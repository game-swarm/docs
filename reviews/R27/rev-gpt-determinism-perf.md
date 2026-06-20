# R27 Phase 1 Clean-Slate Review — Determinism & Performance

Reviewer: rev-gpt-determinism-perf (GPT)
Scope: Determinism contract, PRNG/RNG, cross-node replay consistency, tick efficiency, ECS scheduling, WASM sandbox overhead, FDB/write-path scalability.

## Verdict

CONDITIONAL_APPROVE

R27 的确定性与性能合同相比早期设计已经明显成熟：它把 tick 输入、命令排序、ECS manifest、TickTrace replay-critical subset、WASM 沙箱限制、固定点数值、HashMap 迭代陷阱、FDB 小事务策略都写成了可执行合约。若按文档实现，单节点 500 活跃玩家 / 5000 drones 的 World 模式有可信落地路径。

但我不建议无条件批准：当前文档仍存在若干会导致实现分叉或容量声明过度乐观的合同缺口。最重要的是特殊攻击调度在 `02-command-validation.md` 与 `06-phase2b-system-manifest.md` 中出现顺序冲突；PRNG/seed secrecy 同时追求“不可预测”和“确定性 replay”但缺少 commit-reveal 或 tick 延迟披露方案；Room-Partition 的跨房间 2PC “best-effort fallback”与 replay 原子性目标冲突；WASM/worker pool 的 CPU 配额模型与 500/1000 玩家容量推导之间仍有口径不一致。

## Strengths

1. 确定性合同覆盖面强
   - `01-tick-protocol.md` 明确定义 `sort_key = (priority_class, shuffle_index, source_rank, sequence, command_hash)`，且要求 PRNG、Hash、ECS 顺序、数值类型、Map 迭代均采用确定性实现。
   - `06-phase2b-system-manifest.md` 把 29 个 system 的 stable ID、顺序、R/W 矩阵、manifest hash、CI 检查写成权威调度，避免 Bevy archetype order 或隐式并发导致分叉。
   - `05-persistence-contract.md` 将 replay-critical subset 与 rich/debug blob 分离，避免 FDB 事务写大 blob，也让 replay 关键数据保持原子提交。

2. 已主动规避常见非确定性陷阱
   - 数值使用 integer / fixed-point，禁用 `f64`。
   - 明确不用 `std::HashMap` 迭代顺序，使用 `IndexMap` / canonical sort。
   - WASI clock/random/filesystem/network/thread/atomics 默认关闭，WASM 不直接访问 OS entropy/time。
   - Wasmtime 版本、system manifest hash、world config hash、mods lock hash、host ABI version、codec/truncation version 均进入 TickTrace/Envelope。

3. Replay 闭包意识正确
   - 设计倾向于 `execute_deterministic(state, commands, manifests) -> recorded_state`，且 replay 不重跑 WASM，只重放 accepted commands。
   - FDB commit failure 时复用 canonical COLLECT buffer、不重跑 WASM、不追加 fuel，是正确的确定性与公平性选择。
   - FDB commit 失败显式要求 Bevy World restore，且列出 Component/Resource snapshot 范围。

4. Tick 性能方向正确
   - 两阶段快照（一次构建全局/room 分片，再按玩家拼接）把复杂度从 `O(players × entities)` 降为 `O(entities + players × visible_entities)`。
   - WASM 部署期预编译、tick 内只实例化，避免 tick 关键路径 JIT。
   - FDB 只写 head/manifest/hash/pointer，小事务推进 world head，大 blob 异步入对象存储，方向合理。

5. ECS 调度已经有并行边界意识
   - Serial spine + limited parallel sets 比“全部 parallel Bevy schedule”更适合确定性游戏引擎。
   - RoomCap 中间态、DeathMark filter、SpawningGrace filter、special attack reducer canonical merge sort 等关键竞态已有明确说明。

## Concerns

### T1 — High — 特殊攻击调度在两个权威附近出现冲突，可能导致 replay 分叉

`06-phase2b-system-manifest.md` 的权威调度为：

`death_marker → spawn → spawning_grace → regeneration → combat → special_attack_reducer → damage_application → status effects/status_advance → aging → decay ...`

但 `02-command-validation.md` §3.19 写的是：

