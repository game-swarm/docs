# R19 API/DX/IDL Closure Verification — rev-dsv4-apidx

**Reviewer**: rev-dsv4-apidx (DeepSeek V4 Pro — API/DX/IDL)
**Date**: 2026-06-18
**API Version**: 0.3.0
**Authority Source**: game_api.idl.yaml (specs/reference/)

---

## Overall Verdict: REQUEST_MAJOR_CHANGES

3 API/DX GAPs found. The YAML IDL (authoritative source) has been substantially updated with most R18 blocker/user-decision closures, but the derived Markdown documents (interface.md, mcp-tools.md, commands.md, 02-command-validation.md) have not been brought into alignment. Two divergence categories are systemic — they affect SDK codegen, CI validation, and implementation correctness.

---

## Per-Item Judgment Table

| ID | Status | Evidence |
|----|--------|----------|
| B1 | **GAP** | 02-command-validation.md uses ~23 non-canonical RejectionReason codes (Fatigued, MissingBodyPart, NotMovable, etc.) that are NOT in the YAML's 35 canonical wire enum. Per D2/B design, these should live in `debug_detail`, not as enum variants. commands.md has same divergence. |
| B2 | CLOSED | YAML defines 35 canonical RejectionReason codes + `debug_detail` (512 bytes) + `detail_level` enum (competitive/practice/training). api-registry.md §2 faithfully reflects this. Design is closed. |
| B3 | **GAP** | interface.md lists 50 tools, mcp-tools.md lists 52 tools — both near-totally divergent from YAML's canonical 46-tool registry. Interface.md has ~40 phantom tools not in YAML (swarm_get_docs, swarm_get_schema, swarm_get_available_actions, swarm_explain_last_tick, swarm_inspect_entity, etc.) and misses ~33 canonical YAML tools. Same pattern in mcp-tools.md. Auth category: YAML has 2 tools (swarm_auth_login, swarm_auth_refresh); both derived docs list ~20 legacy auth tools. |
| B4 | CLOSED | YAML TickTrace envelope unified with terminal_state enum (7 explicit variants replacing wasm_status), persistence section (§11), deploy_mutation mechanism (§10). Consistent across api-registry.md. |
| B5 | CLOSED | Security columns present in YAML for all 46 MCP tools: required_scope, subject_source, replay_class, visibility_filter, rate_limit_key. WebSocket security specs (seq+MAC, header signatures) in YAML §3.5 equivalent. Machine-readable. |
| B6 | N/A | Economy query tools in YAML (swarm_get_economy, swarm_get_drone_efficiency, swarm_get_economy_trend). Economy model parameters (tax rates, cost curves) outside API/DX scope — belong in design/gameplay.md. |
| B7 | CLOSED | All capacity limits machine-readable in YAML §5 (limits). 25 parameters including per-player drone cap, global entity cap, WASM memory, tick trace retention, hardware baseline, fair-share admission. CI-verifiable. |
| D1 | CLOSED | api-registry.md header: "本文档由 game_api.idl.yaml 自动生成。冲突时以 YAML 为准。" Covers all 11 sections matching YAML structure. Generator contract established. |
| D2 | CLOSED | 35 canonical codes + debug_detail field + detail_level enum defined in YAML §2. api-registry.md §2 reflects faithfully. Naming conventions documented (InsufficientResource singular, ObjectNotFound unified, NotVisibleOrNotFound merged safe code). |
| D3 | N/A | Recycle refund lifespan calculation (10-50%) is economy mechanics defined in 02-command-validation.md §3.18. Not an API contract — the API contract is Recycle exists with target_id parameter. YAML correctly defines the command without hardcoded refund formula. |
| D4 | N/A | Storage tax tiered rates (0/1/5/20bp) are economy model parameters. YAML defines swarm_get_economy tool with storage_tax output field (f64). Tax tiers themselves belong in economy design docs, not API surface. |
| D5 | CLOSED | async_object_store_upload defined in YAML §11 (persistence): blob types (wasm_module 64MB, replay_recording 1GB, snapshot_archive 256MB), fire-and-forget invocation, exponential backoff retry, FDB manifest record schema, fdb_version_counter ordering. |
| D6 | N/A | soft_launch 3-stage PvP not present in any IDL or API doc. Belongs to gameplay/modes design. |
| DA1 | CLOSED | deploy_mutation replay_class (idempotent_mutation) defined in YAML §10. swarm_deploy output includes fdb_version_counter for deterministic replay ordering. Deploy flow documented: validate→upload blob (async)→commit manifest (FDB)→activate (tick boundary). |
| DA2 | **GAP** | 11 f64 types remain in YAML IDL: income_rate (L484), distance (L675), cost (L676), progress (L718), income (L778), expenses (L779), storage_tax (L780), maintenance (L781), efficiency (L794), confidence (L1008), base_value (L1168). f64→fixed-point conversion not applied. Affects deterministic replay — floating-point is non-deterministic across architectures. |
| DA3 | CLOSED | Worker pool max=256 defined in YAML §5 limits.hardware_baseline. Worker pool size formula: min(max_pool, active_players). api-registry.md §5.5 consistent. |

