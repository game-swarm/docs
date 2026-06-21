# R32 Security 独立评审 — GPT-5.5

## 1. Verdict

REQUEST_MAJOR_CHANGES

理由：安全设计覆盖面很强，尤其在应用层证书、用途隔离、CSR admission、WASM sandbox、可见性 oracle 防线、CVE SLA 等方面已有成熟目标态。但当前文档仍存在多个“同一安全合同多处互相冲突”的阻塞问题：Agent/CLI transport audience 不一致、CSR/Admin 限流在同一文档内互相否定、WebSocket 消息签名 payload 冲突、WASM sandbox 网络命名空间语义自相矛盾、持久化 replay-critical 语义与 deploy blob hash 语义不一致。这些问题会直接诱导实现者选择较弱或错误路径，必须在设计层闭合后才能通过。

## 2. 发现的问题

### S-H1 — High — Agent/CLI audience 枚举与示例冲突，可能导致跨 transport 重放或拒绝合法请求

- 文件引用：`/tmp/swarm-review-R32/specs/security/03-mcp-security.md:51`
- 文件引用：`/tmp/swarm-review-R32/specs/security/03-mcp-security.md:108`
- 文件引用：`/tmp/swarm-review-R32/specs/security/03-mcp-security.md:114`
- 文件引用：`/tmp/swarm-review-R32/specs/security/09-command-source.md:191`
- 文件引用：`/tmp/swarm-review-R32/design/auth.md:113`
- 文件引用：`/tmp/swarm-review-R32/design/auth.md:939`

问题描述：
- MCP 安全文档的证书格式示例将 audience 写为 `swarm-aud-v1:<transport>:...`，Browser endpoint 使用 `browser-ws`，AI/CLI endpoint 使用 `cli-rest`。
- Command Source 明确 MCP(Agent) audience 为 `agent-mcp`，REST 为 `cli-rest`。
- Auth 文档的 `issue_certificate_bundle` 示例固定为 `cli-rest`，但同文档后文 audience 枚举又包含 `agent-mcp`、`cli-rest`、`browser-ws` 等。
- 因此 Agent MCP、CLI REST、Browser WS 的最终 audience 绑定关系不唯一。

影响分析：
- audience 是防跨 transport 重放的核心字段。如果 Agent MCP 与 CLI REST 混用 `cli-rest`，攻击者可能把一个 transport 上的签名请求重放到另一个 endpoint，或实现者为了兼容放宽 audience 精确匹配。
- 如果不同实现选择不同枚举，合法客户端会被错误拒绝；更糟糕的是网关可能为兼容接受多个 audience，从而削弱 §5.7/§7.0 的精确匹配安全保证。

修复建议：
- 统一定义唯一 transport 枚举，并在所有示例和 schema 中引用同一表：建议 `browser-http`、`browser-ws`、`agent-mcp`、`cli-rest`、`replay-viewer`。
- `issue_certificate_bundle` 不应示例固定 `cli-rest`，应声明由目标 endpoint profile 决定，Agent MCP 证书必须使用 `agent-mcp`。
- 在 API Registry/Auth IDL 中将 `audience_transport` 设为枚举字段并由 CI 校验，不允许文档手写分叉。

### S-H2 — High — CSR admission control 在同一 Auth 文档内自相矛盾，削弱注册 DoS 防线

- 文件引用：`/tmp/swarm-review-R32/design/auth.md:263`
- 文件引用：`/tmp/swarm-review-R32/design/auth.md:264`
- 文件引用：`/tmp/swarm-review-R32/design/auth.md:265`
- 文件引用：`/tmp/swarm-review-R32/design/auth.md:266`
- 文件引用：`/tmp/swarm-review-R32/design/auth.md:267`
- 文件引用：`/tmp/swarm-review-R32/design/auth.md:878`
- 文件引用：`/tmp/swarm-review-R32/design/auth.md:884`
- 文件引用：`/tmp/swarm-review-R32/design/auth.md:885`
- 文件引用：`/tmp/swarm-review-R32/design/auth.md:886`
- 文件引用：`/tmp/swarm-review-R32/design/auth.md:887`
- 文件引用：`/tmp/swarm-review-R32/design/auth.md:888`
- 文件引用：`/tmp/swarm-review-R32/design/auth.md:978`

