# R3 Security Review — rev-dsv4-security

> Reviewer: DeepSeek V4 Pro (Security direction, primary)
> Date: 2026-06-16
> Scope: DESIGN.md + specs/01-09 + api/ + security/CVE-SLA.md

---

## Overall Verdict: REQUEST_MAJOR_CHANGES

Two critical findings (C1, C2) require design-level resolution before implementation proceeds. Three high-severity findings (H1-H3) should be addressed during the same revision cycle.

---

## CRITICAL

### C1: Rhai 模组隔离级别与引擎集成代码矛盾

**位置**: DESIGN §8.7, line 1909-1927 vs line 2032-2052

**问题**: DESIGN §8.7 明确声明 "Rhai 模组默认在**进程隔离**模式下运行"（line 1911），隔离模式配置表显示默认 = process 隔离（cgroup + seccomp 加固）。但引擎集成代码（line 2032-2052）显示 Rhai 脚本通过 `app.add_systems(Update, move |world: &mut World| { tick_end.call(...); actions.apply(world); })` 在**主引擎进程的 Bevy ECS pipeline 中同步执行**。

这两个设计是互斥的。如果 Rhai 真的运行在独立进程中：
- 它不能是 `add_systems(Update, ...)` 的一部分（那是 Bevy App 的本地系统）
- 从独立进程传回 `RuleActions` 再 `apply(world)` 需要 IPC 往返，延迟不确定
- 模组的 crash/死循环 不会影响引擎（这是进程隔离的优势）

如果 Rhai 在当前设计中确实是 in-process：
- 必须移除 "默认进程隔离" 的声明，或标注为 "计划远期实现"
- in-process 模式下恶意/错误 Rhai 死循环会直接阻塞整个 tick
- `确定性节点预算` 的 "强制终止" 语义在主进程内能做到什么程度？（Rust 侧需要 cooperative yield 点）

**建议**: 明确当前 MVP 的实现路径。如果 MVP 阶段为 in-process，必须在文档中诚实标注；同时给出 Rhai 脚本的可靠性保证——1 万 AST 节点的硬限制 + 连续超限 10 tick 自动禁用的机制在主进程内是否依赖 cooperative yield？如果 Rhai 脚本中有 `loop { }`，引擎如何检测并终止？

**安全影响**: Rhai 模组由服主安装——信任边界与 WASM（不可信玩家代码）不同。但 in-process Rhai 是引擎进程的 crash/DoS 单点。如果进程隔离不存在，服主安装的每个第三方模组都是引擎的提权向量。

---

### C2: Overload 静默 no-op 存在旁路信息泄露风险

**位置**: DESIGN §8, specs/02 §3.12

**问题**: Overload 设计声称 "静默 no-op，攻击者无法从返回值/副作用推断目标 fuel 状态"。但以下路径可能泄露信息：

1. **跨 tick 关联**: 攻击者可以每 51 tick 对同一目标释放 Overload（刚好超过全局冷却）。如果目标 fuel 从未降到 20% 地板以下，攻击者的每次 Overload 都消耗 500k——这本身就是一种"正常"信号。如果攻击者观察到连续多次 Overload 后目标的**行为模式改变**（drone 动作减少、产出下降），可以推断目标已触及 20% 燃料地板。

2. **多方合谋**: 两个合谋攻击者 A 和 B 对同一目标交错释放 Overload。A 在第 1 tick 释放，B 在第 25 tick 释放。两人共享结果——如果 A 消耗 500k 而 B 消耗 <500k（因为目标在 A 的 Overload 后恢复不足，B 触发了地板），B 知道目标接近地板。

3. **燃料恢复速率已知**: `fuel_budget / 1000` per tick 恢复速率是公开的（world.toml 可配置且通过 `swarm_get_world_rules` 可查询）。攻击者可以精确计算目标何时恢复到可被再次打击的水平。

**建议**: 
- 考虑将 Overload 的 fuel 削减量随机化（如 400k-600k 间的均匀分布），使攻击者无法从削减量反推目标状态
- 或者在 Overload 触发地板时仍消耗攻击者的 500k fuel，但目标不受影响——攻击者无法区分"成功削减"和"地板 no-op"
- 将 fuel 恢复速率设为不可查询（仅引擎内部使用）

**安全影响**: 信息泄露违背 "静默" 设计意图，使 Overload 可用于探测对手经济状况，形成不公平的侦查手段。

---

## HIGH

### H1: refund credit 跨部署保留的 session 定义模糊

**位置**: specs/02 §7.2, line 531

**问题**: "同一 session 内的迭代部署（同 session_id）不清除 credit——不惩罚正常迭代。"

