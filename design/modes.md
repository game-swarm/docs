# World 模式与 Arena 模式

> 游戏模式域文件。从 design/README.md 拆分。World 模式、Arena 模式、PvE 生态层。

## 9. World 模式 vs Arena 模式

Swarm 提供两种**并行核心玩法**。引擎统一，规则可配置。

| 维度 | World（持久世界） | Arena（竞技场） |
|------|-----------------|-----------------------|
| **本质** | 有机世界，类似 Minecraft 服务器 | 限时对决，类似围棋对局 |
| **状态** | ✅ 核心 | ✅ 核心 |
| **地图** | 随机生成，不同玩家不同起点 | 对称初始条件，双方公平 |
| **加入时机** | 随时，先来后到不同 | 由房主控制开始时间 |
| **公平性** | 不追求——天然不对称 | 核心追求——对称起点 + 相同规则 |
| **运行方式** | 7x24 tick 循环 | 固定时长，比赛结束即销毁 |
| **代码** | 随时更新（热重载） | 房间创建时锁定每个槽位的 WASM |
| **玩家** | 人类和 AI agent 共存 | 对抗的主体是**算法**而非玩家。每个槽位绑定一个 WASM 模块——同一玩家可部署多个算法互相对战，也可邀请他人加入某个槽位 |
| **旁观** | public_spectate 控制 | 由房间可见性控制 |
| **回放** | 自身可见，隐私分级 | 赛后生成回放（房间公开则回放公开） |
| **关注点** | 持久性、创造力、涌现玩法 | 算法对抗、策略测试、演示观赏 |
| **胜利条件** | 无——类似 MMO 持续沙盒，玩家自行设定目标（建造、控制、经济、社交）。不存在"游戏结束"状态 | **房间可配置**（房主在创建时选择）：`fixed_ticks`（达到 tick 上限后按剩余资产判定：drone数→建筑数→资源量→平局）、`destroy_all_structures`（摧毁敌方所有建筑）、`full_wipe`（消灭所有敌方 drone + 建筑）、`capture_points_consecutive`（连续控制据点 N tick）、`capture_points_cumulative`（累计控制据点 N tick） |
| **PvE** | ✅ 世界生态层（中立 NPC、资源据点、世界事件、NPC 掉落） | ✅ 挑战模式（PvE scenario，计时评分） |
| **领土平衡** | Empire upkeep 默认启用（protocol hook + Vanilla 公式），服主可关闭/替换。World 不设竞争榜单 | N/A |

### 9.0 World PvE 生态层

PvE 不是独立的「内容消耗品」——它是 World 持久经济的**常驻层**，与 PvP 平行运行。NPC 是**可编程目标**：固定 AI 行为、可再生、产出资源。

#### NPC 类型

| NPC | HP | 伤害 | 行为 | 刷新周期 | 掉落 |
|-----|----|------|------|---------|------|
| **Creep**（野怪） | 50 | 10/tick | 固定巡逻路径（房间内），攻击进入视野的 drone | 50 tick | Energy 10-30 |
| **Guardian**（远古守卫） | 300 | 30/tick | 驻守固定位置（资源据点），不巡逻 | 300 tick | Crystal 5-15 + 蓝图（5%） |
| **Merchant**（游商） | 200 | 0 | 按固定路线跨房间移动，到站停 20 tick | 500 tick | 不可攻击——与之交互触发交易事件 |
| **Swarmling**（虫群） | 20 | 5/tick | 群体出现（10-30 只），向最近玩家基地移动 | 事件触发 | Energy 5-10/只 |

NPC 行为由引擎内置 AI 驱动（非 WASM）——确定性、可回放、不消耗玩家 fuel。

#### 资源据点

| 据点类型 | 守卫 | 产出 | 说明 |
|---------|------|------|------|
| **富矿 (Rich Vein)** | 2 Guardian | Crystal ×2000，再生 50/tick | 高产出但需清除守卫 |
| **遗迹 (Ancient Ruins)** | 3 Guardian + 5 Creep | 随机蓝图 ×1 + Energy 3000 | 一次性——采集后变为普通房间 |
| **能量泉 (Energy Spring)** | 1 Guardian | Energy ×5000，再生 100/tick | 占领后持续产出 |

资源据点在房间生成时随机分布（密度约 1 据点 / 25 房间）。守卫必须被击败后据点才可采集/占领。

#### 世界事件

