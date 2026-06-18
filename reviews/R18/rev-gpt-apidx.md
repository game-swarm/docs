# R18 API / Developer Experience Review (GPT-5.5)

## 1. Verdict

**REQUEST_MAJOR_CHANGES**

R18 相比 R17 已经把 `game_api.idl.yaml` 与生成的 `api-registry.md` 做到了较高程度闭合：IDL 自声明计数与实际结构一致，Registry 中的 CommandAction、RejectionReason、MCP Tools、Host Functions、Limits、TickTrace 基本能从 YAML 找到对应来源。

但从 API/DX 视角，本轮仍不能进入实现：**“YAML → Registry”闭合了，但“YAML → 所有开发者会读/会用的 reference/spec/design 文档”没有闭合**。`commands.md`、`mcp-tools.md`、`host-functions.md`、`design/interface.md`、`core/02-command-validation.md`、`core/09-snapshot-contract.md` 仍大量保留旧 API 表述，且多处直接违背 Registry 中“其他文档只能引用，不得重新声明可冲突列表”的原则。结果是新用户无法 5 分钟上手，SDK/codegen 作者也无法判断哪个 schema 才可生成。

---

## 2. 发现问题 (severity)

### C1 — Critical — CommandAction 单源仍未真正闭合，SDK 与命令校验文档会生成/实现出不同 API

**证据：**

- `game_api.idl.yaml`：`CommandAction` 为 **19 variants**：11 core + 2 global_storage + 6 special_attack；`Leech`、`Fabricate` 明确在 `custom_actions`，不是 Core enum。
- `api-registry.md`：与 YAML 对齐，写明 19 个变体，且 `Leech`/`Fabricate` 是 World Action Manifest custom actions。
- `commands.md` 仍写：
  - “以下 15 种指令对应 `CommandAction` enum 的 15 个具体变体。第 16 个变体 `CommandAction::Custom(type)` 通过 `CustomActionRegistry` 路由到 8 种特殊攻击”。
  - “特殊攻击（via `CommandAction::Custom`）以下 8 种特殊攻击”。
  - 同时又在上方承认 “19 指令（11核心+2Global+6特殊）”。
- `core/02-command-validation.md` 也仍保留大量旧形态章节：`CommandAction 变体` 中使用扁平 `{ "action": "RangedAttack", ... }` 示例，而不是当前 `CommandIntent { sequence, action: { type, ... } }` 格式。

**影响：**

SDK codegen、MCP `swarm_get_schema`、命令验证器测试、教程示例会出现三种相互矛盾的模型：

1. 19 个核心 action；
2. 15 + `Custom(type)`；
3. 示例中扁平 `action` 字符串格式。

这会直接破坏“玩家/AI 写 WASM 返回 CommandIntent[]”的 5 分钟上手体验，也会导致 SDK 类型无法稳定生成。

**建议：**

- `commands.md` 不应再手写“15 + Custom”模型。应从 YAML 生成 action 列表和每个 action 示例。
- `core/02-command-validation.md` 中所有旧扁平 JSON 示例必须替换为 `sequence + action.type` 结构，或改成只引用 Registry/Commands 生成段落。
- 若 `Leech`/`Fabricate` 是 custom actions，就必须始终展示为 World Action Manifest 示例，而不是混入 Core CommandAction 示例。

---

### C2 — Critical — MCP 工具目录与 YAML/Registry 大面积漂移，AI agent 首次接入路径不可预测

**机器交叉检查结果：**

- YAML active MCP tools：声明 46，实际 `mcp_tools.tools` 46。
- `api-registry.md` 工具清单与 YAML active tools 对齐；正则抓取额外出现 `swarm_list_market_orders`，但它在 RFC/Future 节中，语义上不计 active count。
- `design/interface.md` 正则抓取出 51 个 tool-like 名称；与 YAML active tools 对比：
  - 缺失大量 YAML active tools，例如 `swarm_get_info`、`swarm_auth_login`、`swarm_auth_refresh`、`swarm_get_deploy_status`、`swarm_list_deployments`、`swarm_get_tick_trace`、`swarm_dry_run`、全部 `swarm_admin_*`、`resources/list`、`resources/read` 等。
  - 额外保留大量非 YAML active tools，例如 `swarm_get_server_trust`、`swarm_register_challenge`、`swarm_submit_csr`、`swarm_rollback`、`swarm_list_modules`、`swarm_explain_last_tick`、`swarm_inspect_entity`、`swarm_profile`、`swarm_get_docs`、`swarm_get_schema`、`swarm_get_available_actions`、锦标赛工具等。