`death_mark → spawn → spawning_grace → combat → status_advance → (regeneration, decay 并行) → death_cleanup`

这不仅是简化描述，而是改变了 regeneration、damage_application、status_advance、decay 的相对顺序。若实现者参考 `02` 中的旧顺序，状态效果、自然回复、damage 结算、duration decrement 会与 manifest 不一致，直接破坏 replay。

建议：
- 删除 `02-command-validation.md` §3.19 中的独立时间线，只保留“status_advance_system 的权威位置见 06 manifest S22”。
- CI 增加跨文档 grep/AST 校验：除 `06-phase2b-system-manifest.md` 外不得出现完整 Phase 2b 顺序列表。

### T2 — High — RNG “不可预测”与确定性 replay 的威胁模型未完全闭合

文档声称 seeded shuffle “不可预测”，同时 world_seed 是服主级秘密，TickTrace 记录 seed epoch 以 replay。问题：

- 如果客户端或服主能在 tick 前推导 `Blake3("shuffle" || world_seed || tick)`，排序可预测；文档也承认 seed 泄露后未来 tick 全可预测。
- 若 TickTrace 为 replay 记录足够 seed 信息，则需要清楚区分“赛中不可见”和“赛后/审计可见”。目前没有明确 seed disclosure boundary。
- `new_seed = Blake3(old_seed || current_tick)` 泄露后可预测未来，这在竞争世界中是 High 风险；“服主手动 seed-bump”是运维缓解，不是协议级公平保证。

建议：
- 明确 `world_seed/current_seed` 永不进入玩家可见 API、非 admin TickTrace、日志、metrics。
- 若需要真正的赛中不可预测，增加 tick-delayed commit-reveal：tick N 使用 seed epoch secret，tick N+K 后公开 seed/material 用于 replay 验证；或至少记录 hash commitment 而非提前暴露 seed。
- 将 `seed_epoch` 字段定义为 opaque epoch id，而不是可推导 seed 本体；replay verifier 由 admin/offline authority 提供 seed material。

### T3 — High — Room-Partition 的 “2PC fallback to best-effort” 与原子 replay 合同冲突

`05-persistence-contract.md` §8 将 500+ players 场景切到 room-level partition，并写 cross-room operations 使用 2PC，超时 3s 后 fallback to best-effort。这个 fallback 对确定性非常危险：

- 跨房间移动、出口、攻击/视野、资源转移如果一边提交、一边失败，会产生半状态。
- “best-effort” 没有定义 deterministic terminal state、compensation command、abort/commit 决策的 canonical sort。
- FDB 原子提交原本是核心 replay 保证；room partition 后若跨 room 不再原子，`tick(seed,state,commands)->new_state` 闭包不再成立。

建议：
- 对 Phase 1 合同而言，跨 room 操作必须采用确定性两阶段：prepare 全部成功才 commit；任一失败则所有 involved rooms abort，命令 rejected，不能 best-effort mutate。
- 若为了可用性保留 best-effort，必须把它降级为“tick abandon / room-pair locked / deterministic retry”，不得提交半边状态。
- Cross-room transaction 的 conflict set、participant order、timeout handling、retry attempt_id 应进入 TickTrace replay-critical subset。

### T4 — Medium — Command validation 文档仍有同一限制的不同数值，容易实现分叉

`02-command-validation.md` 前文说 tick 输出 JSON 总字节数 ≤ 256KB；后面“批级与系统级校验”又写整批 ≤ 1MB。`04-wasm-sandbox.md` 与 `api-registry.md` 均倾向 256KB 输出上限。

建议：统一为 “WASM tick output hard cap = 256KB，超过整批丢弃”。如果 1MB 是 MCP/Admin batch limit，应拆成不同字段名，不能和 WASM tick output 共用“整批”。

### T5 — Medium — Canonical serialization / command_hash 细节仍需更机器化

多处使用 `Blake3(command_json)`、`state_checksum = Blake3(canonical_serialize(world))`，但允许阅读集合中未提供 canonical JSON/codec 的精确定义。若不同实现对 JSON key order、number encoding、string escaping、enum representation 有差异，command_hash 和 state_checksum 会分叉。

