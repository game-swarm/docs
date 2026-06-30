# R44 Design-Economy Review — glm-5.2

> Reviewer: 架构师评审员 (glm-5.2)
> Scope: Gameplay coherence, Economy balance, Incentive alignment, Progression, Emergent strategy
> Documents reviewed: design/README.md, design/gameplay.md, design/economy-balance-sheet.md, design/architecture.md, design/engine.md, design/modes.md, design/interface.md, specs/core/resource-ledger.md, specs/core/world-rules.md, specs/core/tick-protocol.md, specs/core/command-validation.md, specs/gameplay/feedback-loop.md, specs/gameplay/api-idl.md, specs/gameplay/PLAYTEST-GATED.md, specs/reference/special-attack-table.md, specs/reference/api-registry.md

---

## SS1 Critical Findings (Blockers)

### SS1-1: Fabricate 资源消耗与 Vanilla 单资源体系冲突 [Critical]

**Location**: `design/gameplay.md` L750, `specs/reference/special-attack-table.md` L26, `specs/core/world-rules.md` L886

Vanilla 默认世界仅定义 `Energy` 一种资源（`design/gameplay.md` L519, `specs/core/resource-ledger.md` L124）。但 Fabricate 的 canonical 成本为 `2000 Energy + 500 Matter`。Vanilla 世界中不存在 `Matter` 资源类型——这意味着在 Vanilla 默认世界中，Fabricate 不可用或成本定义不一致。

special-attack-table.md L26 明确标注 `2000 Energy + 500 Matter`，world-rules.md L886 也引用了相同成本。但 IDL `StructureType` enum 不包含 `Matter`，`ResourceName` 在 Vanilla 里只有 `Energy`。

**Impact**: 玩家在 Standard/Arena 默认世界启用所有 8 个 special attack 时，Fabricate 因缺少 Matter 资源而无法执行或行为未定义。这违反了"Standard 全量启用 11 种 vanilla action"的承诺。

**Fix**: 二选一——
- (A) Fabricate 在 Vanilla 世界的成本改为纯 Energy（如 `5000 Energy`），Matter 仅作为多资源世界的可选配置。
- (B) 在 Fabricate 的 action 定义中声明 `cost` 为 world.toml 可覆盖项，Vanilla 默认使用纯 Energy 等价成本，仅当世界定义了 Matter 时才使用 Matter。

### SS1-2: Leech 冷却时间三文档不一致 [Critical]

**Location**: `design/gameplay.md` L749, `specs/reference/special-attack-table.md` L25, `specs/core/world-rules.md` L885

- `design/gameplay.md` L749: Leech 冷却 **150 tick**
- `special-attack-table.md` L25: Leech 冷却 **100 tick (per drone)**
- `world-rules.md` L885: Leech 冷却 **100 tick**

special-attack-table.md 声称自身为"canonical 参数表"，但 gameplay.md 给出了不同的 150 tick 值。同一参数在权威源与引用源之间存在 50% 偏差。

**Impact**: 实现者无法确定 Leech 的真实冷却时间。WASM SDK 根据不同源生成不同常量，导致跨世界/跨实现的行为分叉。

**Fix**: 确认 canonical 值（推测为 100 tick，因 2 个文档一致），修正 `design/gameplay.md` L749 的值。

### SS1-3: RangedAttack body part cost 在 gameplay.md 与 IDL/Registry 间不一致 [Critical]

**Location**: `design/gameplay.md` L879, `specs/gameplay/api-idl.md` L202, `specs/reference/api-registry.md` L812

- `design/gameplay.md` L879: RangedAttack cost = `{ Energy = 150 }`
- `specs/gameplay/api-idl.md` L202: `RangedAttack: { Energy = 150 }` — 一致
- `specs/core/world-rules.md` L372: `cost = { Energy = 100 }` — **不一致**

world-rules.md §7.1 中 RangedAttack 的 cost 定义为 100 Energy，而 IDL 和 gameplay.md 定义为 150 Energy。这是一个 50% 的成本差异。

**Impact**: 依赖 world-rules.md body part 定义实现 `body_cost` 的代码会生成错误的成本表。

**Fix**: 统一为 150 Energy（IDL 为 canonical 机器源），修正 `world-rules.md` L372。

### SS1-4: Debilitate 抗性类型 gameplay.md 与 canonical table 冲突 [High]

**Location**: `design/gameplay.md` L746, `specs/reference/special-attack-table.md` L22, `specs/core/world-rules.md` L882, `specs/core/world-rules.md` L659-662

