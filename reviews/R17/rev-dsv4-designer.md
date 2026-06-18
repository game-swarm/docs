# R17 Game Design Review — Designer (DeepSeek V4 Pro)

**Reviewer**: rev-dsv4-designer
**Date**: 2026-06-18
**Round**: R17 — Clean-Slate Authority Source Closure Verification
**Documents Reviewed**: 8 (design/README.md, design/gameplay.md, design/modes.md, design/interface.md, specs/reference/api-registry.md, specs/gameplay/06-feedback-loop.md, specs/gameplay/08-api-idl.md, specs/core/09-snapshot-contract.md)

---

## Verdict

**CONDITIONAL_APPROVE** — 文档权威单源已实质性闭合，API Registry 作为 machine-readable single source of truth 有效消除了跨文档不一致。游戏设计层面存在 1 个 Critical 结构性问题（soft_launch 悬崖）、3 个 High 策略深度问题、以及若干值得在实现前解决的 Medium 问题。无设计阻断器——所有问题均可在 Phase 1 实现中渐进解决。

---

## Strengths (设计亮点)

1. **API Registry 单事实源架构** (api-registry.md): 35 RejectionReason 变体、19 CommandAction、46 MCP 工具、5 Host Functions、25+ 容量限制参数全部在单一结构化文档中注册。CI 可自动校验跨文件一致性——这是防止文档熵增的正确架构决策。

2. **三级物流模式 (A/B/C)** (gameplay.md §资源存储模型): 从无物流（新手/Arena）到轻物流（默认，1%/5% 损耗）到硬核物流（纯本地物理运输），一架引擎覆盖从 tutorial 到 Factorio-like 的完整难度光谱，无需分叉代码。

3. **累进存储税 + 本地存储隐匿性** (gameplay.md §全局存储反制): 三层反制（累进税率、本地私有、运输延迟）构成优雅的 anti-hoarding 方案。运输中资源可被 PvP 拦截是点睛之笔——将经济囤积转化为物流风险。

4. **Snapshot 截断合同** (09-snapshot-contract.md): 确定性距离桶排序 + 关键实体不可截断前缀 + competitive 降级标记——快照溢出不再是 undefined behavior，而是有明确合同的降级行为。这是引擎健壮性的关键设计。

5. **Safe Hint Ladder** (09-snapshot-contract.md §4): 竞技/练习/训练三级错误提示模型防止通过故意触发错误探测隐藏状态——这是反作弊设计中的优雅方案。竞技模式下所有消息为常数字符串，杜绝信息泄露。

6. **NPC 地理难度梯度** (modes.md §难度梯度): PvE 难度随距世界中心距离递增——不需要"副本入口"或"排队系统"，扩张自然遭遇更强 PvE。这是 MMO 沙盒 PvE 的正确设计模式。

7. **WASM 部署幂等性** (interface.md §5.7, gameplay.md §代码部署): `module_hash` 去重 + `AlreadyDeployed` 返回 + 仅首次扣费——防止网络重试/SDK 误操作多重扣费的干净设计。

8. **OverloadPressure 可见性模型** (gameplay.md §Overload 反馈透明度): 攻击者看自己的 contribution、被攻击者看可见来源的 contribution、不可见来源不暴露——防止反向定位的同时保留了反制决策空间。设计决策表（历史不存储、u32 精度、完整 contribution 列表）有理有据。

---

## Concerns

### Critical

**G1 — Soft_launch → PvP 悬崖：新玩家过渡存在结构性断裂**

(feedback-loop.md §2.4, gameplay.md §反雪球合同)

`soft_launch` 持续 1500 tick（safe_mode 500 tick 后），期间仅 PvE 威胁。结束后 50 tick 广播警告 → 进入完整 PvP。问题：

