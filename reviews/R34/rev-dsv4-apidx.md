# R34 Closure Verification — API/DX (DeepSeek V4 Pro)

## Verdict

**PARTIALLY_CLOSED** — 4 项已闭合/修复，4 项未修复，3 项部分修复，3 项 OK。D3 (Overload PlayerId)、D7 (special-attack-table.md)、E-H2 (MilliUnits type registry)、E-H5 (Recycle spawn proximity) 仍是开放问题。B6 MainActionQuotaExceeded 未注册为 canonical code。B1 工具计数 header 仍不一致。

---

## 逐项验证

### B1: IDL→Registry 链

#### B1a — host_get_random 注册缺口 (R33 B1 Critical)

| 数据源 | host_get_random 存在? | 函数总数 |
|--------|:---:|:---:|
| api-registry.md §4.1 L389-416 | ❌ | 5 |
| game_api.idl.yaml §4 L1435 | ❌ | 5 |
| host-functions.md L11-18 | ❌ | 5 |
| 04-wasm-sandbox.md §3.2 L207-215 | ❌ | 5 |

**状态**: ✅ **FIXED**。R33 B1 修复选项 (b) 已实施——host_get_random 从 api-registry.md 中移除。现在 4 个源一致显示 5 个 host function，无 host_get_random。所有相关文档（api-registry.md §4.1、host-functions.md、04-wasm-sandbox.md §4.1 容量表）均一致。

#### B1b — 工具计数一致性 (R33 B2 Critical)

| 数据源 | header 声明 | 实际列表计数 | 状态 |
|--------|:---:|:---:|------|
| **game_api.idl.yaml** L476 `total_tools` | 56 | 56 | ✅ FIXED (R33 时 57→58, 现 56→56) |
| **api-registry.md** L209 header | 54 | 56 | ❌ 仍差 2 |
| **game_api.idl.yaml** Play 注释 header L678 | "14 tools" | 16 | ❌ 仍差 2 |
| **game_api.idl.yaml** Deploy 注释 header L921 | "6 tools" | 7 | ❌ 仍差 1 |
| **game_api.idl.yaml** Debug 注释 header L1036 | "7 tools" | 8 | ❌ 仍差 1 |

详细计数：
- Onboarding: 10 ✓
- Auth (game): 2 ✓
- Play: 16 ✓
- Deploy: 7 ✓
- Debug: 8 ✓
- Admin: 6 ✓
- SDK: 1 ✓
- Arena: 4 ✓
- Resources: 2 ✓
- **Game API 合计: 56** ✓

**api-registry.md §3.2 header 仍声明 "54"** 而非实际 56。若 `swarm_get_terrain` 和 `swarm_get_path`（两者标记为 `— (host fn only)`）被排除于 "活跃工具" 计数，则 56−2=54 且 header 正确——但文档未说明此排除逻辑。需明确 header 计数的包含/排除规则，或更新 header 为 56。

**game_api.idl.yaml 三个 category 注释 header 仍陈旧**（Play 14→16, Deploy 6→7, Debug 7→8）。这些是 YAML 注释，不影响 codegen，但造成人工阅读时的混淆。

#### B1c — schema_source / alias_of 注释

| 工具 | game_api.idl.yaml | auth_api.idl.yaml | api-registry.md 注释 |
|------|:---:|:---:|------|
| swarm_auth_login | 无 alias_of annotation | canonical 版 (含 device_id, device_name, refresh_token, session_id) | L250: "game_api 版本为其简化形态" |
| swarm_auth_refresh | 无 alias_of annotation | canonical 版 (含 refresh_token) | L250: 同上 |

**状态**: ⚠️ **PARTIAL**。api-registry.md 有文字注释说明 game_api 的 auth 工具是简化版，但 game_api.idl.yaml 中缺少机器可读的 `schema_source` 或 `alias_of` 字段。codegen 无法从 YAML 自动推导跨 IDL 引用。

**Auth 工具计数**：auth_api.idl.yaml v0.2.0 已扩展至 20 个工具（6 cert_lifecycle + 2 session + 5 recovery + 6 profile + 1 federation），但 api-registry.md §3.3 仅列出 11 个（5 lifecycle + 6 cert/device）。api-registry.md header 声明 "11 个 Auth API 工具" 与 auth_api.idl.yaml 的 20 工具不一致——但这是有意为之（api-registry.md 仅记录面向 MCP 暴露的工具子集），还是未同步的生成缺陷？需确认。

