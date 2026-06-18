# R17 性能评审（GPT-5.5）

Verdict: REQUEST_MAJOR_CHANGES

本轮 R17 文档已经明显收敛：容量上限、tick pipeline、WASM fuel、host function 输出上限、FDB 小事务/对象存储分层、COLLECT retry 缓存等关键性能合同基本齐全。但从 Performance 视角，仍有几处会直接落在 tick 关键路径或单一权威源闭合性上，当前不足以批准进入实现。

核心结论：设计意图是可行的，但需要修复对象存储写入进入 tick commit 关键路径、1000 玩家 sandbox 聚合 CPU 不可达、API Registry Markdown 与 IDL 版本不一致、WASM 输出/快照截断语义冲突，以及 Phase 2b 调度权威 manifest 在本审阅子集中不可闭合的问题。

## Strengths

1. Tick 预算被显式拆分
   - World: tick interval 3000ms，SNAPSHOT ≤50ms，COLLECT ≤2500ms，EXECUTE ≤400ms，COMMIT ≤50ms，BROADCAST ≤50ms。
   - Arena: tick interval 300ms，COLLECT ≤200ms，EXECUTE ≤50ms，COMMIT ≤20ms，BROADCAST ≤10ms。
   这比早期“目标 3s”式描述更适合作为性能回归 CI 的合同。

2. 两阶段快照架构方向正确
   - engine.md 明确从 O(players × entities) 降到 O(entities + players × visible_rooms)。
   - 每玩家 WASM snapshot cap = 256KB，展示层分页，不把 UI 展示压力混入 WASM 输入。

3. Host function 有预算和输出上限
   - host call 总预算 1000/tick/player。
   - host_path_find 10/tick，8KB 输出，global 100,000 explored nodes/tick。
   - host_get_objects_in_range 5/tick，64KB 输出。
   这避免了无界 host 调用把 COLLECT 拖死。

4. FDB 小事务方向正确
   - engine.md 与 persistence-contract.md 均要求 FDB 只推进 head/manifest/hash/pointer，小 blob 外置。
   - 事务大小目标从 “全量 TickTrace 进 FDB” 修正为 “FDB manifest + object hash”。

5. retry 不重跑 WASM 是正确修复
   - FDB commit retry 复用 canonical COLLECT buffer，不重复扣 fuel、不重新执行 WASM，避免非确定性输出和 retry 放大 CPU。

6. Worker pool 替代 fork-per-tick 是正确方向
   - fork + seccomp + cgroup per tick 对 500 玩家已不可接受；long-lived worker pool + per-tick Store reset 是性能上唯一合理路径。

## Concerns

### P1 — 对象存储写入仍在 tick commit 关键路径，且超时合同可超过 tick interval

位置：specs/core/05-persistence-contract.md §2、§7；design/engine.md §3.4.1。

persistence-contract.md 定义：
- Phase B: 对象存储写入 tick_trace_blob。
- Phase C: FDB 事务提交。
- 对象存储写入失败/超时 → FDB 回滚，tick 放弃。
- 对象存储写入超时 = 5s。

这与 engine.md 的性能合同冲突：
- World COMMIT ≤50ms p99。
- World tick interval = 3000ms。
- Arena COMMIT ≤20ms，tick interval = 300ms。

如果每 tick 都必须先压缩并写入完整 TickTrace blob 到对象存储，tick critical path 不再是 “FDB 小事务 ≤50ms”，而是 “serialize + compress + object-store write + FDB commit”。对象存储 p99 和 5s timeout 已经足以单独击穿 World 3s tick，更不可能适配 Arena 300ms。

Performance 影响：
- 任何对象存储抖动都会导致 tick abandon。
- TickTrace 10MB buffer 上限与 per-tick 写入结合，形成 I/O 延迟和内存峰值风险。
- FDB 小事务虽然解决了事务大小，但没有解决 commit 前置 blob write 的尾延迟。

建议修复：
- tick authoritative commit 应只依赖 FDB small manifest + local durable WAL/hash pointer；对象存储上传异步化。
- FDB manifest 可先记录 local WAL segment id + content_hash + pending_upload 状态，上传完成后补 etag。
- 若坚持“commit 成功即 blob 可读”，则必须把对象存储 p99 纳入 COMMIT 预算，并把 object-store timeout 从 5s 改成远低于 tick budget 的 hard cap；但这会显著降低可用性。

