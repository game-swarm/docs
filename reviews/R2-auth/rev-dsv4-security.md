# R2 安全复检报告 — D4SV Security Reviewer

**评审人**: rev-dsv4-security  
**日期**: 2026-06-17  
**范围**: `/tmp/swarm-review-R2/auth.md` (1236行), `interface.md`, `tech-choices.md`, `README.md`, `03-mcp-security.md`  
**前置**: R1 clean-slate security review (t_4e0552d2), Verdict: CONDITIONAL_APPROVE (3 High, 4 Medium)

---

## Verdict: CONDITIONAL_APPROVE

R1 共识 Blocker 已全部正确修正。R2 文档在 Auth 域的安全性上达到生产就绪水平。发现 3 个新 Medium 问题和 3 个 Low/Info 问题需在实现前处理。

---

## 1. R1 P0 修正验证 (C1-C8, D1-D4)

### C1 — PoW Challenge 权威绑定 ✅ FIXED

**R1 问题**: 客户端可能在注册请求中回传自选 challenge/difficulty，绕过服务端 PoW。

**R2 修正**: auth.md §8.3 明确 `swarm_register` 仅提交 `challenge_id + nonce`，**不包含** challenge 原文和 difficulty_bits。服务端从 FDB `auth/challenges/<challenge_id>` 读取权威值后验证。请求参数列表中无 `challenge` / `difficulty` 字段（L459-470）。验证流程（L472-497）完整：读取 → 校验 consumed/expiry → 用服务端权威值 verify → 原子标记 consumed。

**评分**: ✅ 密码学正确。客户端无法降级或替换 challenge。

### C2 — Difficulty Bit 服务端权威 ✅ FIXED

**R1 问题**: difficulty_bits 可能被客户端控制。

**R2 修正**: difficulty_bits 存储在 FDB challenge record 中，服务端唯一权威。默认值 24 bits（~16.7M 次尝试），含完整性能矩阵（L447-453）。`swarm_register_challenge` 响应中返回 difficulty_bits 仅用于客户端进度估算，验证时使用 FDB 存储值。附录 C 配置（L1210-1212）支持 `register_pow_difficulty_bits = 24` 可调。

**评分**: ✅ 正确。

### C3 — Login 抗暴力破解 ✅ FIXED

**R1 问题**: 缺乏 per-account 防爆破机制。

**R2 修正**: 多层防御体系完整：
- Per-account 失败计数（FDB `auth/login_fail/<username>`），跨 IP 聚合（L331, L909）
- 不存在用户执行 dummy argon2id（L591, L911）
- 统一返回 `invalid_credentials`（不区分不存在/密码错误，L598）
- 连续失败 5 次锁定 300s（L606, L1216-1217）
- 可选 Login PoW 触发器（§8.4, L501-515），默认关闭
- Per-username 速率限制 10/min（L614）
- Login PoW 可独立配置 difficulty_bits（L1221-1225）

**评分**: ✅ 纵深防御设计优秀。dummy argon2id + 统一错误码 + per-account 计数形成完整防线。

### C4 — Auth 边界分离 ✅ FIXED

**R1 问题**: Auth 职责可能泄漏到 Engine 层。

**R2 修正**: §3 架构（L34-97）明确定义 Auth Service 为独立控制面。职责分离表（L92-97）：

| 组件 | 持有 | 不持有 |
|------|------|--------|
| Auth Service | password_hash, challenge, login计数, refresh_token, session | PlayerCertificate 私钥 |
| Engine | CertificateIssuer 密钥对, revoked_certificates | 密码, PoW state, login计数 |
| Gateway | 无状态代理 | 认证状态 |

Engine 只消费已签发身份/证书，不持有密码库（L25）。

**评分**: ✅ 边界清晰，符合最小权限原则。

### C5 — Identity / FDB 模型 ✅ FIXED

**R1 问题**: player_id 推导和 FDB schema 不完整。

