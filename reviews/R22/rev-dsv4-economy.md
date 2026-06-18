# R22 Economy Review — rev-dsv4-economy (DeepSeek V4 Pro)

**Reviewer**: rev-dsv4-economy (Economy Reviewer)
**Phase**: Phase 1 Clean-Slate
**Date**: 2026-06-18
**Documents Reviewed**:
- /tmp/swarm-review-R16/design/README.md
- /tmp/swarm-review-R16/design/gameplay.md
- /tmp/swarm-review-R16/design/modes.md
- /tmp/swarm-review-R16/design/economy-balance-sheet.md
- /tmp/swarm-review-R16/specs/reference/api-registry.md
- /tmp/swarm-review-R16/specs/gameplay/06-feedback-loop.md
- /tmp/swarm-review-R16/specs/gameplay/08-api-idl.md
- /tmp/swarm-review-R16/specs/core/08-resource-ledger.md

---

## Verdict: REQUEST_MAJOR_CHANGES

The economic architecture is sound in its skeleton — the Resource Ledger single-entry-point design, tiered taxation, superlinear anti-snowball maintenance, and phased new-player onboarding form a coherent vision. However, **critical numerical inconsistencies between the authoritative source (resource-ledger.md) and the generated registry (api-registry.md) break the single-source-of-truth contract**, and the economy balance sheet reveals all modeled scenarios running at net deficit without specifying the assumed initial resource endowments needed to bridge the gap. These are fixable specification errors, not architectural flaws.

---

## Findings

### C1 (Critical): Storage Tax Tier Thresholds — Two Incompatible Definitions

**api-registry.md §5.7** defines absolute thresholds:
| Tier | Threshold | Rate |
|------|-----------|------|
| 1 | 10,000 units | 1 bp |
| 2 | 100,000 units | 5 bp |
| 3 | 1,000,000 units | 20 bp |

**resource-ledger.md §2.1 & §2.2** (declared authoritative) defines percentage-based thresholds:
| Tier | Threshold (% capacity) | Rate | Equivalent at 1M capacity |
|------|------------------------|------|---------------------------|
| 0 | 0–30% | 0 bp | 0–300,000 |
| 1 | 30–60% | 1 bp | 300,000–600,000 |
| 2 | 60–85% | 5 bp | 600,000–850,000 |
| 3 | 85–100% | 20 bp | 850,000–1,000,000 |

These are not reconcilable — at 100K storage, api-registry charges 1 bp while resource-ledger charges 0 bp. At 500K, api-registry charges 5 bp while resource-ledger charges 1 bp. The percentage-based model from resource-ledger.md §2.2 has the correct tiered formula with explicit example calculation, but api-registry.md (declared as the generated authoritative registry from economy.idl.yaml) contains different values.

**Recommendation**: Align economy.idl.yaml with resource-ledger.md §2.1 percentage-based tiers. api-registry.md as a generated artifact will then be consistent. If absolute thresholds are preferred, the tiered formula in §2.2 and the balance sheet calculations must be updated.

---

### C2 (Critical): UpkeepDeduction — Two Incompatible Models

**api-registry.md §10.2** defines:
> "Per-structure cost: 1 unit/tick. Controller upkeep: `level² × 10`. Drones have no passive upkeep."

**resource-ledger.md §Empire Upkeep** and **economy-balance-sheet.md §1** define:
> `upkeep = base_upkeep × rooms × (1 + rooms / room_soft_cap)`

These are fundamentally different models:
- api-registry: per-structure granular (a player with 5 rooms × 10 structures pays ~50/tick + controller costs)
- resource-ledger: superlinear per-room (5 rooms × 50 × 1.5 = 375/tick)

The economy balance sheet uses the resource-ledger formula and validates it. The api-registry formula would produce dramatically different numbers and would not exhibit the O(n²) anti-snowball property. **If api-registry's `UpkeepDeduction` formula is authoritative (generated from economy.idl.yaml), the entire anti-snowball proof in the balance sheet is invalid.**

