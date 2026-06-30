# R44 Cross-Cutting Review — glm-5.2

**Reviewer**: rev-glm-cross-cutting (glm-5.2)
**Scope**: All documents under `/data/swarm/docs/` (37 files, excluding `reviews/`)
**Review axes**: Security, Performance, Operational concerns, Edge cases, Missing specs

---

## §1 Critical Findings (blockers)

### CC-C1 — NATS security model entirely unspecified

**Severity**: Critical
**Files**: `design/architecture.md` §7, `specs/core/distributed-sandbox.md` §4, `specs/security/gateway-protocol.md` §6, `RUNBOOK.md` §1

NATS carries two data flows: (1) tick delta broadcast (Engine → Gateway → WebSocket clients) and (2) sandbox dispatch (Engine → Sandbox Container, including player snapshot JSON and WASM module bytes). Neither TLS, authentication, nor ACL configuration for NATS is specified anywhere.

**Impact**:
- An attacker with network access to the NATS cluster can subscribe to `tick.<world_id>.*` and receive all tick deltas, bypassing `is_visible_to` fog-of-war filtering. This leaks every player's entity positions, combat state, and resource data.
- An attacker can inject fake `swarm.tick.{tick}.player.{player_id}.reply` messages, substituting arbitrary commands for any player's WASM output.
- `distributed-sandbox.md` §5 broadcasts raw `module_bytes` and `compiled_native_bytes` via NATS subject `swarm.deploy.{module_hash}` — an attacker can intercept or replace player WASM binaries.

**Fix**: Add a NATS security spec covering: (1) TLS for all NATS connections, (2) NATS user credential authentication (NATS native accounts/users), (3) ACL rules restricting publish/subscribe subjects per role (Engine, Gateway, Sandbox Container), (4) subject namespace isolation. The current design treats NATS as a trusted internal bus but never defines the trust boundary.

---

### CC-C2 — shard-protocol.md contradicts architecture.md on sharding model

**Severity**: Critical
**Files**: `design/architecture.md` §2, `specs/core/shard-protocol.md` §2

`architecture.md` §2 states:
- `shard_id = f(room_x, room_y)` — static coordinate-based sharding, O(1) from config
- "无 cluster、无 leader election、无 gossip"
- "无运行时 coordinator"

`shard-protocol.md` §2 states:
- `shard_assignment = 一致性哈希 (Jump Hash)`
- References `max_rooms_per_shard = 50` with consistent hash ring semantics

These are mutually exclusive: static coordinate partitioning does not use consistent hashing. Jump Hash requires a hash ring and supports dynamic ring membership, which implies runtime coordination — directly contradicting "无运行时 coordinator".

**Impact**: Any implementation following shard-protocol.md would introduce distributed state (hash ring membership) that architecture.md explicitly excludes. Replay determinism depends on stable shard assignment; Jump Hash ring changes during node addition/removal would break entity referencing.

**Fix**: Reconcile by removing `shard-protocol.md`'s Jump Hash model and aligning it with architecture.md's static config-based shard assignment. If dynamic resharding is needed, it must be specified as an operator-initiated config change + engine restart, not a runtime hash ring.

---

### CC-C3 — Snapshot `omitted_categories` exact counts conflict with visibility oracle defense

**Severity**: Critical
**Files**: `specs/core/snapshot-contract.md` §1.2, `specs/security/visibility.md` §10.2

`snapshot-contract.md` §1.2 defines the truncation marker format with exact integer counts:
```json
"omitted_categories": {
    "entities": 47,
    "resources": 12,
    "events": 3
}
```

`visibility.md` §10.2 explicitly states these counts must be bucketed to prevent oracle attacks:
```
| 1-10 | "few" |
| 11-50 | "some" |
| 51-200 | "many" |
| >200 | "extreme" |
```

These two specs directly conflict. The snapshot contract authorizes exact counts; the visibility spec mandates bucketed values to prevent entity-count oracle attacks (attacker observes `omitted_count` changes to infer hidden entity presence/absence).

