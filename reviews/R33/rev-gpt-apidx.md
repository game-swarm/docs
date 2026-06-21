# R33 API/DX Review — GPT-5.5

## Verdict
REQUEST_MAJOR_CHANGES

本轮 API/DX 评审结论为 REQUEST_MAJOR_CHANGES。核心原因是 IDL → Registry → 派生文档 → codegen 的单事实源链条仍存在多处阻塞级漂移：MCP 工具数量/分类不一致、Host Function 集合不一致、CommandAction 示例与 IDL schema 不一致、SwarmError envelope 在 IDL 与 Registry 中冲突。这些问题会直接破坏 TypeScript/Rust SDK codegen、MCP schema 暴露、IDE 自动补全与错误处理合同。

## Critical (必须修复，否则 BLOCK) (B1..Bn)

### B1. MCP 工具注册表与 IDL/派生文档数量和分类不一致
- Severity: Critical
- 文件引用:
  - /data/swarm/docs/specs/reference/api-registry.md:262
  - /data/swarm/docs/specs/reference/api-registry.md:277
  - /data/swarm/docs/specs/reference/api-registry.md:295
  - /data/swarm/docs/specs/reference/api-registry.md:305
  - /data/swarm/docs/specs/reference/api-registry.md:326
  - /data/swarm/docs/specs/reference/api-registry.md:340
  - /data/swarm/docs/specs/reference/api-registry.md:370
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:498
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:502
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:700
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:734
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:978
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:1093
  - /data/swarm/docs/specs/reference/mcp-tools.md:5
  - /data/swarm/docs/specs/reference/mcp-tools.md:17
  - /data/swarm/docs/specs/reference/mcp-tools.md:19
  - /data/swarm/docs/specs/reference/mcp-tools.md:24
  - /data/swarm/docs/specs/reference/mcp-tools.md:26
  - /data/swarm/docs/specs/reference/codegen.md:27
- 问题描述: 同一 MCP 工具集合在多个权威/派生位置给出互相冲突的数量。Registry 声称 game_api.idl.yaml 有 57 tools，且表中分类为 Onboarding 11、Auth 3、Play 15、Deploy 7、Debug 8、Arena 5、Resources 2；game_api.idl.yaml 注释仍写 “46 tools”，total_tools 为 57，但分组注释写 Auth 2、Play 14、Deploy 6、Debug 7；mcp-tools.md 又声明 “56 个 Game API 活跃工具 + 11 Auth API 工具”，表格为 Onboarding 10、Play 16、Arena 4、Game API 小计 56；codegen.md 也写 MCP tool 当前 56 active。实际人工/脚本核对 game_api.idl.yaml 中 active tools 条目为 57，不含 RFC tool。
- 影响分析: 这是 SDK 和 MCP schema 的阻塞级 DX 问题。生成器无法判断应生成 56 还是 57 个 Game API 工具，也无法判断 auth shortcut 是否包含 swarm_auth_check，Arena 是否包含 swarm_get_leaderboard，Onboarding 是否包含 swarm_get_objectives。TypeScript SDK 会出现缺失方法或多生成方法，MCP clients 的 capability profile 自动补全也会与文档不同步。
- 修复建议: 以 game_api.idl.yaml 的结构化 tools 列表为唯一机器源，重新生成 api-registry.md，并同步修正 mcp-tools.md 与 codegen.md 中所有手写计数。若 game_api Auth shortcuts 目标为 3 个，则必须把 swarm_auth_check 回写到 game_api.idl.yaml；若目标为 2 个，则必须从 api-registry.md 删除 game_api §3.2 Auth 的 swarm_auth_check 并修正总数。修复后 CI 应校验 per-category count 与 total_tools，而不仅校验 markdown diff。

