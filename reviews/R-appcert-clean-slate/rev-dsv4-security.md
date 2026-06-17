# Security Review: Application-Layer Certificate Redesign

**Reviewer:** rev-dsv4-security (DeepSeek V4 Pro)  
**Round:** R-appcert-clean-slate — clean-slate, no prior reviews  
**Date:** 2026-06-17  
**Scope:** Swarm auth redesign — Server CA + CSR + application-layer certificates + canonical request signature  

**Documents reviewed (11 core + 2 cross-ref):**

| Document | Lines | Focus |
|---|---|---|
| `design/auth.md` | 1508 | Primary auth design: CSR, certificate chain, PoW, recovery, federation |
| `design/interface.md` | 115 | MCP tool catalog, deferred command model |
| `design/README.md` | 226 | Architecture overview, design principles |
| `design/tech-choices.md` | 257 | Blake3/Ed25519/FDB/Wasmtime rationale |
| `GETTING-STARTED.md` | 90 | Onboarding flow — includes CA fingerprint pinning step |
| `RUNBOOK.md` | 178 | CA key generation, certificate revocation, disaster recovery |
| `specs/12-gateway-protocol.md` | 171 | Transport auth matrix, WebSocket/REST/MCP security |
| `specs/reference/mcp-tools.md` | 122 | Auth MCP tool surface |
| `specs/security/03-mcp-security.md` | 366 | MCP auth flow, transport split, DNS rebinding defense, scope model |
| `specs/security/09-command-source.md` | 292 | Source-gate model, DeployPayload, cert lifecycle, session/nonce state machine |
| `specs/core/04-wasm-sandbox.md` | 423 | Sandbox OS isolation, Wasmtime config, resource budgets |
| _cross-ref:_ `specs/security/05-visibility.md` | 410 | Visibility oracle defense (referenced by 03, 09, 04) |
| _cross-ref:_ `specs/security/CVE-SLA.md` | 91 | Wasmtime CVE response SLA |

---

## Verdict: CONDITIONAL_APPROVE

**No Critical findings.** The auth redesign is technically sound, well-motivated, and covers an impressive breadth of threat vectors. The certificate model with usage isolation, canonical request signatures, server-authoritative PoW challenges, constant-time user-existence checks, and the clean separation of "certificate expiry != module deactivation" are all excellent design choices that go beyond typical game-server security.

However, **6 High-severity findings** must be addressed before this design can be considered production-ready. They center on: (1) Intermediate CA key protection ambiguity, (2) missing dual-admin authorization for recovery-link generation, (3) a doc inconsistency in the CSR payload format that could cause implementation divergence, (4) Auth Service co-location blurring the security boundary, (5) unauthenticated challenge-request DoS, and (6) missing per-certificate-type TTL configuration. Additionally, 8 Medium and 4 Low findings are provided for hardening.

---

## Top Findings

### High

#### H1: Server Intermediate CA private key storage is underspecified
- **Category:** security gap
- **Evidence:** `design/auth.md` §2 principle "Server Root CA offline" (§3 states Root CA is offline), but the Intermediate CA is described as "online signer, rotating" (§5.1, §3.1). Nowhere in the 11 documents is it specified how the Intermediate CA private key is stored in memory or on disk at runtime.
- **Risk:** The Server Intermediate CA is the most security-critical online component in the entire auth system. If its private key is compromised, the attacker can forge valid certificates for any player, including CodeSigningCertificates and AdminCertificates. §3.1 states "Auth Service 不持有 Server Root CA 私钥" but does not say the same about the Intermediate CA.
- **Required:** Specify key protection mechanism: HSM, encrypted enclave, in-memory-only with reload from encrypted storage, or OS keyring. At minimum, the Intermediate CA private key must never be written to unencrypted disk or appear in logs/audit trails. The emergency rotation runbook in `specs/security/09-command-source.md` §3.4 mentions "Server Intermediate CA 泄露 → bump epoch" but does not describe how to detect the compromise or how to rotate without the Root CA (requires offline operator action). This gap means the response time from compromise detection to effective revocation is undefined.

