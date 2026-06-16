# R3 Architect Review — rev-dsv4-architect (DeepSeek V4 Pro)

Date: 2026-06-16
Documents reviewed: DESIGN.md (2364 lines) + specs/01-09 + api/commands.md + api/mcp-tools.md + ROADMAP.md
Review scope: ECS scheduling, tick lifecycle, FDB+Dragonfly data consistency, algorithmic complexity

---

## Verdict: APPROVE (with 2 documentation fixes recommended)

The design is mature and well-considered. The FDB-centric consistency model is correct, ECS scheduling is sound (Bevy handles component access conflicts automatically), all algorithmic paths are within bounds. No blocking design flaws found. Two documentation inconsistencies and three edge case clarifications recommended.

---

## Strengths

**S1. Deterministic core is comprehensive and correct.** Blake3 XOF for seeded shuffle, IndexMap for deterministic iteration order, fixed-point arithmetic throughout, `.chain()` ordering on data-dependent ECS systems, and seed rotation every 10K ticks with epoch tracking. The determinism contract (§8.8 + spec 01 §3.2) leaves no gaps.

**S2. FDB atomic commit model is the correct choice.** Single FDB transaction wrapping entire Phase 2 (validate + apply + commit) guarantees tick atomicity. The Bevy World snapshot/restore mechanism (spec 01 §3.5) correctly handles FDB rollback — captured Resource types and all ECS Components are restored on commit failure. COLLECT result caching across retries prevents double fuel billing.

**S3. Phase 2a TOCTOU contract is thoroughly specified.** Five protection rules (spec 01 §3.3): Spawn pending invisible, Hack ownership semantics correct, per-drone per-tick action quota, fuel exhaustion discards full output, no cross-tick command carry. All correctly prevent time-of-check-to-time-of-use attacks in the inline execution model.

**S4. Two-phase snapshot architecture is algorithmically sound.** Build complete snapshot once, partition by room, filter per player — O(entities + players × visible_rooms) vs naive O(players × entities). For 10K entities + 500 players: 14.5K vs 5M units of work (344× reduction). Truncation at 256KB with distance-prioritized sorting is a principled trade-off.

**S5. WASM pre-compilation eliminates tick-time JIT latency.** Compile at deploy time, store native code by (module_hash, wasmtime_version), instance only at tick time. Combined with per-tick sandbox worker fork/kill lifecycle — no cross-tick state leakage, no resource accumulation.

**S6. MCP architecture is correctly positioned.** MCP as management/monitoring interface (not gameplay input), AI agents write WASM code deployed through WasmSandboxExecutor — identical path to human players. No McpPlayerExecutor exists. This was a critical correction from earlier rounds.

**S7. Source model is exhaustively enumerated.** spec 09 comprehensively defines 11+ source types with per-source capability matrices, auth context requirements, and rate limits. The Ed25519 client-key + server-certificate deployment signing model (with nonce, CRL, epoch) provides strong audit trail.

**S8. Command validation pipeline is single-path.** All mutating operations go through `validate_and_apply()` — WASM tick output, Admin, RuleMod, Tutorial. The `WorldMutate` trait has exactly one implementor (spec 09 §2.3). No bypass paths exist.

---

## Concerns

### D1: Phase 2b parallelism claim is imprecise (documentation — non-blocking)

DESIGN.md §3.2 states regeneration and decay "并行" with the mainline chain. spec 01 §3.4 says "与主线并行调度（Bevy 自动管理线程）". The RW matrix (spec 01 §3.4) reveals:
- `spawn` writes `Cooldown` on Drone archetype
- `decay` writes `Cooldown` on Drone archetype
- `spawn` writes `Energy/Carry` on Drone archetype
- `regeneration` writes `Energy/Carry` on Source archetype

**Analysis**: Spawn and Decay both access `Cooldown` mutably on Drone archetype — Bevy's scheduler will serialize them. Spawn and Regeneration write `Energy/Carry` but on DIFFERENT archetypes (Drone vs Source), so they CAN run in parallel.

**Conclusion**: The claim "regeneration and decay run in parallel with the mainline" is partially correct (regeneration can, decay cannot during the spawn window). This is not a correctness bug — Bevy automatically handles conflicts — but the documentation should be more precise. The practical observation is that the parallelism benefit is limited to regeneration only.

