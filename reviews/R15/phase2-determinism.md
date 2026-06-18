# R15 Phase 2 CrossCheck — Determinism 补充阅读

## Verdict

REQUEST_MAJOR_CHANGES remains valid. Phase 2 没有推翻 Phase 1 的确定性结论；它把若干原本跨方向的疑点收敛成同一个根因：R15 仍缺少可机器校验的权威执行合同。CommandAction/CustomActionRegistry、simulate/dry-run、ECS partial parallelism、host function ABI/fuel/error 都必须进入同一个 replay input envelope / manifest 体系，否则 `tick(seed, state, commands) -> new_state` 不能证明闭包。

## Strengths

- API/DX、Security、Architect、Performance 四个方向都认同 deferred command model、host functions 只读、WASM 不直接 mutate state 是正确基础。
- 多份报告独立要求 machine-readable registry / manifest，这与确定性方向要求的 Limits Manifest、System Manifest、canonical codec、StableEntityId 一致。
- Performance 对全局 admission/reject 的要求可转化为 deterministic reject contract；这比依赖 wall-clock timeout 更适合 replay。
- Security 对 worker pool reset、simulate 可见性、host buffer boundary 的关注，补强了确定性方向的“隐式状态泄漏”风险面。

## CrossCheck Findings

### API/DX CX1 — Command 数量、默认特殊攻击与 `CustomActionRegistry` 边界

CrossCheck item -> API/DX 指出 core CommandAction、默认特殊攻击、`CustomAction` / `CustomActionRegistry` 在多文档中同时出现且语义不一致；Speaker CX4 要求 Determinism 判断 registry 可变性是否进入 replay 输入外。

Finding -> 这是 replay stability 的 high risk。如果默认特殊攻击有时是一等 enum、有时通过 registry 动态派发，那么同一 serialized command 在不同 world rules / registry version 下可能解析为不同 validator/apply function。若 registry 注册顺序、Rhai script 加载顺序、插件 HashMap 顺序或 server-local config 未进入 TickTrace，replay verifier 无法从 `seed,state,commands` 推导 `new_state`。动态 registry 不是禁止项，但必须满足：

- core envelope 固定，wire action type 使用 canonical fully-qualified id；
- registry snapshot/version/hash 进入 TickInputEnvelope 与 TickTrace；
- dynamic action 的 validation/apply function 只能来自 world_config/mod manifest lock；
- registry iteration order 不得参与执行，冲突按 canonical action id 排序；
- unknown/disabled action 的 error code 必须 deterministic。

disposition -> high. 并入 B3/B4，同时补充 B1：CommandAction registry 必须是 replay manifest 的一部分；否则为 blocker。

### API/DX CX2 — Host function buffer ABI、负数错误码、fuel/host budget 交互

CrossCheck item -> API/DX 指出 Host Function 返回裸 i32 / negative error codes / buffer ABI / fuel 与 host call budget 映射不闭合，要求 Security 检查边界；本任务补充 deterministic error ordering 视角。

Finding -> 这是 medium-high risk，取决于 host error 是否影响 CommandIntent 输出。如果 WASM 根据 host call 返回码分支生成不同 commands，那么 host function ABI 就是确定性输入的一部分。必须定义：

- buffer 太小时返回固定错误还是所需长度；如果返回所需长度，长度计算必须基于 canonical serialization；
- `out_ptr/out_len` 越界、输出截断、timeout、budget exhausted、visibility redaction 的优先级顺序；
- fuel exhausted 与 host call budget exhausted 同时发生时的 deterministic tie-break；
- host error negative code registry、SDK exception mapping、TickTrace 中是否记录 host calls/errors；
- `host_get_objects_in_range` / path_find 等输出排序和 encoding 必须 canonical。

若错误优先级依赖检查顺序、wall-clock timeout 或 buffer write side effect，不同节点可能返回不同 error，进而生成不同 CommandIntent。建议建立 `HostFunctionResult` enum 与 `HostErrorPriority` 表：先 memory bounds，再 ABI version/schema，visibility, budget, function-specific validation, output-size；timeout 只能作为 sandbox failure，不得与 partial output 共存。

disposition -> high for replay-affecting host functions; medium if host errors are fully recorded and replay never reruns COLLECT. 需要作为 HostFunction Registry 的确定性合同补入 B4/B5。

### Security CX1 — long-lived worker pool 与 per-tick Store reset

CrossCheck item -> Security 要求检查 sandbox worker pool 是否保留 JIT/runtime state、host-side cache、FD、signal handler 或 per-player residual state；Architect 也指出 Store/Instance/Memory/CallerContext/HostCallCounters 生命周期不清。

