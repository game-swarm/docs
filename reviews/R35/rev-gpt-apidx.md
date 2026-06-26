### 1. Verdict
REQUEST_MAJOR_CHANGES

理由：API/DX 方向仍存在多处会直接破坏 SDK codegen、MCP 工具发现、typed exception 与示例可复制性的合同漂移。尤其是 `api-registry.md` 自身的错误 envelope 双定义、MCP/Auth/Host Function 计数漂移、Host Function 签名/成本不一致，以及 `commands.md` 中多个示例字段与 CommandAction schema 冲突。这些不是实现细节，而是开发者入口文档与机器生成合同之间的阻塞级一致性问题。

### 2. 发现的问题

#### R35-API-1 — Critical
- 位置：`/tmp/swarm-review-R35/specs/reference/api-registry.md:104`、`/tmp/swarm-review-R35/specs/reference/api-registry.md:739`、`/tmp/swarm-review-R35/specs/reference/api-registry.md:749`、`/tmp/swarm-review-R35/specs/reference/api-registry.md:775`
- 问题描述：同一权威 Registry 内部定义了两套互斥的 SwarmError / JSON-RPC 错误合同。前文要求 `{ "error": { "code": "<canonical_rejection_reason_string>", ... } }`，且 SDK 从 `error.code` 生成 typed exception；后文又规定标准 JSON-RPC `error.code = -32000`，具体错误放在 `error.data.rejection_reason`，并要求 SDK 从 `rejection_reason` 生成 typed exception。
- 影响分析：TypeScript SDK 无法稳定生成异常类型与 narrowing API。IDE 自动补全、`catch (e instanceof InsufficientResourceError)`、MCP client retry policy 都会因错误字段位置不确定而分叉。对 JSON-RPC 兼容客户端而言，`error.code` 是 number 还是 string 也会直接影响协议解析。
- 修复建议：明确唯一 wire contract。建议采用标准 JSON-RPC：`error.code` 固定为 numeric range（如 `-32000`），`error.data.rejection_reason` 为 canonical enum string；SDK 只从 `error.data.rejection_reason` 生成 typed exception。删除或改写 `api-registry.md:104` 的 string-code 版本，并同步 `design/interface.md` 与派生文档。

#### R35-API-2 — Critical
- 位置：`/tmp/swarm-review-R35/specs/reference/api-registry.md:131`、`/tmp/swarm-review-R35/specs/reference/api-registry.md:135`、`/tmp/swarm-review-R35/specs/reference/api-registry.md:163`、`/tmp/swarm-review-R35/specs/reference/api-registry.md:188`、`/tmp/swarm-review-R35/specs/reference/commands.md:222`
- 问题描述：RejectionReason 计数不自洽。Registry §2.2 标题写 Validation 26 codes，但表内编号到 27（`MainActionQuotaExceeded`）；Runtime 6、MCP 3、Auth 12 后，派生文档仍写 canonical code 共 47（35 game + 12 auth）。按当前表计算 game 层至少为 36（若不计 Pipeline）或更多。
- 影响分析：typed enum 生成、错误映射测试、CI 计数 gate 与文档承诺会互相冲突。SDK 使用 exhaustive switch 时会遗漏或重复 case；MCP schema 暴露的 errors 列表也无法可信。
- 修复建议：从 IDL 重新生成并统一计数：明确 Pipeline 是否进入 canonical enum；若 `MainActionQuotaExceeded` 是正式 code，则更新所有“26/35/47”声明；若不是正式 code，则从表中移除或标注为 debug_detail。CI 应校验所有派生文档中的计数字符串。

#### R35-API-3 — High
- 位置：`/tmp/swarm-review-R35/design/interface.md:19`、`/tmp/swarm-review-R35/specs/reference/api-registry.md:268`、`/tmp/swarm-review-R35/specs/reference/api-registry.md:283`、`/tmp/swarm-review-R35/specs/reference/api-registry.md:396`、`/tmp/swarm-review-R35/specs/reference/mcp-tools.md:5`、`/tmp/swarm-review-R35/specs/reference/mcp-tools.md:17`、`/tmp/swarm-review-R35/specs/reference/mcp-tools.md:26`、`/tmp/swarm-review-R35/specs/reference/mcp-tools.md:27`、`/tmp/swarm-review-R35/specs/reference/mcp-tools.md:58`
- 问题描述：MCP/Auth 工具数量在多个入口文档中漂移。`design/interface.md` 写 57 game + 11 auth；Registry 写 game_api 57 tools、auth_api 12 tools；`mcp-tools.md` 顶部写 56 Game API active + 11 Auth API，但表格又列 Auth API 12。Onboarding 在 Registry 为 11 项（含 `swarm_get_objectives`），`mcp-tools.md` 写 10。
- 影响分析：这是 AI agent 和人类 SDK 用户最先看到的接入面。工具计数与 capability profile 漂移会导致 MCP client 能力发现、文档导航和代码生成测试不可信，尤其影响 IDE 自动补全和“工具是否存在”的判断。
- 修复建议：以 IDL/Registry 为唯一源，统一为实际 active 数量；`mcp-tools.md` 不应手写分组计数，改为引用 Registry 生成片段或只描述使用模式。若 `swarm_get_objectives` 或某些 Arena RFC 工具 gated，不应混入 active count，应拆分 `active` / `registered_but_feature_gated` 两列。

