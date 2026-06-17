# Security Review: Swarm 本地用户认证 (R1)

**评审员**: rev-dsv4-security (安全专家)  
**评审日期**: 2026-06-17  
**评审范围**: /tmp/swarm-review-R1/local-auth.md (主设计), interface.md, tech-choices.md, README.md  
**Clean-Slate**: 是 — 未参考 /data/swarm/ 下任何文件或旧评审

---

## Verdict: CONDITIONAL_APPROVE

设计整体扎实，核心安全决策（argon2id、PoW over IP rate limiting、统一错误响应、FDB 原子事务）经得起推敲。发现 **3 个 High** 和 **4 个 Medium** 问题需要在进入实现阶段前修正。无 Critical 阻塞问题。

---

## 发现的问题

### [High] H1 — argon2id 参数未接入实际哈希调用

**位置**: local-auth.md §5.1

文档定义了正确的常量：
```rust
pub const ARGON2_MEMORY_KIB: u32 = 19_456;  // 19 MiB
pub const ARGON2_ITERATIONS: u32 = 2;
pub const ARGON2_PARALLELISM: u32 = 1;
```

但 `hash_password` 和 `verify_password` 函数使用 `Argon2::default()`，该函数使用 crate 内置默认值（**4 MiB memory, 3 iterations**），而非文档声明的 19 MiB/2 iterations。文档中定义的常量从未被使用。

**影响**: 实际运行时的密码哈希强度仅为 4 MiB（crate 默认），远低于设计意图的 19 MiB。对 GPU/ASIC 暴力破解的抗性大幅削弱。

**修复建议**:
```rust
use argon2::{Argon2, Algorithm, Version, Params};

fn argon2_instance() -> Argon2<'static> {
    Argon2::new(
        Algorithm::Argon2id,
        Version::V0x13,
        Params::new(
            ARGON2_MEMORY_KIB,
            ARGON2_ITERATIONS,
            ARGON2_PARALLELISM,
            Some(32),  // output length
        ).unwrap(),
    )
}
```
并在 `hash_password` / `verify_password` 中统一使用此实例。建议在 unit test 中验证 hash 格式包含 `m=19456,t=2,p=1`。

---

### [High] H2 — FDB 事务早退导致 PoW challenge 未消耗（用户名探测向量）

**位置**: local-auth.md 附录 C, 行 771-775

FDB 事务代码的执行顺序存在逻辑缺陷：

```rust
tx.clear(pow_key.as_bytes());  // (1) 标记 challenge 待删除（仅在内存中）

// ... PoW 校验 ...

if tx.get(user_key.as_bytes(), false).await?.is_some() {
    return Err(McpError::conflict("username_taken"));  // (2) 早退——事务未提交
}

tx.set(user_key.as_bytes(), record.to_string().as_bytes());
tx.commit().await?;  // (3) 仅在此处提交
```

**问题**: 当用户名已存在时，代码在 `(2)` 处直接 return，事务对象被丢弃而从未 commit。`tx.clear()` 的副作用从未持久化到 FDB，challenge 保持有效状态。攻击者可以：

1. 求解一个 PoW challenge（~1.3s CPU）
2. 使用该 challenge 尝试注册 "admin" → 返回 `username_taken` → challenge 未被消费
3. 使用同一 challenge 尝试 "root" → 同样未消费
4. 反复探测用户名直到找到可用的，或遍历整个保留字列表

**这违背了 §11.1 威胁模型中 "challenge 一次性使用" 的安全承诺。**

**修复建议**: 无论注册成功与否，只要 PoW 验证通过，就应消费 challenge。两种方案：

