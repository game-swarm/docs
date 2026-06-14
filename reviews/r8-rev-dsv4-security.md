# Swarm Security Review — R8 Final (rev-dsv4-security)

> **Reviewer**: rev-dsv4-security (DeepSeek V4 Pro, Security direction)
> **Date**: 2026-06-14
> **Round**: R8 — Final Review (终审)
> **Scope**: DESIGN.md (full) + tech-choices.md + ROADMAP.md + P0-1 through P0-9
> **Methodology**: Protocol consistency verification, data flow tracing, race condition detection, trust boundary analysis, algorithmic boundary testing, R7 finding tracking

---

## Overall Verdict

**CONDITIONAL_APPROVE**

The Swarm architecture demonstrates mature security thinking at the design level. The deferred command model (`tick() → JSON → Validator → ECS`) is structurally sound. Per-tick WASM fork isolation, server-injected auth context, single-source-of-truth visibility cache, and FDB strict serializability form a robust defense-in-depth baseline. No Critical flaws found.

Since R7, several design documents have been harmonized (McpPlayerExecutor removed, WasmSandboxExecutor unified), but **all 3 High and all 5 Medium findings from R7 remain unaddressed**. Five new High/Medium findings are identified below. The cumulative risk from 5 High + 14 Medium issues warrants resolution before Phase 2 (multi-player) implementation reaches production.

---

## Critical

*None identified.*

No flaws were found that would allow an attacker to bypass the Command Validation Pipeline end-to-end, forge auth context, escape the WASM sandbox, crash the engine deterministically, or corrupt world state irrecoverably. The combined FDB atomic commit + per-tick fork isolation + Blake3 module hashing + server-injected player_id provides a strong foundation.

---

## High

### H-1: Player-name delimiter collision breaks AI prompt boundary (P0-2 §6, P0-3 §6.2–6.3) — UNRESOLVED from R7

**Finding**: P0-2 §6 restricts player names to `[a-zA-Z0-9 _-]` (32 chars). P0-3 §6.3 defines the AI SDK delimiter as `---GAME_DATA---` / `---END_GAME_DATA---`, which is composed entirely of characters in the allowed player-name set. P0-2 §6 itself notes "Prompt injection delimiter must use characters outside this character set" — but this is stated as a design note, not enforced: the current delimiter spec contradicts this requirement.

A player can name their drone `---END_GAME_DATA---`, closing the delimiter early in the AI SDK template. The `untrusted` / `source_player` markers on name fields (P0-3 §6.1) are JSON metadata only — they do not prevent a delimiter string from appearing in the field value.

**Attack scenario**: A hostile player in an AI-competitive world names a drone `---END_GAME_DATA---`. When AI agents receive snapshots, the SDK template wraps game data between the delimiters. An LLM parsing the full prompt may interpret the premature delimiter as the end of game data and treat subsequent game data as trusted system instructions.

**Recommended fix**: Change the delimiter to use characters outside `[a-zA-Z0-9 _-]`, e.g.:

```
‖‖‖GAME_DATA‖‖‖ ... ‖‖‖END_GAME_DATA‖‖‖
```

Alternatively: base64-encode all player-authored string values in snapshots, or enforce delimiter at the JSON structural level (separate sections in the prompt, not string-scan boundaries).

### H-2: Live spectator feed bypasses replay_privacy when spectate_delay=0 (P0-5 §3.5–3.6) — UNRESOLVED from R7

**Finding**: P0-5 §3.5 states spectator WebSocket pushes full map entities without `is_visible_to` filtering when `public_spectate = true`. The delay is controlled by `spectate_delay` (default 0). When `spectate_delay = 0`, a spectator sees full world state in **real time** with zero delay.

In World mode, `replay_privacy` defaults to `"private"`. However, `public_spectate` and `replay_privacy` are independent configuration knobs — P0-5 §3.6 only restricts **stored replays**, not live spectator streams. A World server operator who enables `public_spectate = true` inadvertently exposes all players' positions, resource caches, and build queues in real time, with no respect for replay_privacy settings.

