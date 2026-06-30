# R43 Design & Economy Review — rev-dsv4-design-economy

> 评审员：设计与经济 (DeepSeek V4 Pro)
> 视角：博弈论均衡分析、策略深度度量、资源流建模
> 覆盖文档：design/*.md (5), specs/core/*.md (2), specs/gameplay/*.md (3), specs/reference/api-registry.md

---

## 1. Verdict

**REQUEST_MAJOR_CHANGES**

6 Critical + 5 High issues found. The anti-snowball "proof" is a list of qualitative assertions, not a formal proof. The equilibrium analysis for storage tax, recycling strategy, and active-aging trade-offs is missing. Several parameter inconsistencies exist between design and spec layers. The economic model has the right structure but lacks mathematical closure at the level expected of a "design as target state" document.

---

## 2. 发现的问题

### Critical

**C1: Anti-Snowball "Proof" is Qualitative Assertions, Not a Proof**
- File: `design/economy-balance-sheet.md` §4 (lines 234-242)
- Problem: §4 claims a "proof" but contains only four bullet-point assertions:
  1. "边际收益递减：第 N+1 个房间的维护费增长 > 收入增长" — stated without derivation of marginal revenue vs marginal cost curves
  2. "净正反馈克制：玩家必须通过代码优化获得更高效率，而非单纯扩张" — conceptual, no equilibrium condition shown
  3. "自然上限：50 房间附近维护费吞噬全部收入，形成 soft cap" — parameter observation, not a proof that this holds under all valid configurations
  4. "No Teleport + 物流成本" — conceptual
- Impact: The entire anti-snowball design premise rests on an unproven claim. Server operators who tune parameters need to know the equilibrium conditions, not just one illustrative parameterization.
- Fix: Replace with a formal analysis showing:
  - Marginal revenue function as r(n) = expected_income(n)
  - Marginal cost function as c(n) = upkeep(n) + tax(n) + conversion_loss(n)
  - Derive the equilibrium point n* where r'(n*) = c'(n*)
  - Show n* exists and is finite for all valid parameter ranges in §2.1
  - Prove n* is a stable equilibrium (not merely a soft cap from parameter choice)
  - Show the basin of attraction so server operators know which parameter changes shift n*

**C2: Storage Tax Tier Boundaries Create Discontinuous Incentives**
- File: `specs/core/resource-ledger.md` §2.2 (lines 104-118); `design/economy-balance-sheet.md` §2 (lines 33-197)
- Problem: The tiered storage tax uses percentage thresholds (30%, 60%, 85%) with discrete rate jumps (0→1→5→20 bp). At threshold boundaries, marginal tax rate jumps discontinuously. This creates perverse incentives:
  - A player with storage at 29.9% pays 0 tax. At 30.1%, pays 1bp on all units above threshold.
  - The marginal cost of the 30.0%→30.1% transition is a step function.
  - Rational players will oscillate around threshold boundaries—deposit to avoid crossing, withdraw immediately after crossing, creating tick-by-tick micro-optimizations.
- Impact: Creates unintended gameplay complexity—players spend fuel on tax-avoidance micro-management rather than strategic decisions. The step function is also fragile: small parameter changes can shift equilibrium sharply.
- Fix: Either (a) replace with a continuous marginal rate function (e.g., quadratic or sigmoid that smoothly transitions between tiers), or (b) add explicit hysteresis analysis showing the oscillation amplitude is bounded and acceptable, or (c) use integral-based taxation where tax is computed on average storage over a window rather than instantaneous storage.

**C3: Active Aging Penalty Creates Strategic Vacuum**
- File: `design/gameplay.md` §2「Drone 生命周期」(lines 94-102)
- Problem: `active_aging = 110%` (i.e., +10% penalty for executing commands) is defined as a flat multiplier with no equilibrium analysis. Key questions unanswered:
  - At what lifespan does the 10% penalty make a drone net-negative?
  - What is the optimal idle/active rotation strategy? (Send drone to repair, idle it, or keep it active?)
  - Does the 10% penalty + repair system create a stable drone count equilibrium or oscillation?
  - How does this interact with `age_modifier` from body parts? A TOUGH drone (+100 age_modifier) has different optimal cycle than ATTACK (-80).
- Impact: Players lack the information to make rational drone rotation decisions. The mechanic exists but its strategic implications are undocumented.
- Fix: Add a "Drone Lifecycle Equilibrium" subsection analyzing:
  - Expected net resource generation per drone over its lifespan given active/idle/repair cycles
  - Marginal value of repair (Controller vs Depot) given aging penalty
  - Optimal body-part composition considering aging interaction with age_modifier

**C4: Global ↔ Local Cost Asymmetry (1% vs 5%) Lacks Economic Justification**
- File: `design/gameplay.md` §「资源存储模型」(lines 284-316); `specs/core/resource-ledger.md` §2.1 (lines 76-77)
- Problem: `global_deposit_fee = 100 bp (1%)` vs `global_withdraw_fee = 500 bp (5%)`. A 5× asymmetry with no documented rationale. Moreover, `global_deposit_delay = 10 ticks` vs `global_withdraw_delay = 100 ticks`—another 10× asymmetry.
- Impact: PLAYTEST-GATED.md PG-3 explicitly flags this as unresolved: "6% round-trip 成本需要被理解而非被抱怨". But the design documents should provide the economic rationale now—playtest only calibrates parameters, it doesn't invent the rationale.
- Fix: Document the design rationale. Options include: (a) withdrawal penalty discourages "global storage as combat reserve" (mentioned but not formalized), (b) deposit subsidy encourages converting local resources to global (taxable) storage, (c) the asymmetry creates a strategic decision—pay the premium for flexibility or keep resources local. Whatever the rationale, write it into the design.

**C5: Recycle Strategy Equilibrium Missing**
- File: `design/gameplay.md` §「Drone 身体规划」(lines 104-108); `specs/core/resource-ledger.md` §2.5 (lines 168-177)
- Problem: `RecycleRefund = max(10%, remaining_lifespan/total_lifespan × 50%)` is a linear function of remaining lifespan. Combined with `active_aging = 110%` and repair mechanics, there's a complex optimal-recycle decision. The design states the formula but doesn't analyze:
  - Optimal recycle tick: when does refund + replacement cost beat continued operation?
  - Does the 10% floor create a "ride it to death" zone where recycling is always worse?
  - How does repair (Controller vs Depot) interact with recycle timing?
- Impact: Players can't make informed decisions about drone retirement. The mechanic is mathematically defined but strategically opaque.
- Fix: Derive the break-even condition for recycling. Even a simple inequality like `recycle_refund(t) + spawn_cost > expected_remaining_income(t)` would give players a decision framework.

**C6: PvE Budget Cap Interaction with Zone Difficulty Creates Unsolvable Equilibrium**
- File: `design/modes.md` §「NPC 掉落经济」(lines 60-69); `specs/core/resource-ledger.md` §3 (lines 187-220)
- Problem: PvE has a 4-dimensional budget cap (Global ≤ 30% regen, Zone ≤ 50% regen, Player ≤ controller_level × 1000, Event ≤ event_budget_pool). When combined with zone difficulty gradient (Zone 4 with richest rewards), the first-player advantage in Zone 4 is unbounded: a player who reaches Zone 4 first monopolizes the zone budget cap. The design says "PvE 难度是地理属性" but doesn't model the resulting Nash equilibrium.
- Impact: Creates a "first-to-outer-zone" race condition. If the Zone 4 player cap is much smaller than demand, the equilibrium is unstable—players fight for zone access rather than optimizing PvE efficiency.
- Fix: Either (a) make zone budget caps per-player rather than per-zone (so multiple players in Zone 4 don't compete for the same cap), or (b) add an analysis showing that zone budget caps are large enough to accommodate typical player density, or (c) introduce a sharing mechanism within zone caps.

### High

**H1: Balance Sheet Uses Illustrative Parameters Without Formal Derivation**
- File: `design/economy-balance-sheet.md` §1-2 (lines 1-202)
- Problem: The header explicitly says "以下具体参数为目标经济曲线的示意性估算（illustrative estimates）" and "后续 playtest 仅用于校准参数，不改变本文定义的目标曲线语义". But the balance sheet is internally inconsistent: it simultaneously claims to define the "canonical target curve" while admitting parameters are estimates. The 1-room → 2-room transition analysis (line 200) says "free_upkeep 2000 tick 窗口" is sufficient, but this depends on the unverified `base_upkeep=50` parameter.
- Impact: The "target curve" is semantically defined but mathematically unanchored. A server operator cannot distinguish between "this parameter needs calibration" and "this equilibrium property is guaranteed by the formula structure."
- Fix: Separate into two clearly labeled sections: (A) Formally derived properties that hold for all parameters within valid ranges (e.g., "upkeep is superlinear in rooms", "marginal cost always exceeds marginal revenue beyond some n"), and (B) Parameter-dependent properties that are the canonical target but require calibration (e.g., "自维持区间 is 2-10 rooms"). Mark B-items as playtest-gated explicitly within the balance sheet.

**H2: Transport Intercept Subgame Has Undefined Strategy Space**
- File: `specs/core/snapshot-contract.md` §3.2a (lines 224-272)
- Problem: Intercept success rate formula uses `base_success = 60%`, `part_bonus = min(attacker_extra_parts × 5%, 25%)`, `escort_penalty = defender_has_escort ? 30% : 0%`. The clamp range is [10%, 85%]. This creates a 2×2 subgame (intercept/not × escort/not) but the payoff matrix is undocumented:
  - Attacker payoff: `success_rate × stolen_resources - cost_of_drone_time`
  - Defender payoff: `(1 - success_rate) × resources_received - cost_of_escort`
  - The 60% base rate + 30% escort penalty = 30% net when escorted, vs 85% when unescorted. This is a large swing.
  - Is escorting always dominant for high-value transfers? Is intercepting always dominant for unescorted transfers? The mixed-strategy equilibrium is not analyzed.
- Impact: Players cannot determine optimal intercept/escort strategies. The mechanic exists but the strategic depth is unproven.
- Fix: Provide the payoff matrix for the canonical case (allied transfer, 200 tick delay, 2% fee) and show the Nash equilibrium. Even a simple 2×2 matrix analysis would verify that the mechanic has strategic depth rather than a dominant strategy.

**H3: `drone_decay_rate` and `MIN_LIFESPAN` Interact in Undefined Ways**
- File: `design/gameplay.md` §「Drone 生命周期」(lines 94-102) and §「资源与经济」(lines 86-93)
- Problem: `drone_decay_rate` is listed as a configurable parameter with default 10000 (= 1.0), but its exact semantics are undefined. Is it a multiplier on `active_aging`? On base aging rate? The `MIN_LIFESPAN` (default 100 ticks) is mentioned but its authoritative value reference is circular: "MIN_LIFESPAN 权威值见 Resource Ledger §2 统一参数表" — but Resource Ledger §2 doesn't list MIN_LIFESPAN explicitly (it's buried in the gameplay.md body part `age_modifier` system).
- Impact: Undefined interaction between `drone_decay_rate`, `MIN_LIFESPAN`, and `age_modifier` means mod authors can't predict drone lifespan outcomes.
- Fix: Add explicit formula: `actual_aging_per_tick = base_aging × active_multiplier × drone_decay_rate / 10000` where `base_aging = 1.0`, `active_multiplier = 1.0 (idle) / 1.1 (active)`. Then `effective_lifespan = (BASE_AGE + Σ age_modifier) / actual_aging_per_tick`. List MIN_LIFESPAN explicitly in Resource Ledger §2.1.

**H4: Overload Global Cooldown Proof is Referenced But Not Shown**
- File: `design/gameplay.md` §「Overload」(line 745)
- Problem: Overload has "同一目标每 50 tick 最多被 Overload 一次（不限来源）" with the claim that a "下限证明已规范化" (PLAYTEST-GATED.md PG-2). But the proof itself is not in the reviewed documents. The 50-tick global cooldown per target prevents coordinated multi-player Overload spam, but the design doesn't show that 50 ticks is sufficient to prevent "effectively permanent" Overload.
- Impact: The Overload mechanic's anti-abuse guarantee is asserted but unproven.
- Fix: Either include the proof inline or provide a cross-reference to where it lives. The proof should show that with N attackers and 50-tick global cooldown, no target can have `fuel_budget < MIN_FUEL × 0.2` for more than X% of time.

**H5: Free Upkeep Tick Counting Start Point Is Ambiguous**
- File: `specs/core/resource-ledger.md` §2.3 (lines 133, 137)
- Problem: `free_upkeep_ticks` starts counting from "首次 spawn 起" (line 137). But `spawn_cooldown` (default 0, but configurable) could delay first spawn. Does the timer start from world join or first spawn? If a player joins and waits 100 ticks before spawning (due to `spawn_cooldown`), do they lose 100 ticks of free upkeep?
- Impact: Edge case creates ambiguity for server operators and players planning their opening.
- Fix: Specify: `free_upkeep_ticks` starts counting from the tick of the player's first successful `Spawn` command execution. The 2000-tick window is exclusively post-first-spawn. `spawn_cooldown` delays the start but doesn't consume the window.

### Medium

**M1: Resource Ledger §2 Claims Authority but Doesn't List MIN_LIFESPAN**
- File: `specs/core/resource-ledger.md` §2.1 (lines 70-100)
- Problem: gameplay.md delegates `MIN_LIFESPAN` to "Resource Ledger §2 统一参数表" but §2.1 doesn't contain it. The parameter exists only implicitly through `age_modifier` values in gameplay.md §「身体部件类型定义」.
- Fix: Add `MIN_LIFESPAN` entry to Resource Ledger §2.1 unified parameter table with default value 100.

**M2: `new_player_transfer_lock` Covers Sending AND Receiving — Receiving Side Underspecified**
- File: `design/gameplay.md` §「新玩家资源门」(lines 409-418); `specs/core/resource-ledger.md` §2.1 (line 99) and §2.5 (line 177)
- Problem: `new_player_transfer_lock` "禁止发送与接收" (Resource Ledger §2.5 line 177). But the gameplay.md table only shows "禁止资源 transfer（player↔player）" — it doesn't explicitly state that the lock covers both outbound and inbound. The receiving-side lock means a veteran player cannot donate resources to a new player during the lock period. This is an important design decision that should be explicit.
- Impact: Potential confusion about whether veterans can help new players during the lock period.
- Fix: Align gameplay.md table with Resource Ledger: explicitly state "禁止新玩家发送与接收 player↔player 资源转移".

**M3: `global_deposit_delay` ≠ 0 Assertion Conflicts with Tutorial World Configuration**
- File: `design/gameplay.md` §「资源存储模型」line 313: "不可为 0，防止瞬移补给"
- Problem: The assertion says `global_deposit_delay` cannot be 0. But §1 10-minute Golden Path (line 27) says Tutorial world has `code_update_cost = 0` and `new_player_transfer_lock_ticks = 0` — and the economy-balance-sheet.md §3 shows Tutorial has `global_deposit_delay = 10`. The Tutorial world could benefit from `= 0` for onboarding simplicity. The "不可为 0" constraint is overly restrictive for tutorial contexts.
- Impact: Minor: Tutorial world loses onboarding simplicity. But the design principle of "不可为 0" may need a world-mode exception.
- Fix: Either (a) change constraint to `≥ 0` with strong recommendation against 0 for non-Tutorial worlds, or (b) document that Tutorial worlds are special and accept the constraint.

### Low

**L1: Intercept Window "最后 50 tick" for Allied Transfer Is Arbitrary**
- File: `specs/core/snapshot-contract.md` §3.2a (lines 228-236)
- Problem: Allied Transfer has 200 tick delay, interceptable in last 50 ticks. The choice of 50 is undocumented. Why not 100? Or the full window? The asymmetry (first 150 safe, last 50 vulnerable) creates a defender-advantaged timing game that could be interesting but isn't analyzed.
- Fix: Document the design rationale. Even one sentence: "前 150 tick 安全期保证发送方有时间部署 escort，最后 50 tick 是战术窗口."

**L2: Balance Sheet Uses `storage_capacity` That Grows With Rooms, But Formula Missing**
- File: `design/economy-balance-sheet.md` §2.3-2.6
- Problem: The balance sheet shows `storage_capacity` growing from 1,000,000 (1 room) to 4,000,000 (20 rooms) to 3,000,000 (50 rooms — drops?). The 50-room value (3,000,000) is lower than 20-room (4,000,000), which needs explanation. Is this a typo or does storage capacity decrease after a peak?
- Fix: Either document the storage capacity formula (e.g., `per_room_capacity × rooms` with some cap), or fix the 50-room value.

---

## 3. 亮点

1. **Resource Flow Classification (Faucet/Sink/Transfer/Lockup/Unlock)** is excellent. The taxonomy is complete and closed—every resource operation can be classified, and the net flow accounting is sound. This is the kind of formal structure that enables equilibrium analysis.

2. **Transfer Gateway single-entry architecture** (Resource Ledger §1) is well-designed. All resource flows pass through one audit point, preventing escape paths. The execution order (§4) is explicitly defined and deterministic.

3. **4-dimensional PvE budget** (Global/Zone/Player/Event) is structurally sound. The multi-dimensional cap prevents any single faucet from dominating the economy. Using `Blake3` for deterministic event seeding is correct.

4. **Transport Intercept as final design** (snapshot-contract.md §3.2a). The decision to make intercept part of core rather than mod is the right call—it creates strategic depth in the resource transfer subgame that would be missing if all transfers were uninterruptible.

5. **Allied Transfer constraints** (100-tick alliance membership, 500-tick cooldown, daily cap scaled by receiver GCL) are well-structured. The per-receiver cooldown and GCL-scaled cap prevent transfer-dumping abuse.

6. **`new_player_transfer_lock` covering both send and receive** is the correct anti-smurf design. Resource Ledger §2.5 explicitly states bidirectional lock, which closes the "veteran funds smurf" exploit path.

7. **Fixed-point arithmetic mandate** (Resource Ledger §2) is essential for deterministic replay. All rates in basis points, all amounts in integer units. No floating-point anywhere in the economy. This is correct.

8. **Soft-launch PvP transition phases** (gameplay.md §「soft_launch 后 PvP 渐进过渡」) are well-structured: First-Attack Shield → Soft PvP → Full PvP. The progressive exposure prevents the "baptism by fire" problem where new players exit protection and are immediately destroyed.

---

## 4. CrossCheck

- **CX1**: [C2 — Storage tax discontinuity] The threshold-step tax function's oscillation behavior interacts with tick-level decision making. → 建议 **Architecture** 检查 `specs/core/resource-ledger.md` §4 确定性执行顺序 — 同 tick 内 storage 变化是否会导致税基计算使用 pre-tick 或 post-tick 存储量? 这影响阈值边界的微观行为。

- **CX2**: [C5 — Recycle strategy] The optimal recycling problem depends on repair capacity constraints at Controller/Depot. → 建议 **Engine** 检查 `design/engine.md` §3.4.5 — Controller repair queue ordering must be deterministic and documented, as it affects per-drone repair throughput and thus recycle timing.

- **CX3**: [H2 — Intercept subgame] The intercept payoff depends on whether the attacker is visible to defender. → 建议 **Security** 检查 `specs/security/` — 拦截窗口内的 visibility rules。攻击方 drone 必须 `is_visible_to(attacker, destination_room)`，但 defender 是否能提前知道 attacker 在场？

- **CX4**: [H4 — Overload global cooldown] The 50-tick per-target global cooldown relies on correct rejection of duplicate Overload attempts within the window. → 建议 **Architecture** 检查 `specs/core/command-validation.md` §3.10-3.19 — Overload cooldown check must be per-target (not per-attacker) and validated before fuel deduction.

- **CX5**: [C6 — PvE zone budget] Zone-based budget caps interact with room allocation and visibility. → 建议 **Architecture** 检查 zone boundary definitions in world topology spec — how zone membership is determined and whether it's deterministic across replay.

- **CX6**: [L2 — Storage capacity growth] The balance sheet shows non-monotonic `storage_capacity` (4M at 20 rooms → 3M at 50 rooms). → 建议 **Architecture** 检查 storage capacity model — 是否由 `global_storage_capacity` (per-player cap, 1,000,000) 与 per-room storage structures 组合计算? 如果是，balance sheet 数据可能需要修正。

- **CX7**: [General] The economy balance sheet's maintenance cost formula uses `base_upkeep × rooms × (1 + rooms/room_soft_cap)`. → 建议 **Engine** 检查 `specs/core/world-rules.md` — `empire_upkeep_mod` 是否允许模组替换此公式? 如果是，anti-snowball 保证需要明确哪些公式属性（如 superlinearity）是 invariants，哪些是可配置参数。

---

*评审完成时间: 2026-06-30*
*模型: DeepSeek V4 Pro*
*下一阶段: 等待 Speaker 裁决与用户 D-item 决策*