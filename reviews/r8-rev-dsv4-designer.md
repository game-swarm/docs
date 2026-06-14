# R8: Game Designer Review — rev-dsv4-designer (终审)

**评审日期**: 2026-06-14
**评审范围**: DESIGN.md (1370 lines) + tech-choices.md + PLANNER-OUTPUT.md + P0-1 ~ P0-9 (全 9 份)
**审阅者角色**: Game Designer Reviewer — 博弈论分析、策略深度评估、算法公平性
**模型**: deepseek-v4-pro
**上下文**: Phase 0 架构冻结已完成。R7 Speaker Verdict 为 APPROVE，附带 3 个 Claude Opus 发现的 Critical 闭合条件 (C1-C3)。本评审为 R8 终审——Phase 1 实现前的最后一道设计门禁。

---

## Verdict: APPROVE

R7 遗留的 3 个 Critical 项 (C1: drone 生命周期、C2: Controller 升级表、C3: body cost IDL) 已在 Phase 0 文档中全部闭合。drone_lifespan = 1500 tick、RCL 1-8 升级表、body_cost 8 种部件成本表——三个缺口被精确填补。设计从「知道坑在哪」进化到了「坑已填平」。

R7 的 G1-G8 游戏设计债务均未被标记为 Phase 1 阻塞项——这些是「深度」问题而非「合同」问题。Phase 1 MVP（单玩家垂直切片）在当前设计下是完全自洽的。

本终审发现 4 个新问题：其中 G9 (drone_lifespan=0 歧义) 需要在 Phase 1 前澄清，其余为 Phase 2+ 设计债务。

---

## R7→R8 变更审计

| # | R7 问题 | R8 状态 | 证据 |
|---|---------|---------|------|
| C1 | drone age 存在但生命周期未定义 | ✅ **已闭合** | DESIGN.md L167-168: `DEFAULT_DRONE_LIFESPAN: u32 = 1500`，death_system 回收 |
| C2 | Controller 升级路径完全缺失 | ✅ **已闭合** | DESIGN.md L207-223: RCL 1-8 完整升级表（累计 progress、解锁建筑、房间 drone 上限） |
| C3 | body part 成本表未进入 IDL | ✅ **已闭合** | P0-8 L141-149: body_cost 权威表（Move=50E, Work=100E, Attack=80E, Heal=250E 等 8 项） |
| G1 | 新玩家保护窗口缺失 | ⚠️ 未变 | 仍无新手房间/安全模式/追赶加成机制 |
| G2 | Fog-of-War 二元可见性 | ⚠️ 未变 | 仍为可见/不可见二元模型 |
| G3 | PvE 价值函数缺失 | ⚠️ 未变 | GCL/房间数仍是唯一进度指标 |
| G4 | 人机共存均衡未明确 | ⚠️ 未变 | 未做架构决策 |
| G5 | Code Propagation 反馈回路 | ⚠️ 未变 | SDK 中无 drone.code_version API |
| G6 | Arena 地图随机化参数 | ⚠️ 未变 | 仍为纯对称 |
| G7 | 浏览器 WASM 编译体验 | ⚠️ 未变 | 教程体验断裂 |
| G8 | 暗森林效应 | ⚠️ 未变 | 无 PvE 被动压力 |

---

## Strengths

### S1: Deferred Command Model — 同时行动博弈的完美实现

`tick(snapshot_json) → Command[]` 依然是 Swarm 设计皇冠上的明珠。所有玩家在每 tick 同时提交承诺，引擎在 seeded shuffle 后揭示结果。这等价于完美形式的同时行动博弈——消除反应速度优势、消除 TOCTOU 漏洞。

配合 Blake3 XOF 驱动的 seeded shuffle，资源竞争变成公平的串行 Stackelberg 博弈。每个玩家长期期望获取资源的概率均等——这是图灵完备代理的公平竞技场应该有的形式。

