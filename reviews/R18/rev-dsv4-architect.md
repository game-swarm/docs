# R18 Architecture Review — rev-dsv4-architect (DeepSeek V4 Pro)

**Reviewer**: rev-dsv4-architect (Architect direction, DeepSeek V4 Pro reasoning model)
**Date**: 2026-06-18
**Scope**: R18 Phase 1 Clean-Slate — 10 designated files, design-stage review
**Focus**: YAML→Markdown single-source closure, ECS schedule correctness, tick lifecycle consistency, FDB/Dragonfly data paths

---

## Verdict: REQUEST_MAJOR_CHANGES

The YAML IDL → Markdown generation pipeline is structurally sound — the generated api-registry.md faithfully reproduces all 19 CommandActions, 35 canonical RejectionReason codes, 46 MCP tools, 5 Host Functions, and 22 TickTrace envelope fields from the YAML source. The single-source-of-truth architecture is well-designed with clear authority declarations and version tracking.

However, the execution has **cross-document scheduling drift, capacity value mismatches between the generated registry and hand-maintained design docs, and self-contradictory refund formulas within a single spec**. These gaps mean that two implementers reading different files in the supposedly "closed" document set would produce divergent behavior — specifically divergent world states that break determinism.

---

## Critical Findings

### C1: status_advance_system 调度位置跨文档漂移

**Files**: `specs/core/02-command-validation.md` §3.19 vs `specs/core/06-phase2b-system-manifest.md` §1

**What's declared**:

`02-command-validation.md` §3.19 states:
```
death_mark → spawn → spawning_grace → combat → status_advance → (regeneration, decay 并行) → death_cleanup
```

`06-phase2b-system-manifest.md` §1 (the authoritative manifest) states:
```
death_marker → spawn → spawning_grace → regeneration → combat → special_attack_reducer → damage_application → status effects (status_advance @ S22) → aging → decay → death_cleanup
```

**The conflict**: 02 places `status_advance` BEFORE `regeneration`; the manifest places `regeneration` BEFORE `combat` (which is far before `status_advance`). The manifest explicitly notes the R16 B2 fix ("regeneration 移至 damage_application 之前") which 02-command-validation.md §3.19 did not receive.

**Impact**: 
- Under 02's ordering: regeneration sees post-combat HP after status_advance has processed all special attack state transitions. Hack stage increments and Overload fuel reductions are applied before health regen.
- Under the manifest's ordering: regeneration happens at full HP before any combat damage. Status effects (Hack stage increment, Overload recovery, Fortify decay) happen AFTER regen.
- These produce **different world states** — a determinism split. Two engine implementations or a replay verifier using different documents would diverge.

**Severity**: Critical — determinism contract violation.

**Recommendation**: Update `02-command-validation.md` §3.19 to match the authoritative manifest. The status_advance_system documentation paragraph in 02 should be removed or explicitly reference the manifest with a "see manifest for authoritative ordering" note.

---

### C2: RoomCap "同 tick 释放" 语义歧义 — Phase 2a 校验门控

**Files**: `specs/core/01-tick-protocol.md` §3.4, `engine.md` §3.2, `specs/core/06-phase2b-system-manifest.md` §1

**What's declared**:

Multiple documents state "death_marker 在 spawn 之前：RoomCap 槽位同 tick 释放" — implying same-tick reusability of freed slots.

But the execution timeline is:
1. Phase 2a S06 `spawn_validator` reads RoomCap (R) — **before** any death marks
2. Phase 2b S07 `death_marker` writes RoomCap (W) — releases slots
3. Phase 2b S08 `spawn_system` reads+write RoomCap (R+W) — consumes freed slots

**The gap**: The "同 tick 释放" claim is technically true — S08 `spawn_system` in Phase 2b CAN use slots freed by S07 in the same tick. However, the Phase 2a validation gate (S06 `spawn_validator`) reads RoomCap BEFORE S07, meaning a room at cap at the start of Phase 2a will reject all Spawn commands even if deaths in Phase 2b will free slots later in the same tick.

