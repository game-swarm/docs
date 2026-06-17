# R2 Auth 复检 — Game Designer Reviewer (GPT-5.5)

## Verdict

CONDITIONAL_APPROVE

R2 已经把 R1 的核心 blocker 从“安全/协议空洞”推进到“可实现的认证 UX 方案”：三种注册路径、PoW 绑定、登录抗爆破、密码生命周期、邮箱、账号删除、联邦身份和 OAuth2 共存都有明确设计。以游戏设计/UX 视角看，方案已经足够进入实现前的规格收敛；但仍有少数用户闭环与 MCP learnability 的文档缺口，需要在实现前补齐，否则第一小时体验和 AI 自助接入会出现断点。

## Strengths

- 三种注册场景已形成清晰路径：人类前端注册、AI MCP 自注册、人类经 Agent 代理注册分别给出流程、凭据归属和错误恢复，R1 的“只为人类/只为 OAuth2”缺口基本关闭。
- PoW 体验比 R1 明显成熟：`difficulty_bits` 是 bit 级难度，默认值给出不同运行环境耗时估算，前端 Web Worker、进度、取消、慢设备提示都有说明。
- Agent 代理注册的 UX 风险被正面处理：不把长期 refresh token / certificate 私钥直接写入聊天日志，而是使用一次性 handoff code / 导入链接，符合玩家心理上的“账号归属感”。
- Identity 设计从玩家可理解性上更清楚：`login_username`、`display_name`、`player_id` 三层分离，解决“登录名是否公开/能否改名/排行榜显示什么”的混淆。
- 密码管理、邮箱绑定、密码重置、token rotation、session 绑定、AI agent 凭据持久化都已列入同一 Auth 生命周期，不再是孤立功能点。
- 联邦身份强调“身份跨世界、资产/排名/模块不跨世界”，这对玩家预期很重要，避免把 federation 误读成跨服状态同步或跨服战斗优势。

## Concerns

### G1 — Medium — 账号删除恢复只有承诺，没有玩家/Agent 可执行路径

`auth.md` 说明删除后 30 天内可恢复，并在测试策略中列出 `delete_account_grace_period_allows_recovery`，但 API 表和 MCP interface 只有 `swarm_delete_account`，没有 `swarm_restore_account` / `swarm_cancel_account_deletion` / 浏览器恢复链接，也没有说明删除后登录会看到什么、如何验证身份、资产处置是否可逆。

这会让“误删除可恢复”停留在文案层面。对玩家第一小时/长期账号信任来说，账号删除是高情绪成本操作；如果恢复路径不明确，UX 闭环仍未关闭。

建议补充：
- 删除确认后的状态页与邮件通知。
- grace period 内的恢复入口：登录触发、邮件链接、或独立 MCP tool。
- 恢复后资产处置策略的回滚规则，尤其 `abandon` / `recycle` / `transfer` 是否可逆。
- interface.md 与 auth.md API 表同步新增恢复工具或明确“不支持恢复，只延迟永久删除”。

### G2 — Medium — AI 仅靠 MCP resources 学会认证流程仍不够稳

interface.md 有 `swarm_get_docs`、`swarm_get_schema`、`resources/list`、`resources/read`，也列出了认证工具；但本次材料没有定义这些 resources 必须暴露的 auth onboarding 文档结构。AI player 虽可读 auth.md，但“先注册、生成密码、保存凭据、刷新 token、部署 WASM、失败后恢复”的机器可发现路径还没有被规格化。

对 AI 玩家来说，MCP resources 是教程和 UI 的替代物。若 resources 只给工具列表而没有 recipe/schema/error recovery，AI 会在第一小时卡在凭据保存、PoW 重试、login_pow_required、refresh token rotation 等非玩法问题上。

建议补充至少一个 MCP resource：
- `docs/auth/onboarding-ai`：端到端 AI 自注册 → 凭据持久化 → deploy WASM。
- `docs/auth/errors`：每个错误码的下一步动作。
- `schema/auth-tools`：LoginResult、PoWChallenge、ResetRequestResult 等完整结构。
- `docs/auth/human-agent-handoff`：代理注册的安全交付合同。

### G3 — Low — 文档编号和跨文档术语漂移会削弱实现者信心

`auth.md` 后半部分出现多处章节编号漂移，例如 Token 安全下的 `10.2/10.3/10.4`、联邦身份下的 `18.1/18.2/15.3`、前端变更下的 `18.1/18.2`。这不是设计 blocker，但对实现者和 AI reviewer 来说会降低引用稳定性。

