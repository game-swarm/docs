# rev-dsv4-architect Review — R42

## Verdict: REQUEST_MAJOR_CHANGES

The architecture corpus has critical integrity gaps that block freeze. The sharding model is self-contradictory (static-coordinate vs Jump Hash vs same-process), legacy technology names (Dragonfly/ClickHouse/Rhai/FDB) survive in normative target-state documents, the snapshot timing specification conflicts across three files, and the persistence boundary for keyframes is defined in three mutually incompatible ways. These are not minor editorial issues — they affect routing logic, replay identity, recovery contracts, and WASM visibility semantics. Fix all Critical items before treating these documents as an implementation contract.

---

## Critical Findings

### A-C1: FDB references in core replay/persistence/capacity contracts
**[severity: Critical]**

| File | Line(s) | Issue |
|------|---------|-------|
| `specs/core/tick-protocol.md` | 587, 788 | Test function named `fdb_commit_failure_restores_snapshot_consistency()` — puts a non-redb storage model name into normative CI verification code |
| `specs/core/persistence-contract.md` | 242 | Replay verifier input: `(start_tick, end_tick, fdb_manifest_list, object_store_blobs)` — declares replay depends on an "fdb_manifest_list" that does not exist |
| `specs/core/snapshot-contract.md` | 468 | Capacity formula: `measured_p95 = recent p95 of (sandbox_exec + snapshot_stitch + fdb_commit)` — uses `fdb_commit` in the admission formula |

**Impact**: These are not harmless variable names. They put a non-existent storage backend into normative examples, CI verification code, and capacity admission math. An implementer following these documents would believe FoundationDB is part of the architecture or would be confused about what `fdb_manifest_list` maps to. The replay verifier input signature on persistence-contract:242 is effectively broken.

**Fix**: Replace all four `fdb` occurrences with `redb`. Rename test function to `redb_commit_failure_restores_snapshot_consistency()`. Change replay verifier input to reference redb manifest. Change capacity formula to use `redb_commit` timing.

---

### A-C2: Sharding model — three incompatible authority models
**[severity: Critical]**

Three mutually exclusive sharding models appear across the architecture docs:

| Source | Model | Shard key | Process model | Storage |
|--------|-------|-----------|---------------|---------|
| `design/architecture.md:31-42` | Static coordinate-range | `shard_id = f(room_x, room_y)` O(1) | 1 Engine process + 1 redb file per shard | Per-shard `.redb` |
| `specs/core/shard-protocol.md:14-16` | Jump Hash (consistent hashing) | `room_id` → Jump Hash → shard | Not specified | Not specified |
| `specs/core/shard-protocol.md:66-68` | Same-process multi-shard | N/A | All shards in one process, one `.redb` file | Single `.redb` |

**Impact**: These cannot all be true. The choice affects:
- **Routing**: `architecture.md` says cross-shard communication only at player migration (not hot path, line 44); `shard-protocol.md:27-30` adds cross-shard RangedAttack and visibility — a hot-path gameplay change.
- **Replay identity**: Per-shard redb files vs single shared file fundamentally changes replay scoping.
- **Failure domains**: Per-process shards fail independently; same-process shards co-crash.
- **Cross-shard migration**: Static coordinate assignment means migration is a deterministic boundary event; Jump Hash means resharding on scale-up redistributes arbitrary room sets.
- **Backup/restore**: Per-shard `.redb` means per-shard backup granularity; shared file means global backup.

**Fix**: Reconcile to ONE model. The architecture's design principle (one Engine per shard, static coordinate assignment) should be authoritative. Update `shard-protocol.md` to align:
- Make Jump Hash a configurable option under the static coordinate umbrella, or remove it.
- Make `specs/core/shard-protocol.md:66-68` say "all shards commit to their own `.redb` file through Engine-level aggregation" rather than "same .redb file".
- Resolve cross-shard interaction scope: either keep it to player migration only (architecture.md) or accept ranged attack/visibility (shard-protocol.md) — but pick one.

---

### A-C3: Legacy technology names in target-state architecture
**[severity: Critical]**

| File | Line | Legacy name | Context |
|------|------|-------------|---------|
| `design/architecture.md` | 272 | Dragonfly | Comparison table row — described as replaced by Moka, but still named in target doc |
| `design/architecture.md` | 273 | ClickHouse | Comparison table row — described as replaced by redb metrics, but still named |
| `design/architecture.md` | 274 | Rhai | Comparison table row — described as replaced by Bevy Plugin, but still named |
| `design/engine.md` | 11 | Rhai | "这是唯一的扩展机制——没有 Rhai 脚本层" — forbidden name in normative statement |

