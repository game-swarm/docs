# R-appcert-R2 Security Review — DeepSeek V4 Pro

**Profile**: rev-dsv4-security
**Date**: 2026-06-18
**Scope**: Clean-slate independent review of 25 design documents
**Reviewed**: DESIGN.md(README), auth, engine, gameplay, interface, modes, tech-choices, 01-tick-protocol, 02-command-validation, 04-wasm-sandbox, 07-world-rules, 03-mcp-security, 05-visibility, 09-command-source, CVE-SLA, 06-feedback-loop, 08-api-idl, commands, host-functions, mcp-tools, 12-gateway-protocol, T2-incremental-snapshot, T3-shard-protocol, GETTING-STARTED, RUNBOOK

---

## Verdict: CONDITIONAL_APPROVE

The design demonstrates strong security architecture across all reviewed domains. No Critical findings. 4 High, 6 Medium, 4 Informational findings. All High findings are design-level concerns with clear remediation paths; none require fundamental re-architecture.

---

## Findings

### High Severity

#### H1 — Server Intermediate CA Private Key Storage Requirements Underspecified

**Source**: auth.md §3.1
**Finding**: The document states the Intermediate CA private key "应存储于 HSM/KMS 或等效安全环境；最低要求为 0600 权限的独立文件系统". The Intermediate CA is an **online signing key** — if compromised, the attacker can issue valid application-layer certificates for any player_id with any scopes (including admin).

**Risk**: An attacker with Intermediate CA access can:
- Forge ClientAuthCertificate for any player → impersonate any player
- Forge CodeSigningCertificate for any player → deploy malicious WASM in their name
- Forge AdminCertificate → full administrative control
- The Server Root CA remains offline (good), but Intermediate CA compromise is near-equivalent to full compromise during its validity window

**Remediation**: Strengthen language from "should" to "MUST" for production: "Production deployments MUST use HSM/KMS. File-system storage (0600) is acceptable ONLY for development/staging." Add a RUNBOOK entry for Intermediate CA rotation procedure with target RTO < 1h.

---

#### H2 — Admin Recovery Link Dual-Authorization Not Reflected in MCP Tool Signature

**Source**: auth.md §11.3
**Finding**: The design explicitly states admin-generated recovery links require dual authorization: "需要两个不同 admin 的确认——第一个 admin 发起请求，第二个 admin 在 5 分钟内确认。单 admin 无法独立完成恢复链接生成。" However, the `swarm_admin_create_password_reset` MCP tool signature shows a single call with no second-admin confirmation parameter. There is no `swarm_admin_confirm_password_reset` tool visible in the spec.

**Risk**: If the implementation does not enforce the 2-person rule at the Auth Service level (as opposed to just documenting it), a single compromised admin or rogue operator can:
- Generate recovery links for any account
- Bypass all user-controlled recovery factors (password, passkey, email)
- Take over any player account including their WASM deployment slots

**Remediation**: Add an explicit `swarm_admin_confirm_password_reset` MCP tool (or `swarm_admin_create_password_reset` with a `confirm` phase) to the MCP tools manifest. The two-phase protocol must be enforced at the Auth Service level — the first admin's request creates a pending record, the second admin's confirmation triggers the actual reset token generation. Add integration tests that verify single-admin requests are rejected.

---

#### H3 — Snapshot Truncation Sort-and-Truncate Deterministic Guarantee Has Unverified Edge Cases

**Source**: 01-tick-protocol.md §2.3
**Finding**: The snapshost truncation guarantees that `sort_and_truncate` results are deterministic given `(tick_state, player_visibility_fingerprint)`. The sort key is `(distance_to_drone, entity_id)` within each bucket. However, `distance_to_drone` depends on which drone's position is used as reference. The document says "以 drone 当前位置到实体的曼哈顿距离计算" but does not specify **which drone** when a player has multiple drones.

**Risk**: If the reference drone selection is not deterministic (e.g., iteration order over a HashSet), the truncation result may differ between replay and original execution, breaking replay determinism.

**Remediation**: Specify the reference point as "the player's drone with the smallest entity_id among those in the current room, falling back to the smallest entity_id across all drones." This makes the reference point deterministic and independent of collection order.

---

#### H4 — Pathfinding Cache-Miss DoS Returns Empty Path, Breaking Bot Determinism

**Source**: 04-wasm-sandbox.md §8, 01-tick-protocol.md §2.3
**Finding**: When `path_find cache_miss > 50` in a single tick, "该 tick 后续 path_find 返回空路径". An attacker can exploit this by:
1. Deploying many drones that each call `path_find` with unique (from, to) pairs in early ticks to exhaust the cache-miss budget
2. The victim's bots in later execution order receive empty paths → their entire strategy fails for that tick

The problem compounds with the per-player shuffle order: if the attacker happens to execute before the victim, the victim gets empty paths. If the victim executes first, they get valid paths but the attacker still degrades them.

