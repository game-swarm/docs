# R27 Phase 1 Clean-Slate Security Review — rev-gpt-security

## Verdict

CONDITIONAL_APPROVE

R27 的安全设计整体比上一阶段更闭合：应用层证书、用途隔离、请求签名、可见性统一函数、WASM 沙箱 OS 边界、CVE SLA、replay-critical persistence contract 都已经具备可实现的安全骨架。当前不建议 REJECT，因为核心方向正确且大部分边界有明确合同；但仍存在若实现者按 API Registry 或某些旧式接口落地会造成权限扩大、重放防护失效或 DoS 放大的问题，因此需要在进入实现前修正 High/Medium 项。

## Critical

无 Critical。

## High

### H1 — Auth API Registry 暴露旧式证书签发/轮换接口，突破用途隔离证书模型

Severity: High

证据：
- `design/auth.md` 明确规定 Swarm CA 只用于应用层证书，证书必须按 `ClientAuthCertificate` / `CodeSigningCertificate` / `AdminCertificate` / `FederationCertificate` 用途隔离，且 `Server Root CA` 不在线，`Server Intermediate CA` 只签发受 CSR/恢复证明约束的证书。
- `specs/reference/api-registry.md` §3.3 Auth API 仍列出 `swarm_auth_cert_issue {subject, san_dns_names, san_ip_addresses, validity_days, key_type}`、`swarm_auth_cert_rotate`、`swarm_auth_cert_list` 等偏 TLS/PKI 管理接口，并标记为 active admin tools。

风险：
- 这是典型“旧控制面残留”漏洞模式：新设计把证书签发收敛到 CSR + usage + scope + audience，但 Registry 里仍有泛化 `cert_issue`，实现者若按 Registry 开发，会给 admin scope 一个可签任意 subject/SAN 的万能证书接口。
- 该接口与“Swarm CA 不得作为系统/浏览器 TLS trust anchor”目标冲突，也会让应用层证书与传输层证书语义混淆。
- 一旦 AdminCertificate 或 admin endpoint 被盗，攻击面从“执行受限管理操作”扩大为“签发任意证书材料”，影响范围高于普通 admin mutation。

建议：
- 从 active Auth API 中移除或重命名 `swarm_auth_cert_issue/rotate/list/revoke` 这组通用 PKI 接口；若保留，必须限定为 `swarm_issue_application_certificate`，输入必须是已验证 CSR / recovery proof / admin dual-auth proof，不允许 `san_dns_names` / `san_ip_addresses`。
- API Registry 中所有 cert 管理工具必须显式包含 `usage`、`scope`、`audience`、`certificate_profile`、`csr_hash`、`admin_dual_approval_id`，并禁止签发传输层 TLS 证书。
- CI 应检查 `auth_api.idl.yaml` 不再生成泛化 TLS-style certificate issuance schema。

### H2 — deploy 防重放合同在 Command Source、API Registry、Persistence 三处不一致

Severity: High

证据：
- `specs/security/09-command-source.md` §3.2/§7.3 要求客户端签名 `DeployPayload`，其中包含 `version_counter`，服务端验证 `version_counter > current_version_counter`。
- `design/auth.md` §5.6a/§10.8 又规定 deploy 防重放由 FDB `version_counter` 保证。
- `specs/reference/api-registry.md` §3.2 Deploy 中 `swarm_deploy` 输入只有 `{player_id, drone_id, wasm_bytes, metadata}`，输出才有 `fdb_version_counter`，没有 `DeployPayload`、签名、`metadata_hash`、`version_counter` 输入。
- `specs/core/05-persistence-contract.md` §2.3 描述 FDB manifest 提交 deploy intent，但 `UPLOAD_PREPARE` 可先编译/计算 hash 并入队 object upload，随后才 `MANIFEST_COMMIT`。

风险：
- 若实现者以 API Registry 为准，deploy 请求可能只依赖普通 request signature，而缺少独立的 code-signing payload 签名与 per-slot version 绑定，造成跨 slot、跨 metadata、跨请求体重放边界不清。
- 若实现者以 Command Source 为准，则客户端自带 `version_counter`；若以 Auth/Persistence 为准，则服务端事务内递增。两种模型混用会出现竞态：重复请求、并发部署或 object upload pending 时，可能生成多个不同状态的 manifest。
- 这是供应链/代码签名链路的关键安全面，直接影响“被盗旧请求能否重新部署旧 WASM”“metadata 是否可被替换”“同 module_hash 是否能跨 world/slot 重放”。

