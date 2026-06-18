# R18 Determinism Review — DeepSeek V4 Pro

**Reviewer**: rev-dsv4-determinism
**Date**: 2026-06-18
**Documents Reviewed**: 9 files (design/README.md, design/engine.md, game_api.idl.yaml, api-registry.md, 01-tick-protocol.md, 02-command-validation.md, 04-wasm-sandbox.md, 05-persistence-contract.md, 06-phase2b-system-manifest.md)

---

## 1. Verdict

**REQUEST_MAJOR_CHANGES** — 2 Critical findings that directly threaten replay determinism, 2 High cross-document scheduling conflicts, 3 Medium issues. The determinism contract is well-architected at the core (PRNG, IndexMap, hash-chained TickTrace) but has document drift and f64 leaks that must be resolved before implementation.

---

## 2. Findings

### Critical

**D1 — f64 in MCP Output Schemas Crosses Determinism Boundary**

The YAML IDL defines 7 MCP tools with `f64` output fields, all classified as `replay_class: read_replay_safe`:

| Tool | f64 fields |
|------|-----------|
| `swarm_get_resources` | `income_rate: f64` |
| `swarm_get_path` | `distance: f64, cost: f64` |
| `swarm_get_controller` | `progress: f64` |
| `swarm_get_economy` | `income: f64, expenses: f64, storage_tax: f64, maintenance: f64` |
| `swarm_get_drone_efficiency` | `efficiency: f64` |
| `swarm_simulate` | `confidence: f64` |
| `resources/read` | `base_value: f64` |

The deterministic contract (01-tick-protocol.md §7.1) explicitly states: "数值：整数 + 定点数，禁用 f64（跨平台/编译器非确定）". engine.md §3.4.8 mandates u64/i64 fixed-point for all game values.

**Risk**: If replay verifiers compare MCP output values (as implied by `read_replay_safe`), f64 floating-point differences across platforms/compilers will produce false replay failures. Even though the underlying game state is deterministic (integer), the f64 *presentation layer* introduces non-determinism into the replay comparison surface.

**Fix**: Either (a) change these fields to integer/basis-point types in the output schema (e.g., `income_rate_bp: u64`), or (b) downgrade the replay_class to `display_only` with an explicit statement that these values are NOT replayed. Current state: the schema says `replay_class: read_replay_safe` for all 7 tools — this is an active contract violation.

---

**D2 — Conflicting Recycle Refund Rules Between Same-Document Sections**

02-command-validation.md contains two conflicting refund formulas for Recycle:

- §10.3 (line 722): `body part spawn 总成本的 50%` (flat 50%)
- §3.18 (lines 493-500): `refund_pct = max(0.1, 0.5 × (remaining_lifespan / total_lifespan))` (proportional with 10% floor, includes lifespan-age constraint reasoning)

§3.18 is the newer, more sophisticated formula with economic anti-abuse reasoning. §10.3 appears to be a stale reference that wasn't updated when the proportional model was introduced in R16/R17.

**Risk**: If an implementer reads §10.3 alone, they'll implement flat 50% — different from §3.18's proportional model. Two different implementations = replay fork.

**Fix**: Update §10.3 to reference §3.18 as the authoritative formula, or remove the duplicate definition entirely and link to §3.18.

---

### High

**D3 — Stale status_advance_system Schedule in §3.19**

02-command-validation.md §3.19 (line 517) states:
```
death_mark → spawn → spawning_grace → combat → status_advance → (regeneration, decay 并行) → death_cleanup
```

But the authoritative manifest (06-phase2b-system-manifest.md §1) defines:
```
S07 death_marker → S08 spawn → S09 spawning_grace → S10 regeneration → S11-S13 combat → S14 special_attack_reducer → S15 damage_application → S16-S22 status (incl. status_advance at S22) → S23 aging → S24 decay → S25 death_cleanup
```

Key discrepancies:
1. §3.19 places `status_advance` BEFORE regeneration & decay; manifest places it AFTER combat + damage_application
2. §3.19 has regeneration & decay in parallel; manifest has regeneration (S10) serial BEFORE combat, decay (S24) serial AFTER aging
3. §3.19 omits `special_attack_reducer` (S14) and `damage_application` (S15) entirely
4. §3.19 omits `aging` (S23) entirely