**Impact**: If the snapshot contract is implemented as written, the visibility oracle defense is bypassable. An attacker drones near a hidden enemy can observe `omitted_categories.entities` changing by exactly 1 when an enemy drone enters/exits their vision range, confirming entity presence even when the entity itself is truncated.

**Fix**: Update `snapshot-contract.md` §1.2 to use the bucketed representation from `visibility.md` §10.2. The `omitted_categories` values must be `enum { "0", "few", "some", "many", "extreme" }`, not `u32`.

---

### CC-C4 — RejectionReason count inconsistency across documents

**Severity**: Critical (cross-cutting consistency)
**Files**: `specs/reference/api-registry.md` §2, `specs/gameplay/api-idl.md` §2 (RejectionReason enum), `design/interface.md` §5.6, `specs/core/command-validation.md` §3

| Document | Stated count |
|----------|:------------:|
| `api-registry.md` §2 header | 46 |
| `interface.md` §5.6 | 48 |
| `command-validation.md` §3 | 48 |
| Actual enum in `api-idl.md` | 46 entries |

The IDL (`game_api.idl.yaml` concept section) lists exactly 46 RejectionReason values. Two design/spec documents claim 48. Any code or test that asserts `RejectionReason::VARIANTS.len() == 48` would fail against the actual IDL, and any documentation referencing "48 codes" misleads implementors.

**Impact**: CI gate compares IDL ↔ Registry ↔ generated code. If a human adds 2 codes to the IDL to match the "48" claim, the wire enum silently expands. If they trust the "46" Registry, interface.md and command-validation.md are wrong.

**Fix**: Update `interface.md` §5.6 and `command-validation.md` §3 to say "46 codes" matching the Registry and IDL. Run CI diff gate to verify all four sources agree.

---

### CC-C5 — Leech resistance type contradicts across three documents

**Severity**: High (cross-cutting consistency)
**Files**: `design/gameplay.md` §Vanilla Action table, `design/gameplay.md` §[[special_effects]], `specs/core/command-validation.md` §10.4, `specs/core/world-rules.md` §7.8

| Document | Leech damage_type | Leech resistance |
|----------|:-:|:-:|
| `gameplay.md` Vanilla Action table | Kinetic | **Kinetic** |
| `gameplay.md` [[special_effects]] | (not specified) | **Corrosive** |
| `command-validation.md` §10.4 | Corrosive (implied by base_damage field) | **Corrosive** |
| `world-rules.md` §7.8 | Kinetic | **Kinetic** |

The `special_effects` definition (`resistance = "Corrosive"`) and `command-validation.md` say Corrosive; the Vanilla Action table and `world-rules.md` say Kinetic. Since Leech causes Kinetic damage (all docs agree on damage_type), the resistance check should logically be Kinetic — but the special_effects TOML says Corrosive.

**Impact**: Implementors following different authoritative sources will produce different combat results. The `special-attack-table.md` is supposed to be the canonical source but I was not directed to evaluate it — this inconsistency must be resolved against that table.

**Fix**: Pick one resistance type (likely Kinetic since Leech causes Kinetic damage), update all four documents to agree, and verify against `special-attack-table.md`.

---

## §2 Design Tensions (inconsistencies, conflicts)

### CC-T1 — Distributed sandbox memory limit (256MB) vs local sandbox (128MB) — undocumented discrepancy

**Files**: `specs/core/distributed-sandbox.md` §6, `specs/core/wasm-sandbox.md` §4.2

`distributed-sandbox.md` §6: `memory.max = 256MB` (per container, one player at a time)
`wasm-sandbox.md` §4.2: `memory.max = 128MB` (per worker process)

The 2x difference is never explained. If the distributed sandbox needs more memory for NATS client + module cache, this should be documented. If it's a typo, the larger limit weakens OOM protection.

**Fix**: Document the rationale or align the values. If distributed sandbox needs 256MB for NATS overhead + module cache, state this explicitly and break down the memory budget.

---

### CC-T2 — PowerSpawn and Nuker build costs conflict between design and spec

