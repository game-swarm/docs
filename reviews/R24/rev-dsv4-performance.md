# R24 CV — 性能评审 (DeepSeek V4 Pro)

> **Closure Verification**: 仅验证 R23 共识 Blocker 与 D-items 是否正确闭合。
> **评审方向**: 性能
> **待验证项**: B3 (SIMD禁用), B4 (容量证明+D6/B room-partition+D2/B drone cap)

---

## B3 — SIMD禁用

**[B3] CLOSED**

证据（双重交叉验证）:

1. `specs/core/04-wasm-sandbox.md` §2.2 (L94-95):
   ```
   config.wasm_simd(world_config.simd_enabled);  // SIMD 由 world.toml 控制：**默认禁用**，仅显式 opt-in `deterministic_subset` 时启用
   config.wasm_relaxed_simd(false);              // 不允许 relaxed SIMD（始终禁用）
   ```
   — Wasmtime 配置层：`wasm_simd` 默认禁用，`wasm_relaxed_simd` 编译期硬编码为 false，无绕过路径。

2. `design/engine.md` §3.4.3 Sandbox 生命周期 (L407):
   ```
   禁用的 WASI：clock、random、filesystem、network、env、process、threads、atomics、SIMD（默认禁用；允许 opt-in deterministic integer subset，需跨架构验证）
   ```
   — 引擎级禁用清单：SIMD 列入显式禁用项，opt-in 须满足 deterministic integer subset + 跨架构验证两个前置条件。

闭合判断: SIMD 在 Wasmtime config 和引擎禁用清单两层均默认为禁用状态。唯一启用路径 (world.toml opt-in) 有严格的 deterministic_subset 约束和跨架构验证要求。无未闭合缺口。

---

## B4 — 容量证明 + D6/B room-partition + D2/B drone cap

### B4.1 容量证明 (Synthetic Benchmarks)

**[B4-容量证明] CLOSED**

证据: `specs/core/05-persistence-contract.md` §8.3 (L372-388) 定义了 9 项 benchmark gate：

| Benchmark | 目标 | 判定标准 |
|-----------|------|---------|
| Command validate loop | 100k commands/tick | p99 < 50ms |
| Command apply loop | 100k commands/tick | p99 < 100ms |
| Entity snapshot clone | 50k entities | p99 < 20ms |
| Entity snapshot restore | 50k entities | p99 < 30ms |
| Snapshot stitching | 1000 × 256KB snapshots | p99 < 100ms |
| FDB single-tx commit | 500 active players | p99 < 200ms, conflict rate < 1% |
| FDB room-partition commit | 1000 active players, 200 rooms | p99 < 500ms, per-room conflict rate < 1% |
| Pathfinding | 50×50 A*, 100 concurrent | p99 < 10ms/node, fair-share guarantee |
| Rollback Bevy snapshot/restore | 500 entities, all components | p99 < 50ms |

Gate 失败语义: "对应容量声明不可信，需降级规模或优化实现" — 明确的失败后果。

闭合判断: 容量声明的 verifiable proof 已通过具体的 benchmark gate 定义完成。每个 gate 有明确的目标规模、p99 阈值和失败语义。

### B4.2 D6/B — FDB Room-Partition

**[B4-D6/B] CLOSED**

证据: `specs/core/05-persistence-contract.md` §8 (L340-389):

§8.1 分区策略:
- 单事务 MVP: ≤50 active players, ≤100 rooms — 整个 world 单 FDB 事务
- Room-Partition: >50 active players 或 >100 rooms — 每个 room 独立 FDB 事务分区
- Key layout: `/swarm/{shard}/{room_id}/{tick}/{...}`
- Cross-room operations: 2-phase commit (source room → target room)

§8.2 实现约束:
| 约束 | 单事务 MVP | Room-Partition |
|------|-----------|---------------|
| FDB 事务大小 | < 10KB | < 2KB/room |
| 对象存储异步写入超时 | 5s; 3 次重试 | 5s; 3 次重试 |
| Cross-room conflict | N/A | 2PC, timeout 3s, fallback best-effort |

闭合判断: 分区策略有明确的分区阈值 (50 players / 100 rooms)、key layout、2PC 跨房间操作语义、per-room 事务大小上限 (<2KB) 和超时参数 (3s)。单事务与分区模式的条件边界清晰。

### B4.3 D2/B — 三层 Drone Cap

**[B4-D2/B] CLOSED**

证据（两处权威源交叉验证）:

1. `design/engine.md` §3.4.2 容量合同 (L307):
   ```
   Per-player drone cap: 50 (per-room per-player baseline, world.toml configurable; R23 D2/B 三层 cap)
   — per-room / per-player / per-world 三层取较小值
   ```

2. `specs/reference/api-registry.md` §5.1 (L469-471):
   ```
   Per-player drone cap: 50 — world.toml 可调；per-room per-player baseline（R23 D2/B 三层 cap）
   Per-room drone cap: 500 — world.toml；RCL 表定义 room-level total，与 per-player cap 取较小值
   Global drone cap: 10,000 — 全局活跃 drone 上限
   ```

三层结构:
- Layer 1 (per-room per-player): 50 baseline
- Layer 2 (per-room total): 500 (RCL 表细化)
- Layer 3 (global): 10,000

取较小值语义: engine.md 明确 "三层取较小值"。RoomCap 生命周期约束在 engine.md §3.2 Phase 2b (L254) 中有详细读写顺序定义 (`death_mark → spawn`)。

闭合判断: 三层 drone cap 在 engine.md (性能合同) 和 api-registry.md (权威容量源) 中均有明确定义，包含具体数值和取较小值语义。RCL 表进一步细化 per-room cap。

---

## Verdict: APPROVE

所有待验证项 (B3, B4.1/B4.2/B4.3) 均为 CLOSED，证据充分且可交叉验证。

| 项 | 状态 | 证据位置 |
|----|------|---------|
| B3 SIMD禁用 | CLOSED | 04-wasm-sandbox.md §2.2, engine.md §3.4.3 |
| B4 容量证明 | CLOSED | 05-persistence-contract.md §8.3 |
| B4 D6/B room-partition | CLOSED | 05-persistence-contract.md §8.1-8.2 |
| B4 D2/B drone cap | CLOSED | engine.md §3.4.2, api-registry.md §5.1 |