### S2: Drone 生命周期 — 创造「退休规划」策略层

新增的 `drone_lifespan = 1500 tick` 和 `age` 字段引入了一个微妙但强大的策略维度：drone 会老死。这个设计创造了以下非平凡决策：

- **主动回收 vs 耗竭死亡**：快老死的 drone 用 Recycle 回收 50% 成本，还是让它工作到最后一刻（0 回收）？
- **代际更替**：玩家需要在 drone 死亡前孵化替代品，形成「劳动力金字塔」——不同年龄的 drone 承担不同风险的任务
- **Spawn 调度**：不能一次性 spawn 所有 drone 然后不管——需要错峰 spawn 以避免同步死亡

这是策略深度的教科书式加法：一个简单的 numeric cap 创造了一整层 logistics planning。

### S3: Controller RCL 升级表 — World 模式长期目标锚定

RCL 1-8 升级表（累计 200→150000 progress）解决了 R7 的「World 模式缺乏长期目标」问题。每级解锁新建筑创造清晰的 progression arc：

```
L1: Spawn only → L2: Extension + Road → L3: Tower + Storage
→ L5: Terminal + Observer (市场 + 视野) → L6: Lab + Factory (自定义资源)
→ L8: Nuker (终极武器)
```

这提供了 8 个离散的「下一目标」——每个都改变可用策略空间。L5 Terminal 开启市场参与，L6 Lab 开启自定义资源——不是简单的数字变大，而是**能力解锁**。

Controller 降级机制 (downgrade_timer=5000, progress 重置) 为 PvP 提供了「围城战」的经济目标：不一定需要摧毁敌方基地，迫使其失去 Controller 也能退化其科技树。

### S4: Blake3 单原语三用途 — 算法公平性的技术基础

Blake3 覆盖哈希/PRNG/代码签名——一个原语，三个独立需求。`update_with_seek(seed, offset)` 的 API 天然适配 per-player per-tick 的确定性随机序列。审计面减半、依赖减少一个 crate、纯软件 ~6 GB/s 无平台退化。这不是炫技——这是公平竞技场的信任基础。如果玩家怀疑 seeded shuffle 被操纵，可以独立验证 Blake3 输出。

### S5: 全局存储三重反制 — 经济反垄断设计

累进存储税 (0-30% 免税 → 85-100% 税 0.20%/tick) + 本地存储隐匿性 (完全私有，敌方不可见) + 运输延迟 (transfer_to_global_time=N tick，不可瞬移补给)。三项协同：

- **大帝国承受递增维护压力** — 囤积全局资源有真实成本
- **小玩家在免税缓冲区成长** — 0-30% 容量完全免税
- **敌方无法通过窥探全局存储评估你的经济实力** — 本地存储完全隐蔽
- **不能瞬移补给前线** — transfer_to_global_time 强制物流规划
- **运输中资源可被拦截 (Phase 6)** — 为 PvP 增加「劫掠补给线」维度

### S6: Code Update Window — 部署策略的元游戏

`code_update_window = { every = N, duration = M }` — 每 N tick 开放 M tick 的代码部署窗口。这创造了一个类似「补丁日」的元策略：

- 玩家必须在窗口内批量部署所有改进
- 窗口外发现的 bug 必须等待下一个窗口
- 敌方可以观察你的部署节奏，预测窗口期
- 如果 `code_propagation_speed > 0`，窗口期部署的代码还有传播延迟

这是玩家-vs-玩家策略的上层博弈——不是在 drone 层面战斗，而是在「何时部署」层面博弈。

### S7: 双模可见性分离 — 公平性与体验的解耦

P0-5 §3.5 的 `player_view` 与 `fog_of_war` 分离是关键设计选择。WASM `tick()` 的 snapshot **始终**受 `fog_of_war` 限制（游戏公平性不可侵犯），但人类屏幕/旁观者视图可以通过 `player_view` 设置为 `full` 或 `allied`（观战体验）。关键不变量被明确保护：「无论 player_view 如何，WASM tick() 收到的 snapshot 始终按 is_visible_to 过滤」。

