# R39-CV-ARCH-GPT — Architect GPT 全量架构评审

评审对象：
- `/tmp/swarm-review-R39/design/engine.md`
- `/tmp/swarm-review-R39/specs/core/01-tick-protocol.md`
- `/tmp/swarm-review-R39/specs/core/05-persistence-contract.md`
- 交叉参考：`/tmp/swarm-review-R39/specs/core/06-phase2b-system-manifest.md`

评审维度：架构边界、Phase 2a/2b 数据流、persistence replay 合同、ECS manifest。

## 结论摘要

当前架构主线清晰：COLLECT 只读快照、EXECUTE 修改 Bevy World 并以 FDB 为持久化权威、BROADCAST 不回滚已提交 tick；Phase 2a inline 与 Phase 2b deferred 的边界总体合理；shadow write + atomic publish 也比旧 per-room commit 模型更稳健。

但本轮发现 **4 个阻断级问题** 与 **5 个重要一致性问题**。阻断项主要集中在 ECS manifest 计数/顺序、Leech/Status 到 damage pipeline 的数据流、Spawn pending 合同，以及 TickCommitRecord/WAL 失败语义。若不修正，后续实现会出现 replay 分叉、系统注册 CI 无法落地、或 tick 成功/审计完整性语义自相矛盾。

## 阻断级问题

### A1. ECS Manifest “31 systems” 与实际清单不一致

**位置**：`06-phase2b-system-manifest.md` §1、§5；`engine.md` §3.2/§3.3；`01-tick-protocol.md` §3.4/§9.6。

文档多处声明权威 manifest 为 **31 systems**，但 `06-phase2b-system-manifest.md` 实际列出：

- Phase 2a：`S01-S06` = 6 个
- 新增 `A01 action_dispatch` = 1 个
- Phase 2b：`S07-S29` = 23 个
- 额外命名的 `S22a leech_buffer`、`S22b fabricate_buffer` = 2 个

按清单实体计数为 **32 个 system/handler**。若 `A01` 不是 system，应明确它是 `S01` 的 handler 子路径且不进入 manifest hash；若它是独立 system，则所有 “31 systems”、`system_id_31`、CI gate、manifest_hash 计算都应改为 32。

**影响**：
- `manifest_hash` 无法稳定实现。
- CI “代码注册与文档匹配（31 systems）”会与实际注册冲突。
- replay verifier 对 `system_manifest_hash` 的解释可能分叉。

**建议修正**：选择一个权威口径：
1. 若保留 `A01` 独立调度单元：全量改为 **32 systems**，manifest hash 输入包含 `A01`。
2. 若坚持 31：把 `A01` 降级为 `S01 command_executor` 内的 dispatch branch，不单独出现在 schedule、R/W matrix 与 manifest hash 中。

### A2. S22 Leech 写 PendingDamage 但 S15 已经执行，伤害结算路径断裂

**位置**：`06-phase2b-system-manifest.md` §1、§2 S15、§2 S22、§4；`engine.md` §3.2 Phase 2b pipeline；`01-tick-protocol.md` §9.6。

当前顺序为：

```text
S14 special_attack_reducer → S15 damage_application → S16-S22b buffers → S22 status_advance_system → S23 aging → S24 decay
```

但 S22 明确会为 Leech 等 status effect 写入 `PendingDamage buffer`。由于 `S15 damage_application` 已在 S22 之前执行，该 `PendingDamage` 在本 tick 没有消费点。文档又要求 buffer tick 结束清空，不跨 tick 持久化，因此 Leech damage 可能被丢弃，或实现者被迫引入未声明的跨 tick buffer。

**影响**：
- Status damage 与 combat damage 的确定性结算语义不成立。
- Leech 行为在实现间可能出现“本 tick 生效 / 下 tick 生效 / 永不生效”分叉。
- Unique Writer 合同与 buffer 生命周期冲突。

**建议修正**：二选一：
1. 将 `S22 status_advance_system` 移到 `S15 damage_application` 前，使 S22 产出的 `PendingDamage` 被同 tick S15 消费。
2. 保持 S22 位置不变，但禁止 S22 写 `PendingDamage`，改为 S22 只写 `StatusDamageApplied` 或直接由一个后置 `status_damage_application` 统一结算，并更新 R/W matrix 与 manifest hash。

