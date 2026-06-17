# Swarm 用户认证

> 统一的用户认证系统：本地注册/登录、OAuth2 联合登录、联邦跨世界身份。
> **AI agent 可通过 MCP 自注册，人类玩家可通过 agent 代理注册。**

## 1. 动机

当前 Swarm 仅支持 OAuth2 联合登录（GitHub / Google）。这排除了以下用户群：

- 不愿绑定第三方账号的玩家（隐私）
- 没有 GitHub/Google 账号的玩家（低门槛体验）
- 内网/离线部署场景（无外部 OAuth2 provider 可用）
- 自动化测试与 CI 环境（无需配置 OAuth2 密钥）
- **AI player 自注册** — AI agent 没有浏览器，无法完成 OAuth2 重定向流程
- **Agent 代理注册** — 人类通过 AI agent 代为注册，无需手动操作前端

**目标**：提供与 OAuth2 并列的本地认证路径。两者共享相同的 Ed25519 证书系统和 session 模型。

---

## 2. 设计原则

| 原则 | 说明 |
|------|------|
| **Auth 独立控制面** | 注册、登录、PoW、密码哈希、限速、token 生命周期属于独立 Auth domain。Engine 只消费已签发身份/证书，不持有密码库 |
| **并列共存** | 本地认证与 OAuth2 认证处于同等地位。前端显式提供切换入口，MCP 统一暴露 |
| **同一证书模型** | 本地用户登录后获得与 OAuth2 用户完全相同的 Ed25519 `PlayerCertificate` + `refresh_token`，后续流程无差异 |
| **确定性 player_id** | `player_id = blake3("local:" + login_username_lowercase)` — 与 `oauth_player_id()` 同模式 |
| **PoW 防滥用** | 注册需要完成工作量证明（PoW challenge）。Login PoW 可配置（开关 + 难度） |
| **密码自管理** | AI agent 可自行生成密码（自动生成强随机密码），与人类玩家密码同等对待 |

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
│  │  ┌────────────────┐  ┌─────────────────────────────┐ │ │
│  │  │ OAuth2 handler  │  │ Local Auth handler (新)      │ │ │
│  │  │ (已有)          │  │ /auth/register/challenge    │ │ │
│  │  │                │  │ /auth/register               │ │ │
│  │  │                │  │ /auth/login                  │ │ │
│  │  └────────────────┘  └─────────────┬───────────────┘ │ │
│  └────────────────────────────────────┼─────────────────┘ │
│                                       │                    │
│  ┌────────────────────────────────────▼─────────────────┐ │
│  │              Auth Service / Domain                     │ │
│  │  src/auth/ (Engine 内或独立服务)                        │ │
│  │  ┌──────────────────┐  ┌──────────────────────────┐  │ │
│  │  │ Registration     │  │ Session Management        │  │ │
│  │  │ - challenge 生成  │  │ - refresh token 存储      │  │ │
│  │  │ - PoW 验证       │  │ - revocation              │  │ │
│  │  │ - argon2id 哈希  │  │ - token rotation          │  │ │
│  │  │ - 用户名/密码校验 │  │ - login fail counting     │  │ │
│  │  └──────────────────┘  └──────────────────────────┘  │ │
│  └──────────────────────────┬───────────────────────────┘ │
│                             │                              │
│  ┌──────────────────────────▼───────────────────────────┐ │
│  │              Engine (Game Core)                         │ │
│  │  ┌────────────────┐                                    │ │
│  │  │ CertificateIssuer│ ← Engine 只消费身份和证书          │ │
│  │  │ (Ed25519 签发)  │   不持有密码库                    │ │
│  │  │ verify_cert     │   不执行注册/登录逻辑              │ │
│  │  └────────────────┘                                    │ │
│  └──────────────────────────────────────────────────────┘ │
│                             │                              │
│  ┌──────────────────────────▼───────────────────────────┐ │
│  │              FoundationDB                               │ │
│  │  auth/users/       — 用户凭据 (password_hash, ...)     │ │
│  │  auth/identities/  — IdentityKey → PlayerId 映射       │ │
│  │  auth/challenges/  — PoW challenge 存储                │ │
│  │  auth/sessions/    — refresh token / session           │ │
│  │  auth/login_fail/  — 登录失败计数                      │ │
│  │  auth/revocations/ — 吊销列表                          │ │
│  └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**职责分离**：

