# 反馈循环规范 — Feedback Loop

> 详见 design/modes.md

## 1. 反馈循环

玩家的体验是一个闭环。系统必须为人类和 AI 玩家同时闭合：

```
      学习 (LEARN)    →      决策 (DECIDE)     →      行动 (ACT)
  "规则是什么？        "看到当前世界，          "提交本 tick
   我能做什么？"        我应该做什么？"           的指令"
        ↑                                              │
        │                                              │
        └────────── 理解 (UNDERSTAND) ←────────────────┘
                  "发生了什么？
                   我的指令成功了吗？
                   为什么失败？为什么输了？"
```

这四步任何一步断裂，游戏就不可玩。

## 2. 学习：上手引导

### 2.1 人类程序员（5 分钟教程）

```
1. 打开 Web 客户端 → 教程房间（独立、隔离）
2. 教程 bot（预写、可编辑）自动运行
3. 逐步引导覆盖层:
   - "这是你的 Spawn。你可以在这里创建 drone。"
   - "试试把 'spawn_count = 1' 改成 'spawn_count = 3'"
   - "你的 drone 在采集！看着它们收集能量。"
   - "在 (5,3) 放一个 Tower 来防守。"
4. 引导式代码修改 + 即时反馈（教程 tick 间隔 1s）
5. 提示: "你准备好了！部署到 World 或试试 Arena。"
```

### 2.2 AI 玩家（MCP 教程）

```
AI agent 连接 → swarm://docs/tutorials/basic-agent
返回逐步 MCP 交互指南:

1. 调用 swarm_get_snapshot → 查看当前世界状态（相当于人类的「看地图」）
2. 调用 swarm_get_available_actions → 了解可用的游戏 API 函数
3. 调用 swarm_get_docs → 学习 API 参考和游戏规则
4. 生成代码（AI 用自己的能力写 WASM）→ 调用 swarm_validate_module 预检
5. 调用 swarm_deploy → 上传编译好的 WASM 模块
6. 观察世界变化（swarm_get_snapshot）→ 调试（swarm_explain_last_tick）→ 改进代码
7. 重复 4-6

示例开发循环（伪代码）:
  snapshot = mcp.call("swarm_get_snapshot")
  api_docs = mcp.call("swarm_get_docs")
  wasm_code = generate_wasm(snapshot, api_docs, strategy)  // AI 写代码
  mcp.call("swarm_validate_module", {wasm: wasm_code})      // 预检
  mcp.call("swarm_deploy", {wasm: wasm_code, version: "v2"}) // 部署
  // 等待几 tick...
  explanation = mcp.call("swarm_explain_last_tick")          // 看结果
  // 改进代码，再部署
```

**关键**：AI agent 不是通过 MCP 直接操作 drone——它编写 WASM 代码，drone 由代码控制。这和人类玩家完全相同。

### 2.3 Starter Bot

各 SDK 提供：

| 语言 | Bot | 说明 |
|------|-----|------|
| TypeScript | `basic-harvester` | 3 架 drone，采集最近源，运回能量 |
| TypeScript | `tower-defense` | 建造 Tower，基础防守 |
| TypeScript | `room-claimer` | 占领房间，升级 Controller |
| Rust | `basic-harvester` | 同 TS 版 |
| MCP (AI) | `basic-agent` | 演示 MCP tick 循环的 Python 脚本 |

Starter bot 必须开箱即编译/运行。一键部署：
```
swarm deploy ./basic-harvester
```

### 2.4 First-Hour 过渡：从教程到参与

教程（§2.1-2.3）覆盖前 5 分钟的「按钮在哪」，但新玩家在 safe_mode 结束后到首次 PvP 接触之间存在**体验真空**——可能数小时独自优化，然后突然被碾压。

#### 渐进式威胁曲线

```
Tick 0-500:     safe_mode（房间无敌）          → 纯学习，无压力
Tick 500-2000:  soft_launch 阶段                → 仅 PvE 威胁（中立 NPC、资源竞争）
Tick 2000+:     正常 PvP                         → 完整玩家交互
```

