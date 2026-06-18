# R16 Security Review — DeepSeek V4 Pro

> **评审员**: rev-dsv4-security (DeepSeek V4 Pro)  
> **方向**: Security  
> **类型**: Clean-Slate Phase 1 独立评审  
> **审阅文件**: design/README.md, design/auth.md, specs/reference/api-registry.md, specs/security/03-mcp-security.md, specs/security/05-visibility.md, specs/security/09-command-source.md, specs/security/CVE-SLA.md, specs/core/04-wasm-sandbox.md, specs/core/05-persistence-contract.md  
> **日期**: 2026-06-18  

---

## Verdict: CONDITIONAL_APPROVE

设计从安全角度整体扎实——应用层证书模型、Deferred Command Model、Oracle 防线闭合、OS 级沙箱隔离均有良好覆盖。发现 **2 个 Critical**（文档矛盾 + CRL 吊销窗口）、**4 个 High**、**4 个 Medium**、**3 个 Low**。所有问题均可通过文档修正 + 配置调整修复，不涉及架构推翻。

---

## Critical

### C1. auth.md §5.6a 与 §10.8 deploy nonce 机制矛盾

**文件**: `design/auth.md`  
**位置**: §5.6a 请求 Replay Class 表格 vs §10.8 Nonce vs Version Counter 表格

§5.6a 将 `swarm_deploy` 归类为 `idempotent_mutation`，标注 nonce 策略为 **"Dragonfly nonce + time window"**：

| Replay Class | Nonce 策略 | 示例 |
|---|---|---|
| `idempotent_mutation` | Dragonfly nonce + time window | `swarm_deploy` |

但 §10.8 明确声明：

> Deploy 不使用 nonce——防重放由 `version_counter` 保证

并在 Nonce vs Version Counter 表中将 Deploy 归类为 FDB `version_counter`：

| 场景 | 机制 | 存储 |
|---|---|---|
| Deploy 请求 | Version Counter (FDB) | FDB `version/{player_id}` |

**影响**: 两份权威表格给出矛盾的防重放机制。若实现者依据 §5.6a 使用 Dragonfly nonce 实现 deploy 去重，则 Dragonfly 崩溃后 TTL 窗口内（最长达 300s）可重放 deploy 请求；若依据 §10.8 使用 FDB version_counter，则无此问题。此矛盾必须消解——建议统一以 §10.8 为准（FDB version_counter），修正 §5.6a 表格中 `swarm_deploy` 的 nonce 策略列。

**修复建议**: 
1. 将 §5.6a 中 `swarm_deploy` 的 nonce 策略改为 "FDB version_counter" 或 "N/A (见 §10.8)"
2. 在 idempotent_mutation 行添加脚注说明 deploy 是特例
3. 添加 CI 交叉验证规则：api-registry.md 的方法分类不得与 auth.md 的 nonce 策略冲突

---

### C2. CRL 缓存默认 60s 窗口允许已吊销证书继续部署 WASM

**文件**: `design/auth.md` §10.8 Auth 子系统缓存边界  
**位置**: CRL 缓存延迟行

> | 证书吊销状态 (CRL) | FDB | Engine 内 LRU | **60s**（明确接受的风险：吊销后至多 60s 旧证书仍可被接受。竞争性世界可配置为 5-10s） |

以及 `specs/security/09-command-source.md` §3.3 部署验证流程步骤 3b：

> b. 证书在部署提交时未过期、未被吊销（CRL 查询）

**影响**: 部署验证依赖 CRL 缓存。默认 60s 窗口意味着：攻击者证书被吊销后，仍有最长 60s 窗口可继续部署 WASM 模块。对于竞争性世界（competitive world），60s 足够完成一次恶意部署。文档虽标注"可配置为 5-10s"，但：
1. 默认值 60s 对 competitive world 过高
2. 未说明 CRL 缓存刷新触发机制（是定时轮询还是事件驱动？）——若是 60s 定时轮询，实际窗口可能接近 120s
3. 未定义 "competitive world" 的自动检测或 world.toml 配置项

**修复建议**:
1. 将默认 CRL 缓存 TTL 从 60s 降至 **10s**，competitive world 最低可配 **2s**
2. 明确 CRL 刷新机制：事件驱动（证书吊销时主动推送 invalidation）优于定时轮询
3. 在 `world.toml [auth]` 段添加 `crl_cache_ttl_seconds` 配置项，competitive world 默认 5s
4. Deploy 热路径考虑：若 CRL 缓存 TTL > 10s，则在 deploy 验证时强制实时查询 FDB（绕过缓存）

