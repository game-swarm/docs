# R7 Security Review — rev-gpt-security

## 总体 Verdict

`CONDITIONAL_APPROVE`

R7 的安全设计相比 R6 明显收敛：MCP 不再是 gameplay 通道、WASM-only gameplay、Source Gate、deploy nonce、visibility oracle 防线、Rhai 强制签名、TickTrace/回放审计、Wasmtime fuel + OS sandbox 这些核心边界已经形成可实现的安全骨架。当前未发现需要推翻方向的 Critical 问题；但仍有若干 High 级合同冲突会在实现时直接造成认证降级、sandbox 边界分叉或 RuleMod 权限膨胀，建议在进入外部可访问 Gateway / sandbox / mod ecosystem 实现前修正。

## Critical

无。

## High

### High — Gateway/MCP transport 认证合同存在降级冲突：mTLS/signed request 要求在 Gateway 汇总协议中丢失

位置：
- `specs/security/03-mcp-security.md:95-117` — AI Agent/CLI 端点要求 mTLS 或 Ed25519 signed request，并拒绝混入 browser-style Origin/CSRF header
- `specs/security/09-command-source.md:184-197` — 以 `X-Swarm-Transport` + JWT `aud` 匹配作为 transport 判定
- `specs/12-gateway-protocol.md:21-31`、`specs/12-gateway-protocol.md:110-121`、`specs/12-gateway-protocol.md:144-152` — Agent MCP 汇总为 `JWT (mcp audience) + X-Swarm-Transport: mcp`，未保留 mTLS / signed request 强制要求
- `specs/security/03-mcp-security.md:158-167` — JWT 示例缺少 `aud` 字段，和 `09-command-source` 的 audience 强制模型不闭合

问题描述：
安全规格在 MCP security 文档中把 Agent/CLI 端点定义为“JWT + mTLS 或 Ed25519 signed request”的强认证通道；但 Gateway 协议作为实现入口汇总时，只要求 JWT audience 与 transport header。实现者若以 Gateway 文档为准，很容易把 AI Agent/MCP 暴露成普通 Bearer token HTTP/SSE 端点，丢失客户端证书/请求签名这一层抗 token 泄露、抗跨客户端重放、抗非浏览器伪造的边界。

这类设计和历史上常见的“内部管理 API 经过反向代理后只剩 Bearer token”的事故模式相似：边缘网关文档弱化了后端安全文档的额外认证条件，最后生产配置采用了最宽松解释。尤其 MCP 是 JSON-RPC over HTTP/SSE，长连接、重连、工具调用和部署能力集中在同一入口，认证降级的影响面大于普通 REST read API。

修正建议：
1. 选定并写入唯一 canonical transport auth table，Gateway 与 MCP security 共用同一表。
2. Agent/MCP 生产端点明确为：`JWT aud=mcp:*` AND (`mTLS client cert` OR `Ed25519 request signature`)；缺任一层均拒绝。
3. 在 `specs/12-gateway-protocol.md` §2/§5/§8 中补充 mTLS/signed request 校验职责、失败码、审计字段。
4. 在 `specs/security/03-mcp-security.md` JWT 示例中加入 `aud`，并对齐 `09-command-source` 的 `mcp:{world_id}:{player_id}` / `ws:*` / `rest:*` 格式。
5. 增加 transport-confusion 测试：MCP token 不能连 WS，WS token 不能打 MCP，缺 `X-Swarm-Transport`、缺 mTLS/签名、带 Browser Origin 的 Agent 请求均拒绝。

### High — WASM sandbox OS 边界在同一规格内自相矛盾，可能导致 seccomp / namespace 配置采用宽松解释

位置：
- `specs/core/04-wasm-sandbox.md:19-27` — sandbox worker 标注“无网络命名空间”、`pids.max = 32`
- `specs/core/04-wasm-sandbox.md:230-248` — seccomp 示例允许 `clone (仅 CLONE_VM | CLONE_VFORK)`，同时禁止 fork/exec/socket/open/clock/getrandom
- `specs/core/04-wasm-sandbox.md:250-257` — cgroup 示例 `cpu.max = 250000 3000000`、`pids.max = 32`
- `specs/core/04-wasm-sandbox.md:390-410` — checklist 又要求独立 net/pid/mnt/ipc/uts namespace、socket 返回 `EAFNOSUPPORT`、fork 失败 `EPERM`
- `specs/core/04-wasm-sandbox.md:381-388` — checklist 中 cgroup 变为 `cpu.max = 50000 100000`、`pids.max = 16`

