# R-Design Review: Determinism — DeepSeek V4 Pro

**Reviewer**: rev-dsv4-determinism (DeepSeek V4 Pro)
**Date**: 2026-06-18
**Scope**: Clean-slate review of all 7 design documents
**Direction**: Determinism — deep reasoning chains, algorithm verification, data flow consistency

---

## Verdict: CONDITIONAL_APPROVE

The design demonstrates strong determinism awareness with explicit contracts, correct algorithmic choices (IndexMap, Blake3 XOF, .chain() scheduling, integer-only numerics), and a replay verification mechanism. However, 7 findings were identified — 2 High, 4 Medium, 1 Low — spanning ECS parallel execution order ambiguity, WASM sandbox wire format determinism gap, event-driven RNG dependency on tick scope, and several data flow consistency issues across the FDB/Dragonfly boundary. All are resolvable at design level without architecture changes.

---

## Findings

### D1 [HIGH] regeneration_system / decay_system parallel execution and IndexMap iteration order

**Source**: engine.md §3.2 Phase 2b, gameplay.md §8.8

The design places `regeneration_system` and `decay_system` in Bevy's parallel scheduler, claiming they are "data independent" and therefore safe:

```
regeneration_system ─┐
decay_system ────────┤ 并行（无数据竞争，与主线无依赖）
```

The determinism contract (§8.8) states:
> "Bevy 依赖图保证偏序不变，确定性不依赖并行度"

**The Gap**: The design conflates "no data race" (safety) with "deterministic output" (correctness). Even if two systems operate on disjoint component sets, their outputs can become order-dependent when they both produce **side effects that downstream systems consume via unordered containers**.

Concrete scenario:
1. `regeneration_system` iterates all `Source` entities and increments `ticks_to_regeneration`, producing `Resource` entities at spawn points when regeneration triggers.
2. `decay_system` iterates all `Resource` entities and applies decay.
3. Both produce new/modified `Resource` entities that enter the ECS World.
4. `death_cleanup_system` later iterates entities — in Bevy, the iteration order of newly spawned entities across parallel systems is **not guaranteed** by `.before()/.after()` alone when both systems write to the same archetype.

The IndexMap guarantee only holds within a single system's iteration. Across parallel systems writing to the same archetype table, Bevy's internal archetype ordering depends on allocation order, which can vary with thread scheduling.

**Recommendation**: Either (a) serialize regeneration → decay explicitly via `.chain()`, or (b) document a formal proof that Bevy's archetype insertion order is deterministic under `.before()/.after()` when systems access disjoint component sets but write overlapping entity archetypes. The cost of serialization is negligible (<1% of tick budget) for the determinism guarantee gained.

---

### D2 [HIGH] WASM host function wire format: FlatBuffers vs JSON divergence between COLLECT and replay

**Source**: engine.md §3.4, interface.md §5.1, gameplay.md §8.5

The design specifies two serialization formats:
- **Tick hot path**: FlatBuffers binary canonical encoding (engine.md §3.4)
- **Debug/SDK/compat**: JSON (engine.md §3.4 note)

The determinism contract (§8.8) states:
> "相同初始状态 + 相同玩家指令 → 相同世界状态"

But the contract does not specify which format constitutes the **canonical replay input**. If the hot path uses FlatBuffers but replay verification uses JSON, any discrepancy in number encoding (e.g., floating-point representation in JSON vs integer in FlatBuffers, or field ordering) would cause replay mismatch.

More critically, the interface.md §5 describes "WASM 线性内存" as the snapshot delivery mechanism to `tick(ptr, len)`. If the memory layout differs between the hot path and replay reconstruction, the WASM module could produce different Command[] outputs.

**Recommendation**: Add to §8.8: "The canonical snapshot format for replay is FlatBuffers binary — replay verification must use the identical byte stream, not a JSON reconstruction. JSON is strictly a debug/convenience layer and MUST NOT be used for determinism verification."

---

### D3 [MEDIUM] Player shuffle seed derivation: `hash(tick_number, world_seed)` vs `Blake3(tick_number || world_seed)`

**Source**: engine.md §3.2, gameplay.md §8.8

Two formulations appear in the design:

- engine.md §3.2: `seed = hash(tick_number, world_seed)`
- gameplay.md §8.8: `Blake3(tick_number || world_seed)`

These produce different outputs:
- `hash(a, b)` is underspecified (argument order, delimiter)
- `Blake3(a || b)` is well-defined but requires canonical concatenation

The ambiguity matters because the shuffle seed determines player execution order in Phase 2a, which in turn determines who wins resource conflicts under "先到先得" semantics. If two implementations disagree on the seed derivation, replay verification fails on every tick.

