# R3 Security Review — rev-gpt-security

Reviewer: GPT-5.5 security
Scope: `design/DESIGN.md`, `specs/01`–`09`, `api/mcp-tools.md`, `security/CVE-SLA.md`, plus dependency/advisory spot checks for rmcp / wasmtime / bevy.

## Verdict

REQUEST_MAJOR_CHANGES

R3 相比前轮已经补上了大量正确的安全合同：MCP 不再是 gameplay 控制通道、WASM 是唯一玩家执行器、Source Gate 服务端注入身份、HTTP/SSE 与 browser/CLI transport 拆分、snapshot / host function / WS / REST 共用 `is_visible_to`、JSON-RPC batch 禁用、模拟与审计日志有大小上限。这些方向是对的。

但当前设计仍有若干阻塞项：最严重的是隐藏实体 ID/位置可通过指令拒绝路径枚举、Wasmtime 版本锁定策略与现实 CVE 历史不匹配、以及 MCP / player_view / simulate 形成“只读接口泄露 → 部署 WASM 利用”的跨层信息通道。此外，若实现者照 DESIGN 中的 Rhai in-process 示例落地，会绕过 specs 中较强的进程隔离合同。

---

## Critical

### C1 — 指令校验路径可作为隐藏实体枚举 / 位置 oracle

位置：`specs/02-command-validation-spec.md` §3.5, §3.10–3.16, §5, §6；`specs/05-unified-visibility-policy.md` §2.4, §3.6

问题：多条 gameplay command 的校验顺序是先检查 `target_id` 是否存在、owner、类型、距离，再返回精确 `RejectionReason` 与 detail。示例拒绝响应甚至包含精确位置：

```json
"detail": "object_1001 at (5,3), target_1002 at (5,6) — distance 3, require ≤ 1"
```

这会把 Command Validation Pipeline 变成 IDOR / side-channel oracle。攻击者只需枚举 `target_id` 或猜测单调递增 ObjectId，就可能区分：

- `ObjectNotFound`：ID 不存在；
- `NotStructure` / `target_drone` / `FriendlyTarget`：ID 存在且类型/归属已泄露；
- `OutOfRange { distance, max }`：目标存在且位置距离被泄露；
- `AlreadyHacked` / `AlreadyDebilitated` / cooldown 类错误：隐藏目标状态被泄露。

这绕过了 `specs/05` 中“其他玩家冷却、疲劳、拒绝指令、WASM 错误隐藏”的可见性合同。WASM snapshot 本身即使过滤正确，攻击者仍可通过提交无效命令向服务器探测隐藏实体。

修复建议：

1. 对所有 `target_id` 类参数，在类型/owner/range/detail 前先执行目标可见性检查。
2. 对不可见或不存在目标统一返回 `NotVisibleOrNotFound`，不得区分 ID 是否存在。
3. rejection detail 只允许包含调用者自身实体位置、公开阈值、调用者已可见目标的信息；不可见目标不得写入精确坐标、owner、类型、状态、冷却、body、资源。
4. 把此规则写进 `validate_and_apply()` 的编译期/单元测试合同：枚举隐藏 ObjectId 时，所有输出面只得到同一个 opaque 错误。
5. `swarm_explain_last_tick` / TickTrace 玩家视图同样必须重放该脱敏逻辑；admin trace 才能保留完整 detail。

### C2 — Wasmtime pin `=30.0` 不符合当前安全现实；沙箱逃逸风险不能只靠季度审查兜底

位置：`specs/04-wasm-sandbox-baseline.md` §2.1；`security/CVE-SLA.md`

问题：设计锁定：

```toml
wasmtime = "=30.0"   # 锁定版本 — 不自动升级
```

锁定依赖本身是正确方向，但选定固定版本没有明确落在 Bytecode Alliance 支持窗口，也没有给出“最低安全版本 / LTS 轨道 / cargo-deny 阻断 RustSec advisory”的硬门禁。

外部事实核对：

