# Game Designer Evaluation — Swarm

## Verdict: REQUEST_CHANGES

Swarm has a strong fantasy: "your code is your army" upgraded for a world where AI agents are also legitimate players. The updated plan correctly treats MCP as a first-class player surface instead of a side integration, and that is the right direction.

But from a game-design perspective, the current plan is still too much engine and not enough game. It explains how players can act, but not enough about why their first hour is fun, how an AI player learns without a human babysitter, how mistakes become debuggable stories, or what keeps a player improving after the basic harvest/build/attack loop works.

I would not block the technical foundation, but I would request changes before community launch: add an explicit onboarding/tutorial loop, a first-class AI player handbook exposed through MCP resources, richer replay/debug affordances, and deeper progression goals beyond room controller level + leaderboard.

## Strengths

1. The core pitch is compelling

A persistent MMO RTS where autonomous code fights forever is already a proven fantasy via Screeps. Swarm’s language-agnostic WASM angle makes the fantasy broader: Rust optimizer players, TypeScript quick-iteration players, Python/prototyping players, and eventually AI agents all get a seat at the same table.

2. AI players are treated as real players, not bots glued on later

The planner update moves MCP into the engine’s core player model: PlayerKind, AI sessions, MCP tools, per-player snapshots, isolation, lifecycle management, and MCP-accessible docs. This is exactly the right instinct. For an AI player, MCP is not an API feature; it is the controller, UI, tutorial, memory surface, and debugger.

3. Deterministic simulation is excellent for game feel

Replayability, fixed command ordering, visible rejection reasons, and trace collection are not only engineering wins. They make the game legible. A programming game lives or dies on whether players can answer: "Why did my bot do that?" Determinism gives Swarm the foundation to make every failure explainable.

4. The design naturally creates spectator stories

Room conquest, autonomous swarms, market bots, AI tournaments, and season ladders are easy to understand from the outside. If the replay and observer layers become first-class, Swarm can produce watchable emergent narratives: a botched invasion, a clever economy exploit, a last-second defense, a weird AI strategy that humans copy.

5. The resource model has a clear fairness thesis

WASM fuel metering is a strong improvement over wall-clock CPU. The game can say, with credibility, that players are competing on algorithmic quality rather than runtime luck or language-specific GC behavior.

## Concerns

### G1. AI first-hour experience is underspecified

Experience problem:
An AI agent joining through MCP needs to know: What is the objective? What do I own? What can I do this tick? What is a good beginner strategy? What mistakes did I make? The plan exposes snapshots, action tools, schemas, and docs, but does not define an MCP-native "learn to play" path.

Why this lowers playability:
If the first AI session begins with raw schemas and 11 action tools, many agents will thrash: move randomly, harvest without transferring, spawn bad bodies, ignore fatigue, or fail to understand room goals. Human players can read blog posts, watch videos, and infer intent from UI. AI players only have the resources you expose. If those resources are reference docs instead of coaching docs, the AI player experience will feel like debugging an unfamiliar API rather than playing a game.

Suggestion:
Add MCP resources specifically designed as an AI tutorial, not just generated schema:

- `swarm://tutorial/quickstart` — objective, first 5 minutes, first working policy.
- `swarm://tutorial/basic-harvester` — step-by-step loop: spawn, harvest, transfer, upgrade/build.
- `swarm://strategy/opening-book` — recommended early-game priorities by room state.
- `swarm://rules/fair-play` — limits, command budget, visibility rules, what not to assume.
- `swarm://examples/commands` — valid command sequences with expected outcomes.
- `swarm://self/evaluation` — per-player checklist: idle drones, rejected commands, energy income, survival risk.

Also add an explicit "AI onboarding mode" where a new AI can play a tiny protected scenario and receive structured feedback after each tick.

### G2. MCP tool discoverability is not yet a game UX design

Experience problem:
The plan says there will be `swarm_get_snapshot`, 11 tools mirroring Command enum, and schema/docs resources. That may be technically complete, but tool names, parameter ergonomics, error messages, and action affordances are what determine whether AI players can actually play well.

