# R43 Phase 1 Clean-Slate 评审 — 架构评审员 (GLM)

**评审方向**: 架构 — 模式识别、接口直观性、抽象分层、跨模块数据流、组件耦合度、API 设计直觉性
**评审日期**: 2026-06-30

---

## 1. Verdict

**CONDITIONAL_APPROVE**

整体架构设计成熟——两层计算模型（WASM COLLECT / World EXECUTE）、确定性排序与内联应用、Shadow Write + Atomic Publish 持久化、Unique Writer Contract 等核心模式清晰且有说服力。但存在若干接口一致性问题和架构层面的数据流隐患，修复后可达 APPROVE。

---

## 2. 发现的问题

### 2.1 [High] S03 buildsystem 写入 HitPoints 与 S15 单一 HP writer 声明冲突

**文件**: `specs/core/phase2b-system-manifest.md` 第 427 行（R/W 矩阵）, 第 443–447 行（Multi-writer HitPoints contract）

**问题**: R/W 矩阵中 S03 `build` 对 `HitPoints` 标注为 `W`（写入）。但 Multi-writer HitPoints contract 明确声明：

> HitPoints 由两个独立 writer 按严格串行顺序写入：
> - S10 regen → PendingHeal buffer → S15 结算（不直接写 HitPoints）
> - S15 dmg_apply → combat damage + heal + regen 统一结算写入 HitPoints
> - S24 decay → world maintenance decay

S03 build_system 不在此 HP writer 列表内，却被标注为 W。建筑系统在建时是否有 HP 初始值写入需求？如果是，需要声明 S03 为第三个 HP writer（construction domain），并说明其与 S15/S24 的串行关系。如果不需要，矩阵标注应改为 `-` 或 `R`。

**影响**: CI R/W 冲突检测规则（第 501 行）声称"静态分析所有 31 system 的 Component access（基于 §4 矩阵）"。S03 的矛盾标注会导致 CI 检测认为存在未声明的 HP 竞争写入者——要么 CI 拒绝通过，要么规则白名单遗漏导致真实竞争未被捕获。

**修复建议**: 明确 S03 对 HitPoints 的写入语义：
- (A) 如果建筑创建时需设置初始 HP → 将 S03 声明为 construction-domain HP writer，扩展 Multi-writer contract 增加 S03（construction initialization），声明它与 S15/S24 无竞争（建筑初始 HP 与 combat/decay 不交叉同一实体同一 tick）
- (B) 如果建筑 HP 通过 `PendingEntityCreation` 延迟到 S08 spawn_system flush → S03 矩阵改为 `-`，由 S08 承担 construction HP 写入

### 2.2 [High] `host_path_find` 燃料成本模型在实际场景中可能挤压玩家预算

**文件**: `specs/core/wasm-sandbox.md` 第 440 行, `specs/reference/api-registry.md` 第 475–483 行

**问题**: `host_path_find` 成本 = `500 × explored_nodes + 200 × expanded_edges + cache_miss_penalty(固定 2000)`。50×50 房间最坏情况 A* 探索 ~2500 节点 → 单次调用 = 500 × 2500 + 200 × edges ≈ 1.25M+ fuel（占 10M 总预算的 12.5%+）。per-player 最多 10 次 path_find 调用。10 次最坏 case = 12.5M fuel > 10M MAX_FUEL，导致 deterministic fail。

即使 cache hit（无 2000 penalty），10 次中等路径（~500 nodes × 500 fuel = 250K fuel/次 × 10 = 2.5M fuel）也会消耗 25% 玩家总预算用于寻路。相比 host_get_objects_in_range（2000 base + 100/entity），路径搜索的边际成本远高于其他 host function。

**影响**: 在需要频繁跨房间移动（出口穿越、远程攻击部署）的游戏场景下，寻路燃料成本成为显著瓶颈。玩家被迫在"寻路"与"计算策略"间做极端取舍——这可能是有意的策略设计，但文档未声明此设计意图。考虑到路径膨胀滥用检测（cache_miss > 50 即返回空路径）已防止恶意使用，正常使用的成本也应校准到合理区间。

