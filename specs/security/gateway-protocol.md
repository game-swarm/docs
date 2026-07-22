# Gateway 协议

> 详见 design/interface.md 与 design/auth.md。本文档汇聚 Gateway 入口、realtime relay、MCP forwarding 与 Auth REST routes 的传输合同。

## 1. 架构定位

Gateway 是引擎与外部世界的唯一入口。Browser、CLI 和 AI Agent 都通过 Gateway 连接 Swarm 世界，并都使用应用层证书签名进行认证。

```text
                    +--------------+
Browser  --WS/REST->|              |
CLI      -----REST->|   Gateway    |--NATS--> Engine
Agent    --MCP/REST>| Rust (axum)  |<-HTTP-- Engine (health)
                    +--------------+
```

Gateway 是 Rust (axum) 无状态服务，可水平扩展。所有 Gateway 实例共享同一 NATS 集群，无实例间通信。

## 2. Transport 拆分

| Transport | 协议 | 端口 | 用途 | 认证方式 |
|-----------|------|------|------|---------|
| **Browser Realtime** | WebSocket (`GET /ws`) | 8082 | 人类玩家 Web UI 实时状态推送 | Application certificate signed ticket |
| **MCP Tool Calls** | MCP over HTTP (`POST /mcp`) | 8082 | AI agent、CLI 或 Browser 的游戏 request/response 工具调用 | Application certificate + canonical request signature |
| **Auth REST** | REST (`/auth/*`) | 8082 | CSR、证书生命周期、Server CA trust discovery | Explicit REST action routes；按 route 要求 PoW、CSR 签名或 application certificate signature |
| **Health** | HTTP (`GET /healthz`) | 8082 | Gateway/NATS relay 健康检查 | 无业务数据访问 |
| **SDK Fetch** | HTTP (`GET /sdk/:lang`) | 8082 | SDK starter package | Application certificate + canonical request signature；SDK REST 不属于 auth IDL |

WebSocket 路径 (`/ws`) 负责实时状态订阅；游戏工具调用通过 HTTP `POST /mcp`；Auth 生命周期通过 `/auth/*` REST action routes。Gateway 不提供任何替代的 Auth 生命周期入口。

判定规则：

- 缺少必需 transport binding 字段或签名 payload 与实际请求 transport 不一致 -> `401 InvalidTransportBinding`。
- 签名有效但证书 allowed audience 不包含实际请求 transport -> `403 AudienceMismatch`。
- Browser、CLI、Agent、MCP、REST、WebSocket 和 spectator transport 不可互换。
- 普通 CORS 可用于限制浏览器访问来源，但不得作为身份或信任依据。

## 3. WebSocket 协议

### 3.1 连接

```text
Client -> Gateway: wss://<host>/ws?room=<room>&sessionId=<nonce>&certId=<cert_id>&expires=<unix_ms>&signature=<ed25519_hex>
  signature payload binds cert_id, player_id, room, sessionId, expires and actual transport.
  Gateway verifies expiry, replay/session uniqueness, certificate public key, revocation state and allowed audience membership.
Gateway -> Client: {"type":"connected","player_id":42,"world_id":"world_v1","tick":4521}
```

`player_id` is derived from the verified certificate subject. Gateway must not accept a caller-supplied `playerId` as authority.

### 3.2 Delta 推送

每 tick 结束后，Gateway 通过 NATS 接收 delta 并推送到 WebSocket：

```json
{
  "schema": "swarm.realtime.v1",
  "payload": {
    "tick": 4522,
    "last_tick": 4521,
    "player_id": 42,
    "full_snapshot": true,
    "changed_entities": [],
    "removed_entities": [1001, 1002],
    "state_checksum": 123456789
  }
}
```

Delta 仅包含对 subscriber 可见的实体，经 `is_visible_to(subscriber, tick)` 过滤。

### 3.3 客户端同步

客户端维护 `last_tick`。若发现 tick gap，必须重新获取当前 snapshot；认证仍使用应用层证书签名，不使用浏览器 cookie fallback。

## 4. REST API

