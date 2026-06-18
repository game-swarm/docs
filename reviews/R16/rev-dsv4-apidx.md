# R16 API/Developer Experience Review — DeepSeek V4 Pro

> **Reviewer**: rev-dsv4-apidx (DeepSeek V4 Pro)
> **Phase**: Phase 1 Clean-Slate Independent Review
> **Date**: 2026-06-18
> **Documents Reviewed**: 9 files (design/README.md, design/interface.md, design/tech-choices.md, specs/reference/api-registry.md, specs/reference/commands.md, specs/reference/host-functions.md, specs/reference/mcp-tools.md, specs/core/02-command-validation.md, specs/core/09-snapshot-contract.md)

---

## Verdict: REQUEST_MAJOR_CHANGES

The api-registry.md is a strong step toward a single source of truth, but cross-document consistency has regressed since R15 in several dimensions. The MCP tool list divergence between interface.md and api-registry.md is catastrophic for any developer trying to build against these docs — two different teams would build two different integrations. Host function signatures are inconsistent across three documents. IDL format remains unspecified despite being central to the SDK codegen promise. These are blocking issues that must be resolved before implementation.

---

## R15 Follow-Up: What Was Fixed, What Wasn't

| R15 Finding | R16 Status |
|---|---|
| Move direction 4vs8 inconsistency (Critical) | **FIXED** — Direction4 enum definitively specified in api-registry.md §7; 8-direction marked Future RFC |
| RejectionReason three-document naming (Critical) | **PARTIALLY FIXED** — Naming convention established in api-registry.md §2, but commands.md defines ~27 rejection reasons absent from the registry |
| SendMessage zero-validation (Critical) | **FIXED** — Explicitly marked Future RFC in both api-registry.md §1 and commands.md |
| MCP tools schema missing (Critical) | **NOT FIXED** — Only swarm_sdk_fetch has partial schema; 45/46 tools lack inputSchema/outputSchema |
| Command enum inconsistency (High) | **NOT FIXED** — commands.md has SpawnDrone vs Spawn naming; registry parameter lists omit object_id |
| MCP tools list three-document inconsistency (High) | **REGRESSED** — interface.md and api-registry.md now have fundamentally different tool sets (~30+ non-overlapping tools) |
| host function untyped enum (High) | **FIXED** — Direction4 enum defined; but host function signatures now diverge across 3 documents |
| IDL format unspecified (High) | **NOT FIXED** — game_api.idl referenced but format never defined |

---

## Critical Issues

### C1: MCP Tool List Catastrophic Divergence — interface.md vs api-registry.md

**Severity**: Critical
**Documents**: design/interface.md §4.1 vs specs/reference/api-registry.md §3.1

These two documents define fundamentally different MCP tool sets. Both claim to list the authoritative tools, but they barely overlap:

**Tools in api-registry.md but NOT in interface.md** (34 tools):
`swarm_get_info`, `swarm_get_resources`, `swarm_list_rooms`, `swarm_get_room`, `swarm_list_drones`, `swarm_get_drone`, `swarm_get_code`, `swarm_get_leaderboard`, `swarm_get_events`, `swarm_get_path`, `swarm_get_visibility`, `swarm_list_controllers`, `swarm_get_controller`, `swarm_list_structures`, `swarm_get_structure`, `swarm_list_market_orders`, `swarm_get_messages`, `swarm_get_deploy_status`, `swarm_list_deployments`, `swarm_get_world_config`, `swarm_get_tick_trace`, `swarm_get_engine_stats`, `swarm_get_sandbox_profile`, `swarm_list_errors`, `swarm_get_state_checksum`, `swarm_dry_run`, `swarm_admin_challenge`, `swarm_admin_set_world_config`, `swarm_admin_rollback`, `swarm_admin_ban_player`, `swarm_admin_force_gc`, `swarm_admin_get_audit_log`, `resources/list`, `resources/read`

