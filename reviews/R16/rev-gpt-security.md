# R16 Phase 1 Clean-Slate 安全评审 — GPT-5.5

## Verdict

REQUEST_MAJOR_CHANGES

R16 的安全设计相较早期版本已经显著增强：应用层证书、用途隔离、canonical request、nonce/replay class、可见性统一函数、WASM fuel/cgroup/seccomp、TickTrace hash chain 等核心安全骨架基本成立。但当前白名单文档之间仍存在若干会导致实现者选错弱路径的合同冲突，尤其是 WebSocket 会话内签名语义、API Registry 的授权权威缺口、Admin/Source Gate 语义冲突、Sandbox OS 隔离规格冲突，以及供应链/CVE 响应范围只覆盖 Wasmtime、未覆盖 rmcp/Bevy/关键 Rust crate 的缺口。

这些问题不是实现难度问题，而是设计合同本身不闭合。建议进入下一轮前先修正文档权威源与安全不变量，否则后续实现很容易出现 IDOR、跨 transport replay、admin 滥用、沙箱逃逸面扩大或依赖漏洞响应盲区。

## Critical

无新增 Critical。

## High

### H1 — WebSocket 认证后消息安全语义互相冲突，可能退化为“握手后免签”会话

severity: High

证据：
- `design/auth.md` 的 WebSocket 证书握手写明连接建立后“后续消息免签名（会话内信任）”。
- `specs/security/03-mcp-security.md` 则要求已认证 Agent WS 每条消息必须携带递增 `seq` 与 Ed25519 `mac/signature`，服务端严格检查 `seq == last_seq + 1`，防止会话内重放、注入、重排。

风险：
- 这是典型“认证只发生在连接建立时”的已知漏洞模式。一旦实现者按 `auth.md` 的弱语义做，任何会话内消息混淆、代理层注入、客户端 bug、重连复用、帧重放或中间层错误路由都可能绕过逐请求完整性校验。
- 对 Swarm 来说，WS 不只是 UI 通道，还可能承载 MCP/agent 事件和部署/调试交互。握手后免签会破坏 canonical request 的跨接口安全模型。

建议：
- 统一权威合同：Authenticated Agent WS 必须采用 per-message `seq + body_hash + Ed25519 signature/MAC`。
- `design/auth.md` 删除“后续消息免签名（会话内信任）”，改为引用 `specs/security/03-mcp-security.md` 的 WS message contract。
- Browser spectator WS 明确只读、无认证消息、无写操作；Agent WS 与 browser spectator 走不同 path/transport/audience。

### H2 — API Registry 作为“单一权威源”但缺少完整 authz/replay/visibility 合同，存在 IDOR 与 mass-assignment 实现风险

severity: High

证据：
- `specs/reference/api-registry.md` 自称所有 API 合约的单一权威来源，但 MCP Tools 表只列 Input/Output/Rate Limit，缺少每个工具的 Required Scope、Replay Class、Visibility Filter、subject derivation、Admin Override、是否允许客户端传 `player_id`。
- 多个 API input schema 直接包含 `player_id`：如 `swarm_get_snapshot {player_id}`、`swarm_get_resources {player_id}`、`swarm_list_drones {player_id}`、`swarm_get_economy {player_id}`、`swarm_deploy {player_id, drone_id, wasm_bytes, metadata}`。
- `design/auth.md` 与 `specs/security/09-command-source.md` 又要求 player_id 从证书/Principal 提取，不可自报。

风险：
- 这是典型 IDOR / mass assignment 模式：API 表若被实现者当作权威 schema，客户端提交任意 `player_id` 即可能查询或部署到他人主体。
- 即使安全文档说“服务端覆盖自报 player_id”，Registry 未表达该规则，CI/代码生成/SDK 很难自动防止实现偏差。
- Capability Profile 粒度过粗，不能替代逐工具授权矩阵。例如 debug、replay、profile、admin audit 的数据分级差异很大。

建议：
- 在 API Registry 中为每个 MCP/REST/WS 方法增加机器可读列：`required_scope`、`replay_class`、`subject_source`、`visibility_filter`、`rate_limit_key`、`admin_override`、`idempotency_key_required`。
- 对所有玩家作用域参数改为 `subject = authenticated_principal.player_id`；若允许查询他人公开信息，必须显式标为 `target_player_id_public` 并列出可见字段。
- `swarm_deploy` 的 `player_id` 从 input schema 删除或标注 `ignored_if_present / forbidden_if_present`，部署主体只来自 CodeSigningCertificate。

