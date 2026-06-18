# Swarm API Registry — 权威事实源

> **本文档是 Swarm 所有 API 合约的单一权威来源**。CommandAction、RejectionReason、MCP Tools、Host Functions、容量限制均以此文档为准。其他文档只能引用，不得重新声明可冲突的表格或列表。

## 原则

1. **单事实源**：每类合同只有一个权威定义。设计文档 (design/)、规范 (specs/) 引用本文档，不自行定义。
2. **机器可读优先**：所有定义使用结构化表格，可由 CI 自动校验跨文件一致性。
3. **版本化**：每次 API 变更更新 `api_version`，TickTrace 记录 `api_version`。
4. **完整闭合**：新增指令/错误码/工具/函数必须在此注册，未注册的 CI 拒绝。

**当前 API 版本**: `0.1.0`

---

## 1. CommandAction

Core CommandAction 是 WASM tick() 输出的 CommandIntent 中的 action type。所有 Vanilla action 定义于此。World Action Manifest 通过 `custom_actions` 扩展，但核心集合不变。

### 1.1 核心指令 (11)

| # | Action | 参数 | 说明 |
|---|--------|------|------|
| 1 | `Move` | `direction: Direction4` | 向 N/S/E/W 移动一格 |
| 2 | `Harvest` | `target_id: EntityId` | 采集资源 |
| 3 | `Transfer` | `target_id: EntityId, resource: ResourceType, amount: u32` | 本地转移资源 |
| 4 | `Withdraw` | `target_id: EntityId, resource: ResourceType, amount: u32` | 从建筑提取资源 |
| 5 | `Build` | `structure_type: StructureType, x: i32, y: i32` | 建造建筑 |
| 6 | `Attack` | `target_id: EntityId` | 近战攻击 |
| 7 | `RangedAttack` | `target_id: EntityId` | 远程攻击 |
| 8 | `Heal` | `target_id: EntityId` | 修理/治疗 |
| 9 | `Spawn` | `body_parts: [BodyPart], spawn_id: SpawnId` | 生成 drone |
| 10 | `Recycle` | `target_id: EntityId` | 回收 drone/建筑 |
| 11 | `ClaimController` | `target_id: EntityId` | 占领控制器 |

### 1.2 Global Storage 指令 (2)

| # | Action | 参数 | 说明 |
|---|--------|------|------|
| 12 | `TransferToGlobal` | `resource: ResourceType, amount: u32` | 资源存入全局仓库 |
| 13 | `TransferFromGlobal` | `resource: ResourceType, amount: u32` | 从全局仓库提取 |

### 1.3 特殊攻击 (6)

| # | Action | 参数 | 说明 |
|---|--------|------|------|
| 14 | `Hack` | `target_id: EntityId` | 5 阶段入侵 |
| 15 | `Drain` | `target_id: EntityId` | 持续吸取资源 |
| 16 | `Overload` | `target_id: EntityId` | 削减目标 fuel budget |
| 17 | `Debilitate` | `target_id: EntityId` | 降低目标效率 |
| 18 | `Disrupt` | `target_id: EntityId` | 打断目标操作 |
| 19 | `Fortify` | `target_id: EntityId` | 强化自身防御 |

### 1.4 Custom Actions

`Leech` 和 `Fabricate` 为 World Action Manifest 中的 `custom_actions`，非 Core enum 成员。每个 custom action 在 manifest 中声明 `action_id`、参数 schema、validator、handler。TickTrace 记录 `world_action_manifest_hash` 以确保 replay 确定性。

---

## 2. RejectionReason

所有指令拒绝原因在此注册。**共计 35 个变体**，覆盖管线级、子系统级、MCP 级三层。

### 2.1 管线级 (Pipeline) — 不计入 enum，统一前置处理

| 错误码 | 含义 |
|--------|------|
| `InvalidJson` | JSON 解析失败 |
| `SchemaViolation` | 指令 schema 不符合 IDL |

### 2.2 验证级 (Validation)