**Recommended fix**: Add a cross-reference constraint: when `public_spectate = true` in World mode, `spectate_delay` must be ≥ some minimum (e.g., 50 ticks), OR `replay_privacy` must be `"world"` or higher. Alternatively, apply `replay_privacy` filtering to live spectator feeds — when `replay_privacy = "private"`, spectators see only terrain and public room metadata.

### H-3: Quick re-deploy + refund credit carryover enables fuel budget inflation (P0-1 §2.4, P0-2 §7.2) — UNRESOLVED from R7

**Finding**: P0-1 §2.4 defines atomic module switching at tick boundaries. P0-2 §7.2 states refund credits from rejected commands in tick N are credited to tick N+1's fuel budget (up to MAX_FUEL × 1.1). An attacker can:

1. Tick N: Deploy WASM v1 that submits 100 contention-targeting commands (harvest from shared sources). ~50% are rejected as `SourceEmpty` → 50% refund.
2. Tick N+1: Re-deploy a **different** WASM v2 that uses the inflated fuel budget (up to +10%) for expensive computation.
3. Repeat every 2 ticks, cycling between v1 (refund farmer) and v2 (computation consumer).

The exploit is gated by `code_update_cooldown` (default 0 — no cooldown) and `code_update_cost` (default 0 — free). P0-3 §5.1 limits MCP deploy to 10/hour, providing a backstop for AI players, but Web UI / CLI deploy have no equivalent rate limit.

**Recommended fix**: (a) Set a hard minimum `code_update_cooldown` of 5 ticks for World mode. (b) Add a "deploy-reset" rule: refund credits expire if the WASM module is replaced — credits are tied to the module that earned them. (c) Enforce the 10/hour deploy limit at the Source Gate level (P0-9), not just at the MCP tool level.

### H-4: RuleMod `actions.modify_entity` has no property whitelist — ownership transfer possible (DESIGN §8.7, P0-7) — NEW

**Finding**: DESIGN §8.7 specifies `actions.modify_entity(entity_id, property, value)` as an available Rhai mod action. There is **no whitelist** of modifiable properties. A RuleMod running with server-owner trust could:

- Modify `drone.owner` → transfer drone ownership between players
- Modify `structure.owner` → steal buildings
- Modify `controller.owner` → capture room controllers
- Modify `resource.amounts` → inflate or zero out resource balances
- Modify `drone.age` → reset lifespan, circumventing death_system

P0-7 §8 states RuleMods "绝不可绕过 Command 校验管线" (must never bypass the Command Validation Pipeline), but `modify_entity` operates through `actions.apply(world)` which is described as going through a mini-validator (DESIGN §8.7: "经校验后写入"), not the full P0-2 pipeline. The mini-validator's property enforcement is unspecified.

**Recommended fix**: Replace `modify_entity` with a bounded set of typed action methods:

```rust
// Instead of:
actions.modify_entity(entity_id, "owner", new_owner_id);  // DANGEROUS

// Use:
actions.deduct_resource(player_id, resource, amount);
actions.award_resource(player_id, resource, amount);
actions.set_entity_flag(entity_id, flag_name, value);  // whitelisted flags only
actions.damage_entity(entity_id, amount, reason);
```

Remove raw property access entirely. If a mod needs to modify entity state beyond resource/economy operations, require it to go through the full command pipeline.

### H-5: `spawn_policy = "Inherit"` lacks room-ownership validation (DESIGN §8.2) — NEW

**Finding**: DESIGN §8.2 defines `spawn_policy` with four values: `RandomRoom`, `ManualSelect`, `FixedSpawn`, and `Inherit`. The `Inherit` policy allows spawning "from existing colony" — but the validation for what constitutes a valid colony room is undefined. A player who has ever visited or briefly controlled a room could potentially spawn there indefinitely, even after losing control.

P0-7 §6's World/Arena defaults table lists `RandomRoom` for World and `FixedSpawn` for Arena — `Inherit` is not in the defaults table at all. This suggests it was added to the enum without corresponding validation specification.

**Attack scenario**: Player A briefly controls Room W1N1 with a cheap Claim drone. Player B captures the room. Player A, through Inherit policy, continues to spawn drones in W1N1 (technically "from existing colony" since they once held it), bypassing B's room control.

**Recommended fix**: Define Inherit precisely: spawn is only allowed in rooms where the player currently owns a Controller **and** has an active Spawn structure. The room must be in the player's current controller list at spawn time, not historically.

