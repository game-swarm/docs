# Swarm 本地用户认证

> 独立于 OAuth2 的本地用户名/密码注册与登录系统。
> 允许玩家无需 GitHub/Google 账号即可创建 Swarm 身份。
> **AI agent 可通过 MCP 自注册，人类玩家可通过 agent 代理注册。**

## 1. 动机

当前 Swarm 仅支持 OAuth2 联合登录（GitHub / Google）。这排除了以下用户群：

- 不愿绑定第三方账号的玩家（隐私）
- 没有 GitHub/Google 账号的玩家（低门槛体验）
- 内网/离线部署场景（无外部 OAuth2 provider 可用）
- 自动化测试与 CI 环境（无需配置 OAuth2 密钥）
- **AI player 自注册** — AI agent 没有浏览器，无法完成 OAuth2 重定向流程
- **Agent 代理注册** — 人类通过 AI agent 代为注册，无需手动操作前端

**目标**：提供与 OAuth2 并列的本地认证路径，两者共享相同的证书系统和 session 模型，且 AI agent 和前端 UI 都可以调用。

---

## 2. 设计原则

| 原则 | 说明 |
|------|------|
| **并列共存** | 本地认证与 OAuth2 认证处于同等地位，不是附属。前端显式提供切换入口 |
| **MCP 优先** | 注册和登录的核心实现在 engine MCP 层，前端和 Gateway 是薄封装。AI agent 直接调用 MCP tool |
| **同一证书模型** | 本地用户登录后获得与 OAuth2 用户完全相同的 Ed25519 `PlayerCertificate` + `refresh_token`，后续流程无差异 |
| **最小侵入** | 新增代码集中在 engine 的 `src/local_auth.rs`，不改变现有 OAuth2 逻辑 |
| **确定性 player_id** | `player_id = blake3("local:" + username_lowercase)` — 与 `oauth_player_id()` 同模式，可离线推导 |
| **PoW 防滥用** | 注册需要完成工作量证明（PoW challenge），替代 IP rate limiting。无状态、无 IP 追踪、Agent-friendly |
| **密码自管理** | AI agent 可自行生成密码（自动生成强随机密码），与人类玩家密码同等对待 |

---

## 3. 使用场景

### 3.1 人类玩家 — 前端注册

```
人类 → 浏览器 → LoginButton.tsx
  → "Local Register" 表单 → 输入 username + password
  → 前端自动请求 PoW challenge → 求解 nonce
  → POST /mcp → swarm_register(username, password, challenge, nonce, pubkey)
  → 获得 certificate + refresh_token → 存入 localStorage
```

### 3.2 AI player — MCP 自注册

```
AI agent (Claude/GPT/自主 agent) → Hermes MCP session
  → 调用 swarm_register_challenge() 获取 challenge
  → 本地求解 PoW（blake3 brute-force）
  → 调用 swarm_register(username, password, challenge, nonce, pubkey)
     username  = "ai-bot-<random>" (自行生成)
     password  = random_hex(32) (自行生成)
  → 获得 certificate → 调用 swarm_deploy → 部署 WASM
```

AI agent 将 `username` + `password` + `certificate` + `refresh_token` 视为自己的持久化凭据。后续通过 `swarm_login` 或 `swarm_token_refresh` 续签。

### 3.3 人类 — Agent 代理注册

```
人类 → "帮我在 Swarm 注册一个账号，用户名 kagurazaka"
  → AI agent (Hermes) 调用 swarm_register_challenge() + swarm_register(...)
  → 返回 certificate + refresh_token 给人类
  → 人类手动或通过 agent 将凭据存入前端
```

Agent 在注册过程中充当人类的**程序化代理**——完成挑战求解、API 调用等机械步骤，人类只需提供意图和密码。

---

## 4. 架构概览

