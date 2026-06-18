# R23 Architecture Review — DeepSeek V4 Pro (Architect)

**Reviewer**: rev-dsv4-architect (DeepSeek V4 Pro)
**Date**: 2026-06-19
**Documents Reviewed**: 9 files (design/README.md, design/engine.md, design/tech-choices.md, specs/reference/api-registry.md, specs/core/01-tick-protocol.md, specs/core/02-command-validation.md, specs/core/04-wasm-sandbox.md, specs/core/05-persistence-contract.md, specs/core/06-phase2b-system-manifest.md)

---

## Verdict: CONDITIONAL_APPROVE

The architecture is fundamentally sound — strong deterministic foundations, clean ECS scheduling with explicit parallel safety proofs, well-designed persistence contract with replay-critical subset separation. However, **1 Critical cross-document inconsistency** in the system execution order + **2 High findings** around per-player drone cap semantics and Phase 2a inline deduction/FDB-rollback consistency must be resolved before implementation. All findings are fixable through targeted document updates without architectural redesign.

---

## Findings

### Critical

**D1 — Cross-Document System Execution Order Conflict (02-command-validation §3.19 vs 06-phase2b-system-manifest §1)**

02-command-validation §3.19 "`status_advance_system` 调度" (line 514-527) explicitly states:

```
death_mark → spawn → spawning_grace → combat → status_advance → (regeneration, decay 并行) → death_cleanup
```

06-phase2b-system-manifest §1 "System Schedule" (line 19-65) defines the authoritative order as:

```
death_marker → spawn → spawning_grace → regeneration → combat (parallel A) → special_attack_reducer → damage_application → status effects (parallel B) → aging → decay → death_cleanup → ...
```

Three concrete conflicts:
1. **`status_advance` position**: 02 puts it *between* combat and regeneration; 06 puts it *after* damage_application (S22 in Parallel Set B, S16-S22 position)
2. **`regeneration` position**: 02 puts it *after* combat+status_advance, in parallel with decay; 06 puts it *before* combat (S10, with explicit R16 B2 fix rationale: "regeneration 移至 damage_application 之前，防止 heal+regen 双倍回复")
3. **`decay` concurrency**: 02 claims decay runs parallel with regeneration; 06 has decay as serial (S24), after aging (S23), with no parallel partner

The 06-system-manifest claims to be "the sole authoritative definition" (§1 原则: "所有其他文档引用此处，不得重新声明可冲突的系统列表或顺序") and documents the R16 B2 fix rationale for moving regeneration before combat. But 02-command-validation §3.19 has NOT been updated to reflect this. Any implementer reading 02 §3.19 would build a different execution order than the manifest requires.

**Impact**: Different subsystems implemented from different documents would produce diverging tick execution — breaking determinism. The "status_advance before regeneration" ordering in 02 would cause status effects (Hack stage increment, Fortify shield decay) to run before regen heals, producing different HP outcomes than the manifest order where regen heals first.

**Fix**: Update 02-command-validation §3.19 to match 06-system-manifest, or (if 06 needs correction) update 06 §1 and move the status_advance placement. Add a CI cross-reference checker that validates system ordering across all documents.

---

### High

**D2 — Per-Player Drone Cap Conflict with Controller RCL Room Limits (engine.md §3.1 vs §3.4.2 vs api-registry §5.1)**

Three documents define contradictory drone capacity semantics:

| Source | Cap Value | Scope |
|--------|-----------|-------|
| engine.md §3.4.2 | 50 | "Per-player drone cap" (global, world.toml configurable) |
| api-registry.md §5.1 | 50 | "Per-player drone cap" — same value |
| 02-command-validation §6 | 50 | "MAX_DRONES_PER_PLAYER" (ambiguous scope) |
| engine.md §3.1 Controller RCL Table | 50–500 | Per-room, per RCL level |

If `MAX_DRONES_PER_PLAYER = 50` is a global cap across ALL rooms, then the Controller RCL table showing RCL 8 = 500 max room drones is nonsensical — you can never reach 500 in one room because you can only have 50 drones total.

