# Swarm Security Review — rev-dsv4-security

> **Reviewer**: rev-dsv4-security (DeepSeek V4 Pro, Security direction)  
> **Date**: 2026-06-14  
> **Scope**: DESIGN.md + P0-1 through P0-9 + ROADMAP.md + tech-choices.md + PLANNER-OUTPUT.md  
> **Methodology**: Protocol consistency, data flow tracing, race condition detection, trust boundary analysis, algorithmic boundary testing

---

## Overall Verdict

**APPROVE_WITH_RESERVATIONS**

The design demonstrates mature security thinking: deferred command model, server-injected auth context, single validation pipeline for all 12 command sources, per-tick WASM fork isolation, FDB atomic commit, and seed-shuffle fairness. The architecture is fundamentally sound. Three High-severity findings and five Medium-severity findings are identified below; none are blocking, but all warrant design-time remediation before implementation reaches the relevant phases.

---

## Critical

*None identified.*

No flaws were found that would allow an attacker to bypass the Command Validation Pipeline, forge auth context, crash the engine deterministically, or corrupt world state irrecoverably. The combination of FDB strict serializability + per-tick fork + server-injected player_id forms a robust defense-in-depth baseline.

---

## High

### H-1: Player_id injection via snapshot name fields breaks delimiter contract (P0-3 §6.2, P0-2 §6)

**Finding**: P0-3 §6.2 defines `_untrusted_game_data` markers and SDK delimiter templates to protect AI agents from prompt injection. The delimiter uses `---GAME_DATA---` / `---END_GAME_DATA---`. However, P0-2 §6 restricts **player names** to `[a-zA-Z0-9 _-]` (32 chars) and does not restrict delimiter-like strings within game data. A player can name their drone `---END_GAME_DATA---` or similar, which would close the delimiter early in the AI SDK template and expose subsequent system prompt content or cause the AI to misinterpret the boundary.

In addition, P0-2 §6 states: "Prompt injection delimiter must use characters outside this character set (e.g. `[[`/`]]` or Unicode)" — but this requirement is stated as a **future design note**, not an enforced constraint in the delimiter specification (P0-3 §6.3), which still uses ASCII `---`. The current delimiter format `---GAME_DATA---` is composed entirely of `[a-zA-Z0-9 _-]` characters, which are in the allowed player-name character set. This creates a collision between what P0-2 §6 warns against and what P0-3 §6.3 actually specifies.

**Attack scenario**: A hostile player deploys a drone named `---END_GAME_DATA---` in a world where AI agents compete. When the AI agent receives its snapshot, the SDK template wraps game data. The drone name appears inside the game data block. An insufficiently robust AI client may interpret `---END_GAME_DATA---` as the delimiter and treat subsequent content (which was intended as game data) as trusted system instructions.

**Recommended fix**: Either (a) change the delimiter to use Unicode characters outside the player-name character set (e.g., `‖‖‖GAME_DATA‖‖‖`), or (b) add an escaping layer that transforms any player-authored string containing the delimiter pattern (e.g., prefix with a disallowed character, or base64-encode all player-authored string values in the snapshot), or (c) in the JSON snapshot, use a `"delimiter_safe": true` boolean flag and ensure the delimiter is structurally enforced by JSON nesting rather than string scanning.

### H-2: Replay privacy downgrade via public_spectate bypass (P0-5 §3.5, §6.3)

**Finding**: P0-5 §3.5 states that spectator WebSocket pushes **full map entities without `is_visible_to` filtering** when `public_spectate = true`. The delay is controlled by `spectate_delay` (default 0). When `spectate_delay = 0`, a spectator sees the full world state in **real time** with zero delay.

In World mode, `replay_privacy` defaults to `"private"` — only the player can see their own replay. However, if `public_spectate = true` is accidentally enabled (it defaults to `false` in World, but defaults to `true` in Arena), a real-time spectator feed effectively **becomes a real-time full-information replay** for any connected spectator. This bypasses `replay_privacy` entirely — because live spectator data is not subject to the replay privacy policy (P0-5 §3.6 only restricts stored replays, not live spectator streams).

A World server operator could enable `public_spectate = true` to allow friendly spectating, inadvertently exposing all players' positions, resource caches, and build queues in real time. There is no explicit guard in the design connecting `public_spectate` to `replay_privacy` for live data.

