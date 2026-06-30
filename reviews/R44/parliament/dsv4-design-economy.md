# R44 Design-Economy Review — rev-dsv4-design-economy (DeepSeek V4 Pro)

> 评审日期: 2026-06-30
> 评审模型: deepseek-v4-pro
> 评审范围: /data/swarm/docs/ 全部设计文档

---

## Verdict: REQUEST_MAJOR_CHANGES

存在一项 Critical 和多项 High-severity 问题需要在冻结前解决。经济模型的数学骨架是严谨的，但游戏循环中缺乏正向激励导致「自维持自洽但不可玩」的风险。详见下文。

---

## SS1 Critical Findings (blockers)

### CF-1: World PvP 零正向激励 —「最优策略 = 不打架」 [Critical]

**涉及文件**: `design/gameplay.md` §8, §2.2; `design/modes.md` §9; `design/economy-balance-sheet.md` §4

**问题描述**:

World 模式下，PvP 只带来风险和成本（drone 损失、资源消耗、暴露位置），没有任何正向回报。攻击其他玩家的唯一资源收益途径是 Drain（50 tick CD，200 Energy/tick 消耗，受 EMP 抗性减免），但 Drain 的净收益需要长时间持续窃取才能抵消攻击成本。占领敌方房间通过 Controller Claim 是可实现的，但占领后的房间仍需支付 Empire Upkeep（O(n²)），且占领行为本身消耗资源。

反雪球机制成功阻止了无限扩张，但也同时消除了 PvP 的内在动机。在 2-10 房间的「自维持区间」内，玩家的最优策略是扩张到 ~5 房间后停止，优化代码效率，避免一切 PvP 接触——因为 PvP 只增加成本不增加收益。

**影响分析**:

- 游戏的核心身份是「编程竞技场」，但 World 模式将退化为「编程农场」——玩家各自优化经济，互不接触
- Arena 模式提供了 PvP 出口，但 World 模式的 PvP 真空使持久世界缺乏戏剧性和社交驱动力
- 没有 PvP 驱动力的 MMO 玩家留存率堪忧——「我在这个世界里干什么？」

**修复建议**:

方案 A（推荐）: 引入 PvP 战利品机制——击败敌方 drone 后掉落其 body_cost 的一定比例（如 20-30%）作为可采集资源 Wreckage。此掉落来自世界引擎注入（小型 faucet），不转嫁到被击败玩家（避免「输家双重惩罚」）。掉落量受 PvEBudget 约束，防止刷分滥用。

方案 B: 引入领土收益——占领敌方 Controller 后获得一次性「征服奖励」（如 50% RCL progress 对应的资源量），由世界引擎注入。此奖励与 Empire Upkeep 独立计算——占领的成本是后续维护，但征服的即时回报使攻击决策有正向预期价值。

方案 C: 两者结合——Wreckage 掉落 + 征服奖励，形成完整的 PvP 经济循环。

### CF-2: 经济报表的「自维持」声称与基础代码现实不符 [High]

**涉及文件**: `design/economy-balance-sheet.md` §2; `design/gameplay.md` §8

**问题描述**:

Economy Balance Sheet 的核心结论是：「自维持区间：2-10 房间」。但仔细审视数据：

| 房间数 | 基础代码 (×1.0) | 优化代码 (×1.5-2.0) |
|--------|:--------------:|:------------------:|
| 1 | +22 (free_upkeep) | +22 |
| 2 | **-28** | +18 |
| 3 | - | +55 (估算) |
| 5 | **-110** | +13 |
| 10 | **-420** | +100 |
| 20 | **-1,861** | -841 |
| 50 | **-12,289** | -10,464 |

基础代码在所有房间数 ≥2 时均为负。这意味着**大多数玩家（编写基础代码的新手/中级玩家）将始终处于净亏损状态**，与文档声称的「中期自维持可达」矛盾。「自维持」仅对编写高效代码（×1.5-2.0）的顶尖玩家可达，但文档未明确区分这两种情景的受众。

**影响分析**:

- 新手和中級玩家在 free_upkeep 结束后将陷入不可逆的资源枯竭——他们不知道「为什么我总是亏钱」
- 「自维持可达」的宣称在 playtest 中将导致大量负面反馈——玩家期望与实际体验严重脱节
- 从 1 房间 free_upkeep（+22）到 2 房间基本代码（-28）的过渡是 -50/tick 的断崖，与文档声称的「平滑过渡」矛盾

**修复建议**:

方案 A（推荐）: 重新参数化——降低 `base_upkeep` 或提高 `room_soft_cap`，使基础代码在 1-3 房间区间可达小幅正流量。例如 `base_upkeep=30, room_soft_cap=15`（Vanilla 参数），基础代码 2 房间 net flow 从 -28 变为约 +5。

