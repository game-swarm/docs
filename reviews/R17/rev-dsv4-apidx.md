# R17 API/Developer Experience Review — DeepSeek V4 Pro

**Reviewer**: rev-dsv4-apidx (API/DX 评审员)
**Date**: 2026-06-18
**Review Target**: R17 Phase 1 Clean-Slate — 权威单源闭合验证
**Documents Reviewed**: 10 files (design/README.md, design/interface.md, design/tech-choices.md, specs/reference/api-registry.md, specs/reference/game_api.idl.yaml, specs/reference/commands.md, specs/reference/host-functions.md, specs/reference/mcp-tools.md, specs/core/02-command-validation.md, specs/core/09-snapshot-contract.md)

---

## Verdict: REQUEST_MAJOR_CHANGES

R15-R16 发现的四个核心问题中，IDL 结构化（schema 完整性）和命名规范统一两个方向取得了实质进展。但"权威单源闭合"这一根本目标尚未达成：api_version 跨文档不一致、RejectionReason ~28 个使用中变体未注册、MCP 工具清单 interface.md ↔ registry 仍然高度发散。验证规范的实现路径与权威注册表之间存在系统性断裂——引擎无法通过 CI 的"未注册则拒绝"门禁。

---

## Findings

### Critical

**C1 — api_version 跨文档不一致 (IDL 0.2.0 ≠ registry.md 0.1.0)**
- `game_api.idl.yaml` 第 8 行: `api_version: "0.2.0"`
- `api-registry.md` 第 14 行: `当前 API 版本: 0.1.0`
- Registry 自身声明"冲突时以 YAML 为准"，这意味着 Markdown 中的 0.1.0 是过时的。但开发者阅读 Markdown 时会被误导。R15→R16→R17 三轮后此字段仍未同步。
- **影响**: 机器生成文档与人类可读文档的版本号分歧，TickTrace 中记录的 api_version 取决于哪个源被引用——确定性受损。

**C2 — RejectionReason 权威注册表缺失 ~28 个验证规范实际使用的变体 (35 vs ~63)**
- `api-registry.md` §2 定义 35 个变体 (Pipeline 2 + Validation 26 + MCP 3 + Runtime 6)
- `02-command-validation.md` §3 逐指令校验矩阵使用以下未注册变体:
  `NotMovable`, `Fatigued`, `MissingBodyPart`, `TileBlocked`, `StillSpawning`, `OutOfRoom`, `NoPath`, `PathTooLong`, `InsufficientMoveParts`, `CarryFull`, `NotSource`, `SourceEmpty`, `TargetFull`, `TargetEmpty`, `NotYourRoom`, `TileOccupied`(vs 注册表中的 `PositionOccupied`), `InvalidTerrain`, `TooManyConstructionSites`(vs `ConstructionLimitReached`), `AlreadyFullHealth`, `FriendlyTarget`, `NotYourSpawn`, `BodyTooLarge`(vs `NotEnoughBodyParts`), `ExceedsRoomCapacity`, `NotFriendly`, `AlreadyHacked`, `InvalidDamageType`, `AlreadyDebilitated`, `MainActionQuotaExceeded`
- `commands.md` §Rejection 同样列出这些未注册变体
- 至少存在三组命名冲突: `TileOccupied`/`PositionOccupied`、`TooManyConstructionSites`/`ConstructionLimitReached`、`BodyTooLarge`/`NotEnoughBodyParts`——语义重叠但名称不同
- **影响**: Registry 的 CI 规则"未注册的 CI 拒绝"将阻止当前验证规范的实现代码通过门禁。权威单源原则在验证层已断裂。