### B2. Host Function 集合在 Registry/interface 与 game_api.idl.yaml/host-functions.md 之间不一致
- Severity: Critical
- 文件引用:
  - /data/swarm/docs/design/interface.md:68
  - /data/swarm/docs/design/interface.md:72
  - /data/swarm/docs/design/interface.md:83
  - /data/swarm/docs/specs/reference/api-registry.md:455
  - /data/swarm/docs/specs/reference/api-registry.md:464
  - /data/swarm/docs/specs/reference/api-registry.md:477
  - /data/swarm/docs/specs/reference/api-registry.md:489
  - /data/swarm/docs/specs/reference/api-registry.md:500
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:1506
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:1510
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:1512
  - /data/swarm/docs/specs/reference/host-functions.md:9
  - /data/swarm/docs/specs/reference/host-functions.md:61
  - /data/swarm/docs/specs/reference/host-functions.md:71
- 问题描述: api-registry.md 注册 6 个 Host Functions，新增 `host_get_random`，并定义其预算、输出上限和 fuel 成本；但 game_api.idl.yaml 的 host_functions.total_functions 仍为 5，函数列表不含 host_get_random；host-functions.md 允许 import 列表和详细签名也只有 5 个；design/interface.md 的概念签名同样只列 5 个并称权威定义见 Registry。
- 影响分析: Host Function ABI 是 WASM SDK、Rust bindings、TypeScript wasm helper 类型和沙箱 import allowlist 的硬合同。当前状态下 SDK 可能生成 `host_get_random`，但 sandbox allowlist/IDL 驱动实现认为它不存在；或实现只支持 5 个但文档要求 6 个。对开发者表现为链接失败、运行时 import missing、IDE 自动补全误导。
- 修复建议: 先裁定目标状态是否包含 `host_get_random`。若包含，则在 game_api.idl.yaml §host_functions 添加第 6 项，并同步 host_call_output_limits、预算、codegen.md 当前 Host function 数量与 host-functions.md 的 allowlist/签名。若不包含，则从 api-registry.md 删除 `host_get_random` 相关表项。由于 Registry 声称由 IDL 生成，推荐方向是补齐 IDL 并重新生成。

### B3. CommandAction 示例字段与 IDL schema 冲突，会误导 SDK 用户
- Severity: Critical
- 文件引用:
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:125
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:129
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:167
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:171
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:286
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:289
  - /data/swarm/docs/specs/reference/commands.md:81
  - /data/swarm/docs/specs/reference/commands.md:84
  - /data/swarm/docs/specs/reference/commands.md:90
  - /data/swarm/docs/specs/reference/commands.md:93
  - /data/swarm/docs/specs/reference/commands.md:183
  - /data/swarm/docs/specs/core/02-command-validation.md:206
  - /data/swarm/docs/specs/core/02-command-validation.md:209
  - /data/swarm/docs/specs/core/02-command-validation.md:257
  - /data/swarm/docs/specs/core/02-command-validation.md:260
  - /data/swarm/docs/specs/core/02-command-validation.md:814
  - /data/swarm/docs/specs/core/02-command-validation.md:817
- 问题描述: game_api.idl.yaml 定义 Build 参数为 `structure_type`，但 commands.md 示例使用 `structure`；IDL 定义 Spawn 参数为 `body_parts` + `spawn_id`，commands.md 示例缺少公共 `object_id` 且使用 `body_parts`，02-command-validation.md 示例又使用 `body`；IDL 定义 Fabricate 只有 `target_id`，但 02-command-validation.md 示例额外使用 `structure_type`；Debilitate 在 IDL 中只有 target_id，派生/校验文档示例额外要求 `damage_type`。这些不是展示层措辞差异，而是 JSON schema 字段名差异。
- 影响分析: 对 TypeScript SDK 来说，示例通常会被用户直接复制，也会被 LLM agent 作为 few-shot 生成代码。字段名漂移会导致 `additionalProperties: false` 下的命令被整个 tick 输出拒绝，开发者只能看到 SchemaViolation/TickValidationFailed，体验非常差。
- 修复建议: 建立 `CommandAction` 示例由 IDL 自动生成的机制，至少对 commands.md 与 02-command-validation.md 中的 JSON 示例运行 schema lint。具体修正：统一 Build 为 `structure_type`；统一 Spawn 为 `object_id` + `spawn_id` + `body_parts`，或明确 Spawn 是唯一不含 actor object_id 的例外并同步 Registry line 43 的“所有 21 个变体均包含 object_id”；为 Debilitate/Fabricate 决定是否确实需要 `damage_type`/`structure_type`，需要则补入 IDL，不需要则删除示例字段。

