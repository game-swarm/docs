# R14 API/开发者体验评审报告 (DSV4)

**评审者**: rev-dsv4-apidx (DeepSeek V4 Pro — API/DX 方向)
**日期**: 2026-06-18
**阶段**: Phase 1 Clean-Slate 独立评审
**读取文档**: 7/7 (README.md, interface.md, tech-choices.md, commands.md, host-functions.md, mcp-tools.md, 02-command-validation.md)

---

## 1. Verdict

**CONDITIONAL_APPROVE**

设计整体方向正确——deferred command model、MCP 作为观察/管理界面、IDL 驱动 SDK 生成这三个支柱是坚实的。但存在 **2 个 Critical 级别的跨文档不一致**和 **3 个 High 级别的类型/错误处理空白**，必须在进入实现阶段前解决。这些不是"以后再说"的问题——它们直接影响 `game_api.idl` 的生成和双语言 SDK 的代码生成质量。

---

## 2. 发现的问题

### Critical

#### C1: Host Function 调用限制跨文档冲突 — interface.md vs host-functions.md

| 函数 | interface.md §5.5 | host-functions.md | 差异 |
|------|-------------------|-------------------|------|
| `host_get_objects_in_range` | 50/tick | **5/tick** | **10×** |

这是 **SDK 代码生成的基础数据**。TS/Rust SDK 需要在编译时/文档中告知开发者每个函数的 per-tick 配额。如果两个参考文档给出不同数字，SDK 绑定无法正确生成。必须在 IDL 中统一并锁定。

**建议**: 以 host-functions.md 的 5/tick 为准（interface.md 的 1000 total budget / 10 path_find / 5 objects_in_range 形成更合理的资源分配比例），同步更新 interface.md。可选方案：将配额从文档移到 `game_api.idl`，codegen 直接生成到 SDK 常量中。

#### C2: Command Enum 跨文档不一致 — interface.md vs commands.md vs 02-command-validation.md

三份文档列出的 Command 集合不同：

| Command | interface.md §5.4 | commands.md | 02-command-validation.md 校验矩阵 |
|---------|:---:|:---:|:---:|
| Move | ✅ | ✅ | ✅ |
| Harvest | ✅ | ✅ | ✅ |
| Build | ✅ | ✅ | ✅ |
| Attack | ✅ | ✅ | ✅ |
| RangedAttack | ✅ | ✅ | ✅ |
| Heal | ✅ | ✅ | ✅ |
| Spawn | ✅ | ✅ (as SpawnDrone) | ✅ (as Spawn) |
| Recycle | ✅ | ✅ | ✅ |
| Transfer | ✅ | ✅ | ✅ |
| Withdraw | ✅ | ✅ | ✅ |
| ClaimController | ✅ | ✅ | ✅ |
| Hack | ✅ | ✅ | ✅ |
| Drain | ✅ | ✅ | ✅ |
| Overload | ✅ | ✅ | ✅ |
| Debilitate | ✅ | ✅ | ✅ |
| Disrupt | ✅ | ✅ | ✅ |
| Fortify | ✅ | ✅ | ✅ |
| Leech | ✅ | ✅ | ❌ |
| Fabricate | ✅ | ✅ | ❌ |
| SendMessage | ✅ | ❌ | ❌ |
| TransferToGlobal | ❌ | ✅ | ❌ |
| TransferFromGlobal | ❌ | ✅ | ❌ |
| CreateMarketOrder | ❌ | ✅ | ❌ |
| BuyMarketOrder | ❌ | ✅ | ❌ |

问题：
1. **Spawn vs SpawnDrone**: 同一个指令在不同文档中用不同名称 — IDL 无法确定正确的 enum 变体名
2. **SendMessage**: 在 interface.md 的 Command enum 中列出但完全无校验规则 — WASM 可以提交此指令但引擎不知道如何处理？
3. **TransferToGlobal / TransferFromGlobal / CreateMarketOrder / BuyMarketOrder**: 只在 commands.md 中出现，不在 interface.md 的 Command enum 中 — 这些指令的 `replay_class` 是什么？是否需要 idempotency_key？
4. **Leech / Fabricate**: 标记为 ⏳ Tier 2 但在校验矩阵中没有任何条目 — 即使 Tier 2，也需要在 IDL 中定义 schema

**建议**: 以 `game_api.idl` 为单一事实来源。所有文档引用 IDL 生成的内容，不手写 Command 列表。立即将 SendMessage 和全局存储/市场指令统一纳入 Command enum。

### High

#### H1: 特殊攻击/经济指令的错误路径未完整定义

以下指令缺少正式的 RejectionReason 枚举覆盖：