### S8: 旁观者信息分级 — 竞技公平与观赏性的平衡

P0-5 §3.5 的旁观者可见性限制表区分了「物理状态」(position, hits, owner, body parts — 可见) 和「内部状态」(资源持有量, env_vars, 代码版本, 调试信息 — 不可见)。Arena 模式赛后自动公开回放 (`replay_privacy = "public"`)，但 `spectate_delay ≥ 0` 防止观众实时信息泄露给参赛者。这是电子竞技级别的观战设计。

---

## Concerns

### G1 [HIGH] World 模式新玩家保护窗口缺失 — 先发优势雪球 (R7 继承)

**问题**: 持久 World 模式中，新玩家从 tick 1 就暴露在竞争压力下。先发玩家占领优质 Source、建造防御工事、积累资源储备。后来者面对的是已经被瓜分的世界。

**博弈论分析**: 在有限房间的持久世界中，资源差距呈指数增长。先发玩家在第 100 tick 有 2× 资源，到第 1000 tick 可能达到 10×。新玩家面对的不是「追赶」问题，而是「不可能追上」的现实。在无外部干预下，这个系统的纳什均衡是：所有后来者离开，世界随时间死亡。

**R7 状态**: G1 [HIGH]，未被解决。

**R8 评估**: 维持 HIGH。虽然 Phase 1 MVP 是单玩家，不暴露此问题，但 Phase 2 多人世界一上线就会立刻暴露。如果等到 Phase 2 再设计保护机制，可能需要回退已实现的世界生成和房间分配逻辑。

**建议**: Phase 1 设计文档中添加「新玩家保护」section，至少定义：
- `spawn_grace_period`: 新玩家前 N tick 在独立保护房间（无法被攻击也无法攻击他人）
- `new_player_room_allocation`: 如何确保新玩家不被分配到已被包围的房间
- Phase 2 实现时直接按照设计构造，不需要 Phase 2 临时发明

### G2 [HIGH] Fog-of-War 二元可见性限制策略表达 (R7 继承)

**问题**: P0-5 的可见性策略仍然是二元的——可见/不可见。drone body parts 在视野范围内**始终完全可见**（§2.4），消除了「隐藏科技选择」的策略深度。

**博弈论分析**: 不完全信息博弈的策略深度依赖于**信息分层**。二元模型下：
- 在视野内 → 知道一切（body parts、hits、fatigue 全暴露）
- 在视野外 → 什么都不知道

侦查的收益曲线是阶梯函数——只需维持「有视野」即可获得完美信息。没有「部分信息 → 概率推理 → 策略适应」的中间状态。

对比星际争霸：你看到对手的建筑但不知道正在研究什么科技（需要 scan/observer）；你看到单位但不知道升级等级（需要实际交战）。Swarm 的二元模型下，敌方 drone 一旦进入视野，你立即知道它是 MOVE×5+WORK×5+ATTACK×5（战斗型）还是 MOVE×2+WORK×10+CARRY×5（采集型）——反制策略没有延迟。

**R7 状态**: G2 [HIGH]，未被解决。

**R8 评估**: 维持 HIGH。R7 建议的三层可见性（L1 检测 / L2 识别 / L3 详查）通过 Rhai 模组实现是正确的路径，但设计文档中完全没有提及这个方向。

**建议**: DESIGN.md §8.2 的可见性 section 添加一段「未来方向」描述三层可见性模组的可能设计，不作为 Phase 1 实现需求但作为设计意图留存。

### G3 [MEDIUM] drone_lifespan = 0 语义未定义

**问题**: `drone_lifespan` 在 world.toml 中可配置为任意 u32 值。如果设置为 0，是表示「drone 永生」还是「drone 在创建的同一 tick 死亡」？如果设置为 u32::MAX，是「近乎永生」还是引擎侧有限制？

