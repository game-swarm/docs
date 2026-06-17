# Swarm Auth Design — Consensus Report (R2)

## Overall Verdict + Convergence

**Verdict: CONDITIONAL_APPROVE**

本轮 Speaker 综合基于现有 **6/14 reviewer artifacts**：Architect/Security/Designer 三个方向 × GPT-5.5 与 DeepSeek V4 Pro 两个模型。Claude 评审官已由 operator 明确通知永久退役；R2 原始 9 人要求因此被本轮授权调整为 6 份既有报告综合。本报告结论带 provenance caveat：它反映 6 位可用 R2 reviewer 的共识，不声称覆盖已退役 Claude 视角，也不覆盖 R3 起新增的 Performance/Economy/API-DX/Determinism 四个方向。

总体收敛信号强：6/6 reviewer 均确认 R1 核心 blocker 已实质闭合；2/6 给出 APPROVE，4/6 给出 CONDITIONAL_APPROVE；0/6 要求 major changes，0/6 reject。分歧不在“是否推翻设计”，而在“进入实现前哪些文档/接口合同必须收口”。

Speaker 裁决：R2 Auth 设计可进入 Phase 1 实现准备，但应先关闭少量实现前 gate，尤其是登录 DoS 限流、Auth token/certificate 权威模型、Login PoW 接口契约、CertificateIssuer 签发边界、联邦吊销 stale 上限、账号删除恢复/transfer 语义。

## R1 修正验证 (C1-C8, D1-D4)

| ID | R1 问题 | 6-reviewer 共识状态 | Speaker 结论 |
|---|---|---:|---|
| C1 | PoW challenge 服务端权威绑定 | 6/6 CLOSED | `swarm_register` 仅提交 `challenge_id + nonce`，服务端从 FDB 读取 challenge/difficulty 并原子消费。 |
| C2 | difficulty bit 粒度与服务端权威 | 6/6 CLOSED | bit-level leading-zero 算法、16/20/24/28 难度与默认 24 bits 已明确。 |
| C3 | Login 抗爆破 | 6/6 MOSTLY_CLOSED | per-account fail count、dummy argon2id、lockout、Login PoW 已补齐；但 GPT Security 新发现 per-IP/per-session 限流缺失，作为 R2-Gate-H1 处理。 |
| C4 | Auth 独立控制面边界 | 6/6 CLOSED | Auth/Gateway/Engine 职责表与 FDB `auth/` subspace 隔离已足够关闭 R1 blocker。 |
| C5 | Identity / FDB 模型 | 6/6 CLOSED | `login_username` / `display_name` / `player_id` 三层身份、provider namespace 与 `auth/identities` 索引已明确。 |
| C6 | Token/session 安全 | 5/6 MOSTLY_CLOSED, 1/6 CLOSED | TTL、refresh rotation、client_public_key binding 已补齐；仍需统一 JWT/access_token/PlayerCertificate 权威模型与 one-shot grace 语义。 |
| C7 | 错误恢复 | 5/6 MOSTLY_CLOSED, 1/6 CLOSED | 注册、PoW、密码重置错误恢复已闭合；账号删除恢复路径仍需可执行 API/UI/MCP 合同。 |
| C8 | argon2id 参数 | 6/6 CLOSED | hashing 参数已显式化；verify 示例使用 `Argon2::default()` 与参数校验作为 Low/P2 文档修正处理。 |
| D1 | Auth 独立控制面 | 6/6 CLOSED | 设计原则、架构图、限速独立于 game tick 均已明确。 |
| D2 | Login PoW 可配置 | 6/6 CLOSED | `[auth.login_pow]` 开关、难度、触发阈值、窗口均已明确；接口契约需同步。 |
| D3 | 用户名可见性配置 | 6/6 CLOSED | `auth.username_visibility = public/private` 与 public/private PoW 消费差异已明确。 |
| D4 | 三层身份 | 6/6 CLOSED | 认证主体、显示名、引擎 ID 分离已达成共识。 |

结论：R1 P0 级设计缺口已经关闭。R2 的剩余问题属于实现前合同收敛与安全/UX 边缘收口，不需要回到 R1 级重设计。

## New Findings

