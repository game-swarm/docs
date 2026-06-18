# R15 确定性评审 (GPT-5.5)

## Verdict

REQUEST_MAJOR_CHANGES

R15 明显比早期版本更重视确定性：有统一 Determinism Contract、TickTrace 原子性、Blake3 XOF RNG、IndexMap/禁用 f64/禁 std::HashMap、WASM 禁 clock/random、输出截断整批丢弃等关键原则。但当前设计仍存在多处会导致线上执行、回放验证、跨节点复现分叉的合同冲突。尤其是命令排序键、ECS system 顺序、预算上限、TickTrace/WAL 语义、room 状态机和特殊攻击状态机在不同章节中不一致，尚不能作为可实现的确定性权威规范。

## Strengths

- 明确提出 `tick(seed, state, commands) -> new_state` 型确定性目标，且回放以记录后的 `Command[]` 为输入，不重跑 WASM/LLM，避免 Wasmtime 版本变化影响普通回放。
- RNG 方向正确：使用 Blake3 XOF、domain separation、namespace 隔离、TickTrace 记录 seed epoch/活跃玩家集，避免 OS 熵源进入权威模拟。
- 明确规避常见非确定性源：禁用 `f64`、使用定点整数、禁 `std::HashMap` 迭代、WASM 禁 clock/random/filesystem/network/threads/atomics、relaxed SIMD 禁用。
- Phase 2a inline validate-and-apply 的 TOCTOU 合同清晰，基于当前 Bevy World 而非快照校验，资源竞争先到先得，可解释且可回放。
- Tick 原子性意识较强：FDB commit 失败时要求 Bevy World 显式 restore，COLLECT 结果跨重试复用，避免同 tick 重跑 WASM 产生新命令。
- Snapshot truncation 明确使用 stable key 而非 ECS query 原始顺序，这是高价值的确定性设计。

## Concerns

### T1 — Critical — 命令排序键存在跨文档冲突，会直接导致 replay/线上分叉

`01-tick-protocol.md` §9.1 定义全局排序键为：

`(priority_class, shuffle_index, sequence, source)`，且 source tie-breaker 为 `WASM > MCP_Deploy`。

但 `02-command-validation.md` §2.1 定义 sequence 是 per-(player, source)，并称全局排序键为：

`(priority_class, shuffle_order, source, sequence)`。

这两个顺序在同一玩家同 tick 内存在多个 source 且 sequence 相同/交错时会产生不同执行序。例如 WASM seq=2 与 MCP_Deploy seq=1，在一种合同下先按 sequence，在另一种合同下先按 source。由于 Phase 2a 是 inline apply，排序差异会改变资源竞争、所有权、冷却、refund、RejectionReason 和最终 state_checksum。

要求：选择唯一权威排序键，并在所有文档、TickTrace schema、validation pipeline、replay verifier 中统一。建议固定为 `(priority_class, shuffle_index, source_rank, sequence, command_hash)` 或 `(priority_class, shuffle_index, sequence, source_rank, command_hash)`，但必须明确同 source rank、同 sequence 的最终稳定 tie-breaker，避免稳定排序依赖输入容器顺序。

### T2 — Critical — ECS Phase 2b 权威顺序自相矛盾，部分并行声明与 20-system chain 不一致

`design/engine.md` 描述 Phase 2b 主线为 `death_mark -> spawn -> spawning_grace -> combat -> status_advance -> aging -> death_cleanup`，并称 regeneration/decay 与主线并行，仅需 before death_cleanup。

但 `01-tick-protocol.md` §3.4 给出的 Bevy 代码将大量系统放入 `.chain()`，顺序为：

`death_mark -> pvp_block -> spawn -> regeneration -> seed_rotation -> cargo_in_transit -> global_storage -> controller -> controller_repair -> depot_repair -> room_state -> combat -> decay -> memory_upkeep -> drone_env_var -> rhai_rule_module_tick_end -> death_cleanup -> onboarding`

同一文件 §9.6 又说必须 `.chain()` 的是：

`death_mark -> spawn -> spawning_grace -> combat -> status_advance -> aging -> death_cleanup`

`02-command-validation.md` §3.19 则说：

`death_mark -> spawn -> spawning_grace -> combat -> status_advance -> (regeneration, decay 并行) -> death_cleanup`

这些版本在 regeneration、decay、status_advance、aging、spawning_grace、NPC、RuleMod、controller repair 的相对位置上不一致。任何一个位置差异都会影响 HP、状态持续时间、资源再生、cooldown/fatigue、死亡清理、spawn grace 是否生效，从而影响 deterministic state。

