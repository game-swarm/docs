# R-appcert-clean-slate — GPT-5.5 Architect Review

## Verdict

CONDITIONAL_APPROVE

认证重设计的主干架构是成立的：Server Root CA offline、Server Intermediate CA online signing、CSR + client-held Ed25519 key、用途隔离证书、canonical request signature、federated local re-signing 这些边界组合起来，像成熟的“private PKI + SPIFFE/SPIRE 风格工作负载身份 + TOFU pinning”的应用层版本。它比 OAuth2/JWT/password 作为核心信任根更适合自托管、离线和 AI agent 自动接入场景。

我没有看到必须推翻方案的 blocker。需要在实现前修正的主要问题是“权威表/接口表/旧术语残留”造成的 API 合同歧义：这些不会否定架构，但如果直接进入实现，会让 Gateway、MCP、SDK、Auth Service 各自按不同文档实现。

## Top findings

### A1 — High — Gateway MCP auth path still says JWT while the new model requires app certificates

Category: doc inconsistency / API gap

Evidence:
- `specs/12-gateway-protocol.md:21` defines Agent/MCP auth as “Application certificate + signed request”.
- `specs/12-gateway-protocol.md:118` then lists Gateway MCP responsibilities and says `JWT 认证（mcp audience）`.
- `specs/12-gateway-protocol.md:155` declares the Transport Auth Matrix as the unique authoritative table, where MCP Agent requires `Swarm-Certificate-Chain` + `Swarm-Signature` + `X-Swarm-Transport: mcp` at `specs/12-gateway-protocol.md:163`.
- `design/auth.md:1004` says the only authoritative credential is application-layer certificate chain + user private-key signature; bearer tokens are only Web session compatibility.

Why this matters:
This is the classic “migration succeeded in the design doc, failed in the gateway spec” problem. Gateway implementers may keep a JWT verifier on the MCP path, while Auth/SDK implementers generate app-cert signed MCP requests. The result is not a compile-time conflict; it becomes an integration failure or, worse, a compatibility mode that accidentally accepts bearer tokens on an endpoint intended to require request signatures.

Recommendation:
Make `specs/12-gateway-protocol.md` internally consistent: MCP Gateway responsibility should be certificate-chain validation, canonical request verification, nonce/timestamp replay defense, audience check, and routing. JWT should be described only for Browser/Web session compatibility paths.

### A2 — High — deploy nonce flow depends on `swarm_deploy_challenge`, but the tool is absent from the public MCP tables

Category: API gap / doc inconsistency

Evidence:
- `specs/security/09-command-source.md:99` says `deploy_nonce` is server-issued and obtained through MCP `swarm_deploy_challenge`.
- `specs/security/09-command-source.md:105` makes `swarm_deploy_challenge` step 1 of deployment verification.
- `design/interface.md:23` lists deploy tools but includes only `swarm_deploy`, `swarm_validate_module`, `swarm_rollback`, and `swarm_list_modules`.
- `specs/reference/mcp-tools.md:18` likewise lists deployment tools without `swarm_deploy_challenge`.
- `GETTING-STARTED.md:73` shows MCP deployment as `swarm_deploy(module_bytes, wasm_signature)`, omitting challenge/nonce/DeployPayload.

Why this matters:
The anti-replay property of code deployment is delegated to a nonce service, but the service is not part of the discoverable API surface. This tends to produce one of two bad outcomes: SDK authors skip the nonce and sign only module bytes, or server authors invent an implicit nonce flow not visible to agents and docs. Either weakens the audit/replay model.

Recommendation:
Promote `swarm_deploy_challenge` into all authoritative MCP tool tables and the getting-started flow, or fold it explicitly into `swarm_deploy` as a two-phase operation. The public API should show `DeployPayload` fields, not `wasm_signature` as an opaque shorthand.

### A3 — Medium — certificate TTL policy conflicts across the same design document

Category: doc inconsistency / deferred implementation concern

Evidence:
- `design/auth.md:259` lists `ClientAuthCertificate` TTL as 24h and `CodeSigningCertificate` TTL as 7d.
- `design/auth.md:282` recommends common-device ClientAuth + CodeSigning certs for 30–180 days.
- `design/auth.md:969` lists both `ClientAuthCertificate` and `CodeSigningCertificate` as 15 min–180 days.
- `design/auth.md:297` makes online CRL retention depend on `max_certificate_ttl + max_clock_skew + federation_revocation_cache_ttl + operational_grace`.

Why this matters:
TTL is not just policy text here; it drives CRL retention, renewal UX, breach blast radius, federation cache staleness, and mobile/agent operational behavior. If implementers pick different TTL defaults for Auth Service, CRL cleanup, SDK renewal, and runbook expectations, certificates will appear valid in one component and stale in another.

Recommendation:
Define one canonical `CertificateTtlPolicy` table with defaults and allowed ranges per profile + usage. Other sections should refer to it instead of repeating numbers.

