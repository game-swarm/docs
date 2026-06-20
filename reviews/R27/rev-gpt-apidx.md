# R27 Phase 1 Clean-Slate Review — API/DX (GPT-5.5)

## Verdict

CONDITIONAL_APPROVE

API/DX 方向已经从“散落在设计文档中的概念 API”明显收敛到 IDL → Registry → SDK/Docs 的单事实源路线，MCP 工具分层、只读 host function、deferred command model、capability profiles 与错误提示阶梯都符合可维护 SDK/AI-agent 接入的方向。

但当前文档仍存在若干会直接伤害 SDK 可生成性、MCP schema 可信度和 5 分钟上手体验的漂移：生成链文档的计数/映射与 Registry 不一致，错误 envelope 同时使用 JSON-RPC numeric code 与 string code 两套语义，host function 返回值语义和错误码映射冲突，派生参考文档仍保留非 canonical rejection codes。建议进入下一阶段前修正这些 API 合同漂移；不需要推翻架构。

## Strengths

- **单事实源方向正确**：`api-registry.md` 明确声明 IDL YAML 是机器可读权威源，Registry、SDK 类型、docs 由 codegen 生成，能从根源降低多语言 SDK 漂移风险。
- **MCP 工具分层直觉清晰**：Onboarding / Play / Deploy / Debug / Admin / Arena / SDK / Resources 分类契合 AI agent 使用路径，`capability profile` 也有利于最小权限暴露。
- **避免 MCP 直接游戏动作是好设计**：明确移除 `swarm_move` / `swarm_attack` / `swarm_build` 等 mutating tools，强制 AI 与人类一样部署 WASM，减少双轨 API 和公平性问题。
- **Host Function 暴露面克制**：只提供 terrain / range query / pathfind / world config / rules 五类只读函数，未把 mutating 内部能力泄露给脚本，符合 Rhai/WASM 分层信任模型。
- **错误提示阶梯有 DX 和安全平衡**：competitive/practice/training 三层 detail_level 能同时支持竞技防探测与新手调试，方向优于单一“安全但难用”的错误模型。
- **SDK 自举入口有雏形**：`swarm_sdk_fetch` 直接返回 SDK code、类型定义、示例、ABI version 和 min engine version，是面向 AI agent 的重要 5 分钟上手入口。

## Concerns

### X1 — High — Codegen/Registry 计数和输入映射漂移会破坏 SDK 信任

`api-registry.md` 当前声明：CommandAction 21 个、RejectionReason 47 canonical codes、MCP Game API 56 active + Auth API 11、Host Functions 5。`codegen.md` 却仍写“CommandAction 数量当前 19”、“RejectionReason 数量当前 79”，并把 `auth_api.idl.yaml` 输出映射到 Registry §6-9，而 Registry §6 是 TickTrace envelope、§7 是 Direction4、§8 是 error envelope、§9 才是 Auth Token；Auth tools 实际在 §3.3，Auth TickTrace 在 §6.2。

这不是普通文档错字：如果开发者或 CI 以 `codegen.md` 为实现依据，会生成错误的 SDK 枚举、错误的 changelog 检查和错误的 doc diff gate。API/DX 层面，任何“自动生成”链条只要权威说明自身漂移，用户就很难信任 SDK 与 Registry 的一致性。

**建议**：把 `codegen.md` 改为完全引用 Registry/API version 的当前事实，或从 IDL 自动生成 `codegen.md` 的计数段；至少修正 CommandAction=21、RejectionReason=47 canonical codes、Auth 输出 section 映射、Game API/Auth API 工具数。

### X2 — High — JSON-RPC error envelope 存在两套互斥编码

`design/interface.md` §5.6 示例使用 JSON-RPC 标准形态：`error.code = -32000`，具体 Swarm 错误放在 `error.data.swarm_error`。`api-registry.md` §8 又定义 `error.code = "RejectionReason (string)"`，并补充 `-32000` 只保留给未分类内部错误，具体错误以 `error.code` 字符串为准。

这会让 MCP 客户端、SDK exception 类型和 JSON-RPC 兼容库无所适从：到底 `code` 是 integer 还是 string？标准 JSON-RPC `error.code` 通常是 number，若改为 string，需要明确说明这是 MCP tool result 的 Swarm envelope 而非标准 JSON-RPC error；若保留 number，则 SDK 应从 `data.swarm_error` 读取 canonical code。

**建议**：选择一种 wire contract 并全局替换。API/DX 推荐保留 JSON-RPC numeric `error.code`，用 `data.swarm_error`/`data.rejection_reason` 承载 canonical enum；如果坚持 string code，则需要明确标注“非标准 JSON-RPC error object”，并提供 TS/Rust SDK 的解析规则。

### X3 — High — Host function 返回值语义不一致，SDK wrapper 难以正确生成

