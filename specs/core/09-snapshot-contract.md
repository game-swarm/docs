# Snapshot Contract — 快照截断 · 模拟隔离 · MVP 经济边界 · 安全提示阶梯

> 详见 design/engine.md
>
> **R15 H3/H4/DH1/DH2**。本文档定义 Swarm 引擎快照溢出行为（H3）、模拟/试运行隔离（H4）、MVP 经济边界（DH1）与安全提示分级（DH2），补齐引擎在边界条件与竞技诚信上的合同空白。
>
> **R22 B5 修复**。本文档为 snapshot truncation 的**唯一权威**。新增 measured admission model、capacity SLO + hard budget、pathfinding determinism contract。

## 原则

1. **快照可截断，不可伪造**：当快照超出 256KB 上限时，引擎可截断非关键实体，但必须明确标记截断事实与省略统计。
2. **模拟零副作用**：`swarm_simulate` 产生的 fork 不与权威引擎共享任何可变状态——不消费 RNG 序数、不写入 TickTrace、不影响燃料账本。
3. **竞技公平优先**：截断不得移除影响战术合法性的实体；模拟输出必须携带 `authoritative=false` 标记，防止混淆。
4. **经济边界明确**：MVP 核心经济操作锁定；市场/合约/商人等划入 Future RFC，不在 MVP 范围内实现。
5. **提示按模式分级**：错误提示信息量随竞技→练习→训练模式递增，绝不向竞技对手泄露隐藏状态。

---

## 1. Snapshot Truncation Contract（快照截断合同）— H3

### 1.1 触发条件

引擎在每 tick 结束时为每个 drone 生成感知快照（perception snapshot）。快照序列化为 JSON 后若超过 **256KB** 上限，触发截断：

| 条件 | 行为 |
|------|------|
| `snapshot_size ≤ 256KB` | 完整快照，`truncated = false` |
| `snapshot_size > 256KB` | 截断快照，`truncated = true` |

### 1.2 截断标记

截断后的快照 JSON 必须包含以下字段：

```jsonc
{
  "tick": 12345,
  "drone_id": "drone_0xABCD",
  "truncated": true,
  "omitted_categories": {
    "entities": 47,    // 被省略的实体数量
    "resources": 12,    // 被省略的资源点数量
    "events": 3         // 被省略的事件数量
  },
  "entities": [ /* 保留的实体列表 */ ],
  "resources": [ /* 保留的资源列表 */ ],
  "events": [ /* 保留的事件列表 */ ]
}
```

`omitted_categories` 的值是本次截断实际省略的数量——即使某一类被省略 0 个，键也必须存在（值为 `0`），以保证 schema 稳定性。

### 1.3 确定性截断顺序

截断顺序必须完全确定（同一世界状态、同一 tick、同一 drone 产生完全相同的截断结果）：

1. **第一排序键：距离桶（distance bucket）**

   以无人机当前位置为原点，将实体分组到距离桶：

   | 桶序号 | 距离范围 | 说明 |
   |:------:|----------|------|
   | 0 | 0 | 自身（own） |
   | 1 | (0, 1] | 相邻格 |
   | 2 | (1, 4] | 近距 |
   | 3 | (4, 8] | 中距 |
   | 4 | (8, 16] | 远距 |
   | 5 | (16, 32] | 超远距 |
   | 6 | (32, ∞) | 视野外 |

   资源点和事件按相同桶逻辑分组（事件以事件源位置计算桶）。

2. **第二排序键：`entity_id` 字典序**

   同一距离桶内，按 `entity_id` 的字节序（lexicographic order）排列。

3. **截断方向：从最远桶最末尾开始移除**

   引擎从 bucket 6（最远）的最后一个 entity_id 开始丢弃，逐一向内推进，直到快照体积 ≤ 256KB。

### 1.4 关键实体永不截断

以下实体被标记为 **critical**，截断过程**绝不**触及：

