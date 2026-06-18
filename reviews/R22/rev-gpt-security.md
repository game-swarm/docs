# R22 安全评审 (GPT-5.5)

## Verdict

CONDITIONAL_APPROVE

整体安全设计已经覆盖了关键攻击面：应用层证书、用途隔离、canonical request、WASM 沙箱、可见性统一过滤、DoS 预算、CVE SLA、持久化 hash 链等都有明确合同。相比常见 MMO/沙箱系统，设计意识成熟，尤其对“AI 玩家 = 不可信自动化客户端”的威胁模型处理较好。

但当前文档状态仍存在若干安全合同冲突与少量高风险缺口。它们不构成必须推倒重来的架构性失败，但在进入实现前必须统一权威源、修正不一致，并补足部署/对象存储/浏览器端边界。我的建议是：有条件通过设计方向，但将下列 High 项作为 R22 后续合并前阻塞条件。

## Critical

无明确 Critical。

## High

### H1. Auth API 与设计文档存在权威冲突，可能导致实现选择较弱认证路径

涉及文档：
- `design/auth.md`
- `specs/reference/api-registry.md`
- `specs/security/03-mcp-security.md`
- `specs/security/09-command-source.md`

问题：
`design/auth.md` 明确声明 Swarm 的唯一权威身份凭证是“应用层证书链 + 用户私钥签名”，refresh token/JWT 仅为 Web session 兼容层。但 `api-registry.md` 中 `auth_api` 仍暴露并权威登记了较传统的 token/session/device API：
- `swarm_auth_login` 返回 `{token, refresh_token, expiry, scope, player_id, session_id}`
- `swarm_auth_refresh` 只以 `{refresh_token}` 刷新
- Auth Token Envelope 继续定义 JWT access token 与 opaque refresh token
- `swarm_auth_cert_issue` / `swarm_auth_cert_rotate` / `swarm_auth_device_register` 与 `design/auth.md` 中 CSR、用途隔离证书、Server Intermediate CA 签发模型并不完全同构

安全影响：
实现者可能按 API Registry 的 token-first 语义实现主认证路径，使 bearer token 成为事实上的认证根，从而削弱 canonical request signature、证书用途隔离、audience 精确绑定和私钥持有证明。典型后果包括：
- refresh token 被盗后可绕过私钥签名完成长期会话延续；
- MCP/Agent endpoint 混入 Web token 兼容路径；
- scope/audience 被 JWT claim 替代而不是从证书链与签名 payload 双重验证；
- `swarm_auth_cert_issue` 被误实现为 admin 任意签发证书，而非 CSR proof + policy gate。

建议：
1. 将 API Registry 中 Auth API 改为与 `design/auth.md` 对齐的 CSR/certificate-first 模型，或明确标注 legacy/web-compat only。
2. 每个 auth tool 必须声明：是否允许 bearer token、是否必须 application certificate signature、是否仅限浏览器兼容层。
3. 对 `swarm_auth_refresh` 这类 refresh-token-only 工具增加 client public key proof / DPoP 风格签名要求，避免纯 bearer 续期。
4. CI 应检查 API Registry 与 auth design 中的 auth root 声明一致，防止“文档说证书、IDL 说 token”的漂移。

### H2. MCP 工具清单存在多处不一致，可能造成未审计端点或权限绕过

涉及文档：
- `specs/reference/api-registry.md`
- `specs/security/03-mcp-security.md`
- `design/auth.md`

问题：
文档间对 MCP 工具是否存在、是否移除、是否权威存在冲突。例如：
- `api-registry.md` 显示 `swarm_get_docs`、`swarm_get_schema`、`swarm_get_available_actions`、`swarm_explain_last_tick`、`swarm_list_modules` 为活跃工具。
- `03-mcp-security.md` 却在不同段落称这些工具“已移除”或被替换。
- `api-registry.md` 顶部写“共计 54 个活跃工具 + 11 Auth”，但变更记录又写 “56 active”。
- `design/auth.md` 的 MCP 工具列表包含大量 auth/recovery/federation 工具，而 API Registry 的 Auth API 只有 11 个且名称/语义不同。

安全影响：
安全控制依赖“所有端点都在 registry 中登记 required_scope / replay_class / visibility_filter / rate_limit_key”。如果文档冲突，实际实现可能出现：
- endpoint 存在但未被 security columns 覆盖；
- 已移除工具仍暴露但缺少测试；
- debug/docs/schema 类工具泄露内部数据；
- rate limit、visibility filter、admin scope 在不同来源中不一致。

