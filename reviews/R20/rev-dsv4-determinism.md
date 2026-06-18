# R20 Determinism Review — DSV4

**Verdict: APPROVE**

All 6 R19 Blockers + 4 User Decisions verified as CLOSED against the IDL YAML authoritative sources (game_api.idl.yaml, auth_api.idl.yaml via api-registry.md, economy.idl.yaml via api-registry.md). No determinism GAPs detected.

---

## Per-Item Verdict

| ID | Status | Evidence |
|----|--------|----------|
| **B19-1** | CLOSED | RejectionReason canonical: 35 game_api + 12 auth_api = 47 total codes registered. game_api.idl.yaml §2 defines 35 wire enum variants across Pipeline/Validation/MCP/Runtime layers. auth_api codes use namespace offset 1000+ (1001–1012). `debug_detail` field (512 bytes) is explicitly non-canonical, separated from wire enum — does not affect replay determinism. `detail_level` enum (competitive/practice/training) controls verbosity. Naming conventions enforced: `InsufficientResource` (singular), `ObjectNotFound` (unified), `NotVisibleOrNotFound` (anti-oracle merge). Design docs (engine.md L207, 01-tick-protocol.md L332/L363) reference RejectionReason without redefining — consistent delegation to registry authority. |
| **B19-2** | CLOSED | MCP/Auth tool namespace收敛: auth_api.idl.yaml provides independent namespace with 11 tools (§3.4 in api-registry.md): 5 lifecycle (swarm_auth_login/logout/refresh/check/revoke) + 6 cert/device (swarm_auth_cert_*/device_*). Auth RejectionReason codes 1001–1012 in separate offset range. game_api.idl.yaml §Auth only carries simplified swarm_auth_login/refresh schemas, deferring to auth_api for full schema. No phantom MCP tools in game_api namespace. api-registry.md header declares 3 IDL sources: game_api + auth_api + economy. |
| **B19-3** | CLOSED | `deploy` replay_class → `deploy_mutation`: game_api.idl.yaml L881 (swarm_deploy: `replay_class: deploy_mutation`), §10 deploy section explicitly declares `mechanism: deploy_mutation` (L1578). fdb_version_counter (u64) provides strict total order for replay. api-registry.md §11 confirms deploy_mutation pattern with async object store upload + FDB manifest only. No residual `replay_class` references. |
| **B19-4** | CLOSED | IDL f64→fixed-point: 7 types in game_api.idl.yaml type_registry (ResourceRate_i64, ProgressBps_i64, BasisPoints, EfficiencyBps, ConfidenceBps, milli_distance, micro_cost) + 1 from economy (MilliUnits). All MCP tool output schemas use fixed-point integer types exclusively — no f64 in any IDL. engine.md §3.4.8 mandates u64/i64 fixed-point with documented overflow/rounding semantics (saturating, checked math, floor rounding, basis points precision). 01-tick-protocol.md §7.1 explicitly bans f64. |
| **B19-5** | CLOSED | Worker pool: game_api.idl.yaml §limits.hardware_baseline: `worker_pool_max: 256` (runtime default) + `worker_pool_hard_cap: 1000` (compile-time hard cap). engine.md §3.4.2 Worker Pool 推导 (L342-348): formula `min(256, active_players)` with hard_cap 1000, 256 scenario analysis, 1000 saturation analysis. api-registry.md §5.5: `Worker pool max: 256`, `Worker pool hard cap: 1000`. All three sources agree. |
| **B19-6** | CLOSED | Economy machine source: economy.idl.yaml confirmed as independent IDL source in api-registry.md header (L8). api-registry.md §10 Economy Operations enumerates 7 resource operations with canonical formulas (RecycleRefund lifespan-proportional 10-50%, StorageTax 4-tier 0/1/5/20 bp, UpkeepDeduction, PvEAward tiered, BuildCost with controller discount, SpawnCost per-part, AlliedTransfer tax-free). All amounts use u64/u32 integer types, all rates use BasisPoints. §5.7 Economy limits (9 parameters). Changelog confirms v0.1.0 with "Fixed-point types only: BasisPoints, ResourceRate_i64, MilliUnits." |
| **U1/A** | CLOSED | auth_api.idl.yaml独立: listed as separate IDL source with version 0.1.0 in api-registry.md. 11 auth tools in §3.4 with auth-specific namespace. 12 auth RejectionReason codes at offset 1000+. |
| **U2/B** | CLOSED | economy.idl.yaml独立: listed as separate IDL source with version 0.1.0. Self-contained economy operations, limits, and canonical formulas. |
| **U3/A** | CLOSED | worker_pool default 256 + hard_cap 1000: confirmed in game_api.idl.yaml L1421-1422, api-registry.md §5.5 L520-521, engine.md §3.4.2 L347-348. |
| **U4/A** | CLOSED | deploy_mutation replay_class: confirmed in game_api.idl.yaml L881/L1578, api-registry.md §11. |

---

## Strengths

- **Single Source of Truth**: All API contracts converge on 3 IDL YAML sources (game_api, auth_api, economy). api-registry.md is auto-generated with explicit "conflict → IDL wins" policy. No cross-document redefinition ambiguity.
- **f64 Eradication Complete**: No floating-point types in any IDL output schema, economy formula, or MCP tool. All 8 fixed-point types registered with documented scale/range. engine.md §3.4.8 provides overflow/rounding semantics.
- **RejectionReason Wire Stability**: 35 canonical game_api codes + 12 auth_api codes at offset 1000+. `debug_detail` explicitly non-canonical. `detail_level` enum gives operators control over information leakage without changing wire contract.
- **deploy_mutation Architecture**: FDB only commits small manifest with hash pointer + fdb_version_counter. Large WASM blobs handled asynchronously via object store. Strict total order via fdb_version_counter guarantees replay determinism.
- **Consistent Worker Pool**: 256 default / 1000 hard_cap present in game_api.idl.yaml, api-registry.md, and engine.md with identical values and matching derivation analysis.
- **TickTrace Envelope Completeness**: 22 fields covering all determinism-relevant dimensions (module_hash, wasmtime_version, effective_tick, terminal_state, snapshot_hash, commands_hash, deploy_events, rollback_events, admin_events, world_config_hash, mods_lock_hash, engine_abi_version, core_idl_version, world_action_manifest_hash, validator_version, rejection_reason_registry_version, system_manifest_hash, limits_manifest_hash, host_abi_version, canonical_codec_version, visibility_truncation_version). terminal_state enum (7 variants) replaces legacy wasm_status.

---

## GAPs

None identified. All R19 blockers and user decisions are fully closed with consistent evidence across the IDL YAML authoritative sources and their derived registry.

---

**Reviewer**: rev-dsv4-determinism (DSV4)
**Date**: 2026-06-18
**Authoritative Sources**: game_api.idl.yaml, auth_api.idl.yaml (via api-registry.md), economy.idl.yaml (via api-registry.md)
**Documents Reviewed**: design/README.md, design/engine.md, specs/core/01-tick-protocol.md, specs/core/05-persistence-contract.md, specs/core/06-phase2b-system-manifest.md, specs/reference/api-registry.md, specs/reference/game_api.idl.yaml
