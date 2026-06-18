# R18 API/DX Review — DeepSeek V4 Pro

> **Reviewer**: rev-dsv4-apidx (API/DX 评审员)
> **Date**: 2026-06-18
> **Review Scope**: 10 documents from /tmp/swarm-review-R18/
> **Mandate**: 验证生成式单源闭合 — YAML IDL ↔ api-registry.md 无漂移；设计文档与 IDL 一致性

---

## 1. Verdict: REQUEST_MAJOR_CHANGES

YAML IDL 到 api-registry.md 的生成管道本身是闭合的——这两份文档内部一致，版本对齐，schema 匹配。但 **存在两类致命问题**：

1. **设计文档层未同步**：interface.md、commands.md、mcp-tools.md、host-functions.md、02-command-validation.md 这 5 份文档包含与 YAML IDL 严重冲突的 API 定义——不是小幅漂移，而是完全不同的 RejectionReason 体系、不同的 MCP 工具集合、不同的 host function 签名、不同的指令枚举模型。
2. **YAML IDL 类型系统不完整**：EntityId、ResourceType、StructureType、DamageType 等基础类型在 IDL 中被引用但未定义；所有 46 个 MCP 工具缺少 error schema；SDK codegen 缺少类型闭包。

如果 SDK 从 YAML IDL 生成代码，但开发者阅读 commands.md 理解 API——两套完全矛盾的体系将导致实现错误。

---

## 2. Critical Issues (5)

### C1 — commands.md RejectionReason 列表与 YAML 完全背离 [severity: CRITICAL]

**文件**: `specs/reference/commands.md` §RejectionReason (lines 224–260)

commands.md 列出 35 个拒绝原因，但 **约 28 个不在 YAML IDL 的 35 个 canonical code 中**：

| commands.md 中的码 | YAML 中存在? | YAML 中的定位 |
|---|---|---|
| `NotMovable` | ❌ | D2/B 明确声明为 debug_detail 内容，非 enum 变体 |
| `Fatigued` | ❌ | 同上 |
| `MissingBodyPart` | ❌ | 同上 |
| `TileBlocked` | ❌ | 同上 |
| `StillSpawning` | ❌ | 同上 |
| `CarryFull` | ❌ | 同上 |
| `NotSource` | ❌ | 同上 |
| `SourceEmpty` | ❌ | 同上 |
| `TargetFull` | ❌ | 同上 |
| `TargetEmpty` | ❌ | 同上 |
| `NotYourRoom` | ❌ | 同上 |
| `TileOccupied` | ❌ | YAML 有 `PositionOccupied`（同名不同码） |
| `InvalidTerrain` | ❌ | 同上 |
| `TooManyConstructionSites` | ❌ | YAML 有 `ConstructionLimitReached` |
| `AlreadyFullHealth` | ❌ | debug_detail |
| `FriendlyTarget` | ❌ | debug_detail |
| `NotYourSpawn` | ❌ | debug_detail |
| `BodyTooLarge` | ❌ | YAML 有 `NotEnoughBodyParts` |
| `ExceedsRoomCapacity` | ❌ | YAML 有 `RoomDroneCapReached` |
| `NotFriendly` | ❌ | debug_detail |
| `AlreadyHacked` | ❌ | debug_detail |
| `InvalidDamageType` | ❌ | debug_detail |
| `AlreadyDebilitated` | ❌ | debug_detail |
| `OutOfRoom` | ❌ | 不存在 |
| `NoPath` | ❌ | 不存在 |
| `PathTooLong` | ❌ | 不存在 |
| `InsufficientMoveParts` | ❌ | debug_detail |

**同时**，YAML 的 35 个 canonical code 中有很多 **不在** commands.md 中：
`SchemaViolation`, `NotStructure`, `NotController`, `TargetNotVisible`, `AuthContextInvalid`, `SafeModeActive`, `TargetOverloadCooldown`, `TargetFortifyCooldown`, `InvalidBodyPart`, `InvalidStructureType`, `InvalidResourceType`, `SourceNotAllowed`, `UnknownAction`, `GlobalStorageDisabled`, `TransferInProgress`, `RateLimited`, `InvalidCertificate`, `NotAuthorized`, `FuelExhausted`, `TimeoutExceeded`, `SnapshotOverBudget`, `CommandBufferFull`, `ServerOverloaded`, `InternalError`