建议：
- 在本方向合同中至少引用一个 `canonical_codec_version` 的机器规范：map key 排序、UTF-8 normalization、integer endian、enum tag、unknown field policy。
- `command_hash` 不应 hash 原始 JSON 字节；应 hash Source Gate 注入后的 canonical RawCommand binary/CBOR-like encoding。

### T6 — Medium — Bevy World snapshot/restore 的 ID allocator 与 deferred entity flush 合同不足

文档要求 snapshot 捕获 Component/Resource，但 entity creation/despawn 使用 pending queues 和 StableEntityId。若 FDB retry restore 没有恢复：

- entity ID allocator counter；
- pending_entities / pending_despawn queues；
- command-local buffers（PendingDamage, PendingSpecialAttack, PendingSpawn）；
- resource ledger incremental buffers；

则 retry 后可能生成不同 entity IDs 或重复应用 pending effects。

建议：把这些 Resource/Buffer 明确加入 snapshot mandatory list，并在 CI fault injection 中断言 ID allocator、pending queues、ledger buffers restored exactly。

### T7 — Low — “Fuel metering = 指令数公平”表述需要收敛

Wasmtime fuel 不是跨语言、跨优化级别、跨 wasm compiler backend 的绝对“同等算力”；它更接近 deterministic cost unit。C/Rust/AssemblyScript/TS-to-WASM 的同一高级操作 fuel 消耗不同。文档中“C 玩家和 Python 玩家在相同配额下获得同等算力”的叙述偏强。

建议改为：fuel 提供跨节点确定、可审计的 execution budget；语言公平由 SDK/runtime profile 与 benchmark calibration 近似保证，而不是语义上完全等价。

### P1 — High — 1000 worker / 1000 active players 容量推导过度乐观，且与 cgroup CPU 配额冲突

`engine.md` 推导 hard cap 1000 players 时假设 1000 workers、40 cores，p50=5ms 并行后 wall-clock ~25ms；但 `04-wasm-sandbox.md` 每 sandbox cgroup `cpu.max = 250000 3000000`，每 3s 0.25 CPU 秒。若 1000 sandbox 都可用 0.25 CPU 秒，总需求是 250 CPU 秒 / 3s，远超 32/40 cores。

同时 worker_pool 默认 256，hard cap 1000 需要运营商显式提高，但 1000 OS worker 的 RSS、cgroup、seccomp、Store/Instance reset、IPC fanout 都会显著增加调度开销。

建议：
- 将 hard cap 1000 改为“requires benchmark gate + operator override”，并默认只承诺 target 500。
- aggregate CPU admission 应是唯一准入源；per-worker cgroup quota 必须由 aggregate budget 派生，不能每 worker 固定 0.25 CPU 秒。
- benchmark 必须测 1000 workers 的 Store reset + snapshot copy + Unix socket/gRPC dispatch + output JSON parse，而不只测 command loop。

### P2 — High — Snapshot stitching 1000 × 256KB p99 <100ms 风险很高

1000 个玩家每 tick 最坏 stitching 输出 256MB，100ms 内完成意味着只算内存带宽也很紧，还未包括 visibility filter、serialization、copy into WASM memory、hashing、allocation、cache misses。World 预算 200ms snapshot build + 2500ms collect，目标 500 players 尚可；1000 players 的 p99 <100ms 需要非常强的零拷贝/arena allocator/预编码分片支持。

建议：
- 把 snapshot representation 设计为 pre-serialized room chunks + deterministic slice manifest，避免每玩家重新 JSON serialize。
- 增加 “snapshot bytes copied per tick” 与 allocator churn 指标。
- 对 1000 players 场景单独要求 p99/p999 benchmark，不能只给 p99 <100ms 单值。

### P3 — Medium — Pathfinding 全局 100,000 explored nodes/tick 在 500/1000 玩家下每人份额过小，API 体验与预算冲突

按 fair-share：500 active players 时每人 200 nodes/tick；1000 players 时每人 100 nodes/tick。但 host_path_find 允许每玩家 10 次、path result 500 nodes。实际 A* 在 50×50 房间中一次稍复杂路径就可能超过 100–200 explored nodes。

这不是确定性问题，但会导致大规模场景下 path_find 大量 deterministic fail，玩家必须自建缓存/局部规划，SDK 体验可能崩。

