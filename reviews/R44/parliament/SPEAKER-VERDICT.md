# R44 Speaker 裁决

Speaker: rev-speaker / GPT-5.5
Input: 9/9 reviewer reports read from `/data/swarm/docs/reviews/R44/parliament/`

Reports included:
- `gpt-architect.md` — REQUEST_MAJOR_CHANGES
- `dsv4-architect.md` — CONDITIONAL_APPROVE
- `glm-architect.md` — CONDITIONAL_APPROVE
- `gpt-design-economy.md` — REQUEST_MAJOR_CHANGES
- `dsv4-design-economy.md` — REQUEST_MAJOR_CHANGES
- `glm-design-economy.md` — no final verdict line, but contains Critical/High blockers; treated as REQUEST_MAJOR_CHANGES for severity aggregation
- `gpt-cross-cutting.md` — REQUEST_MAJOR_CHANGES
- `dsv4-cross-cutting.md` — no explicit verdict line, but §5 labels three Critical D-items; treated as REQUEST_MAJOR_CHANGES for severity aggregation
- `glm-cross-cutting.md` — CONDITIONAL_APPROVE

Vote tally:
- APPROVE: 0
- CONDITIONAL_APPROVE: 3
- REQUEST_MAJOR_CHANGES: 6 (4 explicit + 2 inferred from Critical blocker reports)
- REJECT: 0

Overall Verdict: REQUEST_MAJOR_CHANGES

Rationale: The design direction remains strong, but R44 contains multiple cross-document conflicts in replay-critical/API-critical/security-critical domains. Several findings recur across at least two reviewer directions and at least two model families, especially IDL/API enum drift, vanilla economy/special attack/build-cost drift, sharding/NATS security, and snapshot/visibility contracts. These must be resolved before the documents can be considered a clean target-state design.

---

## SS1 Consensus Findings (3-model agreement)

### SS1-1. RejectionReason canonical enum/count drift

Sources:
- `gpt-architect.md` C1: 35 / 46 / 48 split across `api-registry.md`, `interface.md`, `commands.md`, `game_api.idl.yaml`; duplicate `RateLimited` layer ambiguity.
- `glm-architect.md` C3: 46 vs 48 and auth-specific codes diverge between API Registry, IDL, interface, command-validation.
- `glm-cross-cutting.md` CC-C4: 46 vs 48 across API Registry, `api-idl.md`, `interface.md`, `command-validation.md`.

Impact:
- SDK/codegen error enums can diverge.
- JSON-RPC/MCP clients cannot rely on a stable wire enum.
- Replay/TickTrace `rejection_reason_registry_version` loses meaning if the enum set is not canonical.

Speaker classification: Consensus Blocker B1.

Required resolution:
- Pick one machine-readable source for the canonical enum.
- Regenerate or update all human documents from that source.
- Remove hardcoded stale counts.
- Decide whether auth-specific reasons are part of the same wire enum or a separate auth error namespace.

### SS1-2. Special attack parameter drift (Leech / Debilitate / Fabricate / cooldowns / resistance)

Sources:
- `gpt-design-economy.md` SS1-3: special attack resistance/cooldown/cost/range conflicts across `special-attack-table.md`, `gameplay.md`, `world-rules.md`.
- `glm-design-economy.md` SS1-1, SS1-2, SS1-4, SS2-5: Fabricate Matter cost conflicts with Vanilla Energy-only; Leech cooldown 150 vs 100; Debilitate resistance conflict; Heal range conflict.
- `glm-cross-cutting.md` CC-C5, CC-T4: Leech resistance/cooldown conflicts across gameplay/world-rules/command-validation.
- `glm-architect.md` T2/T3 and CX-3 also flags Fabricate and Leech drift.

Impact:
- Combat counterplay becomes unknowable to players.
- SDK constants and engine validation may disagree.
- Arena fairness and replay determinism are compromised if action effects differ by source document.

Speaker classification: Consensus Blocker B2.

Required resolution:
- Make `specs/reference/special-attack-table.md` or IDL-derived table the sole parameter authority.
- Delete or mark all other special-attack numeric tables as illustrative.
- Resolve Fabricate resource cost together with the Vanilla resource model D-item.

### SS1-3. Body part and structure cost/progression drift

Sources:
- `gpt-design-economy.md` SS1-4: structure roster/cost/RCL unlock conflicts; PowerSpawn/Nuker/Depot costs and Road/Wall/Rampart/Container roster differ.
- `glm-design-economy.md` SS1-3, SS2-2, SS2-3, SS2-4: RangedAttack 150 vs 100; PowerSpawn 5000 vs 1200; Nuker 100000 vs 5000; Depot 5000 vs 600.
- `glm-architect.md` C1/C2/T4: RangedAttack and PowerSpawn/Depot cost divergence.
- `glm-cross-cutting.md` CC-T2/CC-T3: PowerSpawn/Nuker and RangedAttack conflicts.

Impact:
- Spawn/build economy is not implementable from docs without guessing.
- RCL progression and economy-balance-sheet cannot be trusted.
- Late-game sinks and early logistics differ by up to 20x depending on document.

Speaker classification: Consensus Blocker B3.

Required resolution:
- Define one canonical body-part and structure-cost table, preferably generated from IDL/API Registry.
- Sync gameplay/world-rules/economy-balance-sheet/RCL docs to reference it.
- Decide whether Road/Wall/Rampart/Container are Vanilla defaults and update tutorials/balance sheet accordingly.

### SS1-4. Authority-chain / duplicate hardcoded tables are causing systemic drift

Sources:
- `gpt-architect.md` C1-C3 and S1: IDL, Registry, MCP tools, host functions, and resource tables all duplicate counts/values.
- `dsv4-architect.md` S2: recommends central Domain Authority Map.
- `glm-architect.md` S1/S4: duplicated body/structure/special-effect definitions and need for authority hierarchy.
- `gpt-cross-cutting.md` S1: auth/rate/visibility/replay/audit fields should be machine-readable.
- `glm-cross-cutting.md` CC-S9: inline TOML examples drift from IDL and need validation/generation.

Impact:
- The individual conflicts are symptoms of a structural documentation problem.
- Future rounds will keep rediscovering drift unless duplicated tables are generated or removed.

Speaker classification: Design Debt DDC-1 and structural issue SS5-1; it also informs B1-B4 remediation.

---

## SS2 Contested Findings (split across models)

