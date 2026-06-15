# Swarm DESIGN — Game Design Review (rev-gpt-designer)

Reviewer: rev-gpt-designer
Focus: player experience, game feel, complexity/accessibility, strategic depth, clarity/completeness, fun/engagement loops
Scope: `/data/swarm/docs/design/DESIGN.md` only; this is a game design review, not spec-compliance review.

## VERDICT: CONDITIONAL_APPROVE

Swarm has a strong core fantasy: “your code is your army” in a persistent programmable MMO RTS, with AI and human players sharing the same WASM path. The design is strategically rich and has a real chance to become a modern Screeps successor rather than a clone.

However, as a game design document, it is currently too systems-heavy and not yet player-experience-complete. It specifies architecture, determinism, moddability, rule extensibility, and simulation contracts in impressive detail, but it under-specifies the first hour, onboarding, moment-to-moment feedback, early goals, player-readable progression, failure recovery, and the social/community loops that make a persistent programming game sticky.

Condition for approval: keep the architecture direction, but add a dedicated “Player Experience / Core Game Loop” layer before implementation: first-hour flow, tutorial ladder, default world rules, early progression milestones, UI/debugging feel, replay/sharing, and long-term goals beyond RCL/GCL-style room progression.

---

## Strengths

### S1 — Core fantasy is clear and compelling
The slogan “你的代码就是你的军队 / Write once, fight forever” is excellent. It communicates the emotional promise quickly: players are not just issuing commands; they are building autonomous systems that persist and fight while they are away.

The strongest identity choices are:
- all players, including AI agents, deploy WASM rather than using privileged action tools;
- deterministic ECS simulation enables replay, debugging, and legitimacy;
- programmable drones create an engineering mastery loop instead of a hand-speed loop;
- World and Arena modes separate sandbox persistence from fair competition.

This gives the project a distinct place between Screeps, Factorio automation, RTS, bot tournaments, and open-source modded servers.

### S2 — Strategic depth is high
The design has many meaningful strategic axes:
- body composition and irreversible body planning;
- local vs global storage tradeoffs;
- code deployment timing/cost/propagation;
- fog-of-war and information asymmetry;
- logistics vs combat vs economy allocation;
- RCL unlock timing;
- rule-modified worlds;
- Arena code-locking for fair competitions.

The local/global storage split is especially promising: it gives casual worlds a simplified economy while allowing hardcore logistics worlds to exist without forcing that burden on everyone.

### S3 — AI/human fairness is a major design advantage
The document correctly avoids giving AI players direct MCP action tools. MCP is “screen and mouse,” not gameplay authority. This preserves the core fantasy and prevents a design split where AI agents are playing a different game from humans.

From a community perspective, this is important: AI agents become legitimate players, not automation cheats.

### S4 — World Rules Engine supports community longevity
Configurable resources, structures, body parts, damage types, special effects, visibility, and Rhai rule mods can turn Swarm from “one game” into a server ecosystem. This can create Minecraft-like community variety:
- beginner worlds;
- hardcore logistics worlds;
- PvE survival worlds;
- Arena ladders;
- experimental modded rule sets;
- AI-only bot leagues.

That is a strong long-term retention engine if paired with good discovery and governance tools.

### S5 — Replay, spectate, and privacy are already present
The visibility model explicitly mentions `public_spectate`, `spectate_delay`, and `replay_privacy`. This is essential for community spread, tournament legitimacy, learning, and content creation.

---

## Issues by Severity

## Critical / Blocker

### G1 — The first-hour experience is not designed yet
The document describes the engine and world rules in depth, but not the player’s first hour.

Missing questions:
- What does a new player see after account creation?
- What is their first successful action within 2 minutes?
- Do they start with a working bot template?
- What does “success” look like in the first 10, 30, and 60 minutes?
- When does the player first experience the “I wrote code and the world changed” dopamine hit?
- How are compile errors, invalid commands, fuel exhaustion, and rejected actions explained?
- How does a non-Screeps veteran learn body parts, resources, spawning, harvesting, transfer, building, and controller upgrading?

Risk: the game may be technically powerful but feel like “read 80 pages and debug JSON before fun starts.” For a programming MMO, onboarding is not a secondary concern; it is the main funnel.

