# R30 API/开发者体验独立评审 — GPT-5.5

## 1. Verdict

REQUEST_MAJOR_CHANGES

当前设计的 API/DX 方向已经建立了 IDL → Registry → SDK/Docs 的正确总体架构，但多份面向开发者的派生文档仍然与 Registry 的权威 schema、工具数量、错误 envelope、CommandAction 参数和 Host Function ABI 存在直接冲突。由于这些冲突会直接破坏 TypeScript SDK 类型生成、IDE 自动补全、MCP 客户端调用体验和错误处理一致性，必须在进入实现前统一修复。

## 2. 发现的问题

### APIDX-H1 — MCP 工具数量与分组在多个文档中不一致

- Severity: High
- 文件引用:
  - `/tmp/swarm-review-R30/design/interface.md:19`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:211`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:228`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:230`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:246`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:256`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:321`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:866`
  - `/tmp/swarm-review-R30/specs/reference/mcp-tools.md:5`
  - `/tmp/swarm-review-R30/specs/reference/mcp-tools.md:13`
- 问题描述: `interface.md` 声称 “56 game tools + 11 auth tools”，`mcp-tools.md` 也写 “56 个 Game API 活跃工具 + 11 个 Auth API 工具”，但 `api-registry.md` 正文写 “57 个活跃工具 + 11 个 Auth API 工具”。同时 Registry 的实际分组包含 Onboarding 11、Auth 3、Play 15、Deploy 7、Debug 8、Admin 6、SDK 1、Arena 5、Resources 2，按表计数为 58；而 changelog 又说 “56 active”。`mcp-tools.md` 的分组表则写 Onboarding 10、Auth 2、Play 16、Arena 4。
- 影响分析: MCP 客户端 capability discovery、SDK 代码生成、文档导航和 AI agent 自举都会得到互相矛盾的工具面。IDE 自动补全与 `swarm_get_schema` 暴露的工具清单若按不同文档生成，会出现 “文档说存在但 schema 不存在” 或 “schema 有但文档遗漏” 的失败模式。
- 修复建议: 以 IDL YAML 为唯一源重新生成 Registry，并让 `mcp-tools.md` 只引用生成出的 machine-readable summary，不再手写工具数量与分组计数。若 `swarm_auth_check`、`swarm_get_objectives`、`swarm_get_leaderboard` 等是 active 工具，则统一更新所有计数；若不是 active，则从 Registry active 表移出或标注为 alias/deprecated/host-only，确保每个工具只能被一个明确计数集合包含。

### APIDX-H2 — CommandAction 参数命名与形状在 Registry、commands、validation 三处冲突

- Severity: High
- 文件引用:
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:41`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:54`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:58`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:59`
  - `/tmp/swarm-review-R30/specs/reference/commands.md:83`
  - `/tmp/swarm-review-R30/specs/reference/commands.md:93`
  - `/tmp/swarm-review-R30/specs/reference/commands.md:117`
  - `/tmp/swarm-review-R30/specs/core/02-command-validation.md:209`
  - `/tmp/swarm-review-R30/specs/core/02-command-validation.md:260`
  - `/tmp/swarm-review-R30/specs/core/02-command-validation.md:279`
  - `/tmp/swarm-review-R30/specs/core/02-command-validation.md:704`
- 问题描述: Registry 明确声明所有 21 个 CommandAction 均包含公共 `object_id`，且 `Build` 参数为 `structure_type`，`Spawn` 参数为 `body_parts, spawn_id`，`Recycle` 参数为 `target_id`。但 `commands.md` 的 `Spawn` 示例缺少 `object_id`，`Build` 使用 `structure` 而不是 `structure_type`；`02-command-validation.md` 的 `Spawn` 使用 `body` 而不是 `body_parts`，`Recycle` 一处使用 `spawn_id`，另一处只包含 `object_id`。这些不是术语差异，而是 wire schema 形状冲突。
- 影响分析: TypeScript SDK 会在 `body`/`body_parts`、`structure`/`structure_type`、`target_id`/`spawn_id` 之间生成互不兼容的类型。玩家按示例写代码会被 schema validation 拒绝；AI agent 通过 MCP `swarm_get_docs` 生成策略时也会产生错误 JSON。公共 `object_id` 是否存在尤其关键，因为它影响所有 action union 的 discriminated type 设计。
- 修复建议: 为 `CommandAction` 定义一个 canonical JSON representation，并在 Registry 中生成所有示例。建议 TS SDK 使用 discriminated union：`{ type: 'Spawn'; object_id: EntityId; spawn_id: SpawnId; body_parts: BodyPart[] }` 等。`commands.md` 和 `02-command-validation.md` 禁止手写字段名，只保留解释性文本或嵌入 codegen 生成的示例块。

### APIDX-H3 — JSON-RPC 错误 envelope 存在两套互斥字段

- Severity: High
- 文件引用:
  - `/tmp/swarm-review-R30/design/interface.md:130`
  - `/tmp/swarm-review-R30/design/interface.md:140`
  - `/tmp/swarm-review-R30/design/interface.md:142`
  - `/tmp/swarm-review-R30/design/interface.md:143`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:668`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:681`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:691`