**Recommendation**: The economy.idl.yaml `UpkeepDeduction` entry must be corrected to reference the `empire_upkeep_mod` tiered formula from resource-ledger.md. Remove the per-structure + controller-level formula from the registry.

---

### H1 (High): Economy Balance Sheet — All Scenarios Run at Net Deficit

All four modeled scenarios show negative net flow:
| Rooms | Net Loss/tick | Accumulated Loss/1500t |
|-------|:---:|:---:|
| 1 | -30 | -45,000 |
| 5 | -250 | -375,000 |
| 20 | -1,940 | -2,910,000 |
| 50 | -12,625 | -18,937,500 |

The balance sheet acknowledges "1 房间阶段需要初始资源包支撑" and "Controller 升级到 RCL 2-3 后可达收支平衡" — but the initial resource endowment is not quantified, and the Controller upgrade path from deficit to breakeven is not modeled. RCL progression depends on Controller upgrade costs (which are Lockup, not Sink — resources locked in Controller), but the balance sheet doesn't show how RCL growth changes income.

**Mathematical gap**: What initial resource package enables surviving the 1-room deficit period? How many ticks does it take to reach RCL 2-3 breakeven? Without these numbers, the economy is not "balanced" — it's "theoretically balanced if you bring enough starting resources."

**Recommendation**: Add a warm-up phase model: initial resources → RCL progression timeline → breakeven point. Provide the initial resource package values for Tutorial/Vanilla/Standard modes explicitly.

---

### H2 (High): AlliedTransfer — Fee/Cooldown Contradiction

**api-registry.md §10.2**: "Tax-free transfer between allied players via global storage. No cooldown."
**resource-ledger.md §2.1**: `allied_transfer_fee = 200 bp (2.00%)`, `allied_transfer_delay = 200 tick`, `allied_transfer_cooldown = 500 tick`
**economy-balance-sheet.md §3**: `allied_transfer_enabled = false (默认)` for Standard mode

Even accounting for the possibility that the fee is configurable and defaults to 0 in some modes, the canonical registry declaring "tax-free, no cooldown" while the authoritative ledger declares "200 bp, 500 tick cooldown" is a direct contradiction.

**Recommendation**: economy.idl.yaml must align with resource-ledger.md §2.1 as the authoritative source. If tax-free allied transfer is a mode-specific override, document it as such with explicit default values.

---

### H3 (High): Upkeep Deficit Death Spiral — Positive Feedback Loop

resource-ledger.md §Empire Upkeep defines deficit penalties:
- 3 consecutive tick deficit → drone efficiency -50%
- 10 consecutive tick deficit → drone forced death (age ×10)

This creates a **positive feedback loop**: deficit → reduced efficiency → less income → larger deficit → forced death. This is the opposite of an anti-snowball mechanism — it's a poverty trap that accelerates the collapse of struggling players. A player who temporarily falls behind (e.g., due to a PvP raid) cannot recover because the efficiency penalty reduces their harvesting, making the upkeep even harder to pay.

**Mathematical concern**: Once a player enters the 3-tick deficit state, the -50% efficiency reduces their income (from harvesting, building, etc.), making it MORE likely they stay in deficit, not less. This is a **push-out-of-equilibrium** dynamic, not a stabilizing one.

While the design intent (preventing players from ignoring upkeep indefinitely) is valid, the penalty curve creates an unrecoverable state. A grace period or progressive recovery mechanism would be more appropriate.

**Recommendation**: Add a recovery path — e.g., "deficit forgiven after 10 ticks of positive net flow" or "efficiency penalty decays at +10%/tick once upkeep is paid." Consider a minimum subsistence income that cannot be reduced by efficiency penalties.

---

### M1 (Medium): Recycle Refund During Tutorial — Zero-Cost Body Part Testing

Tutorial world (first 500 tick): 100% recycle refund. This means:
1. Spawn drone with CLAIM body part (600 Energy)
2. Immediately recycle → 600 Energy returned
3. Net cost: 0 Energy

