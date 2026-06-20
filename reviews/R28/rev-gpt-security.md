# R28 GPT Security Closure Verification

Reviewer: GPT Security
Scope: only verifies the R27 fixes requested by task t_7a7afad5 against the provided documents.

## Verdict

PARTIALLY_CLOSED

R27 fixes are substantially present for B3, B5, S-H2, T-H1, and partially for ML-10. S-H1 is not closed: the auth design still explicitly says CSR submission has no extra IP limit and does not define the requested per-IP / ASN / global / semaphore / queue admission controls. ML-11 is not closed: the documents still use `player_id: u64` broadly and I found no 256-bit stable fingerprint / 64-bit runtime id distinction.

## Critical

None.

## High

### S-H1 — CSR admission control: FAIL

Evidence:
- `/tmp/swarm/docs/design/auth.md:260` requires challenge existence, expiry, non-consumption, and valid PoW before CSR issuance; this is necessary but not admission control.
- `/tmp/swarm/docs/design/auth.md:265` says challenge consumption, user update, public key record, and certificate issuance happen in one transaction; again useful atomicity, but not per-source admission.
- `/tmp/swarm/docs/design/auth.md:830` defines rate-limit dimensions for CSR submission / recovery / challenge.
- `/tmp/swarm/docs/design/auth.md:832` shows CSR submission has no per-IP limit (`—`).
- `/tmp/swarm/docs/design/auth.md:834` only lists global protection as PoW.
- `/tmp/swarm/docs/design/auth.md:836` explicitly says CSR submission does not set IP/username limits because PoW itself is rate control.
- `/tmp/swarm/docs/design/auth.md:915` introduces unauthenticated endpoint protection.
- `/tmp/swarm/docs/design/auth.md:921` again says CSR submission is limited only by PoW with no extra IP limit.

Assessment:
- Requested controls were per-IP, ASN, global, semaphore, and queue. I found no CSR-specific ASN limit, no global in-flight cap, no CSR worker semaphore, and no bounded queue/backpressure contract.
- This leaves the original DoS shape open: minimum CSR requests can still force server-side signature / FDB / certificate issuance work after PoW, and distributed sources can bypass single-IP controls because no ASN/global admission exists.

### S-H2 — Refresh token grace hardening: PASS

Evidence:
- `/tmp/swarm/docs/design/auth.md:1222` starts the refresh token rotation contract.
- `/tmp/swarm/docs/design/auth.md:1224` rotates refresh tokens by marking the old token rotated and returning a new token.
- `/tmp/swarm/docs/design/auth.md:1225` defines grace windows: 60s generally, 10s for trusted devices with valid `ClientAuthCertificate`.
- `/tmp/swarm/docs/design/auth.md:1226` requires atomic grace consumption by setting `grace_consumed_at` in FDB.
- `/tmp/swarm/docs/design/auth.md:1227` revokes the session family on abnormal IP/UA grace use.
- `/tmp/swarm/docs/design/auth.md:1232` binds each session to `(player_id, client_public_key)` and requires matching `client_public_key` for `swarm_token_refresh` / `swarm_auth_revoke`.
- `/tmp/swarm/docs/specs/reference/api-registry.md:350` gives `swarm_auth_refresh` a 5/min rate limit keyed per player.
- `/tmp/swarm/docs/specs/reference/api-registry.md:353` gives `swarm_auth_revoke` a 5/min rate limit keyed per admin.

Assessment:
- The requested pieces are present at design level: FDB atomic consumption, IP/UA anomaly handling, client public key binding, and refresh/revoke rate limits. The text says `grace_consumed_at` rather than spelling CAS, but the stated FDB atomic one-time consume is sufficient for closure.

## Medium

### B3 — Sandbox clone / pids.max / ABI consistency: PASS

Evidence:
- `/tmp/swarm/docs/specs/core/04-wasm-sandbox.md:245` allows `clone` only with `CLONE_VM | CLONE_VFORK` and denies `fork` / `execve`.
- `/tmp/swarm/docs/specs/core/04-wasm-sandbox.md:261` sets `pids.max = 16` for Wasmtime/compiler threads.
- `/tmp/swarm/docs/specs/core/04-wasm-sandbox.md:380` repeats the same `clone (仅 CLONE_VM | CLONE_VFORK)` rule in the unified OS hardening table and explicitly says `fork/vfork` are forbidden.
- `/tmp/swarm/docs/specs/core/04-wasm-sandbox.md:387` repeats `pids.max = 16` in the checklist.
- `/tmp/swarm/docs/specs/core/04-wasm-sandbox.md:45` defines a unified ABI result for trap/OOM/timeout/partial-output: discard the player’s tick output, record TickTrace reason, and emit no command.

Assessment:
- The duplicate sandbox table and unified checklist now agree on clone and `pids.max`. ABI failure semantics are explicitly unified.

### B5 — CodeSigningCert TTL / CRL semantics: PASS