`soft_launch` 阶段机制：

| 机制 | 说明 |
|------|------|
| **中立 NPC 据点** | 新手房间附近生成低威胁中立 drone（固定巡逻路径、低 HP），玩家可练习 combat |
| **限时资源潮 (Resource Surge)** | 每隔 200 tick 在新手区域随机刷新高密度资源点——鼓励探索和轻竞争（多人抢同一资源潮） |
| **新手区公共事件** | 广播事件："x=15,y=20 发现古代遗迹，前 3 个到达的 drone 获得 500 Energy"——诱导玩家离开基地 |
| **PvP 警告广播** | soft_launch 结束后 50 tick 前，全局广播 "PvP 保护将在 50 tick 后解除"，给玩家心理准备 |

#### 低风险社交冲突

在 full PvP 之前引入零和但非毁灭性的互动：

| 机制 | 风险等级 | 说明 |
|------|:--:|------|
| **资源抢占** | 低 | 多人抢同一 Source / Resource Surge——先到先得，但不损失已有资产 |
| **房间占领竞速** | 低 | 多玩家试图 Claim 同一中立房间——输家仅损失 Claim drone，不损失基地 |
| **Arena Challenge 嵌入 World** | 低 | 玩家可在 World UI 中向附近玩家发起小型 Arena 挑战（1v1, 100 tick, 对称初始资源）——输赢不影响 World 资产 |

#### AI Agent 首次部署引导

AI agent 的 onboarding 瓶颈不在教程——在「部署后看不到反馈」：

```
AI 首次部署流程:
  1. MCP 连接 → swarm_deploy → WASM 上传成功
  2. ⚠️ 真空: 等待 tick 执行 → 不知道 drone 是否在动
  3. 解决方案: 部署后通过 polling 查询部署状态和事件:
     - swarm_get_deploy_status → 检查部署是否已激活（compiled → active）
     - swarm_get_events → 按需拉取"deploy_accepted"和"first_tick_executed"事件
  4. AI 无需事件订阅——通过 polling pattern 获取反馈，保持轻量
```

AI agent 开发循环强化：


| 工具 | 用途 | 首次部署专用 |
|------|------|:--:|
| `swarm_deploy` | 上传 WASM | 返回 `deploy_id` 用于追踪 |
| `swarm_get_deploy_status` | 查询部署状态 | 轮询获取 compiled→active 状态转换 |
| `swarm_explain_last_tick` | 解释上一 tick 执行结果 | AI 首个 tick 后自动调用——回答"我的 drone 做了什么？" |
| `swarm_get_snapshot` | 查看世界状态 | 确认 drone 位置、HP、资源变化 |
| `swarm_dry_run` | 预测指令结果 | 部署前验证——不用等 tick 才知道逻辑错误 |
| `swarm_get_events` | 按需拉取事件 | 获取 deploy_accepted、first_tick_executed 等里程碑事件 |

> **采用 polling-based 反馈模型**：MCP 不提供 Agent-facing 事件订阅。AI agent 通过 `swarm_get_deploy_status` + `swarm_get_events` 轮询获取反馈；SSE 仅作为 Gateway/Engine 内部事件通道，不暴露为 MCP subscription。
#### 人类玩家首次 PvP 引导

```
首次被攻击时:
  1. UI 弹出 "你的一架 drone 正在被攻击！" 通知
  2. 一键跳转到战斗位置（地图聚焦）
  3. 提供反制建议: "你可以: [移动逃离] [反击] [呼叫友方 drone]"
  4. 战斗结束后显示 "战斗报告": 谁攻击了你、损失了什么、对方的可见信息
  5. 引导到 Arena Challenge: \"想练习 PvP 但不想冒风险？向攻击者发起 Arena 挑战\"
```

### 2.5 Onboarding 验收标准

以下 golden path 必须在 CI smoke test 中自动化验证——不仅是文档承诺：

#### 人类玩家验收