**影响**: SDK codegen 从 YAML 生成 `enum RejectionReason { ... }` 有 35 个变体。开发者参考 commands.md 写错误处理时，会尝试匹配 28 个不存在的变体，同时漏掉 20+ 个真实存在的变体。CI 的「未注册即拒绝」门禁将直接阻断所有读取 commands.md 的实现。

### C2 — 02-command-validation.md 全篇使用 deprecated RejectionReason 码 [severity: CRITICAL]

**文件**: `specs/core/02-command-validation.md` §3 (lines 152–628)

这是核心校验规范。所有 19 个指令的校验矩阵都引用非 canonical 的旧码：

- §3.1 Move: `NotMovable`, `Fatigued`, `MissingBodyPart(Move)`, `TileBlocked`, `StillSpawning`
- §3.2 Harvest: `MissingBodyPart(Work)`, `MissingBodyPart(Carry)`, `CarryFull`, `NotSource`, `SourceEmpty`
- §3.3 Transfer/Withdraw: `MissingBodyPart(Carry)`, `TargetFull`, `TargetEmpty`
- §3.5 Attack: `MissingBodyPart(Attack)`, `FriendlyTarget`
- §3.7 Heal: `AlreadyFullHealth`, `NotFriendly`
- §3.8 Spawn: `NotYourSpawn`, `BodyTooLarge`, `ExceedsRoomCapacity`
- §3.10 Hack: `MissingBodyPart(Claim)`, `AlreadyHacked`
- §3.11 Drain: `TargetEmpty`, `CarryFull`, `NotStructure`
- §3.12 Overload: `FriendlyTarget` (used where canonical code should be `NotVisibleOrNotFound`)
- §3.13 Debilitate: `InvalidDamageType`, `AlreadyDebilitated(damage_type)`, `MissingBodyPart(Work)`
- §3.14 Disrupt: `MissingBodyPart(Attack)`
- §3.15 Fortify: `NotFriendly`, `MissingBodyPart(Tough)`

这些码在 D2/B 规范中明确属于 `debug_detail` 字段而非 `RejectionReason` enum 变体。如果引擎按此 spec 实现校验，返回的 wire enum 值将与 IDL 生成的 SDK 类型完全不匹配。

### C3 — Host Function 签名三文档不一致 [severity: CRITICAL]

| 函数 | YAML IDL / api-registry.md | host-functions.md | interface.md |
|---|---|---|---|
| `host_get_terrain` | `(room_id: u32, out_ptr: i32, out_len: i32) -> i32` | `(x: i32, y: i32) -> i32` ❌ | `(x: i32, y: i32) -> i32` ❌ |
| `host_path_find` | `(from_x, from_y, to_x, to_y, opts_ptr, opts_len, out_ptr, out_len)` | 缺 `opts_ptr`/`opts_len` ❌ | 缺 `opts_ptr`/`opts_len` ❌ |
| `host_get_world_rules` | `(rule_id_ptr, rule_id_len, out_ptr, out_len)` | `(out_ptr, out_len)` ❌ | `(out_ptr, out_len)` ❌ |

`host_get_terrain` 的差异是灾变性的：YAML 版本接收 `room_id` 并通过 output buffer 返回结果；host-functions.md 版本接收 `(x, y)` 坐标并直接返回 i32。这是两个**完全不同的 ABI**。如果 WASM 模块按 host-functions.md 签名编译，调用时将发生栈破坏或参数错位。

### C4 — MCP 工具集合 interface.md/mcp-tools.md 与 YAML IDL 严重分歧 [severity: CRITICAL]

