# R23 性能评审报告 — DeepSeek V4 Pro

**评审员**: Performance Reviewer (rev-dsv4-performance)
**日期**: 2026-06-19
**范围**: R23 Phase 1 Clean-Slate — engine.md, tech-choices.md, 01-tick-protocol.md, 04-wasm-sandbox.md, 05-persistence-contract.md, api-registry.md

---

## Verdict: CONDITIONAL_APPROVE

设计在确定性、公平性和资源约束方面展现了高度纪律性，Tick Pipeline 预算分解清晰。但存在**3 个 High severity 发现**需要在实现前解决：worker pool 容量假设与实际默认值矛盾、FDB 单事务串行化点在 500+ 玩家下的可行性未验证、pathfinding 全局预算在 scale 下的 fair-share 严重不足以支撑有意义的寻路。另发现 4 个 Medium 和 3 个 Low 问题。

---

## Strengths

- **两阶段快照架构** (engine.md §3.2, spec §2.3): 一次性构建完整世界快照 → 按房间分片 → 每玩家拼接可见分片（≤9 房间）。复杂度从 O(P × E) 降为 O(E + P × 可见房间数)，消除了每玩家独立序列化开销。快照在 WASM 执行前构建完成，天然确定。这是整个 COLLECT 阶段最大的性能优化。
- **WASM 预编译 + Worker Pool** (engine.md §3.2, sandbox §1): 部署时编译为原生码并缓存——tick 时仅需实例化已编译模块。避免了 fork-per-tick 的 2.5-5s 开销。Worker 按 `min(256, active_players)` 动态伸缩，空闲 5min 回收。严格 Store reset（线性内存清零、fuel 重置）防止跨 tick 状态泄漏。
- **FDB 重试下的 COLLECT 缓存** (01-tick-protocol.md §3.5, persistence §7): FDB commit 失败时复用 canonical COLLECT buffer——不重新执行 WASM、不追加扣费。collect_id/attempt_id/commit_id 三标识追踪完整生命周期。跨重试燃料消耗上限 = 1 × MAX_FUEL。
- **Per-player fair-share 预算分配** (engine.md §3.4.2): pathfinding 100,000 explored nodes/tick 按活跃玩家数均分 + 调用顺序消耗 + 先到先得。防止单玩家垄断。同一机制适用于 host call 预算（1,000/tick/player）。
- **确定性截断** (engine.md §3.4.4, spec §2.3): 快照超 256KB 时按 priority bucket + stable entity_id sort 截断。排序键完全基于世界状态中的确定值（距离、entity_id、分桶归属）——不使用墙钟/随机数。含 `truncated` flag + `omitted_count` 给 WASM 代码降级信号。
- **Blake3 单原语** (tech-choices.md §8): 覆盖哈希 + PRNG，减少依赖栈，审计面减半。`update_with_seek(seed, player_id * 256 + counter)` 一行代码替代 ChaCha keystream 管理，per-player per-tick 确定性随机序列天然适配。
- **Spawn 时序精心设计** (engine.md §3.2): death_mark 释放 room cap → spawn 消费 → spawning_grace (免疫) → combat。RoomCap 中间态保护规则明确，防止新系统插入此区间时的读写竞争。

---

## Findings

### Critical: 无

### High

**H1: Worker Pool 容量假设与实际默认值矛盾**

- 位置: engine.md §3.4.2 "1000 Player Capacity Derivation"
- 严重度: **High**
- 问题: 1000-player 场景推导明确假设 "1000 workers, p50=5ms, 理论 peak = 5000ms 但并行化为 ~25ms wall-clock (1000 workers / 40 cores)"。但默认 `worker_pool_max = 256`（api-registry.md §5.2 未显式声明，engine.md 声明为 256 default / 1000 hard cap）。
- 影响: 以 256 workers 处理 1000 players → 每 worker 处理 ~4 players → 串行 4 × 5ms = 20ms per worker。256 workers / 40 cores = 6.4 workers/core → context switch 开销不可忽略。实际 wall-clock 远高于 25ms 假设。
- 建议: 明确 1000-player 场景需要运营商手动调高 `worker_pool_max` 至 ≥ 500 的文档和 runway 说明。或重新计算 256-worker 下的 1000-player 容量证明——当前推导基于错误假设。

