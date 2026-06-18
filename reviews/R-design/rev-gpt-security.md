# R-design Clean-Slate Security Review — GPT-5.5

Reviewer: rev-gpt-security (GPT-5.5)
Scope: only the 7 design documents listed in the task:
- `design/README.md`
- `design/auth.md`
- `design/engine.md`
- `design/gameplay.md`
- `design/interface.md`
- `design/modes.md`
- `design/tech-choices.md`

## Verdict: REQUEST_MAJOR_CHANGES

当前设计有很多安全方向的正确取舍（用途隔离证书、CSR、本地私钥、确定性回放、WASM fuel、nonce/timestamp、管理员双签等），但仍存在至少一个可直接破坏应用层安全模型的 Critical 级问题，以及多处高风险设计空洞/自相矛盾。尤其是“允许 HTTP/不可信代理 + WebSocket 握手后免签名”的组合，会让中间人可在会话建立后篡改/注入消息；这与文档声称的“不安全传输可认证和完整性校验”不一致。

我建议在进入实现前修正以下安全合同，否则实现团队很容易各自按不同解释落地，产生认证绕过、重放、DoS、IDOR/越权、沙箱逃逸放大和供应链投毒风险。

---

## Critical

### C1. 不安全传输语义与 WebSocket “握手后免签名”冲突，导致 MITM 可篡改/注入后续会话消息

Severity: Critical

位置：`auth.md` §5.7、§10.5a；`README.md` 架构图；`interface.md` MCP/WS 入口

设计允许 HTTP、不可信反向代理或本地离线网络，并声明应用层证书能提供身份认证与请求完整性校验。但 WebSocket 认证设计只对升级握手做一次签名，随后“后续消息免签名（会话内信任）”。如果底层不是 TLS，MITM 虽然不能伪造握手签名，但可以在已建立的 TCP/WebSocket 流上修改、丢弃、重放或插入后续帧。这样会破坏：

- 客户端发往服务器的 MCP/控制消息完整性；
- 服务器发往人类/AI 客户端的世界快照、经济告警、调试信息完整性；
- AI agent 的观察输入可信性（攻击者可喂假世界状态诱导错误部署）；
- “HTTP 场景下攻击者无法篡改已签名 body”的安全边界，因为 WS 后续 body 根本未签名。

建议：

1. 明确分层：生产默认必须 HTTPS/WSS；HTTP 仅限显式 `insecure_transport=true` 的离线/开发模式。
2. 如果要支持不安全传输，则 WebSocket 必须建立应用层加密/完整性通道：例如握手后用双方临时密钥协商 session key，所有后续帧 AEAD 加密并携带单调 sequence number；或每个 client->server mutating frame 使用 canonical signature + nonce/version。
3. server->client 推送也需要完整性保护。至少对 tick delta、snapshot、MCP event 加 `tick_number + body_hash + server_signature`，客户端校验 server application certificate chain。
4. 文档必须删除“后续消息免签名”的绝对表述，改为“WSS 下可依赖 TLS 会话；HTTP/WS 下必须应用层帧保护”。

---

## High

### H1. Browser 凭据存储使用 localStorage，XSS 后等价账号接管

Severity: High

位置：`auth.md` §14.3

设计要求浏览器使用 `localStorage` 存储 `{refresh_token, certificate, client_public_key}`，并依赖严格 CSP/Trusted Types 防 XSS。对一个带 Monaco、PixiJS、SDK 下载、世界规则 i18n、可能展示玩家/模组内容的 Web 应用来说，XSS 面非常大。一旦有任意 XSS，localStorage 中 refresh token 和证书材料可被直接读出并 exfiltrate。文档说 JWT/refresh token 不是信任根，但 refresh token 可以兑换会话，实际仍是高价值 bearer secret。

建议：

- refresh token 放入 `HttpOnly; Secure; SameSite=Lax/Strict` cookie，配合 CSRF token 或 double-submit；不要把长期 bearer secret 放 localStorage。
- 私钥必须使用 WebCrypto non-extractable key / OS keychain / passkey-backed credential；不要让 JS 可导出长期私钥。
- 如果坚持非 cookie 方案，至少使用内存 access token + refresh token 由 service worker/secure enclave 管理，并把 XSS 视为账号接管风险写入威胁模型，而不是仅用 CSP 带过。
- 对 Monaco/用户生成内容/模组 README/世界规则描述做严格 sandbox 和 HTML sanitization 合同。

### H2. Dragonfly nonce 被定义为热路径“权威”，崩溃后允许 TTL 窗口内重放

