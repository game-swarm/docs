# R42 Design & Economy Review — rev-dsv4-design-economy

**Model**: DeepSeek V4 Pro
**Scope**: gameplay.md, economy-balance-sheet.md, modes.md, resource-ledger.md, world-rules.md, command-validation.md, phase2b-system-manifest.md, api-idl.md, feedback-loop.md, api-registry.md, special-attack-table.md
**Focus**: Cost/balance/mechanic contradictions, Nash equilibrium analysis, resource flow modeling, anti-snowball proof completeness

---

## 1. Verdict

**REQUEST_MAJOR_CHANGES**

4 Critical findings, 5 High findings, 4 Medium findings. The design has a solid economic foundation with a well-structured anti-snowball mechanism and coherent Resource Ledger model. However, there are severe cross-document numerical contradictions — most critically the Leech special attack parameters, structure build costs, and Fabricate cost — that must be resolved before this design can be considered internally consistent. The economic model's tiered storage tax and superlinear upkeep are mathematically sound, but the canonical numerical authority chain is fractured in multiple places.

---

## 2. 发现的问题

### D-C1: Leech 参数四向分裂 — Kinetic vs Corrosive, 100 vs 150 tick

**Severity**: Critical

**Files & lines**:
- `specs/reference/special-attack-table.md:25` (canonical): Leech cooldown=100, damage_type=Kinetic, resistance=Kinetic
- `specs/core/world-rules.md:885`: Leech cooldown=100, resistance=Kinetic ✅ matches canonical
- `design/gameplay.md:749`: Leech cooldown=**150**, damage_type=Kinetic, resistance=Kinetic ❌ cooldown mismatch
- `specs/core/command-validation.md:638-641`: Leech damage_type=**Corrosive**, cooldown not listed ❌ damage type mismatch
- `design/gameplay.md:1086`: `[[special_effects]] leech` defines resistance=**Corrosive** ❌ resistance mismatch

**Impact**: Five documents describe Leech using four different parameter sets. The canonical authority (`special-attack-table.md`) says Kinetic/100 tick cooldown. But `gameplay.md`'s action table says 150 tick; its `[[special_effects]]` block says Corrosive resistance; `command-validation.md` says Corrosive damage type. Implementers have no way to determine the correct parameters. An incorrect cooldown (100 vs 150) creates a 50% DPS difference; wrong resistance type breaks the entire rock-paper-scissors counterplay matrix.

**Fix**: Align all documents to `special-attack-table.md` canonical: Leech = Kinetic damage_type, Kinetic resistance, 100 tick cooldown. Fix `gameplay.md:749` cooldown, `gameplay.md:1086` resistance, and `command-validation.md:638-641` damage_type. Add CI cross-reference: all Leech parameter mentions must hash-match the canonical table.

---

### D-C2: 建筑建造成本三向分叉 — PowerSpawn (5000/1200), Nuker (100000/5000), Depot (5000/600)

**Severity**: Critical

**Files & lines**:
- `design/gameplay.md:199,215,228`: PowerSpawn=5000, Nuker=100000, Depot=5000
- `specs/core/world-rules.md:498-500` (truncated, but consistent with gameplay for listed types)
- `specs/reference/api-registry.md:855` (§10.2 BuildCost): PowerSpawn=**1200**, Nuker=**5000**, Depot=**600**

**Impact**: `api-registry.md` BuildCost table (generated from `economy.idl.yaml`) declares massively different values for three building types compared to `gameplay.md`/`world-rules.md`. The differences are extreme:
- Nuker: 100,000 vs 5,000 (20× divergence)
- PowerSpawn: 5,000 vs 1,200 (4.2× divergence)
- Depot: 5,000 vs 600 (8.3× divergence)

The api-registry.md §10 warning says "禁止手写经济数值" — making this a generator-vs-source discrepancy, not a simple typo. If the economy.idl.yaml is correct, gameplay.md and world-rules.md are catastrophically wrong. If gameplay.md/world-rules.md are correct, the IDL generation pipeline has produced corrupt output.

**Fix**: Resolve which source is canonical, synchronize all three, add CI gate: all building cost arrays must match across gameplay.md, world-rules.md, and api-registry.md §10.2.

---

### D-C3: Fabricate 消耗在 gameplay.md vanilla ActionRegistry 中缺少 Matter

**Severity**: Critical

