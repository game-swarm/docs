# R30 Security Review — rev-gpt-security

## 1. Verdict

REQUEST_MAJOR_CHANGES

理由：整体安全架构方向是正确的，应用层证书、用途隔离、CSR/PoW、WASM 沙箱和可见性统一函数都有较强安全意识；但当前文档存在多处安全合同冲突，尤其是 WebSocket 会话内消息认证、CSR admission control、Admin rate limit、sandbox 网络隔离语义。这些冲突会直接导致实现者选择较弱路径，形成认证重放、DoS、越权管理面滥用或沙箱 defense-in-depth 缺口，必须在设计目标状态中统一。

## 2. 发现的问题

### S-H1 — WebSocket 会话内消息认证合同互相冲突，可能允许认证后会话内注入/重放

Severity: High

文件引用：
- `/tmp/swarm-review-R30/design/auth.md:779`
- `/tmp/swarm-review-R30/design/auth.md:797`
- `/tmp/swarm-review-R30/design/auth.md:800`
- `/tmp/swarm-review-R30/specs/security/03-mcp-security.md:159`
- `/tmp/swarm-review-R30/specs/security/03-mcp-security.md:160`
- `/tmp/swarm-review-R30/specs/security/03-mcp-security.md:162`
- `/tmp/swarm-review-R30/specs/reference/api-registry.md:386`
- `/tmp/swarm-review-R30/specs/reference/api-registry.md:388`
- `/tmp/swarm-review-R30/specs/reference/api-registry.md:392`

问题描述：
`design/auth.md` 的 WebSocket 证书握手要求只在连接建立时验签，并明确写出“后续消息免签名”；但 `03-mcp-security.md` 和 API Registry 都要求 Agent WS 每条消息携带递增 seq + MAC/Ed25519 签名，且 seq 回退或 MAC 不匹配即断开。两者对同一 WebSocket 安全模型给出相反合同。

影响分析：
如果实现者按 `design/auth.md` 的较弱语义实现，WebSocket 一旦建立，只依赖连接级状态。任何代理层混淆、连接复用 bug、服务端会话绑定 bug、反向代理注入、客户端 SDK bug 或同进程恶意插件都可能在认证后通道内注入、重放或重排消息。对 Agent WS 这类可触发部署、查询、调试的高价值通道，缺少 per-message seq/signature 会扩大单次连接劫持后的影响范围，也削弱审计中每条消息的不可抵赖性。

修复建议：
统一目标状态为强合同：WebSocket 握手只负责建立身份和会话密钥/证书绑定；所有 Agent/CLI 可写或敏感 WS 消息必须携带严格递增 `seq` 与签名/MAC，签名 payload 至少覆盖 `domain separator + session_id + seq + tick? + body_hash + audience`。删除或改写 `design/auth.md` 中“后续消息免签名”的表述。Browser spectator/read-only WS 可以保留只读无 per-message 签名，但必须明确它不能发送任何状态变更或认证消息。

### S-H2 — CSR 提交 admission control 自相矛盾，DoS 防护可能被降级为仅 PoW

Severity: High

文件引用：
- `/tmp/swarm-review-R30/design/auth.md:840`
- `/tmp/swarm-review-R30/design/auth.md:842`
- `/tmp/swarm-review-R30/design/auth.md:847`
- `/tmp/swarm-review-R30/design/auth.md:848`
- `/tmp/swarm-review-R30/design/auth.md:849`
- `/tmp/swarm-review-R30/design/auth.md:850`
- `/tmp/swarm-review-R30/design/auth.md:853`
- `/tmp/swarm-review-R30/design/auth.md:932`
- `/tmp/swarm-review-R30/design/auth.md:934`
- `/tmp/swarm-review-R30/design/auth.md:940`

问题描述：
同一文档先定义 CSR admission control 为多层防护：PoW、Per-IP、Per-ASN、Global in-flight cap、worker semaphore、bounded queue、audit throttle；但后续未认证端点保护表又声明 CSR 提交“PoW 自身限速 / 无额外 IP 限制”。这与前面的安全设计理由直接冲突。

影响分析：
PoW 是 per-request 成本，不是服务端资源隔离机制。云主机、僵尸网络或 GPU/多核来源可以并行求解 PoW，把攻击流量集中到服务端 CSR 验签、证书签发、审计写入和队列资源上。如果实现者采用后表“无额外 IP 限制”，CSR 提交会成为注册/证书签发 DoS 放大面，尤其是在 Auth Service 需要访问 HSM/KMS 或执行签名审计时。

