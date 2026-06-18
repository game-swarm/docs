# R23 Economy Review — DeepSeek V4 Pro

> **Reviewer**: rev-dsv4-economy (Economy Reviewer)
> **Date**: 2026-06-19
> **Phase**: Phase 1 Clean-Slate Independent Review
> **Documents reviewed**: design/README.md, design/gameplay.md, design/modes.md, design/economy-balance-sheet.md, specs/reference/api-registry.md, specs/gameplay/06-feedback-loop.md, specs/gameplay/08-api-idl.md, specs/core/08-resource-ledger.md

---

## Verdict: CONDITIONAL_APPROVE

The economic architecture is fundamentally sound with well-designed anti-snowball mechanisms — superlinear O(n²) upkeep, tiered progressive storage tax, proportional recycle refund, and deterministic execution order. However, the design has a **critical bootstrapping gap** (no starting resources for World mode new players) and **significant cross-document numerical inconsistencies** (storage tax thresholds, build costs, recycle rates) that must be resolved before implementation. The mathematical bones are good; the documentation flesh needs surgery.

---

## Issues Found

### Critical

**D1 — No Starting Resource Allocation for World Mode (Critical)**

The economy balance sheet (economy-balance-sheet.md) demonstrates that Standard mode is net-negative at ALL scales: 1 room (-30/tick), 5 rooms (-250/tick), 20 rooms (-1,940/tick), 50 rooms (-12,625/tick). The document acknowledges this with "需要初始资源包支撑" but **no starting resource parameter is defined anywhere** for World mode.

- `resource_types.starting_amount` defaults to `0` (gameplay.md line 468)
- `safe_mode` (500 ticks) provides room invincibility but does NOT waive upkeep
- `soft_launch` (1500 ticks post-safe_mode) provides PvE-only protection but does NOT waive upkeep
- The Resource Ledger execution order places `UpkeepDeduction` at step 1 — before any income
- After 3 ticks of upkeep deficit: drone efficiency -50%. After 10 ticks: forced drone death.

A new player entering Standard mode with 0 Energy faces immediate death spiral. Tutorial mode works (net +14.5/tick at 1 room), but there's no bridge to Standard. Arena has `initial_resources = { Energy = 10000, Crystal = 5000 }` (modes.md §9.1.2), but World mode has no equivalent.

**Recommendation**: Add `starting_resources` to world.toml World config with reasonable defaults (e.g., 5000 Energy for Standard, 10000 for Vanilla). Or waive upkeep during safe_mode for new players.

---

**D2 — Storage Tax Thresholds: api-registry §5.7 vs resource-ledger §2.1 (Critical)**

**api-registry.md §5.7** (Economy 限制, source: economy IDL) lists absolute unit thresholds:
| Tier | Threshold |
|------|-----------|
| Tier 1 | 10,000 units |
| Tier 2 | 100,000 units |
| Tier 3 | 1,000,000 units |

**resource-ledger.md §2.1** and **gameplay.md §8** both define percentage-based thresholds:
```
storage_tax_tiers = [(30,0),(60,1),(85,5),(100,20)]
// 30%, 60%, 85%, 100% of capacity
```

The api-registry changelog (version 0.1.1) explicitly states: "R22 B2: StorageTax changed to percentage-based tiers (30/60/85/100% capacity)." But §5.7 still carries the old absolute-unit thresholds. The api-registry claims to be auto-generated from IDL — this implies either the economy IDL wasn't updated per R22 B2, or the generation missed §5.7.

The api-registry §10.3 formula uses percentage-based computation correctly. This is a split-brain: §5.7 (limits table) says absolute units, §10.2-10.3 (operations/formulas) says percentage-based.

**Recommendation**: Update economy.idl.yaml §5.7 thresholds to reflect percentage-based tiers. Regenerate api-registry.md and verify consistency.

---

**D3 — Recycle Refund Rate: gameplay.md vs resource-ledger.md (Critical)**