| 事件 | 触发条件 | 效果 | 持续时间 |
|------|---------|------|---------|
| **虫群入侵 (Swarm Invasion)** | 随机——每 1000 tick 概率 10% | 玩家密度最高区域生成 30 Swarmling，向各基地移动 | 200 tick |
| **资源爆发 (Resource Boom)** | 随机——每 500 tick 概率 15% | 全局 Energy/Crystal 再生 ×2 | 100 tick |
| **遗迹激活 (Ruin Awakening)** | 任意玩家 drone 进入遗迹房间 | 生成 3 Guardian + 10 Creep，广播全服事件 | 一次性——NPC 击杀后结束 |
| **游商到来 (Merchant Arrival)** | 定时——每 2000 tick | Merchant 出现在随机新手区房间，停留 100 tick | 100 tick |

所有事件确定性触发：`event_seed = Blake3(world_seed || tick_number || event_type)`，`trigger = (event_seed[0] < threshold)` ——相同 seed 可复现。

#### NPC 掉落经济

| 掉落 | 来源 | 用途 |
|------|------|------|
| Energy / Crystal | 所有 NPC | 基础资源 |
| 蓝图 (Blueprint) | Guardian (5%) | 解锁特殊身体部件或建筑配方（仅 PvE 产出） |
| NPC 残骸 (Wreckage) | Guardian (100%) | 回收获取 `body_cost × 20%` Energy |

**经济约束**：NPC 掉落总量不超过世界资源池注入上限——`max_pve_output_per_tick` 可配置（默认 = 全局 NPC 产出 / tick ≤ 世界再生总量 × 30%）。防止「刷怪经济」压倒 PvP 战略价值。

#### 难度梯度

```
房间距世界中心越远 → NPC 等级越高 → 产出越高
  Zone 1 (中心):     Creep ×1-2/room, 无 Guardian
  Zone 2 (中层):     Creep ×3-5/room, Guardian ×0-1/room
  Zone 3 (外层):     Creep ×5-8/room, Guardian ×1-2/room, 富矿出现
  Zone 4 (边境):     Creep ×8-12/room, Guardian ×2-4/room, 遗迹出现
```

玩家通过扩张自然遭遇更强 PvE——不需要「副本入口」或「排队系统」。PvE 难度是**地理属性**。

> **扩展方向**：深度 PvE（Boss 战多阶段 AI、副本区域链、阵营声望、讨伐进度）不作为原生引擎内容——属于 overhaul 模组范畴。模组可通过 Rhai `actions.*` API（见 specs/core/07-world-rules.md §5.1 能力命名空间）注册自定义 NPC 行为、Boss 阶段触发器和声望系统。引擎仅提供 NPC 实体基础设施（HP、伤害、巡逻/驻守 AI、掉落表、事件钩子）——不硬编码 Boss 机制。

### 9.1 Arena 房间模型

Arena 以**房间制比赛为核心**——玩家创建比赛房间，设定参数，自己或他人加入，比赛结束后生成 room match_result（赛果摘要）。无需自动匹配、天梯排名、赛季组织等上层编排。Arena 的定位是**轻量房间制测试场**：玩家用 WASM 算法在隔离房间中对战，赛后获得 match_result 反馈。

#### 9.1.1 创建与加入

```
房主创建房间
    |
    +-- 设定参数（地图、时长、初始资源）
    +-- 选择可见性（public / unlisted / private）
    +-- 分配槽位——每个槽位指定一个 WASM 模块
    |   槽位 A: 自己的主策略
    |   槽位 B: 自己的实验策略（或留空等他人加入）
    |
    v
房间就绪 -> 房主点击开始 -> 双方代码锁定 -> 比赛执行
```

**关键特性**：同一玩家可以占据多个槽位——在 Arena 中用不同算法自我对抗，测试策略优劣。也可以开放槽位邀请他人对战。

#### 9.1.2 房间配置

```toml
[arena]
enabled = true
max_rooms = 10                   # 服务器最多同时运行的 Arena 房间

[arena.defaults]
match_duration = 5000            # 默认比赛 tick 数
tick_interval_ms = 300           # Arena tick 间隔
slots = 2                        # 默认槽位数（当前仅支持 1v1）
initial_resources = { Energy = 10000, Crystal = 5000 }
map_symmetry = "rotational"      # rotational | mirror
```

**创建房间时的可选项**：

