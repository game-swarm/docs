# R-appcert-clean-slate — GPT-5.5 Economy Review

## Verdict

CONDITIONAL_APPROVE

认证重设计的主干方向是对的：Server CA + CSR + application-layer certificate + canonical request signature 形成了比 OAuth/JWT/password 更适合自托管、AI agent、离线部署和联邦世界的信任模型。从经济/资产/代码部署视角看，证书用途隔离、部署提交时有效性、联邦本地重签、设备级吊销都能支撑公平竞争和资产隔离。

我没有发现必须推倒重来的 blocker。需要在进入实现前修正几处文档断层：Gateway/MCP 认证表述仍残留 JWT，部署 nonce 工具链在 reference 中缺口，账号删除的资产 transfer 规则过于宽松，联邦资产叙述前后冲突，入门路径无法让新人按新认证体系成功部署。

## Top findings

### A1 — High — Gateway MCP 认证仍残留 JWT 表述，容易把主路径实现成旧 token 模型

Category: doc inconsistency / security gap / API gap

Evidence:
- `specs/12-gateway-protocol.md:119` 写 Gateway MCP 职责包含 “JWT 认证（mcp audience）”。
- `specs/12-gateway-protocol.md:163` 的权威矩阵要求 MCP Agent 使用 `Application certificate + signed request`，header 为 `Swarm-Certificate-Chain` + `Swarm-Signature` + `X-Swarm-Transport: mcp`。
- `design/auth.md:1002` 明确应用层证书链 + 用户私钥签名是唯一权威凭证。
- `design/auth.md:1015` 明确 JWT/access_token 不是独立认证根。
- `specs/security/03-mcp-security.md:157` 到 `specs/security/03-mcp-security.md:185` 同样规定 JWT/access_token 仅是 Web session 兼容格式，不用于 MCP/Agent 主认证路径。

Concern:
这是一类“看起来只是文字残留，实际会炸”的断层。Gateway 是实现者最可能先看的入口文档；如果 Gateway 侧按 JWT audience 做 MCP 主认证，后续的 certificate audience、CRL、nonce、signature、federated local resign 都会被旁路或重复实现。已知失败模式类似 OAuth/JWT 迁移到 mTLS/app-cert 时保留两套主路径，最后形成“安全设计在 auth 文档里，生产入口按 legacy token 放行”。

Impact:
- AI agent / CLI 可能绕过 canonical request signature。
- 证书吊销与设备级 revoke 无法成为统一控制点。
- MCP、REST、Browser 的 audience 隔离会从协议约束退化为约定。

Suggested resolution direction:
把 Gateway MCP 职责改为“application certificate chain + canonical request signature verification”，JWT 仅保留 Browser/Web session compatibility 路径，并让 `specs/12-gateway-protocol.md` §5 引用 §9 auth matrix 作为唯一来源。

### A2 — High — Deploy nonce 是安全 spec 的必需步骤，但 MCP/interface reference 没有对应工具

Category: API gap / doc inconsistency / deferred implementation concern

Evidence:
- `specs/security/09-command-source.md:99` 要求 `deploy_nonce` 是服务端签发、短 TTL、单次消费，并通过 MCP `swarm_deploy_challenge` 获取。
- `specs/security/09-command-source.md:103` 到 `specs/security/09-command-source.md:116` 把 `swarm_deploy_challenge` → signed DeployPayload → nonce 验证列为部署验证流程。
- `specs/security/09-command-source.md:253` 到 `specs/security/09-command-source.md:277` 定义 Deploy Nonce 生命周期和 pending deploy token。
- `design/interface.md:23` 到 `design/interface.md:26` 的部署工具列表只有 `swarm_deploy`、`swarm_validate_module`、`swarm_rollback`、`swarm_list_modules`。
- `specs/reference/mcp-tools.md:18` 到 `specs/reference/mcp-tools.md:25` 同样没有 `swarm_deploy_challenge`。

Concern:
安全 spec 把 deploy nonce 当成防重放和部署归属的核心机制，但开发者参考里不可调用。新人或 SDK 作者会自然实现成 “swarm_deploy(wasm, signature)” 一步式接口，导致 nonce 生命周期、pending deploy token、IP/audience binding 落空。

