# R19 架构评审（GPT）

## Verdict

**CONDITIONAL_APPROVE**

R19 已明显收敛 R18 的主要权威源问题：`game_api.idl.yaml` 成为机器源，`api-registry.md` 标注为生成物；RejectionReason、MCP 工具安全列、deploy mutation、异步 blob 上传、资源账本和容量上限均有权威落点。

但仍存在 2 个会影响架构闭合的实质 GAP：

- **TickTrace / Persistence 语义仍分叉**：`terminal_state` 在 IDL/API registry 中表示 WASM 执行终态，但在 persistence/engine 文档中仍被用作 blob/replay 完整性终态，且 `wasm_status` 仍残留。
- **容量/数值合同未完全回灌**：worker pool 在 registry 中为 256，但 engine.md 仍写 1000；IDL 仍有多处 `f64` 输出，未完成 DA2 的定点化裁决。

这两个 GAP 未达到需要重新设计的程度，但必须在实现前修正为单一机器源，否则 replay、capacity admission 和 SDK codegen 会产生分叉。

## Strengths

1. **IDL 权威化方向正确**：`specs/reference/game_api.idl.yaml` 明确声明为 machine-readable single source of truth，`api-registry.md` 声明由 YAML 自动生成。
2. **MCP tool 面收敛明显**：活跃工具数固定为 46，`swarm_list_market_orders` 被移至 RFC；Auth 工具并入 active set，且工具表具备 security columns。
3. **资源账本比上一轮更像可实现合同**：`08-resource-ledger.md` 将费用、回收、税率、PvE faucet、Future RFC 入口集中到一个 Resource Ledger，方向上解决了“经济多入口逃逸”。
4. **持久化大对象异步化合理**：`05-persistence-contract.md` 将 FDB commit 与 object-store blob upload 解耦，避免 FDB 大事务，并用 manifest/hash/status 补足 replay 检查路径。

## Concerns

### A1. TickTrace 的 `terminal_state` 仍是双语义，B4 未完全闭合

- `game_api.idl.yaml` 将 `terminal_state` 定义为 WASM 执行结果：`Success / FuelExhausted / TimeoutExceeded / SnapshotOverBudget / CommandBufferFull / InternalError / NotExecuted`。
- `api-registry.md` 同步生成了上述 7 个执行终态。
- 但 `05-persistence-contract.md` 仍把 `terminal_state` 用作 blob/replay 完整性状态：`verified / audit_gap / unreplayable / reconstructable`。
- `design/engine.md` 仍列出 `wasm_status`，并把 `terminal_state` 写成 replay/blob 完整性状态。
- `01-tick-protocol.md` 的 COLLECT retry 缓存也仍引用 `wasm_status`。

这是典型“看起来都叫 terminal_state，但其实是两个状态机”的风险。实现者很容易把 WASM 执行终态、TickTrace blob 完整性、replay verification 结果混在同一个字段里，导致 replay verifier 与 SDK/IDL 分叉。

### A2. 容量合同在 registry 与 engine.md 间仍冲突，B7/DA3 未完全闭合

- `game_api.idl.yaml` / `api-registry.md` 的 hardware baseline 写明：`worker_pool_max: 256`，`worker_pool_size = min(max_pool, active_players)`。
- `design/engine.md` 仍写：`MAX_POOL = 1000`，并包含 450/750/1000 player 场景下 450/750/1000 workers 的推导。

这会直接影响资源规划、cgroup 配额、进程数上限、故障域和 admission gate。若按 256 实现而按 1000 评估容量，容量论证不可证明；若按 1000 实现，则违反 DA3 用户裁决。

### A3. DA2 “f64 → 定点”未完全闭合到 IDL 机器源

`01-tick-protocol.md` 和 `08-resource-ledger.md` 已声明禁用 `f64` / 使用 basis points、整数、定点数；但权威机器源 `game_api.idl.yaml` 仍包含多处 `f64`，例如：

- `swarm_get_resources.output_schema.income_rate: f64`
- `swarm_get_path.output_schema.distance/cost: f64`
- `swarm_get_controller.output_schema.progress: f64`
- `swarm_get_economy.output_schema.income/expenses/storage_tax/maintenance: f64`
- `swarm_get_drone_efficiency.output_schema.efficiency: f64`
- `swarm_simulate.output_schema.confidence: f64`
- `resources/read.output_schema.base_value: f64`

若 IDL codegen 仍生成浮点字段，SDK、MCP response、replay comparison 和 deterministic tests 都会绕过文档里的定点约束。

## 逐项判定表

