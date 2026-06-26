# R35 Architect 独立评审报告 — rev-dsv4-architect

> **评审视角**: ECS 调度正确性、数据流一致性、算法复杂度和正确性。验证 tick pipeline 的确定性闭合、跨组件状态同步的正确性、持久化边界的完整性。追溯每个数据结构的生命周期。

---

## 1. Verdict

**CONDITIONAL_APPROVE**

架构骨架正确——确定性闭合完整、ECS 调度链清晰、持久化分层严谨、R/W 矩阵无竞争。发现 2 个 High 问题需修复、4 个 Medium 需关注、1 个 Low 建议。无 Critical 阻断项。总体设计可进入实现阶段，但以下问题应在实现前闭合。

---

## 2. 发现的问题

### [High] A-H1 — Refund credit deploy-reset 时序窗口
- **文件**: `specs/core/02-command-validation.md` §7.2
- **问题**: Refund credit 清零规则写作「若玩家在 tick N+1 执行了任何部署操作（`swarm_deploy` / `MCP_Deploy` / `Deploy`），tick N 及之前累计的 refund credit 清零」。但 deploy 状态机（`05-persistence-contract.md` §2.3）定义 MANIFEST_COMMIT 发生在 tick N，activation 在 tick N+1。按当前表述：
  - Tick N-1: 玩家累积 refund credits
  - Tick N: 玩家调用 `swarm_deploy`，manifest 提交
  - Tick N+1: 只发生了 **activation**（不是新的 deploy 操作），规则中的「执行了部署操作」不触发 → refund credits 未被清零 → 新模块带着旧模块累积的 refund credits 启动

  这产生一个跨模块 refund farming 窗口：v1 刷 refund → deploy v2 → v2 消费 v1 的 refund。

- **影响**: 反放大（anti-amplification）机制的核心保障——deploy 时清零 refund credits——存在一个 tick 级的时序缺口，允许跨模块 budget 转移。

- **修复建议**: 将清零触发点从「activation tick」改为「MANIFEST_COMMIT tick」。即：
  > 当 FDB deploy manifest 在 tick N 原子提交时，tick N-1 及之前累计的 refund credit 在 commit 成功的同一事务内清零。

  修复后时序：
  - Tick N-1: 累积 refunds
  - Tick N: `swarm_deploy` → MANIFEST_COMMIT → **同事务内 refund_credit = 0**
  - Tick N+1: activation，干净 credit 启动

### [High] A-H2 — Leech/Fabricate 缺独立校验小节
- **文件**: `specs/core/02-command-validation.md` §3.10–§3.15 vs §8 (CommandAction 变体)
- **问题**: 6 种原始特殊攻击（Hack/Drain/Overload/Debilitate/Disrupt/Fortify）在 §3.10–3.15 各有独立的结构化校验小节（包含：检查项/失败码表、效果描述、状态转换、冷却/资源消耗/抗性详细信息）。但 Leech 和 Fabricate 仅出现在 §8 的汇总表中，缺乏同等级别的详细校验规范。具体缺失：
  - Leech: 缺 `攻击者治疗量` 的精确计算验证（self-heal 50% of damage 应在哪个阶段计算？2a 校验时还是 2b apply 时？）
  - Fabricate: 缺 `5-tick channel` 的状态机描述（channel tick 1-5 各阶段目标行为，Disrupt 打断后残留状态）
  - 两者: 缺与 S22 `status_advance_system` 的交互合同（StatusState 数据结构定义）

- **影响**: 实现者需要通过交叉引用多个文档才能获得完整校验逻辑，增加了实现遗漏风险。8 种特殊攻击全部作为核心目标设计（R30 B1/D5），但文档一致性不完整。

- **修复建议**: 在 §3 中新增 `§3.17 Leech` 和 `§3.18 Fabricate` 小节，与 §3.10–3.15 同等格式——包含检查项/失败码表、效果/状态转换描述、冷却/资源消耗/抗性详情、与 S22 的交互合同。从 `special-attack-table.md`（api-registry.md 引用的权威参数表）提取参数填入。

