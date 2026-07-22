# Distributed WASM Sandbox 设计

> 详见 `design/engine.md` 与 `wasm-sandbox.md`。本文从 design 下沉 Sandbox dispatch contract：所有环境使用 NATS request-reply + queue group 调度共享的无状态 worker pool，继承 ABI、fuel、内存、WASI 禁用和安全约束。

## 1. 架构

```
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
| WASM 原始字节预编译与 hash attestation | 发送/验证 attestation | ✅ 唯一编译者 |
| WASM 模块缓存 | 分发 | ✅ 本地预编译缓存 |
| OS 隔离 | ❌ | ✅ seccomp/cgroup/netns |

### 2.1 Shared Stateless Worker Pool

| 维度 | Contract |
|------|----------|
| Worker 位置 | 独立 Sandbox Container，可本机或远端部署，但调度语义相同 |
| Memory limit | 每容器同一 cgroup profile，按 worker 限制 |
| CPU 计量 | Wasmtime fuel + deadline；NATS 排队不改变 per-player deadline |
| Transport | NATS request-reply + queue group |
| Deadline | Engine 发出请求时携带 absolute collect deadline，超时为空命令 |
| 状态持有 | Worker 不持有世界状态，不绑定 shard |

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
        │     tick_input: Vec<u8>,       // TickInput Swarm codec bytes
       │     module_hash: [u8; 32],      // 应使用的 WASM 模块
       │     fuel_budget: u64,           // 本 tick fuel 配额
       │   }
       └─ 等待 NATS reply（timeout = 2500ms）

3. Sandbox Container:
   ├─ 接收请求
   ├─ 查找/加载 WASM 模块（本地预编译缓存）
   ├─ 执行 WASM tick(TickInput bytes)
   ├─ 收集 TickResult bytes
   └─ NATS reply: TickResult bytes + metrics

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

认证信封固定为 `{ request_id, nonce, timestamp_ms, payload, auth_tag_hex }`，字段顺序按 Rust `AuthenticatedMessage<T>` / sandbox `AuthenticatedRequest<T>` 声明顺序序列化。`request_id` 与 `nonce` 为 16-byte lowercase hex（32 chars），`timestamp_ms` 为 Unix epoch milliseconds。HMAC 签名输入为 `canonical_swarm_codec(AuthenticatedSigningMessage { request_id, nonce, timestamp_ms, payload })`，即同序字段但不包含 `auth_tag_hex`；`auth_tag_hex` 是 HMAC-SHA256 lowercase hex。NATS 内 `module_hash` 为原始 `[u8; 32]`，仅 subject、HTTP、日志和 UI 使用 lowercase 64-char hex。

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
    schema: "swarm.sandbox.tick.v2",
    tick: u64,
    player_id: String,
    room_id: String,
    module_hash: [u8; 32],         // WASM 模块标识
    tick_input: Vec<u8>,           // TickInput Swarm codec bytes（≤256KB）
    fuel_budget: u64,              // wasmtime fuel units
    collect_timeout_ms: u64,       // 本 tick COLLECT timeout
}
```

### 4.3 Reply 载荷

