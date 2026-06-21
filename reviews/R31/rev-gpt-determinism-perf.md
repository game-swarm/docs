# R31 Determinism & Performance Review — GPT-5.5

## 1. Verdict

REQUEST_MAJOR_CHANGES

理由：设计已经覆盖了 determinism、fuel metering、ECS manifest、fixed-point、snapshot truncation、replay-critical 分层等核心方向，但仍存在若干会直接破坏 replay/commit 原子性、ECS 并行安全证明、以及 WASM 输出合同一致性的阻塞问题。尤其是 room-partition 提交流程与 failure semantics 之间存在互相矛盾的 partial commit / all-or-reject 表述，必须在目标设计中收敛为单一可实现语义。

## 2. 发现的问题

### DNP-1 — Critical — Room-partition 提交语义同时声明“无部分提交”和“其他房间独立推进”

- 文件引用：`/tmp/swarm-review-R31/specs/core/01-tick-protocol.md:396`
- 文件引用：`/tmp/swarm-review-R31/specs/core/01-tick-protocol.md:398`
- 文件引用：`/tmp/swarm-review-R31/specs/core/01-tick-protocol.md:432`
- 文件引用：`/tmp/swarm-review-R31/specs/core/01-tick-protocol.md:455`
- 文件引用：`/tmp/swarm-review-R31/specs/core/01-tick-protocol.md:458`
- 文件引用：`/tmp/swarm-review-R31/specs/core/05-persistence-contract.md:370`

问题描述：`01-tick-protocol` 一方面声明生产环境 room-partition commit 且“不存在 best-effort 游戏状态降级路径”、跨房间操作“All-or-Reject”、不允许部分提交；另一方面 failure matrix 又写“单房间 commit 失败 → 该房间 snapshot 恢复，其他房间独立推进”，cross-room timeout 还允许 “Deterministic reject OR tick abandon”。`05-persistence-contract` 进一步写 `Cross-room conflict ... fallback to best-effort`。

影响分析：这是 replay determinism 和 tick atomicity 的核心阻塞。若同一 tick 内部分房间推进、部分房间回滚，则全局 tick_counter、GlobalTickCommit、cross-room intent、resource ledger、player ordering 与 replay hash chain 都会出现歧义。不同节点/重放器如果选择“全局 abandon”“相关房间 rollback”“非相关房间推进”或“best-effort”中的不同解释，会产生合法但不同的世界状态。

修复建议：目标设计中只能保留一种语义。建议采用全局 tick 原子语义：每个 tick 先在内存 Bevy World 完整执行，room-partition 仅作为 FDB 写入分区优化；任一 per-room commit、cross-room coordinator、GlobalTickCommit 失败均导致整个 tick abandon + 全局 snapshot restore + retry，不允许任何 committed room 独立推进。若坚持局部推进，则必须引入 per-room tick/version、跨房间 barrier、global ledger 分片与 replay verifier 的 partial-tick 模型；当前文档未定义这些，因此不应保留 best-effort/partial wording。

### DNP-2 — High — TickCommitRecord / RichTraceBlob 的 replay-critical 边界互相冲突

- 文件引用：`/tmp/swarm-review-R31/specs/core/05-persistence-contract.md:34`
- 文件引用：`/tmp/swarm-review-R31/specs/core/05-persistence-contract.md:45`
- 文件引用：`/tmp/swarm-review-R31/specs/core/05-persistence-contract.md:51`
- 文件引用：`/tmp/swarm-review-R31/specs/core/05-persistence-contract.md:132`
- 文件引用：`/tmp/swarm-review-R31/specs/core/05-persistence-contract.md:152`
- 文件引用：`/tmp/swarm-review-R31/specs/core/05-persistence-contract.md:166`
- 文件引用：`/tmp/swarm-review-R31/specs/core/05-persistence-contract.md:174`
- 文件引用：`/tmp/swarm-review-R31/specs/reference/api-registry.md:872`