另外 `03-mcp-security.md` 仍以 JWT token 格式描述认证，而 auth.md 强调本地/OAuth2 共享 `PlayerCertificate + refresh_token + LoginResult`。两者不一定矛盾，但需要明确 JWT、access_token、PlayerCertificate 三者关系，否则实现者可能做出两套认证模型。

### G4 — Low — 邮箱绑定“不唯一”需要更强 UX 文案

设计允许一个邮箱绑定多个账号，这对家庭/组织/机器人批量账号有好处，但也会影响密码重置心智模型：用户输入邮箱请求重置时，如果多个账号共享邮箱，邮件里必须让用户选择或列出账号，否则会造成“我重置了哪个账号？”的困惑。

建议补充多账号邮箱的 reset 邮件 UX：列出 display_name/login_username、隐藏敏感信息、逐账号重置链接，或明确每次请求必须额外提供 username。

## Missing

- 账号删除恢复 API / UI / MCP tool / 邮件路径。
- AI-only MCP onboarding resource contract，不只是工具表。
- `LoginResult`、`PoWChallenge`、`ResetRequestResult`、`SuccessResult` 等返回结构的统一 schema。
- 邮箱多账号绑定下的密码重置选择体验。
- Browser localStorage 策略与 `03-mcp-security.md` cookie/CSRF 描述的边界说明：浏览器 auth 到底走 bearer/localStorage，还是 cookie + CSRF，或两者分层使用。
- auth.md 章节编号修复，避免未来引用错位。

## R1 Fix Verification

| R1 Item | Status | Designer Notes |
|---|---|---|
| C1 PoW 绑定 | CLOSED | `swarm_register` 只提交 `challenge_id + nonce`，服务端从 FDB 取 challenge/difficulty。 |
| C2 difficulty bit | CLOSED | bit-level leading zero 设计和难度表明确。 |
| C3 login 抗爆破 | CLOSED | dummy argon2id、per-account fail count、lockout、可选 login PoW 已覆盖。 |
| C4 Auth 边界 | CLOSED | Auth 独立控制面与 Engine 只消费证书的边界清楚。 |
| C5 Identity/FDB | CLOSED | 三层身份与 auth subspace 已定义。 |
| C6 Token 安全 | MOSTLY_CLOSED | refresh rotation/session binding 有设计；需和 security.md JWT/access_token 关系再同步。 |
| C7 错误恢复 | MOSTLY_CLOSED | 注册/PoW/密码重置覆盖较好；账号删除恢复缺路径。 |
| C8 argon2id | CLOSED | 参数、PHC 校验、事务外 hash 明确。 |
| D1 Auth 独立控制面 | CLOSED | 设计原则和架构图已补。 |
| D2 Login PoW 可配置 | CLOSED | `[auth.login_pow]` 有开关、难度、触发窗口。 |
| D3 用户名可见性配置 | CLOSED | `username_visibility = public/private` 明确了体验/隐私 tradeoff。 |
| D4 三层身份 | CLOSED | login_username/display_name/player_id 已补。 |
| 新增密码管理/邮箱/账号删除/联邦/OAuth2 | CONDITIONAL | 覆盖完整，但账号恢复、邮箱多账号 reset、联邦 onboarding 文案还需收口。 |

## Fresh Ideas

- 做一个“First Hour Auth Quest”：首次进入时用任务卡引导完成注册、绑定邮箱、部署第一个 WASM、保存 agent 凭据备份；认证不再是表单，而是进入游戏世界的 onboarding。
- 为 AI agent 提供 `swarm_get_onboarding_plan(role="ai_player")`，返回按步骤可执行的 MCP recipe，包括错误码分支和凭据保存提示。
- 删除账号改成“休眠/冻结”语义：30 天内显示为 Dormant Commander，世界中资产按配置进入 abandoned/recyclable 状态；恢复时有清晰叙事而不只是数据库 rollback。
- 对人类代理注册提供 QR/import code：Agent 只展示短期 code，浏览器扫描或粘贴后导入 session，减少聊天日志泄露焦虑。
- 联邦登录首次进入新世界时显示“passport stamp”：清楚告诉玩家这是新世界本地身份，资产和排名从零开始，但身份声誉可被识别。

## Final Verdict

CONDITIONAL_APPROVE

R2 已经正确修正 R1 的主要 blocker，尤其是 PoW、Auth boundary、Identity、登录抗爆破和密码生命周期。进入实现前建议把 G1/G2 作为必须收口项：账号删除恢复必须有可执行路径，AI-only MCP resources 必须能让 agent 自助完成认证 onboarding。其余问题属于文档一致性和 UX polish，可随实现规格一起修正。
