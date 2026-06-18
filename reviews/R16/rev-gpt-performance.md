# R16 Performance Review — GPT-5.5

## Verdict

CONDITIONAL_APPROVE

R16 相比前序设计已经具备可落地的性能合同：tick pipeline 有明确 p99 预算，WASM fuel / wall-clock / memory / host-call / pathfinding 都有硬上限，FDB 从“每 tick 写全量”收敛为 manifest + hash + pointer 的小事务，快照也从 per-player 全量序列化改为 room shard + visible slice。以设计阶段标准看，性能方向可以进入下一轮共识，但仍需修正若干 P1 合同不一致与最坏路径预算缺口，否则 1000 活跃玩家/10000 drones 的 hard cap 下，tick ≤3s 可以靠超时降级维持，tick 内模拟质量和可预测性会明显下降。

## Strengths

1. Tick 预算已经从愿景落到硬合同：World tick interval 3000ms，SNAPSHOT ≤50ms，COLLECT ≤2500ms，EXECUTE ≤400ms，COMMIT ≤50ms，BROADCAST ≤50ms，且有 soft/hard deadline 与 degraded mode。
2. 快照路径的复杂度方向正确：tick 初始一次性构建完整快照、按房间分片，再按玩家 visible rooms 拼接，避免 `O(players × entities)` 重复全量序列化。
3. WASM sandbox 预算闭合度高：10M fuel、64MB linear memory、128MB cgroup、2500ms deadline、1000 host calls、10 path_find、256KB output、5MB module、30s compile 均有明确超限行为。
4. Host function 表对昂贵查询进行了显式计费，特别是 `host_path_find = 500 × explored_nodes + 200 × expanded_edges + cache_miss_penalty`，能防止“免费寻路”成为 tick 黑洞。
5. FDB 写入策略明显收敛：FDB 只存 head/manifest/hash/pointer，小事务推进世界 head；TickTrace/keyframe/delta 进对象存储或 append-only log，减少 16MB+ 事务和热点写放大风险。
6. ECS 调度不再完全串行化：文档至少定义了 serial spine + 并行 regeneration/decay 的方向，并要求通过读写矩阵证明并行安全。

## Concerns

### P1 — Tick 预算存在内部不一致，Arena/World 合同会诱导错误实现

Severity: High

`design/engine.md` 给出 World EXECUTE ≤400ms、Arena EXECUTE ≤50ms；`specs/core/01-tick-protocol.md` 早期状态机仍写 EXECUTE 超时 500ms，后续 §8 又说 EXECUTE 不单独超时，由 COLLECT+EXECUTE 总预算控制。实现者若按 500ms、400ms 或“不单独超时”任一解释实现，监控、CI 和调度器 admission 都会分叉。

性能影响：
- World 预算表中 SNAPSHOT+EXECUTE+COMMIT+BROADCAST = 550ms，留给 COLLECT 的实际 3s 内空间只有 2450ms，但 COLLECT deadline 又是 2500ms，两者已经相差 50ms。
- 如果严格执行 COLLECT 2500ms，再叠加 EXECUTE 400ms、COMMIT 50ms、BROADCAST 50ms，World tick 最坏为 3050ms，超过 3000ms 目标。
- Arena 更紧：20+200+50+20+10 = 300ms，任何调度抖动、队列延迟、对象分配都会超 tick interval。

建议：统一为一个权威 budget manifest，并明确 `tick_interval_ms` 是目标而非硬 deadline 时，CI p99 以 `tick_soft_deadline_ms` / `tick_hard_deadline_ms` 为准；若 3s 是硬 SLA，则 COLLECT deadline 应扣除固定阶段预算和 jitter reserve，例如 World COLLECT hard cap ≤2350ms。

### P1 — 1000 玩家 hard cap 下 sandbox CPU 配额远超单节点常规容量

Severity: High

API registry 给出 sandbox cgroup `cpu.max = 250000 3000000`，即每玩家每 3s 最多 0.25 CPU-s。按 hard cap 1000 active players，理论 sandbox 配额为 250 CPU-s / 3s tick，平均需要约 83.3 个满载 CPU core 才能让所有玩家都用满配额；500 target players 也需要约 41.7 core。

