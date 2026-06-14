# R7: Game Designer Review — rev-dsv4-designer

**评审日期**: 2026-06-14
**评审范围**: DESIGN.md (full 1341 lines) + P0-1 ~ P0-9 (all specs) + R6 Speaker Verdict
**审阅者角色**: Game Designer Reviewer — 博弈论分析、策略深度评估、算法公平性
**模型**: deepseek-v4-pro
**上下文**: Phase 0 已冻结 (R6 全票 CONDITIONAL_APPROVE)，即将进入 Phase 1 实现。本评审为 Phase 1 启动前的设计师视角终审。

---

## Verdict: STRONG_APPROVE

Swarm 的博弈论基础在 R6 之后进一步巩固——Blake3 XOF 替代 ChaCha12 统一了哈希/PRNG/代码签名三个原语，确定性合同更紧凑；P0-9 Tutorial 来源隔离约束补全了 WASM-only 合同的最后一块拼图；i18n 规则描述系统解决了「规则模组对 AI 玩家不可读」的公平性隐患。设计从「框架正确」演进到了「细节自洽」。

R6 遗留的四个核心设计问题（PvE 激励、Fog 粒度、人机均衡、Code Version 反馈）在 Phase 0 文档中**均未被正面解决**——但这些是「游戏设计深度」问题而非「架构合同」问题，**不应阻断 Phase 1 实现**。本评审将它们重新标记为 Phase 2/3 设计债务，而非 Phase 1 阻塞项。

唯一的 P0 级发现：World 模式缺少**新玩家保护窗口**——先发优势在无保护的持久世界中会形成不可逆的雪球效应。这对玩家留存是致命的。

---

## Strengths

### S1: Deferred Command Model — 博弈论完美的同时行动博弈
`tick(snapshot_json) → Command[]` 是 Swarm 设计皇冠上的明珠。所有玩家在每 tick 同时提交承诺（commit），引擎在洗牌后揭示结果（reveal）。这等价于完美形式的同时行动博弈——消除了反应速度优势、消除了「谁先点击」的竞争、消除了 TOCTOU 漏洞。配合 seeded shuffle 的随机排序，资源竞争变成公平的串行 Stackelberg 博弈，长期期望相等。

**与 R6 对比**: 无变化，但 Blake3 XOF 替代 ChaCha12 使 PRNG 与哈希共享原语，减少了依赖面，从安全角度强化了这个设计的可信度。

### S2: Blake3 XOF 确定性 PRNG — 单原语三用途
`Blake3(tick_number || world_seed)` 驱动 seeded shuffle，Blake3 XOF 提供 PRNG 流。一个原语覆盖哈希、PRNG、代码签名 MAC——审计面减半、依赖减少一个 crate、纯软件 ~6 GB/s 无平台退化。`update_with_seek(seed, offset)` 的 API 天然适配 per-player per-tick 的确定性随机序列，比 ChaCha keystream 管理更简洁。

### S3: Fuel Metering + Refund 三层防御 — 经济反滥用
WASM 指令计数计量 CPU 配额，配合退款机制的时序分离（下 tick 生效）、上限（10%）、同源去重、连续高退款率 throttle（80% 连续 3 tick → 减半配额）。三层防御使 refund 系统从「可能被利用的漏洞」变成了「设计精良的公平补偿机制」。P0-2 §7.3 的 per-source-type 去重比 R6 提出的 per-source 方案更精确——同一 tick 对多个不同 Source 提交 Harvest 不会累积退款。

### S4: 全局存储三重反制 — 经济反垄断
累进存储税（0-30% 免税，85-100% 税 0.20%/tick）+ 本地存储完全私有（不对称信息）+ 运输延迟（不可瞬移补给）。三项措施协同作用：大帝国承受递增维护压力，小玩家在免税缓冲区成长，敌方无法通过窥探全局存储来评估你的真实经济实力。运输中资源可被拦截（Phase 6）为 PvP 增加了「劫掠补给线」的策略维度。

