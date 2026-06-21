# R31 API/DX 独立评审 — GPT-5.5

## 1. Verdict

REQUEST_MAJOR_CHANGES

R31 的 API Registry / IDL 单事实源方向是正确的，但当前面向开发者的派生文档仍有多处数量、字段名、错误码、ABI 表面和示例漂移。对 API/DX 来说，这些不是纯文案问题：它们会直接影响 TypeScript SDK 类型生成、MCP 工具发现、IDE 自动补全、错误处理分支和玩家示例代码的可复制性。必须先闭合权威 Registry 与所有 reference/core 派生文档之间的合同一致性，再进入通过。

## 2. 发现的问题

### R31-API-H1 — MCP 工具数量与分组在权威文档和派生文档中互相冲突

Severity: High

文件引用：
- `/tmp/swarm-review-R31/design/interface.md:19`
- `/tmp/swarm-review-R31/specs/reference/api-registry.md:252`
- `/tmp/swarm-review-R31/specs/reference/api-registry.md:254`
- `/tmp/swarm-review-R31/specs/reference/api-registry.md:269`
- `/tmp/swarm-review-R31/specs/reference/api-registry.md:271`
- `/tmp/swarm-review-R31/specs/reference/api-registry.md:287`
- `/tmp/swarm-review-R31/specs/reference/api-registry.md:297`
- `/tmp/swarm-review-R31/specs/reference/api-registry.md:362`
- `/tmp/swarm-review-R31/specs/reference/mcp-tools.md:5`
- `/tmp/swarm-review-R31/specs/reference/mcp-tools.md:13`
- `/tmp/swarm-review-R31/specs/reference/mcp-tools.md:17`
- `/tmp/swarm-review-R31/specs/reference/mcp-tools.md:18`
- `/tmp/swarm-review-R31/specs/reference/mcp-tools.md:19`
- `/tmp/swarm-review-R31/specs/reference/mcp-tools.md:24`
- `/tmp/swarm-review-R31/specs/reference/mcp-tools.md:26`
- `/tmp/swarm-review-R31/specs/reference/api-registry.md:926`

问题描述：
- `design/interface.md` 声称 “56 game tools + 11 auth tools”。
- `api-registry.md` 同时声称 “57 个活跃工具 (game_api) + 11 个 Auth API 工具”，但紧接着又写来源 IDL 是 “57 tools”。
- Registry 实际分组表可见：Onboarding 11、Auth 3、Play 15、Deploy 7、Debug 8、Admin 6、SDK 1、Arena 5、Resources 2，若全算为 58；若跳过 game_api auth shortcuts 则是 55；均不等于 56 或 57。
- `mcp-tools.md` 又声称 56 个 Game API 活跃工具，并列出 Onboarding 10、Auth 2、Play 16、Arena 4，与 Registry 具体分组不一致。
- `api-registry.md` changelog 0.4.0 也写 “MCP tools 总数为 56 active”，与同文档正文冲突。

影响分析：
- MCP 客户端通常依赖工具清单做 tool discovery、capability profile 展示和 IDE/LLM 自动补全。工具数和分组不一致会导致 SDK codegen、文档导航、agent onboarding 和测试 fixture 选择不同工具集合。
- Auth shortcuts 是否算入 Game API active tools 没有机器可读定义，会让 TS SDK 生成重复方法、遗漏方法或生成冲突 overload。
- 开发者无法判断 `swarm_auth_check`、`swarm_get_objectives`、`swarm_get_leaderboard` 等到底属于哪个 profile / 是否 active。

修复建议：
- 在 IDL 中为每个工具增加机器字段：`status: active|alias|deprecated|host_only`、`count_bucket: game_active|auth_canonical|alias_excluded|host_only`、`profiles: [...]`。
- Registry 的总数必须由这些字段生成，并明确两种数字：`Game API callable tools`、`Canonical Auth API tools`、`Aliases excluded from SDK generation`。
- `mcp-tools.md` 不再手写分组计数，改为引用 Registry 生成的 compact summary，或由同一 codegen 模板生成。
- `design/interface.md` 只保留概念说明，不写固定数量；如必须写数量，也必须从生成片段注入。

