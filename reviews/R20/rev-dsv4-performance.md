# R20 性能评审 — DSV4

> 评审员: rev-dsv4-performance (性能)
> 日期: 2026-06-18
> 职责: 验证 R19 Blocker + 用户裁决闭合

---

## 总体 Verdict: APPROVE

全部 10 项验证通过 (6 R19 Blockers + 4 用户裁决)，所有传播残留已在 R20 文档中正确闭合。IDL YAML 与派生文档 (api-registry.md, engine.md, spec 文件) 一致性良好。

---

## 逐项判定

| ID | 状态 | 证据 |
|----|------|------|
| **B19-1** | CLOSED | RejectionReason canonical 35 codes 在 game_api.idl.yaml §2 完整定义; auth_api.idl.yaml add 12 codes (1001-1012); api-registry.md §2 合计 47 codes + debug_detail (512B) + detail_level (competitive/practice/training); 02-command-validation.md §3 显式引用 registry, 旧码 Fatigued/NotMovable 等标记为 (debug_detail) 不进入 wire enum |
| **B19-2** | CLOSED | auth_api.idl.yaml 独立文件: 5 lifecycle + 6 cert/device tools = 11 auth tools; game_api.idl.yaml §3 Auth category 仅 2 简化 tools 并注明 auth_api 完整 schema; api-registry.md §3 分列 Game API (46) + Auth API (11) 双源 |
| **B19-3** | CLOSED | swarm_deploy replay_class: game_api.idl.yaml L881 → `deploy_mutation`; api-registry.md L277 → `deploy_mutation`; api-registry.md §11 完整 deploy_mutation 机制文档 (FDB manifest + fdb_version_counter + async object store) |
| **B19-4** | CLOSED | 8 fixed-point types 注册: game_api.idl.yaml §type_registry (7 types: ResourceRate_i64, ProgressBps_i64, BasisPoints, EfficiencyBps, ConfidenceBps, milli_distance, micro_cost) + economy.idl.yaml §1 (MilliUnits); 所有 IDL YAML 中无 f64 残余; api-registry.md §0 统一 fixed-point type registry 表; game_api.idl.yaml §limits.worker_pool_max=256, worker_pool_hard_cap=1000 |
| **B19-5** | CLOSED | game_api.idl.yaml §5: worker_pool_max=256 (runtime default), worker_pool_hard_cap=1000 (compile-time hard cap); api-registry.md §5.5: Worker pool max=256, Worker pool hard cap=1000; engine.md §3.4.2: 公式 `worker_pool_size = min(max_pool, active_players)` + clamp(hard_cap) — 三文档一致 |
| **B19-6** | CLOSED | economy.idl.yaml 独立文件: 7 resource operations (RecycleRefund/StorageTax/UpkeepDeduction/PvEAward/BuildCost/SpawnCost/AlliedTransfer); 全部 BasisPoints/u64/u32 整数类型; 4-tier storage tax (0/1/5/20 bp); 4 canonical formulas; api-registry.md §10 全量引用 |
| **U1/A** | CLOSED | auth_api.idl.yaml 独立 — api_version 0.1.0, 自有 rejection_reason namespace (1000+), 自有 trace events, 自有 security columns |
| **U2/B** | CLOSED | economy.idl.yaml 独立 — api_version 0.1.0, 自有 types/operations/formulas/limits, 与 game_api 无 f64 冲突 |
| **U3/A** | CLOSED | worker_pool default 256 + hard_cap 1000 — game_api.idl.yaml (L1421-1422) / api-registry.md (§5.5) / engine.md (§3.4.2) 三处一致 |
| **U4/A** | CLOSED | swarm_deploy replay_class: deploy_mutation — game_api.idl.yaml (L881) / api-registry.md (§3.2, §11) 一致; 完整 deploy_mutation 流程文档化 (blob upload → FDB manifest → tick boundary activation) |

---

## GAP: 无

本轮未发现 GAP。所有 10 项在 IDL YAML 权威源与派生文档间闭合一致。

---

## 性能视角附注 (非阻塞)

以下为性能评审员对当前设计的观察，非 blocker，供参考：

1. **Snapshot build p99 ≤50ms with 50K entities**: api-registry.md §5.1 约定 global entity cap = 50,000, engine.md §3.4.1 要求 snapshot build ≤50ms p99。Bevy World 深拷贝 50K 实体的 p99 延时需要实测验证——此预算在 32-core/64GB 硬件上可达成，但需 CI 回归覆盖。

2. **Worker pool 256 → 1000 过渡**: engine.md §3.4.2 注明 1000 hard cap 需要"运营商显式启用 worker_pool_max > 256 并承担容量证明"。此 gate 机制在 IDL 中未显式定义 (仅限 compile-time hard cap 概念)，建议在 engine.md 中补充启用流程。

3. **Pathfinding fair-share 与 worker 分配解耦**: engine.md §3.4.2 的 pathfinding 份额 = `floor(100000 / active_players)`, allocation 在 tick 开始时固定。当 active_players > worker_pool_size (如 500 players / 256 workers), fair-share 的 "先到先得" 可能导致 worker dispatch 顺序影响分配公平性。建议在 capacity derivation 中注明此隐式依赖。