- 问题描述: `interface.md` 的错误 envelope 使用 `data.swarm_error`、`details`、`retry_allowed`、`idempotency_key`；Registry 的权威 envelope 使用 `data.rejection_reason`、`command_index`、`rejection_detail`、`debug_detail`，并要求 SDK 从 `rejection_reason` 生成 typed exception。两者字段名与语义均不兼容。
- 影响分析: SDK 无法提供稳定的 `SwarmError` 类型。调用者不知道应该捕获 `swarm_error` 还是 `rejection_reason`，也不知道重试语义是 envelope 字段还是由 rejection code 映射而来。MCP 客户端、Web UI 和 TS SDK 会各自实现错误解析，导致 DX 分裂。
- 修复建议: 统一为一个 envelope。建议保留 Registry 的 `rejection_reason` 作为 canonical wire code，同时补充 machine-readable `retry_allowed`、`idempotency_key`、`retry_after_tick?` 等字段到同一权威 schema；不要在 `interface.md` 另起 `swarm_error` 字段。所有错误字段应从 IDL 生成 TS 类型和 JSON Schema。

### APIDX-H4 — RejectionReason canonical enum 与校验文档中的失败码不闭合

- Severity: High
- 文件引用:
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:88`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:123`
  - `/tmp/swarm-review-R30/specs/core/02-command-validation.md:169`
  - `/tmp/swarm-review-R30/specs/core/02-command-validation.md:171`
  - `/tmp/swarm-review-R30/specs/core/02-command-validation.md:269`
  - `/tmp/swarm-review-R30/specs/core/02-command-validation.md:374`
  - `/tmp/swarm-review-R30/specs/core/02-command-validation.md:375`
  - `/tmp/swarm-review-R30/specs/core/02-command-validation.md:548`
- 问题描述: Registry 规定 47 个 canonical code，并强调旧码应降级为 `debug_detail`。但 `02-command-validation.md` 仍把 `TileBlocked`、`StillSpawning`、`ExceedsRoomCapacity`、`InvalidDamageType`、`AlreadyDebilitated(damage_type)`、`MainActionQuotaExceeded` 等写作失败码，其中部分不在 Registry canonical enum 中，也未标注为 `debug_detail`。
- 影响分析: SDK typed exception 无法穷尽处理校验文档列出的失败码；玩家会在文档中看到无法从 wire enum 接收的错误名。更严重的是，competitive/practice/training 的 hint ladder 依赖错误类别稳定，未注册错误会破坏错误消息分级与安全脱敏。
- 修复建议: 对 `02-command-validation.md` 做一次 canonicalization pass：每个失败条件必须映射到 Registry 中已有 `RejectionReason`，或显式写为 `debug_detail`，或正式新增到 IDL enum。建议增加一个生成的 “condition → rejection_reason → debug_detail key” 表，并由 CI 检查所有失败码均存在于 IDL。

### APIDX-H5 — Host Function ABI 返回值语义自相矛盾

