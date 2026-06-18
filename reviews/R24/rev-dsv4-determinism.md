# R24 Closure Verification — 确定性方向 (DeepSeek V4 Pro)

**验证轮次**: R24 (Closure Verification)
**评审员**: rev-dsv4-determinism (DeepSeek V4 Pro)
**方向**: 确定性
**待验证 R23 项**: B3 (确定性合同+SIMD+D5/A+Disrupt D3/A), B4 (benchmark gates)

---

## 验证结果

### B3.1 — Determinism Contract (确定性合同)

[B3.1] **CLOSED**

确定性合同已在 `specs/core/01-tick-protocol.md` §9「确定性合同」中完整定义，覆盖以下子合同：

| 子节 | 内容 | 位置 |
|------|------|------|
| §9.1 | 命令全局排序键 — 5 层分层排序 `(priority_class, shuffle_index, source_rank, sequence, command_hash)` | L743-758 |
| §9.2 | 部署生效时序 — `swarm_deploy` 下一 tick 生效，`fdb_version_counter` 全序重放 | L762-772 |
| §9.3 | 输出状态合同 — WASM/MCP/WebSocket/Replay 各消费端版本语义表 | L776-789 |
| §9.4 | TickTrace 完整性 — FDB 事务原子写入 state + trace + fuel | L793-803 |
| §9.5 | RNG 确定性 — 按 namespace 隔离的 Blake3 XOF 派生流 | L823-832 |
| §9.6 | ECS 调度权威顺序 — serial spine + 3 parallel sets | L836-851 |
| §9.7 | WASM output 截断 — 256KB 硬上限，超限整批丢弃 | L854-856 |
| §9.8 | RuleMod / 动态 action 边界 — 固定点数、单一路径、IDL 注册 | L858-861 |

确定性依赖声明见 §7.1 (L624-632)：PRNG=Blake3 XOF、Hash=Blake3 固定实现、排序=确定键、ECS=`.chain()` 串行、数值=整数+定点(f64 禁用)、HashMap=`indexmap`。

### B3.2 — SIMD

[B3.2] **CLOSED**

SIMD 配置明确改为**默认禁用**，仅显式 opt-in 启用：

**`04-wasm-sandbox.md` §2.2 (L94-95)**:
```rust
config.wasm_simd(world_config.simd_enabled);       // SIMD 由 world.toml 控制：默认禁用
config.wasm_relaxed_simd(false);                    // relaxed SIMD 始终禁用
```

**`engine.md` §3.4.3 (L407)**:
> 禁用的 WASI：...SIMD（默认禁用；允许 opt-in deterministic integer subset，需跨架构验证）

关键变更：
- `wasm_simd` 不再硬编码为 `true`，改为由 `world.toml` 的 `simd_enabled` 字段控制
- 默认值为 `false`（禁用）
- `wasm_relaxed_simd` 硬编码为 `false`，永不启用
- Opt-in 需显式设置 `deterministic_subset` + 跨架构验证

此变更直接修复 R23 Critical 发现"WASM SIMD World 模式默认启用破坏跨架构确定性"。

### B3.3 — D5/A (Replay-Critical Subset 分类)

[B3.3] **CLOSED**

`05-persistence-contract.md` §2「Replay-Critical Subset（权威声明）」明确定义了持久化分层中的分类边界：

**§2.1 Replay-Critical — FDB 原子提交（不可降级）** (L34-49)：
10 项必填字段随每 tick FDB 事务原子提交：`tick`, `state_checksum`, `system_manifest_hash`, `world_config_hash`, `mods_lock_hash`, `commands`+`rejections`, `fuel_ledger`, `deploy_activation_decision`, `canonical_codec_version`, `terminal_state`。

**§2.2 Debug/Rich — 对象存储异步写入（可降级）** (L51-59)：
3 项可降级字段：`tick_trace_blob`, `snapshot_delta_blob`, `replay_artifact_blob`。明确声明"缺失不影响 deterministic replay"。

**§3 D5/B 裁决** (L121)：对象存储写入改为异步——FDB commit 先完成，blob upload 后台执行。

连同 `api-registry.md` §12 (L796, L802) 的 D5/B + R22 B1 persistence 条目，完整覆盖了 replay-critical subset 的分类与持久化合同。

### B3.4 — Disrupt D3/A (body part match)

[B3.4] **CLOSED**

`06-phase2b-system-manifest.md` §2 S16-S22 表 (L210)：
```
disrupt_system | `disrupt` | DisruptState, Entity (action), Entity (body_parts) 
               | Entity (interrupted) — 要求 body part match（R23 D3/A）
```

Disrupt 系统现在明确要求 body part match，读取 `Entity (body_parts)` 进行校验后再写入 `Entity (interrupted)`。此约束防止不属于该 body part 类别的操作被错误打断。

### B4 — Benchmark Gates

[B4] **CLOSED**

`05-persistence-contract.md` §8.3「Synthetic Benchmark 要求」(L374-388) 定义了 9 个 benchmark gate：

| Benchmark | 目标 | 判定标准 |
|-----------|------|---------|
| Command validate loop | 100k commands/tick | p99 < 50ms |
| Command apply loop | 100k commands/tick | p99 < 100ms |
| Entity snapshot clone | 50k entities | p99 < 20ms |
| Entity snapshot restore | 50k entities | p99 < 30ms |
| Snapshot stitching | 1000 × 256KB snapshots | p99 < 100ms |
| FDB single-tx commit | 500 active players | p99 < 200ms, conflict < 1% |
| FDB room-partition commit | 1000 active players, 200 rooms | p99 < 500ms, per-room conflict < 1% |
| Pathfinding | 50×50 A* nodes, 100 concurrent ops | p99 < 10ms/node, fair-share |
| Rollback Bevy snapshot/restore | 500 entities, all components | p99 < 50ms, **entity ID allocator verified** |

每个 gate 有明确的：目标规模、判定标准、失败语义（"Gate 失败 → 对应容量声明不可信，需降级规模或优化实现"）。

最后一项 "entity ID allocator verified" 直接回应 R23 发现中关于快照 entity_id 排序需确认 Bevy allocator 恢复的问题。

---

## Verdict: APPROVE

所有待验证项均已正确定义并闭合，证据可追溯至具体文档位置。

- [B3.1] CLOSED — `01-tick-protocol.md` §9 确定性合同（8 子节全覆盖）
- [B3.2] CLOSED — `04-wasm-sandbox.md` §2.2 SIMD 默认禁用
- [B3.3] CLOSED — `05-persistence-contract.md` §2 replay-critical subset 分类 + D5/B async 模型
- [B3.4] CLOSED — `06-phase2b-system-manifest.md` L210 Disrupt body part match (R23 D3/A)
- [B4] CLOSED — `05-persistence-contract.md` §8.3 9 项 benchmark gate（含 entity ID allocator 验证）
