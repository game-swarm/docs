# Swarm Local Auth Design — Consensus Report (R1)

## Overall Verdict
REQUEST_MAJOR_CHANGES

R1 评审呈现“方向正确、实现合同未冻结”的一致信号。9 位评审员全部给出 verdict；其中 4 位 REQUEST_MAJOR_CHANGES，5 位 CONDITIONAL_APPROVE。两个 Claude partial 文件只提供 verdict 与严重度摘要，未提供可追溯的具体 finding 内容，因此本报告在统计中计入其 verdict/severity，但不把未展开的 Claude finding 用作具体共识证据。

核心设计目标获得广泛认可：Local Auth 与 OAuth2 并列、共享 PlayerCertificate/WebAuthSession、AI agent 与人类玩家走同一认证与部署链路、使用 argon2id、FDB 事务与 PoW challenge 的总体方向成立。但当前文本中的 PoW 权威绑定、难度校准、登录抗爆破、Auth 边界、token/session 生命周期、前端/agent 凭据 UX 都存在跨方向重复发现。进入实现前需要先修订设计文档和伪代码，否则实现者很容易照抄出安全或可用性缺陷。

## Consensus Findings (≥2 方向 + ≥2 模型一致)

### C1 — PoW challenge 必须服务端权威绑定并在事务中正确消费
Severity: Critical / High

提到的评审员：
- rev-gpt-architect: A3
- rev-gpt-security: High: PoW challenge 服务端绑定校验不够明确
- rev-claude-designer: G1 Critical
- rev-dsv4-security: H2
- rev-claude-security: partial 摘要显示 2C+，但具体 finding 不可追溯，未计入上列证据

问题：当前 `swarm_register` 同时接收 `challenge_id` 与客户端回传的 `challenge`，附录 C 伪代码只检查 `pchallenge/<id>` 是否存在，然后用 `params.challenge` 和常量 `DIFFICULTY` 验证 PoW。多个评审员独立指出这会让 challenge_id 与 challenge/difficulty/expiry 脱钩，甚至可能退化为可替换 challenge、低难度 PoW 或错误消费路径。dsv4-security 还指出用户名冲突早退会导致已求解 challenge 不被消费，破坏“一次性使用”承诺。

修正要求：
1. `swarm_register` 请求只提交 `challenge_id + nonce + username/password/client_public_key`；删除客户端回传 `challenge`，difficulty 也不得来自客户端。
2. 服务端从 FDB/Auth challenge store 读取 `{challenge, difficulty, expires_at, consumed}`，在同一权威流程中验证未过期、未消费、difficulty 匹配、PoW 成立。
3. 明确 challenge 消费语义：PoW 验证通过后，无论后续 username 冲突还是创建失败，是否消费 challenge 必须写成合同；推荐避免“已验证 PoW 被无限复用”的路径。
4. 更新威胁模型与测试：challenge 替换、difficulty 降级、过期 challenge、重复使用、用户名冲突后的 challenge 状态都必须覆盖。

### C2 — PoW 难度估算与调参模型不可信
Severity: High

提到的评审员：
- rev-gpt-architect: A4
- rev-dsv4-architect: H1
- rev-gpt-security: Medium: difficulty=4 成本估算需真实平台校准
- rev-claude-designer: G3
- rev-dsv4-designer: G4

问题：文档把 difficulty 定义为“前导零字节数”，并声称 difficulty=4 即 2^32 次尝试约 1.3 秒。评审一致认为该吞吐估算对 Rust native、Python、浏览器 WASM、移动端都不可靠，浏览器/移动端可能从秒级变成数十秒、分钟甚至小时。固定字节级 difficulty 也导致 24/32/40 bit 大步跳，缺少细粒度运营调参能力。

修正要求：
1. 用“前导零 bit 数”替代“前导零字节数”，允许 22–28 bits 等细粒度配置。
2. 删除未经基准验证的 “difficulty=4 ~1.3s” 默认承诺；补充 Rust native、Python、Node/browser WASM、移动端的基准或保守估算。
3. difficulty 必须是服务端配置/动态策略的一部分，并随 challenge 记录绑定；不得硬编码为架构常量。
4. 前端与 agent 文档必须说明慢设备、超时、重试和进度反馈策略。

### C3 — 登录抗爆破不能只依赖 argon2id 与模糊 IP/tick 限速
Severity: High