| # | RejectionReason | 含义 |
|---|-----------------|------|
| 1 | `ObjectNotFound` | 目标实体不存在 |
| 2 | `NotOwner` | 不是目标实体的所有者 |
| 3 | `InsufficientResource` | 资源不足 |
| 4 | `OutOfRange` | 目标超出操作距离 |
| 5 | `NotStructure` | 目标不是建筑 |
| 6 | `NotController` | 目标不是控制器 |
| 7 | `NotVisibleOrNotFound` | 目标不可见或不存在（合并，防止 oracle） |
| 8 | `TargetNotVisible` | 目标不在视野内 |
| 9 | `SpawnOnCooldown` | Spawn 冷却中 |
| 10 | `RoomDroneCapReached` | 房间 drone 上限 |
| 11 | `AuthContextInvalid` | 认证上下文无效 |
| 12 | `CooldownActive` | 操作冷却中 |
| 13 | `InvalidDirection` | 方向无效（4 方向之外） |
| 14 | `PositionOccupied` | 目标位置被占用 |
| 15 | `ConstructionLimitReached` | 建筑数量达上限 |
| 16 | `SafeModeActive` | 目标处于 safe mode |
| 17 | `TargetOverloadCooldown` | 目标有过载冷却 |
| 18 | `TargetFortifyCooldown` | 目标有强化冷却 |
| 19 | `NotEnoughBodyParts` | body parts 不足 |
| 20 | `InvalidBodyPart` | 无效 body part |
| 21 | `InvalidStructureType` | 无效建筑类型 |
| 22 | `InvalidResourceType` | 无效资源类型 |
| 23 | `SourceNotAllowed` | 指令来源不允许此操作 |
| 24 | `UnknownAction` | 未知 action type |
| 25 | `GlobalStorageDisabled` | 全局仓库未启用 |
| 26 | `TransferInProgress` | 转移进行中 |

### 2.3 MCP 层

| # | RejectionReason | 含义 |
|---|-----------------|------|
| 27 | `RateLimited` | 频率限制 |
| 28 | `InvalidCertificate` | 证书无效 |
| 29 | `NotAuthorized` | 无权限 |

### 2.4 运行时级 (Runtime)

| # | RejectionReason | 含义 |
|---|-----------------|------|
| 30 | `FuelExhausted` | WASM fuel 耗尽 |
| 31 | `TimeoutExceeded` | WASM 执行超时 |
| 32 | `SnapshotOverBudget` | 快照超过大小预算 |
| 33 | `CommandBufferFull` | 指令缓冲区满 |
| 34 | `ServerOverloaded` | 服务器过载降级 |
| 35 | `InternalError` | 引擎内部错误 |

### 命名规范

- 统一使用 **`InsufficientResource`**（单数），废弃 `InsufficientResources`/`InsufficientEnergy`
- 统一使用 **`ObjectNotFound`**，废弃 `TargetNotFound`
- 统一使用 **`CooldownActive`**（通用冷却），保留 `SpawnOnCooldown` 为 Spawn 专属
- **`NotVisibleOrNotFound`** 为安全合并码，防止通过不同错误码推断实体存在性
- **`NotAuthorized`** 仅用于 MCP 层认证失败；validation 层用 `NotOwner`

---

## 3. MCP Tools

### 3.1 工具清单 (46)