Recommendation:
Add a dedicated section: “First Hour Player Journey.” Suggested milestones:
1. Spawn into Tutorial World with full vision and safe rules.
2. Run a preloaded starter WASM bot.
3. Watch first drone harvest and transfer energy.
4. Edit one line: target resource/source/role threshold.
5. Deploy and see visible improvement.
6. Build first Extension.
7. Upgrade Controller to RCL2.
8. Receive first replay/debug explanation: “your drone failed because it had no Carry part.”
9. Graduate into Beginner World or Arena sandbox.

Acceptance bar: a player should be able to feel smart and successful before they understand the whole system.

### G2 — Complexity budget is too high for the default game
The design includes dynamic resources, dynamic structures, damage types, resistances, special attacks, global/local storage, progressive taxes, logistics interception, body parts, custom actions, mods, visibility modes, RCL, code propagation, memory upkeep, and more.

Each subsystem is individually interesting. Together, they risk overwhelming both players and implementers. The current document does not clearly separate:
- default launch rules;
- advanced optional rules;
- modded-world examples;
- future expansion ideas.

Risk: the MVP becomes unfocused, and new players cannot form a stable mental model.

Recommendation:
Define a “Default Vanilla Swarm” ruleset with a strict complexity budget:
- one resource: Energy;
- no custom damage types beyond basic Attack/Ranged/Heal initially;
- no special attacks in beginner/default worlds;
- global storage either disabled or simplified in Tutorial;
- local logistics introduced only after basic harvest/spawn/build loop;
- RCL1–3 only for MVP progression;
- mods disabled in official beginner worlds.

Move exotic mechanics such as Hack, Drain, Overload, Debilitate, Psionic/EMP/Sonic/Corrosive, Fabricate, custom action registration, and multi-resource economies into “Advanced Worlds / Future Modules,” unless they are required for Phase 1.

## High Severity

### G3 — Core engagement loop is implied, not explicitly specified
The design has many systems, but the repeatable fun loop is not cleanly stated.

A strong loop could be:
Observe → Diagnose → Edit Strategy → Deploy → Watch Outcome → Inspect Trace → Improve → Expand/Compete.

The document covers Deploy, simulation, and trace infrastructure, but not the player-facing feel of Observe, Diagnose, Watch Outcome, or Improve.

Risk: players spend more time fighting tooling than enjoying optimization.

Recommendation:
Add a “Core Loops” section with separate loops for:
- Micro loop: each tick’s command outcomes and rejected-command feedback.
- Coding loop: edit, validate, deploy, compare before/after metrics.
- Economic loop: harvest, store, spawn, build, upgrade.
- Strategic loop: scout, expand, defend, specialize, trade, attack.
- Social loop: spectate, replay, fork strategy, challenge, tournament.

### G4 — Debugging and feedback are underspecified as game feel
For this genre, debugging is part of game feel. The document lists tools such as `swarm_explain_last_tick`, `swarm_profile`, `swarm_dry_run_commands`, and TickTrace, but it does not define the UX quality bar.

Important player-facing questions:
- Does each rejected command have a human-readable explanation?
- Can the player click a drone and see “planned / attempted / succeeded / failed” for the last tick?
- Can they compare two deployments over time?
- Can they set breakpoints or watch expressions in a simulated tick?
- Can they time-travel a replay and inspect state diffs?
- Can AI players retrieve enough docs and schema through MCP to self-correct without web browsing?

Recommendation:
Add a “Debugging as Gameplay” section. The UI should make failure legible:
- command timeline per drone;
- rejection reasons with suggested fixes;
- fuel flamegraph/profile;
- before/after deployment metric cards;
- replay scrubber with entity selection;
- “why did this drone idle?” explanation.

### G5 — Strategic depth may become opaque rather than readable
Many mechanics are deep, but some are hard to reason about from player intuition:
- special attacks use multiple resistance types and success formulas not fully described;
- `damage_multiplier` affecting special attack success/effect is unintuitive;
- Hack turns a drone Neutral for 5 tick then restores owner, which may feel less like “hack” and more like temporary stun/confusion;
- global/local storage includes conversion, cost, time, privacy, interception, and tax in one subsystem;
- code propagation speed can be strategically interesting but may be frustrating if poorly visualized.

Risk: high-skill players may enjoy it, but average players will not understand why they lost.

Recommendation:
For every major mechanic, add three things:
1. Player-facing explanation in one sentence.
2. Example scenario.
3. Counterplay.

Example:
“Overload reduces enemy CPU temporarily; counterplay is EMP resistance, redundant low-fuel fallback code, or Fortify.”

