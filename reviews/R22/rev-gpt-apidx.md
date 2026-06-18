# R22 API/开发者体验评审 (GPT-5.5 / apidx)

## Verdict

REQUEST_MAJOR_CHANGES

当前方向在“IDL 作为单一事实源”“MCP 不直接执行游戏动作”“WASM deferred command model”“错误提示按模式分级”等核心原则上是正确的，且已经具备成为优秀 SDK/API 体系的基础。但从 API/DX 角度看，当前文档状态还不能批准：权威 IDL、生成 registry、派生参考文档之间存在多处可由新用户直接复制的 schema/命名漂移；这些不是实现细节，而会导致 SDK codegen、MCP tool discovery、教程示例和 WASM host ABI 绑定生成出互不兼容的接口。

最严重的问题集中在：CommandAction 数量与参数形状不一致、host function 签名漂移、MCP 工具计数与命名空间混用、Auth 简化 schema 与完整 schema 并存但没有清晰 deprecation/alias 策略、错误 envelope 设计在 JSON-RPC 标准与 Swarm canonical code 之间表述冲突。建议在进入实现前先完成一次“API surface freeze”：以 IDL 为源重生成所有 reference 文档，并用 CI 阻止派生文档继续手写漂移。

## Strengths

1. 单一事实源方向正确：`api-registry.md` 明确声明由 `game_api.idl.yaml`、`auth_api.idl.yaml`、`economy.idl.yaml` 生成，且冲突时以 IDL 为准。这是多语言 SDK、MCP schema 和参考文档保持一致的正确基础。

2. API 分层边界清晰：MCP 明确不暴露 `swarm_move` / `swarm_attack` / `swarm_build` / `swarm_spawn` 等游戏动作，AI agent 必须与人类一样编写 WASM。这避免了“AI 有旁路控制 API”的长期公平性和 DX 双重风险。

3. Deferred command model 对 SDK 友好：`tick(snapshot) -> CommandIntent[]` 模型比 OOP 即时 mutation 更容易做确定性回放、离线 dry-run、语言无关 codegen，也更适合 TypeScript/Rust SDK 生成强类型 command builder。

4. capability profiles 是好设计：`onboarding` / `play` / `deploy` / `debug` / `admin` / `arena` 的工具分组有助于 MCP 客户端逐步暴露能力，降低新 agent 首次接入时的工具噪声。

5. 错误信息分级有明显 DX 价值：`competitive` / `practice` / `training` 的 `detail_level` 与 `debug_detail` 思路能兼顾竞技防泄漏和开发调试体验。

6. 固定点数值类型选择正确：将 economy/API 中的比例、资源率、距离和成本统一为 fixed-point integer，显著降低 SDK 跨语言行为差异。

## Concerns

### X1 — Critical — 权威 IDL、Registry 与派生参考文档存在可破坏 SDK codegen 的 schema 漂移

证据：
- `game_api.idl.yaml` 中 `command_action.total_variants: 19`，特殊攻击 active 只有 6 个；`Leech` / `Fabricate` 位于 `custom_actions.known`，不是 core enum。
- `api-registry.md` §1 却写“变体总数 21”，并将 `Leech` / `Fabricate` 列为 #20/#21 Tier 2 特性。
- `commands.md` 也写“21 指令（11核心+2Global+8特殊）”，并给出 `Leech` / `Fabricate` 的 Command 示例。

DX 影响：
- SDK 生成器若以 IDL 生成，会只生成 19 个 core action；开发者若按 Markdown 示例写 `Leech` / `Fabricate`，会得到 UnknownAction 或自定义 manifest 缺失错误。
- MCP/SDK 文档若公开“21 指令”，新用户无法判断哪些是稳定 ABI、哪些是 world manifest custom action。
- `CommandAction::Custom(type)` 与“在 core enum 中注册 Tier 2”是两种不同扩展模型，不能同时存在。

要求变更：
- 明确三层：core action、vanilla bundled custom action、third-party custom action。
- Registry 中不得把 custom action 计入 core `CommandAction` 变体总数；如需展示 vanilla custom action，放到单独 `VanillaCustomActions` 表。
- 所有 SDK command builder 应明确区分 `commands.move(...)` 与 `commands.custom("Leech", payload)` 或生成 `vanilla.leech(...)` namespace。