### Consensus / Majority Gate Items

#### R2-Gate-H1 — 登录失败路径需要来源维度限流，避免 dummy argon2id DoS 放大

**同意者**: rev-gpt-security (High), rev-dsv4-security 间接确认 login 纵深防御但未标 High；Architect/Designer 未反对。  
**共识等级**: Security 方向 1/2 explicit；跨方向未形成 blocker，但 Speaker 升级为实现前 gate，因为它直接影响生产可用性。

问题：R2 为防用户名枚举要求不存在用户也执行 dummy argon2id，但登录限速模型主要是 per-username 与 global。攻击者可提交大量随机 username 绕过 per-account lockout，把小请求放大为 19MiB argon2id 服务端成本。

修正要求：
- 登录端点增加 per-IP / per-prefix / per-session / gateway connection 维度 token bucket。
- 达到来源限流阈值时在进入 argon2id 前统一返回 `rate_limited`。
- 威胁模型与测试补充 `random nonexistent username` DoS 场景。

#### R2-Gate-H2 — Auth token/certificate 权威模型需统一

**同意者**: rev-gpt-architect A1, rev-gpt-designer G3, rev-dsv4-security H3；rev-dsv4-architect O2/O4 部分相关。  
**共识等级**: ≥2 directions + ≥2 models，跨方向多数。

问题：`auth.md` 以 `LoginResult + PlayerCertificate + refresh_token/session` 为中心；`03-mcp-security.md` 仍保留 JWT/access_token/aud 的安全合同。当前材料没有明确 JWT、access_token、PlayerCertificate、refresh_token 的关系，容易导致实现者分裂出 OAuth JWT、本地 certificate、MCP token 三套并行认证模型。

修正要求：
- 增加单一权威 Auth schema：`LoginResult` 完整字段、`PlayerCertificate` payload、`access_token` 是否存在、JWT 与 certificate 关系、`aud/world_id/client_public_key/issuer/jti` 所属对象。
- 同步 `auth.md`、`interface.md`、`03-mcp-security.md` 的术语和工具表。
- 在 MCP AI agent 场景中明确 transport 安全引用：mTLS 或 Ed25519 signed request，避免凭据在非浏览器 transport 上裸奔。

#### R2-Gate-H3 — Login PoW 触发后的 API 契约缺口

**同意者**: rev-gpt-security M1, rev-dsv4-architect O2, rev-gpt-designer Missing schema/resource；rev-dsv4-designer 间接指出 interface 表不同步。  
**共识等级**: ≥2 directions + ≥2 models。

问题：`auth.md` 定义 `swarm_login_challenge`，但 `interface.md` 缺少该工具；`swarm_login` 示例也未展示 PoW 触发后如何提交 `challenge_id + nonce`，以及同 register PoW 一样禁止客户端提交 challenge/difficulty。

修正要求：
- `interface.md` 补充 `swarm_login_challenge`。
- `swarm_login` 参数定义增加可选 `challenge_id`、`nonce`，明确仅在 `login_pow_required` 后使用。
- 测试补充 login PoW server-authoritative challenge 与拒绝 client-supplied difficulty。

#### R2-Gate-H4 — Auth Service ↔ CertificateIssuer 签发边界需接口合同

**同意者**: rev-gpt-architect A2；rev-dsv4-architect 认可边界但未要求 gate；Security/Designer 未反对。  
**共识等级**: Architect 方向分歧，Speaker 保留为架构实现前 gate。

问题：文档同时声称 Auth Service 不持有 PlayerCertificate 私钥、Engine 持有 CertificateIssuer；但注册/登录由 Auth 返回 `LoginResult { session, certificate }`。实现前必须说明 Auth 如何请求签发：进程内 adapter、internal RPC、signer service，或 Engine module call。

修正要求：
- 定义 `issue_certificate(player_id, client_public_key, scopes, audience, ttl)` 内部接口。
- 明确调用权限、失败恢复、审计、revocation 写入责任。
- 若 Auth 实际位于 Engine 进程内，也需保留模块边界与最小签发接口，避免重新污染 Engine/game core。

#### R2-Gate-H5 — 联邦撤销 stale-as-valid 需要最大 stale 上限或策略开关

