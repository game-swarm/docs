# R39-CV-DP-GPT — Determinism & Performance Review

## 评审范围

- `specs/core/01-tick-protocol.md`
- `specs/core/06-phase2b-system-manifest.md`
- `specs/core/09-snapshot-contract.md`
- `design/engine.md`

重点检查：HP writer contract、snapshot 构建、RNG、shadow write。

## 总体结论

当前文档已经覆盖了大多数确定性基础：canonical sort、Blake3 XOF、禁止 `std::HashMap` 迭代、snapshot 一次构建、Phase 2b manifest、shadow write + atomic publish 等。但仍存在若干会导致实现分叉或 replay 语义不一致的规范冲突。

结论：**不建议直接冻结为实现合同**。建议先修复下列 P0/P1 项，再进入实现或 conformance test 编写。

---

## Findings

### P0 — HP writer contract 中 S22 → PendingDamage 与 S15 顺序矛盾

**位置**

- `specs/core/06-phase2b-system-manifest.md:222`
- `specs/core/06-phase2b-system-manifest.md:252`
- `specs/core/06-phase2b-system-manifest.md:263`
- `specs/core/06-phase2b-system-manifest.md:432`
- `specs/core/01-tick-protocol.md:993`
- `design/engine.md:245`

**问题**

权威顺序是：

`S14 special_attack_reducer → S15 damage_application → S16-S22b status buffer production → S22 status_advance_system → S23 aging → S24 decay`

但 manifest 同时声明：

- S15 是 combat damage/heal 统一 HitPoints writer。
- S22 的 Leech 等 status effect 会写 `PendingDamage` buffer。
- 文档说明 “S22 Leech 等 status effect → PendingDamage buffer → S15 结算”。

这在当前顺序下不可实现：S15 已经在 S22 之前执行，S22 之后写入的 `PendingDamage` 无法在同 tick 被 S15 消费。实现者可能做出三种不兼容解释：

1. S22 写入的 damage 延迟到下一 tick；
2. S22 直接写 HP，破坏 S15 统一 HP writer；
3. 在 S22 后再次运行 S15，破坏 manifest 的 31-system 固定顺序。

**影响**

- Leech / status damage 的生效 tick 不确定。
- replay verifier 与线上实现可能分叉。
- “唯一 HP writer” 合同无法通过静态 CI 简单验证。

**建议**

二选一修复，并在 manifest、tick-protocol、engine.md 同步：

- 方案 A：所有会造成 HP 变化的 status effect 在 S14 或 S16-S22b 阶段产出 buffer，保证 S15 前已完整收集；S22 不允许写 `PendingDamage`。
- 方案 B：将 status damage 的唯一 writer 改为 S22 或新增 `S23 status_damage_apply`，并显式声明 HP writer 域与顺序，不再声称全部走 S15。

推荐方案 A，保留 S15 作为唯一 combat/status HP 结算点。

---

### P0 — TickCommitRecord same-transaction 合同与 WAL 降级语义冲突

**位置**

- `specs/core/01-tick-protocol.md:640`
- `specs/core/01-tick-protocol.md:700`
- `specs/core/01-tick-protocol.md:702`
- `specs/core/01-tick-protocol.md:705`
- `specs/core/01-tick-protocol.md:712`
- `specs/core/01-tick-protocol.md:714`
- `specs/core/01-tick-protocol.md:936`

**问题**

文档同时声明：

- TickCommitRecord 与世界状态在 FDB 同一事务中提交，失败则 tick abandon。
- TickCommitRecord 写入第 3 次失败后写本地 WAL，FDB 恢复后异步回放写入，且“不阻塞 tick 执行”。
- 又声明不存在 “世界状态已变但无审计记录” 的缺口。

这些语义互相冲突。如果本地 WAL 可以替代 FDB TickCommitRecord 并允许 tick 继续，那么 deterministic replay 的权威 replay-critical 子集不再是 FDB same-tx；如果不允许继续，则 WAL 只能作为失败诊断/本地 crash forensics，不能改变 tick abandon 语义。

**影响**

