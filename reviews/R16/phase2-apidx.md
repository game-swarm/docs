# R16 Phase 2 CrossCheck — API/DX 补充验证

范围：仅补充核查 R16 各评审 CrossCheck 中指向 API/DX 的项目；未重跑完整 API/DX 评审。重点来源：`rev-gpt-apidx`、`rev-dsv4-apidx`、`rev-gpt-security`、`rev-dsv4-security`、`rev-gpt-designer`、`rev-gpt-architect`、`rev-gpt-determinism`，以及相关文档 `specs/reference/api-registry.md`、`design/interface.md`、`specs/reference/mcp-tools.md`、`specs/reference/commands.md`、`specs/reference/host-functions.md`、`specs/gameplay/06-feedback-loop.md`、`specs/gameplay/08-api-idl.md`、`specs/security/03-mcp-security.md`。

## CrossCheck item -> Finding -> disposition

### 1. API registry vs interface/mcp-tools/commands/host-functions/feedback-loop 的 tool/action/error/ABI 冲突清单

Finding:

- MCP tool list 仍是多事实源且差集巨大。
  - `api-registry.md` §3.1 声称 MCP Tools (46)，实际表内列出 45 个唯一工具/资源（43 个 `swarm_*` + `resources/list` + `resources/read`），且表中 `swarm_get_resources` 重复出现在 Onboarding 与 Play。
  - `design/interface.md` §4.1 与 `specs/reference/mcp-tools.md` 使用另一套工具：包含 `swarm_get_schema`、`swarm_get_docs`、`swarm_get_available_actions`、`swarm_explain_last_tick`、`swarm_dry_run_commands`、`swarm_rollback`、`swarm_list_modules`、认证工具、锦标赛工具等；这些不在 registry。
  - registry 反过来包含 `swarm_get_info`、`swarm_get_code`、`swarm_get_room`、`swarm_list_drones`、`swarm_get_tick_trace`、`swarm_dry_run`、`swarm_admin_*`、`swarm_get_deploy_status` 等；这些不在 interface/mcp-tools 的主表。
  - `specs/security/03-mcp-security.md` §4.5 明确禁止直接实体操作工具，但其文档仍提到 `swarm_move`/`swarm_attack` 等作为禁止项；这本身可作为说明，但若被简单差集脚本抓取会污染工具清单，需要以机器可读 allowlist/denylist 区分。
- action/CommandAction 冲突仍未闭合。
  - registry §1 是 19 指令（11 core + 2 Global + 6 特殊），特殊攻击为 `Hack/Drain/Overload/Debilitate/Disrupt/Fortify`，并把 `Leech/Fabricate` 明确放入 World Action Manifest 非 Core enum。
  - `commands.md` 标题写“19 指令”，下一行又写“以下 15 种指令…第 16 个变体 Custom(type)…8 种特殊攻击”；正文使用 `SpawnDrone`，registry/IDL 使用 `Spawn`；还列出 `Leech/Fabricate` 为 Tier 2，和 registry 的“非 Core manifest”语义不同。
  - `06-feedback-loop.md` starter bot 示例仍出现 `MoveTo`，但 registry/IDL 当前只有 `Move` + Direction4。
- RejectionReason 冲突仍未闭合。
  - registry §2 声称 35 变体，但 IDL 中列出更多验证级变体（如 `NotMovable`、`Fatigued`、`MissingBodyPart`、`TileBlocked`、`NoPath`、`PathTooLong`、`CarryFull`、`NotSource`、`SourceEmpty`、`InvalidTerrain`、`TooManyConstructionSites`、`BodyTooLarge`、`NotFriendly`、`AlreadyHacked`、`InvalidDamageType`、`AlreadyDebilitated`），同时 registry 有 `CooldownActive`、`PositionOccupied`、`ConstructionLimitReached`、`SafeModeActive`、`TargetFortifyCooldown`、`NotEnoughBodyParts`、`InvalidBodyPart`、`InvalidStructureType`、`InvalidResourceType` 等不在 IDL 片段中。
  - `commands.md` 的拒绝原因列表继续使用多种非 registry 命名（如 `TileOccupied`、`TooManyConstructionSites`、`MissingBodyPart`、`NoPath`、`BodyTooLarge` 等），与 registry §2.1/§2.2 的“统一命名”相冲突。
- Host Function ABI 冲突是明确 blocker。
  - registry §4.1：`host_get_terrain(room_id, out_ptr, out_len)`；host-functions/interface/IDL 仍是 `host_get_terrain(x, y) -> i32` 或短名 `get_terrain(x,y)`。
  - registry §4.1：`host_path_find(..., opts_ptr, opts_len, out_ptr, out_len)`；host-functions/interface/IDL 缺少 `opts_ptr/opts_len`。
  - registry §4.1：`host_get_world_rules(rule_id_ptr, rule_id_len, out_ptr, out_len)`；host-functions/interface/IDL 是无 rule_id 的 `out_ptr,out_len`。
  - registry §4.5 定义负数 ABI 错误优先级，但 host-functions.md 没有同步该错误优先级，开发者无法只读 host-functions 参考实现一致 ABI。