- RustSec package page for `wasmtime` 列出 2026 年多条 advisory，其中包括 Critical：`RUSTSEC-2026-0095`（Winch backend sandbox-escaping memory access）与 `RUSTSEC-2026-0096`（aarch64 Cranelift guest heap access sandbox escape），以及多条 host crash / OOB / data leakage advisory。
- Bytecode Alliance 2026-04-09 advisory 明确发布 `43.0.1`, `42.0.2`, `36.0.7`, `24.0.7` 来修复 12 个安全公告，其中 2 个 Critical，并建议用户尽快升级。

Swarm 的威胁模型是大规模多租户恶意 WASM：玩家可反复上传、编译、运行 adversarial module。这里任何 Wasmtime sandbox escape 都是平台级 Critical。当前 “=30.0 + cargo audit + 人工审查” 不足以成为上线安全合同。

修复建议：

1. 不要在设计中指定 `=30.0` 作为目标版本；改为“锁定到当前受支持安全线的 patch 版本”，并示例使用已修复线（如 Bytecode Alliance 公告中的 maintained patch line）。
2. CI 必须启用 `cargo audit` / `cargo deny`，对 wasmtime / wasmparser / cranelift-codegen / wasmtime-wasi 的 RustSec advisory 直接 fail build，不允许 warn-only。
3. 明确禁用 Winch backend，除非单独经过安全评审；当前设计只写 `cranelift_opt_level`，但未写 `strategy` / compiler backend policy。
4. 对 aarch64 与 x86_64 分别列出支持矩阵。若 aarch64 生产启用，必须把 Cranelift aarch64 advisories 纳入发布 gate。
5. 若使用 component model / WASI preview2，应显式说明；当前设计说 WASI 默认全禁，但 dependency advisories 中多条影响 component string transcoding / wasi:http，需通过 feature flags 最小化依赖面。

---

## High

### H1 — rmcp Streamable HTTP / DNS rebinding 防御需要版本与部署硬门禁，而不只是架构图约束

位置：`design/DESIGN.md` §2.1；`specs/03-mcp-security-contract.md` §2.1–2.3；`api/mcp-tools.md`

设计里已写 Host header 校验、Origin/CSRF、Agent mTLS/signed request、MCP server 仅监听 `127.0.0.1`，方向正确。

但外部 advisory 显示 `rmcp` 在 `1.4.0` 前的 Streamable HTTP server transport 存在 DNS rebinding 漏洞：未校验 Host header，恶意网站可向 victim loopback/private-network MCP server 发送 authenticated requests。Swarm 架构正好使用 `rmcp, HTTP/SSE`，且 MCP 拥有 deploy/debug/read 能力。

风险：如果实现者直接暴露 rmcp transport、绕过 Gateway，或使用 `<1.4.0`，浏览器 DNS rebinding 可打到本地/内网 MCP endpoint，进而执行 `swarm_deploy`、读取 debug、刷新 token 或消耗模拟资源。

修复建议：

- 依赖合同写死：`rmcp >= 1.4.0`，并禁止启用未包在 Gateway 后的 Streamable HTTP server transport。
- MCP server 必须只监听 Unix socket 或 loopback，并在进程启动时拒绝 `0.0.0.0` / private interface bind。
- Gateway 层做 Host allowlist 之外，rmcp 应用层也做 Host / audience / world_id / endpoint kind 校验，形成纵深防御。
- 增加 DNS rebinding 集成测试：恶意 Origin + Host mismatch + SSE reconnect + signed/unsigned agent endpoint 混淆。

### H2 — `player_view = full` / MCP 只读视图可泄露隐藏地图，并通过下一次部署转化为 gameplay 优势

位置：`design/DESIGN.md` §8.2 可见性与观战；`specs/05-unified-visibility-policy.md` §3.5, §8

设计将可见性分成 drone snapshot 与玩家屏幕 / MCP 视图，并允许：

- `player_view = "full"`：玩家实时看到全地图；
- MCP 与人类屏幕同级；
- WASM snapshot 仍按 `is_visible_to(player)` 过滤。

