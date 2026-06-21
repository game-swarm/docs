# R30 Determinism & Performance Review — GPT-5.5

## 1. Verdict

REQUEST_MAJOR_CHANGES

理由：设计整体方向可行，且已覆盖大量确定性与性能关键面；但当前文档存在数个会直接破坏 replay/调度确定性或使容量合同失真的重大矛盾。尤其是 Status Effects 并行写入合同、room-partition cross-room 事务语义、TickTrace/replay-critical 持久化语义、sandbox CPU 配额与 2500ms deadline 的冲突，需要在目标设计中一次性修正。

## 2. 发现的问题

### DNP-1 — Status Effects Parallel Set 同时声明 S16-S22 并行且多系统写 `StatusState`

- Severity: Critical
- 文件引用：
  - `/tmp/swarm-review-R30/specs/core/06-phase2b-system-manifest.md:45`
  - `/tmp/swarm-review-R30/specs/core/06-phase2b-system-manifest.md:203`
  - `/tmp/swarm-review-R30/specs/core/06-phase2b-system-manifest.md:212`
  - `/tmp/swarm-review-R30/specs/core/06-phase2b-system-manifest.md:216`
  - `/tmp/swarm-review-R30/specs/core/06-phase2b-system-manifest.md:357`
- 问题描述：Manifest 将 S16-S22 全部放在 “Parallel Set B: Status Effects” 内，并在 R/W 表中声明 S16-S21 与 S22 都写 `StatusState`；但同文档又声明 “每种 status/component 有且仅有一个写入者 system”，且唯一 writer 是 S22 `status_adv`。并行安全证明声称 S22 “与其他 system 无冲突（不同 component 实例）”，但 S22 的定义是读取全部 pending intents 并统一写入所有 `StatusState`，不是单一 subtype。
- 影响分析：这是确定性与并行调度的硬阻塞。实现者若按 parallel set 并行运行，S16-S21 与 S22 可能产生写写竞争或非确定性覆盖；若按 unique writer contract 实现，则 S16-S21 的 writes/系统职责是错的。Replay checksum 在不同线程调度、Bevy archetype layout 或任务切分下可能分叉。
- 修复建议：将 Status Effects 改为两段明确调度：`S16-S21` 只读现有 status/subtype 并产生 typed intent/effect buffers，禁止写 `StatusState`；`S22 status_advance_system` 从 Parallel Set B 移出，作为 serial reducer/committer，在 S16-S21 完成后唯一写入全部 `StatusState`。同步更新 System Schedule、R/W Matrix、parallel safety proof 和 CI 冲突检测规则。

### DNP-2 — Room-Partition cross-room 2PC 的 `fallback to best-effort` 破坏 tick 原子性

- Severity: High
- 文件引用：
  - `/tmp/swarm-review-R30/specs/core/05-persistence-contract.md:340`
  - `/tmp/swarm-review-R30/specs/core/05-persistence-contract.md:357`
  - `/tmp/swarm-review-R30/specs/core/05-persistence-contract.md:370`
  - `/tmp/swarm-review-R30/specs/core/01-tick-protocol.md:392`
  - `/tmp/swarm-review-R30/specs/core/01-tick-protocol.md:814`
- 问题描述：Persistence Contract 为 500+ players 引入 room-level partition，并声明 cross-room operations 使用 2PC，但实现约束表写 “2PC，超时 3s，fallback to best-effort”。这与 Tick 协议中 “整个阶段二包裹在 FoundationDB 事务中” 和 “状态 + 审计 + fuel 三者原子持久化” 的确定性原子提交合同冲突。
- 影响分析：跨房间移动、跨房间攻击/传输、出口穿越或区域效果一旦进入 best-effort，就可能出现 source room 已提交、target room 未提交的半状态。该半状态不再满足 “tick occurred / did not occur” 二值语义，replay verifier 也无法仅靠单一 command order 重建权威状态。不同节点对 timeout 的观察还可能产生非确定性。
- 修复建议：删除 `best-effort` fallback。Cross-room operation 必须采用确定性 transaction coordinator：所有涉及 room 的 intent 先进入 canonical cross-room intent log，按 `(tick, sorted_room_ids, command_sort_key)` 排序，使用 FDB transaction 或可验证 2PC commit record 原子提交；超时则整个 cross-room intent 在该 tick deterministic reject/abort，不允许部分生效。若无法在 tick deadline 内完成，tick 放弃并 snapshot restore，而不是 best-effort。

