# R16 Phase 1 Clean-Slate Review — Determinism (GPT-5.5)

## Verdict

REQUEST_MAJOR_CHANGES

R16 相比前轮已经显著加强确定性主轴：全局排序键、TickTrace envelope、system manifest hash、IndexMap/稳定排序、定点整数、WASM 无时钟/无随机源、FDB 原子提交与对象存储 hash chain 都是正确方向。但从 Determinism 视角仍不能批准：指定文件之间存在多个“权威定义”互相冲突，且若实现者按不同文档实现，会直接破坏 `tick(seed, state, commands) -> new_state` 的闭包与跨节点一致性。

核心问题不是缺少确定性意识，而是合同没有收敛到单一、可执行、可验证的规范。特别是 Phase 2b 调度、命令/错误枚举、输出大小/截断语义、commit 重试语义、RNG draw contract 仍会让线上执行、replay verifier、SDK/Gateway 产生不同解释。

## Strengths

1. 全局命令排序键已从模糊“玩家顺序 + sequence”提升为 `(priority_class, shuffle_index, source_rank, sequence, command_hash)`，并明确使用 Blake3 洗牌与 stable tiebreaker。
2. WASM 沙箱禁用 WASI clock/random/filesystem/network，并通过 fuel、epoch deadline、Store reset、host function 白名单降低隐式非确定性源。
3. 设计明确禁用 `std::HashMap` 迭代顺序、`std::hash`、`f64`，并要求 IndexMap、Blake3、整数/定点计算。
4. TickTrace envelope 覆盖 api/version/manifest/codec/visibility 等关键 replay 输入，方向正确。
5. FDB commit 与 TickTrace 原子性、对象存储 content hash、hash chain、orphan GC 的思路合理，能支撑审计与 replay 完整性。
6. Snapshot truncation 使用 priority bucket + deterministic key，避免 ECS query 原始顺序泄漏进 replay。
7. Bevy World rollback 已明确要捕获 Component + Resource，避免 FDB rollback 后内存 world 留在半应用状态。

## Concerns

### T1 — Critical — Phase 2b 权威调度与其他文件冲突，足以导致跨节点分叉

`06-phase2b-system-manifest.md` 自称唯一权威，列出 27 systems：`command_executor -> controller_system -> spawn_system -> build_system -> recycle_system -> transfer_system -> combat parallel set -> damage_application -> death_marker -> status parallel set -> aging -> maintenance -> death_cleanup -> pvp_block -> room_state -> controller_system -> resource_ledger`。

但 `engine.md` 和 `01-tick-protocol.md` 仍声明不同顺序：`death_mark -> spawn -> spawning_grace -> combat -> status_advance -> aging -> death_cleanup`，并把 regeneration/decay 作为与主线并行的较小集合。`02-command-validation.md` 又声明 `status_advance` 位于 `combat` 后、`regeneration` 前。

这不是文档表述差异，而是状态转移差异。例如：

- death_mark 在 spawn 前还是 combat 后，决定死亡实体是否释放 room cap、是否还能被攻击/治疗/状态推进。
- command_executor 属于 Phase 2a 还是 Phase 2b，决定 inline apply 是否真的“逐条校验 + 逐条应用”。
- spawning_grace 在 spawn 后立即赋予，还是 World Maintenance set 中递减，决定新生实体本 tick 是否免疫。
- status_advance 与 hack/drain/overload/fortify 并行还是串行，决定同 tick 特殊攻击的结果。

只要两个节点分别按不同文件实现，`same tick -> same output` 会失败。

### T2 — Critical — CommandAction 与 RejectionReason 注册表不闭合

