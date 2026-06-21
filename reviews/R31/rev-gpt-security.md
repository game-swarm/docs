# R31 Clean-Slate Security Review — rev-gpt-security

## 1. Verdict

REQUEST_MAJOR_CHANGES

理由：设计整体安全意识很强，认证链、用途隔离证书、可见性、WASM sandbox、CVE SLA 都覆盖到了关键威胁面；但当前文档之间存在多处安全权威合同冲突，尤其是 CSR admission control、request nonce/replay 语义、audience/transport 绑定、API Registry 与 Auth 设计的工具/限制不一致。这些冲突会直接影响网关、Auth Service、MCP codegen 和 sandbox 实现，属于必须修复的重大问题。

## 2. 发现的问题

### S-H1 — CSR admission control 在同一文档内互相冲突，可能打开批量注册 / CA signing DoS 面

Severity: High

文件引用：
- `/tmp/swarm-review-R31/design/auth.md:862`
- `/tmp/swarm-review-R31/design/auth.md:869`
- `/tmp/swarm-review-R31/design/auth.md:871`
- `/tmp/swarm-review-R31/design/auth.md:875`
- `/tmp/swarm-review-R31/design/auth.md:956`
- `/tmp/swarm-review-R31/design/auth.md:962`

问题描述：
`design/auth.md` 的 CSR Admission Control 章节明确说 PoW 只是第一层成本过滤，不替代速率限制，并要求 Per-IP 10/min、Per-ASN 50/min、全局 in-flight cap、worker semaphore 和熔断机制。但同一文档后续“未认证端点保护”表又声明 `CSR 提交 | PoW 自身限速 | 无额外 IP 限制`。这不是措辞差异，而是对同一未认证高成本路径的相反安全合同。

影响分析：
CSR 提交会触发 PoW 验证、CSR 签名校验、证书签发路径，并可能使用 Intermediate CA/HSM/KMS 签名资源。若实现者按后者执行，分布式攻击者可以并行完成 PoW 后绕过 per-IP/per-ASN/全局并发限制，将 Auth Service、FDB challenge 事务或 CA signing worker 打满。该风险与 OWASP API4/API6/API10（资源消耗、无限制资源使用、安全配置错误）相符。

修复建议：
以 `design/auth.md:862-875` 的多层 admission control 为权威，删除或改写 `design/auth.md:956-963` 中“CSR 提交无额外 IP 限制”的条目。建议统一成：CSR submit = PoW + per-IP + per-ASN + global in-flight semaphore + bounded queue + audit throttle；challenge request 单独轻量限速；所有限制写入 API Registry/auth IDL 的机器可读 security columns，避免文档和 codegen 分叉。

### S-H2 — Nonce/replay 语义自相矛盾，可能导致已签名请求在缓存故障窗口内重放

Severity: High

文件引用：
- `/tmp/swarm-review-R31/design/auth.md:350`
- `/tmp/swarm-review-R31/design/auth.md:378`
- `/tmp/swarm-review-R31/design/auth.md:406`
- `/tmp/swarm-review-R31/design/auth.md:414`
- `/tmp/swarm-review-R31/design/auth.md:885`
- `/tmp/swarm-review-R31/design/auth.md:893`
- `/tmp/swarm-review-R31/design/auth.md:904`

问题描述：
Canonical request signature 对所有敏感请求携带 `Swarm-Nonce`，验证顺序要求 `nonce 未使用`；HTTP 不安全传输章节也说 nonce/timestamp 必须强制启用、重放窗口默认不超过 60 秒。但 Auth 热路径又规定普通 nonce 存在 Dragonfly SETNX TTL，崩溃语义为“TTL 窗口内可重放”，表格也写 MCP 查询请求在 Dragonfly TTL 窗口内可重放。

影响分析：
如果 Dragonfly 崩溃、failover 或数据丢失，攻击者可在 timestamp 窗口内重放已签名请求。对纯读请求影响可能有限，但文档中 nonce 机制被描述为通用 request signature 验证步骤，边界不够明确时容易被实现者用于 idempotent mutation 或准敏感读（例如 debug/profile/snapshot）路径。HTTP 场景本身不提供机密性，已签名流量更容易被观察和重放，因此该冲突会削弱应用层证书在不安全传输上的安全承诺。