---

### B6: Canonical RejectionReason + SwarmError Envelope

#### B6a — error.code string format + debug_detail (R33 H3)

**状态**: ✅ **FIXED**。SwarmError envelope 在 api-registry.md §8 L659-683 和 game_api.idl.yaml §8 L1669-1686 现在一致：
- `error.code`: "RejectionReason (string)" —— 一致 ✓
- `error.data`: 含 command_index, rejection_detail, debug_detail —— 一致 ✓
- `-32000`: 保留给未分类内部错误 —— 一致 ✓
- 不再有 retry_allowed/idempotency_key/retry_after_tick 字段（已从 api-registry.md 移除）

debug_detail 字段在 api-registry.md §2 L92-106 中完整描述（512 bytes max, detail_level 三级控制 competitive/practice/training）。

#### B6b — MainActionQuotaExceeded (R33 B3 Critical)

| 数据源 | MainActionQuotaExceeded 存在? |
|--------|:---:|
| game_api.idl.yaml §2 rejection_reason variants (L308-462) | ❌ 不在 35 canonical codes 中 |
| api-registry.md §2 canonical RejectionReason (L86-203) | ❌ 不在 47 canonical codes 中 |
| **02-command-validation.md §5.1 L557** | ✅ **仍在使用**：`"本 tick main action 配额已用尽 \| 每 drone 每 tick 最多 1 个 main action；第 2 个及以后返回此码"` |

**状态**: ❌ **NOT FIXED**。R33 B3 提供两个修复方案：(a) 映射到 canonical `CooldownActive` + debug_detail；(b) 注册为 canonical code。两者均未实施。02-command-validation.md §5.1 仍将 `MainActionQuotaExceeded` 作为拒绝码使用，但该码不在 wire enum 中——SDK 无法生成对应的 typed exception。

---

### D1: host_get_random

| 要求 | 验证 |
|------|------|
| 在 game_api.idl.yaml 中 | ❌ — 不在 host_functions 列表中 |
| 在 sandbox allowlist (04-wasm-sandbox.md) | ❌ — §3.2 仅列 5 个函数 |
| 在 host-functions 表 (host-functions.md) | ❌ — 仅列 5 个函数 |

**状态**: ✅ **CLOSED**。R33 B1 修复选项 (b) 已实施——host_get_random 从所有源中移除。4 个源一致显示 5 个 host function（不含 host_get_random）。这是有意为之的设计决策：确定性随机数功能将不会以 host function 形式提供。D1 "不在任何源中" = 正确闭合状态。

---

### D3: Overload PlayerId

| 要求 | 验证 |
|------|------|
| target_id type 为 PlayerId | ❌ — game_api.idl.yaml L228-231: `type: EntityId` |
| validation 使用 "visible entity proving existence" | ⚠️ — 02-command-validation.md §3.12 L347: 使用 `NotVisibleOrNotFound`（对 player_id，非 entity_id） |

详细分析：
- **game_api.idl.yaml** command_action §Overload (L227-234): target_id 参数类型为 `EntityId`，但 Overload 语义上以玩家为目标（削减其 fuel budget），而非特定实体。
- **02-command-validation.md §3.12** (L342-361): 校验逻辑说明 `target_id 是有效的 player_id`，使用 `NotVisibleOrNotFound` 和 `TargetNotVisible` 作为失败码。与 IDL 中的 `EntityId` 类型矛盾。
- **02-command-validation.md §3.12** Overload 校验还使用 `is_visible_to(target_player, attacker)` 作为可见性约束——这需要 target_id 可解析为 player_id 而非 entity_id。

**状态**: ❌ **NOT FIXED**。IDL 中 Overload 的 target_id 类型仍为 `EntityId`，应改为 `PlayerId`（或至少是 branded type 可与 player_id 互相转换）。02-command-validation.md 的校验逻辑与 IDL schema 不一致。

---

### D7: special-attack-table.md

| 要求 | 验证 |
|------|------|
| 文件 `specs/reference/special-attack-table.md` 存在 | ❌ — 文件搜索返回 0 结果 |
| 8 attacks 完整文档化 | ⚠️ — 内容存在于 02-command-validation.md §3.10-3.16 和 api-registry.md §1.3 |
| 跨文档引用 | ⚠️ — 02-command-validation.md §3.16 引用 06-phase2b-system-manifest.md |