### R31-API-H2 — CommandAction 示例字段名与 Registry schema 不一致，示例不可直接复制

Severity: High

文件引用：
- `/tmp/swarm-review-R31/specs/reference/api-registry.md:43`
- `/tmp/swarm-review-R31/specs/reference/api-registry.md:58`
- `/tmp/swarm-review-R31/specs/reference/api-registry.md:62`
- `/tmp/swarm-review-R31/specs/reference/commands.md:84`
- `/tmp/swarm-review-R31/specs/reference/commands.md:93`
- `/tmp/swarm-review-R31/specs/reference/commands.md:101`
- `/tmp/swarm-review-R31/specs/reference/commands.md:109`
- `/tmp/swarm-review-R31/specs/core/02-command-validation.md:209`
- `/tmp/swarm-review-R31/specs/core/02-command-validation.md:260`
- `/tmp/swarm-review-R31/specs/core/02-command-validation.md:279`
- `/tmp/swarm-review-R31/specs/core/02-command-validation.md:316`
- `/tmp/swarm-review-R31/specs/core/02-command-validation.md:704`
- `/tmp/swarm-review-R31/specs/core/02-command-validation.md:818`

问题描述：
- Registry 明确所有 21 个 `CommandAction` 变体均包含公共 `object_id`，并说明 Spawn 的 `object_id/actor_id` 是发起 Spawn 的 drone，`spawn_id` 是目标 Spawn 结构。
- `commands.md` 的 Spawn 示例缺少 `object_id`；Build 示例使用 `structure`，但 Registry 参数是 `structure_type`；TransferToGlobal / TransferFromGlobal 示例缺少公共 `object_id`。
- `02-command-validation.md` 中 Spawn 使用 `body` 而不是 Registry 的 `body_parts`；Recycle 在不同位置分别用 `spawn_id`、`target_id` 或完全缺少目标字段；Drain 示例新增 `resource` 字段，但 Registry 的 Drain 参数只有 `target_id`；Fabricate 示例新增 `structure_type` 字段，但 Registry 的 Fabricate 参数只有 `target_id`。

影响分析：
- 这是 API/DX 阻塞问题：玩家和 AI agent 会直接复制这些 JSON 示例，结果被 schema 拒绝。
- TS SDK 若从 Registry 生成 `CommandAction` discriminated union，而文档示例使用不同字段名，会破坏 IDE 自动补全和 LLM 示例学习，导致大量 “文档里能写、SDK 里不能写” 的体验断裂。
- `object_id` 公共字段遗漏尤其严重，因为会影响所有 actor-based helper 的参数顺序设计，例如 `spawn(actor, spawn, bodyParts)` vs `spawn(spawn, bodyParts)`。

修复建议：
- 所有示例必须从 IDL/Registry 生成，或至少由 CI 执行 “示例 JSON validates against generated schema”。
- 为 TypeScript SDK 明确生成目标形态：`type CommandAction = { type: 'Move'; object_id: EntityId; direction: Direction4 } | ...`，并确保所有 reference 示例与该 union 完全一致。
- 对 Spawn / Recycle / Global Transfer / Drain / Fabricate 做一次 schema 裁决：若确实需要额外字段，先改 IDL；若不需要，删除派生文档示例中的额外字段。

### R31-API-H3 — RejectionReason 文档继续引用未注册错误码，破坏 typed exception 合同

Severity: High

