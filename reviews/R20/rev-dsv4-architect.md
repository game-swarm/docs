# R20 Architecture Review — rev-dsv4-architect (DSV4)

**Date**: 2026-06-18 | **Reviewer**: DeepSeek V4 Pro (Architect Direction, Secondary)

---

## 1. Overall Verdict: APPROVE

All 6 R19 Blockers CLOSED. All 4 User Decisions CLOSED. No GAPs detected in the architecture domain.

---

## 2. Per-Item Verification

### R19 Blockers (Propagated Residue)

| ID | Status | Evidence |
|----|--------|----------|
| **B19-1**: RejectionReason canonical propagation | **CLOSED** | `api-registry.md` §2 defines 47 canonical codes (35 game_api + 12 auth_api) as wire enum with `debug_detail` field (512 bytes). `game_api.idl.yaml` §2 declares `total_canonical_codes: 35` with `debug_detail` contract and `detail_level` enum (competitive/practice/training). Both `engine.md` and `01-tick-protocol.md` reference `RejectionReason` by canonical name without redefining variants. The naming conventions are unified: `InsufficientResource` (singular), `ObjectNotFound`, `CooldownActive`, `NotVisibleOrNotFound` (safe merge), `NotAuthorized` (MCP-only). Canonical propagation confirmed across design docs and IDL. |
| **B19-2**: MCP/Auth tool namespace convergence | **CLOSED** | `api-registry.md` §3.4 defines 11 Auth API tools under `swarm_auth_*` namespace prefix with full security columns. `api-registry.md` §2.5 defines 12 auth-layer RejectionReason codes in namespace offset 1000+. `game_api.idl.yaml` changelog B3 confirms: "Add swarm_auth_login and swarm_auth_refresh to Auth category". api-registry.md is generated from 3 IDL sources (game_api + auth_api + economy). `auth_api.idl.yaml` exists as an independent machine-readable source — confirmed by api-registry.md header and changelog entries referencing auth_api `0.1.0`. |
| **B19-3**: deploy replay_class → deploy_mutation | **CLOSED** | `game_api.idl.yaml` §3 (swarm_deploy tool): `replay_class: deploy_mutation` (line 881). `game_api.idl.yaml` §10: `mechanism: deploy_mutation` with `fdb_version_counter` (u64, atomically incremented in FDB transaction). `api-registry.md` §3.2 Deploy: swarm_deploy `Replay Class: deploy_mutation`. `api-registry.md` §11: full deploy_mutation architecture with 4-step flow (Validate → Upload Blob → Commit Manifest → Activate). Changelog B5: "add deploy_mutation mechanism + fdb_version_counter to swarm_deploy output". The old `replay_class` no longer appears. |
| **B19-4**: IDL f64→fixed-point (11 fields) | **CLOSED** | `game_api.idl.yaml` §Type Registry: 7 fixed-point types (ResourceRate_i64, ProgressBps_i64, BasisPoints, EfficiencyBps, ConfidenceBps, milli_distance, micro_cost). `economy.idl.yaml` §1: 3 fixed-point types (BasisPoints, ResourceRate_i64, MilliUnits). `api-registry.md` §0 registers 8 fixed-point types with scale, range, and underlying type. Zero `f64` or `float` types remain in any IDL YAML file. Schema fields referencing these types: income_rate (ResourceRate_i64), progress (ProgressBps_i64), storage_tax (BasisPoints), efficiency (EfficiencyBps), confidence (ConfidenceBps), distance (milli_distance), cost (micro_cost), plus economy operation intermediate values (MilliUnits). `engine.md` §3.4.8 confirms: all resource/age/damage/progress use u64 or i64 fixed-point with saturating arithmetic and floor rounding. Cross-platform determinism guaranteed — no floating-point in any data path. |
| **B19-5**: worker pool 256 default + 1000 hard_cap | **CLOSED** | `game_api.idl.yaml` §5 limits: `worker_pool_max: 256` (runtime default), `worker_pool_hard_cap: 1000` (compile-time hard cap). `api-registry.md` §5.5: Worker pool max = 256, Worker pool hard cap = 1000. `engine.md` §3.4.2: `worker_pool_max = 256`, `worker_pool_hard_cap = 1000` with full derivation formulas. All three sources agree. `engine.md` §3.4.2 explicitly tags api-registry.md as the authoritative source: "权威容量定义：所有容量上限和准入策略以 api-registry.md §5 为准". |
| **B19-6**: Economy machine source | **CLOSED** | `economy.idl.yaml` exists as independent specification (api_version 0.1.0). Contains 7 resource operations: RecycleRefund (lifespan-proportional, 10-50%), StorageTax (4-tier: 0/1/5/20 bp), UpkeepDeduction (structures + controller), PvEAward (5 tiers), BuildCost (12 structure types with controller-level discount), SpawnCost (8 body parts), AlliedTransfer (tax-free). All amounts use integer types (u64/u32), all rates use BasisPoints (u32). `api-registry.md` §10 fully mirrors economy.idl.yaml. `engine.md` references economy formulas. Fixed-point types only — no f64 in any economy path. |

### User Decisions

