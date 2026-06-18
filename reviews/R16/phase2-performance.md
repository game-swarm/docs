# R16 Phase 2 CrossCheck — Performance 补充验证

Scope: 只补充阅读 R16 Phase 1 评审中的 Performance 相关 CrossCheck，不重跑完整评审。主要来源为 `rev-gpt-performance`、`rev-dsv4-performance`、`rev-dsv4-architect`、`rev-gpt-architect`、`rev-dsv4-security`、`rev-gpt-security`；当前 reviews 目录已被清理，因此 Phase 1 报告从 git commit `8c02b92` 读取，同时用当前 `/data/swarm/docs` 设计文档复核现状。

## CrossCheck item -> Finding -> disposition

### 1. target 500 / hard cap 1000 是否绑定硬件基线

Finding:
- 结论：未充分绑定硬件基线，仍是 High。
- 证据：当前 `design/engine.md` §3.4.2 写明单节点 World 容量为 `Active players target 500 / hard cap 1000`，但同节未给 CPU core、内存、worker pool 上限、降级 admission 的最小硬件合同。
- `specs/reference/api-registry.md` 与 `specs/core/04-wasm-sandbox.md` 同时给出 sandbox `cpu.max = 250000 3000000`，即每玩家每 3s 周期可用 0.25 CPU-s。按 500/1000 活跃玩家计算，sandbox 理论峰值为 125/250 CPU-s per tick，约 41.7/83.3 个满载 core，未计入 engine、host-call、FDB、对象存储、网络与调度开销。`rev-gpt-performance` 建议 target 500 约需 ≥48 physical cores、hard cap 1000 约需 ≥96 physical cores；该建议未在当前容量合同落地。
- `rev-dsv4-performance` 还指出 worker 进程按 active_players 扩展时，500 × 128MB = 64GB sandbox cgroup 内存，1000 时约 128GB，外加引擎与缓存，当前文档也未把 target/hard cap 与内存基线绑定。

Disposition: high

### 2. `worker pool = active_players` 是否应改为 `max_pool + admission`

Finding:
- 结论：应改，且是 High；如果继续按 `active_players` 伸缩，应至少明确它只在满足硬件基线时成立。
- 证据：当前 `design/engine.md` §3.4.3 仍写 `Pool: 大小按 max(min_pool, active_players) 动态伸缩`。这正是 `rev-dsv4-performance` C1、`rev-dsv4-architect` X5/M1、`rev-dsv4-security` X3 共同要求交叉确认的问题。
- 性能上，active_players=500/1000 会把 worker 进程、cgroup、seccomp、namespace、FD、内存 commit 与调度器上下文切换一起放大；安全上，共享/独占 worker 的边界也需要明确。按 `max(min_pool, active_players)` 不是 admission contract，而是把并发需求直接外溢到机器规格。
- 推荐改为：`pool_size = min(active_players, max_pool)`，`max_pool` 由 CPU core、memory、host-call budget 与 p99 SLO 共同决定；超过 `max_pool` 的玩家进入确定性 admission/queue/skip 策略。指标需区分 `queued_before_collect`、`skipped_by_admission`、`deadline_timeout`、`cgroup_throttled`。

Disposition: high

### 3. per-player 2500ms deadline 在并行受限时如何重分配

Finding:
- 结论：当前语义在无限并行假设下可解释，但在引入 `max_pool` 后缺少重分配合同；应列为 High。
- 证据：当前 `design/engine.md` §3.4.1 同时列出 `COLLECT ≤2500ms` 与 `Per-player sandbox deadline 2500ms`。`specs/core/01-tick-protocol.md` §8.1/§8.2 进一步说明 `tick_soft_deadline_ms=2500ms`，超过后跳过剩余玩家；但表中 `COLLECT wall-clock per player = 2500ms` 与全局 soft deadline 相同。
- 若 worker pool 受限为 `max_pool < active_players`，固定 per-player 2500ms 会导致队列头部慢玩家消耗整个 COLLECT 窗口，后续玩家被 `skip_remainder` 集体 0 指令。也就是说，deadline 当前不是公平预算，只是单玩家 kill switch。
- 推荐合同：tick 开始计算 `collect_budget_ms = tick_soft_deadline_ms - snapshot_reserve - execute_reserve - commit_reserve - jitter_reserve`；每个玩家的实际 wall deadline 取 `min(configured_per_player_deadline, remaining_collect_budget / remaining_admitted_players)`，或采用固定 quantum + epoch interruption 的轮转。超过可服务容量的玩家应由 admission 明确 deterministic no-op，而不是在队列尾部隐式超时。

Disposition: high

### 4. 50k/100k commands/tick Phase 2a 串行吞吐是否需 blocker

