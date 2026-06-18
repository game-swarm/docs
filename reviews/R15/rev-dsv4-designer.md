# R15 — Game Design Review (DSV4)

**Reviewer**: Game Designer — DeepSeek V4 Pro  
**Date**: 2026-06-18  
**Phase**: 1 (Clean-Slate, Design-Phase — no implementation concerns)  
**Documents Reviewed**:
- design/README.md, design/gameplay.md, design/modes.md, design/interface.md
- specs/gameplay/06-feedback-loop.md, specs/gameplay/08-api-idl.md

---

## Verdict: CONDITIONAL_APPROVE

The design is fundamentally sound and internally consistent across the 6 documents reviewed. The WASM-first deferred command model, configurable world rules engine, and dual-layer economy form a coherent strategic foundation. The issues below are **design-level concerns** — resolvable through tuning or rule augmentation without architectural change. None are blocker-class for design freeze.

---

## Strategy Depth Analysis

### Strategy Space Size

Swarm's strategy space is **multi-dimensional and combinatorially rich**:

| Axis | Variables | Order of Magnitude |
|------|-----------|---------------------|
| Body composition | 8+ part types × part counts (max 50) | ~10⁶ combinations |
| Deployment timing | code_update_cooldown × cost × propagation | ~3 decision points/hr |
| Logistics topology | Controller vs Depot placement × transport routes | ~N² (N = rooms) |
| Special attack selection | 8 attack types × target choice × timing | ~10³/tick |
| Diplomatic posture | 5 ally slots × ally/neutral per neighbor | ~2^N (N = neighbors) |
| PvE engagement | zone risk/reward gradient × NPC type mix | ~4 zones × 4 NPC types |

Total strategic complexity is roughly **O(2^rooms × 10^parts × 10^special-attacks)** — well above the threshold for meaningful optimization gameplay. This is not a solved game.

### Dominant Strategy Assessment

**I find no clearly dominant strategy in the current design**, but identify two potential convergence points:

1. **Turtling tendency**: Active_aging (110%) + ATTACK part lifespan penalty (-80) + Depot supply chain fragility → defensive play is structurally cheaper than offensive play. A "build economy, don't fight" strategy may dominate unless PvE resource pressure (Swarmling invasions, resource surge competition) forces engagement. Current countermeasures (soft_launch PvE-only phase, resource competition) are soft nudges, not structural incentives.

2. **Code iteration speed advantage**: code_update_cost defaults to 0, cooldown only 5 ticks. This means adaptive players can counter specific enemy strategies within 15-30 seconds of observation. While this rewards strategic intelligence (good), it may compress the strategy-meta cycle too fast — counters become near-instant, reducing the value of long-term planning and specialized builds.

### Information Asymmetry Quality

The fog-of-war design provides **adequate foundation** but lacks **gradient depth**:

- **Binary visibility**: Entities within range are fully visible; outside are fully invisible. Missing: detection range (I know something is there) vs identification range (I know what it is).
- **No stealth body part**: Without stealth, the information game is purely geometric (range calculation). A `Stealth` body part that reduces detection range would multiply strategic options.
- **Player_view=drone** is correct default — limiting human-view to drone perception prevents "satellite view" advantages that would undermine fog-of-war.

**Verdict**: Fog-of-war creates a legitimate information game, but it's a 2D chessboard without fog. Adding detection/identification range distinction would unlock deception strategies (feints, hidden reserves, ambushes).

### World PvE + PvP Incentive Structure

The PvE ecological layer is **well-calibrated** for its role:

- **PvE does not outperform PvP**: `max_pve_output_per_tick ≤ 30% of world regeneration` — the cap prevents PvE from becoming the optimal resource strategy.
- **Geography as difficulty**: Zone-based difficulty gradient avoids instance/queue systems. Correct decision.
- **Economic constraint on drops**: NPC drop economy is capped to prevent PvE farming dominance.

**One gap**: The cap is global (per-world), not per-player. A coordinated group of 5 players could monopolize the PvE cap, starving other players of PvE income entirely. Recommend a per-player sub-cap or diminishing returns on NPC kills per tick.

### AI + Human Nash Equilibrium

The core design principle — AI and humans share identical WASM sandbox paths — creates a **natural fairness equilibrium**:

- Same WASM module = same behavior regardless of author
- CPU metering (fuel, not wall-clock) equalizes compute budgets
- MCP is the AI's "screen" — no privileged API access

**Strategic implications**:
- AI agents cannot out-grind humans (same tick-based fuel budget)
- AI agents cannot access hidden information (same snapshot)
- AI agents CAN out-strategize humans (algorithmic optimization)
- Human advantage is in intuition and meta-level adaptation

This is a **well-designed Nash equilibrium**: the dominant strategy is "write better code," which is exactly Swarm's stated goal.

**One concern**: AI agents can deploy code faster (MCP `swarm_deploy` with programmatic iteration). With code_update_cost=0 and cooldown=5, an AI could test 12 strategies per minute. A human, even with CLI, manages ~2-3. This isn't unfair per se (same rules), but it means AI-to-human PvP inherently favors AI reaction speed in the code-update meta. For Arena (code locked at start), this concern disappears.

---

## Findings

### Critical Issues

**G1: Drone lifespan creates structural defensive bias**

- Lifespan 1500 tick (75 min real-time at 3s/tick) with active_aging 110% and ATTACK part -80 age_modifier
- Combat drones with ATTACK + MOVE parts: effective lifespan ≈ 1500 / 1.1 ≈ 1363 ticks, minus 80 = ~1283 ticks (64 min)
- Healer body part (age_modifier -30) further penalizes combat-support compositions
- Controller repair caps at 50% of natural aging → cannot indefinitely sustain drones
- **Effect**: Offensive expeditions require Depot supply chains. Offensive drone lifecycle risk (transport attrition + combat losses + aging) is substantially higher than defensive drone lifecycle risk (static Controller repair). This asymmetry, if unaddressed, will cause World mode to converge toward "turtle until soft_launch ends, then only fight when attacked."
- **Recommendation**: Consider reducing active_aging penalty or increasing Controller repair throughput for drones in rooms without enemy presence. Alternatively, add an "offensive_supply" body part or structure that reduces aging during combat operations.

**G2: Free deployment (code_update_cost=0 default) undermines strategic commitment**

- World mode default: code_update_cost=0, code_update_cooldown=5
- This means players can re-deploy counter strategies essentially instantly
- The strategic weight of "committing to a build" is lost — adaptation cost is zero
- **Game theory impact**: In a zero-cost strategy switch environment, the meta converges to rock-paper-scissors on 5-tick cycles. Long-term strategic planning (e.g., "I'll invest in Heavy+Claim for a control push in 200 ticks") is devalued because opponents can counter instantly.
- **Recommendation**: Set World default code_update_cost to a non-zero value (e.g., 200 Energy — equivalent to one basic drone). Keep code_update_cost=0 for Tutorial only. This introduces "Do I deploy now or save for drones?" as a meaningful strategic tradeoff.

### High Issues

**G3: PvE drop cap is global; lacks per-player gating**

- `max_pve_output_per_tick` is a global cap on total NPC drops per tick
- If 5 players are actively farming NPCs, they consume the cap; 20 other players get nothing
- This creates a "first-to-farm" race condition — not a strategic choice
- No mention of per-player diminishing returns or allocation mechanism
- **Recommendation**: Add `pve_output_per_player_share` (e.g., max 10% of global cap per player per tick) or implement diminishing returns: nth NPC killed by same player in same tick yields `base_drop × 0.8^n`.

**G4: `respawn_policy = "Ban"` contradicts MMO persistence philosophy**

- The design states World mode has "no end state — like MMO"
- But `respawn_policy = "Ban"` permanently removes a player from the world
- Combined with new_player_transfer_lock (500 tick), a banned player who creates a new account cannot rebuild quickly
- **Recommendation**: Either remove "Ban" as a respawn policy (replace with extended cooldown: "Timeout=10000 ticks"), or restrict it to opt-in hardcore worlds.

**G5: Arena PvE scoring ceiling is degenerate**

- Score efficiency = `min(1.0, par_time / actual_time)`
- Going faster than par_time yields ZERO additional score
- At high skill levels, players converge on "exactly par_time with maximum resource efficiency"
- This is a degenerate strategy space: the optimal play is precise timing, not speed optimization
- **Recommendation**: Change to `efficiency = par_time / actual_time` (no cap), or add a speed bonus: `speed_bonus = max(0, (par_time - actual_time) / par_time) × 100`.

