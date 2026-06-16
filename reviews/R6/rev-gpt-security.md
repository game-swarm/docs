# R6 安全设计评审 — rev-gpt-security

## Verdict

CONDITIONAL_APPROVE

当前 R6 文档相比前轮已经具备较强安全基线：MCP 不再是 gameplay 控制器，WASM 是唯一玩家执行器，部署链有证书/nonce/签名，命令模型拒绝客户端自报身份，WASM/Rhai/MCP/Visibility 都有明确隔离合同。因此不建议阻塞整体进入实现。

但仍有几处高风险合同冲突必须在实现前修正，否则不同实现者会按不同文档落地，形成可见性绕过、网关 transport 混淆或 sandbox 边界误配。

## Critical

无。

## High

### High — MCP 可见性合同与 `player_view=full` 存在跨文档冲突

位置：
- `specs/security/03-mcp-security.md:37` — MCP 信息量与 Web UI 等量，不更多不更少
- `specs/security/05-visibility.md:134` — `player_view` 影响人类屏幕和 MCP 只读查询
- `design/gameplay.md:951` — `player_view="full"` 时 AI MCP 实时看到全地图
- `specs/security/05-visibility.md:316` — `fog_of_war=false` 时 drone snapshot 包含全地图

问题：
MCP 安全规范把 MCP 定义为“Web UI 同级屏幕”，但 visibility/gameplay 又允许 `player_view="full"` 让 AI MCP 实时查询全地图，同时 `fog_of_war=true` 时 WASM `tick()` 仍只拿局部 snapshot。这会形成一个典型 visibility oracle：AI agent 可通过 MCP 读取全图，再把全图情报编码进下一版 WASM 策略或部署参数，间接绕过 `tick()` snapshot 的 fog-of-war。文档虽说 `player_view` 只影响只读查询，但对 AI 来说“只读”本身就是策略输入。

修正建议：
- 将 `player_view="full"` 明确限定为 human Web UI / spectator UX，不适用于 AI MCP agent；或
- 若 MCP 也允许 full view，则必须声明该世界为 non-competitive / tutorial / cooperative，关闭排行榜、PvP 或任何公平性承诺；
- 在 `specs/security/05-visibility.md` 增加硬不变量：competitive World 中 MCP `swarm_get_snapshot`、`swarm_get_objects_in_range`、`swarm_inspect_*` 的上限不得超过 WASM `tick()` snapshot 可见范围。

### High — Gateway transport 认证合同不一致，可能导致跨协议校验缺口

位置：
- `specs/security/03-mcp-security.md:88` — Browser 端点要求 Origin/Host/CSRF/Fetch Metadata
- `specs/security/03-mcp-security.md:114` — Agent 端点必须使用 mTLS 或 Ed25519 signed request
- `specs/security/09-command-source.md:184` — JWT `aud` 绑定 transport
- `specs/12-gateway-protocol.md:21` — Agent 认证方式只列 JWT (`mcp` audience) + `X-Swarm-Transport: mcp`
- `specs/12-gateway-protocol.md:28` — 缺少 transport header 拒绝

问题：
安全规范要求 Agent/CLI endpoint 必须使用 mTLS 或 Ed25519 signed request，且拒绝 browser-style header；Gateway 汇总协议却把 Agent 认证降级描述为 JWT audience + header，未包含 mTLS/signed request、Origin/CSRF 拒绝规则，也未说明同端口 8082 上 Browser/REST/Agent 的路由隔离优先级。实现者如果只按 Gateway 协议开发，会把 `X-Swarm-Transport` 这个可伪造 header 当成主要分流依据，复现跨协议混淆类攻击：浏览器/脚本伪装为 MCP transport，绕过 Browser 端点的 CSRF/Origin 防线。

修正建议：
- 在 `specs/12-gateway-protocol.md` 的 Agent 认证方式中加入“JWT audience + mTLS 或 Ed25519 signed request”，并声明 `X-Swarm-Transport` 只用于声明 intent，不是信任根；
- 明确 Gateway 判定顺序：TLS/client cert 或 request signature 校验 → JWT `aud` 校验 → transport header 一致性 → browser Origin/CSRF/Fetch Metadata；
- 明确 Agent endpoint 收到 `Origin`/CSRF/browser Fetch Metadata 时拒绝，Browser endpoint 收到 mcp audience 或缺少 Origin 时拒绝。

### High — Sandbox OS 隔离合同存在互相矛盾的 syscall/namespace 描述

位置：
- `specs/core/04-wasm-sandbox.md:21` — sandbox worker 使用 seccomp/cgroup/无网络/只读 rootfs
- `specs/core/04-wasm-sandbox.md:240` — seccomp 允许 `clone (仅 CLONE_VM | CLONE_VFORK)`
- `specs/core/04-wasm-sandbox.md:245` — 同一段又标注禁止 `fork, execve`
- `specs/core/04-wasm-sandbox.md:261` — sandbox 进程“无网络命名空间”
- `specs/core/04-wasm-sandbox.md:375` — checklist 又要求 `fork/vfork/clone` 全禁
- `specs/core/04-wasm-sandbox.md:395` — checklist 要求独立 net namespace 且无网络接口

问题：
沙箱边界文档在两处给出冲突合同：前半段允许受限 `clone`，后半段 checklist 全禁 `clone/fork/vfork`；前半段说“无网络命名空间”，后半段说“独立网络栈”。这是实现安全边界时的高风险歧义。历史上 WASM runtime escape/DoS 防护经常依赖正确的 seccomp + namespace 配置；如果实现者按较宽松版本执行，可能留下线程/进程创建、网络栈或 fd 继承攻击面。

