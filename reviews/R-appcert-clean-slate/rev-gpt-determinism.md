# R-appcert-clean-slate — Determinism Review

Reviewer: rev-gpt-determinism  
Scope: clean-slate review of the app-certificate/auth redesign docs listed in task `t_526b2dd7`; old reviews and git history intentionally not read.

## Verdict

CONDITIONAL_APPROVE

The Server CA + CSR + application-layer certificate direction is architecturally sound and fits Swarm's self-hosted/offline/AI-agent requirements. I do not see a fundamental blocker in replacing OAuth2/JWT/password as the core trust root.

However, determinism/replay depends on exact byte-level and state-transition contracts. The current docs contain several places where a compliant implementation could make different choices and still claim to follow the design. Those gaps should be closed before implementation is treated as frozen.

## Top findings

### A1 — High — Command ordering contract conflicts across specs

Category: doc inconsistency

Evidence:
- `specs/core/01-tick-protocol.md:246` says commands are ordered by shuffled player order plus per-player command sequence.
- `specs/core/01-tick-protocol.md:250` materializes the global key as `(order_index, player_id, cmd.sequence, cmd)`.
- `specs/core/02-command-validation.md:99` says the sorting key is `(player_id, shuffle_order, source, sequence)`.

Why this can explode:
- These two keys are not equivalent. Putting `player_id` before `shuffle_order` groups by player id and can neutralize the fairness/randomization property of seeded shuffle.
- Replay determinism requires every node, validator, replay runner, and future audit tool to reconstruct the exact same RawCommand order. If one follows `01-tick-protocol` and another follows `02-command-validation`, `state_checksum` can diverge without any malicious input.
- The app-certificate design adds `source` and auth context to commands, so this ambiguity becomes more dangerous: deterministic replay must define whether `source` participates in ordering and where.

Recommendation:
- Make one canonical ordering key authoritative, preferably `(shuffle_order, player_id, source_rank, sequence)` or `(shuffle_order, player_id, sequence)` if gameplay commands truly only come from WASM.
- State explicitly how non-gameplay sources (`MCP_Deploy`, `Replay`, `Admin`, `Simulate`) are excluded from or projected into the gameplay command queue.

### A2 — High — Deploy replay protection references an undefined MCP API/state machine boundary

Category: API gap

Evidence:
- `specs/security/09-command-source.md:99` requires `deploy_nonce` to be obtained through MCP `swarm_deploy_challenge`.
- `specs/security/09-command-source.md:105` makes `swarm_deploy_challenge` the first step of deployment validation.
- `specs/security/09-command-source.md:272`-`specs/security/09-command-source.md:276` introduce `pending_deploy` and a `deploy_token` when compile time exceeds nonce TTL.
- `design/auth.md:606`-`design/auth.md:629`, `design/interface.md:15`-`design/interface.md:57`, and `specs/reference/mcp-tools.md:47`-`specs/reference/mcp-tools.md:70` list auth/MCP tools but do not define `swarm_deploy_challenge` or a deploy-token completion tool.

Why this can explode:
- Replay and anti-replay semantics are only as deterministic as the nonce lifecycle. If the tool is not in the public API/reference, implementers may fold nonce issuance into `swarm_deploy`, use request nonce as deploy nonce, or skip the pending token boundary.
- Long compile handling is underspecified: the design says the nonce is not extended, but does not define exactly what the signed payload covers after `deploy_token` issuance or which operation consumes the token.
- This is a classic “looks fine in sequence diagram, fails in implementation” pattern: one spec has the security invariant, another spec has the API surface, and they do not meet.

Recommendation:
- Add `swarm_deploy_challenge` and the deploy-token completion/commit operation to design/interface, auth tool list, and reference/mcp-tools, or remove the split if deploy is always synchronous.
- Define whether `deploy_token` is bearer, signed, certificate-bound, module-hash-bound, slot-bound, and single-use.

### A3 — High — Canonical request/body serialization is named but not specified

Category: security gap

Evidence:
- `design/auth.md:299` introduces `Canonical Request Signature`.
- `design/auth.md:317` signs `body_hash: <blake3 canonical body hash>`.
- `design/auth.md:325`-`design/auth.md:330` defines verification order but not canonicalization rules.
- `specs/security/03-mcp-security.md:163` only says MCP/Agent uses canonical request signature; it does not define bytes-to-sign.

Why this can explode:
- “Canonical body hash” is not a contract until JSON key ordering, number normalization, Unicode normalization, duplicate key handling, base64 encoding, header casing, path normalization, query ordering, and MCP JSON-RPC envelope canonicalization are defined.
- Different SDKs (TypeScript, Rust, Python agents) will otherwise sign different byte strings for the same logical request, causing hard-to-debug auth failures.
- Worse, server and client disagreements can create replay or signature-confusion bugs if one layer signs a normalized body and another layer routes/verifies a different semantic body.

