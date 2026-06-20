# R27 Architect Review — DeepSeek V4 Pro

> Phase 1 Clean-Slate 独立评审。Architect 方向：系统架构完整性、数据流正确性、组件边界清晰度、可扩展性、向后兼容性。

---

## Verdict

**CONDITIONAL_APPROVE**

架构设计在核心层面是正确的：三阶段 Tick 生命周期清晰、FDB 单权威源 + Dragonfly 缓存 + NATS 推送的分层数据流合理、WASM-only executor 保证了公平性、确定性 backbone（Blake3 PRNG + canonical sort key + 定点数）坚实。但存在 1 个 Critical 跨文档调度冲突必须修复，以及 3 个 High 级别的文档内部矛盾，均属于文档一致性问题而非架构缺陷——修复成本低，不影响核心设计。

---

## Strengths

1. **单权威源设计**：api-registry.md 声明为所有 API 合约的唯一来源，06-phase2b-system-manifest.md 声明为系统调度的唯一权威——消除多文档分叉风险
2. **清晰的三阶段分离**：COLLECT（构建快照 + WASM 执行）→ EXECUTE（Phase 2a inline + Phase 2b deferred）→ BROADCAST（delta 推送），每阶段职责明确
3. **WASM-only executor**：所有玩家（人类/AI）同走 WasmSandboxExecutor，fuel metering 保证公平，不存在 McpPlayerExecutor 绕过路径
4. **确定性 backbone**：Blake3 XOF PRNG + 5 层 canonical sort key + 定点数 + indexmap，回放验证完整
5. **Replay-critical subset 分离**：FDB 原子提交 10 个关键字段，对象存储异步非阻塞——blob 失败不影响确定性回放
6. **准入控制设计完善**：aggregate CPU 公式、per-player fair-share、hard cap + ERR_CPU_SATURATED 拒绝策略
7. **反滥用机制**：snapshot truncation + 滥用检测、per-drone action quota、Overload 抗永久锁死证明
8. **可扩展路径清晰**：单节点 MVP → room-partition FDB → 水平分片，每阶段有明确的容量合同

---

## Findings

### Critical

**C1 — 02-command-validation.md §3.19 与 06-phase2b-system-manifest.md 系统调度冲突**

- 02-command-validation.md §3.19 内联调度链：
  ```
  death_mark → spawn → spawning_grace → combat → status_advance → (regeneration, decay 并行) → death_cleanup
  ```
  将 `status_advance` 置于 `regeneration` **之前**。

- 06-phase2b-system-manifest.md §1 权威调度链（R16 B2 修复后）：
  ```
  S07 death_marker → S08 spawn → S09 spawning_grace → S10 regeneration →
  S11-S13 combat → S14 spec_atk_red → S15 dmg_apply →
  S16-S22 status (含 S22 status_advance) → S23 aging → S24 decay → S25 death_cleanup
  ```
  将 `regeneration`（S10）置于 combat **之前**，`status_advance`（S22）置于 combat + dmg_apply **之后**。

- **根本原因**：02-command-validation.md §3.19 的调度描述是 R16 B2 修复前的旧版，修复后未更新。R16 B2 的关键修复正是将 `regeneration` 移至 `damage_application` 之前（防 heal+regen 双倍回复），此变更未反映到 02-command-validation.md。

- **影响**：实现者若以 02-command-validation.md 为准会得到错误的调度顺序，导致 regen+heal double-dip bug 回归。

- **严重性**：Critical — 06-phase2b-system-manifest.md 声明为唯一权威，但旧版调度链仍在另一个核心规范中存在，构成实现分叉风险。

- **修复建议**：删除 02-command-validation.md §3.19 的内联调度链，替换为对 06-phase2b-system-manifest.md 的引用（与 §3.16 处理特殊攻击优先级的方式一致）。

### High

**H1 — EXECUTE 超时语义多文档不一致**

- engine.md §3.4.1：World EXECUTE budget ≤400ms, Arena ≤50ms
- 01-tick-protocol.md §1.4 状态机图：`硬超时天花板: 500ms`
- 01-tick-protocol.md §8.2 统一预算表：`EXECUTE 不单独超时，由 COLLECT+EXECUTE 总预算控制`

三处描述互相矛盾：400ms budget vs 500ms hard ceiling vs "不单独超时"。实际语义（§8.2 澄清后）是 EXECUTE 无独立超时，受总 tick_soft_deadline_ms=2500ms 约束——但前两处未同步更新。建议 engine.md §3.4.1 和 01-tick-protocol.md §1.4 统一标注"EXECUTE 不独立超时，见 §8.2"。

**H2 — 04-wasm-sandbox.md seccomp clone 策略冲突**

- §4.1 seccomp 允许列表：`clone (仅 CLONE_VM | CLONE_VFORK)` — 允许受限 clone
- §9.1 统一 OS 加固表：`fork/vfork/clone | ❌ 禁止` — 禁止所有 clone 变体

两处矛盾。§9.1（统一加固 checklist）标记为部署前必须逐项验证，若按此表部署则 Wasmtime 内部线程创建将失败。需要确定正确策略：如果 Wasmtime 确实需要 CLONE_VM|CLONE_VFORK，则 §9.1 应修正为"clone (仅 CLONE_VM|CLONE_VFORK) | ✅ 允许"。

**H3 — 04-wasm-sandbox.md PID max 不一致**

- §4.2 cgroup v2：`pids.max = 32`
- §9.1 统一 OS 加固表：`pids.max | 16`