以下问题未定义：
1. **session 生命周期**: session 从何时开始？何时结束？断开 MCP 连接后 session 是否持续？如果 AI agent 保持一个长期 MCP 连接，它的 session 可能持续数万 tick，refund credit 永不清除。
2. **session_id 的不可伪造性**: 谁签发 session_id？客户端能否自报？如果客户端可以伪造 session_id 来保留 credit，这就是一个绕过机制。
3. **多 WASM 槽位**: 一个玩家可以有多个 WASM 模块（槽位）。一个槽位产生的 refund credit 被另一个槽位消费——这本身就是 "跨模块预算转移"。

**建议**: 
- 明确定义 session 生命周期（如：从 MCP 连接到断开，或从 tick 开始到 tick 提交）
- session_id 必须由服务端签发且不可由客户端指定
- 限制 refund credit 仅在单个 WASM 槽位内有效

**安全影响**: 模糊的 session 语义可能被利用来实现 refund credit 的无限期积累，违背 "同 tick 内不得通过故意竞争失败来获取额外计算预算" 的设计原则。

---

### H2: WASM path_find 的 fuel 成本与实际计算成本不匹配

**位置**: specs/04 §8, line 350. specs/02 §4.3

**问题**: `host_path_find` 的 fuel 成本为 `10,000 + 50/tile`，最大路径长度 100 格 → 最大 cost = 15,000 fuel。但 pathfinding 是 A* 算法，在复杂地形上可能探索远多于最终路径长度的节点。

**攻击场景**: 恶意玩家构造一个螺旋迷宫地形（通过模组或地图配置），使得 A* 在找到路径或确认不可达之前探索数千个节点。每次 path_find 仅消耗 15,000 fuel（WASM 侧），但引擎侧消耗的 CPU 时间远超此值。每 tick 10 次调用 × 500 玩家 = 5000 次 path_find，每次在迷宫上可能消耗毫秒级 CPU 时间 → 数十秒的 CPU 时间每 tick。

**建议**:
- 在 path_find 中增加**服务端 wall-clock 超时**（如 5ms 内必须返回），超时返回部分结果
- 或限制 A* 的**最大探索节点数**（非路径长度），如 2000 节点上限
- 缓存键应包含 `(from, to, terrain_hash)`——当前设计已有此缓存（specs/04 line 350），但对迷宫地形缓存命中率低

**安全影响**: DoS 向量——恶意地形 × 恶意 path_find 调用可拖慢整个 tick。

---

### H3: Overload 全局冷却的竞争窗口

**位置**: specs/02 §3.12

**问题**: Overload 的全局冷却定义为 "同一 `(world_id, target_player_id)` 每 50 tick 最多被 Overload 一次"。但在分布式/并行上下文中：

1. **同一 tick 内多个攻击者**: 如果 8 个敌人在同一 tick 的不同 Phase 2a 顺序位置对同一目标释放 Overload，第一个执行后目标被标记为 "过去 50 tick 内被 Overload"，后续 7 个应该被拒绝（`TargetOverloadCooldown`）。但 spec 未明确：检查是 happen-before 还是 at-commit？如果在 Phase 2a 内原地修改，第一个 Overload 成功后立即设置冷却标记，后续检查会看到——正确。但需要明确这一语义。

2. **冷却与燃料恢复的交叠**: 50 tick 全局冷却 + 每 tick 恢复 `fuel_budget/1000`。在 50 tick 冷却期内，10M 上限的目标恢复约 500k——恰好等于一次 Overload 的削减量。这意味着如果只有一个攻击者持续对同一目标 Overload，目标燃料会在 2M（地板）到 2.5M 之间波动——攻击者可以永久保持目标在低燃料状态。这是 design intent 吗？如果是，应该文档化；如果不是，冷却应延长或恢复速率应可配置。

**建议**: 明确冷却检查的 happen-before 语义；文档化持续 Overload 的经济压制效应。

---

## MEDIUM

### M1: Snapshot 截断可能导致关键实体丢失

**位置**: specs/01 §2.3, line 136-148

**问题**: Snapshot 截断策略是 "按距离排序截断（最近优先），保证近距离实体不丢失"。但在以下场景中存在问题：

- 玩家 A 的 drone 集中在一个区域，但**远距离的敌方 drone 正在接近**。截断后敌方 drone 从 snapshot 中消失，玩家 A 的 WASM 策略无法感知逼近的威胁。
- 攻击者可以利用这一点：将主力部队保持在视野边缘（第 3 环房间），而被截断的快照中只包含防御方的近距友方 drone。

**建议**: 截断算法应优先保留**敌方实体**（owner != self），其次按距离排序。或者在 `truncated=true` 时提供一个额外的 `enemy_count` 摘要。

---