- Severity: Medium
- 文件引用:
  - `/tmp/swarm-review-R30/design/interface.md:85`
  - `/tmp/swarm-review-R30/design/interface.md:122`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:404`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:445`
  - `/tmp/swarm-review-R30/specs/reference/host-functions.md:27`
  - `/tmp/swarm-review-R30/specs/reference/host-functions.md:35`
- 问题描述: `interface.md` §5.1 与 `host-functions.md` 说明 `ret >= 0 = bytes_written, ret < 0 = canonical ABI error code`；但 `interface.md` §5.5 又写 “所有 host function 返回 i32（0=成功，负数=错误码）”。Registry 只列 ABI 签名和错误优先级，没有显式重申成功返回值是 bytes_written 还是 0。
- 影响分析: WASM SDK 的 buffer allocation pattern 完全依赖返回语义。若成功返回 0，调用者无法知道实际写入长度；若成功返回 bytes_written，SDK 可以安全切片解析。模糊语义会导致 TS/Rust SDK wrapper、C ABI binding 和玩家手写代码出现不兼容实现。
- 修复建议: 明确单一 ABI 合同：建议采用 `ret >= 0 = bytes_written`，`ret < 0 = HostAbiErrorCode`。在 Registry §4.1 或 §4.5 增加 “Return Semantics” 表，并删除 `0=成功` 的说法。SDK wrapper 应生成 `Result<Uint8Array, HostAbiError>` / `Result<Vec<u8>, HostAbiError>`。

### APIDX-H6 — MCP `swarm_simulate` schema 与设计说明不一致