**Risk**: This creates a non-deterministic DoS vector where identical WASM code produces different results depending on execution order relative to an attacker. A coordinated attacker can reliably degrade or disable any pathfinding-dependent bot.

**Remediation**: Instead of returning an empty path, return a straight-line approximation (Bresenham line) or the last valid cached path with a `PathDegraded` flag. The bot can then decide whether to use the degraded path. This preserves functionality under attack while maintaining deterministic behavior — the degraded path is a function of (from, to) and terrain, not execution order.

---

### Medium Severity

#### M1 — CSR Payload Contains Client-Supplied Challenge Field (Defense-in-Depth)

**Source**: auth.md §5.2, §9.3
**Finding**: The CSR payload format includes `challenge: <server challenge>` as a field, but §9.3 correctly specifies that the server reads the authoritative challenge from FDB. If any code path (WASM, MCP, or SDK) inadvertently validates against the client-supplied challenge value instead of the FDB-stored value, a challenge substitution attack becomes possible.

**Risk**: Low probability (design is correct) but high impact if implemented incorrectly — attacker could solve a low-difficulty challenge and inject it in place of the server's high-difficulty challenge.

**Remediation**: Remove `challenge` and `expires_at` from the CSR payload format entirely — the server already has these values from FDB. Only `challenge_id` is needed. If backward compatibility requires keeping them, add a code comment: "SERVER-SIDE VALIDATION: challenge and expires_at are read from FDB, NOT from this CSR. These fields exist for client reference only."

---

#### M2 — Refresh Token Rotation Grace Period Too Long

**Source**: auth.md §14.1
**Finding**: Refresh token rotation allows the old token to be accepted once within a 5-minute grace period after rotation. This creates a 300-second window where a stolen token remains usable even after the legitimate user has rotated it.

**Risk**: An attacker who exfiltrates a refresh token (e.g., from browser localStorage via XSS, or from AI agent chat log leakage) can race with the legitimate user during the grace period. Combined with the 30-day token TTL, an attacker with periodic access to the victim's token store can maintain indefinite access.

**Remediation**: Reduce grace period to 30 seconds (or configurable, minimum 30s). The purpose of the grace period is to handle network race conditions (concurrent refresh + new request), which resolves in milliseconds, not minutes. 30 seconds is generous for network latency while minimizing the attack window.

---

#### M3 — Rhai Epoch Bump Has No Automated Re-Signing Tooling

**Source**: 07-world-rules.md §5.1
**Finding**: When the Rhai mod epoch is bumped, "所有旧签名失效，需重新签名". The document describes `swarm mod sign` for individual signing but no batch re-signing workflow. In an emergency scenario (mod author key compromise), the server operator must manually re-sign every `.rhai` file with a new trusted key, which could take significant time for worlds with many mods.

**Risk**: During the re-signing window, all mods are disabled, potentially breaking the game world's rules. An operator under time pressure might skip signature verification (if the code allows it) or make errors.

**Remediation**: Add a `swarm mod resign-all --world <world> --key <new_key>` command that batch-re-signs all installed mods with a new key, updates `.sig` files, and updates `trusted_keys` in world.toml atomically. Document this in RUNBOOK §2 (密钥轮换).

---

#### M4 — Dragonfly Nonce Storage Has 300s Replay Window Post-Crash

**Source**: auth.md §10.8
**Finding**: The design acknowledges "崩溃语义: TTL 窗口内可重放；窗口过后 nonce 过期 → 重放被拒绝." For high-value operations (admin certificate issuance, certificate renewal, recovery flow), a 300-second replay window after a Dragonfly crash could allow an attacker who captured authenticated requests to replay them after recovery.

**Risk**: Low probability (requires Dragonfly crash + captured traffic), but high-value operations are affected. The window is bounded at 300s and collapses after TTL expiry.

**Remediation**: For high-value operations (admin, recovery, certificate renewal), use a challenge-response pattern instead of simple nonce-as-TTL. The challenge `Blake3(account_id || server_seed || timestamp)` as already described for admin operations should be extended to certificate renewal and recovery flows. This eliminates the post-crash replay window entirely.

---

#### M5 — CodeSigningCertificate Compromise Has No Automatic Detection

**Source**: auth.md §5.4, 09-command-source.md §3
**Finding**: If a CodeSigningCertificate's corresponding private key is compromised but the compromise goes undetected, the attacker can deploy WASM modules under the victim's identity indefinitely — the certificate's natural expiry does not invalidate already-deployed modules, and the attacker can renew the certificate (proving key possession). There is no anomaly detection for sudden WASM module changes from a player.

**Risk**: A compromised key can be used to deploy malicious WASM that drains a player's resources, attacks their own buildings, or feeds intelligence to an opponent. This could go undetected unless the victim manually reviews deployment history.

**Remediation**: Add an optional notification system: when a new WASM module is deployed for a player, emit an event (SSE/WebSocket) to the player's active sessions. This is analogous to "new login from new device" emails. Players can then detect unauthorized deployments. Add to MCP: `swarm_subscribe_events` with `deploy` event type.

