# WASM 沙箱基线

> 详见 design/interface.md

## 1. 架构

```
┌──────────────────────────────────────────┐
│  引擎进程                                 │
│  ┌────────────────────────────────────┐  │
│  │  Tick 调度器                        │  │
│  │  "执行玩家 42, tick 4521"           │  │
│  └──────────────┬─────────────────────┘  │
│                 │ gRPC (Unix socket)      │
└─────────────────┼────────────────────────┘
                  │
                  ▼
┌──────────────────────────────────────────┐
│  Sandbox Worker 进程（每玩家）              │
│  ┌────────────────────────────────────┐  │
│  │  OS 隔离:                           │  │
│  │  seccomp(bpf) — 白名单系统调用       │  │
│  │  cgroup v2 — 内存/CPU/pid 上限       │  │
│  │  无网络命名空间                      │  │
│  │  只读根文件系统                      │  │
│  │  独立 /tmp (tmpfs, 16MB)            │  │
│  └────────────────────────────────────┘  │
│  ┌────────────────────────────────────┐  │
│  │  Wasmtime 引擎                      │  │
│  │  ┌──────────────────────────────┐  │  │
│  │  │  WASM 模块实例                │  │  │
│  │  │  - fuel: 10M 指令             │  │  │
│  │  │  - 内存: 64MB                │  │  │
│  │  │  - 无 WASI 文件/网络/时钟     │  │  │
│  │  └──────────────────────────────┘  │  │
│  └────────────────────────────────────┘  │
│  生命周期: worker pool + per-tick Store reset     │
└──────────────────────────────────────────┘
```

**生命周期**: Sandbox 采用 **long-lived worker pool** 模型。WASM 模块在部署时预编译并缓存——`Blake3(module_hash || wasmtime_build_commit || wasmparser_version || validation_policy_version || target_arch || security_epoch)` 作为缓存键。每 tick：worker 从池中取出 → 执行 **Store reset checklist**（以下所有步骤按序执行，任一失败 → worker 替换并审计）:

1. **清空 WASM 线性内存**：全部页归零
2. **重置 fuel counter**：`store.set_fuel(MAX_FUEL)`
3. **重建 Instance**：从预编译 Module 重新实例化（含 host function 重新绑定）
4. **epoch deadline 重置**：`store.set_epoch_deadline(1)` — 新 tick 开始
5. **验证 Store 隔离**：检查实例化的 Instance 不含上一 tick 残留引用/状态
6. **seccomp 验证**：确认 BPF filter 仍在生效（通过自检 syscall 验证返回 EPERM）
7. **cgroup 验证**：确认 memory.max、cpu.max、pids.max 未被前次执行修改

→ 执行单一玩家的 `tick()` → 返回结果 → 返回池中。

**设计理由**: fork-per-tick 的隔离性更强，但以 500 活跃玩家计算，fork + seccomp + cgroup 初始化仅进程创建就需 2.5-5s，直接超出整个 tick 预算（3s）。Worker pool 配合严格 Store reset（清空 WASM 线性内存、重置 fuel counter、epoch deadline）和 cgroup/seccomp 持久绑定，在性能与隔离间取得平衡。防止跨 tick 资源累积的机制：Store reset 清空所有 WASM 可变状态；epoch deadline 保证单次 tick 时间上限；OOM killer + memory.max 处理内存泄漏。

**统一 ABI 结果**: trap（如 unreachable）/ OOM / timeout / partial-output 均 → 丢弃该玩家当 tick 全部指令输出，记录到 TickTrace（`output_discarded` 原因码），不产生 command。下一 tick 正常重新执行。

## 2. Wasmtime 配置

### 2.1 依赖

```toml
# Cargo.toml
wasmtime = "=30.0"   # 锁定版本 — 不自动升级
```

CVE 监控：CI 中 `cargo audit`。每次 `wasmtime` 版本升级前人工审查 CHANGELOG。

