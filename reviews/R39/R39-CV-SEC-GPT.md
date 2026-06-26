# R39-CV-SEC-GPT 安全评审报告

## 评审范围

- `/tmp/swarm-review-R39/design/auth.md`
- `/tmp/swarm-review-R39/specs/security/03-mcp-security.md`
- `/tmp/swarm-review-R39/specs/security/09-command-source.md`
- `/tmp/swarm-review-R39/specs/core/04-wasm-sandbox.md`

重点检查：认证链、CSR、transport 安全、WASM sandbox 边界。

## 总体结论

R39 在应用层证书、CSR、用途隔离、transport audience、WebSocket per-message 签名、WASM 沙箱 OS 边界等方面已有较完整安全设计。认证根与 TLS trust root 隔离、Auth/Gateway/Engine 职责分离、CodeSigningCertificate 与 ClientAuthCertificate 用途隔离、联邦 CRL fallback 默认趋严，方向正确。

但本轮仍存在 2 个 Blocker 与 3 个 High：主要是跨章节准入控制参数冲突、部署签名载荷中 `compiled_artifact_hash` 的权威归属混乱、WebSocket 握手 canonical payload 不一致、seccomp `clone/vfork` 语义冲突，以及浏览器 endpoint 的 token/certificate 签名边界未完全收敛。这些问题若进入实现，会导致安全控制被错误实现或跨 transport 重放/绕过。

## Blocker

### B1. CSR admission control 在同一文档内自相矛盾

**位置**：`design/auth.md` §5.2、§10.7、§10.8 未认证端点保护、附录 C

**问题**：

- §5.2 声明 CSR 提交有多层准入链：per-IP `≤ 1/30s`、per-ASN `≤ 10/min`、global semaphore、bounded queue。
- §10.7 的总表仍写 `CSR 提交` 的 Per IP 为 `—`，全局为“受 PoW 保护”。
- §10.8 “未认证端点保护”仍写 `CSR 提交 | PoW 自身限速 | 无额外 IP 限制`。
- Challenge 申请在 §10.7 文本写 `30/min per IP`，§10.8 表格和附录 C 写 `10/min per IP`。

**风险**：实现者可能按后文表格实现“CSR 仅 PoW，无额外 IP 限制”，直接绕过 R39 新增的 admission control。PoW 对分布式攻击不是速率限制，云 VM/botnet 可并行消耗 Auth CPU、队列和审计资源。

**建议修复**：

- 设定唯一权威表：建议以 §5.2 的多层准入链为权威。
- 删除或改写 §10.8 “CSR 提交 | PoW 自身限速 | 无额外 IP 限制”。
- §10.7 总表改为引用 §5.2，不再声明冲突数值。
- Challenge 申请统一为 `10/min per IP` 或 `30/min per IP`，并同步附录 C。

### B2. DeployPayload 把服务端计算的 `compiled_artifact_hash` 放入客户端签名载荷

**位置**：`specs/security/09-command-source.md` §3.1、§3.2、§3.3、§7.3；`specs/core/04-wasm-sandbox.md` §1、§7

**问题**：

- §3.1 明确说 `compiled_artifact_hash` 由服务端编译后计算，仅用于 runtime artifact/cache 完整性，不参与客户端代码签名。
- §3.2 的 `DeployPayload` JSON 又包含 `compiled_artifact_hash`，且说明 `signature` 是客户端 Ed25519 对上述字段签名。
- §7.3 又写 `compiled_artifact_hash 由服务端编译后计算，客户端不得自报`。

**风险**：签名边界不清会导致两类错误实现：

1. 服务端要求客户端签名 `compiled_artifact_hash`，但客户端无法在编译前知道该值，导致实现绕过或填空值。
2. 服务端接受客户端自报的 `compiled_artifact_hash`，污染编译缓存/运行时 artifact 绑定，给 cache poisoning 或审计错配留下空间。

**建议修复**：

