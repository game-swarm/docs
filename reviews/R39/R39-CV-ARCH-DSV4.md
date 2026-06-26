# R39-CV-ARCH-DSV4 架构评审报告

## 评审范围

- `design/engine.md`
- `specs/core/01-tick-protocol.md`
- `specs/core/05-persistence-contract.md`

## 总体结论

DSv4 架构整体方向是可行的：Tick 生命周期、Phase 2a/2b 职责分离、Shadow Write + Atomic Publish、确定性 replay、WASM sandbox、FDB/Object Store 分层等关键边界已经具备较完整的设计闭环。相比典型“单事务写全部”或“per-room 独立提交”方案，当前版本对生产级容量、持久化原子性、回放审计和失败恢复的考虑更成熟。

但当前文档仍存在若干会影响实现一致性的合同冲突，尤其集中在 TickCommitRecord / RichTraceBlob / 对象存储 replay 语义、Shadow Write 与旧持久化流程的并存表述、性能预算“硬合同”与 benchmark gate 数值不一致、以及部分伪代码/路径引用错误。建议在进入实现冻结前修正以下问题。

## 阻塞问题（Blocker）

### B1. TickCommitRecord 与 RichTraceBlob 的 replay-critical 边界存在自相矛盾

**位置**：
- `specs/core/05-persistence-contract.md:34`
- `specs/core/05-persistence-contract.md:58`
- `specs/core/05-persistence-contract.md:214`
- `specs/core/05-persistence-contract.md:321`
- `specs/core/01-tick-protocol.md:700`

**问题**：

持久化合同前半部分明确声明 deterministic replay 仅依赖 FDB 中 TickCommitRecord 的 10 个 replay-critical 字段，对象存储中的 RichTraceBlob 非 replay-critical，缺失只产生 `audit_gap`，绝不导致 `unreplayable`。但后续章节仍描述：

- 正常 Replay 步骤从对象存储获取 `tick_trace_blob` 并反序列化 TickCommitRecord。
- RichTraceBlob hash 不匹配且前后 keyframe 不可用时可进入 `unreplayable`。
- RichTraceBlob delta chain 断裂会影响 replay verifier。
- `01-tick-protocol.md` 也描述 RichTraceBlob 缺失时 terminal_state = audit_gap，但同时保留了 TickCommitRecord 写 WAL 与对象存储关系的混杂语义。

这会导致实现者无法判断：TickCommitRecord 究竟是在 FDB 小行里，还是序列化进对象存储 blob；对象存储缺失是否可能让 deterministic replay 不可用。

**影响**：高。该冲突直接影响审计完整性、事故恢复、replay verifier 输入模型和 SRE runbook。

**建议**：

统一为一个权威模型：

1. `TickCommitRecord` replay-critical subset 永远在 FDB 同事务提交。
2. `RichTraceBlob` 只包含 debug/rich trace，不包含 replay 必需字段。
3. Object Store 缺失/损坏最多为 `audit_gap` 或 `rich_debug_unavailable`，不得导致 deterministic replay `unreplayable`。
4. `05-persistence-contract.md` §5 和 §7.2 中依赖对象存储进行 deterministic replay 的表述应删除或改写为 rich debug replay。
5. `terminal_state` 建议拆分为：`deterministic_replay_state` 与 `rich_trace_state`，避免一个枚举承载两种语义。

## 严重问题（High）

### H1. Shadow Write 模型与旧 FDB commit 序列并存，提交路径不唯一

**位置**：
- `specs/core/01-tick-protocol.md:402`
- `specs/core/01-tick-protocol.md:414`
- `specs/core/05-persistence-contract.md:131`
- `specs/core/05-persistence-contract.md:352`
- `design/engine.md:464`

**问题**：

`01-tick-protocol.md` §3.5 明确生产环境采用 Shadow Write + GlobalTickCommit，per-room staging 行不是 committed state，GlobalTickCommit 是唯一 publish 点。但 `05-persistence-contract.md` §3 仍描述较旧的 Phase B：在一个 FDB 事务内直接 `INSERT tick_head`、`UPDATE entity/resource/controller rows`，然后对象存储异步写入。

`design/engine.md` §3.4.7 又简化为 “FDB 存 head/manifest/hash/pointer，小事务推进 world head”，没有明确说明该描述是否代表 Shadow Write manifest-only publish。

**影响**：高。实现者可能实现出三种不同提交路径：单事务直接更新、per-room staging + global publish、或 head-only manifest publish。跨房间 intent、GC、rollback、hash chain 都会受影响。

