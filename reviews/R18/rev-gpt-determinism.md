# R18 确定性评审（GPT-5.5）

## 1. Verdict

REQUEST_MAJOR_CHANGES

R18 在“YAML IDL → api-registry.md”这一直接生成链路上已经明显进步：我抽样/脚本核对到 CommandAction=19、RejectionReason indexed=35、MCP active tools=46、Host Functions=5，YAML 与生成 Markdown 的核心列表和 host ABI 签名一致，未发现直接 YAML→registry 表格漂移。

但“生成式单源真正闭合”尚未达成。允许阅读范围内仍存在多处由 YAML/registry 与 core specs、engine design、persistence contract 之间产生的确定性合同冲突；其中若实现者按不同文档执行，会导致 tick(seed, state, commands) → new_state 不闭包、replay 可用性语义分叉，或同一非法输入在不同节点产生不同 rejection/terminal behavior。

## 2. 发现问题（severity）

### T1 — HIGH — RejectionReason wire enum 与 command-validation 使用的拒绝码不闭合

YAML IDL 明确规定 35 个 canonical codes 是 wire enum，额外上下文应进入 `debug_detail`，不得新增 RejectionReason enum variant。api-registry.md 与 YAML 直接生成结果一致。

但 `specs/core/02-command-validation.md` 的逐指令矩阵仍大量使用未注册拒绝码，例如：

- `NotMovable`
- `Fatigued`
- `MissingBodyPart(...)`
- `SourceEmpty`
- `TileOccupied`
- `AlreadyFullHealth`
- `NotYourRoom`
- `InvalidTerrain`
- `TooManyConstructionSites`
- `NotYourSpawn`
- `BodyTooLarge`
- `ExceedsRoomCapacity`
- `AlreadyHacked`
- `TargetEmpty`
- `CarryFull`
- `FriendlyTarget`
- `NotFriendly`
- `InvalidDamageType`
- `AlreadyDebilitated(...)`
- `MainActionQuotaExceeded`
- `TickValidationFailed`

这不是单纯命名风格问题，而是 wire 合同冲突：一个实现可能把这些作为 enum 输出，另一个实现可能按 YAML 归并到 35 个 canonical code + debug_detail。跨节点同一非法命令的输出、TickTrace、replay verifier 都可能不一致。

建议：02-command-validation 必须改为只引用 YAML 的 35 个 canonical code；以上细分原因应映射到 canonical code，并写入 `debug_detail`。需要一个显式 mapping 表，例如 `NotMovable -> SchemaViolation/ObjectNotFound? + debug_detail=NotMovable`，`Fatigued -> CooldownActive + debug_detail=Fatigued` 等，避免实现者自由解释。

### T2 — HIGH — WASM output 超限语义冲突：截断前缀 vs 整批丢弃

同一类输入在不同文档中有两种互斥语义：

- `specs/core/01-tick-protocol.md` §8.2：COLLECT Output JSON 256KB，超限行为为“截断（保留前 256KB）”。
- `specs/core/01-tick-protocol.md` §9.7：WASM `tick()` 输出超出 256KB 时“整批丢弃——不保留部分解析的前缀”。
- `specs/core/02-command-validation.md` 与 `specs/core/04-wasm-sandbox.md` 也倾向于“超限/畸形直接丢弃全部输出”。

这会直接影响 replay determinism：如果一个节点截断后恰好形成可解析 JSON 前缀，而另一个节点整批丢弃，则该玩家本 tick 的 command set 不同，后续 world state 分叉。

建议：统一为“整批丢弃”，禁止 prefix truncation；若需要保留审计预览，只能保存 `command_hash + truncated preview`，不得参与执行。

### T3 — HIGH — status_advance_system 调度位置在 command-validation 与 manifest/tick contract 中冲突

权威 manifest 与 tick protocol 定义：

- `06-phase2b-system-manifest.md`：S10 regeneration 在 combat/damage 前；S16–S22 status effects 在 S15 damage_application 后；S22 status_advance_system 位于 Status Effects Parallel Set B。
- `01-tick-protocol.md` §9.6 同样将 `status_advance_system` 放在 damage_application 后的 status effects 阶段。

但 `02-command-validation.md` §3.19 写成：

```text
death_mark → spawn → spawning_grace → combat → status_advance → (regeneration, decay 并行) → death_cleanup
```

并声明 status_advance 在 `combat_system` 之后、`regeneration_system` 之前。

