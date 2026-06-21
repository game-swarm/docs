# R33 Determinism & Performance Review — DeepSeek V4 Pro

## Verdict
**REQUEST_MAJOR_CHANGES** — 2 Critical issues require resolution before approval. The determinism contract is robust and well-specified across all core documents, but a timing budget inconsistency between tick-protocol diagram and unified budget table would cause implementation divergence, and T2 incremental snapshot lacks hash chain verification design. 3 High items also need attention.

---

## Critical (必须修复，否则 BLOCK)

### B1: EXECUTE Phase Timing Budget Inconsistency — Cross-Document Conflict

**Files**: 
- `specs/core/01-tick-protocol.md` §1.4 状态机图: "硬超时天花板: 500ms (budget target 见 design/engine.md §3.4.1: World ≤400ms, Arena ≤50ms)"
- `specs/core/01-tick-protocol.md` §8.2 统一预算表: "EXECUTE | wall-clock total | tick_soft_deadline_ms 内完成 | 软截止前必须完成（EXECUTE 不单独超时，由 COLLECT+EXECUTE 总预算控制）"
- `design/engine.md` §3.4.1: "EXECUTE (2a+2b) ≤400ms"

**问题描述**: 同一文档内 §1.4 和 §8.2 对 EXECUTE 阶段的超时模型给出不一致定义。§1.4 指明 EXECUTE 有独立的 500ms 硬天花板，但 §8.2 的权威统一预算表明确声明 "EXECUTE 不单独超时"，其 wall-clock 预算引用 `tick_soft_deadline_ms`（2500ms，即 COLLECT+EXECUTE 总预算）。这导致实现者无法确定 EXECUTE 是否应该： (a) 在 500ms 时强制 abort（§1.4），还是 (b) 仅在总 COLLECT+EXECUTE 超过 2500ms/4000ms 时触发软/硬截止（§8.2）。

**影响分析**: 
- 若实现遵循 §1.4 的 500ms 硬天花板，则 Phase 2a+2b 在 500ms 被截断后世界状态不完整，tick 必须 abandon → 损失整个 COLLECT 阶段的 fuel 和 work
- 若实现遵循 §8.2 的统一模型，则 EXECUTE 可弹性使用 COLLECT 未消耗的预算，但无独立保护——Phase 2b 的 combat/special_attack/status 链若陷入死循环将拖垮整个 tick
- 两个合法解读导致完全不同的运行时行为和 failure mode

**修复建议**: 
1. 以 §8.2 统一预算表为权威（已标记为"统一模型，消除跨文档分散定义"），将 §1.4 状态机图中的 "硬超时天花板: 500ms" 改为引用 §8.2 的语义：EXECUTE 在 `tick_hard_deadline_ms`(4000ms) 约束下运行，同时受 `tick_soft_deadline_ms`(2500ms) 告警监控
2. 在 §8.2 中增加一行：EXECUTE 独立 watchdog（防止死循环）：若 Phase 2b 单个 system 执行超过 100ms → abort tick。这填补了统一模型缺失的 Phase 2b hang 保护
3. 保持 engine.md §3.4.1 的 ≤400ms 作为 **性能目标**（非硬天花板），与 §8.2 统一

---

### B2: T2 Incremental Snapshot 缺少 Hash Chain 验证设计

**File**: `specs/future/T2-incremental-snapshot.md`

**问题描述**: T2 增量快照协议定义了 `base_snapshot_hash` 字段（"上一 tick 快照的 hash"）但完全没有设计增量链的验证机制。
- §2.3 "增量重建": `tick N snapshot = apply(tick N-1 snapshot, tick N modification_set)` — 未指定如何验证 `tick N-1 snapshot` 的完整性
- 若 keyframe 间隔为 100 tick，从 keyframe 重建到当前 tick 需要依次 apply 100 个 modification_set，任意一个损坏/丢失将导致重建失败且无法定位损坏点
- 与 `05-persistence-contract.md` 的 hash chain 体系（TickCommitRecord → manifest_hash chain）完全脱节——T2 未引用现有 hash chain infrastructure

**影响分析**: 在 T2 scale（≤5000 drone, ≤500 rooms）下，keyframe 重建是 replay/恢复的关键路径。缺乏 hash chain 验证意味着：
- 无法检测 modification_set 的静默损坏
- 无法定位损坏发生的 tick
- 无法从中间 keyframe 部分恢复（必须回到上一个 keyframe 全量重建）
- 与 persistence contract 的 `terminal_state` 分级（verified/audit_gap/unreplayable/reconstructable）不兼容