```
┌─────────────────────────────────────────────────────────┐
│  人类 (Browser)                  AI Agent (MCP)           │
│  ┌──────────────┐  ┌───────┐    ┌─────────────────┐    │
│  │ GitHub Login  │  │ Local  │    │ swarm_register   │    │
│  │ Google Login  │  │ Login  │    │ swarm_login      │    │
│  └──────┬───────┘  └───┬───┘    └────────┬────────┘    │
│         │              │                  │              │
│  ┌──────┴──────────────┴──────────────────┴──────────┐  │
│  │              Gateway (Go)                           │  │
│  │  OAuth2 handler (已有)  │  Local Auth handler (新)  │  │
│  │  /oauth2/{p}/login      │  /auth/register          │  │
│  │  /oauth2/{p}/callback   │  /auth/login             │  │
│  │                          │  /auth/register/challenge│  │
│  └──────────────────────────┴─────────────────────────┘  │
│                          │                                │
│  ┌───────────────────────▼─────────────────────────────┐ │
│  │  Engine MCP (Rust)                                    │ │
│  │  src/mcp.rs              src/local_auth.rs (新)       │ │
│  │  - swarm_oauth2_*        - swarm_register_challenge  │ │
│  │  - CertificateIssuer     - swarm_register            │ │
│  │  - WebAuthSession        - swarm_login               │ │
│  │  - verify_cert           - PoW 生成与校验             │ │
│  │                          - argon2id 哈希              │ │
│  │                          - FDB 读写                   │ │
│  └───────────────────────┬─────────────────────────────┘ │
│                          │                                │
│  ┌───────────────────────▼─────────────────────────────┐ │
│  │  FoundationDB                                          │ │
│  │  "users/<username>" → {phash, player_id, created_at}  │ │
│  │  "pchallenge/<id>"  → {challenge, difficulty, ttl}    │ │
│  └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

---

## 5. 技术选型

### 5.1 密码哈希：argon2id

| 方案 | 优势 | 劣势 |
|------|------|------|
| **argon2id** | OWASP 推荐；内存硬（抗 GPU/ASIC）；内置 salt；可调参数 | Rust 生态相对年轻 |
| bcrypt | 最广泛使用；成熟稳定 | 72 字节密码上限；非内存硬 |
| scrypt | 内存硬；成熟 | 可调参数比 argon2 少 |
| PBKDF2 | FIPS 认证；最广泛 | 非内存硬；需额外实现 salt 管理 |

**选择：argon2id**，使用 `argon2` crate。

参数配置（OWASP 2025 推荐）：

```rust
pub const ARGON2_MEMORY_KIB: u32 = 19_456;  // 19 MiB
pub const ARGON2_ITERATIONS: u32 = 2;
pub const ARGON2_PARALLELISM: u32 = 1;
```

```rust
use argon2::{Argon2, PasswordHasher, PasswordVerifier, password_hash::{SaltString, PasswordHash}};

fn hash_password(password: &str) -> Result<String, McpError> {
    let salt = SaltString::generate(&mut OsRng);
    let argon2 = Argon2::default();
    let hash = argon2
        .hash_password(password.as_bytes(), &salt)
        .map_err(|e| McpError::internal_error(format!("password hashing failed: {e}")))?
        .to_string();
    Ok(hash)
}

fn verify_password(password: &str, hash: &str) -> Result<bool, McpError> {
    let parsed = PasswordHash::new(hash)
        .map_err(|e| McpError::internal_error(format!("invalid password hash: {e}")))?;
    Ok(Argon2::default()
        .verify_password(password.as_bytes(), &parsed)
        .is_ok())
}
```

### 5.2 凭据存储：FoundationDB

Swarm 已使用 FoundationDB 作为权威存储（见 [tech-choices.md §4](tech-choices.md#4-持久化-foundationdb)）。用户凭据使用一致的 key 前缀。

**Key 设计**：

```
FDB key:   "users/<username_lowercase>"
FDB value: JSON { "password_hash": "...", "player_id": N, "created_at": ISO8601 }
```

**替代方案分析**：

| 方案 | 优势 | 劣势 |
|------|------|------|
| FDB | 已有集群；事务保证；与现有 FDB 使用一致 | 需要额外 subdirectory |
| SQLite | 零运维；最简单的 kv | 多 engine 进程会竞争；`/data/swarm/` 单点 |
| 内存 + 文件 | 最快；零依赖 | 重启丢失；多进程不同步 |

**选择：FoundationDB**。Swarm 引擎已绑定 FDB client，添加一个 `users/` subdirectory 成本极低。事务保证避免了注册竞态（两个请求同时注册同一用户名）。

### 5.3 PoW 算法：blake3 前导零

PoW 挑战用 blake3 哈希（与 player_id 推导同一原语，无额外依赖）：

```rust
// 挑战生成
fn generate_challenge(difficulty: u8) -> PoWChallenge {
    PoWChallenge {
        challenge_id: random_hex(16),
        challenge: random_hex(32),
        difficulty,  // 前导零字节数 (推荐默认 4)
        created_at: now_seconds(),
        ttl_seconds: 300,  // 5 分钟有效期
    }
}

