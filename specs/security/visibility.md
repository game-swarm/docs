# 统一可见性策略

> 详见 design/engine.md + design/gameplay.md

## 1. 核心原则

**一个函数回答「玩家 P 在 tick T 能看到什么」：**

```rust
fn is_visible_to(entity: &Entity, player_id: PlayerId, tick: u64) -> bool;
```

所有输出面调用此函数。无绕过。不存在「这只是调试数据所以没关系」的例外。

**Shard clipping 先于一切可见性规则**：候选房间必须属于玩家当前权威 shard。位于相邻 shard 的房间、实体、敌对状态和 gameplay effect 一律不可见；migration staged entity 在 Destination Activation 前也不可见。下文“始终可见”和范围规则均只在当前 shard 内成立。

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

 视野来源 | 范围 |
---------|------|
 Drone | 3（默认，取决于身体部件） |
 Spawn | 3 |
 Tower | 3（充能后 6） |
 Observer | 10（激活时） |
 Controller（拥有者，level ≥ 1） | 1 |

### 2.3 中立/敌对实体

```
HOSTILE: 若在任何友好视野源范围内则可见。
```

敌方 drone、中立建筑、地上资源——落入任何视野锥内即可见。

### 2.4 隐藏信息

 数据 | 默认可见性 |
------|-----------|
 其他玩家资源数量 | ❌ 隐藏 |
 其他玩家 Controller 进度 | ❌ 隐藏 |
 其他玩家在建工程 | ✅ 可见（在视野内） |
 其他玩家冷却时间 | ❌ 隐藏 |
 其他玩家疲劳值 | ❌ 隐藏 |
 其他玩家身体部件组成 | ✅ 可见（可观察特征） |
 RNG 种子 | ❌ 赛中/World 始终隐藏；public Arena 仅在赛后 +100 tick 通过 commitment reveal 公开 epoch-0 seed |
 被拒绝指令（其他玩家） | ❌ 隐藏 |
 WASM 模块错误（其他玩家） | ❌ 隐藏 |

### 2.5 市场

```
MARKET: 所有活跃订单对有视野房间的全体玩家可见。订单创建者身份可见。
```

### 2.6 统计与排行榜

```
STATISTICS (World): `swarm_get_world_statistics` 发布非竞争性聚合统计。指标仅包含世界/玩家级安全汇总，例如房间数、drone 数、控制等级进度和公开 arena 结果；不得泄露资源总量、隐藏实体、当前策略、WASM 源码或不可见房间信息。
RANKINGS (Arena/PvE): 仅公开房间或公开 challenge 进入公开竞争榜；私有房间/challenge 只向参与者返回结果。
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
  "actor_context": {"active_drones": [1001], "primary_drone": 1001},
  "entities": [/* is_visible_to 过滤 */],
  "terrain": [/* 所有可见房间的地形 */],
  "resources": [{"name": "Energy", "amount": 5000}],  // [Resource]；Vanilla 默认，仅自身
  "events": [],
  "truncated": false,           // 是否因 256KB 限制被截断
  "messages": [],
  "omitted_categories": {
    "entities": "0",
    "terrain": "0",
    "resources": "0",
    "events": "0",
    "messages": "0"
  },
  "omitted_messages": "0"
}
```

`tick` 是当前 COLLECT 阶段开始时的 snapshot tick；MCP 与 WASM 使用同一值和同一结构。

`over_budget` 是 optional field，只在 deterministic minimal snapshot path 出现且值为 `true`；普通完整/截断 snapshot（包括上例）必须省略。

> **WASM 作者注意**：`snapshot` 是本 tick COLLECT 阶段开始时的世界状态**快照**，不是"实时"视图。在同一 tick 内，其他玩家的 action 不会反映在该 snapshot 中；COMMIT 成功后的变化会在同一 tick 的 BROADCAST 作为 WebSocket delta 推送，并首次进入下一 tick 的 perception snapshot。这意味着：WASM 基于 snapshot 做出决策后，世界可能已经变化。

### 3.2 MCP 工具

