# R24 API/DX Review — GPT-5.5

Verdict: REQUEST_MAJOR_CHANGES

本轮从 API/SDK/MCP/IDL/参考文档可实现性角度检查 spec ↔ design 对齐。总体方向正确：MCP 不再作为游戏动作通道、IDL/Registry/codegen 单事实源的目标清晰，且多处文档已显式要求 reference 文档只作为派生展示。但当前仍存在若干会直接误导 SDK 生成、WASM ABI、MCP 客户端实现和新用户 5 分钟上手的跨文档冲突；其中 Host Function ABI 与 MCP 工具清单漂移属于阻断级问题。

## Strengths

- design/interface.md 已把 MCP 定位为 AI 的“屏幕和鼠标”，并明确 AI 与人类都必须通过 WASM 部署进入世界；这与 design-parliament 中用户纠正过的核心原则一致。
- API Registry 的目标形态清晰：CommandAction、RejectionReason、MCP Tools、Host Functions、Economy Operations、容量限制统一收敛到 IDL 生成产物。
- commands.md、mcp-tools.md、host-functions.md 多数地方已标注“权威见 API Registry”，这对长期维护是正确方向。
- 错误码设计开始从“枚举爆炸”转向 canonical code + debug_detail，对 SDK 稳定性友好。

## Concerns

### X1 [Critical] — Host Function ABI 在 design、IDL spec 与 API Registry 间不一致

冲突位置：
- design/interface.md §5.1：`host_get_terrain(x: i32, y: i32) -> i32`；`host_path_find(from_x, from_y, to_x, to_y, out_ptr, out_len) -> i32`；`host_get_world_rules(out_ptr, out_len) -> i32`
- specs/gameplay/08-api-idl.md §2 host_functions：`get_terrain(x, y) -> i32`；`path_find(from_x, from_y, to_x, to_y, out_ptr, out_len)`；`get_world_rules(out_ptr, out_len)`
- specs/reference/api-registry.md §4.1：`host_get_terrain(room_id, out_ptr, out_len) -> i32`；`host_path_find(..., opts_ptr, opts_len, out_ptr, out_len)`；`host_get_world_rules(rule_id_ptr, rule_id_len, out_ptr, out_len)`
- specs/reference/host-functions.md §详细签名：仍采用 design/IDL 的旧签名

冲突描述：同一组 WASM import 的 ABI 参数数量、含义和返回语义不同。实现者如果按 Registry 生成 SDK，而文档/IDL 示例按旧签名编译 starter bot，会出现 WASM import 解析失败或运行期错误。`host_get_terrain` 尤其严重：一个版本返回单格 terrain_type，另一个版本按 room_id 写出整房间 terrain buffer。

修正建议：选定唯一 ABI 并回写到所有层。若 Registry 为生成权威，则应更新 design/interface.md、08-api-idl.md、04-wasm-sandbox.md、host-functions.md 的签名和示例；若旧坐标 API 才是目标，则必须修正 game_api.idl.yaml/codegen，使 api-registry.md 不再生成 room buffer 版本。无论选择哪边，都要补充一条 CI：从 IDL 生成 host-functions.md 后 diff 检查。

### X2 [High] — MCP 工具数量与活跃工具清单在 design/spec/reference 间漂移

冲突位置：
- design/interface.md §4.1：声明“56 game tools + 11 auth tools”
- specs/reference/mcp-tools.md §工具总览：声明“56 个 Game API 活跃工具 + 11 个 Auth API 工具”
- specs/security/03-mcp-security.md §4：声明“56 工具”
- specs/reference/api-registry.md §3：声明“54 个活跃工具 (game_api) + 11 个 Auth API 工具”，且 §3.2 表格小计为 Onboarding 10 + Auth 2 + Play 16 + Deploy 7 + Debug 8 + Admin 6 + SDK 1 + Arena 4 + Resources 2 = 56

冲突描述：API Registry 同一节内部也自相矛盾：标题写 54，分类合计为 56。上层 design/reference 又引用 56。SDK/MCP 客户端生成器会以实际 IDL 为准，但人类读者和审计工具会无法判断两个 Resources 工具是否属于 Game API 活跃工具。

修正建议：以 IDL 生成结果为准修正 api-registry.md §3 的总数；如果真实活跃为 56，则把“54 tools”改为“56 tools”。同时在 codegen 输出中增加分类合计校验，避免标题数与表格数再次漂移。

### X3 [High] — specs/security/03-mcp-security 把 Registry 中仍存在的工具标为“已移除”

