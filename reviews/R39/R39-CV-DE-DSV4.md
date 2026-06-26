# R39-CV-DE-DSV4 — Design & Economy Review

## 评审范围

- `design/gameplay.md`
- `design/economy-balance-sheet.md`
- `design/modes.md`
- `specs/core/08-resource-ledger.md`

重点检查：Vanilla/Standard 经济闭环、Resource Ledger 权威性、World/Arena/PvE 模式边界、anti-snowball 与新手保护是否足以冻结为实现合同。

## 总体结论

当前 DSv4 的设计与经济方向整体成立：资源流通过 Resource Ledger 单一入口收敛，维护费、存储税、全局/本地物流、PvE budget、新玩家 transfer lock、World vs Arena 玩法分离等核心设计已经比前几轮更完整。`economy-balance-sheet.md` 也明确把 2–10 房间自维持、20 房后递减、50 房软上限定义为 canonical target curve，而不是把当前数值误当成不可调整真值。

但本轮仍不建议直接冻结 Design & Economy 合同。主要问题不是玩法方向，而是若干跨文档残留冲突会让实现者在 repair/age 经济、存储税计算、PvE/Merchant 范围、Arena 评分语义上落地出不同版本。建议修复下列 Blocker/High 后再进入实现冻结。

## 阻塞问题（Blocker）

### B1. Controller repair/age 维护模型存在三套互斥权威，无法实现一致经济

**位置**：

- `design/gameplay.md:102`
- `design/economy-balance-sheet.md:220`
- `specs/core/08-resource-ledger.md:150`
- `specs/core/08-resource-ledger.md:155`
- `specs/core/08-resource-ledger.md:156`

**问题**：

四份相关文档对 Controller/Depot 降低 age 的经济约束给出了互相冲突的模型：

1. `gameplay.md` 明确说维修能力只受 `repair_range`、per-Controller `repair_capacity`、drone 物理分布限制，且“不存在额外的全局 cap”。
2. `economy-balance-sheet.md` 模式表仍保留 `repair_cap = 5000 bp / 3500 bp` 与 `repair_distance_decay`。
3. `resource-ledger.md` §2.4 定义 `repair_cost = body_cost × (1 - repair_cap / 10000) × ...`，即把 repair 建模为付费/折扣公式。
4. `gameplay.md` 同一段又说 Controller 维修免费、Depot 消耗本地存储资源。

这不是简单数值差异，而是三种互斥设计：

- **免费但受物理吞吐限制**；
- **有全局/比例 cap 的免费 age 回退**；
- **按 body_cost 收费且有距离衰减的 repair cost**。

**影响**：高到阻塞。该模型影响 drone 寿命、远征成本、Depot 价值、前线补给线、anti-snowball、以及经济报表中的维护压力。如果实现者按 Resource Ledger 写付费 repair，而 gameplay 按免费吞吐写玩法，玩家策略和账本审计会完全不同。

**建议**：

以最近的 D7 方向收敛为单一模型，并同步四处文档：

1. Controller age repair：免费，但仅限 `repair_range` + `repair_capacity` + 实体排队/位置约束。
2. Depot age repair：消耗 Depot 本地资源，受 `repair_range=1`、`repair_capacity`、`maintenance`/库存限制。
3. 删除 `repair_cap` / `repair_cost` / `distance_decay_bp` 作为 Resource Ledger 权威公式；若保留距离衰减，只能作为 Depot 或可选 mod 参数，不能与“无全局 cap”并存。
4. Resource Ledger 只记录 Depot 消耗类账本操作；Controller 免费 age repair 不应进入 Resource Ledger 作为资源流出。

## 严重问题（High）

### H1. StorageTax tiered 公式以百分比作为 taxable，会导致数量级错误

**位置**：

- `specs/core/08-resource-ledger.md:102`
- `specs/core/08-resource-ledger.md:105`
- `specs/core/08-resource-ledger.md:106`
- `specs/core/08-resource-ledger.md:112`
- `specs/core/08-resource-ledger.md:114`
- `design/economy-balance-sheet.md:97`
- `design/economy-balance-sheet.md:120`
- `design/economy-balance-sheet.md:143`

**问题**：

Resource Ledger 的公式写作：

```text
storage_tax(tick) = Σ over each tier i where storage_pct > tier_threshold[i]:
    taxable_in_tier = min(storage_pct - tier_threshold[i], tier_width[i])
    tax = taxable_in_tier × tier_rate[i] / 10000
```

这里 `taxable_in_tier` 是容量百分比差值（例如 15），但示例又把 75% 容量、1,000,000 capacity 下 Tier1 计算成 `300,000 × 1 bp = 30`，也就是按“资源单位”计算。公式缺少 `capacity / 100` 的换算，导致实现者若照公式写，会得到接近 0 的税；若照示例写，则得到报表中的 15/45/120/600 一类数值。