推荐方案 1：`S14 → S16-S22b → S22 → S15 → S23 → S24`，并重新审查 S15 是否仍需 `Must run after S14`。

### A3. Spawn “validate only / 不入队” 与 PendingSpawn 合同冲突

**位置**：`engine.md` §3.2、§Phase 2a/2b 分类原则；`01-tick-protocol.md` §1.4/§3.3；`06-phase2b-system-manifest.md` S06/S08。

`engine.md` 与 `01-tick-protocol.md` 多处写明：

- “Spawn 命令在 Phase 2a 中只校验不入队”
- “Spawn 只校验不入队”

但 manifest 的 S06/S08 合同写明：

- S06：校验 + 扣费 + 写入 `PendingSpawn buffer`
- S08：读取 `PendingSpawn buffer` 创建 drone

从架构上看，S08 必须有 PendingSpawn 输入，因此“只校验不入队”是不成立的。更准确的语义应为：**Phase 2a 校验、扣费并写 PendingSpawn，但不创建实体、不让新实体 same-tick 可见或可交互**。

**影响**：
- 实现者可能真的不入队，导致 spawn 永不创建。
- replay 记录与 body_cost refund 路径无法统一。
- TOCTOU 合同表述误导。

**建议修正**：统一改写为：

```text
Spawn 在 Phase 2a 中 validate + reserve/deduct + enqueue PendingSpawn；实体创建仅由 Phase 2b S08 执行，创建实体进入 PendingEntityCreation，flush 后下一 tick 可见。
```

### A4. TickCommitRecord FDB 同事务与 WAL fallback 语义自相矛盾

**位置**：`01-tick-protocol.md` §6.1、§6.3.4、§9.4；`05-persistence-contract.md` §2、§3、§7。

`01-tick-protocol.md` 一方面声明 TickCommitRecord 与世界状态同一 FDB 事务，失败则 tick abandon，不存在状态已变但审计缺失；另一方面在 §6.3.4 表格中写第 3 次失败后“写入本地 WAL”，且 WAL 恢复“不阻塞 tick 执行”。这与“FDB replay-critical 同事务不可降级”冲突。

`05-persistence-contract.md` 的权威方向更清晰：FDB commit 是唯一持久化点；TickCommitRecord 10 字段 replay-critical，不可降级；对象存储可降级。建议以 `05` 为准，删除或重写 `01` 中 TickCommitRecord WAL fallback 的“继续 tick”语义。

**影响**：
- 若 FDB replay-critical 写失败但 tick 继续，会产生 FDB 状态与审计记录不一致。
- 若 WAL 本地记录可替代 FDB 同事务，则 replay verifier 的权威输入从 FDB 扩散到本地 WAL，破坏单一权威源。

**建议修正**：
- TickCommitRecord replay-critical 字段写失败 = FDB transaction fail = tick abandon/retry。
- WAL 只能记录 **未提交 attempt 的本地恢复辅助日志**，不得使 tick 被视为 committed。
- `WAL 恢复不阻塞 tick 执行` 仅可用于非 replay-critical debug/rich 或 operator recovery，不可用于 committed tick 审计替代。

## 重要一致性问题

### B1. Persistence replay 输入合同存在“10 字段”与扩展 envelope 的权威边界不清

`05-persistence-contract.md` 声明 TickCommitRecord replay-critical subset 为 10 个字段；`engine.md` 的 `TickInputEnvelope` 与 `01-tick-protocol.md` 又列出 `collect_id`、`attempt_id`、`commit_id`、`wasm_status`、`deploy_events`、`rollback_events`、`admin_events`、`terminal_state` 等更多字段。

这不一定错误，但需要明确三层：

- **Replay-critical minimum**：05 中 10 字段，缺失不可 replay。
- **Attempt/audit metadata**：collect/attempt/commit/status，用于审计与 retry 追踪，但是否 replay-critical需逐项声明。
- **Rich/debug metadata**：对象存储或可降级字段。

否则实现者会不知道 `collect_id` 或 `wasm_status` 缺失时应标记 `unreplayable`、`audit_gap` 还是 `reconstructable`。

### B2. `05-persistence-contract.md` §5 “正常 Replay” 仍以对象存储 blob 为步骤 2–5，弱化了“对象存储非 replay-critical”声明

§2 明确 deterministic replay 不依赖对象存储；但 §5.1 正常 Replay 流程写成先从对象存储获取 tick_trace_blob，再反序列化 TickCommitRecord。若 TickCommitRecord 的 10 字段在 FDB 中，则 deterministic replay 应先读取 FDB subset；对象存储只用于 rich debug replay。