- `specs/reference/mcp-tools.md` 也同样大面积漂移：缺失 34 个 YAML active tools，同时额外列出一批旧 auth/debug/deploy/tournament 工具。

**影响：**

MCP 是 AI agent 的“屏幕和鼠标”。当前文档会让 agent 在 onboarding 阶段调用不存在的工具：

- `swarm_get_server_trust` / `swarm_register_challenge` / `swarm_submit_csr` 在 interface 和 mcp-tools 中被描述为关键接入工具，但 YAML active tools 已变成 `swarm_auth_login` / `swarm_auth_refresh`。
- `swarm_get_schema` / `swarm_get_docs` / `swarm_get_available_actions` 在设计文档中仍是学习路径核心，但 YAML 只有 `swarm_sdk_fetch`，没有这些 active tools。
- `swarm_rollback` / `swarm_list_modules` 与 YAML 的 `swarm_get_deploy_status` / `swarm_list_deployments` 命名模型冲突。
- `swarm_dry_run_commands` 与 YAML 的 `swarm_dry_run` 冲突。

这不是小的文案问题，而是会让 MCP 客户端、agent prompt、SDK bootstrapping、测试夹具调用完全不同的接口。

**建议：**

- `mcp-tools.md` 必须由 YAML 生成，而不是手写分类说明。
- `design/interface.md` 应只保留概念架构和“权威工具清单见 Registry”，不要再列出可能漂移的完整工具表。
- 如果仍需要“5 分钟接入路径”，应由 YAML 的 `capability_profiles.onboarding` 自动生成，并明确 active tools 当前是：Onboarding + Auth + SDK + Resources 分类。

---

### C3 — Critical — RejectionReason 仍存在 canonical enum 与调试细节混用，错误处理 API 不可生成

**证据：**

- YAML/Registry：35 个 canonical code；`InvalidJson`、`SchemaViolation` 是 pipeline 级；`debug_detail` 承载 `NotMovable`、`Fatigued`、`PathBlocked` 等非 canonical 细节；`InsufficientResource` 为单数。
- `commands.md` 的拒绝原因表仍列出大量非 canonical 名称：`NotMovable`、`Fatigued`、`MissingBodyPart`、`TileBlocked`、`StillSpawning`、`OutOfRoom`、`NoPath`、`PathTooLong`、`CarryFull`、`NotSource`、`SourceEmpty`、`TargetFull`、`TargetEmpty`、`NotYourRoom`、`InvalidTerrain`、`FriendlyTarget`、`NotYourSpawn`、`BodyTooLarge`、`AlreadyHacked`、`InvalidDamageType`、`AlreadyDebilitated` 等。
- `core/02-command-validation.md` 逐指令矩阵也继续把这些非 canonical 名称当作失败码使用。
- `core/09-snapshot-contract.md` 中 Safe Hint Ladder 仍使用 `InsufficientResources`、`PermissionDenied`、`InvalidTarget` 等与 YAML 不一致的类别名。

**影响：**

错误码是 SDK DX 的核心。当前设计会让开发者无法写稳定的：

```ts
switch (err.code) { ... }
```

因为同一失败条件在不同文档中可能是 canonical enum、debug_detail 字符串、或旧错误类别。对 MCP 来说，错误 schema 的 `error.code` 也无法可靠声明。

**建议：**

- 所有 reference/spec 中的“失败码”列必须只允许 YAML canonical codes。
- 非 canonical 细节必须改名为 `debug_detail` 示例，例如 `MissingBodyPart(Work)` 应表达为 `rejection = NotEnoughBodyParts` + `debug_detail = "MissingBodyPart: Work"`（具体映射需由设计明确）。
- `core/02-command-validation.md` 应增加一个从“旧细粒度原因 → canonical code + debug_detail”的生成表，且表源仍应来自 YAML。

---

### H1 — High — Host Function 签名文档与 Registry 不一致，会导致 WASM ABI 调用失败

**证据：**

YAML/Registry 的权威 ABI：

- `host_get_terrain(room_id: u32, out_ptr: i32, out_len: i32) -> i32`
- `host_path_find(from_x, from_y, to_x, to_y, opts_ptr, opts_len, out_ptr, out_len) -> i32`
- `host_get_world_rules(rule_id_ptr, rule_id_len, out_ptr, out_len) -> i32`

`host-functions.md` 仍写：

