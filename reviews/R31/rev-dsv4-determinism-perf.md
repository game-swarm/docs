# R31 Determinism & Performance 独立评审

**评审员**: rev-dsv4-determinism-perf (DeepSeek V4 Pro)
**日期**: 2026-06-21
**文档集**: design/README.md, design/engine.md, design/tech-choices.md, specs/reference/api-registry.md, specs/core/01-tick-protocol.md, specs/core/02-command-validation.md, specs/core/04-wasm-sandbox.md, specs/core/05-persistence-contract.md, specs/core/06-phase2b-system-manifest.md

---

## 1. Verdict

**CONDITIONAL_APPROVE**

设计在确定性保证方面做到了系统性覆盖——非确定性源（HashMap→IndexMap、f64→定点整数、WASI clock/random 禁用）已全面消除。Blake3 单原语覆盖哈希+PRNG，canonical sort tiebreaker 链完整。Phase 2b 31-system manifest 有完备的 R/W 矩阵和并行安全证明。

发现 **2 个 High** 问题：H1（EntityId 分配器确定性未显式保证）和 H2（S22 Phase 2 实体迭代顺序未在伪代码中显式排序）。**4 个 Medium** 问题：M1（canonical_json 数值规范不够精确）、M2（tick latency slack 为零）、M3（CrossRoomIntent timeout 与 EXECUTE budget 矛盾）、M4（Hack TOCTOU 窗口的 pre-Hack owner 缓存未明确定义）。这些均可在不改变整体架构的前提下修复。

---

## 2. 发现的问题

### H1 — EntityId 分配器确定性未显式保证 [High]

**文件**: `specs/core/06-phase2b-system-manifest.md` §3 (Entity Creation/Despawn Order), §S14

**问题**: S14 `special_attack_reducer` 的 merge sort key 使用 `intent_source.entity_id`（第 199 行）:
```
按 (priority_class, intent_source.entity_id, intent_target.entity_id) 确定性归并排序
```
同时，Entity Creation Order（§3）声明 "所有新实体追加到 pending_entities...按 StableEntityId 排序"。但 **EntityId 分配器的确定性未被显式合同化**——没有文档说明 EntityId 在 replay 时是否从确定性 seed 派生产生相同的 ID 序列。若 EntityId 分配器使用自增计数器（非确定性 seed 驱动），同一 tick 的 replay 可能产生不同的 entity_id，导致 S14 的 sort 结果不同→状态分歧。

**影响**: 跨 replay 的 world state 校验可能失败——同一 tick、同一输入产生不同的 state_checksum。

**修复建议**: 
1. 在 `06-phase2b-system-manifest.md` §3 或 `design/engine.md` §3.3 中显式声明 EntityId 分配器使用确定性 seed（如 `Blake3("entity_id" || world_seed || tick.to_le_bytes())` 派生起始 counter，per-entity 递增）。
2. 在 §4 R/W 矩阵中为 EntityId allocator 增加一条确定性合同（即使它不是 ECS system）。
3. 在 CI 验证项中增加 EntityId 确定性检查——跨 `--release`/`--debug` 比较 entity_id assignment 序列。

---

### H2 — S22 Phase 2 实体迭代顺序未在伪代码中显式排序 [High]

**文件**: `specs/core/06-phase2b-system-manifest.md` §S22 Phase 2 (第 257 行)

**问题**: S22 `status_advance_system` 的 Phase 2 伪代码:
```
// Phase 2: Apply buffer effects from S16-S22b (ongoing status tick effects)
for each entity with active StatusState:
    if HackBuffer[entity] → apply hack stage progression
    ...
```
这个循环未指定实体迭代顺序。虽然 Principle 4（第 15 行）声明了 blanket rule "所有系统内实体迭代按 StableEntityId 或 canonical key 排序"，但 **(a)** S22 的 Phase 2 是 per-entity 聚合 buffer effects 应用，不是典型的 Bevy query 迭代；**(b)** 多个 status effect 对同一 entity 的叠加顺序（如同一 entity 同时有 DrainBuffer 和 OverloadBuffer）未在代码中显式声明。

**影响**: 若实现时使用 HashMap/HashSet 查找 buffer 的 entity，迭代顺序可能非确定性→同一 tick 的 status effect 应用顺序不同→ResourceAmount/FuelBudget 的最终状态可能不同。

