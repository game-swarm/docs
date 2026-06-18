# R19 经济/数值闭合验证（GPT）

Verdict: REQUEST_MAJOR_CHANGES

结论：R18 的经济方向核心 blocker 尚未完全闭合。尤其是 B6「经济单源」在 Markdown Resource Ledger 与权威 IDL YAML 之间仍存在结构性断裂：Resource Ledger 定义了完整资源操作与经济参数，但 `game_api.idl.yaml` 的机器源仅收录了部分 ResourceOperation，且未收录 StorageTax / RecycleRefund / UpkeepDeduction 等经济结算操作与费率参数。另有 DA2「f64→定点」未在权威 IDL 的经济/路径/控制器输出中闭合。

## Strengths

- D1/D2/D5/DA1/DA3 等非经济或接口方向裁决在允许文件内可见到明确闭合证据：`api-registry.md` 声明由 `game_api.idl.yaml` 自动生成；RejectionReason 采用 35 canonical code + debug_detail；deploy_mutation / async_object_store_upload / worker pool 256 均已进入 IDL/Registry。
- D3/D4 的设计意图在 `specs/core/08-resource-ledger.md` 中已写清：Recycle lifespan 10%–50%，Storage tax tiered 0/1/5/20bp。
- `design/economy-balance-sheet.md` 明确声明 Resource Ledger 是费率与公式的唯一权威源，并引用维护费、回收、存储税公式，方向正确。

## 逐项判定表