**H2: FDB 单事务串行化 — 500+ 玩家下的竞争热区**

- 位置: 01-tick-protocol.md §3.5, engine.md §3.4.2
- 严重度: **High**
- 问题: EXECUTE 阶段包裹在单一 FDB 事务中（"全或无"）。所有玩家的所有命令 + 所有 ECS system 效果在同一个事务中原子提交。500 玩家 × 最多 100 命令 = 最多 50,000 次实体变更。单个事务内的竞争窗口 = 整个 EXECUTE 阶段（≤400ms budget）。
- 影响:
  - FDB 事务冲突率随活跃玩家数非线性增长——任何两个玩家操作同一房间的同一实体（Source、Controller、建筑）都产生 write-write conflict
  - 3 次重试 + 每次 1s 等待 → 最坏情况 3s retry latency → tick deadline miss（目标 3s）
  - 连续 3 次放弃 → 引擎降级模式——此阈值可能在高负载下频繁触发
  - 单事务大小需 < 10KB（persistence §8），但 replay-critical subset 包含 commands + rejections + fuel_ledger + deploy_activation_decision——500 player 规模的字段体积未做上界推导
- 建议: (a) 提供 FDB 事务冲突率与活跃玩家数的基准测试预期；(b) 评估按房间分区事务的可行性（rooms 天然隔离）；(c) 明确 409 Conflict 的降级策略阈值是否可配。

**H3: Pathfinding 全局预算在 scale 下严重不足**

- 位置: engine.md §3.4.2, api-registry.md §5.2
- 严重度: **High**
- 问题: 全局 pathfinding budget = 100,000 explored nodes/tick。500 活跃玩家 fair-share = 200 nodes/player。每玩家 10 次调用上限 → 每次仅 20 nodes。
- 实际 A* 行为: 50×50 房间（2500 cells），最短对角线穿越需要展开至少 50-70 节点。在复杂地形（swamp/wall/建筑阻挡）下，A* 展开量可达 500-2000 节点——远超 20 节点配额。20 节点只能完成半径 ~4-5 格的邻居移动。
- 影响: 在正常负载下（500 players，每人 1-2 次寻路调用），budget 可能 sufficient。但若有玩家密集寻路（如大规模 drone 调动），先到先得的份额消耗模型意味着后到玩家拿到 0 节点份额——path_find 全部 deterministic fail。这削弱了寻路作为一种战术工具的价值，与 "编程游戏" 定位矛盾。
- 建议: (a) 提供 50×50 房间 A* 的展开节点数 benchmark；(b) 评估将 budget 提高至 500,000-1,000,000 的可行性；(c) 考虑 per-room pathfinding cache 分摊重复计算（多个 drone 穿越同一房间时可复用）。

### Medium

**M1: Bevy World 深拷贝延迟 — 缺大规模 benchmark**

- 位置: 01-tick-protocol.md §3.5 "必须捕获的 Resource 类型" + Component 清单, engine.md §3.4.1 (≤50ms p99 budget)
- 严重度: **Medium**
- 问题: Phase 2a 前进程深拷贝 Bevy World——所有实体（最多 50,000）的所有 Component + 所有 Resource。snapshot scope 包括 Transform、Owner、Body（多个 part 组件）、Resource、Health、Combat、Status、Room、Structure、Terrain、Visibility、Metadata 等 12+ 类 Component。50ms p99 budget 是否覆盖 50,000 entity 深拷贝未提供 benchmark 数据。
- 影响: 若深拷贝超过 budget，snapshot 构建将吃掉 EXECUTE budget，cascading 到 tick deadline。
- 建议: CI 中增加 `snapshot_clone_benchmark(50_000 entities)` 测试，验证 p99 ≤ 50ms。

**M2: Snapshot Truncation 的 "rich get richer" 效应**

