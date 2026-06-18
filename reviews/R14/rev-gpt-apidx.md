# R14 API/开发者体验评审 (GPT)

## Verdict: REQUEST_MAJOR_CHANGES

从 API/DX 视角，R14 的总体方向是正确的：MCP 明确定位为 AI 的“屏幕和鼠标”，不直接承载游戏动作；WASM 使用 deferred command model；SDK 由 IDL/codegen 驱动；MCP 工具有 capability profile 与 schema 完整性要求。这些都是强设计。

但当前文档还不能批准进入实现。核心问题不是缺少功能，而是“接口契约尚未收敛”：同一批 API 在不同参考文档中出现了不同的名称、参数、限制、错误码和语义。对 SDK 使用者、MCP tool 消费者、Rhai/mod 作者来说，这会造成生成代码、文档、测试、示例和错误处理全部分叉。若现在实现，极易形成多个事实来源，之后 API 兼容成本很高。

## Strengths

1. **MCP 与游戏动作边界清楚**
   - `design/interface.md` 和 `specs/reference/mcp-tools.md` 都明确禁止 `swarm_move` / `swarm_attack` / `swarm_build` / `swarm_spawn` 等直接游戏动作工具。
   - AI agent 必须通过 MCP 查看世界、获取 SDK/文档、部署 WASM；真正游戏行为仍由 WASM `tick()` 输出 CommandIntent 完成。这对公平性和用户心理模型都非常好。

2. **Deferred Command Model 对 SDK 友好**
   - `tick(snapshot) -> CommandIntent[]` 是简单、可解释、可测试的接口形态。
   - 玩家代码只负责声明 intent，服务端注入 `player_id` / `source` / `tick` 并统一校验，降低 SDK 暴露内部状态的风险。

3. **存在面向 5 分钟上手的自举入口**
   - `swarm_sdk_fetch`、`swarm_get_schema`、`swarm_get_docs`、`swarm_get_available_actions` 组合上能支持 AI 或新用户快速获得 SDK、类型定义、示例和当前世界能力。
   - capability profile 中的 `onboarding` / `play` / `deploy` / `debug` 分组方向正确，能减少首次接入工具噪音。

4. **错误模型有统一化意图**
   - `SwarmError / JSON-RPC Error Envelope` 包含 `swarm_error`、`details`、`retry_allowed`、`idempotency_key`，比纯字符串错误更适合 SDK 重试与 IDE 展示。
   - 可见性优先的 `NotVisibleOrNotFound` 也兼顾了安全与调用者体验。

5. **Host Function 暴露面克制**
   - WASM host function 限定为只读查询，并显式禁止 mutating host function。这个边界对脚本能力、确定性和安全性都很重要。

## Concerns

### X1 — Critical — Command API 的事实来源不一致，SDK 无法稳定生成

多个文档都声称 API 由 core IDL / `game_api.idl` / CommandAction enum 冻结或生成，但实际 reference 已经分叉：

- `design/interface.md` 的 Command enum 列表包含 `Move`、`Harvest`、`Build`、`Attack`、`RangedAttack`、`Heal`、`Spawn`、`Recycle`、`Transfer`、`Withdraw`、`ClaimController`、8 个特殊攻击、`SendMessage`。
- `specs/reference/commands.md` 称“15 Core + 1 Custom + 8 Special Attacks”，但实际列出了 `TransferToGlobal`、`TransferFromGlobal`、`CreateMarketOrder`、`BuyMarketOrder`，且没有 `SendMessage`。
- `specs/core/02-command-validation.md` 的逐指令矩阵又覆盖了另一组命令，并在后半部分重复出现“CommandAction 变体”，示例字段形态也和前文不同。

这会直接破坏 SDK codegen、MCP `swarm_get_available_actions`、文档示例、校验测试与玩家代码之间的一致性。新用户看到三个参考页会无法判断哪个才是 canonical。

建议：把 `game_api.idl` 或一个 machine-readable schema 明确指定为唯一事实来源；reference 文档只能由它生成。所有文档中的 Command 列表必须删除手写重复表，改为引用生成表或标注“generated from IDL”。

### X2 — Critical — 同一字段/参数命名存在多套风格，开发者直觉会被打断

同一概念在不同地方出现多种命名：