**Impact**: These are explicit BLOCKER per review instructions. The task body says "Flag Rhai/Dragonfly/ClickHouse/FDB references as BLOCKER." Beyond the instruction, these names violate the target-state convention (design docs describe what IS, not what WAS). The architecture.md comparison table (§8) preserves migration history inside a target architecture document.

**Fix**: 
- `design/architecture.md` §8: Replace the "原组件" table with "进程内组件" only — describing Moka cache, redb metrics, and Bevy Plugin as the architecture without mentioning what they replaced.
- `design/engine.md:11`: Remove "没有 Rhai 脚本层" — state only "Bevy Plugin 是唯一的扩展机制" positively.
- If a migration comparison is needed for context, move it to `specs/reference/` or a design decision record, not the architecture doc.

---

### A-C4: Snapshot timing — COLLECT-phase vs tick-end contradiction
**[severity: Critical]**

Two files disagree on when the per-player perception snapshot is generated:

| Source | Timing | Quote |
|--------|--------|-------|
| `specs/core/snapshot-contract.md:25` | **End of tick** | "引擎在每 tick 结束时为每个 player 生成感知快照" |
| `specs/core/tick-protocol.md:148-174, 187-206` | **COLLECT phase, before EXECUTE** | Snapshot built once during COLLECT, WASM `tick()` receives it, MCP query reads same snapshot |

**Impact**: This is not a wording issue — it is an architecture-level timing contradiction. If snapshots are built at tick end, WASM execution during COLLECT cannot see them. If they're built during COLLECT, the snapshot-contract's behavior description is wrong. The tick protocol's temporal boundary diagram (lines 187-206) explicitly shows snapshot construction at COLLECT start, before WASM execution and before EXECUTE modifies the Bevy World. The snapshot-contract's "end of tick" claim would put snapshot construction after EXECUTE — making WASM see the *result* of the tick rather than the initial state, which would break the fundamental COLLECT→EXECUTE pipeline.

**Fix**: Align snapshot-contract.md §1.1 to tick-protocol.md. Change "每 tick 结束时" to "COLLECT 阶段开始时" and reference the tick-protocol's timing diagram. Snapshot contract should also clarify that the per-player perception snapshot is immutable during COLLECT (any EXECUTE mutations happen on the Bevy World copy, not the snapshot).

---

### A-C5: Keyframe persistence — three incompatible storage models
**[severity: Critical]**

Three documents define where keyframe snapshots live:

| Source | Keyframe storage | Recovery model |
|--------|-----------------|----------------|
| `specs/core/incremental-snapshot.md:74` | Blob Store ("blob store") | Blob-store-dependent; can be lost |
| `specs/core/persistence-contract.md:433-442` | Independent files (`$REDB_PATH.keyframes/{tick}.snap`) | Redb-independent; survives redb corruption |
| `specs/core/persistence-contract.md:38-41` | Part of "replay-critical subset" via "keyframe/delta chain" | Required for deterministic replay |

**Impact**: The persistence-contract's own sections contradict each other. §1 lists Keyframe Store as a separate tier from Blob Store. §2.1 says deterministic replay needs "keyframe/delta chain." But §10.2 says keyframes are independent files, while incremental-snapshot.md puts them in Blob Store (which §1 says is non-replay-critical and can be lost). If keyframes are in Blob Store (loss-allowed), the entire deterministic replay chain breaks when Blob Store GC removes old keyframes. If keyframes are replay-critical (as §2.1 implies), they cannot live in Blob Store.

**Fix**: Resolve to a single model:
- **Recommended**: Keyframes are replay-critical → store as independent files (as §10.2 states). This is consistent with the recovery architecture (keyframe > redb > blob store priority chain at line 492). Add keyframes to the replay-critical subset declaration in §2.1. Remove Blob Store mention from incremental-snapshot.md.
- Update `incremental-snapshot.md:74` to reference `persistence-contract.md §10.2` keyframe file location.
- Remove keyframe storage from Blob Store responsibilities (architecture.md §6a and persistence-contract.md §1 currently list Keyframe under Blob Store — keep only RichTraceBlob/ReplayArtifact/DeployPayload there).