提到的评审员：
- rev-gpt-architect: A5
- rev-gpt-security: High: 登录暴力破解防护过度依赖 argon2id
- rev-dsv4-security: H3, M2
- rev-claude-designer: G4
- rev-dsv4-architect: L3
- rev-dsv4-designer: G6

问题：文档称 `swarm_login` 不需要 PoW，因为“每 tick 已限速 10/min per IP”且 argon2id 足够慢。评审一致指出登录是认证控制面，不参与游戏 tick；IP rate limiting 与文档自身“PoW 优于 IP 限速”的论证冲突；分布式低速撞库、同一 username 的跨 IP 尝试、NAT/IPv6 轮换、多 agent 并发都没有被清楚覆盖。dsv4-security 还指出不存在用户路径若直接返回，会产生时序枚举侧信道。

修正要求：
1. 明确登录端点独立于游戏 tick 的速率限制模型，至少包括 username/account 维度、source/network 维度与全局 backpressure。
2. 对连续失败加入递增延迟、短期锁定或失败计数；是否引入低难度 login PoW 需在文档中裁决。
3. 不存在用户也执行等成本 dummy argon2id 验证，避免通过响应时间枚举账号。
4. 威胁模型新增“分布式低速密码爆破 / credential stuffing / CPU exhaustion”行，并给出错误码和恢复策略。

### C4 — Auth 责任边界需要从 Engine MCP 下沉实现改为清晰 control-plane 合同
Severity: High

提到的评审员：
- rev-gpt-architect: A1
- rev-gpt-security: High/Multi-point: engine 权威层、Gateway/Auth 限速、challenge 控制面
- rev-dsv4-architect: M3, CG1
- rev-claude-architect: partial verdict 显示 3C+6H，但具体 finding 不可追溯，未计入上列证据

问题：设计原则写“核心实现在 engine MCP 层，Gateway 是薄封装”，但认证涉及密码哈希、challenge 生成、限速、session/refresh token、注册治理和互联网入口控制。评审认为若把这些全部塞入 Engine MCP，容易把游戏模拟/部署控制面与认证互联网入口耦合，削弱 engine 无状态扩展、审计边界和离线/确定性核心的清晰性。

修正要求：
1. 明确 Auth control-plane 责任：注册、登录、密码哈希、challenge 生命周期、登录失败计数、refresh token 存储/轮换/吊销。
2. Engine 只消费已签发身份、证书与部署权限；如果 MCP tool 仍作为入口，应路由到 Auth service/domain，而不是让游戏核心直接拥有密码库。
3. Gateway REST 与 MCP tool 应共享同一 Auth domain model，避免两套限速/错误/验证逻辑。
4. 文档需给出 Local/OAuth2 共用 sequence diagram：register/login/refresh/revoke/deploy verify。

### C5 — IdentityKey / PlayerId / FDB Auth subspace 合同不足
Severity: High / Medium

提到的评审员：
- rev-gpt-architect: A2, A8, A9, A10
- rev-dsv4-architect: M2, M3, L1, M4
- rev-gpt-security: Low: player_id 可枚举说明
- rev-dsv4-designer: G8

问题：`player_id = blake3("local:" + username_lowercase) -> u64` 的命名空间方向被认可，但 provider registry、subject canonicalization、u64 截断方式、碰撞处理、identity 唯一索引、未来改名/身份合并、FDB key subspace 与 schema_version 都没有冻结。裸 `users/<username>`、`pchallenge/<id>` 混在世界状态 FDB 中，且事务示例可能在事务内执行高成本 password hash。

修正要求：
1. 定义统一 `IdentityKey { provider, subject } -> PlayerId` 合同：provider 枚举、subject 不可变性、canonicalization、hash_to_u64 截断策略、碰撞概率与处理。
2. 定义 Auth FDB subspace：`auth/users/`、`auth/identities/`、`auth/challenges/`、`auth/sessions/`、`auth/login_fail/` 等，value 带 `schema_version`。
3. 明确 username/display_name/account_id 的关系；v1 可不支持改名，但不要把社交显示名、登录名、稳定 subject 永久混为一个概念。
4. 密码哈希应在事务外完成，FDB 事务保持短生命周期；事务冲突重试和错误响应需文档化。

### C6 — Token/session 生命周期与前端凭据存储缺少安全合同
Severity: Medium / High

提到的评审员：
- rev-gpt-architect: A7, A11
- rev-dsv4-security: M4, L1
- rev-gpt-security: Low: HTTPS/CSRF/CORS/token 存储
- rev-gpt-designer: High: 代理注册凭据交付
- rev-claude-designer: G2