`design/interface.md` 写所有 host function 返回 `i32`，`0 = 成功，负数 = 错误码`。`host-functions.md` 对 `host_get_terrain` 写“返回实际写入字节数（≥0），负数=错误码”，但对 `host_get_objects_in_range` 又写“0=成功，负数=错误码”。`api-registry.md` §4.5 定义了错误优先级和负数错误码，但未明确成功时返回 0 还是 bytes_written。

对 C/Rust/TS SDK 来说，这决定 wrapper 是检查 `ret == 0` 后另取长度，还是 `ret > 0` 表示返回字节数。当前混用会导致语言 SDK 的 buffer 读取、重试和错误处理不一致。

**建议**：统一 ABI 成功语义。API/DX 推荐 `ret >= 0` 表示 bytes_written，`ret < 0` 表示 ABI error code；如果成功固定返回 0，则必须另定义 out_len 写回机制或 length header。同步修正设计文档、Registry 和 host-functions 参考。

### X4 — Medium — 派生参考文档仍泄漏非 canonical rejection codes

Registry 明确把 wire enum 收敛为 47 canonical codes，并要求 `Fatigued`、`NotMovable`、`SourceEmpty` 等进入 `debug_detail`。但 `02-command-validation.md` 的校验矩阵仍出现 `TileBlocked`、`StillSpawning`、`ExceedsRoomCapacity`、`InvalidDamageType`、`AlreadyDebilitated(damage_type)`、`MainActionQuotaExceeded` 等看似 wire-level 的失败码，其中有些未标注 `(debug_detail)`，也不在 Registry canonical list 中。

这会让 SDK 作者误以为这些是稳定枚举，进而在客户端类型、switch/case、文档示例中复制旧码。尤其 API/DX 新用户通常先读 command validation 的逐指令表，而不是先完整理解 Registry 的 canonical/debug_detail 分层。

**建议**：把逐指令表中的非 canonical 项统一标为 `debug_detail` 或映射到 canonical code，并在每个表头加一列 `canonical RejectionReason` / `debug_detail key`，避免“说明性名称”被误读为 wire contract。

### X5 — Medium — 5 分钟上手路径仍不完整

文档有 `swarm_sdk_fetch`，也有 MCP Onboarding 工具（`swarm_get_info`、`swarm_get_docs`、`swarm_get_schema`），但缺少一个端到端 Quickstart：登录/证书、fetch SDK、写最小 tick、validate、deploy、查看 last tick/explain。`design/README.md` 的开发环境搭建只到 `docker-compose up`；`interface.md` 也没有“AI agent 首次接入的最短 happy path”。

对新用户尤其是 AI agent，API 的“可用性”不只取决于 schema 完整，还取决于能否在 5 分钟内从空白到部署一个 noop/harvest bot。当前需要在多个文档之间跳转拼流程，摩擦偏高。

**建议**：补一个 canonical quickstart，最好由 `swarm_get_docs({topic:"quickstart"})` 和仓库文档共享同一内容：1) auth/login 或 cert bootstrap；2) `swarm_sdk_fetch`；3) 最小 `tick(snapshot) -> []`；4) `swarm_validate_module`；5) `swarm_deploy`；6) `swarm_explain_last_tick`。

### X6 — Medium — MCP 工具命名存在 namespace 风格混用

绝大多数 MCP 工具使用 `swarm_*` 前缀，例如 `swarm_get_snapshot`、`swarm_deploy`、`swarm_auth_login`。但 Resources 工具使用 `resources/list`、`resources/read` 的 slash namespace 风格。这种混用本身可以接受，但必须有明确命名规则：什么时候用 `swarm_`，什么时候用 MCP resource-style path？否则 AI agent 工具发现和人类记忆都会受影响。

**建议**：统一成 `swarm_resources_list` / `swarm_resources_read`，或在 Registry §3 加“工具命名规范”说明 slash tools 是 MCP resource primitive 而非普通 tool，并在 capability profile 中单独标注。

### X7 — Low — Auth 工具重复定义容易误导 SDK 表面

Registry 同时列出 Game API Auth 简化工具（2 个）和 Auth API 完整工具（11 个），并说明 `swarm_auth_login` / `swarm_auth_refresh` 在 Auth API 中有更丰富 schema。虽然有 note，但对 SDK 生成器来说，这是同名工具的两个 schema。若没有明确 overlay/alias 规则，可能生成两个冲突函数或生成简化 schema 覆盖完整 schema。

**建议**：明确 `game_api` 中的 Auth 2 工具只是 capability shortcut/compat view，不参与 SDK 独立生成；SDK 以 `auth_api.idl.yaml` 完整 schema 为准。更好是 Registry 中给重复工具加 `alias_of` 或 `schema_source=auth_api` 字段。

### X8 — Low — Rhai API 仅有技术选型，缺少脚本接口边界

