# R13 — rev-gpt-security 安全评审

Reviewer: rev-gpt-security (GPT-5.5)
Scope: `/data/swarm/docs/design/DESIGN.md`, `/data/swarm/docs/design/tech-choices.md`, `/data/swarm/docs/specs/p0/`
Focus: 已知漏洞模式、API 滥用、供应链风险、DoS 放大面、权限/可见性边界

## Verdict

REQUEST_MAJOR_CHANGES

总体方向比早期方案安全得多：MCP 不再作为 gameplay controller、唯一 gameplay 执行器是 `WasmSandboxExecutor`、统一可见性函数、Source Gate、WASM fuel/cgroup/seccomp、TickTrace 审计、JSON schema 边界、refund anti-amplification 都是正确的安全骨架。

但 Phase 0 文档仍有几处会直接影响实现安全性的规范冲突/缺口，尤其是：

1. P0-2 的 `RawCommand` 仍把 `player_id`/`tick` 放在 WASM 输出 JSON 内，与 P0-9 “auth context 服务端注入、客户端不可自报”冲突。
2. Wasmtime 模块校验示例没有真正检查 WASM start section，只检查 `_start` export，容易给实现者错误模板。
3. MCP/HTTP 资源类接口和 SSE 连接的 DoS 合同还不够完整，尤其是无限制 docs/schema、SSE 长连接、simulate/dry-run/validate 的成本模型。
4. 部署/签名/证书模型在文档间存在语义不一致：服务端生成临时 keypair、客户端私钥签名、JWT、mTLS、部署证书之间的信任边界不够清晰。
5. Rhai 规则模组作为“服主信任”层，但缺少脚本供应链、能力清单、op budget、审计/签名/版本锁定的 P0 级合同。

建议先修正文档合同再进入实现，否则很容易在实现阶段把“客户端自报字段”“debug 例外”“资源型只读接口不计成本”这些典型漏洞模式固化进 API。

---

## Critical

### C1. `RawCommand.player_id`/`tick` 客户端自报与服务端注入 auth model 冲突，容易导向 IDOR/source spoofing

位置：
- `specs/p0/02-command-validation-spec.md` §2 RawCommand 结构：示例包含 `player_id`, `tick`, `sequence`, `action`，并写明 `player_id` 必须匹配已认证玩家。
- `specs/p0/09-command-source-model.md` §1/§3：声明 `actor/capability/scope` 由服务端注入，客户端不可自报；禁止客户端在 Command body 中自报 `player_id`。
- `specs/p0/04-wasm-sandbox-baseline.md` §3：WASM `tick()` 返回 Command JSON。

问题：
P0-9 的原则是对的，但 P0-2 仍保留了早期“RawCommand 由客户端/WASM 提供 player_id/tick”的形状。实现者如果按 P0-2 生成 schema/SDK，很可能会：

- 允许 WASM 输出 `player_id`，再做“匹配已认证玩家”的普通校验；
- 在 MCP/REST/admin/test 入口复用同一 RawCommand schema；
- 后续某个入口漏掉匹配校验，形成典型 IDOR / mass-assignment / source spoofing；
- 让客户端影响 `tick` 或 `tick_target`，制造预提交、迟到指令、replay 差异或排序攻击。

这类漏洞在多入口系统中很常见：文档一边说“服务端注入”，另一边 schema 允许字段存在，最后某条路径会把“应忽略字段”变成“可覆盖字段”。

建议：
- 把 P0-2 的 WASM 输出类型改名为 `PlayerCommandEnvelope` 或 `CommandIntent`，只允许：`sequence`, `action`。
- `player_id`, `source`, `module_hash`, `cert_fingerprint`, `tick_submitted`, `tick_target` 全部由 Source Gate/Auth Verify 在服务端生成 `RawCommand`。
- JSON schema 对 WASM 输出显式 `additionalProperties: false`，并禁止 `player_id`, `auth`, `source`, `tick`, `module_hash` 等保留字段。
- P0-8 IDL 同步区分：`CommandIntent`（untrusted input） vs `RawCommand`（trusted server envelope） vs `ValidatedCommand`。
- 所有非 WASM 来源（Admin/TestHarness/Tutorial/RuleMod/Simulate）也必须通过 `SourceContext` 构造器注入，不允许 handler 手写 auth 字段。