问题：文档说复用 `swarm_token_refresh` / `swarm_auth_revoke`，但没有定义 token 格式、refresh token rotation、session/device 绑定、吊销传播、cookie vs bearer/localStorage 的安全边界、AI agent 凭据持久化指导。前端 localStorage 保存 refresh_token + certificate 是 MVP 可接受方案，但需要被标注为迁移路径上的风险点。

修正要求：
1. 增加 Token Security 节：access token 生命周期、refresh token 生命周期、rotation、revoke 粒度、session/device/client_public_key 绑定、FDB key 结构。
2. 明确浏览器方案：若 cookie，则 CSRF/SameSite；若 bearer/localStorage，则 CORS、XSS、HSTS、日志脱敏与迁移到 HttpOnly/WebCrypto-bound token 的计划。
3. 明确 AI agent 凭据存储建议：secret store、文件权限、环境变量边界、refresh token 失效后的回退登录流程。
4. 代理注册不得把长期 refresh token 直接暴露在聊天上下文中；应设计一次性 handoff token/导入链接，或明确“agent 托管”需要用户显式授权。

### C7 — 人类/AI/代理注册的错误恢复与 onboarding 闭环不足
Severity: High / Medium

提到的评审员：
- rev-claude-designer: G2, G3, G4
- rev-gpt-designer: High + Medium items
- rev-dsv4-designer: G1-G5
- rev-gpt-security: Medium: AI agent 治理边界

问题：三种注册场景的 happy path 清楚，但失败与恢复路径不足：PoW 求解中断、challenge 过期/已消费、移动端慢设备、agent 凭据丢失、代理注册密码归属、密码无法重置、首个 WASM 部署引导都未闭环。Designer 方向一致认为这会直接影响首小时体验和 AI 自注册可用性。

修正要求：
1. §3 每个场景补充错误恢复：网络中断、PoW 超时、challenge 过期、凭据丢失、注册后下一步。
2. 前端 PoW 必须使用 Web Worker，并显示进度、取消、慢设备提示和自动重新取 challenge 的策略。
3. v1 若不支持密码重置，必须在 UI/文档中显式警告“忘记密码会永久失去账号/资产访问”；注册 UI 增加 Confirm Password。
4. 提供 agent-readable onboarding resource，例如 `swarm_get_docs("onboarding/local-auth-to-first-deploy")`，覆盖 register → validate module → deploy → explain first tick。

### C8 — 密码策略与 argon2id 示例需要从“意图正确”改为“可照抄安全”
Severity: Medium / High

提到的评审员：
- rev-dsv4-security: H1, M1, M3
- rev-gpt-security: Medium: argon2id 参数声明与示例不一致、密码策略偏弱
- rev-gpt-architect: positive note + missing contract implication

问题：argon2id 选择获得认可，但示例使用 `Argon2::default()`，没有显式接入文档声明的 OWASP 参数；弱密码黑名单过短，8 字符 + 字母数字规则对人类用户偏弱。若实现者照抄示例，可能低于设计意图。

修正要求：
1. 示例必须显式构造 Argon2id 参数 `m=19456,t=2,p=1`，测试 PHC 字符串包含这些参数。
2. 密码策略采用长度优先与强度评分/常见泄露密码库；至少提高人类密码提示与弱密码拒绝质量。
3. AI `random_hex(32)` 保留为推荐，但不能替代人类密码强度策略。

## Direction Consensus (方向内一致)

### Architect Consensus

Verdicts:
- rev-claude-architect: REQUEST_MAJOR_CHANGES (partial: 3C+6H)
- rev-gpt-architect: REQUEST_MAJOR_CHANGES
- rev-dsv4-architect: CONDITIONAL_APPROVE

方向共识：
1. 设计方向成立：Local Auth 与 OAuth2 共享证书/session、AI-human parity、FDB 事务、argon2id、PoW 的基本选择被认可。
2. PoW 参数与 challenge 合同是架构前置修正项；dsv4-architect 认为修正 difficulty 后可进入实现，gpt-architect 认为还需同步修 Auth 边界、identity namespace、FDB schema。
3. 架构边界存在分歧：是否把注册/登录核心放在 Engine MCP 层。gpt-architect 明确要求 Gateway/Auth control-plane；dsv4-architect较接受 MCP-first，但仍要求 FDB namespace、事务重试和参数语义澄清。
4. 统一 IdentityKey、Auth subspace、`OAuth2LoginResult` 重命名为 `AuthLoginResult`/`LoginSession` 是方向内多数共识。