- `host_get_terrain(x: i32, y: i32) -> i32`
- `host_path_find(from_x, from_y, to_x, to_y, out_ptr, out_len) -> i32`
- `host_get_world_rules(out_ptr, out_len) -> i32`

`design/interface.md` 也保留概念签名，与 Registry §4.1 不完全一致。

**影响：**

Host ABI 是二进制边界，不是普通文档描述。签名一旦漂移，Rust/TS SDK 的 import declarations、WASM module validation、玩家代码示例会直接不可运行。

**建议：**

- `host-functions.md` 的“详细签名”必须由 YAML 的 `host_functions.functions[].abi_signature` 生成。
- 概念说明可保留，但必须放在权威签名之后，且不得使用可复制的旧 C 签名块。
- 错误返回也必须使用 YAML `abi_error_priority`：当前 `host-functions.md` 写“超出预算 → 返回 -1”与 Registry 中 `ERR_BUDGET_EXHAUSTED = -4`、`ERR_PLAYER_BUDGET = -5`、`ERR_GLOBAL_BUDGET = -6` 冲突。

---

### H2 — High — SwarmError / JSON-RPC envelope 在三处定义不一致

**证据：**

- YAML/Registry：`error.code` 是 `RejectionReason (string)`；`-32000` 仅保留给未分类内部错误；`data.debug_detail` 是 512 bytes 上下文。
- `design/interface.md` 仍给出：
  - `error.code: -32000`
  - `data.swarm_error: "InsufficientResources"`
  - `retry_allowed`、`idempotency_key`
- `core/09-snapshot-contract.md` Safe Hint Ladder 使用 `InsufficientResources` 复数，与 YAML `InsufficientResource` 单数冲突。

**影响：**

MCP 客户端和 SDK 无法确定：

- 应该 switch `error.code` 还是 `data.swarm_error`；
- 错误码是数字还是字符串；
- retry/idempotency 是错误 envelope 的一等字段，还是 tool metadata 的派生行为；
- `InsufficientResource(s)` 到底哪个是 wire name。

**建议：**

- 统一为 Registry 的 JSON-RPC envelope。
- 如果需要 `retry_allowed` / `idempotency_key`，应把它们加入 YAML `swarm_error_envelope.schema.data`，而不是只在设计说明中出现。
- 所有文档中的 `InsufficientResources` 必须改为 `InsufficientResource` 或明确标注为 deprecated 输入兼容，不得出现在 wire 示例中。

---

### H3 — High — API Registry 声称“其他文档只能引用，不得重新声明”，但派生 reference/spec 仍在重声明

`api-registry.md` 明确写：“其他文档只能引用，不得重新声明可冲突的表格或列表”。但当前：

- `commands.md` 重新声明 CommandAction 示例、拒绝原因表、特殊攻击清单。
- `mcp-tools.md` 重新声明完整 MCP 工具分类。
- `host-functions.md` 重新声明 ABI 签名、预算、安全限制。
- `core/02-command-validation.md` 重新声明 command schema、失败码、限制值、旧 JSON 示例。
- `core/09-snapshot-contract.md` 重新声明错误类别和经济操作名。

**影响：**

即使 YAML→Registry 生成正确，开发者实际阅读的是这些更贴近任务的 reference/spec 文档。只要这些不是生成物，单源闭合就仍会反复破裂。

**建议：**

- 明确文档分层：
  - YAML：唯一机器源。
  - Registry：完整人类可读生成物。
  - `commands.md` / `mcp-tools.md` / `host-functions.md`：必须要么 100% 生成，要么只写教程文本并嵌入 Registry 片段。
  - core specs：可以写校验算法，但 enum/tool/signature/error 列表必须引用或生成。

---

### M1 — Medium — MCP naming model 不一致，破坏可预测性

当前 YAML active tools 使用资源式/列表式命名：

- `swarm_list_drones` / `swarm_get_drone`
- `swarm_list_deployments` / `swarm_get_deploy_status`
- `swarm_get_tick_trace` / `swarm_get_engine_stats`

旧文档保留动词/概念式命名：

- `swarm_explain_last_tick`
- `swarm_inspect_entity`
- `swarm_profile`
- `swarm_dry_run_commands`
- `swarm_list_modules`
- `swarm_rollback`

这些名字不是单纯 alias，而是表达不同的对象模型。尤其 `module` vs `deployment`、`dry_run_commands` vs `dry_run(wasm_bytes,tick_count)` 会影响客户端参数设计。

**建议：**

