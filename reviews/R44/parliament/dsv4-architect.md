# R44 Architecture Review — rev-dsv4-architect

## Verdict: CONDITIONAL_APPROVE

The architecture is sound at its core — the two-layer compute model (COLLECT/EXECUTE), the static shard model, the single-authority redb + shadow-write GlobalTickCommit, and the ECS system manifest show disciplined design. However, several document-level integrity issues (truncated Unicode, numbering gaps, stale directory references) and one structural inconsistency in the persistence contract require resolution before this design can be considered production-ready.

---

## §1 Critical Findings (Blockers)

### C1: Truncated Unicode Characters Across Multiple Documents [Critical]

**Files affected:**
- `design/README.md` line 237: `"## 附录 C: 术语表（Glossary — ⏏"`
- `design/engine.md` line 292: `"31 systems（⏏Stage 2a inline 6 + Stage 2b queued 25）"`
- `specs/core/tick-protocol.md` line 400: `"31 systems（⏏Stage 2a inline 6 + Stage 2b queued 25）"`
- `specs/core/phase2b-system-manifest.md` line 419: `"## 4. Component R/W Matrix（全部 31 systems — ⏏"`
- `design/engine.md` line 330: `"**Action dispatch 与 combat_system 的职责分离（⏏**："`
- `design/engine.md` line 350: `"ECS System 执行顺序固定（见 [Complete Tick Execution Manifest](../specs/core/phase2b-system-manifest.md)，31 systems，⏏"`

These appear to be truncated glyphs from an em-dash (—) or multi-byte Unicode character that was cut off during file editing. While the truncated suffix doesn't break the semantic meaning, it means:
- The documents are in a partially-corrupted state
- Cross-platform deterministic builds could be affected if these chars appear in hash inputs
- The problem appears to be systemic — likely an editor truncation of a specific Unicode sequence

**Fix**: Replace all `⏏` occurrences with their intended characters (likely `—` em-dash or the original Chinese character that was truncated). Run a repo-wide search: `rg '⏏' /data/swarm/docs/` to find all instances.

---

### C2: CommandAction ID Numbering Gap in API Registry [High]

**File**: `specs/reference/api-registry.md` §1.1-1.3

The CommandAction enum uses non-sequential IDs:
- Core: 1 (Move), 2 (Harvest), 3 (Transfer), 4 (Withdraw), 5 (Build), 9 (Spawn), 10 (Recycle), 11 (ClaimController)
- Economy: 12 (TransferToGlobal), 13 (TransferFromGlobal)
- Action dispatch: 22 (Action)

IDs 6, 7, 8 and 14-21 are skipped without documentation. This gap either:
1. Represents removed commands (which should be documented as "reserved" or removed from the numbering space), or
2. Is an artifact of a prior renumbering that wasn't fully cleaned up

The skip from 13 to 22 is particularly suspicious — 8 IDs are missing. If these were previously `Attack`, `RangedAttack`, `Heal`, `Hack`, `Drain`, `Overload`, `Debilitate`, `Disrupt` (8 combat/special actions now in ActionRegistry), this should be explicitly documented in the Registry. The current gap creates confusion about whether those IDs are reserved, deprecated, or free for future use.

**Fix**: Either renumber to a dense sequence (1-11) or add explicit documentation in the Registry explaining each gap ID and its status (reserved/deprecated/moved-to-ActionRegistry). The `swarm_deploy idempotency_key` and module hashing may embed these numeric IDs — verify no serialization dependency on the specific numbers before renumbering.

---

### C3: Stale Directory References in AGENTS.md and README.md [High]

**File**: `AGENTS.md` line 40:
```
specs/core/10-11/ 增量快照 + 多世界分片协议（原 T2/T3 已纳入核心）
```

**File**: `docs/README.md` line 39:
```
├── RFC/             扩展路线 (T2 增量快照/T3 分片)
```

But the actual directory structure under `specs/core/` contains:
- `incremental-snapshot.md` (not in a `10-11/` subdirectory)
- `shard-protocol.md` (same)
- `distributed-sandbox.md` (same)

And there is no `specs/RFC/` directory at all. The `specs/RFC/` directory is referenced both in README.md's directory tree and conceptually, but all T2/T3 material has been merged into `specs/core/`.

**Impact**: New contributors following the directory tree will look for non-existent directories. AI agents reading AGENTS.md get wrong structural information.

**Fix**: 
1. Remove `specs/RFC/` from README.md directory tree
2. Update AGENTS.md line 40 to reflect actual file locations
3. If `specs/RFC/` is intended to exist for future RFCs, either create it or document that RFC materials live in `specs/core/` with appropriate filenames