This is a stale R15-era schedule preserved in §3.19. The note at §3.19 line 514 says "调度位置在 Phase 2b 中 combat_system 之后、regeneration_system 之前" — contradicting the manifest where regeneration is BEFORE combat.

**Risk**: If any implementer uses §3.19 as their scheduling reference, they'll produce a different system execution order than the manifest → replay will not match.

**Fix**: Replace the inline schedule in §3.19 with a reference to 06-phase2b-system-manifest.md §1 as the sole authoritative source.

---

**D4 — Worker Pool MAX_POOL Cross-Document Conflict**

| Document | Value |
|----------|-------|
| engine.md §3.4.2 line 345 | `MAX_POOL = 1000` (compile-time constant) |
| api-registry.md §5.5 line 414 | `max_pool` = 256 |
| game_api.idl.yaml §5 limits | `worker_pool_max: 256` |

engine.md also uses MAX_POOL=1000 in its 500/1000 player capacity derivation (lines 357-383), with explicit math: "1000 workers / 40 cores". If the actual limit is 256, the capacity derivation is wrong and the hard-cap 1000 player math doesn't hold.

**Risk**: Implementation could use either 256 or 1000. Different pool sizes → different sandbox scheduling → different execution ordering at the parallelism boundary. Since WASM execution is parallel within COLLECT, different pool sizes could theoretically change timing-dependent behavior (timeout patterns differ).

**Fix**: Single-source this value in the YAML/registry as authoritative. Update engine.md to reference the registry value rather than hardcoding 1000.

---

### Medium

**D5 — Per-Player Drone Cap: 500 vs 50**

| Document | Value |
|----------|-------|
| api-registry.md §5.1 | `Per-player drone cap: 500` |
| engine.md §3.4.2 | `Per-player drone cap: 500 (default, world.toml configurable)` |
| 02-command-validation.md §6 | `MAX_DRONES_PER_PLAYER: 50, 默认 50` |

02-command-validation.md §6 also has a separate Tier 1 note: "50 players × 10 drones = 500 total" suggesting a different use of "50" (maybe per-room?).

**Risk**: Low direct determinism risk (both values are configurable integer caps), but could cause validation-layer rejection differences depending on which constant the implementer uses.

---

**D6 — custom_actions Determinism Contract Gap**

The YAML IDL defines `Leech` and `Fabricate` as `custom_actions` with `action_id: custom`. The `world_action_manifest_hash` is recorded in TickTrace Envelope (field 15). However:

1. No explicit rule for where custom_actions sort in the Phase 2a command queue relative to core actions
2. 02-command-validation.md §10 includes Leech/Fabricate definitions with registration note `[[custom_actions]]` but no determinism clause
3. The RejectionReason registry has no custom-action-specific rejection codes

**Risk**: Different implementations could sort custom_actions differently in the command queue → replay divergence. The hash in the envelope proves the manifest existed but doesn't prescribe the sort order.

---

**D7 — SIMD Toggle Creates Architecture-Dependent Determinism**

| Document | SIMD Setting |
|----------|-------------|
| 04-wasm-sandbox.md §2.2 | `config.wasm_simd(world_config.simd_enabled)` — World: true (性能), Arena: false (确定性/公平) |
| engine.md §3.4.3 | "禁用的 WASI: ... SIMD" — says SIMD is **disabled** |

These are contradictory. engine.md §3.4.3 lists SIMD as explicitly disabled in "禁用的 WASI". But 04-wasm-sandbox.md has fully configurable SIMD with World=true default.

SIMD is not technically WASI — it's a Wasmtime feature flag. But the determinism implication is real: different CPU architectures (x86 AVX-512 vs ARM NEON vs x86 SSE-only) can produce different floating-point results from SIMD operations. For Arena mode (SIMD=false), this is fine. For World mode (SIMD=true default), this creates architecture-dependent determinism.

**Risk**: If World mode ships with SIMD=true, a replay on different hardware could produce different results. TickTrace `module_hash` includes WASM binary but not the CPU architecture SIMD variant.

