# Security Audit Report — Swarm Design Review

> **Reviewer**: DeepSeek V4 Pro (Security Auditor)
> **Date**: 2026-06-15
> **Scope**: DESIGN.md, tech-choices.md, ROADMAP.md, P0-1 ~ P0-9 specs
> **Methodology**: Protocol Consistency, Data Flow Tracing, Race Condition Analysis, Trust Assumption Audit

---

## Verdict: CONDITIONAL_APPROVE

4 Critical, 5 High, 6 Medium issues identified. All are design-level — the architecture is fundamentally sound with strong defenses, but several attack surfaces need pre-implementation hardening. The issues cluster around: concurrent state inconsistency between COLLECT snapshot and EXECUTE validation, a visibility bypass via Overload's unconstrained range, and a fuel refund timing attack. No issues are architecturally fatal.

---

## Critical Issues

### [CRITICAL-1] Tick Boundary Snapshot Staleness — TOCTOU Between COLLECT and EXECUTE

**Severity**: Critical
**Category**: Protocol Consistency, Race Condition
**Affected**: P0-1 §3.3, P0-2 §3.7

**Finding**: The Inline execution model (§3.3, §3.4 of P0-1) validates each command against the *current* Bevy World state, not the snapshot that WASM received. However, the WASM `tick()` function only sees the COLLECT-phase snapshot. This creates a fundamental TOCTOU gap:

- COLLECT: WASM receives snapshot at tick N, decides "move drone to (5,3) and attack enemy at (5,4)"
- EXECUTE Phase 2a: By the time `Move` completes, another player's command (executed earlier in the shuffle) has already moved the enemy to (5,10). The engine correctly rejects `OutOfRange` for the attack.
- **BUT**: the player's CPU fuel was already consumed during COLLECT. They paid fuel for a doomed plan.

**Exploitation scenario**: A malicious player can craft WASM that submits deliberately large command batches knowing some will fail, hoping enough succeed. The engine rejects invalid commands, which is correct, but there's no refund for "commands that were valid at snapshot-time but invalid at execute-time." This is documented in the refund policy (P0-8: `contention_lost: 0.5`, `self_invalid: 0.0`) but the question is whether a player can *cause* others' valid-at-snapshot commands to become invalid at execute-time — which is trivially possible via resource competition.

**Recommendation**: 
1. Clarify in P0-1 that `RejectionReason` includes a `SnapshotStale` variant for commands valid at snapshot-time but invalid at execute-time, distinct from `OutOfRange`/`TileOccupied` caused by player's own stale knowledge.
2. Consider partial fuel refund (50% per `contention_lost` policy) for these cases — this is already in the IDL but needs explicit wiring to the TOCTOU case.
3. Document the adversarial implications: player order affects success rates, and this is by design (seeded shuffle + "hardcore logistics" mode).

### [CRITICAL-2] Overload Attack Has No Range Limit — Cross-World Side Channel

**Severity**: Critical
**Category**: Trust Assumption, Data Flow
**Affected**: P0-2 §3.14, DESIGN §8.2

**Finding**: The Overload special attack states: "No range limit — Overload 是逻辑攻击" (P0-2 §3.14, line 377). This means any player with a RangedAttack drone can reduce *any other player's* fuel budget globally, regardless of room, visibility, or distance. This creates multiple problems:

1. **Information leak**: If Overload succeeds, the attacker learns the target player ID exists and is active. If it fails (`TargetFuelTooLow`), the attacker learns the target's fuel budget state.
2. **Cross-world DoS**: A player with 10 RangedAttack drones can coordinate to reduce one target's fuel budget by 5M/tick (10 × 500k), potentially pushing them below `MAX_FUEL × 0.2` in a single tick.
3. **Visibility bypass**: Unlike every other game mechanic, Overload ignores fog-of-war. P0-5's `is_visible_to()` function is irrelevant — there's no position check.

**Exploitation scenario**: In a World mode with 500 players, a bot network of 50 drones per attacker could systematically cripple every opponent's fuel budget in ~20 ticks, making the game unplayable for anyone not running Overload-counter strategies.