---

## High

### H1. Dragonfly nonce 崩溃重放窗口

**文件**: `design/auth.md` §10.8 Nonce 存储

> | 崩溃语义 | TTL 窗口内可重放；窗口过后 nonce 过期 → 重放被拒绝 |

Dragonfly 作为内存存储，崩溃后所有 nonce 去重状态丢失。TTL 取默认 300s——这意味着 Dragonfly 崩溃恢复后的 300s 内，之前已使用的 nonce 可被重放。

**影响范围评估**:
- `read_replay_safe` 查询：重放无害（纯查询），影响 Low
- `idempotent_mutation`（Dragonfly nonce 路径的）：需逐方法审计是否真正 idempotent；若某方法被错误归类，重放可能产生副作用
- 文档已正确将 `non_idempotent_mutation` 和 `admin_critical` 路由到 FDB——此设计分离是正确的

**修复建议**:
1. 对 Dragonfly nonce 路径的所有 idempotent_mutation 方法进行审计，确认其幂等性经得起重放
2. 在运维手册中添加 Dragonfly 崩溃后的 nonce 窗口风险说明
3. 考虑在 Dragonfly 恢复后，对 FDB 中最近 300s 内的操作进行回放检测（通过对比操作 hash）

---

### H2. Pathfinding 全局预算 100K nodes 可被单玩家耗尽 — fair-share 机制未在审阅文档中明确定义

**文件**: `specs/reference/api-registry.md` §5 全局容量限制, `specs/core/04-wasm-sandbox.md` §6

> | Pathfinding budget | **100,000 explored nodes/tick** | 引擎全局；per-player 10 次调用 |

以及：

> path_find 调用 | 10/tick | 计数；全局预算 100,000 explored nodes/tick，per-player fair-share 分配（见 engine.md §3.4.2）

**影响**: 100K nodes 为全局共享预算。10 次调用/玩家 × 10K nodes/调用 = 单玩家可消耗全部预算。`host_path_find` 的 fuel 成本为 "500 × explored_nodes"，10K nodes = 5M fuel——在 10M/tick 的 fuel 预算内。即单个恶意玩家可在合法 fuel 预算内耗尽全局 pathfinding 配额，导致其他玩家 pathfinding 返回 `ERR_GLOBAL_BUDGET`。

"per-player fair-share 分配" 机制引用了 engine.md §3.4.2，但**该文件不在本次审阅范围内**。无法确认 fair-share 机制是否实际存在、是否可被绕过。

**修复建议**:
1. 在可见文档中补充 per-player pathfinding fair-share 的最小保证值（如 "每玩家最低保证 5000 nodes/tick"）
2. 全局预算耗尽时应返回明确的 RejectionReason（`PathfindingBudgetExhausted`），而非静默 fallback 或错误的路径
3. MCP simulate 边界：`swarm_simulate` 中的 pathfinding 是否消耗全局预算？若消耗，需设独立预算池

---

### H3. Worker Pool Store reset 跨 tick 状态残留审计缺口

**文件**: `specs/core/04-wasm-sandbox.md` §1 生命周期

> 每 tick：worker 从池中取出 → 重置 Wasmtime Store（清空线性内存、重置 fuel counter、重建 Instance） → 执行单一玩家的 `tick()` → 返回结果 → 返回池中。

**影响**: Worker pool 模型意味着同一进程先后执行不同玩家（甚至同一玩家不同 tick）的 WASM。虽然 "重建 Instance" 应创建全新 WASM 实例，但 Wasmtime Store 中可能存在以下残留路径：

1. **Engine 级全局状态**: Wasmtime `Engine` 是进程级单例，编译缓存、JIT code cache 跨 Instance 共享。若 Cranelift JIT 在代码生成中嵌入 player-specific 常量（理论上不应发生，但需验证），可能跨 Instance 泄露
2. **Host function 闭包状态**: Host functions 的实现可能持有指向 Engine/World 状态的引用。`host_path_find` 的寻路缓存若未按 player 隔离（缓存键包含 `player_visibility_fingerprint` 是好的，但需确认实现），可能跨玩家泄露路径信息
3. **OS 级残留**: `/tmp` (tmpfs, 16MB) 在 Store reset 时是否被清空？若否，恶意 WASM 可在 /tmp 中留下标记文件，下一 tick 的 WASM 可检测到（即使 /tmp 是独立 tmpfs，同一 worker 进程内的 /tmp 跨 tick 持久）

