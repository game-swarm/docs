# R22 Performance Review — DeepSeek V4 Pro

**Reviewer**: rev-dsv4-performance  
**Date**: 2026-06-18  
**Scope**: Phase 1 Clean-Slate — design/engine.md, design/tech-choices.md, specs/core/01-tick-protocol.md, specs/core/04-wasm-sandbox.md, specs/core/05-persistence-contract.md, specs/reference/api-registry.md

---

## 1. Verdict: CONDITIONAL_APPROVE

The design has a solid performance foundation: two-phase snapshot architecture, WASM precompilation, worker pool with per-tick Store reset, fuel metering, and FDB async blob upload. The performance contracts are explicit and budgeted. However, several concerns at the 500→1000 player boundary and under adversarial snapshot pressure need resolution before implementation.

---

## 2. Findings (Issues)

### Critical

None.

### High

#### D1 — Snapshot Truncation Cascade Under Adversarial Entity Spam

**Severity**: High  
**Location**: engine.md §3.4.4, 01-tick-protocol.md §2.3

The 256KB per-player snapshot cap is well-designed for normal operation. However, the anti-abuse detection is entirely **reactive** — it only triggers after 3-5 consecutive ticks of anomalous patterns (visibility_abuse after 5 ticks, truncated=true penalty after 3 ticks). An attacker can:

1. Deploy 500 cheap TOUGH drones near a victim's room boundary (cost: 500 × 10 = 5,000 energy)
2. These drones immediately push the victim's snapshot over 256KB
3. The victim operates with truncated information for 2-3 ticks before any penalty applies
4. Even after penalty (snapshot_quota -= 10%), the victim is already information-starved

**Recommendation**: Add a **proactive density tax** on visible entity count per room, calculated during snapshot construction. If a player's visible entity count in any single room exceeds a threshold (e.g., 100), apply progressive truncation with a known, deterministic formula rather than waiting for the reactive penalty. The density tax should be part of the deterministic snapshot contract so replay is unaffected.

#### D2 — Worker Pool Saturation at Hard Cap Underestimates Dispatch Overhead

**Severity**: High  
**Location**: engine.md §3.4.2

The capacity derivation for 1000 players assumes:
```
1000 players × 5ms avg = 5000ms wall-clock → parallelized to ~25ms (1000 workers / 40 cores)
Snapshot stitching + dispatch overhead ≈ 500ms
Remaining: 2500ms - 500ms = 2000ms for execution
```

This has two issues:

1. **Worker pool is capped at 256 (default) / 1000 (hard cap)**, not 1000 by default. At the default 256 workers with 1000 players, each worker handles ~4 players sequentially: 4 × 5ms = 20ms per worker. 256 workers on 32 cores = 8 batches: 8 × 20ms = 160ms execution wall-clock. This is within budget, BUT the snapshot stitching overhead is per-player not per-worker: 0.5ms × 1000 = 500ms. Combined: 160ms + 500ms = 660ms — within 2500ms but tight.

2. **The per-player WASM execution p50 of 5ms is an assumption, not a contract**. The engine has no mechanism to enforce this — it can only enforce the 2500ms hard deadline. At 1000 players, if even 10% take 50ms instead of 5ms, the wall-clock impact is catastrophic: (900 × 5ms + 100 × 50ms) / (256/32 batches) adds ~78ms to the worst-case batch — pushing execution time toward 800ms+. Combined with 500ms snapshot stitching, this breaches the 2500ms COLLECT budget.

**Recommendation**: 
- Decompose the 500ms snapshot stitching overhead: how much is visibility filter vs. serialization? Visibility filter can be parallelized per-room.
- Add a **per-worker execution time histogram** metric in CI regression tests. If p95 WASM execution exceeds a budgeted threshold, fail the CI.
- Consider a **two-tier dispatch**: fast-path players (p50 < 5ms estimated) get dispatched first; slow-path players get the remaining budget.

#### D3 — FDB Single-Commit Contention at 50000 Entities

**Severity**: High  
**Location**: engine.md §3.4.1, 05-persistence-contract.md §2

