# R44 Architecture Review — glm-architect

**Reviewer**: rev-glm-architect (GPT-5.5)
**Date**: 2026-06-30
**Scope**: All documents under `/data/swarm/docs/`
**Review Focus**: Architecture coherence, cross-layer integration, interface design, consistency, simplicity

---

## Verdict: CONDITIONAL_APPROVE

The Swarm documentation suite demonstrates exceptional architectural clarity for a deterministic MMO-RTS engine. The two-layer computation model (WASM COLLECT + Engine EXECUTE), static sharding, and deferred command model form a coherent and defensible architecture. Cross-document referencing is generally disciplined, with clear authority declarations (Resource Ledger for economy, phase2b-system-manifest for ECS scheduling, API Registry for interface schemas).

However, several non-blocking but substantive issues in interface consistency, duplicated definitions, and unresolved cross-layer contracts prevent an unqualified APPROVE. These findings are documented below with specific file references and recommended remediations.

---

## §1 Critical Findings (Blockers)

### C1. RangedAttack body part cost inconsistency across documents — severity: High

**Files affected**:
- `design/gameplay.md` line ~879: `RangedAttack` cost = `{ Energy = 150 }`
- `specs/core/world-rules.md` line ~368: `RangedAttack` cost = `{ Energy = 100 }`
- `specs/gameplay/api-idl.md` line ~203: `body_cost.RangedAttack = { Energy: 150 }`
- `design/gameplay.md` line ~725: `RangedAttack` base_damage = 25, range = 3

**Description**: The RangedAttack body part cost is `{ Energy = 150 }` in gameplay.md and api-idl.md, but `{ Energy = 100 }` in world-rules.md §7.1. Since both claim to define vanilla defaults, this is a direct numeric contradiction.

**Impact**: Implementation ambiguity — a developer following world-rules.md will use a different cost than one following gameplay.md or the IDL. The IDL is supposed to be the single source of truth via codegen, but world-rules.md presents its own `[[body_part_types]]` table with conflicting values.

**Fix**: world-rules.md §7.1 must reference the IDL `body_cost` table as authority, and its inline `[[body_part_types]]` example for RangedAttack must be corrected to `{ Energy = 150 }`. Alternatively, if 100 is the intended value, the IDL and gameplay.md must be updated. The IDL should be canonical for all body part costs.

### C2. PowerSpawn cost inconsistency — severity: High

**Files affected**:
- `design/gameplay.md` line ~199: `PowerSpawn` cost = `{ Energy = 5000 }`
- `specs/core/world-rules.md` line ~557: `PowerSpawn` cost = `{ Energy = 1200 }`
- `design/engine.md` RCL table line ~164: PowerSpawn listed as RCL 7 unlock, no cost specified

**Description**: PowerSpawn build cost is 5000 Energy in gameplay.md but 1200 Energy in world-rules.md. Same root cause as C1 — duplicated structure type definitions with divergent values.

**Impact**: Same as C1 — implementation will produce different economies depending on which document is followed.

**Fix**: Designate API Registry §10.2 (BuildCost) as the single authority for all structure costs, and have gameplay.md and world-rules.md reference it rather than re-declaring values.

### C3. RejectionReason count inconsistency — severity: High