### DNP-3 — TickTrace / replay-critical 持久化语义在文档间互相冲突

- Severity: High
- 文件引用：
  - `/tmp/swarm-review-R30/specs/core/01-tick-protocol.md:601`
  - `/tmp/swarm-review-R30/specs/core/01-tick-protocol.md:614`
  - `/tmp/swarm-review-R30/specs/core/01-tick-protocol.md:620`
  - `/tmp/swarm-review-R30/specs/core/05-persistence-contract.md:34`
  - `/tmp/swarm-review-R30/specs/core/05-persistence-contract.md:51`
  - `/tmp/swarm-review-R30/specs/core/05-persistence-contract.md:144`
  - `/tmp/swarm-review-R30/specs/core/05-persistence-contract.md:166`
- 问题描述：Tick Protocol §6.3.4 声明 TickTrace 写入与 tick 执行同一 FDB 事务，写入失败意味着 tick 放弃，并声称不存在 “tick 成功但回放数据丢失”。但 Persistence Contract 明确将 rich TickTrace blob 异步对象存储，FDB commit 成功后 blob 可能 failed，状态仍完整但 replay 不可用 / audit_gap。
- 影响分析：实现者无法判断 `TickTrace` 一词到底指 replay-critical commands/rejections/fuel/state checksum，还是完整 rich trace blob。审计、CI replay、反作弊和故障恢复会产生不同实现：一种会在 blob 失败时回滚 tick，另一种会保留 tick 并标记 audit_gap。该冲突会影响 terminal_state、hash chain、告警和 replay 可用性判定。
- 修复建议：统一术语：`TickCommitRecord` / replay-critical subset 必须在 FDB 同事务提交；`RichTraceBlob` 可异步失败；`ReplayArtifact` 可由 FDB critical subset + keyframe/delta 重建。将 `01-tick-protocol.md` 中 “TickTrace 写入失败 = tick 放弃 / 不存在 tick 成功但回放数据丢失” 改为仅适用于 FDB replay-critical subset。Rich trace blob 失败应标记 `audit_gap`，但 deterministic replay 仍以 FDB commands/rejections/fuel/state checksum 为准。

### DNP-4 — Sandbox CPU cgroup 配额与 per-player deadline/fuel 预算不一致

