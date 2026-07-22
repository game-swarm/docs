# Game API IDL Spec — 游戏 API 接口定义语言

> 详见 design/interface.md
>
> **本文档说明 IDL 的设计理念、架构边界和 SDK 协议。`*.idl.yaml` 是机器可读参考；[API Registry](../reference/api-registry.md) 是人类可读参考。Engine runtime IDL extraction 是独立表示，不读取文档 YAML，也不生成 Markdown。**

> **目标**: host functions / Command / Validator / SDK / MCP schema 单一真相来源

## 1. 原则

**IDL YAML 是下游 wire schema 的机器可读权威参考。** Design 定义 API 能力语义、信任边界和默认行为；下游 IDL/Registry 定义字段、类型、错误码和 Swarm codec/REST/MCP wire schema，不反向改变 design 语义。Registry 与 YAML 手工同步正文表格，并通过 `scripts/sync_api_registry.py` 同步生成 metadata/tool counts/API 版本；Engine extraction 从 Rust 类型和 runtime registries 构造另一份 `IdlDoc`。三者必须协调维护；三方自动 diff 的范围限定为 metadata/count/version 与明确输入的 Engine JSON 摘要。

**独立版本域**：`GAME_API_VERSION`、`AUTH_API_VERSION`、`ECONOMY_API_VERSION`、`PLUGIN_ABI_VERSION`、SDK package version 与 implementation crate version 彼此独立，必须显式命名，不能互相推导。

**Core IDL vs World Action Manifest 边界**：

- **Core IDL**（本文件 §2-4）：定义基础 envelope/ABI/host functions、14 个 `CommandAction` 变体：13 个非战斗基础指令（Move/Harvest/Transfer/Withdraw/ClaimController/Spawn/Recycle/Build/Repair/UpgradeController/TransferToGlobal/TransferFromGlobal/AlliedTransfer）以及统一 `Action { action_type, object_id, payload: ActionPayload<action_type> }` dispatch。Core IDL 长期稳定，ABI 版本号控制兼容性。
- **World Action Manifest / ActionRegistry**：定义 vanilla combat/effect action（Attack/RangedAttack/Heal + 8 special attacks）与模组扩展 action。包含 canonical hash（`Blake3(manifest)`）、版本 tag、TickTrace 绑定。WASM 模块通过 `target_manifest_hash` 声明兼容的世界版本。

```
文档参考：game_api.idl.yaml ↔ API Registry（手工同步）
运行时表示：Engine Rust registries → IdlDoc extraction → SDK text
轻量检查：链接 + 版本元数据 + 关键 gameplay 常量
```

### 2.0 WASM 导出与指令输出

WASM ABI v2 `tick(input_ptr, input_len, output_ptr, output_len)` 读取 Swarm codec `TickInput`，写入 Swarm codec `TickResult`。ABI v2 是立即 breaking 的唯一 ABI surface；tick input、tick output 和全部 host payload 都使用 IDL-generated、versioned、little-endian、length-prefixed Swarm codec。JSON 只可作为调试显示格式，不能作为 ABI v2 的 tick 或 host wire format。

```yaml
# TickResult.commands 中的元素
CommandIntent:
  additionalProperties: false
  required: [sequence, idempotency_key, action]
  fields:
    sequence: u32
    idempotency_key: string
    client_trace_id: string?
    action: CommandAction

TickResult:
  additionalProperties: false
  required: [commands]
  fields:
    commands: CommandIntent[]
    messages: Message[]
```

**IDL 定义的指令类型是 CommandIntent**——包含 `sequence`、required `idempotency_key`、optional `client_trace_id` 与 `action`。`player_id`、`source`、`tick` 由 Source Gate 注入形成 RawCommand。`TickResult.messages` 进入私有消息队列。


**Schema 不可扩展性**：所有 JSON schema（CommandIntent、每个 Command action、MCP tool input/output、REST API response）默认设置 `additionalProperties: false`——拒绝未知字段。唯一例外需在本文件中显式声明。此规则防止字段注入攻击和实现分叉：不同实现者看到同一 schema 不会因未知字段处理策略不同而产生分歧。