问题描述：
沙箱文档同时给出两套不兼容的 OS 隔离合同：前半部分允许受限 `clone` 且描述“无网络命名空间”；后半部分要求独立网络命名空间且完全禁止 `clone/fork/vfork`。cgroup CPU/PID 限制也有两组值。实现者可能选择较宽松版本来满足 Wasmtime 运行需求，却以为已满足 checklist；也可能选择 checklist 版本导致 Wasmtime 内部线程/信号处理失败，再临时放宽 seccomp。

对于 WASM sandbox，这不是普通文档不一致，而是安全边界分叉：seccomp 和 namespace 的实际组合决定恶意 WASM 是否可能通过运行时/JIT/host function bug 扩大影响。Wasmtime CVE 历史中，很多风险不是单点配置，而是 runtime bug 与 OS 边界缺口叠加；因此边界合同必须唯一、可测试、可审计。

修正建议：
1. 将 `specs/core/04-wasm-sandbox.md` 收敛为一张 canonical sandbox profile：允许 syscall、禁止 syscall、namespace、cgroup、验证命令只有一份。
2. 明确 `clone` 是否允许；若 Wasmtime 需要线程/辅助线程，写出精确 clone flags、seccomp argument filter 和为什么不会创建用户可控线程。
3. 统一 `pids.max`、`cpu.max`、内存和 I/O 限制，并把 §6 资源预算表与 §9 checklist 引用同一常量。
4. 把 CI 验证从“示例”升级为必须通过的 acceptance tests：socket/open/clock/getrandom/fork/exec、OOM、CPU throttle、PID namespace、net namespace 均有可运行断言。

### High — Rhai RuleMod 的权限边界跨文档冲突：世界规则、玩家私有资源与实体修改能力没有闭合

位置：
- `design/gameplay.md:1386-1404` — Rhai API 示例允许 `state.players()` 遍历玩家、`player.resources()`、`actions.deduct_resource(player_id, resource, amount)`、`actions.damage_entity(entity_id, amount, reason)`、`actions.set_entity_flag(entity_id, flag, value)`
- `specs/core/07-world-rules.md:353-359` — 声明 RuleMod 不能访问其他玩家私有数据、不能直接修改玩家私有数据、不能为特定玩家创建/销毁实体
- `specs/core/07-world-rules.md:361-371` — 能力表将 `actions.deduct/award` 限定为全局资源池，禁止玩家私有资源；`set_entity_flag` 仅限全局实体，禁止设置玩家 drone flag
- `specs/security/09-command-source.md:31`、`specs/security/09-command-source.md:47` — Source matrix 又列出 RuleMod 可 `damage_entity/set_entity_flag/deduct_resource/award_resource/emit_event/custom handler`
- `design/gameplay.md:1500-1559` — mod 示例从 git source 安装并在 engine 中注册 tick hook，最后 `actions.apply(world)`

问题描述：
Rhai 被定义为“服主信任”的 in-process 规则系统，这个方向可以接受；但当前文档没有唯一的能力边界。`design/gameplay` 的 API 是玩家级、实体级修改能力；`specs/core/07` 又把这些能力收缩为全局资源和全局实体；`09-command-source` 再次列出更宽的能力集合。实现者无法判断第三方签名模组是否可对特定玩家扣资源、伤害 drone、设置 combat flag，或只能影响世界级参数。

这会形成供应链与权限滥用风险：第三方 mod 只要被服主信任加载，就运行在核心进程内。如果能力边界按宽松解释实现，恶意/被接管 mod 可以成为玩家级作弊通道；如果按严格解释实现，示例 mod 与 API 文档又不可用。签名、trusted_keys、CRL 能确认“谁发布了模组”，但不能替代“模组被授予什么 capability”。

修正建议：
1. 先决定 RuleMod 的安全模型：世界级规则系统，还是可授权的玩家/实体级能力系统。不要两个模型并存。
2. 若默认只允许世界级能力：删除或改写 `design/gameplay.md` 中对 `player.resources()`、`deduct_resource(player_id, ...)`、任意 `damage_entity` 的示例；把玩家级效果改为经过 capability opt-in 的扩展。
3. 若允许玩家/实体级能力：在 `mod.toml` / `world.toml` 中加入 required_capabilities + explicit grant，按 capability 分别限制 target kind、rate、max damage/award/deduct、visibility、audit 字段和 rollback/disable 语义。
4. 将 `specs/security/09-command-source.md` RuleMod 行与 `specs/core/07-world-rules.md` 能力表对齐，避免 Source Gate 对 RuleMod 放宽到超出能力白名单。

