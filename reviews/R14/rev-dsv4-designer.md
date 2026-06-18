# R14 Game Design Review — rev-dsv4-designer

**Reviewer**: Game Designer (DeepSeek V4 Pro)
**Date**: 2026-06-18
**Phase**: Phase 1 Clean-Slate Independent Review
**Documents Reviewed**: design/README.md, design/gameplay.md, design/modes.md, design/interface.md, specs/gameplay/06-feedback-loop.md, specs/gameplay/08-api-idl.md

---

## 1. Verdict

**CONDITIONAL_APPROVE**

The design is fundamentally sound with a clear vision and excellent structural integrity. The "code is your army" philosophy, WASM-based fairness model, and configurable world rules engine are standout achievements. However, there are gaps in the resistance/damage-type depth, economic incentive design, and some specification inconsistencies that should be resolved before implementation begins. These are fixable within the design phase and do not require fundamental rethinking.

---

## 2. Strengths

**S1 — WASM-Path Fairness is Architecturally Elegant**
The design's strongest game design feature is that AI agents and human players use the identical WASM→sandbox→deferred command path. This isn't a policy enforced by moderation — it's a structural property of the engine. No AI-specific shortcuts exist. This makes the fairness guarantee self-enforcing and eliminates an entire class of balance complaints that plague other programmable games.

**S2 — Configurable World Rules Engine is Platform-Defining**
Transforming Swarm from "a game" to "a game engine platform" through `world.toml` configurability (body parts, damage types, resources, structures, special attacks — all declared, not hardcoded) is the single most important design decision. It enables infinite variety while preserving the core WASM programming loop. The ResourceRegistry abstraction (`HashMap<ResourceName, Amount>`) with no hardcoded "Energy" is technically clean and gameplay-correct.

**S3 — Dual-Mode Design (World + Arena) Resolves a Classic Tension**
World mode optimizes for persistence, emergence, and asymmetric creativity. Arena mode optimizes for competitive fairness with symmetric starts and locked WASM. Rather than compromising one to serve the other, the design embraces both as first-class citizens with different rule defaults. This is the correct call.

**S4 — Onboarding and Feedback Loop Design is Exceptionally Thorough**
The 10-minute golden path, CI-smoke-tested starter bots, per-tick command explanation with suggestions, gradual threat curve (safe_mode→soft_launch→full PvP), and MCP-side "deploy_accepted + first_tick_executed" event push show deep empathy for both human and AI player psychology. The feedback loop doc's LEARN→DECIDE→ACT→UNDERSTAND cycle is exactly the right framework.

**S5 — Anti-Dominant-Strategy Measures Show Sophisticated Economic Thinking**
Progressive storage tax (0bp at 0-30%, 20bp at 85-100%), superlinear empire upkeep, controller age hard cap at 50% of natural growth, and the global↔local transfer time delays (no teleport) collectively create diminishing returns on hoarding and expansion. The "运输期间资源可被敌方巡逻 drone 拦截" detail is particularly elegant — it makes logistics a tactical vulnerability, not just a cost.

**S6 — Drone-to-Drone Messaging with Untrusted Protocol Enables Meta-Game**
The peer-to-peer message system (256B payload, visibility-constrained delivery, silent drop on failure) with explicit acknowledgment that "引擎不校验 payload 语义" creates a trust-and-reputation meta-game. Players must design their own credible exchange protocols — this is emergent gameplay gold.

**S7 — Special Attack System with Progressive Unlock Creates Natural Skill Progression**
Eight special attacks, with Tutorial/Novice worlds disabling all of them and Standard/Advanced enabling progressively more, creates a natural difficulty curve. The counters (Hack→Disrupt, Overload→Fortify, Debilitate→Fortify cleanse) create reactive gameplay depth without overwhelming new players.

**S8 — Deferred Command Model + Strict Validation is Design-Contract Excellence**
WASM modules never directly mutate state — they return Command[] JSON that the engine validates and applies. The RejectionReason enum with human-readable suggestions ("OutOfRange: distance 5, max 1. Move closer or use RangedAttack range 3") provides exactly the right feedback for iterative improvement.

---

## 3. Issues Found

### Critical

**G1 — Arena "Algorithm vs Algorithm" Semantics Conflict with Competitive Integrity**
The design states (modes.md §9.1): "对抗的主体是算法而非玩家。每个槽位绑定一个 WASM 模块——同一玩家可部署多个算法互相对战，也可邀请他人加入某个槽位。" This creates a fundamental identity crisis for Arena mode:

- If Arena is about algorithms, not players, what does a tournament ranking mean? A player who runs both sides of a match can never truly "lose."
- If the same player can occupy multiple slots, the Arena PvP ladder measures WASM quality, not player skill — but the PvE Challenge mode already serves this purpose.
- The design also references "Human/WASM, AI-assisted, AI tournament" league partitions (feedback-loop.md §6), suggesting the Arena IS player-vs-player.

**Recommendation**: Separate Arena into two distinct sub-modes:
- **Arena Self-Play** (test mode): single player, multiple WASM slots, no ranking, no public replay — pure algorithm testing.
- **Arena Match** (competitive mode): one player per slot, ranked, public replay, the current competitive features.

### High

**H1 — Resistance System is Under-Specified for 6 Damage Types**
The vanilla ruleset defines 6 damage types (Kinetic, Thermal, EMP, Sonic, Corrosive, Psionic) but provides extremely sparse resistance coverage:

| Source | Resistance |
|--------|-----------|
| Tough body part | Kinetic ×0.5, Sonic ×0.5 |
| Structure (buildings) | EMP ×2.0, Corrosive ×1.5 |

Thermal, Psionic, and Corrosive (on units) have zero resistance options in vanilla. The special attacks reference these damage types for resistance checks (Hack→Psionic, Debilitate→Corrosive, Drain/Overload→EMP) but there's no way for players to build resistant drones against them.

This creates a degenerate strategic situation: if a player wants to defend against Hack (Psionic), they have no body part choices that help. The only defense is to attack the hacker first or use Fortify (universal ×0.5). The resistance system has 6 dimensions but only 2 have actionable player choices.

**Recommendation**: Either (a) add resistance mappings for all 6 damage types across existing body parts (e.g., Heal→Psionic ×0.5, Work→Thermal ×0.7, Claim→EMP ×1.5 weakness), or (b) reduce vanilla damage types to 4 (Kinetic, Thermal, EMP, Corrosive) and defer the rest to mods, so every type has at least one counter-body-part.

**H2 — Default Logistics Mode B is Too Forgiving to Create Meaningful Gameplay**
The default Mode B logistics costs are:
- Local→Global: 1% fee + 10 tick delay
- Global→Local: 5% fee + 5 tick delay

At 1% transfer cost, a player running 100 drones harvesting Energy will barely notice the logistics overhead. The 10-tick delay is the only meaningful constraint, but since global storage pays for deployments directly, players can largely ignore local logistics optimization.

The entire Depot/Controller supply line system (§gameplay.md 后勤网络) — with Depot maintenance costs, repair capacity limits, and tactical Depot destruction — only matters meaningfully in Mode C (global_storage_enabled=false). In the default Mode B, the logistics gameplay layer is almost entirely optional.

**Recommendation**: Raise default transfer costs significantly (e.g., 5% local→global, 10% global→local) or make Mode C the default for Standard+ worlds. The Depot/Controller logistics system is well-designed and deserves to be mechanically relevant, not just flavor.

### Medium

**M1 — Single-Resource Economy Creates Single-Variable Optimization**
With Energy as the only default resource, all strategic decisions collapse to "maximize net Energy/tick." The resource system supports multi-resource economies (Crystal+Gas, Food+Wood+Stone+Gold examples are given), but the vanilla ruleset uses single Energy. This means:

- Body part selection optimizes for Energy-return-on-investment
- Building choices optimize for Energy efficiency
- PvP value is measured in Energy-denominated losses inflicted/absorbed

There's no interesting trade-off like "do I invest in Crystal production (for advanced units) or Energy production (for basic units)?" because everything costs Energy.

**Recommendation**: Add at least one secondary resource to the vanilla ruleset (e.g., "Matter" already exists in the config examples). Make advanced body parts and structures cost Matter. This creates a two-dimensional optimization space that rewards strategic diversity. The infrastructure for this already exists in the design — it just needs to be enabled by default.

**M2 — idle_aging Penalty is Too Weak to Create Tension**
Active drones age at 110% rate vs idle drones at 100%. A 10% differential means a continuously active drone lives 1500/1.1≈1364 ticks vs 1500 ticks idle — a difference of only 136 ticks. This is not enough to make the "commit forces or conserve lifespan" decision feel meaningful.

**Recommendation**: Increase active_aging to at least 125% (or configurable). Combined with the controller age repair hard cap of 50%, this would make sustained military campaigns genuinely costly and force strategic pauses for recuperation.

