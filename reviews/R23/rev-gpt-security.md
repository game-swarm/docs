# R23 安全评审 — GPT-5.5

## Verdict

CONDITIONAL_APPROVE

理由：R23 对既有高风险面已有较强覆盖：应用层证书、用途隔离、canonical request、Web/Agent transport 分离、WASM 沙箱 OS 边界、可见性统一函数、deploy replay class、CVE SLA 都体现了清晰的安全意识。但仍存在若干会在实现阶段变成真实漏洞的合同不闭合点，尤其是 auth API 双轨不一致、Admin 权限例外过宽、PoW/Argon2 DoS 成本模型、WebSocket 会话内信任边界、以及依赖版本/SLA 可执行性。建议在进入实现前补齐下列 High/Medium 项。

## Critical

无明确 Critical。未发现设计层面直接允许远程代码执行、沙箱逃逸、未授权任意世界写入或明文长期凭据泄露的必然路径。

## High

### H1 — Auth API 存在双轨模型，可能导致认证绕过或实现分叉

severity: High

证据与模式：
- `design/auth.md` 将权威模型定义为应用层证书链 + 用户私钥签名，JWT/refresh token 只是 Web session 兼容层。
- `api-registry.md` 同时保留 `swarm_auth_login` / `swarm_auth_refresh` 的 token 登录模型，以及 auth_api 中的 cert/device admin 工具；部分字段仍是 `{credential, challenge_response}` / `{token}`。
- `03-mcp-security.md` 又强调 Agent 主路径必须验证 `Swarm-Certificate-Chain` + canonical signature。

风险：实现者可能把 `swarm_auth_login` 的 bearer token 当作 MCP/Agent 主认证根，形成与设计相反的第二条认证路径。典型结果是 scope/audience/nonce/certificate usage 校验只在一条路径生效，另一条路径出现 IDOR、scope bypass 或 token replay。

建议：
- 在 API Registry 中明确标注 `swarm_auth_login` / `swarm_auth_refresh` 仅限 browser compatibility profile，不得授予 Agent/MCP 主路径权限。
- 所有非浏览器 MCP/REST/WS mutation 必须统一走 application certificate verifier。
- CI/IDL 校验应拒绝任何未声明 `transport_profile`、`auth_authority`、`replay_class` 的工具。

### H2 — Admin source 被描述为“无限制”，与最小权限/双签合同冲突

severity: High

证据与模式：
- `09-command-source.md` 来源矩阵中 Admin 的 `rate_limit` 为“无限制”，且 capability 表显示 Admin 可写世界、全局存储、部署代码、查询世界、触发战斗。
- 同文稍后又要求 Admin 走标准 `validate_and_apply()`、回滚双人审计；`auth.md` 对 Admin 恢复链接、CA 操作有双签和冷却要求。

风险：这是典型高权限后门设计气味。即便实现声称统一管线，文档中“Admin 可触发战斗/部署/写全局存储 + 无限制”会诱导实现者创建绕过玩家约束的超级接口。攻击面包括被盗 AdminCertificate 后批量破坏世界、绕过 replay/fairness、通过 admin debug 面形成隐私数据外泄。

建议：
- 将 Admin capability 改成按工具显式授权，禁止“Admin source 可触发战斗”的泛化描述。
- 所有 admin_critical mutation 必须有 rate limit、cooldown、idempotency_key、双签/审批策略和 TickTrace 记录。
- `Admin` 不应作为 gameplay command source；它只能调用管理操作，管理操作再产生受审计的系统事件。

### H3 — PoW 作为 CSR 唯一速控不足，存在低成本存储/事务 DoS 窗口

severity: High

证据与模式：
- `auth.md` 明确 CSR 提交不设 IP/username 限速，理由是 PoW 本身就是速率控制。
- register challenge 申请 10/min per IP，但 botnet / IPv6 / 代理池可横向扩展；默认 difficulty=24 对 Rust native 约 150ms。
- CSR 提交流程涉及 FDB challenge 读写、用户名检查、用户/公钥/证书记录、证书签发审计，服务端成本明显高于攻击者单次 PoW 成本。

风险：最小请求可制造较大服务端状态变更与签发审计成本，尤其在 `username_visibility=private` 下 taken username 也会消费 challenge 并进入事务路径。该模式类似“client puzzle 不等于服务端 admission control”的注册滥用问题。

建议：
- CSR 提交仍应有全局、per-IP、per-/24 或 ASN、per-username-prefix 的低阈值限流，PoW 只是加权因子。
- 证书签发队列应有 admission gate 与 backpressure；HSM/KMS signing 必须限并发。
- 注册失败路径与成功路径都应有存储写入预算和垃圾回收策略。

### H4 — WebSocket 已认证会话的消息安全合同前后不一致

severity: High

证据与模式：
- `auth.md` §10.5a 写 WebSocket 证书握手后“后续消息免签名（会话内信任）”。
- `03-mcp-security.md` 与 `api-registry.md` §3.5 要求 Agent WS 每条消息递增 seq + MAC/Ed25519 签名。

风险：如果实现采用“握手后免签名”，被同进程插件、代理、浏览器扩展、WS library bug 或连接复用缺陷注入消息时，服务端缺少逐消息完整性与顺序校验。对可编程 MMO 的 Agent WS，这会变成命令注入、重放、跨会话混淆。

建议：
- 统一为 Agent/Auth WS 每消息必须 `seq + body_hash + signature/MAC`，握手只绑定会话与初始公钥。
- Browser spectator WS 保持只读；任何可写 WS 都不能“握手后免签”。
- 删除或修正 `auth.md` 中“后续消息免签名”的表述。