**G6: No stealth/detection gradient in fog-of-war**

- Visibility is binary: visible or not visible
- No detection range vs identification range distinction
- No stealth body part, no sensor structure type beyond Observer
- **Recommendation**: Consider adding `Stealth` body part (reduces enemy detection range by 50% per part), `Sensor` structure (extends detection range, enables identification), and distinguishing "blip on radar" from "full entity data."

### Medium Issues

**G7: Drone-to-drone message payload limited to 256 bytes without justification**

- 256 bytes is enough for simple offers but insufficient for complex multi-resource negotiation protocols
- If messages are the foundation for decentralized trading, 256B may force protocol fragmentation
- **Recommendation**: Either justify 256B (bandwidth/per-tick overhead analysis) or increase to 512B.

**G8: Progressive storage tax starts too high (30% utilization threshold)**

- With default capacity 1,000,000, a player can hold 300,000 tax-free
- At 3,000 Energy/day from sources, reaching 300,000 takes ~100 days of pure accumulation
- The tax is effectively inactive for the first 3 months of a vanilla world
- **Recommendation**: Lower first-tier threshold to 15% for vanilla, keeping 30% as a per-world configurable.

**G9: Coordinated Overload attack can permanently cripple a player**

- Overload: -500k fuel, global cooldown per target: 50 ticks
- 3 coordinated attackers: 1.5M fuel reduction in one tick
- Default MAX_FUEL = 10M, floor = 2M (20%)
- But if fuel is already at 8M from normal operations, a 3-player Overload burst drops it below the recoverable range
- Fuel recovery: budget/1000 per tick (at 2M floor: 2,000/tick; at 8M: 8,000/tick)
- With per-drone cooldown of 200, a dedicated Overload team can keep a target at fuel floor indefinitely
- **Recommendation**: Add per-source Overload diminishing returns: same target hit by same player within N ticks → effect multiplied by 0.5^count.

**G10: Empire upkeep superlinear coefficient is effectively disabled in vanilla**

- Document self-admits: room_superlinear default = 1 (0.0001) → "nearly linear"
- Anti-snowball mechanism exists on paper but has negligible effect
- 50-room empire pays ~50 × 0.0001 × 50² ≈ 12.5 additional Energy/tick (vs 2,500 from linear terms)
- **Recommendation**: Either increase vanilla default to 100 (0.01) for meaningful anti-snowball, or rename the parameter to clarify it's intentionally weak for MVP.

### Low Issues

**G11: Alliance cap of 5 is arbitrary**

- No design rationale for cap of 5 vs 3 or 10
- With 5 allies, a player can cover 6 total participants — enough for small-team coordination but not large-scale alliances
- **Recommendation**: Add a brief justification in the design doc, or make it world-configurable.

**G12: Drone personality is purely cosmetic — wasted design surface**

- Four personality dimensions generated deterministically but affecting only animations
- This is a missed opportunity for soft strategic differentiation
- Example: High-curiosity drones could have +1 detection range but -10% harvest efficiency; high-aggression drones could deal +5% damage but take +10% damage
- **Recommendation**: Keep as cosmetic for MVP, but document as a future strategic expansion point.

**G13: PvE difficulty gradient is uniform radial "onion"**

- Zone 1→4 progression is linear with distance from center
- No terrain-based variation (e.g., a mountain pass zone with fewer but tougher NPCs)
- Expansion strategy is identical in all directions
- **Recommendation**: Add terrain-type modifiers to NPC spawn rates for strategic variety.

---

## Strengths

1. **WASM-first deferred command model is architecturally brilliant**: "Code is your army — write once, fight forever" is not just marketing. The separation of "what you see" (snapshot) from "what you do" (Command[]) with engine-side validation is the correct abstraction for a programming game.

2. **World.toml as game definition language**: Making resources, body parts, damage types, and special attacks all configurable through TOML — not hardcoded — transforms Swarm from "a game" to "a game platform." This is Screeps's killer missing feature.

3. **Dual-layer economy (global vs local storage)**: The 1%/5% transfer cost with transport delay creates genuine logistics depth. Mode C (hardcore: no global storage) transforms the game into Factorio-style logistics optimization — and it's just a config flag.

