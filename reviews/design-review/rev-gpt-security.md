# Design Review — Security Perspective (rev-gpt-security)

Reviewer: rev-gpt-security (Security)
Scope: /data/swarm/docs/design/DESIGN.md
Focus: game DESIGN, not spec compliance

VERDICT: CONDITIONAL_APPROVE

Summary:
The design has a coherent and unusually strong baseline for competitive programmability: all players submit WASM through the same path, mutating operations are deferred into validated commands, deterministic replay is explicit, and Arena mode correctly separates fairness goals from persistent World asymmetry. The main blockers are not architectural collapse points; they are game-mechanics exploit surfaces that need sharper invariants before implementation, especially global/local storage transitions, custom rule/mod effects, special attacks, and first-come conflict resolution. These are fixable in design without changing the core premise.

Critical Issues:
None identified.

High Issues:

1. Global/local storage creates multiple resource-duping and temporal-accounting attack surfaces

The design introduces Player Storage, World Storage, in-transit conversion, market orders, Terminal trading, transfer costs, transfer times, and interception. This is a rich system, but it currently lacks hard invariants that prevent double-spend and duplication across asynchronous state transitions.

Concrete exploit patterns to guard against:
- Start local→global conversion, then spend or transfer the same local resource before conversion finalizes.
- Create a market order from global balance while the same balance is locked for code update cost, upkeep, or transfer_from_global.
- Intercept an in-transit resource while the source or destination still receives a refund/credit due to cancellation, rollback, owner change, or structure destruction.
- Destroy/capture a Storage/Terminal during conversion and trigger ambiguous ownership of the locked resource.
- Replay/rollback around FDB tick commits if conversion state is not part of the canonical tick state.

Why it matters:
This is the highest-value exploit class in MMO economies. If a persistent-world economy permits even rare duplication, dominant players or botnets will convert it into runaway snowballing and market capture.

Required design hardening:
- Define a canonical resource state machine: available → reserved → in_transit → settled / lost / refunded.
- Every resource amount must be in exactly one ledger bucket at any tick.
- All spend paths must consume from available only; market orders, conversions, spawn/build, upkeep, and code deploy must reserve atomically.
- In-transit resources must have owner, source, destination, amount, expiry, and finalization rules in canonical world state.
- Destruction, capture, rollback, disconnect, respawn, and world shutdown must have deterministic settlement rules.
- Add a conservation invariant: sum(player available + reserved + in_transit + world local + dropped + burned/taxed history) changes only through declared sources/sinks.

2. Rhai rule mods are treated as trusted, but their gameplay authority is too broad for competitive or public servers

The design says Rhai mods are “服主自行安装，可信”, then exposes actions such as award_resource, deduct_resource, damage_entity, set_entity_flag, add damage/body/action behavior, and special handlers. From a pure trust-model perspective this is coherent for private servers, but for competitive modes or public ranked worlds it is insufficiently constrained: a trusted mod can create arbitrary imbalance, hidden advantages, resource injection, or grief mechanics while still being “valid”.

Exploit/grief patterns:
- A mod awards resources to a subset of players based on opaque logic.
- A mod sets flags that interact with immunity/resistance and creates unkillable units.
- A mod uses state.players() aggregation or player.resources() to implement targeted rubber-banding or targeted punishment.
- A mod changes upkeep or decay in ways that silently favor already-established players.
- A mod handler creates non-conservative resource or entity transformations.

Required design hardening:
- Separate mod trust tiers by game mode:
  - Arena ranked: no arbitrary Rhai, only audited/allowlisted rule packs with fixed hashes.
  - Arena custom/unranked: arbitrary mods allowed but clearly marked non-ranked.
  - World public: server policy decides, but mods must be fully disclosed with source hash and active config.
- Define a capability manifest per mod: can_award_resource, can_damage_entity, can_change_ownership, can_set_flags, can_read_economy, etc.
- Add per-action conservation and ownership validators, not only call-count budgets.
- Include mod source hash + config hash in replay and tournament commitments.
- Require deterministic mod ordering and conflict resolution when multiple mods touch the same entity/resource.

