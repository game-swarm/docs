# R24 Closure Verification — 确定性 (GPT-5.5)

Verdict: CONDITIONAL_APPROVE

## Strengths

- B3 的确定性合同已集中到 `specs/core/01-tick-protocol.md` §9：全局排序键、输出状态合同、TickTrace 完整性、RNG namespace、ECS 调度权威顺序均有明确条款。
- Replay-critical subset 已在 `specs/core/05-persistence-contract.md` §2.1 权威列出，并明确 FDB 原子提交字段，降低 TickTrace rich/debug blob 缺失导致核心回放失败的风险。
- SIMD/WASI 非确定性来源已在 `design/engine.md` §3.4.3 与 `specs/core/04-wasm-sandbox.md` §2.2/§2.3 约束：WASI clock/random/filesystem/network/env/process/threads/atomics 禁用，SIMD 默认禁用，relaxed SIMD 始终禁用。
- B4 benchmark gates 已在 persistence contract 中纳入 Phase 1 gate，给出 p99/冲突率等明确判定标准。

## Concerns

- T1: B3 仍有一个闭合缺口：特殊攻击/Disrupt 的同 tick 裁决优先级在允许文档内不一致，可能导致不同实现者按不同优先级执行，影响跨节点一致性与 replay。

## Verification Items

[B3] GAP — 部分闭合，但仍有 Disrupt/特殊攻击优先级合同冲突。

已闭合证据：
- 确定性合同：`specs/core/01-tick-protocol.md` §9.1 定义全局排序键 `sort_key = (priority_class, shuffle_index, source_rank, sequence, command_hash)`；§9.5 定义 RNG namespace 与 `Blake3(domain_sep || world_seed || tick.to_le_bytes())`；§9.6 指向 Phase2b 权威顺序。
- Replay-critical 分层：`specs/core/05-persistence-contract.md` §2.1 将 `tick/state_checksum/system_manifest_hash/world_config_hash/mods_lock_hash/commands+rejections/fuel_ledger/deploy_activation_decision/canonical_codec_version/terminal_state` 列为 FDB 原子提交不可降级字段；§7 定义 `collect_id/attempt_id/commit_id` 与 commit retry 时复用 canonical COLLECT buffer。
- SIMD/WASM 非确定性约束：`design/engine.md` §3.4.3 禁用 clock/random/filesystem/network/env/process/threads/atomics，SIMD 默认禁用且仅允许 opt-in deterministic integer subset；`specs/core/04-wasm-sandbox.md` §2.2 明确 `wasm_threads(false)`, `wasm_simd(world_config.simd_enabled)`, `wasm_relaxed_simd(false)`；§2.3 明确 WASI clock/random 等禁用。
- D5/A 持久化方向：`specs/core/05-persistence-contract.md` §2.1/§2.2 明确 replay-critical 与 debug/rich 分离，§3 Phase B/FDB commit 先于 Phase C/object-store async upload，§3 关键不变量声明 FDB commit 成功即 tick 持久化完成，blob 缺失只影响 rich audit/replay gap。
- Disrupt D3/A 的局部闭合证据：`specs/core/06-phase2b-system-manifest.md` §S16-S22 表中 `disrupt_system` 明确 “body part match req (R23 D3/A)”；§Special Attack Unique Writer Contract 声明各 Status Component 只有 `status_adv` 写入，S14 canonical merge sort 后交付 S22。

缺口：
- `specs/core/02-command-validation.md` §3.16 “同 tick 多命中优先级”声明 Disrupt 优先级最高：`Disrupt → Fortify → Debilitate → Hack → Drain/Leech → Overload → Fabricate`，理由是打断效果必须先于持续性效果。
- 但 `specs/core/06-phase2b-system-manifest.md` §S14 的 Reducer resolve 步骤声明优先级链为 `Hack > Drain > Overload > Debilitate > Disrupt > Fortify`。
- 由于 `06-phase2b-system-manifest.md` 自称为 tick 系统执行顺序唯一权威，而 `02-command-validation.md` 给出相反的同 tick 多命中语义，B3 中 “Disrupt D3/A + 确定性合同” 未完全闭合。需要将特殊攻击优先级统一到一个权威顺序，并同步另一文档引用。

[B4] CLOSED — benchmark gates 已正确闭合。

证据：
- `specs/core/05-persistence-contract.md` §8.3 “Synthetic Benchmark 要求”列出 Phase 实现必须交付的 gates：
  - Command validate loop: 100k commands/tick, p99 < 50ms
  - Command apply loop: 100k commands/tick, p99 < 100ms
  - Entity snapshot clone: 50k entities, p99 < 20ms
  - Entity snapshot restore: 50k entities, p99 < 30ms
  - Snapshot stitching: 1000 × 256KB snapshots, p99 < 100ms
  - FDB single-tx commit: 500 active players, p99 < 200ms, conflict rate < 1%
  - FDB room-partition commit: 1000 active players, 200 rooms, p99 < 500ms, per-room conflict rate < 1%
  - Pathfinding: 50×50 A* nodes, 100 concurrent ops, p99 < 10ms/node, fair-share guarantee
  - Rollback Bevy snapshot/restore: 500 entities, all components, p99 < 50ms, entity ID allocator verified
- 同节明确 “Gate 失败 → 对应容量声明不可信，需降级规模或优化实现”，满足 benchmark gate 的判定后果要求。

## State Machine Gaps

- B3 的剩余 gap 仅限特殊攻击 reducer / Disrupt 同 tick 优先级：一个文档要求 Disrupt 先打断，另一个权威 manifest 的 reducer 优先级将 Disrupt 放在 Hack/Drain/Overload/Debilitate 之后。该冲突会影响状态推进路径是否唯一。
- Deploy 状态机、commit retry 状态、terminal_state 分类、Tick 生命周期在本轮允许文档中已有明确状态与转移定义，本方向未发现需纳入 R24 CV 的其他未闭合项。

## Non-Determinism Sources

- RNG: 已约束为 Blake3 XOF + namespace/domain separation；未发现 OS entropy 入口保留在 WASM 路径。
- 时间: WASI clock 与 sandbox `clock_gettime` 在生产边界中被禁止；tick 时间参数由引擎资源配置控制。
- Hash/迭代: `specs/core/01-tick-protocol.md` §7.1 禁用 `std::hash`，要求 `indexmap`，manifest §原则要求系统内按 `StableEntityId` 或 canonical key 排序。
- 浮点: `specs/core/01-tick-protocol.md` §7.1/§9.8 与 `design/engine.md` §3.4.8 要求整数/定点数，禁用 `f64`。
- SIMD: 默认禁用且 relaxed SIMD 始终禁用；opt-in deterministic subset 仍需跨架构验证，当前作为 B3 已有合同但实现阶段需保留 CI 证明。