Impact:
- 代码部署重放窗口无法按设计收窄。
- CodeSigningCertificate 过期语义和 accepted_at_tick 设计会更难审计。
- AI agent 自动部署链路缺少稳定 schema，容易各 SDK 自行发明参数。

Suggested resolution direction:
在 `design/interface.md`、`specs/reference/mcp-tools.md` 和 auth API 一览中补齐 `swarm_deploy_challenge` 与 pending deploy token 的接口形态，明确 `swarm_deploy` 必须携带 `DeployPayload`、certificate chain 和 signature，而非裸 `wasm_signature`。

### A3 — High — 账号删除的 asset transfer 规则可被用作经济清算/资产洗白通道

Category: security gap / UX gap / deferred implementation concern

Evidence:
- `design/auth.md:892` 到 `design/auth.md:899` 规定删除账号时可按 `asset_disposition` 执行 abandon/recycle/transfer，transfer 会把资产转移给指定 player。
- `design/auth.md:936` 到 `design/auth.md:961` 规定 transfer 只要求接收方签名确认 asset_summary，且执行后不可逆。
- `design/modes.md:22` 描述 World 是持续沙盒，目标包括建造、控制、经济、社交，不存在游戏结束。
- `design/modes.md:70` 对 PvE 掉落有全局经济注入上限，说明设计已意识到经济通胀/刷资源风险。

Concern:
“账号删除 = 全资产转移”在 MMO 经济里非常敏感。只要求接收方签名确认资产摘要，缺少债务、竞赛锁定、近期交易冷却、ban/compromise 状态、未结算拍卖/市场订单、世界税/销毁率、资产快照一致性等约束。成功案例通常把账号删除和资产迁移拆成独立、可审计、可延迟撤销的流程；失败案例是删除/恢复/转移路径成为 RMT 洗钱、规避惩罚、绕过战败成本的后门。

Impact:
- 被盗账号可在 5 分钟内把全部资产转走，恢复流程默认保留旧证书时更复杂。
- 玩家可通过小号删除转移绕过正常 transfer cost、领土暴露、市场税或战争风险。
- 账号删除这一 UX 操作被耦合成经济状态迁移，后续很难安全扩展。

Suggested resolution direction:
在设计层明确 asset transfer 是独立经济操作，不应作为普通账号删除的默认同步步骤。若保留 transfer，应至少定义 pending period、admin/audit visibility、资产锁、不可转移资产、近期安全事件冻结、世界配置税/销毁率、撤销窗口与 TickTrace 证据。

### A4 — Medium — 联邦资产叙述前后冲突，会误导跨世界经济边界

Category: doc inconsistency / API gap

Evidence:
- `design/README.md:35` 写世界之间形成联邦宇宙，玩家可跨世界拥有身份和资产，并通过异步方式交互（转移资源、共享排名）。
- `design/auth.md:1103` 写不同世界的同一联邦玩家拥有独立本地 player_id 和资产，联邦身份只用于认证 bootstrap，不共享游戏状态、不共享模块、不共享排名。
- `design/auth.md:1048` 到 `design/auth.md:1052` 的 federation trust levels 仅覆盖 login、login+code、observe、admin，并没有 asset/resource transfer trust level。
- `design/auth.md:1107` 到 `design/auth.md:1113` 强调远端证书不直接授予本地操作权限，部署也必须本地 CodeSigningCertificate。

Concern:
总览说“转移资源、共享排名”，auth 又说“不共享资产/排名”。这不是措辞问题，而是联邦经济模型的边界问题。跨世界资源桥接、排名共享、身份 bootstrap 是三种完全不同的信任/清算模型；如果总览先承诺资产互通，后续实现者可能把 federation login 当成 asset bridge 的前置能力。

Impact:
- 服务器运营者无法判断 trust=`login+code` 是否隐含任何经济互通。
- 玩家对跨世界资产拥有权和排名继承产生错误预期。
- 后续若增加资源桥，会缺少 escrow、exchange rate、rollback、remote revocation、double-spend 防护等设计前置。

