# R19 安全闭合验证 — rev-gpt-security

## 总体 Verdict: REQUEST_MAJOR_CHANGES

本轮不是重新评审设计，而是只验证 R18 Blocker 与用户裁决是否在允许读取的 R19 文档中闭合。结论：仍存在会影响机器权威源与安全执行语义的阻断级缺口，尤其是 `auth_api.idl.yaml` 缺失、Auth MCP 工具未进入机器源、`swarm_deploy` 的 `replay_class` 在同一权威链内自相矛盾。

## Critical

| ID | 状态 | 证据 |
|---|---|---|
| B3: MCP Tool 三套名称空间 | GAP | `design/auth.md:690-709` 定义 `swarm_register_challenge`、`swarm_submit_csr`、`swarm_renew_certificate`、`swarm_revoke_certificate`、`swarm_admin_create_password_reset` 等 Auth MCP 工具；但机器源 `game_api.idl.yaml:573-602` 仅注册 `swarm_auth_login` / `swarm_auth_refresh` 两个 Auth 工具，且任务列出的 `specs/reference/auth_api.idl.yaml` 文件不存在。安全后果：认证/恢复/吊销/管理员恢复工具没有机器可校验的 replay_class、scope、rate limit、visibility_filter、rate_limit_key。 |
| B5: 安全字段未入机器源 | GAP | `game_api.idl.yaml:429-431` 声称 MCP Tools 共 46，且 `game_api.idl.yaml:440-1228` 对已注册工具提供安全列；但 Auth 设计中的核心安全工具未进入该 IDL，`auth_api.idl.yaml` 缺失。`design/auth.md:338-348` 仅以 Markdown 表列出 5 个方法的授权矩阵，并引用 `interface.md` 为完整矩阵；这不是任务约束下可用的机器源。 |
| DA1: deploy_mutation replay_class | GAP | `design/auth.md:316-324` 明确规定 `deploy_mutation` 类由 FDB version_counter 防重放，示例为 `swarm_deploy`；`game_api.idl.yaml:836` 却把 `swarm_deploy` 标为 `idempotent_mutation`，同时 `game_api.idl.yaml:839-843` 的 notes 又说它使用 deploy_mutation pattern。生成文档中同样矛盾：`api-registry.md:218` 为 `idempotent_mutation`，`api-registry.md:225` 与 `api-registry.md:526-539` 又说 deploy_mutation。 |

## High

| ID | 状态 | 证据 |
|---|---|---|
| B1: YAML vs Markdown 双写不一致 | GAP | Game API 部分已有生成声明：`api-registry.md:1-7` 声明由 `game_api.idl.yaml` 自动生成、YAML 为准。但同一生成物仍保留 deploy replay_class 矛盾（见 DA1），且任务指定的 Auth 机器源 `auth_api.idl.yaml` 不存在，导致 Auth Markdown 与机器源无法对齐。 |
| B2: RejectionReason 未闭合 | CLOSED | `game_api.idl.yaml:231-259` 定义 35 个 canonical code、`debug_detail`、`detail_level`；`api-registry.md:69-90` 同步生成；`game_api.idl.yaml:1474-1480` / `api-registry.md:491-500` 在错误 envelope 中包含 `debug_detail`。 |
| B4: Tick/Trace/Persistence 分叉 | CLOSED | TickTrace 机器源已显式化：`game_api.idl.yaml:1397-1452` 定义 22 字段与 `terminal_state` enum；生成文档 `api-registry.md:427-469` 同步。Persistence/Deploy 也进入机器源：`game_api.idl.yaml:1526-1611` 与 `api-registry.md:526-596` 定义 deploy_mutation、fdb_version_counter、async_object_store_upload。注意：闭合不覆盖 DA1 的 replay_class 字段矛盾。 |
| B7: 容量合同不可证明 | CLOSED | `game_api.idl.yaml:1321-1392` 给出权威容量限制；`api-registry.md:360-423` 同步生成。包括 WASM 内存/CPU、simulate 上限、pathfinding budget、worker pool、fair-share admission 等，可被 CI/codegen 消费。 |

## Medium

