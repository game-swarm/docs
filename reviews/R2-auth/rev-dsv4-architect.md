# R2 复检验证 — 架构师评审报告

> **评审员**: rev-dsv4-architect (DeepSeek V4 Pro)
> **轮次**: R2 (R1 共识修正复检)
> **评审范围**: auth.md (1236行) + interface.md + tech-choices.md + README.md + 03-mcp-security.md
> **日期**: 2026-06-17

---

## Verdict: APPROVE ✅

所有 R1 共识 Blocker (C1-C8, D1-D4) 均正确修正。文档质量高，架构清晰，测试策略完备。发现 4 个非阻塞性 Observation，均不影响通过。

---

## R1 修正逐项验证

### C1 — PoW 服务端绑定 ✅ FIXED

| 检查点 | 状态 |
|--------|:----:|
| `swarm_register` 参数仅含 `challenge_id + nonce`，无客户端 challenge/difficulty | ✓ (auth.md L460-469) |
| 服务端从 FDB 读取权威 challenge+difficulty | ✓ (auth.md L475-476) |
| 服务端拒绝客户端提供的 challenge/difficulty | ✓ (auth.md L905) |
| 测试覆盖 | ✓ (L1000-1002: 3 个专项测试) |

**评价**: 安全设计正确。客户端无法降级难度或替换 challenge——FDB 是唯一权威源。

### C2 — Difficulty Bit 粒度 ✅ FIXED

| 检查点 | 状态 |
|--------|:----:|
| 难度以 bit 为单位（非字节） | ✓ (auth.md L414-441) |
| 可配置值: 16/20/24/28 | ✓ (auth.md L446-452, world.toml:24) |
| 前端从服务端 challenge 响应获取 difficulty，不做客户端假设 | ✓ (auth.md L888) |
| Bit 边界精确测试 | ✓ (L998-999) |

**评价**: bit 级粒度允许细粒度调节。Web Worker 进度条基于 difficulty_bits 计算期望值。

### C3 — Login 抗爆破 ✅ FIXED

| 检查点 | 状态 |
|--------|:----:|
| Per-account 失败计数 (跨 IP) | ✓ (auth.md L611-612, FDB auth/login_fail/) |
| 滑动窗口 5次/300秒 → 锁定 300秒 | ✓ (auth.md L1215-1217) |
| Login PoW 可配置触发 (开关 + 难度) | ✓ (auth.md L500-514) |
| Dummy argon2id 防时序 (不存在用户) | ✓ (auth.md L589-590, L910-911) |
| 分布式低速爆破保护 | ✓ (auth.md L909, 跨 IP 失败计数) |
| 测试覆盖 | ✓ (L1058-1067: 7 个专项测试) |

**评价**: 多层防御——per-account 计数 + 递增延迟 + 可配置 PoW 触发 + dummy argon2id。不依赖 IP 限速（IP 可更换）。

### C4 — Auth 控制面边界 ✅ FIXED

| 检查点 | 状态 |
|--------|:----:|
| "Auth 独立控制面" 明确声明 | ✓ (auth.md L23-26) |
| 职责分离表 (Auth/Engine/Gateway) | ✓ (auth.md L92-96) |
| Engine 不持有密码库/PoW/login计数 | ✓ (auth.md L70-75) |
| FDB subspace 独立于游戏世界状态 | ✓ (auth.md L327, auth/ 前缀) |

**评价**: 边界清晰。`CertificateIssuer` 是 Engine 与 Auth 的唯一契约——Auth 签发身份，Engine 消费身份，互不渗透。

### C5 — Identity / FDB Model ✅ FIXED

| 检查点 | 状态 |
|--------|:----:|
| 三层身份完整定义 (login_username/display_name/player_id) | ✓ (auth.md L349-364) |
| player_id 确定性推导 (blake3→u64) | ✓ (auth.md L359-362) |
| 碰撞概率计算 (10^6→2.7×10^-8) | ✓ (auth.md L363) |
| FDB identity 唯一索引 + 碰撞检测 | ✓ (auth.md L364, auth/identities/) |
| schema_version 字段 (未来迁移) | ✓ (auth.md L338) |
| 事务约束明确 (重试3次, <10ms) | ✓ (auth.md L341-343) |
| 测试覆盖 | ✓ (L976-979: 4 个专项测试) |