Suggested resolution direction:
先把当前 app-cert 设计明确限定为“身份 federation + 本地重签 + 本地资产隔离”。如果跨世界资源/排名是未来目标，应单独放入 future spec，定义 trust level、桥接资产类型、清算周期、失败回滚与治理，而不要在主 README 暗示已支持。

### A5 — Medium — Getting Started 和 MCP reference 不足以让新人按新认证体系完成第一次 AI 部署

Category: UX gap / doc inconsistency

Evidence:
- `GETTING-STARTED.md:67` 到 `GETTING-STARTED.md:71` 的 Web UI 路径提到确认 Root CA fingerprint、生成本地设备密钥并提交 CSR。
- `GETTING-STARTED.md:73` 到 `GETTING-STARTED.md:76` 的 MCP 路径只有 `swarm_deploy(module_bytes, wasm_signature)`。
- `design/auth.md:147` 到 `design/auth.md:164` 对 AI player / CLI 自注册要求选择或生成 Ed25519 key、调用 challenge、提交 CSR、持久化证书链和私钥引用、用 CodeSigningCertificate 签 module_hash + metadata。
- `specs/reference/mcp-tools.md:88` 到 `specs/reference/mcp-tools.md:98` 只给认证模型概念，没有端到端示例。

Concern:
新认证体系正确但上手路径不闭环。对 AI agent 而言，第一天体验应是“获取 server trust → pin fingerprint → register challenge → submit CSR → deploy challenge → sign deploy payload → deploy”。现在 Web UI 还算可推断，MCP/CLI 只留下旧式一行部署，容易导致 SDK、教程、agent prompt 全部绕过证书生命周期。

Impact:
- 新人无法判断私钥、certificate bundle、recovery material 应保存在哪里。
- AI agent 自注册可能把长期凭据写入聊天日志或临时目录。
- 文档声称降低 OAuth 门槛，但实际首个 bot 的路径不够直观。

Suggested resolution direction:
补一个 AI/CLI first deploy recipe：含 `swarm_get_server_trust`、fingerprint pinning、`swarm_register_challenge`、`swarm_submit_csr`、证书本地存储、`swarm_deploy_challenge`、signed `DeployPayload`、`swarm_deploy`。这应成为 SDK smoke test 的脚本化流程。

### A6 — Low — 证书 TTL 表述存在局部不一致，但不改变总体模型

Category: doc inconsistency

Evidence:
- `design/auth.md:259` 到 `design/auth.md:264` 的用途隔离证书表写 `ClientAuthCertificate` TTL 24h、`CodeSigningCertificate` TTL 7d、`AdminCertificate` TTL 1h。
- `design/auth.md:282` 到 `design/auth.md:287` 的设备策略表写常用设备 30–180 days、临时设备 15min–24h、管理员 15min–1h。
- `design/auth.md:969` 到 `design/auth.md:974` 的 token 生命周期表写 ClientAuth 和 CodeSigning 都是 15min–180 days。

Concern:
TTL 可以是 profile policy，但当前三个表看起来像三个不同默认值。实现者可能把用途 TTL 和设备 profile TTL 当成并列配置，导致证书续签 UX、CRL 保留窗口和 federation revocation cache 的计算不一致。

Impact:
- CRL 窗口公式依赖 max_certificate_ttl；默认值不清会影响在线吊销保留。
- AI agent 长期运行时续签频率不清，可能过度续签或意外过期。

Suggested resolution direction:
明确一张权威 TTL policy 表：base TTL by certificate usage，override/upper-bound by device profile，最终 TTL = min(policy constraints)。

## Strengths

- 应用层证书不进入系统/browser trust store，且与传输层 TLS/mTLS CA 隔离；这避免了自托管游戏常见的“为了登录让用户安装危险根证书”失败模式。
- 用途隔离证书清楚区分 client_auth、code_signing、admin、federation；从经济角度看，普通登录凭据不能直接签代码或治理证书是正确抽象。
- 代码签名证书“提交部署时有效，已部署模块不因自然过期停止”是务实选择；它避免了长期 bot 因证书续签失败突然掉线，同时保留吊销作为安全事件处理点。
- 多设备证书 + 精确 certificate_id 吊销适合 AI agent、浏览器、人类代理注册共存；不需要因为丢手机就清空整个账号。
- 联邦本地重签是正确边界：远端身份只作为 bootstrap proof，本地操作必须拿本服证书，默认不接受远端 code/admin。
- MCP 不做游戏动作、AI 和人类都必须部署 WASM，这保住了游戏经济公平性的核心：同样的 fuel、同样的 sandbox、同样的可见性边界。