### High — 超大 WASM 输出的处理语义冲突：截断 JSON 与整批拒绝二选一未闭合

位置：
- `specs/core/04-wasm-sandbox.md:181-194` — `tick()` 返回 CommandIntent JSON，`len <= 256KB`，超过则拒绝该玩家当 tick 所有输出
- `specs/core/01-tick-protocol.md:722-735` — 统一预算表将 `Output JSON 256 KB` 的超限行为写为“截断（保留前 256KB）”
- `specs/core/02-command-validation.md:637-640` — 批级校验又规定单条 ≤64KB、整批 ≤1MB

问题描述：
同一个安全边界有三套值/语义：WASM ABI 输出 256KB 且超限整批拒绝；tick 预算表 256KB 且截断；command validation 整批 1MB。最危险的是“截断 JSON”：如果实现者按预算表做 byte-level truncation，再尝试容错解析或保留前半部分合法 commands，会引入 parser differential、partial-command execution、日志/审计 hash 不一致和 DoS 放大空间。恶意 WASM 可以构造“前半段合法、后半段触发截断”的输出，试探不同实现的解析边界。

修正建议：
1. 采用单一规则：WASM `tick()` 返回 buffer 超过上限时，整批拒绝、0 指令、记录 `OutputTooLarge`，不得截断后解析。
2. 统一三个文档的上限：例如 ABI buffer ≤256KB，单条 command ≤64KB，反序列化后的 command count ≤500；若整批仍需要 1MB，则说明适用对象不是 WASM 输出，需明确区分来源。
3. TickTrace 仅可截断“审计预览字段”，不能截断并执行 gameplay input；保留原始输出 hash 用于取证。
4. 增加恶意样本：oversized valid-prefix JSON、deep nesting、large string、duplicate keys、unknown fields、UTF-8 boundary truncation。

## Medium

### Medium — WebSocket token 通过 query string 传递，缺少日志/Referer/重连泄露约束

位置：
- `specs/12-gateway-protocol.md:21-26` — Browser WebSocket 使用 `JWT (ws audience) + ?token=<jwt>`
- `specs/12-gateway-protocol.md:35-40` — 示例连接为 `wss://<host>/ws?token=<jwt>`
- `specs/security/09-command-source.md:186-190` — WebSocket transport 判定同样写为 `?token=<jwt>` query param

问题描述：
JWT 放在 URL query 中常被 reverse proxy access log、browser history、crash report、APM tracing、Referer-like telemetry 或 WebSocket reconnect diagnostics 捕获。虽然 `aud=ws` 降低跨 transport 重放风险，但泄露的 token 在有效期内仍可订阅玩家可见 delta、读取自身状态或造成连接资源消耗。该问题不一定阻塞 MVP，但生产协议应避免把 bearer credential 放入 URL。

修正建议：
1. 优先使用 `Authorization: Bearer`（非浏览器客户端）或 `Sec-WebSocket-Protocol` / HttpOnly SameSite cookie + CSRF-bound upgrade（浏览器）。
2. 如必须使用 query token，强制短 TTL、一次性 upgrade token、日志脱敏、禁止 token 出现在 metrics/traces、重连需刷新 token。
3. 在 Gateway security section 中写明 proxy/nginx access log 必须 redact `token` query。

### Medium — `/metrics` 与 `/healthz` 在 Gateway REST 表中标为无过滤/无认证，外部暴露边界不明确

位置：
- `specs/12-gateway-protocol.md:99-108` — `/healthz`、`/metrics` 列在 REST API 中，可见性过滤为“无”
- `specs/12-gateway-protocol.md:144-152` — 安全表未说明 metrics/admin/health endpoint 的绑定地址、认证或网络隔离
- `RUNBOOK.md:68-79` — 示例通过 localhost curl 访问 metrics/healthz，但这是运维示例，不是 Gateway 协议安全合同

问题描述：
如果实现者把 Gateway 作为唯一外部入口暴露在 8082，`/metrics` 可能泄露 tick number、连接数、部署队列、错误率、世界/玩家维度 label 等信息；`/healthz` 也可用于探测部署拓扑与故障状态。这既是情报泄露，也是低成本 scraping/DoS 入口。当前文档没有说明这些端点仅绑定 localhost/internal network，或需要 admin scope。

修正建议：
1. 明确生产环境 `/metrics` 仅监听 internal/admin listener，不在 public Gateway listener 暴露。
2. `/healthz` 对公网只返回最小状态，不含依赖细节；详细 health 需要 admin/auth 或内网。
3. 指定 Prometheus scrape 的网络边界、mTLS/IP allowlist、label cardinality 上限。