**Files**: `design/gameplay.md` §[[structure_types]], `specs/core/world-rules.md` §7.2, `specs/reference/api-registry.md` §10.2

| Structure | gameplay.md | world-rules.md | api-registry.md |
|-----------|:-:|:-:|:-:|
| PowerSpawn | 5000 Energy | 1200 Energy | 1200 Energy |
| Nuker | 100000 Energy | 5000 Energy | 5000 Energy |

`gameplay.md` has PowerSpawn at 5000 and Nuker at 100000; `world-rules.md` and `api-registry.md` have PowerSpawn at 1200 and Nuker at 5000. The 20x difference for Nuker (100000 vs 5000) is a game-breaking economic imbalance depending on which source an implementor follows.

**Fix**: Align `gameplay.md` structure_types with `api-registry.md` §10.2 (the declared authority for BuildCost). The gameplay.md values appear to be stale from a prior design iteration.

---

### CC-T3 — RangedAttack body part cost conflict

**Files**: `design/gameplay.md` §[[body_part_types]], `specs/core/world-rules.md` §7.1, `specs/gameplay/api-idl.md` §body_cost

| Document | RangedAttack cost |
|----------|:-:|
| `gameplay.md` | 150 Energy |
| `world-rules.md` | 100 Energy |
| `api-idl.md` body_cost | 150 Energy |

`world-rules.md` has 100 Energy for RangedAttack; the other two have 150. This 50% cost difference significantly affects spawn economy.

**Fix**: Align `world-rules.md` with `api-idl.md` (the machine source). Update to 150 Energy.

---

### CC-T4 — Leech cooldown conflict (150 vs 100 tick)

**Files**: `design/gameplay.md` §Vanilla Action table, `specs/core/world-rules.md` §7.8

`gameplay.md`: Leech cooldown = 150 tick
`world-rules.md` §7.8: Leech cooldown = 100 tick

The special-attack-table.md should be canonical, but the two design docs disagree by 50%.

**Fix**: Resolve against `special-attack-table.md` and align both documents.

---

### CC-T5 — CRL fallback behavior during Auth Service outage undefined

**Files**: `specs/security/command-source.md` §3.4

The CRL check flow says "revocation cache miss 时向 Auth Service 查询" but doesn't specify:
1. Timeout for the Auth Service query
2. Behavior if Auth Service is unreachable (fail-open = allow revoked cert, fail-closed = block all deploys)
3. Cache TTL for negative responses (cert not revoked)

**Impact**: During Auth Service outage, either all deploys fails (fail-closed) or revoked certificates are accepted (fail-open). Neither behavior is specified. Fail-open is a security risk; fail-closed is an availability risk.

**Fix**: Specify the CRL fallback policy: fail-closed with a documented grace period (e.g., "CRL cache valid for 300s; after expiry, new deploys rejected but existing modules continue running").

---

### CC-T6 — Snapshot deep-copy every tick: memory pressure undocumented

**Files**: `specs/core/tick-protocol.md` §2.3, §3.5.6

tick-protocol.md §2.3 shows `deep_copy_bevy_world()` every tick for snapshot + rollback. At 50,000 entities with multiple components each, this is a significant allocation. The Bevy World snapshot is used for both:
1. COLLECT snapshot construction (read-only baseline)
2. EXECUTE rollback (if redb commit fails)

But §3.5.6 says the snapshot is taken "Stage 2a 开始前" — meaning the full Bevy World is deep-copied before every EXECUTE. No memory budget or allocation pattern is specified for this operation.

**Impact**: At 50k entities × ~200 bytes/component × ~5 components avg = ~50MB per snapshot. With snapshot + staging payload + Bevy World itself, peak memory could exceed 256MB. No analysis of memory ceiling is provided.

**Fix**: Add a memory budget analysis for the snapshot operation. Consider copy-on-write or immutable structural sharing to avoid full deep copy. Document peak memory ceiling at target capacity (500 players, 50k entities).

---

### CC-T7 — Cross-shard two-phase combat introduces 1-tick ambiguity in deterministic replay

**Files**: `specs/core/shard-protocol.md` §4.2

