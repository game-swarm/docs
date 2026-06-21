# R33 Security Review — DeepSeek V4 Pro

## Verdict

**REQUEST_MAJOR_CHANGES**

发现 2 个 Critical 问题（跨文档 audience 格式不一致可导致跨 transport 重放、Tutorial 来源双重定义导致 Source Gate 语义歧义）、3 个 High 问题（CRL fallback 枚举不一致、refresh token grace 窗口缺乏 per-IP 绑定、JWT Bearer token 未显式拒绝于 Agent 端点），需修复后再审。

---

## Critical（必须修复，否则 BLOCK）

### B1 — Audience 格式三文档不一致，可导致跨 transport 认证重放

**涉及文件**：
- `/data/swarm/docs/design/auth.md` §10.8（行 937–946）
- `/data/swarm/docs/specs/security/03-mcp-security.md` §2.2（行 108）
- `/data/swarm/docs/specs/security/09-command-source.md` §7.0（行 191–195）

**问题描述**：

同一个 transport（AI Agent / CLI 的 MCP 连接）在三份文档中使用了**互相冲突**的 audience transport 标签：

| 文档 | 行号 | Audience transport 值 |
|------|------|----------------------|
| `auth.md` §10.8 | 941 | 枚举包含 `agent-mcp` 和 `cli-rest` 两个独立值 |
| `03-mcp-security.md` §2.2 | 108 | `swarm-aud-v1:cli-rest:<server_id>:<world_id>:<player_id>` |
| `09-command-source.md` §7.0 | 191 | `swarm-aud-v1:agent-mcp:{server_id}:{world_id}:{player_id}` |

`03-mcp-security.md` 将 AI Agent/CLI 的 audience 标为 `cli-rest`，但 `09-command-source.md` 标为 `agent-mcp`。若 Gateway 按 `09-command-source.md` 的 `agent-mcp` 校验，则按 `03-mcp-security.md` 格式签发的请求会被拒绝；反之亦然。

**影响**：audience 是防止跨 transport 重放的核心机制（阻止 MCP agent 证书被重放到 WebSocket 连接）。格式不一致 → 实现时必须选择其一 → 另一文档的指引失效 → 可能存在未被校验的 transport 路径。

**修复建议**：
1. 统一 agent MCP 的 transport 值为 `agent-mcp`（`cli-rest` 保留给非 MCP 的 CLI REST 调用，如 `swarm_sdk_fetch`）
2. 更新 `03-mcp-security.md` §2.2 的 audience 字符串为 `swarm-aud-v1:agent-mcp:...`
3. 在 `auth.md` §10.8 中增加注释明确 `agent-mcp` 和 `cli-rest` 的使用边界：`agent-mcp` = MCP JSON-RPC agent 端点，`cli-rest` = 非 MCP REST 端点（SDK fetch、server trust 查询等）

### B2 — Tutorial 来源在 09-command-source.md 中双重定义

**文件**：`/data/swarm/docs/specs/security/09-command-source.md`

**问题描述**：

`Tutorial` 来源在**两个表格**中分别定义，字段不完全一致：

- §2.1（行 17, 23）：`auth_context: tutorial_session + world_id`, `gameplay: ⚠️ 仅教程世界`, `rate_limit: 10/tick`, `visibility: 教程房间`, `budget: (空)`
- §2.2（行 34）：`auth_context: tutorial_session + world_id`, `gameplay: ⚠️ 仅教程世界`, `rate_limit: 10/tick`, `visibility: 教程房间`, `budget: tutorial budget`

差异在于 §2.2 多了 `budget: tutorial budget`，而 §2.1 该字段为空。此外，§2.2 标题为「扩展来源」但 Tutorial 已在 §2.1「来源矩阵」中列出——双重归类造成歧义。

**影响**：Source Gate 实现时需决定 Tutorial 是否有独立 budget、是否属于「扩展来源」（§2.3 能力约束表中对「扩展来源」有额外限制）。二义性可能导致实现偏差。

**修复建议**：
1. 仅保留 §2.1 中的 Tutorial 定义
2. 从 §2.2 中移除 Tutorial 行
3. 在 §2.1 的 Tutorial 行中补充 `budget: tutorial budget`（若确实需要独立 budget）

---

## High（强烈建议修复）

### H1 — CRL Fallback 枚举值在 auth.md 两处不一致