这是状态机顺序冲突，不是文档措辞问题。Hack stage、Overload 恢复、Fortify duration、Debilitate duration 与 regen/damage 的相对顺序都会改变 tick 输出状态。若实现者按 02 与按 06 实现，跨节点同 tick 结果可能不同。

建议：02-command-validation 应删除本地 schedule 重述，改为只引用 06 manifest；如果保留摘要，必须与 S07–S29 完全一致。

### T4 — HIGH — TickTrace/replay 完整性语义在 tick protocol 与 persistence contract 中冲突

`01-tick-protocol.md` §9.4 和 §6.3.4 强调 TickTrace 与 world state/FDB 状态在同一事务中，不允许“状态成功但审计缺失”；甚至写明 TickTrace 写入失败 = tick 放弃，不存在成功 tick 的 replay/audit 缺口。

但 `05-persistence-contract.md` 定义 D5/B async object store 模型：

- FDB commit 成功即 tick 持久化完成。
- TickTrace blob 异步上传，失败 3 次后 `upload_status = failed`。
- world state 完整但 replay 不可用，terminal_state 可为 `audit_gap`。

这两种语义不能同时成立。一个实现按 01 会在 TickTrace blob 不可写时放弃 tick；另一个按 05 会提交 tick 并标记 replay gap。两者对 tick_counter、state_checksum、fuel refund、replay verifier 的行为都不同。

建议：选择一个权威模型。若接受 05 的 async 模型，则 01 必须改写为“FDB manifest/hash 与 state 同事务；大型 TickTrace blob 可异步失败并产生 audit_gap”，并清除“不存在状态成功但审计缺失”的绝对表述。若坚持 01 的强 replay 完整性，则 05 的 async blob failure 不得产生 committed tick。

### T5 — MEDIUM — YAML/registry 作为权威 limits 与 engine/command-validation 的容量数字仍漂移

R18 目标是验证单源是否闭合。直接 YAML→registry 闭合，但其他允许文件仍有权威数字冲突：

- Worker pool max：YAML/registry 为 `worker_pool_max: 256` / “max_pool 默认 256”；`design/engine.md` 推导中写 `MAX_POOL = 1000（hard cap，编译期常量）`。
- Per-player drone cap：YAML/registry 为 500；`02-command-validation.md` §6 硬性边界写 `MAX_DRONES_PER_PLAYER = 50`，且描述为 Tier 1 容量目标。
- Tick output batch size：02 前文/YAML/wasm sandbox 使用 256KB；02 §6 批级校验又写“整批（tick 输出）≤ 1MB”。

这些漂移会造成 admission、snapshot/output budget、spawn validation 在不同实现中的硬上限不同。即使 YAML 是机器源，设计文档中的重复数字仍会诱导实现分叉。

建议：非 registry 文件不要重新声明这些 hard limit；改为引用 `api-registry.md §5` 或 YAML key 名。若确实需要示例值，应标注“引用自 registry，不是权威”。

### T6 — MEDIUM — IDL/API 暴露 `f64`，与确定性合同“禁用 f64”存在边界不清

`01-tick-protocol.md` §7.1 明确：数值使用整数 + 定点数，禁用 `f64`。但 YAML IDL/API 输出 schema 中仍有多处 `f64`：

- `swarm_get_resources.income_rate`
- `swarm_get_path.distance/cost`
- `swarm_get_controller.progress`
- `swarm_get_economy.income/expenses/storage_tax/maintenance`
- `swarm_get_drone_efficiency.efficiency`
- `swarm_simulate.confidence`
- `resources/read.base_value`

如果这些字段只是展示层派生值，且不进入 WASM snapshot、Command validation、TickTrace state_checksum、Replay deterministic compare，则风险较低；但当前 IDL 未明确 replay class 下的数值编码边界。尤其 `swarm_get_path`/host path cost 容易被玩家策略使用；不同平台浮点舍入差异会变成隐式非确定性输入。

建议：IDL 层统一改为 fixed-point（如 `i64 basis_points`、`u64 micro_units`、`cost_milli`），或在每个 `f64` 字段上标注“presentation-only, excluded from deterministic state/replay/WASM input”，并禁止 WASM host ABI 返回浮点。

## 3. 亮点

