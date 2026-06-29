# Distributed WASM Sandbox 设计

> 将 WASM 执行从引擎本地 Worker Pool 解耦为独立容器，引擎仅作为权威调度器。

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
   ├─ 收集 Vec<Command> JSON
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

swarm.deploy.{module_hash}               — 推送新 WASM 模块到所有 sandbox
swarm.deploy.{module_hash}.ack           — sandbox 确认已缓存模块

swarm.sandbox.heartbeat.{instance_id}     — sandbox 存活心跳
```

### 4.2 Request 载荷

```rust
struct SandboxTickRequest {
    tick: u64,
    player_id: PlayerId,
    snapshot_json: Vec<u8>,         // 可见世界快照（≤256KB）
    module_hash: [u8; 32],         // WASM 模块标识
    fuel_budget: u64,              // wasmtime fuel units
    collect_timeout_ms: u64,       // 本 tick COLLECT 截止时间（墙钟绝对时间）
}
```

### 4.3 Reply 载荷

```rust
struct SandboxTickReply {
    tick: u64,
    player_id: PlayerId,
    commands: Vec<RawCommand>,           // 指令列表（JSON）
    metrics: SandboxExecutionMetrics,    // 执行指标
    status: SandboxExecutionStatus,      // 执行状态
}

struct SandboxExecutionMetrics {
    fuel_consumed: u64,
    wall_clock_ms: u64,
    memory_peak_bytes: u64,
    host_function_calls: u32,
}

enum SandboxExecutionStatus {
    Ok,
    Timeout,
    FuelExhausted,
    Trap(String),
    Oom,
    ModuleNotFound,
}
```

## 5. WASM 模块分发

```
Engine 接收 swarm_deploy(MCP):

1. 校验 WASM + 编译 + FDB manifest commit（逻辑不变）
2. 编译完成后：
   ├─ 计算 compiled_artifact_hash
   ├─ NATS broadcast: swarm.deploy.{compiled_artifact_hash}
   │   payload = {
   │       module_hash, compiled_artifact_hash,
   │       wasm_bytes,                    // 原始 WASM 二进制
   │       compiled_native_bytes,         // 预编译原生码（可选）
   │       wasmtime_version,              // 版本对齐
   │       validation_policy_version,
   │   }
   └─ 等待所有活跃 sandbox ack（或 timeout 后继续——不阻塞）

3. Sandbox Container 接收：
   ├─ 存储 WASM 二进制 + 预编译模块到本地缓存
   ├─ 缓存键 = Blake3(compiled_artifact_hash || wasmtime_version)
   └─ NATS reply: swarm.deploy.{compiled_artifact_hash}.ack

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
  2. 连接 NATS
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
| NATS 断连 | Engine 本地降级：等待超时 → 所有玩家 0 指令（degraded mode） |
| 模块缓存未命中 | 即时 fetch + 编译，若仍失败 → ModuleNotFound，本 tick 0 指令 |
| Engine crash | Sandbox 等待超时后清理当前任务；恢复后从 redb 读取最后提交 tick |
| 编译失败 | 记录审计日志；本 tick 0 指令；不影响其他玩家 |

## 8. 与传统 Worker Pool 的关系

分布式 Sandbox 是 Worker Pool 的超集——本地 Worker Pool 退化为 N=1 个本地容器：

```
本地模式（开发/小规模）:
  sandbox_backend = "local"
  → Engine 上运行 1 个本地 Sandbox Container（同机）

分布式模式（生产/大规模）:
  sandbox_backend = "nats"
  → NATS 连接外部 Sandbox Container 集群
```

模式切换仅在 Engine 配置中修改 `sandbox_backend`——Sandbox Container 代码完全一致。

## 9. 关键不变量

1. **Sandbox 不持有游戏状态**——崩溃/重启不影响世界完整性
2. **所有玩家指令在 Engine 侧确定性排序**——与 sandbox 执行顺序/位置无关
3. **超时语义与本地 Worker Pool 完全一致**——2500ms 后 0 指令
4. **redb 单写者不变**——COMMIT 仍在 Engine 单线程执行
5. **WASM 模块部署仍由 Engine 权威验证**——sandbox 仅缓存执行