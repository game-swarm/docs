# R8 终审 — rev-gpt-security

Reviewer: rev-gpt-security (GPT-5.5)
Scope: `/data/swarm/docs/design/DESIGN.md`, `/data/swarm/docs/design/tech-choices.md`, `/data/swarm/docs/specs/p0/*.md`
Perspective: 已知漏洞模式匹配、API 滥用、供应链风险、DoS/沙箱逃逸风险

## Verdict

REQUEST_MAJOR_CHANGES

R8 已经显著收敛：MCP 不再是 gameplay channel，WASM 是唯一玩家执行路径，Command Source Model、可见性策略、WASM sandbox baseline、IDL 单一真相都已补齐。整体方向正确，且比 R1–R7 的典型架构风险低很多。

但安全终审仍不建议直接进入实现冻结，原因是仍存在 4 个 High 级别问题：

1. rmcp / MCP HTTP/SSE 暴露面缺少版本与 DNS rebinding / Origin / Host 强制合同。
2. Wasmtime 固定为 `=30.0` 但没有安全支持窗口与升级 SLA，按 2026 当前 CVE 历史看风险不可接受。
3. `RawCommand.player_id` 与 P0-9 “客户端不可自报 player_id” 冲突，容易在 IDL/codegen 中生成可伪造身份字段。
4. Tick 持久化阶段在 P0-1 状态机与正文/DESIGN 之间仍不一致，可能导致实现者把 FDB commit 放到 BROADCAST。

这些不是理念性推翻，而是安全合同层面的冻结前修补项。修完后可降为 APPROVE_WITH_RESERVATIONS。

---

## Critical

无 Critical。

我没有发现“AI 通过 MCP 直接控制 drone”、“mutating host function 绕过指令校验”、“不同玩家执行器导致公平性破坏”这类足以推翻设计的 Critical 问题。P0 文档已经明确：

- 唯一 gameplay 执行器是 `WasmSandboxExecutor`。
- MCP 只做 deploy/query/debug，不做 move/attack/build。
- WASM host functions 只读，mutating 操作走 `tick() -> Command[] -> Validator`。
- Source Gate 默认只允许 `WASM` 提交 gameplay 指令。

---

## High

### H1 — rmcp / Streamable HTTP MCP 缺少版本与 DNS rebinding 防护合同

Severity: High
Affected docs:
- DESIGN.md §2.1 / §4：`MCP Server (rmcp, HTTP/SSE)`、MCP 作为 AI 操作界面
- P0-3 §2：MCP Server 默认绑定 127.0.0.1，经 nginx/网关进入
- tech-choices.md：未列出 rmcp 版本与安全策略

Problem:
设计写了 `rmcp, HTTP/SSE`，但没有冻结 rmcp 版本，也没有把 Host / Origin / DNS rebinding 防护写成 P0 合同。这个漏洞模式已经不是理论风险：rmcp 的 Streamable HTTP server 曾有 DNS rebinding 类漏洞（CVE-2026-42559，公开资料显示 prior to 1.4.0 受影响）。MCP server 若监听 localhost 或内网地址，攻击者网页可诱导浏览器向 `127.0.0.1` / 内网 MCP endpoint 发 authenticated requests；如果 token/cookie/本地信任模型处理不严，会变成“网页打内网 MCP”的典型 rebinding 攻击。

Current mitigations are incomplete:
- P0-3 写了 nginx / 网关 TLS、mTLS、限流、证书验证。
- 但没有明确：拒绝非白名单 `Host`、校验 `Origin`、禁止 browser credentialed CORS、强制 bearer token 不走 cookie、MCP server 自身也要做 Host/Origin defense。
- “默认绑定 127.0.0.1”不是防护；DNS rebinding 正是攻击 localhost / private IP 的场景。