#### H2: Admin recovery-link generation lacks dual-authorization requirement
- **Category:** security gap
- **Evidence:** `design/auth.md` §11.3 allows any admin with `AdminCertificate` to call `swarm_admin_create_password_reset` and generate a recovery link that resets a user's certificate access. By contrast, `specs/security/09-command-source.md` §2.2 requires **two different admins' Ed25519 signatures** for the Rollback operation.
- **Risk:** A single compromised admin credential can generate recovery links for any user, effectively taking over any account. Admin-generated recovery links target `login_username` (not email), bypassing email verification entirely. The asymmetry between Rollback (dual-sign) and account recovery (single-sign) is inconsistent — account recovery through admin action is at least as sensitive as a rollback, if not more so.
- **Required:** Either (a) require dual-admin signatures for `swarm_admin_create_password_reset`, or (b) require the recovery link to additionally pass through the user's verified email as a second factor (admin generates link + system sends email, both required), or (c) add a mandatory notification + delay (e.g., admin generates link → 24h cooldown before link activates → user notified via all bound channels).

#### H3: CSR payload includes `challenge` field contradicting the "server-authoritative" verification flow
- **Category:** doc inconsistency
- **Evidence:** `design/auth.md` §5.2 CSR payload definition includes:
  ```
  challenge_id: <challenge_id>
  challenge: <server challenge>
  ```
  However, §9.3 explicitly states: "swarm_submit_csr 请求仅提交 challenge_id + nonce + csr_signature，不包含客户端回传的 challenge 或 difficulty." And §10.3 reinforces: "请求中不包含 challenge 和 difficulty 字段 — 服务端从 FDB 读取权威值."
- **Risk:** If an implementer follows the §5.2 CSR format and includes the `challenge` field in the wire protocol, the client could supply a weaker challenge (e.g., replay a known-easy challenge from a different session) and the server might accidentally use the client-supplied value instead of the FDB-authoritative value. This would defeat the PoW's entire purpose. The server-authoritative design in §9.3 is correct; the CSR payload spec in §5.2 must be consistently aligned.
- **Required:** Remove the `challenge:` field from the CSR payload definition in §5.2. The CSR template should only carry `challenge_id` (and optionally `expires_at` for client-side timeout tracking). The authoritative challenge value lives in FDB and is never provided by the client.

#### H4: Auth Service co-location in Engine process blurs security boundary
- **Category:** security gap
- **Evidence:** `design/auth.md` §3.1 states the Auth Service can be "Engine 内或独立服务" and the issue_certificate_bundle interface can be "模块调用或内部 RPC." The threat model in §17.1 does not consider the scenario where a WASM sandbox escape or Engine memory corruption could reach the Auth Service's Intermediate CA signing capability.
- **Risk:** The Engine process runs untrusted WASM code (from potentially malicious players). If Auth Service runs in the same process as the Engine, a WASM sandbox escape (the most valuable exploit target in the entire system) could directly access Intermediate CA signing keys if they are in the same process memory space. The isolation provided by seccomp/cgroup (§04-wasm-sandbox.md) only applies to sandbox worker processes, not to the Engine parent process.
- **Required:** The Auth Service (specifically the Intermediate CA signing component) MUST run in a separate process with no shared memory with the Engine. Even if "模块调用" is allowed for non-signing operations (user lookup, session management), the actual certificate signing path must cross a process boundary. The `issue_certificate_bundle` interface contract should explicitly state: "Certificate signing must execute in a dedicated auth process; Engine process may only call this via internal RPC, never via direct function call."

#### H5: No PoW/rate-limit on unauthenticated challenge requests
- **Category:** security gap
- **Evidence:** `design/auth.md` §10.7 shows challenge application rate-limited at 10/min per IP, but `swarm_register_challenge` has NO parameters — it's an unauthenticated endpoint. An attacker can request challenges from many IPs and never submit a CSR, consuming FDB storage (`auth/challenges/` records) and forcing the FDB TTL cleaner to work harder.
- **Risk:** While §10.7 states "Challenge 申请设轻量 IP 限速防止存储 DoS" with a 10/min per-IP cap, this is only effective against single-IP attacks. A distributed attack from a botnet with 10,000 IPs could create 100,000 challenge records per minute. Each challenge contains 32 bytes of random challenge + overhead, but FDB transaction overhead per record is the real cost.
- **Required:** Add a global challenge generation rate cap (e.g., 1000/min global) in addition to the per-IP cap, or require a lightweight client puzzle (difficulty_bits=8) just to request a challenge. This ensures that even distributed attacks cannot overwhelm FDB's challenge subspace.