要求：定义一个单一 “Phase 2b System Manifest” 作为权威，列出每个 system 的 reads/writes、必须前驱/后继、是否允许并行、对 DeathMark 的过滤规则。文档中的示例代码必须与该 manifest 完全一致。

### T3 — High — TickTrace 写入失败语义与 WAL 降级链互相冲突

`01-tick-protocol.md` §6.1 失败矩阵写道：`TickTrace write fail` 时 “tick 执行完成，审计不完整”，`Replay write fail` 可从 keyframe 重建。

但 §6.3.4 与 §9.4 又要求 TickTrace 与世界状态写入同一 FDB 事务，失败则 tick 放弃，不允许 “状态成功但审计缺失”。同时 §6.3.4 还引入本地 WAL：第 3 次写入本地 WAL，tick 不阻塞，并称 WAL 最坏延迟补齐。

这三套语义不能同时成立：

- 若 TickTrace 与 state 同事务，则 TickTrace 写失败应导致整个 tick rollback。
- 若 WAL 可承载 TickTrace 并允许 tick 继续，则 state 成功但全局审计不完整，和 §9.4 禁止状态成功审计缺失冲突。
- 若 Replay write fail 可从 keyframe 重建，则 TickTrace 不再是完整 replay 输入的唯一来源，需要定义可重建边界。

要求：二选一。若 deterministic replay 是硬合同，建议将 state delta、TickTrace manifest、chain hash、fuel 写入同一 FDB 小事务；对象存储/WAL 只能作为大 blob 后台复制层，但 FDB 内必须有足够 replay verifier 验证的 hash/pointer/command manifest。失败时 tick rollback，不允许“已成功但不可回放”。

### T4 — High — RNG 合同仍有隐式分叉点：seed rotation 时序、RNG offset、host random API 未闭合

文档声明 RNG namespace 使用 Blake3 XOF，且 per-entity stream seed 可由 `stream_name/world_seed/entity_id/tick` 派生。但仍缺少三个执行级细节：

1. `seed_rotation_system` 在 20-system chain 中位于 regeneration 之后、combat 之前，但排序 shuffle seed、combat seed、loot seed、event seed 分别使用旧 seed 还是新 seed 未明确定义。
2. 对同一 namespace 内多次抽样，没有定义 draw index/offset 的稳定来源。若实现按 ECS iteration 顺序或 “调用到第几次” 消费 XOF，则新增系统、并行度、实体遍历顺序会改变后续随机流。
3. `WASM 代码必须使用 swarm_get_random(sequence)`，但 `04-wasm-sandbox.md` 的允许 host function 列表没有该函数；同时 §3.2 说 host function 全部只读且不计入指令预算但计 fuel，需要说明 random 是否可用、如何计费、是否依赖 player_id/source/sequence。

要求：所有随机事件都应采用 counter-based derivation，例如 `rng(namespace, world_seed_epoch, tick, actor_id/entity_id/room_id, event_kind, ordinal)`，而不是共享流顺序消费。明确 seed rotation 在 tick 边界生效：tick N 全部系统使用 epoch E，rotation 只写入 N+1 的 epoch。

### T5 — High — 状态机闭包不足：Room state、Hack/Neutral、Drain、Fortify/Disrupt、Spawn refund 缺少完整转移表

Room 状态机列出 `neutral/reserved/owned/contested/abandoned`，但缺少以下闭包定义：

- `reserved` 超时回 neutral 时 progress、controller entity、owner、claim lock 如何清理。
- `contested` 多于两个玩家同时 Claim 如何处理；表述只覆盖两个玩家。
- `contested -> reserved/owned/neutral` 的 tie、净 progress 同时归零、玩家退出/死亡、safe_mode 与 Claim 冲突未定义。
- `abandoned` 降级后是否仍保留 owner、建筑权限、repair_capacity、safe_mode/cooldown。

特殊攻击状态机也不闭包：

- Hack stage=5 转 Neutral 后 “5 tick 后自动恢复原 owner”，但若原 owner 已死亡/重生/房间失控如何处理未定义。
- Neutral 期间是否可被 Attack/Heal/Recycle/Drain/Disrupt/Claim 未逐项定义。
- Drain “持续期间每 tick 转移” 与 command model 的每 tick action slot 关系不清：是状态系统自动继续，还是每 tick 必须重新提交命令。
- Fortify 与 Disrupt 的同 tick 优先级表写了高优先级先执行，但 Phase 2a 全局排序同时又按 player shuffle 先到先得；两套优先级若都存在，需要明确是在排序 key 的 priority_class 中体现，还是在 command application 内二次排序。

要求：为每个多 tick 状态提供完整 transition table：状态、触发、guard、effect、next_state、duration/counter 更新、同 tick 多事件 tie-breaker、死亡/despawn/owner change 时清理规则。