**Tools in interface.md but NOT in api-registry.md** (31 tools):
`swarm_inspect_entity`, `swarm_inspect_room`, `swarm_profile`, `swarm_dry_run_commands`, `swarm_explain_last_tick`, `swarm_get_docs`, `swarm_get_schema`, `swarm_get_available_actions`, `swarm_get_server_trust`, `swarm_register_challenge`, `swarm_submit_csr`, `swarm_renew_certificate`, `swarm_list_certificates`, `swarm_revoke_certificate`, `swarm_token_refresh`, `swarm_auth_revoke`, `swarm_change_password`, `swarm_request_password_reset`, `swarm_admin_create_password_reset`, `swarm_confirm_password_reset`, `swarm_register_passkey`, `swarm_recover_with_passkey`, `swarm_bind_email`, `swarm_delete_account`, `swarm_restore_account`, `swarm_cancel_account_deletion`, `swarm_federated_login`, `swarm_update_profile`, `swarm_tournament_precommit`, `swarm_tournament_create`, `swarm_tournament_status`, `swarm_match_result`

**Only ~14 tools appear in BOTH documents**: `swarm_get_snapshot`, `swarm_get_terrain`, `swarm_get_objects_in_range`, `swarm_get_world_rules`, `swarm_deploy`, `swarm_validate_module`, `swarm_rollback`, `swarm_list_modules`, `swarm_get_replay`, `swarm_simulate`, `swarm_get_economy`, `swarm_get_drone_efficiency`, `swarm_get_economy_trend`, `swarm_sdk_fetch`

This means ~68% of tools are defined in only one of the two documents. An SDK developer reading interface.md would implement auth, tournament, and debug tools; one reading api-registry.md would implement admin, drone listing, and resource management tools. Both would be wrong.

**Recommendation**: Declare api-registry.md as the single source of truth. Merge all interface.md-specific tools into the registry (or explicitly mark them as deprecated/removed). Delete the tool listing table from interface.md and replace with a pointer to the registry. Add a CI check that rejects any tool defined outside the registry.

---

### C2: Host Function Signature Inconsistency Across Three Documents

**Severity**: Critical
**Documents**: design/interface.md §5.1, specs/reference/api-registry.md §4.1, specs/reference/host-functions.md

Three documents define the same 5 host functions with different signatures:

**host_get_terrain**:
- interface.md: `(x: i32, y: i32) -> i32` — no out_ptr
- api-registry.md: `(room_id: u32, out_ptr: i32, out_len: i32) -> i32` — has out_ptr, different first param type
- host-functions.md: `(x: i32, y: i32) -> i32` — no out_ptr, matches interface.md

**host_path_find**:
- interface.md: `(from_x, from_y, to_x, to_y, out_ptr, out_len)` → 6 params
- api-registry.md: `(from_x, from_y, to_x, to_y, opts_ptr, opts_len, out_ptr, out_len)` → 8 params (extra opts_ptr/opts_len)
- host-functions.md: `(from_x, from_y, to_x, to_y, out_ptr, out_len)` → 6 params, matches interface.md

**host_get_world_rules**:
- interface.md: `(out_ptr: i32, out_len: i32) -> i32` → 2 params
- api-registry.md: `(rule_id_ptr: i32, rule_id_len: i32, out_ptr: i32, out_len: i32) -> i32` → 4 params (extra rule_id_ptr/rule_id_len)
- host-functions.md: `(out_ptr: i32, out_len: i32) -> i32` → 2 params, matches interface.md

In all three cases, the api-registry.md has MORE parameters than the other two documents. This means the registry is potentially the "newer" version with added features (room_id, opts, rule_id filtering), but the other docs haven't been updated. A WASM module compiled against host-functions.md will crash when calling registry-defined functions due to argument count mismatch.

**Recommendation**: Reconcile to a single authoritative signature set. The registry should be the truth source. Update interface.md and host-functions.md to match. Add ABI version checks so incompatible modules are rejected at deploy time rather than crashing at runtime.

---

### C3: RejectionReason Disjoint Sets — Registry (35) vs Commands (60+)

**Severity**: Critical
**Documents**: specs/reference/api-registry.md §2 vs specs/reference/commands.md

The api-registry.md §2 defines exactly 35 RejectionReason variants (2 pipeline + 26 validation + 3 MCP + 6 runtime, minus 2 pipeline = 35). However, commands.md lists dozens of rejection reasons that do not appear in the registry:

**In commands.md but NOT in registry**: `NotMovable`, `Fatigued`, `MissingBodyPart`, `TileBlocked`, `StillSpawning`, `OutOfRoom`, `NoPath`, `PathTooLong`, `InsufficientMoveParts`, `CarryFull`, `NotSource`, `SourceEmpty`, `TargetFull`, `TargetEmpty`, `NotYourRoom`, `TileOccupied`, `InvalidTerrain`, `TooManyConstructionSites`, `AlreadyFullHealth`, `FriendlyTarget`, `NotYourSpawn`, `BodyTooLarge`, `ExceedsRoomCapacity`, `NotFriendly`, `AlreadyHacked`, `InvalidDamageType`, `AlreadyDebilitated`

That's 27 extra rejection reasons with no registry registration. The registry's naming convention (§2 naming rules) doesn't even mention these variants. Meanwhile, some registry variants like `AuthContextInvalid`, `SafeModeActive`, `ConstructionLimitReached`, `GlobalStorageDisabled`, `TransferInProgress`, `ServerOverloaded`, `InternalError` don't appear in commands.md's validation matrices.

**Recommendation**: Run a full reconciliation. Either: (a) register all 27 missing variants in the registry, or (b) rename commands.md to use only registered variants. The registry must be the single source of truth per its own stated principle #1. Add CI enforcement: any RejectionReason used in validation code that isn't registered → build failure.

---

### C4: object_id Missing from api-registry CommandAction Parameter Definitions

**Severity**: Critical
**Documents**: specs/reference/api-registry.md §1 vs specs/reference/commands.md

The api-registry.md §1.1 CommandAction table defines parameters for each command but omits `object_id` (the acting drone) for most commands:

| Command | Registry Parameters | Commands.md Example |
|---------|-------------------|-------------------|
| Move | `direction: Direction4` | `"object_id": "d1", "direction": "North"` |
| Harvest | `target_id: EntityId` | `"object_id": "d1", "target_id": "s1"` |
| Attack | `target_id: EntityId` | `"object_id": "d1", "target_id": "e5"` |
| Build | `structure_type, x, y` | `"object_id": "d1", "x": 5, "y": 3` |
| Recycle | `target_id: EntityId` | `"object_id": "d1", "spawn_id": "s1"` |

`object_id` is the executing drone — a required field for every command. The registry's parameter column is incomplete without it. An IDL code generator consuming the registry would produce SDK types missing the actor field.

Additionally, **Recycle** has a parameter mismatch: registry says only `target_id`, but commands.md uses `object_id` + `spawn_id` (no `target_id`). The semantics differ — Recycle targets the drone itself (object_id) and a Spawn to return resources to.

**Recommendation**: Add `object_id: EntityId` as a universal first parameter to all CommandAction definitions. Fix Recycle to use `object_id: EntityId, spawn_id: SpawnId`. Make the registry's parameter column definitive.

---

## High Severity Issues

### H1: IDL Format Completely Unspecified

**Severity**: High
**Documents**: design/tech-choices.md §10, design/interface.md §4

Tech-choices.md states: "两者都走 `game_api.idl → codegen → SDK` 的自动化路径，API 一致性由 IDL 保证". Interface.md §4 states: "所有 MCP 工具必须具备 `inputSchema`、`outputSchema` 和 `error` schema，由 `game_api.idl` 生成".

But `game_api.idl` is never defined. Not its format (Protobuf? JSON Schema? Smithy? Custom DSL?), not its location (which repo? which path?), not its schema. Without this, the entire codegen pipeline is vaporware. The SDK codegen promise — a core architectural decision — has no specification to implement against.

**Recommendation**: Define the IDL format explicitly. Choose a format (recommend: JSON Schema for MCP compatibility, or Protobuf for WASM ABI stability). Specify the file location (e.g., `engine/game_api.idl`). Define the codegen pipeline: IDL → TypeScript types → Rust types → JSON Schema for MCP tools. Add a CI check that validates all schemas against the IDL.

---

### H2: Spawn/SpawnDrone Naming Inconsistency

**Severity**: High
**Documents**: specs/reference/api-registry.md §1.1 vs specs/reference/commands.md

- api-registry.md §1.1: Action name is `Spawn`
- commands.md section heading: "SpawnDrone"
- commands.md JSON example: `"type": "Spawn"`

