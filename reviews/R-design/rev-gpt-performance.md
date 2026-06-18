# R-design Clean-Slate 性能评审 — rev-gpt-performance

Reviewer: 性能评审员（GPT-5.5）
Scope: 仅审阅以下 7 个设计文档：`design/README.md`, `design/auth.md`, `design/engine.md`, `design/gameplay.md`, `design/interface.md`, `design/modes.md`, `design/tech-choices.md`。

## Verdict: REQUEST_MAJOR_CHANGES

设计方向整体正确：WASM fuel metering、ECS deterministic pipeline、两阶段 snapshot、二进制热路径、FDB 原子提交、Dragonfly/NATS/ClickHouse 分工，都是适合“可编程 MMO RTS”的性能基础。但当前性能设计存在几个“看起来已经有预算，实际会炸”的问题：Tier1 容量目标和快照/玩家/实体预算互相矛盾，COLLECT 阶段预算几乎把 3s tick 吃满，技术选型文档与引擎文档在 sandbox 生命周期上直接冲突，FDB 每 tick 提交 16MB 的叙述容易把最坏值当正常值，auth/CRL/nonce/联邦同步也有热路径延迟和风暴风险。

在设计冻结前需要一次性能模型重算：以 tick deadline 为核心，把 snapshot、WASM execution、command validation、ECS execute、FDB commit、broadcast、auth verification、pathfinding/visibility 的 p50/p95/p99 预算和退化策略统一到一个可测试的合同里。

---

## Strengths / 亮点

1. 确定性优先的执行模型是性能上的好选择
   - Tick 生命周期清晰拆成 COLLECT / EXECUTE / BROADCAST。
   - 玩家代码并行运行，命令统一排序执行，避免在 ECS mutating path 中引入跨线程不确定性。
   - `IndexMap`、固定 PRNG、整数/定点数、禁止 std HashMap 迭代顺序依赖，这些都减少了 replay/debug 的性能成本。

2. 两阶段 snapshot 方向正确
   - “tick 开始一次性构建世界快照，按房间分片，每玩家只拼接可见房间”比 `O(players × world)` 的逐玩家序列化正确得多。
   - 这符合大型多人模拟常见成功模式：authoritative world snapshot + per-client/per-agent visibility projection。

3. WASM 预编译 + 实例池是正确路线
   - 部署时编译、tick 时实例化/复用，避免首次 tick JIT 抖动。
   - 使用 fuel metering 而非 wall-clock 计费，能把“慢语言/快语言/硬件差异”从公平性问题变成确定的预算问题。

4. 热路径二进制 ABI 的方向正确
   - 文档明确 JSON 保留给调试/SDK/compat，tick 内 snapshot 和 command 使用 binary canonical encoding/FlatBuffers。这避免了许多游戏服务器早期常见的 JSON 序列化瓶颈。

5. Auth 热路径有性能意识
   - nonce 使用 Dragonfly SETNX TTL，而不是每请求写 FDB。
   - 证书链验证有 Engine 进程内 LRU。
   - Argon2 在 FDB 事务外执行，且恢复凭据的 per-IP 限流在 argon2id 前面，避免 CPU/memory 放大。

6. World 与 Arena 预算分离是必要且正确的
   - Arena 300ms tick 和 World 3000ms tick 不应共享同一组预算；文档已经意识到这一点。

---

## Concerns / 发现的问题

### A1 — Critical — Tier1 容量目标、snapshot 预算与文档中的规模假设互相冲突

文档同时出现这些目标/上限：

- Tier1 快照扩展路线：`50 players × 10 drones = 500 total，≤50 房间，≤16MB/tick，≤50ms 构建`。
- Tier1 性能预算注册表：`Active players = 500 (World)`、`Total drones/entities = 50,000 hard cap`、`Snapshot per-player = 256KB`、`Snapshot total (COLLECT) = 128MB`。
- Room/RCL 表中单房间 drone 上限可到 500，单玩家默认 cap 100。

这些数字不是同一套容量模型。500 players × 100 drones = 50,000 drones，但 Tier1 路线表写的是 500 total drones。500 players × 256KB = 128MB 是“每 tick 玩家输入总量”，但 Tier1 路线表又说全量 Bevy 快照 ≤16MB/tick。若 50,000 entities 进入可见性/序列化/pathfinding，128MB COLLECT 不是边界，而可能是常态。

风险：团队会以为 Tier1 支持 500 活跃玩家和 50,000 实体，实际实现只按 500 drone / 16MB 快照优化；上线后 COLLECT 阶段会被 snapshot 拼接、visibility、pathfinding cache miss 和 WASM memory copy 打爆。

