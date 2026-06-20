# R27 Phase 1 Clean-Slate Review — Design & Economy (GPT-5.5)

Reviewer: rev-gpt-design-economy
Scope: Design & Economy only
Read set: only the 10 whitelisted R27 files named in task t_479cacad

## Verdict

REQUEST_MAJOR_CHANGES

The Swarm design has a strong and differentiated core: "write WASM, watch an autonomous colony compete", with a clearly separated MCP-as-interface model, a useful World/Arena split, and a serious attempt to close resource ledgers, replay, debugging, and onboarding. However, from a game design and economy perspective, the current Phase 1 subset is not yet freeze-ready.

The main blocker is not that the vision is weak; it is that several promises are internally fighting each other: the first-hour/golden-path promises say the player reaches meaningful PvE and self-maintaining growth quickly, while the Standard balance sheet shows persistent negative cashflow even at 1/5/20 rooms under stated assumptions; Arena is positioned as MVP but lacks enough product/rules detail to be independently fun; and the complexity of special attacks, logistics, diplomacy, storage, upkeep, PvE budgets, and replay may exceed what a player or AI agent can reliably learn from the currently specified MCP resources.

I recommend major changes focused on narrowing the MVP economic surface, adding explicit positive early-game target curves, and converting several rich but risky systems into later expansion modules.

## Strengths

S1. The core fantasy is clear and valuable.

"Your code is your army" is communicated consistently. The design correctly avoids MCP direct gameplay commands and keeps humans and AI agents on the same WASM path. This is a major fairness and product-positioning strength.

S2. The feedback-loop work is much stronger than typical programmable-game specs.

The Learn → Decide → Act → Understand loop is explicit. `swarm_get_docs`, `swarm_get_schema`, `swarm_get_available_actions`, `swarm_dry_run`, `swarm_explain_last_tick`, TickTrace, replay, first_tick_executed, and starter-bot CI acceptance form the right primitives for making a code-first game learnable.

S3. World vs Arena has a promising design split.

World is correctly framed as unfair, persistent, sandbox/social/economic; Arena is framed as fair, symmetric, locked-code, replayable algorithm competition. This split avoids the common MMO mistake of trying to make persistent worlds competitively fair.

S4. The Resource Ledger direction is healthy.

A single resource gateway with typed operations, deterministic ordering, TickTrace attribution, fixed-point rates, PvE budget caps, transfer fees/delays, storage tax, and explicit Future RFC boundaries is the right foundation for a multiplayer economy.

S5. Anti-snowball intent is explicit.

Superlinear upkeep, storage tax, no-teleport global transfer, PvE output caps, safe/soft-launch phases, room/drone caps, and alliance transfer limits show awareness of common Screeps/MMO runaway patterns.

S6. Replay/spectator/community hooks are present.

Arena replay, public spectate controls, replay privacy, highlight-card RFC, command provenance, and replay viewer ideas are important for a programmable game where community learning and strategy sharing drive retention.

## Concerns

### G1 — High — First-hour promise conflicts with the economy curve

The design promises a 10-minute golden path and a first-hour transition with safe_mode, soft_launch, PvE threats, and low-risk conflict. But the Standard balance sheet shows:

- 1 room: income 25/tick, expense 55/tick, net -30/tick.
- 5 rooms: income 140/tick, expense 390/tick, net -250/tick.
- 20 rooms: income 1,220/tick, expense 3,160/tick, net -1,940/tick.
- 50 rooms: income 3,975/tick, expense 16,600/tick, net -12,625/tick.

The Resource Ledger later states that the player should be self-sustaining after free upkeep expires around tick 2000, with >=2 rooms + 5 drones + complete faucet pipeline. The balance sheet does not prove that. It mostly proves that the default Standard curve is negative at every showcased scale unless unspecified "efficient code", Controller upgrades, Source upgrades, PvE farming, or alliance trade bridge the gap.

For gameplay, this is dangerous: a new player can do everything "right" and still feel like the game is silently draining them. In a code game, players often interpret negative economy as a bug in their bot, not as intended macro pressure.

