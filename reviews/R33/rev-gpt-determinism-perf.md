# R33 Determinism & Performance Review — GPT-5.5

## Verdict
REQUEST_MAJOR_CHANGES

## Critical (必须修复，否则 BLOCK) (B1..Bn)

### B1 — `host_get_random` 在 API Registry 与 WASM Sandbox 白名单中不一致，RNG 合同不可实现

- **Severity**: Critical
- **文件引用**:
  - `/data/swarm/docs/specs/reference/api-registry.md:464` — Registry 将 `host_get_random(sequence, out_ptr, out_len)` 注册为 Host Function。
  - `/data/swarm/docs/specs/reference/api-registry.md:466` — 定义其 seed 为 `(tick_seed, player_id, drone_id, sequence)`。
  - `/data/swarm/docs/specs/reference/api-registry.md:477` — 定义每 tick 上限 10 次。
  - `/data/swarm/docs/specs/reference/api-registry.md:489` — 定义最大输出 256 bytes。
  - `/data/swarm/docs/specs/core/04-wasm-sandbox.md:202` — WASM sandbox 允许的 Host Function 列表开始。
  - `/data/swarm/docs/specs/core/04-wasm-sandbox.md:208` — 仅列 `host_get_terrain`。
  - `/data/swarm/docs/specs/core/04-wasm-sandbox.md:209` — 仅列 `host_get_objects_in_range`。
  - `/data/swarm/docs/specs/core/04-wasm-sandbox.md:210` — 仅列 `host_path_find`。
  - `/data/swarm/docs/specs/core/04-wasm-sandbox.md:213` — 仅列 `host_get_world_config`。
  - `/data/swarm/docs/specs/core/04-wasm-sandbox.md:214` — 仅列 `host_get_world_rules`。
  - `/data/swarm/docs/specs/core/04-wasm-sandbox.md:117` — WASI random 被禁用，并要求使用 host function 提供种子 PRNG。
- **问题描述**: RNG host function 在 Registry 是权威 API 的一部分，但 WASM sandbox 的允许导入白名单完全遗漏它。与此同时 sandbox 明确禁止 WASI random 并要求用 host function 获取确定随机数，导致玩家 WASM 没有任何合法随机源。
- **影响分析**: 这是确定性合同的硬断点。实现者若按 API Registry 暴露 `host_get_random`，会违反 sandbox 白名单；若按 sandbox 白名单执行，WASM 侧无法满足 `01-tick-protocol.md` §9.5 中“WASM 代码必须使用 `swarm_get_random(sequence)`”的要求。不同实现会产生不同 ABI、不同 replay envelope、不同 fuel 计费，直接破坏 byte-identical replay 和 SDK 一致性。
- **修复建议**: 将 `host_get_random` 加入 `04-wasm-sandbox.md` §3.2 允许 Host Function、§8 单次调用成本表、§6 资源预算表和导入白名单；统一名称为 `host_get_random` 或 `swarm_get_random`，不要两个名称并存；明确其 fuel 成本、输出排序、错误码、visibility 无关性以及 replay-critical envelope 中是否记录 `host_abi_version`/`host_cost_table_version`。

### B2 — TickCommitRecord / TickTrace Envelope 字段集合多处冲突，replay-critical 边界不唯一

