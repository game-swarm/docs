# R18 性能评审（GPT-5.5）

## 1. Verdict

REQUEST_CHANGES

R18 相比 R17 的方向是正确的：`game_api.idl.yaml` 已明确成为机器可读单一事实源，`api-registry.md` 在主干 API 数量级字段上与 YAML 对齐；tick 热路径也引入了更合理的“快照分片 + 对象存储异步写入 + FDB 小事务”模型。

但从性能合约角度仍不能批准：关键容量常量仍在 YAML / Markdown / engine spec / sandbox spec 之间漂移，尤其是 worker pool 上限、WASM 模块大小、EXECUTE deadline、WASM output 超限语义。这些漂移不是文档小瑕疵，而是会直接改变 1000 players / 10000 drones 场景下 tick 是否可完成、ECS 是否能并行、WASM fuel 是否能公平限流的设计合同。

## 2. 发现问题（severity）

### P1 — Worker pool 上限单源未闭合：engine 依赖 1000 workers，但 YAML/registry 权威值是 256

证据：
- `design/engine.md` §3.4.2 Worker Pool 推导写明 `MAX_POOL = 1000`，并以 1000 workers 推导 hard cap 1000 players 可运行。
- `game_api.idl.yaml` / `api-registry.md` §5.5 写明 `worker_pool_max: 256` / `max_pool = 256`。

影响：
- 1000 players hard cap 推导在 engine.md 中成立的前提是 1000 个 worker 并发调度；若 registry 的 256 才是权威，COLLECT phase 需要至少 4 批调度。
- 若每玩家 p50 WASM=5ms，则 1000 players 在 256 pool 下理想 wall-clock 约 `ceil(1000/256) * 5ms ≈ 20ms`，看似可接受；但 p99=15ms 时约 60ms，加上 snapshot stitching、IPC、Store reset、host calls 后并不等价于 engine.md 中“1000 workers / 40 cores”推导。
- 更严重的是 admission 公式、cgroup 限额、pool cap 三者分别从不同文件读取会导致实现者选择不同 max_pool，线上性能与回放/指标预期不一致。

要求：
- 只能保留 YAML `limits.hardware_baseline.worker_pool_max` 作为唯一机器事实源；engine.md 不得重新声明 `MAX_POOL = 1000`。
- 1000 players 推导必须基于 `max_pool=256` 或修改 YAML 权威值并重新生成 registry。

### P1 — Sandbox CPU/fuel 合同互相打架：per-sandbox cgroup 允许的总 CPU 与 aggregate fuel admission 不同阶

证据：
- YAML/registry：`sandbox_cpu = cpu.max = 250000 3000000`，即每 sandbox 每 3s 周期 0.25 CPU 秒。
- engine.md aggregate admission：`aggregate_cpu_budget = 2500ms × CPU_CORES × PER_CORE_MIPS`；硬件基线 32 cores、500 MIPS/core 时为 40B instr/tick，1000 players 下 per-player 40M fuel，再被 `MAX_FUEL=10M` 截断。
- 04-wasm-sandbox.md：每玩家 fuel 10,000,000，wall-clock 2500ms。

估算：
- 1000 sandboxes 若都获得 cgroup 上限，理论允许 `1000 × 0.25s = 250 CPU-seconds / 3s`，等价约 83 cores 持续满载，超过 32-core baseline。
- aggregate fuel 在 32 cores/500 MIPS 下给出的物理预算是 40 CPU-seconds/tick；若每玩家仍拿 10M fuel，则约 `1000 × 10M / 500MIPS = 20 CPU-seconds`，与 cgroup 限额不是同一个保护层。

影响：
- 若 fuel metering 正常，cgroup 限额过宽，不能作为过载保护。
- 若 host function / Wasmtime / IPC / memory work 不完全按 fuel 计量，cgroup 的 250 CPU-seconds 可能把 32-core 节点打爆，COLLECT 2500ms deadline 失守。
- `per_player_sandbox_deadline=2500ms` 是 wall-clock，不是 CPU admission；在 256 worker pool 下 timeout 还会形成队头阻塞。

要求：
- 明确三层限额的优先级：fuel 是主计量，cgroup 是硬兜底，deadline 是 wall-clock kill。
- cgroup CPU 应按 pool/global admission 推导，而不是固定每玩家 0.25s；至少需说明 `cpu.max` 是否只用于单 worker 而非每玩家常驻 worker。
- host function CPU 必须计入 aggregate admission，否则 path_find/cache miss 可以绕过 WASM 指令计量。

### P1 — EXECUTE deadline 与 Phase 2a 串行最坏量不闭合

