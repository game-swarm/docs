# Swarm R2 设计评审 — Game Designer 视角 (DSV4)

Reviewer: rev-dsv4-designer (DeepSeek V4 Pro)
Task: t_528c60ca / review-R2-designer-dsv4-v2
Date: 2026-06-16
Scope: DESIGN.md (2300行), specs/01-09, ROADMAP.md, R2 rev-gpt-designer, R2 rev-dsv4-architect, R2 rev-claude-architect
Perspective: 博弈论分析、策略空间深度、信息不对称设计、PvE+PvP 激励机制、纳什均衡、Algorithmic Fairness

---

## Verdict

**APPROVE_WITH_RESERVATIONS** — 与 GPT Designer 的 CONDITIONAL_APPROVE 同向，但关注点不同。

R2 设计在博弈论维度上已确立了对的策略骨架：WASM 对称性消除 AI/人类特权博弈、Overload 的 visibility 约束和全局冷却堵上了信息泄露攻击面、累进存储税提供了反垄断机制。核心公平性合同成立。

但作为 DSV4 视角，我从策略深度和机制设计角度发现以下结构性弱点：(1) World 模式 PvE+PvP 共存缺乏激励梯度设计，可能退化到纯 PvP 或纯 PvE；(2) 特殊攻击矩阵存在「Fortify 纳什陷阱」——最优策略可能退化为全员 Fortify spam；(3) 信息不对称（fog-of-war）的策略价值被浪费——当前设计仅提供「隐藏资源」一层博弈，缺少侦察/反侦察的策略树深度；(4) Overload 攻击在信息不对称下存在概率性推断漏洞——即使静默返回，攻击者可通过间接观测推断目标 fuel 状态。

**关键判断**: 核心 WASM/tick/visibility 骨架正确，可从博弈论角度证明公平性。但策略空间缺乏必要维度的深度——在当前设计下，World 模式的长尾玩家行为预测显示「采集-建造-防御」循环可能在 30 天内收敛到少数 dominant strategies。需在 R3 或 Phase 1 补充策略多样性机制。

---

## Strategy Depth Analysis

### 策略空间维度评估

当前 R2 设计定义的策略空间：

| 维度 | 选项数 | 深度评价 |
|------|-------|---------|
| 身体部件组合 | 8 种部件，单 drone 最多 50 parts | 高 —— 8^50 组合空间，但实际受 cost/lifespan 约束，约 10^4 可行组合 |
| 8 种特殊攻击 | 每 drone 选择 0-8 种 | 高 —— 但存在 Fortify 纳什陷阱（见 G2） |
| 物流模式 A/B/C | 3 种 | 中 —— 由世界规则决定，非玩家选择 |
| 全局存储策略 | 囤积/本地隐匿/频繁转换 | 中 —— 累进税提供反制 |
| 经济策略 | 采集型/贸易型/劫掠型 | 中 —— 但 PvE 世界缺乏劫掠激励 |
| 信息策略 | 侦察/隐蔽/反侦察 | 低 —— 当前侦查手段仅 drone 视野（range 3） |
| 长期 vs 短期 | lifespan 管理 / Controller 维修 | 中 —— age/lifespan 机制增加了时间维度 |

**总体策略空间**: 约 10^6-10^8 个有意义的策略组合。对单局 RTS 足够，但对持久 MMO 可能偏浅——玩家在 30 天内收敛到 Pareto 前沿的 10-50 个策略后，meta 将固化。

### Dominant Strategy 分析

#### 潜在 Dominant Strategy 1: Fortify Spam

```
组合: Tough × N + Attack × M, M ≪ N
策略: 每 300 tick 对所有前线 drone 施放 Fortify
      Fortify 同时提供: 抗性×0.5 + 清除所有负面状态
      负面状态包括: Hack 控制锁、Drain 资源流失、Debilitate 易伤、Overload fuel 效果
```

**为什么接近 Dominant**: 
- Fortify 的「清除所有负面状态」使它成为万能解药——它 counter 了 4/8 的特殊攻击
- 300 tick CD 是所有特殊攻击中合理的，但配合 drone 轮换（3 drone 交替 Fortify）可实现 100 tick 间隔的全覆盖
- 资源消耗 400 Energy 相对 Hack(1000)/Overload(300)/Drain(200+持续) 并非劣势