// 验证
fn verify_pow(challenge: &str, nonce: &str, difficulty: u8) -> bool {
    let input = format!("{}{}", challenge, nonce);
    let hash = blake3::hash(input.as_bytes());
    hash.as_bytes()[..difficulty as usize].iter().all(|&b| b == 0)
}
```

客户端求解示例（Python 伪代码）：

```python
import blake3

def solve_pow(challenge: str, difficulty: int) -> str:
    nonce = 0
    target = b'\x00' * difficulty
    while True:
        h = blake3.blake3(f"{challenge}{nonce}".encode()).digest()
        if h[:difficulty] == target:
            return str(nonce)
        nonce += 1
```

**难度参数**：

| 场景 | difficulty | 预期求解时间 (单核) | 预期尝试次数 |
|------|-----------|-------------------|------------|
| 开发/测试 | 2 | < 1ms | ~65K |
| 生产 (轻量) | 3 | ~5ms | ~16.7M |
| 生产 (标准) | **4** | **~1.3s** | **~4.3B** |
| 反滥用 (高) | 5 | ~5min | ~1.1T |

默认 `difficulty = 4`：每个注册请求消耗约 1.3 秒 CPU，阻止批量注册脚本，但对合法用户（包括 AI agent）完全透明。

---

## 6. 用户名规则

```
允许字符:    [a-zA-Z0-9_-]
长度:        3-32 字符
大小写:      不敏感（存储和查找时一律 lowercase）
禁止:        纯数字开头（保留用于 player_id 直查）
禁止列表:    ["admin", "root", "swarm", "system", "mod", "gm"] （保留字）
```

校验正则：`^[a-zA-Z][a-zA-Z0-9_-]{2,31}$`

不强制邮箱：本地认证的意义就是低门槛，邮箱是可选的。

---

## 7. 密码规则

```
最小长度:    8 字符
最大长度:    128 字符（Bcrypt 兼容边界，虽然实际用 argon2）
要求:        至少包含 1 个字母 + 1 个数字
禁止:        与用户名相同或包含用户名
禁止列表:    ["password", "12345678", "swarm123", "admin123"] （常见弱密码）
```

**AI agent 自动密码**：AI agent 自注册时，建议使用 `random_hex(32)` 生成 64 字符随机密码——彻底绕过密码强度校验和字典攻击风险。

错误响应示例：

```json
{
  "error": {
    "code": "weak_password",
    "message": "Password must be at least 8 characters and contain at least one letter and one digit."
  }
}
```

---

## 8. API 设计

### 8.1 MCP 工具一览

新增三个 MCP tool：

| Tool | 参数 | 返回 | 说明 |
|------|------|------|------|
| `swarm_register_challenge` | (无) | `PoWChallenge` | 获取注册 PoW 挑战 |
| `swarm_register` | `username`, `password`, `challenge_id`, `challenge`, `nonce`, `client_public_key` | `OAuth2LoginResult` | 完成 PoW + 注册并登录 |
| `swarm_login` | `username`, `password`, `client_public_key` | `OAuth2LoginResult` | 登录已有账号 |

三者均映射到 `CommandSource::McpQuery`，不参与游戏 tick 验证。`swarm_login` 不需要 PoW——每 tick 已限速（10/min per IP），且 argon2id 本身足够慢。

### 8.2 `swarm_register_challenge`

```
POST /mcp (JSON-RPC)
{
  "method": "swarm_register_challenge",
  "params": {}
}