### S5: Source Gate 12 来源完整矩阵 — 架构级权限分离
P0-9 将 12 种指令来源的 capability/budget/visibility 建模为完整矩阵。`Tutorial` 来源隔离（仅 `world.mode = "tutorial"` 世界可接受）和独立 namespace（`tutorial_{world_id}`）解决了「教程引导操作可能污染正式世界」的隐患。`MCP_Deploy` 明确不能提交 gameplay 指令——Source Gate 在架构层拒绝，不依赖运行时检查。

### S6: i18n 规则描述系统 — AI 与人类的信息对等
Rhai 模组的 `mod.toml` 支持多语言配置描述（zh/en/ja），MCP `swarm_get_world_rules` 返回结构化 JSON 含完整参数描述。AI 玩家不再需要「猜测」`drone_cost=5` 的语义——引擎以 AI 可解析的结构化形式提供解释。人类在 Web UI 看到格式化面板，AI 通过 MCP 收到等价 JSON——信息对等。

### S7: 双模可见性分离 — drone 公平 + 玩家体验解耦
P0-5 §3.5 的 `player_view` 与 `fog_of_war` 分离是微妙但关键的设计。WASM `tick()` 的 snapshot **始终**受 `fog_of_war` 限制（游戏公平性不可侵犯），但人类屏幕/旁观者视图可以通过 `player_view` 设置为 `full` 或 `allied`（观战体验）。关键不变量被明确保护：「无论 player_view 如何，WASM tick() 收到的 snapshot 始终按 is_visible_to 过滤」。

### S8: Determinism Contract 的定点数纪律
禁 f64（跨平台非确定）、Rhai 引擎侧关闭浮点、所有游戏数值用 `i64 × 精度因子` 或 `fixed<u32,N>`。这不是炫技——这是可验证的确定性回放的基础。`state_checksum` 每 tick 写入 TickTrace，CI 随机采样做 full replay 验证——确定性从「设计承诺」变成了「可自动化验证的合同」。

---

## Concerns

### G1 [HIGH] World 模式新玩家保护窗口缺失 — 先发优势雪球

**问题**: 当前设计中，新玩家在持久 World 模式中没有任何保护机制。`spawn_cooldown`（加入后多少 tick 才能操作）默认 0，意味着新玩家从 tick 1 就暴露在竞争压力下。

**博弈论分析**: 在有限房间的持久世界中，先发优势是累积性的。早期玩家占领优质 Source、建造防御工事、积累资源储备。后期加入的玩家面临：(a) 好位置已被占，(b) 自身实力不足以挑战既有帝国，(c) 没有 PvE-only 的安全成长路径。

Screeps 通过「新手房间」（sector 0 的特定房间新手专属）+「安全模式」（Controller 激活后 24h 内无法被攻击）提供新玩家缓冲。Swarm 目前设计中没有等价机制。

**雪球动力学**: 在无外部干预的持久世界中，资源差距呈指数增长。如果玩家 A 在第 100 tick 有 2× 资源，到第 1000 tick 可能达到 10×——且差距继续扩大。新玩家面对的不是「追赶」问题，而是「不可能追上」的现实。

**建议**: 定义新玩家保护机制，至少包含以下一层：
- **新手房间** (Phase 1 MVP): 前 100 tick 在独立保护房间中成长，无法被攻击也无法攻击他人。100 tick 后迁移到开放世界。
- **安全模式** (Phase 3): 新占领的 Controller 提供 N tick 的不可攻击期。
- **追赶加成** (Phase 6+): 加入时间越晚的玩家获得越高的资源采集倍率（逐步衰减），类似 Civilization 系列的科技追赶。

### G2 [HIGH] Fog-of-War 二元可见性限制策略表达

**问题**: P0-5 的可见性策略仍然是二元的——可见/不可见。drone body parts 在视野范围内**始终完全可见**（§2.4），这消除了「隐藏科技选择」的策略深度。

**博弈论分析**: 不完全信息博弈的策略深度依赖于**信息分层**。如果：
- 在视野内 → 知道一切（body parts、hits、fatigue）
- 在视野外 → 什么都不知道

那么侦查的收益曲线是阶梯函数——只需维持「有视野」即可获得完美信息。没有「部分信息 → 概率推理 → 策略适应」的中间状态。