- replay-critical 数据源不唯一。
- crash recovery 时可能出现 FDB 世界 head 已推进、TickCommitRecord 只在本地 WAL 的状态。
- 多 engine / 多 observer 无法一致验证。

**建议**

收敛为一个明确合同：

- 推荐：TickCommitRecord 失败 = FDB 事务失败 = tick abandon。WAL 只能记录未提交 attempt，用于 debug，不得作为 replay-critical 成功路径。
- 若必须支持 WAL 成功路径，则需把 “本地 WAL commit” 纳入全局共识/复制协议，否则不能称为 deterministic replay authoritative。

---

### P1 — Shadow write manifest-only 与 “state/tick/N 同事务写世界状态” 表述冲突

**位置**

- `specs/core/01-tick-protocol.md:402`
- `specs/core/01-tick-protocol.md:414`
- `specs/core/01-tick-protocol.md:432`
- `specs/core/01-tick-protocol.md:485`
- `specs/core/01-tick-protocol.md:936`
- `design/engine.md:464`

**问题**

Shadow write 模型声明 per-room content-addressed staging rows 不是已发布状态，GlobalTickCommit 只发布 manifest/head/hash/pointer，不复制或提升 room rows。

但后续 TickCommitRecord 完整性示例仍写：

```text
FDB 事务:
  ├── 写入世界状态 (state/tick/N)
  ├── 写入 TickCommitRecord (tick_commit/tick/N)
  └── 写入 consumed_fuel (fuel/tick/N)
```

这会让实现者误以为 GlobalTickCommit 事务仍写入世界状态实体/room delta，而非只写 manifest 指针。

**影响**

- 实现可能回到大事务或 per-room promotion 语义，破坏 shadow write 的原子发布模型。
- FDB 事务大小预算和 GC 语义不清晰。

**建议**

将 §9.4 示例改为 shadow write 术语：

- `/committed/head/{tick}`
- `/committed/manifest/{tick}`
- `/committed/hash_chain/{tick}`
- `/tick_commit/{tick}`
- `/fuel/{tick}`

明确 “世界状态” 在 commit 事务中只是 manifest 指向的 content-addressed room hash list，而不是复制 room payload。

---

### P1 — RNG / shuffle seed 公式存在多处不一致表述

**位置**

- `specs/core/01-tick-protocol.md:238`
- `specs/core/01-tick-protocol.md:896`
- `specs/core/01-tick-protocol.md:980`
- `design/engine.md:200`
- `design/engine.md:263`

**问题**

同一玩家顺序 shuffle 出现至少三种表达：

- `Blake3(tick_number || world_seed)`
- `Blake3("shuffle" || world_seed || tick.to_le_bytes())`
- `hash(tick_number, world_seed)`

§9.1 的 domain-separated 版本更安全、更明确，应为唯一权威。§3.1 和 engine.md 的旧写法会导致实现者在字段顺序、domain separation、encoding 上产生分叉。

RNG namespace 表也使用 `world_seed + tick` 等非精确定义表达，虽随后给出 `Blake3(domain_sep || world_seed || tick.to_le_bytes())`，但表格易被误读为字符串拼接或算术加法。

**影响**

- replay verifier 与线上 shuffle 可能不同。
- domain collision 或 length ambiguity 风险。

**建议**

统一为 length-delimited + domain-separated KDF：

`derive_rng(domain, world_seed, tick, actor_or_entity_id?, sequence?)`

并声明 shuffle 固定为：

`Blake3(len("shuffle") || "shuffle" || world_seed || tick_le_u64)`

所有简写处只引用 §9.1，不再重复公式。

---

### P1 — Snapshot 构建时点在 snapshot-contract 与 tick-protocol 中表述不一致

**位置**

- `specs/core/01-tick-protocol.md:141`
- `specs/core/01-tick-protocol.md:180`
- `specs/core/09-snapshot-contract.md:21`
- `design/engine.md:183`

**问题**

Tick protocol / engine.md 明确：COLLECT 开始时构建一次 world snapshot，WASM 与 MCP query 读取同一份 `snapshot_tick == current_tick` 快照。

