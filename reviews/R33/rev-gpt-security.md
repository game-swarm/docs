# R33 Security Review — GPT-5.5

## Verdict
REQUEST_MAJOR_CHANGES

本轮设计的安全目标方向正确：应用层证书、用途隔离、CSR admission control、WebSocket per-message 签名、可见性统一过滤、WASM fuel/cgroup/seccomp 组合都体现了强安全边界。但当前文档仍存在必须修复的重大问题，主要集中在：机器权威 `auth_api.idl.yaml` 与 `design/auth.md` 的证书模型分叉、CSR admission/rate limit 自相矛盾、sandbox OS 隔离语义冲突、Auth/Persistence 中敏感数据保护未闭合。若按当前设计进入实现，极易出现 codegen 实现走旧 bearer-token/内部 CA 路径，而设计文档宣称走应用层证书路径的安全错配。

## Critical (必须修复，否则 BLOCK) (B1..Bn)

### B1 — `auth_api.idl.yaml` 仍是旧 token/cert-management 模型，未表达 CSR→certificate→credential→session 主链
- Severity: Critical
- 文件引用：
  - `/data/swarm/docs/specs/reference/auth_api.idl.yaml:16`
  - `/data/swarm/docs/specs/reference/auth_api.idl.yaml:30`
  - `/data/swarm/docs/specs/reference/auth_api.idl.yaml:152`
  - `/data/swarm/docs/specs/reference/auth_api.idl.yaml:182`
  - `/data/swarm/docs/design/auth.md:17`
  - `/data/swarm/docs/design/auth.md:118`
  - `/data/swarm/docs/specs/reference/api-registry.md:3`
- 问题描述：`api-registry.md` 明确声明 IDL YAML 是机器可读权威源，冲突时以 IDL 为准；但 `auth_api.idl.yaml` 仍定义 `swarm_auth_login` / `swarm_auth_refresh` / opaque refresh token 主链，以及 `swarm_auth_cert_issue` 这类 admin 内部 CA 证书签发工具。它没有机器可读地注册 `swarm_register_challenge`、`swarm_submit_csr`、`swarm_renew_certificate`、`swarm_get_server_trust`、`swarm_request_password_reset`、`swarm_confirm_password_reset`、`swarm_recover_with_passkey`、`swarm_federated_login` 等 `design/auth.md` 中的目标认证链。
- 影响分析：这是安全合同的根本分叉。实现/codegen 若遵循 IDL，会得到 bearer token + admin cert issue/rotate/revoke 的旧 PKI 管理面，而不是用户持私钥、CSR 提交、用途隔离应用层证书、canonical request signature 的目标模型。攻击面包括：未通过 CSR possession proof 签发凭据、admin 证书签发接口被误用于用户证书、JWT/refresh token 被实现成事实信任根、scope/audience/nonce 约束缺失。
- 修复建议：重写 `auth_api.idl.yaml` 使其成为目标认证模型的机器权威源。至少应包含：CSR/PoW challenge、CSR submit、certificate renewal、certificate revoke/list、server trust pinning、request signature envelope、replay class、scope、audience、rate limit key、recovery/passkey/federation 工具。删除或重命名旧 `swarm_auth_cert_issue/rotate` 中“internal CA/TLS/mTLS certificate”的语义；若保留 admin CA 运维工具，必须明确其只操作 Server Intermediate CA/应用层证书治理，并要求双签/冷却/审计。随后重新生成 `api-registry.md`。

### B2 — CSR rate limit/admission control 在同一设计内冲突，未认证入口可被 DoS
- Severity: Critical
- 文件引用：
  - `/data/swarm/docs/design/auth.md:259`
  - `/data/swarm/docs/design/auth.md:264`
  - `/data/swarm/docs/design/auth.md:266`
  - `/data/swarm/docs/design/auth.md:878`
  - `/data/swarm/docs/design/auth.md:972`
  - `/data/swarm/docs/design/auth.md:978`
