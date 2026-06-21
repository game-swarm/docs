# R32 API/开发者体验独立评审 — rev-gpt-apidx

## 1. Verdict

REQUEST_MAJOR_CHANGES

当前设计的方向正确：IDL/Registry/codegen 作为单一事实源、MCP 不直接执行游戏动作、WASM deferred command model、Rhai RuleMod ABI 都是可行且面向开发者友好的方向。但本轮 API/DX 视角存在多处必须修复的派生文档漂移：MCP 工具数量、Host Function 数量、CommandAction 示例字段、RejectionReason wire enum 与错误提示模型在不同文档中互相冲突。它们会直接破坏 TypeScript SDK 类型生成、IDE 自动补全、MCP client tool discovery、WASM import ABI 与错误处理的稳定性，因此需要 major changes 后再通过。

## 2. 发现的问题

### R32-API-H1 — MCP 工具计数与 capability profile 文档严重漂移

- Severity: High
- 文件引用：
  - `/tmp/swarm-review-R32/design/interface.md:19`
  - `/tmp/swarm-review-R32/specs/reference/api-registry.md:254`
  - `/tmp/swarm-review-R32/specs/reference/api-registry.md:258`
  - `/tmp/swarm-review-R32/specs/reference/api-registry.md:273`
  - `/tmp/swarm-review-R32/specs/reference/mcp-tools.md:5`
  - `/tmp/swarm-review-R32/specs/reference/mcp-tools.md:13`
  - `/tmp/swarm-review-R32/specs/reference/mcp-tools.md:17`
  - `/tmp/swarm-review-R32/specs/reference/mcp-tools.md:18`
  - `/tmp/swarm-review-R32/specs/reference/mcp-tools.md:19`
  - `/tmp/swarm-review-R32/specs/reference/mcp-tools.md:24`
  - `/tmp/swarm-review-R32/specs/reference/mcp-tools.md:26`
  - `/tmp/swarm-review-R32/specs/reference/codegen.md:27`
- 问题描述：`api-registry.md` 声明 `57` 个 Game API active tools + `11` 个 Auth API tools，并在 §3.2 展开了 57 个工具；但 `design/interface.md`、`mcp-tools.md`、`codegen.md` 多处仍写 `56`。更严重的是 `mcp-tools.md` 的分组计数也与 Registry 不一致：Onboarding 写 10 但 Registry 为 11；Auth 写 2 但 Registry game_api Auth shortcut 为 3；Play 写 16 但 Registry 为 15；Arena 写 4 但 Registry 为 5。
- 影响分析：MCP client 的 tool discovery、capability profile UI、权限矩阵、SDK 生成测试都会依据这些计数与分组生成校验。如果文档同时声明 56 和 57，开发者无法判断 `swarm_get_objectives`、`swarm_auth_check`、`swarm_get_leaderboard` 或 tournament tools 应归属哪个 profile；AI agent 也会拿到互相矛盾的 onboarding/play/admin 能力面。
- 修复建议：以 `/tmp/swarm-review-R32/specs/reference/api-registry.md` §3 为唯一权威，统一派生文档：`design/interface.md` 改为 `57 game tools + 11 auth tools`；`mcp-tools.md` 总览表改为 Onboarding 11、Auth 3、Play 15、Arena 5、Game API 小计 57；`codegen.md` 当前 MCP tool 数改为 57，并补一条 CI rule：派生文档中的 count literals 必须由 registry check 验证或禁止手写。

### R32-API-H2 — Host Function ABI 数量与 `host_get_random` 暴露状态冲突

- Severity: High
- 文件引用：
  - `/tmp/swarm-review-R32/specs/reference/api-registry.md:445`
  - `/tmp/swarm-review-R32/specs/reference/api-registry.md:460`
  - `/tmp/swarm-review-R32/specs/reference/api-registry.md:462`
  - `/tmp/swarm-review-R32/specs/reference/api-registry.md:473`
  - `/tmp/swarm-review-R32/specs/reference/api-registry.md:485`
  - `/tmp/swarm-review-R32/specs/reference/api-registry.md:496`
  - `/tmp/swarm-review-R32/specs/reference/host-functions.md:13`
  - `/tmp/swarm-review-R32/specs/reference/host-functions.md:18`
  - `/tmp/swarm-review-R32/specs/reference/host-functions.md:75`
  - `/tmp/swarm-review-R32/specs/reference/host-functions.md:82`
  - `/tmp/swarm-review-R32/specs/reference/codegen.md:29`
  - `/tmp/swarm-review-R32/design/interface.md:72`
  - `/tmp/swarm-review-R32/design/interface.md:81`