#### H6: Single certificate TTL config does not account for type-specific TTLs
- **Category:** API gap
- **Evidence:** `design/auth.md` Appendix C config shows only `certificate_ttl_seconds = 86400` (24h). However, §5.3 defines four certificate types with different TTLs: ClientAuthCertificate (24h), CodeSigningCertificate (7d), AdminCertificate (1h), FederationCertificate (24h). §5.5 also shows device-type-specific TTLs ranging from 15min to 180 days.
- **Risk:** A single `certificate_ttl_seconds` config cannot express the multi-TTL design described in the spec. If an operator sets this to 180 days, AdminCertificates would also get 180-day TTLs (or the implementation would need to hardcode AdminCertificate TTL to 1h regardless of config, making the config misleading). This creates a configuration surface that could accidentally weaken admin certificate security.
- **Required:** Replace the single `certificate_ttl_seconds` with per-certificate-type TTL configs:
  ```toml
  [auth.certificate_ttl]
  client_auth = "24h"
  code_signing = "7d"
  admin = "1h"
  federation = "24h"
  temporary_device_max = "24h"
  managed_device_max = "24h"
  ```

---

### Medium

#### M1: Server-managed private keys lack encryption-at-rest and audit requirements
- **Category:** security gap
- **Evidence:** `design/auth.md` §5.2 defines the `managed_by_server=true` path for user private keys but only specifies constraints on TTL and scope. No mention of encryption-at-rest, access audit, or key rotation for the stored private keys.
- **Risk:** If the FDB `auth/` subspace or server filesystem is compromised, attacker gains user private keys. This is worse than a certificate compromise because private keys can sign new CSRs.
- **Recommendation:** Require that `managed_by_server` private keys are encrypted-at-rest with a key derived from a separate HSM or OS-protected keyring. Log all access to managed private keys to `auth/admin_audit`. Auto-expire managed keys after the shorter of device TTL or 7 days.

#### M2: Email recovery rate-limit can leak email registration status
- **Category:** security gap
- **Evidence:** `design/auth.md` §11.2 implements constant-time dummy operations but also enforces "1 request per 5 min per email" rate limiting. The error code for rate-limited requests is `rate_limited` vs the constant-time `success` for valid+invalid emails.
- **Risk:** An attacker can test emails at 5-minute intervals: if they get `success` for email A, wait 5min, try again and get `rate_limited` → email A is associated with an account. If they get `success` but never hit `rate_limited` → email is not registered.
- **Recommendation:** Return `rate_limited` for all requests from an IP that has exceeded the per-email rate limit, even if the specific email hasn't been rate-limited yet. This makes the rate-limit behavior identical for registered and unregistered emails.

#### M3: Federation revocation cache staleness window (3600s) may be too long
- **Category:** security gap
- **Evidence:** `design/auth.md` §15.6: `revocation_cache_stale_seconds` defaults to 3600s, and the `reject_for_code` fallback still allows login during staleness.
- **Risk:** If a remote world revokes a certificate (e.g., key compromise), an attacker can use the revoked certificate for federated login to other worlds for up to 1 hour after revocation. While code signing and admin are blocked during staleness, login alone still grants a Local ClientAuthCertificate.
- **Recommendation:** Reduce default stale timeout to 600s and add a `/auth/revocations/poll` lightweight endpoint that returns only a merkle root of revocations since a timestamp — enabling near-real-time polling without fetching full CRL.

#### M4: Passkey recovery does not require a second factor when all certificates are lost
- **Category:** security gap
- **Evidence:** `design/auth.md` §11.4 states: "用户丢失所有证书但仍持有 passkey 时，可用 passkey 重新提交 CSR；无需邮箱或管理员介入."
- **Risk:** If an attacker gains access to a user's passkey (e.g., device theft with biometric bypass), and the user has lost all certificates, the attacker can unilaterally recover the account and obtain fresh certificates without any secondary channel notification. Passkey alone becomes the single point of failure for account recovery.
- **Recommendation:** Require at least one additional factor for passkey-only recovery: (a) a 24h delay with notification to bound email, or (b) a recovery password check (if one was set), or (c) require that the user has at least two passkeys registered and both must assert.