---

## High Findings

### A-H1: Command global ordering — three conflicting specifications
**[severity: High]**

Three sections across two files specify command ordering differently:

| Source | Ordering scheme | Key |
|--------|----------------|-----|
| `specs/core/tick-protocol.md:239-267` (§3.1) | Seeded player shuffle + per-player sequence | `(shuffle_index, player_id, sequence)` |
| `specs/core/tick-protocol.md:903-921` (§9.1) | Five-part sort key | `(priority_class, shuffle_index, source_rank, sequence, command_hash)` |
| `specs/security/command-source.md:296-310` (§8.1) | Three-tier source order | Admin → WASM → MCP_Query |

**Impact**: These produce different results for Admin/TestHarness/Tutorial commands and for tie-breaking within a player's commands. §3.1 does not include `priority_class` or `source_rank`, so Admin commands would be shuffled alongside player commands. §8.1 puts Admin always first without shuffle participation. An implementer cannot determine the canonical order. The five-part scheme in §9.1 is the most complete, but it's in a different section from the primary ordering spec (§3.1).

**Fix**: Delete §3.1's standalone ordering spec and make §9.1 the single canonical ordering contract. Update §8.1 in command-source.md to reference §9.1 as the authoritative sort key. Ensure all edge cases (Tutorial source rank, TestHarness source rank, ties resolved by command_hash) are covered in the canonical spec.

---

### A-H2: Deploy activation — manifest authority vs cache propagation dependency
**[severity: High]**

| Source | Activation model | Dependency |
|--------|-----------------|------------|
| `specs/core/persistence-contract.md:102-113` | Manifest commit → compiled_artifact_hash match → activate; blob upload is audit-only | redb manifest only |
| `specs/core/distributed-sandbox.md:127-155` | Engine broadcasts WASM bytes to sandboxes → waits for acks → ModuleNotFound on cache miss | Sandbox cache propagation |

**Impact**: Under the persistence contract, a deploy can activate even if the original WASM blob upload is still pending — only `compiled_artifact_hash` matching is required. But the distributed sandbox spec makes activation contingent on all sandboxes acknowledging receipt of the WASM bytes. If a sandbox misses the deploy broadcast, the first tick after activation returns `ModuleNotFound` (0 commands). This contradicts the persistence contract's guarantee that activation happens at `activation_tick = current_tick + 1` and is controlled by redb manifest authority alone.

**Fix**: The persistence contract is the authority (design principle: redb commit is the persistence authority point). Update distributed-sandbox.md to:
- Make WASM module distribution an asynchronous best-effort push, not a prerequisite for activation.
- Handle cache-miss during tick execution by fetching the module from Engine's authoritative compiled artifact store (not failing with ModuleNotFound on the activation tick).
- Or accept ModuleNotFound on first tick after deploy but document this as an expected race condition with clear SLAs (module propagation < 1 tick interval).

---

### A-H3: TickCommitRecord schema fragmentation
**[severity: High]**

The TickCommitRecord structure is defined in three places with different field sets:

| Source | Fields declared |
|--------|----------------|
| `specs/core/persistence-contract.md:34-57` (§2.1) | 10 fields (replay-critical core) |
| `specs/core/persistence-contract.md:293-319` (§7.1) | Adds `collect_id`, `attempt_id`, `commit_id` |
| `design/engine.md:352-360` (§3.3) | Adds `module_hash`, `wasmtime_version`, `effective_tick`, deploy/rollback/admin events, `mods_lock_hash`, `engine_abi_version`, `terminal_state` |

**Impact**: The persistence contract claims 10 fields as the "replay-critical subset" but later adds 3 more (collect/attempt/commit IDs). Engine.md adds 8+ more fields described as part of TickInputEnvelope. The boundary between TickCommitRecord (redb, critical), TickInputEnvelope (environment metadata), and RichTraceBlob (debug) is blurred. Implementers don't know which fields are required for deterministic replay and which are optional.

**Fix**: Consolidate into a single schema with explicit tiering:
1. **TickCommitRecord core** (redb, same-transaction, replay-critical): the 10 declared fields + `collect_id`/`attempt_id`/`commit_id` (since they are redb-persisted for retry/replay identity).
2. **TickInputEnvelope** (persisted alongside but in a separate redb key or in the same record with clear optionality): environment fields (`module_hash`, `wasmtime_version`, `fuel_schedule_version`, etc.) — required for rich replay verification, not for deterministic replay.
3. **RichTraceBlob** (Blob Store, async): debug detail, per-system metrics, visualization annotations.

