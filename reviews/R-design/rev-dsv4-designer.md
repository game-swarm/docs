# R-design: Game Designer Review — DeepSeek V4 Pro

> 评审员：rev-dsv4-designer (DeepSeek V4 Pro)
> 视角：博弈论分析、策略深度评估、算法公平性
> 日期：2026-06-18
> 评审范围：7 份设计文档 (README / auth / engine / gameplay / modes / interface / tech-choices)

---

## Verdict: CONDITIONAL_APPROVE

设计在策略深度、信息不对称和算法公平性方面表现出色。Move-as-action 单槽设计、累进存储税、确定性种子洗牌、PvE 地理难度梯度构成了一个整体自洽的策略空间。发现 8 个关切点（1 High / 4 Medium / 3 Low），其中 G1（PvE 纯农策略的均衡破坏）和 G3（Overload 协同攻击的信息战 meta）需要设计层面明确立场。

---

## Strengths

1. **Fairness-by-Architecture（架构级公平）**
   AI agent 和人类玩家走完全相同的 WASM 路径——相同的 Fuel Metering（指令计数，非墙钟）、相同的沙箱、相同的 Deferred Command Model。不存在「AI 玩家有 API 优势」或「人类有微操优势」的结构性偏差。这是编程竞技游戏中最干净的公平性保证。

2. **Deterministic Seed-Based Randomness（确定性种子随机）**
   玩家排序使用 `Blake3(tick_number || world_seed)` 洗牌，所有随机数由 Blake3 XOF 确定性生成。这消除了「运气」成分——所有结果可回放验证。种子每 10,000 tick 轮换防止长期观察推断，是反作弊与公平性的双重胜利。

3. **Move-as-Action 单槽策略深度**
   将移动和攻击/采集/建造放在同一 action slot 中竞争，创造了有意义的战术决策：「追击还是停下攻击？」「移动一格后下一 tick 才能采集」——这不是 UI 延迟，是设计意图。相比传统 RTS 的「移动+行动」双动作模型，Swarm 的单槽设计迫使玩家在代码层面预判和批量调度。

4. **Body Part Age Modifier 的构建取舍**
   `age_modifier` 让身体部件选择不仅是 combat stats 的问题：TOUGH +100 延寿、ATTACK -80 折寿。玩家必须在「战力」和「持久性」之间权衡。Drone lifespan 的硬约束（默认 1500 tick）加上 Controller 续期硬上限（≤50% 自然增长），形成「build-and-expire」的有机循环，防止静态囤兵。

5. **Progressive Storage Tax + Superlinear Upkeep（反雪球机制）**
   累进存储税（0%→0.01%→0.05%→0.20%）和超线性帝国维护费（O(n²) rooms）构成双层反垄断设计。既保护新玩家的初期发展空间（safe_mode 500 tick + soft_launch 1500 tick），又不追求硬性公平——先入者仍保有大帝国优势，但维护成本使扩张有自然收敛点。

6. **PvE 作为地理属性**
   NPC 难度随距世界中心距离递增（Zone 1→4），玩家通过扩张自然遭遇更强 PvE。不需要「副本入口」或「排队系统」——PvE 难度是位置函数。资源据点的守卫必须被击败才能采集，使 PvE 成为领土扩张的有机部分而非可跳过的内容层。

7. **Overload Feedback Transparency（信息战设计的克制）**
   `OverloadPressure` 组件的可见性模型极好：攻击者看到自己的贡献，被攻击者只看到可见来源的贡献，不可见的攻击者不暴露。防止通过 Overload 反馈反向定位隐身单位——这在信息不对称设计中是少见的精确处理。

8. **Arena PvE Challenge 隔离沙盒**
   PvE Challenge 不影响 World 状态、不产出 World 资源、不消耗 World 资产。纯粹用于算法测试和排行榜竞争。这种「隔离沙盒」设计避免了 PvE 内容通胀破坏 World 经济。

---

## Concerns

### G1 [High] PvE 纯农策略的均衡破坏风险

**问题**：World PvE 生态层设计精心（NPC 类型、资源据点、世界事件、掉落表），但缺少确保 PvP 参与的内生激励机制。NPC 产出上限 `max_pve_output_per_tick ≤ 30%` 世界再生总量，但未限制单个玩家的 PvE 资源获取比例。

