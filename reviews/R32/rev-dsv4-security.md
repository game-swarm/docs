# R32 Security 独立评审报告

**评审员**: rev-dsv4-security (DeepSeek V4 Pro)
**评审视角**: 协议分析、竞态条件检测、安全边界完整性
**日期**: 2026-06-21
**评审文档集** (9 份):
- `/tmp/swarm-review-R32/design/README.md`
- `/tmp/swarm-review-R32/design/auth.md`
- `/tmp/swarm-review-R32/specs/reference/api-registry.md`
- `/tmp/swarm-review-R32/specs/security/03-mcp-security.md`
- `/tmp/swarm-review-R32/specs/security/05-visibility.md`
- `/tmp/swarm-review-R32/specs/security/09-command-source.md`
- `/tmp/swarm-review-R32/specs/security/CVE-SLA.md`
- `/tmp/swarm-review-R32/specs/core/04-wasm-sandbox.md`
- `/tmp/swarm-review-R32/specs/core/05-persistence-contract.md`

---

## 1. Verdict

**REQUEST_MAJOR_CHANGES**

发现 2 个 Critical 问题（WS MAC payload 跨文档不一致 / Auth 工具缺失 API Registry 注册）和 4 个 High 问题（body_hash 规范化未定义 / 恢复凭据双重 side-channel 缺口 / 联邦 CRL fallback 安全策略默认值 / Admin 双签 challenge-response 缺少 nonce 原子性声明）。这些是信任边界上的确定性安全缺陷，必须在合并前修复。

---

## 2. 发现的问题

### Critical 问题

#### C1. WebSocket Per-Message MAC Payload 跨文档不一致 — 缺少 tick 绑定 → 跨 tick 重放

- **文件对比**: `design/auth.md` §10.5a vs `specs/security/03-mcp-security.md` §2.5 A
- **auth.md §10.5a 行 815**: `SWARM-WS-MSG-V1\n<seq>\n<tick>\n<body_hash>`
- **03-mcp-security.md §2.5 行 162-164**: `SWARM-WS-MSG-V1\n<seq>\n<body_hash>`
- **问题描述**: 两份文档对 Agent WS per-message MAC 的签名 payload 定义不一致。auth.md 包含 `tick` 字段（正确——防止跨 tick 消息重放），03-mcp-security.md 缺失此字段。
- **影响分析**: 若按 03-mcp-security.md 实现，攻击者可在同一 WS 连接内将 tick N 的有效消息重放到 tick N+1。虽有 seq 单调递增防护，但 seq 仅防重排和丢失，不防跨 tick 语义重放（如"deploy intent"消息在已部署后又被重放）。tick 绑定是 WS 时间维度的关键防护层。
- **修复建议**: 统一为 auth.md 版本（包含 tick）。03-mcp-security.md §2.5 行 162-164 应修改为 `SWARM-WS-MSG-V1\n<seq>\n<tick>\n<body_hash>`。同步更新对应的 server-side validation pseudocode。

#### C2. Auth 工具未在 API Registry 注册 — 破坏单事实源原则

- **文件对比**: `design/auth.md` §10.1 (MCP 工具一览，约 20 tools) vs `specs/reference/api-registry.md` §3.3 (仅 11 auth tools)
- **缺失工具清单** (auth.md §10.1 存在但 registry 未见):
  - `swarm_register_challenge` — PoW challenge 获取
  - `swarm_submit_csr` — CSR 提交流程
  - `swarm_renew_certificate` — 证书续签
  - `swarm_get_server_trust` — 服务器信任信息获取
  - `swarm_register_passkey` — passkey 注册
  - `swarm_recover_with_passkey` — passkey 恢复
  - `swarm_bind_email` — 邮箱绑定
  - `swarm_change_password` — 密码修改
  - `swarm_request_password_reset` — 密码重置请求
  - `swarm_confirm_password_reset` — 密码重置确认
  - `swarm_admin_create_password_reset` — 管理员恢复链接
  - `swarm_update_profile` — 修改显示名称
  - `swarm_delete_account` — 账号删除
  - `swarm_restore_account` — 账号恢复
  - `swarm_cancel_account_deletion` — 取消账号删除
  - `swarm_federated_login` — 联邦登录
  - `swarm_list_certificates` — 证书列表
  - `swarm_revoke_certificate` — 证书吊销
  - `swarm_token_refresh` — Web session 兼容续签
  - `swarm_auth_revoke` — session/certificate/key 吊销
