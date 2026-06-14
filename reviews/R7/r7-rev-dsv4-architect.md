# Architecture Review — Swarm Design

**Reviewer**: rev-dsv4-architect (DeepSeek V4 Pro)
**Direction**: Architect (Secondary)
**Date**: 2026-06-14
**Documents Reviewed**: DESIGN.md (full), tech-choices.md, ROADMAP.md, P0-1 through P0-9 (all 9 specs)

---

## Verdict: CONDITIONAL_APPROVE

The architecture is fundamentally sound with excellent separation of concerns, a robust deferred command model, and principled determinism guarantees. The three conditions below must be clarified before Phase 1 implementation begins; they are targeted questions, not redesigns.

---

## Strengths

1. **Deferred Command Model (P0-4 §3, DESIGN §5)**: The `tick(snapshot_json) → Command[]` pattern is the single best architectural decision in this design. It enforces a clean boundary between untrusted WASM code and the authoritative game state, eliminates TOCTOU races at the host function level, and makes replay trivial — just re-feed recorded commands. This is architecturally superior to Screeps' imperative host function model.

2. **Single Source of Truth via IDL (P0-8)**: `game_api.idl → codegen` for Rust/TS/MCP/Docs/Test is exactly right. Drift between Rust Command enum, TS SDK types, and MCP schemas is eliminated at compile time. The CI check (`git diff --exit-code` after `cargo run -- gen-api`) is the correct enforcement mechanism.

3. **Blake3 Monomorphic Primitive (tech-choices §8)**: Using Blake3 for hash + XOF PRNG + keyed MAC reduces the trusted code surface by one full crate (ChaCha). The `update_with_seek(seed, offset)` API for per-player per-tick deterministic randomness is elegant and avoids the complexity of managing a keystream. ~6 GB/s in pure software with no platform degradation is a real operational benefit.