YAML IDL 定义 **46 个 MCP 工具**，但 interface.md §4.1 和 mcp-tools.md 描述的是不同的工具集合：

**在 interface.md/mcp-tools.md 中但不在 YAML 中的工具**（部分列表）：
- `swarm_get_objects_in_range` — interface.md 列出为「世界查看」，YAML 中为 Play 分类的 `swarm_get_room`（语义不同）
- `swarm_rollback` — interface.md 部署类，YAML 中不存在
- `swarm_list_modules` — interface.md 部署类，YAML 中不存在
- `swarm_explain_last_tick` — 调试类，YAML 中为 `swarm_get_tick_trace`
- `swarm_inspect_entity` — 调试类，YAML 中不存在
- `swarm_inspect_room` — 调试类，YAML 中不存在
- `swarm_profile` — 调试类，YAML 中不存在
- `swarm_dry_run_commands` — 调试类，YAML 中为 `swarm_dry_run`
- `swarm_get_docs` — 学习类，YAML 中不存在（合并到 `swarm_sdk_fetch`）
- `swarm_get_schema` — 学习类，YAML 中不存在
- `swarm_get_available_actions` — 学习类，YAML 中不存在
- `swarm_get_player_status` — interface.md 行 9 要求但完全不存在
- 全部认证工具（~20 个：swarm_submit_csr、swarm_renew_certificate、swarm_list_certificates 等）— YAML Auth 分类仅有 2 个工具（swarm_auth_login, swarm_auth_refresh）
- 全部锦标赛工具（swarm_tournament_precommit 等 4 个）— 完全不在 YAML 中

**在 YAML 中但不在 interface.md/mcp-tools.md 中的工具**：
- `swarm_get_info`, `swarm_get_resources`, `swarm_list_rooms`, `swarm_get_room`, `swarm_list_drones`, `swarm_get_drone`, `swarm_get_code` (Onboarding)
- `swarm_auth_login`, `swarm_auth_refresh` (Auth)
- `swarm_get_leaderboard`, `swarm_get_events`, `swarm_get_path`, `swarm_get_visibility`, `swarm_list_controllers`, `swarm_get_controller`, `swarm_list_structures`, `swarm_get_structure`, `swarm_get_messages` (Play)
- `swarm_get_deploy_status`, `swarm_list_deployments` (Deploy)
- `swarm_get_tick_trace`, `swarm_get_engine_stats`, `swarm_get_sandbox_profile`, `swarm_list_errors`, `swarm_get_state_checksum`, `swarm_dry_run` (Debug)
- 全部 6 个 Admin 工具
- `resources/list`, `resources/read` (Resources)

**影响**: 当人类开发者参考 interface.md 写 MCP 客户端、AI agent 通过 swarm_get_schema 获取工具列表时，两边看到的是不同的 API 表面。interface.md 中列出的「world state viewing」工具 `swarm_get_objects_in_range` 在运行时根本不存在——AI agent 会收到 `UnknownTool` 错误。

### C5 — 特殊攻击枚举模型矛盾 [severity: CRITICAL]

- **YAML IDL**: Hack/Drain/Overload/Debilitate/Disrupt/Fortify 是 `command_action` 的第一类变体（indices 14-19），与其他核心指令同级
- **commands.md**: "以下 8 种特殊攻击通过 `CommandAction::Custom(type)` 路由至 `CustomActionRegistry`"（line 134）
- **02-command-validation.md**: 特殊攻击 §3.10-3.15 标题写的是独立类型，但第 427 行注 "特殊攻击的 IDL 定义见 specs/gameplay/08-api-idl"

SDK codegen 从 YAML 生成时，`CommandAction` enum 会有 `Hack(Drain/Overload/...)` 变体。但 commands.md 说它们是 `Custom(type)` 路由——两种模型会生成两种完全不同的 Rust `enum` / TypeScript `discriminated union`。这对 API 消费者是不可调和的矛盾。

---

## 3. High Issues (4)

### H1 — interface.md Schema完备性要求与其自身不一致 [severity: HIGH]