3. Special attack design risks dominant grief strategies and denial-of-control loops

The special attacks are interesting, but several effects target control, CPU budget, resources, and command order rather than HP. These are historically high-risk mechanics because they create “you do not get to play” loops.

Primary concerns:
- Overload reduces another player’s fuel budget by 5%, down to 20%. Coordinated attackers can keep a target near the floor, suppressing defensive logic and recovery.
- Hack turns a drone Neutral, stops WASM, stops fuel, and pauses lifespan. Even if temporary, repeated Hack/control-lock chains can deny control without normal attrition costs.
- Drain steals resources every tick and can become a snowball amplifier if attack cost is lower than expected stolen value.
- Scramble_commands changes next-tick command order; if exposed in default or mods, it attacks determinism/fairness perception and can invalidate carefully sequenced strategies.
- Fortify clears all negative statuses and halves all resistance multipliers; if stackable or chainable, it may become the default mandatory defensive meta.

Required design hardening:
- Define status stacking, refresh, immunity windows, and diminishing returns globally.
- Add per-target cooldowns, not only per-attacker cooldowns, for control effects.
- Overload should have a short duration, explicit recovery, and a hard cap on aggregate incoming effect per player per window.
- Hack should not pause lifespan unless there is a clear anti-abuse reason; pausing creates stalling exploits.
- Drain must be value-capped by attacker investment, target defenses, carry capacity, and risk exposure.
- Tournament/ranked modes should start with a minimal special-effect set and graduate effects only after balance testing.

4. First-come resource conflict resolution by shuffled player order can decide outcomes too strongly

Phase 2a applies commands inline by shuffled player order and current world state, with resource competition “先到先得”. The seed is deterministic and fair in the cryptographic sense, but first-come resolution can still create high-variance gameplay if many contested actions are binary: harvesting the last unit, claiming a controller, landing a killing blow, withdrawing from storage, or occupying a chokepoint.

Risk:
A random order advantage can become a dominant strategy if players flood cheap commands to maximize chance of winning first-come races, or if one lucky tick flips a large accumulated strategic position.

Required design hardening:
- Classify commands by conflict semantics: commutative/pro-rata, exclusive, positional, combat, economic.
- Use pro-rata or simultaneous resolution where appropriate, especially harvesting shared sources, market fills, and same-tick damage/heal.
- Preserve shuffled order only for truly exclusive conflicts where randomness is intended.
- Add per-entity/per-tick action caps to prevent command flooding as a lottery amplifier.
- Record conflict outcomes in TickTrace for audit and balance analysis.

Medium Issues:

1. Anti-snowball mechanisms exist but are incomplete outside global storage

Strengths include global storage tax, local-storage stealth, transport delay, drone lifespan, controller upkeep concepts, hard room drone cap, and example empire-upkeep mod. However, the base World defaults still include free code updates, instant code propagation, global storage enabled, and no mandatory empire upkeep in the core rules.

Risk:
A large early empire may compound via better economy, more map control, more intelligence, more market influence, and more compute-effective strategy while paying only weak carrying costs.

Recommended changes:
- Make at least one empire-size cost part of the default World rules, not merely an optional mod: per-room upkeep, controller upkeep, logistics distance cost, or diminishing source efficiency.
- Add newbie/restart protection beyond Tutorial: protected spawn regions, grace timers, or matchmaking by world age/power band.
- Add anti-monopoly source placement or expansion friction: distance-based logistics, controller maintenance, or territory adjacency requirements.
- Define market anti-manipulation controls: order fees, cancellation fees, position limits, or delayed settlement.

2. Arena fairness guarantees need stronger commitment semantics

The design correctly states Arena uses symmetric fixed spawns, simultaneous start, locked code, public replay, and same rules. But competitive fairness also needs commit/reveal and environment immutability.