修复建议：
明确分层：
1. `read_replay_safe` 可接受 Dragonfly nonce 丢失后的“最多 timestamp window 内重放”，但必须声明只允许无副作用且无额外信息泄露的读。
2. `idempotent_mutation`、`non_idempotent_mutation`、`deploy_mutation`、`admin_critical` 不得依赖 Dragonfly-only nonce，必须使用 FDB version counter、FDB one-time challenge 或 idempotency key 原子消费。
3. 将 HTTP 不安全传输章节的“重放窗口默认不超过 60 秒”与 nonce TTL 300s 统一，或者解释 timestamp window 与 Dragonfly TTL 的不同角色。
4. 在 API Registry 中为每个工具生成 replay_class → nonce strategy 的机器可读矩阵。

### S-H3 — Audience / transport 字符串存在多套语法，削弱跨协议重放防线

Severity: High

文件引用：
- `/tmp/swarm-review-R31/design/auth.md:113`
- `/tmp/swarm-review-R31/specs/security/03-mcp-security.md:51`
- `/tmp/swarm-review-R31/specs/security/03-mcp-security.md:91`
- `/tmp/swarm-review-R31/specs/security/03-mcp-security.md:108`
- `/tmp/swarm-review-R31/specs/security/09-command-source.md:191`
- `/tmp/swarm-review-R31/specs/security/09-command-source.md:192`
- `/tmp/swarm-review-R31/design/auth.md:921`
- `/tmp/swarm-review-R31/design/auth.md:923`

问题描述：
文档中 audience 语法至少出现三种形态：`swarm-aud-v1:swarm-alpha:world_v1:42`、`swarm-aud-v1:<transport>:<server_id>:<world_id>:<player_id>`、`agent-mcp`/`cli-rest`/`browser-http`/`browser-ws` 的 transport 枚举；MCP 文档还使用 `{gateway_origin, world_id, "browser"}` 作为 token aud 绑定描述。虽然后段 `design/auth.md:921-930` 给出了规范语法，但前文接口示例和其他安全规范仍保留旧/不同形式。

影响分析：
Audience 是防跨 transport / 跨协议重放的核心字段。若 Auth Service、Gateway、MCP endpoint 或 SDK/codegen 对 audience 的 parser/formatter 采用不同版本，可能出现 Agent certificate 被 Browser WS/REST 接受、CLI REST 证书被 MCP endpoint 接受、或 token 绑定粒度不一致的问题。该类漏洞历史上常见于 OAuth/OIDC audience confusion、JWT aud 校验不严格和 mTLS/application token 混用场景。

修复建议：
指定唯一权威语法并全局替换旧示例：`swarm-aud-v1:<transport>:<server_id>:<world_id>:<subject_id>`。所有证书、JWT token、DeployPayload、WS handshake、Canonical Request 都必须引用同一枚举表；禁止宽松匹配、别名和缺省 transport。建议把 transport enum 和 audience grammar 提升到 API Registry/auth IDL，文档只引用，不重新声明。

### S-H4 — Auth API Registry 与 Auth 设计的工具名、TTL、限流和权限模型不一致，可能导致 codegen 暴露错误能力面

Severity: High

文件引用：
- `/tmp/swarm-review-R31/specs/reference/api-registry.md:379`
- `/tmp/swarm-review-R31/specs/reference/api-registry.md:385`
- `/tmp/swarm-review-R31/specs/reference/api-registry.md:401`
- `/tmp/swarm-review-R31/specs/reference/api-registry.md:402`
- `/tmp/swarm-review-R31/specs/reference/api-registry.md:403`
- `/tmp/swarm-review-R31/specs/reference/api-registry.md:621`
- `/tmp/swarm-review-R31/specs/reference/api-registry.md:624`
- `/tmp/swarm-review-R31/design/auth.md:690`
- `/tmp/swarm-review-R31/design/auth.md:694`
- `/tmp/swarm-review-R31/design/auth.md:706`
- `/tmp/swarm-review-R31/design/auth.md:1256`
- `/tmp/swarm-review-R31/design/auth.md:1261`

