# R15 Performance Review — GPT-5.5

## Verdict

CONDITIONAL_APPROVE

设计方向整体可通过：R15 相比典型「每玩家深拷贝/每 tick JIT/全量 FDB 写入」方案已经避开了最危险的性能陷阱，明确提出两阶段 snapshot、WASM 预编译、worker pool、FDB 小事务 + blob 外置、host function/path_find 配额、TickTrace 字段截断等关键约束。

但从 Performance 角度仍不应直接 APPROVE。当前设计的最大问题不是单点技术选型，而是若干预算表与执行模型之间仍存在不一致：硬上限允许的 command/pathfinding/WASM 并发工作量明显超过 3s World tick 和 300ms Arena tick 的可实现窗口；ECS 调度说明一边宣称部分并行，一边给出 20 system `.chain()` 主线；snapshot/rollback 的 Bevy World 深拷贝仍在 tick 关键路径上，且未给出增量/arena 快路径。因此建议在补齐容量合同、拒绝策略和调度边界后通过。

## Strengths

1. 两阶段 snapshot 是正确方向
   - 设计将 snapshot 构建从 `O(players × entities)` 降为 `O(entities + players × visible_entities)`，并按房间分片复用，避免每个玩家重复序列化完整世界。
   - 每玩家 WASM snapshot 设 256KB cap，并定义 deterministic truncation，能防止单个玩家的视野膨胀拖垮 collect 阶段。

2. WASM tick 路径避免了最昂贵的 JIT/fork 模式
   - 部署时预编译、tick 时仅实例化，且采用 long-lived worker pool，避免 500-1000 玩家场景下 fork-per-tick 的秒级开销。
   - fuel、epoch interruption、memory limit、host function count、path_find explored_nodes 上限均有明确约束，比墙钟 CPU 计费更可控。

3. FDB 写入策略基本合理
   - tick 内 FDB 只推进 head/manifest/hash/pointer，小事务提交；大型 TickTrace/keyframe 进入对象存储或 append-only log，避免每 tick 写 10MB+ 全量状态。
   - TickTrace 与状态/fuel 同事务，避免状态成功但审计缺失的回放不一致。

4. Command 执行模型偏保守但性能可预测
   - Phase 2a inline 串行保证确定性，避免复杂并发冲突解决。
   - Move-as-action 降低每 drone 每 tick 可变更数量，对 command fanout 有天然限流效果。

5. Host function 成本模型有实际防线
   - `host_path_find` 按 explored_nodes/expanded_edges 计费，并有 per-player 10 calls + 100,000 explored_nodes 上限。
   - `host_get_objects_in_range` 有响应大小和调用次数限制，降低 WASM 侧无界查询风险。

## Concerns

### P1 — High — Hard cap command budget makes EXECUTE target mathematically implausible

设计同时允许：hard cap 1000 active players、每玩家每 tick 1000 commands、World EXECUTE 预算 400ms、Arena EXECUTE 预算 50ms。这意味着硬上限为 1,000,000 commands/tick。

在 World 模式下，400ms / 1,000,000 ≈ 0.4 µs/command；Arena 下 50ms / 1,000,000 ≈ 0.05 µs/command。这个预算不足以完成 Bevy query、validation、component mutation、rejection logging、action quota check、resource contention check，更不用说 cache miss、branch mispredict 和 audit bookkeeping。

建议：
- 将 `Commands per player per tick = max 1000` 改为「全局 tick command budget + per-player fair-share」，例如 target 50-100/player、hard global 50k-100k/tick。
- 明确超限策略：超过 per-player 或 global budget 的 commands deterministic reject，不进入 Phase 2a queue。
- 将预算测试定义为 command mix benchmark，而不是只写单个上限数字。

### P1 — High — path_find 全局最坏情况仍然无界到不可承受

虽然单玩家限制为 10 次 path_find + 100,000 explored_nodes，但 hard cap 1000 players 时，全局最坏为 10,000 path_find calls/tick、100,000,000 explored_nodes/tick。