### X2 — Critical — Host function ABI 在三个位置互相冲突，WASM SDK 绑定无法安全生成

证据：
- `api-registry.md` / `game_api.idl.yaml` 权威签名：`host_get_terrain(room_id: u32, out_ptr: i32, out_len: i32) -> i32`。
- `design/interface.md` 概念签名：`host_get_terrain(x: i32, y: i32) -> i32`。
- `host-functions.md` 详细签名仍写：`i32 host_get_terrain(x: i32, y: i32) -> i32`，且没有 `out_ptr/out_len`。
- `host_path_find` 在 IDL 中有 `opts_ptr/opts_len`，但 `host-functions.md` 只写 `(from_x, from_y, to_x, to_y, out_ptr, out_len)`。
- `host_get_world_rules` 在 IDL 中需要 `rule_id_ptr/rule_id_len`，但 `host-functions.md` 写无输入 key 的 `(out_ptr, out_len)`。

DX 影响：
- Rust/TS SDK 的 WASM import declarations 会生成错误 ABI，运行时表现为 memory corruption、ERR_ABI_VERSION 或难以理解的负数错误码。
- 对新手最关键的“5 分钟上手”会失败，因为 host function 示例无法直接复制。

要求变更：
- `host-functions.md` 必须完全由 IDL 生成或至少嵌入生成片段。
- 所有概念签名必须标注“非 ABI，不可复制”，并链接权威 ABI。
- 增加每个 host function 的 C/Rust/AssemblyScript 绑定示例，并带 ABI version 检查。

### X3 — High — MCP tool 数量、分类和命名空间不一致，影响 tool discovery 与 capability profile

证据：
- `design/interface.md` §4.1 写“56 game tools + 11 auth tools”。
- `api-registry.md` §3 开头写“54 个活跃工具 (game_api) + 11 个 Auth API 工具”，但表格和 changelog 又写 56 active。
- `game_api.idl.yaml` 注释仍写 “MCP Tools — 46 tools”，实际 `total_tools: 56`。
- `api-registry.md` Game API 工具中包含 `resources/list` / `resources/read`，它们不使用 `swarm_` 前缀；其余工具几乎全部是 `swarm_*`。

DX 影响：
- MCP 客户端按 capability profile 做工具过滤时，无法确信数量是否正确。
- `resources/list` 和 `resources/read` 的 slash namespace 与 `swarm_*` 风格混用，会让用户不清楚这是 MCP resources 规范、REST-like path，还是 Swarm tool 名。
- 文档里“host fn only”的 `swarm_get_terrain` / `swarm_get_path` 出现在 MCP Tools 表中，会误导 agent 以为这是可调用 MCP tool。

要求变更：
- 将 active MCP tools、host-only pseudo-tools、MCP resources 分成三个完全独立 registry。
- 如果采用 MCP resource URI 风格，应命名为 resource endpoints，不计入 tools 总数；如果是 tools，应统一为 `swarm_resources_list` / `swarm_resources_read`。
- CI 校验 `total_tools` 与实际列表数量、分类小计、文档小计完全一致。

### X4 — High — Auth 简化 schema 与完整 Auth API schema 重名，缺少兼容策略

证据：
- `game_api.idl.yaml` 中 `swarm_auth_login` 输入为 `{credential, challenge_response}`，输出无 `refresh_token` / `session_id`。
- `auth_api.idl.yaml` 中同名 `swarm_auth_login` 输入为 `{credential, challenge_response, device_id, device_name}`，输出含 `refresh_token` / `session_id`。
- `api-registry.md` 说明 game_api 是简化形态，但仍将同名工具列入 Game API Auth 分类。
- `auth_api.idl.yaml` refresh 描述说“每次 successful refresh also issues a new refresh token”，但输出 schema 只有 `{token, expiry}`，没有 `refresh_token`。

DX 影响：
- MCP tool discovery 中不能存在两个同名但 schema 不同的 tool；多数客户端只会保留一个，或后注册覆盖前注册。
- 新手不知道调用 `swarm_auth_refresh` 应传 `token` 还是 `refresh_token`。
- SDK 类型无法同时表达同名不同 schema，除非引入版本 namespace。