Required fix:
1. 在 tech-choices.md 增加 rmcp 选型与版本：`rmcp >= 1.4.0`（或当前 patched 版本），并写明不得低于修复 DNS rebinding 的版本。
2. 在 P0-3 增加 “MCP HTTP Security Contract”：
   - allowlist Host：只接受配置中的公网域名或 loopback dev host；拒绝 IP literal / unknown Host。
   - enforce Origin：browser-originated requests 必须匹配 allowlist；non-browser MCP client 必须无 Origin 或使用明确 client auth。
   - CORS 默认关闭；如开启，仅允许精确 Origin，禁止 `Access-Control-Allow-Origin: *` 与 credentials 组合。
   - Auth token 只用 `Authorization: Bearer`，不接受 ambient cookies 作为 MCP auth。
   - SSE endpoint 同样执行 Host/Origin/Auth 校验，不能只保护 POST endpoint。
   - MCP server 即使在 nginx 后也要自行校验 `Host` / `X-Forwarded-Host` 信任链，不能只依赖反代。
3. 在 P0-3 的测试部分增加 rebinding regression：伪造 Host/Origin、localhost/private IP Host、SSE GET、preflight、credentialed CORS。

---

### H2 — Wasmtime 固定 `=30.0` 但缺少安全支持窗口；到 2026 已是供应链高风险

Severity: High
Affected docs:
- tech-choices.md §2：选择 Wasmtime
- P0-4 §2.1：`wasmtime = "=30.0"`，仅写 cargo audit + 升级前人工审查

Problem:
P0-4 将 Wasmtime 锁定为 `=30.0`，这对 deterministic replay 有好处，但对 untrusted multi-tenant WASM sandbox 是高风险。Wasmtime 历史上持续出现 sandbox / embedder API / codegen 相关 CVE；当前公开资料显示 2025–2026 仍有 Wasmtime CVE，且补丁版本在 38.x、37.x、36.x、24.x 等支持分支发布。`=30.0` 这种单点固定版本如果不属于受维护安全分支，就会卡在已知漏洞窗口内。

“cargo audit + 人工审查 CHANGELOG”不足以支撑生产安全，因为：
- `cargo audit` 只能发现 RustSec/OSV 已覆盖的 advisory，不能替代供应商 security advisory 跟踪。
- 固定版本没有写 “patched train” 与 “最大滞后时间”。
- 一旦 Wasmtime CVE 需要跳版本修复，replay determinism 与安全修复会冲突；文档没有决策规则。

Required fix:
1. P0-4 不应冻结到 `=30.0` 这个具体旧版本；应冻结为 “pinned supported train”，例如：
   - `wasmtime = "=<current patched supported version>"`
   - 记录 `wasmtime_version` 进入 TickTrace / module cache key / replay metadata。
2. 增加安全升级 SLA：
   - Critical/High Wasmtime advisory：48h 内评估，7 天内升级或下线 untrusted execution。
   - Medium：30 天内升级。
   - 若 CVE 影响 sandbox escape / host memory safety，优先安全，允许 replay verifier 标记跨版本 replay 需要原版本 container。
3. 增加 “Replay compatibility mode”：历史 replay 使用记录的 Wasmtime version 或 deterministic executor container；生产执行使用 patched version。
4. CI 不只跑 `cargo audit`，还要订阅 Bytecode Alliance security advisories / OSV / OpenCVE，并在依赖版本落后于 patched train 时失败。

---

### H3 — `RawCommand.player_id` 与 P0-9 服务端注入身份模型冲突，可能生成身份伪造 API

Severity: High
Affected docs:
- P0-2 §2 RawCommand 结构包含 `player_id`
- P0-9 §1 / §3.3 明确 “客户端不可自报 player_id”
- P0-8 IDL commands 未含 player_id，但 P0-2 示例会影响实现者

Problem:
P0-9 的原则是正确的：player_id 必须来自服务端 auth context，客户端不可自报，若提供也必须覆盖。但 P0-2 的 RawCommand JSON 示例仍把 `player_id` 放在命令体内，并写 “必须匹配已认证玩家”。这在 codegen / SDK / MCP schema 落地时很危险：实现者可能生成一个含 `player_id` 的玩家侧 Command schema，然后在 validator 中做 “匹配检查”。匹配检查一旦某个入口漏掉 auth binding，就退化成典型 IDOR / confused deputy：玩家可构造别人的 player_id 或 object_id 组合尝试越权。