**同意者**: rev-dsv4-security H1, rev-dsv4-architect O4, rev-gpt-architect Missing #3；Designer 认可为可用性取舍但未反对。  
**共识等级**: ≥2 directions + ≥2 models。

问题：外部世界不可达时，本地使用 stale revocation list 并视为有效。无限期 stale-valid 会使已撤销外部证书在 DoS 或远端不可达期间继续被接受。

修正要求：
- 增加 `revocation_cache_stale_seconds` 或 `federation.revocation_fallback = accept|reject`。
- 默认可用性优先可以保留，但高安全世界必须能选择超时拒绝。
- 文档说明 stale 超时后的行为与运维告警。

#### R2-Gate-H6 — 账号删除恢复/transfer 语义需要可执行合同

**同意者**: rev-gpt-designer G1, rev-gpt-architect A4, rev-dsv4-security H2, rev-dsv4-designer G4。  
**共识等级**: ≥3 directions + ≥2 models。

问题：文档承诺 30 天 grace period 可恢复，但 API 表没有 restore/cancel deletion 工具，也没有删除后登录/邮件恢复/UI/MCP 路径。`transfer` 资产处置需要接收方确认，但未定义签名确认、冷却、拒绝、资产摘要与竞赛状态处理。

修正要求：
- 明确恢复语义：新增 `swarm_restore_account` / `swarm_cancel_account_deletion` / 邮件恢复链接，或明确“不支持主动恢复，仅延迟永久删除”。
- 定义 deleted(grace) 状态下 login、token_refresh、username reuse、identity index、asset handling 的状态机。
- `transfer` 如保留，接收方必须 Ed25519 签名确认，确认消息包含删除者 player_id 与资产摘要；否则 Phase 1 仅支持 `abandon`/`recycle`。

### Direction-Specific High / Medium Items

#### A-H1 — identity conflict 错误语义不应全部映射为 `username_taken`

来源：rev-gpt-architect A3。  
处置：Medium。实现前区分 `username_taken`、`identity_conflict`、`player_id_collision`，尤其 OAuth2/federation collision 不是用户换用户名即可解决。

#### S-H1 — refresh token grace 必须 one-shot 原子消费

来源：rev-gpt-security M2。  
处置：Medium。文档应声明 rotated token 的 grace 使用必须在 FDB 中原子标记 `grace_consumed_at`，并对异常 IP/UA 使用触发 session family revoke。

#### S-H2 — verify_password 参数校验与 reset 常量时间

来源：rev-dsv4-security M1/M2，rev-gpt-architect A5。  
处置：Low/Medium。修正 `verify_password` 示例，不再复制 `Argon2::default()`；对不存在邮箱也执行 dummy token generation/discard write，降低 reset 邮箱枚举时序差。

#### D-H1 — AI-only MCP onboarding resources 需规格化

来源：rev-gpt-designer G2，rev-dsv4-designer G1/G5。  
处置：Medium。增加 `docs/auth/onboarding-ai`、`docs/auth/errors`、`schema/auth-tools`、`docs/auth/human-agent-handoff` 等 MCP resource contract；明确 AI agent 如何验证邮箱 token、持久化证书并用于 federation。

#### D-H2 — 邮箱多账号绑定 UX 需定义

来源：rev-gpt-designer G4，rev-dsv4-security I1。  
处置：Low。若一个邮箱绑定多个账号，reset 邮件需列出可识别账号或要求额外 username，避免用户不知道重置了哪个账号。

## Medium/Low 处置