**场景**：一个选择完全避开 PvP 的玩家，在 Zone 3-4 清理 Guardian、采集富矿，可能获得与进行 PvP 的玩家相当甚至更高的资源增长率——因为 PvP 有 drone 损耗、资源消耗和机会成本，而 PvE（特别是对 AI 玩家而言）的损耗可预测且可控。

**博弈论含义**：如果 `E[PvE_profit_per_tick] > E[PvP_profit_per_tick]` 在足够多的参数配置下成立，则纯 PvE 策略将成为 dominant strategy。设计文档在反雪球合同中声明「World 模式不追求竞技公平」，但如果纯 PvE 变成了最优策略，PvP 就变成了 strictly dominated——整个 PvP 系统将变成死代码。

**建议**：
- 引入 per-player PvE reward cap：单个玩家从 NPC 获取的资源量不应超过其总资源收入的 X%（建议 40-50%），差额部分需通过 PvP 或领土控制获取
- 或者引入 Resource Decay：NPC 掉落资源在 Zone 1-2 有更高的基础价值（鼓励新玩家使用），在 Zone 3-4 有递减效应（降低纯农收益）
- 明确 World 模式的 PvP 参与是否必需，并在文档中声明：如果 PvP 是可选的，则 `soft_launch` 结束后 PvP 保护的动机是什么

### G2 [Medium] Move-as-Action 的新玩家 UX 鸿沟

**问题**：文档在 Move-as-action 的设计理由中承认「新玩家会觉得 drone 迟钝」，并声明「这是设计意图」。但没有提供从「drone 迟钝感到策略思维」的渐进式引导机制。

**场景**：来自传统 RTS（StarCraft、AoE）的玩家，习惯「右键移动 + A 键攻击」的即时反馈循环，进入 Swarm 后第一次 tick 发现「我的 drone 只移动了一格就停了」，可能在前 5 分钟内流失。

**建议**：
- Tutorial 世界提供「双动作模式」（Move 免费 + Action 独立），让玩家先体验 drone 的基本行为，再逐步过渡到标准单槽模型
- 在 Tutorial 世界中可视化「tick 边界」——让玩家看到「这一 tick 你用完了你的 action，下一 tick 才能继续」
- 在 Web UI 中引入「策略预览」功能：在部署代码前显示「你的 drone 预计在 N tick 内可以移动 X 格并攻击 Y 次」

### G3 [Medium] Overload 协同攻击的 Nash 均衡

**问题**：Overload 每 50 tick 全局冷却（同一目标，不限来源），但在此冷却内，多个攻击者可以对不同目标分别使用 Overload。如果 N 个玩家协同，可以对同一玩家的 N 个 drone 或 N 个不同系统中的目标执行 Overload 攻击。被攻击者的总 fuel 预算减少是叠加的。

**博弈论分析**：
- 单次 Overload 消耗目标 500k fuel（MAX_FUEL=10M 的 5%），下限 20%
- 如果 3 个玩家对同一目标交替 Overload（错开 50 tick 间隔），目标将在 ~250 tick 内降至 20% fuel
- 降至 20% fuel 后，玩家的 WASM 执行能力降为原来的 1/5——实际上被「信息压制」
- 防御者唯一的响应是 Fortify（清除负面状态）或主动消灭 Overload 施加者

**均衡风险**：如果 Overload + 远程骚扰成为 viable strategy，「耗尽对方计算配额」可能成为比「消灭对方 drone」更高效的手段。这创造了一个二级 meta game——「信息战」——其策略深度未在设计中充分展开。

**建议**：
- 设计中明确 Overload 的预期定位：是「骚扰手段」还是「战略压制工具」？两者的设计参数差异很大
- 考虑 Overload 的 per-player 全局冷却（而非 per-target），防止协同压制
- 或引入 Overload 的渐进抵抗：同一目标连续被 Overload 时，效果递减（每次 -100k fuel 而非 -500k）

### G4 [Medium] Arena 对称性的隐藏偏差

**问题**：Arena 模式允许玩家选择 `map_symmetry = "rotational"` 或 `"mirror"`，初始资源双方相同。但不同 WASM 代码可能适配不同地图几何——如果 player A 的代码针对「从左上开局」优化，而 player B 的代码假设「左下开局」，则旋转对称地图中两个 spawn 位置的「编码便利性」可能不同。