**状态**: ❌ **NOT FIXED**。`specs/reference/special-attack-table.md` 文件不存在。虽然 8 个特殊攻击的文档存在于 02-command-validation.md（逐攻击校验、状态机矩阵、反制窗口矩阵、抗永久锁死证明）和 api-registry.md §1.3（IDL 变体表），但缺少独立的参考表文档。特别地：

- **缺失数据**：独立的 per-attack summary 表（body part, cooldown, cost, resistance, effect type, counter measures）未以统一表格形式存在——这些数据散落在 02-command-validation.md 的 8 个小节中。
- **Leech/Fabricate (Tier 2)** 在 api-registry.md §1.3 中标记 `⏳ Tier 2`，但在 02-command-validation.md §3.16 的反制窗口矩阵中列为 "瞬发/即时" 动作——两者是否已在引擎 custom_action_def 中完整注册？还是以 IDL 存根存在？

---

### E-H1: Category Naming (economy_operation)

搜索 "economy_operation" 在所有文档中返回 0 结果。当前经济操作用各自的语义类别（lifecycle, taxation, maintenance, reward, construction, transfer）而非统一 "economy_operation" 前缀。

**状态**: ✅ **OK**。未发现跨文档的 category 命名冲突。Economy 相关的 CommandAction（TransferToGlobal/TransferFromGlobal）在 IDL 中 category 为 `global_storage`（api-registry.md §1.2 称 "Global Storage 指令"）。Economy operations（§10）使用独立的 Operation category 列。命名体系一致，无混淆。

---

### E-H2: Type Registry Units / Branded Types

| 类型 | game_api.idl.yaml type_registry | api-registry.md §0 | economy.idl.yaml |
|------|:---:|:---:|:---:|
| ResourceRate_i64 | ✅ | ✅ | ✅ |
| ProgressBps_i64 | ✅ | ✅ | ❌ |
| BasisPoints | ✅ | ✅ | ✅ |
| EfficiencyBps | ✅ | ✅ | ❌ |
| ConfidenceBps | ✅ | ✅ | ❌ |
| milli_distance | ✅ | ✅ | ❌ |
| micro_cost | ✅ | ✅ | ❌ |
| **MilliUnits** | ❌ | ✅ | ✅ |

**状态**: ❌ **NOT FIXED**（= R33 M5 未修复）。`MilliUnits` (i64, 1,000 mU = 1 unit) 在 api-registry.md §0 和 economy.idl.yaml 中定义，但不在 game_api.idl.yaml 的 type_registry.fixed_point_types 中。如果 Fixed-Point Type Registry 旨在成为跨 IDL 的综合注册表，MilliUnits 也应包含在内。

---

### E-H3: omitted_categories vs omitted_count

| 数据源 | 字段名 |
|--------|------|
| game_api.idl.yaml swarm_get_snapshot output L507-514 | `omitted_count: u32` |
| api-registry.md swarm_get_snapshot output L233 | `omitted_count` |
| **09-snapshot-contract.md** L39, L50, L100 | `omitted_categories` |

**状态**: ⚠️ **DIVERGENT**。API 表面（IDL + registry）使用 `omitted_count`（单个汇总数字），但 09-snapshot-contract.md 定义 `omitted_categories`（per-category 细分）。两者语义不同：
- `omitted_count`: 被省略的实体总数
- `omitted_categories`: `{entities: N, structures: N, resources: N, ...}` 分类计数

09-snapshot-contract.md L50 明确要求 "即使某一类被省略 0 个，键也必须存在"——这暗示它期望 API 暴露结构化分类信息。若 API 仅返回汇总计数，snapshot-contract 需同步更新；若 API 应返回分类，IDL 需更新。

---

### E-H4: Codegen Command Naming

codegen.md L44-49:
```bash
hermes codegen generate --source specs/reference/*.idl.yaml --output-dir specs/reference/
hermes codegen generate --source specs/reference/*.idl.yaml --check
```