- 问题描述：`design/auth.md` §5.2 将 CSR 提交定义为多层 admission control，包含 per-IP ≤1/30s、per-ASN ≤10/min、global semaphore、bounded queue；但 §10.8 未认证端点保护表又写 `CSR 提交 | PoW 自身限速 | 无额外 IP 限制`。同一文档对最关键未认证高成本路径给出互相矛盾的安全策略。
- 影响分析：CSR 验证路径包含 PoW 验证、CSR signature、FDB transaction、证书签发前置检查等成本。若实现者采用 §10.8 的“无额外 IP 限制”，攻击者可并行提交大量已预计算或低难度 challenge 的 CSR 请求，耗尽 global verifier、FDB challenge rows、队列和 Auth Service CPU。PoW 不能替代速率限制，文档 §10.7 自己也承认分布式来源可绕过 PoW 成本。
- 修复建议：将未认证端点保护表改为引用 §5.2 权威准入链，明确 CSR 提交必须执行 per-IP、per-ASN、global semaphore、bounded queue、audit throttle，且 PoW 仅为 L1 成本过滤。同步 `auth_api.idl.yaml` 的 endpoint rate limits，避免 IDL/codegen 生成“无额外 IP 限制”的实现。

### B3 — Sandbox 网络隔离语义自相矛盾，可能导致生产环境仍有宿主网络面
- Severity: Critical
- 文件引用：
  - `/data/swarm/docs/specs/core/04-wasm-sandbox.md:24`
  - `/data/swarm/docs/specs/core/04-wasm-sandbox.md:264`
  - `/data/swarm/docs/specs/core/04-wasm-sandbox.md:389`
  - `/data/swarm/docs/specs/core/04-wasm-sandbox.md:390`
  - `/data/swarm/docs/specs/core/04-wasm-sandbox.md:379`
- 问题描述：架构图和 §4.3 写“无网络命名空间”，但加固 checklist 又要求独立 `net` namespace 且无网络接口。中文“无网络命名空间”可被理解为没有独立 netns、沿用宿主网络 namespace；这与后文安全目标冲突。
- 影响分析：若实现者按“无网络命名空间”执行，只依赖 seccomp 禁止 `socket/connect/sendmsg/recvmsg`，任何 seccomp 配置遗漏、Wasmtime/host runtime 新增 syscall、或已打开 fd 泄露都可能使 sandbox 接触宿主网络。对可上传 WASM 的 MMO 平台，这是高危沙箱逃逸/SSRF/横向移动面。
- 修复建议：统一措辞为“独立 network namespace，默认无接口/无路由；仅通过预传入 Unix domain socket fd 与引擎通信；seccomp 作为第二层禁止 socket family syscalls”。同时在 checklist 中加入启动时验证：sandbox netns 中无非 loopback 接口、无 default route、无法 connect 外网/private IP。

## High (强烈建议修复) (H1..Hn)

### H1 — Auth TTL/session/lockout 参数在设计文档与 IDL/API Registry 中冲突
- Severity: High
- 文件引用：
  - `/data/swarm/docs/design/auth.md:1272`
  - `/data/swarm/docs/design/auth.md:1277`
  - `/data/swarm/docs/design/auth.md:1836`
  - `/data/swarm/docs/specs/reference/auth_api.idl.yaml:568`
  - `/data/swarm/docs/specs/reference/auth_api.idl.yaml:571`
  - `/data/swarm/docs/specs/reference/auth_api.idl.yaml:573`
  - `/data/swarm/docs/specs/reference/api-registry.md:631`
  - `/data/swarm/docs/specs/reference/api-registry.md:636`
- 问题描述：`design/auth.md` 声明 refresh token TTL 30 days、证书 TTL 15 min–180 days；配置示例也写 refresh_token_ttl_days=30。IDL/API Registry 的机器权威却写 refresh_token_lifetime=7d、cert_validity_max=365d、failed_login_lockout_threshold=10/15m/30m，与设计文档 5 次失败锁 5min、active certificates/device 上限等规则不一致。
- 影响分析：TTL 和 lockout 是安全边界，不一致会导致实现和运维预期错配。过长证书有效期扩大私钥泄露窗口；过宽 lockout 阈值削弱暴力破解防护；Web session 兼容层若按 7d/30d 混用，会造成客户端刷新、审计和风险策略不稳定。
- 修复建议：选定唯一权威参数并同步到 IDL。建议机器权威 IDL 直接表达 certificate profile TTL：ClientAuth、CodeSigning、Admin、Federation、temporary/managed/admin device 的上限；refresh token rotation/grace；login/recovery lockout；active device/certificate cap。Markdown 只引用 IDL 生成值。