Why this lowers playability:
For an AI player, bad tool design is the equivalent of a terrible UI. If action tools require obscure IDs, ambiguous target fields, or return only "invalid command", the AI cannot form a reliable mental model. It will waste turns discovering constraints that should have been obvious.

Suggestion:
Design MCP tools as player-facing verbs with self-explaining parameters and rich failure messages. For example:

- Prefer `swarm_move_unit(unit_id, direction)` over a generic command envelope when exposed as a tool.
- Every tool response should include: accepted/rejected, reason, relevant rule, current entity state, and suggested fix.
- `swarm_get_available_actions(unit_id)` should exist. Do not force players to infer all legal actions from schema + state.
- `swarm_validate_plan(commands[])` should let an AI dry-run command legality before spending a tick.
- `swarm_explain_last_tick()` should summarize what happened in game terms, not raw logs.

Generated docs are good, but hand-authored affordance docs are still needed for the top-level play loop.

### G3. Human-AI fairness is not solved by equal command limits

Experience problem:
The plan’s fairness answer is mostly "same command limits, identical validation." That handles action fairness, but not decision-process fairness. Human code runs inside WASM fuel limits. AI players may use large external models, long chain-of-thought, tool calls, or private memory outside the game before submitting commands.

Why this lowers playability:
If AI players can spend unlimited off-server reasoning time between ticks, they may have a strategic advantage that is invisible to human players and impossible to compare on leaderboards. Conversely, if tick deadlines are strict but not designed around model latency, AI players may feel randomly punished by provider latency rather than outplayed.

Suggestion:
Define competitive classes early:

- Human/WASM ladder: only uploaded WASM code, fuel-metered.
- AI-assisted ladder: external AI allowed, strict wall-clock submission deadline.
- AI tournament ladder: model/provider declared, external reasoning allowed under published constraints.
- Exhibition/sandbox rooms: anything goes.

For AI players, publish fairness metrics: decision latency, commands submitted, invalid command rate, external model label, and whether the player used MCP-only information. Do not mix pure WASM and unconstrained remote-AI players on the same serious leaderboard without labels or divisions.

### G4. Debugging UX needs to explain decisions, not just record traces

Experience problem:
The plan adds TickTrace, EntityEvent, replay, inspect tools, WASM traces, profiling, and overlays. This is a strong start for "what happened," but programming-game frustration usually comes from "why did my bot believe this was the right action?" For AI players, the parallel question is: "Why did my agent choose this plan?"

Why this lowers playability:
A player who cannot debug will churn. In a normal game, losing can still be fun if the cause is visible: I was outnumbered, I was late, I built the wrong counter. In a programming game, losing often looks like silence, invalid commands, or units standing still. Without a decision-centered debugger, the game becomes opaque and punishing.

Suggestion:
Make debugging a core game surface:

- Timeline view: snapshot → player decision → commands → validation → world events.
- Per-unit "why idle?" explanations.
- Rejection explanations with exact failed precondition and example fix.
- `swarm_diff_snapshots(tick_a, tick_b)` for AI and humans.
- `swarm_replay_from_tick(tick, hypothetical_commands)` for local what-if testing.
- Optional player-side decision logs attached to commands, e.g. `reason: "harvester full, returning to spawn"`.
- For AI players, add a structured `decision_trace` field they can submit voluntarily so replays show not only actions but intentions.

The goal should be: a replay is not just a movie; it is a debuggable argument.

### G5. New-player onboarding is hidden in Phase 5, too late

Experience problem:
The current roadmap places docs/tutorials late, while early phases focus on engine, MCP, persistence, and infrastructure. For a programming game, onboarding is not polish. It is the main interface to the game.

Why this lowers playability:
A blank code editor plus a complex world state is intimidating. A raw MCP schema plus action tools is equally intimidating. If the first public build lacks a guided path to first success, early community feedback will be dominated by confusion rather than strategic discussion.

Suggestion:
Move onboarding into the MVP definition:

- First 5-minute human tutorial: edit one line, deploy, see a drone harvest.
- First 5-minute AI tutorial: connect MCP, read quickstart, call snapshot, issue a valid action, receive feedback.
- Starter bot templates for TS, Rust, and MCP-agent players.
- A tiny deterministic tutorial room with scripted goals.
- "Next best improvement" hints: idle unit, energy bottleneck, spawn queue empty, controller neglected.

The MVP should not mean "the engine can run." It should mean "a new player can experience the fantasy."

### G6. Progression depth is currently too close to Screeps basics

Experience problem:
The long-term goals listed are controller levels, combat, market, leaderboards, seasons, and tournaments. These are good, but they are mostly expected genre features. The plan does not yet reveal Swarm’s unique long-term mastery loop.

Why this lowers playability:
Players need a reason to keep improving after they have a stable harvester, builder, upgrader, defender, and market bot. If progression is only bigger rooms and higher rank, the meta may converge into solved templates. AI players may accelerate this convergence by cloning strong patterns quickly.

Suggestion:
Add progression axes that create strategic diversity:

- Research/blueprint system: unlock specialized body parts, structures, or room policies through achievements, not grind alone.
- Seasonal modifiers: altered terrain, scarce resources, asymmetric room rules, weather, decay, neutral threats.
- Specialization paths: logistics empire, mercenary combat, market maker, explorer, defensive fortress, support alliance.
- Contracts/quests: player-created bounties, delivery contracts, defense contracts, scouting jobs.
- Bot reputation: reward reliability, trade honesty, defense success, rescue operations, not only conquest.
- Algorithmic achievements: lowest CPU per energy, best survival under attack, fastest room bootstrap.

The strongest version of Swarm is not merely "Screeps but WASM + AI." It is a programmable civilization sandbox where many styles can be excellent.

### G7. Fun factor depends on watchability, but spectator UX is too late and too vague

Experience problem:
The plan mentions replay, visual overlay, leaderboards, seasons, and AI tournament mode, but not a clear spectator product. Programmable games become community games when people can share surprising behavior.

Why this lowers playability:
If battles and clever bots are hard to watch, the community cannot easily teach, celebrate, or argue about strategy. A game like this needs social proof: "look what my swarm did," "watch this AI bot invent a tactic," "here is the replay where my defense survived."

Suggestion:
Treat replay/spectator as a launch feature, not Phase 7 polish:

- Public replay URLs.
- Shareable clips from tick A to tick B.
- Observer mode for rooms and tournaments.
- Fog-of-war-aware replay modes: owner view, opponent view, omniscient post-match view.
- Commentary overlay: major events, economy graph, command rejection spikes, CPU usage.
- Tournament bracket pages with live room view.

This is how Swarm becomes a community, not just a private coding exercise.

### G8. The game objective is still too implicit

Experience problem:
The design explains systems: drones, structures, resources, controllers, rooms, markets, combat. But it does not clearly state what a player should want minute-to-minute, day-to-day, and season-to-season.

Why this lowers playability:
Without explicit goal ladders, new players ask: Am I supposed to expand? Attack? Upgrade? Trade? Survive? Optimize CPU? AI players will ask the same through their behavior. A sandbox still needs visible aspiration.

Suggestion:
Define three goal layers:

- Immediate: make energy income positive, keep spawn busy, upgrade controller, avoid idle drones.
- Strategic: claim rooms, specialize economy, defend, trade, scout, form alliances.
- Seasonal: rank by multiple dimensions, win tournaments, complete challenges, earn badges/cosmetics/titles.

Expose these goals in both UI and MCP resources. An AI player should be able to ask the game, "What goals are currently available to me?"

## Missing features

These are features the community will likely ask for on day one:

1. Official starter bots

Not just SDK examples, but deployable reference players: basic harvester, upgrader, builder, defender, scout, market bot, and MCP-agent starter.

2. Local simulation and test harness

Players will want to run thousands of ticks locally, write assertions, and compare strategy versions before deploying. The SDK mentions `sim.ts` and `sim.rs`, but this should be a first-class product with fixtures and replay import/export.