| 组件 | 持有 | 不持有 |
|------|------|--------|
| Auth Service | password_hash, challenge, login 失败计数, refresh token, session | PlayerCertificate 私钥 |
| Engine | CertificateIssuer 密钥对, revoked_certificates | 密码, PoW challenge state, login 计数 |
| Gateway | 无状态代理, 路由 | 认证状态 |

---

## 4. 使用场景

### 4.1 人类玩家 — 前端注册

```
人类 → 浏览器 → LoginButton.tsx
  → "Local Register" 表单 → 输入 username + password + confirm password
  → 前端自动请求 PoW challenge → Web Worker 求解 nonce（进度条显示）
  → POST /auth/register → {username, password, challenge_id, nonce, client_public_key}
  → 获得 certificate + refresh_token → 存入 localStorage

错误恢复：
  - PoW 求解中断/超时 → 显示进度和取消按钮，自动重新获取 challenge
  - 移动端慢设备 → difficulty 可配置，前端显示预估时间
  - 注册失败 → 按错误码提示（username_taken, weak_password, invalid_pow）
```

### 4.2 AI player — MCP 自注册

```
AI agent (Claude/GPT/自主 agent) → MCP session
  → 调用 swarm_register_challenge() 获取 challenge
  → 本地求解 PoW（blake3 brute-force，按 difficulty bits）
  → 调用 swarm_register(username, password, challenge_id, nonce, pubkey)
     username  = "ai-bot-<random>" (自行生成)
     password  = random_hex(32) (64字符强随机)
  → 获得 certificate → 调用 swarm_deploy → 部署 WASM

凭据管理：
  - AI agent 必须将 (username, password, certificate, refresh_token, client_secret_key)
    立即写入持久化存储（文件 / secret store / 环境变量）
  - 建议 username 使用可恢复种子生成（而非纯随机），便于凭据丢失后重建
  - refresh_token 过期后用 swarm_login 重新获取（而非仅依赖 token_refresh）

错误恢复：
  - PoW 求解超时 → 自动重新获取 challenge + 重试
  - 凭据丢失 → 通过绑定的邮箱执行密码重置；AI agent 必须将凭据写入持久化存储
  - username_taken → 自动重试新 username
```

### 4.3 人类 — Agent 代理注册

```
人类 → "帮我在 Swarm 注册一个账号，用户名 kagurazaka，密码 hunter2pass"
  → AI agent 调用 swarm_register_challenge() + swarm_register(...)
  → 返回 handoff 信息给人类（见下方安全条款）

密码归属（明确合同）：
  - 密码必须由人类提供并被人类记住
  - Agent 不得自行生成密码代替人类
  - 弱密码时 Agent 应提示人类更换（引用密码策略）

安全交付（防聊天日志泄露）：
  - Agent 返回给人类的是「一次性 handoff code / 导入链接」，而非裸 refresh_token
  - 人类在浏览器中输入 handoff code 完成凭据导入
  - Agent 的聊天日志中不得出现长期有效的 refresh_token 或 certificate 私钥
  - 若使用「Agent 托管」模式（Agent 长期持有凭据代为操作），需人类显式授权
```

### 4.4 OAuth2 联合登录（已有）

与本地认证并列的 OAuth2 路径，支持 GitHub 和 Google：

```
人类 → 浏览器 → "GitHub Login" / "Google Login"
  → Gateway /oauth2/{provider}/login → OAuth2 provider 授权
  → Gateway /oauth2/{provider}/callback → 交换 code 获取 access_token
  → Engine 签发 PlayerCertificate (24h TTL) + refresh_token (30d)
  → 与本地认证返回完全相同的 LoginResult
```

OAuth2 用户与本地用户共享：
- 同一 `CertificateIssuer`（Ed25519 签名）
- 同一 `WebAuthSession` / `refresh_token` 模型
- 同一 `swarm_token_refresh` / `swarm_auth_revoke`

player_id 推导：`oauth_player_id(provider, subject)` — 与本地 `local_player_id(username)` 同模式。

OAuth2 provider 通过环境变量配置：`OAUTH2_GITHUB_CLIENT_ID`、`OAUTH2_GITHUB_CLIENT_SECRET` 等。Gateway 实现参见 `swarm/gateway/oauth2.go`。

---

## 5. 技术选型