### A4 — Medium — transport audience formats are inconsistent between design docs and specs

Category: API gap / doc inconsistency

Evidence:
- `design/auth.md:311` defines canonical request payload audience as `<world_id>@<gateway_origin>` at `design/auth.md:322`.
- `design/auth.md:113` defines certificate audience as `(server_id, world_id, gateway_origin)`.
- `specs/security/03-mcp-security.md:114` says Agent certificate audience binds `{server_id, world_id, "cli"}`.
- `specs/security/09-command-source.md:189` defines concrete audience strings such as `mcp:{server_id}:{world_id}:{player_id}`, `ws:{server_id}:{world_id}:{player_id}`, and `rest:{server_id}:{world_id}:{player_id}`.
- `specs/12-gateway-protocol.md:28` says audience mismatch is rejected, but does not define the canonical serialization beyond referencing security/09.

Why this matters:
Audience is a security boundary, not a label. If one component signs `world@gateway`, another validates `mcp:server:world:player`, and a third stores `{server_id, world_id, transport}`, valid requests will fail or validators will normalize too loosely. Overly loose audience matching is a common source of cross-transport replay bugs.

Recommendation:
Pick one canonical audience grammar and version it, e.g. `SWARM-AUD-V1:{transport}:{server_id}:{world_id}:{subject_id?}:{gateway_origin?}`. Then update certificate fields, request signing payloads, Gateway matrix, and SDK examples to use exactly that grammar.

### A5 — Medium — Auth Service placement is architecturally underspecified relative to Gateway statelessness

Category: doc inconsistency / deferred implementation concern

Evidence:
- `design/auth.md:63` says Auth Service / Domain is `src/auth/ (Engine 内或独立服务)`.
- `design/auth.md:118` says Auth may live inside the Engine process or as a separate service, while keeping the signing interface minimal.
- `design/README.md:82` shows Gateway containing `Auth (CA/CSR)` in the top-level architecture.
- `specs/12-gateway-protocol.md:17` says Gateway is stateless and all Gateway instances share NATS with no instance-to-instance communication.
- `design/auth.md:97` says Gateway is a stateless proxy and does not hold auth state.

Why this matters:
“Auth in Gateway”, “Auth in Engine”, and “Auth as independent service” are materially different deployment models. They affect CA key custody, horizontal scaling, FDB transaction ownership, internal RPC boundaries, and failure modes. The current docs mostly agree on Auth as independent control plane, but the top-level diagram still teaches a contradictory mental model.

Recommendation:
Declare one target topology: preferably `Gateway = stateless verifier/proxy`, `Auth Service = stateful control-plane owner of CSR/challenge/cert/session FDB subspace`, `Engine = consumer/verifier of issued identity`. If Auth can be embedded for dev, mark it as deployment packaging only, not a different ownership model.

### A6 — Low — several internal section references are stale after the auth rewrite

Category: doc inconsistency

Evidence:
- `specs/security/03-mcp-security.md:118` points AI credential storage to `design/auth.md §13.4`, but AI Agent credential storage is at `design/auth.md:996` under §14.4.
- `specs/security/03-mcp-security.md:159` points the authority model to `design/auth.md §13.5`, but it is at `design/auth.md:1002` under §14.5.
- `design/auth.md:693` says app-cert requests are verified per §5.4, but canonical request verification is §5.6 and §5.4 is code-signing certificate expiration semantics.
- `design/auth.md:746` says new password must pass §7 password rules, but password rules are §8.

Why this matters:
These are not architectural blockers, but they are bad affordances for implementers. In a security-heavy design, stale references cause reviewers and implementers to validate the wrong section.

Recommendation:
Run a reference audit after fixing the higher-level model issues. Prefer stable anchors or section titles over numeric-only references where possible.

### A7 — Low — technical choice text still describes “Blake3 MAC” as code signing, conflicting with Ed25519 certificate signing

Category: doc inconsistency

Evidence:
- `design/tech-choices.md:150` includes a code-signing comparison table where `Blake3 MAC` is marked as selected.
- `design/tech-choices.md:165` then selects Ed25519 for certificates, CSR, request signatures, and code signing at `design/tech-choices.md:176`.
- `design/auth.md:270` and `specs/security/09-command-source.md:71` define code deployment authorization as Ed25519 signatures under `CodeSigningCertificate`.

Why this matters:
A keyed MAC is not a non-repudiable code-signing primitive unless the verifier shares the key, which would collapse the user-held private-key model. The later Ed25519 section is correct, but the earlier table can mislead SDK or server implementers.

Recommendation:
Reframe Blake3 as hash/XOF/content addressing only. Code-signing should consistently mean Ed25519 over canonical `DeployPayload` under `CodeSigningCertificate`.

## Strengths

