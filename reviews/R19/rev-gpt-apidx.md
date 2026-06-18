# R19 API/DX/IDL 闭合验证（GPT）

## Verdict

REQUEST_MAJOR_CHANGES

理由：R19 的 IDL-first 主干有明显进展，`game_api.idl.yaml` 与生成版 `api-registry.md` 已覆盖多数 R18 决议；但允许阅读范围内仍存在多处派生文档与 IDL/API Registry 冲突，且至少 B1/B2/B3/B6/B7 未闭合。按任务规则，存在 consensus blocker 级别 GAP，不能 APPROVE / CONDITIONAL_APPROVE。

## Strengths

- `game_api.idl.yaml` 明确声明为机器可读单一事实源，`api-registry.md` 也标注由 YAML 自动生成，D1 主方向正确。
- RejectionReason 在 IDL/API Registry 中已收敛为 35 个 canonical code，并加入 `debug_detail` 与 `detail_level`。
- MCP active tool count 在 IDL/API Registry 中收敛为 46，且每个工具具备 `required_scope` / `subject_source` / `replay_class` / `visibility_filter` / `rate_limit_key` 等安全列。
- deploy/persistence 主线已进入机器源：`deploy_mutation`、`fdb_version_counter`、`async_object_store_upload` 均在 IDL 与 API Registry 中出现。
- TickTrace envelope 已在 IDL/API Registry 中用 `terminal_state` 替代旧 `wasm_status`，并包含 replay 所需 hash/version 字段。

## 逐项判定表

