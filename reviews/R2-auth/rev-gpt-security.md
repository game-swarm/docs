# R2 Auth Security Re-review — GPT Security

Verdict: CONDITIONAL_APPROVE

R2 已实质修复 R1 共识中的核心 P0 blocker：PoW challenge/difficulty 改为服务端权威绑定，注册请求不再接受客户端回传 challenge/difficulty；登录路径加入 dummy argon2id、失败计数、短期锁定与可配置 Login PoW；argon2id 参数从不明确默认值收敛到显式 OWASP 参数；token/session 生命周期、refresh rotation、client_public_key 绑定与威胁模型均已补齐。

仍建议条件批准而非直接批准：登录失败路径存在一个可被最小请求放大为高成本服务端 argon2id 的 DoS 残留面；同时 login PoW 的 API 契约在 auth.md 与 interface.md 之间未完全同步，可能导致实现者跳过触发后的 challenge 参数。

## Critical

无。

## High

### H1 — 登录失败路径缺少 per-IP / per-session 限速，dummy argon2id 可能成为 CPU/内存 DoS 放大器

证据：
- `auth.md:589` 要求无论用户是否存在均执行 dummy argon2id，防止用户名枚举。
- `auth.md:287` 到 `auth.md:321` 规定每次验证使用 argon2id `m=19456,t=2,p=1`，这是正确的密码哈希强度，但也是高成本操作。
- `auth.md:610` 到 `auth.md:618` 的限速模型中，登录只有 per-username `10/min`、失败锁定和全局 `1000/min`，没有 per-IP、per-ASN、per-client 或连接级限制。
- `auth.md:908` 到 `auth.md:911` 的威胁模型覆盖暴力破解、分布式低速爆破和用户名枚举，但没有覆盖“随机不存在 username + dummy argon2id”的资源耗尽模式。

攻击模式：
攻击者持续提交随机 username，每个 username 都不会命中 per-account 锁定；为了防枚举，服务端又必须执行 dummy argon2id。这样最小请求体可稳定触发 19MiB argon2id 工作，直到只受全局 1000/min 限制约束。全局限速不足以隔离单一恶意来源，也会把攻击者成本转嫁给所有正常用户。

修正建议：
- 登录端点增加 per-IP / per-prefix / per-client_public_key 或网关连接级限速，例如 `30/min/IP`，并与 per-username 锁定叠加。
- 对不存在用户的 dummy argon2id 继续保留，但应受 IP 级令牌桶保护；达到阈值后统一返回 `rate_limited`，避免进入 argon2id。
- 将该场景加入 `auth.md` 威胁模型与测试：`test_login_random_username_rate_limited_before_dummy_argon2id_amplification`。

## Medium

### M1 — Login PoW 触发后的请求契约不完整，存在实现歧义

证据：
- `auth.md:499` 到 `auth.md:514` 定义了可配置 Login PoW，并说明触发后该 username 的登录请求需要 PoW。
- `auth.md:526` 将 `swarm_login` 参数仍列为 `username`, `password`, `client_public_key`。
- `auth.md:527` 增加了 `swarm_login_challenge`，但 `auth.md:575` 到 `auth.md:592` 的 `swarm_login` 示例未展示触发后如何携带 `challenge_id` 与 `nonce`。
- `interface.md:37` 到 `interface.md:50` 的认证工具表缺少 `swarm_login_challenge`，与 auth.md 不一致。

风险：
实现者可能只实现错误码 `login_pow_required`，但没有清晰的第二次登录请求参数；也可能把 login PoW 与 register PoW 混用，或在接口层遗漏 `swarm_login_challenge`，导致 R1 的 C3/D2 修正无法可靠落地。

修正建议：
- 明确 `swarm_login` 在 PoW 触发时接受可选 `challenge_id` 与 `nonce`，并声明同样禁止客户端提交 challenge/difficulty。
- 在 `interface.md` 认证工具表补上 `swarm_login_challenge`。
- 添加测试：`test_login_pow_submission_uses_server_authoritative_challenge`、`test_login_pow_rejects_client_supplied_difficulty`。

### M2 — Refresh token rotation 的 5 分钟 grace period 语义过宽，需限制“旧 token 可接受一次”的原子消费

证据：
- `auth.md:750` 到 `auth.md:754` 定义 refresh token 每次使用后轮换，旧 token 在 rotation 后 5 分钟内仍可被接受一次。
- `auth.md:758` 规定 session 绑定 `(player_id, client_public_key)`，这是重要缓解。

风险：
如果“可接受一次”没有在 FDB 中用 compare-and-set/事务字段记录二次消费状态，旧 refresh token 泄露后会形成 5 分钟 replay 窗口。即使绑定 `client_public_key`，浏览器 localStorage XSS 或 agent store 泄露通常会同时泄露 token 与 key material。

修正建议：
- 明确 rotated token 的 grace 使用必须是原子 one-shot：首次 grace 成功后立即标记 `grace_consumed_at`，后续拒绝。
- 对 grace 使用触发审计事件；若新旧 token 在不同 IP/UA/endpoint 使用，应吊销整条 session family。

## Informational

### I1 — R1 P0 修正验证结果

- C1 PoW 权威绑定：通过。`auth.md:455` 到 `auth.md:497` 明确 register 只提交 `challenge_id + nonce`，服务端从 FDB 读取 challenge 与 difficulty。
- C2 difficulty bit：通过。`auth.md:414` 到 `auth.md:441` 使用前导零 bit 而非字节；`auth.md:444` 到 `auth.md:453` 给出 16/20/24/28 bit 难度表。
- C3 login 抗爆破：部分通过。per-account、dummy argon2id、锁定和可选 Login PoW 已补齐，但缺少 per-IP 限速导致 H1。
- C4 Auth 边界：通过。`auth.md:25`、`auth.md:34` 到 `auth.md:96` 明确 Auth 独立控制面，Engine 不持有密码库/PoW/login 计数。
- C5 Identity/FDB：通过。`auth.md:323` 到 `auth.md:364` 定义 auth subspace、identities 唯一索引和三层身份。
- C6 Token 安全：基本通过。`auth.md:740` 到 `auth.md:773` 补齐 TTL、rotation、client_public_key 绑定、CSP/Trusted Types 和日志脱敏；M2 是语义加固建议。
- C7 错误恢复：通过。注册、AI agent、密码重置、错误码体系均有重试/恢复描述。
- C8 argon2id：通过。显式 `m=19456,t=2,p=1`，禁止 `Argon2::default()`，并要求测试 PHC 参数。

### I2 — 亮点

- 威胁模型比 R1 明显完整，覆盖 PoW 降级、重放、challenge DoS、用户名枚举、时序侧信道、聊天日志泄露和 reset token 泄露。
- `auth.username_visibility = private` 默认值是正确方向，避免注册前用户名枚举，同时明确 public/private 的 PoW 消费差异。
- Agent 代理注册不返回裸 refresh_token，而使用一次性 handoff code，显著降低聊天日志长期凭据泄露风险。
- Auth domain 与 Engine 责任边界清晰，减少了把密码/PoW 状态混入游戏 tick 或 WASM 执行路径的风险。

## Verdict

CONDITIONAL_APPROVE。

R1 的主要安全 blocker 已被正确修复，设计可以进入下一轮实现准备；但在落地前应修正 H1，并同步 M1 的接口契约。H1 不要求推翻设计，只需要在限速模型、威胁模型和测试策略中补齐登录路径的来源维度限流。