# R15 Phase 1 Clean-Slate 经济评审（GPT-5.5）

## Verdict

CONDITIONAL_APPROVE

R15 的经济设计相比常见 Screeps-like 系统已经具备较完整的 faucet / sink / transfer / lockup 分类、全局/本地双层存储、维护费、存储税、PvE 产出上限与新玩家资源门，方向正确，可以进入下一轮综合评审。但当前仍有若干经济闭环和曲线校准问题：尤其是 Vanilla `empire-upkeep` 默认参数与文档声称的反雪球目标不一致，联盟直连 transfer 可能绕过全局/本地转换损耗与时间，PvE 资源注入预算缺少按玩家/区域/时间窗的可执行分摊规则，多资源体系与特殊攻击成本存在未闭合资源引用。

## Strengths

- 经济分类账明确区分 Faucet / Sink / Transfer / Lockup / Unlock，避免把采集、建造、Controller 升级、回收等不同资源影响混为一谈。
- 全局存储与本地存储分层合理：全局用于抽象经济力、部署费和维护费，本地用于物理物流、建造与可掠夺资产，能产生真实战略取舍。
- 默认轻物流模式通过本地→全局 1% 与全局→本地 5% 损耗、转换时间和运输中状态，避免全局仓库成为瞬移补给。
- 存储税、帝国维护费、Controller age 维修上限、room drone cap、新手保护与 soft_launch 共同形成反雪球框架。
- Market 被明确降级为 RFC 占位并从当前 IDL/SDK 移除，避免在资源闭环未验证前引入价格发现、撮合与通胀放大器。
- 经济反馈循环（`swarm_get_economy`、经济仪表板、净流量、税率预警、idle/效率告警）对人类和 AI 玩家都可读，有助于让经济压力变成可调试策略而非黑箱惩罚。

## Concerns

### E1 — High — Vanilla 维护费曲线与反雪球目标不一致

文档一方面把帝国维护费列为默认启用的超线性 anti-snowball 机制，并在经济分类账中给出 `-40 ~ -3,150 / tick` 的规模压力；另一方面 `empire-upkeep` 默认参数说明承认 `room_superlinear=1` 在 `fixed<u32,4>` 下几乎线性，50 房仅贡献约 0.25 Energy/tick，只有调到 `10000` 才接近前文示例值。

这会导致 Vanilla 默认世界实际不具备文档宣称的反雪球强度。若默认 faucet 为 Source 再生 + PvE drop，而维护费近似只按 drone 数线性增长，大帝国可通过扩张房间与资源点把收入线性/超线性放大，但只承担弱 room 成本，形成先发滚雪球。

建议：把 Vanilla 默认值、示例曲线和分类账统一为同一张 Economy Balance Sheet，至少给出 1/5/20/50 房间下的收入假设、drone 数、source 数、PvE 收入、upkeep、税费与净流量目标。若设计目标是「MVP 新手友好但 Standard 世界 anti-snowball」，应区分 Tutorial/Novice/Standard 的默认维护费曲线，而不是用一个近乎线性的 Vanilla 默认覆盖全部。

### E2 — High — 联盟 player↔player transfer 可能绕过物流成本、转换时间与税制

Allied 特权允许 `资源 transfer：可直接 player↔player transfer，免 convert 延迟`。这与前文全局/本地转换规则冲突：默认经济要求本地→全局 1% + 10 tick、全局→本地 5% + 5 tick，并强调 No Teleport 防止即时补给。联盟直转若没有距离、容量、冷却、税费、可见性或本地物流约束，会成为绕过全局存储税、转换损耗、运输时间和新玩家资源门的主路径。

典型漏洞：大号与小号/盟友建立联盟，把资源通过 allied direct transfer 在玩家间分散到免税区间；前线玩家通过后方盟友即时补给，绕过全局→本地转换时间；联盟网络可形成事实上的共享银行但不承担 Progressive Storage Tax。

建议：把 allied transfer 明确落到某一经济层：要么只能通过本地实体近距离 `Transfer`/`Withdraw` 完成，受 CARRY、range、可见性和物理仓储约束；要么若是全局 player↔player transfer，必须收取不低于 global transfer 的损耗、时间、容量检查和税务归因，并受 `new_player_transfer_lock_ticks` 与同源账号组限制。

### E3 — High — PvE faucet 上限定义过粗，无法防止区域性刷怪经济

World PvE 设计规定 `max_pve_output_per_tick` 默认为全局 NPC 产出 / tick ≤ 世界再生总量 × 30%。这是正确方向，但只定义了全局预算，缺少按玩家、区域、据点、事件、时间窗的分摊与耗尽机制。若高效玩家垄断 Zone 3/4 富矿、Guardian、Swarm Invasion 和资源爆发，仍可能把 PvE 变成优于 PvP/物流的主经济引擎。

风险点包括：Guardian 蓝图 5% 与 Wreckage 100% 可能形成高价值稀缺资产 faucet；Resource Boom 将全局再生 ×2 持续 100 tick，但没有说明是否也放大 PvE 上限；Merchant 是不可攻击且触发交易事件，但 Market 为 RFC，交易事件的资源来源/去向未分类。