方案 B: 文档诚实化——将「自维持区间」明确标注为「优化代码所需区间」，并将基础代码的持续亏损作为有意的设计压力（「你必须优化代码才能生存」）。但这将改变游戏的受众定位（从「人人可玩」到「程序员硬核」）。

方案 C: 引入基础收入补贴——RCL passive income 从当前 `2/tick per RCL level` 提升到 `5/tick per RCL level`，为基础代码玩家提供更宽的生存窗口。

### CF-3: free_upkeep 断崖 — 2000 tick 后从 +22 跳变到 -33 [High]

**涉及文件**: `design/economy-balance-sheet.md` §2.1; `specs/core/resource-ledger.md` §2.3

**问题描述**:

新玩家在 free_upkeep 期间享有净盈余（+22/tick for 1 room）。在 tick 2000 free_upkeep 结束时：
- 仍只有 1 房间的玩家净流量从 +22 骤降至 **-33/tick**
- 初始资源 5,000 Energy 仅能支撑约 151 tick 的亏损
- 玩家必须在 free_upkeep 的 2,000 tick 窗口内完成至少一次扩张——否则将陷入死亡螺旋

这是一个**硬性「扩张或死亡」门槛**，而非渐进过渡。文档声称 free_upkeep 提供了「初始发展窗口」，但未充分披露此窗口的强制性。

**影响分析**:

- 未能在 2,000 tick 内扩张的玩家将面临不可逆的资源枯竭——这是一个惩罚性的陡峭学习曲线
- 与 Tutorial 和 soft_launch 的渐进保护哲学矛盾——其他保护机制都是渐进过渡，唯独经济是硬断崖
- 对 AI agent 特别不友好——agent 需要时间探索和迭代策略，2,000 tick 的硬 deadline 限制了实验空间

**修复建议**:

方案 A（推荐）: 将 free_upkeep 改为渐进退出——在 tick 2000-3000 期间逐 tick 衰减 free_upkeep 比例（如从 100% 线性降到 0%），而非一次性切断。配合 `soft_launch` 的渐进过渡哲学。

方案 B: 延长 free_upkeep 至 3,000-5,000 tick，将「扩张或死亡」压力推迟到玩家有充分学习时间之后。

方案 C: 在 free_upkeep 结束后提供「经济休克缓冲」——维持 500 tick 的部分补贴（50% 维护费），给予玩家适应期。

### CF-4: 10 房间后的「扩张自毁」悖论 [High]

**涉及文件**: `design/economy-balance-sheet.md` §2.5-2.6; `design/gameplay.md` §8 anti-snowball

**问题描述**:

Anti-snowball 公式的数学证明是正确的——O(n²) upkeep vs O(n) income 必然导致有限均衡点。但这造成了游戏核心机制的自我矛盾：

- 游戏鼓励扩张（更多房间 = 更多 Source = 更多收入），但数学上惩罚扩张
- 优化的平衡点（~5-10 房间）意味着**游戏内容的大部分（房间 11+）在经济上是不理性去追求的**
- 达到 10 房间后，玩家的正确决策是「停止扩张」——但「扩张」是策略游戏的核心乐趣之一

这使反雪球机制从「防止垄断」异化为「惩罚正常玩法」。

**影响分析**:

- 中后期玩家缺乏目标——扩张无益，优化代码有上限（×2.0），PvP 无回报
- 「大帝国需要顶尖代码 + PvE 农场」的声称在 20 房间时仍为 -841/tick 亏损（优化代码），50 房间为 -10,464/tick
- 游戏的「终局」是经济自杀——这是反乌托邦式的游戏设计

**修复建议**:

方案 A（推荐）: 调整维护费公式为非对称曲线——前 15 房间使用较平缓的线性增长（如 `base_upkeep × rooms`，无二次项），15 房间后引入二次项。这保留了反垄断效果，但允许「正常帝国」（~15 房间）在经济上可行。

方案 B: 为高房间数引入新的收入源——如「帝国贸易网络」（15+ 房间解锁，提供与房间数成正比的被动收入），使大帝国在经济上自洽但需要更高的管理复杂度。

方案 C: 明确定义「胜利条件」或「赛季重置」——World 模式不是无限沙盒，而是有明确终点的赛季制世界。玩家在有限时间内竞争，反雪球只需保证新玩家可参与，不需要永久经济均衡。

---

## SS2 Design Tensions (inconsistencies, conflicts)

### DT-1: Move-as-Action 与 combat depth 的张力 [Medium]

**涉及文件**: `design/engine.md` §3.2; `design/gameplay.md` §8

