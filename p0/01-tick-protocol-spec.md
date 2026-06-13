# P0-1: Tick Protocol Spec

> **Status**: Phase 2 blocker | **Rulings**: N/A | **Sources**: D1, D2, D3, G1 consensus

## 1. State Machine

```
                 ┌──────────────────────────────────┐
                 │         TICK IDLE                 │
                 │  tick_counter = N                 │
                 └──────────┬───────────────────────┘
                            │ config.tick_interval elapsed
                            ▼
                 ┌──────────────────────────────────┐
                 │     PHASE 1: COLLECT              │
                 │  timeout: 2500ms                  │
                 │  ┌─────────────────────────┐     │
                 │  │ For each active player:   │     │
                 │  │ 1. Build snapshot (vis)   │     │
                 │  │ 2. Call PlayerExecutor    │     │
                 │  │ 3. Timeout → [] commands  │     │
                 │  └─────────────────────────┘     │
                 │  Result: Map<PlayerId, Vec<Cmd>> │
                 └──────────┬───────────────────────┘
                            │
                            ▼
                 ┌──────────────────────────────────┐
                 │     PHASE 2: EXECUTE              │
                 │  timeout: 500ms                   │
                 │  ┌─────────────────────────┐     │
                 │  │ For each command (sorted):│     │
                 │  │ 1. Validate              │     │
                 │  │ 2. Apply or Reject        │     │
                 │  └─────────────────────────┘     │
                 │  Run ordered ECS systems          │
                 └──────────┬───────────────────────┘
                            │
                            ▼
                 ┌──────────────────────────────────┐
                 │     PHASE 3: BROADCAST            │
                 │  ┌─────────────────────────┐     │
                 │  │ 1. Compute entity deltas  │     │
                 │  │ 2. FDB commit (atomic)    │     │
                 │  │ 3. Dragonfly update       │     │
                 │  │ 4. NATS publish deltas    │     │
                 │  └─────────────────────────┘     │
                 └──────────┬───────────────────────┘
                            │ tick_counter = N + 1
                            ▼
                      TICK IDLE
```

## 2. Phase 1: Collect

### 2.1 Player Execution Model

| Player Kind | Executor | Completion Model |
|------------|----------|-----------------|
| Human/WASM | `WasmSandboxExecutor` in sandbox worker process | Synchronous: completes within collect window |
| AI (MCP) | `McpPlayerExecutor` | Asynchronous: reads from pre-submitted command queue |

### 2.2 Collect Timeout

```
collect_timeout_ms = 2500  // hard deadline

At t + 2500ms:
  For each player that hasn't responded:
    commands[player] = []   // fail-open: no commands this tick
    metrics.collect_timeouts += 1
```

A stuck player does NOT block the tick. Late-arriving commands are queued for the next tick.

### 2.3 Snapshot Construction

```
fn build_snapshot(player_id, tick) -> Snapshot:
    entities = visibility_filter(all_entities, player_id, tick)
    return Snapshot {
        tick,
        player_id,
        entities,    // only those visible to this player
        terrain,     // visible terrain tiles
        resources,   // player's own resource counts
    }
```

Snapshot is serialized ONCE per room, then per-player filtered. Not O(P × E).

### 2.4 AI Player Command Queue

AI players submit commands between ticks via MCP:
```
POST /mcp/tick/{tick+1}/commands
Body: Vec<RawCommand>
```

Commands are stored in `player_commands[tick][player_id]` in Dragonfly.
When tick N begins, engine reads pre-submitted commands. If empty → [].

## 3. Phase 2: Execute

### 3.1 Command Ordering (Deterministic)

```
sort_key = (tick_number, player_id, command_sequence_number)
```

All commands from all players are flattened into a single list sorted by this key.
This is deterministic: given the same set of commands, the order is always the same.

### 3.2 Command Validation

Each command validated against current world state. See P0-2: Command Validation Spec.
Invalid commands → rejected with `RejectionReason`. Recorded in `TickTrace`.

### 3.3 ECS System Ordering (Bevy)

```rust
app.add_systems(Update, (
    build_system,          // structures appear
    harvest_system,        // resources drained
    regeneration_system,   // sources replenish
    movement_system,       // drones move
    combat_system,         // attacks resolve
    decay_system,          // fatigue/cooldowns tick
    death_system,          // dead entities removed
    spawn_system,          // new entities created last
).chain());
```

`.chain()` enforces sequential execution → deterministic.
Future optimization: `.before()/.after()` for partial parallelism while preserving correctness.

### 3.4 Tick Atomicity

The entire Phase 2 is wrapped in a FoundationDB transaction:

```
txn = fdb.create_transaction()
for command in sorted_commands:
    result = validate_and_apply(txn, command, world_state)
    if result.is_err():
        record_rejection(txn, command, result)
txn.set("/tick/{tick}/complete", true)
txn.commit()  // ALL or NOTHING
```

If `txn.commit()` fails (conflict, network) → retry up to 3 times → if all fail, tick is ABANDONED.
Abandoned tick: world state unchanged, tick counter does NOT advance, alert generated.

## 4. Phase 3: Broadcast

### 4.1 Delta Computation

```
delta = compute_delta(world_state_before, world_state_after)
// delta contains only entities that changed this tick
```

### 4.2 Persist → Cache → Publish

```
1. FDB.commit()              // atomic, blocks until durable
2. Dragonfly.update(delta)   // non-authoritative, can lag
3. NATS.publish("tick.{tick}", delta)  // gateway → WS clients
```

Order matters: FDB first, then cache, then broadcast.
If Dragonfly fails → rebuild from FDB.
If NATS fails → clients miss delta, next tick's snapshot is full (not delta).

## 5. Tick Health Metrics

| Metric | Threshold | Action |
|--------|-----------|--------|
| `collect_timeout_rate` | > 10% of players | Alert: too many slow executors |
| `tick_abandon_rate` | > 0 | Critical: FDB commit failures |
| `tick_duration_p99` | > 2800ms | Warning: approaching 3s target |
| `command_rejection_rate` | > 20% per player | Flag player for review |

## 6. Replay Protocol

### 6.1 Recording

For each tick, record to FDB (immutable):
```
/tick/{N}/commands   → sorted Vec<RawCommand> from all players
/tick/{N}/state      → full world state AFTER tick
/tick/{N}/rejections → Vec<(RawCommand, RejectionReason)>
/tick/{N}/metrics    → TickMetrics
```

For AI players: record ACCEPTED commands, NOT raw LLM output.
Replay feeds recorded commands — does NOT re-call the LLM.

### 6.2 Replaying

```
fn replay_tick(tick_N) -> WorldState:
    state = load_state(tick_N - 1)     // starting state
    commands = load_commands(tick_N)   // recorded commands
    return execute_deterministic(state, commands)  // must == recorded state
```

If `execute_deterministic(state, commands) != recorded_state` → DETERMINISM BUG.