**Recommendation**:
1. Add a range or visibility constraint to Overload — minimum: target player must be visible (any entity owned by target is in attacker's vision). Better: target must be in attacker's Controller room or within `MAX_QUERY_RANGE` of a drone.
2. Add global cooldown (not just per-drone) — e.g., a target player can't be Overloaded more than once per 50 ticks regardless of source.
3. Make Overload fail silently (no error code returned to attacker) to prevent information leakage.

### [CRITICAL-3] Fuel Refund Timing Attack — Double-Claim on Abandoned Tick

**Severity**: Critical
**Category**: Race Condition, Protocol Consistency
**Affected**: P0-1 §6.1, P0-1 §3.5

**Finding**: P0-1 §6.1 states "FDB commit fail → tick 放弃 → CPU fuel 退还玩家." The abandonment-and-refund semantics create a potential double-claim:

The tick lifecycle:
1. COLLECT: WASM executes, consumes fuel
2. EXECUTE begins, commands applied
3. FDB commit **fails** (conflict/network)
4. Fuel is refunded to players
5. World state is rolled back (Bevy snapshot restore)
6. Tick retries with same tick_number

**Problem**: If a player's WASM module detects a tick abandonment (via observing that `tick_counter` didn't advance), they could exploit the refund:
- Tick N: WASM executes expensive pathfinding (consuming fuel) → FDB fails → refund
- Tick N retry: WASM executes expensive pathfinding again → FDB succeeds → fuel charged
- Net: Player got 2× fuel budget worth of computation for 1× fuel cost

This is technically bounded (max 3 retries) but the 3× multiplier on fuel budget during degraded mode is a meaningful advantage.

**Recommendation**:
1. Document that fuel is consumed on COLLECT, and the refund on FDB failure is a *best-effort* safety net, not a guarantee. Players should not design strategies around refund timing.
2. Track `fuel_consumed_this_tick_attempt` per player and cap total consumption across retries at 1× MAX_FUEL.
3. Add `TickAttempt` counter to metrics to detect abuse patterns.

### [CRITICAL-4] Bevy World FDB Rollback Inconsistency — Memory vs. Persistence Divergence

**Severity**: Critical
**Category**: Data Flow, Protocol Consistency
**Affected**: P0-1 §3.5, §6.1

**Finding**: P0-1 §3.5 states the EXECUTE phase wraps in a FoundationDB transaction with explicit rollback: "EXECUTE 开始时对 Bevy World 做内存快照——FDB rollback 不自动恢复 Bevy 状态，需显式 `world.restore(snapshot)`." This architecture correctly identifies the problem but the spec is underspecified:

1. **What exactly is snapshotted?** The entire Bevy World? All ECS entities and components? What about resources like `TickCounter`, `PlayerOrder`, RNG state?
2. **When is the snapshot taken?** Before Phase 2a or after Phase 2a command loop but before FDB commit?
3. **What happens to in-flight WASM sandbox workers?** The COLLECT phase already completed. If FDB rollback occurs, do we re-collect from players or reuse the same commands?

**Exploitation**: If RNG state is not properly restored on rollback, a player could observe RNG outputs across retry attempts and infer the world_seed or next shuffle position — undermining deterministic fairness.

**Recommendation**:
1. Define the Bevy World snapshot granularity explicitly: all ECS entities + all resources including TickCounter, RNG state, PlayerOrder, ResourceRegistry.
2. Specify that COLLECT results are cached and reused across retries (same commands, same fuel charges — no re-execution of WASM).
3. Add integration test: simulate FDB failure → verify world.restore() produces identical state to pre-execute snapshot → re-execute → verify deterministic output.

---

## High Issues

### [HIGH-1] "Trust Downstream Will Validate" — Command Validation Pipeline Bypass Risk

**Severity**: High
**Category**: Trust Assumption
**Affected**: P0-2 §1, P0-9 §4

**Finding**: P0-2 §1 states "单一管线：所有入口走同一 校验 → 应用 路径。无绕过。" This is a strong claim. However, examining the Source Gate model (P0-9 §4):

```
RawCommand → Source Gate → Auth Verify → Command Validation Pipeline
```

The `WASM` source passes through. But what about `Admin` source? P0-9 §2.3 shows Admin has full `✅` across all capabilities including "允许写入世界." If Admin commands skip validation (plausible for administrative actions like fixing stuck entities), this creates a dual path.

**Potential bypass**: If Admin commands take a different code path (`admin_apply()` vs `validate_and_apply()`), any bug in the admin path becomes a validation bypass for the main pipeline.

