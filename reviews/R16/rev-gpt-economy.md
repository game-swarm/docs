# R16 Phase 1 Clean-Slate 经济评审（GPT-5.5）

## Verdict

CONDITIONAL_APPROVE

当前设计比上一轮的经济闭环明显更完整：已经把 Market 降级为 RFC，占用 Resource Ledger 作为统一资源入口，并补上全局存储税、PvE faucet cap、维护费曲线与经济可视化。但从 Economy 视角看，R16 仍存在几处会直接影响平衡可验证性的硬问题：维护费公式在不同文件之间不一致，balance sheet 的示例收支长期为负但仍声称可承受/可维持，交易/联盟/P2P 的当前范围仍有冲突。建议条件通过：不阻塞继续设计，但在进入实现冻结前必须修正这些经济权威口径与数值闭环。

## Strengths

1. Resource Ledger 方向正确
   - `specs/core/08-resource-ledger.md` 明确把 Local / Global / Allied / PvE / Recycle / Build / Spawn / Upkeep / StorageTax 都收束到统一 Resource Ledger，且要求 TickTrace 记录 `(tick, source, target, resource_type, amount, operation, fee_paid)`。
   - 这能有效避免多入口资源逃逸，是经济系统可审计、可回放、可调参的必要基础。

2. Market 从当前范围中移除是正确决策
   - `design/gameplay.md` 明确 Market / trading 为 RFC，占位但不进入当前设计范围。
   - 在基础 faucet/sink/transfer 未稳定前不引入订单簿和撮合引擎，可以避免过早把价格发现问题叠加到资源闭环上。

3. Anti-snowball 机制组合完整
   - 设计包含累进全局存储税、全局↔本地转换损耗与延迟、empire upkeep、Controller age 维修硬上限、safe_mode/soft_launch、room drone cap。
   - 这些机制分别覆盖囤积、瞬移补给、横向扩张、永久单位、新人过渡与局部兵力堆叠，方向上是健康的。

4. PvE faucet 有明确预算意识
   - World PvE 掉落设置 `max_pve_output_per_tick`，Resource Ledger 进一步定义 Global / Zone / Player / Event 四维 PvE budget。
   - 这比简单“NPC 掉落资源”安全得多，能防止刷怪成为压倒主经济的主 faucet。

5. 经济反馈面向人类与 AI 都有出口
   - `swarm_get_economy`、`swarm_get_economy_trend`、经济 dashboard、负流入告警等设计能让玩家看到收入、支出、税率与预测。
   - 对编程 RTS 尤其重要：经济不可见会让 AI/human 都难以调参和学习。

## Concerns

### E1 — High — 维护费公式存在权威源冲突，导致平衡不可验证

`design/economy-balance-sheet.md` 使用公式：

```text
maintenance = base_upkeep × rooms × (1 + rooms / room_soft_cap)
room_soft_cap = 10
base_upkeep = 50
```

并给出 1/5/20/50 房间维护费：55 / 375 / 3,000 / 15,000 per tick。

但 `design/gameplay.md` 的 empire-upkeep 模组示例与参数口径是：

```text
total_cost = drones * drone_cost + rooms * (room_base + rooms * room_superlinear / FIXED_SCALE)
default: drone_cost=2, room_base=10, room_superlinear=1 fixed<u32,4>
```

且同一文件又给出“小帝国 40/tick、中帝国 275/tick、大帝国 2100/tick、巨帝国 3150/tick”的示例，并说明默认超线性项极小，强反雪球需要服主把 `room_superlinear` 调到 100-10000。

这三组口径不能同时为权威：
- Balance Sheet 的 50 房 = 15,000/tick；
- Gameplay 示例的 50 房 = 3,150/tick；
- Gameplay 默认参数本身又接近线性，50 房超线性贡献约 0.25/tick。

经济后果：维护费是核心 anti-snowball sink。如果公式、默认参数、示例目标值不统一，任何“可承受 / 硬上限 / 需要高效经济”的结论都无法验证。

建议：指定唯一权威公式与参数源。若 R16 目标采用 Balance Sheet，则 `empire-upkeep` 模组合同、world.toml 示例、API economy 输出、Resource Ledger `UpkeepDeduction` 都必须引用同一公式；若采用 gameplay 模组公式，则 balance sheet 应重算并删掉冲突表述。

