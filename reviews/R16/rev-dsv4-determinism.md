# R16 Determinism Review — DeepSeek V4 Pro

> **审查员**: Determinism Reviewer (rev-dsv4-determinism)
> **日期**: 2026-06-18
> **审查范围**: Phase 1 Clean-Slate — 仅方向相关子集 (7 文档)
> **审查原则**: 设计阶段审查，不考虑分阶段实现。有合适方案直接采用。

---

## Verdict: CONDITIONAL_APPROVE

存在 2 个 Critical 问题必须修复（跨文档系统调度矛盾 + SIMD 确定性缺口），3 个 High 问题建议修复。修复后可升为 APPROVE。核心确定性合同（PRNG、IndexMap、禁止 f64、TickInputEnvelope）设计扎实。

---

## Findings

### Critical (2)

#### C1: Phase 2b death_mark 与 spawn 调度顺序跨文档矛盾

**位置**:
- `design/engine.md` §3.2: "spawn_system 在 death_mark 之后（room cap 槽位已释放）运行"
- `specs/core/06-phase2b-system-manifest.md` §1: 调度顺序为 S03 spawn_system → S11 death_marker

**分析**:
两个权威文档对 RoomCap 生命周期给出了互相矛盾的调度顺序。engine.md 描述的是 `death_mark: W(release) → spawn: R(check) + W(consume)`——先释放死亡 drone 的槽位，再让新 spawn 消费。System Manifest 则相反：S03 spawn 在 S11 death_mark 之前。

这直接影响世界状态确定性：
- 若按 engine.md 顺序：同 tick 内死亡的 drone 立即释放 RoomCap 槽位，同 tick spawn 可使用该槽位。同一输入下可产生更多 spawn。
- 若按 System Manifest 顺序：spawn 基于死亡前的 RoomCap 状态，死亡释放的槽位仅在下个 tick 可用。同一输入下 spawn 更少。

两个实现从相同 initial state + 相同 commands 出发，产出不同世界状态——违反确定性合同。

**Severity**: Critical

**建议修复**:
1. System Manifest 为权威源（已声明），engine.md 中相应描述需同步修正为 `spawn → death_mark`。
2. 若实际意图是 death_mark 先于 spawn（engine.md 的语义），则 System Manifest 需调序，且 RoomCap 约束说明需更新。
3. 修复后需在 `engine.md` §3.2 的遗留代码注释中明确标注"已迁移至 System Manifest，此处为历史记录"。

#### C2: World 模式默认启用 SIMD 破坏跨架构确定性

**位置**: `specs/core/04-wasm-sandbox.md` §2.2: `config.wasm_simd(world_config.simd_enabled); // SIMD 由 world.toml 控制：World 默认 true（性能），Arena 默认 false（确定性/公平）`

**分析**:
SIMD (Single Instruction Multiple Data) 指令在不同 CPU 架构上产生的结果可能不同：
- x86_64 AVX2 vs AVX-512：浮点舍入行为差异
- x86_64 vs ARM NEON：不同指令集的数值精度策略不同
- 即使同架构不同微架构：融合乘加 (FMA) 的有无影响中间精度

World 模式默认 `simd_enabled = true`，意味着：
1. 同一 tick 在同一架构不同 CPU 上回放，WASM 内部浮点计算结果可能不同。
2. 不同架构的服务器执行同一 tick，结果不一致。
3. 虽然 replay 不重新执行 WASM（走存储的 Command[]），但"初始 run"与"换架构后的 run"在 COLLECT 阶段就分叉——分叉后的 Command[] 不同，回放无从复现。

design/engine.md §7.1 明确禁止 f64 在引擎内部使用，但此禁令未覆盖 WASM 模块内部的浮点操作。SIMD 放宽了这一限制在 WASM 层的执行，形成了确定性缺口。