建议：
- 统一为一种模型：推荐“客户端签名 payload 包含 `expected_previous_counter` 或 `idempotency_key`，服务端 FDB 事务内 CAS 递增 `version_counter` 并把最终 counter 写入 manifest”。
- API Registry 的 `swarm_deploy` input 必须加入 `code_signing_certificate_id`、`deploy_payload`、`deploy_signature`、`module_hash`、`metadata_hash`、`module_slot`、`world_id`、`idempotency_key`。
- 明确 object upload 不得在认证、签名、hash、size、module validation 全部通过前发生；否则攻击者可用无效签名请求驱动编译/上传成本。

### H3 — 未认证 CSR/PoW 路径对“最小请求造成最大服务端开销”的控制仍不闭合

Severity: High

证据：
- `design/auth.md` §10.7 写明 CSR 提交不设 IP/username 限速，理由是 PoW 本身就是速率控制。
- 同文档 §9.3/§9.4 要求 CSR 提交读取 FDB challenge、验证 PoW、验证 CSR 签名、检查 username、创建用户并签发证书。
- `design/auth.md` §6.1 已认识到 Argon2id 需要 semaphore/worker pool，但 CSR/证书签发/Ed25519/CSR parse/CA signing 路径没有同等级的并发门控说明。

风险：
- PoW 是客户端成本，不是服务端并发上限。攻击者可预计算或租用算力批量提交有效 PoW，将服务端放大为 FDB 写事务、CSR parser、Ed25519 验签、certificate signing、audit 写入和可能的 email 发送。
- 默认 challenge 申请 10/min per IP 可以限制 challenge 生成，但不能限制分布式来源，也不能限制已获取 challenge 的提交洪峰。
- 如果 HSM/KMS 签名在注册路径同步执行，签名队列本身会成为 DoS 目标。

建议：
- 给 `swarm_submit_csr` 增加服务端硬限流：per-IP、per-/24 或 ASN、global queue、per-username canonical key、per-public-key fingerprint。
- 引入 CSR signing worker pool/semaphore，类似 Argon2：全局并发上限、排队超时、失败返回 `rate_limited`。
- PoW 只作为门槛，不应替代服务端 admission control；审计事件也应采样或限速，避免 ClickHouse/FDB audit 被放大。

### H4 — WebSocket 安全合同互相冲突，可能导致“握手后免签名”实现绕过 per-message MAC

Severity: High

证据：
- `design/auth.md` §10.5a 写 WebSocket 证书握手后“后续消息免签名（会话内信任）”。
- `specs/security/03-mcp-security.md` §2.5 和 `specs/reference/api-registry.md` §3.5 要求 Agent WS 每条消息携带递增 seq + MAC/Ed25519 签名，seq 回退或 MAC 不匹配断开。

风险：
- 这是典型“安全合同双轨”问题：实现者若采用 `auth.md` 的免签模型，会在长期 WS 连接中把认证退化为 bearer session，无法抵抗会话内消息注入、代理层混淆、重放或跨 stream 重排。
- 对 AI/CLI Agent endpoint，WS 往往经过反向代理、SDK、MCP bridge，多跳中任一组件可造成消息重放/复用；per-message MAC 是必要防线。

建议：
- 删除 `后续消息免签名（会话内信任）`，统一为 `Agent WS: handshake + per-message seq/signature`。
- Browser spectator WS 保持只读、无写操作；Browser authenticated WS 若未来允许写操作，也必须使用同等 seq/MAC 或改走 HTTP signed request。

## Medium

### M1 — WASM 沙箱 seccomp/namespace 表存在矛盾，容易让实现落空

Severity: Medium