`tech-choices.md` 说明选择 Rhai 作为服主信任层，强调确定性和可关闭浮点，但允许的 Rhai API 表面没有在本轮允许文档中出现：例如脚本可注册哪些 hooks、可访问哪些 world_config、能否读取/写入 custom action registry、错误如何返回、是否有 capability sandbox。

从 API/DX 角度，Rhai 暴露面“够用但不过度暴露内部”的判断还缺少合同。当前只能认可技术选型，不能确认脚本 API 设计质量。

**建议**：为 Rhai mod API 增加类似 Host Functions 的最小接口表：hook 名称、输入/输出 schema、可用 helper、禁止访问项、错误/回滚语义、版本兼容策略。

## Missing

- **Canonical Quickstart**：缺少面向 AI agent 和人类 SDK 用户的 5 分钟端到端教程。
- **SDK surface examples**：缺少 TypeScript/Rust SDK 生成后的真实调用形态，例如 `client.deploy(...)`、`sdk.tick(...)`、host function safe wrapper 的签名。
- **Error handling guide**：缺少“SDK 如何把 JSON-RPC/MCP error 转成 typed exception/result”的规则，尤其是 retry_allowed、idempotency_key、detail_level 的组合。
- **IDL schema snippets**：Registry 表格足够全面，但新用户仍需要看到最小 IDL YAML 示例和新增 tool/action 的 cookbook。
- **Rhai mod API contract**：缺少脚本层 hook/host API、权限边界、版本策略与错误传播说明。
- **Tool naming convention**：缺少 MCP tool 命名规范，无法解释 `swarm_*` 与 `resources/list` 的混用。

## API Consistency Issues

- `codegen.md` 的 CommandAction/RejectionReason 计数与 `api-registry.md` 当前权威计数不一致。
- `codegen.md` 的 IDL → Registry section 映射与实际 Registry 结构不一致。
- `design/interface.md` 与 `api-registry.md` 对 JSON-RPC `error.code` 的类型和位置定义冲突。
- `design/interface.md`、`host-functions.md` 与 `api-registry.md` 对 host function 成功返回值的语义不一致。
- `host-functions.md` 超出预算写“返回 -1”，但 Registry §4.5 定义 `-4 ERR_BUDGET_EXHAUSTED`、`-5 ERR_PLAYER_BUDGET`、`-6 ERR_GLOBAL_BUDGET`，错误码不一致。
- `02-command-validation.md` 的多个失败码未出现在 canonical RejectionReason 中，且未统一标注为 `debug_detail`。
- `mcp-tools.md` 工具总览写 Play=16、Arena=4，而 Registry 的分类表标题分别为 Play (15) 但列出 16 行、Arena (5) 但 `mcp-tools.md` 写 4；工具计数存在内部漂移。
- `commands.md` 的示例字段名与 Registry 参数名不完全一致：Registry `Build` 参数为 `structure_type`，示例用 `structure`；Registry `Recycle` 参数为 `target_id`，部分示例用 `spawn_id` 或省略 target。
- `Direction4` Registry 使用 `North/South/East/West`，部分命令示例和设计口径混用 body part `MOVE`/`Move`、direction string 与 enum 值，SDK 需明确大小写规范。
- `swarm_simulate` 在 `interface.md` 描述输入为 snapshot + N tick，而 Registry Debug 表中 schema 是 `{commands, assumptions}`；`09-snapshot-contract.md` 又描述 `swarm_simulate(world_state, drone_id, action)`，三处输入模型不一致。

## CrossCheck — 需要跨方向检查

- CX1: `swarm_simulate` / `swarm_dry_run` 的输入模型在 interface、Registry、snapshot contract 三处不一致，可能不只是 DX 问题，还影响模拟隔离与 replay 语义 → 建议 Architect 检查模拟 API 的权威调用模型、状态 fork 边界和 TickTrace 关系。
- CX2: JSON-RPC `error.code` 若改为 string，可能偏离 MCP/JSON-RPC 客户端库预期；若保留 numeric code，又要保证安全 detail 不泄漏 → 建议 Security 检查错误 envelope 的标准兼容性、信息泄露面和审计字段分层。
- CX3: Host function ABI 成功返回 bytes_written vs 0 的选择会影响 WASM 内存读取和 replay determinism，且错误优先级涉及预算/可见性顺序 → 建议 Determinism 检查 host ABI 返回语义、错误优先级与 replay 可复现性。
- CX4: Rhai API 合同缺失，API/DX 无法判断脚本层是否过度暴露内部能力 → 建议 Architect + Security 检查 Rhai mod API 的 capability sandbox、hook 生命周期和可变状态边界。
- CX5: `02-command-validation.md` 仍保留非 canonical code，可能是旧设计残留，也可能代表 Registry 缺漏 → 建议 Architect 检查 RejectionReason canonical set 是否真正覆盖所有实现需要。