#### M5: Browser WebSocket auth dual-path (JWT token OR application certificate) creates ambiguity
- **Category:** API gap
- **Evidence:** `specs/12-gateway-protocol.md` §9 lists Browser WS auth as "Web session token 或 application certificate." The two paths have different security properties: JWT tokens are bearer tokens (anyone with the token can authenticate), while application certificates require possession of the private key to sign each request.
- **Risk:** Implementations or clients may default to the weaker path (JWT) when both are available, undermining the security value of the application certificate model for browser users. The transport auth matrix also lists JWT `aud` binding for Browser but certificate `audience` binding for MCP — different validation logic for the same transport.
- **Recommendation:** Require application certificate for all new Browser connections; allow JWT only as a session-resumption optimization for reconnecting within a short window (e.g., 5 minutes). Make the WebSocket upgrade path prefer certificate chain when available.

#### M6: `Sec-WebSocket-Protocol` misuse for JWT token transport
- **Category:** security gap
- **Evidence:** `specs/12-gateway-protocol.md` §9: "Browser WS token 通过 Sec-WebSocket-Protocol header 传递——不得出现在 URL query string 中." The `Sec-WebSocket-Protocol` header is intended for WebSocket subprotocol negotiation, not for authentication tokens.
- **Risk:** Intermediary proxies, load balancers, and WebSocket libraries may log, modify, or strip the `Sec-WebSocket-Protocol` header. Some proxies limit its length. The spec correctly notes nginx access_log concerns, but the header itself is not designed for auth material. Additionally, multiple Gateways may disagree on subprotocol negotiation.
- **Recommendation:** Use a dedicated custom header (e.g., `X-Swarm-Auth`) for JWT tokens in WebSocket upgrade requests, or use a URL-safe token in the WebSocket path (`wss://host/ws?token=...`) with the constraint that the Gateway MUST strip it from logs. If the token approach is kept, use the `Authorization: Bearer` header during the HTTP upgrade handshake (supported by most WebSocket clients).

#### M7: No periodic review schedule documented for Wasmtime `=30.0` version lock
- **Category:** deferred implementation concern
- **Evidence:** `specs/core/04-wasm-sandbox.md` §2.1 locks Wasmtime to `=30.0` and mentions "CVE 监控：CI 中 cargo audit. 每次 wasmtime 版本升级前人工审查 CHANGELOG." CVE-SLA.md defines response times but not a proactive review cadence.
- **Risk:** Without a scheduled review, the Wasmtime version may drift so far behind that upgrading becomes a multi-version migration with breaking API changes (fuel_consumed_callback removal in ≥30 is already noted). This increases the difficulty of applying security patches under SLA pressure.
- **Recommendation:** Add a quarterly review to the CVE-SLA.md: compare locked version against latest stable, assess migration effort, pre-plan upgrade path. If the locked version falls out of the Bytecode Alliance security support window, upgrade within 30 days.

#### M8: Federated login `challenge_signature` not bound to target world
- **Category:** security gap
- **Evidence:** `design/auth.md` §15.2 step 3: "客户端用 World A 证书对应私钥签名 World B 的 federation challenge." The challenge is server-generated but the federation login payload in §15.3 shows `challenge_signature` without explicit binding to the federation challenge content or the target world_id.
- **Risk:** If the federation challenge is not cryptographically bound to the target world's identity (server_id + world_id), a signed challenge from World B could potentially be replayed to World C if World C also trusts World A's Root CA. The spec says the challenge prevents "证书复制重放" but doesn't fully specify what the challenge contains.
- **Recommendation:** Explicitly define the federation challenge format to include `{remote_server_id, remote_world_id, target_server_id, target_world_id, timestamp, nonce}` in the signed payload. This ensures the challenge signature is only valid for the specific target world.

---

### Low

