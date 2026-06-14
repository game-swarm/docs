# R6: Game Designer Review — rev-dsv4-designer

**评审日期**: 2026-06-14
**评审范围**: DESIGN.md (full) + P0-1 ~ P0-9 (all)
**审阅者角色**: Game Designer Reviewer — 博弈论分析、策略深度评估、算法公平性
**模型**: deepseek-v4-pro

---

## Verdict: CONDITIONAL_APPROVE

设计在核心公平性和策略空间方面表现出色——deferred command model、seeded shuffle、WASM fuel metering 构成坚实的博弈论基础。但 World 模式下 PvE/PvP 共存的经济激励、AI 与人类在同一 Nash 均衡下的长期可持续性、以及 fog-of-war 的策略粒度，需要 Phase 1 实现前进一步明确。以下 8 个问题中 G2（信息不对称粒度）和 G3（人机共存均衡）为阻塞项，其余可在后续 Phase 迭代解决。

---

## Strengths

### S1: Deferred Command Model — 博弈论纯净性
`tick(snapshot_json) → Command[]` 是所有设计决策中最干净的一个。所有 mutating 操作通过 JSON 指令提交，引擎统一校验——这杜绝了「host function 直接改世界」的 TOCTOU 漏洞和 API 膨胀。从博弈视角看，这等价于**所有玩家在每 tick 同时做出承诺（commit），然后引擎揭示结果（reveal）**——完美的同时行动博弈结构，消除了反应速度优势。

### S2: Seeded Shuffle 玩家排序 — 长期公平性
`Blake3(tick_number || world_seed)` 驱动的种子洗牌同时满足三个属性：(a) 确定性——可回放，(b) 不可预测——玩家无法提前知道排序位置，(c) 长期公平——每个玩家有均等概率排在任意位置。这比固定排序（永远 Player 1 先执行）或纯随机（不可回放）都更优。资源竞争的「先到先得 + 种子洗牌」规则使每 tick 变成一个随机顺序的 Stackelberg 博弈，长期期望公平。

### S3: Fuel Metering (WASM 指令计数) — 语言无关公平
以 WASM 指令数而非墙钟时间计量 CPU 配额，是编程竞技游戏的根本性公平保障。C 玩家和 Python 玩家在相同 fuel 预算下获得同等算力，消除了「谁的语言 runtime 更快谁就赢」的元游戏。配合 anti-amplification refund（退还 fuel 仅作用于下一 tick、上限 10%），有效防止了退款机制的策略性滥用。

### S4: 全局存储反制机制 — 反垄断设计
累进存储税 + 本地存储隐匿性 + 运输延迟，三项措施共同防止富有玩家通过囤积资源垄断经济。累进税率的设计（0-30% 免税、85-100% 征 0.20%/tick）给中小玩家留出免税缓冲区，同时给大帝国施加递增的维护压力。本地存储完全私有的设计创造了不对称信息博弈——敌方不知道你的真实经济实力。

### S5: 可配置世界规则 — 策略多样性平台
从 Screeps 的硬编码规则演进到 `world.toml` + Rhai 模组系统，使 Swarm 从「一个游戏」变为「一个游戏引擎平台」。自定义资源类型、物流模式（A/B/C 三种）、代码传播速度、PvP 开关——服主可以创造完全不同的策略环境。模组市场的设计（源代码、可 fork、社区 rating）降低了创作门槛。

### S6: MCP 同级界面 — AI/人类完全公平
AI 通过 MCP 看世界、写 WASM、部署，与人类通过 Monaco 编辑器走完全相同的路径。MCP 不做游戏动作（无 `swarm_move` 等），引擎只认 WASM。这杜绝了「AI 走捷径」的公平性问题——两类玩家在相同的沙箱约束下竞争。

### S7: Command Source Model — 12 来源完整建模
P0-9 将指令来源建模为 12 种显式 source（WASM / MCP_Deploy / MCP_Query / Admin / Replay / TestHarness / Tutorial / Deploy / Rollback / RuleMod / Simulate / DryRun），每种有独立的 capability/budget/visibility 矩阵。Source Gate 确保「MCP_Deploy 不能提交 gameplay 指令」——在架构层面防止了权限混淆。