### B4. SwarmError JSON-RPC envelope 在 IDL 与 Registry 中定义冲突
- Severity: Critical
- 文件引用:
  - /data/swarm/docs/specs/reference/api-registry.md:725
  - /data/swarm/docs/specs/reference/api-registry.md:731
  - /data/swarm/docs/specs/reference/api-registry.md:735
  - /data/swarm/docs/specs/reference/api-registry.md:738
  - /data/swarm/docs/specs/reference/api-registry.md:741
  - /data/swarm/docs/specs/reference/api-registry.md:761
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:1744
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:1747
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:1751
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:1752
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:1756
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:1759
  - /data/swarm/docs/design/interface.md:128
  - /data/swarm/docs/design/interface.md:130
- 问题描述: api-registry.md 要求标准 JSON-RPC numeric `error.code = -32000`，具体错误在 `error.data.rejection_reason`；game_api.idl.yaml 则声明 `error.code: RejectionReason (string)`，`reserved_code -32000` 仅用于 unclassified internal errors，并使用 `rejection_detail` 字段。design/interface.md 又跟 Registry 一致，引用 `rejection_reason`、`retry_allowed`、`idempotency_key`、`retry_after_tick`。
- 影响分析: SDK typed exception 生成依赖错误 envelope。当前两套 schema 会让客户端不知道应 switch `error.code` 还是 `error.data.rejection_reason`，也不知道字段名是 `debug_detail`、`rejection_detail` 还是两者都有。IDE 自动补全和 MCP tool error schema 都会不稳定。
- 修复建议: 以 Registry §8 当前更完整的机器可重试字段为目标合同，回写 game_api.idl.yaml：`error.code` 固定 JSON-RPC numeric，`error.data.rejection_reason` 为 canonical enum，并补齐 `retry_allowed`、`idempotency_key`、`retry_after_tick`。删除或 deprecate `rejection_detail`，避免两个同义字段。

### B5. “Registry 由 IDL 自动生成”的合同被当前文件状态直接违反
- Severity: Critical
- 文件引用:
  - /data/swarm/docs/specs/reference/api-registry.md:1
  - /data/swarm/docs/specs/reference/api-registry.md:3
  - /data/swarm/docs/specs/reference/api-registry.md:13
  - /data/swarm/docs/specs/reference/api-registry.md:39
  - /data/swarm/docs/specs/reference/api-registry.md:260
  - /data/swarm/docs/specs/reference/api-registry.md:451
  - /data/swarm/docs/specs/reference/codegen.md:7
  - /data/swarm/docs/specs/reference/codegen.md:8
  - /data/swarm/docs/specs/reference/codegen.md:36
  - /data/swarm/docs/specs/reference/codegen.md:40
- 问题描述: 文档多次声明 api-registry.md 由三份 IDL 自动生成、手写修改会被覆盖，CI diff check 会阻塞漂移。但本轮读到的实际内容已经出现 B1/B2/B4 级别的 Registry/IDL 不一致，说明生成链本身或文档产物状态不可信。
- 影响分析: 对 API/DX 来说，单事实源失效比单个字段错误更严重。开发者无法判断应该相信 IDL、Registry 还是 reference 文档；SDK 生成也无法成为可信边界。
- 修复建议: 在修正具体漂移后，把 CI Gate 提升为结构校验：解析 IDL 与 Registry 表格，校验 total count、per-category count、工具名集合、host function 集合、error envelope schema、CommandAction 参数集合。codegen.md 中 “本文档自身为手工维护” 的数值也应进入同一检查，或删除所有手写当前数值。