---

## High

### H1. Wasmtime start section 校验写法错误；检查 `_start` export 不能阻止实例化时 start 执行

位置：`specs/p0/04-wasm-sandbox-baseline.md` §2.4 模块校验。

问题：
示例代码：

```rust
if module.export("_start").is_some() { ... }
if module.export("__wasm_call_ctors").is_some() { ... }
```

这不能等价于“无 start 函数”。WASM 的 start section 不是 `_start` export；模块可以声明 start section，在实例化时自动执行。若实现者照此模板，只检查 export 名称，则恶意模块仍可能在 instantiation 阶段执行初始化代码。

影响：
- fuel/epoch 是否已经正确设置取决于实例化流程，容易出现初始化阶段绕过或成本归属不清。
- start 中可执行大量计算、内存增长、host import 调用尝试，形成部署/执行 DoS。
- 即便 mutating host function 不暴露，query host function/内存写出/错误路径也可能扩大攻击面。

建议：
- 使用 `wasmparser` 在预校验阶段显式拒绝 `Payload::StartSection`。
- 明确禁止所有初始化副作用：start section、WASI `_initialize`、不在白名单内的 ctor-like export/import。
- 规范实例化顺序：Store fuel、epoch deadline、memory limiter、host call limiter 必须在 `Instance::new` 前生效。
- 恶意样本库加入：含 start section 但无 `_start` export 的模块；含 `_initialize`；含 active element/data + start 的组合。

### H2. `swarm_get_docs` / `swarm_get_schema` 无 scope、无限流，是低成本高放大的 DoS 与 prompt-injection 分发面

位置：`specs/p0/03-mcp-security-contract.md` §4.4、§5。

问题：
文档写：
- `swarm_get_schema`: Scope 无，限流无限制。
- `swarm_get_docs`: Scope 无，限流无限制。
- 每玩家开发辅助工具 20/tick，但这两个表项又写“无限制”。

这会形成非常典型的“只读接口 DoS”：攻击者不需要账号或只需匿名即可反复请求大文档/API schema/tutorial，造成：

- CPU/序列化/压缩/带宽放大；
- MCP resource 枚举；
- 对 AI agent 的 prompt-injection payload 分发与缓存污染；
- gateway/cache 层热点 key 打爆。

建议：
- 即使公开 docs/schema，也必须有 IP 级、连接级、token 级限流和响应大小上限。
- docs/schema 静态化、强缓存、ETag、预压缩；MCP handler 不应每次动态生成全量 schema。
- 区分 public docs 与 world-specific docs：`swarm_get_world_rules` 已需要 `swarm:read`，任何包含当前世界模组/配置/版本的信息都不应匿名。
- 对 MCP resource 返回增加 `max_bytes`, pagination, `If-None-Match`/content hash。
- AI SDK 中把 docs 与 game data 一样视为 untrusted content；模组提供的 i18n/description 必须标注来源并做长度/字符集限制。

### H3. `swarm_simulate` / `swarm_dry_run_commands` / `swarm_validate_module` 的成本模型不足，存在计算放大

位置：
- `specs/p0/03-mcp-security-contract.md` §4.4：`swarm_simulate` 5/tick。
- `specs/p0/06-mvp-feedback-loop.md` §3.1：`swarm_dry_run_commands`。
- `specs/p0/04-wasm-sandbox-baseline.md` §7：编译预算、module validation 10ms。
- `specs/p0/09-command-source-model.md`：Simulate budget 0.5× MAX_FUEL。