**修复建议**:
1. 在 S22 Phase 2 伪代码中显式添加迭代排序——如 `for each entity in sorted(entities_with_active_status, key=StableEntityId)`。
2. 声明 per-entity 内多个 buffer effect 的应用顺序（建议按 §S14 的 canonical priority 链：Hack > Drain > Overload > Debilitate > Disrupt > Fortify > Leech > Fabricate——与 Phase 1 保持一致）。
3. 在 §4 R/W 矩阵的 parallel safety proof 中增加 S22 内部确定性保证。

---

### M1 — canonical_json 数值表示规范不够精确 [Medium]

**文件**: `specs/core/02-command-validation.md` §2.1 (第 99 行)

**问题**: `canonical_json()` 规则仅列 "键排序、无空格、数值无尾零、字符串 NFC 归一化"。"数值无尾零" 未规范以下边界情况:
- 整数 `1000` 是否允许写成 `1000.0`？（后者无尾零但有小数点）
- 是否允许科学计数法 `1e3`？
- 前导零 `00100` 是否允许？

虽然所有 f64 已被定点整数（i64/u64）替代（api-registry.md §0 定点类型注册表），整数仍有多种合法 JSON 表示。RFC 8259 允许 `1000`、`1000.0`、`1e3` 均为合法 JSON number。

**影响**: 不同 JSON serializer（serde_json、simd-json、不同语言的 JSON 库）可能对同一整数值产生不同的字符串表示→`command_hash` 不同→tiebreaker 结果不同→排序分歧→world state 分歧。

**修复建议**:
1. 扩展 `canonical_json()` 规范：所有数值必须为**整数格式**（无小数点、无科学计数法、无前导零；0 除外）。`1000` ✓，`1000.0` ✗，`1e3` ✗，`0100` ✗。
2. 在 `specs/reference/api-registry.md` §0 定点类型注册表中引用此格式化规则。
3. 或者：使用二进制格式（如 bincode + canonicalization）替代 JSON 用于 command_hash 计算——消除序列化格式歧义。这是更彻底的方案，但实现成本更高。

---

### M2 — Tick latency slack 为零 [Medium]

**文件**: `design/engine.md` §3.4.1 (第 290-298 行)

**问题**: Tick interval 3000ms，各阶段预算总和刚好 3000ms:
```
SNAPSHOT build:  ≤200ms (p95)
COLLECT:         ≤2500ms
EXECUTE:         ≤400ms
COMMIT:          ≤50ms (p99)
BROADCAST:       ≤50ms
─────────────────────────
Total (p95/p99):  3200ms  ← 已超过 interval
Total (p50):      远低于 3000ms
```

虽然各阶段是 p95/p99 上限且正常情况下远低于上限，但当 COLLECT 在 2500ms 超时（多个慢玩家超时截断）后仍需 400ms EXECUTE + 50ms COMMIT + 50ms BROADCAST = 500ms 后续处理。此时总耗时 ≥ 3000ms，下一 tick 立即开始——无调度余量。任何阶段的 GC 暂停、OS 抖动或瞬时负载峰值都会导致 tick 漂移累积。

**影响**: 连续多个 tick 在 deadline 边缘运行会导致 tick rate 退化→玩家体验下降。500-player target 下的容量推导假设 p50=5ms WASM 执行时间，但未为 p99 玩家（15ms）预留足够的 slack。

**修复建议**:
1. 将 tick interval 从 3000ms 放宽到 3200ms（+200ms slack），或收紧各阶段 budget 总和到 2800ms（如 COLLECT ≤2300ms、EXECUTE ≤350ms）。
2. 增加 explicit slack budget（≥100ms）作为 "调度余量"，在 CI 中作为 hard constraint 回归测试。
3. 或引入 adaptive tick interval：当连续 N tick 延迟 > 阈值时自动延长 interval（降级模式），恢复后缩短。此方案需在 RUNBOOK 中定义降级策略。

---

### M3 — CrossRoomIntent timeout 3000ms 与 EXECUTE budget 400ms 矛盾 [Medium]

**文件**: `specs/core/01-tick-protocol.md` §3.5.4 (第 441 行), `design/engine.md` §3.4.1

**问题**: CrossRoomIntent 处理协议中提到 timeout=3000ms:
```
3. 超时处理 (timeout_ms = 3000):
   ├─ 超时 → deterministic rejection（所有未完成的 cross-room intent 标记 REJECTED）
   └─ 或 tick abandon + snapshot restore（若 critical intent 超时）
```
但 EXECUTE 阶段的硬超时天花板是 500ms（01-tick-protocol.md §1.4），且 budget target 是 400ms（engine.md §3.4.1）。3000ms 的 CrossRoomIntent timeout 远超整个 EXECUTE budget。

