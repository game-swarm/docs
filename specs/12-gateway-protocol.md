# Gateway 协议

> 详见 design/interface.md。本文档汇聚 specs/core/01 §4、specs/security/03 §2、specs/security/05 §3、specs/security/09 §7.0 中关于 Gateway 的分散定义。

## 1. 架构定位

Gateway 是引擎与外部世界的唯一入口——所有客户端（Browser、CLI、MCP Agent）通过 Gateway 连接 Swarm 世界。

```
                    ┌──────────────┐
  Browser ──WS─────→│              │
  CLI     ──REST───→│   Gateway    │──NATS──→ Engine
  Agent   ──MCP────→│  (Go, 无状态) │←─REST──→ Engine (health/metrics)
                    └──────────────┘
```

Gateway 是无状态服务，可水平扩展。所有 Gateway 实例共享同一 NATS 集群，无实例间通信。

## 2. Transport 拆分

| Transport | 协议 | 端口 | 用途 | 认证方式 |
|-----------|------|------|------|---------|
| **Browser** | WebSocket | 8082 | 人类玩家 Web UI | Web session token 或 `Swarm-Certificate-Chain` + signed request |
| **REST** | HTTP/1.1 | 8082 | CLI / 外部工具 | Application certificate + signed request；Web session token 仅兼容路径 |
| **Agent** | MCP (HTTP/SSE) | 8082 | AI agent MCP 连接 | Application certificate + signed request |
| **Replay Viewer** | HTTP/1.1 | 8082 | 回放查看器（公开） | Application certificate 或匿名（public replay） |

**判定规则**（specs/security/09 §7.0）：
- 缺少 `X-Swarm-Transport` header → 拒绝 (`401 MissingTransportHeader`)
- 应用层证书 `audience` 不匹配请求 transport → 拒绝 (`403 AudienceMismatch`)
- MCP application certificate 不得用于 WebSocket（Agent ↔ Browser 不可互换）

## 3. WebSocket 协议

### 3.1 连接

```
Client → Gateway:  wss://<host>/ws
  Upgrade request includes `Sec-WebSocket-Protocol: swarm-jwt.<token>` header
Gateway → Client:  {"type": "connected", "player_id": 42, "world_id": "world_v1", "tick": 4521}
```

### 3.2 Delta 推送

每 tick 结束后，Gateway 通过 NATS 接收 delta 并推送到 WebSocket：

```
NATS topic: tick.<world_id>.<tick_number>

Delta 格式:
{
  "type": "tick_delta",
  "tick": 4522,
  "entities": {
    "created": [/* 新实体 */],
    "updated": [/* 变更实体 */],
    "removed": [1001, 1002]  // entity_id 列表
  },
  "resources": { "energy": 4800 },   // 仅自身
  "events": [/* 世界事件 */],
  "state_checksum": "blake3:abc123..."
}
```

Delta 仅包含对 subscriber 可见的实体——经 `is_visible_to(subscriber, tick)` 过滤（specs/security/05 §3.3）。

### 3.3 客户端同步

```
客户端维护 last_tick 字段。

检测 gap:
  if received_tick > last_tick + 1:
      fetch_missing_ticks(last_tick + 1, received_tick - 1)

fetch 回退路径:
  GET /specs/reference/v1/world/ticks?from=<N>&to=<M>
  → 返回该范围的 delta 数组
  → 若 NATS 不可用，客户端通过此路径主动拉取
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
| `/specs/reference/v1/world/rooms/:id` | GET | 房间实体列表 | `is_visible_to(requester, tick)` |
| `/specs/reference/v1/world/rooms/:id/map` | GET | 仅地形（公开） | 无 |
| `/specs/reference/v1/world/ticks` | GET | delta 批量 fetch | `is_visible_to(requester, tick)` |
| `/specs/reference/v1/player/status` | GET | 自身资源/排名 | 仅自身 |
| `/healthz` | GET | Gateway 健康检查 | 无 |
| `/metrics` | GET | Prometheus 指标 | 无 |

## 5. MCP 协议

MCP transport 遵循标准 MCP 协议（JSON-RPC over HTTP/SSE）。Gateway 作为 MCP 反向代理：

```
Agent → Gateway (MCP) → Engine (MCP tools)