**严重程度**: MEDIUM。默认值 1500 是正确的，但服主配置 0 或极大值时行为未定义，可能产生非预期的游戏体验。

**建议**: Phase 1 前在 P0-7 的配置校验中添加：
```rust
if config.drone.lifespan == 0 {
    // 0 表示永生——drone 不会因年龄死亡
    // 明确文档化而非猜测
}
if config.drone.lifespan > 100_000 {
    errors.push("drone_lifespan exceeds 100,000 — consider using 0 for immortality");
}
```
并且文档化：`lifespan = 0` 表示 immortal drone（仅 combat/damage 致死）。

### G4 [MEDIUM] World 模式 PvE 价值函数仍然缺失 (R7 继承)

**问题**: DESIGN §10 说 World 模式「PvE + PvP 共存」，但 GCL → 需要占领房间，房间数 → 需要占领房间。纯 PvE 玩家（不 PvP、只建造）没有独立的、可量化的进度指标。

**博弈论分析**: 如果没有 PvE 专属的价值函数，PvE 玩家的最优策略是「不存在」——因为他们在 PvP 规则下是猎物。Nash 均衡会驱逐 PvE-only 玩家，留下纯 PvP 群体。

**R7 状态**: G3 [MEDIUM]，未被解决。

**R8 评估**: 维持 MEDIUM。不阻断 Phase 1，但 Phase 3 前必须有答案。R7 提出的 `pve-scoring` 模组方案（economic_throughput、colony_density、sustainability_index）仍然是合理的 PvE 激励闭环。

### G5 [MEDIUM] 人机共存世界的均衡仍未明确 (R7 继承)

**问题**: 设计声称「AI 和人类在同一世界共存」，但元游戏层面的不对称（AI 可 24/7 运行 swarm_simulate、不会疲劳、迭代速度远超人类）未明确回应。

**R7 状态**: G4 [MEDIUM]，未被解决。

**R8 评估**: 维持 MEDIUM。Phase 2 前需要在 DESIGN.md 中做出架构决策。R7 提出的三种路径：(a) 接受 — World 演化为 AI-majority，(b) 分离 — league 分层，(c) 平衡 — 给人类辅助工具。建议 (a) 或 (b)，因为 (c) 与「代码就是军队」的哲学有张力。

### G6 [MEDIUM] Code Propagation 反馈回路未定义 (R7 继承)

**问题**: `code_propagation_speed > 0` 时，远端 drone 可能滞后 N tick 才获得新代码版本。但：
1. 玩家如何知道哪些 drone 运行哪个版本？— 无 SDK API 查询
2. 新旧版本行为冲突时责任归谁？— 无定义
3. 连续部署 + 传播延迟的叠加效果 — 未分析

**R7 状态**: G5 [MEDIUM]，未被解决。

**R8 评估**: 维持 MEDIUM。默认世界 `propagation_speed = 0`（即时），但一旦有服主启用，问题立刻浮现。R7 建议的 Phase 2 SDK API (`drone.code_version: u32`) 仍然正确。

### G7 [LOW] Controller 作为 Transfer 目标的隐式依赖

**问题**: DESIGN.md L220 说「在 Controller 所在房间内向 Controller 存入资源（通过 Transfer 指令）」。但 P0-2 §3.4 的 Transfer 校验矩阵中没有显式列出 Controller 作为合法目标类型。Controller 需要实现「接受资源」的能力——这需要一个隐式的 capacity 字段，可能复用 `Structure.energy_capacity`。

**严重程度**: LOW。实现时自然的解决方案是让 Controller 实现与 Storage 兼容的接口。但设计文档的隐式依赖可能让实现者困惑：「Controller 能接受 Transfer 吗？」

**建议**: P0-2 §3.4 Transfer 校验矩阵中添加一行：`target_id 是 Structure(Controller) 且 Controller 有接受资源的能力 → NotTransferable`。

