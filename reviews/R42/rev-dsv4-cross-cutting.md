# R42 Cross-Cutting Review — rev-dsv4-cross-cutting

Reviewer: rev-dsv4-cross-cutting (DeepSeek V4 Pro)
Scope: Full doc set — design/, specs/core/, specs/security/, specs/gameplay/, specs/reference/, root *.md
Focus: Cross-doc consistency (≥2 files per finding), broken links, terminology drift, IDL/Registry alignment

---

## 1. Verdict

**REQUEST_MAJOR_CHANGES**

Three Critical issues found: stale FDB artifact in authoritative persistence contract, conflicting numeric parameter across design and spec, and a wrong component language label in the gateway protocol doc. These are all unambiguous defects that must be fixed before the docs can be considered consistent. Additionally, two High-severity orphan directory references and a terminology split within the same file need attention.

---

## 2. 发现的问题

### Critical

**C-C1: Stale `fdb_manifest_list` in persistence-contract.md §5.3 — FDB artifact in replay verifier input**

- **Files**: `specs/core/persistence-contract.md` line 242, `design/architecture.md` §8 (removed components table), `design/tech-choices.md` §11 (removed components)
- **Description**: `persistence-contract.md` §5.3 "Replay Verifier 输入" lists `fdb_manifest_list` as a replay verifier input parameter. FoundationDB was removed from the architecture in favor of redb (as confirmed by architecture.md §8, tech-choices.md §11, RUNBOOK.md §1). This is the **only** remaining FDB reference in the entire specs tree. All other references correctly use `redb_manifest`/`redb_manifest_list`.
- **Quote**: `persistence-contract.md:242`: `输入: (start_tick, end_tick, fdb_manifest_list, object_store_blobs)`
- **Impact**: Replay verifier implementers reading this section would expect a FoundationDB artifact that does not exist. Creates ambiguity about the authoritative manifest source for replay validation.
- **Fix**: Replace `fdb_manifest_list` → `redb_manifest_list` (or equivalent `tick_manifest` reference). Verify that the parameter name aligns with the `tick_manifest` table described in §2.2–2.3 of the same document.

**C-C2: RangedAttack body part cost conflict — design/gameplay.md (150 Energy) vs specs/core/world-rules.md (100 Energy)**

- **Files**: `design/gameplay.md` line 879, `specs/core/world-rules.md` line 372, `specs/gameplay/api-idl.md` line 178, `specs/reference/api-registry.md` §10
- **Description**: The RangedAttack body part spawn cost has two conflicting values across the documentation:
  - `design/gameplay.md` §[[body_part_types]] table: `cost = { Energy = 150 }`
  - `specs/gameplay/api-idl.md` body_cost table: `RangedAttack: { Energy: 150 }`
  - `specs/core/world-rules.md` §7.1 body_part_types example: `cost = { Energy = 100 }`
  
  Two authoritative documents agree on 150; world-rules.md is the outlier.
- **Impact**: Implementers following world-rules.md alone would set RangedAttack spawn cost to 100 instead of 150 — a 33% cost reduction that affects economic balance. The cost appears in the Economy Balance Sheet calculations and influences anti-snowball tuning.
- **Fix**: Align `specs/core/world-rules.md` line 372 to `cost = { Energy = 150 }` (matching gameplay.md and api-idl.md). Add a cross-reference note pointing to api-idl.md body_cost table as canonical so future divergences are caught.

**C-C3: Gateway language label says "Go" but architecture is Rust — single-doc terminology error**

- **Files**: `specs/security/gateway-protocol.md` line 13, `design/README.md` line 84, `design/architecture.md` lines 60–61, `design/tech-choices.md` §1–11
- **Description**: `gateway-protocol.md` §1 "架构定位" ASCII diagram labels the Gateway as `(Go, 无状态)`. All other architecture documents consistently describe Gateway as Rust:
  - `design/README.md` line 84: `网关 (Rust)`
  - `design/architecture.md` §3: Gateway box labeled `Rust (axum)`
  - `design/tech-choices.md` §1–11: No Go component exists; engine, sandbox, gateway are all Rust
  - `design/tech-choices.md` §11 "已移除的组件" does not include any Go→Rust migration
  - RUNBOOK.md §7: Gateway = "Rust 独立进程"
- **Impact**: The gateway-protocol.md is the **cross-domain protocol document** that `AGENTS.md` line 80 explicitly describes as the converging reference for Gateway behavior (`汇聚 specs/core/01 §4 + specs/security/03 §2 等`). A wrong language label in this convergence doc could mislead implementers about the technology stack and the protocol's expected runtime characteristics.
- **Fix**: Change `(Go, 无状态)` → `(Rust, 无状态)` in gateway-protocol.md line 13.

### High

**C-H1: Orphan directory references in AGENTS.md — `specs/core/10-11/` does not exist**

