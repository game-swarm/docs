# P0-2: Command Validation Spec

> **Status**: Phase 2 blocker | **Rulings**: D1 (UX verbs OK) | **Sources**: D4, S4, D6 consensus

## 1. Command Pipeline

```
RawCommand (from WASM/MCP/REST)
    │
    ▼
┌─────────────────┐
│  DESERIALIZE     │  JSON parse, schema check, bounds check
└────────┬────────┘
         │ Ok(RawCommand)
         ▼
┌─────────────────┐
│  PRE-VALIDATE    │  Static checks: target exists, owner matches, in range
└────────┬────────┘
         │ Ok(ValidatedCommand)
         ▼
┌─────────────────┐
│  APPLY           │  Mutate world state (inside FDB transaction)
└────────┬────────┘
         │ Ok / Err(RejectionReason)
         ▼
   Record in TickTrace
```

**Single pipeline**: All entry points (WASM host functions, MCP tools, REST API, admin CLI) route through the same `validate → apply` path. No bypass.

## 2. RawCommand Schema

```json
{
  "player_id": 42,
  "tick": 4521,
  "sequence": 3,
  "action": {
    "type": "Move",
    "object_id": 1001,
    "direction": "TopRight"
  }
}
```

| Field | Type | Validation |
|-------|------|------------|
| `player_id` | u32 | Must match authenticated player |
| `tick` | u64 | Must be current tick or next tick (for advance queue) |
| `sequence` | u32 | Monotonically increasing per player per tick |
| `action` | Action | See per-action validation below |

## 3. Per-Command Validation Matrix

### 3.1 Move

```json
{"type": "Move", "object_id": 1001, "direction": "TopRight"}
```

| Check | Failure Code |
|-------|-------------|
| `object_id` exists in world | `ObjectNotFound` |
| `object_id.owner == player_id` | `NotOwner` |
| `object_id` is a Drone (not Structure/Resource) | `NotMovable` |
| `drone.fatigue == 0` | `Fatigued` |
| `drone.body` contains `Move` part | `MissingBodyPart(Move)` |
| Target tile is passable (not Wall, not occupied by hostile) | `TileBlocked` |
| Direction is valid hex neighbor | `InvalidDirection` |
| Drone is not `spawning` | `StillSpawning` |

### 3.2 MoveTo

```json
{"type": "MoveTo", "object_id": 1001, "x": 15, "y": 22}
```

| Check | Failure Code |
|-------|-------------|
| All Move checks (3.1) apply | (same) |
| `(x, y)` is within current room | `OutOfRoom` |
| Path exists from current position to `(x, y)` | `NoPath` |
| Path length ≤ MAX_PATH_LENGTH (100) | `PathTooLong` |
| `drone.body` contains `Move` parts ≥ path length (1 MOVE = 1 tile/tick) | `InsufficientMoveParts` |

### 3.3 Harvest

```json
{"type": "Harvest", "object_id": 1001, "target_id": 4001}
```

| Check | Failure Code |
|-------|-------------|
| `object_id` is a Drone owned by player | `NotOwner` |
| `drone.body` contains `Work` part | `MissingBodyPart(Work)` |
| `drone.body` contains `Carry` part | `MissingBodyPart(Carry)` |
| `drone.carry_used < drone.carry_capacity` | `CarryFull` |
| `target_id` is a Source | `NotSource` |
| `target.source.energy > 0` | `SourceEmpty` |
| `object_id` in range of `target_id` (range = 1) | `OutOfRange` |
| `drone.fatigue == 0` | `Fatigued` |

### 3.4 Transfer / Withdraw

```json
{"type": "Transfer", "object_id": 1001, "target_id": 2001, "resource": "Energy", "amount": 50}
{"type": "Withdraw", "object_id": 1001, "target_id": 2001, "resource": "Energy", "amount": 50}
```

| Check | Failure Code |
|-------|-------------|
| `object_id` is a Drone owned by player | `NotOwner` |
| `drone.body` contains `Carry` part | `MissingBodyPart(Carry)` |
| Transfer: `drone.carry[resource] >= amount` | `InsufficientResources` |
| Withdraw: `target.carry[resource] >= amount` | `InsufficientResources` |
| Target has capacity for resource | `TargetFull` / `TargetEmpty` |
| `object_id` in range of `target_id` (range = 1) | `OutOfRange` |

### 3.5 Build

```json
{"type": "Build", "object_id": 1001, "x": 10, "y": 15, "structure": "Extension"}
```

| Check | Failure Code |
|-------|-------------|
| `object_id` is a Drone owned by player | `NotOwner` |
| `drone.body` contains `Work` part | `MissingBodyPart(Work)` |
| `drone.body` contains `Carry` part | `MissingBodyPart(Carry)` |
| `drone.carry[Energy] >= build_cost(structure)` | `InsufficientEnergy` |
| `(x, y)` is in a room with player's Controller | `NotYourRoom` |
| Tile is empty (no existing structure) | `TileOccupied` |
| Tile is Plain terrain (not Wall/Swamp) | `InvalidTerrain` |
| Player has construction sites < MAX_CONSTRUCTION_SITES (100) | `TooManyConstructionSites` |
| `object_id` in range of `(x, y)` (range = 3) | `OutOfRange` |

### 3.6 Repair

