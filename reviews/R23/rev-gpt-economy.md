# R23 经济评审（GPT-5.5）

## Verdict

REQUEST_MAJOR_CHANGES

经济设计方向正确：已经意识到必须用 Resource Ledger 统一资源入口、用超线性维护费和存储税抑制大帝国滚雪球，并为 World / Arena / Tutorial 分别设定不同经济目标。但当前 R23 经济文档仍不能冻结：关键公式、参数、示例收支和 API Registry 之间存在多处冲突；Standard 收支表显示 1/5/20/50 房间全部长期净亏损，且缺少明确的成长路径与 faucet 校准依据。若按当前文本实现，经济系统很可能在新手/中期阶段先被维护费压死，而不是在大帝国阶段形成健康 soft cap。

## Strengths

- Resource Ledger 作为单一经济入口是正确架构：Local/Global/Allied/PvE/Recycle/Build/Spawn/Upkeep/StorageTax 都进入统一账本，并要求 TickTrace 记录 `(tick, source, target, resource_type, amount, operation, fee_paid)`，有利于审计和回放。
- 已经区分 Faucet / Sink / Transfer / Lockup / Unlock，比常见 MMO 文档只列资源名更成熟，能避免早期遗漏净注入和净销毁路径。
- 反雪球目标明确：累进存储税、全局/本地转换损耗、转移延迟、allied transfer 限制、PvE budget、new player transfer lock、empire upkeep 都指向限制无限囤积和小号输血。
- Tutorial / Novice / Standard 的参数分层是合理方向：教学世界弱维护费、长保护期、免税；Standard 启用完整 anti-snowball；Arena 隔离且不产出 World 资源。
- PvE 产出有预算框架：Global / Zone / Player / Event 四维 cap 可以防止“刷怪经济”吞噬主经济，只要后续把预算公式落到权威表即可。
- 全局存储不是免费瞬移：本地↔全局有损耗、延迟和运输中状态，能保留物流玩法，并避免战斗中即时补给。

## Concerns

### E1 — Critical — Standard 维护费曲线把小/中帝国也压成长期负收益

`design/economy-balance-sheet.md` 的 Standard 收支表显示：

- 1 房间：收入 25/tick，支出 55/tick，净流量 -30/tick。
- 5 房间：收入 140/tick，支出 390/tick，净流量 -250/tick。
- 20 房间：收入 1,220/tick，支出 3,160/tick，净流量 -1,940/tick。
- 50 房间：收入 3,975/tick，支出 16,600/tick，净流量 -12,625/tick。

这不是“第 N+1 个房间边际收益递减”，而是“所有规模都负收益”。文档用“需要初始资源包支撑”“升级后可平衡”“需要高效经济”解释，但没有给出初始资源包大小、升级成本、升级耗时、RCL 收入公式、Source level 公式或效率上限。经济评审无法证明玩家能从 1 房间过渡到 5 房间，更无法证明 20 房间是高效玩家目标而非数学死路。

建议：在 Resource Ledger 或 balance sheet 中加入 growth path 表，至少覆盖 tick 0→500→2000→RCL3→5房间的可达路径；要求每个阶段有明确的 faucet、sink、升级成本和 break-even tick。Standard 的 1 房间不应默认长期亏损，除非明确存在足够大的启动补贴且补贴本身有反小号约束。

### E2 — High — 维护费公式和数值在允许阅读文件内互相冲突

`specs/core/08-resource-ledger.md` 与 `design/economy-balance-sheet.md` 使用：

```text
upkeep = base_upkeep × rooms × (1 + rooms / room_soft_cap)
Standard: base_upkeep=50, room_soft_cap=10
```

该公式给出 1/5/20/50 房间维护费为 55 / 375 / 3000 / 15000 per tick。

但 `design/gameplay.md` 后段仍保留另一套 empire-upkeep 示例：

```text
小帝国（1 房, 20 drone）: 维护费 ≈ 40/tick
中帝国（5 房, 100 drone）: 维护费 ≈ 275/tick
大帝国（20 房, 500 drone）: 维护费 ≈ 2100/tick
巨帝国（50 房, 500 drone）: 维护费 ≈ 3150/tick
```

