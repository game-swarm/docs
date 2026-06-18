# R19 性能评审（GPT）闭合验证

Verdict: REQUEST_MAJOR_CHANGES

结论：R19 已明显推进了 IDL 单源化、RejectionReason、MCP Tool 安全字段、TickTrace/Persistence 结构化等闭合项；但在性能关键路径上仍存在可阻断的单源不一致与容量合同不可证明问题。尤其是 worker pool 权威值在 IDL/api-registry 与 engine.md 的 1000-worker 推导冲突，且 02-command-validation.md 仍保留与 06 manifest 冲突的 status_advance 调度和旧 Recycle 50% 退还表述；这些会直接影响 1000 active players / 10000 drones 下的 tick 预算、ECS 调度可验证性与 replay determinism。

## 逐项判定表

| ID | 状态 | 证据 |
|---|---|---|
| B1 YAML vs Markdown 双写不一致 | GAP | `specs/reference/game_api.idl.yaml:1375-1377` 与 `specs/reference/api-registry.md:413-414` 将 `worker_pool_max` 定为 256；但 `design/engine.md:337-352` 使用 `MAX_POOL=1000` 并以 1000 workers 做 1000-player 推导。`specs/core/02-command-validation.md:512-518` 的 status_advance 调度也与 `specs/core/06-phase2b-system-manifest.md:31-61` / `01-tick-protocol.md:832-842` 的权威顺序冲突。 |
| B2 RejectionReason 未闭合 | CLOSED | `specs/reference/game_api.idl.yaml:231-259` 定义 35 canonical codes + `debug_detail` + `detail_level`；`specs/reference/api-registry.md:69-90` 同步生成并声明 canonical wire enum 与 debug_detail 分离。 |
| B3 MCP Tool 三套命名空间 | CLOSED | `specs/reference/game_api.idl.yaml:429-438` 定义 MCP tools 总数 46 与 rate limit 类别；`specs/reference/api-registry.md:158-173` 生成 46 active tools，`api-registry.md:263-271` 将 `swarm_list_market_orders` 移到 RFC/Future，避免活跃命名空间漂移。 |
| B4 Tick/Trace/Persistence 分叉 | GAP | 正向证据：`game_api.idl.yaml:1397-1452` 与 `api-registry.md:427-469` 定义 22 字段 TickTrace Envelope 和 `terminal_state`；`api-registry.md:526-597` 定义 deploy/persistence。阻断冲突：`02-command-validation.md:512-518` 仍声明 `death_mark → spawn → spawning_grace → combat → status_advance → (regeneration, decay 并行) → death_cleanup`，与 `06-phase2b-system-manifest.md:31-61` 的 `regeneration → combat → special_attack_reducer → damage_application → status effects → aging → decay` 不一致。 |
| B5 安全字段未入机器源 | CLOSED | `game_api.idl.yaml:429-438` 声明工具结构；各工具条目包含 `required_scope`、`subject_source`、`replay_class`、`visibility_filter`、`rate_limit_key`，例如 `swarm_deploy` 见 `game_api.idl.yaml:820-843`。`api-registry.md:173-261` 生成同样列。 |
| B6 经济单源未闭合 | GAP | `game_api.idl.yaml:1489-1521` / `api-registry.md:511-523` 的 ResourceOperation 仅覆盖 Harvest/Transfer/Withdraw/Global/Drain，不包含 StorageTax 或 RecycleRefund；`02-command-validation.md:489-510` 有 lifespan 10%-50% 新公式，但 `02-command-validation.md:274-287` 与 `02-command-validation.md:712-724` 仍保留固定 50% 退还。 |
| B7 容量合同不可证明 | GAP | IDL 权威容量为 `worker_pool_max: 256`（`game_api.idl.yaml:1375-1377`，`api-registry.md:407-415`），但 `design/engine.md:337-352` 使用 `MAX_POOL=1000`，且 `design/engine.md:373-383` 的 hard cap 1000 players 推导依赖 1000 workers；因此 1000-player 容量证明没有基于权威 256-worker 合同重算。 |
| D1 api-registry.md 全量生成 | CLOSED | `api-registry.md:1-7` 明确“由 game_api.idl.yaml 自动生成，冲突时以 YAML 为准”，并列出 API version 0.3.0；`game_api.idl.yaml:8` 为同版本。 |
| D2 RejectionReason canonical+debug_detail | CLOSED | `game_api.idl.yaml:231-259` 定义 canonical enum + debug_detail；`api-registry.md:71-90` 生成相同结构，且 `api-registry.md:487-505` 在 SwarmError envelope 中包含 `debug_detail`。 |
| D3 Recycle refund lifespan 10-50% | GAP | 新公式存在于 `02-command-validation.md:489-510`；但同文件 `02-command-validation.md:274-287` 与 `02-command-validation.md:712-724` 仍写“50%”固定退还，形成实现者可误读的冲突。 |
| D4 Storage tax tiered 0/1/5/20bp | GAP | 在允许读取的权威 IDL/registry 中未找到 StorageTax tier 的机器源；`game_api.idl.yaml:1489-1521` 的 ResourceOperation 也未包含 StorageTax。该经济扣费若不进入机器源，无法纳入 resource ledger/replay hash 的容量与写入预算证明。 |
| D5 blob 异步上传 | CLOSED | `game_api.idl.yaml:1568-1611` 定义 `async_object_store_upload`、fire-and-forget、polling 与 retry；`api-registry.md:561-597` 生成同一 Persistence 合同。 |
| D6 soft_launch 3阶段PvP | N/A | 非性能方向；允许读取文件中也未见 soft_launch PvP 三阶段的机器源证据。本评审不据此重审玩法发布策略。 |
| DA1 deploy_mutation replay_class | GAP | Deploy 机制本身已闭合：`game_api.idl.yaml:1526-1558` 为 `mechanism: deploy_mutation`，`api-registry.md:526-558` 同步生成；但 MCP tool 表中 `swarm_deploy` 的 `replay_class` 仍是 `idempotent_mutation`（`game_api.idl.yaml:820-843`，`api-registry.md:214-225`），未形成“deploy_mutation replay_class”的闭合命名。 |
| DA2 f64→定点 | GAP | `design/engine.md:448-454` 已声明整数/定点与 basis points；但 IDL 权威源仍含多个 `f64` 输出字段，例如 `game_api.idl.yaml:477-485` (`income_rate: f64`)、`667-677` (`distance/cost: f64`)、`711-720` (`progress: f64`)、`773-782` (`income/expenses/storage_tax/maintenance: f64`)、`789-796` (`efficiency: f64`)、`999-1009` (`confidence: f64`)、`1160-1169` (`base_value: f64`)。即使部分为展示/查询，机器源仍未完成 f64→fixed 的一致迁移。 |
| DA3 worker pool 256 default | GAP | IDL/api-registry 权威值已是 256（`game_api.idl.yaml:1375-1377`，`api-registry.md:413-414`），但 `design/engine.md:337-352` 和 `design/engine.md:373-383` 仍按 1000 workers 建模；作为性能容量决策，未在所有允许文档闭合。 |