- `design/gameplay.md` L746: Debilitate 抗性 = `Corrosive`
- `special-attack-table.md` L22: Debilitate 抗性 = `Corrosive` — 一致
- `world-rules.md` L882: Debilitate 抗性 = `Corrosive` — 一致
- **但** `world-rules.md` L659-662 中 `[[special_effects]]` 定义 `debilitate` 的 `resistance = "Kinetic"`

同一文档 world-rules.md 内部就存在矛盾：§7.8 特殊攻击方式表写 Corrosive，§7.4 special_effects 定义写 Kinetic。

**Impact**: Debilitate 的抗性检查在实现中可能使用错误类型，导致完全不同的防御计算结果。

**Fix**: 确认 canonical 抗性（推测为 Corrosive，因 3 个位置一致），修正 `world-rules.md` L662 的 `resistance` 值。

### SS1-5: Economy Balance Sheet 中 50 房间 storage_capacity 与 20 房间不一致 [High]

**Location**: `design/economy-balance-sheet.md` L164, L140

- 20 房间行: `storage_capacity = 4,000,000`
- 50 房间行: `storage_capacity = 3,000,000`

全局存储容量是 per-player（默认 1,000,000 units，`resource-ledger.md` L124），world.toml 可调。但 50 房间玩家的 storage_capacity (3M) 低于 20 房间玩家 (4M) 没有任何经济逻辑解释。这不可能是设计意图——更大的帝国不应有更小的全局存储上限。

**Impact**: 存储税计算基于 storage_capacity，错误的值导致税收计算偏差。50 房间行的存储税 (364) 可能严重偏离实际值。

**Fix**: 修正 50 房间行的 storage_capacity 为合理值（如 5,000,000 或更高），使其与帝国规模正相关。或明确标注各行 storage_capacity 的推导理由。

### SS1-6: Economy Balance Sheet §2.2 收入计算存在数学内部矛盾 [High]

**Location**: `design/economy-balance-sheet.md` L63-67

§2.2 (2 房间) 声明：
- "Source Harvester ×4 | 80 | L1-2 sources, 20/tick × 1.0 效率 = 20/tick each"
- 4 × 20 = 80 ✓
- 但"总收入（优化 ×1.5 效率）"= 138，其中写 "Source 30/tick × 4 + Controller"
- 30 × 4 = 120，Controller = 12 → 132 ≠ 138

优化收入 138 无法从声明的组件推导出来。20 × 1.5 = 30/tick each → 30 × 4 = 120 + Controller 12 = 132，而非 138。差值 6 无法解释。

同样，§2.3 (5 房间): "11 Source Harvester | 330 | L1-2 sources, 20/tick × 1.5 效率 = 30/tick each"。11 × 30 = 330 ✓，Controller = 60 → 总收入 390 ✓。但 "11 Source Harvester" 暗示 5 房间有 11 个 source，即平均 2.2 source/room。这与 modes.md 中 "密度约 1 据点 / 25 房间" 的资源据点分布无直接关联，但 Source（普通资源点）的密度未在任何文档中定义。

**Impact**: 经济模型的可信度受损。无法从文档推导验证收支平衡。

**Fix**: 修正 §2.2 的数学错误，或标注计算假设（如 source count per room 的基准值）。

---

## SS2 Design Tensions (Inconsistencies, Conflicts)

### SS2-1: Heal body part cost 在两处定义不同 [Medium]

**Location**: `design/gameplay.md` L888, `specs/core/world-rules.md` L380

- gameplay.md: Heal cost = `{ Energy = 250 }`
- world-rules.md L380: Heal cost = `{ Energy = 250 }` — 一致

**但** gameplay.md L483 中 `[actions.costs]` 示例写 `body_part.Heal = { Crystal = 250, Gas = 100 }`。虽然这是多资源世界的示例，但容易混淆。建议在示例旁加注释说明这是非 Vanilla 配置。

### SS2-2: PowerSpawn 建造成本不一致 [Medium]

**Location**: `design/gameplay.md` L199, `specs/core/world-rules.md` L559, `specs/reference/api-registry.md` L811

- gameplay.md L199: PowerSpawn cost = `{ Energy = 5000 }`
- world-rules.md L559: PowerSpawn cost = `{ Energy = 1200 }`
- api-registry.md L811: `PowerSpawn=1200`

gameplay.md 给出 5000，而 canonical 源给出 1200。**4 倍偏差**。

**Impact**: 玩家建造成本计算严重错误。

**Fix**: 统一为 1200（api-registry.md 为权威），修正 gameplay.md L199。

### SS2-3: Nuker 建造成本不一致 [Medium]

**Location**: `design/gameplay.md` L215, `specs/core/world-rules.md` L575, `specs/reference/api-registry.md` L811