**扩展 action 的字段**：`CommandIntent.action` 内部使用 `Action { action_type, object_id, payload: ActionPayload<action_type> }` 派发到 ActionRegistry；wire `type` 为具体 action 名称，selected payload fields 扁平化。vanilla action 的参数结构来自 core ActionRegistry，mod action 的参数结构来自 enabled signed-plugin World Action Manifest；每个 concrete payload schema `additionalProperties: false`。Action gameplay parameters 来自 typed world config，Vanilla design-profile defaults 只在 design 中裁定；IDL 不声明冲突的固定 resistance/effect authority。

**ABI 向后兼容**：`abi_version` 每次 host function 签名变更时递增。ABI 公告期如下：
| 变更类型 | 公告期 | 替换前模块行为 |
|---|---|---|
| 新增 host function | 即时生效 | 替换前模块不受影响（不使用新函数即可） |
| 修改 host function 签名 | 至少 30 天公告期 | 公告期内替换前签名仍可用，公告期后替换前模块部署被拒（`abi_version_mismatch`） |
| 移除 host function | 至少 60 天公告期 | 公告期内标记 deprecated（WASM 收到 warning），公告期后移除 |

`abi_version` 变更记录在 IDL schema_notes 中。SDK、MCP schema、starter bot 随 `abi_version` 递增同步更新。SDK 获取的 canonical route 是 signed REST `GET /sdk/:lang`，不是 MCP 工具。

### 2.0.1 HostResult 与 HostError

Host payload 使用 Swarm codec。Host result bytes 使用 guest-buffer tagged header 后跟 payload：

```text
tag: u16
code: i32
payload_len: u32
payload: [u8; payload_len]
```

Host function 非负返回值表示 `bytes_written`；负返回值表示 ABI-level failure，例如 invalid guest pointer、输出缓冲不足、decode failure 或 fuel 在完整 header 写入前耗尽。Domain query errors 编码到 tagged `HostResult` header/payload，不作为负返回值。`HostError` 是独立 enum，既不等同于 REST/MCP `RejectionReason`，也不等同于负 ABI failure。隐藏或不存在的实体查询返回成功空结果，不能泄露目标是不可见还是不存在。

## 2. IDL 格式

