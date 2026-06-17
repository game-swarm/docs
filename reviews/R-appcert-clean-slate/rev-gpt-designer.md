# R-appcert-clean-slate — Designer Review (GPT-5.5)

## Verdict

CONDITIONAL_APPROVE

The application-certificate redesign is directionally strong for both human and AI onboarding: it removes OAuth/browser dependency, keeps AI and human players on the same WASM path, and documents recovery factors, device certificates, request signing, and federation boundaries in unusually concrete detail. I do not see a design-level blocker from a UX/player-journey perspective, because the core primitives are coherent and the security model does not force players into impossible browser-only flows.

However, the docs are not yet fully spec-ready for “an AI player can learn and start playing using only MCP resources.” The first-hour path and the public MCP reference still have gaps and contradictions that would make an autonomous agent stall between account creation, deploy signing, and first successful bot execution. These should be closed before implementation, but they do not require rethinking the certificate model.

## Top findings

### G1 — High — AI-only first-hour onboarding is described but not executable from the public MCP/resource surface

Category: UX gap / API gap

Evidence:
- `design/auth.md:166` lists intended MCP resources for AI onboarding: `docs/auth/onboarding-ai`, `docs/auth/errors`, `schema/auth-tools`, and `docs/auth/human-agent-handoff`.
- `specs/reference/mcp-tools.md:38` defines the learning tools `swarm_get_docs`, `swarm_get_schema`, `swarm_get_available_actions`, and `swarm_simulate`.
- `specs/reference/mcp-tools.md:47` lists auth tools, but only as names and short descriptions, without the referenced resource names, schemas, response shapes, ordering, or retry playbook.
- `GETTING-STARTED.md:73` reduces the AI path to `swarm_deploy(module_bytes, wasm_signature)`, skipping `swarm_get_server_trust`, Root CA fingerprint pinning, CSR creation, PoW, certificate persistence, CodeSigningCertificate selection, deploy nonce/signing, and first tick verification.

Designer impact:
An AI agent that starts from `GETTING-STARTED.md` plus MCP tool discovery can infer that registration exists, but cannot reliably complete the first session without reading `design/auth.md` directly. That violates the intended “MCP is the AI player’s screen and mouse” promise: the AI’s in-band learning path should be self-contained, not dependent on hidden design docs.

Recommendation:
Promote the onboarding resources from `design/auth.md` into the authoritative MCP reference as concrete `swarm_get_docs` / `resources/read` names. Add a single first-hour AI path: discover server trust → pin/confirm fingerprint → generate key → register challenge → solve PoW → submit CSR → persist bundle → request deploy nonce → sign deploy payload → deploy → inspect first tick. Include exact schemas and error recovery for each step.

### G2 — High — Deploy nonce is required by security flow but missing from public MCP tool tables

Category: API gap / doc inconsistency

Evidence:
- `specs/security/09-command-source.md:99` says `deploy_nonce` is server-issued and obtained through MCP `swarm_deploy_challenge`.
- `specs/security/09-command-source.md:105` makes `swarm_deploy_challenge` step 1 of deployment verification.
- `specs/security/09-command-source.md:253` repeats the deploy nonce lifecycle and again names `swarm_deploy_challenge`.
- `specs/reference/mcp-tools.md:18` lists deploy tools as `swarm_deploy`, `swarm_validate_module`, `swarm_rollback`, and `swarm_list_modules`, but not `swarm_deploy_challenge`.
- `design/interface.md:23` likewise lists deployment tools without `swarm_deploy_challenge`.
- `GETTING-STARTED.md:73` shows only `swarm_deploy(module_bytes, wasm_signature)`, which hides the nonce and `DeployPayload` ceremony.

Designer impact:
This is likely the first hard stop for a real AI player after successful account creation. The agent can learn that deploys need a nonce, but the public tool surface does not expose the tool needed to get one. Humans may work around this by reading specs and guessing; agents will not.

Recommendation:
Either add `swarm_deploy_challenge` to all MCP tool tables and schemas, or explicitly fold nonce issuance into `swarm_deploy` as a documented two-phase operation. The AI-facing docs should expose `DeployPayload` fields rather than using opaque `wasm_signature` shorthand.

### G3 — Medium — Gateway MCP auth text still says JWT while the redesigned model requires app certificates

Category: doc inconsistency / security gap

