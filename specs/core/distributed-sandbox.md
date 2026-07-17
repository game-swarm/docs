# Distributed WASM Sandbox 设计

> 详见 `wasm-sandbox.md`。本文是 WASM Sandbox 的 distributed profile：继承本地 sandbox 的 ABI、fuel、内存、WASI 禁用和安全约束，并把 worker transport 从本地进程通信扩展为 NATS request-reply。

## 1. 架构对比

```
当前（本地 Sandbox）:
┌──────────────────┐     gRPC (Unix socket)     ┌─────────────────┐
│  Engine (单进程)  │◄─────────────────────────►│  Sandbox Worker  │
│  Tick 调度器      │                            │  (本地进程池)     │
│  EXECUTE          │                            │  seccomp/cgroup  │
│  COMMIT (redb)    │                            │  netns 隔离      │
└──────────────────┘                            └─────────────────┘

目标（分布式 Sandbox）:
┌──────────────────┐     NATS request-reply     ┌──────────────────────┐
│  Engine (单进程)  │◄═══════════════════════════►│  Sandbox Container    │
│  Tick 调度器      │    swarm.tick.{tick}.       │  (独立容器 × N)       │
│  EXECUTE          │    player.{player_id}       │  seccomp/cgroup      │
│  COMMIT (redb)    │                             │  netns 隔离           │
└──────────────────┘                             │  WASM 预编译缓存      │
                                                 └──────────────────────┘
```

## 2. 职责边界

| 职责 | Engine | Sandbox Container |
|------|:-----:|:-----------------:|
| 世界状态 | ✅ 唯一权威源 | ❌ 不持有状态 |
| Tick 调度 | ✅ COLLECT/EXECUTE/COMMIT | ❌ |
| 指令排序 | ✅ 确定性种子洗牌 | ❌ |
| 存储 | ✅ redb 原子提交 | ❌ |
| WASM 执行 | ❌ | ✅ |
| WASM 模块缓存 | 分发 | ✅ 本地预编译缓存 |
| OS 隔离 | ❌ | ✅ seccomp/cgroup/netns |

### 2.1 Local vs Distributed Profile

| 维度 | Local profile (`wasm-sandbox.md`) | Distributed profile（本文） |
|------|-----------------------------------|-----------------------------|
| Worker 位置 | Engine 同机本地进程池 | 独立 Sandbox Container 集群 |
| Memory limit | 同一 cgroup profile，按 worker 限制 | 每容器同一 cgroup profile，按 worker 限制 |
| CPU 计量 | Wasmtime fuel + deadline | Wasmtime fuel + deadline；NATS 排队不改变 per-player deadline |
| Transport | Unix socket / 本地 IPC | NATS request-reply + queue group |
| Deadline | Engine 本地计时，超时为空命令 | Engine 发出请求时携带 absolute collect deadline，超时为空命令 |
| 状态持有 | Worker 不持有世界状态 | Worker 不持有世界状态 |

## 3. COLLECT 阶段流程

```
Tick N COLLECT 开始:

1. Engine: 构建世界快照（一次性，O(entities)）
   └─ 按房间分片，确定性序列化

2. Engine: 遍历活跃玩家，并行分发：
   for player in active_players:
       ├─ stitch 玩家可见快照（≤256KB）
       ├─ NATS publish: swarm.tick.{N}.player.{player_id}
       │   payload = {
       │     tick: N,
       │     player_id,
       │     snapshot_json: Vec<u8>,     // 可见世界快照
       │     module_hash: [u8; 32],      // 应使用的 WASM 模块
       │     fuel_budget: u64,           // 本 tick fuel 配额
       │   }
       └─ 等待 NATS reply（timeout = 2500ms）

3. Sandbox Container:
   ├─ 接收请求
   ├─ 查找/加载 WASM 模块（本地预编译缓存）
   ├─ 执行 WASM tick(snapshot)
   ├─ 收集 CommandIntent[] JSON
   └─ NATS reply: 命令列表 + metrics

4. Engine: 收集所有 reply
   ├─ 超时玩家 → 空命令列表 + timeout 标记
   ├─ 所有命令汇入 canonical sorted command list
   └─ 进入 EXECUTE 阶段（逻辑不变）
```

## 4. 通信协议

