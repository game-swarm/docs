# Swarm API Registry — 权威事实源

> **本文档由 [game_api.idl.yaml](game_api.idl.yaml) 自动生成。冲突时以 YAML 为准。手写修改将被覆盖。**

> **本文档是 Swarm 所有 API 合约的单一权威来源**。CommandAction、RejectionReason、MCP Tools、Host Functions、容量限制均以此文档为准。其他文档只能引用，不得重新声明可冲突的表格或列表。

**生成日期**: 2026-06-18 | **API 版本**: `0.3.0` | **权威源**: [game_api.idl.yaml](game_api.idl.yaml)

## 原则

1. **单事实源 (D1/A)**：YAML IDL 是唯一的机器可读权威源。本 Markdown 由 YAML 自动生成，手工修改将被覆盖。
2. **机器可读优先**：所有定义使用结构化表格，可由 CI 自动校验跨文件一致性。
3. **版本化**：每次 API 变更更新 `api_version`，TickTrace 记录 `api_version`。
4. **完整闭合**：新增指令/错误码/工具/函数必须在此注册，未注册的 CI 拒绝。

**当前 API 版本**: `0.3.0`

---

## 1. CommandAction

Core CommandAction 是 WASM tick() 输出的 CommandIntent 中的 action type。所有 Vanilla action 定义于此。World Action Manifest 通过 `custom_actions` 扩展，但核心集合不变。共 **19 个变体**。

### 1.1 核心指令 (11)

| # | Action | 参数 | 说明 |
|---|--------|------|------|
| 1 | `Move` | `direction: Direction4` | Move one cell in N/S/E/W direction |
| 2 | `Harvest` | `target_id: EntityId` | Harvest a resource from target |
| 3 | `Transfer` | `target_id: EntityId, resource: ResourceType, amount: u32` | Transfer resources locally to target |
| 4 | `Withdraw` | `target_id: EntityId, resource: ResourceType, amount: u32` | Withdraw resources from structure |
| 5 | `Build` | `structure_type: StructureType, x: i32, y: i32` | Build a structure at (x,y) |
| 6 | `Attack` | `target_id: EntityId` | Melee attack target |
| 7 | `RangedAttack` | `target_id: EntityId` | Ranged attack target |
| 8 | `Heal` | `target_id: EntityId` | Repair or heal target |
| 9 | `Spawn` | `body_parts: [BodyPart], spawn_id: SpawnId` | Spawn a drone with given body parts |
| 10 | `Recycle` | `target_id: EntityId` | Recycle a drone or structure |
| 11 | `ClaimController` | `target_id: EntityId` | Claim a room controller |

### 1.2 Global Storage 指令 (2)

| # | Action | 参数 | 说明 |
|---|--------|------|------|
| 12 | `TransferToGlobal` | `resource: ResourceType, amount: u32` | Deposit resources to global storage |
| 13 | `TransferFromGlobal` | `resource: ResourceType, amount: u32` | Withdraw resources from global storage |

### 1.3 特殊攻击 (6)

| # | Action | 参数 | 说明 |
|---|--------|------|------|
| 14 | `Hack` | `target_id: EntityId` | 5-stage intrusion attack |
| 15 | `Drain` | `target_id: EntityId` | Continuously drain resources from target |
| 16 | `Overload` | `target_id: EntityId` | Reduce target fuel budget |
| 17 | `Debilitate` | `target_id: EntityId` | Reduce target efficiency |
| 18 | `Disrupt` | `target_id: EntityId` | Interrupt target operation |
| 19 | `Fortify` | `target_id: EntityId` | Strengthen own defenses |

### 1.4 Custom Actions

`Leech` 和 `Fabricate` 为 World Action Manifest 中的 `custom_actions`，非 Core enum 成员。每个 custom action 在 manifest 中声明 `action_id`、参数 schema、validator、handler。TickTrace 记录 `world_action_manifest_hash` 以确保 replay 确定性。

| Action | action_id | 说明 |
|--------|-----------|------|
| `Leech` | custom | World Action Manifest custom_action |
| `Fabricate` | custom | World Action Manifest custom_action |

---

## 2. RejectionReason

所有指令拒绝原因在此注册。**共计 35 个 canonical code**，覆盖 Pipeline、Validation、MCP、Runtime 四层。

Per D2/B: 35 canonical code 是 wire enum。详细上下文信息（如 NotMovable、Fatigued、特定 target 状态）放入 `debug_detail` 字段，**而非**增加 RejectionReason enum 变体。这保持 wire enum 稳定，同时提供丰富的调试数据。

### debug_detail 字段

| 属性 | 值 |
|------|-----|
| 描述 | Non-canonical, human-readable detail string，提供超出 35 canonical code 的上下文 |
| 最大长度 | 512 bytes |
| 示例 | `"NotMovable: encumbered by 3 units"`, `"Fatigued: action cooldown 12 ticks remaining"`, `"PathBlocked: obstacle at (5,3)"` |