Evidence:
- `specs/12-gateway-protocol.md:21` marks Agent MCP auth as “Application certificate + signed request.”
- `specs/12-gateway-protocol.md:155` says the Transport Auth Matrix is the unique authoritative table.
- `specs/12-gateway-protocol.md:163` requires MCP Agent to use `Swarm-Certificate-Chain` + `Swarm-Signature` + `X-Swarm-Transport: mcp`.
- `specs/12-gateway-protocol.md:118` nevertheless lists Gateway MCP responsibility as “JWT 认证（mcp audience）”.
- `specs/security/03-mcp-security.md:112` says Agent endpoints must verify application certificates and canonical request signatures, not Origin headers.
- `design/auth.md:1004` states the only authoritative identity credential is the application certificate chain plus user private-key signature; bearer tokens are only Web compatibility.

Designer impact:
This creates an implementation and documentation trap exactly at the point where users and AI agents are trying to debug “why am I unauthorized?” If one doc says JWT and another says app-cert signature, onboarding copy and error messages will diverge.

Recommendation:
Replace the Gateway §5 JWT bullet with application-certificate verification and canonical request signature validation. Keep JWT wording only for browser/Web session compatibility paths.

### G4 — Medium — Recovery and device UX is robust in primitives but lacks a user-facing decision/state guide

Category: UX gap

Evidence:
- `design/auth.md:278` defines multiple active certificates per account and device-scoped management.
- `design/auth.md:289` says users revoke lost-device certificates without deleting the whole account.
- `design/auth.md:293` says losing all certificates requires verified email or admin recovery to submit a new CSR.
- `design/auth.md:748` documents email recovery and notes old certificates are kept by default, with UI prompting users to inspect/revoke inaccessible devices at `design/auth.md:787`.
- `design/auth.md:821` defines passkey recovery, including listing/revoking passkeys at `design/auth.md:843`.
- `design/auth.md:1127` sketches a LoginButton UI, but not the decision tree for “new account vs new device vs lost key vs temporary device vs agent-managed key.”

Designer impact:
The primitives are strong, but first-hour UX depends on players understanding which recovery path to choose and what happens to old devices. Without a state guide, the same secure design can feel like PKI jargon: users will not know whether they are creating an account, adding a device, recovering a lost key, or granting an agent custody.

Recommendation:
Add a compact Account/Device UX state matrix: account exists? has usable cert? has passkey/email? agent-managed or self-managed? desired profile? For each state, show primary CTA, required proof, resulting certificate profile, old-cert handling, and error copy.

### G5 — Medium — Error recovery exists for auth, but not for the full “first bot deployed” loop

Category: UX gap / deferred implementation concern

Evidence:
- `design/auth.md:695` defines auth error codes including `invalid_pow`, `challenge_expired`, `challenge_consumed`, `rate_limited`, and `internal_error`.
- `design/auth.md:140` and `design/auth.md:172` define PoW and username retry behavior for humans and AI agents.
- `specs/security/09-command-source.md:279` defines deploy state transitions, including nonce expiry, compile failure, deployed, rejected, and active.
- `specs/core/04-wasm-sandbox.md:191` defines WASM execution failures and output-size rejection behavior.
- `GETTING-STARTED.md:78` only tells users to use replay, `swarm_explain_last_tick`, and logs for debugging; it does not connect auth/deploy/sandbox errors into a first-hour troubleshooting ladder.

Designer impact:
The first hour of a programmable game is not “register succeeded”; it is “my bot performed a visible action.” Current docs have good local error codes, but no end-to-end recovery ladder for common first failures: fingerprint mismatch, PoW timeout, CSR rejected, deploy nonce expired, module validation failed, CodeSigningCertificate missing/expired, first tick returned zero commands, or command rejected.

Recommendation:
Add a first-bot troubleshooting table keyed by symptom and MCP tool: cannot register, cannot sign request, cannot deploy, deploy accepted but no action, action rejected, replay unavailable. This should map each symptom to an error code, likely cause, safe retry, and next tool call.

### G6 — Low — Human onboarding has a 5-minute promise, but the auth redesign adds invisible friction not reflected in the quickstart

Category: UX gap / doc inconsistency

Evidence:
- `GETTING-STARTED.md:3` promises “5 分钟上手 Swarm.”
- `GETTING-STARTED.md:67` lists four deployment steps, including Root CA fingerprint confirmation and CSR submission.
- `design/auth.md:130` expands human registration with username, device label, optional recovery factors, WebCrypto key generation, PoW progress, CSR submission, certificate storage, and multiple failure modes.
- `design/auth.md:1153` requires Web Worker PoW with progress, cancel/retry, and slow-device copy.

