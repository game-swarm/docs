# R16 API/开发者体验评审（GPT-5.5）

## Verdict

CONDITIONAL_APPROVE

R16 相比此前版本已经形成清晰的 API/DX 中心：`api-registry.md` 明确声明单一权威来源，MCP 不做游戏动作的边界被反复固定，`swarm_sdk_fetch`、capability profile、统一错误 envelope、Host Function budget/output limit、Snapshot truncation 与 Safe Hint Ladder 都显著改善了新用户、SDK 生成器和 MCP 客户端的可预期性。

但当前仍不能无条件通过：若按现有文档直接生成 SDK / MCP schema / host ABI binding，派生参考文档与 registry 之间存在多处会让开发者踩坑的残留冲突。结论是：设计方向可接受；在进入实现前必须把派生文档降级为纯引用/示例，或由 registry/IDL 自动生成，消除手写重复事实。

## Strengths

1. **单一权威来源意识已经建立**
   - `specs/reference/api-registry.md` 明确声明 CommandAction、RejectionReason、MCP Tools、Host Functions、容量限制均以 registry 为准，并要求新增项未注册则 CI 拒绝。
   - 对 SDK/DX 来说这是关键改进：SDK、MCP schema、Rhai/API 文档和错误处理可以从同一事实源生成，而不是靠人手同步。

2. **MCP 定位直觉正确**
   - `design/interface.md` 与 `mcp-tools.md` 均明确 MCP 是 AI agent 的“屏幕和鼠标”，不是 `swarm_move` / `swarm_attack` 一类动作通道。
   - 这避免了类似系统常见反模式：为 AI 玩家开一套旁路控制 API，导致公平性、权限、回放和 SDK 心智模型全部分裂。

3. **5 分钟上手路径已有雏形**
   - `swarm_sdk_fetch` 返回 SDK code、type definitions、examples、abi_version、min_engine_version，是 AI agent 和新玩家自举的正确入口。
   - capability profiles 中的 `onboarding` / `play` / `deploy` / `debug` / `admin` 把 MCP 工具体量从“46 个工具一次性砸给用户”降为分场景暴露，降低了首次接入负担。

4. **错误与提示体验开始分层**
   - JSON-RPC envelope、`retry_allowed` / idempotency 概念、Safe Hint Ladder、competitive/practice/training 三档提示，为“既不泄露隐藏状态，又能帮助新手修正错误”提供了可实现的产品模型。

5. **Host Function 暴露面克制**
   - Host Functions 只保留只读查询，mutating 操作统一走 `tick() → Command[]`，对 Rhai/SDK/WASM 都是更稳定的心智模型。
   - 每个 host function 具有预算、输出上限和 ABI 错误优先级，避免“看似只读但可被滥用成热路径 DoS”的常见 API 反模式。

6. **Snapshot / simulate / dry-run 的输出语义更清楚**
   - `truncated`、`omitted_categories`、`authoritative:false`、`not_predictive:true`、`deterministic:true` 等字段对工具链很友好；它们让 SDK 和 UI 可以给出明确状态，而不是让用户猜测返回数据是否完整/权威。

## Concerns

### X1 — High — API Registry 与派生参考文档仍存在实质冲突，破坏 SDK/codegen 可信度

`api-registry.md` 声称是单一权威来源，但多个“派生展示”文件仍手写了不一致的 API 事实。对 SDK 可用性来说，这是最高优先级 DX 问题：用户和生成器不知道该相信哪个文件。

具体例子：

- `api-registry.md` §1 定义 Core CommandAction 为 19 个：11 核心 + 2 Global + 6 特殊攻击；`Leech` / `Fabricate` 是 custom actions，非 Core enum。
- `commands.md` 同时说“19 指令”，又说“以下 15 种指令对应 enum，第 16 个 `CommandAction::Custom(type)` 路由到 8 种特殊攻击”，并继续展示 `Leech`、`Fabricate`、以及“共 11 个 special_effect handler”。这与 registry 的“6 特殊攻击 + 2 custom actions”模型不一致。
- `commands.md` 的拒绝原因列表包含 `NotMovable`、`Fatigued`、`MissingBodyPart`、`TileBlocked`、`StillSpawning`、`NotSource`、`TargetFull`、`TargetEmpty`、`NotYourRoom` 等，但 `api-registry.md` 的 35 个 RejectionReason 中没有这些变体。
- `core/02-command-validation.md` 后半段也继续使用这些未注册拒绝码，并新增 `MainActionQuotaExceeded`，但 registry 中没有。

影响：

- TypeScript/Rust SDK 的 error enum 无法稳定生成。
- MCP client 无法根据 `error.code` 做可靠分支处理。
- 文档读者会遇到“示例可编译但 schema 不承认”或“schema 承认但教程错误码不存在”的体验断层。