冲突位置：
- specs/security/03-mcp-security.md §4.1：称 `swarm_list_modules` 已替换为 `swarm_list_deployments`
- specs/reference/api-registry.md §3.2 Deploy：仍注册 `swarm_list_modules`
- design/interface.md §4.1：部署分类代表性工具也列出 `swarm_list_modules`

另一个同类冲突：
- specs/security/03-mcp-security.md §4.3：称 `swarm_explain_last_tick` 已移除、替换为 `swarm_get_tick_trace`
- specs/reference/api-registry.md §3.2 Debug：仍注册 `swarm_explain_last_tick`
- design/interface.md §4.1：调试分类仍列 `swarm_explain_last_tick`

另一个同类冲突：
- specs/security/03-mcp-security.md §4.4：称 `swarm_get_schema`、`swarm_get_docs`、`swarm_get_available_actions` 已整合移除
- specs/reference/api-registry.md §3.2 Onboarding/Play：仍注册 `swarm_get_docs`、`swarm_get_schema`、`swarm_get_available_actions`
- specs/reference/mcp-tools.md §世界查看：还把它们列为 0.4.0 新增查询入口

冲突描述：这是 MCP 客户端可用性层面的高风险漂移。实现者按 security spec 会删掉工具；按 Registry/codegen 会生成工具；按 design 又会在分类说明里看到工具。新用户会在“工具不存在/存在”的文档之间来回跳转。

修正建议：security spec 不应维护“已移除工具”列表，除非它由 Registry 生成。短期应删除这些“已移除”声明，改为“权威清单见 Registry”；若确实要移除上述工具，则先从 IDL/Registry 删除，再同步 design/interface.md 和 mcp-tools.md。

### X4 [High] — `swarm_deploy` 输入/输出 schema 在 security spec 与 Registry/design 不一致

冲突位置：
- specs/security/03-mcp-security.md §4.1 `swarm_deploy` 示例：输入 `{ wasm_bytes, language, version_tag, room_id }`，输出 `{ module_id, status, deployed_at }`
- specs/reference/api-registry.md §3.2 Deploy：输入 `{player_id, drone_id, wasm_bytes, metadata}`，输出 `{deploy_id, accepted, validation_errors, fdb_version_counter, object_store_key}`
- design/interface.md §5.7：部署语义依赖 `module_hash` idempotency、FDB `version_counter`、object store GC

冲突描述：security spec 的示例是旧的 UX 形态，缺失 replay-critical 字段、idempotency/module hash 语义、deploy_id/status 查询链路，也额外引入 `room_id`/`version_tag`。这会误导 SDK 示例和 MCP quickstart，导致部署流程与持久化/replay 合同脱节。

修正建议：把 security spec §4.1 的 `swarm_deploy` 示例改为 Registry schema，至少包含 `player_id` 来源不可自报说明、`drone_id`/`wasm_bytes`/`metadata`、`deploy_id`、`fdb_version_counter`、`object_store_key`。如果为了 DX 想保留简化示例，应标明“SDK helper 层伪代码”，不要作为 MCP wire schema。

### X5 [Medium] — CommandAction/IDL 示例仍保留旧 RejectionReason 与旧命令数量，和 Registry 的 canonical model 不对齐

冲突位置：
- specs/gameplay/08-api-idl.md §2：注释称 Registry 有 47 变体，但 YAML 示例仍列 `NotMovable`、`Fatigued`、`MissingBodyPart`、`TileBlocked`、`SourceEmpty`、`TargetFull` 等旧错误码
- specs/reference/api-registry.md §2：明确这些应合并到 47 canonical code 或 debug_detail，不作为 canonical wire code
- specs/reference/commands.md §拒绝原因：明确旧错误码已合并/降级
- specs/gameplay/08-api-idl.md §2：注释称“19 指令”，但 Registry §1 与 commands.md 均为 21 指令（11 core + 2 Global + 8 special）

冲突描述：08-api-idl.md 虽然声称权威数据见 Registry，但它同时承载“IDL 格式”和 codegen 思路。示例里保留旧 enum 会让实现者误以为 IDL YAML 仍要生成这些 wire codes，从而和 Registry 的 stable canonical enum 冲突。

修正建议：把 08-api-idl.md §2 的 enum 示例改成 canonical 47 code 的摘要或直接替换为 `$ref: api-registry RejectionReason` 风格；旧错误码只放在 `debug_detail_examples`。同时将“19 指令”改为“21 指令”。

### X6 [Medium] — SDK 分发入口 schema 在 design 与 API Registry 不一致，影响 5 分钟上手