Gateway 职责:
  - JWT 认证（mcp audience）
  - 限流（50 MCP 请求/tick per player）
  - 请求路由到 Engine 的 MCP 端点
  - SSE 事件推送（deploy_accepted, first_tick_executed）
```

MCP 工具清单见 `specs/reference/mcp-tools.md`。

## 6. NATS 主题结构

| 主题 | 方向 | 内容 |
|------|------|------|
| `tick.<world_id>.<tick>` | Engine → Gateway | tick delta |
| `event.<world_id>.<event_type>` | Engine → Gateway | 全局事件（ResourceSurge, SwarmInvasion 等） |
| `deploy.<world_id>.<player_id>` | Engine → Gateway | 部署结果通知 |
| `admin.<world_id>` | Gateway → Engine | 管理命令 |

## 7. 降级模式

| 场景 | Gateway 行为 | 客户端影响 |
|------|-------------|-----------|
| NATS 不可达 | `/healthz` 返回 `503`；delta 推送暂停 | 客户端检测 gap → REST fetch |
| Engine 不可达 | `/healthz` 返回 `503`；所有请求返回 `502` | 客户端重连等待 |
| Dragonfly 不可达 | 不影响 Gateway——Gateway 不直接访问缓存 | 无 |
| Gateway 进程重启 | WebSocket 断开；客户端重连 | gap fetch 恢复 |

## 8. 安全

| 措施 | 说明 |
|------|------|
| JWT audience 绑定 | token 的 `aud` 必须匹配请求 transport |
| DNS rebinding 防护 | Gateway bind 到 `127.0.0.1` 或 unix socket，不监听 `0.0.0.0` |
| CORS | 仅允许配置的 origin（Web UI domain） |
| Rate limiting | 按 player + transport 独立限流（见 specs/security/03 §5） |
| WSS | 生产环境强制 wss://，禁止 ws:// |

## 9. Transport Auth Matrix（唯一权威表）

以下为所有 transport 的认证要求——`specs/security/03` 和 `specs/security/09` 均引用此表。

| Transport | Auth material | Header | Origin/CSRF | 失败码 |
|-----------|---------------|--------|-------------|--------|
| Browser WS | Web session token 或 application certificate | `Sec-WebSocket-Protocol: swarm-jwt.<token>` 或 `Swarm-Certificate-Chain` + `X-Swarm-Transport: ws` | Origin check（Web UI domain） | 401 / 403 |
| REST | Web session token 或 application certificate | Bearer token 或 `Swarm-Certificate-Chain` + `X-Swarm-Transport: rest` | CORS allowed origins | 401 / 403 |
| MCP Agent | Application certificate + signed request | `Swarm-Certificate-Chain` + `Swarm-Signature` + `X-Swarm-Transport: mcp` | N/A（非浏览器） | 401 / 403 |
| Replay Viewer | 无或 application certificate | `X-Swarm-Transport: replay` | 公开回放可匿名 | 401 |
| Admin | AdminCertificate + signed request | `Swarm-Certificate-Chain` + `Swarm-Signature` + `X-Swarm-Transport: rest` | N/A | 401 / 403 |

**禁止项**：
- Browser WS token 通过 `Sec-WebSocket-Protocol` header 传递——**不得**出现在 URL query string 中（nginx access log 会记录）
- MCP token **不得**用于 Browser/REST transport（audience 不匹配）。
- Swarm CA **不得**安装到系统/浏览器 trust store；它只用于应用层证书链验证。
- Admin 端点必须使用 `AdminCertificate` + signed request；不以传输层 mTLS 作为默认身份根。
