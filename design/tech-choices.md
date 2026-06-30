# Swarm 技术选型

> 技术选型的落地规范见 [WASM Sandbox](../specs/core/wasm-sandbox.md)、[Persistence Contract](../specs/core/persistence-contract.md)、[Snapshot Contract](../specs/core/snapshot-contract.md)、[Command Source](../specs/security/command-source.md)。

**设计原则：设计即终态。没有"远期方向"、Phase、future、deferred、"以后再说"或版本分期。每一个技术选型必须按当下最佳实践一次性裁定；不得用分期实现、暂缓决定或保留旧方案并存来逃避取舍。实现顺序只记录在 ROADMAP，不进入设计和规范。**

## 1. 引擎框架: Rust + Bevy ECS

### 备选

| 方案 | 语言 | ECS | 优势 | 劣势 |
|------|------|-----|------|------|
| Bevy | Rust | ✅ 原生 | `.chain()` 天然适配确定性排序；活跃社区；纯 Rust 无 FFI | 相对年轻，API 仍在小版本变动 |
| Legion | Rust | ✅ 原生 | 更成熟稳定 | 已归档，不再维护 |
| Flecs | C | ✅ 原生 | 最快的 ECS；C99 可嵌入任何语言 | FFI 开销；Rust 绑定非一等公民 |
| Unity DOTS | C# | ✅ 原生 | 成熟编辑器 | 闭源；不是 headless 设计；许可费用 |
| 自研 ECS | Rust | ✅ | 完全控制 | 重复造轮子；需要自己解决调度、并行、查询优化 |
| Godot + Rust | GDScript/C++ | ❌ | 免费开源 | 不是真正的 ECS；确定性和 headless 不够好 |

### 选择: Bevy

`.chain()` 强制系统串行执行，和 Determinism Contract 完美匹配。Bevy Plugin trait 是唯一的扩展机制——Mod 就是实现 Plugin 的 Rust crate，静态编译进 Engine。纯 Rust 无 FFI，WASM 沙箱和 Bevy 共享同一 allocator。社区活跃度是 Rust 游戏引擎中最高的。

---

## 2. 玩家沙箱: WASM + Wasmtime

> 沙箱实现详见 [WASM Sandbox](../specs/core/wasm-sandbox.md)。

### 备选

| 方案 | 类型 | 优势 | 劣势 |
|------|------|------|------|
| Wasmtime | 独立运行时 | fuel metering 原生；epoch interruption；pinnable version；C API | 相对重（依赖 Cranelift JIT） |
| Wasmer | 独立运行时 | 多编译器后端 (LLVM/Cranelift/Singlepass) | fuel metering API 不如 Wasmtime 成熟 |
| WasmEdge | 独立运行时 | 云原生定位；轻量 | fuel metering 不原生支持，需自己实现 |
| V8 Isolate | JS 引擎 | 最快的 WASM JIT | fuel metering 不支持；embedding API 复杂；不是为沙箱游戏设计的 |
| Docker/gVisor | 容器 | 隔离性最强 | 启动慢（不能 per-tick fork）；不可确定 |

### 选择: Wasmtime

三个硬需求决定了选择：(1) fuel metering 原生支持——能精确计费每 tick 的 CPU 消耗；(2) epoch interruption——超时即杀，配合 2500ms 硬截止；(3) long-lived worker pool + per-tick clean Store/Instance reset——预编译模块池复用，每 tick 重置 WASM 状态，tick 间无状态泄漏。这三个在 Wasmtime 中是一等公民 API，其他备选需要自己实现至少一项。

**WASM worker pool 跨所有 shard 共享**——worker 无状态、无 shard 亲和性。通过 NATS queue-group 自动负载均衡。

---

## 3. 模组系统: Bevy Plugin 静态编译

**Rhai 已被移除**——Bevy Plugin trait 是唯一的扩展机制。

### 模型

```
Mod = Rust crate implementing Bevy Plugin trait

pub struct EmpireUpkeepMod;
impl Plugin for EmpireUpkeepMod {
    fn build(&self, app: &mut App) {
        app.add_systems(Update, empire_upkeep_system);
        app.insert_resource(EmpireUpkeepConfig::default());
    }
}

Engine build: cargo build --features "mod_empire_upkeep,mod_fog_of_war"
Deployment: single binary = base engine + selected mods
```

### 选型理由

