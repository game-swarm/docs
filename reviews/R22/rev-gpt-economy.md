# R22 经济评审 (GPT-5.5)

Verdict: REQUEST_MAJOR_CHANGES

本轮从经济系统视角不建议直接通过。当前设计已经有明确的资源账本、物流层、累进税、PvE faucet 上限和维护费方向，基础经济思路是对的；但“权威源”之间仍存在多套互相冲突的经济公式与默认值，足以导致实现、文档、SDK/API 展示和玩家策略预期分叉。主要问题不是缺一个机制，而是经济参数的单事实源尚未真正闭合。

## Strengths

1. 资源流动开始形成完整账本闭环
   - Resource Ledger 将 LocalTransfer、GlobalDeposit/Withdraw、AlliedTransfer、PvEAward、RecycleRefund、BuildCost、SpawnCost、UpkeepDeduction、StorageTax 收束到统一入口，并要求 TickTrace 记录每笔资源变动与 balance delta。
   - 这解决了 MMO RTS 常见的“某个奖励/转账路径绕过税费或审计”的通胀漏洞。

2. 物流模型有真实经济摩擦
   - 本地存储、全局存储、全局↔本地转换费、转换延迟、No Teleport、Depot 补给线共同构成了空间经济。
   - 该设计避免了全局仓库成为“即时万能背包”，比纯账户余额模型更适合持久世界。

3. Anti-snowball 方向正确
   - 累进存储税、帝国维护费、Controller age 维修上限、PvE 产出预算、新玩家转账锁、soft_launch 保护共同覆盖了囤积、扩张、刷号、PvE 刷怪等主要滚雪球路径。
   - World 模式承认不完全公平、Arena 模式追求对称公平，两种经济目标分离清楚。

4. PvE faucet 有预算意识
   - World PvE 明确提出 NPC 掉落不超过世界资源池注入上限，Resource Ledger 又进一步给出 Global/Zone/Player/Event 四维预算。
   - 这比“怪物固定掉落”安全，能防止刷怪经济压倒资源点与玩家间战略。

5. 经济反馈面向人类和 AI 玩家
   - `swarm_get_economy`、`swarm_get_drone_efficiency`、`swarm_get_economy_trend`、经济仪表板、税率预警、净流入告警等机制能让玩家看到收入/支出/效率问题。
   - 对编程 RTS 尤其重要，因为经济问题往往来自代码效率而非手动操作。

## Concerns

### E1. Critical — 经济权威源仍然冲突，Resource Ledger 与 API Registry 不一致

Resource Ledger 声称 §2 是所有费率、公式、参数的唯一权威源，但 `specs/reference/api-registry.md` 的 Economy Operations 仍定义了另一套经济公式：

- Resource Ledger §6 Empire Upkeep:
  - `upkeep = base_upkeep × rooms × (1 + rooms / room_soft_cap)`
  - Standard: base_upkeep=50, room_soft_cap=10
  - Vanilla: base_upkeep=30, room_soft_cap=15
  - Tutorial: base_upkeep=10, room_soft_cap=20
  - deficit 连续 3 tick 效率 −50%，连续 10 tick age 加速 ×10

- API Registry §10.2 UpkeepDeduction:
  - “Per-structure cost: 1 unit/tick. Controller upkeep: level² × 10. Drones have no passive upkeep.”

这不是表述差异，而是完全不同的维护费模型。一个按房间规模超线性扣费，另一个按建筑/Controller 扣费且无 drone 被动维护。实现团队若按 API Registry 生成代码，经济平衡将与设计报表完全不同。

影响：
- Empire upkeep 的 anti-snowball 曲线无法保证。
- 经济仪表板和 `swarm_get_economy` 返回的 maintenance 可能与引擎扣费不同。
- 玩家策略、文档示例、CI smoke test 都会围绕错误曲线优化。

建议：
- 立即将 API Registry 的 Economy Operations 改为引用 Resource Ledger 的公式，不再内联另一套 UpkeepDeduction。
- 若 API Registry 是 IDL 自动生成，则必须修正 economy.idl.yaml 中的 UpkeepDeduction 定义；只改 Markdown 不够。
- CI 应加入“Resource Ledger 参数表 ↔ API Registry economy section”一致性检查。

### E2. Critical — 存储税存在两套阈值模型：容量百分比 vs 绝对数量

