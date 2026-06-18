# R-appcert-R2 Performance Review — DeepSeek V4 Pro (Architect Reviewer)

> **Profile**: rev-dsv4-performance | **Date**: 2026-06-18
> **Scope**: Performance perspective — Tick efficiency, ECS scheduling, WASM compile/execute, auth hot path, caching, CRL scale

---

## Verdict: CONDITIONAL_APPROVE

The design demonstrates strong performance fundamentals — WASM pre-compilation, two-phase snapshot architecture, per-tick sandbox fork lifecycle, and Blake3 single-primitive strategy are all sound choices. However, there are scaling inconsistencies between the stated MVP target (500 drones total) and the per-player caps (500 drones/player → 25K total), creating a gap in the snapshot budget model. One critical finding on Arena tick timeout mismatch and several high-severity concerns requiring resolution before Phase 1 implementation.

---

## Strengths

1. **WASM Pre-Compilation eliminates JIT from tick hot path**: Modules are compiled to native code at deploy time (30s budget), not at tick time. Tick execution only instantiates pre-compiled modules. This is the correct architecture for deterministic, low-latency WASM execution.

2. **Two-Phase Snapshot Architecture**: Replaced per-player full serialization (O(P×E)) with one-time world snapshot + per-player room-filtered views (O(E + P×rooms)). The "build once, filter many" model is architecturally correct and eliminates redundant serialization.

3. **COLLECT Result Caching on FDB Commit Retry**: When FDB commit fails, cached COLLECT results (command lists + fuel deductions) are reused without re-executing WASM. This prevents double fuel billing and saves significant CPU on the failure path. The constraint that WASM is executed exactly once per tick (first COLLECT only) is correctly enforced.

4. **Bevy Parallel Scheduling with Proven Data Independence**: The Component/Resource read-write matrix proves `regeneration_system` and `decay_system` have no data races with the main chain. The `.before()/.after()` constraints ensure correctness while Bevy's scheduler handles thread assignment. Determinism is preserved — results don't depend on parallelism degree.

5. **Blake3 Single Primitive**: Hash, PRNG (XOF), and MAC unified under one dependency. ~6 GB/s software throughput, no platform degradation (unlike AES-NI dependency). Simplifies audit surface and eliminates ChaCha crate.

6. **Auth Hot Path Architecture**: Dragonfly SETNX TTL for nonce storage (not FDB writes), in-engine LRU for certificate chain verification, challenge-response for high-value operations — each choice correctly avoids FDB transaction overhead on the auth hot path.

7. **Seeded Shuffle with Blake3 XOF**: Deterministic, fair player ordering with O(N) complexity and negligible overhead. Seed rotation every 10K ticks is architecturally clean.

8. **Host Function Budget Model**: Total 1000 calls/tick, path_find capped at 10/tick + 100K explored_nodes, get_objects_in_range at 5/tick. All well-bounded with deterministic failure on exhaustion.

9. **Fuel Model Architecture**: WASM instruction counting (not wall-clock), per-tick fork/kill lifecycle, and the fuel refund model for FDB commit failures are all correctly specified.

---

## Findings

### Critical

**D1: Per-Player Drone Cap Inconsistency Creates Snapshot Budget Violation**

| Document | Limit |
|----------|-------|
| engine.md §3.2 (Snapshot scale model) | Tier 1 target = 50 players × 10 drones = **500 total** |
| 07-world-rules.md §2 | `max_drones_per_player = 500` |
| engine.md §3.2 (Tier Entry Gate) | Tier 1 snapshot budget = ≤16MB, ≤50ms |

At 50 players × 500 drones = **25,000 drones**, the Tier 1 deep-copy snapshot would be ~50× the budgeted 16MB (approaching 800MB for full component data). This is a direct contradiction between the performance budget and the gameplay configuration limits.

**Recommendation**: Either (a) lower `max_drones_per_player` to 10 for Tier 1 MVP, or (b) enforce a global `max_total_drones` at the engine level with a hard cap of 500 for Tier 1. The per-player cap should not be 50× the budgeted total.

