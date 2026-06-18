# R14 经济评审（GPT）

## Verdict

CONDITIONAL_APPROVE

设计已经具备可评审的经济骨架：资源 faucet/sink/lockup 分类、全局/本地双层存储、物流损耗、累进存储税、帝国维护费、PvE 产出上限、新玩家资源门、Arena/World 经济隔离等关键支柱均已出现。整体方向比 Screeps 式“单资源 + 无限房间扩张 + 市场后补”更稳健。

但当前仍不宜无条件冻结：若不补齐维护费曲线量纲、PvE/事件 faucet 总预算、P2P/联盟交易绕过、资源转换套利与短缺惩罚定义，大世界长期运行后仍可能出现通胀、先发优势过强或最优策略单一化。建议在设计冻结前补一份“Vanilla Economy Balance Sheet + Simulation Targets”，把默认世界的资源流量、维护费、扩张收益和风险边界数值化。

## Strengths

1. 资源模型有明确闭环意识

- 文档将 Source 再生标记为 Faucet，将 Spawn、维护费、存储税、转换损耗、部署费标记为 Sink，将建造/Controller 升级标记为 Lockup，避免了常见 RTS/MMO 设计中“资源从哪里来/到哪里去”未定义的问题。
- 默认单资源 Energy 降低学习成本，同时保留 `resource_types`、`source_types`、`actions.costs` 扩展到多资源世界的能力。
- 本地存储与全局存储分层是正确方向：本地资源承担空间与掠夺风险，全局资源承担便利性与税/转换损耗。

2. 已有多重 anti-snowball 机制

- Empire upkeep 使用 rooms 的超线性维护费，是对持久世界“先占更多房间 → 产出更多 → 永远更强”的必要反制。
- 累进全局存储税与容量/税率 tier 共同限制无限囤积。
- Controller 维修硬上限、drone lifespan、active aging、Depot 维护成本共同阻止永久兵团与无代价前线驻军。
- Safe mode + soft_launch + 新玩家资源门分别处理新手保护、刷号套利和早期被碾压体验。

3. World / Arena 经济边界清晰

- Arena PvE Challenge 明确不产出 World 资源、不消耗 World 资产，这是防止排行榜/练习模式成为资源水龙头的关键边界。
- Arena 默认免税、对称资源、赛前锁代码，与 World 的不公平持久经济分离，避免一个平衡目标污染另一个。

4. 经济可观测性设计较强

- `swarm_get_economy`、经济趋势、税率预警、drone efficiency 和负流入告警能让人类/AI 玩家理解经济压力，而不是只看到资源突然归零。
- 对 AI 玩家尤其重要：宏观经济状态作为只读 MCP 数据出口，有利于形成“扩张 vs 优化”的策略闭环。

5. 市场功能暂缓是合理决策

- Market/Terminal 交易标为 RFC 占位，而不是在资源闭环未验证前直接引入全局订单簿，这是正确克制。开放市场会放大任何 faucet/sink 误差，设计上应后置。

## Concerns

### E1 — High — 帝国维护费曲线的量纲与默认公式不自洽

文档给出示例：

- 小帝国：1 房、20 drone，维护费约 40/tick
- 中帝国：5 房、100 drone，约 275/tick
- 大帝国：20 房、500 drone，约 2100/tick
- 巨帝国：50 房、500 drone，约 3150/tick

但示例 `empire-upkeep` 公式为：

`total_cost = drones * drone_cost + rooms * (room_base + rooms * room_superlinear / FIXED_SCALE)`

默认配置片段显示 `drone_cost = 2`、`room_base = 10`、`room_superlinear = 1`（fixed<u32,4>），则 20 drone 已经是 40/tick，房间项至少还会增加 10/tick；与“小帝国约 40/tick”不一致。若为解释性近似，也需要明确 vanilla 真正公式与参数。