修正建议：
- 统一为一个权威 checklist：生产 sandbox 是否允许 `clone`，若允许，必须列出精确 flags、调用方、验证测试；若不允许，删除前文允许项；
- 将“无网络命名空间”改成明确语义：是“独立 net namespace 且无接口”，还是“不创建 net namespace 但禁止 socket”；建议采用独立 net namespace + socket syscall 禁止双保险；
- CI 增加可执行断言：禁止 syscall 返回 EPERM、网络 socket 失败、PID namespace 内 fork 失败、fd 继承不可访问。

## Medium

### Medium — Replay / spectator 延迟默认值在 design 与 security 规范不一致

位置：
- `specs/security/05-visibility.md:136` — public spectator 全地图但受 `spectate_delay` 控制
- `specs/security/05-visibility.md:138` — World 模式 public_spectate=true 时 delay 必须 ≥50 tick
- `specs/security/05-visibility.md:162` — Arena 全知公开回放赛后延迟 ≥100 tick
- `design/gameplay.md:953` — `spectate_delay` 默认 0，0 表示实时
- `design/gameplay.md:997` — 示例 World 配置 `spectate_delay = 0`

问题：
安全规范要求 World 公开旁观至少 50 tick 延迟、Arena 赛后公开回放至少 100 tick；gameplay 文档把 `spectate_delay=0` 作为默认并描述为实时。虽然示例中 `public_spectate=false`，但默认值会被实现者复制到开启旁观的世界，造成实时全图旁观侧信道。

修正建议：
- 在 design/gameplay 中把 `spectate_delay` 默认改为 50 或声明“仅当 `public_spectate=false` 时可为 0；开启时 validate_config 强制提升/拒绝”；
- 将 Arena 的 spectator/replay 延迟默认单独列出，避免被 World 默认覆盖。

### Medium — `swarm_dry_run_commands` 在 interface/reference 中出现，但预算与语义未完全进入 MCP 安全表

位置：
- `design/interface.md:31` — MCP 调试工具包含 `swarm_dry_run_commands`
- `specs/reference/mcp-tools.md:35` — reference 也列出 `swarm_dry_run_commands`
- `specs/security/03-mcp-security.md:236` — 开发辅助表没有 dry-run，只列 validate/schema/docs/world_rules/available_actions/simulate
- `specs/core/01-tick-protocol.md:739` — Simulate/Dry-Run 有独立预算

问题：
Dry-run 是典型 DoS 放大入口：一个小 JSON 可以触发大量 command validation、路径检查、可见性检查和冲突解析。核心 tick 协议给了预算池，但 MCP 安全表没有列出该工具的 scope、限流、输出大小、是否 snapshot-bound、是否进入审计。实现者若按 MCP 安全文档生成工具表，可能遗漏 dry-run 限流。

修正建议：
- 在 `specs/security/03-mcp-security.md` §4.4/§5 加入 `swarm_dry_run_commands`，明确 `swarm:debug` 或 `swarm:read` scope、20/h 或 50/tick 限流、`max_commands`、`max_output_bytes`、snapshot_id 绑定和审计字段；
- 与 `specs/core/01-tick-protocol.md` 的 DryRun 预算保持同名同值。

### Medium — 供应链 SLA 主要覆盖 Wasmtime，rmcp / Bevy / Rhai / NATS 等关键依赖未纳入同等安全响应

位置：
- `specs/security/CVE-SLA.md:1` — 标题和适用范围聚焦 Wasmtime
- `specs/security/CVE-SLA.md:23` — 监控来源覆盖 RustSec/CVE，但响应目标仍以 Wasmtime 为中心
- `design/tech-choices.md`（技术栈选择域，整体属于 R6 范围）

问题：
Wasmtime 是最大风险点，但 Gateway/MCP/NATS/Bevy/Rhai 也在攻击面上：rmcp 影响 JSON-RPC/SSE parsing 与 request lifecycle，Bevy ECS 影响 schedule/unsafe ECS assumptions，Rhai 影响 in-process 脚本执行，NATS 影响 delta fanout 与 auth。只定义 Wasmtime SLA 会让其他安全公告没有同等时限和 owner。

修正建议：
- 将 `CVE-SLA.md` 扩展为 “Runtime and Protocol Dependencies CVE SLA”，至少列出 wasmtime/wasmtime-wasi/wasmparser/rhai/rmcp/bevy/nats/axum 或 gateway HTTP 栈；
- 对每类依赖给出是否允许临时禁用功能、升级验证测试、回滚策略；
- 对 MCP/HTTP 栈增加 request smuggling、SSE reconnect、JSON-RPC parser、batch 禁用回归测试。

## Informational

### Informational — 多个关键安全合同值得保留

- `specs/security/09-command-source.md:79` 将 deploy payload 加入 domain separator、module_hash、world_id、slot、nonce 和 expires_at，能有效防跨协议/跨世界重放。
- `specs/core/02-command-validation.md:81` 明确 CommandIntent 只允许 `sequence + action`，并拒绝 `player_id/source/tick/auth`，这是防 mass assignment 的正确方向。
- `specs/core/04-wasm-sandbox.md:117` 预校验 StartSection、import whitelist、export ABI、返回 JSON 大小，覆盖了常见 WASM 初始化绕过与输出放大。
- `specs/core/07-world-rules.md:373` 之后给 Rhai 模组签名、白名单、CRL、epoch 和无 unsigned 宽松模式，显著降低规则模组供应链风险。
- `specs/security/05-visibility.md:256` 对特殊攻击返回码 oracle 做了通用不变量约束，方向正确。