冲突位置：
- design/interface.md §5.3：`swarm_sdk_fetch` Input 为 `{ language, include_examples }`
- specs/reference/api-registry.md §3.2 SDK：同样为 `{language, include_examples}`
- specs/gameplay/08-api-idl.md §6.1：MCP 入口写作 `swarm_sdk_fetch(world_id)`，CLI 为 `swarm sdk fetch <world_id>`，并强调 SDK 按 `(mod_manifest_hash, sdk_target)` 缓存

冲突描述：设计层一方面要求 SDK 动态绑定世界 manifest，另一方面 MCP schema 没有 `world_id` 或 `target_manifest_hash` 输入。若客户端连接的是单世界 endpoint，可以隐含 world；若是多世界 Gateway，则缺少 world 选择会导致拿错 SDK。当前文档没有说明这个默认假设。

修正建议：二选一明确：A) MCP endpoint 已绑定 world，`world_id` 来自认证 audience/URL，不进入 schema；B) `swarm_sdk_fetch` schema 增加 `world_id` 或 `target_manifest_hash`。无论选哪种，都要同步 design/interface.md、08-api-idl.md、api-registry.md 和 mcp-tools.md 的 quickstart 表述。

### X7 [Medium] — 经济/资源操作的 API 形态在 Command、ResourceOperation、MCP Resources 三套命名间缺少清晰边界

冲突位置：
- specs/reference/api-registry.md §1：`TransferToGlobal` / `TransferFromGlobal` 是 CommandAction
- specs/reference/api-registry.md §10：Economy ResourceOperation 又列出 `AlliedTransfer`，描述为 `TransferToGlobal + TransferFromGlobal (allied only)`
- specs/reference/api-registry.md §3.2 Resources：MCP 工具使用 `resources/list`、`resources/read`，命名风格与 `swarm_*` 工具不一致
- design/interface.md §4.1：经济分类代表性工具是 `swarm_get_economy`、`swarm_get_drone_efficiency`、`swarm_get_economy_trend`，未提 `resources/list/read`

冲突描述：从 API/DX 看，开发者会混淆三层：WASM command、engine-side economy operation、MCP resource catalog tool。特别是 `resources/list` 采用路径式命名，而其它 MCP 工具全是 `swarm_*`，破坏命名一致性与可发现性。

修正建议：在 API Registry §10 开头明确“ResourceOperation 不是外部 API/CommandAction，除表中 Resource Flow 引用外不可由玩家直接调用”。将 `resources/list`/`resources/read` 要么改名为 `swarm_list_resources`/`swarm_get_resource`，要么在 design/interface.md 的 MCP 分类中增加“Resources namespace 例外及原因”。

## Missing

- 缺少“新用户 5 分钟 MCP → SDK → WASM → deploy → explain_last_tick”的端到端 quickstart，现有信息分散在 interface、feedback-loop、api-idl、mcp-tools 中。建议在 mcp-tools.md 或 GETTING-STARTED.md 增加最短路径，并确保全部工具名来自 Registry。
- 缺少 machine-readable drift checks 的明确清单：工具总数、分类合计、host function ABI、CommandAction 数、RejectionReason 数、rate limit 表都应由 IDL/codegen 校验。
- 缺少 MCP tool error envelope 的输入输出示例矩阵：deploy validation error、rate limited、visibility redaction、auth scope failure 分别应展示 `SwarmError` 如何返回，避免 SDK 作者自行发明异常类型。
- Rhai API 公开面只在 world-rules 中以概念呈现，缺少“哪些 host action 可由 Rhai 调用、哪些内部状态不可见”的最小 API 表；这会影响模组作者 DX 和安全审计。

## API Consistency Issues

- `swarm_*` 与 `resources/list`/`resources/read` 命名风格混用；建议统一动词前缀或明确 namespace 规则。
- `swarm_get_*`、`swarm_list_*`、`swarm_profile` 混用名词/动词；`swarm_profile` 建议改为 `swarm_get_profile`，保持可预测性。
- `swarm_get_path` 是 MCP tool 名，但 host function 是 `host_path_find`；若两者语义不同应在 Registry 明确差异，否则建议命名对齐为 `swarm_path_find` 或 `host_get_path`。
- deploy 相关输出中 `deploy_id`、`module_hash`、`module_id`、`object_store_key` 在不同文档出现但边界不清；建议在 Registry 增加 Deploy object model 小节。
- `InvalidCertificate` / `NotAuthorized` 同名跨 game_api 与 auth_api，Registry 虽解释 namespace offset，但 wire envelope 示例 `error.code` 是 string，可能丢失 namespace。建议要求 error envelope 携带 `domain: game|auth|mcp` 或使用 fully-qualified code（如 `auth.InvalidCertificate`）。