```yaml
# game_api.idl — Swarm Game API Interface Definition

version: "1.0.0"
abi_version: 1                # 每次 host function 签名变更时递增

types:
  PlayerId: u64
  RoomId: u32
  ObjectId: u64
  Tick: u64
  ResourceName: String
  ResourceAmount: u32
  ResourceCost: Map<ResourceName, ResourceAmount>
  Position: { x: i32, y: i32, room: RoomId }

enums:
  Direction: [North, South, East, West]
  BodyPart:  [Move, Work, Carry, Attack, RangedAttack, Heal, Claim, Tough]
  DamageType: [Kinetic, Thermal, EMP, Sonic, Corrosive, Psionic]
  StructureType: [Spawn, Extension, Tower, Storage, Link, Extractor, Lab,
                  Terminal, Nuker, Observer, PowerSpawn, Factory, Depot]
  RejectionReason:
    # > 人类可读同步表见 [API Registry](../reference/api-registry.md#2-rejectionreason)
    - InvalidJson
    - SchemaViolation
    - ObjectNotFound
    - NotOwner
    - InsufficientResource
    - OutOfRange
    - NotStructure
    - NotController
    - NotVisibleOrNotFound
    - TargetNotVisible
    - SpawnOnCooldown
    - RoomDroneCapReached
    - AuthContextInvalid
    - CooldownActive
    - InvalidDirection
    - PositionOccupied
    - ConstructionLimitReached
    - SafeModeActive
    - TargetOverloadCooldown
    - TargetFortifyCooldown
    - NotEnoughBodyParts
    - InvalidBodyPart
    - InvalidStructureType
    - InvalidResourceType
    - SourceNotAllowed
    - UnknownAction
    - GlobalStorageDisabled
    - TransferInProgress
    - RateLimited
    - InvalidCertificate
    - NotAuthorized
    - FuelExhausted
    - TimeoutExceeded
    - SnapshotOverBudget
    - CommandBufferFull
    - ServerOverloaded
    - InternalError

commands:
  # Derived reference representation. Authority flows from design/engine.md through
  # command-validation.md and game_api.idl.yaml/API Registry.
  Move:
    params: { object_id: ObjectId, direction: Direction }
    validator: [exists, owner, drone, fatigue, body_part(Move), passable, !spawning]
    cost: {}   # 无资源消耗

  Harvest:
    params: { object_id: ObjectId, target_id: ObjectId, resource: ResourceName? }
    validator: [exists, owner, drone, body_part(Work,Carry), carry_space, is_source, source_not_empty, in_range(1), fatigue]
    cost: {}

  Transfer:
    params: { object_id: ObjectId, target_id: ObjectId, resource: ResourceName, amount: ResourceAmount }
    validator: [exists, owner, drone, body_part(Carry), has_resource, target_has_space, in_range(1)]
    cost: { transfer_amount: amount }

  Withdraw:
    params: { object_id: ObjectId, target_id: ObjectId, resource: ResourceName, amount: ResourceAmount }
    validator: [exists, owner, drone, body_part(Carry), target_has_resource, has_space, in_range(1)]
    cost: { withdraw_amount: amount }

  Build:
    params: { object_id: ObjectId, x: i32, y: i32, structure: StructureType }
    validator: [exists, owner, drone, body_part(Work,Carry), in_your_room, tile_empty, plain_terrain, under_construction_limit(100), in_range(3)]
    cost: registry.build_cost(structure)

  Repair:
    params: { object_id: ObjectId, target_id: EntityId }
    validator: [exists, owner, drone, body_part(Work,Carry), target_repairable, target_friendly, target_not_full, target_not_death_marked, has_resource(Energy), in_range(3)]
    accepted_amount: min(missing_hits, active_work_parts * combat.repair_hp_per_work_part, carried_energy / combat.repair_energy_per_hp)
    cost: { Energy: accepted_amount * combat.repair_energy_per_hp }
    emits: PendingHeal
    owner: S03_build_system

  Spawn:
    params: { object_id: ObjectId, spawn_id: SpawnId, body_parts: Vec<BodyPart> }
    stable_validator: [exists, owner, is_spawn, body_size(50), body_schema, has_resource(Energy, body_cost)]
    provisional_output: ProvisionalSpawnRequest
    volatile_admission: S08_after_S07_room_cap_release
    materialization: tick_end_creation_flush
    cost: registry.body_cost(body_parts)

  Recycle:
    params: { object_id: ObjectId }
    validator: [exists, owner, drone_or_structure]
    refund: RecycleRefund(body_cost, remaining_lifespan, total_lifespan)  # lifespan-proportional 10%-50%，从 design gameplay 派生

  # ═════════════════════════════════════
  # 扩展指令
  # ═════════════════════════════════════

  ClaimController:
    params: { object_id: ObjectId, target_id: EntityId }
    validator: [exists, owner, drone, body_part(Claim), is_controller, in_range(1)]
    cost: {}

  UpgradeController:
    params: { object_id: ObjectId, target_id: EntityId }
    validator: [exists, actor_owner, drone, body_part(Work,Carry), is_controller, target_owner, controller_level_below_8, in_range(3)]
    cost: { Energy: registry.upgrade_cost() }

  Action:
    params: { action_type: String, object_id: ObjectId, payload: ActionPayload<action_type> }
    wire: "type + object_id + the selected closed payload schema fields, flattened and encoded by the IDL-generated Swarm codec"
    payload_schema: "vanilla ActionRegistry parameters or enabled signed-plugin World Action Manifest parameters; additionalProperties=false"
    dispatch: built_in_action_handler_or_signed_plugin_ActionRegistry
    validator: resolve_action(action_type).schema_and_validator(payload)
    cost: resolve_action(action_type).cost(payload)
    description: "统一 action dispatch；当前 Engine 对 Attack/RangedAttack/Heal 使用固定 handler，8 个 vanilla special attack 与 enabled signed-plugin action 通过 CustomActionRegistry 执行。"

# ═════════════════════════════════════
# Body Part Vanilla 默认成本表（从 design 派生）
# ═════════════════════════════════════

body_cost:
  Move:         { Energy: 50 }
  Work:         { Energy: 100 }
  Carry:        { Energy: 50 }
  Attack:       { Energy: 80 }
  RangedAttack: { Energy: 150 }   # 伤害 25 (权威值见 economy.idl.yaml)
  Heal:         { Energy: 250 }
  Claim:        { Energy: 600 }
  Tough:        { Energy: 10 }

# world.toml 可覆盖以上默认值，例如:
#   [actions.costs]
#   body_part.Move = { Energy: 60, Crystal: 10 }

host_functions:
  # > 此块使用 IDL 内部短名称（如 get_terrain, path_find），权威名称带 host_ 前缀（host_get_terrain, host_path_find）。
  # > 所有签名的权威定义见 [API Registry](../reference/api-registry.md#4-host-functions)。以下为概念形式，实现以 Registry 为准。
  tick:
    # > tick 是 WASM export，非 host function import。Host functions 见 [API Registry](../reference/api-registry.md#4-host-functions)
    export: true
    params: [input_ptr: i32, input_len: i32, output_ptr: i32, output_len: i32]
    input: TickInput   # Swarm codec bytes
    output: TickResult # Swarm codec bytes
    returns: i32       # non-negative = bytes_written; negative = ABI-level failure

  # 世界配置查询（只读）
  get_world_config:
    params: [key_ptr: i32, key_len: i32, out_ptr: i32, out_len: i32]
    returns: i32

  get_world_rules:
    params: [rule_id_ptr: i32, rule_id_len: i32, out_ptr: i32, out_len: i32]
    returns: i32

  # 地形与寻路查询（只读，计入 fuel）
  get_terrain:
    params: [room_id: u32, out_ptr: i32, out_len: i32]
    returns: i32  # terrain grid written to out_ptr

  get_objects_in_range:
    params: [x: i32, y: i32, range: i32, out_ptr: i32, out_len: i32]
    returns: i32  # 写入 object_id 列表到 out_ptr
    limit: 5 calls/tick

  path_find:
    params: [from_x: i32, from_y: i32, to_x: i32, to_y: i32, opts_ptr: i32, opts_len: i32, out_ptr: i32, out_len: i32]
    returns: i32  # 写入路径坐标列表到 out_ptr
    limit: 10 calls/tick

global_storage_commands:
  TransferToGlobal:
    classification: economy_operation
    params: { resource: ResourceName, amount: ResourceAmount }
    validator: [global_storage_enabled, has_local_resource, under_capacity, transfer_time_remaining(0)]
    cost: registry.transfer_to_global_cost() * amount
    duration: global_deposit_delay  # tick 数，运输期间资源不可用

  TransferFromGlobal:
    classification: economy_operation
    params: { resource: ResourceName, amount: ResourceAmount }
    validator: [global_storage_enabled, has_global_resource, transfer_time_remaining(0)]
    cost: registry.transfer_from_global_cost() * amount
    duration: global_withdraw_delay

  AlliedTransfer:
    classification: economy_operation
    params: { target_player: PlayerId, resource: ResourceName, amount: ResourceAmount }
    validator: [global_storage_enabled, has_global_resource, allied_transfer_allowed]
    cost: registry.allied_transfer_fee() * amount
    duration: allied_transfer_delay

refund_policy:
  resource_refund:
    spawn_phase2b_creation_failure: 1.0  # refund body_cost to original debit source
    action_channel_interrupted: registry.action(type).refund_policy
    recycle: RecycleRefund(body_cost, remaining_lifespan, total_lifespan)
  fuel_refund:
    redb_commit_abandoned: 1.0
    validation_rejected: 0.0
    wasm_timeout_or_fuel_exhausted: 0.0
  note: "Resource refunds and WASM fuel refunds are separate ledgers; no generic contention_lost percentage applies."
```

