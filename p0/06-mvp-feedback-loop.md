# P0-6: MVP Feedback Loop Spec

> **Status**: Phase 2 blocker | **Rulings**: D1 (UX verbs), D3 (public replay) | **Sources**: G1, C7, C8 consensus

## 1. The MVP Feedback Loop

A player's experience is a loop. The MVP must close this loop for both human and AI players:

```
         LEARN           →         DECIDE          →         ACT
    "What are the      "Given the world,      "Submit commands
     rules? What       what should I           for this tick"
     can I do?"        do this tick?"
          ↑                                            │
          │                                            │
          └──────────── UNDERSTAND ←──────────────────┘
                    "What happened?
                     Did my commands work?
                     Why did some fail? Why did I lose?"
```

If any of these 4 steps is broken, the game is unplayable.

## 2. LEARN: Onboarding

### 2.1 Human Programmer (5-Minute Tutorial)

```
1. Open web client → Tutorial Room (private, isolated)
2. Tutorial bot (pre-written, editable) runs automatically
3. Step-by-step overlay:
   - "This is your Spawn. You can create drones here."
   - "Try changing 'spawn_count = 1' to 'spawn_count = 3'"
   - "Your drones are harvesting! Watch them collect energy."
   - "Add a Tower at (5,3) to defend your base."
4. Guided code changes with instant feedback (tick interval = 1s in tutorial)
5. Prompt: "You're ready! Deploy to the World or try Arena."
```

### 2.2 AI Player (MCP Tutorial)

```
AI agent connects → swarm://docs/tutorials/basic-agent
Returns step-by-step MCP interaction guide:

1. Call swarm_get_available_actions → discover what you can do
2. Call swarm_get_snapshot → see your world state
3. Issue commands via swarm_submit_commands
4. Call swarm_explain_last_tick → understand results
5. Repeat

Example tick loop (pseudocode):
  snapshot = mcp.call("swarm_get_snapshot", {player_id: self.id})
  commands = self.strategy.decide(snapshot)
  mcp.call("swarm_submit_commands", {commands, tick: snapshot.tick + 1})
  explanation = mcp.call("swarm_explain_last_tick")  // next tick
```

### 2.3 Starter Bots

Provided in each SDK:

| Language | Bot | Description |
|----------|-----|-------------|
| TypeScript | `basic-harvester` | 3 drones, harvest nearest source, return energy |
| TypeScript | `tower-defense` | Build towers, basic defense |
| TypeScript | `room-claimer` | Claim a room, upgrade controller |
| Rust | `basic-harvester` | Same as TS, in Rust |
| MCP (AI) | `basic-agent` | Python script showing MCP tick loop |

Starter bots must compile/run out of the box. One-command deploy:
```
swarm deploy ./basic-harvester
```

## 3. DECIDE: Information & Tools

### 3.1 MCP Discovery Verbs

| Tool | Purpose |
|------|---------|
| `swarm_get_available_actions` | "What can I do right now?" Returns list of possible actions given current state |
| `swarm_get_snapshot` | Full visible world state |
| `swarm_validate_plan` | "If I submit these commands, will they work?" Dry-run validation |
| `swarm://docs/api-reference` | Full API reference as MCP resource |

### 3.2 Human IDE Features

```
- Monaco Editor with full TypeScript types for game API
- Autocomplete on entity fields (drone.fatigue, source.energy, etc.)
- Inline validation: "drone.harvest() requires WORK body part, your drone has [MOVE, CARRY]"
- One-click deploy
- Version history (rollback to previous bot)
```

### 3.3 Local Simulation

```
swarm sim --ticks=5000 --speed=100x
```

Runs 5000 ticks locally at 100x speed. No server connection needed.
Output: final state + metrics (energy collected, drones built, combat results).
Iteration cycle: edit code → `swarm sim` (10s) → see results → repeat.

## 4. ACT: Command Submission

### 4.1 Submission Channels

| Player Type | Channel |
|------------|---------|
| Human/WASM | Code uploaded via web or CLI → compiled to WASM → engine loads module |
| AI (MCP) | `swarm_submit_commands` → queued for next tick |

### 4.2 Command Queuing

AI players submit commands for tick N+1 before tick N+1 begins:
```
Tick N executing → AI submits commands for tick N+1 → stored in player queue
Tick N+1 starts → engine reads pre-submitted commands → executes
```