| ID | 状态 | 证据 |
|---|---|---|
| B1: YAML vs Markdown 双写不一致 | GAP | 经济域仍存在 YAML/Markdown 断裂：`08-resource-ledger.md:41-56` 定义 `AlliedTransfer`/`PvEAward`/`RecycleRefund`/`BuildCost`/`SpawnCost`/`UpkeepDeduction`/`StorageTax` 等操作，但权威 `game_api.idl.yaml:1489-1521` 的 `resource_operation` 只列出 Harvest/Transfer/Withdraw/TransferToGlobal/TransferFromGlobal/Drain。另见 IDL 经济输出仍用 `f64`（`game_api.idl.yaml:778-781`）。 |
| B2: RejectionReason 未闭合 | N/A | 非经济方向。允许文件中可见 `game_api.idl.yaml:231-259` 与 `api-registry.md:69-89` 已定义 35 canonical code + debug_detail/detail_level。 |
| B3: MCP Tool 三套名称空间 | N/A | 非经济方向。允许文件中可见 `api-registry.md:158-271`：46 active tools，market orders 移至 RFC；`game_api.idl.yaml:429-431` 亦声明 46。 |
| B4: Tick/Trace/Persistence 分叉 | N/A | 非经济方向。允许文件中可见 `game_api.idl.yaml:1397-1452` 定义 TickTrace envelope 与 terminal_state；`api-registry.md:427-468` 同步。 |
| B5: 安全字段未入机器源 | N/A | 非经济方向。允许文件中可见 MCP tools 具备 required_scope/subject_source/replay_class/visibility_filter/rate_limit_key 等列（如 `game_api.idl.yaml:444-458`）。 |
| B6: 经济单源未闭合 | GAP | Resource Ledger Markdown 声称是「唯一经济权威」（`08-resource-ledger.md:60-64`），并定义参数表（`08-resource-ledger.md:65-94`）、StorageTax/Reycle 公式（`08-resource-ledger.md:95-118`）、执行顺序（`08-resource-ledger.md:145-160`）。但权威 IDL YAML 没有这些参数/公式，且 `resource_operation` 只含 6 个操作（`game_api.idl.yaml:1489-1521`），未包含 `StorageTax`/`RecycleRefund`/`UpkeepDeduction` 等。按任务约束「以 IDL YAML 为权威源」，该 blocker 未闭合。 |
| B7: 容量合同不可证明 | N/A | 非经济方向。允许文件中可见 capacity/limits 已入 IDL（`game_api.idl.yaml:1321-1393`）与 Registry（`api-registry.md:360-424`）。 |
| D1: api-registry.md 全量生成 | CLOSED | `api-registry.md:3-7` 声明由 `game_api.idl.yaml` 自动生成，冲突以 YAML 为准；`api-registry.md:599-605` 变更记录也声明 YAML IDL 成为唯一机器源。 |
| D2: RejectionReason canonical+debug_detail | N/A | 非经济方向；证据见 `game_api.idl.yaml:231-259`、`api-registry.md:69-89`。 |
| D3: Recycle refund lifespan 10-50% | GAP | Markdown 设计已写入：`08-resource-ledger.md:111-118` 定义 `recycle_refund = body_cost × remaining_lifespan / total_lifespan × recycle_refund_base / 10000` 且 min=10%、base=50%；但 IDL YAML 的 `resource_operation` 未包含 `RecycleRefund`（`game_api.idl.yaml:1489-1521`），机器源无法证明该裁决已闭合。 |
| D4: Storage tax tiered 0/1/5/20bp | GAP | Markdown 设计已写入：`08-resource-ledger.md:78-87` 与 `design/gameplay.md:340-351` 定义 0/1/5/20bp tier；但 IDL YAML 没有 `storage_tax_tiers` 或 `StorageTax` operation，仅 Markdown 可见。按 IDL 权威约束，机器源未闭合。 |
| D5: blob 异步上传 | N/A | 非经济方向。允许文件中可见 `game_api.idl.yaml:1570-1611` 与 `api-registry.md:561-587` 定义 async_object_store_upload。 |
| D6: soft_launch 3阶段 PvP | N/A | 非经济方向。允许文件中可见 `design/gameplay.md:547-598` 定义 Phase 1/2/3。 |
| DA1: deploy_mutation replay_class | N/A | 非经济方向。允许文件中可见 `game_api.idl.yaml:820-843` swarm_deploy 为 `idempotent_mutation` 且包含 fdb_version_counter。 |
| DA2: f64→定点 | GAP | 权威 IDL YAML 仍存在 `f64` 输出：`swarm_get_resources.income_rate`（`game_api.idl.yaml:482-485`）、`swarm_get_path.distance/cost`（`game_api.idl.yaml:673-676`）、`swarm_get_controller.progress`（`game_api.idl.yaml:716-719`）、`swarm_get_economy.income/expenses/storage_tax/maintenance`（`game_api.idl.yaml:776-781`）、`swarm_get_drone_efficiency.efficiency`（`game_api.idl.yaml:792-795`）、`resources/read.base_value`（`game_api.idl.yaml:1166-1169`）。经济口径至少 `income/expenses/storage_tax/maintenance` 未完成定点化。 |
| DA3: worker pool 256 default | N/A | 非经济方向。允许文件中可见 `game_api.idl.yaml:1370-1377` 与 `api-registry.md:407-415` 定义 max_pool 默认 256。 |

## Concerns

### E1 — 经济账本仍不是机器单源

`08-resource-ledger.md` 已经成为较完整的经济设计文档，但它不是任务指定的权威机器源。当前 IDL 只包含部分资源相关 CommandAction/ResourceOperation，缺少：

- `PvEAward`
- `RecycleRefund`
- `BuildCost`
- `SpawnCost`
- `UpkeepDeduction`
- `StorageTax`
- `AlliedTransfer`
- 经济费率参数：`global_deposit_fee`、`global_withdraw_fee`、`storage_tax_tiers`、`recycle_refund_base/min`、`base_upkeep`、`room_soft_cap` 等

这会导致 codegen/CI/SDK 无法从机器源验证经济闭环。

### E2 — D3/D4 在 Markdown 闭合，但未在 IDL 闭合

Recycle 10%–50% 与 Storage tax 0/1/5/20bp 的公式和参数在 Resource Ledger 中清楚，但如果实现端只消费 IDL YAML，无法自动生成或校验这些经济规则。按 R19 约束，这不能算完全 CLOSED。

### E3 — DA2 定点化对经济输出未闭合