**Files & lines**:
- `specs/reference/special-attack-table.md:26` (canonical): `2000 Energy + 500 Matter`
- `specs/core/world-rules.md:886`: `2000E + 500 Matter` ✅
- `specs/core/command-validation.md:653`: `2000 Energy + 500 Matter` ✅
- `design/gameplay.md:1209-1210` (vanilla ActionRegistry definition): `cost = { Energy = 2000 }` ❌ **Matter 缺失**

**Impact**: The vanilla ActionRegistry Fabricate entry in gameplay.md — which is presented as the canonical TOML configuration for the server — omits the 500 Matter cost. A server admin copying this configuration would enable Fabricate at 40% of its intended cost, creating an exploitable economic bypass. Given that Fabricate converts enemy drones to player-owned structures, the missing cost creates a risk-free conversion exploit.

**Fix**: Add `Matter = 500` to `gameplay.md:1210` Fabricate cost. Verify all vanilla ActionRegistry entries in gameplay.md match `special-attack-table.md` canonical params.

---

### D-C4: RangedAttack body part cost 不一致 (100 vs 150)

**Severity**: Critical

**Files & lines**:
- `specs/core/world-rules.md:372`: RangedAttack cost = `{ Energy = 100 }`
- `design/gameplay.md:878`: RangedAttack cost = `{ Energy = 150 }`
- `specs/gameplay/api-idl.md:178`: RangedAttack = `{ Energy: 150 }`
- `specs/reference/api-registry.md:856` (SpawnCost): `RANGED_ATTACK=150`

**Impact**: Three of four sources say 150, but `world-rules.md` — which is the canonical `[[body_part_types]]` definition document — says 100. A 50% cost discrepancy on a frequently-used body part cascades into spawn cost miscalculation, economy balance distortion, and recycle refund errors.

**Fix**: Align `world-rules.md:372` to 150 Energy. Add CI validation that all `[[body_part_types]]` cost arrays match across gameplay.md, world-rules.md, and api-idl.md `body_cost` section.

---

### D-H1: Tutorial 世界默认启用 Allied Transfer

**Severity**: High

**Files & lines**:
- `design/economy-balance-sheet.md:213`: allied_transfer_enabled column shows `true` for Tutorial

**Impact**: Tutorial world has free_upkeep_ticks, no storage tax, free deployment, and a dedicated learning environment — yet defaults to `allied_transfer_enabled = true`. This allows resource transfer between players in a beginner world, undermining the safe learning environment. New players could be scammed or pressured into unfavorable resource transfers. The footnote (L230) notes "Novice/Tutorial 可通过 world.toml 禁用" — but the **default** should be `false` for Tutorial, enabling it only if explicitly configured. This is consistent with how special attacks are all disabled in Tutorial (`mode-unlock-strategy` in phase2b-system-manifest.md L337).

**Fix**: Change Tutorial `allied_transfer_enabled` to `false` (default disabled). Update the footnote to reflect that Tutorial disables it by default and requires explicit `world.toml` opt-in.

---

### D-H2: Economy Balance Sheet 自洽性 — 5/10/20/50 房间存储税计算使用了不一致的 storage_capacity

**Severity**: High

**Files & lines**:
- `design/economy-balance-sheet.md:97` (5 rooms): storage_capacity=1,000,000, stored_total=450,000
- `design/economy-balance-sheet.md:120` (10 rooms): storage_capacity=**3,000,000**, stored_total=1,650,000
- `design/economy-balance-sheet.md:143` (20 rooms): storage_capacity=**4,000,000**, stored_total=2,880,000
- `design/economy-balance-sheet.md:167` (50 rooms): storage_capacity=**3,000,000**, stored_total=2,700,000

**Impact**: The storage_capacity grows 1M→3M→4M between 5/10/20 rooms, then inexplicably drops to 3M at 50 rooms. The summary table (L186-190) carries these values through. This is not explained by any game mechanic — `global_storage_capacity` is per-player (api-registry.md:557 says 1,000,000 units), not per-room. The varying capacities suggest the balance sheet is modeling different assumptions per scenario rather than applying a consistent per-player capacity. This undermines the claim that storage tax is calculated uniformly from a tiered formula.

**Analysis**: If storage_capacity is fixed at 1,000,000 across all scenarios, the storage tax calculations change dramatically. At 50 rooms with 2,700,000 stored but only 1,000,000 capacity, the player would be at 270% capacity — impossible under the model. The balance sheet's illustrative nature is disclosed (L5 "illustrative estimates"), but the inconsistent capacity values make it impossible to verify the tiered tax formula.