The section heading uses `SpawnDrone` but the JSON wire format uses `Spawn`. In an IDL-driven system, the enum variant name must match the wire format. If the enum variant is `SpawnDrone` but the JSON tag is `"Spawn"`, the serialization mapping must be explicitly documented. As written, a code generator might produce `SpawnDrone` or `Spawn` depending on which document it reads.

**Recommendation**: Unify to `Spawn` everywhere (consistent with api-registry.md's table). Rename the commands.md section to "Spawn". If there's a distinction between `Spawn` (the action) and `SpawnDrone` (the intent), document the mapping explicitly.

---

### H3: Missing inputSchema/outputSchema for 45/46 MCP Tools

**Severity**: High
**Documents**: design/interface.md §4, specs/reference/api-registry.md §3.1

Interface.md mandates: "所有 MCP 工具必须具备 `inputSchema`、`outputSchema` 和 `error` schema". But the api-registry.md §3.1 table only provides informal parameter descriptions:

- `swarm_get_snapshot`: `{player_id}` — no type, no required/optional, no nested schema
- `swarm_get_drone`: `{drone_id}` — no type for drone_id
- `swarm_deploy`: `{player_id, drone_id, wasm_bytes, metadata}` — no type for wasm_bytes (base64? binary? reference?)
- `resources/list`: `{}` — but what's the output schema?

Only `swarm_sdk_fetch` has any schema detail (in interface.md §5.3, not even in the registry). Without formal schemas, MCP clients cannot validate requests, SDK codegen cannot produce typed clients, and the IDL promise is broken.

**Recommendation**: Define JSON Schema for every tool's input and output in the registry. This is a prerequisite for SDK codegen. Prioritize the onboarding and play profiles first. Add a CI gate: every registered tool must have a validated JSON Schema.

---

### H4: Simulate vs Dry-Run Tool Naming Divergence

**Severity**: High
**Documents**: design/interface.md §4.1 vs specs/reference/api-registry.md §3.1 vs specs/core/09-snapshot-contract.md §2

- interface.md §4.1 (Debug): `swarm_dry_run_commands`
- api-registry.md §3.1 (Debug): `swarm_dry_run`
- snapshot-contract.md §2.2: `swarm_dry_run` (as MCP method)
- api-registry.md §3.1 (Debug): also has `swarm_simulate`

Four different names/concepts across documents. Are `swarm_dry_run_commands` and `swarm_dry_run` the same tool? The snapshot-contract says `swarm_dry_run` is a deterministic variant of `swarm_simulate` with fixed RNG seed. But `swarm_dry_run_commands` in interface.md takes Command JSON (not WASM bytes). Are these two distinct tools or one with different names?

**Recommendation**: Define exactly which simulation tools exist. Proposed resolution: (1) `swarm_simulate` — NPC-only world, non-deterministic RNG; (2) `swarm_dry_run` — deterministic, takes WASM bytes + tick_count, returns trace. Remove `swarm_dry_run_commands` if it's the same tool, or define it distinctly with its own schema.

---

### H5: Capability Profile Definitions Don't Match Between Documents

**Severity**: High
**Documents**: design/interface.md §4.1a vs specs/reference/api-registry.md §3.2

Interface.md defines profiles with explicit tool lists (e.g., "onboarding: swarm_get_server_trust, swarm_register_challenge, swarm_submit_csr, swarm_sdk_fetch, swarm_get_docs"). The registry defines profiles by category (e.g., "onboarding: Onboarding, SDK, Resources"). Since the tool sets in the two documents are almost entirely disjoint (see C1), the profile definitions are also incompatible.

**Recommendation**: After resolving C1, redefine capability profiles in the registry only. Use category-based grouping. Delete the tool-list-based profile definitions from interface.md.

---

## Medium Severity Issues

### M1: SwarmError JSON-RPC Format Divergence — interface.md vs api-registry.md

**Documents**: design/interface.md §5.6 vs specs/reference/api-registry.md §8

interface.md §5.6 defines the error envelope with `data.swarm_error`, `data.details`, `data.retry_allowed`, `data.idempotency_key`. The api-registry.md §8 defines a simpler format: `error.code` as "RejectionReason", `error.message` (max 256 chars), `data.command_index`, `data.rejection_detail` (max 512 bytes). These are different error envelope shapes — a client parsing one would fail on the other.

**Recommendation**: Unify on one format. The interface.md format is richer (retry_allowed, idempotency_key), but the registry format is simpler. Choose one and delete the other.

---

### M2: Snapshot Format Ambiguity — Structured Binary vs JSON

**Documents**: design/interface.md §5 vs specs/core/09-snapshot-contract.md §1

Interface.md §5: "快照格式为结构化数据（非纯文本 JSON），房间分片保证拼接无歧义". Snapshot-contract.md §1.2: defines snapshot as JSON with `truncated`, `omitted_categories`, `entities`, `resources`, `events` fields. A structured binary format cannot simultaneously be JSON with string-keyed fields. If the snapshot is a binary protocol buffer with a JSON serialization layer, say so. If it's JSON throughout, don't claim it's "非纯文本 JSON."

**Recommendation**: Define the exact serialization format. If it's a binary format (e.g., FlatBuffers for zero-copy WASM access), specify the schema. If it's JSON, remove the "非纯文本 JSON" claim. The WASM linear memory ABI depends on this decision.

---

### M3: Host Function ABI Error Codes Not Mapped to RejectionReason

**Documents**: specs/reference/api-registry.md §4.5 vs §2

The registry §4.5 defines 9 host function error codes (-1 through -9: ERR_MEMORY_BOUNDS, ERR_ABI_VERSION, ERR_NOT_VISIBLE, etc.). These error codes are returned from host functions but are NOT represented in the RejectionReason enum (§2). A WASM module that gets ERR_MEMORY_BOUNDS on a host call — what rejection reason does the validator record? The validator pipeline (§2) only knows about FuelExhausted, TimeoutExceeded, SnapshotOverBudget, CommandBufferFull, ServerOverloaded, InternalError.

**Recommendation**: Either (a) map each host function ABI error to a RejectionReason variant, or (b) add a generic `HostFunctionError(code: i32)` variant to the RejectionReason enum. Without this mapping, error attribution in TickTrace is incomplete.

---

### M4: Rate Limit Definitions Inconsistent Between Documents

**Documents**: design/interface.md §4 (per-tool), specs/reference/api-registry.md §3.3 (per-category), specs/reference/mcp-tools.md (source-level)

Three different rate limiting models across three documents:
- interface.md: per-tool (e.g., "swarm_sdk_fetch: 5/min")
- api-registry.md §3.3: per-category (e.g., "读类: 50/tick, 部署类: 10/h")
- mcp-tools.md: source-level (e.g., "WASM: 1000, MCP_Query: 100")

These don't compose. If category "读类" is 50/tick but source "MCP_Query" is 100 tokens/s, which wins? Does a tool's individual limit override its category limit?

**Recommendation**: Define a clear rate limiting hierarchy: per-tool limit (most specific) > per-category limit > source-level budget > global limit. Express all limits in the registry. Remove rate limit tables from other documents.

---

### M5: CommandAction Enum Count Mathematics Doesn't Add Up

**Documents**: specs/reference/api-registry.md §1 vs specs/reference/commands.md

Commands.md states: "以下 15 种指令对应 `CommandAction` enum 的 15 个具体变体。第 16 个变体 `CommandAction::Custom(type)` 通过 `CustomActionRegistry` 路由到 8 种特殊攻击".

But the registry defines: 11 core + 2 Global + 6 special = 19 actions. If 6 special attacks route through Custom, then enum has 13 concrete + 1 Custom = 14 variants, not 15 or 16. The "8 种特殊攻击" in commands.md also contradicts the registry's 6 special attacks (+ 2 Tier 2 custom_actions Leech/Fabricate = 8 total, but those aren't in the Core enum).