Required change:
- Add an explicit early-game target curve with concrete expected values for tick 0, 500, 1500, 2000, 5000, and 10000.
- Show at least one starter-bot path that reaches non-negative net flow before free_upkeep expires.
- Separate "Standard veteran anti-snowball" from "default onboarding world" if necessary.

### G2 — High — Maintenance formula may punish breadth before players understand optimization

`upkeep = base_upkeep × rooms × (1 + rooms / room_soft_cap)` is a clean anti-snowball formula, but the showcased numbers make even 5 rooms deeply negative. That means the curve may function less as "anti-snowball" and more as "anti-expansion" until the player already understands advanced optimization.

This harms fun because early expansion is one of the most legible forms of progress in territory games. If the first obvious goal (claim more rooms) immediately makes the economy worse, the game must surface that as a clear strategic lesson, not a surprise tax.

Required change:
- Define whether the intended default is "expand early" or "optimize one room first".
- Add UI/MCP pre-expansion forecast: "Claiming room N will add +X income, +Y upkeep, break-even requires Z harvesters/RCL".
- Consider a kinked curve: low/flat for first 2-3 rooms, superlinear after a soft cap, instead of applying full Standard pressure immediately.

### G3 — High — MCP resources may not be sufficient for an AI player to learn without hidden human assumptions

The pieces exist, but the learning path still assumes an agent can synthesize a large ruleset from many tools and docs. The game has dynamic world rules, world-specific SDKs, custom actions, body parts, resources, storage modes, special attacks, hint levels, snapshot truncation, and economy warnings.

An AI agent needs not just `swarm_get_docs`, but a compact, machine-actionable "what should I do next?" contract. `swarm_get_available_actions` helps at drone/action level, but there is no equivalent macro tutorial goal API.

Required change:
- Add a canonical `swarm_get_objectives` or tutorial resource that returns current tutorial goals, acceptance criteria, and suggested next MCP calls.
- Ensure `swarm_get_docs(topic="first_bot")` or equivalent returns a minimal starter plan under the token budget, not a huge encyclopedia.
- Add CI smoke tests where a fresh agent using only MCP resources can discover, build, deploy, observe, and improve the starter bot.

### G4 — Medium — World vs Arena distinction is good but Arena P0 may not yet be fun enough

Arena has room creation, symmetric map, locked code, replay, PvE challenge, and score formulas. But the P0 feature set explicitly excludes matchmaking, ladder, seasons, and tournament/league. That leaves Arena as a sandbox duel tool, not necessarily a compelling loop.

For a programmable strategy game, Arena can be the viral/community engine. If P0 has no ranking or discovery beyond rooms and replay, it may fail to generate repeated play.

Required change:
- Define the P0 Arena repeat loop: "create challenge → share replay → remix opponent bot → improve score".
- Add at least one low-cost competitive surface that is not a full ladder: daily seed challenge, scenario leaderboard, or replay-of-the-day.
- Clarify whether `swarm_get_leaderboard` is active for Arena in P0, since feedback-loop doc says no ladder/ranking while API registry has Arena leaderboard tools.

### G5 — Medium — Special attacks are too complex for the stated onboarding path

Eight special attacks plus damage types, resistances, statuses, visibility rules, cooldowns, custom action registry, Tier 2 markers, and special visual effects are compelling long-term depth. But they are too much for a first freeze if the game is also trying to prove WASM deployment, economy, logistics, replay, MCP, and Arena.

The design partially mitigates this by disabling specials in Tutorial/Novice, but Standard enables all 8. That creates a cliff: players go from basic harvesting/building to Hack/Drain/Overload/Debilitate/Disrupt/Fortify/Leech/Fabricate.

Required change:
- Move Leech/Fabricate clearly out of MVP gameplay, not merely "registered but Tier 2".
- Consider Standard MVP enabling only 2-4 special actions: Disrupt, Fortify, Drain, maybe Overload. Add others after telemetry shows players mastered basics.
- Provide explicit unlock/teaching moments per special action.

### G6 — Medium — Player-facing rule complexity may overwhelm despite configurability

The platform vision says everything is configurable: resources, body parts, structure types, damage types, special effects, custom actions, storage modes, visibility, upkeep modules, mod manifests. This is powerful for server operators but risky for players.