Resource Ledger §2.1/§2.2 与 gameplay/economy-balance-sheet 使用容量百分比 tier：

- 0–30%: 0 bp
- 30–60%: 1 bp
- 60–85%: 5 bp
- 85–100%: 20 bp

但 API Registry §5.7 Economy 限制写的是绝对阈值：

- Tier 1 threshold: 10,000 units
- Tier 2 threshold: 100,000 units
- Tier 3 threshold: 1,000,000 units

API Registry §10.2 StorageTax 又写：

- 0 bp (<10K), 1 bp (10K–100K), 5 bp (100K–1M), 20 bp (1M+)

这与 1,000,000 capacity 下的百分比 tier 明显冲突：按百分比，30% 才开始征税，即 300,000；按 API Registry，10,000 就开始征税。两者会让早期玩家税负相差 30 倍阈值。

影响：
- 新手/小帝国是否免税完全不确定。
- 储蓄策略、全局仓库容量升级价值、市场流动性都会被错误税制扭曲。
- `economy-balance-sheet.md` 中 5/20/50 房间的税额无法作为验证基准。

建议：
- 统一为“容量百分比 tier”或“绝对阈值 tier”之一。就当前设计意图看，建议保留容量百分比 tier，因为它能随 world.toml 的 global_storage_capacity 调整而自动缩放。
- API Registry §5.7 的 economy limits 若必须保留绝对数，应标明它们是默认 capacity=1,000,000 时的派生值，并修正为 300,000 / 600,000 / 850,000，而不是 10,000 / 100,000 / 1,000,000。

### E3. High — 维护费曲线报表与 gameplay 旧示例互相矛盾，数值信号混乱

`design/economy-balance-sheet.md` 采用 Resource Ledger 的公式并给出 Standard：

- 1 房: 55/tick
- 5 房: 375/tick
- 20 房: 3,000/tick
- 50 房: 15,000/tick

但 `design/gameplay.md` 后段仍保留旧示例：

- 小帝国（1 房, 20 drone）维护费 ≈ 40/tick
- 中帝国（5 房, 100 drone）≈ 275/tick
- 大帝国（20 房, 500 drone）≈ 2100/tick
- 巨帝国（50 房, 500 drone）≈ 3150/tick

且同一段又解释 `drone_cost=2, room_base=10, room_superlinear=1` 默认近乎线性，50 房仅约 3150/tick；这与 Resource Ledger 当前 Standard 50 房 15,000/tick 不兼容。

影响：
- 文档不能给服主和玩家可靠预期。
- “50 房硬上限逼近”在 3,150/tick 与 15,000/tick 下是两种完全不同游戏。
- 对维护费是否“新手友好”与“强 anti-snowball”的定位不清。

建议：
- 删除或明确标注 gameplay.md 中旧的 `drone_cost/room_base/room_superlinear` 模组示例为历史/替代公式，不得作为 Vanilla 默认。
- Vanilla/Novice/Standard/Tutorial 的维护费曲线必须只有 Resource Ledger 一套参数。
- 如果保留可替换 upkeep mod，需区分“Vanilla 默认公式”和“第三方/服主自定义公式”，并说明 economy dashboard 如何显示当前公式。

### E4. High — Standard 收支平衡表显示 1/5/20/50 房全部长期净亏损，早中期可持续性没有闭合

`economy-balance-sheet.md` 的 Standard 场景：

- 1 房净流量 -30/tick
- 5 房净流量 -250/tick
- 20 房净流量 -1,940/tick
- 50 房净流量 -12,625/tick

文档说明 1 房依赖初始资源包、5 房依赖优化、20 房依赖高效经济、50 房依赖顶尖代码+PvE+联盟交易。但目前没有给出：

- 初始资源包规模能支撑多长时间；
- RCL2-3 后收入如何达到正流量；
- Source 升级/Controller income 的明确成长公式；
- 5 房何时从 -250/tick 转正；
- 20 房是否有可达的稳定区间，还是必然靠存量燃烧；
- 联盟交易是 transfer 而非 faucet，不能从系统层面解决全体 50 房帝国亏损。

这会造成“扩张总是亏损”的经济体验。Anti-snowball 应该是边际收益递减和高规模软上限，不应让所有阶段默认负现金流，否则玩家会被迫囤初始资源或寻找漏洞。

