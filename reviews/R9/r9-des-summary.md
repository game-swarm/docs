# Swarm — Game Designer Review Summary

> **Reviewer role**: Game Designer
> **Sources**: DESIGN.md, specs/p0/06-mvp-feedback-loop.md, specs/p0/07-world-rules-engine.md, specs/p0/08-game-api-idl.md
> **Date**: 2026-06-14

---

## 1. Core Gameplay Loop

Swarm is a **programming RTS**: players write code (compiled to WASM) that autonomously controls units called drones. There is no real-time manual input — the code *is* the strategy.

The per-tick loop runs every 3 seconds:

```
LEARN → DECIDE → ACT → UNDERSTAND
  ↑                          │
  └──────────────────────────┘
```

Concretely each tick:
1. Each player's WASM module receives a JSON snapshot of the visible world
2. The module returns a list of Commands (move, harvest, attack, build, spawn, etc.)
3. The engine validates and applies all commands in a shuffled-fair order
4. Results broadcast to clients; rejected commands include a human-readable reason + suggestion

The feedback loop spec (P0-6) mandates all four steps be closed for MVP: learning (tutorial/docs), decision (snapshot + dry-run tools), action (WASM deploy), and understanding (per-tick explanation API + replay viewer).

---

## 2. Drone Lifecycle

Drones are the primary controllable unit. Key lifecycle facts:

| Property | Value |
|----------|-------|
| Max age (`lifespan`) | **1500 ticks** ≈ 75 minutes @ 3 s/tick (configurable) |
| Age tracking | `drone.age` increments each tick; `death_system` auto-recycles at `lifespan` |
| Spawned by | Spawn structure (costs body part resources) |
| Recycled by | `Recycle` command at a Spawn (50% resource refund) |

Drones carry a `body: Vec<BodyPart>` that determines every capability. A drone with no `Work` part cannot harvest or build. No body parts can be added after spawn — body composition is a spawn-time decision.

**Fatigue** gates movement: drones on swamp terrain accumulate fatigue; they cannot act until fatigue reaches 0. Number of `Move` parts reduces fatigue per tick.

---

## 3. Controller RCL (Room Control Level)

Each room has a Controller. Owning and upgrading it unlocks buildings and raises the drone cap.

| RCL | Cumulative Progress | Unlocked Buildings | Max Drones/Room |
|-----|--------------------|--------------------|-----------------|
| 1 | 0 | Spawn | 50 |
| 2 | 200 | Extension ×5, Road, Container | 100 |
| 3 | 500 | Extension ×10, Tower, Storage | 200 |
| 4 | 1,500 | Extension ×20, Link | 300 |
| 5 | 5,000 | Extension ×30, Terminal, Observer | 400 |
| 6 | 15,000 | Extension ×40, Extractor, Lab, Factory | 500 |
| 7 | 50,000 | Extension ×50, PowerSpawn | 500 (hard cap) |
| 8 | 150,000 | Extension ×60, Nuker | 500 |

**Upgrading**: Transfer resources into the Controller each tick → auto-converts to `progress`. On `progress >= progress_total`, level advances.

**Downgrade**: If a Controller loses its owner and `downgrade_timer` (default 5 000 ticks) expires, it drops one level and progress resets to 0. This creates meaningful territorial pressure.

---

## 4. Body Part Costs

Default costs from the IDL (authoritative source; `world.toml` can override per-world):

| Body Part | Default Cost | Capability |
|-----------|-------------|------------|
| Move | Energy 50 | Movement; reduces fatigue |
| Work | Energy 100 | Harvest, build, repair, special attacks |
| Carry | Energy 50 | Hold resources for transfer/withdraw |
| Attack | Energy 80 | Melee attack (range 1), Disrupt |
| RangedAttack | Energy 150 | Ranged attack (range 3), Overload |
| Heal | Energy 250 | Heals friendly drones (range 3) |
| Claim | Energy 600 | Controller claim/upgrade, Hack |
| Tough | Energy 10 | Reduces Kinetic + Sonic damage taken, Fortify |

Max body size: **50 parts** per drone. A body's total cost is the sum of its parts. `Recycle` refunds 50%.

---

## 5. Damage Types

Damage types are **world-configurable**, not hardcoded. The default world defines six:

| Type | Description | Notable Resistances |
|------|-------------|---------------------|
| **Kinetic** | Impact, blunt force, explosion | Tough part: ×0.5 |
| **Thermal** | Fire, laser, plasma | — |
| **EMP** | Electric shock, overload, e-jamming | Structures: ×2.0 (weak) |
| **Sonic** | Vibration, resonance | Tough part: ×0.5 |
| **Corrosive** | Acid, nano-dissolution, bio | Structures: ×1.5 (weak) |
| **Psionic** | Mental attack, AI hijack | Counters Hack |

