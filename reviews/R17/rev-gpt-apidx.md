# R17 API/开发者体验评审 (GPT-5.5)

Reviewer: API/DX
Scope: Clean-slate review of the allowed R17 document subset only. Machine source of truth treated as `specs/reference/game_api.idl.yaml` where conflicts exist.

## Verdict: REQUEST_MAJOR_CHANGES

R17 has the right architectural direction: it explicitly introduces `game_api.idl.yaml` as the machine-readable source of truth, pushes CommandAction/RejectionReason/MCP tools/Host Functions/limits into a registry, and improves the developer-facing story around deferred commands, MCP capability profiles, SDK fetch, snapshot truncation, and simulation isolation.

However, the claimed “authoritative single source closure” is not actually closed. The YAML IDL, API Registry, MCP reference, command reference, host-function reference, design/interface, and snapshot contract still contain multiple incompatible API surfaces. From an SDK/API consumer perspective, a new developer or AI agent cannot reliably know which tool names exist, which command variants are core vs custom, which RejectionReason values can appear, what Host ABI to import, or which error envelope shape to parse. This is not an implementation-detail problem; it is a contract-level inconsistency that must be resolved before implementation.

## 发现问题

### X1 — Critical — IDL 与 API Registry 自身不一致，破坏“机器事实源”闭环

Evidence:
- `game_api.idl.yaml` declares `api_version: "0.2.0"`.
- `api-registry.md` declares current API version as `0.1.0`.
- `game_api.idl.yaml` declares `mcp_tools.total_tools: 46`, but the actual `mcp_tools.tools` list contains 45 entries.
- `api-registry.md` repeats “工具清单 (46)” and lists the same apparent 45 concrete rows.

Impact:
- Codegen, SDK version negotiation, MCP schema discovery, and CI consistency checks cannot agree on the API version or tool count.
- If Markdown is truly generated from YAML, the generated artifact is already stale; if it is hand-maintained, the “do not edit Markdown tables directly” rule is not enforceable yet.

Required fix:
- Make `api_version` match between YAML and registry.
- Either add the missing 46th MCP tool to YAML and generated docs, or change all counts to 45.
- Add a generated-manifest checksum or CI assertion that fails when declared totals differ from actual list lengths.

### X2 — Critical — MCP tool surface has three incompatible namesets

Evidence:
- `game_api.idl.yaml` / `api-registry.md` define tools such as `swarm_get_info`, `swarm_get_resources`, `swarm_list_rooms`, `swarm_get_room`, `swarm_get_code`, `swarm_get_deploy_status`, `swarm_get_tick_trace`, `swarm_dry_run`, `swarm_admin_challenge`, `swarm_admin_set_world_config`, `resources/list`, `resources/read`.
- `design/interface.md` instead lists older tools such as `swarm_get_objects_in_range`, `swarm_rollback`, `swarm_list_modules`, `swarm_explain_last_tick`, `swarm_inspect_entity`, `swarm_inspect_room`, `swarm_profile`, `swarm_dry_run_commands`, `swarm_get_docs`, `swarm_get_schema`, `swarm_get_available_actions`, `swarm_get_server_trust`, `swarm_register_challenge`, `swarm_submit_csr`, many auth tools, and tournament tools.
- `specs/reference/mcp-tools.md` repeats the old design/interface tool set and includes numerous tools absent from the IDL, while omitting many IDL-defined tools.

Impact:
- A new MCP client cannot know whether to call `swarm_dry_run` or `swarm_dry_run_commands`, `swarm_get_tick_trace` or `swarm_explain_last_tick`, `swarm_list_deployments` or `swarm_list_modules`, `swarm_get_path` or `swarm_get_objects_in_range`.
- The onboarding profile in design/interface includes `swarm_get_server_trust`, `swarm_register_challenge`, `swarm_submit_csr`, `swarm_get_docs`, and `swarm_get_schema`, but these are not in the current IDL tool list. This breaks the “5-minute first AI agent connection” story.
- The MCP reference claims “逐工具详细说明” but is not actually a detail view of the IDL registry.

