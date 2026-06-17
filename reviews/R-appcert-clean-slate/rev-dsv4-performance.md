# Performance Review — appcert clean-slate

**Reviewer:** rev-dsv4-performance (DeepSeek V4 Pro)
**Date:** 2026-06-17
**Scope:** Certificate chain verification, CRL/nonce/cache, HTTP/agent request overhead, runtime impact
**Docs reviewed:**
- design/README.md, design/auth.md, design/interface.md, design/tech-choices.md, design/engine.md
- GETTING-STARTED.md, RUNBOOK.md
- specs/12-gateway-protocol.md, specs/reference/mcp-tools.md
- specs/security/03-mcp-security.md, specs/security/09-command-source.md
- specs/core/04-wasm-sandbox.md

---

## Verdict: CONDITIONAL_APPROVE

The auth redesign is architecturally sound and thoughtfully constructed. Performance-critical hot paths (Ed25519 verification at ~30k/s, blake3 at ~6 GB/s, argon2id isolated outside FDB transactions) are well-matched to their primitives. However, the design has a **systemic blind spot**: it treats `FDB` as the answer to every auth-state question without modeling aggregate write pressure from per-request nonce storage, and it provides **no certificate verification caching strategy** for the per-request path — these are not blockers at MVP scale (~500 players) but will become scaling bottlenecks before Tier 2. The recommendations are additive (caching, batching, TTL tuning), not architectural rework.

---

## Strengths

1. **Primitive performance alignment.** Ed25519 verification (~30k/s), blake3 hashing (~6 GB/s), and argon2id (19MiB/2-iter = ~100ms outside FDB transaction) are well-matched to their respective hot/cold paths. auth.md §6.1 correctly isolates argon2id outside FDB transactions.

2. **PoW as rate limiter, not crypto puzzle.** auth.md §9 correctly treats PoW as a service-level anti-abuse mechanism rather than a security proof. The difficulty table (§9.2) is calibrated for real-world hardware (Rust ~150ms, WASM ~1.5s at difficulty 24), and §10.7 explicitly avoids IP-rate-limiting CSR submission because PoW _is_ the rate control. This is correct and performant.

3. **Certificate expiry semantics.** auth.md §5.4: "证书自然过期不影响已部署模块继续运行" — this is a critical performance decision. It avoids the "certificate renewal cascade" problem where N players' expiring certificates would trigger N simultaneous deploy re-verifications and potentially N module re-validations.

4. **Deploy nonce as short-lived bridge.** spec/security/09 §7.3: 60s TTL deploy nonce + `deploy_token` (30min) for long compiles. This correctly decouples nonce lifetime from compilation latency, preventing replay window amplification during slow compiles.

5. **Snapshot architecture is performance-aware.** engine.md §3.2: two-phase snapshot (one-time build → per-player room-shard splice) reduces complexity from O(players × entities) to O(entities + players × visible rooms). This is a real performance win documented in the design.

6. **WASM sandbox resource budget is comprehensive.** spec/core/04 §6: fuel (10M instructions), memory (64MB WASM / 128MB process), wall-clock (2500ms), host function call caps, output JSON size cap (256KB). All enforced at the correct enforcement point (Wasmtime config / cgroup / epoch interruption).

---

## Top Findings

### Critical

#### C1 — Per-Request FDB Nonce Storage Creates Linear Write Amplification
**Severity:** Critical | **Category:** deferred implementation concern
**Files:** auth.md §5.6, auth.md §6.2 (auth/request_nonce storage)

Every canonical request (§5.6) generates a nonce stored in FDB at `auth/request_nonce/<certificate_id>/<nonce>`. The spec says nonce "timestamp 在允许窗口内，nonce 未使用" — this requires a persisted anti-replay store per request.

**Scale model (MVP, 500 players):**
- MCP: 50 requests/tick/player × 500 = 25,000 nonce writes/tick
- REST: assume 10% of MCP rate = 2,500 writes/tick
- WebSocket token refresh: ~500 rotations/tick (reconnection bursts)
- **Total: ~28,000 auth FDB writes/tick competing with world state commits**

