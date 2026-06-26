# R39 Determinism & Performance Closure Verification — DSV4 报告

## 结论

**Verdict: REQUEST_CHANGES**

R39 指定范围内的确定性主干已经明显收敛：tick 输入封套、命令排序、Phase 2b serial spine、snapshot truncation、FDB shadow write、COLLECT 缓存复用、same-tx TickCommitRecord 等关键合同均已写入文档，并且多数设计方向正确。

但仍存在 5 个会导致实现分叉或 reviewer 复查失败的文档级问题。其中 **2 个 High** 直接影响确定性/回放合同的一致解释，建议在进入下一轮 Closure Verification 前修正；其余 3 个 Medium/Low 为残留矛盾、术语漂移或测试描述错误。

## 审阅范围

- `specs/core/01-tick-protocol.md`
- `specs/core/06-phase2b-system-manifest.md`
- `specs/core/09-snapshot-contract.md`
- `design/engine.md`

## 已闭合 / 收敛点

1. **命令全局排序合同已具备可实现性**
   - `specs/core/01-tick-protocol.md` §9.1 定义 `sort_key = (priority_class, shuffle_index, source_rank, sequence, command_hash)`，并要求 `command_hash = Blake3(canonical_serialize(raw_command))`。
   - `specs/core/01-tick-protocol.md` §7.1 明确禁用 `std::hash`、禁用浮点状态、使用 RFC 8785/JCS canonical JSON、使用 `BTreeMap`。
   - 这足以避免大多数跨平台排序与序列化漂移。

2. **Phase 2b 调度权威源清晰**
   - `specs/core/06-phase2b-system-manifest.md` 声明自己是 tick 系统执行顺序唯一权威，覆盖 31 systems、serial spine 与 parallel sets。
   - `specs/core/01-tick-protocol.md` §3.4 与 §9.6、`design/engine.md` §3.2/§3.3 均引用该 manifest，方向正确。

3. **Status Effect 并行安全模型基本闭合**
   - Manifest 将 S16-S22b 限定为 typed buffer producers，将 S22 设为唯一 `StatusState` writer。
   - §4 R/W matrix 与 §6 CI 验证明确 Unique Writer、Buffer 生命周期、parallel set 无共享写入。

4. **快照截断合同足够确定**
   - `specs/core/09-snapshot-contract.md` §1.3 定义距离桶、entity_id 字典序、farthest-first 截断。
   - §1.4 定义 critical entity reserve 和关键实体内部降级排序。
   - `specs/core/01-tick-protocol.md` §2.3 与 `design/engine.md` §3.4.4 均指向 snapshot-contract，整体权威边界正确。

5. **tick 原子性从旧 per-room commit 语义迁移到 Shadow Write**
   - `specs/core/01-tick-protocol.md` §3.5 将 staging 行与 GlobalTickCommit publish 点分离，消除了“部分房间已提交、全局 abort”的窗口。
   - Cross-room intent 使用 all-or-reject 语义，失败时全局 abandon + snapshot restore，方向正确。

## 未闭合问题

### H1 — Phase 2a/A01 调度语义仍有“双系统顺序”歧义

**严重级别**: High  
**影响**: replay / action dispatch / 命令排序实现可能分叉

`specs/core/06-phase2b-system-manifest.md` 将 Phase 2a 写成固定 serial spine：S01 command_executor → A01 action_dispatch → S02...S06。但同一文件又说 A01 “Must run after S01 command sorting / quota gate for the same command slot”，而 `specs/core/01-tick-protocol.md` §3.3 说命令循环逐条校验 + 逐条应用。

问题在于：如果实现者按 manifest 图理解为“先批量运行 S01 处理所有非 Action 命令，再批量运行 A01 处理所有 Action 命令”，则会改变全局排序语义；如果实现者按 tick-protocol 理解为“每条命令根据 type 分派到 S01 或 A01”，则 manifest 中的 S01→A01 串行 spine 是伪顺序而不是实际执行阶段。