| 工具 | 可见性过滤 |
|------|-----------|
| `swarm_get_snapshot` | 完整 `is_visible_to` + shard clipping |
| `swarm_list_rooms` / `swarm_get_room` | 仅当前 shard 内、玩家有视野的房间 |
| `swarm_list_drones` / `swarm_get_drone` | 仅当 `is_visible_to` 返回 true 或为当前 shard 内自身实体；`overload_pressure` 按贡献者可见性过滤 |
| `swarm_get_structure` | 仅可见结构；cooldown 为 owner-only；`overload_pressure` 按贡献者可见性过滤 |

`swarm_get_drone` 的 `code_hash` 与 `fuel_used` 是 owner-only fields：非 owner 即使可见 drone，也必须省略；代码内容继续只允许 `swarm_get_code` owner scope，fuel profiling 继续只允许 admin/debug surfaces。

`overload_pressure` 的普通查询形状为 `{total?: u32, contributions:[{source_entity_id:EntityId, amount:u32}], tick_snapshot:u64}`。目标 owner 始终可见 `total`（即使所有 source hidden，`contributions` 可为空）；contributing attacker 可见 `total` 与自己的 contribution。contributions 只包含 caller 自己的来源加 visible sources。第三方只获得 visible-source contributions 且没有 `total`；仅当 caller 既非 target owner/contributor 且没有 visible contribution 时，字段整体省略。

玩家可见拒绝不泄露目标存在性：target-side absent、invisible、type-ineligible、target cooldown 与 protected target `SpawningGrace` 均返回 `NotVisibleOrNotFound`，不得带目标详情或剩余 tick。source/attacker-owned cooldown 仍返回 `CooldownActive`。

### 3.3 WebSocket 增量

```
每 tick 推送增量: 仅包含变更 且 is_visible_to(subscriber) 为 true 的实体。
```

### 3.4 Gateway 查询接口

Gateway 当前不暴露独立的 room/map REST 路由。房间、实体与地形查询通过 MCP 工具进入 Engine，并执行本节定义的 `is_visible_to` 与 terrain 可见性规则。

### 3.5 旁观者视图 (Spectator View)

**两层分离**：引擎始终按 `is_visible_to` 计算 drone 的 snapshot（游戏公平性），但玩家/旁观者的「摄像头」可以有不同的可见范围（观战体验）。

| 模式 | WASM + MCP `swarm_get_snapshot` | 人类 display channel（非 MCP） | WebSocket 旁观 |
|------|---------------------------------|-------------------------------|---------------|
| `player_view = "drone"` | `is_visible_to(player)` 过滤 | 同 snapshot | 按 `replay_privacy` |
| `player_view = "full"` | `is_visible_to(player)` 过滤 | 全地图 display | 按 `replay_privacy`，不继承 player_view |
| `player_view = "allied"` | `is_visible_to(player)` 过滤 | 所有友方 drone 聚合 display | 按 `replay_privacy` |

**关键不变量**：WASM `tick()` 与 MCP `swarm_get_snapshot` 始终返回同一份 `is_visible_to(player)` 感知快照。`player_view` 只影响独立的人类 display channel；普通 MCP query 不因 `player_view=full` 获得额外世界状态。

**旁观者 WebSocket**：当 `public_spectate = true` 时，未登录客户端可订阅受 `spectate_delay` 约束的世界 delta。`replay_privacy=public` 才推送延迟全地图；其他 privacy 值按受众过滤，`private` 只含地形与公共元数据。旁观者无法提交任何指令。

**约束**: 若 `public_spectate = true`，`spectate_delay` 必须 ≥ 100 tick，防止实时信息泄露破坏 `replay_privacy`。旁观者推送的实体信息受 `replay_privacy` 过滤——`private` 时旁观者仅见地形和公开元数据。

**旁观者可见性限制**：

 信息类别 | 玩家自身 | 回放 (replay) | 旁观者 (spectator) |