### P1 — 1000 活跃玩家 sandbox 聚合 CPU 合同不可达，active_players hard cap 不能替代 aggregate CPU admission

位置：design/engine.md §3.4.2、§3.4.3；api-registry.md §5.1；game_api.idl.yaml limits.hardware_baseline；specs/core/04-wasm-sandbox.md §4.2、§6。

权威限制给出：
- target active players = 500，hard cap = 1000。
- Worker pool max = 256。
- Sandbox CPU cgroup = 0.25s / 3s。
- Per-player sandbox deadline = 2500ms。
- Fuel per player = 10,000,000。
- Target hardware = 64GB RAM, 32 cores。

按文档数值估算：
- 500 players × 0.25 CPU-s = 125 CPU-s / tick。
- 1000 players × 0.25 CPU-s = 250 CPU-s / tick。
- 32 cores × 2.5s COLLECT wall window = 80 CPU-s 可用。
- 1000 players 在 max_pool=256 下至少 4 waves。

这意味着只要大量玩家接近 CPU quota，World 模式 target 500 也已超过 32 核 2.5s COLLECT 窗口，更不用说 hard cap 1000。cgroup per worker 限流保护了单玩家公平，但没有给全局 COLLECT 提供 aggregate CPU admission。

Performance 影响：
- “hard cap 1000”在性能意义上不是安全上限，只是人数上限。
- 256 worker pool 可能导致排队，后几波玩家在 2500ms deadline 内天然拿不到执行窗口。
- tick overrun policy 会跳过剩余玩家，表现为活跃玩家数未超过 hard cap 但大量 0 指令。

建议修复：
- 增加 aggregate sandbox CPU budget，例如 `collect_cpu_budget_ms = cores × collect_window × safety_factor`。
- admission 不只看 active_players，还要看最近 N tick 的 fuel_used p95/p99、worker queue depth、timeout rate。
- 明确 worker scheduling：deadline 是 per-player 从 dispatch 开始算，还是从 COLLECT 开始算；若从 COLLECT 开始算，排队玩家必须计入 timeout 风险。
- 对 500/1000 players 给出 fuel-to-wall-clock 校准表，否则 10M fuel 与 0.25 CPU-s 无法映射到 32-core 预算。

### P1 — API Registry Markdown 与 machine-readable IDL 版本不一致，单一事实源未闭合

位置：specs/reference/api-registry.md；specs/reference/game_api.idl.yaml。

发现：
- api-registry.md 写 “当前 API 版本: 0.1.0”。
- game_api.idl.yaml 写 `api_version: "0.2.0"`。
- api-registry.md 还声明 “机器可读权威源为 game_api.idl.yaml，冲突时以 YAML 为准”。

这不是纯文档瑕疵。TickTrace Envelope 记录 api_version，SDK codegen/CI/Replay 都依赖版本号。如果 Markdown 仍宣称 0.1.0，而 IDL 是 0.2.0，则实现者可能把 registry_version、core_idl_version、api_version 的含义分叉。

Performance 影响：
- 版本不一致会使缓存键、codegen artifact、replay verifier manifest 失配。
- 运行时可能出现“同一 ABI 不同版本号”的重复编译/缓存失效，或相反地错误复用旧缓存。

建议修复：
- 由 IDL 自动生成 api-registry.md 的版本号和变更记录。
- CI 加检查：Markdown 中的 “当前 API 版本” 必须等于 YAML `api_version`。
- TickTrace 字段中同时出现 api_version/core_idl_version/host_abi_version 时，要说明它们分别来自哪个权威源。

### P1 — WASM 输出超限语义冲突：截断 vs 整批丢弃

位置：specs/core/01-tick-protocol.md §8.2、§9.7；specs/core/04-wasm-sandbox.md §3.1。

发现：
- 01-tick-protocol §8.2: “Output JSON 256KB，超限行为：截断（保留前 256KB）”。
- 01-tick-protocol §9.7: “WASM tick() 输出上限 256KB。超出时整批丢弃——不保留部分解析的前缀”。
- 04-wasm-sandbox §3.1: CommandIntent JSON 超过 256KB → 拒绝该玩家当 tick 所有输出。

这三处不能同时成立。

Performance 影响：
- 若保留前 256KB，需要解析部分 JSON，容易触发半条 command、schema fail、重试解析和日志放大。
- 若整批丢弃，执行路径简单且确定，但文档表格会误导实现者做 prefix truncation。