### H2 — Command Source 中 Admin “无限制”与 API Registry admin 10/h 冲突
- Severity: High
- 文件引用：
  - `/data/swarm/docs/specs/security/09-command-source.md:20`
  - `/data/swarm/docs/specs/reference/api-registry.md:268`
  - `/data/swarm/docs/specs/reference/api-registry.md:274`
  - `/data/swarm/docs/specs/reference/api-registry.md:357`
  - `/data/swarm/docs/specs/reference/api-registry.md:362`
  - `/data/swarm/docs/design/auth.md:348`
- 问题描述：Command source 来源矩阵将 `Admin` rate_limit 标为“无限制”，而 API Registry 通用 admin rate limit 为 10/h，具体 admin 工具为 5/min、10/h、5/h、30/tick 等。`design/auth.md` 还特别说明 Admin category rate limit 以 API Registry 为准，不能重复声明冲突数值。
- 影响分析：管理员接口是最高权限面。若实现者采用“无限制”，被盗 AdminCertificate 可高速执行 rollback、ban、config、GC、audit dump 等操作，造成大范围破坏或审计/存储 DoS。即使需要 emergency 操作，也应通过 break-glass policy、双签、审计和冷却表达，而不是无限制。
- 修复建议：将 Command Source 的 Admin rate_limit 改为“API Registry per-tool limits + admin_critical FDB challenge/CAS + sensitive ops cooldown/dual-sign”。如需紧急例外，定义明确的 break-glass scope、短 TTL、双 admin、强审计和全局限速。

### H3 — Deploy signed payload 缺少证书 ID/issuer/expiry/audience 绑定，降低抗混淆和审计能力
- Severity: High
- 文件引用：
  - `/data/swarm/docs/specs/security/09-command-source.md:73`
  - `/data/swarm/docs/specs/security/09-command-source.md:82`
  - `/data/swarm/docs/specs/security/09-command-source.md:99`
  - `/data/swarm/docs/specs/security/09-command-source.md:107`
  - `/data/swarm/docs/design/auth.md:360`
  - `/data/swarm/docs/design/auth.md:381`
- 问题描述：`DeployPayload` 签名字段包含 domain、module_hash、metadata_hash、player_id、world_id、module_slot、version_counter、signed_at，但不包含 `certificate_id`、`audience`、`usage`、issuer/intermediate fingerprint、transport/server_id。通用 canonical request signature 则要求 certificate_id 和 audience 入签名 payload。
- 影响分析：虽然服务端会从证书提取 player_id 并验证 usage，但 deploy 签名本身缺少证书实例绑定，容易在多证书、多世界、多中间 CA 轮换、同 key 多用途证书场景中造成审计归因不清、跨上下文 payload 混淆，甚至在实现疏漏时引发跨 audience 重放。
- 修复建议：将 deploy 签名升级为 `SWARM-DEPLOY-V1` canonical payload，纳入 `certificate_id`、`audience`、`server_id`、`world_id`、`player_id`、`module_slot`、`version_counter`、`module_hash`、`metadata_hash`、`signed_at`、`expires_at/not_after` 或 max clock skew 规则。要求 CodeSigningCertificate 的 audience 与 deploy payload 完全匹配。

### H4 — 持久化与审计日志中的敏感数据保护不足，缺少加密/最小化合同
- Severity: High
- 文件引用：
  - `/data/swarm/docs/design/auth.md:506`
  - `/data/swarm/docs/design/auth.md:509`
  - `/data/swarm/docs/design/auth.md:511`
  - `/data/swarm/docs/specs/security/03-mcp-security.md:361`
  - `/data/swarm/docs/specs/security/03-mcp-security.md:368`
  - `/data/swarm/docs/specs/core/05-persistence-contract.md:23`
  - `/data/swarm/docs/specs/core/05-persistence-contract.md:24`
- 问题描述：Auth FDB subspace 存储 sessions、reset token hash、email verification token hash、admin audit 等；MCP audit 表记录 `parameters String`；Persistence object store 保存 RichTraceBlob、snapshot delta、replay artifacts、WASM binaries。但文档没有明确 FDB value/object store/ClickHouse audit 的加密、字段级脱敏、参数白名单/黑名单、密钥管理和访问控制边界。
- 影响分析：即使 token hash 不泄露明文，`parameters String` 可能包含 email、reset flow 参数、device_fingerprint、certificate chain、部署 metadata、玩家原创字符串或未来工具中的敏感参数。Object store 中 RichTrace/debug blob 也可能包含 env_vars、drone memory、debug_detail、audit context。FDB/ClickHouse/object store 泄露会扩大为账号恢复、隐私、策略源码和安全事件情报泄露。
- 修复建议：定义数据分类与存储保护合同：Auth/reset/session/token hash 使用 pepper/HMAC 或 keyed hash；ClickHouse audit parameters 改为 schema-aware redaction 后的 canonical summary + hash，不存原始参数；Object Store at-rest encryption，KMS/age key rotation；RichTraceBlob 中 secret-like 字段默认不落盘或加密；访问路径按 admin/debug/replay scope 分离；日志中证书链、reset token、refresh token、email、device fingerprint 默认脱敏。

