# R15 Performance Review — DSV4 Pro

**Reviewer**: Performance Reviewer (DeepSeek V4 Pro)
**Date**: 2026-06-18
**Documents reviewed**:
- `design/README.md`
- `design/engine.md`
- `design/tech-choices.md`
- `specs/core/01-tick-protocol.md`
- `specs/core/04-wasm-sandbox.md`

---

## 1. Verdict

**CONDITIONAL_APPROVE**

设计在性能维度展现了扎实的工程思维：WASM 预编译消除 JIT 热路径、两阶段快照架构将复杂度从 O(P×E) 降到 O(E+P×R)、燃料计量（fuel metering）替代墙钟公平可审计、FDB 单事务保证原子性。这些决策在 MVP 规模（500 活跃玩家）下合理可行。

但有 3 个 Critical 和 4 个 High 问题需要在进入实现阶段前解决。全部 11 个问题见下。

---

## 2. Issues Found

### Critical

**C1 — COLLECT 预算零裕度：沙箱 deadline = COLLECT 总预算 (2500ms)**

`engine.md §3.4.1` 将 COLLECT 阶段预算和 per-player sandbox deadline 均设为 2500ms。但 COLLECT 阶段不仅包括 WASM 执行：还包含快照分片分发（每个玩家拼接最多 9 个房间分片）、gRPC 调用往返延迟、结果收集与校验。在 per-player sandbox 刚好消耗 2500ms 的边界情况，COLLECT 必然超时。实际上 dispatch overhead 至少需要 5-20ms（500 玩家 × 分片分发 + 结果收集），这意味着有效 sandbox deadline 实际只有 ~2480ms，但设计文档未体现此差异。

**建议**: 将 COLLECT 预算设为 2550ms（2500ms sandbox + 50ms dispatch margin），或降低 per-player sandbox deadline 至 2450ms。

**C2 — Tick p99 预算 (3050ms) 超过软截止 (2500ms)，持续触发告警**

`engine.md §3.4.1` 的阶段预算之和为 50+2500+400+50+50 = 3050ms。虽在硬截止 4000ms 内（`specs/core/01 §8.1`），但远超软截止 2500ms。更关键的是，`specs/core/01 §5` 将 `tick_duration_p99 > 2800ms` 设为告警阈值——而 p99 预算本身已达 3050ms，意味着系统在正常负载下将持续触发告警。告警疲劳将掩盖真正的性能退化。

此外，BROADCAST 虽标注「无硬限制（异步发布）」，但其 50ms 预算在关键路径上（BROADCAST 完成后才释放 tick 资源、推进 tick_counter）。若 BROADCAST 需 50ms，则整个 tick 关键路径至少 3000ms（不含 SNAPSHOT）。

**建议**: 重新分配预算，使 p99 在 2800ms 告警线以下。可能的调整：(a) EXECUTE 从 400ms 压到 300ms（需对命令量做更严格限制或优化 inline apply）；(b) COMMIT 从 50ms 压到 30ms（确保 FDB 事务 <1MB）；(c) 或将 tick_interval 目标调整为 3500ms。

**C3 — FDB 单事务瓶颈：500 玩家所有变更在一个事务中**

`design/engine.md §3.2` 和 `specs/core/01 §9.4` 确认所有玩家状态变更在单一 FDB 事务中原子提交。FDB 推荐事务大小上限为 10MB。在峰值负载下（500 玩家 × 平均 100 条有效指令 × 每条指令 ~200 bytes 状态变更 ≈ 10MB），事务已接近上限。若个别玩家产生更多有效变更（combat/damage 散射到多个 entity），事务大小将超限。

更隐蔽的风险：FDB 事务冲突不是只有大小问题。在 `§9.4` 的「事务大小约束」中提到大型 binary 写入对象存储——这缓解了大小问题，但 **事务冲突概率** 随写入 key 数量增长。500 玩家竞争同一批 key（如热门 Source、Controller、Spawn 区域），FDB 的乐观并发控制在 key 热点下冲突率急剧上升。`§3.5` 规定重试 3 次后 tick 放弃——在高冲突率下，连续 3 次冲突的概率不可忽略。

**建议**: (a) 明确单事务 key 数量上限（建议 ≤5000 keys/tick）；(b) 设计写入合并策略（同一 key 多次写入合并为一次）；(c) 为高冲突率场景（如新世界开局所有玩家同时 Claim）设计专门的冲突缓解策略；(d) 定义 FDB 事务冲突率的 SLO（建议 <1% tick 重试，<0.01% tick 放弃）。

### High

**H1 — Bevy World 深拷贝：50000 entities 的序列化在 50ms 内完成**

