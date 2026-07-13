# Gateway 协议

> 详见 design/interface.md。本文档汇聚 specs/core/01 §4、specs/security/03 §2、specs/security/05 §3、specs/security/09 §7.0 中关于 Gateway 的分散定义。

## 1. 架构定位

Gateway 是引擎与外部世界的唯一入口——所有客户端（Browser、CLI、MCP Agent）通过 Gateway 连接 Swarm 世界。

```
                    ┌──────────────┐
  Browser ──WS─────→│              │
  CLI     ──REST───→│   Gateway    │──NATS──→ Engine
  Agent   ──MCP────→│Rust (axum), 无状态│←─REST──→ Engine (health/metrics)
                    └──────────────┘
```

Gateway 是 Rust (axum) 无状态服务，可水平扩展。所有 Gateway 实例共享同一 NATS 集群，无实例间通信。

## 2. Transport 拆分

| Transport | 协议 | 端口 | 用途 | 认证方式 |
|-----------|------|------|------|---------|
| **Browser** | WebSocket | 8082 | 人类玩家 Web UI | Web session token 或 `Swarm-Certificate` + `Swarm-Cert-Id` + signed request |
| **REST** | HTTP/1.1 | 8082 | CLI / 外部工具 | Application certificate + signed request；Web session token 仅兼容路径 |
| **Agent** | MCP (HTTP) | 8082 | AI agent MCP 连接；无 Agent-facing subscription | Application certificate + signed request |
| **Replay Viewer** | HTTP/1.1 | 8082 | 回放查看器（公开） | Application certificate 或匿名（public replay） |

**判定规则**（specs/security/09 §7.0）：
- 缺少 `X-Swarm-Transport` header → 拒绝 (`401 MissingTransportHeader`)
- 应用层证书 `audience` 不匹配请求 transport → 拒绝 (`403 AudienceMismatch`)
- MCP application certificate 不得用于 WebSocket（Agent ↔ Browser 不可互换）

## 3. WebSocket 协议

### 3.1 连接

```
Client → Gateway:  wss://<host>/ws?room=<room>&sessionId=<nonce>&certId=<cert_id>&expires=<unix_ms>&signature=<ed25519_hex>
  signature payload = `${sessionId}:${certId}:${room}:${expires}`
  Gateway verifies expiry, replay/session uniqueness, certificate public key and configured Origin allowlist.
Gateway → Client:  {"type": "connected", "player_id": 42, "world_id": "world_v1", "tick": 4521}
```

### 3.2 Delta 推送

每 tick 结束后，Gateway 通过 NATS 接收 delta 并推送到 WebSocket：

```
NATS topic: `NATS_SUBJECT`（默认 `swarm.realtime.v1`）

Delta 格式:
{
  "schema": "swarm.realtime.v1",
  "payload": {
    "tick": 4522,
    "last_tick": 4521,
    "player_id": 42,
    "full_snapshot": true,
    "changed_entities": [/* 当前对玩家可见的完整实体集 */],
    "removed_entities": [1001, 1002],
    "state_checksum": 123456789
  }
}
```

Delta 仅包含对 subscriber 可见的实体——经 `is_visible_to(subscriber, tick)` 过滤（specs/security/05 §3.3）。

### 3.3 客户端同步

```
客户端维护 last_tick 字段。

检测 gap:
  if received_tick > last_tick + 1:
      reconnect and request a current snapshot through MCP
      optionally use swarm_get_replay for an authorized historical range
```

### 3.4 重连

```
断连 → 客户端重连（exponential backoff: 1s, 2s, 4s, max 30s）
重连成功:
  Gateway 发送当前 tick 号
  客户端计算 gap → fetch 丢失的 delta
  → 追上当前 tick 后恢复正常推送
```

### 3.5 心跳

```
Gateway → Client:  ping 每 30s
Client → Gateway:  pong
超时 60s 无 pong → Gateway 关闭连接
```

## 4. REST API

| 端点 | 方法 | 用途 | 可见性过滤 |
|------|------|------|-----------|
| `/healthz` | GET | Gateway 健康检查 | 无 |
| `/sdk/:lang` | GET | 获取 SDK starter package | 与 Gateway 请求认证一致 |

游戏查询和历史数据通过 `POST /mcp` 提供；Gateway 当前不暴露独立的 room、map、tick 或 player-status REST 路由。

`/healthz` 返回 Gateway NATS relay readiness。NATS relay 成功连接并订阅 `NATS_SUBJECT` 后返回 HTTP 200 和 `{"status":"ok","nats":"ready"}`；未就绪时返回 HTTP 503 和 `{"status":"degraded","nats":"unavailable"}`。Gateway HTTP server 保持运行并按 `NATS_RETRY_DELAY_MS`（默认 2000ms）重试。

## 5. MCP 协议

MCP transport 遵循标准 MCP 协议（JSON-RPC over HTTP）。Gateway 作为 MCP 反向代理；SSE 仅为 Gateway ↔ Engine 的内部事件通道，非 Agent-facing MCP subscription：

```
Agent → Gateway (MCP) → Engine (MCP tools)

Gateway 职责:
  - 应用层证书 + canonical request 签名验证（MCP/Agent 主认证路径）
  - 限流（50 MCP 请求/tick per player）
  - 请求路由到 Engine 的 MCP 端点
  - 内部 SSE 事件通道（deploy_accepted, first_tick_executed），供 `swarm_get_events`/deploy status polling 消费
```