**Fix**: Either (a) document that storage_capacity scales with rooms/Controller level (and define the scaling function in Resource Ledger), or (b) normalize all scenarios to a consistent per-player storage_capacity and adjust stored_total to realistic values. The current mixed approach breaks formula verifiability.

---

### D-H3: Economy Balance Sheet 中 "canonical target curve" 与 "illustrative estimates" 身份冲突

**Severity**: High

**Files & lines**:
- `design/economy-balance-sheet.md:5`: "Canonical target curve 初始参数化... illustrative estimates"
- `design/economy-balance-sheet.md:180`: "所有数值为 canonical target curve 的初始参数化（illustrative estimates）"

**Impact**: The document simultaneously claims these are the "canonical" target and "illustrative" estimates. Per the project's AGENTS.md: "设计即目标状态... 文档呈现的是最终设计". If the numbers are illustrative, they shouldn't carry canonical weight. If they're canonical, the "illustrative" disclaimer undermines their authority. The playtest-gating reference (L192 "playtest 仅用于校准参数") further muddies this: in a no-MVP/no-phase design philosophy, either the numbers are final or they're not.

**Fix**: Choose one stance: (a) these ARE the canonical target numbers — remove "illustrative estimates" language and all hedging. The balance sheet BECOMES the design target, and playtest data is used to verify (not calibrate) parameters. Or (b) these are illustrative — rename the document, remove "canonical" claims, and defer parameter authority to Resource Ledger §2 exclusively.

---

### D-H4: Leak 在 gameplay.md special_effects 定义中 damage_type/resistance 与 canonical table 冲突

**Severity**: High

**Files & lines**:
- `specs/reference/special-attack-table.md:25`: Leech = Kinetic damage, Kinetic resistance
- `design/gameplay.md:1080-1087`: `[[special_effects]] name = "leech"` defines `resistance = "Corrosive"`

**Impact**: The `[[special_effects]]` block in gameplay.md is presented as the canonical configuration for world.toml special effect definitions. It claims Leech's resistance check is against `Corrosive` damage type. But the canonical action table says `Kinetic`. This means:
1. The resistance check and damage type are different damage types — a fundamental category error
2. If the special_effects definition is used for validation, Leech would check Corrosive resistance while dealing Kinetic damage — the resistance check becomes irrelevant

This is distinct from D-C1: D-C1 is about the action parameter table; D-H4 focuses on the special_effects configuration block which governs how the engine's handler validates and applies the effect.

**Fix**: Change `resistance = "Kinetic"` in `gameplay.md:1086`. The special_effects `leech` resistance must match the action's `damage_type` (Kinetic).

---

### D-H5: 资源 Ledger 执行顺序中 UpkeepDeduction 的 deficit 惩罚与 balance sheet 乐观假设不匹配

**Severity**: High

**Files & lines**:
- `specs/core/resource-ledger.md:299`: "连续 3 tick deficit 触发 drone 饥饿惩罚（效率 −50%），连续 10 tick deficit 触发 drone 强制死亡"
- `design/economy-balance-sheet.md:150`: 20-room scenario "净亏损（优化）-880/tick" — per-tick deficit

**Impact**: The balance sheet shows negative net flow at 20 and 50 rooms (deficits of -880 and -10,865 per tick). Under Resource Ledger's deficit punishment rules, these players would trigger efficiency -50% at tick 3 of continuous deficit, and drone forced death at tick 10 — making the balance sheet scenario of "大帝国需要顶尖代码和 PvE 农场" unachievable because the deficit itself destroys the economy before optimization can compensate. The balance sheet's steady-state deficit modeling is inconsistent with Resource Ledger's non-linear punishment curve.

**Fix**: Either (a) the balance sheet must model the deficit punishment cascade (showing that a -880/tick deficit is not actually sustainable), or (b) Resource Ledger's deficit threshold should be raised for large empires (e.g., deficit tolerance scales with room count). The current combination makes the "20 rooms self-sustaining with good code" claim mathematically impossible.

---

### D-M1: Controller repair 在 economy-balance-sheet 和 gameplay 中为"免费"，但在 resource-ledger 中缺少明确经济建模

**Severity**: Medium

**Files & lines**:
- `design/economy-balance-sheet.md:223-224`: `controller_repair_cost = 0, controller_repair_limit = range/capacity/queue`
- `design/gameplay.md:102`: Controller "免费" repair
- `specs/core/resource-ledger.md:154`: "Controller repair 免费，只受物理约束限制"