建议：冻结一个唯一的 Tier1 容量合同，至少包含：

- `active_players_target`
- `active_players_hard_cap`
- `active_drones_target`
- `active_entities_hard_cap`
- `rooms_loaded_target`
- `visible_rooms_per_player_p95`
- `snapshot_bytes_per_player_p50/p95/max`
- `snapshot_bytes_total_per_tick_p95/max`
- `commands_per_player_max`
- `pathfinding_requests_per_player_per_tick_max`

如果目标真的是 500 players / 50,000 entities，那么 Tier1 不能继续描述为“全量 Bevy World 深拷贝 ≤16MB / ≤50ms”。应直接采用增量/分片可见性 projection 作为 baseline，而不是把它放在 Tier2。

### A2 — Critical — Tick budget 分配不闭合：COLLECT 2500ms + per-player WASM 2500ms 会吞掉 World 3s deadline

World tick interval 是 3000ms，COLLECT budget 是 2500ms，WASM per-tick budget 也是 2500ms per player。即使玩家 WASM 并行，系统仍需要：

- 构建/拼接 snapshot
- 分发到 sandbox worker
- WASM 实例准备/内存拷贝
- 收集 commands
- command validation
- Phase 2a inline serial execution
- Phase 2b systems
- FDB commit
- delta 计算
- Dragonfly/NATS/WebSocket broadcast

给 EXECUTE + commit + broadcast 只留约 500ms，且没有 p99 tail 策略。500 活跃玩家中只要少数 sandbox 卡到 deadline，或者 pathfinding/cache miss/GC-like memory pressure 出现，tick 就会持续超时。

风险：系统表现为“平均能跑，尾延迟周期性炸 tick”。这类架构在线游戏中非常常见：benchmark 单模块看起来没问题，但 tick coordinator 被 p95/p99 straggler 拖死。

建议：把 tick 预算改为 deadline-driven pipeline，而非单个大 COLLECT budget：

- World 3000ms 示例：snapshot build 100ms，sandbox dispatch+execution 1800ms，command collect 100ms，execute 400ms，commit 150ms，broadcast 150ms，slack 300ms。
- 明确 sandbox deadline：到 T_collect_deadline 未返回的玩家本 tick command 为空/沿用 no-op，而不是拖延整个 tick。
- 每阶段定义 p95/p99 和 overload shedding：降低 snapshot detail、拒绝新 spawn、限制 pathfinding、暂停低优先 MCP read 等。
- Arena 300ms 需要完全独立的更小预算和更严格 cap，不能仅“缓存减半”。

### A3 — High — Sandbox 生命周期在文档中自相矛盾：技术选型写 per-tick fork/kill，引擎预算写实例池

`tech-choices.md` 中 Wasmtime 选择理由写到“per-tick fork 生命周期——每 tick 新 fork，执行完 kill”。但 `engine.md` 性能预算写“WASM instances 池化，min=10/max=500，不每 tick fork/kill；空闲 5min 后回收”。

这不是文字小问题，而是性能架构分叉：

- per-tick fork/kill：隔离强，但 500 players × 3s tick 下进程 churn、page fault、编译缓存映射、IPC 都会成为瓶颈。
- 长生命周期 worker pool：性能可行，但必须设计内存清理、instance reset、fuel reset、WASI capability reset、panic/oom 后替换、tenant residue 防泄漏。

风险：实现团队按不同文档做出不同 sandbox manager，性能测试和安全测试都无法对齐。

建议：明确采用“长生命周期 sandbox worker process pool + per-module precompiled artifact + per-tick instance reset”的模型，并把 `tech-choices.md` 的 per-tick fork/kill 改成“epoch interruption + worker recycle on fault/lease expiry”。同时定义：

- worker 与 player/module 的绑定策略
- instance reset 是否重建 Store/Linker/Memory
- max ticks per worker before recycle
- OOM/timeout 后是否隔离该 module
- IPC payload 上限和 backpressure

### A4 — High — FDB 每 tick提交和 TickTrace 存储预算容易把最坏 16MB 当正常路径，写放大风险高

文档列出 FDB transaction size 16MB，且写道“每 K=100 tick 写 keyframe，其余 tick 写 delta”。计算上，如果每 tick 都接近 16MB，3s tick 一天 28,800 tick，即 450GB/day；若多个世界或 Arena 并行，增长很快。虽然文档说每日预算 ≤500GB，但这已经接近单世界最坏值，而且还没算 TickTrace、auth、analytics、indexes、CRL、replay privacy 多副本/压缩前后差异。