同一设计集中 50 房间维护费同时可能是 3,150/tick 或 15,000/tick，差距接近 4.8 倍。虽然 Resource Ledger 声称是权威，但 gameplay 文档仍是玩家/实现者会读到的规则说明，会直接导致实现、调参和玩家预期分叉。

建议：删除或改写 gameplay 中旧公式示例，只保留 Resource Ledger 权威公式；若希望 Tutorial/Novice 使用旧曲线，必须明确标注模式并给出对应参数，不能与 Standard 混写。

### E3 — High — 收入侧模型缺少权威定义，无法证明资源闭环

Balance sheet 假设了若干收入项，但 Resource Ledger 没有定义其数学来源：

- `Controller income`：在 1/5/20/50 房间分别提供 5/30/200/600 income，但 Resource Ledger 只把 Controller 升级描述为 Lockup，不定义 Controller income 这个 faucet。
- `Source Harvester ×2 = 20/tick`、`46 Source Harvesters = 920/tick`、`115 Source Harvesters = 2875/tick`：这些隐含每 harvester 10/20/25 per tick，但 gameplay 的 vanilla 默认又写 `Work harvest: 1 unit/tick`，二者缺少换算关系。
- `L1/L2/L3/L4 source`、`RCL 4-5 avg income`：相关升级规则、成本、产出倍率未进入 Resource Ledger 权威参数表。

这会导致“表格看似闭环，但核心 faucet 是文档外假设”。如果实现者只按 Resource Ledger 做账，Controller income 可能不存在；如果按 balance sheet 做，Resource Ledger 的总量守恒审计又缺少操作枚举。

建议：把所有净注入路径列入 ResourceOperation 或其子类：SourceRegeneration、ControllerIncome、PvEAward、ResourceBoom 等，并为每个提供公式、上限、执行顺序和 TickTrace 归因。

### E4 — High — 存储税权威表、公式和 API Registry 限制存在不一致

Resource Ledger 定义 `storage_tax_tiers = [(30,0),(60,1),(85,5),(100,20)]`，语义是容量百分比；示例中 750,000 / 1,000,000 = 75% 时税为 105/tick，这个结果合理。

但 `api-registry.md` 的 Economy 限制又写：

- Storage tax tier 1 threshold = 10,000 units。
- Storage tax tier 2 threshold = 100,000 units。
- Storage tax tier 3 threshold = 1,000,000 units。

这与 30%/60%/85% 容量 tier 不一致。若按 API Registry 的绝对阈值实现，小容量世界和大容量世界的税负曲线会完全不同，且无法对应 gameplay 的“按容量利用率防囤积”目标。

同时 Resource Ledger §2.2 的公式写法把 `storage_pct` 直接乘以 `global_storage_capacity / 10000`，容易被实现为漏除 `/100` 的公式；示例结果说明作者意图是按 percentage points 转容量单位，但公式文本不够机器可执行。

建议：统一 API Registry 的 Economy limits 为百分比 tier，或明确那些绝对值只是默认容量 1,000,000 下的派生结果；同时把存储税公式改成以 `stored_units` 分段，避免 percent/unit 混算歧义。

### E5 — High — 资源执行顺序可能制造“有本地资源但先饿死”的负体验

Resource Ledger 执行顺序把 `UpkeepDeduction` 和 `StorageTax` 放在每 tick 的第 1、2 步，且维护费从玩家全局存储扣除。之后才处理 PvEAward、LocalTransfer、GlobalDeposit、GlobalWithdraw、BuildCost、SpawnCost、RecycleRefund。

这有确定性优点，但会制造经济陷阱：玩家本地仓库或 drone 身上有足够 Energy，甚至本 tick 正准备 `GlobalDeposit`，仍可能因为全局存储在第 1 步不足而记录 `UpkeepDeficit`。连续 deficit 会触发效率 -50% 和 age ×10，导致“物流延迟 + tick 顺序”被体验成账本不公平。