**Impact**: 
- Players at room cap lose a tick of spawn opportunity whenever a drone dies — the freed slot is only usable starting from the NEXT tick's Phase 2a.
- The "同 tick 释放" claim is misleading to implementers who might assume Phase 2a validation sees freed slots.
- The manifest's R/W matrix correctly shows S06 reads RoomCap while S07 writes it — the protection is designed. But the prose in engine.md and 01-tick-protocol.md does not communicate this gating.

**Severity**: Critical — misleading design prose could cause implementation error.

**Recommendation**: Either (a) clarify in engine.md that "同 tick 释放" applies to Phase 2b spawn_system only, not Phase 2a validation, or (b) move RoomCap release earlier (e.g., have S04 recycle_system immediately release RoomCap for recycled drones, since the slot is semantically freed when the Recycle command is accepted in Phase 2a). Option (b) is a design change; option (a) is a documentation fix.

---

### C3: MAX_DRONES_PER_PLAYER: 500 in registry vs 50 in command-validation

**Files**: `specs/reference/api-registry.md` §5.1 vs `specs/core/02-command-validation.md` §6

**What's declared**:

| Source | Value | Notes |
|--------|-------|-------|
| api-registry.md §5.1 | **500** | "Per-player drone cap: 500 (world.toml configurable)" |
| engine.md §3.4.2 | **500** | "Per-player drone cap: 500 (default, world.toml configurable)" |
| game_api.idl.yaml §5 game_limits | **500** | `per_player_drone_cap: 500` |
| 02-command-validation.md §6 | **50** | "MAX_DRONES_PER_PLAYER \| 50 \| 默认 50。Tier 1 容量目标: 50 players × 10 drones = 500 total" |

The authoritative YAML and registry both say 500. The command-validation spec says 50 (with a "Tier 1 capacity target" justification that seems to describe a different constraint: 50 players × 10 drones each = 500 total, which is a global target, not a per-player limit).

**Impact**: This is a 10× difference in the default per-player drone cap. An implementer following 02-command-validation.md would set a cap of 50 drones/player, severely restricting gameplay relative to the intended 500.

**Severity**: Critical — capacity contract violated. The 50 value would break the engine's 500-active-player target (at 10 drones/player, 500 drones total is far below the 5,000 target drone count).

**Recommendation**: Update 02-command-validation.md §6 `MAX_DRONES_PER_PLAYER` from 50 to 500. The "Tier 1 capacity target" note should be reworded to avoid confusion between per-player cap and global drone targets.

---

## High Findings

### H1: Recycle refund — 50% flat vs lifespan-proportional self-contradiction

**File**: `specs/core/02-command-validation.md` §3.18 vs §10.3

**What's declared**:

§3.18 (detailed formula section):
```
refund_pct = max(0.1, 0.5 × (remaining_lifespan / total_lifespan))
```
With examples: newborn → 50%, half-life → 25%, ≤20% remaining → 10% floor.

§10.3 (summary section):
"标准退还: body part spawn 总成本的 50%"

These conflict within the same document. §3.18 is the refined formula with anti-abuse economics; §10.3 is the flat 50% legacy text that wasn't updated.

**Impact**: §3.18's lifespan-proportional formula is critical for economic integrity (prevents "Recycle末期→spawn新drone→净赚" arbitrage). If §10.3's flat 50% were implemented, the economic constraint is bypassed.

**Recommendation**: Update §10.3 to match §3.18's lifespan-proportional formula.

---

### H2: Worker pool MAX_POOL: 1000 in engine.md vs 256 in authoritative YAML/registry

**Files**: `engine.md` §3.4.2 vs `specs/reference/game_api.idl.yaml` §5 vs `specs/reference/api-registry.md` §5.5

**What's declared**:

| Source | Value |
|--------|-------|
| engine.md §3.4.2 | `MAX_POOL = 1000`（hard cap，编译期常量） |
| YAML limits | `worker_pool_max: 256` |
| api-registry.md | `max_pool = 256` |

engine.md itself declares "所有容量上限和准入策略以 specs/reference/api-registry.md §5「全局容量限制」为准" — meaning the registry (256) is authoritative, and engine.md's 1000 is wrong.

