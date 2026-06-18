# Game Designer Review — Swarm R-appcert-R2

**Reviewer**: rev-dsv4-designer (博弈论/策略深度/算法公平性)
**Date**: 2026-06-18
**Scope**: Clean-slate review of 25 design documents. Design-phase review — no phased implementation consideration. Suitable solutions adopted directly regardless of implementation difficulty.

---

## Verdict: CONDITIONAL_APPROVE

The design demonstrates strong game design fundamentals: fairness-by-architecture (WASM sandbox + fuel metering), meaningful information asymmetry (fog-of-war + oracle defenses), coherent anti-snowball mechanisms (progressive storage tax + drone lifespan + age maintenance logistics), and a well-structured dual-mode system (World/Arena) with clear incentive separation.

Two Conditional items (C1, C2) require resolution before the design can advance to implementation:

- **C1 (Medium)**: Anti-snowball for veteran players in World mode relies solely on drone lifespan and progressive storage tax — no territorial decay or empire upkeep exists. World mode's "no competitive ranking" philosophy is a design choice, not a mechanism. This must be acknowledged explicitly as accepted design debt.
- **C2 (Low)**: Overload's "静默结果" (result opacity) creates perverse incentives — attacker receives zero feedback whether fuel was successfully depleted or target was already at floor. Combined with 3-player Overload coordinate attack transparency gap, this may drive player frustration.

---

## Strategy Depth Analysis

### 1. Strategy Space Size

The strategy space is combinatorially deep:

| Dimension | Range | Notes |
|-----------|-------|-------|
| Body part composition | 8 part types × max 50 parts, order matters | `attack(5)+move(5)+tough(5)` vs `ranged(8)+move(3)+heal(3)` — different tactical roles. Body is irreversible, forcing ex-ante commitment |
| Special attack selection | 6-8 types with cooldowns | Hack (200t cooldown, 1000E cost) vs Drain (50t cooldown, 200E/tick) vs Overload (200t cooldown, 300E) — choice reflects strategic posture |
| Logistics topology | Controller vs Depot, global vs local storage | 3 logistics modes (no-logistics / light / hardcore) × transfer time + intercept-ability |
| Code deployment timing | cooldown + window + propagation | When to deploy vs when to hold — code_propagation_speed creates rollout delay |
| Room expansion path | ClaimController + contested mechanics | Progress investment is revealed and can be countered |

Estimated raw strategy space: >10^12 distinct combinations before considering reactive dynamics.

### 2. Dominant Strategy Analysis

**No global dominant strategy detected.** Key reasons:

- **Move-as-action** (engine.md §Phase 2a table): Moving costs the only per-drone action slot — `move_then_attack` vs `attack_then_move` is a genuine tradeoff. Traditional RTS "move+attack dual-action" would create a dominant strategy of "always move AND attack." Swarm's single-slot design eliminates this.
- **Seeded shuffle** (01-tick-protocol.md §3.1): Player command execution order randomized per tick — no "always go first" advantage exploitable.
- **Body irreversibility** (gameplay.md §Drone 身体规划): Parts cannot be changed post-spawn. Specialization commits you to a specific strategic role — generalist builds sacrifice depth for flexibility.
- **Special attack anti-synergy**: Hack (200t cooldown) and Drain (50t cooldown) compete for different body part requirements (CLAIM vs WORK+CARRY), preventing a single "best drone" build.

**Potential concern**: Fortify (TOUGH body, 300t cooldown, 400E) clearing all negative statuses + halving all resistances ×0.5 for 100 ticks could become a "must-have" in prolonged engagements. The 300-tick cooldown prevents spamming, but if PvP meta converges to Fortify-first engagements, it approaches dominant. Conditional on playtest data.

### 3. Information Asymmetry Assessment

**Excellent oracle defense design** (05-visibility.md §10):

- Overload returns `NotVisibleOrNotFound` for both "target doesn't exist" and "target not visible" — no information leakage through rejection codes
- `omitted_count` uses bucketed values ("few"/"some"/"many"/"extreme") instead of exact numbers — prevents entity-count oracle
- Special attack results: attacker cannot distinguish "target not found" from "target not visible" — unified `NotVisibleOrNotFound` code
- All query host functions filtered through `is_visible_to` — no bypass path for WASM modules