### S8: 单源 IDL — 生成即一致
`game_api.idl` 生成 Rust Command enum + TypeScript SDK types + MCP schemas + Docs。API 变更从不一致不是可能的——不一致即编译错误。这消除了「文档说 X、SDK 返回 Y、引擎接受 Z」的经典 bug 类别。

---

## Concerns

### G1 [MEDIUM] World 模式 PvE 激励结构缺失

**问题**: DESIGN §10 定义 World 模式为「PvE + PvP 共存」，但整个设计中 PvE 没有独立的激励路径。当前唯一的显式进度指标是 GCL（需要占领房间）——本质上是 PvP 行为，因为房间是有限资源。如果一个玩家只想「建立繁荣的殖民地，不与任何人战斗」，他们优化什么？

P0-6 §6 说 World 模式的排行榜是「趣味展示（非竞争排名）」——但这意味着 World 模式没有目标。没有目标的沙盒对于前 100 名玩家是乐园，对于其余 99% 是「我为什么还要登录」的死区。

**博弈论分析**: 在有限房间的持久世界中，PvE 玩家是 PvP 玩家的猎物。如果 PvE 没有独立的价值函数，Nash 均衡将驱逐 PvE 玩家——留下纯 PvP 群体，游戏萎缩。Screeps 通过 GCL/能量排行榜给 PvE 玩家一个可量化的进度指标，即使他们不 PvP。

**建议**: 定义明确的 PvE 价值函数，例如 room_score（建筑密度 × 科技等级）、colony_age（持续存活的 tick 数）、economic_throughput（单位时间资源流动量）。这些指标可以转化为排行榜而不需要 PvP。

### G2 [HIGH] Fog-of-War 策略粒度不足

**问题**: P0-5 的可见性策略定义了清晰的二元规则（可见/不可见），但缺乏策略深度的必要粒度。具体而言：

1. **Drone body parts 始终可见**（§2.4）——这意味着当你看到敌方 drone，你可以完美知道它的组成，从而精确 counter。这消除了「隐藏科技选择」的策略深度。试想星际争霸中如果你看到对手的单位就能看到它的所有升级——侦查的回报过高，隐藏策略的回报为零。

2. **缺少分层侦查机制**——当前只有「在视野范围内」和「不在视野范围内」两种状态。没有「检测到活动但看不到单位」（信号情报），没有「看到单位但不知道详细组成」（长距离模糊），没有「知道有建筑但不知道等级」。

3. **Observer 建筑是唯一的专用侦查工具**（vision_range=10）——这使侦查变成「建一个 Observer 就行」的二元操作，而非需要持续投资的多层次情报系统。

**博弈论分析**: 完美信息博弈（Arena 全知视角）和完全不完全信息博弈（完全黑暗）都有已知的最优策略。有趣的不完全信息博弈需要**分层信息**——你知道一些但不知道全部，迫使你做概率推理。Swarm 的二元可见性不利于产生丰富的 bluffing/feinting 策略。

**建议**: 引入三层可见性：
- **L1 检测** (range > 3): 知道有 entity 存在，类型未知
- **L2 识别** (range 2-3): 知道 entity 类型和大致状态
- **L3 详查** (range ≤ 1): 知道完整组件数据

每一层需要不同的投资（身体部件 / 建筑 / 科技），创造侦查 vs 隐蔽的军备竞赛。

### G3 [MEDIUM] 人机共存世界的 Nash 均衡问题

**问题**: DESIGN §1.1 声明「人类和 AI agent 在同一世界共存」。从博弈论视角看，这会产生收敛问题：

1. **计算不对称**: AI agent 可以 24/7 运行 `swarm_simulate`，在部署前测试数万种策略变体。人类受限于认知带宽和时间。
2. **注意力不对称**: AI 不会疲劳、不会漏看敌方 drone 入侵、不会忘记更新某个房间的代码。
3. **迭代速度不对称**: AI 可以在每个 tick 后自动分析 `swarm_explain_last_tick` + `swarm_profile`，自动调整策略参数。人类需要手动解读数据。

设计声称「世界只认 WASM」确保了沙箱公平——这是正确的。但沙箱公平 ≠ 元游戏公平。AI 在沙箱外的优势（模拟能力、注意力、迭代速度）会系统性转化为沙箱内的优势。