问题描述：
- §5.2 的多层准入链要求 CSR 有 per-IP `≤1/30s`、per-ASN `≤10/min`、global semaphore `≤min(cpu_cores,4)`、queue `≤100`。
- §10.7 的 CSR Admission Control 改为 per-IP `10/min`、per-ASN `50/min`、global in-flight `100`、queue `500`。
- §10.8 “未认证端点保护”又写 CSR 提交为“PoW 自身限速，无额外 IP 限制”。

影响分析：
- 这是注册/证书签发入口，属于典型 OWASP API4/API7 风险面。PoW 只能增加单请求成本，不能替代来源限流和全局并发控制；文档末尾的“无额外 IP 限制”会直接允许攻击者以并发 PoW 结果打爆 CSR 签发队列、HSM/KMS 签名额度或 Auth Service CPU。
- 不同实现者可能选择更宽松的 `10/min + queue 500 + no IP limit`，导致实际 DoS 防线不满足前文安全目标。

修复建议：
- 设立单一 CSR Admission Control 权威表，删除或改写其它重复表。
- 建议最终态至少保留：PoW、per-IP token bucket、per-ASN/网络段 bucket、global signing semaphore、bounded queue、challenge issuance rate limit、audit throttle。
- 明确所有未认证端点都必须有来源限流；`CSR 提交` 不得写成 “PoW 自身限速”。

### S-H3 — High — Admin 高权限操作限流/双签语义冲突，可能造成管理面 DoS 或越权恢复

- 文件引用：`/tmp/swarm-review-R32/specs/security/09-command-source.md:20`
- 文件引用：`/tmp/swarm-review-R32/specs/reference/api-registry.md:270`
- 文件引用：`/tmp/swarm-review-R32/specs/reference/api-registry.md:353`
- 文件引用：`/tmp/swarm-review-R32/specs/reference/api-registry.md:354`
- 文件引用：`/tmp/swarm-review-R32/specs/reference/api-registry.md:355`
- 文件引用：`/tmp/swarm-review-R32/specs/reference/api-registry.md:356`
- 文件引用：`/tmp/swarm-review-R32/specs/reference/api-registry.md:357`
- 文件引用：`/tmp/swarm-review-R32/design/auth.md:840`
- 文件引用：`/tmp/swarm-review-R32/design/auth.md:846`
- 文件引用：`/tmp/swarm-review-R32/design/auth.md:848`
- 文件引用：`/tmp/swarm-review-R32/design/auth.md:980`

问题描述：
- Command Source 来源矩阵把 `Admin` 的 `rate_limit` 写为“无限制”。
- API Registry 对 Admin category 写通用 `10/h`，单项 admin 工具又有 `5/min`、`10/h`、`5/h`、`30/tick` 等限制。
- Auth 文档的 Admin 高权限操作要求部分操作双签和 cooldown，但 “未认证端点保护” 表又写 Admin 恢复链接“认证后无额外限制”。
- Admin recovery link 行只要求 AdminCertificate + 目标用户邮箱验证，而不是显式双签；同表还写 cooldown “无（用户触发）”。

影响分析：
- Admin 是最高权限面，不能存在“无限制”或“认证后无额外限制”的设计语义。攻击者一旦获得 AdminCertificate，或内部管理员账号被滥用，可能批量生成恢复链接、批量吊销证书、频繁 world config 热更新或 force GC，形成管理面 DoS 或账号接管扩大化。
- 文档冲突会使 gateway/schema 实现无法判断哪些 admin 操作需要双签、idempotency key、cooldown、审计和 rate limit。

