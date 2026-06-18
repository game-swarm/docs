# R14 确定性评审 (GPT)

## Verdict: REQUEST_MAJOR_CHANGES

R14 的方向正确：把 tick 设计成 `state + commands + config/mod lock + seed → new_state`，并且明确禁止墙钟、OS 随机数、`std::HashMap` 迭代、浮点数等典型非确定性源。但当前文档内存在多处“权威合同分叉”：命令全局排序、RNG 算法/seed 派生、ECS 调度顺序、沙箱生命周期、输出截断语义、TickTrace 失败语义都出现互相冲突的定义。对确定性系统而言，这不是实现细节问题，而是 replay 与跨节点一致性的根合同不成立。

建议在进入实现前先完成一次 Determinism Contract 收敛：指定唯一权威章节，删除或改写所有冲突叙述，并把 replay 输入封套、排序键、RNG stream、系统链、失败语义做成可测试的规范表。

## 发现的问题

### T1 — Critical — 命令全局排序合同互相矛盾，直接破坏 replay 与公平性

允许文档中至少出现三套排序定义：

- `design/engine.md` 阶段二说明：玩家顺序由 `seed = hash(tick_number, world_seed)` 洗牌，随后按“洗牌后顺序 + 玩家内 sequence”执行。
- `specs/core/01-tick-protocol.md §3.1`：Seeded Shuffle 使用 `Blake3(tick_number || world_seed)`，排序属性声明依赖同 seed 同指令集。
- `specs/core/01-tick-protocol.md §9.1`：确定性权威合同却声明 RawCommand 全局排序键为 `(player_id, sequence, source)`，不同玩家按 `player_id` 字典序。
- `specs/core/02-command-validation.md §2.1` 又写成 `(player_id, shuffle_order, source, sequence)`，其中 `shuffle_order` 来自 PRNG。

这些定义不能同时成立。若线上执行用 seeded shuffle，而 TickTrace/replay verifier 用 `(player_id, sequence, source)`，同一 tick 的资源竞争、攻击先后、建造占位、治疗满血拒绝都会分叉。若跨节点各自选了不同“合理解释”，同一输入会产生不同状态。

必须指定唯一排序键，例如：

`(shuffle_order_for_player, player_id_tiebreaker, source_order, sequence)`

或明确放弃 shuffle，使用纯 `player_id` 序。无论选择哪一个，都必须让 Phase 2a inline apply、TickTrace 记录、replay verifier、admin/source 注入、SDK 文档完全一致。

### T2 — Critical — RNG 合同不统一：Blake3 XOF、ChaCha8Rng、seed 轮换与 per-entity stream 同时存在

当前 RNG 设计出现多套并行合同：

- `design/engine.md §3.3`：shuffle seed 为 `Blake3("shuffle" || world_seed || tick)`，per-entity stream 为 `Blake3(stream_name || world_seed || entity_id || tick)`。
- `specs/core/01 §3.1`：shuffle seed 为 `Blake3(tick_number || world_seed)`，并用 Blake3 XOF 直接取 `read_u64() % (N-i)`。
- `specs/core/01 §9.5`：RNG namespace 使用独立 `ChaCha8Rng`，seed 来源为 `world_seed + tick` 或 `world_seed + tick + entity_id/room_id`。
- `specs/core/04 §2.3`：WASI random 禁用，注释说使用 host function 提供的 seed PRNG；但 §3.2 允许的 host function 列表没有 `swarm_get_random(sequence)`，而 `specs/core/01 §9.5` 又要求 WASM 用该函数获取确定性随机数。

这会造成两个层面的确定性风险：

1. 引擎内部 RNG 流无法由单一 seed 合同推导。实现者可能选择 Blake3 XOF 或 ChaCha8Rng，导致相同 tick 的战斗浮动、NPC spawn、loot、事件触发不同。
2. WASM 玩家 RNG 的 ABI 不闭合。若 WASM 不能调用确定性随机 host function，只能自带 PRNG；若 host function 存在但没有列入沙箱白名单，则部署校验会拒绝或不同实现绕开白名单。

