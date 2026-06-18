# R17 Determinism Review — GPT-5.5

## Verdict

REQUEST_MAJOR_CHANGES

R17 相比 R15/R16 有明显进步：Phase 2a/2b 执行清单、Bevy snapshot restore、COLLECT buffer reuse、TickTrace/FDB/Object Store 分层、RNG domain separation 都比前轮更接近可回放闭包。但本轮目标是验证“权威单一来源是否真正闭合”；从确定性视角看，闭包仍未成立。核心原因不是缺少理念，而是多个白名单文档之间仍存在会导致实现分叉的权威冲突：IDL 与 Markdown registry 版本不一致、CommandAction/RejectionReason 未闭合、特殊攻击系统调度互相矛盾、输出大小/截断语义互相矛盾、时间与 RNG 暴露合同仍有非确定性入口。

## Strengths

- Phase 2b manifest 已把 29 个系统、Stable IDs、R/W 矩阵、RoomCap 中间态约束、SpawningGrace/filter、manifest_hash 进入 TickTrace 等关键确定性机制集中到一个文件，方向正确。
- Tick 原子性比前轮完善：FDB commit 失败时显式 `world.restore(snapshot)`，COLLECT 结果跨 retry 复用，fuel 不重复扣费，避免了 commit retry 重新执行 WASM 的非确定性。
- Persistence contract 明确 FDB 只保存 manifest/hash/pointer，大对象先写对象存储再以 FDB commit 为唯一权威提交点，孤儿 blob 由 GC 清理，避免了“状态成功但审计缺失”的常见双写陷阱。
- 快照截断、命令排序、状态 checksum、整数/定点数、IndexMap/禁 std::HashMap、禁 f64 等确定性设计原则都有明确文本支撑。
- WASM sandbox 明确关闭 WASI clock/random/filesystem/network，并以 fuel metering、epoch interruption、per-tick Store reset 控制跨 tick 状态污染。

## Concerns

### T1 — High — `game_api.idl.yaml` 与 `api-registry.md` 的权威事实源未闭合

`api-registry.md` 明确声明机器可读权威源是 `game_api.idl.yaml`，冲突时以 YAML 为准；但两者在基础版本上已经不一致：Markdown 写当前 API 版本 `0.1.0`，IDL 写 `api_version: "0.2.0"`。同一批 TickTrace 字段也存在文档口径差异：engine.md 叙述 `collect_id/attempt_id/commit_id/terminal_state`，registry/IDL 的 TickTrace Envelope 仍固定 `total_fields: 22`，且未包含这些字段。

这会直接破坏 replay/verifier 的跨节点合同：节点 A 若按 IDL codegen，节点 B 若按 Markdown/engine 文本实现，`api_version`、envelope hash、canonical codec 输入都可能不同。要求将 IDL 作为唯一可生成源，Markdown 只能生成，不得手写版本、字段数、字段清单；并将 `collect_id/attempt_id/commit_id/terminal_state/seed_epoch/active_player_set` 等 replay 必需字段纳入同一 IDL 或明确迁移到另一机器源。

### T2 — Critical — `RejectionReason` 仍未闭合，validation 大量使用未注册错误码

权威 registry/IDL 声称 `RejectionReason` 共 35 个变体，但 `02-command-validation.md` 的逐指令矩阵和竞争规则继续引用大量未注册码，例如 `NotMovable`、`Fatigued`、`MissingBodyPart`、`TileBlocked`、`SourceEmpty`、`TargetFull`、`TargetEmpty`、`NotYourRoom`、`TileOccupied`、`InvalidTerrain`、`TooManyConstructionSites`、`FriendlyTarget`、`NotFriendly`、`NotYourSpawn`、`BodyTooLarge`、`ExceedsRoomCapacity`、`AlreadyHacked`、`InvalidDamageType`、`AlreadyDebilitated`、`MainActionQuotaExceeded`、`TickValidationFailed` 等。