- 新玩家在 2000 tick 内可能完全没有战斗经验（如果所在区域恰无 NPC engagement）——突然暴露于已在世界中存在数万 tick 的 RCL8 邻居面前。
- "安全区出生"和"密度优先"策略仅保证不被堵死在出生点——**不保证出生点附近没有老玩家领地**。新玩家可能在 soft_launch 结束时发现自己被 RCL6+ 帝国包围。
- 虽然有 Arena Challenge 作为低风险 PvP 入口，但如果新玩家从未主动发起挑战，第一次 PvP 接触就是毁灭性的。

**建议**: 引入 soft_launch **渐进退出**机制——例如 tick 1500-2000 期间，PvP 攻击对新玩家 drone 的伤害按比例递增（25%→50%→75%→100%），而非 binary 开关。或者 soft_launch 结束后给予 200 tick 的 "新手战斗保险"（首次被攻击的 drone 损失降低 50%）。

**G1 Severity: Critical** — 玩家留存的第一道关口。如果首次 PvP 体验是被碾压且无法理解为什么输，churn rate 将显著高于必要水平。

---

### High

**G2 — World 模式长期动机真空：无胜利条件的沙盒需要更强的内生目标系统**

(modes.md §World vs Arena, gameplay.md §长期目标系统)

World 模式的胜利条件明确为"无——类似 MMO 持续沙盒"。长期目标系统包括 GCL、RCL、PvE 里程碑、Arena 段位——但这些都是**指标**（metrics），不是**目标**（goals）。

关键缺失：
- 无可争夺的稀缺世界级资源（如唯一命名的 Territory、周期性刷新的 World Boss 首杀荣誉）
- 无世界事件链（如"虫群母巢出现→全服协作/竞争清除→永久改变地图"）
- GCL/RCL 是单调递增的（不会丢失），长期来看缺乏紧张感
- 殖民地年龄是纯粹的被动计时器——不产生有趣决策

与 Eve Online 对比：Eve 的 nullsec 有领土争夺、超级旗舰建造（需联盟级协调）、市场操纵、间谍活动等丰富的内生目标。Swarm 当前的经济/领土系统缺乏类似的多层目标结构。

**建议**: Phase 2 规划中考虑引入可争夺的**世界级唯一资源或周期性目标**，使顶级玩家的竞争有焦点。Phase 1 可保持当前范围，但预留 World Event 系统的扩展点。

**G2 Severity: High** — R16 已标记此问题。GCL/RCL/milestone 系统是改进但未根本解决——仍是 metric 导向而非 goal 导向。

**G3 — Controller aging 硬上限 (50%) 产生防御性均衡偏向**

(gameplay.md §Drone 生命周期, §反雪球合同)

Controller age rollback 硬上限为自然增长的 50%——即无论持有多少 Controller，drone age **只能减缓、不能逆转**。数学上：

- 自然增长: +1/tick
- 最大回退: -0.5/tick（持有 1+ Controller）
- 净增长: +0.5/tick minimum
- 默认 lifespan 1500 tick → 实际最长为 3000 tick

这意味着**所有 drone 都有绝对寿命上限**，无论玩家投入多少物流资源。结果：
1. Drone 成为消耗品而非 investable asset——降低了"保护精英 drone"的策略深度
2. 建设 Depot 物流网络的主要动机（age 维修）被削弱——因为即使最大化维修，drone 也在缓慢走向死亡
3. 鼓励 drone spam（大量便宜 drone）而非 drone 质量（少量高 body part count drone）——与反雪球目标（减少实体数）矛盾

**建议**: 考虑将硬上限改为**软上限**——例如每额外 Controller 的 age rollback 边际递减（`rollback = min(0.5, 1/(1+exp(-k*(n-1))) * 0.5`），允许拥有大量 Controller 的帝国实现接近中性 aging（但永远达不到永久 drone）。同时保留 active_aging 的 +10% 惩罚防止挂机。

**G3 Severity: High** — 影响核心游戏循环的战略多样性。

