# Swarm 用户认证

> 统一的用户认证系统：服务器 CA 签发证书、用户 CSR、用途隔离证书、本地恢复凭据、passkey/email/admin 恢复、联邦跨世界身份。
> **AI agent 可通过 MCP 自注册，人类玩家可通过 agent 代理注册；长期身份根是用户私钥，服务器授权根是部署者 CA。**

## 1. 动机

当前 Swarm 需要脱离第三方身份提供商，支持自托管、内网、离线和 AI agent 自动接入。这要求认证系统不依赖 OAuth2 provider，而以服务器 CA 与用户持有私钥为核心。

- 不愿绑定第三方账号的玩家（隐私）
- 没有 GitHub/Google 账号的玩家（低门槛体验）
- 内网/离线部署场景（无外部 OAuth2 provider 可用）
- 自动化测试与 CI 环境（无需配置 OAuth2 密钥）
- **AI player 自注册** — AI agent 没有浏览器，无法完成 OAuth2 重定向流程
- **Agent 代理注册** — 人类通过 AI agent 代为注册，无需手动操作前端

**目标**：提供以应用层证书为主的认证路径。用户/agent 长期持有私钥并提交 CSR，服务器部署者通过 Server Intermediate CA 签发短期 `ClientAuthCertificate` 与 `CodeSigningCertificate`；passkey、email 和管理员恢复链接作为 bootstrap/recovery 路径并入同一证书模型。Swarm CA 不进入系统/浏览器信任根；HTTP 等不安全传输仍可通过应用层证书完成身份认证与完整性校验。

---

## 2. 设计原则

| 原则 | 说明 |
|------|------|
| **Auth 独立控制面** | 注册、CSR 审核、证书签发、PoW、密码恢复、token 兼容层属于独立 Auth domain。Engine 只消费已签发身份/证书，不持有密码库 |
| **应用层证书强制路径** | Swarm 身份证书只在 HTTP/MCP/WebSocket payload/header 中携带并验证；认证不依赖 TLS client certificate |
| **服务器 CA 授权根** | 每个服务器部署者持有 Server Root CA；在线 Server Intermediate CA 为用户 CSR 签发短期用途隔离证书 |
| **用户私钥持有** | 默认由客户端本地生成私钥并提交 CSR；服务端永不接收或保存私钥。仅当客户端声明非常用设备或无法生成/安全保存私钥时，才允许受限的服务器代管流程 |
| **Bootstrap 并列共存** | 本地恢复密码、passkey、email、管理员重置链接用于首次 CSR 提交或私钥丢失恢复；完成后统一签发应用层证书 |
| **同一证书模型** | `ClientAuthCertificate`、`CodeSigningCertificate`、`AdminCertificate` 共享证书链验证；JWT/refresh token 仅是 Web session 兼容层，不是信任根 |
| **确定性 player_id** | `player_id = blake3("local:" + login_username_lowercase)`；联邦身份使用独立 namespace 的 deterministic hash |
| **PoW 防滥用** | 注册需要完成工作量证明（PoW challenge）。Login/CSR PoW 可配置（开关 + 难度） |
| **传输层 CA 隔离** | 服务器 Swarm CA 不得要求用户安装到系统/浏览器 trust store；传输层 TLS 使用 WebPKI 或独立 mTLS CA，避免服务器 CA 被用于伪装其它站点 |
| **不安全传输可认证** | HTTP 等不安全上下文可通过应用层证书完成身份认证和请求完整性校验；首次访问需人工确认服务器 Root CA fingerprint，写入客户端证书存储后，传输层安全不依赖外部 TLS |

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
│  │              Gateway (Go)                              │ │
│  │  ┌────────────────────────────────────────────────┐   │ │
│  │  │ Certificate Auth handler                       │   │ │
│  │  │ /auth/register/challenge                       │   │ │
│  │  │ /auth/csr/submit                              │   │ │
│  │  │ /auth/cert/renew                              │   │ │
│  │  └────────────────────┬───────────────────────────┘   │ │
│  └────────────────────────────────────┼─────────────────┘ │
│                                       │                    │
│  ┌────────────────────────────────────▼─────────────────┐ │
│  │              Auth Service / Domain                     │ │
│  │  src/auth/ (Engine 内或独立服务)                        │ │
│  │  ┌──────────────────┐  ┌──────────────────────────┐  │ │
│  │  │ CSR Registration │  │ Certificate Sessions      │  │ │
│  │  │ - challenge 生成  │  │ - ClientAuth/Code cert 签发│ │ │
│  │  │ - PoW 验证       │  │ - request signature 校验 │  │ │
│  │  │ - CSR 审核       │  │ - cert revocation        │  │ │
│  │  │ - 密码恢复       │  │ - web token compatibility│  │ │
│  │  └──────────────────┘  └──────────────────────────┘  │ │
│  └──────────────────────────┬───────────────────────────┘ │
│                             │                              │
│  ┌──────────────────────────▼───────────────────────────┐ │
│  │              Engine (Game Core)                         │ │
│  │  ┌────────────────┐                                    │ │
│  │  │ CertificateVerifier│ ← Engine 只消费应用层证书链       │ │
│  │  │ verify_chain    │   不持有密码库或用户私钥             │ │
│  │  │ verify_request  │   不执行注册/CSR 审核逻辑            │ │
│  │  └────────────────┘                                    │ │
│  └──────────────────────────────────────────────────────┘ │
│                             │                              │
│  ┌──────────────────────────▼───────────────────────────┐ │
│  │              FoundationDB                               │ │
│  │  auth/users/       — 用户元数据 (display_name, email, ...)│ │
│  │  auth/public_keys/ — PlayerId → public keys             │ │
│  │  auth/certificates/— 应用层证书记录                     │ │
│  │  auth/identities/  — IdentityKey → PlayerId 映射       │ │
│  │  auth/challenges/  — PoW/login/signature challenge 存储 │ │
│  │  auth/sessions/    — refresh token / Web session 兼容层 │ │
│  │  auth/revocations/ — key/certificate 吊销列表           │ │
│  └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**职责分离**：

| 组件 | 持有 | 不持有 |
|------|------|--------|
| Auth Service | public keys, challenge, password/passkey recovery, refresh token 兼容层, certificate audit | 用户私钥、Server Root CA 私钥 |
| Engine | trusted root fingerprints, certificate verifier, revoked certificate cache | 用户私钥, 密码, PoW challenge state, CA 私钥 |
| Gateway | 无状态代理, 路由, canonical request 验签入口 | 认证状态, 用户私钥 |

### 3.1 证书签发接口

Auth Service 不持有 `Server Root CA` 私钥；Root CA 离线保存。在线签发通过 `Server Intermediate CA` 完成，注册/续签返回用途隔离的证书 bundle：

```
issue_certificate_bundle(
    player_id: u64,
    public_key: Ed25519PublicKey,
    usages: ["client_auth", "code_signing", ...],
    scopes: ["swarm:deploy", "swarm:read", ...],
    audience: "swarm-aud-v1:cli-rest:<server_id>:<world_id>:<player_id>",
    ttl_policy: CertificateTtlPolicy,
) → CertificateBundle
```

**接口合同**：
- Auth Service 是独立进程。所有签名和认证操作在独立进程中完成，不与 Engine 共享内存。Engine 内部仅做信任链验证（证书链、CRL 状态），不持有签名私钥
- 调用者必须持有有效的 CSR 验证结果、external bootstrap proof 或恢复流程授权，不允许无证明调用
- 失败恢复：证书签发失败时 Auth 不创建 session，整体事务回滚——不出现「user 存在但无证书」的半状态
- 审计：每次签发写入 FDB `auth/cert_audit/<certificate_id>`，记录 `player_id, public_key_id, usage, issued_at, issuer, scopes, ttl`
- `Server Root CA` 不在线；`Server Intermediate CA` 定期轮换并可被 Root CA 吊销
- Server Intermediate CA 私钥存储要求：
  | 层级 | 方案 | 最低要求 |
  |---|---|---|
  | 生产环境 | HSM (YubiHSM, AWS CloudHSM) 或 KMS (AWS KMS, GCP KMS) | 密钥不可导出；签名操作在 HSM 内完成 |
  | 自托管 / 小型部署 | soft-HSM (SoloKeys, Nitrokey) 或 `pkcs11-tool` | 密钥加密存储；PIN 保护；速率限制 |
  | 开发 / 测试 | 独立文件系统，`0600` 权限 | Engine/Auth 进程以外无读取权限 |

  **Intermediate CA 私钥保护强制要求**：
  - **离线保护**：生产环境 Intermediate CA 私钥必须位于 HSM/KMS 中，密钥材料不可导出——签名操作在硬件安全边界内完成，私钥从不离开 HSM。自托管部署如无法使用 HSM，必须使用 soft-HSM 或加密文件系统，并**显式接受风险**（在 world.toml `[auth.ca] accept_file_based_intermediate_key = true` 中声明）。
  - **短有效期**：Intermediate CA 轮换周期 90 天，私钥备份需加密并离线冷存储。operator runbook 需包含：CA 私钥生成、轮换、吊销、灾难恢复流程。
  - **启动强制检查**：Auth Service 启动时验证 Intermediate CA 私钥访问方式（HSM 可访问性或文件权限 0600），不满足安全要求则**拒绝启动**并输出明确错误信息。
  - **审计合同**：每次 Intermediate CA 私钥使用（签发证书）写入 FDB `auth/ca_audit`，记录 `timestamp, certificate_id, issuer_id`。私钥轮换事件写入 `auth/ca_rotation_log`。
- Swarm CA 只用于应用层证书，不得作为系统/浏览器 TLS trust anchor

---

## 4. 使用场景

### 4.1 人类玩家 — 前端注册

```
人类 → 浏览器 → LoginButton.tsx
  → "Create account / device" 表单 → 输入 username + device_label + 可选 recovery password/email
  → 浏览器生成 WebCrypto/Swarm Ed25519 keypair，或等待 CLI/agent handoff 提供 CSR
  → 前端自动请求 PoW challenge → Web Worker 求解 nonce（进度条显示）
  → POST /auth/csr/submit → {username, csr, challenge_id, nonce, csr_signature}
  → 获得 ClientAuthCertificate + CodeSigningCertificate + Web session 兼容 token → 存入本地安全存储

错误恢复：
  - PoW 求解中断/超时 → 显示进度和取消按钮，自动重新获取 challenge
  - 移动端慢设备 → difficulty 可配置，前端显示预估时间
  - 私钥丢失 → 使用邮箱、passkey 或管理员生成的恢复链接提交新 CSR
  - 注册失败 → 按错误码提示（username_taken, invalid_signature, invalid_pow）
```

### 4.2 AI player / CLI — CSR 自注册

```
AI agent (Claude/GPT/自主 agent) → MCP session
  → 选择现有 Ed25519 私钥（SSH agent / 私钥文件 / SDK key store）或生成专用 Swarm key
  → 调用 swarm_register_challenge() 获取 challenge
  → 本地求解 PoW（blake3 brute-force，按 difficulty bits）
  → 构造 CSR，并用用户私钥签名 CSR payload
  → 调用 swarm_submit_csr(username, csr, challenge_id, nonce, csr_signature)
     username  = "ai-bot-<random>" (自行生成)
     key_label = "hermes-agent-default"
  → 获得 ClientAuthCertificate + CodeSigningCertificate
  → 用 CodeSigningCertificate 对 module_hash + metadata 签名，再调用 swarm_deploy

凭据管理：
  - AI agent 必须持久化 (username, private_key reference, certificate chain, recovery material)
  - 推荐使用 SSH agent、硬件密钥或 0600 权限私钥文件；禁止把私钥写入代码仓库、公开日志或聊天上下文
  - certificate 过期后通过 swarm_renew_certificate 重新签发（证明持有同一私钥）

MCP 资源指引（AI agent onboarding）：
  - `docs/auth/onboarding-ai` — AI agent 首次注册完整流程（含 PoW 求解、CSR 提交、证书持久化、联邦登录）
  - `docs/auth/errors` — 错误码含义与恢复策略
  - `schema/auth-tools` — auth MCP 工具的 JSON Schema（供 agent function calling）
  - `docs/auth/human-agent-handoff` — 人类通过 agent 代理注册的 handoff 协议

错误恢复：
  - PoW 求解超时 → 自动重新获取 challenge + 重试
  - 私钥丢失 → 通过绑定邮箱或管理员重置链接绑定新 key
  - username_taken → 自动重试新 username
```