问题描述：`05-persistence-contract` §2.1 明确 commands/rejections/fuel 等 replay-critical subset 必须在 FDB 原子提交；但 §3 的 Phase B 只描述写入 tick_head、tick_manifest、content_hash、hash_chain 和状态 mutation，没有显式写入 §2.1 的 replay-critical commands/fuel/deploy decisions。随后 §3/§4 又说 blob 写入失败会导致 replay 不可用或 replay gap；而 API Registry 明确声明 blob 缺失不影响 deterministic replay，仅降级 rich audit。

影响分析：实现者无法判断 deterministic replay 到底依赖 FDB 中的 TickCommitRecord，还是依赖对象存储中的 RichTraceBlob。若 commands/rejections/fuel 实际只在 blob 中，blob 失败会破坏 replay；若它们在 FDB 中，文档中的“replay 不可用”就是错误告警语义。这会直接影响反作弊审计、failure recovery、terminal_state 分类和 TickCommitRecord hash chain。

修复建议：将 tick 持久化序列改成两条明确路径：FDB same-tx 写入 replay-critical `TickCommitRecord`（包含 §2.1 十项字段，尤其 commands/rejections/fuel/deploy_activation_decision/canonical_codec_version），对象存储只写 `RichTraceBlob` 与可重建 delta/debug。所有 `upload_status=failed → replay 不可用/replay gap` 改为 `rich audit unavailable / terminal_state=audit_gap`；只有 FDB replay-critical 字段缺失才允许 `unreplayable`，且该 tick 应 abandon。

### DNP-3 — High — Combat Parallel Set 的 R/W 声明与“reduce 后统一应用”不一致，无法证明并行安全

- 文件引用：`/tmp/swarm-review-R31/specs/core/06-phase2b-system-manifest.md:181`
- 文件引用：`/tmp/swarm-review-R31/specs/core/06-phase2b-system-manifest.md:184`
- 文件引用：`/tmp/swarm-review-R31/specs/core/06-phase2b-system-manifest.md:188`
- 文件引用：`/tmp/swarm-review-R31/specs/core/06-phase2b-system-manifest.md:206`
- 文件引用：`/tmp/swarm-review-R31/specs/core/06-phase2b-system-manifest.md:208`
- 文件引用：`/tmp/swarm-review-R31/specs/core/06-phase2b-system-manifest.md:372`
- 文件引用：`/tmp/swarm-review-R31/specs/core/06-phase2b-system-manifest.md:384`

问题描述：Manifest 将 S11 attack、S12 ranged_attack、S13 heal 放入 Parallel Set A，并在 R/W 表中声明三者都写 `HitPoints`；同段文字又说“按 target_id partition，同一 entity 只被一个 system 写入。Reduce 后由 S15 统一应用”。但 S15 `damage_application` 读取 PendingDamage buffer 并写 HitPoints，说明 S11-S13 应该写 buffer 而不是直接写 HitPoints。

影响分析：当前表述不足以作为 Bevy ECS 并行调度合同。一个实体可能被敌方 attack/ranged_attack 与友方 heal 在同一 tick 同时作为 target；如果 S11-S13 直接写 HitPoints，顺序会影响最终 HP，且并行写入违反唯一写入/确定性约束。如果实际设计是 buffer+S15 reduce，则 R/W matrix 和 system detail 必须同步，否则 CI 的静态 R/W 验证会验证错误合同。

修复建议：将 S11-S13 改为只写 `PendingDamageBuffer` / `PendingHealBuffer` / `CombatIntentBuffer`，不直接写 `HitPoints`；S15 作为唯一 `HitPoints` writer，按 canonical key（target_id, effect_type, source_id, command_hash）归并 damage/heal 后串行应用。若要保留 S11-S13 直接写，则必须定义全局 target partitioner 如何把同一 target 的所有 attack/ranged/heal 分配到同一个 worker，并给出固定 reduce order；但 buffer+S15 更符合现有 S15 设计。

### DNP-4 — High — WASM 输出超限同时定义为“截断前 256KB”和“整批丢弃”

