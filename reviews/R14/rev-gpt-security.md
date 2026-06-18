# R14 Phase 1 Clean-Slate 安全评审（GPT）

## Verdict

REQUEST_MAJOR_CHANGES

理由：整体安全目标正确，尤其是 MCP 不直接执行 gameplay、应用层证书 + 代码签名、统一可见性函数、WASM 多层沙箱等方向是成熟的。但当前文档内存在若干会直接影响安全实现的合同冲突：浏览器凭据存储策略前后矛盾、transport/audience 语法多版本并存、WebSocket 会话内免签与限流语义过宽、sandbox OS 边界描述互相冲突。这些不是实现细节，而是会导致不同组件各自按不同安全模型实现，最终形成认证绕过、跨 transport 重放、信息泄露或 DoS 缺口。因此建议在进入实现前做一轮安全合同收敛。

## Critical

本轮未发现必须判定为 Critical 的设计级问题。现有文档已经覆盖 CA 隔离、用途隔离证书、签名请求、PoW、CRL、可见性过滤、WASM fuel/cgroup/seccomp 等关键高风险面；主要问题是合同不一致与边界未闭合，严重度集中在 High。

## High

### H1 — 浏览器凭据存储策略自相矛盾，可能导致实现落入 localStorage 持久凭据模式

- severity: High
- 涉及文档：`design/auth.md`
- 问题：同一文档先声明“浏览器端 token/certificate material 禁止存 localStorage。使用 HttpOnly Secure cookie + WebCrypto non-extractable key 或 OS keychain”，但后续又在 Token 与会话安全中写明“使用 localStorage 存储 {refresh_token, certificate, client_public_key}”。这会让实现者无法判断权威策略。
- 风险：一旦按 localStorage 实现，任意 XSS 可直接窃取 refresh_token、certificate material 和 client_public_key；即使私钥不可导出，refresh_token 作为 Web session 兼容层仍可被滥用并触发 session family 风险。对于可编程 MMO，玩家原创字符串、回放、调试、文档渲染等都是长期 XSS 攻击面，不能把 CSP 当作唯一防线。
- 要求修改：统一为“长期 bearer material 禁止 localStorage”。推荐：refresh token 用 HttpOnly Secure SameSite=Strict cookie；私钥用 WebCrypto non-extractable key；certificate 可存 IndexedDB/Cache 但不可单独构成认证根；所有需要认证的请求仍必须完成签名或绑定 CSRF + audience。若为了 CLI/Agent 允许文件存储，必须只限非浏览器 transport。

### H2 — transport / audience 语法存在三套模型，可能导致跨 transport 重放或验签歧义

- severity: High
- 涉及文档：`design/auth.md`、`specs/security/03-mcp-security.md`、`specs/security/09-command-source.md`
- 问题：认证文档定义 audience 为 `transport:server_id:world_id:player_id`；MCP 安全文档描述为 `{server_id, world_id, "cli"}` / `server_id + world_id + transport`；Command Source 又定义为 `mcp:{server_id}:{world_id}:{player_id}`、`ws:{...}`、`rest:{...}`、`replay:{...}`。三套写法字段顺序、transport 取值和 player/match 语义均不一致。
- 风险：Gateway、Auth Service、Engine 若分别按不同文档实现，会出现“证书验签通过但 audience 判断不一致”的漏洞；典型后果包括 MCP 证书用于 WebSocket、REST token 用于 Agent endpoint、Replay audience 被普通请求复用，或某层认为 audience 已验证而另一层实际未验证。
- 要求修改：指定唯一 canonical audience grammar，例如 `swarm-aud-v1:<transport>:<server_id>:<world_id>:<subject_id>`，其中 transport 枚举固定为 `browser-http | browser-ws | agent-mcp | cli-rest | replay-viewer`。所有证书、JWT、DeployPayload、WebSocket 握手、canonical request 必须引用同一语法；旧写法全部删除或标注废弃。

### H3 — WebSocket 握手后“后续消息免签名且不计入 per-tick rate limit”过宽

- severity: High
- 涉及文档：`design/auth.md`、`specs/security/03-mcp-security.md`
- 问题：WebSocket 握手要求签名是正确方向，但“后续消息免签名（会话内信任）”与“会话内消息不计入 per-tick rate limit”组合过宽。MCP 查询、调试、simulate、docs/schema 读取等都可通过长连接形成高频请求路径。
- 风险：最小成本的单次签名握手可以换取大量服务端工作：快照构建、可见性过滤、path/simulate、debug trace 聚合、SSE/WS delta 发送等。若连接被劫持、浏览器端 XSS 控制已认证 WS、或客户端实现缺陷导致重放 session message，攻击者可绕过签名成本和每 tick 限流。
- 要求修改：WebSocket 可以免每条 Ed25519 签名，但必须保留每消息的 server-side session sequence、method-level rate limit、per-player/per-connection budget、message size limit、JSON-RPC batch 禁用、heartbeat timeout 和 backpressure。文档中“不计入 per-tick rate limit”应改为“不重复执行握手级认证，但所有工具调用仍计入 method/player/connection/global 限流”。