### detail_level — 控制 debug_detail 详细程度

| 级别 | 说明 |
|------|------|
| `competitive` | 最小细节 — 仅 canonical code，无 debug_detail。Tournament/ladder 模式。**(默认)** |
| `practice` | 中等细节 — debug_detail 包含 cooldown/timer 值、bot 友好提示。 |
| `training` | 完整细节 — debug_detail 包含精确 state diff、path traces、内部诊断信息。 |

### 2.1 Pipeline 级 — 不计入 enum，统一前置处理

| 错误码 | 含义 |
|--------|------|
| `InvalidJson` | JSON parsing failed |
| `SchemaViolation` | Command schema does not conform to IDL |

### 2.2 Validation 级

| # | RejectionReason | 含义 | 备注 |
|---|-----------------|------|------|
| 1 | `ObjectNotFound` | Target entity does not exist | 统一形式；废弃 TargetNotFound |
| 2 | `NotOwner` | Not the owner of the target entity | |
| 3 | `InsufficientResource` | Insufficient resources for operation | 统一单数形式；废弃 InsufficientResources, InsufficientEnergy |
| 4 | `OutOfRange` | Target is beyond operation range | |
| 5 | `NotStructure` | Target is not a structure | |
| 6 | `NotController` | Target is not a controller | |
| 7 | `NotVisibleOrNotFound` | Target not visible or does not exist (merged to prevent oracle inference) | 安全合并码 |
| 8 | `TargetNotVisible` | Target is not in field of view | |
| 9 | `SpawnOnCooldown` | Spawn is on cooldown | Spawn 专属 |
| 10 | `RoomDroneCapReached` | Room drone capacity reached | |
| 11 | `AuthContextInvalid` | Authentication context is invalid | |
| 12 | `CooldownActive` | Operation cooldown is active | 通用冷却；SpawnOnCooldown 为 Spawn 专属 |
| 13 | `InvalidDirection` | Direction is not one of the 4 valid directions | |
| 14 | `PositionOccupied` | Target position is occupied | |
| 15 | `ConstructionLimitReached` | Structure construction limit reached | |
| 16 | `SafeModeActive` | Target is in safe mode | |
| 17 | `TargetOverloadCooldown` | Target has an active overload cooldown | |
| 18 | `TargetFortifyCooldown` | Target has an active fortify cooldown | |
| 19 | `NotEnoughBodyParts` | Not enough body parts for operation | |
| 20 | `InvalidBodyPart` | Invalid body part specified | |
| 21 | `InvalidStructureType` | Invalid structure type specified | |
| 22 | `InvalidResourceType` | Invalid resource type specified | |
| 23 | `SourceNotAllowed` | Command source is not permitted for this operation | |
| 24 | `UnknownAction` | Unknown action type | |
| 25 | `GlobalStorageDisabled` | Global storage is not enabled | |
| 26 | `TransferInProgress` | A transfer is already in progress | |

### 2.3 MCP 层

| # | RejectionReason | 含义 | 备注 |
|---|-----------------|------|------|
| 27 | `RateLimited` | Rate limit exceeded | |
| 28 | `InvalidCertificate` | Certificate is invalid | |
| 29 | `NotAuthorized` | Not authorized for this operation | 仅 MCP 层；validation 层用 NotOwner |

### 2.4 Runtime 级

| # | RejectionReason | 含义 |
|---|-----------------|------|
| 30 | `FuelExhausted` | WASM fuel exhausted |
| 31 | `TimeoutExceeded` | WASM execution timed out |
| 32 | `SnapshotOverBudget` | Snapshot exceeds size budget |
| 33 | `CommandBufferFull` | Command buffer is full |
| 34 | `ServerOverloaded` | Server is overloaded; degraded mode |
| 35 | `InternalError` | Engine internal error |

### 命名规范

- 统一使用 **`InsufficientResource`**（单数），废弃 `InsufficientResources`/`InsufficientEnergy`
- 统一使用 **`ObjectNotFound`**，废弃 `TargetNotFound`
- 统一使用 **`CooldownActive`**（通用冷却），保留 `SpawnOnCooldown` 为 Spawn 专属
- **`NotVisibleOrNotFound`** 为安全合并码，防止通过不同错误码推断实体存在性
- **`NotAuthorized`** 仅用于 MCP 层认证失败；validation 层用 `NotOwner`

---

## 3. MCP Tools

所有 MCP 工具在此注册。**共计 46 个工具**（v0.3.0：swarm_list_market_orders 移至 RFC；新增 Auth category）。

### 3.1 通用 Rate Limit

| 类别 | 限制 |
|------|------|
| query (读类) | 50/tick |
| debug (调试类) | 30/tick |
| dev_aux (开发辅助类) | 20/tick |
| deploy (部署类) | 10/h |
| admin (管理类) | 10/h |
| sdk_fetch (SDK 获取) | 5/min |