Move 占用 per-tick action slot 消除了双动作模型的排序竞争，但导致 kiting/追击/微操空间极度受限。玩家无法「边打边退」或「边追边打」。此设计是 philosophic commitment 而非技术必需——playtest 可能需要重新评估。文档已标注此风险。

**建议**: 在 playtest 中重点收集移动感受反馈。如普遍负面，考虑引入「移动不占用 action slot 但消耗额外 fatigue」的折中方案。

### DT-2: 全局 vs 本地存储的不对称费率缺乏叙事合理性 [Medium]

**涉及文件**: `design/gameplay.md` §2.2; `specs/core/resource-ledger.md` §2.1

存入全局 1% 费率 vs 提取 5% 费率的不对称性（round-trip 6% 损耗）在数学上合理（抑制频繁提取、鼓励本地物流），但对玩家而言缺乏可理解的叙事——「为什么存入便宜提取贵？」PLAYTEST-GATED.md PG-3 已标记此问题但未解决。

**建议**: 在文档中增加不对称费率的设计理由叙事（如「全局存储是压缩/编码过程——解压缩比压缩贵」），或提供人类可读的时间/成本翻译（如「存入 1000 Energy → 5 tick 后可用 990；提取 1000 → 100 tick 后可用 950」）。

### DT-3: Allied Transfer 的高摩擦与联盟价值矛盾 [Medium]

**涉及文件**: `design/gameplay.md` §3; `specs/core/resource-ledger.md` §2.1

Allied Transfer 有 2% 费率、200 tick 延迟、500 tick cooldown、daily cap = max(10k, GCL × 20k)。这意味着联盟的经济互助极为有限——一个 GCL=1 的盟友每天只能接收 10,000 单位（相当于 Standard 模式约 5 分钟的维护费）。联盟提供了 visibility/intel/non-aggression 但经济合作几乎不存在。

**建议**: 考虑将 allied_daily_cap 的基准从 `max(10,000, GCL × 20,000)` 提升到 `max(50,000, GCL × 50,000)`，或在 alliance 持续时间超过 N tick 后提高 cap。同时保留 cooldown 和 fee 作为防止 abuse 的机制。

### DT-4: 文档间的默认值不一致 [Medium]

**涉及文件**: `design/gameplay.md` §2.2 vs `specs/core/world-rules.md` vs `design/gameplay.md` §2.3

| 参数 | gameplay §2.2 (默认) | world-rules.md (示例) | gameplay §2.3 (示例) |
|------|:----------:|:------------:|:------------:|
| `code_update_cooldown` | 5 (World min) | 0 | 100 |
| `spawn_cooldown` | 0 (默认) | 0 | 100 |

文档中对同一个参数呈现了多个不同的「默认值」和「示例值」，但没有清晰的权威层级。World Rules 文档声明为权威配置 schema，但 gameplay.md 中表格的行内「默认」值与 schema 冲突。

**建议**: 明确声明 world-rules.md 为参数默认值的单一权威源。gameplay.md 中应引用而非重复声明参数默认值。示例值应明确标注 `# example config, not default`。

### DT-5: Controller RCL 升级的资源→progress 转换率缺失 [High]

**涉及文件**: `design/engine.md` §3.1; `design/gameplay.md` §RCL

RCL 升级表定义了累计 progress 需求（RCL 1: 0 → RCL 8: 12,000），但没有定义存入资源的 progress 转换率（如 1 Energy = ? progress）。没有此转换率，玩家无法估算升级时间，Economy Balance Sheet 中的「RCL upgrade」成本也无法量化。

**建议**: 定义 `progress_per_energy = 1`（或任何合理值），并写入 Resource Ledger §2.3 或 engine.md Controller section。

---

## SS3 Suggestions (improvements, simplifications)

### SG-1: 引入 PvP 战利品经济 — Wreckage 回收 [High]

见 CF-1 方案 A。击败敌方 drone 后生成 `Wreckage` 资源实体（body_cost × 20-30%），任何玩家可采集。来源为世界引擎小型 faucet，不转嫁输家。这是为 World 模式注入 PvP 动机的最小可行方案。

### SG-2: 基础收入曲线重新参数化 [High]

见 CF-2 方案 A。将 Standard 模式参数调整为 `base_upkeep=30, room_soft_cap=15`，使基础代码玩家在 1-3 房间可达小幅正流量。优化代码玩家在 2-10 房间获得舒适盈余。此调整保留了 O(n²) 的长期压制效果（10+ 房间递减不变），但降低了新手惩罚。

### SG-3: Allied Transfer 增加联盟深度附加值 [Medium]