- 位置: engine.md §3.4.4, 01-tick-protocol.md §2.3
- 严重度: **Medium**
- 问题: 截断算法的 priority bucket 为 self > friendly > enemy > building > NPC > resource。当玩家视野内有大量敌方实体时（被包围场景），敌方实体占据 snapshot 容量 → 挤压自机和友方的信息空间。滥用检测标记 `visibility_abuse` 降低 COMBAT 优先级，但它处理的是攻击方（制造实体的一方），而非受害方（被截断的一方）。受害者 snapshot 质量下降不是由自身行为引起的。
- 影响: 被多个对手包围的玩家即使有正常侦察需求，snapshot 仍被截断。`truncated` flag + `omitted_count` 提供了降级信号，但核心桶（Spawn/Controller/depot/storage）无条件保留的保证在极端场景下可能被稀释。
- 建议: 明确核心桶实体的数量上限（如 "前 20 个核心实体无条件保留，超出部分进入 general pool"）。

**M3: TickTrace 序列化 buffer 10MB 上限 — 接近高负载边界**

- 位置: persistence-contract.md §8, engine.md §3.4.7
- 严重度: **Medium**
- 问题: "TickTrace 序列化后最大 10MB buffer；超限 → tick 放弃 + metric 告警"。10,000 active drones × 详细 state diff + 500 players × commands + rejections + fuel_ledger + per-system metrics → 可能逼近 10MB。
- 影响: tick 放弃在高负载下如果由 buffer overflow 触发而非 FDB contention，诊断会复杂化。两种失败模式（FDB commit fail vs buffer overflow）需要不同的恢复策略，但都导致 tick 放弃。
- 建议: (a) 提供 10,000 drone 场景的 TickTrace 序列化体积估算；(b) 在 tick 开始前预计算预估体积，若超限提前降级（如 skip debug/rich trace、减少 per-system metrics），而非在 commit 阶段才失败。

**M4: Wasmtime 版本锁定 + CVE SLA 间的张力**

- 位置: sandbox.md §2.1, §6
- 严重度: **Medium**
- 问题: `wasmtime = "=30.0"` 锁定版本。CVE SLA: Critical 24h、High 72h。若 Wasmtime 发布 critical CVE 修复，但 Bytecode Alliance 的发布节奏不匹配 24h SLA → 引擎要么在未修复状态下运行，要么暂停 WASM 部署。
- 影响: WASM 部署暂停意味着所有玩家（人类 + AI）无法更新代码——对 live service 是重大事件。
- 建议: 明确 "暂停 WASM 部署" 的具体范围（仅新部署 or 包含已部署模块的执行？）。考虑预留 emergency patch 机制（hot-patch wasmtime via `cargo patch`）。

### Low

**L1: Worker 强制替换周期 (1000 ticks) 的容量抖动**

- 位置: engine.md §3.4.3, sandbox.md §1
- 严重度: **Low**
- 问题: Worker 最多服务 1000 tick（~50min）后强制替换。替换涉及进程 teardown + 重建 + seccomp/cgroup 重新绑定。若多个 worker 同时达到 1000 tick 阈值（同批次启动），可能触发同步替换 → 瞬时容量下降。
- 建议: 引入 jitter（±50 tick）分散替换时间点；或采用 rolling replace 策略（一次最多替换 pool 的 10%）。

**L2: Arena 与 World 预算完全隔离 — 模式切换路径未明**

- 位置: engine.md §3.4.1, §3.4.2
- 严重度: **Low**
- 问题: Arena 使用独立 budget（300ms tick / 200ms collect / 50ms execute），但引擎是同一进程。若 World 和 Arena 共存（同一 engine 进程），两者的资源竞争未建模。
- 建议: 明确同一 engine 进程是否支持 World + Arena 共存。若不支持（推荐），在启动时校验；若支持，需 resource partition 合同。

**L3: `host_get_objects_in_range` 的 64KB 输出与 snapshot 256KB 的关系**

- 位置: api-registry.md §4.3, engine.md §3.4.2
- 严重度: **Low**
- 问题: `host_get_objects_in_range` 最多返回 64KB——此数据在 snapshot 之外额外传输。若 WASM 在 tick() 中调用 5 次此 host function（上限），额外数据传输可达 320KB。这不计入 256KB snapshot cap，但与 snapshot 数据共同构成 COLLECT 阶段的 per-player 数据传输量。
- 影响: 网络 I/O 层面，per-player 实际数据量可能是 256KB (snapshot) + 320KB (host fn outputs) = ~576KB。在 500 players 下 = 288MB aggregate。虽非硬性限制，但若 snapshot 和 host fn 输出共享传输通道（gRPC unix socket），可能成为 hidden bottleneck。
- 建议: 文档化 snapshot + host fn 输出的 aggregate per-player 数据传输量预期。

