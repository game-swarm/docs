# R30 API/Developer Experience 评审报告 — DeepSeek V4 Pro

## 1. Verdict

**REQUEST_MAJOR_CHANGES**

存在 3 项 Critical 级别的跨文档不一致问题 (IDL schema 计数漂移 + 过期枚举定义 + API 版本号冲突)，以及 7 项 High 级别的类型系统缺口和安全性列缺失。修复这些后可达 APPROVE。

---

## 2. 发现的问题

### Critical

**C1 — CommandAction 计数在 IDL YAML 与生成 Registry 间不一致**

- 文件: `specs/reference/game_api.idl.yaml` L72 `total_variants: 19` vs `specs/reference/api-registry.md` L43 `变体总数: 21`
- 问题: YAML IDL 中 `command_action.variants` 列出 19 个变体 (11 core + 2 global + 6 special attack)。Leech 和 Fabricate 被放在 `custom_actions.known` 而非 `variants` 列表中。但 api-registry.md §1.3 将它们列为 #20/#21，并将 `变体总数` 写为 21。
- 影响: 实现者依据不同文档将产生分歧——YAML 读者认为 CommandAction enum 有 19 个变体，Registry 读者认为有 21 个。enum 索引分配 (#20 Leech, #21 Fabricate) 在两种读法下冲突：Registry 认为它们是 CommandAction 的正交成员，YAML 认为它们走 `CommandAction::Custom()` 路由。
- 修复建议: 二选一 (D-item 需用户裁决):
  - 方案 A: 升格 Leech/Fabricate 到 `variants` 列表，将 `total_variants` 更新为 21，更新 YAML 注释描述
  - 方案 B: 保持 YAML 19 变体，api-registry.md §1 改为 "变体总数: 19 (core) + 2 (custom)"，并将 Leech/Fabricate 从 §1 主表移入单独的 custom 子表
  - 推荐方案 A，因为 `commands.md` 和所有文档已按 21 指令工作

**C2 — MCP 工具计数不一致: 57 vs 56**

- 文件: `specs/reference/game_api.idl.yaml` L490 `total_tools: 57` vs `specs/reference/api-registry.md` L211 `56` vs `specs/reference/codegen.md` L28 `56 active`
- 明细: api-registry.md §3 Play 分类头写 `Play (15)` 但表内列出 16 行。其中 `swarm_get_terrain` 和 `swarm_get_path` rate limit 为 `— (host fn only)`，暗示它们不是 MCP 可调用工具，仅为注册用途。若减去这 2 个 host-only 工具 → 14 (非 15)。加上 Onboarding 11 + Auth 3 + Deploy 7 + Debug 8 + Admin 6 + SDK 1 + Arena 5 + Resources 2，总数有多种计算结果:
  - Play=16: 11+3+16+7+8+6+1+5+2 = 59
  - Play=15: 11+3+15+7+8+6+1+5+2 = 58
  - Play=14 (去 host-only): 11+3+14+7+8+6+1+5+2 = 57
  - Play=16 但用旧计数 + 去掉某些: 无法得 56
- 新增工具 `swarm_get_objectives` (Onboarding #11) 在 YAML 中存在但 changelog 未提及，进一步加剧计数分歧。
- 影响: 三个文档分别声明 56/57/58 个工具，SDK codegen 和 CI check 无从判断正确值。
- 修复建议: Play 表头改为 `Play (16)`，明确注释 `swarm_get_terrain` 和 `swarm_get_path` 为 "host-only non-MCP tools registered for trace completeness"，更新 YAML `total_tools`、api-registry 头部、codegen.md 禁止手写计数值为统一数字。同时在 codegen.md 中明确: 本文档生成自 IDL，**不应手工更新数字**——修复 codegen.md 自指 "本文档自身为手工维护" 的矛盾。

**C3 — `specs/gameplay/08-api-idl.md` 包含已废弃的 RejectionReason enum (严重过期)**

- 文件: `specs/gameplay/08-api-idl.md` L68-112
- 问题: 该文件的 RejectionReason enum 列出了 `NotMovable`、`Fatigued`、`MissingBodyPart`、`TileBlocked`、`CarryFull`、`NotYourRoom`、`BodyTooLarge`、`SourceEmpty`、`TargetFull`、`TargetEmpty`、`AlreadyHacked`、`AlreadyDebilitated`、`InvalidDamageType`、`NotSource`、`StillSpawning`、`AlreadyFullHealth`、`FriendlyTarget`、`NotYourSpawn`、`InsufficientMoveParts`、`NoPath` 等 30+ 个代码。
- 所有以上代码在 api-registry.md §2 中已明确被合并至 canonical 47 codes (35 game + 12 auth) 或降级为 `debug_detail` 字段。commands.md L226 明确声明: "旧文档中出现的 NotMovable、Fatigued、SourceEmpty、TargetFull、TargetEmpty、AlreadyHacked、MissingBodyPart、TileBlocked、CarryFull、NotYourRoom、BodyTooLarge 等代码已被统一合并至 canonical 47 码或降级为 debug_detail。"
- 影响: 实现者若依据 gameplay spec 实现将生成与 registry 完全不同的错误枚举，所有 WASM SDK 代码生成将破裂。这是最严重的跨文档不一致。
- 修复建议: 将 `specs/gameplay/08-api-idl.md` 的 RejectionReason enum 替换为对 `api-registry.md §2` 的引用，删除过期枚举定义。同时检查 IDL YAML 的 35 个 canonical 码是否完整覆盖了这些旧代码代表的语义（如 `Fatigued` → 哪个 canonical code？）。

### High

**H1 — `specs/gameplay/08-api-idl.md` API 版本号与 game_api.idl.yaml 冲突**

- 文件: `specs/gameplay/08-api-idl.md` L48 `version: "1.0.0"` vs `specs/reference/game_api.idl.yaml` L8 `api_version: "0.4.0"`
- 影响: 两个文件声明不同的 IDL 版本号。SDK 生成工具和 CI validator 无法判断权威版本。
- 修复建议: gameplay spec 应将版本号替换为对 `game_api.idl.yaml` 的引用，或直接同步为 `0.4.0`。长线方案：gameplay spec 不应冗余声明已在 YAML 中定义的字段。

**H2 — `specs/gameplay/08-api-idl.md` StructureType 枚举与 economy.idl.yaml 完全不一致**

- 文件: `specs/gameplay/08-api-idl.md` L65-66 vs `specs/reference/economy.idl.yaml` L239-273
- 问题: gameplay spec 列出 13 种结构类型 (Spawn, Extension, Tower, Storage, Link, Extractor, Lab, Terminal, Nuker, Observer, PowerSpawn, Factory, Depot)，economy.idl.yaml 列出 12 种 (Spawn, Extension, Road, Wall, Rampart, Storage, Tower, Link, Extractor, Lab, Terminal, Observer)。交集仅 9 种。Road/Wall/Rampart 在 gameplay spec 中缺失；Nuker/PowerSpawn/Factory/Depot 在 economy IDL 中缺失。
- 影响: 两个核心 spec 对 StructureType 的定义完全不一致，代码生成将产生不同的 struct 枚举。
- 修复建议: D-item 需用户裁决。权威 StructureType 定义应在 `game_api.idl.yaml` type_registry 中注册（当前未注册），然后 gameplay spec 和 economy IDL 均引用该处。

**H3 — Type Registry 未集中注册关键枚举类型**

- 文件: `specs/reference/game_api.idl.yaml` §type_registry (L24-67)
- 问题: 只注册了 `ObjectiveType` 一个枚举和 7 个 fixed-point 类型。以下至少在两处 IDL 或 spec 中引用的类型缺乏集中定义: `Direction4`, `BodyPart`, `StructureType`, `ResourceType`, `DamageType`, `EntityId`, `PlayerId`, `DroneId`, `SpawnId`, `RoomId`, `DeployId`。它们的 wire 格式 (u32/u64/string)、序列化方式在不同文档中靠推测。
- 影响: 跨语言 SDK 生成时无法从单一 IDL 源推导类型，容易出现 Rust `u64` ↔ TypeScript `number` ↔ JSON `string` 的不一致。
- 修复建议: 在 `game_api.idl.yaml` type_registry 中新增 `enum_types` 段落，统一定义所有跨 IDL 引用的枚举和 ID 类型的 wire representation。

**H4 — R27 ML-8 IDL 字段注解不完整（已知缺口未闭合）**

- 文件: `specs/reference/api-registry.md` L396-397
- 问题: api-registry 明确标注 "当前 YAML 中仅部分字段有标注——需补齐全部工具"。检查 YAML 确认: 多数 MCP tool 参数缺少 `required`/`optional`/`default` 三元组标注，也缺少 `errors` 列表（按 canonical rejection reason）。
- 影响: SDK stub 生成器无法生成准确的类型签名（哪些参数可省略？default 值是什么？）。MCP schema 暴露给 AI agent 的字段描述不完整。
- 修复建议: 系统性地为所有 57 个 MCP 工具 + 11 个 Auth 工具 + 所有 CommandAction 参数 + 所有 RejectionReason 的触发条件补齐 `required/optional/default` 和 `errors` 注解。这是 R27 明确标记的待办项。

**H5 — auth_api rate_limit_key 枚举值不完整**

- 文件: `specs/reference/auth_api.idl.yaml` §7 security_columns (L659-667) vs `specs/reference/api-registry.md` §3 MCP 工具表
- 问题: auth_api 的 `rate_limit_key` canonical values 仅列出 `per_ip, per_player, per_admin, per_device, per_session, global`。但 game_api MCP 工具表使用了 `per_room`、`per_drone`、`per_structure`、`host_only`，这些在 auth 安全列参考中未定义。
- 影响: 安全审计和 rate limiter 实现在 auth_api 定义的范围内无法处理 per_room/per_drone/per_structure 粒度的限流。
- 修复建议: 将 auth_api §7 `rate_limit_key` values 扩展为包含 `per_room, per_drone, per_structure, host_only`。或明确此 security_columns 仅适用于 auth_api 工具，game_api 工具使用 game_api 自己的 rate_limit_key 定义。

**H6 — JSON-RPC error.code 统一为 -32000，细化信息依赖 data 字段**

- 文件: `specs/reference/api-registry.md` §8 (L668-692)，`design/interface.md` §5.6 (L130-153)
- 问题: 所有 Swarm 错误共享同一 `error.code = -32000`。虽然 SDK 应从 `error.data.rejection_reason` 生成 typed exception，但：
  - 通用 JSON-RPC 客户端/中间件通常基于 `error.code` 分类错误，统一码导致无法区分 transient vs permanent 错误
  - `retry_allowed` 字段在 `design/interface.md` §5.6 提到但 api-registry §8 的 SwarmError envelope 中缺失
  - `idempotency_key` 字段同样在 design doc 提到但 registry 缺失
- 影响: 非 Swarm SDK 的通用 HTTP/gRPC 客户端无法基于 error.code 做智能重试，必须解析 data 字段。
- 修复建议: 在 api-registry §8 SwarmError envelope 中显式包含 `retry_allowed`、`idempotency_key` 字段（当前设计已设计但 registry 未登记）。考虑使用细分 error.code range（如 -32001 起）为不同类型的 SwarmError 分配独立 JSON-RPC code，同时保持 `rejection_reason` 字符串为 canonical wire enum。

**H7 — `specs/gameplay/08-api-idl.md` 与 game_api.idl.yaml 的 host function 参数类型不一致**

- 文件: `specs/gameplay/08-api-idl.md` L262-263 `get_objects_in_range` params 声明 `range: i32` vs `specs/reference/game_api.idl.yaml` (和 api-registry §4.1) 声明 `range: u32`
- 问题: `range` 参数在 gameplay spec 中为 signed `i32`，在权威 IDL 中为 unsigned `u32`。WASM ABI 签名不一致导致跨实现类型错误。
- 影响: SDK 生成和 WASM 模块编译时参数类型不匹配。
- 修复建议: gameplay spec 中所有 host function 签名必须与 api-registry §4.1 一致。gameplay spec 应移除冗余签名，改为引用 registry。

### Medium

**M1 — codegen.md 自指「手工维护」与「生成文档」矛盾**

- 文件: `specs/reference/codegen.md` L24
- 问题: 该文档声明 "本文档自身为手工维护" 但同时 §2 声明 "API Registry 全量生成" 且 codegen.md 中列举的计数（如 56 active）应与生成产物一致。文档中 "建议 CI 同时检查本文档中的计数声明与 --check 输出的一致性" 意味着它需要人工保持同步——但这与 codegen 精神矛盾。
- 修复建议: codegen.md 应从生成链中提取计数声明，或明确标注 "以下数字为最近一次 codegen 快照，CI diff 可能滞后"。

**M2 — `specs/reference/host-functions.md` 声明的模块大小上限与 api-registry 不一致**

- 文件: `specs/reference/host-functions.md` L89 `模块大小上限: 5 MB` vs `specs/reference/api-registry.md` §12 blob types `wasm_module: 64 MB`
- 问题: WASM 模块大小的权威上限在 api-registry 为 64 MB (blob max size)，host-functions.md 写 5 MB (可能指编译后 .wasm binary? 可能是旧值)。
- 影响: 实现者混淆模块大小限制，可能导致 SDK 生成错误的大小校验。
- 修复建议: 统一为 api-registry 的 64 MB，host-functions.md 移除重复声明或引用 registry。

**M3 — `economy.idl.yaml` ResourceRate_i64 定义与 game_api.idl.yaml 存在细微差异**

- 文件: `specs/reference/economy.idl.yaml` L28-36 `ResourceRate_i64` vs `specs/reference/game_api.idl.yaml` L26-29
- 问题: game_api 描述为 "Resource rate in micro-units per tick (1.0 = 1_000_000)"，economy 描述为 "resource units per tick" (无 micro-unit 说明)。两者底层类型和 scale 一致 (i64, 1e6) 但语义描述不同。
- 修复建议: economy 应在描述中明确引用 game_api 定义，或统一描述为 "Signed resource rate in micro-units per tick (1.0 = 1_000_000, scale=1e6)"。

**M4 — `swarm_simulate` 与 `swarm_dry_run` 输出 schema 相似但字段命名不一致**

- 文件: `specs/reference/api-registry.md` §3 Debug 表 L300-302
- 问题: `swarm_simulate` 输出 `{trace, authoritative: false, assumptions, confidence}` vs `swarm_dry_run` 输出 `{trace, fuel_used, errors}`。两者均产生 "trace" 但字段组合不同且 `swarm_simulate` 的 trace 格式未定义。`swarm_dry_run` 字段 `errors` 的类型未声明（是 `[string]`? `[RejectionReason]`?）。
- 影响: SDK 开发者必须分别处理两种几乎相同但有微小差异的输出类型。
- 修复建议: 统一 trace 格式为共同的 `SimulationTrace` schema，两工具共享，差异字段作为可选的 sidecar。

**M5 — `specs/reference/codegen.md` 声称 game_api tool 为 56 个但 YAML 声明为 57**

- 文件: `specs/reference/codegen.md` L28 `56 active` vs `specs/reference/game_api.idl.yaml` L490 `total_tools: 57`
- 问题: 与 C2 紧密相关但更聚焦 codegen 视角。codegen.md 作为生成链的入口，其声明的计数与 IDL 源不同步意味着 `hermes codegen generate --check` 会报漂移。
- 修复建议: 与 C2 一同修复，统一计数后更新 codegen.md。

### Low

**L1 — `mcp-tools.md` Play 分组计数 `16` 与 api-registry 头 `15` 不一致**

- 文件: `specs/reference/mcp-tools.md` L19 `Play | 16` vs `specs/reference/api-registry.md` L257 `Play (15)`
- 问题: mcp-tools.md 的派生文档计数与权威 registry 头不一致。
- 修复建议: 统一计数后更新 mcp-tools.md。

**L2 — `commands.md` Build 指令 JSON 示例字段名不一致**

- 文件: `specs/reference/commands.md` L93 `"structure": "Extension"` vs L129 `"structure_type": StructureType`
- 问题: JSON 示例使用 `structure` 字段，但 IDL 定义参数名为 `structure_type`。
- 修复建议: JSON 示例改为 `"structure_type": "Extension"`。

**L3 — `gameplay/08-api-idl.md` 中 `host_get_terrain` 签名缺少 `room_id` 参数类型标注**

- 文件: `specs/gameplay/08-api-idl.md` L258-260 `get_terrain: params: [room_id: u32, ...]` — 格式正确但该文件使用了短名称 (get_terrain) 而 registry 使用规范名称 (host_get_terrain)
- 建议: 统一使用 registry 的规范名称或在 gameplay spec 添加「此文件使用短名称，规范名称见 registry」说明。

---

## 3. 亮点

1. **Fixed-point 类型系统设计优秀**: `ResourceRate_i64`、`BasisPoints`、`micro_cost`、`milli_distance`、`MilliUnits` 等类型在所有 IDL 中一致使用，彻底消除了 f64 的跨平台非确定性问题。类型 registry + scale 约定清晰，代码生成可直接映射到语言原生整数。

2. **RejectionReason 分层命名空间设计**: 35 game + 12 auth (offset 1000+) 的命名空间隔离避免了 code 冲突。`debug_detail` / `detail_level` 设计在 wire 稳定性与调试丰富性间取得良好平衡，competitive/practice/training 三级控制信息泄漏。

3. **codegen 单事实源链清晰**: game_api → auth_api → economy 三个 YAML IDL → api-registry.md 的生成链定义明确。CI check 机制阻止 hand-fork drift。R27 ML-9 的 `schema_source` + `alias_of` 使 auth tool 的 game_api shortcuts 可自动跳过，从 canonical source 生成唯一实现。

4. **MCP 安全列设计完整**: 每个工具声明 5 个安全列 (`required_scope`, `subject_source`, `replay_class`, `visibility_filter`, `rate_limit_key`)——这在同类游戏 API 设计中少见，为安全审计和 replay 确定性提供了机器可读的完备元数据。

5. **TickTrace Envelope 22 个字段的确定性合同**: 包含 `validator_version`、`rejection_reason_registry_version`、`canonical_codec_version`、`world_action_manifest_hash` 等版本锁定字段，确保任意历史 replay 可精确复现。这是 replay 确定性的设计典范。

6. **Capability 白名单 + Rhai 模组隔离**: Rhai RuleMod 的事务性语义 (all-or-nothing buffer) + 12 级 capability 授权 + 6 级错误降级，在不牺牲安全性的前提下提供了丰富的世界自定义能力。

---

## 4. CrossCheck

以下为超出 API/DevEx 评审方向但值得其他 reviewer 关注的问题：

- **CX-1**: `specs/gameplay/08-api-idl.md` 的 Command 校验规则（如 validator 数组）是否与 `specs/core/02-command-validation.md` 一致？→ 建议 **rev-dsv4-architect** 检查 gameplay spec 中的 validator 谓词列表与 core validation spec 的对齐

- **CX-2**: `specs/gameplay/08-api-idl.md` L61 `Direction: [North, South, East, West]` 的顺序是否与 api-registry §7 Direction4 的 enum 值 (North=0, South=1, East=2, West=3) 一致？→ 建议 **rev-dsv4-determinism-perf** 检查 NESW 顺序在整个引擎中的一致性（pathfinding neighbor order 约定）

- **CX-3**: api-registry §5.1 声明 `MAX_BODY_PARTS = 50`，economy.idl.yaml `max_body_parts: 50`，但 gameplay spec 中未明确声明——是否存在 body part 数量的双重约束被遗漏在 validator 中的风险？→ 建议 **rev-dsv4-design-economy** 检查 economy IDL 的 spawn limits 与 game_api capacity limits 的交叉引用完整性

- **CX-4**: `auth_api.idl.yaml` §7 `replay_class` values 包含 `deploy_mutation`（在 api-registry §3 security columns L856 中出现）但 auth_api security_columns L643-647 仅列出 4 个值（non_replayable, read_replay_safe, idempotent_mutation, admin_critical）——`deploy_mutation` 是否应在 auth 安全列中注册？→ 建议 **rev-dsv4-security** 检查 replay_class 的跨 IDL 一致性

- **CX-5**: api-registry §5.5 Hardware Baseline 声明 `Hard cap players = 1000` 标记为 `benchmark-gated（未验证）`——这是 PG-3 (PLAYTEST-GATED.md) 的范畴。→ 建议 **rev-gpt-design-economy** 确认此容量声明是否与 ROADMAP 中的 playtest-gated 项对齐

- **CX-6**: `economy.idl.yaml` AlliedTransfer 的 `new_player_lock: 500 tick` 字段在 `specs/core/08-resource-ledger.md` 的权威定义中是否存在对应声明？→ 建议 **rev-gpt-security** 交叉检查 economy IDL 的 transfer constraints 与 resource ledger 的一致性

---

## 5. 裁决项摘要

| ID | 问题 | 用户需裁决 |
|----|------|-----------|
| **D1** | C1: CommandAction 计数 19 vs 21 — 方案 A (升格 Leech/Fabricate) 还是方案 B (拆分为 core+custom) | 是 |
| **D2** | C2: MCP 工具计数统一值 — 确定为 57/58? host-only 工具是否计入? | 否 (技术事实，修复即可) |
| **D3** | H2: StructureType 权威定义位置 — game_api.idl.yaml type_registry vs 当前分散定义 | 否 (建议集中到 IDL registry) |

---

*评审日期: 2026-06-21 | 评审模型: DeepSeek V4 Pro | 审查范围: design/interface.md + specs/reference/* + specs/gameplay/08-api-idl.md + gateway-protocol.md*
