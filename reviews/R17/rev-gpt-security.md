# R17 Phase 1 Clean-Slate 安全评审 — GPT-5.5

Reviewer: rev-gpt-security
Perspective: Security / API abuse / sandbox / DoS / single-authority closure

## 1. Verdict

REQUEST_MAJOR_CHANGES

R17 相比 R15/R16 已经显著收敛：Auth 证书模型、PoW 服务端权威、Admin 双签、WASM sandbox、可见性过滤、CVE SLA 都补了大量安全合同。但是“权威单一事实源”仍未真正闭合：`game_api.idl.yaml`、`api-registry.md`、`design/auth.md`、`03-mcp-security.md`、`05-visibility.md`、`09-command-source.md` 之间存在多处安全语义冲突。最危险的是 WebSocket 会话内是否免签、deploy replay class/nonce 语义、以及多个 MCP read/deploy API 是否允许客户端自报 `player_id`。这些冲突足以让不同实现者各取一份文档，落出 IDOR、重放、会话注入或信息 oracle。

本轮不建议批准进入实现；需要先把机器事实源和各安全文档统一，并用 CI 校验“不允许安全关键字段在下游文档重定义”。

## 2. Critical

None.

未发现单点设计直接等价于“必然 sandbox escape / auth 全绕过”的 Critical；但 High 级冲突足以在实现阶段演化为 Critical。

## 3. High

### H1 — WebSocket 安全模型自相矛盾：`auth.md` 允许握手后免签，MCP/IDL 要求每消息 seq+MAC

证据：
- `design/auth.md` §10.5a WebSocket 证书握手：握手后“后续消息免签名（会话内信任）”。
- `specs/security/03-mcp-security.md` §2.5：已认证 Agent WS “每条消息必须携带递增序列号 + MAC/Ed25519 签名”。
- `specs/reference/api-registry.md` §3.4 与 `game_api.idl.yaml` `websocket_security.agent_ws`：Agent WS = per-message seq + MAC，seq 回退/MAC 不匹配断开。

风险：
如果实现者按 `auth.md` 的“会话内信任”实现，TLS 终止层、反向代理、WS hub、连接复用、内部队列或任何会话内注入 bug 都会变成命令/部署消息重放和重排面。R15/R16 已经围绕 WS 会话免签反复修复；R17 仍保留了相反表述，说明权威收敛未完成。

要求：
- 删除 `auth.md` 中“后续消息免签名（会话内信任）”。
- 明确：Agent WS 握手只绑定 identity；所有会话内写/敏感消息仍必须 seq + signature/MAC，且 `seq == last_seq + 1`。
- Browser spectator WS 才可无 per-message 签名，但必须只读、无认证写入、无私密数据。
- 将该字段纳入 IDL：`agent_ws.requires_per_message_signature: true`，由 CI 检查下游文档不得写出相反语义。

### H2 — Deploy replay class 在权威源内冲突：设计要求 `deploy_mutation/version_counter`，IDL/registry 标为 `idempotent_mutation`

证据：
- `design/auth.md` §5.6a：`swarm_deploy` 是 `deploy_mutation`，防重放由 FDB `version_counter` 保证。
- `design/auth.md` §10.8：Deploy 不使用 nonce，使用 FDB 持久化 `version_counter`。
- `specs/security/09-command-source.md` §7.3：Deploy 不使用服务端 nonce，per-player/per-slot 单调递增 `version_counter`。
- 但 `specs/reference/api-registry.md` §3.1：`swarm_deploy` replay_class = `idempotent_mutation`。
- `game_api.idl.yaml` `mcp_tools.tools.swarm_deploy.replay_class`: `idempotent_mutation`。

风险：
IDL 是机器事实源；如果代码生成/网关策略按 `idempotent_mutation` 走 Dragonfly nonce 或普通幂等策略，而部署链路实际依赖 FDB version counter，会出现重放、跨 slot 覆盖、重复部署语义不一致，甚至灾难恢复后 Dragonfly 丢失导致 replay window 内重放。

要求：
- `game_api.idl.yaml` 必须把 `swarm_deploy.replay_class` 改为 `deploy_mutation`。
- 增加结构化字段：`replay_guard: fdb_version_counter`、`version_scope: player_id + module_slot`、`client_nonce: forbidden`。
- `api-registry.md` 从 YAML 再生成，禁止手工保留旧值。