**安全 SLA**（权威源 `specs/security/CVE-SLA.md`）：
- Critical（CVSS ≥ 9.0）：24h 内评估 + 补丁，必要时暂停 WASM 部署
- High（CVSS ≥ 7.0）：72h 内修复
- Medium（CVSS ≥ 4.0）：1w 内修复
- 每季度审查 Wasmtime 安全公告，评估是否需要版本迁移
- `=30.0` 版本的安全支持窗口：跟踪 Bytecode Alliance 的 LTS/non-LTS 发布策略，锁定版本需在官方安全支持窗口内

### 2.2 引擎配置

```rust
let mut config = wasmtime::Config::new();

// === 燃料计量 ===
config.consume_fuel(true);                    // 启用燃料计量
// 注意: Wasmtime ≥30 移除了 fuel_consumed_callback API；
// 燃料检查改为在 Store 层通过 get_fuel() 轮询

// === 内存限制 (Wasmtime ≥30: StoreLimitsBuilder) ===
let mut store_limits = wasmtime::StoreLimitsBuilder::new()
    .memory_size(64 * 1024 * 1024)            // 64MB
    .instances(1)
    .memories(1)
    .tables(10);
config.memory_reservation_for_growth(0);       // 不允许动态增长
config.memory_guard_size(2 * 1024 * 1024);     // 2MB 保护页
config.guard_before_linear_memory(true);        // 前后均设保护

// === 栈限制 ===
config.max_wasm_stack(1 * 1024 * 1024);       // 1MB

// === 编译器 ===
config.cranelift_opt_level(wasmtime::OptLevel::Speed);  // 生产: Speed
                                                        // 调试: SpeedAndSize

// === 线程 ===
config.wasm_threads(false);                    // 禁用多线程
config.wasm_simd(world_config.simd_enabled);       // SIMD 由 world.toml 控制：**默认禁用**，仅显式 opt-in `deterministic_subset` 时启用
config.wasm_relaxed_simd(false);                    // 不允许 relaxed SIMD（始终禁用）

// === Epoch 中断 ===
config.epoch_interruption(true);               // 超时即杀
```

### 2.3 WASI 配置

白名单模式 — 仅允许以下 WASI 函数：

```rust
// 引擎 host function（非 WASI）: 见 §4

// WASI: 默认全禁
let mut wasi = wasmtime_wasi::WasiCtxBuilder::new();
// 无 args、无 env、无预开目录、无 stdin/stdout/stderr
// 自动屏蔽: fd_read, fd_write, path_open, clock_time_get, random_get,
//             sock_accept, environ_get, args_get, proc_exit

// 明确禁止:
// ❌ wasi:cli/*        — 无文件系统
// ❌ wasi:clocks/*     — 无时钟（防止时序攻击）
// ❌ wasi:random/*     — 无随机数（用 host function 提供的种子 PRNG）
// ❌ wasi:sockets/*    — 无网络
// ❌ wasi:http/*       — 无 HTTP
```

### 2.4 模块校验（执行前）

```rust
fn validate_module(wasm_bytes: &[u8]) -> Result<(), Rejection> {
    // 1. 体积检查
    if wasm_bytes.len() > 5 * 1024 * 1024 {
        return Err(Rejection::ModuleTooLarge);  // 最大 5MB
    }

    // 2. 使用 wasmparser 预校验 WASM 二进制（在 wasmtime 之外）
    let parser = wasmparser::Parser::new(0);
    for payload in parser.parse_all(wasm_bytes) {
        match payload? {
            // 3. 显式拒绝 StartSection（实例化时自动执行，绕过 tick）
            wasmparser::Payload::StartSection { .. } => {
                return Err(Rejection::StartSectionForbidden);
            }
            _ => {}
        }
    }

    // 4. 编译模块（在 wasmparser 预检通过后）
    let module = wasmtime::Module::from_binary(&engine, wasm_bytes)?;

    // 5. 检查导出: 必须导出 "tick", "alloc", "free"
    for &name in &["tick", "alloc", "free"] {
        module.get_export(name)
            .ok_or(Rejection::MissingExport(name))?;
    }

    // 6. 检查导入: 仅允许白名单 host function
    for import in module.imports() {
        if !ALLOWED_HOST_FUNCTIONS.contains(import.name()) {
            return Err(Rejection::IllegalImport(import.name()));
        }
    }

    // 7. 实例化前必须设置: Store fuel、epoch deadline、memory limiter
    //    这些在 Instance::new() 调用前生效，确保 start section 的替代品
    //    （如 active element/data segments）也在约束内执行

    Ok(())
}
```