**评价**: 三层模型精确。与 OAuth2 `oauth_player_id()` 同模式（provider:subject → blake3 → u64），联邦身份用 `federated:world_id:original_id` 隔离命名空间。

### C6 — Token 安全 ✅ FIXED

| 检查点 | 状态 |
|--------|:----:|
| Token 生命周期明确 (access 15min / refresh 30d / cert 24h) | ✓ (auth.md L743-748) |
| Refresh token rotation (使用即轮换) | ✓ (auth.md L750-754) |
| Grace period 5min (防竞态) | ✓ (auth.md L753-754) |
| Session 绑定 (player_id, client_public_key) | ✓ (auth.md L758) |
| 浏览器安全 (CSP, Trusted Types, HTTPS, CSRF天然免疫) | ✓ (auth.md L762-766) |
| AI Agent 凭据存储指南 | ✓ (auth.md L770-772) |
| 日志脱敏 (refresh_token 不在 URL/Referrer/日志) | ✓ (auth.md L766) |
| 测试覆盖 | ✓ (L1069-1073: 4 个专项测试) |

**评价**: 完整的 token 生命周期管理。非 cookie 方案天然免疫 CSRF。rotation + grace period 是分布式系统标准实践。

### C7 — 错误恢复 ✅ FIXED

| 检查点 | 状态 |
|--------|:----:|
| 完整错误码表 (10 种错误码 + HTTP 状态 + 可重试标记) | ✓ (auth.md L594-609) |
| 人类注册错误恢复流程 | ✓ (auth.md L111-115) |
| AI agent 错误恢复流程 | ✓ (auth.md L128-137) |
| 密码重置流程 (两步, email based) | ✓ (auth.md L644-680) |
| 账号删除 grace period (30天) | ✓ (auth.md L735-736) |
| 凭据丢失恢复路径 | ✓ (auth.md L136, L916) |

**评价**: 错误码体系完善——每种错误有明确的客户端行动指引（可重试/换用户名/等待）。密码重置为完整的两步流程。

### C8 — argon2id ✅ FIXED

| 检查点 | 状态 |
|--------|:----:|
| 算法: argon2id (OWASP 2025) | ✓ (auth.md L275-276) |
| 参数: 19MiB / 2 iterations / parallelism 1 | ✓ (auth.md L287-289) |
| 显式构造 Params (禁止 `Argon2::default()`) | ✓ (auth.md L321) |
| PHC 字符串验证 (m=19456,t=2,p=1) | ✓ (auth.md L321) |
| 常量时间比较 | ✓ (auth.md L914, argon2 crate) |
| 密码哈希在 FDB 事务外执行 | ✓ (auth.md L341, L406) |
| 测试覆盖 | ✓ (L982-991: 6 个专项测试) |

**评价**: 参数选择合理——19MiB 是现代硬件可接受的开销，2 iterations 在 OWASP 推荐范围内。明确禁止使用 default 构造器，强制显式参数。

### D1 — Auth 独立控制面 ✅ FIXED

| 检查点 | 状态 |
|--------|:----:|
| 架构图显示 Auth Service / Domain 独立于 Engine | ✓ (auth.md L57-67) |
| 限速独立于游戏 tick | ✓ (auth.md L610) |
| MCP tools 按 domain 组织 | ✓ (interface.md L37-56) |

### D2 — Login PoW 可配置 ✅ FIXED

| 检查点 | 状态 |
|--------|:----:|
| world.toml [auth.login_pow] 4 项配置 | ✓ (auth.md L1220-1225) |
| 支持运行时开关 (无需重启) | ✓ (auth.md L514) |
| 默认关闭 | ✓ (auth.md L505) |

### D3 — 用户名可见性可配置 ✅ FIXED

| 检查点 | 状态 |
|--------|:----:|
| `auth.username_visibility = "public"/"private"` | ✓ (auth.md L378-388) |
| 两种模式的 PoW 消费策略明确 | ✓ (auth.md L492-496) |
| 测试覆盖 public/private 两种模式 | ✓ (L1010-1011) |
| Login 统一返回 `invalid_credentials` | ✓ (auth.md L387) |

### D4 — 三层身份 ✅ FIXED

