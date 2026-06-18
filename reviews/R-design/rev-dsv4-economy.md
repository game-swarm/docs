# R-design: DeepSeek V4 Pro 经济视角 Clean-Slate 评审

> 评审员: rev-dsv4-economy (DeepSeek V4 Pro)
> 评审日期: 2026-06-18
> 范围: 全 7 设计文档 (README / auth / engine / gameplay / interface / modes / tech-choices)

---

## Verdict: CONDITIONAL_APPROVE

经济模型设计方向正确——分层存储、累进税制、反雪球合同、完全可配置资源体系构成了坚实的经济骨架。但存在若干中等问题需要设计层面补全后方可进入 Phase 1 实现。

---

## Findings

### E1 — 默认资源体系与示例不一致 (Medium)

**位置**: gameplay.md §8.1, §8.3, §Official Vanilla Ruleset

**问题**: Vanilla Ruleset 明确声明"单一 Energy"作为默认资源，但文档中所有 body part、建筑、action cost 示例都使用 `{Energy, Crystal, Gas, Matter}` 等多资源计费。world.toml 默认配置示例（§8.3）中同时定义了 `Energy` 和 `Matter` 两种资源类型。

这导致一个歧义：Vanilla 默认世界到底是单资源还是双资源？如果所有建筑/body part 的成本表都需要多个资源列，那"单一 Energy"声明就是错的；如果真的是单一 Energy，那么多资源示例就有误导性。

**建议**: 明确 Vanilla Ruleset 的资源数量。若为单一 Energy，所有示例统一为 `{Energy: N}`；若为 Energy + Matter，更新 Vanilla Ruleset 声明并从示例中移除 Crystal/Gas 引用。所有示例中的资源成本必须与 Vanilla Ruleset 声明一致。

---

### E2 — 市场交易占位但经济模型依赖其存在 (Medium)

**位置**: gameplay.md §"经济治理合同", §8.2 resource_types (tradeable 字段); modes.md §9 Arena PvE

**问题**: 市场/交易功能被标记为"Phase 2 候选特性"，仅有 `CreateMarketOrder`/`BuyMarketOrder`/`CancelMarketOrder` 接口占位，无价格发现、撮合引擎、跨世界结算设计。然而：

- `tradeable` 字段在所有 `[[resource_types]]` 定义中存在
- Terminal 建筑（RCL 5 解锁）的存在理由就是"市场交易接口"
- `market_requires_terminal` 配置项已定义
- 全局存储的设计动机之一是"可市场交易"
- PvE 蓝图掉落（Guardian 5%）暗示了玩家间交易蓝图的需求

当前设计形成了一个经济闭环的缺口：资源可以在全局存储中积累，但没有 Phase 1 的出口（除了部署费和维护费）。如果 Phase 1 发布时市场不可用，Terminal 建筑将没有任何功能，`tradeable` 字段成为死代码。

**建议**: 要么 (a) 在 Phase 1 spec 中补充最小可行市场（固定价格 NPC 交易所——不需要撮合引擎，复杂度极低），要么 (b) 明确将 Terminal/tradeable/market_requires_terminal 全部标记为 `⏳ Phase 2 feature-disabled`，并在 Phase 1 中禁用 Terminal 建筑或赋予其替代功能（如仅作为全局↔本地转换加速器）。

---

### E3 — 累进存储税率可能不足以形成经济天花板 (Medium)

**位置**: gameplay.md §"全局存储反制机制"

**问题**: 默认税率 `[(30,0),(60,1),(85,5),(100,20)]` 按每 10 万单位 1/5/20 单位/tick 计算（"每万单位 1 单位"即 0.01%）。

以 1,000,000 容量上限为例：
- 85% 存储 (=850,000): 税率 0.05%/tick = 425/tick
- 100% 存储 (=1,000,000): 税率 0.20%/tick = 2,000/tick

一个中等帝国（5 房间, 100 drone, 50 Work parts）每 tick 采集量约 50×2 = 100 Energy/tick（假设每个 Source 2 Energy/tick）。加上 Source 再生 300/tick，一个大帝国的净流入可达 500-1000/tick。这意味着即使顶格税率 2000/tick，中等帝国也可以无限维持在 850,000 附近。

