# R12 Game Designer Review — rev-dsv4-designer

**Reviewer**: DeepSeek V4 Pro (Game Designer)
**Date**: 2026-06-14
**Documents reviewed**: DESIGN.md (full, 1463 lines), tech-choices.md, P0-1 through P0-9 (all frozen P0 specs), R11 designer review

**Context**: Phase 0 Architecture Freeze complete. All P0 specs frozen as of 2026-06-14. This review evaluates the frozen design from a game design perspective — strategy space, dominant strategy risk, information asymmetry, PvE+PvP incentives, and AI-human coexistence equilibrium.

---

## VERDICT

**APPROVE_WITH_RESERVATIONS**

Phase 0 has produced a remarkably coherent design. The deferred command model, WASM-only execution path for all players (human and AI), damage type resistance matrix, special attack framework, three-tier logistics model, and body part extension system form a genuinely deep strategy game. The MCP-as-peer-interface contract is watertight — AI agents cannot game the system through MCP tools.

However, five HIGH-severity game design concerns remain unaddressed from R11, and two new ones emerge from the frozen spec set. The Phase 0 freeze means these are now implementation-time problems: they must be resolved in Phase 1-2 code and world.toml defaults, not in design docs. Three MEDIUM concerns and one LOW concern round out the review. 11 concerns total.

The single most critical finding: **World mode defaults to a hostile free-for-all with no cooperation mechanics, no PvE content, and no territorial pressure release valve.** The game ships with a Prisoner's Dilemma as its default social contract. The `alliance-system` is mocked up as a mod in the market (§8.7) but is not in core. This is the design's most significant liability — not because alliances are hard to add later, but because *new player onboarding and retention depend on positive-sum social experiences being available from day one.*

---

## STRENGTHS

1. **Deferred Command Model — Watertight Design Contract** — P0-2 §7.2's deploy-reset refund rule (credit tied to module_hash, voided on redeploy) closes a subtle exploit. P0-4 §3 confirms "no imperative host functions for mutation." P0-9 Source Gate enforces `MCP_Deploy → reject 403` for gameplay commands. Three layers of defense against a whole class of exploits. World-of-Warcraft-auction-house-level anti-gaming maturity.

2. **Damage Type × Resistance Matrix — Genuine Strategic Depth** — Six base damage types with multiplicative stacking (body_res × attribute_res) forces players to read opponent body composition and adapt. This is Pokemon-level type-matchup depth, but applied to programmable units where body composition is a strategic choice, not a fixed roster.

3. **Special Attack Framework Creates Tactical Roles** — Hack (mind control at ≤30% HP), Drain (resource theft over time), Overload (CPU budget sabotage), Debilitate (×2 vulnerability), Disrupt (interrupt ongoing actions), Fortify (×0.5 shield). Each creates a distinct tactical role beyond "do damage." Disrupt as anti-Hack/Drain is a particularly good counter-play loop.

4. **Three Logistics Modes with Explicit Trade-offs** — No-logistics (Arena-friendly), Light logistics (1% global tax / 5% local build — creates natural local-storage bias), Hardcore logistics (Factorio-style, global_storage_enabled=false). The 1%/5% asymmetry is beautifully tuned: it incentivizes distributed local storage without making global storage irrelevant.

5. **Body Part Extension System — "Design Your Own Unit"** — `[[body_part_types]]` in world.toml + Rhai mod registration of new parts (Leech, Scramble, Fabricate). The combinatorial space of 8 base parts × max 50 slots × damage type bindings × special attack associations is enormous. This transforms Swarm from a fixed-unit game into a unit-design game.

6. **Progressive Global Storage Tax — Anti-Monopoly Architecture** — Four-tier progressive tax (0%/0.01%/0.05%/0.20%) with three explicit anti-monopoly mechanisms: tax, stealth (local storage is hidden), and transport time (no teleport). The design names and counters economic snowball — rare in multiplayer game design documents.