**修复建议**: 
- (A) 重新校准 `explored_nodes` 系数：从 500 fuel/node 降至 ~100–200 fuel/node，使单次寻路在最坏情况 ≤ 500K fuel（5% 预算）
- (B) 引入路径长度系数（短路径便宜，长路径才变贵），而非按 explored_nodes 线性计费——因为 explored_nodes 反映搜索空间而非结果质量
- (C) 如果当前成本是有意的策略压力，在文档中声明此设计意图（类似 Move 作为 action slot 的设计理由声明）

### 2.3 [Medium] 种子轮换算法的可预测性与"防止推断种子空间"目标矛盾

**文件**: `specs/core/tick-protocol.md` 第 268–275 行

**问题**: 种子轮换算法为 `new_seed = Blake3(old_seed || current_tick)`，轮换周期默认 10000 tick。文档声明此机制的目的是"防止长期观察推断种子空间"。但 Blake3 链推导是**完全确定性**的——一旦攻击者获取或推断出当前 `old_seed`（通过统计检测或泄露），他们可以精确计算所有未来 tick 的种子，因为 `current_tick` 是公开的。

R27 T-H1 已明确承认"确定性系统中前向保密不可能"——这部分是诚实的。但 10000 tick 轮换本身**不增加**安全性——它只是定期改变种子值，新种子仍可从旧种子确定性推导。真正的防线是 Statistical Detection + Operator Seed-Bump，而轮换本身不提供边际安全收益。

**影响**: 10000 tick 轮换可能给人一种安全隔离的假象。实际安全保证完全依赖：(1) seed 不泄露（引擎内存保护），(2) Statistical Detection 触发 Operator Seed-Bump。轮换周期本身不是安全控制——它只是定期刷新使旧观测数据失效。

**修复建议**: 在文档中明确声明：种子轮换的目的是**定期使旧的统计观测样本失效**（而非密码学隔离），真正的防泄露防线是 Statistical Detection + Seed-Bump。或直接省略轮换机制，因为 Seed-Bump 可在任何检测到泄露时手动触发。

### 2.4 [Medium] visibility.md 市场可见性规则引用了不存在的活跃工具集

**文件**: `specs/security/visibility.md` 第 63–66 行（§2.5 Market）, 第 69–73 行（§2.6 Leaderboard）

**问题**: visibility.md §2.5 定义了"市场"可见性规则（MARKET: 所有活跃订单对有视野房间的全体玩家可见）。但 API Registry §3.2 中不存在任何 market/trading 工具——`swarm_list_market_orders` 在历史版本中已移至 RFC-gated（api-registry 变更记录中未提及，但 mcp-security.md 第 252 行确认 `swarm_rollback` 已替换）。同样 §2.6 定义了排行榜可见性，但 `swarm_get_leaderboard` 在 API Registry 中标记为 RFC-LEADERBOARD（非 active）。

**影响**: visibility.md 为不存在的工具定义了可见性行为——这是死规范。如果未来添加这些工具，需要重新审查可见性规则是否有变。当前状态下，这些规则可能误导实现者认为市场/排行榜功能已存在。

**修复建议**: 将 §2.5 和 §2.6 标注为"预定义可见性规则——对应工具当前为 RFC-gated，不实现"，或将这些规则移至 RFC 附录。避免在当前目标状态文档中描述不可用的功能行为。

### 2.5 [Medium] Canonical JSON (RFC 8785/JCS) 与整数-only 约束的边界模糊

**文件**: `specs/core/tick-protocol.md` 第 779 行, `specs/core/command-validation.md` 第 41–56 行

**问题**: 确定性合同声明 canonical JSON 遵循 RFC 8785/JCS，且"禁止 IEEE 754 浮点数编码（JCS §3.2.2 定义的数字格式仅限整数）"。但 RFC 8785 §3.2.2 明确支持非整数数字（如 `1.5`、`1e10`）的 canonical 序列化。文档实际禁止的是 `f64` 在 Rust 运行时中的使用，但 JSON 作为序列化格式本身不禁止浮点——WASM 模块的 tick() 输出 JSON 理论上可以包含浮点数字面量。

