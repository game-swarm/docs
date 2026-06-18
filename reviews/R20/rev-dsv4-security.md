# R20 Security Review — DSV4

> **评审员**: rev-dsv4-security  
> **日期**: 2026-06-18  
> **范围**: R19 Blocker 传播残留 + 用户裁决闭合验证  
> **权威源**: YAML IDL (game_api + auth_api + economy)

---

## 总体 Verdict: APPROVE

全部 10 项验证通过。6 个 R19 Blocker 传播残留均已闭合，4 项用户裁决均已落实。未发现安全方向 GAP。

---

## 逐项判定

| ID | 类型 | 状态 | 证据 |
|----|------|------|------|
| **B19-1** | RejectionReason canonical 传播 | **CLOSED** | game_api.idl.yaml 定义 35 codes (indices 1-35) + auth_api.idl.yaml 12 codes (namespace 1000+, indices 1001-1012)。api-registry.md §2 完整传播全部 47 个 canonical codes。design/auth.md 使用自身的错误码描述（`challenge_expired` 等），与 wire enum 分层不同，不影响。 |
| **B19-2** | MCP/Auth tool namespace 収敛 | **CLOSED** | auth_api.idl.yaml: 5 lifecycle + 6 cert/device = 11 tools。game_api.idl.yaml: 46 tools。两者无名称冲突——auth tools 使用 `swarm_auth_*` 前缀，game tools 使用 `swarm_*`。RejectionReason 通过 namespace_offset=1000 隔离。api-registry.md §3.4 完整列出。 |
| **B19-3** | deploy replay_class → deploy_mutation | **CLOSED** | game_api.idl.yaml L881: `replay_class: deploy_mutation`。design/auth.md §5.6a (L320): `deploy_mutation` for swarm_deploy。specs/security/03-mcp-security.md L232: `deploy_mutation 模式`。api-registry.md L277: deploy_mutation。三文档一致。 |
| **B19-4** | IDL f64→fixed-point (11 fields) | **CLOSED** | api-registry.md §0 注册 8 种定点类型：ResourceRate_i64, ProgressBps_i64, BasisPoints, EfficiencyBps, ConfidenceBps, milli_distance, micro_cost, MilliUnits。全部底层为 i64/u32/u64 整数，无 f64。game_api 声明 7 类 + economy 声明 3 类（含 overlap）= 10 source declarations。residue check: `grep f64` 仅命中 "replacing f64" 注释，无活跃 f64 字段。 |
| **B19-5** | worker pool 256 default + 1000 hard_cap | **CLOSED** | game_api.idl.yaml L1420-1422: `worker_pool_max: 256`（runtime default），`worker_pool_hard_cap: 1000`（compile-time hard cap）。L1418-1419: hard_cap_players: 1000, hard_cap_behavior defined。 |
| **B19-6** | 经济机器源 (economy.idl.yaml) | **CLOSED** | economy.idl.yaml 独立存在，api_version 0.1.0。包含 7 个 ResourceOperation（RecycleRefund/StorageTax/UpkeepDeduction/PvEAward/BuildCost/SpawnCost/AlliedTransfer）+ 4 个 Formulas + 经济专属 limits。全部定点运算，无 f64。api-registry.md §0 以 economy.idl.yaml 为权威源。 |
| **U1/A** | auth_api.idl.yaml 独立 | **CLOSED** | `/specs/reference/auth_api.idl.yaml` 独立文件，api_version "0.1.0"。含 5 lifecycle + 6 cert/device tools，12 auth RejectionReason codes，8 auth trace events，独立 rate limits。 |
| **U2/B** | economy.idl.yaml 独立 | **CLOSED** | `/specs/reference/economy.idl.yaml` 独立文件，api_version "0.1.0"。含定点类型定义、7 个经济操作、4 个 canonical formulas、经济专属 limits。 |
| **U3/A** | worker_pool default 256 + hard_cap 1000 | **CLOSED** | 同 B19-5。game_api.idl.yaml L1421-1422 确认。 |
| **U4/A** | deploy_mutation replay_class | **CLOSED** | 同 B19-3。game_api.idl.yaml 确认 replay_class=deploy_mutation，fdb_version_counter 保证 replay 确定性。 |

---

## 关键变更验证

| 变更 | 文件 | 状态 |
|------|------|------|
| 新增独立 auth_api.idl.yaml | `specs/reference/auth_api.idl.yaml` | ✅ 存在，api_version 0.1.0 |
| 新增独立 economy.idl.yaml | `specs/reference/economy.idl.yaml` | ✅ 存在，api_version 0.1.0 |
| game_api f64→定点 | `game_api.idl.yaml` §type_registry | ✅ 7 fixed-point types |
| game_api worker_pool 256+1000 | `game_api.idl.yaml` L1421-1422 | ✅ |
| game_api deploy_mutation | `game_api.idl.yaml` L881 | ✅ |
| api-registry 从 3 IDL 生成 | `api-registry.md` header | ✅ 声明 3 源 |
| RejectionReason canonical | IDL → api-registry.md §2 | ✅ 47 codes |
| MCP phantom 清理 | auth_api.idl.yaml 11 tools, 无重复 | ✅ |
| MAX_PATH_LENGTH 500 | `game_api.idl.yaml` L1400 | ✅ |

---

## GAP

无安全方向 GAP。

**信息级注意 (Informational)**：
- game_api 与 auth_api 的 RejectionReason 存在同名异码：`InvalidCertificate`（game:28 vs auth:1001）、`NotAuthorized`（game:29 vs auth:1002）、`RateLimited`（game:27 vs auth:1009）。wire enum 使用整数索引，namespace offset 防止冲突；api-registry.md 已文档化此区别。实现者需注意按 layer + index 分发，不可仅按 name string 匹配。
