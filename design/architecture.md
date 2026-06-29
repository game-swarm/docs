# Swarm 架构总览

> 本文是 Swarm 的架构入口：说明系统边界、tick 热路径、分片模型与关键组件职责。详细规则见
> [Engine](engine.md)、[Tech Choices](tech-choices.md)、[Tick Protocol](../specs/core/01-tick-protocol.md)、
> [WASM Sandbox](../specs/core/04-wasm-sandbox.md)、[Persistence Contract](../specs/core/05-persistence-contract.md)、
> [Complete Tick Execution Manifest](../specs/core/06-phase2b-system-manifest.md)、
> [Distributed Sandbox](../specs/core/12-distributed-sandbox.md)。

**设计原则：设计即终态。没有"远期方向"、"阶段"、"future"、"以后再说"。每一个架构决策必须在当下裁定最佳实践，不允许 defer。**

---

## 1. 核心判断

Swarm 的计算分成两层，二者扩展性质完全不同：

1. **WASM Execution / COLLECT**：玩家代码执行。无共享状态、无跨玩家依赖，天然并行，可水平扩展。
2. **World Simulation / EXECUTE**：权威世界模拟。所有命令确定性排序后串行应用，必须保持同输入同输出，是真实瓶颈。

这一区分决定了架构边界：

- sandbox container 可以横向增加。
- 单个权威世界的 EXECUTE 不能靠多机并行写入提升吞吐。
- 世界按坐标范围静态分片——每 shard 一个 Engine 实例，单 writer 不变。
- redb、NATS 都围绕 shard 内的单实例 Engine 服务，而不是替代 Engine 的权威性。

---

## 2. 分片模型

世界按静态坐标范围分片。world.toml 定义分片网格：

```toml
[sharding]
shard_grid = { x_range = [0, 49], y_range = [0, 49] }  # 每 shard 管辖的房间范围
shard_cap = { max_active_players = 500 }                 # 每 shard 活跃玩家上限
```

**性质**：

- shard_id = f(room_x, room_y)，从配置 O(1) 计算，无需运行时 coordinator
- 每 shard 一个 Engine 进程 + 一个 redb 文件
- WASM worker pool 跨所有 shard 共享——worker 无状态，不绑定任何 shard
- 跨 shard 通信仅在玩家迁移时发生（drone 穿过 shard 边界的房间出口），不在热路径
- 单玩家同时只在一个 shard
- 无 cluster、无 leader election、无 gossip

---

## 3. 架构图

```
                 ┌──────────────────────────────────────────┐
                 │              Web / MCP Clients            │
                 │  WebSocket delta · REST/MCP world query   │
                 └───────────────┬──────────────────────────┘
                                 │
                                 ▼
                         ┌──────────────┐
                         │   Gateway    │
                         │ Rust (axum)  │
                         │ 路由 · WS · 认证边界  │
                         └──────┬───────┘
                                │
                         NATS tick broadcast
                                │
┌───────────────────────────────▼────────────────────────────────┐
│                              NATS                               │
│  cluster（每节点一个实例）                                         │
│  tick delta broadcast · sandbox dispatch request-reply           │
│  lightweight pub/sub, no persistence requirement                 │
└───────────────┬───────────────────────────────┬────────────────┘
                │                               │
                │ sandbox request-reply         │ tick/delta publish
                ▼                               ▲
┌──────────────────────────────┐                │
│      Sandbox Containers       │                │
│  COLLECT phase                │                │
│  Wasmtime + WASI              │                │
│  stateless, shared pool       │                │
│  NATS queue-group 负载均衡    │                │
│  timeout => empty commands    │                │
└───────────────┬──────────────┘                │
                │ commands                       │
                ▼                                │
        ┌────────────────────────────────────────┴──────────────┐
        │               Engine × N shards (Rust)                  │
        │                                                        │
        │  COLLECT coordinator                                   │
        │    snapshot fanout -> sandbox -> command collection     │
        │                                                        │
        │  EXECUTE                                               │
        │    deterministic sort                                  │
        │    serial command apply                                │
        │    Bevy ECS fixed schedule, 31 systems                  │
        │                                                        │
        │  COMMIT                                                │
        │    redb WriteTransaction                               │
        │    process-internal cache update                       │
        │    tick delta publish                                  │
        │                                                        │
        │  Process-Internal:                                     │
        │    Moka cache (snapshot + world state)                 │
        │    redb metrics table (per-tick metrics)               │
        └───────────────────────┬───────────────────────────────┘
                                │
                                ▼
                        ┌──────────────┐
                        │     redb     │
                        │ 每 shard 一个  │
                        │ single .redb │
                        │ authoritative│
                        └──────────────┘
```