| 关键实体 | 原因 |
|----------|------|
| 自身 drone（own） | 玩家始终需要知道自己状态 |
| Room Controller | 房间争夺核心，移除将破坏战术合法性 |
| 当前 `target` 指向的实体 | 玩家的攻击/交互目标不可丢失 |
| 己方所有 drone | 同玩家多 drone 必须完全可见 |
| 正在攻击自身的实体 | 防御决策必需 |

实现方式：关键实体在排序时置于不可截断前缀，截断游标不得越过此前缀。

### 1.5 竞技世界截断降级

在 **competitive** 模式下，如果截断导致以下任一情况发生，该 tick 被标记为 **tick degraded**：

- 移除了任何一个玩家可合法交互的实体（位于 `action_range` 内但被截断）
- 移除了任何一个处于冷却中的敌对实体（玩家本可据此决策）
- `omitted_categories.entities > 0` 且被省略实体中包含非中立实体

Tick degraded 不阻止引擎推进，但会记录到 TickTrace 的 `degradation` 段，并在 API 中暴露 `tick_integrity = "degraded"`。竞技平台可据此判定该时刻的战术有效性。

---

## 2. Simulate / Dry-Run Isolation（模拟/试运行隔离）— H4

### 2.1 `swarm_simulate` — 预测性模拟（不可用于竞技决策）

`swarm_simulate` 是对权威引擎的 **side-effect-free fork**，用于玩家预览潜在行动结果。

#### 隔离保证

| 隔离维度 | 权威引擎 | simulate fork |
|----------|:-------:|:-------------:|
| RNG namespace | `authoritative` | `simulate_preview` |
| RNG ordinal 消费 | ✅ 消费 | ❌ 不消费 |
| TickTrace 写入 | ✅ 写入 | ❌ 不写入 |
| Fuel ledger 扣减 | ✅ 扣减 | ❌ 不扣减 |
| 世界状态修改 | ✅ 持久 | ❌ 丢弃 |
| Cache 共享 | — | ❌ 独立 cache |
| Snapshot 缓存 | — | ❌ 独立缓存 |

#### Fork 生命周期

```
swarm_simulate(world_state, drone_id, action)
    │
    ├─ 1. 深拷贝世界状态（只读）
    ├─ 2. 初始化独立 RNG，seed = hash(authoritative_seed + "simulate_preview" + drone_id + tick)
    ├─ 3. 在 fork 中应用 action
    ├─ 4. 生成结果快照
    └─ 5. 丢弃 fork，返回结果
```

Fork 副本**仅存活于单次 simulate 调用的栈帧内**，不存在跨请求的 fork 池或缓存。

#### 输出契约

```jsonc
{
  "authoritative": false,
  "not_predictive": true,
  "result": { /* 模拟结果 */ },
  "rng_ordinals_consumed": 0,
  "fuel_consumed": 0,
  "tick_trace_written": false
}
```

| 字段 | 含义 |
|------|------|
| `authoritative: false` | 此结果不是权威引擎产出 |
| `not_predictive: true` | 此结果不保证在实际 tick 中复现（RNG 不同、对手行为不同、世界状态已变） |

### 2.2 `swarm_dry_run` — 确定性试运行（MCP 中可用）

`swarm_dry_run` 是 `swarm_simulate` 的**确定性变体**，在 MCP（Model Context Protocol）中以独立方法暴露。

与 `swarm_simulate` 的区别：

| 特性 | `swarm_simulate` | `swarm_dry_run` |
|------|:---------------:|:-------------:|
| RNG 来源 | 独立 seed | 固定 seed（确定性） |
| 结果可复现 | ❌ | ✅（同输入 → 同输出） |
| 用途 | 玩家预览 | 测试 / MCP 工具调用 / CI |
| `not_predictive` | `true` | `true` |
| `deterministic` 标记 | 无 | `true` |

### 2.3 产品命名指引

| 内部名称 | 产品/文档标签 | 说明 |
|----------|--------------|------|
| `swarm_simulate` | **非预测性预览**（Non-Predictive Preview） | 强调不可用于竞技决策 |
| `swarm_dry_run` | **试运行**（Dry Run） | 确定性、用于测试与工具集成 |