`api-registry.md` 声称 CommandAction 共 19 个，RejectionReason 共 35 个，是单一权威来源。但 `02-command-validation.md` 使用了大量 registry 中没有的 rejection reason：`NotMovable`、`Fatigued`、`MissingBodyPart`、`TileBlocked`、`NotSource`、`SourceEmpty`、`CarryFull`、`TargetFull`、`TargetEmpty`、`NotYourRoom`、`InvalidTerrain`、`TooManyConstructionSites`、`FriendlyTarget`、`AlreadyFullHealth`、`NotFriendly`、`NotYourSpawn`、`BodyTooLarge`、`ExceedsRoomCapacity`、`AlreadyHacked`、`InvalidDamageType`、`AlreadyDebilitated`、`MainActionQuotaExceeded` 等。

同时 `02-command-validation.md` 的后半部分继续列出 `Leech` / `Fabricate` 变体、Recycle 50%/Tutorial 100% 退还等内容，而 `api-registry.md` 明确 Leech/Fabricate 是 custom action、非 core enum，且 `02` 前文又把 Recycle 改成 lifespan-dependent refund。

这会破坏：

- Command schema canonical hash：不同实现是否接受同一 action 不一致。
- TickTrace/rejection replay：recorded rejection reason 在另一节点可能无法解析。
- SDK/Gateway/engine 的 codegen：registry 说 35 个，validation 实际需要更多。
- `command_hash = Blake3(command_json)` 的稳定性：若不同 schema canonicalization 或未知 action 处理不同，排序与执行都会分叉。

### T3 — High — WASM 输出大小/截断语义冲突

`01-tick-protocol.md` §8.2 写 COLLECT Output JSON 超限行为是“截断（保留前 256KB）”；同一文件 §9.7 又写 WASM output 超 256KB 时“整批丢弃，不保留部分解析的前缀”。`02-command-validation.md` §1.1 写总字节数 ≤256KB，失败则整个 tick 输出丢弃；但 §6 的批级校验又写整批 ≤1MB。`04-wasm-sandbox.md` 也写 len >256KB 拒绝该玩家当 tick 所有输出。

对于 JSON 命令流，前缀截断与整批丢弃会产生完全不同命令集，从而改变排序队列与世界状态。必须只有一种权威语义。建议采用“超限整批丢弃”，禁止 prefix parse，因为 prefix parse 依赖 JSON 解析器错误恢复策略且容易产生 replay 分叉。

### T4 — High — FDB commit 重试语义互相冲突，影响 replay 闭包

`01-tick-protocol.md` 明确 FDB commit 失败重试时复用同一 COLLECT 结果，不重新执行 WASM，fuel 不追加扣费，失败 3 次后退还 consumed_fuel。可这是 determinism 上正确的做法。

`05-persistence-contract.md` §6 却写 commit 失败后“下次循环重新执行 tick N（重跑 COLLECT -> apply）”，并承认“重新生成 TickTrace（可能不同，因为时间流逝）”。这与 tick determinism 直接冲突：如果重跑 COLLECT，wall-clock timeout、sandbox scheduling、host path cache、worker reset 边界、甚至玩家代码内部 deterministic sequence 生成都可能改变结果。

重试策略必须统一为：commit retry 复用首次 COLLECT 的 canonical command envelope、snapshot_hash、wasm_status、consumed_fuel，不重跑 WASM；若需要重新构造对象存储 blob，只能从同一 canonical TickTrace buffer 派生，而不是重新收集。

### T5 — High — RNG 合同缺少 draw-level 稳定性，namespace seed 不足以抗迭代顺序变化

文档定义 Blake3 XOF、namespace、seed 派生公式，但没有定义每个随机事件的 draw key / offset / counter 合同。例如 combat、loot、npc_spawn、event 只写 `world_seed + tick (+ entity_id/room_id)`，没有说明：

- 同一 namespace 内多个 combat 事件按什么 canonical key 取随机数。
- 某事件被拒绝或实体死亡后，后续事件是否仍消耗 draw。
- 并行系统中 draw 顺序是否完全独立于任务调度。
- custom action / RuleMod 如何分配 RNG stream，是否允许按 iteration order 调 `next()`。