如果需要兼容 alias，必须在 YAML 中以 `aliases` / `deprecated_names` 显式声明，并给出 deprecation policy。否则旧名称应从所有面向开发者文档中删除。

---

### M2 — Medium — Onboarding profile 还没有形成真正的“5 分钟上手”闭环

`design/interface.md` 曾要求 onboarding 包含 `swarm_get_server_trust`、CSR、docs/schema/status/deploy 等工具；YAML 当前 onboarding categories 是 Onboarding + Auth + SDK + Resources，但缺少清晰的最短路径叙事。

当前新 AI agent 不知道应该按哪个流程接入：

1. `swarm_auth_login` 获取 token？
2. `swarm_sdk_fetch` 拉 SDK？
3. `swarm_validate_module` / `swarm_deploy` 部署？
4. `swarm_get_snapshot` / `swarm_list_drones` 读取世界？

这些工具在 YAML 中存在，但教程/接口文档仍指向旧 CSR/trust/schema 工具。

**建议：**

从 YAML 生成一个 `Quickstart: AI agent onboarding`：

```text
1. swarm_get_info
2. swarm_auth_login
3. swarm_sdk_fetch(language="typescript")
4. compile WASM
5. swarm_validate_module
6. swarm_deploy
7. swarm_get_deploy_status
8. swarm_get_snapshot / swarm_list_drones
```

如果真实设计仍需要 CSR/应用层证书，则必须把对应 tools 重新放入 YAML active tools，而不是只存在于设计文档。

---

## 3. 亮点 / Strengths

1. **YAML IDL 本体质量明显提升**：`api_version`、`total_variants`、`total_tools`、`total_functions`、`total_fields` 等机器可验证字段齐全，适合作为 codegen/CI 的输入。
2. **YAML ↔ API Registry 主链路基本闭合**：CommandAction 19、MCP active tools 46、Host Functions 5、TickTrace 22、Direction4 等关键计数在 YAML 与 Registry 中一致。
3. **MCP tool schema 方向正确**：每个 YAML tool 都带有 `input_schema`、`output_schema`、`rate_limit`、`required_scope`、`subject_source`、`replay_class`、`visibility_filter`、`rate_limit_key`，比之前单纯工具名列表更接近可生成 MCP server/client 的合同。
4. **RejectionReason 的 canonical/debug_detail 分层是正确 DX 方向**：wire enum 稳定，细节进入 `debug_detail`，这是兼顾 SDK 稳定性与调试可用性的设计。
5. **Host ABI error priority table 是必要且有价值的**：对于 WASM host call，同一调用可能同时触发内存越界、预算耗尽、不可见等错误，明确优先级能避免 replay/debug 不一致。
6. **Deploy mutation + fdb_version_counter 对 API 幂等性与 replay 友好**：`swarm_deploy` 输出中加入 `fdb_version_counter` 和 `object_store_key`，让异步 blob 上传与确定性排序有了可观察合同。

---

## 4. Missing / 需要补齐

1. **生成器合同缺失**：目前文档声明 `api-registry.md` 由 YAML 生成，但未在可读文件中说明生成器输入、输出、禁止手写区域、CI 校验命令、漂移检测方式。
2. **IDL schema 自身缺失**：`game_api.idl.yaml` 是事实源，但没有看到描述该 YAML 结构的 meta-schema。缺少 meta-schema 会让贡献者不知道哪些字段必填，生成器也难以稳定验证。
3. **别名/弃用机制缺失**：旧工具名、旧错误码、旧 action 模型仍散落在文档中。如果要兼容，必须在 YAML 中表达；如果不兼容，必须删除。
4. **SDK 生成目标缺少明确映射**：TypeScript/Rust SDK 应如何从 YAML 生成：enum 命名、string literal union、error class、MCP client method、host ABI imports、版本检查策略，目前尚未形成完整合同。
5. **Quickstart 缺失**：API Registry 是完整参考，但没有一个从认证、拉 SDK、写 tick、部署、查询状态到读取错误的最小闭环示例。

---

## 5. API Consistency Issues

### 5.1 命名一致性

- `InsufficientResource` vs `InsufficientResources`：Registry/YAML 使用单数，interface/snapshot 仍使用复数。
- `swarm_dry_run` vs `swarm_dry_run_commands`：YAML 与旧 MCP 文档冲突。
- `swarm_list_deployments` / `swarm_get_deploy_status` vs `swarm_list_modules` / `swarm_rollback`：部署对象模型冲突。
- `swarm_auth_login` / `swarm_auth_refresh` vs CSR/certificate 工具体系：认证模型冲突。
- `CommandAction` 19 core variants vs `CommandAction::Custom(type)` 旧模型：action extension 模型冲突。

