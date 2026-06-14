# R6 Security Review — rev-gpt-security

Reviewer: rev-gpt-security (GPT-5.5)
Role: Security reviewer
Scope:
- `/data/swarm/docs/design/DESIGN.md`
- `/data/swarm/docs/specs/p0/01-tick-protocol-spec.md`
- `/data/swarm/docs/specs/p0/02-command-validation-spec.md`
- `/data/swarm/docs/specs/p0/03-mcp-security-contract.md`
- `/data/swarm/docs/specs/p0/04-wasm-sandbox-baseline.md`
- `/data/swarm/docs/specs/p0/05-unified-visibility-policy.md`
- `/data/swarm/docs/specs/p0/06-mvp-feedback-loop.md`
- `/data/swarm/docs/specs/p0/07-world-rules-engine.md`
- `/data/swarm/docs/specs/p0/08-game-api-idl.md`
- `/data/swarm/docs/specs/p0/09-command-source-model.md`

## Verdict

CONDITIONAL_APPROVE

理由：当前 P0 设计已经修正了最危险的架构误区：MCP 不再是 gameplay controller，所有玩家动作统一经 WASM + deferred command + validation pipeline；并且在可见性、source gate、fuel refund、sandbox、审计方面有明确安全合同。作为 Phase 0 架构冻结，方向可以进入实现。

但我不建议无条件 APPROVE。仍有若干 High/Medium 级问题需要在 Phase 1/2 实现前补成“可测试的硬合同”，否则这些点很容易在实现中退化成已知攻击模式：MCP public docs/schema DoS、Rhai 规则模组 supply-chain/沙箱边界、simulation/dry-run 信息侧信道、rollback/admin 高危能力、以及 Tick/ODB/FDB 原子性语义不一致。

## Critical

无 Critical 阻断项。

## High

### H-1: `swarm_get_schema` / `swarm_get_docs` 标注“无 scope、无限制”，存在公开 DoS 与爬取放大风险

位置：P0-3 §4.4, §5.1

问题：
- `swarm_get_schema` 与 `swarm_get_docs` 被定义为“无 scope / 无限制”。
- 这类端点通常返回较大文档、schema、教程资源，且可能触发渲染、i18n、聚合或缓存 miss。
- 对公网 MCP/HTTP 服务而言，“无需认证 + 无限制 + 大响应”是典型的低成本高放大 DoS 面。
- 即使内容是 public，也不应代表 unlimited；public endpoint 仍需 per-IP、per-ASN、全局 QPS、响应大小和缓存策略。

攻击模式：
- 单 IP 或分布式客户端高频拉取 docs/schema，大量消耗网关、MCP server、压缩、序列化、带宽。
- 若 schema/docs 后续包含动态生成内容或模组市场信息，可能进一步扩大为后端查询放大。

建议修正：
- 将 public docs/schema 归入 `PublicRead` source 或匿名 source，显式建模 auth_context。
- 加入：per-IP rate limit、全局 token bucket、强缓存 ETag/Last-Modified、gzip/brotli 预压缩、最大响应大小、CDN/static hosting 优先。
- 在 P0-3 §5.1 中删除“无限制”，改为例如：`schema/docs: 60/min/IP, cached, max 1MB response`。

### H-2: Rhai 规则模组被描述为“服主可信”，但又有模组市场；缺少供应链安全、能力最小化与签名/审核合同

位置：DESIGN §8.7, P0-7

问题：
- 设计一方面说规则模组是“服主声明 → 可信”，另一方面又设计了 `swarm mod install empire-upkeep` 和模组市场。
- 这实际形成 supply-chain attack 面：恶意/被接管的模组可通过 `actions.award_resource`、`actions.modify_entity` 等能力修改世界状态。
- 当前能力边界过粗：P0-9 表中 RuleMod “仅经济 + 事件”，但 DESIGN §8.7 又列出 `actions.modify_entity(entity_id, property, value)`，两者不一致。`modify_entity` 是极高危通用写能力，足以绕过游戏经济、权限和反作弊模型。
- 未看到模组签名、版本锁定、依赖锁文件、review/allowlist、capability manifest、危险能力确认、回滚策略。

攻击模式：
- 模组更新后植入后门，对特定 player_id 发资源或削弱敌人。
- 依赖模组被 typosquat 或版本漂移，世界重启时加载恶意版本。
- `modify_entity` 写入未校验字段，破坏确定性或绕过 Command Validation Pipeline。

