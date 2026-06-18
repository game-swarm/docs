# R15 Determinism Review — DeepSeek V4 Pro

**Reviewer**: rev-dsv4-determinism (确定性评审员)
**Date**: 2026-06-18
**Scope**: Phase 1 Clean-Slate — design/README.md, design/engine.md, specs/core/01-tick-protocol.md, specs/core/02-command-validation.md, specs/core/04-wasm-sandbox.md

---

## Verdict: CONDITIONAL_APPROVE

The determinism foundation is exceptionally strong — fully specified PRNG, ordered data structures, single-path command execution, deferred command model. However, **one critical sort-key contradiction (§3.1 vs §9.1)** must be resolved before implementation, and a cluster of medium-severity issues need clarification.

---

## Strengths

1. **Blake3 XOF 确定性 PRNG**：命名空间隔离 (`combat/loot/npc_spawn/event`)，独立流派生，无 OS 熵源依赖。这是业界最佳实践的确定性 RNG 设计。

2. **`IndexMap` 替代 `HashMap`**：Resource.amounts、Source.produces 均使用 IndexMap，保证迭代顺序确定。明确禁止 `std::HashMap`。此模式已贯穿引擎核心数据模型。

3. **f64 显式禁用**：「数值：整数 + 定点数，禁用 `f64`（跨平台/编译器非确定）」— 01-tick-protocol.md §7.1。配合 `u64`/`i64` 定点整数、saturating 溢出、floor 舍入——数值管道完全确定。

4. **种子洗牌 (Seeded Shuffle)**：Fisher-Yates + `Blake3("shuffle" || world_seed || tick)` — 每 tick 公平轮换玩家顺序，同时保证确定性 replay。前向保密威胁模型清晰（接受定期轮换 + 服主 epoch bump 为操作层面缓解）。

5. **Deferred Command Model**：WASM 只输出 `CommandIntent[]` JSON，所有状态变更经单一 `validate_and_apply()` 管线。无 mutating host function。杜绝了并行写入冲突的整个类别。

6. **Snapshot 架构三重确定**：(1) tick 开始时一次性构建，按房间分片；(2) WASM tick() 和 MCP query 见同一份快照；(3) 截断排序键 `(distance_to_drone, entity_id)` 完全基于世界状态确定值。`O(entities + players × visible_rooms)` 复杂度，消除 per-player 重复序列化。

7. **Bevy World 快照恢复**：Phase 2a 前完整深拷贝，FDB commit 失败时 `world.restore(snapshot)` 回滚所有 Component + Resource。COLLECT 结果跨重试缓存，fuel 不追加扣费。CI 中 10% 随机故障注入验证一致性。

8. **TickTrace 完整性链**：`chain[i] = Blake3(chain[i-1] || tick_trace_i)`，与 FDB 状态写入同一事务——「状态成功但审计不完整」被事务原子性杜绝。TickTrace 写入失败 = tick 放弃。

9. **WASM 沙箱确定性封闭**：禁用 wasi:random/wasi:clocks/wasi:sockets，禁用线程/atomics。seccomp 白名单拒绝 `getrandom`/`clock_gettime`。Store reset 每 tick 清零线性内存 + fuel counter。

10. **Phase 2b 并行安全证明**：regeneration/decay 与主线系统的 Component 读写矩阵显式证明无数据竞争——确定性不依赖并行度。

---

## Issues Found

### D1 — Critical: 排序键定义矛盾 — §3.1 vs §2.1 vs §9.1 三者不一致

**位置**: 
- 01-tick-protocol.md §3.1 伪代码: 全局队列键 `(order_index/shuffle_index, sequence)` 
- 02-command-validation.md §2.1: 全局排序键 `(priority_class, shuffle_order, source, sequence)`
- 01-tick-protocol.md §9.1: 全局排序键 `(priority_class, shuffle_index, sequence, source)`

**问题**: `source` 字段在排序键中的位置不一致。在 §2.1 中 `source` 排在 `sequence` 之前，在 §9.1 中排在 `sequence` 之后。对同时通过 WASM 和 MCP_Deploy 提交指令的玩家，这两个排序键产生不同的执行顺序：

