# Review: Authentication Redesign — apidx (API/Developer Experience)

**Reviewer:** rev-dsv4-apidx (DeepSeek V4 Pro)  
**Direction:** apidx — MCP/API/SDK developer experience, tool tables, payload, error codes, compatibility layer  
**Date:** 2026-06-17  
**Scope:** Clean-slate review of 11 target documents (design/, specs/, GETTING-STARTED.md, RUNBOOK.md)  
**Verdict:** REQUEST_MAJOR_CHANGES

---

## Verdict Rationale

The certificate-based authentication redesign is architecturally sound — the Server CA + CSR + application-layer certificate model with usage isolation is well-conceived. However, from the API developer perspective (the "apidx" lens), the documentation has **critical interop gaps** that would prevent an API consumer (human developer or AI agent) from correctly implementing against the documented interface. Two critical findings block API consumability: a required MCP tool missing from all interface specifications, and the certificate `audience` field defined in three mutually incompatible formats across documents. These must be resolved before implementation proceeds.

---

## Top Findings

| # | Severity | Category | Summary |
|---|----------|----------|---------|
| F1 | **Critical** | API gap | `swarm_deploy_challenge` MCP tool missing from all tool tables |
| F2 | **Critical** | Doc inconsistency | Certificate `audience` field has 3 incompatible formats across documents |
| F3 | **High** | API gap | Non-auth MCP tools lack parameter schemas and return types |
| F4 | **High** | Doc inconsistency | specs/12-gateway-protocol.md references JWT for MCP auth (stale) |
| F5 | **High** | API gap | AI agent MCP onboarding path undocumented in GETTING-STARTED |
| F6 | **High** | API gap | SDK API surface (IDL-generated types) not specified |
| F7 | **Medium** | API gap | Error codes missing for non-auth MCP operations |
| F8 | **Medium** | Doc inconsistency | Rate limiting fragmented with inconsistent measurement units |
| F9 | **Medium** | API gap | Deploy payload vs canonical request signature relationship unclear |
| F10 | **Medium** | Doc inconsistency | MCP tool categorization inconsistent between interface.md and mcp-tools.md |
| F11 | **Low** | Deferred concern | Screeps compatibility layer entirely deferred to community |
| F12 | **Low** | Doc inconsistency | `swarm_validate_module` scope not documented in reference |
| F13 | **Low** | Doc inconsistency | `swarm_get_world_rules` description varies across docs (i18n mention missing in some) |

---

## Strengths

1. **MCP tool classification is well-structured.** The 7-category breakdown (世界查看 / 部署 / 调试 / 学习 / 认证 / 锦标赛 / 资源管理) in `design/interface.md` §4.1 provides clear mental model for API consumers. Each category maps to a distinct developer workflow.

2. **Clean separation of concerns — MCP vs WASM.** The design correctly enforces that MCP is a management/monitoring interface, not a gameplay channel. No `swarm_move`, `swarm_attack`, etc. in MCP. AI agents and humans share the same WASM sandbox path. This is the right architectural choice and is consistently enforced across documents.

3. **Canonical request signature format is well-specified.** `SWARM-REQUEST-V1` in `design/auth.md` §5.6 defines method, path, body_hash, timestamp, nonce, certificate_id, player_id, audience — all the right fields for request integrity in an application-certificate model. The verification order (chain → usage → signature → timestamp/nonce → scope) is correct.

4. **PoW header-parameter binding is correct.** `design/auth.md` §9.3 correctly implements server-authoritative challenge: client only submits `challenge_id + nonce + csr_signature`, never the challenge or difficulty value. This prevents downgrade attacks. Evidence: lines 543-583.

5. **Deferred command model is clean.** `tick(snapshot_ptr, snapshot_len, result_ptr) → i32` with explicit alloc/free protocol is a well-defined ABI. Host functions are read-only and clearly enumerated. Evidence: `specs/core/04-wasm-sandbox.md` §3.1.

6. **Error code table for auth operations is good.** `design/auth.md` §10.6 provides HTTP status codes, retry guidance, and human-readable descriptions. The `invalid_credentials` constant-time behavior (no distinction between "user doesn't exist" and "wrong password") is correctly specified.

7. **Deploy nonce lifecycle is well-documented.** `specs/security/09-command-source.md` §7.3-7.4 covers the full state machine: idle → nonce_issued → compiling → deployed → active, with TTL, IP-binding, and compile-time handling (deploy_token fallback for slow compiles).