### E2 — High — Balance Sheet 示例显示所有规模长期亏损，却声称“新手轻松/可承受/顶尖可维持”

`design/economy-balance-sheet.md` 的收支表：
- 1 房：收入 25/tick，支出 55/tick，净 -30/tick；
- 5 房：收入 140/tick，支出 390/tick，净 -250/tick；
- 20 房：收入 1,220/tick，支出 3,160/tick，净 -1,940/tick；
- 50 房：收入 3,975/tick，支出 16,600/tick，净 -12,625/tick。

文档解释为“1 房靠初始资源包支撑”“5 房优化后可缩小缺口”“20 房需要高效经济”“50 房顶尖玩家才能维持”。但当前表格没有给出任何一个正流入或接近 break-even 的可行配置。

经济后果：这不是 anti-snowball，而可能是 universal negative economy。若所有阶段在普通操作下都净亏损，玩家不是被鼓励优化，而是被迫依赖一次性初始资源、PvE farm 或联盟输血；这会把经济中心从“可编程效率”转移到“补贴/外部 faucet”。

建议：Balance Sheet 至少给出三类可验证场景：
- 新手安全线：1 房 starter bot 在 safe_mode/soft_launch 内可维持非负或明确可持续 N tick；
- 中期优化线：5-20 房在合理 RCL/source 等级与 drone 数下可接近 break-even；
- 扩张上限线：50 房只有极高效率才接近 break-even，但不是数学上必然崩溃。

### E3 — High — 交易/转移范围仍互相冲突，可能留下绕过经济税与物流成本的通道

当前文档同时存在以下说法：
- `design/gameplay.md`：Market/trading 为 RFC，未来方向为 Transfer + Alliance 资源池上层抽象；
- `specs/core/08-resource-ledger.md`：AlliedTransfer 当前进入 Resource Ledger，带 2% fee、200 tick delay、500 tick cooldown、daily cap；
- `design/gameplay.md` 外交表：allied 资源 transfer “可直接 player↔player transfer，免 convert 延迟”；
- `design/gameplay.md` Drone 消息机制：点对点资源交换协议可在 WASM 层实现，引擎不提供担保；
- `specs/core/08-resource-ledger.md` Future RFC 表：Drone P2P Offer 为 Future RFC，替代方案是 Allied Transfer。

这里至少有两处冲突：
1. AlliedTransfer 是否有延迟？Ledger 是 200 tick，外交表写免 convert 延迟，容易被理解为即时。
2. Drone P2P offer 是否当前可用？Gameplay 说可通过 messages 实现资源交换协议，Ledger 却把 Drone P2P Offer 标为 Future RFC。

经济后果：若 allied 或 P2P 能绕过 global/local transfer loss、storage tax、new player lock 或 daily cap，就会重新打开“联盟银行/小号输血/无税物流”的滚雪球漏洞。

建议：冻结当前范围为“只有 Resource Ledger 的 Transfer/AlliedTransfer 可改变资源归属，messages 只能承载非执行性 payload，不得导致资源 escrow/settlement”。外交表改为“免 global↔local convert，但仍走 AlliedTransfer fee/delay/cap”。

### E4 — Medium — PvE faucet budget 有框架，但缺少与 Source 再生、事件爆发、掉落表的统一预算仲裁

World PvE 文档定义：
- NPC 掉落 Energy / Crystal / Blueprint / Wreckage；
- 资源据点如 Energy Spring 再生 100/tick、Rich Vein 再生 50/tick；
- 世界事件 Resource Boom 让全局 Energy/Crystal 再生 ×2；
- `max_pve_output_per_tick` 默认 ≤ 世界再生总量 ×30%。

Resource Ledger 又定义 PvE budget 四维 cap：Global / Zone / Player / Event。

问题是：哪些产出算 PvE faucet？普通 Source regeneration、据点再生、Resource Boom 倍率、NPC drop、Wreckage 回收、Blueprint 是否都进入同一个 budget？如果 Resource Boom 把“世界再生总量”翻倍，PvE cap 是否也随之扩大？Blueprint 是非货币资源但可解锁配方，是否需要独立稀缺预算？

经济后果：PvE 不只产出 Energy，还可能产出 Crystal、Blueprint、Wreckage 与占领型持续产出点。若只按“资源单位”限制，会低估稀有解锁、战略据点和事件倍率带来的长期通胀。