## GAP 具体位置与内容

### P1 — worker_pool_max 单源冲突导致 1000-player 容量证明失效

位置：
- `specs/reference/game_api.idl.yaml:1375-1377`
- `specs/reference/api-registry.md:413-414`
- `design/engine.md:337-352`
- `design/engine.md:373-383`

内容：IDL/registry 的权威硬件基线是 `worker_pool_max = 256`，但 engine.md 仍声明 `MAX_POOL = 1000` 并以 1000 workers 证明 1000 active players hard cap。按权威 256 workers，1000 players 至少需要 4 waves；engine.md 中“1000 workers / 40 cores”的推导不再成立。该问题直接阻断 B7 与 DA3 的闭合。

### P1 — Phase 2b 调度仍有旧路径，Tick/Trace/Persistence 闭合不稳

位置：
- `specs/core/02-command-validation.md:512-518`
- `specs/core/06-phase2b-system-manifest.md:31-61`
- `specs/core/01-tick-protocol.md:832-842`

内容：02-command-validation.md 仍写 `combat → status_advance → (regeneration, decay 并行)`；manifest/01 则为 `regeneration → combat → special_attack_reducer → damage_application → status effects → aging → decay`。这不是文字小差异，而是影响 HP、status、regen、damage_application 的 ECS 依赖顺序差异；如果实现者参考 02，则 TickTrace replay 与 manifest hash 可能无法证明一致。

### P1 — Recycle 经济公式仍双写冲突

位置：
- `specs/core/02-command-validation.md:274-287`
- `specs/core/02-command-validation.md:489-510`
- `specs/core/02-command-validation.md:712-724`

内容：同一文件同时存在 fixed 50% refund 与 lifespan-based 10%-50% refund。对性能评审而言，这会影响 resource ledger 写入、经济事件 replay、以及大规模 Recycle/Spawn 周期的资源放大模型。

### P1 — f64 未从权威 IDL 完全移除

位置：
- `specs/reference/game_api.idl.yaml:477-485`
- `specs/reference/game_api.idl.yaml:667-677`
- `specs/reference/game_api.idl.yaml:711-720`
- `specs/reference/game_api.idl.yaml:773-782`
- `specs/reference/game_api.idl.yaml:789-796`
- `specs/reference/game_api.idl.yaml:999-1009`
- `specs/reference/game_api.idl.yaml:1160-1169`

内容：engine.md 的定点声明不能覆盖 IDL 中仍存在的 `f64` schema。即使这些字段多数属于查询输出，若它们进入 replay/debug/metrics/TickTrace 或 SDK codegen，跨平台 deterministic 与 canonical codec 都可能分叉。

### P2 — StorageTax/RecycleRefund 未进入权威经济机器源

位置：
- `specs/reference/game_api.idl.yaml:1489-1521`
- `specs/reference/api-registry.md:511-523`