### H3 — 多个 MCP API 仍在 input schema 中接收 `player_id`，形成 IDOR / mass-assignment 风险

证据：
- `game_api.idl.yaml` 中大量 read tools 输入包含 `player_id`：`swarm_get_snapshot`、`swarm_get_resources`、`swarm_list_rooms`、`swarm_get_economy`、`swarm_get_economy_trend`、`swarm_list_deployments` 等。
- `swarm_deploy` input schema 也包含 `player_id`。
- `09-command-source.md` 和 `auth.md` 多处声明 player_id 应从证书提取、客户端不可自报，但 IDL 的 input schema 没表达“必须忽略/覆盖客户端字段”。

风险：
这是典型 IDOR/mass assignment 漏洞形态：API schema 允许客户端提交主体 ID，而授权模型靠文档提醒实现者“不要信”。一旦某个 handler 直接使用 params.player_id 做查询 key，即可读取他人资源、经济、部署、snapshot 或部署到错误主体。即使 visibility_filter 存在，owner 类查询也可能被错绑定。

要求：
- 对当前主体查询：从 input schema 删除 `player_id`，改为 `subject: authenticated_principal` 或 `player_id_source: certificate`。
- 对 admin 查询：另设 `target_player_id`，并要求 `required_scope: swarm:admin` / `swarm:debug:admin`。
- 对 deploy：`player_id` 必须只来自 CodeSigningCertificate；payload 内 player_id 仅用于签名绑定，服务端必须覆盖客户端自报字段。
- 在 IDL 中加入 machine-checkable 字段：`client_supplied_subject: forbidden`。

### H4 — 可见性 oracle 修复与机器事实源冲突：`omitted_count` 在安全文档要求分桶，但 IDL 仍是精确 `u32`

证据：
- `05-visibility.md` §10.2 明确指出精确 `omitted_count` 会形成 oracle，并修正为 `0 | few | some | many | extreme` 分桶。
- `game_api.idl.yaml` `swarm_get_snapshot.output_schema.omitted_count: u32`。
- `api-registry.md` 也声明 `omitted_count` 为数值字段。

风险：
机器事实源会驱动 SDK/codegen；如果按 IDL 实现，攻击者可以通过制造截断边界观察精确 omitted_count 变化，推断视野外或被过滤实体数量，尤其在战争迷雾、隐身/特殊攻击和旁观延迟场景中形成侧信道。

要求：
- IDL 改为 `omitted_count_bucket: enum[zero,few,some,many,extreme]`，不要沿用数值 `u32`。
- 同时对 `total_visible_count`、截断 metadata 做分桶或删除。
- CI 增加 schema-vs-security invariant：任何 visibility truncation 字段不得是精确隐藏实体计数。

### H5 — API Registry Markdown 与 YAML 版本/内容不一致，单一权威源仍未闭合

证据：
- `api-registry.md` 声称机器权威源是 `game_api.idl.yaml`，冲突时以 YAML 为准。
- `api-registry.md` 当前 API 版本是 `0.1.0`。
- `game_api.idl.yaml` `api_version: "0.2.0"`。
- deploy replay class、snapshot omitted_count 等关键字段也不一致。

风险：
版本不一致本身不是漏洞，但它证明“Markdown 由 YAML 生成/冲突时以 YAML 为准”没有被实际执行。安全关键注册表若无法证明同步，后续 authz、rate limit、visibility、replay class 都可能产生实现分叉。

要求：
- 重新从 YAML 生成 `api-registry.md`。
- CI 检查 `api-registry.md` 中版本号、工具数、replay_class、visibility_filter、rate_limit、subject_source 与 YAML 完全一致。
- 下游文档只能引用 registry anchors，不允许复制安全关键表格。

## 4. Medium

### M1 — `03-mcp-security.md` 仍保留未注册/旧 MCP 工具名，削弱“未注册 CI 拒绝”的合同

证据：
- `03-mcp-security.md` §4.1 列出 `swarm_rollback`、`swarm_list_modules`。
- §4.3 列出 `swarm_explain_last_tick`、`swarm_inspect_entity`、`swarm_inspect_room`、`swarm_profile`。
- §4.4 列出 `swarm_get_schema`、`swarm_get_docs`、`swarm_get_available_actions`。
- `game_api.idl.yaml` / `api-registry.md` 的 46 个 MCP tools 中并无这些名称，取而代之的是 `swarm_get_tick_trace`、`swarm_get_sandbox_profile`、`swarm_list_errors`、`swarm_simulate`、`swarm_dry_run` 等。

