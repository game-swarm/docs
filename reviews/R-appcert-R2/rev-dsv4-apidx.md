# R-appcert-R2 apidx 评审报告

**评审员**: rev-dsv4-apidx (DeepSeek V4 Pro)  
**评审视角**: API / 开发者体验  
**评审日期**: 2026-06-18  
**评审范围**: MCP 工具接口完备性、SDK 可用性、类型系统、错误处理、Canonical 序列化、AI agent 端到端路径  
**已读文档**: 25/25 (DESIGN/README, auth, engine, gameplay, interface, modes, tech-choices, 01-tick-protocol, 02-command-validation, 04-wasm-sandbox, 07-world-rules, 03-mcp-security, 05-visibility, 09-command-source, CVE-SLA, 06-feedback-loop, 08-api-idl, commands, host-functions, mcp-tools, 12-gateway-protocol, T2-incremental-snapshot, T3-shard-protocol, GETTING-STARTED, RUNBOOK)

---

## Verdict: REQUEST_MAJOR_CHANGES

本设计在 MCP 工具面、类型系统、Canonical 序列化和 AI agent 端到端路径上存在 2 个 Critical 和 7 个 High 严重度问题，必须修正后重新评审。整体 API 设计方向正确——deferred command model、单一 IDL 生成所有绑定、MCP/Web UI 同级架构是杰出的设计决策——但类型一致性和接口完备性尚未达到可冻结状态。

---

## Strengths（亮点）

1. **Deferred Command Model 设计**: WASM `tick(snapshot) → CommandIntent[]` 的延迟指令模型 + 服务端 Source Gate 注入身份信息，从架构层面杜绝了客户端伪造 player_id/tick/source 的可能性。

2. **单一 IDL 真相源**: `game_api.idl` 生成 Rust/TS/MCP/Docs/Test 五路产物的架构是教科书级设计。`additionalProperties: false` 的 Schema 不可扩展性规则防止了字段注入攻击和实现分叉。

3. **Canonical Request Signature (SWARM-REQUEST-V1)**: 签名 payload 的确定性序列化规范（LF 分隔、固定字段顺序、domain separator、整数十进制编码、空 body_hash = Blake3("")）设计严谨，完整覆盖 MCP/deploy/admin 所有敏感操作。

4. **Oracle 防线闭合**: `omitted_count` 分桶脱敏、特殊攻击三种结果等价合同、`NotVisibleOrNotFound` 统一不可见目标拒绝码——这套防信息泄露体系在同类设计中少见。

5. **动态 SDK 生成**: 引擎从 `world.toml` + `mods/` 动态生成 world-specific SDK 的架构，配合 `mod_manifest_hash` 校验，保证了不同世界的类型安全和模组隔离。

6. **代码签名 vs 认证证书隔离**: `CodeSigningCertificate` 与 `ClientAuthCertificate` 用途分离，配合 per-slot `version_counter` 防重放，是成熟的应用层安全设计。

---

## Findings

### [C1] Critical — PlayerId 类型不一致 (u32 vs u64)

**涉及文件**:
- `08-api-idl.md` §2: `PlayerId: u32`
- `auth.md` §7.1: `player_id = blake3(...) → 取低 64 bits → u64`
- `02-command-validation.md` §2.2: RawCommand `player_id: u32`
- `09-command-source.md` §3.2: DeployPayload `player_id: 42`（无类型标注）
- `auth.md` §3: `issue_certificate_bundle(player_id: u64, ...)`

**影响**: 若 IDL 代码生成器按 u32 生成所有 binding，而 Auth Service 以 u64 签发证书，则在 player_id > 2^32 时出现截断——IDL 生成的 SDK 类型与运行时证书中的 player_id 不兼容。所有消费 player_id 的接口（CommandIntent envelope、MCP tool params、SDK type）必须统一。

**建议**: 统一为 `u64`。理由：(a) Blake3 输出空间充足，低 64 bits 可覆盖 10^12 玩家无碰撞；(b) u64 允许未来联邦身份扩展 namespace 前缀，无需迁移。

---

### [C2] Critical — `swarm_sdk_fetch` MCP 工具缺失，AI agent 端到端路径断裂