### G6 — Long-term progression beyond room/controller level is weak
The prompt asks: besides GCL and room level, what are the long-term pursuits? The current design has RCL-like room progression and world/mod variety, but not enough persistent aspiration for players.

Potential long-term goals are underdeveloped:
- strategy library/version history mastery;
- league/tournament ranking;
- public bot reputation;
- mod/world ownership;
- alliance diplomacy;
- market/economy dominance;
- achievement/challenge ladder;
- research/unlocks that do not create pay-to-win or snowball issues;
- cosmetics/profile identity;
- public replay portfolio.

Recommendation:
Add a “Long-Term Player Motivation” section. Suggested axes:
- Competitive: Arena rating, seasonal leagues, bot ELO, challenge badges.
- Creative: publish strategy modules, SDK packages, templates, mods.
- Social: alliances, team arenas, shared replay annotations.
- Mastery: optimization benchmarks, fuel-efficiency records, puzzle worlds.
- Collection/identity: profile page, bot lineage, world trophies, cosmetic drone skins for spectators only.

## Medium Severity

### G7 — World vs Arena split is strong but needs product framing
The table in §10 is good, but the document should be clearer about which mode is the primary new-user experience.

World mode is emotionally sticky but unfair. Arena mode is fair but less persistent. New players may need both:
- Tutorial World for learning;
- Beginner Persistent World for attachment;
- Arena Puzzles for fast feedback;
- Ranked Arena after competency.

Recommendation:
Define entry paths:
- “I want to learn programming” → guided Tutorial + puzzles.
- “I want to optimize bots” → Arena ladder.
- “I want a persistent empire” → World server.
- “I want to watch AI wars” → public Arena/replay browser.

### G8 — Spectator and replay sharing need to become first-class community loops
The document has privacy controls, but not a sharing product.

For community spread, Swarm needs shareable artifacts:
- replay links with timeline and camera bookmarks;
- “bot vs bot” match pages;
- post-match stats cards;
- embeddable GIF/video clips;
- annotated replays for tutorials;
- public strategy writeups linked to versions;
- weekly “best battle / most efficient bot / weirdest mod” highlights.

Recommendation:
Add “Replay and Spectator Experience” as a top-level design concern, not just a config table. Arena mode should default to producing shareable public replay pages.

### G9 — AI players can query docs, but learnability via MCP is not fully proven
The design includes `swarm_get_docs`, `swarm_get_schema`, `swarm_get_world_rules`, and available actions. That is promising. But an AI agent needs task-oriented resources, not just raw schemas.

Missing MCP learning resources:
- “getting_started” guide;
- minimal working bot examples per language;
- world-specific objective summary;
- current bottleneck diagnosis;
- common rejection reason explanations;
- allowed commands with examples using currently visible entity IDs;
- tutorial task state.

Recommendation:
Ensure MCP resources answer: “What should I do next?” not only “What APIs exist?” Add curated MCP docs/resources:
- `swarm_get_tutorial_step`
- `swarm_get_strategy_examples`
- `swarm_explain_objective`
- `swarm_get_common_failures`

### G10 — Default numbers are placeholders but read as final balance
The document lists many numbers: RCL progress, drone caps up to 500 per room, costs, cooldowns, damage, tax rates, fuel reduction values, lifespan, tick length, etc. These may be acceptable as draft values, but the document does not label them as tuning targets or balance hypotheses.

Risk: implementers may hard-code untested balance into the MVP; reviewers may debate numbers before fun is validated.

Recommendation:
Mark numeric values as “initial tuning candidates” and define balance goals:
- time to first drone;
- time to first Extension;
- time to RCL2/RCL3;
- expected drones per beginner room after 1 hour/day/week;
- acceptable idle/failure rate for starter bot;
- average Arena match length;
- comeback window after losing a skirmish.

## Low Severity / Polish

### G11 — Some terminology may confuse new players
“Drone,” “Controller,” “RCL,” “global storage,” “world storage,” “fuel,” “body part,” “CommandAction,” “special effects,” “MCP,” “WASM” all appear quickly.

Recommendation:
Add a player-facing glossary separate from implementation terms. Consider hiding terms like ECS, CommandAction, Rhai, and FoundationDB from player-facing docs unless in advanced/modder sections.

### G12 — The design document mixes game design, architecture, implementation, and product roadmap
This is useful for alignment, but it makes the game design harder to review. Player experience concerns are buried inside architecture.

Recommendation:
Split or add clear front sections:
1. Player Fantasy
2. Target Audiences
3. First Hour
4. Core Loops
5. Default Ruleset
6. Progression and Social Systems
7. Advanced/Modded Systems
8. Technical Architecture