---

## Detailed GAP Analysis

### GAP-1: B1 Residual — RejectionReason Dual-Write (02-command-validation.md, commands.md)

**Location**: specs/core/02-command-validation.md §3 validation matrices; specs/reference/commands.md §拒绝原因 table

**Problem**: Both documents use rejection codes that are NOT in the YAML's 35 canonical wire enum. The validation matrices directly reference codes like:

```
Fatigued, MissingBodyPart, NotMovable, TileBlocked, StillSpawning,
CarryFull, NotSource, SourceEmpty, TargetFull, TargetEmpty, NotYourRoom,
TileOccupied, InvalidTerrain, TooManyConstructionSites, AlreadyFullHealth,
FriendlyTarget, NotYourSpawn, BodyTooLarge, ExceedsRoomCapacity, NotFriendly,
AlreadyHacked, InvalidDamageType, AlreadyDebilitated, MainActionQuotaExceeded,
OutOfRoom, NoPath, PathTooLong, InsufficientMoveParts
```

**Canonical status**: Per D2/B design, these 25+ codes are NOT canonical RejectionReason enum variants. They are debug_detail content — non-canonical contextual detail strings that accompany the 35 wire enum codes. For example:

- `Fatigued` → wire code `CooldownActive` + debug_detail `"Fatigued: action cooldown N ticks remaining"`
- `MissingBodyPart` → wire code `NotEnoughBodyParts` + debug_detail `"MissingBodyPart: requires Move"`
- `TileBlocked` → wire code `PositionOccupied` + debug_detail `"TileBlocked: Wall at (5,3)"`

**Impact**: CI validation of "未注册则拒绝" (reject unregistered) will block implementation if the validation spec uses codes outside the 35-canonical set. Codegen from canonical enum will miss these validation paths.

### GAP-2: B3 — MCP Tool Namespace Divergence (interface.md, mcp-tools.md)

**Location**: design/interface.md §4.1; specs/reference/mcp-tools.md

**Scope**: Near-total divergence. interface.md has 50 tools, mcp-tools.md has 52 tools. Only ~10 overlap with YAML's 46 canonical tools.

**Phantom tools in interface.md** (not in YAML canonical registry):
```
swarm_get_docs, swarm_get_schema, swarm_get_available_actions,
swarm_get_objects_in_range, swarm_get_server_trust, swarm_get_player_status,
swarm_explain_last_tick, swarm_inspect_entity, swarm_inspect_room,
swarm_profile, swarm_dry_run_commands, swarm_rollback, swarm_list_modules,
swarm_submit_csr, swarm_register_challenge, swarm_renew_certificate,
swarm_list_certificates, swarm_revoke_certificate, swarm_token_refresh,
swarm_auth_revoke, swarm_change_password, swarm_request_password_reset,
swarm_admin_create_password_reset, swarm_confirm_password_reset,
swarm_register_passkey, swarm_recover_with_passkey, swarm_bind_email,
swarm_delete_account, swarm_restore_account, swarm_cancel_account_deletion,
swarm_federated_login, swarm_update_profile,
swarm_tournament_precommit, swarm_tournament_create, swarm_tournament_status,
swarm_match_result,
swarm_move (forbidden), swarm_attack (forbidden), swarm_build (forbidden)
```

**Canonical YAML tools MISSING from interface.md** (~33 tools):
```
swarm_get_info, swarm_get_resources, swarm_list_rooms, swarm_get_room,
swarm_list_drones, swarm_get_drone, swarm_get_code,
swarm_auth_login, swarm_auth_refresh,
swarm_get_leaderboard, swarm_get_events, swarm_get_path, swarm_get_visibility,
swarm_list_controllers, swarm_get_controller, swarm_list_structures,
swarm_get_structure, swarm_get_messages,
swarm_get_deploy_status, swarm_list_deployments,
swarm_get_world_config, swarm_get_tick_trace, swarm_get_engine_stats,
swarm_get_sandbox_profile, swarm_list_errors, swarm_get_state_checksum,
swarm_dry_run,
swarm_admin_challenge, swarm_admin_set_world_config, swarm_admin_rollback,
swarm_admin_ban_player, swarm_admin_force_gc, swarm_admin_get_audit_log,
resources/list, resources/read
```