---

### C4: Persistence Contract References "fdb" (FoundationDB) — Legacy Artifact [Medium]

**File**: `specs/core/persistence-contract.md` line 242:
```
输入: `(start_tick, end_tick, fdb_manifest_list, object_store_blobs)`
```

**File**: `specs/core/snapshot-contract.md` line 467:
```
measured_p95 = recent p95 of (sandbox_exec + snapshot_stitch + fdb_commit)
```

The project uses `redb` as its storage engine (documented throughout design/architecture.md and design/tech-choices.md). References to `fdb` (FoundationDB) are legacy artifacts from a previous design iteration. This is confirmed by:
- `architecture.md` §6 explicitly states "redb 是 Swarm 的权威持久化层"
- No FoundationDB dependency exists anywhere in the tech stack
- The `persistence-contract.md` itself is titled "redb / TickCommitRecord / RichTraceBlob / WAL / Blob Store 分层"

**Fix**: Replace `fdb_manifest_list` with `redb_manifest_list` and `fdb_commit` with `redb_commit` in both files.

---

### C5: economy-balance-sheet.md §5 References Non-Existent API Registry Section [Medium]

**File**: `design/economy-balance-sheet.md` lines 263-264:
```
**Resource Ledger (`specs/core/resource-ledger.md`) 为所有收支计算的单一权威源。**
```

But also references `specs/reference/api-registry.md` §10 for economic operations, and the economy-balance-sheet claims to reference `resource-ledger.md` §Empire Upkeep — however `resource-ledger.md` uses numbered sections (§1-§8), not named anchors like "§Empire Upkeep". The §-style cross-references (`§2.1`, `§Empire Upkeep`) in economy-balance-sheet.md use implicit anchor names that may not resolve in all renderers.

**Impact**: Cross-document link validation would fail if using a strict link checker.

**Fix**: Standardize all cross-document references to use explicit file paths + section numbers, or add explicit anchor IDs in the target documents.

---

## §2 Design Tensions (Inconsistencies, Conflicts)

### T1: Snapshot Architecture — Two-Phase vs Legacy Model Descriptions [Medium]

**design/README.md** §2.1 line 172-174 describes the two-phase snapshot architecture (build once, stitch per-player) as the current model. This is correct per `engine.md` §3.2.

However, **tick-protocol.md** §2.3 line 149-171 pseudocode (`build_world_snapshot` / `stitch_player_snapshot`) uses a deep-copy-then-shard approach that aligns with the two-phase model, but the pseudocode doesn't explicitly mention the `shard_by_room` optimization described in engine.md.

**engine.md** §3.2 line 341 describes the shift from per-player serialization to the shared-snapshot model, which is referenced as an improvement. But the COLLECT phase description in **tick-protocol.md** §2.2-2.3 still reads as if each player gets an independently-serialized snapshot — the stitching optimization is in the pseudocode but the prose section header doesn't indicate the architectural change.

**Recommendation**: Add an explicit architecture note in tick-protocol.md §2.2 stating "快照按房间分片序列化一次，再为玩家 stitch 可见 shard" at the top of the section, matching the claim in engine.md.

---

### T2: Global Storage Tax Curve Anchors — Two Slightly Different Descriptions [Medium]

**gameplay.md** §8 line 359 describes:
```
global_storage_tax_curve: 30%→0bp, 60%→1bp, 85%→5bp, 100%→20bp
```

**resource-ledger.md** §2.2 line 98-106 describes:
```
storage_tax_anchor_0: (300000 ppm, 0 bp)
storage_tax_anchor_1: (600000 ppm, 1 bp)
storage_tax_anchor_2: (850000 ppm, 5 bp)
storage_tax_anchor_3: (1000000 ppm, 20 bp)
```

These are numerically identical (300,000 ppm = 30%), but the representation differs. The gameplay.md uses human-readable percentages while the resource-ledger uses ppm as the authoritative representation. This is acceptable as long as both are kept in sync, but currently:
- gameplay.md describes it as "curve anchors" with `→` notation
- resource-ledger.md describes it as `smoothstep_interpolate` with explicit ppm values
- economy-balance-sheet.md references it as "continuous marginal anchors"

**Recommendation**: Ensure economy-balance-sheet.md explicitly states it references resource-ledger.md §2.2 (which it does in line 265), and add a cross-check note that any change to anchors must update all three files.

---

### T3: Drone Lifespan Default — 1500 in Multiple Places, MIN_LIFESPAN Risk [Low]