**Severity**: Critical — Tier 1 snapshot is the foundation for deterministic replay. A 50× budget violation would cause tick timeouts.

---

**D2: Arena Mode tick_interval_ms (300ms) vs collect_timeout_ms (2500ms) Mismatch**

01-tick-protocol §8.1 defines:
- `tick_interval_ms = 3000ms` (World) / `300ms` (Arena, default)
- `collect_timeout_ms = 2500ms` (hard deadline for COLLECT)
- `tick_soft_deadline_ms = 2500ms`

For Arena at 300ms tick interval, the 2500ms collect timeout is **8.3× the tick interval** — effectively disabled. All COLLECT budgets (2500ms per-player wall-clock, 10M fuel) are designed for World's 3000ms cycle, not Arena's 300ms cycle.

**Recommendation**: Define Arena-specific budget parameters proportional to tick_interval_ms. For 300ms Arena: `collect_timeout_ms ≈ 200ms`, `fuel_per_player ≈ 1M`, `snapshot_budget ≈ 5ms`.

**Severity**: Critical — Arena mode would operate with World-scale budgets, enabling players to consume 8× more CPU per in-game tick than intended.

---

### High

**D3: FDB Transaction Size Under Max-Drone Scenario**

FDB has a practical transaction size limit (~10MB). At the Tier 1 target of 500 drones, the world state serialization is ≤16MB (stated budget). But at 25K drones (from D1), the transaction would far exceed FDB limits. Even at 500 drones, the TickTrace data (commands, state, rejections, metrics) is written within the same FDB transaction. The cumulative transaction size is not explicitly budgeted.

