# R28 Architect Review — rev-dsv4-architect

**Date**: 2026-06-20
**Reviewer**: rev-dsv4-architect (DeepSeek V4 Pro)
**Scope**: B1+B4+B5 closure + A-H2/T-H1/CX3/E-H1 new contracts
**Files reviewed**: 7 (01-tick-protocol, 02-command-validation, api-registry, design/README, 07-world-rules, design/auth, 09-snapshot-contract)

---

## Verdict: APPROVE_WITH_RESERVATIONS

All five main verification targets pass closure checks. Two minor GAPs identified — neither is blocking but both warrant attention before implementation.

---

## Strengths

1. **Scheduling chain consolidation (B1)**: 02-command-validation.md correctly delegates all scheduling to `06-phase2b-system-manifest.md` — no duplicated scheduling chains found. Priority resolution, status_advance_system placement, and special_attack_reducer all reference the manifest as sole authority.

2. **Capacity model coherence (B4)**: Worker pool formula (`min(max_pool, active_players)`), player hard cap (1000), timeout budget (2500ms COLLECT, 2500ms total COLLECT+EXECUTE), and measured admission model (p95-based dynamic regulation) are consistently defined across 01-tick-protocol, api-registry, and 09-snapshot-contract. No cross-document value collisions.

3. **Auth-Registry alignment (B5)**: Certificate types (ClientAuth/CodeSigning/Admin/Federation) and their TTLs match between auth.md and api-registry. Deploy flow (deploy_mutation + fdb_version_counter + async blob upload) is consistently described. Auth RejectionReason codes (1001-1012) are properly namespaced in api-registry §2.5.

4. **Seed lifecycle self-consistency (T-H1)**: Arena Commit-Reveal and World Operator Seed-Bump form a coherent dual model. Seed generation, runtime hiding, disclosure, archival, and leak response all have defined semantics per mode. Statistical detection metrics (win-rate deviation, combat RNG advantage, spawn clustering) are concrete. Seed archival in keyframe snapshots correctly supports CI replay without external seed archive.

5. **Rhai contract engine alignment (CX3)**: 9 hooks map cleanly to tick phases (on_tick_start → COLLECT → on_command_validated → Phase 2a → on_spawn/on_death → Phase 2b → on_tick_end → BROADCAST). RhaiActionBuffer transactional model (buffer → atomic apply) is consistent with FDB transaction semantics. Single validation path enforced — Rhai cannot bypass Command Validation Pipeline. Fixed-point arithmetic mandate (no f64) confirmed in both 07-world-rules and 01-tick-protocol §9.8.

6. **TickTrace terminology resolved (A-H2)**: design/README Appendix C cleanly disambiguates TickCommitRecord (replay-critical FDB subset), RichTraceBlob (debug detail, deferrable), and ReplayArtifact (self-contained CI bundle). Aligns with api-registry §6 (22-field TickTrace Envelope) and 01-tick-protocol §9.4 (delta chain integrity).

7. **Allied Transfer finalized (E-H1)**: 09-snapshot-contract §3.2a provides complete intercept design — 50-tick window, Steal vs Destroy modes, success rate formula with part_bonus and escort_penalty, deterministic RNG seed. No open items.

---

## Concerns

### GAP-D1: swarm_get_server_trust not registered in API Registry

**Severity**: Low
**Location**: auth.md §10.1 line 693 vs api-registry §3.2-3.3

`swarm_get_server_trust` (returns `ServerTrustInfo` — server_id, Root CA fingerprint, Intermediate chain) is defined in the auth design document but absent from api-registry's 57 game_api tools and 11 auth_api tools. This tool is critical for the "不安全传输可认证" design — clients need it for TOFU pinning on first HTTP access.

**Recommendation**: Add `swarm_get_server_trust` to `auth_api.idl.yaml` as a read_replay_safe tool (no auth required, rate limit 60/min per IP), then regenerate api-registry.md.

### GAP-D2: Hard cap players marked "benchmark-gated (未验证)"

**Severity**: Low (operational, not design)
**Location**: api-registry.md §5.5 line 535

The 1000-player hard cap is explicitly annotated "⚠️ benchmark-gated（未验证）". Until the benchmark validates this number on the target hardware baseline (64 GB RAM, 32 cores), the capacity numbers are provisional. The measured admission model (09-snapshot-contract §7) provides runtime protection by dynamically reducing admitted players when p95 exceeds SLO, which mitigates the risk of an incorrect hard cap.

**Recommendation**: Run benchmark before declaring hard cap as production-ready. Until validated, treat hard cap as advisory and rely on measured admission for runtime protection.

---

## Consistency Gaps: NONE

All cross-document verification targets check out:

| Target | Source Docs | Status |
|--------|------------|--------|
| B1 scheduling chain delegation | 02-command-validation → 06-phase2b-manifest | CLOSED |
| B4 capacity/worker pool consistency | 01-tick-protocol vs api-registry vs 09-snapshot-contract | CLOSED |
| B5 auth/deploy alignment | auth.md vs api-registry §2.5/§11 | CLOSED |
| T-H1 seed lifecycle | 01-tick-protocol §3.1 internal consistency | CLOSED |
| CX3 Rhai vs engine | 07-world-rules vs 01-tick-protocol §9.8 | CLOSED |
| A-H2 TickTrace glossary | design/README Appx C vs api-registry §6 | CLOSED |
| E-H1 Allied Transfer | 09-snapshot-contract §3.2a — fully defined | CLOSED |

---

## Algorithmic Risks: NONE

No computational explosion paths found. Key algorithmic patterns verified:

- Snapshot truncation: O(entities) distance-bucket sort + lexicographic tiebreak → deterministic, bounded. Critical entities immune to truncation.
- Seeded shuffle: Fisher-Yates with Blake3 XOF → O(N) per tick, deterministic. No dependency on OS entropy.
- Pathfinding budget: 100,000 explored nodes global cap, per-player 10 calls with individual share → upper bound enforced at engine level.
- Rhai AST budget: 100,000 nodes deterministic limit, wall-clock 2s only for alerting → prevents infinite loops deterministically.
- FDB transaction sizing: Only state delta + TickTrace manifest + fuel record, not full world state. Large blobs go to object store with FDB pointer only.
- Overload anti-lockout proof: Formal proof in 02-command-validation §3.17 confirms no attacker coalition can permanently lock target fuel budget.

---

## Summary

R28 achieves closure on all five B-series targets (B1/B4/B5/T-H1/CX3) and three new contracts (A-H2/E-H1 + implicit A-H1 via glossary). Two low-severity GAPs identified — neither blocks implementation. Recommend APPROVE_WITH_RESERVATIONS with the two GAPs tracked for R29 follow-up.