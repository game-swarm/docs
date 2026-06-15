# P0-5: 统一可见性策略

> **状态**: Phase 0 冻结 | **日期**: 2026-06-14 | **版本**: 1.0

> **状态**: Frozen for Phase 0 | **实现阶段**: Phase 1-2

## 1. 核心原则

**一个函数回答「玩家 P 在 tick T 能看到什么」：**

```rust
fn is_visible_to(entity: &Entity, player_id: PlayerId, tick: u64) -> bool;
```

所有输出面调用此函数。无绕过。不存在「这只是调试数据所以没关系」的例外。

## 2. 可见性规则

### 2.1 自身实体

```
OWNER: 始终可见，不限位置、不限 tick。
```

玩家始终看到自己的 drone、建筑、资源、在建工程和 Controller。

### 2.2 有视野的房间

```
ROOM_VISIBLE: 若玩家在该房间有视野则可见。
视野来源: 任意拥有的 drone 或建筑，vision_range > 0。
```

| 视野来源 | 范围 |
|---------|------|
| Drone | 3（默认，取决于身体部件） |
| Spawn | 3 |
| Tower | 3（充能后 6） |
| Observer | 10（激活时） |
| Controller（拥有者，level ≥ 1） | 1 |

### 2.3 中立/敌对实体

```
HOSTILE: 若在任何友好视野源范围内则可见。
```

敌方 drone、中立建筑、地上资源——落入任何视野锥内即可见。

### 2.4 隐藏信息

| 数据 | 默认可见性 |
|------|-----------|
| 其他玩家资源数量 | ❌ 隐藏 |
| 其他玩家 Controller 进度 | ❌ 隐藏 |
| 其他玩家在建工程 | ✅ 可见（在视野内） |
| 其他玩家冷却时间 | ❌ 隐藏 |
| 其他玩家疲劳值 | ❌ 隐藏 |
| 其他玩家身体部件组成 | ✅ 可见（可观察特征） |
| RNG 种子 | ❌ 始终隐藏 |
| 被拒绝指令（其他玩家） | ❌ 隐藏 |
| WASM 模块错误（其他玩家） | ❌ 隐藏 |

### 2.5 市场

```
MARKET: 所有活跃订单对有视野房间的全体玩家可见。订单创建者身份可见。
```

### 2.6 排行榜

```
LEADERBOARD: 公开。指标: GCL、房间数、drone 数。
隐藏: 资源总量、当前策略、WASM 模块源码。
```

## 3. 各输出面执行

### 3.0 Host Functions（WASM 查询）

所有 query host function 的返回结果均经 `is_visible_to` 过滤——与 snapshot 使用同一可见性函数。无绕过：WASM 模块传入任意坐标调用 `get_objects_in_range` 时，仅返回对调用者可见的实体。`path_find` 仅基于可见地形计算路径。

### 3.1 快照（WASM `tick()` 输入）

```json
{
  "tick": 4521,
  "player_id": 42,
  "entities": [/* is_visible_to 过滤 */],
  "terrain": [/* 所有可见房间的地形 */],
  "resources": { "energy": 5000, "minerals": {"H": 1200} },  // 仅自身
  "controller": { "level": 3, "progress": 4500 },            // 仅自身
  "market_orders": [/* 可见订单 */],
  "leaderboard_snapshot": { "rank": 42, "gcl": 1500000 }
}
```

### 3.2 MCP 工具

| 工具 | 可见性过滤 |
|------|-----------|
| `get_snapshot` | 完整 `is_visible_to` 过滤 |
| `get_objects_in_range` | `is_visible_to` + 范围检查 |
| `get_terrain` | 任意格 — 地形是公开信息 |
| `inspect_entity` | 仅当 `is_visible_to` 返回 true 或为自身实体 |
| `inspect_room` | 仅限自身有视野的房间 |

### 3.3 WebSocket 增量

```
每 tick 推送增量: 仅包含变更 且 is_visible_to(subscriber) 为 true 的实体。
```

### 3.4 REST API

```
GET /api/v1/world/rooms/:id  → 实体列表经 is_visible_to(请求者) 过滤
GET /api/v1/world/rooms/:id/map → 仅地形（公开）
```

### 3.5 旁观者视图 (Spectator View)

**两层分离**：引擎始终按 `is_visible_to` 计算 drone 的 snapshot（游戏公平性），但玩家/旁观者的「摄像头」可以有不同的可见范围（观战体验）。

| 模式 | drone snapshot | 玩家屏幕 / MCP | WebSocket 旁观 |
|------|---------------|---------------|---------------|
| `player_view = "drone"` | `is_visible_to(player)` 过滤 | 同 snapshot | 同 snapshot |
| `player_view = "full"` | `is_visible_to(player)` 过滤 | 全地图（无视 fog） | 全地图（如 `public_spectate=true`） |
| `player_view = "allied"` | `is_visible_to(player)` 过滤 | 所有友方 drone 聚合视野 | N/A |