- 将客户端签名载荷限定为 `SWARM-DEPLOY-V1`：`wasm_module_hash + metadata_hash + player_id + world_id + module_slot + version_counter + signed_at + audience`。
- `compiled_artifact_hash` 从 `DeployPayload` 中移除，只作为服务端编译完成后写入 deploy manifest 的字段。
- 在 `04-wasm-sandbox.md` 缓存键中明确：缓存键使用服务端生成的 `compiled_artifact_hash`，但 deploy acceptance 永远验证客户端签名的 `wasm_module_hash`。

## High

### H1. WebSocket 握手 canonical payload 在 auth 与 MCP spec 中不一致

**位置**：`design/auth.md` §10.5a；`specs/security/03-mcp-security.md` §2.5

**问题**：

- `design/auth.md` 仍写握手 canonical payload 为 `"SWARM-WS-V1\n<cert_id>\n<timestamp>\n<nonce>"`。
- `03-mcp-security.md` 使用更完整的 `SWARM-WS-HANDSHAKE-V1\n<transport>\n<server_id>\n<world_id>\n<cert_id>\n<timestamp>\n<nonce>\n<audience>`。

**风险**：若实现按较短 payload，握手签名未绑定 transport/server/world/audience，可能出现跨 world、跨 transport、跨 endpoint 的握手重放或协议混淆。

**建议修复**：以 `03-mcp-security.md` 的 `SWARM-WS-HANDSHAKE-V1` 为唯一格式，同步 `design/auth.md`，并要求握手签名必须覆盖 `transport=agent-ws`、`server_id`、`world_id`、`audience` 与 `cert_id`。

### H2. WASM sandbox seccomp 对 `clone/vfork` 的允许/禁止语义冲突

**位置**：`specs/core/04-wasm-sandbox.md` §4.1、§9.1、§9.2

**问题**：

- §4.1 允许 `clone (仅 CLONE_VM | CLONE_VFORK)`。
- §9.1 又写 `clone (仅 CLONE_VM | CLONE_VFORK)` 允许，但理由是 Wasmtime 内部线程创建；同表说 `fork/vfork` 禁止。
- §9.2 CI 验证要求 “PID 命名空间内 fork → 失败”。

`CLONE_VFORK` 语义接近 vfork，允许条件组合不严会扩大进程创建面。若真正需要线程，通常需要明确允许线程相关 flags，而不是宽泛允许 `CLONE_VFORK`。

**风险**：实现 BPF 时可能误放行进程创建或 vfork-like 行为，与 `pids.max`、无 exec、无文件系统组合后仍增加沙箱逃逸面与 DoS 面。

**建议修复**：

- 明确区分线程创建与进程创建：仅允许 Wasmtime 必需的线程 clone flags，禁止 `CLONE_VFORK`。
- 在 §4.1 与 §9.1 使用同一 syscall policy。
- CI 增加对 `clone` flags 的精确测试：线程所需 flags 可过，`fork/vfork/clone(CLONE_VFORK)` 必须 EPERM。

### H3. Browser endpoint 的证书签名路径与 token 兼容路径边界不够一致

**位置**：`design/auth.md` §10.5、§14.5；`specs/security/03-mcp-security.md` §2.1、§2.2、§3

**问题**：

- `design/auth.md` 表述 Web 端点可接受 certificate chain + signature 或 refresh_token 兼容模式，但所有敏感操作仍需证书链验证。
- `03-mcp-security.md` 的 Browser Web UI 主要描述 HTTPS + Origin/Host/CSRF/Fetch Metadata + token audience，未明确哪些 browser MCP 工具必须升级为 application certificate signature。
- `03-mcp-security.md` §3 又说 JWT/access_token 不用于 MCP/Agent 主认证路径，但 browser MCP 与 agent MCP 的边界在工具级授权矩阵中没有完全落表。

**风险**：实现可能把部分敏感 browser MCP 操作仅用 Web session/JWT 放行，弱化“唯一权威凭证是应用层证书链 + 用户私钥签名”的模型；也可能导致 browser-http 与 cli-rest audience 混淆。

**建议修复**：