### SS2-1. Sharding model: static multi-Engine shard vs single-process room partition vs Jump Hash

Sources:
- `gpt-cross-cutting.md` C1: architecture says per-shard Engine+redb; shard-protocol says all shards in same process / same redb transaction.
- `glm-cross-cutting.md` CC-C2: architecture says static coordinate sharding/no coordinator; shard-protocol says Jump Hash/consistent hash ring.
- `glm-cross-cutting.md` CC-T7 and CC-S8: cross-shard combat and multi-shard operations underspecified.

Split:
- Reviewers agree there is a conflict, but differ on the desired resolution.
- `gpt-cross-cutting.md` recommends preserving true multi-Engine shards.
- `glm-cross-cutting.md` recommends aligning shard-protocol to static config-based sharding and removing Jump Hash.

Speaker classification: Consensus Blocker B4 + D5 user decision.

### SS2-2. NATS / distributed sandbox security boundary

Sources:
- `gpt-cross-cutting.md` C2: request/reply envelopes lack auth, MAC/signature, request_id, nonce, reply correlation, replay rejection.
- `glm-cross-cutting.md` CC-C1: NATS TLS/auth/ACL unspecified for tick delta, sandbox dispatch, module broadcasts.
- `dsv4-cross-cutting.md` T3: CVE-SLA should include async-nats and related dependencies.

Split:
- No reviewer argues the current state is acceptable.
- The split is implementation depth: NATS-native credentials/ACL only vs NATS ACL plus message-level signed envelopes and replay correlation.

Speaker classification: Consensus Blocker B5 + D6 user decision if scope needs ruling.

### SS2-3. Vanilla resource model: Energy-only vs multi-resource Vanilla

Sources:
- `gpt-design-economy.md` SS1-1: Vanilla/Standard claim Energy-only while world-rules and Fabricate introduce Matter.
- `glm-design-economy.md` SS1-1: Fabricate requires Matter in a Vanilla world that only defines Energy.
- `glm-architect.md` T2 and `gpt-design-economy.md` SS1-3 also identify Fabricate cost drift.

Split:
- `gpt-design-economy.md` recommends Energy-only Vanilla and moving Matter to advanced/modded worlds.
- `glm-design-economy.md` allows either pure Energy Vanilla Fabricate or world-configurable Fabricate cost.

Speaker classification: Consensus Blocker B6 + D1 user decision.

### SS2-4. New-player economy curve and free_upkeep exit

Sources:
- `gpt-design-economy.md` SS1-2: 10-minute Golden Path / first-hour / 100-minute protection / 7.5-minute deficit cliff conflict.
- `dsv4-design-economy.md` CF-2 and CF-3: basic-code players are negative after free_upkeep; tick 2000 cliff from +22 to -33.
- `glm-design-economy.md` SS1-6, SS3-1, SS3-7: balance sheet math/source assumptions and controller passive income gaps.

Split:
- All agree current curve is risky/inconsistent.
- Options differ: retune base upkeep/soft cap, add ramp-down subsidy, document hard-core intent honestly, or add income sources.

Speaker classification: Consensus Blocker B7 + D3 user decision.

### SS2-5. World PvP incentive loop

Sources:
- `dsv4-design-economy.md` CF-1: World PvP has zero positive incentive; optimal strategy is to avoid fighting.
- `gpt-design-economy.md` SS2-2 and highlights: Allied Transfer/intercept and logistics could create conflict but currently not fully canonicalized.
- `gpt-design-economy.md` SS1-2/SS1-4 and `dsv4-design-economy.md` CF-4: expansion/upkeep/PvP costs create weak mid/late motivation.

Split:
- DeepSeek raises it as Critical; other design-economy reviewers support adjacent incentive problems but do not all call it a direct blocker.
- This is a gameplay design decision, not merely a documentation sync.

Speaker classification: Direction High / D-item, not automatic consensus blocker under strict 3-model rule. Included as D2 because it requires user authority.

### SS2-6. Snapshot truncation schema: exact counts, buckets, omitted_count, omitted_categories

Sources:
- `gpt-architect.md` T5: `omitted_categories` vs `omitted_count` schema conflict.
- `dsv4-cross-cutting.md` C2: snapshot-contract and incremental-snapshot define different deterministic truncation sort keys.
- `glm-cross-cutting.md` CC-C3: exact omitted counts conflict with visibility oracle defense requiring buckets.

Split:
- Findings address related but distinct parts of snapshot output/truncation: schema field, sorting key, and oracle-safe count representation.
- They should be remediated as one snapshot-contract cleanup package.

Speaker classification: Consensus Blocker B8 + D7 if exact-vs-bucket representation needs explicit product/security ruling.

---

## SS3 Novel Issues (single-model unique catch)

Novel issues are not promoted to consensus blockers unless they are replay/security critical and independently supported by adjacent findings.

