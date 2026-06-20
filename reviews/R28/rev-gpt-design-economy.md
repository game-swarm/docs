# R28 Closure Verification — GPT Design & Economy

## Verdict

PARTIALLY_CLOSED

Scope note: this review only verifies the four R27 closure items requested in task `t_ad6a2cca`. It does not perform a new open-ended design/economy review.

## Item Verification

### D-H2 — `swarm_get_objectives` API in Registry + IDL

Status: PASS / CLOSED

Evidence:
- `/data/swarm/docs/specs/reference/api-registry.md:211` states the registry now has 57 active `game_api` tools.
- `/data/swarm/docs/specs/reference/api-registry.md:228` labels the Game API tool list as `(57)`.
- `/data/swarm/docs/specs/reference/api-registry.md:244` registers `swarm_get_objectives` with input `{player_id?, scope?}`, objective output schema, `5/tick`, `swarm:read`, `read_replay_safe`, owner visibility, and `game_api` source.
- `/data/swarm/docs/specs/reference/game_api.idl.yaml:55` defines the `enum_types` section.
- `/data/swarm/docs/specs/reference/game_api.idl.yaml:56` defines `ObjectiveType`.
- `/data/swarm/docs/specs/reference/game_api.idl.yaml:57` describes `ObjectiveType` as machine-readable for `swarm_get_objectives` and AI planning.
- `/data/swarm/docs/specs/reference/game_api.idl.yaml:58` sets `ObjectiveType.total_variants: 8`.
- `/data/swarm/docs/specs/reference/game_api.idl.yaml:60` through `/data/swarm/docs/specs/reference/game_api.idl.yaml:67` list the 8 variants.
- `/data/swarm/docs/specs/reference/game_api.idl.yaml:657` defines the `swarm_get_objectives` tool.
- `/data/swarm/docs/specs/reference/game_api.idl.yaml:667` uses `type: ObjectiveType` in the objective item schema.

Finding: Registry and IDL are aligned on the new onboarding tool and the machine-readable objective enum.

### E-H1 — Allied Transfer intercept rules

Status: PASS / CLOSED

Evidence:
- `/data/swarm/docs/specs/core/09-snapshot-contract.md:198` starts the Allied Transfer restricted cooperation section.
- `/data/swarm/docs/specs/core/09-snapshot-contract.md:205` defines `allied_transfer_delay = 200 tick`, which bounds the intercept timing model.
- `/data/swarm/docs/specs/core/09-snapshot-contract.md:214` adds `3.2a 运输中拦截（R27 E-H1 — 最终设计）`.
- `/data/swarm/docs/specs/core/09-snapshot-contract.md:216` states transport resources can be intercepted during the 200 tick delay and that this is final design, not an MVP placeholder.
- `/data/swarm/docs/specs/core/09-snapshot-contract.md:218` defines the intercept window as the final 50 ticks, tick 150-200.
- `/data/swarm/docs/specs/core/09-snapshot-contract.md:222` through `/data/swarm/docs/specs/core/09-snapshot-contract.md:228` define attacker location/range, PvP/alliance condition, required parts (`CARRY` or `ATTACK`), per-transfer cooldown, and visibility condition.
- `/data/swarm/docs/specs/core/09-snapshot-contract.md:232` through `/data/swarm/docs/specs/core/09-snapshot-contract.md:235` define steal/destroy outcomes and resource split/destruction behavior.
- `/data/swarm/docs/specs/core/09-snapshot-contract.md:239` through `/data/swarm/docs/specs/core/09-snapshot-contract.md:244` define success formula: base success, extra part bonus, escort penalty, and clamp.
- `/data/swarm/docs/specs/core/09-snapshot-contract.md:246` defines escort defense behavior and explicitly says escort consumes no extra command and takes no damage.
- `/data/swarm/docs/specs/core/09-snapshot-contract.md:248` through `/data/swarm/docs/specs/core/09-snapshot-contract.md:252` define deterministic RNG, TickTrace recording, notifications, and audit fields.

