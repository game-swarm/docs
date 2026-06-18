# R15 Phase 1 Clean-Slate 安全评审（GPT-5.5）

## Verdict

REQUEST_MAJOR_CHANGES

R15 在应用层证书、用途隔离、Source Gate、可见性统一函数、WASM 沙箱和 CVE SLA 上已经显著补强，整体方向正确。但当前设计仍存在多处会影响安全边界可证明性的冲突：WebSocket 握手时间单位和后续消息免签语义不一致、MCP/REST 方法矩阵覆盖不足导致授权/限流/可见性不可验证、sandbox OS 隔离规格自相矛盾、无状态 admin challenge 不能提供一次性语义，以及未认证 CSR/PoW 路径存在可被低成本请求放大的存储与 CPU 风险。建议在进入实现前修正这些合同，否则实现会被迫在冲突设计之间自行取舍。

## Critical

无。

## High

### H1: WebSocket 认证后“会话内免签”形成长期连接劫持放大面

- 位置：`design/auth.md` WebSocket 证书握手；`specs/security/03-mcp-security.md` Browser/Agent transport；`specs/security/09-command-source.md` transport audience。
- 问题：WebSocket 升级阶段做证书链、nonce、timestamp 验证后，后续消息“免签名（会话内信任）”。这对只读订阅尚可讨论，但对 MCP 查询、调试、部署状态、设备管理等长连接复用场景，连接一旦被同进程恶意脚本、代理层 bug、反向代理混线、session fixation 或 WS token 泄露劫持，后续消息没有 per-message 完整性、序列号、scope 或重放防线。
- 已知攻击模式：WebSocket 握手认证强、消息层弱，常见于“认证连接被复用为万能通道”的案例；攻击者不需要长期私钥，只需拿到一次连接或注入一条消息。
- 影响：可能绕过 canonical request 的 replay class、scope、rate limit 和 audit 粒度；如果同一 WS 通道承载多类 MCP 调用，风险从信息泄露扩大到越权操作。
- 修正要求：明确 WebSocket 只允许哪些消息类型。若包含任何 mutation、debug/admin 或高价值查询，必须引入 per-message envelope：`session_id + monotonically_increasing_seq + method + body_hash + timestamp + optional signature/MAC`，并按方法矩阵执行 scope、replay class、rate limit、visibility。只读 delta 订阅也应绑定固定 subscription id 与固定 filter，不允许连接内任意切换玩家/world/scope。

### H2: MCP/REST 授权矩阵不是完整规范，导致默认放行风险

- 位置：`design/auth.md` 授权矩阵仅列 5 个示例并写“完整矩阵见 interface.md”；`specs/security/03-mcp-security.md` 列出大量 MCP 工具；`specs/security/05-visibility.md` 列出多个输出面。
- 问题：`swarm_rollback`、`swarm_validate_module`、`swarm_get_docs`、`swarm_get_schema`、`swarm_get_world_rules`、`swarm_get_available_actions`、`swarm_simulate`、`swarm_profile`、账号恢复/删除/邮箱/passkey/federation 等大量方法没有统一的逐方法合同，至少缺少 replay class、required scope、rate limit、visibility filter、body size、audit redaction、是否允许 browser/agent transport。
- 影响：实现者容易把“无 scope”的文档/规则端点、“只读”的 simulate/dry-run 或恢复类端点当成低风险，从而产生 IDOR、越权调试、批量枚举、DoS 或跨 transport 混淆。
- 修正要求：把所有 REST/MCP/WS 方法纳入唯一机器可读授权矩阵，并规定“未列入矩阵的方法默认拒绝注册/启动”。矩阵至少包含：transport、auth scheme、scope、replay class、nonce/idempotency 机制、rate limit key、visibility filter、max body/max output、audit redaction、CSRF/Origin 要求、admin override 规则。

### H3: Sandbox OS 隔离规格互相矛盾，实际实现会削弱隔离

- 位置：`specs/core/04-wasm-sandbox.md` 架构、seccomp、cgroup、namespace checklist。
- 问题：文档前部写“无网络命名空间”，后部 checklist 要求独立 net namespace 且无网络接口；seccomp 示例允许 `clone (仅 CLONE_VM | CLONE_VFORK)`，后部 checklist 又写 `clone/fork/vfork` 禁止；cgroup 前部 `cpu.max = 250000 3000000`、`pids.max = 32`，后部 checklist `cpu.max = 50000 100000`、`pids.max = 16`；前部允许 `write`，OS checklist 又要求 `io.max ... wbps=0`。
- 影响：这些不是文字小错，而是安全边界合同冲突。实现者可能选择较宽松版本：无 net namespace、允许 clone、较高 pids/cpu、可写 IO，从而增加 sandbox escape 后的横向移动和 DoS 面。
- 修正要求：给出单一权威 sandbox profile。生产建议：独立 pid/net/mnt/ipc/uts namespace；net namespace 无接口或仅 UDS fd；默认禁止 `clone/fork/vfork/execve`，除非证明 Wasmtime 运行时必需且限定 flags；cgroup 数值统一；`write` 仅允许到预传入 UDS/pipe fd，不允许文件系统写；CI 以该 profile 做真实边界测试。