**Recommendation**: Clarify in spec 01 §3.4 that decay's parallelism with spawn is limited by Cooldown component access, and that this is handled automatically by Bevy's scheduler.

### D2: Hack maturity vs Recycle race condition is correctly resolved but undocumented (clarity)

Edge case: A drone under Hack (stage 5, about to flip to Neutral) receives a Recycle command from its original owner in Phase 2a of the same tick. Per the TOCTOU contract, the command is validated as if the drone still belongs to the original owner.

**Resolution path**: Recycle in Phase 2a (inline) → drone gets death_marked → Hack handler in Phase 2b sees death_mark and skips ownership transfer. Recycle wins over Hack takeover. This is correct but should be explicitly documented as the resolution order.

**Recommendation**: Add to spec 01 §3.3 TOCTOU contract or spec 02 §3.10 Hack section: "若 Hack 控制锁到期（stage 5）的同 tick 内原 owner 执行 Recycle，Recycle 优先生效（Phase 2a inline 先于 Phase 2b handler），Hack 自动跳过已 death_mark 的目标。"

### D3: Dragonfly read path during tick transition is unspecified (documentation gap)

DESIGN.md §6.2 positions Dragonfly as hot cache for "当前 tick 世界状态快照（高频读取）". spec 01 §4.2 says Dragonfly updates happen in BROADCAST phase, after FDB commit. Between Tick N's FDB commit and Tick N's Dragonfly update, a reader sees Tick N-1's state.

**Question**: Which reads go through Dragonfly vs FDB? MCP `swarm_get_snapshot` — cache or authoritative? WebSocket initial state push — cache or authoritative? The design doesn't specify.

**Risk assessment**: If MCP tools serve from Dragonfly, AI agents may see up to one full tick of stale data. If from FDB, there's a latency trade-off. For correctness, all gameplay-significant reads should hit FDB; Dragonfly should serve only presentation-layer reads (Web UI rendering, spectator views).

**Recommendation**: Add a read-path routing table to spec 01 or DESIGN.md §6.2 specifying which read operations go through which data source, and the staleness bound each tolerates.

### D4: Controller + Depot shared RepairTracker hard cap interaction (balance concern — non-blocking)

DESIGN.md §8.2: "每 tick 总 age 回退不超过自然增长（+1/tick）的 50%". ROADMAP confirms Controller + Depot share `RepairTracker` hard cap.

With 1000 drones: max_age_reduction = 500/tick. A RCL8 Controller provides 80/tick, requiring 42 Depots (10/tick each, consuming maintenance resources) to saturate the cap. This creates an interesting economic tension but the 500/tick cap means 500 drones age naturally (+1/tick) without any reduction possible — they will eventually die even with maximum repair infrastructure.

**Observation**: This is a deliberate "soft ceiling" on army size. Even with perfect logistics, 50% of drones get no age reduction. The 1500-tick lifespan means a drone lives ~1500 ticks without repair, ~3000 ticks with maximum repair. This is tunable via world.toml and represents a conscious design choice, not a flaw.

### D5: Seed rotation epoch boundary in replay verification (implementation risk)

world_seed rotates every 10K ticks via `Blake3(old_seed || current_tick)`. TickTrace records seed epoch per tick. A replay spanning ticks 9998-10003 must track two seed epochs.

The design says "回放时按 epoch 选择对应种子" — correct but adds replay infrastructure complexity. If the replay verifier incorrectly handles the epoch boundary (e.g., uses wrong seed for tick 10000), state_checksum will mismatch.

**Recommendation**: Add a CI test specifically for seed rotation boundary replay: execute ticks 9990-10010, verify replay across the boundary produces identical state_checksums.

---

## Consistency Gaps

### CG1: Direction system inconsistency (documentation bug)

- DESIGN.md §3.1a 出口规则: "N/S/E/W 四个方向" (4 directions, square grid)
- spec 01 §1.2: "N/S/E/W 四个方向" (4 directions)
- spec 02 §3.1 Move validation: "Direction 是合法四方向邻居 (N/S/E/W)"
- spec 08 IDL enum: `Direction: [North, South, East, West]` (4 values)
- api/commands.md Move example: `"direction": "TopRight"` (8-direction name!)
- spec 02 field-level table: "目标格六邻可达" (hexagonal grid phrasing!)

"六邻" (6 neighbors) suggests hexagonal grid adjacency. "TopRight" suggests 8-direction square grid. The rest of the design specifies 4-direction square grid.

