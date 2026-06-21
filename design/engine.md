# Engine 架构

> 引擎架构域文件。从 design/README.md 拆分。详细规范见 `specs/core/01-tick-protocol.md`。

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
| 5 | 1,500 | Extension (30), Terminal, Observer | 400 | 40/tick | 3 格 | 跨世界身份同步/日志交换 |
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
  │   ├── Phase 2b: ECS Systems
    │   │   └── > **权威系统调度见 [Complete Tick Execution Manifest](specs/core/06-phase2b-system-manifest.md)** — 31 systems（R30 B1：Phase 2a inline 6 + Phase 2b deferred 25），serial spine + 2 parallel sets
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
| **Phase 2a (Inline)** | 串行 inline 应用 | Move, Harvest, Attack, RangedAttack, Heal, Claim, Build, Recycle, Transfer, Withdraw, Spawn (validate only) | **玩家提交的命令**——效果依赖执行顺序，且「先到先得」竞争有意义。对 Bevy World 做立即修改，后续命令基于最新状态校验 |

**Move 作为 Main Action 的设计理由**：Move 与 Harvest/Attack/Build 竞争同一个 per-drone per-tick action slot。此设计偏离了大多数 RTS 的「移动 + 行动」双动作模型，是 Swarm 有意的简化和 philosophic commitment：

```
传统 RTS:  Move (free) + Action (attack/harvest/build)  → 每 tick 两个操作
Swarm:     Move = Action  → 每 tick 移动 OR 采集 OR 攻击 OR 建造
```

| 理由 | 说明 |
|------|------|
| **确定性优先** | 双动作模型引入 Move+Attack 的顺序竞争——`move_then_attack` vs `attack_then_move` 在不同排序下产生不同结果。单 action slot 消除了这类二义性 |
| **编程游戏本质** | Swarm 是**编程游戏**，不是微操 RTS。玩家编写策略，不是逐 tick 下指令。Move 占用 action slot 迫使玩家思考"这一 tick 我的 drone 应该移动到哪？"——而不是无脑移动+攻击 |
| **简化 Command 模型** | 单 action slot 使校验、排序、审计链路单一化——不存在 Move 和 Attack 的并发写入冲突 |
| **战术深度** | 玩家必须权衡：这 tick 是继续追击（Move）还是停下来打（Attack）？追击可能让对方跑掉，攻击可能打不中——这是有意义的战术决策 |
| **手感差异** | 新玩家会觉得 drone "迟钝"——移动一格后下一 tick 才能采集。这是**设计意图**：drone 不是即时代理，玩家需通过代码预判和批量调度来弥补单 drone 的动作延迟 |

此设计在 playtest 阶段可能被挑战——如果证据表明玩家普遍因 Move 占用 action slot 而流失，可重新评估。当前作为有意的设计选择冻结。
| **Phase 2b (Deferred)** | ECS Systems (serial spine + parallel sets) | death_marker, spawn, spawning_grace, regeneration, combat (parallel set A), special_attack_reducer, damage_application, status buffer production (parallel set B: S16-S22b), status_advance_system (S22 serial unique writer), aging, decay, death_cleanup, pvp_block, room_state, controller_2b, resource_ledger — **R30 B1: 31 systems** | **被动系统**——有依赖关系的系统串行执行（保证正确性），无数据竞争的系统利用并行调度。不接收玩家命令，响应 2a 产生的状态变化。完整调度见 [Complete Tick Execution Manifest](specs/core/06-phase2b-system-manifest.md) |

**Attack 与 combat_system 的职责分离（R33 B7）**：
- **Phase 2a Attack/RangedAttack/Heal 命令**：仅生成 `PendingDamage`/`PendingHeal` intent，**不直接修改目标 HP**。Phase 2a 校验基本合法性（body part 要求、cooldown、fatigue、target validity），但 damage/heal 的实际应用推迟到 Phase 2b。
- **Phase 2b combat_system（S11-S13）**：统一收集 Phase 2a 产生的 PendingDamage/PendingHeal 以及 Tower 自动攻击、持续伤害效果（DoT）→ S14 special_attack_reducer 归并 → S15 damage_application 统一写入 Entity.hits。
- 此分离保证「先到先得」竞争在 Phase 2a 校验层面生效（先通过校验的 Attack 先拿到 intent 优先级），但所有 HP 变更统一在 Phase 2b S15 确定——避免同 tick 内 Attack 顺序差异导致的不同 HP 结果。