Required fix:
- Treat `game_api.idl.yaml:mcp_tools.tools[*].name` as the only allowed tool-name set.
- Regenerate or rewrite `design/interface.md §4.1`, `§4.1a`, and `specs/reference/mcp-tools.md` from the IDL names.
- If auth/onboarding/tournament tools are intentionally kept, they must be added to the IDL with schemas, scopes, replay class, visibility, and rate limits; otherwise remove them from all references.

### X3 — Critical — CommandAction model is internally contradictory: 19 core variants vs “15 + Custom + 8 special attacks”

Evidence:
- `game_api.idl.yaml` and `api-registry.md` define 19 CommandAction variants: 11 core + 2 Global Storage + 6 Special Attack. `Leech` and `Fabricate` are custom actions only.
- `commands.md` says “19 指令” but immediately states “以下 15 种指令对应 CommandAction enum 的 15 个具体变体。第 16 个变体 CommandAction::Custom(type) 通过 CustomActionRegistry 路由到 8 种特殊攻击”.
- `commands.md` examples include `Leech` and `Fabricate` as action `type` values alongside the 19 list, producing 21 example action types.
- `commands.md` later labels special attacks “via `CommandAction::Custom`”, contradicting the IDL where `Hack/Drain/Overload/Debilitate/Disrupt/Fortify` are core enum variants.
- `specs/core/02-command-validation.md` also contains a stale “CommandAction 变体” section using flat examples such as `{ "action": "RangedAttack", ... }`, inconsistent with the CommandIntent `{sequence, action: {type, ...}}` envelope.

Impact:
- SDK codegen cannot decide whether `Hack` is a typed union member or a custom action string.
- Validators cannot decide whether `Leech`/`Fabricate` should be accepted by default or only when a World Action Manifest registers them.
- Player examples will teach the wrong shape and cause schema rejections.

Required fix:
- Normalize all docs to the IDL model: 19 core variants, 6 special attacks are core, `Leech` and `Fabricate` are manifest custom actions, not default core enum variants.
- Remove stale “15 + Custom + 8” language.
- Ensure every JSON example uses `{ "sequence": N, "action": { "type": "...", ... } }` and uses IDL parameter names.

### X4 — Critical — RejectionReason registry is not closed; references list many undeclared error codes

Evidence:
- `game_api.idl.yaml` declares `rejection_reason.total_variants: 35`, with 37 entries including two pipeline-level entries and 35 indexed variants.
- `api-registry.md` says pipeline `InvalidJson` and `SchemaViolation` are “不计入 enum”.
- `commands.md` rejection table lists many names absent from the IDL registry, including `NotMovable`, `Fatigued`, `MissingBodyPart`, `TileBlocked`, `StillSpawning`, `OutOfRoom`, `NoPath`, `PathTooLong`, `InsufficientMoveParts`, `CarryFull`, `NotSource`, `SourceEmpty`, `TargetFull`, `TargetEmpty`, `NotYourRoom`, `TileOccupied`, `InvalidTerrain`, `TooManyConstructionSites`, `AlreadyFullHealth`, `FriendlyTarget`, `NotYourSpawn`, `BodyTooLarge`, `ExceedsRoomCapacity`, `NotFriendly`, `AlreadyHacked`, `InvalidDamageType`, `AlreadyDebilitated`.
- `specs/core/02-command-validation.md` uses the same undeclared rejection codes and adds `MainActionQuotaExceeded`.
- `specs/core/09-snapshot-contract.md` uses `InsufficientResources` plural and `PermissionDenied`, while the registry says the canonical forms are `InsufficientResource` and `NotAuthorized`/`NotOwner` depending on layer.

Impact:
- Error handling in SDKs cannot be exhaustive.
- MCP JSON-RPC clients cannot distinguish stable enum cases from prose-only examples.
- The safe hint ladder cannot map cleanly to canonical error categories.