**Impact**: SDK codegen from YAML will produce types for 46 tools, but interface.md describes 50 different tools. Developers reading interface.md will try to call phantom tools. MCP client implementations will be wrong.

### GAP-3: DA2 — f64 Remaining in YAML IDL

**Location**: game_api.idl.yaml (11 instances across 7 tools)

| Line | Field | Tool |
|------|-------|------|
| 484 | income_rate: f64 | swarm_get_resources |
| 675 | distance: f64 | swarm_get_path |
| 676 | cost: f64 | swarm_get_path |
| 718 | progress: f64 | swarm_get_controller |
| 778 | income: f64 | swarm_get_economy |
| 779 | expenses: f64 | swarm_get_economy |
| 780 | storage_tax: f64 | swarm_get_economy |
| 781 | maintenance: f64 | swarm_get_economy |
| 794 | efficiency: f64 | swarm_get_drone_efficiency |
| 1008 | confidence: f64 | swarm_simulate |
| 1168 | base_value: f64 | resources/read |

**Impact**: Floating-point types in the IDL prevent deterministic cross-platform replay. IEEE 754 allows implementation-defined behavior for subnormals, NaN payloads, and rounding modes. Fixed-point (e.g., i64 with implicit decimal scaling) is required for deterministic economic calculations.

---

## CLOSED Items — Confirmation Details

### B2 (RejectionReason closure)
YAML §2 defines 35 canonical codes across 4 layers (Pipeline/Validation/MCP/Runtime) with debug_detail (512 bytes) and detail_level enum. The `InsufficientResource` singular form, `ObjectNotFound` unified form, and `NotVisibleOrNotFound` merged safe code are enforced. Naming conventions section ensures consistency.

### B4 (Tick/Trace/Persistence unified)
TickTrace envelope (22 fields) with terminal_state enum (7 variants: Success/FuelExhausted/TimeoutExceeded/SnapshotOverBudget/CommandBufferFull/InternalError/NotExecuted). Deploy uses deploy_mutation with fdb_version_counter. Persistence uses async_object_store_upload decoupled from FDB commit path.

### B5 (Security fields in machine source)
All 46 MCP tools carry 5 security columns. WebSocket security (Agent WS seq+MAC, Browser WS read-only, Replay WS read-only+seek) defined with header-level signature spec (Swarm-Request-Signature: method, uri, timestamp, seq, body_hash).

### D1 (api-registry.md full generation)
api-registry.md header declares YAML as single source of truth. All 11 YAML sections faithfully rendered. Generator contract: "手写修改将被覆盖" (hand edits will be overwritten).

### D5 (blob async upload)
Persistence contract: fire-and-forget upload, immediate object_store_key acknowledgment, exponential backoff retry (max 3), FDB manifest record {blob_hash, object_store_key, size, uploaded_at, status}. Three blob types with size limits and retention policies.

---

## Cross-Check Recommendations

The following items are outside API/DX scope but warrant verification by other reviewers:

1. **Economy model parameters** (→ rev-dsv4-economy): D3 (Recycle refund 10-50%) and D4 (Storage tax 0/1/5/20bp) are economy mechanics, not API surface. Verify in design/economy-balance-sheet.md.

2. **Soft launch PvP staging** (→ rev-dsv4-gameplay): D6 (soft_launch 3-stage PvP) — not in any IDL doc. Verify in design/modes.md.

3. **auth_api.idl.yaml absence**: The task directive lists this file but it does not exist in the R19 review directory. Auth tools (swarm_auth_login, swarm_auth_refresh) are folded into game_api.idl.yaml. Verify whether a separate auth IDL was intentionally merged.

---

## Remediation Summary

To close the 3 GAPs:

1. **B1**: Update 02-command-validation.md validation matrices to use the 35 canonical RejectionReason codes, with debug_detail strings for context. Update commands.md rejection reason table accordingly.

2. **B3**: Regenerate interface.md and mcp-tools.md from the YAML IDL (or mark them as deprecated and point readers to api-registry.md §3). Remove phantom tools, add missing canonical tools, align categories to YAML capability profiles.

3. **DA2**: Replace all 11 f64 fields in game_api.idl.yaml with fixed-point representation (e.g., i64 with documented decimal scaling factor). Update api-registry.md to reflect the change.

---

*Review conducted against game_api.idl.yaml v0.3.0 as sole authority source. No /data/swarm/ repositories, prior reviews, or ROADMAP consulted.*
