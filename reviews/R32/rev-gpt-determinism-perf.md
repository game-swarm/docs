# R32 Determinism & Performance Review — GPT-5.5

## 1. Verdict

REQUEST_MAJOR_CHANGES

当前设计方向正确，但存在多处会直接影响 replay、tick 原子性、WASM 资源计量与 ECS 调度实现的一致性问题。主要风险不是单点缺字段，而是同一权威合同在不同文档或同一文档内部给出了互相冲突的语义；若按当前文本实现，不同工程师会合理实现出不同 replay、不同扣费、不同 commit 恢复行为。

## 2. 发现的问题

### DNP-1 — High — WASM 输出超限语义冲突：整批丢弃 vs 截断保留前缀

- 文件引用：`/tmp/swarm-review-R32/design/engine.md:436`
- 文件引用：`/tmp/swarm-review-R32/specs/core/01-tick-protocol.md:785`
- 文件引用：`/tmp/swarm-review-R32/specs/core/01-tick-protocol.md:954`
- 文件引用：`/tmp/swarm-review-R32/specs/core/02-command-validation.md:50`
- 文件引用：`/tmp/swarm-review-R32/specs/core/04-wasm-sandbox.md:191`

问题描述：
- `engine.md` 明确规定 WASM 输出超过 256KB 时“整批丢弃，不保留前缀”。
- `01-tick-protocol.md` §9.7 同样规定 `output > 256KB` 时整批丢弃。
- 但 `01-tick-protocol.md` 的统一预算表写成 “Output JSON 256 KB：截断（保留前 256KB）”。
- `02-command-validation.md` 与 `04-wasm-sandbox.md` 只写大小上限/读取前检查，未明确是否允许 prefix parse。

影响分析：
- 这是 replay-critical 行为。若实现 A 整批丢弃、实现 B 解析前 256KB 前缀，则同一 WASM 输出会产生不同 RawCommand 集合、不同 fuel/refund、不同状态 checksum。
- 玩家可利用 prefix parse 构造“前缀有效、尾部垃圾”的非直观行为，破坏公平性与调试可解释性。

修复建议：
- 统一选择“整批丢弃”作为唯一合同，因为它已被 `engine.md` 与 `01-tick-protocol.md` §9.7 重复声明，且更利于确定性。
- 修改 `01-tick-protocol.md:785` 为“整批丢弃，0 指令，记录 `output_truncated` / `CommandBufferFull`”。
- 在 `04-wasm-sandbox.md` ABI 步骤中明确：读取 `len` 后若 `len > 256KB`，不得读取/解析任何返回 buffer 内容。

### DNP-2 — Critical — TickCommitRecord / RichTraceBlob / replay-critical 边界互相冲突

- 文件引用：`/tmp/swarm-review-R32/specs/core/05-persistence-contract.md:34`
- 文件引用：`/tmp/swarm-review-R32/specs/core/05-persistence-contract.md:55`
- 文件引用：`/tmp/swarm-review-R32/specs/core/05-persistence-contract.md:136`
- 文件引用：`/tmp/swarm-review-R32/specs/core/05-persistence-contract.md:156`
- 文件引用：`/tmp/swarm-review-R32/specs/core/05-persistence-contract.md:168`
- 文件引用：`/tmp/swarm-review-R32/specs/core/05-persistence-contract.md:175`
- 文件引用：`/tmp/swarm-review-R32/specs/core/01-tick-protocol.md:906`

问题描述：
- `05-persistence-contract.md` §2 声明 FDB 中 10 个 TickCommitRecord 字段足够 replay，Object Store 只承载 RichTraceBlob，缺失只产生 `audit_gap`，绝不会导致 `unreplayable`。
- 但同一文件 §3/§4/§5 又把 `tick_trace_blob` / `tick_manifest.upload_status` 作为 replay 可用性的条件，写明 blob 写入失败时 “replay 不可用”。
- `01-tick-protocol.md` 又说 TickCommitRecord 缺失关键字段才 `unreplayable`，RichTraceBlob 缺失仅 `audit_gap`。

影响分析：
- Replay verifier 无法判断到底应以 FDB 的 TickCommitRecord 为唯一输入，还是必须等待对象存储 blob `complete`。
- 如果实现把对象存储 blob 作为 replay-critical，异步上传失败会把本应可 replay 的 tick 标成不可 replay；如果实现只依赖 FDB，又与 `upload_status` 表的“replay unavailable”冲突。
- 这会污染反作弊审计、CI replay gate、事故恢复 runbook。