4. **Tick Atomicity via FDB (P0-1 §3.4)**: Wrapping the entire EXECUTE phase in a single FDB transaction with strict serializability is the correct approach for deterministic replay. The tick abandon semantics (refund fuel, don't increment counter, retry with backoff) are well-specified. Degraded mode after 3 consecutive abandons is a pragmatic safety net.

5. **Source Gate (P0-9 §4)**: The explicit source matrix with capability constraints (`WASM` can write world, `MCP_Deploy` cannot submit gameplay commands) is the right defense-in-depth layer. Server-injected `player_id` (client cannot self-report) prevents the most common class of auth bypass.

6. **Visibility Caching (P0-5 §5)**: `is_visible_to(entity, player_id, tick)` as the single function called by all output surfaces (snapshot, MCP, WebSocket, REST, replay) eliminates the class of bugs where "snapshot hides it but WS delta leaks it." The cache key `(tick, player_id)` with next-tick invalidation is correct.

7. **Rhai Mod Budget System (DESIGN §8.7)**: AST node limit (10K/tick), actions limit (100/tick), wall-clock limit (100ms), and auto-disable after 10 consecutive over-limit ticks. This is the right multi-layered safety net for user-installable game logic running inside the engine process.

8. **Progressive Storage Tax (DESIGN §8.4)**: The three-pronged anti-dominant-strategy design (progressive tax tiers, local storage stealth advantage, transport time preventing teleport resupply) addresses a real economic game theory problem that most MMO economies ignore until it's too late.

---

## Concerns

### D1 [MEDIUM] — Snapshot Construction Scaling

**Location**: P0-1 §2.3, DESIGN §3.2 Phase 1

The optimization note says: "快照按房间序列化一次，再按玩家过滤——不是 O(P × E)." This is the right intention, but the implementation path is under-specified. With 500 concurrent players and 10,000+ entities per room, the filter step is O(E) per player even with a pre-serialized room snapshot — that's 500 × 10,000 = 5M entity checks per tick in the COLLECT phase.

The concern is not algorithmic correctness but whether the 2.5s COLLECT budget accommodates this at scale. Each filter involves room membership checks + vision range distance calculations + fog-of-war rules. At 5M checks in 2.5s, that's 500ns per check — feasible in Rust but needs benchmarking.

**Recommendation**: Add a Phase 1 deliverable: "Benchmark snapshot construction with 500 simulated players and 10,000 entities. Target < 500ms for the serialization + filter pipeline."

### D2 [MEDIUM] — Dragonfly Cache Rebuild Timing Gap

**Location**: P0-1 §4.2, §6.1 Failure Mode Matrix

The sequence in BROADCAST is:
1. Read committed tick result from in-memory state or FDB versionstamp
2. Dragonfly.update(delta)
3. NATS.publish(delta)

If step 2 fails (Dragonfly unreachable), the spec says "失败则从 FDB 重建." But when does the rebuild trigger — on the next cache miss, or proactively? If it's lazy (on next miss), there's a window where:
- Tick N is committed to FDB (authoritative)
- Dragonfly has tick N-1 state (stale)
- A WebSocket client that detected a NATS gap fetches current state → hits Dragonfly → gets tick N-1 data
- The client doesn't know it's stale because Dragonfly served "current" data

P0-1 §6.1 acknowledges "Dragonfly cache stale" as a failure mode but says "无——FDB 为权威源" and "下次写入时自动刷新." This doesn't cover the read path during the stale window.

**Recommendation**: Specify that Dragonfly reads for "current world state" include a versionstamp check. If the cached versionstamp < FDB latest committed versionstamp, fall back to FDB. This can be a single FDB read of `/tick/current` and comparison against Dragonfly's `last_tick` key.

### D3 [LOW] — Rhai Engine Version Not Pinned for Replay

**Location**: DESIGN §8.8 Determinism Contract

The determinism contract states: "给定 tick N-1 状态 + tick N RawCommand + world_seed + 激活模组列表 → 相同 Wasmtime pinned 版本下 execute_deterministic == recorded_state."

Wasmtime version is pinned (`wasmtime = "=30.0"` in P0-4 §2.1), but the Rhai engine version is not mentioned in the pinning contract. The Rhai crate has its own version that could change AST interpretation semantics across upgrades. If a server upgrades the Rhai dependency between recording and replay, `tick_end.rhai` could produce different results.

**Recommendation**: Pin Rhai version in Cargo.toml alongside Wasmtime, and include the Rhai version in the replay determinism preconditions. Alternatively, record the mod actions output (not just the scripts) in TickTrace so replay feeds recorded actions rather than re-executing Rhai.

### D4 [MEDIUM] — Tutorial Source Isolation Inconsistency

**Location**: P0-9 §2.1 vs §2.4

The source matrix (§2.1) includes `Tutorial` source with `visibility: 教程房间`. But §2.4 states: "Tutorial 来源的指令仅可在 `world.mode = "tutorial"` 的世界中接受。在非 Tutorial 世界收到的 Tutorial 来源指令 → 静默丢弃 + 记录审计日志."

The question: can a tutorial world have multiple concurrent tutorial sessions from different players? If so, the isolation model needs clarification — are tutorial sessions per-player (separate worlds) or shared (one world, multiple tutorial players)? The "独立 namespace (`tutorial_{world_id}`)" in §2.4 suggests shared, but the source matrix shows per-session `auth_context: tutorial_session + world_id`.

If tutorials are per-player isolated worlds, the Source Gate should enforce `Tutorial` source only within the session's assigned namespace, not just "world.mode = tutorial." If they're shared, visibility and resource isolation between tutorial players must be defined.

**Recommendation**: Clarify whether tutorial worlds are per-player or shared, and update P0-9 §2.4 accordingly.

### D5 [LOW] — ECS System Order: Spawn at Chain End

**Location**: P0-1 §3.3, P0-2 §3.10

The ECS chain is: build → harvest → regeneration → movement → combat → decay → death → spawn. P0-2 §3.10 confirms "Drone 在 tick 末尾创建（death_system 之后，spawn 槽位已释放）."

This is correct — newly spawned drones cannot act in their creation tick. But there's a subtle interaction: the Spawn COMMAND is validated and applied during the sequential command execution phase (before ECS systems run). The spawn_system in the ECS chain presumably handles the actual entity creation. This split between "command application" and "ECS system execution" for the same operation is architecturally awkward.

The design intent (prevent same-tick action by newborns) is correct. The concern is that the implementation boundary between command application and ECS spawn_system is not clearly specified.

**Recommendation**: Add a note in P0-1 §3.3 clarifying that Spawn commands create a "pending spawn" record during command application, and the spawn_system materializes the entity at chain end. This makes the two-phase nature explicit.

### D6 [LOW] — In-Transit Resource Data Model Undefined

**Location**: DESIGN §8.4, P0-8 IDL

The transfer system introduces "运输中" (in-transit) resources with a tick-based delay. The IDL defines `TransferToGlobal` and `TransferFromGlobal` commands with `duration` fields. But the data model for in-transit resources — where are they stored, how are they represented in snapshots, can they be intercepted (Phase 6) — is not defined in any P0 spec.

P0-8 mentions `transfer_time_remaining(0)` as a validator check, implying some state tracking. But the snapshot structure (P0-5 §3.1) does not include an `in_transit` or `pending_transfers` field.

**Recommendation**: Define the in-transit resource data model in a P0 spec appendix or a new P0-10. At minimum: storage location (FDB key pattern), snapshot representation, and the skeleton for Phase 6 interception.

---

## Consistency Gaps

### G1 — Tick Output Schema: "additionalProperties: false" vs Extensible Commands

**P0-2 §1.1**: "additionalProperties: false — 拒绝未知顶层字段"
**P0-8 IDL**: Commands have structured params but no explicit `additionalProperties` policy

The tick output JSON schema rejects unknown fields at the top level. But individual command objects within the array — do they also reject unknown fields? The IDL doesn't specify this. A WASM module that adds an extra field to a Move command (e.g., `{"type": "Move", "object_id": 1001, "direction": "TopRight", "_debug_note": "test"}`) might pass schema validation but could indicate a buggy codegen.

**Recommendation**: Either (a) add `additionalProperties: false` at the per-command level, or (b) explicitly document that extra command fields are silently ignored, with the rationale.

### G2 — WASM Module Version Switching: Atomicity Boundary

**P0-1 §2.4**: "引擎在下一 tick 加载新模块...切换是原子的"
**P0-4 §1**: "sandbox worker 进程每 tick 新 fork"

The module switch is atomic at the tick boundary. But within a tick, all players' WASM modules are loaded from the engine's module cache. If a deploy happens during COLLECT phase for player A while player B's WASM is already executing with the old module, there's no race — the new module takes effect next tick for all players.

But the "原子" claim needs clarification: does the engine pre-load all modules for the upcoming tick BEFORE starting any sandbox worker? If it loads lazily (when each worker starts), two workers for the same player in the same tick could theoretically get different module versions if a mid-tick deploy is processed between their starts.

**Recommendation**: Explicitly state that module resolution for all players happens once at tick start (before COLLECT phase begins), and the resolved module hashes are fixed for the entire tick.

### G3 — Refund Policy: "MAX_FUEL" Value Not Normalized Across Docs

**P0-2 §7.3**: "MAX_FUEL × 10%...当前为 1,000,000 fuel 上限" (implying MAX_FUEL = 10,000,000)
**P0-4 §6**: "Fuel（CPU 指令）: 10,000,000"
**DESIGN §3.2**: No explicit fuel value mentioned

The implied MAX_FUEL = 10M is consistent between P0-2 and P0-4. But it only appears as a comment in P0-2 §7.3 ("当前为 1,000,000 fuel 上限" — this says 1M, which contradicts the 10% × 10M = 1M calculation). The refund cap value in the text is correct (1M = 10% of 10M) but the phrasing is misleading.

**Recommendation**: Define MAX_FUEL as a named constant in P0-4 §6 and reference it by name in P0-2, rather than using inline calculations.

---

## Algorithmic Risks

### R1 — Path Finding at Scale

**Scope**: P0-2 §4.3, P0-4 §8

Per-player per-tick: 10 path_find calls. With 500 players: 5,000 path calculations per tick. Each path_find operates on a room grid (max 128×128 = 16,384 tiles) with A* or similar. At 10,000 fuel + 50/tile, a 100-tile path costs 15,000 fuel units (~0.15% of budget). The wall-clock cost at scale is the concern — 5,000 A* runs in a 3-second tick window.

The spec mentions caching: "结果以 (from, to, 地形hash) 缓存 — 地形不变不重算." This helps if players repeatedly path the same routes. But in practice, dynamic worlds with moving entities will have cache misses. The worst case (5,000 uncached paths) needs benchmarking.

**Risk Level**: LOW — Rust A* on 16K-node grids is fast. But deserves a load test milestone.

### R2 — Command Queue Sorting Overhead

**Scope**: P0-1 §3.1

The seeded shuffle is O(P) for P players — trivial. The command queue merge is: for each player, sort their commands by sequence (O(C_p log C_p)), then interleave by shuffle order. Total: O(P log P + sum(C_p log C_p)). With P=500 and C_p≤100, this is ~500×log(500) + 500×100×log(100) ≈ 500×9 + 500×100×7 ≈ 350K operations. In Rust, this is sub-millisecond. Not a real risk.

### R3 — Visibility Cache Memory

**Scope**: P0-5 §5

Cache key: (tick, player_id). Cache value: HashSet<EntityId>. With 500 players and average 200 visible entities per player (8 bytes per EntityId), that's 500 × 200 × 8 = 800KB per tick. The cache is invalidated next tick, so worst-case memory is ~1.6MB (current + next tick being computed). Negligible.

### R4 — FDB Transaction Size

**Scope**: P0-1 §3.4

The FDB transaction per tick includes: world state delta, all commands, all rejections, and metrics. With 500 players × 100 commands = 50,000 commands, each RawCommand is ~200 bytes (JSON). That's ~10MB of command data plus state delta plus rejection records. FDB's transaction size limit is 10MB by default. 50,000 commands at 200 bytes = 10MB exactly at the limit.

If the state delta is also included in the same transaction, this could exceed FDB's transaction limit.

**Risk Level**: MEDIUM — needs sizing analysis. Consider splitting commands/rejections into a separate sub-transaction or using FDB's bulk loading patterns. Alternatively, store commands as a compressed blob and only expand for replay.

---

## Cross-Spec Verification

| Claim in DESIGN | Verified in P0 | Status |
|-----------------|----------------|--------|
| "Deferred command model — tick() → JSON" | P0-4 §3, P0-2 §1 | ✅ Consistent |
| "MCP is management interface, not gameplay controller" | P0-3 §4.5, P0-9 §2.3 | ✅ Consistent |
| "WasmSandboxExecutor is the ONLY executor" | P0-1 §2.1 | ✅ Consistent |
| "Seeded shuffle for fair player ordering" | P0-1 §3.1 | ✅ Consistent |
| "FDB atomic commit per tick" | P0-1 §3.4 | ✅ Consistent |
| "Dragonfly is non-authoritative cache" | P0-1 §4.2, §6.1 | ✅ Consistent |
| "Blake3 for hash + PRNG + signing" | DESIGN §8.8, tech-choices §8 | ✅ Consistent |
| "Rhai mods with budget limits" | P0-7 §1, DESIGN §8.7 | ✅ Consistent |
| "12 command sources in Source Gate" | P0-9 §2.1-2.2 | ✅ Consistent |
| "Progressive storage tax tiers" | DESIGN §8.4 | ⚠️ Only in DESIGN, not in any P0 spec |
| "ECS system order .chain()" | P0-1 §3.3, P0-2 §3.10 | ✅ Consistent |
| "New drone created at tick end" | P0-2 §3.10, P0-1 §3.3 | ✅ Consistent |
| "fuel metering + epoch interruption" | P0-4 §2.2 | ✅ Consistent |
| "Per-tick fork lifecycle" | P0-4 §1 | ✅ Consistent |

---

## Conditions for Approval

1. **Clarify snapshot construction scaling** (D1): Add a Phase 1 benchmark deliverable for 500-player / 10K-entity snapshot filtering. If the benchmark shows >500ms for the filter pipeline, the design needs a spatial index optimization before proceeding.

2. **Close the Dragonfly read-path staleness window** (D2): Add a versionstamp check to Dragonfly read path, or explicitly document the staleness window duration and its user-visible effects.

3. **Pin Rhai version in the determinism contract** (D3): Either pin the Rhai crate version alongside Wasmtime, or record mod action outputs in TickTrace instead of re-executing Rhai scripts during replay.

These are clarifications and benchmark gates, not architectural changes. None of them block the Phase 1 MVP — they can be addressed in parallel with initial engine scaffolding.

---

*Review methodology: Deep reasoning chain covering ECS scheduling correctness, tick lifecycle completeness, FDB+Dragonfly data consistency, and algorithmic scaling bounds. Cross-referenced all 9 P0 specs against DESIGN.md claims.*
