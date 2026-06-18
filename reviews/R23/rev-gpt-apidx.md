# R23 API/DX Review — GPT-5.5

## Verdict

CONDITIONAL_APPROVE

整体方向正确：IDL → Registry → SDK/docs 的单事实源、MCP 不直接执行游戏动作、只读 host function、能力分组与统一错误 envelope，都是对 SDK 可用性和长期 API 治理很有价值的设计。当前主要问题不是理念，而是公开文档之间存在多处会直接误导 SDK/codegen/MCP 客户端实现者的 schema、计数、命名和错误模型漂移；若不修正，会让新用户无法在 5 分钟内可靠上手，也会让自动生成 SDK 的类型合同不可信。

## Strengths

- 单事实源意识强：`api-registry.md` 明确由 `game_api.idl.yaml`、`auth_api.idl.yaml`、`economy.idl.yaml` 生成，并把 CommandAction、RejectionReason、MCP Tools、Host Functions、容量限制集中到一个权威入口。
- MCP 产品边界清晰：反复强调 MCP 是 AI agent 的“屏幕和鼠标”，不暴露 `swarm_move` / `swarm_attack` 等动作工具，避免 AI 玩家绕过 WASM 公平路径。
- Onboarding 体验有雏形：`swarm_get_info`、`swarm_get_docs`、`swarm_get_schema`、`swarm_sdk_fetch` 组合能支持 agent 自举，能力面比传统只给 OpenAPI/README 更友好。
- Capability Profiles 有利于 DX：`onboarding` / `play` / `deploy` / `debug` / `admin` / `arena` 分组符合 MCP 客户端渐进授权与工具发现模式，降低首次暴露的工具噪音。
- 错误分层方向正确：canonical wire code + `debug_detail` / hint ladder 的思路兼顾稳定 enum、竞技安全和训练模式可诊断性。
- Host function 暴露克制：只读查询、统一 `i32` ABI、预算和输出上限明确，避免把内部 ECS 或 mutating 能力过度泄露给脚本。

## Concerns

### X1 — High — 权威 Registry 自身与派生文档的数量/版本声明不一致

`api-registry.md` §3 写“54 个活跃工具 + 11 个 Auth API 工具”，但 `mcp-tools.md`、`design/interface.md`、Registry changelog 又写 56 game tools / 56 active。`codegen.md` 还声明 CommandAction 当前 19、RejectionReason 当前 79，而 Registry 正文是 21 CommandAction、47 canonical codes。对 SDK/codegen 来说，数量是最容易被 CI 和用户校验的事实；这些数字不一致会直接破坏“Registry 是权威事实源”的可信度。

建议：把所有手写数量改成由 codegen 注入的变量，或在派生文档只写“以 Registry §X 为准”而不重复数字；`codegen.md` 的禁止手写数值清单必须同步到 Registry 0.4.0 的实际值。

### X2 — High — Host function 签名在多个文档中冲突，SDK ABI 无法稳定生成

`api-registry.md` §4.1 定义 `host_get_terrain(room_id, out_ptr, out_len)`，但 `host-functions.md` 写 `host_get_terrain(x, y) -> i32`；Registry 的 `host_path_find` 含 `opts_ptr/opts_len`，参考文档与 `design/interface.md` 的概念签名都没有 opts；Registry 的 `host_get_world_rules(rule_id_ptr, rule_id_len, out_ptr, out_len)`，参考文档写无参数版本。ABI 是 SDK 最硬的契约，示例和权威表冲突会导致 TS/Rust SDK、WASM import stub、用户手写 C ABI 全部出现分叉。

建议：`host-functions.md` 不应重写“详细签名”，而应从 IDL 生成；若保留讲解文档，代码块必须逐字匹配 Registry，并补充每个函数的 typed SDK wrapper 示例。

### X3 — High — Command schema 示例与 Registry 参数表不一致

Registry §1 的 `Move` 参数只列 `direction: Direction4`，但 `commands.md` 示例和校验文档需要 `object_id`；Registry `Build` 参数写 `structure_type`，示例写 `structure`；Registry `Recycle` 参数是 `target_id`，校验文档又出现 `spawn_id` 和无 target 形式；`Spawn` 示例有 `body_parts` / `body` 两种字段。玩家和 AI agent 通常会复制示例起步，字段名漂移会让“5 分钟上手”失败。

