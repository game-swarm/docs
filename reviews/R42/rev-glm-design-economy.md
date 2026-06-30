# R42 Review — rev-glm-design-economy

**Model**: glm-5.2
**Direction**: Design & Economy
**Scope**: design/gameplay.md, design/economy-balance-sheet.md, design/modes.md, specs/core/resource-ledger.md, specs/core/world-rules.md, specs/core/command-validation.md, specs/core/phase2b-system-manifest.md, specs/gameplay/api-idl.md, specs/gameplay/feedback-loop.md, specs/reference/api-registry.md, specs/reference/special-attack-table.md

> 注：task body 中的文件路径（specs/gameplay/world-rules.md 等）与实际目录结构不符。实际文件位于 specs/core/ 和 specs/reference/ 下。本评审基于实际文件路径。

---

## 1. Verdict

**REQUEST_MAJOR_CHANGES**

存在 3 个 Critical 级别的成本/平衡矛盾（经济数值三源不一致、vanilla action 要求不存在的资源、浮点数违反确定性合同），5 个 High 级别机制矛盾（特殊攻击抗性自相矛盾、Heal 机制定义分裂），以及多个 Medium 级别文档一致性问题。这些直接影响经济模型的可实施性和游戏机制的可理解性，必须在冻结前修复。

---

## 2. 发现的问题

### D-C1 [Critical] — 建筑成本三源不一致

**文件**: design/gameplay.md L197-228, specs/core/world-rules.md L555-588, specs/reference/api-registry.md L855

**问题**: gameplay.md（设计文档）中 3 个建筑的成本与 specs 权威源严重冲突：

| 建筑 | gameplay.md | world-rules.md | api-registry.md §10.2 |
|------|:-----------:|:--------------:|:---------------------:|
| PowerSpawn | 5,000 | 1,200 | 1,200 |
| Nuker | 100,000 | 5,000 | 5,000 |
| Depot | 5,000 | 600 | 600 |

**影响**: PowerSpawn 相差 4.17 倍，Nuker 相差 20 倍，Depot 相差 8.33 倍。Nuker 在 gameplay.md 标价 100,000 Energy，这是一个足以改变整个经济平衡的终局建筑——其真实成本（5,000）仅为标注的 1/20。这意味着任何基于 gameplay.md 做经济建模或策略分析的人会得到完全错误的结论。Depot（2.5k hits, repair_aging=5）标价 5,000 而实际 600 也将严重扭曲前期后勤经济。

**修复建议**: 以 api-registry.md §10.2 BuildCost 为权威，统一 gameplay.md 和 world-rules.md 中所有建筑成本。gameplay.md 的 `[[structure_types]]` 定义块必须与 api-registry.md 逐一对齐。

---

### D-C2 [Critical] — Fabricate 要求 Matter，但 Vanilla 默认世界只有 Energy

**文件**: design/gameplay.md L750, L519; specs/reference/special-attack-table.md L26; design/gameplay.md L1204-1210

**问题**:
- Vanilla Ruleset 明确声明：「资源：单一 `Energy`——所有操作消耗 Energy」（gameplay.md L519）
- 但 Fabricate action 的成本为「2000 Energy + 500 Matter」（gameplay.md L750, special-attack-table.md L26）
- gameplay.md 的 `[action_registry.vanilla.Fabricate]` TOML 配置写的是 `cost = { Energy = 2000 }`（L1210），不含 Matter

三处出现不一致：(1) Vanilla 默认世界无 Matter 资源；(2) 文字描述和 canonical table 说需要 Matter；(3) TOML 配置不含 Matter。这意味着在 Standard/Arena（Vanilla 规则集）世界中，Fabricate 要么无法使用（因为没有 Matter 资源），要么 TOML 配置是正确的（只需 2000 Energy）而 canonical table 错误。

**影响**: 这直接阻碍了「Standard 全量启用 8 种 special attack」的设计目标。如果 Fabricate 需要 Matter，它在单一 Energy 世界中不可用，Standard 模式的 vanilla action 集合实际上是 7 个而非 8 个。这破坏了 Phase 2b system manifest 中 S22b `fabricate_buffer` 的设计前提。

