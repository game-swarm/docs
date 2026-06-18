# R23 API/DX Review — DeepSeek V4 Pro

> **Reviewer**: rev-dsv4-apidx (DeepSeek V4 Pro)
> **Direction**: API / Developer Experience
> **Date**: 2026-06-19
> **Documents reviewed**: design/README.md, design/interface.md, design/tech-choices.md, specs/reference/api-registry.md, specs/reference/codegen.md, specs/reference/commands.md, specs/reference/host-functions.md, specs/reference/mcp-tools.md, specs/core/02-command-validation.md, specs/core/09-snapshot-contract.md

---

## Verdict: CONDITIONAL_APPROVE

设计整体的 API 架构方向正确 — deferred command model、IDL-driven codegen、fixed-point type system、三级错误提示阶梯都是成熟的 DX 决策。但存在多个关键文档间的不一致和类型系统缺口，必须在进入实现阶段前解决。以下是详细发现。

---

## Strengths（亮点）

1. **Fixed-Point Type Registry** — 用 `BasisPoints`、`ResourceRate_i64`、`MilliUnits` 等定长整数类型全面替代 `f64`，保证了跨平台确定性。`api-registry.md` §0 的类型注册表是教科书级别的做法。

2. **47 Canonical RejectionReason + debug_detail 分离** — D2/B 设计决策将 wire enum 保持在 47 个稳定码，上下文信息放入 `debug_detail` 字段（512 bytes），在稳定性和调试信息丰富度之间取得了很好的平衡。

3. **三级 Safe Hint Ladder** — competitive/practice/training 三级错误详情梯度（09-snapshot-contract.md §4）是出色的竞技公平设计，防止通过错误消息推断隐藏状态。

4. **MCP Capability Profiles** — onboarding/play/deploy/debug/admin/arena 六个能力面（api-registry.md §3.4），AI agent 可按需渐进式接入，降低认知负担。

5. **IDL → Codegen → SDK 自动管线** — codegen.md 定义了 YAML IDL 作为唯一机器源、CI diff check 阻止手写分叉的完整链路。`swarm_sdk_fetch` 工具为 AI agent 提供自举入口（abi_version + min_engine_version），DX 设计周到。

6. **Snapshot Truncation Contract** — 确定性截断顺序（距离桶 → entity_id 字典序）、关键实体不可截断（09-snapshot-contract.md §1.3-1.4）、截断降级标记（tick_integrity = "degraded"）的规范非常完整。

7. **Host Function ABI 错误优先级表** — api-registry.md §4.5 的 9 级错误优先级（ERR_MEMORY_BOUNDS → ERR_TIMEOUT）确保内存安全最先检查，设计合理。

---

## Issues Found

### Critical (4)

**C1: `host_get_terrain` 签名跨文档不一致**

| 文档 | 签名 |
|------|------|
| design/interface.md §5.1 | `fn host_get_terrain(x: i32, y: i32) -> i32;` |
| specs/reference/host-functions.md | `i32 host_get_terrain(x: i32, y: i32) -> i32` |
| specs/reference/api-registry.md §4.1 | `(room_id: u32, out_ptr: i32, out_len: i32) -> i32` |

interface.md 和 host-functions.md 是 2-param 直接返回值模型；api-registry.md（IDL 权威源）是 3-param buffer-write 模型。**这两个签名语义完全不可互换** — 一个按坐标直接返回地形值，一个按 room_id + 输出缓冲区写入整个房间地形。这是阻断性不一致，会导致 WASM ABI 实现者选择错误签名。

**C2: `object_id` 在 CommandAction 参数声明中集体缺失**

api-registry.md §1.1 的 CommandAction 表中，所有需要 drone 作为主体的指令（Move/Harvest/Transfer/Withdraw/Build/Attack/RangedAttack/Heal/Recycle/ClaimController + 全部 8 个特殊攻击）的参数列 **均未声明 `object_id`**。但:
- commands.md 的所有 JSON 示例中都包含 `"object_id": "d1"` 或 `"object_id": 1001`
- 02-command-validation.md §6 的穷举校验表中以 `(entity_id)` 隐式引用所有权检查
- §2.1 的 CommandIntent 字段定义仅含 `sequence` + `action`，不含 `object_id`

`object_id` 到底是 CommandIntent 的顶层字段还是 action 内部的字段？它在 IDL 中的定义位置在哪里？**SDK 类型生成将因缺少 `object_id` 而导致所有 CommandIntent 构建者无法指定执行 drone**。

**C3: RejectionReason 计数跨文档矛盾**

