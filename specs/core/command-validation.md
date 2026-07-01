# 指令校验规范

> 详见 design/interface.md

## 1. 指令管线

```
tick() 输出 JSON（来自 WASM 模块）
    │
    ▼
┌─────────────────┐
│  Tick 输出 Schema  │  JSON schema 验证：最大 256KB、拒绝额外字段、深度≤10
│  校验              │  超限/畸形的 tick 输出直接丢弃，不计入 refund
└────────┬────────┘
         │ Ok(Command[])
         ▼
┌─────────────────┐
│  反序列化         │  JSON 解析，逐指令 schema 验证，边界检查
└────────┬────────┘
         │ Ok(RawCommand[])
         ▼
┌─────────────────┐
│  预校验           │  静态检查：目标存在、归属匹配、距离范围内
└────────┬────────┘
         │ Ok(ValidatedCommand[])
         ▼
┌─────────────────┐
│  应用            │  修改世界状态（redb WriteTransaction 内）
└────────┬────────┘
         │ Ok / Err(RejectionReason)
         ▼
   记录到 TickTrace
```

**单一管线**：所有入口（WASM tick 输出、MCP tool、REST API、admin CLI）走同一 `校验 → 应用` 路径。无绕过。

### 1.1 Tick 输出 JSON Schema

WASM 模块的 `tick()` 必须返回符合以下 schema 的 JSON：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "array",
  "maxItems": 100,
  "items": { "$ref": "#/definitions/Command" }
}
```

- 顶层必须是 JSON **数组**（非 object、非 null、非原始值）
- 数组长度 ≤ MAX_COMMANDS_PER_PLAYER (100)
- 总字节数 ≤ 256 KB
- `additionalProperties: false` — 拒绝未知顶层字段
- 深度限制 ≤ 10 层
- 包含非 JSON 字节序列（二进制垃圾）→ 校验失败，整个 tick 输出丢弃

> 校验失败的 tick 输出：不计入 refund（未进入指令管线），记录到 TickTrace 为 `TickValidationFailed`。

## 2. 指令类型层次

服务端指令管线处理三种不同的指令表示，从不可信输入逐步升级为可信的已验证指令：

```
CommandIntent (WASM 输出, 不可信)
    │  仅含 sequence + action 两个字段
    │  player_id / source / tick 全部由 Source Gate 服务端注入
    ▼
RawCommand (服务端 envelope, auth 已注入)
    │  player_id / tick / sequence / action + auth context
    │  通过 Source Gate 后进入校验管线
    ▼
ValidatedCommand (校验通过, 可安全执行)
    │  所有静态检查已通过
    │  携带解析后的目标引用、距离、成本等缓存数据
    ▼
  进入应用阶段（修改世界状态）