### T6 — Medium — 预算和上限数字跨文档不一致，导致不同实现拒绝边界不同

发现的合同冲突包括：

- `Commands per player per tick` 在 `engine.md` 为 max 1000，`02-command-validation.md` schema 为 maxItems 100，文字为 MAX_COMMANDS_PER_PLAYER 500，硬边界表也是 500。
- tick 输出上限在 `02-command-validation.md` §1.1 为 256KB，但 §6 批级校验写整批 ≤1MB；`01-tick-protocol.md` §8.2 又说 output JSON 256KB 截断，§9.7 说超出整批丢弃。
- COLLECT timeout 在 `01-tick-protocol.md` §2.2 是 2500ms，tick 状态机 EXECUTE 超时写 500ms，§8 又说 EXECUTE 不单独超时，由总预算控制。
- sandbox cgroup CPU 在 `04-wasm-sandbox.md` §4.2 为 `250000 3000000`，§9.2 checklist 为 `50000 100000`。
- pids.max 在 §4.2 为 32，§9.2 为 16。
- `MAX_DRONES_PER_PLAYER` 在 engine 容量表默认 100，validation 硬边界表默认 50。

这些数字若被不同组件引用，会产生 “同输入在 A 节点 accepted、B 节点 rejected” 的跨节点非确定性。

要求：建立单一 `Limits Manifest`，所有文档只引用该 manifest；明确每个超限行为是 “整批丢弃”、“截断”、“拒绝单条”、“deterministic fail” 之一。

### T7 — Medium — Snapshot truncation 的排序合同仍有不稳定字段

`engine.md` 说 priority bucket 顺序为：自机 > 友方 drone > 敌方 drone > 建筑 > NPC > 资源，同桶 stable entity_id。

`01-tick-protocol.md` §2.3 说：关键桶 Spawn/Controller/depot/storage，无条件保留；高优先按距离排序己方 drone/建筑；中优先敌方可见实体/资源点；低优先友方/中立；同桶 `(distance_to_drone, entity_id)`。

差异包括：友方位置、建筑位置、资源点位置、关键桶是否无条件保留、距离_to_drone 在玩家有多个 drone 时如何定义。若多个 drone 共享玩家 snapshot，`distance_to_drone` 是 min distance、每 drone 独立 snapshot、还是某个主 drone？未定义会使截断结果分叉。

要求：定义 canonical visibility/truncation algorithm，包括多 drone 玩家距离函数、bucket enum ordinal、关键桶超出 256KB 时的处理、序列化 size 的 canonical 编码，以及 omitted_counts 的确定计算。

### T8 — Medium — Bevy EntityId / 创建顺序若作为稳定排序键，需要跨回放保证

多处使用 `entity_id` 作为 stable order 或 RNG seed 输入。若 EntityId 来自 Bevy 内部分配，despawn/reuse、不同 spawn 批处理顺序、rollback restore 后 allocator 状态、并行 spawn 都可能改变 EntityId。

要求：区分 engine-internal Entity 与 deterministic `StableEntityId`。所有排序、RNG、TickTrace、snapshot truncation、Command target 均使用 `StableEntityId`，其分配由 `(tick, creator, spawn_sequence/global_counter)` 或 FDB monotonic allocator 确定，并纳入 Bevy snapshot/restore 范围。

### T9 — Low — CI 故障注入示例本身有确定性断言错误，可能误导实现

`fdb_commit_failure_restores_snapshot_consistency()` 示例中 `snapshot_checksum_before` 在 loop 外定义，却在失败时与当前 tick 前 snapshot restore 后状态比较；示例代码还在不可变变量上重新赋值。概念上应比较 `world.restore(snapshot)` 后的 checksum 与该 tick 的 `snapshot_checksum`，而不是初始或上一次成功 checksum。

要求：修正文档示例，避免测试模板被照抄后产生假阳性/假阴性。

## State Machine Gaps

- Room 状态机缺少多玩家 Claim、tie、超时、owner 消失、safe_mode 交互、progress 清零/继承、abandoned 中间态权限的完整转移表。
- Tick 状态机缺少 COLLECT crash、Phase 2a panic、FDB conflict、TickTrace write fail、process crash 在同一状态图中的单一权威路径；当前失败矩阵与 TickTrace 原子性章节冲突。
- Phase 2b system 状态推进没有单一 manifest；不同章节给出不同顺序，状态持续时间和 cleanup 时点无法证明一致。
- Hack/Drain/Overload/Debilitate/Fortify/Disrupt 缺少统一状态表，尤其是同 tick 优先级与全局命令排序的组合规则。
- Spawn pending/body_cost refund/room cap release/DeathMark 的中间态虽有局部说明，但没有覆盖 spawn_system 创建失败、spawn entity 死亡、rollback restore、refund 容量不足等完整路径。
- Deploy 生效状态机只覆盖 N 到 N+1，未覆盖编译失败、签名撤销、security_epoch 变化、degraded mode 暂停 MCP_Deploy 时入队 deploy 如何处理。