**修复建议**:
1. 在 modification_set 中增加 `prev_snapshot_hash`（引用上一 tick 快照）和 `self_hash = Blake3(modification_set || prev_snapshot_hash)`
2. 在 keyframe 中嵌入 `chain_head_hash`（从上一个 keyframe 到当前 keyframe 的 modification_set 链 hash）
3. 定义增量重建验证流程：从 keyframe 出发 → 对每个 modification_set 验证 `self_hash` → 验证 `prev_snapshot_hash` 链完整 → 产出当前 snapshot
4. 引用 `05-persistence-contract.md` 的 `terminal_state` 分级——将 modification_set 缺失/损坏映射到合适的 terminal_state

---

## High (强烈建议修复)

### H1: Capacity Admission 非对称 Hysteresis 可能导致永久欠准入

**File**: `specs/core/09-snapshot-contract.md` §7.2

**问题描述**: Admission decision 的 hysteresis 规则是非对称的：
- 降级：`measured_p95 > SLO` → 立即减少 `admitted_players` by 10%（10 tick cooldown before re-increase）
- 恢复：`measured_p95 < 50% of SLO for 30+ consecutive ticks` → 增加 5%

这意味着一次短暂的 burst（如 mass spawn event）触发降级后，需要 **30 个连续 tick（90 秒）** 的极低负载才能恢复 5% 的容量。在 World 模式下（3s tick, 500 players），`30 ticks × 5% increments` 需要 `30 × 20 = 600 ticks (30 分钟)` 才能从 90% 恢复到 100%。如果 burst 每几分钟发生一次，系统将永久运行在降级容量下。

**影响分析**: 实际容量可能长期低于 target 500——运营商扩容硬件也无法受益，因为 admission 算法限制的是逻辑准入而非物理容量。p95 的统计滞后进一步加长恢复时间。

**修复建议**:
1. 恢复条件从 30 tick 降低到 10 tick（与降级 cooldown 对称）
2. 或增加快速恢复路径：若 `measured_p95 < 25% of SLO for 5+ consecutive ticks` → 立即恢复到 `min(previous_level + 20%, target)` 
3. 增加 manual override admin API：`swarm_admin_set_admission_capacity` 允许运维在 burst 后手动恢复

---

### H2: Phase 2a Inline Command Loop 延迟预算在 100k commands 下无余量

**Files**: `design/engine.md` §3.4.1, `specs/core/05-persistence-contract.md` §8.3

**问题描述**: 
- engine.md §3.4.1: EXECUTE budget target = 400ms (World)
- 05-persistence-contract.md §8.3 Synthetic Benchmark: "Command apply loop: 100k commands/tick p99 < 100ms"
- Hard cap scenario: 1000 players × 100 commands = 100k commands max per tick
- Per-command budget at 100ms = 1μs/command

1μs per command 在 Rust+Bevy 中是**理论上可达成**的，但单个 command inline apply 包括：
- Bevy World query（entity lookup, component read）
- Validation logic（ownership check, range check, resource check, fatigue check, body part check）
- Mutation（position write, hits write, resource deduction, event emission）

保守估计每个 command 5-50μs → 100k commands = 500ms-5000ms，远超 100ms p99 benchmark。即使 benchmark 达标，生产环境中 Phase 2a inline apply 与 Phase 2b ECS systems（S07-S29, 25 systems）共享 EXECUTE 总预算，实际可用时间更少。

**影响分析**: 当 active_players 接近 hard cap 1000 时，Phase 2a inline apply 极可能成为 tick 延迟的主要贡献者。这反过来触发 B1 中的超时问题——500ms 硬天花板（如果存在）或 4000ms 总截止。

**修复建议**:
1. 重新评估 100k commands p99 < 100ms benchmark 是否现实——若不可行，升级 benchmark 目标或降低 MAX_COMMANDS_PER_PLAYER
2. 为 Phase 2a inline apply 增加 per-command 微预算（如 10μs hard ceiling per command）作为防御性设计——超时 command 拒绝但继续处理后续
3. 在 engine.md §3.4.1 中明确 Phase 2a vs Phase 2b 的延迟分拆（当前只有 EXECUTE 总预算）

---

### H3: T3 跨分片 Combat 的 Tick 同步未定义

**File**: `specs/future/T3-shard-protocol.md` §4