---------|---------|--------------|-------------------|
 实体位置/状态（position, hits, owner） | ✅ | ✅ | ✅ |
 drone body parts 组成 | ✅ | ✅ | ✅ |
 资源持有量（本地 + 全局） | ✅ | ✅（自身） | ❌ |
 drone 环境变量 (`env_vars`) | ✅ | ✅ | ❌ |
 drone 内存内容 | ✅ | ✅ | ❌ |
 代码版本 / 部署历史 | ✅ | ✅ | ❌ |
 调试信息 (`swarm_explain_last_tick`) | ✅ | ✅ | ❌ |
 指令列表（本 tick 提交了什么） | ✅ | ✅ | ❌ |
 策略指标 (`swarm_profile`) | ✅ | ✅ | ❌ |

旁观者只能看到**世界层面的物理状态**——实体在哪、谁拥有、战斗中。不能看到任何玩家的**内部状态、代码逻辑、调试信息**。回放查看器在观看自身回放时保留完整权限，观看他人回放时等同于旁观者。

### 3.6 调试/回放

 模式 | 可见性 |
------|--------|
 **裸追踪** (admin) | 全部 — 所有实体、所有指令、所有状态 |
 **自身回放** (玩家) | `is_visible_to(玩家, tick)` — 玩家实际所见 |
 **Arena 赛后回放** | public room 才公开全知物理世界视角；unlisted/private room 仅参与者/房主；始终排除 PlayerMessage、debug、源码与玩家私有状态 |
 **公开回放** (World) | 不公开 — 仅自身回放 |

### 数据分级

 级别 | 内容 | 谁可见 |
------|------|--------|
 Public | 公开 Arena/PvE 榜单、公开房间名、Controller 等级 | 所有人 |
 Self | 自身实体、tick 解释、rejection detail | 仅自己 |
 Admin-only | 全量 tick trace、其他玩家指令、World/active-match seed、RNG 状态 | 仅管理员；public Arena 赛后 commitment reveal 例外 |
 Delayed | Public Arena room 的全知物理世界回放（不含消息/debug/私有状态） | 赛后 + ≥100 tick |

## 4. 房间 Fog of War

```
房间 R 在 tick T:
  对玩家 P:
    若 P 在房间 R 有视野源:
      visible_entities = R 及同一 shard 相邻房间内所有实体（视野范围内）
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

COLLECT-based WASM/MCP 输出读取此 snapshot visibility cache。WebSocket BROADCAST 在 COMMIT 后基于 committed state 重新计算 `broadcast_visibility(tick, subscriber)`，只推送该 committed view 可见的 delta；不得复用 stale snapshot cache，也不得把 delta 伪装成 perception snapshot。

### 各输出面 Tick 基准

COLLECT-based 输出在 `tick N` 读取 **COLLECT 阶段开始时的快照**（即 `snapshot.tick == N`）；WebSocket delta 是明确的 post-commit 例外：

| 输出面 | tick 基准 | 过滤函数 | 备注 |
|--------|:--:|---------|------|
| WASM `tick(snapshot)` | N | `is_visible_to(player, N)` | snapshot.tick == N |
| MCP `swarm_get_snapshot` | N | `is_visible_to(player, N)` | 与 WASM tick 同一份快照 |
| WASM `host_get_objects_in_range` | N | `is_visible_to(player, N)` | 同一快照的子集查询 |
| MCP `swarm_explain_last_tick` | N-1 | 仅自身 | 解释上一 tick 的执行结果 |
| MCP `swarm_get_replay` | N | `is_visible_to(player, tick)` | 每帧按该 tick 的视野重建 |
| WebSocket delta | N committed | `broadcast_visibility(subscriber, committed N)` | COMMIT 后同 tick BROADCAST；不是 COLLECT snapshot；变化进入 snapshot N+1 |
| Replay (自身) | 历史 tick | `is_visible_to(player, tick)` | 逐 tick 重建视野 |
| Replay (Arena 赛后) | 历史 tick + ≥100 延迟 | public room 才公开全知物理世界；private/unlisted 仅参与者/房主 | 仅赛后可用 |
| Spectator WebSocket | N - spectate_delay | 按 `replay_privacy`；仅 `public` 为全地图 | 仅 `public_spectate=true` 时可用 |

## 6. 特殊攻击可见性规则

特殊攻击从 attacker 和 target 两侧的可观察性必须明确——防止信息泄露形成 oracle。

### 6.1 Overload 可观察性

Overload 反馈通过 `OverloadPressure` ECS 组件暴露（详见 `design/gameplay.md` §Overload 反馈透明度）。

```
attacker 视角（执行 Overload 的玩家）:
  - 可见: 是否成功执行（无拒绝码） + target_player_id
  - 可见: 自己的 contribution 量（amount） + 目标当前总压力（total）
  - 不可见: target 的 actual_fuel（仅知 target 在当前世界中有可见实体）
  - 不可见: 其他攻击者的 contribution（除非其他攻击者对当前玩家可见）

