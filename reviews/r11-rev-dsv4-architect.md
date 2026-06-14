# R11 架构评审报告 — Architect Reviewer (DeepSeek V4 Pro)

**评审日期**: 2026-06-14
**评审范围**: DESIGN.md (1463L) + tech-choices.md (223L) + ROADMAP.md (212L) + specs/p0/* (9份)
**评审维度**: ECS调度正确性 | Tick生命周期完整性 | 数据一致性(FDB+Dragonfly) | 算法复杂度
**上轮参考**: R10 rev-dsv4-architect — 3个D1、4个D2、2个D3、2个CG、2个AR

---

## Verdict: APPROVE_WITH_RESERVATIONS

**R10 的 3 个 D1 阻断项全部修复。** Phase 1 架构基础已满足最低条件。本轮新发现 4 个 D2 和 2 个 AR，均为 Phase 2（多人+MCP）实现前需解决的设计深度问题。R10 的 2 个 D3 和 1 个 CG 仍然存在但不阻断 Phase 1。

---

## R10 D1 阻断项 — 修复验证

| R10 ID | 描述 | 状态 | 验证位置 |
|--------|------|------|---------|
| D1-1 | `Source.produces` 使用 HashMap | ✅ **已修复** | DESIGN.md §3.1: `produces: IndexMap<String, u32>` — 与 Resource.amounts 统一为 IndexMap。全量 HashMap 审计通过（Resource/Source 均已改造） |
| D1-2 | Wasmtime 版本锁定 vs 安全SLA 矛盾 | ✅ **已修复** | P0-1 §6.3.3: 「TickTrace 始终记录 Command[] 而非 WASM 输出。回放时引擎直接执行已记录的指令序列，不重新调用 WASM。Wasmtime 版本变更不影响回放。」— 方案 C 落地，Wasmtime 升级不再破坏回放 |
| D1-3 | COLLECT 读取源未定义 | ✅ **已修复** | P0-1 §2.3: 「all_entities 来自 Bevy World 内存（当前 tick 执行前的权威状态）。不从 FDB/Dragonfly 读 —— COLLECT 阶段不访问外部存储。」+ P0-1 §6.3.4 Tick Boundary Contract 明确定义了 Bevy World ↔ FDB 关系 |

**D1 清零。** Phase 1 无架构级阻断。

---

## R10 D2/D3/CG/AR 遗留状态

| R10 ID | 描述 | 状态 | R11 处置 |
|--------|------|------|---------|
| D2-1 | Rhai "mini-validator" 未定义 | ❌ 未修复 | → R11 D2-1（维持严重度） |
| D2-2 | Drone lifespan reset 无冷却 | ⚠️ 部分修复 | 新增 500 tick/玩家冷却。但双人 ping-pong 仍可绕过 → 不升级，见 Strengths.5 |
| D2-3 | EXECUTE 超时处理缺失 | ❌ 未修复 | → R11 D2-2（新分析） |
| D2-4 | PLANNER-OUTPUT.md 过时 | ✅ 已删除 | 文件已从 docs/ 移除 |
| D3-1 | 特殊攻击+伤害类型无 P0 规范 | ❌ 未修复 | Phase 6 功能，不阻断 Phase 1 |
| D3-2 | Transfer cost 字段语义歧义 | ❌ 未修复 | 低优先级，Phase 2 实现时澄清 |
| CG-1 | host_get_world_rules 从 P0-4 §3.2 缺失 | ⚠️ 部分修复 | P0-4 §8 cost 表已含，但 §3.2 白名单仍缺失 → R11 CG-1 |
| CG-2 | TickTrace 写入失败场景矛盾 | ❌ 未修复 | R11 CG-2（文档一致性问题） |
| AR-1 | Snapshot 序列化 O(P×E) | ⚠️ 部分修复 | P0-1 §2.3 新增「按房间序列化一次，再按玩家过滤」，但未量化内存预算 |
| AR-2 | Tick 放弃无指数退避 | ❌ 未修复 | Phase 2+ 优化项 |

---

## D2 (高优先级 — 应在 Phase 2 前解决)

### D2-1: Rhai "mini-validator" 规范完全缺失 — 跨层状态修改无合同

**位置**: DESIGN.md §8.7 (Rhai API) + P0-7 §1

**问题描述** (R10 遗留):

DESIGN.md §8.7 将 Rhai actions 描述为「世界修改（通过 actions，不进命令管线但经 mini-validator）」。P0-7 未定义 mini-validator 的任何细节。

R10 指出此问题后无变化。当前缺口：

1. **校验规则未定义**: `actions.deduct_resource` — 余额不足时是部分扣减、拒绝、还是 panic？`actions.damage_entity` — 实体已被 WASM command 在本 tick 杀死后调用怎么办？
2. **Rhai ↔ WASM 冲突未定义**: tick_end.rhai 调用 `deduct_resource(player_A, "Energy", 5000)`，同时 player_A 的 WASM 指令在 EXECUTE 阶段消耗了 4800 Energy。谁先执行？哪个生效？
3. **Rhai mod 间冲突无排序**: 两个 mod 的 tick_end 各自 deduct 同一玩家的资源。执行顺序决定谁会遇到余额不足。P0-7 §3 的 `register_mod_systems` 代码按声明顺序迭代 `world_config.mods` 注册，但未声明这是确定性的（依赖迭代顺序 — 如果是 HashMap 则非确定）。
4. **`set_entity_flag` 的白名单在哪**: DESIGN.md §8.7 说明 `set_entity_flag` 只能设置白名单标记（slow/empowered），但白名单枚举从未在任何文档中定义。如果 Rhai 作者传入任意字符串 flag 怎么办？

**影响面**: Rhai 模组虽是「服主信任」的，但信任不等于放任绕过所有校验。没有 mini-validator 意味着错误的模组可以：损坏实体引用（dead entity）、触发负值资源（underflow panic 在 deduct 时）、或与 WASM 指令产生未定义交叠。这与「引擎核心不可变」的哲学不一致——模组代码的错误不应导致引擎 panic。

**修复建议**:
1. P0-7 新增 §9 "Rhai Action Validator Specification"，为每个 action 定义：
   - 前置条件（实体存在、资源充足、value 合法）
   - 拒绝行为（返回错误码 vs 静默跳过 vs 截断到合法值）
   - 与 WASM Command 的冲突处理（Rhai 先于 Command、后于 Command、还是同事务冲突则 Rhai 优先？）
2. 声明 mod 执行顺序 = world.toml 中 `[[mods]]` 的声明顺序（文档化，非实现细节）
3. 定义 `set_entity_flag` 合法 flag 枚举并在 P0-7 中列出

**严重度**: D2。核心架构正确（三层信任模型清晰），但第二层（Rhai）的边界合同缺失。在 Phase 3（Rhai 模组上线）前必须解决。不阻断 Phase 1。

---

### D2-2: EXECUTE 阶段 Rhai 钩子的精确插入位置未指定

**位置**: DESIGN.md §3.2 + §8.7 + P0-1 §3.3 + P0-7 §3

**问题描述** (新发现):

R10 D2-3 关注的是 EXECUTE 时间超时后的部分完成策略。本轮发现更精确的问题：**Rhai 钩子在 EXECUTE 链中的位置影响 WASM 命令的校验正确性。**

当前文档的合并状态：
- DESIGN.md §3.2: EXECUTE = 指令排序 → 逐条校验执行 → ECS systems → FDB commit
- P0-1 §3.3: ECS chain = build → harvest → regeneration → movement → combat → decay → death → spawn
- DESIGN.md §8.7: `tick_start.rhai`（每 tick 开始时执行）+ `tick_end.rhai`（每 tick 结束时执行）
- P0-7 §3: `register_mod_systems` 把 tick_end 注册为 `.after(death_system)`

**tick_start.rhai 的位置完全未指定。** 可能的插入点：

| 插入点 | WASM 命令校验的后果 |
|--------|-------------------|
| 在 EXECUTE 开始、排序前 | Commands 在 COLLECT 阶段基于 pre-tick_start 的 snapshot 生成。tick_start 修改了世界（如 deduct_resource），导致命令校验时世界与 WASM 决策时的世界不一致 → 「假阳性拒绝」飙升 |
| 在排序后、命令执行前 | 同上 |
| 在命令执行后、ECS systems 前 | tick_start 的 deduct_resource 先看到 WASM 命令的效果——会计正确，但 tick_start 的「每 tick」语义变模糊 |
| 在 ECS systems 后、tick_end 前 | tick_start 的「每 tick 开始时」语义被违反 |

**设计意图推断**: tick_start.rhai 应该在 COLLECT 之前运行——改变世界状态后让 WASM 玩家在 snapshot 中看到新状态。但这要求 tick_start 在 COLLECT 阶段而非 EXECUTE 阶段执行。当前 Tick Protocol 未设计此钩子。

**修复建议**:
1. 在 P0-1 状态机中明确定义 Rhai 钩子插入点
2. 方案 A（简单）: tick_start → COLLECT（新 snapshot）→ 排序 → 命令执行 → ECS → tick_end → FDB commit
3. 方案 B（保守）: COLLECT（基于上一 tick 结束状态）→ tick_start → 命令执行 → ECS → tick_end → FDB commit（tick_start 修改不影响 snapshot，但影响命令校验）

**严重度**: D2。不阻断 Phase 1（单玩家无需此机制），但在 Phase 2 多玩家 + Phase 3 Rhai 模组时必须确定。

---

### D2-3: 多 Rhai 模组执行顺序的确定性未声明

**位置**: P0-7 §3 (ECS Plugin 注册) + DESIGN.md §8.8 (Determinism Contract)

**问题描述** (新发现):

P0-7 §3 的 `register_mod_systems`:
```rust
for mod_def in &world_config.mods {
    let tick_end = module.tick_end_script.clone();
    app.add_systems(Update, move |world: &mut World| {
        // ...
    }.after(death_system));
}
```

两个关键问题：

1. **world_config.mods 的迭代顺序**: 如果 `mods` 是 `Vec`，顺序确定。如果从 TOML 解析，`[[mods]]` 数组的迭代顺序是声明顺序——这需要显式文档化。P0-7 未提顺序保证。

2. **多个 `.after(death_system)` 之间的顺序**: Bevy 中同样 `.after()` 的系统之间顺序**未定义**。如果 mod-a 和 mod-b 都 `.after(death_system)`，它们可能以任意顺序执行。两个 mod 各自调用 `deduct_resource` 时，执行顺序决定哪个先耗尽资源。

**影响面**: 两个 Rhai mod 产生不同交互结果取决于不可见的执行顺序 → 破坏回放确定性 → 违反 Determinism Contract。

**修复建议**:
1. P0-7 声明 `[[mods]]` 的执行顺序 = world.toml 中的声明顺序（文档化这是确定性要求）
2. 多个 mod 的 tick_start / tick_end 通过 `.chain()` 强制排序
3. 在 Determinism Contract 中补充：「Rhai 模组执行顺序由 world.toml 声明顺序确定，是回放合同的一部分」

**严重度**: D2。Phase 1 无 mod，不影响。Phase 3 前必须解决。

---

### D2-4: Drone lifespan reset 冷却机制存在双人 ping-pong 绕过

**位置**: DESIGN.md §8 (Drone 生命周期)

**问题描述** (R10 D2-2 遗留，部分修复):

R10 指出全局 age reset 可被滥用维持永久 drone。R11 新增了冷却机制：
> 「冷却: 同一玩家 500 tick 内只能触发一次续期（防 ping-pong 滥用）」

**绕过路径**: 冷却作用域是**玩家级别**而非**Controller 级别**。两个合作玩家可以：
1. Player A 占领 Controller-1 → A 的 drone 全部 reset → A 进 500 tick 冷却
2. 100 tick 后 Player B 占领 Controller-1 → B 的 drone 全部 reset → B 进 500 tick 冷却
3. 500 tick 后 Player A 重新占领 Controller-1 → A 的 drone 再次 reset
4. 循环往复 → 两玩家的 drone 每 ~600 tick 刷新一次，远超 1500 tick lifespan

**严重度**: D2（原为 D2，未降级）。冷却机制的加入缓解了单人滥用，但双人合谋路径仍然开放。方案 A（仅重置该房间内 drone 的 age）+ 方案 B（每 Controller 级冷却）结合可彻底封堵。

---

## D3 (低优先级 — 可延后至 Phase 3+)

### D3-1: 特殊攻击与伤害类型体系未进入 P0-8 IDL

**位置**: DESIGN.md §8（特殊攻击方式、伤害类型）vs P0-8 IDL

**状态**: R10 D3-1 遗留，无变化。P0-8 IDL 的 Attack/RangedAttack 无 `damage_type` 字段。6 种特殊攻击（Hack/Drain/Overload/Debilitate/Disrupt/Fortify）无 Command 定义。Phase 6 功能应在 IDL 中留占位符。

**建议**: P0-8 IDL 中添加 `damage_type: Kinetic`（默认）+ status:phase6 注释。不阻断 Phase 1。

---

### D3-2: Transfer/Withdraw 的 cost 字段语义仍然模糊

**位置**: P0-8 IDL commands section

**状态**: R10 D3-1 (now D3-2) 遗留。`cost: { transfer_amount: amount }` 的语义是「资源流动」还是「额外手续费」仍未澄清。P0-2 §3.4 的 Transfer 校验没有资源消耗检查，暗示是纯流动（无手续费），但 cost 字段的命名造成歧义。

**建议**: 如果无手续费，改为 `cost: {}`。不阻断 Phase 1。

---

## Consistency Gaps (跨文档一致性)

### CG-1: `host_get_world_rules` 仍在 P0-4 §3.2 白名单之外

**位置**: P0-4 §3.2 vs P0-4 §8 vs P0-8 IDL

R10 指出此问题后，P0-4 §8（Query Host Function 成本表）已补上 `host_get_world_rules | 1,000 | 16 KB`。但 **§3.2（「允许的 Host Function（查询专用，只读）」）** 仍然只列出 4 个函数：get_terrain、get_objects_in_range、path_find、get_world_config——缺少 get_world_rules。

**后果**: §2.4 的模块校验代码遍历 `module.imports()` 并对照 `ALLOWED_HOST_FUNCTIONS` 白名单。如果此白名单基于 §3.2 构建，导入 `host_get_world_rules` 的 WASM 模块将被拒绝为 `IllegalImport`——但 DESIGN.md §5.1 和 P0-8 IDL 都声明它是合法 host function。

**修复**: 在 P0-4 §3.2 中添加 `fn host_get_world_rules(out_ptr: i32, out_len: i32) -> i32;`，确保 §2.4 模块校验的 `ALLOWED_HOST_FUNCTIONS` 与 §3.2 完全一致。

---

### CG-2: TickTrace 写入失败作为独立场景的文档逻辑矛盾

**位置**: P0-1 §6.1 vs §3.4 vs §6.3.1

R10 指出此问题后无变化。

- P0-1 §6.1 将 "TickTrace write fail (磁盘满)" 列为独立失败模式，与 "FDB commit fail" 分开
- P0-1 §6.3.1: TickTrace 数据 (`/tick/{N}/commands`、`/tick/{N}/state`、...) 全部写入 FDB
- P0-1 §3.4: 整个 EXECUTE 包裹在单个 FDB 事务中

→ 这三个语句逻辑上互斥：如果 TickTrace 写入 FDB 且整个 EXECUTE 是一个 FDB 事务，则 TickTrace 写入失败必然导致整个事务失败（tick abandoned），不可能存在"tick 已完成但 TickTrace 写入失败"的独立场景。

**修复**: 合并 "TickTrace write fail" 到 "FDB commit fail"，或将其重新解释为 ClickHouse audit log 写入失败（此时是独立场景）。

---

## Algorithmic Risks (算法风险评估)

### AR-1: ECS 系统并行化的数据依赖分析缺失

**位置**: DESIGN.md §8.8 + P0-1 §3.3 + ROADMAP §7.1

**问题描述**:

DESIGN §8.8 和 P0-1 §3.3 都提到未来用 `.before()/.after()` 替代部分 `.chain()` 实现并行优化，ROADMAP §7.1 将此作为 Phase 7 交付物。但**没有任何文档分析 ECS 系统之间的数据依赖**——哪些系统可安全并行、哪些必须串行。

当前 ECS 链的数据依赖（初步分析）：
```
build_system        → 写 Position(新建筑)
harvest_system      → 读 Source, 写 Resource + Drone
regeneration_system → 写 Source.ticks_to_regeneration + Source.produces  ← 与 harvest 冲突！
movement_system     → 写 Position                             ← 可能与 combat 的读 Position 冲突
combat_system       → 读 Position, 写 hits
decay_system        → 写 fatigue/cooldown
death_system        → 读 hits, 写 Entity(despawn)
spawn_system        → 读 Spawn, 写新 Entity
```

关键冲突对：
- **harvest ↔ regeneration**: 都访问 Source。如果并行且 harvest 在 regeneration 之前从 produces 读取旧值，或 regeneration 在 harvest 之后覆盖 ticks_to_regeneration → 丢失更新。
- **movement ↔ combat**: movement 写 Position，combat 读 Position 判定攻击范围。如果并行且 combat 先读（旧位置）而 movement 后写（新位置）→ 攻击判定基于旧位置。
- **decay ↔ combat**: decay 减 fatigue，combat 读 fatigue。并行可能导致 combat 基于未衰减的旧值。

**建议**: 在 P0-1 或独立的性能规范中提供 ECS 系统数据依赖矩阵。Phase 7 进行并行优化时以此为基础。不阻断 Phase 1。

---

### AR-2: 500 玩家 COLLECT 阶段的进程 fork 爆炸

**位置**: P0-1 §2.1 + P0-4 §1

**问题描述**:

P0-4 §1 规定 sandbox worker 的生命周期是「每 tick fork → 执行 → kill」。每个玩家需要一次独立的进程 fork。

500 活跃玩家 × 每 3s 一次 fork/kill 循环：
- `fork()` 系统调用本身 ~0.5-2ms（取决于进程内存大小）
- 500 次 fork ≈ 250-1000ms，可能吞噬 10-40% 的 COLLECT 预算
- Wasmtime `Module`（编译后的机器码）在 fork 时通过 CoW 共享，但 Wasmtime `Engine`（JIT 编译元数据）可能不是完全 CoW 友好的
- 连续 fork/kill 500 个子进程触发 OOM killer 的风险（cgroup memory.max 128MB × 500 = 64GB — 实际 CoW 大幅减少，但峰值难以预测）

**建议**: 考虑 sandbox worker 进程池方案（预 fork N 个 worker，每 tick 复用而非 fork/kill）。或定量 benchmark fork 开销并在 P0-1 中声明最大支持玩家数对应的 fork 预算。Phase 2（多玩家）之前应有压力测试数据。

---

## Strengths (设计亮点 — 不应改动)

1. **Deferred Command Model 一致性**: DESIGN.md + P0-2 + P0-4 三处对「WASM → tick() → JSON → 引擎校验执行」的约束完全一致。零个 mutating host function 例外。架构原则贯穿始终。

2. **MCP 不作为游戏控制器**: P0-3 §4.5 明确定义 MCP 不包含任何游戏动作工具——AI 必须写 WASM。与人类完全同权。"MCP is a management/monitoring interface, NOT a gameplay channel" — 设计哲学正确。

3. **Fuel Refund 防滥用三层防护**: 退还时序（下 tick 生效）+ Deploy-reset 绑定（模块变更作废）+ 同源重复不退。堵住了所有退款循环利用路径。P0-2 §7.2 的 Deploy-reset 规则设计精妙。

4. **Blake3 统一原语**: 哈希/PRNG/代码签名统一为 Blake3，依赖栈减 30%，审计面减半。`update_with_seek(seed, offset)` 一行代码替代 ChaCha keystream 管理。

5. **Drone lifespan + 扩张续期机制**: 「占领新 Controller → 全体 drone age 重置」是优雅的策略激励——鼓励扩张而非龟缩。500 tick 冷却的加入提升了滥用门槛（尽管双人 ping-pong 仍存在，但需要两个共谋玩家，实操成本显著提高）。

6. **Wasmtime 回放策略决策**: P0-1 §6.3.3 的方案 C（记录 Command[] → 回放不重调 WASM）是一次正确且勇敢的架构决策。解决了「安全版本升级 vs 回放兼容性」的根本矛盾。

7. **P0-9 Command Source Model**: 12 来源 × 完整能力矩阵，auth context 服务端注入不可伪造。Source Gate 在 Command Validation Pipeline 之前过滤——纵深防御正确。

8. **Tick Boundary Contract**: P0-1 §6.3.4 清晰定义了 Bevy World（每 tick 工作副本）与 FDB（持久化权威源）的关系。消除了 R9 最大的架构模糊点。

---

## 总结

| 类别 | 本轮新 | R10 遗留 | 合计 | Phase 1 阻断 |
|------|--------|---------|------|-------------|
| D1 阻断 | 0 | 0 | **0** | 无 |
| D2 高优 | 3 (D2-2/3/4) | 1 (D2-1) | **4** | 否 — Phase 2-3 前解决 |
| D3 低优 | 0 | 2 (D3-1/2) | **2** | 否 — 可延后 |
| 一致性缺口 | 1 (CG-1) | 1 (CG-2) | **2** | 否 — 文档修复 |
| 算法风险 | 2 (AR-1/2) | 0 | **2** | 否 — 监控+优化 |

**R10 → R11 变化**: D1 从 3→0（全部修复）。D2 从 4→4（2个修复/删除，2个遗留，3个新发现）。一致性缺口从 3→2（1个修复/删除）。算法风险从 2→2（2个部分缓解但需进一步分析）。

**Phase 1 可开始**: 是。R10 的 3 个 D1 阻断项均已解决。当前 D2 项均为 Phase 2-3 的设计深化需求，可在 Phase 1 实现过程中并行推进。

**Phase 2 前需解决的最小集**:
1. D2-1 (Rhai mini-validator) — P0-7 补充完整规范
2. D2-2 (Rhai 钩子插入位置) — P0-1 状态机中定义
3. D2-3 (Rhai mod 执行顺序确定性) — P0-7 声明
4. CG-1 (host_get_world_rules 白名单) — P0-4 §3.2 补全

---

*评审完成于 2026-06-14 | DeepSeek V4 Pro | rev-dsv4-architect profile*
*R11 — 第二轮完整架构评审*