即使单节点扩展只做整数网格 A*，100M node expansions 在 3s World tick 中也会消耗大量 CPU；在 Arena 300ms tick 中更不可接受。更关键的是 path_find 是 host function，实际运行在 COLLECT 并行阶段，会和 WASM fuel、snapshot serialization、worker IPC 争用 CPU。

建议：
- 增加 world-level pathfinding budget：例如每 tick 全局 `MAX_PATH_NODES_TOTAL` 和 per-room `MAX_PATH_NODES_ROOM`。
- 将 path_find 缓存命中与 miss 分离计费：cache hit 低 cost，cache miss 按全局 token bucket 排队/拒绝。
- 对不可达目标启用强制 early cutoff，并要求 benchmark 覆盖 no-path worst case。

### P1 — High — COLLECT wall-clock budget implies impossible CPU provisioning under hard cap

hard cap 1000 players × 2500ms per-player sandbox deadline = 2500 CPU-seconds/tick 的理论上限。若玩家代码都接近 deadline 且 CPU-bound，要在 3000ms tick interval 内完成，需要约 833 cores 才能完全并行吸收最坏情况。

fuel 限制能约束指令数，但文档没有把 `10,000,000 fuel` 映射到期望 wall-clock 分布，也没有定义 worker pool 的 CPU admission control。仅靠每 worker cgroup `0.25 CPU / 3s` 或另一处 `50% CPU` 配置也存在互相冲突。

建议：
- 增加 global COLLECT admission：active sandbox workers 不等于 active players，超出并发池的玩家按 deterministic schedule 本 tick 0 指令或降采样。
- 给出 `fuel → p50/p99 wall-clock` 校准目标，例如 10M fuel 在目标 CPU 上 p99 ≤ 20ms，而不是允许 2500ms 常态运行。
- 统一 cgroup `cpu.max` 数值，当前 `250000 3000000` 与 checklist 的 `50000 100000` 表达的 CPU 配额不同。

### P1 — High — Bevy World 深拷贝仍在 tick 关键路径，可能吞掉 snapshot/rollback 预算

文档要求 COLLECT 开始构建完整世界快照；EXECUTE 前又对 Bevy World 做完整 snapshot 以支持 FDB rollback。硬 cap 为 50,000 entities，且 must capture 所有 Resource 和所有 Component。

这在 World 3s 下或许可控，但 Arena 300ms / snapshot 20ms / execute 50ms 下风险很高。深拷贝 Bevy World 往往不是纯线性 memcpy：archetype layout、sparse sets、资源对象、IndexMap、Vec body parts、ResourceStore 等都会带来分配、cache miss 和 allocator pressure。

建议：
- 明确 rollback snapshot 采用 copy-on-write、component delta journal，或 double-buffer world，而不是完整 deep copy。
- 将 COLLECT visibility snapshot 与 EXECUTE rollback snapshot 合并/复用，避免同 tick 两次大规模拷贝。
- 对 50k entities、10k drones、1000 players 的 snapshot build/restore 做 p99 benchmark 合同。

### P1 — Medium/High — ECS 并行调度描述与 20 system `.chain()` 不一致

engine.md 说 regeneration/decay 可与主线并行，只需 before death_cleanup；tick spec 却给出大量系统全部放在 `.chain()` 中，包括 regeneration、decay、controller、combat、memory_upkeep、drone_env_var 等。若实现按后者执行，Phase 2b 基本串行，Bevy 并行调度收益会显著降低。

建议：
- 将 authoritative ECS schedule 拆成 fixed serial spine + parallel sets，而不是把 20 个系统放进一个 `.chain()`。
- 每个 system manifest 声明 component/resource R/W 集，CI 检查新增 system 是否错误插入串行主线。
- 对 combat/controller/repair/global_storage 这类高 fanout system 做 room-level partition 或 query sharding 设计。

### P2 — Medium — FDB 事务语义仍可能在高并发下形成 world-head 热点