---

## Findings — Detailed Evidence

### F1 [Critical] [API gap] `swarm_deploy_challenge` missing from all MCP tool tables

**Evidence:**
- `specs/security/09-command-source.md` §3.3 step 1: "客户端调用 MCP `swarm_deploy_challenge` → 服务端返回 `deploy_nonce`"
- This tool is NOT listed in:
  - `design/interface.md` §4.1 (MCP 工具分类 table)
  - `design/auth.md` §10.1 (MCP 工具一览 table)
  - `specs/reference/mcp-tools.md` (完整工具清单)

**Impact:** An API consumer reading any of the three tool reference tables would not know this tool exists. The deploy flow documented in 09-command-source.md §3.3 is therefore unreachable from the interface documentation. Every deploy operation requires this tool as a prerequisite — its omission from the canonical tool tables means the documented API surface is incomplete.

**Recommendation:** Add `swarm_deploy_challenge` to all three MCP tool tables, with parameter schema (returns `{deploy_nonce, expires_in_seconds, audience}`) and scope requirement (`swarm:deploy`).

---

### F2 [Critical] [Doc inconsistency] Certificate `audience` field has 3 incompatible formats

**Evidence — three different definitions for the same field:**

| Document | Location | Format |
|----------|----------|--------|
| `design/auth.md` | §5.6, line 322 | `world_id@gateway_origin` |
| `specs/security/03-mcp-security.md` | §2.2, line 114 | `server_id + world_id + "cli"` (concatenation) |
| `specs/security/09-command-source.md` | §7.0, lines 191-194 | `mcp:{server_id}:{world_id}:{player_id}` (colon-separated with transport prefix) |

**Impact:** These are three mutually incompatible serialization formats for the same logical field. An API consumer implementing certificate verification would produce a different `audience` string depending on which document they read. This would cause signature verification failures, effectively breaking all authenticated API calls. This is the kind of inconsistency that results in interop bugs discovered only at integration time.

**Recommendation:** Define a single canonical `audience` format in `design/auth.md` and propagate it to all referencing documents. The `specs/security/09` format (`transport:server_id:world_id:player_id`) is the most expressive and should be the canonical form. Update all other occurrences.

---

### F3 [High] [API gap] Non-auth MCP tools lack parameter schemas and return types

**Evidence:**
- `design/auth.md` §10.2-10.5 provides detailed parameter schemas, return types, and example requests for auth tools (`swarm_register_challenge`, `swarm_submit_csr`, `swarm_renew_certificate`).
- `specs/reference/mcp-tools.md` — the canonical tools reference — lists 40+ tools but provides **zero parameter schemas and zero return types** for non-auth tools. Only tool names and one-line descriptions.
- `specs/security/03-mcp-security.md` §4.1 provides a partial example for `swarm_deploy` but no systematic coverage.

**Impact:** An API consumer cannot programmatically call `swarm_get_snapshot`, `swarm_deploy`, `swarm_explain_last_tick`, `swarm_simulate`, or any non-auth tool without guessing the parameter names and types. This forces every SDK author and AI agent developer to reverse-engineer from prose descriptions. The auth tools prove the team can document parameters well — the gap is scope, not capability.

**Recommendation:** Extend `specs/reference/mcp-tools.md` with parameter schemas and return types for all tools, following the same format used for auth tools in `design/auth.md` §10. Alternatively, reference a machine-readable IDL/schema file that SDK codegen can consume.

---

### F4 [High] [Doc inconsistency] Gateway protocol doc references JWT for MCP (stale after cert migration)

**Evidence:**
- `specs/12-gateway-protocol.md` §5, line 119: "JWT 认证（mcp audience）" — describes MCP auth as JWT-based.
- `specs/security/03-mcp-security.md` §3.1, line 185: "JWT/access_token 仅是 Web session 兼容格式…不用于 MCP/Agent 主认证路径" — correctly states MCP uses application certificates.
- `design/auth.md` §14.5: refresh_token and JWT are compatibility layers, not trust roots. Application certificates are the authoritative credential.

**Impact:** The gateway protocol document — which is the integration reference for anyone building against the gateway — explicitly says MCP uses JWT. But the new design moved MCP to application-certificate-based auth. A developer reading specs/12 as their primary reference would implement JWT-based MCP auth, which would be rejected by the gateway. This is a direct contradiction between the protocol spec and the auth design.