**文件**：`/data/swarm/docs/design/auth.md`

**问题描述**：

- §15.2a（行 1391–1398）定义 `revocation_fallback` 枚举：`reject_for_code`, `reject_for_code_and_login`, `reject_all`, `allow_with_warning`
- §15.6（行 1452–1454）定义撤销传播 fallback 枚举：`reject_for_code`（default）, `accept_login`, `reject_all`

差异：
1. §15.2a 有 `reject_for_code_and_login`（拒绝 code + login），§15.6 无此值
2. §15.6 有 `accept_login`（允许 login），§15.2a 无此值
3. §15.2a 有 `allow_with_warning`，§15.6 无此值

**影响**：联邦 CRL fallback 是安全关键路径——远程世界 CRL 不可达时决定是否接受远程凭证。枚举不一致意味着实现时需二选一，另一组安全语义丢失。

**修复建议**：统一为 4 值枚举 `reject_for_code | reject_for_code_and_login | reject_all | allow_with_warning`，§15.6 的 `accept_login` 映射到 `allow_with_warning`（语义相近——允许但告警）。

### H2 — Refresh token rotation grace window 缺乏 per-IP/UA 强制绑定

**文件**：`/data/swarm/docs/design/auth.md` §14.1（行 1279–1285）

**问题描述**：

Refresh token rotation 后的 grace period（60s 非受信设备 / 10s 受信设备）设计为防止竞态条件，但当前描述仅说「异常 IP/UA 使用 grace 时触发 session family revoke」。这意味着：

- 正常 IP/UA 在 grace 窗口内使用已 rotated token → 不被拒绝
- 攻击者从同一 IP（如共享 NAT 后）在 grace 窗口内重放 intercepted refresh token → 无法区分

grace period 本身不绑定 per-IP 或 per-UA 状态，仅依赖「异常检测」触发吊销——但异常检测逻辑未定义。

**影响**：refresh token 拦截 + 同 IP 快速重放（60s 窗口内）可绕过 rotation 保护。

**修复建议**：在 auth.md §14.1 中明确 grace period 绑定规则：
- Grace 使用必须匹配原始 refresh 请求的 IP hash + UA hash
- 不匹配 → 拒绝 + 触发 family revoke（不等异常检测）
- 缩小非受信设备 grace 至 15s（当前 60s 对无证书设备过长）

### H3 — Gateway 未显式拒绝 JWT Bearer token 于 Agent 端点

**文件**：
- `/data/swarm/docs/specs/security/03-mcp-security.md` §2.2（行 93–118）
- `/data/swarm/docs/design/auth.md` §14.5（行 1320–1325）

**问题描述**：

`03-mcp-security.md` §2.2 明确 Agent 端点接受 `Swarm-Certificate-Chain` + canonical request signature，但**未显式声明拒绝 JWT Bearer token**（`Authorization: Bearer <jwt>`）

`auth.md` §14.5 说「JWT/access_token 不是独立的认证根——必须由应用层证书或有效 refresh_token 兑换」，但没有指定 Gateway 层的 enforcement 点。

**影响**：若 Gateway 实现时未在 Agent 端点显式 reject Bearer token 而仅做证书校验，则持有有效 JWT（但无证书）的攻击者可能通过 Bearer header 绕过证书要求——JWT 的 `aud` 字段若未严格绑定 transport type，可被跨 transport 重放。

**修复建议**：
1. 在 `03-mcp-security.md` §2.2 Agent 端点安全要求中增加：「拒绝任何携带 `Authorization: Bearer` header 的请求（`401 BearerTokenNotAcceptedOnAgentEndpoint`）」
2. 在 `auth.md` §14.5 中增加 Gateway 层 enforcement 声明：「Gateway 按 endpoint type 校验 credential type——Browser/Web 端点允许 JWT Bearer，Agent/CLI 端点仅接受 Swarm-Certificate-Chain + Swarm-Signature」

---

## Medium（建议关注）

### M1 — WASM Store reset 缺乏跨 tick 状态泄漏验证 checklist

**文件**：`/data/swarm/docs/specs/core/04-wasm-sandbox.md` §1（行 41–45）