**修复建议**: 裁决 Fabricate 在 Vanilla 单 Energy 世界中的成本——要么「仅需 2000 Energy」（修改 canonical table 和文字描述），要么「Vanilla 世界需额外定义 Matter 资源」（修改 Vanilla Ruleset L519 的单 Energy 定义）。

---

### D-C3 [Critical] — world.toml 示例使用浮点数，违反确定性合同

**文件**: specs/core/world-rules.md L49,58,103-104,109,130; design/gameplay.md L312-314,1268

**问题**: 确定性合同（gameplay.md §2.8）明确「禁浮点（f64 跨平台/编译器非确定），所有游戏引擎数值使用定点整数类型」。但world.toml 示例多处使用浮点数：

| 文件 | 行 | 字段 | 值 | 应为 |
|------|:--:|------|:--:|:----:|
| world-rules.md L49 | `decay_rate` | `0.0` | `0` (u32) |
| world-rules.md L58 | `decay_rate` | `0.001` | `10` (×10000) |
| world-rules.md L103 | `transfer_to_global_cost` | `{ Energy = 0.01 }` | `{ Energy = 1 }` 或 bp 参数 |
| world-rules.md L104 | `transfer_from_global_cost` | `{ Energy = 0.05 }` | `{ Energy = 5 }` 或 bp 参数 |
| world-rules.md L109 | `damage_multiplier` | `1.0` | `10000` (fixed<u32,4>) |
| world-rules.md L130 | `decay_rate` | `0.001` | `10` |
| gameplay.md L312 | `transfer_to_global_cost` 默认 | `{Energy: 0.01}` | 同上 |
| gameplay.md L1268 | `memory_spawn_cost` | `{ Energy = 0.5 }` | `{ Energy = 1 }` 或 `micro_cost` |

**影响**: 这些示例是开发者直接参考的配置模板。浮点配置值：
1. 违反 `ResourceCost = {String: u32}` 类型合同——0.01 和 0.5 不是 u32
2. 违反 `damage_multiplier` 是 `fixed<u32,4>`（×10000）的约定——1.0 应为 10000
3. 与 Resource Ledger §2.1 使用 basis points (100bp = 1%) 的表示方式完全不一致
4. 实现者照抄这些值会导致运行时类型错误或静默的非确定性行为

**修复建议**: 全部替换为定点整数表示。`transfer_to_global_cost` 改为引用 Resource Ledger 的 `global_deposit_fee` (100bp)；`damage_multiplier = 10000`；`decay_rate = 0`（不衰减）或 `decay_rate = 10`（×10000 = 0.001）。

---

### D-H1 [High] — Leech 抗性自相矛盾

**文件**: design/gameplay.md L749 vs L1086; specs/reference/special-attack-table.md L25

**问题**:
- gameplay.md §Vanilla Action 表 (L749): Leech 抗性 = **Kinetic**
- gameplay.md `[[special_effects]]` 定义 (L1086): Leech resistance = **Corrosive**
- special-attack-table.md canonical table (L25): Leech Resistance = Target **Kinetic** 抗性

两处权威文档（action 表 + canonical table）都说 Kinetic，但 `[[special_effects]]` 块写 Corrosive。同一个文档内部自相矛盾。

**影响**: Leech 是 Attack body part 的 action（特殊攻击表明确 Body Part = Attack），Attack 造成 Kinetic 伤害。如果 Leech 的抗性检查是 Corrosive，则玩家需要准备两套不同的抗性配置来防御一个 Attack 系 action——这破坏了 body part → damage type → resistance 的直觉映射。

**修复建议**: 统一为 **Kinetic**。修改 `[[special_effects]] name = "leech"` 的 `resistance = "Kinetic"`。

---

### D-H2 [High] — Debilitate 抗性自相矛盾

**文件**: design/gameplay.md L746 vs L1062; specs/reference/special-attack-table.md L22