Required fix:
- Either add all operational rejection reasons to `game_api.idl.yaml` with stable layer/index/category semantics, or rewrite validation/reference tables to use only the 35 canonical codes.
- Keep pipeline errors, validation errors, MCP errors, and runtime errors clearly separated in generated SDK types.
- Add a CI grep/schema check: every backticked rejection-like token in reference docs must exist in IDL or be explicitly marked as non-wire prose.

### X5 — High — Host Function ABI remains inconsistent across three places

Evidence:
- IDL / Registry define:
  - `host_get_terrain(room_id: u32, out_ptr: i32, out_len: i32) -> i32`
  - `host_path_find(from_x, from_y, to_x, to_y, opts_ptr, opts_len, out_ptr, out_len) -> i32`
  - `host_get_world_rules(rule_id_ptr, rule_id_len, out_ptr, out_len) -> i32`
- `design/interface.md §5.1` shows conceptual signatures with `host_get_terrain(x, y)`, `host_get_world_rules(out_ptr, out_len)`, and no path options pointer.
- `host-functions.md` presents those conceptual signatures as “详细签名”, not as non-authoritative examples.
- `host-functions.md` says “超出预算 → 返回 -1”, while the registry ABI error priority reserves `-1` for memory bounds and `-4/-5/-6` for budget exhaustion.

Impact:
- WASM SDK authors will import the wrong functions and fail at module validation or runtime.
- Error-code handling around ABI errors will be wrong, especially if `-1` ambiguously means memory violation or budget exhaustion.

Required fix:
- Make `host-functions.md` a generated/detail rendering of `game_api.idl.yaml:host_functions`.
- Mark any simplified signatures in design/interface as non-ABI pseudocode or remove them.
- Use the registry ABI error priority everywhere.

### X6 — High — JSON-RPC error envelope has incompatible `error.code` typing and payload shape

Evidence:
- `design/interface.md §5.6` shows JSON-RPC `error.code: -32000` and `data.swarm_error: "InsufficientResources"`, plus `retry_allowed` and `idempotency_key`.
- `api-registry.md §8` and `game_api.idl.yaml:swarm_error_envelope` define `error.code` as a `RejectionReason` string and reserve `-32000` only for unclassified internal errors.
- The design example uses non-canonical plural `InsufficientResources` while registry requires singular `InsufficientResource`.

Impact:
- MCP clients cannot implement one parser.
- Retry/idempotency semantics are not represented in the IDL envelope that should drive SDK generation.

Required fix:
- Decide one wire envelope. Preferred DX shape: keep JSON-RPC numeric `error.code` for protocol class and put canonical `swarm_error.code` as a string in `error.data`; or commit to registry’s string `error.code` and remove numeric examples. Do not mix both.
- If `retry_allowed` and `idempotency_key` are part of the public contract, add them to `game_api.idl.yaml`.

### X7 — High — Snapshot and simulate contracts do not match MCP/IDL tool schemas

Evidence:
- IDL `swarm_get_snapshot` output is `{tick, entities, terrain, resources, truncated, omitted_count}`.
- `specs/core/09-snapshot-contract.md` requires truncated snapshots to contain `drone_id` and `omitted_categories: {entities, resources, events}`.
- IDL `swarm_simulate` input is `{commands, assumptions}` and output is `{trace, authoritative: false, assumptions, confidence}`.
- Snapshot contract describes `swarm_simulate(world_state, drone_id, action)` and output fields `{authoritative:false, not_predictive:true, result, rng_ordinals_consumed:0, fuel_consumed:0, tick_trace_written:false}`.
- IDL also defines `swarm_dry_run` as `{wasm_bytes, tick_count}` → `{trace, fuel_used, errors}`, whereas snapshot contract defines dry-run as deterministic variant with `not_predictive` and `deterministic` markings.

Impact:
- SDK-generated types for snapshot/simulate will not support the safety markers promised by the design.
- AI agents may mistake a preview for authoritative output because the IDL does not carry `not_predictive` / isolation evidence.
- Snapshot truncation handling cannot be stable if one schema exposes only `omitted_count` and another requires category counts.

