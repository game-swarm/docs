# R-appcert-R2 Performance Review — GPT-5.5

## Verdict

CONDITIONAL_APPROVE

R-appcert-R2 的性能架构方向整体可接受：tick 三阶段、一次房间分片快照、WASM 部署期预编译、编译缓存、CRL 在线窗口、NATS/Dragonfly 非权威缓存、Tier2/Tier3 扩展路线都符合成功的实时仿真/编程游戏架构经验。  

但当前设计仍有若干“看起来安全/确定，实际会炸性能”的模式，尤其是每玩家每 tick fork/kill、JSON ABI 大对象拷贝、Bevy World 深拷贝与 FDB 全状态写入、认证热路径缺少 p99 预算。建议在进入实现前补齐性能预算与基准门槛；若保持这些点模糊，Tier1 可能能跑 demo，但 MVP 500 活跃玩家目标风险偏高。

## Strengths

- **Tick pipeline 边界清晰**：COLLECT / EXECUTE / BROADCAST 拆分合理，WASM 超时不阻塞世界，BROADCAST failure 不回滚已提交 tick，符合高可用实时系统的常见成功模式。
- **快照复杂度意识正确**：从每玩家全量序列化转为 tick 开始一次世界快照 + 房间分片 + 玩家拼接，复杂度从 `O(players × entities)` 降为 `O(entities + players × visible_rooms)`，是必要方向。
- **部署期编译与缓存设计合理**：WASM 在部署阶段预编译，tick 只实例化；缓存键包含 wasmparser / validation policy / wasmtime build / arch / security_epoch，且不跳过部署验证，安全与性能边界较好。
- **资源预算覆盖面广**：fuel、wall-clock、host function 次数、path_find explored_nodes、输出 JSON、编译并发、MCP simulate 配额都有硬限制，避免单玩家 DoS 拖垮 tick。
- **CRL 保留窗口是正确优化**：在线 CRL 只保留未过期和最近过期窗口内条目，避免吊销列表无限增长进入认证热路径。
- **Tiered scaling 路线实用**：Tier1 / Tier2 / Tier3 分层，并明确 Tier1 深拷贝只适用于 MVP，Tier2 使用 modification-set，Tier3 按 room shard，抽象层次基本合理。

## Concerns

### A1 — High — 每玩家每 tick fork/kill 与 3s tick / 500 玩家目标冲突

`04-wasm-sandbox.md` 写明 sandbox worker “每 tick fork → 执行 → kill”，而 `engine.md` 又写 Tier1 MVP 目标是 50 players × 10 drones = 500 total，并在 COLLECT 中“对每个活跃玩家并行 sandbox worker pool”。这两个说法合在一起会产生高常数成本：进程创建、seccomp/cgroup 设置、Unix socket/gRPC 往返、Wasmtime instance 初始化、JSON 拷贝都会落在 2.5s COLLECT 窗口内。

这像很多安全沙箱系统的失败案例：隔离边界非常强，但把“冷启动成本”放进实时热路径。即使单次 fork+setup 只有几毫秒，500 活跃玩家也会在 CPU 和 scheduler 上制造尖峰；如果每玩家还有 0.25 CPU 秒配额，理论并发需求远超普通单节点预算。

建议：
- 将 “每 tick fork/kill” 改为安全可回收的 **warm worker pool**：每玩家或每模块持有短生命周期 worker，tick 后 reset Store/Instance，按 N tick 或异常后 recycle 进程。
- 若安全上必须 fork/kill，必须给出基准门槛：`sandbox_start_p99`、`instance_init_p99`、`collect_wall_p99 @ 50/100/500 players`、`CPU runnable queue`。
- 明确 worker pool 的隔离重置合同：内存清零、Store 丢弃、fuel 重置、epoch deadline 重置、host state 不跨 tick。

### A2 — High — JSON snapshot / CommandIntent ABI 是热路径大对象拷贝瓶颈

WASM ABI 要求 tick 输入是 snapshot JSON，输出是 CommandIntent JSON，单玩家 snapshot 和 output 上限均为 256KB。即使快照先按房间分片，最终仍要为每个玩家拼接、写入 WASM 线性内存、WASM 解析 JSON、输出 JSON、host 再解析。500 活跃玩家情况下，最坏输入拷贝量可达 128MB/tick，且解析成本比拷贝更重。

JSON ABI 很适合作为 SDK/debug/compat 格式，但不适合作为实时 tick 的唯一热路径 ABI。这个模式在游戏服务器、仿真引擎、浏览器插件沙箱中都常见：早期接口直观，后期被 serialization tax 卡死。