### H4: “无状态 admin challenge”无法证明一次性消费

- 位置：`design/auth.md` Auth 热路径性能合同：高价值操作使用 challenge-response，challenge 不存储，校验时重算 `Blake3(account_id || server_seed || timestamp)`；同文档又要求 admin_critical 使用 FDB 事务内消费 challenge。
- 问题：不存储 challenge 与“一次性”语义矛盾。仅由 account/server_seed/timestamp 派生的 challenge 在有效窗口内可重复计算，除非额外记录 used marker、version counter 或签名 payload 绑定不可重复 idempotency key。
- 影响：admin 恢复链接、CA 操作、批量吊销等高价值操作可能被窗口内重放；审计日志会记录多次合法签名，难以区分重放与真实重复请求。
- 修正要求：admin_critical 必须使用 FDB 事务内一次性 challenge 或 per-admin/per-target monotonic counter，并把 `method + canonical params hash + idempotency_key + challenge_id/counter + expires_at` 纳入签名。删除“challenge 不存储”或仅用于 read/idempotent 低风险操作。

## Medium

### M1: CSR 提交仅依赖 PoW，不设 IP/username 限速，仍有存储与验证 DoS 面

- 位置：`design/auth.md` 限速模型与 PoW 工作量证明。
- 问题：文档写 CSR 提交不设 IP/username 限速，PoW 本身就是速率控制。但服务端仍需要读取 FDB challenge、验证 PoW、解析 CSR、验签、检查用户名、事务消费 challenge。攻击者可预先离线求解大量 challenge，或分布式申请 challenge 后集中提交，造成 FDB 热点、事务冲突和签名验证负载。
- 影响：最小请求可触发较多服务端状态访问，尤其 `private` username_visibility 下 taken username 也消耗 challenge 并进入后续逻辑。
- 修正要求：CSR 提交增加轻量全局/per-IP/per-ASN 队列或令牌桶；challenge 记录按 IP/account hint 做配额；PoW 验证前先做廉价结构校验和请求大小限制；PoW 通过后再进入签名/事务；对失败 CSR 建立滑动窗口熔断。

### M2: PoW challenge 申请的存储 DoS 未完全闭合

- 位置：`design/auth.md` `swarm_register_challenge` 10/min per IP、FDB challenge 存储 TTL。
- 问题：challenge TTL 5 分钟、10/min/IP 在 IPv6 / botnet / 代理环境下可制造大量 FDB challenge 记录。文档没有规定全局上限、每前缀上限、过载降级或 challenge 是否可无状态化。
- 影响：未认证端点可被低成本打满 Auth subspace 或触发 TTL 清理压力。
- 修正要求：加入全局 outstanding challenge 上限、per-/64 IPv6 或 ASN 限制、过载时提升 difficulty 或返回 429；考虑 stateless signed challenge（HMAC(server_secret, challenge_id|difficulty|expires|client_hint)）加小型 replay/consume 记录，减少预提交存储。

### M3: 可见性策略允许 `player_view=full` 影响 MCP，只靠 competitive 配置拒绝，边界仍不清晰

- 位置：`specs/security/05-visibility.md` 旁观者/双模式可见性、Oracle 防线。
- 问题：前文写 `player_view=full` 时“玩家屏幕 / MCP”为全地图，后文再规定 competitive world 中 `fog_of_war=true && player_view=full` 拒绝。安全边界取决于 world 配置是否被正确分类为 competitive/non-competitive，且 `swarm_simulate`、docs/rules/actions 等接口是否跟随该配置未完全明确。
- 影响：一旦生产 World 被误配置为 non-competitive 或 full view，AI MCP 比 WASM snapshot 获得更多信息，破坏“AI 与人类/WASM 同等信息量”原则。
- 修正要求：把 MCP agent 可见性默认固定为 WASM snapshot 等价；任何超出 snapshot 的 MCP 全图读取必须要求独立 capability（如 `swarm:observe:full`）和非竞技 world flag，并在响应中显式 `visibility_mode=full_noncompetitive`。生产 competitive 世界启动时强制校验。

### M4: `swarm_get_docs` / `swarm_get_schema` 无认证且 5/tick，可能成为带宽与解析 DoS

- 位置：`specs/security/03-mcp-security.md` 开发辅助工具。
- 问题：无 scope 的 docs/schema 端点单次可达 1MB，按 tick 限制而非 IP/session/global 带宽限制；ETag 304 不计入限流，但未说明未命中、不同资源路径或压缩炸弹防护。
- 影响：未认证客户端可消耗网关带宽、JSON 序列化、缓存和日志资源。
- 修正要求：docs/schema 端点改为静态 CDN/对象存储或强 HTTP cache；加 per-IP/per-origin/global egress 限制、资源 id 白名单、响应压缩上限、max concurrent。无认证端点不应按 tick 计费，应按网络边界限流。

### M5: 审计日志 schema 存 `parameters String`，虽有 TickTrace 限制但 MCP audit 脱敏合同不足