建议修复：
- 从性能和确定性角度，选择 “整批丢弃” 更合理。
- 将 §8.2 表格改为：`Output JSON >256KB → discard whole output; player commands=[]; record OutputTooLarge/SnapshotOverBudget equivalent`。
- 不要对玩家输出做 prefix preserve；只对 TickTrace preview 做截断即可。

### P2 — Phase 2b 调度权威依赖未纳入本审阅闭包，无法验证 ECS 并行安全

位置：design/engine.md §3.2/§3.4.6；specs/core/01-tick-protocol.md §3.4/§9.6。

允许审阅子集中多处声明：
- “权威系统调度见 Complete Tick Execution Manifest (specs/core/06-phase2b-system-manifest.md)”。
- 29 systems，serial spine + 3 parallel sets。
- Component R/W 矩阵见该 manifest。

但本任务明确只允许读取的文件不包含 specs/core/06-phase2b-system-manifest.md。因此，从 clean-slate review 的闭包内，Performance 无法验证：
- combat parallel set 是否真的按 target_id partition 无冲突。
- status effects parallel set 是否真的操作互不重叠的 component/subtype。
- RoomCap 中间态是否没有旁路 reader。
- 29 systems 的 Bevy query 是否能实际并行调度，而不是因 broad query 全部串行化。

Performance 影响：
- ECS 并行性是 EXECUTE 50/400ms 预算的关键前提。
- 如果 manifest 不在评审闭包，当前文档只能证明“声称可并行”，不能证明依赖最小化。

建议修复：
- 要么把 06 manifest 纳入 R17 性能评审允许文件；要么在 01-tick-protocol 中内联最小 R/W summary 表。
- CI 应从 Bevy system param/Rust query 自动抽取 R/W，与 manifest 比对，避免文档调度和实现调度漂移。

### P2 — Snapshot truncation 优先级在 engine.md 与 tick protocol 中不一致

位置：design/engine.md §3.4.4；specs/core/01-tick-protocol.md §2.3。

engine.md 定义 priority bucket：
1. 自机
2. 友方 drone
3. 敌方 drone
4. 建筑
5. NPC
6. 资源
同桶 stable entity_id order。

01-tick-protocol 定义：
1. 关键桶：Spawn、Controller、玩家拥有 depot/storage，无条件保留
2. 高优先：己方 drone、己方建筑，按距离
3. 中优先：敌方可见实体、资源点，按距离
4. 低优先：友方实体、中立实体，按距离
同桶 `(distance_to_drone, entity_id)`。

这两个算法会在同一世界状态下选择不同实体进入 256KB snapshot。

Performance 影响：
- replay determinism 依赖 snapshot_hash；不同实现按不同文档实现会分叉。
- 距离排序对“玩家拥有多个 drone”未定义聚合距离，会导致额外 O(visible_entities × drones) 或实现各自选择 min/nearest/first。
- entity_id-only sort 更便宜；distance sort 更符合玩家直觉但需要明确复杂度和缓存策略。

建议修复：
- 以 IDL/registry 增加 `visibility_truncation_version` 的具体算法定义。
- 明确多 drone 距离 = min Manhattan distance to any owned drone in visible set，或明确 anchor drone 选择规则。
- 用同一个生成源同步 engine.md 与 01-tick-protocol。

### P2 — Pathfinding fair-share 在 1000 玩家时退化为几乎不可用，但仍承担全局调度复杂度

位置：engine.md §3.4.2；api-registry.md §5.2；game_api.idl.yaml limits.fair_share_admission；04-wasm-sandbox.md §8。

全局 pathfinding budget = 100,000 explored nodes/tick，按 active_players 均分。

估算：
- 500 active players → 200 explored nodes/player/tick。
- 1000 active players → 100 explored nodes/player/tick。
- 每玩家最多 10 path_find 调用 → 若均摊，每次只有约 10–20 nodes。
- 50×50 room 内 A* 单次跨房间路径很容易超过这个节点量。

这在性能上是安全的，但在可用性上过于激进；大量 path_find 将 deterministic fail，玩家会转向自实现粗糙寻路或重复请求，反而制造 host call pressure。

建议修复：
- 给出 path cache 命中路径不计或低计 explored_nodes 的规则。
- 将 fair-share 从 active_players 改为 active_path_users 或 rolling demand-based share，并保留 per-player hard cap。
- 增加 admission mode：低负载时允许 burst，高负载时回落到 guaranteed minimum。