- **Severity**: Critical
- **文件引用**:
  - `/data/swarm/docs/design/engine.md:271` — `TickInputEnvelope` 开始列出字段。
  - `/data/swarm/docs/design/engine.md:274` — 包含 `fuel_schedule_version` 与 `host_cost_table_version`。
  - `/data/swarm/docs/design/engine.md:275` — 仍列 `wasm_status`。
  - `/data/swarm/docs/specs/reference/api-registry.md:643` — Registry 声称 TickTrace Envelope 共 22 个字段。
  - `/data/swarm/docs/specs/reference/api-registry.md:655` — 使用 `terminal_state` 替代旧 `wasm_status`。
  - `/data/swarm/docs/specs/reference/api-registry.md:668` — 包含 `system_manifest_hash`。
  - `/data/swarm/docs/specs/reference/api-registry.md:670` — 包含 `host_abi_version`。
  - `/data/swarm/docs/specs/reference/api-registry.md:671` — 包含 `canonical_codec_version`。
  - `/data/swarm/docs/specs/core/05-persistence-contract.md:34` — Persistence 定义 TickCommitRecord FDB 原子提交字段。
  - `/data/swarm/docs/specs/core/05-persistence-contract.md:36` — 声称 TickCommitRecord 由 10 个字段组成。
  - `/data/swarm/docs/specs/core/05-persistence-contract.md:43` — 10 字段表开始。
  - `/data/swarm/docs/specs/core/05-persistence-contract.md:49` — 包含 `canonical_codec_version`。
  - `/data/swarm/docs/specs/core/05-persistence-contract.md:55` — 仅列 `manifest_hash`，未明确等同 `system_manifest_hash`。
  - `/data/swarm/docs/specs/core/05-persistence-contract.md:302` — 后文又给出扩展 TickCommitRecord 结构。
  - `/data/swarm/docs/specs/core/05-persistence-contract.md:312` — 结构中仍使用 `wasm_status`。
  - `/data/swarm/docs/specs/core/01-tick-protocol.md:993` — WASM output 截断合同开始。
  - `/data/swarm/docs/specs/core/01-tick-protocol.md:1001` — 要求写入 `wasm_output_truncated`、`output_size_bytes`、`truncated_at`。
- **问题描述**: 同一 replay-critical 概念在 engine、api-registry、persistence、tick-protocol 中有至少三套字段集合：engine 的 `TickInputEnvelope`、Registry 的 22 字段 Envelope、Persistence 的 10 字段 TickCommitRecord，且存在 `wasm_status` vs `terminal_state`、`manifest_hash` vs `system_manifest_hash`、fuel/host cost version 是否 replay-critical、output truncation 字段是否进入 FDB 的冲突。
- **影响分析**: Replay verifier 无法知道哪组字段是 byte-identical replay 的最小充分输入。尤其 fuel schedule / host cost table 版本若不在权威 FDB replay-critical 子集内，跨 Wasmtime/engine ABI 升级后的 COLLECT 审计与 fuel 扣费不可验证；output truncation 字段若只在某文档声明，超限输出的 terminal state 和 rejection hash 也可能分叉。
- **修复建议**: 指定一个唯一权威结构，例如 `TickCommitRecordVn`，并在所有文档只引用它。建议将至少以下 replay-critical 字段纳入同一表：`terminal_state`、`fuel_schedule_version`、`host_cost_table_version`、`host_abi_version`、`canonical_codec_version`、`system_manifest_hash`、`limits_manifest_hash`、`visibility_truncation_version`、output truncation 标记/大小、`collect_id/attempt_id/commit_id`。删除或迁移所有旧 `wasm_status` 表述。

### B3 — Canonical RejectionReason 仍被未注册旧码污染，命令拒绝记录不可规范化

- **Severity**: Critical
- **文件引用**:
  - `/data/swarm/docs/specs/reference/api-registry.md:127` — Registry 声称 validation 级只有 26 个 canonical codes。
  - `/data/swarm/docs/specs/reference/api-registry.md:170` — Runtime 级 6 codes 开始。
  - `/data/swarm/docs/specs/core/02-command-validation.md:154` — 文档说明旧码如 `SourceEmpty`、`TargetFull` 已从 wire enum 移除。
  - `/data/swarm/docs/specs/core/01-tick-protocol.md:346` — Resource contention 示例仍返回 `SourceEmpty`。
  - `/data/swarm/docs/specs/core/01-tick-protocol.md:354` — 建造同坐标仍返回 `TileOccupied`。
  - `/data/swarm/docs/specs/core/01-tick-protocol.md:356` — 满血治疗仍返回 `AlreadyFullHealth`。
  - `/data/swarm/docs/specs/core/01-tick-protocol.md:357` — 容量满 transfer 仍返回 `TargetFull`。
  - `/data/swarm/docs/specs/core/02-command-validation.md:57` — Tick 输出校验失败记录为 `TickValidationFailed`。
  - `/data/swarm/docs/specs/core/02-command-validation.md:547` — Main action quota 失败返回 `MainActionQuotaExceeded`。
  - `/data/swarm/docs/specs/core/01-tick-protocol.md:1000` — output 超限产出 `output_truncated`。
