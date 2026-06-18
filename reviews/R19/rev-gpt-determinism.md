# R19 确定性/Replay 闭合验证（GPT）

Verdict: REQUEST_MAJOR_CHANGES

结论：R19 尚未闭合 R18 的确定性/Replay 关键 blocker。YAML→registry 单源、RejectionReason canonical+debug_detail、MCP tool 安全字段、deploy_mutation/async blob 等有明确闭合证据；但 TickTrace/Persistence 仍存在 `terminal_state` 语义分叉，IDL 权威源仍暴露多个 `f64` 字段，worker pool 默认值与用户裁决冲突，经济裁决（Recycle refund lifespan、tiered storage tax）未进入机器源且与现有文档冲突。另有两个任务指定的只读文件不存在，导致 replay-recording/architecture 部分无法验证。

## Strengths

- D1/B1 方向明显改善：`api-registry.md` 明确声明由 `game_api.idl.yaml` 自动生成，冲突时 YAML 为准；IDL 也声明自身为 codegen/SDK/CI 的 canonical source。
- D2/B2 基本闭合：RejectionReason 35 canonical code + `debug_detail` + `detail_level` 在 IDL 和 generated registry 中都有机器可读/表格化定义。
- B3/B5/DA1 基本闭合：IDL 中 46 个 active MCP tools 均带 `required_scope`、`subject_source`、`replay_class`、`visibility_filter`、`rate_limit_key` 等安全/Replay 分类字段；`swarm_list_market_orders` 已移至 RFC 区。
- D5/DA1 部署路径改善：`swarm_deploy` 标为 `idempotent_mutation`，输出含 `fdb_version_counter` 与 `object_store_key`，deploy section 描述 async object-store upload + FDB manifest ordering。

## Concerns (T1, T2...)

T1. TickTrace/Persistence 的 `terminal_state` 仍是两套语义，构成 replay blocker。

- IDL/API registry 定义 `terminal_state` 为 WASM 执行终态：`Success/FuelExhausted/TimeoutExceeded/SnapshotOverBudget/CommandBufferFull/InternalError/NotExecuted`（`game_api.idl.yaml` lines 1395-1452；`api-registry.md` lines 427-468）。
- Persistence contract 仍把 `terminal_state` 用作 blob/replay 验证状态：`verified/audit_gap/unreplayable/reconstructable`（`05-persistence-contract.md` lines 215-240），且 TickTrace 示例仍含 `wasm_status: WasmStatus`（lines 197-212）。
- `design/engine.md` 也同时列出 `wasm_status` 与 `terminal_state(verified/audit_gap/...)`（lines 270-278）。
- 结果：同一字段名在 replay verifier、executor、persistence 三处代表不同状态机，`tick(seed,state,commands) -> new_state` 的 trace envelope 不闭包。

T2. DA2 `f64 → 定点` 未闭合到 IDL 权威源。

- `01-tick-protocol.md` 宣称数值使用整数+定点并禁用 `f64`（lines 624-630），RuleMod 也禁用 `f64`（line 857）。
- 但 IDL 权威源仍有 `f64` 输出字段：`income_rate`、`distance`、`cost`、`progress`、`income`、`expenses`、`storage_tax`、`maintenance`、`efficiency`、`confidence`（`game_api.idl.yaml` lines 484, 675-676, 718, 778-781, 794, 1008）。
- 结果：SDK/codegen 仍会生成浮点接口，跨平台 replay 与 hash checksum 仍有非确定性入口。

T3. DA3 worker pool 默认 256 未闭合，且与 engine.md 冲突。

- IDL/API registry 权威限制写为 `worker_pool_max: 256` / `max_pool 默认 256`（`game_api.idl.yaml` lines 1375-1377；`api-registry.md` lines 407-415）。
- `design/engine.md` 仍写 `MAX_POOL = 1000`，并用 450/750/1000 worker 场景推导容量（lines 337-353）。
- 结果：容量合同不能从单一机器源推出，worker 并行度会影响 COLLECT 调度、deadline、timeout/rejection 分布。

T4. B6/D3/D4 经济裁决未闭合到机器源，且现有文档冲突。

- D3 要求 Recycle refund lifespan 10-50%。现有可见证据只有 `09-snapshot-contract.md` 的 `recycle_refund_base=50%`、`recycle_refund_min=10%`（line 188），没有 lifespan-based formula，也未进入 IDL/registry 机器源。
- D4 要求 Storage tax tiered 0/1/5/20bp。现有 `09-snapshot-contract.md` 仍写 `StorageTax` 为 `0.1%/tick`（line 192），IDL/registry 只有 `storage_tax: f64` 输出字段（`game_api.idl.yaml` line 780；`api-registry.md` line 210），没有 tier table。
- 结果：经济 ledger 的资源变化无法由权威 IDL/registry 单源确定，Replay 可能因实现侧选择不同税率/refund 公式而分叉。

