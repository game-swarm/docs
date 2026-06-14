# R9 Final Review — Game Designer (rev-dsv4-designer)

> **审阅人**: DeepSeek V4 Pro — Game Designer 方向
> **日期**: 2026-06-14
> **审阅范围**: DESIGN.md (full) + tech-choices.md + specs/p0/ (01–09)
> **方法论**: 博弈论分析 · 策略深度评估 · 激励相容性 · 信息不对称审计 · 纳什均衡

---

## Verdict: APPROVE_WITH_RESERVATIONS

设计整体表现出罕见的严谨性——从 IDL 单源生成到 Deferred Command Model，从 fuel metering 到 seeded shuffle，核心机制闭环完整且自洽。但作为 Game Designer 角色，我识别出 7 个关注点（G1–G7），其中 2 个为 HIGH severity，需在 Phase 1 实现前解决。整体判断：设计已准备好进入实现，但需对标记问题做出设计裁决。

---

## Strengths

### S1: Deferred Command Model 的策略空间
`tick(snapshot_json) → Command[]` 的延迟指令模型是设计中最强的策略杠杆。与传统 RTS 的"即时反应"不同，Swarm 的玩家必须**预先规划整个 tick 的指令序列**，然后在执行阶段接受校验。这创造了独特的策略维度：
- **指令排序博弈**：玩家内部的 `sequence` 编号决定执行顺序 → 需要编排指令依赖图
- **竞争预期**：采集同一 Source 时，先到先得的规则迫使玩家评估"我该抢这个源还是去找下一个"
- **容错成本**：非法指令被拒绝但不退款 → 鼓励精确编程而非"spray and pray"

### S2: Seeded Shuffle 的公平性与不可预测性
`Blake3(tick_number || world_seed)` 作为种子洗牌的熵源是正确选择。关键属性：
- 确定性回放（相同 tick + seed + 指令 → 相同世界状态）
- 长期期望均等（每 tick 独立洗牌）
- 不可预测（world_seed 对玩家隐藏）→ 防止"我排第三所以不抢这个源"的预判博弈退化

这是设计中最干净的博弈论构造。

### S3: 全局存储累进税——Anti-Dominant-Strategy
三层反制机制（累进税 + 隐匿性 + 运输延迟）构成了稀缺的**反垄断设计**。特别是：
- 累进税率在 85%+ 容量时达到 0.20%/tick → 囤积全局存储的成本呈超线性增长
- 本地存储完全私有 → 创造了"隐藏经济实力"的策略选项
- 运输延迟（5–10 tick）防止全局存储成为战斗中的即时补给

这使得"无限扩张 → 垄断市场"不是 dominant strategy。

### S4: 资源类型抽象——引擎无硬编码
`Resource { amounts: HashMap<String, u32> }` 替代 `Resource { energy: u32 }` 是优秀的设计决策。核心引擎不知道 Energy 是什么——它只操作 named resource amounts。这使 World 模式可以配置为 StarCraft（Crystal + Gas）、AoE（Food + Wood + Stone + Gold）、或 Cyberpunk（CPU + Memory + Bandwidth），无需修改引擎代码。

### S5: World vs Arena 双模式清晰分离
两种模式的差异化设计（World 不追求公平、Arena 追求对称公平）解决了"同一个游戏如何同时服务沙盒玩家和竞技玩家"的核心矛盾。排行榜按 `Human/WASM`、`AI-assisted`、`AI tournament` 分区是正确的——这些组别的策略元游戏完全不同，不应混合排名。

---

## Concerns

### G1: Controller 占领机制缺失 [HIGH]

**问题**: `Claim` body part 在 IDL (P0-8) 中定义了成本（Energy: 600），但在 P0-2 Command Validation Matrix 和 P0-8 commands 列表中**没有对应的 Command 条目**。Hack 特殊攻击（DESIGN.md §8.2 伤害类型章节）使用了 Claim body part，但其语义是"夺取 drone 控制权"，而非"占领无主 Controller"。

**影响**: 如果玩家无法通过代码占领无主 Controller，那么：
- 降级后的房间（Controller 失去 owner → downgrade → owner = None）变成永久无人区
- 新玩家只能通过 spawn 机制获得初始房间，无法通过征服扩展领土
- 这严重削弱了 World 模式的领土竞争策略空间

**建议**: 添加 `Claim` Command（或复用现有 `Claim` body part 语义），明确：
- 目标：无主 Controller（owner = None）
- 条件：drone 含 `Claim` body part，在 Controller 范围内（range = 1）
- 效果：drone.owner 成为 Controller.owner，Controller 等级继承当前 progress
- 限制：每 tick 最多 1 次 Claim 尝试 / 需在 Controller 旁维持 N tick

