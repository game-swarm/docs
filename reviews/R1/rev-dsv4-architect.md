# Swarm 架构评审报告

**评审员**: rev-dsv4-architect (DeepSeek V4 Pro — 架构师方向)
**评审日期**: 2026-06-16
**评审范围**: DESIGN.md (全 2292 行), tech-choices.md (全 223 行), ROADMAP.md (全 109 行), specs/01-09 (全部 9 份规范)
**评审视角**: 系统架构 / ECS 调度正确性 / Tick 生命周期完整性 / 数据一致性 / 算法复杂度 / 确定性保证

---

## 1. 总评 (Verdict)

**APPROVE_WITH_RESERVATIONS** — 设计整体优秀，核心架构决策（Deferred Command Model、WASM 统一执行路径、FDB 权威源、Blake3 单原语策略）均正确且自洽。发现 4 个需修正的问题（D1-D4）和 4 个值得关注的架构风险（R1-R4），均不阻塞 MVP 实现但应在 Phase 1 解决。

---

## 2. 架构亮点 (Strengths)

### S1: Deferred Command Model — 设计合同中最高价值的决策

玩家代码不直接操作世界，通过 `tick(snapshot) → Command[]` 返回指令 JSON，引擎统一校验后应用。这一决策带来连锁优势：

- **单一执行路径**：无论人类还是 AI，无论何种编程语言编译到 WASM，全走 `WasmSandboxExecutor → Command Validation Pipeline → World`，无绕过
- **反作弊天然**：所有 mutating 操作必须经过 Command Validation Pipeline，静态分析变为可能（对比 Screeps 的 `creep.moveTo()` 直接修改 V8 对象）
- **回放简单**：重放只需记录 `RawCommand[]`，不依赖 WASM 重新执行；Wasmtime 版本升级不影响回放
- **MCP 设计干净**：MCP 不需要 `swarm_move`/`swarm_attack` 等工具，AI 必须编写 WASM——与人类走完全相同路径，公平性由 fuel metering 自动保证

### S2: Two-Phase Snapshot Architecture — O(P×E) → O(E + P×R)

DESIGN §3.2 描述的两阶段快照架构（tick 开始一次性构建完整世界快照，按房间分片；每个玩家拼接可见房间分片）是关键的复杂度优化：

- 复杂度的正确性：原始方案 O(玩家数 × 实体数) 在 500 活跃玩家 × 50000 实体时 = 25M 序列化操作/tick，不可行
- 优化后：O(50000 + 500×9) ≈ 54.5K 操作（每玩家可见 ≤9 房间），降低约 3 个数量级
- 确定性的正确性：快照构建在 WASM 执行前完成 → 与玩家顺序无关 → 天然确定

### S3: Blake3 单原语策略 — 优雅的极简主义

将哈希（Blake3）、PRNG（Blake3 XOF）、代码签名（Blake3 keyed hash）统一为 Blake3，这是技术选型中最具架构美感的决策：

- 依赖栈减少一个 crate（ChaCha），审计面减半
- 纯软件 ~6 GB/s，无平台退化（对比 AES-CTR 无 AES-NI 时退化 30×）
- XOF 的 `update_with_seek(seed, offset)` API 天然适配 per-player per-tick 确定性随机序列

### S4: FDB 权威源 + Keyframe/Delta 存储 — 回放完整性保障

Keyframe (每 K tick) + Delta 增量存储模型 + FDB 严格可序列化事务，三者组合提供了：

- 回放可行性：定位最近 keyframe → 重放 delta 链 → 抵达目标 tick
- 存储效率：delta 体积约 keyframe 的 1-5%，整体存储减少 ~90%
- 环境可重现：`mods_lock` + `world_config` 快照确保回放时的规则与模组版本一致

### S5: 三层扩展模型 — 精心设计的可配置性光谱

Layer 1 (Core/IDL 冻结) → Layer 2 (Declarative/world.toml) → Layer 3 (Experimental/world-specific SDK) 的设计清晰划分了稳定性和灵活性的边界：

- Layer 2 覆盖 90% 世界定制需求（纯 TOML 配置，不动 SDK）
- Layer 3 的 `[MOD]` 标记 + 不参与官方排名 + 玩家加入警告，防止碎片化
- `[[custom_actions]]` + `[[special_effects]]` 组合：新特殊攻击只需 TOML 配置，无需 Rust 代码

---

## 3. 发现的问题 (Findings)

### D1 [HIGH] ECS Phase 2b 并行策略需要更严格的数据独立验证