Disposition: blocker

理由：这不是局部命名问题，而是 codegen/SDK/MCP/host ABI 的输入事实源不唯一。若进入实现，会直接生成不同 SDK 类型、不同 MCP tool server、不同 WASM import 签名和不同错误枚举。

### 2. `game_api.idl` 是否应为机器事实源；若未定义，应列为 blocker 还是 high

Finding:

- `specs/gameplay/08-api-idl.md` 明确写“game_api.idl (单一真相)”并声明生成 Rust/TS/MCP/Docs/Test；同时 `api-registry.md` 也自称“所有 API 合约的单一权威来源”。两者现在是双权威。
- IDL 目前只是 Markdown 中的 YAML 片段，不是独立、可解析、可由 CI/codegen 消费的 `game_api.idl` 文件；也没有看到生成器、schema 校验器或 registry-from-IDL 的机器链路。
- 内容层面 IDL 与 registry 已经不一致：CommandAction 名称/数量、RejectionReason 变体、host function 签名均有冲突。

Disposition: blocker

理由：R16 已承诺 SDK、MCP schema、starter bot、host stubs、docs 由 IDL/registry 生成；如果 `game_api.idl` 不是可解析机器源，5 分钟上手和 ABI 稳定性都不可验证。可接受的修复方向二选一：

1. 让 `game_api.idl` 成为唯一机器事实源，`api-registry.md` 改为 generated registry view；或
2. 让 `api-registry.yaml/json` 成为唯一机器事实源，`08-api-idl.md` 改为从 registry 生成的解释性文档。

但不能继续保留“registry 与 IDL 都是权威”。

### 3. MCP tools inputSchema/outputSchema/error schema 覆盖缺口

Finding:

- registry §3.1 的 Input/Output 只是表格内的示意对象（如 `{player_id}`、`{trace, fuel_used, errors}`），没有 JSON Schema 级字段类型、required/optional、enum、bounds、`additionalProperties: false`、错误 schema、错误码绑定、auth scope、visibility/replay 约束。
- `design/interface.md` §4 开头要求所有 MCP 工具必须具备 `inputSchema`、`outputSchema` 和 `error` schema，由 `game_api.idl` 生成，并点名 `swarm_get_schema`、`swarm_get_docs`、`swarm_get_player_status`、`swarm_get_available_actions`、`swarm_explain_last_tick`、`swarm_submit_csr` 等必须进入工具目录；这些工具多数不在 registry。
- `mcp-tools.md` 只列工具名/用途，几乎没有 request/response/error schema；`03-mcp-security.md` 给了部分示例和 scope，但与 registry 工具表不一致。
- `api-registry.md` §8 定义统一 SwarmError JSON-RPC envelope，但没有逐工具声明可能返回的 error code 集合、脱敏规则、rate-limit error、schema violation error、auth error的 data 结构。

Disposition: blocker

理由：MCP 的 DX 依赖工具 schema 可被 agent/IDE 自动发现。当前“示意对象 + 多份工具表”不能让 MCP client 生成可靠 wrapper，也不能让 CI 验证 onboarding sequence。至少应要求：每个工具有机器可读 inputSchema/outputSchema/errorSchema；错误集合引用 registry/IDL enum；schema 均 `additionalProperties:false`；字段级 bounds 与 examples 从同一源生成。

### 4. subject_source/auth_scope/replay_class/visibility_filter 是否必须进入 registry

Finding:

- 必须进入 registry 或其机器源。现状只部分覆盖：
  - `design/interface.md` 表有 `replay_class` 一列，但 registry §3.1 没有；
  - `03-mcp-security.md` §3.2/§4 有 scope 表与部分工具 scope，但工具集合与 registry 不一致；
  - `auth.md` 有大量认证工具/nonce/证书语义，但 registry 仅有 6 个 admin 工具和 `swarm_admin_challenge`，缺少注册/CSR/证书生命周期工具；
  - visibility_filter 只在 snapshot/security/visibility 语义中散落，registry 工具表未绑定“玩家视野 / admin full / spectator delayed / replay-safe redacted”等过滤策略；
  - subject_source（MCP caller、WASM Source Gate、admin、spectator、replay）未逐工具/逐 command 绑定，无法统一 `SourceNotAllowed`、NotAuthorized、replay oracle 防护。
- 安全评审明确要求 API Registry 成为 authz/replay/visibility 权威源；API/DX 角度同意，因为 SDK wrapper、MCP discovery、docs examples 都需要知道“谁能调、返回什么视图、是否可 replay、安全脱敏如何发生”。