建议：
- 保留 JSON 作为 debug/SDK 文档格式，但为 tick 热路径定义 canonical binary ABI，例如 FlatBuffers/Cap’n Proto/Postcard/bincode-like fixed schema。
- 至少定义 Tier1 gate：`snapshot_encode_p99`、`wasm_input_copy_p99`、`command_decode_p99`、`bytes_copied_per_tick`。
- `host_get_objects_in_range` / `host_path_find` 返回值也应使用同一二进制 envelope，避免 host function 内重复 JSON 编解码。

### A3 — High — Bevy World 深拷贝 + FDB 每 tick 完整状态写入会限制 Tier1 上限

`01-tick-protocol.md` 在 COLLECT 开始构建完整世界快照，在 EXECUTE 开始前又对 Bevy World 做内存快照用于 FDB rollback；回放记录中 `/tick/{N}/state` 写入 tick 后完整世界状态。`engine.md` 的 Tier1 预算是全量快照 ≤16MB/tick、≤50ms 构建。

这里有两个叠加风险：
- 内存侧：每 tick 至少一次完整 snapshot，commit 前又一次 rollback snapshot；若 state 接近 16MB，就是 32MB+ 的内存带宽与分配压力，还不含 player-visible snapshots。
- 存储侧：如果每 tick 都写完整 `/tick/{N}/state`，3s tick 下每天约 28,800 次写入；16MB/tick 约 460GB/day 原始状态量，FDB 写放大后更高。

这不是不能做，但需要明确“全状态写入”是否只是 keyframe，还是每 tick。`engine.md` 说每 tick 存 delta、每 K tick 存 keyframe；`01-tick-protocol.md` 说每 tick 写 `/tick/{N}/state`，两者语义冲突，性能上必须统一。

建议：
- 统一 TickTrace 存储语义：每 tick 写 commands + deltas + metrics；每 K tick 写 keyframe；不要默认每 tick 全状态。
- rollback snapshot 应优先用 mutation log / component-level undo log，而不是无条件 deep clone；如果仍用 deep clone，必须有 `world_snapshot_bytes_p99` 和 `snapshot_alloc_p99` gate。
- FDB commit 必须明确 key count、value size、transaction byte limit、conflict range 策略；否则 “FDB 原子提交全世界”在活跃世界会变成隐性瓶颈。

### A4 — Medium — ECS 调度并行度过低，20 系统链容易把性能锁死在串行主线

设计明确 Phase 2b 主线 `.chain()` 串行，只有 regeneration/decay 等少数系统并行。确定性优先是正确的，但如果 combat、room_state、controller、storage、memory_upkeep 等都在一个全局串行链上，MVP 以后会遇到单线程 ceiling。

更好的抽象通常是“确定性分区并行”：按 room/archetype 分桶并行执行，同一 bucket 内固定排序，跨 bucket 只在边界同步。Tier3 已按 room shard，但 Tier1/Tier2 单节点内也需要 room-level parallelism，否则 5,000 drone 之前就会被 Phase 2b 卡住。

建议：
- 为 Phase 2b 定义 room-bucket deterministic scheduler：每房间局部系统并行，跨房间事件进入下一阶段队列。
- 对 combat/pathing/visibility 分别给出 `O(local_entities)` 目标，避免全世界 query。
- 将 ECS system read/write matrix 扩展到所有 20 个系统，而不是只列核心 6 个系统。

### A5 — Medium — 认证热路径缺少延迟预算与缓存失效协议

认证设计安全边界很清楚：每个敏感 MCP/deploy/admin 请求都进行证书链、CRL、Ed25519 signature、nonce、scope、audience 验证；Gateway 对 MCP 限制 50 请求/tick/player；Tier3 提到 Auth Service 全局单例、分片本地 CRL 缓存 60s TTL + push invalidation。

风险在于这些操作可能进入高频读取/调试路径：50 req/tick/player × 500 players 在理论上是 25k request/tick，若每次都做证书链解析、CRL miss RPC、nonce FDB 写入，会把 Auth Service/FDB 变成 shared bottleneck。Nonce 全局 registry 对 deploy/admin 合理，但对所有 read MCP 是否都需要强全局去重，需要分层。

建议：
- 定义 Auth verification cache：按 `(cert_id, cert_epoch, scope, audience)` 缓存链验证结果，短 TTL + revocation push 失效。
- 将 nonce 去重分层：deploy/admin 使用 FDB 强去重；普通 read MCP 可使用 per-gateway bounded nonce window 或 connection-bound session proof，避免每请求 FDB 写。
- 给出认证热路径 SLO：`auth_verify_p99`、`crl_cache_hit_rate`、`revocation_push_lag_p99`、`nonce_check_p99`、`auth_rpc_qps_limit`。