建议：
- 区分 cached path query 与 uncached search budget。cache hit 不消耗 explored_nodes 或消耗极低。
- world.toml 中按 active_players 动态调低 per-player path_find calls，避免“10 次调用但每次都失败”。
- 提供 deterministic partial path / bounded A* contract，而不只是 fail。

### P4 — Medium — Phase 2a inline serial command loop 是关键瓶颈，需要分区化路线更明确

Phase 2a 因先到先得竞争采用全局串行 apply，最坏 1000 players × 100 commands = 100k commands/tick。文档 benchmark gate 要 validate 100k <50ms、apply 100k <100ms，这是很激进但可测。

风险在于大量命令互不相干（不同 room）却被全局排序串行化，浪费并行度；但一旦 room partition，又会引入跨 room determinism 问题。

建议：
- Phase 2a 可按 `(room_id, affected_room_set)` 做 deterministic partition：单 room commands 在 room 内串行，不相交 rooms 并行；跨 room commands 进入 cross-room serial lane。
- sort_key 保持全局可复现，但 apply 可在证明不相交的 partition 中并行。
- Manifest 中加入 Phase 2a partitioner 的 R/W 声明与 CI deterministic equivalence test（serial vs partitioned state_checksum 相同）。

### P5 — Medium — FDB room-partition commit 的 p99 <500ms 会侵蚀 World tick 预算

World 模式 commit 预算在 `engine.md` 是 ≤50ms p99；但 `05-persistence-contract.md` room-partition benchmark 允许 1000 players / 200 rooms p99 <500ms。这两个预算口径不一致。若 commit 真到 500ms，World 3s tick 尚可能承受，但与表中 50ms p99 合同冲突；Arena 300ms tick 更不可接受。

建议：
- 分开定义 MVP single-tx、World room-partition、Arena commit budgets。
- 500ms 只能是 stress benchmark ceiling，不应与 50ms p99 production SLO 同时作为硬合同。

### P6 — Low — JSON ABI 对 WASM tick output 与 snapshot 输入可能成为性能热点

WASM ABI 以 JSON snapshot/CommandIntent 为核心，简单易调试，但每 tick 大量 JSON parse/serialize、UTF-8 validation、allocation 会消耗 CPU。500 players × 256KB 输入已经是每 tick 上百 MB 级 JSON 处理。

建议：
- 保留 JSON as debug/profile，生产 ABI 提供 canonical binary codec（版本进入 TickTrace）。
- SDK 可隐藏 binary codec，玩家仍以 typed API 编程。

## State Machine Gaps

1. Room state machine
   - neutral/reserved/owned/contested/abandoned 已列出，但 contested 的多玩家（>2）情况、simultaneous abandon+claim、reservation timeout 与 claim 同 tick 的裁决顺序不够完整。
   - 建议：把 RoomState transition 写成 table：current_state + ordered input/event + guard + next_state + emitted effects。

2. Deploy state machine
   - VALIDATE → UPLOAD_PREPARE → MANIFEST_COMMIT → ACTIVATION_PENDING → ACTIVE/FAILED 已较完整。
   - 缺口：activation_tick 到达但 upload pending “等待最多 30s” 是否阻塞 tick？若不阻塞，期间每 tick terminal state 如何记录？建议定义为 non-blocking: mark failed at first activation check after timeout; drone continues old module。

3. Tick failure state machine
   - COLLECT crash、Phase 2a panic、FDB commit fail、broadcast fail 等已覆盖。
   - 缺口：Phase 2b panic/OOM 未单独列出，当前只写 Phase 2a panic/OOM。Phase 2b 同样需要 snapshot restore、COLLECT buffer reuse、attempt_id increment。

4. Special attack state machine
   - Hack/Drain/Overload/Debilitate/Disrupt/Fortify 有局部描述，但 S14/S22 的 intent apply、duration decrement、expire reversal 的精确先后仍可能有 off-by-one。
   - 建议：为每个 status 给出 per-tick transition table，尤其是 “apply 后是否同 tick decrement duration”。

5. Room-partition / cross-room transaction state machine
   - 当前是最大缺口。prepare/commit/abort/timeout/retry/fallback 没有 determinism-safe 状态机。
   - 建议：不补齐前，500+ players 的 room-partition 容量声明只能算方向，不能算完整合同。