---

#### M6 — Federation CRL Sync 60s Interval Creates Revocation Latency

**Source**: auth.md §15.2a
**Finding**: Federation CRL sync runs at 60-second intervals. If World A revokes a player's certificate, World B may continue to accept it for up to 60 seconds (plus network latency). An attacker who knows a certificate is about to be revoked has a 60-second window to exploit the federation trust.

**Risk**: Low — the attacker must also pass the federation challenge-signature test (proving possession of the corresponding private key). However, if the revocation reason is `key_compromise`, the attacker has both the certificate AND the private key.

**Remediation**: For `key_compromise` revocations, consider adding a push-based notification from the revoking world to trusted federated worlds (via a dedicated NATS topic or HTTP webhook). This reduces the window from 60s to near-real-time. The pull-based sync remains as fallback.

---

### Informational

#### I1 — PoW Difficulty Static at 24 bits

The default `difficulty_bits = 24` (~17M attempts) is reasonable for 2026 hardware. However, the document acknowledges hardware-improvement risk. Recommend adding a CRONJOB or periodic review reminder: "Re-evaluate PoW difficulty annually against current single-core BLAKE3 benchmarks."

#### I2 — FDB Transaction Retry Limit of 3

The 3-retry limit with tick abandonment and fuel refund is a sound design. The RUNBOOK correctly identifies "FDB commit 连续失败 ≥3 次" as CRITICAL requiring operator intervention. No change needed.

#### I3 — Sandbox Relaxed Mode Correctly Gated

04-wasm-sandbox.md §9.5 correctly prevents `sandbox.relaxed = true` in production: "引擎启动时检查配置，若为 true 且 world.mode != development → 拒绝启动." This is correctly designed. Add to CI: a test that verifies this startup check cannot be bypassed via config parsing edge cases.

#### I4 — HTTP Insecure Transport TOFU Pinning Window

auth.md §5.7 correctly documents the TOFU MITM risk on first connection. This is an inherent limitation of TOFU models and is adequately disclosed. No change needed.

---

## Bright Spots

The following design elements deserve explicit commendation:

1. **Certificate Usage Isolation** — ClientAuth vs CodeSigning vs Admin as separate certificate types with distinct TTLs and scopes is excellent defense-in-depth. A stolen Web session token cannot be used to deploy code; a stolen code-signing cert cannot be used for admin operations.

2. **Deferred Command Model** — WASM modules return JSON commands rather than calling mutating host functions. All state changes flow through a single validation pipeline. This eliminates an entire class of WASM sandbox escape-to-game-state attacks.

3. **Oracle Defense** — The systematic approach to closing information-leak oracles is thorough: unified rejection codes (`NotVisibleOrNotFound`), `omitted_count` bucketing, and three-way equivalence for Overload results. This is rare in game engine designs.

4. **Overload Anti-Permanent-Lockout Proof** — The mathematical proof demonstrates that no coalition of attackers can permanently lock a target's fuel budget. This level of rigor in game balance security is commendable.

5. **Single Visibility Function** — `is_visible_to(entity, player_id, tick)` as the sole authority for all output surfaces (WASM snapshot, MCP, WebSocket, REST, replay) eliminates visibility bypass bugs.

6. **Per-Tick Sandbox Fork** — Each tick forks a fresh sandbox worker, executes one player's WASM, then kills the process. This prevents cross-tick state leakage, memory accumulation, and persistent compromise.

7. **Rhai Mod Signature Verification** — Ed25519 signatures required for all `.rhai` files, with no "allow unsigned" mode. Combined with epoch bump for emergency key rotation, this is a solid trust model for server-side scripting.

8. **Admin Rollback Requires Dual Authorization** — Rollback operations require two different admin Ed25519 signatures. This prevents single-admin abuse of the most powerful operation in the system.

9. **Comprehensive Threat Model** — auth.md §17.1 enumerates 16 specific threats with mitigations. This level of threat modeling clarity is excellent.

10. **CVE-SLA with Defined RTO** — The Wasmtime CVE response SLA defines concrete timelines (24h Critical, 72h High) with rollback procedures. This operationalizes security.

---

## Summary

| Severity | Count | Key Issues |
|----------|-------|------------|
| Critical | 0 | — |
| High | 4 | H1: Intermediate CA key storage; H2: Admin recovery dual-auth MCP gap; H3: Snapshot truncation reference drone ambiguity; H4: Pathfinding cache-miss DoS returns empty path |
| Medium | 6 | M1: CSR challenge field; M2: Token grace period; M3: Rhai re-sign tooling; M4: Nonce post-crash replay; M5: CodeSigning compromise detection; M6: Federation CRL latency |
| Informational | 4 | PoW difficulty review cycle; FDB retry limit; Sandbox relaxed mode gate; TOFU pinning window |

All findings have clear, actionable remediations. None require fundamental architectural changes. The design is production-ready for Phase 1 implementation with the High findings addressed.
