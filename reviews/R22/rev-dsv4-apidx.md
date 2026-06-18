# R22 API/DX Review — DeepSeek V4 Pro

**Reviewer**: rev-dsv4-apidx (API/Developer Experience)
**Date**: 2026-06-18
**Phase**: Phase 1 Clean-Slate

---

## Verdict: CONDITIONAL_APPROVE

The API design demonstrates strong fundamentals — a machine-readable IDL as single source of truth, a well-structured RejectionReason taxonomy across 5 layers, comprehensive MCP tool security columns, and fixed-point type registry eliminating f64 non-determinism. However, critical type definition gaps in the IDL would produce incorrect codegen output, and several cross-document inconsistencies need resolution before SDK generation can be trusted. These are fixable at the design level without architectural rework.

---

## Strengths

1. **Single Source of Truth Architecture (S1)** — game_api.idl.yaml + auth_api.idl.yaml + economy.idl.yaml → auto-generated api-registry.md with CI enforcement. The IDL-first philosophy is exactly right for API/DX. Promising notes in §Appendix A show CI check mode (`--check`) that fails PRs on drift.

2. **Fixed-Point Type Registry (S2)** — All f64 fields replaced with integer representations (BasisPoints, ResourceRate_i64, milli_distance, micro_cost, MilliUnits). Eliminates cross-platform floating-point non-determinism at the type level. Well-documented scale factors and ranges.

3. **RejectionReason Taxonomy (S3)** — 47 canonical codes (35 game + 12 auth) organized into 5 layers (Pipeline → Validation → MCP → Runtime → Auth). The D2/B design decision to keep wire enum stable and push contextual detail to `debug_detail` is elegant. `detail_level` (competitive/practice/training) provides graded information disclosure.

4. **MCP Tool Security Columns (S4)** — Every tool declaration carries `required_scope`, `subject_source`, `replay_class`, `visibility_filter`, and `rate_limit_key`. This machine-readable security model enables automated access control codegen and audit verification. Capability profiles (onboarding/play/deploy/debug/admin/arena) provide sensible grouping.

5. **CommandIntent → RawCommand → ValidatedCommand Type Progression (S5)** — Clear, well-documented staged enrichment. WASM outputs only `sequence + action`; `player_id`/`tick`/`source` are server-injected. This prevents client-side spoofing at the type level.

6. **deploy_mutation Pattern (S6)** — WASM blob async upload to object store + small FDB manifest commit with `fdb_version_counter`. Clean separation of large I/O from transaction latency. Replay determinism through strict total ordering.

7. **Snapshot Truncation Contract (S7)** — Deterministic distance-bucket ordering with critical entity protection. Tick degraded marking for competitive integrity. Well-specified `omitted_categories` schema.

8. **Host Function ABI Error Priority Table (S8)** — 9-tier deterministic error priority ensuring replay-consistent error reporting. Exhaustive ordering from ERR_MEMORY_BOUNDS down to ERR_TIMEOUT.

9. **SwarmError JSON-RPC Envelope (S9)** — Unified error format with `retry_allowed`, `idempotency_key`, and optional `debug_detail`. Clean separation of canonical wire code from human-readable context.

10. **TickTrace Envelope Completeness (S10)** — 22 fields including all version hashes (world_config, mods_lock, engine_abi, core_idl, host_abi, canonical_codec, visibility_truncation). This is the right level of paranoia for replay determinism.

---

## Findings

### Critical

**C1: `object_id` Missing from IDL CommandAction Parameters**

The IDL defines CommandAction variants with only command-specific parameters (e.g., Move has `direction`, Harvest has `target_id`). However, every real CommandIntent JSON includes `object_id` — the acting drone:

```json
// commands.md example:
{ "type": "Move", "object_id": "d1", "direction": "North" }

// IDL definition:
- name: Move
  parameters:
    - name: direction    ← only this. No object_id.
      type: Direction4
```

All 19 core CommandAction variants in game_api.idl.yaml lack `object_id` as a parameter. The CommandIntent type defined in 02-command-validation.md §2.1 explicitly lists only `sequence` and `action` as top-level fields, with `object_id` embedded in `action`. But the IDL — the machine-readable canonical source for codegen — does not include it.