**问题描述**：Sandbox worker pool 模型依赖每 tick Store reset（清空线性内存、重置 fuel counter、重建 Instance）防止跨 tick 状态泄漏。但文档未列出**验证 checklist**——如何确认所有 WASM 可变状态被清除：
- Wasmtime `Engine` 级别的内部缓存（如 compiled code cache、type registry）是否可能跨 tick 残留状态
- `Store` reset 后 global variables / `data` segments 是否正确重置为初始值
- Instance 重建是否使用重新编译的模块还是缓存模块（缓存模块的 `data` segment 状态？）

**影响**：低概率但高影响——若存在未被 reset 的状态通道，玩家 A 的 WASM 可能在 tick N 残留数据到 tick N+1 的玩家 B 执行中。

**修复建议**：在 `04-wasm-sandbox.md` §1 后增加 Store reset verification checklist（或引用 `sandbox_boundary` 测试覆盖），明确验证：
- 每个 tick 后 WASM 线性内存全零
- Global mutable variables 重置为初始值
- Fuel counter 清零
- Instance 的 `data` segments 重新初始化

### M2 — 19 个 Auth 工具存在于 auth.md 但未注册入 api-registry.md / auth_api.idl.yaml

**文件**：
- `/data/swarm/docs/design/auth.md` §10.1（行 700–723）
- `/data/swarm/docs/specs/reference/api-registry.md` §3.3（行 399–414）
- `/data/swarm/docs/specs/reference/auth_api.idl.yaml`

**问题描述**：

`auth.md` §10.1 列出了 20 个 auth MCP 工具。但 `api-registry.md`（由 `auth_api.idl.yaml` 自动生成）仅包含 11 个（5 lifecycle + 6 cert/device）。**缺失 9+ 个工具**的 IDL 注册：

| 工具名 | auth.md §10.1 | api-registry §3.3 | auth_api.idl.yaml |
|--------|:-----------:|:-----------------:|:-----------------:|
| `swarm_register_challenge` | ✅ | ❌ | ❌ |
| `swarm_submit_csr` | ✅ | ❌ | ❌ |
| `swarm_renew_certificate` | ✅ | ❌ | ❌ |
| `swarm_get_server_trust` | ✅ | ❌ | ❌ |
| `swarm_update_profile` | ✅ | ❌ | ❌ |
| `swarm_change_password` | ✅ | ❌ | ❌ |
| `swarm_request_password_reset` | ✅ | ❌ | ❌ |
| `swarm_admin_create_password_reset` | ✅ | ❌ | ❌ |
| `swarm_confirm_password_reset` | ✅ | ❌ | ❌ |
| `swarm_register_passkey` | ✅ | ❌ | ❌ |
| `swarm_recover_with_passkey` | ✅ | ❌ | ❌ |
| `swarm_bind_email` | ✅ | ❌ | ❌ |
| `swarm_delete_account` | ✅ | ❌ | ❌ |
| `swarm_restore_account` | ✅ | ❌ | ❌ |
| `swarm_federated_login` | ✅ | ❌ | ❌ |

**影响**：`api-registry.md` 声明为「单一权威来源」（§0 行 3–6），CI 基于 IDL 做一致性检查。缺失注册 → 这些 auth 工具无法通过 `generate_api_registry.py` 生成 → SDK stub 缺失 → AI agent 无法通过 MCP schema 发现这些工具。**CSR 提交流程的核心工具（`swarm_submit_csr`）也在缺失列表中**——这意味着整个 CSR 注册流程在机器可读层面不存在。

**修复建议**：
1. 在 `auth_api.idl.yaml` 中补全所有 auth.md §10.1 列出的工具
2. 重新运行 `generate_api_registry.py` 更新 `api-registry.md`
3. CI 检查模式验证一致性

### M3 — `DeployPayload.signed_at` 字段缺乏 server-side clock skew 校验

**文件**：`/data/swarm/docs/specs/security/09-command-source.md` §3.2（行 77–101）

**问题描述**：`DeployPayload` 包含 `signed_at: u64`（unix 秒），但 §3.3 验证流程中未包含 `signed_at` 的时效性检查——仅校验 version_counter 防重放。攻击者可以：

1. 获取一个旧的有效 DeployPayload（从日志/网络抓包）
2. 递增 `version_counter` 并重新签名（需要持有私钥——但如果私钥未被吊销则可行）
3. 若 `version_counter` 未达到当前值，重放失败；但若攻击者先正常部署递增 counter，再重放旧的 payload → version_counter 已过期自动拒绝