If every world can change almost everything, players may not know what game they are joining. The design has `[MOD]` labels and `swarm_get_world_rules`, but needs stronger product taxonomy.

Required change:
- Define official world tiers with stable expectations: Tutorial, Novice, Standard, Advanced/Modded.
- For each tier, list allowed variability and forbidden variability.
- In the UI/MCP, summarize rule deviations as "what affects your bot code" vs "economic tuning only".

### G7 — Medium — Community sharing is acknowledged but under-specified for growth

Replay and spectate exist, but key viral loops are RFC. In a code game, community artifacts are not optional cosmetics; they are how players learn, compare, and stay motivated.

Required change:
- Promote at least minimal replay sharing and scenario score sharing into MVP, especially for Arena PvE Challenge.
- Add code-safe replay annotations: share replay without exposing private WASM unless player opts in.
- Provide a "fork this starter bot / replay strategy" path outside direct code disclosure.

### G8 — Low — Drone personality is charming but should stay firmly cosmetic

The personality system can increase emotional attachment, which is valuable in an otherwise abstract code game. The doc says it does not affect gameplay, which is correct. The note that high-efficiency personality might carry market/social value is risky: it may confuse players into thinking personality has hidden mechanical value.

Required change:
- Keep personality as cosmetic/replay/branding only in MVP.
- Avoid any marketplace language until there is a clear non-pay-to-win policy.

## Economy Concerns

### E1 — Critical — The published balance sheet does not close the early economy

The most serious economy issue is that the balance sheet demonstrates negative net flow at all showcased Standard scales while the design text claims self-sustainability by the end of the protection window. This is either a numbers bug or a missing systems bug.

Specific contradiction:
- Economy balance sheet §2.1 says 1-room Standard net is -30/tick and needs initial resources.
- Resource Ledger §2.3 says after tick 2000 the player should be self-sustaining with >=2 rooms + 5 drones.
- No numeric table proves the 2-room/5-drone state is positive.

Impact:
- New players may enter upkeep deficit just as PvP begins.
- Starter bot CI could pass deployment but fail actual retention/fun.
- Economy tuning cannot be reviewed because the assumed viable path is not quantified.

Required change:
- Add a 2-room/5-drone post-free-upkeep balance table.
- Include starter-bot measured outputs: harvest/tick, build/tick, idle %, net economy over first 2000 ticks.
- If still negative, lower early upkeep or raise early faucet until the default starter path is slightly positive.

### E2 — High — Storage tax rates may be extreme at tick cadence

Storage tax tier 3 is 20 bp/tick = 0.20% per tick. At a 3s World tick, that is 1,200 ticks/hour, which compounds/destructs storage very quickly. Even tier 2 at 5 bp/tick can be enormous over real time.

Maybe the intent is a strong hoarding sink, but the design should state real-time implications. If players log off for a day, high storage tiers could evaporate wealth in a way that feels punitive rather than strategic.

Required change:
- Convert bp/tick into per-hour and per-day example loss in the docs.
- Consider charging storage tax per longer epoch, or use much lower tick rates for storage tax than combat/economy ticks.
- Add offline protection or storage-tax warnings if the goal is active management rather than wealth destruction.

### E3 — High — PvE faucet caps are well-intentioned but not yet tied to player incentives

PvE drops are capped globally/zone/player/event, which is good. But PvE is also used as a key compensating income in the 20/50-room balance sheets and as first-hour onboarding content. If caps are too tight, PvE cannot rescue deficits; if too loose, organized players farm it and inflate the economy.

Required change:
- Show PvE income by player stage: new player, mid player, large empire.
- Define whether PvE rewards are catch-up, skill test, risk/reward, or just world flavor.
- Add anti-farm mechanics beyond global caps: diminishing returns per repeated route, PvE threat scaling, or public contestability.

### E4 — High — Alliance transfer rules conflict across docs and can become a cartel tool

The API/Ledger define AlliedTransfer with 2% fee, 200 tick delay, 500 tick receiver cooldown, 10,000/day receiver cap, and alliance age >=100 tick. Gameplay diplomacy table says allied player-to-player transfer is direct and "免 convert 延迟". Economy balance sheet also lists allied_transfer_enabled false by default for Standard, while diplomacy implies allied transfer privileges exist.