### 4.1 NATS Subject 设计

```
swarm.tick.{tick}.player.{player_id}     — 分发 WASM 执行任务（request）
swarm.tick.{tick}.player.{player_id}.reply — 返回命令结果（reply）

swarm.deploy.{module_hash}               — request-reply 推送新 WASM 模块到 sandbox

swarm.sandbox.heartbeat.{instance_id}     — sandbox 存活心跳
```

### 4.1.1 NATS 安全

NATS 连接必须使用 TLS 与 per-role ACL。Engine 只允许 publish sandbox request、subscribe sandbox reply；Sandbox worker 只允许 subscribe sandbox queue group、publish reply 与 heartbeat。除此之外，deploy/tick request 与 reply 都必须使用 `SWARM_NATS_AUTH_SECRET` 做 HMAC-SHA256 消息认证；缺少 secret、缺少 tag、tag 不匹配、timestamp 过期或重复 `(request_id, nonce)` 都必须拒绝。Sandbox worker 必须将已接受的 `(request_id, nonce)` 持久化到 `SWARM_SANDBOX_NONCE_PATH`，按 `AUTH_FRESHNESS_MS` 剪枝；开发环境默认使用私有用户状态目录，生产部署必须显式配置 `/tmp` 以外的可写持久卷。nonce store 读取、解析或原子写入失败时请求 fail closed，不得继续执行 tick/deploy payload。

认证信封固定为 `{ request_id, nonce, timestamp_ms, payload, auth_tag_hex }`，字段顺序按 Rust `AuthenticatedMessage<T>` / sandbox `AuthenticatedRequest<T>` 声明顺序序列化。`request_id` 与 `nonce` 为 16-byte lowercase hex（32 chars），`timestamp_ms` 为 Unix epoch milliseconds。HMAC 签名输入为 `serde_json::to_vec(AuthenticatedSigningMessage { request_id, nonce, timestamp_ms, payload })`，即同序字段但不包含 `auth_tag_hex`；`auth_tag_hex` 是 HMAC-SHA256 lowercase hex。NATS 内 `module_hash` 为原始 `[u8; 32]`，仅 subject、HTTP、日志和 UI 使用 lowercase 64-char hex。

```rust
struct AuthenticatedMessage<T> {
    request_id: String,
    nonce: String,
    timestamp_ms: u64,
    payload: T,
    auth_tag_hex: String,
}

struct AuthenticatedSigningMessage<'a, T> {
    request_id: &'a str,
    nonce: &'a str,
    timestamp_ms: u64,
    payload: &'a T,
}
```

### 4.2 Request 载荷

```rust
struct SandboxTickRequest {
    schema: "swarm.sandbox.tick.v1",
    tick: u64,
    player_id: String,
    room_id: String,
    module_hash: [u8; 32],         // WASM 模块标识
    snapshot_json: String,         // 可见世界快照（≤256KB）
    fuel_budget: u64,              // wasmtime fuel units
    collect_timeout_ms: u64,       // 本 tick COLLECT timeout
}
```

### 4.3 Reply 载荷

```rust
struct SandboxTickReply {
    tick: u64,
    player_id: String,
    commands: Vec<Value>,                // 指令列表（JSON）
    errors: Vec<String>,                 // Engine 兼容字段；sandbox 当前不主动填充
    metrics: SandboxExecutionMetrics,    // 执行指标
    status: String,                      // "Ok", "Timeout", "FuelExhausted", "ModuleNotFound", "Trap(...)"
}

struct SandboxExecutionMetrics {
    fuel_consumed: u64,
    wall_clock_ms: u64,
    memory_peak_bytes: u64,
    host_function_calls: u32,
}

```

## 5. WASM 模块分发