**涉及文件**:
- `08-api-idl.md` §6.1: 明确列出 `MCP: swarm_sdk_fetch(world_id)` 为 SDK 下载端点
- `mcp-tools.md`: 未列出此工具
- `interface.md` §4.1: MCP 工具分类表中无此工具
- `03-mcp-security.md` §4: 开发辅助工具表中无此工具

**影响**: AI agent 通过 MCP 注册、认证后，无法获取与目标世界匹配的 SDK。没有 SDK，AI agent 无法知道该世界的可用 CommandAction、body part 枚举值、资源类型、damage type，无法生成正确的 WASM 代码。这是 AI agent 端到端路径的断裂。

**建议**: 在 mcp-tools.md 和 interface.md 中增加 `swarm_sdk_fetch(world_id: string) → SDKArtifact`，scope 为 `swarm:read`。同时补充其限流策略（建议 1/min）。

---

### [H1] High — GETTING-STARTED.md 中的字段名与实际 IDL 不一致

**涉及文件**:
- `GETTING-STARTED.md` §3: 使用 `seq: 1` 字段名
- `02-command-validation.md` §2.1 / `08-api-idl.md`: 正式规格使用 `sequence: u32`
- `GETTING-STARTED.md` §3: 使用 `action: "SpawnDrone"` 
- `08-api-idl.md` §2: 正式 IDL 定义为 `Spawn`（`commands.Spawn.params`）

**影响**: 新玩家按照 GETTING-STARTED.md 编写的代码会产生 schema 校验失败——`seq` 字段被 `additionalProperties: false` 拒绝，`SpawnDrone` 不存在于 CommandAction enum。这会使 5 分钟教程变成 5 分钟报错。

**建议**: 将 `seq` 改为 `sequence`，`SpawnDrone` 改为 `Spawn`，并在 CI 中增加「starter bot 代码 vs IDL schema」的交叉校验。

---

### [H2] High — Move Direction 示例值超出枚举定义

**涉及文件**:
- `commands.md` §Move: 示例 `"direction": "TopRight"`
- `08-api-idl.md` §2: `Direction: [North, South, East, West]` — 仅四方向

**影响**: IDL 定义的 Direction 枚举仅含四个正交方向 (N/S/E/W)，但 reference 文档中的示例使用 `TopRight`（对角线）。若 SDK 按枚举生成类型，`TopRight` 会导致编译错误或运行时校验失败。需明确：(a) 是否支持对角线移动；(b) 若支持，Direction 枚举需扩展到 8 值。

**建议**: 确认移动方向设计意图。若仅四方向，修正 commands.md 示例为 `"North"`。若支持八方向，扩展 Direction enum 为 `[North, South, East, West, NorthEast, NorthWest, SouthEast, SouthWest]`，并同步更新 WASM SDK 的移动逻辑。

---

### [H3] High — `swarm_get_player_status` 被引用但未定义

**涉及文件**:
- `05-visibility.md` §6.1: "target 视角: 可见: 自身 fuel 变化（MCP `get_player_status`）"

**影响**: 可见性 spec 引用了 `get_player_status` 作为 target 获知自身 fuel 变化的 MCP 工具，但该工具在 mcp-tools.md、interface.md、03-mcp-security.md 中均不存在。若不提供此工具，玩家无法通过 MCP 获知自身 fuel budget 状态（这在被 Overload 攻击后是关键的决策信息）。

**建议**: 定义 `swarm_get_player_status` MCP 工具，返回 `{player_id, fuel_budget, fuel_max, resources, active_drones, ...}`，scope `swarm:read`，仅返回自身数据。

---

### [H4] High — MCP 限流单位不一致

**涉及文件**:
- `mcp-tools.md` Rate Limiter 表: `MCP_Query: 100 tokens/s`
- `03-mcp-security.md` §5.1: "读类工具总计: 50/tick", "调试工具总计: 30/tick", "开发辅助工具: 20/tick"

**影响**: 两个文档使用不同的计量单位（tokens/s vs calls/tick）。当 tick_interval = 3s 时，50/tick ≈ 16.7/s，远低于 100/s。这意味着按 mcp-tools.md 的 100/s 可实现 300/tick 的调用量，而 03-mcp-security.md 只允许 50+30+20=100/tick。AI agent 在不同文档指导下会产生冲突的限流预期。

**建议**: 统一以 `/tick` 为单位表述所有 MCP 限流。Gateway 的 12-source rate limiter 表也应改用 `/tick`。若需同时保留 `/s` 表述（用于运维告警），应注明 `(per-second equivalent at 3s tick) = value/3`。