### [Medium] A-M1 — Snapshot truncation 权威合同不在审查范围内
- **文件**: `design/engine.md` §3.4.4、`specs/core/01-tick-protocol.md` §2.3
- **问题**: 两份文件都将 snapshot truncation 的权威定义委派给 `specs/core/09-snapshot-contract.md`，而该文件不在本次审查文件集中。engine.md 声明「权威截断合同见 Snapshot Contract §1」，01-tick-protocol.md 声明「snapshot-contract 是 snapshot truncation 的唯一权威源」。
- **影响**: 无法从架构视角验证 truncation 算法（距离桶 + entity_id 字典序 + farthest-first + critical 保护）与 tick pipeline 的交互——如截断对 snapshot_hash 的影响、截断后的 WASM 行为合同、truncation 与 visibility filter 的集成。
- **修复建议**: 无需修改当前文件。标记为 CX 项——建议 Speaker 汇总时确保 09-snapshot-contract.md 在后续审查轮回中被覆盖，或确认其已被其他方向审查。

### [Medium] A-M2 — 「Parallel Set C」仅为单系统串行
- **文件**: `specs/core/06-phase2b-system-manifest.md` §1、§4
- **问题**: Manifest 定义「Parallel Set C: World Maintenance」包含仅 S24 `decay_system` 并以「serial within C」执行。一个只有单个串行系统的「parallel set」在架构上存在误导——暗示可扩展并行性但实际是历史遗迹。文档注释承认「Parallel Set C 简化为单一 serial system」但保留了 set 标签。
- **影响**: 低——不影响正确性。但会增加新贡献者的理解成本，可能被误解为「未来可在此插入并行系统」的架构预留。
- **修复建议**: 将 S24 `decay_system` 直接纳入 serial spine（S23 → S24 → S25），移除 Parallel Set C 标签。如确需保留架构预留意图，改为注释「S24: future parallelization candidate — currently serial」而非维持空 parallel set 结构。

### [Medium] A-M3 — 重试 refund 退还时序与「同一事务」语义
- **文件**: `specs/core/01-tick-protocol.md` §6.1 失败模式矩阵行 642 + §9.1 COLLECT 缓存说明
- **问题**: §6.1 行 642 声明 Phase 2a panic 时「已消耗 fuel 不退」。但 §9.1/§7.1 描述 FDB commit 失败（3 次重试后放弃）→「consumed_fuel[tick] 退还」。这两种场景的 fuel 退还语义不同（inline crash vs FDB fail），但 §6.1 矩阵中未区分「inline apply 失败」与「FDB commit 失败」的退款策略。阅读者需跨 §6.1、§7.1、§9.1 三段才能还原完整退款逻辑。
- **影响**: 实现者可能混淆两种失败场景的退款策略，导致 fuel 余额计算错误。
- **修复建议**: 在 §6.1 失败模式矩阵中新增一列「Refund」，对每个失败场景标注退款策略（全退/不退/部分退）。将分散在 §6.1、§7.1、§9.1 的退款逻辑集中于此列。

### [Medium] A-M4 — engine.md 与 spec 文档间的数值权威源声明分散
- **文件**: `design/engine.md` §3.4.2、`specs/reference/api-registry.md` §5
- **问题**: engine.md §3.4.2 声明「权威容量定义：所有容量上限和准入策略以 `specs/reference/api-registry.md` §5 为准」。但 api-registry.md §5 中 `MAX_FUEL`（10,000,000）仅在 engine.md §3.4.2 定义而不在 §5 表中。同样 `PER_CORE_FUEL_RATE`、`MIN_FUEL` 等派生参数只出现在 engine.md。两文档形成交叉依赖——各自声称对方是权威但自身持有独特数值。当数值需要更新时，实现者需同时修改两处，易产生不一致。
- **影响**: 运维调整参数时可能仅更新一处导致冲突。
- **修复建议**: 在 api-registry.md §5.2 中增补 `MAX_FUEL`（10,000,000）、`MIN_FUEL`（500,000）、`PER_CORE_FUEL_RATE`（~500M fuel/s）等 WASM 执行核心参数。engine.md 的容量推导段落保留为说明性叙述，但移除其中的「权威」声明——全部数值以 api-registry.md 为单事实源。