## High (强烈建议修复) (H1..Hn)

### H1. `object_id` / `actor_id` 公共字段合同与部分动作 schema 不一致
- Severity: High
- 文件引用:
  - /data/swarm/docs/specs/reference/api-registry.md:43
  - /data/swarm/docs/specs/reference/api-registry.md:45
  - /data/swarm/docs/specs/reference/api-registry.md:62
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:167
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:171
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:179
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:183
  - /data/swarm/docs/specs/reference/commands.md:84
- 问题描述: Registry 声明所有 21 个 CommandAction 变体均包含 `object_id` 公共字段，但 Spawn 的 IDL 参数只列 `body_parts` 和 `spawn_id`，commands.md Spawn 示例也没有 `object_id`。Recycle 又在 IDL 中把 `object_id` 列为 action 参数，而 Registry 说公共字段不在各 action 参数列重复列出。
- 影响分析: 这会影响 discriminated union 的生成方式：`object_id` 是顶层公共字段、action 内公共字段，还是部分 action 参数？TypeScript SDK 若用公共 base interface，可因 Spawn 例外而错误；若每个 action 单独生成，又会与 Registry 的公共字段合同冲突。
- 修复建议: 明确 `CommandIntent.action` 的结构：推荐统一为 `{ type, object_id, ...variantFields }`，Spawn 也带 `object_id` 作为发起 spawn 的 drone，`spawn_id` 作为目标结构。Recycle 的 `object_id` 不应重复列为 variant parameter，而应标注 self-action no target。若 Spawn 确实无 drone actor，则 Registry line 43 必须改为“除 Spawn 外”。

### H2. `global_storage` / `economy_operation` 分类命名不一致
- Severity: High
- 文件引用:
  - /data/swarm/docs/specs/reference/api-registry.md:66
  - /data/swarm/docs/specs/reference/api-registry.md:72
  - /data/swarm/docs/specs/reference/api-registry.md:73
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:197
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:200
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:212
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:1784
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:1786
- 问题描述: Registry 把 TransferToGlobal/TransferFromGlobal 分类为 `economy_operation`，game_api.idl.yaml 则分类为 `global_storage`。同一概念在 ResourceOperation 子集也继续用 `global_storage`。
- 影响分析: SDK 若生成 enum category、文档筛选、MCP `swarm_get_available_actions` 的分类提示，会出现不同字符串。对 IDE 自动补全、AI agent 根据 category 规划行为都不友好。
- 修复建议: 选择一个 canonical category wire 值。推荐使用 `economy_operation`，因为 Registry 已把它与 §10 Economy Operations 绑定；将 game_api.idl.yaml 中 `global_storage` 改为 `economy_operation`，若需要展示名可另加 `group: global_storage`。