**反制策略缺失**: 
- 没有「禁疗」机制——无法阻止 Fortify 的净化效果
- Disrupt 可打断 Fortify 施放，但 Disrupt 需要近身（range 1），Fortify 也可在安全距离施放
- 当前 meta 下，不 Fortify 的玩家面对 Fortify + 攻击混合编队时处于严格劣势

**设计建议**: 
- 引入「污染」效果——阻止净化直至污染被清除（新增 counterplay 链）
- 或让 Fortify 仅提供护盾（抗性），净化功能移至独立 action `Purge`（强制选择：防护 vs 净化）
- 或增加 Fortify 的受击中断规则——被攻击时 Fortify 施放中断

#### 潜在 Dominant Strategy 2: 全采集 + 龟缩防御

```
策略: 最大化 Work+Carry drone → 快速积累资源 → 建造 Tower 矩阵
      不主动进攻，仅防御。利用 Tower auto-attack (50 dmg) + Fortify 守住
      在 World 模式下这是理性策略——进攻的风险/回报不对称。
```

**为什么在 World 模式接近 Dominant**:
- 进攻成本高：需要远程补给线、Controller 维修链、Overload/Drain 特殊 attack drone
- 防御成本低：Tower 自动攻击（50 dmg, range 3, 充能后 6）、Fortify 全员覆盖
- 进攻失败惩罚高：远征 drone 全灭 → 资源全损 + Controller 维修压力 + 补给线断裂
- 进攻成功回报不确定：占领敌方房间的价值取决于敌方已投入的建设（可能已被摧毁）

**World 模式 PvP 的期望值不对称**:
```
E[进攻] = P(成功) × (掠夺资源 + 占领房间价值) - (1-P(成功)) × (远征成本 + 补给线损失)
E[防御] = 零边际成本（Tower 已在位）+ Fortify 400 Energy/drone/300 tick

当 P(成功) < 0.7 时，E[进攻] < E[防御] —— 龟缩是理性选择。
实际 P(成功) 受 Tower 50 dmg + Fortify 减伤影响，可能 << 0.5
```

**这会导致 World 模式退化为「谁先占坑」+「无限积累」游戏，而非动态战争**。

**设计建议**:
- 引入资源衰减（已有 `decay_rate` 但默认 0）——使囤积有成本，推动资源循环
- 引入「掠夺奖励倍率」——成功入侵获得额外 bonus（如摧毁 Tower 获得资源掉落 +50% 倍率）
- Tower 攻击受「充能」限制——Tower 在连续攻击 N tick 后需要充能窗口，创造进攻窗口
- 引入「领土价值衰减」——长期不扩张的殖民地面临递增维护费（已在 empire-upkeep 模组中有了雏形，但默认值保守）

### 纳什均衡分析：World 模式下人类 + AI 共存

假设 World 模式有以下玩家类型：
- **Type H (Human)**: 有限理性，受编程能力和时间约束
- **Type A (AI agent)**: 近似无限理性，可 24/7 优化策略

**当前设计的隐含均衡**:

```
假设:
- 资源有限（source capacity 3000, regen 300/tick per room）
- 玩家数量 > 资源承载力的房间数
- AI 玩家可全天候优化，人类玩家每天 2-4 小时

结果:
1. AI 玩家在资源采集效率上占绝对优势（24/7 优化 vs 每天数小时）
2. AI 玩家可能形成「资源卡特爾」——多家 AI 协同定价、垄断高价值房间
3. 人类玩家退守新手保护区（safe_mode 500 tick）或放弃 World 模式
4. 最终均衡: World 模式成为 AI vs AI 战场，人类仅在 Arena 模式竞争
```

这**不一定是坏事**——如果设计意图就是 World = AI playground + Arena = Human competition。但当前文档未明确这一分层，可能导致人类玩家进入 World 后的挫败感。

**设计建议**:
- 明确 World 和 Arena 的玩家预期：World 标记为 "AI-native, human-optional"；Arena 标记为 "Human & AI, fair start"
- World 模式引入「AI 可见性标签」——玩家加入前看到该世界的 AI 玩家密度
- 考虑 World 模式的「Novice Island」机制——新玩家自动分配到低 AI 密度的新手大陆

