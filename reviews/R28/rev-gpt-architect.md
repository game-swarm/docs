# R28 Closure Verification — GPT Architect

Verdict: PARTIALLY_CLOSED

Scope note: per task instruction, this review only checked the five R27-changed documents listed in the task body, not the full 31-file design set.

## Strengths

- B1/B4/A-H2/T-H1 are materially improved: the docs now point scheduling to a manifest authority, mark hard capacity as benchmark-gated, define TickTrace-related terms, and document the Arena/World seed-leakage split.
- Deploy/Auth control-plane schema is closer to a source-of-truth pattern: duplicated Auth tool schemas are explicitly labelled as simplified vs complete, and Deploy replay-critical sequencing is consistently tied to `fdb_version_counter`.

## Concerns

### A1 — A-H1 is not closed: broken links remain

Severity: HIGH

The five-file link check found 20 unresolved relative links. Several are not merely “outside the narrow read set”; their targets are missing or the relative path is malformed from the current file location.

Evidence:
- `/tmp/swarm/docs/specs/core/01-tick-protocol.md:382` links to `specs/core/06-phase2b-system-manifest.md`, which resolves from `specs/core/` to `/tmp/swarm/docs/specs/core/specs/core/06-phase2b-system-manifest.md` and is missing.
- `/tmp/swarm/docs/specs/core/01-tick-protocol.md:390` repeats the same malformed manifest path.
- `/tmp/swarm/docs/specs/core/01-tick-protocol.md:851` repeats the same malformed manifest path.
- `/tmp/swarm/docs/design/engine.md:210`, `/tmp/swarm/docs/design/engine.md:243`, `/tmp/swarm/docs/design/engine.md:256`, and `/tmp/swarm/docs/design/engine.md:267` link to `specs/core/06-phase2b-system-manifest.md` from `design/`, resolving to `/tmp/swarm/docs/design/specs/core/06-phase2b-system-manifest.md` and missing.
- `/tmp/swarm/docs/design/engine.md:419` links to `specs/core/09-snapshot-contract.md` from `design/`; the actual checked existing file is `/tmp/swarm/docs/specs/core/09-snapshot-contract.md`, so the link should not resolve under `design/specs/`.
- `/tmp/swarm/docs/design/README.md:13`, `:14`, `:16`, `:19`, `:208` link to `modes.md`, `interface.md`, `tech-choices.md`, `../RUNBOOK.md`, `../AGENTS.md`; those target files were absent in the checked tree.
- `/tmp/swarm/docs/specs/reference/api-registry.md:3` and `:8` link to `game_api.idl.yaml`, `auth_api.idl.yaml`, `economy.idl.yaml` in `specs/reference/`; those files were absent at the referenced paths.

### A2 — CX3 is not closed: Rhai mod contract is only a boundary note

Severity: HIGH

The current text defines important guardrails, but not a complete mod contract with hooks/helpers/capabilities/errors/version.

Evidence:
- `/tmp/swarm/docs/specs/core/01-tick-protocol.md:872` introduces “RuleMod / 动态 action 边界”.
- `/tmp/swarm/docs/specs/core/01-tick-protocol.md:874` states integer-only, no second state-mutation path, and that extended actions must enter World Action Manifest + IDL schema.
- `/tmp/swarm/docs/specs/reference/api-registry.md:39` says World Action Manifest extends `custom_actions`.
- `/tmp/swarm/docs/specs/reference/api-registry.md:607` records `world_action_manifest_hash` in TickTrace.

Gap: there is no visible contract section defining Rhai hooks, helper API surface, capability declarations, mod-specific error mapping, or version/compatibility rules. As written, implementers can enforce the “single command-validation path” rule but cannot independently implement a Rhai mod ABI.

### A3 — B5 mostly closed, but one section reference is stale

Severity: MEDIUM

Auth/Deploy control-plane schema is substantially aligned, but `api-registry.md` contains a stale intra-document pointer.