建议：补一张 PvE output classification 表，将每种 PvE 产出标为 Faucet / Transfer / Unlock / Non-fungible Unlock，并说明是否计入 Global/Zone/Player/Event budget，以及 Resource Boom 是否放大 budget 或只放大 source regeneration。

### E5 — Medium — 全局存储税与 Resource Ledger 税率口径不一致，可能造成调参误读

`design/gameplay.md` 使用累进 tier：
- 0-30%: 0 bp；
- 30-60%: 1 bp；
- 60-85%: 5 bp；
- 85-100%: 20 bp。

`specs/core/08-resource-ledger.md` 的费率模型写：
- `storage_tax_rate = 10 bp/tick`。

`design/economy-balance-sheet.md` 的模式表又写：
- Tutorial 0 bp；Vanilla 5 bp；Standard 10 bp。

这里不清楚 Standard 默认到底是：固定 10 bp/tick、累进 tier、还是模式表里的基础税率叠加 tier。

经济后果：存储税是反囤积核心 sink。固定税与边际累进税会产生完全不同的玩家行为：固定税惩罚所有存量，累进税鼓励保持在阈值以下。若文档不统一，玩家和服主无法预测囤积成本。

建议：将 `storage_tax_rate` 改名为 `storage_tax_base_bps` 或删除，统一使用 `global_storage_tax_tiers`。Balance Sheet 的 storage tax 数值应标注存储量、利用率、tier 和计算公式。

### E6 — Medium — Local/Global 存储转换命令缺少位置与物流实体约束，No Teleport 仍不完全成立

设计目标反复强调全局↔本地转换有时间、损耗、运输中状态，甚至可被敌方拦截。但 IDL 中：

```text
TransferToGlobal: resource, amount
TransferFromGlobal: resource, amount
```

参数没有 source structure、target structure、room_id、route、carrier/transport entity 或 terminal/depot 绑定。Ledger 也只有 GlobalDeposit / GlobalWithdraw，没有明确“运输中实体”的归属、位置、可见性、拦截规则。

经济后果：如果转换只是 player-level 延迟队列，虽然不是即时补给，但仍可能是“跨地图延迟传送”，无法体现物流线可打击、区域封锁、前线补给脆弱性。大型帝国的地理成本会被低估。

建议：若 No Teleport 是设计目标，TransferFromGlobal 至少需要 `target_structure_id` 或 `target_room_id`，并限制为 Terminal/Storage/Spawn/Depot 等合法 sink；运输中状态应有 ledger record + position/route/arrival tick，或明确承认当前版本只是“延迟抽象物流”，不可声称可被巡逻 drone 拦截。

### E7 — Low — Recycle 退还规则存在文档口径差异

`design/gameplay.md` 写标准世界回收退还 50%，Tutorial 前 500 tick 100%。`specs/gameplay/08-api-idl.md` 写 `refund = registry.body_cost(body) * 0.5`。`specs/core/08-resource-ledger.md` 写：

```text
recycle_refund = body_cost * remaining_lifespan * 5000 / total_lifespan / 10000
recycle_refund_min = 10%
```

也就是说 Ledger 实际是随剩余寿命衰减的 50% 上限、10% 下限，而非固定 50%。

经济后果：固定 50% 与寿命比例退还对 suicide-recycle、快速换装、战后回收的策略完全不同。固定 50% 更容易被用作高频重构 body 的低成本期权；寿命比例退还则更像折旧模型。

建议：统一为 Ledger 的折旧模型，并在 gameplay/IDL 中说明 Tutorial 100% 是新手世界 override，而非标准规则。

## Economy Balance Issues

1. Small empire pressure is currently too high in the dedicated balance sheet
   - 1 房净 -30/tick 与“新手轻松”矛盾。
   - 若 starter bot 必须靠初始包支撑，应给出初始资源量、预期存活 tick、RCL2/3 何时 break-even。

2. Medium empire lacks a demonstrated positive optimization path
   - 5 房净 -250/tick，文档只说“优化 Harvester 代码效率”但没有给出优化后收入模型。
   - 对编程游戏来说，“优化可带来多少收益”必须显式量化，否则无法区分设计压力与数值错误。