FDB's strict serializability (§tech-choices.md §4) means these auth writes share the same transaction namespace as game state. While each write is small (~100 bytes), the **transaction rate** is the bottleneck, not byte throughput. At 3s tick intervals, 28,000 auth writes = ~9,333 writes/second just for nonces — before any game state mutations.

The design mentions FDB "事务冲突重试最多 3 次" (auth.md §6.2) but doesn't model auth write pressure as a distinct concern from game state commits.

**No cleanup strategy described.** auth.md §5.5 notes CRL items can be cleaned after `max_certificate_ttl + max_clock_skew + ...` but nonces have no TTL-based GC documented. With ~28,000 nonces/tick × 1,200 ticks/hour = 33.6M nonces/hour. Even with 60s window (§5.7 hints at this), that's 560K nonces in-flight.

**Recommendation:** Add a nonce cache layer backed by Dragonfly (Redis SET NX with TTL) before FDB write. Dragonfly's multi-threaded ~1M QPS can absorb nonce writes; FDB only needs to see them for crash recovery. Alternatively, define a rolling time-window nonce scheme (e.g., bloom filter + timestamp bucket) that drops FDB writes entirely for the hot path, only persisting checkpoint snapshots.

---

#### C2 — Certificate Chain Verification Per Request With No Caching
**Severity:** Critical | **Category:** deferred implementation concern
**Files:** auth.md §5.6, specs/security/03 §2.2, specs/12-gateway-protocol.md §9

Every MCP, deploy, and admin request requires full certificate chain verification (Root CA fingerprint → Intermediate CA → Leaf certificate) plus Ed25519 canonical request signature verification. Per §5.6 the sequence is:
1. Chain trace to trust root + expiry/revocation check
2. Leaf `usage` covers operation
3. Ed25519 signature verification
4. Timestamp window + nonce freshness
5. Scope + audience match

At 25,000 MCP requests/tick, step 1-3 alone = 25,000 × 2 Ed25519 verifications (intermediate sig + leaf sig) = 50,000 verifications/tick = 16,667 verifications/second. Ed25519 verification at ~30k/s means ~0.56 seconds of pure CPU time per tick for cert verification alone — manageable at MVP but not free.

**However:** the Intermediate CA public key is immutable between rotations. There's no design mention of caching the verified Intermediate CA → Root CA binding. Every request re-verifies the same intermediate signature.

**Recommendation:** Add a certificate chain verification cache keyed on `(certificate_id, intermediate_fingerprint)` with invalidation on CRL update or Intermediate CA rotation. The cache can live in-process (in Gateway/Engine) with sub-microsecond lookup — this eliminates 50% of Ed25519 verification work (the intermediate step). This is a 10-line optimization with outsized impact.

---

### High

#### H1 — Federation Revocation Polling Window (3600s) Is Overly Conservative for Code Signing
**Severity:** High | **Category:** security gap (performance intersection)
**Files:** auth.md §15.6

Federation revocation cache staleness defaults to 3600 seconds. The fallback policy `revocation_fallback = "reject_for_code"` means: if the remote world is unreachable and CRL cache is stale, code signing is rejected.

This creates a **cascading unavailability window**: if World A goes down for 5 minutes, World B's federation cache goes stale after 3600 seconds. But if World B's network to World A is intermittent (not down, just flaky), each `swarm_federated_login` or code deploy attempt triggers a cross-server CRL query (network call in the auth hot path), potentially timing out, causing spurious rejections.

The polling model (§15.6: "定期向 World A 查询吊销列表") adds background load proportional to `(federated_worlds × polling_frequency)`. With 10 federated worlds polling at 5-minute intervals, that's 120 CRL fetches/hour — lightweight, but the hot-path CRL query on cache miss isn't modeled.

**Recommendation:** Add a push-based CRL distribution option (Webhook from World A → World B on revocation events) as a complement to polling. Reduce default `revocation_cache_stale_seconds` to 600s for `login+code` trust level, where the security stakes are higher.

---

#### H2 — Auth Subspace Has No Documented Dragonfly Caching Strategy
**Severity:** High | **Category:** doc inconsistency / deferred implementation concern
**Files:** auth.md §6.2, tech-choices.md §6, RUNBOOK.md §4