**engine.md** line 112 sets `DEFAULT_DRONE_LIFESPAN = 1500`.
**gameplay.md** line 98 sets `drone_lifespan` default = 1500, `MIN_LIFESPAN` default = 100.
**resource-ledger.md** §2.1 sets `BASE_AGE` = 1500, `MIN_LIFESPAN` = 100.

The formula `age_max = max(MIN_LIFESPAN, BASE_AGE + sum(age_modifier))` with body parts like ATTACK (-80) means a drone with 19+ ATTACK parts could theoretically drop below 0 before MIN_LIFESPAN kicks in at 100. With TOUGH (+100), a drone could reach 1600+. These extremes are edge cases but the interplay between `MIN_LIFESPAN`, `BASE_AGE`, and `age_modifier` is spread across three files.

**Recommendation**: Consolidate all lifespan-related parameters into resource-ledger.md §2.1 as the single authority, and have engine.md and gameplay.md reference them.

---

### T4: Move-as-Action Design Tension — Acknowledged, Not a Defect [Low]

**engine.md** §3.2 lines 309-324 explicitly documents the philosophical tension between Move-as-Action (Swarm) and the traditional Move+Action (most RTS). This is well-articulated with specific design rationale. However, the note at line 324:

> "此设计在 playtest 阶段可能被挑战——如果证据表明玩家普遍因 Move 占用 action slot 而流失，可重新评估。"

This is an appropriate playtest-gated note. The architecture is coherent with this design — this is not a defect, merely a documented risk.

---

## §3 Suggestions (Improvements, Simplifications)

### S1: Consolidate Section Numbering in economy-balance-sheet.md

The document jumps from §4 (Anti-Snowball 证明) to §5 (与 Resource Ledger 的关系) to §6 (存储税均衡证明). There is no content gap but the section numbers don't follow a logical flow. Consider restructuring:

Current: §1 Maintenance Curve → §2 收支平衡表 → §3 模式差异 → §4 Anti-Snowball → §5 Resource Ledger → §6 Storage Tax Equilibrium

Suggested: §1 Maintenance Curve → §2 Balance Sheet → §3 Mode Differences → §4 Economic Proofs (merge Anti-Snowball + Storage Tax) → §5 Resource Ledger Relationship

---

### S2: Add Explicit "Single Authority" Designation for Each Domain

While individual files have notes like "本文档为权威..." (resource-ledger.md, persistence-contract.md), there's no centralized mapping of which document is authoritative for which concept. This leads to cross-reference sprawl where 3+ documents all describe the same parameter.

**Recommendation**: Add a "Domain Authority Map" table to design/README.md:

| Domain | Authority Document |
|--------|-------------------|
| Tick lifecycle / system ordering | specs/core/phase2b-system-manifest.md |
| Persistence / redb contract | specs/core/persistence-contract.md |
| Economy parameters / formulas | specs/core/resource-ledger.md |
| Snapshot truncation | specs/core/snapshot-contract.md |
| Command validation | specs/core/command-validation.md |
| API schema / RejectionReason | specs/reference/api-registry.md |
| Body part defaults | game_api.idl.yaml |
| Combat/special attack parameters | specs/reference/special-attack-table.md |

---

### S3: Remove "Queued" / "RFC方向" Language from Architecture Docs

Several documents still contain qualifying language that undermines the "设计即终态" principle stated in design/README.md §1.3:

- **modes.md** line 150: "社区传播（RFC）...为产品扩展项——不阻塞目标设计冻结" — the "(RFC)" tag implies deferred design
- **gameplay.md** line 83: "Boss 与 multi-stage AI 属于 mod surface" — while valid, the surrounding "vanilla_boss Plugin" language creates ambiguity between "this is in the design" vs "this will be a mod"
- **snapshot-contract.md** lines 274-287: The RFC section (§3.3) uses `unimplemented!()` as a placeholder — this is a valid design choice but the language should be definitive ("这些特性明确不在核心设计中") rather than implying they're "queued"

---

### S4: Unify "replay_class" Naming Across Documents

- **persistence-contract.md** uses `deploy_mutation`
- **interface.md** line 156 uses `replay_class: deploy_mutation` 
- **command-source.md** §7.2 uses `deploy_mutation`

But the concept of "replay class" is only defined in interface.md's MCP tool descriptions. There's no central registry of replay classes.

**Recommendation**: Add a replay_class table to api-registry.md §5 or create a dedicated section.

---

### S5: Remove the `specs/core/10-11/` Directory Reference from AGENTS.md