Designer impact:
The five-minute goal is still plausible, but only if the UI hides most PKI ceremony. The quickstart currently undersells the number of concepts a new player will encounter: Root CA fingerprint, device key, CSR, certificate, recovery factor, and WASM deploy signature.

Recommendation:
Keep the quickstart promise, but rewrite it as a guided “first session checklist” with the user-visible copy and expected wait times. Use plain-language labels like “Trust this server,” “Create this device,” and “Save recovery method,” while leaving CSR/certificate details in expandable advanced docs.

## Strengths

- The redesign removes the browser/OAuth dependency that previously made AI-agent onboarding structurally awkward; `design/auth.md:14` explicitly names AI players as first-class users.
- The fairness model remains clean: `specs/reference/mcp-tools.md:117` and `design/interface.md:64` clearly forbid direct MCP gameplay actions, keeping AI and humans on the same WASM execution path.
- The recovery model is multi-factor without making any single consumer identity provider mandatory: password, passkey, email, admin reset, and federation all converge back into CSR and local app certificates.
- Device-level certificates are a good UX/security compromise: users can revoke a lost device without burning the whole account, and temporary/managed/admin profiles have distinct constraints.
- The HTTP/unsafe transport story is unusually honest: `design/auth.md:336` documents what attackers can still observe or block, instead of pretending signatures provide confidentiality.
- Code-signing certificate expiry semantics are player-friendly: `design/auth.md:268` allows already deployed modules to keep running after natural cert expiry, preventing surprise colony death.

## Missing

- A concrete MCP resource contract for `docs/auth/onboarding-ai`, `docs/auth/errors`, `schema/auth-tools`, and `docs/auth/human-agent-handoff`.
- Public schemas for `CertificateBundle`, CSR payload, canonical request signature fields, `DeployPayload`, and deploy nonce responses in the AI-facing reference.
- A first-hour AI tutorial that proves an agent can go from no account to first visible in-game action without reading design docs.
- User-facing account/device/recovery state diagrams and copy, especially for “add new device,” “lost all keys,” “agent-managed key,” and “temporary device.”
- End-to-end troubleshooting that connects auth errors, deploy errors, sandbox failures, command rejections, replay, and `swarm_explain_last_tick`.
- Spectator/replay sharing remains underdeveloped relative to community growth: replay tools exist, but public replay permissions, share URLs, forkable bot examples, and social discovery are not yet framed as onboarding/retention loops.

## Fresh Ideas

- Add an MCP-native “onboarding quest” resource: `docs/tutorial/first-bot-ai`, with machine-checkable milestones: trust pinned, certificate issued, module validated, deploy accepted, first tick executed, first command accepted.
- Expose `swarm_onboarding_status` as a read-only helper returning the next missing prerequisite for a player/agent: no cert, no code cert, deploy nonce needed, no module, last tick rejected, etc.
- Make recovery UX device-centric instead of credential-centric: “This laptop,” “My agent,” “Temporary browser,” “Lost phone,” “Admin rescue link.” Hide certificate names until advanced mode.
- Add replay share cards for the first successful bot: a short link with tick range, bot version, visible outcome, and “fork this starter” metadata. This turns onboarding success into community propagation.
- Provide an AI-readable “policy preflight” resource summarizing server-specific auth settings: PoW difficulty, username visibility mode, allowed certificate profiles, federation policy, max WASM size, deploy limit, and replay visibility.
- Add a long-term identity goal beyond GCL/room level: “trusted developer reputation” based on signed module history, tournament results, reusable public bot libraries, and clean security/audit record. This gives certificates a positive social meaning, not just friction.

## Questions/Assumptions

- I assume `swarm_get_docs` / `resources/read` are intended to be sufficient for an AI player to self-onboard without out-of-band documentation.
- I assume the `design/auth.md` resources named in §4.2 are planned resources, not already implemented elsewhere outside this review scope.
- I assume public replay can be anonymous based on `specs/12-gateway-protocol.md:26`, but player-private replay sharing policy still needs product design.
- I did not read previous reviews or consensus notes; findings are based only on the target design/spec docs and limited cross-reference searches outside `reviews/`.
