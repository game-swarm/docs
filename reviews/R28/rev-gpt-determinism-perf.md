# R28 GPT Determinism & Performance Closure Verification

Reviewer: GPT Determinism & Performance
Scope: R27 fixes only — B4 / T-H1 / ML-3 / ML-4 / ML-5

## Verdict

PARTIALLY_CLOSED

4/5 items are closed in the reviewed documents. ML-5 remains not closed because the tick protocol still specifies sequential `Dragonfly.update(delta)` followed by `NATS.publish(...)`, not parallel execution. One additional documentation conflict affects ML-4 authority: `04-wasm-sandbox.md` defines a fixed cache-miss penalty, while `api-registry.md`'s authoritative fuel table omits it.

## Item Verification

### B4 — capacity benchmark-gated / worker pool timeout wording

Status: PASS

Evidence:
- `/tmp/swarm/docs/specs/reference/api-registry.md:534` defines target active players as 500 and says actual capacity is determined by stress testing.
- `/tmp/swarm/docs/specs/reference/api-registry.md:535` marks hard cap players 1000 as `benchmark-gated` and admission-gated/degraded when exceeded.
- `/tmp/swarm/docs/specs/reference/api-registry.md:536` defines worker pool size as `min(max_pool, active_players)`.
- `/tmp/swarm/docs/specs/reference/api-registry.md:537` defines runtime worker pool max 256.
- `/tmp/swarm/docs/specs/reference/api-registry.md:538` defines worker pool hard cap 1000.
- `/tmp/swarm/docs/specs/core/01-tick-protocol.md:126` defines `collect_timeout_ms = 2500` as hard cutoff.
- `/tmp/swarm/docs/specs/core/01-tick-protocol.md:128`-`/tmp/swarm/docs/specs/core/01-tick-protocol.md:131` define timeout handling as empty commands plus timeout metric.
- `/tmp/swarm/docs/specs/core/01-tick-protocol.md:134` states a stuck player does not block the world and timed-out output is discarded for the current tick only.
- `/tmp/swarm/docs/specs/core/04-wasm-sandbox.md:41` defines long-lived worker pool with per-tick Store reset.
- `/tmp/swarm/docs/specs/core/04-wasm-sandbox.md:43` explains fork-per-tick cost at 500 players and worker pool timeout/isolation rationale.

Assessment: Closed. Benchmark-gated capacity is explicitly in the authoritative registry, and worker pool / timeout semantics are clear enough for deterministic tick closure.

### T-H1 — Arena commit-reveal + World operator seed-bump + statistical detection

Status: PASS

Evidence:
- `/tmp/swarm/docs/specs/core/01-tick-protocol.md:260` introduces the R27 seed lifecycle/leakage fix.
- `/tmp/swarm/docs/specs/core/01-tick-protocol.md:262` states the core determinism constraint: true cryptographic forward secrecy is impossible in deterministic replay systems.
- `/tmp/swarm/docs/specs/core/01-tick-protocol.md:264` states the split solution: Arena uses commit-reveal, World uses operator seed-bump.
- `/tmp/swarm/docs/specs/core/01-tick-protocol.md:272`-`/tmp/swarm/docs/specs/core/01-tick-protocol.md:274` define Arena secure seed generation and public commitment.
- `/tmp/swarm/docs/specs/core/01-tick-protocol.md:276`-`/tmp/swarm/docs/specs/core/01-tick-protocol.md:279` define Arena in-match behavior: RNG derives from hidden seed, only commitment is exposed.
- `/tmp/swarm/docs/specs/core/01-tick-protocol.md:281`-`/tmp/swarm/docs/specs/core/01-tick-protocol.md:284` define post-match reveal and audit verification.
- `/tmp/swarm/docs/specs/core/01-tick-protocol.md:287`-`/tmp/swarm/docs/specs/core/01-tick-protocol.md:289` define World mode as operator-loss-limiting rather than commit-reveal.
- `/tmp/swarm/docs/specs/core/01-tick-protocol.md:294`-`/tmp/swarm/docs/specs/core/01-tick-protocol.md:299` define statistical detection metrics and FLAG behavior.
- `/tmp/swarm/docs/specs/core/01-tick-protocol.md:306`-`/tmp/swarm/docs/specs/core/01-tick-protocol.md:312` define `swarm_world_seed_bump`, secure-random new seed, compromised old seed marking, and optional rollback.