| ID | 问题 | 来源 | 负责 Phase | 处置 |
|---|---|---|---|---|
| ML-1 | `auth.md` 章节编号漂移 | 4/6 reviewers | Phase 0 doc cleanup | 全文重编号：§13/14/15/16/17 子节修正。 |
| ML-2 | `swarm_register` 示例缺 `email?` | rev-dsv4-designer | Phase 0 doc cleanup | 在 §9.3 示例或补充示例中标注可选 email。 |
| ML-3 | 附录 C 缺 `username_visibility` | rev-dsv4-designer | Phase 0 doc cleanup | 在 world.toml `[auth]` 段加入默认 `private` 与注释。 |
| ML-4 | AI agent 私钥存储指引不足 | rev-dsv4-security | Phase 1 docs | 增加 HSM/secret manager > encrypted file 0600 > env var 优先级，禁止日志泄露。 |
| ML-5 | Federation certificate export 路径隐式 | rev-dsv4-designer | Phase 1 docs | 明确客户端持久化 `LoginResult.certificate`，或新增 export 工具。 |
| ML-6 | Login fail_count FDB 并发时序未写明 | rev-dsv4-architect | Phase 1 impl notes | 登录更新 fail_count 的事务重试与冲突恢复补一句。 |
| ML-7 | 多账号邮箱 reset 文案 | rev-gpt-designer | UX polish | 邮件显示 display_name/login_username，逐账号 reset 链接或要求 username。 |

## Review Statistics (3×3)

### R2 实际可用矩阵

| Direction | Claude | GPT-5.5 | DeepSeek V4 Pro | Direction Summary |
|---|---:|---:|---:|---|
| Architect | retired / unavailable | CONDITIONAL_APPROVE | APPROVE | R1 架构 blocker closed；需 token schema 与 signer boundary。 |
| Security | retired / unavailable | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE | R1 安全 blocker closed；需 login DoS 限流、federation stale、transfer abuse 收口。 |
| Designer | retired / unavailable | CONDITIONAL_APPROVE | APPROVE | UX 基本闭环；需 account restore 与 AI MCP onboarding resources。 |

### 统计

| Metric | Count |
|---|---:|
| Available reviewers used | 6/14 |
| Original R2 directions covered | 3/3 |
| Original R2 active models covered | 2/2 |
| APPROVE | 2/6 |
| CONDITIONAL_APPROVE | 4/6 |
| REQUEST_MAJOR_CHANGES | 0/6 |
| REJECT | 0/6 |
| R1 items fully/mostly closed | 12/12 |
| New consensus/majority gate items | 6 |
| Direction-specific medium/high items | 5 |
| Medium/Low cleanup items | 7 |

### 共识强度评估

- Strong consensus：R1 C1-C8/D1-D4 已实质关闭；无 reviewer 要求回到 major redesign。
- Cross-direction consensus：token/certificate 权威模型、Login PoW 接口同步、联邦 stale revocation、账号删除恢复/transfer 至少由 2 个方向与 2 个模型发现。
- Direction-local concern：登录 dummy argon2id DoS 主要由 Security 显式提出，但因影响生产可用性，Speaker 标为实现前 gate。
- Isolated but important：CertificateIssuer 签发边界主要由 GPT Architect 提出，因其关系到 R1 Auth boundary 是否在代码中保持，Speaker 标为架构 gate。

## Final Recommendation

**推荐：CONDITIONAL_APPROVE → Phase 1 implementation preparation after gate cleanup.**

R2 Auth 设计已经从 R1 的不完整草案收敛为可实现设计：Auth 控制面边界、PoW 权威绑定、身份模型、FDB schema、登录抗爆破、token 生命周期、密码/邮箱/删除/联邦/OAuth2 流程均具备明确框架。无需重开大设计，也无需阻止实现团队开始做技术准备。

但在正式编码前，应先完成一个短的 Phase 0 cleanup pass：

1. 补登录来源维度限流与 dummy argon2id DoS 测试。
2. 统一 Auth token/certificate/JWT/access_token 权威 schema，并同步 `03-mcp-security.md`。
3. 同步 Login PoW API：`swarm_login_challenge` 与 `swarm_login` 可选 `challenge_id/nonce`。
4. 定义 Auth Service ↔ CertificateIssuer 签发接口。
5. 为 federation revocation stale 策略加上最大上限或 fallback 配置。
6. 明确账号删除恢复 API/UI/MCP 路径与 transfer 确认/滥用防护。
7. 批量修正文档编号、配置示例、MCP onboarding resources 与邮箱多账号 reset UX。

完成以上 gate 后，Speaker 建议进入 Phase 1：先实现本地 Auth core 最小闭环（username/password/argon2id/FDB/register/login/PoW/fail-count），再实现 session/certificate 生命周期、UX/恢复路径、federation 与账号长期治理。