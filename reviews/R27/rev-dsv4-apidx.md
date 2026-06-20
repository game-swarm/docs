# R27 API/DX Review — rev-dsv4-apidx (DeepSeek V4 Pro)

> Phase 1 Clean-Slate independent review.
> Scope: SDK availability, MCP interface design, Rhai API quality, type system consistency, error handling, developer documentation completeness.
> Docs reviewed: 11 files (~32K tokens), per task constraints.

## Verdict: REQUEST_MAJOR_CHANGES

Critical type-system and codegen consistency gaps block SDK generation and CI trust. Must fix before implementation.

---

## Issues

### Critical (block implementation)

**D1: `object_id` missing from CommandAction parameter declarations in api-registry.md §1**

Every CommandAction JSON example in commands.md and every validation rule in 02-command-validation.md §3 requires `object_id` as a mandatory field on the action object. However, the authoritative parameter column in api-registry.md §1.1–1.3 lists only action-specific parameters (e.g., `direction: Direction4`, `target_id: EntityId`) — `object_id` is absent from all 21 entries. This means IDL → codegen cannot generate SDK types that include the universally required `object_id` field. Every command's generated TypeScript/Rust type would be missing a mandatory field.

**Fix**: Add `object_id: EntityId` to every CommandAction parameter declaration in the IDL and regenerate api-registry.md. `object_id` is a shared across all 21 CommandAction variants.

**D2: codegen.md RejectionReason count = 79, api-registry.md = 47 (32-code gap)**

codegen.md "禁止手写的数值" section states `RejectionReason 数量 (当前 79)`. api-registry.md §2 states "共计 47 个 canonical code（35 from game_api + 12 from auth_api）". This 32-code gap is a blocking CI inconsistency. If the codegen `--check` gate runs, it must fail against this. Either:
- (a) The IDL has 79 codes but the registry was hand-edited to 47, violating the single-source-of-truth contract
- (b) codegen.md is severely stale and its own enforcement claim is false

Either path breaks the IDL → Registry codegen promise.

**Fix**: Align codegen.md with actual IDL count. If the IDL has 47, codegen.md should say 47. Run `--check` and ensure it passes.

**D3: codegen.md CommandAction count = 19, api-registry.md = 21**

Same problem as D2. codegen.md says 19 but api-registry.md §1 says "变体总数: 21" (11 core + 2 global + 8 special). Stale count in a document that claims to enforce consistency. Leech and Fabricate (Tier 2, added in v0.3.0 per changelog) are the +2.

**Fix**: Update codegen.md to 21.

### High (significant DX impact)

**D4: `host_get_objects_in_range` range parameter type: `i32` vs `u32`**

interface.md §5.1: `range: i32`
host-functions.md: `range: i32`
api-registry.md §4.1: `range: u32`

api-registry says `u32` (range is non-negative — correct) while the other two docs say `i32`. The IDL is authoritative but the inconsistency across generated docs means codegen or manual editing is at fault. SDKs generated from conflicting types will produce type errors.

**Fix**: Confirm the IDL type (should be `u32`), then ensure all derived docs match. Add a CI cross-check for host function signature consistency across interface.md, host-functions.md, and api-registry.md.

**D5: codegen.md is hand-written but enforces auto-generation for all other docs**

codegen.md describes the IDL → Registry pipeline with "禁止手写" mandates, but is itself a hand-written document containing stale numeric values (D2, D3). This is self-contradictory — the codegen pipeline document should either be auto-generated from IDL metadata or clearly marked as hand-maintained with a regular audit checklist. Currently it claims enforcement it doesn't meet.

**Fix**: Either auto-generate codegen.md's numeric constants from IDL metadata, or add a prominent warning that this document is hand-maintained and requires manual updates on IDL changes (with a CI reminder).

### Medium (should fix before release)

**D6: Pipeline errors lack numeric codes — bifurcated error handling**