Disposition: high

理由：它是安全与 DX 的强需求，但相对“事实源双写/ABI冲突/schema缺失”可作为同一个 registry/codegen 修复包内的 High 子项。若 R16 声称 registry 已经是唯一安全权威，则此项应升级为 blocker；当前建议在 Speaker 的 blocker 包中明确列为必须随 MCP schema 一起补齐的字段。

### 5. Quickstart Contract / onboarding MCP sequence 是否可执行

Finding:

- 当前不可执行，原因不是教程文字缺失，而是 canonical sequence 中引用的工具与 registry 不一致。
  - `06-feedback-loop.md` AI 教程序列：`swarm_get_snapshot` → `swarm_get_available_actions` → `swarm_get_docs` → `swarm_validate_module` → `swarm_deploy` → `swarm_explain_last_tick`。
  - 验收标准又要求 `swarm_get_schema` → `swarm_get_docs` → `swarm_get_available_actions`，并等待 `first_tick_executed`。
  - registry §3.1 没有 `swarm_get_schema`、`swarm_get_docs`、`swarm_get_available_actions`、`swarm_explain_last_tick`，而是提供 `swarm_get_info`、`swarm_sdk_fetch`、`resources/list/read`、`swarm_dry_run`、`swarm_get_tick_trace` 等另一套入口。
- 参数也不一致：feedback 示例用 `swarm_validate_module {wasm: wasm_code}`、`swarm_deploy {wasm: wasm_code, version: "v2"}`；registry 要求 `{wasm_bytes}` 和 `{player_id, drone_id, wasm_bytes, metadata}`。
- starter bot 字段示例出现 `MoveTo`，但 registry/IDL 没有该 action；这会让 smoke test 在第一步生成代码后失败。

Disposition: blocker

理由：任务要求判断“Quickstart Contract / onboarding MCP sequence 是否可执行”。答案是否定的。AI agent 无法仅按文档在 5 分钟内完成 basic-agent 部署，因为 discovery/docs/action/deploy/debug 工具名和 schema 不能同时满足 registry 与教程。

### 6. alias/deprecation 机制是否足以保留 UX 友好名称

Finding:

- IDL §1 只有 host function ABI 变更公告期（新增/修改/移除）和 `abi_version`，但没有 MCP tool alias、CommandAction alias、RejectionReason alias、参数 alias 的统一机制。
- registry §2.1 只是写“废弃 `InsufficientResources`/`InsufficientEnergy`、`TargetNotFound` 等”，没有规定这些旧名在 SDK/MCP/错误响应中是 hard error、warning alias、还是迁移期兼容。
- 当前最需要 alias/deprecation 的冲突包括：
  - `swarm_dry_run_commands` ↔ `swarm_dry_run`
  - `swarm_explain_last_tick` ↔ `swarm_get_tick_trace`/可能的 explain wrapper
  - `swarm_get_schema`/`swarm_get_docs`/`swarm_get_available_actions` ↔ registry 的 `swarm_sdk_fetch`/Resources/onboarding 工具
  - `SpawnDrone` ↔ `Spawn`
  - `MoveTo` ↔ `Move` + pathing/helper
  - `InsufficientResources`/`InsufficientEnergy` ↔ `InsufficientResource`
  - `TargetNotFound` ↔ `ObjectNotFound`/`NotVisibleOrNotFound`
- API/DX 角度建议保留 UX 友好名称，但必须通过机器可读 alias 表表达：canonical name、aliases、deprecated_since、remove_after_abi、warning text、safe rewrite、是否只在 docs/SDK helper 层存在。

Disposition: high

理由：alias/deprecation 不是替代事实源收敛的办法；它能降低迁移成本，但当前机制不足以保证旧教程/SDK wrapper 可用。若不补，容易在修复命名后牺牲新用户可学性。

## 补充裁决建议

1. 把“单事实源”拆成机器源与展示源：选择 `game_api.idl` 或 `api-registry.yaml/json` 之一作为唯一机器输入；Markdown registry/API references 必须生成或 CI diff。
2. 在机器源中加入以下字段：`canonical_name`、`aliases`、`deprecated_since/remove_after`、`inputSchema`、`outputSchema`、`errorSchema`、`auth_scope`、`subject_source`、`replay_class`、`visibility_filter`、`rate_limit`、`capability_profile`、`examples`。
3. 以 onboarding smoke test 作为 DX gate：从空 MCP client 开始，按 canonical sequence 获取 SDK/schema/docs，编译 starter bot，validate，deploy，等待 `first_tick_executed`，再调用 debug/explain 工具；该流程必须只使用 registry/IDL 中存在的工具和参数。
4. 对 Host Function ABI 增加 generated header/wit/json，并让 host-functions.md/interface.md/IDL 均从同一源生成；旧签名只能通过明确 deprecation/compat ABI 表存在。