command-validation.md §1.1 的 Tick 输出 JSON Schema 仅校验 maxItems/深度/字节大小/额外字段，未声明拒绝浮点数。如果 WASM 模块输出 `{"sequence": 1, "action": {"type": "Move", "object_id": 1001.0, "direction": "North"}}`（object_id 为浮点），JSON 解析器会接受但语义不明确。

**影响**: 如果不同语言 SDK 的 JSON 序列化器对整数/浮点的处理不一致（例如 JS 的 `JSON.stringify(1)` vs `JSON.stringify(1.0)`），canonical hash 可能分叉。JCS 对整数和浮点有不同的序列化规则——如果输入混合出现，跨平台 hash 不一致。

**修复建议**: 在 Tick 输出 JSON Schema 中显式声明所有 numeric 字段必须为 JSON integer（非 number），并在反序列化阶段拒绝含有浮点字面量的数值字段。补充到 command-validation.md §1.1 的 schema 定义中。

### 2.6 [Low] `redb_version_counter` 与 `version_counter` 命名碰撞

**文件**: `specs/core/persistence-contract.md` 第 124 行, `specs/security/command-source.md` 第 70 行, `design/README.md` 第 252 行

**问题**: `DeployPayload` 中有 `version_counter`（客户端 per-player/per-slot 单调递增计数器，防重放）。redb 中有 `redb_version_counter`（服务端 deploy manifest 的 redb 原子递增计数器）。README.md 术语表声明："与 `version_counter`（manifest 内字段）语义相同但存储位置不同"——但实际上前者用于**防重放**（拒绝 ≤ current），后者用于**replay 排序**（全序重放），语义并不相同。

**影响**: 术语碰撞可能让实现者混淆两个计数器的用途。防重放检查（`version_counter > current`）和 replay 排序（按 `redb_version_counter` 全序）是两个独立功能，不应被描述为"语义相同"。

**修复建议**: 在术语表中修正定义：`version_counter` = 客户端防重放计数器；`redb_version_counter` = 服务端 replay 排序计数器。明确二者是独立语义而非"存储位置不同"。

---

## 3. 亮点

### 3.1 两层计算模型（WASM COLLECT / World EXECUTE）

**文件**: `design/architecture.md` §1, §5

这是本项目最核心的架构判断：WASM 执行无共享状态、天然并行可水平扩展；World Simulation 确定性串行不可并行。这一分界清晰、自洽且贯穿全局——从 sandbox 容器设计到 worker pool 模型到 NATS queue-group 分发，所有组件选型都服务于这一核心判断。"复杂度只放在真实瓶颈上"（§10 原则 7）是对过度工程化最好的约束声明。

### 3.2 Shadow Write + Atomic Publish 持久化模型

**文件**: `specs/core/tick-protocol.md` §3.5, `specs/core/persistence-contract.md` §8

从旧 per-room 独立 commit 到 Shadow Write + GlobalTickCommit 的升级是关键架构改进。设计精确地消除了"per-room 写入已 durable、全局 abort"的 TOCTOU 窗口——staging 行不是已发布状态，只有 manifest-only publish 才是权威点。跨房间意图在 staging 写入前于 Bevy World 内裁决，避免 post-hoc 合并的复杂度。错误恢复表（§3.5.6）覆盖了所有失败场景且语义统一（tick 放弃 + snapshot 恢复），无 best-effort 降级路径——这是正确的原子性合同。

### 3.3 Unique Writer Contract (S22 status_advance_system)

**文件**: `specs/core/phase2b-system-manifest.md` §Special Attack Unique Writer Contract