- 问题描述：Registry §4 明确 Host Functions 共 6 个，并包含 `host_get_random(sequence: u64, out_ptr: i32, out_len: i32) -> i32`、调用上限、输出上限和 fuel 成本；但 `host-functions.md` 的 allowed imports、详细签名、输出上限完全缺失该函数，`codegen.md` 仍写当前 Host function 数量为 5，`design/interface.md` 的概念签名也只列 5 个。
- 影响分析：这会让 WASM SDK、Rust/TS binding、lint/preflight 和 sandbox import allowlist 产生不一致。最坏情况下，SDK 暴露 `random()` 但 sandbox 拒绝 import；或 sandbox 支持 `host_get_random` 但 SDK/文档不提供类型，玩家只能手写 ABI。对确定性随机 API 来说，这属于严重 DX 断裂。
- 修复建议：统一所有派生文档为 6 个 host functions。`host-functions.md` 必须新增 `host_get_random` 的 import、C 签名、domain separation 说明、10/tick 上限、256 bytes 输出上限、fuel 成本；`codegen.md` 当前数量改为 6；`design/interface.md` 概念签名补 `host_get_random` 或明确“不完整示意，以 Registry 为准且包含 deterministic random”。

### R32-API-C1 — CommandAction 示例字段与 Registry schema 不一致，破坏 SDK 类型安全

- Severity: Critical
- 文件引用：
  - `/tmp/swarm-review-R32/specs/reference/api-registry.md:43`
  - `/tmp/swarm-review-R32/specs/reference/api-registry.md:58`
  - `/tmp/swarm-review-R32/specs/reference/api-registry.md:62`
  - `/tmp/swarm-review-R32/specs/reference/api-registry.md:72`
  - `/tmp/swarm-review-R32/specs/reference/api-registry.md:73`
  - `/tmp/swarm-review-R32/specs/reference/commands.md:83`
  - `/tmp/swarm-review-R32/specs/reference/commands.md:93`
  - `/tmp/swarm-review-R32/specs/reference/commands.md:101`
  - `/tmp/swarm-review-R32/specs/reference/commands.md:109`
  - `/tmp/swarm-review-R32/specs/reference/commands.md:117`
  - `/tmp/swarm-review-R32/specs/core/02-command-validation.md:259`
  - `/tmp/swarm-review-R32/specs/core/02-command-validation.md:278`
- 问题描述：Registry 明确所有 21 个 CommandAction 变体均包含公共 `object_id`，Spawn 参数为 `body_parts` + `spawn_id`，Build 参数为 `structure_type`，TransferToGlobal/TransferFromGlobal 仍是 CommandAction 变体并继承 `object_id`。但 `commands.md` 示例中 Spawn 缺 `object_id`，Build 使用 `structure` 而不是 `structure_type`，TransferToGlobal/TransferFromGlobal 缺 `object_id`，Recycle 使用 `target_id`；`02-command-validation.md` 又在 Spawn 示例中使用 `body`，Recycle 示例中使用 `spawn_id`。同一动作在三份文档中出现三个不同 shape。
- 影响分析：这是 API/DX 阻塞问题。TypeScript SDK 的 discriminated union、IDE autocomplete、JSON schema validation、玩家示例复制粘贴都会失败。AI agent 生成策略代码时极大概率复制 `commands.md` 示例，随后被 Registry schema 拒绝；开发者也无法判断 `Recycle` 到底需要 `target_id`、`spawn_id` 还是二者之一。
- 修复建议：从 IDL/Registry 自动生成 `commands.md` 的示例 schema，禁止手写字段名。立即统一：所有示例使用 `action: { type, object_id, ... }`；Spawn 示例使用 `object_id` + `spawn_id` + `body_parts`；Build 使用 `structure_type`；Global transfer 示例补 `object_id`；Recycle 在 Registry、commands、validation 中确定唯一字段形态。若 Recycle 语义确实需要 Spawn 作为回收站，应先在 IDL 将 Registry 从 `target_id` 改为 `spawn_id` 或 `recycle_at_spawn_id`，不要在派生文档中分叉。

### R32-API-C2 — RejectionReason wire enum 与校验文档仍混用未注册错误码