**M3 — PvE Difficulty is Purely Geographic, Not Adaptive**
The zone system (Zone 1→4 with increasing NPC density) creates a natural difficulty gradient, but once a player's code handles Zone 3, they can farm Zone 3 indefinitely. There's no mechanism that adapts difficulty to player capability — no increasing NPC wave strength in repeatedly-farmed areas, no "heat" system that escalates resistance.

The Swarm Invasion event (random 10% chance per 1000 tick) provides occasional pressure but is not tied to player strength. A player with 500 efficient combat drones faces the same 30 Swarmling invasion as a player with 5 basic drones.

**Recommendation**: Add a "threat level" per room that increases with successful PvE clearing and decays slowly. Higher threat → higher NPC spawns and drop quality. This rewards players for pushing into harder content rather than farming safe zones.

**M4 — Market Commands in IDL Conflict with "RFC 占位" Design Stance**
The `game_api.idl` defines `CreateMarketOrder` and `BuyMarketOrder` as valid Command variants. The design (gameplay.md §经济治理合同) explicitly states "Market 和 trading 功能为 RFC 占位——不在当前设计范围内." This inconsistency means:

- SDK code generation will produce market-related types that can't actually be used
- Players will see market commands in autocomplete and wonder why they don't work
- AI agents parsing the schema may attempt market strategies that silently fail

**Recommendation**: Either remove market commands from the IDL until the market design is complete, or add a "preview/planned" annotation that SDK generators can use to exclude them from production builds while keeping them visible in docs.

### Low

**L1 — No Explicit Comeback Mechanic in World Mode**
The anti-snowball mechanisms (empire upkeep, storage tax) slow large empires but don't accelerate small ones. The safe_mode protects new players for 500 ticks, but once they exit, they face established empires with no assistance. In a persistent world where "先入者、大帝国拥有资源优势是接受的设计" (gameplay.md §反雪球合同), this is philosophically consistent, but it means the World mode onboarding gradient ends abruptly at tick 2000. Some form of "underdog bonus" (e.g., increased source regeneration for bottom-quartile players, catch-up RCL speed) would smooth the transition.

**L2 — Drone Personality System is Purely Cosmetic, Risking Player Confusion**
The personality dimensions (aggression, curiosity, loyalty, efficiency) are explicitly non-gameplay ("人格不影响 gameplay 数值——纯表现和行为微调"). However, naming a dimension "efficiency" and describing high-efficiency drones as "采集动画利落，一次抓取动作完成" will inevitably lead players to believe it affects harvesting speed. The documentation is clear but the naming is misleading.

**Recommendation**: Rename "efficiency" to "precision" or "dexterity" to avoid implying gameplay benefits. Add a tooltip in the Web UI that explicitly states "personalities are cosmetic only."

**L3 — Arena Challenge Embedding in World is Under-Specified**
The first-hour transition design mentions "玩家可在 World UI 中向附近玩家发起小型 Arena 挑战（1v1, 100 tick, 对称初始资源）——输赢不影响 World 资产." How this works technically is unclear: does World tick execution pause for the Arena match? Is the Arena match simulated in a parallel sandbox? The design doesn't specify the execution model, and this has gameplay implications — if World keeps ticking during the Arena match, the challenger's base is undefended.

---

## 4. Strategy Depth Analysis

### Strategy Space Dimensionality

| Dimension | Variables | Effective Depth |
|-----------|-----------|----------------|
| Body composition | 8 part types × cost/age tradeoffs | **High** — meaningful trade-offs |
| Damage type selection | 6 types, but sparse resistance coverage | **Low** — see H1 |
| Special attack choice | 8 attacks with counters | **Medium** — good rock-paper-scissors |
| Economic optimization | Single resource (Energy default) | **Low** — see M1 |
| Logistics | 3 modes, but default trivializes | **Low** — see H2 |
| Territory/expansion | Room control, Controller levels, Depot placement | **High** — spatial strategy |
| Diplomacy | Alliance system with privileges | **Medium** — limited to 5 allies |
| Information warfare | Fog of war, scouts, Observer structures | **Medium** — infrastructure exists |
| P2P trust protocols | Drone messaging with untrusted payloads | **High** — emergent meta-game |

### Dominant Strategy Check

**Body part composition**: No clear dominant strategy. TOUGH-heavy builds survive longer but deal no damage. ATTACK-heavy builds hit hard but die fast (age_modifier -80). The trade-off between lifespan and combat power is real.

**Expansion**: The empire upkeep formula (O(n²) rooms) creates genuine diminishing returns. A 50-room empire pays ~3150/tick in upkeep vs ~40/tick for a 1-room empire. The controller age hard cap prevents infinite drone replacement.