- gameplay.md L215: Nuker cost = `{ Energy = 100000 }`
- world-rules.md L575: Nuker cost = `{ Energy = 5000 }`
- api-registry.md L811: `Nuker=5000`

20 倍偏差。gameplay.md 的 100,000 看起来像是占位符或排版错误。

**Fix**: 统一为 5000，修正 gameplay.md L215。

### SS2-4: Depot 建造成本不一致 [Medium]

**Location**: `design/gameplay.md` L228, `specs/core/world-rules.md` L588

- gameplay.md L228: Depot cost = `{ Energy = 5000 }`
- world-rules.md L588: Depot cost = `{ Energy = 600 }`
- api-registry.md L811: `Depot=600`

8 倍偏差。

**Fix**: 统一为 600，修正 gameplay.md L228。

### SS2-5: RangedAttack range 在 Heal 校验矩阵中缺失 [Medium]

**Location**: `specs/reference/special-attack-table.md` L18

Heal 的 range 标注为 3，但 `design/gameplay.md` L887 和 `specs/core/world-rules.md` L379 都定义 Heal range = 1。canonical table 与 design/world-rules 不一致。

**Impact**: Heal 的有效治疗距离从 1 格变为 3 格是一个重大的平衡性变化——3 格远程治疗将极大改变战斗动态。

**Fix**: 确认 Heal 的 canonical range 并统一所有文档。

### SS2-6: Drone age 维修体系与寿命体系的交互未定义边界条件 [Medium]

**Location**: `design/gameplay.md` L98-102, `specs/core/resource-ledger.md` L88-91

`BASE_AGE` = 1500 tick，`MIN_LIFESPAN` = 100 tick。body part age_modifier 范围：TOUGH +100, ATTACK -80, RANGED_ATTACK -50, HEAL -30, CLAIM -50。

一个全 ATTACK body 的 drone：`age_max = max(100, 1500 + 50×(-80)) = max(100, 1500 - 4000) = max(100, -2500) = 100`。这意味着 50 个 ATTACK part 的 drone 只有 100 tick 寿命。但文档未说明 `age_max = MIN_LIFESPAN` 时 age repair 是否有效、以及维修频率限制。

Controller repair_capacity 在 RCL1 时为 5/tick，repair_aging 未在 Resource Ledger 中定义具体值——gameplay.md L102 提到"每 tick 降低的 age 量"但未给出数字。engine.md L150 定义了 `repair_per_drone` 字段但无默认值。

**Impact**: 无法评估 age repair 对 drone 寿命经济的影响。如果 repair_aging = 5/tick（参考 Depot 的 repair_aging），一个 100-lifespan ATTACK drone 需要 20 tick 纯维修才能恢复满寿命，而其寿命只有 100 tick——这意味着 20% 的时间在维修队列中。

**Fix**: 在 Resource Ledger §2.4 或 engine.md §3.4.5 中定义 Controller `repair_per_drone` 的默认值和计算方式。

### SS2-7: Allied Transfer 的 `allied_daily_cap_world_multiplier` 与 `allied_daily_cap` 公式重叠 [Medium]

**Location**: `specs/core/resource-ledger.md` L77-78, `specs/reference/api-registry.md` L813

Resource Ledger §2.1 定义 `allied_daily_cap = max(10_000, receiver_gcl × 20_000)`。同时定义 `allied_daily_cap_world_multiplier`（Standard=100=1.0×, Arena=50=0.5×, Tutorial=500=5.0×）。

api-registry.md L813 的公式为：`max(10_000, receiver_gcl × 20_000) × allied_daily_cap_world_multiplier / 100`。

但 economy-balance-sheet.md §3 模式差异表中没有列出 `allied_daily_cap_world_multiplier` 的差异行——仅列出 `allied_transfer_enabled` 的差异。这意味着玩家无法从 balance sheet 中获知 Arena 模式的联盟转移上限减半。

**Impact**: 经济参数可发现性不足。

**Fix**: 在 economy-balance-sheet.md §3 模式差异表中补充 `allied_daily_cap_world_multiplier` 行。

### SS2-8: Drone 人格系统的 `efficiency` 维度可能误导玩家 [Low]

**Location**: `design/gameplay.md` L1683

人格维度 `efficiency` 影响动画速度但"不影响实际 tick 执行速度"。但 `efficiency` 这个词在游戏经济语境中已被用于 `swarm_get_drone_efficiency`（实际采集效率）。两个人格维度与经济指标共用同一术语，会造成玩家混淆。