| ID | 状态 | 证据 |
|---|---|---|
| B1: YAML vs Markdown 双写不一致 | GAP | `game_api.idl.yaml` 声明 YAML 为 canonical，`api-registry.md` 标注生成；但 `mcp-tools.md` 仍列 `swarm_rollback`/`swarm_list_modules`/大量旧 auth tools，和 registry §3 的 46 active tools 不一致；`commands.md` 仍写“以下 15 种指令”“第16个 Custom”，同时 registry/IDL 是 19 core variants；`host-functions.md` 的签名与 IDL ABI 签名不一致；`design/interface.md` 仍有旧工具与旧错误 envelope。 |
| B2: RejectionReason 未闭合 | GAP | IDL/API Registry 已有 35 canonical code + `debug_detail`；但 `commands.md` 的拒绝原因表仍列 `NotMovable`、`Fatigued`、`MissingBodyPart`、`TileBlocked`、`SourceEmpty` 等非 canonical code；`02-command-validation.md` 也把这些作为失败码使用。这违反“详细上下文进入 debug_detail，不新增 enum variant”。 |
| B3: MCP Tool 三套名称空间 | GAP | IDL/API Registry active list 是 46 tools，并将 `swarm_list_market_orders` 放入 RFC；但 `mcp-tools.md` 和 `design/interface.md` 仍维护旧分类/旧工具名，如 `swarm_get_objects_in_range`、`swarm_rollback`、`swarm_list_modules`、`swarm_get_docs`、`swarm_get_schema`、`swarm_explain_last_tick` 等，未与 registry 工具目录闭合。 |
| B4: Tick/Trace/Persistence 分叉 | CLOSED | IDL 中 `tick_trace_envelope` 含 22 字段与 `terminal_state` enum，`persistence.async_object_store_upload` 与 deploy flow 均进入机器源；API Registry §6/§10/§11 同步展示。仍有派生文档陈旧问题，但已由 B1 记录。 |
| B5: 安全字段未入机器源 | CLOSED | IDL `mcp_tools.tools` 对 active tools 均包含 `required_scope`、`subject_source`、`replay_class`、`visibility_filter`、`rate_limit_key`；并补充 WebSocket security。 |
| B6: 经济单源未闭合 | GAP | `Recycle` refund lifespan 公式仅在 `02-command-validation.md` 中出现，未进入 IDL 的 machine-readable economy/command contract；`commands.md` 仍写 Recycle 固定退还 50%。`storage_tax` 只作为输出字段出现，未找到 0/1/5/20bp tier 规则的机器源。 |
| B7: 容量合同不可证明 | GAP | IDL 有 `limits`，但派生/核心文档仍冲突：IDL/API Registry 为 `per_player_drone_cap: 500`，`02-command-validation.md` §6 写 `MAX_DRONES_PER_PLAYER = 50`；tick 输出 schema 上方写 256KB，批级校验又写整批 1MB；host budget 在 IDL 为 `1,000/tick/player`，`host-functions.md` 写 `1000 次/tick` 且超预算返回 -1，与 IDL ABI error priority 的 `ERR_BUDGET_EXHAUSTED=-4` 不一致。 |
| D1: api-registry.md 全量生成 | CLOSED | `api-registry.md` 顶部声明“由 game_api.idl.yaml 自动生成，冲突时以 YAML 为准”，并覆盖 CommandAction/RejectionReason/MCP/Host/Limits/TickTrace/Deploy/Persistence。 |
| D2: RejectionReason canonical+debug_detail | GAP | IDL/API Registry 已实现；但 `commands.md` 与 `02-command-validation.md` 仍使用非 canonical rejection names 作为失败码，未完成全链路闭合。 |
| D3: Recycle refund lifespan 10-50% | GAP | `02-command-validation.md` §3.18 有 `refund_pct = max(0.1, 0.5 × remaining/total)`；但 `commands.md` §Recycle 和 `02-command-validation.md` §10.3 仍写固定 50%，且该规则未在 IDL YAML 形成机器可读字段。 |
| D4: Storage tax tiered 0/1/5/20bp | GAP | 在允许文件中仅看到 `storage_tax` 字段，未找到 tiered `0/1/5/20bp` 规则、阈值或机器可读 schema。 |
| D5: blob 异步上传 | CLOSED | IDL `persistence.async_object_store_upload` 明确 fire-and-forget、immediate acknowledgment、polling、failure mode；`swarm_deploy` 输出含 `object_store_key`，API Registry §11 同步。 |
| D6: soft_launch 3阶段 PvP | N/A | 该项属于模式/运营发布策略，不在本 API/DX/IDL 方向的可验证范围；允许文件中也未提供 soft_launch 权威内容。 |
| DA1: deploy_mutation replay_class | CLOSED | IDL `swarm_deploy.replay_class: idempotent_mutation`，deploy section 明确 `mechanism: deploy_mutation` 与 replay `fdb_version_counter` ordering。 |
| DA2: f64→定点 | GAP | IDL 仍多处使用 `f64`：`income_rate`、`distance`、`cost`、controller `progress`、economy `income/expenses/storage_tax/maintenance`、`efficiency`、`confidence`、resource `base_value` 等。未闭合为定点类型。 |
| DA3: worker pool 256 default | CLOSED | IDL `hardware_baseline.worker_pool_max: 256`，API Registry §5.5 写 `max_pool = 256`。 |

## Concerns

### X1 — API Registry 主链路闭合，但派生文档仍会误导 SDK/MCP 实现者
`api-registry.md` 自身与 YAML 基本一致，但 `mcp-tools.md`、`commands.md`、`host-functions.md`、`design/interface.md` 仍包含旧接口、旧错误码和旧签名。对新用户而言，这会直接破坏“5 分钟上手”：同一个工具到底叫 `swarm_get_deploy_status` 还是 `swarm_list_modules`，同一个 host function 到底是 `(room_id,out_ptr,out_len)` 还是 `(x,y)`，无法预测。

### X2 — RejectionReason 的 canonical 设计尚未传播到命令校验规范
IDL 正确把 `NotMovable`/`Fatigued` 等降级为 debug_detail 示例，但命令校验表仍把它们作为失败码。实现者按 `02-command-validation.md` 开发会产出超出 35 canonical set 的 wire enum，直接破坏 D2。

### X3 — Economy 决议没有机器可读单源
Recycle lifespan refund 与 storage tax tier 是经济协议，不应只散落在 Markdown。尤其 D3 还存在“公式版”和“固定 50% 版”同时出现，属于可实现性冲突。

