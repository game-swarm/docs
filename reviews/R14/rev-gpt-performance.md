# R14 性能评审（GPT）

## Verdict

**CONDITIONAL_APPROVE**

设计已经具备清晰的性能合同：tick pipeline 预算、玩家/实体硬上限、WASM fuel、snapshot cap、FDB 小事务策略、host function 预算都被显式化。作为设计阶段方案，可以进入下一轮共识；但需要在 Phase 1 设计内补齐若干关键性能约束，否则 1000 活跃玩家 / 10000 drones 的硬 cap 在最坏路径下仍有明显超预算风险。

## Strengths

1. **Tick pipeline 预算清晰**：World 模式 3000ms tick 被拆成 snapshot ≤50ms、collect ≤2500ms、execute ≤400ms、commit ≤50ms、broadcast ≤50ms，便于后续 CI 建立 p99 回归门禁。
2. **两阶段快照设计方向正确**：tick 开始一次性构建完整世界快照并按房间分片，将快照复杂度从 `O(players × entities)` 降到 `O(entities + players × visible_rooms)`，这是支持 500–1000 活跃玩家的必要前提。
3. **WASM 预算模型较完整**：fuel、wall-clock、linear memory、host function 调用、path_find 调用、输出大小、编译时预算均有硬上限；`fuel/wall-clock 耗尽则整批输出丢弃` 避免部分输出污染 tick。
4. **FDB 写入策略避免大事务**：设计明确 FDB 只推进 head/manifest/hash/pointer，大型 TickTrace/keyframe 进入对象存储或 append-only log，方向上避免了每 tick 全量世界状态写入造成的热点和 16MB 事务风险。
5. **WASM 预编译 + long-lived worker pool 是正确优化方向**：部署时编译、tick 时仅实例化，能避免 JIT 编译抖动进入 tick 关键路径。
6. **snapshot truncation 有确定性排序**：按 priority bucket + stable key 截断，保证性能保护不会破坏 replay determinism。

## Concerns

### P1 — EXECUTE 阶段最坏命令量与 400ms 预算不匹配

- **Severity: High**
- 文档允许 `Commands per player per tick = max 1000`，hard cap 1000 活跃玩家时理论上是 **1,000,000 commands/tick**。
- EXECUTE 总预算为 ≤400ms，折算到每条命令只有 **0.4µs/command**；即使 500 玩家也只有 **0.8µs/command**。
- Phase 2a 是逐条校验 + 逐条 inline 应用，且许多命令需要访问 Bevy World、校验位置/所有权/资源/容量、记录 rejection、可能触发 action quota。0.4–0.8µs/command 对 Rust ECS + 审计写入来说过于激进。
- 建议将命令预算改为双层限制：`commands_per_player` 保留 API 上限，但另设 `global_commands_per_tick`、`commands_per_room_per_tick` 与按命令成本加权的 `execute_budget_units`。例如 Move/Attack/Transfer/Build 按不同 cost 计入全局预算，超出后 deterministic reject 或排队到下一 tick。

### P1 — path_find 全局最坏上限过高，可能吞噬 COLLECT 预算

- **Severity: High**
- 文档给出每玩家 `host_path_find` 上限：10 次调用 + 100,000 explored_nodes/tick。1000 玩家时理论上是 **10,000 path_find calls/tick** 与 **100,000,000 explored_nodes/tick**。
- 即便 A* 单 node 极快，1e8 explored nodes 在 2500ms COLLECT 内也很难稳定完成；且 cache miss、不可达目标、visibility fingerprint 变化都会放大实际成本。
- `host_path_find` fuel cost 是 `500 × explored_nodes + 200 × expanded_edges + cache_miss_penalty`，但文档未说明全局 pathfinding worker 池、全局 explored_nodes 上限、per-room 热点限流、cache miss 熔断策略。
- 建议新增 `global_path_nodes_per_tick`、`per_room_path_nodes_per_tick`、`path_find_cpu_pool_budget_ms`，并规定超限 deterministic fail；对不可达路径必须有最大搜索边界和分层/缓存寻路策略，否则复杂地形/出口 chokepoint 会成为可攻击热点。

### P1 — WASM sandbox 生命周期文档互相冲突，直接影响 tick 成本估算