- **Files**: `AGENTS.md` line 40, `design/README.md` lines 17 and 39
- **Description**: AGENTS.md line 40 states:
  ```
  specs/core/10-11/ 增量快照 + 多世界分片协议（原 T2/T3 已纳入核心）
  ```
  The actual files `incremental-snapshot.md` and `shard-protocol.md` reside directly in `specs/core/` — there is no `specs/core/10-11/` subdirectory. This appears to be a leftover from a numbering scheme that was abandoned when numeric prefixes were dropped from spec filenames (per R41 grill-me cleanup pattern).
- **Impact**: New contributors or AI agents following AGENTS.md file paths will look for a non-existent directory. The doc structure description in AGENTS.md is supposed to be the authoritative navigation reference.
- **Fix**: Change `specs/core/10-11/` → `specs/core/` in AGENTS.md line 40. The parenthetical "(原 T2/T3 已纳入核心)" is fine to keep.

**C-H2: Root README.md references `specs/future/` directory that does not exist**

- **Files**: `README.md` line 17, 39; `design/README.md` line 39
- **Description**: Root README.md line 17 lists `specs/` → `future` as a subdirectory, and line 39 shows:
  ```
  ├── future/             扩展路线 (T2 增量快照/T3 分片)
  ```
  The actual directory structure has no `specs/future/` — incremental-snapshot.md and shard-protocol.md are in `specs/core/`. Similarly, design/README.md line 39 says:
  ```
  ├── specs/future/             扩展路线 (T2 增量快照/T3 分片)
  ```
  Neither location has a `future/` directory.
- **Impact**: Broken navigation — both the root README and design README point readers to a directory that doesn't exist. The "扩展路线" content has been merged into core specs.
- **Fix**: In both README.md and design/README.md, either remove the `future/` directory entry or create a redirect note. The tree diagram in README.md lines 26–47 should reflect the actual directory structure: `specs/core/`, `specs/security/`, `specs/gameplay/`, `specs/reference/`.

**C-H3: "Blob Store" vs "对象存储" (Object Store) terminology split within persistence-contract.md**

- **Files**: `specs/core/persistence-contract.md` (throughout), `design/architecture.md` §6a, `design/README.md` glossary
- **Description**: The `design/architecture.md` §6a is explicitly titled "Blob Store（非权威二进制存储）" and the glossary in `design/README.md` defines `RichTraceBlob` storage as "Blob Store". However, `persistence-contract.md` uses the terms interchangeably:
  - §1 "原则" line 24: storage layer table says "Blob Store"
  - §2.2 "Debug/Rich" line 60: "对象存储中不存放 replay-critical 数据" (object store)
  - §3 "Tick Commit 序列" Phase C: "对象存储异步写入" (object store async write)
  - §6 "GC" line 251: "对象存储 GC" (object store GC)
  
  The document uses both "Blob Store" (English header) and "对象存储" (Chinese body text) without establishing which is canonical. This creates ambiguity about whether "Blob Store" and "Object Store" are the same thing. The glossary clarifies they are the same — but the persistent mixed usage within a single authoritative document undermines that clarity.
- **Impact**: Implementers could interpret "对象存储" as a generic object store (S3/minio) while "Blob Store" might be read as a bespoke subsystem, leading to incorrect storage backend choices.
- **Fix**: Standardize on "Blob Store" throughout `persistence-contract.md`. Either use "Blob Store" everywhere or add a §1 notation: "本文档中「Blob Store」与「对象存储」为同义词，均指向 architecture.md §6a 定义的 Blob Store 层。"

**C-H4: GETTING-STARTED.md references non-existent `swarm_deploy_challenge` tool**

- **Files**: `GETTING-STARTED.md` line 92, `specs/reference/api-registry.md` §3.2–3.3
- **Description**: GETTING-STARTED.md §4.2 step 8 says:
  ```
  不需要先请求 `swarm_deploy_challenge`——防重放由 `version_counter` 保证。
  ```
  The text correctly states this tool is not needed, but the tool `swarm_deploy_challenge` does not exist in the API Registry at all. It is not in the all_declared, active_only, or rfc_gated lists. A beginner reading this will wonder what this non-existent tool is and why it's mentioned.
- **Impact**: Confusion for new developers who might search for `swarm_deploy_challenge` in the registry or IDL and find nothing. The onboarding experience is degraded by a reference to a ghost tool.
- **Fix**: Reword to: "防重放由 DeployPayload 中的 `version_counter` 单调递增保证，无需额外的 challenge 步骤。" Remove mention of the non-existent tool name entirely.

### Moderate

**C-M1: NATS capitalization inconsistency in RUNBOOK.md**

