# R13 Architect 评审发现

> 零历史上下文评审。仅记录问题 + 严重度。

## Critical

**A1. 全局原子 tick 提交与 sharding 根本冲突。** P0-1 §3.4 将整个 EXECUTE（所有玩家全部指令）包裹在单个 FDB 事务里全或无提交；DESIGN §7.2 与 ROADMAP 7.2 又要求「每 shard 一个引擎实例」「不同房间分配到不同引擎进程，跨房间移动通过 FDB 事务协调」。单个全局事务包含全世界所有玩家指令，无法随房间数水平扩展——这是吞吐量天花板。sharding 后哪个进程持有哪个 Bevy World、跨 shard 的种子洗牌玩家全序如何协调，均未定义。需明确：tick 提交粒度是「全局」还是「per-shard」，二者只能选一，当前文档同时声明了两者。

**A2. COLLECT 跨房间可见性与「不访问外部存储」矛盾。** P0-1 §2.3 规定 COLLECT 仅从本地 Bevy World 内存读 `all_entities`，不读 FDB/Dragonfly；但 P0-5 §4 的视野可覆盖「相邻房间」。sharding 下相邻房间若在另一进程，COLLECT 无法在本地内存取到该实体，快照将丢失合法可见实体。需定义跨 shard 的相邻房间状态同步机制（本 tick 起始只读副本？），否则可见性在分布式部署下不正确。

## Major

**A3. 回放输入不完整——world config 未纳入 TickTrace。** §8.8 回放保证列出输入为「tick N-1 state + RawCommand + world_seed + 激活模组列表」，但缺少已解析的 world.toml（resource_types、action_costs、body_cost 覆盖、damage_types）。这些值直接决定指令执行结果，且可 per-world 配置。若世界配置在 tick 之间被修改而 TickTrace 未快照该配置，`execute_deterministic == recorded_state` 不成立。建议把 resolved world config 的内容哈希写入 TickTrace。

**A4. fuel refund credit 未声明为回放状态。** P0-2 §7.2 规定 `next_tick_fuel_credit` 影响下一 tick 的 fuel budget，而 fuel budget 决定 WASM 执行深度（即指令输出）。该 credit 必须是 tick 边界的权威状态并随回放重建，但 §6.3.1 的 `/tick/{N}/*` 记录项未包含它。未记录则回放 fuel 预算偏移 → 指令序列分歧。

**A5. world_seed 轮换的回放可重建性未规定。** §8.8 称 world_seed 每 10000 tick 经 `Blake3(旧种子, 当前tick)` 轮换，使种子变为 tick 依赖量。回放某个 tick 需知道该 tick 生效的轮换后种子。需明确轮换调度可由初始种子纯函数推导（记录初始种子即可），并在协议中固化推导式，否则跨轮换边界的 tick 回放不可重现。

**A6. path_find 缓存与 fuel 计费的确定性耦合。** P0-4 §8 给 `path_find` 定 `10,000 + 50/tile` fuel 成本，同时 P0-2 §4.3 与 §8 又定义按 `(from,to,terrain_hash,visibility_fingerprint)` 缓存。需明确：缓存命中是否仍按全额计费。若命中省 fuel，则 fuel 消耗依赖缓存状态，而缓存状态不属于记录状态 → 回放分歧；若命中仍全额计费，则缓存仅省墙钟、对 fuel 透明（推荐），应在文档显式声明。

## Minor

**A7. tick 时间预算无余量。** COLLECT 2500ms + EXECUTE 500ms = 3000ms 已等于 tick_interval(3s)，BROADCAST/FDB commit/快照构建无预算；且 Phase 2 成功标准 p99<5s 与 3s 间隔暗示需要 tick 流水线重叠（N+1 COLLECT 与 N BROADCAST 并行），但流水线模型未在 P0-1 描述。

**A8. 迟到指令跨 tick 重排破坏 sequence 不变量。** P0-1 §2.2 称超时玩家「迟到指令排入下一 tick 队列」，但 N+1 会重新运行 WASM 产出新指令，且 sequence 是 per-player-per-tick 单调。两批指令如何合并、sequence 如何不冲突未定义。建议明确：超时即丢弃当 tick 输出，不跨 tick 携带。
