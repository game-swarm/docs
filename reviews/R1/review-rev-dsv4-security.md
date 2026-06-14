# Swarm Security Audit — Deep Reasoning Perspective

**Auditor**: DeepSeek V4 Pro (rev-dsv4-security)
**Date**: 2026-06-14
**Scope**: PLANNER-OUTPUT.md + DESIGN.md + engine/ Phase 1 code (9 .rs files, 1 Cargo.toml)
**Verdict**: **REQUEST_CHANGES** — 4 Critical findings that must be resolved before Phase 2 proceeds.

---

## Verdict Rationale

The architecture is well-conceived: deterministic ECS core, WASM isolation, fuel metering, and the two-phase tick protocol are all sound design choices. However, the gap between design intent and code reality is wide. Phase 1 code is almost entirely stubs ("// TODO", println!-only systems, empty Snapshot, no wasmtime dependency). This is expected for early stage — but the design documents commit to specific security properties (parallel execution, deterministic ordering, replay) without the corresponding implementation primitives. The four Critical findings below are *latent* in the design and will manifest as soon as real game logic is wired in. They must be addressed in the architecture, not patched later.

---

## Critical (Must Fix Before Phase 2)

### CRITICAL-1: PathFind Unbounded Computation — Tick-Stalling DoS

**Files**: `engine/src/game_api.rs:39`, `ecs/components.rs:16-24`

The `PathFind` command accepts raw i32 coordinates with no boundary enforcement:

```rust
PathFind { from_x: i32, from_y: i32, to_x: i32, to_y: i32 }
```

**Attack Chain**:
1. Malicious player issues `PathFind { from_x: -2147483648, from_y: -2147483648, to_x: 2147483647, to_y: 2147483647 }`
2. A* or any grid pathfinder instantiates a search space of (2^32)^2 ≈ 1.8×10^19 cells
3. Open set explodes in memory; even with early pruning, this can consume seconds to minutes of CPU
4. Tick COLLECT phase stalls past the 2.5s wall-clock timeout, blocking all other players
5. L6 timeout kills the WASM instance, but the *host-side* pathfinding computation (invoked via `path_find()` host function, DESIGN §3.5.3) runs in the engine process itself — fuel metering does NOT cover host functions

**Root Cause**: The design delegates pathfinding to the host (`path_find(from, to) : PathResult` in Game API) but fuel metering (DESIGN §3.2.3 L3) only counts WASM instructions. If pathfinding is a host function call that the engine computes, it bypasses fuel accounting entirely. An attacker can burn engine CPU for the cost of a single WASM instruction (the `path_find` call).

**Fix**:
1. Define `MAX_PATH_LENGTH` (e.g., 200 tiles). Reject PathFind commands where Manhattan distance exceeds this bound *before* entering the pathfinder.
2. Pathfinding MUST be accounted against the player's fuel budget — either by running it inside WASM (player-supplied algorithm) or by deducting estimated CPU cost from the fuel meter when the host computes it.
3. All coordinates MUST be bounded by the map dimensions. `i32` is wrong: coordinates should be `u16` or `u32` clamped to `[0, MAP_DIM)`. Consider defining a `TileCoord(u32, u32)` newtype with checked construction.
4. Add a host-side compute budget (not just WASM fuel) per player per tick for host-computed operations.

---

### CRITICAL-2: Tick Protocol — No Error Isolation or Synchronization Primitive for Parallel Collect

**Files**: `engine/src/tick/mod.rs`, `engine/src/sandbox_interface.rs`

DESIGN §3.1.2 specifies a two-phase tick: COLLECT (parallel) → EXECUTE (sequential). Current implementation:

```rust
pub fn run_tick(app: &mut App) {
    // PHASE 1: COLLECT  ... (comment only)
    // PHASE 2: EXECUTE  ...
    app.update();  // ← single ECS pass, no collect/execute split
}
```

**Gap Analysis**:

| Property | Design Says | Code Has | Severity |
|----------|------------|----------|----------|
| Parallel player execution | "parallel" | No concurrency primitive | Critical |
| Per-player timeout (2.5s) | "Wall clock 2.5s" | No tokio::time::timeout | Critical |
| Error isolation | "Filter out invalid" | No error boundary per player | Critical |
| Collect→Execute barrier | Implicit phase boundary | Single `app.update()` | Critical |
| Mixed executor types | "WASM + MCP executors in parallel" (PLANNER §3.1) | Not implemented | Critical |