7. **Two-Layer Visibility Model — Elegant Architecture** — P0-5 §3.5: drone snapshot always uses `is_visible_to(player)` for game fairness, but player_view can be "drone"/"full"/"allied" for display. The separation of tactical fog (gameplay) from spectator fog (viewing) is the correct architecture. Spectate_delay on public observers prevents real-time information leaks.

8. **Code Propagation Speed — Asymmetric Update Dynamics** — When propagation_speed > 0, code updates ripple outward from Spawn/Controller. This creates a spatial deployment puzzle: attack with new code at the frontier before defenders receive the update? Propagation source choice (Spawn vs Controller vs AnyDrone) adds a strategic dimension most games never consider.

9. **Rhai Mod System with i18n — Platform Thinking** — The mod.toml format with multi-language descriptions (zh/en/ja) and typed config parameters (u32/fixed<u32,N>/enum) shows mature platform design. The engine doesn't know about mods — mods are ECS plugins that the engine loads. Clean separation.

10. **Determinism Contract — Replay is First-Class** — Blake3 for hash/PRNG/signing, IndexMap for deterministic iteration, `.chain()` for fixed ECS order, integer-only arithmetic. The design understands that determinism is not a feature, it's the foundation for anti-cheat, replay, debugging, and competitive integrity.

---

## CONCERNS

### Strategy Space & Dominant Strategy

**G1 — SEVERITY: HIGH** (R11 Carryover, Unchanged)
**Drone Lifespan Forces Binary "Expand or Die" — No Alternative Survival Paths**

The 1500-tick drone lifespan (§3.1, §8.2) combined with Controller-capture age reset creates a hard constraint: any player not actively expanding loses their entire drone fleet within 75 minutes. The 500-tick cooldown prevents ping-pong abuse between two players, but also prevents coordinated team survival — two allied players cannot "pass" a room to reset each other's drone ages.

Defensive/turtle archetypes are non-viable in standard World mode. The equilibrium analysis (see Strategy Depth section) shows Expansionist dominates all other strategies because the lifespan mechanic creates an absolute deadline. There is exactly ONE trigger for lifespan reset (Controller capture), and exactly ONE way to avoid fleet death (keep capturing rooms).

The empire-upkeep mod adds economic pressure on large empires, but it's a mod — not in default World mode. The game ships with expand-or-die as the only viable long-term strategy.

*Recommendation*: Add at minimum `lifespan_refresh_resource_cost` to core world.toml (not mod-only): spend rare resources to reset drone age. This gives Economic players a survival path without expansion. Add `lifespan_reset_on_room_defense`: holding a room against attack for N ticks refreshes drones in that room — rewards defenders, not just aggressors.

**G2 — SEVERITY: HIGH** (R11 Carryover, Confirmed by P0-5)
**Damage Type System Has Hidden Attribute Flags — Players Guess Multipliers**

The damage type system (§8.2) defines 6 base types with body-part and attribute-level resistances. Players can see body parts (P0-5 §2.4: "其他玩家身体部件组成 → ✅ 可见") but attribute flags like `Shielded`, `Flaming`, `immune_EMP` are **hidden** — they're not in the visibility table at all.

```
Effective Damage = BaseDamage × body_resistance[type] × attribute_resistance[type] × damage_multiplier
```

A player attacking with EMP damage cannot know if the target has `Shielded` (×0.7) or `immune_EMP` (×0) — they see body parts but not attributes. The fog-of-war here creates a "guess the multiplier" game that feels arbitrary, not strategic.

This is not about information hiding for tactical depth — it's about *invisible game mechanics*. A player who doesn't read world.toml (or the MCP `swarm_get_world_rules` response) doesn't even know attribute flags *exist*. The design creates hidden mechanical layers that affect combat outcomes by up to 100% (immune) but provides no in-game observability.

*Recommendation*:
- Add `status_effects` field to entity snapshot: `"status_effects": ["Shielded", "Flaming"]` — reveals WHAT effects are active, not the exact multiplier. This gives players actionable information without eliminating the strategic uncertainty of *which resistance values* the world.toml configured.
- P0-5 §2.4 must add a row: "其他玩家属性标记 (attribute flags)" with visibility = "✅ 可见（激活的状态效果名称，非倍率数值）"
- `swarm_inspect_entity` MCP tool should return active attribute flag names (cost: 5 fuel, not per-tick). This mirrors the human player clicking a unit to see buffs/debuffs.