建议修正：
- P0-7 增加 `mod.lock` / content hash pinning / signature verification / author identity / review status。
- 每个模组声明 capability manifest，例如 `economy.deduct`, `economy.award`, `event.emit`；默认不授予 `entity.modify`。
- 删除或强约束 `actions.modify_entity`：只能调用 typed action，不允许任意 property 写；所有 action 必须走 validator，并记录 deterministic TickTrace。
- 模组市场安装默认 pin exact version + hash；更新必须显式确认并产生审计记录。
- Arena 模式仅允许 allowlisted/signed mods，且赛前锁定。

### H-3: `swarm_simulate` / dry-run 能力可能成为信息侧信道和计算 DoS 面，当前约束不够硬

位置：P0-3 §4.4, P0-6 §3.1, P0-9 §2.2

问题：
- P0-3 中 `swarm_simulate` “按需”，P0-9 中 Simulate 限 5/tick、snapshot-bound dry-run、0.5× MAX_FUEL，但这几个描述没有完全合并为一个硬合同。
- simulate/dry-run 若可对“当前可见 snapshot”做未来预测，可能通过反复试探推断隐藏状态、敌方行为、资源争用结果或 PRNG 顺序。
- 如果模拟执行路径复用真实 validator/pathfinding/规则模组，也可能成为 CPU 放大器。

攻击模式：
- 玩家构造大量 candidate command，调用 dry-run 观察 rejection/detail 差异，推断不可见实体是否存在、目标是否移动、资源是否枯竭。
- 高频 simulate 未来 N tick，消耗 pathfinding、Rhai 规则、ECS 运行成本。
- 在 Arena 中通过 simulate 探测 seeded shuffle 或赛中隐藏信息。

建议修正：
- 将 P0-3 `swarm_simulate` 的“按需”改为与 P0-9 一致的硬限制：snapshot-bound、只读副本、max ticks、max commands、max CPU wall time、per-player/per-IP budgets。
- dry-run 输出必须只基于调用者可见 snapshot；禁止返回任何因隐藏状态导致的精确差异。对不可见/不确定因素返回 `UnknownDueToVisibility` 或 conservative result。
- 不能暴露真实 tick 的 PRNG seed、shuffle order、未来敌方行为。
- 添加 leakage tests：对隐藏实体/隐藏资源/敌方 cooldown 构造 differential dry-run，断言响应不可区分。

### H-4: Rollback/Admin 能力是最高危控制面，当前仅写“rollback_token/双人审计”，缺少防滥用流程

位置：P0-9 §2.2, §2.3, §7；P0-5 data classification

问题：
- `Rollback` 允许回滚写入、全局存储、部署代码、全局可见。该能力实际等价于世界管理员 root。
- 当前仅标注 “admin_id + rollback_token” 与 “双人审计”，未定义 token 生命周期、审批流程、break-glass、不可抵赖日志、回滚范围限制、玩家通知、回滚后 replay/checksum 处理。

攻击模式：
- 单个管理员 token 泄露导致回滚世界状态或替换代码部署。
- 恶意内部人员使用 rollback 操纵 Arena/World 结果。
- 回滚后 TickTrace 与 state checksum 不一致，破坏审计和争议解决。

建议修正：
- 定义 Rollback Runbook：two-person approval、短期 one-time rollback token、硬件/外部签名可选、reason code、affected tick range、dry-run preview、玩家公告。
- Rollback 后生成新的 canonical branch/revision，不覆盖旧 TickTrace；保留 fork lineage。
- Arena 禁用 rollback 的设计是正确的，应写成不可配置硬规则。

## Medium

### M-1: Tick 原子性描述存在阶段不一致，容易实现出“已广播未提交”或“提交点不清”问题

位置：DESIGN §3.2，P0-1 状态机 §1、§3.4、§4.2

问题：
- DESIGN §3.2 写 FDB 原子提交发生在 EXECUTE 阶段。
- P0-1 状态机图 §1 在 BROADCAST 阶段列出 “2. FDB 原子提交”。
- P0-1 §4.2 又说 BROADCAST failure never rolls back committed tick，说明 commit 应已发生在 EXECUTE。