### H5 — Wasmtime 版本锁定写法不精确，CVE SLA 缺少可执行触发门禁

severity: High

证据与模式：
- `04-wasm-sandbox.md` 写 `wasmtime = "=30.0"`，不是有效精确 semver patch 锁定；应为 `=30.0.0` 或具体补丁版本。
- `CVE-SLA.md` 定义响应流程，但没有要求 CI 在 critical/high advisory 时失败，也没有说明 RustSec ignored advisory 的审批/过期机制。

风险：供应链安全依赖“人工记得做”。Wasmtime/Cranelift/wasmparser 属于沙箱边界核心依赖，锁定到错误粒度或缺少 CI fail-closed，会导致已知 CVE 长期滞留。

建议：
- 使用完整 patch 精确版本并提交 lockfile。
- CI 对 RustSec/Wasmtime advisory 默认 fail closed；ignore 必须包含 CVE、影响评估、owner、到期时间。
- 对 wasmtime、cranelift-codegen、wasmparser 启用额外 release/advisory watcher。

## Medium

### M1 — 证书/Token TTL 在文档间冲突，容易产生过长凭据生命周期

severity: Medium

`auth.md`、`api-registry.md` 的 refresh token、certificate TTL 存在 7d/30d、24h/180d/365d 等不同表述。TTL 是安全边界，不应散落多源。建议以 IDL/registry 为唯一机器源，并将 profile-specific TTL 显式拆分为 default/max/absolute max。

### M2 — 不安全 HTTP + TOFU 可用，但恢复/邮箱/管理员 payload 加密细节不足

severity: Medium

`auth.md` 允许 HTTP 上应用层证书认证，并要求敏感 payload 加密给服务器应用层证书 public key，但未定义加密信封、算法、密钥轮换、AEAD associated data、失败语义。建议定义 `SWARM-ENCRYPTED-PAYLOAD-V1`，绑定 server_id/world_id/cert fingerprint/path/body_hash，避免 MITM 在首次 pinning 后做跨端点密文重放。

### M3 — `player_id = blake3(...)->u64` 碰撞处理描述不充分

severity: Medium

文档说 10^6 用户碰撞概率可接受并检测唯一索引，但联邦场景、多世界、恶意选择 username 时不应只返回 `username_taken`。建议明确 collision 与 username_taken 区分，内部审计 collision 事件；必要时采用 128-bit internal player id，wire 层再压缩映射。

### M4 — `debug_detail` / audit 字段虽有限长，但仍需结构化脱敏

severity: Medium

API Registry 允许 512 bytes `debug_detail`，TickTrace 存储参数/result。若直接写 human-readable detail，玩家原创字符串可能造成日志注入、prompt 注入、控制字符污染或隐私泄露。建议所有 detail 使用结构化 enum + sanitized fields，禁止拼接原始玩家字符串；ClickHouse audit 参数默认 hash + allowlist 字段。

### M5 — Sandbox seccomp 列表存在实现歧义

severity: Medium

`04-wasm-sandbox.md` 前段允许 `clone (仅 CLONE_VM | CLONE_VFORK)`，后续 OS 加固表又禁止 `fork/vfork/clone`，pids.max 也出现 32 与 16 两个值。seccomp/cgroup 是硬边界，文档不一致会导致策略漂移。建议统一为单一 profile，并为 Wasmtime/JIT 必需 syscall 给出按架构验证过的 allowlist。

## Informational

- 亮点：应用层证书不进入系统 trust store，避免 Swarm CA 被滥用为 WebPKI 根。
- 亮点：deploy 使用 FDB version counter 而非热 nonce，避免 Dragonfly 崩溃导致部署重放。
- 亮点：可见性统一 `is_visible_to`，并覆盖 snapshot/MCP/WS/REST/replay，是防 oracle 的正确方向。
- 亮点：WASM 采用 deferred command model，禁止 mutating host function，显著降低沙箱逃逸后的直接写世界风险。
- 亮点：Argon2id 参数、dummy hash、worker pool/semaphore 思路合理，但仍需全局 admission control。

## CrossCheck — 需要跨方向检查

- CX1: API Registry 与 `design/auth.md` / `03-mcp-security.md` 的 Auth 工具模型不一致，可能需要删除或重标 `swarm_auth_login` 等旧 token 工具 → 建议 Architect 检查 IDL 单事实源、transport profile、auth_authority 是否能机器校验。
- CX2: Deploy 状态机中 `module_hash = Blake3(compiled_module)` 与部署签名中 `module_hash = Blake3(WASM bytes)` 表述不一致，可能导致签名对象和激活对象不一致 → 建议 Architect 检查 deploy artifact identity 与 replay-critical manifest。
- CX3: Admin source 的能力模型与游戏公平性边界冲突 → 建议 Game/Architecture 检查 Admin 是否应从 gameplay command source 中移除，只保留审计化 system event。
- CX4: Visibility 中 `player_view=full` 对 non-competitive 可全图，且 MCP 只读查询可能超出 WASM snapshot → 建议 UX/Game 检查是否需要在 UI 上强标“非竞技世界”，避免玩家误入后认为公平竞技。
- CX5: Wasmtime worker pool 的 Store reset 能否真实清空跨 tick 状态、JIT cache、host-side per-instance state → 建议 Sandbox/Runtime 检查生命周期实现细节与恶意样本测试覆盖。