建议拆成两个流程：

- Deterministic replay：FDB TickCommitRecord subset + keyframe/delta chain。
- Rich debug replay：在 deterministic replay 已验证后，可选读取对象存储 RichTraceBlob。

### B3. Shadow Write 与 `05` §3 “FOR each persistent state mutation UPDATE rows” 表述不完全一致

`01-tick-protocol.md` §3.5 与 `05` §8 已采用 room staging + GlobalTickCommit manifest-only publish；但 `05` §3 Tick Commit 序列仍描述 FDB 事务中 `FOR each persistent state mutation UPDATE entity/resource/controller/... rows`。这容易被理解为单事务直接更新 committed state rows，而非 staging publish。

建议在 §3 区分：

- small profile single-tx：可直接更新 state rows。
- production room-partition：写 staging content-addressed rows；GlobalTickCommit 只发布 manifest/head/hash-chain。

### B4. Tick 快照边界存在 COLLECT snapshot 与 rollback snapshot 两种概念混用风险

`01-tick-protocol.md` §2.3 的 COLLECT snapshot 是玩家/MCP 可见只读快照；§3.5 的 Bevy World snapshot 是 Phase 2a 前用于 FDB commit 失败恢复的执行回滚快照。两者时间点接近但用途不同。

建议显式命名：

- `PlayerVisibleSnapshot` / `CollectSnapshot`：可见性、截断、WASM 输入。
- `ExecutionRollbackSnapshot`：完整 Bevy World 深拷贝，用于 commit failure rollback，不受 fog/truncation 影响。

这样可避免实现者误用截断后的 player snapshot 做 rollback。

### B5. Manifest 版本表与正文 R35 D3 不一致

`06-phase2b-system-manifest.md` 版本表 v3.0.0 仍写 “S01 写入 PendingSpecialAttackIntent、S14 从 S01 读取 intents”，但正文 R35 D3 已改为 A01 ActionRegistry handler 写 status intent buffer，S14 从 A01 读取。

建议更新版本表或新增 v4.0.0，避免维护者按版本记录实现旧路径。

## 正向确认

以下架构边界和合同在三份核心文档中总体一致，建议保留：

- **COLLECT/EXECUTE/BROADCAST 边界**：COLLECT 读取固定快照，EXECUTE 修改 Bevy World，BROADCAST failure 不回滚 committed tick。
- **Phase 2a inline 语义**：命令按 canonical sort 逐条校验并基于当前 Bevy World 应用，资源竞争先到先得。
- **Phase 2b 被动系统原则**：serial spine + parallel sets，StatusState unique writer 思路正确。
- **Shadow Write + Atomic Publish**：staging row 非已发布状态，GlobalTickCommit 是唯一 publish 点，避免 per-room partial commit。
- **WASM replay 边界**：replay 使用 recorded commands，不重新执行 WASM，Wasmtime 版本变化不破坏确定性 replay。
- **对象存储降级策略**：RichTraceBlob / WASM blob 非 replay-critical，缺失应是 audit gap，而非 deterministic unreplayable。

## 建议修复顺序

1. 先修 `06-phase2b-system-manifest.md`：确定 31/32 口径，修正 A01、S22/S15 顺序、R/W matrix、manifest hash、版本表。
2. 再修 `engine.md` 与 `01-tick-protocol.md`：同步 Phase 2b 顺序与 Spawn PendingSpawn 语义。
3. 修 `01-tick-protocol.md` §6.3.4：删除 TickCommitRecord WAL 替代同事务提交的歧义。
4. 修 `05-persistence-contract.md`：拆分 deterministic replay 与 rich replay 流程，并明确 10 字段与扩展 envelope 的权威关系。
5. 增加 CI gate：manifest system count/hash fixture、S22/S15 buffer 消费验证、Spawn pending 创建路径 replay fixture、FDB commit fail 不产生 TickCommitRecord fixture。

## 最终判定

**R39 当前不建议直接进入实现冻结。**

架构方向可接受，但需先清理上述阻断级合同冲突。尤其 ECS manifest 是 replay determinism 的根，若 system count、调度顺序、R/W matrix 和 manifest hash 不统一，后续所有 replay/persistence 合同都会失去可验证基础。