**gameplay.md** line ~108 (Drone 身体规划 section):
> "Recycle 回收 drone 获得 50% 资源退还"

Flat 50%, unconditional. No mention of lifespan proportionality.

**resource-ledger.md §2.3** (authoritative formula):
```
recycle_refund = body_cost × remaining_lifespan / total_lifespan × recycle_refund_base / 10000
recycle_refund = max(body_cost × recycle_refund_min / 10000, recycle_refund)
// Range: 10% (at end-of-life) to 50% (at full lifespan)
```

These are incompatible. A player reading gameplay.md expects 50% flat; the engine implements 10–50% proportional. The api-registry §10.2-10.3 correctly uses the proportional formula, as does economy-balance-sheet.md (which references resource-ledger as authority).

**Recommendation**: Update gameplay.md Recycle description to "退还 10%–50% 资源（按剩余寿命比例）" and reference resource-ledger §2.3 as authority.

---

### High

**D4 — Balance Sheet Net Loss at All Scales Without Growth Mechanism (High)**

The economy-balance-sheet.md demonstrates net-negative cash flow at 1, 5, 20, and 50 rooms for Standard mode. The document frames this as intentional ("需要初始资源包支撑", "需要高效的 Harvester 代码"), but:

1. No quantitative sweet spot (breakeven room count) is shown — the economic equilibrium is asserted, not proven
2. The income projections omit potential sources: multi-source rooms, optimized harvest routes, Tower-assisted defense savings, PvP loot
3. The 1-room scenario (-30/tick) contradicts the design goal of "新手轻松"
4. No growth trajectory from 1→5→20 rooms is demonstrated — how does a player accumulate enough surplus to expand?

The balance sheet serves as a useful stress-test but **overstates the deficit** by using conservative income assumptions. A more complete model showing the growth path from initial resources (currently undefined — see D1) through expansion would verify the anti-snowball claim.

**Recommendation**: Add a "growth trajectory" section showing how a player with adequate starting resources expands through room counts, with breakeven analysis. Include the profit-maximizing room count (where marginal income = marginal upkeep).

---

**D5 — New Player Transfer Lock: Outgoing-Only, Smurf Vulnerability (High)**

resource-ledger.md §2.1 and gameplay.md §8 define:
> `new_player_transfer_lock_ticks = 500` — 新玩家在前 N tick 不得向其他玩家 transfer 资源

This blocks **outgoing** transfers from new players but does NOT block **incoming** transfers TO new players. An established player can:
1. Create a smurf account
2. Transfer significant resources to the smurf during its lock period
3. Use the smurf as a resource proxy or to bypass allied transfer caps

The `same_origin_account_group_quota = 5` (gameplay.md §8) limits account creation from the same IP, but VPN/proxy circumvention is trivial for motivated players. The `allied_transfer` restrictions (200 bp fee, 200 tick delay, 500 tick cooldown, 10,000 daily cap) don't apply to direct player-to-player transfers unless they go through the allied channel.

**Recommendation**: Either block incoming transfers to new players during lock period, or add a receiving cap. Consider extending `allied_transfer` restrictions to cover all player↔player transfers during the lock window.

---

**D6 — Resource Ledger §2.2 Formula Text Omits × Capacity Step (High)**

The resource-ledger.md claims to be the "唯一设计/数学权威" for all economic formulas. However, §2.2's storage tax formula:

```
taxable_in_tier = min(storage_pct - tier_threshold[i], tier_width[i])
tax = taxable_in_tier × tier_rate[i] × global_storage_capacity / 10000
```

This is dimensionally inconsistent: `taxable_in_tier` is a percentage (0–100), multiplied by rate (bp) and capacity (units), then divided by 10000. The result: `30 × 1 × 1,000,000 / 10000 = 3000` — off by 100× from the correct answer (30).