| ID | Status | Evidence |
|----|--------|----------|
| **U1/A**: auth_api.idl.yaml independent | **CLOSED** | api-registry.md is generated from 3 IDL sources (game_api + auth_api + economy). Auth has its own namespace: 11 MCP tools (`swarm_auth_*`), 12 RejectionReason codes (1001-1012), 8 tick trace events, token envelope spec (JWT + opaque refresh), session lifecycle tools (login/logout/refresh/check/revoke), cert management tools (rotate/issue/revoke/list), device registration tools (register/list). Auth concerns fully separated from game_api concerns. |
| **U2/B**: economy.idl.yaml independent | **CLOSED** | economy.idl.yaml has its own api_version (0.1.0), its own fixed-point types (MilliUnits unique to economy), its own operation definitions (7 operations), its own limits section (§4), and its own changelog. Economy is a distinct specification domain — no game_api concepts leaked in. |
| **U3/A**: worker_pool default 256 + hard_cap 1000 | **CLOSED** | Same as B19-5. Confirmed in all three authoritative sources (game_api.idl.yaml §5, api-registry.md §5.5, engine.md §3.4.2). |
| **U4/A**: deploy_mutation replay_class | **CLOSED** | Same as B19-3. swarm_deploy uses `replay_class: deploy_mutation` with fdb_version_counter for strict total order. Confirmed in IDL and registry. |

### Key Changes (Derived Verification)

| Change | Status | Evidence |
|--------|--------|----------|
| New independent auth_api.idl.yaml | **CONFIRMED** | api-registry.md references it as source; auth content in its own registry sections |
| New independent economy.idl.yaml | **CONFIRMED** | economy.idl.yaml exists with 0.1.0, 7 ops, fixed-point types, independent limits |
| game_api.idl.yaml: f64→fixed-point | **CONFIRMED** | Type registry defines 7 fixed-point types; zero f64 in schema |
| game_api.idl.yaml: worker_pool 256+1000 | **CONFIRMED** | §5 limits; matches engine.md and api-registry.md |
| game_api.idl.yaml: deploy_mutation | **CONFIRMED** | §10 + swarm_deploy replay_class; replaces legacy replay_class |
| api-registry.md from 3 IDL sources | **CONFIRMED** | Header states: "generated from game_api, auth_api, economy"; changelog shows all 3 sources |
| RejectionReason canonical | **CONFIRMED** | 47 codes, debug_detail field, detail_level enum, naming conventions unified |
| MCP phantom cleanup | **CONFIRMED** | swarm_list_market_orders moved from active tools → RFC section; exact tool count = 46 active |
| MAX_PATH_LENGTH 500 | **CONFIRMED** | game_api.idl.yaml: `pathfinding_result_path_max: 500 nodes`; api-registry.md §5.2: "Pathfinding result path: 500 nodes max"; engine.md §3.4.2: "500 nodes max" |

---

## 3. Cross-Document Consistency Check

| Check | Result |
|-------|--------|
| api_version across sources | game_api `0.3.0` ↔ api-registry `0.3.0` ✅ |
| worker_pool across engine/IDL/registry | 256/1000 in all three ✅ |
| deploy_mutation across IDL/registry | deploy_mutation + fdb_version_counter in both ✅ |
| RejectionReason count | 35 (game_api) + 12 (auth_api) = 47 total; namespace offset 1000+ for auth ✅ |
| f64 prohibition | Zero f64 in game_api.idl.yaml schema, economy.idl.yaml explicitly prohibits, engine.md uses u64/i64 ✅ |
| Pathfinding budget | 100,000 nodes/tick across engine.md, game_api.idl.yaml, api-registry.md ✅ |
| Per-player drone cap | 500 across engine.md and game_api.idl.yaml ✅ |
| Hard cap players | 1000 across engine.md and game_api.idl.yaml ✅ |
| ECS system count | engine.md references 29 systems (6 inline + 23 deferred) ↔ 06-phase2b-system-manifest.md defines 29 systems (S01-S29) ✅ |
| Tick phase budget | engine.md §3.4.1 (SNAPSHOT≤50, COLLECT≤2500, EXECUTE≤400, COMMIT≤50, BROADCAST≤50 ms) ↔ 01-tick-protocol.md §1.4 (COLLECT timeout 2500ms, EXECUTE timeout 500ms) ✅ |

---

## 4. GAP

None. All 10 verification items (6 R19 Blockers + 4 User Decisions) are CLOSED with consistent cross-document evidence. All key changes are confirmed.

---

## 5. Architecture-Specific Notes

- **ECS Schedule Integrity**: `06-phase2b-system-manifest.md` remains the authoritative 29-system schedule. engine.md and 01-tick-protocol.md correctly reference it without redefining system order. The RoomCap intermediate-state protection (S07→S08 interval) is intact and R/W matrix confirms no reader in the gap.
- **Deterministic Contract**: Fixed-point migration (B19-4) completes the determinism contract — all floats removed from schema, engine, and economy paths. Combined with Blake3 XOF PRNG, canonical seed shuffle, and stable entity_id iteration, the replay determinism guarantee is structurally sound.
- **IDL Authority Chain**: api-registry.md → game_api.idl.yaml → codegen/SDK. The principle "conflict → IDL wins" is stated and the 3-source generation pipeline is documented. CI check (`--check` mode) enforces registry-IDL consistency.
- **Worker Pool Architecture**: 256 default / 1000 hard cap is properly gated with admission control formulas. The `min(max_pool, active_players)` dynamic sizing + fair-share slot allocation prevents CPU saturation from cascading to active players.
