# R23 安全评审 — DeepSeek V4 Pro

> **评审员**: rev-dsv4-security (Security Reviewer)
> **日期**: 2026-06-19
> **评审范围**: Phase 1 Clean-Slate — 仅方向相关子集（9 份文档）
> **评审视角**: 协议一致性验证、数据流追踪（Snapshot→WASM→Commands→Validator→ECS）、竞态条件检测、信任边界分析

---

## Verdict: CONDITIONAL_APPROVE

**摘要**: 安全架构整体设计扎实——应用层证书链认证、WASM 多层沙箱隔离、统一可见性函数 `is_visible_to`、Oracle 防线闭合、持久化分层 FDB 原子提交均为正确方向。发现 **0 Critical**、**5 High**、**5 Medium**、**4 Low**，以及 **5 项 CrossCheck**。所有 High 级问题均可在实现阶段解决，无架构级阻塞。

---

## 发现的问题

### Critical
（无）

### High

#### S-H1: CSR challenge 字段交叉验证缺失 — 协议一致性

**文件**: `design/auth.md` §5.2, §9.3
**严重性**: High

CSR payload (§5.2) 包含 `challenge: <server challenge>` 字段并被客户端私钥签名。但服务端验证流程 (§9.3) 仅从 FDB 读取 challenge 用于 PoW 验证 (`verify_pow(&stored.challenge, &params.nonce, ...)`)，**未交叉验证 CSR 内嵌的 `challenge` 是否与 FDB 权威值一致**。

**攻击场景**:
1. 攻击者获取 challenge A 并完成 PoW
2. 攻击者构造 CSR，内嵌不同的 challenge B（如过期的旧 challenge）
3. 提交 `challenge_id=A, nonce=valid_for_A, csr_signature=valid`
4. 服务端验证 PoW 通过（使用 FDB 中的 challenge A），CSR 签名验证通过
5. 审计日志中出现不一致的 challenge 值（CSR 中是 B，FDB 中是 A）

**实际风险**: 低（PoW 重放已被 `consumed` 标记阻止，`csr_signature` 绑定 public key 防止身份盗窃），但协议不一致会在未来重构中引入隐蔽漏洞，且审计 trail 不可信。

**修复建议**: 在服务端验证中增加:
```rust
// After reading stored challenge from FDB:
if csr.challenge != stored.challenge {
    return Err("csr_challenge_mismatch");
}
```

#### S-H2: Dragonfly 崩溃后 idempotent_mutation 重放窗口

**文件**: `design/auth.md` §10.8, §5.6a; `specs/reference/api-registry.md` §2.5/§3.3
**严重性**: High

§10.8 明确 Dragonfly nonce 的崩溃语义为「TTL 窗口内可重放」。对于 `read_replay_safe` 操作这是无害的。但在 §5.6a 中，`idempotent_mutation` replay class 也被指定使用「Dragonfly nonce + time window（除 deploy 外）」。

查 API Registry 中标记为 `idempotent_mutation` 的操作:
- `swarm_tournament_precommit` (game_api)
- `swarm_auth_device_register` (auth_api)
- `swarm_submit_csr` (实际使用 PoW challenge 消费，不受影响)

Dragonfly 崩溃后，`swarm_tournament_precommit` 和 `swarm_auth_device_register` 的 nonce 全部丢失，TTL 窗口内的请求可被重放。

**修复建议**:
- 将 `idempotent_mutation` 操作的 nonce 迁移至 FDB（使用原子 CAS），与 deploy 的 version_counter 一致
- 或明确文档化 Dragonfly 崩溃后的重放为**接受风险**，并说明 `tournament_precommit` 的业务影响（重复 precommit 仅覆盖前值，不产生副作用）

#### S-H3: 联邦 CRL 同步信任边界——远程世界可提供过期/不完整 CRL

**文件**: `design/auth.md` §15.2a
**严重性**: High

联邦 CRL 同步通过 HTTPS 向远程世界获取增量吊销列表。远程世界可能:
1. 故意不返回某些吊销记录（恶意世界服主）
2. 因自身故障返回不完整数据
3. 在被攻陷后提供伪造 CRL

