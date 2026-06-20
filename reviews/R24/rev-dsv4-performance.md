# R24 Performance Review — rev-dsv4-performance

**Verdict: CONDITIONAL_APPROVE** (3 Critical findings, 3 High, 2 Medium)

---

## Strengths

1. **Tick budget decomposition is well-structured**: The 3000ms tick pipe (SNAPSHOT→COLLECT→EXECUTE→COMMIT→BROADCAST) has clear per-phase budgets with p99 targets.
2. **Snapshot architecture optimization**: Two-phase snapshot (build once, stitch per-player) eliminates O(P×E) serialization and is well-documented across engine.md and tick-protocol.md.
3. **Worker pool capacity derivation**: The 500/1000 player derivation with explicit assumptions (p50=5ms, p99=15ms, core count, MIPS) is transparent and reviewable.
4. **FDB async blob strategy (D5/B)**: Decoupling FDB commit from object-store blob write is the correct performance decision.
5. **Fair-share admission model**: Per-player quotas for pathfinding and host calls with clear exhaustion behavior.
6. **Aggregate CPU admission formula** (§3.4.2 engine.md) correctly models multi-core WASM parallelism.

---

## Concerns

### C1 — Per-player Drone Cap: IDL=500 vs Design/Registry=50 (Critical)

| Location | Value |
|----------|-------|
| `specs/reference/game_api.idl.yaml` §limits.game_limits (line 1527) | `per_player_drone_cap: 500` |
| `design/engine.md` §3.4.2 容量合同 | `Per-player drone cap: 50` |
| `specs/reference/api-registry.md` §5.1 (line 469) | `Per-player drone cap: 50` |

The IDL declares the per-player drone cap as **500**, but both engine.md and api-registry.md declare it as **50** (with "R23 D2/B 三层 cap" annotation). This 10× discrepancy directly impacts:

- **Tick execution budget**: 500 drones/player × 100 max commands/tick creates a much larger command processing load than 50 drones/player
- **Snapshot size**: 500 drones in visible range would reliably trigger 256KB truncation for all nearby players
- **Pathfinding**: 500 drones doing pathfinding (10/tick cap) could saturate the 100,000 nodes global budget with just 20 players at 500 drones each (20 × 10 calls × 500 nodes = 100,000)
- **Worker pool sizing**: The 256-worker default assumes 50-drones-per-player workload

**Recommendation**: Resolve to 50 (the design/registry value). The 500 in IDL appears to be the **per-room** drone cap (which is correctly 500 in the RCL table), not per-player. Update IDL to `per_player_drone_cap: 50` with the three-layer annotation.

---

### C2 — Snapshot Build Budget: 50ms p99 (engine.md) vs 200ms p95 (snapshot-contract) (Critical)

| Location | Value | Percentile |
|----------|-------|------------|
| `design/engine.md` §3.4.1 Tick Pipeline 预算 | SNAPSHOT build ≤50ms | p99 |
| `specs/core/09-snapshot-contract.md` §7.1 Capacity SLO | Snapshot build time < 200ms | p95 |
| `specs/core/09-snapshot-contract.md` §7.1 Hard Budget | Snapshot build time < 500ms | (rejection threshold) |

The engine.md declares a **hard contract** of ≤50ms p99 for snapshot building. The snapshot-contract declares an **SLO** of <200ms p95 with a hard budget of 500ms. The engine contract is 4× tighter at a stricter percentile:

- 50ms p99 is extremely aggressive for 50,000 entities serialized + room-sharded
- The persistence-contract benchmark gate (§8.3) requires "Entity snapshot clone: 50k entities, p99 < 20ms" and "Snapshot stitching: 1000 × 256KB snapshots, p99 < 100ms" — these together approach but don't fully validate the 50ms p99 claim
- At 50ms p99 snapshot build, only 50ms remains for the entire COLLECT overhead (dispatch, stitching, result collection) before WASM execution begins

**Recommendation**: Align on the snapshot-contract values as the authoritative contract. The engine.md's 50ms p99 is an implementation aspiration, not a cross-document contract. Or, if 50ms p99 is the real target, the snapshot-contract must be updated — but the benchmark gates don't support this ambition at 50k entities.

---

### C3 — EXECUTE Budget: 400ms (engine.md) vs 500ms (tick-protocol.md) (Critical)

| Location | Value |
|----------|-------|
| `design/engine.md` §3.4.1 Tick Pipeline 预算 | EXECUTE (2a+2b) ≤400ms |
| `specs/core/01-tick-protocol.md` §1.4 Tick 状态机 | `超时: 500ms` (for stage 2) |

The tick-protocol spec allocates 500ms for the EXECUTE phase, while engine.md allocates 400ms. This 100ms difference (25% gap) matters because:

- **Tick budget sum**: With engine.md values: 50 + 2500 + 400 + 50 + 50 = 3050ms > 3000ms tick interval. The budgets already exceed the interval.
- With tick-protocol.md values: 500ms for EXECUTE makes the overflow worse.
- The FDB commit retry loop (up to 3 retries with 1s backoff) can consume up to 3 seconds beyond these budgets.