- **问题描述**: API Registry 声称为"所有 API 合约的单一权威来源"（api-registry.md 行 5），但 ~20 个 auth 工具在设计文档 auth.md 中有详尽的参数/流程定义却未注册到 Registry。这意味着这些工具缺乏 canonical IDL 定义、RejectionReason 映射、security columns (required_scope, subject_source, replay_class, visibility_filter, rate_limit_key) 和 CI 校验覆盖。
- **影响分析**: 
  1. auth_api.idl.yaml 不完整 → codegen 无法为这些工具生成 SDK stub 和 server-side validation
  2. 这些工具的 security columns (replay class! rate limit!) 未声明 → 实现者可能遗漏防重放、限流或可见性过滤
  3. CI gate (`--check` mode) 无法检测 auth.md 与 IDL 的不一致
  4. 违反 D1/A 裁决的"单事实源"原则
- **修复建议**: 将所有 auth.md §10.1 列出的工具补充到 `auth_api.idl.yaml`，包含完整的 input/output schema、security columns、rate limits、replay class。重新生成 api-registry.md。特别关注 `swarm_submit_csr` 的 `non_idempotent_mutation` replay class 和 `swarm_admin_create_password_reset` 的 `admin_critical` 双签要求。

### High 问题

#### H1. Canonical Request Signature body_hash 规范化未定义 → 跨实现签名不匹配

- **文件**: `design/auth.md` §5.6c 行 373
- **行**: `body_hash: <blake3 canonical body hash>`
- **问题描述**: canonical request signature payload 包含 `body_hash`，但未定义"canonical body"是什么。JSON-RPC body 可以是多种序列化形式（缩进 vs 紧凑、key 顺序、Unicode 转义）。如果不指定 deterministic canonical form（如 RFC 8785 JSON Canonicalization Scheme 或简单 UTF-8 compact-sorted-keys），客户端和服务端可能计算不同的 `body_hash` → 签名验证失败。
- **影响分析**: 直接影响所有 canonical request 签名验证——认证失败或签名被绕过（若实现者做出不安全假设）。对于 MCP/HTTP API 是全覆盖影响。
- **修复建议**: 在 §5.6c Canonical 序列化规范中增加 body_hash 计算规则：
  1. JSON body: 使用 RFC 8785 JCS (JSON Canonicalization Scheme) 或 `serde_json::to_vec(&value)` 的确定性输出（需注明不保证 key 顺序时的替代方案）
  2. 无 body 请求: `body_hash = blake3("")` (已文档化，OK)
  3. 非 JSON body (binary upload): `body_hash = blake3(raw_bytes)`

#### H2. 恢复凭据双重 side-channel 缺口 — dummy argon2id + 常量时间声明不足

- **文件**: `design/auth.md` §17.1 行 1514-1516
- **行 1514**: `恢复凭据失败统一 invalid_credentials；不存在用户执行 dummy argon2id`
- **行 1515**: `响应时间侧信道: dummy argon2id 消除存在/不存在用户的时间差`
- **问题描述**: 设计依赖 dummy argon2id 消除用户存在性时序侧信道。但存在两个缺口：
  1. **argon2id 不是常量时间算法**：其内存访问模式受参数和输入影响，dummy vs real argon2id 的执行时间可能存在微妙差异（内存带宽、缓存命中率），尤其在共享主机/容器化环境中。文档声称"常量时间"但 argon2id 本身不提供此保证。
  2. **邮箱恢复的 dummy token 生成** (§11.1 Step 1)：对不存在邮箱"同样生成随机 token 并立即 discard（常量时间，防邮箱枚举时序差）"——生成 blake3 随机 token 几乎恒定，但 FDB 写入（真实用户）vs 丢弃（不存在用户）有可测量的 I/O 时间差。
