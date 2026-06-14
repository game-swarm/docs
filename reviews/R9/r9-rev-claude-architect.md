# R9 Architecture Review — Architect Reviewer

> Reviewer: Claude (Architect)
> Date: 2026-06-14
> Source under review: `reviews/r9-arch-summary.md` (Phase 0 Architecture Freeze)
> Scope: Tick lifecycle, determinism contract, deferred command model, FDB semantics, WASM sandbox, IDL, ECS ordering, source gate, fuel refund

---

## VERDICT: CONDITIONAL_APPROVE

The design is coherent, security-conscious, and unusually rigorous about determinism and abuse resistance. The deferred-command model, the single validation pipeline, the unforgeable auth context, and the fuel-refund safety model are production-grade thinking. I'm withholding unconditional approval because of two issues that can block implementation at scale (FDB transaction sizing, and intra-system entity iteration order in Bevy) plus a few correctness/clarity gaps that should be closed before code freeze. None of these are fatal; all have known mitigations.

---

## Issues

### HIGH

**H1. FoundationDB hard transaction limits vs. whole-tick commit.**
Section 4 wraps the entire EXECUTE phase in one transaction and writes `/tick/{N}/state → 完整世界状态` plus commands, rejections, and metrics. FDB enforces a **hard 10 MB write limit and 5 s duration limit per transaction**. A full world-state write every tick will exceed 10 MB for any non-trivial world and is the single biggest feasibility risk in the design. This also contradicts Section 1, which says full snapshots are written only "每 N tick" during BROADCAST.
- Resolution: commit **deltas** per tick (changed entities only), keep `/tick/{N}/state` as a periodic checkpoint (every N ticks), and verify worst-case per-tick write size against the 10 MB ceiling. State the per-tick write budget explicitly and add a guard that abandons/degrades a tick whose write set approaches the limit. Reconcile §1 and §4.

**H2. Intra-system entity iteration order is not pinned.**
The determinism contract handles command ordering `(shuffle_order, player_id, cmd_seq)` and bans `std::HashMap`, but says nothing about **entity iteration order inside ECS systems**. Bevy query iteration order follows archetype/table storage and spawn history; it is **not guaranteed stable** across runs, versions, or after entity moves between archetypes. Any system where outcome depends on visit order (resource contention, combat target selection, spawn placement) can diverge.
- Resolution: require systems with order-sensitive effects to sort by a stable key (e.g. `ObjectId`) before applying, or process entities strictly through the pre-sorted command list rather than raw queries. Add this as an explicit determinism pillar and a CI replay assertion that would catch archetype-order drift.

### MEDIUM

**M1. seccomp whitelist may starve the host runtime.**
Section 5 bans `clock_gettime`/`getrandom` at the seccomp(bpf) layer. seccomp applies to the **whole worker process, not just the guest**. Rust std, allocators, and Wasmtime itself may call `clock_gettime` (e.g. `Instant`, jemalloc/mimalloc timers) and `getrandom` (HashMap seed init, TLS). Epoch interruption runs on a host thread and may need a clock. A too-aggressive whitelist will SIGSYS the worker rather than the guest.
- Resolution: enforce guest determinism at the **WASI/host-function layer** (already done via the full-deny whitelist), and keep seccomp scoped to what the host runtime genuinely needs. Validate the whitelist against the actual Wasmtime/std syscall set under load before freezing it.

**M2. Per-tick fork + module load cost.**
Section 5 forks a fresh process, loads WASM, executes, and kills it every tick per player. Fork + JIT compile + teardown per player per tick is heavy and may not fit the 2500 ms COLLECT budget at scale.
- Resolution: use a **pre-forked worker pool** and **precompiled modules** (`Module::deserialize` from cached `.cwasm`, compiled once at deploy time and invalidated on `module_hash` change). Keep the "no cross-tick state" guarantee by resetting the Store/instance per tick rather than the whole process.

**M3. EXECUTE is fully serial within a 500 ms budget.**
All commands flow through `.chain()` ECS serially. For large worlds the 500 ms ceiling plus the single FDB commit (H1) is the throughput bottleneck. The roadmap's `.before()/.after()` partial parallelism is mentioned but unspecified.
- Resolution: define the target entity/command counts per tick and benchmark the serial path against 500 ms early. Identify which systems are commutative and safe to parallelize without breaking H2.

