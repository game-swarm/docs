# R39-CV-API-GPT — API/DX 一致性评审报告

## 评审范围

- `specs/reference/api-registry.md`
- `specs/reference/commands.md`
- `specs/reference/mcp-tools.md`
- `specs/reference/codegen.md`
- `design/interface.md`
- 辅助核对：`specs/reference/game_api.idl.yaml`、`specs/reference/auth_api.idl.yaml`、`specs/reference/economy.idl.yaml`

## 结论摘要

当前 API/DX 文档已基本形成“IDL → Registry → 派生参考页”的结构，SwarmError envelope、Action dispatch、MCP 不直接做游戏动作、host function 只读等核心方向一致。但仍存在多处高优先级漂移：Registry 与 IDL 的版本号、MCP 工具计数、Auth RejectionReason 枚举、Arena RFC/active 状态、Command 示例字段名、codegen 输出映射均不一致。若直接作为实现依据，会导致 SDK/codegen、MCP schema、错误处理与能力 profile 产生分叉。

## 关键发现

### P0 — Registry 与 IDL 版本/计数不一致

1. `api-registry.md` 头部声明：`game_api` API 版本为 `0.5.0`、`auth_api` 为 `0.1.0`。
2. 实际 IDL：`game_api.idl.yaml` 为 `0.4.0`，`auth_api.idl.yaml` 为 `0.2.0`，`economy.idl.yaml` 为 `0.1.1`。
3. Registry 声称由 IDL 自动生成且冲突时以 IDL YAML 为准，因此当前 Markdown 生成产物明显漂移，或 IDL 版本未同步更新。

建议：先确定真实目标版本。如果 IDL 是权威，应重新生成 Registry；如果 Registry 是新目标，应回写/升级 IDL 后再生成，避免手工修 Markdown。

### P0 — MCP 工具总数存在三套口径

辅助脚本按 `game_api.idl.yaml` 统计：

- `mcp_tools.tools` 总数：59
- 其中带 `rfc_status` 的工具：4（`swarm_get_leaderboard`、`swarm_tournament_create`、`swarm_tournament_precommit`、`swarm_tournament_status`）
- 非 RFC 工具：55
- 分类计数：Onboarding 11、Auth 3、Play 16、Deploy 7、Debug 8、Admin 6、SDK 1、Arena 5、Resources 2

文档口径：

- `api-registry.md`/`mcp-tools.md` 声明 Game API 57。
- `api-registry.md` 将 Play 写为 15、Arena 写为 1 active + 3 RFC、Resources 2。
- `design/interface.md` 写为 57 game tools + 11 auth tools。
- `auth_api.idl.yaml` 实际 auth tools 为 12（CSR lifecycle 7 + device/recovery/federation 5）。

主要差异来源：

- `game_api.idl.yaml` 中 Arena 实际有 5 个条目，4 个带 `rfc_status`，但 Registry 只按 1 active + 3 RFC 展示，且把 `swarm_get_leaderboard` 也列入表格。
- IDL Play 为 16，Registry Play 为 15；`swarm_get_world_stats` 和 `swarm_get_leaderboard` 在历史变更/分类中可能未同步。
- Auth 工具数在 `design/interface.md` 仍写 11，明显落后于 12。

建议：为 MCP 工具计数定义唯一规则：`all_declared`、`active_only`、`feature_gated/RFC` 是否计入必须机器化。Registry、mcp-tools、design 只能引用该口径。

### P0 — RejectionReason Registry 与 Auth IDL 不一致

`api-registry.md` 声明 RejectionReason 共 48 codes，并列出 Auth 12 个：

- `InvalidCertificate` 1001
- `NotAuthorized` 1002
- `CertExpired` 1003
- `DeviceNotRegistered` 1004
- `SessionLimitReached` 1005
- `RefreshTokenInvalid` 1006
- `ScopeInsufficient` 1007
- `TokenRevoked` 1008
- `RateLimited` 1009
- `MultiDeviceConflict` 1010
- `UnknownCredential` 1011
- `InternalAuthError` 1012

