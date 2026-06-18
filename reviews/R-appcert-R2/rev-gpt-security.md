# R-appcert-R2 Security Review — GPT-5.5

Verdict: CONDITIONAL_APPROVE

本轮设计已明显补强应用层证书、用途隔离、命令来源注入、WASM 沙箱、可见性过滤与 CVE 响应流程。整体方向可进入后续共识，但仍有若干安全合同需要在设计阶段冻结，否则实现时容易在 transport/auth/session 边界产生绕过或 DoS 面。

## Critical

无。

## High

### H-1: WebSocket application-certificate 握手缺少 canonical request 签名字段，可能退化为仅 cert_id 认证

证据：`12-gateway-protocol.md` §3.1 写 WebSocket upgrade 可使用 `Sec-WebSocket-Protocol: swarm-cert.<cert_id>`；§9 表格又写 Browser WS 可用 `Sec-WebSocket-Protocol: swarm-cert.<cert_id>` 或 `Swarm-Certificate-Chain + X-Swarm-Transport: ws`。但 WebSocket upgrade 路径没有明确携带 `Swarm-Timestamp`、`Swarm-Nonce`、`Swarm-Signature`、canonical path/method/body_hash，也没有说明 cert_id 如何绑定一次性 challenge。

风险：如果实现者按 `swarm-cert.<cert_id>` 建连，攻击者只要获得 cert_id 或截获一次握手元数据，就可能尝试连接重放、会话固定或跨代理误绑定。证书链验证不能证明“当前连接由私钥持有人发起”；必须有私钥签名或 token 绑定。

建议：冻结唯一 WS 证书握手协议：
- WebSocket 证书路径必须携带 `Swarm-Certificate-Chain`, `Swarm-Cert-Id`, `Swarm-Timestamp`, `Swarm-Nonce`, `Swarm-Signature`, `X-Swarm-Transport: ws`。
- canonical payload 至少包含 `method: GET`, `path: /ws`, `host`, `origin`, `sec-websocket-key`, `timestamp`, `nonce`, `certificate_id`, `audience`。
- 禁止仅凭 `swarm-cert.<cert_id>` 建立认证连接；`Sec-WebSocket-Protocol` 只能承载短标识，不能替代签名材料。

### H-2: Admin 限流/保护合同不一致，存在高权限操作 DoS 与恢复链路放大风险

证据：`mcp-tools.md` Rate Limiter 表写 `Admin | 无限制`；`auth.md` §10.7/§10.8 对恢复凭据、challenge 等有前置限流，但 §10.8 又写 `Admin 恢复链接 | 需 AdminCertificate + signed request | 认证后无额外限制`；`03-mcp-security.md` 对 admin 工具没有给出每 admin、每 target、双签待确认队列的速率上限。

风险：AdminCertificate 一旦被盗、误签或被低权限代理滥用，攻击者可批量创建恢复请求、吊销证书、触发 CRL/epoch 刷新或打满审计存储。高权限不等于无限资源；管理接口通常是最有价值的 DoS 放大点。

建议：所有 admin 操作仍需独立限流与幂等键：
- per-admin、per-target-player、per-operation、global 四层 token bucket。
- 双人授权操作的 pending request 设上限、TTL、幂等键和撤销路径。
- `epoch bump`、CRL 全量刷新、批量吊销等高成本操作设冷却和 break-glass 审计。
- 将 `Admin | 无限制` 改为“无 gameplay 预算限制，但受 security/admin rate limit 约束”。

### H-3: Deploy replay 保护在跨分片文档中出现 nonce registry 与 version_counter 双模型冲突

证据：`09-command-source.md` §3.1/§7.3 明确 Deploy 不使用 nonce，靠 per-player/per-slot `version_counter` 防重放；`auth.md` §10.8 也写 `Deploy 不使用 nonce`；但 `T3-shard-protocol.md` §6 写 `Deploy nonce 去重：全局 nonce registry（单点 FDB key space）`。

风险：设计阶段出现两套 replay 防护模型会导致实现分叉：某些分片按 version_counter，某些网关/文档按 nonce registry。最危险情况是跨分片部署、slot 迁移或重平衡期间 current_version_counter 读取不一致，旧 DeployPayload 在新分片被接受；或实现者误以为 nonce registry 已覆盖 deploy 而放松 counter 原子更新。