**注意**: 纯整数 SIMD（i8x16, i32x4 等）在 WASM 规范中是确定性的。问题出在浮点 SIMD (f32x4, f64x2) 和相关 relaxed SIMD 指令。当前 `wasm_relaxed_simd(false)` 已禁用 relaxed SIMD，但标准浮点 SIMD 仍存在架构差异。

**Severity**: Critical

**建议修复**:
1. World 模式默认 `simd_enabled = false`，与 Arena 一致。性能损失可通过以下弥补：
   - Cranelift 自动向量化标量 WASM 操作（编译时确定性）
   - 玩家侧代码优化（减少不必要的浮点运算）
2. 若确实需要 SIMD 性能，则须在 TickInputEnvelope 中新增 `simd_arch_fingerprint` 字段（记录 CPU 型号 + 微码版本），回放时校验架构匹配。
3. 在 `specs/core/04-wasm-sandbox.md` §2.2 增加"确定性风险"警告，明确浮点 SIMD 的跨架构不确定性。

### High (3)

#### H1: Phase 2a/2b 指令分类边界模糊

**位置**:
- `design/engine.md` §3.2: Phase 2a (Inline) 包含 Move, Harvest, Build, Transfer, Attack, RangedAttack, Heal, Recycle
- `specs/core/06-phase2b-system-manifest.md` §2: S01 command_executor, S06 transfer_system 出现在 Phase 2b 系统中

**分析**:
System Manifest 将 `command_executor` 和 `transfer_system` 列为 Phase 2b 的 S01 和 S06，但 engine.md 将 Transfer/Attack 等指令列为 Phase 2a inline 执行。如果 `command_executor` 是 Phase 2a 指令的批量执行器，则它实际上在 Phase 2b 调度域外运行——但 Manifest 将其列为 S01，暗示它在 Phase 2b serial spine 中。

歧义导致两种实现可能：
- 实现 A：所有 command (含 Transfer) 在 Phase 2a inline 执行，S01/S06 仅为残留占位符。
- 实现 B：Transfer/Build/Recycle 在 Phase 2b S01/S04/S05/S06 中执行，只有 Move/Attack/Harvest 在 Phase 2a inline 执行。

两种实现从相同 commands 出发产生不同的 Phase 2a→2b 中间状态（特别是 ResourceStore 变更时机），进而影响 Phase 2b 系统（如 combat、aging）的输入。

**Severity**: High

**建议修复**:
1. System Manifest 增加 §0 "Phase 2a 边界"明确声明哪些命令在 Phase 2a inline 执行（不进 manifest）。
2. 若 S01 command_executor 确实处理的是 Phase 2a 命令，则将其从 Manifest 调度中移除或标注为 "pre-Phase 2b"。
3. 若 Transfer/Build/Recycle 实际在 Phase 2b 执行（非 inline），engine.md 的分类表需更新。

#### H2: 快照截断排序键中 drone 选择规则未定义

**位置**: `specs/core/01-tick-protocol.md` §2.3

**当前定义**:
```
同一桶内按确定性排序键 (distance_to_drone, entity_id) 升序排列
```

**分析**:
当玩家拥有多个 drone 时，"distance_to_drone" 中的 `drone` 是哪个？
- 最近 drone？最近 drone？entity_id 最小的 drone？
- 不同选择产生不同的距离排序 → 不同的截断结果 → 不同的 snapshot 给 WASM → 不同的 Command[] 输出。

虽然任何一种一致选择都是确定性的，但规范未指定意味着：
1. 不同实现者可能选择不同规则。
2. 未来重构可能无意中改变规则。
3. Replay 验证时若使用不同规则，snapshot_hash 不匹配 → 回放失败。

**Severity**: High

**建议修复**:
1. 明确定义"代表性 drone"：建议使用 `entity_id` 最小的 drone（创建最早），或"所有 drone 位置的几何中心（取 floor）"。
2. 将选择规则写入确定性合同（§7.1 或 §9）。
3. 若选择"最近 drone"——需要考虑一个实体可能对 drone A 近但对 drone B 远，"最近"选择可能导致截断结果对单个 drone 的微小移动过度敏感。建议使用 `entity_id` 最小 drone。