仅“独立流”不够。确定性实现应要求 counter-based RNG：`rng(namespace, world_seed, tick, event_key, draw_index)`，其中 `event_key` 是 command_hash/entity_id/room_id 等 canonical tuple。禁止共享 mutable RNGState 按迭代顺序 draw，尤其是 parallel set 与 ECS query 中。

### T6 — High — Phase 2b manifest 的 parallel safety 声明不足且自相矛盾

`06-phase2b-system-manifest.md` 将 attack/ranged/heal 并行，称按 `target_id` partition，同一 entity 只被一个 system 写入，再由 S10 reduce。但表格仍声明 S07-S09 直接写 `Entity(hits)`，S10 又读 `PendingDamage buffer` 并写 hits。到底是直接写 hits 还是写 pending buffer 不一致。

Status Set B 更危险：`hack_system`、`drain_system`、`overload_system`、`debilitate_system`、`disrupt_system`、`fortify_system`、`status_advance_system` 被放在同一 parallel set。可 `disrupt` 和 `fortify` 会清除或中断其他状态，`status_advance` 会 duration--/expire，这些显然不只是“互不重叠 Component”。同 tick 多命中优先级在 `02-command-validation.md` 规定为 Disrupt > Fortify > Debilitate > Hack > Drain/Leech > Overload > Fabricate，但 manifest 并未表达这个 reducer 顺序。

建议将状态攻击改为：收集 intent/pending status effects（parallel 可行）-> 按目标 canonical order + priority matrix 串行 reduce -> status_advance 串行执行。否则并行调度顺序会影响清除/施加/递减的最终状态。

### T7 — Medium — `command_hash = Blake3(command_json)` 缺少 canonical JSON/codec 定义

全局排序第五层依赖 `Blake3(command_json)`，但指定文件没有完整定义 JSON canonicalization：字段顺序、数字表示、字符串转义、Unicode normalization、未知字段拒绝前还是拒绝后 hash、服务端注入 envelope 是否参与 hash。TickTrace envelope 有 `canonical_codec_version` 字段，但没有在本子集内定义 codec 行为。

如果 SDK、Gateway、engine 以不同 JSON serializer 输出同义命令，hash tiebreaker 可能不同。建议排序 hash 改为 canonical binary IDL encoding，而不是 raw JSON bytes；若保留 JSON，必须指定 RFC 8785/JCS 或自定义 canonical JSON。

### T8 — Medium — “不可预测玩家顺序”与 replay/seed 记录存在设计张力

`01-tick-protocol.md` 同时要求 TickTrace 记录 `seed_epoch` 和 active player set 以支持 replay，又称玩家无法提前知道当前 tick 排序。只要 world_seed 是服主秘密，这可以成立；但 replay 数据公开后，历史 tick 排序必然可知。需要明确：

- seed_epoch 是否包含足以推导 seed 的材料，还是仅 epoch id。
- replay 公开延迟策略是什么，是否会泄露未来 seed epoch。
- admin/debug API 是否能返回 `player_order` 或 shuffle seed。

这是安全/公平与 determinism 的交叉问题，不一定阻塞确定性本身，但当前表述容易让实现把 seed 或 player_order 暴露给玩家查询路径。

### T9 — Medium — 新玩家 spawn / room 分配使用“密度最低”但缺少 tie-breaker

首次加入、重生、NPC spawn、出口生成都依赖确定性选择。出口生成已声明由 world seed 决定，但“密度最低区域”未说明同密度候选如何排序/随机选择。若不同节点遍历 room map 顺序不同，新玩家出生点可能不同。

需要为所有 min/max selection 明确 tie-breaker，例如 `(density, region_coord_x, region_coord_y, spawn_point_id)` 或 seed-derived deterministic choice with recorded event key。

### T10 — Medium — 对象存储写入先于 FDB commit 的 replay 可用性仍有未闭合状态