| ID | 状态 | 证据 |
|---|---|---|
| B1: YAML vs Markdown 双写不一致 | CLOSED | `game_api.idl.yaml` lines 2-5 声明 machine-readable SSoT；`api-registry.md` lines 1-7 声明由 `game_api.idl.yaml` 自动生成，冲突时以 YAML 为准；版本均为 `0.3.0`。 |
| B2: RejectionReason 未闭合 | CLOSED | `game_api.idl.yaml` lines 229-260 定义 35 canonical codes + `debug_detail` + `detail_level`；`api-registry.md` lines 69-89 同步生成；SwarmError envelope 含 `debug_detail`。 |
| B3: MCP Tool 三套名称空间 | CLOSED | `game_api.idl.yaml` lines 427-430 定义 46 active tools；lines 571-602 新增 Auth；lines 1177-1195 将 `swarm_list_market_orders` 放入 RFC，不计 active count；工具均含 `required_scope / subject_source / replay_class / visibility_filter / rate_limit_key`。 |
| B4: Tick/Trace/Persistence 分叉 | GAP | IDL/API registry 将 `terminal_state` 定义为 WASM 执行终态；`05-persistence-contract.md` lines 215-240 仍将 `terminal_state` 用于 blob 完整性；`design/engine.md` lines 270-278 同时保留 `wasm_status` 和另一套 `terminal_state`；`01-tick-protocol.md` line 441 仍引用 `wasm_status`。 |
| B5: 安全字段未入机器源 | CLOSED | `game_api.idl.yaml` 每个 active MCP tool 均包含 security columns；示例 lines 452-457、833-838、1044-1049；`api-registry.md` 工具表也生成这些列。 |
| B6: 经济单源未闭合 | CLOSED | `08-resource-ledger.md` lines 60-64 明确声明其为经济费率、公式、参数唯一权威源；lines 65-118 定义 storage tax 与 recycle 公式；Future RFC 入口在 lines 227-237 被隔离。仍建议文档审计修正 `09-snapshot-contract.md` 的旧 storage tax 描述。 |
| B7: 容量合同不可证明 | GAP | registry/IDL 将 worker pool max 定为 256（`game_api.idl.yaml` lines 1375-1377；`api-registry.md` lines 411-415），但 `design/engine.md` lines 337-353 仍以 `MAX_POOL = 1000` 推导容量。 |
| D1: `api-registry.md` 全量生成 | CLOSED | `api-registry.md` lines 1-7 和 lines 599-605 标注生成源、版本、变更记录；内容覆盖 CommandAction、RejectionReason、MCP Tools、Host Functions、Limits、TickTrace、Deploy、Persistence。 |
| D2: RejectionReason canonical + debug_detail | CLOSED | `game_api.idl.yaml` lines 231-260；`api-registry.md` lines 69-89；error envelope lines 487-507。 |
| D3: Recycle refund lifespan 10-50% | CLOSED | `08-resource-ledger.md` lines 88-90 定义 `recycle_refund_base=5000bp`、`recycle_refund_min=1000bp`；lines 111-118 给出 lifespan 公式。 |
| D4: Storage tax tiered 0/1/5/20bp | CLOSED | `08-resource-ledger.md` lines 78-87 定义 `[(30,0),(60,1),(85,5),(100,20)]`；lines 95-109 给出 tiered 公式。 |
| D5: blob 异步上传 | CLOSED | `05-persistence-contract.md` lines 25-64 定义 FDB commit 先完成、object store 异步写入；`game_api.idl.yaml` lines 1568-1612 定义 `async_object_store_upload`。 |
| D6: soft_launch 3阶段 PvP | GAP | 只看到 `08-resource-ledger.md` lines 91-93 的 `soft_launch_duration = 1500 tick` 与 “safe_mode 结束后 PvE-only 保护期”；未看到 3 阶段 PvP 的状态机、阶段名、转换条件或 TickTrace/配置字段。 |
| DA1: deploy_mutation replay_class | CLOSED | `swarm_deploy` 在 `game_api.idl.yaml` lines 820-843 标记 `replay_class: idempotent_mutation`，并说明 deploy_mutation + `fdb_version_counter`；`api-registry.md` lines 214-225 同步生成。 |
| DA2: f64→定点 | GAP | 文本规范已要求禁用浮点（`01-tick-protocol.md` lines 628-630；`08-resource-ledger.md` lines 194-203），但权威 IDL 仍存在多处 `f64` 输出字段，如 `income_rate`、`distance/cost`、`progress`、`storage_tax`、`efficiency`、`confidence`、`base_value`。 |
| DA3: worker pool 256 default | GAP | registry/IDL 已写 `worker_pool_max: 256`，但 `design/engine.md` lines 337-353、393-398 仍按 `MAX_POOL = 1000` 描述。 |

## GAP 具体位置与内容

### GAP-1: `terminal_state` / `wasm_status` 双状态机冲突

位置：