Mapping to requested fields:
- `intercept_range`: covered by location/range rule at line 224 and timing window at line 218.
- `intercept_parts`: covered by required `CARRY`/`ATTACK` at line 226 and part bonus at line 241.
- `intercept_cost`: covered as commandless/costless escort at line 246 and per-attempt cooldown at line 227; no separate explicit resource cost is introduced.
- `escort_interference`: covered by `escort_penalty = 30%` at line 242 and escort behavior at line 246.

Finding: Intercept mechanics are complete enough for design closure. The only nuance is naming: the document expresses `intercept_cost` as no additional escort command/resource cost plus cooldown friction, not as a literal `intercept_cost` parameter.

### ML-6 — World tiers: Tutorial / Novice / Standard / Advanced / Modded

Status: FAIL / GAP

Evidence:
- `/data/swarm/docs/design/gameplay.md:773` introduces Progressive Unlock by world difficulty tier.
- `/data/swarm/docs/design/gameplay.md:775` defines a `世界层级` table.
- `/data/swarm/docs/design/gameplay.md:777` defines `Tutorial`.
- `/data/swarm/docs/design/gameplay.md:778` defines `Novice`.
- `/data/swarm/docs/design/gameplay.md:779` defines `Standard`.
- `/data/swarm/docs/design/gameplay.md:780` defines `Advanced`.
- `/data/swarm/docs/design/gameplay.md:782` says server owners may override unlock strategy through `world.toml`.
- Search evidence: `Modded` does not appear in `/data/swarm/docs/design/gameplay.md`, `/tmp/swarm/docs/design/gameplay.md`, or the required design/spec contract files; the only `Modded` hit found was another R28 review artifact, not a design contract.

Finding: Four tiers are explicitly defined, but the requested five-tier taxonomy is not closed because `Modded` is absent from the design contract. If the intended design is “Advanced covers custom actions; Rhai modding covers Modded implicitly,” the document should say that explicitly and either add a `Modded` row or define why `Modded` is not a separate tier.

Severity: Medium. This is not an engine/economy blocker, but it is a product/onboarding taxonomy gap: AI players and server owners cannot infer whether `Modded` is a separate official tier, an alias of Advanced, or a free-form non-vanilla category.

### ML-7 — `replay_with_source` default false + source map opt-in

Status: PASS / CLOSED

Evidence:
- `/data/swarm/docs/design/gameplay.md:1242` begins the visibility/spectating section.
- `/data/swarm/docs/design/gameplay.md:1252` scopes the table to player view / AI MCP viewing.
- `/data/swarm/docs/design/gameplay.md:1259` defines replay privacy values and defaults `replay_privacy` to `"private"`.
- `/data/swarm/docs/design/gameplay.md:1261` defines `replay_with_source` as `bool` with default `false`.
- `/data/swarm/docs/design/gameplay.md:1261` explicitly says default replay excludes WASM source and source map.
- `/data/swarm/docs/design/gameplay.md:1261` requires player opt-in through `replay_with_source = true`, subject to world config/server policy.
- `/data/swarm/docs/design/gameplay.md:1261` states source map / code line provenance requires compile-time debug symbol embedding as opt-in.

Finding: Replay/code disclosure default is safe and opt-in behavior is explicitly documented.

## New Document Conflicts

- Medium: ML-6 tier taxonomy mismatch. The R28 checklist asks for Tutorial/Novice/Standard/Advanced/Modded, but `gameplay.md` defines only Tutorial/Novice/Standard/Advanced. This creates a small but real UX/API semantics ambiguity for world discovery, onboarding, and AI interpretation of world rules.
- Low: D-H2 source-location mismatch in the task bundle. The required `/tmp/swarm/docs` copy contains `api-registry.md` but not `game_api.idl.yaml`; the authoritative IDL exists under `/data/swarm/docs/specs/reference/game_api.idl.yaml`. This did not block verification, but future closure tasks should include the IDL file in the stated required-read bundle.

## Closure Recommendation

Do one narrow R29/doc-fix pass for ML-6 only: add an explicit `Modded` row to the world tier table or add a short normative sentence that `Modded` is a separate non-vanilla tier enabled by Rhai/world.toml overrides. After that, all four requested items should be closed.
