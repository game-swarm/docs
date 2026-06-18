# R24 CV-经济 (DeepSeek V4 Pro) — Closure Verification

**Reviewer**: rev-dsv4-economy (Economy Reviewer)
**Date**: 2026-06-19
**Round**: R24 Closure Verification
**Scope**: B1, B2 (R23 Blocker/D-items only)

---

## Verification Items

### B1 — 经济启动 + D1/A starting_resources + free_upkeep + D4/A repair cap

#### D1/A starting_resources

[B1/D1/A] CLOSED

Evidence:
- `specs/core/08-resource-ledger.md` §2.3 (line 124): `starting_resources = {Energy: 5000, Minerals: 2000}`
- `specs/core/08-resource-ledger.md` §4 (line 197): `WorldStartupSubsidy` as step 1 in deterministic execution order — injected on first entry
- `design/economy-balance-sheet.md` §3 (line 129): Same values confirmed across all three modes (Tutorial/Vanilla/Standard)
- `specs/reference/api-registry.md` §5.1 (line 480): `Starting resources = {Energy: 5000, Minerals: 2000}` — R23 D1/A annotated
- Cross-document consistency: all 4 documents agree on identical values

#### free_upkeep

[B1/free_upkeep] CLOSED

Evidence:
- `specs/core/08-resource-ledger.md` §2.3 (lines 125-127): `free_upkeep_controllers = 1`, `free_upkeep_drones = 3`, `free_upkeep_ticks = 2000`
- `specs/core/08-resource-ledger.md` §2.3 (lines 130-133): Complete settlement rules — first N controllers/drones exempt, no retroactive charging, smurf constraint (one-time per identity)
- `design/economy-balance-sheet.md` §3 (lines 130-132): Confirm identical values for Standard/Vanilla
- `specs/reference/api-registry.md` §5.1 (lines 481-483): All three parameters confirmed with R23 D1/A annotation
- Growth Path table (`08-resource-ledger.md` §2.3 lines 137-143) demonstrates break-even viability: starting_resources + controller income during safe mode, soft launch with harvesters, reaching self-sufficiency by tick 2000+

#### D4/A repair cap

[B1/D4/A] CLOSED

Evidence:
- `specs/core/08-resource-ledger.md` §2.4 (lines 150-153): `repair_cap = 3500 bp (35%)`, `distance_decay_bp = 500 bp (5% per tile)`
- Authoritative formula: `repair_cost = body_cost × (1 - repair_cap / 10000) × (1 + distance_from_nearest_controller × distance_decay_bp / 10000)`
- `design/economy-balance-sheet.md` §3 (lines 133-134): Confirms 3500 bp (35%) for Standard/Vanilla, 5000 bp (50%) for Tutorial; distance_decay 500 bp for Standard/Vanilla, 0 bp for Tutorial
- `specs/reference/api-registry.md` §5.1 (lines 484-485): `Repair cap = 3500 bp (35%)`, `Repair distance decay = 500 bp/tile` — both annotated R23 D4/A
- Cross-document consistency: all values match

---

### B2 — 经济参数一致性 (Economy Parameter Consistency)

#### Core parameter cross-reference

The following parameters are consistent across all 5 allowed documents:

| Parameter | resource-ledger | gameplay | balance-sheet | api-registry §5.1 | api-registry §10.2 |
|-----------|:---:|:---:|:---:|:---:|:---:|
| `storage_tax_tiers` | [(30,0),(60,1),(85,5),(100,20)] | same | same | — | same |
| `base_upkeep` (Std) | 50 | — | 50 | — | 50 |
| `room_soft_cap` (Std) | 10 | — | 10 | — | 10 |
| `recycle_refund_base` | 5000 bp | 50% | — | — | 5000 bp |
| `recycle_refund_min` | 1000 bp | 10% | — | — | 1000 bp |
| `global_deposit_fee` | 100 bp | — | — | — | — |
| `global_withdraw_fee` | 500 bp | — | — | — | — |
| `allied_transfer_fee` | 200 bp | — | — | — | 200 bp |
| `starting_resources` | {E:5000,M:2000} | — | {E:5000,M:2000} | {E:5000,M:2000} | — |
| `free_upkeep_{ctrl,drones,ticks}` | 1/3/2000 | — | 1/3/2000 | 1/3/2000 | — |
| `repair_cap` | 3500 bp | — | 3500 bp | 3500 bp | — |
| `repair_distance_decay` | 500 bp | — | 500 bp | 500 bp | — |

#### GAP: api-registry.md §5.7 storage tax thresholds

[B2] GAP

Evidence:
- `specs/reference/api-registry.md` §5.7 (lines 554-556): Storage tax tier thresholds = **10,000 / 100,000 / 1,000,000 units** (absolute values)
- `specs/core/08-resource-ledger.md` §2.2 (lines 82-90): Storage tax tiers = **percentage-based**: 30% / 60% / 85% / 100% of capacity
- `specs/reference/api-registry.md` §10.2 (line 739): Correctly reflects percentage-based model: "0%–30% cap = 0 bp, 30%–60% = 1 bp, 60%–85% = 5 bp, 85%–100% = 20 bp"

The §5.7 thresholds (10K / 100K / 1M) are stale absolute values from pre-R22 model that were not updated when R22 B2 switched to percentage-based tiers. At default capacity (1,000,000):
- §5.7 says tier 1 starts at 10,000 (1%) → should be 300,000 (30%)
- §5.7 says tier 2 starts at 100,000 (10%) → should be 600,000 (60%)
- §5.7 says tier 3 starts at 1,000,000 (100%) → should have 4 tiers with last at 850,000 (85%)

This is the exact inconsistency R23 D2 flagged ("storage tax thresholds mismatch between api-registry §5.7"). The fix was applied to §10.2 and the IDL source (economy.idl.yaml changelog line 859: "R22 B2: StorageTax changed to percentage-based tiers") but §5.7 was not regenerated to reflect it.

**Severity**: Non-blocking. The authoritative source (`08-resource-ledger.md` §2.2) and the canonical formula section (`api-registry.md` §10.2) are both correct. §5.7 is a generated summary table with stale absolute values. A CI regeneration would fix this.

---

## Verdict: CONDITIONAL_APPROVE

| Item | Status | Detail |
|------|:------:|--------|
| B1 (D1/A starting_resources) | CLOSED | Defined with values, execution order, cross-doc consistency |
| B1 (free_upkeep) | CLOSED | Parameters + settlement rules + growth path all present |
| B1 (D4/A repair cap) | CLOSED | Formula, cap value, distance decay all confirmed |
| B2 (parameter consistency) | GAP | api-registry §5.7 stale absolute thresholds (R23 D2 not yet regenerated) |

**Action required**: Regenerate `api-registry.md` from `economy.idl.yaml` to fix §5.7 thresholds, or manually update the 3 stale rows to reflect percentage-based model.