| 文档 | 声称计数 | 
|------|---------|
| specs/reference/codegen.md "禁止手写的数值" | **79** |
| specs/reference/api-registry.md §2 header | **47** canonical (35 game + 12 auth) |

codegen.md 声称 "RejectionReason 数量 (当前 79)"，但手动计数 api-registry.md §2 的结果是 47（35 game codes 1-35 + 12 auth codes 1001-1012）。79 这个数字来源不明（是否包含已废弃的旧码？是否是某个 IDL YAML 的导出值？）。**CI diff check 如果对 codegen.md 的 "当前 79" 声明进行校验，会直接阻塞合并**。

**C4: `host_path_find` signature 跨文档不一致**

| 文档 | 参数数 | 签名 |
|------|:---:|------|
| specs/reference/api-registry.md §4.1 | **8** | `(from_x, from_y, to_x, to_y, opts_ptr, opts_len, out_ptr, out_len)` |
| specs/reference/host-functions.md | **6** | `(from_x, from_y, to_x, to_y, out_ptr, out_len)` |

api-registry.md（IDL 权威源）包含 `opts_ptr`/`opts_len` 两个选项参数，host-functions.md 的参考文档缺失这两个参数。如果 SDK 按照 host-functions.md 的 6-param 签名生成 binding，会与 IDL 产生的 ABI 不兼容。

---

### High (3)

**H1: RejectionReason refund 表有冲突行**

02-command-validation.md §7.1 退还规则表中，`InsufficientResource` 出现两次，且冲突:

| 行 | Refund | 理由 |
|----|:------:|------|
| 第1行 `InsufficientResource` | 退 50% fuel | 竞争导致——非玩家过错 |
| 第6行 `InsufficientResource` | 不退 | 玩家应计算资源 |

这是明显的数据错误。根据上下文推理: 第1行的 "竞争导致" 适用于共享资源竞争（如两个 drone 抢同一个 Source），应退 50%；第6行的 "玩家应计算资源" 适用于自身资源不足（如 drone carry 不足以 Transfer），应不退。但这需要被规范化为两个不同的错误码，或至少在同一表中明确区分。

**H2: MCP 工具计数内部矛盾**

api-registry.md §3 header 声明 "共计 54 个活跃工具 (game_api)"，但逐类统计:
- Onboarding: 10
- Auth: 2
- Play: 16
- Deploy: 7
- Debug: 8
- Admin: 6
- SDK: 1
- Arena: 4
- Resources: 2
**合计: 56**

mcp-tools.md 的概览表也写 "Game API 小计: 56"。api-registry.md 的 54 是陈旧数字 — 变更记录显示 0.4.0 新增了 10 个工具（Onboarding +2, Play +2, Deploy +1, Debug +1, Arena +4），但 header 文本未同步更新。

**H3: `TileBlocked` / `StillSpawning` / `MainActionQuotaExceeded` 未收入 canonical RejectionReason enum**

02-command-validation.md 的逐指令校验表和拒绝码表中使用了以下错误标识:

| 代码 | 出现位置 | canonical mapping |
|------|---------|-------------------|
| `TileBlocked` | Move 校验表、穷举表 | 无对应 canonical code |
| `StillSpawning` | Move 校验表 | 无对应 canonical code |
| `MainActionQuotaExceeded` | §5.1 拒绝码表 | 无对应 canonical code |
| `ExceedsRoomCapacity` | Spawn 校验表 | 无对应 canonical code |
| `InvalidDamageType` | Debilitate 校验表 | 无对应 canonical code |
| `AlreadyDebilitated(damage_type)` | Debilitate 校验表 | 无对应 canonical code |

这些代码要么应被纳入 canonical 47 码，要么应统一标记为 `(debug_detail)` 以明确它们不在 wire enum 中。当前状态下验证文档与 IDL 存在语义鸿沟。

---

### Medium (6)

**M1: 缺少 API 版本向后兼容策略**

codegen.md 定义了 IDL → 产物生成链，api-registry.md 有 changelog 和 `api_version` 跟踪。但**没有任何文档定义**:
- API 版本变更时旧 WASM 模块是否继续可运行？
- 破坏性变更的弃用窗口是多久？
- `api_version` bump 的 semver 语义是什么？
- SDK 的 `min_engine_version` 与引擎 `api_version` 的兼容性矩阵是什么？

这对开发者体验是重大缺口 — WASM 玩家需要知道他们部署的代码在引擎升级后是否仍然有效。

**M2: MCP 工具缺少类型化输出契约**

