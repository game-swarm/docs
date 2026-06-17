# R2 Auth Architecture Review — rev-gpt-architect

## Verdict

CONDITIONAL_APPROVE

R2 已正确修复 R1 共识 Blocker 的核心架构问题：Auth 不再下沉为游戏 tick/Engine 的隐式逻辑，PoW 不再信任客户端 difficulty，Identity/FDB/Session/联邦身份均形成了可实现的边界合同。剩余问题主要是跨文档口径与落地顺序，不构成继续设计返工的 P0，但应在实现前作为 P1 文档同步项关闭。

## Strengths

1. Auth 控制面边界明显比 R1 稳定

`auth.md` 将注册、登录、PoW、密码哈希、限速、refresh token/session 生命周期放入独立 Auth domain；Engine 仅消费已签发身份/证书，不持有密码库。组件职责表也明确 Auth Service 持有 password_hash/challenge/login_fail/session，Engine 持有 CertificateIssuer 私钥但不持有密码、PoW challenge state 或 login 计数。这解决了 R1 中“认证逻辑被塞进 Engine/game core，未来会污染模拟边界”的 blocker。

2. PoW 服务端绑定已闭合

`swarm_register` 请求只提交 `challenge_id + nonce`，明确不包含客户端回传的 `challenge` 或 `difficulty`。服务端在同一个 FDB 事务中读取 `auth/challenges/<challenge_id>` 的权威 challenge/difficulty，检查 TTL/consumed，再验证前导零 bit 并原子消费 challenge。这修复了 R1 对“客户端可降级 difficulty / 替换 challenge”的 P0 质疑。

3. Identity 模型从单一 player_id 变成三层合同

R2 区分了 `login_username`、`display_name`、`player_id`：登录名不可变且大小写归一，显示名可修改，player_id 为 provider namespace 下的确定性 hash。本地、OAuth2、联邦身份各自有 namespace 规则，并通过 `auth/identities/<provider>/<subject>` 做唯一索引。这比 R1 的 “IdentityKey/PlayerId/session 混在一起” 明显更容易实现和解释。

4. FDB subspace 从概念变成可操作 schema

`auth/users/`、`auth/identities/`、`auth/challenges/`、`auth/sessions/`、`auth/login_fail/`、`auth/revocations/`、`auth/reset/`、`auth/email_verify/` 均有 key/value 草案，并要求 `schema_version`。同时说明密码哈希在事务外执行、FDB 事务保持短生命周期、冲突重试最多 3 次。这基本避免了把高延迟 argon2id 放进 FDB transaction 的常见失败模式。

5. Login 抗爆破方案走向实用主义

R2 没有把 login PoW 作为默认强制路径，而是默认关闭，依赖 per-account 限速、失败计数、dummy argon2id，并可在阈值后触发 login PoW。这个选择比“所有登录都 PoW”更适合真实用户体验，也能覆盖分布式低速爆破的主要路径。

6. 联邦身份方向正确

联邦登录不是直接把外部 `player_id` 带入本世界，而是通过 trusted issuer 验证外部证书后，本地映射为 `blake3("federated:" + world_id + ":" + original_player_id)` 并由本地 `CertificateIssuer` 重签。这个模式接近成熟 federation 系统的边界：外部身份只用于认证，本地权限和资产仍归本世界控制。

## Concerns

### A1 — P1 — `auth.md` 与 `03-mcp-security.md` 的 token 权威模型仍不一致

`auth.md` 的新模型以 `PlayerCertificate + refresh_token + session` 为主，并描述 session 绑定 `(player_id, client_public_key)`、refresh token rotation、证书 24h TTL。`03-mcp-security.md` 仍写着 “JWT，由网关 OAuth2 签发”，字段只有 `sub/scope/iat/exp/jti`，且没有反映本地 auth、federated login、client_public_key binding、refresh token rotation，也与后文 browser/cli `aud` 绑定要求没有合并成同一个权威 token schema。

这不是架构不可行，但非常容易让实现者分裂出两套认证路径：一套 OAuth JWT，一套本地 PlayerCertificate/session。实现前应指定唯一权威模型：哪些请求使用 JWT access token，哪些使用 PlayerCertificate，二者如何互换或是否合并，`aud`、`world_id`、`client_public_key`、`issuer`、`jti` 分别在哪个对象上。

### A2 — P1 — `CertificateIssuer` 位于 Engine 但 Auth 是独立控制面，签发调用边界还需要接口合同

R2 职责表说 Auth Service 不持有 PlayerCertificate 私钥，Engine 持有 CertificateIssuer 密钥对；同时注册/登录流程在 Auth Service 内返回 `LoginResult {player_id, session, certificate}`。这留下一个实现边界问题：Auth Service 如何请求 Engine 签发证书？是进程内模块调用、内部 RPC、还是由独立 signer service 暴露最小签发接口？

当前文档说 `src/auth/ (Engine 内或独立服务)`，这在设计阶段可以接受，但实现阶段必须二选一或定义 signer adapter。否则“Auth 独立控制面”会在代码里退化成 Engine 内部大模块，R1 的边界污染风险会以另一种形式回来。