建议：

- 将 `commands.md` 的所有 enum、拒绝码、action 数量表改为从 registry/IDL 生成；手写部分只保留示例和解释。
- CI 检查不仅要“registry 注册完整”，还要扫描派生文档中出现的 `RejectionReason` / `CommandAction` 字面量，未注册即失败。
- 若确实需要更细粒度错误，如 `MissingBodyPart(Work)`，应在 registry 中明确为结构化 detail，而不是另起未注册 enum。

### X2 — High — Host Function ABI 在 registry 与 host-functions.md 中签名冲突

Host Function 是所有 SDK binding 的底层 ABI。这里不能有“概念签名”和“权威签名”并存而不一致。

具体例子：

- `api-registry.md` 定义 `host_get_terrain(room_id: u32, out_ptr: i32, out_len: i32) -> i32`。
- `host-functions.md` 详细签名仍写 `host_get_terrain(x: i32, y: i32) -> i32`，且描述直接返回地形类型。
- `api-registry.md` 定义 `host_path_find(..., opts_ptr, opts_len, out_ptr, out_len)`；`host-functions.md` 仍是无 opts 的旧签名。
- `api-registry.md` 定义 `host_get_world_rules(rule_id_ptr, rule_id_len, out_ptr, out_len)`；`host-functions.md` 仍是 `host_get_world_rules(out_ptr, out_len)`。
- `api-registry.md` 定义预算错误优先级 `ERR_BUDGET_EXHAUSTED = -4` 等；`host-functions.md` 写“超出预算 → 返回 -1”，而 registry 中 -1 是 memory bounds。

影响：

- Rust/TS SDK 的 WASM import declaration 会生成错误。
- 用户按参考文档手写 WASM binding 会在运行时失败。
- 错误码语义错配会让调试体验极差，尤其是 memory bounds 与 budget exhausted 混淆。

建议：

- `host-functions.md` 的签名表必须完全删除或由 registry 生成。
- 若保留教程级简写，必须明确标注“伪代码，不可作为 ABI 使用”，但最好不要在 reference 文档中这样做。
- Host Function ABI 应有独立 `host_abi_version` 与生成物校验示例，SDK 初始化时检查版本不匹配并给出 actionable error。

### X3 — Medium — MCP 工具命名和分类仍有几组旧名/新名并存

R16 已有 capability profile，但工具命名还未完全收敛，容易让 MCP 客户端和新用户困惑。

具体例子：

- `api-registry.md` 中 Deploy 类是 `swarm_get_deploy_status`、`swarm_list_deployments`，但 `design/interface.md` / `mcp-tools.md` 仍列 `swarm_rollback`、`swarm_list_modules`。
- `api-registry.md` 中 Debug 类是 `swarm_get_tick_trace`、`swarm_get_sandbox_profile`、`swarm_dry_run`；`design/interface.md` / `mcp-tools.md` 仍列 `swarm_explain_last_tick`、`swarm_profile`、`swarm_dry_run_commands`。
- `design/interface.md` onboarding profile 提到 `swarm_get_server_trust`、`swarm_register_challenge`、`swarm_submit_csr`、`swarm_get_docs`、`swarm_get_schema`，但 `api-registry.md` 的 46 工具清单没有这些认证/学习工具，反而有 `swarm_get_info`、`resources/list`、`resources/read`。
- `api-registry.md` 工具分类使用 `Onboarding` 容纳大量世界查询工具；`design/interface.md` 则把 onboarding 定义为首次接入认证+SDK+docs。两个“onboarding”含义不同。

影响：

- MCP client 的 tool discovery 无法形成直觉：用户不知道 `profile=onboarding` 到底是“新用户接入”还是“常用世界查看”。
- 文档中的“46 工具”与 interface 中的工具目录不是同一个集合，自动生成 schema 时会漏工具或多工具。

建议：

- 固定一个命名词表：`get_*` 查询，`list_*` 列表，`validate_*` 预检，`deploy_*` 变更，`admin_*` 高危管理。
- 将 profile 名称与工具分类拆开：例如分类 `WorldQuery`，profile `onboarding`，避免同词不同义。
- 给每个工具一个稳定字段：`tool_id`、`category`、`capability_profiles[]`、`replay_class`、`auth_scope`、`rate_limit`、`input_schema_ref`、`output_schema_ref`、`error_schema_ref`。

### X4 — Medium — 错误模型存在三套相近但不完全一致的表达

当前文档同时出现：