- 位置：`specs/security/03-mcp-security.md` 审计日志；`specs/core/04-wasm-sandbox.md` TickTrace 字段限制。
- 问题：MCP audit 表直接存 `parameters String`，没有逐字段 redaction/hash/truncation 合同。Auth 文档同时强调 reset_token、refresh_token、私钥引用、email 等不能进日志，但 audit schema 未把这些要求落到执行层。
- 影响：恢复链接、token、邮箱、CSR、证书链、WASM metadata 或玩家原创字符串可能进入 ClickHouse 长期保留 90 天，形成二次泄露面。
- 修正要求：为每个 MCP 方法定义 audit schema：敏感字段只存 hash 或 redacted marker；大字段只存 digest/size；untrusted string escape + truncate；禁止记录 reset_token、refresh_token、private key material、raw certificate chain。

### M6: Wasmtime 版本 pin `=30.0` 但缺少“支持窗口失效即阻断发布”的硬门禁

- 位置：`specs/core/04-wasm-sandbox.md` Wasmtime 配置；`specs/security/CVE-SLA.md`。
- 问题：CVE-SLA 定义了响应流程，但没有明确当锁定版本退出官方安全支持窗口或 cargo audit 数据库缺失时，CI/发布是否失败。只写“季度人工审查”不足以覆盖短周期 WASM runtime 漏洞。
- 影响：供应链风险在无人维护窗口中累积；Wasmtime/wasmparser/Cranelift 的历史漏洞多与 sandbox escape、OOB、DoS、codegen bug 相关，不能只依赖人工季度检查。
- 修正要求：CI 增加 `cargo audit --deny warnings`、RustSec/OSV/GHSA 订阅、Wasmtime release support policy 检查；锁定版本超过支持窗口或存在未豁免 High+ advisory 时阻断发布。例外必须有到期时间和临时缓解。

## Informational

### I1: 应用层证书模型和用途隔离是明显亮点

`ClientAuthCertificate`、`CodeSigningCertificate`、`AdminCertificate` 的 usage/scope/audience 分离，以及部署时只接受 code signing 证书，能有效降低凭据串用和跨协议重放风险。

### I2: Source Gate 明确“gameplay 指令默认只来自 WASM”

MCP_Query/MCP_Deploy 不能直接产生游戏动作，所有 gameplay action 进入统一 command validation pipeline，是防 API 滥用和反作弊的关键设计。

### I3: 可见性统一函数和输出面闭合意识很好

`is_visible_to` 覆盖 snapshot、MCP、WS、REST、replay，并补充 `omitted_count` 分桶与特殊攻击拒绝码等价策略，能显著减少 oracle 类信息泄露。

### I4: WASM sandbox 多层限制方向正确

Wasmtime fuel、epoch interruption、Store reset、禁 WASI 文件/网络/时钟、host function 白名单、cgroup/seccomp/namespace、恶意 WASM 样本库和 CVE SLA 组合，符合可编程 MMO 的高风险执行模型。

### I5: Browser token 存储从 localStorage 转向 HttpOnly cookie + WebCrypto non-extractable key 是必要修正

考虑到玩家原创字符串、回放、调试输出和文档渲染都是长期 XSS 面，该修正能显著降低 bearer material 被直接读取的风险。

## CrossCheck — 需要跨方向检查

- CX1: Sandbox worker pool 与每 tick Store reset 的确定性/性能/隔离取舍需要 Architecture 检查 → 重点验证 long-lived worker 是否会保留 JIT/runtime 侧状态、host-side cache、FD、signal handler 或 per-player residual state。
- CX2: `swarm_simulate` 的 snapshot copy、fuel 预算和执行结果可见性需要 Architect + Gameplay 检查 → 重点确认 simulate 不会变成高精度战术 oracle，也不会破坏 tick 确定性。
- CX3: `player_view=full`、public spectator、replay privacy 的产品语义需要 UX + Gameplay 检查 → 重点确认教学/合作/竞技三类世界在 UI 上不会被误配置为泄露实时全图。
- CX4: Auth Service 独立进程与 Engine/Gateway 的 principal 传递需要 Architecture 检查 → 重点确认 principal snapshot 是不可伪造、不可由客户端覆盖，并在 gRPC/NATS 内部调用中有服务间认证。
- CX5: Wasmtime `=30.0`、rmcp、Bevy、FoundationDB、Dragonfly、ClickHouse 的依赖树和安全维护策略需要 Supply-chain/Infra 检查 → 重点确认版本 pin、advisory 订阅、SBOM、license、transitive dependency CVE gate。
- CX6: Admin 命令走标准 `validate_and_apply()` 管线但放宽所有权检查，需要 Architecture + Gameplay 检查 → 重点确认 Rust trait 约束真的防止任何世界状态修改绕过审计/验证路径。
- CX7: 文档/规则/schema 无认证读取的缓存与发布链路需要 Infra 检查 → 重点确认不会把未发布规则、内部路径、调试 schema 或大对象通过公开端点泄露/放大。