风险：
- 实现者若按状态机图把 commit 放在 BROADCAST，可能出现 delta 计算/缓存更新/发布与权威状态提交顺序混乱。
- 安全上会影响 replay、client gap recovery、审计一致性。

建议修正：
- 统一为：EXECUTE 内完成 FDB commit，commit 成功后 tick_counter 才推进；BROADCAST 只读 committed result，不包含权威写入。
- 状态机图中 BROADCAST 的 “FDB 原子提交” 改为 “读取 committed tick result / versionstamp”。

### M-2: `RawCommand` schema 仍示例携带 `player_id`，与 P0-9 “客户端不可自报 player_id”存在认知冲突

位置：P0-2 §2，P0-9 §3

问题：
- P0-2 RawCommand 示例包含 `player_id` 字段，并写“必须匹配已认证玩家”。
- P0-9 明确禁止客户端在 Command body 自报 `player_id`，服务端注入 auth context。

风险：
- 实现者可能在反序列化层接受用户提交的 `player_id` 再做 match，容易产生 mass assignment / IDOR 类漏洞。

建议修正：
- 将玩家提交的 command body schema 移除 `player_id`，只保留 `tick/sequence/action` 或甚至由 server 注入 tick_target。
- 内部 `AuthenticatedRawCommand` 可以包含 server-injected `auth.player_id`。
- P0-2 与 P0-9 统一术语：`ClientCommand` vs `AuthenticatedRawCommand`。

### M-3: WASM sandbox seccomp syscall 白名单仍偏概念化，且 `clone` / `write` / Unix socket 的边界需更精确

位置：P0-4 §4.1, §4.3

问题：
- seccomp 允许 `write`，但 WASI 禁 stdout/stderr；需要明确 write 只能到预授权 fd/UDS，否则容易出现日志/FD 泄露。
- `clone (仅 CLONE_VM | CLONE_VFORK)` 表述需要实际 seccomp 参数过滤；否则 clone/fork/线程能力可能扩大逃逸面。
- “无网络命名空间”措辞可能歧义：是创建空 netns，还是不允许网络 namespace？安全目标应为 sandbox 无外部网络能力。

建议修正：
- 明确 fd allowlist：只允许 UDS control fd、eventfd、必要 runtime fd；关闭/close-on-exec 其他 fd。
- seccomp 使用参数级过滤并纳入测试。
- 网络隔离写为：sandbox runs in isolated netns with no interfaces except loopback disabled/unused，或明确无任何 socket syscall。

### M-4: Wasmtime 版本 pin 到 `=30.0` 过粗；缺少 Rust crate 锁文件和 advisory 响应 SLA

位置：P0-4 §2.1

问题：
- `wasmtime = "=30.0"` 不是完整 patch pin；Cargo 语义中这可能不是实际版本号格式，通常需要 `=30.0.0`。
- 仅写 `cargo audit` 和人工审查 changelog，不足以覆盖 wasmtime/Cranelift 这类沙箱逃逸高价值依赖。

建议修正：
- 固定到 exact patch，例如 `=30.0.0`，提交 `Cargo.lock`。
- CI 增加 `cargo deny`，对 `wasmtime`, `cranelift-*`, `wasmtime-wasi`, `cap-std` 设置 security advisory fail-closed。
- 定义高危 CVE 响应 SLA：critical sandbox escape 24h 内评估/升级/临时禁用相关功能。

### M-5: MCP 审计日志记录完整 parameters/result，可能保存 WASM、token-adjacent 信息或敏感策略数据

位置：P0-3 §7

问题：
- `mcp_audit.parameters String, result String` 直接记录完整参数/结果。
- `swarm_deploy` 参数含 `wasm_bytes`；debug/profile/replay 结果可能包含玩家策略敏感数据。
- 审计日志本身若被查询或泄露，会成为代码/策略外泄源。

建议修正：
- 参数按工具定义 redaction policy：WASM bytes 只记录 hash/size/module_id；token/JWT 永不落库；大型 result 摘要化。
- ClickHouse 表增加 `redaction_version`、`module_hash`、`result_hash` 等字段。
- Admin 查询审计日志也需审计。

### M-6: 可见性缓存 `HashSet<EntityId>` 只缓存实体 ID，不足以防字段级泄露

位置：P0-5 §5