---

## Medium

### M-1: path_find adversarial obstacle layouts inflate fuel costs (P0-4 §8) — UNRESOLVED from R7

**Finding**: P0-4 §8 costs `host_path_find` at 10,000 + 50/tile, up to MAX_PATH_LENGTH = 100 → max 15,000 fuel/call. An attacker who builds walls in positions designed to maximize pathfinding exploration can force victims into near-maximal path computations. While the terrain_hash cache (keyed on `(from, to, terrain_hash)`) mitigates repeat queries, an attacker varies target coordinates to generate unique cache keys — up to O(100²) ≈ 10,000 unique reachable targets from a given source.

With 10 calls/tick × 15,000 fuel = 150,000 fuel/tick = 1.5% of the 10M fuel budget. Low-rate but sustained, and the attacker's cost is a cheap Build command.

**Recommended fix**: Cap per-call fuel cost at a lower baseline (e.g., 5,000 + 25/tile). Consider a per-tick global pathfinding budget at the engine level to prevent aggregate CPU drain during the COLLECT phase.

### M-2: Entity ID enumeration oracle via `swarm_inspect_entity` (P0-3 §4.3, P0-5 §3.2) — UNRESOLVED from R7

**Finding**: `swarm_inspect_entity` returns full component data when `is_visible_to` passes. P0-5 §3.2 specifies it returns data only for visible or own entities. If entity IDs are sequential (common in Bevy ECS with `Entity::index()`), an attacker probes IDs to discover entity existence. The error message for "exists but not visible" vs "does not exist" is not specified — this difference creates an oracle.

**Recommended fix**: Return the same error code for both "entity exists outside your visibility" and "entity does not exist" — e.g., `EntityNotAccessible` with no differentiation. Consider using non-sequential entity IDs (hash-based or random).

### M-3: RuleMod `actions.apply()` bypasses full P0-2 validation pipeline (P0-7 §4, §8) — UNRESOLVED from R7

**Finding**: P0-7 §8 states RuleMod "绝不可绕过 Command 校验管线." However, DESIGN §8.7 shows `actions.apply(world)` as "经校验后写入" — going through a mini-validator, not the full P0-2 pipeline (JSON schema → deserialize → pre-validate → apply). P0-7 §5.2 shows `memory_upkeep_system` with `resources.deduct()` and ad-hoc `truncate_to_fit` fallback — inconsistent validation paths per-system.

**Recommended fix**: Spec the `actions.apply()` path explicitly: it must go through a documented mini-validator that checks resource sufficiency before deducting, rejects negative balances, validates overflow on awards, and logs structured rejection reasons to TickTrace. This mini-validator should be documented as an extension of P0-2, not an alternative.

### M-4: JSON 256KB limit does not account for deserialization memory amplification (P0-2 §1.1, P0-4 §6) — UNRESOLVED from R7

**Finding**: P0-2 §1.1 limits tick output JSON to 256KB. A WASM module with 64MB linear memory could craft a 256KB JSON containing 100 commands each with 2KB `detail` strings. When serde_json deserializes this, internal String copies + HashMap reallocations could consume significantly more memory than the JSON byte size — potentially triggering OOM in the validator process (which is inside the engine, not the sandbox).

**Recommended fix**: Add a deserialization memory budget. After JSON parsing, check that resulting Rust data structures do not exceed a memory threshold (e.g., 4MB for the Command array). Also add a per-command string length limit that is explicitly tied to the deserialization budget.

### M-5: `world_seed` lifecycle undefined; PRNG derivation inconsistent (P0-1 §3.1, DESIGN §8.8) — UNRESOLVED from R7

**Finding**: P0-1 §3.1 defines PRNG as `Blake3(tick_number || world_seed)`. DESIGN §8.8 defines it as Blake3 XOF with `update_with_seek(seed, offset)`. These are different derivation methods — the concatenation approach in P0-1 has ambiguous boundaries (where does tick_number end and world_seed begin?). The XOF seek-based approach in DESIGN is more robust but the two specs describe different mechanisms.