- **问题描述**: API Registry 明确要求所有拒绝原因为 canonical enum，但 tick-protocol 与 command-validation 仍使用多个未注册或已废弃错误码。这些错误码有的被文档自己声明为旧码，有的完全未出现在 Registry runtime/validation 表中。
- **影响分析**: RejectionReason 是 TickCommitRecord 的 replay-critical 内容。未注册错误码会导致 wire enum 不可编码、SDK 类型生成分叉、`commands_hash`/`rejections` hash 不稳定。不同实现可能把同一失败映射为不同 code + debug_detail，从而造成 replay mismatch。
- **修复建议**: 全文统一使用 Registry §2.6 的 condition → canonical RejectionReason → debug_detail 映射。将 `SourceEmpty` 映射到 `InsufficientResource` + debug_detail，将 `TileOccupied` 映射到 `PositionOccupied`，将 `AlreadyFullHealth` 映射到 `CooldownActive` 或新增经 IDL 注册的 canonical code，将 `TargetFull` 映射到 `InsufficientResource`/`PositionOccupied` 中的一个明确选项。若确实需要 `MainActionQuotaExceeded`、`TickValidationFailed`、`output_truncated`，必须先进入 IDL/Registry，而不是在规范正文临时发明。

## High (强烈建议修复) (H1..Hn)

### H1 — Future 文档仍包含“候选/待定/需冻结”，不符合“设计即目标状态”评审原则

- **Severity**: High
- **文件引用**:
  - `/data/swarm/docs/specs/future/T2-incremental-snapshot.md:50` — 增量截断排序写为“候选方案”。
  - `/data/swarm/docs/specs/future/T2-incremental-snapshot.md:56` — 写“推荐方案 A”，但未形成唯一合同。
  - `/data/swarm/docs/specs/future/T2-incremental-snapshot.md:73` — keyframe 间隔写“最终值需在 Tier 2 实现前通过基准测试确定”。
  - `/data/swarm/docs/specs/future/T2-incremental-snapshot.md:75` — 明确存在“待定项”。
  - `/data/swarm/docs/specs/future/T2-incremental-snapshot.md:81` — FDB 增量提交整合仍待对齐。
  - `/data/swarm/docs/specs/future/T3-shard-protocol.md:14` — shard assignment 仍是 `jump_hash` 或 `ring_hash` 候选。
  - `/data/swarm/docs/specs/future/T3-shard-protocol.md:73` — 明确存在“待定项”。
  - `/data/swarm/docs/specs/future/T3-shard-protocol.md:80` — 动态重平衡 tick 暂停/降级语义未定义。
  - `/data/swarm/docs/specs/future/T3-shard-protocol.md:81` — 跨分片 replay/anti-cheat 审计链未定义。
- **问题描述**: 评审任务明确要求“设计即目标状态”，但 T2/T3 仍是 RFC/候选方案风格，多个会影响确定性和性能合同的关键项没有唯一语义。
- **影响分析**: 增量快照截断排序、keyframe 间隔、分片 hash、动态重平衡、跨分片审计链都直接影响 byte-identical replay、容量 SLO 和故障恢复。若文档保留候选项，实现者无法写出唯一 CI fixture，也无法生成稳定 manifest hash。
- **修复建议**: 将 T2/T3 改写为目标状态规范：选择唯一截断排序、唯一 keyframe policy、唯一 shard assignment 算法、唯一重平衡协议和全局审计链合并规则。需要用户裁决的 D-item 应显式标记为 D-item 并等待裁决，不应以“候选/待定”留在目标规范正文。

### H2 — 跨分片 Combat 的 1 tick 最终一致语义与核心 tick-by-tick replay 合同边界不清