问题：
- 可见性不只是“实体是否可见”，还包括字段级策略：敌方资源、cooldown、fatigue、rejection、WASM 错误等隐藏。
- 仅缓存 EntityId 容易让某些输出面在实体可见时序列化过多字段。

建议修正：
- 定义 `VisibilityProjection` / `FieldMask`，输出面必须通过同一 projector 生成 DTO，而不是自行 serialize entity。
- 泄露检测测试应覆盖字段级，而不只是实体存在与否。

### M-7: FoundationDB retry + tick abandon 语义需要确保外部 side effect 不重复

位置：P0-1 §3.4, §6

问题：
- FDB commit fail 最多重试 3 次；tick 放弃后同 tick 重试。
- 如果 TickTrace、metrics、NATS、ClickHouse 或 audit 写入在事务外发生，可能出现重复 side effect 或幽灵日志。

建议修正：
- 明确事务内/事务外边界。所有 replay-critical 记录必须与 state commit 同事务或由 committed versionstamp 派生。
- 外部 side effect 使用 idempotency key：`world_id/tick/versionstamp/event_type`。
- tick abandon 不应产生对玩家可见的最终 rejection/explanation，除非标记 abandoned。

## Informational

### I-1: `additionalProperties: false` 对顶层数组措辞不准确

位置：P0-2 §1.1

顶层是 array，`additionalProperties` 只对 object 生效。建议改为：每个 Command object `additionalProperties: false`，并在 definitions 中逐 command 严格枚举字段。

### I-2: 部分章节编号和术语有小不一致

位置：DESIGN §10 重复；P0-9 §6/§5/§7 顺序；P0-2 `InsufficientResources` vs IDL `InsufficientResource`

不构成安全阻断，但会降低生成代码/测试映射的可靠性。建议在 API IDL 冻结前统一术语并由 CI 检查 docs/IDL consistency。

### I-3: `host_get_world_rules` 在 DESIGN/P0-8/P0-4 中出现但 P0-4 §3.2 漏列一次

P0-4 §8 cost table 包含 `host_get_world_rules`，但 §3.2 host function 列表只到 `host_get_world_config`。建议补齐，避免实现者遗漏或自行添加未审计 host function。

## 亮点

1. MCP 架构方向正确：MCP 是 AI 的“屏幕和鼠标”，不是 gameplay controller；不存在 `swarm_move/swarm_attack` 这类直接动作工具。这个修正消除了最核心的不公平与绕过风险。

2. 单一执行器模型清晰：所有玩家动作经 `WasmSandboxExecutor`，人类与 AI 同样写 WASM，同样 fuel metering，有利于公平性、审计和反作弊。

3. Source Gate 明确：P0-9 将 WASM/MCP/Admin/Replay/TestHarness/Tutorial/RuleMod/Simulate/DryRun 等来源显式建模，避免“某个入口顺手绕过 validator”的常见后门。

4. Deferred Command Model 是安全友好的：WASM 只返回 JSON command，mutating host function 明确禁止，状态变更集中在 validation pipeline，便于做权限、TOCTOU、replay 和审计。

5. Fuel refund 设计考虑了 anti-amplification：refund 延迟到下一 tick、设置 10% 上限、重复失败不累计、连续高 refund throttle，这些都是防滥用所必需的。

6. 可见性策略意识强：明确所有输出面（WASM snapshot、MCP、WS、REST、Replay）调用统一可见性策略，并将 debug/replay 纳入同一规则，避免“调试接口泄露”的常见漏洞。

7. WASM sandbox 基线覆盖面较完整：Wasmtime fuel、内存、WASI 禁用、seccomp、cgroup、恶意样本库、host function 成本表都有初步合同，适合作为 Phase 2 安全测试基线。

8. 确定性合同有安全价值：固定 PRNG/hash、禁 f64、IndexMap、state checksum、replay 验证，有助于发现隐藏的非确定性 bug 和作弊争议。

## 结论

我给出 CONDITIONAL_APPROVE：

- 可以进入 Phase 1/2 实现，不需要推翻架构。
- 但建议在实现前把 H-1 到 H-4 转成 P0/P1 checklist 或 blocking tests，尤其是 public MCP docs/schema rate limit、RuleMod supply-chain/capability model、simulate/dry-run leakage contract、Rollback/Admin runbook。
- M-1/M-2 应在文档冻结补丁中立即修正，因为它们是实现者最容易误读并引入安全漏洞的地方。
