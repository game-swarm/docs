# R16 Performance Review — DeepSeek V4 Pro

> Clean-slate review. Phase 1 — 仅读取方向相关子集（7 份文档）。设计阶段评审，不考虑分阶段实现。

**Reviewer**: Performance (DeepSeek V4 Pro)
**Date**: 2026-06-18
**Documents reviewed**: design/README.md, design/engine.md, design/tech-choices.md, specs/reference/api-registry.md, specs/core/01-tick-protocol.md, specs/core/04-wasm-sandbox.md, specs/core/05-persistence-contract.md

---

## Verdict: CONDITIONAL_APPROVE

设计总体具有良好的性能架构——清晰的 tick 预算分解、worker pool + Store reset 模型、两阶段快照架构消除 O(P×E) 序列化开销、FDB 小事务 + 对象存储分层。但 worker pool 伸展到 `active_players` 规模时的资源悬崖、per-player 2500ms deadline 在并行度受限时的预算侵蚀、以及 Phase 2a 串行命令循环在峰值下的吞吐余量需要缓解方案。

---

## Strengths

1. **Tick 预算分解清晰完整**。engine.md §3.4.1 定义了 5 个阶段的 p99 预算（SNAPSHOT ≤50ms / COLLECT ≤2500ms / EXECUTE ≤400ms / COMMIT ≤50ms / BROADCAST ≤50ms），总和 3050ms 在 3000ms 目标附近留了 ~50ms 缓冲（soft deadline 2500ms + hard deadline 4000ms 的降级策略进一步保护了预算超支场景）。

2. **两阶段快照架构消除了 O(P×E) 瓶颈**。engine.md §3.2 和 01-tick-protocol.md §2.3：tick 开始时一次性构建完整世界快照并按房间分片，每个玩家仅拼接可见房间分片（≤9 个）。复杂度从 `O(玩家数 × 实体数)` 降为 `O(实体数 + 玩家数 × 可见房间数)`，消除了 per-player 重复序列化开销。快照构建在 WASM 执行前完成，天然确定。

3. **COLLECT 缓存跨 FDB 重试复用**。01-tick-protocol.md §8.4 和 §3.5：FDB commit 失败时不重新执行 WASM，复用首次 COLLECT 的命令列表和 fuel 扣费明细。跨重试 fuel 消耗上限 = 1 × MAX_FUEL，避免了重试放大——这是正确的设计选择，防止 FDB 抖动导致的玩家 fuel 双扣。

4. **FDB 小事务 + 对象存储分层**。05-persistence-contract.md §2：FDB 仅写 tick_head/manifest/hash_chain（<10KB/事务），大 blob（TickTrace、delta chain、keyframe）进对象存储。FDB commit 是唯一权威持久化点，对象存储写入失败不破坏 FDB 完整性，孤儿 blob 由 GC 清理。这个分离解决了"单事务写一切"的性能瓶颈。

5. **Worker pool + per-tick Store reset 在隔离性与性能间取得平衡**。04-wasm-sandbox.md §1：设计明确拒绝了 fork-per-tick（500 玩家仅进程创建就需要 2.5-5s），选择 long-lived worker pool + Store reset（清空线性内存、重置 fuel counter、重建 Instance）。配合 cgroup/seccomp 持久绑定，避免了每 tick 重新创建隔离边界的开销。

6. **Snapshot 截断的确定性保证**。01-tick-protocol.md §2.3：截断使用确定性排序键 `(priority_bucket, distance, entity_id)`，不使用墙钟或并行度。同一 tick、同一世界状态、同一玩家 → 同一截断结果。关键桶（Spawn、Controller）永不截断——这是 replay determinism 的必要条件。`truncated` flag + `omitted_count` 让 WASM 代码可推理信息完整度。

7. **种子洗牌提供公平性且不可预测**。01-tick-protocol.md §3.1：Fisher-Yates seeded shuffle（Blake3 XOF）保证每 tick 玩家顺序随机轮换，长期期望均等，但单 tick 位置不可预测。结合 seed rotation（每 10000 tick 轮换）限制泄露窗口宽度。

8. **Phase 2b 并行策略有明确的数据竞争分析**。01-tick-protocol.md §3.4：regeneration 和 decay 只操作独立数据（Energy/Carry 和 Fatigue/Cooldown），与主线 `.chain()` 无数据竞争。并行安全有组件级读写矩阵证明。

9. **Sandbox OS 边界加固 checklist 可 CI 验证**。04-wasm-sandbox.md §9：seccomp 白名单、cgroup 限制、命名空间隔离均有具体的验证命令和 CI 测试。生产环境禁止 `sandbox.relaxed = true`——引擎启动时检查拒绝。

---

## Issues

