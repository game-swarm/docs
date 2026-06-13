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

// Resource——掉落资源（动态资源类型）
struct Resource {
    amounts: HashMap<String, u32>,    // { "Energy": 500, "Matter": 200 }
}

// Source——可再生资源点
struct Source {
    produces: HashMap<String, u32>,   // { "Energy": 1 } 或 { "Energy": 1, "Matter": 1 }
    capacity: u32,
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
  ├── 玩家顺序种子洗牌（seed = hash(tick_number, world_seed)）
  ├── 对每条指令（按洗牌后顺序 + 玩家内 sequence 排序）:
  │   ├── 对照当前世界状态校验
  │   ├── 合法 → 通过 ECS system 应用变更
  │   ├── 资源竞争 → 先到先得（先执行者优先）
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

## 8. World Rules Engine — 可配置的游戏规则

Swarm 不是「一个游戏」，而是「一个可配置的游戏引擎平台」。每个世界实例可以有不同的规则集。

### 8.1 核心理念

Screeps 的问题是**规则硬编码**——出生点逻辑、代码更新成本、drone 控制权限都是引擎的一部分，社区服主无法修改。Swarm 把这些做成**世界级配置 + ECS Plugin**。

```
世界配置 (WorldConfig)          ECS Plugin (System 注入)
┌─────────────────────┐        ┌──────────────────────┐
│ spawn_policy         │        │ SpawnPolicySystem    │
│ code_update_cost     │   →    │ CodeUpdateCostSystem │
│ code_propagation     │        │ PropagationSystem    │
│ manual_control       │        │ ManualControlSystem  │
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
| `spawn_policy` | enum | `RandomRoom`（默认）\| `ManualSelect`（玩家选坐标）\| `FixedSpawn`（固定出生点）\| `Inherit`（从已有殖民地出生） |
| `spawn_cooldown` | u32 | 新玩家加入后多少 tick 才能开始操作（默认 0） |
| `respawn_policy` | enum | 殖民地全灭后的处理：`NewRoom` \| `SameRoom` \| `Spectate` \| `Ban` |

#### 代码部署

| 规则 | 类型 | 说明 |
|------|------|------|
| `code_update_cost` | ResourceCost | 部署新 WASM 消耗的资源（默认 `{Energy: 0}` — 免费） |
| `code_update_cooldown` | u32 | 两次部署间的最小 tick 间隔（默认 0） |
| `code_update_window` | (u32, u32) | 部署窗口期：每 N tick 开放 M tick（默认无限制） |
| `code_propagation_speed` | u32 | 代码更新传播速度：0=全局即时，>0=每 tick 传播 N 格 |
| `code_propagation_source` | enum | 传播源：`Spawn`（从出生点传播）\| `Controller`（从控制器传播）\| `AnyDrone` |

#### Drone 控制

| 规则 | 类型 | 说明 |
|------|------|------|
| `env_vars` | bool | 是否允许给 drone 设置环境变量（`drone.set("role", "harvester")`） |
| `memory_size` | u32 | 每 drone 最大环境变量存储（bytes，默认 1024） |
| `memory_spawn_cost` | `{String: f64}` | 每 byte 内存的孵化成本（默认 `{}` = 免费） |
| `memory_upkeep_cost` | `{String: f64}` | 每 byte 内存的每 tick 维护费（默认 `{}` = 免费） |

**手动控制不开放**：manual_control 与「代码就是军队」的核心哲学冲突，已删除。唯一例外是 Tutorial 专用世界中的受限引导操作——但 Tutorial 世界独立运行，不与正式世界互通。

#### 资源与经济

| 规则 | 类型 | 说明 |
|------|------|------|
| `source_regeneration_rate` | f64 | 资源点再生速率倍率（默认 1.0） |
| `build_cost_multiplier` | f64 | 建筑成本倍率（默认 1.0） |
| `drone_decay_rate` | f64 | drone 衰减倍率（默认 1.0） |

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
| `transfer_to_global_time` | u32 | 1 | 转换所需的 tick 数（0=即时） |
| `transfer_from_global_cost` | ResourceCost | `{Energy: 0.05}` | 全局→本地每单位资源的转换成本（默认 5%） |

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

每类资源的定义：

```toml
[[resource_types]]
name = "Crystal"              # 资源名（标识符）
display_name = "水晶矿"        # 显示名
category = "mineral"          # mineral | gas | organic | energy
starting_amount = 0           # 新玩家初始拥有量
max_storage = 100000          # 单玩家最大储量
decay_rate = 0.001            # 每 tick 衰减比例（0 = 不衰减）
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

#### 战斗与 PvP

| 规则 | 类型 | 说明 |
|------|------|------|
| `pvp_enabled` | bool | 是否允许 PvP（默认 true） |
| `friendly_fire` | bool | 是否允许攻击同阵营（默认 false） |
| `damage_multiplier` | f64 | 伤害倍率（默认 1.0） |

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
memory_spawn_cost = { Energy = 0.5 }     # 每 byte 孵化成本
memory_upkeep_cost = { Energy = 0.01 }   # 每 byte 每 tick 维护费

[resources]
source_regeneration = 1.0
build_cost = 1.0
drone_decay = 1.0

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
[actions.costs]
spawn = { Energy = 200, Matter = 50 }
build.Extension = { Energy = 50 }
build.Tower = { Energy = 100, Matter = 25 }
body_part.Move = { Energy = 50 }
body_part.Work = { Energy = 100 }
body_part.Attack = { Energy = 80, Matter = 20 }
body_part.Heal = { Energy = 250, Matter = 100 }
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
pvp = true
friendly_fire = false
damage = 1.0
```

### 8.4 ECS 集成方式

每个规则类别对应一个可选的 ECS System。引擎启动时读取 `world.toml`，有选择地注册 System：

```rust
// engine 启动时
fn register_rule_systems(app: &mut App, config: &WorldConfig) {
    // 基础系统始终注册
    app.add_systems(Update, (movement_system, harvest_system, /* ... */).chain());

    // 注入资源注册表——所有 System 通过它查询资源类型和消耗
    let resource_registry = ResourceRegistry::from_config(&config);
    app.insert_resource(resource_registry);

    // 规则系统按配置注册
    if config.code.propagation_speed > 0 {
        app.add_systems(Update, code_propagation_system.before(movement_system));
    }
    if config.drone.memory_upkeep_cost.len() > 0 {
        app.add_systems(Update, memory_upkeep_system.before(decay_system));
    }
    // ...
}

// ResourceRegistry 是运行时的资源类型字典
struct ResourceRegistry {
    types: HashMap<String, ResourceDef>,
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
    amounts: HashMap<String, u32>,  // { "Energy": 500, "Matter": 200 }
}
struct ResourceDef {
    name: String,
    display_name: String,
    category: ResourceCategory,
    starting_amount: u32,
    max_storage: u32,
    decay_rate: f64,
    tradeable: bool,
}
```

### 8.5 WASM 侧感知

玩家的 WASM 代码通过 host function 读取当前世界的资源类型和动作消耗：

```typescript
// TypeScript SDK
const registry = Game.world.resources();

// 查看世界中定义了哪些资源
for (const [name, def] of registry.types) {
    console.log(`${name} (${def.display_name}): max ${def.max_storage}`);
}

// 查询动作消耗
const spawnCost = registry.cost("spawn");
// → { Energy: 200, Matter: 50 }

const towerCost = registry.cost("build", "Tower");
// → { Energy: 100, Matter: 25 }

// 检查能否支付
if (player.resources.has(spawnCost)) {
    player.spawn(body);
}

// 采集时指定资源类型
drone.harvest(source, "Matter");  // 采集物质
drone.transfer(target, { Energy: 100, Matter: 50 });

// 自适应——同一份 WASM 在任何资源体系的世界中都能运行
```

### 8.6 World 与 Arena 的默认规则

| 规则 | World 默认值 | Arena 默认值 |
|------|------------|------------|
| `spawn_policy` | `RandomRoom` | `FixedSpawn`（对称） |
| `code_update_cost` | 0（免费） | 0 |
| `code_update_window` | 无限制 | 赛前锁定 |
| `code_propagation_speed` | 0（即时） | 0（即时） |
| `manual_control` | false | false |
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
room_superlinear = { type = "f64", default = 0.1, min = 0.0, max = 10.0, description = "超线性系数" }
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
        let room_penalty = rooms * (config.room_base +
            rooms as f64 * config.room_superlinear) as u32;

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
// 状态查询
state.players()          → Iterator<Player>
state.tick()             → u64
player.drones()          → Iterator<Drone>
player.rooms()           → Iterator<Room>
player.resources()       → Map<String, u64>
drone.body_parts()       → Vec<BodyPart>
drone.position()         → (x, y, room_id)

// 世界修改（通过 actions，不进命令管线）
actions.deduct_resource(player_id, resource, amount)
actions.award_resource(player_id, resource, amount)
actions.modify_entity(entity_id, property, value)
actions.emit_event(event_type, data)
actions.log_info(message)
actions.log_warn(message)

// 不可用：文件 IO、网络、时钟、随机数（确定性要求）
```

所有 `actions` 操作被记录到 TickTrace——可回放、可审计。

#### 安装与配置

```bash
# 从模组市场安装
swarm mod install empire-upkeep

# 查看模组的可配置项
swarm mod config empire-upkeep

# 设置参数
swarm mod config empire-upkeep drone_cost 5
swarm mod config empire-upkeep onshortfall "damage"

# 在世界中启用
swarm world add-mod empire-upkeep
```

世界配置中引用：

```toml
# world.toml
[world]
name = "Survival World"

[[mods]]
name = "empire-upkeep"
version = "1.2.0"
[mods.config]
drone_cost = 5
room_superlinear = 0.2
onshortfall = "damage"

[[mods]]
name = "resource-decay"
version = "0.3.0"
[mods.config]
decay_rate = 0.001
```

#### 引擎集成

```rust
fn register_mod_systems(app: &mut App, world_config: &WorldConfig) {
    for mod_def in &world_config.mods {
        let mut module = load_mod(&mod_def.name, &mod_def.version);
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
        }.after(death_system));
    }
}
```

#### 模组市场

```
swarm-mods.kagurazakalan.com

  模组              评分    安装量    描述
  ─────────────────────────────────────────────────
  empire-upkeep     ★4.8   1,234     帝国规模维护费
  fog-of-war        ★4.6   892       战争迷雾
  resource-decay    ★4.3   567       资源腐败衰减
  territory-control ★4.5   445       连续领土要求
  alliance-system   ★4.7   678       玩家间结盟
  mutation          ★4.2   234       drone 进化变异
```

模组是源码——服主可以 fork、修改、提交 PR。社区 review + rating。

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
type = "f64"
default = 0.1
min = 0.0
max = 10.0
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
        "room_superlinear": { "value": 0.2, "type": "f64",
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
巨帝国（50 房, 2000 drone）: 维护费 ≈ 12600/tick — 软天花板

不是硬上限——是「你能支撑多大就有多大」。
想维持巨帝国？你的 drone 物流必须极致优化。
```

### 8.8 Determinism Contract — 确定性合同

#### 固定算法

| 组件 | 算法 | 说明 |
|------|------|------|
| PRNG | **ChaCha12** | 密码学安全 + 确定种子。不用 std::random / OS 熵源。 |
| Hash | **Blake3** | 固定实现。不用 std::hash / SipHash（跨版本可变）。 |
| 种子洗牌 | Blake3(tick_number \|\| world_seed) | 每 tick 确定但不可预测的玩家顺序 |
| ECS 顺序 | `.chain()` | 严格串行。未来用 `.before()/.after()` 部分并行 |
| 数值 | 整数 + 定点数 | 禁 f64（跨平台/编译器非确定）。用 i64 × 精度因子。 |
| 排序 | (shuffle_order, player_id, cmd_seq) | 相同种子 + 相同指令 → 相同顺序 |
| HashMap 顺序 | `indexmap` | 不用 std::HashMap（迭代顺序非确定） |

#### 回放保证

给定 tick N-1 状态 + tick N RawCommand + world_seed + 激活模组列表 → 相同 Wasmtime pinned 版本下 `execute_deterministic == recorded_state`。每个 tick 产出 `state_checksum` 写入 TickTrace。CI 对随机采样 tick 做 full replay 验证。

---

## 9. 路线图

### Phase 0: 架构冻结（Architecture Freeze）— 当前

- [ ] Game API IDL 冻结（host functions + Command + Validator + SDK ABI + MCP schema 同源）
- [ ] Command Source Model 冻结（WASM gameplay / MCP deploy+query / admin / replay / test）
- [ ] Determinism Contract 冻结（PRNG=ChaCha12, hash=Blake3, 禁 f64/禁 std::hash, ECS order）
- [ ] Tick Protocol 拉齐（FDB commit in EXECUTE, tick abandon behavior, NATS ack）
- [ ] World Rules Engine capability model 收敛为 Rhai 模组

### Phase 1: 核心引擎（MVP — 单人垂直切片）

- [ ] Bevy ECS 世界模拟（地形、资源、基础单位）
- [ ] WASM 沙箱 + process pool prototype（fork vs pool 性能数据）
- [ ] 基础游戏 API（move, harvest, build, spawn）
- [ ] MCP server 脚手架（swarm_get_snapshot, swarm_deploy, swarm_get_world_rules）
- [ ] 本地 docker-compose 开发环境
- [ ] TypeScript SDK + Rust SDK（基础 API）
- [ ] Deterministic replay hash 验证（sampling + checksum CI）

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
- [ ] Arena 模式（1v1 比赛制）+ 排行榜（分 league）+ 赛季

### Phase 7: 生产化

- [ ] 性能优化（sharding, ECS 并行化）
- [ ] 反作弊系统
- [ ] AI 锦标赛编排
- [ ] 自动化测试框架
- [ ] CI/CD Pipeline

---

## 10. World 模式 vs Arena 模式

| 维度 | World（持久世界） | Arena（比赛） |
|------|-----------------|-------------|
| **本质** | 有机世界，类似 Minecraft 服务器 | 竞技比赛，类似围棋对局 |
| **地图** | 随机生成，不同玩家不同起点 | 对称初始条件，双方公平 |
| **加入时机** | 随时，先来后到不同 | 同时开始，代码在比赛前锁定 |
| **公平性** | 不追求——天然不对称 | 核心追求——对称起点 + 相同规则 |
| **运行方式** | 7×24 tick 循环 | 固定时长（例：5000 tick ≈ 4h） |
| **代码** | 随时更新（热重载） | 比赛开始时锁定 |
| **排行榜** | 无意义——起点不同无法比较 | 有意义——赛季排名、锦标赛 |
| **回放** | 自身可见，可选分享 | 赛后自动公开 |
| **玩家** | 人类和 AI agent 在同一世界共存 | 1v1 或团队对决 |
| **关注点** | 持久性、创造力、涌现玩法 | 策略深度、公平性、观赏性 |

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