**Recycle 死亡路径**：Recycle 命令走标准 death_mark → death_cleanup 路径（与其他死亡一致），不在 Phase 2a 中立即 despawn。death_mark 在 2b 开头标记待死亡 entity 并释放 room cap 槽位，death_cleanup 在 2b 末尾执行实际 despawn。

**Spawn 时序说明**：spawn_system 在 death_mark 之后（room cap 槽位已释放）运行，紧接着 `spawning_grace_system` 为新生 drone 附加 1 tick 的无敌帧，然后进入 combat/decay。新生 drone 获得 `SpawningGrace { remaining: 1 }` 组件——在本 tick 内免疫所有伤害（含特殊攻击和衰减），下一 tick 恢复正常参与战斗。此机制防止"出生即斩"——对手在 Spawn 旁部署 RangedAttack drone 无法秒杀新生 drone。

**RoomCap 生命周期约束**：`RoomCap` 的读写顺序为 `death_mark: W(release) → spawn: R(check) + W(consume)`。在 `death_mark_system` 与 `spawn_system` 之间的任何 ECS system 不得读取 RoomCap 做准入决策——此时槽位已释放但尚未被新 drone 消费，RoomCap 值处于中间态。新增 system 插入此区间时必须在 manifest 中声明对 RoomCap 的读写关系。

**Phase 2b 并行策略**：Combat (S11-S13) 按 target_id partition 并行——attack_system、ranged_attack_system、heal_system 操作不重叠的 target 实体。Status Buffer Production (S16-S22b) 按 status subtype 并行——各系统写入互不重叠的 typed buffer（HackBuffer/DrainBuffer/OverloadBuffer/DebilitateBuffer/DisruptBuffer/FortifyBuffer/LeechBuffer/FabricateBuffer），不直接修改 StatusState。status_advance_system (S22) 为串行唯一 StatusState writer——从 S14 读取 canonical sorted pending_intents 并从 S16-S22b 读取 typed buffers，统一推进所有 StatusState。decay (S24) 为独立串行系统（疲劳/冷却/结构衰减不与任何并行系统共享数据）。regeneration (S10) 在 damage_application (S15) 之前串行执行（防止 heal+regen 双倍回复）。完整调度及 R/W 矩阵见 [Complete Tick Execution Manifest](specs/core/06-phase2b-system-manifest.md)。

**两阶段快照架构**：阶段一不再为每个玩家独立序列化世界状态。改为：(1) tick 开始时一次性构建完整世界快照，按房间分片；(2) 每个玩家根据其 drone 所在位置，拼接可见房间的分片（默认 ≤9 个）。复杂度从 `O(玩家数 × 实体数)` 降为 `O(实体数 + 玩家数 × 可见房间数)`，消除每玩家重复序列化开销。快照构建在玩家 WASM 执行前完成，与玩家顺序无关，天然确定。

**WASM 预编译**：玩家上传 WASM 模块时，引擎在部署阶段立即编译为原生码并存储（非 tick 时 JIT）。tick 时只需实例化已编译模块，消除首次加载的编译延迟。编译后的模块按 `(module_hash, wasmtime_version)` 缓存，Wasmtime 版本升级时自动重编译。

### 3.3 确定性保证与回放

**确定性要求**：
1. 相同的初始世界状态
2. 相同的 Command 输入（已排序，canonical order 见 [interface.md §4](interface.md)）
3. ECS System 执行顺序固定（见 [Complete Tick Execution Manifest](specs/core/06-phase2b-system-manifest.md)，31 systems，R30 B1）
4. 所有随机数来自确定种子 PRNG——shuffle seed 公式 `Blake3("shuffle" || world_seed || tick.to_le_bytes())`；per-entity stream seed `Blake3(stream_name || world_seed || entity_id.to_le_bytes() || tick.to_le_bytes())`
5. **确定性数据结构**：`ResourceRegistry`、entity 迭代、player 列表等需要确定性键排序的场景使用 `BTreeMap`（标准库全序排列，跨平台一致迭代顺序）。`IndexMap` 保留用于有序资源类型等插入顺序确定的场景。禁止 `std::HashMap`（迭代顺序跨运行非确定）。