### 3.2 工具清单 (46)

#### Onboarding (8)

| 工具名 | Input Schema | Output Schema | Rate Limit | Required Scope | Subject Source | Replay Class | Visibility Filter | Rate Limit Key |
|--------|-------------|---------------|------------|----------------|----------------|--------------|-------------------|----------------|
| `swarm_get_info` | `{}` | `{version, tick_rate, world_name, player_count}` | 100/min | `swarm:read` | `player_id` | `read_replay_safe` | `none` | `per_player` |
| `swarm_get_snapshot` | `{player_id}` | `{tick, entities, terrain, resources, truncated, omitted_count}` | 1/tick | `swarm:read` | `player_id` | `read_replay_safe` | `fog_of_war` | `per_player` |
| `swarm_get_resources` | `{player_id}` | `{resources, storage, income_rate}` | 10/tick | `swarm:read` | `player_id` | `read_replay_safe` | `owner` | `per_player` |
| `swarm_list_rooms` | `{player_id}` | `{rooms: [{id, level, controller_level}]}` | 10/tick | `swarm:read` | `player_id` | `read_replay_safe` | `fog_of_war` | `per_player` |
| `swarm_get_room` | `{room_id}` | `{terrain, entities, resources, controller}` | 10/tick | `swarm:read` | `world` | `read_replay_safe` | `fog_of_war` | `per_room` |
| `swarm_list_drones` | `{player_id}` | `{drones: [{id, room, body, lifespan, status}]}` | 10/tick | `swarm:read` | `player_id` | `read_replay_safe` | `owner` | `per_player` |
| `swarm_get_drone` | `{drone_id}` | `{id, room, body, lifespan, status, code_hash, fuel_used}` | 10/tick | `swarm:read` | `drone_id` | `read_replay_safe` | `owner_or_visible` | `per_drone` |
| `swarm_get_code` | `{drone_id}` | `{code, hash, language, size, last_deployed}` | 20/tick | `swarm:read` | `drone_id` | `read_replay_safe` | `owner` | `per_drone` |

#### Auth (2) — added v0.3.0

| 工具名 | Input Schema | Output Schema | Rate Limit | Required Scope | Subject Source | Replay Class | Visibility Filter | Rate Limit Key |
|--------|-------------|---------------|------------|----------------|----------------|--------------|-------------------|----------------|
| `swarm_auth_login` | `{credential, challenge_response}` | `{token, expiry, scope, player_id}` | 10/min | `swarm:auth` | `none` | `non_replayable` | `none` | `per_ip` |
| `swarm_auth_refresh` | `{token}` | `{token, expiry}` | 5/min | `swarm:auth` | `player_id` | `non_replayable` | `owner` | `per_player` |

#### Play (14)

| 工具名 | Input Schema | Output Schema | Rate Limit | Required Scope | Subject Source | Replay Class | Visibility Filter | Rate Limit Key |
|--------|-------------|---------------|------------|----------------|----------------|--------------|-------------------|----------------|
| `swarm_get_leaderboard` | `{scope, limit}` | `{entries: [{player, gcl, rooms, drones}]}` | 5/tick | `swarm:read` | `world` | `read_replay_safe` | `none` | `global` |
| `swarm_get_replay` | `{tick_range, player_id}` | `{ticks, entities, commands, events}` | 5/min | `swarm:read` | `world` | `read_replay_safe` | `fog_of_war` | `global` |
| `swarm_get_events` | `{room_id, tick_range}` | `{events: [{tick, type, data}]}` | 10/tick | `swarm:read` | `world` | `read_replay_safe` | `fog_of_war` | `per_room` |
| `swarm_get_terrain` | `{room_id, bounds}` | `{terrain_grid, size}` | — (host fn only) | `swarm:read` | `world` | `read_replay_safe` | `none` | `host_only` |
| `swarm_get_path` | `{from, to, player_id}` | `{path, distance, cost}` | — (host fn only) | `swarm:read` | `player_id` | `read_replay_safe` | `fog_of_war` | `host_only` |
| `swarm_get_visibility` | `{player_id}` | `{visible_rooms, visible_entities}` | 10/tick | `swarm:read` | `player_id` | `read_replay_safe` | `owner` | `per_player` |
| `swarm_list_controllers` | `{player_id}` | `{controllers: [{room, level, progress, owner}]}` | 10/tick | `swarm:read` | `player_id` | `read_replay_safe` | `fog_of_war` | `per_player` |
| `swarm_get_controller` | `{controller_id}` | `{room, level, progress, owner, downgrade_timer}` | 10/tick | `swarm:read` | `world` | `read_replay_safe` | `fog_of_war` | `per_room` |
| `swarm_list_structures` | `{room_id, player_id}` | `{structures: [{id, type, pos, hits}]}` | 10/tick | `swarm:read` | `player_id` | `read_replay_safe` | `fog_of_war` | `per_room` |
| `swarm_get_structure` | `{structure_id}` | `{id, type, pos, hits, capacity, cooldown}` | 10/tick | `swarm:read` | `world` | `read_replay_safe` | `fog_of_war` | `per_structure` |
| `swarm_get_messages` | `{drone_id}` | `{messages: [{from, content, tick}]}` | 10/tick | `swarm:read` | `drone_id` | `read_replay_safe` | `owner` | `per_drone` |
| `swarm_get_economy` | `{player_id}` | `{income, expenses, storage_tax, maintenance}` | 10/tick | `swarm:read` | `player_id` | `read_replay_safe` | `owner` | `per_player` |
| `swarm_get_drone_efficiency` | `{drone_id}` | `{efficiency, factors}` | 10/tick | `swarm:read` | `drone_id` | `read_replay_safe` | `owner` | `per_drone` |
| `swarm_get_economy_trend` | `{player_id, ticks}` | `{trend: [{tick, metric, value}]}` | 10/tick | `swarm:read` | `player_id` | `read_replay_safe` | `owner` | `per_player` |

