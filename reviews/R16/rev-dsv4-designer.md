# R16 Game Design Review — Designer (DSV4 Pro)

**Veridct: CONDITIONAL_APPROVE**

> Clean-slate review of R16 Phase 1 design documents. Evaluated from game design perspective: strategy depth, dominant-strategy analysis, fairness, motivational architecture, feedback-loop integrity, and PvE/PvP incentive alignment.

---

## Strategy Depth Analysis

### Strategic Space

Swarm's strategy space is **exceptionally rich** for a programming-RTS. The deferred command model (`tick(snapshot) → Command[]`) combined with:

- **8 body part types** (MOVE, WORK, CARRY, ATTACK, RANGED_ATTACK, HEAL, CLAIM, TOUGH) with configurable costs and age_modifiers
- **13 structure types** across 6 functional categories (core/storage/defense/production/logistics/intel)
- **8 special attack types** (Hack, Drain, Overload, Debilitate, Disrupt, Fortify, Leech, Fabricate) with distinct cooldowns and resource costs
- **6 damage types** with multiplicative resistance system (body-part × attribute)
- **3 logistics modes** (A: no-cost global, B: light logistics with transfer tax, C: hardcore local-only)
- **Controller vs Forward Depot** age-repair duality creating supply-line gameplay

...yields a combinatorial strategy space of approximately `N_body_configs × N_structure_choices × N_attack_strategies × N_logistics_setups` — well beyond human exhaustive optimization. This is exactly what a programming game should offer: no solved meta.

### Dominant Strategy Check

I analyzed for potential dominant strategies:

| Strategy Concern | Mitigation | Verdict |
|---|---|---|
| Defensive turtling (build walls, wait) | Empire upkeep (O(n²) rooms), drone lifespan decay, active_aging penalty. Can't sit forever. | **Mitigated** |
| Zerg rush (spam cheap drones) | Room drone cap (50→500), spawn cooldown, body_cost scaling. SpawnGrace 1-tick prevents spawn-camping. | **Mitigated** |
| Economic monopoly (hoard global storage) | Progressive storage tax (0→20 bp), global↔local transfer delay (no teleport), local storage stealth advantage | **Mitigated** |
| Hack-spam (chain-hack all enemies) | 200-tick global cooldown, Psionic resistance, Disrupt/Fortify counters, Neutral recovery immunity | **Mitigated** |
| Overload denial (starve everyone's fuel) | 50-tick global target cooldown, EMP resistance, Fortify cleanse, MAX_FUEL×0.2 floor | **Mitigated** |

**One potential gap**: Defensive play with Controller+Depot repair infrastructure combined with Fortify (100-tick shield, all resistances ×0.5, cleanse all debuffs) could create an extremely durable defensive posture. Fortify costs 400 Energy with 300-tick cooldown — cheap relative to the protection it provides. In a world where ATTACK body parts carry -80 age_modifier (dying faster, needing more repair trips), aggressive play is double-penalized: combat drones die sooner AND defending drones sit safely under Controller repair. This asymmetry warrants monitoring but doesn't reach dominant-strategy level given the counterplay options (Hack bypasses HP entirely, Drain attacks economic base, Disrupt at 50-tick CD can break Fortify cycles).

### Information Asymmetry

The fog-of-war design is well-layered:

```
Layer 1: drone perception (fog_of_war → snapshot filtering)
Layer 2: player view (drone | allied | full)
Layer 3: spectator delay (0 to N ticks)
Layer 4: safe hint ladder (competitive | practice | training)
```

The `NotVisibleOrNotFound` merged error code is a **strong design decision** — prevents oracle attacks where different error codes reveal entity existence. The Safe Hint Ladder (§snapshot-contract §4) is well-designed: competitive mode errors contain zero dynamic values, preventing information leakage through error messages.

**Concern (Medium)**: The public_spectate interaction with player_view isn't fully specified. When `player_view = "drone"` and `public_spectate = true` with `spectate_delay = 0`, does the spectator see:
- (a) The drone's limited perception? (fair, no info leak)
- (b) The full map? (info leak if spectators can communicate with players)

The spec needs to clarify this interaction explicitly.

---

## Findings

### Strengths

1. **Configurable World Engine**: The `world.toml` → ECS Plugin model is excellent. Not hardcoding game content (body parts, structures, damage types, resources) into the engine is the right architectural choice — every server operator can create a unique rule set without forking the engine. The Vanilla defaults provide sensible baselines.

2. **Global↔Local Storage Duality**: The two-layer resource model (global storage = abstract economic power, local storage = physical, vulnerable, requires logistics) creates genuine strategic tension. Mode B (light logistics with 1%/5% transfer tax) as default is well-calibrated — enough friction to matter, not so much as to punish.

3. **Deferred Command Model**: `tick(snapshot) → Command[]` with all mutating operations going through engine validation is the correct design for a programming game. It prevents WASM modules from directly manipulating world state, enables deterministic replay, and creates a clean AI/human parity path.

4. **Progressive Storage Tax**: The tiered tax (0bp at 0-30%, 1bp at 30-60%, 5bp at 60-85%, 20bp at 85-100%) creates a soft ceiling on hoarding without a hard cap. Combined with local storage stealth (enemies can't see your real reserves until they scout/attack), this produces interesting economic gameplay.

5. **Controller vs Forward Depot**: The age-repair duality is a standout tactical element. Controllers provide free repair but limited range/capacity per RCL; Depots provide frontline repair at resource cost. This creates genuine supply-line gameplay — cut the depot, and frontline drones die. This mechanic alone generates emergent strategic depth.

6. **PvE as Persistent World Layer**: NPCs as geography rather than instanced content is the right model for an MMO. Difficulty gradient by distance from center (Zone 1-4) creates natural progression. Deterministic event triggers via Blake3 seed ensure replay consistency.

7. **Diplomacy State Machine**: Clean state transitions (neutral → pending → allied → broken) with 72h timeout, 24h break cooldown, and detailed allied privileges (visibility, no friendly fire, direct transfers, shared intel). The 5-alliance cap prevents mega-coalition dominance while enabling meaningful cooperation.

8. **Deterministic Snapshot Truncation**: The distance-bucket → entity_id lexicographic ordering with critical-entity protection (own drone, controller, target, allies, attackers) is well-specified. Competitive mode's tick-degraded marking when actionable entities are truncated is a thoughtful competitive-integrity feature.

9. **OverloadPressure Visibility Model**: Exposing overload contributions only from visible sources prevents reverse-locating hidden attackers. The three-tier visibility (attacker sees own contribution + total, defender sees total + visible sources, third parties see only visible entities) is correctly designed.

10. **Drone Personality System**: Cosmetic-only personality traits (aggression, curiosity, loyalty, efficiency) generated deterministically from Blake3 seeds — adds character without affecting gameplay. Good for player attachment and streaming/spectating content.

11. **Drone-to-Drone Messaging**: Point-to-point 256B payload messages with untrusted protocol semantics create a genuine game theory layer. Players must design trustworthy exchange protocols or accept the risk of betrayal — this is emergent gameplay gold.

12. **Economic Feedback Dashboard**: Real-time energy flow, storage utilization, efficiency metrics, idle drone warnings, and tax-tier predictions — gives both human and AI players the information needed for macro-level decision making. The 10/tick independent quota for economic MCP queries is correctly separated from gameplay MCP.

### Concerns

#### G1 [Critical] — World Mode Motivation Vacuum

World mode is described as having **no victory conditions** — "类似 MMO 持续沙盒，玩家自行设定目标。不存在'游戏结束'状态。" While this is philosophically valid for a sandbox, the design provides **insufficient structured motivation** for the persistent world.

The "Long-term Goal System" (§gameplay.md anti-snowball section) lists: Colony Age, GCL, RCL, Arena Rank, PvE Milestones, Replay/Spectating. But these are **tracking metrics, not incentives**:
- GCL and RCL have no stated rewards beyond unlocking buildings (which is a means, not an end)
- Colony age is purely cosmetic — what does a 10,000-tick colony get that a 100-tick colony doesn't?
- PvE milestones are undefined ("世界事件、NPC 据点攻克" — no reward structure)
- There's no progression system (tech tree, unlocks, tiers) that gives players something concrete to work toward

**Risk**: Without intermediate goals or structured progression, World mode risks the "Minecraft Creative Mode" problem — players join, build something, realize there's nothing to achieve, and leave. The gameplay loop needs "what am I building toward?" answered more concretely.

**Recommendation**: Define a minimal progression system that rewards time investment without creating insurmountable first-mover advantage:
- Colony age tiers (100 / 500 / 2000 / 5000 / 10000 ticks) unlock cosmetic variants (drone skins, room border colors, nameplate badges)
- GCL milestones grant incremental QoL improvements (slightly increased global storage cap per GCL level, additional drone memory per level)
- PvE milestones award non-tradeable badges/achievements visible in player profile

These are low-implementation-cost motivational hooks that don't impact competitive balance.

#### G2 [High] — Arena PvE Challenge Disconnected from World Mode Economy

The Arena PvE Challenge is explicitly isolated: "不影响 World 状态、不产出 World 资源、不消耗 World 资产。" This isolation is **correct for competitive integrity**, but creates a motivation gap:

- A World player who invests hours building an economic empire has **zero economic incentive** to engage with Arena PvE
- Arena PvE's only reward is a score on a scenario-specific leaderboard — no crossover visibility, reputation, or recognition
- The design states Arena PvE Challenge is "纯粹用于算法测试和排行榜竞争" — this is fine for AI agents testing algorithms, but human players need motivational bridges

**Recommendation**: Add cross-mode visibility:
- World player profile shows Arena PvE best scores (badge display)
- World mode could have optional "proving ground" rooms near spawn areas that link to Arena PvE scenarios — completing them unlocks cosmetic world decorations
- The Challenge Board (§snapshot-contract §3.4) correctly restricts to "bounty积分/称号" — extend this to World-mode-visible achievements

This creates motivation without violating the economic isolation contract.

#### G3 [High] — Sharp Tax Tier Jump May Create Perverse Incentives

The storage tax jumps from 5bp to 20bp at the 85%→100% boundary (4× increase). At 1,000,000 capacity, holding at 95% means 200 Energy/tick in tax. This creates a **strong incentive to stay below 85% at all costs** — players will:
- Constantly spend to avoid the tax bracket (potentially wasteful spending)
- Convert global→local just to dodge the tax (creating artificial logistics churn)
- Never actually use storage as "strategic reserve" (defeating its purpose)

The 20bp tier (0.2%/tick) depletes a full 1M storage in 500 ticks — about 25 minutes at 3s/tick. This is aggressive enough that the top bracket effectively doesn't exist as usable storage.

**Recommendation**: Smooth the tax curve. Instead of a sharp jump from 5bp to 20bp, consider a continuous or more granular tiered approach:
- 85-92%: 7bp
- 92-97%: 12bp  
- 97-100%: 20bp

Or implement a continuous formula: `tax_rate = max(0, (utilization - 0.30) ^ 2 * 0.40)` producing a smooth quadratic curve. This preserves the anti-hoarding function while making the 85-100% range usable.

#### G4 [High] — Defensive Play Bias: Lifespan + Repair + Fortify Interaction

Three mechanics combine to create a potential defensive dominant strategy:

1. **Attack body parts have -80 age_modifier** → combat drones die ~5% faster naturally
2. **Active aging at 110%** → combat drones (always executing commands) age faster than defending drones at repair stations
3. **Controller repair cap at 50% of natural aging** → repairing never fully counteracts aging
4. **Fortify (300 tick CD, 400 Energy)**: 100-tick shield with all resistances ×0.5 + full debuff cleanse

A defending player with Controllers + Depots + periodic Fortify application creates a **repair fortress** where defending drones effectively live indefinitely while attacking drones die from aging during the approach march. This is exacerbated by:
- Attackers need ATTACK/RANGED_ATTACK parts (-80/-50 age_modifier)
- Defenders can use TOUGH parts (+100 age_modifier) for durability
- Defenders sit within Controller repair range (free, capacity-gated)
- Attackers must cross distance buckets while aging at 110%

The combined effect: **aggressive play is triple-penalized** (age penalty, aging rate, repair distance) while defensive play gets triple-rewarded.

**Recommendation**: 
- Reduce ATTACK age_modifier from -80 to -40 and RANGED_ATTACK from -50 to -25
- Or: add a "repair surge" mechanic — drones returning from combat (having dealt damage in the last 20 ticks) get +50% repair rate for 10 ticks
- Or: make Fortify's resistance multiplier configurable per world tier, with Standard default at ×0.7 instead of ×0.5

#### G5 [Medium] — World Mode Competitive Signaling Contradiction

The core modes.md document states World mode has "无排行榜" because "持久世界天然不公平（老玩家先发优势）."

The feedback-loop spec (§6) then states World mode has "趣味展示（非竞争排名）：殖民地年龄、GCL、房间数——仅供观赏."

These statements contradict: "仅供观赏" rankings are still rankings. The design needs to commit to one position:

**Option A**: No rankings, pure sandbox — remove the "趣味展示" reference
**Option B**: Cosmetic rankings with explicit "not competitive" labeling — define what's displayed

I recommend **Option B** with clear boundaries: display GCL/colony age/rooms explored in player profiles with an explicit disclaimer "World mode does not have competitive rankings. These metrics are for community interest only." This preserves engagement value without creating toxic competition.

#### G6 [Medium] — Spectator Visibility Contract Gap

The visibility configuration table shows combinations of `fog_of_war`, `player_view`, `public_spectate`, and `spectate_delay`. But the spectator's actual rendered view isn't specified:

When `public_spectate = true` and `spectate_delay = 0`:
- Does the spectator see the **drone's perspective** (respecting `player_view = "drone"`)? This is the safe default.
- Does the spectator see the **full map**? If so, with what delay, and how is this communicated to players?

If a spectator can see the full map in real-time while players are limited to drone vision, external communication (Discord, Twitch chat) could leak information. The `spectate_delay` parameter mitigates this, but `spectate_delay = 0` is the default for tutorial worlds and the interaction needs explicit specification.

**Recommendation**: Add a `spectator_view_mode` rule with options: `"player_perspective"` (default, sees what the player sees), `"delayed_full"` (sees full map at spectate_delay), `"delayed_dual"` (toggle between perspectives, delayed). Document the information leak boundary explicitly.

#### G7 [Medium] — Drone Messaging Protocol Attack Surface

The drone-to-drone messaging system (§8.9) explicitly states: "引擎不校验 payload 语义，仅保证消息已投递" and "不可信协议（Game Theory Element）" — untrusted by design. This is a valid game theory layer, but the spec doesn't address the **denial-of-service** surface:

- A malicious drone can send 100 messages/tick filling every recipient's 256B buffer
- Message payloads of 256B are processed into receiver's snapshot — what's the per-drone message cap?
- Can a drone flood an enemy's snapshot with garbage messages to cause truncation of actual game state?

**Recommendation**: Add per-drone message reception caps:
- Max 10 messages received per drone per tick (excess silently dropped)
- Messages count toward snapshot size budget — if truncation occurs, excess messages are in the `omitted_categories.events` bucket
- Message payload processing has a constant-time budget (no parsing loops)

#### G8 [Low] — Idle Curiosity Movement Breaks "Cosmetic Only" Contract

The drone personality system states: "人格不影响 gameplay 数值——纯表现." However, `curiosity` personality causes drones to "idle 时在出生点附近小范围随机游走（半径 `curiosity × 5` 格）."

Random drift movement **is gameplay-impacting**:
- Drone position changes → visibility changes → potential enemy detection
- Drone moves out of Controller repair range → ages faster
- Drone moves into enemy patrol path → gets attacked

While 5-cell radius is small, the contract violation is philosophical: either movement is cosmetic (and shouldn't change position) or it's gameplay (and should be documented as such).

**Recommendation**: Either:
- Make idle movement purely animation-based (drone bounces in place, rotation, particle effects) — no position change
- Or: document curiosity as a gameplay mechanic with a clear warning: "curiosity causes minor position drift — this IS gameplay-relevant"

#### G9 [Low] — Fabricate Action Requires `Matter` Resource But Vanilla Default is Energy-Only

The Fabricate custom action costs `{ Energy = 2000, Matter = 500 }` but the Vanilla ruleset defaults to **single-resource Economy** (`Energy` only). At Standard world tier, Fabricate is enabled but Matter doesn't exist in the default world — making the action unusable.

**Recommendation**: Either:
- Add Matter as a secondary Vanilla resource (with source_types for MatterDeposit)
- Or: change Fabricate's default cost to Energy-only (e.g., `{ Energy = 5000 }`)
- Or: make Fabricate require explicit server operator opt-in with resource configuration

#### G10 [Low] — Code Update Cost Documentation Inconsistency

The `code_update_cost` parameter is documented as:
- Default: `{ Energy: 0 }` (free) in the rules table
- Example value: `{ Energy: 500 }` in the world.toml example at line 1241
- Example value: `{ Crystal: 500 }` in the custom resource example at line 502

The example using `Crystal` (a non-default resource) while the parameter is documented as `ResourceCost` type with `Energy` default is confusing. New server operators might copy the Crystal example without defining Crystal resources.

**Recommendation**: Consistently use `Energy` in all documentation examples, or add a note: "this example assumes a world with Crystal resource type defined."

---

## Cross-Check — Needs Cross-Direction Verification

The following items require verification from other reviewer perspectives:

| # | Item | Cross-Check With | Question |
|---|------|-----------------|----------|
| X1 | Snapshot truncation deterministic ordering: distance bucket → entity_id lexicographic. Are entity_ids guaranteed unique within a bucket? | Architect | Verify no collision cases where two entities share same distance bucket position and same entity_id (impossible by construction, but confirm). |
| X2 | Rhai mods run in-process with global view and `actions.*` capability. Trust model assumes "server operator vets mods." | Security | Is the actions white-list sufficient? `damage_entity` and `award_resource` are powerful — a compromised mod could destroy the economy. |
| X3 | New player transfer lock at 500 ticks with `same_origin_account_group_quota = 5`. | Economy | Is 500 ticks sufficient? At 3s/tick that's ~25 minutes. A determined Sybil attacker can batch-create accounts every 25 minutes. |
| X4 | Empire upkeep uses `fixed<u32,4>` precision for `room_superlinear`. At default value 1 (0.0001), the superlinear component is negligible at 50 rooms — the doc acknowledges this as intentional for MVP. | Economy | Is the default calibration too forgiving? MVP friendliness is good, but does this undermine the stated anti-snowball goal? |
| X5 | `code_update_cooldown` minimum is 5 ticks in World mode. Can players bypass by deploying to different drone groups? | Architect | Verify the cooldown is per-player, not per-drone. If per-drone, rapid redeployment across groups is possible. |
| X6 | `global_storage_tax_tiers` highest tier at 20bp minimum per safety lower bound. At 20bp, 1M storage depletes in 500 ticks (~25 min). | Economy | Is this depletion rate intentional? It effectively caps usable storage at ~85% — verify this matches economic design intent. |

---

## Summary

The R16 design represents a **mature, well-thought-out game design** with strong foundations in configurable game mechanics, deterministic execution, and dual human/AI parity. The deferred command model, Controller/Depot repair duality, and progressive storage tax are particularly elegant designs. The feedback loop (LEARN→DECIDE→ACT→UNDERSTAND) is well-specified with concrete acceptance criteria.

**Key risks to address before implementation**:
1. World mode needs at least a minimal progression/reward structure (G1)
2. The defensive play bias from combined aging + repair + Fortify mechanics warrants parameter tuning before MVP balance testing (G4)
3. The arena↔world motivation bridge needs definition to prevent Arena PvE from becoming dead content (G2)

**Verdict: CONDITIONAL_APPROVE** — The design is sound and implementation-ready for MVP scope with the above concerns addressed during Phase 2 refinement.