证据：
- `specs/core/04-wasm-sandbox.md` §4.1 允许 `clone (仅 CLONE_VM | CLONE_VFORK)`，但 §9.1 统一 OS 加固表又写 `fork/vfork/clone` 全部禁止。
- §1 架构文字写“无网络命名空间”，§9.1 又要求独立 `net` namespace 且无网络接口。
- §4.2 pids.max = 32，§9.1 pids.max = 16。

风险：
- 这些不是纯文档小错。seccomp、namespace、pids cap 的落地通常由不同工程师/脚本实现；矛盾会导致“测试按一套、运行按另一套”。
- 对 Wasmtime 来说，线程/信号/内存映射需求较敏感，`clone` 策略若写错可能在生产中被临时放宽，扩大逃逸和 DoS 面。

建议：
- 以 §9.1 checklist 作为唯一权威，前文只引用，不重复声明。
- 明确 Wasmtime 实际需要的线程模型：若禁止 `clone`，必须验证 Wasmtime 配置不创建线程；若允许特定 clone flags，§9.1 不得写“全禁”。
- pids.max 统一一个值，并补充 CI 对 seccomp BPF、namespace、cgroup 的实际探测。

### M2 — `swarm_simulate` / `swarm_dry_run` 的限流与成本预算在文档间不一致

Severity: Medium

证据：
- `specs/core/04-wasm-sandbox.md` §6.1 定义 simulate: `max_ticks=100`、`max_cpu_ms=5000`、每玩家每小时 `max_fuel_per_hour=50,000,000`、并发 3。
- `specs/security/09-command-source.md` §2.2/§6 写 `Simulate` rate limit 5/tick，budget 0.5× MAX_FUEL；Arena 10/tick。
- `specs/reference/api-registry.md` §3.2 Debug 写 `swarm_simulate` 和 `swarm_dry_run` 为 50/tick。

风险：
- simulate/dry-run 是典型 DoS 面：小 JSON 请求可触发多 tick sandbox 执行、pathfinding、snapshot clone、trace 输出。
- 如果实现者按 API Registry 的 50/tick 放行，而未落实 hourly fuel/global concurrent，最小请求可以产生最大服务端开销。

建议：
- Registry 必须生成并展示成本型限制，而不是只给 rate limit：`max_ticks`、`max_cpu_ms`、`fuel/hour`、`concurrent`、`output_bytes`、`snapshot_entities`。
- 对 simulate/dry-run 采用 admission token：进入执行前扣减预算，失败也计费，避免超时请求免费。

### M3 — 可见性配置允许非竞争世界 full-map MCP，但安全边界依赖配置语义，需防止误配

Severity: Medium

证据：
- `specs/security/05-visibility.md` §10.1 拒绝 `fog_of_war=true && player_view=full` 的 competitive world 组合。
- 同文档 §9 允许教学/合作世界 `fog_of_war=false`、`player_view=full`，MCP read/query 可全地图。

风险：
- 这是合理的产品能力，但安全边界依赖“competitive/non-competitive”配置解释。如果世界从 tutorial/coop 切换到 public competitive 时未强制迁移检查，历史 full-map 行为可能遗留。
- MCP agent 比人类 UI 更适合自动化爬取，误配造成的信息泄露影响更大。

建议：
- world mode 变更时强制重新验证 visibility profile；从 non-competitive → competitive 必须拒绝 `fog_of_war=false` 或 `player_view=full`。
- TickTrace 记录 `visibility_profile_hash` 与 `world_mode`，便于审计某 tick 是否在安全配置下运行。

### M4 — CRL/撤销缓存 60s 可接受风险需要按操作分级，而不是全局说明

Severity: Medium

证据：
- `design/auth.md` §10.8 允许证书吊销状态 CRL 在 Engine LRU 中延迟 60s，竞争世界可配置为 5-10s。
- deploy 提交、admin 操作、普通 read query 的风险不同。

风险：
- 设备丢失或 key compromise 后，60s 内旧证书仍可 deploy 或执行 admin 操作的风险显著高于只读 query。
- 文档已对 admin critical 使用 FDB challenge/CAS，但没有明确要求“admin/deploy 强制 CRL fresh check”。

建议：
- 分级：read query 可接受短缓存；deploy/admin/recovery 必须进行强一致 CRL/FDB fresh check 或接受极短 TTL。
- `key_compromise` / `intermediate_ca_compromise` 事件应触发 push invalidation + epoch bump，而不是等待 LRU TTL。