建议：CommandAction 的每个变体应拥有唯一 canonical JSON shape，示例必须由同一个 IDL schema 生成；如果 `object_id` 是通用 command envelope 字段，不应在 action 参数表中省略到令人误解，而应明确“CommandIntent = {sequence, object_id, action}”或“每个 action 内含 object_id”。

### X4 — High — 错误码模型混用 JSON-RPC 数字 code 与字符串 code

`design/interface.md` §5.6 示例使用 `error.code: -32000` 且 `data.swarm_error` 承载业务错误；`api-registry.md` §8 又使用 `error.code: "RejectionReason (string)"`，并说 `-32000` 仅保留给未分类内部错误。MCP/JSON-RPC 客户端对 `error.code` 的类型和语义非常敏感，数字/字符串混用会让客户端错误处理、重试策略、遥测聚合都变复杂。

建议：统一为标准 JSON-RPC 数字 `error.code` + `data.swarm_error` 字符串，或明确采用 MCP extension 字符串 code，但不能两套并存；同时给出 `RateLimited`、`InvalidCertificate`、`InsufficientResource` 的完整错误样例。

### X5 — Medium — Auth 工具存在 game_api 简化形态与 auth_api 完整形态的同名双 schema

Registry 同时列出 `swarm_auth_login` / `swarm_auth_refresh` 的 game_api 简化 schema 和 auth_api 完整 schema。虽然有注释说明完整 schema 见 Auth API，但对 MCP 工具发现而言，同名 tool 不应存在两个不同 input schema，否则客户端无法知道实际注册的是哪一个版本。

建议：保留一个 canonical MCP tool schema；如果需要兼容简化形态，应通过 optional fields、profile-specific docs 或 alias（如 `swarm_auth_login_basic`）表达，而不是同名双定义。

### X6 — Medium — `resources/list` / `resources/read` 命名破坏 `swarm_*` 工具命名一致性

绝大多数 MCP 工具使用 `swarm_verb_object` 命名，唯独 Resources 使用 slash-style `resources/list`、`resources/read`。这像 MCP resource URI，又被放在 tools 表中，会让工具发现、权限匹配、SDK method naming 出现特殊分支。

建议：若它们是 MCP resources，就移出 tools 表并按 MCP resources 语义定义；若它们是 tools，改为 `swarm_list_resources` / `swarm_get_resource`，保持可预测命名。

### X7 — Medium — `swarm_simulate` / `swarm_dry_run` 的产品语义和 schema 不够一致

`design/interface.md` 说 `swarm_simulate` 输入 `{commands, assumptions}`，`snapshot-contract.md` 又描述 `swarm_simulate(world_state, drone_id, action)`；`api-registry.md` 输出 `{trace, authoritative:false, assumptions, confidence}`，Snapshot Contract 要求 `not_predictive`, `rng_ordinals_consumed`, `fuel_consumed`, `tick_trace_written`。这些工具是 AI agent 调试体验核心，若 schema 不稳定，会导致 agent 错把 preview 当承诺或无法展示风险提示。

建议：为 simulate/dry-run 单独生成一个完整 schema section，强制包含 `authoritative:false`、`not_predictive:true`、`deterministic`（dry-run）等字段，并给出“不能用于竞技承诺”的标准 UI/agent 文案。

### X8 — Medium — RejectionReason 命名规范仍有旧码残留，削弱错误消息可预测性

Registry 命名规范已废弃 `InsufficientResources`、`TargetNotFound` 等旧码，但 `snapshot-contract.md` hint ladder 仍写 `InsufficientResources` / `PermissionDenied` / `InvalidTarget`，`02-command-validation.md` 表中仍出现 `TileBlocked`、`StillSpawning`、`ExceedsRoomCapacity`、`InvalidDamageType`、`AlreadyDebilitated`、`MainActionQuotaExceeded` 等非 canonical 名称。即使部分标为 debug detail，表格“失败码”列会诱导实现者把它们当 wire enum。

建议：所有非 canonical 条目统一写成 `debug_detail=<name>` 或 `category=<name>`，不要放在“失败码”列；hint ladder 的类别必须映射到 Registry §2 的 canonical codes。

### X9 — Medium — 5 分钟上手路径还缺少端到端 happy path

现有文档有 `swarm_sdk_fetch` 和部署工具清单，但没有一个“新 AI agent 从空白到部署第一个 drone”的最小流程：认证、拉 SDK、读取 schema、生成代码、validate、deploy、查看 status、解释 last tick。工具很多但缺少串联，首次接入者仍要在多个参考文档中拼图。