Snapshot Contract §1.1 却写 “引擎在每 tick 结束时为每个 player 生成感知快照”。这与执行模型冲突：WASM 输入快照必须在玩家代码执行前生成，不可能在 tick 结束时生成。

**影响**

- 实现者可能混淆 WASM input snapshot、post-commit display snapshot、broadcast delta。
- MCP `swarm_get_snapshot` 读源语义可能分叉。

**建议**

将 Snapshot Contract §1.1 改为：

- WASM/MCP perception snapshot：COLLECT 开始时基于 pre-execute Bevy World 构建。
- Display/post-commit snapshot：如有，则另行命名，不作为 WASM input contract。

---

### P2 — Snapshot truncation schema 字段名不一致

**位置**

- `specs/core/01-tick-protocol.md:150`
- `specs/core/09-snapshot-contract.md:30`
- `design/engine.md:429`

**问题**

Tick protocol 的伪代码返回：

- `omitted_count`

Snapshot Contract 要求稳定 schema：

- `omitted_categories: { entities, resources, events }`

engine.md 又写 `omitted_counts` 和 bucket 统计。字段名与结构不一致。

**影响**

- SDK/WASM ABI schema 不稳定。
- canonical snapshot hash 可能因字段差异分叉。

**建议**

以 Snapshot Contract 为唯一权威，统一字段为：

- `truncated: bool`
- `omitted_categories: { entities: u32, resources: u32, events: u32 }`
- 如需要 bucket 统计，新增 `truncation_stats`，不要替代 `omitted_categories`。

---

### P2 — Snapshot critical entity 内部降级排序缺少完全定义

**位置**

- `specs/core/09-snapshot-contract.md:84`

**问题**

Critical entity 超过 128KB 预留时，文档允许内部字段降级，并给出排序：

`(entity_priority_bucket, last_modified_tick DESC, entity_id)`

但 `entity_priority_bucket` 未完整枚举，`last_modified_tick DESC` 对同 tick 多组件修改的 tie-breaker 也未说明。

**影响**

- 截断结果可能跨实现不一致。
- canonical snapshot hash 不稳定。

**建议**

补充完整 priority bucket 表，并增加最终 tie-breaker：`component_type_id lexicographic`、`field_path lexicographic` 或固定 field order。

---

## 正向确认

以下设计方向对确定性有帮助，应保留：

- Phase 2a command sort 使用 canonical key，并记录到 TickCommitRecord。
- Phase 2b manifest 要求 stable system IDs、显式 R/W matrix、实体迭代按 `StableEntityId`。
- Snapshot 在 COLLECT 阶段一次构建，WASM 与 MCP query 共享同一快照。
- Pathfinding cache 被定义为 pure optimization，hit/miss 不改变输出，cache hit 仍消耗相同 fuel。
- Shadow write + GlobalTickCommit 作为唯一 publish point 的方向正确，能避免 per-room partial commit 语义。
- 禁止浮点、禁用 `std::HashMap` replay-critical iteration、canonical JSON/JCS 是正确的确定性约束。

## 建议的验收测试

1. **HP writer conformance**：静态验证 S10/S22 不直接写 HitPoints；动态验证 Leech/status damage 与 Attack/Heal 在同 tick 生效顺序。
2. **RNG fixture**：固定 `(world_seed, tick, player_set)`，生成 shuffle order golden file；跨 debug/release/平台比对。
3. **Snapshot fixture**：构造超 256KB 可见实体集，验证截断输出 JSON byte-for-byte 一致。
4. **Shadow write fault injection**：注入 staging 成功但 GlobalTickCommit 失败，验证 committed manifest/head 不变、staging GC 后不可见。
5. **TickCommitRecord failure injection**：注入 TickCommitRecord 写失败，验证 tick 不推进且无 committed head。

## 最小修复清单

- 修复 S22/S15 HP buffer 顺序矛盾。
- 删除或降级 TickCommitRecord WAL “不阻塞 tick 执行” 表述。
- 将 TickCommitRecord 示例改为 shadow write manifest-only commit。
- 统一 RNG derive 公式和 shuffle seed 公式。
- 修正 Snapshot Contract 的 “tick 结束时” 表述。
- 统一 snapshot truncation schema 字段名。
