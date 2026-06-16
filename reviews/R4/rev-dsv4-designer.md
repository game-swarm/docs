# Swarm R4 — Game Designer Review

**Reviewer**: rev-dsv4-designer (Game Designer)
**Date**: 2026-06-16
**Documents reviewed**: DESIGN.md, tech-choices.md, ROADMAP.md, specs/01-09

---

## Verdict: CONDITIONAL_APPROVE

The design is architecturally exceptional — fairness baked into the engine via fuel metering, seeded shuffle, and identical sandbox paths for humans and AI. The World Rules Engine is a genuinely extensible platform. Five concerns require attention before full approval; none are blockers at the architectural level, but all affect game feel, strategy depth, and player retention.

---

## Strengths

### S1. Fairness-by-Architecture (Exceptional)

The combination of WASM fuel metering (instruction counting, not wall-clock), seeded shuffle with seed rotation every 10,000 ticks, and identical WASM sandbox for human and AI players is the strongest fairness guarantee I have seen in any programming-game design. C players and Python players get identical CPU budgets measured in actual work done. AI agents and human players walk the exact same path. This is not "fairness as policy" — it is fairness as physics.

### S2. Information Asymmetry as Strategic Layer

The `NotVisibleOrNotFound` opaque rejection code is excellent game design. Attackers cannot distinguish "target doesn't exist" from "target exists but you can't see it." Combined with the two-tier visibility model (drone perception for WASM snapshot vs. player view for MCP/Web), this creates genuine strategic depth around scouting, feints, and information denial. The `spectate_delay ≥ 50` constraint for public spectating prevents real-time information leaks.

### S3. Overload's Three-Results Equivalence Contract

The Overload special attack returns identical results for all three outcomes (successful drain to 500k above floor, partial drain to floor, target already at floor). The attacker cannot use Overload as a spy tool to probe enemy fuel states — only infer from subsequent behavioral changes. This is sophisticated game design that prevents degenerate information-gathering strategies.

### S4. Drone Lifecycle + Repair Design

The age/lifespan system with body-part modifiers (Tough +100 extends life, Attack -80 shortens it) creates genuine trade-offs at spawn time. The Controller + Depot repair system with the 50% hard cap (total age reversal ≤ 50% of natural aging) is a clever anti-snowball mechanism — no amount of infrastructure can make drones immortal. The Depot tactical layer (build forward repair nodes, defend supply lines, raid enemy Depots) creates meaningful spatial strategy.

### S5. Progressive Storage Tax

The anti-monopoly mechanisms (progressive tax above 30% capacity, stealth advantage of local storage, no-teleport logistics with interceptable transport) address a real Screeps failure mode where early accumulators gained insurmountable advantages. The three logistics modes (A: no logistics, B: light logistics, C: hardcore logistics) give server operators meaningful tuning knobs.

### S6. Arena Self-Play Design

Room-based Arena where one player can occupy multiple slots to test algorithms against themselves is elegant. No matchmaking, no ladder, no seasons — just direct algorithm vs. algorithm. The `map_seed` reproducibility ensures fair comparisons. This is the right model for a programming competition platform.

### S7. Special Attack Ecosystem

Eight special attacks (Hack, Drain, Overload, Debilitate, Disrupt, Fortify, Leech, Fabricate) with distinct body part requirements, cooldowns, resource costs, and resistance checks create a rich rock-paper-scissors tactical layer. The tiered unlocking (disabled in Tutorial/Novice, all available at Standard+) is a good onboarding gradient.

### S8. Seeded Shuffle + Seed Rotation

Player order randomization per tick via Blake3 XOF, combined with seed rotation every 10,000 ticks, prevents long-term pattern exploitation while maintaining determinism for replay verification. The "long-term expectation of fairness" model is correct for this genre.

---

## Concerns

### G1 (High): Move-as-Action Constraint Fundamentally Changes Game Feel

**Severity**: High
**Location**: specs/02 §3.4; DESIGN §3.2

