# R20 API/DX Review (GPT)

## Verdict

CONDITIONAL_APPROVE

## Strengths

- IDL-first 主链路明显收敛：`api-registry.md` 声明由 `game_api.idl.yaml`、`auth_api.idl.yaml`、`economy.idl.yaml` 生成，且冲突时以 IDL YAML 为准。
- `game_api.idl.yaml` 已把核心 DX 决策机器化：fixed-point type registry、35 个 game canonical RejectionReason、`deploy_mutation`、worker pool default 256 / hard cap 1000 都有明确字段。
- `auth_api.idl.yaml` 独立后，认证生命周期、证书/设备工具、auth-specific RejectionReason 与安全列比 R19 更可 codegen。
- `api-registry.md` 对三源 IDL 的聚合可读性较好，适合作为 SDK/文档入口。

## Concerns

### X1 — 派生文档仍残留旧 CommandAction/CustomAction 口径

`commands.md` 顶部同时说“19 指令”，但正文仍写“以下 15 种指令”“第 16 个变体 CommandAction::Custom(type)”和“8 种特殊攻击”；这与 `game_api.idl.yaml` 中 19 个 core variants（含 Hack/Drain/Overload/Debilitate/Disrupt/Fortify 6 个 special_attack）不一致。对 SDK 新用户来说，这会直接造成 action enum 与示例不一致。

### X2 — MCP/Auth namespace 在 `design/interface.md` 未闭合

`auth_api.idl.yaml` 已收敛到 `swarm_auth_login`、`swarm_auth_refresh`、`swarm_auth_logout/check/revoke`、`swarm_auth_cert_*`、`swarm_auth_device_*` 等命名；但 `design/interface.md` 仍列出 `swarm_get_server_trust`、`swarm_register_challenge`、`swarm_submit_csr`、`swarm_token_refresh`、`swarm_change_password`、`swarm_federated_login`、tournament 工具等不在当前 IDL/registry 活跃集中的 phantom tools。该文件还把 `swarm_deploy` 标为 `idempotent_mutation`，而 IDL/registry 的裁决是 `deploy_mutation`。

## Missing

- `economy.idl.yaml` 是 R20 验证清单的一项，但本任务“只读以下文件”白名单未包含该文件；我只能通过 `api-registry.md` 中 economy 来源段验证其聚合结果，不能直接验证 IDL 源文件本身。
- 若要全 CLOSED，需要至少把 `commands.md`、`host-functions.md`、`design/interface.md` 的旧示例/概念签名/phantom tools 与 IDL 重新同步。

## API Consistency Issues

| ID | 状态 | 证据 |
|---|---|---|
| B19-1 RejectionReason canonical 传播 | GAP | `game_api.idl.yaml` 和 `api-registry.md` 已闭合 35 game canonical + debug_detail，但 `design/interface.md` 的 SwarmError 示例仍使用 `code: -32000` + `data.swarm_error/details/retry_allowed/idempotency_key`，与 registry 中 `error.code: RejectionReason (string)`、`data.debug_detail` 不一致。 |
| B19-2 MCP/Auth tool namespace 收敛 | GAP | `auth_api.idl.yaml` 已独立定义 11 个 auth tools；`api-registry.md` 也列出完整 schema。但 `design/interface.md` 仍保留大量非 IDL 工具名，如 `swarm_get_schema`、`swarm_get_docs`、`swarm_submit_csr`、`swarm_token_refresh`、`swarm_change_password`、`swarm_federated_login` 等。 |
| B19-3 deploy replay_class → deploy_mutation | GAP | `game_api.idl.yaml` 的 `swarm_deploy.replay_class` 为 `deploy_mutation`，`api-registry.md` deploy 表也为 `deploy_mutation`；但 `design/interface.md` MCP 分类表仍把 `swarm_deploy` 写成 `idempotent_mutation`。 |
| B19-4 IDL f64→fixed-point (11 fields) | CLOSED | `game_api.idl.yaml` type registry 明确 fixed-point types；`api-registry.md` §0 声明所有 `f64` fields 已替换为 fixed-point integer representations，并在 economy 聚合段说明 amounts/rates 无 f64。 |
| B19-5 worker pool 256 default + 1000 hard_cap | CLOSED | `game_api.idl.yaml` limits.hardware_baseline 中 `worker_pool_max: 256`、`worker_pool_hard_cap: 1000`；`api-registry.md` §5.5 同步为 Worker pool max 256、hard cap 1000。 |
| B19-6 经济机器源 (economy.idl.yaml) | N/A | `api-registry.md` 声明由 `economy.idl.yaml` 生成并包含 Economy Operations/limits/fixed-point；但 `economy.idl.yaml` 不在本任务允许读取列表中，不能直接验证源文件。 |
| U1/A auth_api.idl.yaml 独立 | CLOSED | `/tmp/swarm-review-R20/specs/reference/auth_api.idl.yaml` 存在且为独立 Auth API IDL，包含 lifecycle tools、auth MCP tools、auth RejectionReason、trace events、rate limits、token envelope。 |
| U2/B economy.idl.yaml 独立 | N/A | `api-registry.md` 多处引用 economy source，并列出 economy version/operations/limits；但白名单不允许读取 economy IDL 源，不能判定源文件本身。 |
| U3/A worker_pool default 256 + hard_cap 1000 | CLOSED | 同 B19-5，IDL 与 registry 均闭合。 |
| U4/A deploy_mutation replay_class | GAP | IDL/registry 已闭合；`design/interface.md` 仍保留 `idempotent_mutation`，对 MCP/SDK 读者构成传播残留。 |

## GAP

剩余 GAP 集中在派生文档传播残留，而不是 IDL 主源缺失。按 R20 约束，GAP ≤2 类且 IDL 权威源方向正确，因此给出 CONDITIONAL_APPROVE；实现前应重生成或手工同步 `commands.md`、`host-functions.md`、`design/interface.md`。