**Fix**: Either (a) default SIMD=false for all modes (Arena-style determinism), or (b) record `simd_enabled` + CPU arch feature flags in TickTrace Envelope, or (c) only enable SIMD for integer operations (which ARE deterministic across architectures).

---

### Low

**D8 — engine.md §3.3 TickInputEnvelope vs api-registry.md §6 field count**

engine.md §3.3 lists the envelope fields descriptively (11 lines of prose) but doesn't enumerate all 22. The prose mentions `collect_id`, `attempt_id`, `commit_id` (R16 B3 additions) but also mentions `wasm_status` which has been replaced by `terminal_state` in v0.3.0. No functional gap — just stale prose.

**D9 — 02-command-validation.md §8/§10 numbering gap**

Section numbering jumps from §8 (CommandAction 变体) to §10.1 (RangedAttack) — no visible §9 section. Not a determinism issue, but suggests §9 was deleted and numbering wasn't reflowed.

---

## 3. Strengths

1. **Blake3 PRNG with namespace isolation** — Deterministic seeding + domain separation + per-entity streams. Well-designed and exhaustively documented.

2. **IndexMap over HashMap** — Correctly uses `indexmap` crate for all iteration-order-sensitive collections (Resource amounts, Source produces). Deterministic by construction.

3. **Snapshot truncation with deterministic sort keys** — `(distance_to_drone, entity_id)` sort within priority buckets guarantees replay-identical truncation results. Well-specified boundary conditions.

4. **TickInputEnvelope (22 fields)** — Comprehensive coverage of all replay-relevant inputs: module_hash, wasmtime_version, snapshot_hash, commands_hash, deploy/rollback/admin events, world_config_hash, mods_lock_hash, engine_abi_version, world_action_manifest_hash, system_manifest_hash, terminal_state. This is the gold standard for replay metadata.

5. **Hybrid commit retry with COLLECT buffer reuse** — FDB commit failure → Bevy snapshot restore → reuse canonical COLLECT buffer (no WASM re-execution) → same fuel accounting. Correctly prevents double-execution and cross-attempt drift.

6. **FDB as sole authority with WAL/object-store separation** — async blob upload doesn't block tick commit; FDB stores hash pointers only; orphan cleanup well-defined.

7. **5-layer command sort key** — `(priority_class, shuffle_index, source_rank, sequence, command_hash)`. Fully specified, tiebreaker at every layer, seed determinism documented.

8. **Phase 2b Component R/W matrix** — All 29 systems with explicit read/write declarations. Parallel safety formally proven (disjoint entity partitions, RoomCap middle-state protection).

9. **SpawningGrace protection** — 1-tick immunity window for newborn drones prevents "born-then-killed" race conditions. Correctly placed before combat systems.

10. **Overload anti-lockout proof** — Formal proof that no coalition of attackers can permanently lock a target's fuel budget to zero. Good defensive design documentation.

11. **Snapshot build determinism** — Single snapshot construction O(entities) before any player execution, with `sort_and_truncate` guarantees for per-player view assembly.

12. **YAML IDL as single machine source** — The `api-registry.md` header correctly states it is auto-generated from YAML and hand edits will be overwritten. This is the right architecture for single-source consistency.

---

## 4. CrossCheck — YAML↔Markdown Consistency Audit

### Verified Consistent

| Section | YAML | api-registry.md | Status |
|---------|------|-----------------|--------|
| CommandAction count | 19 | 19 | ✅ |
| RejectionReason count | 35 | 35 | ✅ |
| MCP Tools count | 46 | 46 | ✅ |
| Host Functions count | 5 | 5 | ✅ |
| TickTrace Envelope fields | 22 | 22 | ✅ |
| Direction4 values | 0-3 | 0-3 | ✅ |
| Game limits (all 14 params) | match | match | ✅ |
| WASM limits | match | match | ✅ |
| Replay params | match | match | ✅ |
| Terminal state enum (7 variants) | match | match | ✅ |
| ResourceOperation (6 ops) | match | match | ✅ |
| Deploy flow (4 steps) | match | match | ✅ |
| ABI error priority (9 levels) | match | match | ✅ |
| SwarmError envelope | match | match | ✅ |
| RFC tools (swarm_list_market_orders) | match | match | ✅ |
| WebSocket security | match | match | ✅ |
| Capability profiles | match | match | ✅ |
| Persistence async upload | match | match | ✅ |