修复建议：
删除 `CSR 提交 | PoW 自身限速 | 无额外 IP 限制` 的弱合同，统一为多层 admission control。未认证端点保护表应引用 §10.7 的 L1-L6，并明确默认启用 Per-IP、Per-ASN、global in-flight、worker queue timeout 和熔断；PoW 只作为第一层成本过滤，不能替代速率限制。API Registry/Auth IDL 中也应机器可读表达这些 rate limit 维度，防止 codegen 丢失。

### S-H3 — Admin 来源被声明为“无限制”，与 Admin API rate limit/critical replay class 冲突

Severity: High

文件引用：
- `/tmp/swarm-review-R30/specs/security/09-command-source.md:15`
- `/tmp/swarm-review-R30/specs/security/09-command-source.md:20`
- `/tmp/swarm-review-R30/specs/reference/api-registry.md:304`
- `/tmp/swarm-review-R30/specs/reference/api-registry.md:306`
- `/tmp/swarm-review-R30/specs/reference/api-registry.md:308`
- `/tmp/swarm-review-R30/specs/reference/api-registry.md:313`
- `/tmp/swarm-review-R30/design/auth.md:312`
- `/tmp/swarm-review-R30/design/auth.md:322`

问题描述：
Command Source Model 的来源矩阵将 `Admin` 的 `rate_limit` 标为“无限制”，但 API Registry 对 admin 工具有 `10/h`、`5/h`、`30/tick` 等明确限制，并将多数管理操作标为 `admin_critical`。`design/auth.md` 也要求 `admin_critical` 使用 FDB challenge/counter 与双签审计。

影响分析：
Admin 面通常是最高价值攻击面。即使请求持有 AdminCertificate，也必须默认假设管理员凭据可能被盗、浏览器会话可能被劫持、内部系统可能误调用。若“无限制”成为实现依据，攻击者可批量触发 world config 热更新、rollback、ban、force GC、证书吊销/签发等操作，造成控制面 DoS、审计日志膨胀、配置抖动或批量破坏。Admin 权限高不等于不需要 rate limit；相反应有更严格冷却、双签、idempotency key 和异常检测。

修复建议：
将 `09-command-source.md` 中 Admin `rate_limit` 改为“按 API Registry/admin_critical 策略”，并明确所有 Admin 操作都必须有 per-admin、per-target 或 per-world 限速；安全敏感操作必须使用 FDB 事务内 nonce/counter、idempotency key、审计和可选双签。若存在 emergency break-glass 路径，也应单独建模：短 TTL、双人授权、全量审计、全局冷却，而不是普通 Admin 无限速。

### S-H4 — 沙箱网络隔离语义冲突，削弱 seccomp 之外的 defense-in-depth

Severity: High

文件引用：
- `/tmp/swarm-review-R30/specs/core/04-wasm-sandbox.md:21`
- `/tmp/swarm-review-R30/specs/core/04-wasm-sandbox.md:24`
- `/tmp/swarm-review-R30/specs/core/04-wasm-sandbox.md:248`
- `/tmp/swarm-review-R30/specs/core/04-wasm-sandbox.md:249`
- `/tmp/swarm-review-R30/specs/core/04-wasm-sandbox.md:264`
- `/tmp/swarm-review-R30/specs/core/04-wasm-sandbox.md:266`
- `/tmp/swarm-review-R30/specs/core/04-wasm-sandbox.md:379`
- `/tmp/swarm-review-R30/specs/core/04-wasm-sandbox.md:390`

问题描述：
沙箱架构图和网络命名空间章节写“无网络命名空间”，但后续 OS 加固 checklist 又要求 `net` 为独立网络栈、无网络接口。两种语义安全强度不同：前者可能表示不创建 net namespace、共享宿主网络；后者表示创建隔离 net namespace 并移除接口。

影响分析：
当前设计主要依赖 seccomp 禁止 `socket/connect/sendmsg/recvmsg` 来阻断网络。如果沙箱实际共享宿主网络，一旦 Wasmtime、seccomp profile、允许 syscall 组合、Unix socket fd 传递或未来放宽项出现漏洞，攻击者可能获得宿主网络可达性，进而扫描内网、访问 metadata service、攻击 FoundationDB/Dragonfly/ClickHouse 或其他本机服务。沙箱应采用多层隔离：即使 seccomp 失效，net namespace 仍应阻断网络。