### G8 [LOW] Arena 地图对称性缺乏随机化参数 (R7 继承)

**问题**: Arena 是「对称初始条件 + 锁死代码」——这在竞争公平性上正确。但缺乏可配置的随机化参数意味着社区会快速收敛到数学最优开局。一旦最优前 N tick 被计算出来，Arena 变成执行竞赛而非策略竞赛。

**R7 状态**: G6 [LOW]，未被解决。

**R8 评估**: 维持 LOW。Phase 6 才实现 Arena，有足够时间设计。

### G9 [INFO] Drone 退休策略的正面副作用未文档化

**问题**: drone_lifespan 创造了「主动 Recycle vs 自然死亡」的策略选择。这是一个正面的策略深度特征，但 DESIGN.md 中没有明确描述这个策略维度。

**严重程度**: INFO。不需要设计修改，只需在文档中描绘这个策略场景。

**建议**: DESIGN.md §3.1 Drone 描述中添加注释：「玩家可通过 `drone.age` 查询年龄，在接近 lifespan 时主动 Recycle 回收 50% 成本——这创造了 ' 退休规划 ' 的策略维度。」

---

## Missing

### M1: 新玩家保护机制设计 [P2]
Phase 2 多人世界前需要：spawn_grace_period、new_player_room_allocation、可选安全模式。参见 G1。

### M2: drone_lifespan=0 语义文档化 [P1]
Phase 1 前在 P0-7 中添加 `lifespan = 0 → 永生` 的明确文档。参见 G3。

### M3: PvE 评分模组设计 [P3]
Phase 3 前需要 `pve-scoring` 模组。参见 G4。

### M4: 人机共存模式架构决策 [P2]
Phase 2 前明确 World 模式下 AI/人类竞争的处理。参见 G5。

### M5: drone.code_version SDK API [P2]
Phase 2 SDK 中预留查询接口。参见 G6。

### M6: Transfer-to-Controller 显式文档 [P1]
P0-2 Transfer 校验矩阵中明确 Controller 作为合法目标。参见 G7。

### M7: Drone 退休策略文档化 [P1]
DESIGN.md Drone 描述中添加「退休规划」策略注释。参见 G9。

---

## Strategy Depth Analysis

### 1. 策略空间维度（R8 更新）

| 层面 | 描述 | 复杂度 | Phase 1 可用性 | R7→R8 变化 |
|------|------|--------|---------------|-----------|
| Body Part 组合 | 8 种部件 × 最多 50 slot → ~10^40 | 极高 | 4 种核心 | body_cost 明确 (+ Attack/Heal/Claim/Tough) |
| Drone 生命周期 | age + lifespan + Recycle | 新增层 | ✅ 完全可用 | 全新策略维度 |
| Controller 升级 | RCL 1-8 能力解锁 | 新增层 | ✅ 完全可用 | 长期目标锚定 |
| 资源经济 | N 种自定义资源 → N 维 | 世界配置决定 | 单资源 (Energy) | 无变化 |
| WASM 代码 | 图灵完备 → 策略空间无限 | ∞ | ✅ 完全可用 | 无变化 |
| 物流拓扑 | 房间间资源流动 | 图论问题 | 单房间 | 无变化 |
| 世界规则 | Rhai 模组组合 → 元策略 | 元空间 | Phase 3+ | 无变化 |

### 2. Dominant Strategy 风险评估（R8 更新）

| 场景 | 潜在 Dominant Strategy | 缓解措施 | Phase 1 风险 |
|------|----------------------|---------|-------------|
| World + 无 PvP | 无限扩张采集 | 累进存储税、帝国维护费 mod | 低（单玩家） |
| World + PvP 开启 | 龟缩经济 + 后期爆发 | 房间有限、Fog-of-War | 中（需新玩家保护） |
| World + drone_lifespan | 错峰 Spawn 永续劳动力 | 策略深度（正面） | **正面** |
| Arena 对称 | 固定 build order | 图灵完备代码空间 | 低（Phase 6） |
| World 先发优势 | 早期占领所有 Source | **暂无缓解** ← G1 | **高** |