- `RejectionReason` enum；
- JSON-RPC `SwarmError` envelope；
- Safe Hint Ladder 的 `ErrorCategory` / `CommandError`；
- `design/interface.md` 中 `retry_allowed`、`idempotency_key`；
- `api-registry.md` 中 `error.code` 字符串为 `RejectionReason`，且共享 `-32000`。

这些概念本身都合理，但还缺少一张“从内部错误到外部错误”的映射表。尤其 `design/interface.md` 的示例使用 `InsufficientResources`，而 registry 明确统一为 `InsufficientResource`。

影响：

- SDK 作者不知道应该暴露 `SwarmErrorCode`、`RejectionReason`、还是 `ErrorCategory`。
- MCP 工具错误和 WASM command rejection 的 retry/idempotency 语义混在一起。

建议：

- 定义单一外部错误 envelope：`code`、`category`、`safe_message`、`hint_level`、`retry_allowed`、`idempotency_key?`、`details?`。
- 明确 `RejectionReason` 是 command rejection 的 `code` 子集；MCP/system 错误用同一 envelope 但不同 namespace，如 `Mcp.RateLimited`、`Auth.NotAuthorized`、`Command.NotOwner`。
- 统一单复数：全仓只允许 `InsufficientResource`。

### X5 — Medium — 5 分钟上手流程还缺少端到端 happy path

`swarm_sdk_fetch` 是正确方向，但文档仍没有把“新 AI agent 第一次接入”串成一个可执行路径。

一个新用户需要知道：

1. 发现服务器：调用哪个 tool？
2. 获取信任根：`swarm_get_server_trust` 还是 `swarm_get_info`？
3. 注册/CSR：哪些字段、哪些错误、PoW 怎么处理？
4. 拉 SDK：`swarm_sdk_fetch(language="typescript")`。
5. 写最小 `tick(snapshot)`。
6. validate / dry-run / deploy。
7. 查看部署状态与下一 tick 错误。

现在这些能力分散在多个文件，且工具名集合不一致。

建议：

- 增加一个 `Quickstart Contract`，不是教程正文，而是 API 层必须支持的最短链路。
- 为 MCP profile `onboarding` 明确规定“必须足以完成首次认证、SDK 获取、最小模块部署”。
- `swarm_sdk_fetch` 的 examples 应包含一个完整最小策略，并带 `validate_module` / `deploy` 调用示例。

### X6 — Low — `resources/list` / `resources/read` 使用 slash 命名，破坏 `swarm_*` 命名一致性

MCP registry 中绝大多数工具使用 `swarm_*`，但 Resources 使用 `resources/list`、`resources/read`。这更像 MCP generic resources 语义，而不是 Swarm tool 语义。

如果这是有意利用 MCP resources 机制，应在 registry 中明确它不是 tool，而是 resource endpoint；如果它是 tool，应改为 `swarm_list_resources` / `swarm_get_resource`，保持命名一致。

### X7 — Low — `api_version` 类型描述不一致

`api-registry.md` 顶部当前 API 版本是字符串 `0.1.0`，但 TickTrace Envelope 表中 `api_version` 类型是 `u32`。这会影响 SDK 版本比较与 replay 元数据解析。

建议：

- 若使用 semver，字段类型应为 string，并可另设 `api_version_major/minor/patch` 或 `schema_revision: u32`。
- 若使用整数 revision，顶部也应写 `api_revision = 1`，不要混用 semver 字符串和 u32。

## Missing

1. **机器可读 IDL 文件本体**
   - 文档多次提到 `game_api.idl → codegen → SDK`，但在本次允许阅读范围内没有看到 IDL 的字段级 schema、生成规则、版本兼容策略。API/DX 评审需要确认 IDL 是否能表达 command union、custom action、error envelope、MCP tool schema 和 host ABI。

2. **Schema 引用标识**
   - MCP tool 表现在只写 `{player_id}` 这类简写。对 MCP SDK 来说，需要每个工具引用稳定 schema id，例如 `schema://swarm/mcp/swarm_deploy.input.v1`。

3. **SDK 稳定性承诺**
   - 需要明确 TypeScript/Rust SDK 的 semver 策略：哪些变更是 patch/minor/major，SDK 如何处理 engine `abi_version` / `min_engine_version` 不兼容。

4. **错误详情尺寸与可本地化策略**
   - registry 规定 `message max 256 chars`、`rejection_detail max 512 bytes`，但 Safe Hint Ladder 中的 `fix_hint` / `debug` 未与这些限制统一。需要定义哪些字段可本地化，哪些字段必须是稳定机器码。

5. **Custom Action 的 SDK 发现机制**
   - registry 说 World Action Manifest 扩展 `custom_actions`，但 SDK 如何在运行时发现、类型化、校验这些自定义动作仍不明确。没有这个机制，modded world 的 SDK 体验会退化为手写 JSON。