修复建议：
统一为强合同：每个 sandbox worker 必须运行在独立 network namespace，默认无外部网络接口，仅保留必要的 Unix domain socket fd 与 Engine 通信；禁止共享宿主网络。`04-wasm-sandbox.md` 的“无网络命名空间”应改为“独立网络命名空间，无外部网络接口”。CI checklist 保留 `ip netns`/`lsns` 验证，并增加对 metadata IP、RFC1918、loopback 非授权端口不可达的测试。

### S-M1 — 不安全传输中的敏感 payload 加密要求过弱，恢复链路可被被动窃听

Severity: Medium

文件引用：
- `/tmp/swarm-review-R30/design/auth.md:406`
- `/tmp/swarm-review-R30/design/auth.md:413`
- `/tmp/swarm-review-R30/design/auth.md:415`
- `/tmp/swarm-review-R30/design/auth.md:1011`
- `/tmp/swarm-review-R30/design/auth.md:1024`
- `/tmp/swarm-review-R30/design/auth.md:1029`
- `/tmp/swarm-review-R30/design/auth.md:1034`
- `/tmp/swarm-review-R30/design/auth.md:1260`
- `/tmp/swarm-review-R30/specs/security/03-mcp-security.md:116`

问题描述：
设计允许 HTTP 等不安全传输通过应用层证书完成认证和完整性校验，并承认攻击者可观察流量元数据与阻断请求。对恢复 token、私密邮箱、管理员恢复链接等敏感 payload，文档使用“应加密给服务器应用层证书 public key”，不是强制 MUST。同时浏览器存储策略又要求“仅 HTTPS”，造成不同客户端路径下机密性要求不一致。

影响分析：
应用层签名只能提供身份认证和完整性，不能提供机密性。邮箱恢复 token、admin recovery link、绑定邮箱、reset_token、可能的 handoff code 如果在 HTTP 明文传输或 URL 中出现，被旁路监听者获取后可能导致账号恢复流程被劫持。尤其离线/内网部署常被误认为“可信网络”，但实际存在 Wi-Fi、办公网、代理、日志和网关抓包风险。

修复建议：
把敏感恢复/管理 payload 的加密从 SHOULD 升级为 MUST。目标状态建议：所有 recovery/admin/bootstrap token 在不安全传输上必须使用服务器应用层加密公钥做 HPKE/age-like envelope encryption，且 token 不得出现在 URL query、Referrer 或访问日志；浏览器路径强制 HTTPS；CLI/Agent 若使用 HTTP，必须先完成 root fingerprint pinning，并对敏感 payload 端到端加密。未加密敏感 payload 的请求直接拒绝。

### S-M2 — Refresh token 和证书生命周期在 Auth 设计与 API Registry 中不一致，可能导致过宽有效期

Severity: Medium

文件引用：
- `/tmp/swarm-review-R30/design/auth.md:1234`
- `/tmp/swarm-review-R30/design/auth.md:1239`
- `/tmp/swarm-review-R30/design/auth.md:1279`
- `/tmp/swarm-review-R30/design/auth.md:1797`
- `/tmp/swarm-review-R30/design/auth.md:1798`
- `/tmp/swarm-review-R30/design/auth.md:1801`
- `/tmp/swarm-review-R30/specs/reference/api-registry.md:568`
- `/tmp/swarm-review-R30/specs/reference/api-registry.md:572`
- `/tmp/swarm-review-R30/specs/reference/api-registry.md:577`
- `/tmp/swarm-review-R30/specs/reference/api-registry.md:579`

问题描述：
`design/auth.md` 将 `refresh_token` TTL 定为 30 days，配置参考也是 30 天；API Registry/Auth IDL 的 Auth 限制则写 `Refresh token lifetime = 7d`。`design/auth.md` 的证书 TTL 多处为 15 min–180 days 或 30–180 days，但 API Registry 写 `Cert validity max = 365d`。这些是安全边界参数，不应多源分叉。

影响分析：
生命周期上限直接影响凭据泄露后的攻击窗口、CRL 保留窗口、session family revoke 成本和合规风险。如果实现者从 API Registry/codegen 得到 365d cert 或 7d refresh，而前端/文档/运维按 180d/30d 设计，会出现用户体验和安全预期不一致；更严重的是实现者可能取最大宽松值，导致长期 bearer material 或证书过宽有效期。

