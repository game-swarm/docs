# Swarm API Registry — 权威事实源

> **本文档由以下 IDL 源自动生成：[game_api.idl.yaml](game_api.idl.yaml), [auth_api.idl.yaml](auth_api.idl.yaml), [economy.idl.yaml](economy.idl.yaml)。冲突时以 IDL YAML 为准。手写修改将被覆盖。**

> **本文档是 Swarm 所有 API 合约的单一权威来源**。CommandAction、RejectionReason、MCP Tools、Host Functions、Economy Operations、容量限制均以此文档为准。其他文档只能引用，不得重新声明可冲突的表格或列表。

**生成日期**: 2026-06-18 | **API 版本**: `0.5.0` (game_api) / `0.1.0` (auth_api) / `0.1.1` (economy)
**权威源**: [game_api.idl.yaml](game_api.idl.yaml), [auth_api.idl.yaml](auth_api.idl.yaml), [economy.idl.yaml](economy.idl.yaml)
**Codegen**: [codegen.md](codegen.md) — IDL → Registry/SDK 生成链，禁止手写分叉。

## 原则

1. **单事实源 (D1/A)**：YAML IDL 是唯一的机器可读权威源。本 Markdown 由 IDL YAML 自动生成，手工修改将被覆盖。
2. **机器可读优先**：所有定义使用结构化表格，可由 CI 自动校验跨文件一致性。
3. **版本化**：每次 API 变更更新 `api_version`，TickTrace 记录 `api_version`。
4. **完整闭合**：新增指令/错误码/工具/函数必须在此注册，未注册的 CI 拒绝。

---

## 0. Fixed-Point Type Registry

All `f64` fields have been replaced with fixed-point integer representations to guarantee deterministic cross-platform behavior. The following types are registered across all three IDL sources.

| 类型名 | 底层类型 | 量纲 / 范围 | 来源 IDL | 说明 |
|--------|---------|------------|----------|------|
| `ResourceRate_i64` | `i64` | 1e6 = 1.0 resource/tick | game_api, economy | Resource rate in micro-units per tick. Positive = income, negative = expense. |
| `ProgressBps_i64` | `i64` | 10,000 = 100.00% | game_api | Progress in basis points |
| `BasisPoints` | `u32` | 0–10000 (0%–100%) | game_api, economy | Percentage in basis points. 50% = 5000 bp. 1 bp = 0.01% = 1/10000. |
| `EfficiencyBps` | `u32` | 0–10000 (0%–100%) | game_api | Efficiency in basis points |
| `ConfidenceBps` | `u32` | 0–10000 | game_api | Confidence in basis points |
| `milli_distance` | `i64` | 1,000 = 1 cell | game_api | Distance in milli-cell units |
| `micro_cost` | `u64` | 1e6 = 1.0 resource unit | game_api | Cost in micro resource units |
| `MilliUnits` | `i64` | 1,000 mU = 1 unit | economy | Sub-unit precision for intermediate economy calculations. Floor-rounded to integer units on state commit. |

---

## 1. CommandAction

> ⚠️ **机器权威**: 本表完全由 `game_api.idl.yaml` 的 `command_actions` 段自动生成。**禁止手工编辑** CommandAction 表格（包括变体名称、参数、分类、编号）。任何新增/修改 CommandAction 必须先在 IDL YAML 中定义，再通过 `generate_api_registry.py` 重新生成本文档。CI 检查模式会拒绝手工编辑导致的不一致。

Core CommandAction 是 WASM tick() 输出的 CommandIntent 中的 action type，包含 11 种非战斗基础操作 + Action dispatch。Combat/effect action 不再作为独立 CommandAction 变体注册，而是通过 `Action` dispatch 进入 ActionRegistry。

> **共享字段 `object_id: EntityId` (即 `actor_id`)**: 所有 11 个 CommandAction 变体 + Action dispatch 均包含 `object_id`（执行该动作的 entity，亦称为 `actor_id`）。此字段为所有 action 的公共参数，不在下方表格中各 action 的"参数"列重复列出。IDL 中每个 action 的 schema 均包含 `object_id`。
>
> **Spawn 语义**: `object_id`/`actor_id` = 发起 Spawn 的 drone（执行者），`spawn_id` = 目标 Spawn 结构（非 actor）。其他 action 同理：`actor_id` 始终为执行实体，`target_id` 为目标实体。Action dispatch 中的目标与扩展参数由 `payload: ActionPayload` 承载。

**来源 IDL**: game_api.idl.yaml
**变体总数**: 11 个 CommandAction + ActionRegistry

### 1.1 核心指令 (8)

| # | Action | 参数 | 分类 | 说明 |
|---|--------|------|------|------|
| 1 | `Move` | `direction: Direction4` | core | Move one cell in N/S/E/W direction |
| 2 | `Harvest` | `target_id: EntityId` | core | Harvest a resource from target |
| 3 | `Transfer` | `target_id: EntityId, resource: ResourceType, amount: u32` | core | Transfer resources locally to target |
| 4 | `Withdraw` | `target_id: EntityId, resource: ResourceType, amount: u32` | core | Withdraw resources from structure |
| 5 | `Build` | `structure_type: StructureType, x: i32, y: i32` | core | Build a structure at (x,y) |
| 9 | `Spawn` | `body_parts: [BodyPart], spawn_id: SpawnId` | core | Spawn a drone with given body parts |
| 10 | `Recycle` | `object_id: EntityId` (self-action) | core | Recycle self (drone or structure) |
| 11 | `ClaimController` | `target_id: EntityId` | core | Claim a room controller |

### 1.2 Economy Operation 指令 (2)

> 以下两个 Global Storage 指令属于 EconomyOperation lane——与 §10 Economy Operations 中的 resource flow 一致。它们仍为 CommandAction 变体（可被 WASM tick() 发出），但引擎将其路由至 Economy Operation 管线进行验证和执行。

| # | Action | 参数 | 分类 | 说明 |
|---|--------|------|------|------|
| 12 | `TransferToGlobal` | `resource: ResourceType, amount: u32` | economy_operation | Deposit resources to global storage |
| 13 | `TransferFromGlobal` | `resource: ResourceType, amount: u32` | economy_operation | Withdraw resources from global storage |

### 1.3 Action dispatch (1)

| # | Action | 参数 | 分类 | 说明 |
|---|--------|------|------|------|
| 22 | `Action` | `type: string, payload: ActionPayload` | action | 执行 ActionRegistry 注册的 combat/effect action |

### 1.4 ActionRegistry — 11 Vanilla + Mod-Extensible Combat Actions

11 个 vanilla combat/effect action（`Attack`, `RangedAttack`, `Heal`, `Hack`, `Drain`, `Overload`, `Debilitate`, `Disrupt`, `Fortify`, `Leech`, `Fabricate`）已从 CommandAction enum 移入 ActionRegistry。WASM tick() 通过 `CommandAction::Action { type, payload }` 统一 dispatch；引擎按 `type` 查找 ActionRegistry 定义并按该 action 的 payload schema 校验与执行。

**Canonical 参数表见 [special-attack-table.md](special-attack-table.md)**。Vanilla combat/effect action 的 body_part、damage_type、resistance、cost、cooldown、range、channel_time、counterplay、validation_schema 以该表为准；本 Registry 只声明 dispatch 入口和注册边界。

Mod 扩展通过 `world.toml` 的 `[[action_registry]]` 注册自定义 combat/effect action。TickTrace 记录 `world_action_manifest_hash`，确保 ActionRegistry 变更进入 replay 确定性边界。

---

## 2. RejectionReason — 48 codes

所有指令拒绝原因在此注册。覆盖 Pipeline、Validation、MCP、Runtime、Auth 五层。canonical code 总数为 48，由 IDL YAML 自动生成。

> ⚠️ **CI Gate**: 本计数由 IDL YAML 自动生成。若与其他文档或 IDL 不一致，**禁止手工修改此数**——应修正 IDL YAML 源并重新运行 `generate_api_registry.py`。CI 检查模式拒绝手工编辑导致的不一致。

Per D2/B: canonical code 是 wire enum。详细上下文信息（如 NotMovable、Fatigued、特定 target 状态）放入 `debug_detail` 字段，**而非**增加 RejectionReason enum 变体。这保持 wire enum 稳定，同时提供丰富的调试数据。

**SwarmError envelope（R35 D1）**：所有 API 错误统一使用标准 JSON-RPC 2.0 error object：`error.code` 必须是 numeric code（Swarm application error 使用 `-32000`；JSON parse/schema/transport 层使用 JSON-RPC 标准数值码），`error.message` 为人类可读摘要，canonical RejectionReason 放入 `error.data.rejection_reason`（如 `"NotVisibleOrNotFound"`）。`error.data.debug_detail` 为可选的非权威调试上下文。SDK 从 `error.data.rejection_reason` 生成 typed exception，不得把 `error.code` 当作 RejectionReason 字符串或细分业务码。

### debug_detail 字段

| 属性 | 值 | 来源 IDL |
|------|-----|----------|
| 描述 | Non-canonical, human-readable detail string，提供超出 canonical code 的上下文 | game_api, auth_api |
| 最大长度 | 512 bytes | game_api, auth_api |
| 示例 | `"NotMovable: encumbered by 3 units"`, `"Fatigued: action cooldown 12 ticks remaining"`, `"PathBlocked: obstacle at (5,3)"` | game_api |

### detail_level — 控制 debug_detail 详细程度