`05-persistence-contract.md` 说 FDB commit 成功 = tick 持久化完成，`tick_manifest` 证明对象存储 blob 存在。但对象存储是外部系统，写入成功后在 FDB commit 成功时仍可能因后续损坏/生命周期/读-after-write 一致性问题不可读。文档有 content hash 验证，但缺少“manifest 已提交、blob 后续读取失败”时 replay 的权威处理：tick 是否仍有效、是否 audit-gap、是否必须从 keyframe + state delta 重建、是否阻塞 pruning。

这更偏持久化完整性，但会影响 replay 完整性。

### T11 — Low — `TimeResource` 被纳入 Bevy snapshot，需限制为配置而非真实时间

`01-tick-protocol.md` 的 World snapshot resource 清单含 `TimeResource`（tick 间隔、超时配置等）。如果实现把 wall-clock timestamp、deadline instant 或 monotonic clock 也放入该 Resource 并参与 checksum/replay，会引入非确定性。建议命名为 `TickTimingConfig` 或明确 `TimeResource` 只允许 deterministic config，不允许 real time instant 进入 world state / state_checksum。

### T12 — Low — SIMD 默认 World 开启，需要更强的跨架构边界

`04-wasm-sandbox.md` 禁用 relaxed SIMD，但 World 默认 `wasm_simd=true`。整数 SIMD 通常可控，但玩家 WASM 仍可能包含浮点/SIMD 浮点路径。文档禁止引擎 `f64`，但未明确禁止玩家 WASM 浮点或规定 NaN canonicalization/fast-math 禁止。若玩家代码浮点只影响其输出命令，跨架构差异可能导致不同命令，从而破坏 replay 若 replay 重跑 WASM。虽然当前 replay 记录 Command[] 不重跑 WASM，但 dry-run、degraded 二次验证、arena verification 仍可能受影响。建议明确玩家 WASM 浮点允许但“不参与 authoritative replay”，或在 compile policy 中禁用 FP/要求 deterministic FP profile。

## State Machine Gaps

1. Room 状态机缺少完整转移表：`contested -> owned/reserved/neutral/abandoned` 的所有条件、progress 抵消公式、同 tick 多 Claim tie-breaker 未闭合。
2. Spawn 生命周期跨 Phase 2a/2b 不统一：Phase 2a “只校验不入队”、Phase 2b manifest 又有 `spawn_system`，但 body_cost 扣除、room cap 消费、pending_entities flush 后何时可见需要单一状态图。
3. Death lifecycle 在不同文件中顺序不同：Recycle、combat death、aging death、death_mark、death_cleanup、room cap release 的时点必须统一。
4. Special attack state machine 有优先级矩阵，但 manifest 没有把该矩阵落实为 deterministic reducer；Hack stage、Fortify cleanse、Disrupt interrupt、Overload recovery 的同 tick 组合仍可分叉。
5. Commit failure state machine 在 `01` 与 `05` 冲突：重试时是否重跑 COLLECT 是必须立即统一的核心状态转移。
6. Output validation state machine 不闭合：InvalidJson / schema violation / over-size / partial-output / trap / timeout 到底进入 TickTrace 哪种状态、是否产生 rejection、是否 refund，在多个文件中不一致。
7. Seed rotation / seed bump 状态机缺少持久事件格式：seed epoch、manual bump、rollback 后 seed 选择、active player set snapshot 需要写入 TickTrace 的具体字段与时序。
8. Replay state machine 对 “manifest committed but object blob unavailable/corrupt” 缺少明确 terminal state（verified / audit-gap / unreplayable / reconstructable）。

## Non-Determinism Sources