必须收敛为一个 RNG Contract：固定算法、namespace 字符串、seed 编码、counter/offset 规则、拒绝 modulo bias 的抽样方式、每个 gameplay 随机点的 stream 名称，以及 replay 时是否记录 seed epoch 或 stream offset。

### T3 — Critical — ECS 系统顺序在核心文档之间冲突，状态机不闭包

ECS Phase 2b 至少有三种顺序：

- `design/engine.md`：`death_mark → spawn → combat → regeneration/decay → death_cleanup`，并提到 `spawning_grace`、`status_advance`、`aging`。
- `specs/core/01 §3.4` 的 20 系统链：`death_mark → pvp_block → spawn → regeneration → seed_rotation → cargo → storage → controller → repair → room_state → combat → decay → memory → env → tick_end → death_cleanup → onboarding`。
- `specs/core/01 §9.6`：必须 chain 的权威顺序为 `death_mark → spawn → spawning_grace → combat → status_advance → aging → death_cleanup`，并行系统只有 regeneration、decay。
- `specs/core/02 §3.19`：`status_advance` 位置为 `combat` 之后、`regeneration` 之前，即 `death_mark → spawn → spawning_grace → combat → status_advance → (regeneration, decay) → death_cleanup`。

这些顺序会改变实际结果。例如 regen 在 combat 前后、status advance 在 regen 前后、aging 是否存在、seed_rotation 是否在 tick 内改变 `WorldSeed`，都会影响同一 tick 的死亡、恢复、状态持续时间、随机流派生和 replay checksum。

必须提供唯一 Phase 2b manifest，包含每个 system 的读写集、执行顺序、是否允许并行、并行 system 的确定性证明，以及新增 system 的插入规则。否则 `tick(seed, state, commands) → new_state` 不是闭包合同，而是实现者解释。

### T4 — High — Seeded shuffle 使用 modulo 取余存在偏差，且“不可预测”声明与 world_seed 轮换模型不一致

`position[i] = XOF.read_u64() % (N - i)` 是确定的，但不是均匀洗牌；当 `2^64` 不能整除 `N-i` 时存在 modulo bias。偏差通常很小，但此处排序公平性是核心 gameplay 合同，且玩家会长期采样顺序，微小偏差也可能被策略利用。

同时文档声明玩家“无法提前知道当前 tick 排序位置”，但 world_seed 泄露模型承认泄露后未来 tick 可预测，且 `new_seed = Blake3(old_seed || current_tick)` 从旧 seed 可推出未来 seed。此处至少要把“不可预测”限定为“world_seed 未泄露且玩家无 seed 访问权限时”。

建议采用 rejection sampling 或指定确定性 Fisher-Yates 的无偏抽样算法，并把威胁模型中的“不可预测”改成条件性表述。

### T5 — High — 沙箱生命周期与 determinism/replay envelope 冲突

`design/engine.md §3.4.3` 定义 long-lived worker pool + per-tick clean Store/Instance reset；`specs/core/04 §1` 定义每 tick fork → execute → kill，不保留状态。两者都可以做成确定性，但资源行为、cold start、trap 后恢复、worker recycle 审计字段完全不同。

更重要的是 replay envelope 记录 `wasmtime_version`，但 sandbox 编译缓存键使用 `wasmtime_build_commit`、`wasmparser_version`、`validation_policy_version`、`target_arch`、`security_epoch`。如果 deterministic replay 或二次验证需要复现 WASM 执行，单独记录 `wasmtime_version` 不足以唯一确定编译/验证语义。

虽然文档倾向于 replay 记录 Command[] 而非重跑 WASM，这是正确方向；但异常 tick、degraded tick、二次验证、玩家争议审计仍需一个明确的 WASM execution envelope。否则“同一模块同一快照”是否必须复现同一 Command[] 没有闭合定义。

### T6 — High — TickTrace 写入失败语义自相矛盾，审计完整性与状态成功条件不清