Severity: High

位置：`auth.md` §10.8

Nonce 新鲜度使用 Dragonfly SETNX TTL，并写明崩溃语义是“TTL 窗口内可重放”。这对纯读查询也许可接受，但文档同时把 canonical request 用于敏感 MCP、admin、profile、revoke、recover、federation 等操作；不是所有 mutation 都像 deploy 一样使用 FDB `version_counter`。如果 Dragonfly 重启或主从切换丢失 nonce，攻击者可重放已捕获的仍在 timestamp 窗口内的签名请求。

建议：

- 所有 mutating 操作必须使用 FDB 持久化 idempotency key 或 per-certificate monotonic sequence/version counter。
- Dragonfly nonce 只能用于明确标注为“read-only and replay-safe”的查询。
- 高价值操作（admin、recovery、revoke、delete、deploy、federated login、certificate issuance）必须在 FDB 事务内消费一次性 challenge/idempotency key。
- 文档列出每个 MCP/REST/WS 方法的 replay class：`read_replay_safe` / `idempotent_mutation` / `non_idempotent_mutation` / `admin_critical`。

### H3. Host function 计算成本未纳入明确资源预算，最小 WASM 请求可放大为最大服务端开销

Severity: High

位置：`interface.md` §5.1；`engine.md` §3.4；`gameplay.md` §8.5

WASM host functions 包括 `host_path_find`、`host_get_objects_in_range`、`host_get_world_rules` 等，文档说它们“只读，不计入指令预算但计入 fuel 预算”。Wasmtime fuel 只天然覆盖 guest 指令，host function 内部执行的 Rust 路径搜索、序列化、可见性过滤、规则生成是否计 fuel 并不自动成立。如果玩家在一个 tick 内循环调用 `host_path_find` 或大范围对象查询，就可能用少量 guest 指令触发大量 host CPU/内存/缓存压力。

建议：

- 为每个 host function 定义独立预算：每 tick 调用次数、最大 range、最大输出 bytes、最大 pathfinding nodes、最大 total host CPU cost units。
- host function 成本必须扣减玩家同一 `fuel_budget` 或 `host_call_budget`，超限返回确定性错误。
- `path_find` 必须有固定上限、可见性边界、缓存 key、失败语义和最坏复杂度合同。
- 输出缓冲区写入前后校验 WASM memory 边界，且所有序列化有 hard cap。

### H4. WASM 沙箱隔离边界不完整，且生命周期设计自相矛盾

Severity: High

位置：`README.md` §1.2/架构图；`engine.md` §3.2/§3.4；`tech-choices.md` §2

文档同时出现“独立进程隔离”“WASM 实例使用预编译池，不每 tick fork/kill”和技术选型中“per-tick fork 生命周期——每 tick 新 fork，执行完 kill”。这不是实现细节差异，而是安全边界差异：进程池复用会带来残留状态、资源泄露、FD/capability 泄露和逃逸后横向影响；每 tick fork/kill 则有启动成本和不同的 DoS 模型。

当前缺失的硬安全合同包括：

- WASI 是否启用；默认 capabilities 是否为空；是否禁文件、网络、环境变量、时钟、随机；
- 每实例 memory/table/global 最大值、module size、compile time、instantiation time、linear memory growth 限制；
- seccomp/AppArmor/landlock/cgroup/rlimit 是否包裹 sandbox worker 进程；
- Wasmtime 版本 pinning、CVE 响应、升级后重编译与回放兼容策略；
- 预编译缓存投毒防护：cache key 是否包含 wasmtime version、compiler flags、world ABI、module hash；
- worker 复用时如何清空 store、memory、fuel、epoch、host state。

建议：先冻结 sandbox threat model 和 lifecycle。若使用 worker pool，应明确“一玩家一隔离进程/容器/uid + 每 tick 新 Store/Instance + no shared mutable host state”；若使用 per-tick process，则把性能预算重新对齐。

### H5. 管理员恢复链接流程仍给管理员返回 reset_url，存在支持人员接管账号路径

Severity: High

位置：`auth.md` §10.5b、§11.3

文档说管理员生成恢复链接“不允许管理员读取、指定或保存用户的新私钥或 recovery password”，但接口返回 `reset_url` 给管理员，并要求“返回值只展示一次”。即使有双人授权，两个管理员或一个被盗 admin 会话仍可直接拿链接完成恢复，提交自己的 CSR，接管用户账号。表格中又写“Admin recovery link 生成 = AdminCertificate 签名 + 目标用户邮箱验证”，但 §11.3 的流程没有把链接只发给目标用户的已验证邮箱/外部工单通道。