文件引用：
- `/tmp/swarm-review-R31/specs/reference/api-registry.md:94`
- `/tmp/swarm-review-R31/specs/reference/api-registry.md:129`
- `/tmp/swarm-review-R31/specs/reference/api-registry.md:215`
- `/tmp/swarm-review-R31/specs/reference/api-registry.md:751`
- `/tmp/swarm-review-R31/specs/core/02-command-validation.md:154`
- `/tmp/swarm-review-R31/specs/core/02-command-validation.md:169`
- `/tmp/swarm-review-R31/specs/core/02-command-validation.md:171`
- `/tmp/swarm-review-R31/specs/core/02-command-validation.md:269`
- `/tmp/swarm-review-R31/specs/core/02-command-validation.md:374`
- `/tmp/swarm-review-R31/specs/core/02-command-validation.md:375`
- `/tmp/swarm-review-R31/specs/core/02-command-validation.md:448`
- `/tmp/swarm-review-R31/specs/core/02-command-validation.md:548`
- `/tmp/swarm-review-R31/specs/core/09-snapshot-contract.md:306`
- `/tmp/swarm-review-R31/specs/core/09-snapshot-contract.md:310`
- `/tmp/swarm-review-R31/specs/core/09-snapshot-contract.md:311`
- `/tmp/swarm-review-R31/specs/core/09-snapshot-contract.md:456`

问题描述：
- Registry 规定 `RejectionReason` 是 SDK typed exception 的 canonical wire enum，且所有上下文应放入 `debug_detail`。
- `02-command-validation.md` 仍然在失败码表中使用未注册/已移除错误码：`TileBlocked`、`StillSpawning`、`ExceedsRoomCapacity`、`InvalidDamageType`、`AlreadyDebilitated(damage_type)`、`MainActionQuotaExceeded`、`ERR_CPU_SATURATED` 等。
- `09-snapshot-contract.md` 的 Safe Hint Ladder 使用 `PermissionDenied`、`InvalidTarget`，但 Registry 中没有这两个 canonical code。

影响分析：
- TS SDK 的 typed exception 只能覆盖 Registry 中的 47 个 canonical code。派生文档继续出现未注册错误码，会迫使实现者要么扩展 enum、破坏 wire 稳定性，要么返回文档未说明的替代码。
- 开发者无法为错误处理写穷举 switch；IDE 会提示不存在的异常名或遗漏真实异常。
- 错误消息不可操作性增加：同一个条件到底是 `PositionOccupied`、`InvalidCommand`、`SchemaViolation` 还是 debug_detail，文档没有闭合映射。

修复建议：
- 在 `02-command-validation.md` 中把所有未注册失败码替换为 `canonical RejectionReason + debug_detail template`，并保证每个表格项都是 Registry §2 的 enum 或明确标注 `debug_detail only`。
- 在 Registry §2.6 中补齐缺失条件映射，例如 tile blocked、still spawning、room capacity exceeded、invalid damage type、main action quota exceeded、CPU saturated。
- CI 添加文档 lint：扫描反引号包裹的错误码 token，若不属于 Registry enum 且未标注 `(debug_detail)`，则失败。

### R31-API-H4 — Host Function ABI 表面不一致，`host_get_random` 在不同文档中消失

Severity: High

文件引用：
- `/tmp/swarm-review-R31/design/interface.md:72`
- `/tmp/swarm-review-R31/design/interface.md:85`
- `/tmp/swarm-review-R31/design/interface.md:120`
- `/tmp/swarm-review-R31/specs/reference/api-registry.md:441`
- `/tmp/swarm-review-R31/specs/reference/api-registry.md:445`
- `/tmp/swarm-review-R31/specs/reference/api-registry.md:454`
- `/tmp/swarm-review-R31/specs/reference/api-registry.md:467`
- `/tmp/swarm-review-R31/specs/reference/api-registry.md:479`
- `/tmp/swarm-review-R31/specs/reference/host-functions.md:9`
- `/tmp/swarm-review-R31/specs/reference/host-functions.md:75`
- `/tmp/swarm-review-R31/specs/reference/host-functions.md:83`
- `/tmp/swarm-review-R31/specs/reference/codegen.md:29`