**状态**: ✅ **OK**。命令命名清晰一致（`hermes codegen generate`），子命令语义明确。L24-27 的 "禁止手写的数值" 表也已更新：MCP tool "当前 56 active"（R33 H1 曾为 "56"→ 现正确）。RejectionReason "当前 79"（35 game + 20 auth + 2 pipeline + 其他 = 79？需验证）为新增项，可能需要与 api-registry.md 的 47 canonical codes 对齐。

---

### E-H5: Recycle No Spawn Proximity

| 数据源 | Recycle 校验规则 |
|--------|----------------|
| game_api.idl.yaml §1 (index 10) L165-172 | `target_id: EntityId` — self-action, 无 spawn_id 参数 |
| api-registry.md §1.1 #10 L57 | "Recycle a drone or structure" — self-action |
| **02-command-validation.md §3.9 L277-288** | ❌ 仍要求 spawn_id, range ≤ 1 from spawn |
| **02-command-validation.md §10.3 L709-721** | ✅ self-action, 仅 object_id |

**状态**: ❌ **NOT FIXED**（= R33 L2 未修复）。02-command-validation.md 存在**文档内自相矛盾**：
- §3.9 (早期逐指令校验表): `"Recycle", "object_id": 1001, "spawn_id": 2001` — 参数含 spawn_id, 校验 "object_id 在 spawn 范围内 (range = 1)"
- §10.3 (后期 CommandAction 变体): `"Recycle", "object_id": "d1"` — 无 spawn_id, self-action

§3.9 保留了旧版（需要 spawn 邻近）的校验规则，与 IDL 和 §10.3 的 self-action 设计冲突。需删除 §3.9 中的 spawn_id 参数和 range=1 校验，与 IDL 一致：Recycle = self-action, 仅 target_id (要回收的 drone/structure)。

---

## 亮点

1. **SwarmError Envelope 统一** (R33 H3): api-registry.md §8 和 game_api.idl.yaml §8 现在对 JSON-RPC error envelope 格式完全一致——error.code 为字符串 RejectionReason, data 含 rejection_detail + debug_detail。R33 发现的 retry_allowed/idempotency_key 冲突已清理。这是本次审查中**最干净的修复**。

2. **host_get_random 一致性**: 4 个源全部一致显示 5 个 host function，无遗漏无冗余。R33 B1 通过从 registry 中移除而非强行插入 IDL 来解决——保持了 IDL 作为单一事实源的完整性。

3. **codegen.md "禁止手写数值" 表更新**: L24-27 已从 R33 的 "MCP tool 56" 更新为 "56 active"，Host function "5" 不变。这是正确的同步。

---

## GAP 修复建议

### GAP-1 (Critical): MainActionQuotaExceeded 注册为 canonical code

**问题**: B6b — 02-command-validation.md §5.1 L557 使用非 canonical 拒绝码 `MainActionQuotaExceeded`。

**修复**:
- 选项 A: 将 `MainActionQuotaExceeded` 注册为 game_api.idl.yaml rejection_reason variants 的第 36 个 canonical code (index 36, layer: validation)，同步更新 api-registry.md §2.2。
- 选项 B: 映射到 `CooldownActive` + `debug_detail: "main action quota exhausted for this tick"`, 从 02-command-validation.md 拒绝码表中移除 `MainActionQuotaExceeded`。

### GAP-2 (Critical): Overload target_id → PlayerId

**问题**: D3 — game_api.idl.yaml Overload variant L228-231: `target_id: EntityId` 应为 `PlayerId`。

**修复**:
- 将 game_api.idl.yaml command_action Overload 的 target_id 类型从 `EntityId` 改为 `PlayerId`
- 在 type_registry 或 shared_types 中确保 PlayerId 是公开类型
- 验证 02-command-validation.md §3.12 中的 `is_visible_to(target_player, attacker)` 校验与 PlayerId 类型一致

### GAP-3 (Critical): 创建 special-attack-table.md

**问题**: D7 — `specs/reference/special-attack-table.md` 不存在。

**修复**: 从 02-command-validation.md §3.10-3.16 和 api-registry.md §1.3 提取数据，创建统一参考表，每行包含：
- Action name, index, body part requirement
- Cooldown (per-drone), resource cost
- Target resistance type
- Effect summary, duration
- Counter measures (Disrupt/Fortify)
- Canonical cross-reference: api-registry.md §1.3, 02-command-validation.md §3.10-3.16, 06-phase2b-system-manifest.md §S14