方案 A（推荐）— 重新排序：先检查用户名，再消费 challenge：
```rust
// Step 1: 先检查用户名
let user_key = format!("users/{}", params.username.to_lowercase());
if tx.get(user_key.as_bytes(), false).await?.is_some() {
    return Err(McpError::conflict("username_taken"));
}
// Step 2: 验证并消费 PoW（仅当用户名可用）
let pow_key = format!("pchallenge/{}", params.challenge_id);
if tx.get(pow_key.as_bytes(), false).await?.is_none() {
    return Err(McpError::invalid_params("challenge not found or already used"));
}
// ... 验证 PoW ...
tx.clear(pow_key.as_bytes());
```
注意：此方案下，用户名探测不再消耗 PoW——但这是可接受的，因为用户名本身不是秘密，且 PoW 的目的是防止批量注册（非防探测）。

方案 B — 无条件消费：
在早退路径中也执行 `tx.commit()`（消费 challenge 但不写用户）：
```rust
if tx.get(user_key.as_bytes(), false).await?.is_some() {
    tx.commit().await?;  // 消费 challenge
    return Err(McpError::conflict("username_taken"));
}
```

---

### [High] H3 — 登录路径存在用户名枚举时序侧信道

**位置**: local-auth.md §8.4, §11.1

文档正确要求登录失败统一返回 `invalid_credentials`（§8.4），威胁模型也声明了 "登录失败不区分'用户不存在'和'密码错误'"（§11.1）。但设计中存在一个时序侧信道：

- 用户不存在 → 直接返回 `invalid_credentials`（~1ms）
- 用户存在 + 密码错误 → 执行 argon2id 验证（~100ms）→ 返回 `invalid_credentials`

两者返回完全相同的错误码和消息，但**响应时间相差 ~100×**。攻击者可通过测量响应延迟以高置信度判断用户名是否存在。

**影响**: 虽然用户名不是最高价值目标（player_id 从用户名派生，而用户名是公开信息），但这破坏了设计文档自身的反枚举承诺。在 Swarm 场景中，攻击者可枚举活跃玩家列表用于后续定向攻击。

**修复建议**: 当用户不存在时，仍然执行一次 argon2id 哈希（使用 dummy hash 或固定 salt），使两条路径的时序无法区分：

```rust
async fn login_constant_time(tx: &FdbTransaction, username: &str, password: &str) -> Result<LoginResult, McpError> {
    let user_key = format!("users/{}", username.to_lowercase());
    let stored = tx.get(user_key.as_bytes(), false).await?;
    
    let (hash_to_verify, player_id) = match stored {
        Some(data) => {
            let record: UserRecord = serde_json::from_slice(&data)?;
            (record.password_hash, Some(record.player_id))
        }
        None => {
            // Dummy hash with known-wrong password — same cost as real verification
            ("$argon2id$v=19$m=19456,t=2,p=1$AAAAAAAAAAAAAAAAAAAAAA$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA".to_string(), None)
        }
    };
    
    let is_valid = verify_password(password, &hash_to_verify)?;
    if !is_valid || player_id.is_none() {
        return Err(McpError::unauthorized("invalid_credentials"));
    }
    // ... issue certificate for player_id ...
}
```

注意：dummy hash 的格式必须与实际 hash 使用相同的参数（m=19456,t=2,p=1），确保计算量一致。

---

### [Medium] M1 — 密码黑名单过于薄弱

**位置**: local-auth.md §7

当前黑名单仅 4 项：`["password", "12345678", "swarm123", "admin123"]`。

**问题**: 仅覆盖极少数常见密码。大量高频弱密码（如 `qwerty123`, `iloveyou`, `dragon`, `monkey`, `football`, `letmein` 等）可通过校验。

**修复建议**: 采纳至少 top 10,000 常见密码黑名单（如 `zxcvbn` 库内置的 `common_passwords.txt` 或 HaveIBeenPwned PwnedPasswords 的本地子集）。Rust 生态中可使用 `zxcvbn` crate 进行基于熵的密码强度评估，比黑名单更优雅：

```rust
use zxcvbn::zxcvbn;

fn validate_password(password: &str, username: &str) -> Result<(), McpError> {
    let estimate = zxcvbn(password, &[username]);
    if estimate.score() < 2 {
        return Err(McpError::invalid_params("weak_password"));
    }
    // ... other checks ...
    Ok(())
}
```