Cross-shard combat uses a two-phase protocol with 1 tick latency. The doc claims determinism via logical clock `(tick, shard_priority, entity_id)`, but:
1. `shard_priority` is undefined — what determines shard ordering?
2. The two-phase protocol spans two ticks (intent on tick N, settlement on tick N or N+1?) — replay must reconstruct this exactly.
3. If the attacker_shard and target_shard process at different speeds, the settlement timing is non-deterministic unless strictly tied to tick boundary.

**Impact**: Cross-shard combat replay may diverge if settlement timing depends on anything other than tick boundary. The logical clock is defined but its application to the two-phase protocol is not specified.

**Fix**: Specify that cross-shard combat intents are always resolved at tick N+1 (settlement at the next tick boundary), not asynchronously. Define `shard_priority` as a static config value (e.g., shard_id ascending). Add a cross-shard replay CI test.

---

## §3 Suggestions (improvements, simplifications)

### CC-S1 — Add NATS subject namespace isolation spec

Define a formal subject namespace with per-role ACL:
```
swarm.tick.{world_id}.{tick}           — Engine publish only, Gateway subscribe
swarm.tick.{tick}.player.{player_id}   — Engine publish only, Sandbox subscribe (queue group)
swarm.deploy.{module_hash}             — Engine publish only, Sandbox subscribe
swarm.sandbox.heartbeat.{instance_id}  — Sandbox publish only, Engine subscribe
```
This prevents a compromised sandbox from subscribing to tick deltas or injecting fake deploy broadcasts.

---

### CC-S2 — Add observability spec

The RUNBOOK.md lists 9 metrics but there's no structured observability spec. For a 7x24 MMO-RTS:
- Structured log format (JSON, with `tick`, `player_id`, `shard_id`, `event_type` fields)
- Log retention policy (gameplay logs 30d, security logs 180d, audit logs permanent)
- Distributed tracing (request ID propagation: MCP → Gateway → Engine → Sandbox → redb)
- Alerting rules with severity escalation (tick_duration degradation → degraded mode → page on-call)
- Dashboard templates for Grafana (tick pipeline breakdown, sandbox pool health, redb I/O)

---

### CC-S3 — Specify engine zero-downtime upgrade procedure

No spec exists for upgrading the Engine binary while maintaining tick continuity. For a persistent World mode (7x24), this is operationally critical. Options to spec:
1. **Rolling shard upgrade**: Upgrade one shard at a time, pausing its tick loop, deploying new binary, resuming. Cross-shard migration handles in-flight drones.
2. **Snapshot-restore upgrade**: Take keyframe, stop engine, deploy new binary, restore from keyframe. Downtime = keyframe load time.
3. **Hot module swap**: Currently spec'd only for Bevy Plugin mods, not Engine core itself.

The current design says "运行中不做 tick 级 hot-swap" for mods (engine.md §3.0), but doesn't address Engine binary upgrades.

---

### CC-S4 — Add keyframe file corruption detection

