# R20 API/DX Closure Review — DSV4

**Reviewer**: rev-dsv4-apidx (API/DX — 类型系统 / 错误处理 / 开发者工效)
**Date**: 2026-06-18
**Authoritative Source**: game_api.idl.yaml, auth_api.idl.yaml (IDL YAML)

---

## 1. Verdict: CONDITIONAL_APPROVE

1 GAP found (B19-3 传播残留: interface.md `swarm_deploy` replay_class 仍为 `idempotent_mutation`，IDL 权威源已更正为 `deploy_mutation`)。其余 5 Blocker + 4 User Decisions 均已闭合。建议在合并前修复此残留后 APPROVE。

---

## 2. 逐项判定

### R19 Blockers

| ID | 状态 | 证据 |
|----|------|------|
| B19-1 | CLOSED | commands.md 不再自声明 RejectionReason 列表，统一引用 api-registry.md §2（35 game_api + 12 auth_api = 47 canonical codes）。旧非 canonical 码（NotMovable/Fatigued/SourceEmpty 等）已明确标记为已合并/降级至 debug_detail（commands.md L226）。设计文档无残留声明。 |
| B19-2 | CLOSED | auth_api.idl.yaml 独立存在，定义 5 lifecycle + 6 cert/device = 11 auth tools，含独立 RejectionReason namespace (1001–1012)。game_api.idl.yaml Auth category 仅含 2 个简化版工具（swarm_auth_login, swarm_auth_refresh），api-registry.md §3.2 明确标注 auth_api 版本含完整 schema。工具命名空间收敛正确。 |
| B19-3 | **GAP** | IDL 权威源 (game_api.idl.yaml L881): `swarm_deploy.replay_class: deploy_mutation` ✅。api-registry.md §3.2 Deploy 表: `Replay Class: deploy_mutation` ✅。**interface.md §4.1 表 (L27)**: `swarm_deploy` 的 replay_class 列仍为 `idempotent_mutation` ❌ — 传播残留。 |
| B19-4 | CLOSED | game_api.idl.yaml 定义 7 种定点类型 (ResourceRate_i64, ProgressBps_i64, BasisPoints, EfficiencyBps, ConfidenceBps, milli_distance, micro_cost)；economy 新增 MilliUnits。api-registry.md §0 Fixed-Point Type Registry 列出 8 种类型。IDL 全文无 f64 引用，所有金额/比率/距离字段均使用定点整数。 |
| B19-5 | CLOSED | game_api.idl.yaml L1421: `worker_pool_max: 256` (runtime default)。L1422: `worker_pool_hard_cap: 1000` (compile-time hard cap)。api-registry.md §5.5: 一致。 |
| B19-6 | VERIFIED BY REFERENCE | economy.idl.yaml 不在本次允许读取的文件列表中。api-registry.md 头部声明「由以下 IDL 源自动生成：game_api.idl.yaml, auth_api.idl.yaml, **economy.idl.yaml**」。§5.7/§10.2/§10.3 均标注 `来源 IDL: economy`。api-registry.md 是 economy.idl.yaml 的编译产物，其内容（7 经济操作、4 公式、分层税率表）证实 economy.idl.yaml 作为独立机器源存在。直接文件验证受限于任务约束。 |

### User Decisions

| ID | 状态 | 证据 |
|----|------|------|
| U1/A | CLOSED | auth_api.idl.yaml 作为独立文件存在，api_version "0.1.0"，独立 namespace，11 tools，12 RejectionReason codes (1001-1012)，8 trace events。api-registry.md 三源生成命令确认其独立性。 |
| U2/B | VERIFIED BY REFERENCE | economy.idl.yaml 在 api-registry.md 头部声明为三大 IDL 源之一，其内容（MilliUnits 定点类型、7 economic operations、4 canonical formulas）通过 api-registry.md 间接验证。直接文件访问受约束。 |
| U3/A | CLOSED | game_api.idl.yaml L1421–1422: `worker_pool_max: 256` + `worker_pool_hard_cap: 1000`。api-registry.md §5.5: `Worker pool max: 256` + `Worker pool hard cap: 1000`。 |
| U4/A | CLOSED | game_api.idl.yaml L881: `swarm_deploy.replay_class: deploy_mutation`。api-registry.md §3.2: `Replay Class: deploy_mutation`。§11 完整 deploy_mutation 机制文档。 |

---

## 3. GAP

1. **B19-3 传播残留**: `interface.md` §4.1 表中 `swarm_deploy` 的 replay_class 仍为 `idempotent_mutation`，需更新为 `deploy_mutation` 以与 game_api.idl.yaml (L881) 和 api-registry.md (§3.2 Deploy) 一致。修改位置: interface.md L27，将 `idempotent_mutation` → `deploy_mutation`。

---

## 4. Type Gaps

无。IDL 类型系统闭合：
- 7 game_api + 1 economy 定点类型完全替代 f64
- RejectionReason 47 canonical codes (35 game_api + 12 auth_api) 覆盖 Pipeline/Validation/MCP/Runtime/Auth 五层
- CommandAction 19 variants (11 core + 2 global + 6 special) + 2 custom
- Host Functions 5 个，均有 ABI 签名、预算、fuel 成本、错误优先级
- MCP Tools 46 game_api + 11 auth_api = 57 total，均有 5 security columns

## 5. Error Handling Coverage

完整。错误处理路径覆盖：
- Pipeline 层: InvalidJson, SchemaViolation (2 codes)
- Validation 层: 26 codes (ObjectNotFound → TransferInProgress)
- MCP 层: RateLimited, InvalidCertificate, NotAuthorized (3 codes)
- Runtime 层: 6 codes (FuelExhausted → InternalError)
- Auth 层: 12 codes, namespace 1000+ (InvalidCertificate → InternalAuthError)
- ABI Error Priority: 9 级优先级枚举，确定性错误报告
- SwarmError JSON-RPC Envelope: 统一格式，含 debug_detail (512 bytes)
- detail_level: competitive/practice/training 三级控制
