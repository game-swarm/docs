# R22 Determinism Review — DeepSeek V4 Pro

> **Reviewer**: rev-dsv4-determinism (Determinism Reviewer)
> **Phase**: 1 (Clean-Slate Independent Review)
> **Documents Reviewed**: 8 files from /tmp/swarm-review-R16/
> **Date**: 2026-06-18

---

## Verdict: CONDITIONAL_APPROVE

The design demonstrates strong determinism awareness with layered defense mechanisms (Blake3 PRNG, fixed-point arithmetic, canonical sort keys, serial spine ECS, COLLECT buffer reuse). Three medium-severity concerns need explicit resolution before implementation proceeds; none are blocking if addressed in the spec.

---

## Strengths

1. **Layered Deterministic Sort Key**: `(priority_class, shuffle_index, source_rank, sequence, command_hash)` — 5-tier canonical ordering with Blake3 XOF seeded shuffle. Each tier has a well-defined fallback; command_hash provides absolute tiebreaking. TickTrace records seed_epoch + active player set for replay verification.

2. **Complete Tick Execution Manifest (29 systems)**: Serial spine with 3 parallel sets, full Component R/W matrix covering all 29 systems, explicit entity creation/despawn ordering, and CI-enforceable parallel safety proofs. The manifest_hash enters TickTrace — any schedule change is auditable.

3. **f64 Eradication**: Fixed-Point Type Registry (api-registry.md §0) defines `BasisPoints`, `ResourceRate_i64`, `ProgressBps_i64`, `milli_distance`, `micro_cost`, `MilliUnits`. All economy formulas use integer floor rounding. No floating-point surfaces in CommandAction parameters, host functions, or snapshot data.

4. **COLLECT Buffer Reuse on FDB Retry**: FDB commit failure → reuse canonical COLLECT buffer (same commands, same fuel ledger, same snapshot_hash), no WASM re-execution. `collect_id` stays constant; `attempt_id` increments; `commit_id` only generated on success. This prevents non-deterministic WASM re-runs from contaminating replay.

5. **Snapshot Determinism Contract**: §2.3 of 01-tick-protocol.md explicitly states: "same tick, same world state, same player → same truncation result." Sort keys for truncation are fully state-derived (distance_to_drone, entity_id, bucket assignment) — no wall-clock or parallelism dependence.

6. **Seed Rotation + Forward Secrecy Threat Model**: Acknowledges that Blake3(old || tick) allows forward prediction of future seeds if the current seed leaks. Documents the accepted risk, mitigation (periodic rotation + epoch bump), and provides an incident runbook. This is honest engineering.

7. **WASM Isolation Depth**: seccomp BPF blocks clock_gettime/getrandom; WASI fully disabled; all host functions are read-only with visibility filtering. WASM cannot observe non-deterministic OS state.

8. **TickInputEnvelope Completeness**: 22 fields capture every input that could affect replay — wasmtime_version, engine_abi_version, world_config_hash, mods_lock_hash, canonical_codec_version, system_manifest_hash, visibility_truncation_version. Version-aware replay is possible.

9. **Move-as-Action Design Rationale**: Explicitly justified on determinism grounds — single action slot eliminates Move+Attack ordering ambiguity that would create non-deterministic outcomes under different sort orders.

10. **Phase 2a TOCTOU Protection Contract**: Spawn pending invisibility, Hack ownership timing, per-drone action quota, fuel/wall-clock exhaustion semantics, no cross-tick command carryover — all specified in a single contract section.

---

## Concerns

### D1 [Medium] Canonical JSON Serialization Rules Unspecified

**Location**: 01-tick-protocol.md §9.1, 02-command-validation.md §2.1

The sort key's final tiebreaker is `command_hash = Blake3(command_json)`. For this to be deterministic, `command_json` must be produced by a canonical serializer (sorted keys, no trailing whitespace, consistent number formatting, UTF-8 normalization). The TickInputEnvelope includes `canonical_codec_version` (field 21), implying awareness of this requirement, but:

- The exact canonical JSON rules are not specified in any reviewed document
- Different JSON libraries produce different output for the same logical object
- If WASM modules serialize CommandIntent JSON using language-specific libraries, `command_json` may differ even when the logical command is identical

**Risk**: If two WASM modules produce semantically identical commands with different JSON representations, the `command_hash` tiebreaker produces different sort orders, leading to divergent world states.

**Recommendation**: Specify canonical JSON serialization rules in a dedicated spec section or reference doc:
- Mandate sorted object keys (Unicode codepoint order)
- Mandate no whitespace outside string literals
- Mandate integer representation (no decimal points, no scientific notation)
- Mandate UTF-8 NFC normalization
- Reference the `canonical_codec_version` field to allow future upgrades

---

### D2 [Medium] host_path_find Cache Determinism Not Explicitly Guaranteed