Required fix:
1. P0-2 将玩家侧输出结构拆成两层：
   - `ClientCommand`: `{ tick, sequence, action }`，不含 `player_id`。
   - `AuthenticatedCommand`: `{ command: ClientCommand, auth: AuthContext }`，由服务端注入。
2. P0-8 IDL 明确生成两套 schema：
   - WASM/SDK output schema 禁止 `player_id`、`source`、`auth`、`scope`。
   - internal TickTrace schema 包含 `auth.player_id`。
3. Tick 输出 JSON Schema 增加 `unevaluatedProperties: false` / per-command `additionalProperties: false`，并把 `player_id` 列为 forbidden property。
4. Validator API 形态必须是：
   - `validate(auth: &AuthContext, cmd: &ClientCommand, world: &World)`
   - 禁止 `validate(raw: RawCommand)` 从 body 读取 player_id。

---

### H4 — Tick commit 阶段在 P0-1 图与正文/DESIGN 不一致，可能造成发布未提交状态或回滚语义错误

Severity: High
Affected docs:
- DESIGN.md §3.2：EXECUTE 阶段包含 `FDB 原子提交`
- P0-1 §1 状态机：BROADCAST 阶段第 2 步写 `FDB 原子提交`
- P0-1 §3.4 / §4.2：正文又说 commit 在 EXECUTE，BROADCAST failure never rolls back committed tick

Problem:
这是一个实现风险很高的文档冲突。状态机图把 FDB commit 放在 BROADCAST 阶段，而正文和 DESIGN 把 commit 放在 EXECUTE。两者语义完全不同：

- 正确模型：EXECUTE 在 FDB transaction 内完成 validate/apply/commit；commit 成功后才计算/发布 delta。
- 错误模型：先算 delta / 进入 BROADCAST，再 commit；如果 NATS/Dragonfly/commit 任一失败，客户端可能看到未提交或最终回滚的状态，或 tick_counter 与持久化状态分叉。

Required fix:
1. P0-1 状态机图必须改为：
   - EXECUTE: validate/apply -> FDB atomic commit -> state_checksum -> tick_counter advance
   - BROADCAST: read committed tick result -> Dragonfly update -> NATS publish
2. 明确禁止 BROADCAST 中写权威状态；BROADCAST 只能写非权威缓存/发布消息。
3. 增加 invariant：
   - `NATS tick N` must reference committed FDB versionstamp for tick N。
   - Gateway 发现 delta 无 versionstamp 或 versionstamp 不存在时拒绝广播。
4. 集成测试：注入 commit failure、NATS failure、Dragonfly failure，断言不会广播未提交 tick。

---

## Medium

### M1 — RuleMod / Rhai actions 的 capability 边界仍偏宽，`modify_entity` 容易绕过 Command Validation 的安全不变量

Severity: Medium
Affected docs:
- DESIGN.md §8.7：Rhai actions 包含 `deduct_resource` / `award_resource` / `modify_entity`
- P0-7 §1：模组 actions 不能绕过 Command Validation Pipeline
- P0-9 §2.3：RuleMod 仅经济 + 事件，但 P0-7/DESIGN 又允许 `modify_entity`

Problem:
文档同时表达了两种模型：

- RuleMod 只能做经济 + event，不能触发战斗/查询世界。
- Rhai API 却给了 `actions.modify_entity(entity_id, property, value)`。

`modify_entity` 是典型 capability creep：一旦能改任意 component/property，就可以绕过 movement/combat/build/spawn validator，直接改 owner、hits、position、cooldown、controller progress。即使模组由服主安装，也会成为供应链与恶意模组市场的主要破坏面。

Required fix:
1. 删除通用 `modify_entity`，改成 narrow typed actions：
   - `deduct_resource(player, resource, amount)`
   - `award_resource(player, resource, amount)`
   - `emit_event(type, data)`
   - 如确需修改 entity，只允许白名单 action，如 `apply_status_effect(entity, effect, duration)`，且经过 RuleActionValidator。
2. P0-9 与 P0-7 统一：RuleMod capability 是 “economy/event/status whitelist”，不是 arbitrary ECS mutation。
3. TickTrace 记录每个 RuleAction 的 before/after diff 与 mod_id/version/hash。
4. 模组市场安装时展示 capability manifest，默认拒绝高危 capability。

