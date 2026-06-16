# Swarm 设计评审 — 安全审计报告

**评审人**: Security Reviewer (DeepSeek V4 Pro)
**评审日期**: 2026-06-16
**评审范围**: DESIGN.md, tech-choices.md, ROADMAP.md, specs/ (01-09, 全部 9 篇)
**评审视角**: 协议一致性验证、数据流追踪、竞态条件检测、算法边界审计、信任边界分析

---

## 总体 Verdict

**APPROVE_WITH_RESERVATIONS**

设计中的安全架构基础扎实——Deferred Command Model、WASM 进程隔离、单一校验管线、Source Gate 是不可妥协的安全支柱。发现 2 个 Critical（Overload 信息泄露、spectate_delay 约束缺失）、6 个 High、6 个 Medium 问题需在实现前修正。大部分问题属于边界条件防御不足或跨文档规约不一致，非架构级缺陷。

---

## Critical（阻塞性 — 必须修改设计后重新评审）

### C1. Overload 攻击的静默返回存在两处信息泄露路径

**位置**: DESIGN.md §8.2 特殊攻击方式表 (Overload 行)；specs/02-command-validation-spec.md §3.12；specs/03-mcp-security-contract.md

**问题**: Overload 的设计意图是「返回静默结果——攻击者无法从结果推断目标 fuel 状态」（DESIGN.md line 1141）。但存在两个泄露路径：

1. **间接确认路径**: `value_and_apply()` 必须返回一个结果码。即使不返回具体的 fuel 削减量，返回「成功」vs「TargetFuelTooLow」（specs/02 §3.12）本身就泄露了目标是否在 MAX_FUEL × 0.2 下限以下。状态机的输出差异构成信息通道。

2. **Host function 侧信道**: 攻击者可在同一 tick 内先执行 Overload，再通过 `host_get_objects_in_range` 观察目标 drone 的行为变化（执行命令数骤降 → fuel 不足），或通过 MCP `swarm_get_snapshot` 在下 tick 观察目标是否提交了异常少的指令。

实际上 `TargetFuelTooLow` 拒绝码（specs/02 line 344）直接告诉攻击者「目标 fuel ≤ 2M」，这违反了 DESIGN 中「不可从结果推断 fuel 状态」的设计意图。

**建议**: 
- 移除 `TargetFuelTooLow` 拒绝码——Overload 始终返回成功（即使目标已在 fuel 下限，静默无效）
- 或将 Overload 审计日志写入 ClickHouse 但只对 Admin 可见
- 文档明确记录：完美的信息隐藏在此攻击面不可行，接受「下 tick snapshot 对比」为允许的推理路径

### C2. spectate_delay 约束仅在文档声明、未在设计层强制

**位置**: specs/05-unified-visibility-policy.md §3.5 line 134；DESIGN.md §8.2

**问题**: spec 声明：
> World 模式下若 `public_spectate = true`，`spectate_delay` 必须 ≥ 50 tick

但 `world.toml` 配置段（DESIGN.md §8.3 line 1587）将 `spectate_delay` 默认值设为 0，且 `validate_config()`（specs/07-world-rules-engine.md §9）未校验此约束。这意味着：
- 服主手动设置 `public_spectate = true` 但忘记同步设置 `spectate_delay` → **实时全图信息泄露给旁观者**
- 旁观者可将实时信息传递给正在参赛的玩家，完全破坏 fog_of_war

**建议**:
- 在 `validate_config()` 中添加强制校验：`if visibility.public_spectate && world.mode == "persistent" && visibility.spectate_delay < 50 { error }`
- `spectate_delay` 在 World 模式下的默认值应改为 50（而非 0），Arena 模式保持独立逻辑
- 考虑安全默认：若 `public_spectate` 被启用但 `spectate_delay` 未显式设置，自动 clamp 到 50

---

## High（重要 — 应在 Phase 0 修正）

### H1. Overload per-target 全局冷却的规约冲突

**位置**: DESIGN.md §8.2 line 1140 vs specs/02-command-validation-spec.md §3.12

