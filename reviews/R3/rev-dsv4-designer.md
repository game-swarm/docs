# R3 Game Designer Review — rev-dsv4-designer

> Reviewer: DeepSeek V4 Pro (Game Designer direction, primary)
> Date: 2026-06-16
> Scope: DESIGN.md + specs/05,07,09 + tech-choices.md
> Method: 博弈论分析 / 策略空间评估 / 信息不对称审计 / 激励结构验证

---

## Overall Verdict: APPROVE_WITH_RESERVATIONS

The design foundation is exceptionally strong for a programming RTS. The WASM sandbox model where AI and humans follow identical code→deploy→execute paths is the single best decision in this document — it makes fairness architectural rather than policy-based. The World Rules Engine's separation of "engine core" from "game content" is equally important and correctly scoped.

My reservations are game-design-level: the PvE dimension is missing, some anti-snowball mechanics need reinforcement, and the Arena mode risks becoming a solved game without strategic variety mechanisms. These are addressable in the same design phase and none are fundamental flaws.

---

## Strengths

### S1: Fairness-by-architecture (AI = Human execution path)

The design's single strongest feature: AI agents use MCP to *see* the world and *deploy WASM*, but never to *act* in the world directly. All gameplay flows through `tick(snapshot) → Command[]`. This is not a policy decision but an architectural invariant — enforced by the Source Gate (specs/09 §4) rejecting non-WASM gameplay commands.

From a game theory perspective, this produces a genuine Nash equilibrium: the optimal strategy for an AI agent is to write better WASM code, not to exploit API differences. The playing field is level by construction.

### S2: World Rules Engine enables genre-spanning experiences

The three-layer extension model (Core/Declarative/Experimental) and the `world.toml` configuration system means Swarm can be:
- A minimalist single-resource deathmatch (Energy only, fast decay)
- A complex Factorio-like logistics puzzle (multi-resource, hardcore logistics mode)
- A StarCraft-style asymmetric RTS (custom body parts, damage types, special attacks)

This is not just "configurable" — it's genuinely transformational. The separation of "what a game is" from "what the engine provides" is correctly architected.

### S3: Drone lifespan + repair creates non-trivial logistics

The drone aging system (1500 base ticks, body-part modifiers, active_aging at 110%, controller/depot repair with hard caps) creates a genuine resource management puzzle:

- **Forward Depot** placement becomes a tactical decision: where do you put your repair stations? Too far forward → vulnerable to destruction. Too far back → drones spend too much time commuting for repairs.
- **Controller repair cap** (50% of natural aging) prevents infinite drone maintenance — lifespan remains meaningful even with optimized infrastructure.
- **Recycle at 50% refund** creates a "build order" optimization: when do you recycle an aging drone vs. let it die naturally?

This is the kind of mechanic that separates good players from great ones.

### S4: Progressive storage tax is well-calibrated

The four-tier tax system (0% / 0.01% / 0.05% / 0.20%) creates a soft ceiling on resource hoarding without punishing normal play. The tax only kicks in at 30% capacity, meaning small-to-medium players pay nothing. This is an elegant solution to the rich-get-richer problem — much better than hard caps or arbitrary limits.

### S5: Eight special attacks create genuine strategic variety

Hack, Drain, Overload, Debilitate, Disrupt, Fortify, Leech, Fabricate — this is not an arbitrary list. Each serves a distinct strategic role:

| Attack | Strategic Role | Counter |
|--------|---------------|---------|
| Hack | Territory denial (steal drones) | Disrupt, Fortify |
| Drain | Economic warfare (steal resources) | Disrupt, tower defense |
| Overload | CPU denial (starve opponent's computation) | Fortify, spread drones |
| Debilitate | Force multiplier (amplify damage) | Fortify (cleanse) |
| Disrupt | Interrupt (stop Hack/Drain/Debilitate) | Positioning |
| Fortify | Defense + cleanse (universal counter) | High cooldown (300) |
| Leech | Sustain (heal while damaging) | Anti-Corrosive resistance |
| Fabricate | Ultimate swing (convert enemy to structure) | Psionic resistance, very high cost |

This creates a genuine rock-paper-scissors meta where no single strategy dominates. The cooldowns (50-500 ticks) mean commitment to a strategy path has real weight.

### S6: Information asymmetry is well-layered

The fog-of-war design correctly separates "what the drone knows" (snapshot) from "what the player sees" (player_view). The hidden information categories (enemy resources, controller progress, cooldowns, fatigue) are exactly the right ones to hide — they create uncertainty that rewards scouting and risk-taking without making the game unplayable.

---

## Concerns (Game Design)

### G1: PvE dimension is entirely absent — World mode risks zero-sum decay

**Severity**: HIGH

The design mentions "World 模式下 PvE + PvP" (DESIGN §9 header context) but PvE content is nowhere specified. In a pure PvP persistent world with economic warfare (Drain, Overload, territorial conquest):

- **New players face a negative-sum entry**: they must compete for resources against established players with RCL 8 rooms, Nukers, and optimized logistics. Even with density-priority spawning and 500-tick safe_mode, the skill-to-resource gap is crushing.
- **Losers have no PvE progression path**: if you lose your territory, you respawn with nothing. There's no "farm PvE to rebuild" option — you must re-enter PvP immediately.
- **Winners have no PvE content to engage**: once you dominate your region, the only activity is crushing weaker players. This accelerates player churn.

**Recommendation**: Add a PvE design section. At minimum:
1. **Neutral creeps / wildlife**: Spawn in unclaimed rooms, drop resources when killed. Provide a non-zero-sum resource source.
2. **Periodic world events**: Resource surges, environmental hazards, NPC invasions — create temporary cooperation incentives.
3. **PvE progression milestones**: Achievements, cosmetics, or minor bonuses from PvE activities that don't require PvP dominance.

Without PvE, the World mode economy is structurally zero-sum — every winner creates a loser. That's sustainable for Arena (finite duration, symmetric start) but toxic for a persistent world.

### G2: Arena mode risks becoming a "solved game"

**Severity**: MEDIUM

Arena mode features: symmetric maps, fixed initial resources, locked WASM at match start, single win condition. With identical starting conditions, there exists an optimal opening strategy. Once discovered, all matches become:
1. Execute optimal opener
2. First deviation loses

This is the "Chess opening theory" problem — except Chess has 10^120+ game tree complexity. Swarm Arena may have much less. The current design has no mechanisms to force strategic variety:

- Map_seed exists but only changes terrain layout — same resource distribution
- No bans/picks for body parts, special attacks, or starting conditions
- No hidden information at game start (full arena visible in Arena mode)

**Recommendation**:
1. **Map variety**: Multiple map templates with different resource layouts (rich center, edge-heavy, sparse) that force different openers
2. **Pre-match ban phase**: Each player bans 1-2 body parts or special attacks before match start
3. **Blind initial composition**: First N ticks with limited visibility so neither player knows the opponent's opener
4. **Random resource distribution**: Same total resources but different spatial placement (requires scouting)

### G3: Overload creates asymmetric AI-vs-Human impact

**Severity**: MEDIUM

Overload directly attacks the opponent's fuel budget. This creates an asymmetry:

- **AI agents** need fuel for computation (pathfinding, strategy evaluation, multi-drone coordination). A 5% fuel reduction may force an AI to simplify its strategy or control fewer drones.
- **Human players** with hand-optimized, low-computation code are minimally affected by fuel reduction. Their strategy doesn't change — they just execute fewer drone actions proportionally.

This means Overload is a *stronger weapon against AI players than human players*. In a mixed human-AI world, this creates a perverse incentive: target AI opponents with Overload first because it's more effective. The security review's C2 finding about information leakage through Overload compounds this — an attacker can probe to identify AI vs. human opponents based on behavioral response to fuel pressure.

**Recommendation**: 
1. Consider making fuel budget degradation affect *all* drone commands equally (reduce command slots proportionally), not just computation
2. Or: give AI players a "computation reserve" that's separate from action fuel — Overload only affects action fuel, not strategy computation
3. At minimum: document that Overload's asymmetric impact is intentional and accepted

### G4: Code update cost = 0 undermines strategic commitment

**Severity**: LOW

With free code updates and no cooldown (World default) or cooldown of 5 ticks, players can instantly adapt their strategy. This reduces the cost of strategic mistakes and encourages reactive play over planning.

In Screeps, code changes had meaningful costs (CPU cycles to propagate, spawn timing). In Swarm, `code_update_cooldown = 5` and `code_update_cost = {}` means you can change your entire army's behavior every 15 seconds (5 ticks × 3s). This is too fast for meaningful strategic commitment.

**Recommendation**: 
- World default: `code_update_cost = { Energy: 200 }` — small but non-zero
- Arena: locked code at match start (already the case, good)
- Consider `code_propagation_speed = 1` (non-zero) as World default — makes code updates a gradual, tactical process rather than instant global switch

### G5: No explicit anti-griefing beyond safe_mode

**Severity**: LOW

The 500-tick safe_mode protects new players, but what prevents an established player from:
- Parking high-level drones just outside a newbie's room and killing everything the moment safe_mode expires?
- Systematically hunting new players across respawns?
- Using multiple accounts to surround a new player's room?

The density-priority spawn helps (new players go to low-density areas) but doesn't prevent targeted harassment once they're found.

**Recommendation**:
1. **Escalating respawn protection**: Each consecutive death within N ticks extends safe_mode duration
2. **Anti-harassment detection**: If player A kills player B's drones more than K times in M ticks without B being able to meaningfully fight back (RCL gap > 2), flag for admin review or auto-apply protection
3. **GCL-based matchmaking suggestion**: Recommend new players join worlds with similar-average-GCL populations

### G6: Drone lifespan creates maintenance burden at scale

**Severity**: LOW

At 50+ drones, the drone replacement cycle becomes a significant fraction of total player attention. Every 1500 ticks (~75 minutes at 3s/tick), each drone dies and must be replaced. With active_aging at 110%, actively used drones die faster. 

The repair mechanic helps but has hard caps (controller repair limited to 50% of natural aging). At large scales, a player may spend more time managing the spawn→replace→repair pipeline than making strategic decisions.

**Recommendation**:
1. Add a "spawn queue" API: players can set a persistent spawn template that auto-spawns when resources/room-cap permit
2. Consider "drone squad" abstraction at high counts: group N identical drones into a single tactical unit controlled by one tick() output, reducing micromanagement
3. Add "repair drone" body part type: dedicated repair units that service nearby drones, creating a logistics sub-game rather than manual replacement

---

## Missing from Design

### M1: PvE content design

As discussed in G1. The spec mentions "World 模式下 PvE + PvP" but provides zero PvE mechanics. This is the single biggest gap in the current design.

### M2: Social / cooperative mechanics

The design has a market (Terminal) for resource trading but no:
- Alliances or factions
- Shared territory or joint building
- Cooperative PvE objectives
- Communication infrastructure (in-game messaging, shared maps)

For a persistent world, social mechanics are what retain players. A purely competitive zero-sum world hemorrhages players.

### M3: Economy sink design

The design has resource *sources* (harvesting, source regeneration) and resource *transfer* (market, global↔local logistics) but limited resource *sinks*:
- Drone spawn costs (one-time)
- Building construction (one-time)
- Progressive storage tax (scales with wealth)
- Drone decay/lifespan (constant rate)

Missing sinks:
- **Research/technology tree**: Spend resources to unlock upgrades (body part efficiency, building capacity, vision range)
- **Cosmetic/vanity**: Non-gameplay-affecting purchases that signal status
- **Territory maintenance**: Room-level upkeep that increases with room count (beyond empire-upkeep mod)

Without sinks, resources accumulate indefinitely, leading to inflation and reduced strategic tension.

### M4: Catch-up mechanics

Beyond density-priority spawn seeding, there are no mechanisms for late-joining players to catch up:
- No "underdog bonus" (resource gathering multiplier for low-GCL players)
- No technology diffusion (new players learn from established neighbors)
- No seasonal/epoch resets (World mode is truly persistent)

The progressive tax helps slow down the rich but doesn't speed up the poor.

### M5: Moment-to-moment player experience

The design focuses on architecture and systems but doesn't describe what a typical play session feels like. Key questions unanswered:
- What does a player do in the first 5 minutes? First hour? First week?
- What are the satisfying "aha" moments? (First successful Hack? First room capture?)
- What does the learning curve look like?
- How does the game teach itself? (Tutorial world is mentioned but not designed)

---

## Strategy Depth Analysis

### Strategy Space Dimensionality

I estimate the strategy space dimensionality:

| Dimension | Parameters | Approximate Branching |
|-----------|-----------|----------------------|
| Body composition | 8 types × [0..50] parts | ~10^8 combinations |
| Room expansion order | Room grid × claim timing | ~10^3 meaningful choices |
| Logistics network | Depot placement × Carry routes | ~10^4 topologies |
| Special attack investment | 8 attacks × timing × target selection | ~10^5 meaningful sequences |
| Resource allocation | Multi-resource × build vs. stockpile vs. trade | ~10^3 states |
| Code update timing | Tick-level decisions × propagation | ~10^2 per game phase |

**Total strategy space**: Easily >10^15 meaningful distinct strategies. This is sufficient for a deep game — comparable to StarCraft II's build-order space (~10^12).

### Dominant Strategy Analysis

Does a dominant strategy exist? I tested the hypothesis: "Maximum harvester → maximum reinvestment → exponential growth"

**Counter-forces in the design**:
1. **Drone lifespan cap (1500 ticks)**: Drones die regardless of resources. This puts a hard ceiling on "infinite drone army" — you can maintain at most `max_drones_per_player × lifespan` worth of drone-tick years.
2. **Room drone cap (50 at RCL 1, 500 at RCL 8)**: Room-level saturation forces territorial expansion, which triggers PvP conflict.
3. **Progressive storage tax**: Hoarding has diminishing returns.
4. **Empire upkeep (mod)**: Superlinear room costs punish over-expansion.
5. **Eight special attacks**: Aggressive strategies can be countered — a pure-economic player is vulnerable to Drain + Hack.

**Verdict**: No single dominant strategy. The interplay of caps, taxes, and counters creates a healthy mixed-strategy equilibrium. However, this depends on all anti-snowball mechanics being deployed — in a minimal-config world without empire-upkeep, exponential growth may dominate.

### Information Asymmetry Quality

The fog-of-war design is well-structured:

| Information | Visible to Self | Visible to Enemy | Visible to Spectator |
|-------------|----------------|-----------------|---------------------|
| Drone positions | ✅ | ✅ (in vision) | ✅ |
| Drone body parts | ✅ | ✅ (visible feature) | ✅ |
| Own resources | ✅ | ❌ | ❌ |
| Enemy resources | ❌ | N/A | ❌ |
| Controller progress | ✅ | ❌ | ❌ (unless owned) |
| Cooldown state | ✅ | ❌ | ❌ |
| Fatigue | ✅ | ❌ | ❌ |
| WASM code | ✅ | ❌ | ❌ |
| Rejected commands | ✅ | ❌ | ❌ |

This asymmetry creates meaningful scouting incentives:
- You can *see* enemy drone composition (body parts) → infer their strategy
- You *cannot* see their resources, cooldowns, or code → must probe to gather intel
- The market and leaderboard provide partial economic information → creates a metagame of information management

**AI advantage concern**: MCP's `swarm_simulate` (5/tick, 100-tick simulation) gives AI agents a what-if analysis capability that human players lack. An AI can simulate "if I attack from the north, what happens?" before committing. This is a genuine information advantage that's not available through the Web UI.

**Recommendation**: Consider adding a "simulate" button to the Web UI for parity, or limiting `swarm_simulate` to post-tick analysis rather than pre-commit simulation.

### PvE + PvP Incentive Correctness

**Current state**: The design has no PvE specification. The incentives are purely PvP: conquer rooms, drain enemies, dominate territory.

**Problem**: Pure PvP incentives in a persistent world create a "king of the hill" dynamic where:
1. Early players dominate
2. Late players struggle
3. Losers quit
4. Winners get bored
5. Player base shrinks

**Solution direction**: PvE should provide:
- **Parallel progression**: Non-PvP ways to gain resources and advance
- **Cooperation incentives**: World events that reward temporary alliances
- **Asymmetric goals**: Not everyone needs to be #1 on the leaderboard — PvE achievements provide alternative prestige

Without PvE, the World mode economy is structurally extractive — every winner extracts value from a loser. This is sustainable only with constant new player inflow (which is unlikely for a niche programming game).

### AI vs Human Nash Equilibrium

The design creates an interesting mixed equilibrium:

| Capability | AI Advantage | Human Advantage |
|-----------|-------------|-----------------|
| Computational optimization | Strong (pathfinding, resource allocation) | Weak |
| Multi-tasking | Strong (parallel drone coordination) | Weak |
| Strategic creativity | Weak (bounded by training data) | Strong (novel strategies) |
| Long-term planning | Moderate (simulation-limited) | Strong |
| Adaptation speed | Strong (can re-optimize code rapidly) | Weak (manual recoding) |
| Pattern recognition | Strong | Strong |
| Psychological warfare | None | Strong (bluffing, feints) |

**Equilibrium prediction**: At equal skill, AI agents will dominate in tactical efficiency (optimal pathfinding, perfect resource allocation) while humans will dominate in strategic creativity (novel build orders, unexpected attack vectors). The fuel metering system constrains AI's computational advantage, preventing it from being overwhelming.

This is a *healthy* equilibrium — both player types have viable paths to success. The concern is G3 (Overload asymmetry) which tilts this balance against AI players.

---

## Summary

| Category | Count | Details |
|----------|-------|---------|
| Strengths | 6 | S1-S6 |
| Concerns | 6 | G1 (PvE absent, HIGH), G2 (Arena solved-game risk, MEDIUM), G3 (Overload AI asymmetry, MEDIUM), G4 (free code updates, LOW), G5 (anti-griefing gaps, LOW), G6 (drone maintenance burden, LOW) |
| Missing | 5 | M1 (PvE), M2 (Social mechanics), M3 (Economy sinks), M4 (Catch-up), M5 (Player experience) |

**Core recommendation**: Prioritize G1 (PvE design). This is not an optional feature — it's structural to the World mode's long-term viability. Without PvE, the persistent world economy is zero-sum and will experience player churn regardless of how good the PvP mechanics are.

The architecture is ready. The engine is correctly scoped. The game content layer needs a PvE design pass before implementation begins.
