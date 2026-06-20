# R28 GPT API/DX Closure Verification

Reviewer: GPT API/DX
Scope: only R27 API documentation fixes in:
- `/tmp/swarm/docs/specs/reference/api-registry.md`
- `/tmp/swarm/docs/specs/reference/codegen.md`
- `/tmp/swarm/docs/specs/core/02-command-validation.md`

## Verdict

PARTIALLY_CLOSED

B2, ML-1, and ML-2 are closed for the requested evidence. D-H2, ML-8, and ML-9 remain partially or fully open because the docs either omit the requested schema-level closure or preserve stale/generated-count drift.

## Verification Results

### B2 — PASS

Requested: CmdAction 19→21 / RejReason 79→47 / shared `object_id` field / hand-maintained warning.

Evidence:
- PASS: `api-registry.md:41` states all 21 `CommandAction` variants share `object_id: EntityId`, and the field is not repeated in each action parameter column.
- PASS: `api-registry.md:44` declares `CommandAction` variant count as 21.
- PASS: `api-registry.md:48-82` lists actions 1–21, including `Leech` and `Fabricate` at rows 20–21.
- PASS: `api-registry.md:90` declares 47 canonical `RejectionReason` codes.
- PASS: `api-registry.md:119-178` decomposes the 47 as 26 validation + 3 MCP + 6 runtime + 12 auth canonical codes.
- PASS: `codegen.md:24` warns that `codegen.md` itself is hand-maintained and must be manually updated when IDL changes.
- PASS: `codegen.md:26-29` mirrors CommandAction 21, RejectionReason 47, Host function 5.

Notes:
- Minor residual drift exists in `codegen.md:27`, which still says MCP tool count is `56 active`; this belongs more directly to D-H2 than B2.

### D-H2 — FAIL

Requested: `swarm_get_objectives` (#57 tool / `ObjectiveType` 8 enum variants).

Evidence:
- PASS: `api-registry.md:211-213` declares 57 active game_api tools and 11 auth_api tools.
- PASS: `api-registry.md:228` labels the Game API tool list as 57.
- PASS: `api-registry.md:244` includes `swarm_get_objectives` in the Onboarding section with input/output schema and source IDL.
- FAIL: `codegen.md:27` still says MCP tool count is `56 active`, contradicting `api-registry.md`.
- FAIL: within the required files, no `ObjectiveType` enum definition or 8-variant list is present. `api-registry.md:244` exposes only a generic `type` field inside the objectives output; it does not document allowed enum variants.

Impact:
- API/DX remains ambiguous for SDK generation: users and generated clients can discover that `objectives[].type` exists, but not the closed set of valid `ObjectiveType` values.

### ML-1 — PASS

Requested: WASM tick output unified at 256KB, not 1MB.

Evidence:
- PASS: `02-command-validation.md:12` states tick output schema validation has a maximum of 256KB.
- PASS: `02-command-validation.md:52` states total tick output bytes must be ≤ 256 KB.
- PASS: `02-command-validation.md:617` repeats that the whole tick output batch is ≤ 256KB.
- PASS: `api-registry.md:549` states per-player snapshot is 256 KB.
- PASS: cross-file scan found remaining `1 MB` mentions only for MCP simulate/dry-run output (`01-tick-protocol.md:730`, `04-wasm-sandbox.md:316`), WASM stack (`04-wasm-sandbox.md:86`), or sandbox disk I/O (`04-wasm-sandbox.md:388`), not WASM tick output.

### ML-2 — PASS

Requested: canonical serialization → `Blake3(canonical_json(command))`.

Evidence:
- PASS: `02-command-validation.md:99` defines global ordering tiebreaker `command_hash = Blake3(canonical_json(command))`.
- PASS: `02-command-validation.md:99` also references `canonical_json()` semantics from `specs/reference/canonical-codec.md`: key ordering, no whitespace, no trailing zeroes, and NFC string normalization.
- PASS: `02-command-validation.md:99` clarifies the hash uses `RawCommand` rather than raw `CommandIntent`, so injected server fields participate in ordering.

### ML-8 — FAIL

Requested: MCP tool required/optional/default/errors annotations.

Evidence:
- FAIL: `api-registry.md:395` says every tool parameter and return field must include `required`/`optional`/`default` and each tool must include `errors`, but it also states current YAML only partially contains these annotations and still needs completion.
- FAIL: the visible MCP tool tables (`api-registry.md:232-244`, `api-registry.md:278-301`, `api-registry.md:347-364`) still expose compact inline schemas without per-field required/optional/default/default-value/error annotations.
- FAIL: keyword scan of `specs/reference` found no schema-level `required:`, `optional:`, `default:`, or `errors:` entries corresponding to MCP tools in the required docs.

Impact:
- SDK/MCP clients still cannot reliably derive precise input validation, defaults, or canonical error surfaces from the registry alone.

### ML-9 — FAIL

Requested: Auth API `alias_of` / `schema_source` preventing duplicate generation.

Evidence:
- PARTIAL: `api-registry.md:339` explains that simplified game_api auth tools point to richer auth_api schemas and says SDKs should not generate duplicate functions.
- PARTIAL: `api-registry.md:250-253` documents simplified `swarm_auth_login` and `swarm_auth_refresh` in game_api and points to the full auth_api schema.
- PARTIAL: `api-registry.md:349-352` documents the full auth_api lifecycle schemas, including `swarm_auth_check`.
- FAIL: the required docs do not expose actual machine-readable `alias_of` or `schema_source` fields for auth aliases. `api-registry.md:339` mentions `schema_source=auth_api` in prose, but the tool tables do not contain `alias_of` or `schema_source` columns/fields.
- FAIL: `swarm_auth_check` is claimed at `api-registry.md:339` to have both simplified game_api and full auth_api versions, but no simplified `swarm_auth_check` row appears in the game_api auth subsection at `api-registry.md:246-253`; only login and refresh are listed there.

Impact:
- The duplicate-generation rule is documented as prose but not enforceable by codegen. SDK generators still lack a clear machine-readable alias contract.

## New Documentation Conflicts

### High — MCP tool count drift

- `api-registry.md:211-213` and `api-registry.md:228` say game_api has 57 active tools.
- `codegen.md:27` says MCP tool count is 56 active.

This directly contradicts D-H2 and may cause CI/generator expectations to diverge.

### High — Auth alias prose vs table shape

- `api-registry.md:339` says `swarm_auth_check` exists in both simplified game_api and full auth_api forms.
- `api-registry.md:246-253` only lists `swarm_auth_login` and `swarm_auth_refresh` under game_api Auth.

This makes the alias relationship unclear and undermines ML-9 duplicate-generation prevention.

### Medium — ML-8 states desired annotation contract but not closure

- `api-registry.md:395` defines the desired annotation contract, but explicitly says the YAML remains partially annotated and must be completed.

This is less a contradiction than an explicit open TODO, but it means the closure item is not actually closed.

## API Consistency Issues

- `codegen.md` must be updated from `56 active` to `57 active`, or preferably generated/validated against the same source as `api-registry.md` to avoid future drift.
- `ObjectiveType` should be registered as a named enum with its 8 variants near `swarm_get_objectives`, not hidden as an untyped `type` field in an inline object.
- MCP tool tables need either expanded per-field schema blocks or links to generated schema entries carrying `required`/`optional`/`default`/`errors` metadata.
- Auth duplicate-prevention should be machine-readable: add `alias_of` and `schema_source` columns/fields to the relevant generated registry rows, and resolve whether `swarm_auth_check` has a game_api simplified alias or only auth_api ownership.