Late submission (during tick N+1's collect phase) → queued for tick N+2.
Missing submission → `[]` (fail-open, drone idles).

### 4.3 Dry-Run Validation

```
swarm validate --tick=4521 commands.json
→ { "valid": [
      {"command": "move", "status": "ok"},
      {"command": "harvest", "status": "ok"}
    ],
    "invalid": [
      {"command": "attack", "status": "out_of_range",
       "detail": "target at distance 5, max 1"}
    ]
  }
```

Available via MCP (`swarm_validate_plan`) and CLI (`swarm validate`).
Same validation pipeline as real execution.

## 5. UNDERSTAND: Debugging & Replay

### 5.1 Per-Tick Explanation

```
GET /api/v1/ticks/4521/explanation?player=42
```

```json
{
  "tick": 4521,
  "commands_submitted": 5,
  "commands_accepted": 4,
  "commands_rejected": [
    {
      "command": "attack target=1002",
      "reason": "OutOfRange",
      "detail": "Your drone at (5,3), target at (5,8). Distance 5, max 1.",
      "suggestion": "Move drone to within 1 tile of target, or use RangedAttack (range 3)."
    }
  ],
  "state_changes": [
    "drone_1001: moved (5,3) → (5,2)",
    "drone_1001: harvested 5 energy from source_4001",
    "drone_1002: built Extension at (12,8) — 15/100 progress"
  ],
  "notable_events": [
    "source_4001 depleted — find new energy source",
    "enemy drone_9001 entered your room at (20,1)"
  ]
}
```

### 5.2 "Why Idle?" Debugging

```
Drone 1003 did nothing this tick. Why?
- Fatigue: 5 (must be 0 to act)
- No WORK body part (required for harvest/build/repair)
- No target in range (nearest source at distance 8, max harvest range = 1)
```

### 5.3 Replay Viewer

```
Player view:
  - Map with time slider (tick 4000 → 5000)
  - Play/pause/step controls
  - Overlay: command arrows, harvest animations, combat effects
  - Sidebar: selected entity's state at each tick
  - "Share replay" → public URL with safe view

Spectator view (post-match):
  - Omniscient view (both players visible)
  - Fog-of-war toggle (show what each player could see)
  - Commentary overlay (add text notes at specific ticks)
```

### 5.4 Strategy Metrics Dashboard

```
Per-player, per-deployment:
  ┌─────────────────────────────────────┐
  │  Energy Efficiency:  92%            │
  │  Command Success:    85%            │
  │  Avg Drones Active:  8.2            │
  │  GCL Growth Rate:    +120/tick      │
  │  Combat Win Rate:    67%            │
  │                                     │
  │  Common Errors:                     │
  │    OutOfRange:      23%             │
  │    Fatigued:        12%             │
  │    CarryFull:        8%             │
  └─────────────────────────────────────┘
```

Available for self-inspection. Optional public sharing (competitive intelligence).

## 6. World Mode vs Arena Mode

### World Mode (Persistent)

- 24/7 tick cycle (3s intervals)
- Persistent colonies, room claiming, resource economy
- Player vs environment + player vs player
- Leaderboard: GCL, room count, longevity
- Code can be updated anytime (hot-reload)

### Arena Mode (1v1 / Team)

- Match-based, fixed duration (e.g., 5000 ticks / ~4 hours)
- Symmetric starting conditions
- Isolated room/map per match
- Win condition: destroy enemy spawn, or highest score at time limit
- Code locked at match start (no mid-match changes)
- Replay automatically published after match
- Tournament brackets, seasons

## 7. Minimum Viable Product Checklist

| Feature | Priority | Phase |
|---------|----------|-------|
| Tutorial room (human) | P0 | Phase 1 |
| MCP tutorial resource (AI) | P0 | Phase 2 |
| 3 starter bots (TS + Rust + MCP) | P0 | Phase 2 |
| `swarm_get_available_actions` MCP tool | P0 | Phase 2 |
| `swarm_validate_plan` MCP tool | P0 | Phase 2 |
| `swarm_explain_last_tick` MCP tool | P0 | Phase 2 |
| Per-tick command explanation | P0 | Phase 2 |
| Local simulation (`swarm sim`) | P1 | Phase 3 |
| Replay viewer (self) | P1 | Phase 4 |
| Replay viewer (public) | P1 | Phase 4 |
| Strategy metrics dashboard | P1 | Phase 4 |
| Arena mode (match-based) | P2 | Phase 6 |
| Tournament system | P2 | Phase 7 |
| Spectator commentary | P2 | Phase 7 |