#### R35-API-4 — High
- 位置：`/tmp/swarm-review-R35/specs/reference/api-registry.md:469`、`/tmp/swarm-review-R35/specs/reference/api-registry.md:474`、`/tmp/swarm-review-R35/specs/reference/api-registry.md:501`、`/tmp/swarm-review-R35/specs/reference/api-registry.md:510`、`/tmp/swarm-review-R35/specs/reference/host-functions.md:64`、`/tmp/swarm-review-R35/specs/reference/host-functions.md:69`、`/tmp/swarm-review-R35/specs/reference/codegen.md:29`
- 问题描述：Host Function 合同漂移。Registry 有 6 个 host functions，`codegen.md` 仍写当前 5；`host_get_random` 在 Registry 为 `sequence: u64`，`host-functions.md` 为 `sequence: u32`；Registry 成本为 `200 + 10/32 bytes`，`host-functions.md` 写 `100 base + 1 per output byte`。
- 影响分析：WASM SDK 绑定会生成错误 ABI。TypeScript/Rust SDK 若按 u32 传参，而引擎按 u64 读取，会造成调用 ABI 错位或随机流 domain separation 截断。成本模型不一致会让玩家本地估算与服务端计费不同。
- 修复建议：以 Registry §4 为唯一 ABI，更新 `host-functions.md` 与 `codegen.md`；增加 CI 检查派生文档中的 host function 数量、签名和 per-call fuel 表。建议在 SDK 中暴露 `HostRandomSequence = bigint | number` 的明确 TS 类型策略，避免 JS number 精度陷阱。

#### R35-API-5 — High
- 位置：`/tmp/swarm-review-R35/specs/reference/api-registry.md:43`、`/tmp/swarm-review-R35/specs/reference/api-registry.md:45`、`/tmp/swarm-review-R35/specs/reference/api-registry.md:58`、`/tmp/swarm-review-R35/specs/reference/api-registry.md:62`、`/tmp/swarm-review-R35/specs/reference/commands.md:84`、`/tmp/swarm-review-R35/specs/reference/commands.md:93`、`/tmp/swarm-review-R35/specs/core/02-command-validation.md:259`、`/tmp/swarm-review-R35/specs/core/02-command-validation.md:260`
- 问题描述：Command 示例与权威 schema 不一致。Registry 声明所有 21 个 CommandAction 均包含公共 `object_id`，且 Spawn 的 `object_id/actor_id` 是发起 Spawn 的 drone，`spawn_id` 是目标 Spawn 结构；但 `commands.md` 的 Spawn 示例没有 `object_id`，`02-command-validation.md` 的 Spawn 示例使用 `body` 而非 Registry 的 `body_parts`。Build 在 Registry 中参数为 `structure_type`，示例使用 `structure`。
- 影响分析：示例是 SDK/DX 的事实入口。AI agent 和用户复制示例会得到 `SchemaViolation`，TypeScript SDK 的 literal types 与文档示例无法对齐，降低 IDE 补全可信度。
- 修复建议：所有示例必须由 IDL 示例块生成或由 CI schema-validate。修正 Spawn 示例为 `{ type: "Spawn", object_id, spawn_id, body_parts }`；修正 Build 示例字段为 `structure_type`；在 `commands.md` 明确公共 `object_id` 不可省略。

#### R35-API-6 — High
- 位置：`/tmp/swarm-review-R35/specs/reference/api-registry.md:83`、`/tmp/swarm-review-R35/specs/reference/api-registry.md:84`、`/tmp/swarm-review-R35/specs/reference/api-registry.md:90`、`/tmp/swarm-review-R35/specs/reference/commands.md:315`、`/tmp/swarm-review-R35/specs/reference/commands.md:819`、`/tmp/swarm-review-R35/specs/core/02-command-validation.md:315`、`/tmp/swarm-review-R35/specs/core/02-command-validation.md:819`
- 问题描述：特殊攻击参数示例与 Registry 不一致。Registry 中 `Drain` 仅列 `target_id`，但 `02-command-validation.md` 示例包含 `resource`；Registry 中 `Fabricate` 仅列 `target_id`，但示例包含 `structure_type`。这些字段是否允许并未在 canonical table 中声明。
- 影响分析：如果额外字段被 Tick 输出 Schema 的 `additionalProperties: false` 拒绝，示例会失败；如果实现接受额外字段，则 Registry 不是完整 schema。两者都会破坏 TypeScript SDK 的 discriminated union 生成。
- 修复建议：将每个 special attack 的完整参数纳入 IDL/Registry（包括可选字段、默认值、是否 required），并由 canonical table 只引用而不另写字段。若 `Drain.resource` 与 `Fabricate.structure_type` 是设计目标，应加入 Registry；若不是，应删除示例字段。

