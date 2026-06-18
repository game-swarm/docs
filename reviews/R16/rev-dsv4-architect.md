# R16 Architecture Review — DeepSeek V4 Pro (Architect)

**Reviewer**: rev-dsv4-architect (DeepSeek V4 Pro)  
**Phase**: Clean-Slate R16 Phase 1  
**Documents Reviewed**: 9 files — design/README.md, design/engine.md, design/tech-choices.md, specs/reference/api-registry.md, specs/core/01-tick-protocol.md, specs/core/02-command-validation.md, specs/core/04-wasm-sandbox.md, specs/core/05-persistence-contract.md, specs/core/06-phase2b-system-manifest.md  
**Review Date**: 2026-06-18

---

## Verdict: REQUEST_MAJOR_CHANGES

The design demonstrates mature thinking on determinism, data consistency, and sandbox security. However, the ECS system scheduling between engine.md and the authoritative System Manifest (06-phase2b-system-manifest.md) contains fundamental contradictions — different system counts, different ordering, and a **spawning-grace timing bug** that makes the "birth-kill prevention" design contract unenforceable under the manifest's schedule. These cannot be resolved by implementers choosing "either" interpretation — the two documents describe different engines.

---

## Strengths

1. **Persistence layering (05-persistence-contract.md)** is architecturally solid. FDB as small-object authority + Object Store for heavy blobs + GC for orphan cleanup + dual-write failure semantics table covers all edge cases. The commit-before-FDB pattern with orphan GC is a proven pattern.

2. **TOCTOU contract (02-command-validation.md §3.3)** is rigorous. Spawn deferral, Hack ownership timing, per-drone action quota, no cross-tick command carryover — each rule closes a specific time-window attack vector with explicit justification.

3. **Overload anti-lockout proof (02-command-validation.md §3.17)** is a rare example of formal reasoning about game balance in a technical spec. The 50-tick global cooldown + 2M floor + Fortify purge proves no permanent fuel starvation is possible. This belongs in the design.

4. **Two-phase snapshot architecture** (engine.md §3.2) — O(entities + players × visible_rooms) instead of O(players × entities) — is a genuine optimization with correctly articulated invariants (single snapshot for WASM + MCP in same tick).

5. **Blake3 single-primitive strategy** (tech-choices.md §8) for hash + PRNG + XOF reduces the audit surface and dependency count. The namespace isolation for RNG streams (combat / loot / npc_spawn / event) in 01-tick-protocol.md §9.5 is correctly scoped.

6. **Sandbox OS boundary checklist** (04-wasm-sandbox.md §9) is comprehensive — seccomp table, cgroup limits, namespace isolation, CI verification commands, and a `relaxed` mode gate that refuses production startup. This is the right level of paranoia.

---

## Issues

### Critical

**C1 — ECS System Schedule: Two Incompatible Engine Descriptions**

engine.md §3.4 (lines 381–401) defines a 20-system flat `.chain()`:
```
rhai_rule_module_tick_start → death_mark → pvp_block → spawn → regeneration
→ seed_rotation → cargo_in_transit → global_storage → controller
→ controller_repair → depot_repair → room_state → combat → decay
→ memory_upkeep → drone_env_var → rhai_rule_module_tick_end → death_cleanup → onboarding
```

06-phase2b-system-manifest.md declares itself "the sole authoritative definition" with a **27-system** serial spine + 3 parallel sets in a completely different order:
```
command_executor → controller → spawn → build → recycle → transfer
→ [Parallel A: attack/ranged/heal] → damage_application → death_marker
→ [Parallel B: hack/drain/overload/debilitate/disrupt/fortify/status_advance]
→ aging → [Parallel C: regeneration/decay/spawning_grace]
→ death_cleanup → pvp_block → room_state → controller_p2b → resource_ledger
```

System counts differ (20 vs 27). Ordering is incompatible:
- engine.md: `regeneration` BEFORE `combat`; manifest: `regeneration` AFTER `aging` (which is after combat)
- engine.md: `pvp_block` BETWEEN `death_mark` and `spawn`; manifest: `pvp_block` AFTER `death_cleanup`
- engine.md: `decay` right after `combat`; manifest: `decay` in Parallel Set C after `aging`
- engine.md: no `spawning_grace` in chain; manifest: `spawning_grace` at S22 in Set C