税率设计的表述也存在歧义：§"存储默认值与安全下限"规定"最高税率 ≥ 0.10%/tick"，但 §"累进存储税"表格显示 85-100% = 0.20%。两处对"最高税率"的理解不一致——前者似乎是安全下限，后者是默认值。

**建议**: 
1. 统一"最高税率"的定义——明确是默认值（建议提升至 ≥0.50%/tick 以提供有效天花板）
2. 补充分段税率的经济模拟数据：证明默认参数下，不同规模的帝国在稳态时的存储均衡点
3. 考虑引入绝对上限（hard cap）作为税率失效时的安全阀

---

### E4 — 资源转换途中缺少 PvP 拦截机制定义 (Low)

**位置**: gameplay.md §"全局反制机制" #3; auth.md §13.1 in-transit handling

**问题**: gameplay.md 声明"运输期间资源处于'运输中'状态——可被敌方巡逻 drone 拦截（需 PvP 启用）"，但未定义：
- 拦截的触发条件（需要什么 action？Attack？特殊 action？）
- 拦截成功后的资源去向（归拦截者？丢弃？）
- 运输路线是否对敌方可见
- 如何判定"巡逻"（drone 恰好经过运输路径？）

Auth.md §13.1 对账号删除时的 in-transit 资源处理有明确定义（取消、退回、回滚），但正常的 PvP 拦截机制完全缺失。

**建议**: 补充 in-transit 资源的 PvP 拦截 spec，至少定义：
- 拦截 action 类型（建议复用 Attack 或新增 Intercept action）
- 资源分配规则（建议拦截者获得 50%，其余丢弃）
- 可见性规则（运输路线仅对 allied/own 可见）

---

### E5 — 代码部署零成本削弱经济决策权重 (Low)

**位置**: gameplay.md §8.2 代码部署规则; engine.md §3.2 WASM 预编译

**问题**: World 模式 `code_update_cost` 默认值为 0（免费）。虽然存在 5 tick 最小间隔，但零经济成本意味着：
- 玩家可以频繁切换策略而不付出任何代价
- "commit to a build" 的策略深度被消除
- 与 "你的代码就是你的军队" 哲学存在张力——如果代码可以免费换，那代码本身的决策就不够重量级

与 Screeps 的对比：Screeps 中代码更新需要 CPU 成本（代码从 Spawn 传播到 drone 需要时间），免费部署降低了策略承诺的严肃性。

**建议**: 将 World 模式默认 `code_update_cost` 设为非零值（建议 `{Energy: 100-500}`），Arena 模式保持免费（赛前锁定）。若坚持免费，在文档中记录设计理由。

---

### E6 — PoW 注册经济壁垒接近零 (Low)

**位置**: auth.md §9.2 难度参数; gameplay.md §"PoW 经济治理"

**问题**: difficulty_bits=24 的 PoW 耗时约 150ms（Rust）/ 1.5s（WASM）。经济成本约 $0.0001/次（CPU time）。每 1000 账号攻击成本仅 ~$0.10。这意味着：

- 注册本身几乎免费——不构成经济壁垒
- 真正的反滥用依赖 IP 限速（10/min per IP 的 challenge 申请）
- 攻击者使用 IP 轮换可以绕过年成本极低的批量注册（10000 账号 ≈ $1）

对比文档自身的估算："每 1000 账号攻击成本 ~$0.10（最低）仅 CPU，不含 IP 限流"——这个数字本身就说明了 PoW 不作为独立经济壁垒。

**建议**: 
1. 在文档中明确 PoW 的角色定位——是"速率阻尼"而非"经济壁垒"
2. 补充注册后的行为经济壁垒（如新账号初始资源限制、soft_launch 期间的行动限制），这些已在 gameplay.md 中设计但未与 auth PoW 关联论述
3. 考虑登录 PoW 默认开启（当前默认 false）

---

### E7 — AI agent 经济信息不对称 (Low)

**位置**: interface.md §4.1 MCP 工具; gameplay.md §9.4 玩家经济反馈

**问题**: MCP 提供 `swarm_get_economy`、`swarm_get_drone_efficiency`、`swarm_get_economy_trend` 三个结构化经济查询工具，AI agent 可编程访问。人类玩家只能通过 Web UI 仪表板读取相同信息。