### X4 — `auth_api.idl.yaml` 缺失
任务要求读取 `/tmp/swarm-review-R19/specs/reference/auth_api.idl.yaml`，但该文件不存在。若 auth API 原计划作为独立 IDL 源，则 R19 不能证明 auth/MCP onboarding 的机器源闭合；若已合并入 `game_api.idl.yaml`，需要移除任务/文档对该文件的引用并让 design/interface 的旧 auth tool list 与 registry 收敛。

## Missing

- 缺少 `auth_api.idl.yaml`，或缺少“auth API 已合并到 game_api.idl.yaml”的明确迁移声明。
- 缺少 storage tax tiered 0/1/5/20bp 的机器可读字段：tier 阈值、bp 值、适用资源/容量基准、舍入规则。
- 缺少 Recycle refund 的 IDL 字段或经济规则 schema；当前仅 Markdown 公式，且有固定 50% 的陈旧文本冲突。
- 缺少 f64→fixed-point 的 IDL 类型替换；目前多个 public API output 仍暴露 f64。
- 缺少派生文档生成/校验边界说明：哪些文件是 generated，哪些文件只允许引用 registry，哪些内容不得再列独立表。

## API Consistency Issues

1. MCP tool naming 不一致：
   - Registry active deploy tools：`swarm_deploy`、`swarm_validate_module`、`swarm_get_deploy_status`、`swarm_list_deployments`、`swarm_get_world_config`、`swarm_get_world_rules`。
   - `mcp-tools.md`/`design/interface.md` 仍写 `swarm_rollback`、`swarm_list_modules`、`swarm_explain_last_tick`、`swarm_get_docs`、`swarm_get_schema` 等旧工具。

2. Host function ABI 不一致：
   - IDL：`host_get_terrain(room_id, out_ptr, out_len) -> i32`，`host_path_find(... opts_ptr, opts_len, out_ptr, out_len) -> i32`，`host_get_world_rules(rule_id_ptr, rule_id_len, out_ptr, out_len) -> i32`。
   - `host-functions.md`/`design/interface.md` 仍展示概念签名，如 `host_get_terrain(x, y) -> i32`、`host_get_world_rules(out_ptr, out_len) -> i32`。

3. Error envelope 不一致：
   - IDL/API Registry：`error.code` 是 `RejectionReason (string)`，`error.data.debug_detail` 是非 canonical detail，`-32000` 仅保留给未分类 internal error。
   - `design/interface.md` 仍展示 `error.code: -32000` + `data.swarm_error: InsufficientResources`，且使用已废弃复数形式。

4. RejectionReason 命名不一致：
   - IDL canonical：`InsufficientResource`、`ObjectNotFound`、`CooldownActive`、`NotVisibleOrNotFound` 等 35 codes。
   - `commands.md`/`02-command-validation.md` 仍列 `NotMovable`、`Fatigued`、`MissingBodyPart`、`TileBlocked`、`SourceEmpty`、`TargetFull`、`AlreadyHacked` 等作为拒绝码。

5. Capacity/limit 不一致：
   - IDL/API Registry：per-player drone cap 500；`02-command-validation.md`：MAX_DRONES_PER_PLAYER 50。
   - `02-command-validation.md` 前文 tick output 总字节 ≤256KB，后文批级校验整批 ≤1MB。
   - Host budget error code 在 IDL 是明确 ABI priority `ERR_BUDGET_EXHAUSTED=-4` 等；`host-functions.md` 仍写超预算返回 -1。

## CrossCheck

1. Security reviewer 应重点复核：`debug_detail` 在 competitive/practice/training 下的信息泄漏边界，以及旧 `design/interface.md` auth 工具是否应迁移到独立 auth IDL。
2. Architecture/replay reviewer 应复核：`fdb_version_counter`、`terminal_state`、object store pending/failed 状态是否足以支持 deterministic replay 与 deploy failure replay。
3. Economy/gameplay reviewer 应复核：Recycle lifespan refund、storage tax tier、fixed-point 类型是否已进入真正的机器可读经济规则源，而不是仅存在 Markdown。