**G3 — SEVERITY: HIGH** (NEW — Emerges from Frozen P0-3 + DESIGN §8.2)
**Overload Special Attack Disproportionately Debuffs AI Players — Asymmetry Codified**

The Overload special attack (§8.2) reduces target fuel budget by 500k (5% of MAX_FUEL=10M). P0-4 §4.2 confirms MAX_FUEL=10M with hard cutoff at 2500ms wall-clock. For human players whose WASM code is compute-light (efficient Rust/AssemblyScript, few pathfind calls), this is a minor inconvenience — they operate at 20-40% fuel utilization. For AI players using LLM-generated WASM that operates near the fuel cap (pathfinding, entity enumeration, strategy evaluation), a 5% reduction cascades: fewer host function calls → less information → worse decisions → more failed commands.

This creates a perverse strategic incentive: target AI players with Overload specifically to degrade their decision quality. Since AI and human players share the same world (§1.1), Overload is effectively a "stupidity debuff" that hits AI harder than efficient human coders. The fuel reduction is an ABSOLUTE number (500k), not proportional to actual usage.

The Nash equilibrium implication: in a world with AI players, the optimal strategy includes Overload-harassing AI opponents because the return on investment (fuel cost 300 Energy to remove 500k fuel from target) is higher against AI than against efficient human players. This is not symmetrical treatment.

*Recommendation*:
- Change Overload to reduce a *percentage of the target's actual fuel usage* rather than the absolute cap. An idle player at 10% fuel usage loses 50k (5% × 10% × 10M), while a maxed-out player loses 500k. This makes the debuff proportional to the target's optimization level — efficient code becomes a defense, not a vulnerability.
- Alternatively: Overload reduces MAX_COMMANDS_PER_PLAYER (100 → 90) rather than fuel budget. This affects all players symmetrically — whether your code is fast or slow, you get fewer actions.

**G4 — SEVERITY: MEDIUM** (R11 Carryover)
**Debilitate + Fortify Arms Race — Deterministic Equilibrium, No Counterplay**

Debilitate (×2 damage received, 50-tick duration, 150-tick cooldown) and Fortify (×0.5 damage received, 100-tick duration, 300-tick cooldown) are mirror effects. The optimal response to Debilitate is Fortify — but Fortify's cooldown is 300 ticks vs Debilitate's 150. Over time, Debilitate outpaces Fortify 2:1.

The equilibrium is deterministic: always Debilitate the enemy's highest-value drone; always Fortify your own; whoever runs out of Fortify cooldowns first loses. This lacks the timing-game/interaction depth that makes debuff systems interesting (see: WoW's dispel mechanics, Dota 2's purge interactions).

*Recommendation* (unchanged from R11): Make Debilitate and Fortify interact mechanically:
- Fortify on a Debilitated target: cleanses Debilitate, normalizes damage. Fortify cooldown reduced to 100 ticks when used as cleanse.
- Debilitate on a Fortified target: breaks Fortify, applies only ×1.3 damage (not ×2). Debilitate cooldown halved.
- This creates a "cleanse vs break" dynamic with meaningful timing decisions.

### Information Asymmetry Design

**G5 — SEVERITY: HIGH** (R11 Carryover, Frozen in P0-5 §7)
**Arena Mode Disables Fog of War — Contradicts Special Attack Design**

P0-5 §7 states: "简化可见性：比赛边界内全信息。双方玩家看到整个竞技场。公平竞技禁用 fog-of-war。" P0-7 §6 confirms: Arena `visibility.fog_of_war = false`.

But the special attack system (Hack, Drain, Overload, Disrupt) depends on range limitations and fog-of-war for tactical depth:
- Hack requires proximity to low-HP targets — with full visibility, defenders reposition preemptively
- Drain requires proximity to structures — defenders pre-position at all vulnerable points
- Disrupt's role as "stop the ongoing Hack/Drain" becomes an open-information timing game
- Overload's range targeting loses the discovery phase — you know exactly which enemy drones to target