**场景**：地图上有某一侧的资源点更密集，或 exit 布局对特定初始位置有利。在 rotational symmetry 下，player A 的 spawn 位置可能天然适配某些 strategy，而 player B 的 spawn 位置适配另一些 strategy——这不是「公平」而是「对称但不等价」。

**博弈论含义**：如果地图的 rotational 变换改变了策略的 payoff matrix，则地图不是严格 symmetric game。Arena 的「公平性」声明需要更精确的定义。

**建议**：
- Arena 创建时支持 map_seed 预览——玩家在锁定 WASM 前可以看到 spawn 位置和初始房间的完整地图
- 或引入「双盲 spawn」：双方选定 WASM 后，随机分配 spawn 位置到对称点——任何 spawn bias 被随机化消除
- 在 Arena 创建 UI 中明确标注：「rotational 对称 ≠ 完全等价——不同 spawn 位置可能有不同的资源分布」

### G5 [Medium] World Mode 无胜利条件的长期留存风险

**问题**：World 模式声明「无胜利条件——类似 MMO 持续沙盒」。虽然提供了 GCL/RCL/PvE 里程碑等长期目标系统，但这些目标与 World 的持久性之间存在张力：如果一个玩家达到 RCL 8 + 全部 PvE 里程碑，还有什么可追求的？

**场景**：参考 EVE Online 的设计——持久沙盒的留存依赖「玩家生成内容」（政治、战争、经济操纵）。Swarm 的 diplomacy 系统（最多 5 alliance、24h cooldown）相对简单，可能不足以支撑长期的 emergent gameplay。

**建议**：
- 在设计中承认「endgame 内容生产」的挑战，并将 World 模式定位为「中期循环」（3-6 个月为一个自然周期）
- 或引入 World Reset 机制：周期性世界「终局事件」→ 文明重启 → 玩家保留部分全球成就（类似 Path of Exile 的 League 机制）
- PvE 里程碑完成后可解锁「世界级挑战」：如占领地图的特定坐标、触发全球事件链

### G6 [Low] 特殊攻击的离散启用模型

**问题**：Vanilla Ruleset 按 tier 启用特殊攻击：Tutorial/Novice = 全部禁用，Standard+ = 全部 6 种启用。存在一个从「零特殊攻击」到「六种同时可用」的跳跃，缺乏渐进式引入。

**建议**：在 Novice→Standard 之间插入一个过渡层级（或通过 world.toml 的 `[[custom_actions]]` 选择性启用），让玩家先掌握 2-3 种基础特殊攻击（如 Fortify + Disrupt）再接触更复杂的 Hack/Overload/Drain。

### G7 [Low] Drone 人格系统的市场价值声明

**问题**：文档声明「高 efficiency drone 在交易中可能溢价（尽管不影响实际性能——纯品牌/社区价值）」。这引入了一种「装饰性稀缺」——对游戏玩法无影响的属性在市场中具有交易价值。

**风险**：新玩家可能不理解 efficiency 人格的纯装饰性质，误以为高 efficiency drone 具有实际优势。文档描述中的「采集动画利落」可能被误解为「采集更快」——虽然文档声明不影响实际 tick 执行速度，但市场的存在会模糊这条边界。

**建议**：在 Web UI 中明确标注人格维度的「纯装饰」标签。或者在市场界面中过滤/降权纯装饰属性。

### G8 [Low] 跨房间移动的疲劳成本透明性

**问题**：跨房间移动成本 = 房间内路径 + 穿越出口 cost（默认 +1 fatigue）。文档没有明确这个 +1 是 per-exit 还是 per-tick（如果连续穿越多个房间），以及是否有最大连续穿越限制。

**建议**：明确出口穿越的 fatigue 消耗模型——是每次穿越 +1（即连续穿越 3 个房间消耗额外 3 fatigue），还是每 tick 最多穿越 N 个出口。这直接影响远征策略的可行性。

---

## Strategy Depth Analysis

### Strategy Space Size

Swarm 的策略空间由以下维度构成：