**Impact**: All documents agree Controller repair is free — good. But the balance sheet never models the queue contention cost. With a limited repair_capacity per Controller (determined by RCL), large drone armies will experience repair queue delays. This queue delay is an implicit economic cost (drones aging while waiting for repair) that the balance sheet doesn't account for. The repair capacity constraint is mentioned (L224 `range/capacity/queue`) but not quantified in the balance sheet scenarios.

**Fix**: Note in the balance sheet that Controller repair queue time is an implicit cost not modeled in the per-tick flow. Optionally provide a model for expected queue delay at various drone counts per RCL level.

---

### D-M2: PvE budget cap 的 30% 世界再生上限缺乏经济合理性论证

**Severity**: Medium

**Files & lines**:
- `specs/core/resource-ledger.md:193`: "Global ≤ 世界再生总量 × 30%"
- `design/modes.md:69`: "max_pve_output_per_tick 默认 = 全局 NPC 产出 / tick ≤ 世界再生总量 × 30%"

**Impact**: The 30% cap is stated but never justified. Why 30% and not 20% or 50%? If world regeneration is the primary faucet and PvE is meant to be a meaningful income source (as the balance sheet assumes, contributing 50-500 per tick at 10-50 rooms), capping it at 30% of total world regen means PvE becomes less valuable per-player as player count grows. In a 500-player world, each player's share of the 30% PvE pool averages 0.06% of world regen — making PvE economically negligible. This undermines the balance sheet's reliance on PvE income as a revenue source.

**Fix**: Either (a) provide the economic rationale for the 30% cap with player-count scaling analysis, or (b) consider a per-player or per-zone PvE budget model that doesn't dilute with player count.

---

### D-M3: Per-player drone cap (50) vs per-room drone cap (500) 交互语义不清晰

**Severity**: Medium

**Files & lines**:
- `specs/reference/api-registry.md:547`: "Per-player drone cap = 50 (per-room per-player baseline)"
- `specs/reference/api-registry.md:548`: "Per-room drone cap = 500"
- `design/gameplay.md:437`: "Room drone cap (50→500)"

**Impact**: If per-player per-room cap is 50 and per-room cap is 500, the constraint interaction is: `min(player_cap × players_in_room, room_cap)`. But this isn't stated. With 10 players in one room, the per-player cap (50 × 10 = 500) equals the room cap (500), creating a zero-sum allocation game. The gameplay doc says "50→500" suggesting the cap scales, but the scaling function (by RCL? by player count?) is not defined. This creates an economic externality: a player's drone capacity depends on how many other players are in the same room — a dynamic not modeled in any balance sheet scenario.

**Fix**: Define the exact constraint formula: `per_room_allocation = min(player_cap, room_cap / max(1, players_in_room))` or similar. Document the scaling interaction in gameplay.md §anti-snowball.

---

### D-M4: Progressive storage tax tiers 在 economy-balance-sheet 中计算正确，但与 resource-ledger 公式的 taxable_units 解释存在歧义

**Severity**: Medium

**Files & lines**:
- `specs/core/resource-ledger.md:102-110`: Storage tax tiered formula with `taxable_units_in_tier`
- `design/economy-balance-sheet.md:97`: 5-room calculation: `(450,000 - 300,000) × 1bp / 10000`

**Impact**: The balance sheet's tax calculation at 5 rooms implicitly assumes `storage_capacity = 1,000,000` and applies `(450,000 - 300,000) × 1bp / 10000 = 15`. But the resource-ledger formula also includes a `tier_width_pct` term that isn't shown in the balance sheet's "tier formula" column. When storage exceeds 60% capacity (600,000 units with cap=1M), the balance sheet's simplified `(stored - threshold) × rate` formula breaks down because tier 2 (60-85%) would need a separate calculation. The 5-room scenario doesn't hit tier 2 (450K < 600K) so it's accidentally correct, but the formula simplification is misleading. At 10 rooms with cap=3M and stored=1,650,000 (55%), the calculation hits the same accidentally-correct territory. But the table claims to use the full tiered formula while actually using a simplified threshold subtraction.

**Fix**: Either explicitly apply the full tiered formula in every balance sheet row (including the tier_width and cap% conversion), or note that all scenarios happen to fall within tier 1 range and the simplified formula is a valid shortcut for those specific inputs.