3. Large empire curve may be overcorrected
   - 20 房净 -1,940/tick、50 房净 -12,625/tick 会让扩张变成纯负债，除非存在未计入的高阶 source/RCL/PvE/联盟收入。
   - 如果依赖联盟交易维持大帝国，又会削弱 anti-snowball 的个人规模曲线。

4. Storage tax lacks a concrete worked example
   - 目前只有税率/阶梯，没有给出“存储量 X、容量 Y、税额 Z”的样例。
   - 建议在 1/5/20/50 房表里补充 global storage utilization，否则 storage tax 数字不可复算。

5. PvE cap and Source economy need common unit
   - Source regeneration 表示为每 tick 单位，NPC 掉落是范围值，Blueprint 是非同质解锁，Wreckage 是 body cost 百分比。
   - 需要用 ResourceAmount、UnlockValue 或 rarity budget 统一衡量，否则 PvE 经济难以调参。

## Resource Loop Gaps

1. Faucet → Transfer → Sink 主链基本存在，但数值未闭环
   - Faucet: Source regeneration、PvE drop、资源据点、事件；
   - Transfer: harvest、local/global/allied transfer；
   - Sink: upkeep、storage tax、spawn/build/code update、conversion loss；
   - Gap: balance sheet 没证明任何主要阶段可持续。

2. 资源创建权威仍需收束到 Resource Ledger
   - Rhai actions 包含 `award_resource`，PvE 系统/NPC/事件也会产出资源。
   - 必须明确所有 `award_resource` 都经过 PvE budget 或对应 faucet budget，而不能让模组绕过 ledger cap。

3. 交易与消息边界未完全闭合
   - P2P message offer 当前文本像是可实现资源交换协议，但 Ledger 把 Drone P2P Offer 标为 Future RFC。
   - 若允许 WASM 层协议改变资源归属，必须走 Resource Ledger；若不允许，文档需明确 messages 只能沟通，不能结算。

4. 全局↔本地转换的“运输中”缺少实体模型
   - 文档声称可被拦截，但 IDL/ledger 只表达 player-level transfer。
   - 这会影响大帝国补给线、前线 Depot、No Teleport 的真实性。

5. 多资源系统缺少默认跨资源价值锚
   - 默认 Vanilla 只有 Energy，扩展世界可有 Crystal/Gas/Matter。
   - 当前没有说明维护费、storage tax、PvE cap 在多资源世界中按每种资源独立计算，还是折算为 base_value。若服主启用多资源，通胀监控会缺少共同尺度。

## CrossCheck — 需要跨方向检查

1. Architect CrossCheck: API Registry vs IDL 的 RejectionReason/Tool 名称冲突
   - API Registry 声称 RejectionReason 权威共 35 个；IDL 内仍列出大量额外/旧变体，如 `NotMovable`、`Fatigued`、`MissingBodyPart`、`TileBlocked`、`CarryFull` 等。
   - Economy 影响：资源拒绝码与 refund policy 绑定，错误码不统一会影响扣费/退款归因。

2. Architect CrossCheck: Resource Ledger 执行顺序与 ECS 系统顺序
   - Ledger 顺序把 `UpkeepDeduction` 放在最前，`BuildCost`/`SpawnCost` 靠后。
   - 需要确认这与 spawn/build/combat/death_cleanup 的 ECS tick 顺序是否一致，尤其是死亡、回收、建造完成同 tick 的资源归属。

3. Security CrossCheck: AlliedTransfer / new player lock / same-origin quota
   - 需要验证 allied transfer 的 100 tick 入盟要求、500 tick 新玩家锁、daily cap、same-origin account group quota 能否共同防止小号输血。

4. Gameplay/UX CrossCheck: 经济反馈是否展示“为什么被扣费”
   - `swarm_get_economy` 应能展开 UpkeepDeduction、StorageTax、GlobalTransferFee、PvEBudgetExhausted 等原因。
   - 否则玩家只看到资源下降，不知道是维护费、税、物流损耗还是模组扣费。

5. Design Authority CrossCheck: Market RFC 引用清理
   - `api-registry.md` 仍列出 `swarm_list_market_orders`，`06-feedback-loop.md` 仍提到 Market Contracts。
   - 如果 Market 当前不在范围内，这些 API/玩法入口应标记 RFC 或从当前 MCP capability 中移除，避免实现侧误开资源交易面。
