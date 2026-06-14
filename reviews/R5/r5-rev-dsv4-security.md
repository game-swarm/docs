# R5 Final Security Review — rev-dsv4-security

**Reviewer**: Security Reviewer — DeepSeek V4 Pro
**Date**: 2026-06-14
**Scope**: /data/swarm/docs/design/DESIGN.md + /data/swarm/docs/specs/p0/ (all 9 specs)
**Profile**: Tick protocol consistency, data-flow tracing, race condition detection, algorithmic boundaries, trust assumptions

---

## Verdict: CONDITIONAL_APPROVE

The architecture is fundamentally sound. The deferred command model, single validation pipeline, process-level WASM sandboxing, and source-gated auth context together form a strong security posture. The conditions below are concrete and addressable — none represent architectural flaws.

---

## 1. Security Posture Summary

### 1.1 What Works Well (Strong Points)

| Area | Strength |
|------|----------|
| **WASM Sandbox** | Per-tick fork→execute→kill lifecycle. No state retention between ticks. seccomp + cgroup v2 + no-network-namespace triple isolation. Wasmtime version-pinned. |
| **Command Model** | Deferred: `tick() → Command[]`. No mutating host functions exposed to WASM. All state changes go through the single `validate → apply` pipeline. No bypass. |
| **Fuel Metering** | CPU instruction counting, not wall-clock. Per-tick 10M fuel budget. Refund policy with anti-amplification: credits only apply to next tick, capped at 10% refund + 1.1× max budget cap, same-source-repeat = first-only refund, 80% refund rate for 3 consecutive ticks triggers throttle. |
| **Auth Context** | Server-injected, client cannot self-report. Source Gate at pipeline entry disallows non-WASM sources from submitting gameplay commands. |
| **Visibility** | Single `is_visible_to()` function consumed by all output surfaces. Cached per (tick, player_id). Leak detection tests mandated. |
| **Determinism** | ChaCha12 PRNG + Blake3 hash + IndexMap + ECS `.chain()` + no f64. Full replay verifiability. |
| **IDL Single Source** | game_api.idl generates Rust, TS, MCP schemas, docs. CI enforces generated code matches committed code. |
| **Tick Failure** | Well-specified failure matrix. FDB commit failure → tick abandon + fuel refund + retry. Degraded mode after 3 consecutive abandons. BROADCAST failure never rolls back committed tick. |
| **Tutorial Isolation** | Tutorial worlds use separate namespace. Tutorial-source commands rejected outside tutorial worlds — enforced at engine level, not convention. |

### 1.2 Trust Boundary Map

```
Untrusted               Semi-trusted              Trusted
─────────               ────────────              ───────
WASM module             Rhai rule mod             Engine core (Rust)
Player-provided strings (server-installed)         Validator pipeline
MCP client              World config TOML          ECS systems
                        (server-owner)             FDB transaction
                                                   Auth context injection
```

No "trust downstream to validate" assumptions found. The architecture explicitly rejects this pattern via the single pipeline design (P0-2 §1).

---

## 2. Conditions (Must Address Before Phase 2 Implementation)

### HIGH-1: WASM Module Cache Poisoning via Stale Validation

**Location**: P0-4 §7 (Compilation Budget) + §2.4 (Module Validation)

**Finding**: WASM modules are cached by `(module_hash, wasmtime_version)`. The validation checks imports against a host function allowlist. If the allowlist changes (e.g., a host function is removed or renamed), cached modules validated against the old allowlist will still be served — with imports that no longer match the current host function table. This could cause:
- Crashes when the module calls a now-removed host function
- Information leaks if a host function was repurposed with different semantics

**Recommendation**: Add `host_function_allowlist_hash` to the cache key. On allowlist change, force re-validation of all cached modules.

---

### HIGH-2: Rhai Sandbox — `eval` Not Explicitly Disabled

**Location**: DESIGN.md §8.7 (Rhai API) + P0-7

**Finding**: Rhai scripts run inside the engine process. The DESIGN.md trust model states "服主自行安装，可信" (server-owner installed, trusted). However, Rhai's built-in `eval` function allows dynamic code execution from strings. If a mod's config parameter (user-supplied) is interpolated into a string that gets `eval`'d, this becomes a code injection vector within the trusted boundary.