**Attack / Failure Chain**:
1. Player A's WASM module enters an infinite loop (not all loops are caught by fuel metering — host function callbacks can create re-entrant loops)
2. With no per-player `tokio::time::timeout`, the entire COLLECT phase waits indefinitely
3. Even with timeout, if Player A's timeout fires, the error must NOT affect Player B's collected commands
4. MCP executor (PLANNER §2.5) is inherently async and may have unbounded latency (network calls to external AI providers). Without a timeout + graceful degradation, one slow AI player blocks the tick

**Fix**:
1. Implement collect as `FuturesUnordered` + `tokio::time::timeout` per player with strict per-player isolation
2. Players that time out get zero commands for that tick (not an error that halts the engine)
3. Define a clear barrier between COLLECT and EXECUTE: collect must fully complete (timeouts counted) before any command is applied
4. For MCP executors: implement a "command buffer" model where late commands are queued for the *next* tick, not retroactively applied
5. Add a `TickPhase` state machine enum: `Collecting | Executing | Broadcasting` with transitions enforced at the type level

---

### CRITICAL-3: GetObjectsInRange — World State Exfiltration via Unbounded Range

**Files**: `engine/src/game_api.rs:37`

```rust
GetObjectsInRange { x: i32, y: i32, range: u32 }
```

With `range: u32::MAX` (4,294,967,295), this scans every entity in the world and returns a potentially enormous JSON response.

**Attack Chain**:
1. Player calls `GetObjectsInRange { x: 0, y: 0, range: 4294967295 }`
2. Engine iterates all entities in the entire world
3. Response JSON can be megabytes or tens of megabytes
4. This consumes: engine memory (building response), snapshot serialization time, WASM memory (receiving response), and network bandwidth
5. Repeated across ticks, this becomes a stealth DoS
6. Moreover, this circumvents fog of war / vision limits — the player gets full map knowledge

**Fix**:
1. Cap range to a gameplay-reasonable maximum (e.g., 50 tiles, configurable based on highest vision range)
2. Ensure vision/fog-of-war is enforced: objects outside the player's visible area are never returned regardless of range parameter
3. Add a response size cap. If the response would exceed N bytes, truncate with a warning
4. Deduct fuel for information queries. `GetObjectsInRange` returning 10,000 objects should cost proportionally more fuel than returning 10 objects

---

### CRITICAL-4: WASM Sandbox Not Integrated — Entire Security Model Untested

**Files**: `engine/Cargo.toml`, `engine/src/sandbox_interface.rs`

The Cargo.toml has NO `wasmtime` dependency. The `SandboxExecutor` trait exists but only `NoopExecutor` is implemented. This means **none** of the 6-layer sandbox security model (DESIGN §3.2.3) has been validated against real WASM modules.

**What's at stake**:
- Fuel metering (L3): Wasmtime's `FuelConsumptionMode` must be configured (Eager vs Lazy). Eager is safer but slower. The design must commit to one.
- WASI profile (L2): "Minimal profile" is stated but WASI has many capabilities. Need an explicit allowlist/denylist of WASI imports. An overly permissive WASI config gives WASM access to `clock_time_get` (could be used as a timing side channel) or `random_get` (breaks determinism).
- Module instantiation: DESIGN says "拒绝包含 start function 的模块". Wasmtime also has `_initialize` for Reactor modules. Need to audit all pre-execution entry points.
- Instance pooling: DESIGN §3.2.1 mentions "预热的 Wasmtime Instance (pooling)". If linear memory is not zeroed between ticks, state from Player A's tick could leak into Player B's tick. Wasmtime's pooling allocator can help but requires explicit configuration.
- Memory growth: Unbounded `memory.grow` calls from WASM can exhaust host memory. Must set a hard maximum on WASM linear memory (e.g., 64MB per instance).

**Fix**:
1. Add `wasmtime` to Cargo.toml with a pinned version. Define `WasmSandboxExecutor` implementing `SandboxExecutor` as the top priority for Phase 1.1 (not Phase 2).
2. Define an explicit WASI allowlist as code (not a comment): only `fd_write` for debug logging, nothing else.
3. Configure Wasmtime with: `FuelConsumptionMode::Eager`, max memory pages (64MB), no WASI `random_get` or `clock_time_get`, pooling allocator with full memory zeroing between ticks.
4. Write a security test harness: a set of malicious WASM modules that test each sandbox boundary (infinite loops, memory.grow bombs, host function abuse, bad imports).
5. The Module validation pipeline (DESIGN §3.2.1 step 4a-c) must be implemented as code, not comments, before accepting any player uploads.