```

### 2.1 CommandIntent（不可信输入）

WASM 模块的 `tick()` 只输出 `CommandIntent[]`，**仅允许两个字段**：

```json
{
  "sequence": 3,
  "action": {
    "type": "Move",
    "object_id": 1001,
    "direction": "North"
  }
}
```

 | 字段 | 类型 | 说明 |
 |------|------|------|
 | `sequence` | u32 | 每 tick 单调递增，WASM 自行管理 |
 | `action` | Action | 见 §3 逐指令校验矩阵 |

 **`sequence` 排序范围**：`sequence` 是 **per-(player, source)** 级别——同一玩家在同一 tick 内通过同一 source 提交的指令，按 `(source, sequence)` 排序。不同 source 的 `sequence` 空间独立（WASM 的 seq=1 不与 MCP_Deploy 的 seq=1 冲突）。全局排序键：`(priority_class, shuffle_index, source_rank, sequence, command_hash)`，其中 `shuffle_index` 来自 PRNG 的确定性 shuffle（种子 = `Blake3("shuffle" || world_seed || tick.to_le_bytes())`），`priority_class` 取值 `0`=Admin, `1`=WASM, `2`=MCP_Deploy, `3`=MCP_Query，`source_rank` 为同 shuffle slot 内 per-source 排序，`command_hash` = `Blake3(canonical_serialize(raw_command))` 作为稳定 tiebreaker。`canonical_serialize()` 遵循 RFC 8785/JCS；不额外要求 Unicode NFC normalization。使用 RawCommand（非 CommandIntent 原始输出）——确保 player_id/tick/source 等注入字段参与 hash。详见 `tick-protocol.md` §9.1。

**禁止字段**：`player_id`、`source`、`tick`、`auth` 等字段**不得**由 WASM 提供。若 CommandIntent 包含这些字段 → 整个 tick 输出被拒绝（`TickValidationFailed`），不计入 refund。

### 2.2 RawCommand（服务端 envelope）

Source Gate 验证 CommandIntent 后，服务端注入身份与时序上下文，形成 RawCommand：

```json
{
  "player_id": 42,
  "tick": 4521,
  "sequence": 3,
  "source": "WASM",
  "action": {
    "type": "Move",
    "object_id": 1001,
    "direction": "North"
  }
}
```

 字段 | 类型 | 来源 | 校验规则 |
------|------|------|---------|
 | `player_id` | u64 | **服务端注入** | 必须匹配已认证玩家 |
 `tick` | u64 | **服务端注入** | 必须是当前 tick 或下一 tick（预提交） |
 `source` | Source | **服务端注入** | 见 specs/security/command-source §2.1 来源矩阵 |
 `sequence` | u32 | WASM 提供 | 每玩家每 tick 单调递增 |
 `action` | Action | WASM 提供 | 见 §3 逐指令校验 |

### 2.3 ValidatedCommand（校验通过）

预校验阶段（§1 管线第3步）将 RawCommand 升级为 ValidatedCommand，携带解析后的引用：

```json
{
  "player_id": 42,
  "tick": 4521,
  "sequence": 3,
  "source": "WASM",
  "action_type": "Move",
  "resolved": {
    "object_ref": EntityRef(1001),
    "object_position": { "x": 5, "y": 3, "room": 1 },
    "target_ref": null,
    "distance_to_target": null,
    "cost": {}
  }
}
```

`resolved` 字段由预校验阶段填充，供应用阶段直接使用，避免二次查表。若预校验失败，返回 `RejectionReason`（见 §5）。

## 3. 逐指令校验矩阵

> **注意**：以下校验表中的错误码为说明性名称。权威 `RejectionReason` enum 与数量由 IDL 生成（见 [API Registry §2](../reference/api-registry.md#2-rejectionreason)）。`Fatigued`、`NotMovable`、`SourceEmpty`、`TargetFull`、`TargetEmpty` 等上下文信息放入 `debug_detail` 字段。下文表格中标注 `(debug_detail)` 的表示该条件不映射到独立 canonical code。

`CommandAction` 只承载基础非战斗操作与 `Action` dispatch。`Attack`、`RangedAttack`、`Heal`、`Hack`、`Drain`、`Overload`、`Debilitate`、`Disrupt`、`Fortify`、`Leech`、`Fabricate` 全部不是顶层 `CommandAction` variant，必须编码为：

```json
{"type": "Action", "object_id": 1001, "action_type": "Attack", "payload": {"target_id": 1002}}
```

Action payload 的 schema、body part、cost、cooldown、range、damage/resistance 与效果由 ActionRegistry 校验；canonical 参数见 [Vanilla Action Canonical Table](../reference/special-attack-table.md) 与 [API Registry §1.4](../reference/api-registry.md#14-actionregistry--11-vanilla--mod-extensible-combat-actions)。本节只定义顶层基础操作的校验边界。

### 3.1 Move

```json
{"type": "Move", "object_id": 1001, "direction": "North"}
```

 检查项 | 失败码 |
--------|--------|
 `object_id` 存在于世界中 | `ObjectNotFound` |
 `object_id.owner == player_id` | `NotOwner` |
 | `object_id` 是 Drone（非 Structure/Resource） | `(debug_detail)` |
 | `drone.fatigue == 0` | `(debug_detail)` |
 | `drone.body` 包含 `Move` 部件 | `NotEnoughBodyParts` |
 | 目标格可通行（非 Wall、非敌对占据） | `PositionOccupied`（见 [API Registry §2.6](../reference/api-registry.md#26-validation-condition--rejectionreason--debug_detail-映射)） |
 | Direction 是合法四方向邻居 (N/S/E/W) | `InvalidDirection` |
 | Drone 非 spawning 状态 | `CooldownActive`（见 [API Registry §2.6](../reference/api-registry.md#26-validation-condition--rejectionreason--debug_detail-映射)） |

### 3.2 Harvest

```json
{"type": "Harvest", "object_id": 1001, "target_id": 4001}
```

 检查项 | 失败码 |
--------|--------|
 `object_id` 是玩家拥有的 Drone | `NotOwner` |
 `drone.body` 包含 `Work` 部件 | `NotEnoughBodyParts` |
 `drone.body` 包含 `Carry` 部件 | `NotEnoughBodyParts` |
 `drone.carry_used < drone.carry_capacity` | `(debug_detail)` |
 `target_id` 是 Source | `(debug_detail)` |
 `target.source.energy > 0` | `InsufficientResource` |
 `object_id` 在 `target_id` 范围内 (range = 1) | `OutOfRange` |
 `drone.fatigue == 0` | `(debug_detail)` |

### 3.3 Transfer / Withdraw

```json
{"type": "Transfer", "object_id": 1001, "target_id": 2001, "resource": "Energy", "amount": 50}
{"type": "Withdraw", "object_id": 1001, "target_id": 2001, "resource": "Energy", "amount": 50}
```

 检查项 | 失败码 |
--------|--------|
 `object_id` 是玩家拥有的 Drone | `NotOwner` |
 `drone.body` 包含 `Carry` 部件 | `NotEnoughBodyParts` |
 Transfer: `drone.carry[resource] >= amount` | `InsufficientResource` |
 Withdraw: `target.carry[resource] >= amount` | `InsufficientResource` |
 目标有该资源的容量 | `InsufficientResource` |
 `object_id` 在范围内 (range = 1) | `OutOfRange` |

### 3.4 Build

```json
{"type": "Build", "object_id": 1001, "x": 10, "y": 15, "structure_type": "Extension"}
```

 检查项 | 失败码 |
--------|--------|
 `object_id` 是玩家拥有的 Drone | `NotOwner` |
 `drone.body` 包含 `Work` + `Carry` 部件 | `NotEnoughBodyParts` |
`drone.carry[Energy] >= build_cost(structure_type)` | `InsufficientResource` |
 `(x, y)` 在玩家拥有 Controller 的房间 | `(debug_detail)` |
 该格为空（无既有建筑） | `PositionOccupied` |
 该格是 Plain 地形 | `(debug_detail)` |
 在建工程数 < MAX_CONSTRUCTION_SITES (100) | `ConstructionLimitReached` |
 `object_id` 在 `(x, y)` 范围内 (range = 3) | `OutOfRange` |

### 3.5 Spawn

```json
{"type": "Spawn", "object_id": 1001, "spawn_id": 2001, "body_parts": ["Move", "Work", "Carry", "Move"]}
```

 检查项 | 失败码 |
--------|--------|
 `object_id` 是玩家拥有的 Drone | `NotOwner` |
 `spawn_id` 是玩家拥有的 Spawn | `NotOwner` |
 `spawn.cooldown == 0` | `SpawnOnCooldown` |
`body_parts.len() ≤ MAX_BODY_PARTS` | `NotEnoughBodyParts` |
`body_cost(body_parts) ≤ spawn.energy` | `InsufficientResource` |
`body_parts` 总成本 ≤ 玩家房间能量上限 | `InsufficientResource`（见 [API Registry §2.6](../reference/api-registry.md#26-validation-condition--rejectionreason--debug_detail-映射)） |
 房间有空余 spawn 槽位 | `RoomDroneCapReached` |

Spawn 只写入 `PendingEntityCreation`：新 drone 的 `StableEntityId` 可在当前 tick 预分配并写入 trace，但实体数据不加入本 tick 可见/可交互世界索引。flush 在 tick 末尾按 `StableEntityId` 排序完成；新 drone 从下一 tick 开始参与快照、命令校验和系统迭代。`SpawningGrace { remaining: 1 }` 在该首次可交互 tick 生效，使新生 drone 在首次可交互 tick 免疫 combat/special/decay；随后递减为 0 并正常参与战斗。

**Spawn body_cost 扣除时点**：`body_cost(body_parts)` 在 Stage 2a spawn 命令校验时**立即扣除**（inline apply）——此时 spawn 尚未创建，body_cost 已从 spawn.energy 和/或全局存储中扣除。若 Stage 2b spawn_system 创建失败（如 room cap 竞争），已扣除的 body_cost **全额退还**到原扣费来源（spawn.energy 优先，spawn.energy 容量不足部分回到全局存储）。资源 refund 与 §7.2 fuel refund 是独立池——前者操作 ResourceStore，后者操作 fuel budget。

### 3.6 Recycle

```json
{"type": "Recycle", "object_id": 1001}
```

| 检查项 | 失败码 |
|--------|--------|
| `object_id` 是玩家拥有的 Drone 或 Structure | `NotOwner` |
| Drone 非 spawning 状态 | `CooldownActive` |

返还 lifespan-proportional 比例（10%–50%）身体部件/建筑成本到全局存储。**权威公式见 Resource Ledger §2.5**。Recycle 为 self-action — 仅需 `object_id`，无 `target_id`/`spawn_id`。

### 3.7 Action Dispatch（combat / special）

```json
{"type": "Action", "object_id": 1001, "action_type": "Hack", "payload": {"target_id": 1002}}
```

| 检查项 | 失败码 |
|--------|--------|
| `object_id` 是玩家拥有的可执行实体 | `NotOwner` |
| `action_type` 在当前世界 ActionRegistry 中存在且启用 | `UnknownAction` |
| `payload` 满足该 action 的 schema | `InvalidResourceType` / `InvalidBodyPart` / `InvalidStructureType` / `NotEligible` |
| body part、范围、冷却、可见性、目标合法性、资源成本满足 registry validator | 见 API Registry §2.6 映射 |
| 每 drone 每 tick main action 配额未用尽 | `MainActionQuotaExceeded` |

Action handler 在 Stage 2a 中只写 typed intent buffer 或非 HP 资源/event；combat HP 变化统一由 S15 `damage_application` 写入，status 变化统一由 S22 `status_advance_system` 写入。handler 禁止直接修改 `HitPoints` 或 `StatusState`。

### 3.8 特殊攻击状态机矩阵

#### 同 tick 多命中优先级

> **修复**：特殊攻击优先级以 `phase2b-system-manifest.md` §S14 为唯一权威。此处不再重列可冲突的优先级顺序。

同一 tick 内同一目标被多个特殊攻击命中时，优先级由 `special_attack_reducer` (S14) 按 canonical priority sort 裁决。**权威优先级链见 `specs/core/phase2b-system-manifest.md` §1（System Schedule 注释）和 §S14 reducer 实现**。实现者必须以此为准，不得从本文档复制/粘贴优先级链。测试覆盖要求见 `phase2b-system-manifest.md` §同 tick 多特殊攻击命中测试样例。

#### 同类型多次命中

同一 tick 内同一目标被**同一类型**特殊攻击多次命中（来自不同 attacker）：

| 攻击类型 | 同 tick 多次行为 |
|---------|----------------|
| Hack | 仅第一个成功；后续返回 `(debug_detail)` |
| Drain | 累加：drain_total = sum(drain_i)（不超过 target 资源持有量） |
| Overload | 仅第一个成功；后续因全局冷却（50 tick per target）返回 `TargetOverloadCooldown` |
| Debilitate | 不同类型各自成功；同类型返回 `CooldownActive`（见 [API Registry §2.6](../reference/api-registry.md#26-validation-condition--rejectionreason--debug_detail-映射)） |
| Disrupt | 第一次打断所有持续效果；后续仍可执行但无额外效果 |
| Fortify | 仅第一个成功；后续因 per-target 冷却（300 tick）返回 `TargetFortifyCooldown` |
| Leech | 累加：leech_total = sum(leech_i)（不超过 target HP） |
| Fabricate | 累加：各独立构造，无冲突 |

#### 反制窗口矩阵

| 攻击 | 可被 Disrupt 打断？ | 可被 Fortify 清除？ | 反制窗口 |
|------|:--:|:--:|------|
| Hack | ✅ 打断控制锁（恢复原 owner） | ✅ 清除 Hack 状态 | Hack 施加后 5 tick 内——stage 1-4 可 Disrupt，stage 5 夺取后无法恢复 |
| Drain | ✅ 打断窃取 | ✅ 清除效果 | 持续期间任意时刻 |
| Overload | ✅ 打断（fuel 恢复立即开始） | ✅ 立即清除并触发恢复 | Overload 施加后任意时刻 |
| Debilitate | ❌（效果已施加，非持续性） | ✅ 清除易伤状态 | 50 tick 持续时间内的任意时刻 |
| Leech | ❌（瞬发效果） | ❌（非持续性） | 无——瞬发吸血不可反制 |
| Fabricate | ✅（channel 中） | ❌ | channel 期间可被 Disrupt 打断 |

### 3.9 Overload 抗永久锁死证明

**声明**: 不存在一组攻击者能通过协调 Overload 永久锁死目标 fuel budget。

**证明**:

1. 全局冷却机制：同一 `(world_id, target_player_id)` 每 50 tick 最多被 Overload 一次——**不限攻击者数量**。多个攻击者协调也无法突破此冷却。
2. 单次 Overload 影响：削减 `500,000 fuel`（MAX_FUEL=10M 的 5%），下限 `MAX_FUEL × 0.2 = 2,000,000`。
3. 恢复速率：每 tick 恢复 `fuel_budget / 1000`。对于 10M budget → 10k/tick；对于 2M budget（下限）→ 2k/tick。
4. 最坏情况分析：
   - 假设目标已在 2M 下限，50 tick 内恢复 = 50 × 2k = 100k
   - 第 50 tick 时 budget = 2M + 100k = 2.1M
   - 下一 Overload 削减 500k → budget = max(2M, 2.1M - 500k) = 2M
   - 目标始终保持在 2M 下限——**不会低于下限**
5. Fortify 清除 Overload 效果 + 立即触发恢复 → 恢复速率回到 10k/tick

**结论**: 单个持久 Overload 攻击者可以将目标压制在 ~2M fuel（下限），但无法锁死到 0。多攻击者受全局冷却限制，与单攻击者无异。

### 3.10 Recycle 比例退还与 lifespan 约束

**问题**: 若 Recycle 始终退还 50% body_cost，玩家可在 drone lifespan 末期回收价值——绕过 "aging → death → 资源损失" 的经济约束。

**修正**: Recycle 退还比例与 drone 剩余 lifespan 挂钩：

```
refund_pct = max(0.1, 0.5 × (remaining_lifespan / total_lifespan))