建议：
- 增加至少 3 条可持续曲线：early stable、mid optimized、late elite，展示在合理 RCL/source level 下 1、3、5、10 房可以净正或接近持平。
- 明确 initial resources 与 expected time-to-breakeven，例如“Standard 初始 100,000 Energy，可支撑 1 房 3,000 tick，RCL2 后收入≥维护费”。
- 将 20/50 房定义为高压区可以，但 1/5 房应有清晰的正循环，否则新手会在理解经济前破产。

### E5. High — Global transfer 延迟口径冲突，No Teleport 约束不稳定

`design/gameplay.md` 默认：

- transfer_to_global_time = 10 tick
- transfer_from_global_time = 5 tick

Resource Ledger §2.1：

- global_transfer_delay = 100 tick

API IDL §2 global_storage_commands：

- TransferToGlobal duration = transfer_to_global_time
- TransferFromGlobal duration = transfer_from_global_time

这产生两个问题：

1. 入库和出库是否同一延迟？Resource Ledger 用单一 `global_transfer_delay`，gameplay/IDL 用两个方向参数。
2. 默认值到底是 10/5，还是 100？

影响：
- 物流战略完全不同：5 tick 是短期补给延迟，100 tick 是战略运输周期。
- PvP 中拦截“运输中资源”的窗口大小不同，风险定价不同。
- Arena/World/Tutorial 的体验节奏可能被误调。

建议：
- Resource Ledger 改成两个权威参数：`global_deposit_delay` 与 `global_withdraw_delay`，或明确统一单一 delay 并同步 gameplay/IDL。
- 给出各模式默认值：Tutorial、Novice、Standard、Arena 是否相同。
- 经济报表中加入转运中的资源占用和损耗示例。

### E6. High — AlliedTransfer 设计与 gameplay 外交特权冲突，存在绕税/瞬移风险的文档分叉

Resource Ledger 对 AlliedTransfer 设定：

- allied_transfer_fee = 200 bp
- allied_transfer_delay = 200 tick
- cooldown = 500 tick
- daily cap = 10,000
- 双方联盟 ≥100 tick
- 双方均非 new_player_transfer_lock

但 gameplay.md 外交特权写：

- allied 可直接 player↔player transfer，免 convert 延迟
- API Registry §10.2 又写 AlliedTransfer: “Tax-free transfer between allied players via global storage. No cooldown. Exact amount: sender deduction = receiver credit.”

这三套设定冲突极大。若采用免税、无冷却、无延迟的 allied transfer，联盟会成为最优经济路径：大号可以绕过 global withdraw fee、storage tax 规避、地理物流和新手门控，把资源瞬移给盟友/小号。

影响：
- 破坏 No Teleport。
- 联盟成为避税工具而非外交选择。
- 小号/刷号风控被削弱。
- 大帝国可通过资源分散到盟友账户规避存储税。

建议：
- 以 Resource Ledger 受限 AlliedTransfer 为准，删除 API Registry 中 “Tax-free / No cooldown” 表述。
- gameplay 外交表应改为“allied transfer 可用，但仍经 Resource Ledger，受 fee/delay/cooldown/cap/new-player lock 约束”。
- 增加 anti-avoidance：同盟/同源账号组的全局存储税可按 group aggregate 计算，至少作为 Standard 可选规则。

### E7. Medium — PvE faucet budget 有方向但缺少与 Source faucet 的总量方程

当前 Resource Ledger 给 PvE 四维预算：Global ≤ 世界再生总量 ×30%，Zone ≤ 区域基础再生 ×50%，Player ≤ controller_level ×1000/tick，Event ≤ event_budget_pool。modes.md 又给 NPC 固定掉落、资源据点产出、世界事件倍增。

缺口：
- “世界再生总量”如何计算？仅 Source regeneration，还是含 Resource Boom 后倍率？
- PvE award 与资源据点可采集产出是否共享同一 PvE budget？
- Resource Boom 将全局 Energy/Crystal 再生 ×2 时，PvE cap 是否也随之 ×2？若是，事件期间 faucet 被双重放大。
- Player cap `controller_level ×1000/tick` 对 RCL8 是 8000/tick，远高于多数房间的 source income，可能成为刷 PvE 主导策略。

建议：
- 定义 `world_regeneration_total(tick)` 的精确组成。
- 明确 NPC drop、据点产出、事件奖励是否都走 PvEBudget。
- Player cap 应考虑玩家房间数或近期活跃贡献，避免单高 RCL 玩家无限刷高阶 NPC。
- 对 PvE drop 增加 diminishing returns 或 per-entity respawn budget debt，防止固定路线 farm。