`Resource Ledger` 原则要求费率使用 bp/ppm、禁止浮点（`08-resource-ledger.md:7-10`），但 IDL 对玩家可见经济输出仍使用 `f64`。这不是单纯展示问题：`income/expenses/storage_tax/maintenance` 是经济调试与策略输入，若以 `f64` 作为 wire schema，会破坏定点一致性目标。

## Economy Balance Issues

- 维护费曲线本身在 `economy-balance-sheet.md` 中给出了 1/5/20/50 房间验证，并能表达反雪球目标；但其权威性依赖 `08-resource-ledger.md`，不是 IDL YAML。
- `design/gameplay.md` 仍有旧口径残留：例如 `transfer_to_global_cost = {Energy: 0.01}` / `transfer_from_global_cost = {Energy: 0.05}`（`design/gameplay.md:308-313`）使用小数形式，而 Resource Ledger 要求 bp 定点费率。虽然意图等价于 1%/5%，但仍是双写风险。
- `design/gameplay.md:106-108` 仍写「标准世界回收退还 50%」，而 Resource Ledger 已改为 lifespan 10%–50%（`08-resource-ledger.md:111-118`）。这是 D3 的文档残留风险。

## Resource Loop Gaps

- Resource Ledger 的完整闭环存在于 Markdown，但没有进入 IDL 的机器可读 `resource_operation` 与参数 schema。
- `ResourceOperation` IDL 当前只覆盖玩家命令相关转移，不覆盖系统结算类资源流（upkeep/tax/spawn/build/recycle/PvE award）。这使 `Σ inflows - Σ outflows = Δ storage` 的 CI 账本校验无法仅凭 IDL 构建。
- Future RFC 的 market/contract 已隔离为 RFC，这一点闭合；但 AlliedTransfer 在 Resource Ledger 中是 active/受限路径，IDL ResourceOperation 未登记，仍可能形成实现口径分叉。

## GAP 位置与内容

1. `specs/reference/game_api.idl.yaml:1489-1521`
   - 内容：`resource_operation.operations` 仅列 Harvest/Transfer/Withdraw/TransferToGlobal/TransferFromGlobal/Drain。
   - GAP：缺少 Resource Ledger 中定义的系统经济操作：StorageTax、RecycleRefund、UpkeepDeduction、PvEAward、BuildCost、SpawnCost、AlliedTransfer。

2. `specs/reference/game_api.idl.yaml:776-781`
   - 内容：`swarm_get_economy` 输出 `income/expenses/storage_tax/maintenance: f64`。
   - GAP：DA2 要求 f64→定点；经济输出仍使用 f64。

3. `design/gameplay.md:106-108` 与 `specs/core/08-resource-ledger.md:111-118`
   - 内容：gameplay 仍写标准回收固定 50%，Resource Ledger 写 lifespan 10%–50%。
   - GAP：D3 在 Markdown 间仍有残留冲突；以 Resource Ledger 为意图正确，但需要消除旧口径或改为引用。

4. `design/gameplay.md:308-313` 与 `specs/core/08-resource-ledger.md:65-94`
   - 内容：gameplay 使用 `{Energy: 0.01}` / `{Energy: 0.05}` 小数成本，Resource Ledger 使用 `global_deposit_fee=100bp` / `global_withdraw_fee=500bp`。
   - GAP：同一经济参数仍存在小数 vs bp 双写。

## CrossCheck

1. 架构/API 方向应确认：是否接受将 Resource Ledger 的经济参数与系统 ResourceOperation 纳入 `game_api.idl.yaml`，或另建 machine-readable `economy.idl.yaml` 并由 `game_api.idl.yaml` 引用；否则 B6 不能算闭合。
2. 确定性方向应验证：所有 `f64` wire schema 是否必须改为 fixed/int/bp，尤其 `swarm_get_economy` 与 `swarm_get_resources`。
3. 文档一致性方向应清理 `design/gameplay.md` 中固定 50% recycle 与小数费率残留，统一改为引用 Resource Ledger 或生成内容。