问题描述：
API Registry 声明 auth_api 只有 11 个工具，且包含 `swarm_auth_cert_issue` 这类 admin 证书签发工具；`design/auth.md` 则列出完整账号生命周期工具（register challenge、submit CSR、password reset、passkey、account deletion、federated login 等）。API Registry 中 refresh token lifetime 为 7d，而 Auth 设计中为 30d。Registry 的 `swarm_auth_cert_issue` schema 允许 admin 提交 `{subject, san_dns_names, san_ip_addresses, validity_days, key_type}` 并签发证书，但 Auth 设计强调 CSR、新私钥持有证明、用途隔离和管理员不得生成用户私钥/代签 CSR。

影响分析：
API Registry 明确标注“单一权威来源”和 codegen 来源。如果 codegen 按 Registry 暴露 11 个 auth tools，而实现团队按 Auth 设计实现更完整生命周期，MCP SDK、Gateway authz、审计和限流会分叉。更严重的是，`swarm_auth_cert_issue` 若被实现为通用 admin 证书签发入口，可能绕过 CSR 持有证明和恢复流程，形成高权限证书滥发面。

修复建议：
立即统一 Auth API 的机器权威：
1. 将 `design/auth.md` 的完整 auth lifecycle 工具纳入 `auth_api.idl.yaml` / API Registry，或明确哪些是 REST-only、哪些是 MCP tool。
2. 将 `swarm_auth_cert_issue` 限定为 CA 运维/服务证书用途，禁止为玩家签发 ClientAuth/CodeSigning/AdminCertificate，或要求输入 CSR + proof_signature + policy gate。
3. 统一 refresh token TTL（7d vs 30d）、session cap、lockout 等安全限制。
4. 所有 auth tools 必须带 required_scope、replay_class、rate_limit_key、admin dual-sign requirement、CSR/proof requirement。

### S-M1 — WebSocket 握手与通用请求签名参数不一致，易造成实现分叉

Severity: Medium

文件引用：
- `/tmp/swarm-review-R31/design/auth.md:350`
- `/tmp/swarm-review-R31/design/auth.md:355`
- `/tmp/swarm-review-R31/design/auth.md:356`
- `/tmp/swarm-review-R31/design/auth.md:781`
- `/tmp/swarm-review-R31/design/auth.md:792`
- `/tmp/swarm-review-R31/design/auth.md:793`
- `/tmp/swarm-review-R31/specs/security/03-mcp-security.md:160`
- `/tmp/swarm-review-R31/specs/reference/api-registry.md:429`
- `/tmp/swarm-review-R31/specs/reference/api-registry.md:433`

问题描述：
通用 canonical request header 使用 `Swarm-Timestamp: <unix_ms>` 和 `Swarm-Nonce: <random 128-bit>`；WebSocket 握手示例使用 `<unix_seconds>` 和 `<random_96bit>`。WS message 签名在 MCP 安全规范中覆盖 `SWARM-WS-MSG-V1\n<seq>\n<body_hash>`，API Registry 则说 Agent WS 使用 `Swarm-Request-Signature` 头覆盖 `(method, uri, timestamp, seq, body_hash)`。

影响分析：
这会导致不同端点、SDK 或网关 middleware 对时间单位、nonce 长度和签名 payload 的实现不一致。安全上主要风险是 replay 检测窗口计算错误、nonce 熵不足实现争议、以及 WS per-message signature 验签代码无法复用或误验。

修复建议：
定义一个 WS-specific canonical signature 规范，明确是否复用 `SWARM-REQUEST-V1` 字段，或使用 `SWARM-WS-HANDSHAKE-V1` / `SWARM-WS-MSG-V1`。统一 timestamp 单位（建议 unix_ms）、nonce 长度（建议 128-bit），并删除 API Registry 中与 MCP 安全规范冲突的 payload 描述。

### S-M2 — Sandbox 网络隔离表述冲突，可能导致部署者误配网络 namespace

Severity: Medium

文件引用：
- `/tmp/swarm-review-R31/specs/core/04-wasm-sandbox.md:21`
- `/tmp/swarm-review-R31/specs/core/04-wasm-sandbox.md:24`
- `/tmp/swarm-review-R31/specs/core/04-wasm-sandbox.md:264`
- `/tmp/swarm-review-R31/specs/core/04-wasm-sandbox.md:266`
- `/tmp/swarm-review-R31/specs/core/04-wasm-sandbox.md:379`
- `/tmp/swarm-review-R31/specs/core/04-wasm-sandbox.md:389`
- `/tmp/swarm-review-R31/specs/core/04-wasm-sandbox.md:390`