- **Severity: High**
- `design/engine.md` 描述为 **long-lived worker pool + per-tick clean Store/Instance reset**；`specs/core/04-wasm-sandbox.md` 描述为 **每 tick fork → 执行 → kill**。
- 这两者性能差异巨大：每 tick per-player fork/kill 在 500–1000 活跃玩家下会引入进程创建、cgroup、seccomp、IPC、页表和冷缓存开销，几乎不可能保持 collect p99 ≤2500ms；long-lived pool 则有机会达成。
- 建议以 long-lived worker pool 为唯一权威设计：worker 进程长驻，tick 内重建 Store/Instance 或使用可验证 clean reset；fork/kill 仅作为 OOM/trap/timeout 后回收路径，而不是每 tick 常态路径。

### P1 — snapshot 构建存在深拷贝/序列化双重成本风险

- **Severity: High**
- `specs/core/01` 中 COLLECT 时序写到 `[1] 构建完整世界快照（Bevy World 深拷贝）`，随后 `[2] 按房间分片快照`，每玩家再过滤/截断。
- hard cap 50,000 entities、1000 玩家、默认可见最多 9 房间、WASM 输入上限 256KB 时，理论输入上界约 **244MiB/tick**，在 2.5s collect 窗口内只是带宽上可行；但若还做完整 Bevy World 深拷贝 + JSON 序列化 + 每玩家拼接，50ms snapshot p99 风险很高。
- 建议明确 snapshot 使用增量/列式/arena-backed 只读视图，而非完整 ECS 深拷贝；按 room 维护预序列化 cache，tick 变更后只重建 dirty room shard。WASM 输入也建议从 JSON 迁移到紧凑二进制 ABI 或至少 MessagePack/FlatBuffers，否则 256KB JSON 的 parse/copy/fuel 成本会偏高。

### P1 — FDB 原子提交与 TickTrace 存储策略仍有跨文档不一致

- **Severity: High**
- `design/engine.md` §3.4.7 说 FDB 存 head/manifest/hash/pointer，大型 TickTrace/keyframe 进入对象存储或 append-only log；但 `specs/core/01` §6.3.1/§9.4 又写每 tick `/tick/{N}/commands/state/rejections/metrics` 写入 FDB，并且 TickTrace 与状态在同一 FDB 事务中。
- 若按后者实现，1000 玩家 × 大量 commands/rejections/metrics 很容易造成 FDB 写放大、热点 key-range、事务大小与 commit latency p99 风险；若按前者实现，需要说明审计完整性如何通过 manifest/hash/pointer 保证同事务原子性。
- 建议统一为：FDB tick 事务只写小型 manifest、state head、content-addressed object pointers、hash、versionstamp；大 blob 写入对象存储/append log 后，其 hash/pointer 纳入 FDB 事务。禁止在 FDB 单事务中直接写完整 state 或大 TickTrace blob。

### P2 — ECS 并行调度被 20 系统 `.chain()` 收缩，可能低估 2b 成本

- **Severity: Medium**
- `design/engine.md` 将 regeneration/decay 作为可并行系统；但 `specs/core/01` §3.4 的 20 系统链中大量系统被 `.chain()` 串行，包括 regeneration、decay、controller、repair、combat、memory_upkeep、rhai tick hooks 等。
- 这会让 Bevy 并行调度空间显著收缩，且 Rhai rule hooks 如果进入 tick 主链，解释器开销可能成为 p99 抖动来源。
- 建议为每个 system 提供读写矩阵和 cost class，强制区分 critical chain、room-parallel systems、entity-parallel systems、async/non-critical systems；Rhai hook 必须有执行预算与禁用/降级策略。

### P2 — `get_objects_in_range` 的组合上限不一致

- **Severity: Medium**
- `specs/core/04` 资源预算表写 `get_objects_in_range` 调用 5/tick，但 host function 总表只写 host function 1000/tick，`specs/core/01` 则主要列 host calls 1000/tick，未统一暴露对象查询的全局预算。
- 若对象查询只按 fuel 计费但缺少全局返回实体数/响应字节数预算，玩家可以通过多次范围查询制造重复过滤和序列化成本。
- 建议统一预算：`host_get_objects_in_range_calls_per_player`、`returned_entities_per_player_per_tick`、`host_query_bytes_per_player_per_tick`、`global_host_query_cpu_ms`，并将所有查询结果从同一 per-player snapshot/view cache 中切片，避免重复扫描 ECS。

### P2 — 1000 players / 10000 drones 与“1000 drones ≤100ms”目标口径不一致