对比星际争霸：你看到对手的建筑但不知道正在研究什么科技（需要 scan/observer）；你看到单位但不知道升级等级（需要实际交战）。Swarm 的二元模型下，敌方 drone 一旦进入视野，你立即知道它是 MOVE×5+WORK×5+ATTACK×5（战斗型）还是 MOVE×2+WORK×10+CARRY×5（采集型）——反制策略没有延迟。

**建议**: R6 提出的三层可见性（L1 检测 / L2 识别 / L3 详查）仍然是正确方向，但作为可选的 game mechanic 由服主通过 world.toml 启用，不作为核心引擎修改。Phase 4 实现为 Rhai 模组（`fog-granularity`），默认关闭。

### G3 [MEDIUM] World 模式 PvE 价值函数仍然缺失

**问题**: DESIGN §10 说 World 模式「PvE + PvP 共存」且有「趣味展示（非竞争排名）：殖民地年龄、GCL、房间数」。但 GCL 需要占领房间 → 本质是 PvP 行为（房间有限）。纯 PvE 玩家（不 PvP、只建造）没有独立的、可量化的进度指标。

**博弈论分析**: 如果没有 PvE 专属的价值函数，PvE 玩家的最优策略是「不存在」——因为他们在 PvP 规则下是猎物。Nash 均衡会驱逐 PvE-only 玩家，留下纯 PvP 群体。

当前文档中唯一的「进度」指标都绑定到竞争性行为：
- GCL → 需要占领房间（PvP）
- 房间数 → 需要占领房间（PvP）
- 排行榜 → 基于以上两者

**R6 状态**: G1 [MEDIUM]，未被解决。

**R7 评估**: 降为 MEDIUM 因为：(a) 不阻断 Phase 1 MVP（单人垂直切片只需要一个玩家），(b) 在 Phase 6 Arena/战斗上线前必须有答案，(c) 可以通过 Rhai 模组在 Phase 3+ 实现 PvE 评分系统。

**建议**: Phase 3 设计 `pve-scoring` 模组：基于 `economic_throughput`（tick 间资源流动速率）、`colony_density`（建筑覆盖率）、`sustainability_index`（自给自足度）的综合 PvE 评分。这些指标不需要 PvP 即可量化。

### G4 [MEDIUM] 人机共存世界的均衡仍未明确

**问题**: 设计声称「AI 和人类在同一世界共存」，但元游戏层面的不对称（AI 可 24/7 运行 swarm_simulate、不会疲劳、迭代速度远超人类）未在设计文档中明确回应。

**R6 状态**: G3 [MEDIUM]，未被解决。

**R7 评估**: 降为 MEDIUM 因为 Phase 1 MVP 只有单玩家，在 Phase 2 多人上线前不需要架构决策。但**需要在 Phase 2 规划中做出设计选择**，三种可能路径：
- (a) **接受** — World 模式演化为 AI-majority，明确设计为「AI 研究平台 + 人类观察者」，Arena 保留纯人类 league。
- (b) **分离** — World 模式默认 league 分层（AI-only / Human-only / Mixed），由玩家在加入时选择。
- (c) **平衡** — 给人类辅助工具（AI 策略建议、自动代码优化），使人类在认知层面与 AI 竞争。但这与「代码就是军队」的核心哲学有张力。

建议 (a) 或 (b)。(c) 可能损害 AI 公平性的感知。

### G5 [MEDIUM] Code Propagation 反馈回路未定义

**问题**: `code_propagation_speed > 0` 时，远端 drone 可能滞后 N tick 才获得新代码版本。但：
1. **玩家如何知道哪些 drone 运行哪个版本？** — 无 SDK API 查询 `drone.code_version`
2. **新旧版本行为冲突时责任归谁？** — 无定义
3. **连续部署 + 传播延迟的叠加效果** — 未分析

**R6 状态**: G5 [MEDIUM]，未被解决。

**R7 评估**: 维持 MEDIUM。默认世界 `propagation_speed = 0`（即时），所以 MVP 不受影响。但一旦有服主启用 `propagation_speed > 0`，这个问题立刻浮现。

**建议**: Phase 2 在 SDK 中增加 `drone.code_version: u32` 查询，MCP `swarm_explain_last_tick` 中包含代码版本信息。Web UI 用颜色标注不同版本 drone。