---

## High (Should Fix Before Phase 3)

### HIGH-1: Command Ordering Determinism — No Sorted Key Defined

**Files**: `engine/src/tick/mod.rs:14` (comment), DESIGN §3.1.2

DESIGN says "Sort commands by game order (inter-player deterministic)" but defines no sort key. Two commands of the same type on the same target from different players — who wins?

**Risk**: If the sort key is implicitly `(player_id, command_index)`, then lower player_id always wins ties. This makes the system deterministic but systematically unfair. For replay to work, the sort key must be documented and versioned — changing it breaks all historical replays.

**Fix**:
1. Define and document the sort key explicitly: `(command_priority, timestamp, player_id, command_hash)` or similar
2. Add a `CommandPriority` enum: `Critical > High > Normal > Low`, assigned per command type
3. Version the sort key in the game protocol. Include it in replay metadata.
4. Add a fuzz test: replay the same tick with the same inputs 1000 times, assert identical final state

---

### HIGH-2: Snapshot Data Leak — No Vision / Fog of War in Data Model

**Files**: `engine/src/game_api.rs:43-47`, DESIGN §3.5.1

The `Snapshot` struct is a placeholder (`pub tick: u64`). When populated with real world state, it must respect vision boundaries. The design says "玩家可见的世界状态" but the data model has NO vision component.

**Risk**: Without a `VisionRange` or `VisibleTiles` component, the snapshot serialization code will default to "serialize everything," inadvertently leaking all players' positions to all other players.

**Fix**:
1. Add `Vision { range: u32 }` component to Drone and Structure entities
2. Snapshot construction must iterate only entities within the union of the player's visible tiles
3. Implement fog-of-war at the snapshot level, not just the rendering level
4. Consider that MCP AI players get the same snapshot as WASM players — no extra vision privileges

---

### HIGH-3: MCP Tools Expand Trusted Computing Base

**Files**: PLANNER-OUTPUT.md §2.2-2.4

The MCP server exposes 11 action tools and `swarm_get_snapshot`. These tools bypass the WASM sandbox entirely — they call engine internals directly via Rust function calls.

**Specific risks**:
- `swarm_get_snapshot` called outside of tick COLLECT phase returns live world state, giving AI players real-time information humans don't have
- MCP tools can be called at any cadence, not just once per tick. A compromised or aggressive AI agent can hammer the engine with queries between ticks
- "MCP authentication and per-player isolation" (PLANNER §2.4) is a single line item. The authentication model needs definition: is it API keys? OAuth2? Session tokens? What's the threat model for MCP clients?