更大的问题是维护费没有和房间产能绑定。Source 再生目标是 +3,000 ~ +10,000 / 玩家 / 天，但维护费是 -40 ~ -3,150 / tick。若 World tick 间隔 3s，则一天约 28,800 tick；40/tick 已是 1,152,000/day，远高于 Source 日增长目标。若“天”是游戏内抽象单位，必须定义换算。否则维护费会把所有规模经济压垮，或文档中的日增长目标失真。

建议：冻结前必须给出统一 tick/day 换算，并提供每房间平均可持续产出、每 RCL 阶段净流量、维护费占收入比例目标。例如：

- 1 房新手期：维护费 ≤ 稳定采集收入的 10–20%
- 5 房中期：维护费约 25–40%
- 20 房后期：维护费约 55–75%，迫使优化但不硬锁死
- 50 房巨型帝国：必须依赖物流、Depot、PvE/贸易策略，但仍有正期望上限

### E2 — High — PvE faucet 与世界事件产出未纳入统一资源预算

文档定义 NPC 掉落、资源据点、世界事件，并写明 `max_pve_output_per_tick` 默认 ≤ 世界再生总量 × 30%。这是好方向，但仍缺少预算口径：

- “世界再生总量”是否包含所有 Source、Rich Vein、Energy Spring、Resource Boom 后的倍率？
- NPC 掉落是否从全局 PvE 池扣减，还是击杀时凭空生成？
- Resource Boom 将全局再生 ×2，是否会同步抬高 PvE output cap，从而形成双倍 faucet 叠加？
- Guardian 蓝图不一定是资源，但若解锁高收益配方，会形成间接 faucet，需计入经济权重。

当前 PvE 设计有形成“刷怪经济优于扩张/采集/战争”的风险。特别是固定刷新 NPC + 可编程自动化玩家，会迅速找到低风险刷怪路线，将 NPC 掉落变成可预测现金流。

建议：将 PvE 产出改为显式 budgeted faucet：每世界/区域/难度层有独立预算桶，NPC 掉落和据点产出从预算桶扣减；预算不足时降低掉落或延迟刷新。Resource Boom 应先定义是否提高预算桶，默认不建议同时提高 Source 与 PvE 掉落上限。

### E3 — High — Alliance 直接 player↔player transfer 可能绕过物流、税和新玩家资源门

外交系统中 allied 权限写明“可直接 player↔player transfer，免 convert 延迟”。这会破坏前文全局/本地转换的核心约束：

- 全局↔本地转换需要时间与损耗，防止即时补给。
- 本地存储隐匿性与物流运输是战略权衡。
- 新玩家 transfer lock 防止刷号输血。

若 allied transfer 不受距离、Terminal、容量、冷却、税和新玩家门限制，大帝国可通过联盟网络建立近乎无摩擦银行/补给链，绕过 1%/5% 损耗、运输中可拦截、全局存储税与局部补给压力。此类“联盟银行”是 MMO 经济通胀与先发优势放大的经典反模式。

建议：allied transfer 也必须选择一种物理/经济路径：

- global→global：受全局存储税、转账费、每日/每 tick 限额、新玩家锁约束；
- local→local：必须经 Terminal/Depot/Carry 物流或可拦截运输；
- emergency transfer：可存在但需高额 sink、冷却、公开事件和上限。

“免 convert 延迟”不应作为默认 allied 特权；最多作为特定世界规则或高成本外交科技。

### E4 — Medium — 全局/本地存储转换存在潜在套利与口径缺失

默认轻物流为本地→全局 1% 损耗、全局→本地 5% 损耗。方向上合理，但需要补齐：

- 损耗资源是否按被转换资源扣除，还是统一消耗 Energy？表中 `ResourceCost {Energy: 0.01}` 容易被理解为“每单位任何资源只付 Energy”，多资源世界会产生用廉价 Energy 搬运稀缺 Crystal/Gas 的套利。
- 若转换成本以目标资源计价，如何处理不同资源小数精度与定点舍入？
- 转换中的资源可被拦截，若被拦截是全部损失、部分掉落，还是转移给攻击者？这会影响风险定价。
- 是否允许并行多笔 transfer？IDL 有 `transfer_time_remaining(0)`，看似每玩家或每资源同时只允许一笔，但口径未写清。