问题描述：
- Registry §4 声称 Host Functions 共 6 个，并包含 `host_get_random(sequence, out_ptr, out_len)`。
- `design/interface.md` 概念签名只列 5 个；`host-functions.md` 的允许 import、详细签名、输出上限、安全约束也只列 5 个，没有 `host_get_random`。
- `codegen.md` 的 “Host function 数量 (当前 5)” 与 Registry 的 6 冲突。
- `design/interface.md` 同一节还同时写 “ret >= 0 = bytes_written” 与 “所有 host function 返回 i32（0=成功，负数=错误码）”，对 ABI 返回语义造成歧义。

影响分析：
- WASM SDK import binding 会漏生成 `host_get_random`，导致开发者无法通过 SDK 使用确定性随机数，或者手写 import 后被安全文档误认为非法。
- ABI 返回语义不一致会导致 SDK wrapper 错误处理错误：如果把正数 bytes_written 当成非零失败/成功码，就会截断输出或吞掉错误。
- Host function 是 WASM/Rust/TS SDK 的底层边界，任何漂移都会扩大到所有语言绑定。

修复建议：
- 以 Registry §4 为准，将 `host-functions.md` 的允许 import、详细签名、输出上限、安全约束补齐 `host_get_random`。
- `design/interface.md` 只写 “概念示例，完整列表见 Registry”，并删除固定列表或同步 `host_get_random`。
- 统一 ABI 返回合同为：`ret >= 0` 表示 `bytes_written`，`ret < 0` 表示 `HostAbiError`；SDK wrapper 应生成 `Result<Uint8Array, HostAbiError>` / Rust `Result<&[u8], HostAbiError>`。

### R31-API-M1 — Codegen 文档自身承认手工维护关键计数，削弱单事实源承诺

Severity: Medium

文件引用：
- `/tmp/swarm-review-R31/specs/reference/codegen.md:7`
- `/tmp/swarm-review-R31/specs/reference/codegen.md:20`
- `/tmp/swarm-review-R31/specs/reference/codegen.md:24`
- `/tmp/swarm-review-R31/specs/reference/codegen.md:26`
- `/tmp/swarm-review-R31/specs/reference/codegen.md:27`
- `/tmp/swarm-review-R31/specs/reference/codegen.md:29`
- `/tmp/swarm-review-R31/specs/reference/api-registry.md:437`

问题描述：
- `codegen.md` 一方面规定 IDL 是唯一机器源、Registry 全量生成；另一方面在 “禁止手写的数值” 下写本文档自身为手工维护，且 CommandAction / MCP tool / RejectionReason / Host function 数量需手动更新。
- 当前文档已经表现出这种风险：MCP tool 数量和 Host function 数量均漂移。
- Registry §3.2 还保留 “IDL 字段注解当前仅部分字段有标注——需补齐全部工具” 的未闭合要求，但设计评审原则下文档应呈现目标状态，而非路线图。

影响分析：
- “禁止手写但本文档手写” 会让实现者不清楚 CI 的真正保护边界。
- SDK 生成依赖 required/optional/default/errors 注解；如果 Registry 仍说 “仅部分字段有标注”，TypeScript SDK 无法保证严格类型、默认值和 typed errors。

修复建议：
- `codegen.md` 的计数也应从 generated snippet 注入，或删除具体数值，仅声明从 IDL 派生。
- 把 `required/optional/default/errors` 从 “需补齐” 改为目标状态合同：所有工具、字段、返回值和错误列表必须完整标注；未标注 IDL 不合法。
- 增加 CI gate：`api-registry --check`、`docs-derived-counts --check`、`examples-schema-validate --check` 三类检查分开失败。

### R31-API-M2 — `swarm_simulate` / `swarm_dry_run` 的输入输出合同在 Registry 与 Snapshot Contract 中不一致

Severity: Medium