| 对比 | Rhai（已移除） | Bevy Plugin 静态编译（当前） |
|------|--------------|---------------------------|
| 语言 | 服主学 Rhai 语法 | 服主写 Rust（与引擎同语言） |
| 集成深度 | 通过注册 API，受限于暴露的函数 | 完全访问 Bevy ECS，直接注册 system |
| 安全隔离 | 脚本 panic = 错误返回 | 编译时类型安全，无运行时隔离需求（服主信任） |
| 发布 | `.rhai` 文件 | 源码 crate，服主编译 |
| 性能 | AST 解释 | 原生编译 |
| 确定性 | 需引擎保证（脚本可能调非确定性 API） | 编译器 + ECS 调度保证 |
| 扩展复杂度 | 两套扩展机制（Rhai + WASM） | 一套（Bevy Plugin） |

两层信任模型：

| 层 | 机制 | 信任 | 能力 |
|---|---|---|---|
| 玩家代码 | WASM 沙箱（sandbox 进程） | 不可信 | 只产 `Command[]` |
| 引擎 + Mod | Rust 静态编译（Engine 进程内） | 服主信任 | 完全访问 ECS、注册 system、定义建筑/action/规则 |

---

## 4. 持久化: redb

> 持久化合同详见 [Persistence Contract](../specs/core/persistence-contract.md)，快照模型详见 [Snapshot Contract](../specs/core/snapshot-contract.md)。

### 备选

| 方案 | 事务模型 | 优势 | 劣势 |
|------|---------|------|------|
| redb | 嵌入式 ACID WriteTransaction | 纯 Rust；每 shard 一个 `.redb` 文件；零外部 daemon；多 key batch 原子提交天然适配 tick | 单进程嵌入式存储 |
| SQLite | 可序列化 | 零运维；单文件 | SQL 层和 schema 迁移成本更高；Rust KV 使用不如 redb 直接 |
| PostgreSQL | 可重复读 | 生态最强 | 不是严格可序列化（默认）；每 tick 提交在 MVCC 下有写放大 |
| RocksDB | 快照隔离 | 极快写入 | 不是严格可序列化；无跨 key 事务保证 |
| 分布式 KV | 分布式事务/复制 | 水平扩展 | shard 内单 writer 不需要分布式事务；外部集群运维与故障面不匹配 |

### 选择: redb

Swarm 的权威点是单实例 Engine（per shard）：tick 在内存 Bevy World 中执行，持久化层只需要在 tick 末尾把 replay-critical 的多个 key 作为一个 batch 原子写入。redb 的 `WriteTransaction` 保证这些 key 同生共死。

因此真实需求不是分布式 KV 的严格可序列化，而是**单节点原子多 key batch write**。redb 完全贴合这个边界：嵌入式、纯 Rust、无外部 daemon、部署时每 shard 一个 `.redb` 文件。故障面小，CI 与本地开发一致。

---

## 5. 实时推送: NATS

### 备选

| 方案 | 模式 | 优势 | 劣势 |
|------|------|------|------|
| NATS | Pub/Sub + Queue Group | 极轻量（单二进制 ~20MB）；内建集群；request-reply + queue-group 天然匹配 sandbox 分发 | 无持久化队列（不需要） |
| Kafka | 日志 | 最成熟的持久化队列 | 运维重（ZooKeeper/KRaft）；对 tick 推送是杀鸡用牛刀 |
| Redis Pub/Sub | Pub/Sub | 简单 | 无持久化；断线丢消息；无 request-reply 原语 |
| gRPC streaming | 双向流 | 无额外 daemon | 需自建 worker coordinator 做负载均衡（等于重写 NATS queue-group） |
| ZeroMQ | 多模式 | 无 daemon（库内嵌） | 需自建集群和负载均衡 |

### 选择: NATS

NATS 是唯一的额外基础设施组件（非 Rust）。两个职责：(1) tick delta broadcast——Engine → Gateway → WebSocket；(2) sandbox dispatch——Engine 通过 queue-group 把 COLLECT 分发到共享 WASM pool。

NATS queue-group 是唯一不需要独立 coordinator 就能做到"多个 producer（Engine per shard）、多个 consumer（worker）、自动负载均衡、超时就当空指令"的方案。gRPC/ZMQ 需要自己写 dispatcher。

部署为 NATS cluster——每节点一个实例，单节点部署即为单节点 cluster。

---

## 6. 读缓存: Engine 进程内 Moka Cache