**位置**: DESIGN §3.2 Phase 2b, specs/01 §3.4

**问题**: 设计声明 `regeneration_system` 和 `decay_system` 与主线 `death→spawn→combat→death_cleanup`「无数据竞争」，可并行调度。但此论证不够充分：

```
regeneration_system: 修改 Source.ticks_to_regeneration 和 Source 资源量
decay_system:        修改 drone.fatigue, drone.cooldown, 建筑 cooldown

combat_system:       修改 drone.hits, structure.hits（可能触发死亡标记）
spawn_system:        创建新 entity，修改 Room drone 计数
```

需要明确验证以下交叉点不产生竞态：

| 交叉 | 验证项 |
|------|--------|
| regeneration ↔ spawn | regeneration 不会读取未完全初始化的新 drone（新 drone 没有 Source component，不会命中查询） |
| regeneration ↔ combat | 战斗系统不修改 Source。现已成立 |
| decay ↔ combat | combat 可能因 damage 导致 drone 死亡标记；decay 在 combat 之后运行（`.before(death_cleanup)`）但 combat 已在 `.chain()` 中位于 decay 之前。正确 |
| regeneration ↔ decay | 两者的数据范围交集为空。成立 |

**建议**: 在 spec 中添加一张交叉矩阵表（类似上述），明确列出每对并行系统的数据访问范围和「为什么不冲突」。这比一句「数据独立」更具说服力。同时在确定性 CI 测试中增加针对并行调度的随机线程交错验证（类似 Loom 或 shuttle 的模型检查）。

**严重度**: HIGH — 不修正不会导致 Bug（Bevy 的 `.before()/.after()` 约束已足够），但设计文档中「数据独立」的论证过于宽松，可能在未来增加新系统时引入隐蔽竞态。

---

### D2 [MEDIUM] Dragonfly 缓存与 WebSocket 客户端的初始一致性边界

**位置**: DESIGN §6.2, §3.2 阶段三, specs/01 §4.2

**问题**: 阶段三的流程是：

```
1. FDB commit 成功 → 世界状态已持久化
2. Dragonfly.update(delta) → 更新缓存
3. NATS.publish("tick.{N}", delta) → 推送到客户端
```

新客户端连接时（WebSocket 或 MCP），读取当前世界状态。如果此时：
- FDB 已经写入 tick N+1 的结果，但 Dragonfly 尚未更新（缓存更新和 NATS 发布之间存在微小窗口）
- 或者：Dragonfly 已更新到 tick N+1，但新客户端从 Dragonfly 读到 tick N+1 的实体状态，然后收到 NATS 上 tick N+1 的 delta — 导致 delta 被重复应用？

文档中提到「客户端通过 `last_tick` 字段检测 gap → 主动 fetch」，但未定义初始连接时的 **tick 对齐协议**。具体来说：

1. 客户端连接 → 从 Dragonfly 读取 `current_tick = T` 和对应 snapshot
2. 订阅 NATS `tick.*`
3. 如果收到的第一个 NATS 消息是 `tick.T+1`，正确
4. 如果收到的第一个 NATS 消息是 `tick.T`（在步骤 1 和 3 之间 Dragonfly 还未更新到 T），客户端收到一个已应用的 delta

**建议**: 在连接握手协议中明确：
- 客户端记录 `last_applied_tick` 从 Dragonfly 读取的 tick 号
- 收到 NATS delta 时，忽略 `tick_number <= last_applied_tick` 的消息
- Dragonfly 的当前 snapshot 应携带版本号（tick number），客户端只接受 `tick_dragonfly >= tick_nats - 1` 的情况，否则 fetch full keyframe

**严重度**: MEDIUM — 当前设计（NATS 为轻量推送、允许丢失、客户端 gap detect）在理论上能处理此问题，但初始连接的一致性边界未显式定义。

---

### D3 [MEDIUM] Spawn 在同 tick 参与 combat 的设计意图与玩家预期可能有差距

**位置**: DESIGN §3.2, specs/02 §3.8

**问题**: 文档明确声明新 spawn 的 drone「在同 tick 参与 combat 和 decay——可能出生即被攻击或受衰减影响。此行为是有意设计（『出生即投入战斗』）」。设计意图清晰，但存在以下架构层面的考量：