Recommended additions:
- Tournament precommit should bind: WASM module hash, SDK version, compiler profile if relevant, world rules hash, map seed/hash, mod hashes, engine version, Wasmtime version, and initial state hash.
- No code deploy/rollback after lock except explicitly declared between-match phases.
- Identical fuel, memory, command-count, and host-function budgets for all participants.
- Deterministic map generation must be symmetric by construction, not just fixed spawn positions.
- Spectate delay must be mandatory and non-zero for live Arena if participants can receive external information.

3. Host query functions can become DoS multipliers despite fuel metering

The design says read-only host functions count against fuel but not command budget. host_path_find and range queries can be expensive on the server side compared with the small WASM call that triggers them.

Risk:
A minimal WASM loop can force large pathfinding/range-query work, causing server-side tick pressure or giving high-level languages indirect compute beyond intended fuel.

Recommended additions:
- Add host-function-specific budgets: calls/tick, max radius, max returned objects, path length/search nodes, cache policy.
- Charge fuel or separate “query credits” proportional to actual server work, not just WASM instructions.
- Make pathfinding deterministic and bounded; return partial/failure deterministically when budget is exhausted.
- Include query cost metrics in tick_metrics.

4. Command JSON and dynamic registries need schema-level abuse limits

The design supports dynamic resources, body parts, damage types, custom actions, env vars, and JSON command output. This is flexible, but creates parser/memory bombs and edge cases.

Recommended additions:
- Hard limits for Command[] length, command JSON byte size, string lengths, resource map entries, nested object depth, env var count, and per-drone memory writes.
- Canonical JSON representation for replay hashing and command deduplication.
- Reject unknown fields or define exact forward-compat behavior.
- Use u64/i64 carefully for amount multiplication; specify overflow behavior as reject, never saturating silently unless explicitly intended.

5. Recycling and drone lifespan have exploitable boundary cases

Recycle refunds 50%, Tutorial refunds 100%, and drone lifespan can be offset by controllers. These are reasonable, but exact timing matters.

Potential exploits:
- Spawn/recycle loops to convert resource types or bypass local/global movement costs.
- Recycle just before death to recover value repeatedly if lifespan maintenance is cheap.
- Tutorial 100% refund accidentally connected to standard worlds or markets.
- Controller-based global age rollback favors large empires and may become a snowball mechanic if “all global drones” benefit from many controllers.

Recommended additions:
- Refund only original paid resources, after depreciation, and never refund externally granted/temporary parts.
- Ensure Tutorial worlds are economically isolated.
- Cap lifespan extension per drone and consider local/controller-radius maintenance instead of global benefit.
- Define exact phase ordering: age increment, controller rollback, death marking, recycle settlement.

6. Visibility model is good, but debug/MCP tools risk information leaks

The design separates drone snapshot, player view, public spectate, replay privacy, and delayed spectating. However, tools like swarm_inspect_entity, swarm_explain_last_tick, swarm_profile, swarm_dry_run_commands, and replay views need the same visibility rules.

Recommended additions:
- Every debug/MCP endpoint must declare visibility tier and redaction rules.
- explain_last_tick must not reveal hidden enemy commands or hidden resource balances unless already visible or delayed/public by policy.
- profile should not leak opponent CPU/fuel internals in live competitive matches unless symmetric and intended.
- Dry-run must not become an oracle for hidden state.

7. Supply-chain and dependency risk should be included in the game trust model

The design depends on Wasmtime, rmcp, Rhai, Bevy, FoundationDB, Dragonfly, NATS, SDK toolchains, and a mod marketplace. Even if implementation security is not the primary review target, game fairness depends on pinning and reproducibility.

Recommended additions:
- Pin engine, Wasmtime, Rhai, SDK, and mod versions per world/tournament.
- Record dependency versions in replay metadata.
- Mod marketplace should require source hash, signature, author identity, and review status.
- Ranked worlds should disallow auto-update of mods or engine minor versions mid-season.