**C3 — MCP 工具清单 interface.md vs api-registry.md 系统性分歧 (~73% 工具仅存在于其中一个文档)**
- `interface.md`: 列出 ~45 个工具（侧重 Auth 19个、Tournament 4个、Debug 7个、World 4个、Deploy 4个、Learn 4个、Economy 3个）
- `api-registry.md`/IDL: 列出 46 个工具（侧重 Onboarding 8个、Play 14个、Deploy 6个、Debug 8个、Admin 6个、SDK 1个、Resources 2个、Economy 合并入 Play）
- 两文档共享仅约 12 个工具: `swarm_get_snapshot`, `swarm_get_terrain`, `swarm_get_world_rules`, `swarm_deploy`, `swarm_validate_module`, `swarm_get_replay`, `swarm_get_economy`, `swarm_get_drone_efficiency`, `swarm_get_economy_trend`, `swarm_simulate`, `swarm_sdk_fetch`, `swarm_dry_run`(≈ `swarm_dry_run_commands`)
- R16 报告此问题为 Critical（"~68% of tools exist in only one document"）。R17 中分歧仍然存在，但方向反转——R16 时 registry 工具较少，R17 中 registry 和 interface.md 各自演化出不同的工具集
- `interface.md` 显式声明"权威工具清单见 API Registry §3"，但其表格内容与 Registry 完全不同——自我矛盾
- **影响**: 开发者无法确定哪些 MCP 工具实际存在。Auth 和 Tournament 工具（interface.md 独有）与 Onboarding/Play 细粒度查询工具（registry 独有）之间的选择直接影响架构。

**C4 — interface.md §4 强制要求的 6 个工具在 IDL/Registry 中缺失**
- interface.md 第 9 行声明以下工具"必须进入工具目录并提供完整的 request/response/error 定义":
  `swarm_get_schema`, `swarm_get_docs`, `swarm_get_player_status`, `swarm_get_available_actions`, `swarm_explain_last_tick`, `swarm_submit_csr`
- 这 6 个工具中有 5 个完全不在 IDL 的 46 个工具中（仅 `swarm_submit_csr` 在 interface.md 中列出但不在 registry 中；`swarm_deploy` 和 `swarm_sdk_fetch` 和 `swarm_validate_module` 和 `swarm_get_snapshot` 在两者中均存在）
- **影响**: interface.md 自身的设计合同被打破——它要求的工具未进入其声称的权威源。新开发者按 interface.md 寻找这些工具会失败。

### High

**H1 — Host function 签名三文档分歧 (interface.md / host-functions.md ≠ registry / IDL)**
- `host_get_terrain`:
  - interface.md + host-functions.md: `(x: i32, y: i32) -> i32`
  - api-registry.md + IDL: `(room_id: u32, out_ptr: i32, out_len: i32) -> i32`
- `host_get_world_rules`:
  - interface.md + host-functions.md: `(out_ptr: i32, out_len: i32) -> i32`
  - api-registry.md + IDL: `(rule_id_ptr: i32, rule_id_len: i32, out_ptr: i32, out_len: i32) -> i32`
- 两本实现参考文档（interface.md、host-functions.md）展示的签名与 IDL 不一致。以 IDL 为准的 codegen 会生成与参考文档不同的 SDK 绑定。
- **影响**: SDK 开发者如果参考 host-functions.md 而非 IDL 会写出错误的 import 声明。WASM 模块的 ABI 不匹配导致运行时 `ERR_ABI_VERSION`。

**H2 — IDL 类型系统缺底层定义，仅使用字符串字面量**
- IDL 使用 `"PlayerId"`, `"EntityId"`, `"Direction4"`, `"TerrainGrid"`, `"[Entity]"` 等字符串作为类型
- ~40 个自定义类型未定义其底层表示（Primitive、Struct、Enum、Union）
- 无类型继承/组合关系定义
- **影响**: 从 IDL 生成 TypeScript/Rust SDK 的 codegen 无法确定 `PlayerId` 是 `u64`、`string` 还是 newtype wrapper。方向 enum `Direction4` 的整数编码存在于 api-registry.md §7 但未编码进 IDL 的类型定义中。

**H3 — MCP 工具 IDL 缺 error schema**
- interface.md §4 要求"所有 MCP 工具必须具备 inputSchema、outputSchema 和 error schema"
- IDL 中每个工具有 `input_schema` 和 `output_schema`，但无 `error_schema` 字段
- **影响**: SDK 生成的错误处理代码无法确定每个工具可能返回哪些 SwarmError 变体。调用者需要全局枚举所有可能性而非按工具精确匹配。

