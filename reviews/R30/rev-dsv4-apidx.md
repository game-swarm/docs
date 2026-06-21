# R30 API/Developer Experience Review — rev-dsv4-apidx

> **Reviewer**: API/DX（类型系统完备性、错误处理覆盖、代码生成友好度）
> **Date**: 2026-06-21
> **Documents Reviewed**: design/README.md, design/interface.md, design/tech-choices.md, specs/reference/api-registry.md, specs/reference/commands.md, specs/reference/host-functions.md, specs/reference/mcp-tools.md, specs/reference/codegen.md, specs/reference/rhai-mod-abi.md, specs/core/02-command-validation.md, specs/core/09-snapshot-contract.md

---

## 1. Verdict

**CONDITIONAL_APPROVE**

API 设计整体质量很高——IDL 驱动的单事实源（Single Source of Truth）架构、固定点数类型注册表、47 canonical RejectionReason + debug_detail 分层、确定性序列化合同（canonical_json + Blake3）均达到业界前沿水平。发现 3 个 High-severity 问题和若干 Medium/Low 问题，均可在不改变核心架构的前提下修复。

---

## 2. 发现的问题

### H1 — `mcp-tools.md` 工具计数与 `api-registry.md` 不一致（High）

**文件**: `/tmp/swarm-review-R30/specs/reference/mcp-tools.md`（第 17–27 行）
**对比**: `/tmp/swarm-review-R30/specs/reference/api-registry.md` §3

`mcp-tools.md` 的工具总览表自称「同步自 API Registry 0.4.0」，但分组计数与 registry 不一致：

| 分组 | mcp-tools.md | api-registry.md |
|------|:-----------:|:--------------:|
| Onboarding | **10** | **11** (含 `swarm_get_objectives`) |
| Auth | **2** | **3** (含 `swarm_auth_check`) |
| Arena | **4** | **5** (含 `swarm_get_leaderboard`) |
| Game API 小计 | **56** | **57** |

API Registry §3 明确声明「共计 **57 个活跃工具** (game_api)」——但 `mcp-tools.md` 的概要表显示 56。此外 `design/interface.md` §4.1 也引用了「56 game tools + 11 auth tools」——与 registry 的 57 + 11 不一致。

**影响**: 开发者阅读 `mcp-tools.md` 时会认为只有 56 个工具，可能遗漏 `swarm_get_objectives`（0.4.0 新增的新手引导工具）。以哪个文档为准不明确——虽然 `api-registry.md` 是权威源，但 `mcp-tools.md` 是开发者更可能阅读的「使用指南」。

**修复建议**: `mcp-tools.md` 的工具总览表应从 `api-registry.md` 自动生成（或至少同步更新），并添加 CI 检查确保计数一致。手动更新 `design/interface.md` §4.1 的「56 → 57」。

---

### H2 — SwarmError JSON-RPC Envelope 中 `debug_detail` 与 `rejection_detail` 语义重叠（High）

**文件**: `/tmp/swarm-review-R30/specs/reference/api-registry.md` §8（第 672–692 行）
**对比**: 同文件 §2 的 `debug_detail` 定义（第 94–101 行）

§8 的 SwarmError JSON-RPC Envelope 同时包含两个字段：

```json
"data": {
    "rejection_reason": "...",
    "rejection_detail": "max 512 bytes (optional)",
    "debug_detail": "max 512 bytes — non-canonical contextual detail"
}
```

而 §2 定义了 `debug_detail` 字段（512 bytes, non-canonical, human-readable detail），但没有定义 `rejection_detail`。

**问题**: 
1. `rejection_detail` 和 `debug_detail` 均为 512 bytes optional 字符串，语义重叠。SDK 实现者不清楚哪个字段承载何种信息。
2. §2 的 `detail_level` 分级（competitive/practice/training）控制 `debug_detail` 的详细程度——但 `rejection_detail` 是否同样受分级控制？文档未说明。
3. §6.2 的 `auth_api` TickTrace events 中使用 `rejection_code`（非 `rejection_reason`）——术语不统一（`rejection_code` vs `rejection_reason` vs `code`）。

