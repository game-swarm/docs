# R15 API/开发者体验评审（GPT-5.5）

## Verdict

REQUEST_MAJOR_CHANGES

当前设计方向正确：MCP 不直接做游戏动作、WASM 通过 deferred command model 提交 CommandIntent、Host Function 只读、SDK 由 IDL 生成，这些都是对新用户、AI agent 和长期 API 稳定性友好的基础。但 R15 的 API 合同尚未收敛到“可实现、可生成、可教学”的程度：同一概念在多个参考文档中存在命名、数量、字段形状、限制、错误码和示例格式冲突。对 SDK/DX 来说，这会直接破坏 5 分钟上手体验，也会让 MCP tools 的 schema 与错误消息不可预测。

必须在进入实现前把 `game_api.idl` 作为唯一事实源，并让 Command、MCP、Host Function、RejectionReason、limits、examples 全部从同一 IDL/Schema 生成或显式引用；否则 TypeScript/Rust SDK、MCP schema、文档示例和引擎校验会天然分叉。

## Strengths

- MCP 边界清晰：明确禁止 `swarm_move` / `swarm_attack` / `swarm_build` 等直接游戏动作，要求 AI agent 与人类一样编写 WASM，这避免了“AI 专属遥控器”反模式。
- Deferred Command Model 直觉良好：`tick(snapshot) -> CommandIntent[]` 简单、可回放、便于 SDK 包装，也适合多语言 WASM。
- CommandIntent / RawCommand / ValidatedCommand 分层是好的 API 安全与 DX 设计：新手只需要理解 `sequence + action`，服务端注入身份和 tick，避免用户误传 `player_id` / `source`。
- Host Function 暴露面克制：只读查询函数少而明确，mutating action 不进入 host import，降低脚本 API 滥用和确定性风险。
- MCP capability profiles 是很好的 onboarding 设计：`onboarding` / `play` / `deploy` / `debug` 能让 agent 分阶段获取最小 schema，而不是一次暴露几十个工具。
- `swarm_sdk_fetch` 作为 AI agent 自举入口很强：能返回 SDK、类型定义、示例、ABI 版本和最低引擎版本，符合“5 分钟上手”的核心路径。
- 统一 JSON-RPC error envelope 的方向正确：`swarm_error`、`details`、`retry_allowed`、`idempotency_key` 对 agent 自动修复非常有价值。

## Concerns

### X1 — Critical — Command API 事实源未收敛，SDK 无法可靠生成

`design/interface.md` 声称 Command enum（core IDL，冻结）包含 `Move/Harvest/Build/Attack/RangedAttack/Heal/Spawn/Recycle/Transfer/Withdraw/ClaimController/Hack/Drain/Overload/Debilitate/Disrupt/Fortify/Leech/Fabricate/SendMessage`。但 `specs/reference/commands.md` 又称“15 Core + 1 Custom + 8 Special Attacks”，正文列出 `TransferToGlobal`、`TransferFromGlobal`，却没有完整列出 `SendMessage`；`specs/core/02-command-validation.md` 的逐指令矩阵覆盖 `ClaimController`，后面又有另一套“CommandAction 变体”示例，且格式从 `{ "sequence": 1, "action": { "type": "Move" } }` 变为 `{ "action": "RangedAttack", ... }`。

这对 SDK 是阻塞问题：TypeScript/Rust codegen 不知道应该生成 tagged union、enum+payload、CustomAction registry 还是字符串 action；AI agent 看到不同示例会生成互不兼容的 JSON。

建议：建立唯一 `CommandIntent` IDL，所有文档仅展示从 IDL 生成的 canonical examples。每个 Command 必须有稳定字段名、字段类型、required/optional、默认值、错误码、资源消耗和版本标签。

### X2 — Critical — MCP 工具要求“完整 schema”，但参考文档仍停留在目录级说明

`design/interface.md` 明确要求所有 MCP 工具具备 `inputSchema`、`outputSchema` 和 `error` schema，尤其点名 `swarm_sdk_fetch`、`swarm_get_schema`、`swarm_get_docs`、`swarm_get_player_status`、`swarm_deploy` 等工具。但 `specs/reference/mcp-tools.md` 只给出了工具表和简短说明，没有逐工具 request/response/error schema；其中 `swarm_get_player_status` 在设计要求中被点名，却未出现在工具参考目录；`swarm_sdk_fetch` 在 `design/interface.md` 有详细定义，却没有出现在 `specs/reference/mcp-tools.md` 的工具分类中。