### 信息不对称的策略深度

当前 fog-of-war 设计提供了以下信息博弈层次：

| 层次 | 机制 | 策略深度 |
|------|------|---------|
| 资源隐藏 | 敌方本地存储不可见 | 中 —— 影响「进攻时机」决策 |
| 位置可见 | 视野内敌方 drone/建筑可见 | 低 —— 仅决定「看到才打」 |
| 身体部件可见 | 敌方 drone body parts 可见 | 中 —— 影响 counter 选择 |
| 意图不可见 | 敌方代码/指令/冷却/策略隐藏 | 高 —— 但无法主动侦察 |

**缺失的策略维度**:

1. **侦察深度不足**: drone 视野固定 range=3（或 Tower range=6），无主动侦察机制（如 Scout drone、Spy drone、卫星扫描）。玩家无法获取远程情报——所有决策基于局部视野。这降低了战略层面的信息博弈。

2. **反侦察机制缺失**: 无隐身、伪装、或迷惑敌方侦察的手段。敌方能看到的 = 你存在的全部。无法实施「佯攻」「伏击」「隐形运输」等基于信息不对称的策略。

3. **信息时效性**: fog-of-war 是二元的——要么看到，要么看不到。没有「过期信息」概念——你 10 tick 前离开的房间，信息立即清零。但现实中侦察信息有衰减曲线——「5 分钟前的侦察报告」仍有部分价值。

**设计建议**:
- Phase 2+ 引入侦察 body part（如 `SCOUT`：范围 10，无攻击能力，低 lifespan）
- 引入信息时效性：未持续侦察的房间显示「最后更新时间」和模糊信息（如「估计 5-15 drone」）
- 引入反侦察手段：Camouflage mod、Decoy drone、Fake building blueprint

---

## Strengths

### S1 — WASM 对称性在博弈论上是「强公平」

DESIGN §1.1 §4 的「世界只认 WASM」不仅是一个架构决策——它在博弈论上创建了 Type I（人类）和 Type II（AI）之间的**信号不可区分性**（Signaling Indistinguishability）。引擎无法从 WASM 字节码推断作者是人类还是 AI。这使得两类玩家处于同一博弈树的同一节点上——不存在基于类型的策略特权。

这是 GPT Designer 的 S1 的博弈论强化版本。它不仅「社区心理正确」，而且**数学上正确**——消除类型不对称是机制设计的基础条件。

### S2 — 累进存储税 + 本地隐匿性构成「隐性反制」

DESIGN §8.2 的累进存储税（0%/0.01%/0.05%/0.20%）配合本地存储隐匿性，是一个精巧的隐性反垄断机制：它不直接禁止囤积，而是使囤积在超过临界点后产生递增成本 + 信息暴露风险（挂单时暴露部分余额）。这在博弈论上是**分离均衡**（Separating Equilibrium）——理性玩家会自我选择：小规模囤积（<30%容量）vs 大规模流通（缴税+暴露）。

这个设计比「硬上限」更优雅——它尊重玩家选择，同时通过成本梯度引导行为。

### S3 — Drone Lifespan 是「时间维度策略」

Drone 的 `age + lifespan（默认1500 tick，约75分钟）`创造了博弈论上的**finite horizon problem**——每架 drone 有有限生命，玩家必须规划其整个生命周期的效用。这比传统 RTS 的「单位永久存活」增加了更丰富的策略选择：

- **Early-game drone**: 低成本短寿命（多装 Attack -80 age），rush 战术
- **Late-game drone**: 高成本长寿命（多装 Tough +100 age），持久防御
- **Suicide drone**: 在 lifespan 最后 50 tick 发起高风险突袭
- **Recycle timing**: 在 lifespan 50% 时回收（退还 50% 资源）vs 用到 100% 自然死亡

Body part age_modifier 机制是 R2 最被低估的创新——它在一个看似静态的策略空间中植入了时间动态。

### S4 — Overload 的 Visibility 约束修复 == 关键信息通道闭合