问题：
这些接口是最容易被滥用的“最小请求触发最大服务端开销”：

- `swarm_simulate` 如果可预测未来 N tick，5/tick 仍可能远超真实 tick 成本。
- `dry_run_commands` 若允许提交复杂命令、路径查找、冲突模拟，会复制执行管线成本。
- `validate_module` 涉及 wasm parse/compile/wasmtime validation，10/h 仍可用多账号/IP 放大；且文档同时写 `Module::from_binary` 和 `wasmparser 10ms`，编译/解析边界不清。
- Base64 WASM 走 JSON-RPC，5MB body 上限与 5MB raw module 上限冲突：base64 后约 6.7MB，容易导致实现者临时放宽 body size，扩大 DoS 面。

建议：
- `simulate` 必须显式限制 `ticks`, `entities`, `commands`, `snapshot_size`，并进入独立队列/cgroup；默认不与主 tick 线程池共享。
- `dry_run_commands` 只接受当前 snapshot hash 绑定的 CommandIntent，最多 N 条，禁止递归模拟未来 tick。
- `validate_module` 分两阶段：cheap wasmparser preflight（体积/import/start section）与昂贵 compile；昂贵 compile 走 per-player + per-IP + global concurrency + proof-of-work/队列。
- 上传协议改为二进制 multipart 或明确 `max_json_body >= ceil(max_wasm_bytes*4/3)+overhead`，不要让实现者自行猜。
- 所有开发辅助接口写入审计和滥用指标，连续失败/高成本触发 cooling period。

### H4. 认证/签名/mTLS/JWT/证书模型语义混杂，信任边界容易实现错

位置：
- `specs/p0/03-mcp-security-contract.md` §1.1、§2、§3。
- `specs/p0/09-command-source-model.md` §3。
- `design/tech-choices.md` §8/§9。

问题：
文档同时出现：
- HTTPS + mTLS，由 nginx/gateway 验证；
- JWT access token，900 秒过期；
- 服务端签发“短期证书”，24h 过期；
- 证书内容包含 `public_key`，但写“服务端生成临时密钥对”；
- 部署 WASM 时客户端附带证书 + 私钥签名 Blake3(WASM bytes)；
- tech-choices 又把 Blake3 MAC 放在“签名”表里，Ed25519 用于证书签发。

风险：
- 如果服务端生成私钥再发给客户端，需要定义私钥传输/存储/撤销/重放防护，否则等价于 bearer secret，不能获得强不可抵赖性。
- 如果实际是客户端生成 keypair，文档“服务端生成”会误导实现。
- mTLS 与 JWT 的 audience/binding 不清：token 是否绑定 client cert fingerprint？nginx 终止后如何把验证结果安全传给 MCP server？哪些 header 不可由外部伪造？
- Blake3 MAC 是对称 MAC，不是签名。若用于“代码签名”措辞，容易导致密钥分发错误。

建议：
- 统一术语：
  - OAuth2 session → JWT access token；
  - client-generated Ed25519 keypair → server-signed short-lived certificate；
  - deploy signature = Ed25519 private key over domain-separated payload；
  - module hash = BLAKE3(bytes)，不是签名。
- 如果坚持服务端生成 keypair，则明确它只是短期 bearer deploy credential，不提供不可抵赖性；并要求只通过 mTLS channel 下发、客户端本地加密存储。
- gateway 到 MCP server 使用 Unix socket 或 mTLS；若用 header 传递身份，必须先清除所有外部同名 header，再注入 `X-Swarm-Verified-*`，并在内层只信任来自 gateway 的连接。
- 签名 payload 加 domain separation：`SWARM_DEPLOY_V1 || player_id || world_id || module_hash || abi_version || expires_at || nonce`。
- 部署签名必须防 replay：nonce/jti、过期时间、world_id/audience、module_hash 绑定。