**修复建议**:
1. 添加集成测试：玩家 A 的 WASM 在 tick N 写入状态到 WASM 线性内存 → Store reset → tick N+1 玩家 B 的 WASM 读取同一内存地址 → 断言为初始值（全零）
2. `/tmp` 清理策略：每个 tick 结束后清空 `/tmp` 或每次 tick 使用独立 subdirectory
3. Host function 实现审计：确认所有 host function 闭包不持有跨 tick 状态
4. 在 Sandbox OS 加固 Checklist (§9) 中添加 "Store reset 完整性验证"

---

### H4. 联邦 CRL 同步间隔 60s + `revocation_fallback` 策略矩阵可能导致安全降级

**文件**: `design/auth.md` §15.2a 联邦 CRL 同步

> | 同步间隔 | 60s（可配置） |
> | 获取失败 | 使用上次成功同步的 CRL 快照；`revocation_fallback` 策略生效 |

以及 `revocation_fallback` 策略：

| 值 | 行为 |
|---|---|
| `allow_with_warning` | 允许但有审计日志告警（仅用于低风险世界） |

**影响**: 联邦场景下，远程世界 A 吊销了某玩家的证书，但本地世界 B 的 CRL 同步可能滞后最长 60s + 获取失败后的 fallback 窗口。三层延迟叠加：

1. 世界 A CRL 更新延迟（A 自身的缓存 TTL）
2. 世界 B 同步间隔（60s）
3. 世界 B 获取失败后 `revocation_fallback` 策略

最坏情况：世界 A 吊销 → 世界 A CRL 缓存 60s 延迟 → 世界 B 下次同步再等 60s → 世界 B 获取失败进入 `allow_with_warning` → 攻击者可在世界 B 继续操作数分钟。

`allow_with_warning` 策略允许"低风险世界"在 CRL 不可用时继续接受联邦证书——但风险级别由谁定义？若配置错误将高风险世界标为"低风险"，杀伤链成立。

**修复建议**:
1. `allow_with_warning` 策略应记录 WARN 日志 **并触发监控告警**（不依赖人工查看日志）
2. 默认策略改为 `reject_for_code`（更安全的默认值）
3. 联邦 CRL 获取失败后应在 world.toml 中定义最大 stale 时间（`federation_crl_max_stale_seconds`），超过后强制降级到 `reject_all`

---

## Medium

### M1. Intermediate CA 私钥文件存储的 `accept_file_based_intermediate_key` 风险接受机制

**文件**: `design/auth.md` §3.1 证书签发接口

> 自托管部署如无法使用 HSM，必须使用 soft-HSM 或加密文件系统，并**显式接受风险**（在 world.toml `[auth.ca] accept_file_based_intermediate_key = true` 中声明）。

**分析**: 这个设计是务实的——小型部署确实可能无力负担 HSM。但当前机制有几个薄弱点：

1. `accept_file_based_intermediate_key = true` 是布尔开关——无法区分 "加密文件系统上的 0600 文件" 与 "未加密 ext4 上的 0600 文件"
2. 启动强制检查只验证 "文件权限 0600 或 HSM 可访问性"——0600 权限是必要的但远远不够。文件系统快照、备份、容器镜像层都可能泄露私钥
3. 审计合同（`auth/ca_audit`）记录每次签名——但记录的是事后日志，不能阻止私钥泄露后的签名滥用

**建议**: Medium 级别——这是已知的风险接受，且文档已明确标注。建议增强：启动检查不仅验证 0600，还需验证文件所在挂载点是否加密（如检查 `/proc/mounts` 中是否有 `encryption` 标记）。

---

### M2. 恢复流程 dummy argon2id 常量时间实现验证需求

**文件**: `design/auth.md` §17.1 威胁模型

> | 响应时间侧信道 | dummy argon2id 消除存在/不存在用户的时间差 |
> | 时序攻击 | `verify_password` 使用 argon2 crate 的常量时间比较 |

**分析**: 威胁模型正确识别了侧信道风险。但 dummy argon2id 的实现需要极其小心：
- Dummy 路径必须执行与真实路径**完全相同**的计算量（相同 memory、相同 iterations、相同 parallelism）
- 若 dummy 路径使用简化的参数（如更低的 memory），时序差仍然可观测
- Rust `argon2` crate 的 `verify_password` 内部使用 `PasswordHash::new()` 解析 PHC 字符串——若 dummy 用户使用不同的 salt/hash 格式，解析时间可能不同