### Drift Detected

| Item | YAML | api-registry.md | Severity |
|------|------|-----------------|----------|
| Worker pool max_pool | 256 | 256 | — (consistent) |
| Worker pool max_pool vs engine.md | 256 | "max_pool 默认 256" | ⚠️ engine.md says 1000 (D4) |
| f64 in output schemas | 7 tools | matches YAML | 🔴 D1 |

The YAML→Markdown generation is **structurally correct** — no field count mismatches, no missing sections, no enum value differences. The drift is between the IDL layer and the design layer (engine.md), not within the IDL itself. This validates the R15-R17 single-source architecture.

---

## 5. Replay Gaps

**Gap 1 — MCP output f64 mismatch**: If replay compares MCP tool output values, f64 will diverge. But it's unclear whether the `read_replay_safe` classification means "the values SHOULD match on replay" or "the tool is safe to call during replay."

**Gap 2 — SIMD architecture recording**: TickTrace records `wasmtime_version` and `module_hash` but not CPU feature flags (AVX, NEON, SSE level). If SIMD is enabled in World mode, different hardware = different execution = replay failure without diagnostic information.

**Gap 3 — custom_action ordering**: `world_action_manifest_hash` proves the manifest existed, but the sort order of custom_actions relative to core actions in the command queue is not specified in any determinism contract.

**Gap 4 — seed rotation epoch boundary**: When `world_seed` rotates at tick 10000, the new seed is `Blake3(old_seed || current_tick)`. The TickTrace records `seed_epoch` but the replay engine needs to know which seed to use for which tick. The contract says "回放时按 epoch 选择对应种子" but doesn't define the epoch transition behavior — does tick 10000 use the old seed or new seed?

---

## 6. Formal State Issues

**Issue 1 — RoomCap middle-state**: The manifest correctly identifies that RoomCap is in an intermediate state between S07 (death_marker: release) and S08 (spawn: consume). The rule "no system between S07 and S08 may read RoomCap" is stated. But S06 (spawn_validator) reads RoomCap in Phase 2a for the `RoomDroneCapReached` check — this read happens BEFORE S07's release, which is correct, but needs explicit verification that S06's RoomCap check uses the pre-release value.

**Issue 2 — DeathMark filtering**: S10 (regeneration) and S24 (decay) both `Without<DeathMark>` filter. S25 (death_cleanup) reads DeathMark. This is correctly ordered. But S11-S13 (combat) also need the `Without<DeathMark>` filter — the R/W matrix shows S11-S13 read HitPoints and write HitPoints, but don't show a DeathMark filter. If a DeathMark entity has hits > 0, combat systems could still target it.

**Issue 3 — PendingSpawn visibility**: S06 writes to `PendingSpawn` buffer. S08 reads it. No other system between S06 and S08 reads PendingSpawn. This is correct. But the S06→S08 gap spans Phase 2a/2b boundary — if any system in the serial spine between them accidentally reads pending spawns, it would see entities that don't exist yet.

---

## Summary Matrix

| ID | Severity | Category | Documents Affected |
|----|----------|----------|--------------------|
| D1 | Critical | f64 boundary leak | game_api.idl.yaml, api-registry.md |
| D2 | Critical | Conflicting formulas | 02-command-validation.md (self-conflict) |
| D3 | High | Stale schedule | 02-command-validation.md vs 06-phase2b-system-manifest.md |
| D4 | High | Cross-doc constant | engine.md vs api-registry.md vs game_api.idl.yaml |
| D5 | Medium | Cross-doc constant | 02-command-validation.md vs api-registry.md |
| D6 | Medium | Missing contract | game_api.idl.yaml, 02-command-validation.md |
| D7 | Medium | SIMD determinism | 04-wasm-sandbox.md vs engine.md |
| D8 | Low | Stale prose | engine.md |
| D9 | Low | Numbering gap | 02-command-validation.md |