产品 UI 在展示 simulate 结果时，必须显示醒目的不可信标记（如 "此结果为非预测性预览，实际结果可能不同"），防止玩家将预览结果当作承诺。

---

## 3. MVP Economy Boundaries（MVP 经济边界）— DH1

### 3.1 核心 MVP 经济操作

以下操作在 MVP 中**必须完整实现**：

| 操作 | 类型 | 说明 |
|------|:---:|------|
| `LocalTransfer` | 即时转移 | drone 间本地资源转移，无延迟、无手续费 |
| `GlobalDeposit` | 延迟转移 | 存入全局仓库，收取 `global_deposit_fee`（1%） |
| `GlobalWithdraw` | 延迟转移 | 从全局仓库提取，`global_transfer_delay`（100 tick）后到账，收取 `global_withdraw_fee`（5%） |
| `RecycleRefund` | 回收 | 拆除建筑/回收 drone，按 `recycle_refund_base`（50%）退还资源，最低 `recycle_refund_min`（10%） |
| `BuildCost` | 消耗 | 建造建筑时扣除资源 |
| `SpawnCost` | 消耗 | 生成 drone 时扣除资源 |
| `UpkeepDeduction` | 消耗 | 每 tick 维护费扣除 |
| `StorageTax` | 消耗 | 仓库存储税（0.1%/tick） |

### 3.2 联盟转移（受限合作）

Allied Transfer 在 MVP 中以**受限合作（Restricted Cooperation）**模式实现——功能可用但受严格约束：

| 约束 | 值 | 说明 |
|------|:---:|------|
| `allied_transfer_fee` | 200 bp (2%) | 联盟间转移手续费 |
| `allied_transfer_delay` | 200 tick | 延迟到账 |
| `allied_transfer_cooldown` | 500 tick | 同目标两次转移间冷却 |
| `allied_daily_cap` | 10,000 units | 24h 内对同一接收者上限 |
| 联盟成员最低时长 | 100 tick | 双方必须在同一联盟 ≥ 100 tick |
| 新玩家锁 | 500 tick | 新玩家禁止接收任何转移 |
| 审计日志 | 全部记录 | 每笔 Allied Transfer 写入完整审计日志 |

**MVP 不实现**：联盟资源池（Alliance Resource Pool）、联盟税率、联盟仓库共享。

### 3.3 Future RFC（不在 MVP 范围）

以下经济特性明确划入 **Future RFC**，MVP 中**不实现**：

| 特性 | RFC 标记 | 说明 |
|------|:-------:|------|
| Contract Settlement | `RFC-CONTRACT` | 智能合约结算，条件触发式转移 |
| Merchant NPC | `RFC-MERCHANT` | NPC 商人，固定汇率买卖 |
| Drone P2P Offer | `RFC-P2P` | 无人机间点对点报价交易 |
| Auction House | `RFC-AUCTION` | 拍卖行 |
| Escrow Service | `RFC-ESCROW` | 第三方托管服务 |
| Resource Lending | `RFC-LEND` | 资源借贷（含利息） |

代码中可使用 `enum` 变体预留这些操作类型（如 `ContractSettlement`），但路由到 `unimplemented!()` 或返回 `Err(FeatureGate::FutureRfc)`。

### 3.4 Challenge Board 奖励约束

Challenge Board（挑战板）在 MVP 中**仅发放非资源奖励**：

| 允许的奖励 | 禁止的奖励 |
|------------|-----------|
| Bounty 积分/称号 | 直接资源发放 |
| Replay 分享链接 | 稀有物品/装备 |
| 排行榜位置 | 经验值/等级提升 |
| 成就徽章 | 任何形式的可交易资源 |

原因：通过 Challenge Board 注入资源会绕过 Resource Ledger 的单入口审计，形成逃逸路径。资源注入的唯一合法路径是 PvE Award（通过 Ledger 的 `PvEAward` 操作）。