### H3. Auth shortcut schema 与 canonical auth_api schema 差异需要机器可读映射
- Severity: High
- 文件引用:
  - /data/swarm/docs/specs/reference/api-registry.md:295
  - /data/swarm/docs/specs/reference/api-registry.md:299
  - /data/swarm/docs/specs/reference/api-registry.md:303
  - /data/swarm/docs/specs/reference/api-registry.md:397
  - /data/swarm/docs/specs/reference/api-registry.md:399
  - /data/swarm/docs/specs/reference/auth_api.idl.yaml:30
  - /data/swarm/docs/specs/reference/auth_api.idl.yaml:33
  - /data/swarm/docs/specs/reference/auth_api.idl.yaml:38
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:702
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:704
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:719
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:721
- 问题描述: game_api 中的 `swarm_auth_login`/`swarm_auth_refresh` 是简化 schema，auth_api 中是完整 canonical schema；Registry 通过 prose 和 `schema_source/alias_of` 表列说明 codegen 应跳过 shortcut，但 game_api.idl.yaml 本身没有 `schema_source` / `alias_of` 机器字段。且 Registry 还列出 `swarm_auth_check` shortcut，game_api.idl.yaml 不存在。
- 影响分析: codegen 读 IDL 时无法知道这些工具是 alias 还是真实工具，容易生成重复 auth client 或错误的 refresh 参数（`token` vs `refresh_token`）。
- 修复建议: 在 game_api.idl.yaml 的 shortcut 工具条目中加入机器字段 `schema_source: auth_api`、`alias_of: auth_api.swarm_auth_login` 等，并统一是否存在 `swarm_auth_check` shortcut。codegen 必须以这些字段跳过重复实现，只生成 re-export/compat wrapper。

### H4. Type registry 中单位与命名不稳定，影响 TS 类型品牌化
- Severity: High
- 文件引用:
  - /data/swarm/docs/specs/reference/api-registry.md:26
  - /data/swarm/docs/specs/reference/api-registry.md:31
  - /data/swarm/docs/specs/reference/api-registry.md:32
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:16
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:21
  - /data/swarm/docs/specs/reference/economy.idl.yaml:28
  - /data/swarm/docs/specs/reference/economy.idl.yaml:33
  - /data/swarm/docs/specs/reference/economy.idl.yaml:34
- 问题描述: Registry 把 `ResourceRate_i64` 写作 “1e6 = 1.0 resource/tick”，game_api.idl.yaml 注释也写 micro-units；economy.idl.yaml 中同名类型却描述为 “resource units per tick”，未明确 1e6 scale。`milli_distance` / `micro_cost` 又用小写类型名，和 PascalCase 类型风格不一致。
- 影响分析: TS SDK 最适合生成 branded integer types，例如 `type ResourceRate = Brand<bigint, 'micro_resource_per_tick'>`。当前单位不一致会导致经济 API 与游戏 API 对同名类型产生不同 runtime interpretation。
- 修复建议: 建立统一 type alias registry：同名类型必须完全相同，包括 underlying、scale、unit、range、rounding。推荐把 `ResourceRate_i64` 的 economy 定义改为 micro-units per tick；把 `milli_distance`/`micro_cost` 规范为 PascalCase wire type（可保留 alias）。

### H5. Snapshot/MCP 输出 schema 字段命名不一致
- Severity: High
- 文件引用:
  - /data/swarm/docs/specs/reference/api-registry.md:284
  - /data/swarm/docs/specs/core/09-snapshot-contract.md:32
  - /data/swarm/docs/specs/core/09-snapshot-contract.md:39
  - /data/swarm/docs/specs/core/09-snapshot-contract.md:50
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:530
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:539
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:540
- 问题描述: `swarm_get_snapshot` output_schema 为 `{tick, entities, terrain, resources, truncated, omitted_count}`；snapshot contract 要求截断快照包含 `drone_id` 与 `omitted_categories`，且 `omitted_categories` 每个键即使为 0 也必须存在。
- 影响分析: SDK 用户无法通过类型知道 `omitted_count` 是总数还是分类数，也无法根据 Snapshot Contract 写稳定处理逻辑。MCP 工具返回的 snapshot 与 WASM `tick()` 输入是否同构也变得不清晰。
- 修复建议: 统一 snapshot output schema。推荐将 `omitted_count` 替换为 `omitted_categories: {entities: u32, resources: u32, events: u32}`，并补充 `drone_id?` 或解释 MCP player-level snapshot 与 per-drone perception snapshot 的差异。