- 文件引用：`/tmp/swarm-review-R31/specs/core/01-tick-protocol.md:782`
- 文件引用：`/tmp/swarm-review-R31/specs/core/01-tick-protocol.md:951`
- 文件引用：`/tmp/swarm-review-R31/specs/core/01-tick-protocol.md:953`
- 文件引用：`/tmp/swarm-review-R31/specs/core/04-wasm-sandbox.md:191`
- 文件引用：`/tmp/swarm-review-R31/specs/core/04-wasm-sandbox.md:198`
- 文件引用：`/tmp/swarm-review-R31/specs/core/02-command-validation.md:50`

问题描述：统一预算表写 `Output JSON 256 KB → 截断（保留前 256KB）`；但 determinism contract §9.7、WASM ABI 和 command validation schema 都要求超过 256KB 时整批输出丢弃或校验失败。

影响分析：部分截断 JSON 是危险且不直观的合同：截断点可能落在 UTF-8、JSON token 或 command array 中间，导致 parser 行为、错误优先级、partial command 保留策略出现实现分叉。更严重的是，如果某实现尝试“保留可解析前缀”，玩家可构造依赖截断边界的 command prefix，使线上与 replay 或不同语言 parser 分叉。

修复建议：统一为“超过 256KB 的 WASM tick 输出整批丢弃，不解析任何前缀，不保留部分 command，记录 `output_truncated` / `TickValidationFailed`”。预算表、沙箱 ABI、command validation、TickTrace 术语全部使用同一语义。

### DNP-5 — Medium — Host Function 权威列表遗漏 `host_get_random`，RNG 合同不够直观

- 文件引用：`/tmp/swarm-review-R31/specs/reference/api-registry.md:441`
- 文件引用：`/tmp/swarm-review-R31/specs/reference/api-registry.md:454`
- 文件引用：`/tmp/swarm-review-R31/specs/reference/api-registry.md:456`
- 文件引用：`/tmp/swarm-review-R31/specs/core/04-wasm-sandbox.md:202`
- 文件引用：`/tmp/swarm-review-R31/specs/core/04-wasm-sandbox.md:207`
- 文件引用：`/tmp/swarm-review-R31/specs/core/04-wasm-sandbox.md:215`
- 文件引用：`/tmp/swarm-review-R31/specs/core/01-tick-protocol.md:929`

问题描述：API Registry 声明 Host Functions 共 6 个，包含 `host_get_random`；`04-wasm-sandbox` 的允许 Host Function 列表只列 5 个查询函数，未列 `host_get_random`。同时 `host_get_random(sequence)` 被描述为只读、不改变世界状态，sequence 由调用者提供；文档没有明确 repeated sequence 是否返回同一随机 bytes、是否扣调用序号、是否需要 drone_id/object_id 参与 domain、以及返回 bytes 的 canonical endian/stream offset。

影响分析：如果实现者以 `04-wasm-sandbox` 为准，合法玩家模块导入 `host_get_random` 会被拒绝；如果以 API Registry 为准，则 RNG 调用合同仍可能被不同 SDK 解释为“随机流 next()”或“按 sequence 寻址的 stateless XOF”。这不一定破坏引擎世界 determinism，但会让玩家代码跨语言 replay、SDK 测试和反作弊解释不稳定。

修复建议：在 `04-wasm-sandbox` 加入 `host_get_random` 并引用 API Registry 为权威签名。明确它是 stateless deterministic XOF：`bytes = Blake3_XOF("wasm-rng" || world_seed_epoch || tick || player_id || actor_id || sequence).read(out_len)`；同 tick 同 actor 同 sequence 必须返回相同 bytes；不会推进隐藏状态；out_len ≤256；重复 sequence 是允许但由玩家承担相关性风险。若不希望重复，需定义 per-tick monotonic sequence validator。

### DNP-6 — Medium — `Leech` / `Fabricate` 的目标状态在 API Registry 与 Manifest 中冲突