**Root cause**: The "六邻可达" and "TopRight" are likely stale artifacts from earlier design iterations. The converged design uses 4 cardinal directions on a square grid.

**Fix**: Replace "六邻可达" with "四邻可达" in specs/02-command-validation-spec.md field-level table, Row "Move". Update api/commands.md Move example to use a valid direction like "North".

### CG2: Per-drone action quota interaction with continuous effects (ambiguity)

TOCTOU rule 3: "每 drone 每 tick 最多执行 1 个 main action". Drain is a continuous effect — once started, it transfers resources each tick. 

**Question**: Does maintaining Drain count as the "one main action" for subsequent ticks?

DESIGN.md special attack rules say: "同 tick 只能执行一种" — this implies YES, Drain IS the main action for each tick it's active. The drone cannot Drain AND Move in the same tick. But the spec doesn't explicitly state whether a continuous Drain blocks other actions on subsequent maintenance ticks.

**Recommendation**: Add to spec 02 Drain section: "持续 Drain 期间的每个 tick，Drain 占用该 drone 的 main action 配额（不可同时执行 Move/Attack/Harvest 等）。移动或 Disrupt 会中断 Drain。"

---

## Algorithmic Risks

### AR1: Seeded shuffle — PASS
Fisher-Yates via Blake3 XOF. For N=500 active players: 500 XOF reads. Blake3 at ~6 GB/s → negligible.

### AR2: Visibility computation — PASS  
500 players × ~1000 visible entities = 500K `is_visible_to` checks/tick. Each check is O(1) distance + hash lookup. Visibility cache (spec 05 §5) computed once per tick per player. ~167K checks/sec at 3s tick interval. No risk.

### AR3: Snapshot partitioning — PASS
O(entities + players × visible_rooms). 10K entities + 500 players × 9 rooms = 14.5K work units vs 5M naive. 344× reduction.

### AR4: Delta computation — PASS  
Entity delta via ID hash set comparison. O(entities). For 10K entities with ~10% churn: ~1K delta entries. Negligible.

### AR5: Rhai action budget — PASS
100K AST node hard cap per mod per tick. AST node count is deterministic (same input = same termination point). Timeout is wall-clock-monitored for ops alerting only, not used as a state determinant. Correct approach for deterministic budget enforcement.

### AR6: WASM fuel metering at scale — PASS
500 concurrent sandbox workers, each forked per tick, 10M fuel budget. Worker pool parallelism handles this. 10M instructions × 500 players = 5B instructions/tick at native WASM speed (~100M instructions/sec per core) = 50 core-seconds spread across worker pool. Manageable.

---

## FDB + Dragonfly Consistency Verification

| Path | Write authority | Read source | Staleness bound | Correct? |
|------|----------------|-------------|-----------------|----------|
| Tick state write | FDB (atomic) | — | — | ✅ |
| Tick state read (gameplay) | — | FDB (speculative) | 0 | ✅ (not specified but assumed) |
| Tick state read (UI/spectate) | — | Dragonfly | ~1 tick | ✅ (acceptable for presentation) |
| Dragonfly write | FDB→Dragonfly (BROADCAST) | — | Post-commit | ✅ (non-authoritative) |
| Cache miss fallback | — | FDB direct | 0 | ✅ (spec 01 §6.1) |
| BROADCAST failure | FDB already committed | — | Client sees gap | ✅ (last_tick gap detection) |

The consistency model is correct: FDB is the sole authority. Dragonfly is an eventually-consistent read cache. The one gap is explicit specification of which reads go where (see D3).

---

## Summary

The Swarm design has matured significantly through R1 and R2. The remaining issues are documentation precision rather than design flaws:

- **CG1**: Fix "六邻" → "四邻" and "TopRight" → valid direction (docs bug)
- **CG2**: Clarify Drain's continuous effect counts as main action (ambiguity)
- **D1**: Clarify Phase 2b parallelism limitations (doc precision)
- **D2**: Document Hack/Recycle resolution order (edge case clarity)
- **D3**: Specify read-path routing (FDB vs Dragonfly) (doc gap)
- **D5**: Add seed rotation boundary replay test (implementation risk)

No blocking design issues. The FDB-centric consistency model, ECS scheduling, tick lifecycle, and algorithmic complexity are all correct and well-bounded.