建议：

- 管理员操作只应创建 pending recovery record；恢复链接必须发送到用户已验证邮箱或通过 out-of-band 用户验证流程交付，不直接返回给管理员。
- 如果离线部署没有邮箱，要求双 admin + 用户提供的短码/签名 challenge 双向绑定；admin 只能看到 masked delivery handle。
- reset token 的 redemption 必须绑定 `new_csr`、目标 username、recovery reason、audience，并吊销/保留旧证书策略明确。

### H6. 代码签名技术选型中出现 Blake3 MAC，容易被实现为对称“签名”

Severity: High

位置：`tech-choices.md` §8、§9；`auth.md` §5.3/§5.4

`tech-choices.md` 的表格把“代码签名”列为 “Blake3 MAC / keyed hash”，后文又说证书链、CSR、请求签名和代码签名统一 Ed25519。MAC 是对称认证，不是代码签名；如果实现团队按表格把 module_hash 用服务器或共享密钥做 MAC，会破坏“用户私钥签署部署”的不可抵赖性和用途隔离模型。

建议：

- 删除“Blake3 MAC 用于代码签名”的表述。
- 明确：Blake3 只用于 hash/PRNG/KDF；代码签名必须是 `CodeSigningCertificate` 对应用户私钥的 Ed25519 签名。
- canonical deploy payload 应包含 `module_hash, metadata_hash, world_id, player_id, certificate_id, version_counter, sdk_manifest_hash, wasmtime_target`。

### H7. Auth/恢复的 Argon2id 热路径仍有分布式 DoS 放大风险

Severity: High

位置：`auth.md` §6.1、§10.7、§17.1

设计已经把 per-IP 限流放在 argon2id 前，这是正确方向；但恢复凭据校验全局 1000/min，单次 argon2id 约 19MiB 内存，分布式攻击可用大量随机 username 触发 dummy argon2id，绕过 per-account lockout。1000/min 的全局上限仍可能形成持续高内存带宽/CPU 压力，且会影响合法恢复/login。

建议：

- 增加全局 argon2 semaphore/worker pool，限制并发而不是只限制请求速率。
- 对不存在用户 dummy hash 使用预计算 dummy PHC + 固定成本验证，避免为每个随机 username 生成新 salt/hash。
- 对恢复/login 增加按 ASN / IP prefix / device fingerprint / proof-of-work adaptive gate。
- 明确超载时优先 fail closed：返回 `rate_limited`，不进入 argon2。

### H8. MCP/REST 工具缺少逐方法授权矩阵，容易产生 IDOR、越权和 mass assignment

Severity: High

位置：`interface.md` §4.1；`auth.md` §10.1；`gameplay.md` MCP 经济/调试接口

MCP 工具列表很完整，但没有逐方法声明：认证要求、证书 usage/scope、资源 owner 校验、visibility policy、rate limit、是否可跨 player_id/world_id、是否允许管理员覆盖。高风险接口包括：

- `swarm_inspect_entity` / `swarm_inspect_room` / `swarm_get_snapshot`：可能越权读取不可见实体；
- `swarm_get_replay`：可能泄露他人私有回放/战争情报；
- `swarm_list_modules` / rollback：可能枚举或回滚他人模块；
- `swarm_update_profile` / `swarm_delete_account`：mass assignment 或 target username/player_id 注入；
- `swarm_get_economy` / efficiency / trend：可能泄露对手经济数据。

建议：

- 生成 `authz_matrix.md` 或 IDL 注解，逐工具定义 `required_usage`, `required_scope`, `resource_owner`, `visibility_filter`, `rate_limit`, `replay_class`, `admin_override`。
- 所有 request schema 禁止客户端传 `player_id` 作为授权依据；player_id 必须从证书/session 派生。
- 对任何 `entity_id`, `room_id`, `module_id`, `replay_id`, `certificate_id` 做 owner/visibility check，防 IDOR。
- MCP `inputSchema` 应设置 `additionalProperties=false`，防 mass assignment。

### H9. 模组供应链默认信任过宽，`checksum` 可选且 Rhai 运行在引擎进程内

Severity: High

位置：`gameplay.md` §8.7；`tech-choices.md` §3

设计把 Rhai 模组视为服主信任代码，在引擎进程内运行。这可以作为自托管权衡，但供应链合同仍过弱：第三方模组从任意 git 仓库 clone，`mods.lock` 的 checksum 是可选，更新通过 `git pull + checkout tag`，仅对 tag force-push 告警。模组虽然无文件/网络 API，但它能通过白名单 actions 修改世界、扣资源、伤害实体，且引擎进程内解释器/宿主 API 的漏洞会扩大为服务端 compromise 或世界完整性破坏。

