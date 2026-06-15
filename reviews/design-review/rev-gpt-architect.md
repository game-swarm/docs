# Design Review — Architect Perspective (rev-gpt-architect)

VERDICT: CONDITIONAL_APPROVE

Scope: game design review only, not spec-compliance review. Focused on structural coherence of mechanics, completeness/edge cases, internal consistency, and scalability for multi-player MMO.

## Strengths

1. Strong core premise and fairness model
   - “World only recognizes WASM” is the right architectural/game-design anchor. Human and AI players share the same deployment and execution path, avoiding the common failure mode where bot interfaces become privileged gameplay APIs.
   - Deferred Command Model plus fuel metering gives the design a clean separation between player planning and world mutation.

2. Deterministic simulation is treated as a first-class game mechanic
   - Fixed PRNG/hash, ordered ECS systems, IndexMap, no f64, replay checksum, and explicit command ordering are coherent with a persistent programmable MMO.
   - This is especially important because players will write adversarial automation; replay/debuggability is not optional.

3. World vs Arena separation is healthy
   - The design correctly distinguishes “organic unfair persistent world” from “symmetric competitive match.” This prevents impossible requirements like making persistent worlds globally fair while still supporting ranked competition in Arena.

4. Configurable World Rules Engine is compelling
   - Resource types, body parts, damage types, visibility, storage logistics, and Rhai rule modules form a strong platform story.
   - Making rules visible to players and AI agents is an excellent design choice; programmable games need machine-readable rules.

5. Anti-dominant-strategy thinking is present
   - Global storage taxes, local storage privacy, delayed global/local conversion, no manual control, code update cooldowns, and drone lifespan all show awareness of long-term MMO economy failure modes.

6. Good separation of game action and management/control surfaces
   - MCP is explicitly not gameplay action control. This preserves fairness and prevents AI-specific fast paths.

## Issues by Severity

### Critical

None that require rejecting the design outright. The core structure is viable.

### High

A1. Expansion and map/room topology are underspecified for MMO scale

The design talks about rooms, controllers, ownership, drone caps, random spawn, fixed spawn, observers, terminals, and multi-room empires, but does not define the world topology clearly enough.

Missing/unclear:
- Room size and coordinate system boundaries.
- Room adjacency and movement between rooms.
- Whether rooms are dynamically generated, pre-generated, sharded, instanced, or infinite-grid.
- How new players are placed near/away from established players.
- How contested neutral rooms work.
- Whether one player can own multiple controllers/rooms, and if so what hard/soft limits exist.
- How room cap interacts with cross-room drones.
- How Arena maps are declared and validated for symmetry.

Why this matters:
- In Screeps-like games, topology is not a minor detail; it determines expansion pressure, logistics difficulty, PvP boundaries, player density, newbie survival, and server sharding.
- Without a topology model, the economy, controller rules, visibility, pathfinding, spawn policy, and MMO scalability cannot be validated as one coherent game.

Recommendation:
- Add a “World Topology and Territory Model” section before or inside World Rules.
- Define rooms, exits, coordinates, controller ownership, expansion rules, neutral room behavior, spawn placement constraints, room capacity, cross-shard travel, and Arena map templates.

A2. New-player protection and late-join survivability are not complete enough for persistent MMO

The design has spawn policies and tutorial recycling, but persistent World mode still appears vulnerable to the classic MMO/Screeps problem: established players can dominate territory and resources around new spawns.

Missing/unclear:
- Protected spawn zones or newbie rooms.
- Initial safe mode semantics for new colonies.
- Conditions under which safe mode can/cannot be activated.
- Whether safe mode blocks attack, drain, hack, build, transfer, spawn camping, or only direct damage.
- Grace period for code deployment and initial bootstrapping.
- How respawn avoids repeated placement into hostile/strip-mined areas.
- Whether abandoned/dead colonies leave ruins/resources that create predatory farming loops.

Why this matters:
- Persistent programmable games are harsh: players can automate griefing 24/7.
- If onboarding protection is weak or vague, the long-term population will collapse into incumbent empires plus churned new players.

Recommendation:
- Define a “Colony Bootstrap / New Player Protection” lifecycle: initial spawn resources, invulnerability/safe-mode boundaries, what actions are allowed during protection, when protection ends, and anti-abuse restrictions.