T5. 任务指定的两个只读文件不存在，Replay 录制域无法被完整验证。

- `/tmp/swarm-review-R19/design/architecture.md` 不存在（工具返回 similar files: auth/interface/README/tech-choices）。
- `/tmp/swarm-review-R19/specs/gameplay/04-replay-recording.md` 不存在（工具返回 similar files: gameplay/06-feedback-loop.md、08-api-idl.md）。
- 结果：R19 指定验证材料本身不闭合；尤其 `04-replay-recording.md` 缺失，使 replay recording 合同无法按任务要求审阅。

## 逐项判定表

| ID | 状态 | 证据 |
|---|---|---|
| B1 YAML vs Markdown 双写不一致 | CLOSED | `api-registry.md` lines 1-16 声明由 `game_api.idl.yaml` 自动生成且冲突以 YAML 为准；IDL lines 2-5 声明 machine-readable single source。 |
| B2 RejectionReason 未闭合 | CLOSED | IDL lines 229-260 定义 35 canonical code + `debug_detail` + `detail_level`；registry lines 69-89 同步生成。 |
| B3 MCP Tool 三套命名空间 | CLOSED | IDL lines 427-431 定义 46 active tools；registry lines 158-173 同步 46；`swarm_list_market_orders` 在 RFC 区（IDL lines 1177-1195，registry lines 263-271）。 |
| B4 Tick/Trace/Persistence 分叉 | GAP | `terminal_state` 在 IDL/API 是 WASM 执行终态（IDL lines 1426-1452），在 persistence 是 blob 验证终态（05 lines 215-240）；05 lines 197-212 仍保留 `wasm_status`。 |
| B5 安全字段未入机器源 | CLOSED | IDL 每个 MCP tool 带 `required_scope`、`subject_source`、`replay_class`、`visibility_filter`、`rate_limit_key`；抽样见 lines 444-475、820-839，脚本检查 46/46 均具备这些字段。 |
| B6 经济单源未闭合 | GAP | Recycle/StorageTax 仅在 `09-snapshot-contract.md` 以文本存在且与裁决不一致（line 188、192）；IDL/registry 无 lifespan refund formula 或 tiered bp table。 |
| B7 容量合同不可证明 | GAP | IDL/registry 写 worker pool max/default 256（IDL lines 1375-1377；registry lines 407-415），但 `engine.md` lines 337-353 仍以 `MAX_POOL=1000` 推导容量。 |
| D1 api-registry.md 全量生成 | CLOSED | registry lines 1-16 明确生成关系、版本、原则；内容覆盖 CommandAction、RejectionReason、MCP Tools、Host Functions、Limits、TickTrace、Deploy、Persistence。 |
| D2 RejectionReason canonical+debug_detail | CLOSED | IDL lines 229-260；registry lines 69-89；SwarmError envelope 中也有 `debug_detail`（IDL lines 1469-1481；registry lines 487-507）。 |
| D3 Recycle refund lifespan 10-50% | GAP | 仅发现 base/min 10/50（`09-snapshot-contract.md` line 188），未发现 lifespan-based refund formula，且未进入 IDL 机器源。 |
| D4 Storage tax tiered 0/1/5/20bp | GAP | `09-snapshot-contract.md` line 192 仍为 `0.1%/tick`；IDL line 780 仅 `storage_tax: f64`，无 tiered bp table。 |
| D5 blob 异步上传 | CLOSED | `05-persistence-contract.md` lines 25-64 定义 FDB commit 先完成、Phase C async object-store upload；IDL persistence lines 1568-1611 同步。 |
| D6 soft_launch 3阶段 PvP | N/A | 属发布/玩法 rollout，不是确定性/Replay 闭合项；指定材料中也未提供 soft_launch PvP 三阶段合同。 |
| DA1 deploy_mutation replay_class | CLOSED | `swarm_deploy` IDL lines 820-839 含 `replay_class: idempotent_mutation`；deploy mechanism/fdb_version_counter 见 IDL lines 1524-1566。 |
| DA2 f64→定点 | GAP | `01-tick-protocol.md` lines 624-630 禁 `f64`，但 IDL 仍有多个 `f64` 字段（lines 484, 675-676, 718, 778-781, 794, 1008）。 |
| DA3 worker pool 256 default | GAP | IDL/registry 已有 256（IDL lines 1375-1377；registry lines 407-415），但 `engine.md` 仍为 `MAX_POOL=1000`（lines 337-353）。 |

