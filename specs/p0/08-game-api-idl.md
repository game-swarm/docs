# P0-8: Game API IDL Spec — 游戏 API 接口定义语言

> **状态**: Phase 0 Architecture Freeze | **目标**: host functions / Command / Validator / SDK / MCP schema 单一真相来源

## 1. 原则

**一个 IDL 生成所有绑定——不一致即编译错误。**

```
game_api.idl  (单一真相)
    │
    ├──→ Rust:   host function stubs + Command enum + Validator trait
    ├──→ TS:     SDK types + autocomplete
    ├──→ MCP:    tool schemas + docs resources
    ├──→ Docs:   API reference (human + AI)
    └──→ Test:   property-based test generators
```

## 2. IDL 格式

```yaml
# game_api.idl — Swarm Game API Interface Definition

version: "1.0.0"
generated: "2026-06-14"

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
  Direction: [Top, TopRight, BottomRight, Bottom, BottomLeft, TopLeft]
  BodyPart:  [Move, Work, Carry, Attack, RangedAttack, Heal, Claim, Tough]
  StructureType: [Spawn, Extension, Tower, Storage, Link, Extractor, Lab,
                  Terminal, Nuker, Observer, PowerSpawn, Factory]
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
    - AlreadyFullHealth
    - FriendlyTarget
    - NotYourSpawn
    - SpawnOnCooldown
    - BodyTooLarge
    - ExceedsRoomCapacity
    - RoomDroneCapReached
    - NotFriendly

commands:
  Move:
    params: { object_id: ObjectId, direction: Direction }
    validator: [exists, owner, drone, fatigue, body_part(Move), passable, !spawning]
    cost: {}   # 无资源消耗

  MoveTo:
    params: { object_id: ObjectId, x: i32, y: i32 }
    validator: [Move checks, in_room, path_exists, path_length(100)]
    cost: {}   # pathfinding 计入 fuel

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
    params: { object_id: ObjectId, target_id: ObjectId }
    validator: [exists, owner, drone, body_part(Work,Carry), is_structure, damaged, in_range(3)]
    cost: registry.repair_cost()

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

host_functions:
  tick:
    export: true
    params: [snapshot_ptr: i32, snapshot_len: i32]
    returns: i32  # 0 = success, pointer to command JSON in WASM memory

  # 世界配置查询
  get_world_config:
    params: []
    returns: WorldConfig

  get_world_rules:
    params: []
    returns: Vec<ActiveMod>

refund_policy:
  contention_lost: 0.5    # SourceEmpty, TileOccupied, TargetFull
  self_invalid: 0.0       # OutOfRange, Fatigued, MissingBodyPart, etc.
```

## 3. 代码生成规则

| 目标 | 生成物 |
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