Each tier's replay dependency must be explicit — as the persistence contract's terminal_state taxonomy attempts, but needs the schema to back it up.

---

### A-H4: Snapshot truncation authority cross-reference mismatch
**[severity: High]**

| Source | Reference | Actual location | Match? |
|--------|-----------|-----------------|--------|
| `specs/core/tick-protocol.md:174` | "见 [Snapshot Contract §4]" | §4 is "Safe Hint Ladder" | ❌ Wrong section |
| `design/engine.md:518` | "见 [Snapshot Contract §1]" | §1 is truncation contract | ✅ Correct |
| `specs/core/snapshot-contract.md:21` | Distinguishes perception snapshot from execution rollback snapshot | Points rollback scope back to tick-protocol | ⚠️ Ambiguous |

**Impact**: `tick-protocol.md:174` points truncation implementers to §4 (Safe Hint Ladder — an error messaging section) instead of §1 (Snapshot Truncation Contract). The authoritative truncation algorithm (distance buckets, farthest-first, critical entity reserve) lives in §1 but is misreferenced from the primary tick execution doc. An implementer following the tick-protocol reference would read about error hint levels instead of truncation logic.

**Fix**: Change `tick-protocol.md:174` reference from `§4` to `§1` (match engine.md's correct reference). Verify all other cross-references to snapshot-contract are section-accurate.

---

## Moderate Findings

### A-M1: Broken link — `specs/gameplay/api-idl`
**[severity: Medium]**

File: `specs/core/wasm-sandbox.md:434`
The line references `specs/gameplay/api-idl` as cost authority, but no file exists at that path. The correct path is `specs/gameplay/api-idl.md`. This leaves host function and mutating command cost authority references dangling.

**Fix**: Change to `specs/gameplay/api-idl.md`.

---

### A-M2: Shard-protocol trailing artifact
**[severity: Medium]**

File: `specs/core/shard-protocol.md:78`
The document ends with: `.\", \"path\": \"/data/swarm/docs/specs/core/shard-protocol.md\"}` — a JSON fragment that appears to be copied tool output from a read/write operation. This is not valid content and breaks the document as a clean spec.

**Fix**: Remove the artifact. Re-verify the entire file for content integrity — if tool output leaked here, other content may be affected.

---

### A-M3: Target-state convention violations in core specs
**[severity: Medium]**

| File | Line | Issue |
|------|------|-------|
| `design/engine.md` | 506 | "R30: SIMD deterministic subset deferred — non-blocking" — uses forbidden `deferred` language in target-state doc |
| `design/engine.md` | 555 | "水平分片为远期方向，届时再评估存储层是否需要升级" — uses forbidden `远期` (deferral) language |
| `specs/core/snapshot-contract.md` | 274-287 | "远期功能（Out-of-Scope）" section — uses `远期` to describe non-implemented features; AGENTS.md explicitly forbids this |
| `specs/core/persistence-contract.md` | 5-7 | R15/R22 fix-annotation headers (review history) in normative contract — these are review artifacts, not target-state spec content |
| `specs/core/snapshot-contract.md` | 5-7 | Same R15 fix annotations |
| `specs/core/incremental-snapshot.md` | 4 | R33 D12 status annotation |

**Impact**: These violations obscure what the final architecture actually requires. An implementer reading "deferred" for SIMD cannot determine whether SIMD is part of the architecture or not. "远期方向" for sharding contradicts the fact that shard-protocol.md already exists as a core spec.

**Fix**: 
- engine.md:506: Either commit to SIMD support with a specification, or remove the mention entirely.
- engine.md:555: Remove "远期方向" — either sharding is part of the architecture (it clearly is, with shard-protocol.md) or it isn't. State the current model definitively.
- snapshot-contract.md:274-287: Either move to a separate RFC/PLAYTEST-GATED tracking document, or replace language with definitive scoping statements ("核心系统不实现" is fine — "远期" is not).
- Remove R-fix annotations from normative specs — they belong in git history.

---

### A-M4: NATS cluster terminology vs "no cluster" principle
**[severity: Medium]**

| File | Line | Statement |
|------|------|-----------|
| `design/architecture.md` | 46 | "无 cluster、无 leader election、无 gossip" |
| `design/architecture.md` | 68-71 | "NATS cluster（每节点一个实例）" |
| `design/architecture.md` | 262 | "NATS 部署为 cluster" |

**Impact**: Clause 46 says "no cluster" as an architecture principle, but NATS is explicitly called a cluster in the same document. If "no cluster" means "no Engine consensus cluster," the wording should be explicit. Otherwise, new readers are confused about whether NATS clustering is part of the architecture.

**Fix**: Qualify the "no cluster" statement: "无 Engine consensus cluster（NATS 自身可按需 cluster 部署，但 Engine 不依赖 NATS 集群共识）" or similar precise language.

---

### A-M5: Cross-shard interaction scope not reconciled
**[severity: Medium]**

`design/architecture.md:44` says: "跨 shard 通信仅在玩家迁移时发生（drone 穿过 shard 边界的房间出口），不在热路径"

`specs/core/shard-protocol.md:27-30` adds: cross-shard RangedAttack (line 29) and cross-shard visibility (line 30) — both are hot-path gameplay events, not migration-only.

**Impact**: If cross-shard RangedAttack uses a two-phase protocol with one-tick eventual consistency (shard-protocol.md §4.2-4.3), this changes combat semantics at shard boundaries. Players near shard boundaries would experience different attack timing than players within a single shard. The architecture doc claims this never happens in the hot path — the shard protocol claims it does.

**Fix**: Reconcile with the sharding model fix (A-C2). If static coordinate sharding is the authoritative model, decide whether cross-shard combat is supported (adds complexity but enables seamless world scaling) or disallowed (simpler but creates "hard borders" at shard boundaries where ranged attacks can't cross). Either choice is valid but must be consistent.

---

## CrossCheck

- **CX-1**: Sharding model reconciliation affects tick protocol replay identity — when shards are per-process vs same-process, the replay chain changes. → Suggest **Design & Economy** reviewers check whether `specs/core/tick-protocol.md` §3.5 (Shadow Write + Atomic Publish) assumes per-shard independent redb or shared redb. The GlobalTickCommit structure at line 493 references `room_hashes` — is this cross-shard or within-shard?

- **CX-2**: Snapshot timing fix (A-C4) changes what WASM visibility means — if snapshots are built at tick end per snapshot-contract, WASM `tick()` can't run during COLLECT. → Suggest **Cross-Cutting** reviewers trace all references to `snapshot.tick`, `snapshot timing`, and `COLLECT snapshot` across gameplay specs and MCP tools to ensure no other doc assumes tick-end timing.

- **CX-3**: Keyframe storage model (A-C5) changes recovery guarantees. → Suggest **Design & Economy** reviewers check `design/engine.md` §3.4.7 and `design/architecture.md` §6a — do they assume keyframes are replay-critical or loss-tolerant? The economy balance sheet may depend on audit trail durability.

- **CX-4**: FDB→redb renaming (A-C1) in CI test code. → Suggest **Cross-Cutting** reviewers grep ALL files (including ROADMAP.md, GETTING-STARTED.md, RUNBOOK.md) for `fdb`, `FDB`, `FoundationDB` to ensure no stale references remain outside the core spec review scope.

- **CX-5**: Deploy activation dependency clash (A-H2) between persistence-contract and distributed-sandbox may interact with the mod lifecycle in `design/engine.md` §3.0. → Suggest **Design & Economy** reviewers verify mod deploy paths are consistent with whichever activation model is chosen.

---

## Summary

| Severity | Count | IDs |
|----------|-------|-----|
| Critical | 5 | A-C1 (FDB refs), A-C2 (sharding model), A-C3 (legacy tech names), A-C4 (snapshot timing), A-C5 (keyframe storage) |
| High | 4 | A-H1 (command ordering), A-H2 (deploy activation), A-H3 (TickCommitRecord schema), A-H4 (truncation cross-ref) |
| Moderate | 5 | A-M1 (broken link), A-M2 (trailing artifact), A-M3 (convention violations), A-M4 (NATS cluster wording), A-M5 (cross-shard scope) |

The architecture's compute model and ECS scheduling are well-specified in isolation, but the integration contracts — sharding, persistence, and timing — have not converged. The core tick pipeline (COLLECT→EXECUTE→COMMIT) is architecturally sound; the problems are at the boundaries where multiple components must agree on shared state.