The FDB commit budget is ≤50ms (p99). At 50000 total entities, even with "small transaction (head/manifest/hash/pointer)" as stated, the actual state mutations must touch FDB. The design says "FDB 仅存储小型 manifest record" but Phase 2b produces state changes that must be persisted. 

The key question: **how many FDB keys are mutated per tick?** At 500 active players with average 10 drones each (5000 drones), if 20% of drones take an action that changes state (move, harvest, attack), that's 1000 state mutations per tick. FDB's strict serializability means these are serialized within a single transaction. 50ms for 1000 mutations = 50μs per mutation — achievable for FDB. But at 10000 drones with 20% action rate = 2000 mutations, the budget gets tight.

The async blob upload (D5/B) solves the large-write problem, but the small-write path still needs explicit capacity planning.

**Recommendation**: Add a per-tick mutation count budget to the capacity contract (§3.4.2). Something like: "max 5000 FDB key mutations per tick." Monitor this in CI with simulated load. If mutations exceed budget, batch writes or defer non-critical state updates to the next tick.

### Medium

#### D4 — Bevy World Snapshot Deep Copy: 50ms Budget is Tight

**Severity**: Medium  
**Location**: engine.md §3.4.1, 01-tick-protocol.md §3.5

The snapshot build budget is ≤50ms (p99) for 50000 entities. A full Bevy World deep copy at this scale involves:
- Entity count: 50000
- Components per entity: avg 5-8 (Position, Owner, Health, Body/Structure, etc.)
- Bytes per component: avg 32-64 bytes
- Total: 50000 × 6 × 48 ≈ 14.4 MB of component data + archetype metadata + resource snapshots

A 14+ MB deep copy in Rust (memcpy-heavy) at ~20 GB/s memory bandwidth = ~0.7ms for the raw copy. But Bevy's archetype-based storage means the copy involves iterating archetypes, which adds overhead. The 50ms budget should be achievable but the document should explicitly state how this is measured (wall-clock? CPU time?) and what happens if it exceeds budget (tick abandon?).

**Recommendation**: 
- Specify that snapshot is measured as wall-clock on the tick loop thread
- Add a CI test that builds a 50000-entity world and measures snapshot time
- If budget is exceeded, consider incremental snapshot (copy-on-write) or pre-allocated double-buffer

#### D5 — Pathfinding Fair-Share Collapse at 1000 Players

**Severity**: Medium  
**Location**: engine.md §3.4.2, api-registry.md §5.6

The pathfinding global budget is 100,000 explored nodes/tick, distributed per-player as `floor(100,000 / active_players)`. At 500 players: 200 nodes each. At 1000 players: 100 nodes each. 

100 explored nodes for A* on a 50×50 grid with obstacles is **barely enough for a 10-cell path** (A* typically explores 5-20 nodes per path cell depending on obstacle density). For cross-room pathfinding (up to 100 cells with obstacles), 100 nodes is insufficient — the path will be truncated or fail.

The "first-come-first-served" allocation means players at the end of the shuffle order (determined by seed) consistently get less or no pathfinding budget if early players consume it. While shuffle fairness ensures long-term equity, **within a single tick**, the last player in shuffle might get 0 pathfinding budget.

**Recommendation**: 
- Reserve a minimum per-player pathfinding budget (e.g., 50 nodes) regardless of fair-share calculation
- Consider a **pathfinding cache** that spans ticks: if a player requests the same `(from, to)` as last tick, return the cached result at near-zero cost. Cache key already defined as `(from, to, terrain_hash, player_visibility_fingerprint)` — good.
- Explicitly state the expected path length achievable with minimum node budget

#### D6 — No Network Fan-Out Budget for WebSocket Broadcast

**Severity**: Medium  
**Location**: engine.md §3.4.1 (no budget), 01-tick-protocol.md §4

The BROADCAST phase budget is ≤50ms but there is no breakdown of what this covers:
- Delta computation (entity diff)
- Dragonfly cache update
- NATS publish
- Gateway → WebSocket fan-out to 500+ clients

At 500 concurrent WebSocket connections, serializing and pushing tick deltas is a non-trivial operation. The Go gateway must handle:
- Serialization of delta (JSON or binary?)
- Fan-out to N connected clients
- Each client at different network latency