- **Severity: Medium**
- 任务评审关注“1000 drones 时 tick 是否仍然 ≤100ms”，但文档的 World 性能合同是 3000ms tick，Arena 是 300ms tick，未定义 1000 drones / 100ms 的目标场景。
- 若这是 Arena 或单房间 microbenchmark 目标，需要独立列出：实体数、玩家数、命令数、是否执行 WASM、是否含 FDB commit、是否含 broadcast。
- 建议新增 microbench 合同：`1000 drones, no WASM, no FDB, execute-only p99 ≤100ms` 或 `1000 drones, full arena tick p99 ≤300ms`，避免评审/CI 使用不同口径。

### P2 — Broadcast “无硬限制（异步发布）”可能转移背压而不是消除背压

- **Severity: Medium**
- BROADCAST 不回滚 tick 是正确的，但如果 delta fan-out 长期落后，Gateway/NATS/Dragonfly 队列会累积，最终影响查询延迟和内存。
- 文档有 BROADCAST overload 降级描述，但缺少队列长度、水位线、丢弃策略、客户端差异化优先级。
- 建议补充：per-room delta topic、client subscription filtering、max pending bytes、gap-fetch 强制降级、水位线触发只推关键实体或只推 tick marker。

### P3 — fuel metering 开销需要基准合同

- **Severity: Low**
- Wasmtime fuel metering 本身会增加执行开销，尤其是高频 host calls 与路径查询混合时。文档声明 fuel 是公平计量，但没有给出 fuel overhead benchmark 目标。
- 建议增加 CI benchmark：同一 WASM workload 在 fuel on/off 下的 overhead p50/p99、host call heavy workload、JSON parse workload、path_find workload。建议将 fuel overhead 预算约束在可接受范围，例如 CPU-bound workload overhead ≤20–30%，host-heavy workload 单独建模。

## Bottleneck Analysis

### 1. Tick 关键路径

World tick 的理论预算如下：

- Snapshot build：≤50ms p99
- COLLECT / sandbox dispatch：≤2500ms
- EXECUTE：≤400ms
- COMMIT / FDB：≤50ms p99
- BROADCAST：≤50ms

这形成约 3050ms 的阶段预算总和，略高于 3000ms tick interval；文档后续又引入 `tick_soft_deadline_ms = 2500ms` 与 `tick_hard_deadline_ms = 4000ms`。建议统一解释：2500ms 是 collect soft deadline，3000ms 是目标间隔，4000ms 是 hard abandon deadline；否则实现方可能把阶段预算简单相加后认为 3050ms 仍合规。

最大风险段：

1. **COLLECT**：1000 玩家并行 WASM，理论 fuel 10B/tick，实际依赖 worker pool 并发度、CPU 核数、host query/pathfinding 上限。只要 path_find 全局预算不收紧，COLLECT 会成为可攻击瓶颈。
2. **EXECUTE Phase 2a**：逐命令串行 inline apply 在最坏 1M commands/tick 下几乎不可能 400ms 内完成。这里是当前最明确的容量合同缺口。
3. **Snapshot**：设计方向正确，但“Bevy World 深拷贝 + JSON 序列化 + per-player 拼接”如果照字面实现，50ms p99 风险高。需要 dirty room shard 和预序列化视图。
4. **COMMIT**：若 FDB 事务仅写小 manifest，50ms p99 合理；若直接写完整 TickTrace/state，则不合理。当前文档冲突必须消除。

### 2. ECS 并行调度

当前设计的 ECS 调度有两个方向：

- 好的方向：将玩家命令集中在 Phase 2a，2b 被动系统由 Bevy 依赖图调度；regeneration/decay 等独立系统并行。
- 风险方向：`specs/core/01` 的 20 系统 `.chain()` 实际将大量系统串行化，降低 ECS 并行收益。

建议将 ECS 系统分为四类：

1. **Strict serial**：death_mark、spawn、combat/status/death_cleanup 等真正依赖顺序的系统。
2. **Room-parallel**：controller、repair、resource regeneration、decay、room_state 等可按 room 分区并行的系统。
3. **Entity-parallel**：aging、fatigue/cooldown decay、memory upkeep 等可按 archetype 并行的系统。
4. **Out-of-band**：analytics、debug trace、broadcast diff preparation 等不得阻塞 execute critical path。

### 3. WASM fuel metering 与 host functions

fuel metering 是公平性的核心，设计上合理；但性能风险主要不在纯 WASM 指令，而在 host function 边界：