这对“只看不动”的人类 UI 也许可接受，但对 AI agent 不成立：AI 通过 MCP 读取 full map 后，可以把隐藏信息写进下一版 WASM 策略，或直接选择 deploy timing / spawn body / pathing 参数。即使 tick snapshot 过滤正确，AI 的 out-of-band planning memory 已被污染，下一 tick 的 Command[] 可利用隐藏信息。

修复建议：

1. 对任何会影响正式 World / Arena 竞争结果的 AI MCP endpoint，强制使用 gameplay visibility，不允许 `player_view=full`。
2. `player_view=full` 只能用于 Tutorial / local sandbox / cooperative non-ranked worlds，并且该世界的 deploy / ranking / PvP 标记必须隔离。
3. 若人类 Web UI 允许 full map，AI MCP 也不应同时拥有 deploy 到 competitive world 的能力；需要 capability split：`read_full_map` 与 `swarm:deploy` 互斥。
4. 在 `WorldConfig.validate_config` 中写硬规则，而不是文档建议。

### H3 — `swarm_simulate` / `swarm_dry_run_commands` 的输出边界不足，可能泄露未来不可见状态并形成 DoS 放大

位置：`specs/04-wasm-sandbox-baseline.md` §6.1；`specs/03-mcp-security-contract.md` §4.4；`api/mcp-tools.md`

当前限制有 `max_ticks=100`, `max_entities=1000`, `max_cpu_ms=5000`, `concurrent_simulates=3`。这些是必要但不充分。

信息泄露路径：如果 simulate 输出包含未来 N tick 的实体变化、路径、碰撞、rejection、资源结果，而输入 snapshot 中仅有当前可见数据，那么模拟系统可能通过服务端真实规则/地形/隐藏状态计算出未来不可见信息。尤其是 fog-of-war 地形、隐藏敌方实体、市场/资源状态、spectator delay 相关数据。

DoS 路径：单个玩家 3 个并发 × 5 秒 CPU，500 AI 玩家即可压出约 7500 CPU 秒的瞬时需求。加上 MCP_Query 50/tick、schema/docs 无限制、dry-run 编译预算，很容易从小请求触发大服务端开销。

修复建议：

- simulate 必须只基于调用者提供的、已过滤 snapshot 副本；不得访问 authoritative hidden world state。
- 输出也必须再次套 `is_visible_to` 或 snapshot-bound visibility，不得返回未来全知 delta。
- 增加全局模拟 worker pool、每 IP / 每 player / 每 world 的共享预算和队列上限；超过后返回 429，不排队无限增长。
- `max_cpu_ms=5000` 应区分 wall-clock 与 CPU；对每次模拟的 entity×tick 复杂度做静态估算，超过直接拒绝。
- `swarm_get_schema` / `swarm_get_docs` 虽可无认证，但要 CDN/static 化或加 IP 限流，避免动态生成放大。

### H4 — Command schema / size limits 自相矛盾，容易导致 validator 与生成代码不一致

位置：`specs/02-command-validation-spec.md` §1.1, §6；`specs/08-game-api-idl.md` §2

发现的不一致：

- JSON Schema 写 `maxItems: 100`，文字写 `MAX_COMMANDS_PER_PLAYER (500)`；
- `tick()` ABI 在 `specs/04` 写返回 buffer ≤256KB；`specs/02` 批级限制写整批 ≤1MB；
- CommandIntent 示例用 `{ sequence, action: { type: ... } }`，后面旧段落又出现 `{ action: "RangedAttack", seq: N }` / `{ cmd: "move" }`；
- `additionalProperties: false` 写成“拒绝未知顶层字段”，但 CommandIntent 顶层是 array，真正需要对 item object 和 action variant 设置 `additionalProperties:false`。

安全影响：schema 分歧会导致某些入口接受另一入口拒绝的 payload，形成 mass-assignment / request smuggling 类漏洞。尤其是 `player_id/source/tick/auth` 禁止字段，如果某个生成器或 MCP schema 漏了 `additionalProperties:false`，客户端可尝试自报身份或 source。

修复建议：