- **Severity**: High
- **文件引用**:
  - `/data/swarm/docs/specs/future/T3-shard-protocol.md:39` — 跨分片 combat 使用两阶段协议。
  - `/data/swarm/docs/specs/future/T3-shard-protocol.md:50` — attacker 的 Energy/fuel 在 Phase 1 已扣除且不可逆。
  - `/data/swarm/docs/specs/future/T3-shard-protocol.md:51` — target HP 在 Phase 2 结算。
  - `/data/swarm/docs/specs/future/T3-shard-protocol.md:60` — 跨分片 RangedAttack 是最终一致，延迟 1 tick。
  - `/data/swarm/docs/specs/future/T3-shard-protocol.md:63` — 冲突排序键为 `(tick, shard_priority, entity_id)`。
  - `/data/swarm/docs/specs/future/T3-shard-protocol.md:78` — Phase 1→Phase 2 tick 边界仍需验证。
  - `/data/swarm/docs/specs/future/T3-shard-protocol.md:81` — 跨分片 replay/anti-cheat 审计链仍未定义。
  - `/data/swarm/docs/specs/core/01-tick-protocol.md:744` — 核心确定性合同要求给定 N-1 状态 + N RawCommand + seed + mods 得到 recorded_state。
  - `/data/swarm/docs/specs/core/01-tick-protocol.md:876` — TickCommitRecord 记录 `seed_epoch` 和活跃玩家集快照以支持回放。
- **问题描述**: T3 允许 attacker 侧在 tick N 扣费、target 侧在 tick N+1 结算，但未定义跨分片 intent 是否进入 tick N 或 tick N+1 的全局 TickCommitRecord，也未定义 `shard_priority` 的来源、版本化和 manifest hash。
- **影响分析**: 这会让 replay verifier 在分片模式下无法决定 tick N recorded_state 是否应包含 target HP 变化。攻击者资源消耗与目标伤害跨 tick 分离也会影响 refund、death_mark、spawning_grace、status_advance 等核心系统顺序。若多个 target_shard 同时返回，缺少全局 intent log 会导致审计链无法 byte-identical 合并。
- **修复建议**: 为跨分片协议定义全局 `CrossShardIntentLog`：intent 产生 tick、settlement tick、source shard、target shard、`shard_priority` 派生算法、timeout/reject 语义、refund 语义、hash chain 合并方式。明确跨分片 combat 是“tick N intent + tick N+1 effect”的 replay-critical 状态机，并把 shard topology / shard_priority / assignment algorithm 纳入 `system_manifest_hash` 或独立 `shard_manifest_hash`。

### H3 — 性能容量合同对 1000 玩家 hard cap 的证明与 benchmark-gated 状态冲突

- **Severity**: High
- **文件引用**:
  - `/data/swarm/docs/design/engine.md:288` — 声称全部指标是 deadline-driven 硬性能合同且 CI 回归测试。
  - `/data/swarm/docs/design/engine.md:306` — Active players 写 target 500 / hard cap 1000。
  - `/data/swarm/docs/design/engine.md:393` — 开始推导 1000 active players hard cap。
  - `/data/swarm/docs/design/engine.md:398` — 假设 1000 workers / 40 cores 得到约 125ms wall-clock。
  - `/data/swarm/docs/design/engine.md:403` — 结论为 1000 hard cap 可保证 tick 完成。
  - `/data/swarm/docs/specs/reference/api-registry.md:592` — 硬件基线 target 500。
  - `/data/swarm/docs/specs/reference/api-registry.md:593` — hard cap 1000 明确标注 benchmark-gated（未验证）。
  - `/data/swarm/docs/specs/core/05-persistence-contract.md:391` — Synthetic Benchmark 要求开始。
  - `/data/swarm/docs/specs/core/05-persistence-contract.md:403` — FDB room-partition commit 1000 players p99 < 500ms gate。
  - `/data/swarm/docs/specs/core/04-wasm-sandbox.md:260` — 每个 sandbox cgroup `cpu.max = 250000 3000000`。
