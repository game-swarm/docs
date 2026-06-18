# R24 Closure Verification — 安全方向 (DeepSeek V4 Pro)

> **轮次**: R24 Closure Verification
> **评审员**: rev-dsv4-security (DeepSeek V4 Pro)
> **日期**: 2026-06-19
> **验证文档**: design/README.md, specs/core/04-wasm-sandbox.md, specs/core/05-persistence-contract.md, design/engine.md
> **验证范围**: B3 (SIMD禁用+D5/A), B4 (容量证明)

---

## [B3] SIMD禁用 + D5/A

### SIMD禁用

**CLOSED** — SIMD禁用策略已在三处文档中明确闭合：

| 位置 | 证据 |
|------|------|
| `04-wasm-sandbox.md` §2.2 L94 | `config.wasm_simd(world_config.simd_enabled)` — 注释："SIMD 由 world.toml 控制：**默认禁用**，仅显式 opt-in `deterministic_subset` 时启用" |
| `04-wasm-sandbox.md` §2.2 L95 | `config.wasm_relaxed_simd(false)` — "不允许 relaxed SIMD（始终禁用）" |
| `engine.md` §3.4.3 L407 | "SIMD（默认禁用；允许 opt-in deterministic integer subset，需跨架构验证）" |

**三层防护完整性**：默认禁用（安全基线） → opt-in 需 `deterministic_subset` 显式声明（防止误启用） → relaxed SIMD 始终禁用（消除非确定性向量）。跨架构验证要求作为 opt-in 的前置条件已写明，消除 x86/ARM 间 SIMD 行为差异导致的确定性破坏。

### D5/A

**CLOSED** — 对象存储异步写入模型的完整闭合：

| 位置 | 证据 |
|------|------|
| `05-persistence-contract.md` §3 L121 | "D5/B 裁决：对象存储写入改为异步——FDB commit 先完成，blob upload 在后台执行" |
| `05-persistence-contract.md` §3 (Phase A-D) | 完整的 Tick Commit 序列：Phase B (FDB 原子提交) → Phase C (对象存储异步写入，3次指数退避重试) → Phase D (WAL 截断) |
| `05-persistence-contract.md` §3 (Async Upload Status Tracking) | `upload_status` 四态机：`pending` → `uploading` → `complete` / `failed`。每态对 tick state 完整性的影响明确 |
| `05-persistence-contract.md` §4 | 6 种失败场景矩阵，覆盖 FDB commit 失败/成功 + blob 写入成功/失败/超时/etag 回填失败的全部组合 |
| `05-persistence-contract.md` §6.1 | 孤儿 blob 清理策略：由于 FDB 先于对象存储写入，正常流程不产生孤儿；唯一异常场景（blob 写入成功 + etag 回填失败）→ GC 扫描 1h 后清理 |

**关键不变量已确立**：FDB commit 成功 = tick 持久化完成。blob 写入不再是 tick commit 的前提条件。Replay verifier 以 FDB manifest 为权威，`upload_status` 决定 replay 可用性。异步模型不存在数据丢失窗口。

---

## [B4] 容量证明

**CLOSED** — 容量证明已在两处文档中以具体 benchmark gate 和数学推导形式闭合：

### Benchmark Gates (`05-persistence-contract.md` §8.3)

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
| Rollback Bevy snapshot/restore | 500 entities | p99 < 50ms |

明确后果声明："Gate 失败 → 对应容量声明不可信，需降级规模或优化实现"。

### 容量推导 (`engine.md` §3.4.2)

| 指标 | 硬值 | 推导方式 |
|------|------|---------|
| Active players | target 500 / hard cap 1000 | 基于 p50=5ms WASM 执行时间 × collect budget 推导 |
| Aggregate CPU Admission Formula | `floor(TICK_BUDGET_COLLECT_MS × CPU_CORES × PER_CORE_MIPS)` | 含 Admission 控制：`effective_per_player_quota < MIN_FUEL` → 拒绝新玩家 |
| Worker Pool | 256 default / 1000 hard cap | 动态伸缩公式：`min(worker_pool_max, active_players)` |
| 500-player 推导 | p50=5ms × 500 = 2500ms = Collect budget | 含 p99 余量分析 |
| 1000-player 推导 | 并行化 wall-clock ~25ms (1000 workers / 40 cores) + overhead ~500ms | 含 per-player fuel 极度受限的警告 |
| Per-player fair-share | `floor(global_budget / active_players)` | pathfinding 100,000 explored nodes/tick 全局预算按活跃玩家均分 |

**关键安全属性已覆盖**：
- Admission 控制防止 CPU 饱和扩散到已连接玩家
- Per-player fair-share 防止单玩家垄断全局寻路资源
- 超 hard cap 明确拒绝策略 (`ERR_WORLD_FULL`)
- Worker pool 边界定义清晰（空闲回收 5min、每 worker 1000 tick 强制替换）

---

## Verdict: APPROVE

**所有待验证项均已正确闭合**：

- **B3 (SIMD禁用+D5/A)**: SIMD 三层防护策略完整，异步 blob 写入的失败语义和孤儿清理完整定义
- **B4 (容量证明)**: 9 项 benchmark gate 含具体判定标准 + 完整容量推导公式 + Admission/fair-share 控制策略

无 GAP 项。