### H5 — `auth_api.idl.yaml` 的证书管理工具语义混入 TLS/mTLS/RSA/ECDSA，与应用层 Ed25519 证书模型冲突
- Severity: High
- 文件引用：
  - `/data/swarm/docs/specs/reference/auth_api.idl.yaml:181`
  - `/data/swarm/docs/specs/reference/auth_api.idl.yaml:188`
  - `/data/swarm/docs/specs/reference/auth_api.idl.yaml:195`
  - `/data/swarm/docs/specs/reference/auth_api.idl.yaml:210`
  - `/data/swarm/docs/design/auth.md:26`
  - `/data/swarm/docs/design/auth.md:33`
  - `/data/swarm/docs/design/auth.md:233`
- 问题描述：IDL 的 cert management 工具描述为 “Rotate a TLS/mTLS certificate”、支持 RSA/ECDSA key types、自动加入 trust store；而目标设计要求 Swarm CA 只用于应用层证书，不进入系统/浏览器 trust store，用户 key 归一为 Ed25519。
- 影响分析：这是供应链/信任边界误导。若实现者按 IDL 生成或实现，会把 Swarm CA 当作 TLS/mTLS trust store 管理面，甚至支持非目标 key type，破坏“传输层 CA 隔离”原则，使 Server Root CA 被滥用于伪装站点或扩大 CA 私钥泄露影响。
- 修复建议：删除 TLS/mTLS/RSA/ECDSA/trust store 语义，改为 Swarm application certificate lifecycle。若项目确实需要传输层证书管理，应拆到独立 `transport_tls_api.idl.yaml`，并明确其 CA 与 Swarm application CA 隔离。

### H6 — 可见性配置允许教学/合作世界关闭 fog_of_war，但 MCP 安全文档仍说信息量与 Web UI 等量，缺少模式级安全标签
- Severity: High
- 文件引用：
  - `/data/swarm/docs/specs/security/03-mcp-security.md:40`
  - `/data/swarm/docs/specs/security/05-visibility.md:319`
  - `/data/swarm/docs/specs/security/05-visibility.md:330`
  - `/data/swarm/docs/specs/security/05-visibility.md:371`
  - `/data/swarm/docs/specs/security/05-visibility.md:373`
- 问题描述：MCP 安全文档强调 AI 与 Web UI 信息等量，不更多不少；Visibility 文档允许 non-competitive tutorial/coop/sandbox 中 `fog_of_war=false`、`player_view=full`，MCP read/query 可见全地图。当前缺少强制的 world security label / competitive flag 与 API response 标注，避免 agent 将低安全/教学世界训练出的权限假设带入竞争世界。
- 影响分析：这不是直接越权，但会形成配置误用风险。服主若误把 competitive world 设置成 non-competitive/full，AI/MCP 会获得全图；客户端/SDK 若不显示 security posture，玩家很难判断世界是否公平。
- 修复建议：在 world config validation 中引入不可混淆的 `world.security_class = competitive | cooperative | tutorial | sandbox`，并由 API/MCP response 明示当前 visibility posture。competitive 强制 `fog_of_war=true` 且禁止 `player_view=full`；非 competitive 世界的全图暴露必须在 `swarm_get_info` / `swarm_get_world_config` 中返回警告字段。

## Medium (建议关注) (M1..Mn)

### M1 — HTTP 不安全传输允许认证但敏感 payload 加密合同不足够具体
- Severity: Medium
- 文件引用：
  - `/data/swarm/docs/design/auth.md:418`
  - `/data/swarm/docs/design/auth.md:423`
  - `/data/swarm/docs/design/auth.md:425`
  - `/data/swarm/docs/specs/security/03-mcp-security.md:116`