#### R35-API-7 — High
- 位置：`/tmp/swarm-review-R35/specs/reference/rhai-mod-abi.md:28`、`/tmp/swarm-review-R35/specs/reference/rhai-mod-abi.md:31`、`/tmp/swarm-review-R35/specs/reference/rhai-mod-abi.md:123`、`/tmp/swarm-review-R35/specs/reference/rhai-mod-abi.md:139`、`/tmp/swarm-review-R35/specs/reference/rhai-mod-abi.md:153`、`/tmp/swarm-review-R35/specs/reference/rhai-mod-abi.md:155`、`/tmp/swarm-review-R35/specs/reference/rhai-mod-abi.md:312`
- 问题描述：Rhai ABI 的 capability 模型自相矛盾。前文承诺 Rhai 不能直接写 ECS，只能通过 `actions.*` API；后文又引入 `direct_ecs_writer` capability 允许绕过 `RhaiActionBuffer` 直接写 ECS。Capability 表实际列出 13 项，但实现清单写 12 项。
- 影响分析：模组开发者无法判断“直接写 ECS”是禁止能力、特殊能力还是正式 ABI。SDK/CLI 生成 `mod.toml` schema 时也会在 capability enum 数量和安全等级上漂移。
- 修复建议：若 `direct_ecs_writer` 是目标设计的一部分，应在隔离保证中改为“默认禁止；仅 direct_ecs_writer capability 例外，且受 unique writer gate 约束”，并更新实现清单为 13。若不是目标设计，应移除该 capability。无论哪种，都需要在 `actions.*` 与 direct writer 间明确 replay/audit/error contract。

#### R35-API-8 — Medium
- 位置：`/tmp/swarm-review-R35/specs/reference/rhai-mod-abi.md:109`、`/tmp/swarm-review-R35/specs/reference/rhai-mod-abi.md:111`、`/tmp/swarm-review-R35/specs/reference/rhai-mod-abi.md:204`、`/tmp/swarm-review-R35/specs/reference/rhai-mod-abi.md:210`、`/tmp/swarm-review-R35/specs/reference/rhai-mod-abi.md:211`
- 问题描述：Rhai `actions.*` API 缺少可操作的返回类型与错误类型合同。表格描述能力/禁止项，但没有定义函数返回 `Result`、错误码枚举、错误消息模板、是否可恢复、是否进入 `RhaiActionBuffer`。
- 影响分析：模组作者无法写出类型安全/可诊断脚本，IDE 也无法提供精确补全。比如 `actions.deduct()` 在资源不足时是返回 false、抛 panic、跳过 action 还是让整个 buffer 丢弃，当前仅在错误层次表用自然语言描述。
- 修复建议：为 `query.*` / `actions.*` 增加 Rhai API schema 表：参数类型、返回类型、错误枚举、side-effect class、buffer 行为。建议统一为 `Result<T, RhaiActionError>`，并列出 `BudgetExceeded`、`CapabilityDenied`、`InvalidResource`、`WouldGoNegative`、`ImmutableParam` 等 canonical 错误。

#### R35-API-9 — Medium
- 位置：`/tmp/swarm-review-R35/specs/reference/mcp-tools.md:78`、`/tmp/swarm-review-R35/specs/reference/mcp-tools.md:82`、`/tmp/swarm-review-R35/specs/reference/mcp-tools.md:87`、`/tmp/swarm-review-R35/specs/reference/api-registry.md:270`、`/tmp/swarm-review-R35/specs/reference/api-registry.md:274`
- 问题描述：`mcp-tools.md` 的 Rate Limiter 表继续给出 source-level tokens/s，并写 Admin 无限制；Registry 则定义 per-tool rate limit，Admin 为 10/h 或 30/tick 等有明确限制。虽然 `mcp-tools.md` 标注“参考，以 registry 为准”，但数值表达仍会误导 SDK/MCP client 的 backoff 策略。
- 影响分析：开发者会按错误预算设计客户端节流，导致生产环境频繁 `RateLimited` 或错误地认为 admin 工具无限制。
- 修复建议：删除手写 tokens/s 表，改为只解释限流维度和如何读取 Registry 列；或将该表标为“legacy source classes，不用于客户端预算”。