**问题**: 两处文档对 Overload 冷却逻辑的描述不一致：
- DESIGN.md: 「全局冷却：同一目标每 50 tick 最多被 Overload 一次（不限来源）」
- specs/02 §3.12: 仅列出 per-drone 冷却 200 tick，**完全没有提及 per-target 全局冷却**

如果 specs/02 是实现的权威参考（specs 通常比 DESIGN 更精确），则缺少 per-target 冷却意味着多个 attacker 可以协同在同一 tick 对同一目标叠 Overload，将其 fuel 从 10M 打至 2M（5 次攻击 × 500k），在单 tick 内完成。这比设计意图强 5 倍。

**建议**: 将 per-target 全局冷却写入 specs/02 §3.12，并注明冷却键为 `(target_player_id, tick_applied)`，在 validate 阶段检查。

### H2. Hack/Fortify 控制锁竞态

**位置**: DESIGN.md §8.2 特殊攻击方式表；specs/02-command-validation-spec.md §3.10, §3.15

**问题**: Hack 施加 5-tick 控制锁，Fortify 可「清除目标所有负面状态」包括 Hack 控制锁。在两个玩家同时对同一目标执行 Hack + Fortify 时（可能的 timing：Player A Hacks drone X → Player B（友方）Fortify X 在同一 tick 或随后 tick 清除控制锁）：

- **Phase 2a 顺序依赖**: 若 Fortify 在 Hack 之前执行（洗牌结果），Hack 被 Fortify 清除后立即被 Hack 重新施加——控制锁的 `AlreadyHacked` 检查需要知道 Fortify 是否清除了它
- **跨 tick 竞态**: Tick N: Hack stage=1。Tick N: Fortify 清除 Hack。Tick N+1: Hack 应该从 stage 开始重试还是彻底失败？

当前校验矩阵中 Hack 的 `AlreadyHacked` 检查在 2a 阶段，但 Fortify 的效果也在 2a inline 应用。顺序高度依赖 seeded shuffle。

**建议**: 明确 Fortify 净化后的「免疫窗口」——Fortify 清除 Hack 控制锁后，目标在 Fortify 持续时间内（100 tick）免疫新的 Hack（类似于 Neutral 状态的免疫）。或将 Hack 控制锁设计为不被 Fortify 清除（Fortify 只清除 Debilitate/Drain/Overload，不清除 Hack）。

### H3. `host_path_find` 缓存键泄露可见性信息

**位置**: specs/04-wasm-sandbox-baseline.md §8

**问题**: `path_find` 缓存键为 `(from, to, terrain_hash, player_visibility_fingerprint)`。不同玩家的 `visibility_fingerprint` 产生不同缓存条目。但这并非问题——问题在于 `path_find` **仅基于可见地形计算路径**（specs/04 line 210）。当 to 坐标在 fog of war 中时，返回什么？如果返回「无法到达」或「路径长度 > MAX_PATH_LENGTH」vs 正常路径，攻击者可执行以下探测：

```
for each candidate_enemy_base_location:
    result = path_find(my_location, candidate_location)
    if result has valid path → candidate_location terrain is passable (terrain leak)
    if result is error → candidate_location may have wall or be unmapped
```

结合 terrain 是公开信息（specs/04 line 207: 「地形公开，无需过滤」），此攻击可绘制全地图的可通行性热图——fog of war 仅隐藏实体位置，但 terrain 完全暴露。

**建议**: 
- 对 fog of war 中的坐标，`path_find` 应返回 `Err(LocationNotVisible)` 而非基于部分信息计算
- 或 terrain 应受 fog_of_war 约束——未探索房间的地形不可查询
- `host_get_terrain` 的描述「地形公开，无需过滤」需要重新评估——如果 terrain 真的是公开信息，那 fog_of_war 的防护作用将被大幅削弱

### H4. RNG 种子轮换的可预测性

**位置**: DESIGN.md §8.8；specs/01-tick-protocol-spec.md §3.1

**问题**: 种子轮换使用 `Blake3(old_seed || current_tick)`，每 10,000 tick 一次。攻击者可在 10,000 tick（~8.3 小时）窗口内观察 shuffled player order。每次 tick 的洗牌位置是一个观测值——每个 tick 攻击者知道自己排在哪些玩家前面/后面。10,000 个部分排序观测可能通过 order-revealing 攻击暴露足够的 PRNG 状态信息。