当前 fallback 策略（`reject_for_code` / `reject_all` / `allow_with_warning`）在「sync 超过 2× 同步间隔」时触发，但**未检测远程世界是否返回了选择性隐藏的 CRL**。

**场景**: 恶意远程世界服主吊销了用户 A 的证书，但在 CRL delta 中故意省略该记录。本地世界将继续信任用户 A 的证书，允许其登录或部署代码。

**修复建议**:
- 联邦 CRL 端点响应必须由远程世界的 Server Intermediate CA 签名（CRL 响应包含 Ed25519 签名）
- 或要求远程世界发布可审计的 CRL 日志（append-only merkle tree），本地世界验证 CRL 完整性
- 最低要求：在文档中标注此信任假设（「联邦信任远程世界服主诚实地提供完整 CRL」）

#### S-H4: Refresh token rotation grace period 竞态——60s 窗口内可双花

**文件**: `design/auth.md` §14.1
**严重性**: High

Refresh token rotation 设计为「旧 token 在 rotation 后 60s 内仍可被接受一次（grace period，防竞态）」。这意味着:
1. 合法用户完成 rotation，获得新 token
2. 攻击者（已窃取旧 token）在 60s 内使用旧 token
3. 服务端接受旧 token，执行 rotation，签发又一个新 token
4. 攻击者现在持有有效 token，合法用户的 token 反而因 family revoke 失效

**当前缓解**: 「异常 IP/UA 使用 grace 时触发 session family revoke（该用户所有 session 吊销）」
**不足**: IP/UA 可被同一网络下的攻击者伪造（NAT、同一 WiFi、compromised device）。

**修复建议**:
- 将 grace period 接受条件加强为: `grace 接受必须来自与原始 rotation 请求相同的 IP/UA`，否则直接拒绝（非 family revoke）
- 或缩短受信设备的 grace 至 10s（已在设计中），并将非受信设备的 grace 从 60s 降至 5s
- 或使用 FDB 原子 CAS 确保 grace 只能被消费一次（已在设计中提到 `grace_consumed_at`——确认此字段实现为原子操作）

#### S-H5: 编译缓存的 security_epoch 全量失效——安全事件期间 DoS 放大

**文件**: `specs/core/04-wasm-sandbox.md` §7
**严重性**: High

编译缓存键包含 `security_epoch`。当 epoch bump 发生时，**所有已缓存模块全量失效**。500 活跃玩家 × 每人多个模块 = 数千次重新编译。并发编译上限为 5，即大量模块排队等待。

在安全事件期间（这正是触发 epoch bump 的场景），服务器可能已处于 degraded mode，此时数千次编译将:
- 阻塞新 WASM 部署达数小时
- 使合法玩家无法更新策略应对攻击
- 在 competitive world 中形成事实上的 DoS

**修复建议**:
- 安全事件期间允许编译并发上限临时提高（如 5→20），并从 engine budget 中预分配资源
- 或采用分层失效：security_epoch bump 时旧缓存模块继续运行（仅 `paused_security` 的分级处理），后台异步重新编译
- 最低要求：在 CVE-SLA runbook 中补充「epoch bump 后的编译风暴应急预案」

---

### Medium

#### S-M1: 路径寻找 fair-share 饱和攻击

**文件**: `specs/reference/api-registry.md` §4.4, §5.6
**严重性**: Medium

`host_path_find` 全局预算为 100,000 explored nodes/tick，按 `floor(100,000 / active_players)` 分配。但 fuel 成本为 `500 × explored_nodes + 200 × expanded_edges`，可构造高计算/Fuel比的最坏情况输入（如寻路至不可达的迷宫死胡同，消耗大量节点探索但燃料计数低）。

攻击者可用多个 account 各自消耗其 fair-share 份额，**耗尽全局 100,000 node 预算**，导致正常玩家的 `host_path_find` 返回 `ERR_BUDGET_EXHAUSTED`。