### Security Consensus

Verdicts:
- rev-claude-security: REQUEST_MAJOR_CHANGES (partial: 2C+)
- rev-gpt-security: CONDITIONAL_APPROVE
- rev-dsv4-security: CONDITIONAL_APPROVE

方向共识：
1. 安全基线方向可接受：argon2id、统一错误、FDB 原子事务、一次性 challenge、证书模型复用都应保留。
2. 进入实现前必须修正 PoW challenge 绑定/消费、challenge 申请 DoS、登录抗爆破/枚举侧信道、argon2id 参数示例。
3. IP/tick 限速不是登录安全合同；登录必须具备账号维度、来源维度和全局维度节流。
4. Token/session、前端 storage、AI agent credential storage、HTTPS/CORS/CSRF/log redaction 需要补充防御纵深。

### Designer Consensus

Verdicts:
- rev-claude-designer: REQUEST_MAJOR_CHANGES
- rev-gpt-designer: CONDITIONAL_APPROVE
- rev-dsv4-designer: CONDITIONAL_APPROVE

方向共识：
1. 三种用户场景覆盖方向正确，但只有 happy path，不足以支撑首发体验。
2. 前端 PoW 必须移出主线程，配进度、取消、慢设备提示、重试策略；当前 JS `while(true)` 示例不可照抄。
3. Agent 代理注册的密码归属、凭据交付、聊天日志风险、长期托管授权都需要正式 UX 合同。
4. v1 无密码重置会造成永久账号/资产丢失风险，必须通过 Confirm Password、强提示、凭据备份指导和已登录改密/后续恢复路线缓解。
5. AI agent 注册后到首个部署的 onboarding resource 需要补齐，否则认证完成但“如何开始玩”仍断裂。

## Unresolved Disagreements

### D1 — Auth 核心应放在 Engine MCP 还是独立 Gateway/Auth control-plane？

方案 A：Engine MCP-first
- 主张：保持当前文档哲学，AI agent 直接调用 MCP tool，Gateway/Frontend 只是薄代理；实现集中在 engine，最小侵入。
- 支持信号：dsv4-architect、dsv4-designer 对 MCP-first 方向评价较正面；原文明确以 MCP 优先为原则。
- 风险：认证状态、密码库、限速、token 生命周期进入 engine，控制面与游戏核心耦合。

方案 B：Auth control-plane-first
- 主张：注册、登录、PoW、密码哈希、refresh token、限速归 Auth service/domain；MCP tool 只是入口之一，Engine 只消费身份/证书。
- 支持信号：gpt-architect 明确提出；security 多项发现也要求独立登录/challenge 治理边界。
- 风险：实现面更大，需要定义 Gateway/MCP/Auth domain 调用关系。

Speaker 建议：选择方案 B 或折中版 B：即使代码初期仍在 engine repo 内，也应在文档层定义独立 Auth domain/control-plane，避免把认证视为游戏模拟的一部分。

### D2 — 登录是否也需要 PoW？

方案 A：Login 不加 PoW，但加强账号/来源/全局限速
- 优点：用户体验更简单，避免每次登录 CPU 成本；符合多数传统认证系统。
- 必要条件：per-username 失败计数、递增延迟、短期锁定、dummy argon2id、全局 backpressure。

方案 B：Login 失败后或每次 login 增加低难度 PoW
- 优点：与“PoW over IP rate limiting”的设计哲学一致，对分布式撞库更公平。
- 风险：登录 UX 与 agent 自动化复杂度上升；低难度 PoW 若参数不当可能只增加正常用户摩擦。

Speaker 建议：v1 采用方案 A，并预留“失败阈值触发 login PoW”的升级开关。

### D3 — challenge 在 username_taken 路径是否消费？

方案 A：先检查用户名，再验证/消费 PoW
- 优点：避免为已占用用户名浪费客户端 CPU；用户名占用本身若视为公开属性，则可接受。
- 风险：攻击者可无 PoW 枚举 username_taken，需明确用户名注册状态是否公开。

方案 B：PoW 验证通过后无条件消费 challenge，即使 username_taken
- 优点：严格维护“一次性 challenge”语义，降低同一 PoW 被多次探测使用的风险。
- 风险：用户误填已占用用户名会浪费一次 PoW；UX 需自动重取 challenge。