问题描述：
架构图和网络命名空间章节写“无网络命名空间”，但 OS 加固 checklist 又要求 `net` 为独立网络栈，并验证 `ip netns list`。从安全语义看，“无网络命名空间”可被理解为不创建 netns、共享宿主网络；也可被理解为 sandbox 内没有可用网络。后文 checklist 倾向于“独立 netns 且无网络接口”。

影响分析：
WASM sandbox 网络隔离是防 SSRF、横向移动和数据外传的关键边界。虽然 seccomp 禁止 socket/connect，但 defense-in-depth 需要 namespace 与 seccomp 语义一致。模糊表述可能导致部署者只依赖 seccomp，或错误地让 sandbox 共享宿主网络 namespace。

修复建议：
统一措辞为“独立 network namespace，loopback down 或无可路由接口；禁止 host network；只通过预传入的 Unix domain socket 与引擎通信”。将架构图中的“无网络命名空间”改为“独立 netns / no external network”，并保留 CI 验证项。

### S-M3 — Spectator/Public replay 可见性存在“公开全图”与“只公开元数据”的合同张力

Severity: Medium

文件引用：
- `/tmp/swarm-review-R31/specs/security/03-mcp-security.md:167`
- `/tmp/swarm-review-R31/specs/security/03-mcp-security.md:171`
- `/tmp/swarm-review-R31/specs/security/05-visibility.md:137`
- `/tmp/swarm-review-R31/specs/security/05-visibility.md:139`
- `/tmp/swarm-review-R31/specs/security/05-visibility.md:143`
- `/tmp/swarm-review-R31/specs/security/05-visibility.md:155`
- `/tmp/swarm-review-R31/specs/security/05-visibility.md:163`

问题描述：
MCP 安全规范把浏览器/公开观众 WS 描述为只包含公开世界状态（房间列表、在线玩家数、公开排行榜），而可见性规范允许 `public_spectate=true` 时未登录客户端订阅全地图实体 delta，只受 `spectate_delay` 与 `replay_privacy` 过滤约束。两者并非完全不可兼容，但“公开世界状态”的范围没有共同定义。

影响分析：
如果实现者按 MCP 文档，spectator 只见聚合元数据；按 visibility 文档，则可能公开延迟全图实体位置/状态。World 模式中这会影响情报泄露、赛外分析、bot 训练数据采集和 replay privacy 承诺。

修复建议：
建立统一的 spectator data classification：public metadata、delayed physical state、private internal state 三层。MCP 安全规范应引用 visibility §3.5/§10，并明确 World 默认 `public_spectate=false`，开启时必须满足 `spectate_delay >= 50` 和 `replay_privacy` 过滤；Arena 可赛后/延迟全知。不要在不同文档重复不同措辞。

### S-L1 — Auth 限流数值多处不一致，影响可实施性和安全测试

Severity: Low

文件引用：
- `/tmp/swarm-review-R31/specs/reference/api-registry.md:391`
- `/tmp/swarm-review-R31/specs/reference/api-registry.md:392`
- `/tmp/swarm-review-R31/specs/reference/api-registry.md:621`
- `/tmp/swarm-review-R31/specs/reference/api-registry.md:627`
- `/tmp/swarm-review-R31/design/auth.md:856`
- `/tmp/swarm-review-R31/design/auth.md:858`
- `/tmp/swarm-review-R31/design/auth.md:859`
- `/tmp/swarm-review-R31/design/auth.md:960`
- `/tmp/swarm-review-R31/specs/security/03-mcp-security.md:292`

问题描述：
Auth/API Registry/MCP 文档中 login、refresh、challenge、CSR、lockout 的限流和 TTL 数值不完全一致。例如 Registry 的 refresh token lifetime 为 7d，Auth 为 30d；API Registry login 为 10/min，Auth recovery/login fail lockout 是 10/min 或 5 次失败锁 5min；MCP deploy rate 是 10/h，Auth 方法矩阵又出现 `swarm_deploy` 1/5s。

影响分析：
这类差异不一定单独形成漏洞，但会导致实现、SDK、测试、运维告警阈值和文档不一致。安全测试无法知道哪个阈值为权威，攻击者可能利用较宽实现路径。