target 视角（被 Overload 的玩家）:
  - 可见: 自身 snapshot / SDK state 中的 fuel 变化
  - 可见: 自身 drone 因 fuel 不足未执行 action（MCP `swarm_explain_last_tick`）
  - 可见: OverloadPressure.total（当前累积压力） + 每个可见 source 的 contribution
  - 不可见: 不可见 source 的 identity 和 contribution（不在 contribution 列表中暴露）
```

不可见的攻击者不在 `contributions` 列表中暴露，防止通过 Overload 反馈反向定位隐身单位。`total` 字段始终对 target 可见，因为 target 可以观察自身的 fuel 下降来间接感知压力。

### 6.2 Hack 可观察性

```
attacker 视角:
  - 可见: Hack 是否成功执行（无拒绝码） + target_entity_id
  - 可见: Hack 施加后，target entity 的 owner 暂不变（5 tick 后夺取）
  - 不可见: target 玩家的 WASM 是否检测到 Hack（target 可通过 entity.owner 自查）

target 视角:
  - 可见: 自身 entity 上存在 `Hacked { by: player_id, remaining: 5 }` 状态（MCP `swarm_get_drone`）
  - 可见: 被 Hack 的 entity 无法执行部分命令（拒绝码见 specs/core/command-validation）
  - 不可见: attacker 的后续意图（夺取后如何使用）
