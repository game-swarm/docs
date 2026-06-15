1|# WASM 沙箱基线
2|
3|> **状态**: 当前 | **日期**: 2026-06-14
4|
5|> **状态**: 当前
6|
7|## 1. 架构
8|
9|```
10|┌──────────────────────────────────────────┐
11|│  引擎进程                                 │
12|│  ┌────────────────────────────────────┐  │
13|│  │  Tick 调度器                        │  │
14|│  │  "执行玩家 42, tick 4521"           │  │
15|│  └──────────────┬─────────────────────┘  │
16|│                 │ gRPC (Unix socket)      │
17|└─────────────────┼────────────────────────┘
18|                  │
19|                  ▼
20|┌──────────────────────────────────────────┐
21|│  Sandbox Worker 进程（每玩家）              │
22|│  ┌────────────────────────────────────┐  │
23|│  │  OS 隔离:                           │  │
24|│  │  seccomp(bpf) — 白名单系统调用       │  │
25|│  │  cgroup v2 — 内存/CPU/pid 上限       │  │
26|│  │  无网络命名空间                      │  │
27|│  │  只读根文件系统                      │  │
28|│  │  独立 /tmp (tmpfs, 16MB)            │  │
29|│  └────────────────────────────────────┘  │
30|│  ┌────────────────────────────────────┐  │
31|│  │  Wasmtime 引擎                      │  │
32|│  │  ┌──────────────────────────────┐  │  │
33|│  │  │  WASM 模块实例                │  │  │
34|│  │  │  - fuel: 10M 指令             │  │  │
35|│  │  │  - 内存: 64MB                │  │  │
36|│  │  │  - 无 WASI 文件/网络/时钟     │  │  │
37|│  │  └──────────────────────────────┘  │  │
38|│  └────────────────────────────────────┘  │
39|│  生命周期: 每 tick fork → 执行 → kill     │
40|└──────────────────────────────────────────┘
41|```
42|
43|**生命周期**: sandbox worker 进程每 tick 新 fork，执行一个玩家，返回指令，然后 kill。tick 之间无状态保留。防止跨 tick 内存泄漏、长运行进程资源累积、受感染模块持久化。
44|
45|## 2. Wasmtime 配置
46|
47|### 2.1 依赖
48|
49|```toml
50|# Cargo.toml
51|wasmtime = "=30.0"   # 锁定版本 — 不自动升级
52|```
53|
54|CVE 监控：CI 中 `cargo audit`。每次 `wasmtime` 版本升级前人工审查 CHANGELOG。
55|
56|**安全 SLA**：
57|- 严重 CVE（CVSS ≥ 9.0）：72 小时内评估 + 补丁，必要时临时降级到已知安全版本
58|- 高危 CVE（CVSS ≥ 7.0）：7 天内修复
59|- 每季度审查 Wasmtime 安全公告，评估是否需要版本迁移
60|- `=30.0` 版本的安全支持窗口：跟踪 Bytecode Alliance 的 LTS/non-LTS 发布策略，锁定版本需在官方安全支持窗口内
61|
62|### 2.2 引擎配置
63|
64|```rust
65|let mut config = wasmtime::Config::new();
66|
67|// === 燃料计量 ===
68|config.consume_fuel(true);                    // 启用燃料计量
69|config.fuel_consumed_callback(|fuel| {        // 检查点回调
70|    if fuel > MAX_FUEL { panic!("fuel exhausted"); }
71|});
72|
73|// === 内存限制 ===
74|config.static_memory_maximum_size(64 * 1024 * 1024);  // 64MB
75|config.dynamic_memory_reserved_for_growth(0);          // 不允许动态增长
76|config.memory_guard_size(2 * 1024 * 1024);             // 2MB 保护页
77|config.guard_before_linear_memory(true);                // 前后均设保护
78|
79|// === 表限制 ===
80|config.table_elements_max(10_000);
81|
82|// === 栈限制 ===
83|config.max_wasm_stack(1 * 1024 * 1024);       // 1MB
84|
85|// === 实例限制 ===
86|config.max_instances(1);
87|config.max_wasm_memory_pages(1024);            // 64MB / 64KB pages
88|
89|// === 编译器 ===
90|config.cranelift_opt_level(wasmtime::OptLevel::Speed);  // 生产: Speed
91|                                                        // 调试: SpeedAndSize
92|
93|// === 线程 ===
94|config.wasm_threads(false);                    // 禁用多线程
95|config.wasm_simd(true);                        // 允许 SIMD（性能）
96|config.wasm_relaxed_simd(false);               // 不允许 relaxed SIMD
97|
98|// === Epoch 中断 ===
99|config.epoch_interruption(true);               // 超时即杀
100|```
101|
102|### 2.3 WASI 配置
103|
104|白名单模式 — 仅允许以下 WASI 函数：
105|
106|```rust
107|// 引擎 host function（非 WASI）: 见 §4
108|
109|// WASI: 默认全禁
110|let mut wasi = wasmtime_wasi::WasiCtxBuilder::new();
111|// 无 args、无 env、无预开目录、无 stdin/stdout/stderr
112|// 自动屏蔽: fd_read, fd_write, path_open, clock_time_get, random_get,
113|//             sock_accept, environ_get, args_get, proc_exit
114|
115|// 明确禁止:
116|// ❌ wasi:cli/*        — 无文件系统
117|// ❌ wasi:clocks/*     — 无时钟（防止时序攻击）
118|// ❌ wasi:random/*     — 无随机数（用 host function 提供的种子 PRNG）
119|// ❌ wasi:sockets/*    — 无网络
120|// ❌ wasi:http/*       — 无 HTTP
121|```
122|
123|### 2.4 模块校验（执行前）
124|
125|```rust
126|fn validate_module(wasm_bytes: &[u8]) -> Result<(), Rejection> {
127|    // 1. 体积检查
128|    if wasm_bytes.len() > 5 * 1024 * 1024 {
129|        return Err(Rejection::ModuleTooLarge);  // 最大 5MB
130|    }
131|
132|    // 2. 使用 wasmparser 预校验 WASM 二进制（在 wasmtime 之外）
133|    let parser = wasmparser::Parser::new(0);
134|    for payload in parser.parse_all(wasm_bytes) {
135|        match payload? {
136|            // 3. 显式拒绝 StartSection（实例化时自动执行，绕过 tick）
137|            wasmparser::Payload::StartSection { .. } => {
138|                return Err(Rejection::StartSectionForbidden);
139|            }
140|            _ => {}
141|        }
142|    }
143|
144|    // 4. 编译模块（在 wasmparser 预检通过后）
145|    let module = wasmtime::Module::from_binary(&engine, wasm_bytes)?;
146|
147|    // 5. 检查导出: 必须导出 "tick", "alloc", "free"
148|    for &name in &["tick", "alloc", "free"] {
149|        module.get_export(name)
150|            .ok_or(Rejection::MissingExport(name))?;
151|    }
152|
153|    // 6. 检查导入: 仅允许白名单 host function
154|    for import in module.imports() {
155|        if !ALLOWED_HOST_FUNCTIONS.contains(import.name()) {
156|            return Err(Rejection::IllegalImport(import.name()));
157|        }
158|    }
159|
160|    // 7. 实例化前必须设置: Store fuel、epoch deadline、memory limiter
161|    //    这些在 Instance::new() 调用前生效，确保 start section 的替代品
162|    //    （如 active element/data segments）也在约束内执行
163|
164|    Ok(())
165|}
166|```
167|
168|## 3. Deferred Command Model — 延迟指令模型
169|
170|WASM 模块采用 **deferred model**：`tick()` 接收快照 JSON，**返回指令 JSON**。引擎在校验后执行指令。WASM 中**不得直接调用 mutating host function**——所有状态变更必须通过指令 JSON 返回，由引擎统一应用。
171|
172|### 3.1 模块导出 (ABI)
173|
174|WASM 模块必须导出以下三个函数：
175|
176|```rust
177|// 内存管理（供引擎调用）
178|alloc(len: i32) -> i32;           // 分配 len 字节 WASM 线性内存，返回指针
179|free(ptr: i32, len: i32);         // 释放之前 alloc 的内存
180|
181|// 主入口
182|tick(snapshot_ptr: i32, snapshot_len: i32, result_ptr: i32) -> i32;
183|//   snapshot_ptr/len: 引擎写入的快照 JSON 在 WASM 内存中的位置
184|//   result_ptr: 指向引擎分配的 8 字节 out struct { ptr: u32, len: u32 }
185|//   返回值: 0 = 成功, 负数 = 错误码
186|//
187|//   调用协议:
188|//   1. 引擎 alloc snapshot_len → 写入快照 JSON
189|//   2. 引擎 alloc 8 bytes → 作为 result_ptr
190|//   3. 调用 tick(snapshot_ptr, snapshot_len, result_ptr)
191|//   4. 读取 result_ptr 处的 {ptr, len}
192|//   5. 校验 len <= 256KB → 从 ptr 复制出 CommandIntent JSON
193|//   6. 调用 free(ptr, len) 释放 WASM 侧分配的返回 buffer
194|//   7. 调用 free(snapshot_ptr, snapshot_len) 释放快照 buffer
195|```
196|
197|**安全约束**:
198|- 所有 pointer/len 做 bounds check、alignment check、integer overflow check
199|- CommandIntent JSON 超过 256KB → 拒绝该玩家当 tick 所有输出
200|- tick() 返回非 0 → 视为执行失败，当 tick 0 指令
201|- 不存在的 export → 模块无效，拒绝部署
202|
203|### 3.2 允许的 Host Function（查询专用，只读）
204|
205|WASM 中**仅可调用查询类 host function**——所有函数只读，不计入指令预算但计入 fuel 预算。**所有 host function 的返回结果均经 `is_visible_to` 过滤**——与 snapshot 使用同一可见性函数，无绕过路径：
206|
207|```rust
208|// 信息查询（只读，不改变世界状态，返回结果经可见性过滤）
209|fn host_get_terrain(x: i32, y: i32) -> i32;                           // 地形公开，无需过滤
210|fn host_get_objects_in_range(x: i32, y: i32, range: i32, out_ptr: i32, out_len: i32) -> i32;  // ← 仅返回 is_visible_to(caller) 为 true 的实体
211|fn host_path_find(from_x: i32, from_y: i32, to_x: i32, to_y: i32, out_ptr: i32, out_len: i32) -> i32;  // ← 仅基于可见地形计算路径
212|
213|// 世界配置查询
214|fn host_get_world_config(key_ptr: i32, key_len: i32, out_ptr: i32, out_len: i32) -> i32;
215|fn host_get_world_rules(out_ptr: i32, out_len: i32) -> i32;               // 查询世界规则（只读）
216|```
217|
218|全部返回 `i32`：0 = 成功，负数 = 错误码。
219|`out_ptr`/`out_len`：WASM 分配缓冲区，host 写入结果后再次校验边界。
220|
221|### 3.3 禁止的 Host Function
222|
223|以下函数**不得作为 host function 暴露给 WASM**：
224|
225|- ❌ `host_move` — 改为 `{ "cmd": "move", ... }` JSON 指令
226|- ❌ `host_harvest` — 改为 `{ "cmd": "harvest", ... }` JSON 指令
227|- ❌ `host_transfer` — 改为 `{ "cmd": "transfer", ... }` JSON 指令
228|- ❌ `host_build` — 改为 `{ "cmd": "build", ... }` JSON 指令
229|- ❌ `host_attack` — 改为 `{ "cmd": "attack", ... }` JSON 指令
230|- ❌ `host_heal` — 改为 `{ "cmd": "heal", ... }` JSON 指令
231|
232|所有游戏动作必须通过 `tick() → JSON` 延迟模型提交，引擎在校验后统一应用。
233|
234|## 4. OS 隔离
235|
236|### 4.1 seccomp（系统调用过滤）
237|
238|仅允许 Wasmtime 运行所需的最小系统调用：
239|
240|```c
241|// 允许
242|read, write, mmap, mprotect, munmap,
243|brk, madvise, membarrier,
244|futex, nanosleep,
245|sigaltstack, rt_sigaction, rt_sigreturn,
246|clone (仅 CLONE_VM | CLONE_VFORK), exit, exit_group
247|
248|// 全禁
249|// ❌ open, openat, stat, unlink, mkdir, chmod
250|// ❌ socket, connect, bind, listen, accept
251|// ❌ fork, execve
252|// ❌ clock_gettime
253|// ❌ getrandom
254|```
255|
256|### 4.2 cgroup v2
257|
258|```
259|memory.max = 128MB          // 2x Wasmtime 内存，覆盖运行时开销
260|memory.swap.max = 0          // 禁用 swap
261|cpu.max = 250000 3000000     // 每 3s tick 周期限 0.25 CPU 秒
262|pids.max = 32                // 最多 32 线程（Wasmtime + 编译器）
263|```
264|
265|### 4.3 网络命名空间
266|
267|sandbox 进程无网络命名空间。与引擎通过 Unix domain socket 通信（fd 在 seccomp 锁定前传入）。
268|
269|## 5. 恶意 WASM 样本库
270|
271|### 5.1 测试类别
272|
273|| 类别 | 示例 |
274||------|------|
275|| **资源耗尽** | 死循环、100MB 分配、1 万层函数调用 |
276|| **内存破坏** | 越界访问、栈 use-after-free |
277|| **WASI 逃逸** | 尝试 `fd_write`、`clock_time_get`、`random_get` |
278|| **Host 滥用** | 调 `host_path_find` 1 万次，传入超长 out_ptr |
279|| **栈溢出** | 深层递归、1 万层嵌套调用 |
280|| **类型混淆** | i64→f64 重解释转换、NaN boxing |
281|| **Start 函数** | 模块含 `_start()` 在 `tick()` 之前执行 |
282|| **导入滥用** | 导入不存在的 host function |
283|
284|### 5.2 CI 集成
285|
286|```bash
287|cargo test --test wasm_sandbox -- --test-threads=1
288|# 每个测试:
289|# 1. 编译恶意 WASM
290|# 2. 加载到 sandbox worker
291|# 3. 断言: 被拒绝（未加载）或 超时（被杀）或 OOM（被杀）
292|# 4. 断言: 引擎进程仍运行（未崩溃）
293|```
294|
295|## 6. 资源预算总表
296|
297|| 资源 | 限制 | 执行点 |
298||------|------|--------|
299|| Fuel（CPU 指令） | 10,000,000 | Wasmtime fuel metering |
300|| 内存（WASM 线性） | 64 MB | Wasmtime config |
301|| 内存（总进程） | 128 MB | cgroup memory.max |
302|| 执行时间（墙钟） | 2500 ms | Epoch interruption |
303|| WASM 模块体积 | 5 MB | 预校验 |
304|| Host function 调用 | 1000/tick | 计数 |
305|| path_find 调用 | 10/tick | 计数 |
306|| get_objects_in_range 调用 | 5/tick | 计数 |
307|| 输出 JSON 体积 | 256 KB | 返回值大小检查 |
308|
309|## 7. 编译时预算
310|
311|| 资源 | 限制 | 执行点 |
312||------|------|--------|
313|| 编译超时 | 30s | 独立超时进程 |
314|| 编译内存 | 512 MB | cgroup |
315|| 编译进程 | 每次部署独立 fork | 不缓存编译中间产物 |
316|| 模块缓存 | 按 (module_hash, wasmtime_version) 缓存 | 每次 tick 执行前校验 player 的证书未过期未吊销——过期/吊销立即终止 WASM 执行（该 tick 0 指令）。缓存条目随撤销清除 |
317|| 并发编译 | 最多 5 个 | 防止编译阶段 DoS |
318|| module validation | 10ms | wasmparser 解析超时 |
319|
320|## 8. Query Host Function 单次调用成本表
321|
322|以下仅列出 §3.2 允许的**查询类 host function**。Mutating 操作的 cost 定义在 specs/08- IDL 各 command 的 `cost` 字段中。
323|
324|| 函数 | fuel 成本 | 响应大小上限 |
325||------|----------|------------|
326|| `host_get_terrain` | 500 | 4 bytes |
327|| `host_get_objects_in_range` | 2,000 + 100/entity | 64 KB |
328|| `host_path_find` | 10,000 + 50/tile | 8 KB | **缓存键**: `(from, to, terrain_hash, player_visibility_fingerprint)` — 不同玩家的可见性状态产生不同缓存条目，防止跨玩家路径泄露 |
329|| `host_get_world_config` | 1,000 | 16 KB |
330|| `host_get_world_rules` | 1,000 | 16 KB |
331|