**严重性**: HIGH — 无此机制，World 模式的领土竞争维度断裂。

### G2: World 模式新玩家保护缺失 [HIGH]

**问题**: DESIGN.md §10 明确声明 World 模式"不追求——天然不对称"。这作为设计哲学是成立的，但**完全没有**新玩家保护机制会导致：
- 新玩家 spawn 在 RCL 8 玩家的相邻房间 → 存活时间 < 10 tick
- 没有"安全期"或"不可攻击"窗口
- `spawn_cooldown`（默认 0，可配置）只阻止新玩家行动，不阻止老玩家攻击新玩家

**影响**: 冷启动问题——World 模式的玩家留存率可能在第一天就崩溃。Minecraft 服务器的类比不成立：Minecraft 中你可以跑到 10000 格外建基地，但 Swarm 中 spawn 位置不可控（RandomRoom 默认策略），且地图大小有限。

**建议**: 至少引入以下之一：
- `new_player_protection_ticks`: 新玩家 spawn 后 N tick 内不可被攻击（默认 500 tick ≈ 25 分钟）
- `new_player_room_isolation`: 新玩家初始房间不在其他玩家的视野范围内（地图边缘 spawn）
- `underdog_bonus`: RCL 差距 > 3 级时，低等级玩家享有资源采集加成

**严重性**: HIGH — 直接影响 World 模式的可玩性和留存率。

### G3: AI 玩家信息获取不对称 [MEDIUM]

**问题**: DESIGN.md §4 和 P0-3 声称 MCP 与 Web UI"完全同级"，但两者的信息模态有本质差异：
- **人类**: 通过 PixiJS 渲染的**空间可视化**理解世界 → 直觉式、并行处理
- **AI**: 通过结构化 JSON 数据理解世界 → 精确数值、可编程处理

`swarm_get_snapshot` 返回的 JSON 包含精确坐标、资源数值、冷却时间等**全部数值信息**，而人类在地图上只能估计距离和数量。这不是"信息量"的不对称（设计已保证等量），而是"信息可处理性"的不对称。

**博弈论分析**: 在重复博弈中，能够精确计算的 agent 比依赖视觉估计的人类拥有更低的信息处理错误率。这种不对称在短期不明显，但在数千 tick 的马拉松中会累积为显著优势。

**缓解因素**: WASM fuel metering 是真正的均衡器——无论信息来源如何，执行的 CPU 指令数相同。而且人类可以使用 CLI 工具和本地模拟（`swarm sim`）来弥补计算差距。

**建议**: 当前设计已足够，但应在文档中明确承认这种"模态不对称"，并考虑为 AI 玩家提供额外的 fuel 消耗系数（如 AI 玩家的 MAX_FUEL = 人类玩家的 0.9×）作为补偿机制。此为**可选**而非必须。

**严重性**: MEDIUM — 设计已通过 fuel metering 部分缓解，长期可能需要调整。

### G4: Drone 生命周期与玩家感知脱节 [MEDIUM]

**问题**: Drone 在 1500 tick 后自动死亡（`death_system`），但反馈循环（P0-6）中没有**主动死亡通知**机制。`swarm_explain_last_tick` 是被动的——玩家必须主动查询才知道某个 drone 死了。

**影响**: 玩家可能在 drone 死亡后继续发送针对该 drone 的指令，连续收到 `ObjectNotFound` 拒绝，但不理解原因（以为是 bug 而非寿命到期）。

**建议**: 
- `swarm_explain_last_tick` 的 `notable_events` 字段应包含"drone 因寿命到期死亡"事件
- 可选：在 drone 剩余寿命 < 50 tick 时，snapshot 中添加 `impending_death: true` 标志
- WASM SDK 提供 `drone.ticks_to_live` 查询（只读 host function）

**严重性**: MEDIUM — 影响玩家理解，但不阻塞核心玩法。

### G5: Arena 模式"赛中不可改代码"与 AI 玩家冲突 [MEDIUM]

**问题**: Arena 模式代码在比赛开始时锁定（DESIGN.md §10, P0-9 §6）。对于人类玩家这是公平的。但对于 AI 玩家，这意味着：
- AI 在 5000 tick（≈4 小时）的比赛中无法迭代策略
- AI 的核心优势——快速代码生成和适应——被完全消除
- 这使 AI 在 Arena 中的表现退化到"赛前一次性生成的代码"水平

**当前设计的合理性**: 如果允许 AI 赛中改代码，而人类不能（人类做不到 4 小时内重写 + 编译 + 部署），会创造反向不对称。所以当前设计在**公平性**上是正确的。

**建议**: 考虑引入第三种模式 **"Adaptive Arena"**——赛中允许代码更新，但每次更新消耗递增的资源（第 1 次更新 500 Energy，第 2 次 2000，第 3 次 8000…）。人类和 AI 都可以在赛中更新，但成本限制了频率。这是一种**对称的能力约束**。