建议：转换费默认按“被转换资源的百分比销毁”计算，而不是固定 Energy；若要 Energy 作为手续费，应额外叠加，不应替代资源损耗。并明确 transfer 队列、并发、取消、拦截和 refund 规则。

### E5 — Medium — 市场为 RFC，但 API/玩家协议已经留下交易入口

文档声明 Market/Terminal 交易为 RFC，不在当前范围；但 IDL 已包含 `CreateMarketOrder`、`BuyMarketOrder`，消息系统允许 P2P offer，外交允许 allied transfer，Merchant NPC 会触发交易事件，Market Contracts 也出现在 onboarding 低风险冲突里。

这不是实现问题，而是设计边界问题：即使中心化市场延期，玩家仍可通过消息 + transfer + alliance 构建影子市场。若基础经济没有交易税、反洗钱/反小号、订单履约风险、担保/押金、失败赔付和速率限制，影子市场会绕过官方 RFC 的平衡假设。

建议：Phase 1 至少定义“非市场交易最低合同”：

- 所有 player↔player 资源移动都要进入统一 Transfer Ledger；
- 受新玩家锁、同源账号组配额、频率限制、可审计事件约束；
- 默认无担保 P2P 交易不提供原子 swap，防止玩家误解；
- Market API 在 market_enabled=false 时应完全不可用，且 starter/world docs 不应暗示已可用。

### E6 — Medium — 建筑建造被归类为 Lockup，但摧毁/回收返还规则不完整

Vanilla 分类账写“建筑建造 = Lockup，可回收 50%（摧毁时返还）”，Controller 升级为不可回收 lockup。这里需要更精细：

- 主动拆除、被敌方摧毁、Decay、自毁、占领后拆除是否都返还 50%？返还给谁？掉落在本地还是进入全局？
- 若敌方摧毁可回收 50%，战争可能成为资源转移/faucet；若返还给原 owner，攻击者收益不足；若掉落给攻击者，打建筑可能成为高收益 farm。
- 建筑 HP 维修消耗 `repair_per_hit`，但维修是否恢复 lockup 价值？是否可通过“建造→受损→维修→回收”套利？

建议：建筑应区分 recycle、dismantle、destroyed、captured 四种路径。推荐默认：主动拆除返还低比例到本地；敌方摧毁掉落更低比例且可被抢；自然 decay 不返还或极低返还；Controller 进贡永久 sink/lockup 不返还。

### E7 — Medium — Drone recycle 50% 与 Tutorial 100% 需要防部署/重构套利边界

Body 不可逆 + Recycle 50% 是合理的试错成本；Tutorial 前 500 tick 100% 返还也合理。但要明确：

- 100% 返还是否仅限 Tutorial 独立世界，不能迁移到正式 World；文档有隔离倾向，但应在经济规则中明确。
- Recycle refund 基于原始 body cost、当前世界 body cost，还是 spawn 时记录的 cost snapshot？若 world.toml 调参后按当前成本返还，会产生跨版本套利。
- Active aging 与即将死亡 drone 的 recycle 价值是否折旧？如果无折旧，最优策略可能是在 lifespan 末尾回收所有 drone，实际生命周期 sink 变低。

建议：refund 基于 spawn-time cost snapshot，并按剩余 lifespan 或 age 折旧；Tutorial 100% refund 必须限定在不可转出世界。

### E8 — Medium — 资源类型扩展缺少“替代性/瓶颈资源”平衡准则

系统支持 Crystal/Gas/Matter 等多资源，但目前只定义 schema，没有说明多资源之间的 faucet/sink 比例、瓶颈角色和替代路径。多资源 RTS 常见反模式是：