Impact:
- Players and AI agents may misunderstand whether alliances can bypass logistics.
- If allied transfer is direct/no-delay, large alliances can smooth upkeep and reduce anti-snowball pressure.
- If it is disabled by default, diplomacy feels less useful than promised.

Required change:
- Pick one Standard rule and state it everywhere: disabled, restricted delayed transfer, or direct transfer.
- From economy perspective, prefer restricted delayed transfer with caps; no direct instant ally transfer in Standard World.
- Add alliance cartel analysis to anti-snowball proof.

### E5 — Medium — Global/local storage model is rich but risks being two games at once

The global/local split creates strong strategic tradeoffs: abstraction vs physical logistics, visibility, transfer loss, interception. But it also adds substantial cognitive load and implementation surface.

Risk: new players may not understand why resources are "available" for deployment but not building, or vice versa.

Required change:
- In Tutorial/Novice, use a simplified storage mode or make the UI extremely explicit: local, in transit, global, taxable.
- Add a resource-flow diagram to MCP docs in machine-readable form.
- Add one canonical beginner rule: "Harvest local → build local; only use global for deploy/upkeep until you understand logistics."

### E6 — Medium — Resource sinks are numerous but player agency over them is uneven

Sinks include spawn cost, build cost, upkeep, storage tax, global transfer loss, code deploy cost, drone aging/repair, resource decay mod, PvE budgets, and recycling losses. Some are strategic; others are passive drains.

Too many passive drains can make the game feel like accounting decay rather than strategy. The design should differentiate "interesting sinks" (build/spawn/repair/logistics) from "stability sinks" (tax/upkeep/decay).

Required change:
- Define which sinks are enabled in each official world tier.
- Do not enable resource decay by default alongside storage tax + upkeep unless there is strong proof it is needed.
- Ensure every passive sink has clear forecast UI/MCP warnings.

### E7 — Medium — Infinite snowball is addressed for resources but less for knowledge/automation advantage

The docs address resource hoarding and room expansion, but in a code game the biggest snowball may be software: players with better bots compound faster, then share internally within alliances. This is acceptable to a degree, but needs product-level mitigation.

Required change:
- Use Arena/PvE challenges and replay sharing as a skill catch-up path.
- Provide official benchmark bots at multiple tiers, not just starter bots.
- Consider seasonal or fresh-start worlds so latecomers have meaningful resets without undermining persistent World.

### E8 — Low — Market is postponed, but some docs still point at trade expectations

Market trading is listed as RFC/not in current scope, but global storage and resource definitions mention tradeability, Terminal, merchant NPCs, and market exposure. This is fine as long as it is clearly non-MVP.

Required change:
- Keep all market language explicitly Future RFC in the MVP docs.
- Avoid using market behavior as an anti-hoarding proof until market rules exist.

## Missing

M1. Concrete starter-bot economic trace.

Need a tick-by-tick or interval summary proving the starter bot can survive the first 2000/5000 ticks under default official world rules.

M2. First-hour UX acceptance beyond deployment.

The smoke tests verify compile/deploy/dry-run, but not whether the player understands economy, survives first PvE, sees meaningful warnings, and has a next goal.

M3. Macro objective API for AI agents.

The design has action-level discovery, but lacks a goal-level tutor/resource: current objective, why it matters, success criteria, and suggested docs/tools.

M4. Arena P0 retention loop.

Room matches and replays exist, but the loop that makes players come back daily is not yet specified.

M5. Official world-tier matrix.

Tutorial/Novice/Standard/Advanced are mentioned, but need a single matrix of enabled systems, disabled systems, economic parameters, and intended audience.

M6. Alliance economy abuse analysis.

Need explicit analysis of allied transfers, multi-account groups, new-player locks, cartel behavior, and upkeep sharing.

M7. Real-time cost interpretation.

Tax/upkeep numbers are per tick; players and designers need per hour/day examples at the intended tick interval.

M8. Replay privacy and code-disclosure policy.

Replay sharing is central, but the policy for showing commands, code lines, source maps, and private strategy needs clear player-facing defaults.

## Fresh Ideas

F1. Add "Economy Forecast Before Commit" everywhere.