修复建议：
- 明确三层语义并全文件替换冲突表述：
  1. `deterministic_replay`：仅依赖 FDB TickCommitRecord + keyframe/delta，Object Store RichTraceBlob 缺失不阻塞。
  2. `rich_debug_replay`：依赖 RichTraceBlob，缺失为 `audit_gap`。
  3. `visual/replay_artifact`：可重建或缺失，不影响核心 replay。
- 将 `05-persistence-contract.md:156`、`:170-178` 的 “replay 不可用” 改为 “rich trace/debug unavailable；deterministic replay still available from FDB critical subset”。
- 给 TickCommitRecord 10 字段与 `api-registry.md` TickTrace Envelope 22 字段建立显式映射，避免 `wasm_status` / `terminal_state` 旧新字段混用。

### DNP-3 — Critical — Room-partition commit 声称全局原子，但流程存在已提交 per-room 事务后的不可回滚窗口

- 文件引用：`/tmp/swarm-review-R32/specs/core/01-tick-protocol.md:416`
- 文件引用：`/tmp/swarm-review-R32/specs/core/01-tick-protocol.md:421`
- 文件引用：`/tmp/swarm-review-R32/specs/core/01-tick-protocol.md:423`
- 文件引用：`/tmp/swarm-review-R32/specs/core/01-tick-protocol.md:426`
- 文件引用：`/tmp/swarm-review-R32/specs/core/05-persistence-contract.md:356`
- 文件引用：`/tmp/swarm-review-R32/specs/core/05-persistence-contract.md:361`
- 文件引用：`/tmp/swarm-review-R32/specs/core/05-persistence-contract.md:374`

问题描述：
- `01-tick-protocol.md` 描述每个活跃房间先独立 FDB 事务写入 room delta，然后提交 `GlobalTickCommit`，若全局提交失败则“所有房间快照恢复”。
- 但已 commit 的 per-room FDB 事务无法被真正“回滚”；只能通过后续补偿写入或读路径隐藏。
- `05-persistence-contract.md` 又写 Room-Partition 使用 cross-room 2-phase commit，但同一表格又说跨房间操作在内存中完成、commit 全或无，语义不完整。

影响分析：
- 这破坏 tick 原子性核心承诺。Crash 发生在部分 room_txn commit 成功、GlobalTickCommit 失败之前时，恢复进程可能看到部分房间新状态。
- Replay 与线上读路径可能分叉：若读路径扫描 per-room state 而未检查 global manifest，就会暴露 partial tick。
- “不存在部分房间已提交”的文字目前是目标语义，但缺少能实现该语义的 publish protocol。

修复建议：
- 将 room-partition 定义为“shadow write + atomic publish”：per-room delta 写入 `/staging/{tick}/{room}`，不作为可见状态；只有 `GlobalTickCommit(tick, room_hashes, prev_head)` 成功后，读路径才通过 global head 指向该 tick。
- 启动恢复时扫描 staging：无对应 GlobalTickCommit 的 room staging 全部 GC，不能进入 world head。
- 所有 read/query/replay 必须以 `global_head_tick` / manifest hash 为入口，禁止直接按 room 最新 key 读取。
- 如果需要 2PC，明确 prepare/commit/abort 状态机、超时恢复、idempotency key、crash recovery，而不是仅写“全局快照恢复”。

### DNP-4 — High — ECS manifest 内部 R/W 与 Unique Writer 合同冲突

- 文件引用：`/tmp/swarm-review-R32/specs/core/06-phase2b-system-manifest.md:20`
- 文件引用：`/tmp/swarm-review-R32/specs/core/06-phase2b-system-manifest.md:76`
- 文件引用：`/tmp/swarm-review-R32/specs/core/06-phase2b-system-manifest.md:189`
- 文件引用：`/tmp/swarm-review-R32/specs/core/06-phase2b-system-manifest.md:211`
- 文件引用：`/tmp/swarm-review-R32/specs/core/06-phase2b-system-manifest.md:216`
- 文件引用：`/tmp/swarm-review-R32/specs/core/06-phase2b-system-manifest.md:245`
- 文件引用：`/tmp/swarm-review-R32/specs/core/06-phase2b-system-manifest.md:391`
- 文件引用：`/tmp/swarm-review-R32/specs/core/06-phase2b-system-manifest.md:403`