```
§2.1 排序 (source before seq):      §9.1 排序 (seq before source):
1. WASM seq=1                       1. WASM seq=1
2. WASM seq=2                       2. MCP_Deploy seq=1
3. MCP_Deploy seq=1                 3. WASM seq=2
```

**影响**: 任何使用双 source 的玩家（包括 Admin 通过 MCP 部署 + WASM 执行），其命令执行顺序由实现者选择的排序键版本决定——不同实现者可能分叉。这直接违反确定性回放合同。

**建议**: 统一为 `(priority_class, shuffle_index, source, sequence)`（source 优先于 sequence），因为：(1) 不同 source 的 sequence 空间独立，同一 sequence 编号含义不同；(2) source 优先级本身就有语义（WASM > MCP_Deploy）；(3) §2.1 的定义在 per-source sequence 空间的上下文中更合理。

### D2 — High: RNG 种子派生字符串拼接语义未指定分隔符

**位置**: engine.md §3.3, 01-tick-protocol.md §9.5

**问题**: `Blake3(stream_name || world_seed || entity_id.to_le_bytes() || tick.to_le_bytes())` 中的 `||` 未定义是否使用分隔符。纯裸拼会产生种子碰撞：
- `Blake3("combat" || seed || eid || tick)` 
- `Blake3("com" || "bat" || seed || eid || tick)` — 若有人将 stream_name 拆分为两个参数即碰撞

Blake3 作为 XOF 无 domain separation 防护，裸拼接的种子派生在不同代码路径中可能意外碰撞。

**建议**: 统一使用带长度前缀的分隔方式，或显式插入分隔字节（如 `0xFF`）：
```
seed = Blake3(len(stream_name).to_le_bytes() || stream_name || world_seed || entity_id || tick)
```
或使用 Blake3 keyed hash 模式作为 domain separator。

### D3 — Medium: `active_players` 在 shuffle 前的初始排序未指定

**位置**: 01-tick-protocol.md §3.1

**问题**: `seeded_shuffle(&active_players, &seed)` — Fisher-Yates shuffle 的输出依赖于输入序列的初始顺序。若 `active_players` 来自 `HashSet` 或其他非确定性集合，不同编译/运行中的初始向量顺序不同 → 相同的 seed 产生不同的 shuffle 结果 → 确定性破碎。

**建议**: 显式指定 `active_players` 必须先按 `player_id` 升序排列再传入 shuffle。

### D4 — Medium: Snapshot 截断的 `distance_to_drone` 参考点模糊

**位置**: 02-command-validation.md §2.3

**问题**: 截断排序键使用 `(distance_to_drone, entity_id)`，但一个玩家可能拥有多个 drone 分布在多个房间。距离以哪个 drone 为参考？若未指定，不同实现可能选择「第一个 drone」「最近 drone」「正在执行的 drone」→ 截断结果不同。

**建议**: 明确指定使用**该玩家在快照中排序第一的 drone**（按 entity_id）作为距离参考点，或使用 `(min_distance_to_any_player_drone, entity_id)`。前者更简单确定，后者更公平但需要额外计算。

### D5 — Medium: Bevy ECS archetype 迭代顺序跨编译版本不保证稳定

**位置**: 01-tick-protocol.md §3.4, §9.6

**问题**: 文档声称 ECS `.chain()` 保证确定性的系统间顺序，但 Bevy 在一个系统**内部**对实体的迭代顺序由 archetype 存储结构决定。archetype 迭代顺序在同一二进制内确定，但可能因编译器优化级别、release/debug 模式、甚至 Bevy 版本升级而改变。这意味着同一 tick 的 replay 在不同构建中可能分叉。

**建议**: 
- (a) 在确定性合同中声明「仅承诺同 binary 同 Bevy 版本的 replay」；或
- (b) 对所有 ECS system 内的实体迭代显式加入 `entity_id` 排序（在系统入口处收集 → 排序 → 处理）

### D6 — Medium: Recycle 退还公式使用浮点表示法但全局禁用 f64

