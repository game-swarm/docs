# Designer Review: Swarm App-Cert Clean-Slate

**Reviewer:** rev-dsv4-designer (DeepSeek V4 Pro — Game Designer / UX)
**Date:** 2026-06-17
**Scope:** design/auth.md, design/interface.md, design/README.md, design/tech-choices.md, GETTING-STARTED.md, RUNBOOK.md, specs/12-gateway-protocol.md, specs/reference/mcp-tools.md, specs/security/03-mcp-security.md, specs/security/09-command-source.md, specs/core/04-wasm-sandbox.md (plus cross-references)
**Excluded:** reviews/, ROADMAP, .git history, temp progress files
**Focus:** user/AI agent onboarding, device/recovery UX, error recovery, documentation comprehensibility

---

## Verdict

**CONDITIONAL_APPROVE**

The certificate-based auth model is well-designed at the protocol level — the CSR + Server CA + purpose-isolated certificate approach is elegant, the multi-recovery-path design gives users genuine agency, and the agent proxy registration model is a standout UX innovation for non-technical users. However, the onboarding documentation (GETTING-STARTED.md) is dangerously compressed, four critical AI agent onboarding resources referenced in the design don't exist yet, and the deploy flow shown to users doesn't match the actual two-phase protocol defined in the specs. These are documentation/deferred-implementation gaps, not design flaws — the design contracts themselves are sound.

---

## Strengths

1. **Agent proxy registration UX (auth.md §4.3)** — Allowing humans to say "register me on Swarm" to an AI agent and receive a one-time handoff code (not raw secrets) is a genuinely thoughtful UX for non-technical players. The handoff code + browser import flow prevents chat log leakage.

2. **Multi-recovery-path design (auth.md §6, §11, §12)** — Users have three independent recovery paths (passkey, email, admin-generated link), each with explicit security contracts. The constraint that passkey recovery can't issue AdminCertificate is correctly differentiated.

3. **30-day grace period for account deletion (auth.md §13.2)** — Thoughtful UX: prevents permanent data loss from accidents, gives players time to change their minds, and the state machine is clearly documented with a per-operation behavior table.

4. **Server-authoritative PoW (auth.md §9.3)** — `swarm_submit_csr` doesn't accept client-claimed challenge or difficulty — server reads from FDB. This eliminates client-side difficulty spoofing, which is the right call both for security and for keeping the client simple.

5. **Purpose-isolated certificates (auth.md §5.3)** — Separate ClientAuth/CodeSigning/Admin certificates prevent credential misuse. A stolen auth certificate can't sign code; a code-signing certificate can't perform admin operations. The TTL differentiation (24h for auth, 7d for code, 1h for admin) is well-calibrated.

6. **Code-signing expiry semantics (auth.md §5.4)** — Certificate natural expiry doesn't brick deployed modules. This avoids the catastrophic UX of "cert expired → all my drones stop working."

7. **Deterministic player_id from username (auth.md §7.1)** — `blake3("local:" + username) → u64` is clean and reproducible. The collision probability analysis is explicit.

8. **Username visibility configuration (auth.md §7.2)** — Giving deployers control over whether username existence is revealed before PoW solves a real privacy/UX trade-off.

9. **HTTP unsafe transport semantics (auth.md §5.7)** — Explicitly states what HTTP can and cannot protect. The TOFU fingerprint pinning model is well-documented with clear attacker capability boundaries.

10. **Clear what MCP doesn't do (interface.md §4.2, specs/security/03 §4.5)** — Explicit negative space ("no swarm_move/attack/build") prevents scope creep and sets clear expectations for AI agent developers.

---

## Top Findings

### D1 — High — Onboarding flow compressed to opaque shorthand (UX gap)

**File:** GETTING-STARTED.md, lines 67-71
**Category:** UX gap