- 文件引用：`/tmp/swarm-review-R31/specs/reference/api-registry.md:87`
- 文件引用：`/tmp/swarm-review-R31/specs/reference/api-registry.md:90`
- 文件引用：`/tmp/swarm-review-R31/specs/core/06-phase2b-system-manifest.md:57`
- 文件引用：`/tmp/swarm-review-R31/specs/core/06-phase2b-system-manifest.md:76`
- 文件引用：`/tmp/swarm-review-R31/specs/core/06-phase2b-system-manifest.md:301`
- 文件引用：`/tmp/swarm-review-R31/specs/core/06-phase2b-system-manifest.md:310`

问题描述：API Registry 将 `Leech` 与 `Fabricate` 标为 `⏳ Tier 2`，并说明在 `custom_action_def` 中已注册但标记 Tier 2；Manifest 则明确 8 种特殊攻击全部是核心目标设计，Standard/Arena 全量启用，不存在 Tier/Future 语义。

影响分析：CommandAction 可用性属于状态机完备性与 replay-critical API surface。若 registry/IDL 仍带 Tier 2 标记，实现者可能在 Standard mode 禁用这两个 action，或 SDK 将其标成非核心/可选；而 Manifest 的 S22a/S22b、R/W matrix、mode unlock 又假定其全量参与 tick。这样会造成线上命令接受、replay verifier、SDK schema 与 manifest hash 的分叉。

修复建议：将 API Registry/IDL 中 `Leech`、`Fabricate` 的 Tier 2 标记移除，统一声明为核心 special_attack；如果确实需要按 world.toml 关闭，必须通过 World Action Manifest 的 mode capability 明确记录进 replay-critical manifest hash，而不是使用 Tier/Future 文案。

### DNP-7 — Low — 1000-player 容量推导存在算术与叙述不一致

- 文件引用：`/tmp/swarm-review-R31/design/engine.md:391`
- 文件引用：`/tmp/swarm-review-R31/design/engine.md:393`
- 文件引用：`/tmp/swarm-review-R31/design/engine.md:396`
- 文件引用：`/tmp/swarm-review-R31/specs/reference/api-registry.md:582`
- 文件引用：`/tmp/swarm-review-R31/specs/reference/api-registry.md:583`
- 文件引用：`/tmp/swarm-review-R31/specs/reference/api-registry.md:584`

问题描述：engine.md 写 `1000 players × 5ms avg = 5000ms`，随后假设 `1000 workers / 40 cores` 后理论 wall-clock 约 25ms。按总 CPU 工作量除以 40 cores，理论下界是 125ms，而不是 25ms。API Registry 又将 1000 hard cap 标为 benchmark-gated，并默认 worker_pool max 为 256。

影响分析：这是文档可信度和容量准入风险，不是立即的确定性破坏。错误推导会误导 tick 瓶颈分析，低估 COLLECT CPU saturation 和调度 overhead，进而影响 admission formula、per-player fuel throttling、worker_pool sizing 与硬件基线验收。

修复建议：修正推导为 CPU-core bound：`wall_clock_lower_bound = active_players × p50_exec_ms / min(CPU_CORES, worker_pool_size)`，再加 snapshot stitching、IPC、serialization、scheduler overhead。保留 1000 hard cap benchmark-gated，但不要用错误的 25ms 作为理论依据；同时说明默认 256 worker 下的排队模型。

### DNP-8 — Low — 快照构建复杂度叙述仍有 per-player build 伪代码，易造成实现分叉

- 文件引用：`/tmp/swarm-review-R31/design/engine.md:258`
- 文件引用：`/tmp/swarm-review-R31/specs/core/01-tick-protocol.md:136`
- 文件引用：`/tmp/swarm-review-R31/specs/core/01-tick-protocol.md:139`
- 文件引用：`/tmp/swarm-review-R31/specs/core/01-tick-protocol.md:157`
- 文件引用：`/tmp/swarm-review-R31/specs/core/01-tick-protocol.md:171`

问题描述：engine.md 和 tick timeline 已明确采用两阶段快照：tick 开始构建完整世界快照、按房间分片、玩家只做 visibility/filter/stitch；但 `01-tick-protocol` §2.3 的伪代码函数名仍是 `build_snapshot(player_id, tick)`，内部从 `visibility_filter(all_entities, player_id, tick)` 开始，容易被理解为每玩家扫描全实体。