## 3. Deferred Command Model — 延迟指令模型

WASM 模块采用 **deferred model**：`tick()` 接收快照 JSON，**返回指令 JSON**。引擎在校验后执行指令。WASM 中**不得直接调用 mutating host function**——所有状态变更必须通过指令 JSON 返回，由引擎统一应用。

### 3.1 模块导出 (ABI)

WASM 模块必须导出以下三个函数：

```rust
// 内存管理（供引擎调用）
alloc(len: i32) -> i32;           // 分配 len 字节 WASM 线性内存，返回指针
free(ptr: i32, len: i32);         // 释放之前 alloc 的内存

// 主入口
tick(snapshot_ptr: i32, snapshot_len: i32, result_ptr: i32) -> i32;
//   snapshot_ptr/len: 引擎写入的快照 JSON 在 WASM 内存中的位置
//   result_ptr: 指向引擎分配的 8 字节 out struct { ptr: u32, len: u32 }
//   返回值: 0 = 成功, 负数 = 错误码
//
//   调用协议:
//   1. 引擎 alloc snapshot_len → 写入快照 JSON
//   2. 引擎 alloc 8 bytes → 作为 result_ptr
//   3. 调用 tick(snapshot_ptr, snapshot_len, result_ptr)
//   4. 读取 result_ptr 处的 {ptr, len}
//   5. 校验 len <= 256KB → 从 ptr 复制出 CommandIntent JSON
//   6. 调用 free(ptr, len) 释放 WASM 侧分配的返回 buffer
//   7. 调用 free(snapshot_ptr, snapshot_len) 释放快照 buffer
```

**安全约束**:
- 所有 pointer/len 做 bounds check、alignment check、integer overflow check
- CommandIntent JSON 超过 256KB → 拒绝该玩家当 tick 所有输出
- tick() 返回非 0 → 视为执行失败，当 tick 0 指令
- 不存在的 export → 模块无效，拒绝部署

### 3.2 允许的 Host Function（查询专用，只读）

WASM 中**仅可调用查询类 host function**——所有函数只读，不计入指令预算但计入 fuel 预算。**所有 host function 的返回结果均经 `is_visible_to` 过滤**——与 snapshot 使用同一可见性函数，无绕过路径：

```rust
// 信息查询（只读，不改变世界状态，返回结果经可见性过滤）
fn host_get_terrain(room_id: u32, out_ptr: i32, out_len: i32) -> i32;  // 权威签名见 api-registry.md §4.1
fn host_get_objects_in_range(x: i32, y: i32, range: u32, out_ptr: i32, out_len: i32) -> i32;  // ← 仅返回 is_visible_to(caller) 为 true 的实体
fn host_path_find(from_x: i32, from_y: i32, to_x: i32, to_y: i32, opts_ptr: i32, opts_len: i32, out_ptr: i32, out_len: i32) -> i32;  // ← 仅基于可见地形计算路径
fn host_get_random(sequence: u64, out_ptr: i32, out_len: i32) -> i32;  // ← 确定性随机字节，见下方 derive_rng 规范

// 世界配置查询
fn host_get_world_config(key_ptr: i32, key_len: i32, out_ptr: i32, out_len: i32) -> i32;
fn host_get_world_rules(rule_id_ptr: i32, rule_id_len: i32, out_ptr: i32, out_len: i32) -> i32;  // 权威签名见 api-registry.md §4.1
```

全部返回 `i32`：0 = 成功，负数 = 错误码。
`out_ptr`/`out_len`：WASM 分配缓冲区，host 写入结果后再次校验边界。

`host_get_random` 使用唯一随机派生规范：

```rust
derive_rng(domain: ascii, world_seed: [u8; 32], tick: u64, actor_or_entity_id: u64, sequence: u64) -> Blake3 XOF
```