Required fix:
- Promote snapshot truncation fields and simulate/dry-run isolation markers into `game_api.idl.yaml`.
- Choose one `swarm_simulate` input model: command-list forecast, single-action preview, or both as separate tools.
- Ensure IDL output schemas include the product-safety fields promised by the snapshot contract.

### X8 — Medium — Capability profiles and categories are confusing and partly non-existent

Evidence:
- IDL capability profile `play` includes categories `[Play, Economy]`, but the tool entries categorize economy tools as `Play`; there is no `Economy` category in the actual list.
- `design/interface.md §4.1a` defines profiles using explicit tool names and includes tools absent from IDL.
- `api-registry.md §3.2` defines profiles by category, while mcp-tools.md is organized by a different taxonomy (`世界查看`, `学习`, `认证`, `锦标赛`, etc.).

Impact:
- MCP clients using `swarm_get_schema(profile=...)` cannot predict the returned set.
- Documentation uses “profile”, “category”, and “scope” inconsistently, which harms onboarding and least-privilege reasoning.

Required fix:
- Define profile membership once in IDL, either as explicit tool-name arrays or generated category expansions.
- Ensure every referenced category actually exists.
- Regenerate all profile tables from the IDL.

### X9 — Medium — SDK onboarding path is still not a 5-minute happy path

Evidence:
- `design/interface.md` positions `swarm_sdk_fetch`, `swarm_get_schema`, `swarm_get_docs`, `swarm_get_player_status`, and CSR tools as onboarding-critical.
- The IDL includes `swarm_sdk_fetch`, but not `swarm_get_schema`, `swarm_get_docs`, `swarm_get_player_status`, `swarm_get_server_trust`, `swarm_register_challenge`, or `swarm_submit_csr`.
- `mcp-tools.md` documents the auth tools, but they are absent from the IDL registry.

Impact:
- A first-time AI agent cannot bootstrap trust, schema, docs, account certificate, SDK, and deploy flow from the machine-readable tool catalog alone.
- “MCP with full input/output/error schema” is asserted, but the onboarding tools that need the clearest schemas are not in the source of truth.

Required fix:
- Add an explicit Onboarding Happy Path section generated from IDL, with 5 calls or fewer and concrete request/response examples.
- Include all onboarding tools in IDL or remove claims that they are available in current R17.

### X10 — Low — Developer docs retain stale/version-history language in a reference surface

Evidence:
- `api-registry.md` contains a `变更记录` with date and R15 repair notes.
- Snapshot contract header says `R15 H3/H4/DH1/DH2`.
- Some reference text mentions Future/Tier markers inline (`Leech ⏳ Tier 2`, `Fabricate ⏳ Tier 2`) while also presenting examples as if callable.

Impact:
- This is less severe than schema conflicts, but it weakens “current target-state API reference” clarity.
- Users may interpret future/custom examples as current core support.

Required fix:
- Move historical review notes to changelog/review artifacts, not reference pages.
- For future/custom capabilities, use explicit availability fields from IDL (`core`, `custom_manifest`, `future_rfc`) and avoid mixing them with default call examples.

## 亮点

1. Good direction toward IDL-first API governance. `game_api.idl.yaml` is the right primitive for SDK generation, MCP schema generation, CI checks, and docs derivation.
2. The command model is conceptually sound: WASM emits deferred `CommandIntent[]`, server injects identity/source/tick, then a single validation/apply pipeline processes actions. This is much easier to secure and explain than mutating host calls.
3. MCP “no direct game actions” is a strong DX/security boundary. It keeps AI and human players on the same deploy-WASM path and avoids privileged AI-only gameplay APIs.
4. The registry columns for MCP tools are useful: scope, subject source, replay class, visibility filter, and rate-limit key are exactly the right fields for client SDKs and security review.
5. Host functions are appropriately narrow and read-only. The intended ABI budget/output/fuel tables are good SDK-generation inputs once made consistent.
6. Snapshot truncation and simulate isolation address real AI-agent pitfalls: silent truncation, preview-vs-authoritative confusion, RNG side effects, and TickTrace pollution.
7. The safe hint ladder is a good product/API idea: competitive mode should expose constant safe errors, while training mode can expose full debug detail.