| 级别 | 说明 | 来源 IDL |
|------|------|----------|
| `competitive` | 最小细节 — 仅 canonical code，无 debug_detail。Tournament/ladder 模式。**(默认)** | game_api |
| `practice` | 中等细节 — debug_detail 包含 cooldown/timer 值、bot 友好提示。 | game_api |
| `training` | 完整细节 — debug_detail 包含精确 state diff、path traces、内部诊断信息。 | game_api |

### 2.1 Pipeline 级 — 不计入 enum，统一前置处理

**来源 IDL**: game_api

| 错误码 | 含义 | 来源 IDL |
|--------|------|----------|
| `InvalidJson` | JSON parsing failed | game_api |
| `SchemaViolation` | Command schema does not conform to IDL | game_api |

### 2.2 Validation 级 — 29 codes

**来源 IDL**: game_api

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
| 27 | `MainActionQuotaExceeded` | Per-drone per-tick main action quota exceeded | R33 B6 新增 |
| 48 | `NotEligible` | 目标不满足该 Action 条件或在冷却中 | 与 visibility spec 对齐，编号不冲突现有 47 |

### 2.3 MCP 层 — 3 codes

**来源 IDL**: game_api

| # | RejectionReason | 含义 | 备注 |
|---|-----------------|------|------|
| 28 | `RateLimited` | Rate limit exceeded | |
| 29 | `InvalidCertificate` | Certificate is invalid | |
| 30 | `NotAuthorized` | Not authorized for this operation | 仅 MCP 层；validation 层用 NotOwner |

### 2.4 Runtime 级 — 6 codes

**来源 IDL**: game_api

| # | RejectionReason | 含义 |
|---|-----------------|------|
| 31 | `FuelExhausted` | WASM fuel exhausted |
| 32 | `TimeoutExceeded` | WASM execution timed out |
| 33 | `SnapshotOverBudget` | Snapshot exceeds size budget |
| 34 | `CommandBufferFull` | Command buffer is full |
| 35 | `ServerOverloaded` | Server is overloaded; degraded mode |
| 36 | `InternalError` | Engine internal error |

### 2.5 Auth 层 — 12 canonical codes (namespace offset 1000+)

**来源 IDL**: auth_api

| # | RejectionReason | 含义 | 来源 IDL | 备注 |
|---|-----------------|------|----------|------|
| 1001 | `InvalidCertificate` | Client certificate is invalid, untrusted, or malformed | auth_api | Certificate validation failure |
| 1002 | `NotAuthorized` | Authenticated principal lacks required scope for this operation | auth_api | Auth-layer scope check; distinct from game-layer NotOwner |
| 1003 | `CertExpired` | Client certificate has expired | auth_api | Certificate past its notAfter date |
| 1004 | `DeviceNotRegistered` | Device is not registered in the device trust registry | auth_api | |
| 1005 | `SessionLimitReached` | Player has reached the maximum number of concurrent sessions | auth_api | |
| 1006 | `RefreshTokenInvalid` | Refresh token is invalid, expired, or already consumed (replay detected) | auth_api | Triggers token family revocation |
| 1007 | `ScopeInsufficient` | Token scope does not include the required permission | auth_api | |
| 1008 | `TokenRevoked` | Access or refresh token has been explicitly revoked | auth_api | |
| 1009 | `RateLimited` | Auth endpoint rate limit exceeded; retry after specified window | auth_api | |
| 1010 | `MultiDeviceConflict` | Device registration or session creation conflicts with existing device policy | auth_api | |
| 1011 | `UnknownCredential` | Credential type is not recognized or not supported | auth_api | |
| 1012 | `InternalAuthError` | Internal auth subsystem error | auth_api | E.g., token store unavailable, CA unreachable |

### 命名规范

**来源 IDL**: game_api, auth_api

- 统一使用 **`InsufficientResource`**（单数），废弃 `InsufficientResources`/`InsufficientEnergy`
- 统一使用 **`ObjectNotFound`**，废弃 `TargetNotFound`
- 统一使用 **`CooldownActive`**（通用冷却），保留 `SpawnOnCooldown` 为 Spawn 专属
- **`NotVisibleOrNotFound`** 为安全合并码，防止通过不同错误码推断实体存在性
- **`NotAuthorized`** 仅用于 MCP 层认证失败；validation 层用 `NotOwner`
- Auth 层 **`InvalidCertificate`** (code 1001) 为证书验证失败；game_api 层 `InvalidCertificate` (code 28) 为 MCP 层通用证书错误
- Auth 层 **`NotAuthorized`** (code 1002) 为 scope 检查失败；game_api 层 `NotAuthorized` (code 29) 为 MCP 层通用授权失败

### 2.6 Validation Condition → RejectionReason → debug_detail 映射

所有 validation 失败遵循：**condition → canonical RejectionReason → debug_detail template**。引擎检测到条件后，选择 canonical code，填充 debug_detail 模板。不得为特定 condition 新增 wire enum 变体。

| 条件 (condition) | canonical RejectionReason | debug_detail 模板 |
|---|---|---|
| 目标实体不存在 | `ObjectNotFound` | `"ObjectNotFound: entity_id=<id>"` |
| 目标实体不属于当前玩家 | `NotOwner` | `"NotOwner: entity_id=<id>, owner=<owner_id>"` |
| 资源不足（任意类型） | `InsufficientResource` | `"InsufficientResource: required=<amt> <type>, available=<amt>"` |
| 目标超出操作范围 | `OutOfRange` | `"OutOfRange: distance=<d>, max_range=<r>"` |
| 目标非结构体 | `NotStructure` | `"NotStructure: entity_id=<id>, actual_type=<type>"` |
| 目标非 Controller | `NotController` | `"NotController: entity_id=<id>, actual_type=<type>"` |
| 目标不可见或不存在 | `NotVisibleOrNotFound` | `"NotVisibleOrNotFound: entity_id=<id>"` |
| 目标不在视野内 | `TargetNotVisible` | `"TargetNotVisible: entity_id=<id>"` |
| Spawn 冷却中 | `SpawnOnCooldown` | `"SpawnOnCooldown: spawn_id=<id>, cooldown_remaining=<n> ticks"` |
| 房间 drone 容量已满 | `RoomDroneCapReached` | `"RoomDroneCapReached: room=<id>, current=<n>, cap=<c>"` |
| 认证上下文无效 | `AuthContextInvalid` | `"AuthContextInvalid: reason=<msg>"` |
| 通用冷却激活 | `CooldownActive` | `"CooldownActive: action=<action>, remaining=<n> ticks"` |
| 方向无效 | `InvalidDirection` | `"InvalidDirection: got=<dir>"` |
| 位置被占用 | `PositionOccupied` | `"PositionOccupied: x=<x>, y=<y>, occupied_by=<id>"` |
| 建筑数量达到上限 | `ConstructionLimitReached` | `"ConstructionLimitReached: type=<type>, current=<n>, limit=<l>"` |
| 安全模式激活 | `SafeModeActive` | `"SafeModeActive: entity_id=<id>, remaining=<n> ticks"` |
| 目标 Overload 冷却中 | `TargetOverloadCooldown` | `"TargetOverloadCooldown: target_id=<id>, remaining=<n> ticks"` |
| 目标 Fortify 冷却中 | `TargetFortifyCooldown` | `"TargetFortifyCooldown: target_id=<id>, remaining=<n> ticks"` |
| 身体部件不足 | `NotEnoughBodyParts` | `"NotEnoughBodyParts: required=<n>, available=<m>"` |
| 身体部件无效 | `InvalidBodyPart` | `"InvalidBodyPart: part=<name>"` |
| 结构类型无效 | `InvalidStructureType` | `"InvalidStructureType: type=<name>"` |
| 资源类型无效 | `InvalidResourceType` | `"InvalidResourceType: type=<name>"` |
| 指令来源不被允许 | `SourceNotAllowed` | `"SourceNotAllowed: source=<src>"` |
| 未知 action 类型 | `UnknownAction` | `"UnknownAction: type=<name>"` |
| Global Storage 未启用 | `GlobalStorageDisabled` | `"GlobalStorageDisabled: player_id=<id>"` |
| 传输进行中 | `TransferInProgress` | `"TransferInProgress: entity_id=<id>"` |
| Main action quota 已用尽 | `MainActionQuotaExceeded` | `"MainActionQuotaExceeded: drone_id=<id>, action=<action>, used=<n>, limit=1"` |
| 移动路径被阻挡（墙/敌对占据） | `PositionOccupied` | `"PositionOccupied: x=<x>, y=<y>, blocked_by=<wall|entity_id>"` |
| Drone 处于 spawning 保护期 | `CooldownActive` | `"CooldownActive: spawning_grace_remaining=<n> ticks"` |
| 身体部件成本超出房间能量上限 | `InsufficientResource` | `"InsufficientResource: body_cost=<cost>, room_energy_cap=<cap>"` |
| 无效伤害类型 | `InvalidResourceType` | `"InvalidResourceType: damage_type=<type>"` |
| 目标已有同类型 Debilitate 效果 | `CooldownActive` | `"CooldownActive: target_id=<id>, debilitate_type=<type>"` |

> 引擎实现必须使用 canonical RejectionReason，不得为上述 condition 发明新的 wire enum 变体。所有变体信息通过 `debug_detail` 模板参数化传递。`detail_level` 控制模板中数值的暴露程度（competitive 模式仅返回 canonical code，无 debug_detail）。

---

## 3. MCP Tools