Additionally, world_seed lifecycle is undefined: when is it generated? Can it be rotated? What happens to replay determinism if rotated? What if world_seed leaks (admin error, backup exposure, source commit)?

**Recommended fix**: (a) Unify PRNG derivation to the XOF seek-based approach across both specs. (b) Define world_seed lifecycle: generated once at world creation, stored in FDB with admin-only access, never logged. (c) Add seed rotation mechanism for emergency with explicit documentation that rotation breaks replay determinism for pre-rotation ticks. (d) Add CI check that world_seed never appears in logs, TickTrace, or API responses.

### M-6: `memory_spawn_cost` / `memory_upkeep_cost` precision truncation gives free memory (DESIGN §8.2, P0-7 §5) — NEW

**Finding**: P0-7 §5 shows `memory_upkeep_system` computing: `(used_bytes * cost_per_byte) / FIXED_SCALE`. With FIXED_SCALE = 10000 and cost_per_byte = 1, each byte costs 0.0001 units — but u32 division truncates. A player using up to 9,999 bytes of drone memory pays 0 upkeep (9,999 × 1 / 10000 = 0). Similarly for `memory_spawn_cost`. A player can use nearly 10KB of drone memory for free, and the `truncate_to_fit` fallback in P0-7 §5 only triggers on negative balance — which never happens because the cost rounds to 0.

**Recommended fix**: Either (a) use ceiling division: `(used_bytes * cost_per_byte + FIXED_SCALE - 1) / FIXED_SCALE`, or (b) accumulate fractional remainder in a per-player counter that triggers when reaching FIXED_SCALE, or (c) require cost_per_byte values that are ≥ FIXED_SCALE / max_used_bytes to prevent zero-cost ranges.

### M-7: `swarm_simulate` on snapshot copy may leak hidden information (P0-3 §4.4, P0-5 §3.5, P0-9 §2.3) — NEW

**Finding**: P0-3 §4.4 defines `swarm_simulate` for offline simulation. P0-9 §2.3 says Simulate operates on "snapshot copy" with 0.5× MAX_FUEL budget. The key question: **copy of what?** If the simulation snapshot is the full world state (not filtered by `is_visible_to`), the simulation output reveals entity positions, resource levels, and combat outcomes involving entities the player shouldn't see.

P0-5 §3.5 specifies `player_view` affects MCP queries but the simulate tool isn't explicitly covered in the visibility output surface table (§3.2). Even if the snapshot is visibility-filtered, simulating combat against invisible enemies (if the simulation engine has full knowledge) could leak information through combat outcome differences.

**Recommended fix**: Explicitly specify: `swarm_simulate` operates on the **same visibility-filtered snapshot** that `swarm_get_snapshot` returns. The simulation runs with the same visibility constraints. Add to P0-5 §3.2: `swarm_simulate` → uses visibility-filtered snapshot, no full-information access.

### M-8: Controller `downgrade_timer` + `safe_mode` interaction risk (DESIGN §3.1) — NEW

**Finding**: DESIGN §3.1 defines `controller.downgrade_timer` (default 5000 ticks ≈ 4h) and `controller.safe_mode`. The downgrade timer decrements when the controller has no owner. If an attacker times an assault to coincide with `safe_mode` expiry, and the downgrade_timer has been running during safe_mode (spec unclear whether safe_mode pauses the timer), the controller could de-level immediately after safe_mode ends.

The spec does not define:
- Whether `downgrade_timer` pauses during `safe_mode`
- Whether `downgrade_timer` resets when a new owner claims the controller
- Whether `downgrade_timer` pauses when the room has active defenders but no controller owner

**Recommended fix**: Define: (a) `downgrade_timer` pauses during `safe_mode`. (b) `downgrade_timer` resets to full value (5000) when a new owner claims the controller. (c) `downgrade_timer` decrements ONLY when the controller has no owner AND the room has no friendly drone within vision range (i.e., truly abandoned, not just momentarily unowned).

### M-9: `resource_types` duplicate `name` silently overwrites (DESIGN §8.2, P0-7 §2) — NEW