---

## 4. Tick 热路径

每个 tick 分三段：

```
COLLECT -> EXECUTE -> COMMIT
```

### 4.1 COLLECT：可并行

COLLECT 运行玩家 WASM：

1. Engine 为每个玩家生成 visibility snapshot。
2. snapshot 与 module hash 通过 NATS request-reply 分发到共享 sandbox pool。
3. NATS queue-group 自动负载均衡——任意空闲 worker 可接任意 shard 的请求。
4. 每个 sandbox 独立执行玩家 `tick()`。
5. WASM 输出 `CommandIntent`。
6. timeout、trap、fuel exhausted 转化为 rejection 或 empty commands，不修改世界状态。

关键性质：

- 每个玩家看到自己的可见性快照。
- sandbox 之间零共享状态、零互相依赖。
- sandbox 失败不会污染 Bevy World。
- 通过 NATS queue-group 分布式执行，无 dispatcher 单点。

扩展方式：

```
更多玩家 / 更多 WASM CPU 消耗
        => 增加 sandbox container
        => Engine 只收集结果
```

### 4.2 EXECUTE：必须顺序确定

EXECUTE 推进权威世界：

1. 收集所有玩家命令。
2. 执行服务器侧验证。
3. 按确定性键全序排序。
4. 串行 apply command。
5. 执行 Bevy ECS 固定系统链。
6. 生成 state delta、rejection、fuel、checksum。

关键性质：

- 相同输入必须得到相同世界状态。
- 在线执行和 replay 必须共享同一确定性语义。
- ECS 系统注册顺序固定。
- 权威调度见 [Complete Tick Execution Manifest](../specs/core/06-phase2b-system-manifest.md)：31 systems per tick。

真实瓶颈：

```
500 players x 100 commands = 50,000 commands/tick
EXECUTE p99 target < 400ms
```

EXECUTE 不通过增加 sandbox container 扩容。它主要依赖更快 CPU、更少 command、更紧凑 component layout、更少 archetype churn，以及更高效的 validation/apply path。

### 4.3 COMMIT：单事务推进世界

COMMIT 把 tick 结果变成持久事实：

1. redb `WriteTransaction` 原子写入 replay-critical subset。
2. 推进 tick head 与 state checksum。
3. 更新 Engine 进程内 Moka cache。
4. 通过 NATS 发布 tick delta。
5. 写入 redb metrics table（per-tick metrics）。

COMMIT 的权威点是 redb commit。NATS 不是世界状态来源。

---

## 5. 两层计算模型

| 层 | 阶段 | 输入 | 输出 | 失败语义 | 扩展方式 |
|----|------|------|------|----------|----------|
| WASM Execution | COLLECT | visibility snapshot + module hash + tick context | commands / rejections / fuel usage | timeout = empty commands；trap 不污染世界 | 水平扩展 sandbox containers |
| World Simulation | EXECUTE | validated commands + current Bevy World | next Bevy World + TickCommitRecord | commit 前失败则 tick 不推进 | 垂直扩展与 ECS 优化 |

WASM 层是不可信计算层。它只生产意图，不直接写世界。

World Simulation 是可信计算层。所有玩家、客户端、MCP 最终都以 Engine 的 EXECUTE 结果为准。