### A3 — P1 — `auth/identities` 碰撞处理与错误语义过度绑定 `username_taken`

R2 说明 player_id 取 u64，百万用户碰撞概率可接受，并在 `auth/identities/` 唯一索引冲突时返回 `username_taken`。这对本地 username 冲突成立，但对 OAuth2 provider subject、federated identity 或真实 hash collision 来说不完全准确。建议区分：`username_taken`、`identity_conflict`、`player_id_collision`。尤其 federation 下，冲突可能不是用户可通过“换用户名”解决的问题。

### A4 — P2 — 账号删除与身份索引释放策略需要更精确

账号删除设计包含 `deleted_at`、30 天 grace period、永久清除后释放 `login_username`。但 `auth/identities/<provider>/<subject>` 与 `auth/users/<login_username>` 在 grace period、恢复、永久释放时的状态机尚未展开。若实现者只释放 users key 而保留 identities key，会导致用户名不可重新注册；若过早释放 identities key，则恢复期和历史审计会混乱。

### A5 — P2 — Argon2 验证示例与“不得使用 default”备注存在小型自相矛盾

文档先给出显式 `Params` 的 `hash_password`，但 `verify_password` 示例仍调用 `Argon2::default()`；随后备注又说不得使用 `Argon2::default()`，必须显式构造参数并测试 PHC 字符串包含 `m=19456,t=2,p=1`。这不会推翻设计，但应避免实现者直接复制错误示例。

### A6 — P2 — 文档章节编号多处漂移

`auth.md` 中联邦身份章节出现 `## 14` 下 `### 18.1`、`### 18.2`、`### 15.3` 等编号漂移，后续前端/安全/实现范围也有类似问题。编号问题本身不影响架构，但会降低新人阅读和引用准确性；在进入实现前应整理。

## Missing

1. 单一 Auth Token/Certificate 规范

需要一页权威规格定义：`LoginResult` 完整字段、`PlayerCertificate` payload、refresh token 存储/哈希格式、access token 是否存在、JWT 与 certificate 的关系、browser/cli audience 如何表达、revocation key 用 signature 还是 jti。

2. Auth Service 与 CertificateIssuer 的签发接口

需要明确 `issue_certificate(player_id, client_public_key, scopes, audience, ttl)` 这样的内部接口，以及 Auth Service 是否能直接调用、是否需要 mTLS/internal capability、签发失败如何恢复。

3. Federation revocation 的一致性策略

当前 “外部世界不可达时 stale 视为有效——可用性优先” 是合理默认，但应加上最大 stale TTL、风险提示、可配置模式（strict vs available）。否则高安全世界无法表达“远端不可达则拒绝联邦登录”。

4. 账号生命周期状态机

需要补一张状态机：active → deleted(grace) → restored/permanently_purged，以及各状态下 login、token_refresh、federated_login、username reuse、identity index 的行为。

5. 实现测试与文档同步门禁

测试列表很好，但还应把跨文档一致性作为检查项：`interface.md`、`auth.md`、`03-mcp-security.md` 对认证工具、token 字段、audience、scope 的描述不得互相冲突。

## Phase Ordering

1. Phase 0 — 文档收敛门禁

先关闭 A1/A2：统一 `LoginResult`/Token/Certificate schema，明确 Auth Service ↔ CertificateIssuer 边界。没有这一步就开写代码，最容易生成两套 auth 栈。

2. Phase 1 — Auth core 最小闭环

实现 username normalization、password policy、argon2id 显式参数、FDB auth subspace、register challenge、server-authoritative PoW、register/login、dummy argon2id、per-account fail counter。此阶段不做邮箱、删除、federation。

3. Phase 2 — Session 与 certificate 生命周期

实现 refresh token hash 存储、rotation/grace period、client_public_key binding、certificate signing/verification、revocation。此阶段必须与 `03-mcp-security.md` 的 browser/cli audience 合并验证。

4. Phase 3 — UX 与恢复路径

实现前端 LoginButton、Web Worker PoW、错误码映射、password reset、email verification、agent handoff code。这样可避免核心 auth 未稳定时先做 UI。

5. Phase 4 — Federation

在本地 auth/session/certificate 稳定后再做 trusted issuer、external certificate verification、本地重签、revocation cache。Federation 不应与本地注册/登录同批上线。

6. Phase 5 — Account deletion 与长期治理

最后实现账号删除、grace period、asset disposal、username reuse、identity index purge/recover 状态机，并补充审计与运维工具。

## Final Verdict

CONDITIONAL_APPROVE

R1 的 P0 共识 Blocker 已被 R2 正确修正：Auth 控制面边界、PoW 服务端绑定、Identity/FDB subspace、login 抗爆破、token/session 生命周期、联邦身份方向均有明确可实现设计。批准进入实现准备，但必须先完成 A1/A2 的文档收敛，否则实现阶段大概率分裂成 OAuth JWT、本地证书、MCP token 三套并存的混乱认证栈。