### H4 — WASM sandbox OS 边界描述冲突，容易产生错误隔离实现

- severity: High
- 涉及文档：`specs/core/04-wasm-sandbox.md`
- 问题：沙箱架构写“无网络命名空间”，后文 checklist 又要求独立 net namespace 且无网络接口；seccomp 初始白名单允许 `clone (仅 CLONE_VM | CLONE_VFORK)`，后文 checklist 又写 `clone` 禁止；cgroup CPU/pids 限制在不同章节分别是 `cpu.max = 250000 3000000` / `50000 100000`、`pids.max = 32` / `16`。
- 风险：沙箱边界是安全关键路径，文档矛盾会让实现者选择较宽配置，或 CI 按另一套配置验证而生产按不同配置运行。尤其 clone/fork/thread、net namespace、CPU quota 不一致，可能导致逃逸面扩大或 DoS 预算失真。
- 要求修改：把 sandbox baseline 收敛成唯一权威表：namespace 必须为独立 pid/net/mnt/ipc/uts；net namespace 内无外部接口；seccomp 默认禁止 clone/fork/exec，若 Wasmtime 必需线程则仅在 compile worker 而非 execution worker 放行并写明 flags；cgroup CPU/pids 只保留一组生产默认值；CI checklist 必须与生产默认逐项一致。

## Medium

### M1 — Auth DoS 预算仍存在 PoW 与存储放大窗口

- severity: Medium
- 问题：CSR 提交“不设 IP/username 限速 — PoW 本身就是速率控制”，但 challenge 申请与 CSR 验证仍涉及 FDB challenge 读写、CSR parsing、Ed25519 验签、证书签发前置校验。默认 PoW=24 对 Rust native 约 150ms，对 botnet 或 GPU 并不构成强限制。
- 风险：攻击者可以用大量已求解 PoW 的 CSR 提交制造 FDB 写冲突、challenge 消费、证书审计写入压力，或用大量唯一 username 绕过 per-account 限制。
- 建议：CSR 提交仍应有全局、per-IP / per-prefix、per-username-prefix 或 proof-of-work-adjusted token bucket；PoW 作为成本因子而不是唯一限流。证书签发前应先做廉价 schema/长度/username 检查，复杂验签和事务写入后置。

### M2 — Admin source 矩阵显示“无限制”与后文冷却/双签要求冲突

- severity: Medium
- 问题：Command Source 矩阵中 Admin rate_limit 写“无限制”，但 auth 与 MCP 文档中又要求 AdminCertificate、双签、冷却、审计和 per-target 限制。
- 风险：实现者可能把 admin endpoint 从通用 rate limiter 中排除，导致被盗 admin cert 或误操作脚本可批量执行高危操作。
- 建议：删除“无限制”，改为“bypass gameplay player limit, still subject to admin method cooldown/global safety limiter”。所有 admin_critical 操作必须有 idempotency_key、cooldown、审计、可回滚策略。

### M3 — ClickHouse MCP 审计日志记录 parameters，需明确脱敏与上限

- severity: Medium
- 问题：MCP audit 表包含 `parameters String`，但安全文档同时要求 reset_url、refresh_token、私钥、证书材料、recovery token 不进日志。当前没有为 MCP 参数审计定义字段级 redaction schema。
- 风险：部署、认证、恢复、agent handoff 等调用参数中可能出现 token、email、证书链、CSR、metadata 或玩家原创字符串。全量 parameters 进入 ClickHouse 会形成长期敏感数据仓库。
- 建议：审计日志改为结构化 allowlist：`method, principal, param_hash, redacted_param_preview, object_id, result_code, latency`。对 token/certificate/signature/csr/email/reset_url/private material 默认只存 hash 或后缀掩码；每个 MCP tool schema 标注 audit policy。

### M4 — `swarm_get_docs` / `swarm_get_schema` 无认证且按 tick 限流，需补充 HTTP 缓存与全局限额