文件引用：
- `/tmp/swarm-review-R31/design/interface.md:147`
- `/tmp/swarm-review-R31/specs/reference/api-registry.md:341`
- `/tmp/swarm-review-R31/specs/reference/api-registry.md:342`
- `/tmp/swarm-review-R31/specs/core/09-snapshot-contract.md:138`
- `/tmp/swarm-review-R31/specs/core/09-snapshot-contract.md:156`
- `/tmp/swarm-review-R31/specs/core/09-snapshot-contract.md:412`
- `/tmp/swarm-review-R31/specs/core/09-snapshot-contract.md:413`

问题描述：
- `design/interface.md` 描述 `swarm_simulate` 输入为给定 snapshot 离线模拟 N tick，最大 100 tick、max_entities=1000、输出 deterministic replay。
- Registry 中 `swarm_simulate` schema 是 `{commands, assumptions}` → `{trace, authoritative: false, assumptions, confidence}`；`swarm_dry_run` 是 `{wasm_bytes, tick_count}` → `{trace, fuel_used, errors}`。
- Snapshot Contract 给 `swarm_simulate` 输出增加 `not_predictive`、`rng_ordinals_consumed`、`fuel_consumed`、`tick_trace_written`，给 `swarm_dry_run` 增加 `deterministic` 标记，并允许 `hint_level` 覆盖；这些字段未在 Registry schema 中出现。

影响分析：
- MCP 工具 schema 与说明文档不一致时，AI agent 会调用不存在的参数或期望不存在的字段。
- TypeScript SDK 无法给 `simulate` / `dryRun` 生成准确返回类型，尤其是 `authoritative=false`、`not_predictive=true`、`deterministic=true` 这些非常适合做 literal type narrowing 的字段。

修复建议：
- 把 Snapshot Contract 的输出字段纳入 IDL schema，尤其是 literal boolean 字段：`authoritative: false`、`not_predictive: true`、`deterministic?: true`。
- 明确 `swarm_simulate` 的输入到底是 `snapshot + tick_count`、`commands + assumptions`，还是两者之一，并在 Registry 中生成完整 schema。
- 对 `hint_level` override 加入 input schema，注明权限/模式限制和错误码。

### R31-API-M3 — TypeScript SDK 的开发者体验目标仍停留在原则层，缺少可验证生成合同

Severity: Medium

文件引用：
- `/tmp/swarm-review-R31/design/tech-choices.md:183`
- `/tmp/swarm-review-R31/design/tech-choices.md:197`
- `/tmp/swarm-review-R31/design/tech-choices.md:224`
- `/tmp/swarm-review-R31/specs/reference/codegen.md:18`
- `/tmp/swarm-review-R31/specs/reference/api-registry.md:744`
- `/tmp/swarm-review-R31/specs/reference/api-registry.md:751`
- `/tmp/swarm-review-R31/design/interface.md:100`

问题描述：
- 文档说明 TypeScript 是 AI 玩家第一语言，Monaco 智能提示直接对接 SDK 类型，`swarm_sdk_fetch` 返回 SDK 代码和类型定义。
- 但 reference 文档没有明确 TypeScript SDK 的生成形态：包名、入口模块、泛型 ID 类型、CommandAction discriminated union、错误类层级、MCP tool client 类型、版本兼容检查、literal enum 生成方式、deprecated/alias 处理方式。
- `SwarmError` 写 SDK 从 `rejection_reason` 生成 typed exception，但没有定义异常类/联合类型的名字和 exhaustiveness 机制。

影响分析：
- 对 API/DX 来说，光有 IDL 不足以保证 IDE 自动补全体验。若 SDK 生成策略不固定，不同实现者可能生成不兼容的客户端 API，AI agent 示例也无法稳定学习。
- `swarm_sdk_fetch` 作为自举入口，如果返回的 SDK 结构未定义，MCP onboarding 会变成“拿到一段字符串但不知道怎么 import/use”。