#### L1: Recovery password can be changed without email re-verification when logged in
- **Category:** security gap
- **Evidence:** `design/auth.md` §11.1: "修改成功后不强制重新登录（现有 session 保持有效）."
- **Risk:** If an attacker gains temporary access to a logged-in session (e.g., unlocked computer, stolen session token), they can change the recovery password, locking the legitimate user out of future recovery. The change does not trigger email notification.
- **Recommendation:** Send an email notification on recovery password change; optionally require email verification if the password change is from a device not previously associated with the account.

#### L2: No GPU/ASIC resistance discussion for blake3 PoW
- **Category:** deferred implementation concern
- **Evidence:** `design/auth.md` §9.1: blake3 with variable difficulty_bits is chosen for PoW. §17.1 threat model lists "批量注册 / DDoS" mitigated by PoW.
- **Risk:** blake3 is extremely fast on specialized hardware. An attacker with a GPU (or multiple GPUs) can solve 24-bit PoW (~16.7M attempts, ~150ms on single CPU core) in significantly less time — potentially microseconds. The current difficulty is calibrated for CPU and may be insufficient against GPU-equipped attackers.
- **Recommendation:** Add to the config: `register_pow_max_parallel` (reject rapid sequential challenge+submit cycles from same target), and monitor submission rates per IP to detect GPU-accelerated attacks. Consider memory-hard PoW (e.g., Equihash) if GPU attacks become prevalent — but note that blake3 is acceptable for initial deployment since the primary goal is rate-limiting, not consensus.

#### L3: Permanently deleted accounts' federation identity mappings are not addressed
- **Category:** doc inconsistency
- **Evidence:** `design/auth.md` §13.1: after 30-day grace period, `login_username` is released for re-registration. §15.4 defines federated player_id as `blake3("federated:" + world_id + ":" + original_player_id)`. No mention of what happens to the `auth/identities/<provider>/<subject>` mapping after permanent deletion.
- **Risk:** If a user deletes their account and the grace period expires, the federation identity mapping could persist in other worlds' FDB instances. If the username is re-registered by a different person, the old federated identity could still be accepted by other worlds (since it maps to the old `original_player_id` which was derived from username).
- **Recommendation:** Specify that permanent deletion must propagate to federation identity mappings: emit a `player_deleted` event that other worlds can consume to invalidate their local federated identity cache for that `(remote_server_id, remote_player_id)` pair.

#### L4: `swarm_delete_account` API surface shows `password OR certificate_signature` but auth.md only documents password flow
- **Category:** doc inconsistency
- **Evidence:** `design/interface.md` §4.1 lists `swarm_delete_account` params as "password 或 certificate_signature." But `design/auth.md` §13.1 only documents the password-based flow. The certificate_signature path is mentioned in neither §13.1 nor §13.3.
- **Risk:** Implementation may only support password-based deletion, leaving certificate-only users (who never set a recovery password) with no way to delete their account. Or implementation may support both paths inconsistently with the auth.md spec.
- **Recommendation:** Document the certificate_signature deletion path in auth.md §13.1: specify the canonical request signature format for account deletion, and require that the signing certificate has `usage=client_auth` and belongs to the player.

---

## Strengths

1. **Usage-isolated certificates** — `ClientAuthCertificate`, `CodeSigningCertificate`, `AdminCertificate`, `FederationCertificate` with distinct TTLs, scopes, and audiences. This is the single most impactful security design decision. Prevents credential reuse across auth contexts.

2. **Canonical request signatures** — Every sensitive request is signed with a structured payload (`SWARM-REQUEST-V1` with method, path, body_hash, timestamp, nonce, certificate_id, player_id, audience). Resistant to MITM, replay, and tampering even over HTTP.

3. **Server-authoritative PoW** — Challenge and difficulty are read from FDB, never accepted from the client. The §9.3 flow specifically refuses client-supplied challenge/difficulty. This closes the PoW downgrade attack vector entirely.

4. **Constant-time user existence checks** — Dummy argon2id for non-existent users, unified `invalid_credentials` error for all recovery failures. Combined with `auth.username_visibility = "private"`, makes user enumeration extremely difficult.