- 某稀缺资源只作为高级单位门槛，导致先拿到富矿者永久领先；
- 某副资源产出太低，所有策略被单一 bottleneck 卡死；
- 资源间可通过市场/交易互换后，最稀缺资源成为唯一真实货币，其它资源退化为噪音。

建议在 Vanilla 或扩展指南中增加 Resource Design Contract：每个资源需声明 faucet、primary sinks、substitutability、decay、tradeability、intended bottleneck phase，并给出默认目标占比。

### E9 — Low — 全局存储税可能激励“本地小仓库海”规避

全局存储税只对 global storage 征收，本地存储完全私有且无税。设计上这是战略权衡，但如果本地 Storage 容量很高、维护费低、风险可通过 safe 后方降低，大帝国会把资源拆散到大量本地仓库逃税。

这不一定是坏事，因为它引入可掠夺目标和物流成本。但需要确保规避税的成本真实存在：本地仓库维护费、占地、可见性/侦察、运输时间、防守成本、摧毁掉落规则必须足够强。否则累进存储税会变成只惩罚新手/中型玩家的“不会优化税”。

建议：明确本地大额存储的风险与成本，必要时对 Storage/Terminal 增加容量阶梯维护费或区域性腐败衰减。

### E10 — Low — 经济告警可能泄露竞争情报的边界需定义

经济仪表板自身可见，allied 资源/建筑/HP 额外可见；排行榜可显示全局存储排名区间。需要定义哪些经济指标可被盟友、敌人、旁观者、Replay 看到。否则“全局存储利用率房间边缘颜色”之类 UI 可能意外泄露资源规模。

建议由 UX/Security 共同确认 EconomySnapshot 的 visibility policy：owner/full、ally/partial、enemy/scouted-only、public/aggregate。

## Economy Balance Issues

1. 维护费 vs 收入未统一到同一时间尺度

当前最大平衡风险是 `per tick` 维护费与 `per day` 资源增长目标并列但未换算。按照 3s tick 粗算，一天 28,800 tick，哪怕 40/tick 也是百万级日支出，和 +3,000 ~ +10,000 / 玩家 / 天不在同一数量级。这会导致以下两种解释之一必然错误：

- 维护费示例过高，玩家无法维持基础规模；或
- faucet 目标过低，文档低估了实际通胀；或
- “天”不是现实天，但未定义。

需要强制补一张 Vanilla 经济表：每 tick/每小时/每天的 Source 产出、PvE 产出、spawn 消耗、建筑 lockup、维护费、税、转换损耗。

2. 扩张收益函数缺失

反雪球要成立，必须比较“新增房间的边际收益”与“新增房间的边际维护费/防守/物流成本”。目前只看到维护费曲线，没有看到每房间平均 source 数、source regen、富矿概率、NPC 风险、Controller 升级成本曲线。

建议为 RCL1–RCL8 和 1/5/20/50 rooms 分别给出目标净收益区间。否则 O(n²) rooms 可能过强导致扩张无意义，或过弱导致大帝国继续无限滚雪球。

3. PvE 与 PvP 的机会成本未校准

PvE 掉落上限写得正确，但缺少“同等 drone 投入下，采集/扩张/PvE/掠夺”的收益比较。若 Guardian/Wreckage/Blueprint 收益高且风险可自动化规避，PvE farm 会成为 dominant strategy；若太低，则 PvE 只是新手装饰。

建议定义 PvE ROI：低级 PvE 低于同等采集但提供训练/蓝图机会；高级 PvE 高波动、高风险、高方差，不应稳定超过最优经济扩张。

4. 先发优势仍偏强，需要软重置或边境收益设计

文档接受 World 不公平，这是合理的。但大帝国在以下方面同时占优：更多本地仓库、更强防守、联盟网络、更多 PvE 区域、更高 GCL/RCL、更多算法调优数据。维护费与税只能抑制资源，不一定抑制信息优势和地缘优势。

