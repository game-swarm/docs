# R1 Local Auth — Game Designer Review

**Reviewer:** rev-dsv4-designer (Game Designer Reviewer)
**Date:** 2026-06-17
**Documents reviewed:** local-auth.md, interface.md, tech-choices.md, README.md

---

## Verdict: CONDITIONAL_APPROVE

The local auth design is architecturally sound and philosophically aligned with Swarm's core principles — AI-human parity, player sovereignty, and deployment flexibility. The PoW-based anti-abuse mechanism is an elegant alternative to IP rate limiting and works equally well for humans and AI agents. The three registration scenarios (human browser, AI self-registration, agent proxy) are conceptually covered. However, several UX and edge-case gaps in the agent proxy flow and frontend implementation need attention before implementation.

---

## Strengths

1. **AI-Human parity by design.** Local auth uses the same certificate model, same PoW challenge, and same session system as OAuth2 users. AI agents and humans are indistinguishable downstream — consistent with Swarm's "world only knows WASM" principle. The `provider` field (`github` / `google` / `local`) cleanly separates identity namespaces.

2. **PoW over IP rate limiting is the correct game design choice.** IP rate limiting would fragment the player base behind NATs/CGNAT and penalize AI agents sharing infrastructure. PoW is identity-agnostic, stateless, and charges CPU per registration — the same resource that powers the game itself. The difficulty table (dev=2 / light=3 / standard=4 / high=5) provides operational flexibility without code changes.

3. **The three-step challenge→solve→register flow is clean.** Dead-simple API surface: `swarm_register_challenge()` → client solves PoW → `swarm_register(...)`. Login is even simpler: `swarm_login(username, password, pubkey)`. Error codes (`invalid_pow`, `username_taken`, `invalid_credentials`, `weak_password`) are well-chosen and unambiguous.

4. **Password self-management for AI agents is explicitly designed.** `random_hex(32)` → 64-char hex password bypasses human-oriented validation, providing cryptographically strong credentials with zero human intervention. The integration test `ai_agent_self_registration_flow` directly validates this path.

5. **Deterministic player_id in the same pattern as OAuth2.** `blake3("local:" + username_lowercase)` mirrors `oauth_player_id()`, ensuring offline derivability and no FDB dependency for ID resolution. Consistent with §8 of tech-choices.md (Blake3 single-primitive philosophy).

6. **Security threat model is thorough (§11).** Eight specific threats mapped to mitigations. The decision to not distinguish "user not found" from "wrong password" prevents username enumeration. PoW challenge one-time-use via FDB atomic transaction prevents replay attacks. The explicit "not doing" list (§11.3) sets clear scope boundaries.

7. **FDB transaction design handles registration races correctly.** The atomic consume-challenge + check-username + write-user sequence in Appendix C prevents both challenge reuse and duplicate username registration — no TOCTOU vulnerabilities.

8. **Deterministic test strategy with 18 named test cases.** Covers username validation, password validation, PoW verification, FDB integration, AI agent flow, and the full register→login lifecycle. The `local_register_and_login_full_cycle` integration test is a strong acceptance criterion.

---

## Issues Found

### [Medium] G1 — Frontend PoW solver freezes UI (no Web Worker)

The JavaScript PoW solver in Appendix A (§A.2) runs a tight `while(true)` loop on the main thread:

```javascript
while (true) {
  const hash = blake3.hash(input);
  // ...
  nonce++;
}
```

For difficulty=4 (~4.3B iterations, ~1.3s on desktop), this completely freezes the browser UI — no rendering, no scroll, no interaction. On mobile devices, this could be 5-10 seconds of frozen UI, potentially triggering the browser's "page unresponsive" dialog.

**Recommendation:** Move PoW solving to a Web Worker. The `LoginButton.tsx` component posts the challenge to the worker, receives the nonce via `postMessage`, and only then submits the registration. The main thread should show a progress indicator (spinner or estimated time bar) during solving. This is a standard pattern — the doc should explicitly specify it.

### [Medium] G2 — Agent proxy password flow is underspecified

Section 3.3 describes the agent proxy scenario:

```
人类 → "帮我在 Swarm 注册一个账号，用户名 kagurazaka"
  → AI agent 调用 swarm_register_challenge() + swarm_register(...)
  → 返回 certificate + refresh_token 给人类
```

Three critical questions are unanswered:
1. **Who chooses the password?** The human? The agent? If the agent generates it, how does the human receive it? (Agent chat response? Separate secure channel?)
2. **Password in chat logs.** If the human tells the agent "my password is hunter2!", the password is now in the chat provider's logs (OpenAI/Anthropic/etc.), the agent's session history, and potentially the Hermes session DB. This is a significant security risk not mentioned in §11.
3. **Trust model.** The agent necessarily sees the plaintext password during registration. The human must trust the agent. This is acceptable but should be explicitly documented as a trust boundary.

**Recommendation:** Add a subsection to §3.3 covering:
- Agent SHOULD offer to auto-generate a strong password (`random_hex(32)`) and display it to the human
- Human MAY provide their own password (with the documented chat-log risk)
- After registration, agent SHOULD advise the human to change the password (once password-change is implemented in v1.1) and delete the password from agent memory
- Add this scenario to §11.1 threat model

### [Medium] G3 — No password confirmation field in registration UI

The mockup in §10.1 shows a single password field. For a system where:
- Email is optional (no verification)
- Password reset is deferred to future versions
- A mistyped password means permanent account loss

...a confirmation field ("retype password") is essential UX hygiene. Without it, a single typo during registration locks the player out of their account with no recovery path.

**Recommendation:** Add a "Confirm Password" field to the mockup and spec. The frontend should validate that both fields match before submitting. This is trivial to implement and has high UX impact given the deferred password-reset constraint.

### [Medium] G4 — PoW performance on mobile devices not addressed

The difficulty table in §5.3 benchmarks ~1.3s at difficulty=4 on "单核" (single core), but doesn't specify the reference hardware. On a mid-range mobile device (e.g., Snapdragon 7 series, single-core blake3 throughput ~1/3 to 1/5 of desktop), the same computation could take 4-7 seconds.

This matters because:
- Mobile browsers may kill the tab for excessive CPU usage
- Battery drain from 4.3B hash computations is non-trivial
- Users on slow connections may perceive this as a broken registration flow

**Recommendation:** 
- Specify the reference hardware for the difficulty=4 benchmark (e.g., "Apple M1 single core ~1.3s" or "AMD Zen4 single core ~1.3s")
- Consider a dynamic difficulty negotiation: the server offers difficulty=4 by default; if the client fails to respond within a timeout, the server can re-issue at difficulty=3. This keeps the anti-abuse property for fast clients while not locking out slow ones.
- At minimum, document the expected mobile experience with a note: "On mobile devices, PoW at difficulty=4 may take 3-7 seconds. The frontend should display a progress indicator and not time out before 15 seconds."

### [Medium] G5 — Account loss consequence not explicitly stated

Section 12.2 defers password reset to a future version (needs email infrastructure). Section 7 states email is optional. The combination means: **if a local-auth user forgets their password, the account is permanently inaccessible.** Player assets, deployed WASM modules, tournament history — all locked behind a lost password with zero recovery path.

The doc implicitly acknowledges this (no password reset in v1) but never states the consequence directly. A game design document should be upfront about this permanent-loss risk so players can make informed decisions (e.g., write down the password, use a password manager, or choose OAuth2 instead).

**Recommendation:** Add a prominent warning in §7 (Password Rules) or §12.2 (Deferred Features):
> **Warning:** v1 does not support password reset or account recovery. If you lose your password, your account and all associated assets are permanently inaccessible. Use a password manager or write down your credentials. OAuth2 (GitHub/Google) login is recommended if you need account recovery guarantees.

### [Low] G6 — Login rate limiting specification is vague

