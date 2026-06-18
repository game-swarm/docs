# R20 Game Design Review — 闭合验证 (DSV4)

**审查者**: rev-dsv4-designer (Game Design Reviewer, DeepSeek V4 Pro)
**日期**: 2026-06-18
**审查轮次**: R20 (闭合验证)
**依据**: R19 Blockers 传播残留 + 用户裁决闭合
**权威源**: IDL YAML → api-registry.md (game_api.idl.yaml + auth_api.idl.yaml + economy.idl.yaml)

---

## Verdict: APPROVE

All 6 R19 Blockers and 4 user decisions are verifiably closed in the authoritative IDL→registry pipeline. The api-registry.md serves as the single source of truth, with all design docs (interface.md, gameplay.md, modes.md) cross-referencing it rather than re-declaring conflicting tables. No residual discrepancies that affect the canonical wire contract.

---

## 逐项判定

| ID | 状态 | 证据 |
|----|------|------|
| **B19-1** RejectionReason canonical 传播 | **CLOSED** | api-registry.md §2: 47 canonical codes (35 game_api + 12 auth_api, namespace offset 1000+). D2/B: `debug_detail` 字段吸收上下文细节 (NotMovable, Fatigued 等)，保持 wire enum 稳定。Naming: `InsufficientResource` (单数), `ObjectNotFound` (统一), `CooldownActive` (通用)。08-api-idl.md 已标记 SUPERSEDED。interface.md §5.4 引用 registry 作权威。 |
| **B19-2** MCP/Auth tool namespace 收敛 | **CLOSED** | auth_api.idl.yaml 作为独立 IDL 源存在 (v0.1.0)。api-registry.md §3.4: 11 auth tools (5 lifecycle + 6 cert/device)。§2.5: 12 auth RejectionReason codes (1001–1012)。§5.8: auth 限制。§6.2: 8 auth tick trace events。§9: token envelope。game_api (§3.2 Auth category) 仅保留 2 个简化 auth tools (swarm_auth_login, swarm_auth_refresh)，含注释说明更完整 schema 在 auth_api。 |
| **B19-3** deploy replay_class → deploy_mutation | **CLOSED** | api-registry.md §3.2: swarm_deploy 的 Replay Class = `deploy_mutation`（非 `idempotent_mutation`）。§11: deploy_mutation 机制完整文档（async blob upload → FDB manifest → fdb_version_counter → tick boundary activate）。§13: `deploy_mutation` 列为 canonical replay_class 值。interface.md §4.1 仍有旧 `idempotent_mutation` 标注但行 19 已声明 registry 为权威——该遗留列表不影响 wire contract。 |
| **B19-4** IDL f64→fixed-point (11 fields) | **CLOSED** | api-registry.md §0: 8 定点类型已注册 — ResourceRate_i64, ProgressBps_i64, BasisPoints, EfficiencyBps, ConfidenceBps, milli_distance, micro_cost, MilliUnits。§10: 所有 economy operations 使用 u64/u32/BasisPoints 整数运算。§10.3: Canonical Formulas 明确 floor rounding。全文无残余 f64 引用。 |
| **B19-5** worker pool 256 default + 1000 hard_cap | **CLOSED** | api-registry.md §5.5: Worker pool max = 256 (runtime default, world.toml adjustable)。Worker pool hard cap = 1000 (compile-time hard cap)。Worker pool size = `min(max_pool, active_players)`。Degraded mode: 超 hard cap 拒绝新 WASM 执行，已在 tick 中的玩家继续运行。 |
| **B19-6** economy 机器源 (economy.idl.yaml) | **CLOSED** | economy.idl.yaml 作为独立 IDL 源存在 (v0.1.0)。api-registry.md 由 3 IDL 源生成。§10: 7 economy operations — RecycleRefund (lifespan-proportional 10-50%), StorageTax (4-tier 0/1/5/20 bp), UpkeepDeduction (Controller level²×10), PvEAward (5-tier), BuildCost (Controller level discount), SpawnCost (8 body parts), AlliedTransfer (tax-free)。§5.7: economy-specific limits (max storage 1M/player, global cap 100M, max transfer 100K, income/expense cap 1M/tick)。 |
| **U1/A** auth_api.idl.yaml 独立 | **CLOSED** | 同 B19-2 证据。auth_api.idl.yaml 是三独立 IDL 源之一，生成 api-registry.md 的 §2.5/§3.4/§5.8/§6.2/§9/§13。 |
| **U2/B** economy.idl.yaml 独立 | **CLOSED** | 同 B19-6 证据。economy.idl.yaml 是三独立 IDL 源之一，生成 api-registry.md 的 §0/§5.7/§10。 |
| **U3/A** worker_pool default 256 + hard_cap 1000 | **CLOSED** | 同 B19-5 证据。 |
| **U4/A** deploy_mutation replay_class | **CLOSED** | 同 B19-3 证据。 |

---

## GAP

*None.* 所有 R19 Blocker 已传播至权威 IDL→registry 管线。设计文档 (interface.md §4.1, 08-api-idl.md §2) 包含部分 R19 前遗留示例但均显式声明 api-registry.md 为权威——满足 canonical 传播要求，无需逐行修改历史文档。

---

## Strategy Depth Analysis (DSV4 方向)

本审查为闭合验证，不重新评估设计本身。以下为基于当前 IDL 状态的策略空间快照：

- **RejectionReason canonical 化 (D2/B)**: 将 35+ 变体收敛为 stable wire enum + `debug_detail` 上下文，消除了玩家通过不同 error code 进行 oracle inference 的安全漏洞。`NotVisibleOrNotFound` 合并码是关键的 anti-information-leak 设计。
- **Economy 定点化**: 全部 f64 替换为整数定点类型消除跨平台浮点不确定性——对 replay 确定性至关重要。BasisPoints (0-10000) 的粒度足以表达所有 game balance 参数。
- **deploy_mutation 模式**: FDB 仅提交小型 manifest → object store 异步上传大 blob。fdb_version_counter 提供严格全序，保证 replay 重放时 deploy events 的确定性顺序。
- **Worker pool 256+1000**: 合理的安全边际——256 覆盖 500 target players 的典型并发，1000 hard cap 带编译期保护防止配置错误导致的资源耗尽。
