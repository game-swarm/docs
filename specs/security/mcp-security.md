# MCP 接口安全规范

> 详见 design/interface.md 与 design/auth.md。本文只描述 MCP/Gateway 安全合同；Auth 生命周期语义以显式 REST action routes 为唯一 canonical surface。

## 1. 核心原则

MCP 是 AI 玩家的观察、部署、调试、经济和赛事操作界面。它不承载 Auth 生命周期；注册、CSR、续签、吊销、列表、检查和 Server CA trust discovery 只能走显式 REST action routes。

Auth 生命周期唯一入口：

| Route | 语义 |
|-------|------|
| `POST /auth/register/challenge` | 创建一次性 PoW challenge |
| `POST /auth/csr/submit` | 提交 CSR、PoW nonce 和 CSR 签名；成功后签发证书 |
| `POST /auth/cert/renew` | 使用仍有效的应用层证书续签同用途证书 |
| `POST /auth/cert/revoke` | 吊销指定证书并写入 audit trail |
| `GET /auth/cert/list` | 列出当前 player 可见证书 |
| `POST /auth/cert/check` | 检查证书链、吊销状态、audience 和用途 |
| `GET /auth/server/trust` | 返回 Server CA fingerprint、算法和 operator label |

所有客户端，包括 Browser、CLI 和 AI Agent，都使用应用层证书签名作为认证路径。浏览器 cookie 或浏览器请求头检查不是认证分支；普通 CORS 可作为浏览器访问控制存在，但不得作为信任或身份依据。

## 2. 架构定位

```text
Human Browser / CLI / AI Agent
    |
    | signed REST request or signed MCP request
    v
Gateway certificate auth handler
    |
    +--> Auth Service / Domain     (/auth/* REST action routes)
    |
    +--> Engine MCP endpoint       (/mcp game tools only)
    |
    +--> WebSocket realtime push   (/ws server-to-client deltas)
```

MCP 工具只属于游戏 API surface。注册、CSR、证书续签、吊销、列表、检查和 Server CA trust discovery 必须走 `/auth/*` REST action routes。

普通 MCP 世界读取必须执行统一可见性过滤。`swarm_get_drone` 与 `swarm_get_structure` 可返回 visibility-filtered `overload_pressure`：目标 owner 始终可见 `total`，contributing attacker 可见 `total`，第三方只见 visible-source contributions 且没有 `total`；仅当 caller 既非 owner/contributor 且没有 visible contribution 时字段省略。结构 cooldown、drone `code_hash` 与 `fuel_used` 仍保持 owner-only，不因实体或 overload pressure 可见而扩大。

`swarm_get_drone_efficiency` 返回的 aggregate efficiency/factors 是 owner-only strategy metrics；普通可见性不能授权该工具。

MCP/JSON-RPC 玩家可见错误不得成为目标状态 oracle。target-side absent、invisible、type-ineligible、cooldown 与 protected target `SpawningGrace` 必须映射为 `NotVisibleOrNotFound`，不返回目标详情或 remaining ticks；source-owned cooldown 可返回 `CooldownActive`。

## 3. 应用层证书要求

证书由单层 Server CA 签发，客户端私钥由客户端持有。证书携带用途与 allowed audience：

| Certificate | 用途 | 签名 payload | Audience 检查 |
|-------------|------|--------------|---------------|
| `ClientAuthCertificate` | REST 认证请求、证书续签、普通控制面请求 | `SWARM-REQUEST-V1` | 实际请求 transport 必须属于 allowed audience |
| `CodeSigningCertificate` | WASM/module deploy | `SWARM-DEPLOY-V1` | deploy 的实际 transport 必须属于 allowed audience |

Gateway/Verifier 必须先验证证书链、用途、有效期、吊销状态和签名，再检查请求 transport 与证书 audience 的 membership。`player_id` 从证书主体注入，客户端请求体中的自报身份不得作为权限依据。

Canonical request signature headers：

```text
Swarm-Certificate: <base64 ClientAuthCertificate or CodeSigningCertificate>
Swarm-Cert-Id: <certificate_id>
X-Swarm-Transport: <mcp|rest|ws|replay>
Swarm-Timestamp: <unix_ms>
Swarm-Nonce: <random 128-bit>
Swarm-Signature: <ed25519 signature by user private key>
```

`SWARM-REQUEST-V1` payload 必须绑定服务器实际接收的 transport：

```text
SWARM-REQUEST-V1
TRANSPORT
METHOD
SCHEME
AUTHORITY
PATH_AND_QUERY
TIMESTAMP
NONCE
CERTIFICATE_ID
PLAYER_ID
BLAKE3(stable_json(body))
```

Verifier 必须检查签名中的 `TRANSPORT` 与 `X-Swarm-Transport` 及实际入口一致，且属于证书 allowed audience；`SCHEME + AUTHORITY + PATH_AND_QUERY` 必须与实际请求完全一致。`TIMESTAMP` 必须可解析且处于固定 60 秒 freshness window；`NONCE` 在 `(cert_id, transport)` 作用域内原子记录并拒绝重复。Timestamp/nonce 解析失败或 replay store 读/原子写失败必须 fail closed。

Canonical auth errors：

| Error | HTTP | 语义 |
|-------|------|------|
| `InvalidTransportBinding` | 401 | 签名 payload 中的 transport 与实际请求 transport 不一致，或缺少必需 transport 字段 |
| `AudienceMismatch` | 403 | 签名有效，但证书 allowed audience 不覆盖该 transport |
| `InvalidCertificate` | 401 | 证书链、签名、usage、expiry 或 revocation 校验失败 |
| `RateLimited` | 429 | Auth operation rate limit exceeded |
| `RequestExpired` | 401 | Timestamp 无效或超出 60 秒 freshness window |
| `ReplayDetected` | 409 | Nonce 重复，或 replay store 无法安全读写 |