**问题描述**: T3 跨分片 combat 两阶段协议依赖跨分片 tick 同步：
- Phase 1: attacker_shard → target_shard: AttackIntent（在同一逻辑 tick 内）
- Phase 2: target_shard 结算 → attacker_shard: AttackResult
- 确定性保证: "逻辑时钟 `(tick, shard_order, entity_id)`"

但未定义以下基础同步问题：
1. 各分片的 tick counter 如何保持同步？分片独立推进后 tick 可能漂移
2. 若 target_shard 的 tick N 尚未完成但 attacker_shard 已发送 tick N 的 AttackIntent——如何处理？
3. 跨分片 RangedAttack 的 "1 tick 延迟" 是否意味着 `attacker.tick_N` 的 intent 在 `target.tick_{N+1}` 结算——这要求 target 永远领先或落后 1 tick，但未指定方向

**影响分析**: 这是 `specs/future/` 文档，不阻塞当前实现，但作为未来架构的 Critical 问题需要在进入 T3 实现前解决。当前标记为 "待定项"（TBD）是诚实的，但缺少问题陈述。

**修复建议**: 在 T3-shard-protocol.md 的待定项中增加一条："跨分片 tick 同步协议：定义分片间 tick counter 对齐机制（Barrier synchronization vs 异步消息传递）、AttackIntent 的 tick 归属规则、跨 tick 延迟的方向性"

---

## Medium (建议关注)

### M1: WASM Module Cache 全量失效风险

**Files**: `specs/core/04-wasm-sandbox.md` §7, `specs/reference/api-registry.md` §4

**问题描述**: Module cache key 包含 `wasmtime_build_commit`——Wasmtime 版本升级会使**所有**已缓存模块失效。在 500 active players × 1-5 modules/player 的场景下，版本升级后下一个 tick 的 COLLECT 阶段需重新编译数百个 WASM 模块。编译预算为 30s/module × 并发5 = 理论每 30s 产出 5 个编译 = 500 modules 需要 ~50 分钟全量重建，tick 在此期间将大量超时。

**影响分析**: Wasmtime CVE 修复（安全 SLA ≤72h for High）触发版本升级 → 大规模模块缓存失效 → tick timeout storm → 引擎降级。当前设计缺少 warm-up 策略。

**修复建议**:
1. 增加异步 pre-warm 机制：版本升级后，引擎在后台逐步重编译模块（非 tick 路径），tick 期间使用旧缓存直到新缓存 ready → 原子切换
2. 或保留旧版本 Wasmtime engine 并行运行直到新缓存覆盖率 > 80%
3. 在 `04-wasm-sandbox.md` §7 增加 "Wasmtime 版本升级迁移策略" 小节

---

### M2: Pathfinding Cache Determinism Contract 浪费缓存收益

**File**: `specs/core/09-snapshot-contract.md` §7.3

**问题描述**: Pathfinding determinism contract 规定 "cache hit 时仍消耗相同 fuel（确定性必要）"。这意味着即使路径从缓存获取（0 计算成本），玩家仍被扣减相同的 fuel。这消除了 pathfinding cache 对玩家体验的全部收益——玩家无法通过缓存获益，引擎也无法通过缓存降低计算负载（因为 fuel 照扣但实际 CPU 空闲）。

**影响分析**: 在 player-facing fairness 层面，相同 fuel 扣费是正确的（防止缓存命中与否影响战术公平性）。但从引擎资源利用率角度看，cache hit 时引擎实际不消耗 A* 计算资源但 tick budget 中的 pathfinding 预算被标记为"已消耗"。这可能导致 budget accounting 不准确——`pathfinding explored_nodes` 全局配额应在 cache hit 时不消耗。

**修复建议**: 区分 **fuel accounting**（对玩家扣费）和 **budget accounting**（对引擎资源追踪）：
- Fuel: cache hit 仍扣相同 fuel → 玩家公平（保持）
- Budget: cache hit 不消耗 `explored_nodes` 全局配额 → 引擎可将节省的 CPU 时间分配给其他玩家
- 明确文档："Pathfinding cache determinism contract applies to fuel accounting only; budget accounting tracks actual CPU consumption separately"

---

### M3: Status Buffer Production 并行集的 Cache Line 竞争

**File**: `specs/core/06-phase2b-system-manifest.md` §S16-S22b, §4 R/W Matrix

