# R1 Clean-Slate 架构评审 — 本地用户认证

Verdict: REQUEST_MAJOR_CHANGES

## 发现的问题

[A1] [High] 文档声称“核心实现在 engine MCP 层，Gateway 是薄封装”，但认证边界放在 Engine 会把游戏模拟/部署控制平面和互联网认证入口耦合在一起。已知失败模式是把 auth provider、密码哈希、注册限流、session 签发都塞进业务核心，后续会导致 engine 难以无状态水平扩展，也让离线 replay/确定性核心背负非确定性 I/O 和安全审计责任。建议修正为：Engine 只保留证书验证和 player identity 消费；注册、登录、密码哈希、refresh token、PoW challenge 生命周期放在 Gateway/Auth service；MCP tool 可以作为调用入口，但应路由到 auth control-plane，而不是让 engine 直接拥有密码库。

[A2] [High] `player_id = blake3("local:" + username_lowercase) → u64` 的 provider 隔离方向正确，但缺少全局身份命名空间契约：OAuth2 示例是 `provider:subject`，Local 是 `local:username`，但文档没有规定 provider 字符串注册表、subject canonicalization、hash 截断位宽、碰撞处理、迁移策略和 player_id 类型边界。若 OAuth provider subject、local username、未来 email/passkey provider 都靠字符串拼接，会出现“看起来隔离、实际规范漂移”的长期风险。建议把 `IdentityKey { provider, subject } -> PlayerId` 提升为统一规范，明确 provider 枚举、subject 不可变性、hash_to_u64 算法、碰撞检测索引，以及 FDB 中 `identity/<provider>/<subject> -> player_id` 的唯一约束。

[A3] [High] `challenge` 同时由服务器生成、存储，又由客户端在 `swarm_register` 参数中回传；事务示例只检查 `pchallenge/<id>` 存在，没有展示从 FDB 读取并比对 challenge/difficulty/expiry 后再验证 nonce。这样接口把权威 challenge 内容交给客户端回填，容易实现成“只验证客户端给的 challenge + 固定 DIFFICULTY”，导致 challenge_id 与 challenge 脱钩、TTL/难度失效或重放窗口扩大。建议 `swarm_register` 只接收 `challenge_id` 和 `nonce`，服务端从 FDB 原子读取 `{challenge,difficulty,expires_at}`，验证未过期、未消费、难度匹配后再 clear。

[A4] [High] PoW 成本估算明显不可靠：文档把 difficulty 定义为“前导零字节数”，difficulty=4 预期约 2^32 次尝试，却写成单核约 1.3 秒。这个数量级在浏览器、移动设备、CI、AI agent sandbox、低端 VPS 上差异极大，甚至可能从秒级变成分钟级；同时 GPU/ASIC 对 blake3 brute force 很友好，对批量注册者的边际成本更低。建议不要把固定 difficulty=4 作为架构常量；改为服务端可配置/可动态调节的 bit-level difficulty，配合注册配额、全局 backpressure、失败计数和可观测指标。PoW 可保留为 agent-friendly 摩擦，但不能作为唯一反滥用层。

[A5] [Medium] `swarm_login` 不需要 PoW 的理由写成“每 tick 已限速（10/min per IP）”，但登录是 `CommandSource::McpQuery`，不参与游戏 tick；同时设计原则又说 PoW 替代 IP rate limiting、无 IP 追踪。这里存在跨层概念混淆：认证请求的速率限制、游戏 tick 调度、Gateway IP 维度不是同一个控制面。建议明确登录限速属于 Gateway/Auth service，至少按 username、source network、session/device、全局队列多维限流；MCP 层只能返回统一错误，不能依赖 tick 频率。

[A6] [Medium] certificate/session 模型声称与 OAuth2 完全一致，并复用 `OAuth2LoginResult`，这是兼容方向，但命名和语义会误导新人：本地登录返回 `OAuth2LoginResult`、调用 `issue_login("local", username, "local-credential", ...)`，会把“认证机制”和“登录结果 DTO”长期绑定在 OAuth2 术语上。建议重命名为 `AuthLoginResult` / `LoginSession`，OAuth2 与 Local 都是 provider；保留 wire-compatible 字段但清理内部类型命名。

[A7] [Medium] Refresh token 与 revoke 的共享模型没有说明本地认证的 token 存储键、轮换策略、绑定维度和吊销传播。文档只说 `swarm_token_refresh` / `swarm_auth_revoke` 无需修改，但 Local 引入密码登录后会产生更多长期 refresh token，且 AI agent 会把凭据长期落盘。建议补充 refresh token 以 `player_id + client_public_key/session_id` 绑定、刷新时轮换、revoke 按 session/device 粒度、生效延迟和 FDB key 结构；否则“共享 session”只是返回结构一致，不是安全语义一致。

[A8] [Medium] FDB 用于凭据存储方向可接受，但 key/value 设计过于裸：`users/<username_lowercase>` 混在世界状态 FDB 中，没有明确 subspace、tenant/universe 隔离、备份恢复边界、加密/访问控制、schema version、审计日志和冷热路径分离。密码库和世界状态的可靠性/合规要求不同；共用 FDB cluster 可以，但不应共用随意字符串前缀。建议定义 Auth subspace：`auth/users/<username>`、`auth/identities/<provider>/<subject>`、`auth/challenges/<id>`、`auth/sessions/<id>`，所有 value 带 `schema_version`，并明确权限和备份策略。