interface.md 行 9 要求以下工具"必须进入工具目录并提供完整的 request/response/error 定义和 rate limit"：
`swarm_sdk_fetch`, `swarm_get_schema`, `swarm_get_docs`, `swarm_get_player_status`, `swarm_deploy`, `swarm_validate_module`, `swarm_get_snapshot`, `swarm_get_available_actions`, `swarm_explain_last_tick`, `swarm_submit_csr`

但其中 **6 个工具不在 YAML IDL 中**：`swarm_get_schema`, `swarm_get_docs`, `swarm_get_player_status`, `swarm_get_available_actions`, `swarm_explain_last_tick`, `swarm_submit_csr`。

剩下的 4 个虽然在 YAML 中，但 **YAML 中没有任何工具的 error schema 定义**——interface.md 要求的 `error` schema 完全缺失。

### H2 — MCP Capability Profiles 三文档不一致 [severity: HIGH]

| Profile | interface.md §4.1a | YAML IDL capability_profiles | 差异 |
|---|---|---|---|
| onboarding | 含 swarm_sdk_fetch, swarm_get_docs | Onboarding, Auth, SDK, Resources | YAML 不含 swarm_sdk_fetch（在 SDK 分类） |
| play | swarm_get_snapshot 等 6 工具 | Play 分类全部 14 工具 | 数量差距大 |
| deploy | swarm_deploy, swarm_validate_module, swarm_rollback, swarm_list_modules | Deploy 分类 6 工具 | 成员不同 |
| debug | 含 swarm_simulate | Debug 分类 7 工具 | 数量差距大 |
| admin | 含资源管理工具 | Admin 分类 6 工具 | 成员不同 |

SDK 的 `swarm_get_schema(profile=...)` 返回的工具列表将因文档参照不同而产生不同结果。

### H3 — Command 文档 Title 命名不一致 [severity: HIGH]

commands.md 行 81: 节标题 `### SpawnDrone`，但 JSON 示例使用 `"type": "Spawn"`。
YAML IDL 中此变体名为 `Spawn`。
02-command-validation.md 行 258: 使用 `"type": "Spawn"`。

文档标题与实际 API 名称不匹配可能导致 SDK 生成或文档引用错误。

### H4 — host-functions.md 预算模型与 YAML 不一致 [severity: HIGH]

host-functions.md 行 59-64:
- "host_get_world_config" 无单独上限（"共享剩余配额"）
- YAML IDL 行 1283: `per_tick_budget: 5` — host_get_world_config 有硬上限 5/tick

host-functions.md 行 64:
- "超出预算 → 返回 -1，tick 继续执行（非致命错误）"
- YAML IDL ABI error priority table: -1 = ERR_MEMORY_BOUNDS，不是预算耗尽

预算耗尽在 YAML 中是 `-4` (ERR_BUDGET_EXHAUSTED)、`-5` (ERR_PLAYER_BUDGET)、`-6` (ERR_GLOBAL_BUDGET)，不是 `-1`。

---

## 4. Type System Gaps

### T1 — 基础类型链未闭合

YAML IDL 引用但未定义的类型：

| 被引用的类型 | 引用位置 | 定义状态 |
|---|---|---|
| `EntityId` | CommandAction 参数、MCP tool schemas | **未定义** |
| `PlayerId` | MCP tool schemas | **未定义** |
| `DroneId` | MCP tool schemas | **未定义** |
| `RoomId` | MCP tool schemas | **未定义** |
| `ControllerId` | MCP tool schemas | **未定义** |
| `StructureId` | MCP tool schemas | **未定义** |
| `SpawnId` | CommandAction 参数 | **未定义** |
| `DeployId` | MCP tool schemas | **未定义** |
| `RollbackId` | MCP tool schemas | **未定义** |
| `ResourceType` | CommandAction 参数（Transfer 等） | **未定义** |
| `StructureType` | CommandAction 参数（Build） | **未定义** |
| `BodyPart` | CommandAction 参数（Spawn） | **未定义** |
| `DamageType` | 02-command-validation.md 中引用 | **未定义** |
| `Direction4` | CommandAction 参数（Move） | ✅ 已定义 (§7) |