- `/tmp/swarm-review-R19/specs/reference/game_api.idl.yaml` lines 1395-1453
- `/tmp/swarm-review-R19/specs/reference/api-registry.md` lines 427-468
- `/tmp/swarm-review-R19/specs/core/05-persistence-contract.md` lines 215-240
- `/tmp/swarm-review-R19/design/engine.md` lines 270-278
- `/tmp/swarm-review-R19/specs/core/01-tick-protocol.md` line 441

内容：

- IDL/API registry 的 `terminal_state` = WASM execution terminal state。
- persistence/engine 的 `terminal_state` = blob/replay verification terminal state。
- `wasm_status` 在若干文档中仍作为 TickTrace 字段残留。

建议闭合方式：

- 保留 IDL 的 `terminal_state` 作为唯一 WASM 执行终态字段。
- 将 persistence 中的 `verified/audit_gap/unreplayable/reconstructable` 改名为 `trace_integrity_state` 或 `blob_integrity_state`。
- 删除/替换所有 `wasm_status` 残留为 `terminal_state`，并补充迁移说明。

### GAP-2: worker pool 256 与 1000 冲突

位置：

- `/tmp/swarm-review-R19/specs/reference/game_api.idl.yaml` lines 1375-1377
- `/tmp/swarm-review-R19/specs/reference/api-registry.md` lines 411-415
- `/tmp/swarm-review-R19/design/engine.md` lines 337-353、393-398

内容：

- 机器源和 registry：`worker_pool_max = 256`。
- engine.md：`MAX_POOL = 1000`，且容量推导使用 450/750/1000 workers。

建议闭合方式：

- 以 IDL/registry 的 256 为权威，将 engine.md 的公式与推导改为 `MAX_POOL = 256`。
- 重新计算 500/1000 player 场景下的 per-player quota、queueing model、degraded/admission 行为。

### GAP-3: DA2 定点裁决未进入 IDL

位置：

- `/tmp/swarm-review-R19/specs/reference/game_api.idl.yaml` 多处 `f64` 字段。

内容：

- 规范文本禁止 `f64`，但机器源仍生成 `f64` schema。
- 这会导致 SDK/API 层继续暴露浮点值。

建议闭合方式：

- 将 `f64` 字段替换为明确的定点类型，例如 `FixedBps`、`FixedPpm`、`ResourceRateI64`、`DistanceMilli`、`ConfidenceBps`、`ProgressUnits`。
- 在 IDL type section 中定义这些定点类型的单位、范围、舍入规则。

### GAP-4: D6 soft_launch 三阶段 PvP 未找到闭合证据

位置：

- `/tmp/swarm-review-R19/specs/core/08-resource-ledger.md` lines 91-93 仅出现 `soft_launch_duration`。

内容：

- 未看到 “3阶段 PvP” 的阶段定义、状态机、配置字段、默认持续时间、进入/退出条件、与 safe_mode/new_player_transfer_lock 的关系。

建议闭合方式：

- 在权威配置/IDL 或 game mode spec 中补充三阶段枚举，例如 `ProtectedPvEOnly → LimitedPvP → FullPvP`，并写入 TickTrace/world config hash。

## Missing

1. `/tmp/swarm-review-R19/specs/reference/auth_api.idl.yaml` 在任务白名单中，但实际读取为 **File not found**。当前 Auth 工具似乎已合并进 `game_api.idl.yaml`，如果这是有意决策，应删除任务/文档中的旧文件引用；如果不是，则需要补齐 auth IDL 并明确它与 game IDL 的生成关系。
2. 未看到 soft_launch 3阶段 PvP 的权威状态机。
3. 未看到 IDL 对定点类型的统一 type alias / scalar 定义，导致 DA2 无法由 codegen 强制执行。

## CrossCheck

建议其他方向重点复核：

1. **安全评审**：确认 `debug_detail` / `detail_level` 不会在 competitive 模式泄露隐藏状态；并检查 `swarm_simulate` 的 `hint_level` override 规则是否存在“仅限训练模式提升”的歧义。
2. **实现/测试评审**：为 `api-registry.md` 增加生成校验，确保 Markdown 不可手写漂移；同时加 CI 检测 IDL 中禁止 `f64`。
3. **性能/容量评审**：基于 worker pool 256 重新验证 500/1000 active players 的 CPU admission、cgroup 数量、排队延迟和 degraded mode 触发条件。

## Phase Ordering

1. **先修机器源**：修 `game_api.idl.yaml` 的定点类型、worker pool 常量、TickTrace 字段命名；重新生成 `api-registry.md`。
2. **再清理派生文档**：更新 `design/engine.md`、`01-tick-protocol.md`、`05-persistence-contract.md` 中的 `wasm_status` / `terminal_state` / `MAX_POOL=1000` 残留。
3. **最后补 CI gate**：禁止 Markdown 手写 drift、禁止 IDL `f64`、校验 worker_pool_max 单源、校验 TickTrace 字段名唯一语义。