**Recommendation**: Use engine.md's 400ms as the authoritative budget for EXECUTE. Update tick-protocol.md to match. Also note that the budget sum (50+2500+400+50+50=3050ms) exceeds the 3000ms tick interval — the budgets should sum to ≤3000ms or the interval should be increased to 3500ms.

---

### H1 — Tick Budget Sum Exceeds Tick Interval (High)

As noted in C3, the engine.md phase budgets sum to:

```
50ms (SNAPSHOT) + 2500ms (COLLECT) + 400ms (EXECUTE) + 50ms (COMMIT) + 50ms (BROADCAST) = 3050ms
```

This exceeds the 3000ms tick interval. Either:
- The 3000ms interval needs to increase to 3500ms (matching the budget sum + 450ms headroom)
- Or individual budgets need trimming: e.g., COLLECT to 2400ms

The per-player sandbox deadline of 2500ms _is_ the COLLECT budget — but COLLECT includes snapshot stitching overhead beyond raw WASM execution. At 500 players, snapshot stitching alone costs ~100ms (from benchmark gate), leaving 2400ms for WASM execution.

**Recommendation**: Increase tick interval to 3500ms as the design target, or establish explicit headroom between budget sum and interval.

---

### H2 — Benchmark Gates vs Budget Claims Not Cross-Referenced (High)

The persistence-contract §8.3 defines synthetic benchmark gates:
- "Entity snapshot clone: 50k entities, p99 < 20ms"
- "Snapshot stitching: 1000 × 256KB snapshots, p99 < 100ms"
- "FDB single-tx commit: 500 active players, p99 < 200ms"

But engine.md §3.4.1 declares:
- "SNAPSHOT build: ≤50ms (p99)"
- "COMMIT (FDB): ≤50ms (p99)"

The benchmark gate for FDB commit is **200ms p99**, while the engine contract is **50ms p99** — a 4× gap. The benchmark gate is the implementation-validated number; the engine contract is aspirational.

**Recommendation**: Cross-reference benchmark gates from persistence-contract into engine.md's budget table. Add a `verified_by` column linking each budget to its gate.

---

### H3 — Worker Pool Sizing Ignores Snapshot Stitching Overhead (High)

The 500-player capacity derivation in engine.md §3.4.2 assumes:
```
500 players × 5ms avg = 2500ms ← equals collect budget
```

But this ignores snapshot stitching overhead (~100ms for 500 players from benchmark gates), dispatch overhead, and result collection. The actual timeline is:

```
snapshot_build(50ms) + stitch(100ms) + dispatch_overhead + wasm_execution(5ms × 500 across N cores)
```

At 32 cores with 256 workers: wall-clock ≈ 50 + 100 + ~10 + (500 × 5ms / 32 × cores) ≈ 160 + 78 = ~238ms of serial overhead before parallelism. The remaining 2262ms of the COLLECT phase is for parallel WASM execution. At 5ms avg, ~450 players of WASM can fit (not 500).

**Recommendation**: Include snapshot stitching and dispatch overhead in the 500-player derivation. The current derivation is over-optimistic by ~100-150ms of unaccounted serial work.

---

### M1 — Sandbox Worker 1000-tick Recycle Unreferenced in Specs (Medium)

`design/engine.md` §3.4.3: "每 worker 最多服务 1000 tick 后强制替换"

This lifecycle constraint (mandatory worker replacement after 1000 ticks) is defined in engine.md but absent from `specs/core/04-wasm-sandbox.md`. The spec describes pool lifecycle in general terms but does not mention the 1000-tick recycle limit.

**Impact**: The 1000-tick recycle is a performance-relevant detail — it affects worker pool churn rate and baseline overhead. At 3000ms/tick, a worker recycles every ~50 minutes. Missing this in the spec means implementation may inadvertently skip this lifecycle step.

**Recommendation**: Add the 1000-tick recycle limit to `specs/core/04-wasm-sandbox.md` §1 (生命周期 section).

---

### M2 — Arena Budget Table Missing from Engine Budget Section (Medium)

`design/engine.md` §3.4.1 defines a comprehensive World/Arena budget table. `design/modes.md` §9.1.2 defines `tick_interval_ms = 300` for Arena. But there is no cross-reference from modes.md's Arena budget back to engine.md's Arena budget column. The Arena budgets (300ms tick, 200ms COLLECT, 50ms EXECUTE, 20ms COMMIT) are only visible in engine.md.

**Recommendation**: Add a cross-reference from `design/modes.md` Arena section to `design/engine.md` §3.4.1 for the Arena-specific tick pipeline budget. The Arena section currently only mentions `tick_interval_ms = 300` without the full budget decomposition.

---

## GAP Items (spec超前 design未定义)

### GAP1 — MCP Simulate/Dry-Run Resource Limits (spec-only)

`specs/core/04-wasm-sandbox.md` §6.1 defines hard limits for `swarm_simulate`:
- `max_ticks: 100`, `max_entities: 1000`, `max_output_bytes: 1 MB`, `max_cpu_ms: 5000`, `max_fuel_per_hour: 50,000,000`, `concurrent_simulates: 3`

