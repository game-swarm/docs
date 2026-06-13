# P0-1: Tick 协议规范

> **状态**: Phase 2 阻断项

## 1. 状态机

```
                 ┌──────────────────────────────────┐
                 │         空闲等待                   │
                 │        tick_counter = N           │
                 └──────────┬───────────────────────┘
                            │ 到达 tick_interval
                            ▼
                 ┌──────────────────────────────────┐
                 │     阶段一：收集 (COLLECT)          │
                 │  超时: 2500ms                     │
                 │  ┌─────────────────────────┐     │
                 │  │ 对每个活跃玩家:           │     │
                 │  │ 1. 构建可见性快照          │     │
                 │  │ 2. 调用 PlayerExecutor    │     │
                 │  │ 3. 超时 → 空指令列表      │     │
                 │  └─────────────────────────┘     │
                 │  结果: Map<PlayerId, Vec<Cmd>>   │
                 └──────────┬───────────────────────┘
                            │
                            ▼
                 ┌──────────────────────────────────┐
                 │     阶段二：执行 (EXECUTE)          │
                 │  超时: 500ms                      │
                 │  ┌─────────────────────────┐     │
                 │  │ 对每条指令（已排序）:      │     │
                 │  │ 1. 校验                  │     │
                 │  │ 2. 应用 或 拒绝           │     │
                 │  └─────────────────────────┘     │
                 │  按顺序运行 ECS 系统               │
                 └──────────┬───────────────────────┘
                            │
                            ▼
                 ┌──────────────────────────────────┐
                 │    阶段三：广播 (BROADCAST)         │
                 │  ┌─────────────────────────┐     │
                 │  │ 1. 计算实体增量            │     │
                 │  │ 2. FDB 原子提交            │     │
                 │  │ 3. Dragonfly 缓存更新      │     │
                 │  │ 4. NATS 发布增量           │     │
                 │  └─────────────────────────┘     │
                 └──────────┬───────────────────────┘
                            │ tick_counter = N + 1
                            ▼
                       空闲等待
```

## 2. 阶段一：收集

### 2.1 玩家执行模型

唯一执行器：**WasmSandboxExecutor**。所有玩家的 drone 都通过 WASM 沙箱执行——无论是人类编写还是 AI agent 编写。没有 McpPlayerExecutor。

| 输入来源 | 编译者 | 部署渠道 |
|---------|--------|---------|
| 人类编写代码 | 人类通过 Web UI / CLI 编译 | Web 上传 / `swarm deploy` CLI |
| AI agent 编写代码 | AI 通过自身工具链编译 | MCP `swarm_deploy` |

引擎只关心：「有 WASM 模块了吗？」——不问是谁写的。

### 2.2 收集超时

```
collect_timeout_ms = 2500  // 硬截止时间

在 t + 2500ms 时刻:
  对每个未响应的玩家:
    commands[player] = []   // 宽容失败: 本 tick 无指令
    metrics.collect_timeouts += 1
```

**原则**: 某个玩家卡住不会阻塞整个世界。迟到指令排入下一个 tick 的队列。

### 2.3 快照构建

```
fn build_snapshot(player_id, tick) -> Snapshot:
    entities = visibility_filter(all_entities, player_id, tick)
    return Snapshot {
        tick,
        player_id,
        entities,    // 仅该玩家可见
        terrain,     // 可见地形格
        resources,   // 玩家自身资源
    }
```

快照按房间序列化一次，再按玩家过滤——不是 O(P × E)。

### 2.4 WASM 模块部署

AI 玩家通过 MCP `swarm_deploy` 上传 WASM 模块，引擎在下一 tick 加载新模块：
```
Tick N: 引擎用 WASM 模块 v1 执行玩家代码
Tick N: AI 调用 swarm_deploy，上传 v2
Tick N+1: 引擎自动切换到 v2
```

代码部署不影响当前 tick 执行——当前 tick 使用已加载的模块。切换是原子的。

## 3. 阶段二：执行

### 3.1 指令排序（确定性）

```
sort_key = (tick_number, player_id, command_sequence_number)
```

所有玩家的全部指令展平为一个列表，按此 key 排序。给定相同指令集，顺序始终相同。

### 3.2 指令校验

每条指令对照当前世界状态校验。详见 P0-2 指令校验规范。
非法指令 → 拒绝，记录 RejectionReason，写入 TickTrace。

### 3.3 ECS 系统执行顺序 (Bevy)

```rust
app.add_systems(Update, (
    build_system,          // 建筑先出现
    harvest_system,        // 资源被采集
    regeneration_system,   // 资源点再生
    movement_system,       // 单位移动
    combat_system,         // 战斗结算
    decay_system,          // 疲劳/冷却递减
    death_system,          // 死亡单位清除
    spawn_system,          // 新单位最后创建
).chain());
```

`.chain()` 强制串行执行 → 确定性。后续优化用 `.before()/.after()` 实现部分并行同时保持正确性。

### 3.4 Tick 原子性

整个阶段二包裹在 FoundationDB 事务中：

```
txn = fdb.create_transaction()
for command in sorted_commands:
    result = validate_and_apply(txn, command, world_state)
    if result.is_err():
        record_rejection(txn, command, result)
txn.set("/tick/{tick}/complete", true)
txn.commit()  // 全提交 或 全回滚
```

`txn.commit()` 失败（冲突/网络）→ 最多重试 3 次 → 全部失败则 tick 放弃。
放弃的 tick：世界状态不变，tick 计数器不推进，触发告警。

## 4. 阶段三：广播

### 4.1 增量计算

```
delta = compute_delta(world_state_before, world_state_after)
// delta 仅包含本 tick 变更的实体
```

### 4.2 持久化 → 缓存 → 发布

```
1. FDB.commit()              // 原子提交，阻塞至持久化完成
2. Dragonfly.update(delta)   // 非权威缓存，允许滞后
3. NATS.publish("tick.{tick}", delta)  // 网关 → WebSocket 客户端
```

顺序不可变: FDB 先，缓存后，广播最后。
Dragonfly 挂了 → 从 FDB 重建。
NATS 挂了 → 客户端丢失增量，下个 tick 发全量快照（非增量）。

## 5. Tick 健康指标

| 指标 | 阈值 | 动作 |
|------|------|------|
| `collect_timeout_rate` | > 10% 玩家 | 告警：太多慢执行器 |
| `tick_abandon_rate` | > 0 | 严重：FDB 提交失败 |
| `tick_duration_p99` | > 2800ms | 警告：接近 3s 目标 |
| `command_rejection_rate` | > 20% 每玩家 | 标记玩家审查 |

## 6. 回放协议

### 6.1 记录

每个 tick 写入 FDB（不可变）：
```
/tick/{N}/commands   → 全部玩家排序后的 RawCommand
/tick/{N}/state      → tick 后的完整世界状态
/tick/{N}/rejections → 被拒绝的指令及原因
/tick/{N}/metrics    → TickMetrics
```

AI 玩家：记录 ACCEPTED 指令，不是原始 LLM 输出。回放时喂记录指令——不重调 LLM。

### 6.2 回放执行

```
fn replay_tick(tick_N) -> WorldState:
    state = load_state(tick_N - 1)     // 起始状态
    commands = load_commands(tick_N)   // 记录的指令
    return execute_deterministic(state, commands)  // 必须 == 记录状态
```

`execute_deterministic(state, commands) != recorded_state` → 确定性 BUG。
