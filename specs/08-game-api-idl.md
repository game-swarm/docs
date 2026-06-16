# Game API IDL Spec — 游戏 API 接口定义语言

> 详见 DESIGN §5

> **目标**: host functions / Command / Validator / SDK / MCP schema 单一真相来源

## 1. 原则

**一个 IDL 生成所有绑定——不一致即编译错误。**

**Core IDL vs World Action Manifest 边界**：

- **Core IDL**（本文件 §2-4）：定义基础 envelope/ABI/host functions、内置基础指令（Move/Harvest/Build 等标准动作）、基础 CommandIntent 结构。Core IDL 长期稳定，ABI 版本号控制兼容性。
- **World Action Manifest**（引擎从 world.toml `[[custom_actions]]` + `[[special_effects]]` 动态生成）：定义特定世界的自定义 action（特殊攻击、模组扩展）。包含 canonical hash（`Blake3(manifest)`）、版本 tag、TickTrace 绑定。WASM 模块通过 `target_manifest_hash` 声明兼容的世界版本。

```
game_api.idl  (单一真相)
    │
    ├──→ Rust:   host function stubs + Command enum + Validator trait
    ├──→ TS:     SDK types + autocomplete
    ├──→ MCP:    tool schemas + docs resources
    ├──→ Docs:   API reference (human + AI)
    └──→ Test:   property-based test generators
```

**IDL 定义的指令类型是 CommandIntent**——即 WASM 模块 `tick()` 的可信输出格式。CommandIntent 仅包含 `sequence` + `action` 两个字段。`player_id`、`source`、`tick` 等身份/时序字段由服务端 Source Gate 注入后形成 RawCommand（见 specs/02-command-validation §2）。IDL 不定义 RawCommand 的 envelope 字段——那些是引擎内部结构。所有校验规则（`validator` 数组）定义在 CommandIntent 的 `action` 字段上。

## 2. IDL 格式