**建议**: 在测试策略中添加常量时间验证测试：对不存在用户和存在用户（错误密码）的恢复请求，测量 P99 响应时间差异应 < 5ms。

---

### M3. Wasmtime =30.0 版本锁定无 EOL 迁移计划

**文件**: `specs/core/04-wasm-sandbox.md` §2.1, `specs/security/CVE-SLA.md`

> wasmtime = "=30.0"   # 锁定版本 — 不自动升级

以及：

> 锁定版本需在官方安全支持窗口内

**分析**: Bytecode Alliance 的 Wasmtime 发布周期约每月一个版本。`=30.0` 是一个具体版本号——但未说明这是 Wasmtime 30.0.0 还是语义版本 `^30.0`。当 Wasmtime 30.x 的安全支持窗口结束（通常下一个稳定版发布后 3-6 个月），需要迁移计划。CVE-SLA.md 定义了 Critical 24h 响应，但未定义"版本 EOL → 审计 → 迁移"的流程和触发条件。

**建议**:
1. 明确 `=30.0` 的精度（是 `=30.0.0` 还是 `=30.0` 允许 patch？）
2. 添加季度审查任务：检查锁定版本的安全支持窗口余量
3. 当窗口余量 < 90 天时触发版本迁移评估

---

### M4. Agent 端点 DNS rebinding 依赖 Host header 验证

**文件**: `specs/security/03-mcp-security.md` §2.3 DNS Rebinding 防御

> | DNS rebinding → private network (10.x, 192.168.x) | Gateway 检查 `Host` header，拒绝非白名单 hostname |

**分析**: Agent/CLI 端点使用应用层证书签名，不依赖 Origin header。DNS rebinding 防御完全依赖 Host header 校验。攻击向量：

1. 攻击者注册 `attacker.com`，DNS 返回攻击者 IP
2. 受害者 agent 首次连接 → 获取 Server Root CA fingerprint → pin
3. 攻击者操控 DNS 将 `attacker.com` 解析到 `127.0.0.1`
4. 受害者 agent 后续请求发往 127.0.0.1 → Host header 仍为 `attacker.com`
5. Gateway 检查 Host header → `attacker.com` 不在白名单 → 拒绝 ✓

此向量在当前设计中被正确阻止，但防御面单一。若 Host header 检查存在绕过（如 hostname 后缀匹配 `*.kagurazakalan.com` 而攻击者注册 `fake-kagurazakalan.com`），则可能穿透。

**建议**: 增加第二层防御——Gateway 启动时记录自身监听地址，拒绝目的 IP 为 loopback/private 的请求（即使 Host header 合法）。

---

## Low

### L1. auth.md §5.6a 表格 `swarm_deploy` 示例归类误导

同 C1，但从文档质量角度。`swarm_deploy` 在该表格中作为 `idempotent_mutation` 的示例出现，且 nonce 策略标注为 "Dragonfly nonce"。新读者会据此认为 deploy 使用 Dragonfly 去重。建议在该单元格添加引用 `(见 §10.8 — 实际使用 FDB version_counter)`。

---

### L2. MCP simulate 未定义恶意构造输入的预算消耗

**文件**: `specs/core/04-wasm-sandbox.md` §6.1

> | `max_cpu_ms` | 5000 | 每次模拟最多 5 秒 CPU 时间 |

**分析**: `swarm_simulate` 接受用户提供的 `commands` 和 `assumptions`。模拟在引擎内执行——若攻击者构造恶意 commands（如 10,000 条 Move 指令），模拟是否会消耗超预算的 CPU 时间？当前限制 `max_cpu_ms=5000` 和 `max_ticks=100` 提供了基本保护，但未说明模拟中是否对 commands 数量有限制（类似每 tick 100 commands 的限制）。

**建议**: 在 API Registry 中为 `swarm_simulate` 添加 `max_commands_per_simulate` 参数（建议 ≤ 500）。

---

### L3. 持久化合同未定义 TickTrace blob 的完整性验证频率

**文件**: `specs/core/05-persistence-contract.md` §4

> 3. 验证 Blake3(tick_trace_blob) == tick_manifest.content_hash

**分析**: 完整性验证仅在 Replay 恢复时执行。正常运行中不会主动验证对象存储中已有 blob 的完整性（如 bit rot 检测）。对于 180d cold storage 的 blob，存在静默损坏风险。