**问题描述**: Parallel Set B（S16-S22b）的 8 个 system 全部读取 StatusState components（R/W matrix 中标记为 R）。虽然各 system 写入互不重叠的 typed buffer（无 write conflict），但它们并发读取同一 StatusState 可能导致：
- 若多个 entity 的 StatusState 在同一 cache line（64B on x86），S16-S22b 的并发读会触发 false sharing
- 对于 5000 active drones 且 10-20% 携带 active status → 500-1000 个 StatusState 实体，8 个并行 reader 的 cache line 竞争可能显著

**影响分析**: 非正确性问题，纯性能优化。在当前 scale（500 players, target 5000 drones）下影响可控，但在 T2 scale（5000 drones, 500 rooms）下可能成为瓶颈。

**修复建议**: 在 manifest §4 中加注：StatusState 内存布局应考虑 cache line 对齐（`#[repr(align(64))]` 或 per-entity StatusState 使用独立 allocation），减少并行 reader 的 false sharing。非 blocking——可在实现阶段通过 profiling 确认后再优化。

---

### M4: Snapshot Truncation "关键实体不可截断" 的完整性边界

**File**: `specs/core/09-snapshot-contract.md` §1.4

**问题描述**: 关键实体列表包含 "己方所有 drone" 和 "正在攻击自身的实体"。在 drone cap 500（per room）的极端情况下，如果玩家拥有 500 drones 且遭到 500 drones 攻击，关键实体 = 1000 entities。每个 entity snapshot 估算 ~256 bytes → 256KB，恰好等于 snapshot cap。这意味着：
- 关键实体本身就已占满 256KB
- 所有其他实体（resources, structures, neutral entities）必定被截断
- 截断后的 snapshot 仅含 key entities → 玩家收到 `truncated=true` 但实际无可用信息

**影响分析**: 边界情况——在 drone-dense 战斗场景中，关键实体保护策略可能导致 snapshot 退化至仅含自身军队，失去所有 situational awareness。虽然这正确触发了 `truncated=true` 标记，但极端截断的 game design 影响未讨论。

**修复建议**: 在 §1.4 中增加 "关键实体总大小约束"——若关键实体集合序列化后 > 200KB（预留 56KB for non-critical），按距离桶优先级从最远己方 drone 开始移除（保留最近的 N 个己方 drone + 所有攻击者 + self + Controller）。这是 design decision 层面问题，标记为 D-item 供用户裁决。

---

## Low / Nits (可选改进)

### L1: "Parallel Set C" 命名误导

**File**: `specs/core/06-phase2b-system-manifest.md` §1 Schedule

**问题描述**: 调度图中 "Parallel Set C: World Maintenance" 实际上**仅包含 S24（decay_system）**，且明确标记为 "serial within C"。命名为 "Parallel Set C" 对一个单系统串行 set 具有误导性。

**修复建议**: 将 "Parallel Set C" 改为 "Serial: World Maintenance"，或直接将 S24 合并入 Serial Spine（因其本身就是串行的）。

---

### L2: T2 增量截断方案推荐过早

**File**: `specs/future/T2-incremental-snapshot.md` §4

**问题描述**: 增量截断方案 A vs B 的推荐（"推荐方案 A"）在缺乏 benchmark 数据的情况下做出。T2 整体处于 "待定项" 状态——所有关键参数（CoW page size, keyframe interval, FDB 整合）均为候选值，不应过早确定截断方案。

**修复建议**: 将 "推荐方案 A" 改为 "候选方案 A（倾向）"，明确最终选择需 Tier 2 实现前 benchmark 确认。

---

### L3: FDB Commit Budget 与 Benchmark 数值不对齐

**Files**: `design/engine.md` §3.4.1 vs `specs/core/05-persistence-contract.md` §8.3

**问题描述**: 
- engine.md §3.4.1: "COMMIT (FDB) ≤50ms (p99)"
- 05-persistence-contract.md §8.3 Benchmark: "FDB single-tx commit: 500 active players, p99 < 200ms"

Benchmark 目标（200ms）是 Budget 目标（50ms）的 4 倍。实际 benchmark 可能更保守（更难达成），但数值差异暗示两者测量不同事物（budget = FDB 事务本身，benchmark = 含序列化的端到端提交）。

**修复建议**: 统一术语——在 engine.md 中标注 COMMIT budget 的测量范围（是否含序列化/checksum 计算），与 benchmark 定义对齐。

---

## Strengths (设计亮点)