[A9] [Medium] 注册事务示例在事务内执行 `hash_password()`，argon2id 约 19MiB/attempt 且可能耗时较长，会拉长 FDB 事务生命周期，增加冲突和重试成本；如果事务重试，密码哈希可能重复执行，甚至因随机 salt 导致行为复杂。建议先在事务外完成输入校验和密码哈希，再用短事务执行 challenge 消费 + username 唯一检查 + 写入；若 FDB commit 冲突，只重试短事务，不重复高成本计算，或将 hash 作为已准备好的不可变输入。

[A10] [Low] 用户名规则和 player_id 绑定 username，且 v1 不支持身份合并/改名，等于把显示名、登录名、稳定 subject 三者合一。短期简单，但长期会卡住改名、大小写策略、保留字扩展和社区身份展示。建议拆分 `account_id/player_id`、`login_username`、`display_name`；v1 可不实现改名，但数据模型不要把不可变身份建立在可见用户名字符串上。

[A11] [Low] 前端把 `refresh_token + certificate` 存入 localStorage 是已知 XSS 放大器。作为 MVP 可以接受，但需要在设计中标注这是临时方案，并为 httpOnly secure cookie 或 WebCrypto-bound token 留出迁移路径。否则本地密码账号会比 OAuth2 更容易被前端脚本窃取长期凭据。

[A12] [Low] MCP tool 表与 local-auth 主文档基本一致，但 `interface.md` 把认证工具列为 `swarm_auth_revoke`，local-auth 只说明新增 3 个 tool，未补全本地账号场景下的 `token_refresh/revoke` 参数是否需要 provider/session_id/client_public_key。建议在 MCP API 参考中补齐认证工具的统一 schema，并明确本地认证不新增动作通道，仍只影响身份和部署权限。

## 亮点

- 本地认证与 OAuth2 并列，而不是把本地账号伪装成某个 OAuth provider；这个方向正确，适合离线部署、CI 和 AI agent 自注册。
- AI agent 与人类玩家仍通过相同 certificate、session、WASM deploy 路径进入系统，没有引入“AI 特权执行器”，符合 Swarm 既有公平性架构。
- Provider 隔离的 Player ID 思路是对的；`local:` 与 `github:`/`google:` 的命名空间隔离能避免最常见的 subject 碰撞。
- 使用 argon2id 存储密码是合理选择，参数也在可接受范围；统一错误 `invalid_credentials` 避免了基础用户名枚举。
- 使用 FDB 事务保护“挑战消费 + 用户创建”的方向正确，能防止重复注册竞态，只是事务边界和 key schema 需要收紧。
- MCP API 没有新增 `swarm_move`/`swarm_attack` 等游戏动作，仍保持 MCP 是管理/观测/部署界面的架构合同。

## 总体评价

这个方案的产品方向成立：Swarm 需要本地账号，尤其是为了离线部署、自动化测试和 AI agent 自注册；与 OAuth2 共用证书和部署链路也是正确抽象。但当前文档把认证系统实现下沉到 Engine MCP 层，且对 PoW、session、FDB schema、identity namespace 的关键契约写得过于乐观，属于“看起来能跑、上线后会在安全边界和演进边界爆炸”的典型模式。建议在进入实现前先做一次架构重切：把 Auth 作为 Gateway/Auth control-plane，Engine 只消费已签发身份与证书；同时冻结统一 `IdentityKey -> PlayerId`、Auth FDB subspace、challenge/server-authoritative PoW、refresh token 生命周期。完成这些修正后，方案可以降为 CONDITIONAL_APPROVE。

## Missing

- 统一 Auth domain model：`IdentityKey`、`PlayerId`、`Account/User`、`Session`、`Certificate` 的关系图。
- Auth FDB subspace schema：users、identities、sessions、refresh tokens、challenges、revocation list 的 key/value、版本和唯一约束。
- OAuth2 与 Local 共用的 sequence diagrams：register/login/refresh/revoke/deploy certificate verification。
- PoW 可调难度和观测指标：solve latency、registration throughput、failure rate、abuse pressure、动态降级/升高策略。
- Gateway/Auth service 与 Engine MCP 的责任边界：哪些接口可由 MCP 调用，哪些状态只能由 Gateway/Auth 写入。
- Token 存储与前端安全路线：localStorage 的 MVP 风险、httpOnly cookie 或 WebCrypto-bound token 的迁移计划。
- 账号生命周期：密码修改、账号删除、改名、身份合并虽然可推迟，但需要数据模型预留位。

## Phase Ordering

1. 先冻结身份与会话规范：定义 `IdentityKey -> PlayerId`、provider registry、hash 算法、碰撞处理、`AuthLoginResult` wire schema。
2. 再调整边界：把注册、登录、密码哈希、PoW、refresh token 存储放入 Gateway/Auth control-plane；Engine 只负责证书验证和部署权限消费。
3. 然后设计 FDB Auth subspace：短事务、schema version、唯一索引、challenge/session/revocation 生命周期。
4. 接着实现 MCP/REST 薄入口：MCP tool 和 REST endpoint 共享同一 Auth service，不复制认证逻辑。
5. 再实现前端 Local Account UI 和 AI agent 自注册示例，PoW difficulty 必须从服务端返回且可配置。
6. 最后补全集成测试：OAuth2 login 与 Local login 产生等价 certificate/session；refresh/revoke/deploy 对两种 provider 行为一致；challenge 不可重放且服务端权威验证。