### 5.2 Schema 一致性

- `CommandIntent` 当前应为 `{ sequence, action: { type, ... } }`，但 `core/02-command-validation.md` 后半仍出现 `{ "action": "RangedAttack", ... }` 旧格式。
- Host ABI 签名在 YAML/Registry 与 `host-functions.md` 不一致。
- MCP tool input/output schema 在 YAML 中较完整，但 `mcp-tools.md` 只列工具说明，没有同步 input/output/error schema。
- SwarmError envelope 在 YAML/Registry 与 `design/interface.md` 不一致。

### 5.3 Error DX 一致性

当前错误系统同时出现：

- JSON-RPC `error.code = -32000`；
- JSON-RPC `error.code = RejectionReason string`；
- `data.swarm_error`；
- `rejection` 字段；
- `debug_detail`；
- `detail` / `fix_hint` / `debug`。

建议将外部 wire envelope 收敛为一个生成 schema，并把 hint ladder 作为 `debug_detail`/`hint` 的模式化扩展，而不是另起一套错误类别。

---

## 6. CrossCheck

### 6.1 本轮只读文件

按任务限制，仅阅读以下文件：

- `/tmp/swarm-review-R18/design/README.md`
- `/tmp/swarm-review-R18/design/interface.md`
- `/tmp/swarm-review-R18/design/tech-choices.md`
- `/tmp/swarm-review-R18/specs/reference/game_api.idl.yaml`
- `/tmp/swarm-review-R18/specs/reference/api-registry.md`
- `/tmp/swarm-review-R18/specs/reference/commands.md`
- `/tmp/swarm-review-R18/specs/reference/host-functions.md`
- `/tmp/swarm-review-R18/specs/reference/mcp-tools.md`
- `/tmp/swarm-review-R18/specs/core/02-command-validation.md`
- `/tmp/swarm-review-R18/specs/core/09-snapshot-contract.md`

未读取 `/data/swarm/` 代码仓库、旧 reviews、或列表外文档。

### 6.2 机器交叉检查摘要

使用 `python3 + PyYAML` 对 YAML 与 Markdown 做结构检查，结果：

```text
YAML api_version: 0.3.0
CommandAction declared: 19, actual variants: 19
MCP tools declared: 46, actual tools: 46
Host functions declared: 5, actual functions: 5
RejectionReason declared canonical codes: 35, actual indexed variants: 35, all entries incl pipeline: 37
MCP category counts: Admin 6, Auth 2, Debug 7, Deploy 6, Onboarding 8, Play 14, Resources 2, SDK 1
```

YAML ↔ `api-registry.md`：

```text
YAML active tools: 46
Registry active tools: 46 semantically aligned
Regex-visible extra: swarm_list_market_orders, but only in RFC/Future section and not active
```

YAML ↔ `design/interface.md` / `mcp-tools.md`：

```text
interface.md tool-like names: 51
mcp-tools.md tool-like names: 52
Both are heavily drifted from YAML active tools:
- many YAML active tools missing
- many old/non-active tools still listed
```

YAML ↔ `commands.md`：

```text
YAML actions: 19 core variants
commands.md type examples include all 19, but also Leech and Fabricate as type examples
commands.md prose still says 15 + Custom(type) + 8 special attacks
```

YAML ↔ `host-functions.md`：

```text
host_get_terrain signature drift
host_path_find signature drift
host_get_world_rules signature drift
budget error code drift (-1 vs ERR_BUDGET_EXHAUSTED / ERR_PLAYER_BUDGET / ERR_GLOBAL_BUDGET)
```

### 6.3 结论

R18 已经解决了“有没有一个机器事实源”的核心方向问题，但还没有解决“所有开发者入口是否都由这个事实源派生”的闭环问题。API/DX 的通过条件应是：

1. YAML 与 Registry 继续保持当前闭合；
2. `commands.md`、`mcp-tools.md`、`host-functions.md` 至少关键表格和示例由 YAML 生成；
3. `design/interface.md` 不再手写 active tool catalog；
4. `core/02` 与 `core/09` 不再使用非 canonical wire enum 或旧 JSON shape；
5. 提供一个从 YAML 生成的 AI agent 5-minute quickstart。

在这些完成前，建议不要让 SDK、MCP server 或 WASM ABI 实现依赖当前文档集。