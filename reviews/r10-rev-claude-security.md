# R10 Security Review — Swarm Engine

> **Reviewer**: Claude Opus 4.8 (Security Primary)
> **Round**: R10 · Phase 0 Architecture Freeze
> **Source**: reviews/r10-sec-summary.md (DESIGN.md, tech-choices.md, P0-02/03/04/05/09)
> **Date**: 2026-06-14

---

## VERDICT: APPROVE WITH CONDITIONS

The security architecture is the strongest I've reviewed in this project. Three structural decisions are genuinely excellent and should be treated as load-bearing: (1) the Deferred Command Model that structurally eliminates mutable host functions — WASM cannot mutate state because the API *does not exist*, not because a guard catches it; (2) the single `is_visible_to()` cache feeding all seven output surfaces, which eliminates the classic "surface A leaks what surface B hides" vulnerability class; (3) the per-tick fork-and-kill sandbox lifecycle, which means no persistent compromise, no cross-tick side channel, no memory-leak accumulation.

However, I have two blocking conditions and one structural concern that I cannot pass without noting. Neither is a new discovery — both are inherited from R9 and remain unresolved. The conditions are concrete and small in surface area; fixing them does not require architectural change.

---

## BLOCKING ISSUES

### B1 — Module cache authorizes by hash, not by identity (R9-B1, unresolved)

**Severity: High. This is an authorization bypass.**

The module cache keys on `(module_hash, wasmtime_version)` — an identity-free tuple. A player whose cert is revoked or who is banned has their new submissions blocked, but a cached module continues to dispatch every tick. The cache is an optimization (avoid recompile), not an admission gate, yet it currently functions as one.

The fix is two lines of policy, not a redesign:

1. **Pre-dispatch auth check**: before the scheduler picks a cached module, it must verify the owning `player_id` has a live, unrevoked cert. Cache hit ≠ execution authorization. This is a lookup, not a crypto operation — do it in the scheduler hot path.

2. **Ban-triggered cache purge**: revocation/ban must emit an event that synchronously evicts all cache entries keyed to that `player_id`. Do not rely on TTL for a security boundary. A banned player whose code runs for 10 more ticks has 10 ticks of exploit.

This is the only issue in the document I consider a true authorization bypass. It blocks.

### B2 — `Rollback` dual-person audit is a policy statement with no enforcement mechanism (R9-B2, unresolved)

**Severity: High. Policy without code on a write path is an integrity hole.**

`Rollback` is the most privileged source in the Source Gate matrix — it can write world state, deploy code, and query. The summary says "需双人审计：两个不同 admin 的 Ed25519 签名" — but where does this enforcement live?

A statement in a markdown file does not enforce rollback integrity. A single compromised admin token can rewrite world state. The fix must be:

- **Two distinct Ed25519 signatures from two distinct admin `player_id`s** over the same rollback payload (target tick, module hash, reason), validated server-side *before* Source Gate admission.
- Reject if `signer_a.player_id == signer_b.player_id` or if either cert is revoked.
- Record both identities in TickTrace. Make it a hard rejection, not an audit-after-the-fact log entry.

This is the single most privileged write path in the system. It must have code-level enforcement, not a comment.

---

## STRUCTURAL CONCERN (non-blocking, but do not ship without acknowledging)

### SC1 — The Rhai trust boundary is the weakest link in the chain

The design has three trust tiers: WASM (untrusted) → Rhai (server-trusted) → Rust (immutable). The WASM tier is defended with genuine defense-in-depth. The Rust tier is correct-by-compilation. The Rhai tier sits in the middle with "服主信任" as its entire security model.

I do not dispute that server operators are trusted. But the gap is not about malicious operators — it's about operator *error* and *compromise*. A single Rhai mod with a bug that leaks into the ECS bypasses the entire Command Validation Pipeline. The summary says `modify_entity` was removed (good), but `set_entity_flag` with a closed whitelist is still undefined — "examples" (`slow`, `empowered`) is not a whitelist.

The dsv4-security review flagged `set_entity_flag` whitelist enumeration (M7), but I want to frame this differently: the real concern is that **Rhai is an imperative scripting engine sitting inside the trust boundary with mutable ECS access**. Every future addition to the Rhai API extends the attack surface of the trusted tier.