### P2 — Bevy World 深拷贝/序列化预算仍缺少大小模型

位置：engine.md §3.2、§3.4.1；01-tick-protocol.md §2.3、§3.5。

文档至少有两类快照：
- COLLECT 开始：完整世界快照 + room shard snapshot。
- Phase 2a 前：Bevy World 深拷贝用于 FDB rollback。

容量合同允许：
- total entities hard cap = 50,000。
- global drones = 10,000。
- per-player snapshot cap = 256KB。

风险：
- full world canonical serialization + room shard + Bevy rollback copy 可能形成 2–3 份大内存副本。
- Snapshot build ≤50ms p99 是硬合同，但没有给出 entity/component 平均大小、目标内存带宽、arena 预算下的实体上限折减。

建议修复：
- 定义 `WorldState serialized bytes hard cap` 或 per-entity/component bytes budget。
- 对 Arena 给独立 entity/drone cap，不能只复用 World 50k entity 后要求 SNAPSHOT ≤20ms。
- rollback snapshot 优先采用 archetype-level copy-on-write 或 component delta journal，而不是无条件深拷贝整个 Bevy World。

### P2 — Host function 总预算 1000/tick/player 在 1000 玩家下形成 1M host-call admission 面

位置：api-registry.md §4.2；game_api.idl.yaml host_functions；04-wasm-sandbox.md §6。

每玩家 1000 host calls/tick 固定 cap，1000 玩家即 1,000,000 host calls/tick 的理论 admission 面。虽然 path_find/get_objects 有单独上限，但 host_get_terrain 无单独上限，仅计入总预算。

Performance 影响：
- 大量 cheap host_get_terrain 仍会造成 ABI crossing、bounds check、visibility/context lookup 的固定开销。
- Fuel 500/call 未必覆盖 host crossing 的实际 wall-clock 开销，尤其在 WASM/host 边界和 JSON/buffer copy 模式下。

建议修复：
- 给 host_get_terrain 增加 per-tick cap 或批量 API，例如一次返回 room terrain grid。
- 在性能合同中增加 `host_call_wall_time_budget_per_player` 或 `host_call_global_budget`。
- CI benchmark 覆盖 1000 players × cheap host call flood。

### P3 — SIMD 默认策略与公平/确定性叙述不完全闭合

位置：04-wasm-sandbox.md §2.2；engine.md §3.4.3。

04-wasm-sandbox 写：World 默认 SIMD true（性能），Arena 默认 false（确定性/公平），relaxed SIMD false。engine.md 较早段落写禁用 SIMD。

Performance 影响较小，但会影响 fuel calibration：同样 10M fuel 下，SIMD true 的玩家可能获得不同实际吞吐。若这是有意的性能选择，需要在 fuel/fairness 合同中说明 Wasmtime fuel 对 SIMD 指令的计量方式和是否按 lane 计费。

建议修复：
- 统一 engine.md 与 sandbox spec：SIMD 是否允许、何种世界模式允许。
- 若 World 允许 SIMD，明确 fuel calibration benchmark 与反作弊观测。

## Bottleneck Analysis

1. COLLECT 关键路径
   - 理想路径：一次世界快照 + room sharding + per-player visible slice + WASM tick。
   - 主要瓶颈：aggregate sandbox CPU，而不是单玩家 deadline。
   - 当前 hard cap 1000 在 32 cores 上无法保证所有玩家 2500ms 内获得 CPU。

2. EXECUTE 关键路径
   - Phase 2a 命令循环仍是主要串行热点。
   - 1000 players × 100 commands = 100,000 commands/tick。若每条命令只需 2–4µs，Phase 2a 就是 200–400ms；若含 ECS query、visibility、resource ledger 更新，400ms World 预算很容易吃满，Arena 50ms 不现实。
   - Phase 2b 的并行收益依赖 06 manifest/RW matrix，但本审阅闭包无法验证。

3. COMMIT / Persistence 关键路径
   - FDB 小事务本身方向正确。
   - 但对象存储写入被放在 FDB commit 之前，使 COMMIT 实际受对象存储 p99 影响。
   - 这是当前最明确的 tick critical path blocker。

4. Snapshot / memory bandwidth
   - 50,000 entities hard cap 下，一次完整状态快照可控；两到三份副本 + 序列化 + per-player 250MB aggregate snapshot 输出会成为 p99 风险。
   - 若 snapshot cap 只限制 per-player WASM input，不限制内部 full snapshot bytes，仍可能 OOM 或超 50ms。