**关键不变量**：无论 `player_view` 如何设置，WASM `tick()` 收到的 snapshot **始终**按 `is_visible_to(player)` 过滤——`fog_of_war` 控制。`player_view` 只影响人类屏幕和 MCP 只读查询。

**旁观者 WebSocket**：当 `public_spectate = true` 时，未登录客户端可订阅世界 delta。推送内容为全地图实体（无 `is_visible_to` 过滤），但受 `spectate_delay` tick 延迟控制。此推送仅供显示——旁观者无法提交任何指令。

**约束**: World 模式下若 `public_spectate = true`，`spectate_delay` 必须 ≥ 50 tick，防止实时信息泄露破坏 `replay_privacy`。旁观者推送的实体信息受 `replay_privacy` 过滤——`private` 时旁观者仅见地形和公开元数据。

**旁观者可见性限制**：

| 信息类别 | 玩家自身 | 回放 (replay) | 旁观者 (spectator) |
|---------|---------|--------------|-------------------|
| 实体位置/状态（position, hits, owner） | ✅ | ✅ | ✅ |
| drone body parts 组成 | ✅ | ✅ | ✅ |
| 资源持有量（本地 + 全局） | ✅ | ✅（自身） | ❌ |
| drone 环境变量 (`env_vars`) | ✅ | ✅ | ❌ |
| drone 内存内容 | ✅ | ✅ | ❌ |
| 代码版本 / 部署历史 | ✅ | ✅ | ❌ |
| 调试信息 (`swarm_explain_last_tick`) | ✅ | ✅ | ❌ |
| 指令列表（本 tick 提交了什么） | ✅ | ✅ | ❌ |
| 策略指标 (`swarm_profile`) | ✅ | ✅ | ❌ |

旁观者只能看到**世界层面的物理状态**——实体在哪、谁拥有、战斗中。不能看到任何玩家的**内部状态、代码逻辑、调试信息**。回放查看器在观看自身回放时保留完整权限，观看他人回放时等同于旁观者。

### 3.6 调试/回放

| 模式 | 可见性 |
|------|--------|
| **裸追踪** (admin) | 全部 — 所有实体、所有指令、所有状态 |
| **自身回放** (玩家) | `is_visible_to(玩家, tick)` — 玩家实际所见 |
| **公开回放** (Arena 赛后) | 全知视角 — 赛后延迟 ≥100 tick 才公开 |
| **公开回放** (World) | 不公开 — 仅自身回放 |

### 数据分级

| 级别 | 内容 | 谁可见 |
|------|------|--------|
| Public | 排行榜、房间名、Controller 等级 | 所有人 |
| Self | 自身实体、tick 解释、rejection detail | 仅自己 |
| Admin-only | 全量 tick trace、其他玩家指令、world_seed、RNG 状态 | 仅管理员 |
| Delayed | Arena 全知回放 | 赛后 + ≥100 tick |

## 4. 房间 Fog of War

```
房间 R 在 tick T:
  对玩家 P:
    若 P 在房间 R 有视野源:
      visible_entities = R 及相邻房间内所有实体（视野范围内）
    否则:
      visible_entities = 仅房间元数据（拥有者、等级、房间名）
```

失去某房间全部视野的玩家仍能看到：
- 房间 Controller 归属者
- 房间等级
- 房间名

但看不到实体位置、drone 数量、建筑状态。

## 5. 可见性缓存

```
每 tick、每玩家可见性计算一次并缓存。
缓存键: (tick, player_id)
缓存值: HashSet<EntityId>
失效: 下一 tick
```

所有输出面读取此缓存。防止「快照说隐藏但 WebSocket 增量泄露」的 bug。

## 6. 测试

### 6.1 单元测试

```rust
#[test]
fn test_own_entities_always_visible() { ... }
#[test]
fn test_enemy_outside_vision_hidden() { ... }
#[test]
fn test_multiple_vision_sources_union() { ... }
#[test]
fn test_vision_range_boundary() { ... }
```

### 6.2 集成测试

```rust
// 世界设置: 玩家 A 的 drone 在房间 W1N1，玩家 B 的 drone 在 W1N2
// 断言: 玩家 A 的快照仅含 W1N1 实体
// 断言: 玩家 B 的 WS 增量仅含 W1N2 变化
// 断言: 玩家 A 的回放每 tick 仅显示 W1N1 状态
```

### 6.3 泄露检测测试

```rust
// 对每个输出面（snapshot、MCP、WS、REST、replay）:
//   1. 创建含隐藏信息的世界
//   2. 以不该看到这些信息的玩家身份请求输出
//   3. 断言: 隐藏数据不在输出中
```

## 7. 双模式可见性

### World 模式（持久世界）

按上述完整 fog-of-war 规则。房间保留状态。视野跨 tick 持续至失去为止。

### Arena 模式（比赛）

简化可见性：比赛边界内全信息。双方玩家看到整个竞技场。公平竞技禁用 fog-of-war。计时器和得分对观战者可见。全知回放赛后公开。