#### Deploy (6)

| 工具名 | Input Schema | Output Schema | Rate Limit | Required Scope | Subject Source | Replay Class | Visibility Filter | Rate Limit Key |
|--------|-------------|---------------|------------|----------------|----------------|--------------|-------------------|----------------|
| `swarm_deploy` | `{player_id, drone_id, wasm_bytes, metadata}` | `{deploy_id, accepted, validation_errors, fdb_version_counter, object_store_key}` | 10/h | `swarm:deploy` | `player_id` | `idempotent_mutation` | `owner` | `per_player` |
| `swarm_validate_module` | `{wasm_bytes}` | `{valid, errors, fuel_estimate}` | 10/h | `swarm:deploy` | `player_id` | `read_replay_safe` | `none` | `per_player` |
| `swarm_get_deploy_status` | `{deploy_id}` | `{status, errors, deployed_at, fdb_version_counter, object_store_key}` | 20/tick | `swarm:read` | `player_id` | `read_replay_safe` | `owner` | `per_player` |
| `swarm_list_deployments` | `{player_id}` | `{deployments: [{id, drone_id, status, at, fdb_version_counter}]}` | 20/tick | `swarm:read` | `player_id` | `read_replay_safe` | `owner` | `per_player` |
| `swarm_get_world_config` | `{}` | `{rules, mods, limits, tick_rate}` | 10/tick | `swarm:read` | `world` | `read_replay_safe` | `none` | `global` |
| `swarm_get_world_rules` | `{}` | `{rule_modules, parameters, version}` | 10/tick | `swarm:read` | `world` | `read_replay_safe` | `none` | `global` |

> **swarm_deploy** 使用 deploy_mutation 模式 (R16 B6): WASM blob 异步上传至 object store (见 §11 Persistence)。FDB 仅提交小型 manifest + hash pointer + fdb_version_counter。fdb_version_counter 为 replay 确定性提供严格全序。

#### Debug (7)

| 工具名 | Input Schema | Output Schema | Rate Limit | Required Scope | Subject Source | Replay Class | Visibility Filter | Rate Limit Key |
|--------|-------------|---------------|------------|----------------|----------------|--------------|-------------------|----------------|
| `swarm_get_tick_trace` | `{tick}` | `{commands, state_diff, rejections, metrics}` | 30/tick | `swarm:debug` | `world` | `read_replay_safe` | `admin_scope` | `global` |
| `swarm_get_engine_stats` | `{}` | `{tick_duration, player_count, memory, cpu, sandbox_stats}` | 30/tick | `swarm:debug` | `world` | `read_replay_safe` | `admin_scope` | `global` |
| `swarm_get_sandbox_profile` | `{drone_id}` | `{fuel_used, host_calls, memory_peak, execution_time}` | 30/tick | `swarm:debug` | `drone_id` | `read_replay_safe` | `admin_scope` | `per_drone` |
| `swarm_list_errors` | `{player_id, limit}` | `{errors: [{tick, drone, code, detail}]}` | 20/tick | `swarm:debug` | `player_id` | `read_replay_safe` | `admin_scope` | `per_player` |
| `swarm_get_state_checksum` | `{tick}` | `{checksum, algorithm, scope}` | 30/tick | `swarm:debug` | `world` | `read_replay_safe` | `admin_scope` | `global` |
| `swarm_simulate` | `{commands, assumptions}` | `{trace, authoritative: false, assumptions, confidence}` | 50/tick | `swarm:debug` | `player_id` | `read_replay_safe` | `owner` | `per_player` |
| `swarm_dry_run` | `{wasm_bytes, tick_count}` | `{trace, fuel_used, errors}` | 50/tick | `swarm:debug` | `player_id` | `read_replay_safe` | `owner` | `per_player` |

#### Admin (6)