### H5. Rhai 规则模组缺少供应链与能力合同；“服主信任”不足以保护玩家和共享世界

位置：
- `design/tech-choices.md` §3。
- `specs/p0/07-world-rules-engine.md`。
- `specs/p0/09-command-source-model.md` RuleMod 行。

问题：
Rhai 被定位为中间信任层：“服主声明 → 引擎嵌入”。但 P0 文档还没有定义：

- 模组包来源、签名、版本锁定、依赖锁定；
- 模组能调用哪些 host API / action；
- Rhai op budget / memory budget / recursion limit / AST size；
- 模组 action 是否经过与玩家 command 同等的审计与 replay 记录；
- 模组配置的 schema、迁移、默认值安全；
- 恶意/失误模组对经济、visibility、global storage、refund、replay 的影响边界。

“服主信任”只适用于私服；一旦存在公共世界、托管世界、Arena 或第三方模组市场，模组就是供应链入口。历史上游戏服务器插件/脚本生态经常成为 RCE、经济破坏、权限提升和数据泄露入口。

建议：
- Phase 0 至少冻结 RuleMod capability model：每个模组 manifest 声明能力，如 `economy.award`, `economy.deduct`, `event.emit`, `visibility.none`。
- 所有 RuleMod action 进入 `RuleActionIntent -> Source Gate -> Validator -> AppliedAction`，不得直接改 Bevy component。
- Rhai engine 关闭/限制：eval、模块导入、文件/网络、浮点、随机、无限循环；设置 max operations、max call depth、max string/array/map size。
- 模组包使用签名与 lockfile：`mod_name`, `version`, `source`, `hash`, `signature`, `engine_api_version`。
- Replay 必须记录模组版本/hash/config 与每 tick 产出的 RuleMod actions，否则无法审计经济异常。

### H6. 可见性策略总体正确，但 `player_view = full` 允许 MCP 全图只读查询，和“AI 与 WASM 同屏幕”原则冲突

位置：`specs/p0/05-unified-visibility-policy.md` §3.5。

问题：
文档写关键不变量：WASM `tick()` snapshot 始终按 `is_visible_to(player)` 过滤；但 `player_view = "full"` 时“玩家屏幕 / MCP”为全地图。此前 P0-3 又强调 MCP 和 Web UI 等量，不更多不更少，是 AI 的屏幕和鼠标。

这会产生安全/公平歧义：

- AI agent 可通过 MCP 全图只读查询获得 WASM 无法获得的信息，再生成下一版 WASM 策略，形成 out-of-band intelligence。
- 人类如果 Web UI full map 也能看到全图，同样会把信息写进代码；这改变了游戏模式，应被显式视为 no-fog/observer mode，而不是普通 World fog-of-war。
- `player_view` 只影响“屏幕”，但在编程竞技游戏里屏幕信息就是策略输入。

建议：
- 对普通 World 模式：MCP/Web player view 不得超过 WASM snapshot；`player_view=full` 只允许本地 sim、tutorial、admin、spectator delayed view。
- 若某世界允许 full player view，应在 world rules 中声明 `fog_of_war=false` 或 `out_of_band_intel=true`，并让所有玩家等同获知。
- MCP response 标注 `view_mode` 与 `fairness_class`，避免 agent 误把 spectator/admin 数据用于生产策略。

---

## Medium

### M1. seccomp 白名单包含 `clone(CLONE_VM | CLONE_VFORK)` 与 “wasm_threads(false)” 目标不一致

位置：`specs/p0/04-wasm-sandbox-baseline.md` §4.1。

问题：
WASM threads 已禁用，sandbox worker 生命周期为每 tick fork/kill，但 seccomp 仍允许部分 `clone`。这扩大了内核攻击面和资源模型复杂度。即使 cgroup `pids.max=32`，攻击者诱导 runtime/host path 产生额外线程也可能造成抖动。