- `Spawn` 示例有 `body_parts`、`body`，标题又写 `SpawnDrone`。
- `Build` 参数有 `structure_type` 与 `structure` 两种写法。
- `Move` direction 在 `design/interface.md` 写 `N/S/E/W/NE/NW/SE/SW`，在 command validation 中写四方向 `N/S/E/W`，在 examples 中写 `North`。
- `Overload` 的 `target_id` 在一些地方是 player id，在后段示例中又像 entity id：`"target_id": "e5"`。
- 命令 envelope 有时写 `{ "sequence", "action": { "type": ... } }`，后半段又出现 `{ "action": "RangedAttack", ... }`。

这不是小命名问题，而是 SDK ergonomic blocker。一个 AI agent 或人类玩家无法稳定推断“下一条命令该怎么写”。

建议：定义一份 API 命名规范：所有 action payload 必须统一使用 `action.type` discriminator；实体字段统一为 `object_id` / `target_id` 或更语义化的 `drone_id` / `target_id`，不可混用；枚举值统一 PascalCase 或 SCREAMING_SNAKE_CASE；方向枚举必须在全局固定。

### X3 — High — MCP tool schema 完整性被要求，但 reference 没有落到每个 tool 的 input/output/error

`design/interface.md` 明确要求 MCP 工具具备 `inputSchema`、`outputSchema`、`error` schema，并点名关键工具必须提供 request/response/error/rate limit。但 `specs/reference/mcp-tools.md` 目前大多只是工具名称与一句话说明，只有 `swarm_sdk_fetch` 在设计文档中给出了比较完整的 Input/Output/Error/Rate Limit。

这会影响 MCP 可用性：

- AI agent 无法从文档直接构造合法请求。
- SDK 无法生成 typed client。
- 错误处理无法区分可重试、权限失败、视野失败、schema 失败。
- capability profile 的“最小集”无法被严格验证。

建议：每个 tool 至少补齐：purpose、profile、input schema、output schema、error variants、rate limit source、replay_class、auth requirement、idempotency behavior、example request/response。若由 IDL 生成，应展示生成输出而不是手写摘要。

### X4 — High — 错误码命名和分类分裂，SDK 无法做可靠错误分支

错误码在多个文档中存在命名差异：

- `InsufficientResources` 与 `InsufficientResource` 同时出现。
- `TargetNotFound`、`ObjectNotFound`、`NotVisibleOrNotFound` 的使用边界不统一。
- `TimeoutExceeded`、`FuelExhausted`、`SnapshotOverBudget` 出现在设计枚举中，但 command validation 的 player rejection 表没有对应完整映射。
- `OnCooldown`、`TargetOverloadCooldown`、`TargetFortifyCooldown` 在 validation 中出现，但 reference 的 rejection list 不完整。
- 文档声称 `RejectionReason enum 共 45 个变体`，但展示的是部分表格并混入管线级、子系统级、MCP 层错误。

对 DX 来说，错误码是 API 的重要部分。当前状态下 SDK 只能把大量错误降级为 string，无法稳定提供 `if (err.code === ...)`、retry helper、IDE doc hover 或 localized explanation。

建议：拆分并冻结三个错误层级：`TickValidationError`、`CommandRejectionReason`、`McpToolError`。每个层级独立 enum，禁止同名不同义；reference 只展示 canonical enum，并为每个错误标注 user-facing message、admin detail、retryability、visibility redaction rule。

### X5 — High — 资源/预算限制互相矛盾，会导致调试体验不可预测

host/query/command budget 在允许文档中出现多组数字：

- `design/interface.md`：`host_get_objects_in_range` 50/tick，`host_path_find` 10/tick，`host_get_world_rules` 1/tick。
- `specs/reference/host-functions.md`：`host_get_objects_in_range` 每 tick 最多 5 次，host call 总预算 1000/tick。
- `specs/core/02-command-validation.md`：查询 `GetObjectsInRange` 每玩家每 tick 5 次，`PathFind` 10 次。
- Tick 输出大小在 command validation 前面写 256KB，后面批级校验写整批 1MB。
- Command schema JSON 中 `maxItems: 100`，文字又写 `MAX_COMMANDS_PER_PLAYER (500)`。

这会让玩家很难调优：同样的策略在 SDK local validation、MCP dry run、实际 WASM tick 中可能得到不同错误。

建议：建立一张 `Limits` canonical 表，并由 SDK、MCP schema、docs、validator 共用。所有 limits 应包含名称、默认值、是否 world.toml 可配置、适用入口、超限错误码。

### X6 — Medium — `swarm_sdk_fetch` 是好入口，但还不足以保证 5 分钟上手