### G6 [LOW] Arena 地图对称性缺乏随机化参数

**问题**: Arena 是「对称初始条件 + 锁死代码」——这在竞争公平性上正确。但缺乏可配置的随机化参数意味着社区会快速收敛到数学最优开局（optimal build order）。一旦最优前 100 tick 被计算出来，Arena 变成执行竞赛而非策略竞赛。

**博弈论分析**: 完美信息对称博弈如果缺乏外生随机变量，会收敛到单一的子博弈精炼均衡。多样性需要足够的决策空间使人类无法穷举——或者引入对称但非相同的初始条件。

**R6 状态**: G4 [LOW]，未被解决。

**R7 评估**: 维持 LOW。Phase 6 才实现 Arena，有足够时间设计。

**建议**: Arena 地图生成器支持「对称但非相同」的地形和资源分布——例如双方的地图是 180° 旋转对称，资源点分布不完全相同但有相同的总产出。这将迫使适应性策略而非背诵 build order。

### G7 [INFO] Phase 1 MVP 反馈循环的 WASM 编译体验断裂

**问题**: P0-6 §2.1 定义的 5 分钟教程说「把 'spawn_count = 1' 改成 'spawn_count = 3'」——但这暗示玩家可以直接编辑代码并看到即时效果。实际上，玩家需要：
1. 编辑 TypeScript
2. **编译为 WASM**（需要 AssemblyScript/rustc 工具链）
3. 部署 WASM
4. 等待下一 tick 生效

步骤 2 是体验断裂点——新手可能没有安装编译工具链。Phase 1 MVP 需要提供**浏览器内 WASM 编译**（AssemblyScript 在浏览器中编译，或预编译 sandbox 教程 WASM 模块供修改）。

**严重程度**: INFO —— 已知 UX 挑战，不阻塞 Phase 1 但应在 Phase 1 规划中考虑。

### G8 [INFO] 暗森林效应：World 模式缺少被动压力

**问题**: World 模式的设计是「玩家驱动」的——所有紧张感来自其他玩家。缺少 PvE 被动压力（中立敌对生物、资源枯竭周期、自然灾害、房间衰减）意味着在玩家稀少的早期/后期，World 模式变成「没有敌人的沙盒」。

**Screeps 处理方式**: Invader NPC 定期攻击所有玩家，提供被动紧张感。即使没有人类敌人在线，你仍然需要防御。

**建议**: Phase 4+ 通过 Rhai 模组（`invader-npc`、`resource-depletion`、`room-decay`）实现，不作为核心引擎功能。但设计文档应提及这个设计方向。

---

## Missing

### M1: 新玩家保护窗口 [P1]
Phase 1 MVP 中至少需要「新手房间」概念——前 N tick 在独立保护房间中成长，不可被攻击。后续 Phase 中引入安全模式、追赶加成。参见 G1。

### M2: PvE 评分模组设计 [P3]
Phase 3 前需要 `pve-scoring` 模组的设计文档：economic_throughput、colony_density、sustainability_index 的计算公式和排行榜整合。参见 G3。

### M3: 人机共存模式架构决策 [P2]
Phase 2 前需要在设计文档中明确：World 模式下 AI 和人类竞争，如果 AI 系统性优于人类，世界设计如何处理？三种路径 (a/b/c) 选一。参见 G4。

### M4: drrone.code_version SDK API [P1]
Phase 1 SDK 中预留 `drone.code_version` 查询接口（当前实现可返回常数值 1），Phase 2 在 code_propagation_speed > 0 时接入真实版本号。参见 G5。

### M5: Arena 地图生成器参数化 [P2]
Phase 2 设计 Arena 地图生成器时，预留随机化参数空间：地形分布变体、资源点分布变体（对称但非相同）。参见 G6。

### M6: 浏览器内 WASM 编译体验 [P1]
Phase 1 教程需要提供浏览器内编译能力——AssemblyScript 浏览器编译或预编译教程 WASM 模块。参见 G7。