---

## Scaling Limits

### 单节点垂直扩展

| 指标 | 当前预算 | 500 players 负载 | 1000 players 负载 | 瓶颈判断 |
|------|---------|-----------------|-------------------|---------|
| Snapshot build | 50ms p99 | OK — O(E + P × rooms) | OK — rooms 不变 | 非瓶颈 |
| COLLECT dispatch | 2500ms | 饱和 (500 × 5ms) | 超出 (需 256+ workers) | **主要瓶颈** |
| EXECUTE (2a+2b) | 400ms | 未知 — 依赖命令密度 | 未知 | 需 benchmark |
| FDB COMMIT | 50ms p99 | 可能饱和 — 单事务竞争 | 高风险 | **次要瓶颈** |
| Pathfinding | 100K nodes/tick | 饱和 (200/player) | 严重不足 (100/player) | **功能瓶颈** |

### 水平扩展路径

设计预留了三层扩展模型（单实例 → FDB 分层缓存 → 水平分片），但 Phase 1 仅覆盖单实例。关键观察：

- **房间天然是分片边界**：房间间仅通过出口连接，移动穿越出口是显式事件。这使 room-based sharding 成为自然的扩展策略——与单实例的兼容性高。
- **快照按房间分片** 已在单实例架构中实现——此为水平分片的基础设施。
- **跨分片移动** 是远期关注——数据模型和 API 设计已预留分片接口。当前不应过度设计。

---

## Concurrency Risks

### FDB 事务热区分析

FDB 单事务串行化是当前架构中最显著的并发瓶颈：

```
同一 tick 内的并发冲突场景:
┌─────────────────────────────────────────────┐
│ Room (0,0): Player A harvest Source X       │  ← 写入 Source.components
│ Room (0,0): Player B harvest Source X       │  ← 同一 key → conflict
│ Room (0,0): Player C attack Drone D         │  ← 写入 Drone.health
│ Room (1,0): Player D move to (1,1)          │  ← 写入 Drone.position
│ Room (2,3): Player E build at (5,7)         │  ← 写入 Terrain + Structure
│ ...                                         │
│ 所有变更 → 单一 FDB transaction → atomic     │
└─────────────────────────────────────────────┘
```

冲突概率随以下因素增长：
- 活跃玩家密度（per-room 玩家数）→ 同一房间的争夺
- 命令密度（per-player commands/tick）→ 更多写入 key
- 实体密度（per-room drones/structures）→ 更多潜在冲突目标

**缓解因素**（设计中已有）：
- Phase 2a inline 模型——命令逐条校验基于当前 Bevy World 状态，先到先得已解决同 tick 内同实体竞争（无需 FDB 层面检测，因为只有一个 writer）
- COLLECT 结果跨重试缓存——不重跑 WASM 减少不确定性

**缺失的缓解**（建议补充）：
- FDB transaction 按房间分区（若 FDB 支持 tenant/directory layer）
- 事务冲突率监控 + 自适应退避
- 降级模式触发阈值可配置

### Worker Pool 并发模型

Worker pool 的竞争点在于：
- Pool 大小 vs 玩家数不匹配 → queuing → COLLECT 阶段延迟
- Per-worker 资源隔离（cgroup/seccomp）是静态的——worker 间无动态资源转移
- 新玩家加入时若 pool 满且无空闲 worker → fork 新 worker → fork 开销在 tick 内发生

---

## Latency Budget Decomposition

端到端 Tick Pipeline 延迟预算分解（World 模式，500 活跃玩家，p50 scenario）：