**H4 — SwarmError JSON-RPC envelope 格式三文档不统一**
- `interface.md` §5.6: `{"code": -32000, "data": {"swarm_error": "InsufficientResources", "retry_allowed": false, ...}}` — 错误类型嵌套在 `data.swarm_error`，code 为固定数值
- `api-registry.md` §8: `{"code": "RejectionReason", "data": {"command_index": 3, "rejection_detail": "..."}}` — 错误类型在 `error.code`，为字符串
- `game_api.idl.yaml` §8: 与 registry.md 一致，使用字符串 code
- interface.md 的格式与权威源不一致，包含 registry/IDL 中不存在的字段（`retry_allowed`、`idempotency_key`）
- **影响**: MCP 客户端按 interface.md 解析错误会与按 registry 实现的服务器不兼容。

**H5 — Per-player drone cap 10x 分歧**
- `api-registry.md` §5: `Per-player drone cap = 500 (world.toml 可调)`
- `02-command-validation.md` §6: `MAX_DRONES_PER_PLAYER = 50 (默认)`
- `api-registry.md` §5 同时列出 `Global drone cap = 10,000`
- 500 vs 50 相差 10 倍。若 registry 的 500 是正确的，验证规范的常量和校验逻辑都需要更新；若 50 是正确的，registry 和全局 cap 的比例关系需要重新计算。
- **影响**: Spawn 指令的 `RoomDroneCapReached` 拒绝阈值有 10x 不确定性。

### Medium

**M1 — CommandIntent 的 `object_id` 字段未在 IDL 中建模**
- `commands.md` 和 `02-command-validation.md` 的所有 CommandIntent 示例包含 `object_id` 字段（执行指令的 drone），但 IDL 的 CommandAction 变体定义中无此字段
- IDL 中仅包含 action-specific 参数（`target_id`, `direction`, `resource`, `amount` 等）
- `object_id` 按 02-command-validation.md §2.1 的描述属于 "禁止字段" 之外——它由引擎注入而非 WASM 提供，但其存在性和语义应在 IDL 中有所体现
- **影响**: 从 IDL 生成的 SDK 类型不含 `object_id`，但实际运行时每个 Command 都携带它——调试日志和序列化格式与类型定义不一致

**M2 — Capability profiles 工具分配与工具清单不同**
- `interface.md` §4.1a 的 capability profiles 引用 interface.md 自身工具集中的工具名
- `api-registry.md` §3.2 的 profiles 引用 registry 工具集中的分类名
- 两套 profiles 无法互操作——interface.md onboarding 包含 `swarm_get_server_trust`，registry onboarding 不包含
- **影响**: `swarm_get_schema(profile="onboarding")` 的返回结果取决于服务端使用的是哪个工具集

**M3 — MCP 工具命名空间不统一**
- `resources/list` 和 `resources/read` 使用 `/` 命名空间前缀
- 所有其他 44 个工具使用 `swarm_` 前缀
- 无文档解释为何 Resources 类别使用不同的命名约定
- **影响**: SDK 客户端无法通过统一前缀过滤 MCP 工具列表

**M4 — 无 API 版本化与向后兼容策略文档**
- 多个文档提及 `api_version` 字段和 TickTrace 中的版本号
- 但无文档定义:
  - 版本号语义（SemVer？单调递增？）
  - 向后兼容保证（哪些变更允许在 minor 版本中）
  - 废弃策略（旧 API 版本支持多久）
  - SDK 版本兼容矩阵
- **影响**: 第三方 SDK 开发者无法评估升级风险

**M5 — `swarm_sdk_fetch` 输出格式不一致**
- `interface.md` §5.3: `examples: string[]`（数组）
- IDL: `examples: string`（单字符串）
- `api-registry.md`: 未列出 examples 字段
- **影响**: SDK 生成的返回类型在两个源之间不同

**M6 — Rate limit 格式不一致**
- IDL/Registry: 使用 `"X/tick"`, `"X/min"`, `"X/h"` 格式
- `mcp-tools.md` §Rate Limiter: 使用 `tokens/s` 格式，且按 Source 分类（WASM: 1000, MCP_Query: 100, MCP_Deploy: 10...）
- 两套限流体系是否独立叠加？mcp-tools.md 的 source-level 限流与 registry 的 per-tool rate limit 关系不明确
- **影响**: 客户端无法准确预测限流行为