影响分析：这是性能合同可实施性问题。若实现者按伪代码实现，会回退到 O(players × entities) 的热路径，抵消 design/engine.md 中承诺的 O(entities + players × visible_entities) 优化。虽然后文有文字纠正，但伪代码作为实现指导仍可能造成偏差。

修复建议：把伪代码拆成 `build_world_snapshot_once(tick) -> RoomShardSnapshot[]` 与 `build_player_snapshot(player_id, room_shards) -> Snapshot` 两段，并显式禁止 player path 扫描 all_entities；visibility/filter 只能在可见 room shard 上执行。

## 3. 亮点

- Determinism contract 覆盖面较完整：`/tmp/swarm-review-R31/specs/core/01-tick-protocol.md:701` 起明确 PRNG、Blake3 hash、排序、ECS、定点数、IndexMap/HashMap 禁令，方向正确。
- ECS manifest 的 Stable IDs、R/W matrix、Unique Writer Contract 是很好的设计基础：`/tmp/swarm-review-R31/specs/core/06-phase2b-system-manifest.md:13`、`/tmp/swarm-review-R31/specs/core/06-phase2b-system-manifest.md:14`、`/tmp/swarm-review-R31/specs/core/06-phase2b-system-manifest.md:16`。
- Status effects 从并行 buffer production 到 S22 serial committer 的重构清晰，能显著降低并行写状态导致的非确定性风险：`/tmp/swarm-review-R31/specs/core/06-phase2b-system-manifest.md:213`、`/tmp/swarm-review-R31/specs/core/06-phase2b-system-manifest.md:230`。
- WASM sandbox 使用 fuel metering + epoch interruption + per-tick Store reset + WASI 禁用，资源核算和隔离方向合理：`/tmp/swarm-review-R31/specs/core/04-wasm-sandbox.md:70`、`/tmp/swarm-review-R31/specs/core/04-wasm-sandbox.md:97`、`/tmp/swarm-review-R31/specs/core/04-wasm-sandbox.md:101`。
- Fixed-point registry 明确替换 f64，且数值溢出/舍入规则使用整数、checked/u128 中间值和 floor，能避免常见跨平台 float 陷阱：`/tmp/swarm-review-R31/specs/reference/api-registry.md:20`、`/tmp/swarm-review-R31/design/engine.md:463`。
- Replay retry 复用 canonical COLLECT buffer、不重跑 WASM、fuel 不重复扣费，是防止 FDB retry 引入非确定性输出和预算绕过的正确方向：`/tmp/swarm-review-R31/specs/core/05-persistence-contract.md:262`。

## 4. CrossCheck — 需要跨方向检查

- CX-1: seccomp 规则中允许 `clone (仅 CLONE_VM | CLONE_VFORK)`，同表又写 `fork/vfork` 禁止，且 sandbox 无网络/文件系统约束依赖内核细节 → 建议 Security 检查 syscall allowlist 是否会被 vfork/clone 组合绕过。
- CX-2: `NotVisibleOrNotFound` 与 `TargetNotVisible` 同时存在，部分 command matrix 仍使用可区分目标可见性的错误码 → 建议 Security/API 检查可见性 oracle 是否彻底闭合。
- CX-3: `Leech` / `Fabricate` 从 Tier 2 转核心后，gameplay 平衡、教程模式禁用、SDK 示例和 custom action registry 的用户体验可能不一致 → 建议 Gameplay/API 检查 action availability 与玩家文档。
- CX-4: Room-partition 如果改为全局 tick abandon，运维层需要明确 FDB conflict/timeout 告警、degraded mode 和 backpressure 策略 → 建议 Operations 检查 runbook 与 SLO。
- CX-5: Deploy 状态机中 blob upload pending 最多等待 30s 后 FAILED，可能与证书吊销、代码签名、旧模块继续执行策略相互影响 → 建议 Security/Auth 检查部署失败与 revocation policy 的组合语义。