### M7: PvE 被动压力模组 [P4]
Phase 4+ 的 Rhai 模组生态规划中包括被动 PvE 压力模组：invader-npc、resource-depletion、room-decay。参见 G8。

---

## Strategy Depth Analysis

### 1. 策略空间分层

| 层面 | 描述 | 复杂度 | Phase 1 可用性 |
|------|------|--------|---------------|
| **Body Part 组合** | 8 种部件 × 最多 50 slot → ~10^40 组合 | 极高 | 部分（Move/Work/Carry/Attack 四种） |
| **资源经济** | N 种自定义资源 → N 维优化 | 世界配置决定 | 单资源（Energy） |
| **WASM 代码** | 图灵完备 → 策略空间无限 | ∞ | ✅ 完全可用 |
| **物流拓扑** | 房间间资源流动 | 图论问题 | 单房间 — 暂未展开 |
| **世界规则** | Rhai 模组组合 → 元策略 | 元空间 | Phase 3+ |

### 2. Dominant Strategy 风险评估

| 场景 | 潜在 Dominant Strategy | 缓解措施 | Phase 1 风险 |
|------|----------------------|---------|-------------|
| World + 无 PvP | 无限扩张采集 | 累进存储税、帝国维护费 mod | 低（单玩家） |
| World + PvP 开启 | 龟缩经济 + 后期爆发 | 房间有限、Fog-of-War | 中（需新玩家保护） |
| Arena 对称 | 固定 build order | 图灵完备代码空间 | 低（Phase 6 才实现） |
| World 先发优势 | 早期占领所有 Source | **暂无缓解** ← G1 | **高** |

**关键发现**: 先发优势是唯一在 Phase 1 MVP 中缺乏缓解的 dominant strategy 风险。单玩家模式下不显现，但 Phase 2 多人世界一上线就会暴露。

### 3. 信息不对称质量（更新）

```
信息公开:   排行榜（GCL、房间数、drone 数）、房间归属者、Controller 等级
信息部分:   全局存储（排行榜区间）、市场订单、建筑存在（在视野内）
信息隐蔽:   本地存储（完全私有）、Controller 进度、资源总量、冷却时间、疲劳值
信息不可见: world_seed、RNG 状态、敌方 WASM 源码、敌方拒绝原因
```

**R7 评价**: 分层合理。与 R6 相比，i18n 规则描述系统使「世界规则」从隐蔽变为公开——这对 AI 玩家是重大改进，之前 AI 需要逆向工程世界规则。主要缺项仍是「距离分层」——同一类型数据在不同距离有不同精度。

### 4. 多层级策略互动

```
Meta 层:  代码架构、模拟策略、迭代速度、跨世界知识迁移
        ↕
Macro 层: 多房间扩张、技术树选择（body part）、市场参与
        ↕
Meso 层:  单房间资源流、建造优先级、防御布局
        ↕
Micro 层: 单 drone 路径选择、攻击目标优先级、采集效率
```

Phase 1 MVP 只激活 Micro + Meso 层（单房间单玩家）。Macro 和 Meta 层的策略深度在 Phase 2-6 逐步展开。这是正确的分阶段策略——不需要在 MVP 中验证所有层级。

### 5. 纳什均衡更新

**World 模式（持久世界）**:
- R6 预测: AI-dominated，人类迁移到 Arena
- R7 更新: 新玩家保护窗口（G1）缺失会加速这个收敛——不仅是 AI vs 人类，而是「先到玩家 vs 后来玩家」的不平等。后来者（无论 AI 还是人类）都面临不可逾越的先发优势。没有新玩家保护 → World 模式随时间推移变成「早期玩家俱乐部」→ 新玩家流失 → 世界死亡。

**Arena 模式（1v1 对称）**:
- R6 预测: 社区收敛到经验最优打法
- R7 更新: 如果 Arena 地图生成器支持随机化参数（G6），最优 build order 的收敛会被延迟甚至阻止。关键设计选择：Arena 是「国际象棋」（固定棋盘，比计算深度）还是「星际争霸」（对称但不相同的地图，比适应性）？