Two possible resolutions:
- **Resolution A**: `MAX_DRONES_PER_PLAYER = 50` is a *per-room* cap, and the RCL table shows the *total room capacity* (shared by all players in that room). But then the name "per-player" is misleading.
- **Resolution B**: `MAX_DRONES_PER_PLAYER = 50` is a global cap, and the RCL table columns are mislabeled — they should be "max drones per player in room" at each RCL level, not "max room drones."

The Controller section (engine.md §3.1) uses the term "最大房间 drone" which in Chinese reads as "maximum room drones" (room-level total, not per-player). But the capacity contract (§3.4.2) explicitly says "Per-player drone cap." These cannot both be correct simultaneously.

**Impact**: Implementers will hardcode conflicting limits. Game balancers will design around wrong numbers. Players will hit unexpected caps.

**D3 — Phase 2a Inline body_cost Deduction + FDB Rollback Consistency Gap (02-command-validation §3.8, 01-tick-protocol §3.5)**

02-command-validation §3.8 specifies that Spawn `body_cost` is *immediately deducted* in Phase 2a spawn_validator (inline apply, before the FDB transaction):

> "body_cost 在 Phase 2a spawn 命令校验时立即扣除（inline apply）"

01-tick-protocol §3.5 defines FDB rollback: "world.restore(snapshot)" — restoring Bevy World to pre-Phase-2a state. The Bevy World snapshot scope (§3.5) includes "Structure (建筑): Spawn, Extension, Controller, Tower, Storage" as Component categories.

The concern: The spawn.energy is nested within the Structure/Spawn component. The snapshot restoration mechanism relies on Bevy World deep-copy semantics. If spawn.energy is stored as a `u32` field within a `Spawn` component, and the snapshot is a complete Bevy World clone, restoration should work. But:

1. The snapshot scope table lists "Structure (建筑)" as a category without enumerating all sub-fields — is `spawn.energy` explicitly in the snapshot? 
2. The crash recovery table in 01 §9.4 acknowledges body_cost deduction and says "全额退还" — but only for the crash scenario, not the normal FDB commit failure path
3. If spawn.energy is stored in a Resource rather than a Component, the Resource type table in 01 §3.5 may not explicitly cover it

**Impact**: If body_cost is deducted inline but snapshot restoration doesn't cover spawn.energy, the player loses resources on every FDB commit failure — a resource leak that accumulates over time. In the worst case, an attacker could induce FDB contention to drain opponent spawn energy.

**Fix**: Either (a) move body_cost deduction to Phase 2b spawn_system (inside the FDB transaction), or (b) add explicit verification that spawn.energy is captured in the Bevy World snapshot and restored on rollback, with a CI test that verifies spawn.energy restoration after simulated FDB commit failures.

---

### Medium

**D4 — Shuffle Seed Derivation Formula Inconsistency (01-tick-protocol §3.1 vs §9.1)**

Two different seed derivation formulas appear in the same document:

- §3.1 line 244: `let seed = blake3::hash(&[&tick_number.to_le_bytes(), &world_seed]);`
- §9.1 line 750: `Blake3("shuffle" || world_seed || tick.to_le_bytes())`

These are semantically different:
- §3.1: Hashes `tick_number || world_seed` (tick first, no domain separation)
- §9.1: Hashes `"shuffle" || world_seed || tick` (domain-separated, world_seed first)

Different formulas → different shuffle orders → different command execution order → different world state → determinism broken between implementations that pick different sections.

The §9.1 formula with domain separation ("shuffle") is the correct one (enables independent RNG streams per namespace as defined in §9.5). §3.1 should be updated to match.

**D5 — Phase 2b Inline Execution and RoomCap Read Consistency (06-system-manifest §4)**

The R/W matrix (§4) shows S06 `spawn_validator` reads `RoomCap` in Phase 2a (inline). The RoomCap is then written by S07 `death_marker` in Phase 2b. This is correct sequencing (Phase 2a runs before Phase 2b). But the RoomCap protection rule in §3 states:

> "S07 `death_marker` 释放槽位 → S08 `spawn_system` 消费槽位。此区间内 RoomCap 处于中间态——其他 system 不得读取 RoomCap 做准入决策。"

This rule only protects the S07→S08 interval, but S06's Phase 2a RoomCap read happens BEFORE S07. The question is: when S06 reads RoomCap to validate "room has capacity," is it reading the pre-tick value (which doesn't include deaths from this tick) or the post-death value (which does)?

Since S06 runs in Phase 2a before S07 death_marker runs in Phase 2b, S06 reads the pre-death RoomCap. This means: if a drone dies in the current tick, its room slot won't be available for spawning until the NEXT tick. This may be intentional (one tick delay for slot recycling) but isn't explicitly documented. The engine.md §3.2 text says "spawn_system 在 death_mark 之后（room cap 槽位已释放）运行" implying same-tick reuse. But this only works because S08 runs after S07 in Phase 2b — S06's Phase 2a validation can't see the S07 release.

The document should clarify: "Phase 2a spawn_validator validates against pre-death RoomCap; same-tick spawn reuses slots freed by S07 death_marker in Phase 2b, effectively allowing respawn within the same tick despite Phase 2a validation seeing pre-death capacity."

**D6 — Worker Pool Size Semantics (engine.md §3.4.2)**

The worker pool formula: `worker_pool_size = min(worker_pool_max, active_players)` produces 256 workers for 500 active players. The text says "每个 worker 处理约 2 个玩家" — but this means 244 players (500-256) are queued waiting for worker availability, not actively executing.

The per-player sandbox deadline is 2500ms, but with queuing, a player's effective execution window is: `2500ms / ceil(500/256) ≈ 1250ms` per batch. The timing analysis (500 players × 5ms avg = 2500ms) assumes all players execute in parallel, which contradicts the worker pool model where only 256 can execute concurrently.

The arithmetic is salvageable (256 workers × ~2 players each = 512 player-executions, each averaging 5ms ≈ 2560ms wall time, close to the 2500ms budget), but the document should make the batching model explicit rather than implying full parallelism.

---

### Low

**D7 — Arena COLLECT Timeout Not Specified (01-tick-protocol §2.2 vs engine.md §3.4.1)**

engine.md §3.4.1 specifies Arena COLLECT budget = 200ms. But 01-tick-protocol §2.2 hardcodes `collect_timeout_ms = 2500` without an Arena override. The unified budget table in 01 §8.2 shows COLLECT wall-clock per player = 2500ms with no Arena column. An Arena implementer reading only 01-tick-protocol would use 2500ms for Arena, breaking the 300ms tick budget.

**D8 — Dragonfly Staleness Bound Rationale (engine.md §3.4.7 vs 01-tick-protocol §4.2)**

engine.md states Dragonfly allows "≤2 tick lag" but 01 §4.2 implies BROADCAST writes synchronously to Dragonfly. If writes are synchronous every tick, the 2-tick staleness seems like a worst-case design tolerance that should be explained: when does it occur? (Dragonfly network blip? Worker overload?)

**D9 — TickTrace Hash Chain Dependency on Upload Status (05-persistence-contract §3)**

The tick_hash_chain is computed as `Blake3(prev_chain_hash || tick_head_hash)` at FDB commit time (Phase B). If the blob upload fails (upload_status = "failed"), the FDB commit still succeeded and the hash chain is still valid. But if blob upload succeeds with wrong content (bit flip), the `content_hash` in the manifest won't match. The hash chain remains intact (it hashes tick_head, not the blob). This is correctly designed but merits explicit documentation: "tick_hash_chain integrity is independent of blob upload status."

---

## Strengths

1. **Outstanding Deterministic Foundation**: Blake3 single-primitive strategy (hash + PRNG), seeded Fisher-Yates shuffle, fixed-point integer arithmetic, indexmap for iteration order — the determinism contract is comprehensive and implementable. The 5-layer command sorting key `(priority_class, shuffle_index, source_rank, sequence, command_hash)` is well-designed and covers all edge cases including tiebreakers.