其中:
  remaining_lifespan = drone.lifespan - drone.age
  total_lifespan = drone.lifespan（创建时确定，含 body part age_modifier）
```

| drone 状态 | refund_pct | 示例（body_cost=1000 Energy） |
|-----------|:--:|------|
| 刚出生（remaining = total） | 50% | 500 Energy |
| 半寿 | 25% | 250 Energy |
| 剩余 20% lifespan | 10%（下限） | 100 Energy |
| 剩余 10% lifespan | 10%（下限） | 100 Energy |

**经济约束验证**：drone 在 lifespan 末期 Recycle 仅获 10% body_cost 退还——低于生产新 drone 所需的完整 body_cost，无法形成 "Recycle 末期→spawn 新 drone→净赚" 的套利循环。

### 3.11 `status_advance_system` 调度

所有特殊攻击的状态推进（Hack 的 stage 递增、Overload fuel 恢复、Debilitate 计数递减、Fortify 护盾计数递减）由 `status_advance_system` 统一处理。完整执行管道、per-status 唯一 writer contract、并发写入结构、mode unlock 策略详见 `specs/core/phase2b-system-manifest.md` §S14 + §Special Attack Unique Writer Contract + §Mode Unlock Strategy。

**调度位置**: `status_advance_system` 的权威位置在 `specs/core/phase2b-system-manifest.md` §S22。该 manifest 是 Stage 2b 系统调度的**唯一权威**——此文档不重复列完整调度链，以免与 manifest 产生冲突。任何调度相关问题以 manifest 为准。

## 4. 查询指令（只读）

查询不进指令管线。它们在快照生成阶段（阶段一）处理。

### 4.1 GetTerrain

返回 (x, y) 处地形类型。纯服务端操作。不计每 tick 配额——静态数据。

### 4.2 GetObjectsInRange

返回 (x, y) 周围 `range` 内的可见实体。
- `range ≤ MAX_QUERY_RANGE (10)`
- 仅返回玩家可见的实体（遵循 fog-of-war）
- 每玩家每 tick 查询配额：5 次

### 4.3 PathFind

返回 (from_x, from_y) 到 (to_x, to_y) 的最优路径。
- 两点在同一房间内
- `path_length ≤ MAX_PATH_LENGTH (500)` — 超出则中止
- 计入玩家计算预算（WASM fuel 或 MCP 查询配额）
- 每玩家每 tick：10 次
- 结果以 `(from, to, 地形hash)` 缓存 — 地形不变不重算

## 5. 拒绝响应 — 可见性优先

**可见性优先原则**：所有涉及 `target_id`/`target_player` 的校验，**第一步必须是可见性检查**。不可见或不存在目标统一返回 opaque 错误，不得区分 ID 是否存在。

### 5.1 拒绝码

| 拒绝码 | 含义 | 使用场景 |
|--------|------|---------|
| `NotVisibleOrNotFound` | 目标不可见或不存在 | 替代 `ObjectNotFound` — 调用者对不可见目标执行任何操作时返回 |
| `OutOfRange` | 超出有效范围 | 目标可见但距离超标 |
| `(debug_detail)` | 目标是友方 | 目标可见但为友方 |
| `(debug_detail)` | drone 疲劳 | 自身状态 |
| `MainActionQuotaExceeded` | 本 tick main action 配额已用尽 | 每 drone 每 tick 最多 1 个 main action；第 2 个及以后返回此码 |
| （其他） | 见各指令校验表 | |

**admin trace**（管理员审计视图）保留完整 detail。**player trace**（玩家 TickTrace 视图）仅返回脱敏信息。

### 5.2 玩家拒绝响应示例

```json
{
  "command": { /* 原始 RawCommand */ },
  "rejection": "NotVisibleOrNotFound",
  "tick": 4521
}
```

玩家收到 `NotVisibleOrNotFound` 时无法区分"目标不存在"与"目标存在但你看不到"——这正是安全目标。

### 5.3 Admin 完整审计

```json
{
  "command": { "type": "Attack", "object_id": 1001, "target_id": 1002, "sequence": 3 },
  "rejection": "NotVisibleOrNotFound",
  "detail": "target_id=1002, reason=not_visible_to_caller, caller_pos=(5,3), admin_only=true",
  "tick": 4521
}
```

## 6. 硬性边界与限制

 参数 | 限值 | 原因 |
------|------|------|
 MAX_BODY_PARTS | 50 | 防止 spawn 向量膨胀攻击 |
 MAX_PATH_LENGTH | 500 | 防止寻路计算爆炸 |
 MAX_QUERY_RANGE | 10 | 防止范围扫描过广 |
 MAX_COMMANDS_PER_PLAYER | 100/tick | 防止 MCP 工具滥用 |
 MAX_CONSTRUCTION_SITES | 100/房间 | 防止建造刷屏 |
 MAX_DRONES_PER_PLAYER | 见 API Registry | 容量限制以 [API Registry §Limits](../reference/api-registry.md) 为权威源；本文仅引用，不重列默认值或容量目标 |
 玩家名称 | 32 字符, `[a-zA-Z0-9 _-]` | 防 prompt 注入。**Prompt injection delimiter 必须使用此字符集之外的字符**（如 `[[`/`]]` 或 Unicode），确保玩家名无法伪造系统与用户内容的边界。 |
 房间名称 | 16 字符, `[A-Z][0-9]+[NS][0-9]+[EW]` | 标准化格式 |
 JSON 深度 | 10 | serde_json 递归限制 |
 字符串最大长度（通用） | 256 字符 | 通用保护 |
 i32 坐标范围 | [-128, 127] 每房间 | 防止溢出攻击 |

### 字段级穷举校验表

以下穷举表覆盖所有 Command 类型的 **七大校验维度**，每项校验在 `validate_and_apply()` 单一路径中执行：

 Command | 所有权 (entity_id) | 范围 (in_range) | 数量 (u32) | 资源 (≤持有量) | 坐标 (房间边界内) | 特殊校验 |
---------|-------------------|----------------|-----------|---------------|------------------|---------|
 | **Move** | `object_id.owner == player_id` | 目标格四邻可达 (range=1) | N/A | N/A | 目标格在房间内 | `drone.fatigue==0`, `drone.body` 含 `Move`, 非 spawning, 目标格可通行 |
 **Harvest** | `object_id.owner == player_id` | `object_id` 距 `target_id` ≤ 1 | N/A | `target.source.energy > 0` | N/A | `drone.body` 含 `Work`+`Carry`, `carry_used < carry_capacity`, `fatigue==0` |
 **Transfer** | `object_id.owner == player_id` | `object_id` 距 `target_id` ≤ 1 | `amount: u32`, 防溢出 (amount + target.current ≤ u32::MAX) | `drone.carry[res] ≥ amount` | N/A | `drone.body` 含 `Carry`, 目标有容量 (`InsufficientResource` 拒绝) |
 **Withdraw** | `object_id.owner == player_id` | `object_id` 距 `target_id` ≤ 1 | `amount: u32`, 防溢出 | `target.carry[res] ≥ amount` | N/A | `drone.body` 含 `Carry`, 自身有容量 |
 **Build** | `object_id.owner == player_id` | `object_id` 距 `(x,y)` ≤ 3 | N/A | `drone.carry[Energy] ≥ build_cost` | (x,y) 在玩家拥有 Controller 的房间内 | `drone.body` 含 `Work`+`Carry`, 格为空+Plain 地形, 在建 < 100 |
 | **Action dispatch** | 见 ActionRegistry | 见 ActionRegistry | 见 ActionRegistry | 见 ActionRegistry | 见 ActionRegistry | Combat/effect action (3 基础 combat + 8 特殊) 通过 `CommandAction::Action { type, payload }` dispatch。权威校验参数见 [Vanilla Action Canonical Table](../reference/special-attack-table.md) 和 [API Registry §1.1 ActionRegistry](../reference/api-registry.md#11-actionregistry)。 |
 | **ClaimController** | `object_id.owner == player_id` | `object_id` 距 `target_id` ≤ 1 | N/A | N/A | N/A | `drone.body` 含 `Claim`, target 是 Controller |

> **批级与系统级校验**（在逐指令校验之上）：  
> - **JSON 大小**：单条指令 ≤ 64KB，整批（tick 输出）≤ 256KB（与 §1 Tick 输出 JSON Schema 一致）  
> - **总数**：每 tick 每玩家 ≤ 100 条指令（含 Admin 来源）  
> - **u32 防回绕**：所有 `amount`/`sequence` 字段在反序列化阶段检查，拒绝 wrapping/overflow  
> - **所有权**：`object_id`/`spawn_id`/`target_id` 的 `owner` 必须匹配 `player_id`（Admin 放宽至可操作任意玩家实体，但仍需通过 `validate_and_apply()`）  
> - **Admin 路径统一**：Admin 命令走同一 `validate_and_apply()` 管线，仅 RejectionReason 阈值放宽；编译期通过 trait 设计确保无独立代码路径可绕过（见 specs/security/command-source §2.3）

## 7. 资源争用 Refund 策略

### 7.1 退还规则

 拒绝原因 | Refund | 理由 |
---------|--------|------|
 `InsufficientResource` | 退 50% fuel | 竞争导致——非玩家过错 |
 `PositionOccupied` | 退 50% fuel | 同上 |
 `InsufficientResource` | 退 50% fuel | 同上 |
 `OutOfRange` | 不退 | 玩家应检查距离 |
 `(debug_detail)` | 不退 | 玩家应检查疲劳 |
 `NotEnoughBodyParts` | 不退 | 玩家应知道自己 drone 组成 |
 `InsufficientResource` | 不退 | 玩家应计算资源 |
 `ObjectNotFound` | 不退 | 目标已被销毁——信息过期 |
 其他所有 | 不退 | 默认不退款 |

### 7.2 退还时序（Anti-Amplification）

**退还的 fuel 仅作用于下一 tick 的 fuel budget**，禁止同 tick 内计算放大：

- tick N 的指令在 tick N 执行阶段被拒绝 → 退还 credit 记入玩家的 `next_tick_fuel_credit`
- tick N+1 开始时，玩家 fuel budget = `MAX_FUEL + next_tick_fuel_credit`（不超过 `MAX_FUEL × 1.1`）
- 同 tick 内不得通过故意竞争失败来获取额外计算预算
- **Deploy-reset 规则（**: refund credit 与玩家 session 绑定。当部署 manifest 在 tick N 原子提交（MANIFEST_COMMIT）时，同事务内累计的 refund credit 清零。防止 v1 刷 refund → v2 消费的跨模块预算转移。**例外**: 同一 session 内的迭代部署（同 session_id）不清除 credit——不惩罚正常迭代。

### 7.3 退还上限与滥用检测

 限制 | 值 | 说明 |
------|------|------|
 每人每 tick 退还上限 | `MAX_FUEL × 10%` | 当前为 1,000,000 fuel 上限 |
 同源重复失败 | 仅首次退 50%，后续 0% | 同一 `(player, source, rejection_reason)` 在同一 tick 内重复退还不累计 |
 连续高退还率 throttle | 退还率 > 80% 连续 3 tick | 触发 throttle：该玩家下一 tick fuel budget 降为 `MAX_FUEL × 0.5` |

### 7.4 监控指标

 指标 | 阈值 | 动作 |
------|------|------|
 `refund_abuse_rate` | 退还 fuel / 总消耗 fuel > 0.5 | 记录到审计日志 |
 | `insufficient_resource_refund_pct` | InsufficientResource 占总退还 > 80% | 标记为可疑行为模式 |
 `consecutive_high_refund_ticks` | ≥ 3 | 自动 throttle（见上表） |

---

## 8. CommandAction 与 Action 边界

`CommandAction` enum 含 11 种非战斗基础操作（Move/Harvest/Transfer/Withdraw/Build/Spawn/Recycle/ClaimController/TransferToGlobal/TransferFromGlobal/Action）。全部 11 种 combat/effect action（Attack/RangedAttack/Heal + 8 special attacks）通过 `ActionRegistry` dispatch。详见 [API Registry §1.1 ActionRegistry](../reference/api-registry.md#11-actionregistry) 和 [Vanilla Action Canonical Table](../reference/special-attack-table.md)。以下 §10 各 action 的详细校验参数以 ActionRegistry 和 special-attack-table 为权威源。

### 10.1 RangedAttack

`RangedAttack` 是 ActionRegistry vanilla action，不是顶层 `CommandAction`。WASM 输出必须使用 `CommandAction::Action { type: "RangedAttack", payload }`，payload schema、body part、range、damage type、cost、cooldown 与拒绝码映射以 [special-attack-table.md](../reference/special-attack-table.md) 和 [API Registry §1.4](../reference/api-registry.md#14-actionregistry--11-vanilla--mod-extensible-combat-actions) 为准。本文不重列参数表。

### 10.2 ClaimController

占领 Controller。drone 需 Claim body part。

```json
{ "type": "ClaimController", "object_id": "d1", "target_id": "c1" }
```

 校验规则 | 说明 |
---------|------|
 body part | drone 必须有 Claim body part |
 距离 | target 在 1 格内 |
 target 类型 | target 必须是 Controller |

### 10.3 Recycle

回收 drone，退还资源。

```json
{ "type": "Recycle", "object_id": "d1" }
```

 | 规则 | 说明 |
 |------|------|
 | 标准退还 | lifespan-proportional: `max(1000, remaining_lifespan × 5000 / total_lifespan)` bp，范围 [10%, 50%] body_cost。**权威公式见 Resource Ledger §2.5 和 API Registry §10** |
 | Tutorial override | `tutorial_recycle_refund_full_ticks` 内退还 100%（world-mode override，由 world.toml 控制） |
 | 效果 | drone 走 death_mark → death_cleanup 标准死亡路径（与其他死亡一致） |

### 10.4 Action 校验（general / special attack）

Combat/effect action 通过 ActionRegistry dispatch。以下各 action 的详细参数以 [Vanilla Action Canonical Table](../reference/special-attack-table.md) 和 [API Registry §1.1 ActionRegistry](../reference/api-registry.md#11-actionregistry) 为权威源。Leech/Fabricate 的注册方式已从 `[[custom_actions]]` 改为 ActionRegistry vanilla action——非 mod extension。

#### Disrupt

```json
{ "type": "Action", "object_id": "d1", "action_type": "Disrupt", "payload": { "target_id": "e5" } }
```

 属性 | 值 |
------|-----|
 body part | Attack |
 冷却 | 50 tick |
 消耗 | 100 Energy |
 抗性 | 目标 Sonic 抗性 |
 效果 | 打断目标当前动作（Drain/Hack 等立即终止），不造成 HP 伤害 |

#### Fortify

```json
{ "type": "Action", "action_type": "Fortify", "object_id": "d1", "target_id": "f2", "sequence": N }
```

 属性 | 值 |
------|-----|
 body part | Tough |
 冷却 | 300 tick |
 消耗 | 400 Energy |
 抗性 | 无（增益+净化） |
 效果 | 护盾：所有抗性 ×0.5，清除目标所有负面状态，持续 100 tick |

#### Hack

```json
{ "type": "Action", "action_type": "Hack", "object_id": "d1", "target_id": "e5", "sequence": N }
```

 属性 | 值 |
------|-----|
 body part | Claim |
 冷却 | 200 tick |
 消耗 | 1000 Energy |
 抗性 | 目标 Psionic 抗性 |
 效果 | tick 1-2: 目标减速 50%，tick 3-4: 无法移动，tick 5: 夺取（转 Neutral）。5 tick 后自动恢复。Neutral 期间不消耗 lifespan/fuel |

#### Drain

```json
{ "type": "Action", "action_type": "Drain", "object_id": "d1", "target_id": "s1", "sequence": N }
```

 属性 | 值 |
------|-----|
 body part | Carry + Work |
 冷却 | 50 tick |
 消耗 | 200 Energy/tick |
 抗性 | 目标 EMP 抗性 |
 效果 | 每 tick 从目标建筑/存储转移 carry_capacity 单位资源 |

#### Overload

```json
{ "type": "Action", "action_type": "Overload", "object_id": "d1", "target_id": 42, "sequence": N }
```

 属性 | 值 |
------|-----|
 body part | RangedAttack |
 冷却 | 200 tick |
 消耗 | 300 Energy |
 抗性 | 目标 EMP 抗性 |
 效果 | 目标 fuel budget 减少 500k，下限 MAX_FUEL × 0.2 |

#### Debilitate

```json
{ "type": "Action", "action_type": "Debilitate", "object_id": "d1", "target_id": "e5", "damage_type": "Kinetic", "sequence": N }
```

 属性 | 值 |
------|-----|
 body part | Work |
 冷却 | 150 tick |
 消耗 | 200 Energy |
 抗性 | 目标 Corrosive 抗性 |
 效果 | 指定 damage_type 抗性 ×2，持续 50 tick |

#### Leech

```json
{ "type": "Action", "action_type": "Leech", "object_id": "d1", "target_id": "e5", "sequence": N }
```

 属性 | 值 |
------|-----|
 注册方式 | ActionRegistry vanilla action |
 damage_type | Corrosive |
 base_damage | 15 |
 消耗 | 300 Energy |
 效果 | 伤害的 50% 治疗自身 |

#### Fabricate

```json
{ "type": "Action", "action_type": "Fabricate", "object_id": "d1", "target_id": "e5", "structure_type": "Extension", "sequence": N }
```

 属性 | 值 |
------|-----|
 注册方式 | ActionRegistry vanilla action |
 冷却 | 500 tick |
 消耗 | 见 [Vanilla Action Canonical Table](../reference/special-attack-table.md)；Vanilla 为纯 Energy |
 效果 | 将目标敌方 drone 转化为己方建筑 |