**严重性**: MEDIUM — 当前设计对公平性是正确的，但限制了 Arena 作为 AI vs AI 竞技场的潜力。可作为 Phase 6+ 的扩展。

### G6: 伤害类型体系与 Command 校验矩阵脱节 [LOW]

**问题**: DESIGN.md §8.2 定义了丰富的伤害类型/抗性/特殊攻击体系（Kinetic/Thermal/EMP/Sonic/Corrosive/Psionic + Hack/Drain/Overload/Debilitate/Disrupt/Fortify），但 P0-2 Command Validation Matrix 只包含基础的 Attack/RangedAttack/Heal。特殊攻击（Hack, Drain, Overload 等）没有对应的 Command 条目或 validator 规则。

**影响**: Phase 0 冻结后，这些特殊攻击在实现阶段没有规范可依。要么在实现时临时设计（引入不一致），要么推迟到 Phase 6（战斗系统）才定义——但这意味着 IDL 在 Phase 6 需要大改。

**建议**: 在 P0-8 IDL 或 P0-2 中添加特殊攻击的 Command stub（至少声明为 `Phase6` 状态），确保 IDL 的 schema 预留了扩展槽。当前 IDL 的 `commands` 列表中没有这些条目。

**严重性**: LOW — 不影响 Phase 1–2 MVP，但应在 Phase 6 设计启动前完成 IDL 更新。

### G7: 排行榜信息泄露与策略隐私 [LOW]

**问题**: P0-5 §2.6 规定排行榜公开 GCL、房间数、drone 数。这些指标隐含了大量策略信息：
- drone 数 × 常见 body 成本 → 可估算对手的经济规模
- GCL 增长率 → 可推断对手是否正在升级 Controller
- 房间数变化 → 可推断扩张/收缩策略

**博弈论分析**: 在完全信息博弈中，公开这些数据减少了"隐藏实力"的策略选项。但 Swarm 是**不完全信息博弈**——fog-of-war 隐藏了实体位置和资源。排行榜公开的经济元数据与 fog-of-war 隐藏的战术数据形成了有趣的张力。

**当前设计的合理性**: Screeps 也公开 GCL 排名。适度公开创造了"炫耀"的社交激励，增强了 World 模式的社区感。但对于竞技 Arena，赛前公开对手的 GCL 可能暴露策略偏好。

**建议**: 当前设计可接受。但对于 Arena 模式，考虑在赛前隐藏对手的历史指标，仅公开赛后数据。

**严重性**: LOW — 设计选择而非设计缺陷，但值得记录。

---

## Missing

### M1: Controller 占领 Command
见 G1。这是**必须补充**的缺失机制。

### M2: 新玩家保护期配置
见 G2。`world.toml` 中缺少 `new_player_protection_ticks` 和 `new_player_room_isolation` 配置项。

### M3: Drone 剩余寿命查询
WASM host function 列表中缺少 `host_get_drone_ticks_to_live(drone_id) → u32`。玩家代码无法在 drone 自然死亡前做预案（如转移资源、召回 drone 到 spawn 回收）。

### M4: 特殊攻击 Command stub
P0-8 IDL `commands` 列表中缺少 Hack/Drain/Overload/Debilitate/Disrupt/Fortify 的条目（至少声明为 Phase 6）。

### M5: 资源市场机制详细规范
DESIGN.md §8.2 提到了市场（Market）——活跃订单可见、通过 Terminal 交易——但没有详细的订单匹配规则、价格发现机制、交易 fee 结构。这是 Phase 3+ 的内容，但应在 Phase 0 至少有一个 concept-level 的设计段落。

---

## Strategy Depth Analysis

### 策略空间维度

| 维度 | 可变参数 | 策略含义 |
|------|---------|---------|
| **Body 组合** | 最多 50 parts, 8 种类型 | 组合空间 ≈ 50⁸（但受成本约束）→ 实际可行组合数百种 |
| **指令排序** | 每 tick 最多 100 条指令，seq 递增 | 指令依赖图编排 → NP-hard 调度问题（但 100 条内可穷举） |
| **资源分配** | N 种资源，本地/全局两层 | 多维背包问题 + 运输延迟 → 需要前瞻规划 |
| **领土扩张** | RCL 升级 + Controller 占领 | 投资回报周期计算（RCL 1→8 需 150000 progress，何时回本？） |
| **信息获取** | fog-of-war + vision_range | 侦察 drone 的部署密度 vs 经济 drone 的机会成本 |
| **代码部署时机** | update_cooldown + propagation_speed | 窗口期批量更新 vs 即时热修复的权衡 |