Arena without fog-of-war eliminates the tactical layer these special attacks were designed for. The game reduces to a resource optimization puzzle with full information — closer to an auction than a strategy game.

The two-layer visibility model (P0-5 §3.5) has the correct architecture to fix this: drone snapshot can use `fog_of_war = true` for tactical gameplay while spectator view uses `player_view = "full"` with `spectate_delay ≥ 100` for audience experience. But Arena defaults don't use this.

*Recommendation*: Arena should default to `fog_of_war = true` for drone snapshots. Spectators get `player_view = "full"` via `spectate_delay ≥ 100` ticks (already designed). The stated rationale "公平竞技禁用 fog-of-war" is incorrect — symmetric fog-of-war is FAIR (both players have identical information constraints). Full information removes the fog-based tactical layer, not adds fairness.

**G6 — SEVERITY: MEDIUM** (R11 Carryover, Now Codified in P0-9)
**`swarm_simulate` + `swarm_dry_run_commands` — AI Oracle Advantage in MVP**

P0-3 §4.4: `swarm_simulate` (5/tick World, 3/tick Arena, 0.5× MAX_FUEL budget).
P0-9: Simulate source row — "snapshot-bound dry-run", player_id + snapshot_id.
P0-6 §3.1: `swarm_dry_run_commands` (20/h, compile budget).

An AI agent can:
1. Get snapshot → `swarm_dry_run_commands` to validate → if rejected, iterate
2. `swarm_simulate` forward N ticks with candidate strategies → pick best
3. Deploy optimized code → observe → repeat

A human player in MVP (Phase 1-2) has:
1. Mental simulation
2. Trial-and-error across real ticks (costly — wrong moves cost resources and position)

The asymmetry is in *information access*, not computation (fuel metering handles computation fairness). The MCP simulate/dry-run tools are free queries that the human Web UI doesn't expose equivalently in MVP. P0-6 §4.3 mentions local `swarm sim` but defers it to Phase 3.

With Phase 0 frozen, this is now an implementation-phase concern: Phase 2 ships MCP tools that Phase 1 human players lack.

*Recommendation*:
- Add `swarm_dry_run` as a Web UI button in Phase 2 (not Phase 3). Cost: 1 fuel per dry-run, same budget as MCP equivalent.
- Restrict `swarm_simulate` to a per-code-version budget (e.g., 100 total simulations per deployment, reset on module redeploy). Prevents simulation-spam-as-strategy.
- Add a "Planning Symmetry Principle" to DESIGN.md §4: any tool available to AI via MCP must have a human-facing equivalent in Web UI or CLI within one phase of the AI tool's introduction.

### PvE + PvP Incentive Structures

**G7 — SEVERITY: HIGH** (R11 Carryover, Continued)
**No Core Cooperation Mechanics — World Mode is a Prisoner's Dilemma**

Between any two players in default World mode:

```
           Cooperate    Defect
Cooperate  (3, 3)      (1, 5)
Defect     (5, 1)      (2, 2)
```

Defection (attacking/stealing) dominates cooperation. A player who cooperates expends resources helping another who may later attack them. With no alliance mechanics, shared vision, resource tribute, or mutual defense pacts, the Nash equilibrium is universal defection.

The DESIGN.md §8.7 mod market mockup lists `alliance-system` (★4.7, 678 installs) as a **mod** — not core. P0-7 (World Rules Engine) has no cooperative hooks. P0-3 (MCP Security Contract) has no alliance-scoped tools. No P0 spec defines:
- Alliance formation/invitation/acceptance/leaving
- Shared vision between allies (player_view = "allied" exists in P0-5 §3.5 but has no alliance formation mechanic to trigger it)
- Resource tribute (voluntary transfer between players at 0% tax)
- Mutual defense pacts or non-aggression treaties

This means Swarm ships with a default World mode where "人类和AI agent在同一世界共存" (DESIGN.md §10) defaults to a hostile free-for-all. New players and AI agents face an established-player gank-fest with no cooperative counterweight. The game's social contract at launch is "trust no one."