### Medium — CVE-SLA 仍主要覆盖 Wasmtime，协议栈与 in-process 脚本依赖未纳入同等响应合同

位置：
- `specs/security/CVE-SLA.md:1-10` — 适用范围集中在 Wasmtime/WASM 执行配置/沙箱隔离
- `specs/security/CVE-SLA.md:23-28` — 监控来源包含 RustSec/CVE，但目标仍是 Wasmtime 相关公告
- `design/README.md:123-126` — MCP Server 使用 `rmcp, HTTP/SSE`
- `design/tech-choices.md:3-57` — Bevy、Wasmtime、Rhai 是核心运行时选择

问题描述：
Wasmtime 是最大风险点，但不是唯一安全关键依赖。rmcp/HTTP/SSE 影响 JSON-RPC parsing、SSE reconnect、batch 禁用、request lifecycle；Rhai 是 in-process 脚本执行；Bevy ECS 影响 unsafe schedule/parallel access 假设；NATS/Dragonfly/FDB 客户端也可能影响 auth、反压和持久化一致性。只给 Wasmtime 明确 SLA 会让其他高危依赖缺 owner、缺禁用策略、缺回归测试。

修正建议：
1. 将文档扩展为 Runtime and Protocol Dependencies CVE SLA。
2. 至少列出 wasmtime/wasmtime-wasi/wasmparser/rhai/rmcp/axum或HTTP栈/bevy/nats/fdb client/dragonfly client。
3. 每类依赖定义影响面、临时禁用策略、升级验证测试和回滚策略。
4. 对 MCP/HTTP 栈加入 request smuggling、SSE reconnect、JSON-RPC batch rejection、oversized body、slowloris 回归测试。

### Medium — MCP `swarm_get_schema` / `swarm_get_docs` 无 scope 且无限流，与动态 SDK/世界规则文档存在资源放大风险

位置：
- `specs/security/03-mcp-security.md:236-245` — `swarm_get_schema` 和 `swarm_get_docs` Scope 为“无”，限流为“无限制”；`swarm_get_world_rules`/`swarm_get_available_actions` 则需要 `swarm:read` 且限流
- `specs/gameplay/08-api-idl.md:347-376` — SDK artifacts 由世界配置和 mods 动态生成，并暴露下载/缓存路径
- `specs/security/03-mcp-security.md:257-285` — 开发辅助工具总体有 `20/tick` 限制，但表内 schema/docs 又写无限制

问题描述：
公开 schema/docs 有利于 onboarding，但“无限制 + 动态世界/SDK/模组文档”容易成为低成本 DoS 与枚举入口。攻击者不需要登录即可反复请求不同 world/schema/doc 资源，触发生成、序列化、压缩、缓存 miss 或大响应传输。若 docs 中包含 world-specific mod manifest，也可能泄露未加入世界的配置细节。

修正建议：
1. 区分静态公共 docs 与 world-specific schema/SDK：静态 docs 可匿名缓存，world-specific manifest/schema 至少需要 `swarm:read` 或 world public flag。
2. 即使匿名，也设置 IP/global rate limit、ETag/immutable cache、最大响应大小和生成超时。
3. 文档中明确 `swarm_get_schema` 不触发即时动态生成；只能读取已生成、已缓存、大小受限的 artifact。

## Informational

### 亮点

- `specs/security/09-command-source.md:73-115` 的 DeployPayload 将 domain separator、module_hash、world_id、module_slot、server-issued deploy_nonce、expires_at、Ed25519 signature 串成一条可审计链，能有效防止跨世界/跨 slot/跨协议重放。
- `specs/security/05-visibility.md:360-410` 已补上 MCP query、`omitted_count` 分桶、simulate/dry-run/explain 脱敏和特殊攻击拒绝码等价策略，R6 的主要 visibility oracle 已有明确修正方向。
- `specs/core/02-command-validation.md:557-584` 的 `NotVisibleOrNotFound` 可见性优先原则是防 IDOR / enumeration oracle 的正确基础。
- `specs/gameplay/08-api-idl.md:26-29` 明确 CommandIntent 只包含 `sequence + action`，并默认 `additionalProperties: false`，有效降低 mass assignment / 字段注入风险。
- `specs/core/07-world-rules.md:373-391` 对 Rhai 模组签名、trusted_keys、CRL、epoch、禁止 unsigned 宽松模式的要求方向正确；只需进一步收紧 capability 边界。