建议：
- 明确允许 clone 的原因：Wasmtime/Cranelift/async runtime 是否确实需要。
- 执行阶段和编译阶段使用不同 seccomp profile；执行玩家 WASM 的 profile 尽量禁止 clone。
- 若必须允许，限制 flags 并加入恶意样本测试：线程/clone 尝试、futex storm、pid exhaustion。

### M2. `Host header` / `Origin` 合同对非浏览器客户端过严但对 MCP 客户端身份绑定不足

位置：`specs/p0/03-mcp-security-contract.md` §5.3。

问题：
表中写“非浏览器客户端拒绝缺失 Origin”。MCP agent、CLI、server-to-server client 通常没有浏览器 Origin；强行要求 Origin 容易导致实现者放宽为 `*` 或伪造固定 Origin。Origin 只能作为浏览器 CSRF/DNS rebinding 辅助信号，不是 API client 身份。

建议：
- 浏览器路径：校验 Origin + SameSite/CSRF。
- 非浏览器 MCP/API 路径：要求 Authorization/mTLS，不要求 Origin；若有 Origin 则校验白名单。
- Host header 防 DNS rebinding 保留，但要结合 TLS SNI、gateway allowlist。

### M3. `Admin` 来源 rate_limit “无限制”不安全

位置：`specs/p0/09-command-source-model.md` §2.1。

问题：
Admin 是最高权限来源，但不限流会让被盗 admin token 或脚本 bug 造成最大破坏/DoS。高权限接口更需要速率、审批和审计。

建议：
- admin read/write 分级限流；危险操作（rollback、global trace dump、ban、world config change）单独 budget。
- break-glass 流程：默认有限流，紧急模式需要二次确认/双人签名/短时令牌。
- admin bulk export 使用异步 job，不在请求线程直接 dump。

### M4. Tick 排序使用 `XOF.read_u64() % (N - i)` 有 modulo bias；安全性不致命但可修正

位置：`specs/p0/01-tick-protocol-spec.md` §3.1。

问题：
`u64 % bound` 有微小 modulo bias。对公平性长期统计通常可忽略，但这是竞技系统，最好避免留下争议。

建议：
- 使用 rejection sampling 生成 `[0, bound)`。
- 把 shuffle 算法写成规范测试向量，跨语言/版本固定。

### M5. Pathfinding cache key 在 P0-2 与 P0-4 不一致，可能导致可见性泄露实现偏差

位置：
- `specs/p0/02-command-validation-spec.md` §4.3：缓存 key `(from, to, 地形hash)`。
- `specs/p0/04-wasm-sandbox-baseline.md` §8：缓存 key `(from, to, terrain_hash, player_visibility_fingerprint)`。

问题：
P0-4 的 key 是安全版本；P0-2 的简化 key 如果被实现，会跨玩家复用路径结果，泄露隐形阻挡/可见地形或产生不公平路径建议。

建议：
- 全文统一为包含 `player_visibility_fingerprint`、world/rules version、movement policy 的 cache key。
- 安全测试：玩家 A 可见障碍、玩家 B 不可见时，不得通过 path_find cache 互相影响。

### M6. ClickHouse 审计表存 `parameters String` / `result String`，缺少脱敏与体积限制

位置：`specs/p0/03-mcp-security-contract.md` §7。

问题：
MCP audit 记录 parameters/result 原文，可能包含 base64 WASM、token-like 字符串、玩家私有策略信息、prompt payload。ClickHouse 不是秘密存储；90 天不可修改保留会放大泄露影响。

建议：
- 审计记录结构化字段，默认不存完整 wasm bytes/result；存 hash、size、schema version、rejection reason。
- 对 debug/result 设置 max audit bytes，超出截断并标注。
- token/cert/signature/header 永不入库；敏感字段 redact。
- 管理查询审计日志本身也需要权限和审计。

