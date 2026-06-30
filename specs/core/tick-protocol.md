# Tick 协议规范

> 详见 design/engine.md

## 1. 世界拓扑

### 1.1 房间模型

世界由离散的房间网格构成。每个房间为正方形网格，边长可配置（默认 50×50 格）。坐标系：世界中心为 (0,0)，X 轴向东为正，Y 轴向北为正。

```text
        Y+
        ▲
        │  (-1,1)  (0,1)  (1,1)
        │  (-1,0)  (0,0)  (1,0)
        │  (-1,-1) (0,-1) (1,-1)
        └──────────────► X+
```

### 1.2 出口

相邻房间通过出口连接，支持 N/S/E/W 四个方向。出口位于房间边缘，drone 移动到出口所在格即可穿越。

- 每个房间至少 1 个出口（防止孤岛）
- 相邻房间的出口互相配对：(0,0) 东出口 ↔ (1,0) 西出口
- 出口位置由世界种子确定性生成，沿墙壁边缘分布
- 跨房间移动成本 = 房间内路径 + 穿越出口 cost（默认 +1 fatigue）

### 1.3 房间状态

每个房间处于以下状态之一，由 Controller 决定：

```
neutral ──Claim──→ reserved ──RCL 1──→ owned ←──→ contested
   ▲                                     │              │
   │        (RCL=1 时失去 owner)          │    owner 失去 │
   └─────────── abandoned ←───────────────┘              │
                 │  (RCL>1 时降级)                        │
                 └───────────────────────────────────────┘
```

| 状态 | 触发 | 行为 |
|------|------|------|
| `neutral` | 初始状态 | 任意玩家可 Claim |
| `reserved` | Claim 后 progress < RCL 1 | 独占，超时后回退 neutral |
| `owned` | RCL ≥ 1 | 完整控制权（建造、升级、采集） |
| `contested` | 两玩家同时 Claim | 净 progress 归零方失去资格 |
| `abandoned` | owner 失去超过 downgrade_timer | RCL=1→neutral，RCL>1→降一级 |

### 1.4 Tick 状态机

```
                 ┌──────────────────────────────────┐
                 │         空闲等待                   │
                 │        tick_counter = N           │
                 └──────────┬───────────────────────┘
                            │ 到达 tick_interval
                            ▼
                 ┌──────────────────────────────────┐
                 │     阶段一：收集 (COLLECT)          │
                 │  超时: 2500ms                     │
                 │  ┌─────────────────────────┐     │
                 │  │ 对每个活跃玩家:           │     │
                 │  │ 1. 构建可见性快照          │     │
                 │  │ 2. 调用 PlayerExecutor    │     │
                 │  │ 3. 超时 → 空指令列表      │     │
                 │  └─────────────────────────┘     │
                 │  结果: Map<PlayerId, Vec<Cmd>>   │
                 └──────────┬───────────────────────┘
                            │
                            ▼
                 ┌──────────────────────────────────┐
                 │     阶段二：执行 (EXECUTE)          │
                 │  EXECUTE 在 COLLECT+EXECUTE        │
                 │  总预算下运行，不独立超时            │
                 │  (World ≤400ms、Arena ≤50ms        │
                 │   仅为性能目标，非硬超时)            │
                 │  ┌─────────────────────────┐     │
                 │  │ Phase 2a: 排序命令循环      │     │
                 │  │ for cmd in sorted(         │     │
                 │  │   global_queue,            │     │
                 │  │   key=command.sort_key):   │     │
                 │  │   match cmd.kind:          │     │
                 │  │   Move/Harvest/...→[S01]    │     │
                 │  │   Action→action_dispatch    │     │
                 │  │   (per-command handler,     │     │
                 │  │   非 manifest system)       │     │
                 │  │   Claim→[S02] ...          │     │
                 │  │ 逐条校验+逐条应用            │     │
                 │  │ (基于当前 Bevy World)      │     │
                 │  │ Action→PendingDamage/Heal  │     │
                 │  │ intent 不直接改 HP         │     │
                 │  │ Spawn → 校验+扣费+写入     │     │
                 │  │ PendingEntityCreation      │     │
                 │  └─────────────────────────┘     │
                 │  ┌─────────────────────────┐     │
                 │  │ Phase 2b: ECS Systems     │     │
                 │  │ death_mark → spawn →     │     │
                 │  │ spawning_grace → regen → │     │
                 │  │ combat → spec_atk_red →  │     │
                 │  │ dmg_apply → status →     │     │
                 │  │ aging → decay →          │     │
                 │  │ death_cleanup            │     │
                 │  └─────────────────────────┘     │
                 │  redb 原子提交（全或无,权威源）   │
                 └──────────┬───────────────────────┘
                            │
                            ▼
                 ┌──────────────────────────────────┐
                 │    阶段三：广播 (BROADCAST)         │
                 │  ┌─────────────────────────┐     │
                 │  │ 1. 计算实体增量            │     │
                 │  │ 2. Moka Cache + NATS      │     │
                 │  │    (并行 fan-out)         │     │
                 │  └─────────────────────────┘     │
                 └──────────┬───────────────────────┘
                            │ tick_counter = N + 1
                            ▼
                       空闲等待
```

## 2. 阶段一：收集

### 2.1 玩家执行模型

唯一执行器：**WasmSandboxExecutor**。所有玩家的 drone 都通过 WASM 沙箱执行——无论是人类编写还是 AI agent 编写。没有 McpPlayerExecutor。

| 输入来源 | 编译者 | 部署渠道 |
|---------|--------|---------|
| 人类编写代码 | 人类通过 Web UI / CLI 编译 | Web 上传 / `swarm deploy` CLI |
| AI agent 编写代码 | AI 通过自身工具链编译 | MCP `swarm_deploy` |

引擎只关心：「有 WASM 模块了吗？」——不问是谁写的。

### 2.2 收集超时

```
collect_timeout_ms = 2500  // 硬截止时间

在 t + 2500ms 时刻:
  对每个未响应的玩家:
    commands[player] = []   // 宽容失败: 本 tick 无指令
    metrics.collect_timeouts += 1
```

**原则**: 某个玩家卡住不会阻塞整个世界。超时玩家当 tick 指令输出丢弃——不跨 tick 携带（防止 sequence 冲突与跨 tick 重排）。

### 2.3 快照构建

```rust
fn build_world_snapshot(tick) -> WorldSnapshot:
    let world_copy = deep_copy_bevy_world();
    let room_shards = shard_by_room(world_copy);          // O(rooms)，可并行
    let room_payloads = serialize_room_shards(room_shards); // 每房间一次
    return WorldSnapshot { tick, room_payloads };

fn stitch_player_snapshot(world_snapshot, player_id) -> Snapshot:
    let visible_rooms = visibility_rooms(world_snapshot, player_id);
    let visible_entities = filter_visible_entities(visible_rooms, player_id);
    let payload = apply_snapshot_contract_truncation(visible_entities, 256_000);
    return Snapshot {
        tick: world_snapshot.tick,
        player_id,
        entities: payload.entities,      // 仅该玩家可见，≤256KB
        terrain: payload.terrain,        // 可见地形格
        resources: payload.resources,    // 玩家自身资源
        snapshot_len: payload.serialized_size,
        truncated: payload.truncated,
        omitted_count: payload.omitted_count,
    };
```

- 快照按房间分片序列化一次，再为玩家 stitch 可见 shard——不是对 `all_entities` 做 per-player 全量过滤。
- 超限时的截断策略见 [Snapshot Contract §4](../core/snapshot-contract.md) —— **snapshot-contract 是 snapshot truncation 的唯一权威源**。tick-protocol 不定义独立截断算法，只引用该权威源。
  - 截断算法（距离桶 + entity_id 字典序 + farthest-first + critical 不可截断）全部由 snapshot-contract 定义。
  - `truncated=true` 时 WASM 模块收到标记，应降级策略。
  - `host_get_objects_in_range` 返回格式见 snapshot-contract。

**滥用检测**：以下模式在引擎侧自动检测并标记：
| 滥用模式 | 检测方法 | 响应 |
|---------|---------|------|
| 实体膨胀攻击 | 玩家可见实体数连续 5 tick 超过 `MAX_VISIBLE_ENTITIES`（500） | 标记玩家 `visibility_abuse`，降低其 COMBAT 优先级 |
| 出口视野扩展 | 单 tick 内可见房间数 > 9（默认 ≤9） | 截断到 9 房间，记录审计日志 |
| 截断频率异常 | 连续 3 tick `truncated=true` | 告警；该玩家 `snapshot_quota -= 10%` |
| path_find 路径膨胀 | 单 tick `path_find` cache_miss > 50 | 该 tick 后续 path_find 返回空路径 |