**Recommendation**: Clarify the enum structure explicitly:
```
enum CommandAction {
    // 11 core
    Move { object_id, direction },
    Harvest { ... }, Transfer { ... }, Withdraw { ... },
    Build { ... }, Attack { ... }, RangedAttack { ... },
    Heal { ... }, Spawn { ... }, Recycle { ... }, ClaimController { ... },
    // 2 global
    TransferToGlobal { ... }, TransferFromGlobal { ... },
    // 6 special (also 13+6=19)
    Hack { ... }, Drain { ... }, Overload { ... },
    Debilitate { ... }, Disrupt { ... }, Fortify { ... },
    // extensibility
    Custom { action_id: String, params: Value },
}
```
State the exact variant count (19) and make it consistent everywhere.

---

## Low Severity Issues

### L1: replay_class Field Missing from Registry

interface.md §4.1 assigns `replay_class` to every tool (read_replay_safe, idempotent_mutation, non_idempotent_mutation, admin_critical). The registry's tool table doesn't include this field. If the registry is authoritative, this metadata is lost.

### L2: swarm_get_snapshot Has Conflicting Output Descriptions

api-registry.md §3.1: `{tick, entities, terrain, resources, truncated, omitted_count}`. But snapshot-contract.md defines the snapshot with `drone_id`, `omitted_categories` (not `omitted_count`), and `events` (not in registry output). The field names `omitted_count` vs `omitted_categories` differ.