2. **Clean ECS Scheduling Model**: The Phase 2a (inline) vs Phase 2b (deferred) split is architecturally sound. The 29-system manifest with explicit R/W matrix and parallel safety proofs is exemplary — this is how game engine scheduling should be specified. The parallel set designs (Combat A by target_id partition, Status B by disjoint component sets) are correct and efficient.

3. **Excellent Persistence Contract**: The replay-critical subset separation (10 FDB-atomic fields vs 3 debug/rich blob fields) is a mature design decision. The deploy state machine (VALIDATE → UPLOAD_PREPARE → MANIFEST_COMMIT → ACTIVATION_PENDING → ACTIVE) with `fdb_version_counter` for replay ordering is well-specified. The async blob upload model (FDB commit first, blob upload after) correctly prioritizes state integrity over audit completeness.

4. **Comprehensive Anti-Abuse Mechanisms**: Snapshot truncation with priority buckets + deterministic sort keys, per-player fair-share pathfinding budget, fuel refund caps with anti-amplification rules (50% max refund, same-reason-no-repeat, deploy-reset credit clearing), Overload anti-permanent-lockdown proof — all demonstrate thorough adversarial thinking.

5. **Single-Path Command Validation**: All commands (WASM, MCP, Admin, REST) go through the same `CommandIntent → RawCommand → ValidatedCommand` pipeline with server-side injection of auth context. No bypass paths. This is correct architecture for security.

6. **WASM Sandbox Design**: Worker pool + per-tick Store reset, pre-compilation with cache key covering wasmtime version + security epoch, WASI denylist + seccomp + cgroup v2 — the sandbox security model is thorough and implementable.

7. **Move-as-Action Design Rationale**: The documented philosophical commitment to single-action-per-tick (Move consumes the action slot) has clear deterministic reasoning (eliminates move+attack ordering ambiguity) and honestly acknowledges it may be challenged in playtesting.

---

## CrossCheck — 需跨方向检查

- **CX1**: `status_advance_system` 执行顺序在 02-command-validation §3.19 与 06-system-manifest §1 间存在冲突（见 D1）。→ 建议 **Architect (rev-claude-architect)** 裁决哪个顺序为权威，并同步更新另一文档。

- **CX2**: Shuffle seed 派生公式在 01-tick-protocol §3.1 与 §9.1 中不一致 — 前者缺少 domain separation 前缀。→ 建议 **Security (rev-dsv4-security)** 检查不同 seed 公式是否产生不同排序结果，以及是否影响 replay 可验证性。

- **CX3**: Per-player drone cap=50 与 Controller RCL 表 (每房间 50-500) 的语义矛盾需要 Game Designer 明确：cap 是 global 还是 per-room？→ 建议 **Game Designer (rev-gpt-designer)** 定义最终容量模型。

- **CX4**: Phase 2a inline body_cost 扣除在 FDB 事务边界外执行 — FDB rollback 时 spawn.energy 的恢复是否被 Bevy World snapshot 完整覆盖？→ 建议 **Security (rev-claude-security)** 检查资源安全：是否存在 body_cost 重复扣除或丢失的路径。

- **CX5**: Worker pool 256 vs 500 active players 的排队模型在 engine.md §3.4.2 中描述为"每个 worker 处理约 2 个玩家"，但 timing budget 分析假设全并行。→ 建议 **Architect (rev-claude-architect)** 验证 tick budget 在 batch-execution 模型下是否仍然成立。

- **CX6**: Dragonfly 缓存 "≤2 tick 滞后" 与 BROADCAST 同步写入语义矛盾 — 2 tick 滞后在何种场景发生？→ 建议 **Architect (rev-claude-architect)** 澄清缓存一致性合同。

---

## Summary Statistics

| Severity | Count | IDs |
|----------|-------|-----|
| Critical | 1 | D1 |
| High | 2 | D2, D3 |
| Medium | 3 | D4, D5, D6 |
| Low | 3 | D7, D8, D9 |
| CrossCheck | 6 | CX1–CX6 |
| **Total** | **9 findings + 6 cross-checks** | |