建议：
1. 将 IDL YAML/API Registry 作为唯一接口权威；其他文档不得声明“已移除/替换”的相反事实，只能引用 registry。
2. 对每个 tool 强制 5 列安全属性：required_scope、subject_source、replay_class、visibility_filter、rate_limit_key。
3. CI 增加“文档引用工具名必须存在于 IDL，且状态一致”的检查。
4. 在 R22 合并前清理工具总数、活跃状态和 auth tool 命名，使安全评审能基于单一事实源。

### H3. 部署对象存储异步流程存在 TOCTOU 与激活前可用性缺口

涉及文档：
- `specs/reference/api-registry.md` § Deploy / Persistence
- `specs/core/05-persistence-contract.md`
- `specs/security/09-command-source.md`

问题：
持久化合同采用 FDB 先提交 manifest，object store 后异步上传；`api-registry.md` 的 Deploy Flow 中写：步骤 2 async upload，步骤 3 commit manifest，步骤 4 下一 tick boundary 按 blob_hash 从 object store 加载 WASM 并激活。`05-persistence-contract.md` 则允许 upload_status 为 `pending/uploading/failed`，且 FDB commit 成功即视为状态完整。

安全影响：
如果 deploy manifest 已提交但 blob 仍 pending，下一 tick 激活路径必须非常严格地检查 `upload_status == complete` 且 `Blake3(blob) == manifest.blob_hash`。否则可能出现：
- pending blob 被错误激活导致运行旧缓存或空对象；
- object store key 被预分配后内容尚未写完，触发 race；
- blob 上传失败但 manifest 长期存在，形成 deploy 状态混乱与 DoS；
- 若本地 object store 路径或 key 可预测，存在替换/混淆风险。

建议：
1. 明确 `swarm_deploy` 返回 accepted 仅表示 manifest accepted，不表示 module active。
2. 激活前必须检查 `upload_status == complete`、对象大小、content hash、module_hash、validation_policy_version/security_epoch 全部匹配。
3. pending/uploading 超过短 TTL 后应进入 failed，并阻止激活；不能由 tick hot path 长时间等待对象存储。
4. object_store_key 必须不可由客户端指定；应为 server-generated opaque key，并绑定 player_id/world_id/deploy_id/hash。
5. `swarm_get_deploy_status` 的状态机需区分 `manifest_committed`、`blob_uploaded`、`validated`、`activated`、`failed`。

### H4. 浏览器与 Agent transport 的边界仍有互相矛盾表述，存在跨协议混淆风险

涉及文档：
- `specs/security/03-mcp-security.md`
- `specs/security/09-command-source.md`
- `design/auth.md`

问题：
`03-mcp-security.md` 中区分 Browser endpoint（Origin/CSRF/cookie）与 Agent endpoint（application certificate signed request），并要求 Agent 端点拒绝 browser-style Origin/CSRF header。`09-command-source.md` 的 transport audience 表中又写 Browser WebSocket 可使用 “Web session token 或 application certificate”，REST Browser/CLI 同列为 `cli-rest`。这些边界语义不够干净。

安全影响：
浏览器安全模型与 agent/CLI 安全模型不同，混用会产生典型跨协议漏洞：
- 浏览器可被 CSRF/Origin 绕过诱导访问 Agent endpoint；
- Agent certificate 被用于 browser-ws 或 cookie session 被用于 CLI REST；
- transport audience 字符串被实现为宽松匹配，导致证书跨端点重放；
- CORS/Fetch Metadata 与 certificate signature 双栈入口互相降级。

建议：
1. 为 browser-http、browser-ws、agent-mcp、cli-rest、replay-viewer 建立互斥 endpoint 或互斥 route group。
2. 每个 route group 明确唯一可接受凭证类型；不要写“token 或 certificate”这种可降级语义。
3. `X-Swarm-Transport` 不能由客户端自报后直接信任，应由 route/listener 推导，再与证书 audience 比较。
4. Browser WS 如果使用 cookie session，应独立于 Agent WS；若使用 application certificate，则必须说明浏览器如何安全持有 non-extractable key 并签 per-message MAC。

### H5. Admin 权限边界过宽且部分 rate limit 文档写“无限制”

涉及文档：
- `specs/security/09-command-source.md`
- `design/auth.md`
- `specs/reference/api-registry.md`

问题：
`09-command-source.md` Source 矩阵中 Admin 的 rate_limit 为“无限制”，并允许写世界、读写全局存储、部署代码、查询世界、触发战斗。虽然后文提到 Admin 走标准 `validate_and_apply()` 管线、部分操作双签，但 Admin 能力面仍过宽，且与 `design/auth.md` 中 admin critical 需 challenge/double-sign/audit 的思路不完全一致。