5. FDB 热点
   - 修复后 FDB 只写 head/manifest/hash/pointer，热点主要是 single tick head advancement；这符合单 engine strong consistency 模型。
   - 风险不在 FDB 大事务，而在 tick_head/hash_chain 单调 key 写入和 object-store prewrite。
   - 若未来多 engine shard，需要避免所有 shard 写同一 global hash_chain prefix。

## Throughput Estimates

基于文档硬值的粗估算：

| 场景 | 估算 |
|---|---:|
| 500 players 最大命令量 | 50,000 commands/tick |
| 1000 players 最大命令量 | 100,000 commands/tick |
| 500 players sandbox CPU quota 合计 | 125 CPU-s/tick |
| 1000 players sandbox CPU quota 合计 | 250 CPU-s/tick |
| 32 cores 在 2.5s COLLECT 内可提供 | 80 CPU-s/tick |
| 500 players per-player path share | 200 explored nodes/tick |
| 1000 players per-player path share | 100 explored nodes/tick |
| 500 players aggregate WASM snapshot cap | 125 MB/tick |
| 1000 players aggregate WASM snapshot cap | 250 MB/tick |
| 1000 players host-call theoretical cap | 1,000,000 calls/tick |

结论：
- 1000 drones 场景：如果不是 1000 players，而是 1000 drones distributed across fewer players，EXECUTE ≤100ms 有机会，但取决于 Phase 2a command count 和 ECS manifest 实际并行度。
- 1000 active players 场景：在当前 32-core/0.25s quota/2500ms collect window 下，不具备全员接近 quota 时稳定 tick 的容量证明。
- Arena 300ms tick：当前对象存储 prewrite、深拷贝 snapshot、100k command worst-case 都需要单独 Arena cap，否则 50ms EXECUTE/20ms COMMIT 只是目标值。

## CrossCheck

1. 单一事实源检查
   - `game_api.idl.yaml` 是机器权威源，但 `api-registry.md` 的 API version 与 YAML 不一致：Markdown 0.1.0 vs YAML 0.2.0。
   - 结论：未闭合，必须修复。

2. Tick budget 检查
   - engine.md 的 COMMIT ≤50ms 与 persistence-contract 的 object-store prewrite + 5s timeout 冲突。
   - 结论：未闭合，P1。

3. WASM sandbox 预算检查
   - per-player fuel/memory/deadline/host-call 限制明确。
   - aggregate CPU admission 缺失。
   - 结论：单玩家闭合，全局容量未闭合。

4. ECS 调度检查
   - 文档声称 serial spine + parallel sets，但权威 R/W manifest 不在本任务允许读取列表。
   - 结论：本审阅闭包内无法验证；需要纳入评审或内联摘要。

5. Persistence/FDB 检查
   - FDB 小事务方向正确。
   - object store 进入 commit 前置路径使 p99 latency 泄漏到 tick critical path。
   - 结论：架构方向正确，时序合同需重写。

6. 1000 drones/tick ≤100ms 检查
   - 若 1000 drones 产生 ≤1 command/drone，Phase 2a 约 1000 commands，理论可进入 100ms。
   - 若按玩家最大指令计算，1000 players × 100 commands = 100,000 commands，≤100ms 不现实。
   - 结论：需要区分 “1000 drones” 与 “1000 active players hard cap” 的 benchmark 合同。

## Required Fixes Before Approval

1. 将对象存储写入从 tick critical path 移出，或重写 COMMIT 预算使其真实包含 object-store p99；推荐异步上传 + FDB manifest pending state + WAL/hash proof。
2. 增加 aggregate sandbox CPU admission：基于 fuel_used、worker queue、timeout rate，而非仅 active_players hard cap。
3. 修复 api-registry.md 与 game_api.idl.yaml 的 api_version 冲突，并加 CI。
4. 统一 WASM output >256KB 语义；建议整批丢弃，不做 prefix truncation。
5. 统一 snapshot truncation bucket 算法，并明确多 drone 距离排序规则。
6. 将 Phase 2b system manifest/RW matrix 纳入性能评审闭包，或在 01-tick-protocol 中提供可审计摘要。

在以上 P1 项修复前，Performance verdict 维持 REQUEST_MAJOR_CHANGES。