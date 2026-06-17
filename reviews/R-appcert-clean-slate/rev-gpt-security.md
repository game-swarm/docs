# R-appcert-clean-slate — GPT-5.5 Security Clean-Slate Review

## Verdict

CONDITIONAL_APPROVE

本轮没有发现需要推翻“Server CA + CSR + application-layer certificates + canonical request signature”主架构的 blocker。设计对私钥不出客户端、用途隔离证书、nonce/timestamp、防跨 transport audience、CRL/epoch、passkey/email/admin recovery、联邦本地重签等关键安全边界有明确建模。

但在进入实现前必须收敛若干 High 风险：部分权威文档仍残留 JWT/MCP 认证旧语义、技术选型中把 Blake3 MAC 称为代码签名、Admin 路径写成无限制、恢复流程默认保留旧证书，以及 sandbox OS 边界存在互相冲突的配置。这些不是概念性否决，但若直接按文档实现，会制造典型的 auth bypass、DoS、不可抵赖性失效或隔离降级风险。

## Top Findings

### High — Gateway MCP 认证仍残留 JWT 主路径，和 application certificate 主模型冲突

- Category: doc inconsistency / security gap / API gap
- Evidence:
  - `specs/12-gateway-protocol.md:119` 写 Gateway MCP 职责包含 “JWT 认证（mcp audience）”。
  - `specs/12-gateway-protocol.md:149` 的安全表仍以 “JWT audience 绑定” 描述 transport 认证。
  - 但 `specs/security/03-mcp-security.md:163` 明确 MCP/Agent 主路径使用 application certificate chain + canonical request signature。
  - `specs/security/03-mcp-security.md:185` 明确 JWT/access_token 不用于 MCP/Agent 主认证路径。
  - `design/auth.md:1015` 也规定 JWT/access_token 不是独立认证根。
- Risk:
  - 实现者可能把 MCP Agent endpoint 接成 JWT bearer/audience 校验，而不是强制证书链与请求签名，导致被盗 Web token、错误 audience token 或兼容层 token 成为 MCP 主凭证。
  - 这类似“新认证模型已设计，但旧 bearer-token fast path 留在 gateway”的常见 auth bypass 事故模式。
- Required before implementation:
  - 统一 `specs/12-gateway-protocol.md` §5/§8/§9：MCP Agent 只接受 `Swarm-Certificate-Chain` + `Swarm-Signature` + `X-Swarm-Transport: mcp`；JWT 仅限 Browser/Web session compatibility，且不得用于 Agent MCP。

### High — “Blake3 MAC 代码签名”与 Ed25519 证书签名模型冲突，可能误导实现为共享密钥 MAC

- Category: doc inconsistency / security gap
- Evidence:
  - `design/tech-choices.md:150` 将“代码签名”列为 Blake3 备选项。
  - `design/tech-choices.md:154` 选择 `Blake3 MAC` 作为代码签名。
  - `design/tech-choices.md:159` 进一步称 “代码签名（Blake3 keyed hash / MAC）”。
  - 但 `design/tech-choices.md:178` 又说证书链、CSR、请求签名和代码签名统一使用 Ed25519。
  - `specs/security/09-command-source.md:67` 和 `specs/security/09-command-source.md:71` 明确部署时由 `CodeSigningCertificate` 对结构化 payload 做 Ed25519 签名，并提供审计链。
- Risk:
  - MAC 不是 public-key signature。若实现者按 Blake3 keyed hash 做“代码签名”，验证方必须知道共享密钥，无法证明“某玩家私钥签署了某模块”，也不支持证书链、公钥审计、不可抵赖和跨服务验证。
  - 这会破坏 CodeSigningCertificate 的核心安全目标：player_id 不可自报、部署责任可审计、私钥持有者可证明。
- Required before implementation:
  - 将 Blake3 限定为 hash/XOF/MAC-for-internal-symmetric-use；代码签名、CSR、request signature、deploy payload signature 全部明确为 Ed25519 over canonical payload。避免在任何标题中把 Blake3 MAC 称为“代码签名”。

### High — Admin 来源与 MCP reference 标为“无限制”，和全局写能力组合成 DoS/误操作放大器

- Category: security gap / API gap
- Evidence:
  - `specs/security/09-command-source.md:20` 写 `Admin` auth_context 为 `AdminCertificate + signed request`，visibility 为全局，rate_limit 为“无限制”。
  - `specs/security/09-command-source.md:43` 写 Admin 允许写入世界、读写全局存储、部署代码、查询世界、触发战斗。
  - `specs/security/09-command-source.md:53` 说明 Admin 走标准 `validate_and_apply()`，但所有权检查放宽。
  - `specs/reference/mcp-tools.md:107` 的 Rate Limiter 表也写 `Admin | 无限制`。
  - `design/auth.md:263` 只说敏感操作“可要求双签”，不是强制策略。