---

### [Medium] M2 — 缺少登录失败递增延迟 / 账户锁定机制

**位置**: local-auth.md §8.4

当前设计中 `swarm_login` 对同一账户的连续失败尝试没有任何递增惩罚。argon2id 的 ~100ms 延迟虽然提供了基础阻力，但在以下场景中不足：

- 攻击者使用 100 个并发线程对同一已知用户名进行暴力破解 → 1000 次/秒
- 无账户锁定机制，攻击者可无限尝试
- 文档提及 "每 tick 已限速（10/min per IP）"（§8.1），但此限速机制的作用域不明确——是仅限 login 还是所有 MCP query？且 IP 限速与文档 §11.2 反对 IP rate limiting 的立场矛盾。

**修复建议**:

1. 明确 login 端点的独立速率限制（如 5 次/分钟/账户，或 20 次/分钟/IP）
2. 实现递增延迟（如第 N 次失败后延迟 `2^N * 100ms`）
3. v1 至少添加短暂账户锁定（如 5 次失败 → 锁定 15 分钟）

```rust
// FDB: "login_fail/<player_id>" → {count, last_attempt}
// 5 failures in 15 minutes → return "account_locked" for 15 minutes
```

---

### [Medium] M3 — 密码最小长度 8 字符偏低

**位置**: local-auth.md §7

最小长度 8 字符满足最低行业标准，但考虑到：

- AI agent 使用 `random_hex(32)` (64 字符) 不会有问题
- 人类用户若选择 8 字符密码，配合 argon2id(19 MiB) 仍有相当抗力
- 但 NIST SP 800-63B 和 OWASP 的最新指南倾向于 12+ 字符

**修复建议**: 将最小长度提升至 10 字符，或至少对密码强度评分不足（zxcvbn score < 2）的密码强制 12 字符以上。保持 128 字符上限不变（合理）。

---

### [Medium] M4 — Session Token 安全属性未定义

**位置**: local-auth.md §8.3-8.4

注册/登录成功后返回 `access_token` 和 `refresh_token`，但文档未定义：

- Token 格式（JWT？opaque？）
- Token 是否包含 HttpOnly/Secure/SameSite 属性（前端场景）
- Refresh token rotation 策略（每次 refresh 是否换发新 token？）
- Token 吊销机制细节（仅提到 `swarm_auth_revoke` 工具名）

**修复建议**: 补充一节 "Token Security"，至少声明：
- Access token: 短期（如 1h），opaque，存储于内存
- Refresh token: 长期（如 30d），opaque，HttpOnly cookie 或安全存储
- Refresh token rotation: 每次 refresh 换发新的 refresh token，旧 token 立即失效
- 吊销: `swarm_auth_revoke` 将 token 加入 FDB 吊销集合，所有后续使用被拒绝

---

### [Low] L1 — AI Agent 凭据存储指导缺失

**位置**: local-auth.md §3.2

文档说 AI agent 应 "将 `username` + `password` + `certificate` + `refresh_token` 视为自己的持久化凭据"，但未提供安全存储指导。考虑到 AI agent 可能运行在共享环境（CI/CD、云函数），明文存储凭据存在风险。

**建议**: 添加一节或附录，推荐 AI agent 使用操作系统凭据管理器（如 `keyring` crate、`secret-tool`、环境变量 `SWARM_CREDENTIALS`）存储凭据，而非硬编码在脚本中。

---

### [Low] L2 — PoW 验证函数的短路径比较可被时序利用（理论）

**位置**: local-auth.md §5.3

```rust
hash.as_bytes()[..difficulty as usize].iter().all(|&b| b == 0)
```

使用 `Iterator::all` 进行短路径求值。虽然攻击者提交的 nonce 是自己计算的（已知完整的 hash 值），时序差异本身不泄露服务器一方的新信息。但若未来改为服务器端生成 challenge、客户端部分求解的交互式 PoW，此函数将暴露前导零匹配进度。