**问题**:
- gameplay.md §Vanilla Action 表 (L746): Debilitate 抗性 = **Corrosive**
- gameplay.md `[[special_effects]]` 定义 (L1062): Debilitate resistance = **Kinetic**
- special-attack-table.md canonical table (L22): Debilitate Resistance = Target **Corrosive** 抗性

与 D-H1 模式完全相同——action 表 + canonical table 说 Corrosive，`[[special_effects]]` 块说 Kinetic。

**修复建议**: 统一为 **Corrosive**。修改 `[[special_effects]] name = "debilitate"` 的 `resistance = "Corrosive"`。

---

### D-H3 [High] — Heal 机制定义分裂：恢复 HP vs 缩短负面状态

**文件**: design/gameplay.md L727 vs L883-888

**问题**:
- gameplay.md L727 Body part 伤害绑定表: Heal 基础伤害值 = 12, 说明 = 「每 tick 可缩短一个负面状态 10 tick 持续时间」
- gameplay.md L883-888 body_part_types 定义: Heal `base_heal = 12`, description = 「治疗——每 part 恢复 12 HP」

这两个定义描述了**完全不同的机制**：
1. 伤害绑定表说 Heal 的作用是「缩短负面状态持续时间」（类似 Disrupt 的净化功能）
2. body part 定义说 Heal 的作用是「恢复 12 HP」

更令人困惑的是，Fortify（L748）已经覆盖了「清除所有负面状态」功能，如果 Heal 也能缩短状态持续时间，两者的功能边界模糊。

**影响**: 实现者无法确定 Heal 到底做什么。Phase 2b manifest 的 S13 `heal_system`（L209）写入 `PendingHeal[target_id]` buffer——这是 HP 恢复 intent，不是状态缩短 intent。如果 Heal 实际上也缩短状态，那 S13 应该写 status buffer 而非 PendingHeal。这与 R35 D3 的 unique writer contract 冲突。

**修复建议**: 明确 Heal = 纯 HP 恢复（base_heal = 12 HP/part），状态缩短功能移除或归属 Fortify/Disrupt。修改 L727 表格说明为「每 part 每 tick 恢复 12 HP」。

---

### D-H4 [High] — Heal action range 矛盾

**文件**: design/gameplay.md L886; specs/reference/special-attack-table.md L18

**问题**:
- gameplay.md body_part_types Heal: `range = 1`（L886）
- special-attack-table.md canonical table: Heal Range = **3**（L18）

body part 定义 range=1，canonical action table 说 range=3。虽然 world-rules.md L407 提到「ActionRegistry 的 validator 可覆盖此值」，但没有 vanilla action_registry TOML 配置展示 Heal，也没有说明 Heal 的 range=3 来自何处。

**影响**: 玩家根据 body part 定义认为 Heal 只能治疗 1 格内的目标，但 canonical table 说 3 格。这直接影响战斗队形设计——1 格意味着 Heal drone 必须贴身，3 格允许后排治疗。

**修复建议**: 统一 Heal range。如 canonical table 的 range=3 是权威，则修改 body_part_types 中 Heal 的 range 为 3，或在 action_registry vanilla 配置中明确声明 Heal range=3。

---

### D-H5 [High] — RangedAttack body part 成本矛盾

**文件**: design/gameplay.md L879; specs/core/world-rules.md L372; specs/gameplay/api-idl.md L178; specs/reference/api-registry.md L856

**问题**:
| 文档 | RangedAttack 成本 |
|------|:-----------------:|
| gameplay.md (L879) | { Energy = 150 } |
| api-idl.md (L178) | { Energy = 150 } |
| api-registry.md §10.2 (L856) | RANGED_ATTACK=150 |
| world-rules.md (L372) | { Energy = **100** } |

world-rules.md 是唯一写 100 的文档，其余三个权威源均为 150。

**影响**: 50 Energy 的差异在早期游戏（200 Energy 起步资源）是 25% 的成本偏差。world-rules.md 被标注为「配置 Schema」规范，开发者可能直接复制其 body_part_types 定义块。