#### H3: Dragonfly 缓存滞后窗口对 MCP query 的一致性影响未约束

**位置**:
- `design/engine.md` §3.4.2: Dragonfly "允许 ≤2 tick 滞后"
- `specs/core/01-tick-protocol.md` §9.3: MCP `swarm_get_player_status` 从 Dragonfly 读取，"滞后 ≤ 1 tick"

**分析**:
两个文档对 Dragonfly 滞后给出不同数字（≤2 tick vs ≤1 tick）。更重要的是，MCP query 路径有一部分读 Dragonfly（`swarm_get_player_status`），有一部分读 Bevy snapshot（`swarm_get_snapshot`）。

若 AI agent 在同一 tick 调用 `swarm_get_snapshot`（读本 tick 快照）和 `swarm_get_player_status`（读 Dragonfly，可能滞后 1 tick），两者看到的状态可能属于不同 tick，产生不一致的世界视图。虽然这不是引擎内部的非确定性，但会导致 AI agent 的决策基于不一致信息——间接影响"相同初始状态 + 相同外部刺激 → 相同 agent 行为"这一更广泛意义上的确定性。

**Severity**: High

**建议修复**:
1. 统一 Dragonfly 滞后窗口为 1 tick（与 01-tick-protocol.md 一致）。
2. MCP 工具文档中标注每个工具的读源（Bevy snapshot / Dragonfly / FDB）及可能的滞后。
3. 建议 `swarm_get_player_status` 在 COLLECT 阶段从 Bevy snapshot 读取（与其他 MCP query 一致），消除跨源不一致。

### Medium (3)

#### M1: 并行集 Combat Set A 写入语义欠精确

**位置**: `specs/core/06-phase2b-system-manifest.md` §2 (S07-S09)

**描述**:
``` 
Parallel safety: 三个 system 按 target_id partition，同一 entity 只被一个 system 写入。
Reduce 后由 S10 统一应用。
```

"按 target_id partition" 的具体规则未定义。partition 是基于 `target_id % 3`（确定性哈希）还是"先到先得"（非确定性）？如果是后者，并行度变化会改变哪个 system 处理哪个 target → 不同结果。

当前上下文暗示 S07-S09 写入 PendingDamage buffer 而非直接写 Entity，且 S10 reduce 时合并。若 PendingDamage 是 per-target multi-writer 结构（如 `HashMap<EntityId, Vec<DamageEvent>>`），则写入顺序不影响最终 reduce 结果（加法和最大值是交换的）。但需要明确 PendingDamage 的数据结构和 S10 的合并算法是交换结合(commutative + associative) 的。

**Severity**: Medium

**建议修复**:
1. 明确 PendingDamage 结构为 `IndexMap<EntityId, DamageAccumulator>`，其中 DamageAccumulator 使用交换运算（`total_damage += dmg; total_heal += heal`）。
2. 确认 S10 的 reduce 算法在任意写入顺序下产出相同结果。
3. 若确实有非交换操作（如"最先命中的攻击者获得 bonus"），需改为串行或明确的确定性排序。

#### M2: Phase 2b 并行集错误处理语义未定义

**位置**: `specs/core/06-phase2b-system-manifest.md` §1

**问题**: 如果 Parallel Set B 中 `hack_system` 和 `drain_system` 同时操作同一 entity 的不同 component（合法——它们操作不同 component），但其中一个 panic/OOM，另一个的状态变更如何回滚？

当前设计依赖 FDB 事务回滚（整个 tick 放弃），但在 Phase 2b Bevy World 原地修改后、FDB commit 前的窗口内，并行系统中一个 panic 可能留下部分修改的 Bevy World 状态。Pre-Apply snapshot (engine.md §3.5) 用于恢复，但如果并行系统在 snapshot 之外留下了"中间写入"（如修改了共享 Resource），snapshot restore 能恢复吗？