建议：

- `mods.lock` 必须包含 immutable commit hash 和 content hash；启动时 hash 不匹配拒绝加载，不只是告警。
- 支持 signed tags / Sigstore / minisign，并在生产默认要求签名。
- 内置 allowlist：生产世界只能加载 operator 明确批准的 source host/org/repo。
- 模组 capability manifest 必须声明需要的 actions；默认最小权限，不是所有白名单 action 全给。
- 对 Rhai 引擎版本、已禁用功能（文件、网络、eval、native fn）和 AST 预算写入可测试安全合同。

---

## Medium

### M1. `player_id` 使用 u64 hash，身份碰撞处理不足

Severity: Medium

位置：`auth.md` §2、§7、§15

`player_id = blake3(...) → low 64 bits` 对 10^6 本地用户碰撞概率可接受，但联邦、多世界、长期运行和恶意选择 username/remote_player_id 的场景下，64-bit 命名空间偏紧。文档说注册时检测唯一索引冲突并返回 `username_taken`，但 hash 碰撞并不等于 username 被占用；这可能造成定向拒绝注册，未来也会给跨世界资产/审计带来身份混淆压力。

建议：使用 128-bit `PlayerId` 或内部主键使用 128/256-bit，UI/API 可显示短 ID。若必须 u64，需定义碰撞时的 deterministic rehash/salt 方案，而不是映射为 username_taken。

### M2. HTTP/TOFU 首次 pinning 风险被接受但缺少强 UX/运维保护

Severity: Medium

位置：`auth.md` §5.7

设计承认首次 pinning 前 MITM 可攻击，这是 TOFU 的固有限制。但文档没有要求 out-of-band fingerprint、QR code、admin-distributed trust bundle、pin rotation UX、pin mismatch 急停策略。AI agent 自动注册尤其容易在首次连接时无脑接受攻击者 root。

建议：默认要求 HTTPS/WebPKI；HTTP TOFU 必须需要显式 `--trust-root-fingerprint` 或人工确认。AI onboarding 不应自动 trust unknown root。

### M3. 邮箱/reset token 使用 URL query，缺少 Referrer-Policy 和前端落地页约束

Severity: Medium

位置：`auth.md` §11.2、§11.3

Reset URL 形如 `/auth/reset?token=...`。文档说服务端访问日志脱敏，但未规定前端 reset 页面不得加载第三方资源、不得把 token 放入 referrer、history、analytics。浏览器默认行为和错误埋点很容易泄露 query token。

建议：reset landing page 设置 `Referrer-Policy: no-referrer`、`Cache-Control: no-store`，不加载第三方资源；首次 GET 后立即把 token 交换为短期 HttpOnly recovery transaction cookie，并 `history.replaceState` 清除 URL token。

### M4. Public spectate / replay privacy 与 AI 公平性需要更硬的防串流规则

Severity: Medium

位置：`gameplay.md` §8.2 可见性；`modes.md` Arena 旁观/回放

Arena 默认允许旁观并设置延迟，但 World/自定义世界可将 `public_spectate=true` 且 `spectate_delay=0`。如果玩家或 AI 同时参与并旁观，可能通过旁观 WebSocket 获得超出自己 drone 感知的情报。

建议：当 `fog_of_war=true` 且 PvP 开启时，public spectate 必须有最小延迟或只对非参与账号开放；同一账号/同一证书/player_id 不得旁观自己正在参与的隐藏信息视角。

### M5. FoundationDB 单 tick 事务和快照预算可能形成存储/提交 DoS，需要 admission control

Severity: Medium

位置：`engine.md` §3.4；`README.md` 数据模型

设计给出单 tick FDB transaction size 16MB、每日写入预算估算和 50,000 entity cap，但缺少当 delta/keyframe 超预算时的确定性拒绝策略。攻击者可通过合法建造/资源碎片/大量小实体逼近上限，让 tick 提交失败或回放数据膨胀。

建议：定义 admission control：实体创建、资源拆分、TickTrace 附加数据、replay debug logs 都必须有 per-player/per-room/global quota。超额时以确定性错误拒绝新 Spawn/Build/Drop，而不是 tick 末尾提交失败。

### M6. Admin/world config hot update 缺少 schema-level 安全下限

Severity: Medium