### 5.1 密码哈希：argon2id

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
    Ok(Argon2::default()
        .verify_password(password.as_bytes(), &parsed)
        .is_ok())
}
```

> **实现者注意**：不得使用 `Argon2::default()`。必须显式构造 `Params` 并测试 PHC 字符串包含 `m=19456,t=2,p=1`。

### 5.2 凭据存储：FoundationDB

**Auth subspace（独立于游戏世界状态）**：

```
auth/users/<login_username>         → {password_hash, player_id, display_name, email?, email_verified, created_at, deleted_at?, schema_version: 1}
auth/identities/<provider>/<subject> → player_id  (唯一索引)
auth/challenges/<challenge_id>       → {challenge, difficulty_bits, expires_at, consumed: bool, created_at}
auth/sessions/<refresh_token_hash>   → {player_id, client_public_key, created_at, expires_at, rotated_from}
auth/login_fail/<login_username>     → {fail_count, last_fail_at, locked_until}
auth/revocations/<signature>         → {revoked_at, reason}
auth/reset/<token_hash>              → {player_id, email, created_at, expires_at, consumed: bool}
auth/email_verify/<token_hash>       → {player_id, email, created_at, expires_at, consumed: bool}
```

所有 value 带 `schema_version` 字段便于未来迁移。

**事务约束**：
- 密码哈希在事务外完成（argon2id ~100ms），FDB 事务保持短生命周期（<10ms）
- 事务冲突重试最多 3 次，返回 `McpError::conflict_retry`
- FDB key 使用 `auth/` 前缀隔离游戏世界状态

---

## 6. Identity 模型

### 6.1 三层身份

```
login_username     — 登录凭据，ASCII [a-zA-Z0-9_-]{3,32}，大小写不敏感，不可变
display_name       — 显示名称，Unicode，≤32 字符，可直接修改
player_id          — 引擎内标识，u64，确定性 hash(provider + ":" + subject)
```

- `login_username` 是 subject（认证主体），用于登录和 `player_id` 推导，不可变
- `display_name` 默认为 `login_username`，可通过 `swarm_update_profile` 修改
- `player_id` 推导：
  - 本地：`blake3("local:" + login_username_lowercase) → 取低 64 bits → u64`
  - OAuth2（已有）：`blake3(provider + ":" + subject) → u64`
  - 联邦：`blake3("federated:" + world_id + ":" + original_player_id) → u64`
- 碰撞概率：对于 10^6 用户约 2.7×10^-8，可接受
- 碰撞处理：注册时检测 FDB `auth/identities/` 唯一索引冲突，返回 `username_taken`

### 6.2 用户名规则

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

- `"public"` 模式：`swarm_register` 先检查用户名 → 若 taken 则直接返回 `username_taken`（不消费 challenge）
- `"private"` 模式：先验证 PoW → 消费 challenge → 再检查用户名。即使 taken 也消耗了 PoW，但不暴露信息
- 无论何种模式，`swarm_login` 统一返回 `invalid_credentials`（不区分不存在/密码错误），并执行 dummy argon2id

---

## 7. 密码规则

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

**AI agent 自动密码**：使用 `random_hex(32)` 生成 64 字符随机密码。

密码哈希在事务外执行（避免 FDB 事务内高延迟）。

---

## 8. PoW 工作量证明

### 8.1 算法

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

### 8.2 难度参数

| 配置 | difficulty_bits | 预期尝试次数 | Rust native | Python | Node WASM | 移动端 WASM |
|------|----------------|-------------|-------------|--------|-----------|------------|
| 开发/测试 | 16 | ~65K | <1ms | <5ms | <10ms | <20ms |
| 轻量 | 20 | ~1M | ~10ms | ~50ms | ~100ms | ~200ms |
| 标准 (默认) | **24** | **~16.7M** | **~150ms** | **~800ms** | **~1.5s** | **~3s** |
| 高安全 | 28 | ~268M | ~2.5s | ~13s | ~25s | ~50s |

> 以上为单核保守估算。实际性能受硬件、JIT/WASM 引擎、浏览器节流影响。默认 `difficulty_bits = 24`。

### 8.3 服务端绑定

**`swarm_register` 请求仅提交 `challenge_id + nonce`**，不包含客户端回传的 challenge 或 difficulty：

```json
{
  "method": "swarm_register",
  "params": {
    "username": "kagurazaka",
    "password": "correct-horse-battery-staple",
    "challenge_id": "a1b2c3d4e5f6a7b8",
    "nonce": "1784501234",
    "client_public_key": "ed25519:base64..."
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

### 8.4 Login PoW

Login PoW 通过 `auth.login_pow` 配置项控制：

```toml
[auth.login_pow]
enabled = false          # 默认关闭
difficulty_bits = 16     # 触发时的难度
trigger_fail_count = 5   # 连续失败 N 次后触发
trigger_window_seconds = 300  # 失败计数的滑动窗口
```

- 默认关闭：login 不使用 PoW，依赖 per-account 限速 + dummy argon2id
- 触发后：该 username 的 login 请求在 `trigger_window_seconds` 内要求 PoW
- 服务端动态判断：检查 `auth/login_fail/<username>` 的 fail_count
- 支持运行时开关，无需重启

---

## 9. API 设计

### 9.1 MCP 工具一览

| Tool | 参数 | 返回 | 说明 |
|------|------|------|------|
| `swarm_register_challenge` | (无) | `PoWChallenge` | 获取注册 PoW 挑战 |
| `swarm_register` | `username`, `password`, `email?`, `challenge_id`, `nonce`, `client_public_key` | `LoginResult` | 完成 PoW + 注册并登录 |
| `swarm_login` | `username`, `password`, `client_public_key` | `LoginResult` | 登录已有账号 |
| `swarm_login_challenge` | (无) | `PoWChallenge` | 获取登录 PoW 挑战（仅触发时） |
| `swarm_token_refresh` | `refresh_token`, `client_public_key` | `LoginResult` | 续签 |
| `swarm_auth_revoke` | `refresh_token` 或 `certificate` | `RevokeResult` | 吊销 session/certificate |
| `swarm_update_profile` | `display_name` | `ProfileResult` | 修改显示名称 |
| `swarm_change_password` | `old_password`, `new_password` | `SuccessResult` | 修改密码（已登录） |
| `swarm_request_password_reset` | `email` | `ResetRequestResult` | 请求密码重置（发送邮件） |
| `swarm_confirm_password_reset` | `reset_token`, `new_password` | `LoginResult` | 确认重置 + 自动登录 |
| `swarm_bind_email` | `email` | `SuccessResult` | 绑定/更换邮箱 |
| `swarm_delete_account` | `password` | `SuccessResult` | 删除账号及关联资产 |
| `swarm_federated_login` | `certificate` (外部签发) | `LoginResult` | 跨世界身份登录 |

> 注：`OAuth2LoginResult` 重命名为 `LoginResult`。

### 9.2 `swarm_register_challenge`

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

### 9.3 `swarm_register`

```
POST /mcp (JSON-RPC)
{
  "method": "swarm_register",
  "params": {
    "username": "kagurazaka",
    "password": "correct-horse-battery-staple",
    "challenge_id": "a1b2c3d4e5f6a7b8",
    "nonce": "1784501234",
    "client_public_key": "ed25519:base64..."
  }
}

Response: LoginResult {player_id, session, certificate}
```

**注意**：请求中**不包含** `challenge` 和 `difficulty` 字段 — 服务端从 FDB 读取权威值。

### 9.4 `swarm_login`

```
POST /mcp (JSON-RPC)
{
  "method": "swarm_login",
  "params": {
    "username": "kagurazaka",
    "password": "correct-horse-battery-staple",
    "client_public_key": "ed25519:base64..."
  }
}
```

**安全措施**：
- 无论用户是否存在，均执行 dummy argon2id 验证（防时序枚举）
- 连续失败 5 次后触发 login PoW（若 `auth.login_pow.enabled = true`）
- 不存在用户返回统一 `invalid_credentials`

### 9.5 错误码体系

| Code | HTTP | 说明 | 可重试 |
|------|------|------|--------|
| `invalid_credentials` | 401 | 用户名或密码错误（不区分不存在/错误） | ✅ |
| `username_taken` | 409 | 用户名已被注册 | 换用户名 |
| `weak_password` | 422 | 密码不满足强度要求 | ✅ |
| `invalid_pow` | 422 | PoW 验证失败 | ✅（重新获取 challenge） |
| `challenge_expired` | 422 | Challenge 已过期 | ✅（重新获取） |
| `challenge_consumed` | 422 | Challenge 已使用 | ✅（重新获取） |
| `challenge_not_found` | 404 | challenge_id 不存在 | ✅（重新获取） |
| `account_locked` | 423 | 登录失败次数过多，暂时锁定 | 等待解锁 |
| `login_pow_required` | 428 | 需要完成登录 PoW | ✅（求解 PoW 后重试） |
| `rate_limited` | 429 | 频率限制 | 等待 |
| `internal_error` | 500 | 服务端错误 | ✅ |

### 9.6 限速模型（独立于游戏 tick）

| 维度 | 注册 | 登录 | challenge 申请 |
|------|------|------|---------------|
| Per IP | — | — | 10/min |
| Per username | — | 10/min, 5 次失败锁 5min | — |
| 全局 | 受 PoW 保护 | 1000/min | 100/min |

注册不设 IP/username 限速 — PoW 本身就是速率控制。Challenge 申请设轻量 IP 限速防止存储 DoS。

---

## 10. 密码管理

### 10.1 密码修改（已登录）

已登录用户提供旧密码验证身份后设置新密码：

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

### 10.2 密码重置（邮箱验证）

两步流程：请求 → 邮件 → 确认。

**Step 1: 请求重置**

```
POST /mcp (JSON-RPC)
{
  "method": "swarm_request_password_reset",
  "params": { "email": "user@example.com" }
}
```

- 无论邮箱是否存在，统一返回成功（防邮箱枚举）
- 若邮箱匹配到用户：生成 `reset_token`（blake3 随机 32 字节，有效期 15 分钟），存储到 `auth/reset/<token_hash>`
- 通过邮件服务发送重置链接：`https://<host>/auth/reset?token=<reset_token>`
- 限速：每邮箱 1 次/5 分钟

**Step 2: 确认重置**

```
POST /mcp (JSON-RPC) 或 GET /auth/reset?token=xxx 浏览器
{
  "method": "swarm_confirm_password_reset",
  "params": {
    "reset_token": "abc123...",
    "new_password": "new-password-here"
  }
}
```

- 验证 token：未过期、未使用、匹配 FDB `auth/reset/` 记录
- argon2id hash 新密码 → 更新 FDB → 标记 token 已消费
- 自动登录：返回 `LoginResult`（无需用户再次输入用户名密码）
- 同时吊销该用户所有现有 refresh token（安全措施）

---

## 11. 邮箱绑定

邮箱是可选的，但绑定后解锁密码重置功能。

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

注册时可选的 `email`：

```
swarm_register 参数新增 email?: string
若提供 email，注册成功后自动发送验证邮件
未验证的 email 不能用于密码重置
```

---

## 12. 账号删除

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
   - "transfer": 转移到指定 player_id（需该玩家确认）
4. 世界状态变更在下一 tick 生效（引擎侧处理）
```

- 删除后 30 天内可恢复（grace period），30 天后永久清除
- `login_username` 在永久清除后释放（可被重新注册）

---

## 13. Token 与会话安全

### 13.1 Token 生命周期

| Token | TTL | Rotation | 存储位置 |
|-------|-----|----------|---------|
| `access_token` | 15 min | 不轮换（短寿） | 内存 |
| `refresh_token` | 30 days | 每次使用后轮换 | FDB `auth/sessions/` |
| `PlayerCertificate` | 24 hours | 每次 refresh 后重签 | 客户端 local / agent store |

**Refresh token rotation**：
```
使用 refresh_token → 旧 token 标记 rotated → 签发新 token → 返回新 token
旧 token 在 rotation 后 5min 内仍可被接受一次（grace period，防竞态）
```

### 10.2 会话绑定

每个 session 绑定 `(player_id, client_public_key)`。`swarm_token_refresh` / `swarm_auth_revoke` 需要匹配的 `client_public_key`。

### 10.3 浏览器存储策略

- 使用 `localStorage` 存储 `{refresh_token, certificate, client_public_key}`
- 防护：严格 CSP 防止 XSS（`script-src 'self'` + nonce/hash）；`Trusted Types` 策略
- CSRF：非 cookie 方案天然无 CSRF 风险
- 传输：仅 HTTPS
- 日志脱敏：`refresh_token` 不出现在 URL query、Referrer、服务端访问日志中

### 10.4 AI Agent 凭据存储

- 推荐：文件（0600 权限）、secret store、环境变量
- 禁止：硬编码在代码仓库、公开日志、聊天上下文
- refresh_token 过期后必须用 `swarm_login` 重新获取（不能仅依赖 token_refresh 无限续）

---

## 14. 联邦身份

Swarm 的世界形成**联邦宇宙**——玩家在一个世界注册的身份可以被其他世界识别和接受，无需重复注册。

### 18.1 信任模型

每个世界有自己的 `CertificateIssuer` 密钥对。世界可以通过配置信任其他世界的 issuer 公钥：

```toml
# world.toml
[auth.federation]
# 信任的远程世界列表
trusted_issuers = [
  { world_id = "swarm-alpha",  issuer_public_key = "ed25519:base64..." },
  { world_id = "swarm-beta",   issuer_public_key = "ed25519:base64..." },
]
```

### 18.2 跨世界登录流程

玩家持 World A 的证书来 World B：

```
1. 客户端发送 World A 的 PlayerCertificate（非本地世界签发）
2. World B 查找证书中的 issuer_public_key 是否在 trusted_issuers 列表中
3. 验证证书签名（用 World A 的 issuer 公钥）
4. 验证证书未过期、未被撤销
5. 映射身份：player_id_local = blake3("federated:" + world_id + ":" + original_player_id) → u64
6. World B 用本地 CertificateIssuer 重新签发本地证书（绑定本地 player_id）
7. 返回 LoginResult（包含本地证书 + session）
```

### 15.3 MCP 工具

| Tool | 参数 | 返回 | 说明 |
|------|------|------|------|
| `swarm_federated_login` | `certificate` (外部签发) | `LoginResult` | 用外部世界证书登录本地世界 |

```
POST /mcp (JSON-RPC)
{
  "method": "swarm_federated_login",
  "params": {
    "certificate": {
      "payload": { "player_id": 42, "audience": "swarm-wasm-deploy", ... },
      "issuer_public_key": "ed25519:...",
      "signature": "..."
    }
  }
}

Response: LoginResult { player_id (本地), session, certificate (本地重签) }
```

### 14.4 身份映射

联邦身份的 `player_id` 按世界隔离：

```
本地注册:
  "local" + ":" + username → blake3 → u64 → player_id (本地命名空间)

OAuth2:
  provider + ":" + subject → blake3 → u64 → player_id (OAuth2 命名空间)

联邦:
  "federated" + ":" + world_id + ":" + original_player_id → blake3 → u64 → player_id
```

不同世界的同一联邦玩家拥有**独立的本地 player_id 和资产**。联邦身份只用于认证——不共享游戏状态、不共享模块、不共享排名。这与 [Swarm 联邦宇宙哲学](README.md#11-核心理念) 一致：身份可跨世界，但游戏状态按世界隔离。

### 14.5 撤销传播

- 本地证书撤销仅影响本地世界
- 外部证书撤销：World B 定期向 World A 查询吊销列表（`GET /auth/revocations?since=<timestamp>`），或在验证时实时查询
- 若外部世界不可达：使用本地缓存的吊销列表（stale 视为有效——可用性优先）

---

## 15. 前端变更

### 18.1 `LoginButton.tsx` 扩展现有组件

```
┌──────────────────────────────────────────┐
│  Player authentication                   │
│  ┌──────────────────────────────────────┐│
│  │ ○ GitHub login                       ││
│  │ ○ Google login                       ││
│  └──────────────────────────────────────┘│
│  ── or ──                                │
│  ┌──────────────────────────────────────┐│
│  │ New account:                         ││
│  │ Username:      [______________]      ││
│  │ Password:      [______________]      ││
│  │ Confirm:       [______________]      ││
│  │ [ ▲ Register ]  (~1-3s PoW proof)   ││
│  ├──────────────────────────────────────┤│
│  │ Already registered:                  ││
│  │ Username:      [______________]      ││
│  │ Password:      [______________]      ││
│  │ [ ▶ Login ]                          ││
│  └──────────────────────────────────────┘│
└──────────────────────────────────────────┘
```

### 18.2 PoW 前端实现

- 必须运行在 **Web Worker** 中（禁止主线程 `while(true)` 阻塞）
- 显示进度：`已尝试 N / 预计 M 次`（基于 difficulty_bits 计算期望值）
- 超过 8 秒显示 "Slow device? You can wait or [Cancel]"
- 取消后自动重新获取 challenge + 重试
- `difficulty_bits` 从服务端 challenge 响应获取，不做客户端假设

### 15.3 `provider` 字段扩展

```typescript
export type AuthProvider = 'github' | 'google' | 'local';
```

---

## 16. 安全考量

### 18.1 威胁模型

| 威胁 | 缓解措施 |
|------|---------|
| 批量注册 / DDoS | PoW challenge-response（difficulty_bits=24, ~150ms Rust / ~1.5s WASM） |
| PoW challenge 替换/降级 | 服务端从 FDB 读取权威 challenge+difficulty，register 不接收客户端 challenge 字段 |
| PoW challenge 重放 | 一次性消费（FDB 原子标记 consumed），TTL 5min |
| PoW challenge DoS | challenge 申请 IP 限速 10/min；FDB 存储 TTL 自动清理 |
| 密码暴力破解 | argon2id (19MiB, 2 iters) + per-account 失败计数 + 递增延迟 + 短期锁定 |
| 分布式低速密码爆破 | per-account 失败计数（跨 IP）；可选 login PoW 触发 |
| 用户名枚举 | 登录失败统一 `invalid_credentials`；不存在用户执行 dummy argon2id；用户名注册状态不公开 |
| 响应时间侧信道 | dummy argon2id 消除存在/不存在用户的时间差 |
| 密码传输 | HTTPS（生产部署） |
| FDB 泄露 | 密码仅存储 argon2id hash；所有 value 带 schema_version |
| 时序攻击 | `verify_password` 使用 argon2 crate 的常量时间比较 |
| Chat log 泄露凭据 | Agent 代理注册返回一次性 handoff code，非裸 refresh_token |
| 凭据丢失 | 邮箱密码重置 + 注册 UI 显示 Confirm Password + AI agent 持久化备份 |
| 密码重置 token 泄露 | reset_token 15min TTL + 一次性消费 + 吊销所有现有 session |
| 账号删除误操作 | 密码确认 + 30 天 grace period 可恢复 |
| 邮箱验证 token 劫持 | HTTPS + verification token 24h TTL + 一次性消费 |

### 18.2 不做的

- ❌ 双因素认证（TOTP / WebAuthn）— 可作为后续安全升级
- ❌ IP 黑名单
- ❌ 密码明文日志

---

## 17. 实现范围

### 13.1 Phase 1

| 组件 | 文件 | 变更 |
|------|------|------|
| Engine Auth | `src/auth/mod.rs` (新) | challenge 生成/验证、注册、登录、密码修改、密码重置、账号删除、argon2id、FDB 读写 |
| Engine Auth | `src/auth/challenge.rs` (新) | PoW 生成与验证 |
| Engine Auth | `src/auth/session.rs` (新) | refresh token rotation、session 管理 |
| Engine Auth | `src/auth/identity.rs` (新) | IdentityKey → PlayerId、三层身份模型 |
| Engine Auth | `src/auth/email.rs` (新) | 邮箱验证 token、密码重置 token、邮件发送
| Engine | `src/tick.rs` / `src/mcp.rs` | 注册 auth MCP tools（转发到 auth domain） |
| Engine | `Cargo.toml` | 添加 `argon2` 依赖 |
| Gateway | `local_auth.go` (新) | REST 端点代理 |
| Gateway | `server.go` | 注册路由 |
| Frontend | `LoginButton.tsx` | Local Register/Login UI + Web Worker PoW |

### 13.2 文档同步

- `design/auth.md`（本文档）
- `design/interface.md` MCP 工具表（已更新）
- `specs/security/03-mcp-security.md` 补充 Auth domain 边界

---

## 18. 与 OAuth2 的互动

### 18.1 共享的证书系统

本地认证和 OAuth2 认证使用完全相同的 `CertificateIssuer`、`PlayerCertificate`、`refresh_token` 模型。下游（WASM 部署、MCP 权限）不感知差异。

### 18.2 `provider` 字段

| Provider | 含义 |
|----------|------|
| `github` | GitHub OAuth2 |
| `google` | Google OAuth2 |
| `local` | 本地用户名/密码 |

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
    ch = mcp_call("swarm_register_challenge", {})
    nonce = solve_pow(ch["challenge"], ch["difficulty_bits"])
    result = mcp_call("swarm_register", {
        "username": f"ai-bot-{secrets.token_hex(8)}",
        "password": secrets.token_hex(32),
        "challenge_id": ch["challenge_id"],
        "nonce": nonce,
        "client_public_key": my_ed25519_pubkey,
    })
    # Persist credentials immediately
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
refresh_token_rotation_grace_seconds = 300
access_token_ttl_seconds = 900
certificate_ttl_seconds = 86400
```