这不是命名小问题，而是确定性合同破口：同一非法 command 在不同实现中可能映射到不同 rejection enum、不同 refund、不同 player/admin trace、不同 TickTrace hash。尤其 refund 表又依赖 `SourceEmpty/TileOccupied/TargetFull` 等未注册码，导致 fuel ledger 也不闭合。必须使 IDL 的 rejection registry 覆盖 validation 中所有可达拒绝路径，或把 validation 文档改写为只使用已注册码，并用 CI 反向扫描所有规范文本与代码路径。

### T3 — High — CommandAction / Handler 覆盖关系仍有不一致

IDL/registry 定义 19 个 CommandAction，其中包含 `TransferToGlobal`、`TransferFromGlobal`、6 个特殊攻击和 `ClaimController`。但 manifest 的 Phase 2a handler 清单中 S01 只写 `Move/Harvest/Attack/RangedAttack/Heal/Claim`，S05 只写 `Transfer/Withdraw`，S06 只写 `Spawn`；未看到 `TransferToGlobal`、`TransferFromGlobal` 的 handler 归属。S02 又写 `Claim`/`UpgradeController`，而 IDL 是 `ClaimController`，且 `UpgradeController` 不在 19 个 CommandAction 中。

结果是 action enum、validation matrix、Phase 2a handler、resource ledger 四者不能证明穷举闭合。若某节点把 `TransferToGlobal` 当 S05 处理，另一节点把它当 custom/global subsystem 处理，同一 tick 的 resource ledger 和 state_checksum 会分叉。需要一张由 IDL 生成的 CommandAction → validator → apply handler → system_id → rejection set → ledger effect 的闭包矩阵。

### T4 — High — 特殊攻击调度位置在 `02-command-validation.md` 与 manifest/tick contract 中冲突

`06-phase2b-system-manifest.md` 规定 S10 regeneration 在 S15 damage_application 前，S16-S22 status effects 在 S15 后；`01-tick-protocol.md` §9.6 也复述该顺序。但 `02-command-validation.md` §3.19 仍写 `status_advance_system` 位于 `combat_system` 之后、`regeneration_system` 之前，并给出 `death_mark → spawn → spawning_grace → combat → status_advance → (regeneration, decay 并行) → death_cleanup`。

这会造成可观察分叉：Debilitate、Fortify、Overload、Hack stage、regen/damage 的先后会影响 HP、fuel、状态 duration 与死亡判定。manifest 自称唯一权威，但 validation 文档仍重新声明冲突顺序，说明单一权威未闭合。必须删除或改为引用 manifest，不允许在 validation 中保留第二套调度图。

### T5 — High — WASM 输出大小语义三处冲突，直接影响 replay 输入闭包

`02-command-validation.md` §1.1 写 tick 输出总字节数 ≤ 256KB，校验失败整个输出丢弃；`01-tick-protocol.md` §8.2 写 COLLECT Output JSON 256KB 超限行为是“截断（保留前 256KB）”；`01-tick-protocol.md` §9.7 又写超出时整批丢弃、不保留部分解析前缀。`02-command-validation.md` §6 批级边界又写整批 tick 输出 ≤ 1MB。

这四种口径会使同一个超大 WASM 输出在不同实现中产生：0 指令、前缀部分指令、schema failure、或完整进入管线。由于 commands_hash 是 TickTrace 核心输入，这属于 replay blocker。必须统一为单一语义；从确定性和安全角度建议采用“超过 256KB 整批丢弃，不读取/解析前缀”，并删除 1MB 批级上限或解释其与 256KB 的层级关系。

### T6 — Medium — RNG 合同仍有可推导输入缺口与命名冲突

文档有良好方向：shuffle seed 使用 `Blake3("shuffle" || world_seed || tick.to_le_bytes())`，namespace RNG 使用独立 domain；但仍有不闭合点。`engine.md` 的 per-entity stream seed 包含 `stream_name/world_seed/entity_id/tick`，`01-tick-protocol.md` §9.5 的 namespace 表对 `combat/event` 只写 `world_seed + tick`，未包含 draw index、entity ordering 或 target key；`01-tick-protocol.md` §7.1 又把排序键写成 `priority_class, shuffle_index, source_rank, sequence, command_hash`，但早前 §3.1 的 shuffle 伪码是 active_players 向量 shuffle，未规定 active_players 的 canonical sort 输入。

