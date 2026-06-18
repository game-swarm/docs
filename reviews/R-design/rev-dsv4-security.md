# Security Review — DeepSeek V4 Pro Clean-Slate

**Reviewer**: rev-dsv4-security (DeepSeek V4 Pro)  
**Date**: 2026-06-18  
**Scope**: All 7 design documents (README, auth, engine, gameplay, interface, modes, tech-choices)  
**Methodology**: Clean-slate read of design documents only — no code, no prior reviews. Design-phase review: no phased-implementation considerations.

---

## Verdict: CONDITIONAL_APPROVE

The architecture is fundamentally sound — application-layer certificate model with usage isolation, PoW anti-abuse, deferred command integrity, fuel metering fairness, and deterministic replay are all well-conceived. Six critical/high findings must be addressed before Phase 1 implementation begins, but none are architectural showstoppers.

---

## Findings

### Critical (1)

**C1 — Admin recovery dual-authorization is specified in prose but has no implementation contract**

- **Source**: `auth.md` §11.3: "双人授权：生成恢复链接属于敏感管理操作，需要两个不同 admin 的确认——第一个 admin 发起请求，第二个 admin 在 5 分钟内确认。单 admin 无法独立完成恢复链接生成。"
- **Problem**: This is the single most powerful admin action — it can recover ANY account, bypassing all user-held credentials. The dual-auth requirement is described in one bullet point but:
  1. The implementation scope (§18.1) does not list any dual-auth workflow state machine component
  2. No state model is defined: what happens if the second admin rejects? What if no second admin is available (single-admin deployment)? What's the timeout behavior?
  3. The FDB schema (§6.2) has no table for pending dual-auth requests
  4. Test strategy (§19) has no dual-auth test cases
- **Severity**: Critical — without an enforced, tested dual-auth workflow, a single compromised AdminCertificate could reset every account on the server.
- **Recommendation**: Add a dedicated §11.3a defining the dual-auth state machine (proposed→approved/rejected/expired), FDB schema (`auth/admin_dual_auth/<request_id>`), timeout (5 min as stated), and fallback for single-admin deployments (either disable admin recovery entirely, or require offline Root CA signature). Add corresponding test cases.

### High (4)

**H1 — Server Intermediate CA private key storage is advisory-only, no engine enforcement**

- **Source**: `auth.md` §3.1 table lists HSM/soft-HSM/file-0600 as tiered options but these are operator runbook guidance, not engine-enforced policy.
- **Problem**: The Intermediate CA is the online signer that issues all player certificates. A server operator who deploys with the weakest option (file 0600) — especially in the common "single node, docker-compose up" quickstart path — has the CA private key on the same filesystem as the engine process. An RCE in the engine or sandbox escape could exfiltrate it.
- **Severity**: High — compromise of Intermediate CA = ability to mint arbitrary certificates for all players on that server.
- **Recommendation**: 
  1. At minimum, require engine startup to verify the CA key is stored in a location the engine process cannot read (e.g., check key path is outside the engine data directory)
  2. Add a startup warning (to stderr and MCP `system_status`) when the CA key is on the same filesystem as the engine
  3. In the MVP quickstart (`docker-compose up`), use an ephemeral in-memory Intermediate CA for development and clearly document that production requires HSM/soft-HSM

**H2 — Snapshot truncation behavior undefined when per-player budget exceeded (Tier 1)**