This was already flagged as C3 but deserves explicit mention: the directory structure reference in AGENTS.md is actively misleading. The files `incremental-snapshot.md`, `shard-protocol.md`, and `distributed-sandbox.md` exist flat under `specs/core/`, not in a numbered subdirectory.

---

## §4 Cross-Reference Matrix

| Source Document | Target Reference | Status | Issue |
|----------------|-----------------|--------|-------|
| AGENTS.md → `specs/core/10-11/` | incremental-snapshot.md, shard-protocol.md | **STALE** | Directory doesn't exist; files are flat under specs/core/ |
| README.md → `specs/RFC/` | (nonexistent) | **STALE** | No RFC directory exists |
| persistence-contract.md → `fdb_manifest_list` | redb | **LEGACY** | FoundationDB reference, should be redb |
| snapshot-contract.md → `fdb_commit` | redb | **LEGACY** | Same FoundationDB artifact |
| economy-balance-sheet.md → `resource-ledger.md §Empire Upkeep` | resource-ledger.md §6 | **ANCHOR** | Uses named anchors not present in target |
| gameplay.md → `resource-ledger.md §2.5` | resource-ledger.md | ✅ | Correct reference |
| engine.md → `phase2b-system-manifest.md` | phase2b-system-manifest.md | ✅ | Correct reference |
| command-validation.md → `special-attack-table.md` | special-attack-table.md | ✅ | Correct reference |
| api-registry.md → `game_api.idl.yaml` | (external IDL file) | ⚠️ | IDL files not reviewed — assume correct |
| auth.md → `auth_api.idl.yaml` | (external IDL file) | ⚠️ | Same |
| gateway-protocol.md → `specs/security/03`, `specs/security/05`, `specs/security/09` | command-source.md, visibility.md, mcp-security.md | **NUMBERED** | Uses section numbers that don't match filenames |
| design/README.md glossary → `TickTrace` | persistence-contract.md | ✅ | Three-layer model correctly described |
| feedback-loop.md → `specs/reference/mcp-tools.md` | (not reviewed) | ⚠️ | Assume correct |

---

## Summary

**Core architecture**: The COLLECT/EXECUTE split, static coordinate sharding, redb shadow-write + GlobalTickCommit, and the 31-system ECS manifest are well-designed and internally consistent. The deterministic contracts (seed shuffle, BTreeMap ordering, fixed-point math) are properly specified.

**Documentation integrity**: The Unicode truncation issue (C1) is the most impactful finding — it signals that multiple files were edited with a tool that corrupts specific multi-byte sequences. This needs a systematic fix, not per-file patches.

**Numbering gaps** (C2) and **stale references** (C3, C5) are cleanup items that would block a clean release but don't affect the architectural soundness.

**Legacy artifacts** (C4 — fdb references) indicate the persistence layer was previously FoundationDB before redb was chosen. These should be purged.

The **tensions** identified (T1-T4) are all resolvable through documentation alignment rather than architectural redesign.

---

## CrossCheck Items

### CX-1: IDL YAML vs Registry consistency → suggest `spec-writer` check `api-registry.md` CommandAction numbering gaps
The IDL YAML files (`game_api.idl.yaml`, `auth_api.idl.yaml`, `economy.idl.yaml`) are the machine source for api-registry.md. The CommandAction numbering gaps (IDs 6-8, 14-21 skipped) may originate in the IDL. Verify that the IDL files are the actual source of truth and that the Registry faithfully reflects them.

### CX-2: Transport security spec files exist → suggest `security-reviewer` check `specs/security/` files
gateway-protocol.md references `specs/security/03`, `specs/security/05`, and `specs/security/09` by section number. Confirm that `command-source.md`, `visibility.md`, `mcp-security.md` are indeed the intended targets and that the numbered references don't point to deleted or renamed files.

### CX-3: redb transaction size claims vs actual implementation → suggest `engine-reviewer` verify p99 commit targets
persistence-contract.md §8.3 claims `redb single-tx commit p99 < 200ms` for 500 players and `redb room-partition commit p99 < 500ms` for 1000 players. These are synthetic benchmarks that need empirical validation once the implementation exists. Not a design flaw, but a verification gate.

### CX-4: `host_get_random` calling sequence validation → suggest `security-reviewer` check WASM sandbox contract
wasm-sandbox.md specifies `host_get_random` with a 10-call/tick limit, but the deterministic RNG derivation formula involves `world_seed` which is subject to rotation (tick-protocol.md §3.1). Verify that seed rotation doesn't create a timing window where in-flight WASM calls see different seeds within the same tick.