当前自举接口返回 SDK code、type definitions、examples、ABI version、engine version，这是亮点。但文档没有定义一个完整的最小 happy path：

1. 获取 trust / 注册或登录；
2. fetch SDK；
3. 写最小 `tick(snapshot)`；
4. validate module；
5. deploy；
6. explain last tick / inspect trace。

也缺少“最小 bot”示例的稳定 API 形态，例如 TypeScript 玩家如何构造 `CommandIntent[]`、Rust 玩家如何导出 `tick(ptr, len)` 或使用 SDK wrapper。

建议：为 `onboarding` profile 定义一个严格的 quickstart contract，目标是从零到部署一个只会 move/harvest 的 bot 不超过 5 分钟；所有示例必须通过 schema test。

### X7 — Medium — Rhai/mod API 在允许文档中几乎没有开发者契约

`tech-choices.md` 说明 Rhai 用于服主信任层 mod scripting，但本次可读文档没有定义 Rhai 暴露 API 的名称、能力边界、版本策略或示例。API/DX 角度无法判断：

- mod 作者如何注册 custom action / special effect？
- Rhai 能访问哪些 world config 与 ECS 数据？
- 是否有 capability sandbox？
- 脚本错误如何映射到 server/admin-facing errors？
- Rhai API 与 `world.toml`、CommandAction::Custom、special_effect handler 的关系是什么？

这会让“可配置游戏引擎平台”停留在方向正确但接口不可用的状态。

建议：补一个 Rhai API reference，最少覆盖 `register_action`、`validate(ctx)`、`apply(ctx)`、`effect(ctx)` 的稳定接口、输入输出类型、禁止访问项、错误模型、版本兼容策略。

### X8 — Medium — `replay_class` / idempotency / mutation classification 很有价值，但语义还不完整

MCP 工具表给出了 `read_replay_safe`、`idempotent_mutation`、`non_idempotent_mutation`、`admin_critical` 等分类，`swarm_deploy` 也说明 module_hash/idempotency_key 机制。这对 agent 自动重试很重要。

但 reference 没有系统定义：

- 每个 mutation tool 是否必须支持 client-provided idempotency key？
- `swarm_rollback` 的幂等边界是什么？回滚到 version hash 还是“上一个版本”？
- `swarm_tournament_create` 被标为 read_replay_safe 是否合理？名字上是 create，但分类为 read。
- `swarm_tournament_precommit` 名字像 mutation，却被列为 read_replay_safe。

建议：为每个 tool 增加 `side_effects`、`idempotency_key`、`safe_to_retry`、`replay_recorded` 字段，并审查所有 create/precommit/delete/revoke 类工具的分类。

### X9 — Low — 文档内部格式问题会降低 reference 可读性和可生成性

若未来要从 Markdown 生成 SDK 文档或 schema，当前格式中有若干不稳定点：

- 部分 Markdown 表格行多了前导 `| |`，如 command validation 的字段表和边界表。
- 编号跳跃：`## 8. CommandAction 变体` 下小节从 `### 10.1` 开始。
- `SpawnDrone` 标题与 action `Spawn` 不一致。
- `Recycle` 在前文要求 `spawn_id`，后文示例只给 `object_id`。

建议：reference 文档由 schema 生成，或至少加 markdown/schema lint，避免手写 drift。

## Missing

1. **Canonical API IDL / generated schema artifact**
   - 文档多次引用 `game_api.idl`，但本轮可读文档没有展示它的内容或生成物。API/DX 评审无法确认真正的源头。

2. **Typed SDK surface examples**
   - 需要 TypeScript 和 Rust 的最小用户代码示例，而不仅是 JSON command 示例。
   - 需要展示推荐写法，例如 `commands.move(drone.id, Direction.North)` 是否存在，还是用户直接拼 JSON。

3. **MCP per-tool request/response/error reference**
   - 当前 MCP reference 只够做目录，不够做实现或 agent tool-use。

4. **版本与兼容策略**
   - `abi_version`、`min_engine_version` 出现了，但缺少 schema evolution 规则：新增 action、废弃字段、world-specific custom action 如何协商。

5. **Rhai API reference**
   - 当前只说明选择 Rhai，没有说明服主实际能调用什么、不能调用什么。

6. **Local validation / dry-run developer workflow**
   - 有 `swarm_dry_run_commands` 与 `swarm_validate_module`，但缺少 CLI/SDK 层如何在部署前本地检查 schema、limits、错误码的工作流。