位置：`auth.md` §10.5b；`gameplay.md` world.toml；`engine.md` Tier gate

文档允许 admin 热更新 world config 并记录 diff，但许多配置如果调到极端值会破坏安全或经济：PoW difficulty=0、transfer time=0、public_spectate=0 delay、memory_size 过大、host pathfinding range 过大、mod capability 打开等。

建议：world config schema 区分 `operator_tunable` 和 `security_floor`。低于安全下限的变更需要离线 maintenance window + 多 admin + explicit risk flag，不能普通热更新。

---

## Low / Informational

### L1. 术语与时间单位不一致会诱发实现错误

Severity: Low

例子：Canonical Request timestamp 用 `unix_ms`，WebSocket handshake 用 `unix_seconds`；nonce 有 128-bit、96-bit 两种；证书 TTL 表中 ClientAuth 有 24h、15min–180days、30–180days 多个默认。建议统一单位和默认值，并在 IDL 中固定。

### L2. Challenge/CSR 文档中 CSR payload 含 challenge，但 submit 参数不含 challenge，需更清晰的校验合同

Severity: Low

设计说 submit 请求不包含 challenge/difficulty，服务端从 FDB 取权威值；但 CSR payload 示例包含 `challenge`。建议明确 CSR 中的 challenge 仅用于签名上下文绑定，服务端必须比对 CSR.challenge == stored.challenge，且不得信任 CSR.difficulty。

### L3. 错误码和响应体需要防枚举一致性测试

Severity: Low

文档已经考虑 username/email 枚举，但 `challenge_not_found=404`、`username_taken=409`、`account_deleted`、`identity_conflict` 等在不同流程中仍可能形成账号状态 oracle。建议为 public/private 模式分别列出哪些错误可外显，并加入时序/错误一致性测试。

---

## Strengths

- 应用层证书 + CSR + 用户私钥持有 + 用途隔离证书的总体方向正确，比传统 bearer-token-only 设计更适合 AI agent、自托管和离线环境。
- Server Root CA 离线、Intermediate CA 轮换、HSM/KMS 建议、证书吊销和 audit trail 都是必要且合理的安全控制。
- PoW challenge 使用服务端权威 difficulty，且 submit 不接受客户端 challenge/difficulty，避免了常见 PoW 降级漏洞。
- Canonical Request 有 domain separator、字段顺序、body_hash、timestamp、nonce、audience，基础防重放/防混淆设计较完整。
- Engine 将玩家 mutating 操作统一为 deferred command，由引擎校验后应用；禁止 mutating host function 是正确的沙箱边界。
- TickTrace、world_config、mods_lock、state_checksum 支持回放审计，对反作弊和事后取证很重要。
- 管理员操作引入 AdminCertificate、双签、冷却、审计，是正确方向；只需收紧恢复链接交付模型。
- 设计明确不把 OAuth/OIDC 作为信任根，第三方身份只作为 bootstrap proof，本地重签证书，联邦边界较清楚。

---

## Recommendations

1. 先修复 Critical：为 WS/HTTP 不安全传输定义端到端帧完整性/加密，或明确生产只支持 HTTPS/WSS。
2. 输出一份强制安全矩阵：每个 MCP/REST/WS 方法的 authn、authz、scope、visibility、rate limit、replay class、idempotency、audit requirement。
3. 冻结 sandbox threat model：Wasmtime/WASI capabilities、进程/worker 生命周期、resource quotas、host function metering、precompile cache trust boundary。
4. 把所有 mutating request 的重放防护从 Dragonfly nonce 升级为 FDB idempotency/version/challenge 消费；Dragonfly 只用于 replay-safe reads。
5. 改造浏览器凭据存储：不要 localStorage 长期 refresh token；优先 HttpOnly Secure cookie + CSRF 防护或 WebCrypto non-extractable key 方案。
6. 重新设计 admin recovery：管理员不得直接获得 reset_url；只创建 pending recovery，交付给用户验证过的通道。
7. 将模组供应链从“可选 checksum + git tag”提升为“强制 checksum + immutable rev + 可选/推荐签名 + capability manifest”。
8. 删除 Blake3 MAC 作为代码签名的表述，统一为 Ed25519 CodeSigningCertificate 签名。
9. 为 host functions、pathfinding、snapshot、replay、economy query 建立最坏情况复杂度和 quota 测试。
10. 将 security-floor 配置写入 world.toml schema，防止热更新把安全参数调到危险值。

---

## Issue Count

- Critical: 1
- High: 9
- Medium: 6
- Low/Informational: 3
- Total: 19