**Recommended fix**: Add a cross-reference constraint: when `public_spectate = true` in a World-mode world, `spectate_delay` must be ≥ some minimum (e.g., 50 ticks) unless the world configuration declares `world.mode = "arena"` or `world.mode = "spectator_open"`. Alternatively, respect `replay_privacy` for live spectator feeds: when `replay_privacy = "private"`, spectators see only terrain and public room metadata, not full entity positions. The current P0-5 §3.5 table ("Spectator receives full map entities") should be conditional on `replay_privacy` level.

### H-3: Quick re-deploy enables tick-level code switching exploit (P0-1 §2.4, P0-2 §7.2)

**Finding**: P0-1 §2.4 states that code deployment is atomic — tick N uses v1, tick N+1 uses v2. P0-2 §7.2 states that fuel refunds from rejected commands in tick N are credited to tick N+1's fuel budget (up to MAX_FUEL × 1.1). An attacker can exploit this by:

1. Tick N: Deploy a WASM module that submits 100 deliberately-failing commands targeting contested resources (e.g., harvest from a source that other players also target). These commands have a 50% chance of being rejected as `SourceEmpty` (contention refund).
2. Even if all 100 commands are rejected by contention, the attacker gets 50% fuel refund → 50 × (command fuel cost / 2) credited to tick N+1.
3. Tick N+1: Re-deploy a *different* WASM module that uses this inflated fuel budget for expensive computation (pathfinding spam, deep simulation). The refund credit is consumed before the deploy cooldown mechanism can react.

The attack is gated by the `code_update_cooldown` rule (default 0 — no cooldown) and `code_update_cost` (default 0 — free). In the default World configuration, an attacker can re-deploy every tick with zero cost. P0-3 §5.1 limits `deploy` calls to 10/hour, which provides a backstop, but this is an MCP-specific limit — Web UI and CLI deploy may not have the same rate limit.

**Recommended fix**: (a) Set a minimum `code_update_cooldown` default of 5 ticks for World mode, even when the configurable rule is 0 (a hard floor, not just a configurable parameter). (b) Add a "deploy spin-up" rule: a newly deployed WASM module does not receive refund credits from the *previous* module's failed commands — refund credits expire if the module is replaced. (c) Ensure that the 10/hour deploy limit is enforced at the Source Gate level (P0-9), not just at the MCP tool level — Web/CLI deploy should also be rate-limited.

---

## Medium

### M-1: path_find cache poisoning via adversarial obstacle layouts (P0-4 §8)