建议补充边境/远离中心的收益与风险：外层高产但高 NPC/物流成本，新玩家安全区有有限但稳定资源，老玩家远征收益递减或暴露补给线。

5. 短缺处理 `onshortfall` 会极大影响经济稳定

Empire upkeep 配置有 `onshortfall = degrade/damage/despawn`，但默认行为的经济后果差异巨大：

- degrade：软惩罚，允许恢复；
- damage：可能触发维修 sink 螺旋；
- despawn：硬惩罚，可能导致死亡螺旋和 rage quit。

建议 Vanilla 默认采用 degrade，并提供逐步升级：短缺 1–N tick degrade，长期短缺 damage，极长期才 despawn；同时必须有 UI/MCP 提前预警。

6. Refund 与 contention policy 可能影响 bot 策略

IDL 有 `refund_policy: contention_lost = 0.5`，`self_invalid = 0.0`。对经济而言，contention lost 半退费会降低竞争冲突成本，但也可能鼓励 spam Build/Harvest/Transfer 争抢。需要明确哪些 command 预扣资源、何时 refund、refund 是否进入本地或全局。

## Resource Loop Gaps

1. 缺少统一 Transfer Ledger

资源路径很多：harvest、local storage、global storage、transfer_to_global、transfer_from_global、market RFC、P2P message offer、allied transfer、NPC drop、Merchant event、contract reward、recycle、building destruction。当前没有明确所有资源移动都进入同一个审计/平衡 ledger。

建议定义 ResourceLedgerEvent：`source_kind`、`sink_kind`、`resource`、`amount`、`from_owner`、`to_owner`、`location`、`reason`、`tick`、`is_faucet/sink/transfer/lockup/unlock`。经济模拟、审计、反作弊和回放都应使用它。

2. Merchant / Market Contracts 是未闭合 faucet

Modes 和 onboarding 提到 Merchant 交易事件、Market Contracts 奖励，但 gameplay 又声明 Market 为 RFC。若 Merchant/Contracts 产出资源，必须定义其资金来源：世界 faucet 预算、NPC budget、玩家押金、还是系统凭空发放。

建议在 Market RFC 前，所有 contract reward 默认来自发布者押金；NPC Merchant 默认只做资源兑换且带损耗，不净生成资源，除非消耗 PvE budget。

3. 蓝图是非资源资产，但缺少 sink/流通规则

Blueprint 来源是 Guardian 5%，用途是解锁特殊 body part 或建筑配方。需要定义：是否可交易、是否消耗、是否账号绑定、是否永久解锁、重复蓝图如何处理。否则蓝图会成为高阶经济货币，绕开 Energy/Crystal 平衡。

建议：新手期/关键蓝图绑定账号；重复蓝图可分解为少量资源但受 PvE budget；可交易蓝图需进入市场 RFC。

4. Controller 升级 lockup 缺少升级成本曲线

RCL/GCL 是长期目标，但未给出 Controller 升级每级所需资源、降级规则、维护/老化曲线。它是最重要的长期 sink/lockup 之一，缺口会影响整个持久经济。

建议补充 RCL1–8 upgrade cost、downgrade、attack/claim 影响、进贡资源是否永久销毁或 lockup、GCL 计算与多房间扩张关系。

5. Resource decay 默认禁用，长期存储只靠税不足以覆盖本地囤积

全局税能控制 global storage，本地存储靠风险控制。但和平后方或联盟腹地可能低风险无限囤积。若默认禁用 decay，需要用其他成本覆盖本地大仓库；否则本地资源会长期累积并在战争时一次性释放。

建议至少对非核心高阶资源提供默认微弱 decay，或对 Storage/Terminal 大容量启用维护费。

6. Code deployment cost 默认免费，可能削弱策略迭代的经济选择