输入编码为 length-delimited field encoding：每个字段按 `field_tag || uLEB128(byte_len) || bytes` 写入；`domain` 必须是第一个字段，`host_get_random` 固定使用 domain separator `"swarm.host_random.v1"`；`world_seed` 写入 32 bytes；`tick`、`actor_or_entity_id`、`sequence` 使用 little-endian 固定宽度整数。该编码避免拼接歧义，确保不同 domain、tick、actor/entity/source 与 `u64 sequence` 的随机流隔离，并保持 replay determinism。

### 3.3 禁止的 Host Function

以下函数**不得作为 host function 暴露给 WASM**：

- ❌ `host_move` — 改为 `{ "cmd": "move", ... }` JSON 指令
- ❌ `host_harvest` — 改为 `{ "cmd": "harvest", ... }` JSON 指令
- ❌ `host_transfer` — 改为 `{ "cmd": "transfer", ... }` JSON 指令
- ❌ `host_build` — 改为 `{ "cmd": "build", ... }` JSON 指令
- ❌ `host_attack` — 改为 `{ "cmd": "attack", ... }` JSON 指令
- ❌ `host_heal` — 改为 `{ "cmd": "heal", ... }` JSON 指令

所有游戏动作必须通过 `tick() → JSON` 延迟模型提交，引擎在校验后统一应用。

## 4. OS 隔离

### 4.1 seccomp（系统调用过滤）

仅允许 Wasmtime 运行所需的最小系统调用：

```c
// 允许
read, write, mmap, mprotect, munmap,
brk, madvise, membarrier,
futex, nanosleep,
sigaltstack, rt_sigaction, rt_sigreturn,
clone (仅 CLONE_VM | CLONE_VFORK), exit, exit_group

// 全禁
// ❌ open, openat, stat, unlink, mkdir, chmod
// ❌ socket, connect, bind, listen, accept
// ❌ fork, execve
// ❌ clock_gettime
// ❌ getrandom
```

### 4.2 cgroup v2

```
memory.max = 128MB          // 2x Wasmtime 内存，覆盖运行时开销
memory.swap.max = 0          // 禁用 swap
cpu.max = 250000 3000000     // 每 3s tick 周期限 0.25 CPU 秒
pids.max = 16                // 最多 16 线程（Wasmtime + 编译器）
```

### 4.3 网络命名空间（R33 B8）

sandbox 进程拥有**独立 netns**，无网络接口、无路由表、无 iptables 规则。与引擎通过 Unix domain socket 通信（fd 在 seccomp 锁定前传入）。

**网络隔离层（双层）**：
| 层 | 机制 | 效果 |
|----|------|------|
| **L1: netns** | 独立网络命名空间，`ip link set lo down`，无任何物理/虚拟网卡 | 进程内任何 socket() 调用返回 EAFNOSUPPORT |
| **L2: seccomp** | BPF filter 拒绝所有 socket 相关 syscall（socket/connect/bind/listen/accept/sendmsg/recvmsg） | 系统调用层阻断，防止 netns 逃逸或配置错误 |

**验证命令**：`ip netns exec <sandbox_ns> ip link show` → 仅 lo（DOWN）；`ip netns exec <sandbox_ns> ip route show` → 空。

## 5. 恶意 WASM 样本库

### 5.1 测试类别

| 类别 | 示例 |
|------|------|
| **资源耗尽** | 死循环、100MB 分配、1 万层函数调用 |
| **内存破坏** | 越界访问、栈 use-after-free |
| **WASI 逃逸** | 尝试 `fd_write`、`clock_time_get`、`random_get` |
| **Host 滥用** | 调 `host_path_find` 1 万次，传入超长 out_ptr |
| **栈溢出** | 深层递归、1 万层嵌套调用 |
| **类型混淆** | i64→f64 重解释转换、NaN boxing |
| **Start 函数** | 模块含 `_start()` 在 `tick()` 之前执行 |
| **导入滥用** | 导入不存在的 host function |

### 5.2 CI 集成