### H3 — Admin/Source Gate 的权限、限流和双签语义不一致，可能形成高权限 DoS 或绕过路径

severity: High

证据：
- `specs/security/09-command-source.md` Source 矩阵中 `Admin` 的 `rate_limit` 写为“无限制”，能力表允许 Admin 写世界、读写全局存储、部署代码、查询世界、触发战斗。
- `design/auth.md` 的 Admin 高权限操作要求 AdminCertificate、部分双签、冷却、审计、idempotency_key。
- `api-registry.md` 管理类通用 rate limit 写为 10/h，具体 admin tools 又有 5/h、10/h、30/tick 等差异。

风险：
- 高权限操作如果按 `Command Source` 的“无限制 + 可触发战斗 + owner check 放宽”实现，会成为最小请求最大服务端开销的 DoS 面，也会扩大误操作/被盗 admin key 的爆炸半径。
- “Admin 走标准 validate_and_apply，只是所有权检查放宽”缺少逐操作 capability 白名单，容易把 debug/admin/read/write/rollback/deploy 混成一个超级能力。

建议：
- Admin 不应有“无限制”默认值。所有 admin tool 必须有 rate limit、cooldown、idempotency_key、audit schema，Critical 操作必须双签。
- `Admin` Source 不能泛化为“允许触发战斗”。应拆为 `AdminRead`、`AdminConfig`、`AdminRollback`、`AdminSecurityAction`，每类明确可写字段与双签要求。
- API Registry 成为 admin 限流和双签的唯一权威源，其它文档引用，不重复声明冲突数字。

### H4 — Sandbox OS 隔离规格存在互斥描述，弱实现可能保留网络/clone/过宽 PID 面

severity: High

证据：
- `specs/core/04-wasm-sandbox.md` 架构图写“无网络命名空间”，但后续 checklist 又要求独立 net namespace 且无网络接口。
- seccomp 初始白名单允许 `clone (仅 CLONE_VM | CLONE_VFORK)`，后续 checklist 又明确 `fork/vfork/clone` 全禁。
- cgroup `pids.max` 前文为 32，后文 checklist 为 16。

风险：
- WASM 沙箱边界是本设计最重要的安全根之一。网络 namespace、clone/fork、PID 数、seccomp 白名单的冲突会导致不同实现者选择不同隔离强度。
- Wasmtime/JIT + host process 是历史上 CVE 高价值目标；如果 OS 边界不精确，单个 runtime CVE 可能从 Wasm sandbox escape 升级为宿主机横向移动。

建议：
- 明确生产基线：独立 net namespace，无任何外部网络接口；只通过预传入 Unix domain socket 与引擎通信。
- 生产 seccomp 禁止 `clone/fork/vfork/execve`；如 Wasmtime 运行确需线程/clone，必须列出精确 flags、调用阶段和不可替代理由，并有 CI 边界测试。
- 统一 `pids.max`、`cpu.max`、`memory.max` 数值到 API Registry 或 sandbox spec 单一权威表。

### H5 — 供应链安全 SLA 只覆盖 Wasmtime，未覆盖 rmcp、Bevy、wasmparser、argon2、Ed25519/WebAuthn 等关键依赖

severity: High

证据：
- 白名单中只有 `specs/security/CVE-SLA.md` 专门定义 Wasmtime CVE 响应。
- 架构使用 `rmcp`、Bevy ECS、wasmparser、argon2、Ed25519/WebAuthn、Dragonfly/FDB/ClickHouse 等关键依赖，但未见同等依赖分层、CVE 分级、版本锁定和功能开关策略。
- `README.md` 明确 MCP Server 使用 rmcp，核心 ECS 使用 Bevy；二者一旦出现反序列化、DoS、panic、unsafe、调度确定性或依赖链漏洞，会直接影响认证入口或世界执行。

风险：
- 供应链漏洞响应不能只盯 Wasmtime。MCP/HTTP JSON-RPC、ECS 调度、序列化、WebAuthn、密码哈希、证书解析同样处在攻击面上。
- rmcp/Bevy 依赖树通常比单一 crate 更深，传递依赖 CVE、RUSTSEC advisory、panic-on-malformed-input、regex/serde 资源放大都可能成为入口 DoS。