| ID | Finding | Source | Severity | Speaker disposition |
|---|---|---|---|---|
| N1 | Host Function ABI count/signature/fuel schedule conflict: 6 vs 7 functions; `host_get_random` u32 vs u64; fuel 100+1/byte vs 200+10/32 bytes | `gpt-architect.md` C3 | Critical | Direction High A-H1. Treat as high-priority API/ABI blocker even though single report, because ABI drift is replay-critical. |
| N2 | Plugin systems vs fixed 31-system Tick Manifest abstraction conflict | `gpt-architect.md` C4 | Critical | Direction High A-H2 + D8. Needs user/architecture ruling. |
| N3 | Gateway implementation language Rust vs Go | `dsv4-cross-cutting.md` C1 | Critical | Direction High C-H1 + D9. Single-model but direct contradiction. |
| N4 | Controller age repair lacks TickTrace attribution path | `dsv4-cross-cutting.md` C3 | Critical | Direction High C-H2. Likely direct fix: add AgeRepair trace event or zero-fee ledger op. |
| N5 | Replay/audit retention horizon conflict: Blob 180d, Keyframe 30d, redb full rebuild unclear | `gpt-cross-cutting.md` C3 | Critical | Direction High C-H3 + D10. Ops/security policy decision needed. |
| N6 | Gateway `/metrics` and public/loopback topology unclear | `gpt-cross-cutting.md` T1 | High | Direction High C-H4. Fix with public edge / gateway internal / admin metrics split. |
| N7 | Rate-limit authority and machine-readable tool limits dispersed | `gpt-cross-cutting.md` T2 | High | Direction High C-H5. Fold into IDL/Registry authority work. |
| N8 | World seed/keyframe backup secrecy not specified | `gpt-cross-cutting.md` T3 | High | Direction High C-H6. Fix runbook/keyframe encryption/redaction policy. |
| N9 | CVE-SLA omits bevy_ecs, redb, async-nats, serde_swarm | `dsv4-cross-cutting.md` T3 | High | Direction High C-H7. Direct documentation fix. |
| N10 | RCL progress conversion rate missing | `dsv4-design-economy.md` DT-5 | High | Direction High E-H1. Direct spec addition or D-item if rate not obvious. |
| N11 | Economy balance sheet 50-room storage_capacity less than 20-room capacity | `glm-design-economy.md` SS1-5 | High | Direction High E-H2. Correct table or justify assumption. |
| N12 | Economy balance sheet §2.2 arithmetic error: 30×4+12 = 132, not 138 | `glm-design-economy.md` SS1-6 | High | Direction High E-H3. Direct correction. |
| N13 | Snapshot abuse response lowers victim COMBAT priority | `gpt-cross-cutting.md` T5 | Medium | Medium but safety-relevant; fix by removing semantic punishment and attributing pressure to source. |
| N14 | `Claim Depot` / structure occupation path undefined | `glm-design-economy.md` SS3-6 | Medium | Direction Medium; needs API clarification if Depot capture remains target design. |
| N15 | CRL fallback during Auth Service outage undefined | `glm-cross-cutting.md` CC-T5 | Medium | Direction Medium; direct security policy fix. |

---

## SS4 Design Debt Catalog (recurring patterns)

### DDC-1. Human-maintained canonical-looking tables are drifting

Recurring in:
- RejectionReason counts.
- MCP tool counts.
- Host function count/fuel schedule.
- Body part costs.
- Structure costs.
- Special attack parameters.
- world.toml examples and Resource Ledger values.

Disposition:
- Make machine-readable IDL/Registry/Ledger/special-attack table authoritative.
- Generate human tables where possible.
- If a table is illustrative, label it as illustrative and remove hardcoded counts/values.

### DDC-2. “Target-state design” is polluted by history/RFC/queued language

Sources:
- `dsv4-architect.md` S3.
- `gpt-cross-cutting.md` S4.
- `glm-architect.md` S5.

Disposition:
- Remove “queued”, “RFC方向”, “later”, “unimplemented placeholder” language from core target-state docs.
- If feature-gated but specified, call it `feature-gated specified schema` rather than roadmap language.
- If not part of core target state, move to extension/mod registry.

### DDC-3. Security and ops contracts lag behind architecture diagrams

Recurring in:
- NATS security.
- Gateway public/internal/admin boundary.
- Metrics exposure.
- Keyframe seed secrecy.
- Replay retention/RTO/RPO.
- CRL fallback.
- Engine/shard upgrade/migration runbooks.

Disposition:
- Add operational security specs before production freeze.
- Keep public gameplay design separate from deployment trust-boundary contracts.

### DDC-4. Economy math is rigorous but not yet player-facing or fully auditable

Recurring in:
- Storage tax bp/tick lacks human-readable examples.
- Source density assumptions missing.
- Controller passive income not in ledger faucet list.
- RCL conversion rate missing.
- Economy balance arithmetic/table errors.
- PvP and late-game incentives not fully closed.

Disposition:
- Fix math tables first.
- Add player-facing economy intuition.
- Decide the intended difficulty/retention posture for Standard World.

---

## SS5 Structural Issues (document organization problems)

### SS5-1. Missing Domain Authority Map

Sources:
- `gpt-architect.md` S1.
- `dsv4-architect.md` S2.
- `glm-architect.md` S4.
- `glm-cross-cutting.md` CC-S9.

Required change:
Add a central map, likely in `docs/README.md` or `specs/reference/codegen.md`, with at least:

| Domain | Authority |
|---|---|
| API tools / RejectionReason / CommandAction / Host Functions | IDL YAML + generated API Registry |
| Economy parameters / formulas | Resource Ledger + generated economy schema |
| Body/structure costs | IDL/API Registry generated table |
| Special attacks | `special-attack-table.md` or generated ActionRegistry table |
| Tick schedule / ECS R/W | `phase2b-system-manifest.md` plus plugin policy decision |
| Snapshot truncation/filtering | `snapshot-contract.md` + visibility oracle constraints |
| Persistence/replay retention | `persistence-contract.md` + RUNBOOK retention matrix |
| Security transport/authz/rate limits | security specs + machine-readable Registry fields |

### SS5-2. `design/gameplay.md` is overlarge and mixes canonical rules, examples, economy, mod surface, and UX

Source:
- `glm-architect.md` S7.

Disposition:
- Not a blocker, but current size increases drift risk.
- Split only after blockers are fixed, or first convert hardcoded canonical tables to generated/reference links.

### SS5-3. Stale path/anchor references and corrupted glyphs

Sources:
- `dsv4-architect.md` C1-C5.

Findings:
- Truncated `⏏` glyphs across multiple docs.
- `specs/core/10-11/` and `specs/RFC/` references stale/nonexistent.
- `fdb_*` legacy references despite redb target state.
- Implicit anchors may not resolve.

Disposition:
- Direct cleanup batch. Not a design blocker by itself, but should be fixed before publication.

### SS5-4. Local vs distributed sandbox docs present different transport/resource defaults

Sources:
- `glm-architect.md` T7.
- `gpt-cross-cutting.md` T4.
- `glm-cross-cutting.md` CC-T1.

Disposition:
- Make `distributed-sandbox.md` explicitly a superset/profile of `wasm-sandbox.md`.
- Add a table for local/distributed memory, CPU, transport, and deadline differences.

---

## SS6 Architecture Assessment (overall coherence grade)

Grade: B- current document state; A- potential after blocker cleanup.

Strengths with broad reviewer agreement:
- Two-layer computation model (WASM COLLECT / Engine EXECUTE) is sound.
- Deferred command model avoids mutating host functions and preserves authority boundary.
- redb shadow-write + GlobalTickCommit pattern is strong for atomic tick commit.
- 31-system ECS manifest and R/W matrix are unusually rigorous.
- Snapshot truncation design has a strong deterministic core, though schema/security details need reconciliation.
- Resource Ledger as a single economic audit point is the correct direction.
- Application-layer certificate/auth model is conceptually strong.