---

### [H5] High — `NotVisibleOrNotFound` 与 `PlayerNotFound` 命名不一致

**涉及文件**:
- `05-visibility.md` §10.4: 所有特殊攻击不可见目标统一返回 `NotVisibleOrNotFound`
- `commands.md` RejectionReason 表: 列出 `PlayerNotFound`
- `02-command-validation.md` §3.12: Overload 校验表列出 `PlayerNotFound`

**影响**: `NotVisibleOrNotFound` 是 Oracle 防线的核心设计——攻击者无法区分「目标不存在」与「目标不可见」。但 commands.md 和 02-command-validation.md 仍引用旧名 `PlayerNotFound`。若引擎实现按旧名返回，oracle 防线失效；若按新名返回但 IDL 未更新，SDK 生成的 RejectionReason enum 缺少此变体。

**建议**: 全局替换 `PlayerNotFound` → `NotVisibleOrNotFound`。同时确认 IDL 中 `RejectionReason` enum 已包含 `NotVisibleOrNotFound` 变体，并检查是否存在 `TargetNotVisible` 的遗留引用（在 commands.md §Rejections 中作为管线级拒绝提及，需统一）。

---

### [H6] High — CommandIntent 缺少 Canonical JSON 序列化规范

**涉及文件**: `08-api-idl.md`, `02-command-validation.md`, `09-command-source.md`

**现状**: DeployPayload 和 SWARM-REQUEST-V1 签名 payload 有精确的 canonical 序列化规范（字段顺序、换行符、整数编码）。但 WASM `tick()` 输出的 CommandIntent JSON 没有对应的 canonical 序列化规范。

**影响**: 不同 SDK（Rust/TS）的 JSON 序列化器可能产生不同的 JSON 表示——字段顺序、数字格式（`1` vs `1.0`）、Unicode 转义策略。虽然 CommandIntent 当前不参与哈希计算（module_hash = Blake3(WASM bytes)），但在以下场景会成为问题：(a) 未来若对 CommandIntent 做确定性排序或去重需要稳定序列化；(b) TickTrace 中的命令记录需要 deterministic bytes 以保证回放时可精确重建。