**Location**: 04-wasm-sandbox.md §8

The pathfinding host function uses caching with key `(from, to, terrain_hash, player_visibility_fingerprint)`. The spec says "超限 deterministic fail" for budget exhaustion and details fuel costs for cache_miss vs cache_hit. However:

- It does not explicitly state that a cache hit MUST return the identical path as a cache miss would
- If the cache stores a path that was computed under different world state (stale cache from a previous tick with different terrain), the returned path would be incorrect and non-deterministic
- The cache key includes `terrain_hash` but not `tick` — if terrain changes within a tick (which shouldn't happen since terrain is static, but mods could change it), the cache could return stale results

**Risk**: If caching ever returns a path that differs from what would be computed fresh, replay will diverge because the replay environment may have a different cache state (cold cache on first replay, warm cache on subsequent runs).

**Recommendation**: Add an explicit contract statement: "Cached path results MUST be bitwise-identical to freshly computed results for the same input parameters. The cache is a performance optimization only and MUST NOT alter the return value. CI tests MUST verify that cold-start and warm-cache replays produce identical state_checksum."

---

### D3 [Medium] Contested Room State Resolution — Underspecified Tiebreaking

**Location**: engine.md §3.1a, 01-tick-protocol.md §1.3

The `contested` room state: "每 tick 各自投入的 progress 减去对方的抵消量（取决于双方 Claim body part 数量差）。净 progress 归零的一方失去 claim 资格。"

- If both players have identical Claim body part counts, the "progress difference" is zero for both — does the room stay contested indefinitely?
- The resolution formula ("mutual offset based on Claim body part count difference") is not expressed as a deterministic formula
- When exactly does one side "lose qualification"? Is it when their progress reaches 0 after offset subtraction? What if both reach 0 simultaneously?

**Risk**: Ambiguous resolution rules for the contested state create a non-deterministic fork in the state machine — different implementations could produce different outcomes from the same inputs.

**Recommendation**: Specify the contested resolution formula in closed form:
```
net_progress_A = claim_progress_A - offset(delta_claim_parts) * claim_progress_B
net_progress_B = claim_progress_B - offset(delta_claim_parts) * claim_progress_A
```
Define `offset(delta)` as a deterministic function (e.g., `delta * CLAIM_OFFSET_FACTOR`). Define tiebreaking when both progress values reach zero simultaneously (e.g., the room reverts to neutral, or the player with higher cumulative historical progress wins).

---

### D4 [Low] RoomCap Intermediate State — Future Maintenance Hazard

**Location**: 06-phase2b-system-manifest.md §3

Between S07 (death_marker frees RoomCap) and S08 (spawn consumes RoomCap), no system may read RoomCap for admission decisions. The manifest explicitly warns about this. However:

- S07 and S08 are adjacent in the serial spine (no systems between them), so the hazard window is closed
- If a future system is inserted between S07 and S08, it could inadvertently read RoomCap during the intermediate state
- The protection relies on documentation + code review discipline rather than compile-time enforcement

**Recommendation**: Add a compile-time assertion or CI lint rule: "Any system between S07 and S08 that accesses RoomCap (R or W) is a compile error." This can be enforced via Bevy's system ordering API or a custom CI checker.

---

### D5 [Low] Parallel Combat Set — Partition Determinism Relies on Disjoint Entity Assumption

**Location**: 06-phase2b-system-manifest.md §4, S11-S13

Combat Parallel Set A (attack_system, ranged_attack_system, heal_system) claims safety via "target_id partition — same entity only written by one system." This relies on:

- attack_system targets enemies → writes Entity(hits)
- heal_system targets friendlies → writes Entity(hits)
- Enemy and friendly sets are disjoint

But if a drone changes ownership mid-tick (e.g., Hack stage 5 transfer), entities that were enemies become neutral. The spec says Hack ownership transfer happens at stage 5 in status_advance (S22), which runs AFTER combat (S11-S13). So the disjointness holds for the current design. However:

- This invariant is implicit in the system ordering, not explicitly enforced
- A future system inserted before combat could change ownership and break the assumption

**Recommendation**: Document the invariant explicitly: "Combat Parallel Set A assumes entity ownership is immutable during S11-S13. Any system that modifies Owner must run after S15 (damage_application)." Add CI assertion for this.

---

### D6 [Low] IndexMap Determinism Depends on Insertion Order

**Location**: engine.md §3.1 (Resource, Source structs)

`Resource.amounts: IndexMap<String, u32>` and `Source.produces: IndexMap<String, u32>` guarantee deterministic iteration order. However, the iteration order depends on insertion order, which depends on tick execution order. While the execution order is deterministic (given same inputs), the spec doesn't explicitly note this dependency.

**Recommendation**: Add a note: "IndexMap iteration order is fully determined by the order resources are added during tick execution, which is in turn determined by the canonical command sort order. This creates a deterministic but non-obvious coupling between command execution and resource iteration."

---

## Replay Gaps

### RG1: Snapshot Truncation Amplification in Near-Identical Replays

**Location**: 01-tick-protocol.md §2.3

The snapshot truncation algorithm uses `(distance_to_drone, entity_id)` as sort keys. Distance depends on the drone's current position, which is state-dependent. In a replay scenario where the initial state is identical, truncation produces identical results — determinism is preserved.

However, for forensic/debugging use cases where an operator replays from a "nearby" state (e.g., fixing a corrupted keyframe by interpolating), even a single-cell difference in drone position could cascade through the truncation → WASM input → commands → state chain. This is not a determinism bug but may surprise operators expecting "approximately same" replays.

**Recommendation**: Document this property clearly: "Determinism is exact, not approximate. A one-cell position difference produces a completely different causal chain. Partial or interpolated replays are not supported."

### RG2: FDB Commit Failure + Object Store Async Gap

**Location**: 05-persistence-contract.md §2, §6

FDB commit succeeds → tick is durable. Object store blob is written asynchronously. If the engine crashes between FDB commit success and blob write completion, the tick is durable but unreplayable (upload_status = pending/failed). The spec handles this with terminal_state = audit_gap.

This is acceptable for operational durability (world state is preserved) but creates replay gaps. Operators should monitor upload_status and alert on persistent "pending" entries.

---

## Formal State Issues

### FS1: SpawningGrace Lifecycle Boundary

**Location**: 06-phase2b-system-manifest.md S09, engine.md §3.2

`SpawningGrace { remaining: 1 }` is assigned in S09 (birth tick). The entity is in `pending_entities` until end-of-tick flush. The spec says "next tick remaining decrements to 0" implying status_advance (S22) does NOT decrement it in the birth tick. However:

- S22 runs every tick and reads all StatusState components
- If the entity hasn't been flushed from pending_entities yet, S22 won't see it — this is correct
- But if the flush happens BEFORE S22 in the birth tick (contradicting §3 which says flush is at end of all systems), the grace would be consumed in the same tick

**Status**: The current manifest says entities flush "at end of all systems." This is correct as long as the implementation honors it. Add CI test: "new drone in birth tick must survive all damage systems."

### FS2: Overload Minimum Fuel Budget as Absorbing State

**Location**: 02-command-validation.md §3.17, engine.md §3.4.2

The Overload anti-lockout proof shows that fuel budget cannot go below `MAX_FUEL × 0.2 = 2,000,000` due to global cooldown + recovery. However:

- If `effective_per_player_quota` (from admission formula) drops below 2M (e.g., during high player count), Overload could push a player below their effective quota even though the absolute budget stays at 2M
- The interaction between Overload-reduced fuel and admission formula isn't modeled

**Recommendation**: Document the interaction: "Overload reduces absolute fuel budget. The per-tick allocation is `min(effective_per_player_quota, overload_reduced_fuel)`. A player at 2M minimum + 500 active players = effective quota of ~1M — the player still gets 1M per tick regardless of the absolute 2M minimum."

---

## CrossCheck

- **CX1**: Claim body part delta formula for contested room resolution is underspecified → Suggest Architect verify the closed-form resolution formula with edge cases (equal parts, simultaneous zero)

- **CX2**: Canonical JSON serialization rules are referenced by name (`canonical_codec_version`) but not defined in any reviewed document → Suggest Architect or Security reviewer verify that the canonical serialization spec exists in an un-reviewed document

- **CX3**: The `world_seed` forward-prediction property (`new = Blake3(old || tick)`) is documented as an accepted risk — suggest Security reviewer evaluate whether the 10000-tick rotation window is acceptable for competitive integrity

- **CX4**: `IndexMap` choice for Resource/Source presumes deterministic insertion order — suggest Architect verify that resource operations in the execution trace always produce identical insertion order under replay

- **CX5**: host_path_find cache determinism needs explicit contract — suggest Architect verify that the caching layer is designed as a pure optimization with no semantic effect on output

---

## Summary

The Swarm design demonstrates thorough determinism engineering: Blake3-based PRNG with namespace isolation, fixed-point arithmetic throughout, canonical sort keys spanning 5 tiers, a complete 29-system execution manifest with R/W matrix, COLLECT buffer reuse on retry, and WASM isolation that blocks all non-deterministic OS interfaces.

The three medium-severity concerns (canonical JSON serialization, pathfinding cache determinism, contested room resolution) are specification gaps rather than design flaws — each has a clear resolution path. The four low-severity concerns are maintenance/documentation improvements.

**Verdict**: CONDITIONAL_APPROVE — proceed with implementation after addressing D1, D2, D3 in the spec.