### 4.3 人类 — Agent 代理注册

```
人类 → "帮我在 Swarm 注册一个账号，用户名 kagurazaka"
  → AI agent 生成或选择 Ed25519 私钥，构造 CSR，调用 swarm_register_challenge() + swarm_submit_csr(...)
  → 返回 handoff 信息给人类（见下方安全条款）

私钥归属（明确合同）：
  - Agent 托管模式：Agent 可长期持有私钥代为操作，需人类显式授权
  - 人类自管模式：Agent 只生成一次性导入包，人类导入后 Agent 删除私钥副本
  - 若用户希望保留密码恢复，Agent 可协助绑定邮箱或设置 recovery password

安全交付（防聊天日志泄露）：
  - Agent 返回给人类的是「一次性 handoff code / 导入链接」，而非裸 refresh_token 或私钥明文
  - 人类在浏览器中输入 handoff code 完成 key 导入或授权 Agent 托管
  - Agent 的聊天日志中不得出现长期有效的 refresh_token、certificate 私钥或 SSH private key
  - 所有后续 deploy/admin 请求必须用绑定 key 对 canonical request 签名
```

### 4.4 可选外部 Bootstrap Provider

OAuth2 / OIDC 不属于核心认证协议。若部署者需要 GitHub、Google 或企业 IdP，可通过插件把第三方身份验证结果转换为一次性 bootstrap proof；客户端仍必须提交 CSR，服务器仍只签发本地应用层证书。核心 MCP 工具、默认 Runbook 和联邦信任模型不依赖 OAuth2。

---

## 5. 应用层证书与 CSR

### 5.1 Trust Root 与证书链

Swarm 认证默认使用应用层证书链，而不是 TLS client certificate。每个服务器部署者维护自己的 Swarm CA：

```
Server Root CA (offline / operator-held)
  └─ Server Intermediate CA (online signer, rotating)
       ├─ ClientAuthCertificate(player_id, public_key, scopes, world_id, ttl)
       ├─ CodeSigningCertificate(player_id, public_key, module_scope, ttl)
       └─ AdminCertificate(admin_id, public_key, scopes, ttl)
```

`Server Root CA` 只用于 Swarm 应用层证书，不得要求用户安装到系统或浏览器 trust store。常规 HTTPS 仍使用 WebPKI；若极少数部署需要 mTLS，必须使用与 Swarm CA 隔离的传输层 CA。

### 5.2 用户私钥与 CSR

客户端默认在本地生成密钥对并提交 CSR。服务端只接收 public key、CSR payload 和签名，永不接收或保存 private key。key 可以来自 SSH agent、Swarm SDK、WebCrypto 或硬件密钥，最终归一为 Ed25519 public key。

服务器代管私钥是例外路径，只能用于以下场景：

- 客户端声明当前设备不是常用设备，只需要一次性/短期访问
- 客户端环境无法生成或安全保存私钥
- 人类明确选择 agent/server 托管模式，并理解服务器可代为签名的风险

代管约束：托管 key 必须标记 `managed_by_server=true`、TTL 更短、scope 更窄、不可签发 `AdminCertificate`，并写入 `auth/admin_audit` / `auth/key_audit`。用户迁移到常用设备后应立即重新提交客户端生成的 CSR 并吊销托管 key。

CSR payload：

```
SWARM-CSR-V1
server_id: <server_id>
world_id: <world_id>
username: <login_username_lowercase>
public_key: <normalized public key>
requested_usages: client_auth, code_signing, admin?
requested_scopes: swarm:read, swarm:deploy
certificate_profile: regular_device | temporary_device | managed_device | admin_device
challenge_id: <challenge_id>
challenge: <server challenge>
expires_at: <challenge_expires_at>
```

服务端验证——**多层准入链**（逐层过滤，任一层拒绝 → 请求丢弃）：

| 层级 | 准入检查 | 说明 |
|------|---------|------|
| **L1: PoW** | `challenge_id` 存在、未过期、未消费，且 PoW 成立 | 基础工作量证明——消耗客户端 CPU，防止零成本注册洪泛 |
| **L2: per-IP 限流** | 同 IP CSR 提交速率 ≤ 1/30s（可配置） | 防止单 IP 快速轮换账号绕过 PoW |
| **L3: per-ASN 限流** | 同 ASN CSR 提交速率 ≤ 10/min（可配置） | 防止分布式 botnet 跨 IP 攻击 |
| **L4: global semaphore** | 全局并发 CSR 验证 ≤ `min(cpu_cores, 4)` | 防止 PoW 验证（blake3 brute-force verify）耗尽 CPU |
| **L5: bounded queue** | 排队 CSR ≤ 100；溢出 → `ERR_CSR_QUEUE_FULL` (HTTP 503) | 防止无界排队导致 OOM |
| **L6: audit throttle** | 同 username 连续失败 ≥ 5 → 冷却 300s | 防止暴力枚举用户名 |

通过准入链后进入 CSR payload 验证：
1. CSR 签名可由 CSR 内的 `public_key` 验证
2. `username` 未被占用或已通过恢复流程证明可绑定
3. requested usages/scopes/profile 在服务器策略允许范围内；`admin` usage 只能由 `admin_device` profile 请求，并需要现有管理员授权或离线 bootstrap
4. `temporary_device` 与 `managed_device` 不得请求 `admin` usage，不得获得证书签发、续签其它设备、吊销证书或修改 CA/trust policy 的 scope
5. 在同一事务中消费 challenge、创建或更新 user、记录 public key、签发用途隔离证书

### 5.3 用途隔离证书

证书按用途隔离，避免认证凭据被直接拿去签代码或执行管理员操作：

| Certificate | 用途 | TTL | 约束 |
|-------------|------|-----|------|
| `ClientAuthCertificate` | MCP 查询、session renew、普通认证请求 | 24h | 只能用于 `SWARM-REQUEST-V1` |
| `CodeSigningCertificate` | WASM/module deploy 签名 | 30–180 days（默认 30d，world.toml 可配） | 只能签 `module_hash + metadata` |
| `AdminCertificate` | 管理操作、证书治理、吊销、CA/trust policy 管理 | 1h | admin scope，敏感操作可要求双签；只能签给 `admin_device` profile |
| `FederationCertificate` | 跨服务器身份映射 | 24h | 受 federation trust policy 限制 |

同一个 public key 可以持有多个用途证书，但每张证书必须显式声明 `usage`、`world_id`、`audience`、`scope`、`expires_at` 和 `issuer_chain`。

### 5.4 代码签名证书过期语义

Swarm 不提供服务器 timestamp authority，也不新增 timestamp 审计。`CodeSigningCertificate` 只要求在部署请求提交时有效：

- 新部署或更新模块时，`CodeSigningCertificate` 必须未过期、未吊销，且 `usage=code_signing`
- 部署成功后，`module_hash + metadata` 进入世界状态；证书自然过期不影响已部署模块继续运行
- 证书过期后，用户若要重新部署同一模块，只需用新证书重新签署同一个 `module_hash + metadata`
- 证书吊销是安全事件；服务器可按 revocation reason 冻结、回滚或继续允许既有模块运行
- `accepted_at_tick` / `accepted_at_server_time` 可作为已有部署记录的一部分，但不作为“过期证书仍可授权新部署”的依据

### 5.5 多设备证书生命周期

用户可以要求服务器为同一账号签发任意多个同时有效的证书。推荐以设备为边界签发和管理：

| 设备类型 | 证书策略 | 推荐 TTL | 私钥位置 |
|----------|----------|----------|----------|
| 常用设备 | 每个设备一组 `ClientAuthCertificate` + `CodeSigningCertificate` | 30–180 days（可自动续签） | 客户端本地 / hardware key / OS keychain |
| 临时设备 | 仅签发最小 scope 的短期 `ClientAuthCertificate` | 15 min–24h | 临时本地存储，离开设备前销毁 |
| 托管设备 | 仅在用户声明设备无法生成或保存私钥时使用；禁止证书治理 scope | 15 min–24h | 服务器代管，`managed_by_server=true` |
| 管理员设备 | `AdminCertificate` 独立签发 | 15 min–1h | 硬件密钥优先，敏感操作可要求双签 |

证书管理规则：
- 一个账号可同时拥有多个 active certificate；服务端按 `certificate_id` 精确吊销
- **上限**：每账号最多 10 个 active certificate、5 个 active device；超出上限时续签/新 CSR 被拒（`certificate_limit_reached`），需先吊销旧证书
- 证书必须记录 `device_label`、`public_key_id`、`last_used_at`、`managed_by_server` 和 `revoked_at?`
- 用户发现设备丢失、不可访问或不再信任时，应吊销该设备对应证书，不需要吊销整个账号
- 若用户丢失或吊销了所有可用证书，不能自助续签；必须通过已验证邮箱恢复链接或管理员生成的恢复链接重新提交 CSR
- 常用设备续签时沿用本地私钥证明持有；临时设备默认不自动续签
- 临时设备和托管设备证书不得调用 `swarm_renew_certificate` 为其它设备续签、不得调用 `swarm_revoke_certificate` 吊销其它设备、不得签发新证书或修改 CA/trust policy
- 服务器可按风险策略拒绝为临时/托管设备签发 `CodeSigningCertificate` 或提升 admin scope
- 在线 CRL 只需保留尚未过期和最近过期窗口内的证书吊销项；超过 `max_certificate_ttl + max_clock_skew + federation_revocation_cache_ttl + operational_grace` 后可从在线认证路径清理

### 5.6a 请求 Replay Class 分类

每个 MCP/REST/WS 方法必须标注 replay class，用于 nonce 验证策略：

| Replay Class | 说明 | Nonce 策略 | 示例 |
|-------------|------|-----------|------|
| `read_replay_safe` | 纯查询，重复不影响状态 | 可选 nonce，time window 校验 | `swarm_get_snapshot` |
| `idempotent_mutation` | 重复执行结果相同 | Dragonfly nonce + time window（除 deploy 外） | `swarm_auth_device_register` |
| `deploy_mutation` | 部署请求——防重放由 FDB version_counter 保证 | **FDB version_counter**（见 §10.8） | `swarm_deploy` |
| `non_idempotent_mutation` | 重复执行产生副作用 | FDB 事务内消费 challenge 或 version counter | `swarm_submit_csr`（FDB 事务内消费 PoW challenge，一次性）、`swarm_admin_set_world_config` |
| `admin_critical` | 安全敏感管理操作 | FDB 事务内消费 challenge + 双签审计 | `swarm_revoke_certificate`、CA 操作 |

Dragonfly nonce 仅用于 `read_replay_safe` 和 `idempotent_mutation`。所有 `non_idempotent_mutation` 和 `admin_critical` 操作必须使用 FDB version counter、idempotency key 或一次性 challenge，并在事务内消费。

### 5.6b 授权矩阵

#### Auth / Gateway / Engine 权威边界

| 组件 | 持有 | 不持有 | 职责 |
|------|------|--------|------|
| **Auth Service** | public keys, challenge state, password/passkey recovery, refresh token 兼容层, certificate audit, 证书签发, CRL | 用户私钥、Server Root CA 私钥 | 独立进程，所有签名和认证操作在此完成 |
| **Gateway** | 无状态代理, canonical request 验签入口, rate limit, Principal 注入, transport 层 canonicalization | 认证状态, 用户私钥, 密码库 | 验签后将最小化 principal/certificate snapshot 传入 Engine |
| **Engine** | trusted root fingerprints, certificate verifier, revoked certificate cache | 用户私钥, 密码, PoW challenge state, CA 私钥, 签发能力 | 仅消费已验证的 principal——不执行注册、CSR 审核或证书签发 |

#### MCP/REST 方法授权矩阵