**建议**: 在 08-api-idl.md 中增加 §2.1 "CommandIntent Canonical Serialization"，规范：(a) JSON key 按字母序排列；(b) 整数不使用小数点；(c) 字符串不使用 `\u` 转义（直接用 UTF-8）；(d) 无缩进、无尾随空格；(e) `\n` 结尾。或采用更轻量的方案：声明 CommandIntent 使用 [RFC 8785](https://tools.ietf.org/html/rfc8785) JSON Canonicalization Scheme (JCS)。

---

### [H7] High — MCP 工具响应 Schema 未定义

**涉及文件**: `mcp-tools.md`, `interface.md`, `03-mcp-security.md`, `auth.md` §10

**现状**: 大部分 MCP 工具的输入参数有非正式描述，但输出（返回值结构）没有定义 JSON Schema。例如：
- `swarm_deploy` 返回 `{module_id, status, deployed_at}` —— 仅有示例，无 schema
- `swarm_get_snapshot` 返回体仅在 03-mcp-security.md §6.1 中有示例，无正式 schema
- Auth 工具（§10）有请求体定义，但大多数缺少响应体定义

**影响**: AI agent 依赖 function calling 的 `parameters` / `returns` schema 来生成正确的调用代码和解析返回值。没有 response schema，agent 只能靠文档描述猜测返回结构，增加调用失败率。这对 AI 首次体验尤其致命——首次部署后无法可靠解析 `swarm_deploy` 返回的 `deploy_id`。

**建议**: (a) 所有 MCP 工具必须在 IDL 或 mcp-tools.md 中定义输入+输出 JSON Schema；(b) 代码生成器（08-api-idl.md §3）的 MCP 目标产物应包含完整的 tool schema JSON（含 inputSchema 和 outputSchema），可直接用于 MCP server 的 `tools/list` 响应。

---

### [M1] Medium — SDK 缺少特殊攻击状态类型定义

**涉及文件**: 
- `02-command-validation.md` §3.10-3.15: 特殊攻击定义 HackControlLock, Debilitated, Fortified 等状态
- `08-api-idl.md` §2: BodyPart/DamageType 有枚举但缺少状态类型

**影响**: WASM 代码通过 `tick(snapshot)` 接收实体数据，snapshot 中应包含 drone 的当前状态标记（如 `hacked: {by: player_id, remaining: 5}`）。但 IDL 中未定义这些状态的类型结构。SDK 侧开发者只能通过原始 JSON 字段访问，失去了类型安全。

**建议**: 在 IDL 中增加 `StatusEffect` 类型层次：
```yaml
StatusEffect:
  HackControlLock: { stage: u8, by_player: PlayerId }
  Debilitated: { damage_type: DamageType, remaining: u32 }
  Fortified: { remaining: u32 }
  Overloaded: { fuel_drained: u32 }
  Drained: {}
```

---

### [M2] Medium — ABI 版本缺少向后兼容策略

**涉及文件**: `08-api-idl.md`: 定义了 `abi_version: 1`，但未说明迁移策略

**现状**: 当 ABI 版本递增时（如新增 host function 签名变更），所有已部署 WASM 需要重新编译（见 §6.4 版本兼容性表）。但文档未规定：
- 旧 ABI 版本的 WASM 模块是否有 grace period
- 引擎是否支持同时运行多个 ABI 版本的模块（兼容窗口）
- ABI 版本变更的通信流程（提前多久通知玩家）

**建议**: 在 §6.4 中增加：(a) ABI 升级前至少 30 天公告期；(b) 引擎需支持上一个 ABI 版本的模块继续运行至少 90 天（兼容窗口）；(c) 兼容窗口结束后，旧 ABI 模块 tick 返回空指令 + 审计日志告警。

---

### [M3] Medium — `additionalProperties: false` 与扩展指令的交互未明确

**涉及文件**: 
- `08-api-idl.md` §1: Schema 默认 `additionalProperties: false`
- `08-api-idl.md` §5: 自定义 action 通过 `[[custom_actions]]` 注册

**影响**: Core IDL 定义的 CommandIntent schema 设置 `additionalProperties: false`。但自定义 action（如 Leech, Fabricate）的参数结构与内置指令不同——它们可能需要额外字段。若 schema 严格拒绝额外字段，自定义 action 的 CommandIntent 将被拒绝。

**建议**: 明确 Schema 分层：(a) CommandIntent envelope 的 `additionalProperties: false` 仅作用于顶层 `{sequence, action}`；(b) `action` 内部根据 `action.type` 使用 oneOf 分发到对应子 schema；(c) 自定义 action 的子 schema 由 World Action Manifest 动态注入。

---

### [L1] Low — IDL SDK fetch 端点未列入 mcp-tools.md 索引

同 C2 的文档索引层面。若 `swarm_sdk_fetch` 已计划实现，应在 mcp-tools.md 的"学习"分类下提前列出（标注 ⏳）。

---

### [L2] Low — Auth 工具与 scope 映射不完整

**涉及文件**:
- `auth.md` §10.1: 列出 18 个 auth MCP 工具
- `03-mcp-security.md` §3.2: 仅定义了 4 个 scope (`swarm:deploy`, `swarm:read`, `swarm:debug`, `swarm:admin`)

**影响**: Auth 工具如 `swarm_delete_account`, `swarm_bind_email`, `swarm_update_profile` 不明确映射到哪个 scope。若它们全部归入 `swarm:read`（过于宽泛），攻击者仅需 `swarm:read` scope 即可删除账号。

**建议**: 增加 `swarm:account` scope 覆盖账号管理操作（delete/restore/update_profile/bind_email/change_password），与 `swarm:read` 分离。

---

### [L3] Low — host function `host_get_objects_in_range` 的 visibility filter 文档交叉引用碎裂

**涉及文件**:
- `host-functions.md`: 未提及 `host_get_objects_in_range` 返回结果经 `is_visible_to` 过滤
- `04-wasm-sandbox.md` §3.2: 明确标注"仅返回 is_visible_to(caller) 为 true 的实体"
- `05-visibility.md` §3.0: 确认 host function 经 visibility 过滤

**影响**: 开发者只读 host-functions.md 会认为该函数返回范围内所有实体（无可见性限制），产生安全预期偏差。虽然实际实现会过滤，但文档的读者（SDK 开发者、AI agent）会写出错误假设的代码。

**建议**: 在 host-functions.md 的 `host_get_objects_in_range` 描述中增加可见性过滤的说明和交叉引用。

---

## Consistency Gaps（跨文档一致性缺口）

| # | 不一致项 | 文档 A | 文档 B | 严重度 |
|---|---------|--------|--------|:--:|
| 1 | PlayerId: u32 vs u64 | 08-api-idl.md, 02-command-validation.md | auth.md §7.1, auth.md §3 | 🔴 Critical |
| 2 | SDK fetch MCP 工具 | 08-api-idl.md §6.1 列出 | mcp-tools.md, interface.md 缺失 | 🔴 Critical |
| 3 | Command 字段名 `seq` vs `sequence` | GETTING-STARTED.md | 02-command-validation.md, 08-api-idl.md | 🟠 High |
| 4 | 移动方向 `TopRight` vs 四方向枚举 | commands.md | 08-api-idl.md | 🟠 High |
| 5 | MCP 限流单位 tokens/s vs calls/tick | mcp-tools.md | 03-mcp-security.md | 🟠 High |
| 6 | 拒绝码 `PlayerNotFound` vs `NotVisibleOrNotFound` | commands.md, 02-command-validation.md | 05-visibility.md | 🟠 High |
| 7 | `swarm_get_player_status` 引用 | 05-visibility.md | mcp-tools.md 未定义 | 🟠 High |
| 8 | Spawn 指令名 `SpawnDrone` vs `Spawn` | GETTING-STARTED.md | 08-api-idl.md | 🟠 High |
| 9 | Controller 类型字段不一致 | engine.md `Controller` struct 含 `repair_capacity`, `repair_range`, `repair_per_drone` | 01-tick-protocol.md 的 `RoomController` 未定义这些字段 | 🟡 Medium |
| 10 | Position 类型 | engine.md: `struct Position { x: i32, y: i32, room: RoomId }` | 01-tick-protocol.md: `RoomPosition`, `GridCoord` 两个分离类型 | 🟡 Medium |

---

## Algorithmic Risks（算法风险）

1. **PlayerId 碰撞风险低但未量化**: `blake3("local:" + username) → 低 64 bits`。对于 10^6 用户，生日碰撞概率约 2.7×10^-8（文档已计算），可接受。但联邦身份 `blake3("federated:" + world_id + ":" + original_player_id)` 的碰撞概率未计算——若跨世界联邦达到 10^4 世界 × 10^4 用户，碰撞率需要重新评估。

2. **WASM snapshot 构建中 `host_get_objects_in_range` 与 snapshot 的一致性**: 文档保证两者使用同一 `is_visible_to` 过滤函数和同一快照数据。但若 `host_get_objects_in_range` 在 WASM 执行中途被调用、且快照构建时的可见性缓存与调用时的「当前状态」存在时差（虽然快照只读），需确认实现中缓存键 `(tick, player_id)` 确实在 COLLECT 开始时已固化。当前设计正确，但实现时易出错——建议在 01-tick-protocol.md §2.3 增加明确的固化时点声明。

---

## Summary

| 严重度 | 数量 | 关键项 |
|:--|:--:|------|
| Critical | 2 | PlayerId 类型不一致 (C1), swarm_sdk_fetch 缺失 (C2) |
| High | 7 | 字段名不一致 (H1), 方向枚举 (H2), player_status 缺失 (H3), 限流单位 (H4), 拒绝码命名 (H5), Canonical JSON 缺失 (H6), MCP response schema (H7) |
| Medium | 3 | SDK 状态类型 (M1), ABI 兼容策略 (M2), Schema 扩展性 (M3) |
| Low | 3 | 文档索引 (L1), scope 映射 (L2), visibility filter 文档 (L3) |

**裁决理由**: C1（PlayerId 类型不一致）是 IDL 代码生成的根基——在修复前所有 SDK/类型系统无法信任。C2（SDK fetch 缺失）使 AI agent 的端到端路径不完整。两个 Critical 问题单独即可构成 REQUEST_MAJOR_CHANGES。7 个 High 问题（跨文档不一致）使新开发者和 AI agent 在遵循文档时必然遇到错误。修复 C1-C2 + H1-H7 后可升级为 CONDITIONAL_APPROVE，修复 M1-M3 后可达 APPROVE。