Gateway 转发到 Engine 的 `POST /mcp` 必须使用内部 HMAC-SHA256 请求签名。Canonical payload 为 `METHOD\nPATH\nTIMESTAMP\nNONCE\nPLAYER_ID\nTICK\nSHA256(body)`，对应 headers 为 `X-Swarm-Proxy-Timestamp`、`X-Swarm-Proxy-Nonce`、`X-Swarm-Proxy-Signature`、`X-Swarm-Proxy-Body-Sha256`、`X-Swarm-Player-Id` 和可选 `X-Swarm-Tick`。双方必须拒绝空 secret、过期 timestamp、重复 nonce 和无效签名。

MCP 工具清单见 `specs/reference/mcp-tools.md`。

## 6. NATS 主题结构

| 主题 | 方向 | 内容 |
|------|------|------|
| `swarm.realtime.v1`（可由 `NATS_SUBJECT` 覆盖） | Engine → Gateway | `swarm.realtime.v1` targeted tick delta |
| `event.<world_id>.<event_type>` | Engine → Gateway | 全局事件（ResourceSurge, SwarmInvasion 等） |
| `deploy.<world_id>.<player_id>` | Engine → Gateway | 部署结果通知 |
| `admin.<world_id>` | Gateway → Engine | 管理命令 |

### 6.1 NATS 安全

NATS 安全边界使用 TLS + per-role ACL。Gateway、Engine、Sandbox worker 使用不同 NATS credential，按角色限制 publish/subscribe topic：

| Role | Publish | Subscribe |
|------|---------|-----------|
| Engine | `tick.*`, `event.*`, `deploy.*`, sandbox request subjects | gateway request subjects, sandbox replies |
| Gateway | `admin.*`, query/request subjects | `tick.*`, `event.*`, `deploy.*` |
| Sandbox worker | sandbox replies | sandbox request queue group |

Sandbox deploy/tick subjects 除 TLS/ACL 外还必须使用 `SWARM_NATS_AUTH_SECRET` HMAC 信封。Gateway realtime 只转发包含非空目标 player/session 的消息，不允许无目标广播。Gateway 应用层认证 nonce store 使用 `SWARM_GATEWAY_NONCE_PATH`（默认 `/tmp/swarm-gateway-nonces.db`）持久化 replay 状态；生产部署必须将该路径放在可写持久卷上，读取、解析或原子写入失败时认证 fail closed。规则模组是进程内 Bevy Plugin；安全深度还包括 Gateway 应用层认证、mod 源码审查与可审计 hook/schedule graph。

## 7. 降级模式

| 场景 | Gateway 行为 | 客户端影响 |
|------|-------------|-----------|
| NATS 不可达 | HTTP server 保持运行；NATS relay 按 `NATS_RETRY_DELAY_MS` 重试；`/healthz` 返回 503 degraded JSON；delta 推送暂停 | 客户端检测 gap → REST fetch |
| Engine 不可达 | Proxied Engine 请求返回 `502`；NATS relay readiness 由 `/healthz` 单独报告 | 客户端重连等待 |
| Engine Moka Cache miss | 不影响 Gateway——Gateway 不直接访问缓存 | 请求由 Engine 回退到 redb |
| Gateway 进程重启 | WebSocket 断开；客户端重连 | gap fetch 恢复 |

## 8. 安全

| 措施 | 说明 |
|------|------|
| Certificate identity 绑定 | 请求签名必须绑定 `cert_id`、`player_id`、transport 与当前请求 canonical payload |
| DNS rebinding 防护 | Gateway bind 到 `127.0.0.1` 或 unix socket，不监听 `0.0.0.0` |
| CORS | 仅允许配置的 origin（Web UI domain） |
| Rate limiting | 按 player + transport 独立限流（见 specs/security/03 §5） |
| WSS | 生产环境强制 wss://，禁止 ws:// |

## 9. Transport Auth Matrix（唯一权威表）

以下为所有 transport 的认证要求——`specs/security/03` 和 `specs/security/09` 均引用此表。

| Transport | Auth material | Header | Origin/CSRF | 失败码 |
|-----------|---------------|--------|-------------|--------|
| Browser WS | Web session token 或 application certificate | URL query `room`、`sessionId`、`certId`、`expires`、`signature` + `X-Swarm-Transport: ws` | Origin check（Web UI domain） | 401 / 403 |
| REST | Web session token 或 application certificate | Bearer token 或 `Swarm-Certificate` + `Swarm-Cert-Id` + `X-Swarm-Transport: rest` | CORS allowed origins | 401 / 403 |
| MCP Agent | Application certificate + signed request | `Swarm-Certificate` + `Swarm-Cert-Id` + `Swarm-Signature` + `X-Swarm-Transport: mcp` | N/A（非浏览器） | 401 / 403 |
| Replay Viewer | 无或 application certificate | `X-Swarm-Transport: replay` | 公开回放可匿名 | 401 |
| Admin | ClientAuthCertificate with `admin` scope + signed request | `Swarm-Certificate` + `Swarm-Cert-Id` + `Swarm-Signature` + `X-Swarm-Transport: rest` | N/A | 401 / 403 |

**禁止项**：
- Browser WS certificate ticket 使用 `certId` query 字段；Gateway 从已验证证书缓存或 `SWARM_WS_CERT_PUBLIC_KEYS` 解析公钥，不接受 `playerId` 作为证书 ID。
- MCP application certificate **不得**用于 Browser/REST transport（transport 不匹配）。
- Swarm CA **不得**安装到系统/浏览器 trust store；它只用于应用层证书链验证。
- Admin 端点必须使用带 `admin` scope 的 `ClientAuthCertificate` + signed request；不以传输层 mTLS 作为默认身份根。