### [Low] A-L1 — deploy-reset 规则中「session_id」缺 tick 级定义
- **文件**: `specs/core/02-command-validation.md` §7.2
- **问题**: 「同一 session 内的迭代部署（同 session_id）不清除 credit」中的 `session_id` 无文档定义其生命周期边界。如果 session 跨多个 tick 且持续较长时间，此例外可被滥用——在一个长 session 内：deploy v1 → 长时间累积 refund → deploy v2 → 保留 refund。
- **影响**: 低——session 通常有自然时间边界。但缺少精确定义为未来实现留下歧义空间。
- **修复建议**: 明确 `session_id` 的生命周期边界——建议定义为「自上次 deploy MANIFEST_COMMIT 起、至下个 tick boundary 止」，或直接引用 `specs/reference/api-registry.md` 中 session 定义（若存在）。

---

## 3. 亮点

1. **确定性闭合完整**：shuffle seed 公式 `Blake3("shuffle" || world_seed || tick.to_le_bytes())`、per-entity stream seed、`command_hash` tiebreaker、BTreeMap 替代 HashMap——所有非确定性源被系统性地消除。`01-tick-protocol.md` §9.1 的 5 层排序键（`priority_class → shuffle_index → source_rank → sequence → command_hash`）是对确定性排序问题的教科书级解决方案。

2. **Shadow Write + Atomic Publish 持久化模型**（`01-tick-protocol.md` §3.5）设计精良。将「staging 行不是已提交状态」作为核心不变量，消除了旧模型中 per-room commit → 全局 abort 的时序窗口。GlobalTickCommit 作为唯一 publish 点，所有下游读取仅走 `/committed/` 路径——这是分布式系统中处理部分失败的典范模式。

3. **Phase 2a/2b 分类原则**（`engine.md` §3.2）清晰且有哲学立场：Phase 2a 处理依赖执行顺序的玩家命令（先到先得竞争有意义），Phase 2b 处理被动系统（有依赖关系串行、无数据竞争并行）。Attack/RangedAttack/Heal 只生成 `PendingDamage`/`PendingHeal` intent、S15 统一写入 HitPoints（R33 B7）的分离设计，消除了同 tick 内 Attack 顺序差异导致不同 HP 结果的非确定性。

4. **Status Effects 并行 buffer + 串行唯一 writer**（R30 B1，`06-phase2b-system-manifest.md` §1）的架构设计是 ECS 并行安全的最佳实践：S16-S22b 写入互不重叠的 typed buffer（`HackBuffer` ≠ `DrainBuffer` ≠ …），S22 作为唯一 StatusState writer 串行执行——并行无冲突、串行确定性强。

5. **Replay-critical subset 的显式分离**（`05-persistence-contract.md` §2.1）——TickCommitRecord 的 10 个字段必须在 FDB 事务中原子提交，RichTraceBlob 可降级/延迟/丢失。`terminal_state` enum（verified/audit_gap/unreplayable/reconstructable）为审计完整性提供了精确语义，避免了「blob 缺失 = 世界丢失」的错误假设。

6. **Move-as-action 设计理由**（`engine.md` §3.2 表）提供了清晰的确定性和游戏设计 trade-off 分析——不是简单的「我们决定这样做」，而是解释了为什么双动作模型在确定性系统中会产生顺序竞争，以及为什么编程游戏中的单 action slot 是战术深度而非限制。

---