**R2 修正**: 
- 三层身份模型（§6.1, L349-364）：`login_username`（不可变）→ `display_name`（可变）→ `player_id`（确定性 hash）
- 确定性推导：`blake3("local:" + username_lowercase) → u64`，碰撞概率 2.7×10^-8
- FDB schema 完整（L327-336），含 8 个 subspace，全部带 `schema_version`
- 事务隔离：密码哈希在事务外完成（L341-343），FDB 事务 <10ms
- `auth/` 前缀隔离游戏世界状态

**评分**: ✅ 模型正确，schema 可扩展。

### C6 — Token 安全 ✅ FIXED

**R1 问题**: refresh token 安全不完整。

**R2 修正**:
- Token 生命周期明确（§13.1, L744-754）：access_token 15min, refresh_token 30d, certificate 24h
- **Refresh token rotation**：每次使用后轮换（L750-754），旧 token 5min grace period 防竞态
- Session 绑定 `(player_id, client_public_key)`（L758）
- 浏览器存储：localStorage + 严格 CSP + HTTPS（L762-767）
- AI Agent 凭据存储指引：文件(0600)/secret store/环境变量（L770-772）
- 日志脱敏：refresh_token 不出现在 URL query、Referrer、日志（L766）

**评分**: ✅ Token 生命周期完整，rotation + binding 正确。

### C7 — 错误恢复 ✅ FIXED

**R1 问题**: 错误恢复路径不完整。

**R2 修正**:
- 完整错误码体系（L596-609）：11 种错误码，每种标注 HTTP 状态码和可重试性
- PoW 求解超时 → 自动重新获取 challenge + 重试（L135-137）
- 用户名已占用 → 自动重试新用户名（L137）
- 密码重置（§10.2, L644-679）：两步流程，token 15min TTL + 一次性消费
- 账号删除：30 天 grace period（L735）
- AI Agent 凭据丢失恢复路径（L136）

**评分**: ✅ 错误恢复覆盖全面。

### C8 — argon2id 参数 ✅ FIXED

**R1 问题**: argon2id 常量未连接到 Argon2 实例。

**R2 修正**:
- `hash_password` 显式构造 `Params::new(19_456, 2, 1, Some(32))`（L287-306）
- 显式 `Argon2::new(Algorithm::Argon2id, Version::V0x13, params)`（L300）
- 实现者注意：**不得使用** `Argon2::default()`（L321）
- OWASP 2025 推荐参数：19 MiB, 2 iterations, parallelism=1

**微瑕**: `verify_password` 中使用了 `Argon2::default()`（L315），虽然验证时参数来自 PHC string，但未校验存储的 hash 参数是否匹配期望值（见下方 M1）。

**评分**: ✅ hashing 侧修正正确。verification 侧见新发现 M1。

### D1 — Auth 独立控制面 ✅ CLOSED

§3 架构图 + 职责分离表充分表达。配置项 `[auth]` 段独立于游戏配置。**闭案**。

### D2 — Login PoW 可配置 ✅ CLOSED

§8.4 + 附录 C 完整覆盖。4 个可配置参数 + 运行时开关。**闭案**。

### D3 — 用户名可见性配置 ✅ CLOSED

§6.2 提供 `public` / `private` 两种模式，含完整的 FDB 事务内消费策略差异。**闭案**。

### D4 — 三层身份 ✅ CLOSED

§6.1 明确定义 `login_username` → `display_name` → `player_id`。**闭案**。

---

## 2. 新增安全发现

### H1 — 联邦吊销传播采用 stale-as-valid 策略 [Medium]

**位置**: auth.md §14.5 (L849-852)

**描述**: 联邦跨世界身份验证中，当远程世界不可达时，本世界使用本地缓存的吊销列表，且 "stale 视为有效——可用性优先"。这意味着：

1. 攻击者控制 World A 后撤销证书
2. 对 World B 发动 DoS，阻止其访问 World A 的 `GET /auth/revocations` 端点
3. World B 接受已被 World A 撤销的证书