| 维度 | 可选范围 | 说明 |
|------|---------|------|
| Body Part 组合 | 8 种 × 50 parts max | 每个 part 有独立的 age_modifier / cost / damage / range |
| 特殊攻击选择 | 6 种（Tier1）× cooldown | 每个 drone 每 tick 只能执行一种 |
| 领土策略 | Claim / Contest / Defend | Room 状态机 5 种状态 |
| 物流模式 | A (none) / B (light) / C (hardcore) | 全球 vs 本地存储策略 |
| 外交 | neutral / allied / broken | 5 alliance 上限 |
| 代码部署时机 | code_update_window | 窗口期 vs 成本权衡 |

**Dominant Strategy 检查**：当前设计没有明显的 strictly dominant strategy。Move-as-action 强制每 tick 的局部决策不可被全局优化消除。但 G1（纯 PvE 农策略）可能在某些参数配置下成为 weakly dominant。

### Information Asymmetry Quality

**Fog of War**：默认 per-drone 视野（当前房间 + 相邻，最多 9 房间），Observer（RCL 5+）扩展。分层设计合理。

**隐藏信息**：
- 本地存储余额完全私有（敌方不知道你的真实经济实力）
- Overload 攻击来源可能不可见
- 全局存储余额部分公开（排行榜区间 + 市场挂单暴露）

**评价**：信息不对称设计优秀。隐藏的本地存储创造了 bluff/deterrence 可能性——敌方不知道你的真实防守力量，可能高估或低估你的反击能力。这是 RTS 中常见的「战略模糊性」。

### PvE + PvP 激励机制

**World 模式**：
- PvE：地理难度梯度 + 资源据点占领 + 世界事件
- PvP：领土争夺（Controller Claim/Contest）+ 资源掠夺
- 交叉：NPC 守卫的据点（必须先 PvE 清守卫，再 PvP 守据点）

**激励对齐**：PvE 和 PvP 不是互相隔离的——占领一个富矿需要先击败 Guardian（PvE），然后防御其他玩家的 Claim（PvP）。但 G1 指出这种对齐可能不强制 PvP 参与。

### Nash Equilibrium (AI-Human Parity)

在 Swarm 的规则框架下，AI 和人类玩家的 Nash 均衡不应有结构性差异——因为两者遵循完全相同的 WASM 路径和指令配额。但存在两个不对称：

1. **代码质量不对等**：AI 可能生成更高效的代码（更少指令完成相同逻辑），但 fuel metering 消除了 wall-clock 优势。这不构成结构性不公平。

2. **策略迭代速度不对等**：AI 可以在 tick 间分析回放、调整策略、重新部署。人类需要「阅读回放 → 思考 → 修改代码 → 重新编译 → 部署」——这个循环可能比 AI 慢数个量级。但这属于外部工具优势，不是引擎设计问题。

**结论**：Swarm 的规则本身在 AI 和人类之间达到局部均衡（给定相同代码，结果相同）。策略迭代速度的差异是元游戏层面的问题，不在设计文档范围内。

---

## Recommendations Summary

| # | 优先级 | 建议 |
|---|--------|------|
| R1 | Critical | 明确 World 模式 PvP 参与的必要性，设计 per-player PvE reward cap 或 resource decay 机制防止纯 PvE 农成为 dominant strategy |
| R2 | High | 提供 Move-as-action 的新玩家渐进引导（Tutorial 双动作模式→标准单槽） |
| R3 | High | 明确 Overload 的战略定位（骚扰 vs 压制），考虑 per-player 全局冷却或渐进抵抗 |
| R4 | Medium | Arena 创建时支持 map_seed 预览 + 双盲 spawn 随机化消除地图偏差 |
| R5 | Medium | 设计 World 模式 endgame 内容生产机制（世界级挑战 / 周期性终局事件） |
| R6 | Low | Novice→Standard 之间插入特殊攻击的渐进启用层级 |
| R7 | Low | UI 中明确标注 drone 人格的装饰性质 |

---

## Verdict Justification

CONDITIONAL_APPROVE：核心策略设计自洽且深度足够。fairness-by-architecture、Move-as-action、累进税制、确定性随机和 PvE 地理梯度构成了一个内在一致的策略生态系统。G1（PvE 纯农均衡破坏）是唯一需要设计层面回应的关切——如果纯 PvE 成为最优策略，整个 PvP 系统将沦为死代码。G3（Overload 信息战 meta）和 G2（新玩家 UX 鸿沟）需要明确设计立场但不应阻塞推进。其余 Medium/Low 关切可在迭代中解决。
