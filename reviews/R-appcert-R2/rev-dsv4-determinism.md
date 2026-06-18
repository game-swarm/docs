# R-appcert-R2 确定性评审 — DeepSeek V4 Pro

> **评审员**: rev-dsv4-determinism (DeepSeek V4 Pro)
> **评审视角**: 状态机完备性、RNG 合约、回放完整性、指令顺序确定性、超时/epoch bump 语义
> **评审范围**: 仅设计文档，不考虑分阶段实现难度

---

## Verdict: CONDITIONAL_APPROVE

设计在确定性方面总体上非常扎实。核心确定性保证（Blake3 XOF 单一 PRNG 原语、种子洗牌命令排序、`.chain()` 严格 ECS 调度、全量回放架构、FDB 原子提交、定点数运算）均已妥善设计。发现的问题均为可修复的文档不一致或规范围观缺失，无根本性设计缺陷。两个 HIGH 级别发现需设计团队回应后方可进入实现阶段。

---

## Strengths（亮点）

1. **单一 PRNG 原语 (Blake3 XOF)**: 所有随机性来源统一使用 `Blake3 XOF(seed, offset)`，包括 combat 伤害浮动、spawn 位置随机、资源再生随机、世界事件触发。无 OS 熵源依赖，跨平台完全确定。

2. **种子洗牌命令排序**: `Blake3(tick_number || world_seed)` 驱动的 seeded shuffle 同时满足确定性和公平性——相同 seed + 相同指令集 → 相同顺序。每 tick 玩家顺序随机轮换，长期期望均等。

3. **严格 ECS 调度 (.chain())**: 有数据依赖的 18 个系统串行执行，无数据竞争的系统（regeneration/decay）利用 Bevy 依赖图并行调度。Component 读写矩阵精确定义了并行安全边界。

4. **全量回放架构**: TickTrace 记录 `Command[]` 而非 WASM 输出。回放时不重新执行 WASM——直接执行已记录的指令序列。Wasmtime 版本变更不影响回放。

5. **FDB 原子提交 + 快照恢复**: 每 tick 包裹在 FDB 事务中，全提交或全回滚。Phase 2a 开始前做 Bevy World 深拷贝快照——commit 失败时精确恢复，`state_checksum` 验证。

6. **COLLECT 结果跨重试缓存**: FDB commit 失败重试时复用同一次 COLLECT 结果（命令序列 + fuel 扣费），不重新执行 WASM。跨重试 fuel 总消耗 ≤ 1 × MAX_FUEL。

7. **快照截断确定性排序**: `(bucket, distance_to_drone, entity_id)` 排序键完全由世界状态中的确定值派生，同一 tick 同一世界状态产生同一截断结果。

8. **Overload 抗永久锁死证明**: 数学证明不存在一组攻击者能通过协调 Overload 永久锁死目标 fuel budget——全局冷却 + 下限保护 + Fortify 清除机制形成闭合。

9. **定点数运算全覆盖**: 禁用 `f64`，所有比例计算使用 `fixed<u32,4>`（×10000）。`IndexMap` 替代 `std::HashMap` 保证迭代顺序确定。

10. **安全 epoch bump 确定性语义**: Replay 使用记录的 bump 事件而非重新触发；模块安全状态从 TickTrace 重放，bump 时间戳使用记录值而非 wall clock。

11. **Rhai 事务性执行模型**: 所有 `actions.*` 调用先写入 `RhaiActionBuffer`，脚本全部执行完毕后统一 atomic apply。AST 节点预算（非墙钟）作为确定性终止条件。

12. **MCP/WASM 快照一致性**: MCP query 与 WASM `tick()` 基于同一份快照——`snapshot_tick == current_tick`，不存在时差 oracle。

---

## Findings（发现的问题）

### D1 [HIGH] — ECS 调度: regeneration/decay 系统的并行 vs 串行矛盾

**位置**: engine.md §3.2 Phase 2b vs 01-tick-protocol.md §3.4

**问题**: 两份核心文档对 `regeneration_system` 和 `decay_system` 的调度方式描述矛盾：

- engine.md §3.2 Phase 2b：
  ```
  regeneration_system ─┐
  decay_system ────────┤ 并行（无数据竞争，与主线无依赖）
  ```
- 01-tick-protocol.md §3.4：两个系统位于 `.chain()` 内部（串行执行）
- 01-tick-protocol.md §3.4 Component 读写矩阵和并行安全证明：假设两者并行

**确定性影响**: 若两个系统与主线串行（当前 `.chain()` 写法），Bevy 并行调度不会激活——所有系统按 chain 顺序逐个执行，`regeneration` 和 `decay` 实际上串行于 `combat` 之后。若改为并行（`.before(death_cleanup).after(combat)`），则两者与主线系统并发，但数据独立保证结果相同。