**Recommendation**:
1. Admin commands MUST go through the same `validate_and_apply()` function but with relaxed `RejectionReason` thresholds, not a separate code path.
2. Add audit rule: any command that modifies world state without entering `validate_and_apply()` triggers a compile error (enforced by trait design).

### [HIGH-2] Pathfinding Algorithm Unbounded — Malicious Map DoS

**Severity**: High
**Category**: Race Condition, Data Flow
**Affected**: P0-2 §4.3, P0-4 §3.2

**Finding**: P0-2 §4.3 limits PathFind to `MAX_PATH_LENGTH = 100` and 10 calls/tick. P0-4 §8 charges `10,000 + 50/tile` fuel, capped at 8 KB response. However:

1. **No map complexity limit**: A world admin could create a map with intricate maze-like terrain where A* explores 10,000+ nodes before hitting the 100-tile path limit. The fuel cost `50/tile` only counts path tiles, not explored nodes.
2. **Caching key includes `terrain_hash` but not explored node count**: P0-4 §8 caches by `(from, to, terrain_hash, player_visibility_fingerprint)`. A worst-case map where A* explores 50,000 nodes for every 100-tile unreachable destination means 10 path_find calls = 500,000 explored nodes, potentially exceeding the 2500ms COLLECT timeout for a single player.

**Recommendation**:
1. Add `MAX_PATHFIND_NODES_EXPLORED` limit (suggest 10,000) as a hard cutoff in the A* algorithm, independent of path length.
2. Charge fuel per explored node, not per path tile. `host_path_find` cost should be `10,000 + 50/explored_node`.
3. Add map validation: reject world.toml maps where any room has >5% unreachable tiles (detected at world creation time).

### [HIGH-3] Rhai Mod Trust Model — "Server Owner Trusted" Is Insufficient

**Severity**: High
**Category**: Trust Assumption
**Affected**: P0-7 §5.1, DESIGN §8.7

**Finding**: DESIGN §8.7 defines the three-layer trust model: "WASM 不可信 → Rhai 服主信任 → Rust 核心不可变." However, the `actions.*` API available to Rhai mods includes `damage_entity`, `deduct_resource`, `award_resource`, and `set_entity_flag` (P0-7 §5.1 `Rhai API` section). P0-7 §5.1 also states:

```
"Rhai 脚本不能绕过 Command Validation Pipeline"
"Rhai 脚本不能直接写入 ECS 组件——只能通过 actions.* API"
```

**Problem**: The `actions.*` API is a *second validation pipeline* that runs outside the Command Validation Pipeline. While P0-7's RhaiActionBuffer + transaction model is well-defined, the `actions.apply(world)` call (line 1766) has no explicit integration with P0-2's validation framework. The `actions` API has its own "mini-validator" but there's no spec cross-reference documenting the relationship.

**Specifically dangerous**: `actions.set_entity_flag(entity_id, flag, value)` with a "flag whitelist." The spec says "设置白名单标记" but doesn't define the whitelist. A Rhai mod could theoretically set `entity.set_flag("invulnerable", true)` if "invulnerable" isn't in the whitelist — but what ensures the whitelist is enforced?

**Recommendation**:
1. Define the `EntityFlag` whitelist explicitly (immutable, hardcoded in Rust): `[slow, empowered, immune_Thermal, immune_Kinetic, ...]` with `immune_*` flags requiring explicit world.toml `[[damage_types]]` match.
2. Document the integration point between `RhaiActionBuffer.apply()` and the Command Validation Pipeline — specifically, at which phase in the tick lifecycle `actions` are applied and whether they can conflict with in-flight WASM commands.
3. Add a `RhaiActionValidator` trait that mirrors `CommandValidator`, with the same rejection recording to TickTrace.

### [HIGH-4] Spectator Delay Side Channel — Timing Attacks via Public Spectate

**Severity**: High
**Category**: Data Flow, Trust Assumption
**Affected**: P0-5 §3.5, DESIGN §8.2

**Finding**: P0-5 §3.5 states "World 模式下若 `public_spectate = true`，`spectate_delay` 必须 ≥ 50 tick." However, the spec also defines `spectate_delay` default as 0 (real-time). The enforcement ("必须 ≥ 50 tick") is a constraint in the spec document, not a compile-time or runtime enforcement in the code generator.