### E8. Medium — Recycle/Build/Lockup 语义未完全一致，可能影响资源销毁率

gameplay.md 写：
- body 不可逆；Recycle 回收 drone 获得 50% 资源退还；Tutorial 前 500 tick 100%。
- 建筑建造是 Lockup，可回收 50%（摧毁时返还）。
- Controller 升级不可回收，永久锁定。

Resource Ledger/API Registry 对 drone RecycleRefund 已有 10%–50% lifespan formula，但建筑回收/摧毁返还没有在 Resource Ledger 的 ResourceOperation 中明确公式。API Registry §10.2 RecycleRefund 只说 Recycle command，描述更偏 drone body cost。

影响：
- 建筑拆除/摧毁是 MMO 经济重要的 unlock/sink 边界。若返还比例不明确，会影响战争收益、掠夺价值、建筑 spam 成本。
- Depot 被摧毁“掉落部分资源”与建筑成本返还是否叠加不清楚。

建议：
- 在 Resource Ledger 增加 `StructureRecycleRefund` / `StructureDestructionDrop`，明确建筑成本返还、库存掉落、敌方可拾取比例。
- 区分 owner 主动回收、敌方摧毁、中立 decay 三种路径。

### E9. Medium — 市场交易仍是 RFC 占位，但全局存储/税制/可交易资源已经假设市场存在

gameplay.md 多处提到：
- 世界本地存储可通过 Terminal 在市场交易；
- 全局存储余额会因市场挂单暴露部分余额；
- resource_types 有 `tradeable = true`；
- Vanilla 分类账将市场交易标为 RFC 占位。

如果市场不在当前设计范围内，则这些经济机制依赖不应作为 Standard 平衡前提。尤其 50 房报表提到“联盟交易”，但市场价格发现、订单费、成交税、挂单锁定、反操纵都未定义。

建议：
- Phase 1 设计中明确：当前 Standard 平衡不依赖公开市场，只依赖 Source/PvE/AlliedTransfer。
- 若 Terminal 交易保留为 near-term，至少定义交易是否经过 Resource Ledger、是否有 listing fee / transaction fee / escrow lock / price bounds。

### E10. Low — 经济反馈 API schema 过薄，难以支撑设计中承诺的仪表板

API Registry 中 `swarm_get_economy` 输出只有 `{income, expenses, storage_tax, maintenance}`，但 gameplay.md 经济仪表板承诺：

- 收入/支出分项
- global/local storage
- 当前税率与下一个税率区间预警
- 未来 N tick 预测
- Harvest/Build/Idle 效率
- 最近 100 tick 趋势

虽然还有 `swarm_get_drone_efficiency` 和 `swarm_get_economy_trend`，但 `swarm_get_economy` 的 schema 不足以表达 storage tier、pending transfer、upkeep deficit、PvE budget 使用率、ledger checksum 等经济健康关键字段。

建议：
- 扩展 EconomySnapshot schema：`income_breakdown`、`expense_breakdown`、`global_storage`、`local_storage_summary`、`pending_transfers`、`current_tax_tier`、`next_tax_threshold`、`upkeep_deficit_ticks`、`pve_budget_remaining`、`ledger_checksum`。
- AI agent 需要机器可读字段，不应只依赖 UI 推导。

## Economy Balance Issues

1. Standard 早期负现金流过强
   - 1 房 -30/tick，5 房 -250/tick，如果没有明确的初始资源和 RCL/source 成长曲线，会形成“默认破产经济”。
   - 建议将 1–3 房设计为可通过 starter bot 达到净正或接近持平；5 房开始需要优化；20 房进入明显高压。

2. 维护费 soft cap 位置不稳定
   - 旧 gameplay 示例的 50 房约 3,150/tick 与 balance sheet 的 15,000/tick差距过大。
   - 这会导致 soft cap 到底在 20、50 还是更高完全不清楚。

3. 税率阈值冲突会重塑整个储蓄策略
   - 若 10K 开始征税，小玩家很早被税；若 30% capacity 才征税，小玩家有明显免税缓冲。
   - 必须统一，否则任何报表都不可用。