`engine.md` §3.5 的 Bevy World 快照范围清单覆盖了所有 Component 和 Resource 类型——如果快照是深拷贝，恢复应该是完整的。但需确认 Bevy 的 `World::snapshot()` 语义（深拷贝 vs 浅拷贝 + COW）。

**Severity**: Medium

**建议修复**:
1. 明确 Bevy World snapshot 为深拷贝（序列化/反序列化或 clone 所有 component）。
2. 在 System Manifest 中增加"错误处理"节：任何 system panic → tick 放弃 = snapshot 恢复 + FDB 不提交 + fuel 退还。并行集中一个 system panic 不影响同集其他 system 的结果（反正整个 tick 回滚）。

#### M3: RNG per-entity stream seed 缺少独立文档化

**位置**: 
- `design/engine.md` §3.3: `Blake3(stream_name || world_seed || entity_id.to_le_bytes() || tick.to_le_bytes())`
- `specs/core/01-tick-protocol.md` §9.5: RNG namespace 表

**问题**: engine.md 定义了 per-entity stream seed 公式，但 §9.5 的 RNG namespace 表只列了 4 个 namespace（combat, loot, npc_spawn, event），没有列出 per-entity streams 的 domain_sep 值。如果不同系统使用不同的 domain_sep 格式（如 `"combat"` vs `"cmbt"`），streams 隔离性取决于约定而非规范。

**Severity**: Medium

**建议修复**:
在 `01-tick-protocol.md` §9.5 或 `api-registry.md` 中增加完整的 domain_sep 字符串表，覆盖所有当前和预留的 PRNG stream。

### Low (2)

#### L1: WASM 缓存键跨文档不一致

**位置**:
- `design/engine.md` §3.2: 缓存键 `(module_hash, wasmtime_version)`
- `specs/core/04-wasm-sandbox.md` §1: 缓存键 `Blake3(module_hash || wasmtime_build_commit || wasmparser_version || validation_policy_version || target_arch || security_epoch)`

不影响运行时确定性（replay 不执行 WASM），但若部署/编译阶段缓存键不一致导致编译跳过行为不同，可能影响"同一 WASM 在相同配置下是否触发重编译"的可预测性。

**Severity**: Low

**建议修复**: engine.md 引用 sandbox spec 的完整缓存键定义。

#### L2: TickTrace WAL 紧急路径的跨节点一致性

**位置**: `specs/core/01-tick-protocol.md` §6.3.4

**问题**: 当 FDB 连续 3 次写入失败后，TickTrace 写入本地 WAL（`/var/lib/swarm/wal/ticktrace/`）。若此时 engine 进程崩溃，不同节点可能：
- 节点 A 的 WAL 有某 tick 记录，节点 B 没有。
- 从 FDB 重建时，两者对"是否有该 tick 的审计记录"结果不同。

这仅影响审计完整性（非世界状态确定性），但在分布式环境中，WAL 的本地性意味着不同节点对历史的认知可能分裂。

**Severity**: Low

**建议修复**: 在 WAL 路径增加节点标识符（`hostname` 或 `node_id`），恢复时通过 FDB 交叉验证。

---

## Strengths

1. **确定性合同清晰**：`设计原则 §1.3` 和 `specs/core/01-tick-protocol.md §9` 明确定义"相同初始状态 + 相同指令 → 相同世界状态"，为所有子系统提供统一判断标准。

2. **PRNG 完全确定性**：Blake3 XOF + 确定性种子 + namespace 隔离——无 OS 熵源依赖。所有 RNG 可完整 replay。

3. **IndexMap 取代 HashMap**：所有需要迭代顺序的容器使用 IndexMap，消除 Rust std::HashMap 的非确定性迭代。

4. **f64 显式禁止**：引擎内部所有数值使用整数/定点数，禁止浮点数。跨平台确定性有保障。

5. **TickInputEnvelope 全面**：22 个字段覆盖 WASM hash、wasmtime 版本、snapshot/commands hash、config/mod hash、ABI 版本、manifest hash——回放所需输入全部捕获。