### Low

**L1 — SDK codegen 路径未指定**
- `tech-choices.md` §10 声明 "game_api.idl → codegen → SDK" 但未指定:
  - 使用哪个 codegen 工具
  - TypeScript 和 Rust 的代码生成是否共享同一套模板
  - codegen 是构建时、CI 时还是手动触发的
- 给定 IDL 中的类型缺口（H2），codegen 目前无法生成完整可用的 SDK

**L2 — `commands.md` 声称 15 种指令但实际文档化了 19 种**
- `commands.md` 第 22 行: "以下 15 种指令对应 CommandAction enum 的 15 个具体变体"
- 实际后续文档化了完整的 19 个变体（11 core + 2 global + 6 special）
- 数字 15 来自旧版本计数（可能不含 Custom 路由的特殊攻击），未随 R15-R16 更新

**L3 — `host-functions.md` 超预算行为描述与 Registry 不一致**
- `host-functions.md` 第 62 行: "超出预算 → 返回 -1，tick 继续执行（非致命错误）"
- Registry §4.5: 预算耗尽返回 `-4 (ERR_BUDGET_EXHAUSTED)`, `-5 (ERR_PLAYER_BUDGET)`, `-6 (ERR_GLOBAL_BUDGET)`
- -1 在 Registry 中对应 `ERR_MEMORY_BOUNDS`（内存越界），语义完全不同

**L4 — `02-command-validation.md` §5.1 中的 `PermissionDenied` 未在 Registry 中注册**
- 验证规范 §5.1 拒绝码表格列出 `PermissionDenied`（用于 admin trace）
- 该变体不在 Registry 的 35 个 RejectionReason 中

**L5 — `commands.md` §1 "特殊攻击" 节描述 "第 16 个变体 CommandAction::Custom(type) 通过 CustomActionRegistry 路由到 8 种特殊攻击"**
- IDL 中特殊攻击是独立的 6 个 command_action variants (index 14-19)，而非 Custom 路由
- Leech 和 Fabricate 在 IDL 的 `custom_actions` 段中，与 Core enum 分离
- `commands.md` 的描述与 IDL 的建模方式不一致

---

## Strengths

1. **IDL 机器可读化取得实质进展**: game_api.idl.yaml 现在包含所有 19 个 CommandAction、35 个 RejectionReason、46 个 MCP 工具、5 个 Host Function 的结构化定义——这是 R15 时完全不存在的。IDL 提供了 CI 自动校验的基础。

2. **Command 校验管线文档优秀**: `02-command-validation.md` 的 CommandIntent→RawCommand→ValidatedCommand 三态转换、逐指令校验矩阵（七大维度穷举表）、同 tick 多命中优先级、抗永久锁死证明——这些在 API 设计文档中属于罕见的高质量。

3. **快照截断合同 (H3) 设计严谨**: 确定性截断顺序（距离桶→entity_id 字典序）、关键实体永不截断、竞技世界截断降级标记、`truncated`/`omitted_categories` 字段——边界条件考虑全面。

4. **Safe Hint Ladder (DH2) 是优秀的 DX 设计**: 竞技/练习/训练三级错误提示，Rust 侧 `HintLevel` enum 统一实现，`CommandError` 三态 payload——既保护竞技公平又支持调试。

5. **Recycle 比例退还与 lifespan 挂钩**: refund_pct = max(0.1, 0.5 × remaining/total) 的公式防止了 drone 末期套利——经济约束在 API 层面的体现值得肯定。

6. **Deploy-reset 规则**: refund credit 在部署时清零（同 session 除外）——防止跨模块预算转移的反放大设计。

7. **Host Function ABI 错误优先级**: 9 级错误优先级（ERR_MEMORY_BOUNDS → ERR_TIMEOUT）定义清晰，确定性有保证。

8. **RejectionReason 命名规范文档化**: `InsufficientResource` 单数统一、`ObjectNotFound` 取代 `TargetNotFound`、`NotVisibleOrNotFound` 防 oracle——命名哲学明确。

---

## CrossCheck

### R15 遗留验证