建议：新增 Quickstart，并确保每一步都是 Registry 中真实存在的 tool 和字段；同时给出 TypeScript 与 Rust 最小 `tick(snapshot)` 示例。

### X10 — Low — Rhai API 的服主脚本接口在所读 API/DX 子集中几乎不可见

技术选型说明选择 Rhai，但 API Registry / reference 文档没有给出 rule mod 脚本能调用哪些稳定接口、哪些内部 ECS 类型被隐藏、错误如何返回、版本如何兼容。作为“够用但不过度暴露内部”的脚本 API，目前缺少 DX 合同。

建议：增加 `rhai-api.md` 或在 Registry 中为 mod host API 建立单独 section，定义最小能力面、稳定版本、示例和禁止访问的内部状态。

## Missing

- 缺少 “Hello Swarm” Quickstart：从 `swarm_get_info` / auth / `swarm_sdk_fetch` 到 `swarm_validate_module` / `swarm_deploy` / `swarm_explain_last_tick` 的端到端 5 分钟路径。
- 缺少 generated SDK API surface 示例：例如 TS `client.deploy(...)`、Rust `swarm_sdk::tick(...)`、host function wrapper 的命名和错误类型映射。
- 缺少 MCP tool discovery 的实际 JSON Schema 示例：当前表格只写 `{field}` 简写，不足以让客户端生成强类型和表单。
- 缺少错误 envelope 的完整矩阵：JSON-RPC numeric code、canonical SwarmError、retry policy、hint level、redaction behavior 应在同一处定义。
- 缺少 IDL 兼容性策略：字段新增/删除、enum 扩展、deprecated alias、SDK semver、min_engine_version 如何联动尚不够明确。
- 缺少 Rhai mod API 参考：服主脚本接口、稳定边界、可调用 host services、禁止访问的内部 ECS 细节都未形成 API/DX 文档。

## API Consistency Issues

- 工具数量：`api-registry.md` 正文 54 active、`mcp-tools.md` 56、`interface.md` 56 game + 11 auth、changelog 56 active，必须统一。
- Command 数量：Registry 21，`codegen.md` 禁止手写清单写 19，必须统一。
- RejectionReason 数量：Registry 47 canonical，`codegen.md` 写 79，必须统一或解释 79 是否包含非 wire category。
- Host ABI：`host_get_terrain`、`host_path_find`、`host_get_world_rules` 在 Registry、interface、host-functions 三处签名不同。
- Command 字段：`body_parts` vs `body`、`structure_type` vs `structure`、`target_id` vs `spawn_id`、action 参数是否包含 `object_id` 没有统一。
- 错误 envelope：`error.code=-32000 + data.swarm_error` 与 `error.code="RejectionReason"` 两种模型冲突。
- Auth schema：`swarm_auth_login` / `swarm_auth_refresh` 同名双 schema 影响 MCP tool registry 的唯一性。
- 命名风格：`resources/list`、`resources/read` 与 `swarm_*` tool 命名体系不一致。
- 错误命名：旧码和非 canonical debug names 仍出现在“失败码/错误类别”位置，应从 wire enum 语境中移除。
- Rate limit：Registry 以 per-tool/per-category 表为准，`mcp-tools.md` 又给 source-level tokens/s 表，单位和层级不同，需明确哪个用于实现、哪个仅为说明。

## CrossCheck — 需要跨方向检查

- CX1: IDL/codegen 是否真的能覆盖所有 Registry、SDK、reference 文档并阻止上述漂移 → 建议 Architect 检查生成链边界、CI diff gate、派生文档不可手写区域设计。
- CX2: JSON-RPC/MCP 错误 envelope 与 hint ladder 可能在竞技模式泄露隐藏状态，且 `error.code` 语义不稳定 → 建议 Security 检查 redaction、oracle inference、客户端重试策略和审计日志分层。
- CX3: `swarm_auth_login` 同名双 schema 与证书/JWT/refresh token 并存可能扩大认证状态机复杂度 → 建议 Security 检查 auth tool registry 的唯一 schema、scope、session/device 绑定与 replay 行为。
- CX4: simulate/dry-run 的隔离字段、RNG namespace、cache/fuel accounting 与实际引擎 replay 合同耦合较深 → 建议 Architect 检查这些输出字段是否进入 TickTrace 或 replay-critical envelope。
- CX5: Rhai mod API 未在 API 参考中定义，可能导致服主脚本直接依赖内部 ECS/engine 类型 → 建议 Architect 检查 mod API 的稳定边界与版本策略。