| 工具名 | Input Schema | Output Schema | Rate Limit | Required Scope | Subject Source | Replay Class | Visibility Filter | Rate Limit Key |
|--------|-------------|---------------|------------|----------------|----------------|--------------|-------------------|----------------|
| `swarm_admin_challenge` | `{challenge, signature}` | `{granted, scope, expiry}` | 5/min | `swarm:admin` | `admin_id` | `admin_critical` | `admin_scope` | `per_admin` |
| `swarm_admin_set_world_config` | `{key, value}` | `{accepted, applied_at}` | 10/h | `swarm:admin` | `admin_id` | `admin_critical` | `admin_scope` | `per_admin` |
| `swarm_admin_rollback` | `{target_tick}` | `{rollback_id, state}` | 5/h | `swarm:admin` | `admin_id` | `admin_critical` | `admin_scope` | `per_admin` |
| `swarm_admin_ban_player` | `{player_id, reason, duration}` | `{banned, expiry}` | 10/h | `swarm:admin` | `admin_id` | `admin_critical` | `admin_scope` | `per_admin` |
| `swarm_admin_force_gc` | `{scope}` | `{freed_bytes, duration}` | 5/h | `swarm:admin` | `admin_id` | `admin_critical` | `admin_scope` | `per_admin` |
| `swarm_admin_get_audit_log` | `{scope, limit}` | `{entries: [{timestamp, actor, action, detail}]}` | 30/tick | `swarm:admin` | `admin_id` | `read_replay_safe` | `admin_scope` | `per_admin` |

#### SDK (1)

| 工具名 | Input Schema | Output Schema | Rate Limit | Required Scope | Subject Source | Replay Class | Visibility Filter | Rate Limit Key |
|--------|-------------|---------------|------------|----------------|----------------|--------------|-------------------|----------------|
| `swarm_sdk_fetch` | `{language, include_examples}` | `{sdk_code, type_definitions, examples, abi_version, min_engine_version}` | 5/min | `swarm:read` | `world` | `read_replay_safe` | `none` | `global` |

#### Resources (2)

| 工具名 | Input Schema | Output Schema | Rate Limit | Required Scope | Subject Source | Replay Class | Visibility Filter | Rate Limit Key |
|--------|-------------|---------------|------------|----------------|----------------|--------------|-------------------|----------------|
| `resources/list` | `{}` | `{resources: [{type, name, category}]}` | 50/tick | `swarm:read` | `world` | `read_replay_safe` | `none` | `global` |
| `resources/read` | `{resource_type}` | `{type, name, category, base_value, rarity}` | 50/tick | `swarm:read` | `world` | `read_replay_safe` | `none` | `global` |

### 3.3 RFC / Future Tools

以下工具为 Future RFC 预留，**不计入活跃 tool count**，尚未实现。

| 工具名 | 分类 | RFC 追踪 |
|--------|------|----------|
| `swarm_list_market_orders` | Play | RFC-MARKET-001 |

> Market subsystem 为 RFC 特性。此工具为前向兼容定义但**未激活**。在 RFC-MARKET-001 被接受并实现之前，SDK codegen 不得生成此工具。

### 3.4 Capability Profiles

工具按 profile 分组，控制 MCP 客户端的能力面：

| Profile | 包含分类 | 默认分配 |
|---------|---------|---------|
| `onboarding` | Onboarding, Auth, SDK, Resources | 所有已认证客户端 |
| `play` | Play | World 玩家，Arena spectator |
| `deploy` | Deploy | 所有已认证客户端 |
| `debug` | Debug | 开发者 / Arena host |
| `admin` | Admin | 服主 / Admin 证书 |

### 3.5 WebSocket 通道安全

| 通道类型 | 安全模型 | 说明 |
|---------|---------|------|
| **Agent WS** (MCP/sandbox) | 每消息 seq + MAC (ed25519) | 每条消息附带单调递增序列号和消息认证码。重放检测：seq 必须 > 上次接收值，否则断开。MAC 涵盖 `(seq, tick, payload)` |
| **Browser WS** (展示/观战) | 只读 | 浏览器 WebSocket 仅接收广播（tick delta, 事件流），不允许发送命令。写操作通过 MCP/HTTP 路径 |
| **Replay WS** | 只读 + seek | 回放客户端可请求历史 tick 范围，但不能注入新命令 |

Agent WS 序列号与 MAC 由 `Swarm-Request-Signature` 头携带——每消息签名覆盖 `(method, uri, timestamp, seq, body_hash)`。seq 单调递增，server 端验证后更新 `last_seq`。seq 回退或 MAC 不匹配 → 断开连接并审计日志。

---

## 4. Host Functions

WASM 模块通过 host function import 调用引擎服务。以下为权威签名与限制。**共计 5 个函数**。

### 4.1 函数签名

