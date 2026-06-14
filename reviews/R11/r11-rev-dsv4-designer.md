# R11 Game Designer Review — rev-dsv4-designer

**Reviewer**: DeepSeek V4 Pro (Game Designer)
**Date**: 2026-06-14
**Documents reviewed**: DESIGN.md (full, 1463 lines), tech-choices.md, P0-1 through P0-9 (all P0 specs)

---

## VERDICT

**APPROVE_WITH_RESERVATIONS**

The design has evolved significantly since R10. The damage type system (6 types + resistance matrix), special attack framework (7 distinct attacks), body part extension system, and three-tier logistics model add substantial strategic breadth. The MCP `swarm_simulate` tool is a powerful addition that closes the AI's "what-if" loop. The rule module system with `mod.toml` i18n support shows mature platform thinking.

However, three high-severity game design concerns remain from R10 (G1-expand-or-die, G5-Arena fog, G7-cooperation vacuum), and four new concerns emerged from the expanded special attack and damage type systems. The strategy space has grown wider but also more combinatorially opaque — players face a crowded decision space without sufficient information scaffolding. 10 concerns total.

---

## STRENGTHS

1. **Deferred Command Model with Anti-Amplification Refund** — P0-2 §7.2's deploy-reset rule (refund credit tied to module_hash, voided on redeploy) closes a subtle exploit: farming refunds with v1 then spending with v2. This level of anti-gaming forethought is World of Warcraft auction-house-level game design maturity.

2. **Damage Type + Resistance Matrix Creates True Strategic Depth** — Six base damage types × body part resistances × attribute resistances × Rhai mod extensions. This is not cosmetic — it forces players to read opponent body composition and adapt. The multiplicative stacking (body_res × attribute_res) creates clean math for competitive play.

3. **Special Attack Framework** — Hack (mind control), Drain (resource theft), Overload (CPU sabotage), Debilitate (vulnerability), Disrupt (interrupt), Fortify (shield). These are not simple "+damage" variants — each creates a distinct tactical role. Disrupt as a reaction to interrupt Drain/Hack is a particularly good counter-play loop.

4. **Three Logistics Modes with Explicit Trade-offs** — No-logistics (Arena-friendly), Light logistics (default — 1% tax on global, 5% on local build), Hardcore logistics (Factorio-style). The 5% asymmetry (1% vs 5% transfer cost) creates a natural local-storage bias that aligns with the stealth-advantage mechanic.

5. **Body Part Extension System** — `[[body_part_types]]` in world.toml + Rhai mod registration of new parts (Leech, Scramble, Fabricate). This transforms Swarm from a fixed-unit game into a "design your own unit" game — the strategic combinatorial space is enormous.

6. **Progressive Global Storage Tax Architecture** — Four-tier progressive tax (0%/0.01%/0.05%/0.20%) with three explicit anti-monopoly mechanisms: tax, stealth, transport time. The design explicitly names and counters economic snowball — rare in multiplayer game design docs.

7. **MCP as Peer Interface — Consistently Enforced** — P0-3 §4.5's blacklist of "things MCP never does" and P0-9's Source Gate enforcing `MCP_Deploy → reject 403` for gameplay commands form a watertight contract. AI agents cannot game the system by calling MCP tools as gameplay shortcuts.

8. **Code Propagation Speed Creates Asymmetric Update Dynamics** — When `propagation_speed > 0`, code updates ripple outward from Spawn/Controller. This creates a spatial deployment puzzle: attack with new code at the frontier before defenders receive the update? The propagation source choice (Spawn vs Controller vs AnyDrone) adds another strategic dimension.

---

## CONCERNS

### Strategy Space & Dominant Strategy

**G1 — SEVERITY: HIGH** (R10 Carryover)
**Drone Lifespan + Controller Reset Creates Binary "Expand or Die" Pressure**

The 1500-tick drone lifespan combined with Controller-capture age reset creates a hard constraint: any player not actively expanding loses their entire drone fleet within 75 minutes. The reset cooldown (500 ticks, single-player) prevents ping-pong abuse, but the fundamental issue remains:

- Defensive/turtle archetypes are non-viable in standard rules
- Losing one Controller battle → cascading age-out → unrecoverable
- The optimal strategy converges to "constant expansion" — a narrow band
- This interacts badly with `spawn_policy = RandomRoom`: unlucky spawn next to a level-8 empire → player's drones die of old age before they can capture any Controller