R2 对 Overload 的三项约束（`is_visible_to`、per-target 50 tick 全局冷却、静默返回）在博弈论上是正确的信息通道管理。R1 版本的 Overload 有三条信息泄露通道：

| 信息泄露通道 | R2 修复 |
|-------------|--------|
| 攻击不可见玩家 → 通过效果推断存在 | ✅ 必须 `is_visible_to` |
| 攻击结果（成功/失败）→ 推断 fuel 状态 | ✅ 静默返回 |
| 多攻击者轮流 Overload → 推断 fuel 恢复速率 | ✅ per-target 全局冷却 50 tick |

第三条仍然存在残余风险（见 G3），但前两条已正确闭合。

### S5 — Controller/Depot 维修共享硬上限是资源分配博弈

Controller 维修硬上限（每 tick 总 age 回退 ≤ 自然增长的 50%）配合 Depot 维修（消耗存储资源，range=1），创造了一个资源分配博弈：

```
决策: 把维修资源投给哪些 drone？
- 前线 drone：高价值但维修窗口短（需在 Depot range 内）
- 采集 drone：低价值但维修频繁（永在 Controller range 内）
- 相邻格只有 6 个——维修容量有限，形成排队博弈
```

这个排队模型在博弈论上类似**多臂老虎机问题**（Multi-Armed Bandit）——玩家需要在不确定的回报下分配有限的维修槽位。这是 R2 设计中有真正策略深度的机制之一。

---

## Concerns

### G1 — High — World 模式 PvE+PvP 共存缺乏激励梯度设计

DESIGN §9 声明 World 模式「PvE + PvP 共存」「人类和 AI agent 在同一世界共存」，但没有定义**激励梯度**——玩家从纯 PvE 过渡到 PvP 的动力是什么？什么推动玩家冒 PvP 风险？

当前设计下，PvP 的 risk/reward 不对称（见策略分析 §Dominant Strategy 2）使得「龟缩 PvE」是严格占优策略。除非设计注入以下激励之一：

```
a) 边际收益递减: 纯 PvE 的经济增长曲线在 RCL 5+ 后趋平
b) PvP 独占奖励: 占领敌方房间获得独特资源（如 Artifact、Blueprint）
c) 领土压力: 房间数量超过阈值后维护费非线性增长（empire-upkeep 已有）
d) 动态威胁: AI 驱动的 PvE 入侵（scripted raid）迫使所有玩家建立防御
e) 资源稀缺: 高质量资源点有限，后入者只能通过 PvP 获取
```

当前 `empire-upkeep` 模组提供了 (c)，但其默认值保守（drone_cost=2, room_superlinear=1），在小帝国（5 房 100 drone）时维护费仅 275/tick——难以推动 PvP 行为。建议:
- 在文档层面定义 World 模式从「纯 PvE→PvE 为主→PvP 出现→全面竞争」的演进路径
- 通过世界配置提供 preset：`Novice World`（仅 PvE）、`Standard World`（PvE + 轻 PvP）、`Hardcore World`（full PvP）
- `pvp_enabled` 不应是 bool，而应是 enum: `disabled | defensive_only | contested_zones | full`

### G2 — High — 特殊攻击矩阵存在 Fortify 纳什陷阱

8 种特殊攻击的成本/收益/冷却矩阵分析：

| 攻击 | Cost | CD | 效果类型 | 被 Fortify 反制？ |
|------|------|----|---------|-----------------|
| Hack | 1000E | 200 | 控制夺取 | ✅ 净化控制锁 |
| Drain | 200E/tick | 50 | 资源窃取 | ✅ 清除持续效果 |
| Overload | 300E | 200 | Fuel 消耗 | ✅ 清除效果（？见注） |
| Debilitate | 200E | 150 | 易伤 ×2 | ✅ 清除负面状态 |
| Disrupt | 100E | 50 | 打断动作 | ❌ 但 Fortify 已预防 |
| Fortify | 400E | 300 | 护盾+净化 | — |
| Leech | 300E | 0 | 吸血 50% | 取决于 Fortify 抗性 |
| Fabricate | 2000E+500M | 500 | 转化建筑 | 取决于 Fortify 抗性 |