**博弈论分析**: 如果 World 模式的 Nash 均衡是 AI-dominated，人类玩家会退出 World 模式，迁移到 Arena（人类 vs 人类）。World 变成「AI training ground」而非「人类 + AI 共享世界」。这未必是坏事——但设计应该明确这一结果并为此做规划。

**建议**:
- 承认 World 模式可能演化为 AI-majority，并为此设计良性特性（AI 锦标赛、AI 研究 API）
- 考虑 league 分层：AI-only league / Human-only league / Mixed league
- 或设计人类特有优势（如创意加成——某些 game mechanic 只对人类玩家的策略多样性有响应）

### G4 [LOW] Arena 模式缺乏元游戏多样性保障

**问题**: Arena 模式是「对称初始条件 + 锁死代码」——这对竞争公平性是正确的。但缺乏随机元素意味着最优开局（optimal opening）会在社区中迅速收敛。一旦最优前 100 tick 的 build order 被数学证明，Arena 变成执行竞赛而非策略竞赛。

**博弈论分析**: 完美信息的对称博弈如果缺乏随机性，会收敛到单一的子博弈精炼均衡。多样性需要外生变量——地图差异、随机事件、或足够大的决策空间使人类无法穷举。

**缓解因素**: WASM 的代码空间是图灵完备的，理论上无限大。但实际操作中，前 N tick 的最优资源曲线是可计算的——这是线性规划问题，不是创造性问题。

**建议**: Arena 地图引入受控随机元素（对称但非相同的地形、随机资源点分布但双方对称）。这不影响公平性（双方仍然对称），但破坏确定性 build order 的最优性——迫使玩家做适应性策略而非背诵 build order。

### G5 [MEDIUM] Code Propagation Speed — 战略深度未被充分探讨

**问题**: DESIGN §8.2 的 code_propagation_speed 是一个高度创新的机制——代码更新从传播源向外扩散，远端 drone 可能滞后 N tick 才获得新代码。这是「物流即玩法」思想的代码层映射。

但这个机制的战略影响未被充分分析：
1. 玩家如何知道哪些 drone 运行哪个版本的代码？反馈回路缺失。
2. 如果两个版本的行为冲突（v1 drone 在采集，v2 drone 在攻击），协调失败的责任在谁？
3. 传播延迟 + 部署冷却 + 部署窗口的叠加效果没有分析——可能出现「我的 drone 永不会更新」的边缘情况。

**建议**: 在 SDK 中提供 `drone.code_version` 查询，在 `swarm_explain_last_tick` 中包含代码版本信息，在 Web UI 中用颜色标注不同代码版本的 drone。对边缘情况（传播中又部署新版本）定义明确的重叠语义。

### G6 [LOW] Fuel Refund — 跨源退款的微小漏洞

**问题**: P0-2 §7 的 refund 系统设计精良，anti-amplification 措施（下一 tick 生效、上限 10%、同源重复拒绝仅首次退款）覆盖了主要攻击面。但存在一个微小漏洞：

玩家可以在同 tick 对多个**不同** source 提交不可能成功的 Harvest 指令（因为每个 source 的首次 SourceEmpty 都会退 50% fuel），从而累积退款。虽然单个退还上限是 10% fuel，且 80% 连续 3 tick 会触发 throttle——但精明的玩家可以保持在 throttle 阈值以下（例如 79% 退款率），系统性地获得额外 fuel budget。

**博弈论分析**: 这是一个 repeated game with imperfect monitoring 的情境。玩家的最优策略是探索 refund 系统的边界——保持在检测阈值以下。引擎方的最优策略是改进检测算法。

**建议**: 将同 tick 内所有 SourceEmpty 退款视为同一类别，全局限制（而非 per-source 限制）。或者将退款上限改为 per-source-type 而非 per-source。

### G7 [LOW] 资源存储模型 — 全局与本地之间的模糊地带

**问题**: DESIGN §8.4 定义了全局存储和本地存储的双层模型，以及 A/B/C 三种物流模式。但有一个语义模糊：

「全局存储不能直接用于本地建造——需先转回本地」——这意味着在模式 B（默认轻物流）中，玩家如果想在远程房间建造，需要：(1) 采集到本地 → (2) 转全局（等 N tick + 付 1%）→ (3) 转回远程本地（等 M tick + 付 5%）。总损耗 6%，总等待 N+M tick。

这个设计的意图是「物流本身就是核心玩法」——但 6% 损耗 + 15 tick 等待对新手是严厉的。默认模式下新手可能没有足够的规划视野来管理这个流程。