Weaknesses blocking a clean architecture grade:
- The project repeatedly states “single source of truth” but still hand-maintains conflicting values.
- Security/ops specs for distributed runtime are not yet at the same maturity level as deterministic engine specs.
- Shard architecture target state is not unique.
- Economy/progression player incentives are mathematically detailed but not yet fully coherent as game loops.

Architecture judgment:
- Core engine architecture: sound.
- Interface/codegen authority: not yet clean.
- Distributed/ops/security envelope: incomplete.
- Gameplay economy: requires major design decisions, not just copy-editing.

---

## SS7 Verdict

REQUEST_MAJOR_CHANGES

This is not a rejection: the core architecture and gameplay direction are viable. But R44 cannot be approved while canonical rules, API enums, sandbox trust boundaries, sharding model, and economy incentives contradict across target-state documents.

Minimum exit criteria for next round:
1. Resolve all SS8 blockers B1-B10.
2. Record user rulings for all SS9 D-items before editing docs that depend on them.
3. Add an authority map and remove/mark duplicate hardcoded tables.
4. Re-run a consistency pass focused on IDL/API Registry/special attacks/build costs/economy tables.
5. Verify that all corrections express final target state, not Phase/MVP/history language.

---

## SS8 Blocker List

### B1. RejectionReason canonical enum/count drift

Consensus basis:
- At least 2 directions: Architecture + Cross-cutting.
- At least 2 models: GPT + GLM.
- 3-model agreement present.

Sources:
- `gpt-architect.md` C1.
- `glm-architect.md` C3.
- `glm-cross-cutting.md` CC-C4.

Document references cited by reviewers:
- `specs/reference/api-registry.md`
- `design/interface.md`
- `specs/reference/commands.md`
- `specs/reference/game_api.idl.yaml`
- `specs/core/command-validation.md`
- `specs/gameplay/api-idl.md`

Required fix:
- Canonicalize enum set/count and auth/MCP layering.
- Remove duplicate stale counts.
- Add CI guard for generated Registry/IDL/docs agreement.

### B2. Special attack canonical parameter drift

Consensus basis:
- At least 2 directions: Design-Economy + Cross-cutting + Architecture cross-checks.
- At least 2 models: GPT + GLM.
- 3-model agreement present.

Sources:
- `gpt-design-economy.md` SS1-3.
- `glm-design-economy.md` SS1-1/SS1-2/SS1-4/SS2-5.
- `glm-cross-cutting.md` CC-C5/CC-T4.
- `glm-architect.md` T2/T3/CX-3.

Document references:
- `specs/reference/special-attack-table.md`
- `design/gameplay.md`
- `specs/core/world-rules.md`
- `specs/core/command-validation.md`

Required fix:
- One canonical special attack table.
- Delete duplicate numeric special-effect tables or generate them.
- Resolve Leech cooldown/resistance, Debilitate resistance, Heal range, Fabricate cost.

### B3. Body part and structure cost/progression drift

Consensus basis:
- At least 2 directions: Design-Economy + Architecture + Cross-cutting.
- At least 2 models: GPT + GLM.
- 3-model agreement present.

Sources:
- `gpt-design-economy.md` SS1-4.
- `glm-design-economy.md` SS1-3/SS2-2/SS2-3/SS2-4.
- `glm-architect.md` C1/C2/T4.
- `glm-cross-cutting.md` CC-T2/CC-T3.

Document references:
- `design/gameplay.md`
- `specs/core/world-rules.md`
- `specs/reference/api-registry.md`
- `specs/gameplay/api-idl.md`
- `design/economy-balance-sheet.md`

Required fix:
- Canonical generated cost table.
- Sync PowerSpawn/Nuker/Depot/RangedAttack and roster/RCL unlocks.
- Update economy-balance-sheet assumptions after canonical costs are chosen.

### B4. Sharding architecture target state contradiction

Consensus basis:
- At least 1 direction strongly, but 2 models within Cross-cutting independently found it.
- Security/ops impact is high enough to block architecture freeze.

Sources:
- `gpt-cross-cutting.md` C1.
- `glm-cross-cutting.md` CC-C2/CC-T7/CC-S8.

Document references:
- `design/architecture.md`
- `specs/core/shard-protocol.md`
- `specs/core/persistence-contract.md`
- `specs/core/tick-protocol.md`

Required fix:
- User/architectural decision D5.
- Then rewrite shard-protocol to a single model: true multi-Engine shards or single-Engine room partitions.
- Define cross-shard replay, commit, failure domain, and operations consistently.

### B5. NATS / Distributed Sandbox trust boundary is incomplete

Consensus basis:
- At least 1 direction strongly, 2 models independently found it.
- Security-critical: production deployment unsafe without it.

Sources:
- `gpt-cross-cutting.md` C2.
- `glm-cross-cutting.md` CC-C1/CC-S1.
- `dsv4-cross-cutting.md` T3 adjacent dependency coverage.

Document references:
- `design/architecture.md`
- `specs/core/distributed-sandbox.md`
- `specs/security/gateway-protocol.md`
- `RUNBOOK.md`

Required fix:
- Define NATS TLS/auth/ACL per role.
- Define signed/MACed request/reply envelopes with request_id/collect_id/deadline/nonce/replay protection.
- Define module broadcast integrity and sandbox identity lifecycle.

### B6. Vanilla resource model conflicts with Fabricate/Matter and multi-resource examples

Consensus basis:
- At least 2 models in Design-Economy, with architecture corroboration.
- Gameplay/economy critical.

Sources:
- `gpt-design-economy.md` SS1-1.
- `glm-design-economy.md` SS1-1.
- `glm-architect.md` T2.

Document references:
- `design/gameplay.md`
- `specs/core/resource-ledger.md`
- `design/economy-balance-sheet.md`
- `specs/core/world-rules.md`
- `specs/reference/special-attack-table.md`

Required fix:
- User decision D1.
- Either Energy-only Vanilla with Matter moved to mod/advanced worlds, or multi-resource Vanilla with full faucet/sink/tutorial/balance-sheet support.

### B7. New-player economy/free_upkeep/protection curve creates cliff and inconsistent time promises

Consensus basis:
- 2 Design-Economy models independently flag; third finds math/source assumptions adjacent.
- Player-retention critical.