api-registry.md §2.1 lists Pipeline errors (`InvalidJson`, `SchemaViolation`) as "不计入 enum, 统一前置处理" (not counted in enum, unified pre-processing). They have names but no numeric codes. All other RejectionReason codes have numeric indices. This creates a two-tier error handling system: SDK consumers must handle string-named Pipeline errors differently from numbered Validation/MCP/Runtime/Auth errors. For SDK type generation, all errors should have stable numeric codes.

**Fix**: Assign numeric codes to `InvalidJson` (e.g., 0) and `SchemaViolation` (e.g., -1 or a Pipeline-specific range), or make the distinction explicit in SDK type generation: `type RejectionReason = PipelineError | ValidationError | McpError | ...`.

**D7: MCP tool Input/Output schemas don't consistently mark required vs optional**

Some schemas use `?` (`{topic?}`, `{player_id?}`) to mark optionality, but most don't. `{tick_range, player_id}` — are both required? `{scope, limit}` — is limit optional with a default? Without required/optional markers, SDK codegen can't produce correct function signatures. TypeScript would need `limit?: number` vs `limit: number`.

**Fix**: Adopt a consistent convention in the IDL for required vs optional fields. All IDL schemas should explicitly mark every field as required or optional. Regenerate all docs.

**D8: No default values documented for optional MCP parameters**

When `swarm_get_docs` is called without `topic`, what happens? Returns all docs? When `swarm_profile` is called without `player_id`, defaults to caller? These behaviors need to be specified per-tool. Without defaults, AI agents and SDK users don't know what behavior to expect.

**Fix**: Add a `default` column or annotation to optional parameters in the IDL. At minimum, document default behavior in prose per tool.

**D9: No per-tool error catalog for MCP tools**

The RejectionReason system covers WASM command rejection comprehensively, but MCP tools have no documented error mapping. Which tools can return `RateLimited`? Which return `InvalidCertificate`? Which return `NotAuthorized`? AI agents using MCP need to know what errors to expect from each tool call to write robust error handling.

**Fix**: Add an `errors` column to the MCP tools table listing which canonical errors each tool can produce. At minimum, group by tool category (onboarding, play, deploy, etc.) if per-tool is too verbose.

**D10: Two codegen paths documented — confusion**

codegen.md specifies `hermes codegen generate` as the primary tool. api-registry.md appendix A specifies `python3 scripts/generate_api_registry.py` and `yq`/`jinja2-cli` as alternatives. Are these the same tool under different names? Competing implementations? The existence of two documented codegen paths creates confusion about which is authoritative and whether they produce identical output.

**Fix**: Pick one codegen tool and document it exclusively. If the python script is the implementation, codegen.md should reference it. If `hermes codegen` wraps it, say so explicitly.

**D11: `swarm_get_terrain` / `swarm_get_path` listed as MCP tools but marked "host fn only"**

api-registry.md §3.2 Play includes `swarm_get_terrain` and `swarm_get_path` in the MCP tools table with `rate_limit: — (host fn only)` and `rate_limit_key: host_only`. If these are only callable from WASM host functions, they should not appear in the MCP tools list at all — they're not MCP-accessible. If they ARE MCP-accessible, the "host fn only" label is misleading and they need proper rate limits. This ambiguity breaks the API surface clarity for MCP client developers.

**Fix**: Clarify whether these are MCP-accessible. If yes, give them proper rate limits (e.g., 10/tick). If no, remove them from the MCP tools table and list them only under §4 Host Functions.

**D12: No Rhai API documentation in reviewed document set**

tech-choices.md selects Rhai as the mod scripting language (§3). The reference docs cover WASM host functions (5 functions) and MCP tools (67 tools) comprehensively, but the Rhai scripting API — what engine functions mod scripts can call, their signatures, error models, sandbox constraints — is entirely absent from the documents I was allowed to review. If this is documented elsewhere (e.g., specs/gameplay/), it should be cross-referenced from api-registry.md or interface.md. If it's not documented at all, mod developers have no API reference.