同一文档内同一参数两个不同值（32 vs 16）。需要确定正确值并统一。

### Medium

**M1 — "Parallel Set C" 标签误导**

06-phase2b-system-manifest.md §1 将 S24 decay_system 标记为 `Parallel Set C: World Maintenance`，但该集合仅含一个串行系统。注释说"简化为单一 serial system"，但标签"Parallel Set C"对阅读者产生误导。建议改为 `Serial: World Maintenance` 或直接合并入 serial spine。

**M2 — spawn body_cost refund 竞争路径边界未明确**

02-command-validation.md §3.8：body_cost 在 Phase 2a S06 立即扣除，Phase 2b S08 创建失败时全额退还。但 manifest §3 的 RoomCap 时序是 S07 释放 → S08 消费——S07 总是释放槽位（≥0），S06 在 Phase 2a 看到的 RoomCap ≤ S08 可用的 RoomCap。因此 S08 创建失败的唯一场景是"body_cost 已扣但 room cap 已满且无死亡释放"——这一边界条件应明确文档化。

**M3 — Decay 阶段的 parallelism 声明与实际不符**

06-phase2b-system-manifest.md §4 R/W 矩阵的并行安全证明中声明 "World Maintenance (S24 decay): HitPoints 和 Fatigue 列在该阶段仅 decay 访问——S10 regen 已在之前完成且使用 Without<DeathMark> filter，无数据竞争。" 该声明正确描述了 S24 的数据隔离，但 S24 本身已不是并行集合——它是一个独立串行系统。并行安全证明应更新以反映当前架构。

### Low

**L1 — Controller repair capacity 与维修距离的约束未交叉验证**

engine.md §3.4.5：RCL1 repair_capacity=5/tick, repair_range=1 格。相邻格只有 6 个，5 drones 排队可完全利用——但文档未说明当 drone 数量 > capacity 时的排队策略（FIFO? 按 entity_id? 按距离?）。这不影响正确性但影响确定性实现。

**L2 — 01-tick-protocol.md §2.3 快照构建伪代码截断检测条件**

```rust
truncated: serialized_size > 256_000,
```

但 `entities` 变量已在 `sort_and_truncate` 中截断——此时 `serialized_size` 应 ≤ 256KB，`truncated` 将始终为 false。截断标记应在截断前计算或使用原始大小。这是一个伪代码 bug（不影响英文描述，但实现者若照抄会出错）。

---

## CrossCheck — 需要跨方向检查

以下是我怀疑但超出 Architect 方向范围的问题，指定目标方向：

- **CX1**: [seccomp clone 策略冲突（H2）] → 建议 **Security** 检查正确的沙箱 syscall 策略，确认 Wasmtime 30.x 是否依赖 CLONE_VM|CLONE_VFORK
- **CX2**: [PID max 不一致（H3）] → 建议 **Security** 检查正确的 cgroup pids.max 值（32 vs 16）
- **CX3**: [Overload 抗锁死证明假设 MAX_FUEL=10M] → 建议 **Economy** 验证 fuel budget 与 economy balance 的一致性
- **CX4**: [Recycle 10% 下限退还的经济平衡] → 建议 **Economy** 验证 lifespan-proportional refund 是否可能形成套利循环（Recycle 末期 drone → spawn 新 drone）
- **CX5**: [Storage tax 三级阈值 30/60/85%] → 建议 **Economy** 验证税率设计的激励效果
- **CX6**: [Arena 300ms tick 独立预算] → 建议 **Performance** 验证 Arena 50ms EXECUTE budget 在重战斗场景下的可行性
- **CX7**: [Per-player 256KB snapshot cap] → 建议 **Designer** 验证该 cap 在 fog_of_war 过滤后的典型场景是否充足
- **CX8**: [MainActionQuotaExceeded 对 Transfer chain 的限制] → 建议 **Designer** 验证 per-drone 1 main action + Transfer 不计入的设计是否产生意外玩法限制
- **CX9**: [02-command-validation.md §3.19 旧调度链（C1）] → 建议 **Determinism** 审查整个 02-command-validation.md 是否还有 R16 B2 修复前的其他残留

---

## Algorithmic Risks

1. **命令排序 O(N log N)**：500 玩家 × 100 指令 = 50k 条/tick。sort 开销 ~780k 比较，在 400ms EXECUTE budget 内可接受。但若 active_players 达到 hard cap 1000 且人均指令接近 100，将达 100k 条——此时 sort 占 ~1.6M 比较，需 benchmark 验证。

2. **Snapshot 视野拼接**：两阶段设计（一次构建 + per-player 过滤）将复杂度从 O(P×E) 降至 O(E + P×V)。500 玩家 × 256KB = 128MB 快照总量，在 200ms budget 内。但 1000 玩家时达 256MB——需验证 200ms p95 budget 是否仍可满足。

3. **FDB room-partition 2PC**：跨房间操作（drone 移动穿越出口）需要 source room → target room 两阶段提交。在 room-partition 模式下，出口穿越的频率和 2PC 延迟需要 benchmark。文档给出了 3s 超时 + best-effort fallback，但 best-effort 的语义（部分成功？全部回滚？）未定义。

---

## 变更记录

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2026-06-20 | R27 Phase 1 Clean-Slate Architect 评审。VERDICT: CONDITIONAL_APPROVE。1 Critical (C1)、3 High (H1-H3)、3 Medium (M1-M3)、2 Low (L1-L2)、9 CrossCheck、3 Algorithmic Risks。 |