| 指令 | 使用的拒绝码 | 在 45 变体 RejectionReason enum 中？ |
|------|------------|:---:|
| TransferToGlobal | GlobalStorageDisabled, TransferInProgress | ❌ (子系统拒绝，不在 enum) |
| TransferFromGlobal | GlobalStorageDisabled, TransferInProgress | ❌ |
| CreateMarketOrder | TerminalRequired | ❌ |
| BuyMarketOrder | OrderNotFound | ❌ |
| Leech | (无定义) | ❌ |
| Fabricate | (无定义) | ❌ |
| SendMessage | (完全无定义) | ❌ |

同时，02-command-validation.md 的校验矩阵中引用了大量**不在 45 变体 enum 中的拒绝码**：`NotStructure`, `TargetNotVisible`, `TargetOverloadCooldown`, `TargetFortifyCooldown`, `InsufficientEnergy`, `OnCooldown`, `MainActionQuotaExceeded`。

**建议**: 将所有拒绝码统一纳入 `RejectionReason` enum。子系统拒绝也应映射到 enum 变体（可以通过 `variant` + `subsystem_detail` 字段区分）。codegen 需要完整的 enum 来生成 TS `RejectionReason` 类型和 Rust 错误类型。

#### H2: Move 方向数量跨文档不一致