**G4 — 战术层缺乏空间组合深度**

(api-registry.md §1.1, gameplay.md §身体部件)

当前战术层限制：
- **4 方向移动** (N/S/E/W)：无对角线移动。8 方向明确标记为 Future RFC。
- **近战距离固定 1 格**，远程固定 3 格——无中间距离、无 elevation/terrain 修正。
- **地形仅影响通行性**（plain/wall/swamp/lava），不影响战斗（如高地加成、掩护减伤）。
- 19 个 CommandAction 多数是单目标交互——无 AoE、无墙/障碍物利用、无阵型加成。

与同类游戏对比：Into the Breach 的 8×8 网格 + 位移攻击 + 环境杀伤创造了极深的战术空间。Swarm 的战术层（移动+攻击+特殊攻击）虽然够用，但在纯 PvP Arena 场景中可能迅速被 solved（最优策略收敛）。

**G4 Severity: High** — Arena 模式 PvP 的策略天花板限制。World 模式中经济/物流提供额外深度，纯战斗层则相对浅。

---

### Medium

**G5 — Drone 间通信缺失迫使所有协调中央化**

(interface.md §5.4)

IDL 明确标注："SendMessage: Future RFC: drone间消息传递。当前不在 Core CommandAction 中"。

这意味着：所有 drone 协调必须通过玩家的全局 WASM 代码（单一 `tick()` 函数）完成。任何 emergent swarm behavior（如 drone A 发现敌人 → 通知 drone B 支援）必须在玩家的全局状态中实现——drone 无法本地通信。

这降低了"分布式 AI 控制分散 drone"的游戏幻想，也将所有通信压力集中到 `tick()` 的快照处理中。在拥有 500 drone 上限的场景下，单一函数处理所有 drone 的协调可能成为实现复杂度的瓶颈。

**G5 Severity: Medium** — 核心游戏幻想（"编写 AI 指挥军队"）与实现约束（无 drone 间通信）之间存在 gap。Phase 2 可考虑引入 range-limited drone messaging。

**G6 — MCP 经济工具归属 debug profile，人类玩家获得不对称信息优势**

(interface.md §4.1a, api-registry.md §3.2)

`swarm_get_economy`、`swarm_get_drone_efficiency`、`swarm_get_economy_trend` 均归属 `debug` capability profile。但人类玩家通过 Web UI 的策略指标仪表盘（feedback-loop.md §5.4）获得等效功能——这些信息对 AI agent 同样是战略决策必需的。

AI agent 需要知道自己的经济轨迹才能做出部署/回收/扩张决策——这些不是 debug 信息，是**运营信息**。debug profile 的语义是"开发者诊断"，不应包含日常运营数据。

**建议**: 将三个经济工具移至 `play` profile，或创建独立的 `economy` profile 默认分配给 World 玩家。

**G6 Severity: Medium** — AI vs Human 公平性问题。AI agent 被降权获取运营数据。

**G7 — 特殊攻击渐进解锁：标准世界不区分 Sequencer/Composition 多样性**

(gameplay.md §特殊攻击方式)

Progressive Unlock 将 8 种特殊攻击按世界层级全开/全关（Tutorial/Novice=全关，Standard+=全开）。但 Standard 世界中 8 种特殊攻击同时可用，没有渐进引入曲线——新进入 Standard 世界的玩家需要在已有经济/物流基础上同时学习 8 种特殊攻击的克制关系。

建议：Standard 世界内部引入 Sequencer（如基于 GCL tier 解锁特殊攻击：GCL 1-2 无特殊攻击，GCL 3-4 解锁 Disrupt+Debilitate，GCL 5-6 解锁 Drain+Overload，GCL 7-8 解锁 Hack+Fortify），使特殊攻击的学习曲线与玩家成长曲线对齐。

**G7 Severity: Medium** — 学习曲线体验问题，不影响核心可玩性。

---

### Low