5. **Certificate expiry ≠ module deactivation** — `CodeSigningCertificate` must be valid at deploy time only. Deployed modules continue running after certificate expires. Revocation is a separate security event with configurable response (freeze/rollback/continue). This is the right model for long-running autonomous code.

6. **Transport audience binding** — Certificates and deploy nonces are bound to `{transport, server_id, world_id, player_id}`, preventing cross-transport token replay. The `X-Swarm-Transport` header must be present and match.

7. **Oracle defense in visibility model** — `specs/security/05-visibility.md` §10 comprehensively closes information leaks: `omitted_count` bucketing, `NotVisibleOrNotFound` equivalence class for special attacks, dry-run/simulate result sanitization, competitive world `player_view=full` prohibition.

8. **Dual-admin rollback** — `specs/security/09-command-source.md` §2.2 requires two different admins' Ed25519 signatures for rollback. Set a strong precedent for sensitive admin operations.

9. **Agent proxy security** — Agent-mediated registration returns one-time handoff codes instead of raw credentials. Chat log safety is explicitly designed in (§4.3).

10. **PoW in Web Worker** — Frontend PoW runs off-main-thread with progress display and cancel support (§16.2, Appendix B). Good UX without compromising the anti-abuse mechanism.

---

## Questions / Assumptions

1. **Intermediate CA rotation procedure** — RUNBOOK.md §2 shows `swarm ca intermediate issue` but does not describe the rollout: how are existing valid certificates handled during rotation? Does the new Intermediate CA sign with a new key that clients must fetch before their current certificate expires? Assumption: Intermediate CA rotation produces a transition period where both old and new intermediates are accepted.

2. **Auth Service epoch emergency bump** — `09-command-source.md` §3.4 describes "bump epoch → 所有旧 epoch 证书立即失效 → 强制全量重新认证." How long does this take at scale? If 10,000 players must re-submit CSR, is there a queue/degraded mode? Assumption: epoch bump triggers a force-renew notifications to all connected clients via NATS broadcast.

3. **FDB auth subspace separation from game state** — `design/auth.md` §6.2 uses `auth/` prefix for all auth data. Is `auth/` in a separate FDB cluster or directory layer, or just a key prefix in the same cluster? If the same cluster, a game-state transaction conflict could delay auth operations. Assumption: auth subspace shares the same FDB cluster but uses separate transaction priorities (auth transactions > game state transactions).

4. **Wasmtime `StoreLimitsBuilder` thread safety** — `04-wasm-sandbox.md` §2.2 uses `StoreLimitsBuilder` but Wasmtime ≥30 may require `StoreLimits` to be applied per-`Store` instance. If multiple sandbox workers share a compiled module, is there a risk that one worker's Store limits could affect another? Assumption: each sandbox worker creates its own `Store` with independent limits.

5. **CSR `public_key` normalization** — `design/auth.md` §5.2 states the CSR contains `<normalized public key>` but doesn't define normalization for Ed25519. Is it raw 32-byte, base64, hex, or JWK? Assumption: Ed25519 public key is stored in a canonical binary format (32 bytes raw), serialized as hex or base64 for wire protocol.

---

## Summary

| Severity | Count | Categories |
|---|---|---|
| Critical | 0 | — |
| High | 6 | Intermediate CA key storage, admin recovery missing dual-auth, CSR payload doc inconsistency, Auth/Engine co-location boundary, unauthenticated challenge DoS, single TTL config gap |
| Medium | 8 | Managed key encryption, email rate-limit leak, federation revocation staleness, passkey-only recovery, Browser WS dual-path auth, Sec-WebSocket-Protocol misuse, Wasmtime review cadence, federation challenge binding |
| Low | 4 | Password change notification, GPU PoW resistance, deleted account federation cleanup, delete_account API inconsistency |

The application-layer certificate redesign is a significant security improvement over OAuth2/JWT. The design is internally consistent in all major flows (registration, authentication, deployment, federation). The issues identified are primarily about hardening the implementation boundary (H1, H4), ensuring sensitive admin operations have proportional authorization (H2), and resolving documentation inconsistencies that could cause implementation errors (H3, H6, L4).

All 6 High findings must be addressed before Phase 1 implementation begins. The Medium findings should be resolved during implementation. Low findings can be addressed in post-implementation hardening.