设计已经避免大 blob 写 FDB，这是亮点。但单 Engine 单 world head 每 tick 原子推进仍是天然热点；如果 TickTrace manifest、fuel records、delta pointers、state checksum 都在同一事务中写入，事务大小和 conflict range 需要严格控制。

当前文档说「小事务」「<10MB」，但没有给出 key layout、conflict range、watch/read version 策略，也没有说明 Dragonfly/cache update 是否可能读取未稳定的 head pointer。

建议：
- 定义 `/world/{id}/head` 为唯一强一致热点，其余 tick data 写 append-only immutable keys，head commit 只写 pointer/hash/versionstamp。
- 明确事务目标大小，例如 p99 < 256KB，而不是只低于 FDB 推荐上限 10MB。
- 禁止 tick 内按 player 写大量 fuel keys 进入同一事务；改为聚合 manifest + append log/hash。

### P2 — Medium — JSON ABI 在 tick 关键路径上可能成为 CPU/分配瓶颈

WASM ABI 使用 snapshot JSON 输入和 CommandIntent JSON 输出；每玩家 snapshot cap 256KB，hard cap 1000 players 即 250MB/tick 的潜在输入拷贝/解析/序列化规模。再加上输出 JSON 256KB cap，最坏内存带宽与 allocator 压力很高。

JSON 对开发者友好，但 1000 players/300ms Arena 或大型 World tick 下，serde parse/string escaping/copy into WASM memory 可能成为瓶颈。

建议：
- 保留 JSON 作为 debug/SDK 层格式，但 tick hot path 使用 binary canonical format（FlatBuffers/Cap’n Proto/postcard/bincode with schema lock）或 shared canonical compact encoding。
- 至少要求 snapshot/command JSON 使用 preallocated buffers、zero-copy slices、arena allocator，并加入 serialization p99 benchmark。

### P2 — Medium — Snapshot truncation bucket 规则跨文档不一致

engine.md 的 bucket 顺序是自机 > 友方 drone > 敌方 drone > 建筑 > NPC > 资源；tick spec 的 bucket 是关键实体、己方、敌方/资源点、友方/中立，并按距离排序。这会影响玩家可见输入、CPU 成本和 replay determinism。

建议：
- 指定单一权威 truncation order，并将其纳入 determinism test vector。
- 明确多 drone 玩家如何计算 `distance_to_drone`：最近 drone、拥有者中心点、还是每实体按可见来源 drone 最短距离。

### P2 — Medium — BROADCAST 无硬限制可能造成延迟债务

文档说 BROADCAST 不影响已提交 tick，这是正确的。但如果 delta 过大或 NATS/WebSocket fanout 积压，虽然 world tick 不回滚，客户端延迟会累积，Dragonfly 更新也可能滞后。

建议：
- 给 BROADCAST 加 backpressure contract：最大 pending delta bytes、最大 client lag ticks、超过后降级为 keyframe fetch。
- 明确 delta 计算是否复用 EXECUTE 前后变更 journal，避免再次扫描 50k entities。

### P2 — Low/Medium — Arena 预算继承关系仍需更硬的热路径分离

文档说 Arena 有独立预算：300ms tick、200ms collect、50ms execute。但许多 World 级上限仍按 1000 players、10k drones、50k entities 描述。若 Arena 共享相同 command/path_find/snapshot/fuel 上限，50ms execute 和 20ms FDB commit 难以成立。

建议：
- Arena 单独定义 active players、entities、commands、path nodes、snapshot cap。
- Arena 默认禁用或缩小 costly host functions，并采用更小 map/entity cap。

## Bottleneck Analysis

### Tick 关键路径

1. COLLECT
   - 主要成本：snapshot build + per-player visibility filter/truncation + copy into WASM memory + WASM execution + host function calls。
   - 最大风险：1000 players 同时触发高 fuel + path_find cache miss，导致 CPU 并发需求远超单节点。
   - 当前缓解：worker pool、fuel、host call count、path_find node cap、snapshot cap。
   - 缺口：缺少 global CPU/pathfinding admission control。