## Non-Determinism Sources

- 排序键冲突：`(sequence, source)` 与 `(source, sequence)` 文档分叉是最高优先级非确定性源。
- ECS 调度冲突：`.chain()` 示例、并行系统声明、status_advance 位置不一致，会导致不同实现合法但输出不同。
- RNG 流消费顺序：若使用 XOF 顺序读取而非 counter-based draw key，系统插入、并行度或实体遍历顺序会改变随机结果。
- Seed rotation 时序：rotation 在 tick 内执行但未定义哪些系统使用旧 seed/新 seed。
- Hash/Map/iteration：文档禁 std::HashMap 是正确方向，但仍需覆盖 Bevy query order、IndexMap 插入顺序来源、serialization map key order。
- Floating/SIMD：禁 f64 和 relaxed SIMD 正确；但 World 默认 SIMD enabled 需要限定只允许 deterministic SIMD 指令集，并要求 cross-arch replay CI。
- 系统时间/墙钟：WASM clock 禁用正确；但 collect timeout/wall-clock 影响哪些玩家输出被采纳。跨节点 replay 不应重跑 COLLECT，因此在线多节点共识若存在，需要定义 timeout 裁决权威节点或记录 timeout decisions。
- FDB retry/backoff：1s backoff 是墙钟行为，不影响 replay，但若同 tick 重试期间外部 admin/deploy 事件进入，需要明确事件有效 tick，否则同一 tick 输入集合可能变化。
- EntityId 分配：若依赖 Bevy 内部 EntityId 或并行 spawn 顺序，会污染排序、snapshot truncation、RNG seed。
- JSON serialization：snapshot size/truncation 依赖 `serialized_size`，必须定义 canonical JSON/二进制编码、字段顺序、字符串 escaping，否则不同 serde 配置导致截断边界不同。

## CrossCheck — 需要跨方向检查

- CX1: TickTrace/WAL 与 FDB 同事务语义互相冲突 → 建议 Architect 检查持久化架构是否能同时满足事务大小、审计完整性、对象存储大 blob 分层。
- CX2: WASM sandbox 中 `swarm_get_random(sequence)` 未出现在允许 host function 列表 → 建议 Security 检查是否应暴露确定性 RNG host API，以及该 API 是否会泄露 world_seed 或被用作 covert channel。
- CX3: `sandbox.relaxed=true` 允许 clock_gettime 但称“引擎仍覆盖返回值” → 建议 Security 检查 seccomp/WASI 层是否真的能在允许 syscall 时保证返回确定值。
- CX4: Seed rotation 的前向保密设计把 world_seed 视为 TLS 私钥级秘密 → 建议 Security 检查运维密钥管理、日志脱敏、seed bump runbook 是否足够。
- CX5: Snapshot truncation 可能被实体膨胀攻击影响玩家可见信息完整性 → 建议 Gameplay/UX 检查 omitted_counts、bucket 优先级是否给玩家足够可解释性且不破坏公平。
- CX6: Room state 与 Claim/contested 规则影响领土战略和新手保护 → 建议 Gameplay 检查多玩家争夺、safe_mode、abandoned 降级是否符合预期玩法。
- CX7: World 默认 SIMD enabled、Arena 默认 SIMD disabled → 建议 Architect/Performance 检查跨架构 deterministic replay CI 能否覆盖 x86_64/aarch64，不应只在 Arena 禁 SIMD。

## Required Fixes Before Approval

1. 发布单一 Determinism Contract 附录，权威定义排序键、RNG derivation、ECS manifest、limits manifest、canonical serialization、StableEntityId。
2. 删除或改写所有与权威合同冲突的旧段落，尤其是命令排序、Phase 2b 顺序、TickTrace write fail、输出大小限制。
3. 为 Room、特殊攻击、Deploy、Tick failure 提供完整状态转移表，覆盖所有 terminal/rollback/timeout/despawn/owner-change 路径。
4. 将 replay verifier 输入封套扩展到足以重建：seed_epoch、active_player_set、sorted command list、system manifest version、limits manifest version、world_config/mods lock、canonical codec version、state_checksum chain。
5. 增加跨节点 determinism CI：同一 TickInputEnvelope 在不同线程数、不同 Bevy schedule executor、不同 CPU 架构、不同 map insertion order 下产生相同 state_checksum。