`persistence-contract.md` §10.2 specifies keyframe files as independent files with `canonical_serialize + state_checksum`. But there's no spec for:
1. Keyframe file CRC/hash verification on load (only state_checksum is mentioned, but the file itself can suffer bit rot)
2. Multiple keyframe redundancy (only one keyframe per K=100 ticks; if it's corrupted, replay is broken for that entire range)
3. Keyframe file atomic write verification (tmp + fsync + rename is mentioned but no read-back verification)

**Suggestion**: Add a `keyframe_checksum = Blake3(file_contents)` header to each keyframe file. On load, verify both the file checksum and the embedded `state_checksum`. Maintain 2 redundant keyframe copies (primary + backup) on different storage paths.

---

### CC-S5 — Specify RTO/RPO for disaster recovery

`RUNBOOK.md` §6 lists recovery steps but no time objectives. For a persistent MMO:
- **RPO (Recovery Point Objective)**: Maximum acceptable tick loss. With keyframe every 100 ticks and 3s tick interval, worst case = 300s (5min) of game state loss.
- **RTO (Recovery Time Objective)**: Maximum acceptable downtime. Currently unspecified.

**Suggestion**: Define RPO ≤ 100 ticks (5 min) and RTO ≤ 300s (5 min) as design contracts. Add a CI test that validates recovery time from keyframe within RTO.

---

### CC-S6 — Add sandbox side-channel mitigation spec

The sandbox pool is shared across all players. `wasm-sandbox.md` specifies per-tick Store reset (memory clear, fuel reset, epoch deadline), but:
1. No timing side-channel mitigation (WASM execution time is fuel-bounded but wall-clock varies)
2. No memory residue check beyond "linear memory zeroed"
3. CPU cache state between players is not addressed

**Suggestion**: Document the threat model: "side-channel attacks between players in shared sandbox pool are accepted as a known risk. Mitigation: per-worker 1000-tick recycle limit + independent uid/cgroup." If this is unacceptable, spec per-player sandbox isolation (higher cost).

---

### CC-S7 — Specify anti-cheat statistical detection thresholds

`tick-protocol.md` §7.3 mentions anomaly detection ("状态变化超限", "指令模式异常") but no thresholds, false positive rates, or appeal process. For a competitive game:
- What constitutes "状态变化超过物理上限"? (Specific movement distance, resource rate thresholds)
- What is the false positive rate target? (< 0.1%? < 1%?)
- How does a player appeal a false positive flag?
- What happens to flagged players? (Fuel throttle, full ban, observation mode?)

**Suggestion**: Add a `specs/security/anti-cheat.md` spec with concrete detection rules, thresholds, and the player appeal workflow.

---

### CC-S8 — Add multi-shard operational procedures

No operational spec for:
1. Adding a new shard (config change + engine restart, data migration protocol)
2. Removing a shard (drain entities, reassign rooms)
3. Shard failure recovery (shard crash → entities in that shard frozen → operator intervention)
4. Shard capacity monitoring (when to add a shard — entity count threshold, tick duration threshold)

---

### CC-S9 — Consolidate economic parameter authority chain

Multiple documents define economic parameters with conflicting values (CC-T2, CC-T3, CC-T4). The authority chain is:
```
api-registry.md §10 (generated from IDL) → resource-ledger.md §2 (formula authority) → economy-balance-sheet.md (validation) → gameplay.md/world-rules.md (presentation)
```
But `gameplay.md` and `world-rules.md` contain inline TOML examples with hardcoded values that diverge from the IDL. These inline examples are not CI-gated and can drift silently.

**Suggestion**: Replace all inline TOML examples in `gameplay.md` and `world-rules.md` with references to `api-registry.md` §10.2, or add a CI check that extracts TOML values from design docs and compares against the IDL.

---

### CC-S10 — Add Moka cache capacity and eviction policy spec

`architecture.md` §8 says "Engine 进程内 Moka cache" but no capacity limit or eviction policy is specified. At 500 players:
- Per-player snapshot: 256KB × 500 = 128MB
- World state cache: 50k entities × ~200 bytes = ~10MB
- Tick delta history: 100 ticks × ~500KB = ~50MB

Without a capacity ceiling, the cache grows unbounded until OOM. Moka supports `max_capacity` but it's not configured in any spec.

**Suggestion**: Add `[cache]` section to `world.toml` spec:
```toml
[cache]
moka_max_capacity = 10000  # entries
moka_ttl_seconds = 300
```

---

## §4 Cross-Reference Matrix

| ID | Finding | Suggest checking in direction |
|----|---------|-------------------------------|
| CX-1 | NATS module broadcast sends raw WASM bytes + compiled native code over network — no integrity verification on receive side beyond `compiled_artifact_hash` match, but the broadcast itself has no authentication | → Security direction: verify NATS message-level authentication and module binary integrity on sandbox receive path |
| CX-2 | `Hack` Neutral state (5-tick takeover) — what happens to the Neutral drone's pending `PendingEntityCreation` or resource transfers initiated before Hack? The death/recycle path is specified but Hack-to-Neutral entity state transition is not in the system manifest R/W matrix | → Gameplay direction: verify Hack Neutral state has complete ECS component transition spec in phase2b-system-manifest.md |
| CX-3 | `AlliedTransfer` intercept `transfer_id` generation is unspecified — `Blake3("intercept" \|\| transfer_id \|\| tick \|\| world_seed)` is used for intercept RNG, but how `transfer_id` is created (and whether it's deterministic for replay) is not defined | → Engine direction: verify transfer_id generation is deterministic and recorded in TickCommitRecord for replay |
| CX-4 | `Arena` commit-reveal seed epoch model: the `seed_commitment` is written to "arena public metadata" before match, but the spec doesn't define what happens if the engine crashes between commitment and match end — is the seed lost or recoverable? | → Persistence direction: verify Arena seed epoch survives engine crash/restart |
| CX-5 | `swarm_simulate` deep-copies world state per call (snapshot-contract.md §2.1) — with 3 concurrent simulates per player and 500 players, worst case = 1500 concurrent world copies. No memory budget analysis for this. | → Performance direction: verify simulate fork memory ceiling doesn't cause OOM at scale |
| CX-6 | `world.toml` `code_propagation_speed > 0` causes partial WASM version states across drones — some drones run v1, others run v2 within the same tick. The command validation pipeline validates against current Bevy World, but the WASM module hash varies per drone. Replay must reconstruct which module each drone used. | → Determinism direction: verify per-drone module version is recorded in TickInputEnvelope for replay |
| CX-7 | `Fabricate` converts enemy drone to own structure — this creates an entity type change (Drone → Structure) within a single tick. The system manifest doesn't show a system that handles entity type transmutation. S24/S25 handle death/despawn but not type conversion. | → Engine direction: verify Fabricate entity type transition is in the system manifest or ActionRegistry handler spec |
| CX-8 | The `gateway-protocol.md` §8 says "DNS rebinding 防护: Gateway bind 到 127.0.0.1" but the same doc §2 shows external clients connecting to port 8082. If Gateway only binds to 127.0.0.1, external clients can't connect directly — nginx must be the front. But no spec defines the nginx → Gateway proxy configuration. | → Security direction: verify the nginx TLS termination → Gateway proxy chain is fully specified |
| CX-9 | `Refund Credit` deploy-reset rule (command-validation.md §7.2) clears refund credit on new module manifest commit — but the `session_id` exception ("同一 session 内迭代部署不清除") means a player can maintain a long-lived session to preserve refund credits across module changes. This could be abused. | → Economy direction: verify refund credit session-scoping doesn't create an economic exploit vector |
| CX-10 | `swarm_world_seed_bump` (tick-protocol.md §3.1) generates a new seed from "安全随机源" — but the engine is deterministic and has no access to OS entropy (WASI clock/random disabled). How does the engine obtain external entropy for seed bumping? | → Security/Engine direction: verify operator seed-bump entropy source is spec'd and doesn't break replay determinism |

---

## Verdict

**CONDITIONAL_APPROVE**

The documentation is impressively thorough in most areas — the tick protocol, determinism contract, WASM sandbox isolation, and persistence contract are well-specified with clear authority chains. The major blocking issues are:

1. **CC-C1** (NATS security gap) — a critical operational security hole that must be closed before any production deployment
2. **CC-C2** (sharding model contradiction) — two spec documents define mutually exclusive sharding models
3. **CC-C3** (snapshot oracle conflict) — two specs directly contradict on a security-critical field
4. **CC-C4** (RejectionReason count) — trivial to fix but creates implementor confusion
5. **CC-C5** (Leech resistance) — combat determinism depends on resolving this

These are fixable without architectural changes. The cross-cutting data inconsistencies (CC-T2 through CC-T4) suggest the CI diff gate between IDL and design docs needs to be stricter — inline TOML examples in design docs should be generated from or validated against the IDL, not hand-maintained.

The missing specs (NATS security, observability, anti-cheat thresholds, multi-shard ops, engine upgrade) are operational concerns that don't block the design but should be addressed before production deployment.
