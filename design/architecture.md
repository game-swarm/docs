# Swarm 架构总览

> 本文是 Swarm 的架构入口：说明系统边界、tick 热路径、扩展方式与关键组件职责。详细规则见
> [Engine](engine.md)、[Tech Choices](tech-choices.md)、[Tick Protocol](../specs/core/01-tick-protocol.md)、
> [WASM Sandbox](../specs/core/04-wasm-sandbox.md)、[Persistence Contract](../specs/core/05-persistence-contract.md)、
> [Complete Tick Execution Manifest](../specs/core/06-phase2b-system-manifest.md)、
> [Distributed Sandbox](../specs/core/12-distributed-sandbox.md)。

---

## 1. 核心判断

Swarm 的计算分成两层，二者扩展性质完全不同：

1. **WASM Execution / COLLECT**：玩家代码执行。无共享状态、无跨玩家依赖，天然并行，可水平扩展。
2. **World Simulation / EXECUTE**：权威世界模拟。所有命令确定性排序后串行应用，必须保持同输入同输出，是真实瓶颈。

这一区分决定了架构边界：

- sandbox container 可以横向增加。
- 单个权威世界的 EXECUTE 不能靠多机并行写入提升吞吐。
- redb、NATS、Dragonfly、ClickHouse 都围绕单实例 Engine 服务，而不是替代 Engine 的权威性。

---

## 2. 架构图

```
                 ┌──────────────────────────────────────────┐
                 │              Web / MCP Clients            │
                 │  WebSocket delta · REST/MCP world query   │
                 └───────────────┬──────────────────────────┘
                                 │
                                 ▼
                         ┌──────────────┐
                         │   Gateway    │
                         │ Go API / WS  │
                         └──────┬───────┘
                                │
                         NATS tick broadcast
                                │
┌───────────────────────────────▼────────────────────────────────┐
│                              NATS                               │
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
│  stateless, distributed       │                │
│  timeout => empty commands    │                │
└───────────────┬──────────────┘                │
                │ commands                       │
                ▼                                │
        ┌────────────────────────────────────────┴──────────────┐
        │                    Engine (Rust)                       │
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
        │    cache update                                        │
        │    tick delta publish                                  │
        └───────────────┬───────────────┬──────────────┬────────┘
                        │               │              │
                        ▼               ▼              ▼
              ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
              │     redb     │  │  Dragonfly   │  │  ClickHouse  │
              │ single .redb │  │ read cache   │  │ async OLAP   │
              │ authoritative│  │ non-authority│  │ metrics      │
              └──────────────┘  └──────────────┘  └──────────────┘
```

---

## 3. Tick 热路径

每个 tick 分三段：

```
COLLECT -> EXECUTE -> COMMIT
```

### 3.1 COLLECT：可并行

COLLECT 运行玩家 WASM：

1. Engine 为每个玩家生成 visibility snapshot。
2. snapshot 与 module hash 通过本地 worker 或 NATS 分发到 sandbox container。
3. 每个 sandbox 独立执行玩家 `tick()`。
4. WASM 输出 `CommandIntent`。
5. timeout、trap、fuel exhausted 转化为 rejection 或 empty commands，不修改世界状态。

关键性质：

- 每个玩家看到自己的可见性快照。
- sandbox 之间零共享状态、零互相依赖。
- sandbox 失败不会污染 Bevy World。
- 可通过 NATS request-reply 分布式执行，见 [Distributed Sandbox](../specs/core/12-distributed-sandbox.md)。

扩展方式：

```
更多玩家 / 更多 WASM CPU 消耗
        => 增加 sandbox container
        => Engine 只收集结果
```

### 3.2 EXECUTE：必须顺序确定

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

### 3.3 COMMIT：单事务推进世界

COMMIT 把 tick 结果变成持久事实：

1. redb `WriteTransaction` 原子写入 replay-critical subset。
2. 推进 tick head 与 state checksum。
3. 更新 Dragonfly 读缓存。
4. 通过 NATS 发布 tick delta。
5. 异步写入 ClickHouse tick metrics。

COMMIT 的权威点是 redb commit。Dragonfly、NATS、ClickHouse 都不是世界状态来源。

---

## 4. 两层计算模型

| 层 | 阶段 | 输入 | 输出 | 失败语义 | 扩展方式 |
|----|------|------|------|----------|----------|
| WASM Execution | COLLECT | visibility snapshot + module hash + tick context | commands / rejections / fuel usage | timeout = empty commands；trap 不污染世界 | 水平扩展 sandbox containers |
| World Simulation | EXECUTE | validated commands + current Bevy World | next Bevy World + TickCommitRecord | commit 前失败则 tick 不推进 | 垂直扩展与 ECS 优化 |

