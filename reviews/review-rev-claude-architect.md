# Architect Review — Structural Perspective

**Reviewer**: Claude Opus 4.8 (Architect Primary)
**Review date**: 2026-06-14
**Documents reviewed**: DESIGN.md (658 lines), PLANNER-OUTPUT.md, engine source (9 Rust files)

---

## VERDICT: REQUEST_CHANGES

The Swarm design is directionally sound — WASM multi-language, ECS determinism, and MCP-native AI players are the right bets. However, the gap between the architectural ambition and the Phase 1 skeleton is large, and three structural decisions need to be resolved before Phase 2 implementation begins: (1) the MCP server embedding model, (2) the PlayerExecutor abstraction's completeness, and (3) the tick lifecycle's integration with Bevy internals. These are not implementation details — they are architectural choices that will be expensive to change later.

---

## STRENGTHS

1. **Clean separation of concerns in the ECS model.** Each component (Drone, Structure, Resource, Source, Terrain, Controller) represents an orthogonal dimension. Position is a separate component, not embedded in Drone. This enables Bevy's parallel query execution and is architecturally correct.

2. **The three-phase tick abstraction is well-chosen.** COLLECT (parallel, snapshot→commands) → EXECUTE (sequential, validate→apply) → BROADCAST (delta push) is the canonical architecture for deterministic multiplayer simulation. It cleanly separates the non-deterministic input generation from the deterministic world mutation.

3. **WASM as the universal player runtime is the right long-term bet.** Language-agnostic, fuel-metered, deterministically executable. The 6-layer security model (L1-L6 from DESIGN) is comprehensive and defense-in-depth.

4. **MCP as first-class player interface, not bolt-on.** The PLAN correctly elevates MCP from a documentation-afterthought to a core player surface. The PlayerKind enum (Human/Ai) and the PlayerExecutor abstraction are the correct architectural moves.

---

## CONCERNS

### A1 — MCP Server Embedded in Engine Process Creates an Architectural Knot

**The plan**: Phase 1.2 embeds an MCP server (rmcp) as a Tokio task inside the engine binary, serving HTTP/SSE on a configurable port.

**Why it's architecturally risky**:
- **Blast radius**: If the MCP server panics (malformed request, DoS, memory exhaustion), it takes down the game engine. 10,000 players' ticks stop because one AI player's MCP client sent a malformed message.
- **Scaling asymmetry**: AI players may grow 100x faster than WASM players. When AI traffic saturates the MCP server, it starves the tick scheduler of CPU. The embedded model makes it impossible to scale AI serving independently.
- **Deployment coupling**: Updating the MCP server (e.g., rmcp version bump, CVE patch) requires restarting the entire engine. This is tolerable in Phase 1-2, but unacceptable in production with persistent world state.
- **The PLAN acknowledges this risk (Q4: "Embedded for MVP") but defers the decision to Phase 7.** By Phase 7, the MCP server has been embedded for 6 phases. Extracting it then is a major refactor, not a config change.

**Recommendation**: Extract the MCP server as a separate service (`swarm/mcp-server/`) by Phase 3 at the latest. The engine communicates with it via gRPC (defined in a shared protobuf contract). This aligns with the gateway pattern already in the architecture. The embedded model is acceptable for Phase 1-2 development only, with an explicit plan to extract.

### A2 — PlayerExecutor Trait Is Under-Specified for Hybrid Players

**Current design**: `PlayerExecutor` trait with `execute_tick(snapshot: &str) -> Vec<Command>` and `player_kind() -> PlayerKind`.

**Architectural gap**: The real world has HYBRID players — an AI agent that ALSO runs WASM modules, or a human who uses AI-assisted coding. The current PlayerKind enum (Human | Ai) is a false dichotomy.

More critically, the trait assumes:
1. All executors are pull-based (engine pushes snapshot, executor returns commands). The PLAN Q1 acknowledges bidirectional MCP but doesn't encode it in the trait.
2. All executors complete within one tick. What about an AI player whose external model takes 3 ticks to respond? The commands arrive late — are they queued for the next tick or discarded?
3. No error recovery contract. If `execute_tick` returns `Err`, should the engine retry? Fall back to previous commands? Skip the player?

**Recommendation**:
1. Add an `ExecutorCapability` enum: `Synchronous` (WASM, completes in-tick) | `Asynchronous` (MCP, may deliver commands for future ticks) | `Hybrid` (both).
2. Add a command queue per player: `submit_commands(tick: u64, commands: Vec<Command>)` for async delivery.
3. Define the error contract: `RetryableError` (transient, retry next tick) vs `FatalError` (player suspended, requires manual intervention).
4. Make `PlayerKind` non-exhaustive: add `Ai { model, provider }` and `Hybrid { wasm_module, mcp_endpoint }`.

### A3 — Tick Lifecycle Doesn't Handle Partial Tick Failure

**The DESIGN's three-phase tick**: COLLECT all → EXECUTE all → BROADCAST all.