**回放输入封套**（`TickInputEnvelope`，每 tick 持久化）：
- `collect_id`（Blake3, R16 B3 新增）, `attempt_id`（u32, R16 B3 新增）, `commit_id`（Blake3, R16 B3 新增）
- `module_hash`, `wasmtime_version`, `effective_tick`
- `fuel_schedule_version`, `host_cost_table_version`（R32 B9 新增 — WASM fuel metering 版本对齐）
- `wasm_status`（ok/timeout/trap/fuel_exhausted）
- `snapshot_hash`, `commands_hash`（canonical order）
- `deploy_events`, `rollback_events`, `admin_events`
- `world_config_hash`, `mods_lock_hash`, `engine_abi_version`
- `terminal_state`（verified/audit_gap/unreplayable/reconstructable, R16 B3 新增）

**反作弊**：
- 全量回放：任意房间状态可完整重现
- 异常检测：玩家 tick 间的世界变化超过物理上限 → 标记
- WASM 编译时静态分析：扫描可疑系统调用

### 3.4 性能与容量合同

以下为 deadline-driven 硬性能合同——是实现必须满足的合约，全部指标在 CI 中回归测试。

#### 3.4.1 Tick Pipeline 预算

| 阶段 | World 预算 | Arena 预算 | 说明 |
|------|-----------|-----------|------|
| **Tick interval** | 3000ms | 300ms | 目标 tick 间隔 |
| **SNAPSHOT build** | ≤200ms (p95) | ≤50ms (p99) | 构建全量世界快照并按房间分片 |
| **COLLECT (sandbox dispatch)** | ≤2500ms | ≤200ms | 并行分发 WASM 执行，含 sandbox deadline |
| **EXECUTE (2a+2b)** | ≤400ms | ≤50ms | 命令应用 + ECS systems |
| **COMMIT (FDB)** | ≤50ms (p99) | ≤20ms (p99) | FDB 原子提交 |
| **BROADCAST** | ≤50ms | ≤10ms | Delta 广播 + 缓存更新 |
| **Per-player sandbox deadline** | 2500ms | 200ms | 超时 → deterministic no-op / timeout rejection，不拖延整个 tick |

#### 3.4.2 容量合同（单节点，World 模式）

| 指标 | 硬值 | 说明 |
|------|------|------|
| **Active players** | target 500 / hard cap 1000 | 活跃玩家数 |
| **Active drones** | target 5000 / hard cap 10000 | 活跃 drone 总数 |
| **Total entities** | hard cap 50000 | 含 drones、structures、NPC、resources |
| **Per-player drone cap** | 50 (per-room per-player baseline, world.toml configurable; R23 D2/B 三层 cap) | per-room / per-player / per-world 三层取较小值 |
| **Snapshot per-player (WASM)** | 256KB | tick() 输入；fog_of_war 过滤后的可见实体 |
| **Snapshot player display** | 分页传输 | 展示用，非 WASM 输入；不受 fog_of_war 限制 |
| **Commands per player per tick** | max 100 | 可配置拒绝策略 |
| **Pathfinding requests** | max 10 per player per tick | 超限 deterministic fail |
| **Pathfinding budget** | 100,000 explored nodes/tick | 引擎全局；per-player 按活跃玩家数 fair-share 分配 |
| **Pathfinding result path** | 500 nodes max | 返回路径最大长度；超长截断 |
| **FDB transaction** | 小事务（head/manifest/hash/pointer） | tick 内世界 head 推进；大 blob 进入对象存储 |
| **TickTrace/keyframe retention** | 7d (hot) / 30d (warm) / 180d (cold) | 可配置 |

> **B7 补充**：以下容量推导和准入公式为本节新增。

##### Aggregate CPU Admission Formula

每 tick 的总 WASM CPU 预算由 tick budget 和活跃玩家数共同决定：