所有 MCP 工具在此注册。工具计数由 IDL YAML 自动生成，并按三种口径并列引用：`all_declared`（IDL 中声明的全部工具，含 RFC-gated）、`active_only`（当前可调用/应生成 SDK 的工具）、`rfc_gated`（IDL 保留但 feature-gated、不得作为 active 实现暴露的工具）。其他文档引用工具数量时必须明确口径。

> ⚠️ **CI Gate**: 工具计数由 IDL YAML 自动生成。若与其他文档或 IDL 不一致，**禁止手工修改此数**——应修正 IDL YAML 源并重新运行 `generate_api_registry.py`。CI 检查模式拒绝手工编辑导致的不一致。

**来源 IDL**: game_api.idl.yaml (`all_declared=57`, `active_only=53`, `rfc_gated=4`), auth_api.idl.yaml (`all_declared=12`, `active_only=12`, `rfc_gated=0` — 证书链模型)

| 口径 | Game API | Auth API | 合计 | 用途 |
|------|---------:|---------:|-----:|------|
| `all_declared` | 57 | 12 | 69 | Registry/IDL 全声明口径；包含 RFC-gated 占位 schema |
| `active_only` | 53 | 12 | 65 | 当前运行时与 SDK 默认暴露口径；不含 RFC-gated 工具 |
| `rfc_gated` | 4 | 0 | 4 | IDL 保留但 feature-gated；返回 `ERR_FEATURE_GATED`，不得计入 active |

### 3.1 通用 Rate Limit

**来源 IDL**: game_api

| 类别 | 限制 |
|------|------|
| query (读类) | 50/tick |
| debug (调试类) | 30/tick |
| dev_aux (开发辅助类) | 20/tick |
| deploy (部署类) | 10/h |
| admin (管理类) | 10/h |
| sdk_fetch (SDK 获取) | 5/min |

### 3.2 Game API 工具清单 (`all_declared=57`, `active_only=53`, `rfc_gated=4`)

#### Onboarding (11)

| 工具名 | Input Schema | Output Schema | Rate Limit | Required Scope | Subject Source | Replay Class | Visibility Filter | Rate Limit Key | 来源 IDL |
|--------|-------------|---------------|------------|----------------|----------------|--------------|-------------------|----------------|----------|
| `swarm_get_info` | `{}` | `{version, tick_rate, world_name, player_count}` | 100/min | `swarm:read` | `player_id` | `read_replay_safe` | `none` | `per_player` | game_api |
| `swarm_get_snapshot` | `{player_id}` | `{tick, entities, terrain, resources, truncated, omitted_categories}` | 1/tick | `swarm:read` | `player_id` | `read_replay_safe` | `fog_of_war` | `per_player` | game_api |
| `swarm_get_resources` | `{player_id}` | `{resources, storage, income_rate}` | 10/tick | `swarm:read` | `player_id` | `read_replay_safe` | `owner` | `per_player` | game_api |
| `swarm_list_rooms` | `{player_id}` | `{rooms: [{id, level, controller_level}]}` | 10/tick | `swarm:read` | `player_id` | `read_replay_safe` | `fog_of_war` | `per_player` | game_api |
| `swarm_get_room` | `{room_id}` | `{terrain, entities, resources, controller}` | 10/tick | `swarm:read` | `world` | `read_replay_safe` | `fog_of_war` | `per_room` | game_api |
| `swarm_list_drones` | `{player_id}` | `{drones: [{id, room, body, lifespan, status}]}` | 10/tick | `swarm:read` | `player_id` | `read_replay_safe` | `owner` | `per_player` | game_api |
| `swarm_get_drone` | `{drone_id}` | `{id, room, body, lifespan, status, code_hash, fuel_used}` | 10/tick | `swarm:read` | `drone_id` | `read_replay_safe` | `owner_or_visible` | `per_drone` | game_api |
| `swarm_get_code` | `{drone_id}` | `{code, hash, language, size, last_deployed}` | 20/tick | `swarm:read` | `drone_id` | `read_replay_safe` | `owner` | `per_drone` | game_api |
| `swarm_get_docs` | `{topic?}` | `{docs, sections}` | 20/tick | `swarm:read` | `world` | `read_replay_safe` | `none` | `global` | game_api |
| `swarm_get_schema` | `{entity_type?}` | `{schema, version}` | 20/tick | `swarm:read` | `world` | `read_replay_safe` | `none` | `global` | game_api |
| **`swarm_get_objectives`** | `{player_id?, scope?}` | `{objectives: [{id, type, description, required, current, reward, priority, expires_at?}]}` | 5/tick | `swarm:read` | `player_id` | `read_replay_safe` | `owner` | `per_player` | **game_api** |

#### Auth (3)

| 工具名 | Input Schema | Output Schema | Rate Limit | Required Scope | Subject Source | Replay Class | Visibility Filter | Rate Limit Key | 来源 IDL | schema_source | alias_of |
|--------|-------------|---------------|------------|----------------|----------------|--------------|-------------------|----------------|----------|---------------|----------|
| `swarm_register_challenge` | `{}` | `{challenge_id, challenge, difficulty_bits=24, expires_at}` | 10/min | `none` | `none` | `non_replayable` | `none` | `per_ip` | game_api | `auth_api` | `auth_api.swarm_register_challenge` |
| `swarm_submit_csr` | `{username, csr, certificate_profile, device_label, challenge_id, nonce, csr_signature}` | `{certificate_bundle}` | 1/30s | `none` | `none` | `non_idempotent_mutation` | `none` | `per_ip` | game_api | `auth_api` | `auth_api.swarm_submit_csr` |
| `swarm_cert_check` | `{certificate_id}` | `{valid, player_id, usage, scope, audience, expires_at, revoked}` | 100/min | `swarm:auth` | `player_id` | `read_replay_safe` | `owner` | `per_player` | game_api | `auth_api` | `auth_api.swarm_cert_check` |

> **R33 B4**: Auth category 从 bearer token (swarm_auth_login/refresh/check) 重写为证书链模型 (swarm_register_challenge/submit_csr/cert_check)。完整 schema 见 §3.3 Auth API 工具。

#### Play (15)

| 工具名 | Input Schema | Output Schema | Rate Limit | Required Scope | Subject Source | Replay Class | Visibility Filter | Rate Limit Key | 来源 IDL |
|--------|-------------|---------------|------------|----------------|----------------|--------------|-------------------|----------------|----------|
| `swarm_get_world_stats` | `{scope, limit}` | `{stats: [{player, gcl, rooms, drones}]}` | 5/tick | `swarm:read` | `world` | `read_replay_safe` | `none` | `global` | game_api |
| `swarm_get_replay` | `{tick_range, player_id}` | `{ticks, entities, commands, events}` | 5/min | `swarm:read` | `world` | `read_replay_safe` | `fog_of_war` | `global` | game_api |
| `swarm_get_events` | `{room_id, tick_range}` | `{events: [{tick, type, data}]}` | 10/tick | `swarm:read` | `world` | `read_replay_safe` | `fog_of_war` | `per_room` | game_api |
| `swarm_get_terrain` | `{room_id, bounds}` | `{terrain_grid, size}` | — (host fn only) | `swarm:read` | `world` | `read_replay_safe` | `none` | `host_only` | game_api |
| `swarm_get_path` | `{from, to, player_id}` | `{path, distance, cost}` | — (host fn only) | `swarm:read` | `player_id` | `read_replay_safe` | `fog_of_war` | `host_only` | game_api |
| `swarm_get_visibility` | `{player_id}` | `{visible_rooms, visible_entities}` | 10/tick | `swarm:read` | `player_id` | `read_replay_safe` | `owner` | `per_player` | game_api |
| `swarm_list_controllers` | `{player_id}` | `{controllers: [{room, level, progress, owner}]}` | 10/tick | `swarm:read` | `player_id` | `read_replay_safe` | `fog_of_war` | `per_player` | game_api |
| `swarm_get_controller` | `{controller_id}` | `{room, level, progress, owner, downgrade_timer}` | 10/tick | `swarm:read` | `world` | `read_replay_safe` | `fog_of_war` | `per_room` | game_api |
| `swarm_list_structures` | `{room_id, player_id}` | `{structures: [{id, type, pos, hits}]}` | 10/tick | `swarm:read` | `player_id` | `read_replay_safe` | `fog_of_war` | `per_room` | game_api |
| `swarm_get_structure` | `{structure_id}` | `{id, type, pos, hits, capacity, cooldown}` | 10/tick | `swarm:read` | `world` | `read_replay_safe` | `fog_of_war` | `per_structure` | game_api |
| `swarm_get_messages` | `{drone_id}` | `{messages: [{from, content, tick}]}` | 10/tick | `swarm:read` | `drone_id` | `read_replay_safe` | `owner` | `per_drone` | game_api |
| `swarm_get_economy` | `{player_id}` | `{income, expenses, storage_tax, maintenance}` | 10/tick | `swarm:read` | `player_id` | `read_replay_safe` | `owner` | `per_player` | game_api |
| `swarm_get_drone_efficiency` | `{drone_id}` | `{efficiency, factors}` | 10/tick | `swarm:read` | `drone_id` | `read_replay_safe` | `owner` | `per_drone` | game_api |
| `swarm_get_economy_trend` | `{player_id, ticks}` | `{trend: [{tick, metric, value}]}` | 10/tick | `swarm:read` | `player_id` | `read_replay_safe` | `owner` | `per_player` | game_api |
| `swarm_profile` | `{player_id?}` | `{player_id, gcl, rooms, drones, joined_at}` | 10/tick | `swarm:read` | `player_id` | `read_replay_safe` | `owner` | `per_player` | game_api |
| `swarm_get_available_actions` | `{drone_id}` | `{actions: [{action, cost, cooldown, description}]}` | 10/tick | `swarm:read` | `drone_id` | `read_replay_safe` | `owner` | `per_drone` | game_api |