- **Spawn → 立即死亡**：如果敌方 Tower 在 spawn 房间内且满足攻击范围，新 drone 在 birth tick 就被 Tower 攻击（Tower 攻击在 combat_system 结算，spawn_system 在 combat 之前）。如果新 drone hits 不足 50（Tower 单发 damage），出生即死亡。
- **资源浪费无反馈**：玩家在 tick N 发出 Spawn 命令（Phase 2a 校验通过），tick N 的 combat 立即杀死该 drone。玩家在 tick N+1 才得知 drone 已死。没有任何中间 tick 可操作。
- **Spawn on Cooldown 的保护不足**：Spawn 命令的冷却保护 Spawn 建筑不被滥用，但不保护新 drone 本身。

**建议**: 
- 方案 A（保守）：新 spawn 的 drone 在 birth tick 不受 combat/decay 影响，从 tick N+1 开始参与。通过给新 drone 添加 `SpawningProtection` 标记，让 combat_system 和 decay_system 跳过它们。
- 方案 B（激进，当前设计）：保持现状但显式化为世界规则参数 `spawn_protection_ticks`（默认 0 = 无保护，可配置为 1 = birth tick 保护）。
- 推荐方案 B：保持当前设计的核心哲学不变，但给予服主配置权。Tutorial 世界默认 `spawn_protection_ticks = 1`，标准世界默认 0。

**严重度**: MEDIUM — 设计意图明确且一致，但玩家体验和资源浪费角度存在改进空间。建议至少讨论此问题在设计文档中。

---

### D4 [LOW] `code_update_cooldown` 默认值与 `Deploy-reset` 规则的交互未完全阐明

**位置**: DESIGN §8.2 Code 部署规则, specs/02 §7.2

**问题**: 两条规则之间存在需要澄清的交互：

1. `code_update_cooldown`：两次部署间的最小 tick 间隔（World 模式最小 5 tick）
2. Refund Deploy-reset 规则：「若玩家在 tick N+1 执行了任何部署操作，tick N 及之前累计的 refund credit 清零。例外：同一 session 内的迭代部署」

**场景**: 玩家在 tick N 故意提交大量 `SourceEmpty` 竞争指令 → 获得 50% fuel refund credit。在 tick N+1 部署新代码（refund credit 清零）→ 但 `code_update_cooldown` 最小 5 tick。如果玩家在 tick N 首次部署，tick N+1 不能再次部署 → refund credit 在 tick N+1 未被清零 → 玩家获得额外 fuel。这是否构成为滥用？

**分析**: 实际上不构成滥用——因为：
- 玩家在 tick N 部署后，`code_update_cooldown` 阻止 tick N+1 再次部署 → refund credit 不清零 → 但 refund credit 上限为 `MAX_FUEL × 10%`，且同 tick 竞争失败重复退还仅首次有效 → 最大收益可量化
- 且「同一 session 内的迭代部署不清除 credit」是保护正常迭代的

但设计文档中 `Deploy-reset` 和 `code_update_cooldown` 的关系没有显式交叉引用。建议添加说明，阐明两者互不冲突的设计意图。

**严重度**: LOW — 实际安全，但文档完整性可以改进。

---

## 4. 架构风险 (Architectural Risks)

### R1: ECS 系统顺序的隐式依赖 — 未来扩展风险

**当前设计**: Phase 2b 的 ECS system chain 是：

```
death_mark → spawn → combat → (regen || decay) → death_cleanup
```

其中 `regen` 和 `decay`「与主线并行」。这个结构在**当前系统集**下是正确的，但缺乏一个形式化的依赖图。随着系统增长（未来添加 `weather_system`、`diplomacy_system`、`event_system` 等），需要决定新系统插入的位置。

**风险**: 新开发者可能错误地将系统插入并行区域（与 regen/decay 同级），但新系统可能和 combat 有隐式数据依赖。

**缓解**: 建立一个 ECS System Dependency Matrix（当前 7 个系统的读写集矩阵），新系统添加时要求显式声明读写集并验证无冲突后再确定插入位置。

---

### R2: Rhai 进程隔离的性能上限

**当前设计**: Rhai 模组默认在独立 sandbox 进程中运行（`isolation = "process"`），通过 IPC 与核心引擎通信。

**分析**: 
- 假设 5 个活跃模组，每个模组执行 `tick_start` + `tick_end` 两个钩子 → 10 次 IPC 调用/tick
- 每次 IPC：序列化 WorldState → 传输 → Rhai 执行 → 序列化 actions → 返回 → 应用
- 在 3 秒 tick 目标下，如果每个模组消耗 50ms（IPC + 执行），10 次 = 500ms，仍在预算内
- 但如果服主安装了 20 个模组，IPC 开销可能超过 1s

