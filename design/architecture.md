# Swarm 架构总览

> 本文是 Swarm 的架构入口：说明系统边界、tick 热路径、分片模型与关键组件职责。
> [Engine](engine.md) 与 [Tech Choices](tech-choices.md) 是同一设计面的拆分；core/security/reference specs 是由本文输出的落地合同，不是本文的决策来源。

**设计原则：设计即终态。没有"未裁决方向"、"阶段"、"extension"、"以后再说"。每一个架构决策必须在当下裁定最佳实践，不允许 推迟。**

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

世界按静态坐标范围分片。每个 shard 固定覆盖 **50x50 rooms**，最多承载 **500 active players**。world.toml 声明固定 shard 尺寸与部署容量，不允许改变单 shard 的 50x50 几何：

```toml
[sharding]
shard_size = { width = 50, height = 50 }                # 固定，不可按世界覆盖
shard_cap = { max_active_players = 500 }                 # 每 shard 活跃玩家上限
routing = "fixed-grid-v1"
deployed_shards = [
  { shard_id = "0:0", origin_room = [0, 0] }
]
```

**性质**：

- shard_id = (floor(room_x / 50), floor(room_y / 50))，由固定几何 O(1) 计算，无需运行时 coordinator
- 每 shard 一个 Engine 进程 + 一个 redb 文件
- WASM worker pool 跨所有 shard 共享——worker 无状态，不绑定任何 shard
- visibility snapshot 在 shard 边界硬裁剪；玩家代码不能读取相邻 shard 的房间、实体或敌对状态
- shard 边界两侧没有跨 shard combat、heal、ranged attack、area effect、claim 或资源交互；所有 gameplay effect 只能在当前 shard 内结算
- 跨 shard 通信仅在玩家迁移时发生（drone 穿过 shard 边界的房间出口），不在热路径
- 单玩家同时只在一个 shard
- 无 cluster、无 leader election、无 gossip

#### 2.1 跨 shard 迁移协议

迁移使用 redb durable outbox，不使用全局事务或全局链。源 shard 和目标 shard 都记录同一个 `migration_id`，形成双边 audit trail。

迁移单位是 **entire player bundle**，不是单个 crossing drone。触发边界 Move 前，源 shard 必须确认玩家没有仍归属源 shard 的 claimed room 或固定 structure；存在时拒绝迁移，玩家需先 relinquish/recycle。所有 owned drones、player/global storage、active module slots、version counters 和私有 player state 进入同一迁移包。目标 shard 以 crossing drone 的出口为 anchor，按 StableEntityId 升序把其余 drones 放入 deterministic entry formation；任一位置/capacity 校验失败则 Prepare 失败并在 ACK 前取消。

Shard 间 Stage/Prepare/ACK/Commit 使用 `swarm.migration.v1.<target_shard>` authenticated transport：mTLS + per-shard NATS ACL，并对 canonical envelope `version|migration_id|source_shard|target_shard|phase|sequence|timestamp|payload_hash` 做 HMAC-SHA256。密钥来自 `SWARM_MIGRATION_AUTH_SECRET`。接收方必须验证 source/target 与当前相邻 shard topology、source 对 player 的权威归属、phase/sequence 单调性、timestamp window、payload hash 和 HMAC；`(migration_id, phase, sequence)` 在 redb 原子去重。解析、鉴权、store 或 payload 校验失败全部 fail closed，不写 ACK/Commit。

1. **Stage**：源 shard 在 tick N 写入 migration outbox 记录，冻结玩家在源 shard 的可交互状态，并把迁移包内容 hash 固定。
2. **Prepare**：目标 shard 收到 Stage 后预留目标入口和玩家槽位。Prepare 最早在 N+1 生效；超过 10 ticks 未完成则取消，源 shard 解冻玩家。
3. **ACK**：目标 shard durable 写入 ACK 后，源 shard 进入不可回退段。ACK 后所有重试都必须持续到完成，不能因为网络超时回滚。
4. **Source Tombstone / Commit**：源 shard tombstone 原玩家状态并提交 tick；该玩家从源 shard visibility、combat 和 command validation 中消失。
5. **Destination Activation**：目标 shard 在 Commit 后激活玩家状态。激活 tick 不早于 N+1，且目标 shard 的 player slot 计入 500 active players cap。

迁移失败只影响迁移中的玩家。Prepare 超时前，源 shard 按空命令处理该玩家；Prepare 取消后恢复正常。ACK 后如果目标 activation 暂时不可达，源 shard 保持 tombstone，目标 shard 重试 activation 直到完成。

---

## 3. 架构图