**快照构建时序边界**：

```
tick N 时间线:
  COLLECT 开始
    ├── [1] 构建完整世界快照（Bevy World 深拷贝）      ← 一次性，O(entities)
    ├── [2] 按房间分片快照                             ← 并行，O(rooms)
    ├── [3] 对每个玩家：视野过滤 + 截断                  ← 并行，O(players × visible_entities)
    ├── [4] WASM tick(snapshot) 执行                   ← 并行，O(players)，此阶段快照只读
    ├── [5] MCP query（swarm_get_snapshot）            ← 读取同一快照（步骤 1 构建的副本）
    │                                                ← MCP query 与 WASM tick 看到的是同一份快照
  COLLECT 完成
  EXECUTE（修改 Bevy World）
  redb commit（快照仅用于回滚，不持久化）
```

关键不变量：
- 步骤 [4] WASM tick() 和步骤 [5] MCP query 基于**同一份**快照——`snapshot_tick == current_tick`
- 快照在 COLLECT 阶段构建一次，COLLECT 期间不变（redb commit 失败回滚时使用同一快照恢复）
- MCP query 不能观察到 EXECUTE 阶段的中间状态——只能看到 COLLECT 开始时的世界快照

### 2.4 WASM 模块部署

AI 玩家通过 MCP `swarm_deploy` 上传 WASM 模块。Deploy 是控制面 mutation，不进入 gameplay RawCommand queue，不参与 Phase 2a 指令排序。服务端在 redb deploy manifest 中记录 `activation_tick >= current_tick + 1`，引擎只在 COLLECT 开始前切换到已到达 activation_tick 的模块：
```
Tick N: 引擎用 WASM 模块 v1 执行玩家代码
Tick N: AI 调用 swarm_deploy，上传 v2
Tick N+1: 引擎自动切换到 v2
```

代码部署不影响当前 tick 执行——当前 tick 使用已加载的模块。切换是原子的。

### 2.5 新玩家加入与重生

**首次加入**：新玩家进入世界时，系统分配出生房间。分配策略：

1. **密度优先**：计算各候选区域（以 spawn 点为中心 3×3 房间）的活跃玩家密度，选择密度最低的区域
2. **避免包围**：拒绝将新玩家分配到四周均为敌对玩家已占领房间的区域
3. **safe_mode 保护**：新玩家首次 spawn 后自动获得 safe_mode，持续 `world.toml` 中配置的时长（默认 500 tick），期间其他玩家无法在该房间执行任何敌对操作

```toml
[spawn]
safe_mode_duration = 500       # 新玩家保护期（tick），0 = 禁用
respawn_policy = "NewRoom"     # NewRoom | OriginalRoom
```

**重生**：玩家殖民地全灭后，按 `respawn_policy` 重生：
- `NewRoom`：在密度最低的区域重新分配（默认）
- `OriginalRoom`：回到首次出生的房间

## 3. 阶段二：执行

### 3.1 指令排序（确定性 + 公平）

**问题**：如果排序 key 是 `(tick_number, player_id, ...)  `，同一个玩家每次都在同一位置——不公平且可被利用。

**方案：种子洗牌 (Seeded Shuffle)**

```rust
// 每 tick 洗牌一次，用 Blake3 XOF 从 seed + tick 派生确定性随机序列
// seed = Blake3(tick_number || world_seed)
// shuffle = Blake3 XOF: for i in 0..N:  position[i] = XOF.read_u64() % (N - i)
let seed = blake3::hash(&[&tick_number.to_le_bytes(), &world_seed]);
let player_order: Vec<PlayerId> = seeded_shuffle(&active_players, &seed);

// 按洗牌后的玩家顺序 + 玩家内部指令序号排序
for (order_index, player_id) in player_order.iter().enumerate() {
    let mut player_commands = collected_commands.remove(player_id).unwrap_or_default();
    player_commands.sort_by_key(|c| c.sequence);
    for cmd in player_commands {
        global_queue.push((order_index, player_id, cmd.sequence, cmd));
    }
}
```

**属性**：
- 确定性：相同 `(tick_number, world_seed, 相同指令集)` → 相同顺序 → 相同世界状态
- 公平性：每个 tick 玩家顺序随机轮换，长期期望均等
- 不可预测：玩家无法提前知道自己在当前 tick 的排序位置
- **PlayerId canonical sort**：`seeded_shuffle` 内部先按 `PlayerId` 字节序（lexicographic）排序 → 再对排序后的有序列表执行 Fisher-Yates shuffle（Blake3 XOF 驱动）——保证 shuffle 输入顺序确定性。shuffle 使用 rejection sampling 消除模偏差（`XOF.read_u64() % (N - i)` 当 `N - i` 不整除 2^64 时丢弃超出范围的采样值重试），确保每个排列概率均等。

**种子轮换**：`world_seed` 定期轮换，防止长期观察推断种子空间。轮换周期通过 `world.toml` 配置：

```toml
[world]
seed_rotation_interval = 10000   # 每 N tick 轮换一次（默认 10000）
```

轮换算法：`new_seed = Blake3(old_seed || current_tick)`。旧种子对应的回放数据仍可验证——TickCommitRecord 中记录每 tick 使用的 seed epoch，回放时按 epoch 选择对应种子。

**种子生命周期与泄露防护（R27 T-H1 — 混合方案）**：

> **根本约束**：在确定性系统中，未来状态（包括种子）可从当前状态推导——真正的密码学前向保密不可能。泄露了当前种子 + 状态的攻击者能模拟全部未来 tick。种子归档在快照/keyframe 中已足够用于确定性 replay。

**方案：Arena 用 Commit-Reveal，World 用 Operator Seed-Bump**。

#### Arena：Commit-Reveal（赛中不可见，赛后审计）

Arena 模式有明确时间边界（start tick → end tick），适合 commit-reveal：

```
Arena 赛前:
  seed_epoch_0 = 服务端通过安全随机源生成（非 Blake3 链推导）
  seed_commitment = Blake3(seed_epoch_0 || "commit")
  → seed_commitment 写入 arena 公开元数据，seed_epoch_0 仅引擎内存

Arena 赛中（tick 0 → match_end）:
  所有 RNG 使用 seed_epoch_0 派生
  快照记录 seed_epoch（按 epoch 粒度，非每 tick）
  MCP/API 只暴露 seed_commitment——玩家无法获取实际 seed

Arena 赛后（match_end_tick + 100）:
  seed_epoch_0 自动公开写入 TickCommitRecord
  任何玩家/审计方可验证：Blake3(seed_epoch_0 || "commit") == seed_commitment
  → 证明赛中随机性未被服主篡改
```

#### World：Operator Seed-Bump + Statistical Detection

World 模式无时间边界，commit-reveal 不适用。依靠运维止损：

```
正常轮换：new_seed = Blake3(old_seed || current_tick)（保持现有）

泄露检测（Statistical Detection）：
  每 1000 tick 汇总以下指标：
  - per-player win-rate deviation（排序优势检测）：连续 5+ 次预测命中 → FLAG
  - combat RNG advantage：伤害浮动 all_high / all_low 分布异常 → FLAG
  - spawn position clustering：新生房间密度异常 → FLAG
  触发 FLAG → WARN 日志 + 服主通知（Mattermost/webhook）

种子归档（Replay 可用）：
  每 epoch（10000 tick）的 seed 记录在 keyframe snapshot 中
  快照包含：(seed_epoch_id, seed, epoch_start_tick, epoch_end_tick)
  CI replay 从快照读取 seed → 不需要外部 seed archive

Operator Seed-Bump MCP 工具：
  swarm_world_seed_bump { world_id, reason }
    → 生成全新 seed（来自安全随机源，非 Blake3 链）
    → seed_epoch_id += 1
    → 旧 seed 标记为 compromised（审计日志记录 bump reason）
    → 未来 tick 使用新 seed 派生
    → 可选：从泄露前 keyframe 回滚（服主决策）
```

**Seed 生命周期统一模型**：