**Impact**: Codegen from the IDL would produce incorrect CommandIntent types missing `object_id`, producing runtime schema violations in WASM output. TypeScript SDK types for `MoveIntent`, `HarvestIntent`, etc. would all be wrong.

**Fix**: Add `object_id: EntityId (required: true)` as the first parameter of every core CommandAction variant in game_api.idl.yaml §1.1. Special attacks, global storage commands, Spawn, and Recycle also need it.

Severity: **Critical**

---

**C2: Host Function Signature Mismatch Across Documents**

`host_get_terrain` has two incompatible signatures:

| Document | Signature |
|----------|-----------|
| interface.md §5.1 | `(x: i32, y: i32) -> i32` |
| host-functions.md | `(x: i32, y: i32) -> i32` |
| api-registry.md §4.1 | `(room_id: u32, out_ptr: i32, out_len: i32) -> i32` |
| game_api.idl.yaml §4 | `(room_id: u32, out_ptr: i32, out_len: i32) -> i32` |

The IDL/registry signature uses a room-based + buffer ABI (consistent with other host functions). The interface/host-functions docs use a direct coordinate pair. These are **semantically different APIs** — one queries a whole room, the other queries one cell.

The IDL version is the canonical truth per the single-source-of-truth principle. But two reference documents contradict it.

**Impact**: SDK implementers reading host-functions.md would implement the wrong ABI. WASM modules compiled against the wrong signature would crash or produce garbage.

**Fix**: Update interface.md §5.1 and host-functions.md to match the IDL signature `(room_id: u32, out_ptr: i32, out_len: i32) -> i32`. If the simpler (x,y) API is desired for SDK ergonomics, add a separate host function or make the SDK wrapper translate — don't let the raw ABI docs diverge.

Severity: **Critical**

---

### High

**H1: IDL CommandAction Count Inconsistency (19 vs 21)**