| 检查点 | 状态 |
|--------|:----:|
| login_username / display_name / player_id 三层 | ✓ (auth.md L349-364) |
| login_username 不可变 | ✓ (auth.md L352) |
| display_name 可通过 MCP tool 修改 | ✓ (auth.md L531) |
| player_id 确定性推导 | ✓ (auth.md L359-362) |

---

## 新增功能验证

| 功能 | 状态 | 位置 |
|------|:----:|------|
| 密码修改 (swarm_change_password) | ✅ | auth.md §10.1, L622-642 |
| 密码重置 (两步 + email) | ✅ | auth.md §10.2, L644-680 |
| 邮箱绑定/验证 | ✅ | auth.md §11, L682-708 |
| 账号删除 (grace period) | ✅ | auth.md §12, L712-737 |
| 联邦跨世界身份 | ✅ | auth.md §14, L776-852 |
| OAuth2 联合登录 (GitHub/Google) | ✅ | auth.md §4.4, L160-269 |
| AI agent MCP 自注册 | ✅ | auth.md §4.2, L117-138 |
| Agent 代理注册 + handoff code | ✅ | auth.md §4.3, L140-157 |
| 前端 LoginButton.tsx 扩展 | ✅ | auth.md §15, L855-895 |
| PoW Web Worker 实现 | ✅ | auth.md 附录 B, L1168-1205 |

---

## 跨文档一致性

| 检查 | 结果 |
|------|:----:|
| README.md → auth.md 引用匹配 | ✅ "本地注册/登录、OAuth2、联邦身份、密码管理、账号生命周期" |
| interface.md MCP 工具表 ↔ auth.md §9.1 | ⚠️ 见 Observation 2 |
| 03-mcp-security.md → auth.md 交叉引用 | ✅ "完整的认证设计...见 design/auth.md" |
| tech-choices.md Blake3/Ed25519 ↔ auth.md | ✅ 一致 |

---

## Strengths (架构亮点)

1. **Auth 控制面隔离** — 清晰的职责分离：Auth 管理凭据/会话/限速，Engine 仅消费证书。密码库不在 Engine 中，PoW 状态不在 Engine 中。这是安全架构的正确做法。

2. **服务端 PoW 权威绑定** — 客户端仅提交 `challenge_id + nonce`，challenge 和 difficulty 完全由服务端从 FDB 读取。彻底杜绝客户端降级攻击。设计清晰、可验证。

3. **多层防爆破** — per-account 失败计数（跨 IP）+ 递增延迟 + 短期锁定 + 可选 PoW 触发。不依赖 IP 限速（IP 可更换），核心防护在账号级别。

4. **Token 生命周期完整** — access(15min) / refresh(30d rotation + 5min grace) / cert(24h)。rotation + grace period 是处理分布式竞态的标准方案。

5. **三层身份模型** — login_username(不可变) / display_name(可变) / player_id(u64 确定性 hash)。与 OAuth2、联邦身份完全统一的推导模式。碰撞概率可量化（2.7×10^-8 for 10^6）。

6. **联邦身份设计** — 信任模型清晰（world.toml `trusted_issuers`），身份映射按世界隔离（`federated:world_id:original_id`），资产不跨世界共享。撤销传播有降级策略。

7. **账号生命周期完整** — 注册 → 登录 → 密码管理 → 邮箱绑定 → 删除(grace period)。每个状态转换都有明确定义。

8. **测试策略卓越** — 70+ 测试用例覆盖所有核心路径，包括边缘情况（常量时间比较、PoW bit 边界、username visibility 两种模式、refresh token grace period、federation 隔离）。

---

## Observations (非阻塞性发现)

### O1 — Section Numbering Inconsistency (Medium, Cosmetic)

auth.md 中存在段落编号混乱——疑似从不同草稿合并时的复制遗留：

| 段落 | 当前编号 | 应为 |
|------|---------|------|
| §13 Token 安全 | 10.2, 10.3, 10.4 | 13.2, 13.3, 13.4 |
| §14 联邦身份 | 18.1, 18.2, 15.3, 14.4 | 14.1, 14.2, 14.3, 14.4 |
| §15 前端变更 | 18.1, 18.2, 15.3 | 15.1, 15.2, 15.3 |
| §16 安全考量 | 18.1, 18.2 | 16.1, 16.2 |
| §17 实现范围 | 13.1, 13.2 | 17.1, 17.2 |