- 问题描述：文档说明 HTTP 可认证/完整性校验，但敏感 payload “应加密给服务器应用层证书 public key”。这里缺少强制算法、nonce、AEAD associated data、key rotation、失败语义，以及哪些 endpoint 必须加密的列表。
- 影响分析：若只做签名不加密，email、recovery flow、device metadata、certificate chain 等会在 HTTP/不可信代理中明文暴露。若加密协议不规范，可能出现重放、unknown-key-share 或降级。
- 修复建议：定义 `SWARM-ENCRYPTED-PAYLOAD-V1`：X25519 或 HPKE + AEAD，AAD 包含 method/path/timestamp/nonce/certificate_id/audience/server_id/world_id；列出必须加密的恢复、邮箱、admin recovery、managed key handoff endpoint；未加密直接拒绝。

### M2 — CVE-SLA 缺少 owner/escalation 和自动化门禁细节，可执行性仍偏流程化
- Severity: Medium
- 文件引用：
  - `/data/swarm/docs/specs/security/CVE-SLA.md:21`
  - `/data/swarm/docs/specs/security/CVE-SLA.md:44`
  - `/data/swarm/docs/specs/security/CVE-SLA.md:77`
  - `/data/swarm/docs/specs/security/CVE-SLA.md:90`
- 问题描述：SLA 给出了响应时间、监控来源和记录模板，但没有明确自动创建任务的责任 owner、升级通知路径、SLA breach 行为、CI fail-open/fail-closed 策略、临时豁免的最长有效期。
- 影响分析：安全响应流程可能在告警到任务分派之间失效，尤其 Wasmtime/sandbox escape 类 Critical 需要明确“谁可以暂停部署/谁确认缓解”。
- 修复建议：补充 owner matrix：sandbox/security/infra primary+backup；Critical/High 通知渠道；cargo audit/RustSec gate 默认 fail-closed；豁免必须有 advisory ID、expiry、risk acceptance；SLA breach 自动升级到 release blocker。

### M3 — WebSocket 签名字段在文档之间存在小差异，建议统一为单一 canonical schema
- Severity: Medium
- 文件引用：
  - `/data/swarm/docs/design/auth.md:812`
  - `/data/swarm/docs/design/auth.md:814`
  - `/data/swarm/docs/specs/security/03-mcp-security.md:160`
  - `/data/swarm/docs/specs/reference/api-registry.md:441`
- 问题描述：`design/auth.md` / MCP security 使用 `SWARM-WS-MSG-V1\n<direction>\n<session_id>\n<seq>\n<tick>\n<body_hash>`，API Registry 又描述为 `Swarm-Request-Signature` 覆盖 `(method, uri, timestamp, seq, body_hash)`。两者都表达 per-message signature，但 canonical payload 字段不完全一致。
- 影响分析：实现者可能生成不兼容客户端/服务器签名，或遗漏 tick/session binding。安全上主要是重放/跨 session 混淆风险。
- 修复建议：在 IDL 或单独 spec 中定义唯一 `SWARM-WS-MSG-V1` canonical schema，并让 api-registry 引用生成值。字段建议包含 direction、session_id、transport、server_id、world_id、seq、tick、body_hash。

### M4 — Audit log “不可修改”没有说明防篡改机制
- Severity: Medium
- 文件引用：
  - `/data/swarm/docs/specs/security/03-mcp-security.md:361`
  - `/data/swarm/docs/specs/security/03-mcp-security.md:377`
  - `/data/swarm/docs/design/auth.md:122`
  - `/data/swarm/docs/design/auth.md:135`
- 问题描述：MCP audit 写入 ClickHouse 并称“不可修改”，Auth 证书签发/CA 使用写入 FDB audit，但缺少 append-only enforcement、hash chain、WORM/object-lock、管理员删除/修改防护、跨存储审计一致性。
- 影响分析：管理员或入侵者可篡改/删除审计记录以掩盖证书签发、恢复链接、部署和调试数据访问行为。
- 修复建议：审计记录增加 hash chain 或 Merkle batch root，周期性锚定到 FDB/object store WORM；ClickHouse 表只做查询副本，权威审计根在 append-only log；admin audit 删除需不可用或双签 break-glass 并保留 tombstone。

## Low / Nits (可选改进) (L1..Ln)

### L1 — `MCP security` 中链接引用与实际路径相对关系可能误导
- Severity: Low
- 文件引用：
  - `/data/swarm/docs/specs/security/03-mcp-security.md:181`
  - `/data/swarm/docs/specs/security/03-mcp-security.md:838`