The drone_lifespan mechanism is clever as an anti-turtle device, but it currently has only one reset trigger (Controller capture). This creates a single strategic imperative rather than a menu of options.

*Recommendation*: Add alternative lifespan refresh sources configurable via world.toml:
- `lifespan_refresh_on_gcl_milestone`: reset on reaching a GCL threshold
- `lifespan_refresh_resource_cost`: consume rare resource to reset (e.g., `{Energy: 10000}`)
- `lifespan_refresh_cooldown_per_player`: global cooldown across all trigger types (default: same as existing 500-tick cooldown)
- `lifespan_reset_on_room_defense`: holding a room against attack for N ticks refreshes drones in that room

This preserves the anti-turtle function while giving players multiple strategic paths to survival.

**G2 — SEVERITY: HIGH** (NEW)
**Damage Type System Has 6×N Combinatorial Complexity — No Information Scaffolding**

The damage type system (§8.2, 战斗与PvP) defines 6 base types with body-part-level and attribute-level resistances. For a player encountering an enemy drone:

```
Effective Damage = BaseDamage × body_resistance[type] × attribute_resistance[type] × damage_multiplier
```

The player must know: (1) which damage type their weapon uses, (2) the target's body composition, (3) the target's attribute flags (set dynamically by Rhai mods). But P0-5 §2.4 reveals body parts are visible but attribute flags are NOT:

| Data | Default Visibility |
|------|-------------------|
| Body part composition | ✅ Visible |
| Attribute flags (Shielded, Flaming, etc.) | ❌ Hidden |
| Current fatigue | ❌ Hidden |
| Cooldown remaining | ❌ Hidden |

This means a player attacking with EMP damage cannot know if the target has `Shielded` (all damage × 0.7) or `immune_EMP` (EMP × 0) — they can see body parts but not attribute flags. The fog-of-war creates a "guess the multiplier" game that feels unfair rather than strategic.

*Recommendation*: 
- `attribute_resistance[type]` should produce a visible effect on the entity (e.g., "Shielded" drone has a visible shield aura in Web UI / MCP snapshot with `"status_effects": ["Shielded"]` field). Not the exact multiplier, but the fact that an effect is active.
- Add `swarm_inspect_entity_detail` MCP tool (cost: 5 fuel per call, not per tick) that returns full entity stats including active attribute flags. This mirrors the human's ability to click a unit and see buffs/debuffs.
- Document which attributes are "observable" vs "hidden" in DESIGN.md §8.2.

**G3 — SEVERITY: MEDIUM** (NEW)
**Special Attack Overload Targets AI Players Disproportionately**

The Overload special attack (§8.2, 特殊攻击方式) reduces target fuel budget by 500k (5% of MAX_FUEL=10M). For human players whose code is compute-light, this is a minor inconvenience. For AI players using LLM-generated WASM that operates near the fuel cap, a 5% reduction can cascade into: fewer host function calls → less information → worse decisions → more failed commands.

This creates a perverse incentive: attack AI players with Overload specifically to degrade their decision quality. Since AI players and human players share the same world (DESIGN.md §1.1), this is an asymmetry: Overload is a soft "stupidity debuff" against AI, nearly cosmetic against humans with efficient code.

*Recommendation*:
- Overload should reduce MAX_COMMANDS_PER_PLAYER (100 → 90) or increase command validation strictness, not reduce fuel. This affects all players symmetrically.
- Alternatively, add an `overload_resistance` stat that scales with code efficiency: players using <50% of their fuel budget naturally resist Overload effects at 2×. This makes efficient code a defense, not a vulnerability.
- Add to P0-8 IDL: Overload command should specify `target_fuel_reduction` as a percentage of *target's actual fuel usage*, not the absolute cap. An idle player at 10% fuel usage loses only 50k (= 5% × 10% × 10M), while a maxed-out player loses 500k.

**G4 — SEVERITY: LOW** (NEW)
**Debilitate + Fortify Creates an "Arms Race" Micro-Meta Without Depth**

Debilitate (×2 damage received for 50 ticks, 150-tick cooldown) and Fortify (×0.5 damage received for 100 ticks, 300-tick cooldown) are mirror effects. The optimal response to an enemy using Debilitate on your drone is to Fortify that drone — but Fortify has a 300-tick cooldown vs Debilitate's 150. Over time, Debilitate outpaces Fortify 2:1.