**影响**: 已被远程世界吊销的证书在本地世界仍可被接受，绕过联邦信任模型。

**建议**:
- 为 stale revocation list 设置最大年龄（如 1h），超过后拒绝未知证书（安全优先模式）
- 或提供配置开关 `federation.revocation_fallback = "reject"` / `"accept"`
- 考虑 gossip 协议在联邦世界间主动推送吊销事件，降低对轮询的依赖

### H2 — 账号删除 "transfer" 模式缺少防滥用机制 [Medium]

**位置**: auth.md §12 (L729-733)

**描述**: 资产处置策略含 `"transfer": 转移到指定 player_id（需该玩家确认）`。但未定义确认机制（链上签名？链下同意？），存在以下风险：

1. 删除者指定受害者 player_id
2. 受害者意外确认（UI 误导 / 社会工程）
3. 大量 drone/建筑突然转入受害者账户，可能触发反作弊或改变世界平衡

**影响**: 恶意玩家可通过此机制骚扰他人或破坏游戏经济。

**建议**:
- Transfer 确认必须使用 Ed25519 签名（接收方用私钥签名确认）
- 确认消息需包含删除者 player_id + 资产摘要
- 设置 transfer 冷却期（如 24h）和接收方可拒绝选项
- 或者初期仅支持 "abandon" 和 "recycle" 模式，将 "transfer" 作为后续功能

### H3 — auth.md 未交叉引用 MCP transport 安全要求 [Medium]

**位置**: auth.md 整体 vs 03-mcp-security.md §2

**描述**: auth.md §4.2-4.3 描述 AI agent 通过 MCP 进行注册/登录，但未引用 03-mcp-security.md §2 中定义的 transport 安全合同：
- AI agent 端点要求 mTLS 或 Ed25519 签名（03-mcp-security.md L108-111）
- Token `aud` field 绑定 client type（`"cli"` vs `"browser"`）
- 拒绝跨协议混淆请求（L111）

密码和 refresh_token 在非浏览器环境下通过不安全的 transport 传输将完全暴露。

**影响**: 实现者可能仅参考 auth.md 而忽略 transport 安全要求，导致 AI agent 凭据在网络上明文传输。

**建议**: auth.md §4.2 和 §4.3 加入明确的 transport 安全引用：
```
> **Transport 安全**: AI agent 的 MCP 连接必须使用 mTLS 或 Ed25519 签名请求。
> 详见 design/03-mcp-security.md §2.2。
```

---

### M1 — verify_password 未校验存储 hash 的参数 [Low]

**位置**: auth.md §5.1 (L308-318)

**描述**: `verify_password` 仅校验 `parsed.version != Some(Version::V0x13)`，未校验 hash 中的 m/t/p 参数。若攻击者能向 FDB 写入弱参数 hash（如 m=4096,t=1），验证将接受它。

**缓解**: 需要 FDB 写权限（已等同于完全 compromise），且 hash_password 始终使用强参数。此问题在纵深防御层面存在，但不构成独立攻击面。

**建议**: 添加参数校验：
```rust
let expected_params = Params::new(ARGON2_MEMORY_KIB, ARGON2_ITERATIONS, ARGON2_PARALLELISM, Some(32))?;
if parsed.params != expected_params {
    return Err(McpError::internal_error("stored hash uses unexpected params"));
}
```

### M2 — 密码重置响应时间未做常量时间处理 [Low]

**位置**: auth.md §10.2 (L658-659)

**描述**: `swarm_request_password_reset` 设计为 "无论邮箱是否存在，统一返回成功"。但若实现中 `email lookup → token generation → FDB write` 与 `no-op return` 路径耗时不同，攻击者可通过时序侧信道枚举邮箱。

登录已通过 dummy argon2id 消除此类侧信道（L591），密码重置路径应采用类似策略（对不存在的邮箱执行 dummy token 生成）。

**建议**: 对不存在的邮箱也执行完整 token 生成 + FDB write（写入到一个 discard subspace），确保两条路径耗时相同。