This enables infinite zero-cost experimentation with body part combinations. While intentional for "新人可以试错" (newbie trial-and-error), the interaction with the Spawn cooldown (5 tick) and the ability to test ALL body part combinations at zero cost raises a question: does this trivialize body part discovery? In a game about optimization, free experimentation might be the right call for tutorial, but it should be explicitly bounded (e.g., "first 10 spawns free" rather than "500 ticks of free recycling").

**Recommendation**: Consider an explicit "free_respec_count" parameter instead of time-based free recycling, to prevent the tutorial meta from being "spawn-recycle loop for 500 ticks to discover optimal body."

---

### M2 (Medium): Source Quality vs Room Count — Unmodeled Dependency

The economy balance sheet assumes higher room counts correlate with higher-level sources:
- 1 room: 2× L1 sources
- 50 rooms: 115× L3-4 sources

But there is no formal model linking source quality to room count. The PvE difficulty gradient (§9.0 in modes.md) defines Zone 1-4 with increasing NPC density and resource quality, implying outer rooms have better sources. However:
- There is no function `f(room_distance_from_center) → source_level_distribution`
- The relationship between "rooms controlled" and "average source level" is not guaranteed
- A player could control 50 low-quality rooms and face the same 15,000/tick maintenance but with far less income

**Recommendation**: Add a formal source distribution model by zone level. Even if approximate, it provides the missing link between room count and income in the balance sheet.

---

### M3 (Medium): Controller Aging Hard Cap — 50% Limit Mathematical Implications

gameplay.md §Drone 生命周期: "每 tick 总 age 回退不超过自然增长（+1/tick）的 50%（即 `max(0, age + 1 - min(0.5, controller_count * 0.5))`）"

This means **ALL drones eventually die regardless of controller count**. With the cap at 50% offset, every drone gains at minimum +0.5 effective age per tick (1.0 natural - 0.5 max reduction). At 1500 base lifespan, effective lifespan becomes ~3000 ticks maximum (1500 / 0.5), but with `active_aging` at 110%, it's closer to ~2727 ticks. Multiple controllers do not extend this beyond the 50% cap.

This is fine as a design choice, but it means the "Controller维修" mechanic has a hard practical ceiling. A player with 10 controllers and a player with 2 controllers get the same maximum age reduction — the extra 8 controllers add zero marginal age benefit. The document states "防止玩家通过堆叠多个 Controller 实现永久 drone" — this is achieved, but the 50% cap could be more elegantly expressed as diminishing returns (`age_reduction = 1 - 1/(1 + k*controller_count)`) rather than a hard cliff after 1 controller.

---

### M4 (Medium): PvE Budget Creates Controller-Level Snowball

resource-ledger.md §3, PvE Budget dimension: "per player ≤ player_controller_level × 1000"

This ties PvE farming capacity to PvP progression (controller levels). Players with higher RCL can farm more PvE, gaining more resources to build more controllers. This creates a multiplicative snowball: more controllers → more PvE income → more controllers.

While the global cap (30% of world regeneration) limits total PvE faucet, individual players who achieved high RCL before others can claim a disproportionate share of the PvE budget, accelerating their lead. This interacts negatively with the anti-snowball maintenance model — high-RCL players get both: (a) more PvE farming capacity, and (b) already have the economy to support high maintenance.

**Recommendation**: Consider decoupling PvE budget from controller level, or adding a zone-based cap (outer zones yield more PvE but require more logistics, creating natural friction).

---

### L1 (Low): Global Storage Capacity — Example vs Default Discrepancy

- api-registry.md §5.1: `global_storage_capacity = 1,000,000 units`
- gameplay.md world.toml example: `global_storage_capacity = 100000`

The example uses 1/10th the default capacity. This is likely intentional (example showing configurable value), but readers may confuse the example for the default.

---

### L2 (Low): Body Part Cost — Two Sources, Minor Differences

api-idl.md §body_cost:
- RangedAttack: 100 Energy
- Attack: 80 Energy