除了提高 daily cap（DT-3），建议：
- 联盟持续 500+ tick 后解锁「Allied Depot」——联盟成员可共同建造和使用的共享存储建筑
- 联盟成员可在盟友 Controller 维修范围内维修自己的 drone（降低年龄，消耗盟友 Depot 资源）
- 联盟内 drone 不阻挡彼此移动（已实现）

这些机制不需要独立的经济 faucet，而是利用现有基础设施的权限扩展。

### SG-4: 侦察/隐身 drone body part [Medium]

引入 `Scout` body part：低 HP、无法攻击、高移动速度、扩展视野（+2 格 room range）。这为信息战创造战术深度——侦察 vs 反侦察（Observer/Tower）。与现有的 `Observer` structure 形成互补：Observer 是静态防御性视野，Scout 是动态进攻性视野。

### SG-5: RCL 进度条和经济预测工具的明确化 [Low]

Economy Balance Sheet 提供了数学骨架，但缺少玩家可理解的界面：
- 在 UI 中显示「距下一税率区间约 N tick」
- 在 `swarm_get_economy` MCP 工具中返回预测数据（已部分覆盖）
- 提供「如果你扩张到 N 房间，预估维护费为 X」的规划工具

这些不改变游戏机制但显著改善玩家的经济决策能力。

### SG-6: 中期目标系统（非资产型） [Medium]

10 房间后，经济不支持继续扩张，玩家需要非资产型目标：
- **PvE 据点攻克排行榜**（不产出 World 资源，仅声望和 Arena 入场券）
- **代码效率竞赛**（同资源配置下，谁的 drone 产出最高？）
- **建筑/设计美学竞赛**（非功能性，纯社区投票）

这些目标不改变经济模型但为后期玩家提供留在世界的理由。

---

## SS4 Cross-Reference Matrix

| 发现 | 严重性 | 涉及文档数 | 依赖外部裁决 |
|------|:------:|:--------:|:----------:|
| CF-1: PvP 零正向激励 | Critical | 4 | ✅ 需要设计裁决 |
| CF-2: 自维持声称不实 | High | 2 | ✅ 需要参数调整或文档修正 |
| CF-3: free_upkeep 断崖 | High | 2 | ✅ 需要设计裁决 |
| CF-4: 扩张自毁悖论 | High | 2 | ✅ 需要设计裁决 |
| DT-1: Move-as-Action | Medium | 2 | ❌ playtest-gated |
| DT-2: 不对称费率 | Medium | 2 | ❌ 文档改进 |
| DT-3: Allied 高摩擦 | Medium | 2 | ✅ 参数调整 |
| DT-4: 默认值不一致 | Medium | 3 | ❌ 文档修正 |
| DT-5: RCL 转换率缺失 | High | 2 | ❌ 文档补充 |

---

## CrossCheck

以下问题跨越本评审方向边界，需其他 reviewer 验证：

- **CX-1: [CF-1 PvP 激励] → 建议 security reviewer 检查** Wreckage 掉落机制是否引入可通过多账号刷分的 faucet abuse 向量
- **CX-2: [CF-3 free_upkeep 断崖] → 建议 interface reviewer 检查** 经济告警系统是否充分——玩家在面临资源枯竭前是否收到足够的提前通知
- **CX-3: [DT-4 默认值不一致] → 建议 docs/consistency reviewer 检查** 全文档中所有参数默认值的一致性，包括 world-rules.md → gameplay.md → resource-ledger.md → economy-balance-sheet.md 的值传递链
- **CX-4: [CF-4 扩张自毁] → 建议 gameplay reviewer 检查** 是否存在其他游戏中类似的「扩张惩罚但玩家仍乐在其中」的设计先例作为参考
- **CX-5: [DT-5 RCL 转换率] → 建议 engine reviewer 检查** engine.md Controller section 是否有 RCL progress 转换率的隐含定义但被遗漏在显式文档中

---

## 评审总结

Swarm 的经济模型在数学层面是项目中最严谨的子系统之一——O(n²) anti-snowball 证明、bps 定点费率、四维 PvE budget、连续边际存储税曲线都展现了高水平的系统设计能力。然而，**数学自洽不等于 gameplay 自洽**。

核心问题是 **World 模式缺乏正向激励循环**：PvP 无回报、扩张被惩罚、后期无目标。玩家在 2-10 房间的狭窄「自维持区间」后面对的是经济自杀。游戏需要回答的基本问题是：「作为一个玩家，我为什么要在 World 模式中与其他玩家互动？」

Arena 模式提供了竞技出口，但不能替代 World 模式的社交/戏剧驱动力。建议优先解决 CF-1 (PvP 激励) 和 CF-2/CF-3 (经济可及性)，这两者是「玩家是否会留下」的决定性因素。

反雪球机制是出色的设计——问题不在于它存在，而在于它过于高效，高效到消除了 game loop 中的所有 tension。