Response:
{
  "challenge_id": "a1b2c3d4e5f6a7b8",
  "challenge": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b...",
  "difficulty": 4,
  "expires_in_seconds": 300
}
```

Challenge 有效期 5 分钟。过期后需要重新请求。每个 `challenge_id` 只能使用一次（注册成功或过期后作废）。

### 8.3 `swarm_register`

```
POST /mcp (JSON-RPC)
{
  "method": "swarm_register",
  "params": {
    "username": "kagurazaka",
    "password": "correct-horse-battery-staple",
    "challenge_id": "a1b2c3d4e5f6a7b8",
    "challenge": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b...",
    "nonce": "1784501234",
    "client_public_key": "ed25519:base64..."
  }
}

Response (200):
{
  "player_id": 42,
  "session": {
    "access_token": "swarm_<opaque>",
    "access_token_expires_at": 1781570000,
    "refresh_token": "swarm_<opaque>",
    "refresh_token_expires_at": 1784162000
  },
  "certificate": {
    "payload": {
      "player_id": 42,
      "audience": "swarm-wasm-deploy",
      "client_public_key": "ed25519:base64...",
      "issued_at": 1781568000,
      "expires_at": 1781654400
    },
    "issuer_public_key": "...",
    "signature": "..."
  }
}

Error — PoW 失败:
{
  "error": {
    "code": "invalid_pow",
    "message": "Proof of work verification failed. Solve the challenge and try again."
  }
}

Error — 用户名已存在:
{
  "error": {
    "code": "username_taken",
    "message": "Username 'kagurazaka' is already registered."
  }
}
```

**注册流程**（AI agent 视角）：

```
1. swarm_register_challenge()  →  {challenge_id, challenge, difficulty: 4}
2. nonce = solve_pow(challenge, difficulty)  // CPU brute-force, ~1.3s
3. swarm_register(username, password, challenge_id, challenge, nonce, pubkey)
   →  {player_id, session, certificate}
```

### 8.4 `swarm_login`

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

Response: 同 swarm_register 成功响应

Error — 凭据错误:
{
  "error": {
    "code": "invalid_credentials",
    "message": "Invalid username or password."
  }
}
```

> 注意：登录失败统一返回 `invalid_credentials` 而不区分"用户不存在"和"密码错误"——防止用户名枚举攻击。
> 登录不需要 PoW——argon2id 本身的速度（~100ms per attempt）已经提供了足够的暴力破解阻力。

### 8.5 Gateway REST 端点

Gateway 新增本地认证的 HTTP 端点（与 OAuth2 同级），均为 engine MCP 的薄代理层：

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/auth/register/challenge` | 获取 PoW 挑战 |
| `POST` | `/auth/register` | 注册（含 PoW 验证） |
| `POST` | `/auth/login` | 登录 |

```
POST /auth/register/challenge
→ 代理: {"method": "swarm_register_challenge", "params": {}}
← 返回: challenge + difficulty

POST /auth/register
Content-Type: application/json
{
  "username": "kagurazaka",
  "password": "correct-horse-battery-staple",
  "challenge_id": "a1b2...",
  "challenge": "9f86...",
  "nonce": "1784501234",
  "client_public_key": "ed25519:base64..."
}
→ 代理: {"method": "swarm_register", "params": {...}}
← 返回: certificate + session
```

---

## 9. Player ID 模型

### 9.1 现有模型（OAuth2）

```rust
fn oauth_player_id(provider: &str, subject: &str) -> PlayerId {
    // deterministic hash of "provider:subject"
}
```

### 9.2 新增模型（Local）

```rust
fn local_player_id(username: &str) -> PlayerId {
    // blake3("local:" + username_lowercase) → u64
    blake3_hash_to_player_id(format!("local:{}", username.to_lowercase()))
}
```

与 `oauth_player_id` 同模式——确定性、可离线推导、无需查 FDB 即可获得 `player_id`。

### 9.3 身份共存

同一个自然人可以拥有多个 Swarm 身份：

```
自然人 A:
  - OAuth2 (GitHub:12345)      → player_id = 42
  - OAuth2 (Google:67890)      → player_id = 99
  - Local (username: kagura)   → player_id = 7