### M3 — AI agent 私钥存储指引不足 [Low]

**位置**: auth.md §4.2 (L128-132) 和 §13.4 (L770-772)

**描述**: AI agent 必须存储 `client_secret_key`（Ed25519 私钥），但存储指引仅一行提及"环境变量"。私钥泄露 = 攻击者可冒充 AI agent 部署恶意 WASM，比密码泄露更严重。

**建议**: 
- 明确私钥存储优先级：硬件安全模块/secret manager > 加密文件(0600) > 环境变量
- 私钥不得出现在日志、MCP 请求/响应中
- 建议提供 CLI 工具 `swarm keygen --output /secure/path/key.pem` 生成并安全存储

---

### I1 — 邮箱非唯一性允许有限枚举 [Informational]

**位置**: auth.md §11 (L699)

**描述**: 明确设计为 "一个邮箱可被多个账号绑定"。虽有限速 1 次/5 分钟，攻击者仍可通过密码重置响应时间差异（见 M2）枚举邮箱是否绑定到任何账号。接受此风险为设计权衡。

---

## 3. 安全亮点

1. **纵深防御的登录防护**: dummy argon2id + 统一错误码 + per-account 失败计数 + 可选 Login PoW + per-username 限速，形成 5 层防线
2. **PoW 密码学正确性**: 服务端 FDB 权威 challenge，客户端不可降级；bit 粒度难度；一次性消费 + TTL
3. **Refresh token rotation 设计规范**: 每次使用后轮换 + grace period 防竞态 + client_public_key 绑定，符合 IETF BCP
4. **三层身份模型**: login_username(不可变) / display_name(可变) / player_id(deterministic hash)，干净分离认证主体、展示层、引擎标识
5. **Auth 控制面独立**: 清晰的组件职责分离表 + FDB subspace 隔离，Engine 不持有密码库
6. **Agent 代理安全交付**: handoff code 而非裸 token 返回给人类（L152-156），防聊天日志泄露
7. **配置即文档**: 附录 C 完整 world.toml `[auth]` 段，所有参数有默认值和说明
8. **测试策略全面**: 70+ 测试用例覆盖 identity/password/PoW/register/login/session/federation/email/delete 全生命周期
9. **错误恢复闭环**: 11 种错误码 + 可重试性标注 + PoW 超时自动重试 + 密码重置两步流程
10. **联邦身份隐私隔离**: 不同世界的同一联邦玩家拥有独立 player_id 和资产（L844），身份可跨世界但游戏状态隔离

---

## 4. 修正优先级

| 优先级 | ID | 问题 | 建议阶段 |
|--------|-----|------|---------|
| P0 | — | （无 Critical 发现） | — |
| P1 | H1 | Federation stale-as-valid | Phase 1 配置项 |
| P1 | H2 | 账号删除 transfer 防滥用 | Phase 1 实现前 |
| P2 | H3 | auth.md transport 交叉引用 | Phase 1 文档同步 |
| P3 | M1 | verify_password 参数校验 | Phase 1 实现 |
| P3 | M2 | 密码重置常量时间 | Phase 1 实现 |
| P3 | M3 | AI agent 私钥存储指引 | Phase 2 或文档 |

---

## 5. 评审总结

R2 auth.md (1236行) 从安全角度看是一次高质量的设计修正。R1 发现的 3 个 High 问题均已通过正确的密码学方案和架构调整得到修复：

- **PoW 权威绑定**: 服务端 FDB 权威值，客户端不可控 — 密码学正确
- **argon2id 参数**: 显式构造，包含 OWASP 推荐参数 — hashing 侧正确
- **认证纵深防御**: 5 层防线，远超单一机制 — 设计优秀

新增发现均为 Medium 以下，集中在联邦信任边界操作细节和文档交叉引用完整性。所有问题可在 Phase 1 实现前以低开销修正。

**建议批准进入 Phase 1 实现，前提是 H1/H2 在实现前完成设计收敛。**