- 以 `specs/08-game-api-idl.md` 为唯一机器真相源，删除 `specs/02` 的旧 JSON 样式段落或标记为非权威。
- 明确单一上限：建议 `CommandIntent[] <= 256KB`、单条 command <= 64KB、max commands = 500 或 100 二选一。
- 对每个 action variant 生成 strict schema：`oneOf` + discriminator + `additionalProperties:false`。
- CI 加 round-trip 测试：WASM output schema、MCP dry-run schema、Rust validator、docs 示例必须一致。

### H5 — Rhai 规则模组安全模型在 DESIGN 与 specs 间仍有危险落差

位置：`design/DESIGN.md` §8.7；`specs/07-world-rules-engine.md` §5.1, §7.5, §9

specs 后半部分已加入较强的进程隔离、签名、RhaiActionBuffer、cgroup/seccomp。问题是 DESIGN 仍包含会误导实现的旧模型：

- 表格说 Rhai “服主自行安装，可信”；
- 示例集成代码在 engine 进程内 `tick_end.call(...); actions.apply(world);`；
- `inprocess` 仍是配置选项；
- §9 又说规则 System 可以“修改 ECS 资源/组件”，同时又说不可绕过 Command 校验管线。

这会导致实现者选择性能优先的 in-process 模式或直接给规则系统 `&mut World`，使第三方模组成为 RCE / DoS / 越权写世界状态的供应链入口。

修复建议：

- DESIGN 顶层改为：第三方 Rhai 默认不可信；生产禁止 in-process，或需要 `--unsafe-trust-mods` 明确启动参数且不能加入官方排名。
- 删除 / 改写直接 `actions.apply(world)` 的 in-process 示例，所有示例都走 sandbox worker + IPC + buffer apply。
- `RuleMod` 不应声明“可修改 ECS 组件”；只能提交 capability-scoped actions，由 engine core mini-validator 转换。
- 模组签名除 Ed25519 外，还要有 key rotation / revocation / trust pinning / lockfile checksum 强制校验。禁止 tag force-push 只告警，应失败。

---

## Medium

### M1 — Overload 的“静默 no-op”仍可能通过资源、cooldown、目标全局 cooldown 产生侧信道

位置：`design/DESIGN.md` §8 特殊攻击；`specs/02-command-validation-spec.md` §3.12

设计说目标到达下限后 Overload 静默 no-op，攻击者无法从返回值/副作用推断 fuel 状态。但仍需定义：资源是否扣除、攻击者 drone cooldown 是否进入、目标全局 cooldown 是否刷新、TickTrace / profile 是否显示。这些副作用若随“是否触底”变化，就仍是 oracle。

建议：无论是否触底，只要通过可见性与资源校验，就执行完全相同的扣费、attacker cooldown、target cooldown、审计输出；仅目标 fuel delta clamp。否则改为显式 `TargetOverloadIneffective`，但那就承认这是可见信息并做玩法平衡。

### M2 — FoundationDB 事务 + Bevy World deep snapshot 的 tick 复杂度缺少全局实体/房间硬上限

位置：`specs/01-tick-protocol-spec.md` §3.5；`design/DESIGN.md` §3.2

设计要求 Phase 2a 前对 Bevy World 做深拷贝，FDB commit 失败后 restore。若默认 500 活跃玩家 × 每玩家 500 drones，再加 structures/resources/construction sites，单 tick 深拷贝与 checksum 可能成为最大开销。攻击者可通过合法 build/spawn 扩大实体数，使最小后续请求触发最大服务端成本。

建议：定义每 world / room / player 的实体总量硬上限、snapshot 内存预算、FDB transaction byte budget、tick admission control。超过预算时拒绝 spawn/build 或进入 degraded，而不是让 tick snapshot O(E) 无界增长。

### M3 — REST / WS / gRPC 的常见滥用模式还缺少 endpoint 级合同

位置：`design/DESIGN.md` §2, §7；`specs/03-mcp-security-contract.md`

MCP HTTP 合同较强，但普通 REST / WS / gRPC 只在架构图出现。仍需明确：

- REST 路径 `/api/v1/world/rooms/:id` 是否做 object-level auth，防 IDOR；
- WS subscription 是否只能订阅自己可见 world/room，不能自报 player_id；
- gRPC Gateway→Engine 是否 mTLS / Unix socket / service identity；
- NATS subject 是否按 world/player namespace ACL，防跨租户订阅；
- admin endpoints 是否有 CSRF / MFA / break-glass audit。

