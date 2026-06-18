# R19 Game Design Review — DSV4 (Game Designer)

**Reviewer**: rev-dsv4-designer  
**Date**: 2026-06-18  
**Documents reviewed**:
- `/tmp/swarm-review-R19/design/README.md`
- `/tmp/swarm-review-R19/design/gameplay.md`
- `/tmp/swarm-review-R19/design/modes.md`
- `/tmp/swarm-review-R19/design/interface.md`
- `/tmp/swarm-review-R19/specs/gameplay/08-api-idl.md`
- `/tmp/swarm-review-R19/specs/reference/api-registry.md`

---

## 1. Overall Verdict: REQUEST_MAJOR_CHANGES

**Rationale**: 4 GAPs found — exceeds the ≤2 threshold for CONDITIONAL_APPROVE. One GAP (B1) is a consensus blocker inherited from R18; the other three (B3, D3, D6) are user-decided design closures that remain unaddressed.

---

## 2. Item-by-Item Judgment Table

### R18 Consensus Blockers

| ID | Status | Evidence |
|----|--------|----------|
| B1 | **GAP** | YAML IDL (§2, lines 65-110) lists **44 RejectionReason entries** with verb/state names (Fatigued, TileBlocked, MissingBodyPart, NotMovable, etc.), while api-registry.md §2 declares **35 canonical codes** with unified naming (CooldownActive, PositionOccupied, NotEnoughBodyParts, etc.). The YAML says `权威定义见 API Registry §2 — 35 变体` — self-contradiction: YAML lists 44 but self-cites 35. api-registry.md claims to be auto-generated from YAML, yet the counts and naming diverge. **Root**: the YAML IDL body was never regenerated/synced to reflect the 35-code canonical design. |
| B2 | CLOSED | api-registry.md §2 now has 35 canonical codes across 4 layers (Pipeline/Validation §2.1-2.2, MCP §2.3, Runtime §2.4), `debug_detail` field documented (512 bytes, max), `detail_level` enum (competitive/practice/training) with explicit semantics. Per R17 D2/B, this satisfies the canonical+debug_detail closure. |
| B3 | **GAP** | design/interface.md inline tool listing (§4.1) references tools absent from the authoritative api-registry.md §3 (46 active tools): `swarm_rollback`, `swarm_list_modules`, `swarm_explain_last_tick`, `swarm_inspect_entity`, `swarm_inspect_room`, `swarm_profile`, `swarm_dry_run_commands`, `swarm_get_docs`, `swarm_get_schema`, `swarm_get_available_actions`, ~18 auth tools (swarm_submit_csr, swarm_register_challenge, swarm_get_server_trust, swarm_renew_certificate, etc.), 4 tournament tools. While design/interface.md defers to api-registry.md as authority, the inline listing retains the legacy namespace — **3独立名称空间的残影未清理** (design inline vs IDL YAML vs api-registry). |
| B4 | CLOSED | TickTrace envelope (api-registry.md §6, 22 fields including terminal_state enum), persistence layer (api-registry.md §11, async_object_store_upload), deploy_mutation (api-registry.md §10, fdb_version_counter). All three subsystems now have documented, deterministic, replay-verifiable contracts. |
| B5 | CLOSED | Security-relevant fields now in machine source: replay_class, visibility_filter, required_scope, subject_source, rate_limit_key all in api-registry.md §3.2 tool tables. §3.5 WebSocket channel security (Agent WS seq+MAC, Browser WS read-only, Replay WS read+seek). |
| B6 | CLOSED | Economy single-source established in gameplay.md §8 (Faucet/Sink/Transfer/Lockup/Unlock classification), with resource flow tables, anti-snowball contract, new-player resource gate, global storage progressive tax. api-registry.md §9 ResourceOperation provides machine-readable resource flow mapping. single-source closure achieved. |
| B7 | CLOSED | Capacity contracts in api-registry.md §5 with 25+ parameters: per-player drone cap (500), global entity cap (50,000), commands/player/tick (100), WASM memory (128 MB/64 MB), sandbox CPU, pathfinding budget (100,000 nodes), worker pool (256 default), per-player fair-share admission (§5.6). All in machine-readable tables. |

### R18 User Decisions

