# R-appcert-clean-slate — Performance Review (GPT-5.5)

## Verdict

CONDITIONAL_APPROVE

The application-certificate redesign is directionally sound for performance: Ed25519 is cheap enough for request-path authentication, code-signing validation is kept at deploy time rather than every tick, and the WASM compile cache explicitly avoids tying runtime validity to natural certificate expiry. I do not see a performance blocker that requires abandoning the architecture.

The approval is conditional because several hot-path and state-retention details are underspecified or internally inconsistent. These are the kinds of issues that look harmless in design review but later become latency spikes, cache stampedes, or operationally unbounded online state.

## Top findings

### A1 — High — CRL / certificate TTL policy is internally inconsistent and can silently enlarge the online revocation set

Category: doc inconsistency / deferred implementation concern

Evidence:
- `design/auth.md:259`-`design/auth.md:264` defines fixed purpose TTLs: `ClientAuthCertificate` = 24h, `CodeSigningCertificate` = 7d, `AdminCertificate` = 1h.
- `design/auth.md:282`-`design/auth.md:287` then says regular devices receive `ClientAuthCertificate` + `CodeSigningCertificate` for 30–180 days.
- `design/auth.md:969`-`design/auth.md:973` later generalizes both client and code-signing certificate TTLs to 15 min–180 days.
- `design/auth.md:297` and `specs/security/09-command-source.md:125` define online CRL retention as `max_certificate_ttl + max_clock_skew + federation_revocation_cache_ttl + operational_grace`.

Why this matters for performance:
- The effective online CRL window differs by two orders of magnitude depending on which TTL table implementers follow: 7 days vs 180 days.
- CRL storage, cache warmup, cache-miss frequency, and emergency CA rotation cost are all tied to `max_certificate_ttl`; ambiguous TTLs make capacity planning impossible.
- This is a classic PKI operational failure mode: short-lived certs are cheap to validate and clean up; long-lived certs shift the cost into revocation infrastructure.

Recommendation:
- Pick one authoritative TTL policy table and make all other tables reference it.
- Separate `regular_device` client-auth TTL from code-signing TTL if they intentionally differ.
- Add an explicit online CRL sizing formula or budget using the chosen `max_certificate_ttl`.

### A2 — High — Deploy nonce API is required by the security flow but missing from MCP tool inventories

Category: API gap / deferred implementation concern

Evidence:
- `specs/security/09-command-source.md:99` says `deploy_nonce` is obtained through MCP `swarm_deploy_challenge`.
- `specs/security/09-command-source.md:105` requires the client to call `swarm_deploy_challenge` before deploy.
- `specs/security/09-command-source.md:256`-`specs/security/09-command-source.md:274` defines nonce TTL and the compile-time handoff to a 30-minute `deploy_token`.
- `design/interface.md:22`-`design/interface.md:26`, `design/auth.md:610`-`design/auth.md:629`, and `specs/reference/mcp-tools.md:22`-`specs/reference/mcp-tools.md:70` list MCP/auth tools but do not include `swarm_deploy_challenge` or a deploy-token endpoint/result shape.

Why this matters for performance:
- The nonce path is not just a security detail; it determines whether deploy upload, signature verification, WASM validation, and compilation can be pipelined without retry storms.
- If implementers discover this late, they may fold nonce issuance into `swarm_deploy`, forcing large WASM uploads to fail after expensive work when nonce/CRL/signature checks should have failed early.
- The specified `compile time > nonce TTL -> deploy_token` branch is performance-critical but has no public API contract, making client retry behavior ambiguous.

Recommendation:
- Add `swarm_deploy_challenge` to `design/interface.md`, `design/auth.md`, and `specs/reference/mcp-tools.md`.
- Define whether `deploy_token` is returned by `swarm_deploy`, an async SSE event, or a separate polling endpoint.
- State the intended validation order: nonce/cert/signature before accepting or compiling the 5 MB WASM body wherever streaming transport allows it.

### A3 — Medium — Per-request certificate-chain verification is specified, but cache boundaries are not

Category: deferred implementation concern / API gap

Evidence:
- `design/auth.md:301`-`design/auth.md:329` requires every sensitive MCP/deploy/admin request to carry `Swarm-Certificate-Chain`, timestamp, nonce, and Ed25519 signature, then verifies chain, usage, signature, nonce, scope, and audience.
- `specs/security/03-mcp-security.md:163`-`specs/security/03-mcp-security.md:185` repeats this as the MCP/Agent main path.
- `specs/security/03-mcp-security.md:270`-`specs/security/03-mcp-security.md:283` allows 50 read calls/tick per player, 500 AI players per engine, and 1000 concurrent MCP connections.
- `design/tech-choices.md:178` notes Ed25519 verification speed is ~30k/s, but only for signature verification; it does not budget certificate-chain parsing, CRL checks, nonce storage, scope checks, or FDB/cache round trips.

Why this matters for performance:
- The nominal MCP ceiling can reach 25,000 read requests/tick for 500 AI players before admin/replay/browser traffic.
- Ed25519 alone may be acceptable, but chain deserialization, CRL lookup, nonce write/check, and per-request authorization can dominate latency if repeated for every JSON-RPC call.
- New implementers may read “Gateway is stateless” and miss the need for a local verified-certificate/session cache with revocation-aware invalidation.

Recommendation:
- Define a verified certificate cache keyed by `(certificate_id, issuer_epoch, audience, usage/scope hash)` with max TTL bounded by the smaller of certificate expiry and revocation-cache TTL.
- Clarify that nonce uniqueness still needs a write path, but chain and scope verification should not reparse the full bundle on every hot-path request.
- Add performance counters: cert-cache hit ratio, CRL cache hit ratio, auth-verify p95/p99, nonce-store p95/p99.