Fortify 同时 counter 了 Hack/Drain/Overload/Debilitate 四种攻击（通过净化），并提供了全抗性 ×0.5 护盾。在当前 meta 下：

1. 进攻方选择 Hack/Drain/Overload/Debilitate → 防御方 Fortify → 攻击效果清零，进攻方消耗资源
2. 进攻方选择 Leech/Disrupt → 防御方 Fortify → 伤害减半，但至少有效果
3. 进攻方选择 Fabricate → 防御方 Fortify → 转化成功率降低（抗性），但成本极高

**纳什均衡分析**: 在双方都了解 meta 的情况下，最优策略是：每方都 Fortify 覆盖率最大化 + 仅使用 Leech/Disrupt 作为攻击手段。这导致 meta 退化为 2-3 种攻击，8 种矩阵的价值浪费 60%。

**Ongoing Overload 效果的 Fortify 交互未定义**: DESIGN §8 表格中 Overload 是即时效果（reduce fuel 500k），但 Fortify 描述为「清除目标所有负面状态」。已发生的 fuel 减少是否算「负面状态」？如果是（fuel 低于正常水平 = 负面状态），Fortify 可能成为 fuel 恢复手段——这大大改变了 Overload 的价值主张。

**设计建议**:
- 定义 Overload 的 fuel 减少是「永久效果」（不被 Fortify 逆转）还是「负面状态」（可净化）
- 如 Fortify 净化 Overload，Overload 的价值降低至仅限「Fortify 窗口外」（每 300 tick 有 ~100 tick 窗口）
- 拆分 Fortify 为两个独立 action：`Fortify`（仅护盾）+ `Purge`（仅净化），让玩家选择而非同时获得
- 或为净化引入资源成本——`Purge` 消耗与净化的负面效果数量成正比

### G3 — Medium-High — Overload 静默返回仍有间接信息泄露路径

R2 修复了 Overload 的直接信息泄露（「你的 Overload 成功了吗？」不再有返回码）。但间接信息泄露仍然存在：

**通过实体状态变化推断**:
```
攻击者施放 Overload → 等待 1-2 tick → 观察目标 drone 行为：
  - 目标 drone 继续活跃提交指令 → fuel 仍 > 20% 下限 → Overload 效果 ≤ 已执行但未达下限
  - 目标 drone 停止提交指令 / 进入 idle → fuel < 20% 下限 → Overload 可能触发了下限
  - 目标 drone 行为无变化 → fuel 充足 / Overload 被 Fortify 净化
```

这种推断虽然噪声大（drone 停止提交指令可能有多种原因），但在多次测量中可通过统计方法收敛。这在博弈论上是**信号博弈**（Signaling Game）——攻击者接收不完美的信号，但随着信号样本增加，信息不对称逐渐缩小。

**设计建议**:
- 引入「fuel 噪声」——`swarm_profile` 和外部观察中的 fuel 指标添加随机抖动（±5%），使统计推断不可靠
- 或显式定义 Overload 的「可观测效果」——不是静默，而是固定返回一个标准化的「防御状态」值（无信息量）

### G4 — Medium — 资源运输的 10 tick 延迟 + 可拦截缺乏明确的产品化

DESIGN §8.2 的「全局↔本地转换需 N tick」是一个有策略深度的设计——它使全局存储不能作为战斗中的即时补给。结合「运输期间可被敌方巡逻 drone 拦截」的规则，这应成为一个高策略价值的物流博弈机制。

但当前文档对此机制的描述过于技术化（「transfer_to_global_time = 10」），缺乏游戏化表达：
- 玩家如何知道自己的资源正在运输中？UI 提示？
- 敌方如何看到运输中的资源？需要侦察 drone 在运输路径上？
- 拦截的收益是什么？100% 获取？部分获取？
- 运输路径是如何决定的？最短路径？可视路径？

**设计建议**: 
- 将「运输中」可视化为地图上的资源流线（类似 Factorio 的传送带概念，但抽象化）
- 定义 Transport Intercept 的博弈论模型：拦截成功率 = f(巡逻 drone 数量、速度、路径覆盖)
- 这可以是 Swarm 区别于其他 RTS 的差异化特征——**代码驱动的物流战争**