Sources:
- `gpt-design-economy.md` SS1-2.
- `dsv4-design-economy.md` CF-2/CF-3.
- `glm-design-economy.md` SS1-6/SS3-1/SS3-7.

Document references:
- `design/gameplay.md`
- `specs/gameplay/feedback-loop.md`
- `design/economy-balance-sheet.md`
- `specs/core/resource-ledger.md`
- `specs/core/world-rules.md`

Required fix:
- User decision D3.
- Align real-time vs tick promises.
- Decouple or ramp free_upkeep/PvP/upkeep expiry.
- Correct balance-sheet math and source/passive-income assumptions.

### B8. Snapshot truncation/schema/security contract conflicts

Consensus basis:
- At least 2 directions: Architecture + Cross-cutting.
- At least 3 model reports identify related snapshot conflicts.

Sources:
- `gpt-architect.md` T5.
- `dsv4-cross-cutting.md` C2.
- `glm-cross-cutting.md` CC-C3.

Document references:
- `specs/core/snapshot-contract.md`
- `specs/core/incremental-snapshot.md`
- `specs/core/tick-protocol.md`
- `specs/reference/game_api.idl.yaml`
- `design/engine.md`
- `specs/security/visibility.md`

Required fix:
- One truncation ordering authority.
- One output schema (`omitted_categories` vs `omitted_count`), with oracle-safe buckets if security ruling chooses that.
- Sync IDL/MCP/WASM snapshot schema.

### B9. Host Function ABI count/signature/fuel conflict

Consensus basis:
- Single-model direct critical (`gpt-architect.md`), but replay/ABI severity warrants blocker treatment.

Sources:
- `gpt-architect.md` C3.
- Related cross-checks: `dsv4-architect.md` CX-4, `gpt-architect.md` CX-2.

Document references:
- `specs/reference/game_api.idl.yaml`
- `specs/reference/api-registry.md`
- `specs/reference/host-functions.md`
- `specs/core/wasm-sandbox.md`

Required fix:
- Decide 6 vs 7 host functions.
- Unify `host_get_random` signature and seed derivation.
- Unify fuel schedule and make it replay-versioned.

### B10. Replay/audit retention and keyframe/seed secrecy contracts incomplete

Consensus basis:
- Cross-cutting security/ops blockers from GPT; related keyframe/DR concerns from GLM.

Sources:
- `gpt-cross-cutting.md` C3/T3.
- `glm-cross-cutting.md` CC-S4/CC-S5.
- `dsv4-cross-cutting.md` S3 adjacent Blob Store degraded replay.

Document references:
- `specs/core/persistence-contract.md`
- `specs/core/tick-protocol.md`
- `specs/security/visibility.md`
- `RUNBOOK.md`

Required fix:
- User decision D10 on replay horizon.
- Define redb historical-state assumptions.
- Define keyframe/delta/blob retention, backup matrix, seed-bearing secret handling, and public replay redaction.

---

## SS9 D-Items List

D-items require user authority. Speaker gives recommendation but does not implement or decide for the user.

### D1: Vanilla resource model — Energy-only or multi-resource Vanilla?

Background:
Vanilla/Standard is described as Energy-only in `gameplay.md`, `resource-ledger.md`, and balance-sheet assumptions, but `world-rules.md` examples and Fabricate use Matter. This makes Fabricate either unpayable or undocumented in default Standard/Arena.

Option A: Energy-only Vanilla; Matter is advanced/modded world only.
- Changes: Vanilla Fabricate cost becomes pure Energy or world-configurable with Vanilla pure-Energy default; `world-rules.md` Matter examples become explicitly non-Vanilla examples.
- Recommended.
- Reason: Preserves Golden Path simplicity and existing balance-sheet/resource-ledger assumptions.

Option B: Multi-resource Vanilla with Energy + Matter.
- Changes: Add Matter faucets/sinks/storage/tax/tutorial/starter bot/balance-sheet support; all Standard/Arena docs must teach and price Matter.
- Not recommended for R44 unless user wants a more complex baseline.
- Reason: Larger design surface and undermines current onboarding promise.

Speaker recommendation: A.

### D2: World PvP positive incentive — add Wreckage, conquest reward, both, or no economic PvP reward?

Background:
`dsv4-design-economy.md` argues World PvP has no positive expected value, creating “optimal strategy = avoid combat.” Other reports flag related mid/late motivation and logistics/intercept issues.

Option A: Wreckage drops from defeated drones.
- Description: Defeated enemy drones generate reclaimable Wreckage worth a bounded percentage of body cost, from a world faucet budget rather than directly stealing from the loser.
- Recommended as minimal first incentive.
- Reason: Creates local tactical reward without double-punishing the defeated player.

Option B: Conquest / territory reward.
- Description: Controller capture gives a one-time reward or progress/resource conversion; reward balanced against future upkeep.
- Partially recommended, but higher risk.
- Reason: Stronger strategic incentive, but easier to abuse and entangles expansion economy.

Speaker recommendation: A first; consider B only after anti-abuse and season/territory goals are specified.

### D3: New-player economy transition — ramp subsidy, retune baseline, or hard-core survival pressure?

Background:
Reports agree free_upkeep and protection timing create a cliff: tick 2000 can simultaneously end free upkeep/open PvP/force net-negative economy.

Option A: Smooth/ramped transition.
- Description: free_upkeep decays over a window after soft_launch; PvP opening and full upkeep are decoupled; add failure recovery for 1→2 room transition.
- Recommended.
- Reason: Matches soft_launch philosophy and reduces player churn without discarding anti-snowball.

Option B: Retune economic parameters for basic-code positive flow at 1-3 rooms.
- Description: Lower base_upkeep, increase room_soft_cap, or raise passive income so basic code can survive longer.
- Also viable, but should be combined with A only after recalculation.
- Reason: Directly fixes balance-sheet negatives but changes the global economy more broadly.

Speaker recommendation: A as design direction, then recalculate whether B is also needed.

### D4: Late-game expansion and World goal structure — strict anti-snowball cap or broader empire viability?

Background:
`dsv4-design-economy.md` argues O(n²) upkeep makes 10+ rooms economically irrational, potentially turning expansion into self-destruction. This interacts with PvP incentive and World retention.

Option A: Keep strict anti-snowball; add non-asset goals.
- Description: 5-10 rooms is intended stable empire size; late-game goals are PvE prestige, Arena seeding, code efficiency, seasonal/reputation systems, not infinite expansion.
- Recommended if Swarm wants anti-monopoly World.
- Reason: Preserves core anti-snowball math and avoids large-empires dominating.