1. **确定性合同全面且一致**: 
   - `f64` 全面禁止，定点整数（basis points ×10000）覆盖所有数值计算
   - `HashMap` 禁止，`BTreeMap`/`IndexMap` 保证迭代顺序
   - `canonical_json` 采用 RFC 8785 JCS 国际标准，非自创格式
   - Blake3 覆盖哈希+PRNG，单原语简化审计面

2. **RNG 种子管理层次清晰**:
   - namespace 隔离（combat/loot/npc_spawn/event）+ domain separation
   - Arena commit-reveal / World seed-bump 双模式适应不同信任模型
   - 种子轮换 + 泄露检测 + operator 应急工具链完整
   - Per-entity private stream 使用 `entity_id.to_le_bytes()` 消除排序依赖

3. **ECS 调度设计精良**:
   - 31-system manifest 为唯一权威源，消除跨文档调度冲突
   - S22 为唯一 StatusState writer（Unique Writer Contract），消除并行写入歧义
   - RoomCap 中间态保护（S07-S08 区间禁止 reader）
   - R/W Matrix 覆盖全部 31 systems，CI 可静态验证

4. **Worker pool vs Phase 2 sandbox 分离清晰**: engine.md §3.4.2 明确识别真正的扩展瓶颈——"不在 worker pool（可水平扩展），而在 Phase 2 sandbox 串行执行时间"。这是对整个系统性能特征的诚实评估。

5. **Snapshot 两阶段架构**: 全局一次性快照 + per-player 视野过滤，复杂度从 `O(P × E)` 降至 `O(E + P × 可见房间数)`——消除每玩家重复序列化开销，性能收益巨大且天然确定。

6. **容量推导透明**: 500/1000 player 容量推导包含完整数学过程（p50/p99 延迟、并行度、核心数、overhead 估算），所有假设显式声明，可被 benchmark 验证。

7. **COLLECT 跨重试缓存**: FDB commit 失败后复用 COLLECT 结果而非重新执行 WASM——防止非确定性 double-execution 和 double-fuel-charge，确定性保证不依赖"重试不触发新 WASM"。

8. **T3 逻辑时钟设计**: 跨分片 tiebreaker 使用 `(tick, shard_priority, entity_id)` 纯逻辑时钟，不依赖 FDB versionstamp 或墙钟——保证了分片世界在物理分布下的确定性可回放性。

---

## CrossCheck — 需要跨方向检查

- **CX1**: Snapshot truncation 关键实体集合在极端 drone-dense 场景下可能自身占满 256KB → 建议 **Security Reviewer** 检查：敌方通过堆叠大量 drone 迫使对手 snapshot 退化至仅含 key entities 是否构成信息 denial-of-service 攻击向量（§09-snapshot-contract.md §1.4 + engine.md §3.4.4 anti-abuse 条款）。

- **CX2**: Phase 2a TOCTOU 合同规定 "Hack 施加控制锁后原 owner 的后续命令以原始 owner 身份校验"（02-command-validation.md §3.3 规则 2）→ 建议 **Gameplay Reviewer** 验证：此规则与 Hack 的 5-stage 状态转换（stage=5 夺取 ownership）是否存在竞态——若同一 tick 内 Hack stage 从 4 推进到 5（由 S22 status_advance 处理），Phase 2a 中后续已入队命令的 owner 校验是否正确。

- **CX3**: Capacity admission model §7.2 在 `measured_p95 > SLO` 时减少 `admitted_players` by 10%，但未定义 `admitted_players` 与 `active_players` 的优先级——哪些玩家被踢出？→ 建议 **Security/Gameplay Reviewer** 检查：admission eviction 策略是否可能被滥用（如 DDoS 攻击者占满 admitted slots 迫使合法玩家被 evict）。

- **CX4**: T3 cross-shard RangedAttack 的 "1 tick delay" 语义——若 attacker 和 target 在不同 shard 且 tick counter 已漂移，"1 tick delay" 的定义歧义 → 建议 **Architecture Reviewer** 在未来 T3 设计冻结时检查跨分片 tick 同步协议的确定性边界。

- **CX5**: Rhai RuleMod 边界（01-tick-protocol.md §9.8）："所有 action 必须进入 Command Validation 单一路径" + "扩展 action 必须通过 World Action Manifest + IDL 注册 schema" → 建议 **Interface Reviewer** 验证：World Action Manifest 的动态注册机制是否与 `06-phase2b-system-manifest.md` 的静态 31-system 调度兼容——动态 action 如何在不破坏 manifest hash 确定性的前提下插入调度链。