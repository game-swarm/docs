# Swarm R22 Game Design Review — rev-dsv4-designer

**Reviewer**: Game Designer (DeepSeek V4 Pro)
**Date**: 2026-06-18
**Scope**: Phase 1 Clean-Slate — design-level review, implementation difficulty not considered
**Documents reviewed**: design/README.md, design/gameplay.md, design/modes.md, design/interface.md, specs/reference/api-registry.md, specs/gameplay/06-feedback-loop.md, specs/gameplay/08-api-idl.md, specs/core/09-snapshot-contract.md

---

## Verdict: CONDITIONAL_APPROVE

The core game design is architecturally sound and philosophically coherent. The WASM-only execution model, deferred command architecture, and dual-logistics (Controller + Depot) create a game with genuine strategic depth. However, several mid-severity design gaps in tactical movement, player onboarding transition, and PvE economic integration must be addressed before implementation. The design passes the "strategy space" test — there is no obvious dominant strategy — but the tactical layer needs enrichment.

---

## Strategy Depth Analysis

### Strategy Space Assessment

The game's strategy space spans five orthogonal dimensions:

| Dimension | Variables | Depth |
|-----------|-----------|-------|
| **Body composition** | 8 part types × up to 50 slots × lifespan trade-offs (TOUGH +100 vs ATTACK -80) | High — combinatorial with irreversible commitment |
| **Logistics topology** | Controller (free, RCL-gated) vs Depot (resource-cost, raidable) placement + global↔local transfer timing | High — spatial economic puzzle |
| **Combat tactics** | 6 damage types × 8 special attacks × resistance layering (component + attribute) | High on paper, constrained by 4-direction grid (see G1) |
| **Economic mode** | Faucet/Sink/Transfer/Lockup pipeline with configurable tax, upkeep, and storage policy | High — multi-timescale resource management |
| **Information warfare** | Fog-of-war, snapshot truncation, OverloadPressure visibility model, hint ladder | Medium — well-structured but limited active reconnaissance tools |

**Dominant strategy check**: No single dominant strategy was identified. The interplay between local storage (untaxed, private, vulnerable) and global storage (taxed, semi-public, safe) prevents pure hoarding. Controller aging hard cap (50% of natural growth) prevents "turtling forever" strategies. Empire upkeep O(n²) prevents unchecked expansion. The design successfully creates non-trivial trade-offs at every decision point.

### Information Asymmetry

The fog-of-war + snapshot truncation design is well-calibrated:

- **Critical entity protection** (own drones, Controller, attack targets, entities attacking self) ensures tactical decisions are never made blind
- **Deterministic truncation order** (distance bucket → entity_id lexicographic) guarantees replay consistency
- **NotVisibleOrNotFound** merged error code prevents oracle inference attacks — strong anti-cheat design
- **Hint ladder** (competitive/practice/training) correctly tiers information revelation without leaking hidden state

**Gap**: Active reconnaissance tools are limited to `swarm_get_snapshot` and `host_get_objects_in_range`. There is no "scout drone" mechanic (drone with extended vision but no combat capability), no radar/sensor building, and no information-denial counterplay beyond fog-of-war defaults. The Observer structure (sight_range=10) is the sole vision extension tool. This is adequate for MVP but limits the information warfare dimension.

### PvE + PvP Incentive Structure

**World PvE layer** — well-integrated:
- NPC difficulty by geography (Zone 1→4 gradient) naturally gates content behind expansion
- Resource据点 with Guardian defenders creates "PvE→resource reward" loops that feed back into PvP capability
- World events (Swarm Invasion, Resource Boom) add temporal variety without breaking persistence
- `max_pve_output_per_tick ≤ world_regen × 30%` cap prevents PvE from eclipsing PvP economic value

**Arena PvE Challenge** — cleanly isolated:
- Separate scoring, no World resource leakage
- Deterministic NPC AI ensures replay fairness
- Scenario-based design (Guardian Gauntlet, Swarm Defense, Resource Race, Ruin Siege) covers different strategic skills

**Risk**: The PvE drop economy (NPC → resources + blueprints) creates a parallel advancement path. Players who optimize for PvE farming could accumulate resources without PvP risk, then deploy them in PvP. This is an accepted design trade-off (the 30% cap limits the distortion), but the blueprint drop (5% from Guardian) creates a PvE-exclusive reward category — items unobtainable through PvP. This is acceptable if blueprints offer side-grades rather than strict upgrades, but the current design doesn't specify blueprint power level relative to standard equipment.

### Nash Equilibrium: AI + Humans in Same World

The design achieves a clean equilibrium: all agents (human and AI) produce WASM modules, all WASM modules execute in identical sandboxes with identical fuel metering. There is no asymmetric interface — MCP is a management/monitoring channel, not a gameplay channel.