**Impact**: With 256 workers, the engine.md §3.4.2's 1000-player hard cap derivation becomes invalid (it assumes 1000 workers at 40 cores yielding ~25ms wall-clock for COLLECT). With 256 workers, 1000 players at p50=5ms → 1000/256 × 5ms ≈ 19.5ms... actually that still works. But the derivation and the 750-player scenario calculations in engine.md all assume pool=active_players up to 1000, which the authoritative limit of 256 contradicts.

**Recommendation**: Update engine.md §3.4.2 MAX_POOL from 1000 to 256 and re-derive the 750/1000 player scenarios.

---

### H3: TickTrace envelope — collect_id/attempt_id/commit_id placement ambiguity

**Files**: `engine.md` §3.3 vs `specs/core/05-persistence-contract.md` §6.1 vs `specs/reference/game_api.idl.yaml` §6

**What's declared**:

engine.md §3.3 lists `collect_id`, `attempt_id`, `commit_id` as TickInputEnvelope fields (R16 B3新增).

05-persistence-contract.md §6.1 defines them as TickTrace fields (not TickInputEnvelope fields).

The YAML envelope has 22 fields without collect_id/attempt_id/commit_id.

**The question**: Are these envelope-level fields (serialized into every tick's replay input) or TickTrace-metadata fields (tracked per-attempt but not part of the deterministic input envelope)?

**Impact**: If collect_id/attempt_id/commit_id are in the envelope, they affect `commands_hash` computation and thus determinism verification. If they're TickTrace metadata, they don't. The ambiguity could cause replay hash mismatch.

**Recommendation**: Clarify in engine.md whether collect_id/attempt_id/commit_id belong to TickInputEnvelope or to TickTrace metadata. If they're metadata, move them out of the envelope list in engine.md §3.3.

---

### H4: "terminal_state" naming collision — two distinct concepts share one name

**Files**: `engine.md` §3.3 vs `specs/reference/api-registry.md` §6.1 vs `specs/core/05-persistence-contract.md` §6.2

**What's declared**:

| Source | terminal_state values | Domain |
|--------|----------------------|--------|
| api-registry.md §6.1 / YAML §6 | Success, FuelExhausted, TimeoutExceeded, SnapshotOverBudget, CommandBufferFull, InternalError, NotExecuted | WASM execution outcome |
| engine.md §3.3 | verified, audit_gap, unreplayable, reconstructable | Blob storage integrity |
| 05-persistence-contract.md §6.2 | verified, audit_gap, unreplayable, reconstructable | Blob corruption terminal state |

The YAML/registry `terminal_state` is a WASM execution enum (7 variants). The engine.md/persistence `terminal_state` is a blob-storage integrity enum (4 variants). They share the identical field name but have completely different semantics and value sets.

**Impact**: An implementer working across these documents would encounter "terminal_state" in two contexts with different meanings, different enum values, and different validation rules. The persistence-contract's terminal_state description ("替代旧版 wasm_status 字段") even mirrors the YAML's description, making it appear they're the same concept when they're not.

**Recommendation**: Rename the blob-storage integrity field (engine.md/persistence) to `blob_terminal_state` or `storage_integrity_state` to disambiguate from the WASM execution `terminal_state`.

---

## Medium Findings

### M1: engine.md Worker Pool 推导基于错误的 MAX_POOL

engine.md §3.4.2's 750-player and 1000-player capacity derivations assume `worker_pool_size = min(1000, active_players)`. With authoritative `max_pool = 256`, the 1000-player hard cap derivation needs complete recalculation. See H2.

### M2: 02-command-validation.md §3.19 includes system ordering that's been superseded

The status_advance_system documentation paragraph in §3.19 presents an ECS order (`combat → status_advance → regeneration`) that was valid before R16 B2 but is now incorrect per the manifest. This entire paragraph creates confusion — it appears to be a legacy scheduling description that wasn't cleaned up after the manifest was created as authoritative.

### M3: engine.md TickInputEnvelope lists 20 fields; YAML/registry lists 22

Quick count of engine.md §3.3:
1. collect_id, 2. attempt_id, 3. commit_id, 4. module_hash, 5. wasmtime_version, 6. effective_tick, 7. wasm_status (→terminal_state), 8. snapshot_hash, 9. commands_hash, 10. deploy_events, 11. rollback_events, 12. admin_events, 13. world_config_hash, 14. mods_lock_hash, 15. engine_abi_version, 16. terminal_state (blob, R16 B3)

Then the YAML/registry has 22 fields including: core_idl_version, world_action_manifest_hash, validator_version, rejection_reason_registry_version, system_manifest_hash, limits_manifest_hash, host_abi_version, canonical_codec_version, visibility_truncation_version.

Several of these are missing from engine.md's envelope listing. Since engine.md says "所有容量上限和准入策略以 api-registry.md 为准" but doesn't make the same authority declaration for the envelope, this is a documentation gap rather than a contract violation. Still worth cleaning up.

---

## Low Findings

### L1: 02-command-validation.md §6 `MAX_DRONES_PER_PLAYER` table formatting is broken

The table row for MAX_DRONES_PER_PLAYER has pipe characters that appear malformed — extra `|` symbols. Cosmetic but could confuse parsers.

### L2: 04-wasm-sandbox.md references `specs/security/09-command-source` which is outside the review scope

Cross-reference to a security spec not in the review set. Low severity since it's a reference, not a dependency.

---

## YAML ↔ Markdown CrossCheck

### Generated Closure Verification

| Element | YAML Count | api-registry.md Count | Match |
|---------|-----------|----------------------|-------|
| CommandAction variants | 19 | 19 | ✅ |
| RejectionReason canonical codes | 35 | 35 | ✅ |
| MCP tools (active) | 46 | 46 | ✅ |
| Host Functions | 5 | 5 | ✅ |
| TickTrace envelope fields | 22 | 22 | ✅ |
| terminal_state variants | 7 | 7 | ✅ |
| Direction4 values | 4 | 4 | ✅ |
| Capability profiles | 5 | 5 | ✅ |
| ABI error priorities | 9 | 9 | ✅ |

### Structural Integrity
- ✅ api_version "0.3.0" consistent across YAML and registry
- ✅ YAML changelog matches registry changelog
- ✅ MCP tool rate limits, security columns, visibility filters all reproduce correctly
- ✅ Host function ABI signatures and fuel costs match
- ✅ Global capacity limits (25 parameters) match between YAML §5 and registry §5
- ✅ deploy_mutation flow (4 steps) matches across YAML §10 and registry §10
- ✅ async_object_store_upload contract matches across YAML §11 and registry §11
- ✅ RejectionReason naming conventions (InsufficientResource singular, NotVisibleOrNotFound merged) consistent

### CrossCheck Issues

| Issue | Severity | Detail |
|-------|----------|--------|
| MAX_DRONES_PER_PLAYER | Critical (C3) | registry=500, 02-command-validation=50 |
| Worker pool MAX_POOL | High (H2) | YAML/registry=256, engine.md=1000 |
| TickTrace envelope field discrepancy | Medium (M3) | engine.md lists 16-20 fields, YAML has 22 |

### Non-Issues (Verified Consistent)
- ✅ 19 CommandAction variants: YAML indices 1-19 match registry numbering exactly
- ✅ 35 RejectionReason codes: YAML indices 1-35 (Pipeline codes excluded from enum per design)
- ✅ 46 MCP tools: Verified by counting all 8 categories (8+2+14+6+7+6+1+2=46)
- ✅ Phase 2a Attack/RangedAttack damage application: engine.md correctly describes inline application; Phase 2b attack_system correctly scoped to non-player-command combat
- ✅ Recycle death path: engine.md, 06-manifest, 02-command-validation all agree on death_mark → death_cleanup path
- ✅ regeneration BEFORE damage_application: manifest and 01-tick-protocol agree on the R16 B2 fix
- ✅ spawning_grace BEFORE combat: consistent across all docs
- ✅ death_marker BEFORE spawn: consistent across all docs

---

## Algorithmic Risks

### AR1: A* Pathfinding with fair-share admission — starvation edge case

The per-player fair-share pathfinding budget `floor(100,000 / active_players)` creates a starvation scenario at exactly 1 active player → 100,000 nodes (full budget). But at 500 players → 200 nodes/player, which is below typical A* requirements for a 50×50 room (worst-case 2,500 nodes). The `ERR_BUDGET_EXHAUSTED` for pathfinding is acceptable since it's deterministic and non-fatal, but the 200-node budget at scale may make pathfinding unusable for complex terrain.

**Risk**: Low at 500-player target (players can batch pathfinding across ticks). Becomes a gameplay issue if many players in a dense world need multi-room pathfinding simultaneously.

### AR2: Snapshot sort_and_truncate determinism

The snapshot truncation uses `(distance_to_drone, entity_id)` as deterministic sort key. This is sound — both values are world-state-derived. The per-bucket priority model (critical > high > medium > low) with intra-bucket stable sort guarantees replay determinism. Verifiable.

### AR3: Overload anti-lockout proof

The mathematical proof in 02-command-validation.md §3.17 correctly demonstrates that no set of attackers can permanently lock a target's fuel budget below 20% of MAX_FUEL (2M fuel). The global per-target 50-tick cooldown + recovery rate `fuel_budget/1000` per tick guarantee the lower bound. Sound.

### AR4: Two-phase snapshot architecture O(entities + players × visible rooms)

The design correctly avoids O(players × entities) serialization. With shared room-sharded snapshots, the complexity is O(entities + players × visible_rooms_per_player). At 500 players × ~9 rooms, this is O(entities + 4,500 room-views) — well within the 50ms SNAPSHOT budget.

---

## Highlights

1. **YAML IDL as single source of truth**: The IDL→Markdown generation pipeline is well-architected. The YAML structure is clean, machine-parseable, and includes all necessary metadata (security columns, rate limits, visibility filters). The generated api-registry.md faithfully reproduces the source. This is a significant improvement over hand-maintained dual-source documentation.

2. **Complete Tick Execution Manifest**: The 29-system manifest with explicit R/W matrix and parallel safety proofs is excellent. Each system has a stable ID, version, and documented iteration key. The parallel safety proofs (target_id partition for combat, disjoint StatusState subtypes for status effects) are rigorous.

3. **Persistence contract async model**: The D5/B async object store write with FDB-first commit eliminates the "cross-storage双写" problem cleanly. The upload_status tracking (pending→uploading→complete→failed) with replay gap handling (`audit_gap` terminal state) is well-modeled.

4. **Fuel refund anti-amplification**: The "退还 credit 仅作用于下一 tick" + "deploy-reset 规则" + "同源重复失败仅首次退50%" triad is a thorough defense against refund-abuse economic exploits.

5. **Overload anti-lockout proof**: The formal proof that no coalition can permanently lock a target's fuel budget is mathematically sound and well-documented. Similar rigor should be applied to other economic constraints.

6. **SpawningGrace protection**: The 1-tick invincibility for newborn drones with explicit `Without<SpawningGrace>` filters in all combat systems is clean and prevents "birth-sniping" without leaking protection into subsequent ticks.

---

## Summary of Required Changes

| # | Severity | Description | Action |
|---|----------|-------------|--------|
| C1 | Critical | status_advance 调度漂移 (02 vs manifest) | Fix 02-command-validation.md §3.19 to match manifest |
| C2 | Critical | RoomCap "同 tick 释放" Phase 2a gating prose | Clarify in engine.md that Phase 2a validator sees pre-death-mark RoomCap |
| C3 | Critical | MAX_DRONES_PER_PLAYER: 50→500 | Fix 02-command-validation.md §6 |
| H1 | High | Recycle refund formula self-contradiction | Update §10.3 to lifespan-proportional |
| H2 | High | Worker pool MAX_POOL: 1000→256 | Fix engine.md §3.4.2 |
| H3 | High | collect_id/attempt_id/commit_id placement | Clarify envelope vs metadata |
| H4 | High | terminal_state naming collision | Rename blob storage field |