实际上 `version_counter` 防重放已覆盖此场景。但 `signed_at` 字段的存在暗示有独立的时间窗口检查——若实现时不校验 `signed_at`，该字段成为冗余；若校验，需明确 skew 容忍度。

**影响**：Low——`version_counter` 已充分防重放。`signed_at` 冗余但不造成漏洞。

**修复建议**：在 §3.3 验证流程中明确 `signed_at` 的校验语义（是否检查、skew 容忍度），或标注为 optional informational field。

### M4 — Canonical request body_hash 缺乏序列化规范

**文件**：`/data/swarm/docs/design/auth.md` §5.6c（行 361–414）

**问题描述**：

Canonical request signature 包含 `body_hash: <blake3 canonical body hash>`（行 376），但未定义「canonical body」的序列化规则：
- JSON body 的 canonical 序列化格式（key 排序？空格？缩进？）
- 空 body 的 `body_hash` 是否等于 `blake3("")`（行 397 提到但仅在序列化规范中）
- multipart body 的 canonical 形式

**影响**：若 client 和 server 对同一 JSON body 产生不同的 `body_hash`（因序列化差异），签名验证失败。这不会导致安全漏洞（验签失败即拒绝），但会导致互操作性问题。

**修复建议**：在 §5.6c 中增加 canonical body 序列化规范：
- JSON body：按 key 字典序排序、无缩进、无空格、UTF-8
- 空 body / 无 body：`body_hash = blake3("")` 的 hex 值
- Multipart/form-data：不适用 canonical request 签名（multipart 请求使用独立签名机制）

### M5 — CVE-SLA 季度人工审查频率偏低

**文件**：`/data/swarm/docs/specs/security/CVE-SLA.md` §monitor（行 44–46）

**问题描述**：CVE-SLA 规定对 Wasmtime 安全公告「每季度人工审查」。对于 Critical/High 漏洞，`cargo audit` CI 自动化可即时发现。但对于：
- 漏洞在 Wasmtime 公告中披露但尚未进入 RustSec DB 的时间窗口
- 非 Rust crate（如 Wasmtime 的 C API binding、WASI 实现细节）的漏洞
- 季度审查间隔长达 90 天——足以让一个 Critical 漏洞在不知情的情况下运行数月

**影响**：低——`cargo audit` CI 覆盖了最常见的发现路径。但季度间隔对「公告已发但 DB 未同步」的窗口期无覆盖。

**修复建议**：增加月度 RSS/邮件订阅 Wasmtime security advisory 的自动化监控（非人工），或缩短人工审查至每月。无需修改 SLA 响应时间——仅提高**发现**频率。

---

## Low / Nits（可选改进）

### L1 — WebSocket per-message tick 绑定缺乏窗口/宽松语义定义

**文件**：`/data/swarm/docs/design/auth.md` §10.5a（行 815）

**问题描述**：WebSocket per-message MAC 包含 `tick` 字段，但未定义 tick 是否必须严格等于当前 tick 还是允许 ±N 窗口。快速 tick 速率下，客户端发送消息时 tick 可能与服务端当前 tick 差 1-2。

**修复建议**：定义 `tick` 字段的容许偏差（建议 ±2 ticks），超出窗口则断开连接。

### L2 — 管理端日志中 `reset_url` 脱敏描述模糊

**文件**：`/data/swarm/docs/design/auth.md` §11.3（行 1114）

**问题描述**：「管理端日志必须脱敏 `reset_url`」——但未说明脱敏到什么程度。是完整替换为 `<redacted>`、保留 URL scheme+host、还是保留 token 前缀？

**修复建议**：明确脱敏格式，如 `https://<host>/auth/reset?token=<redacted_32_hex_chars>`

### L3 — `omitted_count` 分桶边界可被逐步探测

**文件**：`/data/swarm/docs/specs/security/05-visibility.md` §10.2（行 379–391）

**问题描述**：`omitted_count` 分桶（0 → "few" → "some" → "many" → "extreme"）是优秀的 oracle 防护设计。但攻击者仍可通过多次查询边界附近的 snapshot，观察分桶标签何时跳变（如从 "few" 到 "some"），推断隐藏实体数量范围。攻击成本从 O(1) 升高到 O(bucket_width)，显著降低但未根除。