### GAP-4 (High): Recycle §3.9 与 §10.3 统一

**问题**: E-H5 — 02-command-validation.md §3.9 和 §10.3 对 Recycle 参数有矛盾定义。

**修复**: 
- 将 §3.9 的 Recycle 校验更新为 self-action（移除 spawn_id, range=1 校验）
- 仅保留: `object_id.owner == player_id` (NotOwner), `target_id (要回收的实体)` 
- 或完全删除 §3.9 的 Recycle 行（因为 §10.3 已有完整定义），在 §3.9 处添加 `→ 见 §10.3` 交叉引用

### GAP-5 (High): api-registry.md 工具计数 header 与 IDL section headers 更新

**问题**: B1b — 4 处计数 header 与实际列表不一致。

**修复**:
- api-registry.md L209: "54" → "56"（或明确说明 host-only 工具排除规则）
- game_api.idl.yaml L678: "Play (14 tools)" → "Play (16 tools)"
- game_api.idl.yaml L921: "Deploy (6 tools)" → "Deploy (7 tools)"
- game_api.idl.yaml L1036: "Debug (7 tools)" → "Debug (8 tools)"
- 在 CI 中添加 section header 一致性校验

### GAP-6 (Medium): MilliUnits 加入 game_api.idl.yaml type_registry

**问题**: E-H2 — MilliUnits 在 api-registry.md 和 economy.idl.yaml 中但不在 game_api.idl.yaml 中。

**修复**: 将 MilliUnits 添加到 game_api.idl.yaml §0 type_registry.fixed_point_types，与 api-registry.md §0 对齐：
```yaml
MilliUnits:
  base_type: i64
  scale: 1_000
  description: "Sub-unit precision for intermediate economy calculations"
```

### GAP-7 (Medium): omitted_count vs omitted_categories 统一

**问题**: E-H3 — API 使用 `omitted_count`（汇总），09-snapshot-contract.md 使用 `omitted_categories`（分类）。

**修复**: 
- 选项 A: 将 IDL/registry 改为 `omitted_categories: {entities: u32, structures: u32, ...}` 以匹配 snapshot-contract
- 选项 B: 将 09-snapshot-contract.md 改为使用 `omitted_count` + 文字描述分类信息放入 debug_detail

### GAP-8 (Low): game_api Auth 工具添加 schema_source 注释

**问题**: B1c — game_api.idl.yaml auth tools 缺少机器可读的 alias_of。

**修复**: 在 swarm_auth_login 和 swarm_auth_refresh 的 YAML 中添加：
```yaml
schema_source: auth_api
alias_of: swarm_auth_login
schema_variant: simplified
```
并在 input_schema/output_schema 中仅包含 game_api 使用的字段子集。

---

## CrossCheck

- **CX-1**: Overload target_id 从 EntityId 改为 PlayerId 后，`is_visible_to(target_player, attacker)` 校验的输入签名是否需调整（从 entity 坐标可见性变为 player-level 可见性）？→ 建议 **Engine/Visibility 方向** 检查 [PlayerId visibility 函数是否支持 player-level 而非 entity-level 查询]

- **CX-2**: host_get_random 被移除后，WASM 模块如何获取确定性随机数？是否有替代机制（如通过 tick_seed 派生）？→ 建议 **Engine/Determinism 方向** 检查 [移除 host_get_random 后的确定性随机数替代方案是否在 sandbox SDK 或 snapshot 中覆盖]

- **CX-3**: auth_api.idl.yaml v0.2.0 有 20 个工具但 api-registry.md 仅列 11 个——其余 9 个（cert_lifecycle 新工具如 swarm_register_challenge, swarm_submit_csr, swarm_get_server_trust 等）是否应暴露为 MCP 工具？→ 建议 **Auth/Gateway 方向** 检查 [auth v0.2.0 新增工具是否应同步到 api-registry.md MCP 表]

- **CX-4**: Leech/Fabricate 在 api-registry.md §1.3 标记 "⏳ Tier 2" 但在 02-command-validation.md §3.16 反制矩阵中列为已实现动作——Tier 2 是否为 "custom_action_def 已注册但未激活" 还是 "完全未实现"？→ 建议 **Gameplay 方向** 检查 [Leech/Fabricate 的实现状态与文档标记一致]