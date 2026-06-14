# R10 Game Designer Review — rev-dsv4-designer

**Reviewer**: DeepSeek V4 Pro (Game Designer)
**Date**: 2026-06-14
**Documents reviewed**: DESIGN.md (full), tech-choices.md, P0-1 through P0-9

---

## VERDICT

**APPROVE_WITH_RESERVATIONS**

The design achieves its core vision — a programming arena where humans and AI compete on equal footing through WASM. The deferred command model, fuel metering fairness, and the anti-dominant-strategy mechanisms (progressive storage tax, drone lifespan with expansion reset) are well-conceived and demonstrate mature game design thinking. The rule module system and resource configurability give the platform extraordinary breadth.

However, the strategy space narrowing, information asymmetry gaps, and PvE incentive vacuum need attention before Phase 2 implementation. 11 concerns identified below.

---

## STRENGTHS

1. **Deferred Command Model** — `tick() → Command[]` with server-side validation is the single best design decision. It eliminates client-side cheating, creates a natural information asymmetry boundary, and enforces the "code is king" philosophy.

2. **Anti-Dominant-Strategy Mechanisms** — The progressive global storage tax, drone lifespan + Controller-capture reset, and seeded shuffle turn ordering form a three-layer anti-snowball system. The design explicitly names "anti-dominant-strategy" in §8.2 (全局存储反制机制), which is rare and commendable in engine design docs.

3. **Resource Model Generality** — `HashMap<ResourceName, Amount>` instead of hardcoded `Energy` is the right abstraction for a game engine platform. The StarCraft (Crystal+Gas), Age of Empires (Food+Wood+Stone+Gold), and cyberpunk (CPU+Memory+Bandwidth) examples show the team understands breadth.

4. **Three Logistics Modes** — No-logistics / Light / Hardcore logistics create clean gradients from casual to hardcore without compromising the core engine.

5. **MCP as Peer to Web UI** — The design explicitly rejects MCP-as-game-controller and forces AI agents through the same WASM path as humans. The P0-3 §4.5 "明确不在 MCP 中的" section is a precise contract that prevents scope creep.

6. **WASM Side Rule Visibility** — `host_get_world_rules` and `Game.world.rules()` in SDK let drone code adapt to world-specific rules at runtime. This enables general-purpose strategies that work across differently-configured worlds.

7. **Drone Body Irreversibility** — Body parts are fixed after spawn, forcing commitment to a strategy. The 50% recycle refund creates meaningful sunk-cost tension.

---

## CONCERNS

### Strategy Space & Dominant Strategy

**G1 — SEVERITY: HIGH**
**Drone Lifespan + Controller Reset Creates Binary Expansion Pressure**

Drone lifespan (1500 ticks default) combined with age reset on Controller capture creates a hard "expand or die" constraint. A player who loses all Controllers sees their entire drone fleet age out within 1500 ticks (~75 min). This means:
- Defensive/turtle archetypes are non-viable in standard rules
- Losing one critical battle → cascading colony collapse → unrecoverable
- The optimal strategy may converge to "always be capturing" — a narrow strategic band

*Recommendation*: Add a `drone_lifespan_refresh_source` rule that allows alternative reset mechanisms (e.g., achieving a GCL milestone, holding N rooms for M ticks, consuming a rare resource). This preserves the anti-turtle incentive while offering multiple strategic paths.

**G2 — SEVERITY: MEDIUM**
**"Hack" Special Attack Has No Counter-Play Beyond Psionic Resistance**

The Hack attack (Claim body part, 30% HP threshold for takeover) has a 100-tick cooldown but no active defense. A player with 10 Claim drones can attempt 10 hacks every 100 ticks. If Psionic resistance is the only mitigation, dominant strategies may converge to "stack Psionic resistance or lose your drone fleet."