### L3: No Deprecation/Versioning Policy for API Changes

The api-registry.md has `api_version: 0.1.0` and TickTrace records it, but there's no documented policy for: (a) how long old API versions are supported, (b) deprecation notice period, (c) migration guides for SDK consumers, (d) what constitutes a breaking vs non-breaking change. The tech-choices.md mentions "API 一致性由 IDL 保证" but versioning is not addressed.

### L4: Rust Enum Definitions Never Written in Rust Syntax

Throughout all documents, enums like Direction4, RejectionReason, CommandAction, DamageType, ResourceType, StructureType, BodyPart are described in tables but never defined in their native Rust syntax. For SDK codegen (Rust SDK), the actual enum definitions with discriminants and data variants need to exist.

### L5: swarm_sdk_fetch Output Schema Incomplete

interface.md §5.3 defines output as `{ sdk_code, type_definitions, examples, abi_version, min_engine_version }`. But: (a) `examples` is `string[]` — are these file paths, inline code, or URLs? (b) What format is `type_definitions`? JSON Schema? TypeScript .d.ts? (c) What is the MIME type of `sdk_code`? This ambiguity makes the AI agent's "self-bootstrapping" path unreliable.

### L6: TransferToGlobal/TransferFromGlobal Have No object_id But Require a Drone

Per §3.1 of the registry, Global storage commands list `resource` and `amount` but omit `object_id`. Yet the commands.md examples show no `object_id` for these either. If Global transfers don't require a specific drone, the design should state this explicitly. If they do, the parameter is missing.

---

## Strengths

1. **api-registry.md as Single Source of Truth is the right architecture.** The principle of one definitive registry with machine-readable tables, CI-enforceable cross-file consistency, and versioned API is exactly correct. The execution just needs to catch up to the principle.

2. **Deferred Command Model is well-designed.** The `tick(snapshot) → Command[]` pattern with server-side injection of player_id/source/tick via Source Gate is a clean separation of concerns. The CommandIntent → RawCommand → ValidatedCommand pipeline is well-specified in 02-command-validation.md.

3. **MCP-as-monitoring, not MCP-as-gameplay** is correctly enforced. No `swarm_move`, `swarm_attack`, etc. in MCP. AI agents write WASM code like humans. This fairness principle is consistently maintained across all documents.

4. **Snapshot Truncation Contract (09-snapshot-contract.md) is excellent.** The deterministic distance-bucket-based truncation with critical entity protection, competitive degraded-tick marking, and simulate isolation guarantees is thorough and implementable. The safe hint ladder (competitive/practice/training) is a thoughtful security measure.

5. **Host function fuel metering is well-specified.** Per-function base fuel + per-entity increment, per-call/per-player/global budgets, output size limits, and error priority in api-registry.md §4.2-4.5 provide a complete resource accounting model.

6. **Direction4 enum is now unambiguous.** The explicit `North=0, South=1, East=2, West=3` definition resolves the R14/R15 4vs8 direction ambiguity.

7. **Overload anti-lockout proof (02-command-validation.md §3.17)** is rigorous. The mathematical demonstration that no coalition of attackers can permanently lock a target's fuel budget is valuable for competitive integrity.