每个 MCP 方法必须标注以下维度：

| 方法 | Replay Class | Required Scope | Rate Limit | Visibility Filter | Admin Override |
|------|-------------|----------------|------------|-------------------|----------------|
| `swarm_get_snapshot` | read_replay_safe | swarm:read | 10/s | fog_of_war | no |
| `swarm_deploy` | deploy_mutation | swarm:deploy | 1/5s | owner | no |
| `swarm_submit_csr` | non_idempotent_mutation | swarm:register | 1/30s | none | no |
| `swarm_revoke_certificate` | admin_critical | swarm:admin | 1/10s | admin scope | required |
| `swarm_admin_create_password_reset` | admin_critical | swarm:admin:recovery | 1/60s | admin scope | dual-audit |

完整矩阵见 `interface.md` MCP 工具表。

### 5.6c Canonical Request Signature

```
Swarm-Certificate-Chain: <base64 leaf + intermediate>
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

验证顺序：
1. 证书链能追溯到当前 server trust root，且 intermediate/leaf 未过期、未吊销
2. leaf certificate 的 `usage` 覆盖当前操作
3. `Swarm-Signature` 可由 leaf certificate 中的 public key 验证
4. timestamp 在允许窗口内，nonce 未使用
5. scope 覆盖当前操作，audience/world_id 匹配

#### Canonical 序列化规范

签名 payload 在签名前按以下规则序列化为字节串：

1. **行分隔**：每行以 `\n` (LF，0x0A) 结尾，不含 `\r`
2. **字段顺序**：严格按 `method → path → body_hash → timestamp → nonce → certificate_id → player_id → audience` 排列
3. **空 body_hash**：无 body 时 `body_hash` 为 `blake3("")` 的 hex 值
4. **整数编码**：timestamp 为十进制字符串（非 hex），player_id 为十进制字符串
5. **domain separator**：首行 `SWARM-REQUEST-V1` 为签名字节前缀
6. **UTF-8**：所有字符串为 valid UTF-8，不包含 BOM

```text
签名输入 = "SWARM-REQUEST-V1\n" +
           "method: <v>\n" +
           "path: <v>\n" +
           "body_hash: <v>\n" +
           "timestamp: <v>\n" +
           "nonce: <v>\n" +
           "certificate_id: <v>\n" +
           "player_id: <v>\n" +
           "audience: <v>\n"
```

Ed25519 签名由此字节串产生。验签时按相同规则重建输入。

### 5.7 不安全传输语义

应用层证书允许 HTTP、不可信反向代理或本地离线网络中的身份认证和请求完整性校验。首次访问 HTTP 服务器时，客户端必须展示 `server_id + Server Root CA fingerprint`，由用户人工确认并写入客户端证书存储（TOFU / explicit pinning）。完成 pinning 后，客户端不再依赖外部 TLS/WebPKI 判断该 Swarm 服务器身份，而是验证应用层证书链是否能追溯到已保存的 Server Root CA。

HTTP 场景下：

- 攻击者无法伪造服务器应用层证书链、用户签名或篡改已签名 body
- 攻击者可以观察流量元数据、阻断请求、回放未过期请求，或在首次 pinning 前发起中间人攻击
- nonce/timestamp 必须强制启用，重放窗口默认不超过 60 秒
- 涉及恢复 token、私密邮箱、管理员恢复链接时，payload 应加密给服务器应用层证书 public key
- 服务端域名真实性由 `server_id / root fingerprint pinning` 保证，不由外部 TLS 证书保证

**安全评审结论 (S-H1/S-H2)**：
- 浏览器端 token/certificate material 禁止存 localStorage。使用 HttpOnly Secure cookie + WebCrypto non-extractable key 或 OS keychain（见 §14.3）。
- Server Intermediate CA 私钥保护从 advisory 升级为 **mandatory**：启动时检查私钥文件权限（0600 或 HSM 可访问性），不满足则拒绝启动；补充强制轮换（90 天）与审计合同

---

## 6. 恢复凭据与技术选型

### 6.1 密码恢复哈希：argon2id

**选择：argon2id**，使用 `argon2` crate。

参数配置（OWASP 2025 推荐）：

```rust
use argon2::{
    Argon2, PasswordHasher, PasswordVerifier,
    password_hash::{SaltString, PasswordHash, rand_core::OsRng},
    Algorithm, Version, Params,
};

pub const ARGON2_MEMORY_KIB: u32 = 19_456;  // 19 MiB
pub const ARGON2_ITERATIONS: u32 = 2;
pub const ARGON2_PARALLELISM: u32 = 1;

fn hash_password(password: &str) -> Result<String, McpError> {
    let salt = SaltString::generate(&mut OsRng);
    let params = Params::new(
        ARGON2_MEMORY_KIB,
        ARGON2_ITERATIONS,
        ARGON2_PARALLELISM,
        Some(Params::DEFAULT_OUTPUT_LEN),
    ).map_err(|e| McpError::internal_error(format!("argon2 params: {e}")))?;

    let argon2 = Argon2::new(Algorithm::Argon2id, Version::V0x13, params);
    let hash = argon2
        .hash_password(password.as_bytes(), &salt)
        .map_err(|e| McpError::internal_error(format!("password hashing failed: {e}")))?
        .to_string();
    Ok(hash)
}

fn verify_password(password: &str, hash: &str) -> Result<bool, McpError> {
    let parsed = PasswordHash::new(hash)
        .map_err(|e| McpError::internal_error(format!("invalid password hash: {e}")))?;
    // Verify PHC string contains expected params
    if parsed.version != Some(Version::V0x13) {
        return Err(McpError::internal_error("unsupported argon2 version"));
    }
    let params = Params::new(
        ARGON2_MEMORY_KIB,
        ARGON2_ITERATIONS,
        ARGON2_PARALLELISM,
        Some(Params::DEFAULT_OUTPUT_LEN),
    ).map_err(|e| McpError::internal_error(format!("argon2 params: {e}")))?;
    let argon2 = Argon2::new(Algorithm::Argon2id, Version::V0x13, params);
    Ok(argon2
        .verify_password(password.as_bytes(), &parsed)
        .is_ok())
}
```

> **实现者注意**：不得使用 `Argon2::default()`。必须显式构造 `Params` 并测试 PHC 字符串包含 `m=19456,t=2,p=1`。
>
> **安全评审要求 (S-H4)**：Argon2id 验证为 CPU 密集型操作（~100ms × 19MiB）。必须在 Auth Service 中部署全局 argon2 semaphore/worker pool——限制并发验证数为 `min(cpu_cores, 4)`。启动时预分配固定大小线程池，超出的请求排队等待（超时返回 `rate_limited`）。配合已有的 dummy PHC 和 per-IP 限流形成三层防护，防止分布式 DoS 放大攻击。

### 6.2 Auth 存储：FoundationDB

**Auth subspace（独立于游戏世界状态）**：

```
auth/users/<login_username>          → {player_id, display_name, email?, email_verified, recovery_password_hash?, created_at, deleted_at?, schema_version: 1}
auth/public_keys/<player_id>/<key_id> → {public_key, key_source, managed_by_server, label, created_at, last_used_at?, revoked_at?}
auth/passkeys/<player_id>/<credential_id> → {public_key, rp_id, transports, device_label?, created_at, last_used_at?, revoked_at?}
auth/certificates/<certificate_id>   → {player_id, key_id, usage, scopes, audience, device_label?, managed_by_server, issuer_id, issued_at, expires_at, last_used_at?, revoked_at?}
auth/ca/intermediates/<issuer_id>    → {public_key, issued_at, expires_at, revoked_at?, root_signature}
auth/identities/<provider>/<subject> → player_id  (唯一索引)
auth/challenges/<challenge_id>       → {kind, challenge, difficulty_bits?, expires_at, consumed: bool, created_at}
auth/sessions/<refresh_token_hash>   → {player_id, certificate_id?, client_public_key, created_at, expires_at, rotated_from}
auth/login_fail/<login_subject>      → {fail_count, last_fail_at, locked_until}
auth/revocations/<id>                → {type: public_key|certificate|session|intermediate, revoked_at, reason}
auth/reset/<token_hash>              → {player_id, email?, admin_id?, reason?, created_at, expires_at, consumed: bool}
auth/email_verify/<token_hash>       → {player_id, email, created_at, expires_at, consumed: bool}
auth/admin_audit/<event_id>          → {admin_id, target_player_id, action, reason, created_at, expires_at?}
auth/request_nonce/<certificate_id>/<nonce> → {created_at, expires_at}
```

所有 value 带 `schema_version` 字段便于未来迁移。

**事务约束**：
- 密码哈希在事务外完成（argon2id ~100ms），FDB 事务保持短生命周期（<10ms）
- 事务冲突重试最多 3 次，返回 `McpError::conflict_retry`
- FDB key 使用 `auth/` 前缀隔离游戏世界状态

---

## 7. Identity 模型

### 7.1 三层身份（+ 审计指纹）

```
login_username        — 登录凭据，ASCII [a-zA-Z0-9_-]{3,32}，大小写不敏感，不可变
display_name          — 显示名称，Unicode，≤32 字符，可直接修改
player_id             — 引擎内运行时标识，u64，确定性 hash(provider + ":" + subject)
identity_fingerprint  — 审计/联邦稳定标识，[u8; 32]，完整 Blake3 输出（不经 64-bit 截断）
```

- `login_username` 是 subject（认证主体），用于登录和 `player_id` 推导，不可变
- `display_name` 默认为 `login_username`，可通过 `swarm_update_profile` 修改
- `player_id` 推导：
  - 本地：`blake3("local:" + login_username_lowercase) → 取低 64 bits → u64`
  - 联邦：`blake3("federated:" + world_id + ":" + original_player_id) → u64`
- `identity_fingerprint` = 完整 `blake3("local:" + login_username_lowercase)` 或 `blake3("federated:" + world_id + ":" + original_player_id)` 的 **全部 32 字节**，不经 64-bit 截断
  - **用途**：跨世界联邦身份映射、审计日志碰撞排查、TOFU pinning（`swarm_get_server_trust`）
  - **不进入 hot-path**：tick 内 ECS 仅使用 `player_id: u64`，`identity_fingerprint` 离线使用
  - **FDB 存储**：在 `auth/users/<login_username>` 中作为可选字段；在 `auth/identities/` 和跨世界联邦握手消息中包含
- 碰撞概率：对于 10^6 用户，64-bit 截断约 2.7×10^-8，可接受。完整 256-bit 指纹碰撞概率可忽略

### 7.2 用户名规则

```
允许字符:    [a-zA-Z0-9_-]
长度:        3-32 字符
大小写:      不敏感（存储和查找时一律 lowercase）
保留列表:    ["admin", "root", "swarm", "system", "mod", "gm"]
校验正则:    ^[a-zA-Z][a-zA-Z0-9_-]{2,31}$
```

**用户名注册状态可见性由服务器配置决定**：通过 `auth.username_visibility` 配置项控制。

```toml
[auth]
# "public": 注册前先检查用户名是否存在（可节省客户端 PoW 但暴露用户名占用状态）
# "private": 先验证 PoW 再检查用户名（不暴露用户名状态，但 taken 时会浪费一次 PoW）
username_visibility = "private"
```

- `"public"` 模式：`swarm_submit_csr` 先检查用户名 → 若 taken 则直接返回 `username_taken`（不消费 challenge）
- `"private"` 模式：先验证 PoW → 消费 challenge → 再检查用户名。即使 taken 也消耗了 PoW，但不暴露信息
- 无论何种模式，恢复凭据校验统一返回 `invalid_credentials`（不区分不存在/密码错误），并执行 dummy argon2id

---

## 8. Recovery Password 规则

```
最小长度:    8 字符（人类），64 字符（AI 随机生成建议）
最大长度:    128 字符
要求:        至少包含 1 个字母 + 1 个数字
禁止:        与 login_username 相同或包含 login_username
禁止列表:    ["password", "12345678", "swarm123", "admin123", "qwerty123", "letmein1",
              "changeme1", "iloveyou1", "monkey123", "dragon123"]
             （常见弱密码 Top 10，后续接入 zxcvbn / HaveIBeenPwned API）