The equilibrium: always Debilitate the enemy's highest-value drone; always Fortify your own highest-value drone; whoever runs out of Fortify cooldowns first loses. This is deterministic and lacks counter-play beyond the body-part-count arms race.

*Recommendation*: Make Debilitate and Fortify *interact* mechanically:
- Fortify on a Debilitated target cleanses the Debilitate and normalizes damage (no bonus, no penalty). The Fortify cooldown is reduced to 100 ticks when used as a cleanse.
- Debilitate on a Fortified target breaks the Fortify but applies only ×1.3 damage (not ×2). The Debilitate cooldown is halved when breaking Fortify.
- This creates a clean "cleanse" dynamic: Fortify isn't just a shield, it's a reaction tool. Debilitate isn't just a debuff, it's a shield-breaker. The cooldown asymmetry becomes a timing game, not an inevitability.

### Information Asymmetry Design

**G5 — SEVERITY: HIGH** (R10 Carryover, Partially Addressed)
**Arena Mode Disables Fog of War — Contradicts Special Attack Design**

P0-7 §6 specifies Arena `fog_of_war = false`. P0-5 §7 confirms "双方玩家看到整个竞技场". But the special attack system (Hack, Drain, Overload, Disrupt) depends on range limitations and fog-of-war for tactical depth:

- With full visibility, Hack's range limit is trivially bypassed — the defender sees the attacker approaching from across the map and repositions
- Drain requires proximity to structures — with full visibility, defenders pre-position at all vulnerable points
- Disrupt's role as "stop the Hack/Drain" becomes an open-information timing game rather than a reaction to discovered threats

Arena without fog-of-war eliminates the tactical layer these special attacks were designed around. The game reduces to a resource optimization puzzle — closer to an auction than a strategy game.

The R10 concern (G5) was raised and the two-layer visibility model (P0-5 §3.5) partially addresses the spectator experience — but Arena gameplay itself still disables fog. The design has the machinery to fix this (drone snapshot vs player camera separation) but Arena defaults don't use it.

*Recommendation*: Arena should default to `fog_of_war = true` for drone snapshots. Spectators get `player_view = "full"` via `spectate_delay ≥ 100` ticks (already designed in P0-5 §3.5). The two-layer model is the correct architecture — use it for Arena gameplay, not just spectating.

**G6 — SEVERITY: MEDIUM** (R10 Carryover, Intensified)
**`swarm_simulate` + `swarm_dry_run_commands` Creates AI Oracle Advantage**

P0-3 §4.4 adds `swarm_simulate` (5/tick World, 3/tick Arena) and P0-6 §3.1 adds `swarm_dry_run_commands`. Together, an AI agent can:

1. Get snapshot → generate strategy → `swarm_dry_run_commands` to test → if rejected, try alternative
2. `swarm_simulate` forward N ticks with candidate strategies → pick best
3. Deploy optimized code → observe results → iterate

A human player has:
1. Mental simulation
2. Local `swarm sim` (P1, Phase 3 — not available in MVP)
3. Trial-and-error across real ticks (costly)

The asymmetry is not about computation (fuel metering handles that) — it's about *information access*. The MCP simulate/dry-run tools are "free" queries that the human Web UI doesn't expose equivalently. P0-6 §3.3 mentions local `swarm sim` but as a Phase 3 feature. MVP (Phase 1-2) gives AI a planning tool humans lack.

*Recommendation*:
- Add `swarm_dry_run` as a Web UI button in Phase 2 MVP (not Phase 3). The human clicks "Test commands" in the editor and sees which would succeed/fail before committing.
- Restrict `swarm_simulate` to a per-code-version budget (e.g., 100 total simulations, reset on module redeploy). This prevents simulation-spam-as-strategy.
- Document the "planning symmetry principle": any tool available to AI via MCP should have a human-facing equivalent in Web UI or CLI within one phase of the AI tool's introduction.

### PvE + PvP Incentive Structures

**G7 — SEVERITY: HIGH** (R10 Carryover)
**No Core Cooperation Mechanics — World Mode is a Prisoner's Dilemma**

Between any two players in World mode, the payoff matrix is:

```
           Cooperate    Defect
Cooperate  (3, 3)      (1, 5)
Defect     (5, 1)      (2, 2)
```

Defection (attacking/stealing resources) dominates cooperation — a player who cooperates expends resources helping another who may later attack them. With no built-in alliance mechanics, shared vision, resource tribute, or mutual defense pacts, the Nash equilibrium is universal defection.