- severity: Medium
- 问题：开发辅助工具中 schema/docs 可无 scope 获取，限制为 5/tick 且单次 ≤1MB。若未认证端点按 tick 计数，攻击者可从多连接/IP 形成带宽与序列化放大。
- 风险：静态或半静态文档接口成为低成本 DoS 面，尤其在 MCP/HTTP JSON-RPC 路径中会占用网关与序列化资源。
- 建议：docs/schema 应尽量走静态文件/CDN/ETag/immutable cache，未认证请求增加 per-IP、global egress、response compression budget；动态 world_rules 才需要认证和 tick 语义。

### M5 — 旁观者全地图 WebSocket 需要连接级与订阅级防滥用合同

- severity: Medium
- 问题：`public_spectate=true` 可向未登录客户端推送延迟全地图实体，已有 `spectate_delay` 和 replay_privacy 过滤，但未定义旁观者连接数、订阅房间数、delta 大小、历史追赶和断线重连预算。
- 风险：未登录 spectator 可成为高带宽 fanout DoS 面；Last-Event-ID / WS reconnect 若处理不当，可能请求大量历史 delta。
- 建议：增加 spectator-specific rate limit：per-IP connections、per-world anonymous subscribers、max delta bytes/sec、max catch-up ticks、drop policy、proof-of-work 或 login gate for large worlds。

## Informational

### I1 — 设计亮点：MCP 与 WASM 权限边界清晰

MCP 不提供 `swarm_move` / `swarm_attack` 等 gameplay 直接控制工具，AI 与人类都必须通过 WASM 沙箱产生 deferred command。这避免了“AI 专属特权控制面”这一类常见架构漏洞，也让 fuel metering 与反作弊模型更统一。

### I2 — 设计亮点：统一可见性函数是正确的反 oracle 方向

`is_visible_to(entity, player_id, tick)` 被要求覆盖 snapshot、MCP、WebSocket、REST、replay 和 host functions，并补充了 `omitted_count` 分桶、特殊攻击拒绝码等价策略。这对防 IDOR、调试接口越权、错误码 oracle 都很关键。

### I3 — 设计亮点：WASM 沙箱采用多层防御

Wasmtime fuel、epoch interruption、线性内存限制、模块预校验、start section 拒绝、WASI 禁用、只读 host function、cgroup/seccomp/namespace、恶意样本 CI，这些组合符合高风险用户代码执行场景的基本要求。

### I4 — 设计亮点：证书用途隔离与代码签名模型较完整

`ClientAuthCertificate`、`CodeSigningCertificate`、`AdminCertificate` 分离，DeployPayload 包含 domain separator、module_hash、metadata_hash、world_id、module_slot、version_counter，并由服务端从证书覆盖 player_id，能有效降低 mass assignment 与跨协议重放风险。

## CrossCheck — 需要跨方向检查

- CX1: sandbox worker “每 tick fork → 执行 → kill”的成本模型可能与 500 玩家/3s tick 的性能目标冲突；若后续为性能改成长生命周期 worker，会改变安全边界 → 建议 Architect 检查 worker 生命周期、进程池、隔离强度与 tick SLA 的一致性。
- CX2: `fog_of_war=true` 且 `player_view=full` 被禁止用于 competitive world，但配置中又列出教学/合作可关闭 fog；需要确认 world mode / competitive 标志是否唯一权威 → 建议 Architect 检查 world.toml 配置状态机，避免服主误配导致公平性破坏。
- CX3: Browser 与 Agent endpoint 分离依赖 nginx/gateway 路由、Origin/CSRF、application certificate 验证；文档未展示完整路由优先级与 fallback 策略 → 建议 Architect 检查网络拓扑和 Gateway route table 是否能防 endpoint confusion。
- CX4: `swarm_simulate` 在线模拟给每玩家每小时 50M fuel、并发 3、单次 5s CPU；在大世界中可能仍对调度产生明显压力 → 建议 Architect/Performance 检查 simulate 是否必须迁移到独立 worker pool，与 tick engine 隔离。
- CX5: 管理员恢复链接要求双 admin + 用户邮箱/out-of-band，但离线部署可能没有邮箱服务 → 建议 Game Designer/UX 检查离线自托管场景下的安全恢复流程是否可用且不诱导管理员绕过双签。

## 建议的阻断项清单

进入实现前至少完成以下安全合同收敛：

1. 删除 localStorage 持久凭据方案，统一浏览器凭据存储权威策略。
2. 统一 audience grammar，并在 auth、MCP、Command Source 三处只保留同一版本。
3. 修改 WebSocket 会话内限流语义：免重复握手，不免工具级限流。
4. 收敛 sandbox OS baseline：namespace、seccomp、cgroup、CI checklist 一致。
5. 为 MCP audit parameters 定义字段级 redaction / hash policy。
6. 为 CSR、docs/schema、spectator、simulate 补充全局与连接级 DoS budget。