Assessment: Closed. The document now explicitly separates Arena auditability from World operational response and preserves replay by archiving seed epochs in snapshots.

### ML-3 — randomized ECS entity iteration CI test

Status: PASS

Evidence:
- `/tmp/swarm/docs/specs/core/07-world-rules.md:204` states Bevy ECS does not guarantee archetype/table iteration order.
- `/tmp/swarm/docs/specs/core/07-world-rules.md:204` requires explicit sorting by `entity_id` lexicographic order for all traversals.
- `/tmp/swarm/docs/specs/core/07-world-rules.md:204` adds CI `randomized-entity-iteration` test mode via feature flag.
- `/tmp/swarm/docs/specs/core/07-world-rules.md:204` says the test randomizes Bevy internal storage order, runs deterministic replay scenarios, and asserts `state_checksum` consistency.
- `/tmp/swarm/docs/specs/core/01-tick-protocol.md:642` states command ordering is deterministic under same seed/player set/commands.
- `/tmp/swarm/docs/specs/core/01-tick-protocol.md:643` describes ECS scheduling as strict `.chain()` plus dependency-ordered partial parallelism.
- `/tmp/swarm/docs/specs/core/01-tick-protocol.md:645` forbids `std::HashMap` iteration order and requires `indexmap`.

Assessment: Closed. The randomized storage-order CI requirement directly targets the nondeterministic Bevy iteration failure mode.

### ML-4 — `host_path_find` cache_miss → fixed 2000 fuel

Status: PASS_WITH_CONFLICT

Evidence supporting closure:
- `/tmp/swarm/docs/specs/core/04-wasm-sandbox.md:355` defines `host_path_find` cost as `500 × explored_nodes + 200 × expanded_edges + cache_miss_penalty`.
- `/tmp/swarm/docs/specs/core/04-wasm-sandbox.md:355` explicitly sets `cache_miss_penalty = fixed 2000 fuel` and says it is hardware-independent for cross-node deterministic accounting.
- `/tmp/swarm/docs/specs/core/04-wasm-sandbox.md:355` defines per-player/per-tick limits: 10 calls plus 100,000 explored nodes, with deterministic fail on over-limit.
- `/tmp/swarm/docs/specs/core/04-wasm-sandbox.md:355` defines the cache key `(from, to, terrain_hash, player_visibility_fingerprint)`.
- `/tmp/swarm/docs/specs/reference/host-functions.md:38`-`/tmp/swarm/docs/specs/reference/host-functions.md:45` define the `host_path_find` signature and per-tick 10-call limit.
- `/tmp/swarm/docs/specs/reference/host-functions.md:61`-`/tmp/swarm/docs/specs/reference/host-functions.md:69` define host call budget and deterministic budget errors.
- `/tmp/swarm/docs/specs/reference/host-functions.md:77` defines `host_path_find` max output as 8 KB.

Conflict evidence:
- `/tmp/swarm/docs/specs/reference/host-functions.md:3` says `game_api.idl.yaml` → `api-registry.md` is the authoritative source.
- `/tmp/swarm/docs/specs/reference/host-functions.md:5` says authoritative definitions are in `api-registry.md` §4.
- `/tmp/swarm/docs/specs/reference/api-registry.md:434`-`/tmp/swarm/docs/specs/reference/api-registry.md:442` defines the authoritative per-call fuel table but lists `host_path_find` only as `500 × nodes` plus `+200 × edges`, with no `cache_miss_penalty` or fixed 2000 fuel.