**建议**: 
- 在 spec 中定义 Rhai 模组的推荐数量上限（如 ≤10 个活跃模组）
- 考虑批量 IPC 模式：一次 IPC 调用执行所有模组的 tick_start 钩子，而非每个模组独立 IPC
- 生产环境的 Rhai 性能基准测试应纳入 CI

---

### R3: Overload 攻击的可见性约束与「静默结果」的张力

**位置**: DESIGN §8.2 特殊攻击方式

**问题**: Overload 的两条约束：

1. 「必须满足 `is_visible_to(target, attacker)`——不可攻击不可见玩家」
2. 「Overload 返回静默结果——攻击者无法从结果推断目标 fuel 状态」

约束 (1) 是正确的隐私保护，但约束 (2) 的「静默结果」在以下场景存在信息泄露面：

- Overload 是一个**指令**，攻击者在 WASM 中提交 `{type: "Overload", target_id: X}`
- 如果 target X 不可见 → 指令被拒绝，RejectionReason 可能是 `PlayerNotFound`（不可见的玩家被视为不存在）或特定于 Overload 的拒绝码
- 攻击者通过**拒绝原因**（而非 Overload 的执行结果）推断出目标存在与否

**分析**: 实际上 specs/02 §3.12 中 Overload 的校验项包含 `target_id 是有效的 player_id`，且 `target_id != player_id`。如果 target 不可见，`is_visible_to` 过滤使之「不存在」→ `PlayerNotFound` 拒绝。攻击者提交 Overload 给多个 player_id，通过哪些被拒绝为 `PlayerNotFound` vs `OnCooldown` 来判断哪些玩家存在且在其视野范围内。

**但**: MCP/WASM 的快照已包含可见房间的所有实体信息。如果攻击者能看到 target 的 drone，就已经知道 target 存在。Overload 不泄露更多信息。真正的风险是：攻击者对**不在视野内**的玩家 ID 进行 prob——这被 `is_visible_to` 阻止。

**结论**: 当前设计安全，但「静默结果」的含义值得在文档中更精确地定义：不是「所有结果都不可区分」，而是「fuel 削减量的具体数值不泄露」。当前 spec 已正确处理。

---

### R4: 单 Engine 实例的水平扩展路径需要更明确的过渡策略

**位置**: DESIGN §3.1a 扩展策略声明

**问题**: 文档列出了三种扩展架构：
1. 单 Engine 实例（MVP, 500 活跃玩家）
2. 单 Engine + FDB 分层缓存（1K-5K 玩家）
3. 水平分片（规模不限）

从架构 2 到架构 3 的过渡涉及「跨分片移动」和「跨 Engine 状态同步」两个核心难题。文档将其标记为「远期关注」，但：

- 如果架构 2 能支持到 5000 玩家，架构 3 可能永远不需要（Screeps 官方服务器的活跃玩家数在数千量级）
- 但「预留分片扩展接口」在数据模型中有体现（ShardId/ShardConfig）→ ROADMAP 确认引擎代码中已存在 sharding 模块（323 行）

**建议**: 
- 评估架构 2 是否已足够覆盖目标用户规模
- 如果水平分片不是近中期需求，考虑将 ShardId 从核心数据路径中移除，仅保留在 config 中作为未来兼容标记
- 当前在引擎代码中包含 ShardId 增加了复杂度但未使用——是一种「过早的抽象」

---

## 5. 数据一致性分析

### 5.1 FDB 权威源模型 — 正确

FDB 作为唯一权威源，Dragonfly 作为非权威缓存，ClickHouse 作为分析存储。一致性模型清晰：

```
写入路径: Bevy World → FDB 事务提交 → Dragonfly 更新 + NATS 发布
读取路径: 
  - Tick 执行: Bevy World 内存（权威）
  - 客户端实时: Dragonfly（非权威） + NATS delta
  - 客户端初始: Dragonfly snapshot → NATS gap fill
  - 回放: FDB keyframe + delta 链（权威）
```

**验证**: FDB 事务失败 → Bevy World 通过 snapshot 恢复 → tick 放弃 → tile counter 不递增。正确性依赖 Bevy World snapshot 的完整性——specs/01 §3.5 的「Bevy World 快照范围清单」覆盖了所有 Resource 和 Component 类型，包括 RNGState 和 PRNG 种子。这是正确且完整的。

### 5.2 COLLECT 结果跨重试缓存 — 正确但有约束