**位置**: 02-command-validation.md §3.18

**问题**: 
```
refund_pct = max(0.1, 0.5 × (remaining_lifespan / total_lifespan))
```
此公式以十进制浮点表示（0.1, 0.5），与 §7.1 全局 f64 禁令冲突。整数除法 `remaining_lifespan / total_lifespan` 会截断为 0（两者均为 u32），导致所有非满 lifespan drone 的 refund 均降至 10% 下限。

**建议**: 改为定点整数（basis points）：
```
refund_basis_points = max(1000, (remaining_lifespan * 5000) / total_lifespan)
refund = body_cost * refund_basis_points / 10000
```
这与 engine.md §3.4.8 的「比例计算: `amount * basis_points / 10000`」一致。

### D7 — Medium: `player_visibility_fingerprint` 未定义

**位置**: 04-wasm-sandbox.md §8

**问题**: `host_path_find` 缓存键包含 `player_visibility_fingerprint`，但该概念在整个规范中无定义。它是可见实体 ID 集合的 hash？fog_of_war 状态？若未精确定义其计算方式，path_find 缓存在不同实现中命中/未命中行为不同——虽然这主要影响性能而非正确性（path_find 本身只读），但若缓存键碰撞导致返回错误路径则影响功能性。

**建议**: 定义 `player_visibility_fingerprint` 为 `Blake3(visible_entity_ids_sorted || fog_of_war_mask)`，或改为不使用此字段（让缓存自然因 snapshot 不同而失效）。

### D8 — Low: Overload fuel budget 的「pre-clamp true value」语义歧义

**位置**: 02-command-validation.md §3.17 证明

**问题**: §3.17 证明中恢复计算使用 pre-clamp value（2.1M），但 §3.12 说 Overload「apply 阶段静默 clamp 至下限」。正式状态机必须明确：fuel_budget 存储的是 clamped 值还是 true 值？若存储 clamped 值（2M），则 §3.17 的恢复起点应为 2M 而非 2.1M——证明需要重新验证。若存储 true 值但 clamp on read，需要额外字段。

**建议**: 显式分离 `fuel_budget_raw`（未 clamp 的真值）与 `fuel_budget`（clamped 展示值），恢复基于 raw，展示用 clamped。

### D9 — Low: wasm_simd 默认 true 的跨 CPU 确定性风险

**位置**: 04-wasm-sandbox.md §2.2

**问题**: World 模式下 `wasm_simd` 默认 true。SIMD 指令在不同 CPU 微架构（Intel/AMD/ARM）上可能因舍入模式、指令延迟、FMA 融合等产生不同结果。虽然 f64 被禁，但即使是整数 SIMD，某些边缘指令（如 i64x2.mul 溢出行为）在不同 Wasmtime 版本/目标上可能有差异。当前文档未论证 SIMD 是否跨架构确定。

**建议**: 
- (a) 锁定 World 模式也默认禁用 SIMD（牺牲性能换确定性保证）；或
- (b) 在 01-tick-protocol.md 确定性合同中声明「仅保证同 CPU 架构的 replay 确定性」并添加架构标签到 TickTrace

### D10 — Low: world_seed 轮换时 in-flight RNG 状态迁移未定义

**位置**: 01-tick-protocol.md §3.1 seed rotation

**问题**: seed 每 10000 tick 轮换，但持续效果（Hack 5-stage 状态机、Fortify 100 tick 护盾、Debilitate 50 tick 易伤）跨越轮换边界。若这些效果依赖旧 seed 的 combat RNG 状态，切换到新 seed 后，新 tick 的随机判定（如 Tower 自动攻击命中、伤害浮动）突然使用不同的 RNG 流——确定性 replay 无法通过简单地切换 seed epoch 来重现。需要明确定义 RNG 流如何从一个 epoch 迁移到下一个。

**建议**: 每个持续效果的 RNG 状态存储在 entity component 上（如 `RngState { stream: Blake3XofState }`），不依赖全局 seed。轮换时持续效果携带自己的 RNG 状态跨边界。

---

## CrossCheck — 需要跨方向检查