**影响**: 文档不一致——实现者可能按 3000ms 实现 CrossRoomIntent 超时（阻塞整个 tick），或按 EXECUTE budget 实现（提前 deterministic reject）。两种行为产生不同的 replay 结果。

**修复建议**:
1. 澄清 3000ms 是 "仅用于 FDB 分区极端故障场景的绝对上限"（如网络分区），正常路径的 CrossRoomIntent latency 应在 EXECUTE budget（400ms）内完成。
2. 或：将正常路径的 CrossRoomIntent deadline 统一为 EXECUTE budget，将 3000ms 标记为 "operator-configurable emergency ceiling"。
3. 确保 deterministic rejection 规则在两种模式下一致——无论按哪个 timeout 触发 reject，拒绝的 intent 集合必须相同（按 canonical sort order 截断）。

---

### M4 — Hack TOCTOU 窗口：pre-Hack owner 缓存未明确定义 [Medium]

**文件**: `specs/core/01-tick-protocol.md` §3.3 (第 373 行), `specs/core/02-command-validation.md` §3.10 (第 306-308 行)

**问题**: Phase 2a TOCTOU 合同规则 2（第 373 行）：
```
Hack 施加控制锁后，原 owner 的后续 friendly/attack/recycle 命令仍以原始 owner 身份校验
```
但 S01 `command_executor` 在处理 Hack 命令时是否缓存了 **pre-Hack owner** 供同 tick 后续命令使用？当前文档没有描述这个缓存机制。如果 S01 在 Hack 命令后重新查询 Bevy World 中的 owner 字段——而此时 Hack 的 effect 尚未应用（Phase 2a 只校验，effect 由 Phase 2b S14→S22 处理）——那 owner 字段未被修改，TOCTOU 保护自然成立。但如果 Phase 2a inline 的 Hack 处理会**立即修改**某个中间状态（如 PendingSpecialAttackIntent 中的标记），则需确认该标记不会影响后续 owner 校验。

实际上，根据 06-phase2b-system-manifest.md R30 B1：S01 对特殊攻击命令只写入 PendingSpecialAttackIntent buffer，不修改目标状态。这意味着 Hack 在 Phase 2a 不修改 owner→TOCTOU 保护自然成立。但文档未显式声明这个「不修改 owner」的承诺。

**影响**: 实现者可能误以为 Hack 应在 Phase 2a 中立即应用 effect（如标记 target 为 "hacked"），从而影响同 tick 后续 owner 校验。

**修复建议**:
1. 在 01-tick-protocol.md §3.3 规则 2 中显式补充："Hack 在 Phase 2a 仅写入 PendingSpecialAttackIntent（不修改 target.owner）。同 tick 后续命令的 owner 校验基于 Phase 2a 开始时的 Bevy World owner 值——即 Hack 前的 owner。"
2. 在 06-phase2b-system-manifest.md §S01 的 Note 中确认特殊攻击不修改 target 的任何 Component。

---

### L1 — PER_CORE_MIPS 常量未标注可配置性 [Low]

**文件**: `design/engine.md` §3.4.2 (第 332 行)

`PER_CORE_MIPS = ~500 MIPS/core` 在不同 CPU 微架构上差异显著（Zen4 ~600, Ice Lake ~450, ARM Neoverse N2 ~400）。admission 公式依赖此值决定是否拒绝新玩家（`MIN_FUEL` 阈值检查）。若固定 500，在慢 CPU 上可能过估容量导致 COLLECT 超时。

**建议**: 标注 PER_CORE_MIPS 可通过 world.toml 配置，或基于启动时 micro-benchmark 自动校准。

---

### L2 — Seed rotation 前向保密 tradeoff 确认 [Low]

**文件**: `specs/core/01-tick-protocol.md` §3.1 (第 258/262 行)

`new_seed = Blake3(old_seed || current_tick)` — 文档已承认 "真正的密码学前向保密不可能"（第 262 行）。这是确定性与安全性之间的已知 tradeoff，非缺陷。仅确认此设计选择已显式记录。

---

### L3 — Dragonfly 缓存滞后描述歧义 [Low]

**文件**: `design/README.md` §3 (第 173 行)