**Recommendation:** Update `specs/12-gateway-protocol.md` §5 to describe application certificate + canonical request signature as the MCP auth path, referencing `design/auth.md` §5.6. The transport auth matrix in §9 is mostly correct but §5 prose must be updated.

---

### F5 [High] [API gap] AI agent MCP onboarding path undocumented

**Evidence:**
- `GETTING-STARTED.md` covers only TypeScript SDK + Web UI flow. MCP is mentioned in one line: `swarm_deploy(module_bytes, wasm_signature)` at line 75.
- `design/auth.md` §4.2 provides a narrative flow for AI agent CSR registration, and references onboarding documents at lines 166-170:
  - `docs/auth/onboarding-ai` — does not exist in the review scope
  - `docs/auth/errors` — does not exist in the review scope
  - `schema/auth-tools` — does not exist in the review scope
  - `docs/auth/human-agent-handoff` — does not exist in the review scope
- The MCP tools reference (`specs/reference/mcp-tools.md`) lists tools but provides no end-to-end workflow.

**Impact:** An AI agent developer (or an AI agent itself!) reading the current documentation cannot complete the onboarding flow. The referenced onboarding documents don't exist. The GETTING-STARTED guide has no MCP path. This is a significant barrier to the primary audience that motivated the cert migration (AI player self-registration).

**Recommendation:** Either create the four referenced onboarding documents, or add a dedicated "AI Agent Quickstart" section to `GETTING-STARTED.md` that covers: (1) get server trust fingerprint, (2) generate keypair, (3) PoW + CSR submit, (4) persist certificate chain, (5) deploy WASM via MCP, (6) verify tick execution.

---

### F6 [High] [API gap] SDK API surface not specified in review scope

**Evidence:**
- `design/tech-choices.md` §10 states SDK codegen path: `game_api.idl → codegen → SDK`
- `GETTING-STARTED.md` §3 shows a TypeScript example using `tick((snap: Snapshot): Command[] => {...})` but does not define the `Snapshot` type or `Command` type.
- `specs/reference/commands.md` exists and defines 15+8 Command types — but it's a reference doc, not an SDK spec.
- The `Snapshot` type is never formally specified. `specs/security/03-mcp-security.md` §6.1 shows a snapshot JSON example but it's illustrative, not normative.
- Host functions (`specs/reference/host-functions.md`) exist but the SDK wrapper types are not documented.

**Impact:** The `game_api.idl` file is the single source of truth for the SDK surface, but it's not in the review scope. Without the IDL or a formal SDK API spec, developers cannot determine what types their WASM module will receive or what SDK functions are available. The TypeScript example in GETTING-STARTED.md uses types (`Snapshot`, `Command`) that are never defined.

**Recommendation:** Either include the IDL file in the review scope, or add an SDK API reference document that defines: (1) the `Snapshot` type structure, (2) the `Command`/`CommandIntent` types, (3) SDK-provided types and utilities, (4) host function wrappers.

---

### F7 [Medium] [API gap] Error codes missing for non-auth MCP operations

**Evidence:**
- `design/auth.md` §10.6 defines 10 error codes for auth operations with HTTP status codes and retry guidance.
- No equivalent error code table exists for:
  - World query tools (`swarm_get_snapshot`, `swarm_get_terrain`, `swarm_get_objects_in_range`)
  - Deploy tools (`swarm_deploy`, `swarm_validate_module`, `swarm_rollback`)
  - Debug tools (`swarm_explain_last_tick`, `swarm_inspect_entity`, `swarm_dry_run_commands`)
  - Simulate tools (`swarm_simulate`)
- `specs/security/09-command-source.md` §4 mentions `Rejection` and `RejectionReason` in Rust context but these are not documented for API consumers.
- `specs/core/04-wasm-sandbox.md` §2.4 mentions `Rejection::ModuleTooLarge`, `Rejection::StartSectionForbidden`, `Rejection::MissingExport`, `Rejection::IllegalImport` — but only as Rust enum variants, not as API-visible error codes.

**Impact:** When an API call fails, the consumer receives an undocumented error. They cannot programmatically distinguish "module too large" from "invalid signature" from "rate limited" — making automated recovery impossible. AI agents especially need structured error codes to self-correct.

