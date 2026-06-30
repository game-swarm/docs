# Swarm 用户认证

> 统一的用户认证系统：Server CA 签发证书、用户 CSR、用途隔离证书、email 可选恢复、联邦跨世界身份。
> **AI agent 可通过 MCP 自注册，人类玩家可通过 agent 代理注册；长期身份根是用户私钥，服务器授权根是 Server CA。**

**设计原则：设计即终态。认证协议当下裁定最佳实践，不允许 defer。**

## 1. 动机

Swarm 需要脱离第三方身份提供商，支持自托管、内网、离线和 AI agent 自动接入。这要求认证系统不依赖 OAuth2 provider，而以 Server CA 与用户持有私钥为核心。

- 不愿绑定第三方账号的玩家（隐私）
- 没有 GitHub/Google 账号的玩家（低门槛体验）
- 内网/离线部署场景（无外部 OAuth2 provider 可用）
- 自动化测试与 CI 环境（无需配置 OAuth2 密钥）
- **AI player 自注册** — AI agent 没有浏览器，无法完成 OAuth2 重定向流程
- **Agent 代理注册** — 人类通过 AI agent 代为注册，无需手动操作前端

**目标**：提供以应用层证书为主的认证路径。用户/agent 长期持有私钥并提交 CSR，Server CA 签发短期 `ClientAuthCertificate` 与 `CodeSigningCertificate`。email 恢复作为可选 bootstrap 路径。

---

## 2. 设计原则

| 原则 | 说明 |
|------|------|
| **Auth 独立控制面** | 注册、CSR、证书签发、PoW 属于独立 Auth domain。Engine 只消费已签发身份/证书，不持有密码库 |
| **应用层证书强制路径** | Swarm 身份证书只在 HTTP/MCP/WebSocket payload/header 中携带并验证；认证不依赖 TLS client certificate |
| **服务器 CA 授权根** | 每个服务器部署者持有单层 Server CA，为用户 CSR 签发短期用途隔离证书 |
| **用户私钥持有** | 默认由客户端本地生成私钥并提交 CSR；服务端永不接收或保存私钥 |
| **单层 CA** | 不分 Root/Intermediate 层级——单服务器部署双层无安全收益。Server CA 密钥对直接签发证书 |
| **用途隔离** | `ClientAuthCertificate`（认证请求）和 `CodeSigningCertificate`（签名 WASM 部署）是仅有的两种证书类型 |
| **确定性 player_id** | `player_id = blake3(\"local:\" + login_username_lowercase)`；联邦身份使用独立 namespace 的 deterministic hash |
| **PoW 防滥用** | 注册需要完成工作量证明（PoW challenge），配合 rate limit 两层准入 |

---

## 3. Auth 控制面架构

Auth 是独立控制面，不属于游戏模拟的一部分：

```
┌──────────────────────────────────────────────────────────┐
│  客户端层                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐   │
│  │ 浏览器前端     │  │ AI Agent      │  │ Agent 代理     │   │
│  │ (LoginButton) │  │ (Hermes MCP)  │  │ (MCP proxy)   │   │
│  └──────┬───────┘  └──────┬───────┘  └───────┬───────┘   │
│         │                 │                   │           │
│         ▼                 ▼                   ▼           │
│  ┌──────────────────────────────────────────────────────┐ │
│  │              Gateway (Rust)                            │ │
│  │  Certificate Auth handler                             │ │
│  │  /auth/register/challenge                             │ │
│  │  /auth/csr/submit                                     │ │
│  │  /auth/cert/renew                                     │ │
│  └────────────────────┬─────────────────────────────────┘ │
│                       │                                    │
│  ┌────────────────────▼─────────────────────────────────┐ │
│  │              Auth Service / Domain                     │ │
│  │  src/auth/                                             │ │
│  │  ┌──────────────────┐  ┌──────────────────────────┐  │ │
│  │  │ CSR Registration │  │ Certificate Sessions      │  │ │
│  │  │ - challenge 生成  │  │ - ClientAuth/CodeSign 签发│  │ │
│  │  │ - PoW 验证       │  │ - request signature 校验 │  │ │
│  │  │ - CSR 审核       │  │ - cert revocation        │  │ │
│  │  │ - email 恢复(可选)│  │                          │  │ │
│  │  └──────────────────┘  └──────────────────────────┘  │ │
│  └──────────────────────────┬───────────────────────────┘ │
│                             │                              │
│  ┌──────────────────────────▼───────────────────────────┐ │
│  │              Engine (Game Core)                         │ │
│  │  CertificateVerifier — 只消费证书链                     │ │
│  │  不持有密码库、不执行注册                                │ │
│  └──────────────────────────────────────────────────────┘ │
│                             │                              │
│  ┌──────────────────────────▼───────────────────────────┐ │
│  │              redb                                       │ │
│  │  auth/users/       — 用户元数据                         │ │
│  │  auth/public_keys/ — PlayerId → public keys             │ │
│  │  auth/certificates/— 证书记录                           │ │
│  │  auth/identities/  — IdentityKey → PlayerId 映射       │ │
│  │  auth/challenges/  — PoW challenge 存储                 │ │
│  │  auth/sessions/    — Web session 兼容层                 │ │
│  │  auth/revocations/ — 吊销列表                           │ │
│  └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**职责分离**：

| 组件 | 持有 | 不持有 |
|------|------|--------|
| Auth Service | public keys, challenge, email recovery(可选), certificate audit | 用户私钥、Server CA 私钥 |
| Engine | trusted root fingerprints, certificate verifier, revoked certificate cache | 用户私钥, 密码库, PoW challenge state, CA 私钥 |
| Gateway | 无状态代理, 路由, canonical request 验签入口 | 认证状态, 用户私钥 |

---

## 4. 应用层证书与 CSR

### 4.1 Trust Root 与证书链

Swarm 认证使用单层应用层证书链。每个服务器部署者维护一个 Server CA：

```
Server CA (operator-held)
  ├─ ClientAuthCertificate(player_id, public_key, scopes, world_id, ttl)
  └─ CodeSigningCertificate(player_id, public_key, module_scope, ttl)