**Equilibrium properties**:
- **Symmetry**: Same API surface, same CommandAction set, same resource constraints
- **No side-channel advantage**: AI cannot execute more commands/tick, has no faster reaction time (tick-bound), and must pay same deploy costs
- **Information parity**: AI sees same fog-of-war-filtered snapshot as human player's WASM
- **Meta-stability**: AI may have advantage in code-generation speed (iterate faster), but this is offset by human strategic intuition. The equilibrium is not perfectly symmetric but is sufficiently balanced — the asymmetry (AI iterates faster, human intuits better) creates interesting dynamics rather than a "solved" outcome.

---

## Findings

### Strengths

1. **Deferred command model as fairness foundation**: All agents output `tick(snapshot) → Command[]` through identical WASM sandboxes. No privileged execution path. This is the single most important design decision and it is correct.

2. **Body part lifespan trade-off system**: The interaction between body parts (TOUGH +100 lifespan, ATTACK -80) × age mechanics × Controller repair creates a genuine "build vs longevity" tension. A 50-ATTACK drone hits hard but dies fast; a 10-TOUGH 5-HEAL drone is nearly immortal but does nothing. The Recycle 50% refund provides a respec path without making it free.

3. **Controller + Depot dual logistics**: The distinction between Controller (free repair, territorial claim, RCL-gated capacity, one-per-room) and Depot (resource-cost repair, no claim, unlimited placement, raidable) creates rich strategic geography. Players must decide: "Do I push a Depot forward to support an offensive, knowing it can be captured and used against me?"

4. **Soft-launch + First-Attack Shield**: The three-phase PvP transition (safe_mode → soft_launch PvE-only → First-Attack Shield → Soft PvP → Full PvP) is the best new-player protection design I've seen in a persistent-world game. The First-Attack Shield's per-attacker scope (immune to the attacker who triggered it, vulnerable to others) creates a nuanced "you get one warning shot" dynamic.

5. **Anti-snowball contract**: Progressive storage tax (0/1/5/20 bp tiers), O(n²) empire upkeep, controller aging hard cap, room drone cap (50→500), and global entity cap (50,000) together create natural convergence without feeling punitive. Notably, the design explicitly acknowledges World mode is NOT competitively fair — this honesty about asymmetry is correct.

6. **Geography as content**: PvE difficulty increases with distance from world center. No "dungeon finder" queue, no instanced content. Players encounter stronger PvE naturally by expanding. This preserves the persistent-world integrity.

7. **Snapshot truncation contract**: The deterministic truncation algorithm (distance bucket → entity_id lexicographic, remove from farthest) with critical entity protection is a robust solution to the "too much world state" problem. The `tick_integrity = "degraded"` flag for competitive mode is a thoughtful touch.

### Concerns

#### G1: 4-Direction Movement Constrains Tactical Depth — MEDIUM

The decision to limit movement to 4 cardinal directions (NESW) with 8-direction listed as "Future RFC" significantly reduces tactical positioning depth. In a game where:
- Melee range is 1 cell
- Ranged range is 3 cells
- Tower range is 5 cells
- Position determines combat outcomes

...being unable to move diagonally means:
- Approaching a diagonal target takes 2 moves instead of 1 (e.g., from (0,0) to (1,1) requires N→E or E→N)
- Defensive formations (walls, chokepoints) behave differently on a 4-direction vs 8-direction grid
- Kiting (hit-and-run tactics) is less dynamic — the escape vector set is smaller

**Recommendation**: Promote 8-direction movement to core MVP. The implementation cost is marginal (Direction4 → Direction8 enum, pathfinding already supports arbitrary graphs). The tactical depth gain is substantial. If 8-direction is truly deferred, the design should at minimum explain the trade-off: what design problem does 4-direction solve?

#### G2: Body Part Irreversibility Punishes Experimentation — MEDIUM

"body 不可逆: 一旦 spawn，body part 组成不可更改" — this is a high-stakes commitment. The Recycle mechanic (50% refund in standard worlds) provides an escape hatch, but:

- A new player who builds a suboptimal body (e.g., all MOVE, no WORK) is stuck with a useless drone until they can afford to Recycle and respawn
- The 50% penalty means experimentation costs real resources — this incentivizes "copy the meta build" behavior rather than creative exploration
- The Tutorial world's 100% refund for 500 ticks is a good band-aid, but the transition to 50% is abrupt

**Recommendation**: Consider a "respec window" — first N ticks after spawning, Recycle at 90%+ refund, decreasing to 50% over time. Alternatively, allow body part swapping at a Controller (with cost and cooldown) rather than full destruction + respawn. This preserves the strategic weight of body composition while reducing the punishment for honest mistakes.

#### G3: Special Attack Novice-Disable Creates Jarring Transition — MEDIUM

The progressive unlock system disables ALL 8 special attacks in Tutorial and Novice worlds, then enables ALL 8 in Standard. This means:

- Players learn the game without Hack/Drain/Overload/Debilitate/Disrupt/Fortify/Leech/Fabricate
- Upon entering a Standard world, they face 8 new combat mechanics simultaneously
- There is no intermediate tier where a subset of special attacks is introduced gradually

The current Novice world is essentially "Standard minus special attacks" rather than a scaffolded learning environment.