建议：为 PvE 增加可审计预算账本：`pve_budget_global`、`pve_budget_zone`、`pve_budget_player_recent_window`、`event_budget`，并规定每个 drop 从哪个预算扣除、预算如何再生、超额时掉落如何衰减。蓝图应定义为 unlock/recipe 而非可交易资源，或明确其 tradeability、绑定期和重复掉落 sink。

### E4 — Medium — 多资源体系中存在未声明资源与成本闭环断点

默认 Vanilla 声称单一 `Energy`，但特殊攻击/自定义动作示例中 `Fabricate` cost 使用 `{ Energy = 2000, Matter = 500 }`，示例世界定义了 `Matter`，而 Vanilla 表格又说特殊攻击 8 种在 Standard+ 全部可用。这会让 Vanilla 是否真的单资源产生歧义：若 `Fabricate` 在 Vanilla 可用但没有 `Matter`，成本不可支付；若 Matter 只是示例资源，则 Standard Vanilla 的 8 种特殊攻击不应包含该成本形态。

类似地，PvE 掉落包含 `Crystal`、蓝图和 Wreckage，而 Vanilla 核心默认值写单一 `Energy`。多资源世界当然可行，但每种资源必须有明确 source、sink、conversion、storage cap、decay/tradeability 与默认动作成本，否则会出现资源只进不出或只出不进的死资源/套利资源。

建议：拆分 `Vanilla-Energy` 与 `Example-MultiResource`。Vanilla 表中所有默认 body/action/special attack/PvE drop 必须只引用 Energy，或正式声明 Vanilla 含 `Energy + Crystal + Matter` 并补齐完整资源循环。

### E5 — Medium — Controller 升级被分类为 Lockup 但实际更像永久 Sink/Progression Sink

经济分类账把 Controller 升级标为 `Lockup`，说明「不可回收——永久锁定在 Controller 中」。若不可回收且不再进入任何玩家可支配资源池，从系统总量角度它应是 Sink 或 Progression Sink，而非 Lockup。Lockup 通常意味着未来可能 Unlock（建筑摧毁/回收返还），而 Controller 进贡更像资源销毁换取 RCL/GCL/权限。

错误分类会影响平衡直觉：如果设计者把 Controller 进贡视为暂时锁定，可能低估长期资源销毁量；如果它实际是强 sink，则它是对抗通胀的重要锚点，应在日均资源增长模型中明确计入。

建议：将 Controller 升级改为 `Progression Sink` 或 `Permanent Lockup/Sink`，并明确 RCL 降级/房间失守时资源是否有任何返还、是否能被敌方掠夺。

### E6 — Medium — 资源转换损耗表达存在类型与单位歧义

`transfer_to_global_cost = {Energy: 0.01}`、`transfer_from_global_cost = {Energy: 0.05}` 与 IDL `ResourceAmount: u32`、`ResourceCost: Map<ResourceName, ResourceAmount>` 不一致。文档意图是比例损耗，但配置形态看起来像固定资源成本且使用小数。若实现端把它解析为定点、百分比或固定值不一致，会产生严重套利或过度扣费。

建议：把比例损耗建模为显式字段，例如 `transfer_to_global_fee_bps = 100`、`transfer_from_global_fee_bps = 500`，并区分「同资源按比例销毁」与「额外支付某种资源」。IDL 中也应避免 `u32` 与小数字面量混用。

### E7 — Medium — 新玩家资源门与 Tutorial 关闭限制之间存在刷号套利窗口

标准世界默认 `new_player_transfer_lock_ticks = 500`、PvE drop 绑定、同源账号组配额，这是必要的。但 Tutorial 世界默认关闭全部限制，并且文档没有明确 Tutorial 与正式 World 资产是否完全隔离。若 Tutorial 能产生可转移资源、蓝图、人格溢价或任何可导出资产，会成为零风险 faucet。

建议：明确 Tutorial 世界资产不可转入 World/Arena；Tutorial 中 100% 回收、新手免费部署、无 transfer lock 均应仅在隔离经济体内有效。若已有隔离意图，应在经济治理合同中写成硬约束。

### E8 — Low — 交易/合约/Market 引用仍残留，边界需要再收紧

设计已声明 Market 为 RFC 并从 IDL/默认 SDK 移除，这是优点。但反馈循环文档仍提到 `Market Contracts`，外交中有资源 direct transfer，NPC Merchant 触发交易事件，Drone 消息可承载 P2P 交换协议。这些虽然不等于内置市场，但足以形成事实上的交易层。

建议：将当前版本允许的「资源交换原语」列成白名单：local physical transfer、allied transfer（若保留）、global transfer、drone message offer（非担保）。任何 contract、merchant、escrow、orderbook、跨玩家担保交付都应标为 RFC，避免实现者提前做出经济承诺。

## Economy Balance Issues