```

### 6.3 通用不变量

所有特殊攻击遵循：
- attacker 不可通过特殊攻击的返回码区分"目标不存在"与"目标不可见"——统一返回 `NotVisibleOrNotFound`
- attacker 不可通过特殊攻击的返回码推断目标的资源/状态内部值
- target 可通过自身数据看到特殊攻击的**效果**（HP 变化、状态标记、fuel 变化），但不可看到**攻击者身份**——除非攻击者实体在 target 视野内

## 7. 测试

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

## 8. 双模式可见性

### World 模式（持久世界）

按上述完整 fog-of-war 规则。房间保留状态。视野跨 tick 持续至失去为止。

### Arena 模式（比赛）

Arena 参与者使用与 World 相同的 drone fog-of-war / drone 感知规则。计时器和得分对观战者可见；观众和赛后 replay 可使用延迟全图 spectator view。全信息 Arena 是 room config 变体选项，不是默认。

---

## 9. 可见性配置

可见性分两层：**drone 感知**（影响游戏公平性）和**玩家视野**（影响观战体验）。

### 8.1 配置项（WorldConfig.visibility）

| 规则 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `fog_of_war` | bool | true | drone 的 WASM `tick()` snapshot 是否受可见性限制。true = drone 只能看到感知范围内的实体；false = snapshot 包含全地图（教学/合作世界） |
| `player_view` | enum | `drone` | 玩家视野模式 |
| `public_spectate` | bool | World `false` / Arena `true` | 未登录用户延迟旁观 |
| `spectate_delay` | u32 | 100 | 旁观延迟（tick）。`public_spectate=true` 时强制最低 100（`validate_config` 拒绝 < 100）；`false` 时忽略 |
| `replay_privacy` | enum | World `private` / Arena `inherit_room_visibility` | Arena public room 公开；unlisted/private room 限参与者/房主 |

### 8.2 PlayerView 模式

 值 | 说明 |
-----|------|
 `drone` | 玩家只能看到自己 drone 所见。默认模式 |
 `full` | 玩家实时看到全地图，无视 drone 感知范围。教学/合作世界使用 |
 `allied` | 看到所有同阵营 drone 的聚合视野 |

### 8.3 ReplayPrivacy 等级

 值 | 可见范围 |
-----|---------|
 `private` | 仅自身 |
 `allies` | 同阵营可看 |
 `world` | 同世界玩家可看 |
 `public` | 任何人（含未登录）。Arena 赛后默认 |

### 8.4 组合场景

 场景 | fog_of_war | player_view | 效果 |
------|-----------|-------------|------|
 标准 World | true | drone | drone 感知有限，玩家只看自己 drone 所见 |
 教学世界 | false | full | 新手看到全地图，drone 也能感知全图 |
 竞技观战 | true | drone | drone 公平受限，观众通过 `public_spectate` + `spectate_delay=100` 看延迟全图 |
 合作 PvE | true | allied | drone 各自感知，但玩家看到所有友方聚合视野 |

### 8.5 配置示例（world.toml）

```toml
[visibility]
fog_of_war = true
player_view = "drone"
public_spectate = false
spectate_delay = 100
```

---

## 10. Oracle 防线 —— 跨接口信息泄露闭合

以下规则确保所有管理/调试/查询接口不会绕过 `is_visible_to` 形成 oracle。

### 10.1 MCP 查询面约束

| 条件 | `player_view` | MCP read/query 可见范围 |
|------|:--:|------|
| competitive world (fog_of_war=true) | `drone` | = WASM snapshot（`is_visible_to` 过滤） |
| competitive world | `full` | = WASM snapshot；`full` 只改变 human display |
| non-competitive (tutorial/coop/sandbox) | `full` | = WASM snapshot；若 `fog_of_war=false` 则 snapshot 本身为全图 |

**规则**：MCP agent 永远看到与 WASM `tick(snapshot)` 相同的范围；`player_view` 不参与 MCP authorization。

### 10.2 `omitted_categories` 脱敏

目标设计：玩家需要知道快照是否发生截断，但不能通过精确省略数量形成 oracle。

**规则**：`omitted_categories` 的每个类别值为分桶枚举：

| 实际丢弃数 | 玩家可见值 |
|:--|:--|
| 0 | `0`（无截断） |
| 1-10 | `"few"` |
| 11-50 | `"some"` |
| 51-200 | `"many"` |
| >200 | `"extreme"` |

`total_visible_count` 同样分桶。`truncated` 布尔值保留。精确计数只允许进入 admin/debug 内部 trace，不进入玩家 WASM snapshot、MCP 普通查询或公开 replay。

### 10.3 dry_run / simulate / explain_last_tick 脱敏

| 接口 | 脱敏策略 |
|------|---------|
| `swarm_dry_run` | 仅返回 `Ok` / `RejectionReason`（等价脱敏版）——不返回被拒绝指令的具体目标信息 |
| `swarm_simulate` | 模拟结果仅包含自身实体状态变化——不包含其他玩家的实体、资源、指令 |
| `swarm_explain_last_tick` | 仅解释自身 drone 的执行结果——不暴露其他玩家的 action、rejection detail、资源变化 |

### 10.4 特殊攻击拒绝码等价策略

所有特殊攻击（Overload/Hack/Drain/Debilitate/Disrupt/Fortify/Leech/Fabricate）的不可见目标拒绝码统一为以下等价类：

| 实际情况 | 返回码 |
|---------|--------|
| 目标不存在 | `NotVisibleOrNotFound` |
| 目标存在但不可见 | `NotVisibleOrNotFound` |
| 目标不可被该攻击类型指定 | `NotVisibleOrNotFound` |
| 目标在冷却中（per-target global cooldown） | `NotVisibleOrNotFound` |
| 攻击者自身条件不足（fatigue/cooldown/资源） | `CooldownActive` / `InsufficientResource`（可附自身 `debug_detail`） |

攻击者**永远无法**通过拒绝码区分"目标不存在"、"目标不可见"、"目标不符合该攻击类型"或目标级冷却——这些目标侧失败统一返回 `NotVisibleOrNotFound`。仅攻击者自身的 canonical 状态码可暴露自身信息（合法——玩家已知自身状态）。