`auth_api.idl.yaml` 实际 Auth 12 个为：

- `InvalidCertificate` 1001
- `CertExpired` 1002
- `CertRevoked` 1003
- `NotAuthorized` 1004
- `ScopeInsufficient` 1005
- `DeviceNotRegistered` 1006
- `DeviceLimitReached` 1007
- `CertificateLimitReached` 1008
- `InvalidCSR` 1009
- `UnknownCredential` 1010
- `RateLimited` 1011
- `InternalAuthError` 1012

这不是单纯排序问题，而是 code→name 绑定变化。SDK typed exception、wire compatibility、错误文档都会受影响。

同时 `game_api.idl.yaml` 声明 game canonical total 为 35；实际 variants 37，其中 pipeline 2 个不计入 enum，indexed game codes 为 35。合并 auth 后 indexed 总数为 47，而 Registry 声称 48，并额外包含 `NotEligible` #48。该 `NotEligible` 未在当前 `game_api.idl.yaml` 中出现。

建议：优先统一 RejectionReason IDL 与 Registry。若 `NotEligible` 是新目标，必须先加入 IDL 并明确 index；若不是，应从 Registry 生成产物中移除。Auth code namespace 需要迁移策略或明确 breaking change。

### P1 — CommandAction 示例字段与 Registry schema 漂移

Registry §1 声明所有 11 个 CommandAction + Action dispatch 均包含共享 `object_id`，且 Build 参数为 `structure_type: StructureType, x: i32, y: i32`。

`commands.md` 存在示例漂移：

- `Spawn` 示例缺少共享 `object_id`，只包含 `spawn_id` 和 `body_parts`。
- `TransferToGlobal` 示例缺少共享 `object_id`。
- `TransferFromGlobal` 示例缺少共享 `object_id`。
- `Build` 示例使用 `structure` 字段，而 Registry/IDL 使用 `structure_type`。
- `Recycle` 在 Registry 表格参数列又写 `object_id`，但 Registry 前文说共享字段不在各 action 参数列重复列出；这是内部展示规则不一致。

建议：派生参考页示例应由 IDL schema 生成或至少由 schema lint 校验，避免 SDK 用户复制后失败。

### P1 — Error envelope 总体一致，但派生页引入未注册错误码

一致部分：

- `api-registry.md` §8、`mcp-tools.md`、`design/interface.md` 均要求 JSON-RPC 2.0 error object。
- `error.code` 为 numeric，Swarm application error 使用 `-32000`。
- canonical 业务错误放入 `error.data.rejection_reason`。
- `debug_detail` 为非 canonical 上下文，最大 512 bytes，受 `detail_level` 控制。

问题：

- `design/interface.md` §5.3 为 `swarm_sdk_fetch` 写了 `SDKNotFound`、`UnsupportedLanguage`、`RateLimited`，其中前两个未出现在当前 Registry/IDL RejectionReason 中。
- `design/interface.md` §5.6 的非规范性指引写 `ConflictRetry`、`InvalidCommand`，当前 Registry/IDL 未注册。

建议：即使标为“非规范性指引”，也不应出现未注册 canonical-looking code。应改为已注册的 `RateLimited`、`SchemaViolation`、`InternalError` 等，或明确为 `debug_detail`/本地 SDK exception，不是 wire RejectionReason。

### P1 — Host function 返回语义在 design 内部自相矛盾

`design/interface.md` §5.1 写：`ret >= 0 = bytes_written，ret < 0 = canonical ABI error code`，与 Registry §4.1 host ABI 签名一致。

但 §5.5 又写：`所有 host function 返回 i32（0=成功，负数=错误码）`。这会让调用方误以为正数不是成功长度。

建议：统一为 `ret >= 0 = bytes_written`，其中 0 表示成功但无输出；负数为 ABI error code。