| # | 函数 | ABI 签名 | 只读 | 说明 |
|---|------|---------|:---:|------|
| 1 | `host_get_terrain` | `(room_id: u32, out_ptr: i32, out_len: i32) -> i32` | ✅ | Get room terrain data |
| 2 | `host_get_objects_in_range` | `(x: i32, y: i32, range: u32, out_ptr: i32, out_len: i32) -> i32` | ✅ | Get entities within range of (x,y) |
| 3 | `host_path_find` | `(from_x: i32, from_y: i32, to_x: i32, to_y: i32, opts_ptr: i32, opts_len: i32, out_ptr: i32, out_len: i32) -> i32` | ✅ | A* pathfinding |
| 4 | `host_get_world_config` | `(key_ptr: i32, key_len: i32, out_ptr: i32, out_len: i32) -> i32` | ✅ | Read world configuration value |
| 5 | `host_get_world_rules` | `(rule_id_ptr: i32, rule_id_len: i32, out_ptr: i32, out_len: i32) -> i32` | ✅ | Read rule module data |

### 4.2 调用预算

| 限制项 | 值 |
|--------|-----|
| Host call 总预算 | **1,000/tick/player** |
| `host_get_objects_in_range` 上限 | **5/tick** |
| `host_path_find` 上限 | **10/tick** |
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

| 优先级 | 错误码 | 名称 | 条件 |
|:---:|:---:|------|------|
| 1 | -1 | `ERR_MEMORY_BOUNDS` | out_ptr/out_len 越界 |
| 2 | -2 | `ERR_ABI_VERSION` | ABI version / schema mismatch |
| 3 | -3 | `ERR_NOT_VISIBLE` | 实体不可见 (visibility redaction) |
| 4 | -4 | `ERR_BUDGET_EXHAUSTED` | Per-call budget exhausted |
| 5 | -5 | `ERR_PLAYER_BUDGET` | Per-player budget exhausted |
| 6 | -6 | `ERR_GLOBAL_BUDGET` | Global budget exhausted |
| 7 | -7 | `ERR_VALIDATION` | Function-specific validation failure |
| 8 | -8 | `ERR_OUTPUT_SIZE` | Output size exceeded |
| 9 | -9 | `ERR_TIMEOUT` | Timeout (仅在线执行，replay 不重跑 COLLECT) |

---

## 5. 全局容量限制

以下数值为权威上限。所有其他文档引用此处，不得重新声明。

### 5.1 游戏限制

| 参数 | 值 | 说明 |
|------|-----|------|
| **Commands/player/tick** | **100** | per-player 最大指令数 |
| **Per-player drone cap** | **500** | world.toml 可调 |
| **Global drone cap** | **10,000** | 全局活跃 drone 上限 |
| **Global entity cap** | **50,000** | 全局实体上限 |
| **Drone lifespan** | **1500 ticks** | 默认值 |
| **MAX_BODY_PARTS** | **50** | 每 drone 最大部件数 |
| **MAX_CONSTRUCTION_SITES** | **100** | 全局在建上限 |
| **Safe mode duration** | **500 ticks** | 默认值 |
| **Reservation timeout** | **1000 ticks** | 房间保留超时 |
| **Downgrade timer** | **5000 ticks** | 控制器降级倒计时 |
| **Global storage capacity** | **1,000,000 units** | world.toml 可调 |

### 5.2 WASM 限制

| 参数 | 值 | 说明 |
|------|-----|------|
| **WASM 内存上限** | **128 MB** | cgroup 进程级；WASM 线性内存 64 MB |
| **Sandbox CPU** | `cpu.max = 250000 3000000` | 每 3s 周期 0.25s |
| **Per-player sandbox deadline** | **2500ms** | World 模式 |
| **MCP simulate max_ticks** | **100** | 模拟最大 tick 数 |
| **MCP simulate max_entities** | **1000** | 模拟最大实体数 |
| **Pathfinding budget** | **100,000 explored nodes/tick** | 引擎全局；per-player 10 次调用 |
| **Pathfinding result path** | **500 nodes max** | 返回路径最大长度 |

### 5.3 TickTrace 保留策略

| 级别 | 保留时长 |
|------|---------|
| hot | 7d |
| warm | 30d |
| cold | 180d |

### 5.4 Replay 参数

| 参数 | 值 | 说明 |
|------|-----|------|
| Replay keyframe 间隔 | **K=100 ticks** | keyframe 写入频率 |
| `code_update_cooldown` | **5 ticks** | World 最小值；world.toml 可配 |

### 5.5 硬件基线 (Hardware Baseline)

| 参数 | 值 | 说明 |
|------|-----|------|
| **Target active players** | **500** | 64 GB RAM, 32 cores |
| **Hard cap players** | **1000** | 超限进入 degraded mode，入场门控 (admission gating) |
| **Worker pool size** | `min(max_pool, active_players)` | max_pool 默认 256，World 模式 |
| **Worker pool max** | `max_pool` = 256 | world.toml 可调 |
| **Degraded mode** | 超过 hard cap 时拒绝新 WASM 执行 | 已在 tick 中的玩家继续运行 |