**修复建议**: 修改 world-rules.md L372 的 RangedAttack cost 为 `{ Energy = 150 }`。

---

### D-H6 [High] — Allied Transfer 延迟语义矛盾

**文件**: design/gameplay.md L1736; specs/core/resource-ledger.md L83

**问题**:
- gameplay.md L1736 Allied 特权表: 「资源 transfer | 仅 global↔local | 可直接 player↔player transfer，**免 convert 延迟**」
- resource-ledger.md §2.1: `allied_transfer_delay` = **200 tick**

gameplay.md 说 allied transfer 「免 convert 延迟」，但 resource-ledger 明确定义了 200 tick 的 allied_transfer_delay。

**影响**: 「免 convert 延迟」可被理解为「即时到账，无任何延迟」，但实际有 200 tick 延迟。这直接影响联盟经济策略——如果玩家以为 allied transfer 是即时的，他们会在紧急情况下依赖一个实际需要 200 tick（约 10 分钟 World 模式）才能到账的转移。

**修复建议**: 修改 gameplay.md L1736 为「可直接 player↔player transfer，免 global deposit/withdraw 延迟（10/100 tick），但受 allied_transfer_delay (200 tick) 约束」。

---

### D-H7 [High] — 建筑类型数量不一致：13 vs 17

**文件**: design/gameplay.md L112; specs/core/world-rules.md L444-589; specs/reference/api-registry.md L855

**问题**:
- gameplay.md L112: 「默认世界提供以下 **13 种**基础类型」
- api-registry.md §10.2 BuildCost 列出 **17 种**建筑（含 Road=10, Wall=50, Rampart=100, Container=100）
- world-rules.md §7.2 列出 **17 种**建筑（同上 4 种额外建筑）
- gameplay.md 的 `[[structure_types]]` 块缺少 Road, Wall, Rampart, Container

**影响**: gameplay.md 是设计域文件，权威性最高。缺少 4 种基础建筑（Road/Wall/Rampart/Container）意味着设计层未完整定义防御和物流基础设施。Road 降低移动疲劳、Wall/Rampart 提供防御——这些是 Screeps 类游戏的核心建筑，不能在设计层缺席。

**修复建议**: 在 gameplay.md 的 `[[structure_types]]` 块中补全 Road, Wall, Rampart, Container，并修正「13 种」为「17 种」。

---

### D-M1 [Medium] — Allied Transfer daily cap 公式 vs 固定值

**文件**: design/economy-balance-sheet.md L230; specs/core/resource-ledger.md L83; specs/reference/api-registry.md L857

**问题**:
- resource-ledger.md §2.1: `allied_daily_cap = max(10_000, receiver_gcl × 20_000)`
- api-registry.md §10.2: 同上公式 + × world_multiplier / 100
- economy-balance-sheet.md §3 L230: 写死 `daily_cap=10000`

balance sheet 写 daily_cap=10000 作为 Standard 的参数值，但公式表明 GCL≥1 时 cap = max(10000, 20000) = 20000。只有 GCL=0（不可能状态）时 cap 才等于 10000。

**修复建议**: balance sheet 应引用公式 `max(10_000, GCL × 20_000)` 而非写死 10000，或注明「GCL=0 时的下限」。

---

### D-M2 [Medium] — Arena 胜利条件描述不匹配

**文件**: specs/gameplay/feedback-loop.md L338; design/modes.md L22

**问题**:
- modes.md L22 定义 5 种可配置 Arena 胜利条件: `fixed_ticks`, `destroy_all_structures`, `full_wipe`, `capture_points_consecutive`, `capture_points_cumulative`
- feedback-loop.md L338: 「胜利条件：摧毁敌方 Spawn，或时限结束时分高者胜」

「摧毁敌方 Spawn」不匹配上述任何条件——`destroy_all_structures` 要求摧毁所有建筑，不是仅 Spawn。