- Severity: High
- 文件引用：
  - `/tmp/swarm-review-R30/specs/core/04-wasm-sandbox.md:257`
  - `/tmp/swarm-review-R30/specs/core/04-wasm-sandbox.md:260`
  - `/tmp/swarm-review-R30/specs/core/04-wasm-sandbox.md:294`
  - `/tmp/swarm-review-R30/specs/core/04-wasm-sandbox.md:298`
  - `/tmp/swarm-review-R30/specs/core/04-wasm-sandbox.md:301`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:502`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:503`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:504`
  - `/tmp/swarm-review-R30/design/engine.md:294`
  - `/tmp/swarm-review-R30/design/engine.md:298`
- 问题描述：WASM sandbox 同时声明 per-player sandbox deadline 为 2500ms、fuel 为 10,000,000，但 cgroup `cpu.max = 250000 3000000` 表示每 3s 仅 0.25 CPU 秒。一个玩家可能在 wall-clock 2500ms 内被 cgroup throttle 到只获得 250ms CPU；这与 “2500ms deadline” 和 fuel admission formula 的语义不同。
- 影响分析：公平资源核算会混杂两套上限：Wasmtime fuel 与 Linux CFS throttling。不同宿主 CPU 性能、cgroup 调度、worker 数量会导致同样 fuel 的玩家获得不同 wall-clock 进展和 timeout 行为。性能合同里 COLLECT 2500ms 与 API registry 0.25 CPU 秒也会让容量估算失真。
- 修复建议：明确资源层级：fuel 是玩家计算配额，cgroup CPU 只作为 runaway/host protection，不应低于最大 fuel 在目标硬件上的保守 CPU 时间；或将 per-player CPU budget 正式定义为 250ms CPU-time，并把 collect deadline 改为 wall-clock kill guard。文档需给出 `MAX_FUEL ↔ calibrated CPU cycles/time` 的校准流程，且 CI/benchmark gate 验证 fuel exhausted 优先于 cgroup throttling 触发。

### DNP-5 — 1000-player 容量推导数学与 worker pool 默认值不匹配

- Severity: High
- 文件引用：
  - `/tmp/swarm-review-R30/design/engine.md:352`
  - `/tmp/swarm-review-R30/design/engine.md:359`
  - `/tmp/swarm-review-R30/design/engine.md:388`
  - `/tmp/swarm-review-R30/design/engine.md:391`
  - `/tmp/swarm-review-R30/design/engine.md:393`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:535`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:536`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:537`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:538`
- 问题描述：engine.md 推导 1000 players × 5ms 平均执行依赖 “1000 workers / 40 cores” 并声称 wall-clock 约 25ms，但 1000 × 5ms / 40 cores = 125ms（未计调度/IPC/snapshot stitching）。同时 API registry 声明 World worker_pool_max 默认 256，hard cap 1000；默认配置下并不会有 1000 workers。
- 影响分析：容量合同是 deadline-driven 硬合同，但核心推导存在算术错误和默认参数冲突。该问题会误导 admission gating、worker pool sizing、fuel fair-share 和硬件 baseline；在性能评审视角下，hard cap 1000 的设计依据不足。
- 修复建议：重写容量推导：以 `ceil(active_players / worker_pool_size) × p99_wasm_time + dispatch_overhead + snapshot_stitching` 建模，分别给出 default 256 workers 与 hard cap 1000 workers 的预算。将 hard cap players 标注为 benchmark-gated 可以保留，但必须移除错误的 25ms 推导，并把 cgroup CPU 配额纳入模型。

### DNP-6 — Seeded shuffle 存在 modulo bias 且 active player canonical order 未完整指定

- Severity: Medium
- 文件引用：
  - `/tmp/swarm-review-R30/specs/core/01-tick-protocol.md:227`
  - `/tmp/swarm-review-R30/specs/core/01-tick-protocol.md:230`
  - `/tmp/swarm-review-R30/specs/core/01-tick-protocol.md:232`
  - `/tmp/swarm-review-R30/specs/core/01-tick-protocol.md:234`
  - `/tmp/swarm-review-R30/specs/core/01-tick-protocol.md:772`
  - `/tmp/swarm-review-R30/design/engine.md:268`
- 问题描述：shuffle 伪代码使用 `XOF.read_u64() % (N - i)`，这会产生 modulo bias；同时 `seeded_shuffle(&active_players, &seed)` 没有明确 active_players 输入列表的 canonical sort，只在后文提到 TickTrace 记录活跃玩家集快照。
- 影响分析：modulo bias 对单 tick 确定性影响不大，但对“长期期望均等”的公平性合同不严格。更重要的是，如果 active_players 来自 HashMap/Bevy query/FDB range scan 的未规范化顺序，即使 seed 相同，不同实现也可能 shuffle 出不同 order，导致 replay 分叉。
- 修复建议：规定 shuffle 输入必须先按 canonical `PlayerId` 字节序升序排序，TickTrace 记录该排序后的 active player vector hash。Fisher-Yates 抽样使用 rejection sampling（拒绝超过最大可整除区间的 `u64`）或 Blake3 XOF 生成足够宽整数后 unbiased map 到 `[0, N-i)`。

### DNP-7 — WASM RNG host 合同不完整且与 Host Function Registry 冲突

- Severity: Medium
- 文件引用：
  - `/tmp/swarm-review-R30/specs/core/01-tick-protocol.md:842`
  - `/tmp/swarm-review-R30/specs/core/01-tick-protocol.md:853`
  - `/tmp/swarm-review-R30/specs/core/04-wasm-sandbox.md:202`
  - `/tmp/swarm-review-R30/specs/core/04-wasm-sandbox.md:207`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:398`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:400`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:406`