Recommendation:
- Define `SWARM-REQUEST-V1` canonicalization as an explicit algorithm with test vectors.
- Include method/path/tool-name normalization, query handling, JSON canonicalization profile, body size/hash domain separator, timestamp units, and whether transport headers are signed.

### A4 — High — Revocation outcome is intentionally flexible but not deterministic

Category: security gap

Evidence:
- `design/auth.md:272` requires `CodeSigningCertificate` to be valid at deploy submission time.
- `design/auth.md:275` says certificate revocation is a security event and the server may freeze, roll back, or continue allowing existing modules by revocation reason.
- `specs/security/09-command-source.md:121`-`specs/security/09-command-source.md:126` repeats CRL checkpoints and the flexible freeze/rollback/continue behavior.
- `specs/core/04-wasm-sandbox.md:338` says deployed modules validate `module_hash` and current validation/security epoch, while revocation is handled by reason policy.

Why this can explode:
- Natural expiry not affecting deployed modules is a good deterministic rule. Revocation, however, is a state transition that affects whether a module keeps running, freezes, or rolls back.
- Without an authoritative `revocation_reason -> deterministic module_state transition` table, two operators or code paths can make different choices for the same event.
- Replay must know whether a module was active at tick N because of a recorded policy decision or because live CRL state happened to be available. The docs say TickTrace records auth context, but not the revocation policy version or module lifecycle event needed to reconstruct the decision.

Recommendation:
- Define a closed enum of revocation reasons and deterministic default action per reason.
- Record revocation policy version, decision tick, affected module slot/hash, and resulting module state in audit/TickTrace or the replay input set.
- Separate operator override from automatic replay semantics; overrides should become explicit world events.

### A5 — Medium — Code signing primitive is contradictory between Blake3 MAC and Ed25519

Category: doc inconsistency

Evidence:
- `design/tech-choices.md:129` titles the section “哈希 / PRNG / 代码签名: Blake3（单原语）”.
- `design/tech-choices.md:154` selects `Blake3 MAC` for code signing.
- `design/tech-choices.md:159` says code signing is `Blake3 keyed hash / MAC`.
- `design/tech-choices.md:176`-`design/tech-choices.md:178` says certificate chain, CSR, request signature, and code signing all use Ed25519.
- `design/auth.md:262` and `specs/security/09-command-source.md:75`-`specs/security/09-command-source.md:101` model deploy signatures as Ed25519 over structured payloads.

Why this matters:
- Blake3 MAC is symmetric authentication, not user-verifiable non-repudiable code signing in the same sense as Ed25519. It does not fit the CSR/certificate/public-key audit model unless a shared secret exists, which the docs do not define.
- Deterministic audit/replay wants the deploy record to prove which public key signed which module hash. Ed25519 supports that cleanly; Blake3 MAC does not without additional key custody assumptions.

Recommendation:
- Make Ed25519 the only deploy/code-signing signature primitive, and keep Blake3 for hashing/PRNG/body hashes.
- If Blake3 MAC is intended only for internal cache/authentication, rename it so it is not confused with user code signing.

### A6 — Medium — Transport audience models differ enough to invite incompatible certificates

Category: doc inconsistency

Evidence:
- `design/auth.md:322` signs `audience: <world_id>@<gateway_origin>` in `SWARM-REQUEST-V1`.
- `specs/security/03-mcp-security.md:181` says certificate `audience` is `server_id + world_id + transport`.
- `specs/security/09-command-source.md:187`-`specs/security/09-command-source.md:194` defines transport-specific audience strings such as `mcp:{server_id}:{world_id}:{player_id}` and `rest:{server_id}:{world_id}:{player_id}`.
- `specs/12-gateway-protocol.md:161`-`specs/12-gateway-protocol.md:165` makes transport separation part of the auth matrix.

Why this matters:
- These are not just naming differences: origin-based audience and transport-based audience answer different replay questions.
- If SDKs sign `world_id@gateway_origin` but certificates carry `mcp:{server_id}:{world_id}:{player_id}`, cross-transport replay defenses become implementation-specific.

Recommendation:
- Define a single typed `Audience` structure and map it to canonical string bytes once.
- State whether `gateway_origin` is included in the certificate, request signature, both, or neither.

### A7 — Medium — WASM determinism contract does not explicitly ban floating-point nondeterminism

Category: deferred implementation concern