- Strong trust-root separation: `design/auth.md:123` keeps Server Root CA offline and rotates/revokes online intermediates; `design/auth.md:217` explicitly prevents Swarm CA from becoming a browser/system TLS trust anchor.
- Good control-plane/data-plane split: `design/auth.md:25` and `design/auth.md:95` separate Auth domain responsibilities from Engine simulation; this mirrors successful identity architectures where issuance is centralized but verification is widely consumable.
- Purpose isolation is well-modeled: `design/auth.md:259` separates client auth, code signing, admin, and federation certificates; `specs/security/09-command-source.md:15` maps command sources to explicit auth contexts and gameplay capability.
- Federation model avoids remote authority leakage: `design/auth.md:1107` requires local re-signing and rejects remote CodeSigning/Admin certificates by default, which is the right shape for autonomous worlds.
- Unsafe transport story is honest: `design/auth.md:334` explains TOFU/fingerprint pinning and `design/auth.md:338` admits metadata visibility, blocking, replay window, and first-pinning MITM risk instead of pretending HTTP becomes confidential.
- MCP fairness boundary is preserved: `design/interface.md:64` and `specs/security/03-mcp-security.md:37` keep MCP as management/view/deploy interface, not a gameplay executor; all gameplay still goes through WASM.

## Concerns

### A1. Hidden compatibility paths may outlive the migration
The biggest risk is not the certificate model itself; it is residual JWT/bearer-token wording causing “temporary” compatibility bypasses. Historically, auth migrations fail when old and new trust roots are both accepted without a single choke point and deprecation invariant.

### A2. API discoverability is not yet good enough for agents
AI agents will rely on `specs/reference/mcp-tools.md` and `GETTING-STARTED.md`, not deep security specs. Any missing tool there is functionally missing from the product, even if it appears in `specs/security/09-command-source.md`.

### A3. Too many repeated literals invite split-brain implementation
TTL values, audience shapes, scope names, and transport labels appear in multiple documents. These should become named policy tables or IDL constants; otherwise Gateway, SDK, Auth, and Engine will drift.

### A4. Auth topology needs one mental model
The docs mostly intend Auth as a separate domain, but diagrams still imply Gateway-owned Auth and text allows Engine-embedded Auth. This is okay as deployment packaging, not okay as ownership ambiguity.

## Missing

- Canonical schema/IDL for `CertificateBundle`, `ClientAuthCertificate`, `CodeSigningCertificate`, `AdminCertificate`, `FederationCertificate`, `CertificateTtlPolicy`, `CertificateAudience`, `CSR`, and `DeployPayload`.
- One authoritative transport/auth table that all other docs quote rather than restating.
- Public MCP reference for `swarm_deploy_challenge` or an explicit replacement two-phase deploy protocol.
- CA/intermediate emergency rotation state machine: what clients see, how trust pins update, how federation stale caches react, and how replay/audit handles epoch bumps.
- Threat-model table for server-managed private-key exception path. The current constraints are good, but this path is inherently dangerous and deserves a dedicated abuse-case section.
- SDK onboarding examples for CLI/agent credential persistence, renewal, and pin verification; `GETTING-STARTED.md` currently compresses the most security-sensitive path to one line.

## Questions/Assumptions

- Assumption: `specs/12-gateway-protocol.md` Transport Auth Matrix is intended to become the single source of truth, as it says at `specs/12-gateway-protocol.md:155`.
- Assumption: JWT/access tokens remain only for browser/Web compatibility and are never accepted as sole auth for MCP Agent endpoints.
- Question: Should Auth Service be a separate process in production, or is Engine-embedded Auth an accepted production topology? The documents should make one answer normative.
- Question: Is `gateway_origin` part of certificate audience, request audience, both, or only a pinning/display property? Current docs imply multiple shapes.
- Question: Are common-device certificates intended to be 24h/7d or 30–180d? This determines CRL retention and renewal UX.

## Phase Ordering

1. Freeze the authority model first: app-cert request verification, JWT compatibility boundaries, Auth Service ownership, Gateway responsibilities.
2. Freeze public API next: MCP tool table, `swarm_deploy_challenge`, `DeployPayload`, canonical audience grammar, certificate bundle schema.
3. Then align policy constants: TTL ranges, CRL retention formula, nonce/timestamp windows, scope names, error codes.
4. Then update onboarding/docs: `GETTING-STARTED.md`, `specs/reference/mcp-tools.md`, Runbook CA rotation examples, SDK credential storage examples.
5. Only after those are consistent should implementation start; otherwise teams will build incompatible Gateway/Auth/SDK slices from different “truths”.

## Blocker assessment

No blocker requiring architectural redesign. The certificate-first architecture is a solid fit for Swarm’s self-hosted and AI-agent requirements. The condition for approval is documentation/API convergence before implementation: especially A1, A2, A3, and A4 should be fixed before coding the auth path.
