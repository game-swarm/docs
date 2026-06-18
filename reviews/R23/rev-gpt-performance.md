# R23 性能评审 — GPT-5.5

## Verdict

CONDITIONAL_APPROVE

设计已经从早期“每玩家全量序列化 / tick 内 JIT / FDB 写大对象”的高风险形态，收敛到较合理的性能边界：两阶段 snapshot、WASM 预编译、worker pool、FDB 小事务、对象存储异步 blob、host function budget 与 pathfinding fair-share 都是正确方向。

但当前性能合同里仍有几个会直接影响大规模 tick 稳定性的缺口。尤其是 1000 active players / 10000 drones 下，Phase 2a 串行命令循环、每 tick Bevy World 深拷贝、snapshot stitching、worker pool 与 CPU/cgroup 配额之间的模型存在不一致。建议在进入实现前补齐基准场景、热路径数据结构和 CI perf gate；否则“World 3s tick 可达”基本可信，但“Arena 300ms / 1000 players hard cap 可达”证据不足。

## Strengths

- 两阶段 snapshot 将复杂度从 `O(players × entities)` 降为 `O(entities + players × visible_entities)`，这是最大性能收益点。
- WASM 部署时预编译、tick 时只实例化，避免 tick 关键路径上出现 Cranelift 编译抖动。
- `worker pool + per-tick Store reset` 比 fork-per-tick 实际可行，且配合 cgroup/seccomp 保留隔离边界。
- Host function 有总调用数、单函数次数、输出大小和 fuel 成本，`host_path_find` 也有全局 explored_nodes budget，避免明显无界计算。
- FDB 只提交 head/manifest/hash/pointer，小对象事务 + blob 异步上传，避免把 replay/debug 大对象拖入 tick commit 路径。
- Tick retry 复用 COLLECT buffer，不重新执行 WASM，避免 FDB 冲突导致双倍 fuel 和非确定性输出。

## Concerns

### P1 — High — Phase 2a 串行命令循环可能成为 1000 玩家瓶颈

允许 `100 commands/player/tick`，1000 玩家即 100000 条命令。当前 Phase 2a 逐条按 canonical order 校验并 inline apply，且很多命令依赖当前 Bevy World 状态，天然串行。若每条 validate+apply 平均只需 3–5µs，100000 条就是 300–500ms，已经吃满或超过 World EXECUTE 400ms，更不可能满足 Arena EXECUTE 50ms。

建议：明确 MVP 的实际 command cap 是否低于 100；在 CI 增加 100k command synthetic benchmark；对可按 room/target 分区的命令做冲突图批处理，只让跨分区竞争走串行 spine。

### P1 — High — Bevy World 深拷贝用于 rollback 成本未纳入预算

Tick 协议要求 Phase 2a 前 `world.snapshot()` 深拷贝完整 Bevy World，并在 FDB commit 失败时 restore。容量合同允许 50000 entities。完整 ECS component/resource 深拷贝的 CPU 与内存带宽成本可能达到数十毫秒，且会造成 cache churn；如果 keyframe/delta/trace buffer 同时存在，内存峰值也会显著上升。

建议：把 `world.snapshot()` 计入 EXECUTE 预算，增加 50k entity / full component mix 的 clone+restore benchmark；优先考虑 command journal undo-log 或 archetype-level copy-on-write，而不是每 tick 无条件全量深拷贝。

### P1 — Medium — Worker pool、cgroup CPU 与 fuel admission 模型不一致

文档同时给出 aggregate admission 公式（32 cores × 500 MIPS × 2.5s = 40000M instructions/tick）、worker_pool 默认 256、hard cap 1000、以及每 sandbox `cpu.max = 250000 3000000`。如果真为 1000 active players 保留 1000 worker，每个 worker 0.25 CPU 秒，理论 cgroup 配额总和远超 32 核物理预算，最终会在宿主调度层排队；如果只用默认 256 worker，则 1000 玩家必须排队，per-player 2ms 的 hard-cap 推导过于乐观。

建议：定义全局 sandbox CPU semaphore 或 core-token scheduler，使 fuel、worker 数和物理 cores 三者一致；hard cap 1000 应以 perf proof gate 开启，而不是只靠配置上调。

### P2 — Medium — Snapshot stitching 的 worst-case 仍可能很重

每玩家最多 9 房间可见、WASM snapshot 256KB cap。1000 玩家 worst-case 每 tick 可能产生 256MB 输入写入 WASM memory，再加 JSON encode/decode 与 copy in/out。即使 snapshot 分片复用，按玩家过滤、截断排序、序列化和写入线性内存仍可能成为 COLLECT 主要开销。