The **example calculation** in the same section produces correct results (30 + 75 = 105), implicitly converting percentage to units: `300,000 × 1 / 10000 = 30`. But the formula text doesn't include this conversion.

The **api-registry.md §10.3** has the corrected formula: `taxable = min(storage_pct - threshold_pct[i], tier_width[i]) × capacity`. The `× capacity` makes it dimensionally correct.

**Recommendation**: Fix resource-ledger.md §2.2 formula to explicitly include the percentage→units conversion: `taxable_amount = taxable_pct × global_storage_capacity / 100; tax += taxable_amount × tier_rate[i] / 10000`.

---

### Medium

**D7 — active_aging Penalty (10%) Too Mild for Anti-Idling (Medium)**

gameplay.md §2.2 defines:
> `active_aging` — 110%（即 +10%）— 每 tick 执行命令的 drone 以 110% 速率衰老

A drone that's always active has effective lifespan of 1500/1.1 ≈ 1364 ticks (vs 1500 idle). Difference: only 136 ticks (9%). The design rationale is "防止挂机囤兵" — but a 9% lifespan reduction is unlikely to deter idling. The economic cost of drone death (body_cost replacement) dwarfs the 9% time saving from idling.

**Recommendation**: Increase active_aging to 150% or make it configurable per world tier (e.g., Standard=150%, Vanilla=120%, Tutorial=100%). Alternatively, make active_aging compound per consecutive active tick to create a real idling-vs-activity tradeoff.

---

**D8 — Balance Sheet Storage Tax Figures Not Reproducible (Medium)**

economy-balance-sheet.md §2.2 (5 rooms) lists storage tax = 15 (tier 1: 30-60% @ 1 bp). But the storage level isn't stated, making the figure unverifiable. For 1,000,000 capacity at 40% utilization:
- Tier 0: 300,000 × 0 / 10000 = 0
- Tier 1: 100,000 × 1 / 10000 = 10

Result: 10, not 15. The 15 could be correct at a different storage level, but the assumption is undocumented. All balance sheet tax figures should state the assumed storage level.

**Recommendation**: Add a "Storage Level Assumed" column to the balance sheet tables.

---

**D9 — BuildCost Table: api-registry vs gameplay.md Divergence (Medium)**

api-registry.md §10.2 lists structure costs:
> Spawn=300, Extension=200, Road=10, Wall=50, Rampart=100, Storage=500, Tower=800, Link=400, Extractor=600, Lab=1000, Terminal=1200, Observer=500

gameplay.md §2.2 structure_types definitions list different costs:
> Spawn=200, Extension=50, Tower=200, Storage=500, Link=300, Extractor=800, Lab=1000, Terminal=500, Observer=300, PowerSpawn=5000, Factory=1500, Nuker=100000, Depot=5000

Significant divergences: Spawn (300 vs 200), Extension (200 vs 50), Tower (800 vs 200). These are order-of-magnitude differences that would dramatically change economic balance. The api-registry claims auto-generation from IDL; gameplay.md structure_types are world.toml definitions.

**Recommendation**: Reconcile and designate a single authoritative source for structure costs. If gameplay.md's `[[structure_types]]` definitions are canonical, update the economy IDL to reference them via code generation rather than hardcoding.

---

### Low

**D10 — "re-deploy refund abuse" Rationale Unsubstantiated (Low)**