**修复建议**:
- `host_path_find` 的 fuel 成本改为与实际 CPU 时间成比例（Wasmtime fuel 本身已计量指令数，但路径寻找在宿主端执行）
- 或对不可达目标的路径寻找实现早期剪枝（如双向 BFS 快速判断连通性后再分配 A* 预算）

#### S-M2: Deploy ACTIVATION_PENDING 等待超时——blob 上传失败 vs 网络延迟的歧义

**文件**: `specs/core/05-persistence-contract.md` §2.3
**严重性**: Medium

Deploy 状态机在 `ACTIVATION_PENDING` 阶段:「upload_status == "pending" (blob 仍在传输) → 等待最多 30s → 仍 pending → 视为 FAILED」。但 30s 超时无法区分「blob 上传真正失败」与「对象存储暂时不可用但稍后会成功」。

若对象存储在 30s 后恢复，blob 上传成功，但 deploy 已被标记 FAILED，出现孤儿 blob。虽然后续 GC 会清理，但玩家需要重新部署（消耗 deploy rate limit 10/h）。

**修复建议**:
- 区分「上传中」(uploading) 与「确认失败」(upload_error)：若 blob worker 仍在传输，延长等待至 120s；仅当 blob worker 返回错误时才立即 FAILED
- 或在 FAILED 后若 blob 上传成功，允许手动 `swarm_retry_deploy` 使用已有 blob（不消耗 rate limit）

#### S-M3: TickTrace untrusted string 截断导致 replay 信息丢失

**文件**: `specs/core/04-wasm-sandbox.md` §6.2
**严重性**: Medium

「Untrusted string（player name, room name 等）256 字符截断...记录原始 hash」。但在 replay 场景中，截断后的字符串如果再经 hash → 与其他字段组合 hash → 进入 hash chain，则 **256 字符截断是非确定性操作**（取决于原始字符串长度，而 hash 输入在截断前后不同）。虽然文档说「记录原始 hash」，但若原始 hash 被用于后续确定性计算，则 replay 验证需要原始 hash 而非截断后的。

**修复建议**: 明确截断策略的实现顺序——先计算完整字符串的 hash，再截断字符串用于显示/存储。hash chain 中始终使用完整字符串的 hash。

#### S-M4: PoW difficulty_bits 缺乏动态调整机制

**文件**: `design/auth.md` §9.2
**严重性**: Medium

PoW 难度固定为 `difficulty_bits = 24`（~16.7M 次尝试，~150ms Rust native）。在以下场景中不足:
- 攻击者使用 GPU/FPGA 加速 blake3（blake3 高度可并行化，GPU 可达 10+ GH/s，24 bits 约 1.7ms）
- 注册风暴时固定难度无法自适应提升

`register_pow_difficulty_bits` 在 world.toml 中可配置，但无自动调节机制。

**修复建议**:
- 实现基于近期注册速率的自适应难度调节（如目标 1 registration/s，超出则 +2 bits）
- 或在文档中明确标注 24 bits 仅适用于 CPU 攻击者，GPU 攻击者可将时间缩短 100×，并建议生产环境使用 28-32 bits

#### S-M5: Argon2id 线程池排队可能导致恢复流程超时

**文件**: `design/auth.md` §6.1 (安全评审要求 S-H4)
**严重性**: Medium

Argon2id 验证部署全局 semaphore/worker pool（限制 `min(cpu_cores, 4)` 并发）。在以下场景可能出问题:
- 攻击者用大量不存在用户名发起恢复请求（触发 dummy argon2id）
- 合法用户的恢复请求排在攻击请求之后，等待超时
- 恢复流程是时间敏感的（reset token 15min TTL），排队延迟可能导致用户错过恢复窗口

当前已有 per-IP 限流在 argon2id 之前拦截，但攻击者可分散 IP（如 botnet）绕过 per-IP 限制。

**修复建议**:
- 为恢复流程分配独立的高优先级 argon2id worker（与登录/注册分离）
- 或在 dummy argon2id 路径使用更轻量的哈希（当用户不存在时，其 dummy 验证可使用固定迭代次数的快速哈希，因为不存在密码可泄露）