| 阶段 | Arena | World |
|------|-------|-------|
| 生成 | 安全随机源（外部熵） | Blake3 链（old → new） |
| 赛中/运行时 | seed hash 公开，seed 仅引擎 | seed 仅引擎 |
| 披露 | 赛后 +100 tick 自动公开 | **不公开**（运维保护） |
| 归档 | 快照/keyframe 中记录 seed epoch | 快照/keyframe 中记录 seed epoch |
| 泄露响应 | 赛后自动审计（seed hash 校验） | Operator seed-bump + 回滚 |

**泄露应急 runbook**（World）：

1. 检测：统计异常检测触发 FLAG → 服主通知
2. 确认：检查 world_seed 访问日志 → 确认泄露时间点
3. 止损：`swarm world seed-bump <world> --reason "seed_leak_detected_at_tick_<N>"`
4. 回滚：从泄露点前的 keyframe 恢复世界状态（可选——取决于竞技公平要求）
5. 公告：通知受影响玩家，提供补偿（如资源补偿、赛季重置）

### 3.2 资源竞争 (Resource Contention)

**场景**：两个玩家的 drone 在同一 tick 试图采集同一个 Source。

**规则：按排序顺序依次执行，先到先得。**

```
Source E1: energy = 5

排序后指令队列:
  1. Player B: harvest(E1) → 拿走 5，E1 剩余 0
  2. Player A: harvest(E1) → 校验时发现 E1.energy = 0
     → RejectionReason: InsufficientResource
     → debug_detail: "SourceEmpty"
     → 记录到 TickCommitRecord
```

**应用范围**：
| 竞争类型 | 处理方式 |
|---------|---------|
| 采集同一 Source | 先到先得，耗尽后 `InsufficientResource` + debug_detail `SourceEmpty` |
| 建造同一坐标 | 先到先得，坐标被占后 `PositionOccupied` |
| 攻击同一目标 | 全部执行——多个攻击者可以打同一目标 |
| 治疗同一目标 | 按顺序加血，满血后 `NotEligible` + debug_detail `AlreadyFullHealth` |
| 传输资源到同一目标 | 顺序填充，容量满后 `InsufficientResource` + debug_detail `TargetFull` |

**设计意图**：
- 先到先得简单、确定、可解释
- 种子洗牌保证了「先到」的公平性——长期来看每个玩家都有同等概率先到
- 创造了策略深度：要不要多个 drone 采集同一个源？万一排在后面就浪费指令
- 不采用比例分配（太复杂且失去竞争性），不采用价高者得（需要市场机制，超出入门复杂度）

### 3.3 指令执行模型（Inline + Phase 2a TOCTOU 合同）

命令循环采用 **Inline 模型**：逐条校验 + 逐条应用，校验基于**当前** Bevy World 状态（非快照）。

**Phase 2a TOCTOU 保护合同**：

以下规则防止 inline 执行中的时间窗口攻击——所有规则在 `validate_and_apply()` 单一路径中强制执行：

1. **Spawn pending 不可见**：Phase 2a 中 Spawn 命令校验 + 扣费 + 写入 `PendingEntityCreation`。S08 在 tick 末尾 flush 创建实体并预分配/记录 `StableEntityId`，但新实体不加入本 tick 可见/可交互世界索引。同 tick 后续命令无法看到、操作、或依赖尚未创建的 drone。新实体从下一 tick 开始参与快照、命令校验和系统迭代；`SpawningGrace { remaining: 1 }` 在首次可交互 tick 生效。
2. **Hack 状态下的所有权**：Hack 施加控制锁后，原 owner 的后续 friendly/attack/recycle 命令仍以**原始 owner** 身份校验（Hack 不立即转移所有权）。5 tick 后实际夺取时 handler 切换 owner。
3. **Per-drone per-tick action quota**：每 drone 每 tick 最多执行 1 个 main action（Move/Attack/Harvest/Build/Heal 及其特殊攻击变体）。Transfer/Withdraw 不计入此配额但受 carry 容量约束。此限制防止 Transfer chain resource amplification。
4. **fuel/wall-clock 耗尽**：WASM 执行中 fuel 耗尽或 wall-clock timeout → 完整输出丢弃（不读取部分输出），不计 refund。
5. **指令队列不跨 tick**：超时玩家的指令输出仅丢弃当前 tick，不携带到下个 tick（防止 sequence 冲突与状态污染）。

非法指令 → 拒绝，记录 RejectionReason，写入 TickCommitRecord。

### 3.4 ECS 系统执行顺序

> **权威调度见 [Complete Tick Execution Manifest](phase2b-system-manifest.md)** — 31 systems（R30 B1：Phase 2a inline 6 + Phase 2b deferred 25），serial spine + 2 parallel sets。Phase 2a inline 处理器在命令循环中逐条 inline 应用。Phase 2b 被动系统按 manifest 定义的 serial spine 顺序执行：death_marker → spawn → spawning_grace → regeneration → combat (parallel set A) → special_attack_reducer → damage_application → status buffer production (parallel set B) → status_advance_system (serial unique writer) → aging → decay → death_cleanup → pvp_block → room_state → controller_2b → resource_ledger。

**关键时序合同**：
- `death_marker` 在 `spawn` 之前：RoomCap 槽位同 tick 释放。
- `spawn_system` flush `PendingEntityCreation`，但新实体最早下一 tick 可交互。
- `spawning_grace` 在 combat 之前：`SpawningGrace { remaining: 1 }` 只在新实体首次可交互 tick 生效。
- `regeneration` 在 `damage_application` 之前：自然回复先于伤害结算，防止 heal+regen 双倍回复。
- `special_attack_reducer`：parallel intent 收集 → pending_intents buffer → canonical priority sort → 交付 status_advance_system。

**Component R/W 矩阵**：见 [Complete Tick Execution Manifest §4](phase2b-system-manifest.md) — 覆盖全部 31 systems 的读写关系、并行安全证明及 RoomCap 中间态保护。

### 3.5 Tick 原子性 — Shadow Write + Atomic Publish

#### 3.5.1 架构概述

生产环境使用 **shadow write + atomic publish** 模型保证 tick 原子性——将世界按房间分片写入 redb staging 区，仅通过 GlobalTickCommit 一次性发布。整个 tick 是**全局原子**的：staging 写入失败不产生已持久化的中间状态，GlobalTickCommit 是唯一的提交点。

**单事务模式仅用于开发/测试 profile**（≤ 50 active players, ≤ 100 rooms），生产环境强制 room-partition。room-partition 不影响游戏语义——GlobalTickCommit 失败则整个 tick 放弃 + Bevy snapshot 恢复。不存在部分房间已提交、部分未提交的中间态，不存在 best-effort 游戏状态降级路径。

**关键区别 vs 旧模型**：
- **旧（已删除）**：每房间独立 redb WriteTransaction 提交 + 全局回滚。声称「room-partition 仅是写入分片策略，不产生 per-room 独立 commit 语义」，但实现上仍依赖 per-room commit hash → 全局 manifest——存在「per-room 写入已持久化、全局 abort」的时序窗口。
- **新（Shadow Write）**：Per-room 写入只到 content-addressed staging 行（如 `/staging/{namespace_epoch}/{content_hash}`）——**staging 行不是已发布状态**，且可在 GlobalTickCommit 失败后由 GC 回收。GlobalTickCommit 是 manifest-only publish 点：仅写入全局 head、房间 hash 列表、manifest/hash-chain 与 staging namespace epoch pointer。所有下游读取（replay、Moka Cache、MCP query）先读取全局 manifest，再按 manifest 指向的 room hash 读取内容——未被 manifest 引用的 staging 数据对外不可见。

#### 3.5.2 Shadow Write 流程