要求变更：
- 只保留一个 canonical auth tool namespace；建议以 `auth_api.idl.yaml` 为准。
- 若需要兼容简化形态，使用显式 alias，如 `swarm_auth_login_basic`，并标注 deprecated / onboarding-only。
- 修复 `swarm_auth_refresh` 输出，若采用 refresh token rotation，则输出必须包含 `refresh_token` 或 `next_refresh_token`。

### X5 — High — CommandIntent 参数形状不完整且示例与 IDL 冲突，SDK 使用者无法构造合法命令

证据：
- `game_api.idl.yaml` 的 `Move` 参数只列 `direction`，未列 `object_id`；`Build` 只列 `structure_type/x/y`，未列执行者 drone；多个 action 均缺少 `object_id`。
- `commands.md` 示例却普遍使用 `object_id`。
- `commands.md` `Build` 示例字段为 `structure: "Extension"`，IDL 参数名为 `structure_type`。
- `commands.md` `Spawn` 示例字段 `body_parts`，`02-command-validation.md` §3.8 示例使用 `body`。
- `Recycle` 在 IDL 中参数是 `target_id`，`02-command-validation.md` §3.9 使用 `spawn_id`，`commands.md` 同时出现 `object_id` 和 `target_id`。

DX 影响：
- 一个玩家无法仅凭 IDL 生成可用 SDK，因为缺少 action actor/source 字段模型。
- 派生示例不可复制，初学者会在第一个 tick 输出就被 schema 拒绝。

要求变更：
- 明确 CommandIntent 的通用 envelope 是否包含 `object_id`：如果每条 action 都由 drone 执行，建议 `CommandIntent = { sequence, object_id, action }`；如果 action 内部携带 actor，则所有 action 参数都必须在 IDL 中列出。
- 派生文档必须从同一个 command schema 生成示例，禁止手写字段名。
- 为每条 action 增加 canonical JSON schema、最小合法示例、常见 rejection 示例。

### X6 — Medium — JSON-RPC 错误 envelope 表述不标准，且内部前后不一致

证据：
- `design/interface.md` §5.6 示例中 JSON-RPC `error.code` 是 `-32000`，具体 canonical code 在 `data.swarm_error`。
- `api-registry.md` §8 示例中 `error.code` 是字符串 `"RejectionReason (string)"`，同时又写“MCP 共享错误码 `-32000` 保留给未分类内部错误”。

DX 影响：
- JSON-RPC 2.0 标准要求 `error.code` 是 integer；把 RejectionReason string 放入 `error.code` 会破坏通用 JSON-RPC 客户端兼容性。
- SDK 无法生成稳定错误类型：是检查 `error.code`、`data.swarm_error`，还是 `data.rejection_detail`？

要求变更：
- 采用标准 JSON-RPC：`error.code` 为整数，`error.data.swarm_code` / `error.data.rejection_reason` 为 canonical string。
- 定义稳定的 numeric mapping：validation -32xxx、auth -33xxx 等；或全部用固定 `-32000` + data code，但必须唯一。
- 增加 typed SDK error hierarchy：`SwarmError.code`, `SwarmError.reason`, `retry_allowed`, `idempotency_key`, `debug_detail`。

### X7 — Medium — fixed-point 类型命名不统一，降低 SDK 直觉性

证据：
- `game_api.idl.yaml` 中存在 `ResourceRate_i64`, `ProgressBps_i64`, `BasisPoints`, `EfficiencyBps`, `ConfidenceBps`, `milli_distance`, `micro_cost`。
- 同一个 registry 同时使用 PascalCase、snake_case，以及在名称中编码底层类型 `_i64`。

DX 影响：
- 生成 TypeScript/Rust SDK 时会出现风格不一致的类型名，如 `ResourceRate_i64` 与 `micro_cost`。
- `_i64` 暴露底层实现细节；一旦底层类型变更，API 名称也被迫破坏。

要求变更：
- 统一类型命名风格，建议 PascalCase：`ResourceRate`, `ProgressBps`, `MilliDistance`, `MicroCost`。
- 底层类型放在 schema metadata，不放在 public type name。
- 每个 fixed-point 类型提供 `scale`、`fromFloatForDisplayOnly`、`format` 的 SDK helper，避免用户手搓比例换算。