此外，`world_seed` 是"32 字节熵（256-bit）"——但 observable output 空间远小于 256-bit。shuffle order 的熵约为 `log2(N!)` = ~1400 bit for 500 players，每 tick 观测一次。10,000 tick × ~9 bit（排序中位置的相对信息）= ~90,000 bit 观测，远超 seed entropy。

**建议**: 
- 缩短轮换周期到 1000 tick（~50 分钟）作为纵深防御，不依赖 256-bit 的理论安全
- 或使用 forward-secure PRNG scheme：每次轮换后旧 seed 被零化，新 seed 从不可逆的 KDF 派生
- 记录每次 shuffle 应使用独立 nonce（`Blake3(seed || tick || "shuffle")`），而非直接用 seed+tick 做 XOF

### H5. WASM 模块预编译缓存 = 恶意 JIT 代码持久化窗口

**位置**: specs/04-wasm-sandbox-baseline.md §7；DESIGN.md §3.2

**问题**: 模块缓存键为 `(module_hash, wasmtime_version)`。若 Wasmtime 在特定版本存在 JIT 编译漏洞（例如 Cranelift 优化 pass 产生的错误代码生成），恶意 WASM 在**编译阶段**可能触发漏洞，产生包含恶意 native code 的缓存条目。此后每次 tick 实例化该条目时都会执行恶意代码。

设计的安全假设是：
1. 部署时 WASM 经过 `validate_module()` 检查（体积、import 白名单、export 检查）
2. Wasmtime 的 fuel metering 限制执行

但编译阶段的安全边界不同于执行阶段——`Module::from_binary()` 调用 Cranelift（完整的编译器 pipeline），其攻击面远大于实例化。CVE 窗口（72h for Critical）与预编译缓存（持久化到 FDB）的组合意味着：一个利用 0-day JIT bug 的 WASM 模块可能在修复前被编译并缓存，修复后缓存条目仍然包含恶意 native code（因为缓存键不变）。

**建议**: 
- 每次 Wasmtime 版本升级时**强制清除所有预编译缓存**（已通过 `(module_hash, wasmtime_version)` 缓存键部分解决——不同 wasmtime 版本产生不同缓存键。但同一版本内的安全补丁不会改变 version tag）
- 增加缓存键 precision——包含 `wasmtime_build_commit` 或在 CVE 事件后主动 bump cache namespace
- 编译 sandbox 应使用独立进程（现有设计已做到，specs line 314: "编译进程：每次部署独立 fork"），但缓存跨进程共享——需要确保编译进程与执行进程的隔离度一致

### H6. Controller repair 公式歧义

**位置**: DESIGN.md §3.1 (line 222-223)

**问题**: 维修硬上限描述为：
> `max(0, age + 1 - min(0.5, controller_count * 0.5))`

该公式存在歧义：
- 「自然增长（+1/tick）的 50%」意味着最大回退 = 0.5 age/tick，即每 2 tick 降低 1 age
- 但 `min(0.5, controller_count * 0.5)` 暗示多个 Controller 可以叠加维修——`controller_count=2` 时 `min(0.5, 1.0)` = 0.5，收益被截断
- 若玩家有 3 个 Controller，每个 RCL 8 的维修容量为 80 drone/tick——总计 240 drone 可同时维修。但每个 drone 的 age 回退被全局 cap 到 0.5/tick

这并非安全漏洞而是设计矛盾：**容量可叠加但效果不可**。玩家可能误以为多 Controller 加速维修（因为「维修容量」叠加），但实际效果被截断。这可能导致玩家资源投入浪费——但不直接构成安全威胁。

**建议**: 明确文档化：多个 Controller 只叠加**服务容量**（可维修的 drone 数量），不叠加**维修速率**（每 drone 的 age 降低量）。维修速率恒定为 `max 0.5 age/tick`，与 Controller 数量无关。

---

## Medium（中等 — 应在 Phase 1 修正）

### M1. WASM path_find 计算量上限不足