**Special attacks**: The counter system (Hack↔Disrupt, Overload↔Fortify, Debilitate↔Fortify) creates a non-trivial mixed strategy equilibrium. A pure Hack strategy loses to Disrupt. A pure Overload strategy loses to Fortify. But the balance depends on cooldown ratios — Hack (200t CD) vs Disrupt (50t CD) means Disrupt is 4× more available, which may over-counter Hack strategies.

**Logistics**: Under default Mode B, the dominant strategy is to use global storage for everything and ignore local logistics infrastructure. This makes Depot construction suboptimal outside Mode C.

### Nash Equilibrium: Human + AI Coexistence

With identical WASM paths and fuel metering, the equilibrium is theoretically fair. However, AI agents have one structural advantage: they can iterate strategy faster through MCP programmatic access (swarm_simulate, swarm_get_snapshot, swarm_explain_last_tick in automated loops). A human takes minutes to read feedback and modify code; an AI agent can do it in seconds.

This is not a design flaw — the design explicitly embraces this asymmetry ("AI agent 不是通过 MCP 直接操作 drone——它编写 WASM 代码，drone 由代码控制。这和人类玩家完全相同"). But it does mean the Nash equilibrium may favor AI players in the long run if no human-oriented assistance (better IDE tooling, strategy templates, community code sharing) closes the iteration-speed gap.

---

## 5. CrossCheck — 需要跨方向检查

- **CX1** [Arena Identity Conflict]: Arena mode mixes "algorithm self-testing" and "player-vs-player competition" semantics. The same-player-multiple-slots design undermines competitive ranking integrity. → **建议 Architect 检查** Arena 的比赛执行模型是否支持区分 self-play 和 competitive match；建议 Speaker 检查 modes.md 中 Arena 的定位一致性。

- **CX2** [Resistance Coverage Gap]: 6 damage types but only 2 have body-part resistance mappings. The special attack system references Psionic/EMP/Corrosive resistance checks but offers no counter-build choices. → **建议 Architect 检查** 这是有意设计（留给 mods）还是遗漏；建议 Security 检查 Overload 攻击在无 EMP 抗性时的平衡性。

- **CX3** [Overload Recovery Math]: Overload deducts 500k fuel; natural recovery is `fuel_budget/1000` per tick. At default MAX_FUEL=10M, recovery = 10k/tick × 50 tick cooldown = 500k — exactly offsetting one Overload. This makes a single Overload attacker completely neutralized by passive recovery. → **建议 Architect 验证** Overload 恢复公式是否产生预期的策略压力（需要协调多攻击者才能造成持久压制）。

- **CX4** [Embedded Arena Challenge Execution Model]: feedback-loop.md §2.4 proposes embedding Arena challenges within World mode. If World ticks continue during the Arena match, the challenger's base is undefended. If World pauses, it affects all other players. → **建议 Architect 检查** 嵌入 Arena 的技术可行性及对 World tick 调度的影响。

- **CX5** [Market IDL Inconsistency]: IDL defines `CreateMarketOrder`/`BuyMarketOrder` as valid commands; design marks market as "RFC 占位." SDK generation will produce dead code. → **建议所有评审员标记** 此不一致项；建议 Speaker 在共识报告中统一处理。

- **CX6** [code_update_cost=0 + cooldown=5 的 Abuse Vector]: The design mentions `code_update_cooldown ≥ 5` to prevent "re-deploy refund abuse," but `code_update_cost` defaults to 0 (free). If deployment is free, what refund abuse exists? The 5-tick cooldown seems to guard against a threat that doesn't exist under default settings. → **建议 Security 检查** re-deploy abuse 场景是否在 cost=0 时仍然存在（如 tick 边界竞态、WASM 编译缓存利用等）。

---

## 6. Summary

Swarm's game design is ambitious, coherent, and structurally sound. The WASM-first fairness model, configurable world rules engine, and dual-mode World/Arena architecture are all correct architectural choices that will age well. The onboarding and feedback loop design is unusually thoughtful for a game engine project at this stage.

The concerns raised (resistance depth, logistics incentive tuning, single-resource economy, Arena identity, market IDL inconsistency) are all addressable within the design phase. None indicate fundamental design flaws. Addressing H1 (resistance coverage) and H2 (logistics incentive strength) would notably improve strategic depth at minimal design complexity cost.

**The design is ready to proceed to implementation with the noted conditions addressed.**