密码强度:    推荐人类使用 12+ 字符 passphrase（如 "correct-horse-battery-staple"）
```

**AI agent recovery password（可选）**：若启用 recovery password，使用 `random_hex(32)` 生成 64 字符随机密码。

密码哈希在事务外执行（避免 FDB 事务内高延迟）。

---

## 9. PoW 工作量证明

### 9.1 算法

**blake3 前导零 bit**（非字节），允许细粒度难度调节：

```rust
fn generate_challenge(difficulty_bits: u8) -> PoWChallenge {
    PoWChallenge {
        challenge_id: random_hex(16),
        challenge: random_hex(32),
        difficulty_bits,       // 服务端权威值，存储于 FDB
        created_at: now_seconds(),
        ttl_seconds: 300,      // 5 分钟有效期
    }
}

fn verify_pow(challenge: &str, nonce: &str, difficulty_bits: u8) -> bool {
    let input = format!("{}{}", challenge, nonce);
    let hash = blake3::hash(input.as_bytes());
    let bytes = hash.as_bytes();
    // 检查前 difficulty_bits 位是否全为零
    let full_bytes = (difficulty_bits / 8) as usize;
    let rem_bits = difficulty_bits % 8;
    if bytes[..full_bytes].iter().any(|&b| b != 0) { return false; }
    if rem_bits > 0 {
        let mask = 0xFFu8 << (8 - rem_bits);
        (bytes[full_bytes] & mask) == 0
    } else {
        true
    }
}
```

### 9.2 难度参数

| 配置 | difficulty_bits | 预期尝试次数 | Rust native | Python | Node WASM | 移动端 WASM |
|------|----------------|-------------|-------------|--------|-----------|------------|
| 开发/测试 | 16 | ~65K | <1ms | <5ms | <10ms | <20ms |
| 轻量 | 20 | ~1M | ~10ms | ~50ms | ~100ms | ~200ms |
| 标准 (默认) | **24** | **~16.7M** | **~150ms** | **~800ms** | **~1.5s** | **~3s** |
| 高安全 | 28 | ~268M | ~2.5s | ~13s | ~25s | ~50s |

> 以上为单核保守估算。实际性能受硬件、JIT/WASM 引擎、浏览器节流影响。默认 `difficulty_bits = 24`。

### 9.3 服务端绑定

**`swarm_submit_csr` 请求仅提交 `challenge_id + nonce + csr_signature`**，不包含客户端回传的 challenge 或 difficulty：

```json
{
  "method": "swarm_submit_csr",
  "params": {
    "username": "kagurazaka",
    "csr": "base64:SWARM-CSR-V1...",
    "challenge_id": "a1b2c3d4e5f6a7b8",
    "nonce": "1784501234",
    "csr_signature": "ed25519:base64..."
  }
}
```

**服务端验证流程**（FDB 事务内）：

```rust
// 1. 从 FDB 读取 challenge（服务端权威）
let stored = tx.get(format!("auth/challenges/{}", params.challenge_id).as_bytes())?;
let challenge: ChallengeRecord = stored.ok_or("challenge not found")?.deserialize()?;

// 2. 校验
if challenge.consumed { return Err("challenge already used"); }
if now > challenge.created_at + challenge.ttl_seconds { return Err("challenge expired"); }

// 3. 用服务端存储的 challenge + difficulty 验证 PoW
if !verify_pow(&challenge.challenge, &params.nonce, challenge.difficulty_bits) {
    return Err("invalid_pow");
}

// 4. PoW 验证通过后，标记消费（原子性）
tx.set(challenge_key, challenge.with_consumed(true).serialize());

// 5. 检查用户名 + 创建用户
//    消费策略取决于 auth.username_visibility：
//    - "public": 先检查用户名 → taken 则返回 username_taken（challenge 不消费）
//    - "private": challenge 已验证/消费 → 再检查用户名 → taken 则返回 username_taken
//    （challenge 已消费，客户端需重新获取）
//    实现: 在 PoW 验证之前或之后分支，但整个流程在同一 FDB 事务内
```

### 9.4 CSR / Recovery PoW

CSR 和恢复流程的额外 PoW 通过 `auth.recovery_pow` 配置项控制：

```toml
[auth.recovery_pow]
enabled = true           # 默认开启（16-bit 低难度 PoW 防滥用）
difficulty_bits = 16     # 低难度（~65K 次尝试，<1ms Rust native）
trigger_fail_count = 5   # 连续失败 N 次后触发
trigger_window_seconds = 300  # 失败计数的滑动窗口
```

- 默认开启：恢复凭据校验始终要求轻量 PoW（16-bit, ~65K 次尝试），与注册 PoW（24-bit）独立
- 低风险环境（内网、离线部署、开发/测试）可在 world.toml 中关闭：`[auth.recovery_pow] enabled = false`
- 服务端动态判断：检查 `auth/login_fail/<username>` 的 fail_count
- 支持运行时开关，无需重启

---

## 10. API 设计

### 10.1 MCP 工具一览

| Tool | 参数 | 返回 | 说明 |
|------|------|------|------|
| `swarm_register_challenge` | (无) | `PoWChallenge` | 获取注册/CSR PoW 挑战 |
| `swarm_submit_csr` | `username`, `csr`, `certificate_profile`, `device_label?`, `challenge_id`, `nonce`, `csr_signature`, `email?`, `recovery_password?` | `CertificateBundle` | 完成 PoW + CSR 验证 + 证书签发 |
| `swarm_renew_certificate` | `certificate_id`, `renewal_csr`, `proof_signature` | `CertificateBundle` | 续签应用层证书 |
| `swarm_get_server_trust` | (无) | `ServerTrustInfo` | 获取 server_id、Root CA fingerprint、Intermediate chain |
| `swarm_token_refresh` | `refresh_token`, `client_public_key` | `LoginResult` | Web session 兼容续签 |
| `swarm_auth_revoke` | `refresh_token`、`certificate_id` 或 `public_key_id` | `RevokeResult` | 吊销 session/certificate/key |
| `swarm_list_certificates` | (无) | `CertificateListResult` | 列出当前账号证书 |
| `swarm_revoke_certificate` | `certificate_id` | `SuccessResult` | 吊销已签发证书 |
| `swarm_update_profile` | `display_name` | `ProfileResult` | 修改显示名称 |
| `swarm_change_password` | `old_password`, `new_password` | `SuccessResult` | 修改 recovery password（已登录） |
| `swarm_request_password_reset` | `email` | `ResetRequestResult` | 请求 key/certificate 恢复（发送邮件） |
| `swarm_admin_create_password_reset` | `username`, `reason` | `AdminPasswordResetResult` | 管理员生成恢复链接 |
| `swarm_confirm_password_reset` | `reset_token`, `new_password?`, `new_csr?` | `CertificateBundle` | 确认恢复 + 签发新证书 |
| `swarm_register_passkey` | `passkey_attestation`, `device_label` | `SuccessResult` | 绑定 passkey 恢复因子 |
| `swarm_recover_with_passkey` | `passkey_assertion`, `new_csr`, `certificate_profile`, `device_label?` | `CertificateBundle` | 使用 passkey 恢复并签发新证书 |
| `swarm_bind_email` | `email` | `SuccessResult` | 绑定/更换邮箱 |
| `swarm_delete_account` | `password` 或 `certificate_signature` | `SuccessResult` | 删除账号及关联资产 |
| `swarm_restore_account` | `username`, `password` 或 `recovery_token` | `CertificateBundle` | 恢复已删除账号（grace period 内） |
| `swarm_cancel_account_deletion` | `username`, `password` 或 `recovery_token` | `CertificateBundle` | 取消账号删除（同 restore） |
| `swarm_federated_login` | `remote_certificate_chain`, `challenge_signature`, `new_csr?` | `CertificateBundle` | 用外部世界证书作为 bootstrap proof，在本地重签证书 |


### 10.2 `swarm_register_challenge`

```
POST /mcp (JSON-RPC)
{"method": "swarm_register_challenge", "params": {}}

Response:
{
  "challenge_id": "a1b2c3d4e5f6a7b8",
  "challenge": "9f86d081884c7d659a2feaa0c55ad015...",
  "difficulty_bits": 24,
  "expires_in_seconds": 300
}
```

### 10.3 `swarm_submit_csr`

```
POST /mcp (JSON-RPC)
{
  "method": "swarm_submit_csr",
  "params": {
    "username": "kagurazaka",
    "csr": "base64:SWARM-CSR-V1...",
    "certificate_profile": "regular_device",
    "device_label": "Kagurazaka laptop",
    "challenge_id": "a1b2c3d4e5f6a7b8",
    "nonce": "1784501234",
    "csr_signature": "ed25519:base64...",
    "email": "user@example.com",                    // 可选
    "recovery_password": "correct-horse-battery-staple" // 可选
  }
}

Response: CertificateBundle {player_id, client_auth_certificate, code_signing_certificate, issuer_chain, web_session?}
```

**注意**：请求中**不包含** `challenge` 和 `difficulty` 字段 — 服务端从 FDB 读取权威值。CSR 内的 public key 必须验证 `csr_signature`。

### 10.4 `swarm_renew_certificate`

```
POST /mcp (JSON-RPC)
{
  "method": "swarm_renew_certificate",
  "params": {
    "certificate_id": "cert_abc123",
    "renewal_csr": "base64:SWARM-CSR-V1...",
    "proof_signature": "ed25519:base64..."
  }
}
```

**安全措施**：
- 旧证书未过期时，`proof_signature` 必须由旧证书 public key 验证
- 私钥轮换时，renewal CSR 可包含新 public key，但必须由旧 key 签署迁移授权
- 旧 key 丢失时，必须走邮箱/管理员恢复链接，不允许无证明续签
- 续签结果按 requested usage 签发新的用途隔离证书

### 10.5 应用层证书请求

客户端对敏感请求添加 `Swarm-Certificate-Chain`、`Swarm-Cert-Id`、`Swarm-Timestamp`、`Swarm-Nonce`、`Swarm-Signature`。服务端按 §5.4 验证证书链、usage、scope、audience、nonce 和签名。

### 10.5a WebSocket 证书握手与会话安全

WebSocket 连接按客户端类型分为两条安全路径：

**A. Agent/CLI 已认证会话（Authenticated WS）**：

连接建立时执行证书握手，禁止仅凭 `swarm-cert.<cert_id>` 建立认证连接：

```
客户端 → 服务端: WebSocket 升级请求
  头部:
    Swarm-Certificate-Chain: <base64 leaf + intermediate>
    Swarm-Cert-Id: <certificate_id>
    Swarm-Timestamp: <unix_seconds>
    Swarm-Nonce: <random_96bit>
    Swarm-Signature: <ed25519 signature of canonical payload>

服务端:
  1. 验证证书链 → 提取 public_key + usage(mcp_query)
  2. 验证 canonical payload: "SWARM-WS-V1\n<cert_id>\n<timestamp>\n<nonce>"
  3. 验证 nonce 未使用（FDB 去重）
  4. 验证 timestamp 在 ±30s 窗口内
  5. 建立认证 WebSocket → 会话绑定 (cert_id, player_id, current_tick)
  6. 后续每条消息必须携带 per-message seq + MAC/Ed25519 签名
     - seq: 单调递增（每方向独立），接收方严格检查 `seq == last_seq + 1`
     - MAC: 对 `SWARM-WS-MSG-V1\n<seq>\n<tick>\n<body_hash>` 的 Ed25519 签名
     - **tick 绑定**：MAC payload 必须包含当前 tick 编号——防止跨 tick 消息重放
     - seq 跳跃或 MAC 不匹配 → 断开连接 + 审计日志
  7. 服务端回复也附独立 seq + 签名