两种调度均保持确定性（只要数据依赖正确），但**不一致会导致实现分叉**——不同开发者按不同文档实现，产生不同的执行顺序，可能导致相同输入产生不同中间状态时间线（如在某 tick 内 regeneration 对 combat 的可见性不同）。

**建议**: 明确权威调度模式。若保持 `.chain()` → 更新 engine.md §3.2 和并行安全证明。若改为并行 → 从 `.chain()` 中移除。

### D2 [HIGH] — combat_system 内 Tower 自动攻击的迭代顺序未定义

**位置**: 01-tick-protocol.md §3.4, engine.md §3.2

**问题**: Phase 2b `combat_system` 处理 Tower 自动攻击、DoT 结算和状态叠加结算。当多个 Tower 在同一 tick 攻击同一目标时，damage 的应用顺序决定目标是否在某个攻击前死亡（影响后续攻击的结算）。当前规范未定义 Tower 在 `combat_system` 内的处理顺序。

Bevy 的 entity 迭代顺序依赖 archetype 存储顺序——存储顺序由 entity 创建顺序决定（在 Swarm 中是确定的），但 Bevy 不将此作为 API 稳定性保证，且未明确承诺跨版本一致性。

**确定性影响**: 若 Bevy 内部 entity 迭代顺序在跨版本或跨编译配置下变化，同一输入可能产生不同的 Tower 攻击结算顺序——导致不同的 damage 分配，破坏确定性保证。

**建议**: 在 `combat_system` 内部显式定义 Tower 攻击的排序键，如 `(room_id, entity_id)` 或 `(owner_id, entity_id)`。不应依赖 Bevy 的隐式 entity 迭代顺序。

### D3 [MEDIUM] — WASM 输出截断语义描述矛盾

**位置**: 02-command-validation.md §1.1, 01-tick-protocol.md §8.2

**问题**: 对 WASM 输出超过 256KB 的处理，存在两处语义矛盾：

- 01-tick-protocol.md §8.2 统一预算表：`"Output JSON: 256 KB — 截断（保留前 256KB）"`
- 02-command-validation.md §1.1：`"总字节数 ≤ 256 KB"` — 超限 → `"整个 tick 输出丢弃"`
- 04-wasm-sandbox.md §2.4：`"CommandIntent JSON 超过 256KB → 拒绝该玩家当 tick 所有输出"`

"保留前 256KB" 与 "整个输出丢弃" 是互斥的。若保留前 256KB，截断点可能出现在 JSON 结构中间，产生不可解析的输出——这也与 "JSON schema 验证" 的前提冲突。

**确定性影响**: 若实现采用 "保留前 256KB" 语义，截断后的 JSON 可能语法不完整 → 解析失败 → 效果等同于丢弃。但若实现采用智能截断（在最后完整 JSON 对象处截断），则不同实现的截断行为可能不同，破坏确定性。

**建议**: 统一为 ">256KB → 整批输出丢弃，退回该 tick 所有指令，不计入 refund"（与 02-command-validation 和 04-wasm-sandbox 一致），删除 01-tick-protocol 中的 "保留前 256KB" 表述。

### D4 [MEDIUM] — snapshot_len 为实际序列化大小，绑定序列化格式

**位置**: 01-tick-protocol.md §2.3

**问题**:
```
snapshot_len: serialized_size(&entities),  // 实际序列化后大小
```
WASM 代码可通过此字段判断 "是否接近 256KB 阈值" 来调整策略。若未来序列化格式变更（如 JSON → MessagePack → 自定义二进制），`snapshot_len` 的含义会直接改变——导致依赖此值的 WASM 策略行为变化。

**确定性影响**: 同一世界状态在不同序列化格式下产生不同的 `snapshot_len` 值。虽然 replay 在同格式下可复现，但跨格式迁移时破坏向后兼容。这不是严格的当前 tick 确定性 bug，而是**长远确定性合约稳定性**问题。

**建议**: 将 `snapshot_len` 定义为 `visible_entity_count`（可见实体数）或 `estimated_serialized_bytes`（近似值），而非绑定到具体序列化格式的精确字节数。或明确将其标记为 `unstable: true`（不保证跨版本稳定）。

### D5 [LOW] — snapshot_tick 语义对 WASM 作者可能混淆

**位置**: 05-visibility.md §3.1, §5

**问题**: `snapshot.tick == N` 的含义是 "tick N 的快照"，但此快照反映的是 tick N-1 执行后的世界状态。WASM `tick()` 接收的快照和 MCP `swarm_get_snapshot` 返回的快照都在 `snapshot_tick == N`，但它们代表的世界状态是 tick N 开始前（即 tick N-1 提交后）的。对 WASM 模块作者来说，`snapshot.tick` 可能被误解为 "这是我正在处理的 tick 的快照" vs "这是 tick N-1 的结果"。