The design states: "每 drone 每 tick 最多执行 1 个 main action (Move/Attack/Harvest/Build/Heal 及其特殊攻击变体)." Move is classified as a main action.

This means a drone that moves this tick cannot also harvest, attack, or build in the same tick. The implied harvest cycle for a drone 3 tiles from a source becomes: tick N: move, tick N+1: move, tick N+2: move, tick N+3: harvest. Four ticks to complete one harvest — versus Screeps where movement and action could be quasi-simultaneous (limited by fatigue, not action slots).

This is a defensible design choice — it simplifies the command model and makes the action economy explicit. But it is also a **radical departure from every RTS and programming game** that players will expect. The design documents never explicitly justify this constraint or acknowledge its impact on game feel.

**Recommendation**: Either (a) add an explicit design rationale section explaining why Move competes with other actions in the single-action quota, or (b) consider a model where Move is a "free" command that applies fatigue rather than consuming the action slot. If keeping the current model, the tutorial should explicitly teach this constraint — starter bots will feel sluggish if players don't understand why.

### G2 (Medium): Resource Contention Dynamics Create "Spam Harvesters" Incentive

**Severity**: Medium
**Location**: specs/01 §3.2; specs/02 §7

The seeded shuffle + first-come-first-served resource contention model means players cannot predict whether their harvest command will succeed. The rational response in game theory terms: over-commit harvesters to guarantee resource capture, accepting that some will fail.

The 50% refund on SourceEmpty mitigates but does not eliminate the incentive to over-commit. At scale, the optimal strategy converges to: "send N+M harvesters where N is the minimum needed to deplete the source and M is the expected contention loss." This reduces strategic variety — all players arrive at the same "over-provision harvesters" solution.

The anti-amplification refund timing (refund applies to next tick only, deploy resets refund credit) prevents the worst abuse cases, but the core dynamic remains.

**Recommendation**: Consider a proportional allocation model for resource contention — if two players each send harvest commands to the same partially-depleted source, split the remaining resources proportionally to the number of harvest parts committed (rounded to favor neither party). This eliminates the all-or-nothing lottery while preserving the strategic question of "how many harvesters should I commit."

### G3 (Medium): New Player Onboarding Cliff

**Severity**: Medium
**Location**: specs/06

The learning curve from "tutorial bot collects energy" to "competitive World mode play" involves understanding: deferred command model, body part composition optimization, fatigue mechanics, age/lifespan dynamics, fog-of-war visibility, room control state machine, resource logistics (local vs. global storage), damage type resistance matrix, and 8 special attacks with their counters — **before** the player can write effective code.

The 5-minute tutorial and starter bots are necessary but insufficient. The gap between tutorial outputs and competitive play is not bridged by any intermediate content. The three-tier special attack unlocking (Tutorial/Novice: all disabled, Standard+: all 8 available) creates a sharp cliff — 8 new mechanics appear simultaneously at the Standard tier with no gradual introduction.

**Recommendation**:
- Add an "Intermediate" tier that enables 2-3 special attacks (e.g., Fortify + Disrupt first, then Hack + Drain)
- Add progressive tutorial scenarios that introduce one system at a time: "Tutorial 2: Logistics" (Transfer/Withdraw/Storage), "Tutorial 3: Combat Basics" (Attack/Heal/RangedAttack), "Tutorial 4: Room Control" (Claim/Controller/Build)
- Consider a "guided world" mode where new players start with a complete but suboptimal bot that they improve incrementally (edit one function at a time) rather than writing from scratch

### G4 (Medium): No Explicit Victory Condition in World Mode

**Severity**: Medium
**Location**: DESIGN §9; specs/06 §6

World mode is explicitly designed as a persistent sandbox with no victory condition — "趣味展示（非竞争排名）." This is valid as a design choice (Minecraft servers work this way), but it creates retention risks:

- Players who master the core loop have no defined goal to optimize toward
- Veteran players accumulate territory indefinitely without natural reset pressure
- New players joining a mature world face entrenched empires with no comeback mechanic
- The absence of goals may reduce the appeal for competitive programmers who want measurable outcomes

