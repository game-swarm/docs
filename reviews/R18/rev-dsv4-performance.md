# R18 Performance Review — DSV4 Pro

**Reviewer**: rev-dsv4-performance (DeepSeek V4 Pro)  
**Date**: 2026-06-18  
**Review Type**: Clean-Slate Performance Review  
**Documents Reviewed**: 9 files (design/ + specs/core/ + specs/reference/)

---

## 1. Verdict

**CONDITIONAL_APPROVE** (4 findings: 1 Critical, 2 High, 1 Medium, 1 Low)

The tick pipeline architecture is well-decomposed with clear budget allocation, the two-phase snapshot optimization is sound, and the 29-system manifest with R/W matrix provides strong concurrency safety guarantees. However, **one critical numerical drift (MAX_POOL 1000→256) invalidates the 1000-player capacity derivation**, and the 3s tick interval has zero headroom against the budgeted numbers. These must be resolved before implementation.

---

## 2. Findings

### D1 [CRITICAL] Worker Pool MAX_POOL Divergence: engine.md=1000 vs YAML IDL=256

**Documents**:
- `engine.md` §3.4.2: `MAX_POOL = 1000（hard cap，编译期常量）`
- `api-registry.md` §5.5: `Worker pool max: max_pool = 256`
- `game_api.idl.yaml` §5 limits.hardware_baseline: `worker_pool_max: 256`

**Analysis**: engine.md's capacity derivation for 1000 players explicitly assumes 1000 workers executing in parallel:

> "假设 1000 workers，p50=5ms，理论 peak = 5000ms 但并行化为 ~25ms wall-clock (1000 workers / 40 cores)"

If max_pool is 256 (as the authoritative YAML IDL declares), then at 1000 players the multiplex factor is ~4. The wall-clock execution per worker becomes `4 × 5ms = 20ms` (p50) with p99 tail at `4 × 15ms = 60ms`. Combined with dispatch overhead (~500ms), the total COLLECT wall-clock approaches `500ms + 60ms = 560ms` which still fits within 2500ms. **However**, this assumes perfect load balancing across workers. In practice:

- Worker assignments are per-player, not per-CPU-core
- Uneven WASM execution times create straggler workers
- 256 workers on 32 cores means ~8 workers/core; context switching overhead is non-trivial
- At p99=15ms per player with 4 players/worker: worst-case worker = 60ms, but with scheduling variance this balloons

**Impact**: The 1000-player capacity claim in engine.md is based on an incorrect MAX_POOL value. With MAX_POOL=256, 1000 players may still be achievable, but the derivation must be rewritten using the correct number. The hard cap should either be adjusted to 1000 (if the 256 was a mistake) or the capacity derivation must account for multiplexing overhead.

**Recommendation**: Reconcile MAX_POOL to a single authoritative value in the YAML IDL. If 1000 is the intent, update limits.hardware_baseline.worker_pool_max to 1000. If 256 is the intent, re-derive the 1000-player capacity in engine.md with multiplexing math.

---

### D2 [HIGH] Tick Budget Exceeds Interval — Zero Headroom

**Documents**:
- `engine.md` §3.4.1: Budget breakdown
- `01-tick-protocol.md` §8.1-8.2: Unified budget table

**Analysis**: The stated budgets sum to:
```
SNAPSHOT build:  ≤50ms
COLLECT:         ≤2500ms
EXECUTE (2a+2b): ≤400ms
COMMIT (FDB):    ≤50ms
BROADCAST:       ≤50ms
───────────────────────
Total:           ≤3050ms  vs  tick_interval = 3000ms
```

The budgets already exceed the target interval by 50ms at p50. At p99:
- SNAPSHOT: 50ms is p99 target → headroom consumed
- COLLECT: at 500 players with 5ms avg, exactly 2500ms → no headroom
- Any single-stage overrun cascades into tick abandonment

The `tick_soft_deadline_ms = 2500ms` in 01-tick-protocol §8.1 acts as a safety valve, but the system is designed to regularly hit it — `collect_timeout_rate > 10%` triggers alerts (§5). A system that alerts at normal operating conditions has a design tension.

**Recommendation**: Either:
1. Increase `tick_interval` to 3500ms (adds 500ms slack)
2. Reduce COLLECT budget to 2200ms and tighten per-player execution (fuel cap reduction)
3. Add explicit slack allocation (~10% = 300ms) to the budget table and recalculate all dependent numbers

---

### D3 [HIGH] FDB Transaction Size: 10KB (persistence-contract) vs 10MB (tick-protocol)

**Documents**:
- `05-persistence-contract.md` §7: `单 tick 事务 < 10KB`
- `01-tick-protocol.md` §9.4: `确保事务大小 < 10MB（FDB 推荐上限）`