问题描述：
- 标题写 “System Schedule (29 systems)”，同段又说共 31 systems。
- S11-S13 文本说只写 `PendingDamage` / `PendingHeal` sub-buffer，不直接修改 `Entity.hits`。
- S15 又声明自己是 HitPoints UNIQUE writer，但同时承认 S10 regen 也写 HitPoints。
- R/W Matrix 却把 S11/S12/S13 标为 `HitPoints = W`，把 S22 也标为 `HitPoints = W`，与 buffer-only 和 S15 unique writer 冲突。
- S22 的 writes 包含 Entity hits/armor/efficiency/interrupted、ResourceAmount、FuelBudget，但 Unique Writer 表只覆盖 StatusState，未解释这些 effect application 与 S15/S29/ResourceLedger 的写入边界。

影响分析：
- CI 静态 R/W 检查无法落地：如果按矩阵，Parallel Set A 对同一 HitPoints 有共享写；如果按文字，矩阵是错的。
- “Unique Writer”合同失效后，combat、regen、status、decay 的同 tick 顺序会产生不同 checksum。
- S22 直接写资源与 fuel 还可能绕过 ResourceLedger / fuel ledger，影响 replay-critical accounting。

修复建议：
- 将 schedule 标题改为 31 systems，并保持全文件计数一致。
- R/W Matrix 中 S11-S13 对 HitPoints 改为 `-`，新增 `PendingDamage/PendingHeal` buffer 列并标 W。
- 明确 HitPoints writer 模型：要么 S10/S15/S22/S24 都是按固定顺序的合法 writers，不再称 S15 为唯一 writer；要么所有非 S15 写入都改成 buffer，经 S15 或后置 reducer 统一提交。
- S22 对 ResourceAmount/FuelBudget 的修改必须声明是否进入 ResourceLedger/fuel ledger；若进入，给出 canonical operation emission order。

### DNP-5 — High — 容量推导存在算术错误且与 worker pool 权威上限不一致

- 文件引用：`/tmp/swarm-review-R32/design/engine.md:388`
- 文件引用：`/tmp/swarm-review-R32/design/engine.md:391`
- 文件引用：`/tmp/swarm-review-R32/design/engine.md:393`
- 文件引用：`/tmp/swarm-review-R32/specs/reference/api-registry.md:588`
- 文件引用：`/tmp/swarm-review-R32/specs/reference/api-registry.md:590`
- 文件引用：`/tmp/swarm-review-R32/specs/reference/api-registry.md:592`
- 文件引用：`/tmp/swarm-review-R32/specs/core/04-wasm-sandbox.md:260`

问题描述：
- `engine.md` hard cap 1000 player 推导写 “1000 players × 5ms = 5000ms”，再假设 “1000 workers / 40 cores” 后 wall-clock 约 25ms。
- 实际用 40 cores 平均分摊，5000ms / 40 = 125ms，不是 25ms。
- `api-registry.md` 又声明 Worker pool 默认 256，hard cap 1000；因此 1000 active players 并不等于默认有 1000 workers。
- `04-wasm-sandbox.md` 的 `cpu.max = 250000 3000000` 是每 sandbox 进程 0.25 CPU 秒 / 3s；若按 1000 worker 同时运行，会形成远超单节点 32/40 core 基线的 cgroup 配额总和，缺少全局 CPU admission 约束。

影响分析：
- 当前容量合同会高估 collect 阶段余量，导致 `target 500 / hard cap 1000` 的可信度不足。
- Worker pool、公平 fuel、cgroup CPU 三套限制没有统一成一个可验证的 admission model。
- 这会直接影响 tick overrun、timeout rate、fuel fairness 与 benchmark gate 的判定。

修复建议：
- 修正容量推导算术，并分别给出 `worker_pool_max=256` 默认与 `worker_pool_hard_cap=1000` opt-in 的 wall-clock 模型。
- 增加全局 CPU admission：`Σ sandbox cpu.max <= collect_budget × available_cores × oversubscription_factor`，且每 tick 根据 active_players 计算 worker 并发与 queueing delay。
- 将 1000-player hard cap 标为 benchmark-gated 的同时，不应在 `engine.md` 推导中写成已保证；应给出必须满足的 p95/p99 empirical gate。

### DNP-6 — High — RNG host function 合同缺失/冲突，且排序 seed 表述不完全统一

- 文件引用：`/tmp/swarm-review-R32/specs/reference/api-registry.md:485`
- 文件引用：`/tmp/swarm-review-R32/specs/reference/api-registry.md:496`
- 文件引用：`/tmp/swarm-review-R32/specs/core/04-wasm-sandbox.md:206`
- 文件引用：`/tmp/swarm-review-R32/specs/core/04-wasm-sandbox.md:215`
- 文件引用：`/tmp/swarm-review-R32/specs/core/01-tick-protocol.md:230`
- 文件引用：`/tmp/swarm-review-R32/specs/core/01-tick-protocol.md:837`
- 文件引用：`/tmp/swarm-review-R32/specs/core/01-tick-protocol.md:932`
- 文件引用：`/tmp/swarm-review-R32/design/engine.md:268`