**位置**: specs/02-command-validation-spec.md §4.3；specs/04-wasm-sandbox-baseline.md §6

**问题**: `path_find` 限制 `MAX_PATH_LENGTH = 100`，price = `10,000 + 50/tile` fuel，每 tick 最多 10 次。但无限制的是**起点-终点对的选择**。恶意 WASM 可选择两个不可达点（被 wall 包围的终点），迫使 A* 探索整个房间的所有可达节点后才返回失败。房间 50×50 = 2500 格 × 10 次 × 50 fuel/tile = 1,250,000 fuel——在 10M budget 内。

但这假设 path 探索限制在单房间。DESIGN.md §3.1a 提到 drone 可跨房间移动（通过出口）。跨房间寻路可能探索多个房间的图——50×50×N 个房间。若 attack surface 暴露跨房间寻路，计算量可能指数级增长。

**建议**: 为 `path_find` 增加「最大探索节点数」硬限制（如 5000 节点），在 A* 算法层截断，而非仅靠路径长度限制。跨房间寻路增加独立的 `MAX_CROSS_ROOM_PATH_COST` 上限。

### M2. `host_get_objects_in_range` 范围上限不一致

**位置**: specs/02-command-validation-spec.md §4.2 (MAX_QUERY_RANGE = 10) vs specs/04-wasm-sandbox-baseline.md §6 (host function 5 次/tick)

**问题**: MAX_QUERY_RANGE = 10 对应的扫描半径为 10 格 = 331 个六边形格子。但 `host_get_objects_in_range` 的返回上限仅 64KB（specs/04 line 326）。如果密集区域内有大量实体（例如 500 drone 在范围内），64KB 的响应容量可能被撑满，实体列表被截断——玩家收到**不完整的信息**但未被通知。

WASM 可能基于不完整信息做出错误决策，而无法区分「范围内无实体」vs「实体太多被截断」。

**建议**: `host_get_objects_in_range` 返回结果中增加 `truncated: bool` 字段。当实体数超过响应容量时，返回 `truncated=true` 并用 `max_results` 优先级（最近的 N 个），而非任意截断。

### M3. memory_upkeep_cost 整数溢出路径

**位置**: specs/07-world-rules-engine.md §4 (memory_upkeep_system)

**问题**: 计算为 `(used_bytes * cost_per_byte) / FIXED_SCALE`。其中：
- `used_bytes` ≤ 65536（memory_size 上限）
- `cost_per_byte` 可配置，类型未明确（从 `{Energy: 0.01}` 看起来是浮点？但 Determinism Contract 禁止浮点！）

冲突：`memory_upkeep_cost = { Energy = 0.01 }`（DESIGN.md line 1580）使用小数点，但 DESIGN §8.8 明确规定「禁 f64（跨平台/编译器非确定），数值用 `i64 × 精度因子`」。如果使用 fixed-point 表示，`0.01` 应表示为 `100`（×10000）——但 TOML 配置中写的是浮点字面量。

**建议**: 统一所有 TOML 配置中的浮点值为定点整数 × 精度因子（如 `memory_upkeep_cost = { Energy = 100 }  # 0.01 × 10000`），并在 `validate_config()` 中拒绝浮点数。这与 Determinism Contract 保持一致。

### M4. seed_rotation_interval 可配置且无下限

**位置**: specs/01-tick-protocol-spec.md §3.1 line 211

**问题**: seed_rotation_interval 可通过 `world.toml` 配置（`seed_rotation_interval = 10000`），但 `validate_config()` 未对其进行校验。恶意服主（或配置错误）可设置 `seed_rotation_interval = 0`（每 tick 轮换）或 `seed_rotation_interval = u64::MAX`（永不轮换）。每 tick 轮换可能导致回放数据膨胀（每 tick 一个新 seed epoch），而永不轮换消除了针对 H4 的防御。

**建议**: `validate_config()` 中强制 `seed_rotation_interval ∈ [100, 100000]`。下限 100 防止存储膨胀，上限 100000 确保定期轮换。

### M5. `swarm_simulate` 可能被用作免费计算资源

**位置**: specs/03-mcp-security-contract.md §4.4