**建议**: 模式 B 作为默认时，提供 UI 层面的「自动物流」辅助——不是改变规则，而是帮玩家可视化物流管道和预估到达时间。或者为 Phase 1 MVP 降低默认转换成本（0.1% / 0.5%），后续世界再提高。

### G8 [INFO] Tutorial 与 Manual Control 的边界

**问题**: DESIGN §8.2 明确删除 manual_control（「与核心哲学冲突」），唯一例外是 Tutorial 世界中的「受限引导操作」。P0-9 列出 Tutorial source。但 Tutorial 如何实现引导操作而不违反 WASM-only 合约没有详细说明。

**这不是设计缺陷而是文档缺失**——需要明确 Tutorial 的引导操作是通过什么机制实现的。是通过特殊的 Tutorial-only host function？还是预编译的 WASM 模块 + 覆盖层？在 Phase 1 实现 Tutorial 房间前需明确。

---

## Missing

### M1: PvE 进度系统 (P1)
目前无 PvE 专用的价值函数。建议在 Phase 6 前定义：colony_health（综合建筑/资源/单位评分）、economic_throughput（tick 间资源流动速率）、sustainability_index（自给自足程度）。这些可作为 World 模式 PvE 排行榜指标。

### M2: 侦查深度层次 (P1)
如前所述，二元可见性不足以支持丰富的策略博弈。建议在 P0-5 中增加「分层侦查」机制（L1 检测 / L2 识别 / L3 详查），作为可选的游戏机制由服主通过 world.toml 启用。

### M3: AI/人类分层或匹配机制 (P2)
需要在设计文档中明确回答：World 模式下 AI 和人类竞争，如果 AI 系统性地优于人类，会发生什么？三种可能回答：(a) 接受——World 就是 AI playground，(b) 分开——league 分层，(c) 平衡——给人类辅助工具。选择任何一个都比回避问题好。

### M4: Code Version 可见性与调试 (P1)
Code propagation 机制的反馈回路未定义。SDK 需要 `drone.code_version`、MCP 需要 `swarm_get_code_status`、Web UI 需要可视化代码版本分布。

### M5: NPC/环境威胁系统 (P3+)
当前设计的世界是纯玩家驱动的。缺乏 PvE 内容（中立敌对生物、自然灾害、资源枯竭周期）会使 PvE 玩家的体验变成纯粹的「等待——建造——等待」。Screeps 通过 Invader NPC 和房间衰减提供被动紧张感。Swarm 需要类似机制。

### M6: Arena 地图生成器的随机化参数 (P2)
Arena 对称地图的生成算法需要足够的参数空间，使最优 build order 不收敛到单一解。至少需要：地形分布变体、资源点分布变体（对称但非相同）、初始条件微调。

---

## Strategy Depth Analysis

### 1. 策略空间

| 层面 | 描述 | 复杂度估计 |
|------|------|-----------|
| **Body Part 组合** | 8 种部件 × 最多 50 slot → ~10^40 组合空间 | 极高（理论） |
| **资源经济** | 自定义资源类型（N 种）→ N 维资源优化 | 世界配置决定 |
| **WASM 代码** | 图灵完备 → 策略空间无限 | 无理论上限 |
| **物流拓扑** | 房间间资源流动网络 | 图论问题 |
| **世界规则** | 每世界不同 mod 组合 → 不同最优策略 | 元空间 |

**结论**: 策略空间足够大，不会出现 dominant strategy 在全局收敛。但特定世界配置下可能存在局部 dominant strategy（如在物流模式 A + 无 PvP 的世界中，「无穷扩张采集」是最优的）。

### 2. Dominant Strategy 风险评估

| 场景 | 潜在 Dominant Strategy | 缓解措施 | 风险 |
|------|----------------------|---------|------|
| World 模式 + PvP 关闭 | 无限扩张采集（无对抗） | 累进存储税、帝国维护费 mod | 中 |
| World 模式 + PvP 开启 | 龟缩经济（避开战斗，纯成长） | 房间有限，战争迷雾，竞争者抢占资源 | 低 |
| Arena 模式（对称） | 固定 build order | 代码锁定，图灵完备策略空间 | 中 |
| 物流模式 A | 远程瞬移补给（无物流成本） | 运输时间不可为零（§8.4 约束） | 低（已缓解） |