```
Phase 2b 完成后:

  1. 对每个活跃房间：独立 redb WriteTransaction 写入 content-addressed staging 键空间
     ├─ content = canonical_room_payload(state_delta, events)
     ├─ room_hash = Blake3(content)
     ├─ Key: /staging/{namespace_epoch}/{room_hash} → content
     └─ room_txn.commit() → per_room_staging_hash = room_hash
     
     注意：staging commit 成功 ≠ 游戏状态已持久化。
     Staging 行仅当前 tick 的 GlobalTickCommit 可读取——其他路径看不到。

  2. 收集所有 per_room_staging_hashes → Vec<(RoomId, Blake3)>

  3. 处理跨房间意图（cross_room_intent_set，见 §3.5.4）

  4. GlobalTickCommit（唯一 publish 点 — redb 原子事务，manifest-only）:
     ├─ 写入 /committed/head/{tick}             → global tick head
     ├─ 写入 /committed/manifest/{tick}          → room hash list + cross-room intent log
     ├─ 写入 /committed/hash_chain/{tick}        → hash chain 续接
     ├─ 写入 /committed/staging_epoch/{tick}     → namespace_epoch pointer
     └─ 成功 → tick 完成，tick_counter 递增
       失败 → tick 放弃，Bevy snapshot 恢复（staging 行由 GC 清理）

  **关键不变量**：
  - Staging 写入失败 → 不影响已持久化状态——tick 放弃，Bevy snapshot 恢复。
  - GlobalTickCommit 失败 → tick 放弃，staging 行孤立（GC 清理），Bevy snapshot 恢复。
  - 不存在「已持久化但未发布」的游戏状态——只有 `/committed/manifest/{tick}` 引用的 content-addressed rows 属于完整 tick。
  - GlobalTickCommit 不提升/复制 per-room rows；它只发布 room hash list 与 staging namespace epoch pointer，因此无 per-room promotion TOCTOU 窗口。
```

#### 3.5.3 Staging 行 GC