修复建议：
- 在 `codegen.md` 或新增 `typescript-sdk-contract.md` 中定义生成目标：
  - `@swarm/sdk` 包入口和浏览器/wasm target。
  - `CommandAction` discriminated union、`CommandIntent`、`WorldSnapshot`、`SwarmErrorData`、`RejectionReason` literal union。
  - MCP client 方法签名，例如 `client.getSnapshot(input): Promise<GetSnapshotOutput>`，并从 `required/optional/default/errors` 生成 overload / defaults。
  - `assertNever` / exhaustive switch pattern 示例。
  - `swarm_sdk_fetch` 返回的 `type_definitions` 与 npm/deno/jsr 包版本的对应关系。

### R31-API-M4 — Rhai API 的事务语义和错误语义存在局部冲突，mod 作者难以判断 action 失败是否回滚全局

Severity: Medium

文件引用：
- `/tmp/swarm-review-R31/specs/reference/rhai-mod-abi.md:16`
- `/tmp/swarm-review-R31/specs/reference/rhai-mod-abi.md:22`
- `/tmp/swarm-review-R31/specs/reference/rhai-mod-abi.md:23`
- `/tmp/swarm-review-R31/specs/reference/rhai-mod-abi.md:109`
- `/tmp/swarm-review-R31/specs/reference/rhai-mod-abi.md:152`
- `/tmp/swarm-review-R31/specs/reference/rhai-mod-abi.md:158`

问题描述：
- Rhai ABI §1.1 规定所有 hooks 执行完毕后 “全部成功 → Buffer apply；任一失败 → Buffer 丢弃”。
- §5.1 又规定单个 `actions.*` 失败时 “跳过该 action，buffer 保留其余”。
- Actions API 表没有给出函数返回类型，例如 `Result<(), ModError>`、`bool`、异常 panic 或 error code。

影响分析：
- mod 作者无法判断 `actions.award()` 失败后是否需要手动补偿，也不知道 action 失败是否会导致整个 tick 的模组输出回滚。
- “任一失败全丢弃” 与 “单 action 失败保留其余” 是不同事务模型，会影响经济类 RuleMod 的可预测性和审计。

修复建议：
- 明确两层失败语义：建议将 `actions.*` 参数校验失败作为 recoverable error 返回给脚本，不写入 buffer；脚本 panic/timeout/security violation 才丢弃该脚本全部 buffer。
- 为每个 `actions.*` 定义 Rhai 签名和返回类型，例如 `actions.award(resource: string, amount: u64, reason: string) -> Result<()>` 或固定 error object。
- 增加一个示例：多个 action 中一个失败时最终 buffer 如何 apply。

### R31-API-L1 — 文档继续使用 “MVP/Future/Phase/Rxx 修复” 叙事，不符合目标状态文档原则

Severity: Low

文件引用：
- `/tmp/swarm-review-R31/specs/core/09-snapshot-contract.md:1`
- `/tmp/swarm-review-R31/specs/core/09-snapshot-contract.md:5`
- `/tmp/swarm-review-R31/specs/core/09-snapshot-contract.md:14`
- `/tmp/swarm-review-R31/specs/core/09-snapshot-contract.md:181`
- `/tmp/swarm-review-R31/specs/core/09-snapshot-contract.md:185`
- `/tmp/swarm-review-R31/specs/core/09-snapshot-contract.md:212`
- `/tmp/swarm-review-R31/specs/core/09-snapshot-contract.md:254`
- `/tmp/swarm-review-R31/specs/core/09-snapshot-contract.md:417`
- `/tmp/swarm-review-R31/specs/reference/api-registry.md:437`

问题描述：
- 多处标题和正文仍写 “MVP 经济边界”、“R15/R22 修复”、“Future RFC”、“当前 YAML 中仅部分字段有标注——需补齐全部工具”。
- 用户明确要求设计文档呈现最终目标状态，不做 Phase/MVP/迭代路线图。