建议：
- 将 `CVE-SLA.md` 扩展为 `Dependency Security SLA`，至少覆盖：Wasmtime/wasmparser、rmcp/MCP transport、Bevy、crypto/auth crates、serialization/compression、database clients。
- 定义 crate tier：Tier 0 sandbox/auth/crypto/MCP；Tier 1 engine/ECS/persistence；Tier 2 UI/SDK。不同 tier 有不同 SLA、pinning、audit gate。
- CI 必须运行 `cargo audit`、`cargo deny`、license/source allowlist、重复依赖检查，并将 advisory 归档到安全任务。

## Medium

### M1 — CSR 提交完全依赖 PoW、无额外 IP/全局限流，仍有 FDB/解析热路径 DoS 面

severity: Medium

设计写明 CSR 提交不设 IP/username 限速，PoW 本身就是速率控制。但攻击者可以大量提交随机 `challenge_id`、畸形 CSR、超大边界输入或重复无效签名，触发 FDB 读取、反序列化、错误路径和审计写入。PoW 只限制“有效 challenge 的求解成本”，不限制“无效请求打到服务端热路径”的成本。

建议：
- `swarm_submit_csr` 增加轻量 per-IP + global token bucket，且在读取 FDB/解析 CSR 前做 body size、JSON depth、base64 长度、字段格式预检。
- 对 `challenge_not_found` / malformed CSR 做更低成本错误路径，不写高成本审计明细，只聚合计数。

### M2 — `public_spectate` 允许 World 延迟全图旁观，需更严格绑定 replay privacy 与竞技世界配置

severity: Medium

可见性文档允许 `public_spectate=true` 时未登录客户端订阅全地图实体，依靠 `spectate_delay >= 50 tick` 与 `replay_privacy` 过滤降低泄露。对持久 MMO RTS，50 tick 是否足够取决于 tick rate、战斗节奏、市场/资源刷新周期。若延迟过短，旁观者流可被玩家外部进程利用，形成合法情报旁路。

建议：
- Competitive World 默认禁止 `public_spectate`，除非 world config 显式声明 `spectator_intel_risk_accepted=true`。
- `spectate_delay` 应按 wall-clock 最小时长配置，例如不少于 5–10 分钟，而不是固定 tick 数。
- `replay_privacy=private` 时 spectator 不应收到全图实体位置，只能收公开元数据。

### M3 — 对象存储完整性有 hash 校验，但缺少不可变性、访问控制和删除/回滚威胁模型

severity: Medium

持久化合同通过 FDB manifest 中的 `content_hash` 验证对象存储 blob 完整性，这是正确方向。但对象存储仍可能被误删、回滚到旧对象、权限误配置公开读取、生命周期策略过早清理或跨租户 key 碰撞影响。当前文档更关注双写原子性，缺少对象存储安全配置基线。

建议：
- 对 TickTrace/WASM/replay object 启用 bucket versioning 或 append-only/object lock（至少 hot/warm 窗口）。
- object key 包含 server_id/world_id/tick/content_hash，避免可预测覆盖。
- 明确对象存储 ACL：默认私有、服务账号最小权限、禁止 public read、删除需双人/延迟。

### M4 — JSON-RPC/MCP Schema 防资源放大要求还不够集中

severity: Medium

各文档分散出现 max body 5MB、simulate 输出 1MB、TickTrace 字段截断、JSON-RPC batch 禁用等要求，但 API Registry 没有把每个 endpoint 的 max request bytes、max response bytes、JSON depth、array length、string length 作为权威合同。

建议：
- API Registry 为每个工具增加 `max_request_bytes`、`max_response_bytes`、`max_json_depth`、`max_array_items`、`batch_allowed=false`。
- 对 `swarm_validate_module`、`swarm_dry_run`、`swarm_simulate` 单独标注 CPU/memory/concurrency budget 和排队策略。

### M5 — `omitted_count` 分桶修正与示例仍不一致，可能被实现者照旧暴露精确 oracle

severity: Medium

`specs/security/05-visibility.md` 前文 snapshot 示例仍展示 `omitted_count: 0` 为数值；后文 10.2 修正要求 `omitted_count` 改为分桶值。虽然 0 是特殊值，但示例未展示字段类型从 number 变为 enum/string union，容易导致 SDK/Schema 继续定义为 number。