---

## 4. Safe Hint Ladder（安全提示阶梯）— DH2

### 4.1 三级错误提示模型

引擎在命令校验失败时返回的错误信息量，按世界模式分级：

```
竞技模式 (competitive)    练习模式 (practice)     训练模式 (training)
    │                        │                      │
    ▼                        ▼                      ▼
┌─────────┐            ┌──────────┐           ┌──────────────┐
│ Safe    │            │ Safe +   │           │ Full Debug   │
│ Only    │            │ Fix Hint │           │ Detail       │
└─────────┘            └──────────┘           └──────────────┘
```

### 4.2 竞技模式（Competitive）：Safe Only

竞技模式下的错误消息**仅包含公开信息**——任何对手也能从世界状态中推导出的信息：

| 错误类别 | 返回信息 | 不返回 |
|----------|---------|--------|
| `NotVisibleOrNotFound` | `"target not visible or not found"` | 目标是否存在、是否在视野内、是否被隐身 |
| `OutOfRange` | `"action out of range"` | 目标实际坐标、距离值、所需距离 |
| `CooldownActive` | `"cooldown active"` | 剩余冷却 tick 数、冷却触发时间 |
| `InsufficientResources` | `"insufficient resources"` | 缺少哪类资源、缺少多少、当前持有量 |
| `PermissionDenied` | `"permission denied"` | 具体缺失的权限、权限持有者 |
| `InvalidTarget` | `"invalid target"` | 为什么无效、有效目标列表 |

**关键原则**：竞技错误消息让对手无法通过故意触发错误来探测隐藏状态。所有 safe 消息都是常数字符串，不包含任何动态值。

### 4.3 练习模式（Practice/Replay）：Safe + Fix Hint

练习模式在 safe 消息基础上追加**修复提示**（fix hint），帮助玩家理解为什么操作失败，但**仍不泄露隐藏状态**：

```jsonc
// 竞技模式
{ "error": "cooldown active" }

// 练习模式
{
  "error": "cooldown active",
  "fix_hint": "Wait for the cooldown to expire before retrying this action.",
  "category": "CooldownActive"
}
```

| 错误类别 | 练习模式追加信息 |
|----------|-----------------|
| `CooldownActive` | 提示等待冷却结束，但不透露剩余 tick |
| `OutOfRange` | 提示靠近目标或使用远程操作，但不透露距离 |
| `InsufficientResources` | 提示资源不足，建议采集或回收，但不透露差额 |
| `NotVisibleOrNotFound` | 提示目标可能不在视野或已被摧毁 |
| `PermissionDenied` | 提示可能需要控制器权限或满足特定条件 |
| `InvalidTarget` | 提示目标类型不适用当前操作 |

### 4.4 训练模式（Training）：Full Debug Detail

训练模式返回**完整调试信息**，包含所有内部状态：

```jsonc
{
  "error": "out of range",
  "category": "OutOfRange",
  "fix_hint": "Move closer to the target or use a longer-range action.",
  "debug": {
    "target_position": { "x": 15, "y": 8, "room": "W3N5" },
    "drone_position": { "x": 4, "y": 2, "room": "W3N5" },
    "distance": 12.53,
    "required_range": 5.0,
    "action": "Attack",
    "action_range": 3.0
  }
}
```

训练模式返回所有内部状态字段，包括：
- 精确坐标与距离
- 剩余冷却 tick 数
- 资源持有量与需求量
- 视野内实体列表
- 权限检查详情
- RNG 状态快照

### 4.5 实现机制

引擎内部错误类型统一携带三个级别的 payload：

```rust
enum HintLevel {
    Safe,       // 竞技模式
    FixHint,    // 练习/回放模式
    FullDebug,  // 训练模式
}

struct CommandError {
    category: ErrorCategory,
    safe_message: &'static str,         // 竞技模式输出
    fix_hint: Option<&'static str>,     // 练习模式追加
    debug_detail: Option<DebugPayload>, // 训练模式追加
}
```