修复建议：
选定唯一权威值并同步所有文档与 IDL。安全建议：refresh token 默认 7d 或更短，支持受信设备通过证书续签而不是长期 refresh；ClientAuthCertificate 默认 24h/短周期自动续签，CodeSigningCertificate 默认 30d、上限 180d；AdminCertificate 上限 1h。API Registry 应作为机器可读权威，设计文档只引用，不重复声明可冲突数值。

### S-M3 — API Registry 中旧 token auth 工具与应用层证书唯一权威模型并存，存在降级认证路径歧义

Severity: Medium

文件引用：
- `/tmp/swarm-review-R30/design/auth.md:1270`
- `/tmp/swarm-review-R30/design/auth.md:1272`
- `/tmp/swarm-review-R30/design/auth.md:1283`
- `/tmp/swarm-review-R30/design/auth.md:1285`
- `/tmp/swarm-review-R30/specs/reference/api-registry.md:246`
- `/tmp/swarm-review-R30/specs/reference/api-registry.md:250`
- `/tmp/swarm-review-R30/specs/reference/api-registry.md:251`
- `/tmp/swarm-review-R30/specs/reference/api-registry.md:350`
- `/tmp/swarm-review-R30/specs/reference/api-registry.md:351`
- `/tmp/swarm-review-R30/specs/reference/api-registry.md:699`
- `/tmp/swarm-review-R30/specs/reference/api-registry.md:703`

问题描述：
Auth 设计明确“唯一权威凭证是应用层证书链 + 用户私钥签名”，JWT/access_token 不是独立认证根。但 API Registry 仍注册 `swarm_auth_login`、`swarm_auth_refresh`、`swarm_auth_check` 等 token 生命周期工具，并定义 JWT Access Token envelope。当前文本虽称 token 是 Web 兼容层，但 Registry 中的 required_scope/replay_class/subject_source 容易被实现为通用 MCP 认证路径。

影响分析：
如果 token 工具被实现为可直接授予 MCP/Agent 主路径权限，应用层证书模型会被 bearer token 降级。Bearer token 一旦泄露，不需要私钥即可访问 API；这会削弱 canonical request signature、audience 绑定、non-extractable key 与用途隔离证书的整体设计。历史上大量 API 滥用来自“兼容 token”意外成为主认证根。

修复建议：
在 API Registry/Auth IDL 中机器可读标注 token 工具仅属于 `browser_web_compat` profile，不可用于 `agent-mcp`/`cli-rest` 主认证路径；所有非浏览器 MCP/Agent 请求必须有应用层证书链和签名。`swarm_auth_check` 等工具若保留，应只校验 Web session 状态，不得作为 Engine principal 注入来源。Gateway 必须拒绝用 Bearer token 调用 Agent endpoint。

### S-L1 — 供应链签名策略覆盖 mod 包，但未闭合依赖与构建 provenance

Severity: Low

文件引用：
- `/tmp/swarm-review-R30/design/README.md:149`
- `/tmp/swarm-review-R30/design/README.md:160`
- `/tmp/swarm-review-R30/specs/security/CVE-SLA.md:30`
- `/tmp/swarm-review-R30/specs/security/CVE-SLA.md:32`
- `/tmp/swarm-review-R30/specs/security/CVE-SLA.md:58`
- `/tmp/swarm-review-R30/specs/security/CVE-SLA.md:77`

问题描述：
设计说明 vanilla mod 通过 submodule 固定版本，并发布 Ed25519 签名 `.swarm-mod` 包；CVE-SLA 覆盖 Wasmtime 与 critical Rust crates。但文档未明确 mod 包签名的 provenance、CI 构建身份、依赖锁文件签名、SLSA/in-toto attestations、submodule 更新审计和第三方 mod trust policy。

影响分析：
签名包只能证明“某个 key 签过此包”，不能证明包来自预期源码、预期 CI、预期依赖锁或未被构建环境污染。第三方 mod 和 vanilla submodule 都是供应链入口；一旦构建 key、CI runner 或 submodule 引用被污染，攻击者可分发被签名的恶意规则包。

修复建议：
补充供应链目标状态：每个 `.swarm-mod` 包包含 source commit、submodule commit、lockfile hash、builder identity、CI run id、artifact hash；发布时生成 Sigstore/cosign 或 Ed25519 + in-toto/SLSA provenance；engine 安装 mod 时验证签名、provenance、world trust policy 和 revocation list。第三方 mod 默认不信任，需 operator 显式 pin key/fingerprint。

## 3. 亮点