Finding -> 对普通 replay（不重跑 WASM）影响较小，但对在线 tick 产生命令的跨节点一致性是 high risk。long-lived worker 可复用 Engine/Module/CompiledCode，但不得复用任何可观察的 per invocation state。尤其是：linear memory、globals/table、fuel counter、epoch deadline、host call counters、path_find visibility cache handle、output buffer、caller context、RNG host API context。若 worker pool 调度导致玩家 A 命中缓存、玩家 B 不命中，且 cache miss timeout 或 host budget 表现不同，会变成非确定性 oracle。

必须写 Sandbox Object Lifecycle 表：

- reusable: Wasmtime Engine、compiled Module、read-only code cache；
- per invocation new/reset: Store、Instance、Memory、CallerContext、HostCallCounters、fuel/epoch、WASI context、output buffer；
- allowed cache: only pure function cache keyed by canonical inputs and visibility fingerprint，且 cache hit/miss 不改变 semantic result，只改变 cost；
- forbidden: player gameplay state、last error、last output length、FD table、random stream cursor 跨 invocation 残留。

disposition -> high. 并入 B5；若 worker residual state 可影响 host return 或 command output，则升级 blocker。

### Security CX2 / API-DX CX6 — `swarm_simulate` / dry-run 的 replay 与 oracle 边界

CrossCheck item -> Security 指出 `swarm_simulate` snapshot copy、fuel budget、结果可见性可能成为高精度战术 oracle；API/DX 指出 simulate 返回 “deterministic replay” 但数据结构未定义，且不执行其他玩家 WASM / 使用 NPC-only world 可能误导。

Finding -> simulate 不应进入 authoritative `tick()` 状态机，也不应产生可被正式 replay 采纳的 hidden state、fuel refund、cooldown、cache warmup 或 world_seed draw。确定性风险有两类：

1. State pollution: simulate 若复用 Bevy World、worker pool、path cache、RNG stream cursor、fuel counters、module instance，可能改变后续真实 tick。
2. Oracle leakage: simulate 若返回比玩家 snapshot 可见更多的信息，或通过 deterministic failure/error timing 暗示不可见实体，会突破 visibility contract。

建议把 simulate 定义为 side-effect-free fork：输入为 `(visible_snapshot, player_commands, explicit assumptions, rules_manifest_hash, rng_seed_for_simulation)`，输出为 `SimulateTrace`，并标注 `authoritative=false`、`confidence/assumptions`、`visibility_mode`。simulate 使用独立 namespace seed（例如 `simulate_preview`）且不消耗 world authoritative RNG ordinal；所有 caches 要么禁用，要么使用 separate namespace；任何 failure 不写入 TickTrace/fuel ledger。

disposition -> high for product/security oracle; medium for authoritative replay if side-effect isolation is made explicit. 需要补入 MCP authz/visibility matrix 与 simulate schema。

### Architect / Performance CX — ECS partial parallelism、System Manifest 与排序稳定

CrossCheck item -> Architect A4/A8 与 Performance CX1 都指出 ECS schedule 在“serial spine + parallel sets”和 20-system `.chain()` 之间冲突，且 Bevy 本身不保证确定性；任务要求核查 manifest 是否足以证明排序稳定。

Finding -> 现有 manifest 还不存在，因此不能证明排序稳定。partial parallelism 可以 deterministic，但条件是 manifest 不只是性能文档，而是 replay 合同：

- 每个 system 有 stable id、version、read/write component/resource set、barrier、must-before/must-after、parallel group id；
- group 内无可观察共享写入，或按 room/owner/stable entity partition 明确定义 reduce/merge order；
- 每个 system 内实体迭代必须显式按 `StableEntityId` 或 canonical key 排序，不得依赖 Bevy query/archetype order；
- entity creation/despawn queues 必须有 deterministic flush order；
- manifest hash/version 进入 TickTrace 与 replay verifier；
- CI 在不同线程数、schedule executor、map insertion order 下比较 state_checksum。

`R/W manifest` 是必要但不充分：它能证明无数据竞争，不能证明 iteration/reduction/order stability。若 parallel set 写不同实体但 later system 读取 aggregate map，则 aggregate construction order 也必须 canonical。

disposition -> high. 并入 B2；如果 R16 仍无 authoritative Phase 2b System Manifest，应保持 blocker。

### Performance CX / Security H2 — Global admission、fuel、timeout 与 deterministic rejection

CrossCheck item -> Performance 要求全局 command/pathfinding/sandbox CPU admission control；Security 要求所有 REST/MCP/WS 方法有 max body/output/rate limit；任务要求检查 fuel budget 是否需要 deterministic error ordering。

Finding -> 全局预算必须以 deterministic reject/admission 表达，而不能依赖实时 worker 可用性或 wall-clock race。否则同一 tick 在不同节点上可能因为 CPU 调度、cache warmth 或 worker pool occupancy 不同而采纳不同玩家输出。建议：

