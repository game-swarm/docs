# Architect Review — Algorithmic / Logical Correctness Perspective

**Reviewer**: DeepSeek V4 Pro (Architect Secondary)
**Review date**: 2026-06-14

---

## VERDICT: REQUEST_CHANGES

The design has a sound conceptual skeleton, but the gap between the current Phase 1 placeholder code and the ambitious 7-phase plan is large, and several algorithmic and consistency hazards are unaddressed at the specification level. The most critical issues manifest in the ECS system scheduling, the tick lifecycle's interaction with Bevy internals, and the data consistency path between FoundationDB and Dragonfly. These are not implementation details — they are structural correctness concerns that will cause bugs systemically if not resolved in the design phase.

---

## STRENGTHS

1. **ECS Component decomposition is well-normalized.** The `Drone`, `Structure`, `Resource`, `Source`, `Terrain`, `Controller` components each represent orthogonal concerns. A drone doesn't carry its position in a field — it gets a separate `Position` component. This is correct ECS design and enables Bevy to parallelize queries on disjoint component sets.

2. **The three-phase tick abstraction is conceptually correct.** Collect → Execute → Broadcast is the standard pattern for multi-player turn-based simulation. The design document correctly separates: player code execution (side-effect-free snapshot → commands), deterministic command application, and output broadcast. This is the right decomposition for a replayable simulation.

3. **Determinism requirements are correctly identified.** The DESIGN explicitly calls out (Section 3.1.3): fixed system execution order, seeded PRNG (no OS entropy), and deterministic world state reproduction. This is the correct set of constraints for enabling replay and anti-cheat.

4. **WASM security layers are comprehensive.** L1-L6 (linear memory, WASI minimal, fuel metering, host allowlist, static scan, wall-clock timeout) form a complete defense-in-depth model. The fuel-metering choice for CPU accounting is mathematically preferable to wall-clock limits for fairness among language runtimes.

5. **The Command enum (game_api.rs) covers all game actions cleanly.** 15 variants encompassing movement, resource operations, construction, combat, spawning, and information queries. The separation of `Move` (one tile) from `MoveTo` (pathfinding) is correct — pathfinding is engine-side work, charged appropriately.

---

## CONCERNS

### D1 — ECS System Ordering Is Undefined and Dangerous

**Location**: `/data/swarm/engine/src/ecs/systems.rs:8-22`

Bevy will parallelize these systems automatically when they operate on disjoint component sets. But the component access patterns create invisible dependencies:

- `death_system` reads `Drone` and `Structure` — it must run AFTER `combat_system` has applied damage that reduces `hits` to zero. If Bevy schedules `death_system` before `combat_system`, entities that should die this tick survive.
- `regeneration_system` reads `Source` and `Controller` — it must run AFTER `harvest_system` has drained `Source.energy`. If it runs before, a source that was fully harvested still regenerates this tick.
- `movement_system` reads `Position` — it must run BEFORE `combat_system` if combat range is computed from positions. Otherwise a drone that moved into range can't be attacked on the same tick.

Without explicit `.chain()` or `.before()/.after()` constraints, the execution order is non-deterministic across Bevy releases and thread counts. The simulation will produce DIFFERENT world states from identical inputs on different hardware configurations. This directly violates the determinism guarantee.

**Recommendation**: Define system ordering with Bevy's system ordering API. Plausible ordering:
1. `build_system` (structures appear first)
2. `harvest_system` (resources drained)
3. `regeneration_system` (sources replenish after harvesting)
4. `movement_system` (drones move)
5. `combat_system` (attacks resolve)
6. `decay_system` (fatigue/cooldowns tick down)
7. `death_system` (dead entities cleaned up)
8. `spawn_system` (new entities created at end to avoid mid-tick targeting)

### D2 — Tick Lifecycle vs. Bevy's Update Model Are In Conflict

**Location**: `/data/swarm/engine/src/tick/mod.rs:6-22`

`app.update()` runs ALL registered systems in one atomic pass. The DESIGN's three-phase model (COLLECT parallel → EXECUTE sequential → BROADCAST) is at odds with this. Command application must happen BEFORE ECS systems run, but the current architecture has no mechanism to inject validated commands into the ECS world before `app.update()` fires.

**Recommendation**: Refactor tick lifecycle into:
1. Pre-ECS phase: Collect commands from all executors (WASM + MCP).
2. Inject validated commands into ECS world as Events or direct component mutations.
3. Call `app.update()` to run ordered ECS systems.
4. Post-ECS phase: Compute deltas, broadcast, persist.