若 combat/event RNG 按“调用顺序 draw”消费，任何并行 reduce、entity iteration 或 command rejection 差异都会改变后续随机数。要求明确每个随机事件的 seed/key 必须由 stable event key 派生，例如 `(namespace, world_seed, tick, stable_entity_id, event_kind, ordinal)`，禁止依赖全局 PRNG mutable cursor；active_players 在 shuffle 前必须 canonical sort 并记录快照/hash。

### T7 — Medium — 浮点/时间类型仍泄漏到 API 与 TickTrace 表面

确定性章节声称禁用 `f64`，数值使用整数/定点；但 IDL/MCP output schema 仍包含 `income_rate: f64`、`distance: f64`、`cost: f64`、`progress: f64`、`income/expenses/storage_tax/maintenance: f64`、`efficiency: f64`、`confidence: f64`、`base_value: f64`。如果这些字段只读、非 TickTrace 输入，可接受但需标注为 presentation-only，不参与 canonical hash；如果 simulate/dry-run trace 或 SDK codegen 复用这些类型进入 deterministic comparison，就会出现跨平台差异。

时间方面，sandbox 禁用 clock，但 audit/admin/deploy/status 输出中有 `timestamp`、`deployed_at`、`expiry` 等 wall-clock 风格字段。它们必须明确不进入 tick deterministic state 或以 tick number/commit versionstamp 规范化，否则 replay checksum 可能混入系统时间。

### T8 — Medium — Persistence contract 与 tick protocol 关于 TickTrace 写入失败存在历史语义残留

`05-persistence-contract.md` 明确对象存储写入失败会导致 tick 放弃，FDB commit 成功才代表 tick 持久化完成；这是正确方向。但 `01-tick-protocol.md` §6.1 的 failure matrix 仍保留“TickTrace write fail: tick 执行完成，审计不完整，标记不可回放”和“Replay write fail: tick 执行完成，丢失 tick 后续从 keyframe 重建”等旧语义。稍后 §6.3.4 又改称 TickTrace 写入失败 = tick 放弃，不存在状态成功但回放数据丢失。

同一文档内部同时存在旧语义和新语义，会导致运维/实现按不同故障路径处理。必须删除 failure matrix 中“tick 成功但审计不完整”的路径，或将其严格限定为 BROADCAST/非权威展示日志，不可用于 TickTrace。

### T9 — Low — CI 故障注入示例自身有断言 bug，削弱规范可信度

`01-tick-protocol.md` 的 FDB 故障注入测试先记录 `snapshot_checksum_before = world.state_checksum()`，循环中每 tick 又创建 `snapshot = world.snapshot()`，commit 失败后却断言 `world.state_checksum() == snapshot_checksum_before`。如果 `snapshot_checksum_before` 未按 tick 前快照更新，示例可能把恢复到当前 tick 前状态误比到更早状态；代码片段还把不可变变量后续赋值。虽然这是文档示例，不是设计本体，但会误导实现测试。

## State Machine Gaps

1. Room state machine 未完全定义所有边：`contested` 如何在双方 progress 同时归零、三方以上 Claim、reserved timeout 与 abandoned/downgrade 同 tick 触发时决策；这些边缺少 canonical tiebreaker。
2. Tick failure state machine 有残留冲突：COLLECT crash、Phase 2a panic、FDB commit fail、TickTrace/object write fail 的 fuel/body_cost refund 与 retry/abandon 边需要统一到 persistence contract。
3. Deploy state machine 未闭合：`swarm_deploy` 编译/签名/入队在 tick N，N+1 生效；但同一玩家多次 deploy、commit retry、degraded mode 暂停 deploy、证书撤销/security_epoch 变化同 tick 发生时没有权威排序。
4. Special attack state machine 有两套顺序：validation 的 `status_advance` 位置与 manifest 不一致；同 tick Fortify/Disrupt/Debilitate/Hack/Drain/Overload 的 priority 与 S16-S22 parallel set 的实际写入顺序未完全统一。
5. Entity creation/despawn 可见性仍有缝隙：manifest 写所有新实体 pending 到 tick 末 flush，但 S08 spawn_system 又需要 S09 spawning_grace、combat filter 在同 tick 作用于新 drone；“pending 不可见”和“同 tick grace/combat 可见”需要精确定义哪些系统可见 pending_entities。
6. Refund/fuel ledger 状态机依赖未注册 rejection code，且 deploy-reset 例外 `same session_id` 未进入 IDL/TickTrace，replay 无法仅凭 recorded commands/state 判断 credit 是否应清零。