- **影响分析**: 攻击者通过统计分析响应时间可能区分"用户存在（argon2id 真实计算 + FDB 写入）"和"用户不存在（dummy argon2id + 丢弃）"，实现用户名/邮箱枚举。对于注册 PoW 保护的场景（enabled 默认），攻击成本较高但非零。
- **修复建议**:
  1. 明确文档：argon2id dummy 验证**不声称常量时间**，而是声称"同等参数、同等内存分配"——在 §17.1 中将"常量时间"改为"固定参数等时近似"。补充说明：在共享 CPU/缓存环境中无法完全消除时序差，但通过固定 worker pool（每个验证使用固定线程、固定内存分配）降低可观察性。
  2. 邮箱恢复 dummy 路径：对不存在用户也写入 FDB（一个 `auth/reset_dummy/<random>` 带短 TTL 的记录），确保 I/O 成本对称。
  3. 考虑在注册/恢复端点引入随机抖动（±10ms），进一步降低时序信噪比（在 per-IP 限流已保护的前提下）。

#### H3. 联邦 CRL fallback 默认值偏向可用性 → 可能接受过期吊销信息

- **文件**: `design/auth.md` §15.2a 行 1350-1353
- **行 1350-1353**:
```
[auth.federation.default_policy]
revocation_fallback = "reject_for_code_and_login"  # R27 ML-10
```
- **问题描述**: 配置示例中 `revocation_fallback = "reject_for_code_and_login"` 是正确的（也是 R27 ML-10 裁决结果），但文档中还有 `revocation_fallback` 策略表包含 `allow_with_warning`（行 1398），标注为"仅用于低风险世界"。这个 per-world 可选值**无强制门控**——服主可能误配置 `allow_with_warning` 到生产环境，导致 CRL 同步失败时仍接受已吊销的联邦证书。
- **影响分析**: 若服主错误配置 `allow_with_warning`，CRL 同步中断时已吊销的联邦身份仍可登录甚至部署代码。对 federation trust model 构成高风险。
- **修复建议**: `allow_with_warning` 应在 `world.toml` 验证阶段强制要求额外确认——`world.mode` 必须为 `development` 或显式声明 `accept_stale_federation_crl_risk = true`（类似 Intermediate CA 文件密钥的 accept 声明，auth.md 行 136）。生产模式拒绝此配置并输出明确错误。将此约束补充到 §15.2a 的 `revocation_fallback` 策略表。

#### H4. Admin 高权限 challenge-response 缺少 FDB CAS 原子性显式声明

- **文件**: `design/auth.md` §10.8 行 914-914
- **行 914**: `高价值操作（admin 证书签发、恢复流程、Admin MCP 工具）使用 challenge-response nonce，nonce 消费在 FDB 事务内原子执行`
- **问题描述**: 文档描述了 admin challenge-response 的 CAS 语义（`auth/admin_nonce_counter/<admin_id>` 单调递增），但未显式声明 CAS 失败时的行为——事务冲突是否回滚整个 admin 操作？重试策略是什么？如果 CAS 成功但后续 FDB 写入失败（同一事务内），计数器是否已递增？文档说"计数器若已被递增（重放）则事务冲突回滚，拒绝操作"，但未覆盖"CAS 成功 + 事务内其他操作失败"的边界情况。由于所有操作在同一 FDB 事务内（`FDB 事务内原子 CAS`），FDB 原子性保证全或无——这是一个文档清晰度问题而非实现缺陷。
- **影响分析**: 低（FDB 事务原子性天然覆盖），但安全关键路径的文档模糊性可能引导实现者使用非事务性 CAS。
- **修复建议**: 在 §10.8 增加一行明确声明：`CAS 递增与 admin 操作效果在同一 FDB 事务内——任何步骤失败导致整体回滚，计数器不递增。计数器值仅在完整事务 COMMIT 后持久化。` 