**修复建议**: 修改 feedback-loop.md L338 引用 modes.md 的 5 种配置化条件，或概括为「房主可配置的胜利条件（详见 modes.md §9.1.3）」。

---

### D-M3 [Medium] — storage_capacity 语义模糊

**文件**: design/economy-balance-sheet.md L182-190; specs/core/resource-ledger.md §2.2; design/gameplay.md L311

**问题**:
- gameplay.md L311: `global_storage_capacity` = 1,000,000 per player
- balance sheet §2.7 汇总表中 storage_capacity 随房间数变化: 1M → 3M → 4M → 3M
- resource-ledger.md §2.2 存储税公式使用 `storage_capacity_units`，未说明是全局还是总计

存储税按 Resource Ledger 定义应用于全局存储，但 balance sheet 的 storage_capacity 变化暗示包含本地 Storage 建筑容量。如果存储税应用于总存储（含本地），则与 gameplay.md §8「全局存储余额→存储税，本地存储→完全私有」矛盾。

**修复建议**: 明确 balance sheet 中 storage_capacity 的语义——如为全局存储，修正为固定 1,000,000；如为总量（含本地），需修改存储税公式适用范围声明。

---

### D-M4 [Medium] — Vanilla action_registry TOML 缺少 range 字段

**文件**: design/gameplay.md L1150-1210

**问题**: gameplay.md L1019 的 schema 声明 `range` 为 ✅ 必需字段，但 vanilla action_registry 条目中：
- Hack: 无 range 字段（canonical table 说 range=1）
- Drain: 无 range（canonical table 说 range=1）
- Overload: 无 range（canonical table 说 range=5 LOS）
- Debilitate: 无 range（canonical table 说 range=3）
- Disrupt: 无 range（canonical table 说 range=1）
- Fortify: 无 range（canonical table 说 range=1 self/ally）
- Leech: 有 range=1 ✓
- Fabricate: 有 range=1 ✓

6 个 vanilla action 缺少自身 schema 声明的必需字段。此外，Attack/RangedAttack/Heal 三种 basic_combat action 完全无 TOML 配置展示。

**修复建议**: 为所有 vanilla action 补全 range 字段，或声明 vanilla action 的 range 由 canonical table 权威定义、schema 的 required 标记不适用于 vanilla 预注册条目。同时补充 3 种 basic_combat action 的 TOML 示例或说明其注册方式。

---

### D-M5 [Medium] — Recycle 公式使用浮点表示

**文件**: specs/core/command-validation.md L339

**问题**: `refund_pct = max(0.1, 0.5 × (remaining_lifespan / total_lifespan))` 使用 0.1 和 0.5 浮点字面量。虽然可能是数学表达式而非代码，但项目禁止浮点。Resource Ledger §2.5 使用 1000bp 和 5000bp——同一公式两种表示法。

**修复建议**: 改为 `refund_rate_bp = max(1000, 5000 × remaining_lifespan / total_lifespan)` 与 Resource Ledger 保持一致。

---

### D-M6 [Medium] — memory_upkeep_cost 单位语义不清

**文件**: design/gameplay.md L1269

**问题**: `memory_upkeep_cost = { Energy = 100 }` 注释写「(basis points, ×10000)」。但 `memory_upkeep_cost` 的类型是 `ResourceCost = {String: u32}`（资源量），不是费率。100 是 100 Energy per byte per tick，还是 100 bp = 1% per byte per tick？如果是后者，1% 的什么值的 1%？

**修复建议**: 明确 memory_upkeep_cost 的语义——如为每 byte 每 tick 扣除固定 Energy，删除「basis points」注释；如为百分比费率，需重新定义类型。

---

### D-M7 [Low] — Overload 全局冷却 vs per-drone 冷却标注混乱

**文件**: design/gameplay.md L745; specs/reference/special-attack-table.md L21

**问题**:
- gameplay.md L745: Overload 冷却 = 「200 tick（drone 冷却）」
- special-attack-table.md L21: Overload Cooldown = 「200 (per drone)」
- gameplay.md L745 描述中还有「全局冷却：同一目标每 50 tick 最多被 Overload 一次」