**17 个类型中仅有 1 个在 IDL 中定义。** SDK codegen 需要对 `EntityId`、`PlayerId` 等做 `type EntityId = string` 或 `newtype` 包装——IDL 不定义这些类型，codegen 只能硬编码默认映射，失去跨语言一致性。

### T2 — MCP 工具缺少 error schema

YAML 中 46 个工具全部缺少 `error` schema 字段。interface.md 明确要求"所有 MCP 工具必须具备 inputSchema、outputSchema 和 error schema"。缺少 error schema 意味着 MCP 客户端无法静态验证工具调用的错误响应。

### T3 — 复合类型未展开

MCP 工具 output_schema 中使用字符串形式的复合类型（如 `"[{id, room, body, lifespan, status}]"`），这些类型在 YAML 中无结构化定义。SDK codegen 无法为 `DroneSummary`、`StructureSummary` 等生成命名类型——只能生成为 `any` 或匿名 record。

---

## 5. Error Handling Coverage

### E1 — per-tool error coverage: 0/46

46 个 YAML 工具中，**无一具有 error schema 定义**。开发者无法静态得知 `swarm_deploy` 可能返回哪些错误、`swarm_simulate` 的错误码集合、`swarm_sdk_fetch` 的 `SDKNotFound` 对应的 canonical code 是什么。

interface.md 为 `swarm_sdk_fetch` 列出了三个 error: `SDKNotFound`, `UnsupportedLanguage`, `RateLimited`。这些 **不在** 35 个 canonical RejectionReason 中。`SDKNotFound` 和 `UnsupportedLanguage` 是工具特有错误码，需要在 IDL 中注册或映射到 canonical code。

### E2 — debug_detail 与 canonical code 桥接未定义

D2/B 规范将 `NotMovable`, `Fatigued`, `MissingBodyPart` 等归入 debug_detail。但 **没有文档定义 canonical code ↔ debug_detail 的映射关系**。例如：
- 当引擎因 drone 疲劳拒绝 Move 指令时，wire 上返回哪个 canonical code？`CooldownActive`？`InvalidDirection`？还是某个通用码？
- debug_detail 字符串 `"Fatigued: action cooldown 12 ticks remaining"` 与哪个 canonical code 配对？

SDK 生成的错误处理代码将无法可靠 match 这些场景。

### E3 — SwarmError envelope 的 retry_allowed 未被 IDL 建模

interface.md §5.6 定义了 `retry_allowed` 分类（TimeoutExceeded/RateLimited/ConflictRetry → true; InvalidCommand/InsufficientResources/NotAuthorized → false）。YAML IDL 的 `SwarmError` envelope 中引用了 `retry_allowed` 但未在 rejection_reason 变体中标记此属性。SDK 无法为每个错误码生成重试策略。

---

## 6. Cross-Check Matrix

| 交叉验证项 | YAML IDL | api-registry.md | commands.md | interface.md | 02-cmd-val.md |
|---|---|---|---|---|---|
| api_version | 0.3.0 ✅ | 0.3.0 ✅ | 未声明 ⚠️ | 未声明 ⚠️ | 未声明 ⚠️ |
| CommandAction 变体数 | 19 ✅ | 19 ✅ | 19+Custom ❌ | 19 ✅ | 19 ✅ |
| RejectionReason 体系 | 35 canonical ✅ | 35 canonical ✅ | 35 (28 不匹配) ❌ | 35 ✅ | 旧体系 ❌ |
| Host function 签名 | 5 (含 opts) ✅ | 匹配 YAML ✅ | — | 3/5 不匹配 ❌ | — |
| MCP 工具数 | 46 ✅ | 46 ✅ | — | ~42 (成员不同) ❌ | — |
| debug_detail | 512 bytes ✅ | 512 bytes ✅ | 无概念 ❌ | 无概念 ❌ | 无概念 ❌ |
| detail_level | 3级 ✅ | 3级 ✅ | — | — | 3级 (snapshot-contract) ✅ |
| SwarmError envelope | 含 debug_detail ✅ | 匹配 YAML ✅ | — | 旧格式(无 debug_detail) ❌ | — |
| 特殊攻击 enum 模型 | 第一类变体 ✅ | 匹配 YAML ✅ | Custom(type) ❌ | — | 混合 ❌ |
| Deploy 机制 | deploy_mutation ✅ | 匹配 YAML ✅ | — | — | — |