### C1 — Worker pool 在 target/hard cap 下的资源悬崖 (Critical)

**位置**: engine.md §3.4.2, engine.md §3.4.3

**描述**: Worker pool 大小公式为 `max(min_pool, active_players)`。当 active_players 达到 target 500 时，这意味着 500 个独立 OS 进程（每个带 seccomp + cgroup + 独立网络命名空间）。每个进程的 cgroup `memory.max = 128MB`，总内存需求为 500 × 128MB = **64GB** 仅用于 sandbox worker，加上引擎进程（Bevy World 50K entities + ECS 系统 ≈ 2-4GB），总计 ~70GB。在 hard cap 1000 玩家时翻倍至 ~130GB。

此外，COLLECT 阶段要求所有 500 个 worker **同时**执行 WASM。这需要至少 500 个可用 CPU 核心或等效的调度单元。即使采用超线程/时间分片，500 个 Wasmtime 实例同时执行 JIT 代码的上下文切换开销不可忽略。

**建议**: 
- 将 pool size 从 `max(min_pool, active_players)` 改为 `min(max_pool, active_players)`，限制最大并发 worker 数（建议 `max_pool = N_cores × 2`），超出部分排队
- 文档中应明确 target 500 players 所需的最小硬件配置（核心数、内存）
- 考虑引入 per-worker 实际内存使用监控（cgroup `memory.current`），而非仅设上限

**严重度**: Critical — target 500 players 的硬件需求未量化，可能误导实现方向

---

### H1 — Per-player 2500ms deadline 在并行度受限时侵蚀全局预算 (High)

**位置**: engine.md §3.4.1, 01-tick-protocol.md §2.2

**描述**: Per-player sandbox deadline 为 2500ms（World 模式）。这意味着单个慢玩家可以合法消耗 COLLECT 预算的 100%。如果并行度受限于 CPU 核心数（而非 pool size），两个慢玩家各占 2000ms 就合计超出 COLLECT 总预算。当前设计依赖 "所有玩家完全并行执行" 的假设——pool size = active_players。

当 pool size 小于 active_players（建议 C1 引入 max_pool 后）时，部分玩家排队。此时单个慢玩家的 2500ms 不仅消耗自身配额，还阻塞排队中的其他玩家——这些玩家可能在 soft deadline 触发 `skip_remainder` 时被集体清空为 0 指令。

**建议**: 
- Per-player deadline 不应是固定值，而应是 `min(2500ms, COLLECT_remaining_budget / queued_players)`
- 或在 worker pool 排队机制中加入 time-slice 轮转（每个 worker 分配 `total_budget / pool_size` 时间片后强制 yield），与 epoch interruption 机制配合

**严重度**: High — 设计假设 100% 并行，实际部署中可能不成立

---

### H2 — FDB small-transaction 假设依赖状态 delta 高度紧凑 (High)

**位置**: 05-persistence-contract.md §7, 01-tick-protocol.md §9.4

**描述**: persistence-contract 声明单 tick FDB 事务 <10KB，但 01-tick-protocol §9.4 使用 FDB 推荐上限 10MB 作为安全边界。这两个数字相差 1000×。10KB 的假设成立需要：(a) 每 tick 的状态变更非常少；(b) 所有大 blob 已正确路由到对象存储。

在高强度战斗场景下（假设 5000 活跃 drone 中 50% 参与战斗），每 tick 可能产生数百个 entity 变更（HitPoints、Fatigue、Position、Cooldown 更新）。每个变更即使压缩后也可能需要 20-50 字节。500 个变更 = 10-25KB 的事务大小——已经接近甚至超过 10KB 目标。如果加上 Controller progress、资源点 regeneration、建筑 construction progress 等，事务大小可能显著超过 10KB。

**建议**: 
- 将 10KB 改为按 active_entities 计算的可变上限（如 `max(10KB, active_entities × 50B)`）
- 在 CI 中添加压力测试：模拟 5000 drone 战斗场景，测量实际 FDB 事务大小
- persistence-contract 和 01-tick-protocol 的事务大小声明应统一为一个权威值

**严重度**: High — 10KB 目标在高活动量下可能不可行，威胁 tick 提交延迟

---

### H3 — Phase 2a 串行命令循环的峰值吞吐余量不足 (High)

**位置**: engine.md §3.2 (Phase 2a Inline), api-registry.md §5 (容量限制)

**描述**: Phase 2a 对全局排序后的命令逐条 inline apply。最坏情况：500 玩家 × 100 命令/玩家 = **50,000 条命令**。EXECUTE 总预算 400ms，减去 Phase 2b（27 systems，估计占用 ~200ms），留给 Phase 2a 约 200ms。200ms 处理 50,000 条命令 = **4μs/命令**。