**Fix**: Cross-reference the Rhai API documentation from interface.md and api-registry.md. Ensure Rhai host functions have the same level of specification as WASM host functions (signatures, budgets, error codes, output limits).

**D13: MCP tool counts inconsistent across docs**

| Category | api-registry.md header | api-registry actual | mcp-tools.md |
|----------|----------------------|-------------------|-------------|
| Play | (15) | 16 | 16 |
| Arena | (5) | 5 | 4 |

api-registry.md Play header says (15) but lists 16 tools. mcp-tools.md Arena says 4 but api-registry has 5 (including `swarm_get_leaderboard`). These off-by-one errors reduce trust in generated counts.

**Fix**: Run codegen with `--check` and ensure generated counts match actual row counts. Add a CI check that counts column headers against actual tool list lengths.

### Low (nice to fix)

**D14: `swarm_deploy` validation_errors uses `[string]` instead of typed error codes**

The deploy output schema shows `validation_errors: [string]` — free-form strings, not canonical RejectionReason codes. This is inconsistent with the rest of the error system which uses typed, stable codes. SDK users parsing deploy responses need string matching instead of enum switching.

**Fix**: Type `validation_errors` as `[RejectionReason]` or add a structured error type. At minimum, document which RejectionReason codes can appear here.

**D15: No formal backward compatibility strategy documented**

TickTrace envelope tracks many version fields (api_version, core_idl_version, engine_abi_version, host_abi_version, etc. — 22 fields total) but there's no policy document specifying what happens when these versions change. Can old WASM modules run on new engines? Is there a deprecation window? Do MCP tools maintain backward compatibility? This matters for SDK versioning and developer trust.

**Fix**: Add a version compatibility policy section to interface.md or a dedicated specs/core/ document. Specify: deprecation window, breaking change policy, SDK version ↔ engine version compatibility matrix.

**D16: host-functions.md budget error code mismatch**

host-functions.md "Host Call Budget" section says "超出预算 → 返回 -1" but the ABI error priority table (§4.5 in api-registry.md) assigns:
- -1: `ERR_MEMORY_BOUNDS`
- -4: `ERR_BUDGET_EXHAUSTED`
- -5: `ERR_PLAYER_BUDGET`

Returning -1 for budget exhaustion would collide with the memory bounds error. The correct code is -4 or -5 depending on which budget was exceeded. The host-functions.md text is wrong.

**Fix**: Correct host-functions.md to reference the canonical error codes: per-call budget exceeded → -4 (`ERR_BUDGET_EXHAUSTED`), per-player budget exceeded → -5 (`ERR_PLAYER_BUDGET`).

**D17: Snapshots §4 — "InsufficientResources" (plural) used instead of canonical "InsufficientResource" (singular)**

09-snapshot-contract.md §4.2 competitive mode table uses `InsufficientResources` (plural). api-registry.md §2 naming convention explicitly states: "统一使用 InsufficientResource（单数），废弃 InsufficientResources/InsufficientEnergy". This is a stale reference in a non-registry doc.

**Fix**: Replace `InsufficientResources` with `InsufficientResource` in 09-snapshot-contract.md §4.2. Add a grep-based CI check for deprecated error code names across all docs.

---

## Strengths

1. **Fixed-point type system** — Replacing all `f64` with `ResourceRate_i64`, `BasisPoints`, `EfficiencyBps`, `milli_distance`, `micro_cost`, `MilliUnits` is a genuinely excellent design decision. Guarantees cross-platform determinism and eliminates floating-point reproducibility bugs. Well-documented in api-registry.md §0.

2. **RejectionReason system with `debug_detail` + `detail_level`** — 47 canonical wire codes keep the enum stable; `debug_detail` (512 bytes) carries rich context without polluting the wire format; 3-tier `detail_level` (competitive/practice/training) prevents information leakage in competitive mode. One of the best error handling designs I've seen in a game engine spec.