安全影响：
Admin 是高价值攻击面。若实现按“无限制 + 可触发战斗 + 可部署代码”理解，单个 AdminCertificate 泄露会变成全服任意写入能力，且 DoS 限速缺失。

建议：
1. Admin 不应有“无限制”rate limit，应有 per-admin、per-world、per-target 的硬限制与冷却。
2. Admin gameplay mutation 必须分级：只读审计、配置变更、回滚、封禁、资产处置、紧急安全操作分离 scope。
3. “触发战斗”不应是通用 admin 能力；若保留，仅限 test/dev 或明确的裁判工具，并写 TickTrace/audit。
4. AdminCertificate 应强制短 TTL、硬件 key 优先、敏感操作双签/延迟执行/可撤销窗口。

## Medium

### M1. Wasmtime 版本锁定写法不完整，安全支持窗口不可验证

`04-wasm-sandbox.md` 写 `wasmtime = "=30.0"`。Cargo 精确版本通常需要完整 patch 版本，例如 `=30.0.0`；且文档没有声明当前锁定版本是否仍在 Bytecode Alliance 安全支持窗口内。

建议：
- 使用完整 semver pin，并在 `Cargo.lock` 层强制审计。
- CVE-SLA 中增加“当前 pinned version 支持状态”检查项；若 Wasmtime 无 LTS，需定义主动升级 cadence。
- 将 `wasmtime`, `wasmparser`, `cranelift-codegen` 的版本联动策略写清楚，避免 parser 与 runtime 策略漂移。

### M2. 沙箱 syscall 白名单前后不一致，可能导致 seccomp 策略实现偏差

`04-wasm-sandbox.md` 前文 seccomp 允许 `clone (仅 CLONE_VM | CLONE_VFORK)`，后续统一 OS 加固表又写 `fork/vfork/clone` 全禁，cgroup pids.max 前文为 32，后表为 16。

安全影响：
实现者可能选择较宽松的一版，尤其是 clone/vfork 对沙箱隔离非常敏感。

建议：
- 统一为一个权威 seccomp profile 表。
- 如果 Wasmtime 需要线程/clone，必须精确列出 flags、调用阶段和验证测试；否则默认全禁。
- cgroup pids.max 使用单一值，并为编译进程和运行进程分别定义。

### M3. WASM 模块体积上限在不同文档中冲突

`04-wasm-sandbox.md` 预校验限制 WASM module 5MB；`api-registry.md` Persistence Blob Types 写 `wasm_module` 最大 64MB；`03-mcp-security.md` HTTP max body size 5MB 且说与 WASM 模块体积一致。

安全影响：
体积上限不一致会影响 DoS 防线、网关 body limit、object store 配额和编译预算。攻击者可能通过路径差异绕过 5MB 限制进入 64MB blob 流程。

建议：
- 明确 raw upload limit、compressed limit、validated wasm limit、object store hard cap 四者关系。
- 网关、deploy validator、object store manifest 必须使用同一 limits manifest hash。

### M4. PoW 不能替代 CSR 提交限流，注册路径仍有存储与验证放大风险

`design/auth.md` 写 CSR 提交不设 IP/username 限速，PoW 本身就是速率控制。虽然 challenge 申请有 IP 限速，但攻击者可分布式获取 challenge 并提交大量有效 PoW。服务端仍需执行 FDB 事务、CSR parsing、签名验证、certificate issuance policy 等操作。

建议：
- CSR submit 也应有全局 admission control、per-IP soft limit、per-ASN/tenant 可选风控、签发队列上限。
- PoW 难度应动态调节并纳入 abuse telemetry。
- 对 CSR payload 大小、字段数量、base64 解码成本、证书链返回大小设硬限制。

### M5. 公开旁观与 replay privacy 的组合仍需默认安全策略

`05-visibility.md` 允许 `public_spectate=true` 时旁观者全地图实体，但要求 `spectate_delay >= 50` 且受 `replay_privacy` 过滤。文档说明较好，但默认策略需要更保守：World 模式默认 private、Arena 赛后 public。

建议：
- `public_spectate=true` 在 World 模式需显式 admin 双确认或配置注释确认风险。
- spectator 输出 schema 与玩家/MCP 输出 schema 分离，避免 accidentally including debug/internal fields。
- 对 spectator event 也要有字段 allowlist，不仅是 denylist。

### M6. Audit/ClickHouse 日志可能保存敏感参数，需要字段级脱敏策略