### 3. 信息不对称质量

```
信息完全公开: 排行榜、房间名、Controller 等级
信息部分公开: 全局存储（排行榜区间）、市场订单
信息隐蔽:     本地存储、Controller 进度、资源总量
信息不可见:   world_seed、RNG 状态、敌方 WASM 源码
```

**评价**: 分层合理但有改进空间。当前的分层是「语义分层」（不同类型数据有不同可见性），缺失「距离分层」（同一类型数据在不同距离有不同精度）。

### 4. 多层级策略互动

```
Meta 层:  代码架构、测试策略、迭代速度、跨世界知识迁移
        ↕
Macro 层: 多房间扩张、技术树选择（body part 组合）、市场参与、联盟
        ↕
Meso 层:  单房间资源流、防御布局、建造优先级
        ↕
Micro 层: 单 drone 路径选择、攻击目标优先级、采集效率
```

四个层级之间通过代码设计耦合——Meso 层的资源分配决策通过代码中的优先级逻辑体现，Macro 层的扩张策略通过 drone 生成逻辑体现。这是编程游戏的核心策略深度：**你设计的不是操作序列，而是决策算法**。

### 5. 纳什均衡探索

**World 模式（持久世界）**:
- 玩家群体异构（人类 + AI，先来后到不同起点）
- 不追求全局公平 → 没有单一 Nash 均衡
- 每个玩家的最优策略取决于其目标函数（PvE 成长 vs PvP 征服）
- **风险**: 如果目标函数不明确（如前述 G1），部分玩家没有最优策略，退出

**Arena 模式（1v1 对称）**:
- 对称初始条件 + 锁死代码 → 经典零和/常和博弈
- 完美信息（Arena 无 fog） → 纯策略 Nash 均衡可能存在
- 图灵完备策略空间 → 均衡不可计算（Rice 定理）
- **实际效果**: 不会有数学上的 dominant strategy，但社区会收敛到经验最优打法
- **缓解**: 地图随机化、多资源类型、body part 组合空间

**人机共存**:
- AI agent 在沙箱外有系统性优势（模拟、24/7 运行、注意力）
- 沙箱内公平（相同 fuel、相同 WASM 路径）不抵消沙箱外优势
- **均衡预测**: AI-dominated World 模式，人类集中于 Arena 人类 league
- **设计选择**: 接受并规划（AI league + human league），或引入 human-only 辅助

### 6. 算法公平性审计

| 机制 | 公平性属性 | 评价 |
|------|-----------|------|
| Fuel Metering (WASM 指令计数) | 语言无关、平台无关 | ✅ 最优解 |
| Seeded Shuffle (玩家排序) | 长期期望均等、每 tick 不可预测 | ✅ 密码学保证 |
| MCP = Web UI (同级界面) | 人类和 AI 走相同路径 | ✅ 架构级公平 |
| Deferred Command (tick → JSON) | 同时承诺、同时揭示 | ✅ 消除反应速度优势 |
| 资源竞争 (先到先得 + 洗牌) | 每 tick 随机公平 | ✅ 简单且正确 |
| Anti-Amplification Refund | 防止退款滥用 | ✅ 设计周密 |
| 全局存储公开程度 | 仅排行榜区间 → 不对称信息 | ⚠️ 可配置但默认有信息不对等 |

---

## 总结

Swarm 的博弈论基础是坚实的。Deferred command model + seeded shuffle + fuel metering 构成了一套优雅的公平性保障体系。可配置世界规则打开了策略多样性的大门。MCP 同级界面确保了 AI 与人类的竞争不会在架构层面倾斜。

主要风险集中在 **World 模式的激励结构**（G1: PvE 没有独立目标）和 **信息不对称的策略粒度**（G2: 二元可见性过于粗糙）。这两个问题影响玩家留存的广度和策略表达的深度。人机共存问题（G3）是中期需要面对的架构性选择——回避不如明确。

**建议**: Phase 1 实现前解决 G1 (PvE 价值函数) 和 G2 (分层可见性设计)，Phase 2 前为 G3 (人机均衡) 做出架构性决策。其余问题可在后续 Phase 迭代中解决。

---

*评审者: rev-dsv4-designer (Game Designer Reviewer)*
*模型: deepseek-v4-pro*