---

## 7. Strengths

1. **YAML→api-registry.md 生成管道闭合**。这两份文档在 CommandAction、RejectionReason 体系、Host Function ABI、MCP 工具安全列、容量限制、TickTrace Envelope、Direction4、SwarmError、Deploy 机制、Persistence 等所有已定义节上完全一致。单源策略的技术基础已经建立。

2. **D2/B debug_detail 设计正确**。35 个 canonical wire enum code + 512 bytes debug_detail 的分离，配合 competitive/practice/training 三级 detail_level，是处理信息泄漏与调试需求之间张力的正确架构。RejectionReason 命名规范（统一单数、废弃旧名）清晰且可执行。

3. **deploy_mutation + fdb_version_counter 确定性合约完整**。Deploy 子系统的幂等性保证、异步 blob 上传解耦、FDB 小事务提交、重放顺序保证——这些在 YAML 和 api-registry 中一致且完整。

4. **09-snapshot-contract.md 的 detail_level 与 YAML 一致**。快照截断合同（H3）、模拟隔离（H4）、MVP 经济边界（DH1）、安全提示阶梯（DH2）与 IDL 定义的 detail_level enum 精确对齐。

5. **MCP 安全列完整**。YAML 中 46 个工具均定义了 `required_scope`、`subject_source`、`replay_class`、`visibility_filter`、`rate_limit_key` 五列安全属性，这在 api-registry.md 中一致呈现。

6. **changelog 清晰可追溯**。YAML 和 api-registry.md 均有结构化 changelog，版本 0.1.0→0.2.0→0.3.0 的变更记录明确。

---

## 8. Action Items (Prioritized)

### Blocker（修复后方可进入 Phase 2）

| # | 操作 | 涉及文档 |
|---|---|---|
| B1 | 将 commands.md RejectionReason 列表替换为 YAML 的 35 canonical codes | commands.md |
| B2 | 将 02-command-validation.md 全部校验矩阵的拒绝码替换为 YAML canonical codes；添加 debug_detail 映射表 | 02-command-validation.md |
| B3 | 统一 host_get_terrain/host_path_find/host_get_world_rules 签名为 YAML 版本 | host-functions.md, interface.md |
| B4 | 将 interface.md/mcp-tools.md 的 MCP 工具清单替换为 YAML 的 46 工具集（含 5 安全列） | interface.md, mcp-tools.md |

### High Priority

| # | 操作 | 涉及文档 |
|---|---|---|
| H1 | 为 46 个 MCP 工具补充 error schema（每个工具的错误码集合 + canonical code 映射） | game_api.idl.yaml |
| H2 | 在 YAML 中定义所有被引用的基础类型（EntityId, PlayerId, ResourceType, StructureType, BodyPart, DamageType 等 16 个） | game_api.idl.yaml |
| H3 | 统一 commands.md/interface.md 的特殊攻击枚举模型为 YAML 的第一类变体模型 | commands.md, interface.md |
| H4 | 定义 canonical code → debug_detail 映射表（每个 canonical code 可携带哪些 debug_detail 字符串） | 02-command-validation.md 或新 spec |
| H5 | 在 YAML RejectionReason 变体中添加 `retry_allowed` 字段 | game_api.idl.yaml |
| H6 | 展开 MCP 工具 output_schema 中的复合类型为命名结构体（DroneSummary, StructureSummary 等） | game_api.idl.yaml |

---

*End of Review*