**Fix**: 重命名人格维度 `efficiency` 为 `diligence` 或 `vigor` 以避免与经济 efficiency 混淆。

---

## SS3 Suggestions (Improvements, Simplifications)

### SS3-1: Source 密度与经济模型的基础假设未文档化 [High]

整个 Economy Balance Sheet 的收入计算依赖"每房间多少 Source"这一基础假设，但没有任何文档定义普通 Source（非 PvE 资源据点）的密度。Balance sheet 中 2 房间 = 4 sources, 5 房间 = 11 sources, 10 房间 = 23 sources, 20 房间 = 46 sources, 50 房间 = 115 sources。这暗示约 2-2.3 sources/room，但此数字未在任何 design 或 spec 文档中声明。

**Impact**: 服主无法根据文档设置 `source_regeneration_rate` 等参数来匹配经济目标曲线。Playtest 校准时缺少 baseline。

**Fix**: 在 gameplay.md 或 world-rules.md 中定义默认 Source 密度（如 2/room），并标注 balance sheet 的 source count 假设来源。

### SS3-2: 存储税的玩家可理解性不足 [Medium]

**Location**: `specs/core/resource-ledger.md` §2.2, `specs/gameplay/PLAYTEST-GATED.md` PG-3

存储税使用连续边际税率公式（smoothstep 插值），计算复杂度高。PLAYTEST-GATED.md PG-3 已标注需要"per-hour/per-day 人类可读单位"。当前 `bp/tick` 对于 bp/tick = 2 的场景，玩家无法直观理解"2 bp/tick 的存储税意味着什么"。

**建议**: 
1. 在 Resource Ledger 或 Balance Sheet 中增加示例场景的年化/日化换算表
2. 考虑在 `swarm_get_economy` MCP 返回中增加 `estimated_daily_tax` 字段

### SS3-3: fabricate special_effect 与 convert_to_structure handler 重叠 [Medium]

**Location**: `design/gameplay.md` L1089-1095, `design/gameplay.md` L1111-1117

`[[special_effects]]` 中同时定义了 `fabricate`（handler="fabricate", target="enemy_drone"）和 `convert_to_structure`（handler="convert_to_structure", target="enemy_drone"）。两者描述几乎相同——都是"将敌方 drone 转化为己方建筑"。vanilla Fabricate action 引用的是 `fabricate` handler，但 `convert_to_structure` 似乎是冗余定义。

**Fix**: 确认 `convert_to_structure` 是否为 mod 扩展预留的别名。如果是，在文档中标注说明；如果冗余，删除。

### SS3-4: 10 分钟 Golden Path 中 PvE 击杀时机过于乐观 [Low]

**Location**: `design/gameplay.md` L24

Golden path 第 7 步"首个 PvE 挑战"预期在 T+8-10min 完成"NPU 被击杀，获得 PvE drop"。但新玩家在 Tutorial 世界需要：
1. 理解 drone body part 系统
2. 编写攻击逻辑
3. 等 NPC drone 出现在视野

modes.md 中 NPC Creep HP=50, 伤害=10/tick。新手 drone 默认 body 未定义——如果 starter bot `basic-harvester` 只有 [MOVE, WORK, CARRY]，则无法攻击。玩家需要在 10 分钟内修改 body 配置加入 ATTACK part 并编写 combat 逻辑，这对编程新手极具挑战。

**Fix**: 
1. 定义 starter bot 的默认 body part 配置
2. 将 Golden Path 中 PvE 击杀标注为"可选目标"或提供 `tower-defense` starter bot 作为替代路径

### SS3-5: 联盟转移的 100-tick alliance 最小时长与外交 timeout 交互 [Low]

**Location**: `specs/core/resource-ledger.md` L175, `design/gameplay.md` L1726

Allied transfer 要求"双方必须是同一联盟成员 ≥ 100 tick"。但外交 pending 状态 timeout 为 72h。如果玩家 A 和 B 在 tick 1000 结盟，那么 tick 1100 才能开始 transfer。但在 tick 3s 间隔下，100 tick = 300s = 5 分钟——这个窗口足够短，可能被滥用于"快速结盟→转移→断盟"循环（虽然有 24h cooldown）。

**建议**: 确认 100 tick alliance 时长是否在 Arena 模式（tick interval 300ms）下仍然合理——在 Arena 中 100 tick = 30 秒，可能过短。

### SS3-6: Forward Depot 可被"占领"的机制未定义 [Medium]

**Location**: `design/gameplay.md` L263

Depot 表格中"可占领"标注为"✅ Claim 或摧毁重建"。但 Claim 操作 (ClaimController) 的 validator 只检查 `is_controller`——Depot 不是 Controller。没有定义 drone 如何 Claim 一个 Depot 建筑。