建议：明确维护费结算周期和 grace buffer。例如：维护费按上一 tick 已 settled 的 global balance 计算，并在 UI/MCP 提前 30 tick 警告；或者允许本地到全局的已完成在途转移先 settle，再扣维护费。无论选择哪种，都需要写入 Resource Ledger 执行顺序。

### E6 — Medium — Allied transfer 与外交文档冲突，存在联盟输血套利空间

Resource Ledger 定义 allied transfer：2% fee、200 tick delay、500 tick cooldown、daily cap 10,000、联盟持续 ≥100 tick、new player lock 过滤。Gameplay 外交表却写 allied 可直接 player↔player transfer，免 convert 延迟。

“免 global/local convert 延迟”不等于“无延迟”，但当前措辞容易被实现为 instant allied transfer。若 allied transfer 可绕过 1%/5% global/local损耗与运输拦截，又只收 2%，联盟可用它作为低成本跨区域物流通道，削弱 No Teleport 和本地物流玩法。

建议：外交文档改为“可发起 AlliedTransfer，但仍受 Resource Ledger 的 fee/delay/cooldown/daily cap 约束”；并明确 allied transfer 的资源来源/落点是 global→global、local→local，还是必须经过 Terminal。

### E7 — Medium — 回收/销毁机制对建筑和 drone 的处理不一致

Gameplay 仍写“body 不可逆，可通过 Recycle 回收 drone 获得 50%资源退还”，而 Resource Ledger 已改为 lifespan-proportional 10%–50%。Balance sheet 又把建筑建造定义为 Lockup，摧毁可回收 50%，Controller 不可回收。

问题是：建筑摧毁、主动拆除、敌方掠夺、Depot 占领、NPC Wreckage 回收分别属于 Unlock、Transfer 还是 Faucet/Sink 并未在 Resource Ledger 中完整列出。若建筑普遍 50%返还，大帝国可以通过“临时建筑锁仓”规避 storage tax；若敌方摧毁也返还给原 owner，则 PvP 没有经济掠夺；若返还到地面可抢，则需要本地资源实体和 decay 规则。

建议：把 StructureRecycleRefund、StructureDestructionDrop、LootPickup 纳入 ResourceOperation，明确 owner、位置、回收率、是否计入存储税、是否 decay。

### E8 — Medium — PvE faucet 有 cap，但奖励表与世界再生预算未闭合

World PvE 文档给出 Creep/Guardian/Swarmling 掉落、资源据点产出和世界事件，Resource Ledger 给出 PvE budget：Global ≤ 世界再生总量 ×30%、Zone ≤ 区域基础再生 ×50%、Player ≤ controller_level ×1000/tick、Event ≤ event_budget_pool。

但仍缺少三项关键校准：

- 世界再生总量如何计算：只算 SourceRegeneration，还是包括 ResourceBoom 后的再生？
- NPC 掉落未产出时如何反馈：击杀 Guardian 但 budget exhausted，是少掉落、延迟掉落、还是转成非资源奖励？
- PvE 蓝图是经济资产还是纯解锁：若可交易，蓝图是高价值 faucet；若不可交易，需要绑定规则。

建议：PvE 奖励表改为“期望值 + budget 裁剪后最大奖励”，并规定 budget exhausted 时的玩家可见反馈，避免玩家误以为掉落被吞。

### E9 — Low — Market 被移出当前范围，但资源 tradeable 字段和经济目标仍依赖市场

文档多处出现 `tradeable = true`、市场挂单暴露余额、联盟交易、Merchant NPC、P2P offer，但 Resource Ledger 把 Market / Contract / Merchant / Drone P2P Offer 标为 Future RFC 或占位。

这在 Phase 1 可以接受，但当前经济平衡表的 50 房间说明写“需要 PvE 农场 + 联盟交易”，等于用未冻结系统解释已冻结曲线。如果 allied transfer 是唯一当前交易机制，应避免用“市场/联盟交易”作为 Standard 维持 50 房间的必要前提。

建议：把 R23 的可平衡目标限定为“无市场，仅 Resource Ledger + AlliedTransfer + PvE”的闭环；Market 相关收益不要进入当前 balance proof。

## Economy Balance Issues