修复建议：
- 删除 Command Source 中 Admin `无限制`，改为引用 API Registry/Auth Admin policy 的具体 rate limit。
- 对 `swarm_admin_create_password_reset`、CA/trust policy、epoch bump、batch revoke、world config hot update 定义强制双签或 step-up authentication、per-target cooldown、global cap、idempotency key、审计字段。
- `Admin 恢复链接` 不应“认证后无额外限制”；至少需要 per-admin、per-target、global 限流和不可重放 challenge。

### S-H4 — Medium — WebSocket 每消息签名 payload 在同一文件内前后不一致，tick 绑定可能被实现遗漏

- 文件引用：`/tmp/swarm-review-R32/specs/security/03-mcp-security.md:160`
- 文件引用：`/tmp/swarm-review-R32/specs/security/03-mcp-security.md:163`
- 文件引用：`/tmp/swarm-review-R32/specs/reference/api-registry.md:433`
- 文件引用：`/tmp/swarm-review-R32/specs/reference/api-registry.md:437`
- 文件引用：`/tmp/swarm-review-R32/design/auth.md:812`
- 文件引用：`/tmp/swarm-review-R32/design/auth.md:814`
- 文件引用：`/tmp/swarm-review-R32/design/auth.md:815`
- 文件引用：`/tmp/swarm-review-R32/design/auth.md:822`
- 文件引用：`/tmp/swarm-review-R32/design/auth.md:823`

问题描述：
- MCP 安全文档说每条消息签名覆盖 `SWARM-WS-MSG-V1\n<seq>\n<body_hash>`，但 API Registry 说 MAC 覆盖 `(seq, tick, payload)` 或 request signature 覆盖 `(method, uri, timestamp, seq, body_hash)`。
- Auth 文档 §10.5a 先要求 MAC payload 包含 `<seq>\n<tick>\n<body_hash>`，紧接着重复 bullets 又写成 `<seq>\n<body_hash>`，遗漏 tick。

影响分析：
- tick 绑定是防跨 tick 消息重放的重要语义。若实现者采用后一个简化 payload，攻击者可在同一 WS 会话或重连窗口内重放旧 tick 的只读/调试/部署相关消息，造成状态混淆或审计误归因。
- 不同 SDK/服务端生成签名输入不一致也会导致互操作失败，常见修补方式是接受多个签名格式，进一步扩大攻击面。

修复建议：
- 指定唯一 canonical WS message signature：建议 `SWARM-WS-MSG-V1\n<direction>\n<session_id>\n<seq>\n<tick>\n<body_hash>`。
- 删除所有旧格式描述；将 WS handshake signature 与 per-message signature 分开命名。
- 在 API Registry/IDL 中加入机器可读 `ws_signature_payload_fields`，并要求 SDK fixture 覆盖。

### S-H5 — Medium — WASM sandbox 网络隔离表述自相矛盾，可能误配置为共享宿主网络

- 文件引用：`/tmp/swarm-review-R32/specs/core/04-wasm-sandbox.md:24`
- 文件引用：`/tmp/swarm-review-R32/specs/core/04-wasm-sandbox.md:264`
- 文件引用：`/tmp/swarm-review-R32/specs/core/04-wasm-sandbox.md:266`
- 文件引用：`/tmp/swarm-review-R32/specs/core/04-wasm-sandbox.md:389`
- 文件引用：`/tmp/swarm-review-R32/specs/core/04-wasm-sandbox.md:390`
- 文件引用：`/tmp/swarm-review-R32/specs/security/03-mcp-security.md:124`
- 文件引用：`/tmp/swarm-review-R32/specs/security/03-mcp-security.md:126`

问题描述：
- sandbox 架构图写 “无网络命名空间”，容易理解为没有启用 network namespace、因此共享宿主网络命名空间。
- 同文 §4.3 又写 “sandbox 进程无网络命名空间。与引擎通过 Unix domain socket 通信”。
- 但 OS 加固 Checklist 又要求 `net` 为“独立网络栈”，并用 `ip netns list` 验证“无网络接口”。MCP 安全文档也要求 container 网络隔离、禁止 `--network=host`。