- 问题描述：文档引用 `design/auth.md` §13.5，但当前 auth 文档应用层证书模型在 §14.5；部分链接从 specs/security 到 specs/security/specs/security 可能因相对路径错误而不可点击。
- 影响分析：不会直接造成漏洞，但会降低实现者查证权威条款的可靠性。
- 修复建议：更新 section 编号或改为稳定 anchor；检查相对路径。

### L2 — WASM module size 在不同文档中存在 5MB/64MB 表述差异
- Severity: Low
- 文件引用：
  - `/data/swarm/docs/specs/core/04-wasm-sandbox.md:127`
  - `/data/swarm/docs/specs/core/04-wasm-sandbox.md:302`
  - `/data/swarm/docs/specs/reference/api-registry.md:898`
- 问题描述：sandbox 预校验限制 WASM module 5MB，而 API Registry object-store Blob Types 里 `wasm_module` 最大 64MB。可能一个是上传对象上限，一个是可部署模块上限，但未明确分层。
- 影响分析：实现者可能按 64MB 接受部署，扩大编译/验证 DoS 面。
- 修复建议：明确 `deployable_wasm_max = 5MB`，`object_store_wasm_blob_max = 64MB` 仅用于历史/压缩/未来 profile；若无用途，统一为 5MB。

## Strengths (设计亮点)

- 应用层证书不进入系统/浏览器 trust store，并明确 TLS/WebPKI 与 Swarm CA 隔离；这是自托管/内网场景下避免 CA 滥用的正确方向。
- CSR 多层准入链包含 PoW、per-IP、per-ASN、global semaphore、bounded queue、audit throttle，覆盖了注册洪泛与服务端 CPU 放大的主要 DoS 向量。
- Canonical request signature 明确包含 method/path/body_hash/timestamp/nonce/certificate_id/player_id/audience，并定义 LF、字段顺序、domain separator，降低跨语言签名不一致风险。
- WebSocket authenticated path 要求握手证书验证 + 每消息 seq/MAC/Ed25519 签名 + tick 绑定，对会话内重放/注入/重排防护充分。
- Visibility 文档强调所有输出面共用 `is_visible_to`，并覆盖 snapshot、MCP、WS、REST、replay、host functions，是防 oracle 泄露的关键设计。
- WASM sandbox 采用 Wasmtime fuel、epoch interruption、Store reset、WASI 禁用、只读 host functions、seccomp/cgroup/namespace 多层防护，整体符合高风险用户代码执行平台的安全基线。
- Persistence contract 将 replay-critical subset 与 RichTraceBlob 分离，FDB hash/content pointer 作为权威，降低对象存储失败对确定性回放的影响。
- CVE-SLA 覆盖 Wasmtime、wasmparser、cranelift、crypto/TLS/async/runtime 关键 Rust crate，且禁止为赶 SLA 放宽 sandbox 约束，这是正确的供应链风险姿态。

## CrossCheck — 需要跨方向检查
- CX1: `auth_api.idl.yaml` 与 `design/auth.md` 分叉会影响 codegen、SDK、Gateway、Auth Service 实现 → 建议 API/IDL 方向检查 auth IDL 是否应重构为 CSR/application certificate 权威源，并重新生成 API Registry。
- CX2: CSR admission 与未认证端点限流冲突会影响 Auth Service/Gateway hot path → 建议 性能/运维 方向检查 rate limiter、queue、semaphore 在多节点部署下的一致性与容量参数。
- CX3: Sandbox netns/seccomp/cgroup 约束需要落地验证 → 建议 Infra/Sandbox 方向检查容器/runtime 是否能创建独立 net/pid/mnt/ipc/uts namespace，并验证预传 fd 后 seccomp 锁定顺序。
- CX4: Persistence 中 RichTraceBlob/Object Store 可能包含敏感 debug/env/memory 数据 → 建议 Data/Privacy 方向检查数据分类、加密、保留期、删除权、管理员访问审计。
- CX5: Command Source 的 Admin 走 `validate_and_apply()` 且放宽所有权检查 → 建议 Engine/Correctness 方向检查 Rust trait 约束是否真的能防止直接 `&mut World` 绕过 Source Gate。
- CX6: Visibility 中 `public_spectate=true` 全地图延迟推送依赖 `replay_privacy` 过滤 → 建议 Gameplay/Fairness 方向检查 spectate_delay=50/100 tick 是否足以防止实时情报战与外部协同。