---

### M2 — Module validation 10ms + Wasmtime `Module::from_binary` 顺序不清，存在小 WASM 解析/编译 DoS 窗口

Severity: Medium
Affected docs:
- P0-4 §2.4 模块校验
- P0-4 §7 编译时预算

Problem:
P0-4 §2.4 的伪代码先调用 `wasmtime::Module::from_binary(&engine, wasm_bytes)`，之后才检查 exports/imports。§7 又写 `module validation = 10ms wasmparser 解析超时`、编译超时 30s。这里需要更明确的 staging，否则实现者可能直接用 Wasmtime 编译器解析+编译 untrusted module，再做导入导出白名单检查。

DoS 模式：攻击者提交 5MB 以内但结构复杂的 WASM，让 Cranelift/validator 花大量 CPU/内存；并发编译 5 个仍可能造成 gateway/engine 资源尖峰。

Required fix:
1. 明确三阶段：
   - Stage A: `wasmparser` streaming pre-parse，10ms/CPU budget，检查 size/import/export/start/custom section count/function count/table/memory limits。
   - Stage B: Wasmtime compile in isolated compile worker，30s/512MB cgroup。
   - Stage C: cache compiled artifact by `(module_hash, wasmtime_version, config_hash)`。
2. 对 function count、type count、data segment count、custom section total bytes 增加硬限制。
3. `swarm_validate_module` 与 `swarm_deploy` 共享同一 pipeline，不能 validate 走轻管线、deploy 走重管线。

---

### M3 — seccomp whitelist 包含 `write`，但没有按 fd 限制；日志/管道泄漏面需收紧

Severity: Medium
Affected docs:
- P0-4 §4.1 seccomp
- P0-4 §2.3 WASI 默认无 stdout/stderr

Problem:
P0-4 禁止 WASI stdout/stderr，但 OS 层 seccomp 仍允许 `write`。这可能是运行时必须 syscall，但如果 fd 继承/传递不严，WASM guest 或 runtime bug 可能向意外 fd 写数据，造成日志注入、协议污染或 side-channel。

Required fix:
1. sandbox fork 后关闭除 Unix socket/control fd 之外的所有 fd，并设置 `close_range()` / `FD_CLOEXEC`。
2. seccomp 使用 argument filtering：`write` 仅允许到明确的 control fd；如不可行，至少在进程启动前确保 fd table 最小化。
3. 测试恶意 WASM / WASI 尝试 stdout/stderr、fd_write、日志注入，断言无输出进入 engine log。

---

### M4 — MCP `swarm_simulate` / `swarm_dry_run_commands` 的 CPU/信息泄露边界需要与可见性策略绑定

Severity: Medium
Affected docs:
- P0-3 §4.4：`swarm_simulate` 5/tick / 3/tick
- P0-6 §3.1：`swarm_dry_run_commands` snapshot-bound non-authoritative dry-run
- P0-9：Simulate budget 0.5× MAX_FUEL

Problem:
Simulate/dry-run 是高价值工具，也天然是 DoS 与 oracle 风险点。当前写了 rate limit 和 snapshot-bound，但缺少：

- 模拟 horizon 上限。
- 是否可调用 pathfinding / host queries。
- 是否会返回隐藏实体导致可见性 oracle。
- dry-run rejection detail 是否可能通过 “试探不可见 object_id” 泄露 ObjectNotFound vs Hidden。

Required fix:
1. 对 simulate 增加 `max_ticks`, `max_entities`, `max_commands`, `max_wall_ms`。
2. dry-run 对不可见对象统一返回 `ObjectNotFoundOrNotVisible`，避免枚举隐藏 entity id。
3. simulate 输入必须是已签名 snapshot_id，不接受客户端自带任意 snapshot JSON 作为 authoritative state。
4. 结果只能包含调用者可见字段；不得返回未来隐藏实体。

---

### M5 — 可见性策略中 `player_view = full` + MCP 查询可能给 AI 超出 WASM snapshot 的信息，需明确“人类 UI 与 AI MCP 是否同等”