**Information leak**: If a World admin sets `public_spectate = true, spectate_delay = 0` (plausible for a "watch party" event), spectators receive real-time entity positions. A spectator could relay this information to an active player via out-of-band channels (Discord, voice chat), giving that player full-map vision.

**Recommendation**:
1. Make the constraint runtime-enforced: engine startup MUST reject `public_spectate = true, spectate_delay < 50` in World mode with a clear error.
2. Add a `public_spectate_delay_minimum` constant in Rust (not configurable by world.toml).
3. For Arena mode, add a similar constraint: `spectate_delay ≥ 100` when `public_spectate = true` unless the match has ended.

### [HIGH-5] Sandbox Worker Fork Safety — File Descriptor Inheritance

**Severity**: High
**Category**: Race Condition, Trust Assumption
**Affected**: P0-4 §4.3

**Finding**: P0-4 §4.3 states the sandbox uses Unix domain socket for engine communication: "fd 在 seccomp 锁定前传入." The per-tick fork lifecycle means each tick creates a new process. If the file descriptor is inherited by the child process before seccomp is applied (the spec says fd is passed "before seccomp lock"), there's a window where the child process could:

1. `dup2()` the inherited fd to a well-known number before seccomp activates
2. Use the dup'd fd to communicate with the engine outside the intended protocol

**Timing**: The seccomp filter is applied via `prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, ...)` which is per-thread. If `clone()` with `CLONE_VM | CLONE_VFORK` is used (as listed in the seccomp allowlist), the parent is suspended until the child calls `execve()` or `_exit()`. However, the child never calls `execve()` (it runs Wasmtime in-process), so the race window is non-trivial.

**Recommendation**:
1. Use `close_range(CLOSE_RANGE_UNSHARE, ...)` or `unshare(CLONE_FILES)` immediately after fork, before any Wasmtime operations.
2. Add a pre-exec hook that closes all fds except the Unix socket before Wasmtime module instantiation.
3. Add integration test: fork → verify only expected fds are open → execute malicious WASM that attempts fd enumeration → verify sandbox kills process.

---

## Medium Issues

### [MEDIUM-1] CommandIntent Validation — Sequence Injection via WASM

**Severity**: Medium
**Category**: Data Flow
**Affected**: P0-2 §2.1

**Finding**: P0-2 §2.1 defines `CommandIntent` with only `sequence` + `action`. The spec correctly rejects `player_id`/`source`/`tick` from WASM. However, `sequence` is a `u32` with no upper bound other than the array limit (100 commands). A player could submit 100 commands with sequences `[u32::MAX-50, ..., u32::MAX]`. If the engine sorts by sequence, this doesn't cause overflow issues in Rust (no wrap-around on comparison), but it could cause visualization issues in debug tools or log correlation.

**More concerning**: The spec says "sequence 每 tick 单调递增" but doesn't clarify: is it per-player per-tick, or global? If per-player per-tick, the engine should normalize sequences to 0..N internally. If the spec allows any u32 values, a player could encode information in sequence gaps (e.g., sequence=100 → sequence=200 → sequence=300 could signal "slow advance" to an out-of-band observer analyzing TickTrace).

**Recommendation**:
1. Normalize sequences to 0..N on receipt, ignoring WASM-provided values except for ordering.
2. Document that sequence gaps are not preserved.

### [MEDIUM-2] WASM Module Caching — Certificate Validation Timing

**Severity**: Medium
**Category**: Race Condition, Trust Assumption
**Affected**: P0-4 §7

**Finding**: P0-4 §7 states: "模块缓存: 按 (module_hash, wasmtime_version) 缓存. 每次 tick 执行前校验 player 的证书未过期未吊销——过期/吊销立即终止 WASM 执行（该 tick 0 指令）." This is good defense-in-depth. However:

**Timing race**: The cache check (`cached module exists for this hash`) and certificate validation (`is cert expired/revoked?`) are sequential operations. If a certificate is revoked between the cache hit and the tick execution, the cached module is used with a revoked cert. The spec handles this by validating at execution time, which is correct, but:

1. What about a player who deployed with a valid cert and is mid-tick when revocation occurs? The spec says "0 指令" for that tick — this means the player's drone control is interrupted and they receive no explanation (no rejection reason is specified for cert-revoked-during-execution).
2. If the cache is shared across players with the same module hash (e.g., starter bot), revoking one player's cert should not purge the module from cache for other players. The spec should clarify cache key is `(module_hash, wasmtime_version, player_id)` or maintain a separate cert validity check independent of cache.

**Recommendation**:
1. Clarify cache key: `(module_hash, wasmtime_version)` is sufficient; certificate check is per-execution, not per-cache-entry.
2. Add `RejectionReason::CertificateExpired` and `CertificateRevoked` to P0-2 §5 for the "0 指令" case.

### [MEDIUM-3] Dragonfly Cache Staleness — Split-Brain During Reconnection

**Severity**: Medium
**Category**: Data Flow, Protocol Consistency
**Affected**: P0-1 §4.2, §6.1

**Finding**: P0-1 §6.1 documents "Dragonfly cache stale" as a known failure mode with "无影响——FDB 为权威源" treatment. However, there's a specific scenario:

1. Dragonfly is updated with tick N delta
2. Gateway-1 receives the NATS message, updates its local state
3. Gateway-2 misses the NATS message (network partition)
4. Gateway-2 serves a player request, reads from Dragonfly
5. Dragonfly returns tick N data (correct so far)
6. Gateway-1 crashes, player reconnects to Gateway-2
7. Gateway-2 has tick N data but player last saw tick N+5 from Gateway-1

**Problem**: The player's WebSocket client detects a `last_tick` gap and fetches, but the fetch goes through Gateway-2 which may have a routing path to a stale Dragonfly replica. The spec says "Dragonfly cache stale → FDB 直读" but this only triggers if the cache version is detectably behind, not if it's just a different gateway's state.

**Recommendation**:
1. Add a `tick_counter` to WebSocket connection state, and compare on reconnect.
2. Gateway should read from FDB directly when serving a gap-fill request (tick range fetch), not from Dragonfly cache.
3. Document the expected behavior explicitly in P0-1 §4.2.

### [MEDIUM-4] Custom Actions Handler Injection — No Namespacing

**Severity**: Medium
**Category**: Trust Assumption
**Affected**: DESIGN §8.2 `[[custom_actions]]`, P0-8 §4.2

**Finding**: The `[[custom_actions]]` system uses a `SpecialEffectRegistry` with string-to-handler mapping. Custom actions reference `special_effect = "name"` which resolves to a handler. If two world.toml configurations define different custom actions with the same `special_effect` name but different expected behaviors, the registry has a single global namespace.

**Collision scenario**: Mod A defines `[[special_effects]] name = "poison" → handler = "debilitate"`. Mod B defines `[[special_effects]] name = "poison" → handler = "leech"`. Both mods installed → last-registered wins, Mod A's custom actions now silently use the wrong handler.

**Recommendation**:
1. Namespace special_effect names with the mod name: `mod_name/effect_name`.
2. Detect duplicate registrations at startup and reject with error.
3. Add a manifest validation: `swarm mod validate` that checks for handler name collisions across all installed mods.

### [MEDIUM-5] Fuel Budget Floor Bypass via Overload + Re-Deploy

**Severity**: Medium
**Category**: Race Condition, Protocol Consistency
**Affected**: P0-2 §3.14, DESIGN §8.2

**Finding**: The Overload attack has a floor of `MAX_FUEL × 0.2` (P0-2 §3.14). However, if a player's fuel budget is reduced to 20%, they can simply deploy new WASM code to "refresh" their state. The fuel budget is per-player, not per-deployment. But:

1. Does deploying new code reset the fuel budget? The spec doesn't say.
2. If fuel budget is per-tick and resets each tick regardless, the Overload floor only matters within a single tick. Across ticks, a player could be Overloaded repeatedly to remain at 20%.

**Recommendation**:
1. Clarify: fuel budget resets to `MAX_FUEL` at the start of each tick. Overload's effect is per-tick only (not cumulative across ticks).
2. If Overload is intended to have cumulative effect, add a recovery rate (e.g., +100k fuel/tick when not Overloaded).

### [MEDIUM-6] Prompt Injection Delimiter Choice — Not Machine-Enforceable

