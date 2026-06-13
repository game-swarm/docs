# P0-5: Unified Visibility Policy

> **Status**: Phase 2 blocker | **Rulings**: D3 (replay public) | **Sources**: C5, S4 consensus

## 1. Core Principle

**One function answers "what can player P see at tick T?":**

```rust
fn is_visible_to(entity: &Entity, player_id: PlayerId, tick: u64) -> bool;
```

Every output surface calls this. No bypass. No "it's just debug data so it's fine."

## 2. Visibility Rules

### 2.1 Own Entities

```
OWNER: Always visible, anywhere, any tick.
```

A player always sees their own drones, structures, resources, construction sites, and controller.

### 2.2 Visible Room Entities

```
ROOM_VISIBLE: Visible if player has vision in that room.
Vision source: any owned drone or structure with vision range > 0.
```

| Vision Source | Range |
|--------------|-------|
| Drone | 3 (default, body-dependent) |
| Spawn | 3 |
| Tower | 3 (6 when powered) |
| Observer | 10 (when active) |
| Controller (owned, level ≥ 1) | 1 |

### 2.3 Neutral/Hostile Entities

```
HOSTILE: Visible if within ANY friendly vision source's range.
```

Enemy drones, neutral structures, resources on ground — visible if they fall within any vision cone.

### 2.4 Hidden Information

| Data | Default Visibility |
|------|-------------------|
| Other player's resource counts | ❌ Hidden |
| Other player's controller progress | ❌ Hidden |
| Other player's construction sites | ✅ Visible (in vision range) |
| Other player's cooldowns | ❌ Hidden |
| Other player's fatigue | ❌ Hidden |
| Other player's body composition | ✅ Visible (observable characteristic) |
| RNG seed | ❌ Hidden (always) |
| Rejected commands (other players) | ❌ Hidden |
| WASM module errors (other players) | ❌ Hidden |

### 2.5 Market Visibility

```
MARKET: All active market orders visible to all players in rooms with vision.
Order creator's identity: visible.
```

### 2.6 Leaderboard Visibility

```
LEADERBOARD: Public.
Metrics: GCL, room count, drone count.
Hidden: resource totals, current strategy, WASM module source.
```

## 3. Output Surfaces — Visibility Enforcement

### 3.1 Snapshot (WASM `tick()` input)

```json
{
  "tick": 4521,
  "player_id": 42,
  "entities": [/* filtered by is_visible_to */],
  "terrain": [/* all terrain in visible rooms */],
  "resources": { "energy": 5000, "minerals": {"H": 1200} },  // OWN only
  "controller": { "level": 3, "progress": 4500 },            // OWN only
  "market_orders": [/* visible orders */],
  "leaderboard_snapshot": { "rank": 42, "gcl": 1500000 }
}
```

### 3.2 MCP Tools

| Tool | Visibility Filter |
|------|------------------|
| `get_snapshot` | Full `is_visible_to` filter |
| `get_objects_in_range` | `is_visible_to` + range check |
| `get_terrain` | Any tile — terrain is public knowledge |
| `inspect_entity` | Only if `is_visible_to` returns true OR own entity |
| `inspect_room` | Only rooms with own vision |

### 3.3 WebSocket Deltas

```
Deltas pushed after each tick: only entities that changed AND are_visible_to(subscriber).
```

### 3.4 REST API

```
GET /api/v1/world/rooms/:id  → entities filtered by is_visible_to(requester)
GET /api/v1/world/rooms/:id/map → terrain only (public)
```

### 3.5 Debug/Replay

| Mode | Visibility |
|------|-----------|
| **Raw trace** (admin) | FULL — all entities, all commands, all state |
| **Self replay** (player) | `is_visible_to(player, tick)` — what player actually saw |
| **Public replay** (match complete) | `is_visible_to(any_player, tick)` OR omniscient (post-match delay) |

## 4. Room-Based Fog of War

```
Room R at tick T:
  for player P:
    if P has any vision source in room R:
      visible_entities = all entities in R + adjacent rooms (within vision range)
    else:
      visible_entities = room_controller_owner(R) and room_level(R)  // metadata only
```

A player who loses all vision in a room still sees:
- Who owns the room controller
- The room level
- The room name

But NOT entity positions, drone counts, structure status.

## 5. Visibility Caching

```
Per-tick, per-player visibility is computed ONCE and cached.
Cache key: (tick, player_id)
Cache value: HashSet<EntityId>
Invalidated: next tick
```

All output surfaces read from this cache. Prevents "snapshot says hidden but WebSocket delta leaks it" bugs.

## 6. Testing

### 6.1 Unit Tests

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

### 6.2 Integration Tests

```rust
// Set up world: Player A has drones in room W1N1, Player B has drone in W1N2
// Assert: Player A's snapshot contains only W1N1 entities
// Assert: Player B's WebSocket delta contains only W1N2 changes
// Assert: Player A's replay shows only W1N1 state at each tick
```

### 6.3 Leak Detection Test

```rust
// For each output surface (snapshot, MCP, WS, REST, replay):
//   1. Create world with hidden information
//   2. Request output as player who shouldn't see it
//   3. Assert: hidden data NOT in output
```

## 7. Phase-Specific Visibility

### World Mode (Persistent)

Full fog-of-war as described. Rooms retain state. Vision persists across ticks until lost.

### Arena Mode (Match)

Simplified visibility: full information within match bounds. Both players see the entire arena. Fog-of-war disabled for competitive fairness. Timer and score visible to spectators.