- 小帝国压力过高：Standard 1 房间默认 -30/tick，不符合“新手轻松”目标。若必须靠初始包支撑，应给出 `starting_amount`、可持续 tick、达到 break-even 的必要动作。
- 中帝国无正反馈窗口：5 房间 -250/tick，且没有明确说明 RCL/source 升级后何时转正。玩家可能在“扩张前亏损，扩张后更亏损”的区间卡死。
- 大帝国 soft cap 目标过猛：20 房间 -1,940/tick 已经接近硬惩罚，而不是 50 房间才逼近上限。20 房间应该是高效玩家可维持目标，不应只靠文档外 PvE/交易续命。
- 50 房间维护费差异过大：3,150/tick 与 15,000/tick 两套曲线会导向完全不同的战略环境，必须先统一再谈平衡。
- 存储税本身合理，但阈值冲突会导致实现偏差：按容量百分比是 anti-hoarding；按绝对 10k/100k/1M 是另一套经济。
- 全局转移损耗 1%/5% 能形成 sink，但 allied transfer 2% 若不受位置/Terminal/延迟限制，可能成为绕过物流的主导策略。
- PvE budget 方向正确，但没有和 Source regeneration、Resource Boom、NPC respawn、Blueprint 价值统一到同一经济报表。

## Resource Loop Gaps

- 缺少完整 faucet 表：SourceRegeneration、ControllerIncome、PvEAward、ResourceBoom、StartingAmount、NPC Wreckage、Blueprint 是否创造经济价值，需要同一表列出。
- 缺少完整 sink 表：Upkeep、StorageTax、SpawnCost、BuildCost、CodeUpdateCost、GlobalTransferFee、AlliedTransferFee、RepairCost、MemoryUpkeep、DepotMaintenance、Decay 需要统一执行顺序和默认启用状态。
- Lockup / Unlock 规则不完整：建筑建造、建筑摧毁、Controller 升级、drone 回收、Depot 占领的资源归属和返还比例未完全账本化。
- Local vs Global 状态转换缺少实体级生命周期：运输中资源、拦截、失败、到达、取消、refund 的操作类型和 TickTrace 事件需要补齐。
- 资源 cap 与税制关系不清：global_storage_capacity、resource_type.max_storage、Global resource cap、per-player cap、storage tax capacity 基准之间缺少优先级。
- 经济短缺处理需要闭环：UpkeepDeficit 触发效率惩罚和死亡，但缺少“恢复条件”“UI/MCP 预警”“是否允许债务”“债务是否可被联盟支付”。

## CrossCheck — 需要跨方向检查

- CX1: Resource Ledger 执行顺序把 Upkeep/Tax 放在所有收入与转移之前，可能与 tick pipeline 的 apply 阶段、death_cleanup、spawn/build 顺序存在架构耦合风险 → 建议 Architect 检查资源操作顺序是否能与 ECS system order、TickTrace replay、FDB transaction 原子性一致。
- CX2: Resource Ledger 声称所有资源流动统一入口，但 Rhai 模组可调用 `actions.award_resource` / `actions.deduct_resource`，如果能力白名单绕过 ledger，经济审计会失效 → 建议 Security 检查 Rhai actions 是否强制走 Resource Ledger、是否能伪造 operation attribution。
- CX3: Allied transfer、new_player_transfer_lock、same_origin_account_group_quota 依赖身份/IP/device fingerprint 约束，属于经济反女巫关键路径 → 建议 Security 检查小号输血、联盟转移拆分、账号组规避和 24h cap 的审计模型。
- CX4: API Registry 标注由 IDL 自动生成但与 Resource Ledger 经济阈值冲突 → 建议 Architect 检查 IDL/codegen 的经济参数来源，确保 Markdown、IDL、world.toml schema 不会三方分叉。
- CX5: 经济反馈循环要求 Web UI/MCP 给出净流量、税率、预测和 idle 原因，但当前经济短缺、PvE budget exhausted、维护费 deficit 的用户可见事件未完全列入 API → 建议 Designer 检查经济仪表盘是否能解释“为什么我亏损/为什么没有掉落/为什么 drone 饿死”。