---

## Missing Design Content

### M1 — Target audience and skill ladder
Define intended audiences:
- programming beginners;
- Screeps veterans;
- competitive bot authors;
- AI-agent experimenters;
- server/mod creators;
- spectators.

Each audience needs different onboarding and retention.

### M2 — Tutorial design
The document mentions Tutorial worlds only briefly. It needs a full tutorial ladder:
- no-code observe mode;
- run starter bot;
- edit constants;
- write first role split;
- debug rejected command;
- spawn body variants;
- build/upgrade;
- defend;
- scout;
- enter Arena.

### M3 — Starter bot templates
A programming game needs “playable before programmable.” Provide default bots:
- TypeScript basic harvester/builder/upgrader;
- Rust equivalent;
- minimal WASM “do nothing but valid” bot;
- Arena starter bot;
- commented examples for each body part/action.

### M4 — Loss, recovery, and anti-frustration design
Persistent PvP games need explicit safety valves:
- what happens after wipeout;
- how beginner protection works;
- how griefing is limited;
- how players relocate;
- whether inactive players decay;
- how much progress is lost;
- whether private/safe learning worlds exist.

### M5 — Social systems
Missing or underdeveloped:
- alliances;
- team ownership/permissions;
- diplomacy/truces;
- public profiles;
- bot/version pages;
- strategy sharing/forking;
- mod marketplace governance;
- server discovery.

### M6 — Spectator UX and content creation
Replay privacy is specified, but not the actual viewer experience:
- match summary;
- timeline events;
- camera bookmarks;
- heatmaps;
- economic graph overlays;
- code version markers;
- shareable highlights.

---

## Fresh Ideas

### F1 — “Bot Garage” as the home screen
Instead of starting from the map, start from the player’s bot as a living artifact:
- current deployed version;
- last tick health;
- fuel usage;
- failed command count;
- economic trend;
- “watch latest replay”;
- “run simulation”;
- “deploy safely.”

This reinforces that the player is designing an autonomous organism, not just playing a map.

### F2 — Replay-driven learning
After every meaningful failure, generate a mini lesson:
- “Your drone reached the source but had no Work part.”
- “Your hauler is idle because no storage target is in range.”
- “Your attack failed because target is behind rampart / out of range / safe mode.”

Let players click “show me in replay.”

### F3 — Public bot cards
Each public bot/version gets a shareable card:
- language;
- age;
- Arena rating;
- favorite body composition;
- average fuel/tick;
- best match replay;
- author notes;
- fork button.

This creates community identity around code artifacts.

### F4 — Puzzle/Arena ladder for fast dopamine
Persistent worlds are slow. Add short deterministic challenges:
- harvest optimization puzzle;
- pathfinding puzzle;
- defend for 500 ticks;
- break a tower defense;
- win with limited fuel;
- multi-resource logistics challenge.

These become onboarding, benchmarks, and shareable competitions.

### F5 — Strategy module ecosystem
Encourage players to publish reusable strategy packages:
- pathing module;
- role scheduler;
- spawn planner;
- market trader;
- defense planner;
- replay analyzer.

This makes the community productive even for players who are not top Arena competitors.

### F6 — “What changed after deploy?” diff view
Every deployment should produce a visible comparison:
- command success rate before/after;
- energy per tick;
- idle drone percentage;
- fuel/tick;
- distance traveled;
- spawn uptime;
- combat damage dealt/taken.

This turns code deployment into a satisfying feedback event.

### F7 — Delayed public spectating as default Arena virality
Arena matches should automatically create public delayed spectator pages with:
- fog removed for viewers;
- commentary timeline;
- player code version names, not necessarily source code;
- highlight markers for first contact, first kill, base breach, economic swing.

This can make Swarm watchable even to people who cannot read the code.

---

## Final Recommendation

CONDITIONAL_APPROVE.

The design is strong enough to proceed as a strategic/technical direction, but it should not be considered game-design-complete. Before implementation locks in the player-facing product, add the missing PX layer:

1. First-hour journey.
2. Default vanilla ruleset and complexity budget.
3. Core engagement loops.
4. Debugging/replay UX as game feel.
5. Long-term progression beyond RCL/GCL.
6. Spectator/community sharing design.
7. AI-learnability resources through MCP.

If these are added, Swarm’s design could support both deep expert play and a much broader community than Screeps-style programming games usually reach.