---

### Low

#### S-L1: 邮箱重置 token 的常量时间比较

**文件**: `design/auth.md` §11.1-11.2
**严重性**: Low

恢复密码使用 argon2id（内置常量时间比较），但邮箱重置 token (§11.2) 的验证未明确要求常量时间比较。32 字节随机 token 的暴力搜索空间为 2^256，不可能穷举，但侧信道仍可泄露部分 token 信息。

**修复建议**: 使用 `subtle::ConstantTimeEq` 或等价常量时间比较实现 token 验证。

#### S-L2: 多账号绑定同一邮箱时的信息泄露

**文件**: `design/auth.md` §12
**严重性**: Low

「多账号绑定同一邮箱时，证书恢复邮件列出所有关联账号的 display_name / login_username」——任何人知道你的邮箱都可以发现你的所有 Swarm 账号名。这被文档标注为特性而非缺陷，但从隐私角度是可选的泄露。

**修复建议**: 为 `auth.email_multi_account_listing` 增加配置开关，允许部署者关闭多账号列举。

#### S-L3: 非浏览器 Agent 端点的 HTTP 不安全传输风险

**文件**: `specs/security/03-mcp-security.md` §2.2, §5.7
**严重性**: Low

Agent/CLI 端点支持 HTTP 不安全传输用于身份认证（通过应用层证书）。虽然文档明确「攻击者可以观察流量元数据」，但未具体说明观察到的元数据范围（MCP tool name, player_id, 请求频率等构成 traffic analysis 攻击面）。

**修复建议**: 在文档中增加 traffic analysis 威胁的具体描述，并建议生产环境始终使用 HTTPS。

#### S-L4: 调试/测试 world 的 relaxed sandbox 配置旁路风险

**文件**: `specs/core/04-wasm-sandbox.md` §9.3
**严重性**: Low

「生产环境禁止 `sandbox.relaxed = true`。引擎启动时检查配置，若为 true 且 `world.mode != "development"` → 拒绝启动」。此检查仅阻止生产 world 启动，但若攻击者能修改 world.toml 并重启引擎（如社工或内部威胁），则 relaxed 模式下 `clock_gettime` 和 `stderr` 被允许，可能泄露信息或破坏确定性。

**修复建议**: 在 world.toml 中为 `sandbox.relaxed` 增加 Ed25519 签名校验（需 admin 签名才能启用）。

---

## 亮点

1. **应用层证书链设计**: 离线 Server Root CA + 在线 Intermediate CA + 用途隔离证书（ClientAuth/CodeSigning/Admin），模型清晰，职责分离到位。CA 私钥强制 HSM/soft-HSM 保护，启动时校验拒绝不安全配置。

2. **WASM 纵深防御**: seccomp(cBPF) × cgroup v2 × Wasmtime fuel metering × epoch interruption × 无 WASI 文件/网络/时钟 × deferred command model —— 五层防护叠加，纵深充分。

3. **可见性统一函数 `is_visible_to`**: 所有输出面（WASM snapshot、MCP、WebSocket、REST、Replay）强制经过同一函数过滤，彻底消除「快照说隐藏但 WebSocket 泄露」类 bug。Oracle 防线（§10.1-10.4）覆盖特殊攻击拒绝码等价类、`omitted_count` 分桶脱敏、`dry_run`/`simulate` 信息降级。

4. **Command Source 矩阵**: 所有指令来源显式建模（WASM/MCP_Deploy/MCP_Query/Admin/Rollback/RuleMod），auth_context 服务端注入不可伪造，`Source Gate` 在管线入口强制检查。Rollback 要求双人 Ed25519 签名——高权限操作的安全设计到位。

5. **Persistence 分层**: FDB 原子提交 replay-critical subset（10 项必填字段），对象存储异步写入 debug/rich blob。FDB commit 成功 = tick 持久化完成，blob 缺失不影响确定性回放。Deploy 完整状态机（VALIDATE→UPLOAD_PREPARE→MANIFEST_COMMIT→ACTIVATION_PENDING→ACTIVE）消除 TOCTOU。