7. **Error message style guide**
   - 需要规定 user-facing message、machine code、admin detail、redaction policy、retry hint 的格式，否则错误会逐模块漂移。

## API Consistency Issues

1. **Command 数量与列表不一致**
   - `design/interface.md` 的 Command enum 与 `specs/reference/commands.md` 的“15 Core + 1 Custom + 8 Special Attacks”不匹配。
   - `SendMessage` 只在 design/interface 出现；global storage 与 market commands 只在 command reference 出现。

2. **Action payload 形态不一致**
   - 推荐应统一为 `{ "sequence": n, "action": { "type": "Move", ... } }`。
   - `specs/core/02-command-validation.md` 后段出现 `{ "action": "RangedAttack", ... }`，会误导 SDK 使用者。

3. **Direction 枚举不一致**
   - 八方向 `N/S/E/W/NE/NW/SE/SW`、四方向 `N/S/E/W`、字符串 `North` 同时出现。

4. **错误码单复数不一致**
   - `InsufficientResource` vs `InsufficientResources`。

5. **对象/目标字段语义不一致**
   - `target_id` 有时是 entity id，有时是 player id。建议 Overload 使用 `target_player_id`，避免和实体目标混淆。

6. **Spawn 参数不一致**
   - `body_parts`、`body`、`SpawnDrone`/`Spawn` 命名混用。

7. **Build 参数不一致**
   - `structure_type` 与 `structure` 混用。

8. **Host function budget 不一致**
   - `host_get_objects_in_range` 在不同文档中为 50/tick 或 5/tick。

9. **Tick output limits 不一致**
   - `maxItems: 100` 与 `MAX_COMMANDS_PER_PLAYER (500)` 不一致；256KB 与 1MB 不一致。

10. **Recycle API 不一致**
    - 一处需要 `spawn_id` 并退到 spawn；另一处只传 `object_id`，走 death path。

11. **Tournament tool classification 可疑**
    - `swarm_tournament_create` 和 `swarm_tournament_precommit` 名称是 mutation，但在 capability/tool table 中分类为 read_replay_safe，需要重新定义。

12. **MCP tool set 与 Schema 完整性要求不对齐**
    - 设计要求关键 tool 有完整 schema/rate limit，但 reference 只提供目录级描述。

## CrossCheck — 需要跨方向检查

- CX1: MCP mutation classification 中 `swarm_tournament_create` / `swarm_tournament_precommit` 被标为 read_replay_safe，可能影响重放、审计和安全边界 → 建议 Architect 检查 replay model 与 mutation taxonomy 是否正确。

- CX2: `NotVisibleOrNotFound`、admin trace、player trace 的错误脱敏策略会影响信息泄露风险 → 建议 Security 检查错误码、MCP tool errors、TickTrace 是否存在可枚举实体或玩家的侧信道。

- CX3: Rhai 作为服主信任层但 API 契约缺失，可能导致 mod 能力过大或与 ECS/Command pipeline 耦合过深 → 建议 Architect 与 Security 联合检查 Rhai capability boundary、determinism 与 sandbox policy。

- CX4: host function 和 MCP 查询都暴露 terrain/object/range/path 语义，但预算和可见性规则不一致 → 建议 Architect 检查是否应统一为同一个 Query API abstraction，以免 WASM、MCP、SDK 三套查询语义漂移。

- CX5: `game_api.idl -> codegen -> SDK` 被作为一致性保证，但本轮文档没有展示 IDL 本体或生成物 → 建议 Speaker/Architect 确认 Phase 2 前是否必须把 IDL 作为 design artifact 纳入评审。

## Recommended Gate Before Approval

在进入实现前，建议至少完成以下 gate：

1. 建立 canonical `game_api.idl` / JSON Schema / OpenAPI-like MCP schema 三件套之一，并声明唯一事实来源。
2. 由 canonical schema 重新生成 `commands.md`、`host-functions.md`、`mcp-tools.md` 中的 API 表格。
3. 修复所有 action、参数、错误码、limits 的跨文档冲突。
4. 为 TypeScript SDK 与 Rust SDK 各补一个最小 bot 示例，并通过 schema validation。
5. 为 MCP onboarding profile 补齐真实 tool schemas 与 happy path。
6. 补 Rhai API 最小契约，明确可调用能力和错误模型。

完成上述后，API/DX 方向可以重新评审，预计可降为 CONDITIONAL_APPROVE 或 APPROVE。
