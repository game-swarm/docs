# Swarm 用户认证

> 统一的用户认证系统：Server CA 签发应用层证书，客户端持有私钥并签名实际请求传输，Auth 控制面以显式 REST action routes 暴露生命周期。

**设计原则：设计文档拥有 API 语义、边界和安全语义；下游 IDL 只拥有 wire schema 表达。认证协议当下裁定终态。**

## 1. 动机

Swarm 需要脱离第三方身份提供商，支持自托管、内网、离线和 AI agent 自动接入。这要求认证系统不依赖 OAuth2 provider，而以 Server CA 与用户持有私钥为核心。

- 不愿绑定第三方账号的玩家（隐私）
- 没有 GitHub/Google 账号的玩家（低门槛体验）
- 内网/离线部署场景（无外部 OAuth2 provider 可用）
- 自动化测试与 CI 环境（无需配置 OAuth2 密钥）
- AI player 自注册：agent 可直接调用 REST 注册和 CSR routes
- Agent 代理注册：人类可让 agent 生成本地密钥并交付加密私钥 bundle

目标：提供以应用层证书为主的认证路径。用户、浏览器和 agent 长期持有 Ed25519 私钥并提交 CSR，Server CA 签发短期 `ClientAuthCertificate` 与 `CodeSigningCertificate`。email 恢复只是可选 bootstrap 模块，不改变证书签名主路径。

---

## 2. 设计原则

| 原则 | 说明 |
|------|------|
| Auth 独立控制面 | 注册、CSR、证书签发、PoW 属于独立 Auth domain。Engine 只消费已签发身份/证书，不持有密码库 |
| 应用层证书强制路径 | 所有客户端，包括 Browser，都使用应用层证书签名；认证不依赖 TLS client certificate |
| 显式 REST 生命周期 | Auth 生命周期只通过 `/auth/*` REST action routes 暴露，不提供 Auth MCP 工具或别名 |
| Server CA 授权根 | 每个服务器部署者持有单层 Server CA，为用户 CSR 签发短期用途隔离证书 |
| 用户私钥持有 | 客户端本地生成私钥并提交 CSR；服务端永不接收、保存或恢复私钥 |
| 用途与 audience 隔离 | 证书声明用途和 allowed audience；验签时同时检查请求传输属于证书 audience |
| 确定性 player_id | `player_id = blake3("local:" + login_username_lowercase)`；联邦身份使用独立 namespace 的 deterministic hash |
| PoW 防滥用 | 注册需要完成工作量证明 challenge，配合 rate limit 两层准入 |

---

## 3. Auth 控制面架构

Auth 是独立控制面，不属于游戏模拟的一部分：

```text
Client (Browser / CLI / AI Agent)
  -> signed REST request
  -> Gateway certificate auth handler
  -> Auth Service / Domain
  -> redb auth tables

Engine
  -> CertificateVerifier
  -> trusted Server CA fingerprints + revoked certificate cache
```

**职责分离**：

| 组件 | 持有 | 不持有 |
|------|------|--------|
| Auth Service | public keys, challenges, canonical request nonce replay store, email recovery metadata, certificate audit, revocation records | 用户私钥、Server CA 私钥 |
| Engine | trusted root fingerprints, certificate verifier, revoked certificate cache | 用户私钥, 密码库, PoW challenge state, CA 私钥 |
| Gateway | 无状态路由, canonical request 验签入口, transport binding 检查；调用 Auth Service 原子 nonce 校验 | 认证状态, nonce replay state, 用户私钥 |

Auth 生命周期 canonical surface：