内容：ResourceOperation 未包含 StorageTax 与 RecycleRefund，Storage tax tiered 0/1/5/20bp 未在允许读取的 IDL/registry 中体现。若这是刻意归属到未列入文件的 resource ledger，则当前 R19 证据不足；从本评审可见范围看，B6/D4 未闭合。

### P2 — deploy_mutation 机制与 replay_class 命名未统一

位置：
- `specs/reference/game_api.idl.yaml:820-843`
- `specs/reference/game_api.idl.yaml:1526-1558`
- `specs/reference/api-registry.md:214-225`
- `specs/reference/api-registry.md:526-558`

内容：deploy 机制为 deploy_mutation，但 `swarm_deploy` 工具的 replay_class 仍是 `idempotent_mutation`。这可能只是字段语义选择，但与 DA1 裁决文字“deploy_mutation replay_class”不一致，建议由架构/安全方向确认是否应新增 replay_class 枚举值或改裁决表述。

## Bottleneck Analysis

1. Tick 关键路径：
   - SNAPSHOT build 与 per-player stitching 的两阶段模型是正确方向，`design/engine.md:258-260` 将复杂度降为 `O(entities + players × visible_rooms)`；但 `01-tick-protocol.md:184-198` 仍写 “Bevy World 深拷贝” 用于 COLLECT 快照，`01-tick-protocol.md:397-438` 又要求 Phase 2a 前完整 Bevy World snapshot 用于 rollback。若这些都是深拷贝，50000 entities 下的内存带宽需要 CI 实测，否则 snapshot 50ms p99 合同偏乐观。
   - EXECUTE budget 在 `engine.md:295` 是 ≤400ms，`01-tick-protocol.md:73-75` 是 500ms，`01-tick-protocol.md:699-703` 又说 EXECUTE 不单独超时、由总预算控制。预算语义仍不完全统一。

2. ECS 并行调度：
   - `06-phase2b-system-manifest.md` 的 R/W 矩阵与 parallel set 证明比前轮更可验证；Combat set 按 target_id partition、Status set 按 subtype partition 是合理闭合。
   - 阻断点是 `02-command-validation.md:512-518` 的旧调度残留。一旦实现者用旧顺序，regen/status/combat 的依赖不再最小化且不可 replay。

3. WASM fuel metering 与无界操作：
   - host call 总预算 1000/tick/player、path_find 10/tick、全局 100000 explored nodes/tick、输出上限 256KB 已在 IDL/registry 中闭合。
   - `host_path_find` 成本按 `500 × nodes + 200 × edges` 是合理 work-proportional metering；但 1000 players 时 fair-share 只有 100 nodes/player/tick，玩家的 10 path_find 调用多数会 deterministic fail。容量上可控，但 gameplay/UX 方向需确认这是否可接受。

4. FDB/对象存储热点：
   - D5 的 async object-store upload 与 FDB 小 manifest 已闭合，避免 WASM blob 进入 FDB 热事务。
   - 仍需确认 deploy status pending/failed 不会在同一热点 key 上轮询争用；当前文档有 `fdb_version_counter` 严格排序，但未展开 keyspace 分布策略。本轮不作为 blocker。

## Throughput Estimates

基于允许文档中的数值：1000 active players、权威 `worker_pool_max = 256`、per-player p50 5ms / p99 15ms（`design/engine.md:363-383` 给出的假设）、Collect budget 2500ms。

- 1000 players on 256 workers: 至少 `ceil(1000/256)=4` waves。
- WASM 执行 wall-clock 粗估：
  - p50 5ms/player → 约 20ms 纯执行波次时间（不含 snapshot stitching、IPC、调度）。
  - p99 15ms/player → 约 60ms 纯执行波次时间。
  - 若按 cgroup 上限 250ms/player 触顶 → 约 1000ms wall-clock，仍在 2500ms collect 内，但 CPU 核心总量会成为瓶颈。
- CPU 配额一致性：`cpu.max = 0.25s / 3s`，1000 sandbox 理论可请求 250 CPU-s/3s；硬件基线 32 cores 只有 96 CPU-s/3s。必须依赖 fuel admission/实际负载远低于 cgroup cap，否则 OS 层 CPU 上限总和超过机器物理容量。
- Pathfinding fair-share：100000 explored nodes/tick / 1000 players = 100 nodes/player/tick。对复杂路径几乎只够极短路径或缓存命中，性能安全但功能体验偏紧。

## CrossCheck

1. 架构方向：确认 DA1 是要求 `swarm_deploy.replay_class = deploy_mutation`，还是“deploy mechanism = deploy_mutation、replay_class 仍可为 idempotent_mutation”。
2. 安全/确定性方向：复核 IDL 中所有 `f64` 是否必须改为 fixed/basis-points，尤其是 debug/simulate 输出是否会进入 canonical codec、TickTrace 或 replay verifier。
3. 经济方向：确认 StorageTax tiered 0/1/5/20bp 与 RecycleRefund 是否已在未列入本任务的 resource ledger 机器源中；若是，应将该机器源纳入 R20 闭合验证清单。