- YAML IDL 已经成为直接 API registry 的强机器源。脚本核对显示：CommandAction 19 ↔ registry 19、RejectionReason indexed 35 ↔ registry 35、active MCP tools 46 ↔ registry 46、Host Functions 5 个 ABI 签名完全一致。
- `TickTrace Envelope` 已纳入 `system_manifest_hash`、`limits_manifest_hash`、`canonical_codec_version`、`visibility_truncation_version` 等版本字段，这对 replay verifier 判定“同一合同下执行”很有价值。
- Phase 2b manifest 采用 stable system IDs、manifest hash、R/W matrix、RoomCap 中间态保护、StableEntityId/canonical key 迭代顺序，方向正确。
- RNG 设计有 domain separation：shuffle、combat、loot、npc_spawn、event 均从 world_seed/tick/entity/room 等确定性输入派生，且明确不用 OS 熵源。
- WASM sandbox 禁用 clock/random/filesystem/network/env/process/threads/relaxed SIMD，并以 fuel metering + clean Store reset 约束玩家代码，能有效减少隐式非确定性源。
- Snapshot truncation 设计使用 priority bucket + stable entity_id / deterministic sort key，明确不依赖 ECS query 原始顺序，这是确定性视角的关键修正。

## 4. CrossCheck

### 4.1 YAML ↔ api-registry.md 直接生成核对

在只读指定文件的约束下，我用脚本抽取 YAML 与 registry Markdown 的核心集合，结果如下：

| 项 | YAML | api-registry.md | 差异 |
|---|---:|---:|---|
| CommandAction | 19 | 19 | 无 |
| RejectionReason indexed canonical codes | 35 | 35 | 无 |
| MCP active tools | 46 | 46 | 无 |
| Host Functions | 5 | 5 | 名称与 ABI 签名无差异 |

补充观察：YAML 中 RejectionReason 总条目为 37，其中 `InvalidJson`、`SchemaViolation` 是 pipeline-level、无 index；registry 也将它们列为 pipeline 级、不计入 35 indexed enum。这个处理在 YAML↔registry 两端一致。

### 4.2 单源闭合核对

直接生成链路通过，但更广义的“单源闭合”未通过：

- YAML/registry 的 canonical rejection enum 未被 02-command-validation 严格消费。
- YAML/registry 的 limits 未完全替代 engine.md、02-command-validation 中的重复 hard-coded 数字。
- 06 manifest 的调度权威性仍被 02-command-validation 的本地 schedule 重述破坏。
- 05 persistence 的 async TickTrace blob 模型未同步到 01 tick/replay 完整性语义。

### 4.3 State Machine Gaps

- Room 状态机本身有五态定义，但 contested/reserved/abandoned 的精确 tick-by-tick transition guard、tie-break、simultaneous claim ordering 仍依赖 command order 与 controller systems 的组合解释；建议在 manifest/command validation 中只保留一处权威 transition table。
- Spawn 生命周期的“Phase 2a 扣费/入队、Phase 2b 创建、失败 refund”方向清晰，但 PendingSpawn 创建失败的完整状态枚举与 rejection/refund trace 字段仍需从 YAML/registry 注册，避免只存在 prose。
- Special attack 状态机受 T3 调度冲突影响，当前不能认为完全闭包。
- Tick commit/retry 状态机受 T4 持久化语义冲突影响，当前不能明确判断 successful tick 是否允许 replay blob 缺失。

### 4.4 Non-Determinism Sources

- 未注册 rejection variants：不同实现可能输出不同 wire code。
- WASM output 超限：prefix truncation 与 whole discard 两种行为会产生不同 command set。
- `f64` API/IDL 字段：若进入 WASM input、pathfinding result、simulate trace 或 replay compare，会引入跨平台舍入风险。
- 文档重复 hard limit：worker_pool、drone cap、output JSON cap 的漂移会导致 admission/validation 分叉。
- Persistence async blob：若 replay verifier 对 `audit_gap` 的处理不统一，会出现“状态可验证但审计不可验证”的节点间解释差异。

## 5. 结论

R18 已解决“YAML 与生成 Markdown 表格是否同步”的表层问题；这部分可以认为基本通过。但从确定性评审角度，系统尚未达到“所有执行者只从一个机器事实源推导相同行为”的标准。建议在进入实现前先完成：

1. 02-command-validation 的 rejection code 全量 canonical mapping；
2. 01/02/04 对 WASM output 超限语义统一为整批丢弃；
3. 02 删除或修正与 06 冲突的 status_advance schedule；
4. 01 与 05 对 TickTrace async blob/audit_gap 语义二选一；
5. limits 只从 YAML/registry 引用，不在其他文档重复声明硬数字；
6. 将 determinism-facing `f64` 字段改为 fixed-point 或明确排除在 replay/WASM deterministic input 外。