AI 集群 B:
  - Local (ai-bot-a1b2c3)      → player_id = 511
  - Local (experiment-d4e5f6)  → player_id = 832
```

v1 不实现身份合并——多个 `player_id` 独立存在，各自拥有独立的模块和资产。

---

## 10. 前端变更

### 10.1 `LoginButton.tsx` 扩展现有组件

在现有 "GitHub login" / "Google login" 按钮下方增加 "Local Account" 区域：

```
┌─────────────────────────────────────┐
│  Player authentication              │
│  ┌─────────────────────────────────┐│
│  │ ○ GitHub login                  ││
│  │ ○ Google login                  ││
│  └─────────────────────────────────┘│
│  ── or ──                           │
│  ┌─────────────────────────────────┐│
│  │ Username: [____________]        ││
│  │ Password: [____________]        ││
│  │ [ ▲ Register ]  [ ▶ Login ]    ││
│  │ (Register needs ~1s PoW proof) ││
│  └─────────────────────────────────┘│
└─────────────────────────────────────┘
```

前端在用户点击 "Register" 后自动执行 PoW 流程（JavaScript blake3 WASM 求解），用户感知到的只是 ~1 秒的加载延迟。

### 10.2 `provider` 字段扩展

```typescript
export type AuthProvider = 'github' | 'google' | 'local';
```

---

## 11. 安全考量

### 11.1 威胁模型

| 威胁 | 缓解措施 |
|------|---------|
| 批量注册 / DDoS | **PoW challenge-response**（difficulty=4, ~1.3s CPU per register） |
| 密码暴力破解 | argon2id 内存硬（19 MiB/attempt）；login 统一返回 `invalid_credentials` |
| 用户名枚举 | 登录失败不区分"用户不存在"和"密码错误" |
| PoW 预计算/重放 | challenge 5min TTL + 一次性使用（FDB 记录已用 challenge_id） |
| 密码传输 | 假设 HTTPS（生产部署） |
| FDB 泄露 | 密码仅存储 argon2id hash，不存储明文 |
| 时序攻击 | `verify_password` 使用 argon2 crate 的常量时间比较 |
| 密码强度不足 | 服务端校验 + 常见密码黑名单；AI agent 建议使用 random_hex(32) |

### 11.2 为什么用 PoW 而非 IP rate limiting

| 维度 | IP Rate Limiting | PoW Challenge |
|------|-------------------|---------------|
| AI agent | Agent 和被注册者同一 IP——限速会误伤 | Agent 为每次注册独立求解 PoW |
| 代理 / NAT | 多用户共享 IP→ 一个用户注册耗尽所有配额 | 每个注册消耗独立计算 |
| 分布式滥用 | Botnet 每个节点不同 IP→ 轻松绕过 | 每个账户仍需真金白银的 CPU 算力 |
| 无状态 | 需要追踪 IP→ 需要 shared state | Challenge 自包含，仅需一次性标记已使用 |
| 用户体验 | 被限速后需等待 1 小时 | 每次注册支付 ~1.3s CPU，立即可重试 |

### 11.3 不做的

- ❌ 密码明文记录日志
- ❌ 密码哈希通过 MCP 响应返回
- ❌ 前端存储密码（仅存 `refresh_token` + `certificate`）
- ❌ 密码重置（v1——待 email 基础设施）
- ❌ 双因素认证（v1）
- ❌ IP 黑名单 / GeoIP 过滤

---

## 12. 实现范围

### 12.1 Phase 1（本文档范围）

| 组件 | 文件 | 变更 |
|------|------|------|
| Engine | `src/local_auth.rs` (新) | `swarm_register_challenge`, `swarm_register`, `swarm_login`；PoW 生成/校验；用户名/密码校验；argon2id 哈希；FDB 读写 |
| Engine | `src/mcp.rs` | 注册 3 个新 MCP tool；`mcp_tool_infos()`；`call_tool()` dispatch；`mcp_tool_source()` |
| Engine | `Cargo.toml` | 添加 `argon2` 依赖（`blake3` 已存在） |
| Gateway | `local_auth.go` (新) | `POST /auth/register/challenge`；`POST /auth/register`；`POST /auth/login` 薄代理 |
| Gateway | `server.go` | 注册新路由 |
| Frontend | `LoginButton.tsx` | Local Register/Login UI + PoW 求解（blake3 WASM）+ API 调用 |

### 12.2 明确推迟到后续版本

| 功能 | 原因 |
|------|------|
| 密码重置 | 需要邮箱验证——待 email 基础设施建立 |
| 邮箱绑定 | MVP 不强制邮箱 |
| 身份合并 | 设计复杂，需完善的迁移方案 |
| WebAuthn / Passkeys | Phase 2 安全升级 |
| 账号删除 | 需要确认资产处理策略 |
| 密码修改 | v1.1 快速补充（无需额外基础设施） |

---

## 13. 与 OAuth2 的互动

### 13.1 共享的证书系统

本地认证和 OAuth2 认证使用完全相同的：

- `CertificateIssuer`（Ed25519 密钥对）
- `WebAuthSession` 结构
- `OAuth2LoginResult` 返回类型
- `swarm_token_refresh` / `swarm_auth_revoke`（无需修改）

下游消费者（网关、前端、WASM 部署、MCP 权限检查）**不感知差异**。

### 13.2 `provider` 字段

| Provider | 含义 |
|----------|------|
| `github` | GitHub OAuth2 |
| `google` | Google OAuth2 |
| `local` | 本地用户名/密码 |

`player_id` 的命名空间按 provider 隔离。

---

## 14. 测试策略

### 单元测试（Engine, `src/local_auth.rs`）

```
test username_rejects_invalid_chars
test username_rejects_reserved_words
test username_rejects_too_short
test username_normalizes_lowercase
test password_rejects_too_short
test password_rejects_no_digit
test password_rejects_matches_username
test password_accepts_ai_generated_strong_password
test hash_password_produces_valid_argon2id
test verify_password_accepts_correct
test verify_password_rejects_wrong
test pow_challenge_generates_valid_challenge
test pow_verify_accepts_correct_nonce
test pow_verify_rejects_wrong_nonce
test pow_verify_rejects_reused_challenge
test pow_challenge_expires_after_ttl
test register_creates_fdb_entry
test register_rejects_duplicate_username
test register_rejects_invalid_pow
test register_rejects_expired_challenge
test register_consumes_challenge_one_time_only
test login_returns_certificate_on_success
test login_rejects_wrong_password
test login_rejects_nonexistent_user
test player_id_is_deterministic
test ai_agent_self_register_with_random_password
test difficulty_4_expected_attempts_approx_4b
```

### 集成测试（`mcp.rs` 模式）

复用现有 `login_with_key()` helper，新增 `local_register_and_login()` helper：

```rust
#[test]
fn local_register_and_login_full_cycle() {
    let mut server = McpServer::new_for_tests();
    let client_key = SigningKey::generate(&mut OsRng);

    // 1. Get challenge
    let challenge = server.swarm_register_challenge().unwrap();

    // 2. Solve PoW
    let nonce = solve_pow_for_test(&challenge.challenge, challenge.difficulty);

    // 3. Register
    let result = server.swarm_register(RegisterParams {
        username: "testuser".into(),
        password: "hunter2pass".into(),
        challenge_id: challenge.challenge_id,
        challenge: challenge.challenge,
        nonce,
        client_public_key: encode_public_key(&client_key),
    }).expect("registration should succeed");

    // 4. Verify certificate
    server.verify_certificate_for_player(&result.certificate, result.player_id)
        .expect("issued certificate should verify");

    // 5. Login
    let login = server.swarm_login(LoginParams {
        username: "testuser".into(),
        password: "hunter2pass".into(),
        client_public_key: encode_public_key(&client_key),
    }).expect("login should succeed");

    assert_eq!(login.player_id, result.player_id);
}