更重要的是 FDB 单事务 16MB 应该是硬上限/异常上限，不应是设计预算。FDB 擅长事务一致性，但不适合作为大 blob tick archive 的主要吞吐通道。

风险：持久世界长期运行后，存储成本、备份恢复、replay 查询、compaction/清理策略先于游戏玩法成为瓶颈。

建议：

- 将 FDB 单 tick 事务预算拆成 `state_mutation_bytes_p95`、`state_mutation_bytes_max`、`trace_pointer_bytes`。
- 大型 TickTrace/keyframe blob 放对象存储或 append-only log，FDB 仅存 manifest/hash/pointer/commit metadata。
- 规定 delta 压缩格式、keyframe retention、replay privacy retention、冷热分层和 GC 策略。
- 将 16MB 定义为拒绝/截断/降级阈值，而不是正常容量目标。

### A5 — High — Pathfinding 和 visibility 被列为缓存大小，但缺少调用预算、复杂度边界和退化策略

设计给了 `Pathfinding cache = 10,000 entries per player`、`Visibility cache = 50,000 entries per player`，但没有规定：

- 每玩家每 tick host_path_find 最大调用次数
- 单次 path_find 最大搜索节点数
- path_find 是否计入 WASM fuel 之外的 engine CPU
- cache key 包含哪些动态障碍/terrain/version
- cache miss 的 p95 成本
- visibility 计算的增量更新策略
- cache 内存总上限：500 players × 10,000 path entries + 500 × 50,000 visibility entries 可能非常大

风险：玩家代码可以合法地把 host_path_find 当免费 oracle 调用，engine CPU 被 host function 耗尽；fuel 只限制 WASM 指令，不自然覆盖 host 侧路径搜索成本。很多 bot 游戏最终瓶颈不是脚本执行，而是 pathfinding 和视野裁剪。

建议：

- host function 必须有独立 cost model，并折算进玩家 fuel 或单独 per-tick quota。
- path_find 返回可降级结果：超预算返回 partial/no_path，并暴露错误码。
- 引入 hierarchical pathfinding / room-level route cache / static terrain precompute。
- visibility 使用 room-level dirty bit + entity movement delta，而不是每 tick 全量扫描。
- 缓存上限应是全局内存预算 + per-player fair share，而不是每玩家固定巨大 cache。

### A6 — High — MCP 读取、经济查询、调试/回放工具可能绕开 tick 热路径限流

MCP 明确不是 gameplay action，这个边界很好；但工具表包含大量读取类接口：snapshot、terrain、objects_in_range、profile、dry_run、replay、economy、trend、explain_last_tick、schema/docs 等。文档只零散提到经济查询独立配额 `10/tick`，未给全局 MCP read budget 和 backpressure。

风险：AI agent 和人类 UI 同时高频读取时，虽然不改变世界状态，却会压垮 snapshot cache、ClickHouse/FDB replay 查询、Dragonfly hot cache 和 Gateway WebSocket/HTTP 带宽。尤其 `swarm_get_snapshot`、`swarm_get_replay`、`swarm_explain_last_tick` 很容易成为“非 gameplay 但比 gameplay 更贵”的接口。

建议：

- 将 MCP read 分为 hot read、warm read、cold read 三类，分别绑定 Dragonfly、ClickHouse/object storage、async job。
- `swarm_get_replay`、`swarm_simulate`、`swarm_explain_last_tick` 不应在 tick coordinator 热路径同步执行。
- 每个工具定义 cost units，而不是简单 requests/min。
- Gateway 对 AI agent 使用 token bucket + response size cap + streaming pagination。
- tick deadline 紧张时，MCP cold reads 自动降级或排队。

### A7 — Medium — Auth p99 预算偏乐观，CRL/联邦同步/证书缓存失效会造成延迟尖峰

Auth 预算写 `p99 10ms cache hit / 50ms cache miss`，CRL 本地允许 60s 延迟，联邦 CRL 60s 同步，首次同步可阻塞 30s。证书链验证缓存 10,000 条 LRU，CRL 更新、证书吊销、Intermediate 轮换会触发失效。

风险：

- 证书吊销/epoch bump/Intermediate rotation 时缓存集体失效，Gateway/Engine 认证 miss 风暴。
- 联邦远端 CRL 失败时策略分支会增加验证路径复杂度。
- WebSocket 握手把 nonce 去重放在 FDB 的描述与后文 nonce 热路径 Dragonfly 可能不一致，若高频连接重连，认证路径可能抖动。

建议：