## 4. Browser 私钥与 Server Trust

Browser 生成 exportable Ed25519 key 时必须 fail closed：

- CSR 前调用 `GET /auth/server/trust` 并要求用户显式确认 Server CA fingerprint。
- 首次确认后的 fingerprint 必须持久化；再次连接时 fingerprint 变化必须 fail closed，直到用户显式确认新 fingerprint。
- 私钥导出必须由用户手动触发，并要求导出密码。
- 导出密码使用 Argon2id 派生 KEK，KEK 用于 AES-256-GCM 加密私钥，输出 ciphertext bundle。
- 用户手动导入/导出 bundle；服务端永不保存 bundle、KEK、密码或私钥。

## 5. MCP 请求安全

MCP transport 遵循 JSON-RPC over HTTP POST。Gateway 作为 MCP 反向代理，将请求转发至 Engine：

```text
Agent/CLI/Browser -> Gateway (POST /mcp) -> Engine (POST /mcp)
```

Gateway 职责：

- 验证应用层证书与 canonical request signature。
- 检查证书 usage、scope、revocation、expiry 和 allowed audience membership。
- 按每个工具声明的 `rate_limit` 与 `rate_limit_key` 维护独立计数器；actual transport 进入认证/replay scope，不额外形成 aggregate rate-limit key。
- 移除 caller-supplied internal principal headers，再注入已验证 principal。
- 将游戏 MCP 请求路由到 Engine；不得代理 `/auth/*` REST action routes。

Gateway 转发到 Engine 的 `POST /mcp` 必须使用内部 HMAC-SHA256 请求签名。Canonical payload 为 `METHOD\nPATH\nTIMESTAMP\nNONCE\nPLAYER_ID\nTICK\nCERT_ID\nCERT_FINGERPRINT\nTRANSPORT\nSCOPES\nAUTH_MODE\nSHA256(body)`。对应 headers 为 `X-Swarm-Proxy-Timestamp`、`X-Swarm-Proxy-Nonce`、`X-Swarm-Proxy-Signature`、`X-Swarm-Proxy-Body-Sha256`、`X-Swarm-Principal-Player-Id`、`X-Swarm-Principal-Cert-Id`、`X-Swarm-Principal-Cert-Fingerprint`、`X-Swarm-Principal-Transport`、`X-Swarm-Principal-Scopes`、`X-Swarm-Principal-Auth-Mode` 和可选 `X-Swarm-Tick`。Gateway 和 Engine 必须拒绝空 secret、过期 timestamp、重复 nonce 和无效签名。

MCP 工具清单见 `specs/reference/mcp-tools.md`；该清单不得包含注册、CSR、续签、吊销、列表、检查或 Server CA trust discovery 入口。

## 6. WebSocket 安全

WebSocket 仅用于服务器向客户端推送实时 delta，不承载写操作或 Auth 生命周期。

- `GET /ws` 握手必须由应用层证书签名 ticket 认证。
- 握手 ticket 必须绑定 `cert_id`、`player_id`、room、expiry、actual transport 和 nonce/session uniqueness。
- 连接建立后 Gateway 只处理 `Pong`/`Close`；其它客户端消息不进入游戏写路径。
- 写操作与工具调用始终走 signed REST 或 `POST /mcp`。
- Gateway 每 30 秒发送 ping，60 秒未收到 pong 时关闭连接。
- 公开 spectator WebSocket 是匿名只读显示面；它不能提交指令，也不能复用 authenticated transport audience。

## 7. Deploy 签名

`swarm_deploy` 使用 `CodeSigningCertificate` 和 `SWARM-DEPLOY-V1` payload。签名必须绑定：

- `wasm_hash`
- `metadata_hash`
- `player_id`
- `world_id`
- `module_slot`
- `version_counter`
- `transport`
- `signed_at`

证书 allowed audience 作为独立检查执行，不写入证书外的自报权限。服务端验证证书链、usage=`code_signing`、scope、有效期、吊销状态、deploy payload 签名、actual transport binding 和 audience membership。`compiled_artifact_hash` 由服务端编译后派生，不进入客户端签名 payload。

## 8. 网络与运行时防护

| 防护 | 要求 |
|------|------|
| Replay | Auth Service shared canonical-request replay store 使用 `SWARM_AUTH_NONCE_PATH`；Gateway 无状态调用它；Engine proxy nonce store 使用 `SWARM_PROXY_NONCE_PATH` |
| Fail closed | nonce store 读取、解析或原子写入失败时认证失败 |
| NATS | Sandbox deploy/tick subjects 除 TLS/ACL 外还必须使用 `SWARM_NATS_AUTH_SECRET` HMAC 信封 |
| Directed realtime | Gateway realtime 只转发包含非空目标 player/session 的消息，不允许无目标广播 |
| CORS | 可限制浏览器允许访问的 Web UI origins，但 CORS 不提供身份信任 |
| Server CA | 只用于 Swarm 应用层证书链，不得安装到系统或浏览器 trust store |

生产部署必须将 nonce store 路径放在 `/tmp` 以外的可写持久卷上，Engine nonce store 父目录必须为 engine 用户所有、私有权限且不能是 symlink。规则模组是进程内 Bevy Plugin；安全深度还包括 Gateway 应用层认证、mod 源码审查与可审计 hook/schedule graph。