### H6. RejectionReason 引用了未注册错误码
- Severity: High
- 文件引用:
  - /data/swarm/docs/specs/core/02-command-validation.md:541
  - /data/swarm/docs/specs/core/02-command-validation.md:547
  - /data/swarm/docs/specs/core/09-snapshot-contract.md:455
  - /data/swarm/docs/specs/reference/api-registry.md:94
  - /data/swarm/docs/specs/reference/api-registry.md:127
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:300
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:332
- 问题描述: 02-command-validation.md 的拒绝码表使用 `MainActionQuotaExceeded`，snapshot admission 使用 `ERR_CPU_SATURATED`，但 Registry/game_api.idl.yaml 的 canonical RejectionReason 中没有这些码，也没有明确映射到 debug_detail 或 host ABI error。
- 影响分析: 错误处理 DX 会破裂：开发者看到文档中的错误码却无法在 SDK enum 中 switch；CI 也无法保证 validator 返回 canonical enum。
- 修复建议: 要么把这些条件映射到现有 canonical code（例如 `CommandBufferFull` / `ServerOverloaded`）并用 `debug_detail` 表达，要么正式新增到 IDL 的 RejectionReason。所有 reference/core 文档不得出现未注册 wire code。

## Medium (建议关注) (M1..Mn)

### M1. `swarm_sdk_fetch` 的 output examples 类型不一致
- Severity: Medium
- 文件引用:
  - /data/swarm/docs/design/interface.md:104
  - /data/swarm/docs/specs/reference/api-registry.md:368
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:1321
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:1324
- 问题描述: design/interface.md 与 api-registry.md 写 `examples: string[]` / `examples: string[]`，game_api.idl.yaml 写 `examples: string`。
- 影响分析: 该工具是 AI agent 自举入口，examples 类型漂移会直接影响 SDK fetch client 的反序列化与 IDE 补全。
- 修复建议: 改为结构化数组，例如 `examples: [{name: string, language: string, code: string}]`；若暂不需要元数据，至少统一为 `[string]`。

### M2. `rate_limit: null # host fn only` 出现在 MCP tools 中，概念边界不清
- Severity: Medium
- 文件引用:
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:782
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:790
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:797
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:807
  - /data/swarm/docs/specs/reference/api-registry.md:312
  - /data/swarm/docs/specs/reference/api-registry.md:313
- 问题描述: `swarm_get_terrain` 和 `swarm_get_path` 被列为 MCP Play tools，但 rate_limit 为 host fn only。名字又与 `host_get_terrain` / `host_path_find` 高度重叠。
- 影响分析: MCP 客户端会以为这些是可调用工具，但 rate_limit_key 为 `host_only` 暗示它们不应作为 MCP 工具暴露。工具名和 host function 名的双重入口会降低直观性。
- 修复建议: 若它们是 MCP 工具，应给出 MCP rate limit；若只是 host function 映射，应从 MCP tool active count 中移除，改到 Host Functions 文档。也可命名为 `swarm_get_terrain`（MCP）与 `host_get_terrain`（WASM）并明确二者 rate limit 与调用面都存在。

### M3. Rhai ABI 缺少类型定义的机器可读 schema
- Severity: Medium
- 文件引用:
  - /data/swarm/docs/specs/reference/rhai-mod-abi.md:46
  - /data/swarm/docs/specs/reference/rhai-mod-abi.md:92
  - /data/swarm/docs/specs/reference/rhai-mod-abi.md:111
  - /data/swarm/docs/specs/reference/rhai-mod-abi.md:250
- 问题描述: Rhai ABI 覆盖了 hooks、query helper、actions API 和实现清单，但 `WorldConfig`、`RoomState`、`Command`、`ActionResult`、`WorldConfig` 等类型仅以名称出现，没有字段级 schema 或示例对象。
- 影响分析: Mod 开发者无法获得 IDE 类型提示，也无法为 Rhai helper 写静态校验或文档生成。Rhai API 的可用性仍偏 prose，未达到 SDK 级合同。
- 修复建议: 增加 `rhai-mod-abi.idl.yaml` 或在本文档增加机器可读 appendix，列出每个 hook/helper 参数和返回对象字段、可选性、单位、错误返回。至少为 9 个 hooks、8 个 query helpers、5 个 actions API 提供完整示例。