- Severity: Critical
- 文件引用：
  - `/tmp/swarm-review-R32/specs/reference/api-registry.md:96`
  - `/tmp/swarm-review-R32/specs/reference/api-registry.md:100`
  - `/tmp/swarm-review-R32/specs/reference/api-registry.md:215`
  - `/tmp/swarm-review-R32/specs/reference/api-registry.md:248`
  - `/tmp/swarm-review-R32/specs/core/02-command-validation.md:154`
  - `/tmp/swarm-review-R32/specs/core/02-command-validation.md:169`
  - `/tmp/swarm-review-R32/specs/core/02-command-validation.md:171`
  - `/tmp/swarm-review-R32/specs/core/02-command-validation.md:269`
  - `/tmp/swarm-review-R32/specs/core/02-command-validation.md:374`
  - `/tmp/swarm-review-R32/specs/core/02-command-validation.md:375`
  - `/tmp/swarm-review-R32/specs/core/02-command-validation.md:548`
  - `/tmp/swarm-review-R32/specs/core/09-snapshot-contract.md:456`
- 问题描述：Registry 宣称 RejectionReason 是 47 个 canonical wire code，细节进入 `debug_detail`；`02-command-validation.md` 也在开头承认旧码应降级为 debug_detail。但后文表格仍直接使用未注册码或未映射码：`TileBlocked`、`StillSpawning`、`ExceedsRoomCapacity`、`InvalidDamageType`、`AlreadyDebilitated(damage_type)`、`MainActionQuotaExceeded`、`ERR_CPU_SATURATED` 等。`Snapshot Contract` admission 又返回 `ERR_CPU_SATURATED`，不在 Registry §4.5 host ABI error，也不在 RejectionReason §2。
- 影响分析：SDK 无法生成稳定 typed exception；MCP JSON-RPC error.data.rejection_reason 可能收到 Registry 中不存在的字符串；玩家代码中的 exhaustive switch 会在运行时漏分支。错误消息可操作性也下降，因为开发者不知道这些码是 wire enum、debug_detail 还是内部分类。
- 修复建议：为 `02-command-validation.md` 增加一张“legacy/internal condition → canonical RejectionReason → debug_detail template”完整映射，并替换逐指令表中的未注册码。若确实需要新增 wire code，例如 `MainActionQuotaExceeded` 或 CPU admission failure，则必须先进入 IDL/Registry 的 canonical list，再由 codegen 派生所有文档。`ERR_*` ABI 错误仅限 host function ABI；不要混入 command/MCP RejectionReason。

### R32-API-H3 — `SwarmError` / `detail_level` 与 Safe Hint Ladder 双轨错误模型未统一

- Severity: High
- 文件引用：
  - `/tmp/swarm-review-R32/specs/reference/api-registry.md:110`
  - `/tmp/swarm-review-R32/specs/reference/api-registry.md:114`
  - `/tmp/swarm-review-R32/specs/reference/api-registry.md:721`
  - `/tmp/swarm-review-R32/specs/reference/api-registry.md:757`
  - `/tmp/swarm-review-R32/design/interface.md:128`
  - `/tmp/swarm-review-R32/design/interface.md:140`
  - `/tmp/swarm-review-R32/specs/core/09-snapshot-contract.md:284`
  - `/tmp/swarm-review-R32/specs/core/09-snapshot-contract.md:370`
  - `/tmp/swarm-review-R32/specs/core/09-snapshot-contract.md:387`
  - `/tmp/swarm-review-R32/specs/core/09-snapshot-contract.md:413`
- 问题描述：Registry/Interface 定义统一 `SwarmError JSON-RPC Envelope`，核心字段是 `rejection_reason`、`debug_detail`、`retry_allowed`、`idempotency_key`、`retry_after_tick`，并通过 `detail_level=competitive/practice/training` 控制 debug_detail 详细程度；但 Snapshot Contract 又定义另一套 `CommandError { safe_message, fix_hint, debug_detail }` 和 `world.hint_level`，并允许 `swarm_dry_run` 传入 `hint_level` 覆盖。两套模型没有说明字段如何映射：`fix_hint` 是否进入 `error.message`、`debug_detail`、还是 `error.data.fix_hint`？`detail_level` 与 `hint_level` 是同一配置还是两套配置？
- 影响分析：SDK 错误类型会分叉：一种按 Registry 生成 `SwarmError`, 另一种按 Snapshot Contract 生成 `CommandError`。IDE 自动补全无法告诉用户 practice 模式下是否存在 `fix_hint`；MCP client 也无法稳定解析训练模式调试信息。错误消息“可操作性”目标因此无法落地。
- 修复建议：把 Safe Hint Ladder 明确收敛到 `SwarmError.data` schema：例如 `safe_message` 固定映射到 JSON-RPC `error.message`，`fix_hint?: string` 和 `debug_detail?: string | DebugPayload` 作为 `error.data` 的可选字段，并把 `detail_level` 与 `world.hint_level` 合并为同一枚举或给出一对一映射。`swarm_dry_run` 的覆盖参数也应进入 Registry tool schema，而不是只在 Snapshot Contract 出现。