- **CX1**: `status_advance_system` 在 02-command-validation.md §3.19 中定义为 combat→status_advance→(regen/decay并行)→death_cleanup，但 01-tick-protocol.md §3.4 的 ECS `.chain()` 代码中未出现此 system。→ 建议 **Architect** 验证 20-system ECS chain 的完整性，确保与本节描述一致。

- **CX2**: `safe_mode`（new player 500 tick 保护）的 command rejection 语义未定义。spec 说「无法执行任何敌对操作」但未指定具体 rejection code（`SafeModeActive`？退回 `NotVisibleOrNotFound`？）→ 建议 **Security** 审查 safe_mode 的 rejection 是否与 visibility-first 原则无冲突。

- **CX3**: `player_visibility_fingerprint` 概念（见 D7）需要权威定义。此概念出现在 sandbox spec 但 scope 跨 engine/sandbox 边界。→ 建议 **Architect** 提供统一定义。

- **CX4**: `wasm_simd` 默认 true 的跨架构确定性风险（见 D9）。→ 建议 **Architect** 明确 SIMD 的确定性保证范围（跨架构？同架构？），并决定 World 模式的默认值是否需要调整。

- **CX5**: `respawn_policy = NewRoom` 与 tick 内 shuffle 的交互——重生玩家是否在重生当 tick 立即参与 COLLECT 和 shuffle？若重生在某 tick 的 COLLECT 开始之后触发（如 death_cleanup 在 Phase 2b 末尾），则新 player 不在该 tick 的 active_players 集中——此语义需要明确。→ 建议 **Architect** 指定 respawn 时序与 COLLECT 的关系。

- **CX6**: `host_path_find` 的 per-player per-tick 上限在 04-wasm-sandbox.md §6 为 10 次，§8 也为 10 次。但 engine.md §3.4.2 容量合同为 "Pathfinding requests: max 100 per player per tick"。100 vs 10 的差异是否暗示 engine 层面有 path_find batching/bulk API 与 WASM 单次调用的不同？→ 建议 **Architect** 统一此数据。

---

## Formal State Issues Summary

| Issue | Severity | Category |
|-------|----------|----------|
| D1 — Sort key contradiction (§3.1/§2.1/§9.1) | Critical | Replay Integrity |
| D2 — RNG seed concatenation delimiter undefined | High | Cross-node Consistency |
| D3 — active_players pre-shuffle order unspecified | Medium | Replay Integrity |
| D4 — Truncation distance reference point ambiguous | Medium | Serialization Determinism |
| D5 — Bevy archetype iteration cross-build stability | Medium | Cross-node Consistency |
| D6 — Recycle formula uses float notation vs f64 ban | Medium | Formal State |
| D7 — player_visibility_fingerprint undefined | Medium | Serialization Determinism |
| D8 — Overload pre-clamp value semantics ambiguous | Low | Formal State |
| D9 — SIMD cross-CPU determinism risk | Low | Cross-node Consistency |
| D10 — Seed rotation in-flight RNG state migration | Low | Replay Integrity |

---

## Replay Gaps

1. **Wasmtime 版本变更时 replay 依赖 Command[] 而非 WASM 重执行**（§6.3.3）— 正确设计，但未说明 cross-version TickTrace 格式兼容策略（若 Command schema 变更，旧 trace 如何解析？）
2. **Keyframe 间隔 K=100 tick**（§3.4.7）— replay 需要从最近 keyframe 开始 + 回放 delta chain。若 keyframe 因容量被 GC，该 tick 范围的 replay 即失能。未定义「最小保证 replay 窗口」对应的 keyframe 保留策略。
3. **TickTrace delta chain 损坏检测依赖 Blake3 链**（§9.4）— 正确，但恢复策略「从最近 keyframe 重放到损坏前」需要 keyframe 恰好落在损坏区间之前。大面积损坏（如存储介质故障）可能导致整个 epoch 不可回放——需在运维文档中定义此场景。

---

## End of Review
All findings are based exclusively on the specified document subset. No cross-contamination from /data/swarm/ or reviews/ directories.