```
Staging GC 策略:

  - GlobalTickCommit 成功 → manifest 引用的 content-addressed rows 成为该 tick 的权威 room payload；未引用 rows 由 GC 清理。
  - GlobalTickCommit 失败 → staging 行成为孤立数据。
    GC worker（每 10s 扫描）:
      └─ 读取 /committed/manifest/{tick} 与 active namespace epochs：未被 manifest 引用且 epoch 过期的 `/staging/{namespace_epoch}/**` 可清理。
  - Staging 行最大存活时间 = 1 tick interval + GC interval（< 15s 保证）。
  - 无累积风险——单次 GlobalTickCommit 失败至多产生 O(rooms × 2KB) 的 staging 孤立数据。
```

#### 3.5.4 跨房间意图 (Cross-Room Intents)

**定义**：涉及两个或以上房间的操作（资源传输、drone 穿越出口等）。

**协议**：
- **Canonical Log**：所有跨房间 intent 写入确定性顺序的规范日志
- **Deterministic Coordinator**：引擎侧单协调器按确定性规则裁决
- **All-or-Reject**：跨房间操作全部成功或全部拒绝——**不允许部分提交**

```
处理流程:
  1. 先在 Bevy World 内裁决所有跨房间操作：对 cross_room_intent_set 按确定性顺序（room_id source 升序）逐一 resolve，应用跨房间状态变更到 Bevy World
  2. 裁决完成后，对每个 affected room 以最终 Bevy World 状态写入 staging payload
  3. 所有跨房间 intent 的最终结果体现在 GlobalTickCommit 的 manifest 中——成功或 rejecting，无 partial
  4. 超时处理 (timeout_ms = 3000):
     └─ 超时 → tick abandon + global snapshot restore（全局原子模型——任何未完成 cross-room intent 均触发 tick 放弃）

**关键变更（D6 裁决）**：
- 跨房间操作在 staging 写入**前**于 Bevy World 内裁决——不再依赖 staging 写入完成后的 post-hoc 合并。
- 裁决后的世界状态直接写入 room staging payload——无需 overlay 合并路径。
```

#### 3.5.5 GlobalTickCommit 结构

```rust
struct GlobalTickCommit {
    tick: u64,
    staging_namespace_epoch: u64,                     // 本 tick staging namespace
    room_hashes: Vec<(RoomId, Blake3)>,                // manifest-only room content hash list
    cross_room_intent_set: Vec<CrossRoomIntent>,       // 跨房间操作集
    global_resource_ledger_hash: Blake3,                // 全局资源账本 hash
    manifest_hash: Blake3,                              // 全局 manifest hash
}
```

#### 3.5.6 TickInputEnvelope 与 TickCommitRecord 边界

Tick replay 分三层记录，字段不得混用：

| 层 | 内容 | replay 作用 |
|----|------|-------------|
| `TickCommitRecord` replay-critical core | commands、rejections、fuel、deploy_activation_decision、canonical_codec_version、snapshot_hash、commands_hash、state_checksum、manifest_hash、world_config_hash | redb 同一事务原子提交；确定性 replay 的最小必需集合 |
| Replay identity | collect_id、attempt_id、commit_id、api_version、engine_abi_version、world_action_manifest_hash、seed_epoch | 识别一次 collect/commit 尝试与世界规则版本；用于审计和 hash-chain |
| `TickInputEnvelope` | module_hash、wasmtime_version、effective_tick、fuel_schedule_version、host_cost_table_version、wasm_status、deploy_events、rollback_events、admin_events、terminal_state | 记录 COLLECT 输入与运行环境；对象存储 rich trace 缺失时仍可由 redb core replay |

Deterministic replay 只依赖 redb replay-critical core + keyframe/delta chain，不依赖 Blob Store/RichTraceBlob。Rich debug replay 可读取 RichTraceBlob 补充 per-system metrics、debug detail 和可视化 annotation；RichTraceBlob 缺失只产生 `terminal_state = audit_gap`，不产生 `unreplayable`。

#### 3.5.6 错误恢复

| 失败场景 | 处理 | 说明 |
|---------|------|------|
| 单房间 staging 写入失败 | tick 放弃，全局 snapshot 恢复 | staging 行不是已提交状态——无回滚需求（已写入的 staging 由 GC 清理） |
| Cross-room intent 任一失败 | tick 放弃，全局 snapshot 恢复 | 跨房间操作无法 partial publish |
| GlobalTickCommit 失败 | tick 放弃，全局 snapshot 恢复 | 唯一 publish 点失败 = tick 未发生 |
| Cross-room intent timeout | tick 放弃，全局 snapshot 恢复 | 全局原子模型——未完成 cross-room intent = 本 tick 游戏状态不完整 |

**与旧模型的区别**：
- ❌ 旧：「单房间写入失败 → tick 放弃，全局快照恢复」（暗示 per-room 写入已 durable → 需要全局回滚）
- ✅ 新：「单房间 staging 写入失败 → tick 放弃，staging 行由 GC 清理」（staging 行从未 durable——无需回滚，仅需 forward abandon + GC）

#### Bevy World 快照范围清单

快照在 Phase 2a 开始前完成，捕获完整的 World 状态。以下为必须捕获的 Resource 类型和所有 ECS Component 类型：

**必须捕获的 Resource 类型**：

| Resource | 说明 |
|----------|------|
| `TickCounter` | 当前 tick 编号 |
| `WorldSeed` | 世界随机种子 |
| `PlayerOrder` | 本 tick 洗牌后的玩家顺序 |
| `ResourceRegistry` | 全局资源注册表 |
| `WorldConfig` | 世界配置（房间尺寸、限制参数等） |
| `RNGState` | 随机数生成器状态（Blake3 XOF 内部状态） |
| `TimeResource` | tick 间隔、超时配置等 |

**必须捕获的 ECS Component 类型**：所有实体上挂载的 Component 均在快照范围内，包括但不限于：

| Component 类别 | 示例 |
|---------------|------|
| `Transform` (位置) | `RoomPosition`, `GridCoord` |
| `Owner` (所有权) | `PlayerId` |
| `Body` (身体部件) | `BodyPart` 及各个 part 组件 (`MovePart`, `WorkPart`, `CarryPart`, `AttackPart`, `RangedAttackPart`, `HealPart`, `ClaimPart`, `ToughPart`) |
| `Resource` (资源) | `Carry`, `Energy`, `ResourceStore` |
| `Health` (生命) | `HitPoints`, `MaxHitPoints` |
| `Combat` (战斗) | `Damage`, `HealAmount`, `DamageType` |
| `Status` (状态) | `Fatigue`, `Cooldown`, `HackControlLock`, `Debilitated`, `Fortified`, `Spawning` |
| `Room` (房间) | `RoomId`, `RoomController` |
| `Structure` (建筑) | `Spawn`, `Extension`, `Controller`, `Tower`, `Storage` |
| `Terrain` (地形) | `TerrainType`, `Walkable` |
| `Visibility` (可见性) | `VisibleTo`, `FogOfWarState` |
| `Metadata` (元数据) | `EntityId`, `SpawnTick`, `Lifespan` |

**快照生命周期**：
```
Phase 2a 开始前: snapshot = world.snapshot()  // 深拷贝 Bevy World
Phase 2a-2b:      在 world 上原地修改
redb commit 成功:  丢弃 snapshot
redb commit 失败:  world.restore(snapshot)      // 恢复所有 Component + Resource
```
`world.restore(snapshot)` 将 Bevy World 完全回滚至 Phase 2a 前的状态，包括所有实体的 Component 数据、所有 Resource 数据。

#### COLLECT 结果跨重试缓存

redb commit 失败触发重试时，**复用 canonical COLLECT buffer**（相同的命令序列 + fuel 扣费 + snapshot_hash + wasm_status），不重新执行 WASM：

- COLLECT 阶段的结果（`Map<PlayerId, Vec<ValidatedCommand>>` + 各玩家的 fuel 扣费明细）在首次 COLLECT 后缓存，产生 `collect_id = Blake3(tick || snapshot_hash || commands_hash)`
- 重试跳过 COLLECT 阶段，直接进入 EXECUTE 阶段，使用缓存的命令列表。`collect_id` 保持不变，`attempt_id` 递增。
- 跨重试 fuel 消耗上限 = `1 × MAX_FUEL`（首次 COLLECT 时的扣费即为最终扣费，重试不追加）
- 若连续 3 次 redb commit 失败后 tick 放弃，已扣除的 fuel 退还玩家
- redb commit 成功后产生 `commit_id = Blake3(collect_id || attempt_id || state_checksum)`

#### redb 故障注入 CI 测试

CI 管线中增加确定性故障注入测试，验证快照恢复的一致性：

```rust
#[test]
fn fdb_commit_failure_restores_snapshot_consistency() {
    // 1. 构建初始 World 状态
    let mut world = World::new(test_world_config());
    let snapshot_checksum_before = world.state_checksum();

    // 2. 注入 redb commit 失败（随机 tick 触发）
    fault_injection::set_mode(FaultMode::RandomCommitFailure {
        probability: 0.1,  // 10% 的 tick 触发 commit 失败
        seed: 42,           // 确定性种子
    });

    // 3. 执行 N 个 tick
    for tick in 0..1000 {
        let snapshot = world.snapshot();  // Phase 2a 前快照
        let collected = collect_commands(&world, tick);
        let commit_result = execute_and_commit(&mut world, collected, tick);

        if commit_result.is_err() {
            world.restore(snapshot);
            // 验证恢复后状态与快照一致
            assert_eq!(world.state_checksum(), snapshot_checksum_before,
                "tick {}: state_checksum mismatch after snapshot restore", tick);
        }

        // 若 commit 成功，更新基准 checksum
        if commit_result.is_ok() {
            snapshot_checksum_before = world.state_checksum();
        }
    }
}
```

**CI 中的随机故障注入策略**：
- 每个 CI run 随机选取 5% 的 tick 触发 redb commit 失败
- 验证断言：`state_checksum == snapshot_checksum`（恢复后状态与快照完全一致）
- 额外验证：`entity_count == snapshot_entity_count`（实体数量一致）
- 额外验证：所有 Resource 值与快照值逐项匹配
- 失败时输出完整 diff（哪个 Component/Resource 不一致）

## 4. 阶段三：广播

### 4.1 增量计算

```
delta = compute_delta(world_state_before, world_state_after)
// delta 仅包含本 tick 变更的实体
```

### 4.2 持久化 → 缓存 + 发布（并行 fan-out）

```
1. Read committed tick result from in-memory post-commit state or redb tick head
2. Post-commit delta fan-out:
   Engine Moka Cache.update(delta)
   NATS.publish("tick.{tick}", delta) → Gateway/WebSocket subscribers
```

**设计理由**：Engine 进程内 Moka Cache 与 NATS 无网络级数据依赖——缓存刷新是本地内存写入，实时推送通过 NATS/Gateway 独立演化。任一失败均不 rollback committed tick。

**BROADCAST failure never rolls back committed tick**——tick 已在 EXECUTE 阶段持久化到 redb。BROADCAST 阶段的任何失败（Moka cache miss、NATS 断开、部分客户端未收到）都不影响世界状态。客户端通过 `last_tick` 字段检测 gap → 主动 fetch。

## 5. Tick 健康指标

| 指标 | 阈值 | 动作 |
|------|------|------|
| `collect_timeout_rate` | > 10% 玩家 | 告警：太多慢执行器 |
| `tick_abandon_rate` | > 0 | 严重：redb 提交失败 |
| `tick_duration_p99` | > 2800ms | 警告：接近 3s 目标 |
| `command_rejection_rate` | > 20% 每玩家 | 标记玩家审查 |

## 6. Tick Failure Semantics — 失败语义

### 6.1 失败模式矩阵

| 失败点 | 触发条件 | 对本 tick 影响 | 对玩家影响 | 恢复策略 |
|--------|---------|--------------|-----------|---------|
| **COLLECT crash** | Bevy World 读取时 panic/OOM | tick 放弃，state 不变 | 该 tick 不执行，不退 fuel | 立即重试；连续 3 tick 引擎降级 |
| **Phase 2a panic/OOM** | inline apply 中 panic 或内存耗尽 | Bevy snapshot 恢复，tick 放弃 | 已消耗 fuel 不退，已执行玩家空 tick | 重试 3 次（复用 COLLECT 缓存）；失败降级 |
| **WASM timeout** | 玩家 tick() 超过 collect_timeout_ms (2500ms) | 该玩家 0 指令，其他玩家正常 | 空 tick，不退 fuel | 下 tick 正常执行 |
| **WASM crash** | 玩家 WASM 崩溃/panic/OOM | 同上 | 空 tick，不退 fuel。连续 3 tick crash → 玩家标记 degraded | 自动恢复，degraded 需人工解除 |
| **WASM output invalid** | tick 输出不符合 JSON schema | 该玩家所有指令丢弃 | 空 tick，不退 fuel | 下 tick 正常（需玩家修复代码） |
| **redb commit fail** | redb 事务冲突/网络错误 | tick 放弃，Bevy snapshot 恢复 | CPU fuel 退还 | 重试 3 次，失败等 1s 重试同 tick。连续 3 次 → 引擎降级 |
| **Moka cache miss** | 缓存未命中/过期 | 无——回退到 redb 直读 | 无影响 | 从 redb 重建缓存（异步） |
| **Moka cache stale** | 缓存版本落后于 redb | 无——redb 为权威源 | 旧数据给查询入口，不影响 tick | 下次写入时自动刷新 |
| **NATS publish fail** | NATS 连接断开/超时 | tick 已持久化到 redb，客户端未收到 delta | 客户端未更新 | NATS 重连；客户端 5s 未收到 delta → 主动拉取 |
| **Broadcast partial** | 部分客户端收到 delta | 客户端间状态暂时不一致 | 未收到的显示旧状态 | 客户端 last_tick gap 检测 → fetch |
| **BROADCAST overload** | 单 tick delta 过大导致 fan-out 积压 | tick 已持久化，但广播延迟 | 客户端收到延迟 delta | 降级：降低 fan-out rate，优先推送关键实体 |
| **TickCommitRecord write fail** | redb WriteTransaction 内 TickCommitRecord 写入失败 | tick 放弃（同事务，state 回滚） | fuel 退还 | tick abandon，Bevy snapshot 恢复。不存在"状态已提交但审计记录缺失"的缺口 |
| **RichTraceBlob write fail** | 对象存储异步写入失败（3 次重试后） | tick 已持久化，debug/rich trace 不可用 | 无 gameplay 影响 | `terminal_state = audit_gap`；不触发 rollback。GC 扫描清理孤儿 blob |

### 6.2 降级模式 (Degraded Mode)

连续 3 次 tick abandon → 引擎进入降级模式：
- 暂停新玩家加入 (`join_lock = true`)
- 暂停 MCP_Deploy 来源（禁止代码更新，防部署丢失）
- 保持已有玩家 WASM 执行
- 告警升级 → 需管理员介入
- 连续 10 tick 正常 → 自动退出降级模式

### 6.3 回放协议

#### 6.3.1 记录

每个 tick 写入 redb（不可变）：
```
/tick/{N}/commands   → 全部玩家排序后的 RawCommand
/tick/{N}/state      → tick 后的完整世界状态
/tick/{N}/rejections → 被拒绝的指令及原因
/tick/{N}/metrics    → TickMetrics
```

AI 玩家：记录 ACCEPTED 指令，不是原始 LLM 输出。回放时喂记录指令——不重调 LLM。

#### 6.3.2 回放执行

```
fn replay_tick(tick_N) -> WorldState:
    state = load_state(tick_N - 1)     // 起始状态
    commands = load_commands(tick_N)   // 记录的指令
    return execute_deterministic(state, commands)  // 必须 == 记录状态
```

`execute_deterministic(state, commands) != recorded_state` → 确定性 BUG。

#### 6.3.3 Wasmtime 版本与回放共存

**问题**: `wasmtime = "=30.0"` 锁定版本 → 发现 CVE 升级后旧 tick 回放中断。

**策略**: TickCommitRecord 始终记录 `Command[]` 而非 WASM 输出。回放时引擎直接执行已记录的指令序列，不重新调用 WASM。Wasmtime 版本变更不影响回放。仅当 tick 被标记为"降级模式"（WASM 执行异常）时，需匹配 Wasmtime 版本进行二次回放验证。

#### 6.3.4 TickCommitRecord 与 RichTraceBlob 写入失败语义

**TickCommitRecord**（redb replay-critical，同事务）：
TickCommitRecord 写入 redb 与 tick 执行在**同一事务**中——写入失败 = 事务回滚 → tick 放弃。

| 失败次数 | 行为 | 审计完整性 |
|:--:|------|:--:|
| 1 | 重试写入（同一 redb WriteTransaction 内） | ✅ 完整 |
| 2 | 重试写入（指数退避 100ms） | ✅ 完整 |
| 3 | 写入本地 WAL（`/var/lib/swarm/wal/tickcommit/`） | ⚠️ 本地完整，未全局持久化 |
| 4+ | WAL 写入 + 告警升级 CRITICAL | ⚠️ 本地完整 + 人工介入 |

**WAL 恢复**：WAL 中的 TickCommitRecord 在 redb 恢复后异步回放写入——不阻塞 tick 执行。WAL 保留策略：最多 10,000 tick 或 24h（先到者清理）。

**审计完整性保证**：
- tick 执行与 TickCommitRecord 写入是**同一 redb WriteTransaction**——要么都成功，要么都失败
- redb WriteTransaction 冲突回滚时，TickCommitRecord **不**写入——避免"有审计记录但世界状态未变"的不一致
- 连续 3 次 redb 写入失败 → tick 放弃（见 §6.1），TickCommitRecord 同样放弃——不存在"世界状态已变但无审计记录"的缺口
- WAL 提供最终一致性：最坏情况下审计记录延迟 ≤ WAL 保留窗口

**与回放的关系**：TickCommitRecord 写入失败 = tick 放弃（Bevy snapshot 恢复）→ 无状态变化 → 无可回放内容。不存在"tick 成功但回放数据丢失"的审计缺口。

---

**RichTraceBlob**（对象存储 async，可降级）：
RichTraceBlob 在 redb commit **成功**后异步写入对象存储——写入失败**不回滚**已提交的 tick。

| 失败场景 | 行为 | 语义 |
|---------|------|------|
| 初次写入失败 | 重试最多 3 次（指数退避 1s/2s/4s） | 不阻塞 tick 循环 |
| 3 次重试后仍失败 | `tick_manifest.upload_status = "failed"` | `terminal_state = audit_gap`；redb 状态完整 |
| Blob 写入成功 + etag 回填失败 | GC 扫描：1h 后清理孤儿 blob | 对象存储有 blob 但 manifest 无 etag |

RichTraceBlob 缺失的 tick 标记 `terminal_state = audit_gap`——replay 可用 TickCommitRecord + keyframe/delta 重建，仅 debug/rich trace 不可用。

### 6.4 MCP/Query 读源优先级

查询接口（MCP_Query / REST / WebSocket）的权威读源优先级：

| 查询类型 | 权威源 | 说明 |
|---------|--------|------|
| 当前世界状态（snapshot） | Bevy World（内存） | COLLECT 阶段已构建，最新 |
| 历史 tick 数据 | redb | 不可变记录 |
| 高频读取（地图/资源） | Engine 进程内 Moka Cache | 允许滞后 ≤ 2 tick；cache miss → redb |
| 实时事件（delta） | NATS | 仅推送，不保证送达；gap → redb fetch |

MCP_Query 不得直接读取 redb（绕过可见性过滤）。所有查询路径共享 `is_visible_to` 过滤器。

COLLECT 阶段从 Bevy World 内存读取权威状态，不访问 redb/Moka Cache。EXECUTE 阶段在 Bevy World 上原地修改 → redb WriteTransaction 提交 → 成功后 redb 为新的权威源。Bevy World 与 redb 的关系：Bevy 是每 tick 的工作副本，redb 是持久化的权威源。启动/恢复时从 redb 重建 Bevy World。

## 7. 确定性保证与反作弊

### 7.1 确定性合同

给定 tick N-1 状态 + tick N RawCommand + world_seed + 激活模组列表 → `execute_deterministic == recorded_state`。每个 tick 产出 `state_checksum` 写入 TickCommitRecord。

确定性依赖：
- PRNG：Blake3 XOF，确定性种子 + offset → 随机流，不依赖 OS 熵源
- Hash：Blake3 固定实现，不用 `std::hash`（跨版本可变）
- 排序：`(priority_class, shuffle_index, source_rank, sequence, command_hash)` — 相同 seed + 相同玩家集 + 相同指令 → 相同顺序。详见 §9.1。
- ECS：`.chain()` 严格串行，`.before()/.after()` 部分并行
- 数值：整数 + 定点数，禁用 `f64`（跨平台/编译器非确定）。禁止 IEEE 754 浮点数——所有数值计算使用 `u64`/`i64` 定点整数（basis points, ×10000 精度），禁止任何浮点类型出现在游戏状态中。定点数 JSON 序列化使用整数表示（非小数），避免 JSON 数字解析的跨语言精度差异。
- **canonical JSON**：`canonical_serialize()` 遵循 **[RFC 8785 JSON Canonicalization Scheme (JCS)](https://www.rfc-editor.org/rfc/rfc8785)**。禁止 IEEE 754 浮点数编码（JCS §3.2.2 定义的数字格式仅限整数，引擎侧不使用 `f64`/`f32`，输出端无浮点 JSON 数字）。对象键按 JCS 规则排序，字符串转义按 JCS §3.2.2.2/§3.2.3 输出；禁止多余空白字符。除 JCS 规定外，canonical codec **不额外执行 Unicode NFC normalization**。`canonical_codec_version` 与 `serde_swarm`/`swarm-codec-go` 双实现 hash fixture 见 `specs/core/persistence-contract.md` §2.1。
- HashMap/Dictionary：`BTreeMap`，不用 `std::HashMap`（迭代顺序非确定）

### 7.2 回放验证

CI 对随机采样 tick 做 full replay 验证：`execute_deterministic(state, commands) != recorded_state` → 确定性 BUG。

```rust
// redb 故障注入 CI 测试：验证快照恢复一致性
fn fdb_commit_failure_restores_snapshot_consistency() {
    fault_injection::set_mode(FaultMode::RandomCommitFailure {
        probability: 0.1,  // 10% tick 触发 commit 失败
        seed: 42,           // 确定性种子
    });
    for tick in 0..1000 {
        let snapshot = world.snapshot();
        let commit_result = execute_and_commit(&mut world, collected, tick);
        if commit_result.is_err() {
            world.restore(snapshot);
            assert_eq!(world.state_checksum(), snapshot_checksum);
        }
    }
}
```

### 7.3 异常检测

引擎对每个玩家进行运行时异常检测：

| 检测类型 | 方法 | 触发动作 |
|---------|------|---------|
| **状态变化超限** | 玩家 tick 间世界变化超过物理上限（drone 移动距离、资源获取速率、建造速度） | 标记玩家，该 tick 指令全部拒绝 |
| **指令模式异常** | 连续多 tick 提交相同指令序列（脚本化行为） | 降级为观察模式，限制 fuel budget |
| **WASM 静态分析** | 部署时扫描可疑系统调用模式、异常内存访问 | 拒绝部署，记录安全审计日志 |

### 7.4 CI 确定性验证

```bash
# 每 CI run 随机选取 5% tick 做 full replay
cargo test --test determinism -- --samples 1000 --sample-rate 0.05

# 验证断言
assert_eq!(replayed.state_checksum, recorded.state_checksum);
assert_eq!(replayed.entity_count, recorded.entity_count);
```

---

## 8. Tick 资源预算统一模型

本节定义单 tick 内所有阶段的资源预算，消除跨文档（specs/core/01、specs/core/04、specs/security/09）分散定义导致的实现分叉风险。specs/core/04 §6 的具体预算值以此表为准。

### 8.1 Tick Interval 语义

| 参数 | 值 | 语义 |
|------|-----|------|
| `tick_interval_ms` | 3000ms（World）/ 可配置（Arena，默认 300ms） | **目标值**，非硬上限 |
| `tick_soft_deadline_ms` | 2500ms | **软截止**——超过此值触发告警。正常操作不应触发（worker pool 水平可扩展） |
| `tick_hard_deadline_ms` | 4000ms | **硬截止**——超过此值 tick 放弃（Bevy snapshot 恢复），连续 3 tick 引擎降级 |
| `tick_overrun_policy` | `abort_and_retry` | 硬截止超时后：tick 放弃，恢复 snapshot，下一 tick retry。不下个 tick 补偿 |

**Worker pool 语义**：PlayerExecutor worker pool 水平可扩展——运营商根据 active_players 调整 worker_pool_max 即可消除排队。Per-player sandbox deadline（2500ms World / 200ms Arena）独立——每个 worker 上的玩家独立计时，互不影响。详见 `design/engine.md` §3.4.2。

**三层资源口径（R35 B3）**：容量推导依赖统一的资源模型——

| 层 | 单位 | 用途 | 确定性 |
|----|------|------|:--:|
| `wasmtime_fuel_units` | fuel units | 确定性计费——玩家代码执行消耗，跨引擎版本一致 | ✅ |
| `sandbox_wall_deadline_ms` | ms | 防 hang——单次 COLLECT 超时保护，不保证跨运行一致性 | ❌ |
| `cpu_cgroup_quota` | μs/period | OS 防 DoS——cgroup 隔离，per-worker 级 | ❌ |

容量公式必须使用经 benchmark 校准的 `fuel_schedule_version → calibrated_fuel_per_core_ms`。默认 `worker_pool_max = 256`——1000 player 推导需运维调至 1000 或使用分片，不是默认容量。cgroup `cpu.max` 与 sandbox deadline 的解耦保证单个坏玩家不能耗尽其他玩家的 COLLECT 时间窗。

### 8.2 统一预算表

| 阶段 | 资源 | 预算 | 超限行为 | 退还 |
|------|------|------|---------|:--:|
| **COLLECT** | wall-clock per player | 2500ms（`collect_timeout_ms`）— 每个玩家独立，并行执行，worker pool 水平可扩展 | 该玩家 0 指令 | ❌ |
| **COLLECT** | WASM fuel per player | 10,000,000 fuel units | 完整输出丢弃，0 指令 | ❌ |
| **COLLECT** | WASM linear memory | 64 MB | OOM → 该玩家 0 指令 | ❌ |
| **COLLECT** | Host function calls | 1000/tick | 第 1001 次返回错误 | ❌ |
| **COLLECT** | `host_path_find` calls | 10/tick + 100,000 explored_nodes 总额度 | 超限 → deterministic fail | ❌ |
| **COLLECT** | Output JSON | 256 KB | 整批丢弃（不保留前缀，不执行已解析指令） | ❌ |
| **EXECUTE** | wall-clock total | `tick_soft_deadline_ms` 内完成 | 软截止前必须完成（EXECUTE 不独立超时，由 COLLECT+EXECUTE 总预算控制，详见 §8.1 `tick_hard_deadline_ms`）。World ≤400ms / Arena ≤50ms 仅为性能目标，非硬超时。 | — |
| **EXECUTE** | redb retry count | 3 次 | 第 4 次失败 → tick 放弃 | ✅ 全额退还 |
| **EXECUTE** | COLLECT 缓存跨重试 | 复用首次 COLLECT 结果 | 不重新执行 WASM，fuel 不追加扣费 | — |
| **BROADCAST** | wall-clock | 无硬限制（异步发布） | Moka Cache/NATS 失败不影响已持久化 tick | — |
| **COMPILE** | wall-clock | 30s per module | 超时 → 拒绝部署 | ✅ (deploy 阶段，非 tick) |
| **COMPILE** | memory | 512 MB | OOM → 拒绝部署 | ✅ |

### 8.3 Simulate / Dry-Run 独立预算

MCP `swarm_simulate` / `swarm_dry_run` 使用独立于 tick 的配额池——防止模拟消耗影响实际 tick 预算：

| 资源 | 限制 | 说明 |
|------|------|------|
| `max_ticks` | 100 | 每次模拟最多 100 tick |
| `max_entities` | 1000 | 模拟世界最多实体数 |
| `max_output_bytes` | 1 MB | 模拟结果最大输出 |
| `max_cpu_ms` | 5000 | 每次模拟 CPU 时间 |
| `max_fuel_per_hour` | 50,000,000 | 每玩家每小时总模拟 fuel（独立于 tick fuel） |
| `concurrent_simulates` | 3 | 每玩家并行模拟上限 |

World 与 Arena 的 simulate 配额**相同**——两者使用同一引擎和同一预算模型。Arena 因为 tick_interval_ms 更短，模拟的 wall-clock 窗口更窄，但 fuel/entity 配额不变。

### 8.4 COLLECT 缓存复用 `consumed_fuel` 语义

redb commit 失败重试时，COLLECT 结果被缓存复用。fuel 扣费语义：

```
首次 COLLECT: consumed_fuel[tick] = actual_fuel_used
redb commit 成功: final_fuel[tick] = consumed_fuel[tick]

redb commit 失败 (retry 1): 跳过 COLLECT，直接 EXECUTE
  → consumed_fuel 不变（不追加扣费）
  → 跨重试总 fuel ≤ 1 × MAX_FUEL

redb commit 成功 (retry N): final_fuel[tick] = consumed_fuel[tick]
redb commit 失败 (retry 3，放弃): 退还 consumed_fuel[tick]

## 9. 确定性合同 (Determinism Contract)

本节是 Swarm 的确定性权威合同——所有实现者（engine、Gateway、SDK、replay verifier）必须一致遵守。若实现者各自选择合理解释，线上 tick 与 replay 可能分叉。

### 9.1 命令全局排序键

所有命令按**分层排序键**确定全局执行顺序：

```
sort_key = (priority_class, shuffle_index, source_rank, sequence, command_hash)
```

**第一层 `priority_class`**：命令优先级类别。取值：`0` = Admin, `1` = WASM, `2` = MCP_Deploy, `3` = MCP_Query。Admin 命令始终最先（紧急冻结/审计操作），WASM 在 MCP 命令之前（沙箱内联执行），MCP_Deploy 在 MCP_Query 之前（写优先于读）。

**第二层 `shuffle_index`**（Player 类内）：使用 Fisher-Yates 种子洗牌确定玩家顺序。种子 = `Blake3("shuffle" || world_seed || tick.to_le_bytes())`，TickCommitRecord 记录 `seed_epoch` 和活跃玩家集快照以支持回放。

**第三层 `source_rank`**：per-source 排序，在相同 shuffle slot 内按 source 类别排序（WASM > MCP_Deploy > MCP_Query）。

**第四层 `sequence`**：同一玩家内同一 tick 内按 `sequence` 升序排列（per-player 单调递增序号）。

**第五层 `command_hash`**：`Blake3(canonical_serialize(raw_command))` 作为稳定 tiebreaker，确保完全确定性排序（即使所有前四层相同）。`canonical_serialize()` 遵循 RFC 8785/JCS，且不额外执行 Unicode NFC normalization。

排序结果确定——相同 seed + 相同玩家集 + 相同命令集 → 相同执行顺序。此排序键同时用于 Phase 2a inline apply 顺序和 TickCommitRecord 记录。

### 9.2 部署生效时序

`swarm_deploy` 的生效时序（详见 `specs/core/persistence-contract.md` §2.3 Deploy 完整状态机）：

```
tick N:    swarm_deploy 调用 → 编译/签名 → redb manifest commit (deploy_mutation replay class)
           └─ 同时入队对象存储异步上传 WASM binary
tick N+1:  若 upload_status == "complete" → COLLECT 阶段加载新模块 → EXECUTE 阶段首次执行
           若 upload_status != "complete" → drone 保持旧模块，deploy 进入 FAILED
```

部署在 redb manifest commit 后的**下一完整 tick** 生效（`activation_tick = current_tick + 1`）。同一 tick 内的 deploy 不影响当前 tick 的执行——WASM 模块快照在 COLLECT 开始时确定。**Replay verifier 以 redb manifest 中的 `redb_version_counter` 全序重放，不依赖对象存储 blob 可用性。**

### 9.3 输出状态合同 (Output State Contract)

各消费端看到世界状态的版本语义：

| 消费端 | 读源 | 版本 | 滞后 |
|---|---|---|---|
| **WASM `tick(snapshot)`** | COLLECT 开始时 Bevy snapshot | `snapshot.tick == current_tick` | 0（本 tick 初始状态） |
| **MCP `swarm_get_snapshot`** | 同 WASM 的 snapshot | `snapshot.tick == current_tick` | 0 |
| **WebSocket delta** | BROADCAST 阶段计算的增量 | `delta.tick == last_committed_tick` | 0（同 tick 推送） |
| **Replay / TickCommitRecord** | redb 持久化记录 | `tick_commit_record.tick == executed_tick` | 0（权威审计记录） |
| **MCP `swarm_get_player_status`** | Moka Cache → redb | `last_tick` 字段 | ≤ 1 tick |
| **Moka cache** | 上次 BROADCAST 写入 | 缓存版本号 | 0–60s（可配置） |

**关键不变量**：WASM `tick()` 和 MCP `swarm_get_snapshot` 始终看到同一份权威快照——不存在"WASM 执行中世界已变化"的时差。WebSocket 推送的 delta 基于同一份已提交状态计算。

Bevy World 是 tick 内的权威执行状态；redb 是跨 tick 的持久化权威；Engine 进程内 Moka Cache 是读缓存（允许滞后，但写入后立即一致）；NATS/WebSocket 是推送通道（尽力送达，gap 由客户端 fetch 填补）。

### 9.4 TickCommitRecord 完整性

TickCommitRecord 必须与 redb 状态写入在同一事务中——禁止"状态成功但审计不完整"与"同事务无缺口"并存：

```
redb WriteTransaction:
  ├── 写入世界状态 (state/tick/N)
  ├── 写入 TickCommitRecord (tick_commit/tick/N)  ← 同一事务
  └── 写入 consumed_fuel (fuel/tick/N)

事务成功 → 状态 + TickCommitRecord + fuel 三者原子持久化
事务失败 → 三者全部回滚，重试
```

若 TickCommitRecord 写入失败（极罕见：事务内部错误），整个 tick 回滚——不允许状态成功但审计缺失。

**Crash 恢复语义**：engine 进程在 COLLECT 完成后、redb commit 前的任意时刻崩溃时：

| 崩溃时点 | 已扣 fuel | 已扣 body_cost | 恢复行为 |
|---------|:--:|:--:|------|
| COLLECT 完成，EXECUTE 执行中 | 是 | 是（spawn 命令 inline apply 时扣除） | 整个 tick 回滚，fuel **全额退还**，当前 tick 重新执行 |
| EXECUTE 完成，redb commit 前 | 是 | 是 | redb WriteTransaction 未提交 → state + TickCommitRecord + fuel 三者均未持久化 → 自动回滚，下一 tick 重试 |
| redb commit 成功后 crash | 是 | 是 | 状态已持久化，恢复后从下一 tick 继续——不重复执行 |

**body_cost refund 规则**：若 Phase 2b spawn_system 创建失败（如 room cap 竞争），已扣除的 body_cost 全额退还到原扣费来源（spawn.energy 优先，capacity 不足部分回到全局存储）。refund 与 fuel refund 是独立资源池——前者操作 ResourceStore，后者操作 fuel budget。

**事务大小约束**：单 tick 的 redb WriteTransaction 仅写入状态 delta + TickCommitRecord manifest + fuel 记录，不写入全量世界状态。大型 binary payload（RichTraceBlob、keyframe snapshot）写入对象存储，redb 仅存指针 + hash + 大小。确保事务大小 < 10MB（redb 推荐上限）。跨 tick 状态通过 prior_tick manifest hash 形成可验证链。

**完整性保护（分层语义）**：
- **TickCommitRecord**：redb 同事务原子写入，缺失 ≥1 字段则 tick 不可 replay（`terminal_state = unreplayable`）。tick 放弃时 TickCommitRecord 不产生——不存在"状态已变更但无审计记录"。
- **RichTraceBlob**：对象存储异步写入，写入失败 → `terminal_state = audit_gap`（不触发回滚）。缺失时 replay 可用 TickCommitRecord + keyframe/delta 重建，仅 debug/rich trace 不可用。
- **ReplayArtifact**：从 TickCommitRecord（critical subset）+ keyframe/delta 重建。`terminal_state = reconstructable` 时从部分关键字段恢复。

三者关系：
```
TickCommitRecord (redb, same-tx)  ──→  不可降级，失败 = abandon
        │
        ├──→ 直接用于 deterministic replay
        └──→ 与 keyframe/delta 组合 → ReplayArtifact

RichTraceBlob (Blob Store, async)  ──→  可降级，失败 = audit_gap
        └──→ 提供 debug detail, rich events, per-system metrics
```

### 9.5 RNG 确定性

RNG 流按 namespace 隔离：

| Namespace | Seed 来源 | 用途 |
|---|---|---|
| `combat` | `world_seed + tick` | 伤害浮动、暴击判定 |
| `loot` | `world_seed + tick + entity_id` | 掉落生成 |
| `npc_spawn` | `world_seed + tick + room_id` | NPC 生成 |
| `event` | `world_seed + tick` | 世界事件触发 |

每个 namespace 使用独立派生流的 Blake3 XOF——`Blake3(domain_sep || world_seed || tick.to_le_bytes())`——种子确定性导出。任何 WASM host function 不暴露 RNG 或熵源——WASM 代码必须使用 `swarm_get_random(sequence)` 从 host 获取确定性随机数。

### 9.6 ECS 调度权威顺序

系统执行顺序的唯一权威定义见 [Complete Tick Execution Manifest](phase2b-system-manifest.md) §1。Phase 2b 串行脊柱（R30 B1 — 31 systems）：

```
death_marker → spawn → spawning_grace → regeneration →
combat (parallel set A: attack/ranged_attack/heal) →
special_attack_reducer → damage_application →
status buffer production (parallel set B: hack_buf/drain_buf/overload_buf/debuff_buf/disrupt_buf/fortify_buf/leech_buf/fabricate_buf) →
status_advance_system (serial — 唯一 StatusState writer) →
aging → decay → death_cleanup → pvp_block → room_state → controller_2b → resource_ledger
```

所有特殊攻击的状态推进由 `status_advance_system`（S22）**唯一**串行处理——S16-S22b 只写 typed buffer，不直接修改 StatusState。S01 写入 `PendingSpecialAttackIntent`；S14 归并裁决后交付 S22。

**关键变更**（R16 B2）：
- `regeneration`（S10）移至 `damage_application`（S15）之前，防止 heal+regen 双倍回复。
- `spawning_grace`（S09）移至 combat（S11-S13）之前，确保出生 tick 免疫保护。
- `death_marker`（S07）在 `spawn`（S08）之前，RoomCap 同 tick 释放。

### 9.7 WASM output 截断

WASM `tick()` 输出上限 256KB。超出时**整批丢弃**——不保留部分解析的前缀，不执行已解析的前 N 条指令。处理合同：

| 状态 | 语义 | 处理 |
|------|------|------|
| **正常** | output ≤ 256KB | 完整指令列表入队执行 |
| **Truncated** | output > 256KB | 整批丢弃，产出 `output_truncated` 拒绝原因 |
| **记录** | — | 写入 TickCommitRecord：`wasm_output_truncated: true`，记录 `output_size_bytes` 和 `truncated_at` |
| **通知** | — | 通过 snapshot/status 通知玩家：`wasm_output_status: "output_truncated"`，附带实际 output 大小 |

WASM 模块收到 `output_truncated` 拒绝码，下一 tick 可重新输出缩减后的指令列表。引擎不执行前缀解析——杜绝部分执行导致的游戏状态不一致。

### 9.8 动态规则脚本移除

运行时规则脚本层已被移除。世界规则扩展只通过 `design/engine.md` 定义的 Bevy Plugin 机制进入 Engine 二进制；扩展 action 必须通过 World Action Manifest + IDL 注册 schema。
```

禁止通过故意竞争失败构造重试绕过 budget：同 tick 内 WASM 仅执行一次（首次 COLLECT），后续重试不触发新的 WASM 调用。