影响分析：
- 对 sandbox 来说，共享宿主 netns 即使 seccomp 禁止 socket，也不是等价安全边界；Wasmtime/JIT/seccomp 漏洞、允许 syscall 漏洞或将来 relaxed/dev 配置可能把网络访问面暴露给恶意 WASM。
- “无网络命名空间”与“独立网络栈”是相反含义，会直接导致部署者误配置。

修复建议：
- 将所有“无网络命名空间”改为“独立 network namespace，且 namespace 内无外部网络接口；仅预先传入 Unix domain socket fd”。
- Checklist 应明确验证 `/proc/self/ns/net` 与宿主不同、无 default route、无 non-loopback interface、socket syscall 被 seccomp 禁止。
- 若确实设计为不创建 netns，则必须给出风险接受；但安全目标态建议使用独立 netns。

### S-H6 — High — Persistence replay-critical 与 object store/replay 语义冲突，可能削弱部署完整性和审计可靠性

- 文件引用：`/tmp/swarm-review-R32/specs/core/05-persistence-contract.md:53`
- 文件引用：`/tmp/swarm-review-R32/specs/core/05-persistence-contract.md:55`
- 文件引用：`/tmp/swarm-review-R32/specs/core/05-persistence-contract.md:65`
- 文件引用：`/tmp/swarm-review-R32/specs/core/05-persistence-contract.md:80`
- 文件引用：`/tmp/swarm-review-R32/specs/core/05-persistence-contract.md:81`
- 文件引用：`/tmp/swarm-review-R32/specs/core/05-persistence-contract.md:98`
- 文件引用：`/tmp/swarm-review-R32/specs/core/05-persistence-contract.md:115`
- 文件引用：`/tmp/swarm-review-R32/specs/core/05-persistence-contract.md:118`
- 文件引用：`/tmp/swarm-review-R32/specs/core/05-persistence-contract.md:156`
- 文件引用：`/tmp/swarm-review-R32/specs/core/05-persistence-contract.md:170`
- 文件引用：`/tmp/swarm-review-R32/specs/core/05-persistence-contract.md:173`
- 文件引用：`/tmp/swarm-review-R32/specs/reference/api-registry.md:878`
- 文件引用：`/tmp/swarm-review-R32/specs/reference/api-registry.md:888`

问题描述：
- Persistence §2.2 声明 object store 仅承载 RichTraceBlob，不存放 replay-critical 数据，blob 缺失绝不导致 unreplayable。
- Deploy 状态机却要求异步上传 WASM binary，activation_tick 到达时必须 `upload_status == complete AND module_hash 验证通过` 才 ACTIVE；blob 缺失会导致部署 FAILED。
- Tick Commit Phase C 失败处理又写 blob 缺失“该 tick replay 不可用”，上传状态表也写 `pending/failed` 为“replay 不可用”。
- API Registry 进一步写 `Blob 缺失不影响 deterministic replay`，但 `permanent failure → deploy rejected`。

影响分析：
- WASM binary 是否 replay-critical 没有被一致建模。若 replay verifier 需要重放部署激活、模块 hash、terminal_state 或审计某个恶意模块，缺失的 WASM blob 可能影响安全审计；若不需要，则文档不能同时说 replay 不可用。
- 部署链路存在 TOCTOU 风险：在 FDB manifest commit 与 object store upload complete 之间，系统已记录 deploy intent，但 blob 缺失/替换/延迟会影响下一 tick 激活。虽然有 module_hash 校验，但 replay/security contract 没有明确 `compiled_module_hash`、`wasm_binary_hash`、`object_store_key` 哪些字段进入 FDB replay-critical 子集。

修复建议：
- 将 object store blob 分类拆开：`RichTraceBlob` 非 replay-critical；`wasm_module_blob` 对未来重新执行/安全审计是否 replay-critical 必须明确。
- 若设计目标是 replay 不依赖 WASM blob，则 FDB TickCommitRecord 必须包含部署激活结果、module hash、terminal_state、commands_hash，且 replay verifier 明确不重新执行 WASM，只验证记录链；同时把“replay 不可用”改为“rich audit unavailable”。
- 若设计目标要求可重新执行/重新审计 WASM，则 WASM blob 可用性或可恢复性必须进入 replay-critical SLA，并不能声称 object store 不存 replay-critical 数据。
- Deploy FDB manifest 应至少原子记录 `wasm_binary_hash`、`compiled_module_hash`、`object_store_key`、`upload_status`、`activation_tick`、`fdb_version_counter`、`signing_cert_id`、`validation_policy_version`。