**What's missing**: What if COLLECT succeeds for 50 of 100 players, then the engine's MCP client times out on player 51? Is the tick abandoned? Partial? Does the engine retry just player 51?

The DESIGN says nothing about tick atomicity. In a database, a transaction either commits or rolls back. In a game tick:
- If only 50% of players submit commands, should the tick proceed for those 50 and the other 50 get "no commands this tick" (fail-open)?
- Or should the tick be delayed until all players respond (fail-closed, risking deadlock)?
- Or should there be a soft deadline after which late players are skipped (fail-partial)?

**Recommendation**: Add to the DESIGN:
- A tick timeout (`tick_collect_timeout_ms`, default 2500ms). After this, any player that hasn't responded is treated as submitting `[]` (no commands).
- A tick health metric: `tick_completion_rate` (fraction of expected players who submitted). If this drops below 90%, alert.
- Explicitly document the fail-open semantics: a stuck player does not block the world.

### A4 — Room Sharding Introduces Cross-Shard Consistency Without a Protocol

**The PLAN (Phase 3.7, 7.2)**: Room-boundary partitioning and room-level sharding for performance.

**Architectural problem**: When a drone moves from Room A to Room B, the drone's components (Position, Drone, Owner, etc.) must atomically transfer from Shard A to Shard B. This is a distributed transaction across shards. The DESIGN mentions room boundaries but not the cross-shard protocol:
- Is there a global tick counter per shard, or one global tick counter?
- How does Shard A tell Shard B "this drone is now yours"? Message queue? Shared FoundationDB?
- What happens if Shard A crashes mid-transfer?

**Recommendation**: Add a "Cross-Shard Entity Transfer" section to the DESIGN before Phase 3.7 begins. Options:
1. **Single global tick, per-shard state**: Simplest. Each shard owns a subset of rooms. Cross-room movement is just a RoomId field update within the same shard. Only shard when rooms don't share borders.
2. **Two-phase transfer**: Shard A marks drone as "departing", sends message to Shard B, Shard B acknowledges, Shard A deletes. But this spans two ticks (not atomic within one tick).
3. **Global ECS**: Don't shard ECS. Shard only the COLLECT phase (WASM execution). The ECS world is a single logical unit. This is the safest architectural choice for correctness.

### A5 — FoundationDB as Persistence Layer Creates a Single Point of Coupling

**The DESIGN**: FoundationDB for world state persistence (Section 4.1), Dragonfly for hot cache (4.2), ClickHouse for analytics (4.3).

**Architectural concern**: FoundationDB is a niche database with a small operational community. If the project is MIT-licensed and aims for community self-hosting, requiring FoundationDB is a high barrier:
- FoundationDB requires a cluster (not a single binary like SQLite or RocksDB).
- Operational expertise is scarce compared to PostgreSQL or etcd.
- The DESIGN doesn't specify a storage abstraction layer — engine code will be directly coupled to FoundationDB's API.

**Recommendation**: Define a `WorldStore` trait:
```rust
trait WorldStore {
    async fn save_tick(&self, tick: u64, state: &WorldSnapshot) -> Result<()>;
    async fn load_latest(&self) -> Result<(u64, WorldSnapshot)>;
}
```
Implement FoundationDB as the production backend, but provide a file-based backend (RocksDB or SQLite) for development and small-scale self-hosting. This keeps the architecture portable.

---

## MISSING

1. **No hot-reload for WASM modules.** Players update their code → how does the engine pick up the new WASM? Full restart? In-place module swap? The DESIGN says nothing about code deployment lifecycle.
2. **No observability architecture.** The PLAN mentions ClickHouse metrics (Phase 3.5) and debug traces (Phase 1.4), but there's no overall observability design: structured logging format, trace IDs across services, OpenTelemetry integration.
3. **No migration strategy for world state.** When the ECS component schema changes (new field, renamed component), how does the engine migrate persisted state from FoundationDB?
4. **No rate limiting architecture.** The PLAN mentions "rate limiting per AI session" but doesn't define the rate limiter: token bucket? Sliding window? Where does it live — gateway or engine?

---

## PHASE ORDERING

The 7-phase ordering is mostly correct, with two adjustments:

1. **Phase 4 (Debugging) should partially precede Phase 3 (Multi-Player).** Debugging a multi-player world without tick traces is nearly impossible. Move 4.1 (per-tick logging) and 4.2 (state inspection) to Phase 2.5 — before multi-player testing begins.

2. **Phase 3.3 (FoundationDB) should be deferred to Phase 4.** Multi-player can work with in-memory state + file-based persistence during development. FoundationDB as a hard dependency in Phase 3 will slow down iteration. Implement against the `WorldStore` trait with a file backend first.

---

## SUMMARY

| Category | Count |
|----------|-------|
| Concerns (A1–A5) | 5 (all High) |
| Missing | 4 |
| Phase Ordering Issues | 2 |

The architecture is on the right track. Resolve A1 (MCP extraction plan), A2 (PlayerExecutor completeness), and A3 (tick failure semantics) at the design level before Phase 2 implementation. The remaining issues can be addressed as the codebase grows.