**Finding**: P0-4 §8 specifies `host_path_find` caching by `(from, to, terrain_hash)`. If terrain is static (walls don't move in the base game), the cache is effectively infinite-lived. An attacker who builds walls (through the Build command) in positions designed to maximize pathfinding computation could force other players' path_find calls to explore near-MAX_PATH_LENGTH (100) paths through complex mazes, each costing 10,000 + 50×100 = 15,000 fuel per call, up to 10 calls/tick = 150,000 fuel/tick = 1.5% of the fuel budget. Over many ticks, this is measurable.

The terrain_hash cache mitigates repeat queries, but an attacker can construct wall layouts where each query hits a *different* `(from, to)` pair (e.g., by varying the target coordinate slightly). With MAX_PATH_LENGTH = 100, the number of unique reachable target positions within path distance 100 from a given source is O(100²) ≈ 10,000 in an open grid, but with carefully placed walls, many of these paths are near-maximal. This is a low-rate resource drain (1.5% fuel/tick) but notable because the attacker's cost is the Build command (cheap), while victims pay ongoing pathfinding costs.

**Recommended fix**: Consider making `host_path_find` cost scale with actual *explored nodes* rather than path length, or cap the per-call cost at a lower baseline (e.g., 5,000 + 25/tile). Also consider a per-tick global pathfinding budget at the engine level (shared across all players) to prevent aggregate pathfinding from consuming engine CPU during the COLLECT phase.

### M-2: swarm_inspect_entity enumeration attack (P0-3 §4.3, P0-5 §3.2)

**Finding**: `swarm_inspect_entity` returns full component data for entities the player owns or can see (`is_visible_to` passes). The spec allows 20 calls/tick. If entity IDs are sequentially assigned (common in ECS with `Entity::index()`), an attacker could probe entity IDs in sequence to discover whether entities exist at specific ID ranges, even if those entities are outside their visibility range. A "NotVisible" error vs "ObjectNotFound" error provides an oracle: if the entity exists but is not visible, the error tells the attacker that *something* is at that ID, even if they can't see it. This leaks the existence and approximate creation order of entities.

P0-5 §3.2 states `inspect_entity` returns data only when `is_visible_to` returns true or is own entity — but the error message for "exists but not visible" vs "does not exist" is not specified and could leak information.

**Recommended fix**: Return the same error code for both "entity exists outside your visibility" and "entity does not exist" — e.g., `EntityNotAccessible` with no differentiation. Also consider using non-sequential (randomized) entity IDs to prevent enumeration.

### M-3: RuleMod Rhai scripts can bypass player-level rate limits (P0-7 §4, §8, P0-9 §2.3)

**Finding**: P0-7 §4 gives Rhai mods access to `actions.deduct_resource(player_id, ...)` and `actions.award_resource(player_id, ...)` — up to 100 actions/tick. These actions enter the world state through `actions.apply(world)` but "经校验后写入" (after validation). However, P0-7 §8 states RuleMod "绝不可绕过 Command 校验管线" (must never bypass Command Validation Pipeline) — yet the actions API (`deduct_resource`, `award_resource`) is described as going through `actions.apply()` rather than the full P0-2 pipeline.

If a mod deducts resources from a player and the player goes negative, what happens? The `memory_upkeep_system` in P0-7 §5.2 has a fallback (`memory.truncate_to_fit`) but this is ad-hoc per-system. The mod could also deduct resources that were committed to pending transfers (P0-8 `global_storage_commands`), creating an inconsistency between the transfer state and the actual resource balance.

**Recommended fix**: Spec the `actions.apply()` path explicitly — it should go through a mini-validator that checks resource sufficiency before deducting, and rejects (rather than allowing negative balances) with structured rejection reasons logged to TickTrace. For awards, validate against overflow. This mini-validator should be documented as an extension of P0-2, not an alternative to it.

### M-4: Tick output JSON 256KB limit does not account for WASM memory amplification (P0-2 §1.1, P0-4 §6)

**Finding**: P0-2 §1.1 limits tick output JSON to 256KB. P0-4 §6 limits WASM linear memory to 64MB. A WASM module could allocate a 64MB buffer, serialize a JSON structure that is just under 256KB at the JSON level, but which contains strings that *when parsed back* expand via internal string interning or hash table resizing to consume significantly more memory in the Rust process. For example, 100 commands each with a 2KB `detail` string (totaling 200KB of strings) could cause the validator's serde_json deserialization to allocate multiple times that due to String copies and HashMap reallocations.

The 256KB limit is at the JSON *byte* level, not the in-memory representation level. A 256KB JSON with 10,000 small nested objects (each near the depth limit of 10) could trigger pathological serde_json behavior.

**Recommended fix**: Add a deserialization memory budget — after parsing JSON, check that the resulting Rust data structures do not exceed a memory threshold (e.g., 4MB for the Command array). This is separate from the WASM linear memory limit and the JSON byte limit. Also add a maximum per-command string length (currently 256 chars general string limit per P0-2 §6, which mitigates this but should be explicitly tied to the deserialization budget).

### M-5: seed shuffle uses world_seed from config but spec does not define world_seed lifecycle (P0-1 §3.1, DESIGN §8.8)

**Finding**: P0-1 §3.1 defines the seed shuffle as `Blake3(tick_number || world_seed)`. DESIGN §8.8 states `world_seed = Blake3(32 random bytes), 32 bytes (256-bit), encoded as hex`. P0-5 §3.6 lists `world_seed` as "Admin-only — always hidden." However, neither spec defines the *lifecycle* of world_seed: when is it generated? Can it be rotated? What happens to replay determinism if world_seed is rotated mid-world? What happens if world_seed leaks (e.g., through an admin error, backup exposure, or source code commit)?

If world_seed leaks, an attacker can:
- Predict player order for all future ticks (breaking the "unpredictable" property)
- Compute PRNG outputs for all future ticks (useful for combat RNG prediction)
- Potentially reconstruct other players' RNG-dependent decisions if those use the same seed

The Blake3 XOF `update_with_seek(seed, offset)` pattern per DESIGN §8.8 is different from P0-1's `Blake3(tick_number || world_seed)` — the XOF seek-based approach is more robust (no concatenation ambiguity), but the two specs describe different PRNG derivation methods. This inconsistency needs resolution.

**Recommended fix**: (a) Unify the PRNG derivation method across P0-1 and DESIGN §8.8 — prefer the XOF seek-based approach. (b) Define world_seed lifecycle: generated once at world creation, stored in FDB with admin-only access, never logged. (c) Add a seed rotation mechanism for emergency situations (world_seed compromise) with explicit documentation that rotation breaks replay determinism for pre-rotation ticks. (d) Add CI check that world_seed is not present in any log output, TickTrace, or API response.

---

## Informational

### I-1: PLANNER-OUTPUT.md contains deprecated McpPlayerExecutor design (known, documented)

PLANNER-OUTPUT.md still references `McpPlayerExecutor` and direct gameplay MCP tools (Phase 2.2: "11 tools mirroring Command enum"). The document header acknowledges this is pre-correction. No action needed — P0-3 and DESIGN.md have corrected this — but PLANNER-OUTPUT.md should be archived or have a prominent deprecation notice at the top of each relevant section, not just the header.

### I-2: WASM SIMD enabled without explicit side-channel analysis (P0-4 §2.2)

`config.wasm_simd(true)` is enabled for performance. While Wasmtime's SIMD implementation is deterministic (same SIMD width across platforms because it uses Cranelift's platform-independent SIMD lowering, not native SIMD), the spec does not document this guarantee. For replay determinism, it's important that SIMD execution is identical across x86_64 and aarch64. Recommend adding a note confirming Cranelift's SIMD lowering is platform-independent.