### X8 — Medium — SDK 自举接口不足以支撑“5 分钟上手”

证据：
- `swarm_sdk_fetch` 输入只有 `{ language, include_examples }`，输出 `{ sdk_code, type_definitions, examples, abi_version, min_engine_version }`。
- 当前文档缺少“创建账户/注册设备/获取世界信息/拉 SDK/编译 WASM/validate/deploy/check status”的完整 happy path。

DX 影响：
- AI agent 首次接入需要自己推断工具调用顺序，尤其 auth 与 device registration 复杂度高。
- `examples: string[]` 或 IDL 中的 `examples: string` 形态也不一致，且没有区分 tutorial、bot template、CI deploy sample。

要求变更：
- 增加 `swarm_onboarding_plan` 或扩展 `swarm_get_docs(topic="quickstart")`，返回机器可执行步骤。
- `swarm_sdk_fetch` 输入建议增加 `target: "wasm" | "mcp-client" | "both"`、`package_manager`、`template`。
- 输出 examples 应结构化：`[{name, language, files, run_commands, expected_output}]`，不要只给字符串。

### X9 — Medium — Snapshot 合同与 MCP snapshot schema 不一致

证据：
- `api-registry.md` 中 `swarm_get_snapshot` 输出为 `{tick, entities, terrain, resources, truncated, omitted_count}`。
- `09-snapshot-contract.md` 截断输出要求 `{tick, drone_id, truncated, omitted_categories: {entities, resources, events}, entities, resources, events}`。
- Snapshot contract 明确 `events` 是保留/省略类别，但 MCP schema 没有 `events` 字段。

DX 影响：
- SDK 的 `WorldSnapshot` 类型无法判断应该暴露 `omitted_count` 还是 `omitted_categories`。
- AI agent 对快照截断的恢复策略依赖 category-level omitted 信息；一个总数不足以做降级决策。

要求变更：
- 统一 `WorldSnapshot` schema，建议保留 `omitted_categories` 并废弃单一 `omitted_count`。
- 明确 `swarm_get_snapshot` 返回的是 player-level snapshot 还是 drone-level perception snapshot；当前 input 是 `player_id`，contract 示例包含 `drone_id`。

### X10 — Low — `debug_detail` 与 `detail_level` 很好，但需要 SDK/模式边界更明确

证据：
- Registry 定义 `competitive/practice/training`，默认 competitive。
- Snapshot contract 中又使用 Safe/FixHint/FullDebug 的实现模型。

DX 影响：
- SDK 使用者不知道应该在请求中传 `detail_level`，还是世界配置决定，还是 debug tools 自动提升。
- 若 `training` 可以通过 MCP 参数提升，需要明确 scope，否则容易误用。

要求变更：
- 定义统一字段名：`detail_level` 或 `hint_level` 二选一。
- 明确每个 MCP tool 是否允许 request override，以及所需 scope。

## Missing

1. 缺少 canonical SDK quickstart：应有一条可复制路径覆盖 auth/device/login、fetch SDK、编译 WASM、validate、deploy、status、explain_last_tick。

2. 缺少 IDL 到 SDK 的映射规范：包括类型命名、optional/null、bytes 编码、u64 在 TypeScript 中用 bigint 还是 string、fixed-point helper、error class 生成规则。

3. 缺少 MCP tool schema 的完整 JSON Schema/OpenAPI 导出策略：当前表格足够人读，但 codegen 需要 machine-readable schemas，尤其 union action payload。

4. 缺少 backward compatibility policy：API version 如何 bump，哪些变更是 breaking，MCP tool alias/deprecation 维持多久，SDK 如何 negotiate `abi_version`。

5. 缺少 examples 测试机制：所有文档里的 JSON 示例应通过 CI 反序列化校验，确保字段名不漂移。

6. 缺少 host ABI 版本协商和语言绑定生成说明：尤其 `ERR_ABI_VERSION` 如何触发、SDK 如何检测并给用户清晰错误。

7. 缺少 capability profile 的 discovery response：MCP 客户端需要知道当前服务器启用了哪些 profile/tool，以及禁用原因。

## API Consistency Issues

1. Tool count drift: 46 / 54 / 56 / 56+11 在不同位置共存。