### Medium 问题

#### M1. Refresh Token Rotation Grace Period 60s 窗口 — 旧 token 仍可被滥用

- **文件**: `design/auth.md` §14.1 行 1282-1284
- **行 1282**: `旧 token 在 rotation 后 60s 内仍可被接受一次（grace period，防竞态）`
- **问题描述**: 60s grace period 允许刚被轮换的旧 refresh_token 仍可使用一次。若攻击者在 rotation 后 60s 内使用窃取的旧 refresh_token（从不同 IP），可以获得新 access token，随后触发 `session family revoke`。但攻击者已获得短期访问权限（15min access token），足够执行恶意操作。
- **影响分析**: 提供了合理的竞态防护（网络延迟、重试），但 60s 对攻击者太长。受信设备（持有有效证书）的 grace 已缩短至 10s，但证书过期的设备仍依赖 60s。
- **修复建议**: 考虑将非受信设备的 grace 缩短至 15-30s（足够覆盖 TCP 重传 + 浏览器刷新，但不给攻击者足够操作窗口）。或设计为：grace 窗口期内旧 token 只能换取一个"仅限 token 校验"的响应，不签发新 access token（仅告知"rotation 已完成，请用新 token"）。

#### M2. CSR 准入控制 — L3 per-ASN 限流 vs per-IP 限流数值不一致

- **文件**: `design/auth.md` §5.2 多层准入链 (行 259-268) vs §10.7 CSR Admission Control (行 878-890)
- **行 266**: L3 per-ASN `≤ 10/min（可配置）`
- **行 887**: L3 Per-ASN `50/min per ASN`
- **问题描述**: CSR admission control 表在两处给出的 per-ASN 值不一致（10/min vs 50/min）。前者是准入链（§5.2），后者是 Admission Control（§10.7）。同一攻击面的防御参数出现歧义。
- **影响分析**: 若按 50/min 实现（较宽松），分布式 botnet 可更高效绕过 per-IP 限流。ASN 级防御的强度取决于此值。
- **修复建议**: 统一为单一权威值。建议以 §10.7 的 50/min 为准（因为这是更详细的 Admission Control 章节），但需评估 50/min/ASN 是否过宽——典型家庭宽带 ASN 可能有数百独立 IP，50/min 意味着每个 IP 仅需 0.3/min 即可不触发 ASN 限流。

#### M3. WASM 编译缓存键未包含 wasmtime 语义版本

- **文件**: `specs/security/09-command-source.md` §3.5 行 134-136
- **行 134**: `blake3(wasmparser_version || validation_policy_version || wasmtime_build_commit || target_arch || security_epoch)`
- **问题描述**: 编译缓存键使用 `wasmtime_build_commit`（Git commit hash）而非 `wasmtime` 语义版本。如果通过 backport/cherry-pick 安全补丁而不改变 build commit（罕见但可能，如 distro 打包），缓存不会失效。另外 `wasmtime_build_commit` 依赖构建环境元数据，可能在不同构建间不稳定。
- **影响分析**: 低概率但高影响——若 wasmtime 安全补丁以非标准方式应用，已缓存的本机码可能使用有漏洞的 wasmtime 编译产物。
- **修复建议**: 缓存键增加 `wasmtime_version` 字段（来自 `wasmtime::VERSION` 常量），与 `wasmtime_build_commit` 并存。确保任一变更都导致缓存失效。

#### M4. 浏览器证书 IndexedDB 存储 + XSS 攻击面

