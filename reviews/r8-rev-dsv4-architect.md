# R8 — 架构评审 (Architect Review)

**评审员**: rev-dsv4-architect (DeepSeek V4 Pro — 架构评审员)
**日期**: 2026-06-14
**评审范围**: DESIGN.md + tech-choices.md + ROADMAP.md + specs/p0/* (9 份 P0 规范)
**评审视角**: ECS 调度正确性 / Tick 生命周期完整性 / 数据一致性 (FDB+Dragonfly) / 算法复杂度

---

## VERDICT: CONDITIONAL_APPROVE

设计架构清晰、一致性好、技术选型理由充分。9 项 Concern 中 1 项 HIGH（文档冲突）、4 项 MEDIUM、4 项 LOW。HIGH 项需在 Phase 1 实现前修正，MEDIUM 项需在对应阶段实现前决议，LOW 项为优化建议。

---

## STRENGTHS (架构亮点)

1. **单一执行器模型 (WasmSandboxExecutor) 贯彻彻底**。P0-3 明确 MCP 不做 gameplay command，P0-9 的 Source Gate 将所有非 WASM 来源的 gameplay 指令在管线入口处拦截。这是整个安全模型的基石，文档链完整。

2. **Seeded Shuffle 指令排序方案优雅**。P0-1 §3.1 用 Blake3 XOF 从 `(tick_number || world_seed)` 派生确定性随机序列，同时满足确定性（相同输入 → 相同输出）和公平性（长期期望均等）。Fisher-Yates 实现选择正确。

3. **Fuel Refund 时序安全模型设计精良**。P0-2 §7.2 将退还的 fuel 作用域限制到下一 tick，禁止同 tick 内计算放大。配合退还上限 (MAX_FUEL × 10%)、同源重复失败去重、连续高退还率 throttle 三层防护，有效阻断 refund farming。

4. **Deferred Command Model 与 Determinism Contract 对齐严密**。P0-4 §3 禁止 imperative host functions，所有状态变更通过 `tick() → JSON` 返回，由引擎统一校验和应用。加上禁用 f64、禁用 std::hash、锁定 IndexMap、ECS `.chain()` — 确定性保证链路无缺口。

5. **可见性策略单点执行**。P0-5 的 `is_visible_to(entity, player_id, tick)` 作为唯一入口，覆盖 snapshot / MCP / WS / REST / replay 全部输出面。缓存策略 (`(tick, player_id) → HashSet<EntityId>`) 消除了「快照说隐藏但 WS 增量泄露」类 bug 的可能性。

6. **全局存储三层反制机制** (累进税/隐匿性/运输时间) 有效防止经济垄断。运输时间不可为 0 的约束（`transfer_to_global_time` / `transfer_from_global_time`）杜绝瞬移补给。PvP 世界中的运输拦截（Phase 6）增加了策略深度。

7. **技术选型理由链完整**。tech-choices.md 对每个组件给出了备选方案矩阵 + 淘汰理由 + 选择理由。Blake3 单原语覆盖哈希/PRNG/代码签名三项需求，减少依赖栈、降低审计面 — 这是成熟的工程判断。

---

## CONCERNS

### D1 [MEDIUM] ECS combat_system 作用域模糊

**位置**: P0-1 §3.3, P0-2 §3.7–3.9, DESIGN.md §3.2

**问题**: Tick 生命周期中，「应用指令」阶段直接修改 HP（Attack/RangedAttack/Heal 指令在校验通过后立即扣血/加血），而 ECS chain 中又有 `combat_system`。两者对同一实体作用的时间差和语义边界未界定：

- Command 应用发生在 EXECUTE 阶段的开头（"对每条指令...应用变更"）
- ECS `combat_system` 在 `.chain()` 中位于 movement_system 之后、decay_system 之前

如果 `combat_system` 处理的是「与指令无关的被动战斗效果」（如 tower 自动攻击、DOT、AoE），需在规范中明确声明其作用域，否则实现时容易出现 HP 被两次扣除的 bug（一次来自 command application，一次来自 combat_system）。

**建议**: 在 P0-1 §3.3 中为 `combat_system` 添加注释，声明其仅处理 passive/periodic combat effects，不处理已通过 command 结算的攻击。

---

### D2 [LOW] Drone `age` 递增缺失

**位置**: DESIGN.md §3.1, P0-1 §3.3

**问题**: Drone 结构体有 `age: u32` 字段，`death_system` 在 `age >= lifespan` 时回收。但没有任何文档说明 `age` 何时递增。可能的实现位置：
- 在 `decay_system` 中统一递增
- 在 `death_system` 中检查前递增
- 独立 `aging_system`

无论哪种方案，`age` 递增必须在 `death_system` 之前、`spawn_system` 之后（新 drone age=0 不应在当前 tick 被杀死）。当前 chain 为 `decay → death → spawn`，如果 age 递增在 decay 中，death 检查是正确的。但需要明确文档化。

**建议**: 在 P0-1 §3.3 的 ECS chain 注释中添加 `aging_system`（独立或合并于 decay），明确递增时机。

---

### D3 [HIGH] FDB 原子提交阶段归属冲突

**位置**: P0-1 §3.4 vs DESIGN.md §3.2

**问题**: 两个文档对 FDB 提交发生在哪个阶段给出矛盾描述：

- **P0-1 §3.4**: "整个阶段二包裹在 FoundationDB 事务中" → FDB commit 发生在 EXECUTE 阶段
- **DESIGN.md §3.2** (Tick 生命周期图): BROADCAST 阶段 → "FDB 原子提交（全或无）" → FDB commit 发生在 BROADCAST 阶段

这对架构有本质影响：
- 若 commit 在 EXECUTE：BROADCAST 失败不影响世界状态（P0-1 §4.2 的 "BROADCAST failure never rolls back committed tick" 成立）
- 若 commit 在 BROADCAST：BROADCAST 的任何组件失败（Dragonfly 写入失败、NATS 发布失败）可能导致已执行 tick 回滚

P0-1 §6.1 的失败矩阵支持「commit 在 EXECUTE」的语义（Dragonfly miss 不影响 tick、NATS fail 只是客户端未收到）。**P0-1 是正确的，DESIGN.md §3.2 需要修正。**

**建议**: 修正 DESIGN.md §3.2 Tick 生命周期图的 BROADCAST 阶段，将 "FDB 原子提交" 移至 EXECUTE 阶段末尾。

---

### D4 [MEDIUM] Tick 三阶段时间预算存在间隙

**位置**: P0-1 §2, §3, §5

**问题**: 
- Phase 1 (COLLECT) 硬截止: 2500ms
- Phase 2 (EXECUTE) 硬截止: 500ms
- Phase 3 (BROADCAST): 无明确超时
- Tick 目标间隔: 3000ms
- P99 警告阈值: 2800ms

当 Phase 1 接近 2500ms 且 Phase 2 接近 500ms 时，Phase 3 剩余时间为 0ms，必然突破 3s 目标。Phase 3 包含：(1) 增量计算 (2) Dragonfly 更新 (3) NATS 发布 — 在 500 玩家规模下这三步需要 50–200ms。

实际上 P0-1 的 2500ms 是硬截止而非预算 — 正常情况 Phase 1 可能只需 1–1.5s。但在降级/高负载场景下，COLLECT 超时比例上升，预算会自然收紧。当前设计依赖「正常情况 Phase 1 远低于 2500ms」的隐含假设，但未建模三阶段总时长的约束关系。

**建议**: 在 P0-1 §5 的 Tick 健康指标中增加 `tick_phase1_duration_p50/p99` 和 `tick_phase3_duration_p99`，并在 §2 中明确声明：Phase 1 超时 + Phase 2 超时 + Phase 3 预估耗时应 ≤ 2800ms，若 COLLECT 超时率上升触发自适应 COLLECT timeout 缩减。

---

### D5 [MEDIUM] Dragonfly 缓存过时检测机制缺失

**位置**: P0-1 §4.2, DESIGN.md §6.2

**问题**: P0-1 §6.1 的失败矩阵只覆盖了 "Dragonfly cache miss"（未命中）和 "Dragonfly cache stale"（版本落后）。对于 stale 场景，文档声明 "FDB 为权威源" 和 "下次写入时自动刷新" — 但未说明**读取方如何检测过时**。

实际场景：Dragonfly 写入成功（tick N），但后续某个读取者（快照构建、MCP 查询、REST API）在 tick N+1 时读到的是 tick N-1 的旧数据（Dragonfly 内部复制延迟 / 主从切换 / 网络分区恢复后）。如果没有数据版本号比对，读者无法知道数据已过时。

**建议**: Dragonfly 中每个 tick 状态写入时附带 `tick_number` 字段。所有读取操作校验返回的 `tick_number >= expected_tick`。不匹配 → 回退到 FDB 直读。

---

### D6 [LOW] COLLECT 阶段快照数据源未显式锁定

**位置**: P0-1 §2.3, §4.2

**问题**: P0-1 §2.3 的快照构建函数接受 `all_entities` 参数但未说明来源。P0-1 §4.2 说 "Read committed tick result from in-memory post-commit state or FDB versionstamp" — 这是 BROADCAST 阶段的读取。COLLECT 快照的数据源应该是同一份 post-commit state（刚刚 commit 的 tick N-1 最终状态），而不是 Dragonfly 缓存。

Phase 1 开始时的 `all_entities` 应明确声明来源为引擎内存中的 `WorldState`（即上一 tick commit 后的 in-memory 副本），不能走 Dragonfly。

**建议**: 在 P0-1 §2.3 的 `build_snapshot` 函数注释中添加数据源声明。

---

### D7 [LOW] Fisher-Yates 洗牌的模偏差

**位置**: P0-1 §3.1

**问题**: 洗牌使用 `XOF.read_u64() % (N - i)` 选择位置。当 N 较大时（虽然 500 玩家下 `2^64 % N` 偏差 < 10^-15），严格确定性系统中仍可记录。对 CPU player 场景 N 可能仅为 2–10，偏差 < 10^-18。

**实际影响**: 无。但「确定性合同」的精神下，值得在实现注释中声明使用了 modulo 而非 rejection sampling，偏差在统计上可忽略。

**建议**: 实现注释即可，不需要代码修改。

---

### D8 [MEDIUM] 可见性计算的复杂度边界

**位置**: P0-1 §2.3, P0-5 §5

**问题**: P0-1 §2.3 声明 "快照按房间序列化一次，再按玩家过滤——不是 O(P × E)"。这依赖高效的空间索引。Bevy ECS 的 spatial query 在单房间内可以 O(k) 查询（k = 视野内实体数），但如果世界有大量房间（如 100 个），且每个玩家在不同房间有视野，则仍接近 O(P × E_room)。

当前设计未指定：
- 视野缓存 (P0-5 §5) 的计算复杂度
- 多房间场景下的增量可见性更新策略
- 500 玩家 × 100 房间 × 1000 实体的极端场景下的表现

500 玩家是 MAX_DRONES_PER_PLAYER 上限，实际活跃玩家的可见性计算需要更精确的预算分析。

**建议**: 在 P0-5 中增加「可见性计算预算」节，声明每 tick 可见性计算的总复杂度目标和降级策略（例如超过 100 玩家时启用空间哈希分桶）。

---

### D9 [LOW] Refund 滥用检测状态持久化

**位置**: P0-2 §7.3

**问题**: "退还率 > 80% 连续 3 tick → 触发 throttle" 需要跨 tick 追踪每玩家的退还率。此状态需要持久化到 FDB（而非仅内存），否则引擎重启后滥用者 slate 被清零，可周期性重启引擎来绕过检测。

**建议**: 在 P0-2 §7.3 中添加：退款滥用计数器写入 FDB `/player/{id}/refund_state`，随 tick 提交一起原子持久化。

---

## CONSISTENCY GAPS

1. **P0-1 vs DESIGN.md — FDB commit phase** (见 D3): HIGH，需优先修正。

2. **DESIGN.md 章节编号错误**: §11 贡献指南下出现 "10.2 代码规范" — 应为 11.2。

3. **DESIGN.md §8.6 World/Arena 默认值表** 的 `manual_control` 行: 字段已在 §8.2 中明确删除 ("手动控制不开放")，但默认值表中仍出现且值为 false。建议移除该行或添加注释说明已移除。

4. **P0-9 §2.1 来源矩阵** 包含 7 个来源，§2.2 扩展来源另含 5 个。`Deploy` 与 `MCP_Deploy` 的语义区分在 §2.3 能力约束表中一致（Deploy 仅部署无查询），但在 §2.1 主矩阵中 `Deploy` 未出现 — 它只在扩展矩阵中。需在 §2.1 中添加 `Deploy` 行或明确扩展矩阵的 Phase 归属。

---

## ALGORITHMIC RISKS

| 风险 | 触发条件 | 影响 | 缓解状态 |
|------|---------|------|---------|
| 可见性计算爆炸 | 500 玩家 × 多房间 | Phase 2/3 延迟 | D8 — 需设计 |
| 编译队列积压 | 大量玩家同时部署 WASM | 部署延迟 | P0-4 §7 限制并发编译 ≤ 5 — 已缓解 |
| 路径寻找组合爆炸 | 所有玩家执行 10 次 path_find | 燃料消耗高但可接受 | 路径长度 ≤ 100 — 已缓解 |
| FDB 事务冲突 | 多玩家操作同房间同资源 | Tick abandon | 3 次重试 + 降级模式 — 已缓解 |
| Sandbox 进程数 × 内存 | 500 玩家 × 128MB | 64GB RAM | 单机可行，多 shard 后降低 — 可接受 |

---

## REVIEW SUMMARY

设计在架构层面是健全的 — ECS 调度正确、Tick 生命周期完整（除文档冲突）、数据一致性语义清晰（需补 Dragonfly stale detection）、算法复杂度有边界但需更多预算分析。9 项 Concern 中无 blocker 级别的架构缺陷。

**条件**: D3 (FDB commit phase 文档冲突) 必须在 Phase 1 开始前修正。其余 MEDIUM 项 (D1/D4/D5/D8) 需在对应 Phase 实现前决议。LOW 项为优化建议。
