# Architect Review — DeepSeek V4 Pro (R-appcert-R2)

**Reviewer**: rev-dsv4-architect (DeepSeek V4 Pro)
**Documents reviewed**: 25 files (README, auth, engine, gameplay, interface, modes, tech-choices, 01-tick-protocol, 02-command-validation, 04-wasm-sandbox, 07-world-rules, 03-mcp-security, 05-visibility, 09-command-source, CVE-SLA, 06-feedback-loop, 08-api-idl, commands, host-functions, mcp-tools, 12-gateway-protocol, T2-incremental-snapshot, T3-shard-protocol, GETTING-STARTED, RUNBOOK)
**Review principles**: Design-stage review only — no implementation-phase concerns. If a suitable solution exists, adopt it without considering implementation difficulty.

---

## Verdict: CONDITIONAL_APPROVE

The design is architecturally sound with mature component boundaries, a well-defined ECS execution chain, and strong determinism guarantees. Three Critical findings require resolution before proceeding to implementation. All are design-level issues with clear fix paths.

---

## Strengths (Architecture Highlights)

**S1. Clean Phase 2a/2b Separation.** The inline command execution (2a) vs deferred ECS systems (2b) boundary is precisely defined: player-submitted commands execute sequentially with TOCTOU protection, while passive systems (spawn, combat, decay, regen) run in a deterministic chain. The classification principle (players submit commands → inline; world responds → deferred) is both intuitive and mechanically sound.

**S2. Snapshot Architecture.** Two-phase snapshot construction (single full snapshot → per-player room-shard stitching) reduces complexity from O(P×E) to O(E + P×visible_rooms). The 256KB per-player cap with deterministic bucket-based truncation is well-designed with explicit determinism guarantees. The `truncated` flag + `omitted_count` (now bucketed) gives WASM modules enough information for graceful degradation.