这些不是实现细节；它们决定是否会重演“内部总线默认可信导致横向移动”的常见事故。

### M4 — Deploy nonce TTL 与编译时间窗口仍需实现级状态机

位置：`specs/09-command-source-model.md` §3.2–3.3；`specs/04-wasm-sandbox-baseline.md` §7

deploy_nonce TTL 60s、payload expires ≤15min，编译 timeout 30s。若客户端上传大 WASM、网络抖动、队列中等待并发编译 slot，nonce 可能在验证前/后过期。更重要的是需要定义 nonce 消费点：验证开始消费、编译成功消费、还是 commit 成功消费。

建议：nonce 在“验证通过并写入 pending deployment record”时原子消费；编译后只引用 pending record，不重新接受客户端 payload。失败 record 可有短 TTL 且不可重放。

### M5 — Bevy 依赖本身当前未见强相关 CVE，但 ECS 调度/unsafe 插件面需要 supply-chain policy

外部核对：OpenCVE 搜索 “Bevy” 返回的 2025 CVE 是另一家 Bevy Event service（SSO/CSRF），不是 Rust Bevy game engine。当前未发现与 `bevyengine/bevy` 直接相关的公开 CVE 命中。

但 Bevy 生态依赖树深、版本仍快速演进，且 Swarm 会把 ECS 作为权威世界状态执行核心。建议：

- 锁定 Bevy 版本并纳入 `cargo deny` / `cargo vet`；
- 禁止在 engine core 引入不必要 Bevy plugins；
- 对任何 unsafe ECS component serialization / snapshot restore 代码单独审计；
- 回放 determinism CI 必须覆盖不同 CPU 架构与 release/debug profile。

---

## Informational

### I1 — 现有强项

- MCP 不做 `swarm_move` / `swarm_attack`，AI 与人类同走 WASM，这修复了上一轮最危险的公平性架构错误。
- Browser 与 Agent transport 拆分、Origin/CSRF/Fetch Metadata 与 mTLS/signed request 分开，是正确防线。
- `Source Gate` 服务端注入 player_id/source/tick，禁止客户端自报 auth context，方向正确。
- WASM host functions 限定只读，mutating 操作统一走 deferred Command[]，方向正确。
- TickTrace 字段截断、JSON batch 禁用、WASM output 体积限制、path_find 调用限制都是必要的 DoS 防线。

### I2 — 建议新增的安全测试清单

1. Hidden ObjectId enumeration：枚举不可见实体 ID，所有 command 均只返回 `NotVisibleOrNotFound`。
2. Rejection detail redaction：玩家视图不含不可见 target 的 owner/type/position/cooldown。
3. rmcp DNS rebinding：Host mismatch、Origin spoof、SSE reconnect、private IP redirect 全拒绝。
4. Wasmtime malicious corpus：start section、illegal import、fuel exhaustion、path_find abuse、SIMD edge cases、aarch64/x86_64 分平台。
5. Simulate isolation：模拟输出不得包含 snapshot 外实体；CPU/entity/tick 预算可预测。
6. Schema strictness：`player_id/source/tick/auth` 注入尝试必须整批拒绝。
7. Rhai sandbox crash：模组 OOM/panic/timeout 不影响 core engine，buffer 全回滚。
8. Public spectate delay：World 模式 `public_spectate=true && spectate_delay<50` 配置验证失败。

---

## Consensus note for Speaker

我同意 DeepSeek security review 中关于 Rhai 隔离、Overload 侧信道、refund session、path_find 成本与 simulate 可见性的担忧；本评审额外把“拒绝响应作为隐藏实体 oracle”和“Wasmtime 固定版本不在安全轨道”提升为阻塞项。若只修文档，优先顺序应为：C1 rejection visibility gate → C2 Wasmtime/rmcp dependency gates → H2/H3 MCP full-view/simulate isolation → H4 schema 单一真相源 → H5 Rhai DESIGN/spec 对齐。