建议：
- API Registry 中定义 `omitted_count_bucket: 0 | "few" | "some" | "many" | "extreme"`，不要继续使用容易误解的 `omitted_count: number`。
- `total_visible_count` 同样移入 registry 并定义分桶类型。

## Low

### L1 — `player_id` 使用 u64 hash 的碰撞处理描述不够强

severity: Low

文档承认 10^6 用户下 u64 碰撞概率约 2.7e-8，并通过唯一索引冲突返回错误。长期联邦、多世界、机器人批量注册后，u64 仍可能成为低概率但高影响身份碰撞点。

建议：
- 存储层和审计层保留完整 identity key / public key fingerprint，`player_id` 只作为游戏内短 ID。
- 碰撞时不要只返回 `username_taken`，应返回内部 `identity_hash_collision` 并告警，避免误判为普通用户名占用。

### L2 — Admin 审计表与 ClickHouse MCP audit 字段存在 PII/secret 脱敏风险

severity: Low

MCP audit 表记录 `parameters String`，若实现直接序列化参数，可能写入 email、reset reason、device_label、metadata、甚至错误传入的 token。文档多处强调日志脱敏，但审计 schema 没有字段级 redaction policy。

建议：
- 为每个 API 参数增加 `audit: omit | hash | redact | plaintext` 标注。
- 默认不记录 raw parameters，只记录 canonical hash + allowlisted summary。

## Informational

- 应用层证书用途隔离（ClientAuth / CodeSigning / Admin / Federation）方向正确，能有效降低凭据复用和跨协议重放风险。
- Canonical Request Signature 明确字段顺序、LF、body_hash、domain separator，比常见“签 JSON 字符串”方案安全得多。
- Replay Class 将 read/idempotent/non-idempotent/admin 分开，并要求非幂等与 admin 走 FDB 原子消费，是正确的重放防线。
- 可见性统一为 `is_visible_to(entity, player_id, tick)` 并要求所有输出面复用，是防 oracle 的关键不变量。
- WASM sandbox 明确禁用 WASI 文件/网络/时钟/随机数，使用 fuel、epoch interruption、cgroup、seccomp、host function 白名单，整体方向正确。
- Persistence Contract 采用对象存储先写、FDB manifest/hash chain 后提交的模式，避免“FDB 写大 blob”和跨存储双写原子性幻觉。

## CrossCheck — 需要跨方向检查

1. Architecture / API：请确认 API Registry 是否应成为唯一 authz/replay/visibility 权威源；若是，需要把 auth.md、MCP security、visibility、command-source 的逐工具安全矩阵合并进去并由 CI 校验。
2. Architecture / Runtime：请统一 WebSocket transport 模型：Agent WS、Browser WS、SSE、Spectator WS 是否共用连接层？Authenticated Agent WS 必须逐消息签名还是只在特定 mutating message 签名？安全侧建议全部 Agent 消息签名。
3. Runtime / Sandbox：请确认 Wasmtime 生产运行是否需要 `clone` 或线程。如果需要，seccomp 不能简单写“clone 全禁”；如果不需要，应删除早期白名单中的 `clone (CLONE_VM | CLONE_VFORK)`。
4. Infra / Security：请把 Wasmtime CVE-SLA 扩展到 rmcp、Bevy、wasmparser、crypto/auth、serde/compression、database clients，并定义 Tier 0/Tier 1 依赖响应时限。
5. Gameplay / Security：请确认 `public_spectate` 在 World 模式下是否允许用于竞争世界。若允许，需要以 wall-clock 延迟和 replay_privacy 作为强制约束，而不是仅 `>=50 tick`。
6. Persistence / Security：请补对象存储不可变性、ACL、versioning、删除保护、跨租户 key namespace 和 hash-chain 恢复 runbook。

## 总结

当前 R16 可以作为安全架构的良好基础，但还不能批准进入实现冻结。需要先解决“单一权威源”和“冲突合同”问题，尤其是 WebSocket 消息签名、API Registry 授权矩阵、Admin 限权、Sandbox OS 边界、供应链 SLA 五项。修正后再做一轮 focused security pass，重点检查是否所有高风险接口都能由机器可读合同驱动实现与测试。