tech-choices.md §6 positions Dragonfly as "非权威缓存" — authoritative source is FDB, Dragonfly accelerates reads. RUNBOOK.md §4 confirms: "无 Dragonfly → 所有读取回退 FDB 直读". But auth.md §6.2 defines the entire auth subspace in FDB with no mention of a Dragonfly caching layer for hot auth reads.

Hot auth reads in the request path:
- `auth/certificates/<id>` — every request checks certificate expiry/revocation
- `auth/revocations/<id>` — CRL lookup
- `auth/request_nonce/<...>` — anti-replay
- `auth/challenges/<id>` — PoW verification on CSR submit

At 25,000 requests/tick, that's 75,000-100,000 FDB reads/tick for auth alone. With FDB's ~50K-100K reads/second on modest hardware, this saturates the read path. Dragonfly can serve these at ~1M QPS (multi-threaded Redis-compatible, per tech-choices.md).

**Recommendation:** Add an auth cache layer section to auth.md that specifies which subspaces are cached in Dragonfly, their TTL, and consistency guarantees (eventual, ≤1 tick staleness). The FDB authoritative write + Dragonfly read-replica model is already the architecture for game state (§tech-choices.md §6); auth should follow the same pattern.

---

#### H3 — Security Epoch Emergency Bump Triggers N-Simultaneous Recompiles
**Severity:** High | **Category:** deferred implementation concern
**Files:** spec/security/09 §3.4–3.5, spec/core/04 §7

spec/security/09 §3.4: "Auth Service epoch: 全局单调递增整数。emergency bump 后所有旧 epoch 证书立即失效".
spec/security/09 §3.5: compile cache key includes `security_epoch`.
spec/core/04 §7: max 5 concurrent compiles, 30s timeout, 512MB memory per compile.

When `security_epoch` is bumped (Intermediate CA compromise scenario), every player must re-authenticate (get new certificates) AND every previously-compiled WASM module has its cache invalidated. With 500 players each having 1-4 module slots, that's 500-2000 recompilations, queued at 5 concurrent with 30s timeout each = 100-400 minutes of compilation backlog.

This is correct behavior for security — you want to force re-verification. But the design doesn't discuss the **operational timeline**: 500 players locked out of gameplay for potentially hours while their modules recompile. The `CodeSigningCertificate` expiry semantics (§5.4: expired certs don't stop running modules) are contradicted here — running modules _do_ stop if epoch bumps invalidate their validation context.

**Recommendation:** Add a phased epoch bump strategy: (1) bump epoch → old certs invalidated, players re-auth (fast, certificates only); (2) old modules continue running with a grace period (e.g., 24h) marked with old security_epoch but monitored; (3) modules recompile in background as compilation slots become available. This decouples auth recovery (minutes) from code recovery (hours).

---

### Medium

#### M1 — Host Function Pathfinding Cost Model Is Precise But Unbounded Per-Tick
**Severity:** Medium | **Category:** deferred implementation concern
**Files:** spec/core/04 §8

`host_path_find` costs: `500 × explored_nodes + 200 × expanded_edges + cache_miss_penalty`. Cap: 10 calls/tick + 100,000 explored_nodes total. Worst-case: 10 pathfind calls × 10,000 explored_nodes each (the cap is aggregate, not per-call) = 100,000 nodes × 500 fuel = 50M fuel just for 10 pathfinding calls.

Fuel budget is 10M per tick total. So a player who uses 10 pathfind calls to unreachable destinations (max explored_nodes per call) burns through their entire fuel on pathfinding alone, producing zero gameplay commands. This is **correct by design** (fuel metering prevents abuse) but worth noting: the pathfind cost model creates a "grief budget" where a hostile player can burn their own fuel trivially (wasting sandbox worker time) without affecting others.

The recommendation is minor: add a per-call `explored_nodes` cap of 20,000 to prevent a single pathfind from consuming disproportionate WASM time before fuel exhaustion.

---

