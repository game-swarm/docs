# R9 Security Review — Swarm Engine

> **Reviewer**: Claude (Security)
> **Round**: R9
> **Source**: reviews/r9-sec-summary.md (DESIGN.md, tech-choices.md, P0-2/3/4/5/9)
> **Date**: 2026-06-14

---

## VERDICT: APPROVE WITH CONDITIONS

The security architecture is mature and shows genuine defense-in-depth rather than checklist security. The sandbox model (deferred commands + no mutating host functions + per-tick fork-and-kill) is the strongest design decision in the document — it structurally eliminates entire bug classes rather than guarding against them. The single visibility cache shared across all output surfaces is similarly excellent.

However, three of the five open questions are not "deeper review" items — they are **exploitable gaps that must be closed before freeze**. The cache-invalidation-on-ban gap (Q3) is a concrete authorization bypass, the dual-person Rollback (Q2) is undefined enforcement on the single most privileged write path, and the flag whitelist (Q1) is an unbounded capability. I cannot approve unconditionally while a banned player's code can still execute.

The conditions below are blocking. The strengths are real and should not be diluted by churn.

---

## BLOCKING ISSUES

### B1 — Module cache survives ban/revocation (Open Q3)
**Severity: High.** Modules are cached by `(module_hash, wasmtime_version)`, which is **identity-free**. Revoking a player's cert/token invalidates new submissions but does nothing to a module already resident in cache. A banned or compromised player's code continues to execute every tick until the cache entry naturally evicts.

Root cause: the cache key omits the authorization dimension. Two fixes, apply both:
- The per-tick scheduler must check **live auth status of the owner** before dispatching a cached module — cache hit ≠ execution authorization. Caching is a compile/validation optimization, not an admission decision.
- Ban/revocation must publish an event that **purges all cache entries owned by that player** synchronously (or marks them non-dispatchable). Do not rely on TTL eviction for a security boundary.

This is the only issue I consider a true authorization bypass. It blocks.

### B2 — `Rollback` dual-person audit has no defined enforcement (Open Q2)
**Severity: High.** `Rollback` is the most privileged source in the Source Gate table (`write + deploy + query`). "Requires dual-person audit" is currently a policy statement with no mechanism. Policy without enforcement on a rollback-write path is an integrity hole — a single compromised admin token can rewrite world state and roll deploys.

Require **two distinct Ed25519 signatures from two distinct admin `player_id`s** over the same rollback request payload (including target tick and module hash), validated server-side before the Source Gate admits the command. Reject if the two signing identities are equal or if either cert is revoked. Record both signers in TickTrace. Make it a hard server-side rejection, not a review-after-the-fact log entry.

### B3 — `set_entity_flag` whitelist is unenumerated (Open Q1)
**Severity: Medium-High.** A capability whose allowed values are undefined is, in practice, unbounded. The summary cites `slow`, `empowered` as examples — but "examples" is exactly the problem. If the whitelist isn't a closed, code-enforced set, a RuleMod author (operator-trusted, but operators are not infallible and can be compromised) can set arbitrary flags, some of which may interact with combat, visibility, or economy in unintended ways.

Enumerate the complete flag set in the spec, mark each with its gameplay surface (combat/movement/economy/cosmetic), and enforce it as a compile-time constant the engine validates against. Anything not on the list is rejected at RuleMod load time, not at call time.

---

## NON-BLOCKING ISSUES

### N1 — `getrandom` blocked but determinism source unspecified
The seccomp allowlist correctly blocks `getrandom` and WASI randomness is disabled — good, this enforces determinism. But the summary never says **where deterministic randomness comes from** for gameplay that needs it. Per memory, the project standardizes on Blake3 as the single primitive; confirm the snapshot delivers a per-tick deterministic seed (e.g., `Blake3(world_seed, tick, player_id)`) so players don't try to smuggle entropy in and fail mysteriously. Document it so the closed door has a labeled alternative.

### N2 — `Simulate` isolation model undefined (Open Q5)
Dry-run at `0.5× MAX_FUEL` on a snapshot copy — but does it spin up a real sandbox worker with the full seccomp/cgroup stack? If simulation takes any shortcut on isolation "because it can't mutate anything," that shortcut becomes the escape vector. **Simulation must use the identical sandbox boundary as live execution.** The only difference should be the discard of output, not a weaker container. State this explicitly.

### N3 — `next_tick_fuel_credit` voided on module change — verify the dual direction
The anti-amplification rule voids credit when `module_hash` changes before consumption (good, kills v1-farms/v2-spends). Confirm the inverse is also closed: a player cannot **accumulate** credit across a redeploy by keeping the same hash and deploying-rolling-back to reset throttle state. The throttle state (`consecutive_high_refund_ticks`) should key on `player_id`, not `module_hash`, so a redeploy doesn't launder the abuse counter.

### N4 — Prompt-injection charset relies on delimiter exclusion only
The defense is solid (untrusted tagging + typed JSON + delimiter contract). One residual: the SDK delimiter contract is **the SDK's** responsibility, and third-party agents may not use the official SDK. The server-enforced `"untrusted": true` tagging is the real backstop — make sure the spec states that this tagging is **non-optional and present on every player-origin string regardless of client**, since that's the one defense that survives a non-compliant client. The summary says this; just ensure it's normative, not aspirational.

### N5 — `public_spectate` + `replay_privacy` enforced at config load? (Open Q4)
Move `spectate_delay ≥ 50` and `arena public delay ≥ 100` from "constraint" to **hard rejection at world-config load time**. A constraint that isn't validated at the boundary is a future leak waiting for a config typo.

---

## STRENGTHS (preserve these — do not refactor away)

1. **Deferred Command Model with no mutating host functions.** This is the architectural keystone. WASM cannot mutate state because the host API to do so *does not exist*, and unknown imports are rejected at validation. Sandbox escape buys an attacker nothing because there's no privileged surface inside the sandbox to reach. This is correct-by-construction security.

2. **Per-tick fork-and-kill lifecycle.** No retained state means no persistent compromise, no cross-tick side channels, no memory-leak accumulation. Expensive, but the right call for an adversarial code-execution platform.

3. **Single visibility cache feeding all output surfaces.** `(tick, player_id) → HashSet<EntityId>` read by snapshot/MCP/WebSocket/REST/replay eliminates the classic "surface A leaks what surface B hides" bug class. This is the kind of design that prevents a whole category of CVEs.

4. **Layered sandbox with belt-and-suspenders.** seccomp + cgroup v2 + Wasmtime fuel + epoch + WASI-disabled + guard pages. Fuel metering and epoch interruption are independent kill paths — one failing doesn't open the box.

5. **Source Gate as a single pipeline with no bypass.** Server-injected `auth_context`, `player_id` non-self-reportable, module hash independently recomputed server-side. The auth-before-action ordering is correct.

6. **Pinned Wasmtime with a real CVE SLA.** `=30.0` plus 72h/7d patch windows turns supply-chain risk into an operational commitment rather than a hope.

7. **Fuel refund anti-amplification is thoughtfully constrained.** Next-tick-only credit, per-tuple dedup, redeploy voids credit, throttle on sustained high refund. The author clearly modeled the abuse case rather than just adding a feature.

---

## SUMMARY

Close B1/B2/B3 and this is a freeze-ready security architecture. The design philosophy — eliminate vulnerability classes structurally rather than patch instances — is exactly right for a platform whose entire premise is running untrusted code. The blocking issues are not design flaws in that philosophy; they are three places where the philosophy wasn't carried all the way to enforcement. Carry them there.
