# R14 安全评审 — DSV4 Pro

> 评审员: DeepSeek V4 Pro (Security)
> 日期: 2026-06-18
> 模型视角: 协议一致性验证、数据流追踪、竞态条件检测

---

## 1. Verdict: CONDITIONAL_APPROVE

设计整体安全姿态良好，但发现 **1 个 Critical 文档矛盾**（localStorage vs HttpOnly Cookie 的相反指令）和 **若干个 Medium 级别风险点**需要修复后才能进入实现阶段。

---

## 2. 发现的问题

### Critical

#### S-C1: 浏览器凭证存储策略前后矛盾 — localStorage vs HttpOnly Cookie

**文件**: `design/auth.md`

**矛盾**:
- **§5.7 安全评审结论 (S-H1/S-H2)**: "浏览器端 token/certificate material **禁止存 localStorage**。使用 HttpOnly Secure cookie + WebCrypto non-extractable key 或 OS keychain。若必须存 localStorage，写入威胁模型并注明 XSS 风险"
- **§14.3 浏览器存储策略**: "使用 **localStorage** 存储 {refresh_token, certificate, client_public_key}"

这两处给出了**完全相反的指令**。§5.7 明确说禁止 localStorage，§14.3 说使用 localStorage。必须解决此矛盾，否则实现者将面临不确定性。安全评审结论 §5.7 的正确性毋庸置疑——XSS 可读取 localStorage，而 HttpOnly cookie 不可。应该以 §5.7 为准，修正 §14.3。

**建议修复**: 
1. 统一采用 HttpOnly Secure cookie + WebCrypto non-extractable key
2. 删除 §14.3 中 localStorage 的引用
3. 在威胁模型中明确标注「曾被考虑但拒绝」的 localStorage 方案

---

### High

#### S-H1: 证书吊销缓存延迟默认值偏高 — 60s 窗口内可部署恶意 WASM

**文件**: `specs/security/09-command-source.md` §3.4, `design/auth.md` §10.8

CRL 缓存延迟明确标注为 60s: "明确接受的风险：吊销后至多 60s 旧证书仍可被接受"。文档同时注明竞争性世界可配置为 5-10s——但**默认值应为更安全的值**。

攻击场景：CodeSigningCertificate 在 tick T 被吊销（key compromise），攻击者在 tick T+1 到 T+59 之间仍可通过证书缓存窗口部署恶意 WASM。对于 competitive world，60s = 至少 30+ tick（以 2s/tick 计），足以造成严重破坏。

**建议修复**:
1. 默认 CRL 缓存 TTL 从 60s 降为 **10s**
2. 非竞争性世界（coop/sandbox/tutorial）可放宽至 30-60s
3. 在 world.toml 中增加 `auth.crl_cache_ttl_seconds` 配置项，竞争性世界默认 10s

---

### Medium

#### S-M1: 浏览器 WebSocket 会话内消息无 per-tick rate limit

**文件**: `specs/security/03-mcp-security.md` §2.1, `design/auth.md` §10.5a

§10.5a 规定: "会话内消息不计入 per-tick rate limit（握手时已完成身份绑定）"。这意味着通过浏览器 WebSocket 可以以无限速率查询世界状态，而 MCP Query 有 50/tick 的显式限流。对于 competitive world，这形成了一个 throughput asymmetry，攻击者可通过 WebSocket 通道进行更高频率的信息刮取。

**建议修复**:
1. WebSocket 会话内消息同样应用 per-tick rate limit
2. 或者在 visibility.md §3.3 的 WebSocket delta 推送中明确只推送变更实体（已如此），但明确拒绝会话内的主动查询请求
3. 若 WebSocket 仅用于服务端推送（delta broadcast），应明确禁止客户端通过 WebSocket 发送查询消息

#### S-M2: MCP `swarm_get_replay` 无限流

**文件**: `specs/security/03-mcp-security.md` §4.3

`swarm_get_replay` 的限流标注为 "按需"（on-demand），没有明确的 per-tick 或 per-hour 上限。回放数据可包含大量历史 tick 的完整世界状态。攻击者可连续调用此接口进行大规模数据外泄。

**建议修复**:
1. 添加 `swarm_get_replay` 的显式限流: 1 次/分钟、单次最多 100 tick
2. 在 world.toml 中可配置