#### R35-API-10 — Medium
- 位置：`/tmp/swarm-review-R35/specs/reference/codegen.md:13`、`/tmp/swarm-review-R35/specs/reference/codegen.md:16`、`/tmp/swarm-review-R35/specs/reference/codegen.md:24`、`/tmp/swarm-review-R35/specs/reference/codegen.md:26`、`/tmp/swarm-review-R35/specs/reference/codegen.md:29`、`/tmp/swarm-review-R35/specs/reference/api-registry.md:262`、`/tmp/swarm-review-R35/specs/reference/api-registry.md:396`
- 问题描述：Codegen 文档本身承认手工维护计数，并且已经与 Registry 漂移：MCP tools 当前 56 active、Host function 5；Auth API 输出映射写到 Registry §6-9，但 Auth 工具实际在 §3.3。
- 影响分析：codegen 是 API/DX 的基础设施说明，若它本身是手工漂移源，无法作为 CI 规则或开发者调试依据。
- 修复建议：将 `codegen.md` 也纳入 generator 或拆成“无计数、无 section number”的稳定规范。所有计数从 IDL 输出，文档只保留命令、不可手写区域和 CI 失败语义。

#### R35-API-11 — Low
- 位置：`/tmp/swarm-review-R35/specs/core/09-snapshot-contract.md:5`、`/tmp/swarm-review-R35/specs/core/09-snapshot-contract.md:423`、`/tmp/swarm-review-R35/specs/core/09-snapshot-contract.md:428`
- 问题描述：Snapshot Contract 仍含 “MVP” 与“可能增加/可能放宽”的迁移式表述，与本轮评审原则“设计文档呈现目标状态，不是阶段路线图”不一致。
- 影响分析：对 API/DX 来说，这会让 `swarm_simulate`、snapshot truncation、Allied Transfer 的客户端合同看起来像阶段性承诺，而非当前目标状态。
- 修复建议：删除 MVP/Extension 叙事，改为目标状态合同；未来扩展用 RFC 标记，不放入当前 API 行为表。

### 3. 亮点

- Registry 明确声明 IDL 为唯一机器源，并将 CommandAction、RejectionReason、MCP Tools、Host Functions、容量限制集中到一个开发者入口，方向正确。
- `CommandIntent → RawCommand → ValidatedCommand` 的三层模型清晰，服务端注入 `player_id/source/tick` 的边界对 SDK 安全封装很友好。
- `SwarmError` 已包含 `retry_allowed`、`idempotency_key`、`retry_after_tick` 等机器可读字段，这是优秀的客户端重试 DX 设计。
- MCP capability profiles（onboarding/play/deploy/debug/admin/arena）能显著改善 AI agent 首次接入体验，避免一次暴露全部工具。
- Snapshot truncation 显式提供 `truncated` 与 `omitted_categories`，对 IDE/agent 解释“为什么看不到对象”很有帮助。
- Rhai ABI 将 `query.*` 与 `actions.*` 命名空间分离，且引入 capability default-deny，模组 API 的心智模型总体清楚。
- Fixed-point type registry 对 TypeScript/Rust SDK 都非常友好，避免 `f64` 造成 deterministic replay 与跨语言序列化问题。

### 4. CrossCheck

- CX1: `direct_ecs_writer` 与“Rhai 不能直接写 ECS”的安全边界冲突 → 建议 Security/Determinism 检查 capability 例外是否会破坏 replay、unique writer 与审计完整性。
- CX2: `swarm_get_terrain` / `swarm_get_path` 在 MCP 工具表中标为 host fn only，却仍列在 Game API Play 工具清单中 → 建议 MCP/Security 检查这些条目是否应暴露给 MCP client，还是仅作为 WASM host import。
- CX3: Snapshot Contract 中 `swarm_dry_run` 可传入 `hint_level` 覆盖世界默认值，且写“仅限训练模式提升，不允许降级”语义不清 → 建议 Security 检查是否允许客户端把 practice/competitive 提升到 training，从而泄露隐藏状态。
- CX4: `api-registry.md` 中 Auth 层与 MCP/Game 层复用 `InvalidCertificate`、`NotAuthorized`、`RateLimited` 名称 → 建议 Auth/Security 检查是否需要命名空间化 wire enum，避免审计日志和 SDK typed exception 混淆。
- CX5: `commands.md` / validation spec 中特殊攻击状态机仍引用未授权读取范围外的 system manifest 作为唯一权威 → 建议 Engine/Determinism 方向检查 special attack reducer 的优先级是否已与 API 表和 TickTrace hash 对齐。