将 8 种特殊攻击的状态推进拆分为"并行 buffer 生产 (S16-S22b)"+"串行唯一 committer (S22)"是一个优雅的并发安全设计。各 buffer system 写入互不重叠的 typed buffer，S22 作为唯一 StatusState writer 串行消费——消除了并行写入冲突，同时保留了 buffer 生产的并行性。Buffer 生命周期清晰（tick 结束清空，不跨 tick 持久化）。R/W 矩阵 CI 验证规则确保新增 system 无法违反 unique writer 约束。

### 3.4 Command Source Model — 服务端注入 auth context

**文件**: `specs/security/command-source.md` §2–3

WASM 玩家的 `player_id`、`source`、`tick` 全部由服务端 Source Gate 注入，WASM 不得自报。这一设计从根本上消除了客户端身份伪造的面。全部来源（WASM/MCP_Deploy/MCP_Query/Admin/Replay/Tutorial）的 capability matrix（§2.3）清晰穷举，Admin 路径通过 `WorldMutate` trait 的唯一实现者 `validate_and_apply()` 在编译期保证无绕过——这是一个将运行时安全约束提升到编译期的优秀设计。

### 3.5 Deploy 同步提交状态机

**文件**: `specs/core/persistence-contract.md` §2.3, `specs/reference/api-registry.md` §11

Deploy 状态机（VALIDATE → COMPILE_PREPARE → MANIFEST_COMMIT → ACTIVATION_PENDING → ACTIVE）消除了 TOCTOU 和激活前可用性缺口。redb manifest 是唯一权威记录，`redb_version_counter` 提供严格全序，blob 上传异步但不阻塞激活判定。`compiled_artifact_hash` 是服务端派生字段不进入客户端签名 payload——代码签名审计（`wasm_module_hash`）与运行时 artifact 完整性（`compiled_artifact_hash`）的分离设计精确。

### 3.6 可见性 Oracle 闭合

**文件**: `specs/security/visibility.md` §10

§10 Oracle 防线全面覆盖了跨接口信息泄露风险：`omitted_count` 分桶化防止通过截断计数推断隐藏实体数量；dry_run/simulate/explain_last_tick 脱敏策略确保模拟/调试只暴露自身数据；特殊攻击拒绝码等价策略（`NotVisibleOrNotFound` 统一不可见/不存在，`NotEligible` 统一不满足条件/冷却中）消除了通过拒绝码推断目标存在性或状态的 oracle 路径。这是安全设计中的少见深度——大多数项目止步于 fog-of-war 而不处理调试/管理接口的间接泄露。

---

## 4. CrossCheck — 需要跨方向检查

- **CX1**: [S03 build_system 矩阵中 HitPoints=W 与 Multi-writer contract 仅列 S15/S24 不一致] → 建议 [游戏机制] 检查 [建筑系统是否在创建时写入初始 HP，若是则与 S15 是否存在同 tick 同实体 HP 竞争]
- **CX2**: [host_path_find 燃料成本在实际 50×50 房间场景下可能挤压玩家预算至 deterministic fail] → 建议 [游戏机制/经济] 检查 [寻路成本与玩家策略可行性的平衡关系，是否为有意的策略压力设计]
- **CX3**: [visibility.md §2.5/§2.6 定义了市场和排行榜的可见性规则，但对应工具在 API Registry 中为 RFC-gated（非 active）] → 建议 [接口/API] 检查 [市场/排行榜功能的目标状态定义——是已裁定终点还是已延期项目，文档引用一致性]
- **CX4**: [种子轮换 `Blake3(old_seed || tick)` 是确定性推导，声明"防推断"但实际不提供密码学隔离] → 建议 [安全] 检查 [种子轮换机制是否提供了超越 Statistical Detection + Seed-Bump 的额外安全边际，还是纯粹使旧样本失效的定期刷新]
- **CX5**: [Canonical JSON (RFC 8785/JCS) 允许浮点数序列化，但引擎禁止 f64——JSON 边界的浮点拒绝策略未在 Tick 输出 Schema 中声明] → 建议 [引擎/确定性] 检查 [WASM tick() 输出 JSON 中浮点字面量的处理策略，跨语言 SDK JSON 序列化器对整数/浮点的差异化是否影响 canonical hash 一致性]