这会严重影响 MCP DX：agent 无法知道 `swarm_deploy` 需要哪些字段、签名字段如何传、`swarm_get_schema(profile=...)` 的 profile 枚举是什么、错误 data 的结构是否稳定。

建议：为每个 MCP tool 提供机器可读 schema 与最小示例，至少覆盖 Input、Output、Error、RateLimit、ReplayClass、AuthScope、Idempotency、VisibilityPolicy。文档表格可以作为索引，但不能替代 schema。

### X3 — High — 命名风格不一致，破坏 API 可预测性

文档中同一类概念存在多套命名风格：

- Command 名称：`Spawn` vs 标题 `SpawnDrone`；`structure_type` vs `structure`；`body_parts` vs `body`；`ClaimController` 在高层表中无参数，参考示例中使用 `controller_id`。
- 方向枚举：`design/interface.md` 使用 `N/S/E/W/NE/NW/SE/SW`，`specs/core/02-command-validation.md` 写“四方向邻居 (N/S/E/W)”，示例使用 `North`。
- 资源错误：`InsufficientResources`、`InsufficientResource`、`InsufficientEnergy` 同时出现。
- 可见性错误：`TargetNotFound`、`ObjectNotFound`、`NotVisibleOrNotFound`、`TargetNotVisible` 同时出现。
- ID 类型：示例有字符串 ID（`"d1"`, `"s1"`）和数字 ID（`1001`, `42`）混用，Overload 的 `target_id` 有时是 player_id，有时示例写成实体 ID `"e5"`。

这些不是文档瑕疵，而是 SDK 合同瑕疵。新用户会从示例复制代码；AI agent 更会把示例当作 schema。命名不一致会直接变成无效 Command。

建议：采用统一命名规范，例如 command `type` 使用 PascalCase，JSON 字段使用 snake_case，body part / direction / resource 使用 PascalCase 或 SCREAMING_SNAKE_CASE 只能选一种；所有 ID 使用明确 branded 类型：`EntityId`、`PlayerId`、`StructureId`，不要统一叫 `target_id`。

### X4 — High — 限制值冲突，开发者无法判断真实预算

同一限制在不同位置冲突：

- Tick schema `maxItems: 100`，文字又说数组长度 `≤ MAX_COMMANDS_PER_PLAYER (500)`。
- `design/interface.md` 和 host-functions 参考说 tick 输出 JSON 上限 256KB；`specs/core/02-command-validation.md` §6.批级校验又写单条 ≤64KB、整批 ≤1MB。
- Host Function `host_get_objects_in_range` 在 `design/interface.md` 成本表中 max output 4KB，在 host-functions 参考只写最大 `out_len`，未复述错误码与输出 schema。
- Host call budget 同时有“总计 1000 次/tick”、“host function 不计入指令预算但计入 fuel 预算”、“call budget 独立于 WASM compute budget——两者均计入 per-tick 总量”等表述，概念边界不够清晰。

预算是 SDK 和策略代码最依赖的契约。冲突会导致玩家写出本地通过、线上失败的策略。

建议：建立 `limits` schema，由 `swarm_get_world_rules` / `swarm_get_schema` 返回，并在 SDK 中暴露为 `ctx.limits.maxCommandsPerTick`、`ctx.limits.maxTickOutputBytes` 等常量；文档不得手写重复数字。

### X5 — High — 错误模型方向正确但 taxonomy 未闭合

`SwarmError / JSON-RPC Error Envelope` 是 MCP 层错误；`RejectionReason` 是游戏指令拒绝；Host Function 返回负数错误码；Tick 输出 schema 失败又是 `TickValidationFailed`。这些层次本来合理，但目前缺少清晰映射：

- Host Function 负数错误码没有统一枚举名或 `host_last_error` / SDK exception 包装策略。
- `RejectionReason` 在 `design/interface.md` 只有 10 个，在 `commands.md` 声称 45 个但表格不完整，`02-command-validation.md` 又使用更多未统一的 `OnCooldown`、`TargetOverloadCooldown`、`TargetFortifyCooldown`、`NotStructure`、`InsufficientEnergy` 等。
- MCP `SwarmError` 分类中列 `InvalidCommand`、`InsufficientResources`、`NotAuthorized`，但 command pipeline 使用的是更细 RejectionReason；二者关系未定义。