**问题**: `swarm_simulate` 以 `0.5 × MAX_FUEL` 预算运行 dry-run，限制为 5/tick (World) / 3/tick (Arena)。但限制以 tick 为粒度——AI agent 可在 tick 间隙无限次调用（MCP 不绑定 tick 周期）。如果 AI 使用 `simulate` 执行搜索/优化（本质上将 swarm engine 用作免费云计算），单次 simulate 的 0.5 × MAX_FUEL = 5M instructions，连续调用可累积大量计算。

**建议**: `swarm_simulate` 增加每小时全局频率限制（如 60/h），与 deploy 的 10/h 类似。或在引擎侧跟踪 simulate 总 fuel 消耗并在超过每日上限后 throttle。

### M6. Rhai inprocess 模式缺少安全守卫

**位置**: DESIGN.md §8.7 line 1907-1920

**问题**: `inprocess` 模式被文档标注为「开发/调试、完全信任所有模组来源」。但存在误用风险——服主可能为了性能在生产环境选择 `inprocess`。一个错误或恶意的 Rhai 模组可在 `inprocess` 模式下：
- 死循环拖垮整个引擎进程（无进程隔离 = 无 watchdog）
- 内存耗尽（无 cgroup 限制）

文档中的安全建议（line 1919-1920）是软性的，不应作为唯一防护。

**建议**: 引擎启动时检测 `inprocess` 模式 + 生产环境标志（如 `--release`）→ 打印醒目的多行 WARNING 并 sleep 5 秒。`inprocess` 模式下自动启用 AST 节点预算硬限制（不可关闭），至少保证死循环可被截断。

---

## Informational（信息性 — 设计亮点）

### I1. Deferred Command Model 的前向安全设计

WASM 模块仅通过 `tick() → JSON` 与引擎交互，所有 mutating 操作走指令管线。这从根本上消除了「WASM 直接修改世界状态」的攻击面。即使 WASM 被恶意编译为任意 native code，其唯一输出是 JSON 字符串——需要经过 Schema validation → Command validation → ECS apply 三层校验。**这是本设计中最强的安全决策。**

### I2. Source Gate 的单一路径强制

所有指令来源（WASM/MCP_Deploy/MCP_Query/Admin/RuleMod）必须通过 Source Gate → Auth Verify → Command Validation Pipeline。specs/09 §2.3 使用 Rust trait 设计保证「编译期阻止任何持有 `&mut World` 的代码绕过 `validate_and_apply()`」。Admin 不过是一个放宽了 `RejectionReason` 阈值的 WASM player——**没有独立的管理员代码路径**。这消除了「管理员忘记权限检查」这一类别的所有漏洞。

### I3. WASM Sandbox 的三层纵深防御

1. **Wasmtime 层**: fuel metering + epoch interruption + 内存限制 + WASI 全禁 + import 白名单
2. **OS 层**: seccomp(BPF) + cgroup v2 + 无网络 namespace + 只读根文件系统
3. **生命周期层**: per-tick fork → execute → kill（无跨 tick 状态保留，防止持久化恶意代码）

三层中的任何一层被突破都不会导致完整逃逸。特别是 no-network-namespace + Unix domain socket 通信的设计，使得即使 WASM→native code 的 sandbox escape 成功，攻击者也处于一个无网络、只读 FS、受 cgroup 限制的进程中。

### I4. Rhai 事务性 Action Buffer

specs/07 §5.1 设计了一个关键安全机制：所有 `actions.*` 调用写入 buffer → 脚本执行完毕后一次性 apply。若脚本超 AST 预算，整个 buffer 丢弃——**部分修改从不落地**。这防止了「模组 script 中途崩溃导致世界状态不一致」的经典 bug。与 FDB 事务的 atomic commit 配合，保证规则模组的副作用完全遵循 ACID。

### I5. 可见性函数单点 (Single Point of Truth)

specs/05 定义了 `is_visible_to(entity, player_id, tick)` 作为唯一的信息过滤函数。所有输出面（WASM snapshot、MCP tools、WebSocket delta、REST API、host functions）必须调用此函数。**不存在「这只是调试信息所以没关系」的例外**（spec line 12）。这消除了「快照说隐藏但 WebSocket 泄露」这一类别的所有信息泄露 bug。