Evidence:
- `/tmp/swarm/docs/specs/reference/api-registry.md:250` and `:251` list simplified game_api Auth tool schemas.
- `/tmp/swarm/docs/specs/reference/api-registry.md:253` says complete schema is in “§3.4 Auth API 工具”, but the actual Auth API heading is at `/tmp/swarm/docs/specs/reference/api-registry.md:337`; §3.4 starts Capability Profiles at `/tmp/swarm/docs/specs/reference/api-registry.md:366`.
- `/tmp/swarm/docs/specs/reference/api-registry.md:339` clarifies game_api is simplified and auth_api is complete, with SDK de-duplication.
- `/tmp/swarm/docs/specs/reference/api-registry.md:349` and `:350` define richer Auth login/refresh schemas.
- `/tmp/swarm/docs/specs/reference/api-registry.md:280`, `:288`, `:774`, `:781`, `:782`, `:790`, and `:800` consistently document Deploy manifest + `fdb_version_counter` behavior.

This is not a structural blocker for B5, but it is a documentation navigation defect that will mislead implementers.

## Item Verification

| Item | Result | Evidence |
|------|--------|----------|
| B1: §2.3 scheduling chain removed / points to manifest | PASS | `01-tick-protocol.md:382` points ECS scheduling to Complete Tick Execution Manifest instead of owning an old independent chain; `01-tick-protocol.md:851` states the system order’s only authority is the manifest; `02-command-validation.md:435-437` and `:508-510` avoid duplicating special-attack/status scheduling and defer to manifest authority. Caveat: the link path itself is broken; counted under A-H1. |
| B4: capacity claims marked benchmark-gated | PASS | `api-registry.md:534-535` marks hard cap players as benchmark-gated and says actual hard cap is pressure-test determined; `engine.md:300-315` keeps performance/capacity as a contract table while `engine.md:396` points authoritative capacity definitions back to API Registry; `engine.md:356-358` gates 1000-worker hard-cap operation on operator enablement and capacity proof. |
| B5: Deploy/Auth control-plane schema consistency | PASS_WITH_MINOR_CONCERN | Auth split is explicit at `api-registry.md:339-343`; complete Auth schemas are listed at `api-registry.md:349-364`; Deploy tool and replay class are aligned at `api-registry.md:280`, `:288`, `:774-782`, `:790-800`; tick protocol deploy timing agrees at `01-tick-protocol.md:778-787`. Minor concern: stale “§3.4 Auth API 工具” pointer at `api-registry.md:253`. |
| A-H1: broken links fixed | FAIL | Five-file link check found 20 unresolved relative links; key broken examples are `01-tick-protocol.md:382`, `:390`, `:851`; `design/engine.md:210`, `:243`, `:256`, `:267`, `:419`; `api-registry.md:3`, `:8`; plus absent design README targets at `design/README.md:13`, `:14`, `:16`, `:19`, `:208`. |
| A-H2: TickTrace glossary distinguishes 4 concepts | PASS | `design/README.md:235-250` defines `TickCommitRecord`, `RichTraceBlob`, `ReplayArtifact`, and broader `TickTrace` usage; it also distinguishes nearby `RawCommand`, `CommandIntent`, `ValidatedCommand`, `DeployPayload`, and `fdb_version_counter`. |
| T-H1: Arena commit-reveal + World operator bump recorded | PASS | `01-tick-protocol.md:260-264` states the hybrid approach; `:266-285` details Arena commit-reveal and post-match reveal; `:287-295` starts World Operator Seed-Bump + statistical detection. |
| CX3: Rhai mod contract complete | FAIL | Only boundary rules are present at `01-tick-protocol.md:872-874`, with related manifest hash references at `api-registry.md:39` and `:607`. Hooks/helpers/capabilities/errors/version are not specified as a complete implementable contract. |

## Missing

- A concrete Rhai RuleMod ABI/contract section covering:
  - Hook names and call timing.
  - Helper functions exposed to Rhai.
  - Capability declaration format and enforcement point.
  - Error namespace / mapping to canonical RejectionReason or mod-specific typed errors.
  - Versioning and compatibility rules, including manifest hash behavior.
- A link hygiene pass over the five changed files, especially relative paths from `specs/core/` and `design/`.
- Correction of the stale Auth section pointer in `api-registry.md:253`.

## Phase Ordering

1. Fix A-H1 first: broken links undermine every “single authority” pointer and make B1 fragile in practice.
2. Fix CX3 next: without a complete Rhai mod ABI, implementation teams will invent incompatible hook/helper/capability/error/version conventions.
3. Patch B5’s stale Auth pointer as part of the same docs hygiene pass; it is low risk and prevents SDK/control-plane confusion.
4. Re-run a narrow closure verification only for A-H1, CX3, and the B5 pointer; B1/B4/A-H2/T-H1 do not need broad re-review unless those patches touch their substance.