```bash
cargo test --test wasm_sandbox -- --test-threads=1
# 每个测试:
# 1. 编译恶意 WASM
# 2. 加载到 sandbox worker
# 3. 断言: 被拒绝（未加载）或 超时（被杀）或 OOM（被杀）
# 4. 断言: 引擎进程仍运行（未崩溃）
```

## 6. 资源预算总表

| 资源 | 限制 | 执行点 |
|------|------|--------|
| Fuel（CPU 指令） | 10,000,000 | Wasmtime fuel metering |
| 内存（WASM 线性） | 64 MB | Wasmtime config |
| 内存（总进程） | 128 MB | cgroup memory.max |
| 执行时间（墙钟） | 2500 ms | Epoch interruption |
| WASM 模块体积 | 5 MB | 预校验 |
| Host function 调用 | 1000/tick | 计数 |
| path_find 调用 | 10/tick | 计数；全局预算 100,000 explored nodes/tick，per-player fair-share 分配（见 engine.md §3.4.2） |
| get_objects_in_range 调用 | 5/tick | 计数 |
| host_get_random 调用 | 10/tick | 计数 |
| 输出 JSON 体积 | 256 KB | 返回值大小检查 |

### 6.1 MCP Simulate/Dry-Run 限制

MCP 在线模拟（`swarm_simulate`）使用 snapshot 副本执行——不修改真实世界状态，但消耗引擎计算资源。以下硬限制防止 DoS：

| 参数 | 限制 | 说明 |
|------|------|------|
| `max_ticks` | 100 | 每次模拟最多 100 tick |
| `max_entities` | 1000 | 模拟世界最多 1000 个实体 |
| `max_output_bytes` | 1 MB | 模拟结果最大输出 |
| `max_cpu_ms` | 5000 | 每次模拟最多 5 秒 CPU 时间 |
| `max_fuel_per_hour` | 50,000,000 | 每玩家每小时模拟总 fuel 配额 |
| `concurrent_simulates` | 3 | 每玩家最多并行 3 个模拟（排队的拒绝） |

超限 → 返回错误码 + 审计日志。长模拟（>100 tick）必须使用本地 CLI 离线模拟或异步隔离 worker。

### 6.2 Audit / TickTrace 字段限制

TickTrace 中存储的审计日志受以下大小限制，防止磁盘 DoS：

| 字段 | 限制 | 超限处理 |
|------|------|---------|
| RawCommand body | 1 KB（hash + truncated preview） | 完整 body 丢弃，保留 `command_hash` + 前 200 字符 |
| Rejection detail | 512 bytes | 截断至 500 字符 + `…truncated` |
| Snapshot metadata | 4 KB per player | 仅存 entity count + truncation markers |
| Untrusted string（player name, room name 等） | 256 字符 | 超出截断，记录原始 hash |

所有 untrusted string 在写入 TickTrace 前经过 escaping（防 JSON 注入 + 日志注入），并在长度上限处截断。

## 7. 编译时预算


### 7.1 Wasmtime Pre-Warm Strategy

> **R34 ML-6**: 部署延迟和首 tick 冷启动惩罚需要 pre-warm 机制降低 P99 延迟。

**双版本并行**：
- 当前活跃版本（`active_module`）服务所有 tick 请求
- 预编译版本（`prewarm_module`）在后台异步编译，不与 active 版本竞争 tick 预算
- 预编译版本就绪后原子切换：`active_module ← prewarm_module`

**后台预编译触发**：
1. 新 WASM 部署成功（`swarm_deploy` 完成 FDB commit + object store upload）
2. 后台编译 worker 收到通知 → 独立 Wasmtime Engine 实例编译模块
3. 编译期间 active 版本不受影响（独立 Engine，独立 cgroup limits）
4. 编译完成 → 模块 hash 写入 `prewarm_registry`（FDB `sandbox/prewarm/<player_id>/<module_hash>`）