1. 多权威文档冲突：实现者按不同文件编码 Phase 2b、validation、persistence retry，会直接产生不同 state checksum。
2. JSON canonicalization 未定义：`command_hash`、commands_hash、snapshot_hash 若使用 raw serializer bytes，会受字段顺序与编码影响。
3. RNG mutable stream 风险：仅 namespace seed 不足，必须定义 event-keyed counter draw，避免 ECS/parallel iteration 顺序影响随机数消费。
4. Bevy query/archetype order：manifest 已要求 stable entity iteration，但所有系统细节必须落实；尤其 pending_entities、pending_damage、status intents reducer。
5. HashMap / registry iteration：文档要求 IndexMap，但 ResourceRegistry、WorldConfig、mods_lock、custom_actions manifest 也必须 canonical sort/hash。
6. 系统时间：WASM 已禁用 clock，但 commit retry 文档提到“时间流逝导致 TickTrace 不同”；真实时间不得进入 authoritative TickTrace/state hash，除非作为 non-authoritative audit metadata 排除 replay checksum。
7. Object store / async IO：BROADCAST 不影响 state 是合理的；但 object store availability 会影响 replay audit，需定义损坏/缺失处理。
8. SIMD/浮点：引擎禁 f64，但玩家 WASM 与 RuleMod/host pathfinding heuristic 若使用浮点会造成跨平台差异；应统一整数/定点。
9. Tie-breaker 缺失：密度最低 spawn、同等距离 snapshot truncation across multiple drones、同 target multi-status reducer、room/controller contested resolution 都需要 canonical tie-breaker。
10. Cache influence：path_find cache key 包含 visibility fingerprint 是好事，但 cache hit/miss 不得改变返回路径，只能改变 fuel 成本；若超预算依赖 cache state，则 cache state 必须是 deterministic/replay 输入或不影响 authoritative command results。

## CrossCheck — 需要跨方向检查

1. Architecture / Docs：请统一“权威文档”层级。`api-registry.md`、`06-phase2b-system-manifest.md`、`05-persistence-contract.md` 自称权威，但其他文件仍保留冲突表格；应删除或改为引用，CI 检查禁止重复定义。
2. Gameplay：特殊攻击同 tick 优先级矩阵需要与 Phase 2b manifest 合并成一个 deterministic reducer 规范，尤其 Disrupt/Fortify/Hack/Overload 的清除、施加、恢复顺序。
3. Security：world_seed、seed_epoch、player_order、replay data 的可见性策略需要确认，避免 debug/MCP/API 泄露未来排序。
4. Persistence：`01` 与 `05` 的 commit retry 必须由持久化方向确认：是否复用 COLLECT canonical buffer；object blob 在 FDB commit 前写入失败/超时/损坏时如何标记 replay 状态。
5. SDK/API：CommandAction/RejectionReason 必须 codegen 化，registry 与 validation 矩阵目前不一致，SDK 无法可靠生成类型。
6. Sandbox：需要确认玩家 WASM 浮点/SIMD 策略；如果 authoritative replay 永不重跑 WASM，可接受更宽松策略，但 dry-run/degraded verification 要明确非权威或固定平台。
7. QA/CI：建议新增 cross-doc determinism CI：从 registry 生成 enum，与 validation 表、manifest、TickTrace envelope 做机器校验；再用同一 seed 在 debug/release、单线程/多线程执行对比 state_checksum。

## Approval Conditions

至少完成以下修复后，Determinism 方向可重新考虑 APPROVE/CONDITIONAL_APPROVE：

1. 删除或重写所有与 `06-phase2b-system-manifest.md` 冲突的 Phase 2b 顺序描述，并把特殊攻击 reducer 顺序纳入 manifest。
2. 使 `api-registry.md` 与 `02-command-validation.md` 的 CommandAction/RejectionReason 完全一致；所有未注册变体要么注册，要么从 validation 中删除。
3. 统一 WASM output 超限语义为单一规则，推荐“整批丢弃、不 prefix parse”。
4. 统一 FDB commit retry：不得重跑 COLLECT；重试必须复用首次 COLLECT 的 canonical commands、snapshot_hash、wasm_status、fuel ledger。
5. 定义 RNG draw contract：counter-based、event-keyed、与迭代顺序无关，并覆盖 custom action / RuleMod。
6. 定义 canonical codec/hash：command_hash、commands_hash、snapshot_hash、state_checksum、manifest_hash 均使用同一 canonical binary/JSON 规范。
