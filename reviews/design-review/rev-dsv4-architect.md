# Swarm Design Review — Architect (DeepSeek V4 Pro)

> **Reviewer**: rev-dsv4-architect
> **Direction**: Architecture
> **Date**: 2026-06-15
> **Documents Reviewed**: DESIGN.md (1988 lines), P0-1 Tick Protocol, P0-5 Visibility Policy

---

## VERDICT: CONDITIONAL_APPROVE

The design is architecturally sound at its core. The deferred command model + WASM sandbox, deterministic ECS pipeline, dynamic resource system, and extensible World Rules Engine form a coherent foundation. No fundamental architectural flaw was found.

However, **six issues must be resolved before Phase 1 implementation**, and four concerns should be tracked as implementation risks. The primary gap is the multi-shard MMO scalability model, which is mentioned in the deployment diagram but never explained in design terms.

---

## STRENGTHS

**S1. Deferred Command Model is architecturally correct.** The `tick(snapshot) → Command[]` model cleanly separates read-only perception from mutating action, prevents WASM modules from directly manipulating world state, and enables deterministic replay. This is the single most important architectural decision and it's right.

**S2. Determinism contract is thorough and implementable.** Blake3 XOF for PRNG, IndexMap for ordered collections, no f64, `.chain()` for ECS ordering — every source of non-determinism is explicitly addressed. The seed rotation strategy (every 10,000 ticks) is a nice touch that prevents long-term seed inference.

**S3. Resource model is genuinely dynamic.** The engine operates on `HashMap<ResourceName, Amount>` rather than hardcoding Energy. This enables StarCraft-style dual-resource economies, Age of Empires multi-resource worlds, or cyberpunk-themed CPU/Bandwidth economies — all through TOML configuration without engine changes. This is rare and well-executed.

**S4. Global storage anti-snowball mechanisms are well-designed.** The progressive storage tax, stealth advantage of local storage, and transport-time delays create a rich strategic layer without arbitrary caps. The three-tier logistics model (none/light/hardcore) lets world operators tune the economic complexity.

**S5. Body part → CommandAction binding is extensible.** Separating body part definitions (TOML) from command action handlers (Rust/Rhai) means new body parts can reuse existing actions, and truly new actions can be registered through the special effects system. Good separation of concerns.

**S6. Rhai mod execution model has correct transactional isolation.** Buffering actions and applying atomically after script completion (`actions.apply(world)`) avoids partial state corruption on timeout. The 100ms wall-clock budget with full rollback is the right approach.

**S7. Visibility model (P0-5) has a single source of truth.** `is_visible_to(entity, player_id, tick)` as the one function all output surfaces call — no backdoors. The separation between drone perception (WASM snapshot, game fairness) and player view (screen/MCP, spectator experience) is clean.

---

## ISSUES — REQUIRED RESOLUTION (D1–D6)

### D1 [MAJOR] Multi-Shard MMO Model is Undefined

**Location**: §7.2 (Deployment Architecture), cross-cutting

The deployment diagram shows "Engine (每 shard 一个实例)" with a NATS cluster and FDB cluster behind it. This implies a sharded architecture for MMO scale. But the design says **nothing** about:

1. **Shard assignment**: How are players assigned to shards? By room? By geographic region? By player ID hash? The choice has profound implications for gameplay (can two friends play in the same room if they're on different shards?).

2. **Cross-shard interaction**: Can a drone on shard A attack a drone on shard B? If yes, how are cross-shard commands ordered deterministically? The current Phase 2 design assumes a single engine with a seeded shuffle over all players — this breaks with multiple independent engines.

3. **Cross-shard consistency**: If shards are isolated (no cross-shard interaction), each shard is essentially a separate world. This isn't an MMO — it's a collection of parallel single-server instances.

**Required**: Add a §7.3 or new §12 defining the sharding model:
- Option A: "Rooms as shards" — each room is fully contained on one shard, with no cross-room interaction except market/trade (which can be cross-shard since it's FDB-backed).
- Option B: "Single world, single engine" — the engine is vertically scaled, not sharded. The diagram shows multiple engines for HA (active-passive), not for horizontal scaling.
- Option C: "Region sharding with cross-shard protocol" — define a deterministic cross-shard command ordering protocol.

**Recommendation**: For Phase 1–3, go with Option B (single engine, vertical scale). Document that horizontal sharding is a Phase 7+ concern. The FDB cluster + tuned Rust engine can handle significant scale before sharding is needed.

### D2 [MAJOR] Phase 2a vs 2b Boundary is Underspecified

**Location**: §3.2 (Tick Lifecycle), §8.4 (ECS Integration)

The design splits command execution into:
- **Phase 2a**: Inline command execution — Move, Harvest, Build, Transfer, Attack, Heal, Recycle are applied immediately via "对应 ECS system"
- **Phase 2b**: Deferred ECS systems — Spawn (deferred from 2a), combat, regeneration, decay, death

The problem: **there is no stated principle for what goes where.** Spawn is deferred "for room cap coordination" — but so is Build (which also has `max_per_room` constraints). Combat is deferred to 2b, but Attack commands go through 2a inline. What happens?

Specifically:
- Attack command in 2a reduces target HP → combat_system in 2b processes damage again? Or is the Attack in 2a a "damage application" and combat_system handles something else (Tower auto-attacks, passive damage)?
- Move in 2a changes entity position → regeneration_system in 2b runs on the new position. This is correct behavior but should be stated explicitly.
- If a Move command in 2a moves a drone into Tower range, the Tower's auto-attack happens in combat_system (2b) — same tick. Is this intentional? The timing creates interesting gameplay but isn't documented.

**Required**: Add a design principle for what goes inline (2a) vs deferred (2b):
```
2a (Inline): Commands whose effect depends on execution order and where
  "first-come-first-served" competition matters (harvest, build, move).
  These are player-submitted commands processed in shuffle order.

2b (Deferred): Passive systems that run uniformly on all entities, or
  commands that require cross-entity coordination (spawn needs room cap,
  combat needs simultaneous damage+heal resolution).
```

Then audit each command type against this principle and document the rationale.

### D3 [MAJOR] Spawn Room Cap Has a Race Condition

**Location**: §3.2 Phase 2a/2b, §3.1 Controller Upgrade Table

Phase 2a: Spawn commands are validated (room has capacity) but not executed.
Phase 2b: `spawn_system` creates drones. `death_mark_system` runs before `spawn_system` to free room cap slots.

The race: If room cap is 50, current drone count is 49, and two players each submit a spawn command for that room. Phase 2a validates both as legal (49 < 50). Phase 2b tries to create both. The second one (by shuffle order) fails because cap was exhausted by the first.

**This is fine behavior** — first-come-first-served. But the design document doesn't state:
1. That this race is intentional and unavoidable
2. What RejectionReason is returned (suggest: `RoomCapExceeded`)
3. Whether the failed spawn refunds resources (should it? The command was "valid when submitted" but "invalid when executed")

**Required**: Document the spawn race explicitly in §3.2 Phase 2b `spawn_system` description. Add resource refund behavior: spawn cost is deducted only on successful creation in 2b, not during 2a validation.

### D4 [MEDIUM] Controller Lifecycle Has Undefined Edge Cases

**Location**: §3.1 (Controller struct, Upgrade Table)

1. **Downgrade timer reset on ownership change**: The Controller has `downgrade_timer` (default 5000 tick). If Player A loses ownership and the timer starts counting down, then Player B claims it — does the timer reset? Presumably yes, but not stated.

2. **Upgrade progress conversion rate**: "每 tick 自动转换为 progress" — what's the conversion rate? Is it 1 energy → 1 progress? All energy deposited? Capped per tick? Not specified.

3. **Partial downgrade**: If downgrade_timer reaches 0, the Controller drops one level and progress resets to 0. But what if players are actively depositing resources during the downgrade countdown? Do deposits pause the timer? Extend it?

4. **Minimum level on downgrade**: Can a Controller downgrade below level 1? What happens? Is it destroyed?

5. **Claim timing**: The Claim body part is defined (§8.2) but theController claim mechanics aren't specified. How many claim ticks to capture? Does the existing owner's controller resist? Is there a claim cooldown?

**Required**: Add a Controller Lifecycle subsection (§3.1.1) covering: upgrade conversion rate, downgrade semantics (including partial deposits), claim mechanics, and minimum level behavior.

### D5 [MEDIUM] Drone Lifespan Extension Has Floor Ambiguity

**Location**: §8.2, Drone Lifecycle rule

The rule: "玩家拥有的每个 Controller 每 tick 给全局所有 drone 回退 age 0.5 tick（多 Controller 可叠加，上限为完全抵消自然 age 增长）"

Two issues:

1. **Floor behavior**: If a player has 3 Controllers, the reduction is 1.5/tick, capped at 1.0 (matching natural +1 increase). So age is frozen at 0 net change. But does age go below 0? If a drone starts at age 0 and has 2 Controllers, the reduction is 1.0 — does age stay at 0 or go to -1? If negative ages are allowed, drones could "bank" youth during peaceful periods.

2. **Global scope intentionality**: The rule says "全局所有 drone" — a Controller in room A extends the lifespan of drones in room B. This is a significant design choice that should be explicitly called out. It means Controllers act as a global infrastructure investment rather than per-room assets. The strategic implications: concentrating Controllers in safe rooms sustains an empire's entire drone fleet.

**Required**: Specify floor behavior (recommend: `age = max(0, age + 1 - min(1.0, 0.5 * controller_count))`). Document the global scope as an intentional design choice with its strategic implications.

### D6 [MEDIUM] FDB Commit Failure Recovery is Undefined

**Location**: §3.2 Phase 2 (EXECUTE), P0-1 §3.5

The design says "FDB 原子提交（全或无）" at the end of Phase 2. But:

1. **What happens if the commit fails?** Does the engine retry? How many times? With what backoff? If the commit fails after 3 retries, does the engine crash? Skip the tick? Enter a degraded mode?

2. **Tick counter advancement**: "tick_counter 推进" — is this incremented before or after the FDB commit? If after: a failed commit means tick_counter doesn't advance, and the next attempt re-uses the same tick number (correct for determinism). If before: a partially-written tick with a gap in tick numbers.

3. **BROADCAST phase dependency**: Phase 3 runs after successful FDB commit. If commit fails, does Phase 3 still run (broadcasting a "no change" delta)? Or is the entire tick abandoned?

P0-1 §3.5 mentions "tick abandon behavior" but only in the Phase 0 checklist — the actual behavior isn't specified.

**Required**: Add §3.2.1 "Tick Atomicity & Failure Recovery":
```
FDB commit failure:
  1. Retry up to 3 times with exponential backoff (100ms, 200ms, 400ms)
  2. If all retries fail: tick is ABANDONED
     - tick_counter does NOT advance
     - No state changes are persisted (world state remains at tick N-1)
     - All collected commands are discarded
     - Next attempt re-executes as tick N with fresh snapshots
  3. Abandoned tick → NATS alert → operator notification
  4. Consecutive abandoned ticks (3+) → engine enters degraded mode
```

---

## CONCERNS — TRACK DURING IMPLEMENTATION (C1–C4)

### C1 [LOW] Phase 2 Serial Execution Bottleneck at Scale

The design budgets 500ms for serial command execution in Phase 2. At 1000 players × 50 drones each = 50,000 drones, each potentially issuing multiple commands. If command validation + application takes even 10μs per command, that's 500ms just for 50,000 single commands. Real commands involve path checking, collision detection, resource validation — more like 50–100μs each.

This is a Phase 7 concern but should be tracked. Potential mitigations:
- Batch validate then apply (not one-at-a-time)
- Parallelize non-conflicting commands within a single tick (commands targeting different rooms don't conflict)
- Use `before()/after()` for partial ECS parallelism in Phase 2b

**Rating**: Not blocking. The single-engine model is correct for MVP. Track as a scalability gate before production.

### C2 [LOW] Dragonfly Cache Consistency Model

The design uses Dragonfly as a hot cache (Phase 3 update after FDB commit) and the gateway reads from it for WebSocket deltas. Questions to resolve during implementation:

1. **Cache miss fallback**: If Dragonfly is empty (cold start, eviction), does the gateway fall back to FDB reads?
2. **Read-your-own-writes**: After a player's command is executed in tick N, and they query state in tick N+1 through REST API, do they see consistent results? (FDB commit is durable, Dragonfly is eventually consistent.)
3. **Cache invalidation**: Is Dragonfly updated atomically with FDB? Or is there a window where FDB has tick N but Dragonfly still has tick N-1?

**Recommendation**: Dragonfly should be treated as a read-through cache with FDB as the authority. Gateways should fall back to FDB on cache miss. Cache population happens synchronously after FDB commit (not async in Phase 3) to minimize the inconsistency window.

### C3 [LOW] Overload Fuel Reduction Timing

**Location**: §8.2 Special Attacks table

Overload "消耗目标计算配额。目标 fuel budget 减少 500k". The fuel budget is consumed during Phase 1 WASM execution. But Overload is a command submitted in Phase 1 and applied in Phase 2. The target's WASM already executed in the current tick.

**Question**: Does the fuel reduction apply to the *next* tick's execution? This is the only sensible interpretation (the target has already used its current tick's budget) but should be stated explicitly in the Overload description.

### C4 [LOW] Death Mark Mid-Tick Targetability

**Location**: §3.2 Phase 2b ordering

`death_mark_system` marks entities for death but `death_cleanup_system` (which actually despawns them) runs last in the chain. Entities marked for death in 2b are still valid targets for commands processed inline in 2a — because 2a runs before 2b. But within 2b itself, entities marked by `death_mark_system` could theoretically be targeted by later systems in the chain (combat_system, regeneration_system).

**Question**: Should entities marked for death be excluded from combat_system and regeneration_system? If a drone is killed (0 HP from combat) and marked for death, should it still receive healing from a friendly Heal command in the same tick? 

**Recommendation**: Yes — allow same-tick healing as a "last chance" mechanic. Document this as an intentional design choice.

---

## CONSISTENCY CROSS-CHECK

### Design vs P0-1 (Tick Protocol)
- ✅ Three-phase lifecycle (COLLECT → EXECUTE → BROADCAST) is consistent
- ✅ 2500ms/500ms timeouts match
- ✅ Seeded shuffle, inline command model, deferred spawn all align
- ✅ P0-1 adds detail on snapshot construction (per-room serialization + per-player filtering) not in DESIGN
- ⚠️ P0-1 §3.5 mentions "tick abandon behavior" — check if this has been fully specified

### Design vs P0-5 (Visibility)
- ✅ `is_visible_to` single-source-of-truth matches DESIGN's fog_of_war model
- ✅ Snapshot filtering, WebSocket delta filtering, MCP tool filtering all consistent
- ✅ Spectator view separation (drone perception vs player view) is well-defined in P0-5
- ⚠️ DESIGN §8.2 has four visibility rules (fog_of_war, player_view, public_spectate, spectate_delay) but P0-5 adds `replay_privacy` and `allied` mode — ensure DESIGN is updated

### Internal Consistency Within DESIGN

- ✅ Resource types → body part costs → action costs form a consistent pipeline
- ✅ Body part types → CommandAction binding → custom_actions extension is coherent
- ✅ World Rules → TOML config → ECS system registration is well-integrated
- ✅ Rhai mod lifecycle (init → tick_start → tick_end) is clean
- ⚠️ Controller level table (§3.1) shows "最大房间 drone" caps but doesn't cross-reference the room cap enforcement mechanism in spawn_system (§3.2)
- ⚠️ Special attack table (§8.2) lists "damage_multiplier 世界规则影响" but damage_multiplier is defined as a simple fixed-point multiplier — how does it affect non-damage effects like Hack duration or Drain rate?

---

## ALGORITHMIC SCALABILITY ANALYSIS

### Tick Budget Feasibility (target: 3s/tick)

| Component | Complexity | 100 players | 1,000 players | 10,000 players |
|-----------|-----------|-------------|---------------|----------------|
| Phase 1: Snapshot build | O(R × E) amortized | ✓ trivial | ✓ fine | ⚠️ needs batching |
| Phase 1: WASM execution | O(P) parallel | ✓ 2.5s budget | ✓ ~160ms/core | ⚠️ 1.6s/core |
| Phase 2a: Command loop | O(C) serial | ✓ <50ms | ⚠️ ~500ms | ❌ >5s |
| Phase 2b: ECS systems | O(E) serial | ✓ <10ms | ✓ ~50ms | ⚠️ ~500ms |
| Phase 3: Delta broadcast | O(ΔE × S) | ✓ | ✓ | ⚠️ NATS fan-out |

**Bottleneck**: Phase 2a serial command loop. Each command requires validation (check entity exists, check permissions, check resources, check range, check collision) plus application (ECS component mutation). At scale, this dominates.

**Mitigation path for Phase 7**:
- Spatial partitioning: commands targeting different rooms have no conflicts → parallelize by room
- Command batching: validate all commands in a batch, apply atomically
- ECS archetype optimization: Bevy's archetype storage is already cache-friendly

### Deterministic Replay Storage

The design stores full world snapshots every N ticks (§3.2). Storage estimate:
- Snapshot size: ~1KB per entity (position, components, state)
- 50,000 entities × 1KB = 50MB per snapshot
- Every 100 ticks × 50MB = 5GB per 10,000 ticks
- 864,000 ticks/day (at 0.1s tick for replay) × 50MB/100 = 432GB/day

**This is manageable with FDB's LSM-tree storage** but note that full snapshots dominate storage costs. Incremental delta storage (storing only changes between snapshots) should be on the Phase 7 roadmap.

---

## SUMMARY

| Category | Count | Status |
|----------|-------|--------|
| MAJOR issues (must fix) | 3 (D1, D2, D3) | Blocking Phase 1 |
| MEDIUM issues (should fix) | 3 (D4, D5, D6) | Blocking Phase 2 |
| LOW concerns (track) | 4 (C1–C4) | Non-blocking |
| Strengths identified | 7 (S1–S7) | — |

The architecture is fundamentally correct. The deferred command model, deterministic ECS pipeline, and dynamic resource system form a solid foundation. The six required resolutions are clarifications and edge-case specifications, not redesigns. Once D1–D6 are addressed, the design is ready for Phase 1 implementation.