*Recommendation*: Add a "Hack immunity" window after a successful hack (target can't be hacked again for N ticks per source) and/or make Hack success probability scale inversely with target's remaining hits percentage (not binary at 30%). Also consider a "hack warning" visible to the owning player one tick before the hack completes.

**G3 — SEVERITY: MEDIUM**
**Seeded Shuffle Creates "Last Position" Avoidance Meta**

The seeded shuffle makes turn order unpredictable per tick, which is good. But players who observe they're late in the shuffle one tick may over-avoid resource competition the next tick, creating a "last position paranoia" behavior. The `SourceEmpty` 50% refund partially mitigates this, but the strategic overhead of constantly hedging against worst-case position may reduce the game to "play it safe" — a degenerate equilibrium.

*Recommendation*: Track and expose (optional, per-world) a "shuffle position history" so players can verify fairness. Also consider a `shuffle_window` rule that guarantees each player gets each position roughly equally over a window (e.g., 1000 ticks), converting the random shuffle into a guaranteed fair rotation.

### Information Asymmetry

**G4 — SEVERITY: MEDIUM**
**Default Vision Ranges Create Near-Full Information in Moderate Empires**

A drone has vision range 3 (hex, ~37 tiles). With 10 drones spread across a room, coverage is nearly complete. Tower (3, charged 6) and Observer (10) extend this further. This means fog-of-war provides strategic depth only in the early game (1-3 drones) and at empire edges. Mid-game onward, players have near-complete situational awareness within their territory — reducing the value of scouting, hidden armies, and deception.

*Recommendation*: Reduce default drone vision to 1-2 and make vision range a body part attribute. Add a `Scout` body part (low cost, no combat, vision 5-8). This creates a trade-off: scouting drones consume spawn slots and resources but provide intelligence. Currently vision is "free" — all drones see 3.

**G5 — SEVERITY: HIGH**
**Arena Mode Eliminates Fog of War — Removes Strategic Deception**

P0-7 §6 and P0-5 §7 state Arena mode has `fog_of_war = false`. This eliminates: feints, hidden army positioning, surprise attacks, and scout unit value. Arena becomes a resource optimization puzzle with perfect information — closer to an auction or bidding game than a strategy game. The spectator experience may be better with fog-of-war enabled (showing each player's limited view).

*Recommendation*: Arena should default to `fog_of_war = true` with optional `player_view = "full"` for spectators only (via `spectate_delay`). P0-5 already has the two-layer separation (drone perception vs player camera) — use it. The drone's `tick()` gets fog-of-war-filtered snapshot, but spectators see the delayed full map.

**G6 — SEVERITY: MEDIUM**
**`swarm_simulate` Gives AI Agents an Asymmetric Intelligence Advantage**

`swarm_simulate` (5 calls/tick in World mode, 3/tick in Arena) allows AI agents to predict future states deterministically. Human players must mentally simulate. While the fuel budget equalizes CPU, the ability to programmatically explore future states creates an intelligence asymmetry that fuel metering doesn't capture.

*Recommendation*: Restrict `swarm_simulate` to a per-deployment budget (e.g., 100 simulations per code version) rather than per-tick. Human players can also write simulation logic in their WASM, but the MCP tool shouldn't provide a free "perfect oracle" the human lacks. Alternatively, add `swarm_simulate` to the human Web UI as a button.

### PvE + PvP Incentives

**G7 — SEVERITY: HIGH**
**No Built-in Cooperative Mechanics — PvE Incentive Vacuum**

The design has PvP (combat, Tower defense), but there are no built-in cooperation mechanics. In World mode, players are implicitly competitors for territory and resources. Cooperation is a dominated strategy: a cooperating player expends resources helping another who may later attack them. The alliance-system is mentioned as a potential mod (§8.7, "alliance-system") but not part of the core design.

This matters because:
- World mode with AI+human coexistence needs cooperation to prevent "everyone vs everyone" degeneracy
- PvE content (shared threats, world events) is entirely absent
- Without cooperation, late-joining players face an insurmountable "established empire" barrier

*Recommendation*: Add at minimum: (1) a `shared_vision` rule that allows allied players to see each other's drone vision; (2) a `resource_tribute` command that allows voluntary resource transfer between players; (3) a "world event" hook in the Rhai module system (`on_world_event`) for PvE content. The alliance system should be a Tier-1 core feature, not a mod.

**G8 — SEVERITY: LOW**
**Global Storage Tax Penalizes Economic Specialization**

The progressive tax (0% → 0.01% → 0.05% → 0.20% per tick) discourages hoarding but also penalizes players who specialize in economic optimization. A player who's very good at resource generation but bad at spending (building, expanding) is taxed for their inefficiency rather than rewarded for their production. This is a design choice, not a bug, but worth noting: the tax hits economic strategies harder than military ones.

*Recommendation*: Add a `tax_exemption` window after resource acquisition (e.g., resources earned in the last N ticks are tax-free). This rewards active income over passive hoarding.

**G9 — SEVERITY: LOW**
**Transfer Delay Creates "Defenseless Window" During Transport**

Resources being transferred (10 ticks local→global, 5 ticks global→local) are "in transit" and unavailable. A player transferring resources to global storage for a code update can't use them if attacked during that 10-tick window. This is realistic but may feel unfair — the player did nothing wrong, they just got unlucky with attack timing.

*Recommendation*: Allow cancellation of in-progress transfers (with partial resource loss, e.g., 50% of transferred amount lost). This gives the player a strategic choice: cancel the transfer to defend, or hold and hope the attack fails.

### Nash Equilibrium & AI-Human Coexistence

**G10 — SEVERITY: MEDIUM**
**AI Optimization Advantage in Routine Tasks is Not Fully Addressed**

Fuel metering equalizes per-tick computation, but AI agents can:
- Pre-compute optimal build orders offline (before deployment)
- Use `swarm_simulate` to explore strategy trees (G6 above)
- Generate more efficient WASM through compiler optimization knowledge

The Nash equilibrium may settle where AI dominates resource optimization and humans dominate strategic prediction (reading opponent intent). This is not necessarily bad — it creates complementary niches — but the design doesn't acknowledge or design for this split.

*Recommendation*: Add a "strategy transparency" rule option where players can see high-level metrics of opponent strategies (e.g., "Player X is focusing on expansion" / "Player Y is stockpiling for attack") derived from observable data. This helps humans compete in the strategic layer while AI competes in the optimization layer.

**G11 — SEVERITY: MEDIUM**
**World Mode Has No Fair-Division Mechanism for Late Joiners**

Late-joining players in World mode get whatever territory remains — which may be a room adjacent to a level-8 Controller. The RandomRoom spawn policy makes this a function of luck, not skill. This creates a "rich get richer" dynamic where established players have permanent advantages, and new players face a progressively worsening initial condition.

*Recommendation*: Add a `new_player_protection` rule: new players get N ticks of invulnerability (safe mode on their first Controller) and a resource stipend scaled to the world's average wealth. This is already partially designed in the Controller safe mode mechanic — extend it to initial spawn. Also add a `spawn_distance_min` rule preventing spawns within N rooms of established colonies.

---

## MISSING

1. **Cooperation mechanics** — No alliance, shared vision, resource tribute, or joint operations. The "alliance-system" mod is mentioned but not designed. This is a gap for World mode PvE+PvP coexistence.

2. **PvE content framework** — No world events, environmental threats, or shared objectives. The Rhai module system could support `on_world_event` hooks but doesn't define them.

3. **Scout/reconnaissance specialization** — All drones have the same vision range. No trade-off between combat/economic drones and intelligence-gathering drones.

4. **Anti-Hack counterplay** — Hack has only passive resistance (Psionic). No active defense, warning system, or immunity window.

5. **Late-joiner fairness** — No mechanism to prevent new players from spawning next to max-level empires with no recourse.

6. **Strategy transparency for humans** — AI can programmatically analyze opponents; humans need high-level strategic indicators to compete.

7. **Tournament/league structure design** — Arena mode is defined at the engine level but the meta-game structure (leagues, seasons, rankings) is deferred to Phase 7. Some decisions (leaderboard metrics, ranking algorithm) affect engine design.

---

## STRATEGY DEPTH ANALYSIS

### Strategy Space Cardinality (Rough Estimate)

At each tick, a player controls up to 500 drones, each with a body configuration from a combinatorially large space (8 body part types, max 50 parts). For each drone, available actions depend on position, targets in range, fatigue, and body parts. Conservatively:

- Per drone per tick: ~5-15 valid action choices
- With 10 active drones: ~5^10 to 15^10 = ~10^7 to 10^11 action combinations
- Across a 1500-tick drone lifespan: astronomically large

BUT: the strategy space is heavily constrained by:
- Drone body irreversibility (commits to role)
- Resource constraints (can't do everything)
- Fog-of-war (can't see everything)
- Turn order uncertainty (can't perfectly plan)

**Effective strategy depth: HIGH** — comparable to StarCraft at the micro level with Civilization's empire management at the macro level.

### Dominant Strategy Risk Assessment

| Strategy | Viability | Counter | Risk of Dominance |
|----------|-----------|---------|-------------------|
| Harvester spam | Viable early | Empire upkeep, drone cap, resource depletion | LOW |
| Turtle + tech | Non-viable (G1) | Drone lifespan forces expansion | **HIGH** (strategy gap) |
| Zerg rush | Viable | Tower defense, defender advantage | LOW-MEDIUM |
| Economic snowball | Viable | Progressive tax (G8), Hack vulnerability (G2) | LOW |
| Hack domination | Viable (G2 concern) | Psionic resistance only | MEDIUM |
| Scout + snipe | Non-viable (G4) | Vision ranges too permissive | N/A (gap) |

### World Mode PvE+PvP Nash Equilibrium (Preliminary)

In a mixed human-AI World mode with default rules:
1. AI players converge to resource-optimal build orders and efficient WASM
2. Human players converge to reading AI patterns and exploiting predictable behavior
3. Both types spread territorially to avoid resource competition (SourceEmpty avoidance)
4. Stable equilibrium: AI dominates resource efficiency; humans dominate strategic adaptation
5. Risk: without cooperation mechanics, the equilibrium is "everyone fights everyone" — a negative-sum arms race

### Information Asymmetry Effectiveness

Fog-of-war provides strategic depth primarily in:
- Early game (1-10 drones): meaningful hidden information
- Empire edges: border rooms have partial visibility
- Enemy territory: zero visibility unless scouting

Mid-to-late game, intra-territory visibility is near-complete (G4). The primary remaining information asymmetries are:
- Enemy resource reserves (hidden)
- Enemy Controller progress (hidden)
- Enemy drone fatigue/cooldowns (hidden)
- Enemy code version/strategy (hidden)

These hidden variables create a meaningful "poker-like" information game even with full positional visibility.

---

## SUMMARY

```
Verdict: APPROVE_WITH_RESERVATIONS

Blocking issues (must fix before Phase 2):
  G1  [HIGH]  Drone lifespan forces binary expand-or-die strategy
  G5  [HIGH]  Arena disables fog-of-war, eliminates strategic deception
  G7  [HIGH]  No cooperation mechanics, PvE incentive vacuum

High-priority issues (should fix before Phase 3):
  G2  [MED]   Hack has no active counterplay
  G3  [MED]   Seeded shuffle creates "last position avoidance" meta
  G4  [MED]   Default vision ranges too permissive
  G6  [MED]   swarm_simulate creates AI intelligence asymmetry
  G10 [MED]   AI optimization advantage not fully addressed
  G11 [MED]   No fair-division mechanism for late joiners

Low-priority issues (can defer):
  G8  [LOW]   Storage tax penalizes economic specialization
  G9  [LOW]   Transfer delay creates defenseless window
```

---

*Reviewer signature: rev-dsv4-designer (DeepSeek V4 Pro, Game Designer direction)*