### P1 — Codegen 文档的输入输出映射过期

`codegen.md` 声明：

- `game_api.idl.yaml` 生成 `api-registry.md` §1-5, §11。
- `auth_api.idl.yaml` 生成 §6-9。
- `economy.idl.yaml` 生成 §10。

当前 Registry 实际结构中：

- §6 是 TickTrace Envelope，主要来自 game_api，同时包含 Auth Tick Trace Events。
- §7 Direction4 来自 game_api。
- §8 SwarmError 来自 game_api。
- §9 Certificate Envelope 来自 auth_api。
- §11 Deploy 来自 game_api。
- §12 Persistence 来自 game_api。
- §13 Security Columns 来自 auth_api。

因此 codegen 映射会误导维护者，以为部分章节不受对应 IDL 约束。

建议：更新 codegen 映射到当前章节结构，并让 `hermes codegen generate --check` 与附录中的 `scripts/generate_api_registry.py --check` 保持同一命令/同一输出路径。

### P2 — 文档陈旧标识与历史记录易误导

- `mcp-tools.md` 标题写“同步自 API Registry 0.4.0”，但 Registry 头部写 game_api 0.5.0。
- `api-registry.md` changelog 0.4.0 写 “MCP tools 总数为 56 active”，但当前同文档 §3 写 57，IDL 又显示 59/55 的不同口径。
- `api-registry.md` changelog 0.1.0 auth_api 写 “5 lifecycle tools, 6 cert/device MCP tools”，与当前 auth IDL 的 7 + 5 不一致。作为历史记录可以保留，但应避免被当作当前口径。

建议：历史记录中保留旧值可以接受，但当前摘要/标题/总览不得引用旧版本号；若 changelog 中的“当前”语气会误导，应改成历史描述。

## 正向一致项

- MCP 不暴露 `swarm_move`/`swarm_attack`/`swarm_build`/`swarm_spawn` 等直接游戏动作，`mcp-tools.md` 与 `design/interface.md` 一致。
- Combat/effect 动作通过 `CommandAction::Action { type, payload }` 派发到 ActionRegistry，`commands.md` 与 Registry 方向一致。
- `Direction4` 仅 N/S/E/W，8 方向为 Out-of-Scope RFC，`commands.md` 与 Registry 一致。
- SwarmError envelope 的核心设计在三份文档间基本一致。
- Host functions 列表 6 个，`design/interface.md` 与 Registry §4.1 名称一致。
- `codegen.md` 明确 IDL 为唯一机器源、Registry 全量生成、CI diff check，这一治理方向正确。

## 建议修复顺序

1. 先修 IDL/Registry 漂移：版本号、RejectionReason、MCP 工具计数必须回到单一事实源。
2. 明确 MCP 工具计数口径：区分 active、declared、RFC/feature-gated，并统一 Registry/mcp-tools/design。
3. 修正 `commands.md` 示例：补 `object_id`，`structure` 改 `structure_type`。
4. 清理未注册错误码：`SDKNotFound`、`UnsupportedLanguage`、`ConflictRetry`、`InvalidCommand` 不应作为 wire RejectionReason 出现。
5. 更新 `codegen.md` 章节映射和 CI 命令，确保与实际生成脚本/输出路径一致。
6. 统一 host function 返回说明为 `ret >= 0 = bytes_written`。

## 验证记录

使用 Python/YAML 对 IDL 做了辅助统计：

```text
game_api.idl.yaml api_version = 0.4.0
auth_api.idl.yaml api_version = 0.2.0
economy.idl.yaml api_version = 0.1.1
Game mcp_tools.tools = 59
Game non-rfc_status tools = 55
Auth tools = 12
Game indexed RejectionReason = 35
Auth RejectionReason = 12
Combined indexed RejectionReason = 47
```

本报告未修改被评审规范正文，仅新增审查产物。