#[test]
fn ai_agent_self_registration_flow() {
    // AI generates random credentials
    let username = format!("ai-bot-{}", random_hex(8));
    let password = random_hex(32);  // 64 chars

    // Standard PoW + register flow
    let challenge = server.swarm_register_challenge().unwrap();
    let nonce = solve_pow_for_test(&challenge.challenge, challenge.difficulty);
    let result = server.swarm_register(RegisterParams {
        username: username.clone(),
        password: password.clone(),
        challenge_id: challenge.challenge_id,
        challenge: challenge.challenge,
        nonce,
        client_public_key: pubkey.clone(),
    }).expect("AI agent should be able to self-register");

    // Certificate is valid for WASM deploy
    assert_eq!(result.certificate.payload.audience, "swarm-wasm-deploy");
}
```

---

## 附录 A: PoW 客户端实现参考

### Python（AI agent / 脚本）

```python
import blake3
import secrets
import time

def request_challenge(endpoint: str) -> dict:
    """GET /auth/register/challenge"""
    ...

def solve_pow(challenge: str, difficulty: int) -> str:
    target = b'\x00' * difficulty
    nonce = 0
    while True:
        h = blake3.blake3(f"{challenge}{nonce}".encode()).digest()
        if h[:difficulty] == target:
            return str(nonce)
        nonce += 1