#### M2 — Nonce Replay Window Size Imprecise Across Documents
**Severity:** Medium | **Category:** doc inconsistency
**Files:** auth.md §5.7 vs spec/security/09 §7.3

auth.md §5.7: "nonce/timestamp 必须强制启用，重放窗口默认不超过 60 秒"
spec/security/09 §7.3: deploy nonce TTL = 60s

auth.md §5.6: specifies nonce freshness as "timestamp 在允许窗口内，nonce 未使用" without stating the window size. The 60-second window only appears in §5.7 (insecure transport context) and §9 (deploy nonce — a different nonce type).

For request nonces (canonical request anti-replay), the window should be explicitly stated in §5.6 alongside the nonce generation specification. If the request nonce window differs from the deploy nonce window, that needs to be called out.

---

#### M3 — Refresh Token Rotation Grace Period Creates Short-Burst FDB Contention
**Severity:** Medium | **Category:** deferred implementation concern
**Files:** auth.md §14.1

Refresh token rotation: "旧 token 在 rotation 后 5min 内仍可被接受一次 (grace period，防竞态)". This means every rotation writes:
1. Mark old token `rotated` + set `grace_consumed_at` = None
2. Create new token
3. (If grace used) Atomic consume of grace_consumed_at

In WebSocket reconnection storms (500 players reconnect in 10s after a gateway restart), all attempt token refresh simultaneously. Each refresh is an FDB transaction. With 500 refreshes over 10s = 50 writes/second — manageable but the grace period logic requires an atomic "check grace_consumed_at is None, set it" operation within the same transaction, which increases conflict probability under contention.

**Recommendation:** Add a jitter (0-500ms) to client-side refresh timing to smear reconnection storms. Not a design change, just a client SDK recommendation.

---

#### M4 — MCP Simulate Concurrent Budget Is Per-Player, Not Per-Engine
**Severity:** Medium | **Category:** deferred implementation concern
**Files:** spec/core/04 §6.1

`concurrent_simulates = 3` per player. At 500 players all simulating simultaneously = 1,500 concurrent simulates. Each simulate uses a snapshot copy and up to 5000ms CPU. With 1,500 concurrent simulates × (potentially) 5s CPU = 7,500 CPU-seconds of work queued.

spec/core/04 §6.1 has per-player fuel budget (`max_fuel_per_hour = 50M`) but no global concurrency cap. The WASM sandbox pool shares resources with simulation workers — a simulation storm could starve real tick execution.

**Recommendation:** Add a global `max_concurrent_simulates` cap (e.g., 50) in addition to per-player limits. Queue simulations beyond the cap with FIFO ordering.

---

### Low

#### L1 — Challenge Cleanup Strategy Undocumented
**Severity:** Low | **Category:** doc inconsistency
**Files:** auth.md §9.1

Challenges have 5-min TTL and are marked `consumed: bool`. No FDB cleanup/GC strategy for expired challenges in `auth/challenges/`. At 10 challenge requests/min/IP (the limit in §10.7), with minimal users this is negligible. But it should be documented for completeness.

---

#### L2 — Compile Cache Key Includes `wasmtime_build_commit` — Deployment Instability on Wasmtime Patch
**Severity:** Low | **Category:** deferred implementation concern
**Files:** spec/security/09 §3.5, spec/core/04 §2.1

spec/core/04 §2.1: wasmtime version locked at `=30.0`. The compile cache key includes `wasmtime_build_commit`. A CVE-patch bump of wasmtime (e.g., 30.0 → 30.1) changes the build commit, invalidating all cached compilations. This is correct — you want to recompile under the new runtime — but is a deployment-time surprise if the operator doesn't expect it.

**Recommendation:** Add a note in RUNBOOK.md §2 (密钥轮换) or a new section documenting that wasmtime version bumps trigger full module recompilation and the expected duration.

---

#### L3 — MCP Tool Count Discrepancy Between Documents
**Severity:** Low | **Category:** doc inconsistency
**Files:** design/interface.md §4.1 vs specs/reference/mcp-tools.md

interface.md lists `swarm_dry_run_commands` as a debug tool. mcp-tools.md does not list it. interface.md lists `swarm_get_available_actions` under learning; mcp-tools.md lists it under development assistance. Minor inconsistencies — no performance impact but worth harmonizing.