This is not a technical limitation — P0-5 §3.5 already defines `player_view = "allied"`. The missing piece is the social mechanic to FORM alliances and the game-mechanical benefits that make cooperation viable.

*Recommendation*: Add to Phase 2 minimum viable:
1. `alliance.invite` / `alliance.accept` / `alliance.leave` — MCP tools + REST endpoints
2. Shared vision: allied players' drone vision aggregates into each member's snapshot (uses existing `player_view = "allied"` infrastructure)
3. `resource_tribute` command: voluntary resource transfer at 0% tax, instant (incentivizes cooperation over market trading at tax rates)
4. `on_player_alliance_formed` / `on_player_alliance_broken` Rhai event hooks for mod-driven alliance mechanics
5. Alliance size cap (default: 5 players) to prevent mega-alliances from dominating

**G8 — SEVERITY: MEDIUM** (R11 Carryover)
**World Mode Has No Territory Pressure Release Valve**

Once a room is claimed (Controller captured), the only ways to lose it are:
- Enemy captures the Controller (PvP)
- Downgrade timer expires (5000 ticks without owner)
- Voluntary abandonment (not designed as a mechanic)

There is no environmental pressure to vacate or lose territory. This creates:
- "Dead rooms" — claimed but unused, blocking new players from the map
- Territory inflation — total claimed rooms grows monotonically (bounded only by map size and player count)
- Late-joiner disadvantage compounds over time — all good rooms taken

The empire-upkeep mod (§8.7) provides economic pressure on LARGE empires but does nothing about dead rooms. A player who claims 3 rooms, puts a Controller in each, and goes idle for weeks still holds those rooms for 5000 ticks (~4 hours at 3s/tick) before downgrade starts. With occasional login to reset downgrade timers, they hold territory indefinitely with zero activity.

*Recommendation*: Add to core World mode (configurable on/off, default on):
- `controller_decay_rate`: Controller level decays by 1 per N ticks if the room has zero drone activity for M ticks. Default: N=1000, M=100.
- `inactive_room_release`: rooms with no drone visits for 5000 ticks become neutral (Controller unowned, structures persist but degrade at 2× rate).
- `room_activity_metric`: count of distinct ticks in the last N where at least one player-owned drone was present. Decays over time. Below threshold → room marked "inactive" on map (visible to all).

### Nash Equilibrium & AI-Human Coexistence

**G9 — SEVERITY: MEDIUM** (R11 Carryover)
**AI-Human Specialization Gap Widens — Not Acknowledged in Design**

With the expanded damage type system, special attacks, and resource logistics:

| Layer | AI Advantage | Human Advantage |
|-------|-------------|-----------------|
| Build order optimization | ✅ Pre-compute optimal sequences | ❌ Intuition only |
| Damage type counter-picking | ✅ Programmatic analysis of visible body parts | ✅ Pattern recognition |
| Special attack timing | ❌ Requires opponent modeling | ✅ Psychological prediction |
| Resource logistics | ✅ Perfect optimization | ❌ Rough estimation |
| Strategic deception | ❌ Predictable LLM patterns | ✅ Creative feints |
| Multi-room coordination | ✅ Parallel optimization | ❌ Mental bandwidth limit |

The equilibrium: AI dominates optimization layers; humans dominate strategic layers. This is not inherently bad — complementary niches create interesting dynamics. But:
1. The design never acknowledges this split
2. There's no mechanism for humans to compete in optimization or AI to compete in deception
3. The "best player" in a mixed world may always be a human+AI pair — which makes the AI-only and human-only leaderboard categories feel like consolation prizes

*Recommendation*:
- Add `strategy_indicators` to leaderboard: "Player X is focusing on [Expansion / Defense / Economy / Aggression]" derived from observable metrics (drone composition ratios, building patterns, resource flow direction). Gives humans strategic-level reads without programmatic analysis.
- Document the intended coexistence model explicitly in DESIGN.md §1.1: "Swarm 中 AI 和人类是互补的存在——AI 擅长优化，人类擅长策略。两者在同一世界中的互动产生的涌现玩法是 Swarm 最独特的价值。"
- Add a `deception_score` metric (internal, no gameplay impact): how much does a player's observed behavior deviate from their historical pattern? For community analysis only.