这不是安全问题，而是容量合同问题：文档同时声称“单 Engine 实例 target 500 / hard cap 1000 active players”，但没有声明单节点硬件基线、worker pool admission、超额活跃玩家降级策略、或 per-player CPU 配额随 active_players 动态缩放。若部署在 16–32 core 机器，COLLECT 会经常靠 timeout/no-op 维持 tick，而不是按 fuel 公平执行。

建议：补充硬件基线与 admission contract，例如：
- `sandbox_cpu_quota_ms_per_tick = min(configured_quota, core_budget_ms / active_players)`；
- target 500 需要 ≥48 physical cores，hard cap 1000 需要 ≥96 physical cores；
- 低于硬件基线时 hard cap 自动按 core budget 降额；
- metrics 中区分 fuel exhausted、cgroup throttled、deadline timeout。

### P1 — Phase 2a 最坏命令量 100k/tick 仍是串行 inline 热点

Severity: High

容量上限为 1000 players × 100 commands/player/tick = 100,000 commands/tick。Phase 2a 需要按 seeded player order + sequence 串行逐条校验并 inline apply，且每条命令可能访问 visibility、position occupancy、resource store、combat/health、RoomCap、Rejection trace。这个 serial spine 是 tick 关键路径上最可能突破 400ms EXECUTE 预算的部分。

Move-as-action 有助于减少每 drone 多动作，但没有减少玩家可提交命令上限；在 10000 drones hard cap 下，100k commands/tick 仍明显高于有效 drone action 数。大量无效命令也必须排序、校验、拒绝并写 trace，可能成为拒绝风暴。

建议：为 EXECUTE 增加 admission 前置层：
- per-drone main action 去重在排序前完成，只保留 canonical winning candidate 或拒绝多余命令；
- per-player accepted validation work budget，而不仅是 command count；
- Rejection trace 采样/聚合上限，避免无效命令写放大；
- CI 增加 100k commands/tick、80% invalid、热点同坐标 Move/Build、同 Source Harvest 竞争基准，证明 Phase 2a p99 ≤400ms。

### P1 — Pathfinding fair-share 在 hard cap 下过低，可能让 API 合同不可用

Severity: High

全局 pathfinding budget 为 100,000 explored nodes/tick，并按 active_players 均分。500 玩家时每人 200 nodes/tick；1000 玩家时每人 100 nodes/tick。与此同时 host_path_find 每玩家允许 10 次调用，result path 最大 500 nodes。对 50×50 room、多房间出口、障碍和不可达目标，100–200 explored nodes 往往不足以完成一次有意义 A*，更不用说 10 次。

这会形成性能上安全但产品上不可用的状态：高负载时 path_find 大量 deterministic fail，玩家为了规避可能改用 `host_get_terrain` + 自己在 WASM 内寻路，反而把成本转移到 fuel 和 host_get_terrain 调用上。

建议：把 budget 从“active_players 均分”改为“active_path_users 或 active_drones/rooms 加权”，并提供分层缓存：same-room static terrain path cache、出口路径 cache、visibility fingerprint cache。还应定义 unreachable search 的最大 expansion 和 negative-cache TTL。

### P2 — 快照构建仍存在 Bevy World 深拷贝成本风险

Severity: Medium

R16 已经消除了 per-player 全量序列化，但 tick 开始仍定义了“构建完整世界快照（Bevy World 深拷贝）”以及 FDB rollback 前的 `world.snapshot()` 深拷贝。50,000 entities、组件较多、资源/状态/metadata 全量复制时，SNAPSHOT ≤50ms 和 EXECUTE 前 rollback snapshot 成本可能叠加成为内存带宽瓶颈。

尤其是 commit retry 路径：Phase 2a 前完整 snapshot + apply + restore。如果实现为完整 archetype clone，p99 会受 allocator、cache locality、component fragmentation 影响。

建议：设计层明确 snapshot 实现约束：copy-on-write component pages、dirty component journal、archetype chunk checksum，或 command apply undo-log。至少应要求基准覆盖 50k entities、最大 component set、10% dirty entities、FDB commit failure restore ≤50ms。

### P2 — Persistence contract 与 tick protocol 对 COLLECT 重试语义冲突

Severity: Medium

`specs/core/01` 明确 FDB commit 失败时复用同一 COLLECT 结果，不重新执行 WASM，避免重复 fuel 与非确定性；`specs/core/05` §6 却写“下次循环重新执行 tick N（重跑 COLLECT → apply）”且 TickTrace 可能不同。这是性能与确定性双重风险。