- `host_path_find` 成本虽按 explored_nodes 计 fuel，但底层 CPU 仍是真实消耗；1000 玩家理论 100M explored nodes/tick 过高。
- `host_get_objects_in_range` 若每次重新 visibility filter，会造成重复扫描；应从 COLLECT 阶段的 per-player visible snapshot/view 中切片。
- JSON snapshot 输入与 JSON command 输出会把 parsing/serialization 成本推给 WASM 与 engine 双方；对 TS/Rust SDK 都是热路径成本。

建议：host function 不仅计 fuel，也必须计 global CPU budget 和 per-room hotspot budget。所有 host query 应共享同一 tick snapshot cache，避免查询绕过或重复构建可见性。

### 4. 数据库 / FDB 热点

FDB 选型本身可接受，关键在写入模式：

- 合理模式：每 tick 单事务只更新 `/world/{id}/head`、manifest pointer、hash、versionstamp、小型 metrics summary；大 blob 已经 content-addressed 写入对象存储或 append log。
- 风险模式：每 tick 在 FDB 下写 `/tick/{N}/commands/state/rejections/metrics` 完整内容，尤其所有 tick 顺序写入同一 key-range，可能制造热点与事务膨胀。

建议明确 keyspace 分散策略：按 world/shard/tick bucket hash 前缀拆分 immutable trace keys；head key 单点写入可以接受，但必须保持小值、单写者、无读写冲突；读侧走 Dragonfly/对象存储，避免大量客户端打 FDB current state。

## Throughput Estimates

基于文档硬上限的保守估算：

| 场景 | 500 players | 1000 players |
|---|---:|---:|
| Total fuel per tick | 5,000,000,000 | 10,000,000,000 |
| Serial equivalent collect budget/player | 5.00ms | 2.50ms |
| Max commands/tick | 500,000 | 1,000,000 |
| EXECUTE budget/command @400ms | 0.800µs | 0.400µs |
| Max path_find calls/tick | 5,000 | 10,000 |
| Max explored nodes/tick | 50,000,000 | 100,000,000 |
| WASM snapshot input upper bound | 122.1MiB/tick | 244.1MiB/tick |
| Snapshot bandwidth over 2.5s collect | 48.8MiB/s | 97.7MiB/s |

结论：

- **500 players / 5000 drones**：在 long-lived worker pool、dirty room snapshot、收紧 pathfinding 全局预算、限制全局 command 数后，有机会达成 3s World tick。
- **1000 players / 10000 drones**：作为 hard cap 可保留，但必须引入全局执行预算与背压；否则 1M commands/tick 和 100M path nodes/tick 的最坏组合会击穿 400ms EXECUTE 与 2500ms COLLECT。
- **1000 drones ≤100ms**：文档当前没有定义这个目标口径。若指 execute-only microbenchmark，需单独设 CI 合同；若指 full tick with WASM/FDB/broadcast，则与当前 World/Arena 预算不一致。

## CrossCheck — 需要跨方向检查

- CX1: FDB TickTrace/state 存储策略在 `engine.md` 与 `01-tick-protocol.md` 中冲突 → 建议 Architect 检查权威数据流：FDB 小事务 + object/log blob pointer 是否能同时满足原子提交、回放完整性和审计不可抵赖。
- CX2: WASM sandbox 生命周期在 `engine.md` 与 `04-wasm-sandbox.md` 中冲突（long-lived pool vs per-tick fork/kill）→ 建议 Security 与 Architect 联合检查隔离强度与性能目标的取舍，并指定唯一权威生命周期。
- CX3: `world_seed` 泄露后的未来 tick 可预测被标为接受风险 → 建议 Security 检查是否需要 commit-reveal、延迟公开 seed、VRF 或服主 epoch bump 的操作约束，以免性能优化后的 replay/cache 机制扩大影响面。
- CX4: Rhai RuleMod 进入 tick start/end 主链可能引入解释器抖动和第二套状态路径风险 → 建议 Architect 检查 RuleMod manifest、预算、禁用策略，以及所有动态 action 是否确实只走 Command Validation 单一路径。
- CX5: Broadcast overload 降级策略缺少客户端一致性体验约束 → 建议 UX/Frontend 检查 gap-fetch、延迟 delta、关键实体优先推送时客户端如何展示 stale/partial state。
- CX6: `snapshot.truncated` 和 hostile entity inflation 属于可见性/公平性边界 → 建议 Gameplay 检查 density tax、attacker cost、priority bucket 是否会产生可被玩家利用的信息压制策略。