Finding:
- 结论：需要 blocker。Phase 2a 串行吞吐目前没有证明能满足 EXECUTE 预算，且它位于 tick 关键路径。
- 证据：当前 `design/engine.md` §3.4.2 给出 `Commands per player per tick max 100`、active players target/hard cap 500/1000，因此 Phase 2a 最坏输入是 50,000/100,000 commands/tick。`rev-dsv4-performance` H3 按 target 500 估算：若 EXECUTE 400ms 中 Phase 2b 占约 200ms，Phase 2a 只剩约 200ms，50k commands 需要约 4µs/command；hard cap 1000 时 100k commands 更无余量。`rev-gpt-performance` 同样指出 100k commands/tick 的排序、校验、拒绝记录、ECS mutation 是 EXECUTE ≤400ms 的核心瓶颈。
- 当前文档没有看到 per-room 并行 apply、只读预校验并行、命令预归并、按 drone/action 限流、invalid storm trace 聚合等可执行合同，也没有 CI benchmark 证明 50k/100k、80% invalid、热点同坐标/同资源竞争场景的 p99。
- 因为该问题不是单纯优化项，而是 target/hard cap 与 tick budget 的直接可实现性缺口，应提升为 blocker：在共识前需降低命令上限、给出 Phase 2a benchmark 门槛，或把串行 spine 改成“并行 precheck + deterministic conflict merge + bounded serial commit”。

Disposition: blocker

### 5. pathfinding fair-share 100/200 nodes/player/tick 是否产品不可用

Finding:
- 结论：是，当前公平分配安全但产品不可用，至少 High；若 `host_path_find` 是核心 AI API，则接近 blocker。
- 证据：当前 `design/engine.md` §3.4.2 写全局 `Pathfinding budget = 100,000 explored nodes/tick`，并明确按 active_players 均分，500 玩家=200 nodes/player/tick，1000 玩家=100 nodes/player/tick。`specs/core/04-wasm-sandbox.md` §8 的 `host_path_find` 又写单次调用成本按 explored_nodes/expanded_edges，per-player 上限为 10 次调用，返回路径最大 500 nodes。
- 100/200 explored nodes 往往不足以完成一次 50×50 room、有障碍、跨房间出口或不可达目标的 A*，更无法支撑每玩家 10 次 path_find。结果会是高负载下大量 deterministic fail；玩家可能改用 `host_get_terrain` + WASM 内自寻路，把成本转移到 fuel、host calls 与 JSON 交互，反而恶化 COLLECT。
- `rev-dsv4-security` H2 的“单玩家耗尽全局预算”已被当前 `engine.md` 的 per-player fair-share 部分缓解，但 `specs/core/04-wasm-sandbox.md` §8 仍写“per-player/per-tick 上限：10 次调用 + 100,000 explored_nodes 总额度”，容易被读成单玩家也有 100k nodes；需要统一为 per-player fair-share 份额或独立 per-player node cap。
- 推荐改为按 `active_path_users`、active drones、room/shard 或 subscription weight 分配，并提供最低有用额度、negative cache、same-room/exit static path cache、unreachable expansion cap。若预算不足，应在产品层明示 degradation，而不是让核心 API 在 hard cap 下默认不可用。

Disposition: high

### 6. FDB transaction 10KB vs 10MB、object store timeout 与 tick budget 是否冲突

Finding:
- 结论：冲突存在。FDB 大小数字本身可用“目标 vs 上限”解释为 Medium，但对象存储同步写入与 tick budget 冲突是 High。
- 证据：当前 `specs/core/05-persistence-contract.md` §7 写 `FDB 事务大小: 单 tick 事务 < 10KB`；而 `specs/core/01-tick-protocol.md` §8.4 附近写事务大小确保 `<10MB (FDB 推荐上限)`。这两个数字一个像性能目标、一个像硬安全上限，但文档没有显式分层，导致实现者无法判断高活动 tick 的状态 delta 超过 10KB 时是告警、降级还是拒绝。
- 10KB 目标在高活动场景下偏紧：几百个 entity/resource/controller mutations 即可达到 10–25KB。若强行把 delta 压到 10KB 以下，可能牺牲审计/replay 信息；若按 10MB 上限实现，又可能把 FDB commit p99 推高并引入热点。
- 更严重的是 `specs/core/05-persistence-contract.md` §2/§7 要求 Phase B 对象存储先写，且对象存储写入超时为 5s；但 World tick interval 是 3000ms，Arena 默认 300ms，engine 预算中 COMMIT 只有 ≤50ms。同步对象写入、10MB buffer、5s timeout 进入 tick commit 前置路径，会直接破坏 tick p99。`rev-gpt-security` 的对象存储 ACL/immutability 关注是安全补充，但不解决热路径超时问题。
- 推荐：把 FDB `<10KB target / <10MB hard reject` 明确分层，并增加 state delta bytes 指标与压力测试；tick 同步持久化路径只依赖本地 durable WAL/hash + FDB 小事务，Object Store 改为异步归档或受 ≤50/100ms hot-path timeout 限制，Arena 禁止同步对象写。

Disposition: high

## 汇总

- close: 0
- medium: 0（FDB 10KB vs 10MB 单独看可为 medium，但与 object store 同步超时合并后为 high）
- high: 5
- blocker: 1

建议 Speaker 将 Phase 2a 50k/100k 串行吞吐列为共识 blocker；其余 Performance CrossCheck 作为 high-priority design fixes 进入同一轮修订，特别是 `max_pool + admission`、硬件基线、动态 per-player deadline、pathfinding 有用额度、Object Store 脱离 tick 热路径。