```json
{"type": "Repair", "object_id": 1001, "target_id": 2002}
```

| Check | Failure Code |
|-------|-------------|
| `object_id` is a Drone with Work+Carry | `MissingBodyPart` |
| `target_id` is a Structure | `NotStructure` |
| `target.hits < target.hits_max` | `AlreadyFullHealth` |
| `drone.carry[Energy] >= repair_cost` | `InsufficientEnergy` |
| `object_id` in range (range = 3) | `OutOfRange` |

### 3.7 Attack

```json
{"type": "Attack", "object_id": 1001, "target_id": 1002}
```

| Check | Failure Code |
|-------|-------------|
| `object_id` is a Drone owned by player | `NotOwner` |
| `drone.body` contains `Attack` part | `MissingBodyPart(Attack)` |
| `target_id` exists | `ObjectNotFound` |
| `target_id.owner != player_id` OR is neutral hostile | `FriendlyTarget` |
| `object_id` in range (range = 1) | `OutOfRange` |
| `drone.fatigue == 0` | `Fatigued` |

**TOCTOU**: If target moved between snapshot and execution, range is checked against CURRENT position → `OutOfRange` if moved away. Attack does NOT follow the target.

### 3.8 RangedAttack

Same as Attack, range = 3, requires `RangedAttack` body part.

### 3.9 Heal

```json
{"type": "Heal", "object_id": 1001, "target_id": 1003}
```

| Check | Failure Code |
|-------|-------------|
| `drone.body` contains `Heal` part | `MissingBodyPart(Heal)` |
| `target.hits < target.hits_max` | `AlreadyFullHealth` |
| Target owned by player or ally | `NotFriendly` |
| Range = 3 | `OutOfRange` |

### 3.10 Spawn

```json
{"type": "Spawn", "spawn_id": 2001, "body": ["Move", "Work", "Carry", "Move"]}
```

| Check | Failure Code |
|-------|-------------|
| `spawn_id` is a Spawn structure owned by player | `NotYourSpawn` |
| `spawn.cooldown == 0` | `SpawnOnCooldown` |
| `body.len() ≤ MAX_BODY_PARTS (50)` | `BodyTooLarge` |
| `body_cost(body) ≤ spawn.energy` | `InsufficientEnergy` |
| `body_cost(body) ≤ player.energy_capacity` | `ExceedsRoomCapacity` |
| Room has available spawn slot (not at room drone cap) | `RoomDroneCapReached` |

Drone is created at end of tick (after death_system, so spawn slot is freed).

### 3.11 Recycle

```json
{"type": "Recycle", "object_id": 1001, "spawn_id": 2001}
```

| Check | Failure Code |
|-------|-------------|
| `object_id` is a Drone owned by player | `NotOwner` |
| `spawn_id` is player's Spawn | `NotYourSpawn` |
| `object_id` in range of `spawn_id` (range = 1) | `OutOfRange` |

Returns 50% of body cost as energy to spawn.

## 4. Query Commands (Read-Only)

Queries do NOT go through the command pipeline. They are handled during snapshot generation (Phase 1).

### 4.1 GetTerrain

Returns terrain type at (x, y). Server-side only. No per-tick quota — static data.

### 4.2 GetObjectsInRange

Returns visible entities within `range` of (x, y).
- `range ≤ MAX_QUERY_RANGE (10)`
- Only returns entities visible to player (respects fog-of-war)
- Per-player-per-tick query budget: 5 calls

### 4.3 PathFind

Returns optimal path from (from_x, from_y) to (to_x, to_y).
- Both points within same room
- `path_length ≤ MAX_PATH_LENGTH (100)` — pathfinding aborts if longer
- Charged against player's compute budget (WASM fuel or MCP query budget)
- Per-player-per-tick: 10 calls
- Result cached per (from, to, terrain_hash) — not recomputed if unchanged

## 5. Rejection Response

Every rejection returns:

```json
{
  "command": { /* original RawCommand */ },
  "rejection": "OutOfRange",
  "detail": "object_1001 at (5,3), target_1002 at (5,6) — distance 3, require ≤ 1",
  "tick": 4521
}
```

AI-accessible explainability: the `detail` field is machine-readable JSON with exact positions, distances, and thresholds. See P0-6 for UX-friendly explanations.

## 6. Bounds & Limits (Hard)

| Parameter | Limit | Rationale |
|-----------|-------|-----------|
| MAX_BODY_PARTS | 50 | Prevents spawn vector DoS |
| MAX_PATH_LENGTH | 100 | Prevents pathfinding explosion |
| MAX_QUERY_RANGE | 10 | Prevents GetObjectsInRange scan |
| MAX_COMMANDS_PER_PLAYER | 100/tick | Caps MCP tool spam |
| MAX_CONSTRUCTION_SITES | 100/room | Prevents build spam |
| MAX_DRONES_PER_PLAYER | 500 | Prevents drone spam |
| Player name | 32 chars, `[a-zA-Z0-9 _-]` | Prompt injection prevention |
| Room name | 16 chars, `[A-Z][0-9]+[NS][0-9]+[EW]` | Standardized format |
| JSON depth | 10 | serde_json recursion limit |
| String max len (any) | 256 chars | General protection |
| i32 coordinate range | [-128, 127] per room | Prevents overflow attacks |