**G10 — SEVERITY: LOW** (R11 Carryover)
**Late-Joiner Protection Not Configurable**

`spawn_policy` supports RandomRoom, ManualSelect, FixedSpawn, Inherit (§8.2). But there's no:
- `spawn_distance_min_from_player`: minimum room distance from existing players' closest Controller
- `new_player_protection_ticks`: automatic safe mode on first Controller for N ticks
- `new_player_resource_stipend`: one-time resource grant on first join, scaled to world average wealth

A new player who spawns adjacent to a level-8 empire can lose their only Spawn before deploying code. The Controller safe_mode mechanic (§3.1) is a per-player activated ability, not an automatic protection. A new player who doesn't know to immediately activate safe mode is defenseless.

*Recommendation*: Add to spawn config in world.toml (configured per-world, default values for World mode):
- `spawn_distance_min_from_player`: u32, default 5 rooms
- `new_player_safe_mode_ticks`: u32, default 100
- `new_player_resource_stipend`: ResourceCost, default `{Energy: 2000}`

**G11 — SEVERITY: MEDIUM** (NEW — Phase 0 Freeze Context)
**No Tutorial-to-World Graduation Path — Onboarding Friction**

Tutorial worlds are isolated (`world.mode = "tutorial"`, P0-9 §2.4: "Tutorial 来源的指令仅可在 world.mode = 'tutorial' 的世界中接受"). Tutorial worlds have separate global storage namespace (`tutorial_{world_id}`). This is architecturally clean but creates an onboarding cliff:

1. Player learns in Tutorial world (100% recycle refund, guided actions)
2. Player "graduates" to a real World — all resources, drones, and progress are gone
3. The first real-world experience is: spawn alone, no resources, no allies, potentially next to a level-8 empire
4. Tutorial taught the player to use guided actions — World mode has no guidance at all

The gap between "protected tutorial" and "hostile free-for-all" is too wide. There's no intermediate "rookie world" with limited PvP, no "newbie protection window," no "starter colony" that persists across the tutorial boundary.

*Recommendation*:
- Add `world.mode = "rookie"`: PvP disabled for first N ticks (default 500), 100% recycle refund for first 200 ticks, spawn_distance_min_from_player enforced at 10 rooms. Players auto-graduate to standard World after N ticks or upon first PvP action.
- Allow tutorial worlds to export a "colony template" (body config + initial strategy code) that can be deployed in a real world — gives new players something to start with.
- Add Phase 4 milestone: "rookie world graduation" with a ceremony/achievement to make the transition feel like progress, not loss.

---

## MISSING

The following game design elements are absent or underspecified in the frozen Phase 0 documents:

1. **Cooperation framework** (R11 carryover, now frozen out) — Alliance formation, shared vision, resource tribute, mutual defense. The `alliance-system` mod mockup exists but no core mechanic. Essential for World mode PvE+PvP coexistence and new player retention.

2. **PvE content hooks** — No world events, environmental threats, neutral enemies, or shared objectives. The Rhai `on_world_event` hook doesn't exist. A game engine without PvE can only run zero-sum PvP — this limits World mode to hostile competition only. No positive-sum play exists.

3. **Territory churn mechanics** — No environmental decay, no inactive room release, no map rotation. World mode territory is permanent unless actively conquered. This leads to map ossification as the world ages.

4. **Scout/reconnaissance specialization** (R11 carryover) — All drones have identical vision range (3). No body part for intelligence-gathering (longer vision, see-through-walls, detect hidden resources). Vision is a "free" attribute — every drone is equally a scout. This eliminates an entire class of strategic specialization.

5. **Arena spectator UX** — P0-5 §3.5 specifies the technical architecture (two-layer visibility, spectate_delay) but not the viewer experience: map overlay with both players' actual views? Fog-of-war toggle per-player? Commentary hooks? Replay speed controls?