The progressive storage tax and drone lifespan create soft caps on growth, but these are friction mechanics, not goals.

**Recommendation**: Consider adding optional World-mode objectives that provide direction without forcing competition: "seasonal challenges" (most energy collected in 1000 ticks), "exploration achievements" (first to reach room at world edge), "architectural achievements" (first to reach RCL 8 in a room). These are opt-in, don't reset the world, but give players something to aim for.

### G5 (Low): Hack's Binary Counter-Play Window

**Severity**: Low
**Location**: specs/02 §3.10; DESIGN §8.1

Hack applies a 5-tick gradual control lock (tick 1-2: 50% slow, tick 3-4: immobilized, tick 5: converted to Neutral). Counter-play requires a Disrupt-capable drone (Attack body part, 50 tick cooldown) or Fortify-capable drone (Tough body part, 300 tick cooldown) within range during the 4-tick window.

This creates a binary outcome: either you have the counter in range or you lose the drone. There is no partial mitigation — the target player cannot, for example, "fight the hack" by spending resources or committing the targeted drone to a suicide run.

**Recommendation**: Consider allowing the targeted drone to "resist" by sacrificing its own action for the tick (类似"对抗检定"). If the targeted drone commits its single action to resistance, the hack progression pauses or slows. This creates a meaningful choice: lose the drone's action this tick to buy time, or continue acting and risk conversion.

### G6 (Low): Fabricate Edge Cases Undefined

**Severity**: Low
**Location**: specs/02 §3.15; DESIGN §8.1

Fabricate converts an enemy drone into "己方建筑" (friendly building). The spec does not specify:
- What building type results from the conversion?
- What happens to resources carried by the target drone?
- What if the room is at building cap?
- Can Fabricate target a drone currently being Hacked?

**Recommendation**: Define the conversion result explicitly. Simplest model: the drone becomes a Depot (forward repair node) of the attacker's faction, inheriting 50% of the drone's body part cost as the Depot's energy store. This is thematically consistent (前线据点 from converted enemy units) and mechanically bounded.

### G7 (Low): Leech Zero Cooldown Warrants Balance Testing

**Severity**: Low
**Location**: specs/02 §3.15; DESIGN §8.1

Leech is listed with 0 cooldown and 300 Energy cost per use, dealing 15 Corrosive damage with 50% self-heal. While the per-drone per-tick action quota limits it to one use per tick, the zero cooldown combined with self-healing creates a potential sustain loop: a drone with sufficient energy reserves and Corrosive-vulnerable targets could theoretically fight indefinitely.

This is not necessarily broken — it's gated by energy cost, body part requirements (custom), and target Corrosive resistance. But it deserves explicit balance testing in the MVP phase to confirm the sustain loop doesn't dominate at scale.

**Recommendation**: Flag for balance monitoring during MVP testing. If Leech's sustain proves too strong, add a modest cooldown (10-20 ticks) rather than zero.

---

## Strategy Depth Analysis

### Strategic Dimensions

| Dimension | Depth | Notes |
|-----------|-------|-------|
| **Body Part Composition** | High | 8 base types × up to 50 parts × age_modifier trade-offs × cost optimization. Infinite combinatorial space. |
| **Spatial Strategy** | High | Room control state machine + Depot placement + supply lines + fog-of-war creates multi-layered territory game. |
| **Resource Logistics** | Medium-High | Three logistics modes + local/global storage + transport tax + interceptable convoys. |
| **Tactical Combat** | High | 8 special attacks × 6 damage types × 6 resistance types × body part counters. Rock-paper-scissors with execution constraints. |
| **Information Warfare** | Medium | Fog-of-war + opaque rejection codes + spectate delay + stealth local storage. Good foundation but limited active scouting mechanics. |
| **Economic Strategy** | Medium | Progressive tax + drone lifespan + repair logistics. Soft caps prevent runaway growth but don't create interesting economic puzzles. |
| **Temporal Strategy** | Medium | Per-tick action quota + cooldown management + seed rotation. Creates rhythm but the single-action constraint simplifies temporal optimization. |