4. Allied transfer 如不受限会成为 dominant strategy
   - 免税、无冷却、无延迟的联盟转账会绕过全局↔本地损耗和地理物流。
   - Resource Ledger 的 fee/delay/cap/cooldown 约束必须落到 API 和外交文档。

5. PvE 的 30% global cap 是好方向，但 Player cap 可能过大
   - `controller_level ×1000/tick` 在高 RCL 时可能让 PvE 收入成为主经济来源。
   - 需要结合房间数、NPC respawn、事件预算和区域预算做数值证明。

6. Recycle 10%–50% lifespan formula 优于固定 50%，但文档需同步
   - 固定 50% 会鼓励快进快出重配 body；lifespan proportional 更健康。
   - gameplay 中“一律 50%”表述应改为“最高 50%，随剩余寿命衰减，Tutorial 例外”。

## Resource Loop Gaps

1. Source → harvest → local storage → global storage → upkeep/tax/deploy 的主循环已基本闭合，但参数冲突使实际扣费点不稳定。

2. PvE faucet → player storage 的路径有 budget，但 NPC 掉落、资源据点、世界事件是否共用同一 budget 未完全闭合。

3. Structure lifecycle 不完整：BuildCost 已有，建筑主动回收、敌方摧毁、库存掉落、残骸归属、返还比例缺少 Resource Ledger 级定义。

4. Controller upgrade 是永久 lockup，但 Controller income 又在 economy-balance-sheet 中作为收入源出现；该 income 的来源、成长公式、是否 faucet 未在 Resource Ledger 中定义。

5. Market/Terminal 交易被多处引用，但 Resource Ledger 只把 ContractSettlement 标为 Future RFC，市场交易仍缺 listing/order/escrow/fee/tax/anti-manipulation 账本入口。

6. Upkeep deficit 的惩罚定义在 Resource Ledger，但 economy feedback API 未暴露 deficit ticks/惩罚状态，玩家可能不知道为什么效率突然下降或 drone 快速死亡。

7. Global resource cap 100,000,000 units 已在 API Registry 出现，但达到 cap 后 faucet 如何裁剪、按玩家/区域如何分配、是否记录 rejected income 尚未定义。

## CrossCheck — 需要跨方向检查

- CX1: API Registry 由 IDL 自动生成，但其 economy operations 与 Resource Ledger 冲突 → 建议 Architect 检查“Resource Ledger、economy.idl.yaml、api-registry.md”的单事实源生成链，确认到底哪份文件应作为机器权威。

- CX2: AlliedTransfer 的 fee/delay/cooldown/cap 与外交系统的“免延迟直接 transfer”冲突 → 建议 Gameplay/UX 检查联盟体验是否接受受限转账，并明确玩家界面如何展示转账冷却和每日上限。

- CX3: PvE budget 需要与世界事件、NPC respawn 和资源据点生成共享同一随机/预算模型 → 建议 Architect 检查 PvE faucet 是否在 ECS 执行顺序和 TickTrace 中具备可复放、可审计的统一入口。

- CX4: 经济仪表板承诺的预测、分项和告警超过当前 API schema → 建议 UX/API 检查 `EconomySnapshot` 是否能支撑人类 UI 与 AI agent 决策，而不是只返回四个粗字段。

- CX5: Standard 收支表显示早中期持续净亏损 → 建议 Gameplay 检查新手 10 分钟 golden path 与 first-hour 经济是否会因维护费在 RCL2 前破产。

- CX6: Global resource cap 达上限后的 faucet 裁剪策略未定义 → 建议 Architect 检查资源 cap 在并发玩家、PvE award、source regeneration 同 tick 触发时的公平排序与确定性。

## Recommended Gate

建议 R22 不进入 APPROVE。最低通过条件：

1. 修正 economy.idl/API Registry，使 UpkeepDeduction、StorageTax、AlliedTransfer 与 Resource Ledger 完全一致。
2. 删除或降级 gameplay.md 中旧维护费示例，统一 Vanilla/Standard/Tutorial 曲线。
3. 为 Standard 1/3/5 房提供可持续正循环证明，包括初始资源、RCL/source 成长和 time-to-breakeven。
4. 明确 PvE faucet 的总量方程与 budget 覆盖范围。
5. 补全建筑回收/摧毁/掉落的 Resource Ledger 操作。

在这些问题修复前，经济系统方向正确但不可实现为稳定、可验证、可调参的 MMO 经济。