My recommendation: treat Rhai as a declarative action engine, not an imperative one. All Rhai scripts produce `RuleAction[]` (award, deduct, emit_event, set_flag) that passes through the same validator as WASM commands. This closes the "trusted tier mutates ECS directly" structural gap without reducing modder power.

This is not blocking for Phase 0 freeze because the operator-is-trusted model is a valid design choice. But I am flagging it because designs that start with "this tier is trusted" tend to accumulate capabilities until the trust assumption is the only thing holding.

---

## NON-BLOCKING ISSUES

### N1 — path_find executes in both COLLECT and EXECUTE phases with different cost accounting

**Severity: Medium-High.** The dsv4-security review captured this well (H1 + H2). I will not repeat the analysis, but I want to add the structural framing: this is not a "fuel formula is wrong" bug — it's a **phase-coupling defect**. The COLLECT phase (parallel, per-player sandbox) and EXECUTE phase (serial, engine-side) should not perform the same expensive computation with different cost models. Pick one phase. My recommendation: COLLECT owns path_find (it has parallelism, fuel metering, and per-player quotas). EXECUTE validates "path length ≤ MAX_PATH_LENGTH" as a cheap bounds check on the already-computed result. If terrain changed between phases, the MoveTo fails with `PathChanged` and refunds 50% fuel — that's cheaper than recomputing A* for 100 MoveTo commands serially.

### N2 — `swarm_simulate` has no tick-count ceiling

**Severity: Medium.** `0.5 × MAX_FUEL` is a per-simulated-tick budget, not a total-work budget. A `simulate(N=1,000,000)` could run for seconds even if each tick is cheap. The rate limit (5/tick) helps but does not constrain wall-clock duration. Add `MAX_SIMULATE_TICKS` (100–200) and an independent wall-clock timeout (500ms). The dsv4-security review also flagged this (H3); I concur.

### N3 — `downgrade_timer` behavior during `safe_mode` is unspecified

**Severity: Medium.** The dsv4-security review identified this (M5). I want to add the security framing: if `downgrade_timer` continues to decrement during `safe_mode`, an attacker can siege a room through the entire safe_mode window and attack the moment it expires — when the Controller may already be at minimum level. The fix: pause `downgrade_timer` during `safe_mode`, reset on owner change. This is a one-line spec change with significant gameplay-security implications.

### N4 — `amount=0` passes all validators and wastes pipeline resources

**Severity: Low.** Transfer/Withdraw with `amount=0` passes every check (has_resource: 0 ≤ carry_amount; target_has_space: true) and consumes a command slot and TickTrace entry. Not a security vulnerability, but it's a free filler attack vector — 100 `amount=0` Transfer commands are indistinguishable from 100 real commands for pipeline cost purposes. Add `amount > 0` to the validator. Trivial fix.

### N5 — FDB transaction retry has no exponential backoff

**Severity: Low.** "重试最多 3 次" with no backoff means high-contention keys cause three rapid-fire conflicts, burning compute for no progress. Add 1s/2s/4s backoff and consider `join_lock` on retry 2. Not a vulnerability, but at 500-player scale it becomes a performance degradation vector that looks like a DoS.

---

## STRENGTHS (preserve these — do not refactor away)

1. **Deferred Command Model with zero mutating host functions.** This is the architectural keystone. WASM has exactly four read-only host functions. Unknown imports are rejected at validation. Sandbox escape buys an attacker nothing because there is no privileged surface inside the sandbox. This is correct-by-construction security — it eliminates vulnerability classes rather than defending against them.

2. **Single `is_visible_to()` cache feeding all output surfaces.** Snapshot, MCP, WebSocket, REST, replay, delta, and debug all read the same `(tick, player_id) → HashSet<EntityId>` cache. This prevents the classic "surface A hides entity X but surface B's delta stream reveals it" bug class. One function to audit. One cache to verify. No bypass paths.

3. **Per-tick fork-and-kill sandbox lifecycle.** No retained state, no persistent compromise, no cross-tick side channels, no memory-leak accumulation. Expensive, but the correct call for a platform whose premise is running adversarial code. Combined with seccomp + cgroup v2 + Wasmtime fuel + epoch interruption + WASI-disabled, this is a belt-and-suspenders sandbox where two independent kill paths (fuel exhaustion and epoch timeout) must both fail for a resource-exhaustion attack to succeed.