#### Deploy (7)

| 工具名 | Input Schema | Output Schema | Rate Limit | Required Scope | Subject Source | Replay Class | Visibility Filter | Rate Limit Key | 来源 IDL |
|--------|-------------|---------------|------------|----------------|----------------|--------------|-------------------|----------------|----------|
| `swarm_deploy` | `{player_id, drone_id, deploy_payload, code_signature, certificate_id, version_counter, metadata}` | `{deploy_id, accepted, validation_errors, redb_version_counter}` | 10/h | `swarm:deploy` | `player_id` | `deploy_mutation` | `owner` | `per_player` | game_api |
| `swarm_validate_module` | `{wasm_bytes}` | `{valid, errors, fuel_estimate}` | 10/h | `swarm:deploy` | `player_id` | `read_replay_safe` | `none` | `per_player` | game_api |
| `swarm_get_deploy_status` | `{deploy_id}` | `{status, errors, deployed_at, redb_version_counter}` | 20/tick | `swarm:read` | `player_id` | `read_replay_safe` | `owner` | `per_player` | game_api |
| `swarm_list_deployments` | `{player_id}` | `{deployments: [{id, drone_id, status, at, redb_version_counter}]}` | 20/tick | `swarm:read` | `player_id` | `read_replay_safe` | `owner` | `per_player` | game_api |
| `swarm_get_world_config` | `{}` | `{rules, mods, limits, tick_rate}` | 10/tick | `swarm:read` | `world` | `read_replay_safe` | `none` | `global` | game_api |
| `swarm_get_world_rules` | `{}` | `{rule_modules, parameters, version}` | 10/tick | `swarm:read` | `world` | `read_replay_safe` | `none` | `global` | game_api |
| `swarm_list_modules` | `{player_id}` | `{modules: [{id, drone_id, hash, language, size, deployed_at, status}]}` | 10/tick | `swarm:read` | `player_id` | `read_replay_safe` | `owner` | `per_player` | game_api |

> **swarm_deploy** 使用 `deploy_mutation` replay class (R16 B6, R22 B1, D4 统一): Deploy 为同步提交。请求内的 `deploy_payload`、`code_signature`、`certificate_id`、`version_counter` 一并进入 redb 原子事务；服务端验证签名、证书与版本计数器后，同步写入 deploy manifest 并返回 `redb_version_counter`。Deploy 完整状态机见 `specs/core/05-persistence-contract.md` §2.3。Replay verifier 以 `redb_version_counter` 全序重放，replay-critical 字段清单见 `05-persistence-contract.md` §2.1。

#### Debug (8)

| 工具名 | Input Schema | Output Schema | Rate Limit | Required Scope | Subject Source | Replay Class | Visibility Filter | Rate Limit Key | 来源 IDL |
|--------|-------------|---------------|------------|----------------|----------------|--------------|-------------------|----------------|----------|
| `swarm_get_tick_trace` | `{tick}` | `{commands, state_diff, rejections, metrics}` | 30/tick | `swarm:debug` | `world` | `read_replay_safe` | `admin_scope` | `global` | game_api |
| `swarm_get_engine_stats` | `{}` | `{tick_duration, player_count, memory, cpu, sandbox_stats}` | 30/tick | `swarm:debug` | `world` | `read_replay_safe` | `admin_scope` | `global` | game_api |
| `swarm_get_sandbox_profile` | `{drone_id}` | `{fuel_used, host_calls, memory_peak, execution_time}` | 30/tick | `swarm:debug` | `drone_id` | `read_replay_safe` | `admin_scope` | `per_drone` | game_api |
| `swarm_list_errors` | `{player_id, limit}` | `{errors: [{tick, drone, code, detail}]}` | 20/tick | `swarm:debug` | `player_id` | `read_replay_safe` | `admin_scope` | `per_player` | game_api |
| `swarm_get_state_checksum` | `{tick}` | `{checksum, algorithm, scope}` | 30/tick | `swarm:debug` | `world` | `read_replay_safe` | `admin_scope` | `global` | game_api |
| `swarm_simulate` | `{commands, assumptions}` | `{trace, authoritative: false, assumptions, confidence}` | 50/tick | `swarm:debug` | `player_id` | `read_replay_safe` | `owner` | `per_player` | game_api |
| `swarm_dry_run` | `{wasm_bytes, tick_count}` | `{trace, fuel_used, errors}` | 50/tick | `swarm:debug` | `player_id` | `read_replay_safe` | `owner` | `per_player` | game_api |
| `swarm_explain_last_tick` | `{drone_id}` | `{explanation, commands_executed, commands_rejected, events}` | 10/tick | `swarm:debug` | `drone_id` | `read_replay_safe` | `owner` | `per_drone` | game_api |

#### Admin (6)

| 工具名 | Input Schema | Output Schema | Rate Limit | Required Scope | Subject Source | Replay Class | Visibility Filter | Rate Limit Key | 来源 IDL |
|--------|-------------|---------------|------------|----------------|----------------|--------------|-------------------|----------------|----------|
| `swarm_admin_challenge` | `{challenge, signature}` | `{granted, scope, expiry}` | 5/min | `swarm:admin` | `admin_id` | `admin_critical` | `admin_scope` | `per_admin` | game_api |
| `swarm_admin_set_world_config` | `{key, value}` | `{accepted, applied_at}` | 10/h | `swarm:admin` | `admin_id` | `admin_critical` | `admin_scope` | `per_admin` | game_api |
| `swarm_admin_rollback` | `{target_tick}` | `{rollback_id, state}` | 5/h | `swarm:admin` | `admin_id` | `admin_critical` | `admin_scope` | `per_admin` | game_api |
| `swarm_admin_ban_player` | `{player_id, reason, duration}` | `{banned, expiry}` | 10/h | `swarm:admin` | `admin_id` | `admin_critical` | `admin_scope` | `per_admin` | game_api |
| `swarm_admin_force_gc` | `{scope}` | `{freed_bytes, duration}` | 5/h | `swarm:admin` | `admin_id` | `admin_critical` | `admin_scope` | `per_admin` | game_api |
| `swarm_admin_get_audit_log` | `{scope, limit}` | `{entries: [{timestamp, actor, action, detail}]}` | 30/tick | `swarm:admin` | `admin_id` | `read_replay_safe` | `admin_scope` | `per_admin` | game_api |

#### SDK (1)

| 工具名 | Input Schema | Output Schema | Rate Limit | Required Scope | Subject Source | Replay Class | Visibility Filter | Rate Limit Key | 来源 IDL |
|--------|-------------|---------------|------------|----------------|----------------|--------------|-------------------|----------------|----------|
| `swarm_sdk_fetch` | `{language, include_examples}` | `{sdk_code, type_definitions, examples, abi_version, min_engine_version}` | 5/min | `swarm:read` | `world` | `read_replay_safe` | `none` | `global` | game_api |

#### Arena (`all_declared=4`, `active_only=1`, `rfc_gated=3`)


| 工具名 | Input Schema | Output Schema | Rate Limit | Required Scope | Subject Source | Replay Class | Visibility Filter | Rate Limit Key | 来源 IDL |
|--------|-------------|---------------|------------|----------------|----------------|--------------|-------------------|----------------|----------|
| `swarm_match_result` | `{match_id}` | `{match_id, winner?, scores, duration_ticks, replay_url?}` | 10/tick | `swarm:read` | `world` | `read_replay_safe` | `none` | `global` | game_api |
| `swarm_get_leaderboard` | `{scope, limit}` | `{entries: [{player, gcl, rooms, drones}]}` | 5/tick | `swarm:read` | `world` | `read_replay_safe` | `none` | `global` | game_api | **RFC-LEADERBOARD** |
| `swarm_tournament_create` | `{name, rules, start_at?}` | `{tournament_id, status}` | 10/h | `swarm:admin` | `admin_id` | `admin_critical` | `admin_scope` | `per_admin` | game_api | **RFC-TOURNAMENT** |
| `swarm_tournament_precommit` | `{tournament_id, player_id, wasm_hash}` | `{accepted, precommit_id}` | 1/tick | `swarm:deploy` | `player_id` | `idempotent_mutation` | `owner` | `per_player` | game_api | **RFC-TOURNAMENT** |
| `swarm_tournament_status` | `{tournament_id}` | `{tournament_id, status, players, tick, brackets}` | 10/tick | `swarm:read` | `world` | `read_replay_safe` | `none` | `global` | game_api | **RFC-TOURNAMENT** |

> **RFC-TOURNAMENT** / **RFC-LEADERBOARD**: Tournament/League 为上层编排，leaderboard 为 Product 扩展项。这些工具 schema 计入 `all_declared` 与 `rfc_gated`，但不计入 `active_only`，当前不实现——返回 `ERR_FEATURE_GATED`。当前仅提供 `swarm_match_result`（房间赛后摘要）。

#### Resources (2)

| 工具名 | Input Schema | Output Schema | Rate Limit | Required Scope | Subject Source | Replay Class | Visibility Filter | Rate Limit Key | 来源 IDL |
|--------|-------------|---------------|------------|----------------|----------------|--------------|-------------------|----------------|----------|
| `resources/list` | `{}` | `{resources: [{type, name, category}]}` | 50/tick | `swarm:read` | `world` | `read_replay_safe` | `none` | `global` | game_api |
| `resources/read` | `{resource_type}` | `{type, name, category, base_value, rarity}` | 50/tick | `swarm:read` | `world` | `read_replay_safe` | `none` | `global` | game_api |