api-registry.md §10.2 SpawnCost:
- RANGED_ATTACK: 150 Energy
- ATTACK: 80 Energy

RangedAttack cost differs (100 vs 150). The api-idl.md serves as the authoritative IDL while api-registry.md is generated from it, so this may indicate a stale generation. All other body part costs match.

---

### L3 (Low): Recycle Refund Formula — Double Definition

resource-ledger.md §2.3 defines: `recycle_refund = max(body_cost × recycle_refund_min / 10000, recycle_refund)` where `recycle_refund = body_cost × remaining_lifespan / total_lifespan × recycle_refund_base / 10000`

api-registry.md §10.3 defines: `refund_rate_bp = max(1000, (remaining_lifespan * 5000) / total_lifespan)` then `refund_amount = (refund_rate_bp * body_cost) / 10000`

These are mathematically equivalent (max(1000 bp, lifespan_ratio × 5000 bp)), but the resource-ledger expresses it as a two-step formula while api-registry computes the rate first. No functional issue, but having two formulations risks divergence during future edits. Resource-ledger.md §2 is the declared authoritative source.

---

## Strengths

1. **Anti-Snowball Architecture**: The superlinear O(n²) maintenance curve + progressive storage tax + Controller aging cap + room drone cap (50→500) form a mathematically coherent set of dampening mechanisms. The economy-balance-sheet proves convergence: 50 rooms require 40× the maintenance of 5 rooms (not 10× linear).

2. **Single-Entry Resource Ledger**: The Transfer Gateway architecture (resource-ledger.md §1) eliminates multi-path resource exploits. All operations — LocalTransfer, GlobalDeposit, PvEAward, RecycleRefund, BuildCost, SpawnCost, UpkeepDeduction, StorageTax — pass through one deterministic pipeline with tick-level traceability.

3. **Fixed-Point Fee Model**: All rates expressed as basis points (integer), all amounts as u64/u32, no floating-point. This guarantees deterministic cross-platform computation and replay integrity. The `MilliUnits` type for intermediate calculations with floor-rounding on commit is a correct approach for sub-unit precision without float drift.

4. **Recycle Refund Proportional to Lifespan**: The 10%-50% proportional refund (resource-ledger.md §2.3) elegantly prevents spawn-recycle arbitrage — recycling a fresh drone loses 50%, recycling an old drone nets near 10%. Combined with `active_aging` at 110%, drones that work hard lose recycle value faster, adding a subtle cost to aggressive strategies.

5. **Phased New-Player Onboarding**: safe_mode (500 tick) → soft_launch (1500 tick PvE-only) → First-Attack Shield (200 tick full shield) → Soft PvP (300 tick 50% damage) → Full PvP. This graduated transition prevents the "protection cliff" problem where new players get destroyed the instant their shield drops.

6. **Three Logistics Modes**: Mode A (no logistics, instant global), Mode B (light logistics, 1%/5% transfer costs), Mode C (hardcore, no global storage) — all configurable via world.toml. This enables server operators to tune economic complexity without engine changes.

7. **Deterministic Execution Order**: Resource operations execute in fixed order per tick (UpkeepDeduction → StorageTax → PvEAward → LocalTransfer → GlobalDeposit → GlobalWithdraw → AlliedTransfer → BuildCost → SpawnCost → RecycleRefund). This prevents ordering-dependent exploits where, e.g., players could spend resources before upkeep is deducted.

8. **Modular Vanilla Content**: Body parts, structures, damage types, special attacks, resources — ALL defined in world.toml, none hardcoded. Engine core operates on `HashMap<ResourceName, Amount>`, agnostic to what "Energy" means. This is architecturally correct for an extensible game engine.

---

## Mathematical Gaps

### G1: Breakeven RCL Not Quantified
The balance sheet acknowledges RCL 2-3 is needed for breakeven but doesn't model the timeline or cost. How many ticks of -30/tick deficit at RCL 1 before reaching RCL 2? Controller upgrade costs are Lockup (not Sink), so they don't appear in the P&L, but the upgrade TIME determines how long the deficit period lasts.