**AI/人类共存**:
- R6 预测: AI 在沙箱外有系统性优势
- R7 更新: Phase 1 MVP 中这个不是问题（单玩家）。Phase 2 多玩家时，如果 AI 玩家的初始 WASM 质量与人类 starter bot 相近，早期的竞争是公平的。AI 的优势在于迭代速度——但人类的优势在于一次可以设计全新的策略范式（AI 受限于训练数据）。这种互补性可能产生有趣的共存而非驱逐。

### 6. 算法公平性审计（更新）

| 机制 | 公平性属性 | R6 评价 | R7 更新 |
|------|-----------|--------|---------|
| Fuel Metering | 语言无关、平台无关 | ✅ 最优解 | ✅ 无变化 |
| Seeded Shuffle | 长期期望均等 | ✅ 密码学保证 | ✅ Blake3 XOF 替代 ChaCha12 — 更紧凑 |
| MCP = Web UI | 人类和 AI 走相同路径 | ✅ 架构级公平 | ✅ i18n → AI 获得等价规则描述 |
| Deferred Command | 同时承诺、同时揭示 | ✅ 消除反应速度优势 | ✅ 无变化 |
| 资源竞争 | 先到先得 + 洗牌 | ✅ 简单且正确 | ✅ 无变化 |
| Anti-Amp Refund | 防止退款滥用 | ✅ 设计周密 | ✅ per-source-type 去重更精确 |
| 全局存储公开 | 仅排行榜区间 | ⚠️ 不对称 | ✅ 可配置（`global_storage_public`） |
| **新玩家公平** | 先发优势无缓解 | ❌ 未提及 | ❌ **G1 — 新发现** |

### 7. PvE + PvP 激励结构评估

```
PvP 激励路径:
  占领房间 → GCL ↑ → 排行榜可见 → 声望（→ 更多玩家挑战你 → 更多 PvP）

PvE 激励路径:
  ??? → ??? → ???

  当前设计: PvE 没有独立的激励闭环
  后果: PvE-only 玩家没有留在 World 模式的理由
```

**建议的 PvE 闭环**（通过 `pve-scoring` Rhai 模组实现）:
```
采集效率 ↑ → economic_throughput ↑ → PvE 评分 ↑ → 排行榜（独立于 PvP 排行榜）→ 声望
建造覆盖 → colony_density ↑       → PvE 评分 ↑ → 同上
自给自足 → sustainability ↑      → PvE 评分 ↑ → 同上
```

---

## 总结

Swarm 的博弈论设计在 R6 → R7 期间进一步成熟。Blake3 单原语统一、i18n 规则描述、双模可见性分离、Tutorial 来源隔离——这些增量改进解决了多个「细节让公平性漏风」的问题。

**Phase 1 MVP 可放心启动**。当前设计对单玩家垂直切片是完全自洽的。

Phase 1 实现过程中需要关注的设计债务（按优先级）:

| 优先级 | 问题 | 实现阶段 | 建议 |
|--------|------|---------|------|
| **P1** | G1: 新玩家保护窗口 | Phase 2 前 | 新手房间机制 |
| **P1** | M4: drone.code_version SDK API | Phase 1 | 预留接口 |
| **P1** | M6: 浏览器内 WASM 编译 | Phase 1 教程 | 预编译模块或 AS 浏览器编译 |
| **P2** | M3: 人机共存架构决策 | Phase 2 前 | 选 (a) 或 (b) |
| **P2** | M5: Arena 地图随机化参数 | Phase 2 设计 | 预留参数空间 |
| **P3** | M2: PvE 评分模组 | Phase 3 | Rhai 模组实现 |
| **P3** | G2: Fog 三层可见性 | Phase 4 | Rhai 模组，默认关闭 |
| **P4** | M7: PvE 被动压力 | Phase 4+ | Rhai 模组生态 |
| **P6** | G6: Arena 地图随机化 | Phase 6 | 对称但非相同地形 |

**核心判断**: 设计文档的质量已经超越「能开工」的水平，达到了「知道开工后哪些坑在哪里」的水平。Phase 1 实现团队可以被信任去建造正确的 MVP——文档契约足够坚实。

---

*评审者: rev-dsv4-designer (Game Designer Reviewer)*
*模型: deepseek-v4-pro*
*回合: R7 — Phase 1 启动前终审*