A3. Combat/special effects are too powerful and not yet integrated with economy, visibility, and determinism

The basic combat model is plausible, but special attacks introduce several MMO-scale instability risks.

Specific risks:
- Hack can remove ownership/control and create Neutral idle behavior, but ownership restoration, queued commands, visibility, logistics, and target immunity are only partly defined.
- Overload reduces another player’s fuel budget. This is a meta-resource attack on compute, not just in-world state. It can become a denial-of-play mechanic if stacked by many attackers or alt accounts.
- Drain, Fabricate, Scramble, Fortify, Debilitate introduce status effects, ongoing actions, and cross-tick state, but the status stacking and priority rules are not fully specified.
- “命中判定取决于 body part 数量与目标防御的差值” is too vague for a deterministic programmable game.
- “damage_multiplier affects success rate/effect amount” is ambiguous and can break replay expectations unless fully formalized.

Why this matters:
- These mechanics can be exciting, but they are high-complexity late-game mechanics. If introduced too early or left vague, they will dominate design and implementation complexity.

Recommendation:
- Move advanced special attacks to a later phase or optional ruleset.
- For each status/effect define: target validity, range, stacking, refresh, immunity, interrupt, cleanup on death/ownership change, conflict priority, replay encoding, and cap per target/player/tick.
- Treat Overload especially carefully; consider making it affect in-game unit efficiency rather than player CPU budget, or apply strict per-target diminishing returns.

A4. Rule extensibility is structurally ambitious but may undermine game identity and balance

The design positions Swarm as both a specific MMO RTS and a configurable game engine platform. That is powerful, but there is tension:
- Default game rules need strong identity and balance.
- World-level custom resources/body parts/actions/effects can create wildly incompatible games.
- Modded worlds may fragment SDK expectations, tutorials, strategy examples, and matchmaking.
- “custom_actions dynamically register CommandAction variants” conflicts with the cost of stable SDKs, replay tools, validators, and player code portability.

Why this matters:
- If every world can redefine too much, Swarm becomes an engine with no canonical game. That can weaken player learning, community strategy sharing, and competitive comparability.

Recommendation:
- Define a “Core Ruleset” that is stable, canonical, and used for official World/Arena.
- Classify extensibility into tiers:
  1. Safe config values, no SDK changes.
  2. Declarative extensions using existing CommandActions/effects.
  3. Experimental custom actions requiring world-specific SDK/schema generation.
- Make official ranked Arena allow only Tier 1/approved Tier 2 changes.

### Medium

A5. Resource storage model has internal ambiguity

The document says drone harvesting enters local storage near Storage/Extension/Spawn, but it does not define what happens when no valid storage exists, storage is full, or multiple nearby stores are valid.

Undefined cases:
- Does Harvest require Carry capacity, like Screeps, or can resources teleport to nearest storage?
- If resources go to “nearest local storage,” how is nearest chosen deterministically on ties?
- Can drones carry resources as an entity inventory? Carry part implies yes, but harvesting text implies direct deposit.
- What happens when local storage is destroyed during global transfer?
- Can in-transit global/local resources be intercepted anywhere, on a path, or as abstract events?
- How are market orders reserved against resources in transfer?

Recommendation:
- Define a single resource custody state machine: source → drone cargo → structure inventory → local account → in-transit → global account → market escrow, with deterministic failure/rollback rules.

A6. Drone lifecycle and Controller-based age rollback is mechanically interesting but potentially confusing

The design says every owned Controller rolls back global drone age by 0.5 tick, stacking up to fully offset natural aging. This creates an empire-wide lifespan upkeep model, but several behaviors are unclear.

Undefined cases:
- Does Neutral/Hacked time pause before or after global rollback?
- Does controller loss immediately accelerate all drones?
- Is age fractional or fixed-point?
- Which controllers count: owned, reserved, contested, safe-mode, downgrading?
- Can players keep drones immortal with two controllers forever? The text says capped at full offset, but this means lifespan stops being a meaningful sink for mature empires.

Recommendation:
- Reframe as explicit “lifecycle maintenance” or “global decay reduction” with fixed-point math and clear caps. Consider keeping some minimum aging rate so replacement/logistics remain relevant.

A7. Tick execution model has fairness and scalability pressure points