### S-M1 — Medium — API Registry 活跃工具数量与链接锚点不一致，削弱安全矩阵可实施性

- 文件引用：`/tmp/swarm-review-R32/specs/reference/api-registry.md:254`
- 文件引用：`/tmp/swarm-review-R32/specs/reference/api-registry.md:932`
- 文件引用：`/tmp/swarm-review-R32/specs/security/03-mcp-security.md:223`

问题描述：
- API Registry §3 声明 `57` 个活跃 Game API 工具 + 11 Auth API 工具。
- 变更记录仍写 “MCP tools 总数为 56 active”。
- MCP 安全文档链接文字也写 “56 工具”。

影响分析：
- 工具总数本身不是安全漏洞，但安全矩阵、scope、rate limit、visibility filter 都依赖“全工具闭合”。数量不一致通常意味着至少一个工具未被正确纳入授权/限流/审计/可见性矩阵。

修复建议：
- 以 IDL 生成结果为唯一权威，修正 changelog 和引用文本。
- CI 增加 “工具总数、工具名集合、scope/rate/visibility 五列完整性” 检查，禁止 Markdown stale count。

### S-M2 — Medium — `NotEligible` 等拒绝码在可见性文档中使用但不在 RejectionReason Registry 注册

- 文件引用：`/tmp/swarm-review-R32/specs/security/05-visibility.md:403`
- 文件引用：`/tmp/swarm-review-R32/specs/security/05-visibility.md:409`
- 文件引用：`/tmp/swarm-review-R32/specs/security/05-visibility.md:410`
- 文件引用：`/tmp/swarm-review-R32/specs/reference/api-registry.md:127`
- 文件引用：`/tmp/swarm-review-R32/specs/reference/api-registry.md:156`

问题描述：
- Visibility 特殊攻击拒绝码等价策略使用 `NotEligible`。
- API Registry 的 canonical RejectionReason 列表没有 `NotEligible`；类似自身状态码示例 `Fatigued`、`OnCooldown`、`InsufficientEnergy` 也与 Registry 的 `CooldownActive`、`InsufficientResource` 规范不一致。

影响分析：
- Oracle 防线依赖统一拒绝码。未注册或别名拒绝码会导致实现者临时添加 wire enum，破坏 canonical RejectionReason 稳定性，也可能重新引入“目标存在但不可见”区分。

修复建议：
- 要么在 IDL/API Registry 中正式增加 `NotEligible` 并定义所有映射；要么将 Visibility 文档改为现有 canonical code，例如 `UnknownAction`/`SourceNotAllowed`/`CooldownActive` 的脱敏组合。
- 所有拒绝码必须以 API Registry 为准；安全文档不得发明未注册 wire code。

### S-L1 — Low — Recovery password 最小长度偏低且弱密码策略停留在小黑名单

- 文件引用：`/tmp/swarm-review-R32/design/auth.md:571`
- 文件引用：`/tmp/swarm-review-R32/design/auth.md:574`
- 文件引用：`/tmp/swarm-review-R32/design/auth.md:580`

问题描述：
- Recovery password 人类最小长度为 8 字符，弱密码黑名单仅 Top 10，并把 zxcvbn/HIBP 作为后续接入。

影响分析：
- 恢复密码是私钥丢失后的账号恢复入口，安全强度应高于普通登录密码。8 字符 + 小黑名单容易被 credential stuffing 或离线泄露后暴力破解放大风险。

修复建议：
- 目标态直接要求 ≥12 字符或 passphrase ≥4 words，接入 zxcvbn-style entropy score 或大规模常见密码库检查。
- 保持 argon2id、dummy PHC、per-IP/per-account/global semaphore；恢复流程默认启用 PoW。