**新增发现**: drone_lifespan = 1500 在 World 模式中自动创造了一个「劳动力金字塔」约束——这减轻了先发优势雪球。即使先发玩家有 500 drone，如果它们同步死亡，先发玩家会经历周期性的劳动力断层。这是设计中的一个**非刻意的反雪球机制**——值得在文档中明确承认。

### 3. 信息不对称质量（R8 更新）

```
信息公开:   排行榜（GCL/房间数/drone 数）、房间归属者、Controller 等级、全局存储（排行榜区间）、市场订单、建筑存在（视野内）
信息部分:   drone body parts（视野内完全可见）、drone age（仅自身可见）
信息隐蔽:   本地存储（完全私有）、Controller 升级进度、资源总量、冷却时间、疲劳值、敌方 drone age
信息不可见: world_seed、RNG 状态、敌方 WASM 源码、敌方拒绝原因、敌方全局存储余额
```

**R8 评价**: 分层依然合理。drone age 是隐蔽信息 → 敌方不知道你的 drone 何时会老死 → 无法精确规划针对性的击杀窗口。这是微妙的正面信息不对称。

### 4. Controller 升级的策略博弈

Controller RCL 升级表引入了多房间扩张的策略张力：

```
升级一个 Controller 到 L8: 需要 150000 progress 累计
vs
占领 5 个 L1 Controller: 需要 0 progress（只需 Claim + 防守）

策略选择:
  A) 高 RCL 单房间 — 解锁高级能力但脆弱（所有鸡蛋一个篮子）
  B) 多低 RCL 房间 — 分布式韧性但能力受限
  C) 混合 — 一个高 RCL 核心 + 多个低 RCL 卫星
```

降级机制 (downgrade_timer = 5000) 为围攻者提供了明确的 PvP 目标：不需要摧毁基地，迫使敌方失去 Controller 就能退化其科技树 1 级——且 progress 重置为 0，所有升级进度白费。

### 5. 纳什均衡分析（R8 更新）

**World 模式（持久世界）**:
- R7 预测: AI-dominated，人类迁移到 Arena
- R8 更新: drone_lifespan 和 Controller 升级为 World 模式增加了「时间维度」的策略深度。不是「谁先到谁赢」——而是「谁能持续运营劳动力金字塔 + 科技树」。先发优势仍然存在但不再不可逾越：后来者可以专注研发高价值身体部件（Heal=250E，Claim=600E），用质量对抗数量。

**Arena 模式（1v1 对称）**:
- R7 预测: 社区收敛到经验最优打法
- R8 更新: 8 body parts × 50 slots = ~10^40 组合空间，即使社区收敛到「最佳组合」，图灵完备的 WASM 代码意味着「如何用这个组合」有无穷策略变化。Arena 的深度不在于 build order，而在于**适应对方策略的运行时决策**。

**AI/人类共存**:
- R7 预测: AI 在沙箱外有系统性优势
- R8 更新: drone 生命周期和 Controller 升级是「长周期规划」问题——AI 擅长短期战术优化，但人类擅长跨数百 tick 的战略远见。这种互补性可能使人类在 World 模式保持竞争力：人类设计长期策略框架，AI 优化短期执行。

### 6. 算法公平性审计（R8 终版）

