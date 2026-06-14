# R7 Security Review — rev-gpt-security

Reviewer: GPT-5.5 / Security
Scope read:
- /data/swarm/docs/design/DESIGN.md
- /data/swarm/docs/design/ROADMAP.md
- /data/swarm/docs/design/tech-choices.md
- /data/swarm/docs/design/PLANNER-OUTPUT.md
- /data/swarm/docs/specs/p0/01-tick-protocol-spec.md
- /data/swarm/docs/specs/p0/02-command-validation-spec.md

Note: 用户要求的 `specs/p0/` 在仓库实际位置是 `/data/swarm/docs/specs/p0/`。该目录当前只包含 P0-1/P0-2；设计文档与路线图多次引用 P0-3/P0-4/P0-5/P0-6/P0-7/P0-8/P0-9，但这些文件在当前读取范围内不存在。

## Verdict

REQUEST_MAJOR_CHANGES

安全方向不建议进入实现冻结。当前 R7 版本比早期草案有明显进步：MCP 已回归“查看/部署/调试界面”而不是 gameplay action executor，WASM mutating host functions 被禁止，P0-2 建立了统一 Command Validation Pipeline，refund 也考虑了反放大。但从安全评审角度，仍存在多项 Phase 1/2 会直接落地的阻断问题：

1. 文档一致性破裂：DESIGN/ROADMAP 宣称 P0-3..P0-9 已冻结，但 specs/p0 实际只有 P0-1/P0-2；PLANNER-OUTPUT 仍保留已废弃的 McpPlayerExecutor/gameplay MCP 工具内容。
2. WASM sandbox 的隔离边界没有形成可执行合同：Wasmtime fuel/epoch、线性内存、host function、worker process 生命周期、资源限制、模块静态审计都只是散点，没有 P0 级强制矩阵。
3. MCP/rmcp 暴露面被低估：HTTP/SSE、OAuth2、部署、调试、文档资源和世界状态查询是完整远程控制平面，当前仅有原则，没有 Host/Origin、DNS rebinding、token scope、tool authorization、audit redaction、rate limit 的落地规则。
4. Tick 原子性与 FDB 事务边界表述存在严重矛盾，可能导致不可回放、锁持有过久、重复执行副作用或 DoS。
5. Rule Module / Rhai 供应链与 capability model 把“服主可信”当作安全边界，缺少签名、版本锁定、依赖解析、market moderation、动作 capability 与确定性审计。

建议：R7 先补齐安全合同和缺失 P0 文档，再进入实现。至少 P0-3 MCP security contract、P0-4 WASM sandbox contract、P0-5 visibility contract、P0-7 rule-mod capability contract、P0-8 IDL、P0-9 source gate 必须真实存在并与 DESIGN/ROADMAP 一致。

---

## Critical

### C1. 冻结状态与实际 P0 文件不一致，导致实现者会沿用过期安全模型

证据：
- DESIGN §4.2 引用 `specs/p0/03-mcp-security-contract.md`。
- DESIGN §9 宣称 P0-3/P0-4/P0-5/P0-7/P0-8/P0-9 均已冻结。
- ROADMAP 多个交付物锚定 P0-3/P0-4/P0-5/P0-6/P0-7/P0-8/P0-9。
- 实际 `/data/swarm/docs/specs/p0/` 当前只有 `01-tick-protocol-spec.md` 与 `02-command-validation-spec.md`。
- PLANNER-OUTPUT 明确标注是评审前草案，但正文仍写有 `McpPlayerExecutor`、`实现全部游戏动作 MCP 工具`、`AI 玩家不需要 WASM` 等已废弃内容。

攻击/失败模式：
- 开发者按 PLANNER-OUTPUT 或 ROADMAP 的锚点实现，可能重新引入 MCP gameplay command path，绕过 WasmSandboxExecutor 与 fuel metering 公平边界。
- CI/评审无法验证“冻结规范”，因为大量规范不存在。
- 安全评审无法判断 source gate、visibility、IDL、sandbox 的真实强制条件。

要求：
- 将 PLANNER-OUTPUT 移入 `archive/` 或在文件顶部加入机器可检索的 `DEPRECATED_DO_NOT_IMPLEMENT`，并删除/修正正文中的 McpPlayerExecutor/gameplay MCP 工具列表。
- 补齐或降级 DESIGN/ROADMAP 中所有 P0-3..P0-9 “已冻结”声明。
- 每个 Phase 1/2 交付物必须锚定真实存在的规范文件与章节。