### Dominant Strategy 分析

当前设计中，以下策略被反制机制阻断：

| 潜在 Dominant Strategy | 阻断机制 |
|------------------------|---------|
| 无限扩张 → 资源垄断 | 累进存储税 + 运输延迟 |
| 常驻排序首位 → 永远先手 | Seeded shuffle（Blake3 + world_seed 隐藏） |
| Spray-and-pray（大量低质量指令） | MAX_COMMANDS_PER_PLAYER=100 + 不退款的拒绝 |
| 跨 tick 状态累积攻击 | Sandbox per-tick fork → kill，无跨 tick 状态保留 |
| AI 高频部署 → 每次 tick 换策略 | code_update_cooldown（World 默认 5 tick） |
| 刷 refund → 获取额外计算预算 | 同源重复失败仅首次退款 + deploy-reset 规则 |

**结论**: 当前设计**没有明显的 dominant strategy**。每个策略选择都有对应的反制或机会成本。这是博弈论设计的正面信号。

### 信息不对称的策略深度

fog-of-war 分层设计创造了丰富的信息博弈：

```
layer 1: 地形（始终公开）         → 基础空间推理
layer 2: 建筑存在（视野内可见）    → 需要侦察 drone
layer 3: 资源持有量（完全隐藏）    → 需要占领/侦察才能知晓
layer 4: 代码逻辑（完全隐藏）      → 只能通过行为推断
```

这种分层意味着玩家可以在"隐藏经济实力"（囤积本地存储）和"展示威慑力"（部署大量可见 drone）之间做策略性选择。这是健康的博弈深度。

### World 模式下 PvE + PvP 的激励相容性

| 行为 | 激励 | 反激励 |
|------|------|--------|
| 采集资源 | 经济正增长 | 累进存储税（囤积过多时） |
| 扩张领土 | 更多资源点 + RCL 升级 | 超线性维护费（empire-upkeep 模组） |
| PvP 攻击 | 夺取资源/领土 | 反击风险 + 暴露自身位置 + 消耗 body parts |
| 合作/结盟 | 共享视野 + 协同防御 | 盟友可能背叛 + 分润资源 |
| 代码创新 | 策略优势 | code_update_cost（如配置） |

World 模式下 PvE 和 PvP 的激励是**自我平衡**的——过度扩张会导致维护成本超过收入，过度保守会导致被超越。这种平衡取决于 world.toml 配置，服主可以根据目标社区调参。

### AI 与人类在同一世界的纳什均衡

**模型设定**: N 个玩家（含 AI 和人类），每人选择策略 sᵢ，收益函数 Uᵢ(sᵢ, s₋ᵢ) 取决于相对排名（GCL/领土/资源）。

**均衡分析**:

1. **对称均衡（短期）**: 所有玩家使用 starter bot 时，由于对称的 WASM fuel 配额和相同的 seeded shuffle 期望位置，期望收益相等。这是纳什均衡——没有玩家可以通过单方面改变策略提高收益（因为 starter bot 是局部最优的简单策略）。

2. **非对称均衡（长期）**: 随着玩家开发出更优策略，均衡会向**创新-模仿**循环移动：
   - 创新者投入计算资源（AI 优势）或人类洞察力（人类优势）开发新策略
   - 模仿者通过观察排行榜变化推测策略方向并复制
   - 长期均衡取决于**策略空间的探索速度** vs **fog-of-war 的信息隐藏程度**

3. **AI 特有策略**: AI 可能在以下方面找到非对称优势：
   - 精确的寻路优化（每 tick 10 次 path_find，AI 可以最优调度）
   - 资源分配线性规划（多维背包问题的精确解）
   - 对手行为模式识别（数千 tick 的数据中检测规律）

   但这些优势受限于 **fuel budget（10M 指令/tick）**——AI 的计算必须在 fuel 预算内完成，和人类的 WASM 代码一样。

**结论**: 当前设计下，AI 和人类在 WASM fuel 配额上处于**对称约束**，这使得纳什均衡不会完全偏向 AI。长期来看，最优策略是混合型——AI 辅助人类设计核心算法，人类提供创造性策略方向。这正是 Arena 排行榜 `AI-assisted` 分区的意义。

---

## Summary

| 类别 | 数量 |
|------|------|
| Strengths | 5 |
| HIGH severity concerns | 2 (G1, G2) |
| MEDIUM severity concerns | 3 (G3, G4, G5) |
| LOW severity concerns | 2 (G6, G7) |
| Missing items | 5 (M1–M5) |

**行动建议**: G1（Controller 占领）和 G2（新玩家保护）必须在 Phase 1 实现前完成设计裁决。其余关注点可在 Phase 2–6 中渐进解决，不阻塞 MVP。