```
aggregate_cpu_budget = floor(TICK_BUDGET_COLLECT_MS × CPU_CORES × PER_CORE_FUEL_RATE)
per_player_cpu_quota = floor(aggregate_cpu_budget / active_players)
effective_per_player_quota = min(per_player_cpu_quota, MAX_FUEL)
```

其中：
- `TICK_BUDGET_COLLECT_MS` = 2500ms（见 §3.4.1 COLLECT budget）
- `CPU_CORES` = 引擎可用 CPU 核心数（默认 `num_cpus::get()`）
- `PER_CORE_FUEL_RATE` = 每核每秒 wasmtime fuel units（保守估算 ~500M fuel/s per core，对应 wasmtime 默认 fuel 计量。详见 wasmtime `Store::fuel_consumed`）
- `MAX_FUEL` = 10,000,000 wasmtime fuel units（per-player hard cap）
- `fuel_schedule_version`：Wasmtime `FuelCostingSchedule` 版本标识符，与 `host_cost_table_version` 一起写入 TickCommitRecord。引擎启动时通过 `wasmtime::Config::consume_fuel(true)` 启用 fuel metering。host function cost 表版本随 engine ABI version 更新，确定性 replay 需匹配相同版本。

> **fuel 语义**：fuel 是 wasmtime fuel units（非 CPU instructions 或真实时间）。wasmtime 按指令权重累加 fuel，`fuel_consumed()` 返回消耗量。host function 调用有独立 cost（engine 侧 `add_fuel()`），总计入 per-tick quota。WASM 执行中 fuel 耗尽 → 立即 trap（`fuel_exhausted`），完整输出丢弃，不计 refund。fuel 计量在 WASM 实例边界内——不同 wasmtime 版本/配置的 fuel 消耗不可直接比较（需 `fuel_schedule_version` 对齐）。

**Admission 决策**：每个玩家 WASM 执行时，其 fuel budget = `min(effective_per_player_quota, player_reserved_fuel)`。若 `effective_per_player_quota < MIN_FUEL`（默认 500,000），引擎拒绝新玩家 WASM 执行（`ERR_CPU_SATURATED`），已入玩家不受影响。此机制防止 CPU 过载扩散到已连接的活跃玩家。

##### Worker Pool 推导

Sandbox worker pool 水平可扩展——每个 worker 独立执行一个玩家的 drone 算法，生成指令序列。指令序列在 Phase 2 sandbox 中确定性串行执行。

```text
Phase 1 (COLLECT): Worker Pool 并行 — 水平可扩展
  Worker₁ → Player₁.drone() → [cmd₁, cmd₂, ...]
  Worker₂ → Player₂.drone() → [cmd₃, cmd₄, ...]
  ...
  Workerₙ → Playerₙ.drone() → [cmdₙ, ...]
        ↓ (所有指令序列入队)
Phase 2 (EXECUTE): Sandbox 串行 — 确定性世界模拟
  for cmd in sorted(commands):  apply_to_world(cmd)
```

**Worker pool 配置**:

```
worker_pool_size = min(worker_pool_max, active_players)
worker_pool_size = clamp(worker_pool_size, 0, worker_pool_hard_cap)

其中:
  worker_pool_max = 256（运行期默认，见 game_api.idl.yaml §limits.worker_pool）
  worker_pool_hard_cap = 1000（编译期硬上限，见 game_api.idl.yaml §limits.worker_pool）
  active_players = 当前活跃玩家数（有 WASM 模块部署 + 至少 1 个存活 drone）
```

Worker pool 水平可扩展——运营商根据 active_players 调整 worker_pool_max 即可消除排队。空闲 worker 保留 5min 后回收。新玩家连接时若 pool 未满且 active_players < worker_pool_max，fork 新 worker（若池中有空闲则复用）。

**Per-player sandbox deadline**: 2500ms（World）/ 200ms（Arena）= 单个玩家 drone 算法的最大执行时间。超时后该玩家本 tick 输出 0 command + `TimeoutExceeded`。此 deadline 独立于 worker pool 大小——每个 worker 上的玩家独立计时。

