# P0-6: MVP 反馈循环规范

> **状态**: Phase 2 阻断项 | **裁决**: D1 (UX verbs), D3 (公开 replay) | **模式**: World + Arena 双模式

## 1. MVP 反馈循环

玩家的体验是一个闭环。MVP 必须为人类和 AI 玩家同时闭合：

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

## 3. 决策：信息与工具

### 3.1 MCP 发现型 Verb

| 工具 | 用途 |
|------|------|
| `swarm_get_available_actions` | "我现在能做什么？" 返回当前状态下的可能动作列表 |
| `swarm_get_snapshot` | 完整可见世界状态 |
| `swarm_validate_plan` | "如果我提交这些指令，会成功吗？" 预演校验 |
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

引擎收到新 WASM 模块后，在下一 tick 自动切换到新模块。旧模块保留作为回滚目标。

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
GET /api/v1/ticks/4521/explanation?player=42
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
- 持久殖民地、房间占领、资源经济
- PvE + PvP 共存
- 排行榜：GCL、房间数、存活时长
- 代码随时更新（热重载）
- 人类和 AI agent 在同一世界共存

### Arena 模式（1v1 / 团队）

- 比赛制，固定时长（例：5000 tick ≈ 4 小时）
- 对称初始条件
- 独立房间/地图
- 胜利条件：摧毁敌方 Spawn，或时限结束时分高者胜
- 代码在比赛开始时锁定（赛中不可改）
- 赛后自动发布回放
- 锦标赛分组、赛季

## 7. MVP 达成清单

| 功能 | 优先级 | 阶段 |
|------|--------|------|
| 教程房间（人类） | P0 | Phase 1 |
| MCP 教程资源（AI） | P0 | Phase 2 |
| 3 个 starter bot（TS + Rust + MCP） | P0 | Phase 2 |
| `swarm_get_available_actions` MCP 工具 | P0 | Phase 2 |
| `swarm_validate_plan` MCP 工具 | P0 | Phase 2 |
| `swarm_explain_last_tick` MCP 工具 | P0 | Phase 2 |
| 每 tick 指令解释 | P0 | Phase 2 |
| 本地模拟 (`swarm sim`) | P1 | Phase 3 |
| 回放查看器（自身） | P1 | Phase 4 |
| 回放查看器（公开） | P1 | Phase 4 |
| 策略指标仪表盘 | P1 | Phase 4 |
| Arena 模式（比赛制） | P2 | Phase 6 |
| 锦标赛系统 | P2 | Phase 7 |
| 观战解说 | P2 | Phase 7 |