| Source | Count | Notes |
|--------|-------|-------|
| game_api.idl.yaml `command_action.total_variants` | 19 | Indices 1–19 in the `variants` list |
| api-registry.md §1 header | 21 | 11 core + 2 global + 8 special |
| api-registry.md §1 actual rows | 21 | Leech(#20) + Fabricate(#21) included |

The IDL lists 19 variants under `command_action.variants` and places Leech/Fabricate in `command_action.custom_actions`. The registry counts them as variants 20–21. The discrepancy: are Leech and Fabricate core CommandAction enum variants, or custom actions routed through `CommandAction::Custom(type)`? The IDL says custom, the registry implies they're variants.

**Impact**: Codegen ambiguity — should the SDK generate Leech/Fabricate as first-class action types or as generic `CustomAction { type: "Leech", ... }`? Different choices produce incompatible wire formats.

**Fix**: Either (a) move Leech/Fabricate fully into `command_action.variants` with proper indices and mark them `tier: 2` with a feature flag, or (b) keep them in `custom_actions` and fix the registry count to 19 with a note that 2 custom actions exist. Document the `CommandAction::Custom(type)` routing explicitly in the IDL.

Severity: **High**

---

**H2: MCP Tool Count Inconsistency (54 vs 56)**

api-registry.md §3 header: "共计 **54** 个活跃工具 (game_api) + 11 个 Auth API 工具"

Actual subsection count: Onboarding(10) + Auth(2) + Play(16) + Deploy(7) + Debug(8) + Admin(6) + SDK(1) + Arena(4) + Resources(2) = **56**

game_api.idl.yaml `mcp_tools.total_tools`: **56**

The header is stale. The IDL and actual enumeration both say 56.

**Fix**: Update api-registry.md §3 header to "56".

Severity: **High**

---

### Medium

**M1: Optional Field Notation Undocumented**

Input schemas use `?` for optional fields (e.g., `topic: string?` for swarm_get_docs, `player_id: PlayerId?` for swarm_profile, `start_at: u64?` for swarm_tournament_create). But there is no formal specification of this convention — no `required: true/false` annotation like CommandAction parameters use, no `optional` key, no schema-level documentation.

**Impact**: Codegen cannot distinguish required from optional fields without ad-hoc `?` detection. This is fragile — a field name containing `?` could cause false positives, and a required field ending in `?` (unlikely but possible) would be misclassified.

**Fix**: Standardize MCP tool parameter schemas to use explicit `required: bool` or `optional: bool` annotations, matching the pattern already used in CommandAction variants. Or document the `?` convention in the IDL header with unambiguous parsing rules.

Severity: **Medium**

---

**M2: Type Primitives Not Defined in IDL**

These types are referenced throughout the IDL and registry but have no canonical definition:

| Type | Referenced In | Defined? |
|------|--------------|----------|
| `EntityId` | All CommandAction variants | No |
| `DroneId` | MCP tools | No |
| `PlayerId` | MCP tools, Auth | No |
| `RoomId` | MCP tools | No |
| `StructureId` | MCP tools | No |
| `ControllerId` | MCP tools | No |
| `SpawnId` | CommandAction | No |
| `DeployId` | deploy section | No |
| `Direction4` | Move command | Yes (registry §7, IDL §7) |
| `ResourceType` | Transfer/Withdraw | No |
| `StructureType` | Build | No |
| `BodyPart` | Spawn | No |
| `DamageType` | Debilitate | No |
| `Credential` | Auth tools | No |

Only `Direction4` is fully enumerated. The rest are referenced by name with no underlying type (u32? u64? string? newtype?), no valid range, and no serialization format.

**Impact**: SDK codegen cannot produce proper types for these without guessing. Is `EntityId` a `u64`? A UUID string? A newtype? The answer affects both TypeScript and Rust SDK type definitions.

**Fix**: Add a `primitive_types` section to game_api.idl.yaml defining each ID type with its underlying representation, serialization format, and valid range.

Severity: **Medium**

---

**M3: No Game API Version Negotiation Protocol**

The IDL has `api_version: "0.4.0"` and `swarm_get_info` returns a `version` string. But there is no documented protocol for:
- How a client discovers the server's API version before connecting
- How a client declares its expected API version
- What happens when versions mismatch (error code? graceful degradation?)
- Whether `swarm_sdk_fetch` returns SDK matching the server version or the requested version

**Impact**: When the API version bumps (e.g., 0.4.0 → 0.5.0 with a breaking change), AI agents and human players have no programmatic way to detect incompatibility. Silent deserialization failures or cryptic runtime errors result.

**Fix**: Add a required `api_version` field to the MCP handshake or `swarm_get_info` response. Define version compatibility semantics (semver? API version match required?). Add a `VersionMismatch` rejection code.

Severity: **Medium**

---

**M4: Refund Policy Table Has Duplicate Error Codes**

02-command-validation.md §7.1 lists `InsufficientResource` three times with conflicting refund policies:

```
| InsufficientResource | 退 50% fuel | 竞争导致——非玩家过错 |
| InsufficientResource | 退 50% fuel | 同上 |
| InsufficientResource | 不退 | 玩家应计算资源 |
```

Row 1 and 2 say 50% refund; row 3 says no refund. Same `InsufficientResource` code, different contexts, but the table doesn't distinguish which `InsufficientResource` scenario maps to which refund policy.

**Impact**: Implementers cannot determine the correct refund behavior from the spec. This is a runtime behavior specification gap.

**Fix**: Distinguish `InsufficientResource` refund cases by the command context (e.g., Transfer/Withdraw insufficient = 50% refund, Build insufficient = no refund). Or define sub-categories in `debug_detail` that drive refund logic.

Severity: **Medium**

---

**M5: `world.toml` Configuration Schema Undefined**

The design references `world.toml` extensively for configuration: custom_actions, special_effects, overload parameters, drone caps, storage limits, rule modules, etc. But there is no machine-readable schema for `world.toml` — no TOML schema, no JSON Schema, no IDL section.

**Impact**: SDK tooling cannot validate world configurations, cannot auto-generate configuration types, and cannot provide editor autocomplete for world.toml. This is a significant DX gap for server operators and mod developers.

**Fix**: Add a `world_config` section to game_api.idl.yaml (or a separate `world_config.idl.yaml`) defining all configurable parameters with types, defaults, ranges, and documentation. Generate a JSON Schema for CI validation.

Severity: **Medium**

---

### Low

**L1: SwarmError `code` Field Dual-Type**

The JSON-RPC envelope defines:
```json
"error": {
    "code": "RejectionReason (string)",   ← string
    ...
}
```
But also reserves `-32000` as a numeric code. The `code` field is described as a string in the schema but shown as numeric in the reserved code. JSON-RPC 2.0 uses integer error codes by convention; mixing string and integer in the same field is unusual.

**Impact**: SDK error parsers need to handle both `string` and `number` types for `error.code`. Minor implementation annoyance.

**Fix**: Either use only string codes and drop the `-32000` numeric reference, or adopt a hybrid: `code: integer` for JSON-RPC compliance + `swarm_error: string` in `data` for the canonical RejectionReason.

Severity: **Low**

---

**L2: SDK Codegen Pipeline Not Specified**

The design states "game_api.idl → codegen → SDK" (tech-choices.md §10) and defines `swarm_sdk_fetch` as the SDK delivery tool. But the codegen pipeline itself is unspecified:
- What codegen tool/script is used?
- What are the output targets (TypeScript interfaces? Rust structs? Both)?
- How are IDL breaking changes reflected in SDK versioning?
- What CI checks validate that SDK code matches the IDL?

**Impact**: The IDL is the single source of truth, but without a specified codegen pipeline, the connection from IDL to actual SDK code is hand-waved. This is a documentation gap, not a design flaw — the infrastructure is conceptually correct but needs specification.

**Fix**: Add a `specs/reference/codegen.md` defining the codegen pipeline, input/output contracts, and CI validation.

Severity: **Low**

---

**L3: `swarm_get_terrain` Listed as Both MCP Tool and Host Function**

The Play category in api-registry.md §3.2 includes `swarm_get_terrain` as an MCP tool (rate_limit: `— (host fn only)`, rate_limit_key: `host_only`), but terrain queries are also available as the WASM host function `host_get_terrain`. The MCP registration with `host_only` key suggests it's not actually callable via MCP — but it's present in the MCP tool list with a full security column row.

**Impact**: MCP tool discovery would list `swarm_get_terrain` as available, but it can't be called. Confusing for AI agents doing capability discovery.

**Fix**: Either remove `swarm_get_terrain` and `swarm_get_path` from the MCP tool list (keeping them in host functions only), or clarify that `host_only` tools are documentation-only and should not appear in MCP tool listings sent to clients. Add a `status: host_only` field to suppress from active tool discovery.

Severity: **Low**

---

**L4: `debug_detail` Length Discrepancy**

| Source | max_length |
|--------|-----------|
| game_api.idl.yaml rejection_reason.debug_detail | 512 bytes |
| api-registry.md §2 debug_detail | 512 bytes |
| interface.md §5.6 SwarmError data.debug_detail | "max 512 bytes" |
| api-registry.md §8 SwarmError data.debug_detail | "max 512 bytes" |
| api-registry.md §8 SwarmError data.rejection_detail | "max 512 bytes (optional)" |

`rejection_detail` and `debug_detail` both cap at 512 bytes. Are they the same field with different names? The SwarmError envelope includes both as separate optional fields. If they're different, their relationship is undocumented.

**Fix**: Clarify relationship between `rejection_detail` and `debug_detail`. If one is canonical wire data and the other is human-readable context, document which is which and when each is populated.

Severity: **Low**

---

## CrossCheck

Items I suspect may be issues but lie outside my API/DX direction scope:

- **CX1**: `object_id` is missing from IDL but present in every command example. Is `object_id` universal across all CommandAction variants, or are there commands that don't need it (e.g., TransferToGlobal)? → **Suggest Architect** verify the complete CommandIntent wire schema and ensure all fields (object_id, sequence, etc.) are consistently specified across IDL, commands.md, and the validation spec.

- **CX2**: Host function `host_get_terrain` has two incompatible signatures across documents. Are there other host functions with similar drift? → **Suggest Architect** audit all 5 host function signatures across all 4 documents (IDL, registry, interface.md, host-functions.md) and declare one canonical source.

- **CX3**: `world.toml` schema is undefined but heavily referenced. What is the complete set of configurable parameters, their types, defaults, and valid ranges? → **Suggest Game Designer** define the world.toml schema and **Architect** to ensure it covers all parameters referenced across engine.md, gameplay.md, and modes.md.

- **CX4**: Refresh token is "opaque" and "server-side" (api-registry.md §9). Does this mean stateless servers need shared token storage? → **Suggest Security** verify that the auth architecture works for multi-engine-instance deployments without shared mutable state bottlenecks.

- **CX5**: MCP simulate/dry-run isolation guarantees "independent RNG, seed = hash(authoritative_seed + 'simulate_preview' + drone_id + tick)". Is the authoritative_seed itself deterministic and replayable? → **Suggest Architect** verify RNG seed derivation chain from world seed through to simulate forks.

- **CX6**: Per-player drone cap is 500 in api-registry.md §5.1 but 50 in 02-command-validation.md §6 (`MAX_DRONES_PER_PLAYER = 50`). These are wildly different numbers. → **Suggest Architect** resolve the authoritative cap value and ensure all documents reference the same source.

---

## Error Handling Coverage

**Covered paths (excellent)**:
- Pipeline layer: `InvalidJson`, `SchemaViolation` — malformed input
- Validation layer: 26 codes covering ownership, resource, range, cooldown, body parts, construction limits, visibility
- MCP layer: `RateLimited`, `InvalidCertificate`, `NotAuthorized`
- Runtime layer: `FuelExhausted`, `TimeoutExceeded`, `SnapshotOverBudget`, `CommandBufferFull`, `ServerOverloaded`, `InternalError`
- Auth layer: 12 codes covering certificate lifecycle, session management, device registration, rate limiting

**Missing paths**:
- No explicit `VersionMismatch` error — clients cannot detect API version incompatibility programmatically
- No `FeatureDisabled` / `FeatureGated` error — Tier 2 features (Leech, Fabricate) and RFC features have no standard rejection when invoked on a server that doesn't support them
- No `WorldFull` / `ServerAtCapacity` error — the admission gating for hard cap (1000 players) has no corresponding API error code

**Error handling quality**: The `debug_detail` + `detail_level` design is excellent for security-conscious error reporting. Fuel refund anti-amplification rules (§7.2-7.3) are thorough and well-reasoned.

---

## Type Gaps Summary

| Gap | Location | Severity |
|-----|----------|----------|
| `object_id` missing from CommandAction IDL params | game_api.idl.yaml §1 | Critical |
| `host_get_terrain` signature mismatch | interface.md vs IDL | Critical |
| CommandAction variant count (19 vs 21) | IDL vs registry | High |
| MCP tool count (54 vs 56) | registry header vs actual | High |
| Optional field notation undocumented | IDL MCP schemas | Medium |
| Primitive ID types undefined | IDL + registry | Medium |
| API version negotiation missing | All docs | Medium |
| Refund policy `InsufficientResource` ambiguity | 02-command-validation.md | Medium |
| `world.toml` schema missing | All docs | Medium |
| `debug_detail` vs `rejection_detail` confusion | registry §8 | Low |
| `swarm_get_terrain` dual registration | registry + IDL | Low |

---

## Summary

The API foundation is strong — the IDL-first approach, type registry, rejection taxonomy, and deploy_mutation pattern are exactly right. The critical issues (C1, C2) are specification gaps, not architectural flaws — they can be resolved by updating the IDL and aligning cross-document references. Once C1 and C2 are addressed, SDK codegen from the IDL becomes viable. I recommend CONDITIONAL_APPROVE with the condition that C1, C2, H1, and H2 are resolved before Phase 2.