- 在 API Registry 或 `03-mcp-security.md` 增加 per-tool auth mode：`web_session_ok`、`app_cert_required`、`admin_cert_required`。
- 明确 `swarm_deploy`、证书吊销、恢复确认、admin 操作、profile/security settings 等敏感操作在 browser 入口也必须使用 application certificate signature。
- 将 `browser-http` 加入 `design/auth.md` 的 audience transport 枚举与示例，避免全部 REST 示例默认为 `cli-rest`。

## Medium

### M1. Auth Service 架构描述仍出现 “Engine 内或独立服务” 歧义

**位置**：`design/auth.md` §3 架构图、§3.1 接口合同

**问题**：架构图中写 `src/auth/ (Engine 内或独立服务)`，但 §3.1 又强制 Auth Service 是独立进程，不与 Engine 共享内存。

**风险**：实现者可能先做 Engine 内嵌 Auth，破坏私钥、CSR、恢复流程与 Engine tick 热路径隔离。

**建议修复**：删除 “Engine 内或” 表述，统一为独立 Auth Service / 独立进程。

### M2. Admin 恢复链接请求参数缺少 `recovery_reason`

**位置**：`design/auth.md` §10.9、§11.3

**问题**：§10.9 要求管理员生成恢复链接时必须记录 `recovery_reason`，确认阶段以 token 记录为准；但 §11.3 的 `swarm_admin_create_password_reset` 示例参数只有 `username` 与 `reason`，没有 `recovery_reason`。

**风险**：实现者可能只记录自由文本 reason，确认阶段无法强制执行 `stolen-device/all-certs-lost` 等旧证书吊销策略。

**建议修复**：在 admin reset API 参数中显式加入枚举型 `recovery_reason`，并区分审计 `reason` 与策略 `recovery_reason`。

### M3. 联邦 CRL fallback 枚举仍有旧值残留

**位置**：`design/auth.md` §15.1、§15.2a、§15.6

**问题**：§15.1/§15.2a 新默认值为 `reject_for_code_and_login`，但 §15.6 仍描述旧默认 `reject_for_code`，并出现 `accept_login`，而 §15.2a 枚举表未列 `accept_login`。

**风险**：实现配置枚举不一致，导致联邦撤销失效时 login/code 的 fail-closed 策略不可预测。

**建议修复**：以 §15.2a 表为唯一枚举，删除或更新 §15.6 旧策略文字。

## Positive Findings

- 认证根设计合理：Server Root CA 离线、Intermediate CA 在线短期轮换、用途隔离证书、Swarm CA 不进入系统/浏览器 trust store。
- CSR 流程具备服务器权威 challenge/difficulty、CSR 签名验证、用途/scope/profile 策略检查与 FDB 原子消费。
- Transport 安全方向正确：Agent/CLI 不依赖 Origin，Browser 使用 Origin/Host/CSRF/Fetch Metadata，应用层 audience 精确绑定 transport/server/world/player。
- Command source 模型清晰：gameplay 默认仅来自 WASM，MCP Query/Deploy 不直接提交 gameplay 指令，服务端注入 actor/capability/scope。
- WASM sandbox 具备多层边界：Wasmtime fuel、Store reset、WASI 默认禁用、只读 host functions、seccomp、cgroup、独立 netns、只读 FS、CI boundary tests。

## 建议的修复顺序

1. 先修 B1/B2，避免实现 admission control 与代码签名边界走偏。
2. 同步 WebSocket handshake canonical payload，统一 `SWARM-WS-HANDSHAKE-V1`。
3. 收紧 seccomp `clone` policy，删除 `CLONE_VFORK` 放行。
4. 补齐 browser endpoint per-tool auth mode，避免 Web session 被误当权威凭证。
5. 清理 auth/联邦/admin recovery 的残留不一致描述。

## 评审结论

当前 R39 文档不建议直接冻结为实现依据。建议在合并前至少修复 B1、B2、H1、H2；H3 可与 API Registry 工具授权矩阵同步修复。修复后认证链、CSR、transport 与 sandbox 边界将具备较强的一致性和可实现性。