---

## Questions / Assumptions

1. **Certificate chain verification caching.** The review assumes no caching because none is documented. If caching is intended but just not written down, the criticality of C2 drops to Low. Please confirm.

2. **FDB cluster sizing.** The 28,000 auth writes/tick model assumes a single FDB cluster handling both auth and game state. If auth has a dedicated FDB instance (or namespace-level isolation with separate transaction logs), write contention is reduced. Is this the plan?

3. **Nonce storage architecture.** The review assumes FDB persistence for every request nonce. If the intent is an in-memory nonce window (Dragonfly) with periodic checkpointing to FDB, C1's severity drops. The design docs are ambiguous here.

4. **Dragonfly auth caching.** Is Dragonfly planned for auth subspace caching? The architecture (FDB authoritative + Dragonfly read replica) is already in place for game state but auth.md doesn't mention it.

5. **Parliament consensus note.** Several findings (C1, H2, M2) border on architecture concerns (data store contention, cache layering). If the architect reviewers flag the same issues, they should be resolved before implementation. If they do not, the performance-only perspective may be overly conservative for MVP scale.

---

## Summary Table

| ID | Severity | Category | Summary |
|----|----------|----------|---------|
| C1 | Critical | deferred impl | Per-request FDB nonce writes: ~28K/tick, no cleanup strategy, competes with game state transactions |
| C2 | Critical | deferred impl | No certificate chain verification caching — 50K Ed25519 verifications/tick, intermediate CA re-verified per request |
| H1 | High | security/perf | Federation CRL polling window (3600s) causes cascading unavailability; no push-based distribution |
| H2 | High | doc inconsistency | Auth subspace FDB-only — no Dragonfly caching strategy documented for hot auth reads |
| H3 | High | deferred impl | Security epoch bump invalidates all compile caches → N-simultaneous recompiles, hours of player downtime |
| M1 | Medium | deferred impl | Pathfinding fuel model allows grief-budget (10× max pathfind = 50M fuel) within per-tick limits |
| M2 | Medium | doc inconsistency | Nonce replay window size not explicitly stated in §5.6 canonical request spec |
| M3 | Medium | deferred impl | Refresh token rotation grace period creates FDB contention during reconnection storms |
| M4 | Medium | deferred impl | MCP simulate concurrency is per-player only — no global engine cap |
| L1 | Low | doc inconsistency | Challenge TTL cleanup strategy undocumented |
| L2 | Low | deferred impl | Wasmtime version bump invalidates all compile caches — no operator guidance |
| L3 | Low | doc inconsistency | MCP tool list discrepancy between interface.md and mcp-tools.md |

---

## No-Blocker Justification

The design passes at `CONDITIONAL_APPROVE` rather than `REQUEST_MAJOR_CHANGES` because:

1. **All findings are additive, not architectural.** C1 (nonce storage) and C2 (cert caching) are optimization layers — they don't change the certificate model, CSR flow, or trust topology. They can be layered on post-MVP without refactoring.

2. **MVP scale is bounded.** The engine targets 500 players (engine.md §3.1a, spec/core/04 §6). At 500 players, C1 is ~9,333 writes/second — heavy for FDB but not catastrophic. C2 is ~17K verifications/second — within single-core Ed25519 capacity. The design works at MVP; it just won't scale to Tier 2 without the recommended changes.

3. **The core performance primitives are correct.** Ed25519, blake3, argon2id, fuel metering, epoch interruption, snapshot architecture — all are well-chosen and correctly integrated. The issues are in the operational layers (caching, storage, cleanup) that accumulate at scale.

4. **No correctness issues found.** The certificate chain model, nonce freshness, signature verification order, and scope/audience checks are internally consistent. This is a performance review, and no security bypass or data corruption paths were identified.

The conditions for approval are: (a) document a certificate verification caching strategy before Phase 1 implementation, (b) define the nonce storage architecture (FDB vs Dragonfly + checkpoint), and (c) add a Dragonfly auth subspace caching plan with TTLs.