The manifest is labeled "authoritative," but engine.md's `.chain()` code is the implementer's canonical reference. An implementer reading both would not know which engine to build. One must be deprecated, or their relationship explicitly scoped (e.g., "manifest is Phase 2b only; engine.md `.chain()` includes all phases").

**C2 — Spawning Grace Timing: "Birth-Kill" Possible Under Manifest Schedule**

Design intent (engine.md §3.2): "新生 drone 获得 SpawningGrace { remaining: 1 } 组件——在本 tick 内免疫所有伤害".  

Manifest schedule:
```
S03: spawn_system         ← drone created here
  ...
S07-S09: [Parallel Set A: attack, ranged_attack, heal]  ← combat runs HERE
S10: damage_application   ← damage applied HERE
S11: death_marker
  ...
S22: spawning_grace_system ← SpawningGrace added HERE (in Parallel Set C)
```

The spawn happens at S03, combat at S07-S10, but SpawningGrace is not applied until S22. A newly spawned drone is **fully vulnerable to all attacks in its birth tick** — damage_application (S10) can reduce hits to ≤0, death_marker (S11) would then mark it for despawn, and death_cleanup (S23) would despawn it. The drone is created and killed within the same tick.

**Remediation**: `spawning_grace_system` MUST run immediately after `spawn_system` (at S04), before any combat system. The manifest's placement at S22 breaks the stated design contract. The engine.md code (`spawning_grace_system.after(spawn_system).before(npc_combat_system)`) has the correct ordering; the manifest has the wrong ordering.

**C3 — Component R/W Matrix Is Incomplete (8 Components vs 30+)**

engine.md §3.4.6 Component/Resource R/W matrix covers only 8 components: Position, HitPoints, Fatigue, Energy/Carry, Cooldown, RoomCap, DeathMark, Owner.  

The manifest declares 27 systems operating on 30+ distinct component types: HackState, DrainState, OverloadState, DebilitateState, DisruptState, FortifyState, SpawningGrace, PendingDamage, ConstructionSite, ResourceLedger, ResourceAmount, FuelBudget, CommandQueue, WorldConfig, PlayerState, EventLog, PvpBlock, Controller (progress/level/downgrade_timer), and more.

The existing matrix cannot be used to verify parallel safety of the manifest's scheduling. A system reading from an unlisted component (e.g., `overload_system` reading `FuelBudget`) has no documented R/W relationship to verify against other systems.

**C4 — pvp_block_system Position: Incompatible Between Documents**

engine.md places `pvp_block_system` BETWEEN `death_mark_system` and `spawn_system` in the serial chain. This is a **RoomCap intermediate state** — death_mark has released room slots but spawn hasn't consumed them yet. engine.md §3.2 explicitly warns: "在 death_mark_system 与 spawn_system 之间的任何 ECS system 不得读取 RoomCap 做准入决策".  

The manifest places `pvp_block_system` at S24, AFTER `death_cleanup` (S23). This is a fundamentally different location with different semantics:  

- engine.md position: pvp_block sees entities post-death-mark (dead marked, cap slots freed), pre-spawn.  
- manifest position: pvp_block sees world after death_cleanup (all dead entities removed), post-spawn, post-combat.  

These are not minor ordering differences — they represent different design decisions about when PvP blocking is evaluated. The manifest placement (after death_cleanup) is safer (no dead-entity ambiguity), but contradicts engine.md's explicit placement rationale.

---

### High

**H1 — engine.md §3.5 Overstates FDB Transaction Scope**

engine.md §3.5: "整个阶段二包裹在 FoundationDB 事务中" (entire Phase 2 wrapped in FDB transaction).

05-persistence-contract.md clarifies: the FDB transaction (Phase C) only contains tick_head, manifest, hash_chain, and small entity mutations. Heavy objects (TickTrace blobs, snapshots) go to Object Store BEFORE the FDB commit. The FDB transaction does NOT wrap gameplay execution — it wraps persistence of already-computed results.

The engine.md phrasing misleads implementers into thinking they need to wrap their entire ECS simulate loop in an FDB transaction, which would be architecturally wrong (FDB transactions should be short-lived, <5s). Clarify: "Phase 2 execution produces results; FDB transaction atomically persists those results."