### D3 — FoundationDB + Dragonfly Write Path Consistency Is Undefined

The design places FoundationDB as persistence and Dragonfly as hot cache. The write order is never specified. "Persist full world state snapshot to FoundationDB (every Nth tick)" — NOT every tick is persisted. If the engine crashes on tick 47 and last persisted is tick 40, ticks 41-47 are lost. A player who built a structure on tick 42 sees it vanish on recovery.

**Recommendation**: 
1. Engine writes to FoundationDB FIRST, then updates Dragonfly AFTER FDB transaction commits.
2. Specify N (persist frequency). N=1 for correctness; higher N is an optimization with documented data-loss consequences.
3. FoundationDB itself can serve as a cache — Dragonfly may be premature optimization.

### D4 — TOCTOU Gap in Command Validation

Player A sees drone X at position (5,3) and issues `attack {X}`. Player B issues `move {X, Top}` first (deterministic sort). Player A's attack targets a drone that moved. The DESIGN says "discard with rejection" but for attacks on moved targets — should it silently fail or retarget?

**Recommendation**: Per-command-variant failure conditions:
- Target destroyed → `TargetNotFound`
- Target moved out of range → `TargetOutOfRange` (don't silently retarget)

### D5 — WASM Fuel Metering vs. MCP Command Limits Are Not Mathematically Equivalent

WASM players have 10M fuel instructions. MCP AI players have UNLIMITED external compute behind a single API call. "Same command limit" restricts OUTPUT count, not INPUT compute. AI players can run optimal pathfinding on their own servers — asymmetric advantage.

**Recommendation**: Either:
1. Separate AI and human leaderboards, or
2. Impose token budget on AI players (max 4K input, 1K output per tick), or
3. Require AI players to submit WASM modules (AI writes code, not commands).

### D6 — Command Enum Confuses Mutations with Queries

`GetTerrain`, `GetObjectsInRange`, `PathFind` are QUERIES, not mutations. They introduce 1-tick latency (3s) for information that should be instantaneous. `PathFind` in the EXECUTE phase may blow the 0.5s budget.

**Recommendation**: Split `Command` into `Action` (mutating) and `Query` (read-only). Handle queries during snapshot generation in COLLECT phase, charged against player fuel.

---

## CONSISTENCY GAPS

### G1 — No Tick Atomicity Guarantee
If COLLECT succeeds for 50/100 players then engine crashes — are collected commands persisted or discarded? A tick must be ATOMIC: either all commands execute or none do. Requires FoundationDB transaction wrapping or snapshot-and-commit model.

### G2 — Determinism vs. AI Non-Determinism
AI players are inherently non-deterministic (LLM responses vary). Replay must LOG AI-generated commands, not re-call the AI. "Deterministic core" applies to ECS execution only, not input generation.

### G3 — Snapshot Serialization Cost Is Per-Player, Not Shared
If 100 players share overlapping visible regions, each gets separately serialized snapshot. O(P * V) cost. Should serialize ONCE per room and filter per-player.

---

## ALGORITHMIC RISKS

### R1 — Pathfinding Cost Amplification
50 drones × 50 path requests per player × 100 players = 12.5M node explorations per tick. Needs pathfinding result cache, flow-field approach, or per-player-per-tick pathfinding limit.

### R2 — Vision Computation Is O(D × E)
50 drones × 500 entities = 25K distance checks per player, 2.5M per tick for 100 players. Needs spatial index (quadtree/grid hash).

### R3 — Conflict Resolution Sorting Cost
If sort key is (player_id, command_index), high-player-id players have last-mover advantage in contested interactions. Sort key choice has game balance implications.

### R4 — Bevy's Parallel Scheduling Is Non-Deterministic
Even with `.before()/.after()`, Bevy's work-stealing may execute independent systems in different orders across runs. Cross-room interactions introduce cross-shard consistency issues.

---

## SUMMARY

| Category | Count | Severity |
|----------|-------|----------|
| Concerns (D1–D6) | 6 | 2 Critical (D1, D2), 3 High (D3, D4, D5), 1 Medium (D6) |
| Consistency Gaps (G1–G3) | 3 | 1 Critical (G1), 1 High (G2), 1 Medium (G3) |
| Algorithmic Risks (R1–R4) | 4 | 2 High (R1, R2), 2 Medium (R3, R4) |

The foundational ECS model and tick abstraction are correct. The primary gaps are in system ordering (D1), tick lifecycle integration with Bevy (D2), persistence consistency (D3/G1), and the fairness model between WASM and AI players (D5). These should be resolved at the design level before Phase 2 implementation begins.