| Route | Rate limit | 语义 |
|-------|------------|------|
| `POST /auth/register/challenge` | 10/min per IP | 创建一次性 PoW challenge |
| `POST /auth/csr/submit` | 1/30s per IP | 提交 CSR、PoW nonce 和 CSR 签名；成功后签发证书 |
| `POST /auth/cert/renew` | 5/min per player | 使用仍有效的应用层证书续签同用途证书 |
| `POST /auth/cert/revoke` | 5/min per player | 吊销指定证书并写入 audit trail |
| `GET /auth/cert/list` | 30/min per player | 列出当前 player 可见证书 |
| `POST /auth/cert/check` | 100/min per player | 检查证书链、吊销状态、audience 和用途 |
| `GET /auth/server/trust` | 60/min global | 返回 Server CA fingerprint、算法和 operator label |

这些 routes 是 Auth 生命周期的唯一 API 语义入口。MCP 不包含 Auth 工具、兼容别名或代理包装。

---

## 4. 应用层证书与 CSR

### 4.1 Trust Root 与证书链

Swarm 认证使用单层应用层证书链。每个服务器部署者维护一个 Server CA：

```text
Server CA (operator-held)
  +- ClientAuthCertificate(player_id, public_key, scopes, allowed_audience, ttl)
  +- CodeSigningCertificate(player_id, public_key, module_scope, allowed_audience, ttl)
```

不分 Root-CA/issuing-CA 层级。Server CA 只用于 Swarm 应用层证书，不得要求用户安装到系统或浏览器 trust store。常规 HTTPS 使用 WebPKI；若部署需要 mTLS，必须使用与 Swarm CA 隔离的传输层 CA。

### 4.2 用途隔离证书

证书按用途隔离，避免认证凭据被直接拿去签代码：

| Certificate | 用途 | TTL | 约束 |
|-------------|------|-----|------|
| `ClientAuthCertificate` | REST 认证请求、证书续签、普通控制面请求 | 24h | 只能用于 `SWARM-REQUEST-V1`，且请求 transport 必须属于 allowed audience |
| `CodeSigningCertificate` | WASM/module deploy 签名 | 30-180d（默认 30d，world.toml 可配） | 只能签 `SWARM-DEPLOY-V1` 载荷，且 deploy transport 必须属于 allowed audience |

Admin 操作 = `ClientAuthCertificate` + admin scope flag。Identity mapping 是身份映射协议，不需要独立证书类型。

### 4.3 准入流程

CSR 验证分两层：

| 层级 | 准入检查 | 说明 |
|------|---------|------|
| L1: PoW | `challenge_id` 存在、未过期、未消费，且 PoW 成立 | anti-spam：消耗客户端 CPU，防止零成本注册洪泛 |
| L2: rate limit | 同 IP 快速注册限制 | 防止单 IP 轮换账号 |

PoW challenge TTL 5min，一次性消费。默认 `difficulty_bits = 24`，难度自适应调整范围为 `difficulty_bits_min = 20`、`difficulty_bits_max = 32`。通过准入后进入 CSR payload 验证：签名校验、username 唯一性、requested usages 与 allowed audience 在允许范围内。

### 4.4 代码签名证书过期语义

- 新部署时 `CodeSigningCertificate` 必须未过期、未吊销
- 证书过期后，用新证书重新签署同一个 `wasm_hash + metadata_hash` 即可重新部署
- 证书吊销是安全事件，服务端可按 revocation reason 冻结、回滚或继续允许既有模块运行

---

## 5. 使用场景

### 5.1 人类玩家：浏览器注册

```text
人类 -> Browser
  -> 浏览器生成 Ed25519 keypair
  -> GET /auth/server/trust 并要求用户确认 Server CA fingerprint
  -> POST /auth/register/challenge
  -> Web Worker 求解 PoW nonce
  -> POST /auth/csr/submit { username, csr, requested_usages, requested_audience, challenge_id, nonce, csr_signature }
  -> 获得 ClientAuthCertificate + CodeSigningCertificate
```

Browser 与 CLI、AI Agent 使用同一套应用层证书签名语义。不存在 Web session、CSRF、Origin/Host/Fetch metadata 的认证分支。