**Fog-of-war design**: Appropriate tiered visibility (self/room/hostile/market) with clear boundaries. The split between `player_view` (human screen) and WASM `tick()` input (always filtered) is correctly separated — prevents MCP agent information advantage.

**Weakness identified**: In Arena mode, fog-of-war is disabled entirely (07-world-rules.md §6: `visibility.fog_of_war = false`). This is correct for competitive fairness but eliminates strategic fog-of-war play in Arena — reducing Arena strategy depth compared to World mode. Acceptable for 1v1 fairness but worth noting.

### 4. PvE + PvP Incentive Correctness (World Mode)

**PvE-to-PvP transition is well-gated:**

```
Tick 0-500:     safe_mode (room invincible)
Tick 500-2000:  soft_launch (PvE only — NPC threats, resource surges)
Tick 2000+:      Full PvP enabled
```

**Correct incentive properties:**
- `max_pve_output_per_tick ≤ world_regen × 30%` (modes.md §NPC 掉落经济): Prevents NPC farming from overwhelming PvP strategic value
- NPC difficulty is geographic (zones 1-4 from center): Players self-select risk/reward through expansion, not through "dungeon queues"
- Resource Booms / Swarm Invasions / Merchant Arrivals: Deterministic event seeding creates shared PvE objectives that can catalyze PvP competition (everyone wants the Rich Vein at the same time)
- No PvE "boss drops" that trivialize PvP — Guardian blueprints are 5% drop rate and unlock recipes, not instant power

**One concern**: soft_launch at tick 2000 flips to full PvP. A player who joined at tick 1900 has only 100 ticks (5 min @ 3s/tick) of soft_launch before being thrown into combat. The 50-tick warning broadcast helps, but the first PvP encounter for late-joiners may still be jarring. Consider making soft_launch duration per-player instead of per-world (i.e., 1500 ticks after *individual* spawn).

### 5. AI ⇄ Human Nash Equilibrium

The design correctly treats AI agents and humans as equivalent participants:

| Property | Mechanism | Fairness Implication |
|----------|-----------|---------------------|
| Identical execution path | Both go through WASM sandbox | AI cannot cheat through direct API calls |
| Identical fuel budget | 10M fuel/tick for all players | AI computation advantage constrained by wasmtime fuel metering |
| Identical information access | Same `is_visible_to` filtering for MCP and WASM snapshot | Prevents AI information advantage |
| Identical deploy pipeline | AI uses `swarm_deploy` (MCP), human uses Web UI — same CodeSigningCertificate requirement | Same authentication and validation |

**Nash equilibrium**: Given that both sides have identical constraints, the equilibrium is determined by code quality alone — not by API access, not by wall-clock speed, not by information privilege. This is the strongest possible fairness guarantee for a programming game.

**AI agent specific concern**: The MCP `swarm_simulate` function (max 100 tick) gives AI agents an offline prediction capacity that human players lack without external tooling. Humans must use `swarm sim` CLI, which is equivalent in capability but requires separate setup. The 50M fuel/hour limit on simulate and 3 concurrent simulate cap provide reasonable bounds.

### 6. Anti-Snowball Mechanisms

| Mechanism | Strength | Coverage |
|-----------|----------|----------|
| **Drone lifespan** (1500 tick default) | Strong — all drones eventually die | Prevents infinite drone accumulation |
| **Active aging penalty** (+10% for active drones) | Medium — slight asymmetry | Prevents idle stockpiling |
| **Controller repair cap** (max 50% of natural age growth) | Strong — hard mathematical ceiling | Prevents multi-controller immortality |
| **Progressive storage tax** (0%→0.01%→0.05%→0.20%) | Strong — non-linear, self-correcting | Prevents resource hoarding / market manipulation |
| **Global→Local transfer time** (5-10 tick, interceptable) | Medium | Prevents instant teleport resupply |
| **Room drone cap** (50→500 by RCL) | Medium | Caps local force concentration |
| **Respawn = NewRoom** (density-prioritized) | Strong — loss of all colonies is a soft reset | Prevents spawn-camping elimination |
| **Overload** (fuel depletion attack) | Medium — temporary, recoverable at fuel/1000 per tick | Punishes over-concentration without permanent damage |
| **No World mode competitive ranking** | Weak — design choice, not mechanism | Old players with accumulated territory have permanent advantage |