**Impact**: "夺取敌方 Depot 获取其中资源"这一战术设计缺少实现路径。

**Fix**: 定义 Claim 对 Structure 的扩展行为，或新增 `ClaimStructure` action；或明确 Depot 的"占领"通过摧毁后重建实现（此时"获取其中资源"不成立——摧毁会掉落部分资源但不是全部）。

### SS3-7: Controller 被动收入在 Resource Ledger 中未列为 Faucet [Medium]

**Location**: `design/economy-balance-sheet.md` L37, `specs/core/resource-ledger.md` §2

Balance Sheet §2 显式假设中包含"RCL passive income: Controller 每级被动收入基础 2/tick"。但 Resource Ledger 的 Vanilla 经济分类账（gameplay.md L388-406）中 **没有列出 Controller passive income**。分类账列了 Source 再生 (Faucet)、drone 采集 (Transfer)、Spawn (Sink)、建筑建造 (Lockup)、Controller 升级 (Lockup)、Empire upkeep (Sink) 等——但缺少 "Controller passive income" 作为独立 Faucet 条目。

**Impact**: 经济模型声称"2-10 房间自维持"，但核心收入来源之一（Controller passive income）未在权威账本中定义，导致收支验证缺少权威基础。

**Fix**: 在 Resource Ledger 或 gameplay.md 的 Vanilla 经济分类账中增加 "Controller passive income" 条目，标注为 Faucet，定义计算公式和默认值。

### SS3-8: Fabricate 转化建筑类型未在 Vanilla 中定义 [Low]

**Location**: `design/gameplay.md` L750

Fabricate 将敌方 drone 转化为"己方结构（Tower/Storage/Wall）"。但 action 定义中未指定玩家选择哪种结构——是由 player 在 payload 中指定？还是由引擎自动决定？command-validation.md §3.7 只定义了 `payload: ActionPayload` 的通用 dispatch，未定义 Fabricate 的具体 payload schema。

**Fix**: 在 special-attack-table.md 或 command-validation.md §3 中定义 Fabricate 的 payload schema（如 `{ target_id, structure_type }`）。

---

## SS4 Cross-Reference Matrix

| CX# | Finding | Target Direction | Check Focus |
|-----|---------|-----------------|-------------|
| CX-1 | Fabricate 的 `500 Matter` 成本在 Vanilla 单资源世界中未定义 → 建议安全/接口方向检查 ResourceName validation 是否拒绝未定义资源类型 | Security/Interface | ResourceName validation, cost resolver 未知资源名行为 |
| CX-2 | `convert_to_structure` handler 与 `fabricate` handler 行为重叠 → 建议架构方向检查 SpecialEffectRegistry 是否存在冗余注册路径 | Architecture | handler 去重、registry 一致性 |
| CX-3 | Depot "可占领"但 Claim action 只支持 Controller → 建议接口方向检查 CommandAction 是否缺失 ClaimStructure 或结构占领路径 | Interface/API | CommandAction 完整性、Claim 适用范围 |
| CX-4 | `heal_self` special_effect 定义中 `resistance` 字段缺失但 Leech 的 `[[special_effects]]` entry 写了 `resistance = "Corrosive"`，而 gameplay.md 说 Leech 抗性是 `Kinetic`。但 `heal_self` 没有抗性 → 建议安全方向检查 Leech 的 damage 与 heal 计算是否分离了抗性检查 | Security | damage/heal dual-path 抗性处理 |
| CX-5 | Tick 输入封套 `TickInputEnvelope` 从 22 字段（api-registry.md §6）扩展到了引擎描述中的 collect_id/attempt_id/commit_id（engine.md L355）——Registry 是否已同步更新？→ 建议架构方向检查 IDL YAML 与 Registry 的字段一致性 | Architecture | IDL-Registry CI gate, TickTraceEnvelope 字段计数 |
| CX-6 | world-rules.md §9 `validate_config` 中 `damage_multiplier < 1` 检查暗示 f64——但确定性合同禁止浮点。world.toml 示例也写了 `damage_multiplier = 1.0` → 建议安全方向检查 world.toml 配置解析是否正确处理定点类型 | Security | fixed-point config parsing, determinism violation |
| CX-7 | `storage_tax_curve` 在 gameplay.md L359 使用 `curve anchors` 作为类型，但 Resource Ledger §2.1 使用具体 `quadratic_smoothstep` enum → 建议架构方向检查 world.toml 配置 schema 是否正确定义 curve 类型 | Architecture | Config schema, curve type binding |
