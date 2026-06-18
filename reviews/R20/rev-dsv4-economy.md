# R20 经济评审报告 — DSV4

**评审员**: rev-dsv4-economy (Economy Reviewer)
**日期**: 2026-06-18
**权威源**: economy.idl.yaml, game_api.idl.yaml, api-registry.md
**上级任务**: R19 Blocker 闭合验证 + 用户裁决确认

---

## 总体 Verdict: CONDITIONAL_APPROVE

全 6 项 R19 Blocker + 4 项用户裁决均已闭合。发现 1 个经济域 GAP：存储税 tier 定义在 economy.idl.yaml（绝对阈值 10K/100K/1M）与设计文档（百分比 30%/60%/85%/100%）之间存在歧义，需统一到 IDL 权威定义。

---

## 逐项判定

| ID | 项目 | 状态 | 证据 |
|----|------|------|------|
| B19-1 | RejectionReason canonical 传播 | ✅ CLOSED | game_api.idl.yaml §2: 35 canonical codes + debug_detail (512B max) + detail_level enum (competitive/practice/training)。api-registry.md §2: 完整 47 code (35 game_api + 12 auth_api, namespace offset 1000+) 。命名规范 (InsufficientResource/ ObjectNotFound/CooldownActive/NotVisibleOrNotFound) 在 IDL 与 registry 一致。 |
| B19-2 | MCP/Auth tool namespace 收敛 | ✅ CLOSED | api-registry.md §3.2 (game_api Auth 2 tools: swarm_auth_login/refresh) + §3.4 (auth_api 11 tools: 5 lifecycle + 6 cert/device)。auth_api 工具使用独立 replay_class (non_replayable/admin_critical/idempotent_mutation) 与独立 rate_limit_key。api-registry.md 明确标注 game_api 版为简化形态，auth_api 版为完整 schema。 |
| B19-3 | deploy replay_class → deploy_mutation | ✅ CLOSED | game_api.idl.yaml L881: `swarm_deploy.replay_class: deploy_mutation`。game_api.idl.yaml §10 Deploy 完整描述 deploy_mutation 机制 + fdb_version_counter。api-registry.md §11 确认 deploy_mutation 架构。 |
| B19-4 | IDL f64→fixed-point (全量) | ✅ CLOSED | game_api.idl.yaml type_registry 声明 7 种定点类型 (ResourceRate_i64, ProgressBps_i64, BasisPoints, EfficiencyBps, ConfidenceBps, milli_distance, micro_cost)。economy.idl.yaml 补充 MilliUnits。api-registry.md §0 注册 8 种定点类型。两 IDL 中 `f64` 仅出现在注释（"prohibited/was replaced"），无实际 f64 字段。 |
| B19-5 | worker pool 256 default + 1000 hard_cap | ✅ CLOSED | game_api.idl.yaml §5 limits → hardware_baseline: `worker_pool_max: 256` (runtime default), `worker_pool_hard_cap: 1000` (compile-time)。api-registry.md §5.5: "Worker pool max = 256 (world.toml 可调), Worker pool hard cap = 1000 (编译期硬上限)"。一致。 |
| B19-6 | 经济机器源 (economy.idl.yaml) | ✅ CLOSED | economy.idl.yaml 独立存在，含 3 种定点类型、7 个 ResourceOperation、canonical formulas（recycle_refund/storage_tax/build_cost_discounted/spawn_cost_total）、economy-specific limits（§4）。api-registry.md 头声明 economy.idl.yaml 为三大 IDL 源之一，§10 完整引用。 |
| U1/A | auth_api.idl.yaml 独立 | ✅ CLOSED | api-registry.md 声明三源：game_api + auth_api + economy。auth_api 拥有独立版本 (0.1.0)、独立 RejectionReason namespace (1000+)、独立 MCP 工具集 (11 tools)、独立限制 (§5.8)。不以 game_api 子集形式存在。 |
| U2/B | economy.idl.yaml 独立 | ✅ CLOSED | economy.idl.yaml 为独立文件，独立 api_version (0.1.0)，独立类型系统 (BasisPoints/ResourceRate_i64/MilliUnits)，独立操作定义。api-registry.md 以等同地位引用三个 IDL 源。 |
| U3/A | worker_pool default 256 + hard_cap 1000 | ✅ CLOSED | 同 B19-5。game_api.idl.yaml L1420-1422 确认。 |
| U4/A | deploy_mutation replay_class | ✅ CLOSED | 同 B19-3。swarm_deploy 使用 deploy_mutation。 |

---

## GAP

**GAP-1: 存储税 tier 定义歧义 — economy.idl.yaml vs 设计文档**

`economy.idl.yaml` §2.2 使用**绝对单位阈值**: tier 0 (0–9,999), tier 1 (10,000–99,999), tier 2 (100,000–999,999), tier 3 (1,000,000+)。`api-registry.md` §5.7/§10.2 与此一致。

但 `specs/core/08-resource-ledger.md` §2.1 使用**容量百分比阈值**: `[(30,0),(60,1),(85,5),(100,20)]`（即 30%/60%/85%/100% of capacity）。`design/gameplay.md` §8 与 `design/economy-balance-sheet.md` 均引用百分比定义。

在 capacity=1,000,000 时：IDL 的 tier 1 从 10,000 (1%) 开始，而 Resource Ledger 的 tier 1 从 300,000 (30%) 开始——差距 30 倍。建议以 `economy.idl.yaml` 为准，更新 Resource Ledger §2.1 的 `storage_tax_tiers` 为与 IDL 一致的绝对阈值，并重新计算 economy-balance-sheet.md 中所有存储税数值。

---

## 评审说明

- **B19-2**: auth_api.idl.yaml 不在本评审员授权文件列表中。验证基于 api-registry.md（从 IDL 自动生成），其中 §3.4 和 §5.8 提供了 auth_api 的完整 schema 和限制，足以证明 auth_api 的独立性和 namespace 收敛。
- **非经济域项** (B19-1 RejectionReason, B19-2 Auth namespace, B19-3 deploy_mutation, B19-4 定点类型计数, B19-5 worker_pool) 仅验证是否已闭合，不重新评审其设计合理性——按约束"不重新评审设计本身"。
- Recycle 公式在 economy.idl.yaml §2.1、economy.idl.yaml §3 (formulas)、resource-ledger.md §2.3 三方一致（10%–50% lifespan-proportional），无冲突。