These limits are absent from `design/engine.md`'s capacity contract (§3.4.2). The engine capacity table covers normal tick operations but doesn't mention simulate resource budgets.

**Recommendation**: Add a simulate/dry-run resource budget row to `design/engine.md` §3.4.2, or cross-reference `specs/core/04-wasm-sandbox.md` §6.1.

---

### GAP2 — Snapshot Truncation Abuse Detection Limits (spec-only)

`specs/core/01-tick-protocol.md` §2.3 defines abuse detection thresholds:
- `MAX_VISIBLE_ENTITIES` = 500 (entity膨胀攻击)
- 连续 3 tick `truncated=true` → `snapshot_quota -= 10%`
- `path_find` cache_miss > 50 → 后续返回空路径

These numeric thresholds are not referenced in `design/engine.md` §3.4.4 (WASM Snapshot Truncation section). The design section describes truncation priority buckets but omits the anti-abuse numeric thresholds.

**Recommendation**: Add the anti-abuse numeric thresholds to `design/engine.md` §3.4.4 or cross-reference `specs/core/01-tick-protocol.md` §2.3.

---

## Scaling Limits Analysis

| Dimension | Design Target | Bottleneck | Headroom |
|-----------|-------------|------------|----------|
| **Players (single node)** | target 500 / hard 1000 | CPU cores × WASM parallelism | Thin — 500 players at p50=5ms saturates COLLECT |
| **Entities** | 50,000 hard cap | Snapshot clone + FDB commit | Benchmark gates at p99=20ms/200ms; engine claims need tightening |
| **Drones** | target 5,000 / hard 10,000 | Per-tick command processing (max 100 × 500 players = 50,000 commands/tick) | The 100k commands/tick benchmark gate covers this |
| **Rooms** | unbounded (world_size config) | Cross-room operations (2PC in room-partition mode) | Not benchmarked for >200 rooms |
| **Tick latency** | 3000ms target | Budget sum > interval (see H1) | Negative — budgets overflow interval by 50ms+ |
| **Snapshot throughput** | 256KB × 500 players = 128MB/tick | Stitching benchmark gate at 100ms p99 for 1000 snapshots | Acceptable |
| **Pathfinding** | 100,000 nodes/tick global | Per-player fair-share at 50 drones/player × 10 calls = 500 nodes/call avg | Adequate at target 500 players (200 nodes/player) |

**Key scaling concern**: The 500→1000 player transition relies on worker pool scaling from 256→1000 workers. At 1000 players with 1000 workers, per-player WASM fuel must drop dramatically (effective_per_player_quota drops 50%). The aggregate CPU admission formula correctly gates this, but the player experience degradation at hard cap has no documented SLO.

---

## Concurrency Risks

1. **FDB single-tx contention at 500+ players**: The persistence-contract §8.1 acknowledges this and provides room-partition as the upgrade path. However, the engine.md capacity contract assumes single-tx MVP for "target 500." The benchmark gate requires "conflict rate < 1%" at 500 players — if this gate fails, the 500-player target is invalid.

2. **Phase 2b parallel safety**: The 29-system manifest with explicit R/W matrix is comprehensive and correct. Combat Parallel Set A partitions by `target_id` — safe. Status Effects Parallel Set B partitions by `StatusState` subtype — safe. RoomCap intermediate-state protection between S07→S08 is documented.

3. **WASM worker pool dispatch ordering**: Workers execute in parallel — the per-player sandbox deadline (2500ms) is per-worker, not global. A single slow player (p99=15ms) doesn't cascade. The epoch interruption mechanism provides hard cutoff. ✓

4. **Snapshot build ↔ WASM execution race**: The two-phase design (build once before dispatch) eliminates this. COLLECT results are cached across FDB commit retries. ✓

5. **Bevy World snapshot/restore for FDB rollback**: The persistence-contract §8.3 benchmark gate requires "p99 < 50ms, entity ID allocator verified." This is the correct safety mechanism — restore correctness is verified, not assumed. ✓

---

## Summary

| Severity | Count | Items |
|----------|-------|-------|
| Critical | 3 | C1 (drone cap 500 vs 50), C2 (snapshot budget 50ms vs 200ms), C3 (EXECUTE 400ms vs 500ms) |
| High | 3 | H1 (budget sum > interval), H2 (benchmark gates vs budget mismatch), H3 (stitching overhead unaccounted) |
| Medium | 2 | M1 (1000-tick recycle missing in spec), M2 (Arena budget cross-reference missing) |
| GAP | 2 | GAP1 (simulate limits not in design), GAP2 (anti-abuse thresholds not in design) |

All findings are spec↔design alignment issues — no implementation defects (nothing to test). The core architecture contracts (ECS scheduling, FDB async blob, fair-share admission) are sound. The three Critical items are numeric discrepancies between the IDL/engine/spec documents that must be resolved before implementation benchmarking can be trusted.