| ID | Status | Evidence |
|----|--------|----------|
| D1 | CLOSED | api-registry.md covers 11 sections: CommandAction (19), RejectionReason (35), MCP Tools (46), Host Functions (5), Capacity Limits, TickTrace Envelope (22), Direction4, SwarmError, ResourceOperation, Deploy (deploy_mutation), Persistence (async_object_store_upload). Comprehensive single-source registry. Markdown auto-generated from YAML IDL pipeline per header declaration. |
| D2 | CLOSED | RejectionReason: 35 canonical code (wire enum), debug_detail (512 bytes non-canonical context), detail_level (competitive/practice/training). Per D2/B: canonical codes stable, rich context goes into debug_detail. |
| D3 | **GAP** | Recycle refund is **flat 50%** regardless of drone lifespan. Evidence: (a) gameplay.md line 107: `回收 drone 获得 50% 资源退还`; (b) 08-api-idl.md line 162: `refund: registry.body_cost(body) * 0.5`; (c) refund_policy line 284: `contention_lost: 0.5, self_invalid: 0.0`. **No lifespan-dependent gradient (10-50%) exists.** The decision called for refund scaling from 10% (near-death drone) to 50% (fresh drone) based on `age / age_max` ratio. This mechanism is entirely absent. |
| D4 | CLOSED | Storage tax tiered at exactly 0/1/5/20 bp: gameplay.md §8 table (lines 344-349) and config default `global_storage_tax_tiers = [(30,0),(60,1),(85,5),(100,20)]` at line 370. Tier boundaries at 30%/60%/85%/100% capacity. Arena mode default免税 per "竞技公平". |
| D5 | CLOSED | Blob async upload: api-registry.md §11 documents `async_object_store_upload` — fire-and-forget from deploy flow, FDB stores only manifest record (hash pointer), retry with exponential backoff (max 3), 3 blob types (wasm_module/replay_recording/snapshot_archive). §10 deploy_mutation flow step 2: upload blob async, step 3: commit manifest to FDB. |
| D6 | **GAP** | soft_launch is **single-stage 1500 tick protection** — no 3-stage PvP progression. Evidence: gameplay.md §8 anti-snowball table: `soft_launch 1500 tick — 新玩家独立保护期`. No mechanism for graduated PvP exposure (e.g., Stage 1: PvE-only 0-500t, Stage 2: limited PvP zone 500-1000t, Stage 3: full PvP 1000-1500t). The soft_launch parameter is a binary on/off timer. |
| DA1 | CLOSED | deploy_mutation replay_class: api-registry.md §3.2 — `swarm_deploy` replay_class = `idempotent_mutation`. §10 documents deploy_mutation with `fdb_version_counter` for strict total order in replay. §6 TickTrace Envelope includes `deploy_events` field (#8). |
| DA2 | CLOSED | f64→定点: gameplay.md §8 uses `fixed<u32,4>` type for `source_regeneration_rate` (line 90), `build_cost_multiplier` (line 91), `drone_decay_rate` (line 92). Fixed-point with 4 decimal places (×10000 scaling). Cost values use u32 throughout IDL. |
| DA3 | CLOSED | Worker pool 256 default: api-registry.md §5.5 — `max_pool = 256`, worker pool size = `min(max_pool, active_players)`, world.toml adjustable. |

---

## 3. GAP Details

### GAP-B1: YAML IDL RejectionReason 44 vs Markdown 35 — 命名分歧

**Location**:  
- YAML IDL: 08-api-idl.md §2, lines 65-110 (44 entries)  
- API Registry: api-registry.md §2 (35 canonical codes across §2.1-2.4)

**Content**:  
The YAML IDL enumerates 44 RejectionReason variants using verbose, state-specific names:
- `Fatigued` (not `CooldownActive`)
- `TileBlocked` (not `PositionOccupied`)
- `MissingBodyPart { part: BodyPart }` (not `NotEnoughBodyParts`)
- `AlreadyHacked`, `AlreadyDebilitated`, `InvalidDamageType`
- `NoPath`, `PathTooLong`, `OutOfRoom`, `StillSpawning`, etc.

The api-registry.md uses 35 unified canonical codes:
- `CooldownActive` (generic), `PositionOccupied`, `NotEnoughBodyParts`
- No `AlreadyHacked`/`AlreadyDebilitated`/`InvalidDamageType` — context pushed to `debug_detail`
- No `NoPath`/`PathTooLong`/`OutOfRoom`/`StillSpawning` — consolidated or removed

The YAML self-references the Markdown as authority (`权威定义见 API Registry §2 — 35 变体`), creating circular inconsistency.

**Impact**: Code generators reading the YAML produce different RejectionReason enums than the canonical 35-code spec. Implementers have no single truth source.

**Fix direction**: Regenerate the YAML IDL RejectionReason list to match the 35 canonical codes, or update api-registry.md to include all YAML entries as canonical and correct the count.

### GAP-B3: MCP Tool Namespace Divergence — 三套名称残影

**Location**:  
- design/interface.md §4.1 (43 named tools in category table)  
- api-registry.md §3.2 (46 tools in 8 categories)

**Content**:  
design/interface.md lists tools not in the authoritative api-registry.md:

| design/interface.md | api-registry.md equivalent |
|---|---|
| `swarm_rollback` | Not present (replaced by `swarm_get_deploy_status`) |
| `swarm_list_modules` | Not present (replaced by `swarm_list_deployments`) |
| `swarm_explain_last_tick` | `swarm_get_tick_trace` (renamed) |
| `swarm_inspect_entity` | Not present |
| `swarm_inspect_room` | Not present |
| `swarm_profile` | `swarm_get_sandbox_profile` (renamed) |
| `swarm_dry_run_commands` | `swarm_dry_run` (renamed) |
| `swarm_get_docs` | Not present (consolidated into `swarm_sdk_fetch`?) |
| `swarm_get_schema` | Not present |
| `swarm_get_available_actions` | Not present |
| `swarm_submit_csr` etc. (18 auth) | Only `swarm_auth_login`, `swarm_auth_refresh` |
| `swarm_tournament_*` (4 tools) | Not present |

While design/interface.md says `权威工具清单见 API Registry §3`, the inline listing creates **第二套名称空间** for anyone reading the design doc without opening the registry. The IDL YAML code generation pipeline produces a **第三套** based on YAML scanning.

**Impact**: SDK codegen, MCP server implementation, and AI agent onboarding docs may produce different tool surfaces.

**Fix direction**: Strip the inline tool listing from design/interface.md §4.1 — replace with a single pointer to api-registry.md §3.2. Or keep a high-level capability summary without tool names.

### GAP-D3: Recycle Refund Missing Lifespan Gradient (D3: 10-50%)

**Location**:  
- gameplay.md §8, line 107  
- 08-api-idl.md §2, line 162

**Content**:  
The R18 user decision D3 requested Recycle refund scale from 10% to 50% based on drone remaining lifespan (age/age_max ratio). Current implementation:

```
# Current (flat):
refund = body_cost * 0.5          # always 50%

# D3 expected (lifespan gradient):
refund_ratio = 0.1 + 0.4 * (1.0 - age / age_max)   # 10% when near-death, 50% when fresh
```

Both gameplay.md and the IDL YAML document only the flat 50% refund. The refund_policy section distinguishes `contention_lost` (0.5) from `self_invalid` (0.0) but neither branches on lifespan.

**Impact**: Without lifespan-dependent refund, players have no incentive to recycle drones before they age out — the 50% refund is constant from spawn to death. This removes a strategic trade-off (recycle early for more resources vs squeeze more work out of aging drones).

**Fix direction**: Add `age_ratio` field to Recycle's refund calculation. Define formula: `refund = body_cost * (0.1 + 0.4 * (1.0 - age/age_max))`. Document in gameplay.md drone lifecycle section and IDL refund_policy.

### GAP-D6: soft_launch Missing 3-Stage PvP Progression (D6: 3阶段PvP)

**Location**:  
- gameplay.md §8, anti-snowball table  
- design/modes.md — World mode description

**Content**:  
The R18 user decision D6 specified a 3-stage soft_launch for graduated PvP exposure:

```
Expected (3-stage):
  Stage 1 (PvE-Only):       0-500 ticks   — 新玩家仅遭遇NPC，不可被PvP攻击，不可攻击其他玩家
  Stage 2 (Limited PvP):   500-1000 ticks — 可被攻击但攻击者受衰减(-30% damage)，可反击
  Stage 3 (Full PvP):     1000-1500 ticks — 完整PvP，soft_launch结束时全部限制解除
```

Current documentation only describes a single binary `soft_launch` timer (1500 ticks) as a "新玩家独立保护期". No stage mechanism, no graduated exposure, no partial PvP damage modifiers.

**Impact**: New players face a cliff — at tick 1501 they transition from full protection to full PvP vulnerability instantly. This creates a "day after soft_launch" massacre window where veteran players camp new-player borders. The 3-stage design was specifically chosen to mitigate this cliff.

**Fix direction**: Replace the binary `soft_launch_ticks` parameter with `soft_launch_stages = [(500, "pve_only"), (1000, "limited_pvp"), (1500, "full_pvp")]`. Define limited_pvp rules: incoming damage ×0.7, outgoing damage normal, full vision. Document in gameplay.md anti-snowball section and world.toml config spec.

---

## 4. CrossCheck — 建议其他方向验证

| # | Direction | Item | Why |
|---|-----------|------|-----|
| 1 | **rev-dsv4-security** | B3 auth tools | The design/interface.md lists ~18 auth-related MCP tools (swarm_submit_csr, swarm_register_challenge, etc.) that are absent from api-registry.md's Auth category (only 2 tools: swarm_auth_login, swarm_auth_refresh). Security reviewer should verify: (a) Are these 18 tools intentionally removed from the registry or accidentally dropped? (b) If removed, where is the equivalent auth functionality routed? |
| 2 | **rev-dsv4-architect** | B1 IDL codegen | The YAML IDL (44 RejectionReason) vs Markdown (35 canonical codes) inconsistency will produce different codegen output depending on which source the generator reads. Architect should verify: (a) Which file does the actual `cargo run -- gen-api` pipeline consume? (b) Does the generated Rust code match the 35-canonical spec or the 44-entry YAML body? |
| 3 | **rev-dsv4-sdk** | B3 + D6 | SDK codegen from api-registry.md produces different tool surfaces than design/interface.md documents. SDK reviewer should verify: (a) Do SDK type definitions include all 46 tools? (b) Is soft_launch exposed as a queryable parameter in SDK world config so players can programmatically detect their PvP stage (if 3-stage is implemented)? |

---

## 5. Strategy Depth Analysis (game designer domain notes)

**Economy depth**: The Faucet/Sink/Transfer/Lockup/Unlock classification (gameplay.md §8) is well-structured. Progressive storage tax (D4) creates meaningful strategic choice between global accumulation and local stealth. The global↔local transfer latency (10t/5t) with interception risk adds logistics gameplay depth. ✅

**Drone lifecycle**: Controller aging hard cap (50% of natural growth) and Depot logistics create spatial strategy. However, the flat 50% Recycle refund (GAP-D3) removes the temporal dimension of drone management — there's no incentive to time your recycle optimally. This flattens an otherwise rich decision space. ⚠️

**PvE layer**: World PvE ecology (modes.md §9.0) is well-specified with NPC types, resource points, world events, and deterministic triggers. The geographic difficulty gradient (Zone 1→4) naturally gates progression without artificial barriers. Economy constraint (`max_pve_output ≤ 30% world regen`) prevents PvE farming from overwhelming PvP strategy. ✅

**PvP transition**: The binary soft_launch (GAP-D6) creates a degenerate strategy: veteran players camp at the 1500-tick boundary. The missing 3-stage graduated exposure would have created a richer strategic space — new players could test their PvP readiness in Stage 2 before full exposure, and veterans would face counterplay risk (defenders get normal damage in limited PvP). Without it, the optimal strategy for veterans is trivial: wait at border, strike at tick 1501. ⚠️

**Arena mode**: Well-specified with room configuration, symmetric maps, replay system, and PvE Challenge scoring. The absence of auto-matchmaking is an explicit design choice (not a gap). PvE Challenge scoring formula `(base_score × efficiency × difficulty + bonus)` is sound. ✅

---

## 6. Summary

|Category|Count|
|---|---|
|CLOSED|12|
|GAP|4|
|N/A|0|
|Total items|16|

**Closing note**: The api-registry.md as a consolidated single-source is excellent progress — D1/D2/D4/D5/DA1/DA2/DA3 are well-executed closures. The four GAPs are all documentation/design inconsistencies (B1, B3) or missing mechanism implementations (D3, D6). None require architectural rework — they are specification corrections and parameter additions.
