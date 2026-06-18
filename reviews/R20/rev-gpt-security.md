# R20 安全闭合验证（GPT）

Verdict: APPROVE

## 逐项判定

| ID | 状态 | 证据 |
|---|---|---|
| B19-1 | CLOSED | `api-registry.md` 明确声明所有指令拒绝原因注册为 47 个 canonical code（35 game_api + 12 auth_api），`debug_detail` 作为非 canonical 上下文字段；`game_api.idl.yaml` 中 `rejection_reason.total_canonical_codes: 35` 且 `debug_detail.max_length: 512`、`detail_level.default: competitive`；`auth_api.idl.yaml` 中 auth 层 `total_canonical_codes: 12`、`namespace_offset: 1000`。 |
| B19-2 | CLOSED | `auth_api.idl.yaml` 独立定义 5 个 lifecycle tools 与 6 个 cert/device tools；每个工具包含 `required_scope`、`subject_source`、`replay_class`、`visibility_filter`、`rate_limit_key` 安全列。`03-mcp-security.md` 明确认证工具权威定义见 `auth_api.idl.yaml`，授权以 API Registry capability profiles 为准，不在安全文档重复声明。 |
| B19-3 | CLOSED | `game_api.idl.yaml` 中 `swarm_deploy.replay_class: deploy_mutation`，并在 deploy 节声明 `mechanism: deploy_mutation`、`fdb_version_counter` 原子递增和 replay 按 counter 升序重放；`api-registry.md` Deploy 表同步显示 `swarm_deploy` 为 `deploy_mutation`。 |
| B19-4 | CLOSED | `game_api.idl.yaml` Type Registry 声明所有 `f64` 已替换为 fixed-point integer representations，并定义 `ResourceRate_i64`、`ProgressBps_i64`、`BasisPoints`、`EfficiencyBps`、`ConfidenceBps`、`milli_distance`、`micro_cost`；对应输出字段已使用这些定点类型。`api-registry.md` 同步声明 all `f64` fields replaced。 |
| B19-5 | CLOSED | `game_api.idl.yaml` hardware baseline 中 `worker_pool_max: 256`、`worker_pool_hard_cap: 1000`；`api-registry.md` §5.5 同步为 Worker pool max 256、hard cap 1000，并定义超过 hard cap 进入 degraded/admission gating。 |
| B19-6 | CLOSED | `api-registry.md` 声明由 `economy.idl.yaml` 生成，包含 Economy Operations，且所有 amounts 使用整数、rates 使用 `BasisPoints`、No f64；注册 7 个经济操作与 Economy 限制。注：任务白名单未授权直接读取 `economy.idl.yaml`，本项按允许文件中的 registry 派生证据核验。 |
| U1/A | CLOSED | `auth_api.idl.yaml` 作为独立文件存在并提供 auth subsystem 的机器可读单一事实源；`api-registry.md` 权威源列表包含 `auth_api.idl.yaml`。 |
| U2/B | CLOSED | `api-registry.md` 权威源列表包含 `economy.idl.yaml`，并标明 Economy Operations 来源为 `economy.idl.yaml`；未直接读取该 YAML 是遵守任务只读白名单。 |
| U3/A | CLOSED | `game_api.idl.yaml` 与 `api-registry.md` 均闭合为 worker pool 默认/运行时 max 256、编译期 hard cap 1000。 |
| U4/A | CLOSED | `swarm_deploy` 在 `game_api.idl.yaml` 与 `api-registry.md` 均标注为 `deploy_mutation`，且 replay 合约依赖 `fdb_version_counter` 严格全序。 |

## GAP

无阻断 GAP。唯一限制是任务白名单未包含 `economy.idl.yaml` 本体，因此 B19-6/U2 仅能基于允许读取的 `api-registry.md` 派生内容完成闭合验证。