```rust
struct SandboxTickReply {
    tick: u64,
    player_id: String,
    tick_result: Vec<u8>,                // TickResult Swarm codec bytes
    errors: Vec<String>,                 // ABI/执行错误；成功时为空
    metrics: SandboxExecutionMetrics,    // 执行指标
    status: String,                      // "Ok", "Timeout", "FuelExhausted", "ArtifactUnavailable", "Trap(...)"
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

1. 校验 WASM bytes、证书、签名、DeployPayload hash 与 version_counter；此时不提交 manifest
2. 计算 `module_hash = BLAKE3(module_bytes)` 后：
   ├─ NATS request: swarm.deploy.{module_hash_hex}
   │   payload = {
│       schema: "swarm.sandbox.deploy.v2",
   │       module_hash: [u8; 32],
   │       module_bytes,
│       validation_policy_version: "raw-wasm-v2",
   │   }
   └─ 等待 authenticated deploy ack；ack 校验失败、超时或非 cached 状态均视为部署失败

3. Sandbox Container 接收：
   ├─ 验证 HMAC、schema 与 BLAKE3(module_bytes) == module_hash
   ├─ 在 sandbox 进程内编译 WASM；禁止接收调用方提供的 native artifact
   ├─ 将 compiled artifact + attestation 写入共享 Artifact Store primary + backup
   ├─ 缓存键 = module_hash + wasmtime_version + validation_policy_version
    └─ NATS request reply: authenticated DeployAck

```rust
struct DeployAck {
    instance_id: String,
    module_hash: String,  // lowercase 64-char BLAKE3 hex
    compiled_artifact_hash: String,
    wasmtime_version: String,
    validation_policy_version: String,
    artifact_ref: String,
    replica_etags: [String; 2],
    status: String,       // success: "cached:{validation_policy_version}"; failure: "rejected:{reason}"
    attestation: String,  // HMAC(instance_id || hashes || versions || artifact_ref || replica_etags || status)
}
```

4. Engine verifies DeployAck HMAC, hashes, pinned versions, artifact_ref and both replica etags. Only then may it commit the manifest. Any tick worker with a cache miss fetches this attested artifact from the shared store and verifies the same fields before load; it does not contact the original worker.

5. 任意 worker 在下次 tick cache miss 时：
   ├─ 请求携带 module_hash
   ├─ sandbox 发现本地缓存未命中
   ├─ 从 shared Artifact Store 获取 manifest 指向的 attested compiled artifact
   ├─ 验证 artifact hash、Sandbox attestation、Wasmtime/policy version 后载入
   └─ shared store/attestation 失败 → `ArtifactUnavailable`，slot 进入 PAUSED_RECOVERY；不得回退到 Engine module fetch
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
  3. 若缓存未命中 → 从 shared Artifact Store fetch + verify attestation；禁止 Engine fetch/JIT fallback
  4. Wasmtime Store reset（清空线性内存、重置 fuel、epoch deadline）
5. 执行 tick(TickInput bytes) → 收集 TickResult bytes
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
| NATS 不可达 | Engine/Gateway/Sandbox 都重试初始 NATS 连接；无本地 sandbox fallback。Engine 和 Gateway `/healthz` 返回 `503 degraded`；Sandbox `/healthz` 与 `/readyz` 返回 503 degraded health payload 并标明 tick/deploy 订阅不可用，进程保持存活并持续重试初始连接。 |
| 模块缓存未命中 | 从 shared Artifact Store fetch + verify attestation；失败 → ArtifactUnavailable，本 tick 0 指令并进入 PAUSED_RECOVERY |
| Engine crash | Sandbox 等待超时后清理当前任务；恢复后从 redb 读取最后提交 tick |
| 编译失败 | 记录审计日志；本 tick 0 指令；不影响其他玩家 |

## 8. Worker Pool 部署模型

Sandbox worker pool 始终通过 NATS queue group 调度；单机部署只是 N=1 个 Sandbox Container 连接同一个 NATS subject，不改变 transport 或调度语义：

```
统一模式（本地/CI/生产）:
  sandbox_backend = "nats"
  → NATS 连接 Sandbox Container worker pool
```

当前 Engine 要求 NATS sandbox；`SANDBOX_BACKEND` 非 `nats` 会被忽略，不会启用本地/Unix sandbox fallback。

## 9. 关键不变量

1. **Sandbox 不持有游戏状态**——崩溃/重启不影响世界完整性
2. **所有玩家指令在 Engine 侧确定性排序**——与 sandbox 执行顺序/位置无关
3. **超时语义统一**——2500ms 后 0 指令，与 worker 所在主机无关
4. **redb 单写者不变**——COMMIT 仍在 Engine 单线程执行
5. **WASM 模块部署仍由 Engine 权威验证**——sandbox 仅缓存执行