| 端点 | 方法 | 用途 | 可见性过滤 |
|------|------|------|-----------|
| `/auth/register/challenge` | POST | 创建一次性 PoW challenge | 无 |
| `/auth/csr/submit` | POST | 提交 CSR、PoW nonce 和 CSR 签名 | 无；成功主体来自 CSR/certificate |
| `/auth/cert/renew` | POST | 续签证书 | owner |
| `/auth/cert/revoke` | POST | 吊销证书 | owner/admin scope |
| `/auth/cert/list` | GET | 列出当前 player 可见证书 | owner |
| `/auth/cert/check` | POST | 检查证书链、吊销状态、audience 和用途 | owner/admin scope |
| `/auth/server/trust` | GET | 返回 Server CA fingerprint、算法和 operator label | public |
| `/healthz` | GET | Gateway 健康检查 | 无 |
| `/sdk/:lang` | GET | 获取 SDK starter package | 与 Gateway 请求认证一致 |

游戏查询和历史数据通过 `POST /mcp` 提供；Gateway 当前不暴露独立的 room、map、tick 或 player-status REST 路由。SDK REST 是 interface domain 的 fetch route，不属于 auth IDL。

`/healthz` 返回 Gateway NATS relay readiness。NATS relay 成功连接并订阅 `NATS_SUBJECT` 后返回 HTTP 200 和 `{"status":"ok","nats":"ready"}`；未就绪时返回 HTTP 503 和 `{"status":"degraded","nats":"unavailable"}`。Gateway HTTP server 保持运行并按 `NATS_RETRY_DELAY_MS`（默认 2000ms）重试。

## 5. MCP 协议

MCP transport 遵循 JSON-RPC over HTTP POST。Gateway 作为 MCP 反向代理，将请求转发至 Engine：

```text
Client -> Gateway (POST /mcp) -> Engine (POST /mcp)
```

Gateway 职责：

- 应用层证书 + canonical request 签名验证。
- 检查 certificate usage、scope、expiry、revocation 和 allowed audience membership。
- 按每个工具声明的 `rate_limit` 与 `rate_limit_key` 维护独立计数器；Gateway 不叠加未由 design/IDL 声明的 per-player、per-transport 或 aggregate MCP cap。
- 请求路由到 Engine 的 MCP 端点；不得代理 Auth REST routes。
- 响应结果转发。

Gateway 转发到 Engine 的 `POST /mcp` 必须使用内部 HMAC-SHA256 请求签名。Canonical payload 为 `METHOD\nPATH\nTIMESTAMP\nNONCE\nPLAYER_ID\nTICK\nCERT_ID\nCERT_FINGERPRINT\nTRANSPORT\nSCOPES\nAUTH_MODE\nSHA256(body)`。对应 headers 为 `X-Swarm-Proxy-Timestamp`、`X-Swarm-Proxy-Nonce`、`X-Swarm-Proxy-Signature`、`X-Swarm-Proxy-Body-Sha256`、`X-Swarm-Principal-Player-Id`、`X-Swarm-Principal-Cert-Id`、`X-Swarm-Principal-Cert-Fingerprint`、`X-Swarm-Principal-Transport`、`X-Swarm-Principal-Scopes`、`X-Swarm-Principal-Auth-Mode` 和可选 `X-Swarm-Tick`。Gateway 必须先移除所有 caller-supplied internal principal headers，再注入已验证 principal。双方必须拒绝空 secret、过期 timestamp、重复 nonce 和无效签名。

MCP 工具清单见 `specs/reference/mcp-tools.md`。该清单不得包含注册、CSR、续签、吊销、列表、检查或 Server CA trust discovery 入口。

## 6. NATS 主题结构

| 主题 | 方向 | 内容 |
|------|------|------|
| `swarm.realtime.v1`（可由 `NATS_SUBJECT` 覆盖） | Engine -> Gateway | 定向 tick delta；当前 Gateway 唯一订阅的 realtime subject |

### 6.1 NATS 安全

NATS 安全边界使用 TLS + per-role ACL。Gateway、Engine、Sandbox worker 使用不同 NATS credential，按角色限制 publish/subscribe topic：

| Role | Publish | Subscribe |
|------|---------|-----------|
| Engine | `NATS_SUBJECT`、sandbox request subjects | sandbox replies |
| Gateway | - | `NATS_SUBJECT` |
| Sandbox worker | sandbox replies | sandbox request queue group |