**Finding**: DESIGN §8.2 and P0-7 §2 allow `[[resource_types]]` with arbitrary `name` fields. The `ResourceRegistry` uses `HashMap<String, ResourceDef>` — if two resource types have the same `name`, the last one silently overwrites the first. Resource names are also used as keys in `actions.costs` and `source_types.produces`. A duplicate resource type name could shadow a critical resource, causing incorrect cost calculations, source production, or storage limits.

While world.toml is authored by the server operator (trusted), this is a validation gap that could cause silent misconfiguration with security implications — e.g., defining a second `Energy` with `starting_amount = 0` would overwrite the first, giving new players zero starting energy.

**Recommended fix**: Add to P0-7 §7 (`validate_config`): reject duplicate `resource_types.name` values with a clear error. Also validate that `actions.costs` keys refer to existing resource types and `source_types.produces` keys refer to existing resource types.

---

## Informational

### I-1: WASM SIMD determinism guarantee undocumented (P0-4 §2.2)

`config.wasm_simd(true)` is enabled. While Wasmtime's Cranelift SIMD lowering is platform-independent (same SIMD width across x86_64 and aarch64), P0-4 does not document this guarantee. For replay determinism, this should be explicitly stated.

### I-2: Compile budget rate-limit scope inconsistent (P0-3 §5.1, P0-4 §7, P0-9 §2.2)

P0-3 §5.1 limits deploy to 10/hour (MCP-specific). P0-4 §7 allows 5 concurrent compilations with 30s timeout. P0-9 §2.2 lists Deploy source at 1/tick. These limits are not coordinated — an attacker could deploy via Web UI, CLI, and MCP simultaneously to multiply effective rate.

### I-3: 50K commands/tick at full scale needs early-rejection optimization (P0-2 §6)

At 500 players × 100 commands = 50,000 commands/tick, serial validation within 500ms EXECUTE budget gives 100μs/command. Each command involves multiple ECS queries, spatial checks, and FDB reads. Early-rejection (pre-filtering obviously invalid commands) should be designed into Phase 1, not deferred.

### I-4: IDL `refund_policy` not wired to codegen (P0-8 §2, §3)

P0-8 defines `refund_policy.contention_lost: 0.5` and `refund_policy.self_invalid: 0.0` in the IDL. However, P0-8 §3 codegen targets (Rust Command enum, TS SDK types, MCP schemas) do not list "refund validation" as a generated artifact. The IDL refund_policy should generate the refund logic in the P0-2 pipeline to ensure consistency.

### I-5: `TransferToGlobal` / `TransferFromGlobal` absent from P0-2 validation matrix (P0-8, P0-2)

P0-8 defines `global_storage_commands` with validators and cost fields. P0-2 §3 only covers Move through Recycle — global storage commands are absent. These commands have security implications (transport intercept in PvP per DESIGN §8.4, double-spend during pending transfers) and should be included in the validation matrix.

### I-6: Tutorial namespace isolation could use dual-layer gate (P0-9 §2.4)

P0-9 §2.4 isolates Tutorial via separate FDB namespace (`tutorial_{world_id}`). If a bug causes namespace leakage (shared cache key, misrouted NATS message), tutorial commands could affect a non-tutorial world. A dual-layer gate (checking `world_mode` field on each command at the Source Gate level) would provide defense-in-depth.

### I-7: `drone_lifespan` minimum value not validated (DESIGN §3.1, P0-7 §7)

DEFAULT_DRONE_LIFESPAN = 1500 is the default, but `drone.lifespan` in world.toml has no documented minimum. Setting `drone_lifespan = 0` would cause drones to die in the same tick they spawn (death_system checks `age >= lifespan`, and `age` starts at 0). P0-7 §7 validation doesn't include a minimum lifespan check.

### I-8: `code_propagation_source = "AnyDrone"` listed but not documented (DESIGN §8.2)

DESIGN §8.2's code propagation table lists `code_propagation_source` values including `"AnyDrone"`. The behavior of "AnyDrone" propagation — whether any drone acts as a relay, whether it creates a mesh network, and what happens when two drones with different code versions meet — is not specified anywhere in DESIGN or P0-7.

### I-9: `seed shuffle` could benefit from commit-reveal fairness (P0-1 §3.1)

