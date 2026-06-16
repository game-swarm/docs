# Swarm — 设计文档

> **Swarm** 是一个开源的、可编程的 MMO RTS 游戏引擎。它是 [Screeps](https://screeps.com/) 的精神续作，用现代技术栈从零重构，支持多语言。
>
> — *「你的代码就是你的军队。Write once, fight forever.」*

## 目录

1. [愿景](#1-愿景)
2. [系统架构](#2-系统架构)
3. [Engine（Rust）](#3-enginerust)
4. [MCP 接口](#4-mcp-接口ai-玩家的操作界面)
5. [游戏 API](#5-游戏-apideferred-command-model)
6. [数据模型](#6-数据模型)
7. [部署架构](#7-部署架构)
8. [World Rules Engine](#8-world-rules-engine--可配置的游戏规则)
9. [World vs Arena 模式](#9-world-模式-vs-arena-模式)
10. [贡献指南](#10-贡献指南)

---

## 1. 愿景

### 1.1 核心理念

Swarm 是一个**编程竞技场**——玩家编写真实代码来控制自主单位（drone），在一个持久共享世界中运行。与传统 RTS 不同，Swarm 的胜负不取决于手速，而取决于**算法思维、系统设计和资源优化**。

Swarm 支持两种玩家：
- **人类程序员**：通过 Web UI（Monaco 编辑器 + PixiJS 渲染）编写代码，编译为 WASM 部署
- **AI agent**：通过 MCP 接口查看世界、生成代码、部署 WASM——与人类走完全相同路径

世界只认 WASM。不论代码是谁写的。

Swarm 不是单个游戏，而是一个**可配置游戏引擎平台**。每个世界实例是一个独立 universe，有各自的规则集（world.toml）、资源体系、身体部件、建筑类型和特殊攻击——所有内容都是可配置的官方扩展，非引擎硬编码。世界之间形成**联邦宇宙**：玩家可跨世界拥有身份和资产，通过异步方式交互（转移资源、共享排名），但不同步执行实时操作（无跨世界 combat）。

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
├── docs/           # 设计文档、技术规范
│   ├── design/     #   架构设计
│   ├── specs/      #   技术规范
│   ├── api/        #   API 参考
│   └── security/   #   安全策略
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
    age: u32,                  // 创建后经过的 tick 数。达到 lifespan 后死亡
}

/// drone 生命周期 — 年龄达到上限后自动死亡。
/// 默认值 1500 tick，可通过 world.toml `drone.lifespan` 覆盖。
const DEFAULT_DRONE_LIFESPAN: u32 = 1500;

// Structure——建筑
struct Structure {
    structure_type: StructureType,  // Spawn, Extension, Tower, Storage 等
    owner: Option<PlayerId>,
    hits: u32, hits_max: u32,
    energy: Option<u32>,
    energy_capacity: Option<u32>,
    cooldown: u32,
}

// Resource——掉落资源（动态资源类型）
struct Resource {
    amounts: IndexMap<String, u32>,    // IndexMap 保证迭代顺序确定。{ "Energy": 500, "Matter": 200 }
}

// Source——可再生资源点
struct Source {
    produces: IndexMap<String, u32>,   // IndexMap 保证迭代顺序确定。{ "Energy": 1 } 或 { "Energy": 1, "Matter": 1 }
    capacity: u32,
    ticks_to_regeneration: u32,
}

// Terrain——地形
struct Terrain(TerrainType);  // Plain, Swamp, Wall

// Controller——房间控制器（占领/升级）
struct Controller {
    owner: Option<PlayerId>,
    level: u8,                    // 1–8，控制可用建筑与维修容量
    progress: u32, progress_total: u32,  // 升级进度
    downgrade_timer: u32,         // 降级倒计时（无 owner 时递减）
    safe_mode: u32,               // 安全模式剩余 tick
    safe_mode_available: u32,     // 可用安全模式次数
    safe_mode_cooldown: u32,      // 安全模式冷却
    repair_capacity: u32,         // 每 tick 可服务的 drone 数（由 RCL 决定）
    repair_range: u32,           // 维修距离（RCL1=1, RCL8=5）
    repair_per_drone: u32,        // 每 drone 回退的 age 量。硬上限规则详见 §8.2 Drone 生命周期。
}
```

#### Controller 升级表 (RCL)

| Level | 累计 progress | 解锁建筑 | 最大房间 drone | 维修容量 | 维修距离 | 说明 |
|-------|-------------|---------|---------------|---------|---------|------|
| 1 | 0 | Spawn | 50 | 5/tick | 1 格 | 初始状态 |
| 2 | 200 | Extension (5), Road, Container | 100 | 10/tick | 1 格 | 储能起步 |
| 3 | 400 | Extension (10), Tower, Storage, Depot | 200 | 20/tick | 2 格 | 防御+前线维修 |
| 4 | 800 | Extension (20), Link | 300 | 30/tick | 2 格 | 能源网络 |
| 5 | 1,500 | Extension (30), Terminal, Observer | 400 | 40/tick | 3 格 | 市场交易 |
| 6 | 3,000 | Extension (40), Extractor, Lab, Factory | 500 | 50/tick | 3 格 | 制造系统 |
| 7 | 6,000 | Extension (50), PowerSpawn | 500 | 60/tick | 4 格 | 晚期产能 |
| 8 | 12,000 | Extension (60), Nuker | 500 | 80/tick | 5 格 | 终极武器 |

**升级机制**: 在 Controller 所在房间内向 Controller 存入资源（通过 Transfer 指令），每 tick 自动转换为 `progress`。`progress >= progress_total` 时升级到下一级。

**降级**: 若 Controller 失去 owner 超过 `downgrade_timer`（默认 5000 tick），降一级，`progress` 重置为 0。

### 3.1a World Topology & Territory（世界拓扑与领土）

Swarm 世界由**离散的房间（Room）网格**构成，每个房间是一个独立的物理空间，房间之间通过出口连接。本节定义世界拓扑模型、领土状态机以及相关的扩展策略。

#### Room 模型

- **形状**：每个房间为正方形网格，边长可配置，**默认 50×50 格**。
- **连接**：相邻房间通过**出口（Exit）**连接，支持 N/S/E/W 四个方向。出口位于房间边缘，drone 必须移动到出口所在格才能穿越到相邻房间。
- **房间独立性**：每个房间拥有独立的地形、资源点和 Controller，物理上不与其他房间重叠。

#### 坐标系

- **原点**：世界中心为 (0, 0)。
- **轴向**：X 轴向东为正，Y 轴向北为正。每个房间的坐标即其在该网格中的位置。
- **可达性**：理论上无限扩展，实际由 world.toml 中配置的 `world_size`（房间数）限制。

```text
世界坐标系示例（9 房间，3×3）：

        Y+
        ▲
        │  (-1,1)  (0,1)  (1,1)
        │  (-1,0)  (0,0)  (1,0)
        │  (-1,-1) (0,-1) (1,-1)
        └──────────────► X+
```

#### Room 状态机

每个房间处于以下五种状态之一，由其中的 Controller 状态决定：

```text
                    ┌──────────┐
                    │ neutral  │  中立，无玩家 Controller
                    └────┬─────┘
                         │ 任意玩家对 Controller 执行 Claim
                         ▼
                    ┌──────────┐
                    │ reserved │  预约，Controller 已放置但 progress 未满
                    └────┬─────┘
                         │ progress >= progress_total（RCL 1 达成）
                         ▼
          ┌──────────┐         ┌───────────┐
          │  owned   │◄───────►│ contested │
          │ 正常运作  │  争夺    │ 两个玩家  │
          └────┬─────┘         │ 同时 Claim│
               │               └───────────┘
               │ owner 失去超过 downgrade_timer
               ▼
          ┌────────────┐
          │ abandoned   │  降级：失去 RCL 1 回到 neutral
          │ 降级中...    │  降级：RCL >1 降一级 + progress 重置
          └────────────┘
```

- **neutral**：房间无玩家 Controller。任何玩家可对其执行 Claim 操作进入 reserved。
- **reserved**：Controller 已放置（已关联玩家），但 `progress < progress_total`（尚未达到 RCL 1）。此时房间不能被其他玩家 Claim。若 progress 在 `reservation_timeout`（默认 1000 tick）内未达到 RCL 1，房间回退到 neutral。
- **owned**：房间正常运作，玩家拥有完整控制权（建造、升级、资源采集）。
- **contested**：两个不同玩家同时对同一 Controller 执行 Claim。系统进入争夺模式——每 tick 各自投入的 progress 减去对方的抵消量（取决于双方 Claim body part 数量差）。净 progress 归零的一方失去 claim 资格，房间转入对方的 reserved 状态。
- **abandoned**：owner 失去（玩家主动放弃或被消灭）超过 `downgrade_timer`（默认 5000 tick）后触发降级。若 RCL = 1，直接回到 neutral。若 RCL > 1，降一级并重置 progress。

#### 出口规则

- **最少出口**：每个房间有 1-4 个出口。系统强制保证每个房间至少有一个出口，防止孤岛房间（不可达）。
- **配对**：相邻房间的出口互相配对。例如房间 (0,0) 的东出口连接房间 (1,0) 的西出口。
- **生成**：出口位置在房间生成时由世界种子确定性随机确定，沿墙壁边缘分布。
- **静态出口**：出口默认为固定静态，不可被摧毁或建造。未来可通过模组扩展为可摧毁/可建造出口。

#### 视野与移动距离

- **默认可见范围**：WASM 玩家代码可见范围为**当前房间 + 相邻房间**（即最多 9 个房间的数据在每 tick snapshot 中可见）。Controller 的 **Observer** 升级（RCL 5 解锁）可扩展视野范围（RCL 5 = +1 房间，RCL 8 = +3 房间）。
- **跨房间移动**：drone 可跨房间移动，但必须通过出口。移动成本 = 房间内路径 cost + 穿越出口 cost（默认 +1 fatigue）。
- **移动限制**：跨房间移动的 drone 在穿越出口时必须有足够的 fatigue capacity（由 MOVE body part 决定）。

#### 扩展策略声明

Swarm 支持三个扩展层级：

| 架构 | 玩家容量 | 说明 |
|------|---------|------|
| 单 Engine 实例（垂直扩展） | 目标 MVP = 500 活跃玩家 | 单机 + FDB 单一提交保证世界一致性 |
| 单 Engine + FDB 分层缓存 | 1,000-5,000 活跃玩家 | 引入房间级读写分离与区域缓存 |
| 水平分片（多 Engine 实例） | 规模不限 | 跨 Engine 状态同步、跨分片移动为远期关注 |

单实例下 FDB 的单一事务提交保证世界内的强一致性。水平分片为远期方向，数据模型和 API 设计预留了分片扩展接口。

#### 新手房间分配策略

- **密度优先**：新玩家首次 spawn 时，系统计算各房间区域（以候选 spawn 点为中心 3×3 房间）的活跃玩家密度，选择**密度最低**的区域分配出生房间。
- **避免包围**：系统拒绝将新玩家分配到四周均为敌对玩家已占领房间的区域（"出生点包围"检测），确保新手有安全的早期发展空间。
- **safe_mode 保护**：新玩家首次 spawn 后自动获得 **500 tick safe_mode**（房间内无敌），此期间其他玩家无法在该房间执行任何敌对操作（Attack/Claim/Hack 等）。
- **重生策略**：殖民地全灭后，玩家在密度最低的区域重生（`respawn_policy = NewRoom`），而非回到原房间。

### 3.2 Tick 生命周期

```
每 tick（目标 3s）：

阶段一：收集 (COLLECT) — 并行
  ├── [tick 开始] 构建世界快照（一次性，按房间分区）
  │   ├── 序列化完整世界状态为结构化快照，按房间分片
  │   └── 快照构建在玩家代码执行前完成，天然确定
  ├── 对每个活跃玩家（并行，sandbox worker pool）:
  │   ├── 根据玩家 drone 所在房间，拼接可见房间的快照分片
  │   │   └── 默认可见 = 当前房间 + 相邻房间（最多 9 个分片拼接）
  │   ├── 实例化玩家 WASM 模块（部署时已预编译为原生码，tick 时仅实例化）
  │   ├── 调用 tick(snapshot)，fuel limit = 玩家 CPU 配额
  │   └── 收集 Vec<Command>，过滤无效指令（超配额、非法操作）
  └── 收集全部指令到指令队列

阶段二：执行 (EXECUTE) — 约束并行
  ├── 玩家顺序种子洗牌（seed = hash(tick_number, world_seed)）
  ├── Phase 2a: 命令循环（逐条 inline 应用）
  │   ├── 对每条指令（按洗牌后顺序 + 玩家内 sequence 排序）:
  │   │   ├── 对照**当前** Bevy World 状态校验（非快照）
  │   │   ├── 合法 → 立即通过对应 ECS system 应用变更
  │   │   ├── 资源竞争 → 先到先得（先执行者优先）
  │   │   └── 冲突 → 丢弃 + 记录 RejectionReason
  │   └── Spawn 命令在 Phase 2a 中只校验不入队
  ├── Phase 2b: ECS Systems（部分并行）
  │   ├── death_mark_system（标记待死亡 entity，释放 room cap 槽位）
  │   ├── spawn_system（统一创建 Phase 2a 校验通过的 drone）
  │   ├── combat_system（damage 先 → heal 后，同 tick 内结算）
  │   ├── regeneration_system ─┐
  │   ├── decay_system ────────┤ 并行（无数据竞争，与主线无依赖）
  │   └── death_cleanup_system（实际 despawn，等全部系统完成）
  ├── FDB 原子提交（全或无）
  └── tick_counter 推进

阶段三：广播 (BROADCAST) — 即时
  ├── 计算增量（与上一 tick 快照的实体差异）
  ├── Dragonfly 缓存更新
  ├── 通过 NATS → Gateway → WebSocket 客户端发布
  └── 持久化：每 tick 存储 delta，每 K tick 存储 keyframe 到 FDB（回放用）
```

### Phase 2a/2b 分类原则

| 阶段 | 执行模型 | 包含的命令/系统 | 分类原则 |
|------|---------|---------------|---------|
| **Phase 2a (Inline)** | 串行 inline 应用 | Move, Harvest, Build, Transfer, Attack, RangedAttack, Heal, Recycle | **玩家提交的命令**——效果依赖执行顺序，且「先到先得」竞争有意义。对 Bevy World 做立即修改，后续命令基于最新状态校验 |
| **Phase 2b (Deferred)** | ECS Systems `.chain()` + `.before()/.after()` | death_mark, spawn, combat（主线 `.chain()`）；regeneration, decay（并行，仅需 before death_cleanup） | **被动系统**——对有依赖关系的系统串行执行（保证正确性），无数据竞争的系统利用 Bevy 并行调度。不接收玩家命令，响应 2a 产生的状态变化 |

**Attack 与 combat_system 的职责分离**：
- **Phase 2a Attack/RangedAttack 命令**：直接应用 damage（含抗性/伤害类型计算），立即反映到目标 HP
- **Phase 2b combat_system**：仅处理非玩家命令的战斗——Tower 自动攻击、持续伤害效果（DoT）、叠加状态结算
- 此分离保证「先到先得」竞争在 Attack 上生效，同时 Tower/DoT 统一在 2b 末尾结算

**Recycle 死亡路径**：Recycle 命令走标准 death_mark → death_cleanup 路径（与其他死亡一致），不在 Phase 2a 中立即 despawn。death_mark 在 2b 开头标记待死亡 entity 并释放 room cap 槽位，death_cleanup 在 2b 末尾执行实际 despawn。

**Spawn 时序说明**：spawn_system 在 death_mark 之后（room cap 槽位已释放）、combat/decay 之前运行。新 spawn 的 drone **在同 tick 参与 combat 和 decay**——可能出生即被攻击或受衰减影响。此行为是有意设计（「出生即投入战斗」），非文档错误。

**Phase 2b 并行策略**：regeneration（资源点再生）和 decay（疲劳/冷却递减）只操作各自独立的数据，与主线 death→spawn→combat→death_cleanup 无数据竞争。利用 Bevy 的 `.before()/.after()` 将这两个系统与主线并行调度——Bevy 在幕后自动分配线程，无需手动管理。约束：两者必须在 `death_cleanup` 之前完成（防止操作已 despawn 的 entity），其他无顺序要求。正确性由数据独立 + Bevy 依赖图保证，确定性不依赖并行度（同 input 同 output）。

**两阶段快照架构**：阶段一不再为每个玩家独立序列化世界状态。改为：(1) tick 开始时一次性构建完整世界快照，按房间分片；(2) 每个玩家根据其 drone 所在位置，拼接可见房间的分片（默认 ≤9 个）。复杂度从 `O(玩家数 × 实体数)` 降为 `O(实体数 + 玩家数 × 可见房间数)`，消除每玩家重复序列化开销。快照构建在玩家 WASM 执行前完成，与玩家顺序无关，天然确定。

**WASM 预编译**：玩家上传 WASM 模块时，引擎在部署阶段立即编译为原生码并存储（非 tick 时 JIT）。tick 时只需实例化已编译模块，消除首次加载的编译延迟。编译后的模块按 `(module_hash, wasmtime_version)` 缓存，Wasmtime 版本升级时自动重编译。

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
| | `swarm_get_world_rules` | 获取世界规则配置 |
| **部署** | `swarm_deploy` | 上传 WASM 模块 |
| | `swarm_validate_module` | 上传前预检 |
| | `swarm_rollback` | 回滚到之前版本 |
| | `swarm_list_modules` | 列出已部署的 WASM 模块 |
| **调试** | `swarm_explain_last_tick` | 解释上 tick 发生了什么 |
| | `swarm_inspect_entity` | 检查实体完整状态 |
| | `swarm_inspect_room` | 查看有视野的房间概况 |
| | `swarm_profile` | 策略性能指标 |
| | `swarm_dry_run_commands` | 干跑 Command JSON |
| | `swarm_get_replay` | 获取 tick 范围回放数据 |
| **学习** | `swarm_get_docs` | API 参考和游戏规则 |
| | `swarm_get_schema` | 游戏 API JSON Schema |
| | `swarm_get_available_actions` | 当前可用的 API 函数 |
| | `swarm_simulate` | 离线模拟：给定快照预测未来 N tick |
| **认证** | `swarm_oauth2_login` | OAuth2 登录 |
| | `swarm_oauth2_callback` | OAuth2 回调 |
| | `swarm_token_refresh` | 刷新 token |
| | `swarm_auth_revoke` | 吊销证书 |
| **锦标赛** | `swarm_tournament_precommit` | 锁定 WASM 模块 |
| | `swarm_tournament_create` | 创建 bracket |
| | `swarm_tournament_status` | 查询状态 |
| | `swarm_match_result` | 查询比赛结果 |
| **资源管理** | `resources/list` | 列出可用资源类型 |
| | `resources/read` | 读取资源定义 |

### 4.2 明确不在 MCP 中

MCP 不做游戏动作。不存在 `swarm_move`、`swarm_attack`、`swarm_build` 等工具。AI agent 必须**编写 WASM 代码**来实现策略，和人类玩家完全一样。

---

## 5. 游戏 API（Deferred Command Model）

WASM 模块通过 **deferred command model** 与引擎交互：

```
部署:  上传 WASM → 验证 → 预编译为原生码 → 存储（按 module_hash 索引）
tick:  tick(snapshot) → Command[]
```

1. 引擎构建世界快照（按房间分片），根据玩家可见范围拼接子集，写入 WASM 线性内存
2. 调用 `tick(ptr, len)` — WASM 模块接收快照，返回指令 JSON 列表
3. 引擎校验所有指令 → 应用到世界

快照格式为结构化数据（非纯文本 JSON），房间分片保证拼接无歧义。SDK 侧通过 `WorldSnapshot` 类型访问，无需感知底层分片结构。

### 5.1 允许的 Host Function（查询专用，只读）

WASM 中**仅可调用查询类 host function**——所有函数只读，不计入指令预算但计入 fuel 预算：

```rust
// 信息查询（只读，不改变世界状态）
fn host_get_terrain(x: i32, y: i32) -> i32;
fn host_get_objects_in_range(x: i32, y: i32, range: i32, out_ptr: i32, out_len: i32) -> i32;
fn host_path_find(from_x: i32, from_y: i32, to_x: i32, to_y: i32, out_ptr: i32, out_len: i32) -> i32;

// 世界配置查询
fn host_get_world_config(key_ptr: i32, key_len: i32, out_ptr: i32, out_len: i32) -> i32;
fn host_get_world_rules(out_ptr: i32, out_len: i32) -> i32;
```

全部返回 `i32`：0 = 成功，负数 = 错误码。
`out_ptr`/`out_len`：WASM 分配缓冲区，host 写入结果后再次校验边界。

### 5.2 禁止的 Host Function

以下**游戏动作不得作为 host function 暴露给 WASM**。所有 mutating 操作通过 `tick() → Command[]` JSON 延迟模型提交，引擎在校验后统一应用：

- ❌ `host_move` / `host_move_to` — 改为 `{ "action": "Move", ... }` JSON 指令
- ❌ `host_harvest` / `host_transfer` / `host_withdraw`
- ❌ `host_build` / `host_repair`
- ❌ `host_attack` / `host_ranged_attack` / `host_heal`
- ❌ `host_spawn` / `host_recycle`

> **设计合同**: WASM 模块不直接调用 mutating host function。所有状态变更通过 `tick() → JSON` 延迟模型提交。

---

## 6. 数据模型

### 6.1 FoundationDB — 世界状态

世界状态采用 **Keyframe + Delta** 存储模型，兼顾回放完整性和存储效率：

```
/tick/{N}/keyframe       → 每 K tick 的完整世界状态（keyframe）
/tick/{N}/delta          → keyframe 之间的增量（实体变更集 + 指令日志）
/tick/{N}/commands       → 全部玩家的排序指令
/tick/{N}/rejections     → 被拒绝的指令及原因
/tick/{N}/metrics        → tick 指标
/tick/{N}/mods_lock      → 该 tick 时的 mods.lock 快照（模组版本哈希集）
/tick/{N}/world_config   → 该 tick 时的 world.toml 快照（世界规则配置）
/player/{id}/profile     → 玩家档案
/player/{id}/modules/    → WASM 模块历史（含预编译后的原生码）
```

**回放元数据**：`mods_lock` + `world_config` 构成回放的完整环境元数据。两者都在 keyframe 级别存储完整快照；keyframe 之间的 delta 仅在配置或模组版本发生变更时记录差异（配置变更远少于每 tick 实体变更，几乎不增加存储）。回放时恢复完整环境后再重放指令。

**回放流程**：定位最近 keyframe → 加载状态 + `mods_lock` + `world_config` → checkout 模组到精确 commit，恢复世界规则 → 顺序重放 delta 链 → 抵达目标 tick。确定性保证：相同初始状态 + 相同 seed + 相同指令 + 相同 world_config + 相同模组版本 → 相同 state_checksum。

**典型配置**：`K=100`（每 100 tick 一个 keyframe，约 5 分钟），delta 仅存储实体变更（创建/修改/删除），体积约为 keyframe 的 1-5%。整体存储减少约 90%。

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
│     (每个世界一个实例)              │
└──────────┬──────────────────────┘
           │
           ▼
┌─────────────────────────────────┐
│   FoundationDB 集群               │
└─────────────────────────────────┘
```

多个 Engine 实例可并行运行——每个服务一个独立的世界。世界之间通过异步协议交互（如跨世界转移资产、共享排名），但不共享实时游戏状态。这形成了 Swarm 的联邦宇宙。

---

## 8. World Rules Engine — 可配置的游戏规则

Swarm 不是「一个游戏」，而是「一个可配置的游戏引擎平台」。每个世界实例可以有不同的规则集。

### 8.1 核心理念

Screeps 的问题是**规则硬编码**——出生点逻辑、代码更新成本、drone 控制权限都是引擎的一部分，社区服主无法修改。Swarm 把这些做成**世界级配置**。

**所有游戏内容都是 world.toml 中默认启用的官方扩展**——身体部件类型、建筑类型、伤害类型、特殊攻击、资源类型，全部通过 `[[body_part_types]]` / `[[structure_types]]` / `[[damage_types]]` / `[[special_effects]]` / `[[custom_actions]]` / `[[resource_types]]` 定义。引擎核心只提供 validation + execution pipeline，不硬编码任何游戏内容。服主可禁用、修改、或从头定义自己的世界规则。

```
世界配置 (WorldConfig)          ECS Plugin (System 注入)
┌─────────────────────┐        ┌──────────────────────┐
│ spawn_policy         │        │ SpawnPolicySystem    │
│ code_update_cost     │   →    │ CodeUpdateCostSystem │
│ code_propagation     │        │ PropagationSystem    │
│ drone_env_vars       │        │ DroneEnvVarSystem    │
│ ...                  │        │ ...                  │
└─────────────────────┘        └──────────────────────┘
         │                              │
         └──────────┬───────────────────┘
                    ▼
            引擎启动时加载
```

### 8.2 规则分类

#### 出生与加入

| 规则 | 类型 | 说明 |
|------|------|------|
| `spawn_policy` | enum | `RandomRoom`（默认） \| `ManualSelect`（玩家选坐标，仅在首次加入/重生时） \| `FixedSpawn`（固定出生点） \| `Inherit`（从已有殖民地出生——需该房间存在玩家的 Controller 且 level ≥ 1） |
| `spawn_cooldown` | u32 | 新玩家加入后多少 tick 才能开始操作（默认 0） |
| `respawn_policy` | enum | 殖民地全灭后的处理：`NewRoom` \| `SameRoom` \| `Spectate` \| `Ban` |

#### 代码部署

| 规则 | 类型 | 说明 |
|------|------|------|
| `code_update_cost` | ResourceCost | 部署新 WASM 消耗的资源（默认 `{Energy: 0}` — 免费） |
| `code_update_cooldown` | u32 | 两次部署间的最小 tick 间隔（默认 5，World 模式最小 5，防止 re-deploy refund 滥用） |
| `code_update_window` | (u32, u32) | 部署窗口期：每 N tick 开放 M tick（默认无限制） |
| `code_propagation_speed` | u32 | 代码更新传播速度：0=全局即时，>0=每 tick 传播 N 格 |
| `code_propagation_source` | enum | 传播源：`Spawn`（从出生点传播）\| `Controller`（从控制器传播）\| `AnyDrone` |

#### Drone 控制

| 规则 | 类型 | 说明 |
|------|------|------|
| `env_vars` | bool | 是否允许给 drone 设置环境变量（`drone.set("role", "harvester")`） |
| `memory_size` | u32 | 每 drone 最大环境变量存储（bytes，默认 1024） |
| `memory_spawn_cost` | `{String: u32}` | 每 byte 内存的孵化成本 × 精度因子（默认 `{}` = 免费） |
| `memory_upkeep_cost` | `{String: u32}` | 每 byte 内存的每 tick 维护费 × 精度因子（默认 `{}` = 免费） |

**手动控制不开放**：manual_control 与「代码就是军队」的核心哲学冲突，不在设计范围内。唯一例外是 Tutorial 专用世界中的受限引导操作——但 Tutorial 世界独立运行，不与正式世界互通。

#### 资源与经济

| 规则 | 类型 | 说明 |
|------|------|------|
| `source_regeneration_rate` | `fixed<u32,4>` | 资源点再生速率倍率 × 10000（默认 10000 = 1.0） |
| `build_cost_multiplier` | `fixed<u32,4>` | 建筑成本倍率 × 10000（默认 10000 = 1.0） |
| `drone_decay_rate` | `fixed<u32,4>` | drone 衰减倍率 × 10000（默认 10000 = 1.0） |

#### Drone 生命周期

| 规则 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `drone_lifespan` | u32 | 1500 | drone 基础存活 tick 数。实际 `age_max = BASE_AGE + sum(每个 body part 的 age_modifier)`。`age_modifier` 定义在 `[[body_part_types]]` 中（如 TOUGH +100 延寿、ATTACK -80 折寿），世界可配置。达到 age_max 后自动死亡。 |
| `idle_aging` | — | 100% | idle drone 按正常速率衰老 |
| `active_aging` | — | 110%（即 +10%） | 每 tick 执行命令的 drone 以 110% 速率衰老（正常速率的 1.1 倍），防止挂机囤兵 |

**Age 恢复**: drone 必须**移动到 Controller 或 Forward Depot 维修范围内**才能降低 age。Controller 维修距离随 RCL 增长（RCL1=1 格，RCL8=5 格），免费，每 tick 服务上限由 RCL 决定。Forward Depot 固定 range=1，消耗存储资源。相邻格只有 6 个——大量 drone 需要排队，形成物流拥挤决策。**Controller 续期硬上限：无论拥有多少个 Controller，每 tick 总 age 回退不超过自然增长（+1/tick）的 50%（即 `max(0, age + 1 - min(0.5, controller_count * 0.5))`）。此上限防止玩家通过堆叠多个 Controller 实现永久 drone，保留 lifespan 的核心约束意义。**Healer body part 只能恢复 HP，不能降低 age。

#### Drone 身体规划

**body 不可逆**: 一旦 spawn，body part 组成不可更改。但可通过 `Recycle` 回收 drone 获得 50% 资源退还，重新 spawn 更优 body。

**新手保护**: Tutorial 世界前 500 tick 回收退还 100%（新人可以试错）。标准世界回收退还 50%。

#### 自定义建筑类型（`[[structure_types]]`）

与资源类型一样，建筑类型可通过 world.toml 定义。默认世界提供以下 13 种基础类型：

```toml
# world.toml — 建筑类型定义（可扩展）

[[structure_types]]
name = "Spawn"
description = "出生点——生成 drone"
category = "core"
hits = 5000
rcl_required = 1
cost = { Energy = 200 }

[[structure_types]]
name = "Extension"
description = "扩展——存储能量，最多 60 个"
category = "storage"
hits = 1000
rcl_required = 2
max_per_room = 60
cost = { Energy = 50 }

[[structure_types]]
name = "Tower"
description = "防御塔——自动攻击射程内敌方"
category = "defense"
hits = 3000
rcl_required = 3
attack = { damage = 50, damage_type = "Kinetic", range = 5, cooldown = 10 }
cost = { Energy = 200 }

[[structure_types]]
name = "Storage"
description = "仓库——大容量本地资源存储"
category = "storage"
hits = 10000
rcl_required = 3
capacity = 1000000
cost = { Energy = 500 }

[[structure_types]]
name = "Link"
description = "链接——短距离能量传输"
category = "logistics"
hits = 1000
rcl_required = 4
cost = { Energy = 300 }

[[structure_types]]
name = "Extractor"
description = "萃取器——从资源点采集矿物"
category = "production"
hits = 5000
rcl_required = 6
cost = { Energy = 800 }

[[structure_types]]
name = "Lab"
description = "实验室——化学反应/资源合成"
category = "production"
hits = 5000
rcl_required = 6
cost = { Energy = 1000 }

[[structure_types]]
name = "Terminal"
description = "终端——市场交易接口"
category = "logistics"
hits = 3000
rcl_required = 5
cost = { Energy = 500 }

[[structure_types]]
name = "Observer"
description = "观察者——扩展视野范围"
category = "intel"
hits = 500
rcl_required = 5
sight_range = 10
cost = { Energy = 300 }

[[structure_types]]
name = "PowerSpawn"
description = "强化出生点——处理高等级 drone body"
category = "core"
hits = 5000
rcl_required = 7
cost = { Energy = 5000 }

[[structure_types]]
name = "Factory"
description = "工厂——批量生产商品"
category = "production"
hits = 5000
rcl_required = 6
cost = { Energy = 1500 }

[[structure_types]]
name = "Nuker"
description = "核弹发射井——终极武器"
category = "defense"
hits = 10000
rcl_required = 8
cost = { Energy = 100000 }

[[structure_types]]
name = "Depot"
description = "前线维护节点——消耗资源为附近 drone 降低 age，可被占领"
category = "logistics"
hits = 2500
rcl_required = 2
capacity = 50000
maintenance = { Energy = 10 }      # 每 tick 维持消耗（资源耗尽停止维修）
repair_capacity = 10               # 每 tick 可服务的最大 drone 数
repair_range = 1                   # 维修距离（固定 1 格）
repair_aging = 5                   # 每 drone 降低的 age 量
cost = { Energy = 5000 }
```

**字段说明**：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `name` | string | ✅ | 唯一标识符 |
| `description` | string | ✅ | 人类可读描述 |
| `category` | enum | ✅ | `core` / `storage` / `defense` / `production` / `logistics` / `intel` |
| `hits` | u32 | ✅ | 最大 HP |
| `rcl_required` | u8 | ✅ | 需要的最低 RCL 等级（1-8） |
| `max_per_room` | u32 | 否 | 每房间最大数量（无限制则省略） |
| `capacity` | u32 | 否 | 资源存储容量 |
| `attack` | map | 否 | 自动攻击配置 `{damage, damage_type, range, cooldown}` |
| `sight_range` | u32 | 否 | 提供的额外视野范围 |
| `cost` | `{String: u32}` | ✅ | 建造成本 |
| `maintenance` | `{String: u32}` | 否 | 每 tick 维持消耗。资源耗尽时建筑停止功能（如 Depot 停止维修） |
| `repair_capacity` | u32 | 否 | 每 tick 可服务的最大 drone 数（Depot 专用） |
| `repair_range` | u32 | 否 | 维修距离（Depot 固定 1 格，Controller 由 RCL 决定） |
| `repair_aging` | u32 | 否 | 每 drone 降低的 age 量（Depot 专用） |

建筑类型像资源一样可扩展——服主可添加自定义建筑（如 `ShieldGenerator`、`Teleporter`），模组可通过 Rhai 赋予特殊行为。

#### 后勤网络：Controller vs Depot

drone age 维护由两层设施构成：

| | Controller | Forward Depot |
|---|-----------|---------------|
| 功能 | 领土主权 + age 维修 | 前线 age 维修 |
| 领土 | ✅ 宣称主权 | ❌ 不宣称 |
| 建筑解锁 | ✅ RCL 决定 | ❌ 无 |
| 降 age | ✅ 免费（容量由 RCL 决定） | ✅ 消耗本地存储资源 |
| 存储 | ❌ 只接收升级进贡 | ✅ 独立本地仓库 |
| 可占领 | ✅ Claim | ✅ Claim 或摧毁重建 |
| 可摧毁 | ❌ 降级 | ✅ 破坏 + 掉落部分资源 |
| 建造限制 | 每房间 1 个 | 任意（但有维护成本） |
| 维持消耗 | 无 | `maintenance` 字段定义 |

**战术含义**：
- **推进前线**: 在敌方领地边缘建 Depot，远征 drone 不用跑回主基地
- **补给线**: Depot 需要 CARRY drone 持续运输资源来维持运转——物流是玩法，不是免费午餐
- **打击后勤**: 摧毁敌方 Depot → 前线 drone 全部断粮，被迫撤退或等死
- **夺取节点**: 攻占敌方 Depot 获取其中资源，并为自己前线服务

#### 自定义资源类型

世界可以定义任意种类和数量的资源。默认世界只有 `Energy` 一种资源——但服主可以定义 `Crystal + Gas`（星际争霸风格）、`Food + Wood + Stone + Gold`（帝国时代风格）、或 `CPU + Memory + Bandwidth`（赛博朋克主题）。

| 规则 | 类型 | 说明 |
|------|------|------|
| `resource_types` | `[ResourceDef]` | 世界中的资源类型列表，默认 `[{name: "Energy"}]` |

#### 资源存储模型：全局 vs 本地

玩家的资源分为两层：

```
全局存储 (Player Storage)          本地存储 (World Storage)
┌─────────────────────┐           ┌──────────────────────┐
│ 抽象经济力量          │           │ 物理存在于建筑中        │
│ 不依赖建筑            │  物流成本  │ 需要 Storage/Extension │
│ 可市场交易            │ ←──────→ │ drone 采集先到这里     │
│ 可支付部署费          │           │ 跨房间运输需要 Carry    │
│ 有容量上限（研究升级）  │           │ 可被敌方掠夺/摧毁      │
└─────────────────────┘           └──────────────────────┘
```

**默认行为**：
- drone 采集资源 → 先进入**世界本地存储**（就近的 Storage/Extension/Spawn）
- 世界本地存储的资源可通过 Terminal 在市场交易（需物流可达）
- 玩家可将本地存储转为全局存储（消耗能量 + 时间 = 物流成本）
- 全局存储的资源在部署代码、支付维护费时自动扣除
- 全局存储不能直接用于本地建造——需先转回本地

**可配置参数**：

| 规则 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `global_storage_enabled` | bool | true | 是否启用全局存储。false = 纯本地物流 |
| `global_storage_capacity` | u32 | 100000 | 全局存储上限 |
| `transfer_to_global_cost` | ResourceCost | `{Energy: 0.01}` | 本地→全局每单位资源的转换成本（默认 1%） |
| `transfer_to_global_time` | u32 | 10 | 转换所需的 tick 数（不可为 0，防止瞬移补给） |
| `transfer_from_global_cost` | ResourceCost | `{Energy: 0.05}` | 全局→本地每单位资源的转换成本（默认 5%） |
| `transfer_from_global_time` | u32 | 5 | 全局→本地转换所需 tick 数（不可为 0） |

**三种物流模式**：

```
模式 A: 无物流 (global_storage_enabled=true, transfer_cost=0)
  drone采集 → 即时进入全局存储 → 任何地方可用
  最简单，适合新手和快节奏 Arena

模式 B: 轻物流 (默认)
  drone采集 → 本地存储 → 付1%转全局 → 全局付部署费
  全局→本地付5% → 本地建造
  有策略深度但不过度惩罚

模式 C: 硬核物流 (global_storage_enabled=false)
  所有资源物理存在，必须用 Carry drone 运输
  类似 Factorio——物流本身就是核心玩法
```

**市场交易的物流规则**：

- 全局存储中的资源 → 可即时挂单交易（无物流延迟）
- 本地存储中的资源 → 需要先转全局，或通过 Terminal 建筑交易
- 买入的资源 → 进入全局存储（需转本地才能用于建造）
- 世界规则可配置：`market_requires_terminal = true/false`

#### 全局存储反制机制（Anti-Dominant-Strategy）

为防止富有玩家通过囤积全局存储垄断经济、操纵市场价格、阻断新玩家供给，设计以下三项内置反制：

**1. 累进存储税（Progressive Storage Tax）**

玩家全局存储总量超过阈值后，超出部分按累进税率征收每 tick 维护费：

| 存储量（占容量上限） | 税率（每 tick） |
|---|---|
| 0–30% | 0%（免税） |
| 30–60% | 0.01%（每万单位 1 单位） |
| 60–85% | 0.05% |
| 85–100% | 0.20% |

> 税率由世界规则配置 `global_storage_tax_tiers` 控制。Arena 模式默认免税（竞技公平）。

**2. 本地存储隐匿性（Stealth Advantage）**

- **全局存储余额**：部分公开——排行榜可显示排名区间，市场挂单暴露部分余额
- **本地存储**：完全私有——敌方无法获知你的建筑中存了多少资源，直到发起侦察或占领

这使得囤积本地存储成为战略优势：敌方不知道你的真实经济实力。

**3. 全局↔本地转换需物流运输（No Teleport）**

- `transfer_to_global_time`：本地→全局转换需 N tick（默认 10 tick）。资源在运输期间不可用。
- `transfer_from_global_time`：全局→本地转换需 N tick（默认 5 tick）。大型帝国需提前规划补给线。
- 转换期间资源处于"运输中"状态——可被敌方巡逻 drone 拦截（需 PvP 启用）。

> 运输时间使全局存储不能作为"战斗中的即时补给"——这是一种非平凡的策略权衡。

| 规则 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `global_storage_tax_tiers` | `[(u32, u32)]` | `[(30,0),(60,1),(85,5),(100,20)]` | 累进税率：(容量%, 每10万单位税率) |
| `transfer_to_global_time` | u32 | 10 | 本地→全局转换所需 tick 数（不可为 0） |
| `transfer_from_global_time` | u32 | 5 | 全局→本地转换所需 tick 数（不可为 0） |
| `global_storage_public` | bool | false | （计划中）全局存储是否完全公开 |

#### 资源定义

```toml
[[resource_types]]
name = "Crystal"              # 资源名（标识符）
display_name = "水晶矿"        # 显示名
category = "mineral"          # mineral | gas | organic | energy
starting_amount = 0           # 新玩家初始拥有量
max_storage = 100000          # 单玩家最大储量
decay_rate = 10               # 每 tick 衰减比例 × 10000（0 = 不衰减）
tradeable = true              # 是否可在市场交易
```

定义了资源类型后，可以给不同的动作指定不同的资源消耗：

```toml
[actions.costs]

# Spawn drone 消耗：水晶 + 高能瓦斯
spawn = { Crystal = 200, Gas = 50 }

# 建造建筑
build.Extension = { Crystal = 50 }
build.Tower = { Crystal = 100, Gas = 25 }

# 生成 body part
body_part.Move = { Crystal = 50 }
body_part.Work = { Crystal = 100 }
body_part.Attack = { Crystal = 80, Gas = 20 }
body_part.Heal = { Crystal = 250, Gas = 100 }
body_part.Claim = { Crystal = 600 }

# 代码部署
code_update = { Crystal = 500 }

# 维修
repair_per_hit = { Crystal = 1 }
```

资源点可以产出多种资源：

```toml
[[source_types]]
name = "CrystalField"
produces = { Crystal = 1 }     # 每 tick 产出
capacity = 3000
regeneration = 300             # 每 tick 再生量

[[source_types]]
name = "GasVent"
produces = { Gas = 1 }
capacity = 2000
regeneration = 10
```

### Official Vanilla Swarm Ruleset（官方默认规则集）

Swarm 是一个**可配置的游戏引擎平台**——每个世界实例（world instance）可以通过 `world.toml` 自定义资源体系、身体部件、建筑类型、伤害类型、特殊攻击等几乎所有游戏内容。然而，为了让新手**无需任何配置即可开始游戏**，Swarm 官方提供一套**强默认规则集（Vanilla Ruleset）**，所有可配置项在此规则集中均有固定默认值。

本节汇总 Vanilla Ruleset 的核心默认值，作为所有官方世界（包括 Tutorial、World 模式默认世界、Arena 模式默认世界）的基线。

#### 核心默认值一览

| 类别 | 默认值 | 说明 |
|------|--------|------|
| **资源** | 单一 `Energy` | 所有操作消耗 Energy，简化经济模型。世界可通过 `[[resource_types]]` 扩展 |
| **身体部件** | 8 种标准件：`MOVE`, `CARRY`, `WORK`, `ATTACK`, `RANGED_ATTACK`, `HEAL`, `CLAIM`, `TOUGH` | 每种部件的 cost/age_modifier/能力 见 `[[body_part_types]]` 默认定义 |
| **伤害类型** | 6 种：`Kinetic`, `Thermal`, `EMP`, `Sonic`, `Corrosive`, `Psionic` | 默认抗性均为 1.0，详见 §8 伤害与武器类型定义 |
| **物流模式** | **模式 B（轻物流）** | 全局传输 1% 损耗，本地建造 5% 损耗。模式 A（无损耗）和模式 C（重物流）为可选项 |
| **特殊攻击** | 分层解锁：Tutorial/Novice 默认禁用全部 8 种特殊攻击（`Hack`, `Drain`, `Overload`, `Debilitate`, `Disrupt`, `Fortify`, `Leech`, `Fabricate`）。Standard+ 全部可用 | 冷却时间与资源消耗见 §8 特殊攻击方式表格。层级配置: world.toml `vanilla.tier = \"Tutorial\" | \"Novice\" | \"Standard\" | \"Advanced\"` |
| **Controller 维修** | 硬上限：每 tick 总 age 回退 ≤ 自然增长的 50% | 详见 §3.1 Controller 结构定义 |
| **可见性** | `fog_of_war = true`，`player_view = drone`，`public_spectate = false` | 玩家仅可见自己 drone 视野内的内容；公开观战默认关闭 |
| **排行榜** | World 模式无排行榜，Arena 模式有排行榜 | 持久世界天然不公平（老玩家先发优势），竞技场模式为有限时间窗口的公平竞争 |
| **新玩家保护** | 首次 spawn 后 **500 tick safe_mode** | 房间内无敌，不可被攻击/Claim/Hack，详见 §3.1a 新手房间分配策略 |

#### 三层扩展模型

Vanilla Ruleset 是 Swarm 扩展体系的第一层。世界定制按照对 SDK 的影响深度分为三层：

```text
┌─────────────────────────────────────────────────┐
│ Layer 1: Core（核心，编译期 IDL 冻结）              │
│   - 官方 SDK 长期稳定，ABI 不变                     │
│   - 身体部件枚举、资源类型、基础 Command 接口         │
│   - 所有 Vanilla 世界使用此层                      │
├─────────────────────────────────────────────────┤
│ Layer 2: Declarative（声明式，world.toml 可配）    │
│   - 参数调整：cost、cooldown、damage_multiplier 等  │
│   - 不改变 SDK 类型系统，仅调数值                    │
│   - 服主可直接修改 world.toml，无需重新编译 SDK      │
├─────────────────────────────────────────────────┤
│ Layer 3: Experimental（实验性，世界特定 schema）     │
│   - 新增类型/能力：自定义 body part、新 damage type  │
│   - 需要 world-specific SDK artifact + ABI hash    │
│   - 玩家需下载对应世界的 SDK 才能编写代码             │
│   - 标记为实验性，不保证跨版本兼容                    │
└─────────────────────────────────────────────────┘
```

**说明**：
- **Layer 1** 是 IDL（Interface Definition Language）层面冻结的类型——新增 body part 枚举值或 Command 类型需要经过正式的 RFC 流程，确保所有 SDK 同步更新。
- **Layer 2** 是 90% 世界定制需求的解决方案——大多数服主只需要调整数值（如加速资源再生、提高伤害倍率、延长 safe_mode 时间），world.toml 即可完成，不触动 SDK。
- **Layer 3** 为深度模组世界预留——当服主希望引入全新机制（如"火焰伤害"类型、"隐身" body part）时，需要生成 world-specific SDK 并在 WASM ABI 中加入 hash 校验，防止玩家用错误 SDK 编译的 WASM 部署到不兼容的世界。

#### 模组世界标识

任何使用 Layer 3 扩展（自定义 body part / damage type / Command）的世界实例**标记为非官方世界**：
- 在世界列表中显示 `[MOD]` 标识
- **不参与官方排名**（World 模式无排行榜，Arena 模式仅 Vanilla 世界计入排名）
- 玩家加入时显示明确警告：「此世界使用非标准规则集，可能与官方 SDK 不兼容。请确认已安装对应的世界 SDK。」

#### 战斗与 PvP

| 规则 | 类型 | 说明 |
|------|------|------|
| `pvp_enabled` | bool | 是否允许 PvP（默认 true） |
| `friendly_fire` | bool | 是否允许攻击同阵营（默认 false） |
| `damage_multiplier` | `fixed<u32,4>` | 伤害倍率 × 10000（默认 10000 = 1.0） |

#### 伤害与武器类型

伤害类型和抗性体系是**世界规则的一部分**——像资源类型一样可由 world.toml 定义和模组扩展。默认世界提供以下基础类型：

```toml
# world.toml — 伤害类型定义（可扩展）
[[damage_types]]
name = "Kinetic"
description = "动能冲击——碰撞、钝击、爆炸"
default_resistance = 1.0

[[damage_types]]
name = "Thermal"
description = "热能——火焰、激光、等离子"
default_resistance = 1.0

[[damage_types]]
name = "EMP"
description = "电磁脉冲——电击、过载、电子干扰"
default_resistance = 1.0

[[damage_types]]
name = "Sonic"
description = "声波——振动、共振、超声波"
default_resistance = 1.0

[[damage_types]]
name = "Corrosive"
description = "腐蚀——酸液、纳米分解、生化"
default_resistance = 1.0

[[damage_types]]
name = "Psionic"
description = "心灵——精神攻击、认知干扰、AI 劫持"
default_resistance = 1.0

# 抗性：按 body part / structure / 属性叠加
# 抗性倍率相乘: final_multiplier = body_resistance × attribute_resistance
[resistances.Tough]
Kinetic = 0.5          # 肉盾：动能减半
Sonic = 0.5            # 减震

[resistances.Structure]
EMP = 2.0              # 建筑弱电磁
Corrosive = 1.5        # 建筑怕腐蚀

# 属性级抗性（Rhai 模组可为实体动态赋予）
# 例如: actions.set_attribute(entity_id, "Shielded", true)
#       → 所有伤害 × 0.7 (需在 world.toml 定义 attribute_multipliers)
```

**Body part 伤害绑定**（完整定义见 `[[body_part_types]]`）：

| Body Part | 默认伤害类型 | 基础伤害值 | 说明 |
|-----------|------------|----------|------|
| Attack | Kinetic | 30 | 近战（距离 1），低成本高伤害 |
| RangedAttack | Kinetic | 25 | 远程（距离 3），射程优势 |
| Tower（建筑自动攻击） | Kinetic | 50 | — |
| Heal | —（反向治疗） | 12 | 每 tick 可缩短一个负面状态 10 tick 持续时间 |

**抗性机制**: 分两层叠加——**组件抗性**（body part / structure 的固定倍率）+ **属性抗性**（由模组/规则动态赋予的倍率，如 `Shielded = 0.7`）。最终倍率 = 组件倍率 × 属性倍率。

**免疫机制**: Rhai 模组可通过 `actions.set_entity_flag(entity_id, "immune_Thermal", true)` 赋予免疫（倍率 = 0）。适用于 Boss 单位、世界事件、特殊建筑。

**模组扩展**: Rhai 模组可注册新伤害类型（`actions.add_damage_type("Fire", 1.0)`）、设置抗性（`actions.set_resistance("Tough", "Fire", 0.3)`）、赋予属性（`actions.set_attribute(entity_id, "Flaming", true)`）。

#### 特殊攻击方式

除了 HP 伤害，以下特殊攻击方式作为 Command 或 body part 能力存在：

| 攻击方式 | 触发 body part | 效果 | 冷却 | 资源消耗 | 抗性 |
|---------|--------------|------|------|---------|------|
| **Hack** | Claim | 夺取目标 drone：施加"控制锁"逐步建立控制——tick 1-2 目标减速 50%，tick 3-4 目标无法移动，tick 5 夺取成功（drone 转为 Neutral，停止执行 WASM，进入 idle）。5 tick 后自动恢复。idle 期间不消耗 lifespan。目标可通过 Disrupt 打断或 Fortify 净化控制锁 | 200 tick | 1000 Energy | 目标 `Psionic` 抗性 |
| **Drain** | Carry + Work | 从目标建筑/存储中窃取资源，每 tick 转移 `carry_capacity` 单位 | 50 tick | 200 Energy/tick | 目标 `EMP` 抗性 |
| **Overload** | RangedAttack | 消耗目标计算配额。目标 `fuel budget` 减少 500k（默认 MAX_FUEL=10M 的 5%）。**下限 MAX_FUEL × 0.2**。**必须满足 `is_visible_to(target, attacker)`——不可攻击不可见玩家。全局冷却：同一目标每 50 tick 最多被 Overload 一次（不限来源）。**Overload 返回静默结果——攻击者无法从结果推断目标 fuel 状态（信息泄露） | 200 tick（drone 冷却） | 300 Energy | 目标 `EMP` 抗性 |
| **Debilitate** | Work | 给目标附加易伤状态。指定伤害类型抗性 ×2，持续 50 tick | 150 tick | 200 Energy | 目标 `Corrosive` 抗性 |
| **Disrupt** | Attack | 打断目标当前动作（Drain/Hack 等持续动作立即终止）。不造成 HP 伤害 | 50 tick | 100 Energy | 目标 `Sonic` 抗性 |
| **Fortify** | Tough | 自身/友方获得护盾（所有抗性 ×0.5）。**同时清除目标所有负面状态**（Debilitate/Drain/Overload/Hack控制锁），持续 100 tick | 300 tick | 400 Energy | 无——增益+净化 |
| **Leech** | Attack | 吸血攻击——造成 Corrosive 15 dmg，伤害的 50% 治疗自身 | 0（即时） | 300 Energy | 目标 `Corrosive` 抗性 |
| **Fabricate** | Work | 将敌方 drone 转化为己方建筑 | 500 tick | 2000 Energy + 500 Matter | 目标 `Psionic` 抗性 |

**通用规则**：
- 特殊攻击与 HP 伤害互斥——同一 body part 在同一 tick 只能执行一种
- 特殊攻击的"命中判定"取决于 body part 数量与目标防御的差值，非简单的命中/未命中
- 持续型攻击（Drain/Hack）在 drone 移动或被 Disrupt 时中断
- 所有特殊攻击受 `damage_multiplier` 世界规则影响（倍率作用于成功率/效果量）

**Neutral 状态**（Hack 夺取后）:
- `owner = Neutral (0)`——不归任何玩家所有
- 停止执行 WASM（进入 idle 状态，不提交指令）
- 不消耗 lifespan、不消耗 fuel
- 5 tick 后自动恢复原 owner（Hack 自然到期）
- 恢复前免疫再次 Hack
- 可见性：对原 owner 保持可见（ally 级），对其他玩家为 enemy 级

#### 身体部件类型定义（`[[body_part_types]]`）

与资源类型和伤害类型一样，身体部件可通过 world.toml 定义和模组扩展。默认世界提供以下 8 种基础类型：

```toml
# world.toml — 身体部件类型定义（可扩展）

[[body_part_types]]
name = "Move"
description = "移动——每 part 每 tick 可消除 1 fatigue"
action = "Move"
range = 1
cost = { Energy = 50 }

[[body_part_types]]
name = "Work"
description = "工作——采集资源、建造建筑、维修"
action = ["Harvest", "Build"]
range = 1
cost = { Energy = 100 }

[[body_part_types]]
name = "Carry"
description = "运输——携带资源，容量 = parts × 50"
action = ["Transfer", "Withdraw"]
passive = { carry_capacity_per_part = 50 }
cost = { Energy = 50 }

[[body_part_types]]
name = "Attack"
description = "近战攻击——距离 1，每 part 30 伤害"
action = "Attack"
damage_type = "Kinetic"
base_damage = 30
range = 1
age_modifier = -80
cost = { Energy = 80 }

[[body_part_types]]
name = "RangedAttack"
description = "远程攻击——距离 3，每 part 25 伤害"
action = "RangedAttack"
damage_type = "Kinetic"
base_damage = 25
range = 3
age_modifier = -50
cost = { Energy = 100 }

[[body_part_types]]
name = "Heal"
description = "治疗——每 part 恢复 12 HP"
action = "Heal"
base_heal = 12
range = 1
age_modifier = -30
cost = { Energy = 250 }

[[body_part_types]]
name = "Claim"
description = "占领——夺取敌方建筑/Controller"
action = "ClaimController"
range = 1
age_modifier = -50
cost = { Energy = 600 }

[[body_part_types]]
name = "Tough"
description = "韧性——被动 HP 加成，每 part +100 hits_max"
passive = { hits_per_part = 100 }
age_modifier = 100
cost = { Energy = 10 }
```

**字段说明**：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `name` | string | ✅ | 唯一标识符 |
| `description` | string | ✅ | 人类可读描述 |
| `action` | string \| string[] | 条件 | 绑定的 CommandAction。`passive` 类型可省略。数组表示支持多种 action（如 Work→Harvest+Build） |
| `passive` | map | 条件 | 被动效果配置（如 Tough 的 hits_per_part、Carry 的 carry_capacity_per_part）。与 action 互斥 |
| `damage_type` | string | 条件 | 攻击类型的伤害类型，引用 `[[damage_types]]` 中的 name |
| `base_damage` | u32 | 条件 | 每 part 的基础伤害值。`damage_type` 存在时必需 |
| `base_heal` | u32 | 条件 | 每 part 的基础治疗量。action=Heal 时必需 |
| `range` | u32 | ✅ | 生效距离（被动类型填 0） |
| `cost` | `{String: u32}` | ✅ | 生成该 body part 的资源消耗，key 为资源名 |
| `age_modifier` | i32 | 否 | 对 drone age_max 的修改量（TOUGH +100 延寿、ATTACK -80 折寿）。不指定则默认为 0 |

**Body part → CommandAction 绑定规则**：

```
┌──────────────────┐      ┌─────────────────────┐
│ BodyPart.name     │ ──▶  │ CommandAction        │
│ + damage_type     │      │ + damage 计算         │
│ + base_damage     │      │ + 校验 (body part 存在) │
│ + range           │      │ + 消耗 (冷却/资源)     │
│ + cost            │      └─────────────────────┘
└──────────────────┘
```

- 一个 CommandAction 可被多个 body part 触发（如 `Move` 只能由 `Move` part 触发，但 `Attack` 在未来可由 `Claw`/`Bite` 等多个 part 触发）
- 新 body part 绑定到**已有 CommandAction** 时，只需定义不同的 damage_type/base_damage/cost ——引擎自动复用该 action 的校验和应用逻辑
- 引入**新 CommandAction** 时（如 `Leech`），需在引擎中注册新的 `CommandAction` 变体 + 对应的 validate/apply handler + 在 IDL 中暴露给 SDK

**模组扩展**：Rhai 模组可通过以下 API 注册新 body part：

```rust
// Rhai API（远期扩展——MVP阶段通过world.toml [[custom_actions]]声明式配置）
actions.add_body_part_type("Leech", #{
    action: "Leech",           // 新 CommandAction
    damage_type: "Corrosive",
    base_damage: 15,
    range: 1,
    cost: #{ Energy: 300 },
    special: "heal_self_50pct" // 特殊效果：伤害的 50% 治疗自身
});
```

#### 自定义 CommandAction（`[[custom_actions]]`）

当新 body part 需要的动作无法映射到已有 CommandAction 时，需注册新的 CommandAction 变体：

```toml
# world.toml — 自定义 CommandAction（需引擎编译时注册）

[[custom_actions]]
name = "Leech"
description = "吸血攻击——造成伤害并治疗自身 50%"
damage_type = "Corrosive"
base_damage = 15
range = 1
special_effect = "heal_self"
special_param = 0.5

[[custom_actions]]
name = "Scramble"
description = "扰乱——随机重排目标下一 tick 的指令执行顺序"
range = 3
special_effect = "scramble_commands"
cooldown = 100
cost = { Energy = 400 }

[[custom_actions]]
name = "Fabricate"
description = "转化——将敌方 drone 转化为己方建筑"
range = 1
special_effect = "convert_to_structure"
cooldown = 500
cost = { Energy = 2000, Matter = 500 }
```

**注册流程**：

```
1. world.toml 中声明 [[custom_actions]]
   → 引擎启动时解析，动态注册 CommandAction 变体
2. 每个 custom action 需提供对应的 validate/apply handler：
   - 已有 special_effect 的（如 heal_self, scramble_commands）引擎内置
   - 全新效果的需通过 Rhai 模组提供 handler
3. IDL 自动生成——新 CommandAction 自动暴露给 SDK 和 MCP
4. WASM 模块通过 tick() → Command[] 使用新 action（与内置 action 语法一致）
```

**字段说明**：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `name` | string | ✅ | 唯一标识符，生成 `CommandAction::{name}` 变体 |
| `description` | string | ✅ | 人类可读描述 |
| `damage_type` | string | 否 | 伤害类型，引用 `[[damage_types]]` |
| `base_damage` | u32 | 否 | 基础伤害值 |
| `range` | u32 | ✅ | 生效距离 |
| `special_effect` | string | 否 | 特殊效果标识符，引用 `[[special_effects]]` 中定义的 name。内置默认效果见下方 |
| `special_param` | float | 否 | 特殊效果的参数 |
| `cooldown` | u32 | 否 | 冷却时间（tick） |
| `cost` | `{String: u32}` | 否 | 每次使用的资源消耗（body part spawn 成本在 `[[body_part_types]]` 中独立定义） |

#### 特殊效果类型定义（`[[special_effects]]`）

与 body_part_types 和 damage_types 一样，特殊效果可通过 world.toml 定义和扩展。每个 `[[special_effects]]` 条目定义一个可由 `[[custom_actions]]` 引用的效果类型：

```toml
# world.toml — 特殊效果类型定义（可扩展）

[[special_effects]]
name = "hack"
description = "夺取目标 drone——施加控制锁逐步建立控制，5 tick 后目标转为 Neutral"
handler = "hack"               # 引擎内置 handler 名
target = "enemy_drone"         # enemy_drone | enemy_structure | self | ally | any
duration = 5                   # 持续 tick 数（0 = 即时）
resistance = "Psionic"          # 目标抗性检查（引用 [[damage_types]]）

[[special_effects]]
name = "drain"
description = "从目标建筑/存储中窃取资源，每 tick 转移 carry_capacity 单位"
handler = "drain"
target = "enemy_structure"
duration = 0                   # 持续型，手动中断
resistance = "EMP"

[[special_effects]]
name = "overload"
description = "消耗目标计算配额——fuel budget -500k，下限 MAX_FUEL×0.2"
handler = "overload"
target = "enemy_player"
duration = 0                   # 即时
resistance = "EMP"

[[special_effects]]
name = "debilitate"
description = "给目标附加易伤状态——指定伤害类型抗性×2"
handler = "debilitate"
target = "enemy_any"
duration = 50
resistance = "Corrosive"

[[special_effects]]
name = "disrupt"
description = "打断目标当前持续动作（Drain/Hack/Debilitate 等），不造成 HP 伤害"
handler = "disrupt"
target = "enemy_drone"
duration = 0                   # 即时
resistance = "Sonic"

[[special_effects]]
name = "fortify"
description = "自身/友方获得护盾（所有抗性×0.5）+ 清除所有负面状态"
handler = "fortify"
target = "self_or_ally"
duration = 100
# 无 resistance — 增益效果不检查抗性

[[special_effects]]
name = "leech"
description = "吸血——造成伤害的 50% 治疗自身"
handler = "leech"
target = "enemy_any"
duration = 0
resistance = "Corrosive"
# special_param = 0.5 → 治疗比例，在 [[custom_actions]] 中指定

[[special_effects]]
name = "fabricate"
description = "将敌方 drone 转化为己方建筑"
handler = "fabricate"
target = "enemy_drone"
duration = 0
resistance = "Psionic"

[[special_effects]]
name = "heal_self"
description = "造成伤害的指定比例治疗自身"
handler = "heal_self"
target = "enemy_any"
duration = 0

[[special_effects]]
name = "scramble_commands"
description = "随机重排目标下 tick 的指令执行顺序"
handler = "scramble_commands"
target = "enemy_drone"
duration = 0

[[special_effects]]
name = "convert_to_structure"
description = "将目标 drone 转化为己方建筑"
handler = "convert_to_structure"
target = "enemy_drone"
duration = 0
resistance = "Psionic"
```

**字段说明**：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `name` | string | ✅ | 唯一标识符，被 `[[custom_actions]].special_effect` 引用 |
| `description` | string | ✅ | 人类可读描述 |
| `handler` | string | ✅ | 引擎内置处理器名。内置：`hack`, `drain`, `overload`, `debilitate`, `disrupt`, `fortify`, `leech`, `fabricate`, `heal_self`, `scramble_commands`, `convert_to_structure` |
| `target` | enum | ✅ | 目标类型：`enemy_drone`, `enemy_structure`, `enemy_player`, `enemy_any`, `self`, `ally`, `self_or_ally`, `any` |
| `duration` | u32 | ✅ | 持续 tick 数（0 = 即时生效） |
| `resistance` | string | 否 | 目标抗性检查，引用 `[[damage_types]]` 中的 name。无此字段 = 不检查抗性 |

**注册流程**：

```
1. world.toml 中声明 [[special_effects]]
   → 引擎启动时解析，注册到 SpecialEffectRegistry
2. [[custom_actions]] 中通过 special_effect = "name" 引用
   → 引擎在 CommandAction 注册时自动绑定 handler
3. 引擎内置所有 handler（hack/drain/overload/…）— 无需 Rhai 即可使用
4. 服主只需在 world.toml 中声明 [[custom_actions]] + 引用已有 [[special_effects]]
   → 新特殊攻击只需 TOML 配置，无需改 Rust 代码
5. 如需全新 handler（TOML 配置无法表达的效果），通过 Rhai 模组注册
```

**默认 world.toml 中的特殊攻击注册**：

```toml
# 以下 8 个特殊攻击在默认 world.toml 中预注册
# 服主可禁用（注释/删除）或修改参数

[[custom_actions]]
name = "Hack"
description = "夺取 drone——5 tick 控制锁后转为 Neutral"
special_effect = "hack"
cooldown = 200
cost = { Energy = 1000 }

[[custom_actions]]
name = "Drain"
description = "从目标建筑窃取资源"
special_effect = "drain"
cooldown = 50
cost = { Energy = 200 }

[[custom_actions]]
name = "Overload"
description = "消耗目标 fuel budget 500k"
special_effect = "overload"
cooldown = 200
cost = { Energy = 300 }

[[custom_actions]]
name = "Debilitate"
description = "施加易伤——指定伤害类型抗性×2，持续 50 tick"
special_effect = "debilitate"
special_param = 2.0
cooldown = 150
cost = { Energy = 200 }

[[custom_actions]]
name = "Disrupt"
description = "打断目标持续动作"
special_effect = "disrupt"
cooldown = 50
cost = { Energy = 100 }

[[custom_actions]]
name = "Fortify"
description = "护盾+净化——所有抗性×0.5，清除负面状态"
special_effect = "fortify"
special_param = 0.5
cooldown = 300
cost = { Energy = 400 }

[[custom_actions]]
name = "Leech"
description = "吸血攻击——伤害 50% 治疗自身，Corrosive 15 dmg"
damage_type = "Corrosive"
base_damage = 15
range = 1
special_effect = "leech"
special_param = 0.5
cost = { Energy = 300 }

[[custom_actions]]
name = "Fabricate"
description = "将敌方 drone 转化为己方建筑"
range = 1
special_effect = "fabricate"
cooldown = 500
cost = { Energy = 2000, Matter = 500 }
```

#### 可见性与观战

可见性分两层：**drone 感知**（影响游戏公平性）和**玩家视野**（影响观战体验）。

##### Drone 感知（进入 snapshot）

| 规则 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `fog_of_war` | bool | true | drone 的 WASM `tick()` snapshot 是否受可见性限制。true = drone 只能"看到"感知范围内的实体（视觉/听觉/嗅觉分层）；false = snapshot 包含全地图（合作/教学世界） |

##### 玩家视野（人类屏幕 / AI MCP 查看）

| 规则 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `player_view` | enum | `"drone"` | `"drone"` = 玩家只能看到自己 drone 所见；`"full"` = 玩家实时看到全地图（无论 drone 感知范围）；`"allied"` = 看到所有同阵营 drone 的聚合视野 |
| `public_spectate` | bool | false | 是否允许未登录用户实时旁观（只读 WebSocket）。World 默认关，Arena 默认开 |
| `spectate_delay` | u32 | 0 | 旁观延迟（tick 数）。0 = 实时；>0 = 延迟回放，防止观众信息泄露给参赛者 |
| `replay_privacy` | enum | `"private"` | 回放可见性：`"private"` = 仅自身；`"allies"` = 同阵营可看；`"world"` = 同世界玩家可看；`"public"` = 任何人（含未登录）。Arena 模式赛后强制 `"public"` |

**组合示例**：

| 场景 | fog_of_war | player_view | 效果 |
|------|-----------|-------------|------|
| 标准 World | true | drone | drone 感知有限，玩家只看自己 drone 所见 |
| 教学世界 | false | full | 新手看到全地图，drone 也能感知全图 |
| 竞技观战 | true | drone | drone 公平受限，但观众通过 `public_spectate` + `spectate_delay=100` 看延迟全图 |
| 合作 PvE | true | allied | drone 各自感知，但玩家看到所有友方聚合视野 |

### 8.3 配置格式

```toml
# world.toml — 每个世界实例的配置文件

[world]
name = "World of Swarm"
mode = "persistent"              # persistent | arena

[spawn]
policy = "RandomRoom"
respawn = "NewRoom"
cooldown = 100                   # 加入后 100 tick 才能操作

[code]
update_cost = { Energy = 500 }   # 部署消耗 500 能量
update_cooldown = 100            # 两次部署间隔 100 tick
update_window = { every = 1000, duration = 100 }  # 每 1000 tick 开放 100 tick 窗口
propagation_speed = 3            # 每 tick 传播 3 格
propagation_source = "Spawn"     # 从出生点向外传播

[drone]
env_vars = true                  # 允许环境变量
memory_size = 2048               # 每 drone 2KB 存储
lifespan = 1500                  # drone 存活 tick 数上限
memory_spawn_cost = { Energy = 0.5 }     # 每 byte 孵化成本
memory_upkeep_cost = { Energy = 0.01 }   # 每 byte 每 tick 维护费

[visibility]
fog_of_war = true                # drone 感知受可见性限制
player_view = "drone"            # 玩家只看自己 drone 所见
public_spectate = false          # World 模式默认不公开旁观
spectate_delay = 0               # 回放无延迟

[resources]
source_regeneration_rate = 10000     # ×10000 精度，默认 1.0
build_cost_multiplier = 10000
drone_decay_rate = 10000

# 物流配置
global_storage_enabled = true
global_storage_capacity = 100000
transfer_to_global_cost = { Energy = 0.01 }    # 1% 损耗
transfer_from_global_cost = { Energy = 0.05 }   # 5% 损耗
market_requires_terminal = true

# 自定义资源类型
[[resource_types]]
name = "Energy"
display_name = "能量"
category = "energy"
starting_amount = 1000
max_storage = 100000

[[resource_types]]
name = "Matter"
display_name = "物质"
category = "mineral"
starting_amount = 500
max_storage = 50000

# 各动作资源消耗
# 注意: body part spawn 成本在 [[body_part_types]].cost 中定义，此处不重复
[actions.costs]
spawn = { Energy = 200, Matter = 50 }
build.Extension = { Energy = 50 }
build.Tower = { Energy = 100, Matter = 25 }
code_update = { Energy = 500 }
repair_per_hit = { Energy = 1 }

# 资源点类型
[[source_types]]
name = "EnergyField"
produces = { Energy = 1 }
capacity = 3000
regeneration = 300

[[source_types]]
name = "MatterDeposit"
produces = { Matter = 1 }
capacity = 2000
regeneration = 10

[combat]
pvp_enabled = true
friendly_fire = false
damage_multiplier = 10000
```

### 8.4 ECS 集成方式

每个规则类别对应一个可选的 ECS System。引擎启动时读取 `world.toml`，有选择地注册 System：

```rust
// engine 启动时
fn register_rule_systems(app: &mut App, config: &WorldConfig) {
    // 基础系统始终注册
    // 主线（必须串行，有数据依赖）
    app.add_systems(Update, (
        death_mark_system,       // 标记待死亡 entity，释放 room cap
        spawn_system,            // 统一创建校验通过的 drone
        combat_system,           // 战斗结算（damage 先 → heal 后）
        death_cleanup_system,    // 实际 despawn
    ).chain());

    // 无依赖系统（与主线并行，仅需在 death_cleanup 前完成）
    app.add_systems(Update, (
        regeneration_system,     // 资源点再生
        decay_system,            // 疲劳/冷却递减
    ).after(death_mark_system).before(death_cleanup_system));

    // 注入资源注册表——所有 System 通过它查询资源类型和消耗
    let resource_registry = ResourceRegistry::from_config(&config);
    app.insert_resource(resource_registry);

    // 规则系统按配置注册
    if config.code.propagation_speed > 0 {
        app.add_systems(Update, code_propagation_system.before(spawn_system));
    }
    if config.drone.memory_upkeep_cost.len() > 0 {
        app.add_systems(Update, memory_upkeep_system.before(decay_system));
    }
    // ...
}

// ResourceRegistry 是运行时的资源类型字典
struct ResourceRegistry {
    types: IndexMap<String, ResourceDef>,  // IndexMap 保证迭代顺序确定
    action_costs: ActionCosts,       // spawn, build.*, body_part.*, ...
    source_types: Vec<SourceDef>,
}

impl ResourceRegistry {
    /// 查询某个动作的资源消耗
    fn cost(&self, action: &str, detail: Option<&str>) -> HashMap<String, u32> {
        // action = "build", detail = "Tower"
        // → { "Energy": 100, "Matter": 25 }
    }
}
```

关键是：**核心引擎不硬编码 Energy**。它只操作 `HashMap<ResourceName, Amount>`。资源名是配置决定的字符串。

```rust
// 之前（硬编码）
struct Resource { energy: u32 }

// 之后（动态）
struct Resource {
    amounts: IndexMap<String, u32>,  // IndexMap 保证迭代顺序确定
}
struct ResourceDef {
    name: String,
    display_name: String,
    category: ResourceCategory,
    starting_amount: u32,
    max_storage: u32,
    decay_rate: u32,  // 每 tick 衰减比例 × 精度因子（0 = 不衰减）
    tradeable: bool,
}
```

### 8.5 WASM 侧感知（Deferred 模型）

WASM 模块通过 `tick(snapshot_json) → commands_json` 延迟模型运作：
- 引擎将快照 JSON 写入 WASM 线性内存，调用 `tick()`
- WASM 模块通过**查询 host function**（get_terrain、get_objects_in_range、path_find、get_world_config）读取世界状态
- `tick()` 返回指令 JSON 列表，引擎在校验后统一应用

```typescript
// TypeScript SDK — tick() 接收 Snapshot，返回 Command[]
function tick(snapshot: WorldSnapshot): Command[] {
    // 查询世界配置（只读 host function）
    const registry = snapshot.resourceRegistry;

    // 查看世界中定义了哪些资源
    for (const [name, def] of registry.types) {
        console.log(`${name} (${def.display_name}): max ${def.maxStorage}`);
    }

    // 查询动作消耗
    const spawnCost = registry.cost("spawn");
    // → { Energy: 200, Matter: 50 }

    // 生成指令列表
    const commands: Command[] = [];

    // 检查资源 → 决定指令
    if (snapshot.player.resources.has(spawnCost)) {
        commands.push({ cmd: "spawn", body: [...] });
    }

    // 采集指令
    commands.push({ cmd: "harvest", target: sourceId, resource: "Matter" });

    // 传输指令
    commands.push({ cmd: "transfer", target: targetId, resources: { Energy: 100, Matter: 50 } });

    // 返回指令 JSON — 引擎统一校验后执行
    return commands;
}
```

> **设计合同**: WASM 模块通过 `tick() → JSON` 延迟模型运作。所有 mutating 操作以 JSON 指令形式返回，引擎统一校验和应用。不得通过 host function 直接修改世界状态。

### 8.6 World 与 Arena 的默认规则

| 规则 | World 默认值 | Arena 默认值 |
|------|------------|------------|
| `spawn_policy` | `RandomRoom` | `FixedSpawn`（对称） |
| `code_update_cost` | 0（免费） | 0 |
| `code_update_window` | 无限制 | 赛前锁定 |
| `code_propagation_speed` | 0（即时） | 0（即时） |
| `drone_env_vars` | true | true |
| `pvp_enabled` | true | true（必须） |

### 8.7 Rule Module System — 可安装的游戏模组

规则模组是**可安装的 Rhai 脚本 + 声明式配置**——轻量、确定、可组合。

```
玩家代码:  WASM → 控制 drone     (不可信 → sandbox)
规则模组:  Rhai → 修改世界规则    (服主声明 → 引擎嵌入)
引擎核心:  Rust → 确定性模拟      (不可变)
```

#### 为什么不是 WASM

| | WASM（玩家） | Rhai（规则） |
|------|-------------|------------|
| 信任模型 | 不可信，需要进程隔离 | 服主自行安装，可信 |
| 编译步骤 | 需要外部工具链 | 无，引擎直接执行源码 |
| 确定性 | 依赖 wasmtime 版本 | 同引擎版本完全确定 |
| 语言复杂度 | 取决于源语言 | 极简，类似 Rust/JS |
| 性能 | JIT | AST 解释（规则场景足够） |

#### 模组结构

一个模组是一个目录：

```
empire-upkeep/
├── mod.toml          # 模组元数据 + 可配置参数声明
├── init.rhai         # 加载时执行一次
├── tick_start.rhai   # 每 tick 开始时执行
└── tick_end.rhai     # 每 tick 结束时执行
```

##### mod.toml

```toml
[meta]
name = "empire-upkeep"
version = "1.2.0"
description = "帝国规模维护费——drone 和房间越多，每 tick 消耗越大"
author = "kagurazaka"
license = "MIT"
dependencies = []       # 依赖的其他模组
conflicts = []          # 冲突的模组

# 可配置参数——每项在脚本中作为全局变量可用
[config]
drone_cost = { type = "u32", default = 2, min = 0, max = 100, description = "每 drone 每 tick 维护费" }
room_base = { type = "u32", default = 10, min = 0, max = 1000, description = "每房间基础维护费" }
room_superlinear = { type = "fixed<u32,4>", default = 1, min = 0, max = 100, description = "超线性系数（定点数，4位小数精度）" }
onshortfall = { type = "enum", default = "degrade", values = ["degrade", "damage", "despawn"], description = "资源不足时的处理方式" }
```

##### init.rhai

```rust
// 模组加载时执行一次——验证配置、初始化内部状态
fn init(config, actions) {
    actions.log_info(`empire-upkeep v${MOD_VERSION} loaded`);
    actions.log_info(`  drone_cost=${config.drone_cost}`);
    actions.log_info(`  room_superlinear=${config.room_superlinear}`);
    actions.log_info(`  onshortfall=${config.onshortfall}`);
}
```

##### tick_end.rhai

```rust
// 每 tick 结束时执行——计算维护费并扣除
fn on_tick_end(state, events, config, actions) {
    for player in state.players() {
        let drones = player.drones().len();
        let rooms = player.rooms().len();

        // 超线性：房间越多，每房间成本越高
        // room_superlinear 为 fixed<u32,4> 定点数（4位小数精度）
        let room_penalty = rooms * (config.room_base +
            rooms * config.room_superlinear / FIXED_SCALE);

        let total_cost = drones * config.drone_cost + room_penalty;

        actions.deduct_resource(player.id, "Energy", total_cost);
        actions.emit_event("upkeep_charged", #{
            player: player.id,
            drones: drones,
            rooms: rooms,
            cost: total_cost
        });
    }
}
```

#### Rhai API：模组可用的函数

```rust
// 状态查询（经可见性过滤——模组不能看到隐藏实体）
state.players()          → Iterator<Player>        // 聚合统计，不暴露具体玩家
state.tick()             → u64
player.drones()          → Iterator<Drone>          // 仅该玩家的 drone（owner=player_id）
player.rooms()           → Iterator<Room>           // 仅该玩家有视野的房间
player.resources()       → Map<String, u64>         // 仅该玩家的资源
drone.body_parts()       → Vec<BodyPart>
drone.position()         → (x, y, room_id)

// 世界修改（通过 actions，不进命令管线但经 mini-validator）
actions.deduct_resource(player_id, resource, amount)   // 扣除资源
actions.award_resource(player_id, resource, amount)    // 奖励资源
actions.damage_entity(entity_id, amount, reason)       // 对实体造成伤害
actions.set_entity_flag(entity_id, flag, value)        // 设置白名单标记（如 slow/empowered）
actions.emit_event(event_type, data)                   // 发出事件
actions.log_info(message)                              // 日志
actions.log_warn(message)

// 不可用: modify_entity（不在能力白名单中）
// 不可用: 文件 IO、网络、时钟、随机数（确定性要求）
```

#### Rhai 执行预算

每个模组每次 `tick_start` / `tick_end` 钩子的执行预算：

| 资源 | 限制 | 超限行为 |
|------|------|---------|
| AST 节点数（软限制） | 10,000/tick | 该模组本次 tick 跳过，记录警告 |
| actions 调用次数 | 100/tick | 超出部分丢弃 |
| `state.players()` 迭代 | 3,000 项 | 超出的玩家跳过 |
| 确定性节点预算（硬限制） | 100,000 AST 节点/tick | 强制终止当前模组，**该模组本 tick 的所有 actions 全部回滚**（事务性隔离）。超限模组记录警告，连续 10 tick 超限自动禁用。AST 节点数是确定性度量——同一输入在任何硬件上终止于相同节点，保证 state_checksum 可复现。墙钟仅用于告警监控（如单模组 >2s 触发运维告警），不作为状态决定因素。 |

> 连续 10 tick 超限的模组自动禁用，需服主手动重新启用。防止恶意/错误模组拖垮引擎。

所有 `actions` 操作被记录到 TickTrace——可回放、可审计。

#### Rhai 安全隔离

Rhai 模组默认在**进程隔离**模式下运行，通过 IPC 与核心引擎通信，确保模组崩溃或恶意行为不会影响引擎稳定性。

**隔离模式**：

| 模式 | 隔离级别 | 性能 | 适用场景 |
|------|---------|------|---------|
| 进程隔离（默认） | Rhai engine 运行于独立 sandbox 进程（cgroup + seccomp 加固） | 中等 | 生产环境、不信任模组来源 |
| 进程内 | Rhai engine 与核心引擎共享进程 | 高 | 开发/调试、完全信任所有模组来源 |

服主可通过 `world.toml` 切换模式：

```toml
[rhai]
isolation = "process"   # "process" | "inprocess"
```

> **安全建议**: 生产环境始终使用 `process` 模式。`inprocess` 模式下，恶意模组可通过死循环或内存耗尽拖垮整个引擎进程。

**能力白名单**：所有 Rhai actions 必须经过引擎显式注册的 action handler 白名单。未注册的 action 调用在引擎侧被拒绝，即使 Rhai 脚本语法正确。引擎启动时构建白名单，运行时所有 `actions.*` 调用经白名单校验后才执行。

当前白名单 action：

| Action | Handler | 说明 |
|--------|---------|------|
| `deduct_resource` | `engine::rule::handler::deduct_resource` | 扣除玩家资源 |
| `award_resource` | `engine::rule::handler::award_resource` | 奖励玩家资源 |
| `damage_entity` | `engine::rule::handler::damage_entity` | 对实体造成伤害 |
| `set_entity_flag` | `engine::rule::handler::set_entity_flag` | 设置白名单标记（如 slow/empowered/immune_Thermal） |
| `emit_event` | `engine::rule::handler::emit_event` | 发出世界事件 |
| `log_info` / `log_warn` | `engine::rule::handler::log` | 日志输出 |

> 扩展新 action 需在引擎中注册 handler + 加入白名单。未注册的 action 在运行时被拒绝并记录安全审计日志。

#### 安装与配置

模组分发模型：**一个模组 = 一个 git 仓库**。无中心化市场或注册表。

```
内置模组:  engine/mods/ 目录下随引擎分发（多子目录，每个子目录一个模组）
第三方:   任意 git 仓库，服主 clone 到本地后引用
```

```bash
# 安装第三方模组（git clone 到本地模组目录）
swarm mod add https://git.kagurazakalan.com/swarm/mods/empire-upkeep.git

# 安装指定版本（git tag）
swarm mod add https://git.kagurazakalan.com/swarm/mods/empire-upkeep.git --tag v1.2.0

# 查看已安装模组
swarm mod list

# 查看模组的可配置项
swarm mod config empire-upkeep

# 设置参数
swarm mod config empire-upkeep drone_cost 5
swarm mod config empire-upkeep onshortfall "damage"

# 在世界中启用（引用已安装的模组名）
swarm world add-mod empire-upkeep

# 更新模组（git pull，自动更新 mods.lock）
swarm mod update empire-upkeep
```

**版本锁定**：`world.toml` 和 `mods.lock` 分离——前者由服主编辑（表达意图），后者由工具自动生成（记录解析结果）。

```
world.toml              mods.lock
──────────              ─────────
服主手写                 自动生成，不应手改
version = "1.2"         rev = "a1b2c3d..."
"我要这个 tag"          "已解析为这个 commit"
提交到 git               提交到 git
```

`swarm mod add` 和 `swarm mod update` 自动将当前 checkout 的 commit hash 写入 `mods.lock`。引擎启动时以 `mods.lock` 为准进行 checkout；若所在 commit 与 `world.toml` 声明的 tag 不对应（tag 被 force-push），发出告警。`mods.lock` 可选包含 content hash（`checksum` 字段），提供类似 `Cargo.lock` 的完整性校验。

世界配置中引用（`world.toml`，仅表达意图）：

```toml
# world.toml — 服主编辑，表达意图
[world]
name = "Survival World"

[[mods]]
name = "empire-upkeep"
source = "https://git.kagurazakalan.com/swarm/mods/empire-upkeep.git"
version = "1.2.0"              # git tag — 人类可读
[mods.config]
drone_cost = 5
room_superlinear = 2            # fixed<u32,4>: 0.0002 超线性系数
onshortfall = "damage"

[[mods]]
name = "resource-decay"
source = "https://git.kagurazakalan.com/swarm/mods/resource-decay.git"
version = "0.3.0"
[mods.config]
decay_rate = 0.001
```

```toml
# mods.lock — 工具自动生成，记录解析结果，与 world.toml 一并提交
[[mods]]
name = "empire-upkeep"
source = "https://git.kagurazakalan.com/swarm/mods/empire-upkeep.git"
version = "1.2.0"
rev = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"   # 不可变 commit hash
checksum = "sha256:8f3a..."                          # 可选：内容完整性校验

[[mods]]
name = "resource-decay"
source = "https://git.kagurazakalan.com/swarm/mods/resource-decay.git"
version = "0.3.0"
rev = "e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
```

#### 引擎集成

```rust
fn register_mod_systems(app: &mut App, world_config: &WorldConfig) {
    // world_config.mods 中的每个条目已解析为本地路径：
    //   内置模组 → engine/mods/{name}/
    //   第三方   → ~/.swarm/mods/{host}/{owner}/{repo}/（git clone 目录）
    for mod_def in &world_config.mods {
        let mut module = load_mod_from_path(&mod_def.path);
        module.configure(&mod_def.config);                // 注入参数
        module.run_init();                                 // init.rhai

        // 注册 tick 钩子
        let tick_end = module.tick_end_script.clone();
        app.add_systems(Update, move |world: &mut World| {
            let state = WorldState::from_world(world);
            let mut actions = RuleActions::new();
            let events = TickEvents::current();
            tick_end.call(&state, &events, &module.config, &mut actions);
            actions.apply(world);  // 经校验后写入
        }.after(death_cleanup_system));
    }
}
```

#### 模组分发

**一个模组 = 一个 git 仓库**。Swarm 不运营中心化模组市场或注册表。

```
分发路径:

  内置模组                     第三方模组
  ┌──────────────────┐       ┌─────────────────────┐
  │ engine/mods/      │       │ 任意 git 仓库        │
  │   empire-upkeep/  │       │ swarm mod add <url>  │
  │   fog-of-war/     │       │ → clone 到本地        │
  │   resource-decay/ │       │ → world.toml 引用     │
  │   ...             │       └─────────────────────┘
  └──────────────────┘
    随引擎源码分发                 服主自行管理
    默认启用（可禁用）              按需安装
```

**内置模组**：引擎仓库 `engine/mods/` 下的每个子目录是一个内置模组。引擎启动时自动发现并注册，服主可在 `world.toml` 中禁用不需要的。内置模组提供官方默认规则集的核心扩展——empire-upkeep、fog-of-war、resource-decay 等。

**第三方模组**：服主通过 `swarm mod add <git-url>` 安装。引擎 clone 到本地模组目录后，`world.toml` 通过 `source` + `version`（git tag）引用。更新通过 `swarm mod update`（背后是 `git pull` + checkout tag）。

**发现**：不提供中心化搜索。模组通过社区渠道分发——文档 wiki、论坛、社交网络。模组仓库的 README 即为"商店页面"。

#### 规则可见性与 i18n

世界的活跃规则对所有玩家（人类和 AI）完全可见。每个配置项都有多语言描述。

##### mod.toml 中的 i18n

```toml
[meta]
name = "empire-upkeep"
version = "1.2.0"
description = "帝国规模维护费"

# 多语言描述
[meta.description_i18n]
zh = "帝国规模维护费——drone 和房间越多，每 tick 消耗越大。维护费不足时效率下降。"
en = "Empire upkeep — more drones and rooms cost more per tick. Shortfall degrades efficiency."
ja = "帝国維持費——ドローンと部屋が多いほど毎 tick のコストが増加。不足時は効率低下。"

[config]

[config.drone_cost]
type = "u32"
default = 2
min = 0
max = 100
[config.drone_cost.description_i18n]
zh = "每架 drone 每 tick 消耗的能量"
en = "Energy consumed per drone per tick"
ja = "ドローン1機あたりの毎 tick エネルギー消費"

[config.room_superlinear]
type = "fixed<u32,4>"
default = 1
min = 0
max = 100
[config.room_superlinear.description_i18n]
zh = "超线性系数——房间越多，每间房的单位成本越高"
en = "Superlinear factor — more rooms increase per-room cost"
ja = "超線形係数——部屋が増えるほど1部屋あたりのコストが上昇"

[config.onshortfall]
type = "enum"
default = "degrade"
values = ["degrade", "damage", "despawn"]
[config.onshortfall.description_i18n]
zh = "资源不足时的处理方式：degrade=效率下降, damage=建筑受损, despawn=单位消亡"
en = "Behavior on resource shortfall: degrade=slow, damage=hurt buildings, despawn=lose units"
ja = "リソース不足時の動作：degrade=効率低下, damage=建物損傷, despawn=ユニット消滅"
[config.onshortfall.values_i18n]
degrade = { zh = "效率下降", en = "Efficiency degradation", ja = "効率低下" }
damage = { zh = "建筑受损", en = "Building damage", ja = "建物損傷" }
despawn = { zh = "单位消亡", en = "Unit despawn", ja = "ユニット消滅" }
```

##### 玩家可见的世界规则

人类玩家在 Web UI 中看到：

```
┌─────────────────────────────────────────────┐
│  世界规则 — Survival World                    │
│                                               │
│  🔧 empire-upkeep v1.2.0                      │
│  帝国规模维护费——drone 和房间越多，每 tick    │
│  消耗越大。维护费不足时效率下降。               │
│                                               │
│  当前参数:                                     │
│    drone_cost = 5        每架 drone 每 tick   │
│                          消耗的能量             │
│    room_superlinear = 0.2                     │
│                          超线性系数             │
│    onshortfall = damage  资源不足时的处理方式    │
│                                               │
│  🍂 resource-decay v0.3.0                     │
│  资源腐败衰减——储存的资源随时间缓慢减少。        │
│                                               │
│  当前参数:                                     │
│    decay_rate = 0.001   每 tick 衰减比例        │
└─────────────────────────────────────────────┘
```

AI 玩家通过 MCP 查询：

```
mcp.call("swarm_get_world_rules")
→ {
  "mods": [
    {
      "name": "empire-upkeep",
      "version": "1.2.0",
      "description": "帝国规模维护费——drone 和房间越多...",
      "config": {
        "drone_cost": { "value": 5, "type": "u32", "min": 0, "max": 100,
                        "description": "每架 drone 每 tick 消耗的能量" },
        "room_superlinear": { "value": 2, "type": "fixed<u32,4>",
                              "description": "超线性系数——房间越多..." },
        "onshortfall": { "value": "damage", "type": "enum",
                         "values": ["degrade","damage","despawn"],
                         "description": "资源不足时的处理方式" }
      }
    }
  ]
}
```

##### WASM 侧查询

玩家的 drone 代码可以查询当前世界规则：

```typescript
// TypeScript SDK
const rules = Game.world.rules();

for (const mod of rules.active_mods) {
    console.log(`${mod.name} v${mod.version}`);
    console.log(`  ${mod.description}`);
    for (const [key, param] of mod.config) {
        console.log(`  ${key} = ${param.value}  // ${param.description}`);
    }
}

// 根据规则调整策略
if (rules.get("empire-upkeep").config.onshortfall.value === "damage") {
    // 维护费不足会损坏建筑——必须保持能量正流入
    strategy.prioritize_energy_income();
}
```

##### 语言选择

引擎根据请求的 `Accept-Language` 头或 MCP 客户端的 `locale` 参数返回对应语言的描述。缺少翻译时回退到 `en`，再回退到 `description` 字段。

#### 帝国维护费示例效果

```
小帝国（1 房, 20 drone）: 维护费 ≈ 40/tick     — 轻松
中帝国（5 房, 100 drone）: 维护费 ≈ 275/tick   — 可承受
大帝国（20 房, 500 drone）: 维护费 ≈ 2100/tick  — 需要高效经济
巨帝国（50 房, 500 drone）: 维护费 ≈ 3150/tick — 硬上限

不是不可逾越——达到上限前「你能支撑多大就有多大」。
想维持巨帝国？你的 drone 物流必须极致优化。
```

### 8.8 Determinism Contract — 确定性合同

#### 固定算法

| 组件 | 算法 | 说明 |
|------|------|------|
| PRNG | **Blake3 XOF** | 确定种子 + offset → 随机流。与哈希同原语，消除 ChaCha 依赖，纯软件 ~6 GB/s。XOF 模式：`blake3::Hasher::update_with_seek(seed, offset)` |
| 种子 | world_seed = Blake3(32随机字节) | 32 字节熵（256-bit），编码为 hex 字符串。不可从 tick_number 推导。**每 10,000 tick 自动轮换**（Blake3(旧种子, 当前tick)），防止长期观察推断种子空间 |
| Hash | **Blake3** | 固定实现。不用 std::hash / SipHash（跨版本可变）。 |
| 种子洗牌 | Blake3(tick_number \\|\\| world_seed) | 每 tick 确定但不可预测的玩家顺序。**不是手速/运气**——玩家无法通过加快操作影响排序位置。公平随机：所有玩家同等不可预测，相同种子=相同顺序，可回放验证 |
| ECS 顺序 | `.chain()` + `.before()/.after()` | 有数据依赖的串行（death→spawn→combat→death_cleanup），无依赖的并行（regeneration, decay）。Bevy 依赖图保证偏序不变，确定性不依赖并行度 |
| 数值 | 整数 + 定点数 | 禁 f64（跨平台/编译器非确定）。游戏引擎数值用 `i64 × 精度因子`。**Rhai 模组脚本同样禁用浮点**——所有模组参数必须声明为 `u32`/`i64`/`fixed<u32,N>` 定点类型，Rhai 引擎侧关闭浮点运算能力。 |
| 排序 | (shuffle_order, player_id, cmd_seq) | 相同种子 + 相同指令 → 相同顺序 |
| HashMap 顺序 | `indexmap` | 不用 std::HashMap（迭代顺序非确定） |

#### 回放保证

给定 tick N-1 状态 + tick N RawCommand + world_seed + world_config（世界规则快照）+ mods_lock（模组版本快照）→ 相同 Wasmtime pinned 版本下 `execute_deterministic == recorded_state`。每个 tick 产出 `state_checksum` 写入 TickTrace。CI 对随机采样 tick 做 full replay 验证——包括恢复对应 `world_config` 规则集 + checkout 到对应 `mods_lock` 记录的精确模组 commit。

---

## 9. World 模式 vs Arena 模式

Swarm 提供两种**并行核心玩法**——World 和 Arena 同等重要，面向不同玩家群体。引擎统一，规则可配置。

| 维度 | World（持久世界） | Arena（竞技场） |
|------|-----------------|-----------------------|
| **本质** | 有机世界，类似 Minecraft 服务器 | 竞技比赛，类似围棋对局 |
| **状态** | ✅ MVP 核心 | ✅ MVP 核心 |
| **地图** | 随机生成，不同玩家不同起点 | 对称初始条件，双方公平 |
| **加入时机** | 随时，先来后到不同 | 同时开始，代码在比赛前锁定 |
| **公平性** | 不追求——天然不对称 | 核心追求——对称起点 + 相同规则 |
| **运行方式** | 7x24 tick 循环 | 固定时长（例：5000 tick ~ 4h） |
| **代码** | 随时更新（热重载） | 比赛开始时锁定 |
| **排行榜** | 无意义——起点不同无法比较 | 有意义——赛季排名、锦标赛 |
| **回放** | 自身可见，隐私分级控制 | 赛后自动公开（replay_privacy = public） |
| **旁观** | public_spectate 控制，默认关闭 | 默认公开（public_spectate=true） |
| **玩家** | 人类和 AI agent 在同一世界共存 | 1v1 或团队对决 |
| **关注点** | 持久性、创造力、涌现玩法 | 策略深度、公平性、观赏性 |

### 9.1 Arena 匹配与排名系统

Arena 模式提供完整的竞技闭环：匹配 -> 对战 -> 结算 -> 回放。

#### 9.1.1 匹配队列

玩家发起匹配 -> 按 rating 区间 + 等待时间匹配配对 -> 准备阶段（30s 确认）-> 代码锁定 -> 比赛开始。

| 参数 | 默认值 | 说明 |
|------|--------|------|
| match_type | 1v1 | 1v1 / 2v2 / FFA(4人) |
| match_duration | 5000 tick | 比赛固定时长（约4h） |
| rating_window | +/-200 Elo | 初始匹配窗口 |
| window_expand_rate | +50/min | 每分钟扩大窗口 |
| max_wait_time | 300s | 超时后跨任意区间匹配 |

#### 9.1.2 排名系统 (Elo)

初始 Elo: 1200，K-factor: 32。胜：Elo += K x (1 - expected)；负：Elo -= K x expected；平：Elo += K x (0.5 - expected)。

赛季长度 1 个月，段位：Bronze/Silver/Gold/Platinum/Diamond。软重置：new_elo = 1200 + (old_elo - 1200) x 0.5。定级赛前 5 场 K=64。

**联赛分层**：

| 联赛 | 参与者 | 排名 |
|------|--------|------|
| Human | 人类编写 WASM | 计入主力排名 |
| AI-Assisted | 人类 + AI 协作 | 独立榜单 |
| AI Tournament | 纯 AI agent | 独立榜单 |

联赛之间不混合匹配。

#### 9.1.3 比赛流程

Lobby（匹配配对）-> Lock（代码锁定，30s 确认）-> Play（比赛中，引擎运行专用 Arena 实例，对称地图）-> Result（计算 Elo，更新排名）-> Replay（赛后自动公开回放，含完整 TickTrace + 双方视角）。

比赛终止条件（按优先级）：一方 drone=0 提前获胜 > 一方认输 > tick 到上限按剩余资产判定 > 平局。

#### 9.1.4 Arena 配置

```toml
[arena]
enabled = true
match_type = "1v1"
match_duration = 5000
tick_interval_ms = 300
initial_resources = { Energy = 10000, Crystal = 5000 }
map_symmetry = "rotational"

[arena.rating]
initial_elo = 1200
k_factor = 32
placement_matches = 5
placement_k_factor = 64
season_duration_days = 30
soft_reset_ratio = 0.5

[arena.spectator]
public_spectate = true
spectate_delay = 100
allow_chat = false
```

#### 9.1.5 回放与社区分享

赛后生成 Full Replay（TickTrace JSONL）+ Highlights（关键时刻摘要）。回放播放器支持速度控制、双视角切换、tick 定位、指令展开、性能叠加。社区分享：每场生成 share card（头像/段位/Elo变化 + 关键统计 + 二维码），支持一键分享。

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