Evidence:
- `/tmp/swarm/docs/design/auth.md:274` defines `CodeSigningCertificate` TTL as 30–180 days, default 30d, configurable by `world.toml`.
- `/tmp/swarm/docs/design/auth.md:284` requires new deploy/update submissions to use an unexpired, unrevoked `usage=code_signing` certificate.
- `/tmp/swarm/docs/design/auth.md:285` says successful deployments continue after certificate natural expiry.
- `/tmp/swarm/docs/design/auth.md:287` says certificate revocation is a security event and server action depends on revocation reason.
- `/tmp/swarm/docs/specs/security/03-mcp-security.md:57` requires deploy verification of chain, usage, scope, submit-time unexpired/unrevoked status, and signature.
- `/tmp/swarm/docs/specs/security/03-mcp-security.md:59` repeats that natural expiry after deployment does not affect already deployed modules.
- `/tmp/swarm/docs/specs/security/03-mcp-security.md:60` repeats revocation reason handling.
- `/tmp/swarm/docs/specs/core/04-wasm-sandbox.md:343` aligns module cache semantics: cache skip does not skip verification; deploy submission verifies CodeSigningCertificate unexpired/unrevoked; natural expiry after deployment does not terminate WASM.

Assessment:
- TTL and CRL/expiry semantics are now consistent across auth, MCP security, and WASM sandbox cache semantics.

### T-H1 — Seed lifecycle Arena / World split: PASS

Evidence:
- `/tmp/swarm/docs/specs/core/01-tick-protocol.md:260` introduces the R27 T-H1 seed lifecycle/leakage section.
- `/tmp/swarm/docs/specs/core/01-tick-protocol.md:264` states the split: Arena uses Commit-Reveal, World uses Operator Seed-Bump.
- `/tmp/swarm/docs/specs/core/01-tick-protocol.md:271` through `/tmp/swarm/docs/specs/core/01-tick-protocol.md:284` describe Arena generation, commitment exposure, hidden in-match seed, post-match disclosure, and audit verification.
- `/tmp/swarm/docs/specs/core/01-tick-protocol.md:287` through `/tmp/swarm/docs/specs/core/01-tick-protocol.md:313` describe World seed-bump, anomaly detection, seed archival, and optional rollback.
- `/tmp/swarm/docs/specs/core/01-tick-protocol.md:315` through `/tmp/swarm/docs/specs/core/01-tick-protocol.md:323` give a unified lifecycle table distinguishing Arena and World.

Assessment:
- The requested Arena/World split-mode lifecycle is recorded clearly enough to close T-H1.

### ML-10 — CRL stale default reject_for_code_and_login: PARTIAL

Evidence:
- `/tmp/swarm/docs/design/auth.md:1294` still shows the example config default as `revocation_fallback = "reject_for_code"`.
- `/tmp/swarm/docs/design/auth.md:1296` adds the R27 ML-10 recommendation that the default should upgrade to `reject_for_code_and_login`.
- `/tmp/swarm/docs/design/auth.md:1338` defines `reject_for_code` as rejecting code-signing when CRL is stale while still allowing login.
- `/tmp/swarm/docs/design/auth.md:1394` again says `"reject_for_code"` is the default and ordinary login can be accepted short-term.

Assessment:
- The requested recommendation exists at line 1296, so the advisory was added.
- However, it conflicts with the surrounding example/default text that still names `reject_for_code` as default. Closure is therefore partial, not full.

### ML-11 — player_id 64-bit vs 256-bit fingerprint distinction: FAIL

Evidence:
- `/tmp/swarm/docs/design/auth.md:109` uses `player_id: u64` in certificate bundle issuance.
- `/tmp/swarm/docs/design/auth.md:521` defines `player_id` as a u64 deterministic hash.
- `/tmp/swarm/docs/design/auth.md:527` derives local `player_id` by taking low 64 bits from Blake3.
- `/tmp/swarm/docs/design/auth.md:528` derives federated `player_id` as u64.
- `/tmp/swarm/docs/specs/security/03-mcp-security.md:47` lists certificate `player_id: u64`.
- Search for `fingerprint` / `identity_fingerprint` / `certificate_fingerprint` found only certificate/root/intermediate/server fingerprints and no stable 256-bit identity fingerprint distinction.

Assessment:
- The documents still conflate identity with a 64-bit runtime/player id. I found no R27 text distinguishing a 64-bit runtime `player_id` from a 256-bit collision-resistant identity fingerprint.
- This leaves collision/domain-separation ambiguity for certificates, federation, audit, and long-lived identity references.

## Informational

- `/tmp/swarm/docs/specs/reference/api-registry.md:1` to `/tmp/swarm/docs/specs/reference/api-registry.md:5` states API Registry is generated from IDL and is the single source for API contracts. I therefore did not treat missing CSR admission details in the registry alone as proof of failure; the failure is based on explicit contradictory `auth.md` text.
- `/tmp/swarm/docs/design/auth.md:1296` is inside a TOML fenced block immediately after `revocation_fallback = "reject_for_code"`. This formatting makes the R27 ML-10 note visually look like config/comment content rather than a normative policy section, which increases implementation ambiguity.

## New Document Conflicts

- High: CSR admission control conflict. `auth.md` says CSR has no IP/username limit and only PoW rate control at `/tmp/swarm/docs/design/auth.md:836` and `/tmp/swarm/docs/design/auth.md:921`, directly conflicting with the R28 verification target requiring per-IP / ASN / global / semaphore / queue admission controls.
- Medium: CRL stale fallback conflict. `auth.md` recommends `reject_for_code_and_login` at `/tmp/swarm/docs/design/auth.md:1296`, but the example/default and later federation text still use `reject_for_code` at `/tmp/swarm/docs/design/auth.md:1294`, `/tmp/swarm/docs/design/auth.md:1338`, and `/tmp/swarm/docs/design/auth.md:1394`.
- Medium: identity-width ambiguity. `auth.md` and `03-mcp-security.md` continue to expose only `player_id: u64` for certificate/identity contexts, while no 256-bit identity fingerprint contract is documented.
