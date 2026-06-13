# P0-4: WASM Sandbox Baseline

> **Status**: Phase 2 blocker | **Rulings**: D2 (process isolation) | **Sources**: C4, S2 consensus

## 1. Architecture

```
┌──────────────────────────────────────────┐
│  Engine Process                           │
│  ┌────────────────────────────────────┐  │
│  │  Tick Scheduler                     │  │
│  │  "execute player 42, tick 4521"     │  │
│  └──────────────┬─────────────────────┘  │
│                 │ gRPC                    │
└─────────────────┼────────────────────────┘
                  │
                  ▼
┌──────────────────────────────────────────┐
│  Sandbox Worker Process (per player)      │
│  ┌────────────────────────────────────┐  │
│  │  OS Isolation:                      │  │
│  │  seccomp(bpf) — allowlist syscalls  │  │
│  │  cgroup v2 — memory/CPU/pids caps   │  │
│  │  no network namespace               │  │
│  │  read-only rootfs                   │  │
│  │  private /tmp (tmpfs, size=16MB)    │  │
│  └────────────────────────────────────┘  │
│  ┌────────────────────────────────────┐  │
│  │  Wasmtime Engine                    │  │
│  │  ┌──────────────────────────────┐  │  │
│  │  │  WASM Module Instance         │  │  │
│  │  │  - fuel: 10M instructions     │  │  │
│  │  │  - memory: 64MB               │  │  │
│  │  │  - no WASI fs/network/clock   │  │  │
│  │  └──────────────────────────────┘  │  │
│  └────────────────────────────────────┘  │
│  Lifecycle: process per tick → kill      │
└──────────────────────────────────────────┘
```

**Lifecycle**: Sandbox worker process is FORKED for each tick, executes one player, returns commands, then KILLED. No state persists between ticks in the sandbox process. This prevents:
- Cross-tick memory exfiltration
- Long-running process resource accumulation
- Supply-chain attacks from compromised WASM modules persisting

## 2. Wasmtime Configuration

### 2.1 Dependency

```toml
# Cargo.toml
wasmtime = "=30.0"   # PINNED — no auto-upgrades
```

CVE monitoring: `cargo audit` in CI. CHANGELOG reviewed manually on each `wasmtime` version bump.

### 2.2 Engine Configuration

```rust
let mut config = wasmtime::Config::new();

// === Fuel Metering ===
config.consume_fuel(true);                    // Enable fuel metering
config.fuel_consumed_callback(|fuel| {        // Checkpoint callback
    if fuel > MAX_FUEL { panic!("fuel exhausted"); }
});

// === Memory Limits ===
config.static_memory_maximum_size(64 * 1024 * 1024);  // 64MB
config.dynamic_memory_reserved_for_growth(0);          // No dynamic growth
config.memory_guard_size(2 * 1024 * 1024);             // 2MB guard pages
config.guard_before_linear_memory(true);                // Guard before AND after

// === Table Limits ===
config.table_elements_max(10_000);

// === Stack Limits ===
config.max_wasm_stack(1 * 1024 * 1024);       // 1MB stack

// === Instance Limits ===
config.max_instances(1);
config.max_wasm_memory_pages(1024);            // 64MB / 64KB pages

// === Compiler ===
config.cranelift_opt_level(wasmtime::OptLevel::Speed);  // Production: Speed
                                                        // Debug: SpeedAndSize

// === Threads ===
config.wasm_threads(false);                    // NO threading
config.wasm_simd(true);                        // SIMD allowed (performance)
config.wasm_relaxed_simd(false);               // No relaxed SIMD

// === Epoch Interruption ===
config.epoch_interruption(true);               // Kill on deadline
```

### 2.3 WASI Configuration

ALLOWLIST — only these WASI functions:

```rust
// ALLOWED (engine host functions, not WASI)
// Game API host functions: see §4

// WASI: NONE by default
let mut wasi = wasmtime_wasi::WasiCtxBuilder::new();
// No args, no env, no preopened dirs, no stdin/stdout/stderr
// This blocks: fd_read, fd_write, path_open, clock_time_get, random_get,
//              sock_accept, environ_get, args_get, proc_exit

// Explicitly NOT allowed:
// ❌ wasi:cli/*        — no filesystem
// ❌ wasi:clocks/*     — no clock (enables timing attacks)
// ❌ wasi:random/*     — no random (use seeded PRNG via host function)
// ❌ wasi:sockets/*    — no network
// ❌ wasi:http/*       — no HTTP
```

### 2.4 Module Validation (Pre-Execution)