API 层根据世界模式字段 `world.hint_level` 选择暴露哪个级别的信息：

| `world.hint_level` | 返回 hint_level | 适用场景 |
|:------------------:|:--------------:|----------|
| `competitive` | `Safe` | 排位赛、锦标赛、竞技匹配 |
| `practice` | `FixHint` | 练习赛、回放观看、沙盒 |
| `training` | `FullDebug` | 教程、调试、开发环境 |

---

## 5. 跨切面约束

### 5.1 截断 × 模拟

- `swarm_simulate` 返回的快照遵循相同的截断规则（256KB 上限）。
- simulate fork 中触发的截断**不影响**权威引擎的 TickTrace（fork 被完全丢弃）。
- simulate 输出的 `truncated` 标记与权威快照格式一致。

### 5.2 经济 × 截断

- 资源转移操作不计入快照体积（资源数据在独立 ledger 段）。
- 截断不影响经济结算——被截断的实体仍参与正常的资源流动，只是不在感知快照中暴露。

### 5.3 提示阶梯 × 模拟

- simulate/dry_run 的输出中的错误消息按当前世界 `hint_level` 返回。
- MCP 工具调用 `swarm_dry_run` 时，可传入 `hint_level` 覆盖世界默认值（仅限训练模式提升，不允许降级）。

---

## 6. 兼容性与迁移

| 版本 | 变更 |
|------|------|
| MVP | 快照截断实现 H3；simulate 隔离实现 H4；经济边界按 DH1 锁定；提示阶梯实现 DH2 |
| Future | `truncated` 字段可能增加 `truncation_reason` 枚举；simulate 可能支持指定 RNG seed；Allied Transfer 可能放宽约束 |

---

## 7. Capacity Admission Model (R22 B5)

> **R22 B5**: 从静态容量承诺改为 measured admission。基于实测 p95/p99 指标动态计算 admitted players/fuel。

### 7.1 Capacity SLO + Hard Budget

| 指标 | SLO (target) | Hard Budget (拒绝阈值) | 说明 |
|------|:-----------:|:--------------------:|------|
| Per-tick FDB mutation count | < 5,000 | 10,000 | 单 tick 事务内 mutation 数 |
| Snapshot build time | < 200ms p95 | 500ms | COLLECT 阶段快照构建 |
| Network broadcast budget | < 100ms | 300ms | BROADCAST 阶段 delta 推送 |
| Worker reset bandwidth | < 50ms p99 | 200ms | WASM 实例化开销 |
| Pathfinding budget | < 100ms p95 | 250ms | 路径搜索 CPU budget |
| Active players | target 500 | hard cap 1000 | measured admission 自动调节 |

### 7.2 Admission Decision

```
每 tick 评估:
  active_players = count(players with deployed WASM + ≥1 alive drone)
  measured_p95 = recent p95 of (sandbox_exec + snapshot_stitch + fdb_commit)
  
  if measured_p95 > SLO:
      reduce admitted_players by 10% (hysteresis: 10 tick cooldown before re-increase)
  if measured_p95 < 50% of SLO for 30+ consecutive ticks:
      increase admitted_players by 5% (gradual recovery)
  
  effective_per_player_quota = remaining_tick_budget / active_players
  
  if effective_per_player_quota < MIN_FUEL (500,000):
      reject new players → ERR_CPU_SATURATED
```

### 7.3 Pathfinding Cache Determinism Contract

Pathfinding cache 是 pure optimization：
- **hit/miss 不改变输出**：相同起点/终点/terrain → 相同路径（无论 cache 状态）
- **Cache population timing** 不进入 replay-critical envelope
- **Budget accounting**：cache hit 时仍消耗相同 fuel（确定性必要）
- **Cache invalidation**：terrain 变更（Build/Wall/结构破坏）触发对应区域 cache purge
- CI 验证：随机采样 tick，对比 cache-enabled vs cache-disabled 执行结果 → 必须一致