### A6 — Medium — Tier2/Tier3 specs 仍有过多“需基准测试确认”但任务原则要求设计阶段冻结

T2/T3 文档已经列出 modification-set、CoW page size、keyframe interval、FDB 增量提交、jump hash、动态重平衡、跨分片 replay 等待定项。这是诚实的，但本轮评审原则是设计阶段评审、不考虑分阶段实现难度；在这个原则下，关键扩展策略不能只写候选。

尤其是 T2 的 `cow_page_size`、`max_dirty_pages`、keyframe interval 和 FDB delta mapping，直接决定 5,000 drone 是否可达；T3 的 dynamic rebalance 和跨分片 TickTrace 合并，直接决定多节点可运维性。

建议：
- 在 R2 设计中至少冻结默认值与替代条件：例如 keyframe every `min(100 tick, 1000 changed entities)`，并定义如何通过 benchmark 调整。
- 将“需基准测试确认”改为 entry gate：没有达到指定 p99/throughput，不允许从 Tier1 升 Tier2。
- 明确 Tier2/Tier3 的容量基准场景，而不是只写目标规模。

### A7 — Low — `path_find` 缓存键可能过细，命中率风险未量化

`host_path_find` 缓存键包含 `(from, to, terrain_hash, player_visibility_fingerprint)`。这能保证可见性安全，但 `player_visibility_fingerprint` 如果随实体移动频繁变化，会导致 path cache miss 过高。文档已有 miss >50/tick 的滥用限制和 explored_nodes 成本，这很好，但对正常玩家路径规划的命中率没有目标。

建议：
- 区分 terrain-only path cache 与 visibility-constrained overlay；不可见实体通常不应影响地形 path 的主缓存。
- 增加 `path_cache_hit_rate`、`path_explored_nodes_p99`、`path_empty_due_to_quota_rate` 指标。

## Missing

- **端到端容量基准矩阵**：至少覆盖 50/100/500 active players、10/50/500 rooms、500/5,000 drones、不同 command mix、不同 snapshot truncation rate。
- **热路径 CPU 预算表**：把 3s tick 拆成 snapshot build、WASM worker start/init、WASM execution、command validation、ECS systems、FDB commit、broadcast delta 的 p50/p95/p99 预算。
- **worker lifecycle benchmark**：fork/kill vs warm pool vs persistent per-player worker 的启动延迟、内存泄漏风险、隔离重置成本对比。
- **serialization profile**：JSON encode/decode/copy 的 bytes/tick、alloc/tick、CPU/tick；若保留 JSON，需证明 500 active players 下可达。
- **FDB transaction model**：每 tick key/value 数量、transaction byte size、conflict ranges、keyframe/delta retention、WAL 与 TickTrace 的一致性恢复流程。
- **Auth cache/invalidation design**：CRL push 失效、cert epoch bump、nonce 策略、Gateway 本地缓存一致性、Auth Service 水平扩展方案。
- **Observability dashboards**：已有指标表，但缺少按 pipeline stage 的 histogram 和 saturation 指标（worker queue depth、compile queue depth、auth cache hit、NATS backlog、Dragonfly rebuild lag）。

## Phase Ordering

1. **先冻结性能预算**：把 3s tick 目标拆成 stage-level p99 budget，并定义 Tier1/Tier2/Tier3 entry gates。
2. **先解决 sandbox lifecycle**：在 fork/kill 与 warm worker pool 之间做明确架构选择；若选择 fork/kill，必须用基准证明 500 active players 可达。
3. **再冻结 hot-path ABI**：决定 tick 内 JSON 是否仅用于 debug，或引入 binary canonical ABI；这个决定会影响 SDK、host functions、TickTrace 与 replay。
4. **再统一 snapshot / TickTrace 存储语义**：明确 delta/keyframe/全状态各自何时写入，消除 `/tick/{N}/state` 每 tick 全量写与 keyframe 说法冲突。
5. **然后补认证缓存与 CRL 失效协议**：在安全模型不降级的前提下，避免 Auth/FDB 成为所有 Gateway/MCP 请求的共享瓶颈。
6. **最后冻结 Tier2/Tier3 默认策略**：T2 modification-set/FDB mapping/keyframe interval，T3 rebalance/replay/shard assignment，全部转为可执行 entry gate，而不是候选说明。

## Final Recommendation

R2 可以继续推进，但不应以当前性能设计直接进入实现。建议将以上 A1/A2/A3/A5 作为进入实现前必须关闭的条件；A4/A6 作为 Tier2 前置条件；A7 可作为优化项进入 benchmark backlog。整体 verdict 为 CONDITIONAL_APPROVE。