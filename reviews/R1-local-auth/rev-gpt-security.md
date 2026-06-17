Verdict: CONDITIONAL_APPROVE

## 发现的问题

[High] PoW challenge 的服务端绑定校验不够明确，存在实现偏差后退化为可重放/可替换 challenge 的风险。文档要求 challenge_id 一次性使用、5 分钟 TTL，并在接口中同时提交 challenge_id 与 challenge；但附录事务示例只检查 pchallenge/<id> 是否存在并随后使用 params.challenge 验证 PoW，没有显式说明必须从 FDB 读取 challenge 记录并比较 stored.challenge == params.challenge、stored.difficulty == params.difficulty/server difficulty、expires_at >= now。若实现者照示例走，攻击者可能拿一个有效 challenge_id 搭配自己可控或低难度 challenge 字符串，或利用前后端参数不一致造成验证绕过/错误消费。建议 swarm_register 中只信任服务端存储的 challenge/difficulty/expires_at，不信任客户端传回的 challenge/difficulty；客户端最多提交 challenge_id + nonce；消费 challenge 前后都必须在同一 FDB 事务内完成读取、过期判断、PoW 校验和 clear。

[High] swarm_register_challenge 本身缺少滥用控制，可能成为低成本状态写入 DoS。设计用 PoW 替代 IP rate limiting，但获取 challenge 无需 PoW，且每次会写入 FDB 的 pchallenge/<id>，攻击者可以用最小请求批量制造 5 分钟 TTL 的热键/垃圾记录，消耗 FDB 写入、存储和清理成本；这正是“最小请求产生最大服务端开销”的典型 DoS 面。建议 challenge 生成接口增加轻量全局/来源级限速、并发上限、容量水位、惰性或后台 TTL 清理策略；更优做法是将 challenge 设计为服务端签名的无状态 token，只在成功注册时记录已消费 nonce/token id，或采用短 TTL + bounded LRU/DB subspace 配额。

[High] 登录暴力破解防护过度依赖 argon2id，且“10/min per IP”边界不清。文档说 swarm_login 不需要 PoW，因为每 tick 已限速 10/min per IP 且 argon2id 足够慢；但 MCP 直连、Gateway REST、反向代理、NAT、IPv6 地址轮换、多 agent 并发都可能绕过单一 IP 计数。argon2id 会保护离线破解，但在线猜测仍需要账号维度和全局维度节流，否则攻击者可对同一用户名分布式撞库，也可用不存在用户名路径制造枚举侧信道或 CPU 消耗差异。建议明确在 engine 权威层实现 username_lowercase + source + global 三层限速/退避；不存在用户也应走等成本 dummy argon2id 校验，避免通过响应时间区分用户是否存在。

[Medium] argon2id 参数声明与示例实现存在不一致风险。文档声明 OWASP 推荐参数 m=19456 KiB、t=2、p=1，但示例代码使用 Argon2::default()，这会依赖 crate 默认值，未来版本或默认 profile 变化可能偏离文档，且读者不一定知道默认值是否正好等于 m=19456,t=2,p=1。建议示例和实现都显式构造 Params::new(ARGON2_MEMORY_KIB, ARGON2_ITERATIONS, ARGON2_PARALLELISM, Some(32))，并在测试中断言 PHC 字符串包含 m=19456,t=2,p=1。参数本身作为最低 OWASP 档位可以接受，但如果目标包含高价值账号或服务器内存充足，建议预留配置项支持提升到 46 MiB/1 iter 或更高成本档。

[Medium] PoW difficulty=4 的成本估算需要用真实目标平台校准，且前导“零字节”难度可能对浏览器/移动端过重。文档写 difficulty=4 约 4.3B 次尝试、单核约 1.3s，这等价于每秒约 3.3B 次 blake3 尝试；该数值对 Rust native/SIMD 可能乐观，对 JavaScript/WASM、低端移动设备、无 SIMD 环境可能显著更慢。若前端注册实际卡几十秒，用户会重试并放大 challenge 申请压力。建议在 Rust native、Node、主流浏览器 WASM、低端设备上基准测试后确定默认 difficulty，并支持按部署配置动态调整；同时把难度从“前导零字节”改为“前导零 bit 数”，便于细粒度调参，例如 22–28 bits，而不是只能 24/32/40 bits 大步跳。