| R15 发现 | R17 状态 |
|----------|---------|
| Move 方向 4 vs 8 三文档冲突 (C1) | **已闭合**。Direction4 统一为 4 方向（North/South/East/West），8 方向标注为 Future RFC。api-registry.md §7、IDL §7、interface.md §5.4 一致。 |
| RejectionReason 三文档三种命名体系 (C2) | **部分闭合**。命名规范已文档化（api-registry.md §2 命名规范段），registry 和 IDL 内部一致。但 ~28 个验证规范实际使用的变体未注册（见 C2 新发现）。 |
| SendMessage 零校验定义 (C3) | **已闭合**。SendMessage 标注为 Future RFC，commands.md 和 interface.md 均不再定义为当前指令。 |
| MCP 工具 schema 普遍缺失 (C4) | **已闭合**。IDL 中所有 46 个工具均有 input_schema 和 output_schema。但 error schema 仍缺失（见 H3）。 |

### R16 遗留验证

| R16 发现 | R17 状态 |
|----------|---------|
| MCP tool list catastrophic divergence (C1) | **未闭合，方向反转**。R16 时 interface.md 有大量工具而 registry 较少；R17 中两文档各自演化出不同工具集，分歧率仍然 ~73%。需要决策：以哪个文档为准，然后删除另一个文档中不在权威源的工具。 |
| interface.md schema 要求未满足 (C2) | **部分闭合**。IDL 现在有 input/output schema。但 interface.md §4 强制要求的 6 个工具中有 5 个不在 IDL 中（见 C4）。 |
| Command enum 不一致 (C3) | **已闭合**。IDL 定义 19 个 variants，api-registry.md 同步。commands.md 仍声称 15 种但实际文档化 19 种（L2）——低优先级。 |
| MCP 工具清单三文档不一致 (C4) | **部分闭合**。IDL 与 registry.md 在 46 工具上一致。但 interface.md 和 mcp-tools.md 仍有独立工具集。mcp-tools.md 的 Auth/Tournament 工具在 registry 中不存在，registry 的大量 Read 工具在 mcp-tools.md 中不存在。 |

### 新发现（R17 特有）

- **api_version 不一致** (C1): IDL 0.2.0 vs registry.md 0.1.0——这是一个新引入的分歧，之前版本可能一致
- **RejectionReason 注册表不完整** (C2): 验证规范使用了 ~28 个未注册变体——这是设计阶段的核心问题：验证规范是"实现合同"，注册表是"权威枚举"，两者必须一致
- **Host function 签名分歧** (H1): interface.md 和 host-functions.md 使用了与 registry/IDL 不同的签名——说明参考文档在与 IDL 同步更新时落后
- **Error envelope 三格式** (H4): interface.md 的 JSON 结构与 registry 不同——可能导致客户端实现不兼容
- **Drone cap 10x 差异** (H5): 500 vs 50——需要权威裁定

### 闭合建议优先级

1. **统一 RejectionReason 注册表** (C2): 将 02-command-validation.md 使用的所有变体注册到 registry/IDL 中，或将验证规范修改为使用已注册变体。建议前者——验证规范的变体更细粒度，是经过验证的合同。
2. **决策 MCP 工具权威集** (C3): 确定 46 工具清单（registry 版）是否为权威，然后更新 interface.md 表格以匹配，或反之。建议以 registry/IDL 为准，将 Auth/Tournament 工具作为 Future RFC 或在 registry 中补充。
3. **同步 api_version** (C1): 将 registry.md 的版本号更新为 0.2.0，或建立自动化 CI 从 IDL 生成 Markdown 版本号。
4. **补全 interface.md 强制要求的工具** (C4): 将缺失工具加入 IDL 或修改 interface.md 要求。
5. **统一 host function 签名** (H1): 更新 interface.md 和 host-functions.md 以匹配 IDL。
6. **统一错误 envelope** (H4): 以 registry/IDL 格式为准更新 interface.md。
7. **定义 IDL 底层类型** (H2): 为所有自定义类型添加 Primitive/Struct/Enum 定义。
8. **添加 error schema 到 IDL** (H3): 为每个 MCP 工具定义可能的错误变体。
9. **裁定 drone cap** (H5): 确定 50 还是 500，统一所有文档。
