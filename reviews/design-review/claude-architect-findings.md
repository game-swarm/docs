# Architect 评审发现 — Swarm DESIGN.md (Stage 1)

> 评审员: Claude Opus 4.8 (Architect) | 输入: design-summary.md | 视角: 边界/耦合/爆炸半径/扩展性

## Verdict
架构内核（确定性 + WASM 沙箱 + ECS + 延迟指令）扎实且自洽，但**确定性契约存在两处自我矛盾**，且**单世界扩展上限未定义**。可进入实现，但 A1/A2 须在 ABI 冻结前解决。

## Strengths
- 延迟指令模型 + 只读 host function：清晰的可信边界，审计面收敛。
- fuel metering（指令数）作为 CPU 核算：确定性正确。
- ECS `.chain()` 组合性：新机制低耦合扩展。

## Concerns

**A1（严重·确定性自相矛盾）** Rhai 的 `100ms 墙钟 → 强制终止 + 回滚`（§8.4）与 §1.5 原则2「确定性核心」直接冲突。墙钟在不同硬件/负载下不一致 → 回放/重模拟时同一 tick 的 mod 在 A 机被杀、B 机存活 → 世界状态分叉。AST 节点数（10k）是确定的，应作为**唯一**终止判据；墙钟只能用于告警，不能影响世界状态。

**A2（严重·扩展天花板）** EXECUTE 串行 ~0.5s 是确定性的代价，意味着单世界**无法跨机分片**。10→10000 玩家的瓶颈在此：串行阶段随 drone×command 线性增长，0.5s 预算在数千玩家下必然溢出。文档缺单世界实体/玩家硬上限——10000 玩家只能靠「多世界水平扩展」而非「大世界」，但该策略未声明。

**A3（严重·FDB 事务上限）** 「FDB 原子提交（全或无）」对整个 tick 世界状态。FoundationDB 单事务硬限 10MB / 5s。大世界全量提交会超 10MB → 提交失败或被迫拆分，拆分即破坏「全或无」原子性。需定义分片提交 + 跨片一致性策略。

**A4（中·COLLECT 扩展）** 并行收集需对每玩家「加载 WASM + 序列化可见快照(JSON)」。JSON 序列化在数千玩家下成本爆炸，且 WASM 实例的缓存/暖池策略未定义（每 tick 冷启动不可行）。快照格式即 WASM ABI，冻结后难改——应在冻结前评估二进制格式。

**A5（中·Phase 2a/2b 耦合）** inline 校验「对照当前世界状态」+ ECS 系统读取存在读后写顺序耦合：命令 N 看到命令 N-1 的副作用。这锁死了命令级并行（与 A2 互相强化），且两套变更机制（inline mutate vs ECS system）边界模糊，易产生「2a 改了、2b 又改」的双写 bug。

**A6（中·跨切面契约）** 新 CommandAction 需「引擎注册 + IDL + SDK 重生成」（§2.4）。IDL/ABI 是横切契约，任何动作变更波及全部 SDK 与玩家代码。D15 的「平衡参数仍为 default」叠加此处：若 MAX_FUEL/lifespan 后续大改，已冻结的快照/ABI 假设可能失效。

**A7（中·模组顺序确定性）** 多 mod 的 `tick_start.rhai` 执行顺序未规定（D12）。顺序影响世界状态 → 必须有确定性排序（如 mod id 字典序），否则破坏 A1。无依赖/版本解析器，组合爆炸风险确认。

## Missing
- 单世界玩家/实体硬上限（扩展契约）
- WASM 实例暖池/缓存策略
- 快照序列化格式与大小预算
- Tick 超时策略（COLLECT >2.5s 或 EXECUTE >0.5s：拉长 tick 还是丢指令？此处又是确定性风险）
- WS 断线重连/增量补洞协议（Dragonfly↔FDB 一致性）
- 运输中(in-flight)资源的 ECS 实体模型（D5 拦截机制依赖它）

## Phase Ordering
**摘要未含 7-Phase 计划**，无法逐条核对依赖。按架构推断关键路径：
1. Determinism Contract + IDL/ABI 冻结 → 必须最先（A1/A6 是前置阻塞）。
2. WASM Executor 与 SDK 依赖 ABI → 串行其后。
3. Rhai 集成依赖 Determinism Contract（A1/A7）→ 不可与之并行。
4. 可并行：ECS 系统实现 ∥ Dragonfly/NATS 广播层 ∥ MCP 工具层（三者仅依赖已冻结数据模型，互不耦合）。
建议补全 7-Phase 文档后做专项依赖图复核。