```rust
fn validate_module(wasm_bytes: &[u8]) -> Result<(), Rejection> {
    // 1. Size check
    if wasm_bytes.len() > 5 * 1024 * 1024 {
        return Err(Rejection::ModuleTooLarge);  // 5MB max
    }

    // 2. Parse + validate WASM binary
    let module = wasmtime::Module::from_binary(&engine, wasm_bytes)?;

    // 3. Check exports: must export "tick" function
    let tick = module.get_export("tick")
        .ok_or(Rejection::MissingTickExport)?;

    // 4. Check NO start function (prevents pre-execution)
    if module.export("_start").is_some() {
        return Err(Rejection::StartFunctionForbidden);
    }

    // 5. Check imports: only allowed host functions
    for import in module.imports() {
        if !ALLOWED_HOST_FUNCTIONS.contains(import.name()) {
            return Err(Rejection::IllegalImport(import.name()));
        }
    }

    Ok(())
}
```

## 3. Allowed Host Functions (Game API)

The ONLY functions callable from WASM:

```rust
// Movement
fn host_move(object_id: i64, direction: i32) -> i32;

// Harvesting
fn host_harvest(object_id: i64, target_id: i64) -> i32;
fn host_transfer(object_id: i64, target_id: i64, resource: i32, amount: i32) -> i32;

// Building
fn host_build(object_id: i64, x: i32, y: i32, structure_type: i32) -> i32;

// Combat
fn host_attack(object_id: i64, target_id: i64) -> i32;
fn host_heal(object_id: i64, target_id: i64) -> i32;

// Information (charged against fuel budget)
fn host_get_terrain(x: i32, y: i32) -> i32;
fn host_get_objects_in_range(x: i32, y: i32, range: i32, out_ptr: i32, out_len: i32) -> i32;
fn host_path_find(from_x: i32, from_y: i32, to_x: i32, to_y: i32, out_ptr: i32, out_len: i32) -> i32;

// Snapshot access (snapshot JSON passed as WASM memory, not host function)
// tick(ptr: i32, len: i32) -> i32  ← exported, receives snapshot, returns commands JSON
```

All return `i32`: 0 = success, negative = error code.
All `out_ptr`/`out_len` pairs: WASM allocates buffer, host writes result, re-checks bounds.

## 4. OS Isolation

### 4.1 seccomp (syscall filter)

Bare minimum syscalls for Wasmtime runtime:

```c
// ALLOWED
read, write, mmap, mprotect, munmap,
brk, madvise, membarrier,
futex, nanosleep,
sigaltstack, rt_sigaction, rt_sigreturn,
clone (CLONE_VM | CLONE_VFORK only), exit, exit_group

// EVERYTHING ELSE BLOCKED
// ❌ open, openat, stat, unlink, mkdir, chmod
// ❌ socket, connect, bind, listen, accept
// ❌ fork, execve
// ❌ clock_gettime
// ❌ getrandom
```

### 4.2 cgroup v2

```
memory.max = 128MB          // 2x Wasmtime memory for runtime overhead
memory.swap.max = 0          // NO swap
cpu.max = 250000 3000000     // 0.25 CPU seconds per 3s tick period
pids.max = 32                // Max 32 threads (Wasmtime + compiler)
```

### 4.3 Network Namespace

Sandbox process has NO network namespace. No lo, no eth0. gRPC communication with engine is via Unix domain socket (passed as fd before seccomp lock).

## 5. Malicious WASM Corpus

### 5.1 Test Categories

| Category | Example |
|----------|---------|
| **Resource exhaustion** | Infinite loop, 100MB allocation, 10K function calls |
| **Memory corruption** | Out-of-bounds access, use-after-free via stack |
| **WASI escape** | Attempt `fd_write`, `clock_time_get`, `random_get` |
| **Host abuse** | Call `host_path_find` 10K times, pass huge out_ptr |
| **Stack overflow** | Deep recursion, 10K nested calls |
| **Type confusion** | i64 → f64 reinterpret cast, NaN boxing |
| **Start function** | Module with `_start()` that executes before `tick()` |
| **Import abuse** | Module importing non-existent host functions |

### 5.2 CI Integration

```bash
# In CI
cargo test --test wasm_sandbox -- --test-threads=1
# Each test:
# 1. Compile malicious WASM
# 2. Load into sandbox worker
# 3. Assert: REJECTED (not loaded) OR TIMEOUT (killed) OR OOM (killed)
# 4. Assert: engine process still alive (not crashed)
```

## 6. Resource Budgets

| Resource | Limit | Enforcement |
|----------|-------|-------------|
| Fuel (CPU instructions) | 10,000,000 | Wasmtime fuel metering |
| Memory (WASM linear) | 64 MB | Wasmtime config |
| Memory (total process) | 128 MB | cgroup memory.max |
| Execution time (wall) | 2500 ms | Epoch interruption |
| WASM module size | 5 MB | Pre-validation |
| Host function calls | 1000/tick | Counter in host functions |
| path_find calls | 10/tick | Host function counter |
| get_objects_in_range calls | 5/tick | Host function counter |
| Output JSON size | 256 KB | Size check on return value |