6. **Ranking/league meta-structure** — Arena mode defined at engine level but ranking algorithm, league splitting (Human/WASM, AI-assisted, AI tournament), season structure deferred to Phase 7. The leaderboard metrics affect game design — players optimize what they're ranked on. If ranking is "GCL + rooms + drone count," the leaderboard itself reinforces the expand-or-die dominant strategy.

7. **Body part extension IDL** — DESIGN.md §8.2 mentions `[[body_part_types]]` but no P0 spec for the extension interface. What fields does a new body part need? Damage type binding? Vision range modifier? Special attack association? Resource cost? The body part system is a key strategic axis but its extension API is undefined.

8. **Observable status effects** — The damage/resistance system creates hidden attribute flags (Shielded, Flaming, immune_X) that dramatically affect combat (×0 to ×2 multipliers). Players can see body parts but not attributes. No "entity status effects" field in the snapshot or MCP query results.

9. **Drone lifespan documentation inconsistency** — §3.1 shows `const DEFAULT_DRONE_LIFESPAN: u32 = 1500;` as a Rust constant in the Engine section. §8.2 shows `drone_lifespan` as a configurable world rule. Which is authoritative? The engine should read from world config, not have a hardcoded const.

10. **"Fun" metrics** — The design measures efficiency, fuel, command success rate, rejection reasons. Where are the fun metrics? "Times you surprised an opponent." "Resources stolen via clever Drain positioning." "Battles won against larger forces." "Alliances formed." The metrics dashboard (§5.4) is purely optimization-focused — it tells you how EFFICIENT you are, not how much FUN you're having.

---

## STRATEGY DEPTH ANALYSIS

### Strategy Space Cardinality

Per tick, a player's decision space is the product of:

- **Drone count**: 1-500 (capped by world.toml)
- **Body configurations**: 8 base parts, max 50 total → combinatorial. A 10-part drone has enormous possible configurations
- **Actions per drone**: 5-15 valid choices per tick (move/harvest/attack/special/transfer/build/global_storage)
- **Target selection**: per drone, 0-N visible targets (0-37 tiles in vision-3 hex)
- **Resource allocation**: which resources to spend (dynamic, per-world types)
- **Special attack timing**: cooldown management across 7 special attacks
- **Logistics mode**: local-vs-global storage decisions, transport timing

Conservative lower bound with 10 drones each having 5 valid actions:
```
10^5 × target_combinations × resource_decisions → ~10^8 to 10^12 per tick
```

Constrained by: drone body irreversibility (role commitment), resource budgets, fog-of-war, turn order uncertainty, drone lifespan (long-term commitment), code propagation delay.

**Effective strategic depth: VERY HIGH** — comparable to StarCraft micro + Civilization macro + Factorio logistics, with Pokemon type-matchups layered on top.

### Dominant Strategy Risk Assessment (R12 Update)

| Strategy | Viability | Hard Counter | Soft Counter | Risk |
|----------|-----------|-------------|-------------|------|
| Harvester spam | Early-game viable | Drone cap, empire upkeep (mod), SourceEmpty contention | Resource depletion | LOW |
| Turtle + tech | **Non-viable (G1)** | Drone lifespan forces expansion | None available | **HIGH** |
| Zerg rush | Viable | Tower defense, Fortify, defender advantage | Pre-positioning | LOW-MED |
| Economic snowball | Viable | Progressive tax, Hack, Drain | Local storage stealth | LOW |
| Hack domination | Viable | Psionic resistance, Disrupt interrupt | Spread drones | MED |
| Overload harassment | **AI-disproportionate (G3)** | None for AI players | Efficient code for humans | **HIGH** (vs AI) |
| Damage-type counter-picking | Viable | **Hidden attribute flags (G2)** | Body part visibility | MED |
| Scout + snipe | **Non-viable** | All drones have vision 3 — no scout specialization | None | N/A (gap) |
| Alliance builder | **Non-viable (G7)** | No core alliance mechanics exist | None | **HIGH** (gap) |

### World Mode PvE+PvP Nash Equilibrium (R12 Update)