- **问题描述**: engine.md 将 1000 players 描述为可保证 tick 完成的 hard cap，而 API Registry 将其标为未验证 benchmark-gated。engine.md 的推导还假设 1000 workers 与 40 cores，但默认 worker_pool_max 是 256，sandbox cgroup 还对每 worker 设置了固定 CPU quota，aggregate CPU admission 未显式纳入 cgroup 总量约束。
- **影响分析**: 性能合同是实现和运维 admission 的依据。若“hard cap”既是硬保证又是 benchmark-gated，运营端无法知道何时应拒绝新玩家。若 worker 数、CPU cores、cgroup quota、fuel rate 之间没有统一方程，fuel admission 可能过度乐观，导致 COLLECT p99 挤压 EXECUTE/FDB commit，tick overrun 进入降级。
- **修复建议**: 将 capacity 文档改成单一 measured admission 合同：1000 players 在 benchmark 通过前不得称为 hard guarantee；`worker_pool_max`、`worker_pool_hard_cap`、CPU cores、per-worker cgroup quota、aggregate fuel budget 必须进入同一公式。若 Registry 是权威容量源，engine.md 只引用其 benchmark-gated 状态，不再重复推导出强结论。

## Medium (建议关注) (M1..Mn)

### M1 — Snapshot Contract 中仍出现浮点调试字段和百分比公式，容易污染“禁止 float”心智模型

- **Severity**: Medium
- **文件引用**:
  - `/data/swarm/docs/specs/core/09-snapshot-contract.md:239` — `base_success = 60%`。
  - `/data/swarm/docs/specs/core/09-snapshot-contract.md:241` — `attacker_extra_parts × 5%`。
  - `/data/swarm/docs/specs/core/09-snapshot-contract.md:243` — `clamp(..., 10%, 85%)`。
  - `/data/swarm/docs/specs/core/09-snapshot-contract.md:352` — debug 示例返回 `distance: 12.53`。
  - `/data/swarm/docs/specs/core/09-snapshot-contract.md:353` — debug 示例返回 `required_range: 5.0`。
  - `/data/swarm/docs/specs/core/09-snapshot-contract.md:355` — debug 示例返回 `action_range: 3.0`。
  - `/data/swarm/docs/specs/reference/api-registry.md:20` — Fixed-Point Type Registry 开始。
  - `/data/swarm/docs/specs/reference/api-registry.md:22` — 声明所有 `f64` 字段已替换为 fixed-point integer。
  - `/data/swarm/docs/specs/core/01-tick-protocol.md:751` — 禁止任何浮点类型出现在游戏状态中，JSON 定点数使用整数表示。
- **问题描述**: Snapshot Contract 的 intercept 成功率公式和 training debug JSON 示例仍使用百分号/小数。虽然可能只是展示格式，但它与固定点整数全局规范冲突。
- **影响分析**: Debug payload、training mode 和审计事件常被 SDK/工具照抄。如果示例中出现小数，SDK 可能生成 `f64` 字段，进而污染 replay fixtures 或玩家 bot 决策。百分比公式也应明确为 basis points，避免实现者用浮点概率计算。
- **修复建议**: 将所有概率改为 bp：`base_success_bp = 6000`、`part_bonus_bp = min(extra_parts * 500, 2500)`、`escort_penalty_bp = 3000`、`clamp(..., 1000, 8500)`。Debug 示例改为 `distance_milli: 12530`、`required_range_milli: 5000`、`action_range_milli: 3000`。

### M2 — Snapshot truncation 权威引用章节号漂移，增加实现者误读风险

- **Severity**: Medium
- **文件引用**:
  - `/data/swarm/docs/design/engine.md:433` — 声称权威截断合同见 Snapshot Contract §1。
  - `/data/swarm/docs/specs/core/01-tick-protocol.md:158` — 声称超限截断策略见 Snapshot Contract §4。
  - `/data/swarm/docs/specs/core/09-snapshot-contract.md:19` — 实际 `Snapshot Truncation Contract` 在 §1。
  - `/data/swarm/docs/specs/core/09-snapshot-contract.md:284` — §4 实际是 Safe Hint Ladder。