**G8 — World 模式无世界地图/微缩视图的 API 暴露**

(api-registry.md §3.1)

MCP 工具提供了 `swarm_get_snapshot`（per-drone 视野）、`swarm_list_rooms`（玩家拥有的房间）、`swarm_get_room`（指定房间）——但**没有世界地图视图**。AI agent 无法回答"我的帝国在世界中的位置"、"最近的未占领资源点在哪"、"哪个方向扩张最安全"等宏观战略问题。

人类玩家通过 Web UI 的 PixiJS 渲染获得世界地图——AI agent 应该获得等效的战略信息。

**G8 Severity: Low** — AI agent 可通过多次 `swarm_get_room` 调用拼接地图信息，但效率低且消耗 API 配额。

**G9 — Starter bot smoke test 的 dry-run 在 tutorial snapshot 上运行，不代表 World 条件**

(feedback-loop.md §2.5)

CI smoke test 要求 "`swarm_dry_run_commands` 在 tutorial world snapshot 上执行，无拒绝码"。但 Tutorial 世界 `fog_of_war=false`、`code_update_cost=0`、无 PvP 威胁——与标准 World 条件差异显著。通过 smoke test 的 bot 可能在真实 World 中因 fog of war 导致的 `NotVisibleOrNotFound`、或被其他玩家 drone 占据位置的 `PositionOccupied` 而大量失败。

**G9 Severity: Low** — CI 门禁问题，非设计缺陷。建议 dry-run 使用包含 fog-of-war + 竞争实体的 representative snapshot。

---

## Strategy Depth Analysis

### 策略空间维度

| 维度 | 深度评估 | 瓶颈 |
|------|---------|------|
| **经济优化** | 高 — 采集效率、物流路线、全局/本地存储转换时机、累进税率规避 | — |
| **领土扩张** | 高 — RCL 升级决策、Controller 维护、Depot 布局、房间 drone cap 分配 | — |
| **Body 组合** | 中高 — 8 基础 part × 50 MAX_BODY_PARTS、age_modifier 权衡、特殊攻击绑定 | 绝对寿命上限降低长期投资价值 (G3) |
| **战术战斗** | 中 — 移动+攻击+6 特殊攻击、distrupt 打断、fortify 净化 | 4 方向 + 固定距离限制空间深度 (G4) |
| **信息战** | 中 — fog of war、OverloadPressure 隐藏、本地存储隐匿 | drone 间无通信降低 emergent 行为 (G5) |
| **多 drone 协调** | 中低 — 所有协调在 tick() 中集中化，无分布式通信 | SendMessage 缺失 (G5) |
| **PvE 策略** | 中 — NPC 类型有限（4 种）、据点类型有限（3 种）、事件固定 | 扩展方向留给 mod |

### 主导策略分析 (Dominant Strategy)

当前设计下，**不存在严格主导策略**，但存在几个收敛方向：

1. **经济主导**：最大化早期 Energy 采集 → 快速 RCL 升级 → 解锁高级建筑（Tower/Terminal/Factory）→ 经济碾压。由于 aging 硬上限使 drone 最终会死，高质量 drone 的长期回报被 discounting——这推向了 drone spam（便宜 drone × 数量 > 贵 drone × 质量）。

2. **防御优势**：Controller 维修范围 + Tower 自动攻击 + safe_mode → 防御方有显著优势。但在 aging 硬上限下，进攻方可以用 disposable drone 消耗战逐步推进（防御方的 Tower 有 cooldown 10 tick）。这是微妙的平衡——不是明显的 defense-dominant。

3. **Arena vs World 策略分歧**：Arena 对称初始条件 + 代码锁定 → 纯算法对抗。World 非对称 + 先发优势 → 策略重心从"最优算法"转向"最优长期规划"。两者对玩家技能的要求差异大——一个优秀的 Arena 选手未必在 World 中成功，反之亦然。这是设计意图而非缺陷。