Sandbox deploy/tick subjects 除 TLS/ACL 外还必须使用 `SWARM_NATS_AUTH_SECRET` HMAC 信封。Gateway realtime 只转发包含非空目标 player/session 的消息，不允许无目标广播。Gateway 保持无状态：canonical request 的 `(cert_id, transport, nonce)` 原子去重由单一逻辑写者 Auth Service 的共享 replay store 执行，Gateway 必须在转发前调用该校验；不使用本地 Gateway nonce 文件或 sticky session。Auth Service 使用 `SWARM_AUTH_NONCE_PATH` 持久化，Engine 对 Gateway proxy request 的 nonce replay 状态使用 `SWARM_PROXY_NONCE_PATH` 持久化。生产部署必须将这些路径放在 `/tmp` 以外的可写持久卷上；读取、解析、RPC 或原子写入失败时认证 fail closed。

## 7. 降级模式

| 场景 | Gateway 行为 | 客户端影响 |
|------|-------------|-----------|
| NATS 不可达 | HTTP server 保持运行；NATS relay 按 `NATS_RETRY_DELAY_MS` 重试 | `/healthz` degraded；实时推送暂停 |
| Engine MCP 不可达 | 返回 503，并记录 signed principal audit | MCP 请求失败；Auth REST 不受影响 |
| Auth Service 不可达 | 需要 Auth state 的 routes 返回 503；已缓存 revoked certificate miss 时 fail closed | 证书续签/检查受影响；认证不可绕过 |
| Nonce store 不可写 | 认证 fail closed | signed request 被拒绝 |

## 8. Security Invariants

| 不变量 | 说明 |
|--------|------|
| Single ingress | 外部客户端只能访问 Gateway；Engine MCP 只接收 Gateway 内部 signed proxy request |
| Auth REST only | Auth 生命周期只有 `/auth/*` REST action routes；不存在替代入口 |
| Certificate identity binding | 请求签名必须绑定 `cert_id`、`player_id`、actual transport 与 canonical payload |
| Audience membership | 证书 allowed audience 必须覆盖实际请求 transport；失败为 `403 AudienceMismatch` |
| Invalid transport binding | 缺少或不匹配 transport binding 失败为 `401 InvalidTransportBinding` |
| Visibility | 所有 Gateway 输出必须执行 `is_visible_to` 或对应 public/spectator policy |
| WSS | 生产环境强制 wss://，禁止 ws:// |

## 9. Transport Auth Matrix（design-derived consolidated contract）

以下为所有 transport 的认证要求；mcp-security.md 和 command-source.md 均引用此表。

| Transport | Auth material | Binding material | Browser-only controls | 失败码 |
|-----------|---------------|------------------|-----------------------|--------|
| Browser WS | Application certificate signed ticket | query `room`、`sessionId`、`certId`、`expires`、`signature` binding actual `ws` transport | CORS/origin may limit access but is not trust | `401 InvalidTransportBinding` / `403 AudienceMismatch` |
| Auth REST | PoW/CSR signature or application certificate, depending on route | `SWARM-REQUEST-V1` actual REST transport | CORS may exist but is not trust | `401 InvalidTransportBinding` / `403 AudienceMismatch` |
| MCP | Application certificate + signed request | `SWARM-REQUEST-V1` actual MCP transport | N/A | `401 InvalidTransportBinding` / `403 AudienceMismatch` |
| SDK REST | Application certificate + signed request | `SWARM-REQUEST-V1` actual REST transport | CORS may exist but is not trust | `401 InvalidTransportBinding` / `403 AudienceMismatch` |
| Replay Viewer | Anonymous public replay or application certificate for private replay | replay transport or signed request | N/A | 401 / 403 |
| Admin | `ClientAuthCertificate` with `admin` scope + signed request | `SWARM-REQUEST-V1` actual REST/MCP admin transport | N/A | 401 / 403 |

禁止项：

- Browser WS certificate ticket 使用 `certId` query 字段；Gateway 从已验证证书缓存或 configured certificate public-key source 解析公钥，不接受 `playerId` 作为证书 ID。
- Auth lifecycle routes 不得通过任何替代入口暴露。
- Swarm CA 不得安装到系统/浏览器 trust store；它只用于应用层证书链验证。
- Admin 端点必须使用带 `admin` scope 的 `ClientAuthCertificate` + signed request；不以传输层 mTLS 作为默认身份根。