- 问题描述：Tick Protocol §9.5 写 “任何 WASM host function 不暴露 RNG 或熵源——WASM 代码必须使用 `swarm_get_random(sequence)` 从 host 获取确定性随机数”。但 WASM Sandbox 允许的 host function 清单和 API Registry 的 5 个 Host Functions 均没有 `swarm_get_random`。
- 影响分析：玩家代码的随机性合同不直观：到底禁止所有 RNG，还是提供 deterministic RNG host function？如果 SDK 自行在 WASM 内实现 PRNG，seed 从何而来？如果 host 提供 RNG，fuel cost、sequence 防重放、namespace、replay hash 都未注册。该空白会导致 SDK/engine/replay verifier 实现分叉。
- 修复建议：二选一并写入 API Registry：A) 不提供玩家 RNG，玩家只能自带 deterministic PRNG 且 seed 来自 snapshot 中的公开 deterministic field；B) 新增 `host_get_random(sequence, out_ptr, out_len)`，注册 ABI、fuel cost、per-tick call limit、domain separation、sequence monotonic rule，并明确它只返回 per-player deterministic stream，不泄露 engine world_seed。

### DNP-8 — RejectionReason/校验表仍引用未注册 canonical codes，易导致 wire contract 分叉

- Severity: Medium
- 文件引用：
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:90`
  - `/tmp/swarm-review-R30/specs/core/02-command-validation.md:154`
  - `/tmp/swarm-review-R30/specs/core/02-command-validation.md:169`
  - `/tmp/swarm-review-R30/specs/core/02-command-validation.md:171`
  - `/tmp/swarm-review-R30/specs/core/02-command-validation.md:345`
  - `/tmp/swarm-review-R30/specs/core/02-command-validation.md:548`
- 问题描述：Command Validation 说明表仍出现 `TileBlocked`、`StillSpawning`、`SourceEmpty`、`TargetFull`、`MainActionQuotaExceeded` 等名称；虽然文档前置说明称旧码应放入 `debug_detail`，但这些表格没有全部标注 `(debug_detail)` 或映射到 47 个 canonical RejectionReason。API Registry 的 canonical enum 中也没有这些名称。
- 影响分析：实现者可能把说明性失败码误实现为 wire enum，破坏 SDK typed exception、Replay trace 稳定性和跨语言一致性。对 determinism 来说，rejection reason 是 TickTrace/replay-critical 子集的一部分，wire code 不一致会导致 commands_hash/rejections_hash 分叉。
- 修复建议：在 `02-command-validation.md` 增加 “non-canonical label → canonical RejectionReason + debug_detail template” 映射表，并把逐指令矩阵所有失败码改为 canonical code；非 canonical 条件统一写 `(canonical: X, debug_detail: Y)`。

### DNP-9 — Snapshot 构建描述存在 O(P×E) 与两阶段分片模型的表述冲突

- Severity: Low
- 文件引用：
  - `/tmp/swarm-review-R30/design/engine.md:258`
  - `/tmp/swarm-review-R30/specs/core/01-tick-protocol.md:136`
  - `/tmp/swarm-review-R30/specs/core/01-tick-protocol.md:139`
  - `/tmp/swarm-review-R30/specs/core/01-tick-protocol.md:157`
  - `/tmp/swarm-review-R30/specs/core/01-tick-protocol.md:176`
- 问题描述：engine.md 明确两阶段快照为 “tick 开始一次性构建完整世界快照，按房间分片；每玩家拼接可见房间”。但 tick-protocol §2.3 的伪代码仍是 `fn build_snapshot(player_id, tick)` 并调用 `visibility_filter(all_entities, player_id, tick)`，容易被理解为每玩家扫描 all_entities。
- 影响分析：这是性能规范可实施性问题，不一定破坏确定性，但可能让实现回到 O(players × entities)，使 500/1000 player 预算不可达。
- 修复建议：将 tick-protocol 伪代码改为 `build_world_snapshot_once()` + `partition_by_room()` + `build_player_view(player_id, room_shards)`，并明确玩家视图只扫描可见 room shard，不扫描全世界实体。

## 3. 亮点

- 确定性合同覆盖面很完整：`01-tick-protocol.md:758` 起明确了排序、部署生效、输出状态、TickTrace、RNG、ECS 调度、WASM output 截断和 RuleMod 边界，方向正确。
- Float 确定性处理到位：API Registry 明确替换所有 `f64` 为 fixed-point integer types，engine.md 也规定资源/年龄/伤害/进度使用整数与 floor rounding，降低跨平台 replay 风险。
- ECS manifest 思路正确：`06-phase2b-system-manifest.md` 使用 stable system IDs、manifest hash、显式 R/W matrix 和 stable entity iteration，这是可回放 ECS 的必要基础。
- Phase 2a inline + current world validation 的 TOCTOU 合同清晰：逐条校验/应用、Spawn pending 不可见、Hack owner 原身份校验、超时输出整批丢弃，都是确定性友好的设计。
- WASM sandbox 基线扎实：Wasmtime pinned version、fuel metering、epoch interruption、Store reset、WASI 默认关闭、host function 只读、StartSection 拒绝、OS/cgroup/seccomp checklist 都是合理防线。
- Snapshot truncation 已强调 stable `entity_id` sort、critical entities 不可截断、展示层与 WASM cap 分离，避免 ECS query order 进入玩家输入。
- Persistence Contract 将 replay-critical subset 与 rich/debug blob 分层是正确方向；只需要统一术语和失败语义即可成为稳固的 replay 基础。

## 4. CrossCheck — 需要跨方向检查

- CX-1: `swarm_get_random(sequence)` 是否应存在，以及若存在是否会泄露 world_seed / 影响安全模型 → 建议 Security/Auth 方向检查 RNG host function 的暴露边界、seed 隔离和反预测能力。
- CX-2: Room-partition cross-room 事务若删除 best-effort 后，跨房间移动/攻击/物流的玩法语义是否仍符合游戏设计 → 建议 Gameplay/Rules 方向检查跨房间 action 的原子性与失败反馈。
- CX-3: Overload 将目标 fuel budget 降至 20% 下限是否构成可接受的 PvP 经济/体验压制 → 建议 Gameplay Balance 方向检查长期压制、Fortify 反制成本和新手保护交互。
- CX-4: RichTraceBlob `audit_gap` 对反作弊、管理员申诉和赛事审计是否足够 → 建议 Security/Operations 方向检查 audit SLA、对象存储故障告警和赛事模式是否需要更强持久化。
- CX-5: `debug_detail` 在 practice/training 模式暴露 cooldown/timer/state diff 是否可能成为 visibility oracle → 建议 Security/API 方向检查不同 detail_level 的可见性红线。
- CX-6: MCP simulate/dry-run 独立预算是否会被 AI agent 用于离线穷举搜索从而影响竞技公平 → 建议 AI/MCP 方向检查 simulate 输出、rate limit 与 Arena tournament 规则。