```yaml
# game_api.idl — Swarm Game API Interface Definition

version: "1.0.0"
abi_version: 1                # 每次 host function 签名变更时递增

types:
  PlayerId: u32
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
    - ObjectNotFound
    - NotOwner
    - NotMovable
    - Fatigued
    - MissingBodyPart { part: BodyPart }
    - TileBlocked
    - InvalidDirection
    - StillSpawning
    - OutOfRoom
    - NoPath
    - PathTooLong
    - InsufficientMoveParts
    - CarryFull
    - NotSource
    - SourceEmpty
    - OutOfRange { distance: u32, max: u32 }
    - InsufficientResource { resource: ResourceName, required: u32, available: u32 }
    - TargetFull
    - TargetEmpty
    - NotYourRoom
    - TileOccupied
    - InvalidTerrain
    - TooManyConstructionSites
    - NotStructure
    - NotController
    - AlreadyFullHealth
    - FriendlyTarget
    - NotYourSpawn
    - SpawnOnCooldown
    - BodyTooLarge
    - ExceedsRoomCapacity
    - RoomDroneCapReached
    - NotFriendly
    - SourceNotAllowed
    - AuthContextInvalid
    - GlobalStorageDisabled
    - TransferInProgress
    - TerminalRequired
    - OrderNotFound
    - UnknownAction { action: String }
    - AlreadyHacked
    - InvalidDamageType
    - AlreadyDebilitated { damage_type: String }
    - PlayerNotFound
    - TargetNotVisible
    - TargetOverloadCooldown

commands:
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

  Attack:
    params: { object_id: ObjectId, target_id: ObjectId }
    validator: [exists, owner, drone, body_part(Attack), enemy_target, in_range(1), fatigue]
    cost: {}

  RangedAttack:
    params: { object_id: ObjectId, target_id: ObjectId }
    validator: [exists, owner, drone, body_part(RangedAttack), enemy_target, in_range(3), fatigue]
    cost: {}

  Heal:
    params: { object_id: ObjectId, target_id: ObjectId }
    validator: [exists, owner, drone, body_part(Heal), friendly_target, damaged, in_range(3)]
    cost: {}

  Spawn:
    params: { spawn_id: ObjectId, body: Vec<BodyPart> }
    validator: [exists, owner, is_spawn, cooldown_zero, body_size(50), has_energy(body_cost), room_drone_cap]
    cost: registry.body_cost(body)

  Recycle:
    params: { object_id: ObjectId, spawn_id: ObjectId }
    validator: [exists, owner, drone, is_spawn, in_range(1)]
    refund: registry.body_cost(body) * 0.5

  # ═════════════════════════════════════
  # 扩展指令
  # ═════════════════════════════════════

  ClaimController:
    params: { object_id: ObjectId, controller_id: ObjectId }
    validator: [exists, owner, drone, body_part(Claim), is_controller, in_range(1)]
    cost: {}

  CreateMarketOrder:
    params: { object_id: ObjectId, resource: ResourceName, amount: ResourceAmount, price_resource: ResourceName, price_amount: ResourceAmount }
    validator: [exists, owner, drone, market_enabled, valid_resource, valid_price]
    cost: {}

  BuyMarketOrder:
    params: { object_id: ObjectId, order_id: u64 }
    validator: [exists, owner, drone, market_enabled, order_exists, not_expired, has_resources]
    cost: {}

  # ═════════════════════════════════════
  # 特殊攻击
  # ═════════════════════════════════════

  Hack:
    params: { object_id: ObjectId, target_id: ObjectId }
    validator: [exists, owner, drone, body_part(Claim), target_drone, not_hacked, in_range(1), fatigue]
    cost: { Energy: 1000 }
    cooldown: 200         # 全局冷却
    description: "施加控制锁逐步夺取 drone——5 tick 渐进控制后转为 Neutral"

  Drain:
    params: { object_id: ObjectId, target_id: ObjectId, resource: ResourceName? }
    validator: [exists, owner, drone, body_part(Work,Carry), target_structure, enemy_target, target_has_resource, carry_space, in_range(1), fatigue]
    cost: { Energy: 200 }
    cooldown: 50          # 每 drone 冷却
    description: "从目标建筑/存储窃取资源，每 tick 转移 carry_capacity 单位"

  Overload:
    params: { object_id: ObjectId, target_id: PlayerId }
    validator: [exists, owner, drone, body_part(RangedAttack), target_player, enemy_target, visible_target, target_global_cooldown(50), fatigue]
    cost: { Energy: 300 }
    cooldown: 200         # 每 drone 冷却
    description: "消耗目标 fuel budget 500k（短期压制，可恢复）。下限 MAX_FUEL×0.2，已触下限时静默 no-op。恢复 fuel_budget/1000 per tick。Fortify/Purge 清除效果。"

  Debilitate:
    params: { object_id: ObjectId, target_id: ObjectId, damage_type: DamageType }
    validator: [exists, owner, drone, body_part(Work), enemy_target, valid_damage_type, not_debilitated(damage_type), in_range(3), fatigue]
    cost: { Energy: 200 }
    cooldown: 150         # 每 drone 冷却
    description: "施加易伤状态——指定伤害类型抗性×2，持续 50 tick"

  Disrupt:
    params: { object_id: ObjectId, target_id: ObjectId }
    validator: [exists, owner, drone, body_part(Attack), target_drone, enemy_target, in_range(1), fatigue]
    cost: { Energy: 100 }
    cooldown: 50          # 每 drone 冷却
    description: "打断目标持续动作（Drain/Hack 控制锁等），不造成伤害"

  Fortify:
    params: { object_id: ObjectId, target_id: ObjectId? }
    validator: [exists, owner, drone, body_part(Tough), target_self_or_ally, in_range(1), fatigue]
    cost: { Energy: 400 }
    cooldown: 300         # 每 drone 冷却
    description: "护盾（所有抗性×0.5）+ 清除目标所有负面状态，持续 100 tick"

# ═════════════════════════════════════
# Body Part 默认成本表（权威来源）
# ═════════════════════════════════════

body_cost:
  Move:         { Energy: 50 }
  Work:         { Energy: 100 }
  Carry:        { Energy: 50 }
  Attack:       { Energy: 80 }
  RangedAttack: { Energy: 100 }   # 伤害 25
  Heal:         { Energy: 250 }
  Claim:        { Energy: 600 }
  Tough:        { Energy: 10 }

# world.toml 可覆盖以上默认值，例如:
#   [actions.costs]
#   body_part.Move = { Energy: 60, Crystal: 10 }

host_functions:
  tick:
    export: true
    params: [snapshot_ptr: i32, snapshot_len: i32]
    returns: i32  # 0 = success, pointer to command JSON in WASM memory

  # 世界配置查询（只读）
  get_world_config:
    params: [key_ptr: i32, key_len: i32, out_ptr: i32, out_len: i32]
    returns: i32

  get_world_rules:
    params: [out_ptr: i32, out_len: i32]
    returns: i32

  # 地形与寻路查询（只读，计入 fuel）
  get_terrain:
    params: [x: i32, y: i32]
    returns: i32  # terrain_type as i32 (0=plain, 1=wall, 2=swamp, 3=lava)

  get_objects_in_range:
    params: [x: i32, y: i32, range: i32, out_ptr: i32, out_len: i32]
    returns: i32  # 写入 object_id 列表到 out_ptr
    limit: 5 calls/tick

  path_find:
    params: [from_x: i32, from_y: i32, to_x: i32, to_y: i32, out_ptr: i32, out_len: i32]
    returns: i32  # 写入路径坐标列表到 out_ptr
    limit: 10 calls/tick

global_storage_commands:
  TransferToGlobal:
    params: { resource: ResourceName, amount: ResourceAmount }
    validator: [global_storage_enabled, has_local_resource, under_capacity, transfer_time_remaining(0)]
    cost: registry.transfer_to_global_cost() * amount
    duration: transfer_to_global_time  # tick 数，运输期间资源不可用

  TransferFromGlobal:
    params: { resource: ResourceName, amount: ResourceAmount }
    validator: [global_storage_enabled, has_global_resource, transfer_time_remaining(0)]
    cost: registry.transfer_from_global_cost() * amount
    duration: transfer_from_global_time

refund_policy:
  contention_lost: 0.5    # SourceEmpty, TileOccupied, TargetFull
  self_invalid: 0.0       # OutOfRange, Fatigued, MissingBodyPart, etc.
```