| 分类 | 工具名 | Input Schema | Output Schema | Rate Limit |
|------|--------|-------------|---------------|------------|
| **Onboarding** | `swarm_get_info` | `{}` | `{version, tick_rate, world_name, player_count}` | 100/min |
| | `swarm_get_snapshot` | `{player_id}` | `{tick, entities, terrain, resources, truncated, omitted_count}` | 1/tick |
| | `swarm_get_resources` | `{player_id}` | `{resources, storage, income_rate}` | 10/tick |
| | `swarm_list_rooms` | `{player_id}` | `{rooms: [{id, level, controller_level}]}` | 10/tick |
| | `swarm_get_room` | `{room_id}` | `{terrain, entities, resources, controller}` | 10/tick |
| | `swarm_list_drones` | `{player_id}` | `{drones: [{id, room, body, lifespan, status}]}` | 10/tick |
| | `swarm_get_drone` | `{drone_id}` | `{id, room, body, lifespan, status, code_hash, fuel_used}` | 10/tick |
| | `swarm_get_code` | `{drone_id}` | `{code, hash, language, size, last_deployed}` | 20/tick |
| **Play** | `swarm_get_leaderboard` | `{scope, limit}` | `{entries: [{player, gcl, rooms, drones}]}` | 5/tick |
| | `swarm_get_replay` | `{tick_range, player_id}` | `{ticks, entities, commands, events}` | 5/min |
| | `swarm_get_events` | `{room_id, tick_range}` | `{events: [{tick, type, data}]}` | 10/tick |
| | `swarm_get_terrain` | `{room_id, bounds}` | `{terrain_grid, size}` | — (host fn only) |
| | `swarm_get_path` | `{from, to, player_id}` | `{path, distance, cost}` | — (host fn only) |
| | `swarm_get_visibility` | `{player_id}` | `{visible_rooms, visible_entities}` | 10/tick |
| | `swarm_list_controllers` | `{player_id}` | `{controllers: [{room, level, progress, owner}]}` | 10/tick |
| | `swarm_get_controller` | `{controller_id}` | `{room, level, progress, owner, downgrade_timer}` | 10/tick |
| | `swarm_list_structures` | `{room_id, player_id}` | `{structures: [{id, type, pos, hits}]}` | 10/tick |
| | `swarm_get_structure` | `{structure_id}` | `{id, type, pos, hits, capacity, cooldown}` | 10/tick |
| | `swarm_get_resources` | `{player_id}` | (见 Onboarding) | 10/tick |
| | `swarm_list_market_orders` | `{room_id}` | `{orders: [{id, type, resource, amount, price}]}` | 10/tick |
| | `swarm_get_messages` | `{drone_id}` | `{messages: [{from, content, tick}]}` | 10/tick |
| | `swarm_get_economy` | `{player_id}` | `{income, expenses, storage_tax, maintenance}` | 10/tick |
| | `swarm_get_drone_efficiency` | `{drone_id}` | `{efficiency, factors}` | 10/tick |
| | `swarm_get_economy_trend` | `{player_id, ticks}` | `{trend: [{tick, metric, value}]}` | 10/tick |
| **Deploy** | `swarm_deploy` | `{player_id, drone_id, wasm_bytes, metadata}` | `{deploy_id, accepted, validation_errors}` | 10/h |
| | `swarm_validate_module` | `{wasm_bytes}` | `{valid, errors, fuel_estimate}` | 10/h |
| | `swarm_get_deploy_status` | `{deploy_id}` | `{status, errors, deployed_at}` | 20/tick |
| | `swarm_list_deployments` | `{player_id}` | `{deployments: [{id, drone_id, status, at}]}` | 20/tick |
| | `swarm_get_world_config` | `{}` | `{rules, mods, limits, tick_rate}` | 10/tick |
| | `swarm_get_world_rules` | `{}` | `{rule_modules, parameters, version}` | 10/tick |
| **Debug** | `swarm_get_tick_trace` | `{tick}` | `{commands, state_diff, rejections, metrics}` | 30/tick |
| | `swarm_get_engine_stats` | `{}` | `{tick_duration, player_count, memory, cpu, sandbox_stats}` | 30/tick |
| | `swarm_get_sandbox_profile` | `{drone_id}` | `{fuel_used, host_calls, memory_peak, execution_time}` | 30/tick |
| | `swarm_list_errors` | `{player_id, limit}` | `{errors: [{tick, drone, code, detail}]}` | 20/tick |
| | `swarm_get_state_checksum` | `{tick}` | `{checksum, algorithm, scope}` | 30/tick |
| | `swarm_simulate` | `{commands, assumptions}` | `{trace, authoritative: false, assumptions, confidence}` | 50/tick |
| | `swarm_dry_run` | `{wasm_bytes, tick_count}` | `{trace, fuel_used, errors}` | 50/tick |
| **Admin** | `swarm_admin_challenge` | `{challenge, signature}` | `{granted, scope, expiry}` | 5/min |
| | `swarm_admin_set_world_config` | `{key, value}` | `{accepted, applied_at}` | 10/h |
| | `swarm_admin_rollback` | `{target_tick}` | `{rollback_id, state}` | 5/h |
| | `swarm_admin_ban_player` | `{player_id, reason, duration}` | `{banned, expiry}` | 10/h |
| | `swarm_admin_force_gc` | `{scope}` | `{freed_bytes, duration}` | 5/h |
| | `swarm_admin_get_audit_log` | `{scope, limit}` | `{entries: [{timestamp, actor, action, detail}]}` | 30/tick |
| **SDK** | `swarm_sdk_fetch` | `{language, include_examples}` | `{sdk_code, type_definitions, examples, abi_version, min_engine_version}` | 5/min |
| **Resources** | `resources/list` | `{}` | `{resources: [{type, name, category}]}` | 50/tick |
| | `resources/read` | `{resource_type}` | `{type, name, category, base_value, rarity}` | 50/tick |

### 3.2 Capability Profiles

工具按 profile 分组，控制 MCP 客户端的能力面：