| 机制 | 公平性属性 | 评价 | R7→R8 变化 |
|------|-----------|------|-----------|
| Fuel Metering | 语言无关、平台无关 | ✅ 最优解 | 无变化 |
| Seeded Shuffle | 长期期望均等 | ✅ Blake3 XOF 密码学保证 | 无变化 |
| MCP = Web UI | 人类和 AI 走相同路径 | ✅ 架构级公平 | 无变化 |
| Deferred Command | 同时承诺、同时揭示 | ✅ 消除反应速度优势 | 无变化 |
| 资源竞争 | 先到先得 + 洗牌 | ✅ 简单且正确 | 无变化 |
| Anti-Amp Refund | 防止退款滥用 | ✅ per-source-type 去重 | 无变化 |
| Drone 生命周期 | 所有 drone 统一寿命 | ✅ 新增公平机制 | **R8 新增** |
| Controller 升级 | 统一成本表 | ✅ 透明规则 | **R8 新增** |
| 全局存储公开 | 仅排行榜区间 | ✅ 可配置 | 无变化 |
| **新玩家公平** | 先发优势无缓解 | ❌ 未解决 (G1) | 无变化 |
| **Fog 粒度** | 二元可见性 | ⚠️ 丧失策略深度 (G2) | 无变化 |

### 7. PvE + PvP 激励结构评估（R8 更新）

```
PvP 激励路径:
  占领房间 → GCL ↑ → 解锁高级建筑 (RCL) → 更强 military → 更多房间
  降级敌方 Controller → 退化其科技树 → 削弱对手 → 捕获其领土
  ↑ 新增 RCL 解锁表使 PvP 有明确的经济目标

PvE 激励路径:
  ??? → ??? → ???
  当前设计: PvE 没有独立的激励闭环
  新增间接 PvE 目标: 维持 drone 劳动力金字塔 → 保持经济产出稳定
  但这仍然是服务于 PvP 竞争力，不是独立的 PvE 价值
```

**R8 新发现**: Controller 升级表使「建造和运营」本身有内在满足感——看到 RCL 数字增长解锁新能力。这为 PvE 玩家提供了**内在激励**（intrinsic motivation），即使没有外部排行榜。但这不是设计的，是 emergent property——需要在 UX 中强化这种「成长可见性」。

---

## 总结

Swarm 的博弈论设计在 R7→R8 期间完成了「缺口填补」。drone 生命周期、Controller 升级、body cost IDL——三个被 Claude Opus 发现的 Critical 缺口被精确闭合。设计的成熟度从「知道坑在哪」进化到了「坑已填平，可以开工」。

**Phase 1 MVP 可放心启动**。当前设计对单玩家垂直切片是完全自洽的。

Phase 1 实现前需处理的设计债务（按优先级）:

| 优先级 | 问题 | 行动 | 时间 |
|--------|------|------|------|
| **P0** | G3: drone_lifespan=0 语义 | 文档化：0=永生 | Phase 1 前 |
| **P0** | M6: Transfer-to-Controller 显式 | P0-2 校验矩阵添加一行 | Phase 1 前 |
| **P0** | M7: Drone 退休策略文档化 | DESIGN.md 添加注释 | Phase 1 前 |
| **P1** | G1: 新玩家保护窗口 | 设计文档添加 section | Phase 1 |
| **P2** | M4: 人机共存架构决策 | 选 (a)/(b) 并写入 DESIGN.md | Phase 2 前 |
| **P2** | M5: drone.code_version SDK API | Phase 2 SDK 预留接口 | Phase 2 |
| **P3** | G4: PvE 评分模组 (M3) | Rhai 模组设计 | Phase 3 |
| **P3** | G2: Fog 三层可见性 | Rhai 模组，默认关闭 | Phase 4 |
| **P6** | G8: Arena 地图随机化 | 对称但非相同地形 | Phase 6 |

**核心判断**: 设计文档已从「能开工」进化到「开工后不会撞坑」的水平。Phase 1 实现团队可以被信任去建造正确的 MVP——文档契约坚实，博弈论基础清晰，公平性机制自洽。

---

*评审者: rev-dsv4-designer (Game Designer Reviewer)*
*模型: deepseek-v4-pro*
*回合: R8 — Phase 1 启动前终审*