api-registry.md §3 的 MCP 工具表包含 `Input Schema` 和 `Output Schema` 列，但输出 schema 是自由文本描述（如 `{tick, entities, terrain, resources, truncated, omitted_count}`），**不是结构化的类型定义**。对比输入使用 JSON schema-like 表示法，输出缺乏:
- 字段类型声明
- 可选 vs 必填标记
- 嵌套对象的结构

这使得 SDK 代码生成无法从 IDL 自动产出 MCP 工具返回类型的 TypeScript/Rust 定义。

**M3: `Fabricate` 示例包含未声明的参数**

commands.md §Fabricate 的 JSON 示例:
```json
{"action": "Fabricate", "object_id": "d1", "target_id": "e5", "structure_type": "Extension", ...}
```

但 api-registry.md §1.3 中 Fabricate 的参数列仅为 `target_id: EntityId`。`structure_type` 未在 IDL 声明中出现。如果这是设计意图（Fabricate 可指定转化为何种建筑），需要进入 IDL；如果是错误，需要从示例中移除。

**M4: EntityId 类型表示不一致**

- commands.md 示例: `"object_id": "d1"` (字符串)
- 02-command-validation.md 示例: `"object_id": 1001` (数字)
- api-registry.md: 参数类型写作 `EntityId`，但未定义 `EntityId` 的 wire format 是 u64、string 还是其他

SDK 生成需要明确的 wire type。建议统一为 u64 并声明，字符串形式（如 "d1"）保留为文档人类可读标注。

**M5: Snapshot 输出契约与 MCP `swarm_get_snapshot` 输出未对齐**

09-snapshot-contract.md §1.2 定义截断快照的 JSON 包含 `truncated` + `omitted_categories` + `entities/resources/events`。但 api-registry.md §3.2 中 `swarm_get_snapshot` 的 output schema 是 `{tick, entities, terrain, resources, truncated, omitted_count}` — 使用单数 `omitted_count` 而非分类别的 `omitted_categories`。快照合同与 MCP 工具输出契约之间存在未解耦的字段不匹配。

**M6: WASM tick() 输出总大小限制存在双值**

02-command-validation.md §1.1 和 §6 批级校验:
- §1.1: "总字节数 ≤ 256 KB"
- §6 批级校验: "整批（tick 输出）≤ 1MB"

256KB vs 1MB 不一致。对于 SDK 开发者，这影响他们能返回多少条命令。

---

### Low (3)

**L1: `CommandAction` 计数 codegen.md 陈旧 (19 vs 实际 21)**

codegen.md "禁止手写的数值" 声称 "CommandAction 数量 (当前 19)"，但 api-registry.md §1 明确为 21（11 core + 2 global + 8 special）。19 是旧版本数字（变更记录显示 0.1.0 为 19 指令），此后增加了 Leech 和 Fabricate 两个 Tier 2 特殊攻击。

**L2: SDK 生成产物缺少 Optional/Result 类型规范**

codegen.md 和 tech-choices.md §10 确认了 TypeScript + Rust 双 SDK，但没有规定生成代码中的错误处理模式:
- Host function 返回 `i32` 错误码，SDK 是否封装为 `Result<T, HostError>`?
- MCP 工具调用的拒绝是否映射为 typed exception / Result?
- 可选字段使用 `Option<T>` 还是 `T | undefined`?

**L3: interface.md 的 Host Function 声明引用已过时**

interface.md §5.1 声明 "权威定义见 API Registry §4.1"，但其列出的函数签名与 api-registry.md §4.1 的权威签名不符（C1 和 C4 中已详述）。interface.md 应移除内联签名，仅保留到 api-registry.md 的指针引用。

---

## Type Gaps

| # | Gap | 影响 | 
|---|-----|------|
| TG1 | `object_id` 不在任何 CommandAction 的 IDL 参数声明中 | SDK 无法生成正确的 CommandIntent 构建器 |
| TG2 | MCP 工具 Output Schema 无结构化类型定义 | SDK 无法生成返回类型 |
| TG3 | `EntityId` 的 wire type 未定义（u64? string?） | Codegen 不知道该生成什么 primitive |
| TG4 | `Direction4` 的 wire format 未在 api-registry.md §7 外显式声明（是 int enum 还是 string?） | SDK 类型生成歧义 |
| TG5 | `DamageType` 枚举未在 api-registry.md 中注册 | 依赖它的命令（Debilitate, Leech）无法类型检查 |
| TG6 | Snapshot 的完整 schema 未在 api-registry.md 中定义 | SDK `WorldSnapshot` 类型无法从 IDL 自动生成 |