- **文件**: `design/auth.md` §14.3 行 1295
- **行 1295**: `certificate: 使用 IndexedDB 存储（仅作缓存，不构成独立认证根——所有认证请求仍需完成签名绑定）`
- **问题描述**: IndexedDB 可被 XSS 读取（不同于 HttpOnly cookie）。虽证书不构成独立认证根（需要 WebCrypto non-extractable key 签名），但暴露证书链和 certificate_id 本身就是信息泄露——攻击者可利用这些信息发起钓鱼、社会工程或结合其他漏洞。
- **影响分析**: 中等——XSS 仍是 Web 应用的常见漏洞类型。Swarm 的玩家原创字符串（drone 名称、回放描述）以及代码编辑器（Monaco）渲染是天然的 XSS 攻击面。
- **修复建议**: 文档明确：CSP 策略必须包括 `script-src 'self'` + nonce/hash + `'strict-dynamic'`；Monaco editor 渲染玩家内容时使用 sandboxed iframe；IndexedDB 中证书存储不作为 XSS 后的恢复路径（XSS 后必须假设所有 client-side secret 已泄露并触发证书轮换）。

### Low 问题

#### L1. 账号删除时 in-transit 资源处置缺少时序保证

- **文件**: `design/auth.md` §13.1 行 1198-1202
- **行 1198-1202**: `in-transit 资源处置: 进行中的 cargo transfer 立即取消...以上操作与资产处置在同一 tick 原子执行`
- **问题描述**: "同一 tick 原子执行" 的语义正确，但 "cargo_in_transit" 的定义未在文档中明确——是 ECS 组件还是 FDB 中的独立记录？取消时的回退路径（资源退回源 depot）依赖源 depot 在删除时仍存在。若源 depot 在删除前已被摧毁（战斗），回退逻辑可能遇到 dangling reference。
- **影响分析**: 极边缘情况（账号删除发生在战斗摧毁 depot 的同一 tick 内）。
- **修复建议**: 文档补充：`若源 depot 不存在（已被摧毁或回收），in-transit 资源进入世界丢弃池，记录 WARN 审计日志。`

#### L2. Replay verifier 依赖对象存储 blob 但 blob 可为 pending

- **文件**: `specs/core/05-persistence-contract.md` §2.2 行 61-63 + §3 行 177-178
- **行 177-178**: `pending / uploading → 等待最多 30s 后重试；超时则降级为 failed`
- **问题描述**: replay verifier 查询 `tick_manifest.upload_status`，对于 pending/uploading 状态等待最多 30s。但如果 replay verifier 在 CI 中运行（无交互等待能力），30s 等待是不可接受的。此外，若 blob upload 持续失败（后端存储故障），所有 replay tick 均为 audit_gap → 反作弊审计能力完全丧失。
- **影响分析**: 低——这是 persistence 层的可用性问题而非安全缺陷。但反作弊审计依赖 replay 可用性。
- **修复建议**: 文档中补充：replay verifier 应有一个 `max_blob_wait_seconds` 配置参数（默认 30s，CI 中可设为 0 跳过 pending tick）；持续 blob upload 失败超过阈值应触发 operator alert。

#### L3. Tutorial 来源缺少正式的 Replay Class 声明

- **文件**: `specs/security/09-command-source.md` §2.1 vs §2.2 行 23, 34
- **行 23**: Tutorial source 在核心来源矩阵中
- **行 34**: Tutorial source 在扩展来源矩阵中重复出现
- **问题描述**: Tutorial 来源在两处定义（§2.1 基础 + §2.2 扩展），但 replay class 未在任何一处声明——`WASM` 有 `fuel budget`，`MCP_Deploy` 有 `deploy_mutation`，`Admin` 有 `admin_critical`，但 Tutorial 的指令应归类为什么 replay class？Tutorial 指令走 `validate_and_apply()` 还是独立路径？
- **影响分析**: 低——Tutorial 世界与正式世界隔离，但 replay 审计和命令验证管线的确定性要求覆盖所有 source。
- **修复建议**: 移除 §2.2 中的重复 Tutorial 条目（或合并为引用 §2.1），并在 §2.1 的 Tutorial 行增加 replay_class 列（建议 `idempotent_mutation` 或专用 `tutorial_instruction` class）。

---

## 3. 亮点

1. **用途隔离证书模型** (auth.md §5.3): `ClientAuthCertificate` / `CodeSigningCertificate` / `AdminCertificate` / `FederationCertificate` 四类证书按用途严格隔离——认证凭据不能用于签名代码、代码签名凭据不能执行管理操作。这是纵深防御的核心支柱，比单一证书 + scope 的模型更安全。