| Profile | 包含分类 | 默认分配 |
|---------|---------|---------|
| `onboarding` | Onboarding, SDK, Resources | 所有已认证客户端 |
| `play` | Play, Economy | World 玩家，Arena spectator |
| `deploy` | Deploy | 所有已认证客户端 |
| `debug` | Debug | 开发者 / Arena host |
| `admin` | Admin | 服主 / Admin 证书 |

### 3.3 通用 Rate Limit

MCP 层统一 rate limit（非 source-level 限流）：

- 读类 (query)：50/tick
- 调试类：30/tick
- 开发辅助类：20/tick
- 部署类：10/h
- 管理类：10/h
- SDK 获取：5/min

---

## 4. Host Functions

WASM 模块通过 host function import 调用引擎服务。以下为权威签名与限制。

### 4.1 函数签名

| # | 函数 | 签名 | 只读 | 说明 |
|---|------|------|:---:|------|
| 1 | `host_get_terrain` | `(room_id: u32, out_ptr: i32, out_len: i32) -> i32` | ✅ | 获取房间地形 |
| 2 | `host_get_objects_in_range` | `(x: i32, y: i32, range: u32, out_ptr: i32, out_len: i32) -> i32` | ✅ | 获取范围内实体 |
| 3 | `host_path_find` | `(from_x: i32, from_y: i32, to_x: i32, to_y: i32, opts_ptr: i32, opts_len: i32, out_ptr: i32, out_len: i32) -> i32` | ✅ | A* 寻路 |
| 4 | `host_get_world_config` | `(key_ptr: i32, key_len: i32, out_ptr: i32, out_len: i32) -> i32` | ✅ | 读取世界配置 |
| 5 | `host_get_world_rules` | `(rule_id_ptr: i32, rule_id_len: i32, out_ptr: i32, out_len: i32) -> i32` | ✅ | 读取规则模块 |

### 4.2 调用预算

| 限制项 | 值 |
|--------|-----|
| Host call 总预算 | **1,000/tick/player** |
| `host_path_find` 上限 | **10/tick** |
| `host_get_objects_in_range` 上限 | **5/tick** |
| `host_get_world_config` 上限 | **5/tick** |
| `host_get_world_rules` 上限 | **1/tick** |
| `host_get_terrain` | 计入总预算，无单独上限 |

### 4.3 输出上限

| 函数 | 最大输出 |
|------|---------|
| `host_path_find` | **8 KB** |
| `host_get_objects_in_range` | **64 KB** |
| `host_get_world_config` | **16 KB** |
| `host_get_world_rules` | **16 KB** |
| `host_get_terrain` | **8 KB** |

### 4.4 Per-Call Fuel 成本

| 函数 | 基础 fuel | 增量 |
|------|----------|------|
| `host_get_terrain` | 500 | — |
| `host_get_objects_in_range` | 2000 | +100/entity |
| `host_path_find` | 500 × nodes | +200 × edges |
| `host_get_world_config` | 1000 | — |
| `host_get_world_rules` | 1000 | — |

### 4.5 Host Function ABI 错误优先级

当多个错误条件同时满足时，按以下优先级返回：

```
1. Memory bounds (out_ptr/out_len 越界)        → 返回 -1 (ERR_MEMORY_BOUNDS)
2. ABI version / schema mismatch                → 返回 -2 (ERR_ABI_VERSION)
3. Visibility redaction (实体不可见)             → 返回 -3 (ERR_NOT_VISIBLE)
4. Per-call budget exhausted                    → 返回 -4 (ERR_BUDGET_EXHAUSTED)
5. Per-player budget exhausted                  → 返回 -5 (ERR_PLAYER_BUDGET)
6. Global budget exhausted                      → 返回 -6 (ERR_GLOBAL_BUDGET)
7. Function-specific validation failure         → 返回 -7 (ERR_VALIDATION)
8. Output size exceeded                         → 返回 -8 (ERR_OUTPUT_SIZE)
9. Timeout (仅在线执行，replay 不重跑 COLLECT)    → 返回 -9 (ERR_TIMEOUT)
```

---

## 5. 全局容量限制

以下数值为权威上限。所有其他文档引用此处，不得重新声明。

