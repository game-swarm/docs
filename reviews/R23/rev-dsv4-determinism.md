# R23 确定性评审 — DeepSeek V4 Pro

> Phase 1 Clean-Slate 独立评审 | 方向: Determinism
> 评审员: rev-dsv4-determinism (DeepSeek V4 Pro)
> 仅读取方向相关子集: design/README.md, design/engine.md, specs/reference/api-registry.md, specs/core/01-06

---

## 1. Verdict

**CONDITIONAL_APPROVE**

设计在确定性方面整体扎实——f64 全面替换为定点整数、ECS 调度权威化、PRNG 确定性派生、IndexMap 替代 HashMap、快照一次性构建——这些是正确的工程决策。但存在 **1 个 Critical 问题**（WASM SIMD 默认启用破坏确定性）和 **3 个 High 问题**（种子前向泄漏、快照 entity_id 排序保证、寻路缓存可见性指纹）需修复或明确化后方可进入实现。

---

## 2. 发现的问题

### Critical

#### D1: WASM SIMD 在 World 模式默认启用 — 架构级非确定性

**文件**: `specs/core/04-wasm-sandbox.md` §2.2

```rust
config.wasm_simd(world_config.simd_enabled);  // World 默认 true（性能），Arena 默认 false（确定性/公平）
```

**问题**: World 模式下 WASM SIMD 默认启用。WASM SIMD 指令（即使限于整数）在不同 CPU 架构（x86_64 AVX2 vs ARM NEON vs x86_64 SSE4.2）上可能产生不同的浮点中间结果和舍入行为。即使引擎自身使用纯整数定点运算，玩家 WASM 代码（编译自 C/Rust/AssemblyScript）可能：

- 使用 `f32x4` 等浮点 SIMD 类型
- 在 SIMD 路径中引入架构依赖的近似指令（如 `f32x4.sqrt` 在不同硬件上的最后一位差异）
- 跨 x86/ARM 重放产生不同的 WASM 执行结果

**与确定性的直接冲突**: engine.md §3.3 明确声明 "所有随机数来自确定种子 PRNG"，SIMD 在此合同之外。若 World 模式允许 SIMD，则 `execute_deterministic(state, commands) == recorded_state` 合同在同一架构内勉强成立（Wasmtime 同版本），但跨架构回放**不保证**。

**严重性论证**: World 是 Swarm 的主要游戏模式。若 World 默认允许非确定性 SIMD，则：
- 跨架构 CI 重放验证无法通过（x86 CI vs ARM 开发机）
- 玩家在不同 CPU 上得到不同的 fuel 消耗和游戏结果
- 反作弊审计无法在异构硬件上复现

**建议**: 两种方案：

A.（推荐）World 模式也默认禁用 SIMD (`wasm_simd(false)`)，仅在 `world.toml` 中显式声明 `[wasm] simd = "deterministic_subset"` 时启用受限制的整数 SIMD 子集，且该子集需跨架构验证
B. 保留当前默认，但在 `TickInputEnvelope` 中记录 `simd_arch` 和 `simd_enabled` 标志，回放时要求相同架构

---

### High

#### D2: 世界种子前向可推导 — 泄露后所有未来 tick 可预测

**文件**: `specs/core/01-tick-protocol.md` §3.1

```
轮换算法: new_seed = Blake3(old_seed || current_tick)
```

**问题**: 种子轮换使用单向函数从旧种子推导新种子。若 `world_seed` 在 tick N 泄露，攻击者可计算 tick N+1, N+2, ... 的**所有未来种子**。文档 §3.1 "前向保密威胁模型" 已承认此风险并评级为 🔴 Critical——攻击者可以：

- 精确预知自己在每个 tick 的 shuffle 位置
- 预演所有未来 tick 的随机结果（combat 伤害浮动、spawn 位置、资源再生等）
- 计算最优剥削策略

**当前缓解**: 定期轮换（每 10000 tick）+ 服主手动 bump epoch。依赖 `world_seed` 与 TLS 私钥同级保护的安全假设。

**确定性与前向保密的矛盾**: 文档正确识别了此矛盾——"完善前向保密需要定期从外部熵源注入——与确定性回放要求冲突"。**此风险已被设计接受**，但需在评审中明确记录。

**建议**: 
- 此为已接受的已知风险，不作为 blocking issue
- 建议运维 runbook 中增加 seed 泄露检测（已在文档中）和定期审计
- 考虑将 seed 轮换间隔从 10000 降低到 1000（减少泄露窗口），代价是每 1000 tick 更新一次 TickTrace 中的 seed_epoch

---

#### D3: 快照截断排序依赖 entity_id — 跨 tick entity_id 分配顺序不确定性

**文件**: `specs/core/01-tick-protocol.md` §2.3

```
同一桶内按确定性排序键 (distance_to_drone, entity_id) 升序排列
```