建议：将 snapshot wire format 从 JSON 迁移或预留为 canonical binary format；按 room 分片预编码，玩家视野只做 slice manifest + bounded copy；对 `1000 players × 256KB` 做 p99 benchmark。

### P2 — Medium — Pathfinding budget 在 1000 玩家下可用性很低

全局 `100000 explored_nodes/tick` fair-share 到 1000 玩家仅 100 nodes/player/tick，但 API 允许 10 次 path_find。实际每次复杂路径很容易超过 100 nodes，结果会大量 deterministic fail。性能上安全，但玩法层面可能导致高负载下 pathfinding 退化为不可用。

建议：增加跨 tick path cache、目标局部流场/room-level route cache；把 per-player share 暴露给 SDK，让玩家能在 tick 开始时知道本 tick path budget。

### P2 — Medium — FDB 热点仍需 key-space 设计证明

“FDB 小事务”方向正确，但 `tick_head`、hash chain、fuel ledger、commands/rejections 若集中在单 tick 前缀或单全局 head key，会形成严格串行热点。3s World tick 可能可接受，Arena 300ms 会更敏感。

建议：明确 FDB key layout：全局 head 单 key 只做 version pointer，commands/fuel/rejections 按 tick+player/room 分散写；在 CI 或 staging 中测 300ms tick 下的 commit p99 与 conflict rate。

## Bottleneck Analysis

- COLLECT 热点：WASM 执行本身已被 fuel/deadline 控制，真正风险在 snapshot filtering/stitching、JSON serialization、WASM memory copy、worker scheduling overhead。
- EXECUTE 热点：Phase 2a serial command loop 是最明显 critical path；Phase 2b 已有 serial spine + parallel sets，但可并行收益会被 2a 抵消。
- COMMIT 热点：FDB 小事务策略正确，主要风险从“事务太大”转为“单 head/hash-chain 热 key + commit p99”。
- BROADCAST 热点：设计为不回滚 tick，性能风险较低；但 1000 玩家观战/客户端 fan-out 需要 gateway/NATS 背压策略支撑。
- WASM metering：fuel + epoch + cgroup 多层限制合理；需要避免 host function fuel 成本低估，尤其 `host_get_objects_in_range` 与 `host_path_find`。

## Throughput Estimates

基于文档给出的 32 cores、500 MIPS/core、2500ms COLLECT budget，单 tick aggregate budget 约 40000M instructions。

- 500 players：fair-share 约 80M instructions/player/tick；若平均 WASM 5ms，32 核理想 COLLECT wall time 约 78ms，256 workers 排队模型约 10ms，主要开销会转移到 snapshot 与调度。
- 1000 players：fair-share 约 40M instructions/player/tick；若平均 WASM 5ms，32 核理想 COLLECT wall time 约 156ms，256 workers 排队模型约 20ms，但 per-player 可用预算会被 snapshot、host call、scheduler overhead 明显压缩。
- 1000 players × 100 commands：Phase 2a 最坏 100000 serial commands/tick；只要单命令超过 4µs，EXECUTE 400ms 就会被吃满。
- 1000 players pathfinding：fair-share 只有 100 explored nodes/player/tick；更像 DoS 防线，不像可舒适使用的寻路预算。
- 1000 drones 目标：在 50 drones/player cap 下相当于约 20 active players。若不是所有玩家都输出满 100 commands，World tick ≤100ms 的模拟核心可达；但要包含 COLLECT/WASM/snapshot/FDB 后，≤100ms 只适合作为 microbenchmark 目标，不应作为完整 tick SLO。

## CrossCheck — 需要跨方向检查

- CX1: Phase 2a 串行 inline apply 与“ECS 可并行”之间存在架构张力 → 建议 Architect 检查是否能以 room/target conflict graph 拆分 command execution，避免所有玩家命令落入单串行瓶颈。
- CX2: `world.snapshot()` 深拷贝作为 rollback 机制可能与 Bevy ECS 数据布局冲突 → 建议 Architect 检查 undo-log / copy-on-write / transactional component storage 的实现可行性。
- CX3: Snapshot truncation 会把敌方堆实体造成的信息压力转化为受害方观测损失 → 建议 Security 检查这是否构成 visibility DoS / competitive griefing，并确认惩罚策略不会被反向利用。
- CX4: 1000 worker hard cap 与 cgroup CPU 配额可能产生宿主级调度争用 → 建议 Security/Operations 检查 sandbox cgroup 层级是否有全局 CPU 上限，防止配置误开导致整机抖动。