- 应用层证书而非 TLS client cert 作为身份根，且明确 Swarm CA 不进入系统/浏览器 trust store，避免自托管 CA 被误用为通用 TLS 信任根（`/tmp/swarm-review-R30/design/auth.md:26`, `/tmp/swarm-review-R30/design/auth.md:33`, `/tmp/swarm-review-R30/design/auth.md:136`）。
- 用途隔离证书模型清晰：ClientAuth、CodeSigning、Admin、Federation 分离，usage/scope/audience/ttl 明确，能降低单一凭据被横向滥用的风险（`/tmp/swarm-review-R30/design/auth.md:267`, `/tmp/swarm-review-R30/design/auth.md:271`, `/tmp/swarm-review-R30/design/auth.md:278`）。
- CSR/PoW 设计避免客户端回传 challenge/difficulty 造成降级攻击，服务端从 FDB 读取权威 challenge 并在事务内消费，方向正确（`/tmp/swarm-review-R30/design/auth.md:625`, `/tmp/swarm-review-R30/design/auth.md:627`, `/tmp/swarm-review-R30/design/auth.md:642`）。
- 可见性设计坚持所有输出面统一调用 `is_visible_to`，并显式考虑 host functions、MCP、WS、REST、Replay、Spectator 的 oracle 风险，安全边界意识强（`/tmp/swarm-review-R30/specs/security/05-visibility.md:7`, `/tmp/swarm-review-R30/specs/security/05-visibility.md:13`, `/tmp/swarm-review-R30/specs/security/05-visibility.md:77`）。
- WASM 沙箱多层资源限制比较完整：Wasmtime fuel、epoch interruption、线性内存、cgroup、seccomp、禁 WASI 文件/网络/时钟、host function 白名单、恶意样本 CI 都有覆盖（`/tmp/swarm-review-R30/specs/core/04-wasm-sandbox.md:47`, `/tmp/swarm-review-R30/specs/core/04-wasm-sandbox.md:101`, `/tmp/swarm-review-R30/specs/core/04-wasm-sandbox.md:233`, `/tmp/swarm-review-R30/specs/core/04-wasm-sandbox.md:268`）。
- CVE-SLA 将 Wasmtime 与 critical Rust crates 纳入响应流程，并禁止为了赶 SLA 放宽沙箱限制，这是正确的供应链安全底线（`/tmp/swarm-review-R30/specs/security/CVE-SLA.md:5`, `/tmp/swarm-review-R30/specs/security/CVE-SLA.md:21`, `/tmp/swarm-review-R30/specs/security/CVE-SLA.md:62`）。
- Persistence contract 将 replay-critical subset 与 debug/rich blob 分离，FDB commit 作为唯一权威点，并用 content hash 绑定 object store，有助于避免跨存储双写破坏安全审计（`/tmp/swarm-review-R30/specs/core/05-persistence-contract.md:9`, `/tmp/swarm-review-R30/specs/core/05-persistence-contract.md:30`, `/tmp/swarm-review-R30/specs/core/05-persistence-contract.md:111`）。

## 4. CrossCheck — 需要跨方向检查

- CX-1: API Registry 与设计文档多处重复声明安全参数并产生冲突 → 建议 API/Docs 方向检查 IDL codegen 是否能表达 transport profile、rate limit、TTL、replay class 的单一权威来源。
- CX-2: WebSocket Agent per-message signature 会影响 SDK ergonomics 和连接性能 → 建议 Interface/SDK 方向检查官方 SDK 是否默认封装 seq/signature、断线恢复和错误处理，避免用户手写出错。
- CX-3: `fog_of_war=false` 的教学/合作世界允许 drone snapshot 全图 → 建议 Gameplay/Mode 方向检查该配置是否必须标记 non-competitive，并禁止排行榜/奖励/跨世界资产收益。
- CX-4: Room-partition FDB 事务的 2PC fallback to best-effort 可能影响 replay/security invariants → 建议 Persistence/Determinism 方向检查跨 room 操作失败语义是否仍 deterministic、可审计且不可被玩家利用套利。
- CX-5: Admin 操作统一走 `validate_and_apply()` 并放宽所有权检查 → 建议 Engine/Permissions 方向检查 trait 边界是否能表达最小权限，避免 Admin 路径意外获得非必要 world mutation 能力。
- CX-6: 第三方 mod 签名与 provenance 尚未完全闭合 → 建议 Supply Chain/Modding 方向检查 `.swarm-mod` 包格式、信任策略、吊销机制和 reproducible build 合同。