**Recommendation**: Add a TickTrace size budget to §8.2 of 01-tick-protocol. Specify maximum FDB transaction size (e.g., ≤8MB to stay well under FDB's 10MB limit). Add CI assertion: `fdb_txn.estimated_size() < 8MB`.

**Severity**: High — FDB transaction failure at scale would cause tick abandonment and engine degradation.

---

**D4: Pathfinding Cache Has No Size Limit or Eviction Policy**

04-wasm-sandbox §8 specifies path_find caching with key `(from, to, terrain_hash, player_visibility_fingerprint)`. No cache size limit, no eviction policy, and the cache key is per-player (different visibility fingerprints). At 500 players × 10 path_find calls/tick × varied positions, the cache could grow to millions of entries. Even at a modest 1KB per cache entry, this is gigabytes of memory.

**Recommendation**: Add a bounded LRU cache with configurable size (e.g., 100K entries). Specify eviction under memory pressure. Consider a two-tier cache: global terrain cache (shared, large) + per-player route cache (small, per-tick).

**Severity**: High — Unbounded memory growth is a stability risk for long-running World instances.

---

**D5: Visibility Cache Recalculation Strategy Underspecified**

05-visibility §5 states visibility cache is keyed `(tick, player_id)` and computed once per tick. But for 500 players with drones spread across the world, the naive O(P × E_in_visible_rooms) approach is expensive. The room-partitioned snapshot architecture helps, but the visibility calculation itself needs:

- Spatial indexing (grid/spatial hash) to avoid per-entity distance checks
- Incremental update: most entities don't move between ticks, and players' visible room sets rarely change

**Recommendation**: Add a spatial index (grid-based lookup) to the visibility system. Document the expected computational cost: O(P × avg_entities_per_visible_room_set). For Tier 1 MVP this is manageable; for Tier 2, incremental visibility updates should be specified.

**Severity**: High — At Tier 1 scale this works, but without spatial indexing the design leaves performance characteristics unspecified for the Tier 1→Tier 2 transition.

---

### Medium

**D6: Dragonfly Cold Start After Engine Restart Has No Mitigation**

05-visibility §5 describes Dragonfly as non-authoritative cache. After engine restart, Bevy World rebuilds from FDB, but Dragonfly is empty. All reads go directly to FDB until the cache warms up (2+ ticks). For the first 2 ticks after restart, FDB read pressure is at peak.

**Recommendation**: Add a cache warming step during engine startup — preload Dragonfly with the initial world state from FDB before accepting player connections.

**Severity**: Medium — Affects only restart scenarios, but restart is a critical failure recovery path.

---

**D7: Command Processing Queue Length in Worst Case**

02-command-validation specifies `MAX_COMMANDS_PER_PLAYER = 500`. With 50 players at Tier 1, worst case is 25,000 commands in the global queue. Phase 2a inline execution processes commands sequentially. At even 10μs per command validation + application, that's 250ms. Including ECS system execution (Phase 2b), the total EXECUTE phase budget is 500ms. At worst-case command volume, the budget is tight.

**Recommendation**: Document expected per-command processing latency (target: <20μs for validation + inline apply). Add a Phase 2a progress metric so operators can detect command queue saturation.

**Severity**: Medium — Within Tier 1 budget (500 drones, not 25K), the 500ms EXECUTE budget is sufficient. The risk materializes at higher scales or with many complex special-attack commands.

---

**D8: Certificate Revocation List (CRL) Cache TTL Ambiguity**

auth.md §10.8 specifies CRL cache with "60s" staleness allowance. But the text also says the Engine LRU cache for cert verification has "0 (即时失效)" delay. These appear contradictory — if CRL cache has 60s TTL, certificate verification is NOT instantaneously invalidated on revocation. The revocation window is up to 60 seconds.

**Recommendation**: Clarify the CRL cache TTL vs verification cache relationship. If CRL has 60s staleness, explicitly state this as an accepted risk in the security model. Consider reducing to 5-10s for competitive worlds where revocation responsiveness matters.

**Severity**: Medium — Operational tradeoff between performance and security responsiveness. 60s window may be acceptable but must be explicit.

---

**D9: `host_path_find` cache_miss > 50 → returns empty path (Abuse Detection)**

01-tick-protocol §2.3 specifies: "单 tick `path_find` cache_miss > 50 → 该 tick 后续 path_find 返回空路径". But the host function budget limits path_find to 10 calls/tick total (04-wasm-sandbox §2). A limit of 50 cache misses per tick is meaningless when only 10 calls are allowed. The abuse detection threshold should be consistent with the call budget.

**Recommendation**: Align abuse detection threshold with actual budget: `cache_miss > 5` (50% of the 10-call budget) triggers the empty-path response.

**Severity**: Medium — The rule is non-functional (can never trigger) but reveals a spec consistency issue.

---

### Low

**D10: Snapshot Deep Copy Restore on FDB Commit Failure**

When FDB commit fails, Bevy World is restored from a deep-copy snapshot taken before Phase 2a. At Tier 1 scale (≤16MB), each restore is ~50ms. With up to 3 retries, worst-case overhead is 150ms. The snapshot+restore mechanism is architecturally correct, but the 50ms restore latency is not explicitly budgeted in the EXECUTE phase.

**Recommendation**: Add snapshot restore latency to the EXECUTE phase budget table (§8.2). Budget ~50ms per restore attempt.

**Severity**: Low — Within current Tier 1 budget, but undocumented.

---

**D11: MCP `swarm_simulate` Concurrent Limit**

04-wasm-sandbox §6 specifies `concurrent_simulates = 3` per player. Each simulate can use up to 5000ms CPU and 50M fuel/hour. Three concurrent simulates × 5000ms CPU each = 15s CPU in worst case. Engine resources consumed by simulation should not starve tick execution.

**Recommendation**: Add a global concurrent simulate limit (e.g., 50 total across all players) and a simulate CPU priority lower than tick COLLECT/EXECUTE.

**Severity**: Low — Per-player limit prevents individual abuse, but no global cap for aggregate impact.

---

**D12: Overload Attack — Fuel Recovery Rate Scaling**

Overload's recovery formula is `fuel_budget / 1000` per tick. For 10M budget → 10K/tick recovery. But if MAX_FUEL is world-configurable (world.toml), the recovery rate scales linearly. At 1M budget → 1K/tick recovery. The Overload lock-proof (01-tick-protocol §3.17) assumes MAX_FUEL=10M. For custom worlds with lower budgets, the proof should be re-validated.

**Recommendation**: Parameterize the Overload lock-proof with configurable MAX_FUEL. Add a CI property test: `∀ budget ∈ [1M, 100M]: recover_from_floor(budget) > 0`.

**Severity**: Low — Affects only custom-world configurations.

---

## Consistency Gaps

1. **Snapshot Budget vs Drone Cap**: Tier 1 target (500 drones) contradicts `max_drones_per_player = 500` (→25K). See D1.

2. **Arena Budget vs World Budget**: Arena tick interval (300ms) uses World-scale COLLECT budgets (2500ms). See D2.

3. **Pathfinding Abuse Threshold vs Call Budget**: cache_miss > 50 threshold is unreachable when max path_find calls = 10. See D9.

4. **CRL Cache TTL vs Verification Cache**: 60s CRL staleness vs "instant" verification invalidation. See D8.

5. **Per-Drone Per-Tick Action Quota vs Transfer**: Transfer/Withdraw are excluded from the per-drone action quota (01-tick-protocol §3.3 rule #3) but carry no per-tick call limit beyond host function budget (1000 total). A drone with CARRY could issue 1000 Transfer calls in one tick, each with range=1 check → all within budget.

---

## Algorithmic Risks

1. **Seeded Shuffle Observation Window**: With seed rotation every 10K ticks and 3s/tick, the window is ~8.3 hours. An attacker who learns world_seed can predict player ordering for 8+ hours. The forward-secrecy analysis in 01-tick-protocol §3.1 acknowledges this risk. The 10K rotation period is a reasonable trade-off, but operators should monitor for statistical anomalies in player win rates correlated with ordering position.

2. **FDB Commit Contention Under Load**: Multiple players issuing commands that modify the same FDB keys (e.g., two players harvesting the same Source in different worker batches) create FDB transaction conflicts. With 3 retries + 1s delay between retries, a tick could take up to 6+ seconds (2.5s COLLECT + 500ms EXECUTE + 3 × 1s retry delays). The design handles this with tick abandonment after 3 failures, but the tail latency is significant.

3. **WASM Instance Memory Allocation Pattern**: The tick() ABI requires: engine alloc(snapshot_len) → write snapshot → alloc(8) for result_ptr → call tick() → read result → free(ptr, len) × 2. Each alloc/free is a WASM linear memory operation. For large snapshots (near 256KB), repeated alloc/free across ticks could fragment linear memory. Wasmtime's memory management handles this, but the per-tick fork/kill lifecycle (new process each tick) eliminates this concern entirely — a strong architectural choice.

---

## Summary

| Severity | Count | Key Items |
|----------|-------|-----------|
| Critical | 2 | D1 (drone cap vs snapshot budget), D2 (Arena budget mismatch) |
| High | 3 | D3 (FDB txn size), D4 (pathfinding cache), D5 (visibility calc) |
| Medium | 4 | D6-D9 (cold start, command queue, CRL TTL, abuse threshold) |
| Low | 3 | D10-D12 (snapshot restore, simulate cap, Overload recovery) |

The architecture is fundamentally sound for the stated MVP scope (500 drones, 50 players). The critical issues are scaling inconsistency between gameplay caps and performance budgets — easily resolved by aligning the per-player drone limit with the snapshot budget. The Arena budget mismatch requires explicit budget scaling proportional to tick interval. The high-severity findings are all Tier 1→Tier 2 transition risks that should be addressed in spec before Phase 1 code begins.

**Verdict**: CONDITIONAL_APPROVE — resolve D1 and D2 before implementation. Address D3-D5 in spec updates during Phase 1.