**M4. COLLECT reproducibility is conflated with the replay guarantee.**
The replay contract (§2) correctly replays from **recorded RawCommands**, so the wall-clock `epoch interruption (2500ms)` timeout in COLLECT does not break replay — good. But this means COLLECT itself is **not reproducible** (wall-clock timeouts vary run to run), and the fuel limit's role is fairness/DoS, not determinism. The summary presents fuel as a determinism pillar, which is misleading.
- Resolution: state explicitly that determinism/replay covers EXECUTE only, that COLLECT output is captured as authoritative input, and that wall-clock timeout is acceptable precisely because its result is recorded. Clarify fuel's purpose as fairness, not replay.

### LOW

**L1. `host_path_find` determinism.** Pathfinding affects command output. During live play, identical inputs across players should yield identical paths (integer cost, fixed tie-break). Replay is safe (commands recorded), but document the determinism/tie-break rule for fairness and to avoid surprising authors.

**L2. Abandon-then-retry semantics.** On FDB commit failure with up to 3 retries, confirm the retry reuses the already-collected command set (deterministic re-apply) rather than re-running COLLECT, and that fuel refund + re-credit cannot be double-counted across the retry.

**L3. Wasmtime version pinning for replay.** §2 conditions replay on "相同 Wasmtime 版本". Document the upgrade/migration story: re-checkpoint full state at the version boundary so historical replays remain valid across engine upgrades.

---

## Strengths

- **Deferred command model is the right core decision.** No mutating host functions; every entry point (WASM/MCP/REST/admin/rule-mod) funnels through one `validate → apply` pipeline. This eliminates an entire class of bypass and trust bugs and makes the system auditable.
- **Determinism contract is disciplined.** Blake3 for both hashing and PRNG (one primitive), banning f64, `indexmap` over `std::HashMap`, seeded shuffle for execution order, and a `state_checksum` in TickTrace with CI random-sample full replay. This is exactly how you keep a simulation reproducible.
- **Unforgeable, server-injected auth context.** `source`, `player_id`, `cert_fingerprint`, `module_hash`, session/tick fields cannot be self-reported by clients. Combined with the Source Gate matrix and Ed25519 short-lived certs, the threat model for command spoofing and privilege escalation is well covered.
- **Two-layer WASM isolation.** OS layer (seccomp + cgroup v2 + no network namespace + read-only rootfs) plus Wasmtime layer (fuel, static 64 MB memory, guard pages, no threads, bounded module/output sizes) is defense-in-depth done properly. Lenient single-player failure isolation keeps the world live.
- **IDL as single source of truth** with `gen-api` + `git diff --exit-code` in CI, an explicit `abi_version`, and "no hand-written Command variants" is the correct way to keep Rust/TS/MCP/docs/tests from drifting.
- **Fuel-refund safety model is notably mature.** Next-tick credit binding, deploy-reset to prevent cross-module budget transfer, abuse-rate throttling, and same-source repeat-failure decay close the obvious gaming vectors most designs miss entirely.
- **Tutorial isolation** via namespace separation and silent-drop-plus-audit on world-mode mismatch is clean and prevents tutorial traffic from contaminating live worlds.
- **Graceful degradation path** (3 consecutive abandons → pause joins / block deploys → auto-recover after 10 clean ticks) shows operational maturity.

---

## Recommended gating conditions before code freeze

1. Resolve **H1** — prove the per-tick write set fits FDB's 10 MB / 5 s limits; switch to delta commits with periodic checkpoints; reconcile §1↔§4.
2. Resolve **H2** — add a stable intra-system ordering rule and a CI replay test that exercises archetype reordering.
3. Validate **M1** seccomp whitelist against the real host syscall set, and prototype **M2/M3** to confirm the COLLECT/EXECUTE time budgets hold at target scale.
4. Tighten the **M4** wording so determinism scope is unambiguous.

Address H1 and H2 and this is a clear APPROVE.