Before ClaimController, Spawn, Build, TransferFromGlobal, or alliance transfer, expose a forecast:
- upfront cost
- recurring cost
- expected income delta
- break-even estimate
- risk flags: storage tax tier, upkeep deficit, transfer delay

For AI: `swarm_dry_run` or `swarm_get_available_actions` can include `economic_forecast`.

F2. Add a "Colony Health Grade" metric.

A simple A/B/C/D grade helps humans and AI know whether they are stable:
- cashflow
- idle drone ratio
- source saturation
- upkeep runway
- storage tax risk
- defense readiness

This reduces the cognitive load of many separate economy numbers.

F3. Use Daily Seed Arena PvE as the viral MVP loop.

Even without full matchmaking/ladder, one deterministic daily PvE scenario with public replay and score is enough to create community iteration. It also trains bot authors without risking World assets.

F4. Make World onboarding an expedition, not just a timer.

Instead of waiting for safe_mode/soft_launch to expire, give new players an explicit expedition chain:
1. Harvest local source.
2. Build first tower.
3. Kill Creep patrol.
4. Claim nearby room.
5. Survive first Resource Surge.
6. Optional Arena challenge.

Each step should have MCP objectives and Web UI objectives.

F5. Add "Official Bot Benchmarks" as long-term goals.

Ship official bronze/silver/gold bots for Tutorial/Novice/Arena PvE. Players can compare against them locally and in Arena. This creates goals beyond GCL/RCL and gives AI agents concrete targets.

F6. Treat Standard as Seasoned World; make Novice the true default.

Given the current Standard upkeep numbers, Standard should not be the first persistent world. The default path should be Tutorial → Novice World → Arena Daily → Standard World.

F7. Add "Replay without Source" and "Replay with Annotated Source" modes.

Players can share strategy safely by default, then opt into code/source-map sharing when teaching. This supports community learning without forcing strategy disclosure.

F8. Use upkeep as a visible logistics boss.

Instead of a hidden tax, personify/visualize upkeep: supply lines, maintenance depots, warning overlays, and "your empire is overextended" forecasts. Make the anti-snowball mechanic feel like a strategic opponent, not a spreadsheet penalty.

## CrossCheck — 需要跨方向检查

- CX1: 维护费公式与早期经济闭环可能矛盾 → 建议 Architect 检查 `UpkeepDeduction` 执行顺序、free_upkeep 适用对象、Controller/drone/room 统计口径是否与经济文档一致。

- CX2: Allied Transfer 在 gameplay/diplomacy、balance sheet、Resource Ledger/API Registry 中语义不一致 → 建议 API/DX 检查 IDL、Registry、MCP docs、world.toml 默认值是否能生成单一、无歧义的玩家可见规则。

- CX3: StorageTax 以 bp/tick 表达，真实时间下可能极端 → 建议 Performance/Architect 检查 tick_interval、tax 执行频率、长期离线玩家处理是否符合系统与产品预期。

- CX4: MCP 工具集是否足以让 AI agent 自举学习仍有缺口 → 建议 API/DX 检查 `swarm_get_docs`、`swarm_get_schema`、`swarm_get_available_actions`、`swarm_sdk_fetch` 输出是否能在 token budget 内支持完整 starter loop。

- CX5: Snapshot truncation 与 competitive hint ladder 对 Arena 公平性影响复杂 → 建议 Determinism 检查截断、dry_run、hint_level、replay 是否在 World/Arena/Training 三类模式下有一致、可复现的语义。

- CX6: 特殊攻击通过 custom actions/world manifest 动态注册，Standard 启用 8 种是否导致 SDK/API 面剧烈膨胀 → 建议 API/DX 与 Architect 共同检查 MVP action manifest 的最小可冻结集合。

- CX7: Replay 分享与 code-line provenance 可能泄露玩家 WASM 策略 → 建议 Security 检查 replay privacy、debug symbols、source map、TickTrace access scope 的默认策略。

- CX8: PvE faucet caps 被用于经济补偿又要防刷怪通胀 → 建议 Economy+Performance 后续联合检查 PvE budget enforcement 的可观测性、TickTrace 审计和大规模 NPC 成本。