影响分析：
- 对开发者体验来说，历史叙事会让读者误解哪些 API 是稳定目标、哪些是临时过渡。
- “MVP 不实现” 与 “设计即目标状态” 冲突，会干扰 SDK 是否生成某些枚举变体、feature gate 和文档导航。

修复建议：
- 将历史修复标签移入 changelog 或移除正文。
- 将 “MVP 经济边界” 改为 “Core Economy Boundary” 或 “Canonical Economy Scope”。
- “Future RFC” 若确实不是当前目标状态，应从当前 API reference 中移除或明确为非生成 RFC 附录，不进入 SDK active surface。

## 3. 亮点

- IDL → Registry → SDK/Docs 的单事实源方向正确，且 `api-registry.md` 明确手写修改会被覆盖，这是长期维护 API/DX 的正确基础。
- `CommandIntent` / `RawCommand` / `ValidatedCommand` 的分层清晰，能帮助 SDK 区分玩家可构造字段和服务端注入字段，避免把 `player_id/source/tick` 暴露为可写参数。
- `SwarmError` JSON-RPC envelope 的 `rejection_reason`、`debug_detail`、`retry_allowed`、`idempotency_key`、`retry_after_tick` 设计对自动化 agent 非常友好，具备机器可恢复能力。
- MCP 不直接暴露 `move/attack/build/spawn` 的边界清楚，能防止 AI agent 走不同于人类玩家的作弊路径；“AI 必须写 WASM” 的产品语义一致。
- Host function 预算、输出上限和错误优先级有明确表格，适合生成 WASM SDK wrapper 和 deterministic test vectors。
- Fixed-point registry 把 `f64` 全部替换为整数量纲，对跨语言 SDK 和 replay determinism 都是正向设计。
- Capability Profiles 的概念对 MCP onboarding 很有价值，未来可直接驱动 “只暴露 onboarding/play/deploy/debug/admin/arena 子集” 的工具发现 UX。
- Rhai ABI 使用 `query.*` / `actions.*` 双命名空间，方向直观，mod 作者能快速理解只读查询与事务性写入的边界。

## 4. CrossCheck — 需要跨方向检查

- CX-1: `api-registry.md` 中 Auth 层和 Game/MCP 层重复 `InvalidCertificate`、`NotAuthorized`、`RateLimited` 名称，仅靠 numeric namespace 区分；SDK 生成时可能出现同名 enum collision → 建议安全/认证方向检查 wire enum 是否需要 namespaced discriminant 或 SDK alias 策略。
- CX-2: `host_get_random` 以 `(tick_seed, player_id, drone_id, sequence)` 生成随机流，但 `sequence` 由调用方提供；同一 tick 内重复 sequence 是否允许、是否需要 SDK guard 或审计 → 建议确定性/反作弊方向检查 RNG domain separation 与 replay 约束。
- CX-3: Agent WS 描述 “每消息 seq + MAC (ed25519)” 和 “MAC 由 Swarm-Request-Signature 头携带” 术语混用，Ed25519 是签名不是 MAC → 建议安全方向检查协议术语与签名覆盖字段。
- CX-4: `swarm_get_code` 输出 `{code, hash, language, size, last_deployed}`，即使 owner 过滤也可能暴露玩家源码；是否应只返回 own code 或只返回 hash/metadata → 建议安全/隐私方向检查代码访问控制。
- CX-5: Snapshot Contract 中训练模式允许返回 RNG 状态快照，但确定性与反作弊设计通常避免暴露 seed material → 建议安全/确定性方向检查 `FullDebug` 是否可在任何多人环境启用。
- CX-6: Rhai mod 签名模型中 `author_pubkey` 由 mod 作者自行声明，签名只证明“来自声明作者”，不证明作者身份；供应链信任可能不足 → 建议安全/运维方向检查 mod trust root、pinning 和更新策略。