修复建议：
将所有安全限制收敛到 API Registry/auth IDL 的机器可读字段。设计文档只保留解释和引用，不重新声明数值；如必须重复，增加 CI cross-doc consistency check。

## 3. 亮点

- 应用层证书模型方向正确：Swarm CA 不进入系统/浏览器 trust store，传输层 TLS 与应用层 CA 隔离，降低 CA 误用风险（`/tmp/swarm-review-R31/design/auth.md:33`、`/tmp/swarm-review-R31/design/auth.md:136`）。
- 用途隔离证书设计扎实：`ClientAuthCertificate`、`CodeSigningCertificate`、`AdminCertificate` 的 usage/scope/TTL 分离，能有效降低单凭据泄露的横向影响（`/tmp/swarm-review-R31/design/auth.md:267`）。
- CSR/PoW 设计注意到了服务端权威 challenge/difficulty，避免客户端降级 PoW 难度（`/tmp/swarm-review-R31/design/auth.md:625`）。
- 可见性规范强调所有输出面统一调用 `is_visible_to`，并把 debug/replay/host functions 纳入同一过滤模型，能显著减少 oracle 类漏洞（`/tmp/swarm-review-R31/specs/security/05-visibility.md:7`、`/tmp/swarm-review-R31/specs/security/05-visibility.md:13`、`/tmp/swarm-review-R31/specs/security/05-visibility.md:77`）。
- WASM sandbox 覆盖了多层防线：Wasmtime fuel、内存限制、WASI 禁用、start section 拒绝、host function 白名单、seccomp/cgroup/namespace checklist、恶意样本库和 CVE SLA（`/tmp/swarm-review-R31/specs/core/04-wasm-sandbox.md:47`、`/tmp/swarm-review-R31/specs/core/04-wasm-sandbox.md:101`、`/tmp/swarm-review-R31/specs/core/04-wasm-sandbox.md:122`、`/tmp/swarm-review-R31/specs/security/CVE-SLA.md:19`）。
- Persistence contract 将 replay-critical subset 与 rich/debug blob 分离，FDB hash/content pointer 模型清晰，有助于对象存储失败时保持核心状态完整性（`/tmp/swarm-review-R31/specs/core/05-persistence-contract.md:30`、`/tmp/swarm-review-R31/specs/core/05-persistence-contract.md:111`）。
- Refresh token rotation、family revoke、浏览器 HttpOnly/SameSite/WebCrypto non-extractable key、禁止 localStorage 等 Web 安全基线明确，覆盖常见 XSS/token theft 风险（`/tmp/swarm-review-R31/design/auth.md:1263`、`/tmp/swarm-review-R31/design/auth.md:1275`）。

## 4. CrossCheck — 需要跨方向检查

- CX-1: API Registry 声称由 IDL 自动生成，但与 Auth 设计工具清单明显不一致 → 建议 API/IDL 方向检查 `auth_api.idl.yaml` 是否遗漏完整 auth lifecycle，以及 codegen 是否会暴露错误工具面。
- CX-2: `design/auth.md` 后段仍保留“Phase 1 / 实现范围”表述 → 建议 Documentation/Speaker 方向检查是否违反“设计即目标状态、非阶段路线图”的文档原则，并清理历史阶段语言。
- CX-3: Deploy activation 在 API Registry 中写 async upload immediate key，但 Persistence contract 中要求 activation_tick 到达时必须 upload complete 且 hash 验证 → 建议 Persistence/Engine 方向检查 deploy_mutation 状态机是否唯一权威。
- CX-4: RuleMod source 可写 damage/effect/resource/custom handler，但本次安全子集未包含 mod sandbox / Rhai capability 详细规范 → 建议 Gameplay/Modding/Sandbox 方向检查 RuleMod capability whitelist 是否足以防越权写世界状态。
- CX-5: Admin 操作“无 rate limit”出现在 Command Source matrix，而 API Registry 为 admin 10/h 或 per-admin → 建议 Operations/Auth 方向检查 admin rate/cooldown/dual-sign 是否统一。
- CX-6: Visibility 文档允许 non-competitive `fog_of_war=false + player_view=full`，但 MCP 安全强调 AI/Web 信息等量 → 建议 Gameplay/UX 方向检查教学/合作世界是否明确标记 non-competitive，避免 ladder/world 配置误开全图。