## Missing

1. A generated artifact contract: docs should state which Markdown files are generated from `game_api.idl.yaml`, which are explanatory, and which CI command validates drift.
2. A machine-readable per-tool error schema. The docs assert MCP tools have input/output/error schemas, but the IDL only has input/output plus global rejection/error concepts; per-tool error sets and retry/idempotency semantics are not yet explicit.
3. A canonical SDK surface example. There is no single “hello world AI agent” flow that fetches SDK, gets schema/docs, validates a module, deploys, reads snapshot, and handles one rejection.
4. Stable type definitions for common referenced types (`PlayerId`, `Entity`, `TerrainGrid`, `Assumptions`, `TickTrace`, `Metadata`, etc.). Current schemas are field sketches, not enough for SDK codegen.
5. Alias/deprecation policy. Given old names like `swarm_dry_run_commands` vs new `swarm_dry_run`, the docs need either “no aliases” or a formal alias table with sunset behavior.
6. A canonical naming convention for MCP tools. Current surface mixes `swarm_get_*`, `swarm_list_*`, `swarm_admin_*`, and MCP resource-style `resources/list`; that may be OK, but the rule should be documented.
7. A clear split between command validation RejectionReason and MCP/tool errors. Right now command rejection, runtime failure, auth failure, and JSON-RPC transport error are mixed.

## API Consistency Issues

- `api_version`: IDL says `0.2.0`; registry says `0.1.0`.
- MCP tool count: IDL declares 46 but lists 45.
- MCP names: IDL/registry current names differ substantially from design/interface and mcp-tools reference.
- CommandAction count/model: IDL says 19 core variants with 6 special attacks; commands.md says 15 concrete + Custom + 8 special attacks and includes 21 example action types.
- RejectionReason names: registry canonical set is not used by commands.md, command-validation, or snapshot-contract.
- Error envelope: design/interface uses JSON-RPC numeric `-32000` + `data.swarm_error`; registry/IDL use string `error.code` with `-32000` reserved.
- Host ABI: IDL signatures differ from host-functions.md detailed signatures and design/interface conceptual signatures.
- Budget errors: registry maps budget exhaustion to `-4/-5/-6`; host-functions.md says budget exceeded returns `-1`.
- Snapshot schema: IDL has `omitted_count`; snapshot contract requires `omitted_categories` and `drone_id`.
- Simulate/dry-run schemas: IDL schemas omit `not_predictive`, `deterministic`, and isolation evidence promised by snapshot contract.
- Capability profiles: IDL references an `Economy` category that the actual tool entries do not use.
- Derived docs claim authority but still define conflicting tables/lists instead of strictly linking to or rendering the IDL.

## CrossCheck

- Checked `game_api.idl.yaml` against `api-registry.md`: not closed (`api_version`, MCP tool count).
- Checked IDL MCP tool list against `design/interface.md` and `mcp-tools.md`: not closed (large nameset drift; onboarding/auth/tournament/debug tools conflict).
- Checked IDL CommandAction model against `commands.md` and `02-command-validation.md`: not closed (19 core vs 15+Custom+8; stale flat JSON examples).
- Checked IDL RejectionReason set against `commands.md`, `02-command-validation.md`, and `09-snapshot-contract.md`: not closed (many undeclared rejection codes and plural/canonical naming drift).
- Checked IDL Host Function ABI against `host-functions.md` and `design/interface.md`: not closed (signature and error-code drift).
- Checked IDL snapshot/simulate tool schemas against `09-snapshot-contract.md`: not closed (truncation and isolation fields mismatch).

Conclusion: R17 is directionally much closer than earlier rounds, but Phase 1 should not proceed as “API contracts approved” until the IDL-derived closure is made mechanically true across the allowed reference/design/spec subset.