**Fix**:
1. MCP tools must be phase-gated: `swarm_get_snapshot` only returns the *last committed* snapshot (from previous tick's BROADCAST phase), never live state
2. Rate-limit MCP tool calls per player per tick. At most one snapshot + N commands per tick cycle
3. Document the MCP authentication model. If the engine is on a private network, is MCP unauthenticated? If public, what auth?
4. MCP tool calls should go through the same `Command` validation pipeline as WASM commands — never bypass validation

---

### HIGH-4: Two-Phase Validation Trust Model Ambiguity

**Files**: DESIGN §3.1.2, tick/mod.rs

DESIGN Phase 1 says "Filter out invalid commands (out-of-quota, illegal actions)" and Phase 2 says "Validate against current world state." This implies two validation passes, but their relationship is unclear.

**Risk**: If Phase 1 validation is treated as "pre-filtering" and Phase 2 as "authoritative," then any code path that delivers commands directly to Phase 2 (e.g., MCP commands, admin tools, future gRPC API) bypasses Phase 1 filtering.

**Fix**:
1. Define Phase 1 validation as "static/mechanical" (syntax, quota, ownership pre-check) and Phase 2 as "dynamic/semantic" (state-dependent, conflict resolution)
2. Phase 2 MUST re-validate everything. Never assume Phase 1 caught all invalid commands.
3. Use Rust's type system: `RawCommand` (unvalidated) → `ValidatedCommand` (Phase 1) → Applied or Rejected (Phase 2). Make it impossible to apply a `RawCommand` directly.

---

### HIGH-5: Spawn Body Vector Unbounded — Memory Exhaustion

**Files**: `engine/src/game_api.rs:31`, `ecs/components.rs:36`

```rust
Spawn { spawn_id: ObjectId, body: Vec<BodyPart> }
```

No limit on `body.len()`. A malicious player can send `body: [MOVE; 10000000]`.

**Fix**:
1. Cap `body.len()` to a gameplay-defined `MAX_BODY_PARTS` (Screeps uses 50)
2. Enforce on deserialization: reject any `Spawn` command with `body.len() > MAX_BODY_PARTS`
3. Deduct spawn cost from player resources BEFORE creating the entity (cost is sum of body part costs). This prevents spawning drones the player can't afford.

---

## Medium (Worth Addressing)

### MEDIUM-1: ResourceType::Mineral(String) — Unbounded Arbitrary String in Game State

**Files**: `engine/src/ecs/components.rs:159`

Arbitrary `String` in an enum variant that flows through serialization, storage, and potentially logs/UI. If this string appears in HTML (frontend), it's an XSS vector. If it appears in SQL-like queries (ClickHouse), it's an injection vector.

**Fix**: Either constrain to a predefined set of mineral names (enum variants instead of String), or enforce a max length (e.g., 64 chars) and ASCII-only at deserialization boundaries.

---

### MEDIUM-2: No Depth Limit on serde_json Deserialization

**Files**: `engine/Cargo.toml` (serde_json), all types with `#[derive(Deserialize)]`

serde_json by default accepts arbitrarily nested JSON. An attacker sending 10,000-deep nested objects can cause a stack overflow during deserialization.

**Fix**: Configure `serde_json::Deserializer::with_depth_limit(256)` or use `#[serde(deny_unknown_fields)]` at minimum. Apply this at every deserialization boundary (Snapshot input, Command input, config loading).

---

### MEDIUM-3: i32 Coordinate Overflow in Movement

**Files**: `engine/src/ecs/components.rs:19-20`

Position uses `i32`. Movement directions add ±1 to coordinates without checked arithmetic. When a drone at `(0, 0)` moves `TopLeft`, it goes to `(-1, 1)` — which is outside the logical map but within i32 range.

**Fix**: Use `u32` for coordinates with map bounds checks, or use `i32` with `checked_add` / `saturating_add` and bounds enforcement at every mutation.

---

### MEDIUM-4: Deterministic Replay Requires Versioned Schemas

**Files**: DESIGN §3.1.3, all component types

DESIGN says "全量 Replay：任意房间状态可完全重现." But the component types use `#[derive(Serialize, Deserialize)]` without versioning. If `TerrainType` gains a `DeepWater` variant in a future update, old replays with terrain data will fail to deserialize.

**Fix**: Add a protocol version field to all persisted types. Use `#[serde(tag = "type")]` or explicit version discriminants. Consider message framing with version headers for all persisted data.

---

### MEDIUM-5: Snapshot Not Populated — Vision Logic Not Designed

**Files**: `engine/src/game_api.rs:43-47`

The `Snapshot` struct is empty. What goes into it determines the entire information boundary between engine and player code. This must be designed with security in mind:
- Include player's own entities (all properties)
- Include visible other-player entities (limited properties — e.g., position + type, not resource amounts)
- Include terrain for visible tiles only
- Never include: other players' resource totals, room controller claim progress of hostile rooms, unit internals of enemies without `Observer`

---

### MEDIUM-6: GameError Carries User-Controlled Strings

**Files**: `engine/src/error.rs`

`InvalidCommand(String)`, `Sandbox(String)`, etc. — these carry arbitrary error messages. If error messages are reflected to players (via WebSocket/console), they could contain crafted content. A WASM module that triggers an error with a 10MB message string becomes a DoS vector.

**Fix**: Use static error codes with optional bounded context. Don't propagate unbounded arbitrary strings in errors. Use `&'static str` for error messages where possible.

---

## Informational (Defense in Depth)

### INFO-1: serde_json Float-to-Int Coercion is Silent

serde_json by default converts JSON floats to integer types: `"amount": 3.14` becomes `3u32` silently. This allows players to send malformed data that "works" but means something different than intended. Enable `serde_json::Deserializer::from_reader` with `reject_float_truncation` or use `#[serde(deserialize_with = "...")]` for integer fields.

### INFO-2: No Content Security Model for Player-Generated Strings

PLANNER-IDENTIFIED risk "Prompt injection via game state → sanitize all player-generated strings" is correct but unspecific. When MCP players receive game state as context, player-named entities (drone names, structure names, mineral names) become prompt injection vectors. Define "sanitize" concretely: strip control characters, limit length, escape for the target context (JSON/HTML/plain text).

### INFO-3: MCP Tool Explosion Expands Attack Surface

11 MCP tools are planned (PLANNER §2.2). Each tool adds a new input vector to the engine. Consider collapsing them: instead of 11 separate tools, expose a single `swarm_submit_commands` tool that takes a `Vec<Command>` — mirroring the WASM interface exactly. This reduces attack surface to one validated path.

### INFO-4: Dragonfly Cache Consistency with Tick Transitions

DESIGN §4.2 uses Dragonfly for "当前 tick 的世界状态快照 (频繁读写)." During a tick transition (COLLECT → EXECUTE), the cache contains stale data from the previous tick. If any code path reads from cache during EXECUTE, it sees pre-mutation state inconsistently. Document the cache invalidation protocol per tick phase.

### INFO-5: No Fuzzing Infrastructure

The codebase has no fuzz targets. Given the security-critical nature of JSON deserialization, WASM module loading, and command validation, fuzzing should be part of CI from Phase 1. Add `cargo-fuzz` targets for: Snapshot deserialization, Command deserialization, WASM module validation, pathfinding.

### INFO-6: Engine Cargo.toml Missing wasmtime — No Sandbox Testing Possible

The engine crate lacks `wasmtime` as a dependency. This means the `SandboxExecutor` trait cannot be tested with real WASM modules. At minimum, add wasmtime as a `[dev-dependency]` so security tests can exercise the sandbox boundary.

---

## Attack Surface Summary

```
                    ┌─────────┐
                    │ Players │
                    └────┬────┘
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
   ┌──────────┐  ┌───────────┐  ┌───────────┐
   │WASM code │  │ MCP tools │  │ REST/WS   │
   │(14_host  │  │(11_tools) │  │(auth_     │
   │ _calls)  │  │           │  │ boundary) │
   └────┬─────┘  └─────┬─────┘  └─────┬─────┘
        │              │              │
        ▼              ▼              ▼
   ┌─────────────────────────────────────┐
   │        ENGINE (Rust)                │
   │  ┌─────────────────────────────┐    │
   │  │ SandboxExecutor trait       │ ◄── 1 impl (Noop)
   │  │ ┌───────────────────────┐   │    │
   │  │ │ Host functions (TODO) │   │    │
   │  │ │ • path_find ← CRIT-1  │   │    │
   │  │ │ • move_to             │   │    │
   │  │ └───────────────────────┘   │    │
   │  └─────────────────────────────┘    │
   │  ┌─────────────────────────────┐    │
   │  │ Tick protocol (stub)        │ ◄── CRIT-2
   │  └─────────────────────────────┘    │
   │  ┌─────────────────────────────┐    │
   │  │ Command validation (TODO)   │ ◄── CRIT-3, HIGH-4
   │  └─────────────────────────────┘    │
   │  ┌─────────────────────────────┐    │
   │  │ ECS Systems (println stubs) │    │
   │  └─────────────────────────────┘    │
   └─────────────────────────────────────┘
```

**Verdict summary**:
- **4 Critical**: PathFind DoS, Tick isolation gaps, GetObjectsInRange exfiltration, WASM sandbox not integrated
- **5 High**: Command ordering ambiguity, Snapshot vision leak, MCP TCB expansion, two-phase validation ambiguity, Spawn body unbounded
- **6 Medium**: Mineral string injection, JSON depth, coordinate overflow, schema versioning, empty snapshot design, error string DoS
- **6 Informational**: Float coercion, prompt injection, tool explosion, cache consistency, fuzzing gap, missing dev dependency

**Recommendation**: Do not proceed to Phase 2 (MCP server + AI players) until CRITICALs 1-4 are resolved. The WASM sandbox integration (CRIT-4) is a prerequisite for validating all other security properties. Without it, the engine has no security model — only an aspiration.