### G2: No Formal Source Distribution Model
The assumed source quality per room count (L1→L4 progression) has no underlying zone model. Without `f(room_count) → expected_income`, the balance sheet numbers are illustrative, not predictive.

### G3: Empire Upkeep Convergence Bound Unverified
The formula `upkeep = base_upkeep × N × (1 + N/C)` converges to infinity as N→∞. The balance sheet stops at N=50. Is there a stable equilibrium point where marginal income = marginal upkeep? The income model would need to be expressed as `I(N)` to solve `dI/dN = dU/dN` for the equilibrium room count.

### G4: UpkeepDeficit Recovery Not Modeled
The deficit → efficiency penalty → deeper deficit spiral is not analyzed for recoverability. A simple differential equation model would reveal whether the system has a stable fixed point or diverges to collapse for any perturbation.

---

## Nash Equilibrium Issues

### NE1: Optimal Strategy May Be "Don't Expand"
Given superlinear maintenance, the net flow at 5 rooms (-250/tick) is worse than 1 room (-30/tick) in absolute terms (-250 < -30), but the per-room deficit improves (-50/room vs -30/room at 1 room). However, both are deficits — no modeled scenario achieves breakeven. The Nash equilibrium in this economy appears to be "consume initial resources and collapse" — which is not a game anyone plays.

### NE2: PvP Resource Capture Unmodeled
If attacking and destroying an enemy structure yields 50% of its build cost (building destruction → partial refund), then aggressive players have an income source not captured in the balance sheet. The optimal strategy may shift from "harvest" to "raid" if combat rewards exceed harvesting yields. The economy model needs to account for PvP resource transfers.

### NE3: Tutorial 100% Refund Creates "Perfect Information" Advantage
Players who exhaustively test all body part combinations during the tutorial's 500-tick free-recycle window gain perfect information about body part efficiency. Players who don't (or can't, due to joining late) operate with incomplete information. In a game about optimization, this information asymmetry is a first-mover advantage that compounds over time. Consider time-gating free respecs or making tutorial replayable.

---

## CrossCheck — 跨方向检查

- **CX1**: UpkeepDeduction model conflict (api-registry vs resource-ledger) → 建议 **Architect** 检查 economy.idl.yaml 中 UpkeepDeduction 的定义，确认哪一方为权威源，并统一所有引用。

- **CX2**: Economy balance sheet shows all scenarios in deficit — is this a "warm-up" design where initial resources are expected to carry players through early RCL levels? → 建议 **Gameplay** 检查 new player initial resource package 的量级，以及 RCL 1→3 升级时间线。

- **CX3**: Controller aging 50% hard cap means 1 controller = 10 controllers for age reduction. Is the strategic value of multiple controllers supposed to come from room control/unlocks rather than age management? → 建议 **Gameplay** 确认 Controller 的 multi-controller 边际价值设计意图。

- **CX4**: PvE budget ties to controller_level × 1000 — this creates a "rich get richer" PvE farming dynamic that counteracts the anti-snowball maintenance model. → 建议 **Gameplay** 评估 PvE budget 是否应解耦 controller level。

- **CX5**: API Registry §10.2 describes AlliedTransfer as "tax-free, no cooldown" while Resource Ledger §2.1 specifies 200 bp fee + 500 tick cooldown. → 建议 **Architect** 确认 economy.idl.yaml 中 AlliedTransfer 的权威定义。

- **CX6**: Body part RangedAttack cost: 100 (api-idl.md) vs 150 (api-registry.md §10.2). → 建议 **Architect** 检查 IDL → Registry 生成管线，确认是否 stale generation。

- **CX7**: Storage tax tier representation: absolute thresholds (api-registry) vs percentage-based (resource-ledger). The percentage-based model is more robust to capacity changes. → 建议 **Architect** 确认 economy.idl.yaml 中的 storage_tax_tiers 表示方式，以及 api-registry.md 生成逻辑是否正确转换了百分比为绝对值。