**Missing anti-snowball**: No territorial upkeep/scaling cost exists (World mode explicitly defers this to phase 1+). A player who controls 50 rooms has the same per-room cost (other than proportional drone maintenance) as a player with 5 rooms. This is a legitimate design choice ("no empire upkeep") but should be explicitly acknowledged: in a persistent world without territorial decay, the rich get richer. The progressive storage tax addresses one symptom (resource hoarding) but not the root cause (unbounded territorial expansion).

This is acceptable for MVP (World mode has no competitive ranking), but must be addressed before any competitive World mode feature is added.

---

## Strengths

### S1: Fairness-by-Architecture
The WASM sandbox + fuel metering + `is_visible_to` filtering + seeded shuffle creates a system where code quality, not platform privilege, determines outcomes. AI and human players share identical constraints — a rare and valuable property.

### S2: Move-as-Action Design
Making Move consume the single per-drone action slot is philosophically coherent: Swarm is a *programming* game where strategic positioning matters, not a micro-heavy RTS. The elimination of dual-action ordering ambiguity simplifies determinism while adding genuine tactical depth.

### S3: Oracle Defense Architecture
The visibility system (05-visibility.md §10) is among the most thorough information-leakage defenses I've seen in game design documentation. Bucketed `omitted_count`, unified `NotVisibleOrNotFound` rejection codes, and the explicit enumeration of "attacker can never distinguish X from Y" scenarios demonstrate deep security thinking.

### S4: Logistics-as-Gameplay
The Controller-vs-Depot repair system (gameplay.md §后勤网络) creates genuine strategic logistics: forward depots require supply lines (CARRY drones must ferry resources), are capturable (offensive value), and create vulnerable chokepoints (defensive risk). This is Factorio-level logistics depth in an MMO context.

### S5: Progressive Storage Tax
The tiered tax (0%/0.01%/0.05%/0.20%) is a rare example of an economic anti-snowball mechanism that is both mathematically sound and game-design elegant. It doesn't cap wealth — it creates diminishing returns that naturally encourage spending over hoarding.

### S6: Seeded Shuffle with Forward-Secrecy Awareness
The shuffle protocol (01-tick-protocol.md §3.1) correctly acknowledges the forward-secrecy limitation of Blake3-based seed derivation and provides operational countermeasures (epoch bump, audit logging, seed rotation interval). The honest acknowledgment of the accepted risk model is commendable.

### S7: Dual-Mode Clean Separation
World mode (persistent sandbox, no ranking) and Arena mode (symmetric 1v1, competitive) have clearly distinct design philosophies with no feature leakage. The PvE Challenge mode in Arena provides a "safe" competitive outlet without World-mode baggage.

### S8: First-Hour Experience Design
The safe_mode → soft_launch → full PvP graduation (06-feedback-loop.md §2.4) is well-paced. Low-risk social conflicts (resource racing, room claiming, Arena challenges embedded in World UI) provide graduated exposure to competition before full PvP.

