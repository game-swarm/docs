# R23 Phase 1 Clean-Slate 架构评审 — GPT-5.5

## Verdict

CONDITIONAL_APPROVE

方向是成立的：Swarm 当前架构抓住了可编程 MMO RTS 的关键不变量——所有玩家统一走 WASM、tick 可回放、ECS 调度显式化、持久化把 replay-critical 与 rich/debug 分层。它不像“先搭玩法再补确定性”的高风险游戏服务器，而更接近 FoundationDB simulation / deterministic replay / event-sourced game loop 的成功范式。

但我不建议直接进入大规模实现。当前设计已经从“概念架构”推进到“准实现规范”，最大风险不在单个技术选型，而在多个权威文档之间仍存在少量互相打架的合同、过早并行化带来的隐式复杂度，以及若干看起来合理但实现时容易炸的边界。建议按下方 Phase Ordering 先收敛合同，再写核心最小闭环。

## Strengths

- 统一执行路径正确：人类与 AI agent 都生成/部署 WASM，MCP 是管理与部署界面而不是旁路 gameplay executor，避免了 Screeps 类系统常见的“人类脚本与 bot 通道不公平”问题。
- Tick 三阶段模型直观：COLLECT / EXECUTE / BROADCAST 的边界清晰，WASM 只读快照、Phase 2a inline apply、Phase 2b deferred systems 的职责总体可解释。
- 确定性意识强：固定排序键、manifest hash、integer/fixed-point、IndexMap、禁用 f64、记录 commands 而非重跑 WASM，都是正确方向。
- 持久化分层方向成熟：FDB 只承载小型权威记录，对象存储承载大 blob，replay-critical subset 明确，比“FDB 事务内写一切”更可落地。
- System manifest 是高价值设计：29 systems、R/W 矩阵、RoomCap 中间态保护、manifest hash 入 TickTrace，可以把 ECS 调度从口头约定变成 CI 可验证合同。
- 资源预算开始形成闭环：sandbox fuel、host function、snapshot cap、pathfinding fair-share、deploy activation 都有初步预算和失败语义。

## Concerns

A1. High — API Registry 自身存在权威计数不一致，会削弱“单事实源”可信度。

`api-registry.md` 开头声明 Game API 工具为 54 个、Auth 11 个，但 changelog 又写 MCP tools 总数为 56 active。对于声称由 IDL 自动生成、所有 API 合约单一权威的文档，这类小数字冲突不是表面 typo：它会让后续 codegen、CI check、SDK 文档、新人理解都不知道该相信哪一列。架构上建议把“Registry 生成物不可手改”落到 CI：生成后 diff 必须为零，并增加统计断言。

A2. High — TickTrace / persistence 的 terminal_state 语义在多处冲突。

`engine.md` 与 `api-registry.md` 使用 Success/FuelExhausted/TimeoutExceeded/SnapshotOverBudget/CommandBufferFull/InternalError/NotExecuted 这类执行终端状态；`05-persistence-contract.md` 又定义 verified/audit_gap/unreplayable/reconstructable 作为 blob 损坏/审计恢复状态；同一字段名 `terminal_state` 同时承载执行结果与审计完整性，会在 replay verifier、玩家错误反馈、审计 UI 中造成语义混淆。建议拆成 `execution_terminal_state` 与 `audit_integrity_state`，并在 TickTrace envelope 中明确二者生命周期。

A3. High — Phase 2a/2b 特殊攻击路径仍显得过度复杂且有调度冲突味道。

Manifest 中 S14 special_attack_reducer 写 `StatusState`，S16-S22 又把各 status system 和 `status_advance_system` 放入同一 parallel set；同时 Unique Writer Contract 又说所有状态唯一 writer 是 S22。文档试图修补“多路径写状态”的失败模式，但当前描述仍让实现者可能写出两套路径：各 attack system 自己推进状态、S22 再推进一次。建议简化为：Phase 2a 只产生命令结果 / intents；S14 只做 canonical merge；S22 单点 apply+advance；S16-S21 若保留，只能是纯派生计算且不得写状态，或者干脆从 manifest 移除。