**问题**: 快照截断的 sort key 使用 `entity_id` 作为 tiebreaker。此排序的确定性依赖于：同一 tick、同一世界状态下，visible entities 的 entity_id 集**完全相同**。

由于快照在 Phase 2a 之前构建（Bevy World 深拷贝），entity_id 集由 tick N-1 的最终状态决定。只要 tick N-1 是确定性的，tick N 的快照截断就是确定性的——**当前设计满足此条件**。

但存在一个边缘情况：若 FDB commit 失败并回滚后重试，Phase 2b spawn_system 可能在不同的 attempt 中分配不同的 entity_id（取决于 Bevy 内部的 entity ID 计数器恢复机制）。文档 §3.5 声明 `world.restore(snapshot)` 恢复所有 Component + Resource——但 Bevy 的 entity ID allocator 是否也被恢复到快照时的状态？

若 entity ID allocator 未被精确恢复，则：
- 同一 tick 的不同 attempt 可能产生不同的 entity_id
- 虽然 attempt 失败不持久化，但若 spawn 发生在 attempt 1 中且 entity_id 已被分配，attempt 2 的快照恢复后 entity_id 可能不同
- 快照截断的排序结果会在不同 attempt 间变化

**当前保护**: S25 `death_cleanup` 按 `entity_id` 降序 despawn 防止 ID 复用——这意味着 entity_id 是单调递增的，恢复后可能不回到原始计数器值。

**建议**: 
- 确认 `Bevy World snapshot/restore` 的语义包含 entity ID allocator 状态
- 或在 `world.restore()` 实现中显式恢复 `Entities` resource
- 或在 FDB 故障注入 CI 测试（已存在）中额外验证 entity_id 分配器的确定性

---

#### D4: Pathfinding 缓存键 `player_visibility_fingerprint` 的确定性未定义

**文件**: `specs/core/04-wasm-sandbox.md` §8

```
host_path_find 缓存键: (from, to, terrain_hash, player_visibility_fingerprint)
```

**问题**: `player_visibility_fingerprint` 在文档中未定义。该值必须由完全确定性的输入构成（玩家位置、fog_of_war 状态、observer 范围等）。若包含任何非确定性成分（如上次可见性计算的时序、并行 worker 的计算顺序），则缓存命中结果在不同 run 间不一致。

**当前文档未定义**:
- `player_visibility_fingerprint` 的构成公式
- 是否与 snapshot hash 一致（snapshot 已包含可见性过滤结果）
- 若与 snapshot hash 一致，为何不直接使用 `snapshot_hash` 作为缓存键的一部分？

**建议**: 
- 明确定义 `player_visibility_fingerprint` = `Blake3(fog_of_war_state || drone_positions || observer_range)`
- 或直接使用 snapshot 的 `Blake3(filtered_visible_entities)` 作为子键
- 在 04-wasm-sandbox.md §8 中补充公式定义

---

### Medium

#### D5: Parallel Combat Set A 的事件/指标排序非确定性

**文件**: `specs/core/06-phase2b-system-manifest.md` §2 (S11-S13)

```
Parallel Set A: Combat (S11-S13) — 按 target_id partition 并行
```

**问题**: 三个 combat system (attack/ranged_attack/heal) 按 `target_id` partition 并行执行。虽然写入安全性通过 partition 保证（同一 target 只被一个 system 写入），但以下顺序可能非确定：

- **EventLog 写入顺序**: 若 S11 和 S12 同时写入不同的 EventLog entry，并行执行可能导致 entry 顺序在不同 run 间变化
- **Metrics 累加**: 若 combat metrics 使用原子累加，顺序可能影响浮点累加结果（但引擎使用整数，此风险较低）
- **status_advance_system intent buffer**: S11-S13 产生的 special attack intents 写入 per-system sub-buffer，然后由 S14 merge sort——文档声明 "禁止依赖 nondeterministic push order"。需确认各 sub-buffer 内部在 push 时是否已排序

**当前保护**: S14 的 merge sort 按 `(priority_class, intent_source.entity_id, intent_target.entity_id)` 确定性归并——只要各 sub-buffer 内部元素在 merge 前已按此键排序，结果就是确定的。

**建议**: 
- 在 S14 §2 中明确声明 "每个 per-system sub-buffer 在 merge 前必须按 `(intent_source.entity_id, intent_target.entity_id)` 排序"
- CI 中加入并行执行下的 EventLog 顺序一致性测试

---

#### D6: Recycle refund 公式除法的舍入边界

**文件**: `specs/core/02-command-validation.md` §3.18

```
refund_pct = max(0.1, 0.5 × (remaining_lifespan / total_lifespan))
```

**问题**: 公式使用浮点数表示 `0.1` 和 `0.5`，但引擎禁止 f64。需要明确此公式在整数实现中的精确表达：

```
refund_rate_bp = max(1000, (remaining_lifespan * 5000) / total_lifespan)  // basis points
refund_amount = (refund_rate_bp * body_cost) / 10000
```