### 3.3 Auth API 工具 (`all_declared=12`, `active_only=12`, `rfc_gated=0`)

> **R33 B4 证书链重写**: game_api §3.2 Auth 表中的 `schema_source` 和 `alias_of` 列使 codegen 自动跳过 auth shortcuts，从 `auth_api.idl.yaml` canonical source 生成唯一实现。

**来源 IDL**: auth_api.idl.yaml

Auth API 提供 7 个 CSR/certificate lifecycle 工具 + 5 个 device/recovery/federation 工具，总计 12 个。全部基于应用层证书链 (Ed25519)，不依赖 bearer token 或 TLS/mTLS。

#### CSR Lifecycle (7)

| 工具名 | Input Schema | Output Schema | Rate Limit | Required Scope | Subject Source | Replay Class | Visibility Filter | Rate Limit Key |
|--------|-------------|---------------|------------|----------------|----------------|--------------|-------------------|----------------|
| `swarm_register_challenge` | `{}` | `{challenge_id, challenge, difficulty_bits=24, expires_at}` | 10/min | `none` | `none` | `non_replayable` | `none` | `per_ip` |
| `swarm_submit_csr` | `{username, csr, certificate_profile, device_label, challenge_id, nonce, csr_signature, recovery_password?}` | `{certificate_bundle: {client_auth_cert, code_signing_cert, cert_id, player_id, public_key_fingerprint, issued_at, expires_at}}` | 1/30s | `none` | `none` | `non_idempotent_mutation` | `none` | `per_ip` |
| `swarm_renew_certificate` | `{certificate_id, renewal_csr, proof_signature}` | `{certificate_bundle}` | 5/min | `swarm:auth` | `player_id` | `idempotent_mutation` | `owner` | `per_player` |
| `swarm_revoke_certificate` | `{certificate_id, reason}` | `{revoked, revocation_time, crl_updated}` | 5/min | `swarm:auth` | `player_id` | `admin_critical` | `owner` | `per_player` |
| `swarm_cert_list` | `{status?}` | `{certificates: [{cert_id, usage, device_label, fingerprint, issued_at, expires_at, status, managed_by_server}]}` | 30/min | `swarm:auth` | `player_id` | `read_replay_safe` | `owner` | `per_player` |
| `swarm_cert_check` | `{certificate_id}` | `{valid, player_id, usage, scope, audience, expires_at, revoked}` | 100/min | `swarm:auth` | `player_id` | `read_replay_safe` | `owner` | `per_player` |
| `swarm_get_server_trust` | `{}` | `{server_id, root_ca_fingerprint, intermediate_ca_fingerprint, supported_algorithms, supported_audiences}` | 30/min | `none` | `none` | `read_replay_safe` | `none` | `global` |

> **CSR challenge PoW（S-H3）**: `swarm_register_challenge.difficulty_bits` 固定为 **24 bits**。`swarm_submit_csr.nonce` 必须使 challenge preimage 满足该难度；低于 24 bits 的 challenge 或提交不得接受。

#### Device / Recovery / Federation (5)

| 工具名 | Input Schema | Output Schema | Rate Limit | Required Scope | Subject Source | Replay Class | Visibility Filter | Rate Limit Key |
|--------|-------------|---------------|------------|----------------|----------------|--------------|-------------------|----------------|
| `swarm_device_register` | `{device_id, device_name, device_fingerprint, public_key, metadata}` | `{registered, device_id, registration_time}` | 30/min | `swarm:auth` | `player_id` | `idempotent_mutation` | `owner` | `per_player` |
| `swarm_device_list` | `{}` | `{devices: [{device_id, device_name, registered_at, last_seen, status, active_certificates}]}` | 30/min | `swarm:auth` | `player_id` | `read_replay_safe` | `owner` | `per_player` |
| `swarm_passkey_register` | `{passkey_credential}` | `{registered, credential_id}` | 10/min | `swarm:auth` | `player_id` | `idempotent_mutation` | `owner` | `per_player` |
| `swarm_recovery_email_bind` | `{email}` | `{bound, verification_sent}` | 5/min | `swarm:auth` | `player_id` | `idempotent_mutation` | `owner` | `per_player` |
| `swarm_federation_identity` | `{target_server_id}` | `{federation_token, target_player_id, expires_at}` | 5/min | `swarm:auth` | `player_id` | `idempotent_mutation` | `owner` | `per_player` |

### 3.4 Capability Profiles

MCP 工具按 capability profile 分组。每个工具可属于多个 profile（如 `swarm_get_drone` 同属 play + debug）。

工具按 profile 分组，控制 MCP 客户端的能力面：

| Profile | 包含分类 | 默认分配 |
|---------|---------|---------|
| `onboarding` | Onboarding, Auth, SDK, Resources | 所有已认证客户端 |
| `play` | Play (含 `swarm_get_world_stats` — World 非竞争统计) | World 玩家，Arena spectator |
| `deploy` | Deploy | 所有已认证客户端 |
| `debug` | Debug | 开发者 / Arena host |
| `admin` | Admin | 服主 / Admin 证书 |
| `arena` | Arena (`swarm_match_result` 仅 — 房间赛后摘要) | Arena host / 赛事管理员 |

### 3.5 WebSocket 通道安全

**来源 IDL**: game_api

| 通道类型 | 安全模型 | 说明 |
|---------|---------|------|
| **Agent WS** (MCP/sandbox) | 每消息 seq + canonical MAC (ed25519) | 每条消息按 `SWARM-WS-MSG-V1` canonical payload 签名。重放检测：seq 必须严格递增（`seq == last_seq + 1`），否则断开。签名覆盖 `direction`、`session_id`、`seq`、`tick`、`body_hash`、`audience` |
| **Browser WS** (展示/观战) | 只读 | 浏览器 WebSocket 仅接收广播（tick delta, 事件流），不允许发送命令。写操作通过 MCP/HTTP 路径 |
| **Replay WS** | 只读 + seek | 回放客户端可请求历史 tick 范围，但不能注入新命令 |

Agent WS 每消息认证使用 `SWARM-WS-MSG-V1` canonical payload：`direction || session_id || seq || tick || body_hash || audience`，各字段采用规范编码后签名，`body_hash` 为消息 body 的 canonical hash。server 端仅在验证签名且 `seq == last_seq + 1` 后更新 `last_seq`；seq 跳号、回退、重复或 MAC 不匹配 → 断开连接并审计日志。

---

> **R27 ML-8 — IDL 字段注解规范**: `game_api.idl.yaml` 与 `auth_api.idl.yaml` 中的每个工具参数和返回字段必须标注 `required`/`optional`/`default` 三元组，以及每个工具的 `errors` 列表（按 canonical rejection reason）。SDK stub 生成和 MCP schema 暴露依赖这些注解。当前 YAML 中仅部分字段有标注——需补齐全部工具。

## 4. Host Functions

WASM 模块通过 host function import 调用引擎服务。以下为权威签名与限制。

> ⚠️ **CI Gate**: 函数计数由 IDL YAML 自动生成。若与其他文档或 IDL 不一致，**禁止手工修改此数**——应修正 IDL YAML 源并重新运行 `generate_api_registry.py`。CI 检查模式拒绝手工编辑导致的不一致。

**来源 IDL**: game_api

### 4.1 函数签名

| # | 函数 | ABI 签名 | 只读 | 说明 |
|---|------|---------|:---:|------|
| 1 | `host_get_terrain` | `(room_id: u32, out_ptr: i32, out_len: i32) -> i32` | ✅ | Get room terrain data |
| 2 | `host_get_objects_in_range` | `(x: i32, y: i32, range: u32, out_ptr: i32, out_len: i32) -> i32` | ✅ | Get entities within range of (x,y) |
| 3 | `host_path_find` | `(from_x: i32, from_y: i32, to_x: i32, to_y: i32, opts_ptr: i32, opts_len: i32, out_ptr: i32, out_len: i32) -> i32` | ✅ | A* pathfinding |
| 4 | `host_get_world_config` | `(key_ptr: i32, key_len: i32, out_ptr: i32, out_len: i32) -> i32` | ✅ | Read world configuration value |
| 5 | `host_get_world_rules` | `(rule_id_ptr: i32, rule_id_len: i32, out_ptr: i32, out_len: i32) -> i32` | ✅ | Read rule module data |
| 6 | `host_get_random` | `(sequence: u64, out_ptr: i32, out_len: i32) -> i32` | ✅ | Deterministic random bytes from engine PRNG |

> **`host_get_random` domain separation（B2）**: `host_get_random(sequence, out_ptr, out_len)` 由引擎内部 `derive_rng(domain, world_seed, tick, actor_or_entity_id, sequence)` 派生确定性随机字节。`domain`、`world_seed`、`tick`、`actor_or_entity_id`、`sequence` 以 length-delimited encoding 串接后进入 KDF/PRNG，避免字段拼接歧义与跨域碰撞。相同输入必须产生相同输出；不同 domain、actor/entity 或 sequence 必须形成独立随机流。该函数为只读查询，不改变世界状态。

### 4.2 调用预算