A4. High — 快照截断策略跨文档不一致，会直接影响 replay 与玩家策略。

`engine.md` 说 priority bucket 是自机、友方 drone、敌方 drone、建筑、NPC、资源并按 stable entity_id；`01-tick-protocol.md` 又说关键桶 Spawn/Controller/depot，随后按距离排序的高/中/低优先桶。两者都合理，但不能同时为权威。Snapshot truncation 是玩家可观察 API，也是 anti-abuse 与 determinism 的交界点。若实现者按不同文档写 SDK、server、replay，玩家会看到不可解释的 omitted entities。建议抽出 `SnapshotTruncationManifest`，让 registry 只引用 manifest hash。

A5. Medium — FDB 单 tick 提交模型低估了“全世界单事务”的容量/热点风险。

文档已经避免大 blob 入 FDB，这是正确的；但 500-1000 active players、10k drones、50k entities 下，即便每 tick 只写 delta + manifests，热点 key、conflict range、versionstamp ordering、watch/read amplification 都可能让 FDB 成为串行瓶颈。当前说“单 Engine + FDB 单一提交保证一致性”是 MVP 可接受，但需要显式定义 tick write-set 上限、keyspace sharding、conflict range 最小化策略，否则会重演许多 event-sourced MMO 后端的“理论 ACID，实际热点写爆”问题。

A6. Medium — Worker pool 的“每玩家 worker”与 256/1000 pool 推导需要收敛。

`04-wasm-sandbox.md` 架构图写 Sandbox Worker 进程（每玩家），但 `engine.md` 又说 worker_pool_size = min(max_pool, active_players)，默认 256，500 玩家时每 worker 约处理 2 个玩家。二者不是不能兼容，但命名会误导新人：到底是 per-player long-lived worker，还是 pooled worker running multiple players over time？这会影响 cgroup 归属、缓存键、内存残留风险、日志归因。建议改成“pooled isolated worker process；每次 tick 绑定一个 player execution context”。

A7. Medium — Seed rotation 的安全叙述不够自洽。

文档承认 `new_seed = Blake3(old_seed || tick)` 在泄露当前 seed 后可推导未来 seed，然后用定期轮换限制窗口。但这个算法本身不会限制未来窗口，除非后续 rotation 引入外部管理员 epoch bump 或预先密封的 seed schedule。若坚持 deterministic replay，不代表不能使用预提交 seed chain / delayed reveal / HSM-sealed epoch schedule。当前方案可作为 MVP，但不应称为有效窗口限制。建议把“周期轮换”降级为组织流程，或设计不可由当前 seed 推导未来 epoch 的 seed commitment。

A8. Medium — 文档中仍有旧错误码/旧 action 名称残留，说明合同未完全收敛。

`02-command-validation.md` 仍出现 `TileBlocked`、`StillSpawning`、`ExceedsRoomCapacity`、`MainActionQuotaExceeded`、`InvalidDamageType`、`AlreadyDebilitated`、`SourceEmpty` 等非 registry canonical code；同文件又说这些只是说明性名称，具体放 debug_detail。对实现者来说，这会诱导 wire enum 分叉。建议所有表格的失败码列只允许 canonical code，非 canonical 条件统一写到 `debug_detail_condition` 列。

A9. Medium — “Build inline 创建结构”与 entity creation flush 规则存在潜在冲突。

Manifest S03 写 Build 可 immediate inline 创建 structure，后文 Entity Creation 又说所有新实体追加到 `pending_entities`，当前 tick 所有 system 完成后 flush。若建筑是否同 tick 可见影响后续 Transfer/Attack/Collision，就必须明确 Build 与 Spawn 是否采用不同实体可见性模型。否则会出现玩家 A 先 build wall、玩家 B 同 tick move 是否被挡住这类高争议判定。