gameplay.md §2.2 states `code_update_cooldown` minimum is 5 ticks to "防止 re-deploy refund 滥用". However:
1. `code_update_cost` defaults to `{Energy: 0}` — there's nothing to refund-abuse
2. No "refund on re-deploy" mechanism is described anywhere in the docs
3. If a server sets non-zero `code_update_cost`, the cooldown would prevent rapid cycles, but the rationale is circular (the cooldown prevents abuse of a refund that isn't defined)

**Recommendation**: Either remove this rationale or document the refund mechanism it's protecting against.

---

**D11 — Economy Balance Sheet Lacks Transparency in Assumptions (Low)**

Several economy-balance-sheet.md figures rely on unstated assumptions (RCL levels, source levels, harvester efficiency, storage percentage). While the document correctly references resource-ledger.md as the formula authority, the numerical scenarios would be more convincing if assumptions were explicitly tabulated.

**Recommendation**: Add an "Assumptions" table for each scenario (RCL distribution, source levels, harvester count per room, storage utilization %).

---

## Strengths

1. **Superlinear Maintenance Formula (O(n²))**: `upkeep = base_upkeep × rooms × (1 + rooms / room_soft_cap)` creates a natural soft cap — 50 rooms costs 40× more than 5 rooms (not 10× linear). This is a provably effective anti-snowball mechanism.

2. **Tiered Progressive Storage Tax**: 0/1/5/20 bp brackets (30/60/85/100% capacity) create increasing pressure as storage grows. Low-utilization players pay nothing; hoarders face accelerating drain. Well-calibrated.

3. **Proportional Recycle Refund (10–50%)**: Tying refund to remaining lifespan elegantly prevents arbitrage — you can't spawn-recycle-spawn for profit. The 10% floor ensures end-of-life drones still have some salvage value. Strategic reconfiguration (recycle early, respawn optimized) carries a real cost.

4. **Global↔Local Transfer with Friction**: 1% deposit fee + 5% withdrawal fee + 10/5 tick delays prevent "teleport economy." Resources must be physically planned, creating logistics as gameplay.

5. **PvE Budget 4-Dimension Cap** (resource-ledger.md §3): Global (≤30% world regen), Zone (≤50% zone regen), Player (≤RCL×1000), Event caps prevent NPC farming from overwhelming strategic PvP. Well-designed faucet governance.

6. **Deterministic Execution Order** (resource-ledger.md §4): Upkeep→Tax→PvE→Transfers→Build→Spawn→Recycle. Fixed order ensures replay consistency and prevents ordering exploits.

7. **Fixed-Point Arithmetic Throughout**: All rates in basis points, all amounts in integers. No floating-point nondeterminism. Correctly specified in api-registry §0 (type registry) and resource-ledger §6.

8. **Allied Transfer Restrictions**: 2% fee, 200 tick delay, 500 tick cooldown, 10,000 daily cap, 100-tick alliance membership requirement. Multi-layered anti-abuse. Well-calibrated.

9. **Arena Mode Economic Separation**: Tax-free storage, symmetric initial resources, fixed match duration. Correctly isolates competitive fairness from World mode's asymmetric persistence.

10. **soft_launch Progressive PvP Transition** (gameplay.md §2.3 D6/B): Three-phase transition (First-Attack Shield → Soft PvP 50% damage → Full PvP) prevents protection-cliff griefing. Elegant design.

---

## CrossCheck — Cross-Direction Concerns

- **CX1**: Storage tax thresholds in api-registry §5.7 (absolute units: 10K/100K/1M) contradict resource-ledger §2.1 (percentages: 30/60/85/100%). R22 B2 migration appears incomplete in the economy IDL. → 建议 **Architect** 检查 economy.idl.yaml 是否已更新为百分比制，并重新生成 api-registry.md

- **CX2**: BuildCost table in api-registry §10.2 diverges significantly from gameplay.md structure_type cost definitions (Spawn: 300 vs 200, Extension: 200 vs 50, Tower: 800 vs 200). → 建议 **Architect** 确定结构成本的单一权威源（IDL 硬编码 vs world.toml [[structure_types]] 定义），统一后重新生成

- **CX3**: No `starting_resources` field exists in the documented world.toml schema despite the economy requiring bootstrap resources. Arena mode has `initial_resources`; World mode needs equivalent. → 建议 **Architect** 添加 `starting_resources` 到 WorldConfig，默认值对齐 economy-balance-sheet 假设

- **CX4**: Controller age repair hard cap formula `max(0, age + 1 - min(0.5, controller_count × 0.5))` — the cap is always 0.5/tick regardless of controller count beyond 1. Is the `controller_count` multiplier intentional or should multiple controllers provide diminishing but non-zero additional benefit? → 建议 **Gameplay** 确认多 Controller age 维修的边际效益设计意图

- **CX5**: `code_update_cooldown` minimum of 5 ticks is explained as preventing "re-deploy refund abuse," but no refund mechanism exists for deploys. → 建议 **Gameplay** 澄清或移除该理由

---

## Mathematical Gaps

### Gap 1: Storage Tax Formula Dimension Error (see D6)
The resource-ledger §2.2 formula text omits the `× capacity / 100` conversion from percentage to units.

### Gap 2: Maintenance Convergence Not Analyzed
The maintenance formula `base_upkeep × rooms × (1 + rooms / room_soft_cap)` diverges quadratically (O(n²)). The anti-snowball goal is achieved (marginal cost > marginal income → natural soft cap), but no analysis shows WHERE the crossover point lies. The profit-maximizing room count (where dIncome/dRooms = dUpkeep/dRooms) is never computed.

### Gap 3: Balance Sheet Income Linearity Assumption
Income is modeled as linear in room count (harvesters/room, controller income/room), but high-RCL rooms have multiplicative productivity. A 20-room empire with RCL 6-7 rooms generates disproportionately more income than 20× a 1-room start. The balance sheet's net-loss figures may be overly pessimistic for developed empires.

---

## Nash Equilibrium Issues

### NE1: Optimal Strategy May Be "Don't Expand"
If the balance sheet is correct and ALL room counts are net-negative, the Nash equilibrium is to minimize rooms (stay at 1) and minimize spending — a degenerate "do nothing" strategy. This contradicts the game's intended expansion dynamic. The missing starting resources (D1) and overly conservative income modeling (Gap 3) likely explain this, but the equilibrium should be explicitly verified once parameters are finalized.

### NE2: Recycle Timing Game
The proportional recycle formula creates a strategic calculation: recycle early (high refund, lost productive time) vs recycle late (low refund, maximized productive time). The Nash equilibrium depends on the drone's marginal productivity vs spawn cost. For standard harvesters (200 Energy spawn, ~10 Energy/tick income), the break-even is ~20 ticks of harvesting. Beyond that, keeping the drone dominates recycling. This is a healthy strategic tradeoff — no degenerate equilibrium.

### NE3: Storage Tax Evasion via Local Hoarding
Since local storage is private and untaxed, the dominant strategy for large empires is to keep resources in local storage (in Structures/Extensions) rather than global storage, avoiding the progressive tax entirely. This is somewhat intentional (gameplay.md §8: "本地存储隐匿性" is a feature), but it means the storage tax only applies to resources players CHOOSE to expose. Players who optimize local logistics can effectively negate the tax. This undermines the anti-hoarding goal — the tax becomes avoidable.

---

## World vs Arena Economic Divergence

The design correctly separates World (persistent, asymmetric, anti-snowball mechanisms active) from Arena (symmetric, tax-free, fixed duration). Key observations:

| Mechanism | World (Standard) | Arena |
|-----------|-----------------|-------|
| Storage tax | Tiered 0/1/5/20 bp | Exempt |
| Upkeep | O(n²) superlinear | N/A (fixed match) |
| Starting resources | **UNDEFINED** (see D1) | 10,000 Energy + 5,000 Crystal |
| Recycle refund | 10–50% proportional | 10–50% proportional |
| Transfer fees | 1%/5% deposit/withdraw | N/A |
| Allied transfers | Restricted | N/A |

The World mode's **long-term economic health** depends on resolving D1 (starting resources) and verifying that the anti-snowball mechanisms produce a viable growth curve. Without starting resources, World mode is economically unplayable for new entrants.

---

*End of Review*