6. **CVE SLA 务实**: Wasmtime + 14 个 Critical Rust crate 的 CVE 监控/评估/修复/测试/发布/回滚完整流程，Critical 24h、High 72h 的响应时限切实可行。安全 epoch bump 分级状态机处理 `paused_security` 与 `needs_revalidation`。

7. **Anti-enumeration 实现**: 恢复凭据统一返回 `invalid_credentials` + dummy argon2id 消除时序差；`username_visibility` 可配 `private` 模式隐藏用户名占用状态；邮箱重置统一返回成功——防枚举措施覆盖全面。

---

## CrossCheck — 需要跨方向检查

- **CX1**: Deploy `activation_tick = current_tick + 1` 的精确语义——COLLECT 阶段与 deploy manifest commit 的时序关系需 Architect 验证：若 deploy 在 COLLECT 完成后、同一 tick 的 EXECUTE 阶段提交，下一 tick 的 COLLECT 能否正确读取新模块快照？ → 建议 **Architect** 检查 Tick 调度器与 Deploy 状态机的交互时序。

- **CX2**: Worker pool 模型下 Wasmtime Instance 重建的隔离完备性——`specs/core/04-wasm-sandbox.md` §1 声明「重建 Instance」清空 WASM 线性内存、重置 fuel counter，但未说明 Wasmtime 内部是否有跨 Instance 的隐式状态（如编译缓存、全局堆）。 → 建议 **Architect** 对照 Wasmtime 30.0 文档验证 Instance 重建的隔离边界。

- **CX3**: Dragonfly 作为 nonce 存储时，`idempotent_mutation` 操作（tournament_precommit、device_register）在 Dragonfly 崩溃后的行为——是否可能产生双重提交或状态不一致？当前设计中 deploy 使用 FDB version_counter、admin 使用 FDB monotonic counter，但 idempotent_mutation 仍依赖 Dragonfly。 → 建议 **Architect** 枚举所有 Dragonfly 崩溃场景下的状态恢复路径。

- **CX4**: 联邦 CRL 同步的 HTTPS 端点——当前设计未要求 CRL 响应包含远程 Server Intermediate CA 签名或 merkle proof。若远程世界服主恶意隐藏吊销记录，本地世界无检测能力。 → 建议 **Security (交叉验证)** 检查联邦信任模型的威胁模型文档，确认此风险是否被接受。

- **CX5**: Pathfinding fair-share 分配可能在 competitive world 中被滥用——攻击者可用多 account 耗尽全局 100,000 explored nodes/tick 预算，使合法玩家的 pathfinding 全部失败。需量化此攻击在 500 active players 场景下的实际影响。 → 建议 **Gameplay / Economy** 评估 pathfinding 预算耗尽对核心游戏循环的影响程度。

---

## 审查文件清单

| # | 文件 | 行数 | 状态 |
|---|------|------|------|
| 1 | `design/README.md` | 231 | ✅ 已审查 |
| 2 | `design/auth.md` | 1780 | ✅ 已审查 |
| 3 | `specs/reference/api-registry.md` | 889 | ✅ 已审查 |
| 4 | `specs/security/03-mcp-security.md` | 389 | ✅ 已审查 |
| 5 | `specs/security/05-visibility.md` | 413 | ✅ 已审查 |
| 6 | `specs/security/09-command-source.md` | 340 | ✅ 已审查 |
| 7 | `specs/security/CVE-SLA.md` | 101 | ✅ 已审查 |
| 8 | `specs/core/04-wasm-sandbox.md` | 418 | ✅ 已审查 |
| 9 | `specs/core/05-persistence-contract.md` | 357 | ✅ 已审查 |

**总计**: 9/9 文件，~4,918 行审查完毕。

---

*评审完成时间: 2026-06-19 | 评审模型: DeepSeek V4 Pro | 配置文件: rev-dsv4-security*