3. **MCP capability profiles** — Grouping 67 tools into onboarding/play/deploy/debug/admin/arena profiles with progressive exposure is excellent DX. AI agents get onboarding first, then unlock more capabilities. The default assignments in api-registry.md §3.4 are sensible.

4. **5-column MCP security model** — Every MCP tool carries `required_scope`, `subject_source`, `replay_class`, `visibility_filter`, `rate_limit_key`. This is a complete, auditable authorization model that maps cleanly to code generation (Rust attribute macros, TypeScript decorators).

5. **TickTrace envelope completeness** — 22 versioned fields (api_version, module_hash, wasmtime_version, snapshot_hash, commands_hash, world_config_hash, mods_lock_hash, engine_abi_version, core_idl_version, world_action_manifest_hash, validator_version, rejection_reason_registry_version, system_manifest_hash, limits_manifest_hash, host_abi_version, canonical_codec_version, visibility_truncation_version, deploy_events, rollback_events, admin_events, terminal_state, effective_tick) provide deterministic replay at every layer. This is thorough.

6. **Snapshot truncation contract** — Deterministic ordering algorithm (distance bucket → entity_id lexicographic → remove from farthest), critical entity protection (own drone, controller, targets, allies, attackers), and competitive degradation tracking. Complete and well-specified.

7. **Safe Hint Ladder** — Three-tier error message model (Safe/FixHint/FullDebug) with explicit per-tier payloads in 09-snapshot-contract.md §4. The `CommandError` struct design with `safe_message` (static string), `fix_hint` (optional static string), and `debug_detail` (optional dynamic payload) is elegant.

8. **Per-tool rate limit granularity** — Rate limit keys span `per_ip`, `per_player`, `per_admin`, `per_device`, `per_session`, `global`, `per_room`, `per_drone`, `per_structure`, `host_only`. This fine-grained control prevents both abuse and noisy-neighbor problems.

9. **Deploy idempotency** — `module_hash` as idempotency key + `fdb_version_counter` for replay ordering. Clean separation of blob storage (async object store) from deterministic metadata (FDB manifest). Well-architected.

10. **Overload anti-lockout proof** — Mathematical proof in 02-command-validation.md §3.17 demonstrates that coordinated Overload attacks cannot permanently lock a target's fuel budget below the 20% floor. This kind of rigor in game balance design is rare and commendable.

---

## CrossCheck — items requiring other direction verification

- **CX1**: Rhai API surface — no Rhai function signatures, type system, or error model in reviewed docs. → Suggest **Architect** verify: what engine functions do Rhai mod scripts call? Are they a subset of WASM host functions or a separate API? Is there a Rhai API reference doc?

- **CX2**: codegen.md staleness (19 vs 21 CommandAction, 79 vs 47 RejectionReason) suggests the CI `--check` gate may not actually run or its failures are being ignored. → Suggest **Security/CI** reviewer verify: does `hermes codegen generate --check` pass against current IDL? If it fails, why was it merged?

- **CX3**: `host_get_objects_in_range` range type discrepancy (`i32` in interface.md/host-functions.md vs `u32` in api-registry.md) — need IDL ground truth. → Suggest **Architect** verify the canonical type in game_api.idl.yaml and align all derived docs.

- **CX4**: The document list I was allowed to read includes `specs/reference/mcp-tools.md` which self-describes as "权威工具清单见 API Registry" but contains its own tool count table that disagrees with the registry (Arena: 4 vs 5). → Suggest **Documentation** reviewer verify that all non-registry docs defer counts to the registry and don't maintain independent tallies.

- **CX5**: `swarm_get_terrain` and `swarm_get_path` marked as both MCP tools and "host fn only" — design intent unclear. → Suggest **Architect** clarify: are these accessible via MCP or only via WASM host imports? If MCP-accessible, they need real rate limits; if not, remove from MCP table.