| 步骤 | 验收条件 | 目标时间 |
|---|---|---|
| 1. 进入教程房间 | Web 客户端加载完成后 10s 内显示教程 overlay | <30s 从打开到教程开始 |
| 2. 修改 spawn_count | 代码修改 → 保存 → drone 数量变化在 3 tick 内可见 | <15s |
| 3. 部署到 World | 从教程点击"部署到世界" → starter bot 在 World 中运行 | <60s |
| 4. 首次 safe_mode 结束 | 玩家收到 soft_launch 过渡通知 | 自动（tick 500） |
| 5. 首次 PvP 接触 | 战斗报告弹出一键可达 | 首次被攻击时 |

#### AI Agent 验收

| 步骤 | MCP 调用序列 | 验收条件 |
|---|---|---|
| 1. 发现 API | `swarm_get_schema` → `swarm_get_docs` → `swarm_get_available_actions` | 三次调用全部返回 200，schema 与当前世界 manifest hash 一致 |
| 2. 生成并校验代码 | `swarm_validate_module` | 返回 `valid: true` 或具体错误列表 |
| 3. 部署 | `swarm_deploy` | 返回 `deploy_id`，状态 `compiled` → `active` |
| 4. 首次 tick 反馈 | 部署后通过 `swarm_get_deploy_status` 轮询获得 `status=active` | `swarm_get_events` 返回 `first_tick_executed`，含 drone_count > 0 |
| 5. 调试循环 | `swarm_explain_last_tick` → 修改代码 → `swarm_deploy` | 完成至少 1 次完整改进循环 |

#### Starter Bot Smoke Test（CI 集成）

每个 starter bot 必须在 CI 中通过：

```
1. 编译（TS: npx asc / Rust: cargo build --target wasm32-unknown-unknown）
2. schema 校验（swarm_validate_module 返回 valid: true）
3. dry-run（`swarm_dry_run` 在 tutorial world snapshot 上执行，无拒绝码）
4. 部署到 tutorial world（swarm_deploy → 等待 first_tick_executed）
```

Starter bot 代码中的字段名（`sequence`, `Spawn`, `MoveTo` 等）由 IDL 自动生成，禁止手写——通过 CI 交叉校验 `starter bot 源码` vs `game_api.idl` 的 schema。

## 3. 决策：信息与工具

### 3.1 MCP 发现型 Verb

| 工具 | 用途 |
|------|------|
| `swarm_get_available_actions` | "我现在能做什么？" 返回当前状态下的可能动作列表 |
| `swarm_get_snapshot` | 完整可见世界状态 |
| `swarm_dry_run` | "如果我提交这些指令，会成功吗？" snapshot-bound non-authoritative dry-run |
| `swarm://docs/api-reference` | 完整 API 参考（MCP 资源） |

### 3.2 人类 IDE 功能

```
- Monaco 编辑器，内置游戏 API 的完整 TypeScript 类型
- 实体字段自动补全（drone.fatigue, source.energy 等）
- 行内校验："drone.harvest() 需要 WORK 部件，你的 drone 是 [MOVE, CARRY]"
- 一键部署
- 版本历史（回滚到之前的 bot）
```

### 3.3 本地模拟

```
swarm sim --ticks=5000 --speed=100x
```

本地运行 5000 tick，100 倍速。无需连接服务器。
输出：最终状态 + 指标（采集能量、建造数、战斗结果）。
迭代周期：改代码 → `swarm sim`（10s）→ 看结果 → 再改。

## 4. 行动：代码部署

### 4.1 部署渠道

| 玩家类型 | 渠道 |
|---------|------|
| 人类 | Web UI（编辑器中一键部署）或 CLI `swarm deploy` |
| AI (MCP) | MCP `swarm_deploy` 工具 |

引擎收到新 WASM 模块后，在下一 tick 自动切换到新模块。替换前模块保留作为回滚目标。

### 4.2 部署流程

```
1. 编写代码（人类手写 / AI 生成）
2. 编译为 WASM（本地工具链 / AI 自身编译能力）
3. 预检（swarm_validate_module）← 可选
4. 上传（swarm_deploy）→ 引擎加载 → 下一 tick 生效
5. 观察结果 → 迭代
```