Additionally, `actions.modify_entity(entity_id, property, value)` in DESIGN.md §8.7 has no documented scope. Which properties can a mod modify? Can it change `Owner`, `Hits`, or `Controller.level`? The scope should be explicitly constrained.

**Recommendation**:
1. Explicitly disable `eval` in the Rhai engine configuration: `engine.set_allow_eval(false)`.
2. Document the allowed `modify_entity` properties — limit to economic/resource adjustments, not ownership or structural integrity.
3. Even though mods are server-installed, apply the principle of least privilege: Rhai scripts should have the minimum engine access needed.

---

### HIGH-3: Refund Policy — OutOfRange Does Not Distinguish TOCTOU vs Player Error

**Location**: P0-2 §7.1 (Refund Rules) + §3.7 (Attack TOCTOU)

**Finding**: The refund policy table classifies `OutOfRange` as "不退" (no refund) with rationale "玩家应检查距离". However, P0-2 §3.7 explicitly acknowledges the TOCTOU window for Attack: "如果目标在快照和执行之间移动了，按当前位置检查范围 → 移开则 OutOfRange. 攻击不跟踪移动目标." A player whose target was in-range at snapshot time but moved during execution gets no refund — yet this is a contention outcome (target moved due to other players' actions), not a player error. This is inconsistent with the refund policy for `SourceEmpty` and `TileOccupied`, which DO provide 50% refund for contention losses.

**Recommendation**: Split `OutOfRange` into two rejection codes:
- `OutOfRange_SelfError`: Player targeted something beyond valid range → no refund
- `OutOfRange_TargetMoved`: Target was in range at snapshot time but moved before execution → 50% refund (parity with other contention refunds)

---

### HIGH-4: "Late Commands Queue" Underspecified — Race Condition Risk

**Location**: P0-1 §2.2 (Collection Timeout)

**Finding**: The spec states: "迟到指令排入下一个 tick 的队列" (late commands are queued for the next tick). No mechanism is described for how commands arriving after the 2500ms COLLECT deadline but before/during EXECUTE are:
1. Detected (what constitutes "late"?)
2. Stored (where is the queue?)
3. Associated with the correct tick (do they target tick N or N+1?)
4. Subject to fuel accounting (charged to which tick?)

If a player's WASM returns at COLLECT+2600ms with commands that reference entities as they existed in tick N's snapshot, applying them in tick N+1 will produce entity-not-found or stale-data rejections — silently degrading that player's effectiveness without explanation.

**Recommendation**: Either:
- (Preferred) Drop late commands entirely and document this clearly. The player gets 0 commands for that tick and must adapt in the next tick. This is simpler and matches the current timeout behavior.
- Or design an explicit late-command queue with: deduplication, tick-target validation (commands must reference tick N+1 snapshot not tick N), and separate fuel accounting.

---

## 3. Medium-Severity Items

### MED-1: No Wasmtime Security Patch SLA

**Location**: P0-4 §2.1

**Finding**: Wasmtime version is pinned to `=30.0`. CI runs `cargo audit` for CVE detection. However, no SLA is defined for how quickly a critical Wasmtime CVE must be patched. A zero-day in the WASM runtime is the most likely escape vector from the sandbox.

**Recommendation**: Define a patch SLA: Critical Wasmtime CVE → patch within 24 hours. High → within 72 hours. Document the rollback procedure if a patched wasmtime version breaks determinism.

---

### MED-2: MCP swarm_simulate Missing from Rate Limit Table

**Location**: P0-3 §4.4 vs §5.1

**Finding**: `swarm_simulate` is listed as a tool in §4.4 (Development Aids) with rate limit "按需" (on-demand), but is absent from the rate limit table in §5.1. P0-9 gives it a 5/tick rate limit but without budget specification. `swarm_simulate` runs WASM code in a dry-run context — it consumes real CPU resources even though it doesn't affect world state.

**Recommendation**: Add `swarm_simulate` to P0-3 §5.1 with explicit rate limit (5/tick, consistent with P0-9) and document its fuel budget (0.5× MAX_FUEL as specified in P0-9).

---

### MED-3: _initialize Function Not Blocked

**Location**: P0-4 §2.4 (Module Validation step 4)

**Finding**: The validation checks for and rejects `_start` function export. However, the WASM component model and newer WASM specs use `_initialize` as an alternative pre-invocation hook. Only `_start` is explicitly blocked.

**Recommendation**: Also check for and reject `_initialize` export during module validation. Add `_initialize` to the malicious WASM sample library test cases.

---

### MED-4: WASM Module ABI Version — No Runtime Mismatch Detection

**Location**: P0-8 §2 (IDL Format) + P0-4 §7 (Module Caching)

**Finding**: The IDL has an `abi_version` field that increments on host function signature changes. However, the WASM module format has no embedded ABI version marker that the engine can check at load time. If the engine is upgraded (ABI v1 → v2) and a cached module compiled for ABI v1 is loaded, the module will call host functions with wrong signatures — leading to memory corruption or undefined behavior inside the sandbox.

**Recommendation**: 
1. Require WASM modules to export a constant `ABI_VERSION: i32` that the engine checks at load time.
2. Reject modules whose `ABI_VERSION` doesn't match the engine's current version.
3. On ABI version bump, invalidate all cached modules.

---

### MED-5: Transfer/Withdraw Cost Semantics Ambiguous

**Location**: P0-8 §2 (IDL — Transfer and Withdraw command definitions)

**Finding**: The IDL defines:
```yaml
Transfer:
    cost: { transfer_amount: amount }
Withdraw:
    cost: { withdraw_amount: amount }
```
The `cost` field is semantically overloaded — it's unclear whether this means "the resource cost of executing this command" or "the amount being transferred/withdrawn." If interpreted as the former, a Transfer of 50 Energy would cost 50 Energy to execute (doubling the actual cost). If interpreted as the latter, it's not a cost at all — it's the operation parameter. The validator already checks `has_resource` separately.

**Recommendation**: Clarify that `cost` represents the fuel/execution cost of the command, not the resource being moved. Or rename the field to avoid ambiguity: `resource_movement: { resource: Energy, amount: 50 }` vs `cost: {}`.

---

## 4. Informational Items

### INFO-1: Deploy Rate Limit Asymmetry

**Location**: P0-3 §5.1 vs P0-9 §2.2

**Finding**: MCP_Deploy (AI) is rate-limited to 10/hour. Deploy (human via Web UI) is listed as 1/tick = ~1200/hour. This is a 120× asymmetry. While deployment is infrastructure (not gameplay), and the asymmetry is intentional (AI might be more prone to rapid iteration abuse), the rationale should be documented.

### INFO-2: No Explicit ASLR/Exploit Mitigation Documentation

**Location**: P0-4 §4 (OS Isolation)

**Finding**: The seccomp and cgroup configurations are well-documented. However, standard exploit mitigations (ASLR, NX, stack canaries, RELRO, PIE) for the sandbox worker binary are not mentioned. These are typically compiler/linker defaults for Rust binaries but should be explicitly verified and documented.

**Recommendation**: Add a section to P0-4 confirming that the sandbox worker binary is compiled with: `-C relocation-model=pie`, full RELRO, stack canaries, and that the kernel has ASLR enabled (`kernel.randomize_va_space=2`).

### INFO-3: Missing Operational Security Documentation

**Location**: Cross-cutting

**Finding**: The following operational security topics are not addressed in any P0 spec:
- `world_seed` storage and access control (who can read it? where is it stored?)
- JWT signing key rotation procedure
- FoundationDB credential management
- Backup encryption requirements
- nginx/TLS certificate lifecycle

**Recommendation**: These are Phase 3+ concerns but should be tracked as a P1 spec (e.g., P0-10 Operational Security) to ensure they aren't overlooked.

### INFO-4: Pathfinding Algorithmic Boundary

**Location**: P0-2 §4.3 + P0-4 §8

**Finding**: Pathfinding is bounded by MAX_PATH_LENGTH=100 and 10 calls/tick. Fuel cost is 10,000 + 50/tile base. Worst case: 100-tile path × 10 calls = 15,000 × 10 = 150,000 fuel out of 10,000,000 (1.5%). Acceptable. However, the actual pathfinding algorithm is not specified. A* on a hex grid with room dimensions up to ~50×50 = 2,500 nodes is bounded, but with obstacles creating complex mazes, the explored node count could spike. The terrain-hash cache mitigates this when terrain is static. The real bound is the path length limit (100 steps), which implicitly bounds A* exploration.

No action required for MVP, but the pathfinding implementation should include a per-call node-expansion limit (e.g., 10,000 nodes) as a defense-in-depth measure regardless of path length constraints.

---

## 5. Data Flow Trace: Snapshot → WASM → Commands → Validator → ECS

Full trace performed. Summary:

```
Tick N COLLECT:
  visibility_filter(all_entities, player, tick) → Snapshot
  Snapshot serialized to JSON → written to WASM linear memory
  WASM tick(snapshot_ptr, snapshot_len) executes
    ├── WASM may call host_get_terrain, host_get_objects_in_range, host_path_find
    │   └── All read-only, fuel-metered, call-count limited
    └── Returns pointer to Command[] JSON in WASM memory
  Engine reads Command[] JSON from WASM memory
  JSON schema validation (max 256KB, depth≤10, max 100 commands)

Tick N EXECUTE:
  Seeded shuffle of player order
  Per sorted command:
    Source Gate check → pass (source=WASM)
    Auth context verification
    Per-command validation (existence, ownership, body parts, range, resources)
    If valid → apply to world state (in FDB transaction)
    If invalid → record RejectionReason
  FDB commit (atomic)
  ECS systems run in .chain() order

Tick N BROADCAST:
  Delta computation (entities changed)
  Dragonfly cache update
  NATS publish → Gateway → WebSocket clients
```

**Integrity check result**: Each step has explicit validation. No unvalidated data crosses the trust boundary.

**Verified**: WASM output enters the same Command Validation Pipeline as all other sources (P0-2 §1). The pipeline is non-bypassable. The Source Gate (P0-9 §4) blocks non-WASM sources from submitting gameplay commands.

---

## 6. Race Condition Scan

| Scenario | Status | Notes |
|----------|--------|-------|
| Two players harvest same Source | HANDLED | First-come-first-served per shuffled order. Latter gets `SourceEmpty` + 50% refund. |
| Two players build on same tile | HANDLED | First build succeeds, second gets `TileOccupied` + 50% refund. |
| Attack target moves between snapshot and execution | PARTIAL | OutOfRange rejection, but no refund (see HIGH-3). |
| Player deploys new WASM during their own tick execution | HANDLED | Deployment takes effect next tick. Current tick uses already-loaded module. |
| Late WASM response after COLLECT timeout | UNDEFINED | "Late queue" mechanism underspecified (see HIGH-4). |
| FDB transaction conflict during EXECUTE | HANDLED | Retry 3 times, then tick abandon + fuel refund + degraded mode. |
| Two MCP deploy calls in same tick | HANDLED | Rate-limited to 10/hour. Last deploy wins, next-tick activation. |
| Visibility cache computed then entity moves within same tick | BY DESIGN | Snapshot taken at tick start. Commands execute later but validate against current state. This is the TOCTOU window — documented and handled per-command. |

---

## 7. Final Assessment

The Swarm P0 design is security-conscious and architecturally coherent. The deferred command model with single validation pipeline eliminates entire classes of bugs (direct state manipulation from WASM, validation bypass, source spoofing). The WASM sandbox design follows defense-in-depth: Wasmtime fuel metering + OS seccomp/cgroup + process isolation + per-tick lifecycle.

The four HIGH conditions are concrete and addressable — they represent edge cases and specification gaps, not fundamental design flaws. Addressing them before Phase 2 implementation will close the identified windows without requiring architectural changes.

**Action items for Phase 1 resolution:**
- HIGH-1 through HIGH-4: spec updates to P0-4, P0-7, P0-2, P0-1 respectively
- MED-1 through MED-5: tracked as Phase 1 implementation requirements
- INFO-1 through INFO-4: tracked for Phase 3+ operational readiness

---

*Review completed 2026-06-14. This document is part of the Architecture Freeze gate.*