**500/1000 player 容量的真正瓶颈**: 不在 worker pool（可水平扩展），而在 (a) Phase 2 sandbox 串行执行时间，(b) Per-player WASM 平均执行时间 × 并行度。详见 §3.4.1 Tick Pipeline 预算与下方容量推导。

##### 500/1000 Player Capacity Derivation

**Target 500 活跃玩家推导**（单节点垂直扩展）：

```
输入假设:
  - Tick interval = 3000ms
  - Collect budget = 2500ms
  - Per-player WASM execution p50 = 5ms, p99 = 15ms
  - Snapshot build per player = ~0.5ms (shared snapshot, per-player view stitching)
  - Execute phase = 400ms

500 players × 5ms avg = 2500ms ← 等于 Collect budget
  → 500 players at p50 execution time fully saturates Collect phase
  → p99 players (15ms) cause排队，增大 tick 风险
  → 500 = target（安全操作点，有余量处理 p99 延迟）
```

**Hard cap 1000 活跃玩家推导**：

```
1000 players × 5ms avg = 5000ms > Collect budget (2500ms)
  → 依赖并行 worker pool 分摊
  → 假设 1000 workers，p50=5ms，理论 peak = 5000ms 但并行化为 ~125ms wall-clock（1000 × 5ms / 40 cores）
  → 实际操作: snapshot stitching + dispatch overhead ≈ 500ms
  → 总 wall-clock: 125ms (WASM 执行) + 500ms (overhead) = 625ms
  → 余量: 2500ms - 625ms = 1875ms
  → 每玩家可用 CPU 预算 = 1875ms × 40 / 1000 ≈ 75ms aggregate（实际 fuel 分配见 Aggregate CPU Admission Formula）
  → 1000 = hard cap（引擎在此负载下仍可保证 tick 完成，但 per-player fuel 极度受限）
```

**超过 hard cap**: 新 WASM 部署被拒绝（`ERR_WORLD_FULL`），已部署但非活跃（无存活 drone）的玩家不计入 `active_players`。玩家可排队等待 slot 释放（drone 死亡、玩家登出）。

**Per-player fair-share admission**: 引擎全局预算（如 pathfinding 100,000 explored nodes/tick）按活跃玩家数均分。每玩家份额 = `floor(global_budget / active_players)`。若 active_players 为 0，不执行分配。玩家超出其份额 → 当前调用 deterministic reject（路径返回部分结果或 `ERR_BUDGET_EXHAUSTED`）。引擎在 tick 开始时计算份额，整个 tick 内份额不变。份额按调用顺序消耗——先到先得，后续超份额即拒。此机制防止单玩家垄断全局寻路资源，保证公平性。

> **权威容量定义**：所有容量上限和准入策略以 `specs/reference/api-registry.md` §5「全局容量限制」为准。engine.md 本节仅作性能合同（budget），数值引用自 registry 的权威列。

**Arena 独立预算**：Arena 使用独立的 tick/collect/simulate budget，不继承 World 的 3s 模型。Arena pathfinding 和 visibility 缓存大小减半（5,000 / 25,000）。

#### 3.4.3 Sandbox 生命周期

WASM 实例使用 **long-lived worker pool + per-tick clean Store/Instance reset**：

- **Pool**：大小按 `min(MAX_POOL, active_players)` 动态伸缩（见 §3.4.2 Worker Pool 推导）；空闲实例 5min 后回收
- **Per-tick reset**：memory 清零、fuel 重置、WASI 全部关闭后重新按需开启
- **WASI 默认全部关闭**，仅开启确定性子集（由 engine 编译期固定）
- **禁用的 WASI**：clock、random、filesystem、network、env、process、threads、atomics、SIMD（默认禁用；允许 opt-in deterministic integer subset，需跨架构验证。R30: SIMD deterministic subset deferred — non-blocking）
- **Worker 边界**：每个 worker 有独立 uid/cgroup；seccomp profile 限制 syscall；OOM score adj；rlimit（nproc、nofile、memlock）
- **Recycle 策略**：每 worker 最多服务 1000 tick 后强制替换；OOM/trap/timeout 后立即替换并记入 audit log
- **Wasmtime version 固定**：编译期锁定，升级后重编译所有缓存模块