---

## 3. 亮点

1. **Resource Ledger 单一切入点设计极为优秀**。将所有资源流动（Local/Global/Allied/PvE/Recycle/Build/Spawn）收敛到同一个 Transfer Gateway，配合确定的 TickTrace 审计轨迹，这从根本上消除了资源逃逸路径。`ResourceOperation` 枚举 + 执行顺序模型（§4）形成了一个可被数学验证的封闭经济系统。

2. **Anti-snowball 的 O(n²) 维护费模型数学正确**。Economy Balance Sheet 中的 `upkeep = base_upkeep × rooms × (1 + rooms / room_soft_cap)` 公式确保了边际收益递减。50 房间维护费是 5 房间的 40 倍（而非 10 倍线性）——这是正确的超线性惩罚。证明结构完整：投入→产出→边际递减→自然上限的四步论证成立。

3. **累进存储税 tier 设计精准**。`[(30,0),(60,1),(85,5),(100,20)]` 的阶梯结构在 Resource Ledger 中的 tiered 公式完全正确：小型持有者免税，中型持有者轻微税负，大型持有者加速消耗。这防止了资源囤积垄断，同时不惩罚正常运营——是一个 Nash 均衡友好型设计。

4. **Recycle 退还公式的经济闭合性好**。`max(10%, remaining_lifespan/total_lifespan × 50%)` 的 lifespan-proportional 退还模型精确防止了"末期回收→重生"套利循环。数学验证通过：末期(10% lifespan)退还仅 10% body_cost，无法形成正反馈套利。

5. **Phase 2b System Manifest 的 Scheduling 完整性**。31 个 system 的串行/并行调度、StatusState unique writer contract、buffer 生命周期管理——构成一个没有数据竞争的确定性执行引擎。S14 special_attack_reducer 的 `Hack > Drain > Overload > Debilitate > Disrupt > Fortify > Leech > Fabricate` 优先级链是合理的 counterplay 设计。

6. **PvE Budget 四维账本控制**。Player/Zone/Global/Event 四层预算约束防止了 NPC 刷怪经济的无限放大，与 Resource Ledger 的 faucet/sink 分类一致。这避免了"刷怪经济压倒 PvP 战略价值"的常见设计陷阱。

---

## 4. CrossCheck

以下是我怀疑但超出 Design & Economy 方向范围的问题：

- **CX-1: TickTrace envelope 22 字段在 api-registry 和 persistence-contract 中的一致性** — `api-registry.md:664-687` 列出了 22 个 TickInputEnvelope 字段，但 `persistence-contract.md` 是否也声明了相同数量和类型的字段需要验证。→ 建议 **Architect** 方向检查 `persistence-contract.md` 的 TickTrace 字段是否与 api-registry 一致。

- **CX-2: Phase2b System Manifest 的 system 数量** — `phase2b-system-manifest.md` 声称 31 systems，但 R30 B1 新增的 S22a/S22b 改变了 system counting。`api-registry.md` 或 `engine.md` 是否引用了过时的 system count 需要检查。→ 建议 **Cross-Cutting** 方向扫描所有文档中对 system manifest 计数的引用。

- **CX-3: Special attack 在 Tutorial/Novice 模式下的禁用范围** — `phase2b-system-manifest.md:337` 说 Tutorial 和 Novice 全部禁用 special attacks，但 `gameplay.md:758` 表格也说了相同的话。需要确认 `api-idl.md`、`command-validation.md` 和 `api-registry.md` 是否都一致地反映了这个禁用策略。→ 建议 **Cross-Cutting** 方向验证 mode-unlock 策略在所有文档中的一致性。

- **CX-4: Vanilla Ruleset 中 core defaults 跨越三个文档的重复声明** — gameplay.md §2、world-rules.md §2、economy-balance-sheet.md §3 都声明了默认参数表（base_upkeep, room_soft_cap 等），但这些表之间存在细微的字段覆盖差异。→ 建议 **Cross-Cutting** 方向做 cross-document field comparison，确认没有未标记的冲突。

- **CX-5: `contract_settlement` 和 `merchant_npc` 在 Resource Ledger §7 中标记为 Out-of-Scope，但 `gameplay.md` 的市场交易标记为 "RFC 占位"** — 这两个 "不在当前设计范围内" 的声明是否一致需要验证。→ 建议 **Architect** 方向检查所有 Out-of-Scope/RFC 标签的一致性。