### A4 — Medium — Nonce storage is specified as per-request but no shard/cardinality or cleanup budget is given

Category: deferred implementation concern

Evidence:
- `design/auth.md:306`-`design/auth.md:329` requires every signed request to include a nonce and validates that the nonce is unused.
- `design/auth.md:340` sets the replay window default to no more than 60 seconds.
- `design/auth.md:422` stores request nonces at `auth/request_nonce/<certificate_id>/<nonce> -> {created_at, expires_at}`.
- `specs/security/09-command-source.md:253`-`specs/security/09-command-source.md:292` defines deploy nonce state but does not cover the higher-volume generic request nonce path.

Why this matters for performance:
- At 1000 active MCP connections and 50 read requests/tick, nonce writes can become one of the largest auth-domain write streams.
- Keying by `<certificate_id>/<nonce>` is intuitive but can create hot prefixes for highly active agents unless the storage layer or schema deliberately shards by time/hash.
- Cleanup of 60-second nonce windows is operationally small only if TTL expiry/compaction behavior is explicit.

Recommendation:
- Specify whether request nonces live in FDB, Dragonfly, or Gateway-local storage with replication constraints.
- If FDB is used, shard keys by time bucket and nonce hash rather than a single certificate prefix.
- Define cleanup semantics and metrics: nonce writes/sec, duplicate reject count, nonce-store latency, expired-key backlog.

### A5 — Low — PoW defaults are reasonable but can still create UX-driven retry bursts on browsers and agents

Category: UX gap / deferred implementation concern

Evidence:
- `design/auth.md:532`-`design/auth.md:539` sets default `difficulty_bits = 24`, estimated at ~1.5s in Node WASM and ~3s on mobile WASM.
- `design/auth.md:1144`-`design/auth.md:1158` presents the frontend flow as `~1-3s PoW proof`, Web Worker execution, an 8s slow-device prompt, and cancel/retry behavior.
- `design/auth.md:714`-`design/auth.md:720` sets challenge issuance limits at 10/min per IP and 100/min globally, with CSR submit relying on PoW instead of IP/username limits.

Why this matters for performance:
- The Web Worker and progress UI are good, but the cancel path automatically fetches a new challenge. Slow devices or impatient users can turn client-side CPU delay into server-side challenge churn.
- AI agents running in constrained containers may also retry aggressively if the function-call loop times out before PoW completes.

Recommendation:
- Keep the current default, but document client backoff and challenge reuse rules for cancel/retry.
- Add a server-side metric for abandoned challenges and challenge issuance throttling so operators can tune difficulty without guessing.

## Strengths

- The design correctly keeps gameplay execution out of MCP: AI and humans both deploy WASM, so auth verification and MCP request overhead do not enter the per-drone command path (`design/interface.md:66`-`design/interface.md:87`, `specs/security/09-command-source.md:15`-`specs/security/09-command-source.md:20`).
- Deploy-time code-signing semantics are performance-friendly: certificate natural expiry does not invalidate already deployed modules, avoiding mass recompilation or per-tick certificate checks (`design/auth.md:270`-`design/auth.md:276`, `specs/security/09-command-source.md:138`).
- The WASM compile cache explicitly includes validation/security epoch and skips only compilation, not deploy-time verification; this is the right separation between safety and performance (`specs/core/04-wasm-sandbox.md:338`).
- PoW uses client-side work and has explicit browser Web Worker guidance, preventing main-thread blocking in the common frontend path (`design/auth.md:503`-`design/auth.md:527`, `design/auth.md:1153`-`design/auth.md:1159`).
- The system already recognizes cache-miss semantics for CRL lookup (`specs/security/09-command-source.md:121`-`specs/security/09-command-source.md:125`), which is the right foundation once TTL and cache boundaries are made precise.

## Questions/Assumptions

- Assumption: Gateway remains mostly stateless for routing, but may hold bounded local auth caches; if “stateless” forbids any verified-certificate cache, A3 becomes High.
- Assumption: FDB is the source of truth for certificate/revocation state; nonce fast-path storage may still be Dragonfly or Gateway-local if the replay guarantees are documented.
- Question: Is `ClientAuthCertificate` intended to be short-lived (24h) while `CodeSigningCertificate` can be device-profile long-lived, or are both profile-driven up to 180 days?
- Question: Should MCP read calls over a long-lived SSE/HTTP session verify the full certificate chain once per session plus per-message signature/nonce, or fully verify every JSON-RPC request?
- Question: Is `swarm_deploy_challenge` intentionally omitted because deploy nonce is internal to `swarm_deploy`, or should it be a first-class MCP tool?

## Missing

- A single authoritative TTL matrix covering purpose, device profile, renewal policy, and CRL retention impact.
- A documented auth hot-path cache strategy: verified certificate cache, CRL cache, nonce store, invalidation via revocation/security epoch, and metrics.
- Public API contract for deploy nonce issuance and compile-time `deploy_token` continuation.
- Capacity estimates for worst-case MCP auth overhead: 500 players × 50 requests/tick, plus reconnect and deploy bursts.
- Operational runbook checks for auth path saturation: cert-cache hit ratio, nonce write latency, CRL miss rate, abandoned PoW challenges.

## Phase Ordering

1. Normalize the certificate TTL policy before implementation; this determines CRL retention, cache TTLs, and emergency rotation blast radius.
2. Add the deploy challenge/token API contract before wiring `swarm_deploy`; this prevents expensive upload/compile retries from being baked into clients.
3. Design the auth fast path next: verified-cert cache, CRL cache, nonce store schema, invalidation, and metrics.
4. Implement Gateway/MCP auth with load tests at the documented ceilings before enabling high AI-player counts.
5. Tune PoW difficulty and browser/agent retry behavior after observing abandoned challenges and registration latency in staging.