**影响**: 不影响设计正确性，但会混淆实现者——特别是 §16 安全考量中的 "18.1 威胁模型" 引用不匹配。

**建议**: 全文统一编号。R2 可 defer，Phase 1 实现前修。

### O2 — interface.md 缺少 `swarm_login_challenge` (Low, Doc Gap)

- auth.md §9.1 (L527) 定义了 `swarm_login_challenge` 工具
- interface.md MCP 工具表中未列出该工具
- 该工具仅在 login PoW 触发时暴露——不影响常规流程，但文档应保持完整

**建议**: interface.md MCP 工具表补充 `swarm_login_challenge`。

### O3 — Login verify_password 后 FDB 事务时序 (Low, Theoretical)

auth.md 设计：login 流程为 (1) 读取 FDB `auth/users/` + `auth/login_fail/` → (2) argon2id verify (~100ms) → (3) 写入 FDB 更新 fail_count。步骤 2 在事务外（正确），但同一用户的并发 login 请求可能在步骤 3 产生 FDB conflict。

**分析**: FDB 的重试机制（3次）能处理此场景。但文档未显式说明 login 的 FDB transaction 边界和冲突恢复策略。

**建议**: 在 §9.4 login 流程中增加一句 "并发 login 更新 fail_count 由 FDB 事务重试处理"。

### O4 — 联邦撤销 "stale=valid" 可用性取舍 (Low, Documented)

auth.md L848-851: "若外部世界不可达：使用本地缓存的吊销列表（stale 视为有效——可用性优先）"

这是明确的安全 vs 可用性取舍——已正确文档化。但未提供 "stale timeout" 上限（缓存的有效期阈值）。无限期使用 stale 吊销列表存在风险。

**建议**: 增加 `revocation_cache_stale_seconds` 配置项（如 3600），超时后拒绝外部证书而非默认信任。

---

## Algorithmic & Consistency Analysis

### 数据一致性路径

```
注册: client → PoW challenge (FDB read) → solve PoW → POST register(challenge_id, nonce)
      → FDB 事务: verify PoW (server authoritative) + check identity conflict + insert user + mark challenge consumed
      → Engine CertificateIssuer 签发证书

登录: client → POST login(username, password, pubkey)
      → FDB read: user record + fail count
      → 事务外: argon2id verify (~100ms)
      → FDB write: update fail_count (retry on conflict)
      → Engine CertificateIssuer 签发证书

Token refresh: client → POST token_refresh(old_token, pubkey)
      → FDB 事务: verify session + mark old consumed + insert new session
      → Engine CertificateIssuer 重签证书
```

**评价**: 读写路径清晰。关键写操作在 FDB 事务内且使用 auth/ 前缀隔离。密码哈希在事务外是正确优化。FDB 的严格可序列化保证 auth 数据一致性。

### 复杂度分析

| 操作 | 复杂度 | 关键路径 |
|------|--------|---------|
| 注册 | O(1) FDB read + O(2^difficulty) PoW + O(1) FDB write | PoW 客户端侧 ~150ms (24bit Rust) |
| 登录 | O(1) FDB read + O(1) argon2id + O(1) FDB write | argon2id ~100ms 服务端 |
| Token refresh | O(1) FDB read + O(1) FDB write | <1ms |
| 联邦登录 | O(1) cert verify + O(log N) issuer lookup | Ed25519 verify ~30μs |

无计算爆炸风险。PoW 成本在客户端，服务端仅执行一次 blake3 hash 验证（<1μs）。

---

## 总体评价

R2 auth 设计文档质量显著提升——从 R1 的概念框架进化为可实现的完整设计。所有 R1 Blocker 均有明确、可验证的修正。Auth 控制面隔离、PoW 服务端绑定、三层身份模型、Token 生命周期管理、联邦身份等核心架构决策均正确。

4 个 Observation 中 O1（编号混乱）是唯一建议 Phase 1 前修复的，其余 O2-O4 为低优先文档完善或非关键边缘情况。

---

## Summary

- **R1 Items Verified**: 12/12 ✅ (C1-C8 + D1-D4)
- **New Features Verified**: 10/10 ✅
- **Cross-doc Consistency**: 3/4 ✅ (1 minor gap)
- **Observations**: 4 (0 Blocking, 1 Medium cosmetic, 3 Low)
- **Test Coverage**: 70+ cases specified