| 参数 | 默认 | 说明 |
|------|------|------|
| match_duration | 5000 tick | 比赛时长 |
| initial_resources | 默认配置 | 双方初始资源 |
| map_seed | 随机 | 地图种子（相同种子 = 相同地图，可复现对决） |
| visibility | public | public（列表可见）/ unlisted（有链接可进）/ private（仅受邀） |
| allow_spectate | true | 是否允许旁观 |
| spectate_delay | 100 tick | 旁观延迟（实时旁观 vs 延迟播放） |
| spectate_privacy | public | public（任何人可旁观）/ participants（仅参与者）/ private（仅房主） |

#### 9.1.3 比赛流程

```
Create -> Configure -> Ready -> Play -> Finish -> Replay
   |          |          |        |        |         |
  创建房间   设参数     双方就绪  比赛中   结算      回放生成
           选WASM     锁定代码          结果展示    (可公开)
```

**终止条件**（按房间配置的 victory_condition，优先级由配置决定）：`fixed_ticks` 模式下：tick 到上限按剩余资产判定（drone数→建筑数→资源量）→平局。`destroy_all_structures` 模式下：一方所有建筑被摧毁。`full_wipe` 模式下：一方 drone 全灭 + 建筑全毁。`capture_points` 模式下：达到连续/累计控制 tick 数。

#### 9.1.4 回放

赛后自动生成回放（TickTrace JSONL）。房间 `public` 则回放公开可访问；`unlisted/private` 则仅参与者可见。回放播放器支持速度控制、双视角切换、tick 定位、指令展开。

> **社区传播（RFC）**：分享 URL、战报卡（highlight card）、自动摘要、社区 replay 排行榜为产品扩展项——不阻塞当前设计冻结。

#### 9.1.5 PvE 挑战模式

Arena 除 PvP 对决外，提供 **PvE Challenge** 模式——玩家用 WASM 对抗预设 NPC 场景，按完成时间和效率评分。

**房间类型**：

```
Arena 房间模式:
  ├── PvP (1v1 / NvN)     ← 玩家 vs 玩家
  └── PvE Challenge        ← 玩家 vs NPC 场景
```

**创建 PvE 挑战**：

```toml
[arena]
mode = "pve_challenge"

[arena.pve]
scenario = "guardian_gauntlet"   # 预设场景名
difficulty = 2                   # 1-5，影响 NPC 数量和强度
time_limit = 500                 # 最大 tick 数
map_seed = 12345                 # 地图种子（相同 seed 可复现）
```

**预设场景**：

| 场景 | 描述 | 评分指标 |
|------|------|---------|
| **Guardian Gauntlet** | 地图中心有 5 Guardian + 20 Creep。玩家在一个角落出生，需消灭所有 NPC | 完成 tick、drone 存活数、资源剩余 |
| **Swarm Defense** | 每 50 tick 一波 Swarmling（递增数量）向玩家基地进攻。存活 500 tick | 存活 tick、击杀数、建筑存活 |
| **Resource Race** | 地图散布 10 个富矿，被 Guardian 守卫。采集最多 Crystal | 采集总量、完成时间 |
| **Ruin Siege** | 地图中心遗迹有 Boss NPC（1000 HP、多阶段 AI）。击败 Boss | 完成 tick、伤害效率、drone 损失 |

**评分公式**：

```
PvE Score = base_score × efficiency_multiplier × difficulty_multiplier

base_score = f(scenario, completion)  — 场景特定基础分
efficiency = min(1.0, par_time / actual_time)  — 效率倍率
difficulty = 1.0 + 0.5 × (difficulty - 1)     — 难度倍率

最终: 1000 × efficiency × difficulty + bonus
bonus: 全部 drone 存活 +100，全建筑存活 +50
```

**PvE 排行榜**：按 scenario + difficulty 分组，全局排名。同一玩家可多次挑战刷新分数。排行榜不跨 scenario 混合——每个场景独立排名。

**PvE NPC AI 来源**：挑战模式 NPC 使用引擎内置 AI（与 World PvE 相同 NPC 行为系统），非 WASM。确定性保证：相同 `(scenario, difficulty, map_seed, player_commands)` → 相同结果 → 可回放。

**与 World PvE 的关系**：Arena PvE Challenge 是**隔离沙盒**——不影响 World 状态、不产出 World 资源、不消耗 World 资产。纯粹用于算法测试和排行榜竞争。World 中的 PvE 内容（§9.0）不需要 Arena Challenge 来访问——两者是平行的 PvE 出口。

---