With default World mode rules (no alliance system, no PvE events, expand-or-die drone lifespan):

**Phase 1 — Early game (0-500 ticks)**: Exploration + initial spawn. Players spread to avoid competition. Optimal: claim a room with 2+ energy sources. Nash: diffuse distribution, minimal conflict.

**Phase 2 — Mid game (500-2000 ticks)**: Territorial consolidation. Players encounter borders. First conflicts over contested rooms. Optimal: expand while maintaining drone count below upkeep threshold. Nash: local skirmishes, no total war.

**Phase 3 — Late game (2000+ ticks)**: Established empires. Three stable strategies emerge:
- **Expansionist**: Continuous room capture to reset drone lifespan. High risk, high reward.
- **Raider**: Hack/Drain/Overload harassment of neighbors. Medium risk, sustains without expansion.
- **Economic**: Optimize within existing territory. Low risk, slow growth — vulnerable.

**Phase 4 — Equilibrium outcome**: Expansionist → captures Raider's unprotected rooms → Raider counter-expands or dies → Economic gets absorbed. **Convergence: Expansionist dominance.** The drone lifespan mechanic creates forced expansion, and there is no defensive advantage sufficient to offset this pressure.

**With AI players**: AI Expansionists optimize build orders → AI Raiders optimize Hack timing → Human players cluster in Economic strategy → human Economies survive only if hidden behind AI buffer empires or if AI players form alliances (which don't exist in core).

**With alliance system (hypothetical)**: Allied players share vision, tribute resources, coordinate defense. The payoff matrix shifts:
```
           Cooperate (allied)    Defect
Cooperate  (5, 5)               (2, 4)
Defect     (4, 2)               (2, 2)
```
Cooperation becomes dominant within alliances. But alliance-vs-alliance dynamics create a meta-game of alliance formation and betrayal — much richer strategic texture.

### Information Asymmetry Progression

| Game Phase | Hidden Information | Strategic Value |
|-----------|-------------------|-----------------|
| Early (1-10 drones) | Enemy positions, resource locations | HIGH — scouting matters |
| Mid (10-50 drones) | Enemy Controller progress, resource reserves | MED — partial fog coverage |
| Late (50+ drones) | Resource reserves, fatigue/cooldowns, code version, **attribute flags** | MED — positional fog is gone but mechanical fog remains |

The game transitions from "where is the enemy" (early) to "what is the enemy thinking" (late) — a good progression arc. But the attribute flag problem (G2) breaks this arc: in late game, combat outcomes depend on hidden mechanical multipliers that players cannot observe. This shifts the information game from "read the opponent's intent" to "guess the hidden configuration" — a less satisfying strategic layer.

---

## SUMMARY

```
Verdict: APPROVE_WITH_RESERVATIONS

Phase 0 frozen. Implementation must address these design concerns:

BLOCKING (must resolve in Phase 1-2 implementation, not design docs):
  G1  [HIGH]  Drone lifespan forces binary expand-or-die strategy
  G2  [HIGH]  Hidden attribute flags create "guess the multiplier" combat
  G3  [HIGH]  Overload disproportionately debuffs AI players (NEW)
  G5  [HIGH]  Arena fog_of_war=false contradicts special attack design
  G7  [HIGH]  No core cooperation mechanics — World mode defaults to hostile

HIGH PRIORITY (should resolve before Phase 3):
  G4  [MED]   Debilitate/Fortify arms race lacks interaction depth
  G6  [MED]   swarm_simulate creates AI oracle advantage in MVP
  G8  [MED]   No territory pressure release valve
  G9  [MED]   AI-human specialization gap unacknowledged
  G11 [MED]   No tutorial-to-world graduation path (NEW)

LOW PRIORITY (can defer to post-MVP):
  G10 [LOW]   Late-joiner protection not configurable
```

---

*Reviewer signature: rev-dsv4-designer (DeepSeek V4 Pro, Game Designer direction)*
*Round: R12 — Phase 0 Frozen Review*
*Prior review: R11 (10 concerns, 3 HIGH)*