The design executes commands inline in shuffled player order with first-come-first-served resource conflict resolution. This is deterministic and simple, but at MMO scale it creates important gameplay consequences.

Risks:
- Whole-player order can dominate contested resource/combat outcomes for a tick.
- A player with many commands may get many sequential advantages within their turn before another player acts, depending on interleaving details.
- Sorting by shuffled player order + player-local sequence may be deterministic but not necessarily fair across large battles.
- 2.5s collect / 0.5s execute may not hold with thousands of players, many host_path_find calls, large snapshots, and Rhai mods.

Recommendation:
- Define command interleaving at action/entity granularity, not only player granularity, or explicitly justify player-order resolution as intended gameplay.
- Add command budgets per player/entity/tick.
- Define overload behavior when COLLECT exceeds budget: skip player, use previous code, partial commands, or tick abandon?

A8. Visibility model needs stronger separation between drone perception, player UI, replay, and server authority

The design has a good two-layer visibility model, but several edge cases are undefined.

Missing/unclear:
- What exact entity fields are visible at each visibility level? Position only? Body? Hits? Owner? Cargo? Intent? Status effects?
- Does MCP `inspect_entity` reveal full state only for visible entities or also hidden internals?
- Can players infer hidden local storage from market/leaderboard/resource tax signals?
- How delayed public spectate interacts with live players also watching streams or using alt accounts.
- Whether observer buildings reveal full state or only extend sight range.

Recommendation:
- Add a visibility matrix by entity type and field, for drone snapshot, player UI, MCP, replay, spectator, and audit/admin.

A9. Safe mode exists in Controller but is not designed

Controller contains `safe_mode`, `safe_mode_available`, and `safe_mode_cooldown`, but the gameplay rules for safe mode are absent.

Recommendation:
- Define trigger conditions, duration, cooldown, effects, exclusions, and anti-abuse rules. In persistent MMO, safe mode is a foundational survival mechanic, not a field in a struct.

A10. Market/economy is referenced but not designed

Terminal, market trading, global resources, market_requires_terminal, and price manipulation prevention are referenced, but market mechanics are not specified.

Missing/unclear:
- Order types and settlement timing.
- Fees, taxes, escrow, cancellation, partial fill.
- Regional vs global market.
- Transport requirements and interception rules.
- Anti-alt/anti-manipulation assumptions.

Recommendation:
- Either mark market as out of scope for MVP or add a minimal deterministic market model.

### Low

A11. Some numeric defaults are placeholders but presented as frozen design

Examples: RCL progress, body costs, tower damage, special attack cooldowns, fuel budget effects, storage tax rates, upkeep examples. These are likely not balance-tested.

Recommendation:
- Label numeric values as “initial tuning constants” unless backed by simulation. Reserve “frozen” for interfaces and invariants, not balance numbers.

A12. “Engine does not hardcode Energy” conflicts with examples and some mechanics

The document correctly says core engine should not hardcode Energy, but examples and special attacks often use Energy-specific costs and semantics. That is fine for the default ruleset, but the boundary between engine invariant and default ruleset should be clearer.

Recommendation:
- Explicitly distinguish Engine Core, Default Ruleset, and Example Mod values.

A13. Rhai module visibility statement is odd for trusted server-side rules

The Rhai API says state queries are visibility-filtered and mods cannot see hidden entities. Since mods are server-installed trusted rules, this may limit legitimate global mechanics and create confusing behavior.

Recommendation:
- Define mod capability classes: global-authority mods, player-perspective mods, spectator-safe mods. Do not force all mods through player visibility unless that is an intentional design constraint.

A14. Tutorial is mentioned as exception but not designed

Tutorial worlds are said to allow limited guided operations and 100% recycle refund, but the tutorial progression, sandbox boundaries, and relation to real worlds are undefined.

Recommendation:
- Add tutorial as a separate non-authoritative world type with explicit allowed shortcuts and migration path to real code deployment.

## Missing Design Sections

1. World topology and territory model
2. New-player bootstrap and protection lifecycle
3. Complete command/action schema from a game-design perspective
4. Resource custody/inventory state machine
5. Status effect and special attack resolution model
6. Safe mode rules
7. Market mechanics or explicit deferral
8. Visibility field matrix
9. Sharding/cross-shard gameplay model
10. Official Core Ruleset vs modded world compatibility policy
11. Balance/simulation plan for numeric constants
12. Failure-mode gameplay behavior: tick overrun, player timeout, stale code, disconnected player, module deployment failure