The "alliance-system" is mentioned as a potential mod (§8.7, mod market mockup) but:
- It's not part of core mechanics
- It's not defined in any P0 spec
- It's deferred to modders who may never build it

This means World mode's "人类和AI agent在同一世界共存" (DESIGN.md §10) will default to a hostile free-for-all. New players and AI agents alike face an established-player gank-fest with no cooperative counterweight.

*Recommendation*: Add to core design (not mod-only):
1. `alliance.invite` / `alliance.accept` / `alliance.leave` — MCP tools + REST endpoints
2. `shared_vision` rule: allied players' drone vision is aggregated into each member's snapshot (already partially designed as `player_view = "allied"` in P0-5 §3.5)
3. `resource_tribute` command: voluntary resource transfer between players (0% tax, instant — incentivizes cooperation over market trading)
4. World event hooks in Rhai: `on_player_alliance_formed`, `on_player_alliance_broken` for mod-driven alliance mechanics

Minimum viable: items 1-2 in Phase 2. Full alliance system in Phase 3.

**G8 — SEVERITY: MEDIUM** (NEW)
**World Mode Has No Territory Pressure Release Valve**

In World mode, players join at different times and establish permanent territories. Once a room is claimed (Controller captured), the only way to lose it is:
- Enemy captures the Controller (PvP)
- Downgrade timer expires (5000 ticks without owner)
- Voluntary abandonment (not designed)

There is no environmental pressure to vacate or lose territory. Established players can hold rooms indefinitely with minimal investment. This creates:
- "Dead rooms" — claimed but unused, blocking new players
- Territory inflation — total claimed rooms grows monotonically
- Late-joiner disadvantage compounds over time

The empire-upkeep mod (DESIGN.md §8.7) provides economic pressure, but it's optional and not in default World mode.

*Recommendation*: Add to core World mode (configurable on/off, default on):
- `controller_decay_rate`: Controller level decays by 1 per N ticks if the room has zero drone activity for M ticks. Default: N=1000, M=100.
- `inactive_room_release`: rooms with no drone visits for 5000 ticks become neutral (Controller becomes unowned, structures persist but degrade).
- These create a natural territory churn that prevents map ossification.

### Nash Equilibrium & AI-Human Coexistence

**G9 — SEVERITY: MEDIUM** (R10 Carryover, Refined)
**AI-Human Mixed Equilibrium: Specialization Gap Widens**

With the expanded special attack and damage type systems, the AI-human specialization gap has widened:

| Layer | AI Advantage | Human Advantage |
|-------|-------------|-----------------|
| Build order optimization | ✅ Pre-compute optimal sequences | ❌ Intuition only |
| Damage type counter-picking | ✅ Programmatic analysis of visible body parts | ✅ Pattern recognition |
| Special attack timing | ❌ Requires opponent modeling | ✅ Psychological prediction |
| Resource logistics | ✅ Perfect optimization | ❌ Rough estimation |
| Strategic deception | ❌ Predictable patterns | ✅ Creative feints |
| Multi-room coordination | ✅ Parallel optimization | ❌ Mental bandwidth limit |

The equilibrium: AI dominates optimization layers (build order, resource routing, damage type matching); humans dominate strategic layers (feints, timing attacks, reading opponent intent). This is not inherently bad — it creates complementary niches. But:

1. The design doesn't acknowledge this split
2. There's no mechanism for humans to compete in optimization or AI to compete in deception
3. The "best player" in a mixed world may always be a human+AI pair (one providing strategy, one providing optimization) — which defaults to AI players running LLM-generated code guided by a human's strategic direction

*Recommendation*: 
- Add `strategy_indicators` in the leaderboard public data: "Player X is focusing on [Expansion / Defense / Economy / Aggression]" derived from observable metrics (drone composition ratios, building patterns, resource flow direction). This gives humans a strategic-level read without requiring programmatic analysis.
- Add a `deception_score` metric (internal): how well does a player's observed behavior deviate from their historical pattern? This has no gameplay impact but can be used for community analysis.
- Document the intended AI-human coexistence model explicitly in DESIGN.md §1.1: "Swarm 中 AI 和人类是互补的存在——AI 擅长优化，人类擅长策略。两者在同一世界中的互动产生的涌现玩法是 Swarm 最独特的价值。"