### R32-API-M1 — TypeScript SDK/API 生成链仍缺少足够的类型层细节

- Severity: Medium
- 文件引用：
  - `/tmp/swarm-review-R32/specs/reference/codegen.md:11`
  - `/tmp/swarm-review-R32/specs/reference/codegen.md:18`
  - `/tmp/swarm-review-R32/specs/reference/api-registry.md:441`
  - `/tmp/swarm-review-R32/design/tech-choices.md:183`
  - `/tmp/swarm-review-R32/design/tech-choices.md:197`
  - `/tmp/swarm-review-R32/design/tech-choices.md:224`
- 问题描述：文档多次强调 TypeScript SDK、Monaco 智能提示和 IDL → SDK 自动化，但 codegen 规范只写“SDK 类型定义 (`sdk-templates/`)”，没有规定 TS 输出形态：是否生成 discriminated union、branded IDs、literal enum、Result/exception 策略、optional/default 的展开规则、deprecated 标注、JSDoc 来源、MCP tool client 的 overload 形态。Registry 甚至注明当前 YAML 仅部分字段有 `required/optional/default/errors` 注解，需补齐全部工具。
- 影响分析：对 API/DX 来说，这会导致“有 IDL 但没有 IDE 体验合同”。不同实现者可能生成互不兼容的 SDK：`EntityId` 可能是裸 string、number 或 branded type；`RejectionReason` 可能是 string union 或 enum；optional/default 字段可能在 input 与 output 上表现不同。AI agent 和人类玩家获得的自动补全质量不可预测。
- 修复建议：在 `codegen.md` 增加 TypeScript SDK 生成合同：CommandAction 必须生成 discriminated union；`EntityId`/`PlayerId`/`SpawnId` 使用 branded primitive；RejectionReason 生成 exhaustive string literal union；每个 MCP tool 生成 `client.toolName(input): Promise<Output>`；IDL 的 required/optional/default/errors 必须完整，否则 CI fail；JSDoc 从 Registry 描述生成，deprecated/error/retry metadata 进入类型。

### R32-API-M2 — Rhai RuleMod ABI 对开发者友好，但 `capabilities` 默认授权语义危险且不直觉

- Severity: Medium
- 文件引用：
  - `/tmp/swarm-review-R32/specs/reference/rhai-mod-abi.md:121`
  - `/tmp/swarm-review-R32/specs/reference/rhai-mod-abi.md:127`
  - `/tmp/swarm-review-R32/specs/reference/rhai-mod-abi.md:136`
  - `/tmp/swarm-review-R32/specs/reference/rhai-mod-abi.md:140`
  - `/tmp/swarm-review-R32/specs/reference/rhai-mod-abi.md:150`
- 问题描述：Rhai ABI 的 capability 表区分默认授权 ✅/❌，但 §4.2 写“不写 `capabilities` = 全部已声明 capability 均授权”。这对服主来说不直觉：他们可能以为省略 capabilities 表示使用安全默认值，实际却授权模组声明的全部 capability，包括高风险能力如果模组在 `required_capabilities` 中声明了它们。
- 影响分析：从 DX/安全交互角度，这是典型 footgun。服主配置一个模组时，最短配置反而可能是最大授权；IDE/TOML autocomplete 也很难提示“省略字段不是默认安全”。虽然这是信任模型/安全方向也应复核的问题，但 API 设计上应避免默认行为违反最小惊讶原则。
- 修复建议：改为“不写 `capabilities` = 仅授权 `default=true` 且模组声明的 capabilities”；若要全部授权，要求显式 `capabilities = "all_declared"` 或 `capabilities = [ ... ]`。同时在 `mod.toml` 与 `world.toml` 示例中展示 least-privilege 配置。

### R32-API-L1 — 派生文档保留 MVP/Future/Phase 语义，违背“设计即目标状态”的评审原则