A10. Low — 当前抽象层次略偏“全量最终态”，不利于 MVP 新人落地。

文档已经同时包含 World、Arena、Auth、Economy、Special Attacks、Object Store、WAL、Federation、Vanilla mods、Tournament。作为长期蓝图很好，但 Phase 1/Phase 2 的最小验证切片不够突出。新人会先被 29-system manifest 和 56-tool registry 淹没，而不是先实现 deterministic tick kernel。建议每份核心文档顶部增加 MVP slice / Later slice，明确哪些必须先实现，哪些只是合同预留。

## Missing

- 缺少一个真正权威的 `Determinism Compatibility Matrix`：哪些字段进入 state checksum、哪些进入 TickTrace hash chain、哪些只是 rich audit；现在散落在 engine、tick、persistence、registry。
- 缺少 keyspace schema：FDB 的 key layout、conflict range、tick head CAS、entity delta row 形状没有给出，导致“FDB 小事务”仍停留在原则层。
- 缺少 snapshot truncation 的机器可读 manifest：当前自然语言描述过多，难以让 server、SDK、replay verifier 共享同一算法。
- 缺少最小 playable vertical slice：例如 Move/Harvest/Transfer/Spawn + 3 个 ECS systems + FDB commit + replay verifier，作为实现顺序锚点。
- 缺少“文档权威层级”校验规则：虽然很多文件说自己是权威，但冲突时到底 IDL、registry、manifest、spec 哪个赢，需要统一写入 README 并由 CI 检查。

## CrossCheck — 需要跨方向检查

- CX1: `terminal_state` 同时表示 WASM 执行状态与审计/blob 完整性，可能造成安全审计误判 → 建议 Security 检查 replay audit、incident response、玩家可见错误码是否会泄露或混淆。
- CX2: MCP 工具数量、RejectionReason、CommandAction 的 registry 统计不一致 → 建议 Architect 检查 IDL/codegen/registry 的单事实源链路与 CI 生成策略。
- CX3: Snapshot truncation bucket 规则跨文件不同，可能影响 fog-of-war 与策略公平 → 建议 Security 检查 truncation 是否产生 oracle 或可被实体膨胀攻击操纵。
- CX4: Special attack reducer 与 status systems 的多路径写入风险 → 建议 Architect 检查 ECS R/W 矩阵是否能由静态分析真实验证，而不是仅文档声明。
- CX5: Seed rotation 在 seed 泄露后的未来可预测性 → 建议 Security 检查威胁模型是否接受当前方案，或改为 seed commitment / epoch bump 机制。

## Phase Ordering

1. Contract Freeze：先修正 API Registry 统计、terminal_state 拆分、RejectionReason 表格、snapshot truncation 唯一权威，确保所有核心文档不再互相打架。
2. Deterministic Kernel：只实现最小 tick loop：COLLECT fixed snapshot、WASM dummy executor、canonical command sorting、Move/Harvest/Transfer/Spawn、state_checksum、replay verifier。
3. Persistence Slice：实现 FDB tick_head + manifest + command/rejection/fuel ledger，小事务提交与 commit failure restore；对象存储 rich blob 先 stub 为 local adapter。
4. Sandbox Hardening：接入 Wasmtime fuel、memory limit、host functions、恶意 WASM 样本库；先不引入复杂 special attacks。
5. ECS Manifest Enforcement：把 29-system manifest 转为机器可读配置或生成测试，CI 验证系统注册、R/W、顺序、manifest_hash。
6. Gameplay Expansion：在核心 replay 稳定后再引入 special attacks、economy ledger、global storage、arena/tournament，而不是同时实现。
7. Scale Validation：最后做 500-player synthetic benchmark、FDB conflict profiling、snapshot truncation abuse tests；用数据决定是否需要 room-level partition 或多 engine shard。