**Recommendation**: Introduce special attacks in waves at the Novice tier:
- Novice Phase 1 (first N ticks): Disrupt + Fortify only (defensive/utility, easy to understand)
- Novice Phase 2: +Debilitate + Drain (offensive but non-lethal)
- Standard: Full set including Hack/Overload/Leech/Fabricate

Or, alternatively, tie special attack unlock to GCL/RCL progression within a single world, giving players organic exposure.

#### G4: PvE Drop Economy May Create Distortion — MEDIUM

The PvE drop system includes blueprints (5% from Guardian) as PvE-exclusive rewards. While the 30% global cap on PvE output relative to world regeneration prevents PvE from dominating the economy, it doesn't address:

- **Blueprint power level**: If blueprints unlock strictly better body parts or structures (vs side-grades), PvE becomes mandatory for competitive parity
- **Farming concentration**: A few players cornering Guardian spawn points (Zone 3-4) could monopolize blueprint supply
- **Drop rate transparency**: 5% is low enough to feel unfair (some players get lucky, others don't) but high enough to be farmable

**Recommendation**: 
1. Clarify blueprint design philosophy: side-grades (different, not better) or progression (strict upgrades)?
2. Consider bad luck protection: guaranteed blueprint after N Guardian kills without drop
3. Add a PvP path to acquire blueprints (market, looting, or reverse-engineering captured drones)

#### G5: Arena PvE Challenge `par_time` Undefined — LOW

The PvE Challenge scoring formula references `par_time`:
```
efficiency = min(1.0, par_time / actual_time)
```

But the document never defines how `par_time` is determined. Is it:
- A designer-set target (static per scenario)?
- A dynamic percentile of community performance (e.g., top 10% median)?
- A theoretical minimum computed from map layout?

Without this definition, the scoring system is incomplete. If `par_time` is dynamic (community-driven), the scoring formula creates a moving target that can be gamed (sandbagging to lower `par_time`, then optimizing).

**Recommendation**: Define `par_time` as a static designer-set value per scenario, adjusted manually on scenario balance patches. This makes scores comparable across time periods and prevents gaming.

#### G6: No Drone-to-Drone Communication — LOW

The design currently has no mechanism for drones to communicate within a player's swarm. `SendMessage` is marked as "Future RFC." This means:

- Swarm tactics (flanking, focused fire, coordinated retreat) must be implemented through shared state in WASM memory, which requires all drones to use the same module
- Multi-module strategies (different WASM for different drone roles) cannot coordinate without polling global state
- This pushes players toward monolithic WASM modules rather than specialized role-based modules

**Recommendation**: For MVP, implement a minimal intra-player message system: each drone can publish a short message (≤256 bytes) visible to all other drones owned by the same player in the same or adjacent rooms. This enables basic coordination without requiring complex routing.

#### G7: Late-Game Resource Sink Gap — LOW

The economic model has strong sinks for early/mid game (spawn costs, build costs, upkeep) but limited sinks for late-game resource accumulation:

- Once all 8 RCL rooms are built, construction spending drops
- Empire upkeep caps at O(n²) but stops growing when expansion stops
- Storage tax only affects global storage — local storage has no tax
- No "prestige" or "wonder" mechanics that consume massive resources for non-territorial advancement

This could lead to resource inflation in mature worlds where established players accumulate resources with nothing to spend them on, potentially distorting the economy for new players.

**Recommendation**: Consider a "Grand Project" system — expensive, long-duration constructions that provide server-wide benefits (e.g., faster resource regeneration for all players in region, shared vision radius increase). This creates a communal resource sink that established players can contribute to without directly harming new players.

---

## CrossCheck

Items I suspect are problematic but fall outside the Game Designer direction:

- **CX1**: The API registry lists `swarm_deploy` as an MCP tool with `deploy_mutation` replay class. Architect should verify that the deploy_mutation flow (async object store upload → FDB manifest commit → next-tick activation) is correctly sequenced to prevent race conditions where a drone executes with a partially-deployed module. → **Architect**

- **CX2**: Snapshot truncation at 256KB per player — Architect should verify this is sufficient for the maximum case (500 drones per player with OverloadPressure components, visible entities, terrain data). The truncation algorithm is logically sound, but the 256KB constant may need validation against actual data models. → **Architect**

- **CX3**: The Anti-Snowball O(n²) upkeep formula combined with the "no competitive fairness in World mode" philosophy — Security reviewer should verify that the "too big to fail" scenario (an empire so large that only coordinated multi-player assault could challenge it) doesn't create a de facto unassailable position that drives new players away. → **Security**

- **CX4**: MCP tools include `swarm_simulate` at 50/tick rate limit. Architect should verify that simulate fork isolation (independent RNG namespace, no ordinal consumption, discarded state) is correctly implemented to prevent side-channel leakage between simulate calls and authoritative ticks. → **Architect**

- **CX5**: The `NotVisibleOrNotFound` merged error code is a strong anti-oracle design, but the `fix_hint` in practice mode ("目标可能不在视野或已被摧毁") partially defeats it by confirming the entity once existed. Security should review whether practice-mode hints create oracle vectors. → **Security**