对 AI agent 来说，错误消息是否可恢复取决于稳定 taxonomy。现在 agent 很难判断 `SchemaViolation`、`InvalidCommand`、`TickValidationFailed`、`RejectionReason` 应该如何自动修复。

建议：定义四层错误命名空间并提供转换规则：`McpError`、`TickOutputError`、`CommandRejection`、`HostError`。所有错误都必须有 stable code、human message、machine detail、retryability、visibility redaction policy。

### X6 — Medium — 5 分钟上手路径还没有端到端样例

设计中已经有 `onboarding` profile 和 `swarm_sdk_fetch`，但缺少“从零到第一个 drone 移动”的最短路径：获取 server trust、CSR、fetch SDK、生成最小 tick、validate、deploy、explain last tick。现在文档结构更像参考手册，不像新用户 quickstart。

建议补一个 SDK-first Quickstart，并保证其中所有命令都可复制运行：

1. `swarm_get_server_trust`
2. `swarm_register_challenge` + `swarm_submit_csr`
3. `swarm_sdk_fetch(language="typescript", include_examples=true)`
4. 写 `tick(snapshot) { return [move(...)] }`
5. `swarm_validate_module`
6. `swarm_deploy`
7. `swarm_explain_last_tick`

这会显著提升 AI agent 和人类新用户的成功率。

### X7 — Medium — Rhai API 在当前评审子集中几乎没有可用合同

`tech-choices.md` 说明 Rhai 是服主信任层，但白名单文档没有列出 Rhai 暴露 API、注册点、可修改对象、禁止能力、版本兼容、错误报告和测试方式。对 API/DX 来说，Rhai 现在只是技术选择，不是脚本接口设计。

建议至少定义 Rhai 的最小 public surface：`register_custom_action`、`register_special_effect`、`modify_world_rules`、`validate_config` 等是否存在；脚本拿到的是 DTO 还是 ECS handle；错误如何映射到 admin trace；哪些内部类型永远不暴露。

### X8 — Medium — `CustomAction` 与默认特殊攻击的边界不直觉

`commands.md` 说第 16 个变体 `CommandAction::Custom(type)` 路由到 8 种特殊攻击；但同一文件后续又把 `Disrupt`、`Fortify`、`Hack` 等作为 `{ "type": "Disrupt" }` 的普通 action 示例。`design/interface.md` 也把特殊攻击直接列为 Command enum 项。这会让 SDK 设计陷入两难：到底生成 `action: { type: "Custom", custom_type: "Disrupt" }`，还是生成 `action: { type: "Disrupt" }`？

建议明确：默认特殊攻击若是核心 API，就应成为一等 CommandAction；`CustomAction` 仅用于世界自定义扩展，并必须有命名空间（如 `custom:server_slug/action_name`）避免与未来核心命令冲突。

### X9 — Low — 文档表格存在格式和编号噪音，影响参考质量

`02-command-validation.md` 有多处表格行以空列开头，章节从 §3 跳到 “### 10.1”，`commands.md` 标题 `SpawnDrone` 但 JSON type 是 `Spawn`。这些看似低级，但 API 参考文档中会直接降低可信度，也会干扰 LLM 解析。

建议把 API reference 作为生成产物或至少引入 markdown/schema lint，避免参考文档漂移。

## Missing

- 缺少 `game_api.idl` 的实际 canonical 摘要或生成规则说明；当前多处写“由 IDL 生成”，但评审子集中看不到 IDL 如何约束 JSON、SDK、MCP、错误码。
- 缺少逐 MCP tool 的机器可读 `inputSchema` / `outputSchema` / `error` schema，尤其 `swarm_deploy`、`swarm_validate_module`、`swarm_get_snapshot`、`swarm_get_schema`、`swarm_get_docs`。
- 缺少 SDK API 形态：TypeScript/Rust 用户到底写 raw JSON、builder、typed command helper，还是 `ctx.move(drone, Direction.North)` 这种高阶 API。
- 缺少最小 quickstart 和完整 agent onboarding transcript。
- 缺少版本协商：`abi_version`、`min_engine_version` 出现在 `swarm_sdk_fetch`，但 Command/MCP schema 如何携带 semver、兼容策略、deprecation policy 未定义。
- 缺少 host function 输出 ABI：返回 JSON、二进制结构、长度返回策略、buffer 太小时如何发现所需长度，都未形成统一模式。
- 缺少 Rhai public API reference：脚本可用函数、数据模型、错误、权限和稳定性级别未定义。
- 缺少错误码完整列表与跨层映射表。
- 缺少 visibility redaction 对 SDK 的影响说明：哪些错误 detail 在 player trace 中隐藏，SDK 如何向用户呈现“可能不可见或不存在”。