### 纳什均衡 — AI 与人类同世界

- **信息对称性**：AI agent 通过 MCP 获得的数据与人类通过 Web UI 获得的数据是等价的（snapshot model 一致）。但 G6 中经济工具归属 debug profile 打破了这一对称——人类有策略仪表盘，AI agent 在没有 debug 权限时没有。
- **执行公平性**：两者都经过 WASM 沙箱 + fuel metering，计算配额由指令数决定而非语言——这是可证明的公平。
- **时间尺度不对称**：AI agent 可以 24/7 运行优化循环，人类受限于注意力/时间。这是 MMO 的通用问题（脚本 vs 真人）——Swarm 通过 `active_aging`（操作加速衰老）和 `code_update_cooldown`（部署冷却）提供了部分抑制，但未根本解决。
- **均衡预测**：在 World 模式下，AI agent 将主导资源采集效率（连续优化），人类在创造性策略和不可预测行为上占优（Arena 模式）。World 模式的人类-AI 混合会形成分层：AI agent 专注于经济基础层，人类玩家在顶层做战略决策和领土政治（如果有 alliance 机制）。这是健康的共生均衡。

---

## CrossCheck — Authority Source Closure Verification

> 本次 R17 评审的核心目标是验证权威单源是否真正闭合。以下逐项检查。

### CrossCheck 1: RejectionReason 一致性

| 检查项 | api-registry.md §2 (权威) | gameplay.md (IDL) | 状态 |
|--------|--------------------------|-------------------|------|
| 变体总数 | 35 | 47 (含 Fatigued/MissingBodyPart 等 IDL 特有) | ⚠️ 数量不一致 |
| 命名规范 | `InsufficientResource` (单数) | `InsufficientResource` | ✅ |
| `NotVisibleOrNotFound` | §2.2 #7 | IDL §2 #108 | ✅ 两边均存在 |
| `CooldownActive` vs `SpawnOnCooldown` | 分离定义 | 分离定义 | ✅ |

**发现**: IDL 中 RejectionReason enum 包含 47 个变体，api-registry 中为 35 个。差异项包括 `Fatigued`、`MissingBodyPart`、`NotMovable`、`TileBlocked`、`StillSpawning` 等在 IDL 中存在但 registry §2 中缺失的变体。IDL §2 RejectionReason 明确标注 "> 权威定义见 API Registry §2 — 35 变体"——但 IDL 自身列出了更多变体。

**严重度: Medium** — 需对齐。建议以 api-registry 为准，将 IDL 中的额外变体合并归一或补充到 registry。

### CrossCheck 2: CommandAction 一致性

| 检查项 | api-registry.md §1 | gameplay.md (IDL) | interface.md | 状态 |
|--------|-------------------|-------------------|-------------|------|
| 核心指令数 | 11 | 11 (Move/Attack/RangedAttack/Spawn/Recycle/ClaimController + Harvest/Transfer/Withdraw/Build/Heal) | — | ✅ |
| Global 指令 | 2 (TransferToGlobal, TransferFromGlobal) | 2 (TransferToGlobal, TransferFromGlobal) | — | ✅ |
| 特殊攻击 | 6 (Hack/Drain/Overload/Debilitate/Disrupt/Fortify) | 6 | — | ✅ |
| Custom (Leech/Fabricate) | §1.4 — 非 Core | §5.1 — 通过 [[custom_actions]] | — | ✅ |

所有文档 CommandAction 定义一致。✅

### CrossCheck 3: MCP Tools 分类一致性

| 检查项 | api-registry.md §3.1 (46 工具) | interface.md §4.1 (分类) | 状态 |
|--------|-------------------------------|--------------------------|------|
| capability profiles | Onboarding/Play/Deploy/Debug/Admin | onboarding/play/deploy/debug/admin | ✅ |
| 经济工具归属 | Play profile (api-registry §3.1) | Debug profile (interface §4.1a) | ❌ **冲突** |