证据：
- engine.md §3.4.1：EXECUTE (2a+2b) World 预算 ≤400ms。
- 01-tick-protocol.md 状态机：EXECUTE 超时 500ms。
- 01-tick-protocol.md §8.2：EXECUTE “不单独超时，由 COLLECT+EXECUTE 总预算控制”。
- 容量：1000 players × 100 commands/player/tick = 100,000 Phase 2a inline commands/tick。

影响：
- Phase 2a 是严格串行 inline validate+apply，且每条命令基于当前 Bevy World 校验。100k commands 在 400ms 内要求端到端 4µs/command，包含 ECS lookup、visibility/ownership/range validation、ledger、rejection trace、resource mutation，风险很高。
- 若使用 500ms，则是 5µs/command；仍非常紧，且与 engine 的 400ms CI 合同冲突。
- 1000 drones 场景如果每 drone 1 command，则仅 Phase 2a 预算约 0.4ms/100 commands；1000 drones 可行，但 1000 players hard cap 的 100k command 最坏值没有 admission throttle。

要求：
- 将 `commands_per_player_per_tick=100` 与全局 EXECUTE admission 绑定，例如 `global_commands_per_tick`、per-action cost、或 tick 内丢弃策略。
- 统一 EXECUTE deadline 的唯一权威字段。
- 给出 100k command 的 microbenchmark 目标：p50/p99 command apply ns、ledger write ns、rejection trace bytes。

### P1 — YAML→Markdown 生成式单源只在主数量字段闭合，深层常量仍漂移

我对允许文件做了只读交叉检查，顶层字段一致：

| 项 | YAML | api-registry.md | 结果 |
|---|---:|---:|---|
| api_version | 0.3.0 | 0.3.0 | OK |
| CommandAction total | 19 | 19 | OK |
| RejectionReason canonical | 35 | 35 | OK |
| MCP tools total | 46 | 46 | OK |
| Host functions total | 5 | 5 | OK |

但生成式闭环仍不完整：
- worker pool：engine `MAX_POOL=1000` vs YAML/registry `worker_pool_max=256`。
- WASM module size：04-wasm-sandbox validation 拒绝 `>5MB`，YAML persistence blob type `wasm_module max_size=64MB`。
- WASM output 超限：01 §8.2 写“Output JSON 256KB → 截断（保留前 256KB）”；01 §9.7 与 04-wasm-sandbox 写“超出则整批丢弃/拒绝该玩家全部输出”。
- EXECUTE deadline：400ms、500ms、无单独超时三种表述并存。

影响：
- 这说明 `api-registry.md` 虽由 YAML 生成，但其他核心 specs 并未从 YAML/manifest 读取常量；“单一机器事实源”还没有扩展到性能关键常量。
- 性能实现会被迫人工选择哪个值，CI 无法防止漂移。

要求：
- 把 performance/capacity limits 抽为机器可读 `limits_manifest`，由 YAML 生成 engine/sandbox/tick 文档表格。
- 所有非生成文档只引用符号名，不重新声明数值。

### P2 — ECS 并行调度声明与 R/W 矩阵不一致，Combat Parallel Set A 可能无法安全并行

证据：
- 06 manifest 宣称 S11 attack、S12 ranged_attack、S13 heal “按 target_id partition，同一 entity 只被一个 system 写入”。
- 同一文件 R/W 矩阵却标注 S11/S12/S13 都直接写 `HitPoints`。
- S15 又声明读取 `PendingDamage buffer` 并统一应用 damage，暗示 S11/S12/S13 应写 buffer 而不是直接写 HitPoints。

影响：
- 如果 S11-S13 直接写 HitPoints，则 attack 与 heal 同 target 是典型写冲突，Bevy 调度不会安全并行，必须串行或通过 interior mutability/commands 延迟。
- 如果它们只写 PendingDamage/PendingHeal buffer，则 R/W 矩阵错误，CI 静态冲突检测会失真。

要求：
- 将 Combat Set 改为“并行收集 intents → S15 serial reduce/apply”，R/W 矩阵中 S11-S13 写 PendingCombatIntent，不写 HitPoints。
- 或明确 target partitioner 如何把 attack/ranged/heal 的同目标操作归到同一 worker 并保持 canonical reduce 顺序。

### P2 — Snapshot build 50ms p99 合同缺少大规模 stitching 成本上限

证据：
- engine.md 采用两阶段快照，目标 SNAPSHOT build ≤50ms p99。
- 单玩家 WASM snapshot cap 256KB；1000 players 的最坏拼接输出可达约 256MB/tick。
- 01-tick-protocol.md 仍出现“Bevy World 深拷贝”作为 COLLECT 开始步骤。