- COLLECT admission 先按 canonical active player order / shuffled order / fair-share budget 裁决，裁决结果记录到 TickTrace；
- 超过 global command/path/pathnodes/hostcall/fuel budget 的 command 或 host call 返回固定 rejection/error；
- wall-clock timeout 只用于保护在线执行，正式 replay 不重跑 COLLECT；若多节点在线执行需要共识，timeout decision 必须由权威 engine 记录；
- per-player 与 global budget 冲突时定义优先级，例如 memory bounds > schema > per-call > per-player > per-room > global > timeout。

disposition -> high. 并入 B6 与 Determinism T6；需要 Limits Manifest + Error Ordering Manifest。

### Snapshot / visibility truncation — Architect/Performance/Security 交叉项

CrossCheck item -> Performance CX2 与 Architect A5 指出 truncation bucket 顺序跨文档不一致；Security 指出 player_view/full/simulate/replay privacy 可能形成 oracle。

Finding -> 这是 replay input determinism 与 fairness 的 medium-high risk。snapshot 是 WASM command generation 的输入；如果截断顺序、distance reference、critical bucket overflow 或 omitted_counts 计算不同，玩家会提交不同 commands。必须把 visibility/truncation algorithm 也纳入 core determinism contract，而不是 UI/性能附录。

disposition -> high if snapshot is rebuilt during replay or multi-node COLLECT; medium if replay only consumes recorded Command[] but online cross-node consistency still matters. 并入 B1/B2 修订清单。

## State Machine Gaps

- Command registry state machine: 缺少 `registered -> enabled -> deprecated -> disabled` 与 core enum collision、world rules upgrade、replay old tick 的处理。
- Simulate state machine: 缺少 fork/execute/report/discard 的副作用边界，未定义 cache/fuel/RNG/trace 是否隔离。
- Host function state machine: 缺少 memory bounds、buffer too small、visibility redaction、budget exhausted、timeout、serialization overflow 的优先级和 terminal behavior。
- ECS schedule state machine: 缺少 single authoritative system manifest；parallel groups 的 barrier、flush、entity spawn/despawn、aggregate reduction 未闭合。
- Admission/budget state machine: 缺少 global/per-player/per-room budget 冲突时的 deterministic reject order。
- Replay envelope: 缺少 registry hash、system manifest hash、limits manifest hash、host ABI version、canonical codec version、visibility/truncation version、simulate exclusion marker。

## Non-Determinism Sources

- Dynamic registry not locked: Rhai/mod/plugin registration order、server-local config、CustomAction namespace collision。
- Bevy internals: query/archetype iteration order、EntityId allocation/reuse、parallel schedule executor differences。
- Host ABI: negative error priority, buffer length calculation, canonical serialization size, timeout vs budget order。
- Worker pool residuals: reused Store/Instance state, host-side caches, last error/output buffers, FD/WASI context, fuel counters。
- Wall-clock admission: sandbox timeout, worker availability, path_find cache miss latency, CPU scheduling。
- Visibility/simulate oracle: full-map MCP views, dry-run assumptions, NPC-only simulation misleading tactical output。
- Serialization and maps: JSON field order/string escaping/size, HashMap iteration in registries or error details。

## Required Additions Before Freeze

1. Add `ActionRegistryManifest` / `game_api.idl` lock: core actions, custom actions, host functions, errors, limits, schema versions, and manifest hash in TickTrace.
2. Add `Phase2bSystemManifest`: stable system ids, R/W sets, barriers, parallel sets, entity iteration key, spawn/despawn flush order, manifest hash.
3. Add `HostFunction ABI Determinism` table: memory/buffer/error/budget/timeout priority, canonical output encoding, and negative code registry.
4. Add `Simulate Isolation Contract`: side-effect-free fork, visible-only inputs, separate RNG/cache namespace, non-authoritative trace schema.
5. Add `Deterministic Admission/Error Ordering`: global budgets, fair-share, reject order, and TickTrace recording for timeout/admission decisions.

## Final Disposition Table

| CrossCheck item | Finding | disposition |
|---|---|---|
| CommandAction vs dynamic registry | Replay unsafe unless registry/version/hash is locked in TickInputEnvelope and action dispatch is canonical | high |
| simulate/dry-run | Must be side-effect-free, visible-only, separate RNG/cache namespace; otherwise oracle/state pollution risk | high |
| ECS partial parallelism + manifest | R/W manifest necessary but insufficient; need stable iteration/reduction/flush order and manifest hash | high |
| host function buffer ABI / negative error codes | Replay-affecting host returns need deterministic error priority and canonical encoding | high |
| fuel / host / global budget | Must reject/admit by deterministic order, not worker availability or wall-clock race | high |
| snapshot truncation / visibility | Must become core determinism contract with canonical bucket/distance/overflow handling | medium-high |