## 3. IDL 表示与分发

文档 YAML/Registry 与 Engine runtime `IdlDoc` 是需要协调维护的不同表示。当前 Engine extraction 不读取文档 YAML；SDK 生成器消费 Engine 提取出的 runtime `IdlDoc`。

| 目标 | 同步机制 |
|------|--------|
| Engine | 从 Rust 类型与 runtime registries 提取 JSON `IdlDoc` |
| SDK | Engine `sdk_gen` 消费 runtime `IdlDoc` 生成文本 |
| MCP | 固定 vanilla schemas + 通用 custom-action schema；不为每个 custom action 生成独立工具 |
| Docs | YAML 与 Registry 手工同步发布 |

## 4. 一致性检查边界

当前检查分为两条独立路径：

1. **文档仓库**：`scripts/check_docs.py` 检查链接、版本声明和关键 gameplay 常量，不比较全部 Registry/IDL 字段。
2. **Engine 仓库**：Engine tests 检查 runtime extraction 和 SDK 生成，不读取本仓库 YAML/Registry；docs CLI 可在供应 Engine JSON 时记录计数摘要。

Registry 正文表格 ↔ IDL ↔ Engine 语义三方 generator/diff 不属于 docs-side 轻量检查范围。Registry metadata/count/version 使用 `scripts/sync_api_registry.py --check` 校验；禁止使用不存在的 `cargo run -- gen-api` 等命令；详细边界见 [Codegen Pipeline](../reference/codegen.md)。