### G5 — Medium — Vanilla 默认值未对齐博弈论最优

查看 §8.4 的 Vanilla Ruleset 核心默认值表：

| 规则 | 默认值 | 博弈论评估 |
|------|-------|----------|
| 资源 | 单一 Energy | 简化合理，但降低了 counter 链深度 |
| 身体部件 | 8 种全部 | 合理 |
| 伤害类型 | 6 种全部 | 与 8 种身体部件正交，策略空间 OK |
| 物流模式 | B（轻物流） | B 是折中方案，但未提供 A/B/C 之间的推荐场景 |
| 特殊攻击 | **全部 8 种可用** | ❌ 过宽（GPT Designer G4 也指出） |
| Controller 维修 | 上限 50% | ✅ 合理，提供策略张力 |
| fog_of_war | true | ✅ 正确 |

**关键问题**: Vanilla 默认同时打开 8 种特殊攻击 + 6 种伤害类型，对新手认知负载过高，对 meta 建立不利。在博弈论上，新游戏的前 3 个月是「meta 探索期」——如果初始 meta 空间太大，玩家无法收敛到可理解的策略，导致流失。

建议 Vanilla 分层（与 GPT Designer G4 一致但以博弈论角度补充理由）:
- Tutorial Vanilla: Move / Work / Carry / Attack / Heal / Tough + Spawn / Extension / Tower / Storage（0 特殊攻击）
- Novice Vanilla: + Disrupt / Fortify（2 种特殊攻击，构成基础 counterplay 链：Disrupt ↔ Fortify ↔ Attack）
- Standard Vanilla: + Overload / Hack / Drain（5 种，完整的进攻三角）
- Advanced: + Debilitate / Leech / Fabricate（8 种全开）

这种分层的博弈论理由是：**在受限策略空间中，玩家能更快找到纳什均衡并建立共享认知**。当 meta 固化后再扩展，每个新机制都成为「meta 扰动」而非「噪音」。

### G6 — Low-Medium — Arena 赛前 precommit 窗口未定义策略锁定粒度

DESIGN §9 Arena 定义「代码在比赛开始时锁定」。但未定义：
- 锁定的是整个 WASM 模块？还是可以保留多个 module 在赛中切换？
- 如果可切换，AI 玩家可能预编译 100 个对抗性 module，赛中按对手行为切换——这改变了「锁定」的含义
- 如果不允许切换，人类玩家如何 experiment？赛中调整策略是 RTS 的核心乐趣之一

**设计建议**:
- Arena 提供三种锁定模式：
  - `full_lock`: 1 个 module，赛中不可切换（纯策略对决，类似围棋）
  - `pool_lock`: 预注册 3-5 个 module，赛中可在 module 间切换（有切换成本/冷却）
  - `open_dev`: 赛中可随时部署新 module（但部署有 cooldown + cost）
- 不同 league 使用不同模式——Novice 用 pool_lock，Tournament 用 full_lock，World 永远 open_dev

---

## Cross-Reference to GPT Designer Review

GPT Designer (t_e489346d) 已覆盖以下领域，本评审不重复：
- G1: First Hour 情绪/认知曲线
- G2: AI MCP curriculum 可判定课程图
- G3: Progressive Reveal 产品入口
- G6: Replay 传播包装
- G7: World 长期身份与非零和荣誉
- G8: Spectator config 示例与约束不一致
- G9: Direction enum 六边形 vs 方形
- G10: 失败恢复循环情绪化

本评审与 GPT Designer 的关系：**互补而非重复**。GPT 关注「产品化」和「用户体验闭环」，DSV4 关注「博弈论正确性」和「策略深度」。两者共同构成完整的 Designer 视角。

**与 GPT Designer 一致点**:
- Vanilla 范围过宽（GPT G4 ↔ DSV4 G5）
- 资源默认值过于简化（GPT 隐含 ↔ DSV4 显式分析）
- Fortify 交互需要明确（GPT 未提及，但 G2 可能与 GPT 达成共识）
- Arena 产品化不足（GPT G5 ↔ DSV4 G6 补充角度）
- 物流拦截需要产品化（GPT 未涉及 ↔ DSV4 G4 提出）