`economy-balance-sheet.md` 进一步把 5 房间 “40% utilization，Tier1 @ 1bp” 写成存储税 15/tick，但若 capacity 为 1,000,000 且存储 40%，按 Resource Ledger 示例应为 `(400k-300k)*1bp = 10/tick`。这说明报表中的存储量假设没有显式写出，无法从权威公式重算。

**影响**：高。存储税是 anti-hoarding 的核心经济 sink。公式单位不清会直接导致实现、IDL 生成、报表和模拟器四套结果不一致。

**建议**：

将 Resource Ledger §2.2 改为单位明确的公式：

```text
storage_units = stored_total
capacity_units = storage_capacity
tier_start_units = capacity_units × threshold_pct[i] / 100
tier_end_units = capacity_units × threshold_pct[i+1] / 100
taxable_units = max(0, min(storage_units, tier_end_units) - tier_start_units)
tax += taxable_units × tier_rate_bp[i] / 10000
```

然后在 Balance Sheet 每个存储税数值旁补充 `storage_capacity` 与 `stored_total/utilization` 假设，或降级为“示意值，不可重算”。

### H2. Merchant NPC 在模式设计中作为当前 World PvE 内容出现，但 Resource Ledger 明确 Out-of-Scope

**位置**：

- `design/modes.md:36`
- `design/modes.md:58`
- `specs/core/08-resource-ledger.md:299`
- `specs/core/08-resource-ledger.md:305`
- `specs/core/08-resource-ledger.md:306`

**问题**：

`modes.md` 的 World PvE 生态层把 Merchant 列为 NPC 类型，并定义“游商到来”世界事件；Merchant 到站后“交互触发交易事件”。但 `resource-ledger.md` §7 明确 `Merchant NPC` 是远期入口、Out-of-Scope，当前 Resource Ledger 不接入。

这会产生范围冲突：如果 Merchant 是当前 World PvE 常驻层，那么它必然涉及交易、资源流、价格/费率、审计与反滥用；如果它是 Out-of-Scope，则不应在当前模式文档中以可交互经济实体出现。

**影响**：高。Merchant 是资源入口/转移入口，若没有 Ledger 结算规则，会绕开“单一资源入口”原则；若实现者跳过 Merchant，又会与 World PvE 内容表冲突。

**建议**：

二选一：

1. 推荐：把 `modes.md` 中 Merchant 行和 Merchant Arrival 事件标记为 `RFC-MERCHANT / Out-of-Scope`，当前仅保留 Creep/Guardian/Swarmling 与资源据点。
2. 若保留当前实现范围，则必须在 Resource Ledger 增加 `MerchantTrade` 操作、费率、限额、执行顺序、TickTrace 归因和 new_player_transfer_lock 交互规则。

### H3. Arena PvE 评分公式使用浮点/小数语义，与全局定点合同不一致

**位置**：

- `design/modes.md:187`
- `design/modes.md:193`
- `design/modes.md:194`
- `design/gameplay.md:1988`
- `specs/core/08-resource-ledger.md:15`

**问题**：

`modes.md` 的 PvE Challenge 评分公式使用：

```text
efficiency = min(1.0, par_time / actual_time)
difficulty = 1.0 + 0.5 × (difficulty - 1)
```

而 `gameplay.md` 的 Determinism Contract 与 Resource Ledger 原则都要求游戏引擎数值使用整数/定点数，禁止浮点。评分如果影响排行榜、match_result 或可复现 replay，它也属于需要 deterministic 的游戏结果。

**影响**：中高。若前端展示可用浮点，问题较小；但文档当前把它写为 Arena PvE 评分公式，容易被实现为核心结算逻辑，从而引入跨语言/平台差异。

**建议**：

改成定点整数公式，例如：

```text
efficiency_bps = min(10000, par_time * 10000 / actual_time)
difficulty_bps = 10000 + 5000 * (difficulty - 1)
score = (base_score * efficiency_bps / 10000) * difficulty_bps / 10000 + bonus
```

并声明排行榜存储整数分数，浮点仅可用于 UI 展示。

## 中等问题（Medium）

### M1. Balance Sheet 的“权威公式见 Resource Ledger”与自身数值不可完全重算

**位置**：

- `design/economy-balance-sheet.md:35`
- `design/economy-balance-sheet.md:37`
- `design/economy-balance-sheet.md:39`
- `design/economy-balance-sheet.md:89`
- `design/economy-balance-sheet.md:111`
- `design/economy-balance-sheet.md:180`

**问题**：

Balance Sheet 已正确声明数值是 canonical target curve 的初始参数化，但多个收入项仍依赖未权威化假设：每房 source 数、source L1/L2/L3 产出、Controller passive income、代码效率 multiplier、PvE drop share。文档说明这些是显式假设，但 “所有费率、公式以 Resource Ledger 为唯一权威源” 的措辞会让人误以为这些收入曲线也已可实现。

**建议**：

将 Balance Sheet 表格拆成两层：

- Resource Ledger 已权威化：upkeep、storage tax、transfer fee、free upkeep、PvE budget cap。
- Playtest/target assumptions：source density、RCL passive income、efficiency multiplier、PvE realized drop。