每条命令需要：(a) 从排序队列取出；(b) 对照当前 Bevy World 状态校验（owner check、resource check、position check、cooldown check 等）；(c) 通过 ECS system 立即 apply（可能触发多个 component 写入）。4μs 在 Rust/Bevy 中是可能的但非常紧——没有任何容错余量。

如果实际命令数经常接近上限（例如所有玩家都在积极战斗），串行瓶颈将成为 tick 延迟的主要贡献者。

**建议**: 
- 考虑将 Phase 2a 的命令校验与应用分离：校验可以并行（基于快照状态的只读校验），仅 apply 保持串行
- 或引入 per-room 命令分组：不同房间的命令之间无竞争（操作不同 entity），可以并行执行
- 在 CI 中添加 50,000 命令吞吐基准测试

**严重度**: High — 50,000 命令/400ms 的吞吐目标需要验证，当前设计无缓冲

---

### M1 — Per-tick Instance 重建成本未量化 (Medium)

**位置**: 04-wasm-sandbox.md §1 (Store reset), engine.md §3.2 (WASM 预编译)

**描述**: Per-tick Store reset 包括：清空线性内存、重置 fuel counter、重建 Instance（重新绑定所有 host function imports）。Instance 重建涉及 Wasmtime 内部的 instantiation 流程——即使模块已预编译，instantiation 仍需解析 imports、设置 memory、初始化 globals/tables。对于有 5 个 host function imports 的模块，这个成本可能很小（<100μs）；但如果未来 host function 数量增长或模块有复杂的内存初始化（active data segments），成本可能上升到毫秒级。

文档提到 "tick 时只需实例化已编译模块" 但未给出 instantiation 的 p99 延迟目标。在 500 玩家并发场景下，500 × Instance 重建的总开销应在 SNAPSHOT/COLLECT 预算中占有一席之地。

**建议**: 
- 在 04-wasm-sandbox.md 中明确 Store reset + Instance 重建的延迟目标（建议 ≤1ms p99）
- 在 CI 中添加基准测试：测量 500 并发 Instance 重建的总 wall-clock

**严重度**: Medium — 成本可能不大但未量化，属于预算盲区

---

### M2 — Broadcast fan-out 在 500+ 客户端下的退化行为 (Medium)

**位置**: engine.md §3.4.1 (BROADCAST ≤50ms), 01-tick-protocol.md §4.2, §6.1 (BROADCAST overload)

**描述**: BROADCAST 预算 ≤50ms 包括：delta 计算 + Dragonfly 缓存更新 + NATS 发布。在 500 活跃玩家场景下，每个玩家可能有多条 WebSocket 连接（Web UI + MCP），总连接数可达 1000+。NATS 向 1000+ 订阅者发布 delta 的 fan-out 延迟取决于 NATS 集群规模，可能接近甚至超过 50ms。

文档在 §6.1 中承认了 BROADCAST overload 的降级策略（降低 fan-out rate），但降级意味着部分客户端收到延迟 delta——对于依赖实时信息的 WASM 策略（如下一 tick 的决策），延迟 delta 可能导致基于过时信息的决策。

**建议**: 
- 将 NATS fan-out 分层：关键客户端（活跃玩家 WebSocket）优先推送，MCP 客户端接受更高延迟
- BROADCAST budget 可以为 fan-out 分配独立的异步预算（如 200ms），不并入 50ms 的严格预算

**严重度**: Medium — 有降级策略但实时性退化影响游戏公平性

---

### M3 — Worker 生命周期强制的 cold start (Medium)

**位置**: engine.md §3.4.3 (Recycle 策略: 每 worker 最多服务 1000 tick)

**描述**: Worker 在服务 1000 tick 后被强制替换。1000 tick × 3s = 50 分钟。替换意味着：(a) 新 worker 进程创建 + seccomp + cgroup 初始化；(b) 预编译模块从缓存加载（仍需反序列化 cranelift 编译产物）；(c) 新 worker 首次 tick 仍有 JIT 预热成本（即使模块已预编译，cranelift 编译的代码可能仍需 CPU icache/dcache 预热）。

在 500 玩家场景下，worker 替换会分散在 50 分钟内——平均每 6 秒一个 worker 替换。这个频率很低，不会造成集中冲击。但如果玩家的 worker 恰好在其关键操作（大规模战斗）期间被替换，该 tick 的首次执行可能有额外延迟。

**建议**: 
- Worker 替换应在玩家空闲 tick（该玩家无活跃 drone 或有 drone 但未参与竞争）时触发
- 或在替换前预热新 worker（执行一次空 tick），然后原子切换

**严重度**: Medium — 分散替换降低风险，但仍有单玩家体验抖动

---