### 5.6 Per-Player Fair-Share Admission

| 资源 | 全局预算 | 分配策略 |
|------|---------|---------|
| **Pathfinding explored nodes** | 100,000 / tick | 每玩家份额 = `floor(100,000 / active_players)`，先到先得，超出即 `ERR_BUDGET_EXHAUSTED`。tick 开始时计算份额，整个 tick 不变 |
| **Host call budget** | 1,000 / tick / player | 固定 per-player cap |
| **Snapshot per-player** | 256 KB | 固定 per-player cap |

---

## 6. TickTrace Envelope

Replay 确定性依赖 TickInputEnvelope 的完整性。**共计 22 个字段**。v0.3.0：`wasm_status` → `terminal_state` 显式 enum。

| # | 字段 | 类型 | 说明 |
|---|------|------|------|
| 1 | `api_version` | `u32` | API registry version |
| 2 | `module_hash` | `[u8; 32]` | WASM module Blake3 hash |
| 3 | `wasmtime_version` | `string` | Wasmtime engine version |
| 4 | `effective_tick` | `u64` | Effective tick number |
| 5 | `terminal_state` | `enum` | Terminal execution state (replaces legacy wasm_status) |
| 6 | `snapshot_hash` | `[u8; 32]` | Input snapshot hash |
| 7 | `commands_hash` | `[u8; 32]` | Output commands hash |
| 8 | `deploy_events` | `[DeployEvent]` | Deploy event list |
| 9 | `rollback_events` | `[RollbackEvent]` | Rollback event list |
| 10 | `admin_events` | `[AdminEvent]` | Admin event list |
| 11 | `world_config_hash` | `[u8; 32]` | World configuration hash |
| 12 | `mods_lock_hash` | `[u8; 32]` | Rule module lock hash |
| 13 | `engine_abi_version` | `u32` | Engine ABI version |
| 14 | `core_idl_version` | `u32` | Core IDL version |
| 15 | `world_action_manifest_hash` | `[u8; 32]` | World Action Manifest hash |
| 16 | `validator_version` | `u32` | Validator version |
| 17 | `rejection_reason_registry_version` | `u32` | RejectionReason registry version |
| 18 | `system_manifest_hash` | `[u8; 32]` | Phase 2b System Manifest hash |
| 19 | `limits_manifest_hash` | `[u8; 32]` | Limits Manifest hash |
| 20 | `host_abi_version` | `u32` | Host Function ABI version |
| 21 | `canonical_codec_version` | `u32` | Canonical Codec version |
| 22 | `visibility_truncation_version` | `u32` | Visibility/Truncation algorithm version |

### 6.1 terminal_state Enum

替代旧版 `wasm_status` 字段。Replay 必须产生相同 terminal_state 否则 replay 无效。

| 值 | 名称 | 说明 |
|:--:|------|------|
| 0 | `Success` | WASM execution completed successfully, commands produced |
| 1 | `FuelExhausted` | WASM fuel budget exhausted before completion |
| 2 | `TimeoutExceeded` | WASM execution exceeded wall-clock deadline |
| 3 | `SnapshotOverBudget` | Input snapshot exceeded per-player size budget |
| 4 | `CommandBufferFull` | Output command buffer exceeded capacity |
| 5 | `InternalError` | Engine internal error during WASM execution |
| 6 | `NotExecuted` | WASM was not executed this tick (e.g., replay from snapshot, degraded mode skip) |

---

## 7. Direction4 枚举

Move 指令使用 4 方向：

| 名称 | 值 |
|------|:--:|
| North | 0 |
| South | 1 |
| East | 2 |
| West | 3 |

8 方向（含 NE/NW/SE/SW）为 Future RFC，不在当前核心定义中。

---

## 8. SwarmError JSON-RPC Envelope

MCP/API 错误统一格式：

```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": "RejectionReason (string)",
    "message": "Human-readable detail (max 256 chars)",
    "data": {
      "command_index": "u32 (optional)",
      "rejection_detail": "max 512 bytes (optional)",
      "debug_detail": "max 512 bytes — non-canonical contextual detail"
    }
  },
  "id": "<request_id>"
}
```

MCP 共享错误码 `-32000` 保留给未分类内部错误，具体错误以 `error.code` 字符串为准。

---

## 9. ResourceOperation

所有涉及资源操作的 action 类型（CommandAction 子集）：

| Operation | Action # | 分类 | 说明 | Resource Flow |
|-----------|:-------:|------|------|---------------|
| `Harvest` | 2 | core | Harvest a resource from target entity | source → drone |
| `Transfer` | 3 | core | Transfer resources locally to target | drone → target |
| `Withdraw` | 4 | core | Withdraw resources from structure | structure → drone |
| `TransferToGlobal` | 12 | global_storage | Deposit resources to global storage | drone → global |
| `TransferFromGlobal` | 13 | global_storage | Withdraw resources from global storage | global → drone |
| `Drain` | 15 | special_attack | Continuously drain resources from target | target → drone |

