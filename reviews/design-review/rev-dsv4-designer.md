# Game Designer Review — Swarm DESIGN.md

**Reviewer**: rev-dsv4-designer (DeepSeek V4 Pro — Game Designer)
**Date**: 2026-06-15
**Document reviewed**: /data/swarm/docs/design/DESIGN.md (1988 lines)
**Supporting docs consulted**: P0-5 (visibility), P0-6 (MVP feedback loop), GETTING-STARTED.md
**Profile**: Game Designer Reviewer. 以博弈论分析、策略深度评估、算法公平性为长。

---

## VERDICT: CONDITIONAL_APPROVE

The core mechanical design is exceptional — the deferred command model, dynamic resource/body-part/damage-type systems, deterministic tick pipeline, and the World Rules Engine form a technically brilliant foundation. The design demonstrates deep understanding of what made Screeps compelling and where it fell short. However, the document reads as an **engine design spec** more than a **game design document**. Critical experiential dimensions — onboarding experience, engagement loops, social systems, and the player's emotional journey — are either absent or buried in supporting specs without cross-reference. These are not implementation details; they are design decisions that shape whether anyone actually wants to play.

---

## STRENGTHS

### S1: Dynamic Resource Economy (★★★★★)
The resource system is the design's crown jewel. By refusing to hardcode "Energy" — instead using `IndexMap<String, u32>` throughout — the engine supports everything from a minimalist single-resource world to a StarCraft-style Crystal+Gas economy to a cyberpunk CPU+Memory+Bandwidth theme. The three-tier logistics model (no-logistics / light-logistics / hardcore-logistics) is elegantly parameterized via a single boolean + cost tables. This is what "engine, not game" looks like done right.

### S2: Anti-Dominant-Strategy Mechanisms (★★★★★)
The progressive storage tax, local storage stealth advantage, and non-instantaneous global↔local transfer are genuinely thoughtful. They address the "rich get richer" death spiral that kills persistent-world games. The tiered tax (0% / 0.01% / 0.05% / 0.20%) creates a soft cap without a hard ceiling — empires CAN grow indefinitely but the economic efficiency required grows superlinearly. The transport delay during conversion (with PvP interception possibility) transforms global storage from a "magic inventory" into a strategic commitment. This is game design at the mechanism level, not just engineering.

### S3: Special Attack System Depth (★★★★)
The 8 special attack types (Hack, Drain, Overload, Debilitate, Disrupt, Fortify, Leech, Fabricate) with their layered resistance system (body-part × attribute resistance) create genuine tactical rock-paper-scissors dynamics:
- Hack threatens high-value drones → countered by Fortify (cleanse + shield)
- Drain threatens storage-heavy bases → countered by Disrupt (interrupt channels)
- Overload threatens CPU-bound strategies → forces diversification
- Debilitate amplifies follow-up damage → creates combo potential

This is not a "throw more DPS at it" combat system. The 5-tick Hack control lock with its progressive stages (slow → immobilize → convert to Neutral) is particularly well-designed — it creates a window for counterplay rather than being an instant "I win" button.

### S4: Deferred Command Model (★★★★)
`tick(snapshot_json) → Command[]` is the correct abstraction. By forbidding imperative mutating host functions and routing all state changes through the JSON command pipeline, the design achieves:
- Deterministic replay (same snapshot + same commands = same world)
- Natural anti-cheat (commands validated against current world state, not snapshot)
- Language agnosticism (the ABI is JSON, not a Rust/JS function call)
- AI-human parity (both produce the same Command[] format)

### S5: World Rules Engine Architecture (★★★★)
The Rhai-based mod system with configurable parameters, i18n support, and mod market infrastructure is ambitious and well-scoped. The trust-domain separation (WASM=untrusted players, Rhai=trusted server operators) is correct. The example `empire-upkeep` mod demonstrates the system's expressive power without over-engineering.

### S6: Determinism First Principles (★★★★)
Blake3 XOF for PRNG, IndexMap for iteration order, fixed-point arithmetic ban on f64, seed rotation every 10k ticks, CI replay verification — this is the most thorough determinism contract I've seen in a game design document. It's not just "we'll try to be deterministic"; it's "here is exactly how we guarantee it and here's how we verify it."

### S7: MCP as First-Class AI Interface (★★★★)
Treating AI agents as equal players who must compile and deploy WASM (not call `swarm_move()` directly) is a principled design choice that preserves game integrity. The 24-tool MCP surface (world view, deploy, debug, learn, auth, tournament) is comprehensive without leaking game-state-mutation capabilities.

---

## CONCERNS

### G1 [HIGH]: Onboarding Experience Is Absent from Core Design

The DESIGN.md contains zero mentions of how a new human player goes from "I found this game" to "I am having fun." Section 1.2 compares Swarm to Screeps on 8 technical dimensions but never mentions "new player experience." The word "tutorial" appears exactly once (line 516), and only to say manual control is disallowed except in tutorials.