### S9: Certificate/Equipment UX
The multi-device certificate model with clear lifecycle (issue → use → renew → revoke) and device-level granularity (revoking one device doesn't lose all access) is well-designed. AI agent self-registration path with PoW challenge is practical. The "agent proxy registration" mode with handoff codes (not raw credentials) shows good security UX thinking.

---

## Concerns

### G1 (Medium): Overload Feedback Opacity

**Location**: 05-visibility.md §6.1, commands.md Overload entry

Overload is described as having "静默结果" — attacker receives zero indication whether fuel was actually depleted or target was already at floor. While this prevents oracle information leakage, it creates a perverse user experience:

1. Attacker spends 200t cooldown + 300E with *zero feedback* on effectiveness
2. Three players coordinating Overload on one target waste 2/3 of attacks if target already at floor — but nobody can tell
3. The only feedback mechanism is "observe whether target drones stop moving next tick" — which could be caused by many factors (code bug, fuel exhaustion from expensive operations, etc.)

**Recommendation**: Provide delayed feedback (tick+10 "intel report") with bucketed estimates: "target operations reduced significantly" vs "target operations unchanged." This preserves oracle defense timing while giving strategic feedback.

### G2 (Low): Concentrated Overload Attack Transparency

**Location**: commands.md Overload entry

Overload's per-target global cooldown of 50 ticks prevents rapid sequential Overload — but three attackers can each Overload once within the same 50-tick window, potentially depleting 1.5M fuel (3 × 500k) from a single target. With MAX_FUEL at 10M and floor at 2M (20%), this can disable a player in ~2.5 minutes of coordinated attack.

This is not broken (requires 3 players coordinating, consumes 900E + 3×200t cooldown each), but the target has **zero awareness** of Overload attacks (05-visibility.md §6.1: target "不可见: 谁执行的 Overload"). Combined with G1's feedback opacity, the target may attribute drone inactivity to code bugs rather than coordinated attack.

**Recommendation**: Target should receive notification: "Your fuel reserves are under attack" (without attacker attribution). This preserves attacker anonymity while giving target agency to respond (deploy fuel-efficient code, disperse drones, seek allies).

### G3 (Low): soft_launch Duration is Per-World, Not Per-Player

**Location**: 06-feedback-loop.md §2.4, gameplay.md Vanilla Ruleset table

soft_launch_phase of 1500 ticks is a world-level property. A player who joins at tick 1900 in a world with soft_launch ending at tick 2000 gets only 100 ticks of PvE protection before full PvP exposure. The system is "join at your own timing risk" which is philosophically consistent with World mode's "no fairness guarantee" design — but contradicts the "新手引导完整性" requirement.

**Recommendation**: Either (a) make soft_launch per-player (1500 ticks after individual first spawn) or (b) document this as acceptable World-mode asymmetry and provide enhanced warnings for late-joiners.

### G4 (Low): Arena Lacks Fog-of-War Strategic Depth

**Location**: 07-world-rules.md §6: `visibility.fog_of_war = false` for Arena

Arena disables fog-of-war entirely for competitive fairness. While correct for symmetric-information 1v1, this removes an entire layer of strategic depth (scouting, hidden builds, surprise attacks) that exists in World mode. Arena strategy reduces to pure build-order and micro-optimization without the spatial information game.

**Recommendation**: Consider an optional "Blind Arena" mode with fog-of-war enabled — symmetrical but unknown. This would test a different strategic dimension and appeal to players who prefer the World mode's fog-of-war gameplay.

### G5 (Low): Empire Upkeep Explicitly Deferred

**Location**: modes.md §9 table: "领土平衡: ⚠️ Phase 1+ deferred"

The lack of territorial scaling costs creates an acknowledged snowball risk in World mode. The design acknowledges this as "服主可通过 world.toml 自定义扩张成本" and "empire-upkeep is a Rhai mod (version 1.2.0)." However, the vanilla ruleset ships without it. World mode without empire upkeep means territorial expansion has no diminishing returns.

**Recommendation**: Either ship empire-upkeep as a default-enabled mod in the vanilla ruleset, or add an explicit note in the World mode documentation: "This world has no territorial scaling costs. Large empires will dominate small ones. This is by design."

### G6 (Low): New Player Onboarding Assumes Code Literacy

**Location**: GETTING-STARTED.md, 06-feedback-loop.md §2.1

The 5-minute tutorial assumes the player can read and modify TypeScript code. For non-programmers attracted by the "编程竞技场" concept, the TypeScript syntax barrier is absolute. The Starter Bot (basic-harvester) mitigates this ("run what we give you"), but modification requires code literacy.

**Recommendation**: Add a "visual rule editor" for non-coders — drag-and-drop behavior blocks (if source nearby → harvest, else → move toward source). This keeps the "code is your army" philosophy while broadening the audience.

---

## Missing

### M1: Drone Personality / Individual Identity System

Drone are interchangeable units identified only by `entity_id`. In a programming game where players invest code into drone behavior, there's no mechanism for drone individuality — naming, achievements, kill counts, or behavioral specialization visible in UI. Screeps' "creep memory" provided this; Swarm's `env_vars` exist but are purely functional (no display layer).

**Impact**: Reduces emotional attachment to units, which drives retention in MMO-style games.

### M2: Diplomacy / Alliance Primitives

The design has no alliance, non-aggression pact, or shared-vision mechanics. World mode is pure anarchy — every other player is a potential enemy with no formal cooperation paths. The market system is the only inter-player coordination mechanism.

**Impact**: World mode lacks the social layer that sustains MMO persistence. Without alliance mechanics, large-scale cooperation is purely ad-hoc and trust-based.

### M3: Drone Behavior Visualization (Spectator UX)

The replay/spectator system (05-visibility.md §3.5-3.6) describes data visibility but not behavioral visualization. Spectators can see entity positions and HP but cannot see *what strategies are being executed* — no code overlay, no "intent arrows," no strategy annotation layer.

**Impact**: Spectator experience is purely positional — misses the "oh, that's clever code" moment that makes programming competitions watchable.

### M4: Player-Driven Economy Feedback Loop

The market system (CreateMarketOrder, BuyMarketOrder) is present but described purely as infrastructure. Missing: how does market activity affect world economy? Can resource oversupply crash prices? Is there price discovery or fixed-price only? The answer is "world.toml configurable" — this is a gap, not flexibility.

---

## Certificate / Equipment UX Assessment

**Overall: Strong.** The multi-device certificate model with per-device lifecycle management is well-designed. Specific observations:

- **Device-level granularity** (auth.md §5.5): Revoking one device's certificate doesn't lose all access — correct for user trust.
- **AI agent self-registration** (auth.md §4.2): PoW challenge → CSR → certificate bundle flow works without browser — essential for headless AI players.
- **Agent proxy registration** (auth.md §4.3): Human can say "register me" to AI agent, agent handles CSR/PoW, returns handoff code — good UX for non-technical players.
- **Credential storage guidance** (auth.md §4.2): Explicit "禁止把私钥写入代码仓库、公开日志或聊天上下文" — correct security posture communication.
- **Certificate expiration UX** (auth.md §10.9): MCP response headers + SSE events for expiry warnings — proactive, well-designed.

**One UX gap**: No "certificate health dashboard." A player with 5 devices should see at a glance: which certificates are active, expiring soon, and which devices haven't been used recently. Currently this requires manual `swarm_list_certificates` calls and parsing.

---

## Summary

| Dimension | Rating | Notes |
|-----------|--------|-------|
| Strategy Depth | ★★★★★ | Combinatorial body × attack × logistics space. No dominant strategy detected. |
| Information Asymmetry | ★★★★★ | Thorough oracle defense. Unified rejection codes. Bucketed visibility data. |
| Anti-Snowball | ★★★★☆ | Strong economic mechanisms (tax, lifespan). Missing territorial scaling. |
| New Player Guidance | ★★★★☆ | Well-paced safe_mode→soft_launch→PvP graduation. Code-literacy barrier. |
| Certificate UX | ★★★★☆ | Multi-device model well-designed. Missing dashboard view. |
| AI-Human Fairness | ★★★★★ | Identical sandbox, fuel, visibility, and deploy path — no asymmetry. |
| PvE/PvP Balance | ★★★★☆ | Geographic PvE difficulty. NPC output capped. soft_launch timing concern. |

**Outcome**: CONDITIONAL_APPROVE — Proceed with implementation after addressing C1 (acknowledge territorial snowball as accepted design debt) and C2 (consider delayed Overload feedback). All other concerns are Low severity and non-blocking.