**建议**: 添加后台 GC 任务：对 cold storage 中超过 30d 的 blob，每 7d 抽样验证 hash。

---

## 亮点

1. **Oracle 防线闭合优秀**: `NotVisibleOrNotFound` 合并错误码、`omitted_count` 分桶化、特殊攻击统一 `NotEligible`、dry_run/simulate 脱敏——形成了多层次的 anti-oracle 防御体系。这是整个设计中最严密的安全部分。

2. **应用层证书模型清晰**: 用途隔离证书（ClientAuth/CodeSigning/Admin）、audience 绑定 transport、Server CA 不进入系统信任根、不安全传输可认证——设计完整且不依赖外部 PKI。

3. **Deferred Command Model 正确**: WASM `tick()` 只输出 JSON 指令，不能直接调用 mutating host function。所有状态变更必须经过引擎校验管线（Source Gate → Auth Verify → Command Validation）——这是一个强制安全边界。

4. **Sandbox OS 加固 Checklist 实用**: seccomp 白名单、cgroup 限制、命名空间隔离、恶意 WASM 样本库、CI 验证——从设计到测试覆盖完整。

5. **威胁模型自洽**: auth.md §17.1 列举 15 种威胁及其缓解措施，与 §5-§14 的机制设计一一对应，无"定义了威胁但忘了缓解"或"实现了缓解但未声明威胁"的脱节。

6. **浏览器存储策略正确**: HttpOnly Secure SameSite=Strict cookie + WebCrypto non-extractable key + 明确禁止 localStorage——对于可编程 MMO（玩家原创字符串构成 XSS 攻击面）这是关键设计。

---

## CrossCheck — 需要跨方向检查

以下问题本方向无法独立验证，需要 Architect / Game Designer 方向确认：

### X1. Engine 侧 CRL 缓存失效触发机制 [→ Architect]

本方向发现 CRL 缓存默认 60s 对 deploy 路径过宽（C2）。需要 Architect 确认：
- Engine 内 CRL 缓存是定时轮询（interval 多少？）还是事件驱动（Auth Service 主动 push）？
- 定时轮询模式下的实际最大窗口 = 缓存 TTL + 轮询间隔（可能 > 60s）
- 是否可在 deploy 热路径强制跳过缓存直接查 FDB？

### X2. Pathfinding fair-share 分配算法 [→ Architect]

本方向发现全局 100K nodes 预算可被单玩家耗尽（H2）。需要 Architect 确认：
- engine.md §3.4.2 中 fair-share 分配的具体算法（max-min fairness? weighted? hard cap per player?）
- 若 fair-share 存在，是否在 wasm-sandbox.md 或 api-registry.md 中有对应的 per-player 最低保证值？
- 全局预算耗尽时各玩家的行为（全部返回 `ERR_GLOBAL_BUDGET` 还是部分玩家成功？）

### X3. Worker pool 大小与玩家隔离度 [→ Architect]

本方向提出 Store reset 跨 tick 残留风险（H3）。需要 Architect 确认：
- Worker pool 是 per-player 独占进程还是共享池？
- 若共享池：同一 worker 进程在执行玩家 A 的 tick N 后、执行玩家 B 的 tick N 之前，除 Store reset 外还有哪些清理步骤？
- `/tmp` (tmpfs) 的清理策略？

### X4. Overload/Hack 等特殊攻击的 Oracle 防线 [→ Game Designer]

visibility.md §6 定义了 Overload/Hack 的可观察性规则。需要 Game Designer 确认：
- `OverloadPressure.total` 对 target 始终可见——target 可通过自身 fuel 下降间接感知，此设计没问题。但 attacker 可见的 `target_player_id` 是否构成 oracle？（attacker 可通过此信息确认某 player 在目标世界有活跃实体）
- Hack 施加后 `Hacked { by: player_id, remaining: 5 }` 对 target 可见——`by: player_id` 暴露了攻击者身份。这与 §6.3 "target 不可看到攻击者身份除非在视野内" 矛盾吗？

### X5. deploy nonce 矛盾的权威解析 [→ Speaker]

C1 发现的 auth.md §5.6a vs §10.8 矛盾需要 Speaker 在跨方向评审中裁决哪一方为权威。建议：
- deploy 防重放以 §10.8 为准（FDB version_counter，更安全）
- §5.6a 表格修正为引用 §10.8
- 全文档搜索 `swarm_deploy` + `nonce` 关键字，确保再无矛盾引用