## 3. 代码生成规则

 目标 | 生成物 |
|------|--------|
| Rust | `src/generated/commands.rs` — Command enum + validate() |
| Rust | `src/generated/host_functions.rs` — host function stubs |
| TS SDK | `sdk-ts/src/generated/api.ts` — types + autocomplete |
| MCP | MCP tool schemas JSON |
| Replay | TickTrace schema |
| Docs | API reference markdown |

## 4. CI 检查

```bash
cargo run -- gen-api        # 从 IDL 生成代码
git diff --exit-code        # 生成代码与提交代码一致 → 不一致则 CI 失败
```

任何对游戏 API 的修改必须从 IDL 开始——修改 `game_api.idl` → 重新生成 → 提交生成的代码。不允许手写 Command 变体或 host function。

---

## 5. 可配置命令

**所有特殊攻击通过 world.toml 的 `[[custom_actions]]` + `[[special_effects]]` 可配置注册**，非硬编码。

### 5.1 变体列表

 CommandAction | body part | special_effect | 说明 |
--------------|-----------|---------------|------|
 `RangedAttack` | RangedAttack | — | 远程攻击，parts × 25，范围 3 |
 `ClaimController` | Claim | — | 占领 Controller |
 `Recycle` | — | — | 回收 drone，退还 50% body part 资源 |
 `Disrupt` | Attack | `disrupt` | 打断目标动作，50 tick CD |
 `Fortify` | Tough | `fortify` | 护盾 + 净化，300 tick CD |
 `Hack` | Claim | `hack` | 夺取 drone → Neutral，200 tick CD |
 `Drain` | Carry+Work | `drain` | 窃取资源，50 tick CD |
 `Overload` | RangedAttack | `overload` | 消耗配额 -500k，200 tick CD |
 `Debilitate` | Work | `debilitate` | 易伤 ×2，150 tick CD |
 `Leech` | custom | `leech` | 吸血 50%，Corrosive 15 dmg |
 `Fabricate` | custom | `fabricate` | 转化建筑，500 tick CD |

### 5.2 注册规则

- 以上变体在引擎启动时从 world.toml 动态注册，注册链路：
  ```
  [[special_effects]]  →  定义效果类型（handler / target / duration / resistance）
         │
         ▼
  [[custom_actions]]   →  引用 special_effect = "name"，定义 CD / cost / damage
         │
         ▼
  引擎 CommandAction 注册表  →  自动绑定 validate/apply handler
         │
         ▼
  IDL 代码生成器  →  扫描注册表 → 生成所有 target 语言的绑定
  ```
- `[[body_part_types]]` 定义 body part → action 绑定（如 `Claim` part → `Hack` action）
- `[[special_effects]]` 定义效果类型（11 个内置 handler：`hack`, `drain`, `overload`, `debilitate`, `disrupt`, `fortify`, `leech`, `fabricate`, `heal_self`, `scramble_commands`, `convert_to_structure`）
- 服主可在 world.toml 中新增 `[[custom_actions]]` 条目引用已有 `[[special_effects]]` ——无需改 Rust 代码
- 需全新 handler 时通过 Rhai 模组注册
- SDK 和 MCP schema 自动包含所有已注册 action

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
    │   ├─ custom_actions: world.toml [[custom_actions]] 条目
    │   ├─ mod config:  各模组暴露的可配置参数
    │   └─ Body parts:  [[body_part_types]] 中的自定义 parts
    │
    ├─ 生成 SDK artifacts:
    │   ├─ sdk-rust:  Rust crate (types + Command enum + host function stubs)
    │   ├─ sdk-ts:    npm package (types + autocomplete)
    │   └─ sdk.json:  machine-readable manifest (供 MCP/CLI 查询)
    │
    ├─ 暴露下载端点:
    │   ├─ MCP:  swarm_sdk_fetch(world_id)
    │   ├─ CLI:  swarm sdk fetch <world_id>
    │   └─ Web:  世界详情页 SDK 下载链接
    │
    └─ 缓存: 按 (mod_manifest_hash, sdk_target) 缓存，相同 hash 复用
```

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
- 不参与官方排名（World 模式无排行榜，Arena 模式仅 Vanilla 世界计入排名）
- 玩家加入时显示警告：「此世界使用非标准规则集，请确认已安装对应世界 SDK。」