```

WebSocket 断开后需重新握手。会话内消息不计入 per-tick rate limit（握手时已完成身份绑定）。

- `seq`: 单调递增序号（从 1 开始），接收方严格检查 `seq == last_seq + 1`
- `mac`: 对 `SWARM-WS-MSG-V1\n<seq>\n<body_hash>` 的 Ed25519 签名，使用握手绑定的用户私钥
- 签名验证通过后消息才能被处理；seq 跳跃视为安全事件 → 断开连接 + 审计日志
- 服务端回复也必须附 seq（独立计数器）+ 服务端签名

WebSocket 断开后需重新握手。会话内消息不计入 per-tick rate limit（握手时已完成身份绑定）。

**B. 浏览器/公开观众（Read-Only Spectator WS）**：

浏览器 WebSocket 连接**仅允许只读订阅**——接收 SSE 风格的推送事件流，不得发送任何写操作或认证消息：

- 公开 spectator WS 端点不接受 `Swarm-Certificate-Chain` 头部，不执行证书握手
- 只读事件流仅包含公开世界状态（房间列表、在线玩家数、公开排行榜），不泄露玩家私有数据
- **无 per-message 签名要求**（只读、无状态变更）
- 速率限制：每个 spectator 连接最多 10 events/s

> **决策记录 (D7)**：Agent/CLI WS 采用 per-message seq/MAC/signature，浏览器 spectator 跳过签名（只读订阅）。详见 [MCP 安全规范](specs/security/03-mcp-security.md) §2.5。

### 10.5b Admin 高权限操作认证

Admin 工具（`swarm_admin_*`）必须在 MCP schema 中显式表达双签/冷却/审计要求：

| 操作 | 认证要求 | 冷却 | 审计 |
|---|---|---|---|
| Epoch bump / force CRL rotation | AdminCertificate 签名 + 第二个 Admin 确认 | 60s per-world | 写入 `audit/admin/` 日志 |
| Batch revoke | AdminCertificate 签名 | 10s per-target | 记录所有 revoked cert_id |
| Admin recovery link 生成 | AdminCertificate 签名 + 目标用户邮箱验证 | 无（用户触发） | 写入 `audit/recovery/` |
| World config 热更新 | AdminCertificate 签名 | 30s per-world | 记录变更前后 config diff |

Admin MCP tools 的 input schema 必须显式包含 `admin_certificate_id`、`admin_signature`、`idempotency_key`。服务端验证 canonical payload 包含 `method + params + timestamp + nonce`。

### 10.6 错误码体系

| Code | HTTP | 说明 | 可重试 |
|------|------|------|--------|
| `invalid_credentials` | 401 | recovery password 或恢复证明无效（不区分不存在/错误） | ✅ |
| `username_taken` | 409 | 用户名已被注册 | 换用户名 |
| `identity_conflict` | 409 | external bootstrap/federation identity 与已有账号冲突 | 联系支持 |
| `weak_password` | 422 | 密码不满足强度要求 | ✅ |
| `invalid_pow` | 422 | PoW 验证失败 | ✅（重新获取 challenge） |
| `challenge_expired` | 422 | Challenge 已过期 | ✅（重新获取） |
| `challenge_consumed` | 422 | Challenge 已使用 | ✅（重新获取） |
| `challenge_not_found` | 404 | challenge_id 不存在 | ✅（重新获取） |
| `account_locked` | 423 | 登录失败次数过多，暂时锁定 | 等待解锁 |
| `login_pow_required` | 428 | 需要完成登录 PoW | ✅（求解 PoW 后重试） |
| `rate_limited` | 429 | 频率限制 | 等待 |
| `internal_error` | 500 | 服务端错误 | ✅ |

### 10.7 限速模型（独立于游戏 tick）

| 维度 | CSR 提交 | 恢复凭据校验 | challenge 申请 |
|------|----------|--------------|---------------|
| Per IP | — | 10/min | 10/min |
| Per username | — | 10/min, 5 次失败锁 5min | — |
| 全局 | 受 PoW 保护 | 1000/min | 100/min |

##### CSR Admission Control（多维防护）

CSR 提交使用**多层 admission control**，PoW 为第一层成本过滤，不替代速率限制：

| 层 | 机制 | 限制 | 说明 |
|----|------|------|------|
| **L1: PoW** | Blake3 brute-force | 可配置难度（默认 24 bits） | 第一层成本过滤——提高单次 CSR 成本，不限制并发度 |
| **L2: Per-IP rate limit** | Token bucket | 10/min per IP | 单 IP CSR 提交速率上限 |
| **L3: Per-ASN rate limit** | Token bucket | 50/min per ASN | 同一 ASN 的分布式攻击防御 |
| **L4: Global in-flight cap** | Semaphore | 100 并发 CSR signing | 全局并发 CSR 签发上限 |
| **L5: Worker semaphore + bounded queue** | Semaphore + timeout | queue depth=500, queue timeout=30s | CSR signing worker pool 饱和时排队，超时返回 `rate_limited` |
| **L6: Audit throttle** | 异常检测 | 连续超限 → 熔断 | 连续 3 次触发 L4/L5 限流后，该来源 5min 内所有 CSR 直接拒绝 |

**设计理由**：PoW 是 per-request 成本，对分布式来源（云 VM、僵尸网络）不构成有效的速率控制——攻击者可利用并行计算优势绕过 PoW 难度。多维 admission control 按实体（IP/ASN）和全局资源（semaphore/queue）限制并发，PoW 作为基础成本层防止无成本滥用。

Challenge 申请设轻量 IP 限速（30/min per IP）防止存储 DoS，独立于 CSR admission control。

恢复凭据 per-IP 限流部署在 argon2id 验证之前：达到来源限流阈值时直接返回 `rate_limited`，不进入密码哈希，防止攻击者用大量随机 username 绕过 per-account lockout 将小请求放大为 19MiB argon2id 服务端成本。

### 10.8 Auth 热路径性能合同

#### Nonce 存储

请求 nonce 防重放不写 FDB。使用 Dragonfly SETNX TTL 作为热路径权威存储：

| 维度 | 决策 |
|------|------|
| 存储引擎 | Dragonfly SETNX TTL |
| Key 格式 | `nonce:{account_id}:{nonce_value}` → `"1"` |
| TTL | 300s（可配置），覆盖网络重传窗口 |
| 清理 | TTL 自动过期，无后台任务 |
| 崩溃语义 | TTL 窗口内可重放；窗口过后 nonce 过期 → 重放被拒绝 |
| 分片 | Dragonfly cluster hash-slot 按 `{account_id}` 分片 |

Deploy 不使用 nonce——防重放由 `version_counter` 保证（见 D2 裁决）。

高价值操作（admin 证书签发、恢复流程、Admin MCP 工具）使用 challenge-response nonce，nonce 消费在 **FDB 事务内原子执行**：服务端维护 per-admin 单调递增计数器 `auth/admin_nonce_counter/<admin_id>`，每个 admin challenge 绑定当前计数器值。消费时在 FDB 事务内执行原子 CAS（compare-and-swap）递增计数器——若计数器已被递增（重放）则事务冲突回滚，拒绝操作。此机制保证 admin 操作的严格一次性语义，崩溃后不重放。

#### Nonce vs Version Counter

| 场景 | 机制 | 存储 | 崩溃语义 |
|---|---|---|---|
| MCP 查询请求（读） | Nonce (Dragonfly TTL) | Dragonfly, 300s TTL | TTL 窗口内可重放 |
| Deploy 请求 | Version Counter (FDB) | FDB `version/{player_id}` | 严格递增，崩溃后不重放 |
| Admin 高权限操作 | FDB monotonic counter (CAS atomic) | FDB `auth/admin_nonce_counter/<admin_id>` | 严格递增，崩溃后不重放 |
| CSR 提交 | PoW nonce | FDB `challenge/{id}`，consumed 标记 | 一次性消费，原子标记 |

Deploy 使用 FDB 持久化的 `version_counter`：

```
swarm_deploy:
  FDB 事务:
    current = read version/{player_id}
    write version/{player_id} = current + 1
    write deploy/{player_id}/{current + 1} = {module_hash, ...}
```

同一 player 的 deploy 严格按 version_counter 顺序执行。即使 Dragonfly 崩溃，deploy 也不重放——FDB 事务保证 version_counter 原子递增。

#### Audience 字符串语法

所有 audience 字符串使用规范语法：`swarm-aud-v1:<transport>:<server_id>:<world_id>:<subject_id>`

- `transport`：客户端传输类型，枚举：`browser-http` | `browser-ws` | `agent-mcp` | `cli-rest` | `replay-viewer`
- `server_id`：服务端标识（来自 Server Root CA 的 server_id）
- `world_id`：世界标识
- `subject_id`：主体标识——对于玩家操作为 `player_id`，对于服务间调用为 `server_id`

禁止宽松匹配——audience 必须精确匹配 Canonical Request 中的对应字段。Gateway 在入口处验证 `audience` 字段与请求上下文（目标 server/world/player/transport）完全一致。

#### 证书链验证缓存

| 维度 | 决策 |
|------|------|
| 缓存位置 | Engine 进程内 LRU（不跨请求走 Auth Service） |
| 缓存键 | `Blake3(cert_fingerprint || intermediate_fingerprint)` |
| 失效触发 | CRL 更新、证书吊销、Intermediate CA 轮换 |
| 容量 | 10000 条，LRU 淘汰 |
| 预热 | 服务启动时不预热，首次请求冷启动 |

#### Auth 子系统缓存边界

| 数据 | 权威存储 | 热路径缓存 | 允许延迟 |
|------|---------|-----------|---------|
| Nonce 新鲜度 | Dragonfly (TTL) | 无（直接查 Dragonfly） | 0 |
| 证书吊销状态 (CRL) | FDB | Engine 内 LRU | World 默认 60s（持久世界容忍度更高）；Arena/competitive 默认 5s（吊销后至多 5s 旧证书仍可被接受） |
| 证书链验证结果 | — | Engine 内 LRU | 0（即时失效） |
| Server Root CA | FDB | Engine 启动时加载 | 0（重启生效） |
| Intermediate CA | FDB | Engine 启动时加载 | 0（重启生效） |
| 用户 session | Dragonfly (TTL) | 无 | 0 |
| 账号状态（锁定/删除） | FDB | Dragonfly (30s TTL) | 30s |

#### 未认证端点保护

未认证端点（challenge 申请、CSR 提交）的速率限制：

| 端点 | 限制 | 机制 |
|------|------|------|
| `swarm_register_challenge` | 10/min per IP | Dragonfly 计数器 |
| `swarm_get_server_trust` | 60/min per IP | Dragonfly 计数器 |
| CSR 提交 | PoW 自身限速 | 无额外 IP 限制 |
| 恢复凭据校验 | 10/min per IP + 5 次失败锁 5min per username | Dragonfly + FDB |
| Admin 恢复链接 | 需 AdminCertificate + signed request | 认证后无额外限制 |

#### 安全 Epoch Bump 运维行为

安全 epoch bump 按 D5 裁决的分级状态机执行。运维层面：

- bump 命令需要 `AdminCertificate` 签名
- bump 事件写入 FDB `auth/epoch_history`，记录 reason + timestamp + admin_id
- 受影响模块列表写入 TickTrace，replay 使用记录事件
- Engine 收到 bump 通知后立即更新 CRL 缓存（全量刷新）
- 运行中模块按 reason 分级处理：`paused_security` 立即暂停，`needs_revalidation` 后台队列

### 10.9 证书生命周期 UX

#### 到期通知

客户端可通过以下方式感知证书即将到期：

| 渠道 | 内容 |
|------|------|
| MCP 响应头 | `Swarm-Cert-Expires-In: 86400`（秒） |
| MCP 事件 | `certificate_expiring_soon` SSE 事件（距到期 ≤ 7 天时触发） |
| Web UI | 设备列表显示每张证书的剩余有效期 |

#### 设备管理

Web UI 和 MCP 均提供设备证书管理：

- `swarm_list_certificates` — 列出当前账号所有证书，含 `device_label`、`usage`、`issued_at`、`expires_at`、`last_used_at`
- `swarm_revoke_certificate` — 吊销指定证书，立即生效（CRL 更新）
- `swarm_renew_certificate` — 续签证书，需旧证书签名授权

#### 恢复默认策略（D4 裁决）

| 恢复场景 | 默认行为 |
|----------|----------|
| stolen-device | 吊销全部旧证书 |
| all-certs-lost | 吊销全部旧证书 |
| device-swap（旧设备仍可控） | 保留，用户可手动吊销 |
| forgot-password（同设备） | 保留 |

---

## 11. Recovery Password 管理

### 11.1 Recovery Password 修改（已登录）

已登录用户可提供旧 recovery password 验证身份后设置新 recovery password：

```
POST /mcp (JSON-RPC)
{
  "method": "swarm_change_password",
  "params": {
    "old_password": "correct-horse-battery-staple",
    "new_password": "new-correct-horse-battery-staple"
  }
}
```

- 需要有效的 session/证书（与 `swarm_token_refresh` 同等权限）
- 验证旧密码 → argon2id hash 新密码 → 更新 FDB
- 修改成功后不强制重新登录（现有 session 保持有效）
- 新密码必须通过 §7 密码规则校验

### 11.2 证书恢复（邮箱验证）

当用户丢失所有可用证书、设备不可访问或私钥损坏时，通过邮箱恢复链接重新提交 CSR 并签发新证书。两步流程：请求 → 邮件 → 确认。

**Step 1: 请求恢复**

```
POST /mcp (JSON-RPC)
{
  "method": "swarm_request_password_reset",
  "params": { "email": "user@example.com" }
}
```

- 无论邮箱是否存在，统一返回成功（防邮箱枚举）
- 若邮箱匹配到用户：生成 `reset_token`（blake3 随机 32 字节，有效期 15 分钟），存储到 `auth/reset/<token_hash>`
- 若邮箱不匹配任何用户：同样生成随机 token 并立即 discard（常量时间，防邮箱枚举时序差）
- 通过邮件服务发送重置链接：`https://<host>/auth/reset?token=<reset_token>`
- 限速：每邮箱 1 次/5 分钟