6. **Replay 不重执行 WASM**：回放使用存储的 Command[] 而非重新调用 WASM tick()。Wasmtime 版本变更不影响历史回放。

7. **WASI 全禁**：clock、random、filesystem、network、env、process、threads 全部禁用——WASM 可访问的唯一非确定性源被彻底切断。

8. **两阶段快照架构**：O(entities + players × visible_rooms) 替代 O(players × entities)，快照在 COLLECT 开始一次性构建——所有玩家和 MCP query 看到同一一致性快照。

9. **命令排序键完整分层**：5 层排序键 `(priority_class, shuffle_index, source_rank, sequence, command_hash)`，command_hash 作为稳定 tiebreaker——完全确定性。

10. **FDB 单写事务原子性**：每 tick 单 FDB commit → 全或无。回滚时 Bevy World 快照恢复——无中间状态泄露。

11. **System Manifest R/W 矩阵**：每个 system 声明 reads/writes 的 Component/Resource 集合，CI 验证并行安全——可静态分析确定性。

12. **Snap truncation 确定性保证**：`(bucket_priority, distance_to_drone, entity_id)` 完全基于世界状态中的确定值——同输入同截断结果。

13. **Seed 轮换 + TickTrace epoch 记录**：每 10000 tick 轮换 world_seed，TickTrace 记录 seed_epoch——回放可跨种子边界。

14. **Bevy World 快照范围穷举**：所有 Resource 类型和 ECS Component 类型均在快照范围内——恢复完整性有保障。

---

## CrossCheck — 需要跨方向检查

以下事项由当前审查方向（Determinism）识别，但需其他方向审查员在各自领域深入验证：

| # | 事项 | 需检查方向 | 理由 |
|---|------|-----------|------|
| X1 | Wasmtime `=30.0` 锁定的安全支持窗口 | **Security** | CVE-SLA 依赖 Bytecode Alliance 的 LTS 策略——需 Security 审查员确认 `=30.0` 的支持窗口与 Swarm 的发布计划对齐 |
| X2 | `world_seed` 前向保密威胁模型的充分性 | **Security** | 设计接受"seed 泄露可预测所有未来 tick"——Security 需确认此风险在服主级秘密保护下可接受 |
| X3 | Phase 2b Parallel Set B 中 7 个 system 的"互不重叠 Component 集合"声明 | **Architecture** | 需 Architecture 审查员验证 hack_system/drain_system/overload_system 等确实操作互斥的 Component 类型 |
| X4 | `is_visible_to` 的一致性——snapshot 构造和 host function 过滤使用同一函数 | **Architecture / Security** | 当前文档声明此保证但未给出函数签名或证明——需确认不存在过滤器绕过路径 |
| X5 | Custom actions (Leech, Fabricate) 的 validator/handler 注册对 System Manifest 的影响 | **Architecture** | Custom actions 通过 World Action Manifest 注册，其 handler 的执行时序和并行安全性未在 Manifest 中建模 |
| X6 | Replay verifier 的 delta chain 验证完整性 | **Architecture / QA** | `chain[i] = Blake3(chain[i-1] \|\| tick_trace_i)`——需确认 keyframe + delta replay 在所有边界条件下可重建完整状态 |

---

## Summary

R16 的确定性设计在核心路径上扎实：PRNG 纯净、HashMap 全部 Eliminated、f64 禁止、TickInputEnvelope 全面、Replay 使用存储命令。**但 2 个 Critical 问题必须在 Phase 2 前解决**：

1. **C1 (death_mark ↔ spawn 排序矛盾)**: engine.md 与 System Manifest 定义了互斥的调度顺序——必须选定一个权威顺序并同步所有文档。
2. **C2 (World SIMD 确定性缺口)**: WASM SIMD 在跨架构间浮点结果不确定——World 模式不应默认开启 SIMD。

修复上述两项后，确定性设计可升为 APPROVE。