#### S-M3: MCP SDK 分隔符契约仅在 SDK 层强制执行 — 无服务端验证

**文件**: `specs/security/03-mcp-security.md` §6.3

Prompt 注入防御通过 "AI SDK 分隔符契约" 实现——即官方 SDK 负责在 system prompt 中用分隔符包裹游戏数据。但这仅是 SDK 约定，服务端不强校验。如果 AI agent 使用自定义 HTTP 客户端而非官方 SDK，分隔符不会被应用，`_untrusted_game_data` 标志虽然存在但无实际屏障效果。

**建议修复**:
1. 服务端在 `swarm_get_snapshot` 响应中包含 `X-Swarm-Data-Integrity: untrusted` header
2. 文档明确说明: 使用非官方 SDK/MCP 客户端的 AI agent 需自行实现 prompt 分隔符契约
3. 在威胁模型中标注"使用非官方 SDK 的 AI agent 面临 prompt 注入风险"

#### S-M4: Login PoW 默认难度过低

**文件**: `design/auth.md` §9.4, 附录 C

Login PoW 默认 `difficulty_bits = 16`，仅 ~65K 次尝试。即使 enabled=false（默认禁用），若被启用，16-bit PoW 对现代硬件微不足道（<1ms in Rust）。如果部署者启用 login PoW 但未调整难度，它无法提供实际保护。

**建议修复**:
1. Login PoW difficulty 默认至少 **20 bits**（~1M attempts）
2. 文档中强调 login PoW 难度应 ≥ register PoW 的 80%

---

### Low

#### S-L1: 非浏览器客户端缺失 Origin → 拒绝的设计可能过严

**文件**: `specs/security/03-mcp-security.md` §5.3

"非浏览器客户端拒绝缺失 Origin" — 但 §2.2 说 Agent/CLI "不依赖 Origin header"。这两处存在轻微矛盾。§5.3 的表述应限定为 "浏览器端点"，而非全局 HTTP 安全合同。

**建议修复**: §5.3 表中将 "非浏览器客户端拒绝缺失 Origin" 改为 "浏览器端点拒绝缺失 Origin；Agent 端点不校验 Origin"

#### S-L2: Path finding 无 per-call 节点展开上限

**文件**: `specs/core/04-wasm-sandbox.md` §8

`host_path_find` 的 per-tick 总预算是 100,000 explored_nodes + 10 calls，但单次调用无上限。恶意超大迷宫地图可使单次 path finding 耗尽全部 100,000 nodes 预算，导致玩家的其他 path find 调用全部确定性失败。

**建议修复**: 添加 per-call 上限 50,000 explored_nodes，超限返回 `PathTooComplex`

#### S-L3: 账号删除后资产处置的 "transfer" 模式签名时间戳窗口过长

**文件**: `design/auth.md` §13.4

Transfer 签名时间戳窗口为 5 分钟。对于高价值资产转移，5 分钟窗口足以被中间人拦截重放（在 HTTP 不安全传输场景下）。

**建议修复**: 缩短为 60 秒，并要求 nonce 去重

#### S-L4: 联邦 CRL 同步失败后的 `allow_with_warning` 策略风险未充分说明

**文件**: `design/auth.md` §15.2a

`revocation_fallback = "allow_with_warning"` 在文档中标注 "仅用于低风险世界"，但未定义 "低风险世界" 的判定标准。运营商可能误配置此模式于竞争性世界。

**建议修复**: 明确定义"低风险世界" = world.mode ∈ {tutorial, sandbox} 且 fog_of_war = false

---

## 3. 亮点

以下是设计中值得肯定的安全措施：

1. **Deferred Command Model** (`04-wasm-sandbox.md` §3): WASM 不能直接调用 mutating host function，所有游戏动作必须通过 tick() → JSON 返回，由引擎验证后统一执行。这是最坚固的沙箱边界设计。

2. **应用层证书 + 用户私钥签名** (`auth.md` §5): 不依赖 JWT/bearer token 作为信任根。JWT 仅是 Web 兼容层。所有敏感操作需要 Ed25519 签名 + 证书链验证。

3. **Fork-Exec-Kill 沙箱生命周期** (`04-wasm-sandbox.md` §1): 每 tick 新 fork → 执行 → kill，无跨 tick 状态保留。防止内存泄漏、长运行进程资源累积、受感染模块持久化。