Dragonfly 被描述为 "允许 ≤2 tick 滞后"，但 engine.md §3.2 BROADCAST 阶段 "通过 NATS → Gateway → WebSocket 客户端发布" 和 "Dragonfly 缓存更新" 是实时广播。≤2 tick 滞后是退化场景（如 Dragonfly 重启后追赶）而非正常操作——建议明确标注。

---

## 3. 亮点

1. **系统性的确定性设计**：Fixed-Point Type Registry（api-registry.md §0）全面替代 f64，IndexMap 替代 HashMap，WASI clock/random 禁用，Blake3 XOF 覆盖 PRNG——非确定性源消除覆盖面完整，不留死角。

2. **Phase 2b 31-system manifest 的并行安全证明**：R/W 矩阵（§4）覆盖全部 31 个 system，Combat Parallel Set A 按 target_id partition、Status Buffer Production Parallel Set B 按 typed buffer 分离、S22 唯一 StatusState writer——并行安全证明逐项可验证，RoomCap 中间态保护显式声明。

3. **canonical sort tiebreaker 链完整**：`(priority_class, shuffle_index, source_rank, sequence, command_hash)` 五元组排序 + `canonical_json()` 规则（键排序、无空格、无尾零、NFC 归一化）——tiebreaker 覆盖到命令级，无模糊窗口。`command_hash` 使用 RawCommand（含服务端注入字段）防止不同玩家间 hash 碰撞。

4. **Seed 安全的分场景方案**：Arena commit-reveal（赛中不可见、赛后审计）与 World operator seed-bump + statistical detection——不试图用单一机制解决两种场景的不同需求。种子归档在 keyframe 中完成，不依赖外部 seed archive。

5. **WASM 预编译 + Store reset 模型**：部署时预编译为原生码，tick 时仅实例化——消除 JIT 编译延迟的非确定性。Store reset 保证 tick 间无状态泄漏。WASI 白名单模式（默认全禁）将攻击面最小化。

6. **snapshot 两阶段架构**：一次性全量快照 + per-player 视野拼接——复杂度从 O(P×E) 降至 O(E + P×visible_rooms)，消除 per-player 重复序列化。快照在 COLLECT 开始前完成，与玩家顺序无关。

7. **Overload 抗永久锁死证明**（02-command-validation.md §3.17）：数学证明全局冷却 + 下限 + 恢复速率保证无攻击者组合能永久锁死目标 fuel budget——此级别的机制安全分析在游戏设计中罕见且值得称赞。

---

## 4. CrossCheck

以下问题超出 Determinism & Performance 方向范围，需跨方向检查：

- **CX-1**: EntityId 分配器确定性依赖（H1）→ 建议 **Architecture** reviewer 检查 `design/engine.md` 或 engine 组件 spec 中是否存在 EntityId 分配器的确定性合同。若不存在，需新增。

- **CX-2**: canonical_json 数值规范（M1）→ 建议 **Security** reviewer 检查 `canonical_json()` 的完整规范文档（若独立存在），验证跨语言实现（Rust serde、JS JSON.stringify、Go encoding/json）是否可收敛到同一规范。若 R30 M1 已修复，确认修复是否覆盖了整数格式歧义。

- **CX-3**: CrossRoomIntent timeout 与 EXECUTE budget 矛盾（M3）→ 建议 **Architecture** reviewer 检查 FDB room-partition 的 2PC 协议延迟合同，统一正常路径 deadline。

- **CX-4**: Overload 参数可配置性下的锁死证明→ 建议 **Gameplay** reviewer 检查 world.toml 中 `overload.fuel_recovery_rate` 和 `MAX_FUEL` 的可配置范围——若服主将 recovery_rate 设为 0 或下限设为 0，锁死证明是否仍成立。

- **CX-5**: WASM 输出超 256KB 整 tick 丢弃且不计 refund→ 建议 **Gameplay / Interface** reviewer 评估此设计对玩家的影响——单条超长指令导致整个 tick 的合法指令被丢弃，是否存在更精细的截断策略（如截断到 100 条命令而非全丢弃）。

- **CX-6**: 02-command-validation.md §3.16 特殊攻击状态机矩阵明确声明 "权威优先级链见 06-phase2b-system-manifest.md §S14"，避免了跨文档重复。→ 建议 **Architecture** reviewer 验证所有引用 S14 优先级链的文档是否使用一致引用格式（不复制粘贴优先级链）。