**Recommendation:** Extend the error code table to cover all MCP tools, following the same format as `design/auth.md` §10.6. Include: error code string, HTTP status, description, retry guidance. At minimum, cover: `module_too_large`, `invalid_wasm`, `missing_export`, `illegal_import`, `deploy_nonce_expired`, `deploy_nonce_consumed`, `rate_limited`, `snapshot_out_of_range`, `simulate_too_many_ticks`, `dry_run_failed`.

---

### F8 [Medium] [Doc inconsistency] Rate limiting fragmented with inconsistent measurement units

**Evidence — three different rate limit tables with different units:**

| Document | Location | Unit | Example |
|----------|----------|------|---------|
| `specs/reference/mcp-tools.md` | "Rate Limiter" table | **tokens/s** | MCP_Deploy: 10 tokens/s |
| `specs/security/03-mcp-security.md` | §5.1 | **per-tick / per-hour** | deploy: 10/小时, get_snapshot: 1/tick |
| `design/auth.md` | §10.7 | **per-minute** | CSR 提交: PoW protected, challenge: 10/min |

**Specific conflicts:**
- Deploy rate: `mcp-tools.md` says "10 tokens/s", `03-mcp-security.md` says "10/小时". These are incompatible (10/s = 36,000/hour).
- Query rate: `mcp-tools.md` has "MCP_Query: 100 tokens/s", `03-mcp-security.md` has per-tool limits totaling ~81/tick. At 3s ticks, that's ~27 tokens/s — incompatible with 100 tokens/s.

**Impact:** An API consumer implementing rate limiting would produce different throttling behavior depending on which document they read. This also means the gateway implementation and the documentation could diverge. Excessively permissive interpretation (10/s deploy) could be exploited; overly restrictive (10/hour deploy) could hinder legitimate use.

**Recommendation:** Consolidate all rate limits into a single authoritative table in `specs/reference/mcp-tools.md` (or a dedicated `specs/security/` doc). Use consistent units. Define whether limits are hard (rejected) or soft (delayed). The 12-source classification in mcp-tools.md is a good structure — extend it with per-tool sub-limits.

---

### F9 [Medium] [API gap] Deploy payload vs canonical request signature relationship unclear

**Evidence:**
- `design/auth.md` §5.6 defines `SWARM-REQUEST-V1` as the canonical request signature format, applied to "each sensitive MCP, deploy, admin request."
- `specs/security/09-command-source.md` §3.2 defines `DeployPayload` with a different structure: `domain: "swarm-deploy"`, `module_hash`, `player_id`, `world_id`, `module_slot`, `version_tag`, `deploy_nonce`, `expires_at`, `signature`.
- The relationship between these two signature payloads is never explained. Does a deploy request carry BOTH signatures? Does the deploy payload replace the canonical request for deploy operations? Are they nested?

**Impact:** An API consumer implementing `swarm_deploy` doesn't know whether to sign a `SWARM-REQUEST-V1` payload, a `DeployPayload`, or both. The header fields (`Swarm-Certificate-Chain`, `Swarm-Signature`, etc.) are defined for `SWARM-REQUEST-V1` — does the deploy signature go in the same header? A different header? The body? This ambiguity would cause implementation errors.

**Recommendation:** Clarify the layering: `SWARM-REQUEST-V1` is the transport-layer signature (what goes in HTTP headers), while `DeployPayload` is the application-layer signed payload (what goes in the request body). Or explicitly state that `DeployPayload` replaces `SWARM-REQUEST-V1` for deploy operations. Either way, document the relationship explicitly in both `design/auth.md` §5.6 and `specs/security/09-command-source.md` §3.2.

---

### F10 [Medium] [Doc inconsistency] MCP tool categorization inconsistent between reference documents

**Evidence:**
- `design/interface.md` §4.1 places `swarm_validate_module` under **部署** category.
- `specs/security/03-mcp-security.md` §4.4 places `swarm_validate_module` under **开发辅助** category with scope `swarm:deploy` and rate limit 10/h.
- `specs/reference/mcp-tools.md` places `swarm_validate_module` under **部署** with no scope annotation.

**Impact:** Minor — the tool exists in all lists and the categorization difference doesn't affect functionality. But it creates confusion about which document is authoritative for tool metadata (category, scope, rate limit). The 03 spec has the richest metadata but is not positioned as the primary tool reference.