### C2. MCP/rmcp 远程控制平面缺少强制安全合同

证据：
- DESIGN 将 MCP 作为 AI agent 查看世界、部署 WASM、rollback、debug/profile、docs/schema 的一等接口。
- ROADMAP Phase 2 才写 “OAuth2 → Ed25519 证书签发；限流按 P0-9 来源矩阵”，但 P0-3/P0-9 不存在。
- 技术栈使用 rmcp HTTP/SSE。外部检索显示 rmcp Streamable HTTP transport 曾有 Host header / DNS rebinding 类漏洞（CVE-2026-42559，prior to 1.4.0 未校验 Host header）。即使具体版本未来变化，MCP HTTP transport 本身也天然是浏览器可触达的控制平面。

攻击/失败模式：
- DNS rebinding / Host header 绕过：恶意网页借用户浏览器访问本地或内网 MCP endpoint，调用 `swarm_deploy` / `swarm_rollback` / `swarm_profile` / `swarm_get_snapshot`。
- Token confused deputy：AI agent、Web UI、CLI、CI deploy 共用 OAuth token 或证书 scope，导致低权限查询 token 可部署代码。
- Tool authorization 缺失：`swarm_inspect_entity`、`swarm_explain_last_tick`、`swarm_profile` 泄露不可见对象、其他玩家 rejection/detail、性能策略。
- MCP resource prompt injection：`swarm_get_docs`、玩家名、mod 描述、事件 detail 若返回给 LLM agent，可能成为 agent 操作指令注入载体。

要求：
- P0-3 必须存在，并至少包含：绑定地址默认 localhost/明确生产域名；Host allowlist；Origin/CORS 策略；CSRF 防护；DNS rebinding 防护；每 tool 的 scope；部署/rollback 需强认证和 replay nonce；query/debug/deploy 分离 token；per-player + per-IP + per-tool rate limit；audit redaction；SSE 连接上限和心跳超时。
- rmcp 版本必须 pin，并在 CI 跑 `cargo audit`/RustSec；设 CVE SLA。当前 ROADMAP 只提 Wasmtime SLA，不够。
- 所有 MCP query/debug 输出必须先通过 P0-5 visibility filter，再做 redaction。

### C3. Tick 原子性与 FDB 事务边界会诱发不可回放和 DoS

证据：
- P0-1 §3.4 写“整个阶段二包裹在 FoundationDB 事务中”，并在事务内 `validate_and_apply(txn, command, world_state)`。
- P0-1 §4.2 又写 BROADCAST 从 “in-memory post-commit state or FDB versionstamp” 读取。
- P0-1 §6.1 写 TickTrace write fail 时 “tick 执行完成但审计日志不完整”，但 §6.3 又要求每 tick 写入 commands/state/rejections/metrics 用于回放。

攻击/失败模式：
- 长事务 DoS：把整个 command execution、ECS system、可能的 validation read 都放入 FDB transaction，会把 500ms execute 窗口变成分布式事务长持有，冲突概率和 retry 成本急剧上升。攻击者可制造高冲突资源竞争提高 tick abandon rate。
- 重试副作用：如果 `validate_and_apply` 修改 in-memory world_state，再遇到 FDB commit fail 重试，必须证明内存状态 rollback；文档未说明。
- 审计缺口：TickTrace write fail 后仍推进世界，意味着该 tick 不可回放，破坏反作弊与 determinism contract。对安全系统来说，不可审计 tick 不应是普通降级。

要求：
- 明确执行模型：先在纯内存 deterministic world 上执行得到 `TickResult`，再用短 FDB transaction 原子写入 tick N state/commands/rejections/metrics/checksum；commit 失败则丢弃 TickResult 并重算或重试写入，不得复用半变异状态。
- TickTrace 是安全边界，不能 “gameplay completed but audit missing”。若 trace/state/commands/rejections 任一写入失败，整个 tick 必须视为未提交。
- 为高冲突 command 设置 per-tick conflict budget 与 backpressure，防止资源争用被用作 FDB conflict amplifier。

---

## High

### H1. WASM sandbox contract 不完整，Wasmtime 风险没有被系统化管理