If serialization to JSON per client, 500 × (delta size) of serialization work. If delta is ~50KB, that's 25MB of JSON serialization. At Go's JSON performance (~100MB/s), that's 250ms — far exceeding 50ms.

**Recommendation**: 
- Specify that delta is serialized **once** (protobuf or binary), not per-client
- Gateway should use a shared buffer or zero-copy approach for fan-out
- Add a BROADCAST budget line item for "per-client serialization" — should be 0 (shared buffer)
- Add CI test: 500 mock WebSocket clients, measure broadcast wall-clock

#### D7 — WASM Worker Memory Reset Bandwidth

**Severity**: Medium  
**Location**: specs/core/04-wasm-sandbox.md §1, §6

Per-tick Store reset clears WASM linear memory (up to 64MB per instance). At 256 active workers, that's up to 16GB of memory zeroing per tick. At DDR4 bandwidth (~20 GB/s), this alone consumes ~0.8s of memory bandwidth. While this is spread across workers on different cores, it still consumes significant L3 cache and memory controller bandwidth.

The document says "Store reset（清空 WASM 线性内存、重置 fuel counter、epoch deadline）" — but Wasmtime's `Store::reset()` may not actually zero the memory; it resets the instance state. The actual memory clearing behavior depends on Wasmtime's implementation.

**Recommendation**: 
- Verify with Wasmtime 30.0 whether Store reset actually zeroes linear memory or just resets the memory pointer
- If zeroing is required, consider using a pool of pre-zeroed memory regions (page-aligned, MADV_DONTNEED on Linux)

### Low

#### D8 — Reactive Admission Control Has No Hysteresis

**Severity**: Low  
**Location**: engine.md §3.4.2

The admission formula rejects new WASM execution when `effective_per_player_quota < MIN_FUEL` (500,000). This lacks hysteresis — if players join and leave rapidly, the system oscillates between accepting and rejecting. 

**Recommendation**: Add a hysteresis band: reject when quota < 500,000, but don't re-accept until quota > 750,000. This prevents flapping.

#### D9 — TickTrace WAL Write Could Block Under Load

**Severity**: Low  
**Location**: 01-tick-protocol.md §6.3.4

The WAL fallback path (3rd retry → write to local WAL) writes to a filesystem path `/var/lib/swarm/wal/ticktrace/`. If the filesystem is under I/O pressure (e.g., from ClickHouse ingestion or object store uploads), this local write could stall the tick loop.

**Recommendation**: Use `O_DIRECT | O_SYNC` with a separate I/O thread or `io_uring` for WAL writes. Specify that WAL write timeout is 10ms; if exceeded, skip WAL and escalate alert.

---

## 3. Strengths

1. **Two-phase snapshot architecture** (§2.3): One-time build + per-player view stitching reduces complexity from O(P×E) to O(E + P×R). This is the single biggest performance win in the design.

2. **FDB async blob upload (D5/B)**: Decoupling FDB commit from blob upload is correct — FDB transactions stay small (<1KB), blob upload failures don't block ticks. The upload_status tracking (pending→uploading→complete→failed) is comprehensive.

3. **WASM precompilation + pool**: Precompiling at deploy time eliminates JIT overhead during tick. The pool model with per-tick Store reset strikes the right balance between isolation (fork-per-tick too expensive) and performance.

4. **Fuel metering granularity**: 10M fuel units + per-host-function cost table (500 for terrain, 2000+100/entity for get_objects_in_range, 500×nodes for pathfinding) provides fine-grained resource accounting.

5. **COLLECT cache reuse across FDB retries**: Not re-executing WASM on FDB commit failure is correct — saves CPU and prevents double fuel charging.

6. **Performance contracts with CI regression**: Explicit p99 budgets in §3.4.1 with CI enforcement ("全部指标在 CI 中回归测试") — this is rare and valuable.

7. **Bevy ECS parallel sets**: Combat (S11-S13) partitioned by target_id and Status Effects (S16-S22) by subtype — good concurrency design with documented R/W matrices.