Resistance stacks in two layers: **component resistance** (fixed, from body part / structure type) × **attribute resistance** (dynamic, assigned by mods/rules, e.g. `Shielded = 0.7`). Immunity (`multiplier = 0`) can be granted via mod scripting — intended for boss units or world events.

Body part → damage type bindings (defaults):

| Source | Damage Type | Base Damage |
|--------|-------------|-------------|
| Attack part | Kinetic | 30 |
| RangedAttack part | Kinetic | 20 |
| Tower (auto) | Kinetic | 50 |
| Heal part | — (reverse) | 12 HP restored |

---

## 6. Special Attacks

Beyond HP damage, six special attack types exist as command-level abilities tied to specific body parts:

| Attack | Required Part | Effect | Countered By |
|--------|--------------|--------|--------------|
| **Hack** | Claim | Captures target drone if `hits < max_hits × 0.3`; transfers ownership | Target Psionic resistance |
| **Drain** | Carry + Work | Steals resources from target structure, `carry_capacity` units/tick; must stay in range 1 | Target EMP resistance |
| **Overload** | RangedAttack | Reduces target's CPU fuel budget by ~500k fuel; no HP damage | Target EMP resistance |
| **Debilitate** | Work | Doubles target's vulnerability to a damage type for 50 ticks | Target Corrosive resistance |
| **Disrupt** | Attack | Interrupts target's ongoing action (Drain/Hack); no HP damage | Target Sonic resistance |
| **Fortify** | Tough | Grants self/ally ×0.5 damage reduction for 100 ticks (buff) | None — it's a buff |

General rules:
- A body part cannot deal HP damage *and* a special attack in the same tick
- Continuous attacks (Drain, Hack) break if the drone moves or is Disrupted
- All effects scale with the world's `damage_multiplier` rule

---

## 7. Global Storage Economics

Resource flow has two layers with explicit logistics costs between them:

```
Local Storage (physical)          Global Storage (abstract)
─────────────────────────         ──────────────────────────
Lives in buildings                Not tied to any location
Drones deposit here first         Can pay deployment fees
Can be raided/destroyed           Can be market-traded instantly
Fully private                     Partially visible (leaderboard tier)
                    ←──── cost + delay ────→
```

**Default transfer costs:**

| Direction | Cost | Delay |
|-----------|------|-------|
| Local → Global | 1% of resource | 10 ticks |
| Global → Local | 5% of resource | 5 ticks |

During transit, resources are locked ("in transit") and can theoretically be intercepted (PvP Phase 6).

**Three logistics modes** (server-configurable):

| Mode | Setting | Feel |
|------|---------|------|
| No logistics | `global_storage_enabled=true`, cost=0 | Simplified; good for Arena / new players |
| Light logistics (default) | 1%/5% costs, delays enabled | Strategic depth without punishing new players |
| Hardcore logistics | `global_storage_enabled=false` | All resources are physical; Carry drones required — Factorio-style |

**Anti-dominant-strategy mechanisms** to prevent hoarding:

1. **Progressive storage tax** — exceeding 30% of capacity triggers per-tick upkeep fees, scaling up to 0.20%/tick above 85% capacity
2. **Local storage stealth** — enemies cannot see what's in your buildings until they scout/capture; incentivises keeping reserves local
3. **No teleport rule** — transfers always take non-zero time; global storage cannot be used as instant battle supply

---

## 8. World Mode vs Arena Mode

| Dimension | World (Persistent) | Arena (Match-based) |
|-----------|-------------------|---------------------|
| Duration | 24/7, indefinite | Fixed length (e.g. 5 000 ticks ≈ 4 h) |
| Map | Persistent, random-generated | Symmetric, per-match |
| Fairness | Not a goal — players join at different times | Symmetric start conditions |
| Spawn | Random room | Fixed symmetric spawn |
| Code updates | Anytime (hot-reload) | Locked at match start |
| Win condition | None (territorial/economic) | Destroy enemy Spawn, or most points at time limit |
| Replay | Private by default | Auto-published post-match |
| Spectating | Disabled by default | Enabled by default |
| Storage tax | Active | Disabled (competitive fairness) |
| Fog of war | true (drone-only vision) | false (full map visible) |
| Leaderboard | Vanity (colony age, GCL, rooms) | Ranked by league: Human/WASM, AI-assisted, AI tournament |

Arena is Phase 6+; World is the MVP target.

---

## 9. Visibility & Spectator System

Two independent axes control what is seen:

**Drone perception** (`fog_of_war`):
- `true` (default World): WASM `tick()` snapshot only contains entities within the drone's sensing range — drones are informationally blind to the wider map
- `false` (tutorials, cooperative): snapshot includes full map; drones "know everything"

**Player view** (`player_view`):
- `"drone"` — player sees only what their drones see (matches fog_of_war)
- `"full"` — player sees the entire map regardless of drone position (tutorial / cooperative)
- `"allied"` — player sees the union of all allied drones' vision

**Spectator settings:**