```
Engine 接收 swarm_deploy(MCP):

1. 校验 WASM、证书、签名与 version_counter，并提交 redb manifest
2. 计算 `module_hash = BLAKE3(module_bytes)` 后：
   ├─ NATS request: swarm.deploy.{module_hash_hex}
   │   payload = {
   │       schema: "swarm.sandbox.deploy.v1",
   │       module_hash: [u8; 32],
   │       module_bytes,
   │       validation_policy_version: "raw-wasm-v1",
   │   }
   └─ 等待 authenticated deploy ack；ack 校验失败、超时或非 cached 状态均视为部署失败

3. Sandbox Container 接收：
   ├─ 验证 HMAC、schema 与 BLAKE3(module_bytes) == module_hash
   ├─ 在 sandbox 进程内编译 WASM；禁止接收调用方提供的 native artifact
   ├─ 缓存键 = module_hash + wasmtime_version + validation_policy_version
    └─ NATS request reply: authenticated DeployAck

```rust
struct DeployAck {
    instance_id: String,
    module_hash: String,  // lowercase 64-char BLAKE3 hex
    status: String,       // success: "cached:{validation_policy_version}"; failure: "rejected:{reason}"
}
```

4. 未 ack 的 sandbox 在下次 tick 请求时：
   ├─ 请求携带 module_hash
   ├─ sandbox 发现本地缓存未命中
   ├─ 从 engine 请求模块（swarm.module.fetch.{module_hash}）
   └─ 本次 tick 返回 ModuleNotFound（玩家本 tick 0 指令）
```

## 6. Sandbox Container 生命周期

```
启动:
  1. 容器启动
  2. 连接 NATS；失败时按 NATS_CONNECT_RETRY_MS（默认 1000ms）持续重试
  3. 订阅: swarm.tick.*.player.* (shared queue group "sandbox-workers")
  4. 发布心跳: swarm.sandbox.heartbeat.{instance_id}
  5. 等待任务

单次 Tick 执行:
  1. 接收 swarm.tick.{tick}.player.{player_id}
  2. 从本地缓存加载 WASM 模块（预编译）
  3. 若缓存未命中 → 从 engine fetch + 编译（仅首次）
  4. Wasmtime Store reset（清空线性内存、重置 fuel、epoch deadline）
  5. 执行 tick(snapshot) → 收集 commands
  6. NATS reply 命令列表
  7. 返回等待状态

缩容:
  - Engine 维护 min_idle_sandboxes 个空闲容器
  - 空闲超过 idle_timeout 的容器自动销毁
  - 负载突增时 spawn 新容器

容器资源限制:
  - memory.max = 256MB (每 tick 执行一个玩家，非共享)
  - cpu.max = 无硬限（WASM fuel 已限制计算量）
  - 每个容器同时只处理一个 tick 请求
```

## 7. 容错

| 场景 | 行为 |
|------|------|
| Sandbox 超时（2500ms 无 reply） | 玩家本 tick 0 指令，不计入 sandbox 健康度 |
| Sandbox crash/重启 | NATS queue group 自动重新分配任务；该 tick 该玩家 0 指令 |
| NATS 不可达 | Engine/Gateway/Sandbox 都重试初始 NATS 连接；无本地 sandbox fallback。Engine 和 Gateway `/healthz` 返回 `503 degraded`；Sandbox `/healthz` 与 `/readyz` 返回 503 degraded JSON 并标明 tick/deploy 订阅不可用，进程保持存活并持续重试初始连接。 |
| 模块缓存未命中 | 即时 fetch + 编译，若仍失败 → ModuleNotFound，本 tick 0 指令 |
| Engine crash | Sandbox 等待超时后清理当前任务；恢复后从 redb 读取最后提交 tick |
| 编译失败 | 记录审计日志；本 tick 0 指令；不影响其他玩家 |

## 8. 与传统 Worker Pool 的关系

分布式 Sandbox 是 Worker Pool 的超集——本地 Worker Pool 退化为 N=1 个本地容器：

```
分布式模式（生产/大规模）:
  sandbox_backend = "nats"
  → NATS 连接外部 Sandbox Container 集群
```

当前 Engine 要求远程 NATS sandbox；`SANDBOX_BACKEND` 非 `nats` 会被忽略，不会启用本地 sandbox fallback。

## 9. 关键不变量

1. **Sandbox 不持有游戏状态**——崩溃/重启不影响世界完整性
2. **所有玩家指令在 Engine 侧确定性排序**——与 sandbox 执行顺序/位置无关
3. **超时语义与本地 Worker Pool 完全一致**——2500ms 后 0 指令
4. **redb 单写者不变**——COMMIT 仍在 Engine 单线程执行
5. **WASM 模块部署仍由 Engine 权威验证**——sandbox 仅缓存执行