**建议**：

- 将 `05-persistence-contract.md` §3 改写为两个明确 profile：
  - Dev/Test single-tx：仅限 ≤50 active players / ≤100 rooms。
  - Prod room-partition shadow-write：per-room staging + GlobalTickCommit manifest-only publish。
- 所有“UPDATE entity/resource/controller rows”的生产表述改为“write content-addressed staging payload; publish via committed manifest”。
- `design/engine.md` §3.4.7 增加一句：生产路径以 `01-tick-protocol.md` §3.5 和 `05-persistence-contract.md` §8 的 Shadow Write 为准。

### H2. 性能预算合同互相冲突，CI gate 不可执行

**位置**：
- `design/engine.md:287`
- `design/engine.md:291`
- `specs/core/01-tick-protocol.md:810`
- `specs/core/05-persistence-contract.md:392`

**问题**：

`engine.md` 声称性能合同是 “deadline-driven 硬性能合同，全部指标在 CI 中回归测试”，其中 FDB commit p99 World ≤50ms。`01-tick-protocol.md` 又将 EXECUTE 的 World ≤400ms 描述为性能目标、非硬超时。`05-persistence-contract.md` benchmark gate 则要求 FDB room-partition commit 1000 players / 200 rooms p99 <500ms，FDB single-tx 500 players p99 <200ms。

这些数值无法同时成立：如果 World COMMIT p99 硬合同是 ≤50ms，则 room-partition p99 <500ms gate 已经不满足核心合同；如果 benchmark gate 是扩展场景指标，则 engine.md 的硬合同需要按 profile 拆分。

**影响**：高。CI 无法建立统一通过标准，容量声明也无法被客观验证。

**建议**：

- 拆分 `latency SLO`、`hard deadline`、`benchmark gate` 三类指标。
- 明确 World 500 target 与 1000 hard cap 对应的 FDB commit SLO。
- 若 room-partition p99 <500ms 是现实目标，则 `engine.md` COMMIT ≤50ms 应降级为小规模/dev profile 或 head-only publish latency，而非完整 staging+publish latency。

### H3. Cross-room intent 在 staging 完成后裁决，可能与已序列化 room payload 不一致

**位置**：
- `specs/core/01-tick-protocol.md:460`
- `specs/core/01-tick-protocol.md:469`
- `specs/core/01-tick-protocol.md:485`
- `specs/core/05-persistence-contract.md:381`

**问题**：

Cross-room intent 流程写为：先对每个活跃房间写入 staging，再收集 `cross_room_intent_set`，再裁决 intent，最终结果体现在 GlobalTickCommit manifest 中。这里缺少一个关键说明：跨房间操作的成功结果如何反映回 source/target room 的 canonical payload。

如果 room staging payload 已经在 intent 裁决前 content-addressed hash 固化，则成功的跨房间移动/转账必须产生新的 room payload hash；否则 manifest 中 intent log 与 room payload state 可能不一致。若 intent 只是 manifest overlay，则读取路径必须定义“room payload + cross-room intent replay overlay”的权威合成规则。

**影响**：高。该问题会破坏 state_checksum、room_hash、replay 和实时查询的一致性。

**建议**：

明确二选一：

1. **先裁决再 staging**：Phase 2b 已在 Bevy World 内完成跨房间状态变更，随后每个 affected room 写最终 payload。
2. **intent overlay 模型**：staging 写 base payload，GlobalTickCommit manifest 包含 intent overlay；所有读取和 replay 必须按 manifest overlay 合成最终状态，并将 overlay 纳入 `state_checksum`。

建议采用方案 1，架构更简单且更符合“Bevy World 是 tick 内权威执行状态”。

## 中等问题（Medium）

### M1. COLLECT 快照深拷贝成本与 benchmark gate 数值不一致

**位置**：
- `specs/core/01-tick-protocol.md:141`
- `specs/core/01-tick-protocol.md:180`
- `specs/core/05-persistence-contract.md:392`
- `design/engine.md:291`

**问题**：

文档要求 COLLECT 开始时 deep copy Bevy World，并在 FDB commit fail 时 restore。Benchmark gate 对 50k entities snapshot clone 要求 p99 <20ms，对 restore 50k entities p99 <30ms，但另一个 gate 又写 “Rollback Bevy snapshot/restore 500 entities p99 <50ms”。这里 500 和 50k 口径明显不一致。