---

## 5. 可配置命令

**所有特殊攻击均为 ActionRegistry vanilla action**。参数、冷却、消耗和效果由 `design/gameplay.md` 定义，Vanilla Action 表与 API Registry 负责下沉为实现/wire 发布；
World Action Manifest 仅负责暴露当前世界启用的 action set 与 mod 扩展 action。

### 5.1 变体列表

 | ActionRegistry action | body part | 类别 | 说明 |
 |--------------|-----------|------|------|
 | `Attack` | Attack | basic_combat | 近战攻击，参数见 canonical table |
 | `RangedAttack` | RangedAttack | basic_combat | 远程攻击，参数见 canonical table |
 | `Heal` | Heal | basic_combat | 治疗/修复目标 |
 | `Hack` | Claim | special_attack | 参数见 canonical table |
 | `Drain` | Carry+Work | special_attack | 参数见 canonical table |
 | `Overload` | RangedAttack | special_attack | 参数见 canonical table |
 | `Debilitate` | Work | special_attack | 参数见 canonical table |
 | `Disrupt` | Attack | special_attack | 参数见 canonical table |
 | `Fortify` | Tough | special_attack | 参数见 canonical table |
 | `Leech` | Attack | special_attack | 参数见 canonical table |
 | `Fabricate` | Work+Carry | special_attack | 参数见 canonical table；Vanilla 成本为纯 Energy |

### 5.2 注册规则

- 规范层以 ActionRegistry 统一描述 vanilla 与 mod action；当前 Engine 的具体实现边界为：
  ```
  fixed handlers (Attack/RangedAttack/Heal) ─────────────┐
                                                          ├→ CommandAction::Action dispatch
  CustomActionRegistry (8 vanilla special + mod actions) ─┘
                  │
                  ├→ runtime IdlDoc → SDK generator
                  └→ MCP generic custom-action schema
  ```
- `[[body_part_types]]` 定义 body part → action 绑定（如 `Claim` part → `Hack` action）
- engine-owned Vanilla manifest 或 signed plugin package manifest 定义可复用效果 handler；8 个 vanilla special attack 由 engine profile 预注册，并由 `mods.lock` + strict `world.toml [mods.special-attacks]` typed config 控制
- enabled signed plugin 通过 package World Action Manifest 声明非保留 mod action、closed payload schema 与 handler identity；不得覆盖 vanilla action 名称
- Plugin 必须向预定义 ActionRegistry fixed hook 注册 manifest 中声明的 handler，且只写 typed intent buffer；`world.toml` 不能声明 action/effect identity 或 handler
- runtime SDK 包含 `CustomActionRegistry` 中的 custom action；MCP 通过通用 custom-action schema 接收非保留 action 名称

## 6. SDK 生成与分发

SDK 由引擎基于世界加载的模组**动态生成**，而非预先编译分发。不同世界加载不同模组 → 不同的 API 面 → 不同的 SDK。

