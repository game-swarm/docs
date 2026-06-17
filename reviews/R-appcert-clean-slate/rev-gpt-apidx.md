# R-appcert-clean-slate — apidx review

Reviewer: rev-gpt-apidx  
Focus: MCP/API/SDK developer experience, tool tables, payloads, error codes, compatibility layer

## Verdict

CONDITIONAL_APPROVE

The clean-slate authentication direction is architecturally sound for an AI-native, self-hostable game platform: application-layer certificates, CSR-based onboarding, purpose-separated certificates, canonical request signatures, transport audience binding, and local federation re-signing form a coherent trust model. I do not see a conceptual blocker in the Server CA + CSR + app-cert model itself.

However, the API-facing documents are not yet implementation-ready. The main risk is not cryptography; it is that several public-facing API/spec surfaces still describe different protocols for the same action. If implemented as written, SDK authors and MCP clients will build against inconsistent tool inventories, deploy payloads, auth headers, and error semantics.

## Top findings

### A1 — High — Gateway MCP section still names JWT as the MCP auth mechanism

Category: doc inconsistency / security gap / API gap

Evidence:
- `specs/12-gateway-protocol.md:119` says Gateway MCP responsibilities include `JWT 认证（mcp audience）`.
- `specs/12-gateway-protocol.md:163` later says MCP Agent uses `Application certificate + signed request` with `Swarm-Certificate-Chain` + `Swarm-Signature` + `X-Swarm-Transport: mcp`.
- `design/auth.md:30` says JWT/refresh token is only a Web session compatibility layer, not a trust root.
- `specs/security/03-mcp-security.md:157` and `specs/security/03-mcp-security.md:185` also state the authoritative MCP/Agent path is application certificate chain + user private-key signature, while JWT/access_token is not the MCP/Agent primary auth path.

Why this matters:
- This is the classic “old auth path survived in a proxy spec” failure mode. Gateway implementers will naturally treat `specs/12-gateway-protocol.md` as the transport authority and may ship JWT acceptance on the Agent endpoint.
- Once JWT is accepted by MCP Agent endpoints, the architecture loses the clean separation between browser compatibility tokens and agent certificates. It also makes audience-binding and canonical request signature requirements ambiguous.

Expected resolution before implementation:
- Make `specs/12-gateway-protocol.md §5` align with the auth matrix in §9: MCP Agent must verify application certificate chain, transport audience, nonce/timestamp, canonical body hash, and `Swarm-Signature`; JWT should be explicitly limited to Web session compatibility where intended.

### A2 — High — Deploy payload examples disagree on what is actually signed and submitted

Category: API gap / security gap / doc inconsistency

Evidence:
- `design/auth.md:150`–`design/auth.md:159` says AI agents obtain `ClientAuthCertificate + CodeSigningCertificate`, sign `module_hash + metadata`, then call `swarm_deploy`.
- `specs/security/09-command-source.md:75`–`specs/security/09-command-source.md:101` defines `DeployPayload` with `player_id`, `module_hash`, `world_id`, `code_signing_cert_id`, `deploy_nonce`, and `signature`, with the nonce obtained through `swarm_deploy_challenge`.
- `specs/security/03-mcp-security.md:212`–`specs/security/03-mcp-security.md:222` shows `swarm_deploy` params as only `wasm_bytes`, `language`, `version_tag`, and `room_id`, and returns active deployment; it omits certificate id, nonce, payload hash, metadata, signature, and challenge flow.
- `GETTING-STARTED.md:73`–`GETTING-STARTED.md:76` reduces MCP deploy to `swarm_deploy(module_bytes, wasm_signature)`, which is too underspecified for the canonical deploy protocol.

Why this matters:
- Deploy is the most security-sensitive developer action. If one team implements the MCP tool from `03-mcp-security` and another implements validation from `09-command-source`, clients will not interoperate.
- The current examples obscure whether the signature is over raw WASM bytes, module hash, metadata, room_id, version_tag, nonce, or a canonical payload. That is exactly where replay and substitution bugs tend to appear.