### I6. 反制措施的经济设计

全局存储累进税（DESIGN §8.2 反制机制）不是传统安全控制，而是**经济层面的滥用防护**。存储超过 85% 容量时每 tick 征收 0.2% 税率——囤积垄断变得昂贵，从而防止经济 DoS（单个玩家买断所有关键资源）。这种「安全通过经济学」的风格与游戏的 RTS 本质一致。

### I7. AI 快照安全契约 (Prompt Injection 防御)

specs/03 §6 设计了多层 prompt injection 防御：
- 服务端强制标注 `"untrusted": true, "source_player": N`
- 名称最长 32 字符，仅 `[a-zA-Z0-9 _-]`
- SDK 用分隔符 `‖‖‖GAME_DATA‖‖‖ ... ‖‖‖END_GAME_DATA‖‖‖` 包裹游戏数据
- room name 和 player name 的字符集明确禁止 prompt 分隔符字符

此设计使 AI agent 的 prompt 注入攻击面可控——即使玩家名包含恶意内容，SDK 层的分隔符提供了结构化的不可信数据边界。

---

## 数据流追踪摘要

```
World Snapshot (per-room shards)
    │  ┌─ is_visible_to(player_id) ── 安全: 单一过滤点
    ▼  ▼
WASM tick(snapshot) — 仅接收可见数据
    │  ┌─ fuel metering ── 安全: 10M 指令硬限制
    │  ├─ epoch interruption ── 安全: 2500ms 墙钟硬截止
    ▼  ▼
CommandIntent[] (JSON, 仅含 sequence + action)
    │  ┌─ Schema validation ── 安全: 256KB max, depth≤10
    │  ├─ Source Gate ── 安全: 拒绝非 WASM 来源的 gameplay 命令
    │  ├─ Auth injection ── 安全: player_id 服务端强制覆盖
    ▼  ▼
RawCommand[] (auth context 已注入)
    │  ┌─ 逐指令校验 ── 安全: 所有权/距离/body part/fatigue/冷却
    │  ├─ 资源竞争 ── 安全: 先到先得 + seeded shuffle 公平性
    ▼  ▼
Bevy ECS World — Phase 2a inline → Phase 2b systems
    │  ┌─ FDB 原子提交 ── 安全: 全或无
    │  ├─ 快照恢复 ── 安全: commit 失败 → world.restore(snapshot)
    ▼  ▼
Delta Broadcast → NATS → Gateway → WebSocket
    │  ┌─ is_visible_to(subscriber) ── 安全: 信息过滤
    │  ├─ spectate_delay ── ⚠️ C2: 约束未强制执行
    ▼
Clients
```

**信任边界识别**:
- 不可信 → WASM 模块 (任意玩家上传)
- 不可信 → MCP 客户端 (AI agent)
- 不可信 → WebSocket 客户端
- 不可信 → world.toml 配置 (服主可恶意配置)
- 半可信 → Rhai 模组 (服主安装，有签名验证，inprocess 模式危险)
- 可信 → Bevy ECS 核心
- 可信 → FDB 事务层
- 可信 → Source Gate + Auth Verify

---

## 审计覆盖统计

| 严重级别 | 数量 | 涉及文档 |
|---------|------|---------|
| Critical | 2 | specs/02, specs/05, DESIGN.md |
| High | 6 | specs/01, specs/02, specs/04, DESIGN.md |
| Medium | 6 | specs/02, specs/03, specs/04, specs/07, DESIGN.md |
| Informational (亮点) | 7 | 全 9 篇 spec |
| **总计** | **21** | |

---

## 建议优先级

1. **立即修正（Phase 0）**: C1 (Overload 信息泄露), C2 (spectate_delay 强制校验)
2. **Phase 0-1**: H1 (Overload 规约对齐), H2 (Hack/Fortify 竞态), H3 (terrain 信息公开性), H4 (RNG 轮换周期), H5 (JIT 缓存 namespace)
3. **Phase 1**: M1-M6 (边界条件加固)

END OF REVIEW