api-registry.md §10.3 已给出整数版公式（`max(1000, (remaining_lifespan * 5000) / total_lifespan)`），与 §3.18 的文字描述一致。但两个文档间存在表述差异（§3.18 用浮点伪代码，§10.3 用整数精确公式）。建议统一为整数表述。

**影响**: 低——若实现按 api-registry.md 的精确公式，舍入行为已确定（floor）。仅文档一致性问题。

---

### Low

#### D7: Controller repair 单个 drone 时 global_cap = 0

**文件**: `design/engine.md` §3.4.5

```
global_cap = floor(active_drones × 0.5)
```

**问题**: 当 `active_drones = 1` 时，`global_cap = floor(0.5) = 0`，意味单个 drone 无法获得任何 Controller repair。此行为虽然确定，但可能违背直觉（单个 drone 应该可以被维修）。

**影响**: 极低——边缘情况，且世界启动时 `active_drones` 可能为 0 或 ≥2。但值得在 gameplay 测试中验证。

---

## 3. 亮点 (Strengths)

1. **f64 全面消除** (api-registry.md §0): 所有浮点替换为 `BasisPoints`(u32)、`ResourceRate_i64`(i64)、`MilliUnits`(i64) 等定点类型。`IndexMap` 替代 `HashMap` 保证迭代顺序。这是 Swarm 确定性设计的基石决策，执行彻底。

2. **ECS 调度权威化** (06-phase2b-system-manifest.md): 29 systems 全部定义 `system_id` + `version`，组成 `manifest_hash` 进入 TickTrace。Component R/W 矩阵覆盖全部并行 set，包含 RoomCap 中间态保护和 parallel safety 证明。

3. **快照一次性构建** (engine.md §3.2): 两阶段快照架构——COLLECT 开始时一次性深拷贝 Bevy World → 按房间分片 → 按玩家拼接可见分片。复杂度从 `O(P×E)` 降为 `O(E + P×R)`，且构建在 WASM 执行前完成，天然确定。

4. **FDB 事务原子性 + 重试隔离** (01-tick-protocol.md §3.5): FDB commit 失败 → Bevy snapshot 恢复 → 复用 canonical COLLECT buffer → 不重新执行 WASM。`collect_id`/`attempt_id`/`commit_id` 三级标识追踪每次 attempt。

5. **Deferred Command Model** (04-wasm-sandbox.md §3): WASM 仅输出 JSON 指令，所有状态变更由引擎在校验后统一应用。无 direct mutating host function——杜绝 WASM 绕过校验的非确定性路径。

6. **确定性排序键** (01-tick-protocol.md §9.1): 五层 `(priority_class, shuffle_index, source_rank, sequence, command_hash)` 全局排序键，`command_hash = Blake3(command_json)` 作为最终 tiebreaker——完全消除排序歧义。

7. **Replay-critical subset 分离** (05-persistence-contract.md §2): FDB 原子提交 10 项 replay-critical 字段，对象存储 blob 异步写入可降级。Blob 缺失不影响 deterministic replay——仅降级 rich audit。

8. **Special Attack Unique Writer Contract** (06-phase2b-system-manifest.md): 每种 status component 有且仅有一个写入者 system (`status_advance` S22)，杜绝多路径写同一状态的并发非确定性。

---

## 4. CrossCheck — 需要跨方向检查

以下问题超出确定性方向的直接范围，但怀疑存在风险，建议对应方向的评审员关注：

- **CX1**: SIMD 在 World 模式默认启用可能违反安全沙箱假设 → 建议 **Security (rev-dsv4-security)** 检查：WASM SIMD 指令是否可能绕过 fuel metering？是否存在 SIMD 侧信道（如 SIMD register 状态跨 tick 泄漏）？

- **CX2**: 种子前向可推导性（D2）的威胁模型接受度 → 建议 **Security** 检查：当前缓解（定期轮换 + 服主 bump）对竞技公平性的保护是否充分？是否需要将 seed 轮换间隔降低到更小的窗口？

- **CX3**: 快照 entity_id 排序依赖（D3）的 Bevy snapshot 恢复完整性 → 建议 **Architect (rev-claude-architect)** 检查：`Bevy World::snapshot()` / `restore()` 的实现范围——是否覆盖 entity ID allocator？CI 故障注入测试是否覆盖此路径？

- **CX4**: Pathfinding 缓存键的 `player_visibility_fingerprint` 定义缺失（D4） → 建议 **Architect** 检查：需要在 04-wasm-sandbox.md §8 中补充确定性公式定义。

- **CX5**: Parallel Combat Set A 的 EventLog 排序 → 建议 **Architect** 检查：并行 system 写入的 EventLog 是否需要 canonical sort？是否影响 TickTrace 的确定性审计？

- **CX6**: f64 消除的完整性 → 建议 **Architect** 检查：引擎中是否存在未被 api-registry.md 覆盖的、使用 f64 的内部计算路径（如 pathfinding 启发式、combat damage 抗性乘法、economy tax 累加）？