`specs/core/01 §2.3` 描述为「Bevy World 深拷贝」但实际是序列化（`序列化完整世界状态为结构化快照`）。50000 entities 每个平均 200 bytes = 10MB 序列化输出。在 Rust 中 10MB 序列化 + 反序列化在 50ms 内需要 200MB/s 吞吐。虽在优化良好的二进制格式（如 bincode/postcard）下可实现，但 Bevy 的 reflection-based 序列化通常慢一个数量级。`engine.md §3.4.1` 将 SNAPSHOT 预算设为 50ms p99 可能过于乐观。

**建议**: (a) 确认序列化方案（是否为 Bevy 的 Scene/Reflect 还是定制二进制格式）；(b) 在 50000 entities 负载下 benchmark 实际序列化延迟；(c) 若超限，考虑增量快照（仅序列化 dirty entities）而非全量深拷贝。

**H2 — Worker pool 动态扩容延迟：突发玩家加入的响应时间**

`engine.md §3.4.3` 规定 pool 大小按 `max(min_pool, active_players)` 动态伸缩。当活跃玩家从 100 突增至 500（如直播活动、赛事开始），需创建 400 个新 worker。每个 worker 需要：cgroup v2 初始化 + seccomp 加载 + namespace 创建 + Wasmtime Engine 初始化。即使优化到每个 worker 100ms 启动时间，400 个并行创建也需数秒（受 CPU 核心数限制）。在此期间多个 tick 将在 worker 不足的情况下运行——玩家代码执行延迟增加，可能导致超时和空指令。

**建议**: (a) 实现预热池（warm pool），保持 pool 大小为 `max(min_pool, active_players + warm_margin)`，warm_margin = 10-20%；(b) 限制扩容速率（每 tick 最多新增 N 个 worker）；(c) 在扩容期间的 tick 降级处理（如限制每玩家 fuel 至 50%）。

**H3 — 连续 3 次 FDB 提交失败 → 降级模式：恢复策略不明确**

`specs/core/01 §6.2` 规定连续 3 次 tick abandon → 降级模式（暂停新玩家加入、暂停部署）。但降级模式中的恢复策略仅一句「连续 10 tick 正常 → 自动退出降级模式」。未定义：(a) 降级期间的世界状态一致性保证（是否有部分玩家状态不一致）；(b) 降级期间是否继续广播；(c) 降级期间管理员介入的具体操作（如何诊断冲突源、如何解除降级）；(d) 降级模式对已有玩家的体验影响（他们的 drone 是否仍然行动、fuel 是否正常扣除）。

此外，降级触发条件「连续 3 次 tick abandon」过于敏感。在正常 FDB 运维（如 rolling restart）期间，可能触发间歇性冲突导致无意义的降级。

**建议**: (a) 定义降级级别的梯度（Level 1: 暂停新玩家, Level 2: 暂停部署, Level 3: 暂停所有沙箱执行）；(b) 增加降级触发的前置条件（如连续 5 次而非 3 次）；(c) 明确管理员恢复 runbook；(d) FDB 运维窗口内抑制降级触发。

**H4 — Per-tick Store Reset 成本：64MB 线性内存清零 + Instance 重建**

`specs/core/04 §1` 描述 Worker Pool 模型：每 tick 重置 Wasmtime Store（清空线性内存、重置 fuel counter、重建 Instance）。64MB 线性内存清零按 ~10GB/s 内存带宽计算需 6.4ms。500 个 worker 同时执行此操作时，总内存清零量为 500 × 64MB = 32GB，即使分散在各 worker 进程中也消耗可观的内存带宽。加上 Instance 重建（链接 host functions、初始化 memory segments），单 worker 的 reset 成本可能在 8-15ms 范围。

这不包含在 COLLECT 的 2500ms 预算中（2500ms 是 sandbox deadline + 结果收集，Worker reset 在分发前）。但 Worker reset 仍在关键路径上——它在每个 tick 的 sandbox 分发之前完成。500 个 worker 串行 reset = 4-7.5s，不可接受；并行 reset 受 CPU 核心数限制，在 32 核机器上约需 125-235ms。

**建议**: (a) 实现增量 reset——不清零整个 64MB，仅重置 WASM 堆的已使用页（track dirty pages）；(b) 使用 memory pool——预清零的内存页池，tick 时交换指针而非 memcpy；(c) Benchmark 实际 reset 成本并在预算模型中体现。

### Medium

**M1 — Host function 调用开销：可见性过滤按调用重复执行**

`specs/core/04 §3.2` 规定所有 host function 返回结果经 `is_visible_to` 过滤。在 500 玩家 × 5 次 `host_get_objects_in_range` = 2500 次调用/tick 下，每次 `is_visible_to` 可能涉及多个房间的可见性计算。若每个调用平均 1ms（可见性计算 + 序列化），总开销 = 2.5s。虽在并行 sandbox 中分散，但各 host function 调用共享引擎端的 CPU——引擎需要处理 2500 次串行查询（因为 Bevy World 在 COLLECT 阶段是只读的，host function 查询需要访问同一份数据）。