Option B: Make 10-15 room empires economically viable, then curve sharply.
- Description: Use gentler upkeep before 15 rooms or add high-complexity income sources.
- Not rejected, but riskier.
- Reason: Supports expansion fantasy but may reintroduce snowball pressure.

Speaker recommendation: A unless user explicitly wants larger empire fantasy as core World identity.

### D5: Sharding target state — true multi-Engine shards or single-Engine room partitions?

Background:
Architecture and shard-protocol conflict on per-shard Engine/redb vs same-process/same-redb room partitions and Jump Hash vs static coordinate sharding.

Option A: True multi-Engine static shards.
- Description: Each shard has its own Engine/redb/failure domain; static coordinate assignment; cross-shard moves/combat use deterministic tick-barrier protocol and global anchor hash.
- Recommended.
- Reason: Matches architecture.md horizontal scaling and failure-domain story.

Option B: Single Engine room-partition only.
- Description: Rename shard-protocol to room partition; remove multi-node/multi-Engine claims; same process and same redb transaction remain authoritative.
- Not recommended if scale-out is a core target, but simpler.
- Reason: Easier determinism/ops, but contradicts current horizontal scale promise.

Speaker recommendation: A.

### D6: NATS/distributed sandbox security depth — transport ACL only or message-level signed envelopes too?

Background:
NATS carries snapshots, WASM/module artifacts, sandbox requests/replies, and tick deltas. Current docs lack trust boundary and replay protection.

Option A: NATS TLS/auth/ACL + message-level request/reply MAC/signatures and nonce/replay correlation.
- Recommended.
- Reason: Defense in depth; handles compromised/buggy worker, stale reply replay, subject confusion, and audit attribution.

Option B: NATS TLS/auth/ACL only; rely on private network and validation.
- Not recommended for target-state security.
- Reason: Does not solve forged/replayed/mismatched replies or compromised worker identity cleanly.

Speaker recommendation: A.

### D7: Snapshot omitted counts — exact numeric counts or oracle-safe buckets?

Background:
Snapshot contract shows exact `omitted_categories` counts, while visibility oracle defense requires bucketed counts. API surfaces also use `omitted_count` elsewhere.

Option A: Oracle-safe buckets for player-visible outputs.
- Description: `omitted_categories` values become enums such as `0/few/some/many/extreme`; exact counts remain internal/admin/debug only.
- Recommended.
- Reason: Preserves visibility/oracle defense.

Option B: Exact numeric counts everywhere.
- Not recommended.
- Reason: Easier UX/debug but leaks entity-count side channels.

Speaker recommendation: A.

### D8: Plugin/mod execution model — fixed hook surface or extensible Bevy schedule?

Background:
`gpt-architect.md` finds conflict between fixed 31-system Tick Manifest and plugin systems that can inject ECS logic before/after execution.

Option A: Fixed schedule / fixed hook surface.
- Description: Mods register schemas, ActionRegistry handlers, SpecialEffect reducers, resource formulas, NPC behavior tables; no arbitrary Bevy system injection into authoritative schedule.
- Recommended.
- Reason: Keeps replay, R/W matrix, and Unique Writer Contract tractable.

Option B: Extensible schedule with plugin systems.
- Description: World Manifest includes plugin system IDs, order constraints, R/W sets, hashes, CI checks across plugin graph.
- Not recommended for core target unless mod power is a top priority.
- Reason: More flexible but much higher determinism and verification complexity.

Speaker recommendation: A.

### D9: Gateway implementation language — Rust or Go?

Background:
`design/README.md` and `architecture.md` say Gateway is Rust/axum; `gateway-protocol.md` says Go/stateless.

Option A: Rust/axum Gateway.
- Recommended.
- Reason: Consistent with current Rust engine stack and design docs; likely easier shared types/codegen/security review.

Option B: Go Gateway.
- Not recommended unless there is an external operational reason.
- Reason: Introduces separate runtime/ecosystem and contradicts most design docs.

Speaker recommendation: A.

### D10: Replay retention horizon — deterministic replay 180d or rich artifacts 180d / deterministic 30d?

Background:
Persistence docs imply Blob 180d, keyframe 30d, and possible redb full rebuild, but do not define whether 180d deterministic replay is actually guaranteed.

Option A: Deterministic replay for 180d.
- Description: Retain keyframe + delta chain + replay-critical subset for 180d; Blob/RichTrace may have separate tiers; backups include all replay-critical artifacts.
- Recommended if audit/competitive disputes are core.
- Reason: Matches strong audit promise but increases storage/ops burden.

Option B: Deterministic replay 30d; rich artifacts 180d.
- Description: Publicly expose replay horizon; after 30d, old ticks may have rich/audit metadata but not guaranteed deterministic reconstruction.
- Viable if storage/ops simplicity is more important.
- Reason: Honest and cheaper, but weakens long-term audit.

Speaker recommendation: A for Arena/competitive worlds; B may be acceptable for casual World if explicitly mode-scoped.

### D11: New-player transfer lock semantics — send-only, receive-only, or send+receive?

Background:
`gpt-design-economy.md` finds send-only in gameplay, send+receive in resource-ledger, receive-only in snapshot-contract.

Option A: send+receive lock during new-player protection.
- Recommended.
- Reason: Strongest anti-smurf/funneling rule and aligns with Resource Ledger.

Option B: send-only or receive-only lock.
- Not recommended as default.
- Reason: Each leaves one abuse direction open, though it improves social assistance.

Speaker recommendation: A, with non-resource mentorship/help channels to preserve friend onboarding.

### D12: Arena visibility default — participant fog-of-war or full-information Arena?

Background:
`gpt-design-economy.md` flags Arena fog-of-war conflict: some docs say participant drone view/fog, world-rules says Arena full visibility.

Option A: Participant WASM uses fog-of-war/drone perception; spectator/replay can be delayed full view.
- Recommended.
- Reason: Preserves World skill transfer and scouting/deception strategy.

Option B: Full-information Arena by default.
- Not recommended as default; valid as a room variant.
- Reason: Fair and simpler, but compresses strategy space.

Speaker recommendation: A.

---

## Direction专属 High

### Architecture-only High