| 参数 | 值 | 说明 |
|------|-----|------|
| **Commands/player/tick** | **100** | per-player 最大指令数 |
| **Per-player drone cap** | **500** | (world.toml 可调) |
| **Global drone cap** | **10,000** | 全局活跃 drone 上限 |
| **Global entity cap** | **50,000** | 全局实体上限 |
| **Drone lifespan** | **1500 tick** | 默认值 |
| **MAX_BODY_PARTS** | **50** | 每 drone 最大部件数 |
| **MAX_CONSTRUCTION_SITES** | **100** | 全局在建上限 |
| **Safe mode duration** | **500 tick** | 默认值 |
| **Reservation timeout** | **1000 tick** | 房间保留超时 |
| **Downgrade timer** | **5000 tick** | 控制器降级倒计时 |
| **Global storage capacity** | **1,000,000** 单位 | (world.toml 可调) |
| **WASM 内存上限** | **128 MB** | cgroup 进程级；WASM 线性内存 64MB |
| **Sandbox CPU** | **cpu.max = 250000 3000000** | 每 3s 周期 0.25s |
| **Per-player sandbox deadline** | **2500ms** | World 模式 |
| **MCP simulate max_ticks** | **100** | 模拟最大 tick 数 |
| **MCP simulate max_entities** | **1000** | 模拟最大实体数 |
| **Pathfinding budget** | **100,000 explored nodes/tick** | 引擎全局；per-player 10 次调用 |
| **Pathfinding result path** | **500 nodes max** | 返回路径最大长度 |
| **TickTrace 保留** | **7d (hot) / 30d (warm) / 180d (cold)** | 分级保留 |
| **Replay keyframe 间隔** | **K=100 tick** | keyframe 写入频率 |
| **code_update_cooldown** | **5 tick** (World 最小) | world.toml 配置 |

---

## 6. TickTrace Envelope

Replay 确定性依赖 TickInputEnvelope 的完整性。以下字段为权威定义。

| 字段 | 类型 | 说明 |
|------|------|------|
| `api_version` | `u32` | API registry 版本 |
| `module_hash` | `[u8; 32]` | WASM 模块 Blak3 hash |
| `wasmtime_version` | `string` | Wasmtime 引擎版本 |
| `effective_tick` | `u64` | 有效 tick 编号 |
| `wasm_status` | `enum` | WASM 执行结果 |
| `snapshot_hash` | `[u8; 32]` | 输入快照 hash |
| `commands_hash` | `[u8; 32]` | 输出指令 hash |
| `deploy_events` | `[DeployEvent]` | 部署事件列表 |
| `rollback_events` | `[RollbackEvent]` | 回滚事件列表 |
| `admin_events` | `[AdminEvent]` | 管理事件列表 |
| `world_config_hash` | `[u8; 32]` | 世界配置 hash |
| `mods_lock_hash` | `[u8; 32]` | 规则模块锁定 hash |
| `engine_abi_version` | `u32` | 引擎 ABI 版本 |
| `core_idl_version` | `u32` | Core IDL 版本 |
| `world_action_manifest_hash` | `[u8; 32]` | World Action Manifest hash |
| `validator_version` | `u32` | 验证器版本 |
| `rejection_reason_registry_version` | `u32` | RejectionReason 注册表版本 |
| `system_manifest_hash` | `[u8; 32]` | Phase 2b System Manifest hash |
| `limits_manifest_hash` | `[u8; 32]` | Limits Manifest hash |
| `host_abi_version` | `u32` | Host Function ABI 版本 |
| `canonical_codec_version` | `u32` | Canonical Codec 版本 |
| `visibility_truncation_version` | `u32` | Visibility/Truncation 算法版本 |

---

## 7. Direction4 枚举

Move 指令使用 4 方向：

```
North = 0
South = 1
East  = 2
West  = 3
```

8 方向（含 NE/NW/SE/SW）为 Future RFC，不在当前核心定义中。

---

## 8. SwarmError JSON-RPC Envelope

MCP/API 错误统一格式：

```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": "RejectionReason",
    "message": "Human-readable detail (max 256 chars)",
    "data": {
      "command_index": 3,
      "rejection_detail": "max 512 bytes"
    }
  },
  "id": "<request_id>"
}
```

MCP 共享错误码 `-32000` 保留给未分类内部错误，具体错误以 `error.code` 字符串为准。

---

## 变更记录

| 版本 | 日期 | 变更 |
|------|------|------|
| 0.1.0 | 2026-06-18 | R15 B1+B4+H1 修复：初次建立权威注册表。统一 RejectionReason (35 变体)、CommandAction (19 指令，含 11 核心+2 Global+6 特殊)、MCP Tools (46)、Host Functions (5)、容量限制 (25 参数)、TickTrace Envelope (22 字段)、Direction4、错误格式。 |