风险：
安全文档里出现未注册工具，会导致实现者绕过 registry 添加 ad-hoc endpoint；这些 endpoint 往往缺少 authz、visibility、rate limit、audit 字段，是历史上 MCP/REST 滥用的常见入口。

要求：
- 删除所有未注册工具名，或先在 IDL 中注册完整安全列。
- 加 CI：security docs 中出现 `swarm_*` 名称必须能在 `game_api.idl.yaml` 中解析。

### M2 — Special attack 拒绝码使用未注册变体，错误等价类无法由机器源约束

证据：
- `05-visibility.md` §10.4 使用 `NotEligible`、`Fatigued`、`OnCooldown`、`InsufficientEnergy`。
- `game_api.idl.yaml` RejectionReason 中没有 `NotEligible`、`Fatigued`、`OnCooldown`、`InsufficientEnergy`；现有规范要求使用 `InsufficientResource`、`CooldownActive`。

风险：
特殊攻击 oracle 防线依赖拒绝码等价类。如果等价类里的码不在机器注册表中，代码生成、测试和审计无法检查；实现者可能回退到更具体错误，从而泄露“目标存在但不可见 / 目标在冷却 / 目标类型不适用”。

要求：
- 在 IDL 中注册 `NotEligible`，或把 visibility 文档改为现有注册码。
- 为特殊攻击增加 machine-readable `oracle_equivalence_class`，由 CI 生成测试矩阵。

### M3 — Sandbox OS 边界表存在实现级矛盾：clone/pids/net namespace 前后不一致

证据：
- `04-wasm-sandbox.md` §4.1 seccomp 允许 `clone (仅 CLONE_VM | CLONE_VFORK)`，但 §9.1 统一表禁止 `fork/vfork/clone`。
- §4.2 `pids.max = 32`，§9.1 `pids.max = 16`。
- 架构图写“无网络命名空间”，§9.1 又要求独立 net namespace；两者语义相反（无 net namespace 通常意味着共享宿主网络 namespace）。

风险：
Sandbox 安全依赖精确 OS 策略。seccomp/cgroup/namespace 前后矛盾会导致部署侧选择较宽策略，或 CI 验证与运行时策略不一致。尤其 `clone` 与 net namespace 是 sandbox escape/DoS 关键边界。

要求：
- 单一 OS 加固表作为唯一权威；前文只引用。
- 明确 `clone3`、`clone`、`vfork`、`fork` 的最终策略；如果 Wasmtime 需要线程，改为受控线程模型并用 pids 上限兜底，不要同时写允许/禁止。
- “无网络”应表述为“独立 net namespace 且无外部接口/路由”，避免误解为共享宿主网络 namespace。

### M4 — Admin rate limit / 权限边界前后不一致

证据：
- `09-command-source.md` 来源矩阵中 Admin `rate_limit` 写“无限制”。
- `api-registry.md`/IDL 对 Admin tools 设置 `10/h`、`5/h`、`5/min` 等限制。
- `09-command-source.md` 又写 Admin 可触发战斗、可写世界、走 `validate_and_apply()` 放宽 ownership 检查；但 IDL 只注册了有限 admin 工具。

风险：
管理员接口虽然高权限，但仍是攻击者盗取 AdminCertificate 后的放大面。无限制 admin 写操作 + 可触发战斗的宽泛语义会扩大 blast radius，也会使审计/回滚难以建模。

要求：
- Admin 来源矩阵不得写“无限制”；改为“以 API Registry per-tool limit 为准”。
- Admin 不应有泛化 gameplay 操作能力，除非每个 admin action 都在 IDL 注册并具备双签/冷却/audit/idempotency_key。

### M5 — `swarm_get_info` 要求 `swarm:read` 但用于 onboarding，可能阻断未认证 bootstrap；若改公开则需防枚举/DoS

证据：
- IDL `swarm_get_info` category = Onboarding，但 required_scope = `swarm:read`。
- Auth bootstrap 需要未认证获取 server trust/challenge；`auth.md` 提供 `swarm_get_server_trust`，但该工具未出现在 IDL 的 46 tools 中。