Expected resolution before implementation:
- Define one authoritative deploy JSON schema, likely in `specs/reference/mcp-tools.md` or a referenced schema file, and make all examples use the same fields and signing string.
- Decide whether `swarm_deploy_challenge` is an MCP tool. It is required by `specs/security/09-command-source.md:99` and `specs/security/09-command-source.md:105`, but it is absent from `design/interface.md:17`–`design/interface.md:62` and `specs/reference/mcp-tools.md:7`–`specs/reference/mcp-tools.md:86`.

### A3 — High — MCP tool inventory is not synchronized across design, reference, and security spec

Category: API gap / doc inconsistency / UX gap

Evidence:
- `design/interface.md:17`–`design/interface.md:62` lists a broad MCP catalog including auth, tournament, and `resources/list` / `resources/read`.
- `specs/reference/mcp-tools.md:47`–`specs/reference/mcp-tools.md:86` mostly mirrors that catalog, but its “not in MCP” list includes `swarm_spawn` at `specs/reference/mcp-tools.md:119`, while `design/interface.md:66` lists only `swarm_move`, `swarm_attack`, and `swarm_build` as examples.
- `specs/security/03-mcp-security.md:203`–`specs/security/03-mcp-security.md:254` contains a much smaller MCP table and omits all auth tools such as `swarm_get_server_trust`, `swarm_register_challenge`, `swarm_submit_csr`, certificate lifecycle tools, account recovery tools, tournament tools, and resource tools.
- `specs/security/03-mcp-security.md:260`–`specs/security/03-mcp-security.md:261` names additional forbidden direct-gameplay tools (`swarm_harvest`, `swarm_heal`, `swarm_transfer`, `swarm_withdraw`) that are not reflected in the reference doc's forbidden list.

Why this matters:
- MCP is the AI-agent API surface. Tool list drift is highly visible: function-calling agents, SDK generators, docs search, and server implementations will disagree about available methods.
- Auth tools are especially important in this redesign; their absence from the security MCP table makes it unclear whether they are MCP tools, Auth Service routes, or both.

Expected resolution before implementation:
- Establish one authoritative tool manifest and generate the design/reference/security tables from it, or explicitly mark each table as “summary only” and link to the canonical manifest.
- Include tool name, auth requirement, scope, rate-limit bucket, params schema, result schema, and error codes for every MCP method.

### A4 — Medium — Error code taxonomy is fragmented and not attached to tool schemas

Category: API gap / UX gap

Evidence:
- `design/auth.md:695`–`design/auth.md:710` defines auth error codes such as `invalid_credentials`, `username_taken`, `invalid_pow`, `challenge_expired`, `rate_limited`, and `internal_error`.
- `specs/12-gateway-protocol.md:29`–`specs/12-gateway-protocol.md:30` and `specs/security/09-command-source.md:197`–`specs/security/09-command-source.md:198` define transport/auth failures such as `MissingTransportHeader` and `AudienceMismatch`.
- `design/interface.md:100` and `specs/core/04-wasm-sandbox.md:212` say host functions return `i32`, where `0 = success` and negative values are error codes, but the negative enum/range is not defined in the reviewed API-facing documents.
- `specs/reference/mcp-tools.md:7`–`specs/reference/mcp-tools.md:86` lists tools but does not attach per-tool error codes or retry guidance.

Why this matters:
- New client authors need to know which failures are retryable, which require new PoW/challenge, which require user recovery, and which indicate a developer bug.
- Current docs contain the raw ingredients but not an API contract. Without a unified error taxonomy, SDKs will invent incompatible exception hierarchies and retry policies.

Expected resolution before implementation:
- Add a shared error envelope and per-domain error registry for MCP/REST/Auth/Deploy/HostFunction.
- Attach expected errors to each MCP tool schema, with retryability and recovery guidance.

### A5 — Medium — Compatibility-layer story is intentionally minimal but underspecified for migration tooling

Category: UX gap / deferred implementation concern

Evidence:
- `design/README.md:207`–`design/README.md:214` says Swarm does not pursue Screeps API compatibility, but community projects can build a compatibility layer mapping Screeps-style calls to Swarm commands.
- `design/tech-choices.md:182`–`design/tech-choices.md:196` commits to TypeScript and Rust SDKs generated from `game_api.idl`.
- `GETTING-STARTED.md:20`–`GETTING-STARTED.md:23` offers TypeScript and Rust SDKs, but the quickstart does not mention compatibility boundaries, migration helpers, or how an AI agent discovers unsupported Screeps-style APIs.