```
                 ┌──────────────────────────────────────────┐
                 │              Web / MCP Clients            │
                 │  WebSocket (/ws) · MCP over HTTP (/mcp)   │
                 └───────────────┬──────────────────────────┘
                                 │
                                 ▼
                         ┌──────────────┐
                         │   Gateway    │
                         │ Rust (axum)  │
                         │ 路由 · WS · /mcp · 认证边界  │
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
        │    Bevy ECS: 25 registered Pass 2b systems              │
        │    + 6 Pass 2a inline handlers = 31 combined            │
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
6. timeout、trap、fuel exhausted 或 replay-critical artifact 缺失转化为 rejection 或 empty commands，不修改世界状态。

关键性质：

- 每个玩家看到自己的可见性快照。
- visibility snapshot 永远裁剪到当前 shard；边界外房间即使在几何范围内也不可见。
- sandbox 之间零共享状态、零互相依赖。
- sandbox 失败不会污染 Bevy World。
- 通过 NATS queue-group 分布式执行，无 dispatcher 单点。
- 玩家模块所需 artifact 丢失时，仅暂停受影响玩家模块并提交 empty commands；世界 tick、其他玩家和 shard 迁移继续推进。

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
3. 按确定性键全序排序：`player_order` → `player_id` → `sequence` → `command_id`。
4. 串行 apply command。
5. 执行 Bevy ECS 固定系统链。
6. 生成 state delta、rejection、fuel、checksum。

关键性质：

- 相同输入必须得到相同世界状态。
- 在线执行和 replay 必须共享同一确定性语义。
- ECS 系统注册顺序固定。
- 固定调度为 6 个 System Pass 2a inline handlers + 25 个 registered Pass 2b systems = 31 combined entries per tick。
- `command_id = blake3(canonical RawCommand bytes)`；RawCommand 的 canonical form 包含 WASM 输出、服务端注入的 `player_id`、tick、source 和 auth context。
- Admin control plane 事件不进入 gameplay command sort；admin/deploy/rollback 先形成 tick input context，gameplay order 只排序玩家命令。

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
- 永久保留 replay-critical history，足以从 genesis 重新回放到任意 tick。

redb 永久保存 TickCommitRecord、canonical command hash 列表、rejection/fuel/accounting、state checksum、tick input envelope、migration outbox/tombstone/activation records，以及从 genesis replay 所需的 world config 和 mod manifest hash lineage。redb 不做分布式事务、不做共识协议、不做高频读缓存（进程内 Moka cache 覆盖）。

---

## 6a. Blob Store（非权威二进制存储）

Blob Store 存储 redb 不适合存的大型二进制对象。**非权威**——丢失不影响确定性 replay，因为 redb 已永久保留从 genesis replay 所需的历史。Blob/keyframe stores 只承担加速和 rich audit。

| 数据类型 | 存储内容 | 可丢失? | 保留策略 |
|---------|---------|:------:|---------|
| RichTraceBlob | 完整 TickTrace（debug detail、per-system metrics） | ✅ 可降级 | `rich_artifact_retention_ticks` 默认 864000 |
| ReplayArtifact | 回放验证自包含 bundle | ✅ 可由 redb 历史重建 | 与 rich artifact retention 一致 |
| WasmModuleArtifact | WASM binary + manifest + compiled execution artifact | ❌ 玩家模块执行需要 | 每 world/module_slot 最近 10 版 + active slot/rollback pin/operator hold；历史 replay manifest 本身不构成引用 |

这两个 retention 值使用 tick 单位，可在 `world.toml [retention]` 调整；只影响 rich audit/恢复速度，不得裁剪 redb replay-critical history。

**Keyframe Store 是独立存储边界**：`/data/swarm/keyframes/` primary + 独立故障域 backup，保存每 K tick 全量快照，默认 `keyframe_acceleration_retention_ticks = 5_184_000`。它不使用 `[blob_store]` backend，也不与 RichTrace/WASM blob GC 混合。

**默认后端**：本地文件系统 `/data/swarm/blobs/`，按 shard 分目录。

**可配置远端**：通过 `world.toml` 切换为 S3 兼容存储：

```toml
[blob_store]
backend = "s3"                              # "local" (默认) | "s3"
[blob_store.local]
path = "/data/swarm/blobs"
[blob_store.s3]
endpoint = "https://s3.example.com"
bucket = "swarm-blobs"
region = "auto"
access_key = "$S3_ACCESS_KEY"               # 环境变量引用
secret_key = "$S3_SECRET_KEY"
```

Blob Store 不是权威源——redb 的 TickCommitRecord 保存所有 blob 的 content hash 指针。任何 blob 丢失都不影响 world state 或 deterministic replay 完整性；`WasmModuleArtifact` 丢失还会暂停对应玩家模块，其他 blob 丢失只影响 debug、audit 或恢复速度。

对象存储角色是显式的：WasmModuleArtifact 是玩家模块执行输入；RichTraceBlob 是 rich audit；ReplayArtifact 和 Keyframe Snapshot 是 replay 加速。只有 WasmModuleArtifact 丢失会暂停对应玩家模块并产生 empty commands；其他对象丢失只降低调试、审计或恢复速度。

---

## 7. 消息总线：NATS

NATS 承担两个职责：

1. **tick broadcast**：Engine 每 3s 发布 delta，经 Gateway 推送给 WebSocket 客户端。
2. **sandbox dispatch**：Engine 通过 NATS queue-group 把 COLLECT 任务分发到共享 sandbox pool。

NATS 部署为 cluster——每节点一个实例，单节点部署即为单节点 cluster。所有环境，包括本地开发、CI、单机部署和生产，都使用 NATS request-reply + queue-group 访问同一个 stateless sandbox pool。

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
| Admin Control Plane | 非 gameplay 输入 | deploy、rollback、operator action、world config 变更进入 tick input context | 参与玩家命令排序、改变同 tick gameplay priority |

---

## 9a. ABI 与二进制合同

ABI v2 是立即生效的 breaking cutover。Snapshots、`TickResult`、`HostResult` 和 sandbox host boundary payload 全部使用 IDL-generated Swarm binary codec，不保留 v1 JSON/bincode 兼容路径。

IDL 是 codec 和 SDK 类型生成输入；输出物包括 Swarm binary schemas、host bindings、SDK 类型和 reference docs。Engine、Sandbox、Gateway、SDK 必须在同一个 ABI v2 schema hash 上运行，hash 不匹配直接拒绝启动或部署。

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
8. **设计即终态——不允许 推迟 到"未裁决方向"。**

Swarm 的扩展性来自清楚地区分并行沙箱计算和串行权威模拟，加上静态坐标分片让多 Engine 实例各自承载独立世界区域——而不是把所有组件都做成分布式系统。