**Recommendation**: Standardize on exactly one formulation — `Blake3(world_seed || tick_number.to_le_bytes())` with explicit endianness — and propagate it to engine.md §3.2.

---

### D4 [MEDIUM] Event-driven RNG: NPC events use `Blake3(world_seed || tick_number || event_type)` without per-entity seeding

**Source**: modes.md §9.0

World events (Swarm Invasion, Resource Boom, Ruin Awakening) trigger via:
```
event_seed = Blake3(world_seed || tick_number || event_type)
trigger = (event_seed[0] < threshold)
```

When an event triggers, it spawns NPC entities (e.g., 30 Swarmlings) with behavior driven by "引擎内置 AI (非 WASM) — 确定性". However, the design does not specify how individual NPC PRNG states are seeded.

If all NPCs share the same event_seed-derived PRNG stream, their behavior is deterministic but their **interleaved random draws** depend on entity iteration order — which IndexMap guarantees within one category but does not guarantee across entity archetypes.

Example: 30 Swarmlings spawned in one tick. If Swarmling #15 draws `rand()` before Swarmling #7 due to iteration order, its patrol path differs from a replay where the iteration order swapped.

**Recommendation**: Each NPC entity must derive its own PRNG seed from a deterministic formula: `Blake3(event_seed || entity_id || spawn_sequence)`. Document this in modes.md §9.0.

---

### D5 [MEDIUM] FDB/Dragonfly read path divergence during COLLECT phase

**Source**: README.md §3, engine.md §3.2

The design states:
- FDB: "每 tick 原子写入" (authoritative)
- Dragonfly: "高频读取, 允许 ≤2 tick 滞后" (cache)

The COLLECT phase builds a world snapshot at tick start. The design says this is "一次性构建完整世界快照" done before WASM execution. But it doesn't specify whether the snapshot is built from FDB (authoritative, consistent) or Dragonfly (cached, may be stale).

If COLLECT reads from Dragonfly (for performance), the snapshot could be up to 2 ticks stale, making replay verification impossible because replay would read from FDB (no Dragonfly in replay path). If COLLECT reads from FDB, the Dragonfly ≤2 tick lag is acceptable for client reads but the design must state the contract explicitly.

**Recommendation**: Add to engine.md §3.2: "COLLECT phase snapshot construction reads exclusively from FDB — never from Dragonfly. Dragonfly is a client-facing read cache only, not a tick execution data source. Replay verification bypasses Dragonfly entirely."

---

### D6 [MEDIUM] Overload feedback visibility and determinism: `is_visible_to` depends on fog-of-war state at execution time

**Source**: gameplay.md §Overload 反馈透明度

The `OverloadPressure` component exposes:
> "被攻击者: 总压力 + 每个可见 source 的 contribution — 仅限 is_visible(target, source) 返回 true 的来源"

The `is_visible_to` check depends on the current fog-of-war state, which in turn depends on drone positions and visibility ranges at execution time. Since Overload is applied during Phase 2a (inline command execution), and visibility may change within the same tick (as Move commands execute), the set of "visible sources" in `OverloadPressure` could differ depending on player execution order.

For example: Player A's drone moves into range → Player B's Overload hits → Player C is visible to the target at that instant. If player order shuffles differently, Player A might not have moved yet, making Player C invisible to the Overload target.

**Recommendation**: Freeze visibility snapshots at tick start for all Phase 2a operations. All `is_visible_to` checks during Phase 2a use the pre-tick visibility state, not the in-flight state. This matches the snapshot construction model and eliminates execution-order dependency from visibility-based effects.

---

### D7 [LOW] `state_checksum` scope ambiguity: mod code vs engine code

**Source**: gameplay.md §8.8

The determinism contract states:
> "每个 tick 产出 state_checksum 写入 TickTrace"

But it does not specify whether `state_checksum` covers:
(a) Engine state only (ECS World + FDB)
(b) Engine state + mod state (Rhai-visible state)
(c) Engine state + mod state + auth state
(d) Full tick output (World + commands + rejections + metrics)

For replay verification, the scope matters: if `state_checksum` covers only (a), a replay that passes (a) could still diverge in mod state (b) without detection.

**Recommendation**: Define `state_checksum` scope explicitly: `Blake3( WorldState || mod_state_snapshot || tick_metrics )`. Mod state snapshot = all `actions.*` calls and their parameters from all Rhai mods in this tick, serialized in mod registration order.

---

## Strengths