**Files affected**:
- `specs/reference/api-registry.md` §2 header: "46 codes"
- `specs/reference/api-registry.md` §2 listing: codes numbered 1–46 (46 entries)
- `specs/gameplay/api-idl.md` lines ~91-138: RejectionReason enum lists 46 entries but includes `NotEligible` (which api-registry numbers as #46, under Auth layer) AND `DeviceNotRegistered`, `SessionLimitReached`, `MultiDeviceConflict`, `UnknownCredential` which are NOT in api-registry.md's canonical list
- `design/interface.md` line ~139: states "48 codes"
- `specs/core/command-validation.md` line ~154: states "48 个 canonical code"

**Description**: The RejectionReason wire enum count is stated as 46 in api-registry.md, 48 in interface.md and command-validation.md, but the IDL YAML lists a different set that includes auth-specific codes (`DeviceNotRegistered`, `SessionLimitReached`, `MultiDeviceConflict`, `UnknownCredential`) not present in api-registry.md's canonical 46. The enumeration is inconsistent across at least three documents.

**Impact**: SDK codegen will produce different error enums depending on which source is used. Wire protocol compatibility breaks if implementations disagree on canonical codes.

**Fix**: The IDL YAML must be the single source. api-registry.md is generated from it. The count must match exactly. interface.md and command-validation.md must reference the Registry count rather than hardcoding a number. The auth-specific codes (`DeviceNotRegistered`, `SessionLimitReached`, etc.) must either be added to api-registry.md's canonical list or removed from the IDL if they are obsolete (replaced by the certificate model).

---

## §2 Design Tensions (Inconsistencies, Conflicts)

### T1. Structure type list divergence between gameplay.md and world-rules.md — severity: Medium

**Files**: `design/gameplay.md` lines ~112-229 (13 types), `specs/core/world-rules.md` lines ~443-589 (15 types)

**Description**: gameplay.md lists 13 structure types; world-rules.md lists 15 (adds Road and Wall). wall and rampart exist in world-rules.md but not in gameplay.md's structure table. This isn't necessarily wrong (world-rules.md is the spec, gameplay.md is design overview), but gameplay.md claims "默认世界提供以下 13 种基础类型" while world-rules.md provides 15, creating confusion about the vanilla default.

**Impact**: Low — developer confusion about vanilla structure count. Non-blocking but erodes document trust.

**Fix**: gameplay.md should either list all 15 types or state "see world-rules.md §7.2 for the complete vanilla structure list" without claiming a specific count.

### T2. Fabricate cost divergence — severity: Medium

**Files**:
- `design/gameplay.md` line ~750: Fabricate cost = `2000 Energy + 500 Matter`
- `design/gameplay.md` line ~1210 (vanilla action_registry): Fabricate cost = `{ Energy = 2000 }` (no Matter)
- `specs/core/world-rules.md` line ~887: Fabricate cost = `2000E + 500 Matter`
- `specs/core/command-validation.md` line ~653: Fabricate cost = `2000 Energy + 500 Matter`

**Description**: The vanilla `[action_registry.vanilla.Fabricate]` TOML block in gameplay.md line ~1204-1210 defines `cost = { Energy = 2000 }` without Matter, while every other reference includes 500 Matter. Since the vanilla world uses single-resource Energy by default, the TOML block may be intentionally simplified, but this is not stated.

**Impact**: If a developer copies the TOML block, Fabricate will cost only 2000 Energy — the 500 Matter requirement is silently dropped.

**Fix**: The vanilla TOML block must include `cost = { Energy = 2000, Matter = 500 }` OR add a note that Matter is only required when the world defines Matter as a resource type, with the canonical cost being `special-attack-table.md`.

### T3. Leech cooldown inconsistency — severity: Medium

**Files**:
- `design/gameplay.md` line ~749: Leech cooldown = 150 tick
- `specs/core/world-rules.md` line ~887: Leech cooldown = 100 tick
- `specs/core/command-validation.md` line ~635: Leech — no cooldown listed, but registered via ActionRegistry

**Description**: Leech cooldown is 150 tick in gameplay.md but 100 tick in world-rules.md. The special-attack-table.md is supposed to be the canonical source, but the discrepancy exists in two design/spec documents.

**Impact**: Combat balance changes depending on which document is followed.

**Fix**: Both documents must reference special-attack-table.md as the canonical source and not redeclare cooldown values.

### T4. Depot cost divergence — severity: Medium

**Files**:
- `design/gameplay.md` line ~226: Depot cost = `{ Energy = 5000 }`
- `specs/core/world-rules.md` line ~588: Depot cost = `{ Energy = 600 }`

**Description**: Depot build cost is 5000 Energy in gameplay.md but 600 Energy in world-rules.md. This is a 8.3× difference — if 5000 is intended, Depot is an extremely expensive mid-game building; if 600, it's a cheap RCL2 structure.

**Impact**: Significant gameplay balance implication. Non-blocking for architecture but critical for game design.

**Fix**: Designate API Registry §10.2 as authority for all structure costs; correct whichever document has the wrong value.

### T5. `command-validation.md` §7.1 refund table duplication and potential conflict — severity: Low

**Files**: `specs/core/command-validation.md` lines ~467-477

**Description**: The refund table lists `InsufficientResource` three times with different refund policies (50% fuel for contention, 0% for player should-have-known). The table is ambiguous — it's unclear which row applies when. The canonical refund policy should be unambiguous per rejection code.

**Impact**: Implementation may apply incorrect refund rates.

**Fix**: Restructure the table to be keyed by `(RejectionReason, context)` with no duplicate keys, or separate contention refunds from validation refunds into two tables.

### T6. `validate_config` uses f64 in code sample — severity: Low

**Files**: `specs/core/world-rules.md` line ~1011: `if config.combat.damage_multiplier < 1`

**Description**: The entire project mandates fixed-point integers (basis points) and prohibits f64. But the `validate_config` code sample checks `damage_multiplier < 1`, implying a float comparison. The IDL defines `damage_multiplier` as `fixed<u32,4>` in world.toml but as `BasisPoints` in the registry.

**Impact**: Minor — code sample inconsistency. But it sets a bad precedent for implementation.

**Fix**: Change the code sample to `if config.combat.damage_multiplier_bps < 10000`.

### T7. Dispatched sandbox architecture shows gRPC in one diagram but NATS in another — severity: Low

**Files**:
- `specs/core/wasm-sandbox.md` line ~15: "gRPC (Unix socket)" between Engine and Sandbox Worker
- `specs/core/distributed-sandbox.md` line ~17: "NATS request-reply" between Engine and Sandbox Container
- `design/architecture.md` line ~79: "NATS queue-group 负载均衡"

**Description**: wasm-sandbox.md describes a local gRPC Unix socket model, while distributed-sandbox.md and architecture.md describe a NATS-based model. distributed-sandbox.md §8 explicitly states the local mode is a degenerate case of the distributed model, but wasm-sandbox.md doesn't acknowledge this relationship and presents gRPC as the sole communication method.

**Impact**: Developer confusion about which transport is canonical.

**Fix**: wasm-sandbox.md should note that the gRPC diagram represents the local/single-container mode and that production uses NATS (see distributed-sandbox.md). Add a cross-reference.

---

## §3 Suggestions (Improvements, Simplifications)

### S1. Consolidate body_part_types and structure_types definitions
**Problem**: Body part types and structure types are fully defined in at least three places each: gameplay.md, world-rules.md, and the IDL. Even when values match, the repetition creates maintenance burden and drift risk.

**Recommendation**: Designate `specs/reference/api-registry.md` (generated from IDL) as the single authority for all numeric costs and parameters. gameplay.md and world-rules.md should show conceptual examples only and explicitly defer to the Registry for canonical values. This is already partially done for RejectionReason and CommandAction — extend the pattern to body parts, structures, and damage types.

### S2. Clarify the relationship between `special_effects` in gameplay.md and world-rules.md
**Problem**: Both `design/gameplay.md` (lines ~1025-1118) and `specs/core/world-rules.md` (lines ~627-716) define `[[special_effects]]` with identical content. This is a pure duplicate that will inevitably drift.

**Recommendation**: world-rules.md should contain the canonical `[[special_effects]]` definition; gameplay.md should reference it.

### S3. Economy parameter table in Resource Ledger should be explicitly linked from economy-balance-sheet.md
**Problem**: economy-balance-sheet.md correctly references Resource Ledger §2 for formulas, but the balance sheet still contains specific numeric tables (maintenance costs, storage tax values) that could drift if Resource Ledger parameters change.

**Recommendation**: The balance sheet tables should include a "last verified against Resource Ledger §2 on [date]" note, or better, the tables should be generated from the same parameter source.

### S4. Add a canonical "document authority hierarchy" section
**Problem**: Documents frequently declare themselves as "唯一权威" or "权威源" for various topics, but there's no explicit hierarchy showing which document wins when two both claim authority. Currently:
- Resource Ledger §2 claims economic authority
- phase2b-system-manifest claims scheduling authority
- API Registry claims interface authority
- snapshot-contract claims truncation authority
- persistence-contract claims persistence authority

These don't overlap, but a reader doesn't know this without reading all documents.

**Recommendation**: Add a "Document Authority Map" to `docs/README.md` listing each domain and its canonical document, with the rule: "When two documents conflict, the domain authority document wins."

### S5. Simplify the tick execution manifest system count narrative
**Problem**: The document repeatedly states "31 systems" with parenthetical notes about what was added/removed. The count is correct, but the extensive change-history annotations (e.g., "新增 S22a", "修复：S22 移出 Parallel Set B") make the current state harder to read.

**Recommendation**: Present the 31-system schedule as a clean current-state table. Move all change-history annotations to a changelog section at the bottom, or remove them entirely since "design = target state" per the project's own principle.

### S6. Consider unifying the "command source" model with the "transport audience" model
**Problem**: `specs/security/command-source.md` defines Source types (WASM, MCP_Deploy, MCP_Query, Admin, etc.) while `specs/security/gateway-protocol.md` and `specs/security/mcp-security.md` define Transport types (Browser WS, REST, MCP Agent, etc.). The mapping between Source and Transport is implied but not explicitly tabulated.

**Recommendation**: Add a Source × Transport matrix to command-source.md showing which sources are valid on which transports. This would close the loop between the command pipeline and the gateway protocol.

### S7. `design/gameplay.md` is 1853 lines — consider splitting
**Problem**: gameplay.md is the largest single document (91KB), covering game rules, body parts, structures, damage types, special attacks, economy, visibility, SDK generation, mod system, and more. This scope makes it difficult to maintain and reference.

**Recommendation**: Split into focused documents: `game-rules.md` (Vanilla ruleset, RCL, room states), `combat.md` (damage types, body parts, special attacks), `economy.md` (resource model, global/local storage, anti-snowball). This aligns with the existing pattern of design/engine.md and design/modes.md being focused.

---

## §4 Cross-Reference Matrix

The following are issues I suspect but that fall outside the architecture review scope. They are flagged for other reviewer directions to check.

| ID | Issue | Target Direction | Check |
|----|-------|-----------------|-------|
| CX-1 | RangedAttack body part cost (150 vs 100) and PowerSpawn cost (5000 vs 1200) — numeric correctness | Economy/Balance | Verify intended vanilla values in special-attack-table.md and economy.idl.yaml |
| CX-2 | RejectionReason enum count (46 vs 48) and auth-specific codes in IDL (DeviceNotRegistered, SessionLimitReached, MultiDeviceConflict, UnknownCredential) — whether these are obsolete from the certificate model transition | Security | Check if these codes are still reachable in the certificate-based auth flow, or if they are dead codes from a removed OAuth model |
| CX-3 | Leech cooldown (150 vs 100 tick) and Fabricate cost (Matter inclusion) — combat balance correctness | Gameplay/Combat | Verify canonical values in special-attack-table.md; check if TOML example in gameplay.md §action_registry.vanilla is authoritative or illustrative |
| CX-4 | `validate_config` code sample uses float comparison `< 1` instead of bps `< 10000` — determinism violation in sample code | Determinism/Engine | Verify all code samples across docs use fixed-point, not f64; check if any actual spec (not just samples) uses float types |
| CX-5 | wasm-sandbox.md shows gRPC while distributed-sandbox.md shows NATS — verify the local mode is truly a degenerate case and not a separate implementation path | Engine/Infra | Check if codebase has two separate transport implementations or one unified implementation with a config switch |
| CX-6 | economy-balance-sheet.md §2.2 2-room scenario shows "Source 30/tick × 4" for optimized income but footnote says "20/tick × 1.0" — the 30/tick implies ×1.5 but the base says ×1.0; verify income math | Economy/Balance | Recalculate 2-room income: 4 harvesters × 20 base × 1.5 efficiency = 120, not 80; the table shows 80 for base and 138 for optimized (30×4+12=132, not 138) — verify all balance sheet arithmetic |
| CX-7 | `specs/core/world-rules.md` structure_types lists Road (hits=500, cost=10) and Wall (hits=10000, cost=50) but neither appears in gameplay.md or engine.md RCL unlock table — verify these are vanilla defaults | Gameplay | Check if Road/Wall are intentionally omitted from RCL table or if they are unlocked at RCL1 (Road in Screeps is available from start) |
| CX-8 | `specs/core/tick-protocol.md` §3.1 shuffle seed formula: `Blake3(tick_number || world_seed)` but `design/engine.md` §3.3 says `Blake3("shuffle" || world_seed || tick.to_le_bytes())` — different field orders and prefix | Determinism | Verify canonical shuffle seed formula; ensure all documents reference the same construction |
| CX-9 | `specs/security/visibility.md` §6.1 tests labeled "6.1, 6.2, 6.3" in heading but body says "§7" in some references — section numbering drift | Documentation | Fix section numbering in visibility.md test section |
| CX-10 | `specs/core/phase2b-system-manifest.md` S01 writes `ResourceLedger` but S29 `resource_ledger` also writes `ResourceLedger` — two writers for the same component; verify R/W matrix is correct (S01 may write per-operation deltas while S29 writes the final checksum) | Engine/Determinism | Verify S01's ResourceLedger write doesn't conflict with S29's unique writer status; if S01 writes are append-only event logs and S29 writes the checksum, document this distinction explicitly |

---

## Highlights

1. **Two-layer computation model is architecturally sound.** The clean separation between stateless WASM COLLECT (horizontally scalable) and serial EXECUTE (deterministic, single-writer per shard) is the correct architectural choice for a deterministic multiplayer engine. The documentation articulates this boundary with unusual clarity.

2. **Shadow Write + GlobalTickCommit** persistence model (tick-protocol.md §3.5) is well-designed. The content-addressed staging → manifest-only publish pattern eliminates the per-room commit TOCTOU window that plagued the previous model. The atomicity guarantee ("no partially committed tick") is properly maintained.

3. **31-system manifest with R/W matrix** (phase2b-system-manifest.md) is the most rigorous ECS scheduling specification I've seen in a game engine design document. The unique-writer contract for StatusState (S22 as sole writer, S16-S22b as buffer producers) is correct and eliminates parallel write hazards without sacrificing parallelism in buffer production.

4. **Snapshot Contract truncation design** is deterministically complete — the distance bucket + entity_id lexicographic + farthest-first removal algorithm is fully specified and reproducible. The Critical Entity Size Reserve (50% budget) ensures tactical legitimacy.

5. **Resource Ledger as single economic authority** is well-executed. The principle that all resource flows pass through one API with deterministic attribution is sound. The basis-points-only fixed-point mandate and the explicit prohibition of f64 in game state are correctly applied throughout most documents.

6. **API Registry codegen approach** is the right call for maintaining schema consistency across 4 SDK languages + MCP + REST. The CI gate ("IDL YAML ↔ Registry ↔ generated code three-way diff") is a strong correctness guarantee.

7. **Distributed sandbox as superset of local** (distributed-sandbox.md §8) is an elegant design — local mode is N=1 degenerate case, not a separate code path. This eliminates implementation bifurcation.

8. **Allied Transfer intercept mechanism** (snapshot-contract.md §3.2a) is well-specified as a final design. The success rate formula, escort defense, and deterministic RNG are complete and implementable without further design work.

---

*End of R44 Architecture Review — glm-architect*