- **Files**: `RUNBOOK.md` (throughout), `design/architecture.md` §7, `design/tech-choices.md` §5
- **Description**: RUNBOOK.md uses "NATS" (standard capitalization per NATS.io official branding) in most places but "nats" (lowercase) appears in:
  - Line 33: entry for NATS uses lowercase in same table that uses title-case for other services
  - `docker compose exec nats` commands (lowercase service name — acceptable for docker)
  - `nats server check connection` (lowercase when referring to the binary — acceptable)
  
  The table at line 31–36 shows the service column entry for NATS inconsistently compared to other entries (Engine, Gateway, Frontend all capitalized).
- **Impact**: Minor visual inconsistency. The binary name `nats` is correct in shell commands; the service name should be "NATS" in prose.
- **Fix**: Use "NATS" in all prose contexts in RUNBOOK.md. The `nats` binary name in shell commands is correct and should stay.

**C-M2: "Vanilla (Novice)" vs "Novice" mode naming ambiguity in economy-balance-sheet.md**

- **Files**: `design/economy-balance-sheet.md` §3 header table, `design/gameplay.md` §2.2, `design/modes.md`
- **Description**: `economy-balance-sheet.md` §3 "模式差异" table uses column header "Vanilla (Novice)" to describe one difficulty tier, while `design/gameplay.md` §8 "渐进解锁" table uses columns "Tutorial", "Novice", "Standard", "Advanced" as distinct tiers. The parenthetical "(Novice)" suggests equivalence but the two docs describe different concept spaces:
  - economy-balance-sheet.md: "Vanilla (Novice)" is an economic difficulty tier with `base_upkeep = 30`
  - gameplay.md: "Novice" is a world difficulty tier that disables all special attacks
  - modes.md: Doesn't use "Novice" at all — uses "World" / "Arena" / "PvE Challenge"
- **Impact**: A world operator configuring `world.toml` might conflate the economic "Vanilla (Novice)" tier with the gameplay "Novice" difficulty tier, which have overlapping but distinct parameter spaces.
- **Fix**: Either rename the economy column to "Novice" (matching gameplay.md) and drop "Vanilla", or add a clarifying note explaining the naming convention.

**C-M3: design/README.md §3 "回放数据" uses flat key paths inconsistent with persistence-contract.md hierarchical key layout**

- **Files**: `design/README.md` lines 183–188, `specs/core/persistence-contract.md` §3, §8, `specs/core/tick-protocol.md` §3.5
- **Description**: design/README.md §3 "回放数据" table shows flat key paths:
  ```
  /tick/{N}/commands, /tick/{N}/state, /tick/{N}/rejections, ...
  ```
  The authoritative persistence-contract.md and tick-protocol.md use hierarchical paths:
  ```
  /committed/head/{tick}, /committed/manifest/{tick}, /staging/{namespace_epoch}/{room_hash}
  ```
  The design/README flat paths don't match the actual Shadow Write / committed/staging hierarchy described in persistence-contract.md §8 and tick-protocol.md §3.5.
- **Impact**: Readers of design/README.md get a simplified model that doesn't reflect the Shadow Write architecture. This is a "导航 vs 规范" gap — the navigation doc should accurately describe the data layout or should explicitly note it's a conceptual simplification.
- **Fix**: Either update design/README.md to reflect the actual key hierarchy (preferred) or add a note: "以上为逻辑路径，物理存储见 persistence-contract.md §8 Shadow Write 分区策略。"

**C-M4: `hint_level` field name inconsistency — `world.hint_level` vs `hint_level` in snapshot-contract.md and mcp-security.md**

- **Files**: `specs/core/snapshot-contract.md` §4.5, `specs/security/mcp-security.md` (no hint_level mention)
- **Description**: snapshot-contract.md §4.5 uses `world.hint_level` as the config field name. visibility.md references `detail_level` (from api-registry.md §2). Neither document explicitly states whether `hint_level` and `detail_level` are the same field. This is a cross-cutting concern because:
  - api-registry.md §2 defines `detail_level` with values `competitive`/`practice`/`training`
  - snapshot-contract.md §4.5 defines `world.hint_level` with the same three values
  - These appear to be the same concept under two names
- **Impact**: Implementers unsure whether to look for `hint_level` or `detail_level` in world config. SDK codegen may produce different field names.
- **Fix**: Unify on a single name. Given api-registry.md is the canonical schema authority, align snapshot-contract.md to use `detail_level`. Add a cross-reference from visibility.md to api-registry.md for the canonical field definition.

**C-M5: design/gameplay.md §2.2 `[[special_effects]]` mentioned but not defined**

- **Files**: `design/gameplay.md`, `specs/gameplay/api-idl.md` §5.2, `specs/core/world-rules.md`
- **Description**: gameplay.md discusses the "Vanilla Action 方式" extensively and api-idl.md §5.2 references `[[special_effects]]` as "可复用效果 handler". However:
  - The `[[special_effects]]` TOML section is never defined with its schema
  - world-rules.md does not have a `[[special_effects]]` section in its config schema
  - The term appears only in api-idl.md §5.2 as a forward reference without definition