- 证书验证缓存采用 stale-while-revalidate 或 generation-based invalidation，避免全量瞬时清空。
- CRL delta apply 应异步、批量、带 generation id；热路径只读内存快照。
- WebSocket 握手 nonce 也应走 Dragonfly SETNX TTL，除非明确属于高价值操作。
- Auth p99 预算需要在“cache cold after rotation”和“federation stale”场景下单独定义。

### A8 — Medium — Rhai 模组执行在引擎进程内，虽然有 AST 预算，但性能隔离仍不足

Rhai 模组被视为服主可信代码，并在引擎进程内运行。文档已有 AST 节点硬限制、actions 次数限制、事务回滚、连续超限禁用，这是很好的起点。但性能上仍缺少：

- 多模组总预算，而不只是单模组预算
- state 查询迭代的真实成本上限
- action rollback buffer 的内存上限
- tick_start/tick_end 与主 ECS pipeline 的具体调度位置预算
- 模组日志/事件输出的 backpressure

风险：一个“可信但写坏了”的模组不一定越过单模组节点限制，也可能通过大量合法 state queries/actions/logs 造成 tick tail latency。

建议：

- 增加 per-world mod total budget。
- actions buffer 有 byte cap，超过则整个模组本 tick fail closed。
- state iterator 必须 lazy + quota-aware。
- 模组日志进入 ring buffer，不允许同步阻塞。
- 将 mod execution 纳入 tick budget registry。

### A9 — Medium — Arena 300ms tick 与当前 sandbox/API 模型的开销不匹配

Arena 目标 300ms tick，但仍走 WASM snapshot、host functions、command collection、ECS execute、replay、观战延迟等完整链路。文档仅写 Arena pathfinding/visibility 缓存减半，但没有给 Arena 的独立玩家数、drone 数、snapshot size、WASM fuel、command count、replay write budget。

风险：World 3s tick 下可接受的设计，放到 300ms Arena 会立刻暴露序列化、IPC、pathfinding、broadcast 的固定开销。Arena 需要的是低固定成本和小地图强约束，而不是 World 的缩小版。

建议：Arena 单独定义 hard caps：slots、drones、rooms/map cells、snapshot bytes、path_find calls、commands、replay flush interval。Arena replay 可以异步缓冲，不应每 300ms 同步落完整 trace。

### A10 — Medium — 经济与 PvE 事件增加实体/事件峰值，但没有纳入性能预算

World PvE 事件如 Swarm Invasion 一次生成 30 Swarmling，遗迹激活生成 Guardian/Creep，资源爆发影响再生，NPC AI 不消耗玩家 fuel。它们是确定性内置 AI，但仍消耗 engine CPU、pathfinding、combat、snapshot 和 broadcast。

风险：PvE 事件在玩家密度最高区域触发，恰好打在最热房间；这会把局部热点放大为全局 tick 延迟。

建议：

- NPC 也必须有 per-room/per-world AI budget。
- 世界事件触发前检查当前 tick load，必要时延迟或分批 spawn。
- NPC pathfinding 使用更粗粒度/预计算巡逻路线，不与玩家 host_path_find 争同一预算池。

### A11 — Low — 技术选型中 Blake3 MAC 被称为“代码签名”容易混淆真实性与完整性

`tech-choices.md` 写“代码签名: Blake3 MAC”，但同文后面又说证书、CSR、请求签名和代码签名统一使用 Ed25519。性能角度 Blake3 keyed hash 很快，但 MAC 不是可公开验证的代码签名，要求共享密钥；玩家部署 WASM 的可审计签名应使用 Ed25519 CodeSigningCertificate，Blake3 用于 module_hash/content hash。

风险：实现时把 MAC 当成玩家代码签名，会引入密钥分发和验证模型问题，也会影响缓存 key / artifact provenance。

建议：统一术语：

- `module_hash = Blake3(wasm bytes)`
- `integrity/MAC` 仅用于服务端内部 artifact cache
- `code signature = Ed25519 over module_hash + metadata by CodeSigningCertificate`

### A12 — Low — 前端 Monaco + PixiJS 选择合理，但 500 drone 的渲染目标低于后端 50,000 entity 上限

技术选型说 PixiJS 在 500 drone 下不卡；后端 Tier1 表却给 50,000 entities hard cap。如果客户端只看局部视野，这不是必然矛盾，但文档应明确 Web UI 的渲染预算是“可见实体”而非“世界实体”。

建议：定义前端预算：visible entities p95/max、draw calls、tile chunk size、WebSocket delta bytes、客户端降级策略（隐藏粒子、合并资源、降低 replay speed）。

---

## Missing / 缺失项