[Medium] 密码策略对人类用户偏弱，弱口令黑名单过短。最小 8 字符 + 至少 1 字母 1 数字会接受大量已泄露弱密码变体，文档仅列出 4 个禁止密码，无法覆盖 credential stuffing 常见集合。建议采用长度优先策略：人类密码最低 12 字符或 passphrase 16+ 字符；接入 zxcvbn/常见泄露密码库的服务端检查；禁止 username、player_id、常见 leetspeak/大小写变体；保留 128 字符上限以防超长输入 DoS。AI agent random_hex(32) 的建议很好，但不能替代人类密码强度策略。

[Medium] 用户名占用接口会泄露注册状态，需要明确这是可接受的公开属性或降低可枚举性。登录失败统一 invalid_credentials 是正确的，但注册失败返回 username_taken 且 message 包含用户名，本质上允许枚举本地账号是否存在。对于公开排行榜/玩家名系统这可能可接受，但文档应在威胁模型中显式说明“用户名注册状态是公开信息”；若不接受，应改成更模糊的响应或要求前端只在注册流程中显示通用冲突提示。无论选择哪种，都应避免在日志和错误链中记录原始密码或完整凭据。

[Medium] AI agent 自注册缺少滥用后的治理边界。设计允许 AI agent 通过 MCP 大规模自注册并获取与人类相同的证书和 refresh_token；PoW 只能提高单账号成本，不能表达配额、信誉、设备/agent 归属、批量封禁和异常检测策略。建议补充 agent 注册的治理模型：每个部署/tenant 的注册开关、每日注册预算、证书签发审计字段 provider=local/auth_method=pow、refresh_token 撤销与批量封禁、异常注册速率告警、以及 tournament/生产世界是否允许匿名本地注册的配置开关。

[Low] player_id 由 username_lowercase 确定性推导会让身份空间可离线枚举。该模式与 OAuth2 provider:subject 一致，但本地用户名通常更短、更可猜，外部观察者可以预计算常见用户名到 player_id 的映射。若 player_id 在游戏内本来公开，则影响有限；若某些 API 依赖 player_id 不可猜，则这是 IDOR 的前置条件。建议文档明确 player_id 不作为秘密，所有基于 player_id 的读取/写入必须经证书授权和可见性检查；如需降低枚举性，可考虑存储随机 user_id 并单独保留 username 唯一索引。

[Low] HTTPS、CSRF、CORS 与前端 token 存储边界写得过于简略。文档只写“假设 HTTPS”和 localStorage 保存 refresh_token + certificate。若 Gateway REST 用 cookie，则需要 CSRF；若用 bearer token，则需要严格 CORS、XSS 防护和 token 生命周期说明。localStorage 中 refresh_token 对 XSS 高敏感。建议补充：生产强制 HTTPS/HSTS；REST 只接受 JSON + 同源/CORS allowlist；refresh_token 是否放 HttpOnly Secure SameSite cookie 或 localStorage 的取舍；前端不得持久化密码；日志、analytics、错误上报必须脱敏。

## 亮点

- 选择 argon2id 而非 bcrypt/PBKDF2 是正确方向，19 MiB/2 iter/p=1 符合当前 OWASP 最低推荐档位，并保留了内存硬抗 GPU 的安全属性。
- 登录失败统一 invalid_credentials，明确不区分“用户不存在”和“密码错误”，这是防用户名枚举的必要设计。
- PoW challenge 有 TTL 和一次性使用的目标设计，且计划用 FDB 事务原子消费 challenge 与创建用户，方向正确，能避免常见注册竞态和重复使用问题。
- 本地认证复用现有 Ed25519 PlayerCertificate、refresh_token、swarm_token_refresh / swarm_auth_revoke，减少了认证后权限模型分叉，降低了下游 IDOR/权限遗漏概率。
- 用户名规则使用小字符集、长度上限、lowercase 规范化和保留字，减少了路径注入、大小写碰撞和显示混淆风险。
- 明确不记录明文密码、不返回 password hash、前端不存密码，这些边界值得保留并转化为测试/日志审计项。

## 总体评价

该设计的安全基线是可接受的：argon2id、统一登录错误、PoW 一次性挑战、FDB 事务注册、证书模型复用都符合成熟认证系统的基本方向。因此我不建议推倒重做。但当前文本仍有几个会影响实现安全性的高风险空洞：challenge 绑定校验必须只信任服务端状态，challenge 申请接口必须有自己的 DoS 防线，登录抗爆破不能只依赖 IP 与 argon2id。建议在进入实现前把这些点写成明确合同和测试用例；完成后可按 CONDITIONAL_APPROVE 继续推进。