**Step 2: 确认重置**

```
POST /mcp (JSON-RPC) 或 GET /auth/reset?token=xxx 浏览器
{
  "method": "swarm_confirm_password_reset",
  "params": {
    "reset_token": "abc123...",
    "new_csr": "base64:SWARM-CSR-V1...",
    "certificate_profile": "regular_device",
    "device_label": "replacement laptop",
    "new_password": "new-recovery-password"        // 可选，更新 recovery password
  }
}
```

- 验证 token：未过期、未使用、匹配 FDB `auth/reset/` 记录
- 验证 `new_csr` 签名与 requested profile/scope，签发新的应用层证书 bundle
- 若提供 `new_password`：argon2id hash 新 recovery password → 更新 FDB
- 标记 token 已消费，同时吊销该用户所有现有 refresh token；是否吊销旧证书由用户选择，默认保留未撤销证书
- 若恢复原因是“所有证书丢失”，UI 应提示用户检查并吊销不可访问设备对应证书

### 11.3 管理员生成恢复链接

管理员可为无法使用邮箱恢复、离线部署、AI agent 凭据丢失或用户丢失所有证书的账号生成一次性恢复链接。该能力只创建恢复入口，不允许管理员读取、指定或保存用户的新私钥或 recovery password。

```
POST /mcp (JSON-RPC)
{
  "method": "swarm_admin_create_password_reset",
  "params": {
    "username": "kagurazaka",
    "reason": "user requested recovery via support ticket"
  }
}

Response:
{
  "created": true,
  "expires_in_seconds": 900
}
```

**权限与安全合同**：
- 调用者必须持有 admin scope；非 admin 返回 `forbidden`
- **管理员恢复链接不得直接返回给管理员**。`swarm_admin_create_password_reset` 返回 `{created: true}`，实际 `reset_url` 发送到用户已验证的邮箱或 out-of-band 用户验证通道。离线部署需双 admin + 用户短码/签名 challenge
- 只接受 `login_username`，不按 email 查询，避免 admin recovery 路径扩大邮箱枚举面
- 生成的 `reset_token` 与邮箱恢复使用同一 `auth/reset/<token_hash>` 存储和确认流程
- token 有效期 15 分钟、一次性使用；确认恢复后签发新证书并吊销该用户所有现有 refresh token
- 返回值只展示一次，服务端只存 token hash；管理端日志必须脱敏 `reset_url`
- 每次生成写入 `auth/admin_audit/<event_id>`：`admin_id, target_player_id, action, reason, created_at, expires_at`
- 管理员不得直接设置用户密码、生成用户私钥或代替用户签署 CSR；最终 `new_csr` 必须由持有新私钥的一方提交
- 对 `deleted(grace)` 账号拒绝生成恢复链接；应使用账号恢复流程
- **双人授权**：生成恢复链接属于敏感管理操作，需要两个不同 admin 的确认——第一个 admin 发起请求，第二个 admin 在 5 分钟内确认。单 admin 无法独立完成恢复链接生成。审计日志记录双方 admin_id

### 11.4 Passkey 恢复

Passkey 可作为邮箱和管理员之外的恢复因子。它不替代应用层证书：passkey 只用于证明用户可恢复账号，恢复成功后仍必须提交新的 CSR 并由服务器签发新的应用层证书。

```
POST /mcp (JSON-RPC)
{
  "method": "swarm_recover_with_passkey",
  "params": {
    "passkey_assertion": "base64:webauthn-assertion...",
    "new_csr": "base64:SWARM-CSR-V1...",
    "certificate_profile": "regular_device",
    "device_label": "new phone"
  }
}
```

**安全合同**：
- Passkey 绑定需要已登录证书或恢复链接确认，写入 `auth/passkeys/<player_id>/<credential_id>`
- Passkey assertion 必须绑定 `server_id`、`world_id`、challenge、origin/rp_id，防跨站重放
- Passkey 恢复只能签发 `regular_device` 或 `temporary_device` profile；不得直接签发 `AdminCertificate`
- 用户丢失所有证书但仍持有 passkey 时，可用 passkey 重新提交 CSR；无需邮箱或管理员介入
- 用户应可列出和吊销 passkey；丢失设备时吊销对应 passkey 与证书

---

## 12. 邮箱绑定

邮箱是可选的，但绑定后解锁证书恢复功能。

```
POST /mcp (JSON-RPC)
{
  "method": "swarm_bind_email",
  "params": { "email": "user@example.com" }
}
```

- 需要已登录（session/certificate）
- 发送验证邮件到目标邮箱（含 verification token，24h 有效）
- 用户点击链接验证后，FDB `auth/users/<username>` 更新 `email_verified` + `email`
- 更换邮箱：重复上述流程，新邮箱验证通过后替换旧邮箱
- 一个邮箱可被多个账号绑定（不要求唯一）
- `email` 不用于登录——登录始终用 `login_username`
- 多账号绑定同一邮箱时，证书恢复邮件列出所有关联账号的 `display_name` / `login_username`，每个账号独立的 recovery 链接

注册时可选的 `email`：

```
swarm_submit_csr 参数新增 email?: string
若提供 email，证书签发成功后自动发送验证邮件
未验证的 email 不能用于证书恢复
```

---

## 13. 账号删除与恢复

### 13.1 删除流程

```
POST /mcp (JSON-RPC)
{
  "method": "swarm_delete_account",
  "params": { "password": "current-password" }
}
```

- 验证密码（与登录同等）
- 确认后执行：

```
1. 标记 FDB auth/users/<username>.deleted_at = now
2. 吊销所有 refresh token + certificate
3. 玩家资产处置策略（参见 world.toml 配置）：
   - "abandon":  所有 drone/建筑/资源留在世界中，无人控制
   - "recycle":  按比例退还资源到最近 Spawn（默认 50%）
   - "transfer": 转移到指定 player_id（需该玩家 Ed25519 签名确认）
4. **in-transit 资源处置**：
   - 进行中的 cargo transfer（`cargo_in_transit`）：立即取消，资源退回源 depot；若无源 depot 则进入世界丢弃池
   - 未完成的 depot transaction：回滚，depot 状态恢复至操作前
   - 以上操作与资产处置（步骤 3）在同一 tick 原子执行
5. 世界状态变更在下一 tick 生效（引擎侧处理）
```

- 删除后 30 天内可恢复（grace period），30 天后永久清除
- `login_username` 在永久清除后释放（可被重新注册）

### 13.2 Grace Period 状态机

删除后账号进入 `deleted(grace)` 状态，行为如下：

| 操作 | deleted(grace) 行为 |
|------|--------------------|
| 证书续签 / CSR 提交 | 拒绝，返回 `account_deleted`（提示可恢复） |
| `swarm_token_refresh` | 拒绝 |
| 邮箱/Passkey 证书恢复 | 拒绝（账号标记删除） |
| `swarm_restore_account` | 接受 → 清除 deleted_at → 恢复登录 |
| `swarm_cancel_account_deletion` | 同 restore（别名） |
| 30 天后 | `deleted_at` 满 30 天 → 永久清除 FDB 记录 + 释放 username |

### 13.3 恢复账号

```
POST /mcp (JSON-RPC)
{
  "method": "swarm_restore_account",
  "params": {
    "username": "kagurazaka",
    "password": "current-password"
  }
}
```

- 验证密码（与删除时同等）→ 清除 `deleted_at` → 账号恢复
- 恢复后需重新登录（旧 session/certificate 已在删除时吊销）
- 返回 `CertificateBundle`（签发恢复后的本地证书链）
- 邮件恢复：若账号绑定了已验证邮箱，可发送恢复链接到邮箱；人类用户点击链接后在浏览器中完成恢复

### 13.4 Transfer 资产处置

当 `asset_disposition = "transfer"` 时：

```
POST /mcp (JSON-RPC)
{
  "method": "swarm_delete_account",
  "params": {
    "password": "current-password",
    "transfer_target": 42,                          // 接收方 player_id
    "transfer_acceptance": {                        // 接收方 Ed25519 签名确认
      "signer_player_id": 42,
      "deleting_player_id": "<derived from auth>",
      "asset_summary": "12 drones, 5 buildings, 3500 resources",
      "timestamp": 1718000000,
      "signature": "ed25519:base64..."
    }
  }
}
```

- 接收方必须在删除操作前提供 Ed25519 签名确认（包含删除者 player_id + 资产摘要 + 时间戳）
- 服务端验证签名、检查接收方 player_id 存在且未删除、检查时间戳在 5 分钟内
- Transfer 一旦执行不可逆——接收方获得全部资产
- 若接收方拒绝确认、签名无效或超时：删除失败，返回 `transfer_rejected`

---

## 14. Token 与会话安全

### 14.1 Token 生命周期

| Token | TTL | Rotation | 存储位置 |
|-------|-----|----------|---------|
| `ClientAuthCertificate` | 15 min–180 days | `swarm_renew_certificate` 续签 | 每设备本地 / agent store |
| `CodeSigningCertificate` | 30–180 days（默认 30d，world.toml 可配） | CSR renewal | 每设备本地 / agent store |
| `AdminCertificate` | 15 min–1h | 重新签发 | 管理员设备 / hardware key |
| `refresh_token` | 30 days | 每次使用后轮换 | FDB `auth/sessions/`（Web 兼容层） |

**Refresh token rotation**：
```
使用 refresh_token → 旧 token 标记 rotated → 签发新 token → 返回新 token
旧 token 在 rotation 后 60s 内仍可被接受一次（grace period，防竞态）。受信设备（已持有有效 ClientAuthCertificate）的 grace 缩短至 10s；非受信设备（仅 refresh_token）保持 60s。
grace 使用必须原子消费：FDB 中设置 grace_consumed_at，避免重复使用
异常 IP/UA 使用 grace 时触发 session family revoke（该用户所有 session 吊销）
```

### 14.2 会话绑定

每个 session 绑定 `(player_id, client_public_key)`。`swarm_token_refresh` / `swarm_auth_revoke` 需要匹配的 `client_public_key`。

### 14.3 浏览器存储策略

