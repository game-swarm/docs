# Swarm — Design Document

> **Swarm** is an open-source programmable MMO RTS game engine.  
> It is a spiritual successor to [Screeps](https://screeps.com/), redesigned from the ground up with modern technology and multi-language support.
>
> — *"你的代码就是你的军队。Write once, fight forever."*

---

## 1. Vision

### 1.1 核心理念

Swarm is a **programming arena** where players write real code to control autonomous units ("drones") in a persistent, shared world. Unlike traditional RTS games where victory depends on APM (actions per minute), Swarm rewards **algorithmic thinking, system design, and resource optimization**.

### 1.2 与 Screeps 的关键区别

| Dimension | Screeps | Swarm |
|-----------|---------|-------|
| **Player Language** | JavaScript only | **Any language → WASM** |
| **Sandbox** | V8 Isolate (isolated-vm) | WASM + WASI (Wasmtime) |
| **Resource Metering** | Wall-clock CPU limit | **CPU instruction count** (fuel metering) |
| **Game Model** | OOP script-based | **ECS** (Bevy) — deterministic, parallel, replayable |
| **Performance** | Bound by V8 GC | WASM native speed, 10-100x faster at same quota |
| **Extensibility** | JS mods only | WASM plugin system + language SDKs |

### 1.3 设计原则

1. **Language Agnostic** — The game engine does not know or care what language a player's code was written in. Everything compiles to WASM.
2. **Deterministic Core** — Same initial state + same player commands → same world state. Enables replay, debugging, and anti-cheat.
3. **Fair Resource Accounting** — CPU quotas measured in WASM instructions, not wall time. A C player and a Python player with the same quota get the same compute.
4. **Composable Architecture** — ECS enables new game mechanics to be added as Systems without touching existing code.
5. **Open Source from Day 1** — MIT licensed. Community contributions welcome.

---

## 2. System Architecture

### 2.1 整体架构图

```
┌──────────────────────────────────────────────────────────┐
│                   CLIENTS                                 │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐ │
│  │ Web Client   │  │ Desktop App   │  │ CI/CD Pipeline   │ │
│  │ (Monaco +    │  │ (Tauri)       │  │ (GitHub Actions) │ │
│  │  PixiJS)     │  │               │  │                  │ │
│  └──────┬───────┘  └──────┬───────┘  └────────┬────────┘ │
└─────────┼─────────────────┼───────────────────┼──────────┘
          │                 │                   │
          │    WebSocket    │    WebSocket      │  gRPC
          │    + REST       │    + REST         │
          ▼                 ▼                   ▼
┌─────────────────────────────────────────────────────────┐
│                   GATEWAY (Go)                            │
│  ┌──────────────┐  ┌─────────────┐  ┌───────────────┐  │
│  │ WS Hub        │  │ Auth (OAuth) │  │ API Router     │  │
│  │ (per-shard)   │  │              │  │                │  │
│  └──────────────┘  └─────────────┘  └───────────────┘  │
└────────────────────────┬────────────────────────────────┘
                         │ gRPC + NATS
                         ▼
┌─────────────────────────────────────────────────────────┐
│                 TICK ENGINE (Rust)                        │
│                                                           │
│  ┌──────────────────────────────────────────────────┐   │
│  │              Tick Scheduler                        │   │
│  │  Tick N-1 done ──► Tick N dispatch ──► Tick N+1   │   │
│  └──────────────────────┬───────────────────────────┘   │
│                         │                                 │
│          ┌──────────────┼──────────────┐                 │
│          ▼              ▼              ▼                  │
│  ┌─────────────┐ ┌────────────┐ ┌──────────────┐        │
│  │ WASM Sandbox │ │ WASM       │ │ WASM         │  ...   │
│  │ Player 1     │ │ Player 2   │ │ Player 3     │        │
│  └──────┬───────┘ └─────┬──────┘ └──────┬───────┘        │
│         │               │               │                 │
│         ▼               ▼               ▼                 │
│  ┌──────────────────────────────────────────────────┐   │
│  │         Command Collector + Validator              │   │
│  │   (dedup, conflict resolution, anti-cheat)         │   │
│  └──────────────────────┬───────────────────────────┘   │
│                         │                                 │
│  ┌──────────────────────▼───────────────────────────┐   │
│  │              Bevy ECS World                        │   │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌───────────┐  │   │
│  │  │Movement│ │Combat  │ │Economy │ │Construction│  │   │
│  │  │System  │ │System  │ │System  │ │System      │  │   │
│  │  └────────┘ └────────┘ └────────┘ └───────────┘  │   │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌───────────┐  │   │
│  │  │Vision  │ │Resource│ │Pathfind│ │Death       │  │   │
│  │  │System  │ │System  │ │System  │ │System      │  │   │
│  │  └────────┘ └────────┘ └────────┘ └───────────┘  │   │
│  └──────────────────────────────────────────────────┘   │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                   DATA LAYER                              │
│  ┌──────────────┐  ┌─────────────┐  ┌───────────────┐  │
│  │ FoundationDB  │  │ Dragonfly    │  │ ClickHouse     │  │
│  │ (World State) │  │ (Hot Cache)  │  │ (Analytics)    │  │
│  └──────────────┘  └─────────────┘  └───────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 2.2 Repository 结构

```
swarm/
├── docs/           # 设计文档 (this repo)
├── engine/         # Rust 游戏引擎 — Bevy ECS, Tick调度, 世界模拟
├── sandbox/        # WASM 沙箱运行时 — 编译服务, 模块管理, 安全审计
├── gateway/        # Go API 网关 — WebSocket, REST, gRPC, 认证
├── frontend/       # Web 客户端 — Monaco Editor, PixiJS 渲染
├── sdk-ts/         # TypeScript SDK — Game API types + WASM 编译工具链
└── sdk-rust/       # Rust SDK — Game API + wasm-bindgen 工具链
```

---

## 3. 各模块详细设计

### 3.1 Engine (Rust)

**技术栈：** Rust 2024 + Bevy ECS + Tokio

#### 3.1.1 核心 ECS 实体模型

```rust
// === 世界实体 (World Entities) ===

// Drone — 玩家的可编程单位
#[derive(Component)]
struct Drone {
    owner: PlayerId,
    body: Vec<BodyPart>,     // WORK, CARRY, MOVE, ATTACK, etc.
    fatigue: u32,
    hits: u32,
    hits_max: u32,
    spawning: bool,
    age: u32,                // ticks since spawned
}

// Structure — 建筑
#[derive(Component)]
struct Structure {
    structure_type: StructureType,  // Spawn, Extension, Tower, Storage, etc.
    owner: PlayerId,
    hits: u32,
    hits_max: u32,
    energy: Option<u32>,
    energy_capacity: Option<u32>,
    cooldown: u32,
}

// Resource — 掉落资源
#[derive(Component)]
struct Resource {
    resource_type: ResourceType,  // Energy, Mineral, etc.
    amount: u32,
}

// Source / Mineral — 地图上的可再生资源点
#[derive(Component)]
struct Source {
    energy: u32,
    energy_capacity: u32,
    ticks_to_regeneration: u32,
}

// Terrain — 地形
#[derive(Component)]
struct Terrain(TerrainType);  // Plain, Swamp, Wall

// Position — 所有有位置的东西都有这个
#[derive(Component)]
struct Position { x: i32, y: i32, room: RoomId }

// Owner — 所有权
#[derive(Component)]
struct Owner(PlayerId);

// Controller — 房间控制器 (占领/升级)
#[derive(Component)]
struct Controller {
    owner: Option<PlayerId>,
    level: u8,
    progress: u32,
    progress_total: u32,
    downgrade_timer: u32,
    safe_mode: u32,
    safe_mode_available: u32,
    safe_mode_cooldown: u32,
}
```

#### 3.1.2 Tick 循环协议

```
TICK LIFECYCLE (per tick, ~3s target):

PHASE 1: COLLECT (parallel, ~2.5s)
  ├── For each player with active code:
  │   ├── Load player's WASM module (cached from last compilation)
  │   ├── Serialize visible world state → JSON snapshot
  │   ├── Instantiate WASM with fuel limit = player's CPU quota
  │   ├── Call `tick(snapshot)` → collect Commands[]
  │   └── Filter out invalid commands (out-of-quota, illegal actions)
  └── Collect all commands into command queue

PHASE 2: EXECUTE (sequential, ~0.5s)
  ├── Sort commands by game order (inter-player deterministic)
  ├── For each command:
  │   ├── Validate against current world state
  │   ├── If valid: apply mutation via ECS system
  │   └── If conflict: discard + record rejection reason
  ├── Run intra-tick ECS systems (combat, decay, regeneration)
  └── Increment game time

PHASE 3: BROADCAST (immediate)
  ├── Compute delta (changed entities since last snapshot)
  ├── Publish via NATS → Gateway → WebSocket → Clients
  └── Persist full world state snapshot to FoundationDB (every Nth tick)

Hints for future optimization:
- Shard per room — rooms that don't share borders can tick independently
- ECS systems can run in parallel when data dependencies allow (Bevy auto-scheduling)
```

#### 3.1.3 确定性保证

```
确定性需要满足：
1. 相同的初始 World State
2. 相同的 Command 输入 (已排序)
3. ECS System 的执行顺序固定
4. 所有随机数来自确定的种子 PRNG (do not use OS entropy)

反作弊策略：
- 全量 Replay：任意房间状态可完全重现
- 异常检测：玩家 tick 间的 world delta 如果不符合物理上限 → flag
- WASM 编译时静态分析：扫描可疑系统调用
```

---

### 3.2 Sandbox (WASM Runtime)

**目标：** 让玩家用任意语言编写 AI，编译为 WASM，安全地在服务端执行。

#### 3.2.1 玩家代码的生命周期

```
1. 玩家编写代码 (TS, Rust, Go, Python, Zig, ...)
2. 通过 Frontend SDK 编译为 WASM
3. 上传 WASM 模块到 Sandbox Service
4. Sandbox 服务:
   a. 验证 WASM 字节码合法性
   b. 静态分析 (可疑 import, 过大二进制)
   c. 存储到 S3/对象存储
   d. 返回 module_id
5. 每 Tick:
   a. Engine 请求 "player N's module"
   b. Sandbox 返回预热的 Wasmtime Instance (pooling)
   c. Engine 注入 snapshot, 执行, 提取 commands
   d. 回收 instance 到池中
```

#### 3.2.2 WASM ABI (玩家侧)

所有 SDK 导出同一个函数签名：

```typescript
// TypeScript SDK — 编译目标
export function tick(snapshot: string): string;
```

```rust
// Rust SDK — 编译目标
#[no_mangle]
pub extern "C" fn tick(snapshot_ptr: *const u8, snapshot_len: usize) -> *mut u8;
```

```
snapshot (JSON): 玩家可见的世界状态
return (JSON):   [Command, Command, ...] — 这一 tick 要执行的操作列表

Command 格式:
{
  "action": "move",        // move, harvest, build, attack, spawn, transfer, ...
  "target_id": "drone_a",
  "params": { "direction": 3 }
}
```

#### 3.2.3 安全层次

| Layer | Mechanism | Purpose |
|-------|-----------|---------|
| L1 | WASM linear memory isolation | Prevent memory escape |
| L2 | WASI minimal profile | No FS / network / clock / random |
| L3 | Fuel metering (Wasmtime) | CPU instruction counting |
| L4 | Host function allowlist | Only game API functions exposed |
| L5 | Static bytecode scan | Reject known-malicious patterns |
| L6 | Timeout (wall clock 2.5s) | Kill stuck modules |

#### 3.2.4 编译服务

```
Frontend SDK 负责本地编译:
  sdk-ts:  AssemblyScript 或 TypeScript → WASM
  sdk-rust:  wasm-pack → WASM

Sandbox Service 验证:
  - wasmparser 检查 WASM 模块有效性
  - 只接受已知且允许的 imports
  - 拒绝 > 5MB 的模块
  - 拒绝包含 start function 的模块 (防止预执行)
```

---

### 3.3 Gateway (Go)

**技术栈：** Go + gorilla/websocket + gRPC + NATS

#### 3.3.1 职责

- WebSocket 连接管理 (每 shard 一个 hub)
- REST API (用户管理, 排行榜, 比赛历史)
- gRPC server (Engine 内部调用)
- Auth (OAuth2 / API Key)
- 消息广播 (NATS consumer → WS clients)

#### 3.3.2 API 设计 (REST)

```
POST   /api/v1/auth/login          # OAuth2 login
GET    /api/v1/auth/me             # Current user
POST   /api/v1/auth/apikey         # Generate API key for CI

GET    /api/v1/world/rooms         # List all rooms
GET    /api/v1/world/rooms/:id     # Room overview
GET    /api/v1/world/rooms/:id/map # Terrain data

POST   /api/v1/code/compile        # Upload WASM module
GET    /api/v1/code/:id            # Module status

GET    /api/v1/leaderboard         # Global ranking
GET    /api/v1/leaderboard/season  # Current season

GET    /api/v1/matches             # Match history
GET    /api/v1/matches/:id         # Match replay
```

---

### 3.4 Frontend

**技术栈：** React 18 + Monaco Editor + PixiJS 8 + WebSocket

#### 3.4.1 核心页面

```
1. Dashboard — 多殖民地总览, 资源图表
2. Room View — 等距地图渲染 (PixiJS), 单位动画, 实时事件
3. Code Editor — Monaco Editor, 多文件项目, TypeScript types 内置
4. Console — Engine 返回的日志／错误
5. Market — 玩家间资源交易 (后期)
```

#### 3.4.2 地图渲染

- **PixiJS** (WebGL) 绘制等距/俯视地图
- 分层：Terrain → Structures → Resources → Creeps → Effects
- 视口管理：可拖拽、缩放，只渲染可见区域 (culling)
- 增量更新：只重新绘制 delta 实体

#### 3.4.3 代码编辑器

```
┌─────────────────────────────────────────────────┐
│ File: main.ts                           [Save] [Deploy]  │
├─────────────────────────────────────────────────┤
│                                               │
│  import { tick, Snapshot, Command }           │
│    from "@swarm/sdk"                          │
│                                               │
│  export function tick(snap: Snapshot):        │
│    Command[] {                                 │
│    const cmds: Command[] = []                 │
│                                               │
│    for (const drone of snap.drones) {         │
│      if (drone.fatigue === 0) {               │
│        cmds.push({                             │
│          action: "move",                      │
│          target_id: drone.id,                 │
│          params: { direction: 3 }              │
│        })                                      │
│      }                                         │
│    }                                           │
│                                               │
│    return cmds                                │
│  }                                             │
│                                               │
├─────────────────────────────────────────────────┤
│ Console: [Tick 4521] drone_a moved E3         │
│ [Tick 4522] drone_b harvested +5 energy        │
└─────────────────────────────────────────────────┘
```

---

### 3.5 SDK Design

#### 3.5.1 TypeScript SDK (`sdk-ts`)

```
@sdk-ts/
├── src/
│   ├── types.ts          # Snapshot, Command, Entity 类型定义
│   ├── sim.ts            # 本地模拟器 (用于离线测试)
│   ├── utils.ts          # 路径规划, 距离计算, 缓存工具
│   └── index.ts
├── examples/
│   ├── basic-harvester/
│   ├── tower-defense/
│   └── trade-bot/
├── package.json
└── tsconfig.json
```

#### 3.5.2 Rust SDK (`sdk-rust`)

```
@sdk-rust/
├── src/
│   ├── types.rs          # Snapshot, Command, Entity
│   ├── sim.rs            # 本地模拟器
│   ├── pathfinding.rs    # A* 等路径规划
│   └── lib.rs
├── examples/
│   ├── basic-harvester/
│   └── combat-squad/
├── Cargo.toml
└── README.md
```

#### 3.5.3 Game API (Host Functions)

These are the ONLY functions available inside the WASM sandbox:

```typescript
// 宿主提供给 WASM 的 API — 最小化设计
// (inside the sandbox, player code calls these to issue commands)

// Movement
move(target_id, direction) : Result
move_to(target_id, x, y)  : Result  // uses built-in pathfinder

// Harvesting / Resources
harvest(target_id, source_id)    : Result
transfer(target_id, target_id, resource, amount) : Result
withdraw(target_id, target_id, resource, amount) : Result

// Building
build(target_id, x, y, structure_type) : Result
repair(target_id, structure_id)        : Result

// Combat
attack(target_id, target_id)       : Result
ranged_attack(target_id, target_id): Result
heal(target_id, target_id)         : Result

// Spawning
spawn(spawn_id, body_parts[])     : Result
recycle(target_id, spawn_id)      : Result

// Information
get_terrain(x, y)                : TerrainType
get_objects_in_range(x, y, range): ObjectSummary[]
path_find(from, to)              : PathResult
```

---

## 4. 数据模型

### 4.1 FoundationDB — 世界状态

```
Key schema:
  /world/{shard}/room/{room_id}/terrain     → 地形数据 (static, 256KB max)
  /world/{shard}/room/{room_id}/entities    → 实体列表 (变动频繁)
  /world/{shard}/room/{room_id}/tick        → 当前 tick 号
  /player/{id}/profile                       → 玩家档案
  /player/{id}/modules/{module_id}           → WASM 模块元数据
  /player/{id}/stats                         → 统计信息
```

### 4.2 Dragonfly — 热缓存

```
用途：
- 当前 tick 的世界状态快照 (频繁读写)
- Player session 映射 (WS connection → player_id)
- 排行榜缓存 (每分钟刷新)
- Rate limiting counters
```

### 4.3 ClickHouse — 分析

```
表:
  tick_metrics     — 每 tick: 玩家 CPU 消耗, 命令数, 延迟
  player_events    — 日志: spawn, death, attack, build
  room_events      — 日志: 占领, 升级, 毁灭
  economy_events   — 日志: harvest, transfer, market trade
```

---

## 5. 部署架构

### 5.1 开发环境 (docker-compose)

```yaml
services:
  fdb:        # FoundationDB
  dragonfly:  # Redis 兼容缓存
  gateway:    # Go 服务
  engine:     # Rust 引擎
  sandbox:    # WASM 运行时
  frontend:   # Vite dev server
```

### 5.2 生产环境

```
┌──────────────────────────────────────────────┐
│              Load Balancer                    │
│           (nginx / Traefik)                   │
└──────┬───────────────────────┬───────────────┘
       │                       │
       ▼                       ▼
┌──────────────┐      ┌──────────────┐
│ Gateway-1    │      │ Gateway-2    │ ...  (Go, stateless, horizontal scale)
└──────┬───────┘      └──────┬───────┘
       │                     │
       └──────────┬──────────┘
                  ▼
┌─────────────────────────────────┐
│         NATS Cluster             │
└──────────┬──────────────────────┘
           │
           ▼
┌─────────────────────────────────┐
│     Engine (Rust)                │
│     (1 instance per shard)       │
└──────────┬──────────────────────┘
           │
           ▼
┌─────────────────────────────────┐
│   FoundationDB Cluster           │
└─────────────────────────────────┘
```

---

## 6. 路线图 (Roadmap)

### Phase 1: 核心引擎 (MVP — 单人沙箱)

- [ ] Bevy ECS 世界模拟 (地形, 资源, 基础单位)
- [ ] WASM 沙箱执行 (单 tick)
- [ ] 基础 Game API (move, harvest, build, spawn)
- [ ] 本地 docker-compose 开发环境
- [ ] TypeScript SDK + Rust SDK (基础 API)

### Phase 2: 多人世界

- [ ] Tick 调度器 (多玩家并行)
- [ ] 命令冲突解决
- [ ] 持久化 (FoundationDB)
- [ ] WebSocket 实时推送 (增量 delta)
- [ ] Room 边界 + 多房间

### Phase 3: 客户端

- [ ] Web 客户端 (React + Monaco + PixiJS)
- [ ] OAuth2 登录
- [ ] 代码编辑器 + 一键部署
- [ ] 实时地图渲染

### Phase 4: 游戏化

- [ ] 控制器 (Controller) + 房间占领
- [ ] 战斗系统 (melee/ranged/heal)
- [ ] 市场 (玩家间交易)
- [ ] 排行榜 + 赛季

### Phase 5: 生产化

- [ ] 性能优化 (sharding, ECS 并行化)
- [ ] 反作弊系统
- [ ] 自动化测试框架
- [ ] 文档 + 教程
- [ ] CI/CD Pipeline (GitHub Actions)

---

## 7. 贡献指南

### 7.1 开发环境搭建

```bash
# 克隆所有仓库
git clone git@git.kagurazakalan.com:swarm/engine.git
git clone git@git.kagurazakalan.com:swarm/sandbox.git
# ... etc

# 启动开发环境
cd engine && docker-compose up
```

### 7.2 代码规范

- Rust: `cargo fmt` + `cargo clippy` (strict)
- Go: `gofmt` + `golangci-lint`
- TypeScript: `prettier` + `eslint` (strict)
- Commit: [Conventional Commits](https://www.conventionalcommits.org/)

---

## 附录 A: 与 Screeps 的 API 兼容性

Swarm does NOT aim for API compatibility with Screeps. The design philosophy is different:

- Screeps API is object-oriented (`creep.moveTo()`, `Game.spawns['Spawn1']`)
- Swarm API is functional/data-oriented (`move(creep_id, direction)`, return commands)

However, a **compatibility layer** could be built as a community project that wraps Screeps-style API calls into Swarm commands.

## 附录 B: 为什么不用现有 Screeps 方案?

| Concern | Screeps | Swarm |
|---------|---------|-------|
| JavaScript lock-in | Only JS | Any WASM language |
| Performance ceiling | V8 + GC pauses | WASM native speed |
| CPU metering accuracy | Wall clock (system-dependent) | Fuel metering (deterministic) |
| Determinism | Not guaranteed | Designed for |
| Codebase age | Started 2014, Node.js 8 era | 2026, Rust + WASM |
| Licensing | Mixed (server open, client proprietary) | MIT (fully open) |

---

*Last updated: 2026-06-13*