2. **Oracle 防线系统化闭合** (05-visibility.md §10): `NotVisibleOrNotFound` 统一拒绝码、`omitted_count` 分桶脱敏、特殊攻击拒绝码等价类策略（§10.4）——系统性地消除了通过不同错误码推断隐藏信息的 side-channel。这是同类设计中较少见的完整性。

3. **WASM 沙箱四层隔离** (04-wasm-sandbox.md §4 + §9): Wasmtime fuel/epoch + seccomp BPF + cgroup v2 + namespace 隔离 + 统一 OS 加固 checklist。部署前 CI 验证禁止的系统调用返回 EPERM 而非 ENOSYS（防 fallback）。这是教科书级别的沙箱设计。

4. **FDB replay-critical subset 显式声明** (05-persistence-contract.md §2.1): 10 字段清单明确标识哪些是 replay 必需的（FDB 原子提交）、哪些是 debug/rich（可降级、可丢失）。消除了"FDB 事务内写一切"与"跨存储双写会炸"之间的模糊地带。

5. **CVE-SLA 确定性回归测试要求** (CVE-SLA.md §5): 对 crypto/security crates（blake3, ed25519-dalek, ring, rustls）升级后强制 determinism regression test——验证同一 tick 输入产生相同的 hash/signature/TLS handshake 结果。这在实时系统安全补丁流程中罕见且关键。

6. **AI Agent 凭据安全交付** (auth.md §4.3): Agent 代理注册返回"一次性 handoff code / 导入链接"而非裸 refresh_token 或私钥明文。聊天日志不会泄露长期凭据。这是 AI agent 场景专用的安全设计，业界少见。

7. **Deferred Command Model 的编译期 enforce** (09-command-source.md §2.3): `WorldMutate` trait 的唯一实现者是 `validate_and_apply()`——任何试图直接持有 `&mut World` 的代码产生编译错误。Admin 路径无绕过——编译期保证安全边界。

---

## 4. CrossCheck

以下问题需要跨方向验证——标注目标方向供 Speaker/Phase 2 协调：

- **CX-1: WS MAC payload 不一致** (C1) → 建议 **Interface** 方向确认 WS 协议规范的最终版本，**Engine** 方向确认实现侧遵循的格式。需要单文档裁决 (auth.md vs 03-mcp-security.md)。

- **CX-2: Auth 工具 IDL 注册缺失** (C2) → 建议 **API Registry** 方向（由 IDL 维护者）补齐 `auth_api.idl.yaml` 中缺失的工具定义。**Engine** 方向确认实现侧是否已有这些工具的 handler（可能已有代码但缺 IDL）。需要检查 CI codegen 是否已检测到此缺口。

- **CX-3: body_hash 规范化方案** (H1) → 建议 **Interface** 方向确认 JSON canonicalization 策略（RFC 8785 vs 项目自定义）。**SDK** 方向需同步实现 canonical body hash。涉及跨语言 (Rust/Go/TypeScript/Python) 一致性。

- **CX-4: WASM 编译缓存键** (M3) → 建议 **Sandbox** 方向确认缓存键是否需要 wasmtime 语义版本。**CI/Infra** 方向确认构建流程中 `wasmtime_build_commit` 的可靠性。

- **CX-5: 联邦 CRL fallback 安全配置** (H3) → 建议 **Auth** 方向补充 world.toml 验证逻辑。**Operations** 方向确认 runbook 中是否已包含 CRL 同步失败告警。

- **CX-6: Per-ASN 限流值不一致** (M2) → 建议 **Auth** 方向统一 CSR admission control 数值（§5.2 vs §10.7）。**Infra** 方向确认 ASN 解析方案和 IP-ASN 映射的准确性。

- **CX-7: Tutorial source replay class** (L3) → 建议 **Engine** 方向确认 Tutorial 指令的 replay 路径和 validate_and_apply 集成方式。**Gameplay** 方向确认 Tutorial 世界是否需要 replay 审计。