建议：选择并冻结一个权威模型。若坚持 version_counter：
- 删除 T3 的 deploy nonce registry 描述。
- 明确 `current_version_counter` 的权威 FDB key、事务冲突规则、slot 迁移时的原子读写、跨 shard ownership lease。
- DeployPayload 增加 `slot_epoch` 或 `shard_epoch`，防止迁移窗口旧 payload 在新 owner 上重放。
若改回 nonce：则需定义 nonce 的持久性、跨分片写入事务和与 version_counter 的优先级。

### H-4: `player_view=full` 允许 MCP 只读查询全地图，可能破坏 AI 公平性与 fog-of-war 安全边界

证据：`05-visibility.md` §3.5 表格写 `player_view = "full"` 时，drone snapshot 仍按 `is_visible_to`，但“玩家屏幕 / MCP”为全地图；同文 §1 又强调所有输出面调用 `is_visible_to`，`03-mcp-security.md` §1 强调 MCP 与 Web UI 等量、不更多。

风险：即使 WASM tick 输入受限，AI agent 可通过 MCP 全图只读查询生成下一版 WASM 策略，等价于用 out-of-band 全图情报优化代码部署。对于编程竞技游戏，这会绕过 fog-of-war 的策略约束；“只读”并不等于“不可用于决策”。

建议：将 MCP query 默认绑定 `drone snapshot` 可见性，而不是人类摄像机视图。若世界模式允许 full spectator：
- 仅 Web spectator/replay 可全图，且延迟 ≥ policy。
- MCP full-map 需独立 scope（例如 `swarm:spectate_full`），不得与 player deploy certificate 共存，不能用于同一 player 的 deploy/session。
- 在设计中区分 “human rendering camera” 与 “agent decision input”。

## Medium

### M-1: Audience 字符串格式在文档中不一致，容易造成跨 transport 校验失败或被宽松匹配绕过

证据：`auth.md` canonical request 使用 `audience: "transport:server_id:world_id:player_id"`；`09-command-source.md` §7.0 使用 `mcp:{server_id}:{world_id}:{player_id}` / `ws:...` / `rest:...`；`03-mcp-security.md` 又写 `{server_id, world_id, "cli"}`；`12-gateway-protocol.md` 表格写 `transport:server_id:world_id:player_id`。

风险：实现者可能写“兼容多个格式”的宽松 parser，导致 `mcp`/`rest`/`ws` audience 误接受，或者证书签发与验签端使用不同格式引起可用性事故。Audience 是跨协议重放防线，必须字节级规范。

建议：定义唯一 ABNF/BNF，例如 `swarm-aud-v1:<transport>:<server_id>:<world_id>:<subject_id>`，transport 枚举为 `mcp|ws|rest|replay|admin`；证书字段、canonical request、DeployPayload、JWT aud 全部引用同一规范，并明确不得做别名/前缀匹配。

### M-2: 普通请求 nonce 使用 Dragonfly 热路径，崩溃语义描述与“重放被拒绝”矛盾

证据：`auth.md` §10.8 写 nonce 使用 Dragonfly SETNX TTL，`崩溃语义 | TTL 窗口内可重放；窗口过后 nonce 过期 → 重放被拒绝`。但若 nonce 记录丢失，窗口内重放反而可能被接受；窗口过后 timestamp 是否拒绝取决于 timestamp window，不是 nonce 过期本身。

风险：Dragonfly 故障/重启期间，攻击者可重放 60-300s 内截获的已签名敏感请求，尤其是非幂等 MCP/admin 操作。文档当前语义会让实现/运维误判 replay 风险。

建议：
- 明确 nonce store 失效策略：fail-closed 用于 mutating/admin/deploy-adjacent 请求；只读查询可 fail-open 或降级。
- 将“窗口过后 nonce 过期 → 重放被拒绝”改为“timestamp 窗口过期导致拒绝”。
- 对高价值操作使用 FDB 持久 nonce/challenge 或操作级幂等键。

### M-3: `swarm_get_schema` / `swarm_get_docs` 无限制，存在低成本枚举和文档放大 DoS

证据：`03-mcp-security.md` §4.4 写 `swarm_get_schema` scope 无、限流无限制；`swarm_get_docs` scope 无、限流无限制。`mcp-tools.md` 也列出学习类工具，但未给未认证/匿名限流与响应大小上限。