**确定性影响**: 无直接确定性影响。这是 API 语义清晰度问题——可能引起 WASM 模块作者的时间线混淆。

**建议**: 在 API 文档中显式注释：`snapshot.tick` 是快照构建时刻的 tick 编号（即当前正在处理的 tick），快照内容反映的是上一个 tick 提交后的世界状态。

### D6 [LOW] — 种子轮换触发逻辑的相位边界需 CBOR 测试覆盖

**位置**: 01-tick-protocol.md §3.1

**问题**: seed epoch 轮换发生在 `seed_rotation_system`（位于 `.chain()` 中 regeneration 之后）。若 seed epoch 切换发生在 tick N 且 EXECUTE 阶段被 FDB rollback，rollback 恢复的 Bevy World snapshot 可能使用旧 seed。下次重试时 `seed_rotation_system` 会再次执行，产生不同的新 seed。

**确定性影响**: 分析表明此场景不影响确定性——若 tick N 被 rollback：
- Bevy World 恢复到 Phase 2a 前的状态（快照），seed 回到旧值
- 重试时 `seed_rotation_system` 以相同输入再次执行 → 产生相同的 new_seed
- COLLECT 缓存复用的命令列表不变 → EXECUTE 结果不变

但此路径应在 CI 确定性测试中覆盖（在 epoch 边界 tick 注入 FDB commit failure）。

**建议**: CI 确定性测试增加 epoch 边界 tick 的故障注入场景。

### D7 [LOW] — RNGState 在快照恢复中的原子性声明不足

**位置**: 01-tick-protocol.md §3.5

**问题**: Bevy World 快照范围清单包含 `RNGState`，但 `world.restore(snapshot)` 的语义描述为 "将 Bevy World 完全回滚至 Phase 2a 前的状态，包括所有实体的 Component 数据、所有 Resource 数据"。`RNGState` 作为 Resource 被隐式覆盖，但缺少显式确认。

**确定性影响**: 无——Resource 类型在快照范围内，"所有 Resource 数据" 已覆盖 `RNGState`。此发现仅建议显式声明以消除审计疑虑。

**建议**: 在快照范围清单之后增加一行："RNGState 随 snapshot 原子恢复——rollback 后 PRNG 状态与 Phase 2a 前完全一致。"

---

## Consistency Gaps（跨文档一致性缺口）

| 缺口 | 文档 A | 文档 B | 严重度 |
|------|--------|--------|:------:|
| regeneration/decay 调度方式 | engine.md §3.2: 并行 | 01-tick-protocol.md §3.4: `.chain()` 内串行 | HIGH |
| WASM 输出截断语义 | 01-tick-protocol.md: "保留前 256KB" | 02-cmd-validation + 04-wasm: "整批丢弃" | MEDIUM |
| `regeneration_system` 在 `.chain()` 中的位置 vs 并行描述 | 01-tick-protocol.md §3.4: chain 中第 4 位 | 同一文档 §3.4 并行安全证明: 假设并行 | HIGH |

---

## Algorithmic Risks（算法风险）

1. **snapshot 全量深拷贝 (Tier 1)**: ≤16MB/tick, ≤50ms 构建。在 50 players × 10 drones 规模下可行。若实际 entity count 因建筑/Source/Controller 等超越预期，深拷贝开销线性增长。建议 CI 中 mock 最坏情况（每玩家 50 drone + 100 建筑 + 50 Source）。

2. **Tier 2 增量快照的 modification-set**: 提案中的 `(bucket, last_modified_tick DESC, entity_id)` 排序键依赖 "最近修改" 语义——需要 `last_modified_tick` 字段在所有 entity 上精确维护。若某 ECS system 修改了 entity 但未更新此字段（实现遗漏），截断顺序将偏离设计意图。虽不影响同一 CI/版本的确定性，但可能导致调试困难。

3. **跨分片 combat 两阶段协议 (Tier 3)**: 依赖逻辑时钟 `(tick, shard_priority, entity_id)` 作为 tie-breaker。此设计正确——但在 Phase 1→Phase 2 之间若 target 被其他攻击击杀，`AttackResult.target_dead` 的触发逻辑需要完整覆盖所有竞态。建议在 Tier 3 spec 冻结前用 TLA+ 或类似形式化方法验证。

---

## 评审总结

Swarm 的确定性设计在核心路径上是卓越的——Blake3 单一原语、种子洗牌、`.chain()` 调度、回放架构形成四重保障。7 个发现中 2 个 HIGH（均属文档不一致，非设计缺陷）、2 个 MEDIUM（语义澄清）、3 个 LOW（测试覆盖/文档增强）。修复后无阻塞进入实现阶段。

**建议**: 在设计进入 Phase 1 实现前，由 Architecture Reviewer 确认 D1 的权威调度方案，并统一 D3 的截断语义。