Overload 有两个不同的冷却维度：(1) per-drone 200 tick 冷却，(2) per-target 50 tick 全局冷却。特殊攻击表中只记录了 per-drone 冷却，未记录 per-target 全局冷却。command-validation.md L296 明确了「全局冷却（50 tick per target）」作为独立约束，但 canonical table 缺少这个维度。

**修复建议**: 在 special-attack-table.md 的 Cooldown 列中补充 Overload 的双维度冷却：「200 (per drone) + 50 (global per target)」。

---

## 3. 亮点

1. **Resource Ledger 单一权威设计**：将所有经济费率收敛到 §2.1 统一参数表 + basis points 定点表示，并明确其他文档「必须引用此文档参数，不得独立定义公式」——这是极其正确的架构决策。economy-balance-sheet.md 严格声明「所有费率、公式以 resource-ledger 为唯一权威源」并逐行标注可重算输入，实现了数值可审计性。

2. **存储税 tiered 公式精确定义**：resource-ledger.md §2.2 的累进税公式清晰、可重算、用整数 basis points。economy-balance-sheet.md 对每个房间数场景标注了完整的 tier formula 可重算输入——这种「数值可追溯」设计在游戏经济文档中极为罕见且高质量。

3. **Economy 分类账（Faucet/Sink/Transfer/Lockup/Unlock）**：gameplay.md §经济分类账将每条经济规则按资源流向分类，并标注目标日均增长率——这是游戏经济平衡分析的正确方法论框架。

4. **Phase 2b System Manifest 的 Unique Writer Contract**：phase2b-system-manifest.md 的 R/W 矩阵 + 唯一 writer 约定 + buffer 生命周期管理，是保证确定性模拟的严谨工程方案。S16-S22b 只写 typed buffer、S22 作为唯一 StatusState writer 的分层设计消除了并行写入冲突。

5. **CommandValidation 的可见性优先原则**：command-validation.md §5 的「所有涉及 target_id 的校验，第一步必须是可见性检查」+ NotVisibleOrNotFound 安全合并码，正确实现了信息泄露防护。

6. **self-sustaining 区间设计目标**：economy-balance-sheet.md 明确「2-10 房间自维持可达，20 房后递减，50 房软上限」的目标曲线，并通过维护费超线性增长 + 存储税 + 物流成本三重机制验证。这为 playtest 校准提供了清晰的锚点。

---

## 4. CrossCheck

- **CX-1**: world.toml 中的 `damage_multiplier = 1.0` (float) 与 determinism contract 的 `fixed<u32,4>` 类型 → 建议 **Architect** 检查 world.toml schema 的类型约束是否在 engine 解析层强制
- **CX-2**: S22 `status_advance_system` 中 Leech 的处理写「不写 PendingDamage — Leech HP 影响由 age acceleration + aging/decay 自然覆盖」(L284-286) → 建议 **Architect** 检查 Leech 的 HP 影响是否确实通过 age 而非 damage 路径实现，这与 body part 表说 Leech 造成 Kinetic 伤害可能有架构级冲突
- **CX-3**: `allied_daily_cap_world_multiplier` 中 Arena=50 (0.5×) 与 Tutorial=500 (5.0×) 的倍率 → 建议 **Cross-Cutting** 检查这些倍率是否与 modes.md 中 Arena/Tutorial 的经济隔离设计一致
- **CX-4**: gameplay.md §2.9 Drone 间消息机制引用 `[u8; 256]` payload 但 IDL 中无 Message 类型定义 → 建议 **Cross-Cutting** 检查 api-idl.md 和 api-registry.md 是否遗漏 Message 类型注册
- **CX-5**: economy-balance-sheet.md §2.7 中 50 room storage_capacity=3,000,000 但 20 room=4,000,000（非单调递增）→ 建议 **Cross-Cutting** 检查存储容量是否不应随房间数增长（可能是 balance sheet 参数笔误）