风险：schema/docs 通常响应体大、可被匿名反复请求，容易成为带宽/CPU/cache 放大点；如果 docs 动态生成或包含 world manifest，也可能泄露未公开规则或内部错误。

建议：匿名学习端点也应有 per-IP/global 限流、响应大小上限、ETag/cache、静态化策略；world-specific schema/docs 要么要求 `swarm:read`，要么只返回公开 manifest。

### M-4: Host function 预算在文档间不一致，可能导致沙箱 DoS 合同实现分叉

证据：`01-tick-protocol.md` §7.1 写 host calls 1000/tick、`host_path_find` 10/tick + 100,000 explored_nodes；`host-functions.md` 写 `host_get_objects_in_range` 5/tick、`host_path_find` 10/tick；`04-wasm-sandbox.md` §3.2 仅说只读且计入 fuel；`08-api-idl.md` 对 get_objects/path_find 限额局部声明但未覆盖 total explored nodes。

风险：寻路是典型“小请求大开销”DoS 面。如果 IDL 生成器没有权威预算字段，某些绑定可能只限制调用次数，不限制 explored nodes、range、out_len、返回截断成本。

建议：把 host function 预算移入 IDL 单一真相：每函数定义 `calls_per_tick`, `max_range`, `max_out_bytes`, `max_explored_nodes`, `fuel_multiplier`, `on_exceed`。所有文档引用 IDL 生成结果。

### M-5: CodeSigningCertificate 吊销后已部署模块处理策略过于开放

证据：`auth.md` §5.4 与 `09-command-source.md` §3.4 写证书吊销是安全事件，服务器可按 revocation reason 冻结、回滚或继续允许既有模块运行。

风险：如果吊销原因是 key compromise，而默认仍允许既有模块运行，攻击者已部署的恶意 WASM 可继续消耗资源或保持战略优势。设计未定义 revocation reason 到 action 的强制映射。

建议：冻结最小策略：`key_compromise`, `admin_revoked`, `fraud`, `malware`, `intermediate_compromise` 必须 pause/freeze affected modules；只有 `device_retired`、`cert_rotation` 可继续运行既有模块。策略应写入 TickTrace 与 replay 语义。

## Low

### L-1: Wasmtime CVE SLA 文档间时间不一致

证据：`04-wasm-sandbox.md` 写 Critical 72h / High 7d；`CVE-SLA.md` 写 Critical 24h / High 72h。

风险：不是直接漏洞，但安全响应期望不一致会影响值班和发布决策。

建议：以 `CVE-SLA.md` 为权威，其他文档引用，不复制数值。

### L-2: `player_id` 在 auth 文档中同时出现 u64 与部分结构 u32

证据：`auth.md` 使用 `player_id: u64` 和 hash 取低 64 bits；`08-api-idl.md` types 定义 `PlayerId: u32`；`02-command-validation.md` RawCommand 表写 `player_id u32`。

风险：ID 截断可造成兼容性/碰撞风险，尤其是联邦身份和跨世界映射。

建议：统一 `PlayerId` 为 u64，IDL、RawCommand、证书 subject、FDB key 全部一致。

## Informational / Highlights

- 应用层证书与 TLS trust store 明确隔离，降低“私有 CA 被安装成系统根”类事故风险。
- CSR、CodeSigningCertificate、ClientAuthCertificate、AdminCertificate 用途隔离清晰，且服务端不保存用户私钥作为默认路径。
- CommandIntent 只允许 `sequence + action`，`player_id/source/tick` 服务端注入，能有效缓解 mass assignment / source spoofing。
- 单一 command validation pipeline 覆盖 WASM、MCP、REST、admin CLI，方向正确。
- WASM 沙箱基线覆盖 fuel、epoch interruption、内存/栈、WASI 禁用、start section 拒绝、seccomp/cgroup，防御纵深较完整。
- 可见性策略提出统一 `is_visible_to` 与 player/admin trace 分离，是避免调试接口泄露的正确方向。
- Auth 热路径意识较强：argon2id 前置 per-IP 限流、dummy argon2id、防用户名枚举、challenge 申请限流均是必要设计。
- CVE-SLA 单独成文，并要求恶意 WASM 样本、资源预算和回放一致性验证，值得保留。