- **Source**: `engine.md` §3.4 specifies per-player snapshot budget of 256KB and total snapshot 128MB, but no truncation semantics are defined for Tier 1. The snapshot extension roadmap (§3.2, Tiers 1-3) pushes all truncation logic to Tier 2 (modification-set tracking, CoW entity paging).
- **Problem**: When a player has drones/entities that would produce >256KB of snapshot data, the engine must either truncate (losing information, potentially causing WASM to make decisions on incomplete data) or reject (blocking that player's tick). Neither behavior is specified. This is both a correctness issue (what does the WASM see?) and a DoS surface (players could deliberately spawn configurations that hit the budget edge case).
- **Severity**: High — undefined behavior on a per-tick hot path boundary that every player interacts with.
- **Recommendation**: Define Tier 1 truncation semantics explicitly:
  1. Priority ordering for what stays in snapshot when budget exceeded (e.g., own drones first, then visible entities by distance)
  2. A `truncated: bool` flag in the snapshot so WASM code can branch on incomplete data
  3. A `snapshot_truncation_count` metric to detect players frequently hitting the budget

**H3 — Rhai mod trust boundary depends entirely on server operator; no defense-in-depth against malicious mods**

- **Source**: `gameplay.md` §8.7: "Rhai 模组在引擎进程内运行——服主安装的模组是受信代码。不引入进程隔离的复杂性和性能开销。"
- **Problem**: The capability allowlist (§8.7) gives Rhai mods significant power: `damage_entity`, `deduct_resource`, `set_entity_flag`, `emit_event`. A malicious or buggy mod can damage entities, drain resources, or set arbitrary flags (including `immune_*` immunities). The safety net is AST node budgeting and auto-disable after 10 consecutive overruns — but an attacker could craft a mod that stays under the budget while doing maximum damage (e.g., targeting specific players with small per-tick deductions that accumulate).
- **Severity**: High — a compromised mod repo or social-engineering attack on a server operator can compromise the entire world's integrity.
- **Recommendation**:
  1. Make `checksum` (content hash) in `mods.lock` required, not optional
  2. Add a "mod review mode" where new mod versions run in dry-run for N ticks with actions logged but not applied
  3. Consider a `max_per_player_per_tick` cap on resource deduction/damage per mod
  4. Document the threat model explicitly: server operators should treat mod installation with the same care as code deployment

**H4 — Federation CRL stale-state fallback permits revoked certificates during network partition**

- **Source**: `auth.md` §15.2a, `revocation_fallback` policy with options `reject_for_code` (default), `reject_all`, `allow_with_warning`.
- **Problem**: If a remote world becomes unreachable for an extended period, the default `reject_for_code` still allows federated login using certificates that may have been revoked on the source world. An attacker who compromises credentials on World A, gets them revoked, but then uses them on World B during a network partition could gain access. The `allow_with_warning` option is even more permissive.
- **Severity**: High — cross-world trust is the hardest security problem, and the fallback defaults to availability over security.
- **Recommendation**: 
  1. Change the default `revocation_fallback` to `reject_all` — availability can be restored by the operator when they've confirmed the remote world is trustworthy
  2. For federated login during CRL stale state, require an additional local PoW challenge (the remote certificate alone isn't sufficient)
  3. Add a maximum stale window (e.g., 24h) after which ALL federation trust is suspended regardless of policy

### Medium (7)

**M1 — Dragonfly nonce TTL of 300s creates a 5-minute replay window on crash**

- **Source**: `auth.md` §10.8: "Nonce 防重放不写 FDB。使用 Dragonfly SETNX TTL... TTL 窗口内可重放"
- **Problem**: If Dragonfly crashes or restarts, all in-flight nonces within the 300s TTL are lost. An attacker who captured a signed request in that window can replay it successfully. The design correctly identifies this risk but for MCP queries (reads) this is acceptable. However, the nonce storage section doesn't distinguish between read-only MCP queries and mutating operations — do any mutating MCP operations use Dragonfly nonces?
- **Severity**: Medium — limited to replay within TTL window and only after Dragonfly failure.
- **Recommendation**: Explicitly categorize which MCP operations use Dragonfly nonces vs FDB atomic operations. All mutating operations should use FDB atomic checks. Add a `nonce_source` field to the audit log so replays can be traced.

**M2 — Refresh token rotation grace period allows 60s replay window**

- **Source**: `auth.md` §14.1: "旧 token 在 rotation 后 60s 内仍可被接受一次（grace period，防竞态）"
- **Problem**: The grace period is a deliberate design trade-off but creates a 60s window where a stolen refresh token remains usable even after legitimate rotation. The design mitigates this with "异常 IP/UA 使用 grace 时触发 session family revoke" — this is good but the IP/UA check can be bypassed if the attacker is on the same network.
- **Severity**: Medium — narrow window, partially mitigated.
- **Recommendation**: Reduce grace period to 10s for all tokens (not just trusted-device). Add a notification to the user ("Your session was refreshed from a new location") when grace is consumed from a different IP.

**M3 — Email binding allows multiple accounts per email (Sybil enablement)**

- **Source**: `auth.md` §12: "一个邮箱可被多个账号绑定（不要求唯一）"
- **Problem**: A single email can be used as recovery for unlimited accounts. Combined with PoW-solved registration (which costs ~$0.0001 per account), an attacker can create thousands of Sybil accounts all recoverable through one email. In World mode this enables economic manipulation (voting, market flooding). The recovery email listing "列出所有关联账号" partially mitigates by making the scope visible.
- **Severity**: Medium — enables Sybil attacks at scale.
- **Recommendation**: Add a configurable `max_accounts_per_email` (default 5). For worlds with competitive elements, allow operators to set this to 1.

**M4 — Pathfinding host function has no per-call budget**

- **Source**: `interface.md` §5.1: `host_path_find(from_x, from_y, to_x, to_y, out_ptr, out_len)` — no complexity budget specified.
- **Problem**: `host_path_find` runs server-side (engine process). A WASM module could request a path between coordinates at opposite extremes of a large world, consuming engine CPU. While fuel metering DOES count host function calls, the engine-side pathfinding computation happens synchronously during the WASM execution window. Multiple players doing this simultaneously could cause tick overrun.
- **Severity**: Medium — tick timing violation risk.
- **Recommendation**: Add a per-call node expansion limit (e.g., 10,000 nodes) to `host_path_find`. Exceeded → return partial path + `PATH_TRUNCATED` error code. Add `pathfind_budget_exceeded` to TickMetrics.

**M5 — No signature verification on mod git repositories**

- **Source**: `gameplay.md` §8.7: mod distribution model is `git clone` from arbitrary URLs. `mods.lock` pins commit hash but the optional `checksum` field provides integrity, not authenticity.
- **Problem**: A compromised git remote (or MITM on git:// protocol) could serve malicious mod code. The commit hash provides integrity (tamper-evident after first clone) but not authenticity (who authored it). There's no GPG signature verification, no mod signing, and checksum is optional.
- **Severity**: Medium — requires compromised git remote or MITM.
- **Recommendation**: Make `checksum` required in `mods.lock`. Recommend (but don't block on) GPG-signed tags. Document that operators should verify mod sources before `swarm mod add`.

**M6 — CSR `certificate_profile` self-declared by client, no server-side override for admin requests**

- **Source**: `auth.md` §5.2: CSR payload includes `certificate_profile: regular_device | temporary_device | managed_device | admin_device`. Server validates that "admin usage 只能由 admin_device profile 请求".
- **Problem**: The server checks that `admin` usage must come with `admin_device` profile — but if a client includes both, the server's validation logic depends on correctly enforcing the conjunction. A bug in the validation (e.g., checking `admin_device` but not the usage) could allow admin certificates to be issued to non-admin profiles. This is a validation ordering dependency risk.
- **Severity**: Medium — code-level validation bug risk, but the design clearly states the constraints.
- **Recommendation**: Add a test case specifically for "admin usage with non-admin profile → rejected". Ensure the validation order is: (1) parse profile, (2) if `admin_device`, require additional authorization (existing admin approval or offline bootstrap), (3) only then check requested usages. Never allow `admin` usage through the default CSR submit path regardless of profile field.

**M7 — WASM snapshot budget exceeded produces no player-visible error**

- **Source**: `engine.md` §3.4: 256KB snapshot per player. When exceeded, what happens?
- **Problem**: Related to H2 but specific to the player experience. If a player's drone distribution causes snapshot truncation, they receive incomplete world data and make decisions on partial information — but there's no mechanism for the WASM to detect this (no `truncated` flag). This could lead to "ghost" entities that exist in the world but aren't in the snapshot, causing commands to fail with mysterious `InvalidTarget` errors.
- **Severity**: Medium — player experience and debuggability.
- **Recommendation**: Add `snapshot_truncated: bool` to the snapshot struct. When true, also include `truncated_entity_count: u32` so the player knows how much data is missing. This is critical for AI agents (MCP path) to make informed decisions.

### Low (4)

**L1 — Admin operations have per-operation cooldowns but no global admin rate limit**

- **Source**: `auth.md` §10.5b: per-operation cooldowns (60s, 10s, 30s) but no global "N admin actions per minute" cap.
- **Recommendation**: Add `admin_global_rate_limit = 10/min` to prevent an attacker with a valid AdminCertificate from cycling through all admin operations rapidly.

**L2 — Dragonfly hot cache unencrypted at rest**

- **Source**: `tech-choices.md` §6: Dragonfly as hot cache. No mention of encryption.
- **Recommendation**: If Dragonfly stores any PII (email? player display names?), document the encryption posture. For MVP with only entity state caching, this is acceptable without encryption.

**L3 — PoW difficulty auto-adjustment may oscillate without hysteresis**

- **Source**: `gameplay.md` §8.2 PoW economic governance: difficulty auto-adjusts based on "近期注册速率、失败率、IP 多样性" but no hysteresis mechanism.
- **Recommendation**: Add `difficulty_adjustment_cooldown = 300s` to prevent rapid oscillation. Use exponential moving average rather than instantaneous rate.

**L4 — Overload attack coordinated by multiple players can drain target to 20% fuel floor**

- **Source**: `gameplay.md` §8 special attacks: Overload has per-target 50-tick cooldown but "不限来源". Multiple attackers can rotate Overload to keep a target permanently at 20% fuel floor.
- **Recommendation**: This appears to be an acceptable gameplay design choice — 20% floor ensures the target isn't completely disabled. Document that this is intentional and accepted.

---

## Strengths

1. **Application-layer certificate model with usage isolation** — `ClientAuthCertificate` ≠ `CodeSigningCertificate` ≠ `AdminCertificate`. This is excellent defense-in-depth: a stolen auth cert can't sign code, a stolen code-signing cert can't perform admin operations. Short TTLs on admin certs (1h) further limit blast radius.

2. **PoW anti-abuse throughout** — Registration PoW (blake3 leading-zero bits, ~150ms), configurable recovery PoW, and the "server-authoritative challenge" pattern (client never supplies challenge/difficulty — server reads from FDB) prevent challenge downgrade attacks. Well-designed.

3. **Deferred command model prevents direct WASM state mutation** — All player actions go through `tick() → Command[]` JSON, validated and applied by the engine in Phase 2a. Host functions are strictly read-only. This is the correct architecture for untrusted code execution.

4. **Deterministic replay as anti-cheat foundation** — `state_checksum` per tick, full replay verification in CI, seed rotation every 10,000 ticks. The PRNG seed shuffle per tick prevents players from gaming execution order. This is comprehensive.

5. **Fuel metering for fair resource accounting** — Wasmtime's native fuel metering (instruction counting, not wall-clock) ensures C players and Python players get equivalent compute per tick. This is the right fairness primitive for a programming game.

6. **Blake3 as single cryptographic primitive** — Hash, XOF (PRNG), and MAC all from Blake3. Reduces dependency audit surface. The `update_with_seek` XOF pattern for per-player per-tick randomness is elegant.

7. **FoundationDB strict serializability** — Per-tick atomic commits guarantee world state consistency. This is the correct choice for a deterministic game engine where partial commits would break replay.

8. **Refresh token rotation with reuse detection** — Rotate on every use, detect abnormal IP/UA on grace period consumption, trigger full session family revoke. This is well above industry average for token security.

9. **Account deletion with 30-day grace period and transfer protocol** — Requires recipient Ed25519 signature confirming transfer acceptance. Well-designed to prevent coercion/social-engineering attacks.

10. **Federation trust layering** — `login` / `login+code` / `observe` trust levels, local certificate re-issuance (remote certs never grant direct local authority), CRL synchronization with stale-state fallback policies. This is the right model for cross-world identity.

---

## Recommendations Summary

| ID | Priority | Action |
|----|----------|--------|
| C1 | Critical | Define and implement dual-auth state machine for admin recovery |
| H1 | High | Enforce (not just recommend) Intermediate CA key isolation |
| H2 | High | Define snapshot truncation behavior for Tier 1 |
| H3 | High | Require mod checksum; add mod dry-run mode |
| H4 | High | Change federation revocation fallback default to `reject_all` |
| M1 | Medium | Categorize MCP ops by nonce storage (Dragonfly vs FDB) |
| M2 | Medium | Reduce refresh token grace to 10s universal |
| M3 | Medium | Add `max_accounts_per_email` config (default 5) |
| M4 | Medium | Add per-call node expansion limit to pathfinding |
| M5 | Medium | Require mod checksum in mods.lock |
| M6 | Medium | Add test for admin usage + non-admin profile rejection |
| M7 | Medium | Add `snapshot_truncated` flag to snapshot |
| L1-L4 | Low | See individual recommendations above |

---

## Review Metadata

- **Documents reviewed**: 7/7 (README, auth, engine, gameplay, interface, modes, tech-choices)
- **Total findings**: 16 (1 Critical, 4 High, 7 Medium, 4 Low)
- **Design quality**: Very high. The auth system in particular is among the best-designed application-level certificate architectures I've reviewed. The deferred command model and deterministic replay are architecturally correct.
- **Most concerning gap**: Admin recovery dual-authorization (C1) — it's the right idea but not yet a real contract.