**Analysis**: The persistence contract (§7) specifies a 10KB FDB transaction limit, while tick-protocol §9.4 cites FDB's 10MB recommended limit. These differ by 1000x. The persistence contract's 10KB is likely aspirational — at 5000 active drones with state mutations, even delta-only writes would exceed 10KB. The tick-protocol's 10MB is FDB's documented safe upper bound.

The persistence contract itself clarifies (in the same §7) that the FDB transaction includes:
> "FOR each persistent state mutation: UPDATE entity/resource/controller/... rows"

This implies per-entity state rows in FDB, which at 5000 drones would be substantial even with delta encoding.

**Recommendation**: Align on a realistic transaction size budget. Suggestion: 100KB as a practical target with 1MB hard cap. Document the per-entity mutation cost estimate to justify the budget. The 10KB in persistence-contract §7 should be revised upward.

---

### D4 [MEDIUM] Wasmtime ≥30 Fuel Polling Overhead (vs Callback)

**Documents**:
- `04-wasm-sandbox.md` §2.2: `// 注意: Wasmtime ≥30 移除了 fuel_consumed_callback API；燃料检查改为在 Store 层通过 get_fuel() 轮询`

**Analysis**: Wasmtime ≥30 removed the `fuel_consumed_callback` API. The design now relies on polling `get_fuel()`. The document notes this but does not quantify the overhead:

- Poll frequency is unspecified — is it per-host-function-call? Per-N-instructions?
- At 1000 host function calls/player/tick with 500 players: 500,000 fuel polls/tick
- If each poll is ~100ns (a reasonable estimate for an atomic read), total overhead is ~50ms — 2% of COLLECT budget
- If polling is per-instruction (in Wasmtime's internal fuel loop), the overhead is already priced into Wasmtime's execution cost

**Recommendation**: Document the polling strategy (frequency/trigger) and include it in the COLLECT budget derivation as a line item. Consider benchmarking Wasmtime ≥30 fuel polling overhead at 500 concurrent instances.

---

### D5 [LOW] Snapshot Truncation Priority Buckets: engine.md vs tick-protocol.md

**Documents**:
- `engine.md` §3.4.4 priority buckets: `自机 > 友方 drone > 敌方 drone > 建筑 > NPC > 资源`
- `01-tick-protocol.md` §2.3 priority buckets: `关键桶(Spawn/Controller/depot/storage) > 高优先(己方 drone/己方建筑) > 中优先(敌方可见实体/资源点) > 低优先(友方实体/中立实体)`

**Analysis**: The two documents describe different bucket structures. engine.md has 6 flat tiers; tick-protocol.md has 4 tiers with sub-categories. The tick-protocol version is more detailed and references "关键桶" (critical bucket) for Spawn/Controller/depot/storage — these are always preserved regardless of truncation. engine.md's version lacks this critical-bucket concept entirely. Since tick-protocol.md explicitly states truncation is a replay-determinism concern (same input → same truncation result), the bucket structure must be unambiguous.

**Recommendation**: Adopt the tick-protocol.md 4-tier bucket structure as authoritative. Update engine.md §3.4.4 to reference it rather than re-declaring.

---

## 3. Strengths

- **Two-phase shared snapshot architecture**: O(entities + players × visible_rooms) instead of O(players × entities) — a fundamental scalability improvement over per-player serialization. The COLLECT→EXECUTE separation with cache-reuse on FDB retry is elegant.

- **29-system R/W matrix with parallel safety proof**: The manifest (06-phase2b-system-manifest.md) provides exhaustive read/write declarations for all 29 systems. Parallel safety for Combat Set A (target_id partition) and Status Set B (disjoint component subtypes) is formally justified. RoomCap intermediate-state protection (S07→S08 interval) is explicitly documented.

- **Aggregate CPU admission formula**: `floor(TICK_BUDGET_COLLECT_MS × CPU_CORES × PER_CORE_MIPS) / active_players` with MIN_FUEL gate — prevents CPU saturation from propagating to existing players. This is a well-reasoned formula that ties hardware capacity to per-player fairness.

- **FDB-first, blob-async persistence model**: FDB commit = tick authority; blob upload is asynchronous with retry. This correctly decouples transaction latency from I/O throughput. The `upload_status` state machine (pending→uploading→complete/failed) and replay-verifier integration are thorough.

- **COLLECT cache reuse across FDB retries**: Same collect_id, same commands_hash, no WASM re-execution, no double fuel charging. The collect_id/attempt_id/commit_id triple provides full auditability across retry attempts.

- **Seed-shuffle player ordering**: Deterministic, fair (per-tick rotation), and unpredictable. The forward-secrecy threat model analysis (§3.1) is honest about the accepted risk and documents the mitigation (epoch rotation + admin seed bump).

---

## 4. CrossCheck: YAML IDL ↔ api-registry.md Drift Analysis

The task specifies: "生成式单源是否真正闭合，YAML↔Markdown 是否无漂移"

### 4.1 Structural Equivalence

| Section | YAML IDL | api-registry.md | Match |
|---------|----------|-----------------|-------|
| api_version | `"0.3.0"` | `0.3.0` | ✓ |
| CommandAction variants | 19 (indices 1-19) | 19 (11 core + 2 global + 6 special) | ✓ |
| RejectionReason total | 35 canonical codes | 35 (2 pipeline + 26 validation + 3 MCP + 4 runtime) | ✓ |
| MCP Tools total | 46 active | 46 (8 Onboarding + 2 Auth + 14 Play + 6 Deploy + 7 Debug + 6 Admin + 1 SDK + 2 Resources) | ✓ |
| Host Functions total | 5 | 5 | ✓ |
| TickTrace Envelope fields | 22 | 22 | ✓ |
| terminal_state variants | 7 | 7 | ✓ |
| Direction4 values | 4 (N/S/E/W) | 4 | ✓ |

### 4.2 Content-Level Drift

| Item | YAML IDL | api-registry.md | Drift? |
|------|----------|-----------------|--------|
| debug_detail max_length | 512 bytes | 512 bytes | ✓ None |
| detail_level default | competitive | competitive **(默认)** | ✓ None |
| swarm_get_snapshot output_schema | `{tick, entities, terrain, resources, truncated, omitted_count}` | `{tick, entities, terrain, resources, truncated, omitted_count}` | ✓ None |
| swarm_list_market_orders | RFC section, not active | RFC section, not active | ✓ None |
| Auth tools count | 2 (swarm_auth_login, swarm_auth_refresh) | 2 | ✓ None |
| Deploy fdb_version_counter | u64, atomic with manifest | u64, atomic with manifest | ✓ None |
| Sandbox CPU limit | `cpu.max = 250000 3000000` | `cpu.max = 250000 3000000` | ✓ None |
| worker_pool_max | 256 | 256 | ✓ None |
| global_drone_cap | 10000 | 10,000 | ✓ None |
| global_entity_cap | 50000 | 50,000 | ✓ None |
| pathfinding_budget | 100000 explored nodes/tick | 100,000 explored nodes/tick | ✓ None |
| keyframe_interval | 100 ticks | K=100 ticks | ✓ None |

### 4.3 Host Function ABI Error Priority

YAML IDL and api-registry.md both list 9 error codes (-1 through -9) with identical priority ordering, names, and conditions. No drift. ✓

### 4.4 CrossCheck Verdict

**YAML IDL ↔ api-registry.md: NO DRIFT DETECTED.** The generated Markdown faithfully reproduces all structured data from the YAML IDL. The 46-tool list, 35 rejection codes, 5 host functions, 22 envelope fields, and all capacity limits match exactly. The single-source-of-truth closure holds.

**However**: The drift is not between YAML and registry — it's between **the YAML/registry pair and engine.md**. See D1 (MAX_POOL 1000→256) and D5 (truncation bucket structure).

---

## 5. Scaling Limits Summary

| Metric | Engine.md Claim | YAML/Registry Claim | Verdict |
|--------|----------------|---------------------|---------|
| MAX_POOL (workers) | 1000 | 256 | **DRIFT** — D1 |
| FDB transaction size | "小事务" (ambiguous) | 10KB vs 10MB cited elsewhere | **DRIFT** — D3 |
| Active players target/hard | 500/1000 | 500/1000 | Consistent |
| COLLECT budget saturation | 500 players at 5ms avg | Same | No headroom — D2 |
| Global drone cap | 5000 target / 10000 hard | 10000 (no target tier) | Minor language difference |

---

## 6. Concurrency Risk Summary

| Risk | Severity | Mitigation Status |
|------|----------|-------------------|
| Combat Set A parallel unsafety | None | target_id partition proven safe (disjoint entity sets) |
| Status Set B parallel unsafety | None | disjoint component subtypes proven safe |
| RoomCap read during S07→S08 gap | None | explicitly documented and gated; CI validates |
| DeathMark entity read by regen/decay | None | `Without<DeathMark>` filter enforced |
| FDB transaction conflict at scale | Medium | 3-retry + Bevy snapshot restore; lacks analysis of conflict rate at 500 players |
| Worker pool contention at 1000 players | Medium | 256 max pool → 4x multiplex; straggler risk not modeled |
| Seed-shuffle forward secrecy leak | Low | Accepted risk; documented with epoch rotation mitigation |