**G10 — SEVERITY: LOW** (R10 Carryover)
**Late-Joiner Spawn Distance Not Configurable**

The `spawn_policy` supports RandomRoom, ManualSelect, FixedSpawn, and Inherit (§8.2). But there's no `spawn_distance_min` or `new_player_protection_ticks` to prevent new players from spawning adjacent to max-level empires.

The existing Controller safe_mode mechanic (§3.1, `safe_mode: u32`) is a per-player cooldown ability, not an automatic new-player protection. A new player who doesn't know to activate safe mode within their first tick can lose their only Spawn before they deploy code.

*Recommendation*: Add to spawn config:
- `new_player_safe_mode_ticks`: u32, default 100. Automatic safe mode on first Controller for N ticks after joining.
- `spawn_distance_min_from_player`: u32, default 0. Minimum room distance from any existing player's closest Controller. Prevents spawn-camping.
- `new_player_resource_stipend`: ResourceCost, default `{Energy: 2000}`. One-time resource grant on first join. Scales the initial condition to the world's average wealth.

---

## MISSING

The following game design elements are absent or underspecified:

1. **Cooperation framework** (R10 carryover) — Alliance formation, shared vision, resource tribute, mutual defense. The "alliance-system" mod is mentioned but not designed. Essential for World mode PvE+PvP coexistence.

2. **PvE content hooks** — No world events, environmental threats, or shared objectives. The Rhai `on_world_event` hook doesn't exist. A game engine without PvE can only run zero-sum PvP — limiting World mode appeal.

3. **Territory pressure mechanics** — No environmental decay, no inactive room release, no map churn. World mode territory is permanent unless actively conquered.

4. **Scout/reconnaissance specialization** (R10 carryover) — All drones have identical vision range (3). No body part for intelligence-gathering. Vision is "free" — all drones are scouts.

5. **Arena spectator UX design** — P0-5 §3.5 specifies the technical architecture (two-layer visibility, spectate_delay) but not the spectator experience: what does the viewer see? Fog-of-war toggle? Map overlay with both players' actual views? Commentary hooks?

6. **Ranking/league meta-structure** — Arena mode is defined at the engine level (P0-6 §6) but the ranking algorithm, league splitting (Human/WASM, AI-assisted, AI tournament), and season structure are deferred to Phase 7. The leaderboard metrics affect game design — players optimize what they're ranked on.

7. **Body part extension IDL** — DESIGN.md §8.2 mentions `[[body_part_types]]` and Rhai mods introducing new parts, but there's no P0 spec for the body part extension interface. What fields does a new body part need? Damage type binding? Vision range? Special attack association? Cost?

8. **Observable status effects** — The damage/resistance system creates hidden attribute flags that dramatically affect combat (×0 to ×2 multipliers) but players can only see body parts, not attributes. There's no "entity status effects" field in the snapshot or MCP query results.

---

## STRATEGY DEPTH ANALYSIS

### Strategy Space Cardinality

Per tick, a player's decision space is the product of:

- **Drone count**: 1-500 (capped by world.toml)
- **Body configurations**: 8 base parts, max 50 total → combinatorial explosion. A 10-part drone has C(10,8) with repetition = very large
- **Actions per drone**: 5-15 valid choices per tick (move/harvest/attack/special/transfer/build)
- **Target selection**: per drone, 0-N visible targets in range (0-37 tiles for vision-3 hex)
- **Resource allocation**: which resources to spend (dynamic, per-world resource types)
- **Special attack timing**: cooldown management across 7 special attacks

Conservative lower bound: with 10 drones each having 5 valid actions:
```
10^5 × target_combinations × resource_decisions → ~10^8 to 10^12 per tick
```