**影响**: SDK 代码生成器无法确定两个字段各自的用途，可能导致跨 SDK 行为不一致（一个 SDK 读取 `rejection_detail`，另一个读取 `debug_detail`）。

**修复建议**: 
- 合并 `rejection_detail` 和 `debug_detail` 为一个字段 `debug_detail`（与 §2 定义一致），删除 `rejection_detail`。
- 或者：明确区分两者：`rejection_detail` = machine-readable structured context（如 `{"required": 200, "available": 50}`），`debug_detail` = human-readable narrative（如 `"Not enough energy: need 200, have 50"`）。两者共存时需在 schema 中定义各自的 schema/semantics。
- 统一术语 `rejection_code` → `rejection_reason` 在 auth_api 事件中。

---

### H3 — `Leech` 和 `Fabricate`（⏳ Tier 2）在 IDL 中已注册但实现未完成——codegen 产生的 stub 暴露不完整 API surface（High）

**文件**: `/tmp/swarm-review-R30/specs/reference/api-registry.md` §1.3（第 80–83 行）
**对比**: `/tmp/swarm-review-R30/specs/core/02-command-validation.md` §3

`api-registry.md` §1 将 Leech (#20) 和 Fabricate (#21) 作为 CommandAction enum 的正式变体列出，标记 ⏳ Tier 2。这意味着：
1. `game_api.idl.yaml` 包含这两个 action type
2. Codegen 会生成对应的 SDK 类型和 stub
3. `commands.md` 在「特殊攻击」节中包含两者的完整 JSON schema、校验规则和属性

但是 §1.3 明确说两者「在引擎 `custom_action_def` 中已注册但标记 ⏳ Tier 2」——暗示引擎实现可能不完整或部分 gated。

**问题**: 从 DX 角度，SDK 暴露了这两个 action 的类型定义和使用示例，但运行时调用可能返回 unimplemented 错误或行为不完整。这构成 API surface 与实现的 gap——SDK 使用者无法从类型系统判断哪些功能实际可用。

此外，`02-command-validation.md` §3 为 Leech (#3.16 同类型多次命中表) 和 Fabricate 定义了完整的行为语义（累加、冷却、消耗），但在 §3.10–3.15 的逐指令校验矩阵中**没有** Leech 和 Fabricate 的独立校验表（Hack/Drain/Overload/Debilitate/Disrupt/Fortify 的校验表在 §3.10–3.15 完整覆盖，但 Leech 和 Fabricate 仅在 §10.4 末尾有简要属性表，无校验矩阵）。

**影响**: AI agent 通过 `swarm_sdk_fetch` 获取 SDK 后，可能基于类型定义生成调用 Leech/Fabricate 的代码，但运行时行为不可预测。违反「API surface = implemented surface」期望。

**修复建议**: 
- 方案 A（推荐）：若 Leech 和 Fabricate 是最终设计但实现未完成，在 IDL 中增加 `availability: "tier2_gated"` 标记，codegen 在 SDK 中生成 `@unimplemented` / `#[cfg(feature = "tier2")]` 标注。`swarm_sdk_fetch` 返回的 `type_definitions` 中按 Tier filter。
- 方案 B：若两者应完全可用，补齐 `02-command-validation.md` §3 中的独立逐指令校验矩阵（对标 Hack/Drain 等 6 个已覆盖的特殊攻击）。
- 至少：`02-command-validation.md` 补充 Leech 和 Fabricate 的校验矩阵（对标 §3.10–3.15）。

---

### M1 — `codegen.md` 手工维护的计数声明存在漂移风险（Medium）

**文件**: `/tmp/swarm-review-R30/specs/reference/codegen.md` 第 24–34 行

`codegen.md` 的「禁止手写的数值」段自述为手工维护：

> ⚠️ **本文档自身为手工维护**。本文档中的数值（CommandAction 数量、RejectionReason 数量等）需在 IDL 变更时手动更新。

其中硬编码了 `MAX_DRONES_PER_PLAYER (50)` 等值。

**问题**: 这与 IDL 单事实源原则相悖——`codegen.md` 是描述 codegen pipeline 的元文档，其中的数值声明应与 IDL 自动同步。当前方案依赖人工在 IDL 变更后记得更新 `codegen.md`，已有证据表明此依赖不可靠（mcp-tools.md 的计数已漂移）。

**影响**: CI `--check` 可能检测到 `api-registry.md` 与 IDL 一致，但无法检测 `codegen.md` 的计数漂移——因为 `codegen.md` 不在 `--check` 的检查范围内。建议的「CI 同时检查本文档中的计数声明与 `--check` 输出的一致性」目前仅是建议，未实现。

**修复建议**: 
- 将 `codegen.md` 中的计数声明（CommandAction 数量、MCP tool 数量等）也纳入 CI gate——从 IDL 计算实际值，与 `codegen.md` 中声明值对比。
- 或将 `codegen.md` 中所有硬编码的数值替换为对 `api-registry.md` 的交叉引用（「当前 CommandAction 数量见 [API Registry](api-registry.md) §1」），彻底消除手工维护的数值。

---

### M2 — Pipeline 级拒绝码（`InvalidJson`, `SchemaViolation`）的 wire representation 未定义（Medium）

**文件**: `/tmp/swarm-review-R30/specs/reference/api-registry.md` §2.1（第 110–118 行）

§2.1 定义了两个 Pipeline 级拒绝码，但注明「不计入 enum，统一前置处理」：

| 错误码 | 含义 |
|--------|------|
| `InvalidJson` | JSON parsing failed |
| `SchemaViolation` | Command schema does not conform to IDL |

**问题**: 
1. 这两个码不包含在 47 canonical RejectionReason enum 中。那么它们在 wire 上如何表示？是否使用与 canonical RejectionReason 相同的 SwarmError JSON-RPC envelope？
2. Pipeline 级验证在「任何指令进入校验管线之前」发生——如果整个 tick 输出是畸形 JSON，错误应该返回给谁？`tick()` 没有返回值通道（它是一个导出函数，输入 snapshot，输出 Command[]）。
3. `02-command-validation.md` §1.1 提到「校验失败的 tick 输出：不计入 refund（未进入指令管线），记录到 TickTrace 为 `TickValidationFailed`」——但 `TickValidationFailed` 不在 registry 的任何表中，也不在 `terminal_state` enum 中。

**影响**: SDK 实现者无法确定这些错误的序列化格式。AI agent 通过 MCP 获取 tick trace 时可能看到 `TickValidationFailed` 但无法将其映射到任何 documented error code。

**修复建议**: 
- 为 Pipeline 级错误定义统一的 wire representation（复用 SwarmError JSON-RPC envelope 或定义独立的 pipeline_error 格式）
- 将 `TickValidationFailed` 添加到 registry 中（作为 `terminal_state` 的新 variant 或独立的 trace event）
- 明确：MCP 中 `swarm_get_tick_trace` / `swarm_list_errors` 如何暴露 Pipeline 级失败

---

### M3 — `interface.md` §4.1 工具计数过期（Medium）

**文件**: `/tmp/swarm-review-R30/design/interface.md` 第 19 行

> **权威工具清单见 [API Registry](specs/reference/api-registry.md) §3** — 56 game tools + 11 auth tools.

但 api-registry.md §3 声明「共计 **57 个活跃工具** (game_api) + **11 个 Auth API 工具** (auth_api)」。

**影响**: 虽然 `interface.md` 声明了 api-registry.md 的权威性，但 56 这个数字本身已过期，开发者在概念性文档中看到过期数字会产生困惑。

**修复建议**: 更新 56 → 57，或改为「57 game tools + 11 auth tools（见 API Registry §3 权威计数）」。

---

### L1 — `commands.md` CommandIntent examples 中 `object_id` 类型不一致（Low）

**文件**: `/tmp/swarm-review-R30/specs/reference/commands.md` 第 17 行 vs JSON 示例

§CommandIntent 格式表定义 `sequence` 为 `u32`，但 JSON 示例中使用字符串作为 ID：
- `"object_id": "d1"`  (Move 示例)
- `"target_id": "s1"`  (Harvest 示例)

而 `api-registry.md` §1 声明所有 CommandAction 的 `object_id` 为 `EntityId`（隐含 numeric/u64 类型），`02-command-validation.md` §2.1 的示例使用 `"object_id": 1001`（数字）。

**影响**: 跨文档类型不一致会导致 SDK 实现者在 `string | number` 之间犹豫。AI agent 从 `commands.md` 学习 API 时可能生成字符串 ID 的 JSON，导致 SchemaViolation。

**修复建议**: 统一 `commands.md` 所有 JSON 示例中的 ID 为数字类型（与 `02-command-validation.md` 一致），并在 CommandIntent 格式表中明确 `object_id` 的类型（`u64` 或 `EntityId`）。

---

### L2 — 快照截断合同未定义「关键实体本身超过 256KB」的边界情况（Low）

**文件**: `/tmp/swarm-review-R30/specs/core/09-snapshot-contract.md` §1.4（第 82–92 行）

§1.4 定义了五类关键实体「绝不截断」（own drone、Room Controller、current target、all owned drones、entities attacking self）。但合同未说明当这些关键实体**本身的序列化体积**超过 256KB 时引擎的行为。

**问题**: 虽然在实际游戏中不太可能发生（单个 drone 的序列化远小于 256KB），但作为合同（contract）必须覆盖所有输入。API 消费者需要知道引擎在此极端情况下的行为——是返回 error？还是丢弃部分关键实体（违反 §1.4 的「绝不」）？还是 panic？

**影响**: 边缘情况未定义——对于 CI 和 replay verifier，这是不可测试的 gap。确定性合同要求所有路径有确定行为。

**修复建议**: 添加 fallback clause：当关键实体集合本身超过 256KB 时，引擎返回 `SnapshotOverBudget` terminal state（此行为已在 `terminal_state` enum (variant 3) 中定义），tick 被标记为 degraded。

---

### L3 — 文档间重复内容增加漂移风险（Low）

**文件**: 多个

以下内容在多个文档中重复出现，构成事实上的「手工分叉」：
- CommandAction 列表：`api-registry.md` §1（权威）、`commands.md` §指令列表（解释性）、`02-command-validation.md` §8（部分重复）
- Host function 签名：`api-registry.md` §4（权威）、`host-functions.md`（解释性）、`design/interface.md` §5.1（概念性）
- RejectionReason 列表：`api-registry.md` §2（权威）、`commands.md` §拒绝原因（引用）、`02-command-validation.md` §5（部分重复）

**影响**: 目前已有计数漂移（H1）证明此模式不可靠。每次 IDL 变更后，需要手动更新 3–4 个文件。codegen pipeline 只覆盖 `api-registry.md`，不覆盖解释性文档。

**修复建议**: 
- `commands.md` 和 `02-command-validation.md` 的 CommandAction 列表替换为对 `api-registry.md` §1 的交叉引用 + 解释性说明（不重复表格）
- `host-functions.md` 的签名表替换为对 `api-registry.md` §4 的交叉引用
- 或者：将 codegen 扩展到生成这些解释性文档中的结构表格

---

## 3. 亮点

### 3.1 固定点数类型注册表（§0 Fixed-Point Type Registry）
`api-registry.md` §0 将 `ResourceRate_i64`、`BasisPoints`、`milli_distance` 等 8 个类型统一注册，底层均为整数。彻底消除了 `f64` 的跨平台非确定性风险。所有数值计算（经济、伤害、距离）均有明确的 rounding 规则（floor/exact/additive）——这对跨语言 SDK 的正确实现至关重要。

### 3.2 IDL → Codegen 单事实源架构
三个 YAML IDL（`game_api`、`auth_api`、`economy`）作为唯一机器源，通过 `hermes codegen generate --check` 在 CI 中强制检测漂移。`api-registry.md` 的全量自动生成消除了手工维护权威文档的人为错误。SDK 类型定义直接由 IDL 生成——TypeScript 和 Rust 的 API 一致性由机器保证。

### 3.3 RejectionReason 分层 + debug_detail 设计（D2/B）
47 canonical wire enum + `debug_detail` 512-byte 非规范性上下文 + `detail_level` 三级控制（competitive/practice/training）——这是极佳的 API 设计决策。wire enum 保持稳定（不因新增上下文信息而膨胀），`debug_detail` 提供逐步丰富的调试信息，三级控制完美对应竞技公平性和开发者体验的平衡。`NotVisibleOrNotFound` 安全合并码防止通过错误码差异推断隐藏状态——安全与 DX 的兼顾。

### 3.4 确定性序列化合同（canonical_json + Blake3）
`canonical_json()` 规则（键排序、无空格、数值无尾零、字符串 NFC 归一化）为跨语言确定性序列化提供了精确规范。配合 Blake3 覆盖哈希和 PRNG（XOF 模式），整个系统的确定性数据流是可审计、可验证的。这对 CI replay verifier 和反作弊审计的意义不亚于游戏机制本身。

### 3.5 Host Function ABI 错误优先级
`api-registry.md` §4.5 定义了 9 级 ABI 错误优先级（ERR_MEMORY_BOUNDS → ERR_TIMEOUT），明确了当多个错误条件同时满足时的返回顺序。这在 WASM host function 设计中是罕见的，却是跨实现一致性所必需的。

### 3.6 Rhai RuleMod ABI 合同的完整性
`rhai-mod-abi.md` 覆盖了执行模型（事务性语义）、9 个 hook 的完整清单+调度顺序、8 个 query helper + 5 个 actions API、12 个 capability 白名单、6 级错误层次+自动降级、Semver 兼容策略、Ed25519 签名验证。这是模组开发者可以据此实现而不需要查阅引擎源码的合同——达到了真正的「ABI」标准。

### 3.7 Snapshot Truncation 确定性截断顺序
`09-snapshot-contract.md` §1.3 定义的 6 层距离桶（distance bucket）+ entity_id 字典序 + 从远到近的截断方向，保证了同一世界状态下截断结果的确定性。critical entity 不截断的设计确保了战术合法性的下限。竞技世界的 `tick degraded` 标记提供了透明性。

### 3.8 Capacity Admission Model
从静态容量承诺改为 measured admission（基于 p95/p99 指标动态调节 admitted players），配合 hysteresis（恢复需 30+ 连续 tick 低于 50% SLO）。这给运维者提供了可预测的过载行为，取代了早期设计中不可验证的「benchmark-gated」hard cap。

---

## 4. CrossCheck

以下问题在 API/DX 方向内无法完全裁决，需要跨方向验证：

### CX-1: `debug_detail` 与 `rejection_detail` 字段重复 → 建议 **Security** 方向检查
H2 发现 SwarmError envelope 中同时存在 `debug_detail` 和 `rejection_detail` 两个 512-byte 字段。Security 方向应确认：这两个字段在 `detail_level=competitive` 时分别承载什么信息？`rejection_detail` 是否会泄露 `debug_detail` 不应在 competitive 模式下暴露的状态？

### CX-2: Leech / Fabricate Tier 2 gating 机制 → 建议 **Engine** 方向检查
H3 发现 Leech 和 Fabricate 已在 IDL 和 CommandAction enum 中注册，但标记 ⏳ Tier 2。Engine 方向应确认：引擎在运行时收到 Leech/Fabricate 命令时的行为是什么？是返回 `UnknownAction` rejection？还是通过 feature flag 静默忽略？TickTrace 的 `world_action_manifest_hash` 是否已包含这两个 action？

### CX-3: `TickValidationFailed` 未在 registry 中注册 → 建议 **Security** 方向检查
M2 发现 Pipeline 级校验失败产生的 `TickValidationFailed` 不在 RejectionReason enum 或 `terminal_state` enum 中。Security 方向应确认：这个状态如何序列化到 TickTrace？replay verifier 如何正确处理包含 `TickValidationFailed` 的 tick？

### CX-4: 快照截断边界情况 → 建议 **Engine** 方向检查
L2 发现当关键实体集合本身超过 256KB 时，引擎行为未定义。Engine 方向应确认：当前实现是否已覆盖此情况（如返回 `SnapshotOverBudget`）？若未覆盖，需要定义明确行为（建议对齐 `terminal_state` variant 3）。