证据：
- DESIGN/tech-choices 选择 Wasmtime，提 fuel metering、epoch interruption、per-tick fork、64MB memory、只读 host functions。
- P0-4 被多处引用但不存在。
- 外部检索显示 Wasmtime 有持续 RustSec/NVD advisories；Wasmtime 的安全边界需要版本 pin、CVE 响应、runtime config 锁定和回归测试。

风险：
- Fuel metering 不是完整资源控制：host functions、JSON serialization、path_find、snapshot build、module instantiation/JIT、memory growth、table allocation 可能消耗 host CPU/memory。
- “per-tick fork” 未定义 fork 是 OS process、pre-fork worker、还是 Wasmtime Store reset。不同实现的隔离强度和性能完全不同。
- 只说 64MB linear memory，不够：还需要 max tables, max instances, max memories, max stack, max wasm size, max compiled artifact size, max imports/exports, component model/WASI 禁用策略。
- 静态分析“扫描可疑系统调用”对 WASM/WASI 不应作为主要防线；主防线应是 imports allowlist + no WASI by default。

要求：
- P0-4 定义 sandbox matrix：imports allowlist、WASI disabled/limited、memory/table/instance/module size、fuel cost model、epoch timeout、host function CPU accounting、process rlimit/seccomp/user namespace、compiled module cache eviction、crash quarantine、degraded policy。
- Wasmtime 版本 pin + RustSec audit + CVE patch SLA 不仅放 Phase 7，而应从 Phase 1 开始。
- host function 必须二次校验 `out_ptr/out_len`、返回大小、range、visibility，并计入同一 fuel/budget 或单独 query budget。

### H2. Visibility 作为横切安全边界被引用但未规格化

证据：
- P0-1 snapshot 构建只写 `visibility_filter(all_entities, player_id, tick)`。
- P0-2 查询说明 GetObjectsInRange 返回可见实体。
- DESIGN §8.2 定义 fog_of_war、player_view、public_spectate、spectate_delay、replay_privacy。
- ROADMAP 锚定 P0-5，但 P0-5 不存在。

风险：
- snapshot/MCP/WS/REST/replay/debug/profile/ClickHouse analytics 任何一个面绕过 visibility 都是信息泄露。
- `swarm_explain_last_tick` 的 rejection detail 可能泄露隐藏目标位置、敌方资源、建筑状态。
- `public_spectate` + `spectate_delay=0` 默认组合在 Arena/World 的差异未强制，可能给参赛者旁路情报。

要求：
- P0-5 必须把 `is_visible_to(subject, viewer, surface, tick)` 作为唯一出口，覆盖 snapshot、MCP、WebSocket delta、REST fetch、replay、debug、profile、audit export。
- RejectionReason detail 必须区分 self-visible detail 与 redacted detail。例如目标不可见时不能返回真实坐标。
- Spectator token 与 player token 分离；public replay/spectate 默认延迟策略写入 world mode invariant。

### H3. Command validation 存在 schema/语义不一致和 mass-assignment 风险

证据：
- P0-2 §1.1 顶层 schema 是数组，但同时写 `additionalProperties: false — 拒绝未知顶层字段`，对数组无意义。
- RawCommand 包含 `player_id`、`tick`，但 P0-9 Source Gate 不存在。
- P0-2 §5 说 `detail` 字段是机器可读 JSON，但示例是字符串。
- DESIGN 使用 `cmd` 字段示例，P0-2 使用 `action.type`。

风险：
- 如果实现直接信任 RawCommand.player_id 或 tick，会出现 IDOR / command spoofing / next-tick replay。
- schema 漂移会导致 SDK、WASM output、MCP dry-run、REST admin 走不同结构，破坏“单一管线”。
- 未知字段、重复 JSON key、数字溢出、NaN/浮点、Unicode normalization 未说明，容易出现解析差异。

要求：
- `player_id`、source、capabilities 必须由 authenticated context 注入，客户端提交的 player_id 一律忽略或拒绝。
- `tick` 只允许 current/next 的规则要配合 nonce/sequence replay cache；迟到队列的行为要明确。
- 所有 command schema 从 P0-8 IDL 生成；禁止文档手写分叉。
- 明确 JSON parser 策略：duplicate keys reject、unknown fields reject、integer range exact、string normalization、max bytes before parse。