### I-3: compile timeout (30s) is per-module, but attacker could deploy many modules (P0-4 §7)

The compilation budget limits concurrent compilations to 5 with 30s timeout each. If an attacker deploys 5 modules, each timing out at 30s, the compile pipeline is blocked for 30s. P0-3 §5.1 limits deploy to 10/hour which mitigates this, but the 10/hour is MCP-specific. Need to confirm this limit applies to all deploy sources (P0-9: WASM deploy via Web UI, CLI, and MCP_Deploy should share the same rate limiter).

### I-4: MAX_COMMANDS_PER_PLAYER of 100 × N players creates quadratic validation load (P0-2 §6)

At 500 players × 100 commands = 50,000 commands per tick. The P0-2 validation pipeline processes these serially within the EXECUTE phase (500ms budget). Each command involves multiple ECS queries (entity existence, component reads, spatial queries). At 50K commands, that's 100μs per command — tight but feasible. The design should consider early rejection (pre-filtering) for obviously invalid commands before entering the full pipeline. P0-1 §2.2's timeout mechanism (empty commands for slow players) provides a backstop for the COLLECT phase but not for validation overhead.

### I-5: P0-8 IDL `refund_policy` is defined at IDL level but not yet wired to codegen

The IDL includes `refund_policy.contention_lost: 0.5` and `refund_policy.self_invalid: 0.0`. This is elegant — refund policy lives in the single source of truth. However, the codegen targets (Rust Command enum, TS SDK, MCP schema) in P0-8 §3 do not list "refund validation" as a generated artifact. The IDL refund_policy should generate the refund logic in the P0-2 pipeline to ensure consistency.

### I-6: `TransferToGlobal` / `TransferFromGlobal` not in P0-2 validation matrix (P0-8, P0-2)

P0-8 defines `global_storage_commands` (TransferToGlobal, TransferFromGlobal) with validators. P0-2's command validation matrix (§3) only covers Move through Recycle — global storage commands are absent. These have significant security implications (transport intercept in PvP per DESIGN §8.4) and should be included in the validation matrix.

### I-7: `Tutorial` source can submit gameplay commands (P0-9 §2.4)

P0-9 §2.4 restricts Tutorial commands to `world.mode = "tutorial"` only, and uses an isolated namespace. Tutorial commands bypass the normal WASM sandbox (they come from the tutorial UI, not from WASM). While the isolation is strong (separate FDB namespace), if a bug allows namespace leakage (e.g., a shared cache key), tutorial commands could affect a non-tutorial world. Recommend adding a second layer: Tutorial-source commands carry an additional `world_mode` field that the Source Gate checks against the target world's actual mode, rejecting at the gate level (not just at namespace isolation level).

---

## Strengths / Design Highlights

1. **Deferred Command Model (DESIGN §5, P0-4 §3)**: WASM cannot directly mutate world state — all mutations go through `tick() → JSON → Validator → ECS`. This eliminates an entire class of sandbox-escape-to-game-state attacks. The design contract is explicit: "所有 mutating 操作通过 `tick() → JSON` 延迟模型提交。"

2. **Server-Injected Auth Context (P0-9 §3)**: Player_id is never trusted from the client. The service extracts it from the certificate and overwrites any client-provided value. This prevents player_id spoofing even if an attacker crafts their own RawCommand JSON. Combined with Blake3 module hashing, the engine can verify at tick-execution time that the executing module matches the deployed module.