3. A tutorial room

A safe deterministic room with explicit objectives and no enemy pressure: harvest 100 energy, spawn a worker, build a road, upgrade controller, survive a scripted attack.

4. Action validation / dry-run API

Both humans and AI agents need to know whether a command would be legal before losing a live tick.

5. Explainable command rejection

Invalid commands should never be a dead-end error. They should say exactly what rule failed and how to fix it.

6. Public replay sharing

Replay URLs, short clips, and a simple web viewer should exist before serious tournaments.

7. Bot versioning and rollback

Players need to deploy v12, compare it to v11, roll back after a bad release, and annotate strategy changes.

8. Strategy metrics dashboard

Energy per tick, CPU/fuel per tick, idle unit time, spawn uptime, death causes, distance traveled per delivered energy, command rejection rate.

9. Fog-of-war and information policy documentation

AI players especially need clear rules on what is visible, remembered, stale, or forbidden.

10. Social layer

Alliances, room messages, player profiles, bot descriptions, match history, and maybe diplomacy APIs. Persistent strategy games become much more fun when players can recognize each other.

11. League separation

Human WASM, AI-assisted, pure AI, and sandbox/exhibition should be clearly labeled to avoid fairness arguments.

12. MCP capability manifest

A single AI-readable resource that lists tools, resources, limits, current player identity, tick deadline, command budget, and recommended next docs.

## Fresh ideas

1. MCP "coach mode"

Let an AI or human ask `swarm_coach_analyze(tick_range)` and receive a structured critique: idle units, wasted movement, bad body composition, energy bottlenecks, unsafe expansion. This could be available in tutorial rooms or as a post-match analysis feature.

2. Intent-tagged commands

Allow commands to include optional intent labels: `harvest_loop`, `retreat`, `defend_spawn`, `probe_enemy`, `market_arbitrage`. Replays could then show not only what happened, but what the bot thought it was doing.

3. Opening-book challenges

Weekly challenge rooms where everyone starts from the same seed and tries to optimize a specific goal: fastest 1,000 energy, lowest CPU bootstrap, survive 500 ticks, best tower defense. Great for humans and AI agents.

4. Bot genome / strategy cards

Players can publish a bot profile: language, architecture, strengths, weaknesses, average metrics, favorite openings. This makes autonomous code feel like a roster of recognizable competitors.

5. AI-only "black box league"

Agents are restricted to MCP resources and cannot use private hand-written strategy docs during a match. The point is to test how well agents learn the game from the game itself. This would be a powerful benchmark and a unique identity for Swarm.

6. Replay commentary generator

After a battle, generate a sports-style summary: turning points, economic lead changes, decisive errors, best unit, most wasteful tick. This makes matches shareable even for people who do not read code.

7. Market as programmable PvP

Make the market deep enough for non-combat players: contracts, futures, delivery risk, regional scarcity, reputation. Some players should be able to "win" by being the best logistics/market bot rather than the best attacker.

8. Debugging achievements

Reward clean engineering: 10,000 ticks with zero invalid commands, best CPU efficiency, most improved energy curve, fastest recovery after spawn loss. This reinforces that optimization itself is gameplay.

9. Alliance APIs

Expose controlled diplomacy primitives: request aid, offer trade, publish room status, set defense pacts. AI players could negotiate through bounded game-native messages rather than arbitrary prompt-injectable chat.

10. Seasonal anomalies

Introduce temporary world rules: solar storms reduce vision, mineral rushes alter economy, neutral invaders pressure overexpanded players, terrain shifts open new corridors. This prevents the meta from freezing.

## Final recommendation

Proceed with the MCP-first implementation, but revise the plan before launch around one principle:

The playable unit is not the engine. The playable unit is the complete feedback loop: learn the rules, make a decision, see the result, understand the mistake, improve the bot, and share the story.

For humans, that loop runs through editor, simulator, replay, and dashboard. For AI players, it runs through MCP resources, tools, validation, and explanations. Both must be designed as game UX from Phase 1, not documentation or debug polish added later.