| ID | Finding | Source | Disposition |
|---|---|---|---|
| A-H1 | Host Function ABI count/signature/fuel conflict | `gpt-architect.md` C3 | Blocker B9. |
| A-H2 | Plugin systems vs fixed Tick Manifest boundary | `gpt-architect.md` C4 | D8 required. |
| A-H3 | MCP tool registry/Auth count/capability profile drift | `gpt-architect.md` C2 | Fold into DDC-1 authority/codegen cleanup; may be blocker under API consistency if not fixed with B1. |
| A-H4 | Command ordering sorting key/seed domain inconsistent | `gpt-architect.md` T3 and `glm-architect.md` CX-8 | High direct fix: one canonical sorting key in tick-protocol §9.1. |
| A-H5 | Drone messaging active side-channel vs out-of-scope command | `gpt-architect.md` T2 | High clarification: distinguish `TickResult.messages` from `SendMessage` CommandAction or remove active surface. |

### Design-Economy-only High

| ID | Finding | Source | Disposition |
|---|---|---|---|
| E-H1 | World PvP lacks positive incentive loop | `dsv4-design-economy.md` CF-1 | D2 required. |
| E-H2 | Expansion beyond ~10 rooms becomes economically irrational | `dsv4-design-economy.md` CF-4 | D4 required. |
| E-H3 | RCL progress conversion rate missing | `dsv4-design-economy.md` DT-5 | Direct fix or user-set rate. |
| E-H4 | Economy-balance-sheet storage_capacity and arithmetic errors | `glm-design-economy.md` SS1-5/SS1-6 | Direct fix before next review. |
| E-H5 | Source density assumptions undocumented | `glm-design-economy.md` SS3-1 | Add default source density and cite in balance sheet. |
| E-H6 | Controller passive income missing from Resource Ledger faucet list | `glm-design-economy.md` SS3-7 | Add ledger entry or remove from balance sheet. |
| E-H7 | Allied Transfer cap/intercept/UX not fully canonicalized | `gpt-design-economy.md` SS2-2 and `dsv4-design-economy.md` DT-3 | Parameter/UX fix after D11 and Resource Ledger sync. |

### Cross-cutting-only High

| ID | Finding | Source | Disposition |
|---|---|---|---|
| C-H1 | Gateway language Rust vs Go | `dsv4-cross-cutting.md` C1 | D9 required. |
| C-H2 | Controller age repair lacks TickTrace attribution | `dsv4-cross-cutting.md` C3 | Direct fix: `AgeRepair` trace event or zero-fee ledger op. |
| C-H3 | Replay retention/keyframe/redb rebuild conflict | `gpt-cross-cutting.md` C3 | D10 required. |
| C-H4 | Gateway public/internal/admin `/metrics` boundary unclear | `gpt-cross-cutting.md` T1 | Direct security/ops fix. |
| C-H5 | Rate-limit authority/limits dispersed | `gpt-cross-cutting.md` T2 | Fold into API Registry/IDL machine-readable authority. |
| C-H6 | Keyframe/world_seed secrecy and backup policy incomplete | `gpt-cross-cutting.md` T3 | Direct security/runbook fix. |
| C-H7 | CVE-SLA missing deterministic/runtime dependencies | `dsv4-cross-cutting.md` T3 | Direct CVE-SLA update. |

---

## Medium / Low 处置

| Finding cluster | Representative sources | Severity | Speaker disposition |
|---|---|---:|---|
| Stale directories, RFC paths, fdb legacy references, anchor drift | `dsv4-architect.md` C1-C5 | Medium/Low | Direct cleanup; no D-item. |
| Unicode truncation `⏏` | `dsv4-architect.md` C1 | Medium | Repo-wide repair and editor/tooling check. |
| world.toml floats / f64 examples vs fixed-point contract | `gpt-architect.md` T1, `glm-architect.md` T6, `gpt-design-economy.md` CX-1 | Medium/High | Direct fix: bps/fixed-point only. |
| Deploy audit archive vs activation dependency | `gpt-architect.md` T4 | Medium | Rename `wasm_module` async blob to audit archive; separate deploy status from archive status. |
| GlobalWithdraw delay naming drift | `gpt-architect.md` T6 | Medium | Direct rename to Resource Ledger canonical field. |
| Move-as-Action tension | `dsv4-architect.md` T4, `dsv4-design-economy.md` DT-1 | Low/Medium | Keep playtest-gated; not a blocker. |
| Storage tax player comprehension | `gpt-design-economy.md` SS2-4, `glm-design-economy.md` SS3-2, `dsv4-design-economy.md` DT-2 | Medium | Add human-readable per-hour/per-day examples and UI warnings. |
| MCP onboarding “available actions” / MoveTo stale wording | `gpt-design-economy.md` SS2-5 | Medium | Rename/explain as schema discovery; remove MoveTo. |
| Sandbox memory/cpu limits local vs distributed | `gpt-cross-cutting.md` T4, `glm-cross-cutting.md` CC-T1 | Medium | Add profile table; keep CPU wall-clock/cgroup constraints. |
| CRL fallback undefined | `glm-cross-cutting.md` CC-T5 | Medium | Direct security policy: timeout, TTL, fail-closed/grace period. |
| Staging GC crash accumulation | `dsv4-cross-cutting.md` T4 | Medium | Add health check/startup cleanup/TTL policy. |
| Observability, upgrade, migration, RTO/RPO, anti-cheat thresholds | `glm-cross-cutting.md` S2-S8, `dsv4-cross-cutting.md` S1 | Medium | Ops backlog for production readiness; not all block design sync unless tied to B4/B10. |
| Personality `efficiency` naming confusion | `glm-design-economy.md` SS2-8 | Low | Rename to `diligence`/`vigor`. |
| PvE Golden Path timing may be optimistic | `glm-design-economy.md` SS3-4 | Low | Clarify starter bot combat path or make PvE kill optional. |

---

## CrossCheck 补漏发现

No separate Phase 2 reports were provided for R44 Speaker synthesis. CrossCheck items embedded inside the nine Phase 1 reports were incorporated into SS2/SS3/SS8 where they were corroborated or safety-critical.

Notable CrossCheck-derived additions:
- `host_get_random`/RNG domain/fuel and replay drift concerns elevated into B9.
- `player_view=full`/Arena/MCP visibility concerns incorporated into D12 and B8 adjacent work.
- `transfer_id` deterministic generation for AlliedTransfer intercept should be checked during Resource Ledger/snapshot cleanup.
- `Fabricate` entity type transmutation and Depot claim semantics need engine/API validation when special attack and structure tables are corrected.
- Seed-bump entropy and keyframe secrecy folded into B10/C-H6.

