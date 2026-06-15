1|# Tick 协议规范
2|
3|> **状态**: 当前 | **日期**: 2026-06-14
4|
5|> **状态**: 当前
6|
7|## 1. 状态机
8|
9|```
10|                 ┌──────────────────────────────────┐
11|                 │         空闲等待                   │
12|                 │        tick_counter = N           │
13|                 └──────────┬───────────────────────┘
14|                            │ 到达 tick_interval
15|                            ▼
16|                 ┌──────────────────────────────────┐
17|                 │     阶段一：收集 (COLLECT)          │
18|                 │  超时: 2500ms                     │
19|                 │  ┌─────────────────────────┐     │
20|                 │  │ 对每个活跃玩家:           │     │
21|                 │  │ 1. 构建可见性快照          │     │
22|                 │  │ 2. 调用 PlayerExecutor    │     │
23|                 │  │ 3. 超时 → 空指令列表      │     │
24|                 │  └─────────────────────────┘     │
25|                 │  结果: Map<PlayerId, Vec<Cmd>>   │
26|                 └──────────┬───────────────────────┘
27|                            │
28|                            ▼
29|                 ┌──────────────────────────────────┐
30|                 │     阶段二：执行 (EXECUTE)          │
31|                 │  超时: 500ms                      │
32|                 │  ┌─────────────────────────┐     │
33|                 │  │ Phase 2a: 命令循环        │     │
34|                 │  │ 逐条校验 + 逐条应用       │     │
35|                 │  │ (基于当前 Bevy World)    │     │
36|                 │  │ Spawn 只校验不入队        │     │
37|                 │  └─────────────────────────┘     │
38|                 │  ┌─────────────────────────┐     │
39|                 │  │ Phase 2b: ECS Systems     │     │
40|                 │  │ death_mark → spawn →     │     │
41|                 │  │ combat → regen/decay →   │     │
42|                 │  │ death_cleanup            │     │
43|                 │  └─────────────────────────┘     │
44|                 │  FDB 原子提交（全或无,权威源）   │
45|                 └──────────┬───────────────────────┘
46|                            │
47|                            ▼
48|                 ┌──────────────────────────────────┐
49|                 │    阶段三：广播 (BROADCAST)         │
50|                 │  ┌─────────────────────────┐     │
51|                 │  │ 1. 计算实体增量            │     │
52|                 │  │ 2. Dragonfly 缓存更新      │     │
53|                 │  │ 3. NATS 发布增量           │     │
54|                 │  └─────────────────────────┘     │
55|                 └──────────┬───────────────────────┘
56|                            │ tick_counter = N + 1
57|                            ▼
58|                       空闲等待
59|```
60|
61|## 2. 阶段一：收集
62|
63|### 2.1 玩家执行模型
64|
65|唯一执行器：**WasmSandboxExecutor**。所有玩家的 drone 都通过 WASM 沙箱执行——无论是人类编写还是 AI agent 编写。没有 McpPlayerExecutor。
66|
67|| 输入来源 | 编译者 | 部署渠道 |
68||---------|--------|---------|
69|| 人类编写代码 | 人类通过 Web UI / CLI 编译 | Web 上传 / `swarm deploy` CLI |
70|| AI agent 编写代码 | AI 通过自身工具链编译 | MCP `swarm_deploy` |
71|
72|引擎只关心：「有 WASM 模块了吗？」——不问是谁写的。
73|
74|### 2.2 收集超时
75|
76|```
77|collect_timeout_ms = 2500  // 硬截止时间
78|
79|在 t + 2500ms 时刻:
80|  对每个未响应的玩家:
81|    commands[player] = []   // 宽容失败: 本 tick 无指令
82|    metrics.collect_timeouts += 1
83|```
84|
85|**原则**: 某个玩家卡住不会阻塞整个世界。超时玩家当 tick 指令输出丢弃——不跨 tick 携带（防止 sequence 冲突与跨 tick 重排）。
86|
87|### 2.3 快照构建
88|
89|```
90|fn build_snapshot(player_id, tick) -> Snapshot:
91|    // all_entities 来自 Bevy World 内存（当前 tick 执行前的权威状态）
92|    // 不从 FDB/Dragonfly 读 —— COLLECT 阶段不访问外部存储
93|    entities = visibility_filter(all_entities, player_id, tick)
94|    return Snapshot {
95|        tick,
96|        player_id,
97|        entities,    // 仅该玩家可见
98|        terrain,     // 可见地形格
99|        resources,   // 玩家自身资源
100|    }
101|```
102|
103|快照按房间序列化一次，再按玩家过滤——不是 O(P × E)。
104|
105|### 2.4 WASM 模块部署
106|
107|AI 玩家通过 MCP `swarm_deploy` 上传 WASM 模块，引擎在下一 tick 加载新模块：
108|```
109|Tick N: 引擎用 WASM 模块 v1 执行玩家代码
110|Tick N: AI 调用 swarm_deploy，上传 v2
111|Tick N+1: 引擎自动切换到 v2
112|```
113|
114|代码部署不影响当前 tick 执行——当前 tick 使用已加载的模块。切换是原子的。
115|
116|## 3. 阶段二：执行
117|
118|### 3.1 指令排序（确定性 + 公平）
119|
120|**问题**：如果排序 key 是 `(tick_number, player_id, ...)  `，同一个玩家每次都在同一位置——不公平且可被利用。
121|
122|**方案：种子洗牌 (Seeded Shuffle)**
123|
124|```rust
125|// 每 tick 洗牌一次，用 Blake3 XOF 从 seed + tick 派生确定性随机序列
126|// seed = Blake3(tick_number || world_seed)
127|// shuffle = Blake3 XOF: for i in 0..N:  position[i] = XOF.read_u64() % (N - i)
128|let seed = blake3::hash(&[&tick_number.to_le_bytes(), &world_seed]);
129|let player_order: Vec<PlayerId> = seeded_shuffle(&active_players, &seed);
130|
131|// 按洗牌后的玩家顺序 + 玩家内部指令序号排序
132|for (order_index, player_id) in player_order.iter().enumerate() {
133|    let player_commands = collected_commands[player_id].sort_by_key(|c| c.sequence);
134|    for cmd in player_commands {
135|        global_queue.push((order_index, player_id, cmd.sequence, cmd));
136|    }
137|}
138|```
139|
140|**属性**：
141|- 确定性：相同 `(tick_number, world_seed, 相同指令集)` → 相同顺序 → 相同世界状态
142|- 公平性：每个 tick 玩家顺序随机轮换，长期期望均等
143|- 不可预测：玩家无法提前知道自己在当前 tick 的排序位置
144|
145|### 3.2 资源竞争 (Resource Contention)
146|
147|**场景**：两个玩家的 drone 在同一 tick 试图采集同一个 Source。
148|
149|**规则：按排序顺序依次执行，先到先得。**
150|
151|```
152|Source E1: energy = 5
153|
154|排序后指令队列:
155|  1. Player B: harvest(E1) → 拿走 5，E1 剩余 0
156|  2. Player A: harvest(E1) → 校验时发现 E1.energy = 0
157|     → RejectionReason: SourceEmpty
158|     → 记录到 TickTrace
159|```
160|
161|**应用范围**：
162|| 竞争类型 | 处理方式 |
163||---------|---------|
164|| 采集同一 Source | 先到先得，耗尽后 `SourceEmpty` |
165|| 建造同一坐标 | 先到先得，坐标被占后 `TileOccupied` |
166|| 攻击同一目标 | 全部执行——多个攻击者可以打同一目标 |
167|| 治疗同一目标 | 按顺序加血，满血后 `AlreadyFullHealth` |
168|| 传输资源到同一目标 | 顺序填充，容量满后 `TargetFull` |
169|
170|**设计意图**：
171|- 先到先得简单、确定、可解释
172|- 种子洗牌保证了「先到」的公平性——长期来看每个玩家都有同等概率先到
173|- 创造了策略深度：要不要多个 drone 采集同一个源？万一排在后面就浪费指令
174|- 不采用比例分配（太复杂且失去竞争性），不采用价高者得（需要市场机制，超出入门复杂度）
175|
176|### 3.3 指令执行模型（Inline）
177|
178|命令循环采用 **Inline 模型**：逐条校验 + 逐条应用，校验基于**当前** Bevy World 状态（非快照）。Move/Harvest/Build/Transfer/Attack/Heal/Recycle 在命令循环中立即执行。Spawn 命令在 Phase 2a 中只校验不入队，在 Phase 2b spawn_system 中统一创建。
179|
180|非法指令 → 拒绝，记录 RejectionReason，写入 TickTrace。
181|
182|### 3.4 ECS 系统执行顺序 (Bevy)
183|
184|Phase 2b 中 ECS Systems 按 `.chain()` 严格排序：
185|
186|```rust
187|app.add_systems(Update, (
188|    death_mark_system,       // 标记待死亡 entity，释放 room cap 槽位
189|    spawn_system,            // 统一创建 Phase 2a 校验通过的 drone
190|    regeneration_system,     // 资源点再生
191|    combat_system,           // 战斗结算（damage 先 → heal 后）
192|    decay_system,            // 疲劳/冷却递减
193|    death_cleanup_system,    // 实际 despawn 已标记 entity
194|).chain());
195|```
196|
197|`.chain()` 强制串行执行 → 确定性。后续优化用 `.before()/.after()` 实现部分并行同时保持正确性。
198|
199|### 3.5 Tick 原子性
200|
201|整个阶段二包裹在 FoundationDB 事务中：
202|
203|```
204|txn = fdb.create_transaction()
205|for command in sorted_commands:
206|    result = validate_and_apply(txn, command, world_state)
207|    if result.is_err():
208|        record_rejection(txn, command, result)
209|txn.set("/tick/{tick}/complete", true)
210|txn.commit()  // 全提交 或 全回滚
211|```
212|
213|`txn.commit()` 失败（冲突/网络）→ 最多重试 3 次 → 全部失败则 tick 放弃。
214|放弃的 tick：世界状态不变，tick_counter 不递增，消耗的 CPU fuel 退还玩家。
215|放弃后等待 1s 重试同一 tick（避免立即重试导致相同的 FDB 冲突）。
216|连续放弃 3 次 → 引擎进入降级模式（暂停新玩家加入），告警触发。
217|**关键**: EXECUTE 开始时对 `Bevy World` 做内存快照——FDB rollback 不自动恢复 Bevy 状态，需显式 `world.restore(snapshot)`。
218|
219|#### Bevy World 快照范围清单
220|
221|快照在 Phase 2a 开始前完成，捕获完整的 World 状态。以下为必须捕获的 Resource 类型和所有 ECS Component 类型：
222|
223|**必须捕获的 Resource 类型**：
224|
225|| Resource | 说明 |
226||----------|------|
227|| `TickCounter` | 当前 tick 编号 |
228|| `WorldSeed` | 世界随机种子 |
229|| `PlayerOrder` | 本 tick 洗牌后的玩家顺序 |
230|| `ResourceRegistry` | 全局资源注册表 |
231|| `WorldConfig` | 世界配置（房间尺寸、限制参数等） |
232|| `RNGState` | 随机数生成器状态（Blake3 XOF 内部状态） |
233|| `TimeResource` | tick 间隔、超时配置等 |
234|
235|**必须捕获的 ECS Component 类型**：所有实体上挂载的 Component 均在快照范围内，包括但不限于：
236|
237|| Component 类别 | 示例 |
238||---------------|------|
239|| `Transform` (位置) | `RoomPosition`, `HexCoord` |
240|| `Owner` (所有权) | `PlayerId` |
241|| `Body` (身体部件) | `BodyPart` 及各个 part 组件 (`MovePart`, `WorkPart`, `CarryPart`, `AttackPart`, `RangedAttackPart`, `HealPart`, `ClaimPart`, `ToughPart`) |
242|| `Resource` (资源) | `Carry`, `Energy`, `ResourceStore` |
243|| `Health` (生命) | `HitPoints`, `MaxHitPoints` |
244|| `Combat` (战斗) | `Damage`, `HealAmount`, `DamageType` |
245|| `Status` (状态) | `Fatigue`, `Cooldown`, `HackControlLock`, `Debilitated`, `Fortified`, `Spawning` |
246|| `Room` (房间) | `RoomId`, `RoomController` |
247|| `Structure` (建筑) | `Spawn`, `Extension`, `Controller`, `Tower`, `Storage` |
248|| `Terrain` (地形) | `TerrainType`, `Walkable` |
249|| `Visibility` (可见性) | `VisibleTo`, `FogOfWarState` |
250|| `Metadata` (元数据) | `EntityId`, `SpawnTick`, `Lifespan` |
251|
252|**快照生命周期**：
253|```
254|Phase 2a 开始前: snapshot = world.snapshot()  // 深拷贝 Bevy World
255|Phase 2a-2b:      在 world 上原地修改
256|FDB commit 成功:  丢弃 snapshot
257|FDB commit 失败:  world.restore(snapshot)      // 恢复所有 Component + Resource
258|```
259|`world.restore(snapshot)` 将 Bevy World 完全回滚至 Phase 2a 前的状态，包括所有实体的 Component 数据、所有 Resource 数据。
260|
261|#### COLLECT 结果跨重试缓存
262|
263|FDB commit 失败触发重试时，**复用同一 COLLECT 结果**（相同的命令序列 + fuel 扣费），不重新执行 WASM：
264|
265|- COLLECT 阶段的结果（`Map<PlayerId, Vec<ValidatedCommand>>` + 各玩家的 fuel 扣费明细）在首次 COLLECT 后缓存
266|- 重试跳过 COLLECT 阶段，直接进入 EXECUTE 阶段，使用缓存的命令列表
267|- 跨重试 fuel 消耗上限 = `1 × MAX_FUEL`（首次 COLLECT 时的扣费即为最终扣费，重试不追加）
268|- 若连续 3 次 FDB commit 失败后 tick 放弃，已扣除的 fuel 退还玩家
269|
270|#### FDB 故障注入 CI 测试
271|
272|CI 管线中增加确定性故障注入测试，验证快照恢复的一致性：
273|
274|```rust
275|#[test]
276|fn fdb_commit_failure_restores_snapshot_consistency() {
277|    // 1. 构建初始 World 状态
278|    let mut world = World::new(test_world_config());
279|    let snapshot_checksum_before = world.state_checksum();
280|
281|    // 2. 注入 FDB commit 失败（随机 tick 触发）
282|    fault_injection::set_mode(FaultMode::RandomCommitFailure {
283|        probability: 0.1,  // 10% 的 tick 触发 commit 失败
284|        seed: 42,           // 确定性种子
285|    });
286|
287|    // 3. 执行 N 个 tick
288|    for tick in 0..1000 {
289|        let snapshot = world.snapshot();  // Phase 2a 前快照
290|        let collected = collect_commands(&world, tick);
291|        let commit_result = execute_and_commit(&mut world, collected, tick);
292|
293|        if commit_result.is_err() {
294|            world.restore(snapshot);
295|            // 验证恢复后状态与快照一致
296|            assert_eq!(world.state_checksum(), snapshot_checksum_before,
297|                "tick {}: state_checksum mismatch after snapshot restore", tick);
298|        }
299|
300|        // 若 commit 成功，更新基准 checksum
301|        if commit_result.is_ok() {
302|            snapshot_checksum_before = world.state_checksum();
303|        }
304|    }
305|}
306|```
307|
308|**CI 中的随机故障注入策略**：
309|- 每个 CI run 随机选取 5% 的 tick 触发 FDB commit 失败
310|- 验证断言：`state_checksum == snapshot_checksum`（恢复后状态与快照完全一致）
311|- 额外验证：`entity_count == snapshot_entity_count`（实体数量一致）
312|- 额外验证：所有 Resource 值与快照值逐项匹配
313|- 失败时输出完整 diff（哪个 Component/Resource 不一致）
314|
315|## 4. 阶段三：广播
316|
317|### 4.1 增量计算
318|
319|```
320|delta = compute_delta(world_state_before, world_state_after)
321|// delta 仅包含本 tick 变更的实体
322|```
323|
324|### 4.2 持久化 → 缓存 → 发布
325|
326|```
327|1. Read committed tick result from in-memory post-commit state or FDB versionstamp
328|2. Dragonfly.update(delta)   // 非权威缓存，允许滞后。失败则从 FDB 重建
329|3. NATS.publish("tick.{tick}", delta)  // 网关 → WebSocket 客户端
330|```
331|
332|**BROADCAST failure never rolls back committed tick**——tick 已在 EXECUTE 阶段持久化到 FDB。BROADCAST 阶段的任何失败（Dragonfly 未命中、NATS 断开、部分客户端未收到）都不影响世界状态。客户端通过 `last_tick` 字段检测 gap → 主动 fetch。
333|
334|## 5. Tick 健康指标
335|
336|| 指标 | 阈值 | 动作 |
337||------|------|------|
338|| `collect_timeout_rate` | > 10% 玩家 | 告警：太多慢执行器 |
339|| `tick_abandon_rate` | > 0 | 严重：FDB 提交失败 |
340|| `tick_duration_p99` | > 2800ms | 警告：接近 3s 目标 |
341|| `command_rejection_rate` | > 20% 每玩家 | 标记玩家审查 |
342|
343|## 6. Tick Failure Semantics — 失败语义
344|
345|### 6.1 失败模式矩阵
346|
347|| 失败点 | 触发条件 | 对本 tick 影响 | 对玩家影响 | 恢复策略 |
348||--------|---------|--------------|-----------|---------|
349|| **WASM timeout** | 玩家 tick() 超过 collect_timeout_ms (2500ms) | 该玩家 0 指令，其他玩家正常 | 空 tick，不退 fuel | 下 tick 正常执行 |
350|| **WASM crash** | 玩家 WASM 崩溃/panic/OOM | 同上 | 空 tick，不退 fuel。连续 3 tick crash → 玩家标记 degraded | 自动恢复，degraded 需人工解除 |
351|| **WASM output invalid** | tick 输出不符合 JSON schema（见 specs/02-command-validation §1.1） | 该玩家所有指令丢弃 | 空 tick，不退 fuel | 下 tick 正常（需玩家修复代码） |
352|| **FDB commit fail** | FoundationDB 事务冲突/网络错误 | tick 放弃（state 不变，tick_counter 不递增） | CPU fuel 退还 | 重试 3 次，失败等 1s 重试同 tick。连续 3 tick abandon → 引擎降级 |
353|| **Dragonfly cache miss** | 缓存未命中/过期 | 无——回退到 FDB 直读 | 无影响 | 从 FDB 重建缓存（异步） |
354|| **Dragonfly cache stale** | 缓存版本落后于 FDB | 无——FDB 为权威源 | 旧数据给查询入口，不影响 tick | 下次写入时自动刷新 |
355|| **NATS publish fail** | NATS 连接断开/超时 | tick 结果已持久化到 FDB，但客户端未收到 delta | 客户端未更新，需等 polling fallback | NATS 重连；客户端 5s 未收到 delta → 主动拉取 |
356|| **Broadcast partial** | 部分客户端已收到 delta，部分未收到 | 客户端间状态不一致（暂时） | 未收到的客户端显示旧状态 | 客户端通过 last_tick 字段检测 gap → 主动 fetch |
357|| **TickTrace write fail** | FDB 写入 TickTrace 失败（磁盘满） | tick 执行完成但审计日志不完整 | 无 gameplay 影响 | 告警；TickTrace 丢失的 tick 标记为不可回放 |
358|
359|### 6.2 降级模式 (Degraded Mode)
360|
361|连续 3 次 tick abandon → 引擎进入降级模式：
362|- 暂停新玩家加入 (`join_lock = true`)
363|- 暂停 MCP_Deploy 来源（禁止代码更新，防部署丢失）
364|- 保持已有玩家 WASM 执行
365|- 告警升级 → 需管理员介入
366|- 连续 10 tick 正常 → 自动退出降级模式
367|
368|### 6.3 回放协议
369|
370|#### 6.3.1 记录
371|
372|每个 tick 写入 FDB（不可变）：
373|```
374|/tick/{N}/commands   → 全部玩家排序后的 RawCommand
375|/tick/{N}/state      → tick 后的完整世界状态
376|/tick/{N}/rejections → 被拒绝的指令及原因
377|/tick/{N}/metrics    → TickMetrics
378|```
379|
380|AI 玩家：记录 ACCEPTED 指令，不是原始 LLM 输出。回放时喂记录指令——不重调 LLM。
381|
382|#### 6.3.2 回放执行
383|
384|```
385|fn replay_tick(tick_N) -> WorldState:
386|    state = load_state(tick_N - 1)     // 起始状态
387|    commands = load_commands(tick_N)   // 记录的指令
388|    return execute_deterministic(state, commands)  // 必须 == 记录状态
389|```
390|
391|`execute_deterministic(state, commands) != recorded_state` → 确定性 BUG。
392|
393|#### 6.3.3 Wasmtime 版本与回放共存
394|
395|**问题**: `wasmtime = "=30.0"` 锁定版本 → 发现 CVE 升级后旧 tick 回放中断。
396|
397|**策略**: TickTrace 始终记录 `Command[]` 而非 WASM 输出。回放时引擎直接执行已记录的指令序列，不重新调用 WASM。Wasmtime 版本变更不影响回放。仅当 tick 被标记为"降级模式"（WASM 执行异常）时，需匹配 Wasmtime 版本进行二次回放验证。
398|
399|#### 6.3.4 Tick Boundary Contract
400|
401|COLLECT 阶段从 Bevy World 内存读取权威状态，不访问 FDB/Dragonfly。EXECUTE 阶段在 Bevy World 上原地修改 → FDB 事务提交 → 成功后 FDB 为新的权威源。Bevy World 与 FDB 的关系：Bevy 是每 tick 的工作副本，FDB 是持久化的权威源。启动/恢复时从 FDB 重建 Bevy World。
402|