4. **Controller vs Depot age repair dichotomy**: Controller = free but limited throughput; Depot = unlimited throughput but costs resources. The 6-adjacent-cell queuing constraint creates spatial logistics puzzles. This is elegant game design.

5. **Neutral state after Hack**: 5-tick control lock → Neutral (idle, no lifespan consumption, immune to re-Hack). This is carefully balanced — it's a temporary disable, not permanent theft. The Disrupt/Fortify counterplay chain creates a mini-meta within the special attack system.

6. **AI-human fairness via identical sandbox**: MCP is the AI's "screen and mouse." No privileged API. AI writes WASM, same as humans. Fuel metering (not wall-clock) equalizes compute. This is the correct approach to AI integration.

7. **PvE as geography, not instances**: Zone-based NPC difficulty (center=easy, border=hard) eliminates instance matching, queue systems, and artificial "dungeon entrances." Player expansion naturally discovers harder content.

8. **soft_launch transition design**: 500-tick safe_mode → 1500-tick PvE-only → full PvP with 50-tick warning broadcast. This is a well-paced onboarding curve that doesn't infantilize players — they experience PvE pressure before PvP pressure.

9. **Drone-to-drone untrusted messaging**: Making message protocol enforcement the PLAYER'S responsibility (engine only guarantees delivery) creates genuine game-theory depth. Players must design reputation systems, escrow protocols, or trust networks.

10. **Special attack progressive unlock**: Tutorial/Novice = disabled; Standard = all 8; Advanced = +custom. Prevents new-player information overload while providing escalating strategic depth.

11. **Deterministic replay with full state checksum**: Blake3 PRNG + indexmap ordering + fixed ECS chain + state_checksum in TickTrace. This is comprehensive determinism engineering — not just "we use seeds."

12. **Move-as-action (not OOP method)**: The IDL's `Move { object_id, direction }` model — where Move is a Command, not a drone method — is correct for a deferred command system. Every action is a discrete decision point, enabling per-command validation and rejection with structured error reasons.

---

## CrossCheck — Inter-Direction Concerns

These are issues I suspect exist but cannot verify from my document subset. They require inspection by other reviewers:

- **CX1: Code propagation model may have edge cases with dynamic fog-of-war** — If `code_propagation_speed > 0` (gradual propagation) and a drone moves into a room where code hasn't propagated, does it run old code or go idle? → Suggest **Architect** check propagation boundary behavior during room transitions.

- **CX2: Snapshot size scaling with drone count may hit per-player 256KB cap** — 50 max body parts per drone × 8+ fields × protobuf/JSON serialization. A full 50-drone army with full state may approach the budget. → Suggest **Performance** reviewer calculate worst-case snapshot size for max drone+structure configurations.

- **CX3: Mod integrity hash (mods.lock checksum) and dynamic SDK generation pipeline** — The design says SDK is generated at engine startup from world.toml + mods. If a mod updates (new commit → new manifest_hash), all deployed WASM modules become invalid ("SDK mismatch"). Is there a migration/transition period? → Suggest **Architect** review the mod version upgrade path for active worlds.

- **CX4: Economic governance contract (PoW register difficulty) assumes CPU-based attack cost** — The analysis cites "$0.10 per 1000 accounts (CPU only)" but attackers with access to GPU/ASIC PoW solvers would have dramatically lower costs. Blake3 is fast on GPU. → Suggest **Security** reviewer assess GPU/ASIC attack economics for account creation at scale.

- **CX5: spectate_delay prevents real-time information leaks but breaks real-time spectator experience** — 100-tick delay at 3s/tick = 5-minute delay. This is a tradeoff: competitive integrity vs viewer engagement. → Suggest **UX/Experience** reviewer assess acceptable delay range for different Arena visibility modes.

- **CX6: Empire upkeep runs in Rhai (global view) while WASM runs in player snapshot (fog-of-war filtered)** — The document notes this asymmetry (Rhai sees everything) but doesn't address whether Rhai mods could accidentally leak information through events/notifications visible to players. → Suggest **Security** reviewer verify that Rhai `emit_event` cannot expose fog-of-war-hidden data.

---

*End of Game Design Review — rev-dsv4-designer*