如果重跑 COLLECT，1000 玩家高负载下 FDB 瞬时冲突会把 COLLECT 成本放大 N 倍，并且玩家代码可能因 snapshot/host cache/timeout 状态不同产生不同输出。性能上会导致 retry storm；确定性上也会让 TickTrace/fuel 语义难以解释。

建议：以 tick protocol 的“复用首次 COLLECT 结果”为权威，persistence contract 改为“重新 apply cached collect result，重新生成对象 blob/manifest，但不重新调用 WASM”。

### P2 — Host function 总调用上限过高，1M calls/tick 需要全局调度预算

Severity: Medium

1000 players × 1000 host calls/player/tick = 1,000,000 host calls/tick。即使多数是 cheap `host_get_terrain`，跨进程 Unix socket/gRPC、bounds check、visibility filter、serialization 都会明显占用 COLLECT budget。当前只有 per-player 上限，没有 engine-wide host-call CPU admission。

建议：增加 host-call 全局 CPU budget 与 fast path：terrain/config/rules 应尽量在 snapshot 中预填或共享 readonly mmap；对跨进程调用批处理；host function metrics 应按 type 记录 p50/p99、cache hit、bytes out、fuel charged。

### P2 — FDB 热点虽已缓解，但 world head 单 key/单事务仍需抗热点设计

Severity: Medium

FDB 小事务是正确方向，但每 tick 都会写 tick_head、tick_hash_chain、manifest、state mutation。若所有 watch/query/engine recovery 都围绕当前 head key，会产生读热点；若 state mutation key 按 entity id 分布良好则问题不大，但 room/controller/global storage 等资源仍可能是高争用热点。

建议：定义 keyspace：tick head 用 versioned append row + latest pointer；读热点通过 Dragonfly/engine memory 服务，不让客户端直接 watch FDB head；global resources/controller rows 加 shard prefix 或 room partition。CI 增加 FDB simulation 的 hotspot workload。

### P2 — TickTrace 对象写入在 commit 前同步，5s 超时与 3s tick interval 不匹配

Severity: Medium

Persistence contract 要求 Phase B 对象存储写入先于 FDB commit，object store 写入超时 5s；但 World tick interval 是 3s，Arena 300ms。若 TickTrace blob 接近 10MB、对象存储 p99 抖动，tick 会被对象写阻塞，且 5s 超时本身超过 World tick 目标。

建议：把对象写入分为 bounded hot append log 与异步对象归档；FDB commit 只依赖本地 durable WAL/hash，object store 异步完成后补 manifest 状态。若坚持对象先写，则对象写 timeout 应纳入 tick hard deadline，World ≤100ms、Arena 禁止同步对象写。

### P3 — SIMD 默认策略需要更明确的 determinism/performance tradeoff

Severity: Low

WASM sandbox 中 World 默认 SIMD true、Arena 默认 false、relaxed SIMD false。禁用 relaxed SIMD 是正确的，但普通 SIMD 仍可能放大跨 CPU 特性差异和验证矩阵。性能上 SIMD 对玩家代码有利，但 replay 不重跑 WASM，主要影响在线 COLLECT fairness。

建议：要求 deployment target CPU feature set 固定，module cache key 已含 target_arch 但还应含 CPU feature profile；跨节点迁移时若 feature profile 不一致则重编译或禁用 SIMD。

## Bottleneck Analysis

### Tick Critical Path

1. SNAPSHOT build：目标 ≤50ms。当前设计从 per-player serialization 降为 room shard，方向正确；最大风险是 Bevy World 深拷贝和 50k entities 下的 component clone/cache miss。
2. COLLECT：目标 ≤2500ms，是最大预算池。主要瓶颈不是 fuel metering 本身，而是 worker pool 并发度、cgroup throttling、跨进程 host calls、snapshot copy into WASM memory、JSON parse/serialize。
3. EXECUTE：目标 ≤400ms。Phase 2a 串行 command loop 是核心瓶颈，100k commands/tick 的排序、校验、拒绝记录和 ECS mutation 需要专门 benchmark；Phase 2b serial spine 相比 Phase 2a 风险较低。
4. COMMIT：目标 ≤50ms。小事务策略可行；风险集中在热点 key、状态 mutation 数量、object-store-before-FDB 的同步等待。
5. BROADCAST：目标 ≤50ms。NATS/Dragonfly 异步失败不回滚 tick 是正确设计；风险是 delta 计算若需要 world_before/world_after diff 全扫描，会和 snapshot 成本叠加。