Informational Issues:

1. “World does not pursue fairness” is acceptable, but should not mean “no abuse controls”

The World/Arena split is conceptually strong. Persistent worlds can be asymmetric and emergent. Still, grief resistance, economy conservation, spawn protection, and anti-monopoly controls are necessary for retention and server health even when strict fairness is not promised.

2. “Fair CPU by fuel” is necessary but not sufficient

Fuel metering fairly measures WASM instructions. It does not automatically equalize host-function cost, language runtime memory behavior, module initialization cost, snapshot parse cost, or command validation cost. These should be budgeted explicitly.

3. Default parameters need balance simulation

Many values are plausible but unproven: RCL thresholds, drone caps, storage tax rates, transfer times, special attack costs/cooldowns, fuel reduction, controller downgrade, lifespan, and upkeep examples. Before public play, run adversarial simulations for hoarding, zerg rush, turtle defense, drain farming, Overload lockdown, and market manipulation.

Strengths:

1. Coherent AI/human trust model

The design correctly avoids a separate privileged AI action interface. Human players and AI agents both produce WASM, and MCP is positioned as management/observation/deployment rather than direct gameplay control. This removes an entire class of fairness and authorization bugs.

2. Deferred command model is the right security boundary

Forbidding mutating host functions and requiring tick() → Command[] gives the engine a central validation point. This is the correct design for replayability, anti-cheat, and resource accounting.

3. Determinism is treated as a first-class game feature

The design specifies fixed PRNG/hash, IndexMap instead of HashMap iteration, fixed ECS ordering, no f64, replay checksums, and pinned Wasmtime for replay. This is stronger than typical game-engine design docs and directly supports competitive audits.

4. World vs Arena separation is healthy

The document explicitly distinguishes persistent emergent play from competitive fairness. This avoids trying to make one mode satisfy incompatible goals and gives room for both MMO creativity and tournament integrity.

5. Global storage anti-dominant-strategy section is directionally good

Progressive storage tax, local stealth, and non-instant transfers are good anti-hoarding mechanisms. They need stronger accounting invariants, but the gameplay instinct is correct.

6. Rhai mod budgets and transaction rollback are good foundations

Node/action/call/time budgets, deterministic restrictions, no file/network/time/random, and rollback-on-timeout are the right primitives. The missing piece is capability restriction and ranked-mode policy, not the basic choice of a lightweight scripting tier.

7. Visibility design recognizes the difference between player UX and drone perception

Separating drone snapshot fairness from Web/MCP/spectator views is important and well captured. With stricter endpoint redaction rules, this can become a strong anti-leak model.

Recommended Conditions for Approval:

1. Add a formal resource ledger/state-machine section covering available/reserved/in_transit/settled/burned and conservation invariants.
2. Define ranked Arena trust policy: fixed engine, fixed rules, fixed mod allowlist, hash commitments, non-zero spectate delay, immutable code after lock.
3. Add host-function/query budgets proportional to server work, especially pathfinding and object-range queries.
4. Define global status-effect stacking, immunity, aggregate caps, and anti-lockout rules before implementing Overload/Hack/Drain/Fortify.
5. Add command and JSON size limits, canonicalization, overflow behavior, and per-tick command caps.
6. Define Rhai mod capability manifests and separate trusted-private, public-world, and ranked-Arena mod policies.
7. Make at least one anti-snowball empire-cost mechanism part of the default World rules, not only an optional example mod.

Final Verdict Rationale:
CONDITIONAL_APPROVE because the central security/fairness architecture is sound: same WASM path for all players, deferred commands, deterministic replay, and clear World/Arena separation. However, several game-mechanics systems are currently powerful enough to create economy duplication, control-denial griefing, or ranked fairness disputes unless their invariants are specified before implementation. The design should proceed after the above conditions are incorporated into DESIGN/specs and validated through adversarial balance simulations.