#### 3.4.4 WASM Snapshot Truncation

WASM tick() 输入 snapshot 受 per-player 256KB cap 约束：

| 状态 | 语义 | 处理 |
|------|------|------|
| **正常** | snapshot ≤ cap | 完整传入 |
| **Truncated** | snapshot > cap | 按确定性截断顺序（距离桶 → entity_id 字典序，从最远桶末尾移除）截断；`snapshot.truncated=true`；暴露 `omitted_counts` 和 bucket 统计。**权威截断合同见 [Snapshot Contract](specs/core/09-snapshot-contract.md) §1** |
| **Rejected** | 保护性拒绝（如 OOM 攻击） | 返回 deterministic empty input + `over_budget_rejected` 错误码 |

**截断顺序**: 距离桶 0(self) > 1(adjacent) > 2(near) > 3(mid) > 4(far) > 5(very far) > 6(out of sight)，同桶内 entity_id 字典序。关键实体（自身/Controller/target/己方 drone/攻击者）不可截断。详见 Snapshot Contract §1.3–1.4。

截断不依赖 ECS query 原始顺序——使用 stable `entity_id` sort 保证确定性 replay。给玩家的展示层 snapshot 走分页传输，不在 WASM cap 约束内。

**Anti-abuse**：可见实体造成的 snapshot 压力纳入 room/entity cap、density tax 和 attacker cost 策略。敌对方可通过堆叠实体增加受害方 snapshot 压力——此行为不被禁止，但 snapshot truncation 不会因此泄露更多信息。

**WASM 输出截断**：WASM `tick()` 输出上限 256KB。超出时整批丢弃（不保留前缀，不执行已解析指令）。产出 `output_truncated` 拒绝原因，写入 TickCommitRecord，通过 snapshot/status 通知玩家。详见 [Tick Protocol §9.7](../specs/core/01-tick-protocol.md#97-wasm-output-截断)。

#### 3.4.5 Controller 维修公式

Controller repair 降低 drone age。公式使用定点整数（basis points, × 10000）：

```
age_reduction = min(repair_per_drone, drone.age)
total_reduction = Σ age_reduction per drone serviced (up to repair_capacity)
```

**维修距离**：Controller RCL1=1 格，RCL8=5 格。相邻格只有 6 个——大量 drone 排队形成物流拥挤。

> **设计决策 (D7)**：移除全局 repair cap。维修仅受物理约束限制——(a) `repair_range`（RCL1=1 格 → RCL8=5 格），(b) `repair_capacity` 每 Controller 每 tick 可服务 drone 数，以及 (c) drone 物理分布（必须移动到 Controller 邻域才能被维修）。这些约束已足够防止维修被滥用，无需人工全局 cap。

#### 3.4.6 Phase 2b DeathMark 读写语义

`death_mark_system` 在 Phase 2b 开头标记待死亡 entity 并释放 room cap 槽位。在其之后的 `regeneration_system` 和 `decay_system` 必须跳过 `DeathMark` 标记的 entity——两者的所有读写操作在查询时过滤 `Without<DeathMark>`。`death_cleanup_system` 在 2b 末尾执行实际 despawn。

#### 3.4.7 FDB 写入策略

- FDB 存 head/manifest/hash/pointer——小事务推进 world head
- 大型 RichTraceBlob/keyframe 进入对象存储或 append-only log
- 每 K=100 tick 写入一次 keyframe，其余 tick 写入 delta
- 每日写入预算：按 target load 估算（非 16MB/tick 全量写入）
- `state_checksum`：覆盖 WorldState + mod_state/action_log + tick_metrics + config hash + manifest pointer

#### 3.4.8 数值溢出与舍入

所有资源/年龄/伤害/进度使用 `u64` 或 `i64` 定点整数。overflow 行为：
- 资源加减：saturating（不得超过 `u64::MAX`，不得低于 0）
- 乘除：中间结果使用 `u128` 或 checked math
- 舍入：一律 floor（向下取整）
- 比例计算：`amount * basis_points / 10000`（basis points 精度）

---