### H4. Rhai Rule Module 供应链与 capability 边界不足

证据：
- DESIGN §8.7 将规则模组设为 Rhai 脚本 + 模组市场，服主可信。
- Rhai API 提供 `actions.deduct_resource/award_resource/modify_entity/emit_event`，并通过 `actions.apply(world)` 写入。
- 依赖、conflicts、market、rating 有产品描述，但没有安全安装合同。

风险：
- 模组市场是供应链入口：恶意更新、typosquat、依赖混淆、版本漂移会直接修改世界状态。
- `modify_entity(entity_id, property, value)` 是高危 mass assignment；如果不做 allowlist/capability，会绕过 command validation 和 game invariants。
- “服主可信”不等于“脚本可信”；服务器运营者也需要防止 buggy mod 破坏 determinism 或经济。

要求：
- 模组必须有签名、lockfile、content hash、semver pin、dependency resolution、review state、rollback。
- 每个 mod 声明 capability：可读哪些 state、可写哪些 component/action、每 tick budget、是否可访问 player-private data。
- 禁止通用 `modify_entity(property,value)`；改为 typed actions，并复用 validator/invariant checks。
- 模组输出和 actions 必须进入 TickTrace；mod version/hash/config 必须是 replay input。

### H5. DoS 面：最小请求触发最大服务端开销

主要向量：
- MCP `swarm_get_snapshot` / `swarm_get_objects_in_range` / `swarm_profile` / docs/schema 可被远程高频调用。
- WASM tick 输出 256KB × 每玩家 × 每 tick，JSON parse + schema validate + rejection detail 生成可能成为 CPU/alloc 热点。
- `PathFind` 每玩家每 tick 10 次，`MoveTo` 也会做路径检查；若 host_path_find 与 command validation 双重寻路，成本翻倍。
- `MoveTo` 要求 MOVE 部件数量 ≥ 路径长度，这既怪异也可能迫使服务端做完整路径计算。
- Snapshot “按房间序列化一次，再按玩家过滤”如果先序列化全房间再过滤，可能泄露缓存侧信道，也会在大房间造成 O(E) 热点。

要求：
- 为每个 source/surface 设置 budget：MCP query QPS、snapshot bytes/s、pathfind nodes/s、JSON parse bytes/s、profile query window。
- PathFind 使用 node expansion 上限，而不只是 path_length 上限。
- 查询缓存 key 必须包含 visibility/fog/version，不得跨玩家复用可见实体结果。
- Rejection detail 生成应 lazy/limited，避免攻击者用 100 条 invalid command 放大字符串构造和日志写入。

---

## Medium

### M1. AuthN/AuthZ 生命周期不完整

OAuth2 → Ed25519 证书签发是合理方向，但缺少：证书 audience、scope、key rotation、revocation propagation、clock skew、mTLS 是否需要、部署签名 nonce、CI/CD deploy token 最小权限。24h 证书若泄露可持续部署恶意 WASM，需要短 TTL + revoke list + device/session binding。

### M2. Replay 隐私与审计保留策略未定义

TickTrace 同时是反作弊、调试、用户体验和隐私数据。需要定义 retention、export authorization、player deletion policy、public Arena replay 的 redaction、ClickHouse 与 FDB 中敏感字段一致性。否则 `mcp_audit.parameters/result` 可能长期保存玩家代码、策略、token-like 字符串。

### M3. Code deploy / rollback 缺少安全细节

`swarm_deploy` 和 `swarm_rollback` 是高危操作。需要：WASM module hash、签名、size limit、compile timeout、validation cache、rollback target authorization、deploy cooldown source gate、atomic activation tick、rollback audit、malware/quarantine status。当前只写 “下一 tick 切换到 v2”。

### M4. Determinism contract 对依赖版本和平台仍不够硬

DESIGN §8.8 禁 f64、Blake3、IndexMap、Wasmtime pinned 是好方向，但还需要：Rust compiler/profile pin、Bevy version pin、Rhai version/config pin、serde_json ordering/canonicalization、WASM compiler toolchain non-determinism 影响边界、CPU architecture differences、feature flags lock。

### M5. 日志与 prompt injection 处理过窄