问题描述：
- `api-registry.md` 注册了 `host_get_random` 的响应大小与 fuel 成本。
- `04-wasm-sandbox.md` 的允许 host function 列表没有 `host_get_random`，只列 terrain/range/path/config/rules。
- `01-tick-protocol.md` 又说 WASM 必须使用 `swarm_get_random(sequence)` 从 host 获取确定性随机数，但该名称与 registry 的 `host_get_random` 不一致。
- 排序 seed 在同一 tick-protocol 早期示例为 `Blake3(tick_number || world_seed)`，后续权威合同为 `Blake3("shuffle" || world_seed || tick.to_le_bytes())`；虽然后者更完整，但前者作为代码块仍会误导实现。

影响分析：
- 玩家可用随机数 API 是确定性合同核心之一。若 sandbox 不暴露而 SDK 生成暴露，玩家代码会编译/运行分叉；若实现者自行命名，会破坏 ABI。
- 缺少明确的 `(player_id, tick, sequence, domain)` 派生规则时，同一玩家多次调用 random 的流位置、跨 replay 行为、host call fuel 成本都可能不一致。

修复建议：
- 在 `api-registry.md`、`04-wasm-sandbox.md`、`01-tick-protocol.md` 统一为一个名称，例如 `host_get_random(sequence, out_ptr, out_len)`。
- 明确派生公式：`Blake3("wasm_random" || world_seed || tick_le || player_id_le || sequence_le || request_index_le)`，并规定每次调用最大 bytes、offset、rejection behavior。
- 删除或改写早期 `Blake3(tick_number || world_seed)` 示例，统一使用带 domain separation 的权威公式。

### DNP-7 — Medium — Fuel metering 被描述成“CPU 指令计数”，但 Wasmtime fuel、host function fuel 与硬件 admission 未形成同一单位合同

- 文件引用：`/tmp/swarm-review-R32/design/README.md:43`
- 文件引用：`/tmp/swarm-review-R32/design/README.md:54`
- 文件引用：`/tmp/swarm-review-R32/design/tech-choices.md:40`
- 文件引用：`/tmp/swarm-review-R32/design/engine.md:324`
- 文件引用：`/tmp/swarm-review-R32/design/engine.md:332`
- 文件引用：`/tmp/swarm-review-R32/specs/core/04-wasm-sandbox.md:298`
- 文件引用：`/tmp/swarm-review-R32/specs/core/04-wasm-sandbox.md:351`
- 文件引用：`/tmp/swarm-review-R32/specs/core/04-wasm-sandbox.md:355`

问题描述：
- 文档多处把 fuel 描述为 CPU 指令数或同等算力。
- `engine.md` admission 公式使用 `PER_CORE_MIPS` 推导 fuel budget，但 `04-wasm-sandbox.md` 又把 host functions 定义为手工 fuel cost（如 path_find 按 explored_nodes/edges）。
- Wasmtime fuel 是 runtime-defined metering unit，不等同于硬件 CPU instruction，也不天然跨 Wasmtime version / Cranelift opt level / target_arch 保持成本稳定。

影响分析：
- “C 玩家和 Python 玩家同等算力”的公平性声明会被误解为硬件指令级公平，但实际是 engine-defined fuel economy。
- Wasmtime 版本升级或编译优化变化可能改变同一 WASM 的 fuel 消耗，影响长期 replay 的 billing/audit 可解释性。
- Host function 的算法工作量 fuel 与 Wasmtime opcode fuel 若无校准，会产生“把计算搬进 host function 更便宜/更贵”的套利空间。

修复建议：
- 将公开合同改为“deterministic engine fuel units”，不要称为真实 CPU 指令数。
- TickCommitRecord 记录 `fuel_schedule_version`、`wasmtime_build_commit`、`host_cost_table_version`。
- 为 Wasmtime opcode fuel 与 host function fuel 建立版本化成本表；升级 Wasmtime 或 cost table 时必须 bump version，并给 replay/billing 说明。
- Admission 使用 empirical benchmark 校准后的 `fuel_per_ms_p95`，而非直接 `PER_CORE_MIPS`。