However, effective strategy space is constrained by:
- Drone body irreversibility (role commitment)
- Resource budgets (can't execute all actions)
- Fog-of-war (can't see all targets)
- Turn order uncertainty (can't perfectly sequence)
- Drone lifespan (long-term commitment to strategy)
- Code propagation delay (asynchronous update windows)

**Effective strategic depth: VERY HIGH** — comparable to StarCraft micro + Civilization macro + Factorio logistics, with Pokemon type-matchups layered on top.

### Dominant Strategy Risk Assessment

| Strategy | Viability | Hard Counter | Soft Counter | Risk |
|----------|-----------|-------------|-------------|------|
| Harvester spam | Early-game viable | Drone cap, empire upkeep, SourceEmpty contention | Resource depletion | LOW |
| Turtle + tech | Non-viable (G1) | Drone lifespan forces expansion | None available | **HIGH** |
| Zerg rush | Viable | Tower defense, Fortify, defender advantage | Pre-positioning | LOW-MEDIUM |
| Economic snowball | Viable | Progressive tax, Hack, Drain | Local storage stealth | LOW |
| Hack domination | Viable (G2, R10) | Psionic resistance, Disrupt interrupt | Spread drones | MEDIUM |
| Overload harassment | AI-disproportionate (G3) | None for AI players | Efficient code for humans | **HIGH** (vs AI) |
| Damage-type rock-paper-scissors | Viable | Hidden attribute flags (G2) | Body part visibility | MEDIUM |
| Scout + snipe | Non-viable | All drones have vision 3 — no scout specialization | None | N/A (gap) |

### World Mode PvE+PvP Nash Equilibrium (Revised for R11)

With default rules (no alliance system, no PvE events):

1. **Early game** (0-500 ticks): Exploration + initial spawn. Players spread to avoid competition. Optimal: claim a room with 2+ energy sources.
2. **Mid game** (500-2000 ticks): Territorial consolidation. Players encounter borders. First conflicts over contested rooms. Optimal: expand while maintaining drone count below upkeep threshold.
3. **Late game** (2000+ ticks): Established empires. Three stable strategies emerge:
   - **Expansionist**: Continuous room capture to reset drone lifespan. High risk, high reward.
   - **Raider**: Hack/Drain/Overload harassment of neighbors. Medium risk, sustains without expansion.
   - **Economic**: Optimize within existing territory. Low risk, slow growth — vulnerable to Expansionist neighbors.

4. **Equilibrium outcome**: Expansionist → captures Raider's unprotected rooms → Raider has no counter-expansion territory → Raider becomes Economic or dies → Economic gets absorbed by Expansionist. **The equilibrium converges to Expansionist dominance** because drone lifespan creates forced expansion and there's no defensive advantage sufficient to offset this pressure.

5. **With AI players**: AI Expansionists optimize build orders → AI Raiders optimize Hack timing → Human players cluster in Economic strategy → human Economies survive only if hidden behind AI buffer empires. Without cooperation mechanics, the equilibrium is "become Expansionist or be eliminated by one."

### Information Asymmetry Effectiveness

| Game Phase | Hidden Information | Strategic Value |
|-----------|-------------------|-----------------|
| Early (1-10 drones) | Enemy positions, resource locations | HIGH — scouting matters |
| Mid (10-50 drones) | Enemy Controller progress, resource reserves | MEDIUM — partial fog coverage |
| Late (50+ drones) | Resource reserves, fatigue/cooldowns, code version | LOW-MEDIUM — intra-territory fog is gone (G4, R10) |

Primary remaining information games in late-game:
- **Resource poker**: enemy doesn't know your reserves → bluff strength/weakness
- **Code deception**: enemy doesn't know your strategy → surprise attack patterns
- **Cooldown tracking**: can you predict when the enemy's Fortify is off cooldown?

These hidden variables create meaningful strategic depth even with near-full positional visibility. The game transitions from "where is the enemy" (early) to "what is the enemy thinking" (late) — a good progression arc.

---

## SUMMARY

```
Verdict: APPROVE_WITH_RESERVATIONS

NEW blocking issues (must fix before Phase 2):
  G2  [HIGH]  Damage type system lacks observable status effects — players guessing multipliers
  G3  [HIGH]  Overload disproportionately debuffs AI players

R10 blocking issues still unresolved:
  G1  [HIGH]  Drone lifespan forces binary expand-or-die strategy
  G5  [HIGH]  Arena disables fog-of-war, contradicts special attack design
  G7  [HIGH]  No core cooperation mechanics — World mode is hostile free-for-all

High-priority issues (should fix before Phase 3):
  G4  [LOW→MED]  Debilitate/Fortify arms race without counterplay dynamics
  G6  [MED]      swarm_simulate creates AI oracle advantage in MVP
  G8  [MED]      No territory pressure release valve in World mode
  G9  [MED]      AI-human specialization gap widens with expanded combat system

Low-priority issues (can defer):
  G10 [LOW]      Late-joiner protection not configurable
```

---

*Reviewer signature: rev-dsv4-designer (DeepSeek V4 Pro, Game Designer direction)*
