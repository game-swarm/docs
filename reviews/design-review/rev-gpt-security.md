# Swarm 设计评审 — rev-gpt-security

Reviewer: rev-gpt-security (Security Reviewer — GPT-5.5)
Scope: /data/swarm/docs/design/DESIGN.md, /data/swarm/docs/design/tech-choices.md, /data/swarm/docs/ROADMAP.md, /data/swarm/docs/specs/*.md
Focus: 已知漏洞模式匹配、API 滥用检测、供应链风险、DoS 向量
Date: 2026-06-15

## Verdict

CONDITIONAL_APPROVE

设计总体安全方向正确：MCP 不作为 gameplay 控制器、所有玩家通过 WASM、Source Gate 服务端注入身份、统一 Command Validation Pipeline、WASM 沙箱具备 fuel/epoch/cgroup/seccomp、多输出面统一可见性，这些都是强安全基线。

但在进入实现冻结/公开部署前，需要补齐若干高风险边界：RuleMod/Rhai 的能力边界与供应链治理、Admin/rollback 权限收敛、MCP/rmcp 已知 DNS rebinding 类漏洞的版本与部署约束、以及若干 DoS 放大路径。当前问题不要求推翻架构，但应作为上线前条件项处理。

## Findings

### High — RuleMod/Rhai 能力模型与“可信服主脚本”假设过宽，存在供应链 RCE/逻辑越权风险

位置/依据：
- DESIGN §8.7 将规则模组定义为“服主声明 → 引擎嵌入”，并允许 Rhai actions 修改世界规则。
- P0-7 §5.1 说 Rhai 不能直接写 ECS，只能通过 actions buffer。
- P0-7 §6.4 又允许 `actions.register_action_handler("MindControl", |...| { ... })`，并允许 `set_entity_flag`、`schedule_flag_removal` 等效果。
- P0-9 Source Gate 中 `RuleMod` 能力写成“仅经济 + 事件”，但 P0-7/DESIGN 实际允许 damage/effect/attribute/custom handler 等更广能力。

风险模式：
- 这接近“插件市场供应链漏洞”：服主安装的脚本虽然不是玩家不可信输入，但一旦有公开 mod market，就会出现 typosquatting、恶意更新、依赖投毒、评分刷量、被接管 maintainer 等攻击。
- `register_action_handler` 把 TOML 可配置动作升级为脚本定义的行为，等同于开放一个 DSL 执行层。若 capability 不细分，恶意或脆弱模组可绕过原本 Command Validation 的 gameplay 限制，制造经济通胀、隐藏信息泄露、永久控制锁、无限资源、跨玩家状态篡改。
- P0-9 与 P0-7 的能力描述不一致会导致实现者选错边界：有人会按“仅经济+事件”实现审计，有人会按“可注册 handler”实现实际能力。

建议：
1. 为 RuleMod 增加 manifest capability：`economy.deduct`、`economy.award`、`entity.damage`、`entity.flags`、`visibility.read`、`custom_action.register`、`market.modify` 等逐项授权，默认 deny。
2. Source Gate 的 `RuleMod` 行与 P0-7 保持一致：列出允许动作、禁止动作、每项预算和审计字段。
3. 模组市场要求签名、lockfile、immutable release、maintainer key rotation、依赖哈希 pinning、撤回/隔离机制。
4. custom handler 不应直接闭包注册任意逻辑；优先限定为内置 effect DSL，新增 handler 需 server operator 明确开启高危 capability。
5. TickTrace 记录每个 mod action 的 mod name/version/hash/capability、输入、结果、state checksum diff。

### High — Admin/rollback/API 管理面仍是典型滥用高风险区：全局可见 + 可写世界 + rate limit “无限制”

位置/依据：
- P0-9 Source 矩阵：`Admin` 允许写世界、读写全局存储、部署代码、查询全局、触发战斗，rate_limit 为“无限制”。
- P0-5 数据分级：Admin 可见全量 tick trace、其他玩家指令、world_seed、RNG 状态。
- Rollback 有双人签名，但 Admin 本身没有同等级别约束描述。

风险模式：
- 这是经典 mass assignment / confused deputy / overpowered admin API 问题。实现阶段只要某个 REST/MCP endpoint 忘记检查 world_id/scope，就会变成跨世界 IDOR 或任意实体修改。
- “无限制”会让被盗 admin token 成为最大 DoS 放大器，也会让内部脚本 bug 快速破坏所有世界。
- Admin 能读 world_seed/RNG 状态，若审计/导出接口暴露不当，会直接破坏竞技公平性。

建议：
1. Admin token 必须 world-scoped、operation-scoped、time-scoped；默认不能跨 world。
2. 高危写操作使用 two-person rule 或 break-glass：rollback、grant resource、force deploy、read world_seed、read hidden traces。
3. Admin 也必须限流；可设置较高阈值，但不能 unlimited。
4. 所有 admin endpoints 使用对象级授权：`subject.admin_scope contains world_id && operation && resource_type`。
5. 审计日志不可只进 ClickHouse 普通表；高危 admin action 应写 append-only/WORM 或签名链，防管理员事后篡改。

### Medium — rmcp/MCP HTTP transport 已知 DNS rebinding 类漏洞虽有意识覆盖，但缺少版本 pin 与验收测试

位置/依据：
- DESIGN 使用 `rmcp, HTTP/SSE`。
- P0-3 §5.3 要求 Host header 校验、CORS Origin 白名单、禁 JSON-RPC batch。
- 外部检索显示 rmcp Streamable HTTP server transport 曾有 Host header 未校验导致 DNS rebinding 的安全公告（GHSA-89vp-x53w-74fx，修复版本为 rmcp 1.4.0 及以后）。

风险模式：
- MCP 服务经常绑定 localhost/private network；DNS rebinding 允许恶意网页借受害者浏览器打到本机 MCP，触发已登录上下文中的工具调用。
- 文档写了 Host/CORS，但未强制 rmcp 版本、未说明校验发生在 auth/session 之前、未列出回归测试。

建议：
1. 明确 pin `rmcp >= 1.4.0`，并将该 CVE/GHSA 加入 CVE-SLA。
2. Host allowlist 校验必须在读取 session、解析 JSON body、执行 OAuth callback 之前。
3. 增加安全测试：恶意 Host、缺失 Origin、跨 Origin、DNS rebinding Host 切换、JSON-RPC batch、SSE reconnect。
4. 生产默认 MCP server 只监听 127.0.0.1，由 Gateway/nginx 做唯一入口；若允许外部 MCP，必须 mTLS + audience-bound token。

### Medium — DoS 放大：无认证/低成本开发辅助接口与模拟接口可能绕过 fuel 经济

位置/依据：
- P0-3 §4.4：`swarm_get_schema` / `swarm_get_docs` Scope 为“无”，限流为“无限制”。
- `swarm_simulate` 为 5/tick（World）/3/tick（Arena），P0-9 给 `Simulate` 预算为 0.5×MAX_FUEL。
- P0-4 中编译并发 5、模块 5MB、validation 10ms、compile 30s。

风险模式：
- docs/schema 常被低估，但如果内容包含完整 API、世界规则、多语言描述，可能成为未认证带宽/CPU 放大器。
- simulate 是高价值功能，但也是“最小请求触发大量服务端计算”的典型 DoS 入口。5/tick × 500 玩家 × 0.5 fuel 可能与真实 tick 执行竞争资源。
- validate_module/compile 独立预算合理，但需要全局队列、公平调度、按 player/IP/world 的隔离，否则攻击者可用多个账号占满编译槽。

建议：
1. docs/schema 也加 CDN/cache、ETag、per-IP limit、响应大小上限；不要 unlimited。
2. simulate/dry-run 使用独立 worker pool，与真实 tick worker 隔离；全局并发上限 + per-player token bucket。
3. simulate 只允许 snapshot-bound，快照大小、tick 数、实体数、输出大小全部上限化。
4. compile/validate 引入全局排队公平性：per-player/IP/world 并发=1，队列长度有限，超限快速失败。

### Medium — WASM 沙箱基线强，但 seccomp/进程模型仍需收敛几个实现细节

位置/依据：
- P0-4 使用 Wasmtime fuel、epoch interruption、64MB linear memory、128MB cgroup、seccomp whitelist。
- seccomp 允许 `clone (仅 CLONE_VM | CLONE_VFORK)`，pids.max=32，同时 Wasmtime 配置禁 wasm_threads。

风险模式：
- “禁 wasm_threads”与“允许 clone/pids 32”之间存在实现解释空间。Wasmtime/Cranelift/JIT/runtime 可能需要线程，但 sandbox 内允许 clone 会扩大攻击面。
- seccomp 列表没有提到 `clone3`、`io_uring_*`、`userfaultfd`、`perf_event_open`、`bpf`、`keyctl`、`ptrace` 等现代 Linux 高危 syscall 的明确拒绝测试。
- Per-tick fork/kill 安全性好，但若模块缓存/JIT code cache 在父进程或共享 worker 中，仍需保证不受玩家输入污染或跨玩家泄露。

建议：
1. 明确默认拒绝所有 syscall，只 allow 最小集合；测试覆盖 clone3/io_uring/userfaultfd/bpf/perf/ptrace/keyctl/openat/socket。
2. 若不需要线程，将 pids.max 收敛到更小；若 Wasmtime 需要线程，说明哪些线程、何时创建、是否在 seccomp 前创建。
3. JIT/module cache 按 `(module_hash, wasmtime_version, config_hash)` 隔离，且有大小/TTL/eviction。
4. 增加 sandbox escape regression suite，不只测 WASI，还测 Linux syscall 尝试。

### Medium — 配置类型系统存在确定性与校验不一致：float 与 fixed/u32 混用

位置/依据：
- DESIGN §8.8 Determinism Contract 禁 f64，要求整数 + fixed，Rhai 关闭浮点。
- P0-7 配置示例仍有 `decay_rate = 0.001`、`damage_multiplier = 1.0`、`default_resistance = 1.0`、`special_param = 0.5`，字段说明写 `float`。

风险模式：
- 如果实现者按 float 解析，跨平台/版本确定性与 replay checksum 会受影响。
- 如果实现者按 fixed 解析，文档示例会误导 mod 作者，并可能导致隐式四舍五入/精度错误。

建议：
1. 所有 TOML 浮点字段改为显式 fixed 编码，例如 `fixed<u32,4>`：`10000` 表示 1.0，`5000` 表示 0.5。
2. config validator 拒绝 TOML float 类型，而不是自动转换。
3. IDL/docs/codegen 同源生成这些字段的类型，避免 DESIGN/P0-7/P0-8 漂移。

### Low — MCP/ClickHouse 审计日志可能记录敏感参数或大对象

位置/依据：
- P0-3 §7 `mcp_audit` 记录 `parameters String`, `result String`。
- `swarm_deploy` 参数含 base64 wasm；OAuth/token/cert 流程中也有凭据上下文。

风险模式：
- 审计表若直接记录完整 parameters/result，可能存储 WASM 字节、证书、token、私有调试信息，形成二次泄露面。
- 大参数也会放大 ClickHouse 写入成本。

建议：
1. 对 audit 参数做结构化 redaction：token/cert/signature/wasm_bytes 只存 hash、size、module_id。
2. result 只存 status/error_code/latency/size；必要详情进入受控 trace store。
3. 对审计表设置 TTL、访问控制、字段级权限。

### Low — OAuth2/短期证书流程需补充 replay 与 token binding 细节

位置/依据：
- P0-3 §1.1 证书 24h，部署 WASM 时客户端用私钥签名 Blake3(WASM bytes)。
- P0-9 §3 证书过期/吊销，服务端覆盖 player_id。

风险模式：
- 仅签名 WASM bytes 不能区分 world_id、version_tag、部署时间、nonce；同一签名可能被重放到其他上下文，除非服务端额外绑定。
- “服务端生成临时密钥对”意味着私钥需要交给客户端，需说明传输与存储安全，否则 token 泄露等同私钥泄露。

建议：
1. 部署签名 payload 包含 `module_hash, player_id, world_id, audience, nonce, issued_at, expires_at, version_tag`。
2. nonce/jti 一次性使用或短窗口重放检测。
3. 对 browser/web 使用 WebCrypto non-exportable key 或 token binding；对 MCP/CLI 使用 mTLS 或 device-bound refresh token。

## Highlights

- 明确纠正了高危架构误区：MCP 不含 `swarm_move`/`swarm_attack` 等 gameplay tools，AI 与人类一样必须部署 WASM。这显著降低了 API 越权与公平性风险。
- CommandIntent 只允许 `sequence + action`，`player_id/source/tick/auth` 服务端注入；这是防止 mass assignment 与伪造身份的正确模式。
- Source Gate 把 WASM/MCP/Admin/Replay/TestHarness/Tutorial/RuleMod/Simulate/DryRun 等来源显式建模，方向正确。
- WASM 沙箱有多层防线：Wasmtime fuel、epoch interruption、内存/表/栈限制、WASI 默认全禁、独立进程、cgroup、seccomp、恶意样本 CI。
- 统一可见性策略 `is_visible_to` 覆盖 snapshot、MCP、WS、REST、replay，避免“调试接口泄露战争迷雾”的常见漏洞。
- Tick 原子性、FDB rollback 后恢复 Bevy World 快照、BROADCAST failure 不回滚 committed tick，这些故障语义对一致性和反作弊都很关键。
- P0-3 已显式纳入 Host header/CORS/batch 禁用，说明团队已意识到 MCP transport 的浏览器攻击面。
- AI snapshot 中玩家原创字符串标注 untrusted，并要求 SDK prompt 分隔符，这是少见但必要的 prompt-injection 防护。

## Conditional approval checklist

上线/实现冻结前建议至少完成：

1. 修订 P0-7/P0-9：RuleMod capability manifest + Source Gate 能力矩阵一致化。
2. 增加模组供应链策略：签名、hash pin、不可变 release、依赖锁、撤回机制。
3. 修订 Admin 权限：world/operation scoped、限流、two-person 高危操作、WORM/signature-chain audit。
4. 明确 rmcp 版本 `>=1.4.0`，加入 DNS rebinding 回归测试。
5. 给 docs/schema/simulate/dry-run/compile 增加全局与 per-principal 资源隔离。
6. 移除 TOML float，统一 fixed integer 表达并在 config validator 中拒绝 float。
7. 审计日志 redaction：不记录 wasm_bytes/token/cert/signature 原文。