**原子切换**：
- 下一 tick COLLECT 开始前：检查 `prewarm_registry` 是否有匹配当前部署 hash 的预编译模块
- 有 → `active_module` 替换为预编译版本（原子指针 swap）
- 无 → 使用当前 active 版本（无惩罚）
- 切换不中断当前 tick，仅影响下一次 COLLECT

**覆盖率阈值**：
- 编译 worker pool 最大 5 并发（见 §7 编译时预算 `并发编译` 限制）
- 若 `prewarm_cache_hit_rate` < 80%（连续 10 次部署），扩展到 8 worker
- 若 `prewarm_cache_hit_rate` > 95%（连续 100 tick），缩回 5 worker
- Pre-warm 编译失败不影响 active 版本——记录 `prewarm_compile_failed` 审计日志

**Rollback Window**：
- 预编译模块保留最近 3 个版本（按 `fdb_version_counter` 降序）
- 第 4 个及更早版本由 GC 清理（每 1h 扫描）
- 紧急回滚时：Admin `swarm_admin_rollback` 可指定 target `fdb_version_counter`，引擎自动切换到对应预编译版本（若缓存中）

**Pre-warm 编译预算**：
| 资源 | 限制 | 说明 |
|------|------|------|
| 编译超时 | 30s（同部署编译） | 独立超时进程 |
| 编译内存 | 512 MB（同部署编译） | 独立 cgroup |
| 并发编译 worker | 5（可扩展至 8） | 防止后台编译影响 tick 执行 |
| 预编译缓存 | 3 版本/玩家 | 超出由 GC 清理 |

| 资源 | 限制 | 执行点 |
|------|------|--------|
| 编译超时 | 30s | 独立超时进程 |
| 编译内存 | 512 MB | cgroup |
| 编译进程 | 每次部署独立 fork | 不缓存编译中间产物 |
| 模块缓存 | 按 `Blake3(module_hash || wasmtime_build_commit || wasmparser_version || validation_policy_version || target_arch || security_epoch)` 缓存 | 部署提交时验证 `CodeSigningCertificate` 未过期未吊销；部署成功后证书自然过期不终止 WASM 执行。证书吊销按 revocation reason 冻结/回滚/继续允许既有模块。security_epoch 或 validation policy 变更 → 全量失效。编译仅跳过，验证不跳过。 |
| 并发编译 | 最多 5 个 | 防止编译阶段 DoS |
| module validation | 10ms | wasmparser 解析超时 |

## 8. Query Host Function 单次调用成本表

以下仅列出 §3.2 允许的**查询类 host function**。Mutating 操作的 cost 定义在 specs/gameplay/08-api-idl 各 command 的 `cost` 字段中。

| 函数 | fuel 成本 | 响应大小上限 | 说明 |
|------|----------|------------|------|
| `host_get_terrain` | 500 | 8 KB | |
| `host_get_objects_in_range` | 2,000 + 100/entity | 64 KB | |
| `host_path_find` | 500 × explored_nodes + 200 × expanded_edges + cache_miss_penalty | 8 KB | **成本按实际工作量**：explored_nodes（A* 展开的节点数）、expanded_edges（评估的邻居数）、cache_miss_penalty = **固定 2000 fuel**（与硬件无关，保证跨节点确定性结算）。不可达目标消耗更高（无路径可剪枝）。per-player/per-tick 上限：10 次调用 + 100,000 explored_nodes 总额度。超限 deterministic fail。**缓存键**: `(from, to, terrain_hash, player_visibility_fingerprint)` |
| `host_get_world_config` | 1,000 | 16 KB | |
| `host_get_world_rules` | 1,000 | 16 KB | |
| `host_get_random` | 100 + 1/output byte | 256 bytes | 确定性随机；seed=(tick_seed, player_id, drone_id, sequence)；per_tick_limit=10 |

---

## 9. Sandbox OS 边界加固 Checklist（统一表）

每个 WASM sandbox worker 进程必须在以下 OS 边界受约束。以下单表为部署前必须逐项验证的完整 checklist。

### 9.1 统一 OS 加固表