1. 统一性能模型
   - 当前有很多局部预算，但没有一个从 tick deadline 出发的端到端模型。
   - 需要一张表把 COLLECT、WASM、host functions、EXECUTE、FDB commit、broadcast、MCP reads、auth verification 全部放进同一 3000ms / 300ms deadline。

2. 负载画像
   - 缺少明确 workload profiles：新手区、密集 PvP、PvE event、Arena 1v1、AI 高频调试、回放下载、证书轮换等。
   - 每个 profile 应有 p50/p95/p99 数据量和操作量。

3. Backpressure / overload policy
   - 当 tick 超时、FDB commit 接近上限、Dragonfly/NATS 慢、MCP read 过载、ClickHouse lag 时，系统如何降级？
   - 需要定义“游戏模拟优先，观战/分析/调试降级”的全局策略。

4. Host function 计费
   - WASM fuel 不能覆盖所有 host 侧成本。path_find、objects_in_range、world_rules、terrain 查询都需要 cost units。

5. 数据保留与冷热分层
   - TickTrace、keyframe、delta、ClickHouse analytics、replay privacy、audit logs 的 retention 和压缩策略没有闭环。

6. Worker pool 与 IPC 协议细节
   - 缺少 sandbox worker pool 的生命周期、fault isolation、memory reset、module cache、IPC payload cap、deadline kill 语义。

7. Performance CI 合同
   - 文档说预算在 CI 回归测试，但未定义基准场景、数据生成器、判定阈值、p95/p99 统计方式。

---

## Recommendations / 建议

1. 先冻结“唯一 Tier1 性能合同”
   - 不要同时保留 500 drones 和 50,000 entities 两套叙事。
   - 如果目标是 500 active players，就按 500 players 设计；如果 MVP 是 50 players，就明确写 50，不要在不同章节混用。

2. 将 Tier2 的增量 snapshot 提前为 baseline 候选
   - 对 MMO RTS 来说，snapshot 是核心瓶颈。若 clean-slate 阶段不考虑实现难度，建议直接采用 modification-set tracking + room visibility projection，而不是 Tier1 全量深拷贝。

3. 建立“host function cost units”
   - 每个 host function 定义 deterministic cost，扣玩家预算。
   - pathfinding 单独设置节点展开上限和缓存 miss 限额。

4. 统一 sandbox 生命周期文档
   - 删除 per-tick fork/kill 叙述，改成 pooled worker + deterministic reset + fault recycle。

5. FDB 只做权威事务元数据和小状态变更，大 trace/blob 外置
   - TickTrace/keyframe 大对象走 append-only object/log storage，FDB 存 hash/pointer/commit manifest。

6. MCP read 与 replay/debug 从 tick coordinator 解耦
   - 所有 expensive read 使用异步 job、分页、response byte cap、cache generation。

7. 引入性能准入测试矩阵
   - 场景至少包括：500 players idle、500 players pathfinding-heavy、dense combat 10 rooms、PvE event hotspot、Arena 300ms 1v1、CRL cache cold、MCP replay download storm。

---

## Phase Ordering / 设计冻结前的排序建议

1. P0 — 统一容量数字与 tick deadline budget
   - 这是所有后续设计的根。没有它，技术选型无法判断对错。

2. P0 — 统一 sandbox worker model
   - 明确 pool、reset、deadline、fault isolation，消除 per-tick fork/kill 冲突。

3. P0 — 定义 snapshot/visibility/pathfinding cost model
   - 这是最大性能风险面，应在 gameplay/API 冻结前完成。

4. P1 — 重写 FDB/TickTrace 存储边界
   - 确定 FDB 事务只承载权威小状态和 manifest，大 blob 外置。

5. P1 — MCP read/backpressure 合同
   - 防止 AI agent 和 replay/debug 工具压垮模拟热路径。

6. P1 — Auth cache/CRL invalidation 压测场景
   - 重点覆盖 cache cold、epoch bump、federation stale。

7. P2 — Arena 独立性能合同
   - Arena 300ms tick 不能作为 World 的缩小版，需要专门 caps。

8. P2 — 前端可见实体与渲染降级预算
   - 与后端 entity cap 对齐，避免 UI 目标只覆盖小规模演示。

---

## Final assessment

当前设计已经有正确的性能直觉，但还不是可冻结的性能架构。最大问题不是“选错技术”，而是预算合同互相打架：500 players、50,000 entities、16MB snapshot、128MB COLLECT、2500ms WASM、3000ms tick、FDB 16MB transaction 这些数字需要被重新放进同一张端到端性能模型。完成上述 P0/P1 修改后，本设计很可能可以转为 CONDITIONAL_APPROVE；在此之前建议 REQUEST_MAJOR_CHANGES。