虽然信息内容相同，但 AI agent 可以通过编程方式批量分析、跨 tick 趋势计算、自动优化——这些对人类玩家而言需要额外开发工具或手动分析。

这不是设计缺陷（MCP 是 AI 的原生界面，提供结构化数据是合理的），但应在公平性声明中注明：经济数据的可编程访问是 AI 玩家的合理优势，人类玩家可通过 SDK 或社区工具弥补。

**建议**: 在 gameplay.md §9.4 或 README 设计原则中，添加关于 AI/人类经济信息对称性的简短声明。

---

### E8 — Drone 人格经济价值未经定义 (Low)

**位置**: gameplay.md §9.1 Drone 人格系统

**问题**: §9.1 声明"高 efficiency drone 在交易中可能溢价（尽管不影响实际性能——纯品牌/社区价值）"。这引入了两个未解决的问题：

1. 人格种子是确定性的（Blake3 hash），玩家无法"培育"高 efficiency 人格——这意味着溢价市场没有供给侧经济学基础（供给完全随机）
2. 市场交易本身是 Phase 2 特性——人格溢价讨论为时过早

此外，"efficiency" 人格维度的命名具有误导性——名为"efficiency"但明确不影响实际性能，新玩家可能产生混淆。

**建议**: 
1. 将人格的人格溢价讨论移至 Phase 2 market spec
2. 考虑将 "efficiency" 维度重命名为 "style" 或 "demeanor" 以避免混淆

---

## Strengths

1. **分层存储模型（全局↔本地）设计优秀**。三层物流模式（无物流/轻物流/硬核物流）覆盖了从休闲到硬核的全谱系玩家，且传输损耗（1%/5%）和延迟（10/5 tick）创造了真实的物流决策空间。这是整个设计中最成熟的经济机制。

2. **累进存储税 + 本地存储隐匿性 + 无瞬移补给** 的三位一体反垄断设计。不是简单的"收税"，而是通过信息不对称（本地存储私有）和物流约束（转换需时间）创造了策略纵深——囤积全局存储 vs 隐藏本地实力的张力是优秀的经济博弈设计。

3. **反雪球合同完整且克制**。不追求竞技公平（World 本质不对称），但通过存储税、维护费、Controller 老化、soft_launch、安全区出生、SpawnGrace 等多层机制保护生态可持续性。每个机制的参数都可配置，服主有充分的调参自由度。

4. **资源体系完全可配置**。引擎核心不硬编码 Energy——所有操作通过 `HashMap<ResourceName, Amount>` 处理，资源类型、数量、衰减率、可交易性全在 world.toml 定义。这为经济模组生态奠定了坚实基础。

5. **NPC PvE 经济约束（max_pve_output_per_tick ≤ 世界再生总量 × 30%）** 防止了"刷怪经济"压倒 PvP 战略价值。这是容易被忽视但重要的设计——很多 MMO 的 PvE 经济会自然通货膨胀。

6. **Fuel metering 跨语言公平**。WASM 指令计数而非墙钟 CPU 计量，确保 C 玩家和 Python 玩家在相同配额下获得同等算力。这是编程竞技游戏的核心公平性保证。

7. **Drone 回收 50% 退还**。在不可逆 body plan（一旦 spawn 不可修改）的约束下，50% 回收率提供了合理的经济容错——既不鼓励频繁重组（有成本），也不惩罚试错（有退还）。新手 Tutorial 100% 退还更是优秀的新手引导设计。

8. **Controller/Depot 双层维修经济**。Controller 免费但容量有限、Depot 消耗资源但可前线部署——创造了"在哪里部署维修节点"的经济地理决策。Depot 的可占领属性进一步增加了 PvP 经济维度。

---

## Recommendations

1. **补充资源 sink 多样性分析**（关联 E2/E3）。当世界达到稳态（max drones + max buildings）后，除累进存储税外缺乏其他资源出口。考虑在 Phase 2 之前，至少设计 1-2 个 Phase 1 可用的资源 sink（如 Controller 加速升级消耗、Tower 弹药消耗、drone 涂装/人格重 roll）。

