# R20 Economy Review — GPT

Verdict: CONDITIONAL_APPROVE

Strengths
- B19-4/B19-6 的核心机器闭合已完成：`economy.idl.yaml` 独立存在，声明 fixed-point only、BasisPoints/ResourceRate_i64/MilliUnits，并给出 7 个 ResourceOperation。
- `game_api.idl.yaml` 已将经济可见 API 输出改为定点类型，并将 worker_pool default 256 + hard_cap 1000、deploy_mutation replay_class 写入 IDL 权威源。
- `api-registry.md` 明确由 game_api/auth_api/economy 三个 IDL 源生成，且 Economy Operations、fixed-point registry、容量限制均能从 IDL 派生。

Concerns
- E1: Resource Ledger 仍在正文中自称“所有费率、公式、参数的唯一定义源”，但任务要求以 IDL YAML 为权威源；这与新增独立 `economy.idl.yaml` 的用户裁决 U2/B 形成残留冲突。
- E2: 经济派生文档仍存在与 `economy.idl.yaml` 不一致的经济口径：Resource Ledger 记载 allied_transfer_fee=200bp/cooldown/daily cap，而 `economy.idl.yaml` 的 AlliedTransfer 为 tax_exempt=true、cooldown=null；StorageTax 在 Resource Ledger 使用容量百分比累进公式，而 `economy.idl.yaml` 使用 stored_total 绝对阈值 10K/100K/1M。

## 逐项判定

| ID | 状态 | 证据 |
|---|---|---|
| B19-1 | CLOSED | `game_api.idl.yaml` §2 将 RejectionReason 固定为 35 canonical codes，并规定 `debug_detail` 不进入 wire enum；`api-registry.md` §2 传播 canonical/debug_detail 规则。 |
| B19-2 | N/A | auth_api.idl.yaml 不在本任务允许读取清单内；但 `api-registry.md` 明确由 `auth_api.idl.yaml` 参与生成，并列出独立 Auth API 工具与 namespace offset 1000+。非经济方向不作实质复审。 |
| B19-3 | CLOSED | `game_api.idl.yaml` 中 `swarm_deploy.replay_class: deploy_mutation`，deploy 章节声明 `mechanism: deploy_mutation` 与 `fdb_version_counter` replay contract；`api-registry.md` §11 同步传播。 |
| B19-4 | CLOSED | `game_api.idl.yaml` type_registry 明确 f64 已替换为 ResourceRate_i64/ProgressBps_i64/BasisPoints/EfficiencyBps/ConfidenceBps/milli_distance/micro_cost；相关 economy API 输出使用 ResourceRate_i64/BasisPoints/EfficiencyBps/ConfidenceBps。 |
| B19-5 | CLOSED | `game_api.idl.yaml` limits.hardware_baseline 声明 `worker_pool_max: 256` 与 `worker_pool_hard_cap: 1000`；`api-registry.md` §5.5 同步为 Worker pool max 256、hard cap 1000。 |
| B19-6 | CLOSED | `economy.idl.yaml` 独立定义经济机器源，包含 fixed-point types、RecycleRefund/StorageTax/UpkeepDeduction/PvEAward/BuildCost/SpawnCost/AlliedTransfer、canonical formulas 与 economy-specific limits。 |
| U1/A | N/A | auth_api.idl.yaml 不在允许读取清单内；`api-registry.md` 顶部列出 `auth_api.idl.yaml` 为独立 IDL 源。非经济方向不作实质复审。 |
| U2/B | CLOSED | `economy.idl.yaml` 独立存在，api_version 0.1.0；`api-registry.md` 顶部声明从 game_api/auth_api/economy 三源生成。 |
| U3/A | CLOSED | `game_api.idl.yaml` worker_pool_max=256、worker_pool_hard_cap=1000；registry 同步传播。 |
| U4/A | CLOSED | `game_api.idl.yaml` 和 `api-registry.md` 均使用 deploy_mutation，而非 deploy replay_class 残留。 |

## Economy Balance Issues

- IDL 机器源已能支持固定点经济闭合，但 `Resource Ledger` 与 `economy.idl.yaml` 对 StorageTax/AlliedTransfer 的参数仍不一致，后续实现若从 Markdown 与 YAML 分别取值会产生分叉。
- `economy-balance-sheet.md` 引用 Resource Ledger 为公式来源，间接继承上述冲突；这不是 R20 blocker 未闭合，但属于经济派生文档的一处残留 GAP。

## Resource Loop Gaps

- GAP: 核心 R19 blocker 与用户裁决在 IDL 层已闭合；经济方向剩余 GAP 是派生文档未完全降级为引用 IDL，且存在 StorageTax/AlliedTransfer 口径冲突。
- 建议下一轮只做派生文档收敛：将 Resource Ledger/Economy Balance Sheet 的“唯一权威源”措辞改为引用 `economy.idl.yaml`，并删除或同步冲突参数。