P0-2 将玩家名限制为 `[a-zA-Z0-9 _-]` 是亮点，但 prompt injection 不只来自玩家名：mod description_i18n、room names、event detail、chat/market order text、docs resources、rejection detail、entity labels 都会进入 AI 上下文。需要统一 LLM-facing serialization contract：data/code fences、source labels、untrusted markers、length caps、HTML/Markdown escaping。

### M6. Admin/TestHarness/Tutorial/Replay 等非玩家来源未被真实规范化

DESIGN §9 提到 12 sources 和 Source Gate，但 P0-9 不存在。Admin 和 TestHarness 常是安全事故来源：若它们复用 REST/MCP，没有 capability separation，会绕过 owner/range/visibility 校验。Replay/Simulate/DryRun 也必须保证只读、不可写生产世界。

---

## Informational

### I1. `InsufficientResource` vs `InsufficientResources` 命名不一致

P0-2 表中同时出现单复数，建议 IDL 统一枚举，避免 SDK/日志/指标分裂。

### I2. DESIGN 章节编号有小错

DESIGN §11 后出现 “### 10.2 代码规范”，应为 11.2。非安全问题，但冻结文档建议修正。

### I3. `Blake3 MAC` 用词建议更精确

技术选型称 “代码签名: Blake3 MAC”。MAC 是对称认证，不是签名。若用于部署 artifact integrity，可以叫 keyed hash/MAC；若用于不可抵赖或第三方验证，仍需 Ed25519/signature。避免实现时混淆。

---

## 亮点

1. MCP 定位修正是正确的：AI agent 通过 MCP 查看/部署/调试，gameplay 仍必须写 WASM，与人类同路径。这消除了早期 McpPlayerExecutor 带来的公平性和绕过校验风险。
2. Deferred Command Model 明确禁止 mutating host functions，所有状态变更走 `tick() → Command[] → validator → ECS`，这是安全架构核心亮点。
3. P0-2 的硬边界意识较强：MAX_COMMANDS_PER_PLAYER、JSON bytes/depth、MAX_BODY_PARTS、MAX_PATH_LENGTH、MAX_QUERY_RANGE、坐标范围、玩家名字符集等都对典型 DoS/注入有帮助。
4. Refund anti-amplification 设计合理：退还只进入下一 tick、10% 上限、重复失败不累计、高退还率 throttle，避免同 tick 计算预算放大。
5. Tick failure semantics 已经覆盖 WASM timeout/crash/invalid output、FDB fail、cache stale、NATS fail，说明设计者已经把分布式失败当作一等场景处理。
6. Determinism contract 中禁止 f64、禁 std::HashMap iteration、使用 Blake3/IndexMap、ECS `.chain()` 的方向正确，有利于回放和反作弊。
7. FDB 作为权威源、Dragonfly 作为非权威缓存、NATS publish fail 不回滚 committed tick，这个数据权威层级是清晰的。
8. Visibility 分层（drone 感知 vs player_view vs spectator/replay privacy）是正确抽象，只是还需要 P0-5 落成强制合同。
9. Rule Module 将玩家不可信 WASM 与服主规则脚本分层，产品上有扩展性；只要补上 capability/supply-chain，就有潜力成为安全可控的 mod 系统。

---

## 建议的阻断修复清单

进入实现前必须完成：

1. 补齐 P0-3/P0-4/P0-5/P0-7/P0-8/P0-9，或删除“已冻结”声明。
2. 废弃或修正 PLANNER-OUTPUT 中的 McpPlayerExecutor/gameplay MCP 内容。
3. 写出 MCP security contract：Host/Origin/DNS rebinding、tool scopes、token/证书、rate limit、visibility、audit redaction。
4. 写出 WASM sandbox contract：Wasmtime pin、imports allowlist、WASI policy、memory/table/module limits、host function budget、process isolation、CVE audit。
5. 重写 Tick atomicity：短事务提交完整 TickResult，TickTrace 不可缺失，commit fail 不得留下半变异内存状态。
6. 建立 Source Gate：认证上下文注入 player_id/source/capability，客户端字段不可信。
7. 建立 Visibility Gate：所有输出面统一调用，并定义 debug/replay/profile redaction。
8. Rule Module 改为 signed + locked + capability-based typed actions，禁止通用 mass assignment。

完成以上后，安全 verdict 可重新评估为 APPROVE_WITH_RESERVATIONS；否则当前版本应保持 REQUEST_MAJOR_CHANGES。