## Concerns

### A1. Legacy auth wording at Gateway

见 Top finding A1。Gateway 文档必须消除 JWT 主路径残留，否则实现会自然回退到旧 token 模型。

### A2. Deploy API split is under-specified

见 Top finding A2。安全 spec 和 reference API 的断层会直接影响 SDK 和 agent function-calling schema。

### A3. Account deletion is overloaded with economic transfer

见 Top finding A3。账号生命周期和资产迁移应解耦，否则删除/恢复路径会变成经济后门。

### A4. Federation boundary must be one story

见 Top finding A4。当前同时暗示“跨世界资产/排名交互”和“资产/排名不共享”。建议当前版本只承诺身份 federation。

### A5. Newcomer path needs executable shape

见 Top finding A5。证书体系正确但复杂，必须给新人和 AI agent 一个按步骤可执行的 first deploy recipe。

## Missing

- 缺少 `swarm_deploy_challenge` / pending deploy token 在 MCP reference 与 design/interface 中的正式 schema。
- 缺少 asset transfer 的经济治理规则：冷却、锁定、税/销毁率、不可转移资产、compromised-account freeze、审计和撤销窗口。
- 缺少 federation economic model 的明确边界：当前是否只做 identity bootstrap；若未来做资源桥，需单独 spec。
- 缺少 AI/CLI credential store 规范的开发者级示例：文件路径、权限、证书 bundle 格式、recovery material 存放和日志脱敏测试。
- 缺少统一 TTL policy 表，解释 usage TTL、device profile TTL、CRL retention、federation revocation cache 之间的关系。

## Questions/Assumptions

- Assumption: 本轮 app-cert redesign 的目标是先替换认证根，不同时交付跨世界资产桥。
- Assumption: `refresh_token` / JWT 只服务 Browser/Web session compatibility，不允许成为 MCP/CLI 主认证材料。
- Question: `asset_disposition = "transfer"` 是世界级可选策略，还是计划作为默认账号删除 UX 暴露给普通玩家？如果是后者，我建议降级为 future spec。
- Question: 证书吊销 reason 对已部署模块的 freeze/rollback/continue 策略是世界配置、管理员操作，还是固定规则？经济侧需要知道这是否会影响比赛/排名结算。
- Question: 联邦 `trust = "login+code"` 是否允许基于远端身份自动拿本地 CodeSigningCertificate，还是仍需本地新 CSR + 本地 policy 审核？文档倾向后者，但应在 reference 中写死。

## Phase Ordering

1. 先修正文档一致性：Gateway MCP 认证表述、deploy nonce API、联邦资产边界、TTL policy。这些是实现前的协议面，不应留到代码阶段靠 PR review 发现。
2. 再补齐端到端 UX：AI/CLI first deploy recipe、SDK schema、credential storage examples。目标是让新人不读完整 auth 设计也能安全完成第一次部署。
3. 然后冻结经济危险路径：账号删除与资产 transfer 解耦；若保留 transfer，先定义 pending/lock/audit/tax/revoke，再实现。
4. 最后进入实现：Auth Service、Gateway verifier、MCP auth tools、deploy nonce state machine、CRL/cache。实现顺序应让 `swarm_submit_csr` 和 `swarm_deploy_challenge` 成为第一批集成测试，而不是后补功能。

## Final note

整体架构不像失败的“JWT 包一层证书壳”方案；它更接近成功的 capability certificate + local re-sign + signed request 模型。条件批准的原因是：核心抽象合理，但入口文档和经济边界还有足够多的“看起来没问题，实际实现时会分叉”的缝隙。修完这些缝隙后，可以进入实现。