Severity: Medium
Affected docs:
- DESIGN.md §8 可见性
- P0-5 §3.5：`player_view = full` 时玩家屏幕 / MCP 全地图，但 WASM snapshot 仍过滤
- P0-3 §1：MCP 信息量与 Web UI 等量，不更多不更少

Problem:
P0-5 允许 `player_view = full` 使人类屏幕 / MCP 全地图，但 WASM `tick()` snapshot 仍按 `is_visible_to`。这对教学/合作世界可能合理，但对 AI agent 是一个潜在 fairness split：AI 可通过 MCP 看全图，再生成下一版 WASM 策略，而 WASM tick 本身看不到全图。人类也能通过屏幕看全图再改代码，所以“同级”成立；但必须在 World/Arena policy 中明确哪些模式允许。

Required fix:
1. 明确 `player_view=full` 只允许 Tutorial / PvE / explicitly non-competitive worlds；Arena 与 default World 禁用。
2. MCP `get_snapshot` 与 WASM snapshot 区分命名：
   - `swarm_get_player_view`：屏幕/MCP 视角，可 full。
   - `swarm_get_wasm_snapshot`：实际 tick 输入，永远 fog-filtered。
3. 在世界规则 UI/MCP docs 中标注：该世界是否 competitive-fair。

---

## Informational

### I1 — 文档中仍有若干状态/编号不一致，建议冻结前清理

Severity: Informational
Examples:
- P0-1 标注 “Phase 2 阻断项”，DESIGN §9 又标注 Phase 0 完成。
- DESIGN §11.2 标题写成 `10.2`。
- P0-7 配置示例仍使用 `decay_rate = 0.0` / `damage_multiplier = 1.0` 浮点表示，但 Determinism Contract 禁 f64，建议统一为 fixed integer。

Impact:
不是直接安全漏洞，但会导致实现者误读冻结状态或把浮点带入配置解析。

Recommendation:
冻结前跑一次 docs lint：章节编号、状态字段、浮点 literal、source/capability 矩阵一致性。

---

### I2 — 供应链清单还不完整

Severity: Informational

tech-choices.md 覆盖了 Bevy、Wasmtime、Rhai、FDB、NATS、Dragonfly、ClickHouse、Blake3、Ed25519、SDK、Web UI，但缺少：

- rmcp 版本与安全策略。
- OAuth/JWT 库选择。
- seccomp/cgroup helper crate 或 sandbox launcher。
- JSON Schema validator crate。
- wasmparser / object parsing crate。
- Rhai sandbox feature flags。

Recommendation:
增加 `security-dependencies.md` 或 tech-choices 的 “Security-critical dependencies” 表：crate、版本策略、CVE feed、升级 SLA、是否允许 transitive default features。

---

### I3 — Bevy 本身不是主要 CVE 风险，但应避免引入渲染/asset 侧依赖到 headless engine

Severity: Informational

Bevy ECS 用于 headless server 是合理选择，公开搜索未显示 Bevy ECS 有类似 Wasmtime/rmcp 的高危 CVE 历史。但 Bevy 全引擎默认 feature 可能拉入渲染、asset、image/audio 等不必要依赖，扩大供应链面。

Recommendation:
engine 侧只依赖 `bevy_ecs` / 必要 schedule crates，禁用 default features，避免把 wgpu/image/asset loader 等客户端依赖带进 server binary。

---

## Final Gate

安全终审 gate 条件：

必须修复后再进入实现冻结：
- H1 rmcp/MCP HTTP Host-Origin-DNS rebinding 合同与版本 pin。
- H2 Wasmtime supported patched train + CVE upgrade SLA + replay versioning。
- H3 ClientCommand/AuthContext 分离，禁止玩家侧 `player_id`。
- H4 P0-1 commit 阶段统一到 EXECUTE，并加未提交 tick 不广播 invariant。

建议同批修复：
- M1 删除或强约束 RuleMod `modify_entity`。
- M2 明确 module validation staging。
- M4 收紧 simulate/dry-run oracle 边界。

修复以上 High 后，我的预期 verdict：APPROVE_WITH_RESERVATIONS。
