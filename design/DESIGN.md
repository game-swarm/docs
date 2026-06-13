# Swarm — 设计文档

> **Swarm** 是一个开源的、可编程的 MMO RTS 游戏引擎。它是 [Screeps](https://screeps.com/) 的精神续作，用现代技术栈从零重构，支持多语言。
>
> — *「你的代码就是你的军队。Write once, fight forever.」*

---

## 1. 愿景

### 1.1 核心理念

Swarm 是一个**编程竞技场**——玩家编写真实代码来控制自主单位（drone），在一个持久共享世界中运行。与传统 RTS 不同，Swarm 的胜负不取决于手速，而取决于**算法思维、系统设计和资源优化**。

Swarm 支持两种玩家：
- **人类程序员**：通过 Web UI（Monaco 编辑器 + PixiJS 渲染）编写代码，编译为 WASM 部署
- **AI agent**：通过 MCP 接口查看世界、生成代码、部署 WASM——与人类走完全相同路径

世界只认 WASM。不论代码是谁写的。

### 1.2 与 Screeps 的关键区别

| 维度 | Screeps | Swarm |
|------|---------|-------|
| **玩家语言** | 仅 JavaScript | **任意语言 → WASM** |
| **沙箱** | V8 Isolate (isolated-vm) | WASM + WASI（Wasmtime，独立进程隔离） |
| **资源计量** | 墙钟 CPU 限制 | **CPU 指令计数**（fuel metering） |
| **游戏模型** | OOP 脚本模式 | **ECS**（Bevy）— 确定性、可并行、可回放 |
| **性能** | 受限于 V8 GC | WASM 原生速度，同等配额快 10-100 倍 |
| **AI 玩家** | 无原生支持 | **MCP 原生界面**——AI 写 WASM，同人类 |
| **扩展性** | 仅 JS mod | WASM 多语言 SDK + 插件系统 |
| **客户端** | Web + Steam 封装浏览器 | Web（Monaco + PixiJS）+ MCP（AI 界面） |

### 1.3 设计原则

1. **语言无关**：引擎不知道也不关心玩家代码是什么语言写的。一切编译为 WASM。
2. **确定性核心**：相同初始状态 + 相同玩家指令 → 相同世界状态。支撑回放、调试和反作弊。
3. **公平资源核算**：CPU 配额度量为 WASM 指令数，非墙钟。C 玩家和 Python 玩家在相同配额下获得同等算力。AI 玩家和人类玩家同走 WASM 沙箱，天然公平。
4. **可组合架构**：ECS 允许新增游戏机制时无需触碰既有代码。
5. **开源首日**：MIT 许可证。

---

## 2. 系统架构

### 2.1 整体架构图

```
┌──────────────────────────────────────────────────────────┐
│                        客户端                               │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐ │
│  │ Web Client   │  │ Desktop App   │  │ CI/CD Pipeline   │ │
│  │ (Monaco +    │  │ (Tauri)       │  │ (GitHub Actions) │ │
│  │  PixiJS)     │  │               │  │                  │ │
│  └──────┬───────┘  └──────┬───────┘  └────────┬────────┘ │
│         │                 │                    │           │
│  ┌──────┴─────────────────┴────────────────────┴────────┐ │
│  │                   MCP Interface (AI 玩家)              │ │
│  │  AI agent 查看世界 · 生成代码 · 部署 WASM · 调试       │ │
│  └────────────────────────┬─────────────────────────────┘ │
└───────────────────────────┼───────────────────────────────┘
                            │
            WebSocket + REST │ HTTPS (MCP)
                            ▼
┌─────────────────────────────────────────────────────────┐
│                   网关 (Go)                                │
│  ┌──────────────┐  ┌─────────────┐  ┌───────────────┐  │
│  │ WS Hub        │  │ Auth (OAuth) │  │ API Router     │  │
│  └──────────────┘  └─────────────┘  └───────────────┘  │
└────────────────────────┬────────────────────────────────┘
                         │ gRPC + NATS
                         ▼
┌─────────────────────────────────────────────────────────┐
│                Tick 引擎 (Rust)                            │
│                                                           │
│  ┌──────────────────────────────────────────────────┐   │
│  │              Tick 调度器                            │   │
│  │  Tick N-1 完成 → Tick N 分发 → Tick N+1           │   │
│  └──────────────────────┬───────────────────────────┘   │
│                         │                                 │
│          ┌──────────────┼──────────────┐                 │
│          ▼              ▼              ▼                  │
│  ┌─────────────┐ ┌────────────┐ ┌──────────────┐        │
│  │ Sandbox     │ │ Sandbox    │ │ Sandbox      │  ...   │
│  │ Worker 1    │ │ Worker 2   │ │ Worker 3     │        │
│  │ (独立进程)   │ │ (独立进程)  │ │ (独立进程)    │        │
│  │ WASM 玩家 1 │ │ WASM 玩家2 │ │ WASM 玩家 3  │        │
│  └──────┬──────┘ └─────┬──────┘ └──────┬───────┘        │
│         │              │               │                 │
│         ▼              ▼               ▼                 │
│  ┌──────────────────────────────────────────────────┐   │
│  │         指令收集器 + 校验器 + 反作弊               │   │
│  │    (去重、冲突解决、反作弊)                        │   │
│  └──────────────────────┬───────────────────────────┘   │
│                         │                                 │
│  ┌──────────────────────▼───────────────────────────┐   │
│  │              Bevy ECS 世界                         │   │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌───────────┐  │   │
│  │  │ 移动   │ │ 战斗   │ │ 经济   │ │ 建造      │  │   │
│  │  │ System │ │ System │ │ System │ │ System    │  │   │
│  │  └────────┘ └────────┘ └────────┘ └───────────┘  │   │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌───────────┐  │   │
│  │  │ 视野   │ │ 资源   │ │ 寻路   │ │ 死亡      │  │   │
│  │  │ System │ │ System │ │ System │ │ System    │  │   │
│  │  └────────┘ └────────┘ └────────┘ └───────────┘  │   │
│  └──────────────────────────────────────────────────┘   │
│                                                           │
│  ┌───────────────────┐  ┌───────────────┐                 │
│  │ MCP Server        │  │ Debug/Trace   │                 │
│  │ (rmcp, HTTP/SSE)  │  │ Collector     │                 │
│  └───────────────────┘  └───────────────┘                 │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                   数据层                                   │
│  ┌──────────────┐  ┌─────────────┐  ┌───────────────┐  │
│  │ FoundationDB  │  │ Dragonfly    │  │ ClickHouse     │  │
│  │ (世界状态)    │  │ (热缓存)     │  │ (分析 + 审计)  │  │
│  └──────────────┘  └─────────────┘  └───────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 2.2 仓库结构

```
swarm/
├── docs/           # 设计文档、P0 规范、评审报告
│   ├── design/     #   架构设计
│   ├── specs/      #   技术规范
│   └── reviews/    #   评审报告
├── engine/         # Rust 游戏引擎 — Bevy ECS, Tick 调度, 世界模拟
├── sandbox/        # WASM 沙箱运行时 — 编译服务, 模块管理, 安全审计
├── gateway/        # Go API 网关 — WebSocket, REST, gRPC, 认证
├── frontend/       # Web 客户端 — Monaco Editor, PixiJS 渲染
├── sdk-ts/         # TypeScript SDK — 游戏 API 类型 + WASM 编译工具链
└── sdk-rust/       # Rust SDK — 游戏 API + wasm-bindgen 工具链
```

---

## 3. Engine（Rust）

**技术栈**：Rust + Bevy ECS + Tokio + FoundationDB

### 3.1 核心 ECS 实体

```rust
// 位置——所有有位置的实体都有此组件
struct Position { x: i32, y: i32, room: RoomId }

// 所有权
struct Owner(PlayerId);

// Drone——玩家的可编程单位
struct Drone {
    owner: PlayerId,
    body: Vec<BodyPart>,       // MOVE, WORK, CARRY, ATTACK 等
    fatigue: u32,              // 疲劳值，0 才能行动
    hits: u32,
    hits_max: u32,
    spawning: bool,
    age: u32,                  // 创建后经过的 tick 数
}

// Structure——建筑
struct Structure {
    structure_type: StructureType,  // Spawn, Extension, Tower, Storage 等
    owner: Option<PlayerId>,
    hits: u32, hits_max: u32,
    energy: Option<u32>,
    energy_capacity: Option<u32>,
    cooldown: u32,
}

// Resource——掉落资源
struct Resource {
    resource_type: ResourceType,  // Energy, Mineral, Power
    amount: u32,
}

// Source——地图上可再生资源点
struct Source {
    energy: u32,
    energy_capacity: u32,
    ticks_to_regeneration: u32,
}

// Terrain——地形
struct Terrain(TerrainType);  // Plain, Swamp, Wall

// Controller——房间控制器（占领/升级）
struct Controller {
    owner: Option<PlayerId>,
    level: u8,
    progress: u32, progress_total: u32,
    downgrade_timer: u32,
    safe_mode: u32,
    safe_mode_available: u32,
    safe_mode_cooldown: u32,
}
```

### 3.2 Tick 生命周期

```
每 tick（目标 3s）：

阶段一：收集 (COLLECT) — 并行, ~2.5s
  ├── 对每个活跃玩家:
  │   ├── 加载玩家 WASM 模块（缓存在内存中）
  │   ├── 序列化可见世界状态 → JSON 快照
  │   ├── 在 sandbox worker 进程中实例化 WASM，fuel limit = 玩家 CPU 配额
  │   ├── 调用 tick(snapshot) → 收集 Vec<Command>
  │   └── 过滤无效指令（超配额、非法操作）
  └── 收集全部指令到指令队列

阶段二：执行 (EXECUTE) — 串行, ~0.5s
  ├── 指令按确定性排序（tick, player_id, sequence）
  ├── 对每条指令:
  │   ├── 对照当前世界状态校验
  │   ├── 合法 → 通过 ECS system 应用变更
  │   └── 冲突 → 丢弃 + 记录 RejectionReason
  ├── 运行 tick 内 ECS systems（战斗、衰减、再生）
  ├── FDB 原子提交（全或无）
  └── tick_counter 推进

阶段三：广播 (BROADCAST) — 即时
  ├── 计算增量（与上一 tick 快照的实体差异）
  ├── Dragonfly 缓存更新
  ├── 通过 NATS → Gateway → WebSocket 客户端发布
  └── 每隔 N tick 记录完整世界快照到 FDB（回放用）
```

### 3.3 确定性保证

```
确定性需要：
1. 相同的初始世界状态
2. 相同的 Command 输入（已排序）
3. ECS System 执行顺序固定（.chain()）
4. 所有随机数来自确定种子 PRNG（不用 OS 熵源）

反作弊：
- 全量回放：任意房间状态可完整重现
- 异常检测：玩家 tick 间的世界变化超过物理上限 → 标记
- WASM 编译时静态分析：扫描可疑系统调用
```

---

## 4. MCP 接口——AI 玩家的操作界面

MCP 是 AI agent 的「屏幕和鼠标」——与人类玩家的 Web UI 完全同级。

```
人类：Monaco 编辑器 → 编译 WASM → 上传 ─┐
                                       ├─→ WasmSandboxExecutor → 世界
AI：  MCP 看世界 → 生成 WASM → 部署 ───┘
```

### 4.1 MCP 工具分类

| 类别 | 工具 | 用途 |
|------|------|------|
| **世界查看** | `swarm_get_snapshot` | 获取可见世界状态 |
| | `swarm_get_terrain` | 查看地形 |
| | `swarm_get_objects_in_range` | 查看范围内的实体 |
| **部署** | `swarm_deploy` | 上传 WASM 模块 |
| | `swarm_validate_module` | 上传前预检 |
| | `swarm_rollback` | 回滚到之前版本 |
| **调试** | `swarm_explain_last_tick` | 解释上 tick 发生了什么 |
| | `swarm_inspect_entity` | 检查实体完整状态 |
| | `swarm_profile` | 策略性能指标 |
| **学习** | `swarm_get_docs` | API 参考和游戏规则 |
| | `swarm_get_schema` | 游戏 API JSON Schema |
| | `swarm_get_available_actions` | 当前可用的 API 函数 |

### 4.2 明确不在 MCP 中

MCP 不做游戏动作。不存在 `swarm_move`、`swarm_attack`、`swarm_build` 等工具。AI agent 必须**编写 WASM 代码**来实现策略，和人类玩家完全一样。

详见 `specs/p0/03-mcp-security-contract.md`。

---

## 5. 游戏 API（WASM Host Function）

以下是在 WASM 沙箱中唯一可调用的函数：

```rust
// 移动
fn host_move(object_id: i64, direction: i32) -> i32;
fn host_move_to(object_id: i64, x: i32, y: i32) -> i32;

// 采集 / 资源
fn host_harvest(object_id: i64, target_id: i64) -> i32;
fn host_transfer(object_id: i64, target_id: i64, resource: i32, amount: i32) -> i32;
fn host_withdraw(object_id: i64, target_id: i64, resource: i32, amount: i32) -> i32;

// 建造
fn host_build(object_id: i64, x: i32, y: i32, structure_type: i32) -> i32;
fn host_repair(object_id: i64, target_id: i64) -> i32;

// 战斗
fn host_attack(object_id: i64, target_id: i64) -> i32;
fn host_ranged_attack(object_id: i64, target_id: i64) -> i32;
fn host_heal(object_id: i64, target_id: i64) -> i32;

// 孵化 / 回收
fn host_spawn(spawn_id: i64, body_parts_ptr: i32, body_parts_len: i32) -> i32;
fn host_recycle(object_id: i64, spawn_id: i64) -> i32;

// 信息查询（计入 fuel 预算）
fn host_get_terrain(x: i32, y: i32) -> i32;
fn host_get_objects_in_range(x: i32, y: i32, range: i32, out_ptr: i32, out_len: i32) -> i32;
fn host_path_find(from_x: i32, from_y: i32, to_x: i32, to_y: i32, out_ptr: i32, out_len: i32) -> i32;
```

全部返回 `i32`：0 = 成功，负数 = 错误码。

---

## 6. 数据模型

### 6.1 FoundationDB — 世界状态

```
/tick/{N}/state          → tick N 后的完整世界状态
/tick/{N}/commands       → 全部玩家的排序指令
/tick/{N}/rejections     → 被拒绝的指令及原因
/tick/{N}/metrics        → tick 指标
/player/{id}/profile     → 玩家档案
/player/{id}/modules/    → WASM 模块历史
```

### 6.2 Dragonfly — 热缓存

- 当前 tick 世界状态快照（高频读取）
- 玩家 session 映射（WS 连接 → player_id）
- 排行榜缓存（每分钟刷新）
- Rate limiting 计数器

### 6.3 ClickHouse — 分析

```sql
-- tick 指标
tick_metrics:    tick, player_id, cpu_fuel, cmd_count, cmd_success, latency_ms

-- MCP 审计
mcp_audit:       timestamp, player_id, tool_name, parameters, result

-- 游戏事件
player_events:   tick, player_id, event_type, entity_id, detail
```

---

## 7. 部署架构

### 7.1 开发环境（docker-compose）

```yaml
services:
  fdb:          # FoundationDB
  dragonfly:    # Redis 兼容缓存
  engine:       # Rust 引擎
  gateway:      # Go 网关
  frontend:     # Vite dev server
```

### 7.2 生产环境

```
┌──────────────────────────────────────────────┐
│              负载均衡 (nginx / Traefik)         │
└──────┬───────────────────────┬───────────────┘
       │                       │
       ▼                       ▼
┌──────────────┐      ┌──────────────┐
│ Gateway-1    │      │ Gateway-2    │ ...  (Go, 无状态, 水平扩展)
└──────┬───────┘      └──────┬───────┘
       │                     │
       └──────────┬──────────┘
                  ▼
┌─────────────────────────────────┐
│         NATS 集群                │
└──────────┬──────────────────────┘
           │
           ▼
┌─────────────────────────────────┐
│     Engine (Rust)                │
│     (每 shard 一个实例)           │
└──────────┬──────────────────────┘
           │
           ▼
┌─────────────────────────────────┐
│   FoundationDB 集群               │
└─────────────────────────────────┘
```

---

## 8. 路线图

### Phase 1: 核心引擎（MVP — 单人沙箱）

- [ ] Bevy ECS 世界模拟（地形、资源、基础单位）
- [ ] WASM 沙箱 + sandbox worker 进程（进程隔离）
- [ ] 基础游戏 API（move, harvest, build, spawn）
- [ ] MCP server 脚手架（swarm_get_snapshot, swarm_deploy）
- [ ] 本地 docker-compose 开发环境
- [ ] TypeScript SDK + Rust SDK（基础 API）

### Phase 2: MCP 完整界面 + 多人世界

- [ ] MCP 完整工具集（世界查看、调试、部署）
- [ ] MCP 认证与限流
- [ ] Tick 调度器（多玩家并行）
- [ ] 指令冲突解决
- [ ] WebSocket 实时推送

### Phase 3: 持久化 + 多房间

- [ ] FoundationDB 持久化（N=1，每 tick 原子提交）
- [ ] Dragonfly 热缓存
- [ ] ClickHouse 指标管线
- [ ] 房间边界 + 多房间

### Phase 4: 调试 + 回放

- [ ] 每 tick 日志 + 回放
- [ ] 状态检查工具
- [ ] WASM 执行追踪
- [ ] 策略指标仪表盘

### Phase 5: 客户端

- [ ] Web 客户端（React + Monaco + PixiJS）
- [ ] 自动生成 API 参考站
- [ ] OAuth2 登录
- [ ] MCP 教程资源（AI 玩家上手指南）

### Phase 6: 游戏化

- [ ] Controller + 房间占领
- [ ] 战斗系统
- [ ] 市场（玩家间交易）
- [ ] 排行榜 + 赛季
- [ ] Arena 模式（1v1 比赛制）

### Phase 7: 生产化

- [ ] 性能优化（sharding, ECS 并行化）
- [ ] 反作弊系统
- [ ] AI 锦标赛编排
- [ ] 自动化测试框架
- [ ] CI/CD Pipeline

---

## 9. World 模式 vs Arena 模式

| 维度 | World（持久世界） | Arena（比赛） |
|------|-----------------|-------------|
| **运行方式** | 7×24 tick 循环 | 固定时长（例：5000 tick） |
| **地貌** | 持久殖民地、房间占领 | 对称初始条件、独立地图 |
| **代码** | 随时更新（热重载） | 比赛开始时锁定 |
| **交互** | PvE + PvP 共存 | 1v1 或团队对决 |
| **胜利条件** | 排行榜排名（GCL、房间数） | 摧毁敌方 Spawn 或最高分 |
| **回放** | 自身可见 | 赛后自动公开 |
| **玩家** | 人类和 AI agent 在同一世界共存 | |

---

## 10. 贡献指南

### 10.1 开发环境搭建

```bash
git clone git@git.kagurazakalan.com:swarm/engine.git
cd engine && docker-compose up
```

### 10.2 代码规范

- Rust: `cargo fmt` + `cargo clippy`（严格）
- Go: `gofmt` + `golangci-lint`
- TypeScript: `prettier` + `eslint`（严格）
- Commit: [Conventional Commits](https://www.conventionalcommits.org/)

---

## 附录 A: 与 Screeps 的 API 兼容性

Swarm 不追求与 Screeps API 兼容。设计哲学不同：

- Screeps API 是面向对象的（`creep.moveTo()`, `Game.spawns['Spawn1']`）
- Swarm API 是功能/数据导向的（`move(creep_id, direction)`, return commands）

但可以通过社区项目构建兼容层，将 Screeps 风格 API 调用包装为 Swarm 指令。

## 附录 B: 为什么不用现有 Screeps 方案？

| 关注点 | Screeps | Swarm |
|--------|---------|-------|
| 语言锁定 | 仅 JS | 任意 WASM 语言 |
| 性能上限 | V8 + GC 停顿 | WASM 原生速度 |
| CPU 计量精度 | 墙钟（系统依赖） | Fuel metering（确定性） |
| 确定性 | 不保证 | 设计目标 |
| AI 玩家 | 无 | MCP 原生界面 |
| 代码年代 | 2014 起步，Node.js 8 | 2026，Rust + WASM |
| 许可证 | 混合（server 开源，client 专有） | MIT（完全开源） |

---

*最后更新: 2026-06-14*