### DNP-8 — Medium — CommandAction 覆盖不一致：Manifest/Registry 有 21 类，Phase 2a 分类与校验表未闭合 economy operations

- 文件引用：`/tmp/swarm-review-R32/specs/reference/api-registry.md:48`
- 文件引用：`/tmp/swarm-review-R32/specs/reference/api-registry.md:66`
- 文件引用：`/tmp/swarm-review-R32/specs/reference/api-registry.md:72`
- 文件引用：`/tmp/swarm-review-R32/design/engine.md:225`
- 文件引用：`/tmp/swarm-review-R32/specs/core/06-phase2b-system-manifest.md:95`
- 文件引用：`/tmp/swarm-review-R32/specs/core/02-command-validation.md:596`

问题描述：
- API Registry 声明 CommandAction 总数 21，包含 `TransferToGlobal` / `TransferFromGlobal` 两个 economy_operation。
- `engine.md` Phase 2a inline 列表未包含这两个 action。
- Manifest S01/S05 handled commands 也未包含这两个 action。
- `02-command-validation.md` 字段级穷举校验表同样未覆盖 `TransferToGlobal` / `TransferFromGlobal`。

影响分析：
- 这是状态机完备性缺口。IDL/Registry 允许 WASM 发出 economy operation，但 tick 执行 manifest 没有明确在哪个 system 校验和应用。
- 若实现者临时接到 ResourceLedger 或 Gateway，将形成第二套状态修改路径，违反 command validation 单一路径与 replay determinism。

修复建议：
- 在 `06-phase2b-system-manifest.md` 中明确 economy operations 的 Phase 2a handler，例如纳入 S05 transfer_system 或新增 S05b economy_operation_system。
- 在 `02-command-validation.md` 字段级表补齐 `TransferToGlobal` / `TransferFromGlobal` 的 ownership、range、resource、global storage cap、ledger emission 顺序。
- 在 `engine.md` Phase 2a 分类表引用 Registry 的 21 action 并说明每个 action 的执行系统。

## 3. 亮点

- 确定性核心方向正确：`IndexMap` 替代非确定性 HashMap、定点整数替代 f64、StableEntityId 排序、manifest hash 入 TickTrace 都是正确的基础设计。
- Tick 生命周期有清晰的 COLLECT / EXECUTE / BROADCAST 分层，且快照在玩家 WASM 执行前一次性构建，避免玩家执行顺序影响输入快照。
- Seeded Shuffle 使用 canonical PlayerId sort + Fisher-Yates + rejection sampling，公平性与确定性兼顾，比简单 `(player_id, sequence)` 排序更合理。
- WASM sandbox 的 long-lived worker pool + per-tick clean Store reset 是性能上必要且方向正确的折中；禁用 clock/random/filesystem/network/threads/relaxed SIMD 的边界符合确定性要求。
- S16-S22b typed buffer + S22 serial committer 的大方向正确，能解决状态效果并行写入的核心竞争；问题主要是 R/W matrix 与 effect application 还没完全对齐。
- Replay-critical 与 rich debug trace 分层思路正确，若把冲突表述修正为单一合同，可以形成可实施的持久化模型。

## 4. CrossCheck — 需要跨方向检查

- CX-1: Room-partition 的 shadow write / global publish 需要与 FDB key layout、operator recovery runbook 对齐 → 建议 Persistence / Ops 方向检查 crash recovery、GC、read path 是否只从 global head 进入。
- CX-2: `host_get_random` / `swarm_get_random` ABI 命名和 SDK 暴露方式不一致 → 建议 API / SDK 方向检查 IDL、SDK codegen、WASM import namespace 的统一性。
- CX-3: `TransferToGlobal` / `TransferFromGlobal` 在 Registry 中存在但执行 manifest 未闭合 → 建议 Economy / Resource Ledger 方向检查 economy operation 是否必须走 ResourceLedger 且无第二写入路径。
- CX-4: `NotVisibleOrNotFound` 可见性优先与部分逐指令表仍先写 ObjectNotFound / target exists → 建议 Security 方向检查错误码优先级是否会泄露不可见实体存在性。
- CX-5: Sandbox seccomp 允许 `nanosleep`，但禁 clock/random/network → 建议 Security / Sandbox 方向检查 nanosleep 是否会形成 timing side-channel 或被 epoch interruption 安全覆盖。
- CX-6: `Tutorial/Novice` special attacks 默认禁用但 Registry 允许 world.toml 覆盖 → 建议 Gameplay / Product 方向检查模式语义是否允许服主覆盖核心 mode unlock 策略。