**与 GPT Designer 差异点**:
- GPT 要求 First Hour Journey → DSV4 要求 Strategy Depth Progression（分层 meta 探索）
- GPT 要求 Replay 产品包装 → DSV4 要求 Information Asymmetry 博弈深度
- GPT 要求 Long-term Identity → DSV4 要求 PvE→PvP 激励梯度

---

## Missing

以下是从策略深度/博弈论角度缺失的设计元素：

1. **World PvE→PvP 激励梯度设计** (`world-conflict-escalation.md`): 定义从纯 PvE 到全面 PvP 的平滑过渡路径，避免「要么和平要么战争」的二元选择。

2. **策略多样性保障机制** (`meta-diversity-report.md`): 定义 meta 多样性监控指标——如果某策略使用率 >40%，自动触发规则调参或季节性 meta 扰动。

3. **侦察/反侦察机制扩展** (`reconnaissance-design.md`): Phase 2+ 的侦察 body part、信息时效性、反侦察手段的完整设计。

4. **特殊攻击平衡矩阵** (`special-attack-balance-matrix.md`): 8 种攻击的 pairwise counterplay 链、Fortify 拆分方案、Overload-Fortify 交互定义。

5. **多 module 策略切换设计** (`arena-precommit-design.md`): Arena 三种锁定模式定义、module 切换成本模型、AI precompile 限制。

6. **物流拦截游戏化设计** (`transport-intercept-game.md`): 资源运输路径可视化、拦截成功率模型、UI 表现。

7. **AI/人类共存模型** (`human-ai-coexistence-model.md`): World 模式 AI 密度标签、Novice Island 机制、人类玩家的合理竞争窗口。

8. **经济反垄断深度分析** (`economy-anti-cartel.md`): 累计存储税在 N 玩家下的均衡分析、AI 卡特爾的检测与反制。

---

## Designer Action Items

### R2 必须响应（阻塞 Designer 方向通过）

| ID | 问题 | 建议 |
|----|------|------|
| G1-resp | World PvE+PvP 激励梯度 | 在 DESIGN §9 增加 World 模式演进路径描述（纯 PvE → 竞争出现 → 全面 PvP），至少定义 3 种 preset |
| G2-resp | Fortify 纳什陷阱 | 明确 Overload 效果是否可被 Fortify 净化，给出 Fortify/Purge 拆分方案的决策 |
| G3-resp | Overload 间接信息泄露 | 定义是否引入 fuel 噪声（±5%）或标准防御状态返回值 |

### Phase 1 补充（可与 MVP 并行）

| ID | 问题 |
|----|------|
| G4 | 物流拦截游戏化：运输路径可视化 + Intercept 模型 |
| G5 | Vanilla 分层默认值：定义 Tutorial/Novice/Standard/Advanced 各启用哪些规则 |
| G6 | Arena module 锁定模式：full_lock / pool_lock / open_dev |

### R3 / Phase 2 远期

| ID | 问题 |
|----|------|
| — | 侦察/反侦察 body part 设计（Scout, Camouflage, Decoy） |
| — | Meta 多样性监控指标与自动化规则调参 |
| — | AI 卡特爾检测与反垄断机制 |
| — | 信息时效性系统（模糊侦察报告，Decaying Intel） |

---

## Designer Exit Criteria (DSV4 视角补充)

在 GPT Designer 的 6 条 Exit Criteria 基础上，DSV4 增加：

7. World 模式必须定义至少 3 个冲突等级（Novice/Standard/Hardcore），每个等级明确 pvp_enabled 不是 bool 而是参与规则。
8. 特殊攻击矩阵必须完成 pairwise counterplay 审计——确保没有单个 action 同时 counter ≥4 种其他 action（Fortify 当前违反此约束）。
9. Arena 锁定模式必须在 specs 级定义，至少在 `full_lock` 和 `pool_lock` 间做出决策。
10. Overload-Fortify 交互（fuel 减少是否可净化）必须在 specs/02 中明确。

---

*rev-dsv4-designer (DeepSeek V4 Pro) — R2 评审结束。博弈论视角的 Game Designer 审查。*