**H2 — JSON Canonical Serialization Not Specified for command_hash Tiebreaker**

01-tick-protocol.md §9.1: `command_hash = Blake3(command_json)` as the final sort tiebreaker. This requires that `command_json` be **canonical** — identical commands from different WASM SDKs (TypeScript, Rust, future Python) must produce identical JSON bytes.

No canonical serialization format is specified: key ordering, whitespace rules, number formatting (e.g., `amount: 50` vs `amount: 50.0`), enum representation. Two SDKs that produce semantically identical commands but byte-different JSON will produce different `command_hash` values, breaking the tiebreaker's determinism guarantee.

**H3 — regeneration_system Position Divergence Has Gameplay Impact**

engine.md serial chain: regeneration runs BEFORE combat_system. Manifest (Parallel Set C): regeneration runs AFTER aging_system (which is after combat).

Impact: if regeneration runs before combat, health regenerated in the current tick is available to absorb damage in the same tick's combat. If regeneration runs after combat, regenerated health is only available next tick. This is a gameplay-relevant difference that affects balance calculations.

**H4 — Phase 2a/2b Classification Table Has Stale References**

engine.md §3.2 Phase 2a/2b table says Phase 2b includes `status_advance` and `aging` in the serial chain (consistent with engine.md's `.chain()` code). The manifest moves `status_advance` into Parallel Set B and `aging` to S19 between Set B and Set C. The classification table in engine.md is inconsistent with the declared-authoritative manifest.

**H5 — Missing Systems in Manifest That Appear in engine.md Chain**

The following systems appear in engine.md's `.chain()` but not in the manifest's 27-system schedule:

- `rhai_rule_module_tick_start_system` / `rhai_rule_module_tick_end_system`
- `seed_rotation_system`
- `cargo_in_transit_system`
- `global_storage_system`
- `controller_repair_system`
- `depot_repair_system`
- `memory_upkeep_system`
- `drone_env_var_system`
- `onboarding_system`

If these are intentionally excluded from the manifest (because they run outside Phase 2b or are deferred to a separate scheduling layer), the manifest must document this scope boundary. If they were accidentally omitted, the manifest is incomplete.

---

### Medium

**M1 — Per-Player 2500ms Deadline vs Global 2500ms COLLECT Total: Parallelism Dependency**

engine.md §3.4.1: per-player sandbox deadline = 2500ms, global COLLECT budget = ≤2500ms. The global COLLECT budget is achievable only if the sandbox worker pool provides sufficient parallelism. With `pool_size = max(min_pool, active_players)` (engine.md §3.4.3), 500 active players need 500 workers to meet the budget — a significant resource requirement not documented in capacity planning.

**M2 — RoomCap Constraints Not Reflected in Manifest R/W Declarations**

engine.md §3.2: "RoomCap 的读写顺序为 death_mark: W(release) → spawn: R(check) + W(consume)" and "在 death_mark_system 与 spawn_system 之间的任何 ECS system 不得读取 RoomCap 做准入决策".  

The manifest: S11 (death_marker) writes DeathMark; S03 (spawn_system) reads Spawn/DroneTemplate/Room, writes Drone/Spawn/ResourceAmount. RoomCap is not listed in either system's R/W declaration. The manifest's S03 placement (before death_marker) also changes the RoomCap lifecycle — spawn happens before death_mark, so room caps are not released before new spawns are checked.

**M3 — Spawn body_cost Deduction-Refund Creates Dual-Phase Tracking Requirement**

02-command-validation.md §3.8: body_cost deducted in Phase 2a (inline apply), but spawn creation happens in Phase 2b (deferred). If Phase 2b spawn_system fails, body_cost must be refunded. This requires tracking "pending spawn deductions" as transient state across the Phase 2a→2b boundary. The document doesn't specify how this transient state survives the inline-to-deferred transition or interacts with FDB commit rollback.

**M4 — `spawning_grace_expiry_system` in engine.md Code Has No Manifest Equivalent**

engine.md code: `spawning_grace_expiry_system.after(combat_system).before(decay_system)`. The manifest has `spawning_grace_system` in Set C but no separate expiry system. If expiry is folded into the same system, this needs documentation. If expiry is missing, SpawningGrace components will never be cleaned up (memory leak).

**M5 — Recycle Command Variant Discrepancy**

02-command-validation.md §10.3: Recycle takes `(object_id, sequence)` — 2 fields, no spawn_id.
02-command-validation.md §3.9: Recycle takes `(object_id, spawn_id)` — 3 fields.
api-registry.md §1.1 #10: Recycle takes `target_id: EntityId` — 1 param.

Three different signatures for the same command. The api-registry (authoritative) lists only `target_id`; the command-validation spec lists `spawn_id` in §3.9 but omits it in §10.3.

---

### Low

**L1 — `TickValidationFailed` vs `SchemaViolation` Rejection Overlap**

02-command-validation.md §1.1: schema violations produce `TickValidationFailed`. api-registry.md §2.1: schema violations produce `SchemaViolation`. The api-registry is authoritative (35 RejectionReason variants), and `TickValidationFailed` is not in the registry. Harmonize.

**L2 — `NotMovable` RejectionReason Missing from api-registry.md**

02-command-validation.md §3.1 Move validation: "object_id 是 Drone（非 Structure/Resource）→ NotMovable". api-registry.md §2.2 does not list `NotMovable` in its 26 validation-level RejectionReason variants. Either add it, or fold into an existing code (e.g., `InvalidBodyPart` or a generic `InvalidTargetType`).

**L3 — `StillSpawning` RejectionReason Missing from api-registry.md**

02-command-validation.md §3.1 Move validation: "Drone 非 spawning 状态 → StillSpawning". Not in api-registry.md.

**L4 — Arena `tick_interval` 300ms vs no corresponding ENGINE changes**

tech-choices.md and engine.md §3.4.1 mention Arena at 300ms tick interval (10× faster than World's 3000ms). The manifest, persistence contract, and sandbox config all assume World timings. If Arena is a first-class mode, it needs explicit budgeting in the manifest (e.g., which systems skip? which run at reduced scope?).

**L5 — `world.mode != "development"` gate in 04-wasm-sandbox.md §9.5 references a config field not defined in the reviewed document set.**

---

## CrossCheck — Items Requiring Cross-Direction Verification

The following issues span multiple reviewer domains and require cross-checking against gameplay, security, and interface specs:

| # | Issue | Cross-check with | Why |
|---|-------|-----------------|-----|
| X1 | C2 Spawning grace timing — does gameplay spec expect birth-tick invulnerability? | Gameplay reviewer | If gameplay design is OK with birth-kill, then C2 is not a bug — but engine.md explicitly states the opposite |
| X2 | H3 regeneration position — does economic balance model assume pre-combat or post-combat regen? | Gameplay / Economy reviewer | Determines which document's ordering is authoritative for balance |
| X3 | C1 ECS schedule — which is the actually-implemented engine? | All reviewers | Multiple reviewers reading different docs will reach different conclusions about what the engine does |
| X4 | H2 canonical JSON — does the IDL/codegen pipeline guarantee canonical serialization? | Interface / SDK reviewer | If codegen enforces it, H2 is a documentation gap only; if not, it's a determinism bug |
| X5 | M1 worker pool sizing — is 500 concurrent processes within operational budgets? | Infrastructure / Security reviewer | Sandbox worker count directly impacts hosting cost and attack surface |
| X6 | H5 missing systems — are Rhai rule modules, seed rotation, and global storage in-scope for Phase 2b? | Gameplay / Mod reviewer | These systems affect mod scripting and economy; their scheduling matters |

---

## Summary

**4 Critical, 5 High, 5 Medium, 5 Low** issues found.

The single most impactful finding is C1 — the ECS schedule conflict between engine.md and the authoritative System Manifest. One document describes a 20-system flat chain; the other describes a 27-system spine+parallel architecture. This is not a "pick one" situation — it means implementers have no single truth to build against. The clean-slate phase should resolve this by: (1) declaring the manifest authoritative, (2) stripping the legacy `.chain()` code from engine.md and 01-tick-protocol.md, (3) ensuring the manifest's schedule is verified against the design contracts (spawning grace, RoomCap lifecycle, PvP block semantics).

C2 (spawning grace positioning) is a concrete correctness bug in the manifest that would allow drones to be killed in their birth tick — directly violating a documented design guarantee.