**S3. Determinism Contract.** Blake3 XOF PRNG, `indexmap` for ordered iteration, explicit `f64` prohibition, `.chain()` enforcement — every determinism dependency is named with a replacement. The seeded shuffle for fair command ordering is elegant: deterministic (same seed → same order), fair (rotation per tick), and unpredictable (players can't know their position).

**S4. FDB Failure Recovery.** The Bevy World snapshot → inline modify → FDB commit → restore-on-failure chain is a principled approach to atomicity without FDB's transaction model leaking into the game engine. The complete Component/Resource snapshot list in §3.5 is exhaustive. CI fault injection tests (random 10% commit failures) provide regression coverage.

**S5. WASM-Only Executor.** No McpPlayerExecutor. MCP is management only. All players — human or AI — submit WASM through the same sandbox. Fuel metering provides automatic fairness. This is the correct architecture for a programming game platform.

**S6. Tier Entry Gate Matrix.** The explicit freeze of what each Tier enables/defers (engine.md §3.2 Tier Entry Gate Matrix) prevents MVP scope creep. `future-disabled` items compile-time excluded via feature flags — no dead code paths in production.

**S7. Collateral Damage Containment.** COLLECT timeout isolates slow players (empty commands, no world blocking). WASM crash → empty tick, not engine crash. Rhai script AST budget → isolated script discard, not world rollback. Each failure mode has a documented blast radius.

**S8. Oracle Defense.** The visibility oracle closure (05-visibility §10) closes cross-interface information leaks: `NotVisibleOrNotFound` unified rejection, `omitted_count` bucketed, dry-run/simulate/explain output desensitized. Special attack attackers can't distinguish "target not found" from "target not visible."

**S9. Progressive Overload Lock-Out Proof.** The formal proof (02-command-validation §3.17) demonstrating that no coalition of attackers can permanently lock out a target's fuel budget via Overload is mathematically sound: global per-target cooldown (50 tick) + recovery rate (fuel_budget/1000 per tick) + floor (20% of max) guarantee unbounded eventual recovery.

---

## Findings

### Critical

**C1. Bevy World Snapshot Completeness — Living List Risk**

**Location**: 01-tick-protocol §3.5 (Bevy World Snapshot Range List), engine.md §3.2

**Issue**: The FDB commit failure recovery path requires `world.restore(snapshot)` to roll back all ECS state modified during Phase 2a inline execution. The design provides an explicit Component/Resource snapshot list (§3.5) that must be captured. However, this is a **manually maintained enumeration** — every new Component or Resource type added to the engine must also be added to this list, or it will be silently lost on rollback.

The current list includes ~25 Component categories and 7 Resource types. As features expand (body part types, status effects, custom world rules), the risk of omission grows with each addition. A silent omission would cause a state inconsistency that persists across ticks — the Bevy World after rollback would differ from the pre-Phase 2a state, violating the determinism contract.

**Severity**: Critical — if triggered, causes silent state corruption that compounds across ticks.

**Recommendation**: 
1. Add a CI test that introspects all Component and Resource types registered in the Bevy App at startup, compares against the snapshot list, and fails if any type is missing. This turns the living list from a manual audit into a compile-time guarantee.
2. Consider using Bevy's reflection system (`AppTypeRegistry`) to auto-discover all Component/Resource types at snapshot time, falling back to the explicit list only for non-reflected types. This reduces the maintenance burden to zero for reflected types.

**C2. World Seed Forward Predictability — Deterministic Chain Leak**

**Location**: 01-tick-protocol §3.1 (Forward Secrecy Threat Model)

**Issue**: The world_seed rotation algorithm (`new = Blake3(old || tick)`) creates a deterministic derivation chain. An attacker who obtains the seed at tick N can compute all future seeds until the next **manual** epoch bump. The design acknowledges this as "accepted risk" and classifies world_seed as "admin-level secret."

However, the design simultaneously relies on world_seed for:
- Player command ordering (seeded shuffle)
- All RNG outputs (combat damage variance, spawn positions, resource regeneration timing, NPC event triggers)
- Snapshot truncation tiebreaking

A leaked seed is not merely an ordering advantage — it enables **complete future state prediction**. An attacker can pre-compute every random outcome for the next 10,000 ticks, identify optimal strategies, and execute them with perfect timing. This goes beyond "unfair advantage" into "solved game" territory.

The current mitigation (periodic rotation every 10,000 ticks) only limits the window width — it doesn't prevent exploitation within the window. The manual epoch bump requires human detection and intervention, creating a window between leak and response.

**Severity**: Critical — leaked seed enables complete game-state prediction within the rotation window.

**Recommendation**: 
The design explicitly rejects cryptographic forward secrecy (bidirectional unpredictability) because it would require external entropy injection, breaking determinism. This constraint is real. Acceptable mitigations within the determinism constraint:

1. **Hash chain with blinding**: Instead of `new = Blake3(old || tick)`, use `new = Blake3(old || tick || server_secret)` where `server_secret` is a secondary secret stored separately from world_seed (e.g., in an environment variable or HSM). This breaks the forward computation chain: knowledge of world_seed alone is insufficient to compute future seeds without the server_secret. The server_secret is still static (no external entropy), preserving determinism, but creates a two-factor seed system.
2. **Dual-seed model**: Split world_seed into `public_seed` (used for tick-to-tick derivation, rotation) and `blind_seed` (used for RNG output, never in the derivation chain). Leaking `public_seed` reveals ordering but not RNG outputs.
3. Document the attack surface explicitly: "World seed leak = complete game compromise within rotation window. Protection equivalent to TLS private key."

**C3. Direction Enum Inconsistency — TopRight vs Cardinal**

**Location**: commands.md §Move vs 08-api-idl.md §Direction enum

**Issue**: `commands.md` documents Move direction as `"TopRight"` (example: `{"type": "Move", "object_id": "d1", "direction": "TopRight"}`). However, `08-api-idl.md` defines the `Direction` enum as `[North, South, East, West]` — four cardinal directions only. `02-command-validation.md` validates against `InvalidDirection` with "Direction is valid four-way neighbor (N/S/E/W)."

TopRight is a diagonal — it is not N, S, E, or W. The reference documentation (commands.md) and the IDL/spec are in direct conflict. If implemented per commands.md, diagonal moves would be rejected by the validation pipeline. If implemented per IDL, the reference docs are misleading.

**Severity**: Critical — SDK code generation from IDL would produce types incompatible with reference documentation, breaking all WASM modules that follow the reference docs.

**Recommendation**: Fix commands.md to use cardinal directions consistent with the IDL. The Move example should use `"North"` instead of `"TopRight"`. This is a documentation bug, not a design flaw — the IDL is the authoritative source.

---

### High

**D1. FDB/Dragonfly Authority Transition — No Explicit Staleness Protocol**

**Location**: 01-tick-protocol §6.4, 12-gateway-protocol §3.2

**Issue**: The read-path authority chain is: COLLECT → Bevy World, EXECUTE → Bevy World → FDB commit, BROADCAST → Dragonfly/NATS. After FDB commit, Dragonfly receives a cache update. But between FDB commit success and Dragonfly update receipt, a read request could hit Dragonfly and receive stale data. The design says "Dragonfly cache stale → fall back to FDB" but does not define **how** Dragonfly detects staleness.

The current design: FDB commits with a versionstamp (FDB's built-in monotonic counter). Dragonfly receives the update asynchronously. A reader hitting Dragonfly after FDB commit but before Dragonfly update would see the previous tick's data. The fallback mechanism (check versionstamp → if stale, read FDB) is described in prose but lacks a concrete protocol specification.

**Severity**: High — Under concurrent read/write load, stale reads could cause clients to act on outdated world state. While clients detect gaps via `last_tick`, the gap detection relies on tick number monotonicity, not data freshness within a tick.

**Recommendation**: Define an explicit staleness detection protocol:
1. Dragonfly stores `(tick_number, data)` for each cached key.
2. On read, compare Dragonfly's stored tick_number against the current committed tick from FDB.
3. If Dragonfly tick < FDB committed tick → read FDB directly.
4. Document the maximum staleness window (≤2 ticks per DESIGN.md §3) and the conditions that widen it (Dragonfly under load, NATS backpressure).

**D2. Snapshot Truncation with Entity References — Broken References Risk**

**Location**: 01-tick-protocol §2.3, 02-command-validation §3

**Issue**: When a snapshot is truncated (≥256KB), entities are dropped based on priority buckets. However, WASM code may generate commands referencing truncated entity IDs. Example: drone A is in the high-priority bucket (retained), but the nearest Source is in the low-priority bucket (truncated). The WASM module sees drone A but cannot see the Source to target with Harvest. The `truncated=true` flag tells WASM "your data is incomplete" but doesn't indicate **which** entities are missing.

The design addresses this with `omitted_count` (now bucketed: few/some/many/extreme) and the priority bucket ordering. But there is no **forward guarantee** that WASM modules can safely generate commands when truncated. A module might generate a Harvest targeting an entity_id that was truncated — the validation pipeline would reject it as `ObjectNotFound`, consuming the action slot and fuel.

**Severity**: High — Silent command failures due to truncation create a frustrating feedback loop where players can't distinguish "my logic is wrong" from "the entity I targeted was truncated from my snapshot."

**Recommendation**: 
1. Add a `truncated_entity_ids: Vec<EntityId>` field to the snapshot that lists the entity IDs of truncated entities. This lets WASM modules explicitly avoid generating commands for missing entities.
2. Or: treat entity references in commands against truncated entities as `TruncatedEntity` (distinct from `ObjectNotFound`), with fuel refund. This gives players clear feedback: "your logic was correct, but you couldn't see the target."

**D3. COLLECT Cache Reuse Depends on Perfect Snapshot Restore**

**Location**: 01-tick-protocol §3.5 (COLLECT Result Cross-Retry Cache)

**Issue**: On FDB commit failure, the COLLECT result cache (commands + fuel deductions) is reused for retries. This is correct only if the Bevy World is perfectly restored to its pre-Phase 2a state. If any state leaks through (see C1), the retry would validate cached commands against a subtly different world state, producing different results — violating determinism.

This is a dependency chain: D3 resolves if C1 is fully addressed. But it's architecturally significant enough to flag independently: the COLLECT cache reuse is an optimization that introduces tight coupling between snapshot correctness and retry correctness.

**Severity**: High — chains with C1; if C1 occurs, D3 amplifies the corruption across retries.

**Recommendation**: Add a sanity check before COLLECT cache reuse: compute `state_checksum` of the restored Bevy World and compare against the pre-Phase 2a checksum stored with the COLLECT cache. If they differ, abort the tick (don't retry with inconsistent state) and trigger a CRITICAL alert. This converts a silent corruption into a loud failure.

---

### Medium

**D4. RoomCap Release Timing — death_mark → spawn Pipeline Coupling**

**Location**: engine.md §3.2 (Phase 2b ordering), 01-tick-protocol §3.4

**Issue**: The Phase 2b chain runs `death_mark_system` (releases room cap slots) → `pvp_block_system` → `spawn_system` (consumes room cap slots). This ordering is correct for same-tick dead→spawn replacement. However, there are 10 systems between `death_mark` and `spawn` in the `.chain()` (pvp_block, npc_spawn, spawn, regeneration, seed_rotation, cargo_in_transit, global_storage, controller, controller_repair, depot_repair...). Any system added between them that reads `RoomCap` would see the post-death-mark-but-pre-spawn intermediate state, where slots are freed but not yet re-consumed. This could cause transient over-subscription if a system uses the intermediate RoomCap value for admission control.

**Severity**: Medium — Currently no system between death_mark and spawn reads RoomCap. But the coupling is implicit (depends on ordering knowledge), making it fragile to future system additions.

**Recommendation**: Document the RoomCap lifecycle explicitly in the Component/Resource write matrix (§3.4): `death_mark: W(release), spawn: R(check) + W(consume)`. Add a comment in the `.chain()` registration that no system between death_mark and spawn should use RoomCap for admission decisions.

**D5. Dragonfly Nonce Storage — Acceptable Risk Boundary**

**Location**: auth.md §10.8

**Issue**: Request nonces for replay protection are stored in Dragonfly with SETNX TTL, not in FDB. If Dragonfly crashes between nonce write and TTL expiry, a replay within the TTL window (default 300s) would succeed. The design acknowledges this as "崩溃语义: TTL 窗口内可重放."

**Severity**: Medium — The nonce is per-(account_id, nonce_value) with a 128-bit random nonce. Replay requires: (a) attacker captured the original request, (b) Dragonfly crashed within the TTL window, (c) attacker replays before TTL expiry, (d) the certificate hasn't expired. This is a narrow window requiring multiple coincident failures. For non-admin operations (MCP queries, deploys with version_counter), the impact is limited.

**Recommendation**: Document the threat model explicitly: "Dragonfly crash within nonce TTL window enables single-request replay. Mitigated by: 128-bit random nonce space, certificate expiry, deploy version_counter, and the narrow coincidence window." No architectural change needed — the risk is accepted and quantified.

**D6. Tier 2/3 Specs — Frozen but Unverified**

**Location**: T2-incremental-snapshot.md, T3-shard-protocol.md

**Issue**: Tier 2 (modification-set tracking, CoW entity paging) and Tier 3 (room-based sharding, cross-shard combat protocol) are described with candidate solutions but marked as "must be frozen before Phase 1 implementation." The T2 spec has 6 "pending items" requiring benchmark confirmation. The T3 spec has 5 pending items including the consistency hash algorithm and cross-shard replay chain merge. These are not design gaps — they're correctly identified as future work. But the "Phase 1 implementation" gate is fuzzy.

**Severity**: Medium — If Phase 1 implementation proceeds without T2/T3 specs being frozen, the engine may make architectural choices that complicate the Tier 1→T2 migration path (e.g., snapshot format, entity ID allocation, FDB key layout).

**Recommendation**: Add explicit freeze criteria to the Tier Entry Gate matrix: "Tier 2 spec must be frozen (all pending items resolved) before any Tier 1 code paths that affect snapshot format, entity ID generation, or FDB key layout are merged."

---

### Low

**D7. `snapshot_tick` Mismatch Between `swarm_explain_last_tick` and Other Queries**

**Location**: 05-visibility §5 (Output Surface Tick Baseline table)

**Issue**: The table shows `swarm_explain_last_tick` uses tick N-1 as its baseline, while all other query surfaces use tick N. This is semantically correct (explaining what already happened vs querying current state), but creates a subtle API asymmetry: if a player calls `swarm_get_snapshot` (tick N) and `swarm_explain_last_tick` (tick N-1) in the same tick, the entity positions in the snapshot won't match the explanation's context. This is by design, but not explicitly warned in the API docs.

**Severity**: Low — Documented in the visibility spec but not surfaced in MCP tool documentation.

**Recommendation**: Add a note to `swarm_explain_last_tick` MCP tool docs: "Returns explanation for tick N-1, which may not match entities visible in tick N's snapshot. Use the replay tool for frame-accurate correlation."

**D8. Arena `spectate_delay` Minimum Enforcement**

**Location**: 05-visibility §8.1, modes.md §9.1.2

**Issue**: `spectate_delay` is specified as minimum 50 in the visibility spec, but Arena mode lists it as configurable with default 100. The minimum 50 is enforced in `validate_config` (rejects < 50) for World mode, but Arena mode's `spectate_delay` minimum is not explicitly stated in the Arena config schema.

**Severity**: Low — Arena mode would naturally use a higher delay, but missing explicit enforcement could allow configuration errors.

**Recommendation**: Add `spectate_delay` minimum to Arena config validation with the same ≥50 constraint, or document that Arena inherits World's validate_config rules.

---

## Cross-Document Consistency Gaps

**G1. Direction Enum**: commands.md uses `"TopRight"`; 08-api-idl.md defines `[North, South, East, West]`; 02-command-validation.md validates against four-way neighbors. **Status**: INCONSISTENT (see C3).

**G2. Command Type Names**: commands.md uses `SpawnDrone` as the type name in the intro text but `Spawn` in the JSON example. 08-api-idl.md uses `Spawn`. 02-command-validation.md uses `Spawn`. **Status**: Minor naming inconsistency in reference docs; IDL is authoritative.

**G3. `RoomDroneCapReached` Enum**: Appears in 02-command-validation.md RejectionReason list as `RoomDroneCapReached`. Also appears in 08-api-idl.md as `RoomDroneCapReached`. **Status**: Consistent.

**G4. Body Part Count**: gameplay.md mentions 8 standard body parts (Move/Work/Carry/Attack/RangedAttack/Heal/Claim/Tough). 08-api-idl.md lists the same 8 in the BodyPart enum. 02-command-validation.md references these 8 in per-command validator lists. **Status**: Consistent.

**G5. Special Attack Count**: gameplay.md Vanilla Ruleset table says "Tier 1 includes 6" special attacks (Hack/Drain/Overload/Debilitate/Disrupt/Fortify). 02-command-validation.md defines these 6 plus Leech and Fabricate (marked Tier 2). 08-api-idl.md defines all 8 in the commands section. **Status**: Consistent — the 6/8 split is correctly documented.

**G6. `swarm_get_available_actions` vs `swarm_sdk_fetch`**: 06-feedback-loop.md and interface.md reference `swarm_get_available_actions`. 08-api-idl.md §6 references `swarm_sdk_fetch`. These appear to be different tools — `get_available_actions` returns the current action list, while `sdk_fetch` downloads the full SDK artifact. **Status**: Potentially confusing naming; clarify in MCP tool docs.

---

## Algorithmic Risk Assessment

**Risk 1: A* Pathfinding — Explored Node Budget**
- Budget: 10 calls/tick × 100,000 explored_nodes total per player
- With 500 active players: worst case 5M nodes explored per tick
- **Risk**: A malicious WASM module can consume the full 100,000 node budget on a single path_find call (targeting an unreachable destination). The budget cap prevents CPU exhaustion but creates a per-player denial condition: a player who exhausts their budget has zero pathfinding for the rest of the tick.
- **Mitigation**: The deterministic fail on budget exhaustion is correct. The 10-call limit prevents a single bad path_find from consuming all calls. Acceptable.

**Risk 2: Visibility Computation — Per-Player Per-Tick**
- Each player's visibility set is computed once per tick: O(visible_entities) per player
- With 500 players and ~200 visible entities each: 100,000 entity visibility checks per tick
- **Risk**: The per-tick cache (keyed by (tick, player_id)) prevents recomputation across output surfaces. Acceptable for MVP. At Tier 2 scale (5,000 players), the cache approach will need incremental visibility updates rather than full recomputation.

**Risk 3: Seeded Shuffle — O(N) Per Tick**
- Fisher-Yates shuffle of active player list: O(N) where N ≤ 500
- **Risk**: Negligible. 500-element shuffle is sub-millisecond.

**Risk 4: Snapshot Construction — Entity Serialization**
- Full Bevy World deep copy per tick: O(entities) for the full snapshot, then O(players × visible_entities) for per-player filtering
- **Risk**: At Tier 1 scale (500 entities, 50 players), this is ~50ms. At Tier 2 scale (5,000 entities, 500 players), this becomes ~500ms before the 256KB truncation kicks in. The Tier 2 migration to modification-set tracking is correctly identified as necessary.

---

## Summary

| Severity | Count | IDs |
|----------|-------|-----|
| Critical | 3 | C1 (snapshot completeness), C2 (seed forward predictability), C3 (direction enum inconsistency) |
| High | 3 | D1 (Dragonfly staleness protocol), D2 (truncation broken references), D3 (COLLECT cache → snapshot dependency) |
| Medium | 3 | D4 (RoomCap timing coupling), D5 (Dragonfly nonce risk), D6 (Tier 2/3 freeze criteria) |
| Low | 2 | D7 (explain_last_tick tick mismatch), D8 (Arena spectate_delay minimum) |

**Action**: All three Critical findings must be addressed. C1 requires a CI-enforced snapshot completeness check. C2 requires the dual-seed or blind-seed mitigation. C3 is a documentation fix (commands.md direction example). High findings should be addressed before Phase 2 implementation. Medium and Low findings are non-blocking but should be tracked.