The seed shuffle `Blake3(tick_number || world_seed)` is deterministic but world_seed is hidden. However, if world_seed leaks (M-5), all future tick orders become predictable. A commit-reveal scheme where each player submits a random nonce that is XORed into the shuffle seed would provide additional unpredictability even if world_seed is compromised.

---

## R7 Finding Status

| R7 ID | Severity | Status | Notes |
|-------|----------|--------|-------|
| H-1 | High | UNRESOLVED | Delimiter collision still present; re-filed as R8 H-1 |
| H-2 | High | UNRESOLVED | Spectator bypass still present; re-filed as R8 H-2 |
| H-3 | High | UNRESOLVED | Refund carryover exploit; re-filed as R8 H-3 |
| M-1 | Medium | UNRESOLVED | Pathfinding cost inflation; re-filed as R8 M-1 |
| M-2 | Medium | UNRESOLVED | Entity ID oracle; re-filed as R8 M-2 |
| M-3 | Medium | UNRESOLVED | RuleMod validation bypass; re-filed as R8 M-3 |
| M-4 | Medium | UNRESOLVED | JSON memory amplification; re-filed as R8 M-4 |
| M-5 | Medium | UNRESOLVED | world_seed lifecycle; re-filed as R8 M-5 |
| I-1 | Info | RESOLVED | McpPlayerExecutor removed; DESIGN + P0-1 now consistent |
| I-2 | Info | UNRESOLVED | SIMD docs still missing; re-filed as R8 I-1 |
| I-3 | Info | UNRESOLVED | Compile budget scope unclear; re-filed as R8 I-2 |
| I-4 | Info | UNRESOLVED | 50K commands early-rejection; re-filed as R8 I-3 |
| I-5 | Info | UNRESOLVED | IDL refund policy unwired; re-filed as R8 I-4 |
| I-6 | Info | UNRESOLVED | Global storage missing from P0-2; re-filed as R8 I-5 |
| I-7 | Info | UNRESOLVED | Tutorial dual-layer gate; re-filed as R8 I-6 |

---

## Strengths / Design Highlights

1. **Deferred Command Model (DESIGN §5, P0-4 §3)**: WASM cannot directly mutate world state — all mutations go through `tick() → JSON → Validator → ECS`. This eliminates the entire class of sandbox-escape-to-game-state attacks. The design contract is explicit and enforced at the host function level (only read-only host functions exposed).

2. **Server-Injected Auth Context (P0-9 §3)**: Player_id is never trusted from the client. The service extracts it from the certificate and overwrites any client-provided value. Combined with Blake3 module hashing at deploy time and verification at execution time, player_id spoofing is impossible.

3. **Single Validation Pipeline (P0-2 §1)**: All 12 command sources go through the same `JSON Schema → Deserialize → Pre-validate → Apply → Record` pipeline. The Source Gate (P0-9 §4) blocks non-gameplay sources from submitting gameplay commands at the earliest possible point — before any command processing occurs.

4. **Per-Tick WASM Fork Isolation (P0-4 §1)**: Each tick spawns a fresh sandbox worker process, executes one player, then kills it. No state persists between ticks. Combined with seccomp BPF + cgroup v2 + no network namespace + read-only rootfs, the sandbox implements genuine defense-in-depth. Cross-tick memory leaks, long-running malicious processes, and infected module persistence are structurally prevented.

5. **Tick Atomicity via FDB (P0-1 §3.4)**: The entire EXECUTE phase is wrapped in a single FDB transaction with strict serializability. If commit fails, the tick is abandoned — world state unchanged, tick_counter not incremented, CPU fuel refunded. No partial world states ever exist. Degraded mode after 3 consecutive abandons provides a safety valve.

6. **Seed Shuffle Fairness (P0-1 §3.1)**: Player execution order is deterministically shuffled each tick using Blake3 XOF, derived from world_seed (hidden from players). Long-term expected fairness is mathematically guaranteed. Players cannot predict their position in the current tick's order.

7. **Unified Visibility Cache (P0-5 §5)**: `is_visible_to(entity, player_id, tick)` is computed once per tick per player, cached, and used by all output surfaces (snapshot, MCP, WebSocket, REST, replay). This eliminates the "snapshot says hidden but WebSocket leaks" class of bugs — a historically common vulnerability in multiplayer games.