Why this matters:
- This is not a blocker for the clean-slate auth redesign, and I agree with not making Screeps compatibility a core constraint.
- But the project explicitly positions itself as a Screeps spiritual successor. Without a visible migration/compatibility stance in the SDK/API docs, new users and AI agents will assume more compatibility than exists.

Expected resolution before public SDK release:
- Add a short “not Screeps-compatible by default” note to the developer entry points and expose a machine-readable capability/schema path so agents fail early instead of generating Screeps API calls.

## Strengths

- The trust model has a clean separation of authority: Server Root CA is offline, Server Intermediate CA signs short-lived purpose-specific certificates, and Swarm CA is not installed into OS/browser trust stores (`design/auth.md:105`–`design/auth.md:124`, `design/auth.md:217`).
- Purpose separation is strong and intuitive: `ClientAuthCertificate`, `CodeSigningCertificate`, `AdminCertificate`, and `FederationCertificate` have distinct usages, TTLs, and scopes (`design/auth.md:257`–`design/auth.md:266`).
- Multi-device and recovery flows are first-class rather than bolted on later (`design/auth.md:278`–`design/auth.md:297`). This avoids the common failure mode where “lost device” recovery bypasses the intended auth model.
- Canonical request signing is correctly specified at the conceptual layer, including certificate chain, cert id, timestamp, nonce, body hash, and signature verification (`design/auth.md:299`–`design/auth.md:328`).
- Transport audience binding is a good guardrail against browser/agent credential confusion (`specs/12-gateway-protocol.md:155`–`specs/12-gateway-protocol.md:171`, `specs/security/09-command-source.md:185`–`specs/security/09-command-source.md:199`).
- The design wisely keeps MCP from becoming a gameplay remote-control API; game actions still flow through WASM and deferred commands (`design/interface.md:64`–`design/interface.md:66`, `specs/reference/mcp-tools.md:117`–`specs/reference/mcp-tools.md:122`).

## Questions/Assumptions

- I assume `specs/reference/mcp-tools.md` is intended to be developer-facing and close to authoritative for SDK/tool generation. If it is only a human overview, a separate machine-readable schema needs to be identified.
- I assume `swarm_deploy_challenge` is required, because `specs/security/09-command-source.md` makes `deploy_nonce` server-issued and single-use. If the challenge is embedded into `swarm_deploy` instead, the deploy flow should say so explicitly.
- I assume JWT/access_token may remain valid for browser/Web session compatibility, but not as a primary credential on MCP Agent endpoints.
- I assume the reviewed docs describe target design, not current implementation. Findings therefore focus on contradictions and missing contracts that would block implementation alignment, not on code availability.

## Missing

- A canonical MCP tool manifest with schema-level details: params, result, auth material, scope, rate-limit bucket, audit fields, and error codes.
- A single deploy schema that reconciles `swarm_deploy`, `DeployPayload`, deploy nonce/challenge, module hash, metadata, certificate id, and signature coverage.
- A unified error envelope and retry taxonomy across MCP JSON-RPC, REST/Gateway, Auth, Deploy, and WASM host functions.
- SDK onboarding details for certificate storage, canonical request construction, deploy signing, and error recovery. The design states these exist conceptually, but the developer-facing reference does not yet make them executable.
- Explicit compatibility-layer boundary in the quickstart: what is intentionally not Screeps-compatible, and how agents discover the supported Swarm API surface.

## Phase Ordering

1. First, freeze the auth/transport contract: MCP Agent must consistently use application certificates + canonical request signatures; JWT remains only where the Web compatibility layer explicitly allows it.
2. Next, freeze the deploy contract: define the deploy challenge/nonce flow, exact signed payload, canonical serialization, and MCP method names.
3. Then, generate or manually synchronize the MCP tool manifest across `design/interface.md`, `specs/reference/mcp-tools.md`, and `specs/security/03-mcp-security.md`.
4. Then, define SDK-facing error envelopes and retry guidance before implementation teams write clients.
5. Finally, update quickstart examples so the first AI-agent path exercises the real certificate + CSR + signed deploy protocol rather than a simplified placeholder.
