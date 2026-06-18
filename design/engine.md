# Engine 架构

> 详见 DESIGN §3。本文档是从 DESIGN.md 拆分出的引擎架构域文件。

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
| **Phase 2b (Deferred)** | ECS Systems `.chain()` + `.before()/.after()` | death_mark, spawn, spawning_grace, combat, status_advance, aging（主线 `.chain()`）；regeneration, decay（并行，仅需 before death_cleanup） | **被动系统**——对有依赖关系的系统串行执行（保证正确性），无数据竞争的系统利用 Bevy 并行调度。不接收玩家命令，响应 2a 产生的状态变化 |

**Attack 与 combat_system 的职责分离**：
- **Phase 2a Attack/RangedAttack 命令**：直接应用 damage（含抗性/伤害类型计算），立即反映到目标 HP
- **Phase 2b combat_system**：仅处理非玩家命令的战斗——Tower 自动攻击、持续伤害效果（DoT）、叠加状态结算
- 此分离保证「先到先得」竞争在 Attack 上生效，同时 Tower/DoT 统一在 2b 末尾结算

**Recycle 死亡路径**：Recycle 命令走标准 death_mark → death_cleanup 路径（与其他死亡一致），不在 Phase 2a 中立即 despawn。death_mark 在 2b 开头标记待死亡 entity 并释放 room cap 槽位，death_cleanup 在 2b 末尾执行实际 despawn。

**Spawn 时序说明**：spawn_system 在 death_mark 之后（room cap 槽位已释放）运行，紧接着 `spawning_grace_system` 为新生 drone 附加 1 tick 的无敌帧，然后进入 combat/decay。新生 drone 获得 `SpawningGrace { remaining: 1 }` 组件——在本 tick 内免疫所有伤害（含特殊攻击和衰减），下一 tick 恢复正常参与战斗。此机制防止"出生即斩"——对手在 Spawn 旁部署 RangedAttack drone 无法秒杀新生 drone。

**RoomCap 生命周期约束**：`RoomCap` 的读写顺序为 `death_mark: W(release) → spawn: R(check) + W(consume)`。在 `death_mark_system` 与 `spawn_system` 之间的任何 ECS system 不得读取 RoomCap 做准入决策——此时槽位已释放但尚未被新 drone 消费，RoomCap 值处于中间态。新增 system 插入此区间时必须在 manifest 中声明对 RoomCap 的读写关系。

**Phase 2b 并行策略**：regeneration（资源点再生）和 decay（疲劳/冷却递减）只操作各自独立的数据，与主线 death_mark→spawn→spawning_grace→combat→status_advance→aging→death_cleanup 无数据竞争。利用 Bevy 的 `.before()/.after()` 将这两个系统与主线并行调度——Bevy 在幕后自动分配线程，无需手动管理。约束：两者必须在 `death_cleanup` 之前完成（防止操作已 despawn 的 entity），其他无顺序要求。正确性由数据独立 + Bevy 依赖图保证，确定性不依赖并行度（同 input 同 output）。

**两阶段快照架构**：阶段一不再为每个玩家独立序列化世界状态。改为：(1) tick 开始时一次性构建完整世界快照，按房间分片；(2) 每个玩家根据其 drone 所在位置，拼接可见房间的分片（默认 ≤9 个）。复杂度从 `O(玩家数 × 实体数)` 降为 `O(实体数 + 玩家数 × 可见房间数)`，消除每玩家重复序列化开销。快照构建在玩家 WASM 执行前完成，与玩家顺序无关，天然确定。

**快照扩展路线（三级规模模型）**：

| 规模 | 目标 | 快照策略 | Snapshot 预算 | 状态 |
|------|------|---------|:--:|:--:|
| **Tier 1 — MVP** | 50 players × 10 drones = 500 total，≤50 房间，单节点 | Bevy World 深拷贝全量快照 | ≤16MB / tick，≤50ms 构建 | 当前设计目标，specs/core/01 已覆盖 |
| **Tier 2 — 中等规模** | ≤5,000 drone，≤500 房间，单节点 | 增量快照 + modification-set tracking + copy-on-write 实体分页 | ≤64MB / tick，≤200ms 构建 | 需补充完整 spec（增量差异协议、CoW 实体页大小、modification-set 合并策略、truncation 在增量模式下的语义） |
| **Tier 3 — 大规模** | >5,000 drone，多节点 | 按房间分片 + 跨节点 snapshot 路由 + 跨分片 combat 协议 | 每分片 ≤64MB / tick | 需补充完整 spec（分片键设计、跨分片实体引用、分布式 combat 结算、FDB 多区域部署） |

Tier 2 和 Tier 3 的完整 spec 必须在 Phase 1 实现前完成——不得作为远期声明模糊处理。Tier 1 的深拷贝全量快照仅在 MVP 阶段有效；Tier 2 的增量快照 spec 必须定义从 Tier 1 深拷贝的迁移路径。

#### Tier Entry Gate 矩阵

以下矩阵明确每个 Tier 冻结什么、延后什么，防止 MVP 实现被未来扩展污染：

| 能力 | Tier 1 (MVP) | Tier 2 | Tier 3 |
|:--|:--:|:--:|:--:|
| **Core IDL**（Move/Harvest/Build/Attack/Heal/Spawn/Recycle/Transfer/Withdraw/ClaimController） | ✅ 冻结 | — | — |
| **6 种特殊攻击**（Hack/Drain/Overload/Debilitate/Disrupt/Fortify） | ✅ 冻结（Standard+ 可用，Tutorial/Novice 禁用） | — | — |
| **Leech / Fabricate** | ❌ Tier 2+（通过 `[[custom_actions]]` 注册） | ✅ 冻结 | — |
| **8 种 body part**（Move/Work/Carry/Attack/RangedAttack/Heal/Claim/Tough） | ✅ 冻结 | — | — |
| **Vanilla Ruleset 默认值** | ✅ 冻结 | world.toml 可覆盖 | — |
| **Dynamic CommandAction**（world.toml `[[custom_actions]]` 注册新 action） | ❌ future-disabled | ✅ | — |
| **Rhai custom handler**（`actions.add_body_part_type` 等动态注册） | ❌ future-disabled | ✅ | — |
| **World-specific SDK artifact**（ABI hash + dynamic manifest） | ❌ future-disabled | ✅ | — |
| **全量 Bevy 快照** | ✅ 冻结（≤16MB/tick） | — | — |
| **增量快照 + modification-set** | ❌ | ✅ 冻结 | — |
| **按房间分片** | ❌ | ❌ | ✅ 冻结 |
| **跨分片 combat** | ❌ | ❌ | ✅ 冻结 |
| **FDB 多区域部署** | ❌ | ❌ | ✅ 冻结 |
| **Gateway 无状态水平扩展** | ✅ | — | — |
| **Admin rollback** | ⚠️ gated（需双人审计） | — | — |
| **WASM sandbox worker pool** | ✅（每玩家独立进程） | — | — |

**规则**：
- Tier 1 的 `future-disabled` 项在引擎编译期通过 feature flag 排除——不在二进制中
- Tier 2/3 启用对应 feature flag 后，相关 spec 必须已冻结
- 跨 Tier 的文档引用（如 specs/future/）不阻塞 Tier 1 实现

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