- **问题描述**: tick-protocol 引用 Snapshot Contract §4，但实际截断权威在 §1，§4 是错误提示阶梯。
- **影响分析**: 这不是算法缺陷，但在“唯一权威源”模式下，错链会让实现者读错章节，尤其 snapshot truncation 与 hint ladder 都涉及可见性和信息泄露，混淆会导致实现偏差。
- **修复建议**: 将 `/data/swarm/docs/specs/core/01-tick-protocol.md:158` 的引用改为 Snapshot Contract §1，并在 Snapshot Contract 顶部提供稳定锚点名而非章节号。

### M3 — S15 HitPoints 唯一写入者声明与 S10 regen 例外表述不够机器可检验

- **Severity**: Medium
- **文件引用**:
  - `/data/swarm/docs/specs/core/06-phase2b-system-manifest.md:209` — S15 damage_application 标题声明 UNIQUE HitPoints writer。
  - `/data/swarm/docs/specs/core/06-phase2b-system-manifest.md:211` — 又写 S10 regen 除外。
  - `/data/swarm/docs/specs/core/06-phase2b-system-manifest.md:216` — HitPoints 写入契约再次写 S15 是除 S10 外唯一 writer。
  - `/data/swarm/docs/specs/core/06-phase2b-system-manifest.md:402` — R/W 矩阵中 S10 对 HitPoints 是 W。
  - `/data/swarm/docs/specs/core/06-phase2b-system-manifest.md:407` — R/W 矩阵中 S15 对 HitPoints 是 W。
  - `/data/swarm/docs/specs/core/06-phase2b-system-manifest.md:463` — CI 要求迭代确定性验证。
- **问题描述**: 文档用“唯一写入者”描述 S15，但又允许 S10 写 HitPoints。语义上可接受（S10 在 S15 前串行），但“Unique Writer”术语对 CI 静态分析不够精确。
- **影响分析**: 如果 CI 机械验证“仅 S15 写 HitPoints”，会误报；如果放宽为“S10/S15 都可写”，又可能让新增系统钻空子。该点不一定破坏设计，但会降低 R/W contract 可实施性。
- **修复建议**: 将术语改为 `HitPoints writer set = {S10, S15}`，并声明 S10 只允许 monotonic capped regen、S15 是 damage/heal reducer 唯一 writer；CI gate 应验证 writer set 精确等于这两个 system，且 S10 必须在 S15 前并带 `Without<DeathMark>`。

## Low / Nits (可选改进) (L1..Ln)

### L1 — 文档中“Phase/MVP/Tier”术语与 Clean Slate 目标状态叙述混杂

- **Severity**: Low
- **文件引用**:
  - `/data/swarm/docs/design/engine.md:170` — 表格写 `目标 MVP = 500 活跃玩家`。
  - `/data/swarm/docs/specs/core/09-snapshot-contract.md:181` — `MVP Economy Boundaries` 标题。
  - `/data/swarm/docs/specs/future/T2-incremental-snapshot.md:1` — `Tier 2 增量快照协议`。
  - `/data/swarm/docs/specs/future/T3-shard-protocol.md:1` — `Tier 3 分片协议`。
- **问题描述**: 这些术语可能只是容量层级标签，但与本轮“设计即目标状态，不区分 Phase/MVP/迭代”的评审原则不完全一致。
- **影响分析**: 容量层级可以保留，但 MVP/Phase 词汇容易被误读为临时设计或路线图，而非目标状态规范。
- **修复建议**: 将 `MVP` 改为 `Core Profile` 或 `Baseline Profile`，将 Tier 文档明确写成“目标容量 profile”，不是实现阶段路线图。

## Strengths (设计亮点)