1. **Explicit Determinism Contract (§8.8)**: The document explicitly enumerates algorithms, seeds, and ordering guarantees — rare and valuable. Having a centralized contract prevents drift between implementation and design.

2. **IndexMap throughout**: Correctly identifies that `std::HashMap` iteration order is non-deterministic and mandates `IndexMap` for `Resource.amounts`, `Source.produces`, `ResourceRegistry.types`, and other collections. This is precisely the right granularity.

3. **Blake3 single-primitive stack**: Hash, PRNG (XOF), and keyed hash all from one primitive — eliminates whole categories of cross-crypto determinism bugs and reduces audit surface. The XOF `update_with_seek` pattern is elegant for per-player per-tick random streams.

4. **Integer-only numerics**: Mandating `i64 × 精度因子` with f64 ban is correct. Cross-platform floating-point determinism is a known impossibility; avoiding it entirely is the right call.

5. **AST node budget as determinism boundary for Rhai**: Using AST node count (deterministic) rather than wall-clock time (non-deterministic) to bound mod execution is the correct approach. The "事务隔离" rollback mechanism when a mod exceeds budget prevents partial state corruption.

6. **Move-as-action design rationale**: The explicit decision to make Move consume the per-tick action slot eliminates the Move+Attack ordering ambiguity that plagues traditional RTS determinism. This is a philosophically sound simplification.

7. **Two-phase snapshot architecture**: Building the snapshot once at tick start before any player code executes eliminates the entire class of "snapshot-built-during-execution" non-determinism bugs. The O(entities + players×rooms) complexity improvement is also a meaningful algorithmic win.

8. **Seed rotation and replay**: Rotating world_seed every 10,000 ticks with a deterministic derivation formula (`Blake3(old_seed, current_tick)`) means replay only needs the initial seed — not all rotated seeds.

9. **Federation identity determinism**: `player_id = blake3("federated:" + world_id + ":" + original_player_id)` is deterministic, verifiable, and collision-resistant. Cross-world identity mapping is replayable.

---

## Recommendations

### R1: Formalize the Phase 2b parallel scheduling proof

Per D1, either serialize regeneration before decay or produce a formal proof that Bevy's archetype ordering is deterministic under `.before()/.after()` for disjoint-component parallel systems. Given the negligible performance cost (<1%), serialization is the safer default.

### R2: Canonicalize the FlatBuffers schema as the replay authority

Per D2, the FlatBuffers binary format must be declared the canonical serialization for replay verification. JSON is a convenience layer and must never be used for determinism checks.

### R3: Unify player shuffle seed derivation

Per D3, standardize on `Blake3(world_seed || tick_number.to_le_bytes())` with explicit endianness.

### R4: Per-entity PRNG seeding for NPCs

Per D4, derive individual PRNG seeds for each NPC entity from `Blake3(event_seed || entity_id || spawn_sequence)` to prevent iteration-order-dependent behavior.

### R5: Explicit FDB-as-snapshot-source contract

Per D5, document that COLLECT phase reads from FDB exclusively. Dragonfly is client-facing only.

### R6: Freeze visibility at tick start for Phase 2a

Per D6, use pre-tick visibility snapshots for all `is_visible_to` checks during Phase 2a command execution. This eliminates execution-order sensitivity from visibility-dependent effects.

### R7: Document state_checksum coverage

Per D7, define the exact scope of `state_checksum` — World state + mod state + tick metrics minimum.

### R8: Consider a "determinism budget" per tick

The design specifies performance budgets (2500ms COLLECT, etc.) but not a determinism verification budget. Recommend adding: "CI replays N randomly sampled ticks per commit (N = min(100, tick_count / 1000)). Replay verification wall-clock budget: 5× original tick interval. Any mismatch → CI fails."

---

## Algorithmic Complexity Notes

| Path | Complexity | Bottleneck | Mitigation |
|---|---|---|---|
| Snapshot construction | O(entities + players × rooms) | Serialization | FlatBuffers <1ms target |
| WASM execution | O(players × fuel_budget) | Per-player sandbox | Pre-compiled modules, instance pooling |
| Command validation | O(commands × entities) per sequential pass | Phase 2a inline checks | Per-player Command[] caps |
| Pathfinding | O(drones × path_length) worst case | A* in WASM host functions | 10K entry LRU cache per player |
| Combat resolution | O(combat_actions × damage_types) | Resistance stacking | Phase 2b deferred batch |
| Rhai mod execution | O(mods × AST nodes) | AST interpretation | 100K node hard cap |

No single path exceeds O(n²) in the critical dimension (player count), and the Tier 1 hard caps (500 players, 50K entities) provide bounded worst-case guarantees.