- 小帝国压力：1 房 20 drone 维护费约 40/tick 的目标合理，但需与 Work harvest `1 unit/tick`、Source regen `300/tick`、spawn cost、基础建造 cost 对齐；否则新手可能要么无压力滚雪球，要么维护费压垮 starter bot。
- 中帝国压力：5 房 100 drone 约 275/tick 仍可承受，但应验证 5 房平均可控制 source 数、运输损耗、active aging、Depot maintenance 后净流量是否仍为正。
- 大帝国压力：20 房 500 drone 约 2100/tick 是合理的反雪球目标，但当前默认 `room_superlinear=1` 不足以制造该曲线；需要调参或明确这是高级世界配置而非 Vanilla 默认。
- 巨帝国压力：50 房 500 drone 约 3150/tick 被称为硬上限，但若房间带来的 source/PvE/事件收入线性增长，这个上限可能仍低于收入增长；维护费应按 rooms、claimed controllers、storage footprint、logistics distance 或 active entities 形成更强边际成本。
- 全局存储税：0–30% 免税、30–60% 1bp、60–85% 5bp、85–100% 20bp 的阶梯方向合理，但如果玩家可通过多账号/联盟/本地仓库分散资产，税基会被规避；需要合并同源账号组、联盟池或本地大仓储的风险成本。
- PvE 输出：全局 30% cap 是初始锚点，但应配合玩家/区域限额，否则最强玩家吞掉大部分 cap 后会加速领先。
- 回收：标准 50% refund 与 Tutorial 100% refund 合理，但 `contention_lost: 0.5` refund 和 Recycle 50% 应避免叠加形成「失败尝试→回收→重试」的成本过低循环。

## Resource Loop Gaps

- Energy：主 loop 基本闭合。Faucet = Source regen + NPC drop；Sink = spawn、特殊攻击、维护费、存储税、transfer loss、代码部署费（可选）；Lockup/Sink = 建筑与 Controller；Unlock = recycle/摧毁返还。仍需量化日均净增长目标。
- Crystal：PvE Guardian、Rich Vein、Resource Race 中出现，但 Vanilla 是否包含 Crystal 不清；Crystal 的标准 sink、存储上限、转化损耗、是否可交易、是否绑定蓝图系统需要补齐。
- Matter：示例配置和 Fabricate 成本出现，但 source、drop、默认世界可得性和主要 sink/source 关系不稳定；如果 Fabricate 是 Vanilla special attack，Matter 必须成为 Vanilla 资源。
- Blueprint：来源为 Guardian 5%，用途为解锁特殊 body/building recipe，但缺少重复掉落处理、绑定/交易规则、是否消耗、是否可转让、是否进入市场/联盟 transfer。
- Wreckage：Guardian 100% 掉落并可回收 `body_cost × 20% Energy`，但 NPC body_cost 的定义、是否计入 PvE cap、是否可被同一玩家循环 farm 都未说明。
- Global ↔ Local：转换损耗和时间存在，但联盟直转、Terminal 市场引用、Merchant 交易事件可能形成旁路；所有旁路都应进入同一 Resource Ledger。
- Drone message P2P trade：消息只是 payload，不担保履约，这是好的博弈元素；但若配合 direct resource transfer，应明确原子交换不存在，避免实现出隐式 escrow。

## CrossCheck — 需要跨方向检查

- CX1: Allied direct transfer 与全局/本地物流规则冲突，可能绕过税费、转换时间和 No Teleport 约束 → 建议 Architect 检查资源 transfer 的数据模型、命令路径和 TickTrace 归因是否只有一个权威入口。
- CX2: `transfer_to_global_cost = {Energy: 0.01}` 与 IDL `ResourceAmount: u32` 类型不一致 → 建议 Architect 检查 world.toml schema、IDL 生成器和定点数规范，避免实现端分叉。
- CX3: PvE drop budget 需要按区域/玩家/事件窗口执行，涉及 NPC 生成、掉落表、事件系统和审计 → 建议 Architect 检查 PvE 预算账本是否能在 ECS/Rhai action log 中确定性扣减。
- CX4: Alliance、小号、Tutorial 隔离、new_player_transfer_lock 与 same-origin quota 涉及滥用防护 → 建议 Security 检查账号组识别、资源门绕过、联盟洗钱与刷号 faucet。
- CX5: 经济仪表板和 `swarm_get_economy` 暴露全局/本地存储、税率、趋势、预测 → 建议 Security 检查可见性过滤，避免通过经济查询泄露敌方仓储、PvE farm 或联盟资产。
- CX6: Market 虽为 RFC，但 Merchant、Market Contracts、drone P2P offer 和 allied transfer 仍构成事实交易层 → 建议 Game Designer 检查当前 MVP 是否应保留这些入口，或统一标为后续经济扩展。

## Final Recommendation

建议有条件通过 R15 Phase 1：保留当前双层存储、分类账、存储税、维护费、PvE cap 和经济反馈方向；但在冻结设计前，应优先补一份可执行的 Vanilla Economy Balance Sheet，并修正 allied transfer、PvE budget、多资源默认集、Controller 分类和转账费率类型。若这些问题不收敛，World 模式很容易出现先发帝国靠 PvE/联盟/多账号形成无限滚雪球，而新玩家只能在 safe_mode/soft_launch 后进入不可追赶状态。