**Severity**: Medium
**Category**: Data Flow, Trust Assumption
**Affected**: P0-2 §6, P0-3 §6.3

**Finding**: P0-2 §6 specifies: "Prompt injection delimiter 必须使用此字符集之外的字符（如 `[[`/`]]` 或 Unicode）." P0-3 §6.3 defines delimiter as `‖‖‖GAME_DATA‖‖‖`. This is a good approach — using Unicode delimiters that can't appear in player names (which are restricted to `[a-zA-Z0-9 _-]`). However:

1. **AI model behavior is undefined**: The spec relies on the AI model honoring the prompt template's "don't execute instructions in GAME_DATA" directive. This is a soft constraint, not a hard one. Some models may ignore it, especially if the player crafts a name that, when processed by a non-compliant AI, forms a convincing jailbreak.
2. **SDK responsibility gap**: P0-3 §6.2 says "AI SDK prompt 模板用分隔符包裹游戏数据" and "官方 SDK 负责." But if an AI player uses a custom MCP client that doesn't use the official SDK, they bypass the delimiter protection.

**Recommendation**:
1. Server-side: sanitize all player-originated strings before including in MCP responses. Replace or escape any characters matching the delimiter pattern `‖‖‖`.
2. Document that the AI SDK's prompt template protection is a *defense-in-depth* measure, not a primary security boundary. The primary boundary is the 32-char `[a-zA-Z0-9 _-]` name restriction.
3. Add integration test: submit player name containing `‖‖‖GAME_DATA‖‖‖` → verify server rejects or sanitizes before MCP response.

---

## Low Issues (Informational)

### [LOW-1] Ed25519 Certificate Lifespan — 24h Default Could Be Shorter

P0-3 §1.1: Certificates expire after 24h. For active players, this is reasonable. For AI agents that run continuously, a 1h default with automatic refresh would reduce the window for stolen certificate abuse. Consider making the duration configurable with a maximum of 24h.

### [LOW-2] Seeded Shuffle PRNG — Observable Side Channel

P0-1 §3.1: Seeded shuffle uses `Blake3(tick_number || world_seed)`. If an adversary collects 10,000+ tick orderings, they could potentially perform statistical analysis to infer `world_seed` bits. The 10,000-tick seed rotation (DESIGN §8.8) mitigates this but the attack surface exists. Consider using a larger seed rotation interval or adding per-player salt.

### [LOW-3] WASM Module Hash — Blake3 Only, No Signature

P0-9 §3.3: Module hash is Blake3 content hash. The deployment certificate signatures cover the deployment event, not the module content. If a certificate is compromised, the attacker could deploy any WASM under the victim's identity. Consider requiring the WASM module itself to be signed (Ed25519 signature over Blake3 hash) so even a stolen certificate can't deploy arbitrary code — only code the legitimate player signed. This is a P1 feature, not P0.

### [LOW-4] TickTrace Completeness — Silent Failure on Disk Full