---

## Final Speaker Notes

The remediation should not be a piecemeal typo pass. R44 needs a short design-decision round for D1-D12, followed by a consistency rewrite that removes duplicate canonical tables. The highest-leverage sequence is:

1. User rulings: D1, D5, D6, D7, D8, D10 first because they affect many files.
2. API/codegen authority cleanup: B1, B2, B3, B9.
3. Security/ops cleanup: B5, B8, B10, C-H4/C-H6/C-H7.
4. Economy/gameplay cleanup: B6, B7, D2-D4, E-H3-E-H7.
5. Structural cleanup: authority map, stale references, target-state language, examples generated or marked illustrative.

No implementation or design-document edits were performed by Speaker; this file is the裁决 artifact only.

---

## §9b D-Item User Rulings（2026-06-30 用户裁决，已完成）

| D | 议题 | 裁决 | 方向 |
|---|------|------|------|
| D1 | Vanilla 资源模型 | Energy-only Vanilla；Matter → advanced/mod world；Fabricate 成本改为纯 Energy | A |
| D2 | World PvP 正向激励 | Wreckage（残骸）机制；残骸价值 ≤ drone body cost 百分比，随 tick 衰减；效率严格低于 Recycle（Recycle 10-50%，Wreckage 更低） | A + 约束 |
| D3 | 新手经济过渡 | 重调基线参数：降 base_upkeep、提 room_soft_cap、加被动收入，让基础代码在 1-3 房间可持续正流 | B |
| D4 | 后期扩张目标 | 更大帝国可行；anti-snowball O(n²) 曲线的常数因子设定在「顶级代码可达 15+ 房，普通代码停在 5-10」——天花板是代码能力，非硬性经济死刑 | 用户裁定 |
| D5 | Sharding 架构 | 真多 Engine 静态坐标分片：每 shard 独立 Engine + redb + 故障域；静态坐标分配；跨 shard 移动用 tick-barrier 协议 | A |
| D6 | NATS 安全深度 | NATS ACL+TLS only（消息级签名无必要：mod 是 Bevy Plugin 同进程，被攻破的 Engine 可签任何消息；安全深度由 D8 hook surface + 源码审查保障） | B |
| D7 | 快照省略计数 | Oracle 安全分桶：玩家可见输出 `0/few/some/many/extreme`；精确计数仅 admin/debug 内部 | A |
| D8 | Plugin 执行模型 | 可扩展 schedule：mod 可注入任意 Bevy system；mod 源码分发 → 服务器主人在编译前审查代码 → 安全边界在审查层 | B |
| D9 | Gateway 技术选型 | Rust + axum（tokio 生态，与 Engine 统一；具体框架如 axum/actix-web 中选定 axum） | A |
| D10 | 重放保留期 | world.toml 配置化：竞技/Arena 世界可设 180d 确定性重放；休闲世界可设 30d 确定性 + 180d 富制品 | 配置化 |
| D11 | 新手转账锁 | 移除 — 不区分新老玩家，统一转账规则；依赖 anti-snowball 数学 + rate limit 防滥用 | 移除 |
| D12 | Arena 可见性 | 参与者 fog-of-war（WASM drone 感知范围）；观众/回放可延迟全图；保留侦察策略深度 | A |

### 裁决执行顺序

1. D1, D5, D8 — 影响面最广（资源模型、分片架构、插件边界）
2. D9 — Gateway axum 选型
3. D2, D3, D6 — 经济与安全参数
4. D4, D7, D10 — 曲线/可见性/retention
5. D11 — 移除（文档清理）
6. D12 — Arena 默认

### 受影响文档 (per D-item)

- **D1**: `design/gameplay.md`, `specs/core/world-rules.md`, `specs/core/resource-ledger.md`, `specs/reference/special-attack-table.md`, `design/economy-balance-sheet.md`
- **D2**: `design/gameplay.md` §combat, `specs/core/resource-ledger.md`, `design/economy-balance-sheet.md`
- **D3**: `design/gameplay.md` §onboarding, `design/economy-balance-sheet.md`, `specs/core/resource-ledger.md`, `specs/core/world-rules.md`
- **D4**: `design/gameplay.md` §expansion, `design/economy-balance-sheet.md`, `specs/core/world-rules.md`
- **D5**: `design/architecture.md`, `specs/core/shard-protocol.md`, `specs/core/persistence-contract.md`, `specs/core/tick-protocol.md`
- **D6**: `specs/core/distributed-sandbox.md`, `specs/security/gateway-protocol.md`, `RUNBOOK.md`
- **D7**: `specs/core/snapshot-contract.md`, `specs/core/incremental-snapshot.md`, `specs/security/visibility.md`
- **D8**: `design/gameplay.md`, `specs/core/world-rules.md`, `specs/core/phase2b-system-manifest.md`, `specs/core/tick-protocol.md`
- **D9**: `design/architecture.md`, `design/README.md`, `specs/security/gateway-protocol.md`, `specs/security/CVE-SLA.md`
- **D10**: `specs/core/persistence-contract.md`, `specs/core/tick-protocol.md`, `RUNBOOK.md`
- **D11**: `design/gameplay.md`, `specs/core/resource-ledger.md`, `specs/core/snapshot-contract.md`
- **D12**: `design/gameplay.md`, `specs/core/world-rules.md`, `design/modes.md`, `specs/security/visibility.md`

---

## Final Speaker Notes

The remediation should not be a piecemeal typo pass. R44 needs a short design-decision round for D1-D12, followed by a consistency rewrite that removes duplicate canonical tables. **D-items ruled: 6/30/2026 — 12/12 decided.**

The highest-leverage fix sequence after rulings:
1. API/codegen authority cleanup: B1, B2, B3, B9.
2. Sharding/model cleanup: B4, D5.
3. Security/ops cleanup: B5, B8, B10, C-H4/C-H6/C-H7.
4. Economy/gameplay cleanup: B6, B7, D2-D4, E-H3-E-H7.
5. Structural cleanup: authority map, stale references, target-state language, examples generated or marked illustrative.

No implementation or design-document edits were performed by Speaker; this file is the 裁决 artifact only. D-item rulings were appended by the orchestrator after user decision session.