`03-mcp-security.md` 的 `mcp_audit` 表含 `parameters String`。虽然其他文档提到 token/private key 不得进日志，但这里没有字段级 redaction 合同。

建议：
- 审计日志保存 canonical hash + redacted preview，禁止完整 parameters 默认落库。
- 对 `csr`, `refresh_token`, `reset_token`, `email`, `recovery_password`, `wasm_bytes`, `certificate_chain`, `signature` 分别定义 redaction/hash 规则。
- 安全事件调查需要完整请求时，应使用短期加密隔离存储与 break-glass 审计。

### M7. `player_id = blake3(...)-> low64` 碰撞处理描述不充分

`design/auth.md` 认为 10^6 用户碰撞概率可接受，并注册时检测唯一索引冲突返回 `username_taken`。但如果不同 username 产生相同 low64 player_id，返回 `username_taken` 会造成语义混淆，也可能成为用户名枚举/拒绝服务边界问题。

建议：
- 单独返回内部 `player_id_collision_retry` 或使用更长内部 ID（u128），对外可压缩显示。
- collision 不应暴露为 username_taken。
- 联邦映射也应有 collision resolution 策略。

## Low

### L1. Canonical Request 时间单位不一致

`design/auth.md` canonical request 使用 unix_ms；WebSocket 握手示例使用 unix_seconds；不同窗口又写 ±30s。建议统一字段名与单位，例如所有外部协议均为 `unix_ms`，WS payload 也遵循同一 canonical codec。

### L2. 错误码命名存在漂移

不同文档出现 `stale_deploy`、`already_deployed`、`MissingTransportHeader`、`AudienceMismatch`、`NotEligible` 等，但 API Registry 的 RejectionReason 未完整登记这些 code。建议所有 wire-visible error code 统一进入 IDL registry。

### L3. Debug detail 与 visibility redaction 的关系需更明确

API Registry 支持 `debug_detail`，visibility 文档强调防 oracle。建议规定 competitive 模式下 debug_detail 默认关闭，practice/training 也必须经过 visibility-aware redaction。

## Informational / 亮点

1. 应用层证书用途隔离设计扎实：ClientAuth、CodeSigning、Admin、Federation 分离，scope/audience/usage 都进入验证流程。
2. 对不安全 HTTP 的边界描述清楚：认证与完整性可由应用层证书保证，但机密性、流量隐藏和首次 pinning 前 MITM 不保证。
3. WASM 沙箱采用多层防护：Wasmtime fuel、线性内存、epoch interruption、WASI 禁用、只读 host function、seccomp、cgroup、namespace、防 start section。
4. 可见性策略强调整个输出面共用 `is_visible_to`，并包含 omitted_count 分桶、特殊攻击拒绝码等价策略，明显是在防 oracle。
5. DoS 设计比常规文档更完整：host function per-call cost、pathfinding explored nodes、simulate 限额、argon2 semaphore、challenge rate limit、编译并发限制都有覆盖。
6. CVE-SLA 不只盯 Wasmtime，还列出 crypto/TLS/serde/tokio/libc 等 critical crates，并禁止为赶 SLA 放宽沙箱约束。
7. 持久化合同承认跨存储双写问题，用 FDB manifest + content hash + async upload status 明确失败语义，这是正确方向。

## CrossCheck — 需要跨方向检查

- CX1: API Registry 与 `design/auth.md`/`03-mcp-security.md` 的 Auth 工具、token 语义和工具总数存在冲突 → 建议 Architect 检查“IDL 是否为唯一权威源”以及 auth/web/session 兼容层如何在架构图中分层。
- CX2: Deploy async object store 的状态机需要与 tick 激活调度闭合 → 建议 Architect 检查 manifest commit、blob upload、validation、activation 四阶段是否有单一状态机，避免 pending blob 被 tick boundary 误激活。
- CX3: Browser/Agent/CLI/WebSocket transport 边界仍混杂 → 建议 Architect 检查路由拓扑是否能做到 endpoint 级凭证类型互斥，而不是依赖客户端自报 `X-Swarm-Transport`。
- CX4: visibility 文档允许 `player_view=full` 用于 non-competitive world → 建议 Gameplay/UX 检查哪些模式被定义为 competitive，以及配置验证是否能防止正式 World 误启 full view。
- CX5: Admin 操作能力面过宽 → 建议 Architect/Ops 检查 admin scope 分级、双签、冷却、break-glass 和审计留存是否满足实际运营需求。
- CX6: Wasmtime/seccomp/cgroup 限制表前后不一致 → 建议 Implementation/Infra 检查最终 Linux sandbox profile 是否可实现并能被 CI 自动验证。