**Recommendation:** Make `specs/reference/mcp-tools.md` the single authoritative MCP tool reference. Move all metadata (scope, rate limit, category) there. Have other documents reference it rather than maintaining parallel lists.

---

### F11 [Low] [Deferred concern] Screeps compatibility layer entirely deferred to community

**Evidence:**
- `design/README.md` Appendix A, line 214: "可以通过社区项目构建兼容层，将 Screeps 风格 API 调用包装为 Swarm 指令"

**Impact:** Acceptable for Phase 1 given the fundamentally different API philosophy (OOP vs functional/deferred). However, if community adoption is a goal, providing even a thin reference compatibility mapping would reduce friction for Screeps migrants.

**Recommendation:** Non-blocking. Document as a Phase 2 consideration. At minimum, note which Screeps API concepts have no Swarm equivalent.

---

### F12 [Low] [Doc inconsistency] `swarm_validate_module` scope undocumented in reference

**Evidence:**
- `specs/reference/mcp-tools.md` lists `swarm_validate_module` without scope information.
- `specs/security/03-mcp-security.md` §4.4 correctly specifies scope `swarm:deploy`.

**Recommendation:** Add scope column to `specs/reference/mcp-tools.md` tool tables (resolved by F3).

---

### F13 [Low] [Doc inconsistency] `swarm_get_world_rules` description varies in richness

**Evidence:**
- `specs/security/03-mcp-security.md` §4.4: "获取当前世界的活跃模组及完整配置（含 i18n 描述）" — mentions i18n.
- `specs/reference/mcp-tools.md`: "获取世界规则配置" — generic.
- `design/interface.md` §4.1: "获取世界规则配置" — generic.

**Impact:** Minimal. The i18n mention in the 03 spec is helpful for SDK authors to know that world rules may contain localized strings.

**Recommendation:** Propagate the richer description (with i18n note) to the canonical reference.

---

## Questions / Assumptions

1. **Assumption: `game_api.idl` exists and will be reviewed separately.** The SDK codegen path (`game_api.idl → codegen → SDK`) implies a machine-readable API definition. This review assumes the IDL will be reviewed as part of the SDK deliverable. If the IDL does not yet exist, this is a Phase 1 blocker for SDK development.

2. **Assumption: The four referenced onboarding docs will be created.** `design/auth.md` §4.2 references `docs/auth/onboarding-ai`, `docs/auth/errors`, `schema/auth-tools`, `docs/auth/human-agent-handoff`. This review assumes these are planned deliverables, not omissions.

3. **Question: Is `swarm_deploy_challenge` intended to be a separate MCP tool or a sub-step of `swarm_deploy`?** The spec describes it as a prerequisite MCP call, which implies a separate tool. But if the intent is to fold the nonce into `swarm_deploy`'s flow (server returns nonce, client signs and resubmits), the API design changes significantly. Clarification needed.

4. **Question: What is the error response envelope format?** Auth tools return JSON-RPC responses with error codes, but the transport-level error format (JSON-RPC error object? HTTP problem details? Custom envelope?) is not specified for non-auth tools.

5. **Assumption: The transport auth matrix in `specs/12-gateway-protocol.md` §9 is the authoritative table for the cert-migrated world.** This table correctly shows MCP Agent using `Swarm-Certificate-Chain + Swarm-Signature`. The stale JWT reference in §5 prose is assumed to be an editing artifact, not a design intent.

---

## Summary

The authentication redesign is technically sound. The certificate model with usage isolation, server-authoritative PoW, and canonical request signatures is well-specified for the auth domain. However, the **API consumability** of the documentation has critical gaps: a required tool missing from all interface specifications (F1), a field format inconsistency that would break all authenticated calls (F2), and missing schemas for the majority of MCP tools (F3). Additionally, the gateway protocol spec is stale post-cert-migration (F4), and the AI agent onboarding path — the primary use case for the cert redesign — is undocumented (F5).

These issues are **documentation-level**, not design-level. The underlying design decisions are correct. But documentation IS the API contract — when the contract is inconsistent, the implementation will be wrong. All six High+ findings should be resolved before implementation begins.

---

*Review conducted on 2026-06-17 by rev-dsv4-apidx. 11 documents read, 0 old reviews consulted (clean-slate).*