## Internal Consistency Notes

1. MCP fairness is internally consistent
   - The document repeatedly states MCP is management/visibility/deployment, not direct gameplay action. This is coherent and should be preserved.

2. Deferred command model is mostly consistent
   - Mutating host functions are banned, and all state change goes through command validation. Good.
   - However, Rhai mods bypass the command pipeline via actions. That can be fine because they are world rules, but the distinction should be made more explicit in game-design terms: player agency vs world-rule authority.

3. Configurable actions vs stable SDK tension
   - The design says new CommandAction requires engine registration and IDL exposure, but later says new CommandAction can be dynamically registered from TOML and automatically exposed. This needs reconciliation.

4. Global storage mode examples conflict with anti-teleport rule
   - Mode A says no logistics / instant global storage is possible, while later transfer times are “不可为 0” to prevent teleport supply. This is not necessarily wrong if Mode A is an explicit arcade exception, but it should be labelled as an exception and disallowed in persistent/ranked worlds if desired.

5. Drone harvesting/storage flow conflicts with Carry part semantics
   - Carry part implies drones physically carry resources, but default harvesting text says resources go directly to nearest local storage. Pick one canonical default.

## Scalability Assessment for Multi-player MMO

The macro architecture can scale conceptually via shards, gateway statelessness, NATS, FoundationDB, and deterministic tick execution. The game design itself still needs stronger constraints before it is MMO-ready.

Main scalability risks:
- Pathfinding host function load across thousands of drones.
- Snapshot serialization size for large empires and many visible entities.
- Player-order command execution in large battles.
- Rhai mod execution across thousands of players.
- Global market/storage operations becoming cross-shard coordination bottlenecks.
- Replay/storage volume for full world snapshots every N ticks.
- New-player placement in saturated maps.

Recommended scalability design additions:
- Per-room or per-shard simulation boundaries with explicit cross-boundary interactions.
- Per-player, per-drone, and per-command budgets.
- Snapshot delta and visibility-index model.
- Pathfinding cache and deterministic path budget limits.
- Cross-shard market/storage consistency model.
- Load-shedding behavior that is deterministic and fair.

## Phase Ordering Recommendations

1. Before implementation freeze
   - Define world topology, territory, new-player protection, safe mode, resource custody, and visibility matrix.
   - Reconcile custom CommandAction dynamic registration vs stable SDK/IDL.

2. Phase 1 MVP
   - Keep one room or small fixed room graph.
   - Implement only core loop: spawn, move, harvest, carry, transfer, build, repair, attack, death, controller upgrade.
   - Do not implement advanced special attacks, market, custom actions, or Rhai mods yet.

3. Phase 2 multiplayer
   - Add contested resources, PvP basics, safe mode, fog of war, room transitions, and deterministic replay.
   - Add new-player protection before public persistent world testing.

4. Phase 3 economy/persistence
   - Add local/global storage only after resource custody is formalized.
   - Add market only after storage, escrow, and transport semantics are stable.

5. Phase 4 extensibility
   - Add Rhai mods and custom rule registries after the default Core Ruleset is fun and stable.
   - Keep custom CommandAction as experimental until SDK/schema generation is proven.

6. Phase 5 advanced combat
   - Add Hack/Drain/Overload/Debilitate/Fortify/Fabricate only after basic combat has telemetry and balance data.
   - Overload should receive separate design review because attacking player compute budget is unusually dangerous.

## Final Recommendation

CONDITIONAL_APPROVE.

The design has a strong and coherent foundation: WASM-only player agency, deterministic deferred commands, clear human/AI fairness, and a promising configurable rules platform. It is architecturally recognizable as a modernized Screeps-like MMO with better determinism and extensibility.

The main concern is not the core concept; it is that several MMO-critical game systems are referenced but not yet fully designed. World topology, newbie survival, safe mode, resource custody, market logistics, visibility fields, and special-effect resolution must be specified before broad implementation. Without those, the design risks producing a technically elegant engine whose persistent-world gameplay fails under real adversarial multiplayer pressure.

Approve the direction, but require the missing high-severity sections to be resolved before treating the game design as implementation-ready for persistent MMO scale.