| ID | 状态 | 证据 |
|---|---|---|
| B6: 经济单源未闭合 | N/A | 非安全主方向。可见 `game_api.idl.yaml:773-782` 有 economy 输出字段、`game_api.idl.yaml:1340-1342` 有 global_storage_capacity，但 storage tax tier 与 recycle refund 不在允许文件中形成可验证机器合同；建议由经济/设计方向复核。 |
| D1: api-registry.md 全量生成 | CLOSED | `api-registry.md:1-7` 明确声明由 `game_api.idl.yaml` 自动生成，包含 CommandAction、RejectionReason、MCP Tools、Host Functions、容量限制、TickTrace、Deploy/Persistence 等章节。 |
| D2: RejectionReason canonical + debug_detail | CLOSED | 同 B2。canonical wire enum 保持 35 code，额外上下文放 `debug_detail`；默认 `detail_level=competitive` 有信息泄露控制。 |
| D5: blob 异步上传 | CLOSED | `game_api.idl.yaml:1570-1611` 定义 `async_object_store_upload`，ack immediate、poll status、failure retry、FDB manifest 小记录；`api-registry.md:561-596` 同步生成。 |
| DA3: worker pool 256 default | CLOSED | `game_api.idl.yaml:1375-1377` 定义 `worker_pool_size: min(max_pool, active_players)`、`worker_pool_max: 256`；`api-registry.md:411-415` 同步生成。 |

## Informational / N/A

| ID | 状态 | 证据 |
|---|---|---|
| D3: Recycle refund lifespan 10-50% | N/A | 非安全主方向；允许文件中仅见 `Recycle` action (`game_api.idl.yaml:120-127`) 和账号删除资产处置 recycle 默认 50% (`design/auth.md:1137-1140`)，未见 10-50% lifespan 公式的机器源。建议 gameplay/economy 方向验证。 |
| D4: Storage tax tiered 0/1/5/20bp | N/A | 非安全主方向；允许文件中仅见 `storage_tax` 输出字段仍为 `f64` (`game_api.idl.yaml:778-781`)，未见 tiered 0/1/5/20bp 机器枚举。建议 economy 方向验证。 |
| D6: soft_launch 3阶段 PvP | N/A | 非安全主方向；允许文件中未见 soft_launch / PvP phase 合同。建议产品/模式方向验证。 |
| DA2: f64→定点 | N/A | 非安全主方向；但允许文件中仍可见多个 `f64` API 字段：`income_rate` (`game_api.idl.yaml:483-484`)、path `distance/cost` (`game_api.idl.yaml:674-676`)、economy (`game_api.idl.yaml:778-781`)、efficiency (`game_api.idl.yaml:793-795`)、resource `base_value` (`game_api.idl.yaml:1167-1169`)。建议 determinism/IDL 方向作为潜在 GAP 复核。 |

## GAP 详情

1. `/tmp/swarm-review-R19/specs/reference/auth_api.idl.yaml` 缺失
   - 任务明确把该文件列为允许且应读取的权威 IDL；实际读取结果为 file not found，仅发现相似文件 `game_api.idl.yaml`。
   - 这使 Auth domain 的 MCP 工具、错误码、证书/CSR schema、admin recovery schema 没有独立机器源。

2. Auth 工具集未闭合进机器源
   - Markdown Auth 设计列出了完整认证生命周期工具，但 `game_api.idl.yaml` 只包含 `swarm_auth_login` / `swarm_auth_refresh`。
   - `swarm_submit_csr`、`swarm_register_challenge`、`swarm_renew_certificate`、`swarm_revoke_certificate`、`swarm_admin_create_password_reset` 等安全关键工具无法由 IDL 驱动 codegen / CI 验证。

3. `swarm_deploy` replay_class 自相矛盾
   - 机器字段 `replay_class: idempotent_mutation` 与同一条工具 notes、Deploy 章节、Auth replay class 设计均冲突。
   - 安全上这会让实现者选择 Dragonfly nonce/time-window 语义，而不是 FDB version_counter 严格防重放语义，属于可被重放/乱序语义误实现的高风险缺口。

## CrossCheck

1. 请 IDL/架构方向确认是否应新增并生成 `auth_api.idl.yaml`，或把 Auth 全量工具合并进 `game_api.idl.yaml`；两者必须二选一成为机器权威源。
2. 请 API/Replay 方向修正 `swarm_deploy.replay_class` 为 `deploy_mutation`，并增加 CI 规则防止工具表字段与章节说明矛盾。
3. 请 Economy/Determinism 方向复核 D3/D4/DA2：允许文件中仍存在 `f64` 与缺失的 storage-tax/recycle-refund 机器合同，可能不是安全主责但会影响 replay/确定性闭合。