```

不分 Root/Intermediate 层级——双层签名链在单服务器部署中没有安全收益。攻击者能拿到 Intermediate CA 私钥就能拿到 Root CA 私钥（在同一台机器上）。

Server CA 只用于 Swarm 应用层证书，不得要求用户安装到系统或浏览器 trust store。常规 HTTPS 使用 WebPKI；若部署需要 mTLS，必须使用与 Swarm CA 隔离的传输层 CA。

### 4.2 用途隔离证书

证书按用途隔离，避免认证凭据被直接拿去签代码：

| Certificate | 用途 | TTL | 约束 |
|-------------|------|-----|------|
| `ClientAuthCertificate` | MCP 查询、session renew、普通认证请求 | 24h | 只能用于 `SWARM-REQUEST-V1` |
| `CodeSigningCertificate` | WASM/module deploy 签名 | 30–180 days（默认 30d，world.toml 可配） | 只能签 `SWARM-DEPLOY-V1` 载荷 |

Admin 操作 = `ClientAuthCertificate` + admin scope flag（不需要独立证书类型）。Federation 是身份映射协议，不需要独立证书类型。

### 4.3 准入流程

CSR 验证分两层：

| 层级 | 准入检查 | 说明 |
|------|---------|------|
| **L1: PoW** | `challenge_id` 存在、未过期、未消费，且 PoW 成立 | anti-spam——消耗客户端 CPU，防止零成本注册洪泛 |
| **L2: rate limit** | 同 IP 快速注册限制 | 防止单 IP 轮换账号 |

PoW challenge TTL 5min，一次性消费。难度自适应调整（`difficulty_bits_min = 20`，`difficulty_bits_max = 32`）。

通过准入后进入 CSR payload 验证——签名校验、username 唯一性、requested usages 在允许范围内。

### 4.4 代码签名证书过期语义

- 新部署时 `CodeSigningCertificate` 必须未过期、未吊销
- 证书过期后，用新证书重新签署同一个 `wasm_module_hash + metadata_hash` 即可重新部署
- 证书吊销是安全事件——服务端可按 revocation reason 冻结、回滚或继续允许既有模块运行

---

## 5. 使用场景

### 5.1 人类玩家 — 前端注册

```
人类 → 浏览器 → LoginButton.tsx
  → 浏览器生成 Ed25519 keypair
  → 前端自动请求 PoW challenge → Web Worker 求解 nonce
  → POST /auth/csr/submit → {username, csr, challenge_id, nonce, csr_signature}
  → 获得 ClientAuthCertificate + CodeSigningCertificate
```

### 5.2 AI player / CLI — CSR 自注册

```
AI agent → MCP session
  → 选择或生成 Ed25519 私钥
  → swarm_register_challenge() 获取 challenge
  → 本地求解 PoW
  → swarm_submit_csr(username, csr, challenge_id, nonce, csr_signature)
  → 获得 ClientAuthCertificate + CodeSigningCertificate
```

### 5.3 人类 — Agent 代理注册

```
人类 → "帮我在 Swarm 注册一个账号，用户名 kagurazaka"
  → AI agent 生成 Ed25519 私钥，构造 CSR，完成注册
  → 返回一次性 handoff code / 导入链接给人类
```

---

## 6. 恢复凭据（可选模块）

email 恢复为可选模块——服主可在 world.toml 中启用。

密码恢复哈希使用 argon2id（`argon2` crate），参数：19 MiB memory、2 iterations、1 parallelism。

---

## 7. Canonical Request Signature

```
Swarm-Certificate: <base64 ClientAuthCertificate or CodeSigningCertificate>
Swarm-Cert-Id: <certificate_id>
Swarm-Timestamp: <unix_ms>
Swarm-Nonce: <random 128-bit>
Swarm-Signature: <ed25519 signature by user private key>
```

签名 payload：

```
SWARM-REQUEST-V1
method: <http method or mcp method>
path: <http path or mcp tool name>
body_hash: <blake3 canonical body hash>
timestamp: <unix_ms>
nonce: <nonce>
certificate_id: <certificate_id>
player_id: <player_id>
audience: "swarm-aud-v1:<transport>:<server_id>:<world_id>:<player_id>"
```

---

## 8. 传输安全

默认要求 TLS。不安全传输（HTTP）为可选配置——服主显式开启并接受风险。Server identity 由 Server CA fingerprint pinning 保证（TOFU），不由外部 TLS 证书保证。

---

## 9. 与旧版设计的差异

| 旧设计 | 当前设计 |
|--------|---------|
| Server Root CA + Intermediate CA 双层 | 单层 Server CA |
| 4 种证书（ClientAuth + CodeSigning + Admin + Federation） | 2 种（ClientAuth + CodeSigning） |
| 6 层 CSR 准入链 | 2 层（PoW + rate limit） |
| passkey/email/admin 三种强制恢复 | email 可选恢复 |
| 不安全传输为核心需求 | TLS 默认要求，不安全为可选配置 |