## 3. 亮点

- 应用层证书模型方向正确：Swarm CA 不进入系统/浏览器 trust store，TLS/WebPKI 与 Swarm application certificate 分层清晰，降低了自托管 CA 被误用为通用 TLS 信任根的风险。
- 用途隔离证书设计成熟：`ClientAuthCertificate`、`CodeSigningCertificate`、`AdminCertificate`、`FederationCertificate` 区分 usage、scope、audience、TTL，能显著降低凭据横向滥用风险。
- CSR 防滥用思路完整：PoW、per-source limit、global semaphore、bounded queue、audit throttle、challenge 原子消费等要素齐全，只需消除冲突并指定唯一权威表。
- 请求签名与防重放覆盖较好：Canonical Request Signature、nonce、timestamp、version_counter、admin FDB CAS counter、CSR challenge consumption 分层设计合理。
- 可见性 oracle 防线有深度：`is_visible_to` 单函数、跨 snapshot/MCP/WS/REST/replay 统一过滤、`NotVisibleOrNotFound`、`omitted_count` 分桶、debug/simulate 脱敏都符合安全目标。
- WASM sandbox baseline 强：Wasmtime fuel、epoch interruption、WASI 文件/网络/时钟禁用、host function 白名单、seccomp/cgroup/namespace、恶意样本库、CVE SLA 均覆盖到位。
- 供应链响应设计具体：Wasmtime 和 critical Rust crates 的 CVE 分级、监控来源、patch/test/deploy/rollback 流程清楚，避免了“只写 cargo audit”但无响应闭环的问题。
- Deploy 签名链包含 `module_hash`、`metadata_hash`、`version_counter`、`world_id`、`module_slot` 和 CodeSigningCertificate，整体能够抵抗裸 WASM 替换和旧版本重放。

## 4. CrossCheck — 需要跨方向检查

- CX-1: Persistence 中 object store / replay-critical / deploy activation 的语义冲突 → 建议 Engine/Persistence 方向检查 TickCommitRecord、RichTraceBlob、WASM module blob、ReplayArtifact 的权威分层与 replay verifier 输入。
- CX-2: API Registry 工具数量、Auth 工具别名、MCP 安全文档链接文字不一致 → 建议 API/IDL 方向检查 codegen 输出、Markdown stale count、工具五列安全矩阵是否全量生成。
- CX-3: `NotEligible`、`Fatigued`、`OnCooldown`、`InsufficientEnergy` 等拒绝码与 canonical RejectionReason 不一致 → 建议 Gameplay/Command Validation 方向检查特殊攻击拒绝码等价类是否已在 IDL 注册。
- CX-4: Admin 命令走标准 `validate_and_apply()` 管线且 `WorldMutate` trait 唯一实现 → 建议 Engine 架构方向检查 Rust trait 边界是否能真正阻止 Admin/RuleMod 直接持有 `&mut World`。
- CX-5: `player_id` 使用 Blake3 低 64 bits 截断，碰撞概率被接受但账号创建时应有碰撞处理 → 建议 Auth/Identity 方向检查 FDB 唯一索引、collision retry/deny 策略和 federation mapping。
- CX-6: `public_spectate=true` 下 World 全地图延迟推送与 `replay_privacy` 过滤 → 建议 Gameplay/UX 方向检查 competitive world 的观战延迟、公开实体字段和策略信息泄露边界。
- CX-7: `sandbox.relaxed=true` 开发模式允许 `clock_gettime` 且声称“引擎仍覆盖返回值” → 建议 Sandbox/Determinism 方向检查 seccomp/WASI 层是否真的能覆盖 native syscall 返回，而非只覆盖 host function。
- CX-8: HSM/KMS signing、CRL cache、Auth Service epoch bump 与 Engine cache invalidation 的时序 → 建议 Infra/Ops 方向检查分布式缓存刷新、通知丢失、Arena 5s/World 60s 延迟接受旧证书的风险边界。