## API Consistency Issues

- `swarm_sdk_fetch` 在设计中是关键 onboarding 工具，但 MCP reference 未列入工具目录。
- `swarm_get_player_status` 被设计要求点名必须有 schema，但 MCP reference 未列出。
- `CommandIntent[]`、`Command[]`、`RawCommand[]` 在不同文档中混用，建议对外只称 `CommandIntent[]`，服务端内部才称 `RawCommand`。
- `Command enum（core IDL，冻结）` 与 `CommandAction::Custom(type)` 的关系不清；默认特殊攻击应一等化或 custom 化，不能两者同时存在。
- `SpawnDrone` 标题与 `type: "Spawn"` 不一致。
- `body_parts`、`body` 两种字段名不一致。
- `structure_type`、`structure` 两种字段名不一致。
- `direction` 枚举有 `N/S/E/W/NE/NW/SE/SW`、`N/S/E/W`、`North` 三种表达。
- `object_id` 有时是字符串、有时是数字；需要统一 ID 编码或明确 JSON wire type。
- `target_id` 同时表示 entity id、structure id、controller id、player id；Overload 尤其需要改成 `target_player_id`。
- `InsufficientResource`、`InsufficientResources`、`InsufficientEnergy` 应收敛为一个主错误或明确层级。
- `ObjectNotFound` 与可见性优先的 `NotVisibleOrNotFound` 冲突；对玩家可见 API 应统一 opaque code，admin trace 再给 detail。
- Tick 输出 `maxItems: 100` 与 `MAX_COMMANDS_PER_PLAYER = 500` 冲突。
- Tick 输出上限 256KB 与批级校验 1MB 冲突。
- `host_get_world_config` 示例 key `world.rules.rs` 看起来像文件路径/语言后缀，命名不直觉；建议定义 key namespace，例如 `rules.max_drones_per_player`。
- `host_get_objects_in_range` 输出为“实体 JSON 列表”，但核心快照强调结构化数据非纯 JSON；Host Function 输出格式应与 SDK snapshot DTO 对齐。

## CrossCheck — 需要跨方向检查

- CX1: Command 数量、默认特殊攻击与 `CustomActionRegistry` 的边界未收敛，可能影响 ECS 调度与扩展模型 → 建议 Architect 检查核心 CommandAction 是否应冻结为一等 enum，还是保留 registry 动态派发，以及这对 replay determinism 的影响。
- CX2: Host Function buffer ABI、负数错误码和 fuel/host budget 的交互不够清楚，可能影响沙箱安全与 DoS 边界 → 建议 Security 检查 buffer 边界、错误码信息泄露、host call budget 与 wasmtime fuel 的双重扣费模型。
- CX3: 可见性优先错误策略与玩家调试体验存在张力，opaque error 可能让新手难以修复策略 → 建议 UX/Game Design 检查 player trace 是否需要提供安全的 hint，例如“目标不可操作：请确认视野或 ID”。
- CX4: MCP 认证模型声称 HTTP 等不安全传输也可完成身份认证与完整性校验，可能让开发者误解 TLS 可选性 → 建议 Security 检查文档措辞是否会鼓励明文部署，以及 CA pinning/nonce/signature 是否覆盖 replay 和 downgrade。
- CX5: Rhai 作为服主信任层但 API surface 未定义，可能导致过度暴露 ECS 内部或破坏确定性 → 建议 Architect 与 Security 共同检查 Rhai 应只操作声明式 rules/custom action DTO，还是允许更深 hook。
- CX6: `swarm_simulate` 不执行其他玩家 WASM、使用 NPC-only world，这与玩家期望的“预测未来 N tick”可能不一致 → 建议 Game Design 检查该工具命名是否应改为 `swarm_simulate_solo` 或在输出中明确 confidence/assumptions。