**Dragonfly 已被移除**——进程内缓存覆盖所有读加速场景。

| 原组件 | 替代方案 |
|--------|---------|
| Dragonfly（Redis 兼容缓存） | Engine 进程内 `moka::sync::Cache` |

理由：单 shard Engine 是进程内单 writer，500 玩家的读请求走本地内存比走 Redis 协议快一个数量级。零网络延迟、零额外 daemon、零运维。MCP 查询和 WebSocket 初始状态全部从进程内缓存返回。Gateway 通过 gRPC/NATS 请求 Engine 的查询 endpoint。

---

## 7. 分析: redb Metrics Table + Gateway 聚合

**ClickHouse 已被移除**——per-shard 数据量不需要列式存储。

| 原组件 | 替代方案 |
|--------|---------|
| ClickHouse（列式 OLAP） | redb metrics table（per-shard）+ Gateway 跨 shard 聚合 |

每 shard ~4KB/tick × 86,400 tick/天 = ~350MB/天。redb 轻松处理。跨 shard 聚合查询由 Gateway fan-out 到各 Engine 的 metrics endpoint，Gateway 内存中聚合后返回。

---

## 8. 哈希 / PRNG / 代码签名: Blake3（单原语）+ Ed25519

### 选择: Blake3 覆盖哈希和 PRNG；代码签名使用 Ed25519

Blake3 覆盖哈希和 PRNG 后：(1) 依赖栈减少一个 crate（ChaCha）；(2) 审计面减半；(3) 纯软件 ~6 GB/s，无平台退化；(4) seed+offset XOF 模式天然适配 per-player per-tick 的确定性随机序列。

证书使用 Ed25519——单层 Server CA，签名小（64B），纯 Rust `ed25519-dalek` 成熟。用途隔离：`ClientAuthCertificate` + `CodeSigningCertificate` 两种证书类型。

---

## 9. SDK: IDL Codegen → TS + Rust + Go + C/C++

### 备选

| 方案 | 类型 | 优势 | 劣势 |
|------|------|------|------|
| TypeScript | AI 玩家第一语言 | AI agent 生态（MCP SDK、LLM 工具链）；Web 同构 | 性能上限 |
| Rust | 人类硬核玩家 | 性能顶尖；类型安全 | 上手门槛高 |
| Go | 后端开发者 | 简单；TinyGo → WASM | GC 开销 |
| C/C++ | 底层/游戏开发 | 最成熟的 WASM 编译路径 | 手动内存管理 |
| Python | 科研/AI | 最多 AI 开发者会用 | Python 运行时编译到 WASM 太重 |

### 选择: IDL codegen 驱动，初始四种语言

`game_api.idl` 是单一事实源 → codegen 生成所有语言的类型定义 + host function 绑定。新增语言 = 新增 codegen 模板。初始四种：TS + Rust + Go + C/C++。

---

## 10. Web UI: Monaco + PixiJS

| 方案 | 优势 | 劣势 |
|------|------|------|
| Monaco | VS Code 内核；TypeScript 原生支持 | 相对重 (~5MB) |
| CodeMirror 6 | 更轻；模块化 | TypeScript 支持不如 Monaco |
| PixiJS | 最快的 2D WebGL；tilemap 原生 | WebGPU 还在迁移 |

### 选择: Monaco + PixiJS

前端保留 TypeScript。Monaco 的 TypeScript 智能提示直接对接 SDK 类型——玩家写 `drone.` 弹出 `harvest/move/transfer`。PixiJS 的 tilemap 渲染 `MAX_QUERY_RANGE` 内的可见实体，WebGL 加速下 500 drone 不卡。

---

## 11. 已移除的组件

| 组件 | 移除理由 |
|------|---------|
| Dragonfly | 进程内 Moka cache 覆盖读加速，零网络延迟，零运维 |
| ClickHouse | 每 shard ~350MB/天数据量，redb metrics table 足够；跨 shard 聚合由 Gateway fan-out |
| Rhai | Bevy Plugin trait 是唯一扩展机制；两套扩展系统 = 不必要的复杂度 |
| 双层 CA（Root + Intermediate） | 单服务器部署无安全收益；单层 Server CA 足够 |
| passkey/admin 恢复（强制） | 砍掉强制恢复路径；email 恢复为可选模块 |
| 不安全传输（核心需求） | 默认要求 TLS；不安全传输为可选配置 |