2. Command count drift: IDL 为 19 core variants，registry/commands 文档为 21。

3. Custom action status drift: `Leech` / `Fabricate` 在 IDL 是 custom known，在 registry/commands 是 Tier 2 active-like action。

4. Host ABI drift: `host_get_terrain`、`host_path_find`、`host_get_world_rules` 签名在 IDL、registry、host-functions.md、interface.md 中不一致。

5. Auth duplicate names: `swarm_auth_login` / `swarm_auth_refresh` 在 game_api 与 auth_api 中同名但 schema 不同。

6. Error envelope drift: `error.code` 一处是 JSON-RPC integer，另一处是 RejectionReason string。

7. Field naming drift: `structure` vs `structure_type`，`body` vs `body_parts`，`omitted_count` vs `omitted_categories`，`detail_level` vs `hint_level`。

8. Error code drift: `02-command-validation.md` 仍出现 `TileBlocked`、`StillSpawning`、`ExceedsRoomCapacity`、`InvalidDamageType`、`AlreadyDebilitated`、`MainActionQuotaExceeded`、`InsufficientResources`、`PermissionDenied` 等不在 canonical 47 codes 中的名称；有些标为 debug_detail，有些未标。

9. Limits drift: `host-functions.md` 写模块大小上限 5 MB，而 `api-registry.md` persistence blob type 中 `wasm_module` 最大 64 MB；`02-command-validation.md` 批大小写 1MB，而 §1 写 tick 输出 256KB。

10. Namespace drift: `resources/list` / `resources/read` 与 `swarm_*` tool namespace 混用；如果这是 MCP Resources，应从 Tools 表中移除。

## CrossCheck — 需要跨方向检查

- CX1: `swarm_get_terrain` / `swarm_get_path` 在 MCP Tools 表中标记为 `host fn only`，但仍列入 Play 工具与工具总数 → 建议 Architect 检查 MCP tool registry、host ABI registry、SDK codegen registry 是否应拆成三个独立 artifact。

- CX2: Auth API 同名双 schema 与证书/Token 模型之间可能存在安全边界混淆 → 建议 Security 检查 `swarm_auth_login`、device registration、refresh token rotation、certificate auth 的统一认证流程是否存在重放或降级路径。

- CX3: Snapshot contract 的 player-level vs drone-level 语义不一致 (`player_id` input vs `drone_id` output) → 建议 Architect 检查快照生成归属：是每玩家聚合快照、每 drone perception snapshot，还是两者都需要不同 API。

- CX4: `swarm_simulate` / `swarm_dry_run` 输出 schema 在 registry 中过于简略，和 Snapshot Contract 的 `authoritative=false`、`not_predictive=true`、`deterministic=true` 不一致 → 建议 Engine/Architect 检查调试 API 是否需要统一 simulation envelope。

- CX5: Economy IDL 定义 AlliedTransfer 为 tax-free/no cooldown，但 Snapshot Contract 的 MVP economy boundaries 定义 allied transfer fee/delay/cooldown/daily cap → 建议 Economy reviewer 检查经济 API 与 MVP 经济规则哪个为权威。

- CX6: `api-registry.md` 声明 auth trace events 是 replay envelope 的一部分，但其中包含 ip_address/hash 与 non_replayable 事件 → 建议 Security/Architect 检查审计事件、隐私数据与 deterministic replay 的存储边界。

- CX7: `debug_detail` 在 training 模式可能包含精确 state diff/path traces/internal diagnostics → 建议 Security 检查训练/练习/竞技模式切换是否可以被客户端请求提升，以及是否必须要求 admin/debug scope。

## Recommended Gate Before Approval

1. 将 `api-registry.md`、`commands.md`、`host-functions.md`、`mcp-tools.md` 全部改为 IDL 生成或生成片段嵌入。
2. CI 增加 drift checks：工具数量、action 数量、host ABI 签名、error enum、limits、JSON 示例均从 IDL 校验。
3. 冻结 public naming：CommandIntent envelope、host ABI、MCP tool namespace、Auth canonical schema、JSON-RPC error envelope。
4. 增加 SDK quickstart golden test：从文档复制示例，生成 TS/Rust SDK 类型，构造一个最小 WASM bot，validate/dry_run/deploy schema 全链路通过。