`specs/core/01 §6.1` 失败矩阵写道：

- TickTrace write fail：tick 执行完成，审计不完整，标记不可回放。
- Replay write fail：tick 执行完成，后续从 keyframe 重建。

但 `§6.3.4` 和 `§9.4` 又声明 TickTrace 与状态写入在同一 FDB 事务中，写入失败则整个 tick 回滚，不允许状态成功但审计缺失。

这对 replay 完整性是根本冲突。若允许“状态成功但 TickTrace 缺失”，则 deterministic audit 链断裂；若不允许，则失败矩阵必须改为 tick abandon / retry。当前两者并存会让运维和实现做出不同故障处理。

建议以 §9.4 为权威：状态、TickTrace、fuel 三者同事务；任何 TickTrace 写入失败导致事务失败、重试或 tick abandon。删除“tick 执行完成，审计不完整”的路径，或明确它仅指非权威分析日志而非 TickTrace。

### T7 — High — 输出大小/截断语义多处冲突，可能导致 replay 命令集不一致

文档对 WASM 输出大小的定义不一致：

- `specs/core/01 §8.2`：Output JSON 256KB，超限行为为“截断（保留前 256KB）”。
- `specs/core/01 §9.7`：超过 256KB 时整批丢弃，不保留部分解析前缀。
- `specs/core/02 §1.1`：总字节数 ≤256KB，校验失败整个 tick 输出丢弃。
- `specs/core/02 §6` 批级校验又写整批 tick 输出 ≤1MB。
- `specs/core/04 §3.1`：len >256KB 拒绝该玩家当 tick 所有输出。

确定性角度必须选择“整批拒绝”或“确定性截断后解析”，不能混用。保留前 256KB 尤其危险：JSON 可能被截断到半个 token，不同 parser 的错误恢复策略不能纳入确定性合同；即使只保留完整前缀，也会改变玩家输出序列语义。

建议统一为：WASM 返回 buffer len 超过 256KB → 该玩家本 tick 输出整批拒绝，记录 `OutputTooLarge`，不尝试解析任何前缀。

### T8 — Medium — 快照截断排序键在文档间不一致，且多 drone 玩家距离基准未定义

`design/engine.md §3.4.4` 的 priority bucket 顺序为“自机 > 友方 drone > 敌方 drone > 建筑 > NPC > 资源”，同桶按 stable `entity_id`。`specs/core/01 §2.3` 则定义关键桶/高/中/低桶，同桶按 `(distance_to_drone, entity_id)`。

如果一个玩家有多个 drone，`distance_to_drone` 是哪个 drone？最小距离、拥有者主 drone、每实体最近己方 drone、还是当前调用 host function 的 drone？不同选择会截断出不同实体集，导致玩家 Command[] 和 replay 可见性分叉。

需要为 snapshot truncation 指定唯一排序：bucket 枚举、距离基准、距离平局、entity_id 编码、序列化 size 计算方式，以及 `host_get_objects_in_range` 与 tick snapshot 是否共享同一 truncation 规则。

### T9 — Medium — HashMap/IndexMap 规则方向正确，但没有覆盖所有 map/set 与序列化 canonicalization

文档明确不用 `std::HashMap`，资源使用 `IndexMap`，Hash 用 Blake3，不用 `std::hash`。这是亮点。但确定性合同还需要覆盖：

- 所有 set/map 的插入顺序来源是否 deterministic；`IndexMap` 只保证保留插入顺序，不保证插入顺序本身正确。
- JSON/TickTrace/commands_hash/snapshot_hash 的 canonical serialization：字段顺序、整数编码、枚举字符串大小写、缺省字段是否省略。
- Bevy query 结果是否必须按 stable EntityId 排序后再用于任何状态修改或序列化。

否则即使不用 `HashMap`，仍可能因为 ECS query/entity allocation 顺序或 serde map 字段顺序产生 checksum 分叉。

### T10 — Medium — 部分校验表仍保留旧/重复 action 定义，状态机覆盖不完整