### M4. Codegen 文档中使用 `hermes codegen` 命令名可能与项目命名混淆
- Severity: Medium
- 文件引用:
  - /data/swarm/docs/specs/reference/codegen.md:36
  - /data/swarm/docs/specs/reference/codegen.md:40
  - /data/swarm/docs/specs/reference/codegen.md:48
  - /data/swarm/docs/specs/reference/api-registry.md:950
- 问题描述: codegen.md 使用 `hermes codegen generate`，api-registry.md 附录使用 `python3 scripts/generate_api_registry.py`。项目名是 Swarm，而 `hermes` 也是外部 agent 工具名，容易让开发者误解依赖哪个 CLI。
- 影响分析: 新贡献者在本仓库内无法判断应运行 Swarm 自带脚本还是 Hermes Agent CLI。CI 命令不可复现会削弱单事实源可信度。
- 修复建议: 统一命令名。若实际脚本是 `scripts/generate_api_registry.py`，codegen.md 应使用该命令；若目标是 Swarm CLI，命名应为 `swarm codegen generate` 而非 `hermes`。

### M5. “当前设计”文档仍保留 MVP/Future 叙述，容易影响 API 目标状态理解
- Severity: Medium
- 文件引用:
  - /data/swarm/docs/specs/core/09-snapshot-contract.md:1
  - /data/swarm/docs/specs/core/09-snapshot-contract.md:5
  - /data/swarm/docs/specs/core/09-snapshot-contract.md:181
  - /data/swarm/docs/specs/core/09-snapshot-contract.md:254
  - /data/swarm/docs/specs/core/09-snapshot-contract.md:417
- 问题描述: 任务原则要求设计即目标状态、不区分 Phase/MVP/迭代，但 snapshot contract 标题和正文大量使用 MVP/Future。虽然这是跨方向文字风格问题，但对 API/DX 来说会影响生成器是否应包含某些 economy 操作。
- 影响分析: 开发者可能把 AlliedTransfer 或 economy boundaries 理解为阶段性占位，而非当前目标合同。
- 修复建议: 用 “Core Economy Boundary / Out-of-Scope RFC” 替换 MVP/Future 术语；对确实不在当前 API 的功能使用 RFC 状态字段，而不是阶段语言。

## Low / Nits (可选改进) (L1..Ln)

### L1. 文档链接相对路径在 design/interface.md 中可能错误
- Severity: Low
- 文件引用:
  - /data/swarm/docs/design/interface.md:9
  - /data/swarm/docs/design/interface.md:19
  - /data/swarm/docs/design/interface.md:29
- 问题描述: design/interface.md 位于 docs/design，但链接写 `specs/reference/api-registry.md`，从该目录相对解析应为 `../specs/reference/api-registry.md`。
- 影响分析: Markdown 点击体验受损，尤其影响新开发者从设计文档跳到 API 参考。
- 修复建议: 修正相对链接，或统一使用 docs-root 相对路径约定并在 README 说明。

### L2. Codegen 文档说 Registry §6-9 由 auth_api 生成，但当前 Registry §6 是 TickTrace Envelope
- Severity: Low
- 文件引用:
  - /data/swarm/docs/specs/reference/codegen.md:16
  - /data/swarm/docs/specs/reference/api-registry.md:643
  - /data/swarm/docs/specs/reference/api-registry.md:765
- 问题描述: codegen.md 输入输出映射写 `auth_api.idl.yaml → api-registry.md §6-9`，但 Registry §6 为 TickTrace Envelope，§9 才是 Auth Token Envelope，Auth tools 在 §3.3。
- 影响分析: 生成器维护者会误判模板 section mapping。
- 修复建议: 更新 codegen.md 的 section mapping，例如 auth_api 生成 §2.5、§3.3、§6.2、§9、§13。

