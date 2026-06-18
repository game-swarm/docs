# R14 Architecture Review — rev-dsv4-architect (DeepSeek V4 Pro)

> Phase 1 Clean-Slate Independent Review
> Reviewer: Architect direction (ECS scheduling, Tick lifecycle, Data consistency, Algorithm complexity)
> Documents reviewed: design/README.md, design/engine.md, design/tech-choices.md, specs/core/01-tick-protocol.md, specs/core/02-command-validation.md, specs/core/04-wasm-sandbox.md

---

## 1. Verdict

**REQUEST_MAJOR_CHANGES**

The design has a strong conceptual foundation — the three-phase tick model, FDB atomic commits, and deferred WASM command model are well-conceived. However, there are **critical cross-document contradictions** in ECS system ordering, **missing systems** in the authoritative chain, and **undefined crash-safety semantics** around fuel deduction that must be resolved before implementation. These are not minor clarifications; they directly affect determinism guarantees, gameplay behavior, and the parallel safety proof.

---

## 2. Findings

### Critical

**C1: `regeneration_system` ordering contradiction between engine.md and 01-tick-protocol.md**

- **engine.md §3.2** (high-level Phase 2b diagram):
  ```
  death_mark → spawn → combat → regeneration/decay(parallel) → death_cleanup
  ```
  Shows regeneration **after** combat, running in parallel with decay.

- **01-tick-protocol.md §3.4** (authoritative Rust `.chain()` code):
  ```
  death_mark → pvp_block → spawn → regeneration → ...(9 systems)... → combat → decay → ... → death_cleanup
  ```
  Shows regeneration **before** combat, running serially in the main chain — not parallel at all.