Evidence:
- `specs/core/04-wasm-sandbox.md:88` disables wasm threads.
- `specs/core/04-wasm-sandbox.md:89` allows SIMD and `specs/core/04-wasm-sandbox.md:90` disables relaxed SIMD.
- `specs/core/04-wasm-sandbox.md:104`-`specs/core/04-wasm-sandbox.md:114` disables WASI time/random/network.
- `design/tech-choices.md:54` mentions floating point can be closed on the engine-side Rhai layer, but the WASM module validation section does not state whether floating-point instructions are allowed in player WASM.

Why this matters:
- WASM numeric semantics are much better specified than native floating point, and disabling relaxed SIMD is a good sign. Still, if gameplay commands can depend on floating-point pathfinding, NaN canonicalization, or SDK-level float math, cross-version/compiler differences can leak into command generation.
- The core replay design records `Command[]` rather than re-running WASM, which protects historical replay, but live deterministic simulation across validators still needs identical command generation assumptions if multiple executors validate the same player code.

Recommendation:
- State whether player WASM may use floating-point instructions, and if yes, where determinism is relied upon versus not relied upon.
- Add validation/test-vector language for NaN, SIMD, and SDK math behavior.

### A8 — Low — HTTP pinning acknowledges first-use MITM but lacks operator UX guardrails

Category: UX gap

Evidence:
- `design/auth.md:334` requires users to confirm `server_id + Server Root CA fingerprint` on first HTTP access.
- `design/auth.md:339` acknowledges first-pinning MITM risk.
- `GETTING-STARTED.md:67`-`GETTING-STARTED.md:70` tells users to confirm fingerprint and generate a local device key, but does not say where the fingerprint should be obtained out of band.
- `RUNBOOK.md:101`-`RUNBOOK.md:102` shows how operators print the fingerprint.

Why this matters:
- The security design is honest, but the happy-path onboarding can train users to click through TOFU prompts without an out-of-band comparison.
- This is not a blocker for architecture, but it is a known failure pattern in SSH-like trust-on-first-use systems.

Recommendation:
- Add a short operator/user UX contract: display fingerprint in console/admin panel, publish it in server docs, and require mismatch handling instructions in clients.

## Strengths

- The design cleanly separates transport TLS trust from Swarm application-layer identity; this is the right shape for self-hosted, local-network, and AI-agent usage.
- The “cert valid at deploy time; natural expiry does not stop already deployed modules” rule is pragmatic and avoids a timestamp-authority dependency.
- The MCP/Web UI boundary is strong: AI agents deploy WASM like humans, and MCP is not a privileged gameplay command channel.
- Deploy payloads include good anti-replay ingredients: domain separator, module hash, player/world/slot, nonce, expiry, and certificate-bound signature.
- The replay system’s choice to persist sorted `Command[]` rather than re-run WASM is a strong mitigation against Wasmtime/version drift in historical replay.
- CRL online-window retention is operationally realistic; it avoids requiring infinite online revocation history for naturally expired certificates.

## Questions/Assumptions

- I assume the intended deploy signature primitive is Ed25519, not Blake3 MAC, because the auth and command-source specs consistently model user-held private keys and public-key certificates.
- I assume gameplay commands are intended to come only from WASM after the redesign; if so, command sorting specs should not include deploy/admin/query sources in the gameplay queue.
- I assume “local res(ign)” in federation means the target world always issues local certificates before any local operation; the docs support this, but the challenge canonicalization still needs exact bytes.
- I assume current docs are target design, not implementation status; I did not review code, ROADMAP, git history, or prior reviews.

## Missing

- A normative canonicalization spec with multi-language test vectors for `SWARM-REQUEST-V1`, CSR payloads, and `DeployPayload`.
- A complete deploy nonce API contract covering `swarm_deploy_challenge`, long compile `pending_deploy`, `deploy_token`, token consumption, and failure/idempotency behavior.
- A deterministic revocation policy table and replay/audit record schema for module lifecycle effects caused by key/certificate compromise.
- One authoritative command ordering key shared by tick protocol, command validation, replay, and source model.
- A single typed audience model spanning certificates, signed requests, gateway transports, and federation.
- An explicit WASM numeric determinism policy, especially for floating point/SIMD and SDK-generated code.

## Phase Ordering

1. Freeze determinism-critical contracts first: command ordering, canonical request bytes, deploy nonce/token state machine, and audience string/structure.
2. Then freeze security lifecycle semantics: CRL retention, revocation reason table, security epoch behavior, and module freeze/rollback/continue events.
3. Then update API/reference docs so every required security primitive is visible to SDK and MCP implementers.
4. Then add test vectors and replay fixtures: signed request vectors, deploy replay attempts, revoked certificate module behavior, and cross-language canonicalization checks.
5. Only after those are stable should implementation begin; otherwise SDKs and gateway/auth/engine can each make locally reasonable but globally incompatible choices.