- Risk:
  - 被盗 AdminCertificate、脚本 bug 或误配置可在没有速率阀的情况下触发全局查询、部署、rollback/写操作，造成最大服务端开销或全局状态破坏。
  - “Admin 无限制”是典型高权限路径 DoS 与 blast radius 事故模式；即便 Admin 可信，也应有 emergency brake、global cap、审计告警和敏感操作双签。
- Required before implementation:
  - Admin 不能是 unlimited。至少定义 per-admin/per-world/global 速率、并发、body size、expensive operation budget；CA/trust policy、rollback、全局状态写入、批量吊销等必须强制双签或 break-glass 流程，并触发审计告警。

### High — 恢复成功默认保留旧证书，和“所有证书丢失/私钥损坏”恢复威胁模型不匹配

- Category: security gap / UX gap
- Evidence:
  - `design/auth.md:750` 将邮箱恢复用于“丢失所有可用证书、设备不可访问或私钥损坏”。
  - `design/auth.md:787` 写确认恢复后吊销所有现有 refresh token；旧证书是否吊销由用户选择，默认保留未撤销证书。
  - `design/auth.md:788` 仅提示用户检查并吊销不可访问设备对应证书。
  - `design/auth.md:815` 管理员恢复也只明确吊销 refresh token，没有强制吊销旧证书。
  - 相比之下，账号删除流程 `design/auth.md:894` 明确吊销所有 refresh token + certificate。
- Risk:
  - 当恢复原因是设备丢失、私钥损坏、agent 凭据丢失或怀疑 compromise 时，默认保留旧 certificate 等于让可能已泄露的私钥继续拥有 `ClientAuthCertificate` / `CodeSigningCertificate` 权限。
  - 用户在恢复时最可能处于低信息状态，默认保留会把安全决策推给 UX，容易形成长期幽灵设备。
- Required before implementation:
  - 恢复流程需要区分原因：lost/compromised/all-devices-lost 应默认吊销旧 device certificates 和 code signing certificates；仅 “add new device while old device trusted” 才可保留。管理员恢复链接应带 reason，并把默认吊销策略写入合同。

### Medium — Sandbox OS 边界配置互相冲突，可能导致 seccomp/cgroup 实现选择不安全一侧

- Category: doc inconsistency / security gap / deferred implementation concern
- Evidence:
  - `specs/core/04-wasm-sandbox.md:240` 的 seccomp 允许 `clone (仅 CLONE_VM | CLONE_VFORK)`。
  - `specs/core/04-wasm-sandbox.md:255` 写 `cpu.max = 250000 3000000`。
  - `specs/core/04-wasm-sandbox.md:256` 写 `pids.max = 32`。
  - 但 checklist `specs/core/04-wasm-sandbox.md:375` 又写 `fork/vfork/clone` 全禁。
  - checklist `specs/core/04-wasm-sandbox.md:386` 写 `cpu.max = 50000 100000`，`specs/core/04-wasm-sandbox.md:387` 写 `pids.max = 16`。
- Risk:
  - 沙箱边界是安全关键配置，不能靠实现者猜哪个表是权威。允许 `clone` 与更多 PID 可能扩大 Wasmtime/JIT 或依赖 bug 的后利用空间；CPU 配额不一致会影响 tick DoS 上限。
- Required before implementation:
  - 指定唯一权威 seccomp/cgroup profile；解释 Wasmtime 是否确实需要 thread/clone。如果需要，列出最小 flags、线程数、测试；如果不需要，clone 全禁并保持 checklist 一致。

### Medium — `swarm_deploy_challenge` 是部署防重放核心，但 auth/interface/reference 工具表未列出

- Category: API gap / doc inconsistency
- Evidence:
  - `specs/security/09-command-source.md:99` 要求 `deploy_nonce` 通过 MCP `swarm_deploy_challenge` 获取。
  - `specs/security/09-command-source.md:105` 和 `specs/security/09-command-source.md:256` 都把 `swarm_deploy_challenge` 作为部署状态机第一步。
  - 但 `design/interface.md:18`–`design/interface.md:63` 的 MCP 工具表未列出 `swarm_deploy_challenge`。
  - `specs/reference/mcp-tools.md:18`–`specs/reference/mcp-tools.md:26` 的部署工具也未列出该工具。
  - `design/auth.md:610`–`design/auth.md:629` 的 auth MCP 工具表只列注册/CSR challenge，未列部署 challenge。
- Risk:
  - 如果 API 参考/实现清单漏掉 nonce issuance endpoint，部署流程可能退化为直接签 `module_hash + metadata`，扩大重放窗口；或者各实现自创 nonce API，破坏 canonical payload 与审计一致性。
- Required before implementation:
  - 将 `swarm_deploy_challenge` 加入 design/interface 与 reference/mcp-tools，定义参数、返回、scope、rate limit、audience、single-use semantics，与 specs/security/09 对齐。

### Medium — 浏览器把 refresh token 放入 localStorage，安全性依赖“严格 CSP 无 XSS”这一强假设

