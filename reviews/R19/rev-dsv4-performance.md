# R19 Performance Review — rev-dsv4-performance

**Reviewer**: Performance Reviewer (DSV4)
**Date**: 2026-06-18
**Verdict**: **CONDITIONAL_APPROVE** (1 GAP, no consensus blocker)

---

## 1. R18 Blocker Closure Verification

| ID | Status | Evidence |
|----|--------|----------|
| B1 | CLOSED | api-registry.md is auto-generated from game_api.idl.yaml. Header: "冲突时以 YAML 为准". Cross-checked all 10 sections — no YAML↔Markdown discrepancies found. |
| B2 | CLOSED | RejectionReason: 35 canonical wire-enum codes + `debug_detail` field (512 bytes, non-canonical) + `detail_level` enum (competitive/practice/training). YAML §2 matches api-registry.md §2. |
| B3 | CLOSED | MCP Tools: exactly 46 active tools across 8 categories (Onboarding/Auth/Play/Deploy/Debug/Admin/SDK/Resources). swarm_list_market_orders moved to RFC. Auth category added. |
| B4 | CLOSED | TickTrace Envelope: 22 fields. `wasm_status` → `terminal_state` explicit enum (7 variants: Success/FuelExhausted/TimeoutExceeded/SnapshotOverBudget/CommandBufferFull/InternalError/NotExecuted). YAML §6 matches api-registry.md §6. |
| B5 | CLOSED | All 46 MCP tools carry 5 security columns in YAML §3: `replay_class`, `visibility_filter`, `rate_limit_key`, `required_scope`, `subject_source`. Reflected in api-registry.md. |
| B6 | CLOSED | ResourceOperation defined in both YAML §9 and api-registry.md §9. All 6 resource-touching actions listed with flow directions. |
| B7 | CLOSED | Capacity contract now provable — Aggregate CPU Admission Formula, Worker Pool Derivation, 500/1000 Player Capacity Derivation all documented in engine.md §3.4.2. Per-player fair-share admission formalized. |

## 2. R18 User Decision Closure Verification

| ID | Status | Evidence |
|----|--------|----------|
| D1 | CLOSED | api-registry.md fully auto-generated from game_api.idl.yaml. All 11 sections present. |
| D2 | CLOSED | Same as B2 — 35 canonical codes + debug_detail + detail_level. |
| D3 | CLOSED | 02-command-validation.md §3.18: `refund_pct = max(0.1, 0.5 × (remaining_lifespan / total_lifespan))` → 10%-50% range. Verified with examples table (50%→25%→10%). |
| D4 | N/A | Storage tax tiered rates (0/1/5/20bp) — economy domain, not in performance reviewer's file set. |
| D5 | CLOSED | async_object_store_upload fully specified: YAML §11 + api-registry.md §11. Deploy flow: upload blob (async) → commit manifest (FDB) → activate (next tick). FDB only stores small manifest {blob_hash, object_store_key, size, uploaded_at, status}. |
| D6 | N/A | soft_launch 3-phase PvP — game mode domain, not in performance reviewer's file set. |
| DA1 | CLOSED | swarm_deploy replay_class = `idempotent_mutation` in both YAML §3 and api-registry.md §3. |
| DA2 | CLOSED | Core state uses integer + fixed point (u64/i64). engine.md §3.4.8: 比例计算 = `amount * basis_points / 10000`. 01-tick-protocol.md §7.1: "整数 + 定点数，禁用 f64". f64 appears only in display/output schemas (e.g., efficiency display, income_rate display) — not in game state. |
| DA3 | **GAP** | See §3.1 below. |

## 3. GAPs Found

### 3.1 GAP-H1: Worker Pool MAX_POOL 分叉 (DA3) — engine.md vs YAML

**Location**: engine.md §3.4.2 / game_api.idl.yaml §5 limits.hardware_baseline / api-registry.md §5.5

**Discrepancy**:

| Source | Value | Context |
|--------|-------|---------|
| YAML (authoritative) | `worker_pool_max: 256` | limits.hardware_baseline |
| api-registry.md | `max_pool = 256` | §5.5 Hardware Baseline |
| engine.md | `MAX_POOL = 1000（hard cap，编译期常量）` | §3.4.2 Worker Pool 推导 |

**Impact**: The capacity derivation scenarios in engine.md all assume `MAX_POOL = 1000`:

```
450 player scenario:  pool = min(1000, 450) = 450 workers
750 player scenario:  pool = min(1000, 750) = 750 workers
1000 player scenario: pool = min(1000, 1000) = 1000 workers
```

With authoritative `MAX_POOL = 256`:
```
450 player scenario:  pool = min(256, 450) = 256 workers
750 player scenario:  pool = min(256, 750) = 256 workers
1000 player scenario: pool = min(256, 1000) = 256 workers
```

The 1000-player hard cap derivation ("1000 workers / 40 cores → 25ms wall-clock") is invalidated — with 256 workers, per-worker queue depth ≈ 4 players, wall-clock ≈ 20ms + 500ms overhead ≈ 520ms. The hard cap still holds (fuel throttling absorbs the difference) but the derivation math is wrong.

**Fix**: Update engine.md §3.4.2 to use `MAX_POOL = 256` and recalculate the capacity derivation scenarios.

### 3.2 OBS-P1: MAX_PATH_LENGTH 分叉

| Source | Value |
|--------|-------|
| 02-command-validation.md §6 | `MAX_PATH_LENGTH = 100` |
| YAML §5.2 | `pathfinding_result_path_max: 500` |
| engine.md §3.4.2 | `Pathfinding result path: 500 nodes max` |
| api-registry.md §5.2 | `Pathfinding result path: 500 nodes max` |

02-command-validation.md has a stale value (100); authoritative sources agree on 500.

### 3.3 OBS-P2: Sandbox pids.max 分叉

| Source | Value |
|--------|-------|
| wasm-sandbox.md §4.2 | `pids.max = 32` (Wasmtime + 编译器线程) |
| wasm-sandbox.md §9.1 | `pids.max: 16` (统一 OS 加固表) |

Two values within the same document. The §9.1 unified table should be authoritative.

### 3.4 OBS-H3: Recycle 退还比例双写

02-command-validation.md §10.3 says "标准退还: body part spawn 总成本的 50%" (always 50%), but §3.18 correctly implements the lifespan-scaled formula `max(0.1, 0.5 × (remaining_lifespan / total_lifespan))` per D3. §10.3 needs updating.

## 4. Performance-Specific Observations

### EXECUTE Budget Inconsistency

| Source | EXECUTE Budget |
|--------|---------------|
| engine.md §3.4.1 | EXECUTE (2a+2b) ≤ 400ms |
| 01-tick-protocol.md §1.4 | EXECUTE timeout 500ms |

Not a hard conflict — engine.md ≤400ms is a performance target, tick-protocol 500ms is a timeout. But they should align to avoid confusion.

### FDB Transaction Size

| Source | Statement |
|--------|-----------|
| engine.md §3.4.2 | "小事务（head/manifest/hash/pointer）" |
| 01-tick-protocol.md §9.4 | "事务大小 < 10MB（FDB 推荐上限）" |

Consistent — small manifests only, large blobs go to object store.

### Capacity Derivation Integrity (post-fix)

After fixing DA3 (MAX_POOL = 256), the 500-player target derivation still holds:
- 500 players / 256 workers ≈ 2 players/worker → p50=5ms → ~10ms wall-clock
- With snapshot overhead (~500ms): ~510ms total — well within 2500ms COLLECT budget
- 1000-player hard cap: 4 players/worker → ~20ms + 500ms = ~520ms — fuel-throttled but viable

### Sandbox Memory Limits

Consistent across all sources: WASM linear memory 64MB, cgroup process-level 128MB (2× margin). Per-tick Store reset prevents memory accumulation. OOM/trap/timeout → immediate worker replacement + audit log.

## 5. CrossCheck — Recommended Verification by Other Reviewers

1. **Economy Reviewer**: D4 Storage tax tiered rates (0/1/5/20bp) — verify these are documented in gameplay specs. Not in performance reviewer's file set.
2. **Game Mode Reviewer**: D6 soft_launch 3-phase PvP — verify implementation in modes.md or related spec.
3. **Architecture Reviewer**: Confirm MAX_POOL = 256 is the intended value (not 1000 from engine.md). The 1000-worker assumption changes the parallelism model significantly — from "one worker per player" to "4 players per worker" at peak load.

---

*Review completed with YAML IDL as authoritative source (per constraint).*
