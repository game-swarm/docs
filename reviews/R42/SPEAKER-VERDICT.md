# R42 Speaker Verdict

## §1 Verdict Summary

Overall verdict: Block.

Voting tally: 3 Block / 0 Pass.

All three GPT-5.5 review directions found freeze-blocking inconsistencies. The dominant pattern is authority drift: target design, specs, reference docs, and generated IDL surfaces restate the same rules with different storage models, sharding rules, command/API schemas, economy formulas, and combat semantics. The corpus is not yet suitable as an implementation contract.

## §2 Consensus Blockers

### B1. Target-state documentation violations remain across design/spec/reference layers

Description: Multiple reviewed files still contain review markers, status/changelog text, legacy negative notes, stage/future/deferred wording, or explicit removed-technology names. Architect and Design-Economy both flagged this directly, and Cross-Cutting flagged the same target-state violation through API/reference navigation and `PLAYTEST-GATED.md`.

Affected files: `design/architecture.md`, `design/engine.md`, `design/economy-balance-sheet.md`, `specs/core/persistence-contract.md`, `specs/core/snapshot-contract.md`, `specs/core/incremental-snapshot.md`, `specs/core/shard-protocol.md`, `specs/core/resource-ledger.md`, `specs/core/phase2b-system-manifest.md`, `specs/reference/api-registry.md`, `specs/gameplay/feedback-loop.md`, `specs/gameplay/PLAYTEST-GATED.md`.

Fix direction: Remove status/history/change/deferred language from design/spec/reference docs. Remove forbidden legacy technology names from normative text, examples, test names, variable names, and formulas. Move tracking material to `ROADMAP.md` or the active review report.

### B2. Canonical authority boundaries are inconsistent

Description: Each direction found documents that claim one canonical authority while embedding incompatible local rules elsewhere. Architect found storage/sharding/replay authority conflicts. Design-Economy found Resource Ledger bypasses and duplicated special-action rules. Cross-Cutting found Registry/IDL/security/reference schema drift.

Affected files: `design/architecture.md`, `design/modes.md`, `design/gameplay.md`, `design/interface.md`, `specs/core/tick-protocol.md`, `specs/core/persistence-contract.md`, `specs/core/snapshot-contract.md`, `specs/core/incremental-snapshot.md`, `specs/core/shard-protocol.md`, `specs/core/resource-ledger.md`, `specs/core/phase2b-system-manifest.md`, `specs/security/mcp-security.md`, `specs/security/visibility.md`, `specs/gameplay/api-idl.md`, `specs/gameplay/feedback-loop.md`, `specs/reference/api-registry.md`, `specs/reference/game_api.idl.yaml`, `specs/reference/mcp-tools.md`, `specs/reference/commands.md`, `specs/reference/host-functions.md`, `specs/reference/special-attack-table.md`.

Fix direction: For every repeated domain, declare exactly one normative source and convert other files to references or exact generated projections. Do not restate parameter tables, schemas, or behavioral contracts unless the restatement is mechanically kept identical.

### B3. API/IDL/reference surfaces do not describe one MCP/Game API contract

Description: Cross-Cutting found hard schema/count conflicts in Game API tools, `swarm_deploy`, CommandAction terminology, host functions, and snapshot truncation fields. Architect also found snapshot timing/schema drift, and Design-Economy found stale economy/gameplay references that undermine authority claims.

Affected files: `design/interface.md`, `design/engine.md`, `specs/security/mcp-security.md`, `specs/security/visibility.md`, `specs/gameplay/api-idl.md`, `specs/reference/api-registry.md`, `specs/reference/game_api.idl.yaml`, `specs/reference/mcp-tools.md`, `specs/reference/commands.md`, `specs/reference/host-functions.md`.

Fix direction: Make `api-registry.md` and generated IDL agree on counts, sections, input/output schemas, field names, and enum terminology. Security and gameplay docs should reference those schemas instead of carrying divergent examples.

### B4. Gameplay/economy rules bypass or contradict their declared authorities