- Category: security gap / deferred implementation concern
- Evidence:
  - `design/auth.md:990` 写浏览器使用 `localStorage` 存储 `{refresh_token, certificate, client_public_key}`。
  - `design/auth.md:991` 用严格 CSP 和 Trusted Types 防护 XSS。
  - `design/auth.md:974` 写 refresh_token TTL 为 30 days。
  - `design/auth.md:978`–`design/auth.md:981` 定义 refresh token rotation grace。
- Risk:
  - localStorage 中 30 天 refresh token 一旦被 XSS 读取即成为长期续签材料；CSP/Trusted Types 是重要防线但不是秘密存储。这个风险在包含 Monaco、PixiJS、玩家原创字符串、回放/调试视图的 Web UI 中尤其敏感。
- Required before implementation:
  - 明确 Web token 存储威胁模型：若坚持 localStorage，应加 refresh token family anomaly detection、device-bound proof、shorter browser TTL、XSS regression tests；或考虑 HttpOnly SameSite cookie + CSRF/Origin 防护与 application cert 分层。

### Low — 不安全 HTTP pinning 是 TOFU，文档承认首次 MITM，但缺少 out-of-band fingerprint 分发与轮换 UX 合同

- Category: UX gap / security gap
- Evidence:
  - `design/auth.md:334` 要求首次 HTTP 访问展示 `server_id + Server Root CA fingerprint`，用户人工确认并 pin。
  - `design/auth.md:339` 承认首次 pinning 前可被 MITM。
  - `RUNBOOK.md:101`–`RUNBOOK.md:102` 只给出查看 fingerprint 的运维命令。
  - `GETTING-STARTED.md:68` 仅写首次访问时确认 Root CA fingerprint。
- Risk:
  - TOFU 对本地/离线场景可接受，但若没有二维码、控制台、DNS TXT、签名公告或管理员 out-of-band channel，普通用户会习惯性点击确认，首次 MITM 风险变成实际可利用路径。
- Required before implementation:
  - 补充推荐 fingerprint 分发/核验流程、pin 变更/Root CA 轮换 UX、错误文案和“fingerprint changed” fail-closed 行为。

## Strengths

- 私钥边界清晰：`design/auth.md:221` 明确服务端默认永不接收或保存 private key，托管 key 被限制为短 TTL、窄 scope、不可签发 AdminCertificate（`design/auth.md:229`）。
- 用途隔离设计合理：`ClientAuthCertificate`、`CodeSigningCertificate`、`AdminCertificate` 分离 usage/scope/TTL（`design/auth.md:259`–`design/auth.md:264`），降低凭据横向滥用。
- Canonical request signature 覆盖关键重放字段：method/path/body_hash/timestamp/nonce/certificate_id/player_id/audience 均入签名 payload（`design/auth.md:311`–`design/auth.md:323`）。
- HTTP 不安全传输没有被误描述为机密通道：文档明确它只提供身份认证与完整性，不提供机密性/流量隐藏，并要求 nonce/timestamp（`design/auth.md:336`–`design/auth.md:342`）。
- 联邦身份默认本地重签：远端证书只作为 bootstrap proof，本地操作仍需目标服证书，且默认不接受远端 CodeSigning/AdminCertificate（`design/auth.md:1107`–`design/auth.md:1113`）。
- WASM sandbox 覆盖多层防线：wasmtime fuel/epoch/memory、WASI 禁用、seccomp/cgroup、恶意样本库、host function 成本表与 simulate 限额均有设计（`specs/core/04-wasm-sandbox.md:43`–`specs/core/04-wasm-sandbox.md:423`）。
- DoS 方面已有积极修正：恢复凭据 per-IP 限流位于 argon2id 之前，避免随机 username dummy argon2id 放大（`design/auth.md:720`–`design/auth.md:722`）。

## Questions / Assumptions

- 我假设本轮只审目标文档，不审代码实现，也不读取旧 reviews；结论只针对设计一致性与安全合同。
- `Gateway` 是无状态代理（`specs/12-gateway-protocol.md:17`），但 nonce/timestamp/replay cache 需要共享状态或 Auth/FDB 后端。实现前需明确 nonce cache 的一致性模型，尤其多 Gateway 水平扩展时的 single-use 保证。
- `AdminCertificate` “敏感操作可要求双签”是否意味着可配置，还是安全基线？安全建议是 CA/trust policy、rollback、global write、bulk revoke 必须强制双签。
- 恢复流程中 “默认保留旧证书” 是为多设备便利性还是临时占位？若设计目标包括 lost/compromised recovery，应改为按 recovery reason 默认吊销。
- `CodeSigningCertificate` TTL 在 `design/auth.md:262` 为 7d，在 `design/auth.md:972` 为 15 min–180 days，在 `design/auth.md:1507` 配置样例为 86400s。是否存在 profile-specific TTL 权威表？实现前需指定唯一默认值与最大值。
- `swarm_get_schema` / `swarm_get_docs` 在 `specs/security/03-mcp-security.md:250`–`specs/security/03-mcp-security.md:251` 标为无 scope 且无限制；我未列为 Top finding，因为内容可能静态可缓存，但仍建议至少有 IP/global cache rate limit，避免低成本 scraping 或 bandwidth DoS。