`specs/core/02` 前半定义 Recycle 需要 `spawn_id`，返还比例后文又改成 lifespan 相关；后半 `CommandAction 变体` 中 Recycle 示例没有 `spawn_id`，并写“标准退还 50% / Tutorial 前 500 tick 100%”。同文件内存在过时定义。

特殊攻击矩阵还引用 Leech/Fabricate，但前面的逐指令校验矩阵没有完整定义二者；R14 允许文档中也没有它们的 deterministic execution order、资源扣除、状态推进、抗性 RNG 规则。若 RuleMod 可动态注册这些 action，就必须说明它们如何进入同一 manifest、同一排序、同一 RNG namespace、同一 validation/apply 路径。

## 亮点

- 明确把确定性作为核心原则：相同初始状态 + 相同 Command 输入 → 相同世界状态，并把 replay/反作弊建立在该合同上。
- Tick 生命周期拆成 COLLECT / EXECUTE / BROADCAST，且规定 BROADCAST failure 不回滚已提交 tick，状态权威边界清晰。
- Phase 2a inline apply 选择“基于当前 Bevy World 逐条校验 + 应用”，对资源竞争和 TOCTOU 的语义比批量 apply 更明确。
- WASM deferred command model 是正确方向：玩家代码只能返回 CommandIntent，不能直接 mutating host function 修改世界。
- 已显式识别并规避多类常见非确定性源：墙钟、OS RNG、filesystem/network/env/process、`std::HashMap`、`std::hash`、浮点数、relaxed SIMD、threads/atomics。
- FDB commit 失败时要求恢复 Bevy World snapshot，并复用 COLLECT 结果，避免重跑 WASM 造成跨重试非确定性。
- Snapshot truncation 试图使用 stable ordering，并暴露 `truncated/omitted_count`，这是防 DoS 与 replay determinism 兼顾的正确方向。
- TickTrace 与 state_checksum 的设计能够为后续 CI replay、线上抽样验证、争议审计提供基础。

## State Machine Gaps

1. Room 状态机缺少完整 transition table。`neutral/reserved/owned/contested/abandoned` 的图示不错，但 contested 的多玩家扩展、同 tick claim 排序、reservation_timeout 与 downgrade_timer 同 tick 触发优先级、放弃/消灭 owner 的精确定义仍不完整。
2. Tick 状态机缺少“commit fail retry loop”的完整状态图。当前有 abandon、retry、degraded、rollback，但没有明确 `COLLECT_CACHE_READY`、`EXECUTE_RETRYING`、`ABANDONED_NO_TICK_INCREMENT` 等状态与计数器重置条件。
3. WASM module lifecycle 状态机不闭合。部署、编译、签名、缓存命中、validation policy 变更、security_epoch 变更、revocation、rollback、effective_tick 的状态转换需要统一。
4. Special attack 状态推进不完整。Hack、Drain、Overload、Debilitate、Fortify、Disrupt 的持续状态、同 tick 反制、stage 递增/递减、owner 恢复、lifespan/fuel 是否暂停，需要进入同一个 `status_advance_system` transition table。
5. Spawn/Recycle/DeathMark 状态机仍有边界问题。Spawn Phase 2a 扣费、Phase 2b 创建失败 refund、death_mark 释放 room cap、spawning grace、death_cleanup despawn 的顺序需要用状态图表达，并覆盖 commit rollback。
6. Seed epoch 状态机未闭合。正常轮换、手动 bump、泄露恢复、历史 replay 按 epoch 选择 seed、未来 tick 的 seed 派生停止点，需要成为可审计状态机。
7. Query/read state machine 未完全定义。WASM snapshot、MCP query、Dragonfly cache、WebSocket delta、FDB history 的版本转换已有表格，但 cache stale / gap fetch / current Bevy snapshot 与 FDB 恢复之间的边界还需更明确。

## Non-Determinism Sources