| 维度 | 约束项 | 限制 | 验证命令 | 理由 |
|------|--------|------|---------|------|
| **seccomp** | `read` | ✅ 允许 | — | WASM 线性内存读写所需 |
| | `write` | ✅ 允许 | — | 输出指令 JSON |
| | `mmap` | ✅ 允许 | — | Wasmtime 内存管理 |
| | `mprotect` | ✅ 允许 | — | Wasmtime JIT 代码页执行权限 |
| | `madvise` | ✅ 允许 | — | 内存优化提示 |
| | `futex` | ✅ 允许 | — | Wasmtime 内部同步 |
| | `sigaltstack` | ✅ 允许 | — | Wasmtime 信号处理 |
| | `clock_gettime` | ❌ 禁止 | seccomp BPF 检查 | 确定性要求（时间由引擎提供） |
| | `getrandom` | ❌ 禁止 | seccomp BPF 检查 | 随机数由 host function 提供 |
| | `open/openat` | ❌ 禁止 | seccomp BPF 检查 | 无文件系统访问 |
| | `socket/connect/sendmsg/recvmsg` | ❌ 禁止 | seccomp BPF 检查 | 无网络访问 |
| | `clone (仅 CLONE_VM \| CLONE_VFORK)` | ✅ 允许 | seccomp BPF 检查 | Wasmtime 内部线程创建所需；`fork/vfork` ❌ 禁止 |
| | `execve` | ❌ 禁止 | seccomp BPF 检查 | 无程序执行 |
| | `ptrace` | ❌ 禁止 | seccomp BPF 检查 | 无调试 |
| | `kill/tkill` | ❌ 禁止 | seccomp BPF 检查 | 无信号发送 |
| | `mount/umount` | ❌ 禁止 | seccomp BPF 检查 | 无文件系统操作 |
| **cgroup** | `memory.max` | 128 MB | `cgget -r memory.max /swarm-sandbox` | 防止 OOM 扩散 |
| | `cpu.max` | `250000 3000000`（每 3s 周期 0.25s） | `cgget -r cpu.max /swarm-sandbox` | 限制 CPU 使用 |
| | `pids.max` | 16 | `cgget -r pids.max /swarm-sandbox` | 防止进程爆炸 |
| | `io.max` | `8:0 rbps=1048576 wbps=0`（仅 1MB/s 读，禁止写） | `cgget -r io.max /swarm-sandbox` | 限制磁盘 I/O |
| **namespace** | `pid` | 独立 PID 空间 | `lsns -t pid` | sandbox 看不到宿主进程 |
| | `net` | 独立网络栈 | `ip netns list` | 无网络接口 |
| | `mnt` | 独立挂载点 | `findmnt` | `/proc` 只读绑定 |
| | `ipc` | 独立 IPC | `lsns -t ipc` | 无共享内存/Semaphore |
| | `uts` | 独立 hostname | `lsns -t uts` | 无宿主信息泄露 |

### 9.2 CI 验证

```bash
# 每个 sandbox 部署前 CI 运行：
cargo test --test sandbox_boundary -- --test-threads=1
# 验证:
# 1. 禁止的系统调用返回 EPERM（非 ENOSYS——避免 fallback）
# 2. 内存超限 → OOM killed（非 hang）
# 3. CPU 超限 → 进程被 throttled（非 infinite loop）
# 4. PID 命名空间内 fork → 失败（EPERM）
# 5. 网络命名空间内 socket → 失败（EAFNOSUPPORT）
```

### 9.3 加固例外

以下场景允许放宽某些限制——仅限 `world.toml` 中显式声明 `sandbox.relaxed = true` 的开发/调试世界：

| 放宽项 | 默认 | relaxed 模式 | 风险 |
|--------|:--:|:--:|------|
| `clock_gettime` | 禁止 | 允许（确定性种子） | 无——引擎仍覆盖返回值 |
| `stderr` 输出 | 禁止 | 允许（仅 1KB/tick） | sandbox 日志泄露（仅 dev） |
| 内存上限 | 128 MB | 256 MB | 资源消耗 |

生产环境 **禁止** `sandbox.relaxed = true`。引擎启动时检查配置，若为 true 且 `world.mode != "development"` → 拒绝启动。