def register(endpoint: str, username: str, password: str, pubkey: str):
    ch = request_challenge(endpoint)
    nonce = solve_pow(ch["challenge"], ch["difficulty"])
    # POST /auth/register with {username, password, challenge_id, challenge, nonce, client_public_key}
    ...

# AI agent self-registration
register(endpoint, f"ai-bot-{secrets.token_hex(8)}", secrets.token_hex(32), my_ed25519_pubkey)
```

### JavaScript（前端 / Web）

```javascript
import * as blake3 from 'blake3-wasm';

async function solvePoW(challenge, difficulty) {
  const target = new Uint8Array(difficulty);
  let nonce = 0n;
  while (true) {
    const input = new TextEncoder().encode(challenge + nonce.toString());
    const hash = blake3.hash(input);
    if (hash.slice(0, difficulty).every((b, i) => b === target[i])) {
      return nonce.toString();
    }
    nonce++;
  }
}
```

---

## 附录 B: argon2id hash 格式

```
$argon2id$v=19$m=19456,t=2,p=1$<base64-salt>$<base64-hash>
```

- `$argon2id$` — 算法标识
- `v=19` — 版本
- `m=19456` — memory (KiB)
- `t=2` — iterations
- `p=1` — parallelism
- `<salt>` — 16 字节随机 salt，base64 编码
- `<hash>` — 32 字节 hash output，base64 编码

## 附录 C: FDB Transaction 示例

```rust
// 注册（带竞态保护）
let tx = fdb.create_transaction();

// 1. 验证 PoW（一次性使用）
let pow_key = format!("pchallenge/{}", params.challenge_id);
if tx.get(pow_key.as_bytes(), false).await?.is_none() {
    return Err(McpError::invalid_params("challenge not found or already used"));
}
tx.clear(pow_key.as_bytes());  // 原子消费 challenge

// 2. 验证 PoW 解
if !verify_pow(&params.challenge, &params.nonce, DIFFICULTY) {
    return Err(McpError::invalid_params("invalid_pow"));
}

// 3. 检查用户名
let user_key = format!("users/{}", params.username.to_lowercase());
if tx.get(user_key.as_bytes(), false).await?.is_some() {
    return Err(McpError::conflict("username_taken"));
}

// 4. 写入用户
let record = json!({
    "password_hash": hash_password(&params.password)?,
    "player_id": local_player_id(&params.username),
    "created_at": Utc::now().to_rfc3339(),
});
tx.set(user_key.as_bytes(), record.to_string().as_bytes());

// 5. 原子提交（保证 challenge 消费 + 用户创建要么同时成功，要么都不发生）
tx.commit().await?;

// 6. 签发证书（在事务外部，与 OAuth2 login 相同）
self.issue_login("local", &params.username, "local-credential", params.client_public_key)
```