Assessment: Functionally closed in `04-wasm-sandbox.md`, but authority conflict remains. Because `host-functions.md` delegates authority to `api-registry.md`, implementations generated from the registry may omit the 2000 fuel cache-miss penalty. Treat as PASS_WITH_CONFLICT rather than a clean PASS.

### ML-5 — Dragonfly update and NATS broadcast parallel

Status: FAIL

Evidence:
- `/tmp/swarm/docs/specs/core/01-tick-protocol.md:98`-`/tmp/swarm/docs/specs/core/01-tick-protocol.md:103` still diagrams BROADCAST as ordered steps: compute delta, Dragonfly cache update, then NATS delta publish.
- `/tmp/swarm/docs/specs/core/01-tick-protocol.md:518` names the section `持久化 → 缓存 → 发布`, explicitly sequential in wording.
- `/tmp/swarm/docs/specs/core/01-tick-protocol.md:521`-`/tmp/swarm/docs/specs/core/01-tick-protocol.md:523` lists `Dragonfly.update(delta)` before `NATS.publish("tick.{tick}", delta)`.
- `/tmp/swarm/docs/specs/core/01-tick-protocol.md:526` says BROADCAST failures never roll back committed tick, but does not state Dragonfly and NATS run concurrently.
- `/tmp/swarm/docs/specs/core/01-tick-protocol.md:718` says BROADCAST has no hard wall-clock limit and is asynchronous, but again does not specify Dragonfly/NATS parallel fan-out.
- `/tmp/swarm/docs/specs/core/01-tick-protocol.md:804` states Dragonfly is read cache and NATS/WebSocket is best-effort push, but not that their writes are parallel or independent branches.

Assessment: Not closed. The current text supports asynchronous/non-authoritative broadcast failure semantics, but it still defines a sequential cache-then-publish pipeline. R27's requested closure item was specifically “Dragonfly update 与 NATS broadcast 并行”; that exact dependency relaxation is absent.

## New Documentation Conflicts

### C1 — `host_path_find` cache miss fuel penalty missing from authoritative API registry

Severity: High

- `04-wasm-sandbox.md` defines fixed 2000 fuel for `host_path_find` cache misses at `/tmp/swarm/docs/specs/core/04-wasm-sandbox.md:355`.
- `host-functions.md` says authority is `api-registry.md` at `/tmp/swarm/docs/specs/reference/host-functions.md:3` and `/tmp/swarm/docs/specs/reference/host-functions.md:5`.
- `api-registry.md` omits the cache miss penalty from the authoritative fuel table at `/tmp/swarm/docs/specs/reference/api-registry.md:434`-`/tmp/swarm/docs/specs/reference/api-registry.md:442`.

Impact: Codegen or implementers following the registry can diverge from sandbox accounting, causing cross-node fuel/accounting differences for cache-hit vs cache-miss pathfinding.

## State Machine Gaps

- ML-5 leaves BROADCAST dependency ordering ambiguous/wrong: the state machine still implies `NATS.publish` waits behind `Dragonfly.update`, even though both consume the already-committed delta and failures do not affect the authoritative tick.
- ML-4 has an authority gap between sandbox and registry: the replay/fuel contract is only safe if `api-registry.md` includes the same fixed cache-miss penalty.

## Bottleneck Analysis

- B4 is acceptable for closure: capacity is explicitly benchmark-gated, target/hard-cap are separated, and timeout behavior avoids a slow player blocking the tick.
- T-H1 is acceptable: seed lifecycle now avoids false forward-secrecy claims and defines practical operational response for World mode.
- ML-3 is acceptable: randomized ECS storage-order CI is the right test for hidden archetype/table ordering dependence.
- ML-4 is close but should be patched in the registry to avoid generated/spec-authority drift.
- ML-5 remains a performance bottleneck risk: sequential Dragonfly update before NATS publish can add avoidable broadcast tail latency; the desired fix should describe fan-out from committed delta into independent async tasks, with each failure recorded independently and no rollback path.
