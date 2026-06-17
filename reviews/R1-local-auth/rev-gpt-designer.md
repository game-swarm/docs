Verdict: CONDITIONAL_APPROVE

## 发现的问题

[High] Agent 代理注册的凭据交付与归属体验没有闭环。文档说明 agent 可返回 certificate + refresh_token 给人类，再由人类手动或通过 agent 存入前端，但这一步涉及高价值凭据复制、保存位置、误发给聊天上下文、浏览器导入、以及“账号到底归谁”的心理模型。建议补充一条正式的代理注册 UX：agent 只生成一次性导入链接或短期 handoff token，前端通过 HTTPS 接收并换取 session；同时明确 agent 不应长期保存人类账号 refresh_token，除非用户显式授权托管。

[High] MCP 自注册能完成认证，但 AI 仅凭 MCP resources 学会“下一步怎么玩”的闭环仍不完整。interface.md 有 `swarm_get_docs`、`swarm_get_schema`、`swarm_get_available_actions`，local-auth.md 也有注册三步，但没有说明注册成功后如何通过 MCP discover onboarding resource、生成第一份可部署 WASM、验证模块、部署、解释首 tick 失败。建议补充 `swarm_get_docs("onboarding/local-auth-to-first-deploy")` 或等价 resource，覆盖 challenge→solve→register→validate_module→deploy→explain_last_tick 的端到端机器可读教程。

[Medium] 人类浏览器注册的首小时体验低估了 PoW 对“首次进入游戏”的情绪影响。~1.3s 本身可接受，但当前 UI 文案只有 “Register needs ~1s PoW proof”，没有进度、取消、低性能设备降级、移动端耗时提示、失败重试策略。建议将 PoW 包装为“正在保护开放世界免受批量小号攻击”的可解释加载状态，显示 spinner/progress、预计耗时、失败后自动重新取 challenge，并在耗时超过 5s 时提示用户可继续等待或稍后重试。

[Medium] 密码生命周期对普通玩家不完整。v1 明确不做密码重置，并将密码修改推迟到 v1.1；这对本地账号首发可用性有风险，因为忘记密码意味着永久失去身份和资产。建议至少在 v1 中提供“已登录状态下修改密码”和“导出/备份恢复凭据提示”；若不做重置，应在注册 UI 明确提示“请保存密码，当前版本无法找回”。

[Medium] AI agent 自动密码策略安全合理，但可用性文档不足。`random_hex(32)` 强度足够，但文档没有定义推荐存储位置、权限、轮换、refresh_token 与密码的区别，也没有给出 agent 丢失密码但仍持有 refresh_token 时的恢复路径。建议新增 AI 凭据管理小节：用户名、密码、refresh_token、certificate 分别何时需要持久化；推荐 secret store / local file 权限；token refresh 失败后何时回退到 `swarm_login`。

[Medium] 注册错误处理覆盖了弱密码、用户名占用、PoW 失败、凭据错误，但缺少面向前端和 agent 的错误恢复矩阵。边界情况包括 challenge 过期、challenge 已消费、客户端公钥格式错误、FDB 临时不可用、argon2 资源耗尽、PoW 难度升级、浏览器 tab 后台导致求解被限速。建议在文档中增加错误码表：code、可重试性、用户可见文案、agent 应采取的下一步。

[Low] 用户名规则对社区身份感有些保守。只允许 ASCII `[a-zA-Z0-9_-]` 便于实现和 player_id 确定性，但会削弱非英语玩家的表达和社区认同。建议保留 canonical username 为 ASCII，同时允许独立 `display_name` 支持 Unicode、改名和前端展示，避免把技术标识和社交身份绑死。

[Low] 本地认证与长期社区传播的连接还不够强。认证方案解决“进门”，但没有利用注册完成节点引导玩家进入旁观者模式、示例 replay、starter bot 或社区分享。建议注册成功响应或前端 onboarding 给出三条首小时路径：观战一个热门 replay、部署 starter bot、进入 sandbox 房间试运行。

## 亮点

- 三种注册场景覆盖完整：人类浏览器、AI MCP 自注册、人类通过 agent 代理注册都被明确建模，方向正确且符合 Swarm “AI 与人类同级玩家”的愿景。
- `challenge → solve → register` 三步 API 简洁，MCP 与 Gateway REST 薄代理共享同一核心逻辑，降低了前端、人类脚本和 AI agent 的认知差异。
- 本地认证复用现有 `OAuth2LoginResult`、`WebAuthSession`、`PlayerCertificate` 与 Ed25519 证书链，下游部署和权限系统不需要区分登录来源，这是很好的产品一致性设计。
- 用 PoW 替代 IP rate limiting 很适合 agent-friendly 和 NAT 友好的开放注册场景；相比验证码，它不会破坏 AI 自主注册能力。
- 确定性 `player_id = blake3("local:" + username_lowercase)` 与 OAuth provider namespace 模型一致，便于离线推导、调试和跨系统引用。
- 文档提供了 API 示例、错误示例、测试清单、Python/JavaScript PoW 参考实现，对工程落地很友好。

## 总体评价

这个本地认证方案的核心设计是可接受的：它把本地用户名密码、OAuth2、AI agent 自注册放在同一证书模型下，API 也足够短，适合作为 Swarm 首个开放注册入口。主要问题不在密码哈希或 player_id 这类底层选择，而在“注册之后玩家/agent 如何安全、顺滑地进入第一小时游戏体验”：代理注册凭据交付、AI onboarding resource、PoW 等待反馈、密码恢复/改密、错误恢复矩阵都需要补齐。建议在修正上述 High 与 Medium UX 缺口后进入实现；不需要推翻整体架构。