---

## 6. 存储：redb

redb 是 Swarm 的权威持久化层：

- 嵌入式 ACID KV。
- 纯 Rust，零 C 依赖。
- 每 shard 一个 `.redb` 文件。
- 无外部 daemon。
- `WriteTransaction` 支持每 tick 多 key batch 原子提交。
- 单 Engine 实例天然对应单 writer。

redb 不做分布式事务、不做共识协议、不做高频读缓存（进程内 Moka cache 覆盖）。

持久化合同见 [Persistence Contract](../specs/core/05-persistence-contract.md)。

---

## 7. 消息总线：NATS

NATS 承担两个职责：

1. **tick broadcast**：Engine 每 3s 发布 delta，经 Gateway 推送给 WebSocket 客户端。
2. **sandbox dispatch**：Engine 通过 NATS queue-group 把 COLLECT 任务分发到共享 sandbox pool。

NATS 部署为 cluster——每节点一个实例，单节点部署即为单节点 cluster。

NATS 不需要持久化。客户端错过 delta 可以检测 gap 后回放/拉取；sandbox request 超时可按 empty commands 处理；权威状态已经在 redb。

---

## 8. 进程内组件（替代原外部服务）

| 原组件 | 替代方案 | 理由 |
|--------|---------|------|
| Dragonfly（读缓存） | Engine 进程内 Moka cache | 零网络延迟、零运维、与 Engine 同生命周期。500 玩家读请求本地内存处理 |
| ClickHouse（分析） | redb metrics table + Gateway 跨 shard 聚合 | 每 shard ~350MB/天，redb 轻松处理。跨 shard 查询由 Gateway fan-out |
| Rhai（模组脚本） | Bevy Plugin 静态编译 | 单一扩展机制——Rust crate 实现 Plugin trait，编译进 Engine 二进制 |

---

## 9. 组件职责边界

| 组件 | 权威性 | 职责 | 不负责 |
|------|--------|------|--------|
| Engine | 权威 | EXECUTE、COMMIT、确定性世界推进 | 水平分布式写世界（分片处理） |
| Sandbox Containers | 非权威 | 运行玩家 WASM，产生命令意图 | 直接修改世界 |
| redb | 权威持久化 | 原子提交 replay-critical state | 分布式事务、读缓存、OLAP |
| NATS | 非权威传输 | tick 广播、sandbox 分发 | 持久化事实 |
| Gateway | 非权威入口 | REST/MCP/WebSocket、认证边界、shard 路由 | 世界模拟 |

---

## 10. 扩展策略

可以水平扩展：

- WASM sandbox containers（共享 pool，NATS queue-group 负载均衡）
- Gateway WebSocket 连接层
- NATS cluster nodes
- Engine shards（按坐标范围增加 shard，每 shard 独立 Engine + redb）

单个 shard 内的 EXECUTE 不能拆成多台机器并行写入。原因是 command apply 必须确定性全序，ECS 系统存在跨实体依赖，replay 要求同输入同输出，且 redb commit 是单 writer 权威提交点。

通过增加 shard 实现水平扩容——每个 shard 承载一部分房间。跨 shard 玩家迁移是边界事件，不频繁。

---

## 11. 架构原则

1. **WASM 只产生命令，不写世界。**
2. **Engine 是唯一世界权威（per shard）。**
3. **redb commit 是 tick 持久化权威点。**
4. **NATS 可重建或重放，不是世界状态源。**
5. **COLLECT 追求水平扩展（共享 WASM pool）。**
6. **EXECUTE 追求确定性、可回放和低 p99。**
7. **复杂度只放在真实瓶颈上。**
8. **设计即终态——不允许 defer 到"远期方向"。**

Swarm 的扩展性来自清楚地区分并行沙箱计算和串行权威模拟，加上静态坐标分片让多 Engine 实例各自承载独立世界区域——而不是把所有组件都做成分布式系统。