风险：
这更偏一致性/可用性，但安全后果是实现者可能临时开放未注册 endpoint 来完成 bootstrap，绕过统一 rate limit/audit；或者错误地把更多 info endpoint 公开。

要求：
- 把 auth bootstrap tools 纳入 IDL，标注 unauthenticated、per-IP rate limit、response size。
- 明确 `swarm_get_info` 是 authenticated 还是 public；若 public，必须有独立 rate limit 与字段脱敏。

## 5. Low

### L1 — Wasmtime 版本锁定写作不够精确

`04-wasm-sandbox.md` 写 `wasmtime = "=30.0"`。建议统一成完整补丁版本（例如 `=30.0.0` 形式）并在 CVE-SLA 中要求 Cargo.lock 同步审计。此项不是直接漏洞，但精确版本更利于 CVE 响应和复现。

### L2 — `api-registry.md` 变更记录仍停留 R15，R17 审查难以追踪修复闭环

Registry 变更记录只有 R15 条目；R17 已出现 0.2.0 YAML，但 Markdown 未同步记录。建议把安全裁决、字段重命名、replay class 变化全部进入 machine-readable changelog。

## 6. 亮点

- Auth 设计的职责边界比前几轮清晰：Auth Service、Gateway、Engine 分工明确，Root CA 离线、Intermediate CA 强制 HSM/KMS/权限检查、证书用途隔离、AdminCertificate 短 TTL 都是正确方向。
- PoW 已修复“客户端回传 challenge/difficulty”的降级面：服务端从 FDB 读取权威 challenge 与 difficulty，一次性消费。
- Recovery password 的 argon2id DoS 保护有明确 worker pool/semaphore、per-IP 前置限流、dummy PHC，考虑到了小请求放大为 19MiB hash 的风险。
- 可见性文档明确提出所有输出面共用 `is_visible_to`，并识别了 `omitted_count` oracle；方向正确，只是 IDL 尚未同步。
- Command source model 明确“gameplay 默认只来自 WASM，MCP 不直接动作”，大幅降低 AI/MCP 越权操控游戏实体的攻击面。
- WASM sandbox 文档覆盖 fuel、epoch interruption、WASI 禁用、start section 拒绝、host function 白名单、cgroup/seccomp/namespace、恶意样本测试和 CVE SLA，安全覆盖面完整。
- CVE-SLA 不只覆盖 Wasmtime，也覆盖 `wasmparser`、`cranelift-codegen`、`rustls`、`ed25519-dalek`、`tokio`、`serde` 等关键 Rust crate，这是供应链风险治理的正确粒度。

## CrossCheck

1. 必须以 `game_api.idl.yaml` 为唯一机器事实源重新生成 `api-registry.md`，至少修复：`api_version`、`swarm_deploy.replay_class`、`swarm_get_snapshot.omitted_count`、所有 tool 名称。
2. 在 CI 中加入“文档引用校验”：任何 `swarm_*` 工具名、RejectionReason、Replay Class、Visibility Filter、Rate Limit、Subject Source 出现在安全/设计文档中时，必须能在 IDL 中解析且值一致。
3. 修复 WebSocket 安全合同：Agent WS 握手后仍必须每消息 seq + Ed25519/MAC；只有 Browser spectator read-only WS 可无签名。
4. 修复 IDOR 面：所有以当前玩家为主体的工具不得接受客户端 `player_id`；IDL 要表达 `subject_source=certificate_principal` 且 `client_supplied_subject=forbidden`。
5. 修复 deploy 防重放：IDL 明确 `deploy_mutation + fdb_version_counter + per-player/per-slot`，不要落入普通 `idempotent_mutation`。
6. 修复 visibility oracle：IDL 将 `omitted_count` 改为分桶 enum；添加测试覆盖截断边界不泄露隐藏实体数量。
7. 统一 sandbox OS 加固表：clone/pids/net namespace 只能保留一个最终策略，并让 CI 按同一表验证。
8. 把 auth bootstrap tools（如 `swarm_get_server_trust`、`swarm_register_challenge`、`swarm_submit_csr`）纳入机器 IDL 或明确它们属于独立 Auth API registry；否则“所有 API 合约单一权威来源”仍不成立。