Description: Design-Economy found PvE reward paths and balance-sheet assumptions outside Resource Ledger, plus Leech/Fabricate conflicts. Cross-Cutting independently found special-attack authority violations in `api-idl.md`. These are the same class of blocker: implementers cannot derive one economic or action-resolution rule set.

Affected files: `design/economy-balance-sheet.md`, `design/modes.md`, `design/gameplay.md`, `specs/core/resource-ledger.md`, `specs/core/phase2b-system-manifest.md`, `specs/gameplay/api-idl.md`, `specs/gameplay/feedback-loop.md`, `specs/reference/special-attack-table.md`, `specs/reference/api-registry.md`.

Fix direction: Route every resource emission through Resource Ledger operations and budgets. Pick one canonical Leech/Fabricate/Overload semantic table, then update gameplay/spec/reference descriptions to point at it or match it exactly.

### B5. Storage, sharding, snapshot, and replay contracts cannot be implemented as written

Description: Architect found mutually exclusive sharding/storage models, cross-shard hot-path semantics, fuel refund/crash retry rules, snapshot generation timing, TickCommitRecord schema, and command ordering. Cross-Cutting also found snapshot field-name drift. These issues affect replay identity and deterministic execution.

Affected files: `design/architecture.md`, `design/engine.md`, `specs/core/tick-protocol.md`, `specs/core/persistence-contract.md`, `specs/core/snapshot-contract.md`, `specs/core/incremental-snapshot.md`, `specs/core/shard-protocol.md`, `specs/security/command-source.md`, `specs/security/visibility.md`, `specs/reference/api-registry.md`, `specs/reference/game_api.idl.yaml`.

Fix direction: Choose one shard key, placement algorithm, process/file ownership model, cross-shard interaction rule, crash/refund model, snapshot timing, commit schema, and command ordering algorithm. Update all dependent docs from that single decision set.

## §3 Direction-Specific Findings

### Architect-only findings

- NATS deployment wording conflicts with the "no cluster" premise. Clarify whether "no cluster" means no Engine consensus cluster while NATS may still be clustered.
- `specs/core/wasm-sandbox.md` references a stale `specs/gameplay/api-idl` path.
- `specs/core/shard-protocol.md` contains a copied syntax artifact at the end of the document.
- Deploy activation semantics diverge between persistence and distributed sandbox: activation by compiled artifact conflicts with runtime cache-miss `ModuleNotFound` behavior.
- Incremental snapshot persistence alternates between blob store, redb replay-critical chain, and `$REDB_PATH.keyframes`.

### Design-Economy-only findings

- Arena victory conditions are broader in `design/modes.md` than in `specs/gameplay/feedback-loop.md`.
- Arena/Tournament T5 rewards need an explicit boundary: non-World metadata or ledger-contained rewards.
- Economy references include stale or missing anchors, including `PLAYTEST-GATED.md`, `Resource Ledger §StorageTax`, `Resource Ledger §6`, and repair authority references.

### Cross-Cutting-only findings

- Root `README.md` still advertises removed or relocated paths such as `specs/future/` and root-level `specs/gateway-protocol.md`.
- `specs/gameplay/PLAYTEST-GATED.md` is itself a tracking artifact inside `specs/`, which conflicts with the three-layer documentation model.

## §4 D-items

### D1. Sharding authority model

Background: Architecture defines static coordinate-range sharding with one Engine process and one redb file per shard. Shard protocol defines `room_id` Jump Hash assignment and same-process multi-shard redb ownership.

Option A: Static coordinate shards, one Engine process and one redb file per shard. Tradeoff: simple spatial routing, clear failure domains, and direct world-coordinate reasoning; less flexible rebalancing when shard load is uneven.

Option B: `room_id` Jump Hash shards with shared process/storage grouping. Tradeoff: easier redistribution and uniform key placement; weaker spatial locality and more complex replay/failure boundaries unless storage ownership is further specified.

Speaker recommendation: Option A, because it matches the architecture's world-coordinate model and keeps deterministic replay, backup/restore, and shard ownership easier to reason about.

### D2. Cross-shard gameplay semantics

Background: Architecture says cross-shard communication is only player migration and not hot path. Shard protocol adds cross-shard visibility/ranged attacks/combat with one-tick eventual consistency.

