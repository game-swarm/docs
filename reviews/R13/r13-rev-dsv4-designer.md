# R13 — Game Designer Review

**Reviewer:** rev-dsv4-designer (DeepSeek V4 Pro)
**Date:** 2026-06-14
**Documents Reviewed:** DESIGN.md, tech-choices.md, P0-1~P0-9
**Role:** Game Designer — 博弈论分析 / 策略深度评估 / 算法公平性

---

## Verdict

**APPROVE_WITH_RESERVATIONS**

The design is fundamentally sound. The deferred command model, WASM sandbox parity between human and AI players, seeded shuffle for fairness, and layered visibility system form a coherent strategic foundation. The concerns below are addressable — none are design-level fatal flaws — but several require explicit resolution before Phase 1 implementation to avoid baking in strategic pathologies.

---

## Strengths

1. **Human-AI parity is the right default.** WASM is the sole executor. MCP is AI's "screen and mouse," not a gameplay shortcut. No McpPlayerExecutor — only WasmSandboxExecutor. This is the single most important design decision, and it's correct.

2. **Seeded shuffle for player ordering** (Blake3 XOF from tick_number || world_seed) is elegant. It provides determinism for replay, fairness for players, and unpredictability that prevents ordering exploitation. The "can't speed up to get a better slot" property is critical.

3. **Deferred command model** (tick() → JSON) is strategically rich. Players submit intentions without guarantees, creating risk/reward around resource contention. The refund policy (50% for contention losses, 0% for self-inflicted errors) is well-calibrated.

4. **Three-tier logistics model** (no-logistics / light / hardcore) is a rare example of vertical difficulty scaling done right. Each tier serves a distinct player segment without compromising the others. The "in-transit resources interceptable in PvP" detail shows genuine strategic thinking.

5. **Progressive global storage tax** with three anti-dominant-strategy pillars (tax, stealth advantage, transport time) demonstrates awareness of economic monopoly as a design problem. The non-linear tiers (0% → 0.01% → 0.05% → 0.20%) discourage hoarding without punishing legitimate economic growth.

6. **Drone lifespan + renewal** creates genuine expansion pressure. The 50% oldest-drone age reset on controller capture, with 500-tick cooldown, turns room conquest into a strategic resource beyond territory — it buys your existing army more time. This is clever.

7. **Code deployment as strategy** (update_cost, cooldown, propagation_speed, windows) elevates software deployment from infrastructure detail to gameplay mechanic. A player managing code propagation across a 20-room empire is playing a fundamentally different game than one in a single room.

8. **Fog-of-war + player_view separation** correctly distinguishes "what your drone perceives" (fairness boundary) from "what you see on screen" (UX boundary). The P0-5 spec's invariant — WASM tick() always receives is_visible_to-filtered snapshots regardless of player_view — is the right invariant.

9. **Dynamic resource types** (not hardcoded Energy) enable fundamentally different economic games on different worlds. A Crystal+Gas world plays differently from an Energy-only world, and both play differently from a CPU+Memory+Bandwidth world.

10. **Special attacks** (Hack, Drain, Overload, Debilitate, Disrupt, Fortify) add non-HP-axis strategic depth to combat. Overload reducing enemy fuel budget is a meta-game attack that exists nowhere else in the programming-game genre.

---

## Concerns

### G1 — Critical

**G1.1 — World mode lacks catch-up mechanics for late joiners.**

The design explicitly states World mode "doesn't pursue fairness" (DESIGN §8.6, §10) but provides zero mechanical support for late-joining players. An established empire after 100,000 ticks has:
- Multiple RCL-8 rooms with full Extensions
- 500-drone armies with optimized body compositions
- Accumulated global storage and market positions
- Code bases refined over thousands of iterations

A new player spawning in RandomRoom faces an insurmountable gap. The progressive storage tax and drone lifespan both slow the leader but do nothing to accelerate the trailer. Without catch-up mechanics, World mode becomes unplayable for newcomers after the first month.

**Recommendation:** Consider tiered starting resources based on world age (e.g., new players in worlds older than 10,000 ticks receive 5× starting energy and a pre-built Extension). Or implement a "newbie protection" period with PvP immunity and boosted resource rates. This is not about making World "fair" — it's about making it playable.