```
Tick N 生命周期总延迟: 目标 ≤ 3000ms

Phase 1: SNAPSHOT BUILD                          ≤50ms p99
  ├─ Bevy World 深拷贝                     ~15ms
  ├─ 按房间分片 (并行)                      ~5ms
  └─ 每玩家视野过滤 + 截断 (并行)           ~20ms

Phase 2: COLLECT (sandbox dispatch)              ≤2500ms
  ├─ Worker pool dispatch overhead          ~50ms (256 workers × ~0.2ms)
  ├─ Per-player WASM execution (p50)        5ms × 500 = 2500ms (并行化为 ~50ms wall-clock)
  ├─ Command collection + validation        ~20ms
  └─ Worker pool return + cleanup           ~10ms

Phase 3: EXECUTE (2a + 2b)                      ≤400ms
  ├─ Phase 2a: Inline command loop           ~150ms (取决于命令数)
  ├─ Phase 2b: ECS systems serial spine      ~200ms (29 systems, 3 parallel sets)
  └─ Bevy World snapshot (pre-rollback)      ~50ms (included in 2a/2b budget)

Phase 4: FDB COMMIT                              ≤50ms p99
  ├─ FDB transaction begin + write           ~30ms
  ├─ FDB commit confirmation                 ~20ms

Phase 5: BROADCAST                               ≤50ms
  ├─ Delta computation                       ~20ms
  ├─ Dragonfly cache update                  ~10ms
  └─ NATS publish + WebSocket fanout         ~20ms

─────────────────────────────────────────────────
Total (p50):                              ~2700ms
Margin:                                     ~300ms
```

**关键观察**:
- COLLECT 阶段的 wall-clock 取决于 worker pool size 和 per-player WASM execution time。500 players × 5ms p50 = 2500ms 总计算量，在 256 workers / 40 cores 上并行化为约 60-80ms wall-clock——仍在 budget 内。
- EXECUTE 阶段的 400ms 是最大不确定性来源——Phase 2a 命令密度和 Phase 2b 系统复杂度直接影响。
- FDB COMMIT 50ms 是 p99 约束——p50 应显著更低（~20ms）。
- 300ms margin 对于 p99 tail latency 不够充裕——若 WASM p99 = 15ms（而非 5ms），500 players × 15ms = 7500ms 总计算量，即使并行化也会推高 wall-clock。

---

## CrossCheck — 需跨方向检查

- **CX1**: FDB 单事务串行化模型 —— 所有玩家的所有命令 + 所有 ECS 效果在单一原子事务中。**建议 Architect 检查**: 按房间分区 FDB 事务的可行性；单事务大小上界在 500/1000 player 下的推导；FDB 事务冲突率的建模与基准。
- **CX2**: Worker pool 256 default 与 1000-player scenario 的 1000-worker 假设矛盾。**建议 Architect 检查**: 1000-player capacity derivation 是否需要修正；`worker_pool_max` 默认值 256 的理由；运营商手动调高至 500+ 的 runway 和风险。
- **CX3**: Bevy World 深拷贝的 scope 包含 "所有实体上的所有 Component"——在 50,000 entities 下，深拷贝延迟是否能满足 ≤50ms p99 budget。**建议 Architect 检查**: 各 Component 的序列化/克隆开销；是否需要 lazily copy (CoW) 策略。
- **CX4**: Pathfinding 全局 budget (100,000 explored nodes/tick) 在 500 players 下 fair-share = 200 nodes/player/10 calls，对于 50×50 房间的 A* 是否足够。**建议 Architect + Gameplay 联合检查**: A* 在标准 Swarm 地形中的展开节点数分布；预算是否需要上调至 500K-1M；per-room cache 分摊方案的可行性。
- **CX5**: Snapshot 256KB cap + host fn 64KB × 5 = 320KB extra per player = 576KB aggregate。在 500 players 下 = 288MB/3s = 96MB/s 的 unix socket 流量。**建议 Architect 检查**: gRPC unix socket 在此吞吐量下的延迟特征；是否需要 per-player data streaming 上限。
- **CX6**: WASM 预编译模块的缓存键包含 `security_epoch`——security_epoch bump 会导致全量缓存失效，触发所有活跃模块重编译。**建议 Security 检查**: security_epoch bump 的触发条件（是否包括 CVE patch？）；全量重编译时 5 concurrent compilations 限制是否会导致部署 backlog；是否需要 warm-up 机制。