WASM 层是不可信计算层。它只生产意图，不直接写世界。

World Simulation 是可信计算层。所有玩家、客户端、MCP、缓存最终都以 Engine 的 EXECUTE 结果为准。

---

## 5. 存储：redb

redb 是 Swarm 的权威持久化层：

- 嵌入式 ACID KV。
- 纯 Rust，零 C 依赖。
- 单 `.redb` 文件。
- 无外部 daemon。
- `WriteTransaction` 支持每 tick 多 key batch 原子提交。
- 单 Engine 实例天然对应单 writer。

redb 不做分布式事务、不做共识协议、不承载高频读缓存职责，也不承载 OLAP 聚合查询职责。历史选型从 FDB 到 TiKV 再到 redb，每一步都删除了当前架构不需要的复杂度：Swarm 的世界权威点是单实例 Engine，存储层只需要可靠提交这个权威结果。

持久化合同见 [Persistence Contract](../specs/core/05-persistence-contract.md)。

---

## 6. 消息总线：NATS

NATS 承担两个职责：

1. **tick broadcast**：Engine 每 3s 发布 delta，经 Gateway 推送给 WebSocket 客户端。
2. **sandbox dispatch**：Engine 通过 request-reply 把 COLLECT 任务分发到 sandbox containers。

NATS 不需要持久化。客户端错过 delta 可以检测 gap 后回放/拉取；sandbox request 超时可按 empty commands 处理；权威状态已经在 redb。NATS 的价值是轻量、低运维成本、Go 单二进制和简单 pub/sub，而不是事件溯源。

---

## 7. 缓存：Dragonfly

Dragonfly 是非权威读缓存：

- 服务 MCP 查询。
- 服务 WebSocket 当前世界状态读取。
- 缓解 redb 与 Engine 热读压力。
- Redis 协议兼容。
- 多线程，目标约 1M QPS 级读吞吐。

缓存允许滞后或重建。任何冲突都以 redb 与 Engine tick head 为准。Dragonfly 不参与 command apply、replay 判定、tick commit 原子性，也不参与 deploy mutation 的严格防重放。

---

## 8. 分析：ClickHouse

ClickHouse 用于异步分析，不在 tick 热路径上。

写入内容包括每 tick 每玩家 fuel 消耗、command rejection 统计、world delta 大小、资源、扩张、战斗和经济指标。它回答的是列式 OLAP 问题，例如：

```
过去 1000 tick 中哪个玩家扩张最快？
哪些 command 类型 rejection 最高？
哪个 ruleset 导致 fuel 消耗异常？
```

这些查询不应该压到 redb 或 Engine 热路径上。

---

## 9. 组件职责边界

| 组件 | 权威性 | 职责 | 不负责 |
|------|--------|------|--------|
| Engine | 权威 | EXECUTE、COMMIT、确定性世界推进 | 水平分布式写世界 |
| Sandbox Containers | 非权威 | 运行玩家 WASM，产生命令意图 | 直接修改世界 |
| redb | 权威持久化 | 原子提交 replay-critical state | 分布式事务、OLAP |
| NATS | 非权威传输 | tick 广播、sandbox 分发 | 持久化事实 |
| Dragonfly | 非权威缓存 | 高频读缓存、session/nonce 热路径 | 世界真相源 |
| ClickHouse | 非权威分析 | tick metrics、聚合查询 | tick 热路径决策 |
| Gateway | 非权威入口 | REST/MCP/WebSocket、认证边界 | 世界模拟 |

---

## 10. 扩展策略

可以水平扩展：

- WASM sandbox containers。
- Gateway WebSocket 连接层。
- NATS consumers。
- Dragonfly 读缓存。
- ClickHouse ingestion/query。

单个权威世界的 EXECUTE 不能简单拆成多台机器并行写入。原因是 command apply 必须确定性全序，ECS 系统存在跨实体依赖，replay 要求同输入同输出，且 redb commit 是单 writer 权威提交点。

远期 shard protocol 可以改变世界拓扑边界，但不是让同一个冲突域内的 tick apply 随意并行。相关边界见 [Shard Protocol](../specs/core/11-shard-protocol.md)。

---

## 11. 架构原则

1. **WASM 只产生命令，不写世界。**
2. **Engine 是唯一世界权威。**
3. **redb commit 是 tick 持久化权威点。**
4. **Dragonfly、NATS、ClickHouse 都可重建或重放。**
5. **COLLECT 追求水平扩展。**
6. **EXECUTE 追求确定性、可回放和低 p99。**
7. **复杂度只放在真实瓶颈上。**

Swarm 的扩展性来自清楚地区分并行沙箱计算和串行权威模拟，而不是把所有组件都做成分布式系统。