浏览器私钥导出规则：Browser 导出用户私有 Ed25519 key 时，必须先要求用户输入导出密码；使用 Argon2id 从密码派生 KEK，再用 AES-256-GCM 加密私钥，生成 ciphertext bundle。用户手动导出/导入该 bundle；服务端永不保存 bundle、KEK、密码或私钥。

### 5.2 AI player / CLI：CSR 自注册

```text
AI agent / CLI
  -> 选择或生成 Ed25519 私钥
  -> GET /auth/server/trust 并确认 Server CA fingerprint
  -> POST /auth/register/challenge
  -> 本地求解 PoW
  -> POST /auth/csr/submit { username, csr, requested_usages, requested_audience, challenge_id, nonce, csr_signature }
  -> 获得 ClientAuthCertificate + CodeSigningCertificate
```

首次确认后的 Server CA fingerprint 必须持久化。再次连接时若 fingerprint 变化，客户端 fail closed，要求用户显式确认新的 fingerprint 后才可继续 CSR 或续签流程。

### 5.3 人类：Agent 代理注册

```text
人类 -> "帮我在 Swarm 注册一个账号，用户名 kagurazaka"
  -> AI agent 生成 Ed25519 私钥，确认 Server CA fingerprint，构造 CSR，完成注册
  -> 返回 AES-256-GCM ciphertext bundle 给人类手动导入
```

---

## 6. 恢复凭据（可选模块）

email 恢复为可选模块，服主可在 world.toml 中启用。它只能帮助重新建立 bootstrap 准入，不能恢复或替代用户私钥。密码恢复哈希使用 Argon2id，参数：19 MiB memory、2 iterations、1 parallelism。

---

## 7. Canonical Request Signature

```text
Swarm-Certificate: <base64 ClientAuthCertificate or CodeSigningCertificate>
Swarm-Cert-Id: <certificate_id>
X-Swarm-Transport: <mcp|rest|ws|replay>
Swarm-Timestamp: <unix_ms>
Swarm-Nonce: <random 128-bit>
Swarm-Signature: <ed25519 signature by user private key>
```

签名 payload（UTF-8，LF 分隔）绑定实际 transport：

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

`stable_json` 递归按对象 key 排序，数组保持顺序；客户端对该稳定 JSON 字节串计算 BLAKE3，并将十六进制 hash 放入 canonical payload。Verifier 必须检查签名中的 `TRANSPORT` 与 `X-Swarm-Transport` 及服务器实际接收的入口一致，并确认该 transport 属于证书 allowed audience；`SCHEME + AUTHORITY + PATH_AND_QUERY` 必须与实际请求完全一致。`TIMESTAMP` 的 freshness window 固定为 60 秒；`NONCE` 在 `(cert_id, transport)` 作用域内必须原子写入 replay store 并拒绝重复值。Timestamp/nonce 解析、replay store 读取或原子写入失败全部 fail closed。

语义错误：

| Error | HTTP | 语义 |
|-------|------|------|
| `InvalidTransportBinding` | 401 | 签名 payload 中的 transport 与实际请求 transport 不一致，或缺少必需 transport 字段 |
| `AudienceMismatch` | 403 | 签名有效，但证书 allowed audience 不覆盖该 transport |
| `RequestExpired` | 401 | 请求 timestamp 超出 60 秒 freshness window，或 timestamp 无法解析 |
| `ReplayDetected` | 409 | `(cert_id, transport, nonce)` 已使用，或 nonce replay store 无法安全读写 |
| `InvalidCertificate` | 401 | 证书链、usage、expiry、revocation 或签名校验失败 |
| `RateLimited` | 429 | Auth operation rate limit exceeded |

---

## 8. 传输安全

默认要求 TLS。不安全传输（HTTP）为可选配置，服主显式开启并接受风险。Server identity 由用户确认的 Server CA fingerprint pinning 保护；fingerprint 变化必须 fail closed。