2. EXECUTE Phase 2a
   - 主要成本：command sorting、per-command validation、action quota、Bevy component mutation、rejection logging。
   - 最大风险：1M commands/tick 与 400ms/50ms 预算不匹配。
   - 当前缓解：per-drone main action quota、Move-as-action。
   - 缺口：缺少 global command budget；per-player 1000 commands 过高。

3. EXECUTE Phase 2b
   - 主要成本：combat/controller/repair/decay/spawn/death cleanup 等 ECS queries。
   - 最大风险：20-system chain 串行化，Bevy 并行能力无法发挥；combat/repair 类系统高 fanout。
   - 当前缓解：理论上有 regeneration/decay 并行。
   - 缺口：权威 schedule 与并行证明不一致。

4. COMMIT/FDB
   - 主要成本：world head 推进、manifest/hash/fuel/TickTrace pointer 写入、事务提交延迟。
   - 最大风险：head 热点、事务过大、冲突重试导致 tick abandon。
   - 当前缓解：large blob 外置、小事务、keyframe every K tick。
   - 缺口：key layout/conflict range/事务大小 p99 未定义。

5. BROADCAST
   - 主要成本：delta computation、Dragonfly update、NATS fanout、WebSocket 客户端背压。
   - 最大风险：广播异步积压不影响世界状态但影响玩家观测与 UI。
   - 当前缓解：gap fetch、cache fallback。
   - 缺口：缺少 pending backlog 上限与降级策略。

### ECS 调度模式

当前最应调整的是从「串行大链 + 少量例外」改成「显式 serial spine + room/field parallel sets」：

- 必须串行：death_mark → spawn → spawning_grace → combat/status effects → aging → death_cleanup。
- 可按 room 分区并行：regeneration、decay、resource production、controller repair、NPC spawn/AI、memory upkeep。
- 需谨慎并行：combat、global_storage、controller_system，因为它们可能跨 owner、room 或 shared resource 写入。

如果保持 20 system `.chain()`，1000 players/10k drones 下 Phase 2b 会变成 cache-unfriendly 串行扫描集合，不符合 Bevy ECS 选型的并行收益预期。

### WASM fuel metering 开销

Wasmtime fuel metering 本身可接受，但必须把「fuel units」校准到目标硬件上的 wall-clock，否则 10M fuel 只是安全概念，不是容量合同。

需要特别注意：
- Fuel metering 对 tight loop 可控，但 host function 的真实成本不只由 WASM fuel 体现；path_find/get_objects 必须独立 budget。
- Store reset + memory zeroing 对 64MB 线性内存若每 tick 全量清零，1000 players 最坏为 64GB/tick 内存写流量；应明确 lazy zeroing、dirty page tracking 或复用预零化 memory。
- JSON snapshot copy into WASM memory 是 fuel 外的 host 侧成本，需要计入 COLLECT p99。

### 数据库/FDB 热点

FDB 适合做权威事务推进，但不适合承载每 tick 大量 per-player/per-command 明细写入。当前设计总体知道这一点，但仍需要更强的写模式约束：

- 每 tick 只允许一个小型 head commit。
- per-player fuel/metrics/rejection detail 应聚合成 manifest/blob，FDB 存 hash+pointer。
- TickTrace immutable keys 可 append，但不要在同事务内写 1000×player 子键。
- Replay chain hash 可以放 manifest，详细链体外置。

## Throughput Estimates

基于文档给定硬值的粗略估算：