**影响**：极低——攻击需要精确控制实体数量并在桶边界反复测试，实践中不构成威胁。

**修复建议**：维持当前设计。可在文档中标注此为「显著降低 oracle 精度（~10×）但非根除」以明确 trade-off。

### L4 — auth_api.idl.yaml 中 `auth_rate_limit_hit` event 的字段不完整

**文件**：`/data/swarm/docs/specs/reference/auth_api.idl.yaml` 行 496–505

**问题描述**：`auth_rate_limit_hit` trace event 包含 `endpoint, key_type, key_value, current_count, limit` 五个字段，但在 api-registry.md §6.2（行 703）中仅列出了 `tick, endpoint, key_type, key_value, current_count, limit` 四个字段——缺少 `key_value`。IDL YAML 有 5 个字段，生成产物只有 4 个。

**影响**：仅在 `auth_rate_limit_hit` 审计事件中丢失 `key_value` 字段。低影响——仅影响调试/审计。

**修复建议**：检查 `generate_api_registry.py` 是否正确解析所有 IDL 字段，或在 IDL 的 `auth_rate_limit_hit` 中验证字段数。

---

## Strengths（设计亮点）

1. **多层 CSR admission control**：PoW + per-IP + per-ASN + global semaphore + bounded queue + audit throttle 六层防护，纵深防御设计优秀，不依赖单层机制。

2. **应用层证书模型根本性避免了 TLS client certificate 的部署复杂性**：服务器 CA 不进系统 trust store，HTTP 不安全传输仍可认证——这对内网/离线/自托管场景是实质性安全收益。

3. **Refresh token family tracking + rotation + reuse detection**：与简单的 bearer token 不同，token family 机制使得 intercepted token 在被使用后立即失效整个 session 链——远超行业平均水平。

4. **Oracle 防线闭合**（`05-visibility.md` §10）：`NotVisibleOrNotFound` 等价码、`omitted_count` 分桶、`NotEligible` 等价类——三层 oracle 防护覆盖了实体存在性、数量、和攻击条件三种信息泄露向量，设计非常全面。

5. **Deferred command model + read-only host functions**：WASM 只能通过 JSON 返回指令意图，不能直接调用 mutating host function——这是一个强安全边界，将 WASM 沙箱逃逸的影响限制为「返回恶意指令」（仍会被 engine 校验拒绝），而非「直接修改世界状态」。

6. **持久化分层 + replay-critical subset**：FDB 原子提交 10 字段 replay-critical subset，对象存储异步写入 RichTraceBlob——清晰分离了确定性保证与调试便利性。Blob 丢失不影响确定性 replay——这是正确且经过深思熟虑的设计选择。

7. **DNS rebinding 多层防御**（`03-mcp-security.md` §2.3）：bind to unix socket / 127.0.0.1、Host header 校验、禁止 redirect to private IP、SSRF 防护——覆盖了 rebinding 的 6 种攻击向量。

---

## CrossCheck — 需要跨方向检查

- **CX-1**: Audience transport 标签三文档不一致（B1）→ 建议 **Interface 方向**检查 `03-mcp-security.md` §2.2 的 audience 字符串是否应与 `09-command-source.md` §7.0 对齐为 `agent-mcp`，建议 **Engine 方向**确认 Gateway canonical request audience 解析逻辑使用哪个 transport 枚举

- **CX-2**: Tutorial 来源双重定义（B2）→ 建议 **Engine 方向**检查 Source Gate 实现中 Tutorial source 是否有独立 budget 字段，确认应使用 §2.1 还是 §2.2 的定义

- **CX-3**: 19 个 Auth 工具未注册入 IDL（M2）→ 建议 **Interface 方向**检查 `api-registry.md` 是否需要重新生成以包含完整 auth 工具集，建议 **Auth 方向**确认 `auth_api.idl.yaml` 应补全所有 auth.md §10.1 列出的工具

- **CX-4**: CRL fallback 枚举两处不一致（H1）→ 建议 **Auth 方向**统一 `revocation_fallback` 的 4 值枚举，消除 §15.2a 与 §15.6 的差异

- **CX-5**: Canonical body_hash 序列化规范缺失（M4）→ 建议 **Interface 方向**在 canonical request 规范中增加 body serialization 规则，建议 **Engine 方向**确认 Gateway 当前 body_hash 计算逻辑并文档化