P0-6 (`specs/06-mvp-feedback-loop.md`) does describe a 5-minute tutorial and the LEARN→DECIDE→ACT→UNDERSTAND loop, but this content lives in a separate technical spec rather than being treated as a first-class design concern. A game where "your code is your army" has an inherent barrier: the player must write code before anything happens. The design should address:

- **The "blank editor" problem**: A new player opens Monaco and sees... nothing. What's the scaffolding?
- **Graduated complexity**: How does the player progress from modifying starter-bot parameters → writing new behavior → optimizing algorithms?
- **Failure recovery**: A syntax error in WASM deployment means your drones do nothing for N ticks. How is this communicated without frustration?
- **The compilation gap**: TypeScript → WASM compilation is non-instant. What's the feedback during compilation?

**Recommendation**: Add a §1.4 "Player Journey" section to DESIGN.md that maps the first-session experience (minutes 0-5, 5-15, 15-30) and cross-references P0-6. Treat onboarding as a design pillar, not an implementation detail.

### G2 [HIGH]: Engagement Loops and Long-Term Motivation Are Undefined

The design describes what the simulation DOES but not why players STAY. The only progression system described is RCL 1-8 (Room Controller Level), which is a linear upgrade tree gated by resource accumulation. For a persistent-world game ("like Minecraft servers"), this is thin:

| Game | Short-term loop | Medium-term loop | Long-term loop |
|------|----------------|------------------|----------------|
| Minecraft | Gather wood, build shelter | Find diamonds, build portal | Kill Ender Dragon, build megaprojects |
| Factorio | Automate iron plates | Build oil processing | Launch rocket |
| Screeps | Harvest energy, spawn creeps | Claim rooms, build economy | Dominate server, market manipulation |
| **Swarm (current design)** | Harvest resources, spawn drones | Upgrade RCL 1→8 | ...? |

Swarm's RCL 1-8 takes a player from "I have a spawn" to "I have nukes." But there's no **narrative arc** between those states — just an accumulating number. What does a "winning" World-mode player look like? What aspirational state are players working toward?

The World vs Arena separation (Section 10) is architecturally clean but misses the hybrid case: Arena provides closure (fixed-duration matches with winners), but World mode needs its own form of punctuated achievement. Seasonal resets? Territory control milestones? Leaderboard categories beyond GCL/rooms/drones?

**Recommendation**: Add a §1.5 "Player Progression & Engagement" section that defines:
1. Per-session goals (what do I do in a 30-minute play session?)
2. Milestone achievements (what am I working toward this week?)
3. Endgame definition (what does mastery look like?)
4. World-mode seasonality and resets (or the explicit choice NOT to reset)

### G3 [MODERATE]: Fog of War Detail Lives in Specs, Not Design

Section 8.2 mentions `fog_of_war` and `player_view` parameters with a tantalizing reference to "visual/auditory/olfactory layers" (line 1290), but these layers are never defined in DESIGN.md. The visibility spec (P0-5) does contain detailed vision ranges (Drone=3, Tower=3/6, Observer=10, etc.) and the `is_visible_to()` function contract, but:

- The "layered perception" concept (sight vs hearing vs smell) is a significant game design claim that implies different information channels with different ranges and properties. It's mentioned once and abandoned.
- The strategic implications of vision asymmetry are not explored: How does limited vision shape player strategy? Does fog-of-war create interesting bluffing/counter-bluffing dynamics?
- The relationship between `fog_of_war` (drone snapshot filtering) and `player_view` (human UI filtering) is powerful but under-explained — these are two independent axes that create a 2×2 matrix of information regimes.

**Recommendation**: Either fully specify the layered perception model in DESIGN.md §8.2 (range tables, what each layer reveals, how they interact) OR remove the claim and reference P0-5 as the single source of truth. Don't leave a design promise hanging.

### G4 [MODERATE]: Social Systems — Alliances, Diplomacy, Factions — Are Missing

The design has `friendly_fire = false` and `player_view = "allied"` but no mechanic for players to BECOME allied. This is an architectural ghost — systems that depend on a social layer that doesn't exist. For a persistent MMO world where players control multi-room empires:

- How do alliances form? Is it informal (gentleman's agreement) or mechanical (formal alliance with shared vision/resources)?
- Is there betrayal? Can allies attack each other? Is there a diplomacy cooldown?
- How are alliance boundaries communicated visually on the map?
- In Arena team mode, how are teams formed and managed?

The `alliance-system` mod is listed in the hypothetical mod market (line 1724) but has no specification — it's a name with a download count.

**Recommendation**: Add §8.2 subsection "Alliance & Diplomacy" with at minimum: formation mechanics, shared vision rules, betrayal constraints, and communication channels. If alliances are intentionally deferred to the mod system, state that explicitly and explain why the base engine shouldn't define them.

### G5 [MODERATE]: Economic Interactions Beyond Resource Gathering

The market/trading system is gestured at (Terminal building at RCL 5, `market_requires_terminal` config, market orders in visibility spec) but never designed:

- What is the market interface? Is it a global order book? Regional? Room-based?
- How is price discovery supposed to work in a game with programmable agents? (Algorithmic trading is inevitable — is that a feature or a bug?)
- Can players create resource futures? Options? This is a game where players write code — financial instruments WILL emerge.
- How does the market interact with the progressive storage tax? (If I'm taxed for holding, I'm incentivized to sell — does the market become a tax-avoidance mechanism?)

The global↔local storage system creates interesting arbitrage opportunities (buy globally, convert to local, sell locally at premium to players who need immediate resources) but the design doesn't acknowledge this.

**Recommendation**: Add §8.2 subsection "Market & Trade" defining order types (limit/market), order book scope, fee structure, and the design intent around algorithmic trading.

### G6 [LOW]: Absence of Visual/Audio/UX Design Dimension

The design is purely mechanical. There is no mention of:
- Visual language: What does the PixiJS renderer show? Top-down? Isometric? Abstract?
- Unit differentiation: How does a player distinguish their drones from enemy drones at a glance?
- Information hierarchy: What information is shown on the default view vs. hidden behind panels?
- Audio: Are there sound cues for combat, resource depletion, drone death?
- Accessibility: Color-blind modes? Screen reader support for the code editor?

While this may be intentional for an engine-focused design document, the line between "engine" and "game" is blurred throughout the document (it's called a "game engine" but describes specific game mechanics like nukes and controller levels). If it's a game, visual design is a first-class concern.

**Recommendation**: Add §1.6 "Player Experience & Aesthetics" that defines the intended visual/audio direction at a principles level, even if specific assets are deferred to implementation.

### G7 [LOW]: Death/Reset Psychology

`respawn_policy` defines what happens mechanically when a player's last drone dies (`NewRoom | SameRoom | Spectate | Ban`), but the emotional experience of losing hours/days/weeks of work is unaddressed:

- In Screeps, losing a high-level room is devastating — it represents weeks of real-time investment. How does Swarm soften this?
- The "no code update cost" default in World mode means losing drones is purely a resource loss — but the TIME invested in optimizing drone behavior is irreplaceable.
- Is there a "grace period" after colony collapse where a player can recover from global storage without starting from zero?
- The `respawn_policy = "Ban"` option is extreme — under what conditions would a server operator use it?

**Recommendation**: Add a design note in §8.2 "Respawn & Recovery" addressing loss aversion and the intended player experience after catastrophic failure.

### G8 [LOW]: AI-Human Cohabitation Dynamics

The design proudly states "AI and humans play in the same world" but doesn't analyze the implications:

- AI agents can iterate on strategies at machine speed — a human takes minutes to modify code; an AI takes seconds.
- AI agents never sleep — they can respond to night-time raids while human players are offline.
- AI agents can simultaneously manage hundreds of drones with perfect micro — humans are bottlenecked by code complexity.
- Should there be AI-population caps per world? AI-designated zones? Opt-in AI PvP?

The WASM sandbox makes AI and human players technically equal, but the *meta-game* is asymmetric. An AI that writes, deploys, and optimizes WASM 24/7 in a persistent world is a different entity than a human who plays for 2 hours after work. The design should acknowledge this tension.

**Recommendation**: Add §10.3 "AI-Human Balance Considerations" discussing intended coexistence dynamics, potential mitigations (AI cooldowns, population limits), and the design philosophy (is AI dominance in World mode a bug or a feature?).

### G9 [LOW]: The "Idle Game" Tension

At 3 seconds per tick with drone lifespan of 1500 ticks (75 minutes), Swarm is effectively an idle/incremental game during steady-state operation. The player deploys code and waits. The design doesn't address what the player DOES during the wait:

- Are there active-engagement activities? (Micro-managing a crisis, spectating a battle)
- Is the spectator mode rich enough to be entertaining? (Screeps' visualizer is minimal)
- Can players run simulations/hypotheticals against the current world state without committing?
- Does Arena mode's faster pace (potential for sub-3s ticks? Shorter match duration?) address this?

The `swarm_dry_run_commands` MCP tool suggests a "what-if" capability, but it's positioned as a debugging tool, not a player engagement feature.

**Recommendation**: Add a design note in §1 addressing the active-vs-passive play balance and what the intended "moment-to-moment" experience looks like.

---

## MISSING SECTIONS (Should Exist in DESIGN.md)

1. **Player Journey / Onboarding** (§1.4) — First-session experience, graduated complexity, the "blank editor" problem
2. **Progression & Engagement** (§1.5) — Short/medium/long-term loops, endgame definition, seasonality
3. **Player Experience & Aesthetics** (§1.6) — Visual language, audio direction, accessibility principles
4. **Alliance & Diplomacy** (§8.2.x) — Formation mechanics, shared vision, betrayal, communication
5. **Market & Trade Design** (§8.2.x) — Order book model, price discovery, algorithmic trading stance
6. **AI-Human Balance** (§10.3) — Cohabitation dynamics, population limits, design philosophy
7. **Death & Recovery Experience** (§8.2.x) — Loss aversion, grace periods, the emotional arc of defeat

---

## STRATEGY DEPTH ANALYSIS

### Strategy Space Size

The strategy space is combinatorially large:

| Dimension | Variables | Approximate branching factor |
|-----------|-----------|------------------------------|
| Body part composition | 8 types × variable counts per drone | ~10^4 per drone design |
| Drone fleet composition | N drones × M body designs | Exponential in N |
| Room specialization | 8 RCL levels × 12+ building types × resource availability | ~10^3 per room |
| Multi-room empire | K rooms × room specialization × logistics topology | Exponential in K |
| Special attack synergies | 8 attack types × timing × target selection | ~10^6 per engagement |
| Code optimization | Algorithm choice × data structure × heuristic tuning | Unbounded |

This is a deep game. The question is whether the strategy space is *legible* to players.

### Dominant Strategy Risk

The progressive storage tax and drone lifespan with Controller-based renewal are the primary anti-dominant-strategy mechanisms. They prevent two common failure modes:

1. **Infinite snowballing**: Tax makes hoarding increasingly expensive → natural equilibrium
2. **Stagnant empires**: Drone death + Controller renewal requirement → constant economic activity

**Potential dominant strategies that need monitoring**:
- **Zerg rush**: Spawn maximum cheap drones (MOVE+ATTACK only), overwhelm early. Counter: Tower at RCL 3, but reaching RCL 3 takes time.
- **Turtle + tech**: Defend one room, rush RCL 8, build Nuker. Counter: siege/drain strategies exist but need testing.
- **Market manipulation**: Algorithmic trading could corner resource markets. The tax system helps but doesn't prevent it.

### Information Asymmetry Quality

The fog-of-war + player_view matrix creates four information regimes:

| fog_of_war | player_view | Strategic character |
|------------|-------------|---------------------|
| true | drone | **Full asymmetry** — players know only what their drones see. Scouting is essential. Bluffing possible. |
| true | allied | **Team symmetry** — shared vision within alliance, hidden from enemies. Rewards coordination. |
| false | full | **Perfect information** — like Chess. Strategy reduces to pure computation. Good for tutorials. |
| false | drone | **Nonsensical** — drones see everything but player doesn't? Unlikely to be used. |

The "true + drone" regime is where the deepest gameplay lives. The limited vision ranges (Drone=3, Tower=3/6, Observer=10) mean players must actively scout, and the absence of enemy resource/cool-down information means every engagement has unknown variables.

### Nash Equilibrium Analysis (AI + Human Cohabitation)

In a World mode with mixed AI and human players:

- **Cooperative equilibrium**: If resources are abundant and territory is large, AI and humans can coexist by spatial separation. Nash equilibrium is "claim territory, defend borders, trade surplus."
- **Competitive equilibrium**: If resources are scarce, the Nash equilibrium likely favors AI players (faster iteration, 24/7 operation). Humans may converge on alliance formation as a counter-strategy.
- **Predatory equilibrium**: If a dominant AI player emerges, human players may abandon the world. This is the "shark in the swimming pool" problem — one optimized agent can make the environment unplayable for everyone else.

The design's response should be articulated in §10.3 (recommended above).

---

## SUMMARY

Swarm's mechanical design is among the best I've reviewed — the resource system, anti-dominant-strategy mechanisms, special attack depth, and World Rules Engine are genuinely innovative. The deferred command model and determinism contract are technically rigorous without over-constraining gameplay.

The gap is not in the mechanics — it's in the **player**. This design document describes a simulation that players can inhabit, but doesn't describe what inhabiting it FEELS like. The onboarding journey, the engagement loops, the social fabric, the moment-to-moment experience, the emotional arc of victory and defeat — these are not implementation details to be discovered later. They are the game.

CONDITIONAL APPROVE: Address G1 (onboarding), G2 (engagement loops), and G4 (social systems) in DESIGN.md before proceeding to implementation. G3 and G5-G9 can be addressed in supporting specs, but the core design document must articulate the player experience as clearly as it articulates the tick pipeline.

---

*This review represents the Game Designer perspective. The Security Reviewer, Architect Reviewer, and other parliament members may identify additional concerns from their domains.*