- Severity: Low
- 文件引用：
  - `/tmp/swarm-review-R32/specs/core/09-snapshot-contract.md:1`
  - `/tmp/swarm-review-R32/specs/core/09-snapshot-contract.md:5`
  - `/tmp/swarm-review-R32/specs/core/09-snapshot-contract.md:14`
  - `/tmp/swarm-review-R32/specs/core/09-snapshot-contract.md:181`
  - `/tmp/swarm-review-R32/specs/core/09-snapshot-contract.md:254`
  - `/tmp/swarm-review-R32/specs/core/09-snapshot-contract.md:417`
- 问题描述：Snapshot Contract 仍大量使用 “MVP”、“Future”、“Future RFC” 等阶段性措辞。任务要求明确“设计即目标状态”，不区分 Phase/MVP/迭代。虽然这不一定改变 API wire contract，但会让开发者误解哪些 API 是最终合同、哪些只是临时边界。
- 影响分析：SDK/文档使用者会犹豫是否依赖 Allied Transfer、economy operations、simulate/dry-run 等 API；设计评审也难以判断字段是否应进入当前 Registry。
- 修复建议：把 “MVP” 改写为 “Core Contract” 或 “Current Core Scope”；把 “Future RFC” 改为 “Out-of-Scope RFC”；兼容性表不要写 MVP/Future 阶段，而写 “Current Contract” 与 “Out-of-Scope Extensions”。

## 3. 亮点

- `api-registry.md` 把 CommandAction、RejectionReason、MCP Tools、Host Functions、limits、TickTrace、SwarmError 放在同一个权威 Registry 中，并明确由 IDL 自动生成，这是维护 SDK 一致性的正确方向。
- MCP 明确不暴露 `swarm_move` / `swarm_attack` / `swarm_build` / `swarm_spawn`，要求 AI agent 与人类一样通过 WASM 部署策略，避免 MCP 变成作弊级动作接口。
- `SwarmError` 使用 canonical `rejection_reason` + 非 canonical `debug_detail`，并包含 `retry_allowed`、`idempotency_key`、`retry_after_tick`，对 AI agent 自动修复与幂等重试非常友好。
- Host Function ABI 明确 `out_ptr/out_len`、负数错误码、预算、输出上限和错误优先级，适合生成低层 WASM binding，也便于玩家理解 buffer-too-small / budget-exhausted 的处理路径。
- Rhai RuleMod ABI 的 hook 表、query/actions 命名空间、事务性 `RhaiActionBuffer`、AST 节点预算和 Semver 兼容策略都很清晰，模组作者能据此直接实现和测试。
- Snapshot truncation contract 对 `truncated`、`omitted_categories`、关键实体不可截断、确定性排序的定义细致，能显著改善玩家与 AI agent 在超大快照下的调试体验。

## 4. CrossCheck — 需要跨方向检查

- CX-1: `host_get_random` 的 seed material 与 replay envelope 是否足够覆盖 `(tick_seed, player_id, drone_id, sequence)`，并与快照/keyframe 中的 seed 归档策略一致 → 建议 Determinism/Replay 方向检查 RNG domain separation 与 replay reproducibility。
- CX-2: Rhai `capabilities` 省略即授权全部 declared capabilities 的语义可能扩大服主误配置风险 → 建议 Security/Auth 方向检查 capability default-deny 与 mod trust model。
- CX-3: MCP/Auth tool 中 `Subject Source = player_id` 的工具仍在 input schema 接收 `player_id`，需要确认是否会产生代操作/越权歧义 → 建议 Security/Auth 方向检查 subject derivation 与 request principal 绑定。
- CX-4: `swarm_simulate` / `swarm_dry_run` 的 `hint_level` 覆盖规则“仅限训练模式提升，不允许降级”措辞可疑，可能与竞技信息隐藏目标冲突 → 建议 Gameplay/Security 方向检查模式提升权限与 hidden-state leakage。
- CX-5: `api-registry.md` 中 async object store 描述同时写 immediate return、失败后 deploy rejected、blob 缺失不影响 replay 但 `terminal_state = audit_gap`，语义可能跨持久化/回放冲突 → 建议 Persistence/Replay 方向检查 deploy_mutation 状态机。
- CX-6: `02-command-validation.md` 的特殊攻击优先级引用未读的 Phase 2b manifest，本评审无法验证 S14/S22 与当前 API shape 一致 → 建议 Engine/Gameplay 方向检查 special attack reducer 与 CommandAction Custom routing。
