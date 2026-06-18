# R20 架构闭合验证 — GPT

## Verdict

APPROVE

R20 对 R19 Blocker 与用户裁决的关键传播项已闭合。以允许读取的 IDL YAML 与 api-registry 派生文档为证据，架构层面没有发现需要阻断 Phase 进入的残留分叉。

## Strengths

- IDL-first 路线明显收敛：api-registry 明确由 game_api.idl.yaml、auth_api.idl.yaml、economy.idl.yaml 三个 IDL 源生成，降低 Markdown 手写漂移风险。
- RejectionReason 采用 canonical code + debug_detail 的模式，避免继续扩张 wire enum，同时保留训练/调试可用性。
- deploy 从 replay_class 残留收敛到 deploy_mutation，并带 fdb_version_counter，符合 replay 全序要求。
- fixed-point 类型注册覆盖 game/economy 的关键数值面，消除 f64 跨平台确定性风险。
- worker_pool default 256 / hard_cap 1000 在 IDL、registry、engine 性能合同之间一致。

## Concerns

| ID | 状态 | 证据 |
|---|---|---|
| B19-1 RejectionReason canonical 传播 | CLOSED | api-registry.md §2 声明 47 个 canonical code，debug_detail 非 wire enum；game_api.idl.yaml §2 定义 35 个 game canonical code 与 debug_detail/detail_level。 |
| B19-2 MCP/Auth tool namespace 收敛 | CLOSED | api-registry.md 声明由 auth_api.idl.yaml 生成，Auth API 工具有独立 §3.4，含 5 lifecycle + 6 cert/device tools；安全列包含 required_scope/subject_source/replay_class/visibility_filter/rate_limit_key。 |
| B19-3 deploy replay_class → deploy_mutation | CLOSED | game_api.idl.yaml 中 swarm_deploy replay_class 为 deploy_mutation，deploy.mechanism 为 deploy_mutation；api-registry.md §11 同步说明 deploy_mutation + fdb_version_counter。 |
| B19-4 IDL f64→fixed-point | CLOSED | game_api.idl.yaml type_registry 注册 ResourceRate_i64、ProgressBps_i64、BasisPoints、EfficiencyBps、ConfidenceBps、milli_distance、micro_cost；economy.idl.yaml 明确 fixed-point only / No f64。搜索结果仅剩注释说明替换 f64，无字段使用 f64。 |
| B19-5 worker pool 256 default + 1000 hard_cap | CLOSED | game_api.idl.yaml limits.hardware_baseline: worker_pool_max 256、worker_pool_hard_cap 1000；api-registry.md §5.5 与 engine.md §3.4.2 保持同值。 |
| B19-6 经济机器源 | CLOSED | economy.idl.yaml 独立定义 7 个 ResourceOperation、fixed-point 类型、canonical formulas 与 economy limits；api-registry.md §10 声明来源为 economy.idl.yaml。 |
| U1/A auth_api.idl.yaml 独立 | CLOSED | api-registry.md 顶部声明 auth_api.idl.yaml 为独立 IDL 源，§3.4 单列 Auth API 工具，§5.8 单列 Auth 限制，§6.2 单列 Auth Tick Trace Events。注：任务允许清单未包含 auth_api.idl.yaml 本体，本项按派生 registry 证据判定。 |
| U2/B economy.idl.yaml 独立 | CLOSED | economy.idl.yaml 为独立 Economy IDL，api_version 0.1.0，且 api-registry.md 将 economy 作为第三 IDL 源生成。 |
| U3/A worker_pool default 256 + hard_cap 1000 | CLOSED | 同 B19-5。 |
| U4/A deploy_mutation replay_class | CLOSED | 同 B19-3。 |

## Missing

允许读取清单未包含 auth_api.idl.yaml 本体，因此 auth 独立性的验证依赖 api-registry.md 的派生声明与表格，而非源文件直读。未发现需要作为 blocker 的架构缺口。

## Phase Ordering

可以进入下一阶段；当前 R20 更像是权威源传播收敛后的闭合态，而不是仍需继续设计辩论的状态。

## GAP

GAP: auth_api.idl.yaml 本体不在本次允许读取清单内，无法直接核验源文件内容。该限制不影响 APPROVE，因为 api-registry 已声明其从 auth_api 独立源生成并列出 auth 专属工具、限制与事件。