| 限制项 | 值 |
|--------|-----|
| Host call 总预算 | **1,000/tick/player** |
| `host_get_objects_in_range` 上限 | **5/tick** |
| `host_path_find` 上限 | **10/tick** |
| `host_get_world_config` 上限 | **5/tick** |
| `host_get_world_rules` 上限 | **1/tick** |
| `host_get_random` 上限 | **10/tick** |
| `host_get_terrain` | 计入总预算，无单独上限 |

### 4.3 输出上限

| 函数 | 最大输出 |
|------|---------|
| `host_path_find` | **8 KB** |
| `host_get_objects_in_range` | **64 KB** |
| `host_get_world_config` | **16 KB** |
| `host_get_world_rules` | **16 KB** |
| `host_get_terrain` | **8 KB** |
| `host_get_random` | **256 bytes** |

### 4.4 Per-Call Fuel 成本

| 函数 | 基础 fuel | 增量 |
|------|----------|------|
| `host_get_terrain` | 500 | — |
| `host_get_objects_in_range` | 2000 | +100/entity |
| `host_path_find` | 500 × nodes | +200 × edges |
| `host_get_world_config` | 1000 | — |
| `host_get_world_rules` | 1000 | — |
| `host_get_random` | 200 | +10/32 bytes |

### 4.5 Host Function ABI 错误优先级

当多个错误条件同时满足时，按以下优先级返回：

**来源 IDL**: game_api

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

**来源 IDL**: game_api (primary), economy (complementary)

### 5.1 游戏限制

**来源 IDL**: game_api

| 参数 | 值 | 说明 |
|------|-----|------|
| **Commands/player/tick** | **100** | per-player 最大指令数 |
| **Per-player drone cap** | **50** | world.toml 可调；per-room per-player baseline（R23 D2/B 三层 cap） |
| **Per-room drone cap** | **500** | world.toml；RCL 表定义 room-level total，与 per-player cap 取较小值 |
| **Global drone cap** | **10,000** | 全局活跃 drone 上限 |
| **Global entity cap** | **50,000** | 全局实体上限 |
| **Drone lifespan** | **1500 ticks** | 默认值 |
| **MAX_BODY_PARTS** | **50** | 每 drone 最大部件数 |
| **MAX_CONSTRUCTION_SITES** | **100** | 全局在建上限 |
| **Safe mode duration** | **500 ticks** | 默认值 |
| **Reservation timeout** | **1000 ticks** | 房间保留超时 |
| **Downgrade timer** | **5000 ticks** | 控制器降级倒计时 |
| **Global storage capacity** | **1,000,000 units** | world.toml 可调 |
| **Starting resources** | `{Energy: 5000}` | 新玩家初始资源包 — R35 D6: Vanilla 默认单一 Energy |
| **Free upkeep controllers** | 1 | 免维护费 controller 数量（R23 D1/A） |
| **Free upkeep drones** | 3 | 免维护费 drone 数量（R23 D1/A） |
| **Free upkeep ticks** | 2000 | 免维护费持续时间（R23 D1/A） |
| 无全局 repair cap — 维修受物理范围（repair_range）和 per-Controller 容量（repair_capacity）自然限制 |
| **Repair distance decay** | 500 bp/tile | repair 距离衰减（R23 D4/A） |

### 5.2 WASM 限制

**来源 IDL**: game_api

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

**来源 IDL**: game_api

| 级别 | 保留时长 |
|------|---------|
| hot | 7d |
| warm | 30d |
| cold | 180d |

### 5.4 Replay 参数

**来源 IDL**: game_api

| 参数 | 值 | 说明 |
|------|-----|------|
| Replay keyframe 间隔 | **K=100 ticks** | keyframe 写入频率 |
| `code_update_cooldown` | **5 ticks** | World 最小值；world.toml 可配 |

### 5.5 硬件基线 (Hardware Baseline)

**来源 IDL**: game_api

| 参数 | 值 | 说明 |
|------|-----|------|
| **Target active players** | **500** | 64 GB RAM, 32 cores。实际容量由压力测试确定——tick 时间可随负载弹性增加 |
| **Hard cap players** | **1000** | ⚠️ **benchmark-gated**（未验证）。超限进入 degraded mode，入场门控 (admission gating)。实际 hard cap 由压力测试在目标硬件上测定 |
| **Worker pool size** | `min(max_pool, active_players)` | max_pool 默认 256，World 模式 |
| **Worker pool max** | **256** | 运行时默认值 (world.toml 可调) |
| **Worker pool hard cap** | **1000** | 编译期硬上限 |
| **Degraded mode** | 超过 hard cap 时拒绝新 WASM 执行 | 已在 tick 中的玩家继续运行 |

### 5.6 Per-Player Fair-Share Admission

**来源 IDL**: game_api

| 资源 | 全局预算 | 分配策略 |
|------|---------|---------|
| **Pathfinding explored nodes** | 100,000 / tick | 每玩家份额 = `floor(100,000 / active_players)`，先到先得，超出即 `ERR_BUDGET_EXHAUSTED`。tick 开始时计算份额，整个 tick 不变 |
| **Host call budget** | 1,000 / tick / player | 固定 per-player cap |
| **Snapshot per-player** | 256 KB | 固定 per-player cap |

### 5.7 Economy 限制

**来源 IDL**: economy

| 参数 | 值 | 说明 |
|------|-----|------|
| **Max storage per player** | **1,000,000 units** | Per-player global storage capacity (world.toml 可调) |
| **Global resource cap** | **100,000,000 units** | World-wide total resource cap across all players |
| **Max single transfer** | **100,000 units** | Maximum resource units in a single transfer operation |
| **Max per-tick income** | **1,000,000 units/tick** | Hard cap on total resource income per player per tick |
| **Max per-tick expense** | **1,000,000 units/tick** | Hard cap on total resource deductions per player per tick |
| **Storage tax tier 1 threshold** | **30% capacity** | Tier-1 storage tax begins at 30% of max storage capacity (1 bp). 权威定义见 Resource Ledger §2.2 |
| **Storage tax tier 2 threshold** | **60% capacity** | Tier-2 storage tax begins at 60% of max storage capacity (5 bp) |
| **Storage tax tier 3 threshold** | **85% capacity** | Tier-3 storage tax begins at 85% of max storage capacity (20 bp) |
| **Max active alliances** | **10** | Maximum number of active alliances per player |

### 5.8 Auth 限制

**来源 IDL**: auth_api

| 参数 | 值 | 说明 |
|------|-----|------|
| **Max active certificates per player** | **10** | Per-player certificate cap |
| **Max active devices per player** | **5** | Per-player device cap |
| **CSR challenge TTL** | **300s** | PoW challenge 有效期 |
| **CSR challenge default difficulty** | **24 bits** | 固定难度（S-H3） |
| **Failed CSR lockout threshold** | **5 attempts** | 同 username 连续失败 |
| **Failed CSR lockout window** | **15m** | |
| **Failed CSR lockout duration** | **30m** | |
| **Certificate validity max** | **365d** | |
| **ClientAuthCertificate TTL** | **15 min–180 days** | world.toml 可配 |
| **CodeSigningCertificate TTL** | **30–180 days (default 30d)** | world.toml 可配 |
| **AdminCertificate TTL** | **15 min–1h** | |
| **FederationCertificate TTL** | **24h** | |
| **Canonical request nonce window** | **60s** | SWARM-REQUEST-V1 timestamp/nonce |

---

## 6. TickTrace Envelope

Replay 确定性依赖 TickInputEnvelope 的完整性。**共计 22 个字段**。

**来源 IDL**: game_api

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

**来源 IDL**: game_api

| 值 | 名称 | 说明 |
|:--:|------|------|
| 0 | `Success` | WASM execution completed successfully, commands produced |
| 1 | `FuelExhausted` | WASM fuel budget exhausted before completion |
| 2 | `TimeoutExceeded` | WASM execution exceeded wall-clock deadline |
| 3 | `SnapshotOverBudget` | Input snapshot exceeded per-player size budget |
| 4 | `CommandBufferFull` | Output command buffer exceeded capacity |
| 5 | `InternalError` | Engine internal error during WASM execution |
| 6 | `NotExecuted` | WASM was not executed this tick (e.g., replay from snapshot, degraded mode skip) |

### 6.2 Auth Tick Trace Events

**来源 IDL**: auth_api
**总事件类型**: 8

| # | Event | Fields | Replay Class | 说明 |
|---|-------|--------|--------------|------|
| 1 | `auth_csr_submit` | `tick, player_id, username, certificate_profile, ip_address, success, rejection_code` | `non_replayable` | Emitted on swarm_submit_csr |
| 2 | `auth_cert_issue` | `tick, player_id, cert_id, usage, fingerprint, issued_at, expires_at` | `admin_critical` | Emitted when certificate is issued |
| 3 | `auth_cert_renew` | `tick, player_id, old_cert_id, new_cert_id, new_fingerprint` | `idempotent_mutation` | Emitted on swarm_renew_certificate |
| 4 | `auth_cert_revoke` | `tick, actor_id, target_player_id, cert_id, reason` | `admin_critical` | Emitted on certificate revocation |
| 5 | `auth_device_register` | `tick, player_id, device_id, device_name, device_fingerprint` | `idempotent_mutation` | Emitted on swarm_device_register |
| 6 | `auth_recovery_bind` | `tick, player_id, recovery_type, success` | `non_replayable` | Emitted on recovery email/passkey binding |
| 7 | `auth_rate_limit_hit` | `tick, endpoint, key_type, key_value, current_count, limit` | `non_replayable` | Emitted when auth endpoint rate limit is exceeded |
| 8 | `auth_security_alert` | `tick, alert_type, severity, player_id, ip_address, detail` | `non_replayable` | Emitted when auth subsystem detects security-relevant anomaly |