Section 8.1 states "*swarm_login* 不需要 PoW——每 tick 已限速（10/min per IP）". However:
- "10/min per IP" appears to reference the tick-system rate limit, which applies to MCP queries in general. Is this enforced at the Gateway REST endpoint (`POST /auth/login`) too?
- 10 attempts/minute allows ~14,400 attempts/day per IP. With argon2id at ~100ms/attempt on the server, a determined attacker with a botnet could sustain high throughput.
- The doc doesn't specify whether login failures trigger escalating delays (exponential backoff) or if it's a flat 10/min cap.

**Recommendation:** Explicitly document the login rate-limiting strategy for the Gateway REST endpoint. Consider:
- 10 attempts/minute/IP baseline
- After 5 consecutive failures from the same IP: 1-minute cooldown
- After 10 consecutive failures: 5-minute cooldown
- This is standard practice and adds minimal implementation complexity.

### [Low] G7 — Password-in-chat-logs risk not in threat model

Related to G2 but distinct: the threat model (§11.1) covers password transmission over HTTPS and FDB storage, but doesn't mention the chat-log risk when a human tells an AI agent their password during the agent-proxy flow. This is a realistic attack vector — compromised chat logs at the LLM provider would expose Swarm credentials.

**Recommendation:** Add to §11.1 threat model:
> | 密码经 AI agent 传输 | Agent 代理注册时，建议 agent 自生成密码并显示给人类，而非让人类在聊天中发送密码。如人类主动提供密码，agent 应在注册完成后提示人类删除聊天记录中的密码。 |

### [Low] G8 — player_id collision not mentioned

`local_player_id()` hashes into a u64 (2^64 space). The birthday bound is ~2^32 users (~4.3 billion). While extremely unlikely at any realistic player count, the doc should note that:
- Collision probability is negligible for expected scale
- If a collision were to occur, the second registrant would receive a `username_taken` error (since FDB check happens first)
- This is the same collision model as `oauth_player_id()` and is consistent

---

## Strategy Depth Analysis

From a game designer's perspective, this auth system contributes to Swarm's strategic depth in several ways:

**Identity as a strategic resource.** A player can maintain multiple identities across providers (GitHub, Google, local), each with independent assets and modules. This creates interesting strategic options: a player might run different strategies under different identities, testing approaches in a "lower-stakes" identity before committing to their main account. The design correctly keeps identities separate in v1 (no merge) — merging would remove this strategic dimension.

**AI agent onboarding friction is well-calibrated.** The PoW requirement (~1.3s CPU per registration) creates a small but meaningful cost for AI agent self-registration. This prevents AI agents from spawning thousands of disposable accounts to gain information advantages through mass exploration. The cost is trivial for legitimate agents (one registration per agent identity) but prohibitive for abuse.

**Local-first enables private servers and modded ecosystems.** By not requiring external OAuth2 providers, Swarm can run in air-gapped or private deployments. This enables community-run servers with custom rulesets, which is a powerful driver of long-term game ecosystem health (cf. Minecraft, WoW private servers). The design correctly identifies this in §1 (动机).

**The absence of email binding has gameplay implications.** Without email verification, accounts are more disposable — a player can create a throwaway account for experimentation. This is arguably a feature for a programming game where players might want to test radical strategies without risking their main account's reputation. The lack of password reset is the symmetrical cost: throwaway accounts are truly disposable because they can't be recovered.

---

## Overall Assessment

The local auth design is mature and well-considered. The core architecture — PoW anti-abuse, argon2id password hashing, FDB atomic transactions, shared certificate model — is sound and well-documented. The three registration scenarios cover the intended use cases, and the API surface is admirably simple.

The issues identified are almost entirely in the **UX and documentation layers**, not the architecture. G1 (Web Worker), G3 (password confirmation), and G4 (mobile performance) are frontend implementation details that the doc should specify. G2 (agent proxy password flow) and G7 (chat-log risk) are gaps in the agent-interaction design. G5 (account loss warning) is a documentation gap that has real player-impact.

None of these issues are architectural blockers. All can be resolved by updating the design document — none require rethinking the core approach. I recommend addressing G1-G5 before implementation begins, and treating G6-G8 as nice-to-have clarifications.

**Verdict: CONDITIONAL_APPROVE** — proceed with implementation after addressing the five Medium-severity issues (G1-G5).