| 项目 | Target | Hard | 评估 |
|---|---:|---:|---|
| Active players | 500 | 1000 | World 可作为长期目标；Arena 需单独缩小 |
| Active drones | 5000 | 10000 | ECS 可承载，但 combat/repair/pathfinding 需 room partition |
| Total entities | - | 50000 | snapshot/rollback 深拷贝风险较高 |
| Commands/tick | 500k | 1M | 明显过高，需全局 budget |
| EXECUTE budget/command | 0.8µs target | 0.4µs hard | 不现实 |
| Arena EXECUTE budget/command | 0.1µs target | 0.05µs hard | 不现实 |
| Host calls/tick | 500k | 1M | 需全局 admission control |
| Path calls/tick | 5k | 10k | cache hit 可接受，cache miss 不可接受 |
| Path nodes/tick | 50M | 100M | 单节点 tick 内不可承受 |
| Snapshot WASM input/tick | 125MB | 250MB | World 勉强可优化；Arena 不可接受 |
| Fuel/tick | 5B | 10B fuel | 需硬件校准，不可只看 fuel 数字 |
| COLLECT CPU worst-case | 1250 CPU-s | 2500 CPU-s | 必须通过 admission/fair-share 削峰 |

### 对「1000 drones tick ≤100ms」的判断

若场景是 1000 drones、命令数受 per-drone main action 限制、path_find cache hit、多数系统按 room 分区并行，则纯 ECS simulate 达到 ≤100ms 是可行目标。

但在当前文档允许的最坏输入下，1000 drones 不等于 1000 commands：如果 1000 active players 每人可提交 1000 commands，且 host_path_find 总额度仍可达到 100M nodes/tick，则 tick ≤100ms 不成立。要让 1000 drones ≤100ms 成为可信合同，必须绑定以下前提：

- 全局 commands ≤ 50k/tick，或每 drone 只接受 1 main action + 少量 free transfer/withdraw。
- path_find cache miss 全局 nodes ≤ 1M-5M/tick，并对 no-path case early cutoff。
- snapshot 构建复用 room shards，不做 per-player deep serialization。
- ECS Phase 2b 不使用 20-system full chain，而使用 room-level parallel schedule。
- FDB commit 不在 100ms simulate benchmark 内，或 commit p99 单独 ≤20-50ms。

## CrossCheck — 需要跨方向检查

- CX1: ECS 调度权威定义存在冲突：engine.md 声称 regeneration/decay 可并行，但 tick spec 给出 20 system `.chain()`，可能导致实现者选择完全串行路径 → 建议 Architect 检查最终 authoritative schedule、system manifest 与 Bevy schedule 写法。
- CX2: Snapshot truncation bucket 顺序跨文档不一致，可能影响 determinism、玩家策略可解释性和 replay test vector → 建议 Architect 检查 truncation 规则是否需要统一到 core determinism contract。
- CX3: `world_seed` 泄露后未来 tick 可预测被接受为风险，但这会直接影响排序公平和经济竞争 → 建议 Security 检查 seed 管理、日志访问、epoch bump 与运维权限边界。
- CX4: `visibility_abuse` 降低 COMBAT 优先级属于 gameplay 惩罚，会改变玩家竞争公平性，可能被反向利用为诱导 debuff → 建议 Game Designer 检查该惩罚是否符合游戏设计，或改成资源税/实体成本。
- CX5: JSON ABI 对 SDK 友好但热路径昂贵；切换 binary canonical format 会影响多语言 SDK 设计 → 建议 Developer Experience/SDK 方向检查是否采用 debug JSON + runtime binary 的双层接口。

## Required Changes Before Full Approval

1. 定义 global command budget、global pathfinding budget、global sandbox CPU admission control，并写入 tick protocol。
2. 统一 World/Arena 独立容量合同，Arena 不得继承 World 的 1000-player/1M-command 级别上限。
3. 将 ECS schedule 改成可验证的 serial spine + parallel sets，并用 R/W manifest 约束新增 system。
4. 替换或限定 Bevy World 全量 deep copy，给出 rollback snapshot 的增量实现与 p99 benchmark。
5. 统一 snapshot truncation 规则，并加入 deterministic test vector。
6. 将 FDB transaction 目标从「<10MB」收紧到明确 p99 大小、key layout 和 conflict range 合同。

满足以上后，Performance 方向可以升级为 APPROVE。