**证据**:
- `specs/core/06-phase2b-system-manifest.md` §1 将 S01、A01、S02-S06 画入同一个 serial spine。
- `specs/core/06-phase2b-system-manifest.md` §2 A01 写 “Must run after: S01 command sorting / quota gate for the same command slot”。
- `specs/core/01-tick-protocol.md` §3.3 写 “逐条校验 + 逐条应用”。

**建议修复**:
- 将 Phase 2a manifest 改写为“per-command dispatcher loop”，明确每个 `global_queue` slot 只执行一个 handler：非 Action 命令进入 S01/S02/S03/S04/S05/S06 对应 handler，`CommandAction::Action` 进入 A01。
- 明确 S01 不是所有命令的前置批处理阶段；“quota gate / sorting” 是命令循环的公共前置逻辑，不是 S01 system 的批量执行。
- 在 manifest 中用伪代码替代 S01→A01 的阶段图，例如：`for cmd in sorted(global_queue): dispatch(cmd.kind)`。

### H2 — `TickCommitRecord` 写失败语义自相矛盾

**严重级别**: High  
**影响**: 审计完整性 / replay terminal_state / 实现错误恢复

`specs/core/01-tick-protocol.md` §6.1 明确 `TickCommitRecord write fail` 会导致 tick 放弃、state 回滚，不存在状态已提交但审计记录缺失。§6.3.4 也反复声明 TickCommitRecord 与世界状态是同一 FDB 事务，要么都成功，要么都失败。

但同一节的失败次数表又写：第 3 次写入失败时写入本地 WAL，“本地完整，未全局持久化”；第 4+ 次 WAL 写入 + CRITICAL。这与同事务原子语义冲突：如果 FDB 同事务内 TickCommitRecord 写失败，整个 tick 应 abandon，不应继续 tick 执行并依赖 WAL 补审计。否则就重新引入“状态成功但全局审计缺失/延迟”的语义。

**证据**:
- `specs/core/01-tick-protocol.md` §6.1 表格：TickCommitRecord write fail → tick 放弃。
- `specs/core/01-tick-protocol.md` §6.3.4 表格：失败 3 次 → 写入本地 WAL，失败 4+ → WAL + 告警。
- `specs/core/01-tick-protocol.md` §9.4 又写缺失 ≥1 字段则 `terminal_state = unreplayable`，tick 放弃时不产生 TickCommitRecord。

**建议修复**:
- 二选一收敛，推荐选择 A：
  - **A（推荐）**：删除 TickCommitRecord 的 WAL 降级表；保留同事务失败 = tick abandon。WAL 只允许用于 engine crash 前的本地诊断日志，不作为 replay-critical TickCommitRecord 的替代路径。
  - B：如果确实要 WAL，则必须承认 tick 成功但 TickCommitRecord 可延迟持久化，并重写 §6.1、§9.4、terminal_state 语义。但这会削弱当前确定性合同，不推荐。

### M1 — system 数量与编号存在残留不一致

**严重级别**: Medium  
**影响**: manifest hash / CI 注册验证 / reviewer 误报

Manifest 多处写 “31 systems”，但系统编号实际到 S29，外加 A01、S22a、S22b。如果计数方式是 S01-S29 + A01 + S22a + S22b = 32 个条目；如果 S22a/S22b 是 S16-S22b 区间的子系统且计入 31，则 A01 是否计入 manifest hash 需要明确。

同时 manifest §5 写 `system_id_31 || version_31`，但 §1 的可见编号没有 S30/S31。`specs/core/01-tick-protocol.md` §3.4 又写 “Phase 2a inline 6 + Phase 2b deferred 25”，而 manifest 当前 Phase 2a 包含 S01-S06 加 A01（7 个条目）。

**证据**:
- `specs/core/06-phase2b-system-manifest.md` §1 标题 “31 systems”。
- `specs/core/06-phase2b-system-manifest.md` §5 manifest hash 示例到 `system_id_31`。
- `specs/core/01-tick-protocol.md` §3.4 写 “31 systems（Phase 2a inline 6 + Phase 2b deferred 25）”。
- `design/engine.md` §3.2 同样写 “Phase 2a inline 6 + Phase 2b deferred 25”。