4. **Unified Visibility with Oracle Defenses** (`05-visibility.md` §10): `is_visible_to()` 统一过滤所有输出面。`omitted_count` 分桶、dry_run/simulate 脱敏、特殊攻击拒绝码等价类——系统性闭合信息泄露。

5. **Server-Authoritative PoW Challenge** (`auth.md` §9.3): 客户端不传输 challenge/difficulty，服务端从 FDB 读取权威值。彻底消除 challenge 降级攻击面。

6. **Transport Splitting** (`03-mcp-security.md` §2): Browser 和 Agent 使用独立安全合同——Origin/CSRF vs application certificate。DNS rebinding 防御全面。

7. **Version Counter 防重放** (`09-command-source.md` §7.3): Deploy 使用 per-player/per-slot 单调递增 version_counter 防重放，不依赖可能丢失的 Dragonfly nonce。

8. **CVE SLA 体系** (`CVE-SLA.md`): Wasmtime CVE 按 CVSS 分级响应（Critical 24h / High 72h），含回滚策略和复盘要求。

9. **管理员恢复链接的双人授权** (`auth.md` §11.3): 敏感操作需两个不同 admin 在 5 分钟内确认，单 admin 无法独立完成。

10. **账号删除 Grace Period** (`auth.md` §13.2): 30 天可恢复，防止误操作和恶意删除。

---

## 4. CrossCheck — 需要跨方向检查

以下是我怀疑但超出安全方向范围的问题，需要其他方向的评审员验证：

- **CX1**: `is_visible_to()` 在 `snapshot_tick` 语义下的一致性——COLLECT 阶段开始的快照和 EXECUTE 阶段结束后的广播之间存在时间窗口（1 tick 延迟）。在极端情况下，玩家 A 在 COLLECT 时可见的实体可能在 EXECUTE 中被玩家 B 摧毁，但 A 的决策已基于可见假设提交。这是设计预期还是信息一致性问题？ → 建议 **Architect** 检查 snapshot semantics 的跨 tick 因果一致性

- **CX2**: MCP `swarm_explain_last_tick` 返回「被拒绝指令及原因」——若拒绝原因是 `TargetNotVisible`，攻击者可通过系统性地提交对不同坐标/目标的操作，根据拒绝原因推断隐藏实体的存在和位置（尽管 §05-visibility §10.4 已设计了等价类）。特殊攻击已处理，但普通 move/attack 等指令的拒绝码是否同样等价？ → 建议 **Architect** 检查所有命令拒绝码的 oracle 闭合（不仅是特殊攻击）

- **CX3**: fuel metering (10M/tick) + epoch interruption (2500ms 墙钟) 的双重限制下的边界行为——如果 WASM 模块在 2500ms 内消耗了 9.9M fuel 但未完成返回，是返回部分指令还是全部丢弃？当前文档说 "终止 tick，已执行命令不回滚，剩余 fuel 计为逾期"——但 WASM 返回的是 JSON 指令集，如果 JSON 未完整生成就被终止，解析会失败 → 建议 **Architect** 检查 tick() ABI 的超时语义，确保部分输出不会产生未定义行为

- **CX4**: AI agent 代理注册时，「一次性 handoff code / 导入链接」的安全性依赖于传输通道的机密性。若通过不安全的聊天平台（如明文 IRC）传递 handoff code，存在截获风险。是否有 handoff code 的额外绑定机制（如限定 IP、限定时间窗口 < 60s）？ → 建议 **Game Designer** 确认 agent 代理注册的用户体验流程中的威胁模型覆盖

- **CX5**: `swarm_simulate` 限制中 `max_fuel_per_hour = 50,000,000`——这相当于 5 次完整 tick 的 fuel 预算。对于 competitive world，高频 simulate 可能被用于对手策略建模（用 simulate 探索对手可能的行为空间）。文档已标注必须使用 `is_visible_to` 过滤（§05-visibility §10.3），但 simulate 的输入快照是当前玩家的可见范围——这本身是合理的，但需要确认 simulate 不会通过多次试错反推隐藏信息 → 建议 **Architect** 确认 simulate 的 oracle 闭合

---

*评审完成。准备提交 kanban_complete。*