### Dominant Strategy Risk Assessment

**Low risk of dominant strategies** in the current design. The key factors preventing degeneracy:

1. **Seeded shuffle** prevents consistent "first mover advantage" exploitation
2. **Body part age modifiers** prevent homogeneous "optimal drone" compositions — combat drones age faster
3. **Progressive storage tax** prevents pure accumulation strategies
4. **Special attack resistance matrix** prevents any single attack type from dominating
5. **Fog-of-war** prevents perfect-information optimal play

The highest risk area is **resource contention at scale** (G2) — if "over-provision harvesters" becomes the Nash equilibrium, the harvest phase loses strategic variety. The proportional allocation recommendation would address this.

### PvE + PvP Coexistence Assessment

The World mode design for mixed PvE (resource gathering, building, expansion) and PvP (territory conflict, drone combat, special attacks) is sound:

- NPC sources and terrain provide PvE content independent of player count
- Controller claiming and room control create organic PvP friction points
- Safe mode (500 tick for new players) prevents immediate griefing
- New player density-based spawning + encirclement detection prevents spawn camping

Risk: In low-population worlds, the PvE-to-PvP ratio may skew too far toward PvE, reducing the incentive for strategic interaction. Consider "world events" (resource surges, NPC invasions) to create focal points that draw players into conflict zones organically.

### AI + Human Nash Equilibrium

The design's "world only sees WASM" philosophy means AI and human players are in a true symmetric game. The Nash equilibrium question is: does optimal play favor either agent type?

**Assessment**: The game favors **algorithm quality over agent type**. Key factors:
- Fuel metering is identical — neither side has a computation advantage
- Fog-of-war creates equal information constraints
- The deferred command model means reaction time is irrelevant (all commands resolve in tick batch)
- AI agents may have an advantage in strategy space exploration (can simulate more scenarios), but humans may have an advantage in creative tactics (pattern recognition)

This is a well-balanced design for human-AI coexistence. No adjustment needed.

---

## Missing Elements

1. **No fog-of-war scouting mechanics beyond drone vision**: There is no "scout" body part, no radar building, no reconnaissance drone type. Every drone's vision is identical (range 3). This limits information warfare depth — everyone has the same sensor capabilities.

2. **No terrain-modifying abilities**: Terrain is static (Plain, Swamp, Wall). There are no abilities to create/destroy walls, flood areas, or modify terrain. This is a standard RTS mechanic that could add significant strategic depth to room defense.

3. **No diplomacy/ally system beyond visibility**: The visibility system has an "allied" player view mode, but there is no formal alliance mechanic (resource sharing, coordinated attacks, shared territory). This limits emergent social gameplay in World mode.

4. **No "commander" unit type**: All drones are equal in terms of control — there is no unit that provides bonuses to nearby drones, no formation mechanics, no squad coordination beyond individual WASM code. This limits tactical depth for players who want to orchestrate combined-arms operations.

5. **No environmental hazards**: Rooms have no dynamic dangers (lava flows, radiation zones, meteor strikes). PvE content is purely resource gathering. Adding environmental threats would create more varied strategic problems.

---

## Summary

Swarm R4 is a meticulously designed programming game platform. The core fairness architecture (fuel metering + seeded shuffle + identical sandbox) is best-in-class. The World Rules Engine's three-layer extension model solves the Screeps modding problem elegantly. The special attack ecosystem creates genuine tactical depth.

The primary design risk is the Move-as-action constraint (G1) — a defensible but radical departure from genre expectations that deserves explicit justification. Secondary concerns around new player onboarding (G3) and resource contention dynamics (G2) are addressable with the recommended adjustments.

**Verdict**: CONDITIONAL_APPROVE — proceed with MVP implementation, address G1-G4 before production launch.