---

## 7. Direction4 枚举

**来源 IDL**: game_api

Move 指令使用 4 方向：

| 名称 | 值 |
|------|:--:|
| North | 0 |
| South | 1 |
| East | 2 |
| West | 3 |

8 方向（含 NE/NW/SE/SW）为 Out-of-Scope RFC，不在当前核心定义中。

---

## 8. SwarmError JSON-RPC Envelope

**来源 IDL**: game_api

MCP/API 错误统一格式遵循 JSON-RPC 2.0 error object。`error.code` 为 numeric code；Swarm application error 固定使用 `-32000`，具体 canonical wire enum 通过 `error.data.rejection_reason` 承载（见 §2 RejectionReason）。所有错误上下文通过 `error.data.debug_detail` 传递，**不**在 wire enum 中增加新变体。

```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32000,
    "message": "Human-readable summary (max 256 chars)",
    "data": {
      "rejection_reason": "InsufficientResource",
      "command_index": "u32 (optional, batch command index)",
      "debug_detail": "max 512 bytes — non-canonical contextual detail",
      "retry_allowed": "bool (optional, machine-readable)",
      "idempotency_key": "string | null (optional, machine-readable)",
      "retry_after_tick": "u64 | null (optional, machine-readable)"
    }
  },
  "id": "<request_id>"
}
```

### 8.1 字段说明

| 字段 | 类型 | 必需 | 说明 |
|------|------|:---:|------|
| `error.code` | `i32` numeric JSON-RPC code | ✅ | JSON-RPC 标准 numeric code；Swarm application error 使用 `-32000`，不得填 RejectionReason 字符串 |
| `error.message` | `string` (≤ 256 chars) | ✅ | 人类可读摘要 |
| `error.data.rejection_reason` | `RejectionReason` (canonical enum string) | ✅ | Wire enum，见 §2。SDK 据此生成 typed exception |
| `error.data.command_index` | `u32` | ❌ | 批量指令中失败指令的索引 |
| `error.data.debug_detail` | `string` (≤ 512 bytes) | ❌ | 人类可读的调试上下文。详细程度由 `detail_level` 控制（§2） |
| `error.data.retry_allowed` | `bool` | ❌ | 客户端可否安全重试。例：`TimeoutExceeded`/`RateLimited` → true；`InsufficientResource`/`NotOwner` → false |
| `error.data.idempotency_key` | `string \| null` | ❌ | 幂等重试 key。若提供，相同 key 的重试只执行一次（如 deploy 用 `module_hash`） |
| `error.data.retry_after_tick` | `u64 \| null` | ❌ | 建议重试的最早 tick。例：cooldown 剩余 12 ticks → `retry_after_tick = current_tick + 12` |

标准 JSON-RPC numeric `error.code = -32000` 保留给 Swarm 错误。具体错误以 `error.data.rejection_reason` 承载（canonical RejectionReason enum）。SDK 从 `rejection_reason` 生成 typed exception，不得依赖 `error.code` 的细分值。

---

## 9. Application-Layer Certificate Envelope

**来源 IDL**: auth_api

### Certificate Types

| Type | Usage | Audience | TTL | Renewal |
|------|-------|----------|-----|---------|
| `ClientAuthCertificate` | `client_auth` | `swarm-aud-v1:<transport>:<server_id>:<world_id>:<player_id>` | 15 min–180 days | `swarm_renew_certificate` |
| `CodeSigningCertificate` | `code_signing` | `swarm-aud-v1:wasm-sdk:<server_id>:<world_id>:<player_id>` | 30–180 days (default 30d) | `swarm_renew_certificate` |
| `AdminCertificate` | `admin` | `swarm-aud-v1:cli-rest:<server_id>:<world_id>:<admin_id>` | 15 min–1h | manual only |
| `FederationCertificate` | `federation` | `swarm-aud-v1:federation:<source>:<target>:<player_id>` | 24h | re-federate per session |

### Canonical Request Signature (SWARM-REQUEST-V1)

Headers:
- `Swarm-Certificate-Chain: <base64 leaf + intermediate>`
- `Swarm-Cert-Id: <certificate_id>`
- `Swarm-Timestamp: <unix_ms>`
- `Swarm-Nonce: <random 128-bit>`
- `Swarm-Signature: <ed25519 signature>`

Signature payload (UTF-8, LF line endings):
```
SWARM-REQUEST-V1
method: <HTTP method or MCP tool name>
path: <HTTP path or MCP tool name>
body_hash: <blake3 canonical body hash>
timestamp: <unix_ms>
nonce: <nonce>
certificate_id: <certificate_id>
player_id: <player_id>
audience: <swarm-aud-v1:...>
```

Algorithm: Ed25519. Validation: cert chain → public key → signature → timestamp window (60s) → nonce → scope/audience.

### Transport Labels

| Label | Audience |
|-------|----------|
| `agent-mcp` | AI agent via MCP session |
| `cli-rest` | Human CLI or REST client |
| `wasm-sdk` | WASM SDK (deploy, code signing) |

---

## 10. Economy Operations

**来源 IDL**: economy.idl.yaml. **经济权威**: `specs/core/08-resource-ledger.md` 为所有费率/公式的数学权威。IDL 为机器 schema，本文档为生成产物——禁止手写经济数值。

Economy resource operations are engine-side computations, not player CommandActions. All amounts use integer types (u64/u32), all rates use BasisPoints. No f64.

### 10.1 ResourceOperation (CommandAction Subset, excludes Action dispatch combat operations)

**来源 IDL**: game_api

所有涉及资源操作的 action 类型（CommandAction 子集，不含 Action dispatch 中的 combat 操作）：

| Operation | Action # | 分类 | 说明 | Resource Flow |
|-----------|:-------:|------|------|---------------|
| `Harvest` | 2 | core | Harvest a resource from target entity | source → drone |
| `Transfer` | 3 | core | Transfer resources locally to target | drone → target |
| `Withdraw` | 4 | core | Withdraw resources from structure | structure → drone |
| `TransferToGlobal` | 12 | economy_operation | Deposit resources to global storage | drone → global |
| `TransferFromGlobal` | 13 | economy_operation | Withdraw resources from global storage | global → drone |

### 10.2 Economy Resource Operations

**来源 IDL**: economy

| # | Operation | Category | Trigger | Description |
|---|-----------|----------|---------|-------------|
| 1 | **RecycleRefund** | lifecycle | Recycle command (index 10) | Lifespan-proportional partial refund. Formula: `max(1000, (remaining_lifespan * 5000) / total_lifespan)` bp → `(rate_bp * body_cost) / 10000`. Clamped to [10%, 50%]. |
| 2 | **StorageTax** | taxation | Every tick, per player | Percentage-based tiered tax on global storage. Tiers: 0%–30% cap = 0 bp, 30%–60% = 1 bp, 60%–85% = 5 bp, 85%–100% = 20 bp. Per `specs/core/08-resource-ledger.md` §2.2 authoritative tiered formula. Min 1 unit if rate > 0. |
| 3 | **UpkeepDeduction** | maintenance | Every tick, per player | Empire-wide superlinear upkeep: `base_upkeep × rooms × (1 + rooms / room_soft_cap)`. Deducted from global storage. Standard defaults: base_upkeep=50, room_soft_cap=10. Per `specs/core/08-resource-ledger.md` §Empire Upkeep. |
| 4 | **PvEAward** | reward | On NPC entity destruction | Tiered: T1=100, T2=500, T3=2000, T4=10000, T5=50000. Entity type modifier in bp adjusts base. |
| 5 | **BuildCost** | construction | Build command (index 5) | Structure costs: Spawn=300, Extension=200, Road=10, Wall=50, Rampart=100, Storage=500, Tower=800, Link=400, Extractor=600, Lab=1000, Terminal=1200, Observer=500. Controller level discount: 100%→65% (L1→L8) in bp. |
| 6 | **SpawnCost** | lifecycle | Spawn command (index 9) | Body part costs: MOVE=50, WORK=100, CARRY=50, ATTACK=80, RANGED_ATTACK=150, HEAL=250, CLAIM=600, TOUGH=10. Max 50 body parts. Total = sum of part costs. |
| 7 | **AlliedTransfer** | transfer | TransferToGlobal + TransferFromGlobal (allied only) | Allied transfer with 200 bp (2.00%) fee. 200 tick delay. 500 tick cooldown per receiver. Daily cap: 10,000 units per receiver. Both players must share active alliance ≥ 100 tick. Per `specs/core/08-resource-ledger.md` §2.1. |

### 10.3 Canonical Formulas

**来源 IDL**: economy

| Formula | Steps | Rounding |
|---------|-------|----------|
| **RecycleRefund** | 1. `refund_rate_bp = max(1000, (remaining_lifespan * 5000) / total_lifespan)` (u32 → u32, clamp [1000, 5000] bp). 2. `refund_amount = (refund_rate_bp * body_cost) / 10000` (u32, u64 → u64). | floor |
| **StorageTax** | 1. `storage_pct = stored_total / storage_capacity × 100`. 2. For each percentage tier i: `taxable = min(storage_pct - threshold_pct[i], tier_width[i]) × capacity; tax += taxable × rate_bp[i] / 10000`. Per `resource-ledger.md` §2.2 tiered formula. | floor |
| **BuildCostDiscounted** | 1. `discounted_cost = (base_cost * discount_factor_bp) / 10000` (u64, u32 → u64). | floor |
| **SpawnCost** | 1. `total = sum(part_cost for each body_part)` ([u64] → u64). | exact (additive) |