```markdown
通过 Web UI（`http://localhost:5173`）：
1. 首次访问时确认服务器 Root CA fingerprint
2. 生成本地设备密钥并提交 CSR
3. 点击 **Deploy** → 代码编译为 WASM → 上传到引擎
```

These are the three most security-sensitive user actions in the entire system, compressed into three bullet points with zero explanation:

- **Step 1** ("confirm Root CA fingerprint"): The user is told to confirm a 32-byte fingerprint. What does this look like? Is it a dialog with a hex string? A QR code? A copy-paste comparison against the server admin's published fingerprint? A new user cannot verify this correctly without explicit guidance. Compare this to SSH's "The authenticity of host can't be established" prompt — that prompt explains *why* the user should care. Getting Started doesn't.

- **Step 2** ("generate device key + submit CSR"): This involves browser WebCrypto keypair generation + ~1.5-3s PoW computation in a Web Worker + CSR construction + submission. Getting Started says none of this. A user clicking through will see a ~3s spinner with no context.

- **Step 3** ("Deploy"): The code shows `swarm_deploy(module_bytes, wasm_signature)` but the actual protocol is a two-phase flow: `swarm_deploy_challenge → DeployPayload signature → swarm_deploy(wams_bytes, deploy_payload)`. Getting Started uses an opaque shorthand.

**Recommendation:** Expand Getting Started to include a "First-time setup" section with screen mockups or step-by-step explanation of the fingerprint verification dialog, the PoW progress bar, and the deploy flow.

---

### D2 — High — Four referenced onboarding/auth resources don't exist (deferred implementation concern)

**File:** design/auth.md, lines 167-170
**Category:** deferred implementation concern

Auth.md §4.2 lists four resources as the primary AI agent onboarding path:

```
- `docs/auth/onboarding-ai` — AI agent 首次注册完整流程
- `docs/auth/errors` — 错误码含义与恢复策略
- `schema/auth-tools` — auth MCP 工具的 JSON Schema
- `docs/auth/human-agent-handoff` — 人类通过 agent 代理注册的 handoff 协议
```

None of these files exist in the repository. An AI agent reading auth.md for onboarding instructions has no actual onboarding document to follow. The error codes table (§10.6) exists but lacks recovery strategy guidance per code beyond simple "retry / wait / change username" indicators.

**Recommendation:** Either create these documents before Phase 1 implementation begins, or inline the onboarding flow into auth.md itself as a concrete section rather than a pointer to non-existent docs. The error code recovery strategies should be at minimum a column in §10.6's table.

---

### D3 — Medium — Certificate expiry: no proactive notification UX defined (UX gap)

**File:** design/auth.md, §5.4-5.5 (lines 268-297)
**Category:** UX gap

The certificate model defines TTLs from 15 minutes to 180 days. When a certificate expires, the next authenticated request returns a 401. But there's no mechanism for:

- **Proactive warning**: No API/tool like `swarm_list_certificates` returns `expires_in` or `expiring_soon` flags that a client could use to warn the user.
- **Renewal UX**: The user discovers expiry by getting an auth failure. They then need to remember to call `swarm_renew_certificate`. If they miss the window and their private key is unavailable, they fall into recovery.
- **Agent awareness**: An AI agent polling `swarm_get_snapshot` every tick might get a sudden 401 with no prior indication.

This is a UX time-bomb: a player with a 180-day certificate who goes inactive for 6 months returns to find nothing works and they need email recovery. A simple `expiring_soon` flag or an MCP notification event would prevent this class of support tickets.

---

### D4 — Medium — Multi-device management visibility gap between MCP and Web UI (UX gap)

**File:** design/auth.md §5.5 (lines 279-297) vs design/interface.md §4.1
**Category:** UX gap

Auth.md defines rich multi-device certificate lifecycle management (regular_device, temporary_device, managed_device, admin_device) with granular rules about which device type can revoke/renew what. The MCP interface exposes `swarm_list_certificates` and `swarm_revoke_certificate`.

But the Web UI section (§16, LoginButton.tsx mockup) shows only registration and recovery flows. There's no "Device Management" panel described where a human player could:
- See all their active certificates across devices
- Revoke a lost device's certificate
- See which device last accessed when
- Initiate renewal for an expiring certificate

Human players need the same device management visibility that AI agents get via MCP.

---

### D5 — Medium — Post-recovery certificate cleanup ambiguity (doc inconsistency)

**File:** design/auth.md, lines 787-788
**Category:** doc inconsistency

§11.2 Step 2 says:

> 标记 token 已消费，同时吊销该用户所有现有 refresh token；是否吊销旧证书由用户选择，默认保留未撤销证书

And then:

> 若恢复原因是"所有证书丢失"，UI 应提示用户检查并吊销不可访问设备对应证书

This creates a "default is unsafe" situation. If a user recovers because their laptop was stolen, the default behavior is to *keep* all old certificates active — including the one on the stolen laptop. The user must manually notice a UI prompt and take action. A stolen-device scenario should default to revoking all certificates, with an opt-out for "I just forgot my password but still have my devices."

---

### D6 — Low — `swarm_deploy` API signature mismatch between GETTING-STARTED and spec (doc inconsistency)

**File:** GETTING-STARTED.md, line 75 vs specs/security/09-command-source.md, lines 99-116
**Category:** doc inconsistency / API gap

GETTING-STARTED shows:

```
swarm_deploy(module_bytes, wasm_signature)
```

But 09-command-source.md defines a two-phase flow:
1. `swarm_deploy_challenge` → get deploy_nonce
2. Build `DeployPayload` → sign with Ed25519 → `swarm_deploy(wasm_bytes, deploy_payload)`

The Getting Started shorthand `wasm_signature` doesn't explain what's being signed (module_hash? metadata? deploy_nonce?). The `swarm_deploy_challenge` tool is also absent from the MCP tools table in both interface.md and mcp-tools.md.

---

### D7 — Low — RUNBOOK CA setup section assumes operator has `swarm ca` CLI, which is not introduced (doc inconsistency)

**File:** RUNBOOK.md, lines 93-102
**Category:** doc inconsistency

The RUNBOOK §2 shows:

```bash
swarm ca root init --out /secure/swarm-root-ca
swarm ca intermediate issue --root /secure/swarm-root-ca --out /etc/swarm/intermediate
```

But no other document introduces the `swarm` CLI tool. The design docs describe the CA model conceptually. Getting Started uses docker compose. The RUNBOOK is the only place that references a `swarm ca` command-line tool, but there's no installation or build instruction for it.

---

### D8 — Low — Email verification page UX not described (UX gap)

**File:** design/auth.md, §12 (lines 847-873)
**Category:** UX gap

The email binding flow sends a verification link. The user clicks it. What page do they see? A plain "Verified ✓" page? A redirect back to the Swarm UI? The docs don't specify the verification page behavior. This matters because:

- If the user is on mobile, the link opens in a browser that may not be their Swarm client
- The verification page is a trust boundary — users are confirming their email ownership here
- There's no mention of rate-limiting on verification link clicks or anti-abuse

---

### D9 — Low — PoW difficulty UX for slow mobile devices not differentiated (UX gap)

**File:** design/auth.md, §9.2 table (line 533-537) and §16.2 (lines 1153-1159)
**Category:** UX gap

§9.2 shows mobile WASM PoW at ~3s for difficulty_bits=24. §16.2 says to show "Slow device? You can wait or [Cancel]" after 8 seconds. But 3 seconds is already a long blank wait for a first-time user. There's no:

- Dynamic difficulty adjustment for mobile clients
- Client-side capability detection to estimate PoW time before starting
- Explanation to the user of *why* they're waiting ("Verifying you're not a bot...")

The 8-second fallback message ("Slow device?") appears after the expected completion time, creating a confusing UX where the progress bar completes before the warning appears.

---

## Questions / Assumptions

1. **Assumption**: The `docs/auth/onboarding-ai`, `docs/auth/errors`, `docs/auth/human-agent-handoff`, and `schema/auth-tools` documents will be created before Phase 1 implementation. If not, AI agent onboarding has no documentation path.
2. **Question**: Is the `swarm_deploy_challenge` tool intentionally omitted from the public MCP tables, or is it an oversight? The deploy flow literally cannot work without it.
3. **Question**: What is the browser storage UX for certificate chain + private key? auth.md §14.3 mentions `localStorage` for `{refresh_token, certificate, client_public_key}`. If the private key is generated via WebCrypto, is it stored in IndexedDB or left non-extractable in the CryptoKey? The storage strategy affects the "what happens when I clear browser data" story.
4. **Assumption**: The `swarm ca` CLI tool referenced in RUNBOOK will have its own documentation. Currently it exists only as an operational command.
5. **Question**: How does a player discover the server's Root CA fingerprint before first connection? The docs say "confirm the fingerprint" but don't describe the out-of-band channel. Is the fingerprint published on a website? In a README? On a physical poster at a LAN party?

---

## Strategy Depth Analysis (Designer Perspective)

The auth system's strategy space is well-constrained — this is an access control system, not a game mechanic, so "dominant strategy" analysis doesn't apply in the traditional sense. Instead, consider the **recovery strategy space**:

- **Email recovery**: Convenient, but requires the user to have bound email *before* losing access. Timing risk: if you lose all certificates before binding email, you're locked to admin recovery only.
- **Passkey recovery**: Convenient and doesn't require remembering passwords, but passkey sync across platforms (iCloud/Google) introduces a new trust dependency.
- **Admin recovery**: Last resort, requires out-of-band communication with server operator. Works offline, but adds latency and human dependency.

No single recovery path dominates — email is fastest for connected users, passkey is best for cross-device users, admin is the only option for completely locked-out offline users. The recommendation to enable at least two recovery paths (e.g., email + passkey) before considering the setup complete should be documented in the onboarding flow.

**Nash equilibrium for recovery**: The optimal strategy is email + passkey binding immediately after registration, with admin recovery as the documented fallback. This minimizes the probability of permanent lockout. The documentation should explicitly recommend this.

---

## Summary

| Severity | Count | Categories |
|----------|-------|-----------|
| Critical | 0 | — |
| High | 2 | UX gap (D1), deferred implementation concern (D2) |
| Medium | 3 | UX gap (D3, D4), doc inconsistency (D5) |
| Low | 4 | Doc inconsistency (D6, D7), UX gap (D8, D9) |

The auth protocol design is sound and well-specified at the contract level. The issues are all in the user-facing surface: compressed onboarding, missing AI agent docs, and UX gaps around certificate lifecycle management. These don't require redesign — they require documentation and Phase 1 implementation decisions.

No blocking design flaws found. The CONDITIONAL_APPROVE condition is: create the four missing onboarding documents (or inline their content) and expand GETTING-STARTED.md's security-critical onboarding steps before Phase 1 implementation begins.