### M2: Tutorial 来源隔离未在 Source Gate 管线中明确体现

**位置**: specs/09 §2.4 + §4

**问题**: specs/09 §2.4 声明 Tutorial 来源指令 "仅可在 `world.mode = 'tutorial'` 的世界中接受"。但 §4 的 Source Gate 管线只展示了 WASM→pass, MCP_Deploy→reject 两条路径。Tutorial 来源不在这个显式管线中。

**建议**: 在 Source Gate 管线图中增加 Tutorial 路径，明确其校验点。

---

### M3: 部署 nonce 的短 TTL (60s) 与 WASM 编译时间窗口可能冲突

**位置**: specs/09 §3.2-3.3

**问题**: `deploy_nonce` 的 TTL 为 60s。但 WASM 上传 + 服务端编译可能需要 >60s（编译超时设为 30s，加上网络延迟和验证）。如果客户端获取 nonce 后编译超时或网络慢，nonce 可能在上传完成前过期。重试需要新 nonce，但旧 nonce 已被消费（单次消费）——导致部署失败循环。

**建议**: nonce TTL 应 ≥ 编译超时 + 网络往返 + buffer。建议 120s minimum。

---

### M4: CollectCache 重试时的 fuel 扣费语义不够精确

**位置**: specs/01 §3.5, line 379-386

**问题**: "跨重试 fuel 消耗上限 = 1 × MAX_FUEL（首次 COLLECT 时的扣费即为最终扣费，重试不追加）"。这意味着：
- 如果 FDB commit 失败但玩家的 COLLECT 阶段消耗了 fuel，该 fuel 已被扣除
- 重试时使用缓存的命令，不追加扣费

但如果 FDB 连续失败 3 次后 tick 放弃，spec 说 "已扣除的 fuel 退还玩家"。但退还后玩家是否可以用这些 refunded fuel 在同一个 tick 的重新执行中再次消费？spec 说 tick 放弃后 "等待 1s 重试同一 tick"——这 1s 内的状态是什么？CollectCache 是否被清除？

**建议**: 明确 CollectCache 的生命周期——在 tick 成功提交或放弃后清除。明确重试时钟的起始点。

---

## INFORMATIONAL

### I1: Rhai 能力白名单的完整性

DESIGN §8.7 列出了 6 个白名单 action（deduct_resource, award_resource, damage_entity, set_entity_flag, emit_event, log）。`set_entity_flag` 的参数 "白名单标记" 未定义具体的允许标记集合。如果 Rhai 可以设置任意 flag（如 `owner=attacker_id`），这就是所有权绕过的后门。

**建议**: 文档化 `set_entity_flag` 的允许值白名单。

### I2: Snapshot 压缩潜力

每玩家 256KB snapshot × 500 玩家 = 128MB/tick。World 模式下目标 500 活跃玩家，tick 间隔 3s。Snapshot 构建和传输是显著的吞吐量问题。

### I3: CollectCache 的缓存键

specs/01 §3.5 说 FDB commit 失败时 "复用同一 COLLECT 结果"。但缓存键是什么？如果玩家在 FDB commit 失败和重试之间改变了部署（MCP_Deploy 来源的部署可能在别的线程中进行），缓存的命令序列是否仍然有效？spec 未明确说明 COLLECT 阶段和部署阶段的隔离边界。

### I4: Wasmtime 版本锁定与回放

specs/01 §6.3.3 明确了回放时使用记录的 Command[] 而非重新调用 WASM，因此 Wasmtime 版本变更不影响回放。这一设计决策是正确的。但需要验证：在 "降级模式" 下需要匹配 Wasmtime 版本进行二次回放验证——是否有降级模式回放的 CI 测试？

### I5: MCP simulate 的输出可能泄露不可见信息

`swarm_simulate` 使用 snapshot 副本执行模拟。但模拟结果中可能包含通过模拟计算推断出的隐藏信息（如：模拟走到第 N tick 时 drone 的移动揭示了一个不可见的地形特征）。虽然有 100 tick 上限，但仍可能泄露短期信息。

---

## Summary

| Severity | Count | IDs |
|----------|-------|-----|
| Critical | 2 | C1, C2 |
| High | 3 | H1, H2, H3 |
| Medium | 4 | M1, M2, M3, M4 |
| Informational | 5 | I1, I2, I3, I4, I5 |

Core security strengths of this design:
- WASM sandbox isolation is thorough (seccomp + cgroup + no WASI file/net/clock)
- Command validation pipeline is single-entry, no bypass paths
- Deferred command model prevents WASM from directly mutating world state
- Client-side Ed25519 signing provides strong audit trail for deployments
- Deterministic replay enables full audit trail verification
- MCP is correctly positioned as a management interface, not a gameplay channel