8. **Fuel Refund Anti-Abuse (P0-2 §7)**: Refund credits apply to next tick only (no same-tick amplification), are capped at MAX_FUEL × 10%, deduplicate same-source repeated failures, and auto-throttle at >80% refund rate for 3 consecutive ticks. This is a well-considered anti-gaming mechanism.

9. **WASM Module Validation at Upload (P0-4 §2.4)**: Modules are pre-screened for size (≤5MB), required `tick` export, forbidden `_start` function, and allowed imports only. This prevents deploying modules that would fail at execution time, reducing the attack surface during the time-critical COLLECT phase.

10. **Blake3 Monoculture (tech-choices.md §8)**: Using Blake3 for hashing, PRNG (XOF mode), and code signing (keyed hash) reduces the cryptographic dependency surface from three primitives to one. Fewer primitives means fewer CVEs and fewer implementation bugs.

11. **Resource Registry Decoupling (DESIGN §8.4)**: The engine operates on `HashMap<String, u32>` for resources rather than hardcoded `Energy`. This eliminates an entire class of "forgot to validate this resource type exists" bugs and makes the engine genuinely resource-type-agnostic.

12. **Drone Lifespan as Built-in Anti-Snowball (DESIGN §3.1, §8.2)**: The 1500-tick default lifespan (~75 minutes) means no drone army lasts forever. Combined with empire-upkeep progressive taxation, this creates a natural anti-monopoly dynamic that doesn't require administrative intervention.

---

## Summary Table

| ID | Severity | Area | Summary | R7? |
|----|----------|------|---------|-----|
| H-1 | High | P0-2/P0-3 | Player-name delimiter collision with AI prompt boundary | Yes |
| H-2 | High | P0-5 | Live spectator feed bypasses replay_privacy when spectate_delay=0 | Yes |
| H-3 | High | P0-1/P0-2 | Rapid re-deploy + refund credit carryover enables fuel budget inflation | Yes |
| H-4 | High | P0-7/DESIGN | RuleMod `modify_entity` has no property whitelist — ownership transfer possible | New |
| H-5 | High | DESIGN | `spawn_policy = "Inherit"` lacks room-ownership validation | New |
| M-1 | Medium | P0-4 | Adversarial obstacle layouts inflate pathfinding fuel costs | Yes |
| M-2 | Medium | P0-3/P0-5 | Entity ID enumeration oracle leaks existence info | Yes |
| M-3 | Medium | P0-7 | RuleMod `actions.apply()` bypasses full P0-2 validation pipeline | Yes |
| M-4 | Medium | P0-2 | JSON 256KB limit doesn't account for deserialization memory amplification | Yes |
| M-5 | Medium | P0-1/DESIGN | world_seed lifecycle undefined; PRNG derivation inconsistent across specs | Yes |
| M-6 | Medium | DESIGN/P0-7 | memory_spawn_cost/upkeep_cost precision truncation gives free memory | New |
| M-7 | Medium | P0-3/P0-5 | swarm_simulate may leak hidden info through full-knowledge simulation | New |
| M-8 | Medium | DESIGN | Controller downgrade_timer + safe_mode interaction risks undefined | New |
| M-9 | Medium | DESIGN/P0-7 | Duplicate resource_types.name silently overwrites | New |
| I-1 | Info | P0-4 | SIMD determinism guarantee undocumented | Yes |
| I-2 | Info | P0-3/P0-4 | Compile budget rate-limit scope inconsistent across sources | Yes |
| I-3 | Info | P0-2 | 50K commands/tick at full scale needs early-rejection optimization | Yes |
| I-4 | Info | P0-8 | IDL refund_policy not wired to codegen pipeline | Yes |
| I-5 | Info | P0-2/P0-8 | Global storage commands absent from P0-2 validation matrix | Yes |
| I-6 | Info | P0-9 | Tutorial namespace isolation could use dual-layer Source Gate check | Yes |
| I-7 | Info | DESIGN/P0-7 | drone_lifespan minimum value not validated (0 = instant death) | New |
| I-8 | Info | DESIGN | code_propagation_source = "AnyDrone" behavior undocumented | New |
| I-9 | Info | P0-1 | Seed shuffle could benefit from commit-reveal for additional unpredictability | New |