6. **Rhai API 暴露清单**
   - 技术选型说明 Rhai 用于服主信任层，但本次相关文件没有给出 Rhai 可调用 API、禁止项、determinism guard、错误模型与版本策略。API/DX 角度无法确认“够用但不过度暴露内部”。

## API Consistency Issues

1. **Action 数量不一致**
   - Registry：19 指令 = 11 core + 2 global + 6 special。
   - Commands：15 enum + 1 Custom + 8 special，并包含 Leech/Fabricate Tier 2。
   - 建议：以 registry 为准，commands 只展示 registry 中的 19 个；Leech/Fabricate 放入 custom action 示例章节。

2. **RejectionReason 集合不一致**
   - Registry 35 个变体不含 `Fatigued`、`MissingBodyPart`、`TileBlocked`、`TargetFull` 等。
   - Validation/commands 大量使用这些名字。
   - 建议：要么提升进 registry，要么作为 `details.reason_detail`，不能作为外部 `code`。

3. **Host ABI 签名不一致**
   - `host_get_terrain`、`host_path_find`、`host_get_world_rules` 在 registry 与 host-functions reference 中不同。
   - 建议：reference 只引用 registry 生成签名。

4. **Host ABI 错误码不一致**
   - Registry：-1 memory bounds，-4 budget exhausted。
   - Host-functions：预算超出返回 -1。
   - 建议：预算错误统一返回 registry 的 -4/-5/-6。

5. **MCP 工具名不一致**
   - `swarm_profile` vs `swarm_get_sandbox_profile`。
   - `swarm_dry_run_commands` vs `swarm_dry_run`。
   - `swarm_explain_last_tick` vs `swarm_get_tick_trace`。
   - `swarm_list_modules` vs `swarm_list_deployments`。
   - 建议：保留一个 canonical name，旧名如需存在必须声明 alias/deprecated。

6. **Capability profile 语义不一致**
   - interface 的 `onboarding` 是首次接入；registry 的 `Onboarding` 分类包含大量世界查看工具。
   - 建议：分类与 profile 分离，profile 不应复用分类名表达不同语义。

7. **错误命名单复数不一致**
   - Registry 要求 `InsufficientResource`。
   - interface / snapshot hint ladder 仍出现 `InsufficientResources`。
   - 建议：CI 扫描禁用旧拼写。

8. **容量限制不一致**
   - Registry：tick 输出 / snapshot 等多个上限集中在全局容量表。
   - `02-command-validation.md` 同时写 tick 输出 256KB，又在批级校验写整批 ≤ 1MB；`09-snapshot-contract.md` 也使用 256KB snapshot。
   - 建议：区分 `tick_output_max_bytes`、`single_command_max_bytes`、`snapshot_max_bytes`，并全部从 Limits Manifest 引用。

9. **版本字段类型不一致**
   - `0.1.0` semver string vs TickTrace `api_version: u32`。
   - 建议：拆分 `api_semver: string` 与 `schema_revision: u32`。

## CrossCheck — 需要跨方向检查

1. **Architecture CrossCheck**
   - 请确认 `api-registry.md` 是否真的会成为 `game_api.idl` / codegen / CI 的唯一输入，而不是又多出一份 IDL 与 registry 双写。
   - 如果 IDL 才是机器事实源，registry 应改名为“generated registry view”，避免权威层级倒置。

2. **Security CrossCheck**
   - MCP profile 与 auth_scope 需要逐工具绑定，尤其 `admin`、`debug`、`deploy`、`simulate/dry_run`。当前工具表缺少 `auth_scope` 字段，难以审计权限最小化。
   - Safe Hint Ladder 与 `RejectionReason` 的 mapping 需要安全方向确认，避免 practice/training 信息通过 MCP 在 competitive world 中被越权提升。

3. **Game Design CrossCheck**
   - `Leech` / `Fabricate` 当前在 custom action、Tier 2、special_effect handler 三种语义之间摇摆。需要玩法方向确认它们是否属于 MVP core、world custom action 示例，还是 future RFC。

4. **Documentation/Tooling CrossCheck**
   - 所有派生 reference 文档应由 registry/IDL 自动生成或通过 CI 校验。否则 R16 修复只是“文档宣称单事实源”，实际仍会回到手写漂移。

5. **SDK CrossCheck**
   - `swarm_sdk_fetch` 返回的 SDK 必须包含：ABI 版本检查、schema version mismatch 的 actionable error、最小 tick 示例、error enum、tool client wrapper、dry-run/deploy helper。否则它只是代码下载接口，不足以支撑 5 分钟上手。