`specs/core/04 §8` 的 host function 成本表仅列出 fuel 成本（WASM 侧），未列出引擎侧的 wall-clock 成本。

**建议**: (a) 为 host function 实现批量查询接口（一次调用查询多个范围）；(b) 预计算可见性位图（per-player per-room），host function 查表而非实时计算；(c) 限制全局 host function 调用总 wall-clock（如 ≤500ms/tick）。

**M2 — Keyframe 写入（每 100 tick）可能导致周期性 tick 尖峰**

`engine.md §3.4.7` 规定每 K=100 tick 写入一次 keyframe。50000 entities 的全量序列化（~10MB）写入 FDB/对象存储。虽 `specs/core/01 §9.4` 说大型 binary 写入对象存储而非 FDB 事务内，但 keyframe 写入仍消耗 IO 带宽。在 keyframe tick，FDB commit 可能因对象存储写入延迟而延长。这导致每 100 tick（300s = 5min）出现一次周期性延迟尖峰，影响玩家体验的一致性。

**建议**: (a) 将 keyframe 写入完全异步化——tick commit 仅记录 keyframe 指针，实际写入在后台完成；(b) 或使用增量 keyframe（仅写入与上一 keyframe 的差异）；(c) 在 keyframe tick 额外分配 1-2s 的 tick 预算缓冲。

**M3 — Snapshot 截断导致信息不对称：玩家间不公平竞争**

`engine.md §3.4.4` 和 `specs/core/01 §2.3` 定义 256KB snapshot cap + 优先级分桶截断。当某玩家因 snapshot 截断而丢失关键信息（如敌方 Tower 位置），而攻击方因 drone 较少（snapshot 小，不截断）拥有完整视野时，形成信息不对称。虽 `§2.3` 的反滥用检测可标记「实体膨胀攻击」，但正常游戏场景（如 RCL8 房间密集建筑群）也会触发截断，使守方因信息劣势处于不利。

截断的确定性保证（`§2.3` 中的截断确定性保证段落）是好的——但确定性的截断仍是截断。引擎侧未对截断玩家提供补偿策略（如 fuel 折扣或优先顺序提升）。

**建议**: (a) 对截断玩家提供 `omitted_counts` 的统计分布（按 bucket），帮助 WASM 代码推理丢失信息的类型；(b) 考虑截断玩家的 fuel 补偿（如截断超过 20% 返还 10% fuel）；(c) 截断率作为公平性指标纳入监控。

**M4 — COLLECT 结果跨重试缓存：首次 COLLECT 的「坏」结果被固化**

`specs/core/01 §4`（应该是 §8.4 附近）规定 FDB commit 失败重试时复用首次 COLLECT 结果。这意味着某玩家在首次 COLLECT 中因外部原因（如 worker 负载抖动）导致部分 host function 超时或性能下降，其结果在后续重试中被固化。虽整体上是正确设计（避免重跑 WASM），但在边际情况下可能不公平——某个玩家因为首次 COLLECT 时的瞬时 worker 过载而获得空指令，其他玩家正常。

**建议**: 记录首次 COLLECT 中各玩家的 wall-clock 和 host function 延迟。若某玩家的 COLLECT 延迟 >2× 中位数且产生了空指令，在 FDB 重试失败后考虑重新执行该玩家的 COLLECT。

### Low

**L1 — Idle pool 清理的 OS 级 churn**

`engine.md §3.4.3` 规定空闲 worker 5min 后回收。在 500 worker 的池中，若 100 个因玩家下线变为空闲，每 5min 回收 100 个进程 = 每 3s 回收 1 个。虽频率不高，但进程销毁涉及 cgroup 清理、namespace 拆卸、PID 回收——在极端情况下（大量玩家同时下线）可能造成短暂的内核资源争用。

**建议**: 实现惰性回收——空闲 worker 不主动销毁，保持为 warm standby；仅当 pool 总大小超过 `active_players + max_idle` 时才回收。

**L2 — Pathfinding cache miss penalty 未量化**

`specs/core/04 §8` 中 `host_path_find` 成本公式包含 `cache_miss_penalty`，但未给出具体数值。在动态世界（建筑频繁建造/摧毁）中，terrain 变更导致缓存频繁失效。cache miss penalty 的不确定性使得 per-player 路径寻找的 wall-clock 不可预测——可能成为 2500ms sandbox deadline 下的长尾延迟来源。