- **refresh_token**：使用 **HttpOnly Secure SameSite=Strict cookie**，禁止 JavaScript 访问
- **私钥**：使用 **WebCrypto non-extractable key**（`CryptoKey` 不可导出）
- **certificate**：使用 **IndexedDB** 存储（仅作缓存，不构成独立认证根——所有认证请求仍需完成签名绑定）
- 防护：严格 CSP 防止 XSS（`script-src 'self'` + nonce/hash）；`Trusted Types` 策略
- CSRF：SameSite=Strict + CSRF token 双重防护
- 传输：仅 HTTPS
- 日志脱敏：`refresh_token` 不出现在 URL query、Referrer、服务端访问日志中
- **禁止**：`localStorage` 用于存储任何长期 bearer material（token、certificate、私钥引用）。若被 XSS 读取，refresh_token 可被滥用并触发 session family 风险。对于可编程 MMO，玩家原创字符串、回放、调试、文档渲染等都是长期 XSS 攻击面。

### 14.4 AI Agent 凭据存储

- 推荐：文件（0600 权限）、secret store、环境变量
- 禁止：硬编码在代码仓库、公开日志、聊天上下文
- 证书过期后必须用 `swarm_renew_certificate` 续签；私钥丢失则走恢复链接重新提交 CSR

### 14.5 应用层证书权威模型

Swarm 认证系统的**唯一权威凭证是应用层证书链 + 用户私钥签名**。所有 bearer token 仅是 Web session 兼容层，不构成独立信任根：

| 凭证 | 角色 | 权威来源 |
|------|------|---------|
| `ClientAuthCertificate` | 普通认证请求凭证 | Server Intermediate CA 签名，链到 Server Root CA |
| `CodeSigningCertificate` | WASM/module 部署签名凭证 | Server Intermediate CA 签名，usage 限定为 code_signing |
| `AdminCertificate` | 管理操作凭证 | Server Intermediate CA 签名，admin scope + 短 TTL |
| `refresh_token` | Web session 兼容续签材料 | 服务端随机生成，FDB 存储，每次使用后旋转 |
| JWT (`access_token`) | 可选 Web/Gateway 传递格式 | 由 `refresh_token` 兑换，仅限 Web 兼容路径 |

**约束**：
- JWT/access_token 不是独立的认证根——它必须由应用层证书或有效 `refresh_token` 兑换，不可单独用于身份证明
- 应用层证书包含 `player_id, public_key, usage, scopes, audience("swarm-aud-v1:<transport>:<server_id>:<world_id>:<player_id>"), issued_at, expires_at, issuer_chain`
- MCP/HTTP/WebSocket 安全：请求必须携带 `Swarm-Certificate-Chain` 与 canonical request 签名；不依赖 mTLS 或 TLS client certificate
- HTTP 不安全传输允许认证与完整性校验，但不提供机密性、流量隐藏或服务端域名真实性
- Token `aud` 字段绑定 `{gateway_origin, world_id, client_type}` 三元组，防止跨环境 token 重放

---

## 15. 联邦身份

Swarm 的世界形成**联邦宇宙**——玩家在一个世界注册的身份可以被其他世界识别和接受，无需重复注册。

### 15.1 信任模型

每个世界有自己的 Server Root CA 与 Server Intermediate CA。世界可以通过配置信任其他世界的 Swarm Root CA fingerprint：

```toml
# world.toml
[auth.federation]
# 信任的远程世界列表。root_fingerprint 必须由管理员显式配置，不自动发现。
trusted_roots = [
  { server_id = "swarm-alpha", root_fingerprint = "blake3:...", trust = "login" },
  { server_id = "swarm-beta",  root_fingerprint = "blake3:...", trust = "login+code" },
]

[auth.federation.default_policy]
allow_login = true
allow_code_signing = false
allow_admin = false
require_local_certificate = true
revocation_fallback = "reject_for_code_and_login"

> **R27 ML-10**: 默认值 `reject_for_code_and_login`，CRL 过期时同时拒绝 login 和 code signing。对于确实需要可用性优先的低风险世界，可改为 `reject_for_code`（仅拒绝 code signing，仍允许 login）并标注风险。
```

信任级别：
- `login`：只允许远端身份作为 bootstrap proof，目标服重新签发本地 `ClientAuthCertificate`
- `login+code`：允许用户基于远端身份申请本地 `CodeSigningCertificate`，但仍由目标服 CA 签发
- `observe`：只允许查看公开资料/回放，不创建本地玩家
- `admin`：默认禁止；跨服 admin 不自动信任，必须由目标服本地管理员重新授权

### 15.2 跨世界登录流程

玩家持 World A 的证书来 World B：

```
1. 客户端发送 World A 的 FederationCertificate 或 ClientAuthCertificate 链
2. World B 查找证书链 Root CA fingerprint 是否在 trusted_roots 列表中
3. 客户端用 World A 证书对应私钥签名 World B 的 federation challenge，防止证书复制重放
4. World B 验证证书链、usage、scope、audience、challenge 签名与撤销状态
5. 映射身份：player_id_local = blake3("federated:" + remote_server_id + ":" + remote_player_id) → u64
6. World B 创建/更新本地 federated identity 记录
7. World B 用本地 Server Intermediate CA 签发本地 ClientAuthCertificate（绑定本地 player_id）
8. 若 trust=login+code 且本地策略允许，用户可提交 CSR 申请本地 CodeSigningCertificate
9. 返回 CertificateBundle（包含本地证书链 + Web session 兼容材料）
```

### 15.2a 联邦 CRL 同步

每个信任的远程世界定期同步其 CRL：

| 维度 | 决策 |
|------|------|
| 同步间隔 | 60s（可配置） |
| 获取端点 | `GET https://<remote_host>/auth/crl/delta?since=<timestamp>` |
| 本地缓存 | Engine 内 LRU，与本地 CRL 共用缓存空间 |
| 获取失败 | 使用上次成功同步的 CRL 快照；`revocation_fallback` 策略生效 |
| 首次同步 | 启动时全量获取，阻塞至成功或超时（30s） |
| 增量更新 | `since` 参数返回该时间点之后的新吊销项 |

`revocation_fallback` 策略：

| 值 | 行为 |
|----|------|
| `reject_for_code` | 若 CRL 超过 2× 同步间隔未更新，拒绝该远程世界的 `CodeSigningCertificate`；仍允许 login |
| `reject_for_code_and_login` | CRL 过期则拒绝该远程世界的 `CodeSigningCertificate` **和**所有 login 请求 |
| `reject_all` | CRL 过期则拒绝该远程世界的所有证书 |
| `allow_with_warning` | 允许但有审计日志告警（仅用于低风险世界） |

联邦 CRL 同步独立于本地 Engine tick 循环，不阻塞热路径。

### 15.3 MCP 工具

| Tool | 参数 | 返回 | 说明 |
|------|------|------|------|
| `swarm_federated_login` | `remote_certificate_chain`, `challenge_signature`, `new_csr?` | `CertificateBundle` | 用外部世界证书作为 bootstrap proof，在本地重签证书 |

```
POST /mcp (JSON-RPC)
{
  "method": "swarm_federated_login",
  "params": {
    "remote_certificate_chain": "base64:leaf+intermediate...",
    "challenge_id": "fed_challenge_abc",
    "challenge_signature": "ed25519:base64...",
    "new_csr": "base64:SWARM-CSR-V1..."      // 可选：申请本地 CodeSigningCertificate 或新设备证书
  }
}

Response: CertificateBundle { player_id (本地), client_auth_certificate, code_signing_certificate?, issuer_chain, web_session? }
```

### 15.4 身份映射

联邦身份的 `player_id` 按世界隔离：

```
本地注册:
  "local" + ":" + username → blake3 → u64 → player_id (本地命名空间)

联邦:
  "federated" + ":" + world_id + ":" + original_player_id → blake3 → u64 → player_id
```