4. **Source Gate as a single pipeline with server-side identity injection.** `player_id` is server-injected, not client-claimed. Module hash is recomputed server-side. Auth context flows through every stage. No "trust the client" assumptions anywhere in the chain. The auth-before-action ordering is correct.

5. **Fuel refund anti-amplification is thoughtfully constrained.** Next-tick-only credit, per-tuple dedup, deploy-reset voids credit, throttle on sustained high refund rate, 10% cap per tick. The designer clearly modeled the abuse case rather than adding a feature and hoping. The deploy-reset rule in particular closes a subtle cross-module budget-transfer exploit.

6. **Pinned Wasmtime with a real CVE SLA.** `=30.0` version pin plus 72h (CVSS ≥9.0) / 7d (CVSS ≥7.0) patch windows. This turns supply-chain risk from a hope into an operational commitment. Quarterly Wasmtime security bulletin review plus `cargo audit` in CI is the correct posture for a platform that ships a WASM runtime as its core execution engine.

7. **Prompt injection defense is server-enforced, not SDK-reliant.** The `"untrusted": true, "source_player": N` tagging is mandatory on every player-origin string regardless of client. The delimiter contract (`‖‖‖GAME_DATA‖‖‖`) is defense-in-depth, not the primary defense. A non-compliant client still gets tagged strings — the server is the backstop. This is the correct layering order.

---

## R8/R9 FINDING TRACKING

| ID | Round | Severity | Description | Status |
|----|-------|----------|-------------|--------|
| R9-B1 | R9 | High | Module cache survives ban/revocation | **UNRESOLVED** → R10 B1 |
| R9-B2 | R9 | High | Rollback dual-audit enforcement missing | **UNRESOLVED** → R10 B2 |
| R9-B3 | R9 | Med-High | `set_entity_flag` whitelist unenumerated | **UNRESOLVED** → R10 SC1 (structural concern) |
| R8-H-1 | R8 | High | Player-name delimiter collision | **RESOLVED** — Unicode `‖‖‖` |
| R8-H-2 | R8 | High | Spectator bypass replay_privacy | **RESOLVED** — `spectate_delay ≥ 50` |
| R8-H-3 | R8 | High | Refund carryover exploit | **RESOLVED** — deploy-reset rule |
| R8-H-4 | R8 | High | `modify_entity` no whitelist | **RESOLVED** — removed from Rhai API |

---

## CROSS-REVIEWER ALIGNMENT

My review aligns with dsv4-security on the unresolved R9 items (C1 start section bypass, H1 path_find fuel, H3 simulate cap) and with gpt-security on the Rhai trust boundary concern (their H3, my SC1). I diverge from gpt-security on their H4 (auth/signing model confusion) — I read the Ed25519 cert model as internally consistent: OAuth2 is for initial identity proof, the cert is the operational credential, and the client holds the private key it generated. The terminology tension (Blake3 MAC vs Ed25519 signing) is a documentation clarity issue, not a security flaw. I also consider gpt-security's H1 (MCP IDOR) to be a valid testing concern but not a design flaw — the `is_visible_to()` cache already constrains all MCP reads; the risk is in implementation, not architecture.

My review is more permissive than gpt-security's REQUEST_MAJOR_CHANGES verdict. The difference is philosophical: I believe the design's structural properties (deferred commands, single visibility cache, fork-and-kill sandbox) are strong enough that the remaining issues are fixable at the spec level without reopening architecture. gpt-security sees the same issues and wants them resolved before freeze. Both positions are defensible; the Speaker should decide whether "Phase 0 freeze" means "architecture frozen, spec details can still be tightened" or "every spec paragraph is final."

---

## SUMMARY

Close B1 and B2 and this architecture is freeze-ready from a security perspective. The design philosophy — eliminate vulnerability classes structurally rather than patch instances — is exactly correct for a platform whose core premise is running untrusted code. The remaining issues are enforcement gaps in an otherwise sound design, not fundamental flaws.

The structural concern about Rhai (SC1) is a Phase 1 hardening item, not a freeze blocker. Flag it in the roadmap and address it before the first public world goes live.

---

*R10 · Security Reviewer · APPROVE WITH CONDITIONS (B1, B2 blocking)*