Speaker 建议：先由用户裁决“用户名注册状态是否公开”。若公开，方案 A 更顺滑；若不公开，方案 B 更一致。

### D4 — 本地 username 是否可改名 / 是否拆 display_name？

方案 A：v1 维持 username 即 subject/display name
- 优点：简单、可离线推导、最小实现。
- 风险：长期卡住改名、Unicode 社区身份、显示名与登录名分离。

方案 B：拆 `account_id/player_id`、`login_username`、`display_name`
- 优点：长期演进更稳；允许 ASCII canonical username + Unicode display_name。
- 风险：数据模型复杂度上升，v1 设计范围扩大。

Speaker 建议：v1 至少在文档中保留 `display_name`/改名扩展位；不要求立即实现改名。

## Action Recommendations (按优先级)

### P0 — 进入实现前必须修正
1. 改写 PoW register contract：服务端权威读取 challenge/difficulty/expires_at，删除 register 请求中的客户端 `challenge` 字段，补齐替换/降级/重放测试。
2. 重新定义 PoW difficulty：bit-level、可配置/可动态调整、真实平台基准、Web Worker 和慢设备 UX。
3. 定义登录安全合同：per-account/source/global 限速、递增延迟/锁定、dummy argon2id、分布式爆破威胁模型。
4. 明确 Auth domain/control-plane 边界：Gateway/MCP/Auth/Engine 的职责、sequence diagram、错误码归属。
5. 修正 argon2id 示例：显式参数构造并测试 PHC 参数，不允许 `Argon2::default()` 与文档常量漂移。

### P1 — 实现前建议同步完成
1. 定义 `IdentityKey -> PlayerId`、provider registry、hash_to_u64 截断、碰撞处理和 FDB identity 唯一索引。
2. 定义 Auth FDB subspace 与 schema_version，拆分 users/challenges/sessions/refresh tokens/login_fail/revocation。
3. 增加 Token Security：access/refresh token 生命周期、rotation、revoke、session/device/client_public_key 绑定、浏览器存储策略。
4. 增加注册/登录错误恢复矩阵：code、是否可重试、用户文案、agent next step。
5. 补全 agent proxy handoff：一次性导入链接/短期 handoff token、聊天日志风险、agent 托管授权边界。

### P2 — 可作为 v1 文档完善或 v1.1 backlog
1. 增加 Confirm Password、无密码重置永久丢失警告、已登录改密优先级说明。
2. 增加 AI agent credential storage 指南与 onboarding resource 到首个 WASM deploy。
3. 强化密码策略：zxcvbn/常见泄露密码库、12+ passphrase 指导、username 变体拒绝。
4. 预留 `display_name` 与改名/身份合并数据模型扩展。
5. 增加 challenge 申请 DoS 控制：轻量限速、容量水位、GC/TTL 策略或无状态签名 challenge 方案评估。

## Review Statistics (3×3 matrix, verdict + verdict count)

| Direction | Claude Opus 4.7 | GPT-5.5 | DeepSeek V4 Pro |
|---|---|---|---|
| Architect | REQUEST_MAJOR_CHANGES (partial: 3C+6H) | REQUEST_MAJOR_CHANGES | CONDITIONAL_APPROVE |
| Security | REQUEST_MAJOR_CHANGES (partial: 2C+) | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE |
| Designer | REQUEST_MAJOR_CHANGES | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE |

Verdict count:
- REQUEST_MAJOR_CHANGES: 4/9
- CONDITIONAL_APPROVE: 5/9
- APPROVE: 0/9
- REJECT: 0/9

Severity signal:
- Critical/Critical-like items appear in Claude partial summaries and rev-claude-designer; PoW challenge binding/consumption is the strongest concrete Critical consensus.
- High items appear in all three directions and all three model families.
- No reviewer recommends unconditional approval.

Consensus strength:
- Strongest consensus: C1 PoW challenge authority/consumption, C2 PoW difficulty calibration, C3 login anti-bruteforce.
- Medium-strong consensus: C5 identity/FDB schema, C6 token/session/credential storage, C7 UX/onboarding recovery.
- Primary unresolved design decision: Auth control-plane placement and exact login PoW policy.

Final Speaker disposition: revise the design document before implementation, then run R2 targeted re-review focused on P0 closure. If P0 items are corrected and unresolved disagreements are explicitly adjudicated, expected next verdict is CONDITIONAL_APPROVE or APPROVE depending on whether token/session and onboarding contracts are also completed.