不同世界的同一联邦玩家拥有**独立的本地 player_id 和资产**。联邦身份只用于认证 bootstrap——不共享游戏状态、不共享模块、不共享排名。这与 [Swarm 联邦宇宙哲学](README.md#11-核心理念) 一致：身份可跨世界，但游戏状态按世界隔离。

### 15.5 本地重签与权限边界

远端证书不直接授予本地操作权限：

- 远端 `ClientAuthCertificate` / `FederationCertificate` 只作为 bootstrap proof
- 目标服始终签发本地 `ClientAuthCertificate` 后才允许本地 MCP/HTTP/WebSocket 请求
- 目标服默认不接受远端 `CodeSigningCertificate`；部署 WASM 必须使用目标服签发的 `CodeSigningCertificate`
- 目标服默认不接受远端 `AdminCertificate`；管理员权限必须由目标服本地管理员重新授权
- 目标服可随时吊销 federated local identity 或本地证书，不依赖来源服

### 15.6 撤销传播

- 本地证书撤销仅影响本地世界
- 外部证书撤销：World B 定期向 World A 查询吊销列表（`GET /auth/revocations?since=<timestamp>`），或在验证时实时查询
- 若外部世界不可达：使用本地缓存的吊销列表，在 `revocation_cache_stale_seconds`（默认 3600 秒）内视为有效；超过 stale 上限后行为由 `federation.revocation_fallback` 配置：
  - `"reject_for_code"`（默认）：普通 login 可短期接受，申请/使用本地 `CodeSigningCertificate` 必须拒绝
  - `"accept_login"`：可用性优先，仅接受登录，记录 WARN；不接受 code/admin
  - `"reject_all"`：安全优先，拒绝联邦登录直至远端恢复
- 运维告警：stale 超时后记录 WARN 日志，触发监控告警

---

## 16. 前端变更

### 16.1 `LoginButton.tsx` 扩展现有组件

```
┌──────────────────────────────────────────┐
│  Player authentication                   │
│  ┌──────────────────────────────────────┐│
│  │ ○ Create / recover with CSR         ││
│  │ ○ Recover with passkey/email/admin  ││
│  └──────────────────────────────────────┘│
│  ── or ──                                │
│  ┌──────────────────────────────────────┐│
│  │ New account / new device:            ││
│  │ Username:      [______________]      ││
│  │ Device label:  [______________]      ││
│  │ Profile:       (regular/temporary)   ││
│  │ [ ▲ Generate key + Submit CSR ]      ││
│  │              (~1-3s PoW proof)       ││
│  ├──────────────────────────────────────┤│
│  │ Existing account recovery:           ││
│  │ [ Passkey ] [ Email link ] [ Admin ] ││
│  └──────────────────────────────────────┘│
└──────────────────────────────────────────┘
```

### 16.2 PoW 前端实现

- 必须运行在 **Web Worker** 中（禁止主线程 `while(true)` 阻塞）
- 显示进度：`已尝试 N / 预计 M 次`（基于 difficulty_bits 计算期望值）
- 超过 8 秒显示 "Slow device? You can wait or [Cancel]"
- 取消后自动重新获取 challenge + 重试
- `difficulty_bits` 从服务端 challenge 响应获取，不做客户端假设

### 16.3 `provider` 字段扩展

```typescript
export type AuthProvider = 'local' | 'passkey' | 'email_recovery' | 'admin_recovery' | 'federated';
```

---

## 17. 安全考量

### 17.1 威胁模型

| 威胁 | 缓解措施 |
|------|---------|
| 批量注册 / DDoS | PoW challenge-response（difficulty_bits=24, ~150ms Rust / ~1.5s WASM） |
| PoW challenge 替换/降级 | 服务端从 FDB 读取权威 challenge+difficulty，register 不接收客户端 challenge 字段 |
| PoW challenge 重放 | 一次性消费（FDB 原子标记 consumed），TTL 5min |
| PoW challenge DoS | challenge 申请 IP 限速 10/min；FDB 存储 TTL 自动清理 |
| 恢复密码暴力破解 | argon2id (19MiB, 2 iters) + per-account 失败计数 + 递增延迟 + 短期锁定 |
| 分布式低速恢复尝试 | per-account 失败计数（跨 IP）；可选 recovery PoW 触发 |
| Dummy argon2id DoS 放大 | 恢复凭据校验 per-IP 限流在 argon2id 之前拦截；per-account lockout |
| 用户名枚举 | 恢复凭据失败统一 `invalid_credentials`；不存在用户执行 dummy argon2id；用户名注册状态不公开 |
| 响应时间侧信道 | dummy argon2id 消除存在/不存在用户的时间差 |
| CSR / 恢复传输 | 应用层证书 pinning；敏感 payload 加密给服务器应用层证书 public key |
| FDB 泄露 | recovery password 仅存储 argon2id hash；所有 value 带 schema_version |
| 时序攻击 | `verify_password` 使用 argon2 crate 的常量时间比较 |
| Chat log 泄露凭据 | Agent 代理注册返回一次性 handoff code，非裸 refresh_token 或私钥 |
| 凭据丢失 | 已验证邮箱、passkey 或管理员恢复链接 + 新 CSR；AI agent 持久化证书链和私钥引用 |
| 恢复 token 泄露 | reset_token 15min TTL + 一次性消费 + 吊销所有现有 Web session |
| 账号删除误操作 | 密码确认 + 30 天 grace period 可恢复 |
| 邮箱验证 token 劫持 | HTTPS + verification token 24h TTL + 一次性消费 |

### 17.2 不做的

- ❌ TOTP 作为默认要求 — 可作为后续高安全 profile
- ❌ IP 黑名单
- ❌ 密码明文日志

---

## 18. 实现范围

### 18.1 Phase 1

| 组件 | 文件 | 变更 |
|------|------|------|
| Auth Service | `src/auth/mod.rs` (新) | challenge 生成/验证、CSR 审核、证书签发/续签/吊销、恢复流程、账号删除、FDB 读写 |
| Auth Service | `src/auth/challenge.rs` (新) | PoW 生成与验证 |
| Auth Service | `src/auth/cert.rs` (新) | Server Intermediate CA、应用层证书链、CRL 窗口、Root fingerprint pinning |
| Auth Service | `src/auth/session.rs` (新) | refresh token rotation、Web session 兼容层 |
| Auth Service | `src/auth/identity.rs` (新) | IdentityKey → PlayerId、三层身份模型、联邦 identity 映射 |
| Auth Service | `src/auth/email.rs` (新) | 邮箱验证 token、证书恢复 token、邮件发送 |
| Auth Service | `src/auth/passkey.rs` (新) | passkey 绑定与恢复 |
| Engine | `src/tick.rs` / `src/mcp.rs` | 注册 auth MCP tools（转发到 auth domain） |
| Engine | `Cargo.toml` | 添加 `argon2` / Ed25519 / WebAuthn 依赖 |
| Gateway | `cert_auth.go` (新) | CSR / certificate / recovery REST 端点代理 |
| Gateway | `server.go` | 注册路由 |
| Frontend | `LoginButton.tsx` | CSR submit / device profile / passkey recovery UI + Web Worker PoW |

### 18.2 文档同步

- `design/auth.md`（本文档）
- `design/interface.md` MCP 工具表（已更新）
- `specs/security/03-mcp-security.md` 补充 Auth domain 边界

---

## 19. 测试策略

### 单元测试

```
# Identity
test identity_login_username_rejects_invalid_chars
test identity_login_username_normalizes_lowercase
test identity_player_id_is_deterministic
test identity_player_id_collision_detection
test identity_display_name_defaults_to_username

# Password
test password_rejects_too_short
test password_rejects_no_digit
test password_rejects_matches_username
test password_rejects_common_weak
test password_accepts_ai_random_hex_32
test hash_password_produces_valid_argon2id_with_explicit_params
test verify_password_accepts_correct
test verify_password_rejects_wrong
test verify_password_constant_time

# PoW
test pow_challenge_generates_valid_blake3_challenge
test pow_verify_accepts_correct_nonce
test pow_verify_rejects_wrong_nonce
test pow_verify_bit_boundary_exact
test pow_verify_bit_boundary_one_off
test pow_challenge_expires_after_ttl
test pow_registration_uses_server_authoritative_challenge
test pow_registration_rejects_client_supplied_challenge
test pow_registration_rejects_client_supplied_difficulty

# Register
test register_creates_fdb_entry_in_auth_subspace
test register_rejects_duplicate_username
test register_rejects_invalid_pow
test register_rejects_expired_challenge
test register_consumes_challenge_even_on_username_taken
test register_username_visibility_public_skips_pow_on_taken
test register_username_visibility_private_consumes_pow_on_taken
test register_sets_display_name_from_username

# Profile
test update_profile_changes_display_name
test update_profile_rejects_empty_display_name
test update_profile_requires_authentication
test password_hash_done_outside_fdb_transaction

# Password management
test change_password_succeeds_with_correct_old_password
test change_password_rejects_wrong_old_password
test change_password_enforces_policy_on_new_password
test change_password_does_not_invalidate_existing_session
test request_password_reset_always_returns_success
test request_password_reset_rate_limited_per_email
test confirm_password_reset_with_valid_token
test confirm_password_reset_rejects_expired_token
test confirm_password_reset_rejects_consumed_token
test confirm_password_reset_revokes_existing_sessions
test confirm_password_reset_returns_login_result

# Email
test bind_email_sends_verification
test bind_email_verification_updates_user_record
test bind_email_replaces_old_email
test register_with_email_creates_unverified_email
test unverified_email_cannot_reset_password

# Account deletion
test delete_account_verifies_password
test delete_account_marks_deleted_at
test delete_account_revokes_sessions
test delete_account_grace_period_allows_recovery
test delete_account_permanent_after_grace_period
test delete_account_releases_username_after_permanent

# Federation
test federated_login_accepts_trusted_issuer_certificate
test federated_login_rejects_untrusted_issuer
test federated_login_rejects_expired_foreign_certificate
test federated_login_maps_deterministic_local_player_id
test federated_login_reissues_local_certificate
test federated_identity_isolated_assets_per_world
test federation_revocation_propagation

# Login
test login_returns_certificate_on_success
test login_rejects_wrong_password
test login_rejects_nonexistent_user_same_timing_as_wrong_password
test login_dummy_argon2id_for_nonexistent_user
test login_fail_count_increments
test login_fail_count_resets_on_success
test login_locks_after_consecutive_failures
test login_pow_required_after_trigger
test login_pow_config_disabled_skips_pow
test login_rate_limited_per_username

# Session
test refresh_token_rotates_on_use
test old_refresh_token_accepted_in_grace_period
test rotated_token_rejected_after_grace_period
test session_bound_to_client_public_key

# AI Agent
test ai_agent_self_register_with_random_credentials
test agent_proxy_handoff_token_generation
```

### 集成测试

```rust
#[test]
fn local_auth_full_lifecycle() {
    let auth = AuthService::new_for_tests();
    let engine = McpServer::new_for_tests();

    // Register
    let challenge = auth.create_challenge().unwrap();
    let nonce = solve_pow(&challenge.challenge, challenge.difficulty_bits);
    let result = auth.register(RegisterParams {
        login_username: "testuser".into(),
        password: "hunter2pass".into(),
        challenge_id: challenge.challenge_id,
        nonce,
        client_public_key: pubkey.clone(),
    }).expect("registration");

    // Certificate valid for deploy
    engine.verify_certificate_for_player(&result.certificate, result.player_id).unwrap();

    // Login
    let login = auth.login("testuser", "hunter2pass", &pubkey).expect("login");
    assert_eq!(login.player_id, result.player_id);

    // Refresh rotation
    let old_token = login.session.refresh_token.clone();
    let refreshed = auth.token_refresh(&old_token, &pubkey).expect("refresh");
    assert_ne!(refreshed.session.refresh_token, old_token);

    // Revoke
    auth.revoke(RevokeParams { refresh_token: Some(refreshed.session.refresh_token), .. }).unwrap();

    // Password change
    auth.change_password("testuser", "hunter2pass", "newHunter3pass", &pubkey)
        .expect("password change");
    let login2 = auth.login("testuser", "newHunter3pass", &pubkey).expect("login with new password");

    // Email + password reset
    auth.bind_email("testuser", "user@example.com", &pubkey).expect("bind email");
    let reset = auth.request_password_reset("user@example.com").expect("request reset");
    let recovered = auth.confirm_password_reset(&reset.token, "recoveredPass1", &pubkey)
        .expect("reset + auto-login");

    // Account deletion
    auth.delete_account("testuser", "recoveredPass1", &pubkey).expect("delete");
    assert!(auth.is_deleted("testuser"));
}
```

---

## 附录 A: PoW 客户端实现（Python）

```python
import blake3
import secrets
import time

def solve_pow(challenge: str, difficulty_bits: int) -> str:
    target_bytes = difficulty_bits // 8
    target_bits = difficulty_bits % 8
    nonce = 0
    while True:
        h = blake3.blake3(f"{challenge}{nonce}".encode()).digest()
        if h[:target_bytes] != b'\x00' * target_bytes:
            nonce += 1; continue
        if target_bits > 0:
            mask = 0xFF << (8 - target_bits)
            if (h[target_bytes] & mask) != 0:
                nonce += 1; continue
        return str(nonce)

def self_register(mcp_endpoint: str):
    keypair = load_or_generate_ed25519_key()
    ch = mcp_call("swarm_register_challenge", {})
    nonce = solve_pow(ch["challenge"], ch["difficulty_bits"])
    csr = build_swarm_csr(
        server_id=fetch_server_trust()["server_id"],
        world_id="default",
        username=f"ai-bot-{secrets.token_hex(8)}",
        public_key=keypair.public_key,
        requested_usages=["client_auth", "code_signing"],
        requested_scopes=["swarm:read", "swarm:deploy"],
        challenge_id=ch["challenge_id"],
        challenge=ch["challenge"],
    )
    result = mcp_call("swarm_submit_csr", {
        "username": csr.username,
        "csr": csr.to_base64(),
        "challenge_id": ch["challenge_id"],
        "nonce": nonce,
        "csr_signature": keypair.sign(csr.canonical_payload()),
    })
    # Persist certificate chain and private-key reference immediately
    save_credentials(result)
```

## 附录 B: PoW 前端实现（Web Worker）

```javascript
// main.js
const worker = new Worker('/js/pow-worker.js');
worker.onmessage = (e) => {
  if (e.data.type === 'progress') {
    updateProgressBar(e.data.ratio);
  } else if (e.data.type === 'done') {
    submitRegistration(e.data.nonce);
  }
};
worker.postMessage({ challenge, difficultyBits });

// pow-worker.js
importScripts('/js/blake3-wasm.js');
self.onmessage = (e) => {
  const { challenge, difficultyBits } = e.data;
  const targetBytes = Math.floor(difficultyBits / 8);
  const targetBits = difficultyBits % 8;
  let nonce = 0n;
  let lastReport = Date.now();
  while (true) {
    const hash = blake3.hash(new TextEncoder().encode(challenge + nonce.toString()));
    if (hash.slice(0, targetBytes).every(b => b === 0)) {
      if (targetBits === 0 || (hash[targetBytes] & (0xFF << (8 - targetBits))) === 0) {
        self.postMessage({ type: 'done', nonce: nonce.toString() });
        return;
      }
    }
    nonce++;
    if (Date.now() - lastReport > 100) {
      self.postMessage({ type: 'progress', ratio: Number(nonce) / (1 << difficultyBits) });
      lastReport = Date.now();
    }
  }
};
```

## 附录 C: 配置参考（world.toml `[auth]` 段）

```toml
[auth]
# 用户名可见性
username_visibility = "private"     # "public" 或 "private"

# PoW 难度（注册专用，登录 PoW 见 login_pow）
register_pow_difficulty_bits = 24

# 登录限速
login_max_attempts_per_window = 5
login_fail_window_seconds = 300
login_lockout_seconds = 300
login_dummy_argon2id_enabled = true

# 登录 PoW（可配置开关）
[auth.login_pow]
enabled = false
difficulty_bits = 16
trigger_fail_count = 5
trigger_window_seconds = 300

# Challenge
challenge_ttl_seconds = 300
challenge_request_rate_limit_per_ip_per_minute = 10

# Session
refresh_token_ttl_days = 30
refresh_token_rotation_grace_seconds = 60
access_token_ttl_seconds = 900
certificate_ttl_seconds = 86400
```