### ECS Scheduling

R16 的 ECS 调度已经把被动系统分成 serial spine 与可并行集合，但性能收益仍有限：真正大头 Phase 2a 是基于公平排序的串行 inline apply，天然难以并行。若要进一步优化，应优先在 Phase 2a 前做命令预归并、按 room 分区构建无冲突 batch、对只读校验做 parallel precheck，然后在冲突点保持 canonical serial order。

### WASM Fuel Metering

Fuel metering 开销本身可接受，因为 Wasmtime 原生支持且每玩家有 10M fuel hard cap。更大的问题是 fuel 与 wall-clock/cgroup CPU 并存：fuel 限制指令数，cgroup 限制真实 CPU，epoch 限制墙钟。三者需要在 metrics 中分开，否则性能退化会被误判为玩家代码慢。Host function 成本按 fuel 收费是必要的，但跨进程 host call 的真实 CPU 还需要全局 admission。

### FDB / Object Store

FDB 从大 blob 迁出是本轮最大性能亮点。剩余风险是同步对象写入被放进 tick commit 前置路径，以及 world head/hash chain 的热点读写。建议将对象存储作为异步归档层，tick commit 的同步 durable path 只依赖本地 WAL + FDB 小事务，避免对象存储 p99 直接进入 tick p99。

## Throughput Estimates

| Scenario | Active Players | Drones | Max Commands | Max Host Calls | Snapshot Cap | Path Fair Share | Sandbox CPU Quota |
|---|---:|---:|---:|---:|---:|---:|---:|
| Target World | 500 | 5,000 | 50,000/tick | 500,000/tick | 125 MiB/tick | 200 nodes/player/tick | 125 CPU-s / 3s |
| Hard Cap World | 1,000 | 10,000 | 100,000/tick | 1,000,000/tick | 250 MiB/tick | 100 nodes/player/tick | 250 CPU-s / 3s |

Interpretation:
- 500 players target requires roughly 42 fully utilized CPU cores if every player consumes the cgroup CPU quota; practical deployment should budget ≥48 cores plus engine/FDB/network overhead.
- 1000 players hard cap requires roughly 84 fully utilized CPU cores for sandbox alone; practical deployment should budget ≥96 cores or dynamically reduce per-player CPU quota.
- 1000 drones alone is safe under current hard caps; the real stress case is not drone count but active player count × command cap × host-call cap. With 1000 drones and ≤100 active players, tick ≤100ms for simulation-only EXECUTE is plausible if Phase 2a commands are near drone count rather than command cap.
- 10000 drones / 1000 players is feasible only if most players use a fraction of their command/host/path budgets; worst-case adversarial use will hit COLLECT and Phase 2a bottlenecks before FDB.
- Arena 300ms tick is much less forgiving: the budget has essentially no jitter margin. Arena should use lower active player/entity caps or a separate compiled benchmark contract.

## CrossCheck — 需要跨方向检查

1. Architecture CrossCheck: 统一 Tick budget 权威来源，解决 400ms/500ms/无 EXECUTE 独立超时、COLLECT 2500ms 与 3s 总预算相冲突的问题。
2. Persistence CrossCheck: `specs/core/05` 的“重跑 COLLECT”应与 `specs/core/01` 的“复用 COLLECT 结果”统一，否则性能和确定性合同冲突。
3. Gameplay/API CrossCheck: Pathfinding fair-share 在 1000 玩家下只有 100 nodes/player/tick，可能让 `host_path_find` API 在高负载下不可用，需要产品语义确认。
4. Infrastructure CrossCheck: 单 Engine target/hard cap 需要绑定硬件基线、CPU core 数、worker pool 上限和 admission 降级策略。
5. Security CrossCheck: World 默认 SIMD true 需要与 sandbox/replay threat model 确认 CPU feature profile 和跨机器迁移策略。
6. Observability CrossCheck: metrics 必须区分 fuel exhausted、epoch timeout、cgroup throttled、host-call global budget exhausted、path budget exhausted，避免性能诊断混淆。