**建议**: 使用常量时间比较（`blake3` 的 `Hash` 实现了 `ConstantTimeEq`，但此处是对 `[u8]` 比较）。对于当前架构，风险极低；作为防御纵深，建议改为：

```rust
use constant_time_eq::constant_time_eq;
constant_time_eq(&hash.as_bytes()[..difficulty as usize], &vec![0u8; difficulty as usize])
```

---

### [Low] L3 — 无人类/AI 账户类型区分

**位置**: local-auth.md §3.2, §6

AI agent 自注册时使用的用户名格式（`ai-bot-<random>`）仅是约定，无强制。恶意 AI agent 可选择任意用户名（如 `pro_player`）伪装人类。文档 §6 只禁止了保留字和纯数字开头。

**建议**: 若未来需要区分人类/AI 账户（如锦标赛分组、排行榜分类），应在注册时增加 `account_type` 字段。当前阶段可接受——"世界只认 WASM" 的设计哲学本身不区分人类/AI。作为 Low 仅记录，不做强制修改。

---

## 亮点

以下设计决策值得保留并推广到其他子系统：

1. **PoW over IP rate limiting (§11.2)** — 论证充分有力。PoW 的无状态、Agent-friendly、抗分布式滥用特性在 Swarm 的 AI-first 场景中明显优于传统 IP 限速。对比表格清晰，是设计文档的典范写法。

2. **统一错误响应反枚举 (§8.4)** — `invalid_credentials` 统一返回，不区分"用户不存在"和"密码错误"。虽然存在时序侧信道（见 H3），但设计意图正确，修复路径清晰。

3. **FDB 原子事务防竞态 (§5.2, 附录 C)** — 依赖 FoundationDB 的严格可序列化事务保证"challenge 消费 + 用户创建"原子性。与 engine 整体架构一致，避免了分布式锁的复杂性。

4. **确定性 player_id (§9.2)** — `blake3("local:" + username_lowercase)` 与 OAuth2 的 `oauth_player_id()` 同模式，可离线推导，不依赖数据库查询。简洁优雅。

5. **密码不落地原则 (§11.3)** — 明文密码不记日志、不过 MCP 响应、不存前端。每个"不做的"条目都有明确的理由，减少攻击面。

6. **AI agent 自动强密码 (§7)** — 建议 `random_hex(32)` 生成 64 字符密码，绕过字典攻击风险。务实且有效。

7. **威胁模型表 (§11.1)** — 8 个威胁 × 缓解措施的矩阵覆盖了认证系统的主要攻击面。格式清晰，可作为其他子系统威胁建模的模板。

8. **测试策略覆盖安全路径 (§14)** — 18 个单元测试 + 2 个集成测试覆盖了 PoW 重放、challenge 过期、用户名冲突、AI agent 自注册等关键安全路径。测试先行意识值得肯定。

---

## 总体评价

Swarm 本地用户认证设计展现了成熟的安全思维：正确的密码哈希选择（argon2id）、创新的防滥用机制（PoW challenge-response）、严格的反枚举策略、以及整洁的 FDB 原子事务模型。对 AI agent 自注册和代理注册场景的覆盖在同类游戏引擎中具有前瞻性。

三个 High 问题均属于**实现细节层面的偏离**而非设计缺陷：H1（常量未接入）是设计文档到代码的翻译误差，H2（事务早退）是交易编排顺序问题，H3（时序侧信道）是反枚举策略的不完全实现。三者均有明确且低风险的修复路径，不涉及设计哲学变更。

四个 Medium 问题（密码黑名单、锁定机制、最小长度、token 安全）属于防御深度的补充，v1 可接受当前状态但建议尽快迭代。

**建议优先级**:
1. 进入 Phase 1 实现前必须修复 H1、H2
2. 实现过程中同步处理 H3 和 M1（低成本高收益）
3. M2、M3、M4 可在 v1.1 中补充

综合评定：**CONDITIONAL_APPROVE** — 修正 H1、H2 后即可进入实现阶段。