影响：
- 50k entities 的结构化快照 + room sharding + 1000 players visibility filter + 最高 256MB copy/serialize，在 50ms p99 下非常紧。
- 若每 tick 深拷贝 Bevy World，再序列化分片，再 per-player stitching，cache locality 和 allocator 压力会成为 COLLECT 前置瓶颈。

要求：
- 给出 snapshot 的实际数据布局合同：零拷贝 Arc slice / arena buffer / precompressed room chunks / per-player view index，而不是每玩家 JSON 拼接。
- `SnapshotOverBudget` 和 truncation 需发生在 binary/canonical codec 层，避免先构建超大 JSON 再截断。

### P2 — FDB “小事务”方向正确，但 state mutation 写集合缺少硬上限，仍可能形成 tick commit 热点

证据：
- 05-persistence-contract.md 明确 FDB 只写 tick head、manifest、hash、pointer，小对象；大 blob 异步进 object store。
- 同一 Tick Commit Phase B 又写 “FOR each persistent state mutation: UPDATE entity/resource/controller/... rows”。
- 实现约束写 “FDB transaction <10KB”，但容量允许 10,000 drones / 50,000 entities。

影响：
- 只要一个 tick 中 mutated entities 多，单事务就会突破 10KB；例如 10k drones aging/fatigue/cooldown 若都持久化为 mutation rows，FDB commit 不再是小事务。
- 单 world tick_head/hash_chain 是单写者时不争用，但 entity rows 的写放大和 FDB conflict range 会影响恢复、备份和 replay tail latency。

要求：
- 明确 tick 内哪些 state mutation 进入 FDB row，哪些只进入 object-store delta/keyframe。
- 给出 dirty-set cap、delta compression、chunk manifest schema；否则 “FDB 小事务”只是意图，不是合同。

## 3. 亮点

- YAML IDL 主干闭合明显改善：CommandAction=19、RejectionReason=35、MCP Tools=46、Host Functions=5、TickTrace=22 字段在 YAML 与生成 Markdown 之间对齐。
- 对象存储异步化是正确方向：FDB commit 不等待 TickTrace/keyframe blob，大幅降低 tick critical path 的 I/O 风险。
- Tick retry 复用 canonical COLLECT buffer，避免 FDB retry 重新执行 WASM，解决了重复扣 fuel 和非确定输出问题。
- Phase 2b manifest 明确了 29 systems、stable IDs、manifest_hash、R/W 矩阵和 RoomCap 中间态约束，具备做 CI 调度验证的基础。
- Snapshot 从 O(players × entities) 改为 O(entities + players × visible rooms) 的方向正确，能消除早期每玩家重复全量序列化瓶颈。
- Host function 有 per-call fuel、输出上限、调用上限和错误优先级表；比无界 host call 安全得多。

## 4. CrossCheck

### YAML ↔ api-registry.md

结论：主 API 表已基本闭合，但性能关键 limits 尚未成为跨文档唯一事实源。

已核对一致：
- `api_version`: 0.3.0 ↔ 0.3.0
- `command_action.total_variants`: 19 ↔ 19
- `rejection_reason.total_canonical_codes`: 35 ↔ 35
- `mcp_tools.total_tools`: 46 ↔ 46
- `host_functions.total_functions`: 5 ↔ 5

发现漂移：
- `worker_pool_max`: YAML/registry=256，engine 推导=1000。
- `wasm_module max_size`: sandbox validation=5MB，YAML persistence blob=64MB。
- `output_json over budget`: truncate vs whole-output discard。
- EXECUTE deadline: 400ms vs 500ms vs no independent timeout。

### engine.md ↔ 01-tick-protocol.md

- Tick lifecycle 方向一致：COLLECT → EXECUTE → BROADCAST。
- 但预算不一致：engine 的 World EXECUTE=400ms；01 状态机写 500ms；01 §8.2 又说 EXECUTE 不单独超时。
- Snapshot 描述不完全一致：engine 强调按房间分片避免 per-player 全量序列化；01 仍写 Bevy World 深拷贝 + per-player visibility filter，需要明确是否深拷贝实体数据还是构建只读 snapshot view。

### 04-wasm-sandbox.md ↔ api-registry/YAML

- fuel=10M、linear memory=64MB、host call=1000/tick、path_find=10/tick 基本一致。
- module size 不一致：sandbox 5MB validation vs persistence `wasm_module max_size=64MB`。
- cgroup CPU 与 aggregate fuel admission 未对齐，需要一个统一公式。