8. **Recycle refund tied to lifespan (02-command-validation.md §3.18)** closes an economic exploit. The proportional refund formula prevents players from recycling drones at end-of-life to recover full value.

---

## Type System Gaps

| Gap | Detail |
|-----|--------|
| No `Option<T>` / `Optional<T>` convention | Parameters like `opts_ptr` in registry host_path_find are implicitly optional but never marked as such. SDK codegen needs to know which fields are `Option<T>` vs required. |
| No `Result<T, E>` convention for host functions | Host functions return `i32` (0=success, negative=error code) but the error code mapping to RejectionReason is undefined (see M3). A typed error enum would improve SDK ergonomics. |
| EntityId type undefined | Used everywhere but never declared — is it u64? String? A newtype with Display? |
| ResourceType, StructureType, BodyPart, DamageType enums undefined | Referenced in parameter tables but never enumerated. SDK codegen can't produce these types. |
| `Value` type for Custom actions | Commands routed through `CommandAction::Custom` need a JSON `Value` type, but no specification of what schema `Value` follows. |

---

## Error Handling Coverage

| API Surface | Error Paths Defined? | Coverage |
|---|---|---|
| WASM tick() output validation | Schema violation, JSON parse failure, size limit, depth limit, forbidden fields | **Good** — 02-command-validation.md §1.1 covers output schema validation thoroughly |
| Per-command validation (15 types) | 02-command-validation.md §3.1-3.15 defines per-command error matrices | **Good** — each command has an explicit validation matrix with error codes |
| Special attack state machine | §3.16 defines priority, multi-hit, counter windows | **Good** |
| MCP tool invocation | Only swarm_sdk_fetch has error types (SDKNotFound, UnsupportedLanguage, RateLimited) | **Poor** — 45/46 tools lack error type definitions |
| Host function calls | ABI error codes defined (§4.5) but not mapped to RejectionReason | **Partial** — errors exist but don't integrate with the rejection pipeline |
| Snapshot truncation | Truncation markers defined, degraded-tick for competitive | **Good** |
| Simulate/dry-run | Isolation guarantees, not_predictive flag, authoritative=false | **Good** |
| Auth flow (CSR, cert renewal, recovery) | Error states not documented for any auth tool | **Missing** — 18 auth-related tools with zero error path documentation |
| Rate limiting | Over-budget behavior not specified — reject with 429? Silent drop? Queue? | **Missing** |

---

## CrossCheck — Items Requiring Cross-Direction Verification

These issues affect multiple review directions and should be checked by other reviewers:

1. **MCP Tool List Reconciliation (C1)** — Affects Architect (MCP architecture), Security (auth tools vs admin tools scope), Game Designer (are the right tools exposed for gameplay?)

2. **Host Function Signature Reconciliation (C2)** — Affects Architect (ABI stability), Security (memory bounds checking implications of different signatures)

3. **IDL Format Decision (H1)** — Affects Architect (codegen pipeline architecture), Security (schema validation as security boundary)

4. **CommandAction enum structure (M5)** — Affects Architect (ECS integration), Game Designer (are all needed actions represented?)

5. **SwarmError format unification (M1)** — Affects Security (error information leakage), Architect (API consistency)

6. **Snapshot serialization format (M2)** — Affects Architect (WASM memory layout), Security (truncation fairness)

---

## Summary

The R16 design has made real progress: the api-registry.md is a strong foundation, the deferred command model is clean, Direction4 is fixed, and the snapshot/truncation/simulate contracts are excellent. However, cross-document consistency has regressed in the MCP tool space — the interface.md and api-registry.md tool lists are irreconcilably different. Host function signatures diverge across three documents. The IDL format remains unspecified, making the SDK codegen promise unfulfillable. These are blocking issues that must be resolved before implementation.

**Priority fix order**:
1. Reconcile MCP tool lists (C1) — choose registry, merge everything there, delete duplicate tables
2. Reconcile host function signatures (C2) — registry wins, update other docs
3. Reconcile RejectionReason variants (C3) — register all 60+ variants in the registry
4. Add object_id to all CommandAction definitions (C4)
5. Define IDL format (H1)
6. Complete inputSchema/outputSchema for all 46 tools (H3)
7. Fix remaining naming/format inconsistencies (H2, H4, H5, M1-M5)