## 4. CrossCheck

- **CX1: [A-H1 — refund deploy-reset 时序]** → 建议 **Speaker** 检查该修复是否影响 FDB 事务设计（同事务内清零 refund credit 是否会增加事务冲突概率），以及是否需要在 TickCommitRecord 中新增 `refund_credit_reset` 字段用于 replay 验证。

- **CX2: [A-M1 — snapshot-contract 审查覆盖]** → 建议 **Speaker** 确认 `specs/core/09-snapshot-contract.md` 是否已被其他方向审查，或其是否应在 R35 后续 Phase 中被排入审查文件集。Architect 无法在缺失该文件的情况下验证 truncation → tick pipeline 的集成正确性。

- **CX3: [A-H2 — Leech/Fabricate 校验标准]** → 建议 **Gameplay Reviewer** 检查 `special-attack-table.md` 中 Leech/Fabricate 的权威参数是否已定义完整（damage、heal ratio、channel time、cooldown、cost、resistance），确保 A-H2 修复时可直接引用而不需重新设计参数。

- **CX4: [A-M4 — 容量数值权威源分散]** → 建议 **Speaker** 确认 engine.md §3.4.2 与 api-registry.md §5 之间的权威源声明是否需要全局统一——当前存在双向交叉引用（engine → registry, registry 缺某些值回到 engine）。建议裁定「api-registry.md 为全部容量参数的唯一权威源，engine.md 仅保留推导说明」作为全局文档约定。

- **CX5: [R/W Matrix HitPoints 写入者标注]** → 建议 **ECS Reviewer** 检查 S10 regen、S15 dmg_apply、S22 status_adv 三个 HitPoints 写入者之间的交互——虽然串行执行保证无竞争（S10→S15→S22），但 CI Unique Writer 检测需放宽至允许「多个 writer 但时序不重叠」的语义。建议在 `06-phase2b-system-manifest.md` §4 的 HitPoints 列将「W」升级为「W†（serial domain）」或类似标记，避免 CI 误报。

---

## 附录：已核验的一致性项目

以下项目经交叉比对确认一致，无需修改：

| # | 项目 | 跨文档验证 |
|---|------|-----------|
| CC1 | 31 system 计数 | engine.md (6+25) = manifest.md (S01-S29 逐项计数) = 01-tick-protocol.md §9.6 = 31 ✅ |
| CC2 | MAX_FUEL = 10,000,000 | engine.md §3.4.2 = 04-wasm-sandbox.md §6 = 01-tick-protocol.md §8.2 ✅ |
| CC3 | Per-player drone cap = 50 | engine.md §3.4.2 = api-registry.md §5.1 ✅ |
| CC4 | Pathfinding budget = 100,000 | engine.md §3.4.2 = api-registry.md §5.2 = api-registry.md §5.6 ✅ |
| CC5 | WASM linear memory = 64MB / cgroup = 128MB | 04-wasm-sandbox.md §1 + §2.2 = api-registry.md §5.2 ✅ |
| CC6 | Tick interval = 3000ms World | engine.md §3.4.1 = 01-tick-protocol.md §8.1 ✅ |
| CC7 | Worker pool max = 256 | engine.md §3.4.2 = api-registry.md §5.5 ✅ |
| CC8 | Keyframe interval K=100 | 05-persistence-contract.md (implied) = api-registry.md §5.4 ✅ |
| CC9 | Direction4 枚举值 | api-registry.md §7 = 02-command-validation.md §3.1 ✅ |
| CC10 | Shuffle seed 公式 | engine.md §3.2 = 01-tick-protocol.md §3.1 ✅ |
| CC11 | SpawningGrace 在 combat 之前 | engine.md §3.2 = manifest.md §1 = 01-tick-protocol.md §3.4 ✅ |
| CC12 | Regeneration 在 damage_application 之前 | manifest.md §1 = 01-tick-protocol.md §3.4 ✅ |