没有「直接提交指令」的通道——所有游戏动作必须经过 WASM 沙箱中的代码执行。

## 5. 理解：调试与回放

### 5.1 每 Tick 解释

```
GET /specs/reference/v1/ticks/4521/explanation?player=42
```

```json
{
  "tick": 4521,
  "commands_submitted": 5,
  "commands_accepted": 4,
  "commands_rejected": [
    {
      "command": "attack target=1002",
      "reason": "OutOfRange",
      "detail": "你的 drone 在 (5,3)，目标在 (5,8)。距离 5，最大 1。",
      "suggestion": "将 drone 移至目标 1 格以内，或使用 RangedAttack（范围 3）。"
    }
  ],
  "state_changes": [
    "drone_1001: 移动 (5,3) → (5,2)",
    "drone_1001: 从 source_4001 采集 5 能量",
    "drone_1002: 在 (12,8) 建造 Extension — 15/100 进度"
  ],
  "notable_events": [
    "source_4001 枯竭 — 寻找新能量源",
    "敌方 drone_9001 在 (20,1) 进入你的房间"
  ]
}
```

### 5.2 「为什么闲置？」调试

```
Drone 1003 本 tick 未行动。原因:
- 疲劳值: 5（必须为 0 才能行动）
- 无 WORK 身体部件（采集/建造/维修需要）
- 范围内无目标（最近能量源距离 8，最大采集范围 1）
```

### 5.3 回放查看器

```
玩家视角:
  - 地图 + 时间滑块（tick 4000 → 5000）
  - 播放/暂停/步进控制
  - 覆盖层：指令箭头、采集动画、战斗效果
  - 侧边栏：选中实体每 tick 的状态
  - "分享回放" → 公开 safe view URL

观战视角（赛后）:
  - 全知视角（双方可见）
  - Fog-of-war 切换（显示各玩家实际所见）
  - 解说覆盖层（在特定 tick 添加文字注释）
```

### 5.4 策略指标仪表盘

```
每玩家、每次部署:
  ┌─────────────────────────────────────┐
  │  能量效率:      92%                 │
  │  指令成功率:    85%                 │
  │  平均活跃 Drone: 8.2                │
  │  GCL 增长率:    +120/tick           │
  │  战斗胜率:      67%                 │
  │                                     │
  │  常见错误:                          │
  │    OutOfRange:    23%               │
  │    Fatigued:      12%               │
  │    CarryFull:      8%               │
  └─────────────────────────────────────┘
```

自身可见。可选公开分享（竞技情报）。

## 6. World 模式 与 Arena 模式

### World 模式（持久世界）

- 7×24 tick 循环（3s 间隔）
- 地图随机生成，持久殖民地、房间占领、资源经济
- 玩家随时加入，起点不同——**不追求公平性**
- PvE + PvP 共存
- 代码随时更新（热重载）
- 人类和 AI agent 在同一世界共存
- 趣味展示（非竞争排名）：殖民地年龄、GCL、房间数——仅供观赏

### Arena 模式（房间制比赛）

- 房间制，玩家创建比赛房间，设定参数，自己或他人加入
- 对称初始条件，双方公平
- 独立房间/地图
- 胜利条件：摧毁敌方 Spawn，或时限结束时分高者胜
- 代码在比赛开始时锁定（赛中不可改）
- 赛后自动发布回放
- 无自动匹配、无天梯排名、无赛季
- Tournament/League 为上层编排，通过多场 Room Match 组合实现（Out-of-Scope，后续 Stage 交付）

## 7. 功能清单

- 教程房间（人类）
- MCP 教程资源（AI）
- 3 个 starter bot（TS + Rust + MCP）
- `swarm_get_available_actions` MCP 工具
- `swarm_dry_run` MCP 工具
- `swarm_explain_last_tick` MCP 工具
- 每 tick 指令解释
- 本地模拟 (`swarm sim`)
- 回放查看器（自身）
- 回放查看器（公开）
- 策略指标仪表盘
- Arena 模式（房间制比赛）
- 回放排行榜（非竞争展示）
- 观战解说