## GAP 具体位置与内容

1. `specs/core/05-persistence-contract.md` lines 197-212, 215-240；`design/engine.md` lines 270-278；`specs/reference/game_api.idl.yaml` lines 1426-1452
   - 同名 `terminal_state` 分别表示 WASM execution terminal state 与 replay/blob verification terminal state。
   - 建议：保留 IDL 的 `terminal_state` 作为 WASM execution 终态；将 persistence 的 verified/audit_gap/unreplayable/reconstructable 改名为 `replay_blob_state` 或 `audit_blob_state`，并让 TickTrace 示例删除/迁移 legacy `wasm_status`。

2. `specs/reference/game_api.idl.yaml` lines 484, 675-676, 718, 778-781, 794, 1008
   - 权威 IDL 仍使用 `f64` 输出字段，与 `01-tick-protocol.md` 禁 f64 冲突。
   - 建议：改为定点类型（如 `Fixed64`, `BasisPoints`, `MilliUnits`, 或 `{value_i64, scale}`），并在 canonical codec 中定义舍入/序列化。

3. `design/engine.md` lines 337-353 vs `specs/reference/game_api.idl.yaml` lines 1375-1377 / `api-registry.md` lines 407-415
   - worker pool 最大/默认 1000 vs 256 冲突。
   - 建议：engine.md 只引用 registry 的 256，不再保留独立容量推导数字；若需要示例，改为 256 pool 下的 450/750/1000 active players 排队/配额推导。

4. `specs/core/09-snapshot-contract.md` lines 188, 192；`specs/reference/game_api.idl.yaml` line 780
   - Recycle refund 未按 lifespan 10-50% 定义；StorageTax 仍是 0.1%/tick 且为 `f64` 输出，未实现 0/1/5/20bp tier table。
   - 建议：将经济参数加入 IDL/registry 的 `limits` 或 `economy` section，使用 bp/整数定点，并让 `09-snapshot-contract.md` 引用机器源。

5. 缺失文件：`/tmp/swarm-review-R19/design/architecture.md`、`/tmp/swarm-review-R19/specs/gameplay/04-replay-recording.md`
   - 任务要求只读文件不存在，导致 replay recording 域无法闭合验证。
   - 建议：恢复/重命名这些文件，或更新 R19 审查输入清单；Replay recording 合同应至少包含 `ReplayRecord`, `ReplayBlobState`, keyframe/delta, manifest/hash-chain 的字段级定义。

## State Machine Gaps

- `terminal_state` 状态机未闭合：WASM execution terminal states 与 replay blob verification states 混用，导致同一 TickTrace 字段无法被 replay verifier 唯一解释。
- Persistence async upload 状态（pending/uploading/complete/failed）与 replay verifier 终态（verified/audit_gap/unreplayable/reconstructable）没有在 IDL envelope 中分层命名，容易在跨节点验证时出现不同映射。
- 经济状态机（Recycle refund、StorageTax tiers）缺少机器源字段，ResourceLedger 无法证明所有资源变化均由同一公式导出。

## Non-Determinism Sources

- IDL `f64` 仍存在：即使内部实现使用定点，SDK/API wire 层的浮点值会污染 replay checksum、client-side dry-run、MCP simulate 输出。
- Worker pool 并行度冲突：256 vs 1000 会改变 COLLECT 排队与 timeout 边界，进而改变 `terminal_state`/empty-command 分布。
- `terminal_state` 命名冲突：不同组件可能把同一字段序列化为不同 enum domain，导致 cross-node replay 输出不一致。
- 缺失 replay-recording spec：无法确认 replay blob、keyframe、delta chain、audit gap 的 canonical serialization 与 hash 输入集合。

## CrossCheck

1. 架构/文档方向：检查所有文档中 `wasm_status`、`terminal_state`、`audit_gap`、`verified` 的命名，确认是否统一为两个不同字段，而不是同名 enum。
2. 经济/资源方向：验证 Recycle refund lifespan 10-50% 与 StorageTax 0/1/5/20bp 是否进入 IDL/registry 机器源，并由 ResourceLedger 引用。
3. SDK/API 方向：运行 codegen schema 检查，禁止 `game_api.idl.yaml` 中出现 `f64`（除非明确标记为非 replay / non-authoritative display-only）。