**发现**: `swarm_get_economy`/`swarm_get_drone_efficiency`/`swarm_get_economy_trend` 在 api-registry §3.1 表格中归类为 "Play | Economy"，但 interface.md §4.1a 的 capability profiles 表中将它们归入 `debug` profile。

**严重度: High** — 这是权威源内部的分歧。api-registry 声称自己为"单一权威来源"，但 interface.md 给出了不同的 profile 分配。必须统一——建议以 api-registry 为准（这三个工具应为 play profile），参见 G6。

### CrossCheck 4: Host Functions 一致性

| 检查项 | api-registry.md §4.1 | gameplay.md (IDL §2) | interface.md §5.1 | 状态 |
|--------|---------------------|---------------------|-------------------|------|
| host_get_terrain | ✅ | ✅ (get_terrain, 短名) | ✅ | ✅ |
| host_get_objects_in_range | ✅ | ✅ | ✅ | ✅ |
| host_path_find | ✅ | ✅ (path_find) | ✅ | ✅ |
| host_get_world_config | ✅ | ✅ | ✅ | ✅ |
| host_get_world_rules | ✅ | ✅ | ✅ | ✅ |
| 调用预算 | §4.2 详细 | §2 (每函数 limit) | §5.5 (概述) | ✅ |
| Per-call fuel 成本 | §4.4 详细 | — | §5.5 (概述) | ✅ |

Host Functions 在所有文档中一致。✅

### CrossCheck 5: 容量限制一致性

| 参数 | api-registry.md §5 | gameplay.md / modes.md | 状态 |
|------|-------------------|----------------------|------|
| drone lifespan | 1500 tick | 1500 tick | ✅ |
| MAX_BODY_PARTS | 50 | 50 (IDL §2) | ✅ |
| Per-player drone cap | 500 | 500 (反雪球合同: "Room drone cap 50→500") | ✅ |
| Commands/player/tick | 100 | — | ✅ |
| Global storage capacity | 1,000,000 | 1,000,000 | ✅ |
| code_update_cooldown | 5 tick (World 最小) | 5 (默认), 100 (示例) | ✅ |

容量限制在所有文档中一致。✅

### CrossCheck 6: Snapshot 截断合同 — 权威源链

| 检查项 | 09-snapshot-contract.md | api-registry.md §1.3 | design/README.md | 状态 |
|--------|------------------------|---------------------|-----------------|------|
| 256KB cap | ✅ | §5 Per-player snapshot 256KB | — | ✅ |
| truncated flag | ✅ | — | — | ⚠️ 仅 contract 文档定义 |
| omitted_categories | ✅ | — | — | ⚠️ 仅 contract 文档定义 |

snapshot 截断合同的细节集中在 09-snapshot-contract.md 中，api-registry 仅引用了 cap 值——这是合理的设计（contract 文档是权威细节源）。但建议在 api-registry §5 的 Per-player snapshot 行旁添加 contract 文档引用。

---

## Summary

R17 的权威单源架构整体闭合良好——api-registry.md 作为 machine-readable single source of truth 有效地消除了大部分 R15-R16 发现的多文档不一致。剩余的主要问题集中在：

1. **结构性** (G1): soft_launch 悬崖——实现前可解决
2. **策略深度** (G2-G4): World 动机真空、aging 硬上限的防御偏向、战术层空间深度——Phase 1 可接受当前范围，Phase 2 需扩展
3. **公平性** (G6): MCP 经济工具 profile 归属——影响 AI vs Human 信息对称
4. **权威源内部分歧** (CrossCheck 3): api-registry 与 interface.md 的 profile 分配冲突——需立即解决

无 REJECT/REQUEST_MAJOR_CHANGES 级别的设计缺陷。Phase 1 实现可在解决 G1 和 CrossCheck 3 的前提下推进。