### 05-persistence-contract.md ↔ tick protocol

- 异步 object store 与 FDB 小 manifest 是性能正向修复。
- 但 01 §9.4 仍强调 TickTrace 与 FDB 状态同事务完整性；05 改为 FDB manifest 先提交、blob async 后补。二者可兼容的前提是“TickTrace manifest/hash 同事务，blob 不同事务”，但文档需避免读者理解为完整 TickTrace blob 同事务。

## Bottleneck Analysis

### Tick critical path

1. SNAPSHOT build/stitching：50k entities + 1000 player views，可能产生最高约 256MB/tick 的 snapshot payload copy。若使用 JSON，会先于 WASM 占用大量 CPU 和 allocator 时间。
2. COLLECT sandbox dispatch：Wasmtime Store reset + IPC + host calls 是主要不确定项；fuel 只覆盖 WASM 指令，不天然覆盖所有宿主开销。
3. EXECUTE Phase 2a：100k commands/tick 串行 inline 是最明显瓶颈。400ms 预算下需要约 4µs/command。
4. Phase 2b：当前 manifest 的串行脊柱较长；并行 set 数量有限，但 10k drones 时 aging/decay/death cleanup 可以线性扫实体，需 SoA/dirty-set 优化。
5. COMMIT：FDB 小事务方向正确；风险在 dirty state mutation 是否真的不进入 FDB 大事务。

### ECS 调度

- Serial spine 保证确定性，但并行度偏保守。
- Combat Set A 和 Status Set B 的并行安全声明需要与实际 R/W 矩阵修正，否则 Bevy 调度会退化串行。
- aging/decay/resource_ledger 都是潜在 O(active_entities) 串行尾部，应避免每 tick 全表扫描。

### WASM fuel metering

- Wasmtime fuel 本身合理；10M fuel/player 是可操作的 hard cap。
- 风险在 host functions：path_find 虽有 explored_nodes 全局预算，但 cache miss、visibility filtering、serialization/output copy 也要被计入 admission。
- cgroup CPU 当前更像宽松兜底，不足以证明 1000 players 在 32 cores 下稳定。

### FDB / Dragonfly 热点

- tick_head/hash_chain 单写热点在单 engine 模式可接受。
- Deploy 的 `fdb_version_counter` 是全局递增热点，但 deploy rate=10/h/player，短期可接受。
- 真正风险是 “for each persistent state mutation” 是否扩大为 10k+ row writes/tick；这会破坏 <10KB transaction 合同。

## Throughput Estimates

假设硬件基线为 32 cores、500 MIPS/core、World tick interval=3000ms：

- Aggregate collect fuel budget：`2.5s × 32 × 500M instr/s = 40B instr/tick`。
- 1000 active players 下 fair share：`40M instr/player`，再被 `MAX_FUEL=10M` 截断；理论 WASM 指令 CPU 约 `1000 × 10M / 500MIPS = 20 CPU-seconds/tick`，占 32 cores 的约 625ms wall-clock 理想下限。
- cgroup 若按 `0.25s/player/3s` 放开，1000 players 可消耗 250 CPU-seconds/tick，超过 32-core 节点 3s 内可提供的 96 CPU-seconds，必须依赖 fuel/worker pool 限制，否则不可控。
- Phase 2a worst case：1000 players × 100 commands = 100k commands/tick。400ms 预算要求平均 ≤4µs/command；500ms 预算要求 ≤5µs/command。考虑 validation + ECS mutation + ledger + trace，这需要强 admission 或非常激进的数据布局。
- Pathfinding：100k explored nodes/tick global，在 1000 players 下 fair share=100 nodes/player/tick。若每玩家仍允许 10 calls，则平均每 call 只有 10 explored nodes，很多真实路径会 deterministic fail；性能上安全，但体验/策略层面会非常紧。
- Snapshot payload：1000 players × 256KB cap = 256MB/tick 上限；3s tick 下约 85MB/s payload 构造，不含 JSON parse/stringify 放大。若 Arena 300ms tick 沿用同 cap，则不可接受，必须降低 Arena cap 或使用 binary/zero-copy view。
- FDB commit：若坚持 <10KB manifest 小事务，p99 ≤50ms 可合理；若将 10k drone aging/decay 全部作为 row mutation 写入，50ms p99 不可信。

总体判断：在修复上述 P1 前，设计尚不能证明 1000 players hard cap 或 1000 drones ≤100ms 级别 simulation 能稳定达成。当前架构方向可行，但性能合同必须回到单一机器事实源，并为 Phase 2a 串行命令量、snapshot stitching、host function CPU、FDB dirty-set 建立硬 admission。