- Severity: Medium
- 文件引用:
  - `/tmp/swarm-review-R30/design/interface.md:154`
  - `/tmp/swarm-review-R30/design/interface.md:156`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:300`
  - `/tmp/swarm-review-R30/specs/core/09-snapshot-contract.md:108`
  - `/tmp/swarm-review-R30/specs/core/09-snapshot-contract.md:127`
  - `/tmp/swarm-review-R30/specs/core/09-snapshot-contract.md:140`
- 问题描述: `interface.md` 描述 `swarm_simulate` 为 “给定 snapshot 离线模拟 N tick”，最大 100 tick；Registry 的 input schema 却是 `{commands, assumptions}`，输出 `{trace, authoritative: false, assumptions, confidence}`；Snapshot Contract 的流程又写 `swarm_simulate(world_state, drone_id, action)`，输出包含 `not_predictive`、`rng_ordinals_consumed`、`fuel_consumed`、`tick_trace_written`。
- 影响分析: AI agent 和 IDE 无法从文档推断正确调用方式。`snapshot`、`world_state`、`commands`、`assumptions` 是不同抽象层；如果 SDK 只按 Registry 生成，设计文档中的示例无法调用；如果 MCP server 按设计文档实现，则 Registry schema 错误。
- 修复建议: 统一 `swarm_simulate` 的产品级 API。建议 input 明确为 `{snapshot?: SnapshotRef | SnapshotInline, commands: CommandIntent[], tick_count: u32, assumptions?: SimulationAssumptions, hint_level?: HintLevel}`，output 明确包含 `authoritative: false`、`not_predictive: true`、`deterministic?: false`。`swarm_dry_run` 则单独生成 deterministic schema，不与 simulate 混用。

### APIDX-H7 — `swarm_deploy` 的二进制上传形态对 MCP/DX 不够明确

- Severity: Medium
- 文件引用:
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:281`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:789`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:790`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:794`
  - `/tmp/swarm-review-R30/specs/reference/mcp-tools.md:33`
- 问题描述: Registry 的 `swarm_deploy` input 为 `{player_id, drone_id, wasm_bytes, metadata}`，但 Deploy Flow 又描述 “WASM blob 通过 async_object_store_upload 上传至 object store”，输出包含 `object_store_key`。MCP 工具是 JSON-RPC 工具面，但文档没有说明 `wasm_bytes` 的编码方式、大小上限、分片/预签名上传路径、hash precommit、或 `swarm_validate_module` 与 `swarm_deploy` 是否都接受内联二进制。
- 影响分析: TS SDK 与 MCP 客户端可能把 WASM 作为 base64 字符串塞进 JSON-RPC，触发大 payload、内存膨胀和代理限制；另一些客户端可能先上传 object store key，导致服务端 schema 不匹配。AI agent 自举部署是核心路径，二进制上传不清晰会显著降低 DX。
- 修复建议: 明确二进制传输合同。建议 `swarm_deploy` 支持两种互斥输入：`wasm_base64`（小模块，明确 max size）或 `upload_ref`（由 `swarm_create_upload`/预签名 URL 或 MCP resource upload 返回）。IDL 中用 tagged union 表达，并要求 `module_hash`/`idempotency_key` 必填，避免同一二进制重复扣费。

### APIDX-M1 — Rhai RuleMod API 对模组作者仍偏 stringly-typed，缺少可生成的类型与错误枚举

- Severity: Medium
- 文件引用:
  - `/tmp/swarm-review-R30/specs/reference/rhai-mod-abi.md:46`
  - `/tmp/swarm-review-R30/specs/reference/rhai-mod-abi.md:92`
  - `/tmp/swarm-review-R30/specs/reference/rhai-mod-abi.md:111`
  - `/tmp/swarm-review-R30/specs/reference/rhai-mod-abi.md:123`
  - `/tmp/swarm-review-R30/specs/reference/rhai-mod-abi.md:152`
- 问题描述: Rhai ABI 定义了 hooks、`query.*`、`actions.*` 和 capability，但大量关键参数仍是裸 `string` 或未展开结构，如 `resource`, `reason`, `event_type`, `key`, `flag`, `data`。错误传播表也没有给出 `actions.*` 返回值类型、错误码集合或脚本可捕获的异常形态。
- 影响分析: 模组作者无法获得可靠补全，IDE/语言服务器也难以生成 stub。`actions.set_world_param(key, value)` 和 `actions.set_entity_flag(entity_id, flag, value)` 这类 API 极易拼错 key 或传错 value 类型，只有运行时失败，降低 Rhai mod 的可用性与可调试性。
- 修复建议: 增加 Rhai ABI IDL 或 machine-readable manifest，生成 `resources.Energy`、`flags.ImmuneThermal`、`events.ModDegraded`、`world_params.overload.fuel_recovery_rate` 等常量模块。所有 `actions.*` 应统一返回 `Result<T, RhaiActionError>`，并列出可捕获错误 enum、错误消息、审计字段与 hint level 映射。

### APIDX-M2 — 文档仍暴露 “MVP/Future/Phase” 术语，削弱目标状态 API 合同

- Severity: Medium
- 文件引用:
  - `/tmp/swarm-review-R30/specs/core/09-snapshot-contract.md:1`
  - `/tmp/swarm-review-R30/specs/core/09-snapshot-contract.md:14`
  - `/tmp/swarm-review-R30/specs/core/09-snapshot-contract.md:181`
  - `/tmp/swarm-review-R30/specs/core/09-snapshot-contract.md:254`
  - `/tmp/swarm-review-R30/specs/core/09-snapshot-contract.md:417`
- 问题描述: 任务评审原则要求设计文档呈现最终目标状态，不区分 Phase/MVP/迭代。但 `09-snapshot-contract.md` 标题和多处正文仍使用 “MVP Economy Boundaries”、“MVP 中必须完整实现”、“Future RFC”、“兼容性与迁移 Future”等措辞。
- 影响分析: 从 API/DX 角度，玩家与 SDK 作者会误判哪些能力当前可依赖、哪些只是临时边界。尤其经济与 Allied Transfer 是玩家策略和 SDK 类型的重要组成；“MVP/Future” 叙述会让目标 API 合同变得像路线图而非规范。
- 修复建议: 将文档改写为目标状态语言：核心经济操作、受限 Allied Transfer、非核心扩展能力分别以 “Core Contract”、“Optional Extension / RFC Extension” 或 “Not in Core API” 表达。不要使用 MVP/Phase 作为 API 可用性边界。

### APIDX-L1 — 文档相对链接在拆分后存在错误路径，影响开发者导航

- Severity: Low
- 文件引用:
  - `/tmp/swarm-review-R30/design/interface.md:9`
  - `/tmp/swarm-review-R30/design/interface.md:29`
  - `/tmp/swarm-review-R30/design/interface.md:83`
  - `/tmp/swarm-review-R30/design/tech-choices.md:3`
- 问题描述: `design/interface.md` 位于 `design/` 目录，但多处链接写成 `specs/reference/...`，从该文件相对路径解析会指向 `design/specs/reference/...`，而实际文件在 `../specs/reference/...`。`tech-choices.md` 也使用 `specs/core/...` 形式，存在同类导航问题。
- 影响分析: 文档站、IDE Markdown preview 和 GitHub/Gitea 浏览会产生 404。API/DX 文档最关键的 Registry、IDL、Auth schema 链接失效，会妨碍新开发者自助理解。
- 修复建议: 统一运行 markdown link check。`design/*.md` 中指向 specs 的链接应使用 `../specs/...`；或者采用文档站绝对根路径并在构建时校验。

## 3. 亮点

- IDL-first 架构方向正确：`api-registry.md` 明确声明 IDL YAML 是机器可读唯一源，并要求 Registry/SDK/Docs 由 codegen 生成，这是避免 SDK 与 MCP schema 漂移的正确基础。
- MCP 与游戏动作边界清晰：`design/interface.md` 明确 MCP 不提供 `swarm_move`/`swarm_attack` 等动作工具，AI agent 必须通过 WASM 策略参与，与人类玩家路径一致，公平性与开发体验都更干净。
- Capability Profiles 是好的 DX 抽象：`onboarding`、`play`、`deploy`、`debug`、`admin`、`arena` 能让 MCP 客户端按场景暴露工具，减少 AI agent 工具面噪声。
- 错误提示分级设计有价值：competitive/practice/training 的 hint ladder 能兼顾竞技安全与新手调试体验，只需与 canonical RejectionReason 和 JSON-RPC envelope 统一即可落地为优秀 SDK 异常层。
- Fixed-point registry 覆盖全面：`ResourceRate_i64`、`BasisPoints`、`milli_distance`、`micro_cost` 等类型对 TS/Rust SDK 都有明确生成价值，能减少浮点不确定性和单位误用。
- Rhai RuleMod ABI 有清晰的命名空间分层：`query.*` 只读、`actions.*` 写入 buffer 的设计直观，事务性语义和 capability gate 也为服主与模组作者建立了可理解的 mental model。

## 4. CrossCheck — 需要跨方向检查

- CX-1: `api-registry.md` 工具数量、CommandAction 数量与 IDL 源是否真实一致 → 建议 Tooling/CI 方向检查 codegen 是否真的覆盖 `mcp-tools.md`、`commands.md`、`02-command-validation.md` 中的派生字段与计数。
- CX-2: `swarm_deploy` 的 object store 异步上传与 FDB manifest 提交顺序是否存在 “accepted 但 blob permanent failure” 的状态歧义 → 建议 Persistence/Architecture 方向检查 deploy 状态机、重试与 replay-critical subset。
- CX-3: WebSocket `Swarm-Request-Signature` 用 header 承载每消息签名是否适用于真实 WS frame → 建议 Security/Protocol 方向检查 WS 握手签名、frame-level MAC 与 seq 更新模型。
- CX-4: Rhai `actions.award`、`actions.deduct` 作用于 “全局资源池” 是否可能绕过 Resource Ledger 单入口审计 → 建议 Economy/Security 方向检查 RuleMod action 与 ledger operation 的一致性。
- CX-5: Snapshot Contract 中 “simulate 可传入 hint_level 覆盖世界默认值（仅限训练模式提升，不允许降级）” 是否会在竞技环境泄露 debug detail → 建议 Security/Gameplay 方向检查 hint escalation 权限边界。
- CX-6: `NotVisibleOrNotFound` 与 Registry 中仍保留 `ObjectNotFound`、`TargetNotVisible` 的适用边界是否足够严格 → 建议 Security/API 方向共同检查 oracle-inference 防护是否覆盖所有 target_id/player_id 查询。