## Low

### L1 — `player_id` 取 64-bit hash 碰撞概率虽低，但高价值身份建议保留全长 identity key

Severity: Low

证据：
- `design/auth.md` §7.1 使用 `blake3(...) → 取低 64 bits → u64`，并认为 10^6 用户碰撞概率可接受。

风险：
- 游戏内 u64 player_id 便于 ECS，但认证/审计/联邦映射不应只依赖截断 ID。

建议：
- 保留 `identity_key = blake3(namespace + subject)` 全长 256-bit 作为 Auth/FDB 唯一键，`player_id u64` 仅作为游戏内短 ID；所有证书、审计和联邦映射包含全长 fingerprint。

### L2 — debug_detail 分级默认值与输出面脱敏需保持一致

Severity: Low

证据：
- `api-registry.md` §2 将 `competitive` 设为默认，且无 debug_detail。
- `visibility.md` §10.3 要求 dry_run/simulate/explain_last_tick 脱敏。

风险：
- 若某个世界把 detail_level 切到 practice/training，可能和 oracle 防线冲突。

建议：
- competitive world 强制 `detail_level=competitive`；practice/training 仅允许 non-competitive world，且 TickTrace 记录 detail level。

## Informational

### I1 — 亮点：应用层证书与用途隔离设计完整度较高

`ClientAuthCertificate`、`CodeSigningCertificate`、`AdminCertificate`、`FederationCertificate` 的 usage/scope/audience 分离是正确方向。尤其是“不依赖 TLS client certificate”“Swarm CA 不进入系统 trust store”“JWT 不是独立信任根”这些约束，能避免常见 mTLS/应用 token 混用问题。

### I2 — 亮点：可见性统一函数与 oracle 防线写得较具体

`is_visible_to` 单函数、所有输出面统一过滤、`NotVisibleOrNotFound`、`omitted_count` 分桶、simulate/dry_run/explain 脱敏，这些都是对 IDOR 和信息 oracle 的有效防线。

### I3 — 亮点：WASM 沙箱多层资源预算覆盖了常见 Wasmtime 滥用模式

fuel、epoch interruption、Store reset、WASI 禁用、host function 白名单、path_find 节点预算、输出大小限制、恶意样本库、CVE SLA 都有明确条款。尤其是 start section 拒绝、host function 返回可见性过滤、compile-time budget，是高价值设计点。

### I4 — 亮点：Persistence replay-critical subset 把对象存储降级风险隔离出来

FDB 原子提交 replay-critical subset，对象存储只承载 rich/debug blob，能避免跨存储双写破坏 tick 正确性。`deploy_activation_decision` 纳入 replay-critical 字段也是必要修复。

## CrossCheck — 需要跨方向检查

- CX1: deploy 状态机在 `UPLOAD_PREPARE`、object upload、FDB manifest commit、activation tick 的顺序仍有 TOCTOU 风险 → 建议 Architect 检查最终权威状态机是否单一、是否所有重试/并发部署都有确定性序列。
- CX2: `swarm_simulate` / `swarm_dry_run` 的预算数字在 security/core/registry 间不一致 → 建议 Performance 检查最坏情况 CPU、snapshot clone、pathfinding 与输出成本，给出统一容量公式。
- CX3: API Registry 标注“由 IDL 自动生成，冲突以 IDL 为准”，但本轮只读文件中未包含 IDL YAML → 建议 API/DX 检查 auth_api/game_api IDL 是否仍保留旧 schema，确保生成源被修正而不是只改 Markdown。
- CX4: public_spectate、replay_privacy、Arena 赛后全知回放的产品语义依赖模式配置 → 建议 Designer 检查 UI/UX 是否能清晰提示玩家当前世界是否公开旁观/回放，避免隐私预期落差。
- CX5: Wasmtime/Bevy/rmcp 等依赖的具体版本锁定与 CVE 支持窗口只在 Wasmtime `=30.0` 上较明确 → 建议 Architect/DevOps 检查完整依赖树、RustSec gate、cargo-deny policy、rmcp/bevy transitive dependency 深度和 release pinning。