### L1 — Pathfinding 缓存有效性依赖 player_visibility_fingerprint 稳定性 (Low)

**位置**: 04-wasm-sandbox.md §8 (host_path_find 缓存键)

**描述**: `host_path_find` 的缓存键包含 `player_visibility_fingerprint`。这个 fingerprint 在玩家视野变化时改变——每次 drone 移动到一个新房间、房间被 contested 状态改变、Controller Observer 升级等。在高移动性场景下（drone 频繁跨房间），fingerprint 变化可能导致缓存命中率显著下降，触发 CPU 重算。A* 重算 100-500 nodes 的成本约 5000-25000 fuel + 0.1-0.5ms wall-clock——在 per-player 10 次调用预算下，最坏情况消耗 0.5-5ms。

**建议**: 
- 对 terrain_hash（房间地形不变）和 visibility_fingerprint 分层缓存：同一房间相同地形的路径可以跨 visibility 变化复用，仅在路径终点不可见时失效
- 监控 `cache_miss_penalty` 指标，设置告警阈值

**严重度**: Low — 性能影响有上限（10 次调用 × 500 nodes），但缓存设计值得细化

---

### L2 — COLLECT 阶段 500 并发 WASM 实例的内存带宽竞争 (Low)

**位置**: engine.md §3.2, 04-wasm-sandbox.md §1

**描述**: 两阶段快照架构中，快照构建后为只读共享——500 个 worker 同时从共享快照内存中读取各自可见房间的分片。虽然避免了写竞争，但 500 个并发 reader 同时遍历快照数据结构可能造成 CPU cache 抖动（特别是共享的 L3 cache）。这个影响在多数 CPU 架构上很小（只读共享 cache line 的成本远低于写入），但在 NUMA 架构上跨 socket 读取可能产生额外延迟。

**建议**: 
- 快照分片可考虑按 NUMA node 亲和性分配 worker——每个 NUMA node 上的 worker 优先读取本地内存中的分片副本
- 在性能测试中测量不同 CPU 拓扑下的快照读取延迟

**严重度**: Low — 只读共享的 cache 抖动影响通常<5%，且仅在大规模 NUMA 上需关注

---

## CrossCheck — 需要跨方向检查

以下问题需要其他方向评审员的确认或交叉验证：

1. **C1 Worker pool 资源估算 → Architect 方向**: worker pool size = active_players 的架构决策需要架构师确认——这是设计意图还是临时占位？是否有计划引入 max_pool 上限？

2. **H2 FDB 事务大小 → Architect/Security 方向**: 10KB vs 10MB 的跨文档不一致需要统一。同时需要 Security 方向确认：状态 delta 写入 FDB 是否包含了足够的审计信息？如果 delta 压缩太激进，是否影响回放验证？

3. **H3 Phase 2a 吞吐 → Architect 方向**: 50,000 命令/400ms 的吞吐目标是否在架构层面的预期内？per-room 并行是否是远期扩展方向？

4. **M1 Instance 重建成本 → Architect/Security 方向**: Store reset + Instance 重建是否暴露了任何安全边界问题？例如，重建过程中是否有短暂窗口泄露前一 tick 的 WASM 状态？

5. **Snapshot 截断的实体密度攻击 → Security 方向**: 敌对方通过堆叠实体增加受害方 snapshot 压力——文档在 engine.md §3.4.4 中声明"此行为不被禁止"，仅通过截断限制信息泄露。但 snapshot 截断本身消耗 CPU（排序 + 序列化）。Security 方向应确认：DDOS 通过 snapshot 膨胀是否在威胁模型中？

---

## 预算分解汇总

| 阶段 | 预算 | 关键假设 | 风险 |
|------|------|---------|------|
| SNAPSHOT build | ≤50ms p99 | 50K entities, 单次序列化, 按房间分片并行 | 低 — 分片并行 + Rust 序列化性能 |
| COLLECT dispatch | ≤2500ms | pool size = active_players, 100% 并行 | **C1** — 500 进程 × 128MB = 64GB |
| EXECUTE Phase 2a | ~200ms (inferred) | 50K 命令 inline apply | **H3** — 4μs/命令无余量 |
| EXECUTE Phase 2b | ~200ms (inferred) | 27 systems, serial spine + 3 parallel sets | 低 — Bevy 调度成熟 |
| COMMIT (FDB) | ≤50ms p99 | <10KB 事务 | **H2** — 高活动量下事务膨胀 |
| BROADCAST | ≤50ms | Dragonfly + NATS fan-out | **M2** — 500+ 客户端退化 |

---

*Review complete. 3 Critical/High issues (C1, H1-H3) + 3 Medium (M1-M3) + 2 Low (L1-L2). 8 strengths identified. 5 cross-check items for other directions.*