---

## 11. Deploy — deploy_mutation 同步提交机制 (R16 B6, D4)

**来源 IDL**: game_api

### 架构

Deploy 子系统使用 deploy_mutation 模式：`swarm_deploy` 同步提交 `deploy_payload`、`code_signature`、`certificate_id`、`version_counter` 与 metadata。redb 在单个原子事务中验证并写入 deploy manifest，同时递增并返回 `redb_version_counter`。部署提交不依赖异步 blob 上传路径；replay 以 redb manifest 与 `redb_version_counter` 为权威。

### redb_version_counter

| 属性 | 值 |
|------|-----|
| 类型 | `u64` |
| 原子性 | 与 deploy manifest 在同一 redb WriteTransaction 中递增 |
| Replay 合约 | deploy events 必须按 redb_version_counter 升序重放 |

### Deploy Flow

| 步骤 | 描述 | Actor |
|:----:|------|-------|
| 1. Validate | Client 调用 `swarm_validate_module`，或在 `swarm_deploy` 中提交完整 `deploy_payload` 供服务端同步验证 | client / engine |
| 2. Authenticate | 服务端验证 `code_signature`、`certificate_id` 与 `version_counter`，拒绝签名、证书或版本计数器不匹配的提交 | engine |
| 3. Commit Manifest | redb WriteTransaction 提交 manifest record: `{deploy_id, drone_id, deploy_payload_hash, certificate_id, version_counter, metadata, redb_version_counter}` | engine |
| 4. Activate | 下一 tick boundary，引擎按已提交 manifest 在 drone 上激活代码（延迟到 tick boundary 以保证确定性调度） | engine |

### swarm_deploy 输出

| 字段 | 类型 |
|------|------|
| `deploy_id` | DeployId |
| `accepted` | bool |
| `validation_errors` | [string] |
| `redb_version_counter` | u64 |

---

## 12. Persistence — async_object_store_upload (D5/B, R22 B1)

**来源 IDL**: game_api. **权威合同**: `specs/core/05-persistence-contract.md` §2 Replay-Critical Subset。Deploy 提交语义以 §11 同步 deploy_mutation 为准。

### 概述

Persistence 层处理非 deploy 的大型二进制对象存储（如 replay recording、snapshot archive）。Per D5/B + R22 B1：redb WriteTransaction 原子提交 **replay-critical subset**（10 项必填字段，见 `05-persistence-contract.md` §2.1）；辅助 object-store blob 上传可异步执行并通过 manifest 记录审计状态。Deploy payload 不走本节异步上传路径。

### async_object_store_upload

| 属性 | 值 |
|------|-----|
| Storage Backend | pluggable (default: local filesystem; production: S3-compatible) |
| 调用方式 | fire-and-forget for non-deploy large artifacts |
| 确认 | immediate — 返回 object_store_key |
| 完成轮询 | 使用对应 artifact status API 检查上传完成状态 |
| 失败模式 | retry with exponential backoff (max 3 attempts); permanent failure → artifact status failed |

### Blob Types

| 类型 | 最大大小 | 保留策略 | Content Hash |
|------|---------|---------|-------------|
| `wasm_module` | 64 MB | permanent (until all referencing drones are recycled) | Blake3 |
| `replay_recording` | 1 GB | per tick_trace_retention policy | Blake3 |
| `snapshot_archive` | 256 MB | per tick_trace_retention policy | Blake3 |

### redb Manifest Record

redb 每 blob 仅存储小型 manifest record: `{blob_hash, object_store_key, size, uploaded_at, status}`。此 record 是 deploy_mutation redb WriteTransaction 的一部分，受 redb_version_counter 排序覆盖。

| 字段 | 类型 |
|------|------|
| `blob_hash` | `[u8; 32]` |
| `object_store_key` | string |
| `size` | u64 |
| `uploaded_at` | u64 |
| `status` | `enum { pending, uploaded, failed }` |

---

## 13. Security Columns Reference

**来源 IDL**: auth_api

Every MCP/auth tool declaration includes these five security columns:

| Column | Description | Canonical Values |
|--------|-------------|------------------|
| **required_scope** | OAuth2-style scope required to invoke the tool | `swarm:auth`, `swarm:read`, `swarm:deploy`, `swarm:debug`, `swarm:admin` |
| **subject_source** | How the tool derives the subject (principal) for authorization | `none`, `player_id`, `admin_id`, `world`, `drone_id` |
| **replay_class** | Replay determinism classification | `non_replayable`, `read_replay_safe`, `idempotent_mutation`, `admin_critical`, `deploy_mutation` |
| **visibility_filter** | How output data is filtered based on caller's visibility | `none`, `owner`, `admin_scope`, `fog_of_war`, `owner_or_visible` |
| **rate_limit_key** | Key used for rate limit tracking | `per_ip`, `per_player`, `per_admin`, `per_device`, `per_session`, `global`, `per_room`, `per_drone`, `per_structure`, `host_only` |

---

## 变更记录

| 版本 | 日期 | 来源 | 变更 |
|------|------|------|------|
| 0.5.0 | 2026-06-18 | game_api | R35 D3: CommandAction 泛化为 11 个非战斗基础操作 + `Action` dispatch。`Attack`/`RangedAttack`/`Heal` 与 8 个 special attacks 移入 ActionRegistry；mod 通过 `world.toml` `[[action_registry]]` 扩展 combat/effect action。 |
| 0.4.0 | 2026-06-18 | game_api | MCP 工具注册: 新增 10 引擎工具入 IDL (Onboarding +2: swarm_get_docs/swarm_get_schema; Play +2: swarm_profile/swarm_get_available_actions; Deploy +1: swarm_list_modules; Debug +1: swarm_explain_last_tick; Arena +4: swarm_tournament_create/precommit/status + swarm_match_result)。MCP tools 总数为 56 active。新增 Arena capability profile。移除 v0.3.0 内联标记，保留 changelog。 |
| 0.3.0 | 2026-06-18 | game_api | B1: api_version → 0.3.0。B2/D2: RejectionReason 新增 debug_detail 字段 (512 bytes) + detail_level enum (competitive/practice/training)。B3: swarm_list_market_orders 移至 RFC；新增 Auth category (swarm_auth_login, swarm_auth_refresh)；MCP tools 为 46 active。B4: TickTrace envelope `wasm_status` → `terminal_state` 显式 enum (7 variants)。B5: Deploy 新增 deploy_mutation 机制 + redb_version_counter 输出。D5/B: 新增 Persistence (async_object_store_upload)。Host functions ABI 错误优先级表增加显式优先级编号。 |
| 0.1.0 | 2026-06-18 | auth_api | Initial auth API IDL: 5 lifecycle tools, 6 cert/device MCP tools, 12 canonical auth RejectionReason codes (namespace offset 1000+), 8 auth tick trace events, rate limits, token envelope specification, 5 security columns. |
| 0.1.1 | 2026-06-18 | economy | R22 B2: StorageTax changed to percentage-based tiers (30/60/85/100% capacity). UpkeepDeduction changed to superlinear empire upkeep. AlliedTransfer added 200bp fee + 200 tick delay + 500 tick cooldown + 10000 daily cap. Authority annotations added referencing resource-ledger.md. |
| 0.1.0 | 2026-06-18 | economy | Initial economy IDL: 7 resource operations (RecycleRefund, StorageTax, UpkeepDeduction, PvEAward, BuildCost, SpawnCost, AlliedTransfer). Fixed-point types only: BasisPoints, ResourceRate_i64, MilliUnits. 4-tier storage tax schedule (0/1/5/20 bp). RecycleRefund lifespan-proportional 10-50% refund formula. Economy-specific limits. All amounts in u64/u32 integer units. |
| 0.2.0 | 2026-06-18 | game_api | Initial structured IDL with 10 sections |
| 0.1.0 | 2026-06-18 | game_api | R15 B1+B4+H1: 初次建立权威注册表。统一 RejectionReason (35 变体)、CommandAction (19 指令)、MCP Tools (46)、Host Functions (5)、容量限制 (25 参数)、TickTrace Envelope (22 字段)、Direction4、错误格式。 |

---

## 附录 A: CLI 重新生成命令

在 CI 中执行以下命令以重新生成本文档：

```bash
# 从三个 IDL 源重新生成 api-registry.md
python3 scripts/generate_api_registry.py \
    --source game_api.idl.yaml \
    --source auth_api.idl.yaml \
    --source economy.idl.yaml \
    --output docs/specs/reference/api-registry.md

# 校验重新生成的文件与当前文件一致（CI 检查模式）
python3 scripts/generate_api_registry.py \
    --source game_api.idl.yaml \
    --source auth_api.idl.yaml \
    --source economy.idl.yaml \
    --output docs/specs/reference/api-registry.md \
    --check
```

若缺少 `generate_api_registry.py` 脚本，可使用以下最小替代方案（YAML 到 Markdown 的转换器）：

```bash
# 手动触发重新生成（依赖 yq 和 jinja2-cli）
yq eval-all '. as $item ireduce ({}; . * $item )' \
    game_api.idl.yaml auth_api.idl.yaml economy.idl.yaml \
    | jinja2 templates/api-registry.md.j2 > docs/specs/reference/api-registry.md
```

**CI 检查**: 在 PR 合并前运行 `--check` 模式以验证 api-registry.md 与 IDL 源一致。不一致时 CI 失败，阻止合并。