## Non-Determinism Sources

1. 未注册 rejection code 与 action handler 不闭合：不同实现可选择不同 enum 或 fallback，影响 rejections、refund、commands_hash/state_checksum。
2. WASM 输出超限处理冲突：截断前缀 vs 整批丢弃会直接改变 accepted command set。
3. RNG 若使用 namespace mutable cursor 或并行系统 draw order，会受 entity iteration/parallel scheduling 影响；需要 per-event key 派生而非顺序 draw。
4. Active player set shuffle 前的输入顺序未完全规定；任何 HashMap/DB scan/cache iteration 差异都会改变 player_order。
5. API schema 中 f64 输出若进入 canonical trace/simulate checksum，会受平台、编译器、NaN/rounding 影响。
6. Wall-clock 字段如 timestamp/deployed_at/expiry 若进入 authoritative state 或 TickTrace hash，会破坏 replay。
7. Bevy archetype/entity iteration 已被 manifest 原则禁止，但 validation/engine 文档仍有“按距离排序”“按 bucket 排序”等派生排序，需保证 tie-breaker 覆盖所有相等情况。
8. Object store ETag 若由具体后端生成且参与 canonical hash，会跨后端不同；persistence contract 应只用 content_hash 参与确定性验证，ETag 仅作诊断。
9. Simulate/dry-run 使用 assumptions/confidence 且输出 f64，必须标注为 non-authoritative，否则容易被 SDK 或 bot 策略当作 replay-safe deterministic trace。

## CrossCheck

- 权威单源：未通过。`game_api.idl.yaml` 与 `api-registry.md` 在 API version、TickTrace fields 上不一致，且 Markdown 仍包含手写权威表。
- CommandAction 闭包：未通过。19 个 IDL action 未能全部映射到 manifest handler；manifest 还引用不在 IDL 中的 `UpgradeController`/`Claim` 命名。
- RejectionReason 闭包：未通过。validation/refund 使用大量 IDL 未注册拒绝码。
- Tick(seed, state, commands) → new_state 闭包：接近但未通过。Phase 2b manifest、FDB retry、snapshot restore 是强项；但 special attack schedule、WASM output 超限、refund code、RNG draw key 仍可导致分叉。
- RNG 合同：部分通过。Blake3/domain separation 正确，但需要将所有 random event 改为 stable event-key 派生并记录 active player set canonical hash。
- 跨节点一致性：未通过。只要两个节点分别按 IDL、registry、validation 或 manifest 的不同文本实现，同 tick 仍可产生不同 command rejection、fuel ledger、status progression 或 trace hash。

## Required Fixes Before Approval

1. 以 `game_api.idl.yaml` 为唯一机器事实源，生成 `api-registry.md`；消除 API version、field count、CommandAction、RejectionReason 的手写分叉。
2. 建立 CI：扫描规范与代码中所有 `RejectionReason`/`CommandAction` token，任何未在 IDL 注册的使用直接失败。
3. 生成 CommandAction → validator → apply handler/system_id → rejection set → resource/fuel ledger effect 的穷举矩阵，并纳入 TickTrace/manifest hash。
4. 删除 `02-command-validation.md` 中与 `06-phase2b-system-manifest.md` 冲突的调度图；validation 只引用 manifest。
5. 统一 WASM output 超限语义为单一路径，并同步 `01/02/04/api-registry/IDL`。
6. 明确 RNG per-event stable key，不允许依赖全局 mutable draw cursor；active player set canonical sort/hash 必须写入 TickTrace。
7. 明确 f64/time fields 是否 presentation-only；任何进入 deterministic checksum 的数值必须整数/定点，任何时间必须 tick/versionstamp 化。
8. 清理 tick failure matrix 中“状态成功但 TickTrace/replay 缺失”的旧语义，使 persistence contract 成为唯一故障语义。