**G1.2 — Drone lifespan + renewal creates "snowball" feedback.**

The renewal mechanic (capture a room → reset 50% of oldest drones' age) means players who are already expanding get to keep their existing army, while players who are stagnant or losing lose drones to aging. The 500-tick cooldown prevents spam but doesn't change the direction: expansion feeds expansion. Combined with G1.1, this means established empires both have more resources AND face lower attrition.

**Recommendation:** Consider decoupling renewal from conquest. Options: (a) renewal tied to energy expenditure rather than room capture; (b) fixed "drone retirement" replaced by a more predictable decay curve; (c) all players get periodic age-reset "molt" events regardless of expansion status.

### G2 — Significant

**G2.1 — AI iteration advantage in practice.**

AI agents can run `swarm_simulate` 5×/tick and `swarm_dry_run_commands` 20×/hour for offline strategy testing. A human's equivalent is `swarm sim` (local, Phase 3) which is slower and less integrated. In World mode where both coexist, AI players have a structural iteration-speed advantage:
- AI: MCP loop → simulate → refine → deploy → observe → repeat (fully automated)
- Human: Write code → local sim → deploy → observe → think → rewrite (manual steps)

The 10/hour deploy limit bounds deployment frequency but not testing frequency. Five simulate calls per tick over 24 hours = 432,000 simulated ticks of strategy refinement. A human cannot match this.

**Recommendation:** Consider per-hour simulate limits (not just per-tick), or add a fuel cost to simulate that's higher than the discount (currently 0.5× MAX_FUEL). Alternatively, provide humans with equivalent local tooling before World mode launches with AI players.

**G2.2 — `player_view='full'` + `spectate_delay=0` information leak.**

If a World server enables both `player_view='full'` and `public_spectate=true` with `spectate_delay=0`, a spectator can see the full map in real-time and relay information to a player via out-of-band channels (Discord, etc.). P0-5 §3.5 partially mitigates with "spectate_delay ≥ 50 when public_spectate=true in World" but this constraint is specified only in P0-5, not enforced in DESIGN.md's main configuration section (§8.2).

**Recommendation:** Move the spectate_delay constraint from P0-5 to DESIGN.md §8.2 and make it a config validation rule (reject on load, not at runtime). Also consider: if `player_view='full'` and `fog_of_war=true`, the WASM still receives filtered snapshots — but the human watching the screen sees everything. This creates a secondary information channel (human sees, human codes differently) that bypasses fog-of-war. Document this explicitly.

**G2.3 — Tutorial→World transition cliff.**

Tutorial world: Recycle returns 100% body cost. Standard world: 50%. This is a 2× difficulty jump on a core economic mechanic. A player who learns "recycle is free" in tutorial faces immediate resource shocks when their first 10-drone recomposition costs 2,500 Energy instead of being free. No intermediate step exists.

**Recommendation:** Add a "novice world" or "beginner world" preset with Recycle at 75% and other eased parameters. Make the transition graduated: Tutorial (100%, isolated) → Novice (75%, real world, PvP off) → Standard (50%, full rules). Or scale Recycle refund by player age: first 2,000 ticks = 100%, next 3,000 = 75%, thereafter = 50%.

### G3 — Moderate

**G3.1 — Arena scoring undefined.**

Arena mode victory conditions are mentioned ("destroy enemy Spawn, or highest score at time limit") but "score" is never defined. Is it GCL? Total resources? Territory size? Drone count? Damage dealt? Different scoring functions produce dramatically different optimal strategies. A "destroy Spawn" victory condition encourages all-in rushes; a "highest GCL" condition encourages economic turtle strategies. Both can be fun, but the scoring function IS the game in Arena mode.

**Recommendation:** Define Arena scoring in DESIGN.md before Phase 1. Consider multi-factor scoring (GCL × territory × resource efficiency) or a weighted sum with configurable weights per tournament.

**G3.2 — Market mechanics unspecified.**

Market trading is referenced throughout (global storage, Terminal, `market_requires_terminal`, "all active orders visible") but the market's core mechanics are never specified:
- Order types? (limit orders only, or also market orders?)
- Matching algorithm? (price-time priority? pro-rata?)
- Fee structure? (maker/taker fees? flat per-order cost?)
- Settlement? (instant? per-tick batch?)

The global storage anti-dominant-strategy design interacts with market mechanics: if a wealthy player can place orders that never fill but distort the order book, the tax alone may not prevent market manipulation.

**Recommendation:** Add a P0-10 "Market Mechanics Spec" or integrate into DESIGN.md §8. At minimum: order types, matching rules, fee structure, and anti-manipulation measures (e.g., minimum fill ratio, order expiry).

**G3.3 — No drone cap exceptions for small empires.**

MAX_DRONES_PER_PLAYER = 500 is a hard cap. But a single-room empire with 500 drones has fundamentally different capabilities than a 20-room empire with 25 drones per room (same total). The RCL table specifies per-room drone limits (50/100/200/300/400/500/500/500) but the 500 hard cap means RCL-8 rooms cannot fill their slots if the player already has 500 drones elsewhere. This is a non-obvious constraint that rewards spreading drones thin across many rooms rather than concentrating force.

**Recommendation:** Either (a) make max_drones_per_player configurable per-RCL-tier, or (b) replace with per-room caps only and remove the global cap, or (c) document the strategic implication explicitly so players understand the tradeoff.

**G3.4 — Overload attack symmetry concern.**

Overload reduces target's fuel budget by 500k (5% of MAX_FUEL). If multiple players coordinate Overload attacks on one target, the target's budget hits the 20% hard floor (2M fuel). At 2M fuel, a player's WASM has 80% less computation — potentially preventing complex pathfinding, multi-drone coordination, or market analysis. This is a rich strategic option but may become a dominant strategy in multi-player diplomacy: gang up on the leader with Overload, keep them at 20% fuel permanently.

**Recommendation:** Add diminishing returns to Overload within a time window (e.g., each successive Overload in a 50-tick window has 50% reduced effect). Or add a post-Overload "recovery surge" that restores fuel faster if the target survives.

**G3.5 — Memory upkeep cost precision factor unspecified.**

`memory_spawn_cost` and `memory_upkeep_cost` are described with a `× 精度因子` multiplier but the precision factor value is never defined. The example shows `memory_spawn_cost = { Energy = 0.5 }` — is 0.5 the final cost, or does a precision factor apply? If the latter, what is the factor and why isn't it folded into the config value?

**Recommendation:** Either remove the precision factor abstraction (have config directly specify per-byte cost) or define it explicitly with rationale.

### G4 — Minor

**G4.1 — `code_update_cooldown` minimum rationale unclear.**

The spec says World mode minimum is 5 ticks "to prevent re-deploy refund abuse." But P0-2 §7.2 already has deploy-reset rules (refund credit invalidated on module change). The 5-tick cooldown and the deploy-reset rule serve overlapping purposes. If the deploy-reset rule works correctly, the cooldown minimum could be 1 tick. If the deploy-reset rule has gaps, those should be fixed rather than patched by cooldown.

**Recommendation:** Clarify the threat model. If deploy-reset handles it, reduce minimum to 1. If not, fix deploy-reset and then reduce.

**G4.2 — Body part `Carry` capacity undefined.**

Harvest validation checks `drone.carry_used < drone.carry_capacity` but Carry capacity per body part is not specified in DESIGN.md or P0-8 IDL. A drone with 1×Carry and one with 10×Carry need clearly different capacities for strategic planning.

**Recommendation:** Add Carry capacity to P0-8 IDL body_cost section or DESIGN.md body part table.

**G4.3 — Hack's "turn to Neutral, still runs original WASM" edge case.**

When Hack succeeds, the drone becomes Neutral (not owned by any player) but continues executing the original owner's WASM. This creates a peculiar state: a Neutral drone running enemy code, immune to further Hacks for 5 ticks. What if the original owner's WASM contains logic like "if I'm being hacked, self-destruct"? Does the Neutral drone execute this? Does the original owner control Neutral drones in any way? This edge case needs explicit specification.

**Recommendation:** Define Neutral drone behavior: (a) does it still execute tick()? (b) if yes, does the original owner's code run? (c) can the original owner issue self-targeting commands (Recycle)? (d) after 5-tick immunity, who can Hack it?

**G4.4 — Player name regex `[a-zA-Z0-9 _-]` allows ASCII-only.**

The name regex excludes all non-ASCII characters including CJK, Cyrillic, Arabic, and emoji. For a game targeting a global audience with Chinese-language design docs, this is unnecessarily restrictive. The prompt injection concern (names shouldn't contain delimiter characters) is valid but can be solved by using non-ASCII delimiters (as the spec itself suggests: `[[`/`]]` or Unicode).

**Recommendation:** Allow Unicode letters in player names. Use Unicode delimiter characters (e.g., `‖‖‖`) in the AI SDK prompt template — already done per P0-3 §6.3.

---

## Missing

1. **Arena scoring function.** (See G3.1) — must be defined before Phase 6.
2. **Market mechanics specification.** (See G3.2) — must be defined before Phase 3 (market features).
3. **Catch-up mechanics for World mode.** (See G1.1) — critical for long-term World viability.
4. **Intermediate difficulty preset** between Tutorial and Standard worlds. (See G2.3)
5. **Drone behavior specification for special combat states** — stun, root, silence, Neutral. Current spec only covers Neutral from Hack.
6. **Resource sink design.** The progressive tax is anti-hoarding but not a sink — it redistributes nothing. What happens to taxed resources? Are they destroyed (deflationary)? Redistributed (zero-sum)? Added to a world pool (inflationary)? This affects long-term economic balance.
7. **Alliance/faction system** is not in DESIGN.md but appears in the Rhai mod marketplace example (`alliance-system`). If alliances are core (shared vision, coordinated attacks), they need base engine support, not just a mod. If they're optional, the marketplace listing is premature.
8. **Death/permadeath semantics.** What happens when all a player's drones die and they have no Spawn? The respawn_policy covers colony extinction but not the intermediate case of "Spawn exists but no drones." Can the Spawn auto-produce a free basic drone?

---

## Strategy Depth Analysis

### Strategy Space Dimensionality

The game's strategy space decomposes into independent but interacting dimensions:

| Dimension | Degrees of Freedom | Bounded By |
|-----------|-------------------|------------|
| Body composition | Combinatorial (8 part types × up to 50 slots) | Spawn energy, body_cost |
| Room expansion | Spatial (map topology) | fog-of-war, terrain, enemy presence |
| RCL progression | Linear (1→8) with fixed costs | Resource income rate |
| Economic resource mix | N-dimensional (N configurable resource types) | Source availability, trade |
| Logistics topology | Graph (room connectivity × transport paths) | Distance, terrain, carry capacity |
| Code strategy | Turing-complete (arbitrary WASM logic) | Fuel budget (10M instructions/tick) |
| Temporal (deployment timing) | Discrete (tick-granular windows) | Code cooldown, propagation speed |
| Combat tactics | Compositional (body part + position + special attacks) | Fatigue, range, body requirements |
| Information gathering | Scout drone positioning | Visibility ranges, fog-of-war |
| Diplomatic (future) | Player-player coordination | Not yet specified |

Estimated strategy space: **10^6 to 10^12 distinct viable states** before considering code logic. With Turing-complete WASM, the effective space is unbounded — but bounded by fuel, making it an *optimization-under-constraint* problem rather than a *search* problem.

### Dominant Strategy Analysis

**Does a dominant strategy exist?**

At current spec, no single strategy dominates all others, but several *dominant strategy clusters* are identifiable:

1. **Early rush** (spawn MOVE+ATTACK drones, attack neighbor spawns before they build defenses) — strong in small maps, weak against Tower defense + RangedAttack.
2. **Economic turtle** (maximize harvesting, rush RCL, build Towers, expand slowly) — strong against rushes, vulnerable to being contained and out-scaled.
3. **Tech rush** (minimize drone count, maximize RCL progression to unlock Extensions and Terminal) — fragile early, dominant late if uncontested.
4. **Harassment** (small groups of fast drones raiding enemy harvesters) — wins through economic attrition rather than direct combat.

These form a **non-transitive balance** (rock-paper-scissors dynamics): Rush beats Tech, Tech beats Turtle, Turtle beats Rush, Harassment disrupts all three. This is the ideal state for strategic depth.

**However**, the drone lifespan mechanic (G1.2) biases the meta toward expansion-heavy strategies. A Turtle who holds 1 room sees drones die of old age while an expander who holds 5 rooms gets renewal. Over long timescales, this may collapse the non-transitive balance into "expand or die."

### Fog-of-War Strategic Depth

The current fog-of-war design creates three layers of strategic information play:

1. **Scout positioning** — where you place drones determines what you see. Vision ranges (3 for drones, 6 for charged Towers, 10 for Observer) create a spectrum from "blind" to "omniscient in my territory."

2. **Information denial** — hidden enemy resources, controller progress, and cooldowns mean you cannot perfectly calculate enemy capabilities. You must infer from observable behavior (drone count, building types, expansion rate).

3. **Deception** — because body parts are visible but fatigue/cooldowns are not, a player can position attack drones that appear threatening but are actually fatigued, or vice versa.

**Depth assessment: Good.** The hidden information set is well-chosen — it hides what you'd need espionage to discover (resources, progress, internal state) but shows what any observer would see (positions, body types, building types). The `player_view` separation from `fog_of_war` enables both competitive integrity and spectating enjoyment.

### PvE + PvP Incentive Structure (World Mode)

World mode's incentives break down as:

| Action | PvE Incentive | PvP Incentive | Tension |
|--------|-------------|-------------|---------|
| Harvest resources | ✅ Always positive | ⚠️ Exposes drones to raids | Balancing harvester count vs defender count |
| Upgrade Controller | ✅ Unlocks buildings | ⚠️ Reveals room importance | Visible progress attracts attacks |
| Build Towers | ✅ Defense | ❌ Resource cost that could have been drones | Defender's dilemma |
| Expand to new room | ✅ More resources | ⚠️ Thinner defense spread | Empire coherence vs sprawl |
| Attack neighbor | ❌ Costs resources, drones | ✅ Potential territory gain | Aggression cost-benefit |
| Trade on market | ✅ Resource optimization | ⚠️ Reveals economic strength | Information leakage |

The **mixed PvE+PvP incentive structure is well-balanced**. No single action is optimal in all contexts. The primary risk is that in worlds with low player density (few neighbors), PvE dominates and the game becomes a solo optimization problem — which is fine for World mode's "Minecraft server" philosophy but needs acknowledgment.

### AI + Human Nash Equilibrium

In a game where AI and humans coexist with identical mechanics:

**Short-term equilibrium**: Both populations optimize within their comparative advantages:
- **Humans** excel at creative strategy shifts, intuition about opponent psychology, and "reading the room" meta
- **AI agents** excel at precise optimization, systematic exploration of strategy space, and rapid iteration

At Nash equilibrium, each player type's strategy is a best response to the mixed population's expected strategies. The seeded shuffle and resource contention mechanics ensure no player type has a structural execution advantage.

**Long-term equilibrium risk**: If AI agents achieve superhuman performance (possible given simulation+iteration advantage, G2.1), human players may be driven out of World mode. This is not a design flaw — it's the expected outcome of a game where "better code wins" — but it has product implications:
- World servers may need AI-only, human-only, and mixed shards
- Arena mode already segments by player type (Human/WASM, AI-assisted, AI tournament)
- World mode segmentation is not yet specified

**Recommendation**: Add world.toml config `player_type_policy`: `"mixed"` (default), `"human_only"`, `"ai_only"`. This gives server operators explicit control over population composition without changing game mechanics.

---

## Summary

| Category | Count |
|----------|-------|
| G1 (Critical) | 2 |
| G2 (Significant) | 3 |
| G3 (Moderate) | 5 |
| G4 (Minor) | 4 |
| Missing | 8 |

The design's strategic foundation is strong. The deferred command model, seeded shuffle, human-AI parity through WASM, and layered visibility system are all correct design choices. The concerns above are refinements, not refutations — most are about edge cases, long-term viability, or missing specifications that implementation will demand. None require architectural redesign.

**Bottom line**: Proceed to Phase 1 implementation. Address G1 items before World mode launch. Address G2 items during Phase 2-3. G3/G4 can be resolved incrementally.
