# R20 游戏设计闭合验证（GPT）

## Verdict

CONDITIONAL_APPROVE

## Strengths

- API Registry 明确由 `game_api.idl.yaml`、`auth_api.idl.yaml`、`economy.idl.yaml` 三源生成，并声明冲突时以 IDL YAML 为准。
- `deploy_mutation`、fixed-point type registry、worker pool 256/1000、economy operations 均已在权威 Registry 中收敛。
- MCP/Auth/Economy 的工具、错误码、replay_class、安全列已集中进入 Registry，AI 玩家可通过 MCP resources 学到当前 API 面。

## Concerns

| ID | 状态 | 证据 |
|---|---|---|
| B19-1 RejectionReason canonical 传播 | GAP | `specs/reference/api-registry.md:90` 声明 47 个 canonical code；但 `design/interface.md:152` 仍写「35 变体」，设计文档传播未完全闭合。 |
| B19-2 MCP/Auth tool namespace 收敛 | CLOSED | `specs/reference/api-registry.md:3` 声明 Registry 由 `auth_api.idl.yaml` 参与生成；`specs/reference/api-registry.md:332` 单列 Auth API 工具 11 个。 |
| B19-3 deploy replay_class → deploy_mutation | GAP | `specs/reference/api-registry.md:277` 将 `swarm_deploy` 标为 `deploy_mutation`；但 `design/interface.md:27` 仍标 `idempotent_mutation`。 |
| B19-4 IDL f64→fixed-point | CLOSED | `specs/reference/api-registry.md:21` 建立 Fixed-Point Type Registry；`specs/reference/api-registry.md:23` 明确 all `f64` fields replaced；`design/gameplay.md:1961` 也声明游戏引擎数值禁用 f64。 |
| B19-5 worker pool 256 default + 1000 hard_cap | CLOSED | `specs/reference/api-registry.md:519` 定义 worker pool 默认 max_pool 256；`specs/reference/api-registry.md:521` 定义 hard cap 1000。 |
| B19-6 经济机器源 | CLOSED | `specs/reference/api-registry.md:702` 起单列 Economy Operations；`specs/reference/api-registry.md:704` 标注来源为 `economy.idl.yaml`；`specs/reference/api-registry.md:706` 明确 No f64。 |
| U1/A auth_api.idl.yaml 独立 | CLOSED | `specs/reference/api-registry.md:7` 版本行单列 `auth_api 0.1.0`；`specs/reference/api-registry.md:177` 单列 Auth 层 canonical codes。 |
| U2/B economy.idl.yaml 独立 | CLOSED | `specs/reference/api-registry.md:7` 版本行单列 `economy 0.1.0`；`specs/reference/api-registry.md:534` 单列 Economy 限制。 |
| U3/A worker_pool default 256 + hard_cap 1000 | CLOSED | 同 B19-5，`specs/reference/api-registry.md:519` / `specs/reference/api-registry.md:521` 已闭合。 |
| U4/A deploy_mutation replay_class | CLOSED_WITH_PROPAGATION_GAP | 权威 Registry 已闭合：`specs/reference/api-registry.md:277` / `specs/reference/api-registry.md:750`；但 `design/interface.md:27` 仍有旧 replay_class。 |

## Missing

- 仍需把 `design/interface.md` 的 `swarm_deploy` replay_class 从 `idempotent_mutation` 改为引用 Registry 的 `deploy_mutation`。
- 仍需把 `design/interface.md` 的 RejectionReason 计数从旧「35 变体」改为引用 Registry §2，避免 AI onboarding 读到旧事实。

## Fresh Ideas

N/A — 本轮任务仅验证 R19 Blocker 与用户裁决闭合，不重新评审设计或 brainstorm。

## GAP

GAP 共 2 项，均为派生设计文档传播残留；权威 Registry/IDL 路径本身已闭合。按任务规则，结论为 CONDITIONAL_APPROVE。