2. **定义 Vanilla 经济的平衡目标**。当前文档只给出了参数默认值，但没有说明这些默认值对应的经济平衡目标——例如"一个中等帝国（5 房间）需要多少 tick 达到稳态？稳态时 drone 数量预期是多少？"这些数值不需要精确，但应作为设计意图记录下来，供 playtest 调参参考。

3. **补充经济治理的运维手册条目**。当前 RUNBOOK.md 在 README 中被引用但内容未知。建议确保运维手册包含经济紧急操作（全局税率临时调整、资源池注入/回收、市场熔断），以应对经济异常（刷钱 bug、恶性通货膨胀）。

4. **efficiency_benchmark MCP 事件的隐私考量**（关联 E7）。`efficiency_benchmark` 事件向 AI agent 暴露"代码在最近 100 tick 中效率低于世界 P50"的信息。这个 P50 基准需要保护——不应通过此事件反向推断其他玩家的经济状况。建议 P50 计算使用差分隐私或粗粒度分桶。

5. **Federation 经济隔离声明显式化**。当前文档在 federation 部分声明了资产隔离，但 economic 视角的完整声明不足：跨世界没有资源转移、没有汇率、没有共同市场。建议在 gameplay.md 经济模型开头添加一句明确声明。

---

## Consistency Gaps

| 位置 A | 位置 B | 不一致 |
|--------|--------|--------|
| gameplay.md Vanilla Ruleset: "单一 Energy" | gameplay.md §8.3 world.toml 示例: 定义了 Energy + Matter 两种资源 | 默认资源数量矛盾 |
| gameplay.md §存储默认值: "最高税率 ≥ 0.10%/tick" | gameplay.md §累进税率表: 85-100% = 0.20% | 最高税率的定义不同——前者是安全下限，后者是默认值 |
| gameplay.md: Leech/Fabricate 在 Tier 1 `[[custom_actions]]` 预注册中定义 | engine.md Tier Entry Gate: Leech/Fabricate 标记为 Tier 2+ | Leech/Fabricate 的 Tier 归属不一致——engine.md 说 Tier 2+，gameplay.md 的默认 world.toml 示例却预注册了它们 |
| auth.md §13.1: 账号删除时 in-transit 资源有完整处理 | gameplay.md §反制机制 #3: in-transit PvP 拦截无定义 | in-transit 语义不完整——删除路径有 spec，PvP 路径缺失 |

---

## Algorithmic / Economic Risks

1. **累进税率的稳定性风险**。如果大量玩家恰好在税率分界线附近（如 30% 容量），微小的资源波动会导致税率在 0% 和 0.01% 之间振荡。建议在税级边界实施迟滞（hysteresis）——跨越上线需要超过 2% 余量。

2. **Controller 维修 50% 硬上限的死锁风险**。如果玩家的所有 Controller 都被摧毁，正在前线的 drone 无法返回维修。此时 drone 只能等死，无法自救。虽然这是设计意图（"断补给=死亡"），但新手可能不理解为什么 drone 在 Controller 范围内却没有维修——需要 UI/反馈层面清晰说明维修容量已满。

3. **经济数据可回放性**。所有经济操作（资源扣除、transfers、market orders）必须写入 TickTrace 以保证审计。当前设计声明了这一点（TickTrace 包含完整状态），但需确保经济操作的 granularity 足够——如果 TickTrace 只记录净变化而非每笔交易，将无法追溯经济 bug。

---

## Summary

经济视角给予 **CONDITIONAL_APPROVE**。3 个 Medium 问题（E1-E3）和 5 个 Low 问题（E4-E8）需要在设计层面解决。最关键的三个行动项：

1. **统一默认资源体系**（E1）——消除 Vanilla Ruleset 声明与示例的矛盾
2. **决定市场 Phase 1 策略**（E2）——要么提供最小可行市场，要么禁用相关建筑/字段
3. **验证累进税率经济效果**（E3）——确保默认参数下存在有效的经济天花板

经济模型的结构设计（分层存储、反垄断、完全可配置）质量很高，当前问题集中于参数校准、占位功能的处理、以及边界情况的 spec 完备性——这些都是设计阶段可修复的。