**建议修复**:
- 明确定义计数口径：例如 “31 engine systems + 1 command dispatch pseudo-system A01” 或 “32 manifest entries”。
- 若 A01 参与 manifest hash，应更新所有 “31 systems / 6+25” 为一致口径。
- 若 A01 不参与 manifest hash，应声明它是 command loop dispatch contract，不是 ECS system，并从 schedule 图中移出 system count。

### M2 — `design/engine.md` 保留 `IndexMap` 作为确定性依据，和核心合同偏移

**严重级别**: Medium  
**影响**: 实现者可能继续依赖插入顺序作为确定性来源

`design/engine.md` §3.1 在 `Resource` 与 `Source` 结构中写 `IndexMap<String, u32>` 并注释 “IndexMap 保证迭代顺序确定”。但 `specs/core/01-tick-protocol.md` §7.1 要求 HashMap/Dictionary 使用 `BTreeMap`，`design/engine.md` §3.3 也写确定性键排序场景使用 `BTreeMap`，`IndexMap` 只用于插入顺序确定的资源类型。

这不是必然 blocker，但文档容易诱导实现者认为 IndexMap 本身足以保证跨 replay 确定性。实际上 IndexMap 只能保留插入顺序；若资源注册/插入来源未 canonicalize，仍会漂移。

**证据**:
- `design/engine.md` §3.1 `Resource.amounts: IndexMap<String, u32>` 注释 “保证迭代顺序确定”。
- `design/engine.md` §3.3 写需要确定性键排序的场景使用 `BTreeMap`，IndexMap 只用于插入顺序确定场景。
- `specs/core/01-tick-protocol.md` §7.1 写 HashMap/Dictionary 使用 `BTreeMap`。

**建议修复**:
- 修改 §3.1 注释为：“资源类型顺序来自 canonical ResourceRegistry；若来源不是 registry order，必须转为 BTreeMap/canonical sort 后参与 hash/replay。”
- 避免单句 “IndexMap 保证迭代顺序确定” 被理解为充分条件。

### L1 — FDB 故障注入测试示例断言变量/语义错误

**严重级别**: Low  
**影响**: CI 示例可读性 / 实现者复制错误测试

`specs/core/01-tick-protocol.md` §3.5.6 的测试示例中，`snapshot_checksum_before` 被声明为 immutable，但循环内更新；更重要的是，commit 失败时断言 `world.state_checksum() == snapshot_checksum_before`，而该变量表示“上一次成功 tick 后的基准 checksum”，不是当前 tick 开始时 `snapshot` 的 checksum。若 tick 内存在 deterministic pre-execute bookkeeping 或 snapshot 捕获后状态字段，示例会误导实现。

**证据**:
- `specs/core/01-tick-protocol.md` §3.5.6 `let snapshot_checksum_before = world.state_checksum();` 后续又赋值。
- 同节断言失败恢复后等于 `snapshot_checksum_before`，而不是 `snapshot.state_checksum()` 或 `snapshot_checksum_at_tick_start`。

**建议修复**:
- 改为 `let mut baseline_checksum = world.state_checksum();`。
- 每个 tick 开始时记录 `let snapshot_checksum = snapshot.state_checksum();`，commit 失败后断言恢复值等于 `snapshot_checksum`。
- commit 成功后再更新 `baseline_checksum = world.state_checksum()`。

## 建议修复优先级

1. **先修 H1**：这是最容易导致 engine 与 replay verifier 分叉的歧义。
2. **再修 H2**：TickCommitRecord 是 replay-critical，必须只有一种失败语义。
3. **随后修 M1**：统一 system count / manifest hash 口径，避免下一轮 CV 重复抓到。
4. **顺手修 M2/L1**：文档注释和测试示例级别，改动小。

## 总体判断

当前 R39 指定范围离 APPROVE 很近，但不建议直接通过。若 H1/H2/M1 修正并做一次窄范围 CV，预计可收敛到 **CONDITIONAL_APPROVE / APPROVE**。本轮主要风险不是缺少设计，而是同一设计在不同文档和同一文档不同段落中的表达仍未完全唯一。