**建议**：统一 benchmark 规模，至少覆盖容量合同中的 `Total entities hard cap 50000`。若 50k p99 <20/30ms 不现实，应改成工程可验证的 profile 阶梯指标。

### M2. Seed 不可预测性表述与确定性归档存在张力

**位置**：
- `specs/core/01-tick-protocol.md:232`
- `specs/core/01-tick-protocol.md:270`
- `specs/core/01-tick-protocol.md:325`

**问题**：

指令排序章节称玩家无法提前知道当前 tick 排序位置，但 World 模式又说明 seed 归档在 keyframe snapshot 中，且当前状态可推导未来状态，不具备真正前向保密。文档已有解释，但“不可预测”容易被实现/产品误读为安全性质。

**建议**：将“不可预测”改为“对普通玩家 API 不公开；若 seed 泄露则可预测”，避免安全承诺过强。

### M3. TickCommitRecord 字段清单跨文档不一致

**位置**：
- `design/engine.md:272`
- `specs/core/05-persistence-contract.md:34`
- `specs/core/05-persistence-contract.md:293`

**问题**：

`engine.md` 的 `TickInputEnvelope` 包含 `module_hash`、`wasmtime_version`、`fuel_schedule_version`、`deploy_events`、`rollback_events`、`admin_events`、`terminal_state` 等字段；`05-persistence-contract.md` §2.1 规定 10 个 replay-critical 字段；§7.1 又给出扩展 TickCommitRecord。三者未明确哪些是 envelope、哪些是 FDB replay-critical、哪些是 rich/debug 或 derived 字段。

**建议**：建立一张统一字段矩阵：字段名、存储位置、是否 replay-critical、是否 hash-chain 输入、缺失后的 terminal state、生产者/消费者。

## 轻微问题（Low）

### L1. 文档引用路径存在错误或不稳定

**位置**：
- `specs/core/01-tick-protocol.md:390`
- `specs/core/01-tick-protocol.md:993`
- `specs/core/01-tick-protocol.md:166`

**问题**：

在 `specs/core/01-tick-protocol.md` 内引用 `specs/core/06-phase2b-system-manifest.md`，相对路径可能解析为 `specs/core/specs/core/...`。同文件内另一处引用 `../core/09-snapshot-contract.md`，从 `specs/core` 出发等价于 `specs/core/09-snapshot-contract.md`，可用但不够直接。

**建议**：统一使用相对当前文件的路径：`06-phase2b-system-manifest.md`、`09-snapshot-contract.md`。

### L2. 示例测试伪代码存在可读性/正确性瑕疵

**位置**：
- `specs/core/01-tick-protocol.md:563`
- `specs/core/01-tick-protocol.md:769`

**问题**：

`fdb_commit_failure_restores_snapshot_consistency` 示例中 `snapshot_checksum_before` 初始后被 `let` 声明却后续赋值；断言在失败分支中对比的变量也容易误导，应对比当前 tick snapshot 的 checksum，而非最初或上一次成功 commit 的 checksum。

**建议**：将伪代码改为：每 tick snapshot 后立即保存 `snapshot_checksum`，失败恢复后断言 `world.state_checksum() == snapshot_checksum`。

## 架构正向评价

- Phase 2a inline 与 Phase 2b deferred 的职责边界清晰，尤其 combat/status intent 化能降低同 tick HP 顺序差异。
- Shadow Write + Atomic Publish 是正确方向，可以避免 per-room partial commit 暴露给读取路径。
- COLLECT 缓存跨 FDB retry 复用是必要设计，避免 WASM 重跑导致非确定性输出和重复扣费。
- FDB replay-critical 与 Object Store rich/debug 分层是合理方向，只需清理残留矛盾表述。
- WASM output 超限整批丢弃、canonical JSON、禁用浮点、BTreeMap/IndexMap 约束均有利于跨平台确定性。

## 建议的冻结前修复顺序

1. 先修复 TickCommitRecord / RichTraceBlob / Object Store replay-critical 边界。
2. 再统一 Shadow Write 提交流程为生产唯一权威路径。
3. 然后重整性能合同，将 hard deadline、SLO、benchmark gate 分层。
4. 最后清理字段矩阵、路径引用与伪代码问题。

## 评审结论

**结论：有条件通过（Conditional Pass）。**

DSv4 的核心架构可以继续推进，但不建议在当前文本状态下作为实现冻结合同。上述 Blocker 与 High 问题应在 R39 后续修订中完成收敛，否则实现团队可能基于不同章节落地出互不兼容的持久化、回放与提交语义。