FDB commit 失败重试时复用 COLLECT 结果，不重新执行 WASM。这一优化的前置条件是：

- COLLECT 阶段的结果仅依赖于 tick 开始时的世界状态（快照构建在此阶段）
- EXECUTE 重试仅改变世界状态，不影响已收集的指令

前提成立。但 fuel 退还策略的约束（specs/01 §3.5）需要澄清：首次 COLLECT 时的 fuel 扣费 = 最终扣费。如果重试 3 次后 tick 放弃，fuel 退还。这与「放弃的 tick：世界状态不变，tick_counter 不递增，消耗的 CPU fuel 退还玩家」一致。

---

## 6. 算法复杂度分析

### 6.1 确定性种子洗牌 — O(N log N) per tick

```
seed = Blake3(tick_number || world_seed)
for i in 0..N: position[i] = XOF.read_u64() % (N - i)
```

对于 N=500 活跃玩家，洗牌需要 500 次 XOF 读取 + 500 次取模 → 微秒级 ← 可忽略。

### 6.2 Command 校验 — O(M) per tick

M = 总指令数。每玩家最多 100 条，500 玩家 → M ≤ 50,000。每条指令的校验主要包括 Entity lookup（O(1) via Bevy ECS）、position/range 检查（O(1)）、resource 检查（O(1)）。

总计：50,000 次 O(1) 操作 → 在 500ms EXECUTE 预算内可行。

### 6.3 可见性过滤 — O(E) per tick snapshot

E = 世界实体总数。每个实体的 `is_visible_to` 检查是 O(1)（基于缓存的 HashSet<EntityId>）。每玩家可见性缓存 (tick, player_id) → 计算一次，所有输出面复用。

总计：E ≈ 50,000 → O(50,000) 每 tick → 在 2500ms COLLECT 预算内可忽略。

### 6.4 PathFind 复杂度 — 上限控制

`MAX_PATH_LENGTH = 100` 限制寻路计算爆炸。地形哈希缓存 `(from, to, terrain_hash, player_visibility_fingerprint)` 进一步减少重复计算。A* 在 50×50 格、100 步上限下最坏约 2500 节点扩展 → 毫秒级。

---

## 7. 回放模型验证

**回放协议**: TickTrace 记录 `RawCommand[]`（非 WASM 原始输出）→ 回放不依赖 WASM → Wasmtime 版本升级不影响回放。这是正确的。

**环境重现**: `mods_lock`（模组版本快照）+ `world_config`（世界规则快照）确保回放时的规则环境与记录时一致。keyframe 中的 `state_checksum` 提供完整性校验。

**CI 验证**: specs/01 §3.5 的 FDB 故障注入测试验证快照恢复一致性。但缺少专门的「并行调度确定性」测试——这是 D1 所建议的。

---

## 8. 建议优先级

| 优先级 | ID | 内容 | 类型 |
|--------|-----|------|------|
| P0 | D1 | ECS 并行策略的数据独立验证矩阵 | 文档增强 + CI 测试 |
| P1 | D2 | Dragonfly/WebSocket 初始连接 tick 对齐协议 | 协议规范 |
| P2 | D3 | Spawn birth-tick protection 配置化 | 设计讨论 |
| P2 | R1 | ECS System Dependency Matrix 制度化 | 流程改进 |
| P3 | D4 | Deploy-reset 与 code_update_cooldown 交互文档 | 文档完善 |
| P3 | R2 | Rhai 批量 IPC 性能评估 | 性能工程 |
| — | R3 | Overload 信息泄露 — 已验证安全 | 无需行动 |
| P3 | R4 | ShardId 过早抽象评估 | 架构讨论 |

---

## 9. 结论

Swarm 的架构设计在以下维度表现卓越：
- **安全模型**：WASM sandbox + Deferred Command + 单一执行路径，纵深防御完整
- **确定性**：Blake3 单原语 + seed shuffle + `.chain()` ECS + indexmap + 定点数，所有细节到位
- **公平性**：fuel metering + MCP/WASM 统一路径，AI 与人类天然公平
- **可扩展性**：三层扩展模型 + `[[custom_actions]]`/`[[special_effects]]` 声明式扩展，服主友好

核心建议：将 D1（并行数据独立验证矩阵）和 D2（连接对齐协议）纳入 Phase 1 工作项，其余可在后续迭代中处理。

整体判断：设计已达到实施就绪状态（Implementation-Ready），无阻塞性架构缺陷。