| 来源 | 允许的方向 |
|------|-----------|
| interface.md §5.4 Command enum | N/S/E/W/**NE/NW/SE/SW** (8方向) |
| 02-command-validation.md §3.1 校验矩阵 | **合法四方向邻居 (N/S/E/W)** (4方向) |
| host-functions.md pathfinding | NESW 顺时针 (4方向邻居序) |

这是 **游戏规则级别** 的不一致。对角线移动是否存在直接影响寻路策略、伤害计算和战术深度。必须统一。

**建议**: 如果设计意图是允许 8 方向移动，更新校验矩阵；如果是 4 方向，更新 interface.md 的 Command enum 描述。无论哪种选择，在 `game_api.idl` 中将 Direction 类型定义为严格枚举。

#### H3: IDL 格式未指定 — 代码生成管线缺少基础

设计文档多次引用 `game_api.idl` 作为 "core IDL" 和 SDK 代码生成的来源，但：

1. **IDL 格式未指定**: 是 protobuf？自定义 DSL？JSON Schema？OpenAPI fragment？
2. **生成目标未明确**: TypeScript SDK 生成 `.d.ts` 还是完整 `.ts` 源文件？Rust SDK 生成 `enum`/`struct` 还是 trait？
3. **版本化策略缺失**: IDL 有版本号吗？`swarm_sdk_fetch` 返回 `abi_version` 和 `min_engine_version`，但 IDL 本身的版本协商协议没有
4. **WorldSnapshot 二进制格式**: SDK 接收的是 "结构化数据（非纯文本 JSON）" — 这是什么格式？FlatBuffers？bincode？自定义二进制布局？这直接影响 SDK 的 `WorldSnapshot` 类型定义

**建议**: 在 `specs/reference/` 下新增 `idl-format.md`，明确：
- IDL 格式（推荐 protobuf — 多语言代码生成最成熟）
- 生成管线：IDL → codegen → sdk-ts/src/generated/ + sdk-rust/src/generated/
- 版本号约定（semver），以及 `abi_version` 与 IDL version 的映射关系
- WorldSnapshot 序列化格式（推荐 FlatBuffers — 零拷贝读取适合 WASM 场景）

### Medium

#### M1: 批级限制未进入管线图

02-command-validation.md §1 的管线图显示：`Schema 校验 → 反序列化 → 预校验 → 应用`，但 §6 定义的批级限制（500 cmd/tick, 1MB/批, u32 防回绕）不在此管线中。`parse_tick_output` 被描述为 "(大小/深度/Schema 校验)" 但不在管线图节点中。

**建议**: 管线图增加明确的 "批级校验" 步骤，包含所有 §6 限制。

#### M2: swarm_sdk_fetch 输出格式未细化

`swarm_sdk_fetch` 返回:
- `sdk_code: string` — 这是完整 SDK 源码还是工具函数子集？
- `type_definitions: string` — `.d.ts` 格式？JSON Schema？
- `examples: string[]` — 每个 example 是完整 `.ts` 文件还是代码片段？

对于 AI agent 的首次接入（onboarding profile 的核心工具），这些字段需要精确的类型定义。如果 `type_definitions` 是 `.d.ts`，AI agent 可以直接将其注入编译上下文。

**建议**: 在 mcp-tools.md 中为 `swarm_sdk_fetch` 提供完整的 request/response/error schema。

#### M3: 经济指令缺少 replay_class 分类

interface.md §4.1 的 MCP 工具表定义了 `replay_class`（read_replay_safe / idempotent_mutation / non_idempotent_mutation / admin_critical），但经济类指令（TransferToGlobal 等）不在该表中，没有 replay_class 定义。这对回放系统的正确性至关重要。

**建议**: 所有 MCP 工具都应在 interface.md §4.1 中列出，含 replay_class。

#### M4: 前端 WebSocket/REST API 未在 API 参考中定义

架构图显示网关通过 WebSocket + REST 提供服务，但 `specs/reference/` 中没有任何 WebSocket 消息格式或 REST endpoint 定义。人类玩家的 Web UI 如何获取游戏状态？MCP 是 AI 接口，但前端是人类接口——两者同样需要 API 文档。

**建议**: 新增 `specs/reference/websocket-api.md` 和 `specs/reference/rest-api.md`。至少定义 tick delta 推送的 WebSocket 消息格式和世界状态查询的 REST endpoint。

#### M5: Leech/Fabricate ⏳ Tier 2 — IDL 处理策略不明

Leech 和 Fabricate 标记为 ⏳ Tier 2，但在 interface.md 的 Command enum 中已经列出。如果 Tier 2 意味着"IDL 定义存在但引擎暂不实现"，那 SDK 生成的类型如何处理——是包含但标记 `#[cfg(feature = "tier2")]` 还是完全排除？

**建议**: 在 `game_api.idl` 中为每个 Command 变体加 `tier` annotation，codegen 根据 tier 生成 feature-gated 代码。

### Low

#### L1: Capability Profile 缺少只读/观察者 profile

MCP 的 capability profiles (onboarding/play/deploy/debug/admin) 覆盖了主要场景，但缺少一个 "observer" profile — 纯只读查看世界，不包含任何 deploy 或 mutation 工具。这对以下场景有价值：(a) AI agent 在提交 CSR 前评估"这个世界是否值得玩"；(b) 锦标赛观众。

#### L2: Tutorial 模式检测机制缺失

commands.md §10.3 提到 "Tutorial 前 500 tick 退还 100%"，但没有 API 可以查询当前是否处于 tutorial 模式或剩余 tutorial tick 数。SDK 代码无法利用此信息做决策。

**建议**: 在 `swarm_get_player_status` 或 `swarm_get_world_rules` 中暴露 tutorial 状态。

#### L3: Host Function 错误码命名空间冲突

| 错误码 | host_get_objects_in_range | host_path_find | host_get_world_config |
|--------|--------------------------|---------------|----------------------|
| -2 | range_too_large | dest_unreachable | key_not_found |
| -3 | buffer_overflow | node_limit_exceeded | — |

同一个数值 -2 在不同函数中含义完全不同。虽然函数上下文可以消歧，但 SDK wrapper 层需要额外的映射逻辑。

**建议**: 使用函数前缀的错误码（如 `-102` = PATHFIND_DEST_UNREACHABLE），或在 IDL 中按函数定义独立错误枚举。

---

## 3. 亮点

1. **Deferred Command Model 设计出色**: `tick(snapshot) → Command[]` 的架构干净利落，WASM 只读 host function + JSON 指令延迟提交的分层保证了安全性和确定性，同时保持了 SDK 的简单性。

2. **错误信封设计成熟**: JSON-RPC 2.0 格式 + `retry_allowed` + `idempotency_key` 的组合在 AI agent 场景下非常实用。`retry_allowed=false` 的明确标记避免了 agent 无意义重试。

3. **visibility-first 拒绝策略**: `NotVisibleOrNotFound` 统一返回的设计在安全和反作弊方面是正确的。admin trace vs player trace 的双轨审计也很周到。

4. **Capability Profiles 机制**: `swarm_get_schema(profile=...)` 返回最小工具集是优秀的 DX 设计——AI agent 可以按需请求权限，避免一次性暴露 42 个工具。

5. **Fuel Refund 反滥用设计**: 退还延至下一 tick + 连续高退还率 throttle + deploy-reset 规则构成了一套周全的反滥用体系。特别是禁止同 tick 内计算放大（anti-amplification）的设计非常精准。

6. **Recycle 与 lifespan 挂钩**: `refund_pct` 随剩余 lifespan 线性递减的设计精巧地解决了经济套利问题。

7. **特殊攻击状态机矩阵**: §3.16 的同 tick 优先级、多次命中规则、反制窗口矩阵极其详尽——这是 SDK 行为测试用例的直接来源。

8. **Overload 抗永久锁死证明**: §3.17 的数学证明是设计文档中的典范——将安全性声明形式化，可被外部验证。

---

## 4. CrossCheck — 需要跨方向检查

以下问题我怀疑存在但超出 API/DX 方向范围:

- **CX1**: `is_visible_to(target_player, attacker)` 的可见性计算是否 **确定性**？在回放时是否产生相同结果？如果可见性依赖随机种子或时序，会影响 replay determinism。
  → 建议 **Architect** 检查 visibility system 的 Determinism Contract 兼容性

- **CX2**: Ed25519 证书链的续签流程 (`swarm_renew_certificate`) — 证书即将过期时，AI agent 在 tick 执行期间发现 MCP 调用被拒（证书过期），此时已经进入 WASM tick 周期。证书续签是否需要中断当前 tick？MCP 认证失败是否计入 player trace？
  → 建议 **Security** 检查证书生命周期与 tick 周期的交互

- **CX3**: `TransferToGlobal`/`TransferFromGlobal` 的 N tick 延迟（"可被运输拦截"）——这个延迟在回放中是否确定性可重现？如果拦截行为依赖同 tick 内其他玩家的指令执行顺序，可能违反 Determinism Contract。
  → 建议 **Architect** 检查全局存储延迟模型的确定性

- **CX4**: Recycle 退还公式 `max(0.1, 0.5 × (remaining_lifespan / total_lifespan))` — 刚 spawn（SpawningGrace 期间）的 drone 是否可以立即 Recycle 获取 50% 退还？与 Spawn body_cost 的立即扣除（§3.8）组合，是否形成 "spawn → immediate recycle → 净赚 cost 差异" 的套利？
  → 建议 **Game Designer** 检查 spawning_grace + recycle 的经济边界

- **CX5**: `host_get_objects_in_range` 返回 "可见实体" — 但 `host_get_terrain` 是否受 fog-of-war 限制？如果 AI 可以通过 terrain query 探测未揭示区域的地形边界，会破坏 fog-of-war。
  → 建议 **Security** 检查 host function 的信息泄漏面

---

## 5. Type Gaps Summary

| Gap | 影响 |
|-----|------|
| `game_api.idl` 格式未指定 | SDK codegen 无法开始 |
| Command enum 跨文档不一致 | 生成的类型在所有 SDK 中不同 |
| 拒绝码 enum 不完整 | 错误处理代码无法穷举 |
| WorldSnapshot 二进制格式未定义 | SDK Reader 无法实现 |
| `swarm_sdk_fetch` 输出格式未细化 | onboarding 工具无法可靠使用 |
| WebSocket/REST 消息格式缺失 | 前端/第三方客户端无法开发 |
| Host function 错误码命名空间冲突 | SDK wrapper 需要额外映射 |

---

## 6. Error Handling Coverage

| 路径 | 覆盖率 | 说明 |
|------|:---:|------|
| WASM tick 输出校验 | 95% | 管线清晰，批级限制需进入流程图 |
| Host function 错误 | 90% | 错误码定义完整但命名空间冲突 |
| Command 逐条校验 | 85% | 15 core + 6 special 有完整矩阵；SendMessage/Leech/Fabricate 缺失 |
| 经济指令 (TransferToGlobal 等) | 40% | 拒绝码不在正式 enum 中 |
| MCP 工具错误 | 80% | JSON-RPC 信封好；部分工具缺少 error schema |
| Refund 路径 | 95% | 退还策略表 + 反滥用 + 时序设计均优秀 |
| 证书生命周期错误 | 70% | 工具列表完整但过期/续签时序未定义 |

---

## 7. SDK/IDL Action Items (优先级排序)

1. **[P0]** 统一并发布 `game_api.idl` 格式规范（protobuf 推荐）
2. **[P0]** 将所有 Command 变体收敛到 IDL — 消除跨文档 enum 不一致
3. **[P0]** 统一 host function 调用限制为单一来源（host-functions.md 为准）
4. **[P1]** 将 45+ RejectionReason 变体完整纳入 IDL，覆盖子系统拒绝码
5. **[P1]** 定义 WorldSnapshot 二进制格式（FlatBuffers 推荐）
6. **[P1]** 定义 WebSocket tick delta 推送 + REST endpoint 消息格式
7. **[P2]** 为 `swarm_sdk_fetch` 提供完整的 request/response/error schema
8. **[P2]** 为所有 MCP 工具补全 `replay_class` 分类
9. **[P3]** 新增 observer capability profile
10. **[P3]** 标准化 host function 错误码命名空间

---

*本报告仅基于 7 个指定文档，未读取 /data/swarm/ 下的代码仓库或其他设计文档。Phase 2 cross-review 时建议与其他方向评审员对比发现。*