- **Impact**: World operators reading api-idl.md will expect to find `[[special_effects]]` configuration but it's not defined anywhere. Mod developers implementing custom special effects have no specification to follow.
- **Fix**: Either define the `[[special_effects]]` TOML schema in world-rules.md, or remove the forward reference from api-idl.md §5.2 if the concept is covered by ActionRegistry registration.

---

## 3. 亮点

1. **Glossary-driven disambiguation** (design/README.md 附录 C): The centralized glossary defining `TickCommitRecord`, `RichTraceBlob`, `ReplayArtifact`, `RawCommand`, `CommandIntent`, `ValidatedCommand`, `DeployPayload`, `PendingEntityCreation`, `TickInputEnvelope`, and `redb_version_counter` with explicit storage layer assignments is a strong cross-cutting practice. Every spec that uses these terms can avoid redefinition.

2. **Single economic authority** (resource-ledger.md): The consistent delegation pattern where `design/economy-balance-sheet.md`, `design/gameplay.md`, and `design/engine.md` all defer to `specs/core/resource-ledger.md` §2 for canonical fee/basis-points/parameter definitions is well-executed. The tiered storage tax formula is consistently referenced rather than copied.

3. **API Registry as single source of truth**: The api-registry.md's §1 (CommandAction), §2 (RejectionReason with condition→code→debug_detail mapping), §3 (MCP Tools with all_declared/active_only/rfc_gated split), and §4 (Host Functions) provides a genuine single authority that other docs consistently reference. The CI gate requiring Registry↔IDL YAML↔generated code alignment is a strong design contract.

4. **Snapshot Contract's critical entity reserve**: The `critical_entity_reserve = 128KB` design in snapshot-contract.md §1.4, combined with the minimum retention set guarantee, provides clear implementable bounds for snapshot truncation that prevent tactical-information loss while maintaining the 256KB budget.

5. **Consistent reference to `phase2b-system-manifest.md` for scheduling authority**: Every doc that discusses Phase 2b ECS system ordering (tick-protocol.md, command-validation.md, engine.md) consistently points to `specs/core/phase2b-system-manifest.md` as the single scheduling authority rather than duplicating system ordering. This prevents the common problem of stale scheduling copies.

---

## 4. CrossCheck

Items below are suspicious but outside the Cross-Cutting direction's definitive scope. Each points to the relevant direction for investigation.

**CX-1: `phase2b-system-manifest.md` referenced but not read — structural verification needed**
→ 建议 **Architect** 方向检查 `specs/core/phase2b-system-manifest.md` 是否实际存在且内容与 tick-protocol.md §3.4 引用一致（31 systems, serial spine + 2 parallel sets, R/W matrix）

**CX-2: Blob Store backend config (`world.toml` S3 section) — consistency with economy model**
→ 建议 **Design & Economy** 方向检查 `design/architecture.md` §6a 的 Blob Store S3 配置是否与 resource-ledger.md 的费用模型产生隐式耦合（S3 存储成本是否需要经济核算）

**CX-3: Arena `tick_interval_ms = 300` vs World `tick_interval_ms = 3000` — confirmed consistency?**
→ 建议 **Architect** 方向验证 Arena 的 300ms tick interval (modes.md §9.1.2, engine.md §3.4.1) 是否与所有 per-player sandbox deadline (200ms), EXECUTE budget (50ms), COMMIT budget (20ms) 在数值上闭合

**CX-4: `swarm_get_world_stats` — Arena "段位统计" vs World "非竞争统计" routing**
→ 建议 **Design & Economy** 方向检查 api-registry.md §3.2 Play 表中的 `swarm_get_world_stats` 是否在 World 和 Arena 模式下正确路由到不同的统计口径（gameplay.md §Vanilla Ruleset 声称 Arena 有段位统计但 Registry 只列了一个工具）

**CX-5: `allied_transfer_enabled` default varies by mode — consistency verified?**
→ 建议 **Design & Economy** 方向检查 economy-balance-sheet.md §3 声称 Standard 默认 `allied_transfer_enabled = true (Restricted)` 但 resource-ledger.md §2.1 的 Allied Transfer 参数表未区分 World/Standard/Novice 默认值，需要验证两者一致性

**CX-6: `Swarm-Certificate` header serialization — single canonical definition?**
→ 建议 **Cross-Cutting** (self) 或 **Architect** 方向后续验证 design/auth.md §7, mcp-security.md §3.1, command-source.md §3.1 三处对 canonical request signature payload 的描述是否逐字节一致（R42 scope 内已确认格式相同，但 payload 拼接顺序需要逐字段交叉比对）

---

*Review completed. All findings cite ≥2 files. No implementation or code files were consulted.*