### M7. `get_objects_in_range`/`inspect_entity` 的 object id 枚举防护还需更明确

位置：`specs/p0/03-mcp-security-contract.md` §4.2/§4.3，`specs/p0/05-unified-visibility-policy.md` §3.2。

问题：
可见性过滤是正确的，但还应明确：对不可见 object id，响应应与不存在对象不可区分，否则可通过 `inspect_entity(id)` 枚举全局 ID 空间获得对象存在性、活跃度或增长速率。

建议：
- 不可见与不存在统一返回 `NotFound`，审计内部可区分。
- object id 使用不可预测 ID 或至少不把顺序 ID 的分配速率暴露给非 owner。
- 对 inspect_entity miss 高比例触发枚举检测。

---

## Informational

### I1. 设计中已有多项值得保留的安全正向约束

- MCP 不提供 `swarm_move`/`swarm_attack` 等 gameplay action，避免 AI 特权通道。
- `WasmSandboxExecutor` 唯一执行器，AI 与人类共享 fuel metering。
- P0-5 “所有输出面调用同一 `is_visible_to`”是防信息泄露的正确抽象。
- P0-9 Source Gate 明确 MCP_Deploy/MCP_Query 不可提交 gameplay 指令。
- P0-2 JSON schema 限制：max 256KB、max 100 commands、depth ≤ 10、additionalProperties false。
- Refund credit 绑定 module_hash，避免 v1 刷 refund → v2 消费。
- 回放记录 Command[] 而非重跑 WASM，规避 Wasmtime 升级后 replay 不稳定。

### I2. 供应链基线建议补成 checklist

建议在 tech-choices 或单独 P0 spec 加一节 `Supply Chain Baseline`：

- Rust: `Cargo.lock` committed, `cargo audit`, `cargo deny`, license allowlist, duplicate crate check。
- Wasmtime/rmcp/Bevy/Rhai：版本锁定策略、CVE SLA、升级演练。
- Docker/CI: pinned image digest, minimal runtime image, SBOM。
- Frontend SDK: npm lockfile, provenance/signature if发布包。
- Mod packages: manifest + signature + hash lock。

### I3. rmcp 依赖需要单独风险跟踪

MCP/rmcp 生态仍较新，攻击面包含 JSON-RPC parsing、SSE lifecycle、tool schema generation、resource enumeration、prompt-injection content boundary。建议：

- rmcp 封装在 adapter crate，不让业务逻辑直接依赖其 request context。
- 禁用 JSON-RPC batch 已写入，保留。
- 加 fuzz/property tests：畸形 JSON-RPC、超大 params、断线重连、SSE 慢客户端、重复 request id。

### I4. Bevy 确定性仍需实现层约束

`.chain()` 只能保证系统顺序，不自动保证 Query 迭代顺序、HashMap 顺序、浮点一致性、并行 scheduler 后续改动安全。建议在 Determinism Contract 中补：

- 禁用或封装 nondeterministic HashMap；使用 IndexMap/BTreeMap 或排序。
- Query 结果涉及竞争时显式 sort by stable EntityId。
- 禁用浮点或用 fixed point。
- 每个 release 跑 replay determinism corpus。

---

## 建议修复优先级

1. 立即修 C1：重写 P0-2/P0-8 的 Command 类型边界，禁止客户端自报 auth/player/tick 字段。
2. 立即修 H1：WASM start section 校验与实例化前 fuel/epoch/limiter 顺序。
3. 补 MCP DoS 合同：docs/schema/simulate/dry-run/validate/SSE 的统一成本与限流模型。
4. 统一认证/签名文档：JWT、mTLS、短期证书、Ed25519 deploy signature、BLAKE3 hash 的角色分离。
5. 给 Rhai RuleMod 增加 manifest/capability/op budget/signed lockfile/audit/replay 合同。
6. 统一 path_find cache key 与可见性策略；明确 object id 不可见响应语义。