### 6.1 生成流程

```
引擎启动
    │
    ├─ 解析 world.toml + 加载 mods/
    ├─ 计算 mod_manifest_hash = Blake3(world.toml || mods.lock || engine_abi_version)
    │
    ├─ 扫描注册表:
    │   ├─ Core IDL:   内置指令 (Move/Harvest/Build/...)
    │   ├─ ActionRegistry: vanilla action + world manifest mod action
    │   ├─ mod config:  各模组暴露的可配置参数
    │   └─ Body parts:  [[body_part_types]] 中的自定义 parts
    │
    ├─ 生成 SDK artifacts:
    │   ├─ sdk-rust:  Rust crate (types + Command enum + host function stubs)
    │   ├─ sdk-ts:    npm package (types + autocomplete)
    │   ├─ command-intent schema: 14 CommandAction branches; Action resolves through Vanilla/plugin ActionRegistry
    │   └─ sdk.json:  machine-readable manifest (供 MCP/CLI 查询)
    │
    ├─ 导出 Frontend contracts:
    │   ├─ swarm-contracts.ts: ts-rs generated Rust contract types
    │   ├─ command-intent.schema.json: schemars generated command schema
    │   ├─ realtime.schema.json: swarm.realtime.v1 envelope schema
    │   └─ visible-snapshot.schema.json: visibility-filtered snapshot schema
    │
    ├─ 暴露下载端点:
    │   ├─ REST: signed GET /sdk/:lang
    │   ├─ CLI:  swarm sdk fetch <world_id>
    │   └─ Web:  世界详情页 SDK 下载链接
    │
    └─ 缓存: 按 (mod_manifest_hash, sdk_target) 缓存，相同 hash 复用
```

ABI v2 is immediate breaking: generated SDKs must encode `TickInput` and decode/write `TickResult` with the IDL-generated Swarm codec. Generated `swarm.realtime.v1` contracts remain the frontend/live-client envelope; codegen must keep frontend contracts and ABI v2 command schemas consistent with the same Rust `CommandAction` branch source.

### 6.2 WASM 模块声明

每个 WASM 模块在编译时嵌入目标世界标识：

```toml
# Cargo.toml (Rust) / package.json (TS)
[package.metadata.swarm]
target_manifest_hash = "abc123..."   # 编译时从 swarm sdk fetch 获取
engine_abi_version = 1
```

### 6.3 部署验证

```
玩家部署 WASM
    │
    ▼
引擎校验:
  module.target_manifest_hash == world.current_manifest_hash ?
    ├─ 是 → 接受部署
    └─ 否 → 拒绝，返回错误:
         "SDK mismatch: module built for hash X, world currently at hash Y.
          Run `swarm sdk fetch` to update."
```

### 6.4 版本兼容性

| 变更 | manifest_hash 变化 | 已部署 WASM |
|------|-------------------|------------|
| world.toml 调参（cost/cooldown） | 不变 | ✅ 兼容 |
| 新增 mod（新 handler） | 变化 | ❌ 需重新编译 |
| 移除 mod | 变化 | ❌ 需重新编译 |
| engine ABI 升级 | 变化 | ❌ 需重新编译 |
| Vanilla world（无 mods） | 固定 hash `vanilla-v1` | ✅ 跨世界兼容 |

### 6.5 离线开发

```
swarm sdk fetch world_v1          # 拉取 SDK
swarm sdk build --target world_v1 # 编译 WASM（离线）
swarm sdk publish world_v1        # 部署到目标世界（在线）
```

本地开发时 SDK 缓存到 `~/.swarm/sdks/{hash}/`，相同 hash 复用。

### 6.6 模组世界标识

任何使用 Layer 3 扩展（自定义 body part / damage type / Command）的世界实例标记为非官方世界：
- 在世界列表中显示 `[MOD]` 标识
- 不参与官方排名（World 模式无公开排行榜，仅非竞争统计；Arena 模式仅 Vanilla 世界计入排名）
- 玩家加入时显示警告：「此世界使用非标准规则集，请确认已安装对应世界 SDK。」