---

## Error Handling Coverage

### Covered (✓)
- 47 canonical RejectionReason 覆盖 Pipeline/Validation/MCP/Runtime/Auth 五层
- Host function 9 级 ABI 错误优先级
- WASM runtime 错误: FuelExhausted, TimeoutExceeded, SnapshotOverBudget, CommandBufferFull, InternalError
- MCP 层: RateLimited, InvalidCertificate, NotAuthorized
- Auth 层: 12 个独立 code (1001-1012)，含 token family revocation
- JSON-RPC 统一错误信封（§8）
- refund 策略: 竞争失败退 50%，玩家自身错误不退
- Anti-amplification: refund 仅作用于下一 tick，deploy-reset 清零规则
- Throttle: 连续 3 tick 高退还率 → budget 减半
- idempotency_key 用于 deploy 等操作的安全重试
- `retry_allowed` boolean 区分可重试 vs 不可重试错误

### Gaps (✗)
- `TileBlocked` 等 6 个验证文档中的错误码未映射到 canonical enum（见 H3）
- `InsufficientResource` 退还策略冲突（见 H1）— 无法从错误码确定退还行为
- 缺少 "MCP tool not found" / "Unknown tool" 错误码（当前仅有 game 层的 `UnknownAction`）
- SnapshotOverBudget 时 WASM 是否还能返回部分指令？当前文档未定义此边界行为
- MCP tool 请求的 schema 验证失败错误（输入不符合 Input Schema）没有 canonical code — 是返回 `SchemaViolation` 还是用 MCP 协议级错误？
- Rate limit 超额后的 retry-after header / 提示未在 API 契约中定义

---

## CrossCheck — 需要跨方向检查

以下问题超出 API/DX 方向范围，但我在审查过程中发现可疑，建议指定方向的评审员验证:

- **CX1**: `object_id` 缺失同时影响 SDK codegen（API/DX）和引擎校验管线（Architect）— 这到底是 CommandIntent envelope 字段还是 action 内部字段？如果 action 内部不声明 `object_id`，引擎如何知道哪个 drone 执行该指令？→ **建议 Architect 检查** CommandIntent → RawCommand 转换中 `object_id` 的来源与注入时点。

- **CX2**: `InsufficientResource` 退还策略冲突中的"竞争场景"需要定义什么是竞争 — 多个 drone 抢同一 Source 是竞争，但 drone carry 不足算不算竞争？→ **建议 Game Designer 检查** 游戏机制层对 "玩家自身错误 vs 竞争导致" 的边界定义。

- **CX3**: `detail_level` 三级系统 (competitive/practice/training) 在 competitive 模式下的最小信息策略，是否可能通过定时攻击 (timing side-channel) 泄露信息（如：不同拒绝路径的执行时间不同）？→ **建议 Security 检查** competitive 模式下的常量时间错误返回。

- **CX4**: `host_get_terrain` 的两个签名中，哪个是设计意图？如果是 `(room_id, out_ptr, out_len)` 模型，那 terrain 数据的内部格式是什么 — 逐 tile 编码还是 run-length？这影响快照体积预算。→ **建议 Architect 检查** terrain 在快照中的序列化格式。

- **CX5**: Snapshot 合同 (§09-snapshot-contract.md) 中 `truncated` 和 `omitted_categories` 的结构，与 MCP `swarm_get_snapshot` 输出中的 `omitted_count`（单数），是设计上的简化还是不一致？→ **建议 Architect 检查** 快照合同的输出 schema 与 MCP 工具 schema 的对齐。

---

## Summary

| 维度 | 评价 |
|------|------|
| Type System 完整性 | ⚠️ 强项（fixed-point registry）但存在关键缺口（object_id 缺失、EntityId/DamageType wire type 未定义）|
| 错误处理完整性 | ⚠️ 覆盖面广（47 codes + 9 级 ABI 优先级）但存在映射缺口和冲突 |
| SDK 生成就绪度 | ⚠️ IDL 管线方向正确但输出类型未结构化、object_id 缺口会阻断代码生成 |
| 版本兼容性 | ❌ 完全未定义 — 无 deprecation policy、无 semver 语义、无 WASM 兼容性矩阵 |
| 跨文档一致性 | ❌ 存在 4 个关键签名/计数不一致，CI 校验会直接失败 |

**Bottom line**: 设计方向正确，但类型系统的关键缺口（C2 object_id）和文档间签名不一致（C1 host_get_terrain, C4 host_path_find）必须在进入实现前修复。建议完成修复后重新触发 API/DX 方向的快速复核。