### L3. `api_version` 与 changelog 版本不一致
- Severity: Low
- 文件引用:
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:8
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:1893
  - /data/swarm/docs/specs/reference/game_api.idl.yaml:1894
  - /data/swarm/docs/specs/reference/api-registry.md:7
  - /data/swarm/docs/specs/reference/api-registry.md:936
- 问题描述: game_api.idl.yaml 顶部 api_version 为 0.4.0，但 changelog 有 0.4.1；api-registry.md 头部也仍显示 0.4.0，而 changelog 说 0.4.0 的 MCP tools 总数为 56 active，与正文 57 冲突。
- 影响分析: SDK 版本 pinning 与 `abi_version` 判断会不可靠。
- 修复建议: 每次 IDL changelog 新版本必须同步 bump `api_version`，并让 Registry 头部由该字段生成。

## Strengths (设计亮点)

- 单事实源意识明确：api-registry.md、codegen.md、commands.md、host-functions.md 都反复声明 IDL → Registry → SDK 的生成链，这是正确方向，适合保障 SDK 类型安全。
- `CommandIntent → RawCommand → ValidatedCommand` 分层清晰，服务端注入 player_id/source/tick 的设计对 API 安全和开发者心智都友好。
- RejectionReason 将 canonical wire enum 与 `debug_detail` 分离，配合 detail_level 能兼顾竞技信息隐藏与训练模式可调试性。
- MCP 明确不做游戏动作，AI agent 与人类玩家都必须走 WASM 部署路径；这一点降低了 API surface 的长期复杂度。
- Capability Profiles（onboarding/play/deploy/debug/admin/arena）非常适合 MCP 客户端做能力发现、最小权限和 IDE/agent 工具分组。
- Rhai RuleMod ABI 的事务性 buffer、default-deny capability 和固定 hook 调度顺序是良好的 mod 开发合同基础。
- Fixed-point type registry 方向正确，避免 f64 进入 replay-critical API，是确定性 SDK 的必要基础。

## CrossCheck — 需要跨方向检查

- CX1: Host Function `host_get_random` 是否应进入生产 ABI 牵涉 RNG 域分离、replay seed 与玩家可见随机流 → 建议 Determinism/Security 检查 replay envelope 是否记录足够 seed material、是否允许 WASM 直接请求随机字节。
- CX2: `swarm_get_terrain` / `swarm_get_path` 同时表现为 MCP tool 与 host function，可能影响能力隔离与限流 → 建议 Security/MCP 检查这些 host_only 工具是否应对外暴露给 MCP 客户端。
- CX3: 02-command-validation.md 中可见性优先要求与部分逐指令表先查 ObjectNotFound/NotOwner 的顺序可能冲突 → 建议 Security 检查 oracle inference 防护是否在所有 target_id 路径成立。
- CX4: Snapshot Contract 中 `swarm_simulate` 可传入/覆盖 hint_level，且“仅限训练模式提升，不允许降级”的措辞可能反向泄露更多信息 → 建议 Security/Gameplay 检查 simulate/dry_run 在竞技模式下的信息暴露边界。
- CX5: Rhai RuleMod 可通过 `actions.set_world_param` 与 `actions.set_entity_flag` 修改全局参数/实体 flag，虽然有 capability gate，但可能影响 replay 与权限审计 → 建议 Architecture/Determinism 检查 RhaiActionBuffer apply 顺序、审计字段和 TickTrace 是否完整。
- CX6: Allied Transfer 在 snapshot contract 中仍使用 MVP/Future 表述，并涉及拦截 RNG 与经济结算 → 建议 Gameplay/Economy 检查其 API schema 是否已覆盖 transfer_id、intercept event、audit record 与 fee/delay/cooldown。