| Rule | Default (World) | Default (Arena) |
|------|----------------|----------------|
| `public_spectate` | false | true |
| `spectate_delay` | 0 ticks | recommended ≥ 100 ticks to prevent intel leakage |
| `replay_privacy` | `"private"` | `"public"` (forced post-match) |

Replay viewer supports: tick scrubber, play/pause/step, command-arrow overlays, entity state sidebar, fog-of-war toggle for post-match spectators, annotation overlays for commentary.

---

## 10. Mod System

Rules are **Rhai scripts + declarative TOML config**, not WASM. Three-tier trust model:

```
Player code  →  WASM sandbox     (untrusted, process-isolated)
Rule mods    →  Rhai scripts     (server-owner trusted, engine-embedded)
Engine core  →  Rust             (immutable)
```

A mod is a directory with:
- `mod.toml` — metadata + typed configurable parameters
- `init.rhai` — runs once on load
- `tick_start.rhai` / `tick_end.rhai` — runs each tick

**Rhai API surface available to mods:**
- Read: `state.players()`, `player.drones()`, `player.rooms()`, `player.resources()`
- Write (via `actions`): deduct/award resources, damage entities, set entity flags (whitelist only), emit events, log
- Forbidden: file I/O, network, clock, entropy (determinism requirement)

**Execution budget per mod per tick hook:**

| Resource | Limit | Over-limit behaviour |
|----------|-------|---------------------|
| AST nodes | 10 000 | Mod skipped this tick, warning logged |
| `actions` calls | 100 | Extras discarded |
| Player iteration | 3 000 items | Excess players skipped |
| Wall-clock time | 100 ms | Hard kill; mod marked "degraded" |

Mods that breach limits for 10 consecutive ticks are auto-disabled until re-enabled by the server owner.

**Example built-in mod — `empire-upkeep`:** charges per-tick Energy fees based on drone count + rooms, with a superlinear room penalty. Configurable shortfall behaviour: `degrade` / `damage` / `despawn`.

Install flow:
```bash
swarm mod install empire-upkeep
swarm mod config empire-upkeep drone_cost 5
swarm world add-mod empire-upkeep
```

---

## 11. New Player Experience

### Human programmer (target: 5-minute tutorial)

1. Opens Web client → isolated tutorial room (separate from live World)
2. Pre-written bot runs automatically; guided overlay steps explain Spawn, drones, harvesting, Tower placement
3. Guided code edits with immediate feedback (tutorial tick = 1 s, not 3 s)
4. Prompt to deploy to World or try Arena when ready

### AI agent (MCP tutorial)

1. Connect → `swarm://docs/tutorials/basic-agent`
2. Call `swarm_get_snapshot` → see world; `swarm_get_available_actions` → know what's possible
3. Generate WASM → `swarm_validate_module` → `swarm_deploy`
4. Observe via `swarm_get_snapshot` + `swarm_explain_last_tick` → iterate

**Key principle**: AI agents do not control drones directly through MCP — they write and deploy WASM code, identical to human players. There is no `swarm_move` or `swarm_attack` MCP tool.

### Starter bots (one-command deploy)

| Language | Bot | Purpose |
|----------|-----|---------|
| TypeScript | `basic-harvester` | 3 drones, harvest nearest source, return energy |
| TypeScript | `tower-defense` | Build Tower, basic defense |
| TypeScript | `room-claimer` | Claim room, upgrade Controller |
| Rust | `basic-harvester` | Same as TS |
| Python (MCP) | `basic-agent` | Demonstrates MCP tick loop |

### Debug tools (close the feedback loop)

- **Per-tick explanation API**: rejected commands include distance/range detail + actionable suggestion ("Move drone within 1 tile, or use RangedAttack with range 3")
- **"Why idle?" debugger**: explains fatigue, missing body parts, no targets in range
- **Local sim**: `swarm sim --ticks=5000 --speed=100x` — offline iteration without a server
- **Replay viewer**: tick scrubber + command overlays + fog-of-war toggle + shareable URL
- **Strategy dashboard**: energy efficiency, command success rate, average active drones, common error breakdown — self-visible, optionally public

---

## Key Design Tensions to Watch

1. **Logistics depth vs new-player accessibility** — three logistics modes mitigate this, but the default (light logistics) still requires understanding global/local duality early
2. **Drone lifespan forcing constant re-spawn** — 1 500 ticks is intentionally short; players must automate spawn loops from the start, which is both a teaching moment and a potential frustration gate
3. **Body composition irreversibility** — no mid-life part changes create strong spawn-time decisions; punishing for new players who don't yet know what parts they'll need
4. **Arena code-lock tension** — locking code at match start is competitive-clean but means bugs discovered mid-match cannot be fixed; needs clear UI communication
5. **Mod system power** — `actions.damage_entity` and resource deduction in Rhai mods can dramatically alter game feel; server owners need good documentation and the auto-disable safeguard is important