Option A: Cross-shard interactions are limited to migration. Tradeoff: cleaner hot path and deterministic local tick execution; gameplay at shard borders must be constrained by placement or migration rules.

Option B: Cross-shard visibility and combat are first-class with an explicit two-phase protocol. Tradeoff: richer border gameplay; adds latency, replay complexity, and consistency rules to combat.

Speaker recommendation: Option A unless border combat is a core product requirement. The current design benefits more from keeping combat local and deterministic.

### D3. Deploy activation authority

Background: Persistence allows deploy activation once compiled artifacts match, while distributed sandbox docs make runtime success depend on broadcast/cache propagation and allow first-tick `ModuleNotFound`.

Option A: redb compiled artifact is authoritative for activation; sandboxes fetch by content hash on demand, and cache miss is infrastructure latency, not a zero-command gameplay outcome. Tradeoff: deploy success has strong semantics; requires robust artifact fetch path.

Option B: sandbox propagation acknowledgements gate activation. Tradeoff: avoids first-use cache misses; deploy latency and availability depend on the sandbox fleet.

Speaker recommendation: Option A, with explicit prefetch as an optimization. Activation should not depend on transient cache broadcast state.

### D4. Snapshot/keyframe persistence authority

Background: Incremental snapshot docs place keyframes in blob storage, persistence says replay-critical data is redb plus keyframe/delta chain, and another section puts keyframes under `$REDB_PATH.keyframes`.

Option A: Replay-critical keyframes and deltas are redb-authoritative or colocated in a redb-owned file set. Blob/object storage is backup/export only. Tradeoff: stronger deterministic replay guarantees; larger local storage responsibility.

Option B: Blob/object storage is authoritative for keyframes. Tradeoff: simpler large-object storage; deterministic replay depends on external retention and availability guarantees.

Speaker recommendation: Option A. Replay-critical state should not depend on a non-authoritative blob retention path.

### D5. Special-action semantic authority

Background: Leech, Fabricate, and Overload are restated differently across gameplay, API IDL, manifest, and reference tables.

Option A: `specs/reference/special-attack-table.md` is the only parameter authority, and other docs reference it while describing only integration points. Tradeoff: less local readability; one table controls balance and avoids drift.

Option B: Gameplay/spec docs may restate action semantics when needed. Tradeoff: easier local reading; high drift risk unless generated checks enforce equality.

Speaker recommendation: Option A, with generated validation where possible.

### D6. Arena reward boundary

Background: Arena PvE Challenge is described as isolated from World resources, while Resource Ledger reserves T5 Arena/Tournament reward pools.

Option A: Arena/Tournament rewards are non-World metadata only. Tradeoff: strong economy isolation; less persistent economic incentive.

Option B: Arena/Tournament rewards may enter a ledger, but only through explicit Resource Ledger operations and separate budget boundaries. Tradeoff: supports material rewards; adds anti-faucet accounting complexity.

Speaker recommendation: Option A until the economy model explicitly needs cross-mode material rewards.

## §5 Note on Reviewer Availability

DSv4 and GLM reviewers unavailable due to API issues (403/rate-limit). This review is GPT-5.5 only across 3 directions. Next round should include multi-model coverage.

## §6 Review Statistics

| reviewer | direction | model | verdict | main findings |
|---|---|---|---|---|
| rev-gpt-architect | Architecture | GPT-5.5 | Blocker | Legacy technology names, sharding/storage contradictions, cross-shard semantics, fuel/crash replay conflicts, snapshot timing, deploy activation, TickCommitRecord and command ordering drift |
| rev-gpt-design-economy | Design/Economy | GPT-5.5 | Block | Resource Ledger/balance-sheet mismatch, PvE reward bypasses, Leech/Fabricate contradictions, Arena victory/reward boundary drift, stale economy references |
| rev-gpt-cross-cutting | Cross-Cutting | GPT-5.5 | Blocking | Game API tool count drift, `swarm_deploy` schema split, CommandAction terminology conflict, host-function omissions, snapshot truncation field drift, stale README navigation |