并在 §2 汇总表加一列“权威/假设来源”，避免实现团队把示意性经济目标误写成 engine hard constants。

### M2. World 10 分钟 Golden Path 与 Standard 经济表之间缺少 Tutorial→Standard 资产隔离说明

**位置**：

- `design/gameplay.md:5`
- `design/gameplay.md:18`
- `design/gameplay.md:26`
- `design/economy-balance-sheet.md:216`
- `design/modes.md:204`

**问题**：

Golden Path 明确 Tutorial 世界 10 分钟内完成首次 PvE，并默认关闭 transfer lock、部署费、fog；Balance Sheet 又定义 Tutorial starting resources 10,000、Standard 5,000、Novice/Standard transfer lock 500 tick。当前文档没有在这四份评审范围内明确说明 Tutorial 产出的资源/掉落是否能迁移到 Standard/World。

如果 Tutorial 资源可迁移，关闭 transfer lock 与高 starting resources 会成为刷号 faucet；如果不可迁移，应明确 Tutorial 是隔离训练世界，只有成就/SDK 学习可迁移，不迁移资源。

**建议**：

在 `gameplay.md` Golden Path 或 `modes.md` 增加一句：Tutorial 世界资产与 Standard/World 经济隔离；Tutorial PvE drop、starting_resources、recycle refund 不可转入持久 World，只用于教学/本世界内体验。

### M3. PvE budget 与 World 事件奖励边界仍偏概念化

**位置**：

- `design/modes.md:55`
- `design/modes.md:64`
- `design/modes.md:72`
- `specs/core/08-resource-ledger.md:181`
- `specs/core/08-resource-ledger.md:187`
- `specs/core/08-resource-ledger.md:190`

**问题**：

Resource Ledger 定义 PvE 资源产出受 Global/Zone/Player/Event 四维预算控制，这是正确方向。但 `modes.md` 的事件表仍写 Resource Boom 使全局 Energy/Crystal 再生 ×2、Swarmling 固定掉落 5–10/只、据点固定产出等，只有 NPC 掉落段引用 PvEAward。

这些可以作为设计内容存在，但需要明确哪些是：

- 环境 Source 再生倍率，属于 `source_regeneration_rate` 或事件 mod，不计入玩家 PvEAward；
- NPC 击杀奖励，必须进入 PvEAward；
- 据点占领后的持续产出，属于 Source/structure faucet，是否计入 Zone/Global cap。

**建议**：

在 `modes.md` §9.0 增加“所有直接进入玩家账户/库存的 NPC 与事件奖励必须通过 Resource Ledger `PvEAward`；环境 source 再生倍率不直接发放给玩家，但仍计入世界再生总量基线”的边界说明。

## 轻微问题（Low）

### L1. `gameplay.md` 存在 Markdown 强调未闭合

**位置**：

- `design/gameplay.md:102`

**问题**：

`**Healer body part 只能恢复 HP，不能降低 age。` 缺少结束 `**`。

**建议**：补齐 Markdown 强调，避免渲染污染后续段落。

### L2. Economy Balance Sheet 引用 Resource Ledger §6 的位置已过期

**位置**：

- `design/economy-balance-sheet.md:245`

**问题**：

表格写 “回收 (RecycleRefund) | Resource Ledger §6”，但当前 Resource Ledger 的回收权威公式在 §2.5，§6 是 ResourceAmount / ResourceRate 定点建模。

**建议**：改为 `Resource Ledger §2.5`。

## 正向评价

- Resource Ledger 单一入口方向正确，覆盖 Local/Global/Allied/PvE/Recycle/Build/Spawn/Upkeep/StorageTax，能有效防止资源逃逸。
- new_player_transfer_lock 已定义为双向锁，并覆盖未来 ContractSettlement，反刷号语义较清晰。
- Balance Sheet 把 2–10 房自维持、20/50 房递减作为目标曲线，而非绝对数值，符合设计阶段与 playtest 校准边界。
- World 与 Arena 的玩法目标分离清楚：World 接受不公平持久沙盒，Arena 追求对称、公平、短局回放。
- PvE budget 四维上限是必要设计，能避免刷怪经济压倒 PvP/物流战略。

## 建议的冻结前修复顺序

1. 先统一 Controller/Depot age repair 经济模型，删除 `repair_cap`/`repair_cost` 残留或明确改为可选 mod。
2. 修正 StorageTax 单位公式，并让 Balance Sheet 税额可重算或明确降级为示意。
3. 清理 Merchant 当前范围：标记为 RFC，或补齐 Ledger 操作。
4. 将 Arena PvE score 改为整数/定点公式。
5. 补充 Tutorial 资产隔离与 PvE budget 边界说明。

## 评审结论

**结论：请求修改（Request Changes）。**

DSv4 的 Design & Economy 大方向可继续推进，但当前文本仍包含会直接影响实现合同的经济模型冲突。尤其是 repair/age 维护与 StorageTax 公式必须在 R39 后续修订中闭合，否则实现团队无法从文档中得到单一、可测试、可审计的经济规则。