- **确定性核心合同深度高**: `/data/swarm/docs/specs/core/01-tick-protocol.md:862` 将 Determinism Contract 独立成权威章节，覆盖排序、部署时序、输出状态、TickCommitRecord、RNG、ECS 调度和 WASM output 截断。
- **ECS 调度 manifest 明确**: `/data/swarm/docs/specs/core/06-phase2b-system-manifest.md:20` 给出 31 systems 全链路，`/data/swarm/docs/specs/core/06-phase2b-system-manifest.md:387` 给出 R/W 矩阵，`/data/swarm/docs/specs/core/06-phase2b-system-manifest.md:457` 给出 CI 验证项，整体可实施性强。
- **Status Effects 并行设计合理**: `/data/swarm/docs/specs/core/06-phase2b-system-manifest.md:222` 将状态效果拆成 typed buffer production，`/data/swarm/docs/specs/core/06-phase2b-system-manifest.md:239` 由 S22 串行唯一推进，避免并行写 StatusState 的常见非确定性陷阱。
- **Worker Pool 与串行瓶颈分离清晰**: `/data/swarm/docs/design/engine.md:342` 到 `/data/swarm/docs/design/engine.md:373` 明确 Phase 1 worker pool 水平扩展，真正瓶颈在 Phase 2 串行执行与 per-player WASM 平均执行时间 × 并行度，方向正确。
- **WASM sandbox DoS 防线完整**: `/data/swarm/docs/specs/core/04-wasm-sandbox.md:41` 定义 long-lived worker + per-tick Store reset，`/data/swarm/docs/specs/core/04-wasm-sandbox.md:67` 开始列 Wasmtime 配置，`/data/swarm/docs/specs/core/04-wasm-sandbox.md:361` 给出 OS 边界加固 checklist，fuel、epoch、cgroup、seccomp 多层防护合理。
- **Shadow Write + Atomic Publish 修复了 room-partition 原子性风险**: `/data/swarm/docs/specs/core/01-tick-protocol.md:393` 到 `/data/swarm/docs/specs/core/01-tick-protocol.md:435` 明确 staging 不可见、GlobalTickCommit 是唯一 publish 点，能避免 per-room partial commit 破坏全局 replay。
- **Snapshot truncation 的确定性排序设计良好**: `/data/swarm/docs/specs/core/09-snapshot-contract.md:52` 到 `/data/swarm/docs/specs/core/09-snapshot-contract.md:92` 定义距离桶、entity_id 字典序、critical entity 不可截断，符合 deterministic perception 的要求。
- **Pathfinding cache determinism 处理到位**: `/data/swarm/docs/specs/core/09-snapshot-contract.md:459` 到 `/data/swarm/docs/specs/core/09-snapshot-contract.md:466` 明确 cache hit/miss 不改变输出且 cache hit 仍消耗相同 fuel，这是性能优化不污染 replay 的正确做法。

## CrossCheck — 需要跨方向检查

- CX1: `host_get_random` / `swarm_get_random` 命名与 SDK 暴露不一致 → 建议 API/SDK 方向检查 TypeScript/Rust SDK codegen 是否生成同一 host function 名称、错误码和调用预算。
- CX2: TickCommitRecord 字段集合冲突涉及 FDB schema 与 object-store 降级语义 → 建议 Persistence/Storage 方向检查 FDB row schema、hash chain、WAL fallback 是否只使用同一 replay-critical 结构。
- CX3: 未注册 RejectionReason 会影响 wire enum 和玩家提示阶梯 → 建议 API/UX 方向检查 IDL、Registry、Safe Hint Ladder 是否由同一错误码表生成。
- CX4: T3 跨分片 combat 的 attacker 扣费与 target 延迟受伤可能影响竞技公平 → 建议 Gameplay/Balance 方向检查 1 tick 延迟是否会改变 RangedAttack、death_mark、spawning_grace 和特殊攻击反制窗口。
- CX5: Sandbox seccomp 允许 `nanosleep` 但禁止 clock/random，且 relaxed 模式可允许 `clock_gettime` → 建议 Security 方向检查 Wasmtime/host runtime 是否可通过 timing side channel 或 syscall fallback 泄露环境状态。
- CX6: 1000-player capacity hard cap 仍 benchmark-gated → 建议 Ops/SRE 方向检查实际硬件基线、cgroup aggregate quota、worker_pool_max 默认值、FDB p99 benchmark 是否形成可执行 admission runbook。