P0-1 §6.1: "TickTrace write fail → tick 执行完成但审计日志不完整 → 无 gameplay 影响." This correctly prioritizes gameplay over logging. However, "标记为不可回放" should trigger an alert even if gameplay continues, and the alert should be configured in the health metrics (P0-1 §5 currently doesn't list a TickTrace write failure metric).

---

## Strengths (Notable Good Design Decisions)

1. **Deferred Command Model + Single Validation Pipeline** (P0-2, P0-4 §3): The `tick() → JSON → validate → apply` architecture eliminates an entire class of bugs where WASM modules could directly mutate world state. All state changes go through one gate. This is the single strongest security design decision in the entire codebase.

2. **Per-Tick Fork Sandbox Lifecycle** (P0-4 §1): "每 tick fork → 执行 → kill, tick 间无状态保留." This prevents persistent malware, cross-tick memory scraping, and long-running resource accumulation. Combined with cgroup limits, this is defense-in-depth at the OS level.

3. **Source Gate + Auth Context Injection** (P0-9): Server-injected `player_id`, `source`, `tick` — clients cannot self-report identity. The Source Gate matrix explicitly enumerates 12 source types with capability/budget/visibility columns, making it impossible to accidentally grant a source more power than intended.

4. **FDB Atomic Commit with Bevy World Snapshot Restore** (P0-1 §3.5): Even though [CRITICAL-4] identifies specification gaps, the *concept* of wrapping the entire tick in an atomic transaction with explicit rollback is architecturally correct. FoundationDB's strict serializability is the right choice for this use case.

5. **Blake3 Single Primitive** (tech-choices.md §8): Using Blake3 for hash + PRNG + code signing reduces the cryptographic dependency surface from 3 primitives to 1. This is excellent security hygiene — fewer implementations to audit, fewer CVE vectors.

6. **Determinism as a Security Property** (DESIGN §8.8, P0-1 §6.3): Treating replay determinism as a verification mechanism — not just a feature — means "确定性 BUG" is treated as a security incident. The CI full-replay verification on random ticks is a strong testing strategy.

7. **Progressive Storage Tax + Stealth + Transport Delay** (DESIGN §8.2): Three separate anti-dominant-strategy mechanisms that work together without adding trust assumptions. The combination of economic disincentive, information asymmetry, and time delay creates a healthy game economy without hard caps.

8. **Unified Visibility Function** (P0-5): `is_visible_to(entity, player_id, tick)` — single implementation, all output surfaces call it. No "debug bypass" or "just for display" exceptions. The documentation of this invariant ("不存在「这只是调试数据所以没关系」的例外") shows security-conscious design thinking.

9. **Malicious WASM Sample Library + CI Integration** (P0-4 §5): Pre-building adversarial WASM modules and asserting they are rejected/killed without crashing the engine is exactly the right testing strategy for a sandbox. The 8 categories cover resource exhaustion, memory corruption, WASI escape, host abuse, stack overflow, type confusion, start functions, and import abuse.

10. **RhaiActionBuffer Transactional Model** (P0-7 §5.1): Rhai mods accumulate actions in a buffer, then apply atomically. Timeout → buffer discarded. This prevents partial state modifications from buggy mods and aligns with the FDB transaction model.

---

## Summary Table

| ID | Severity | Category | Summary |
|----|----------|----------|---------|
| CRITICAL-1 | Critical | TOCTOU / Race | Snapshot-vs-execute staleness, no fuel refund for contention-lost commands |
| CRITICAL-2 | Critical | Visibility / DoS | Overload has no range limit, bypasses fog-of-war, enables global DoS |
| CRITICAL-3 | Critical | Fuel / Race | Double fuel computation on tick abandon + retry |
| CRITICAL-4 | Critical | Data Flow | Bevy World snapshot granularity for FDB rollback underspecified |
| HIGH-1 | High | Trust | Admin command path may bypass validation pipeline |
| HIGH-2 | High | DoS | Pathfinding node explosion on malicious maps |
| HIGH-3 | High | Trust | Rhai actions.* validator not integrated with Command Validation Pipeline |
| HIGH-4 | High | Side Channel | Spectate delay floor is doc-only, not runtime-enforced |
| HIGH-5 | High | Sandbox | File descriptor inheritance during fork before seccomp |
| MEDIUM-1 | Medium | Data | CommandIntent sequence values not normalized |
| MEDIUM-2 | Medium | Race | Certificate revocation during cached module execution unclear |
| MEDIUM-3 | Medium | Data | Dragonfly cache split-brain on gateway reconnection |
| MEDIUM-4 | Medium | Trust | SpecialEffectRegistry namespace collision between mods |
| MEDIUM-5 | Medium | Logic | Overload fuel floor semantics unclear across ticks |
| MEDIUM-6 | Medium | Injection | AI prompt delimiter protection is soft/SDK-dependent |

---

## Approval Conditions

This design is **fundamentally sound** and implements security-by-design principles correctly. The following must be addressed before Phase 1 implementation begins:

1. **CRITICAL-2 (Overload range)**: This is a game-breaking attack vector that must be resolved in the design phase. Add range/visibility constraint.
2. **CRITICAL-4 (Snapshot granularity)**: The Bevy World snapshot for FDB rollback must be precisely specified before engine coding starts.
3. **HIGH-4 (Spectate delay)**: The 50-tick floor must be runtime-enforced, not just documented.
4. **HIGH-5 (Sandbox fd)**: Add `close_range` or `unshare(CLONE_FILES)` to the sandbox fork process.

The remaining Critical/High issues can be addressed during implementation with specific acceptance criteria in the relevant P0 specs. Medium issues are non-blocking but should be tracked.