---

## 10. Deploy — deploy_mutation 机制 (R16 B6)

### 架构

Deploy 子系统使用 deploy_mutation 模式：完整 WASM blob 异步上传至 object store，FDB 仅提交小型 manifest record（含 hash pointer 和 fdb_version_counter）。这保持 FDB 事务小而确定性。

### fdb_version_counter

| 属性 | 值 |
|------|-----|
| 类型 | `u64` |
| 原子性 | 与 deploy manifest 在同一 FDB 事务中递增 |
| Replay 合约 | deploy events 必须按 fdb_version_counter 升序重放 |

### Deploy Flow

| 步骤 | 描述 | Actor |
|:----:|------|-------|
| 1. Validate | Client 调用 swarm_validate_module 或在 swarm_deploy 中包含 wasm_bytes | client |
| 2. Upload Blob | WASM blob 通过 async_object_store_upload 上传至 object store（异步，不阻塞 deploy 调用） | engine |
| 3. Commit Manifest | FDB 事务提交 manifest record: `{deploy_id, drone_id, blob_hash, metadata, fdb_version_counter}` — 唯一 FDB 写入，小、快、确定性 | engine |
| 4. Activate | 下一 tick boundary，引擎按 blob_hash 从 object store 加载 WASM 并在 drone 上激活（延迟到 tick boundary 以保证确定性调度） | engine |

### swarm_deploy 输出 (v0.3.0)

| 字段 | 类型 |
|------|------|
| `deploy_id` | DeployId |
| `accepted` | bool |
| `validation_errors` | [string] |
| `fdb_version_counter` | u64 |
| `object_store_key` | string |

---

## 11. Persistence — async_object_store_upload (D5/B)

### 概述

Persistence 层处理大型二进制对象的存储。Per D5/B：object-store blob 上传为**异步**，不阻塞 FDB 提交路径。FDB 仅存储含 blob hash pointer 的小型 manifest record。这解耦了 I/O 吞吐与事务延迟。

### async_object_store_upload

| 属性 | 值 |
|------|-----|
| Storage Backend | pluggable (default: local filesystem; production: S3-compatible) |
| 调用方式 | fire-and-forget from deploy flow (step 2) |
| 确认 | immediate — 返回 object_store_key |
| 完成轮询 | 使用 swarm_get_deploy_status 检查上传完成状态 |
| 失败模式 | retry with exponential backoff (max 3 attempts); permanent failure → deploy rejected |

### Blob Types

| 类型 | 最大大小 | 保留策略 | Content Hash |
|------|---------|---------|-------------|
| `wasm_module` | 64 MB | permanent (until all referencing drones are recycled) | Blake3 |
| `replay_recording` | 1 GB | per tick_trace_retention policy | Blake3 |
| `snapshot_archive` | 256 MB | per tick_trace_retention policy | Blake3 |

### FDB Manifest Record

FDB 每 blob 仅存储小型 manifest record: `{blob_hash, object_store_key, size, uploaded_at, status}`。此 record 是 deploy_mutation FDB 事务的一部分，受 fdb_version_counter 排序覆盖。

| 字段 | 类型 |
|------|------|
| `blob_hash` | `[u8; 32]` |
| `object_store_key` | string |
| `size` | u64 |
| `uploaded_at` | u64 |
| `status` | `enum { pending, uploaded, failed }` |

---

## 变更记录

| 版本 | 日期 | 变更 |
|------|------|------|
| 0.3.0 | 2026-06-18 | **R17 D1/A**: YAML IDL 成为唯一机器源，本文档由 [game_api.idl.yaml](game_api.idl.yaml) 生成。B1: api_version → 0.3.0。B2/D2: RejectionReason 新增 debug_detail 字段 (512 bytes) + detail_level enum (competitive/practice/training)。B3: swarm_list_market_orders 移至 RFC；新增 Auth category (swarm_auth_login, swarm_auth_refresh)；MCP tools 精确定为 46 active。B4: TickTrace envelope `wasm_status` → `terminal_state` 显式 enum (7 variants)。B5: Deploy 新增 deploy_mutation 机制 + fdb_version_counter 输出。D5/B: 新增 §11 Persistence (async_object_store_upload)。Host functions ABI 错误优先级表增加显式优先级编号。SwarmError envelope error.data 新增 debug_detail。 |
| 0.2.0 | 2026-06-18 | Initial structured IDL with 10 sections |
| 0.1.0 | 2026-06-18 | R15 B1+B4+H1: 初次建立权威注册表。统一 RejectionReason (35 变体)、CommandAction (19 指令)、MCP Tools (46)、Host Functions (5)、容量限制 (25 参数)、TickTrace Envelope (22 字段)、Direction4、错误格式。 |