**建议**: (a) 量化 cache_miss_penalty（建议通过 benchmark 在 50×50 房间、500 obstacles 下测量）；(b) 在 host function 成本表中给出 p50/p99 cache_miss_penalty 值；(c) 实现渐进式缓存失效（仅失效受 terrain 变更影响的路径，而非全量）。

---

## 3. Strengths

1. **WASM 预编译 + Worker Pool 架构**：部署时预编译消除 tick 热路径的 JIT 延迟；long-lived worker pool 避免 fork-per-tick 的进程创建开销（fork + seccomp + cgroup 初始化 >2.5s）。这是在高隔离性要求下难得的高效设计。

2. **两阶段快照架构**：从 O(玩家数 × 实体数) 降到 O(实体数 + 玩家数 × 可见房间数)，消除每玩家重复序列化。一次性构建全量快照后按房间分片复用——复杂度降维精准到位。

3. **Fuel metering + Epoch interruption 双重保护**：Wasmtime 原生燃料计量 + epoch 中断 = 确定性 CPU 核算 + 硬超时保护。任一保护失效时另一保护兜底，纵深防御优秀。

4. **FDB 单事务原子性 + Bevy snapshot 恢复**：事务提交失败时 Bevy World 回滚至 Phase 2a 前快照——保证了世界状态与 FDB 的严格一致性。COLLECT 结果跨重试缓存避免重复执行 WASM，精细处理了 fuel 公平性问题。

5. **COLLECT 超时宽容策略**：单个玩家超时不阻塞整个 tick——超时玩家 0 指令，其他玩家正常执行。这是实时系统的关键容错设计。

6. **内存隔离纵深**：OS 级（cgroup 128MB + namespace）+ Runtime 级（64MB WASM 线性内存 + 2MB guard page）+ 应用级（seccomp 白名单）。三层防线无单点。

7. **事务大小约束策略**：将大型 binary payload 移出 FDB 事务（对象存储/append-only log），FDB 仅存指针+hash——避免 tick 事务因大小超限失败。这是正确的 FDB 使用模式。

8. **TickTrace 完整性链**：`chain[i] = Blake3(chain[i-1] || tick_trace_i)` 提供防篡改审计链，任一 tick 损坏可检测。与 FDB 事务原子性配合，杜绝「状态成功但审计缺失」的缺口。

---

## 4. CrossCheck — 需跨方向检查

以下问题超出纯性能视角，需要其他方向评审员介入：

- **CX1**: world_seed 泄露可推导所有未来 tick 的玩家排序和 RNG 输出（`specs/core/01 §3.1` 前向保密威胁模型）。文档承认这是已知风险但依赖服主级秘密保护。实际运维中 seed 泄露的检测和恢复 runbook 是否完备？→ 建议 **Security 评审员** 检查 seed 的生命周期管理、访问控制、泄露检测机制。

- **CX2**: FDB 单事务模型在 500+ 玩家下的事务冲突率、key 热点问题，与 FDB 的乐观并发控制模型如何交互？引擎侧对冲突的处理（3 次重试 → 降级）可能不足以应对生产环境的冲突模式。→ 建议 **Architect 评审员** 检查 FDB 事务设计的冲突模型、key 分布策略、以及是否需要事务分片或写入合并。

- **CX3**: Snapshot 256KB cap 在复杂游戏状态（RCL8 房间 + 大量建筑 + 高密度 drone）下是否充足？截断导致的信息丢失对游戏公平性的影响由谁评估？→ 建议 **Gameplay 评审员** 检查典型游戏场景的 snapshot 大小估算、截断对战术决策的影响。

- **CX4**: 10000 drone 峰值下，每玩家平均 20 drone + 100 drone cap。每个 drone 每 tick 至少产生 1 条 command（Move/Attack 等），意味着 500 玩家可产生 10000+ commands/tick。Phase 2a inline apply 的 O(commands) 在校验阶段的延迟是否可接受？→ 建议 **Architect 评审员** 检查 Phase 2a 的命令校验复杂度、是否有批量化机会。

- **CX5**: 软截止 2500ms 在 p99 预算 3050ms 下持续触发 `tick_duration_p99` 告警——这意味着玩家持续经历「部分玩家被跳过」的 COLLECT 截断。截断体验的玩家感知如何？→ 建议 **Experience 评审员** 检查 tick 延迟对玩家体验的影响、客户端如何处理不完整 tick。

- **CX6**: WASM Worker 与引擎通过 Unix domain socket + gRPC 通信。在高并发 500 worker 下，Unix socket 的吞吐和延迟是否成为瓶颈？gRPC 的序列化开销（protobuf）在 256KB snapshot + command JSON 场景下的表现？→ 建议 **Architect 评审员** 检查引擎-sandbox 通信通道的容量设计。