3. **Single Validation Pipeline (P0-2 §1)**: All 12 command sources go through the same `JSON Schema → Deserialize → Pre-validate → Apply → Record` pipeline. No bypasses. The Source Gate (P0-9 §4) blocks non-gameplay sources from submitting gameplay commands at the earliest possible point.

4. **Per-Tick WASM Fork Isolation (P0-4 §1)**: Each tick spawns a fresh sandbox worker process, executes one player, then kills it. No state persists between ticks. This prevents: cross-tick memory leaks, long-running malicious processes, and infected modules from persisting. Combined with seccomp BPF + cgroup v2 + no network namespace + read-only rootfs, the sandbox is defense-in-depth.

5. **Tick Atomicity via FDB (P0-1 §3.4)**: The entire EXECUTE phase is wrapped in a single FDB transaction. If commit fails, the tick is abandoned — world state unchanged, tick_counter not incremented, CPU fuel refunded. No partial world states ever exist. Degraded mode after 3 consecutive abandons provides a safety valve.

6. **Seed Shuffle Fairness (P0-1 §3.1)**: Player execution order is deterministically shuffled each tick using Blake3 XOF. This prevents any player from always being first or last, and the seed is derived from world_seed (which is hidden from players), making the order unpredictable. Long-term expected fairness is mathematically guaranteed.

7. **Visibility Cache Shared Across Surfaces (P0-5 §5)**: The `is_visible_to(entity, player_id, tick)` function is computed once per tick per player, cached, and then used by all output surfaces (snapshot, MCP, WebSocket, REST, replay). This eliminates the "snapshot says hidden but WebSocket leaks" class of bugs — a common vulnerability in multiplayer games with multiple output channels.

8. **Fuel Refund Anti-Abuse (P0-2 §7)**: The refund system is carefully designed: refund credits apply to the *next* tick only (no same-tick amplification), are capped at MAX_FUEL × 10%, deduplicate same-source repeated failures, and auto-throttle at >80% refund rate for 3 consecutive ticks. This is a well-considered anti-gaming mechanism.

9. **WASM Module Validation at Upload (P0-4 §2.4)**: Modules are validated for size (≤5MB), required `tick` export, forbidden `_start` function, and allowed imports before acceptance. This pre-screening prevents deploying modules that would fail at execution time, reducing the attack surface during the time-critical COLLECT phase.

10. **Blake3 Monoculture for Audit Surface Reduction (tech-choices.md §8)**: Using Blake3 for hashing, PRNG (XOF mode), and code signing (keyed hash / MAC) reduces the cryptographic dependency surface from three primitives to one. This is a pragmatic security choice — fewer primitives means fewer CVEs to track and fewer implementation bugs to worry about.

---

## Summary Table

| ID | Severity | Area | Summary |
|----|----------|------|---------|
| H-1 | High | P0-2/P0-3 | Player-name delimiter collision with AI prompt boundary |
| H-2 | High | P0-5 | Live spectator feed bypasses replay_privacy when spectate_delay=0 |
| H-3 | High | P0-1/P0-2 | Rapid re-deploy + refund credit carryover enables budget inflation |
| M-1 | Medium | P0-4 | Adversarial obstacle layouts inflate pathfinding fuel costs |
| M-2 | Medium | P0-3/P0-5 | Entity ID enumeration oracle leaks existence info |
| M-3 | Medium | P0-7 | RuleMod actions bypass full P0-2 validation pipeline |
| M-4 | Medium | P0-2 | JSON 256KB limit doesn't account for deserialization memory amplification |
| M-5 | Medium | P0-1/DESIGN | world_seed lifecycle undefined; PRNG derivation inconsistent across specs |
| I-1 | Info | PLANNER-OUTPUT | Deprecated McpPlayerExecutor references remain |
| I-2 | Info | P0-4 | SIMD determinism guarantee undocumented |
| I-3 | Info | P0-4 | Compile budget rate-limit scope unclear |
| I-4 | Info | P0-2 | 50K commands/tick at full scale needs early-rejection optimization |
| I-5 | Info | P0-8 | Refund policy in IDL not wired to codegen |
| I-6 | Info | P0-2/P0-8 | Global storage commands absent from P0-2 validation matrix |
| I-7 | Info | P0-9 | Tutorial namespace isolation could use dual-layer gate |