8. **Aggregate CPU admission formula**: `floor(2500ms × cores × 500 MIPS)` is a principled approach to capacity planning.

---

## 4. Scaling Limits

| Dimension | Current Limit | Bottleneck | Projected Ceiling |
|-----------|--------------|------------|-------------------|
| Active players | 500 target / 1000 hard | Worker pool depth (256 default) + snapshot stitching overhead | ~800 without architectural changes |
| Active drones | 5000 target / 10000 hard | FDB mutations per tick + snapshot size | ~8000 before 50ms FDB budget at risk |
| Total entities | 50000 | Bevy World snapshot deep copy | ~50000 (tight at 50ms budget) |
| Tick interval | 3000ms | COLLECT phase is the long pole | Can't go below 2000ms without significant optimization |
| Per-player WASM fuel | 10M | Effective at 1000 players with admission control | Scales down proportionally with player count |

**Horizontal scaling readiness**: The design acknowledges future horizontal sharding (§3.1a: "水平分片（多 Engine 实例）") but the single FDB cluster is the coordination bottleneck. Multi-engine would require cross-shard FDB transactions or a two-phase commit protocol — not designed yet, correctly deferred.

---

## 5. Concurrency Risks

| Risk | Location | Impact | Mitigation |
|------|----------|--------|------------|
| FDB transaction conflict on hot keys (Controller, RoomCap) | 01-tick-protocol.md §3.5 | Tick abandon if >3 retries | COLLECT cache reuse avoids WASM re-execution; but 3 consecutive abandons → degraded mode. RoomCap intermediate state protection in manifest helps |
| Worker pool contention at 256 limit | engine.md §3.4.2 | Players queued, COLLECT exceeds budget | Admission control prevents over-subscription; but see D2 |
| Dragonfly write contention | 01-tick-protocol.md §4.2 | Cache stale > 2 ticks | FDB is authoritative; cache miss → FDB read is acceptable |
| NATS fan-out congestion | 01-tick-protocol.md §4.2 | Client sees stale state | Client `last_tick` gap detection → fetch; designed correctly |
| Phase 2b parallel set data races | engine.md §3.2 | Non-deterministic execution | R/W matrix in manifest prevents races; CI deterministic replay catches violations |

---

## 6. CrossCheck

Issues I suspect but that fall outside the performance direction scope:

- **CX1**: Snapshot truncation priority buckets prioritize "self > friendly > enemy" but don't account for entity **threat level**. An enemy Tower (high threat) might be truncated before a friendly Road (low value). Truncation with threat-weighted ordering could improve survivability. → **Suggest Architect检查截断优先级是否应考虑实体威胁权重**

- **CX2**: The Bevy World snapshot captures component data but it's unclear if **Entity relationships** (parent/child, Controller→Room, Structure→Room) are preserved in the snapshot in a way that `world.restore(snapshot)` correctly reconstructs the archetype graph. A missing relationship edge would cause restore to create orphaned entities. → **Suggest Architect验证快照恢复的实体关系完整性**

- **CX3**: The Controller repair formula allows `repair_per_drone` age reduction per tick (engine.md §3.4.5) with a global cap of `floor(active_drones × 0.5)`. At 5000 drones, the cap is 2500 age reduction/tick, which could sustain ~2500 drones indefinitely if repair is well-distributed. This makes drone lifespan effectively unbounded under optimal repair. → **Suggest Gameplay检查维修公式是否使drone寿命无限延长**

- **CX4**: The `host_path_find` cache key is `(from, to, terrain_hash, player_visibility_fingerprint)`. Terrain changes (Construction, Rampart building) invalidate the cache. If terrain changes are frequent (e.g., Wall spam), the cache hit rate drops to near zero. → **Suggest Architect检查路径缓存失效频率及是否需要增量地形hash**

- **CX5**: WASM module deployment switches at tick N+1 boundary. If a player deploys a module at tick N and the module contains a critical bug fix, the player must wait a full tick. For competitive play, a "hot-reload" mechanism that applies mid-tick (with appropriate safety) might be needed. → **Suggest Interface/Architect评估是否需要mid-tick热重载**