1. 多重排序合同：seeded shuffle、player_id 字典序、`(player_id, shuffle_order, source, sequence)` 并存，是当前最大非确定性源。
2. 多重 RNG 合同：Blake3 XOF、ChaCha8Rng、per-entity Blake3 stream、host random function 白名单缺失并存。
3. Bevy ECS query/order：若任何 system 依赖 query 原始迭代顺序、entity allocation 顺序或并行调度完成顺序，可能跨平台/跨节点分叉。
4. `IndexMap` 插入顺序：若插入顺序来自非稳定来源，`IndexMap` 只能稳定保存错误顺序，不能自动提供 canonical order。
5. JSON/canonical serialization：commands_hash、snapshot_hash、state_checksum 未定义完整 canonical encoding，可能因字段顺序或缺省字段分叉。
6. Wasmtime/Cranelift/SIMD：普通 SIMD 被允许而 relaxed SIMD 禁用；仍需说明所有允许的 SIMD 指令不得影响 gameplay 数值，特别是若玩家 WASM 内部用浮点/SIMD 计算 CommandIntent，replay 不重跑 WASM 可以规避状态分叉，但争议复现 Command[] 时会受影响。
7. 沙箱 wall-clock timeout：超时导致 0 指令是确定的结果类别，但哪个玩家在 collect soft deadline 后被“跳过剩余”依赖调度顺序；必须定义 dispatch order 与 deadline cutoff 的 deterministic selection，避免不同节点跳过集合不同。
8. Pathfinding host function：成本按 explored_nodes/expanded_edges，缓存键含 terrain_hash/visibility_fingerprint；但 A* tie-breaker、open-set 排序、邻居遍历顺序未定义会导致路径和 fuel 消耗分叉。
9. FDB retry/backoff：等待 1s 重试同 tick 不影响 replay，但若期间 deploy/admin events 是否排队进入同一 tick 未定义，会造成边界分叉。
10. RuleMod/Rhai：禁止 f64 是正确的，但动态 action 的 manifest、执行顺序、RNG namespace、状态写入路径若未强制，会形成第二套状态修改路径。
11. System time/config：TimeResource 捕获 tick interval/timeout 配置，但如果 runtime wall-clock 参与 tick 内逻辑（除超时分类外）会破坏 replay；应明确 gameplay state 不读取系统时间。
12. Output truncation：若保留前 256KB 与整批拒绝并存，不同实现会生成不同 Command[]。

## CrossCheck — 需要跨方向检查

- CX1: 命令排序到底选择 seeded shuffle 还是 player_id canonical order → 建议 Architect 检查 Phase 2a、TickTrace、Replay Verifier、Command Source Gate 的唯一权威排序合同，并删除冲突章节。
- CX2: RNG 算法、seed epoch、host random ABI 不统一 → 建议 Architect + Security 检查 RNG Contract 是否满足公平性、泄露恢复、回放可验证和 WASM 沙箱白名单一致性。
- CX3: TickTrace failure 语义冲突 → 建议 Reliability/Storage 检查 FDB 事务边界、WAL 是否只是审计补偿、以及是否允许任何“状态成功但不可回放”的线上路径。
- CX4: 沙箱生命周期 long-lived pool 与 per-tick fork 冲突 → 建议 Security + Performance 检查隔离强度、冷启动预算、trap/OOM 后状态清理、以及 replay envelope 需要记录哪些版本字段。
- CX5: Snapshot truncation 与 query host function 的排序/距离基准不一致 → 建议 Gameplay/UX 检查玩家可预期性，Architect 检查 canonical visibility fingerprint 与 stable serialization。
- CX6: RuleMod 动态 action 可能形成第二套状态修改路径 → 建议 Extensibility/Plugin 方向检查 World Action Manifest 是否强制 schema、排序、RNG、读写集和 replay verifier 集成。
- CX7: Pathfinding tie-breaker 与缓存键未完整指定 → 建议 Gameplay + Determinism 复核 A* open-set ordering、邻居顺序、不可达时 fuel cost、缓存命中是否影响输出。