World 默认 `code_update_cost = 0`、cooldown 5。免费热重载对上手友好，但长期 World 中代码部署没有经济权衡，顶级玩家可高频 A/B 测试与战术热切。虽然 cooldown 防 spam，但没有资源 sink。

建议 Tutorial/Arena 免费；Standard World 可保持低成本但非零，或在高频更新时递增收费，并确保相同 hash 幂等不重复扣费。

7. Fuel/CPU 经济与资源经济尚未连接

Overload 攻击目标 fuel budget，资源经济仪表盘关注 Energy。CPU/fuel 是 Swarm 的核心公平资源，但它是否是纯配额、是否可通过建筑/资源提高、是否有经济 sink/source，未在授权文档中闭合。若未来可购买/扩展 CPU，会极大影响 pay-to-win/资源优势；若不可购买，也应明确其与经济系统隔离。

## CrossCheck — 需要跨方向检查

- CX1: Empire upkeep 的 Rhai state 视图在文档中出现过“经可见性过滤”和“经济/维护类模组 global view 不受过滤影响”两种表述 → 建议 Architect 检查规则模组状态视图合同，确保维护费能看到玩家全局 rooms/drones/storage，且不泄露给玩家 WASM。

- CX2: allied transfer 免 convert 延迟可能破坏物流模型与反小号策略 → 建议 Security 检查资源转移权限、新玩家锁、同源账号组配额、联盟滥用和审计日志是否覆盖所有 player↔player 资源移动。

- CX3: Market 为 RFC 但 IDL 已暴露 `CreateMarketOrder` / `BuyMarketOrder` → 建议 API/Architect 检查 market_enabled=false 时 schema、validator、SDK 文档是否会误导玩家依赖未冻结功能。

- CX4: EconomySnapshot、全局存储排名区间、allied 经济可见性和房间边缘税率颜色可能泄露情报 → 建议 UX + Security 检查经济信息的 visibility policy 和 replay/观战暴露边界。

- CX5: `ResourceCost` 示例包含小数如 `{Energy: 0.01}`，而 IDL `ResourceAmount` 是 u32，设计又要求整数/定点数 → 建议 Architect/API 检查资源成本定点表达、舍入规则和跨平台确定性。

- CX6: PvE event seed 与 Resource Boom 全局倍率会影响世界资源总量 → 建议 Architect 检查事件系统是否有全局经济预算桶，避免 deterministic event 在高玩家密度下产生不可控 faucet。

- CX7: 建筑摧毁返还、Depot 掉落、Drain 窃取和 Fabricate 转化都会移动或释放资源 → 建议 Gameplay/Combat 检查战斗结算顺序与资源 ledger 是否可回放、不可复制、不可双花。

- CX8: AI 玩家可通过 MCP 高频读取经济指标，文档说独立配额 10/tick → 建议 Performance/Infra 检查经济查询聚合是否缓存，避免大帝国 EconomySnapshot 成为新的 per-tick 计算外部性。

## Recommended Freeze Conditions

在 R14 进入设计冻结前，建议至少补齐以下经济冻结条件：

1. 发布 Vanilla Economy Balance Sheet：统一 tick/day、source 产出、PvE 产出、维护费、税、转换损耗、spawn/build/recycle/refund。
2. 给出 1/5/20/50 rooms、20/100/500 drones 的净流量模拟目标，明确可持续与不可持续边界。
3. 定义统一 Resource Ledger，覆盖所有 faucet/sink/transfer/lockup/unlock。
4. 修正 allied transfer：默认不应无成本绕过物流/税/新玩家门。
5. 明确 PvE budget：NPC 掉落、据点、Resource Boom、Merchant/Contract 是否共享预算。
6. 明确 refund/destroy/recycle/decay 的资源去向与比例。
7. 将 Market RFC 与当前可用交易机制隔离，避免影子市场绕过经济治理。

若以上补齐，本设计可进入 CONDITIONAL_APPROVE 后的冻结准备；否则长期 World 经济仍有较高通胀和联盟滚雪球风险。