- **Impact**: If regeneration runs before combat, freshly regenerated resources are available for combat damage calculations in the same tick. If it runs after, only pre-combat resource states matter. These produce different world states, breaking determinism. The parallel safety proof in §3.4 (regeneration only writes `Energy/Carry`, no conflict with combat's `HitPoints` write) is correct regardless of ordering, but the **gameplay semantics** differ fundamentally.

- **Recommendation**: Declare one ordering as authoritative. If regeneration-before-combat is intended (enabling same-tick resource availability for combat), update engine.md and the parallel labeling. If combat-before-regeneration is intended, fix the chain in 01-tick-protocol.md. Update the determinism contract (§9.6) accordingly.

---

**C2: `status_advance_system` and `aging_system` are missing from the authoritative ECS chain**

- **01-tick-protocol.md §9.6** specifies:
  > 所有特殊攻击的状态推进（Overload fuel 恢复、Hack stage 递增、Debilitate 计数递减、Fortify 护盾递减）由 `status_advance_system` 统一处理，位置在 `combat_system` 之后、`aging_system` 之前。

- **02-command-validation.md §3.19** specifies:
  ```
  death_mark → spawn → spawning_grace → combat → status_advance → (regeneration, decay 并行) → death_cleanup
  ```

- **01-tick-protocol.md §3.4** (the actual Rust code): Neither `status_advance_system` nor `aging_system` appears in the 19-system `.chain()`. Without `status_advance_system`, Hack stages never increment, Overload fuel never recovers, Debilitate/Fortify counters never decrement — all special attacks become permanent effects. Without `aging_system`, drone lifespan never advances — drones never die of old age.

- **Impact**: The design references systems that don't exist in the implementation chain. This is a critical gap that would render core game mechanics non-functional.

- **Recommendation**: Add `status_advance_system` and `aging_system` to the authoritative chain at the positions specified by the design documents. Update the Component read-write matrix to include their access patterns.

---

### High

**H1: RoomCap intermediate-state window lacks enforcement mechanism**

- **engine.md §3.2** acknowledges:
  > 在 `death_mark_system` 与 `spawn_system` 之间的任何 ECS system 不得读取 RoomCap 做准入决策

  But this is a **documented convention**, not a compile-time or runtime enforcement. The chain has `pvp_block_system` between `death_mark` and `spawn`. Any system inserted into this window (by a mod, Rhai script, or future engine developer) that reads RoomCap will observe the intermediate state where slots have been released but not yet consumed.

- **Recommendation**: Add a Bevy run condition or compile-time lint that rejects systems in this window that declare `RoomCap` reads. Alternatively, restructure to have `death_mark` and `spawn` adjacent in the chain with no intervening systems.

---

**H2: Process crash between COLLECT completion and FDB commit loses fuel without refund**

- **01-tick-protocol.md §6.1** (Failure Semantics Matrix) covers: COLLECT crash, Phase 2a panic/OOM, WASM timeout, WASM crash, WASM output invalid, FDB commit fail, Dragonfly cache miss/stale, NATS publish fail, broadcast partial, TickTrace write fail, replay write fail.

- **Missing scenario**: Engine process crashes after COLLECT succeeds (WASM executed, fuel consumed, commands collected) but before FDB commit completes. On restart, the engine replays from the last committed tick. Players lose fuel for work that was executed but never persisted. The design's fuel refund mechanism (§3.5: "放弃的 tick：消耗的 CPU fuel 退还玩家") requires the process to be alive to execute the refund path.

- **Impact**: In the 500-player target, at 3s ticks, this is a rare but real scenario (power loss, kernel panic, OOM killer). Affected players lose up to 10M fuel per crash event.

- **Recommendation**: Either (a) make fuel deduction part of the same FDB transaction as state changes (atomic commit), or (b) explicitly document this as an accepted risk with operational mitigations (UPS, watchdog timers, crash-rate SLA). Option (a) is architecturally cleaner but requires FDB to track per-player fuel counters — which it already does for `consumed_fuel` in TickTrace (§9.4).

---

**H3: Spawn body_cost pre-deduction is vulnerable to the same crash window as H2**

- **02-command-validation.md §3.8**: body_cost is deducted in Phase 2a inline apply, but the drone is created in Phase 2b spawn_system. If spawn_system fails (room cap race), body_cost is refunded. But if the process crashes between Phase 2a deduction and Phase 2b refund, the deduction is lost.

- This is a finer-grained instance of H2. Same recommendation applies.

---

### Medium

**M1: Component read-write matrix is incomplete — only covers 6 of 19+ systems**

- **01-tick-protocol.md §3.4** provides a read-write matrix for: death_mark, spawn, combat, regeneration, decay, death_cleanup.
- **Missing from matrix**: pvp_block, seed_rotation, cargo_in_transit, global_storage, controller, controller_repair, depot_repair, room_state, memory_upkeep, drone_env_var, rhai_rule_module_tick_start/end, onboarding, and all conditional/parallel systems (npc_ai, npc_combat, stronghold_*, world_event, spawning_grace, code_propagation).
- The parallel safety proof for regeneration/decay relies on "no other system accesses these components." Without a complete matrix, this is unverifiable.
- **Recommendation**: Extend the matrix to cover all systems in the chain. This is essential for verifying the determinism contract.

---

**M2: MCP query read-source semantics during EXECUTE phase are undefined**

- **01-tick-protocol.md §2.3** (快照构建时序边界): MCP `swarm_get_snapshot` reads from the COLLECT snapshot (step [1]), which exists during COLLECT phase.
- During EXECUTE (including FDB retries), the COLLECT snapshot is no longer the working state — Bevy World is being modified. What does MCP query return during EXECUTE?
- **01-tick-protocol.md §6.4** says "当前世界状态（snapshot）→ Bevy World（内存）| COLLECT 阶段已构建，最新" — but during EXECUTE, the COLLECT snapshot may be stale or consumed.
- **Recommendation**: Define MCP query semantics during EXECUTE: either (a) preserve the COLLECT snapshot for the full tick duration and serve queries from it, or (b) block MCP queries during EXECUTE, or (c) serve from the last committed FDB state. Document the choice in §6.4.

---

**M3: path_find cache key omits structure/buildings**

- **04-wasm-sandbox.md §8**: `host_path_find` cache key = `(from, to, terrain_hash, player_visibility_fingerprint)`.
- Buildings (walls, structures) affect pathfinding but are not captured by `terrain_hash` if terrain and structures are separate component types. If a player builds a wall between cached `from→to`, the stale cached path would route through the wall.
- **Recommendation**: Include `structure_hash` or an `obstruction_hash` in the cache key that captures all path-blocking entities in the affected area.

---

**M4: Recycle lifespan-refund formula verified correct, but boundary at 20% remaining needs clarification**

- **02-command-validation.md §3.18**: `refund_pct = max(0.1, 0.5 × (remaining_lifespan / total_lifespan))`
- At 20% remaining: `0.5 × 0.2 = 0.1`. The floor and the formula meet at exactly 10%. At 19% remaining: `0.5 × 0.19 = 0.095 → max(0.1, 0.095) = 0.1`. The transition is continuous at the floor.
- Economic constraint verified: no arbitrage possible. 10% refund < 100% build cost.
- **Low severity, informational**: Document the breakpoint explicitly (20% remaining = transition to floor).

---

### Low

**L1: TickTrace audit field limits may lose forensic data for complex attacks**

- **04-wasm-sandbox.md §6.2**: RawCommand body truncated to 1KB (hash + 200 char preview), Rejection detail capped at 512 bytes.
- For complex multi-target attacks (e.g., Overload with 50 targets), the truncated command body may lose contextual information needed for abuse investigation.
- **Recommendation**: Consider per-command-type retention policies — critical commands (Hack, Overload) could have higher body retention limits.

---

**L2: `seeded_shuffle` seed derivation uses `tick_number` directly concatenated with `world_seed`**

- **01-tick-protocol.md §3.1**: `seed = blake3::hash(&[&tick_number.to_le_bytes(), &world_seed])`
- This is correct for determinism. The forward secrecy analysis (§3.1 threat model) is thorough and the accepted risk is well-documented. No issue — just noting this is architecturally sound.

---

**L3: WASM `tick()` output truncation at 256KB lacks partial-parse safety analysis**

- **01-tick-protocol.md §9.7**: "WASM tick() 输出上限 256KB。超出时整批丢弃——不保留部分解析的前缀。"
- **02-command-validation.md §1.1** (JSON Schema): "包含非 JSON 字节序列（二进制垃圾）→ 校验失败，整个 tick 输出丢弃"
- If WASM produces 255KB of valid JSON + 2KB of binary garbage, the output is entirely discarded. This is safe but could be surprising to SDK developers who accidentally include debug prints. Low-priority, but consider a configurable warning threshold (e.g., warn at >200KB before hard-reject at 256KB).

---

## 3. Strengths (亮点)

1. **Three-phase tick model (COLLECT → EXECUTE → BROADCAST)** with clear separation of concerns. The "build snapshot once, filter per-player" optimization (O(E + P×V) instead of O(P×E)) is a well-reasoned performance improvement.

2. **FDB strict serializability for atomic tick commits** is the correct choice. The design correctly identifies that partial commits would break replay determinism. The retry-with-cached-COLLECT strategy avoids re-executing WASM on transient failures.

3. **Deferred command model** (WASM returns JSON commands, engine applies them) is architecturally superior to direct host function mutation. It enables: unified validation, replay from recorded commands, and prevents WASM from observing intermediate world states.

4. **Blake3 unifying hash + PRNG** eliminates a dependency (ChaCha), reduces audit surface, and the XOF mode with seed+offset is an elegant fit for per-entity deterministic random streams.

5. **Seeded shuffle for player ordering** correctly balances determinism (same seed → same order) with fairness (long-term expectation equal across players). The forward secrecy analysis and accepted risk documentation is exemplary.

6. **Comprehensive failure semantics matrix** (§6.1 in 01-tick-protocol.md) — 14 failure modes with impact analysis, recovery strategies, and degradation paths. This level of operational thinking in a design document is rare and valuable.

7. **Anti-abuse detection patterns** (§2.3 in 01-tick-protocol.md): entity inflation attack detection, export vision expansion detection, truncation frequency monitoring, path_find cache miss throttling — all well-defined with specific thresholds and responses.

8. **WASM sandbox boundary** (seccomp, cgroup v2, network namespace, restricted WASI) is thorough and well-documented. The malicious WASM sample library for CI testing (§5 of 04-wasm-sandbox.md) is a strong security practice.

9. **Move-as-action design choice** is well-justified with explicit reasoning about determinism, programming-game philosophy, and TOCTOU elimination. The document acknowledges this may be challenged in playtest — good engineering humility.

10. **Snapshot truncation with deterministic ordering** (§2.3): the priority bucket system + stable entity_id sort guarantees replay-identical truncation. The player-predictability documentation (what players can infer about truncation) is useful for SDK design.

---

## 4. CrossCheck — 需要跨方向检查

- **CX1**: regeneration_system ordering contradiction (C1 above) affects both determinism and gameplay balance. → 建议 **Game Designer (rev-gpt-designer)** 检查: should resources regenerate before or after combat in the same tick? What gameplay dynamics does each ordering create?

- **CX2**: Missing status_advance_system and aging_system (C2) → 建议 **Architect (rev-claude-architect)** 验证完整的 20+ system chain against the determinism contract §9.6, and confirm that all referenced systems have defined positions.

- **CX3**: RoomCap intermediate-state window (H1) — the design relies on convention, not enforcement. → 建议 **Security (rev-dsv4-security)** 审查: could a malicious Rhai mod exploit the RoomCap window to exceed per-room drone limits?

- **CX4**: Process crash fuel-loss scenario (H2) — the failure matrix covers 14 modes but omits engine process crash. → 建议 **Architect (rev-claude-architect)** 检查: does the existing FDB schema support atomic fuel deduction? Is the implementation complexity of moving fuel into the FDB transaction acceptable?

- **CX5**: path_find cache key missing structures (M3) — this is a correctness issue that could affect gameplay. → 建议 **Security (rev-dsv4-security)** 审查: can a malicious player exploit stale pathfinding caches to route drones through walls?

- **CX6**: Component read-write matrix incompleteness (M1) — the parallel safety proof for regeneration/decay is unverifiable without a full matrix. → 建议 **Architect (rev-claude-architect)** 验证: are there hidden data races between the 19+ systems in the chain?

---

*Review completed 2026-06-18 by rev-dsv4-architect (DeepSeek V4 Pro)*