## Bottleneck Analysis

1. Tick 关键路径排序
   - Highest risk: COLLECT snapshot stitching + WASM dispatch/reset + host functions/pathfinding。
   - Second: Phase 2a serial command validate/apply at 100k commands/tick。
   - Third: FDB commit under room partition / cross-room operations。
   - Broadcast/NATS/Dragonfly 不应回滚 tick，正确地被放在非权威路径。

2. 500 players / 5000 drones
   - 在 3s World tick 下，若 per-player WASM p50 5ms、worker pool 256、snapshot stitching 接近 0.5ms/player，目标 500 是可信但需要 benchmark 证明。
   - 主要风险是 p99 玩家 15ms 导致排队，以及 host_path_find/cache miss 造成 tail latency。

3. 1000 players / 10000 drones
   - 当前更像 hard cap aspiration，不应作为默认可保证容量。
   - 需要 room partition、snapshot zero-copy/binary codec、aggregate CPU admission、worker pool OS overhead benchmark 全部通过后才能承诺。

4. ECS 并行调度
   - Phase 2b 的并行已经较保守，性能收益有限但确定性风险低，这是合理取舍。
   - 真正需要并行化的是 Phase 2a 的 non-overlapping room command apply；但这必须以 deterministic partition proof 为前提。

5. WASM fuel metering overhead
   - Fuel metering 本身合理；更大的 overhead 是 per-tick Store/Instance reset、JSON snapshot copy、host function boundary、pathfinding。
   - 建议 benchmark 以 “玩家 tick empty module / path-heavy module / 256KB snapshot module / max host calls module” 四类 profile 分开测。

6. FDB 热点
   - tick_head / manifest / hash_chain 是天然热点，但小对象单写可接受。
   - 500+ 场景必须避免每 tick 全局大事务；room partition 是正确方向，但 cross-room 原子语义必须先补齐。

## CrossCheck — 需要跨方向检查

- CX1: Room-Partition 的 cross-room 2PC / best-effort fallback 可能破坏架构一致性与故障恢复语义 → 建议 Architect 检查 room partition 是否应进入 Phase 1 硬合同，以及跨 room 操作的 commit/abort 权威模型。

- CX2: world_seed secrecy、seed bump runbook、赛中不可预测与 replay 可验证之间存在安全边界问题 → 建议 Security 检查 seed material 的访问控制、日志泄露面、admin TickTrace 可见性、commit-reveal 是否必要。

- CX3: `NotVisibleOrNotFound`、debug_detail detail_level、admin trace 与 player trace 的差异会影响信息泄露 → 建议 Security/API-DX 检查错误码在 competitive/practice/training 模式下的默认暴露策略。

- CX4: Pathfinding fair-share 在 500/1000 玩家下每人节点份额很低，可能造成编程体验差 → 建议 Designer/API-DX 检查 SDK 是否提供本地 path cache、partial path、失败降级模式。

- CX5: Fuel “语言公平”表述过强，可能误导玩家预期 → 建议 API-DX/Designer 检查玩家文档中如何解释 fuel、host function cost、不同语言 SDK 的性能差异。

- CX6: 特殊攻击优先级链 Hack > Drain > Overload > Debilitate > Disrupt > Fortify 是否符合玩法反制直觉（例如 Disrupt 排在 Fortify 前但低于 Hack/Drain） → 建议 Game Designer 检查该优先级的玩法公平性；本评审只确认它需要唯一权威与确定性。

## Required Follow-up Before Full Approve

1. 修复 `02-command-validation.md` 与 `06-phase2b-system-manifest.md` 的 Phase 2b/status_advance 顺序冲突。
2. 明确 RNG seed disclosure boundary；至少区分 seed_epoch id 与 secret seed material，禁止赛中玩家可见。
3. 将 room-partition cross-room “best-effort fallback” 改为 deterministic abort/retry 或补完整原子状态机。
4. 统一 WASM output batch size 256KB vs 1MB 的冲突。
5. 把 entity allocator / pending buffers / ledger buffers 加入 Bevy snapshot/restore 必捕获清单。
6. 将 1000-player hard cap 标注为 benchmark-gated，不作为默认性能承诺。
