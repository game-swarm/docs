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
│  应用            │  修改世界状态（FDB 事务内）
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
- 数组长度 ≤ MAX_COMMANDS_PER_PLAYER (500)
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

 **`sequence` 排序范围**：`sequence` 是 **per-(player, source)** 级别——同一玩家在同一 tick 内通过同一 source 提交的指令，按 `(player_id, source, sequence)` 排序。不同 source 的 `sequence` 空间独立（WASM 的 seq=1 不与 MCP_Deploy 的 seq=1 冲突）。排序键：`(player_id, shuffle_order, source, sequence)`，其中 `shuffle_order` 来自 PRNG 的确定性 shuffle，保证同 tick 同 seed 同顺序。

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
 `player_id` | u32 | **服务端注入** | 必须匹配已认证玩家 |
 `tick` | u64 | **服务端注入** | 必须是当前 tick 或下一 tick（预提交） |
 `source` | Source | **服务端注入** | 见 specs/security/09-command-source §2.1 来源矩阵 |
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

### 3.1 Move

```json
{"type": "Move", "object_id": 1001, "direction": "North"}
```

 检查项 | 失败码 |
--------|--------|
 `object_id` 存在于世界中 | `ObjectNotFound` |
 `object_id.owner == player_id` | `NotOwner` |
 `object_id` 是 Drone（非 Structure/Resource） | `NotMovable` |
 `drone.fatigue == 0` | `Fatigued` |
 `drone.body` 包含 `Move` 部件 | `MissingBodyPart(Move)` |
 | 目标格可通行（非 Wall、非敌对占据） | `TileBlocked` |
 | Direction 是合法四方向邻居 (N/S/E/W) | `InvalidDirection` |
 | Drone 非 spawning 状态 | `StillSpawning` |

### 3.2 Harvest

```json
{"type": "Harvest", "object_id": 1001, "target_id": 4001}
```

 检查项 | 失败码 |
--------|--------|
 `object_id` 是玩家拥有的 Drone | `NotOwner` |
 `drone.body` 包含 `Work` 部件 | `MissingBodyPart(Work)` |
 `drone.body` 包含 `Carry` 部件 | `MissingBodyPart(Carry)` |
 `drone.carry_used < drone.carry_capacity` | `CarryFull` |
 `target_id` 是 Source | `NotSource` |
 `target.source.energy > 0` | `SourceEmpty` |
 `object_id` 在 `target_id` 范围内 (range = 1) | `OutOfRange` |
 `drone.fatigue == 0` | `Fatigued` |

### 3.3 Transfer / Withdraw

```json
{"type": "Transfer", "object_id": 1001, "target_id": 2001, "resource": "Energy", "amount": 50}
{"type": "Withdraw", "object_id": 1001, "target_id": 2001, "resource": "Energy", "amount": 50}
```

 检查项 | 失败码 |
--------|--------|
 `object_id` 是玩家拥有的 Drone | `NotOwner` |
 `drone.body` 包含 `Carry` 部件 | `MissingBodyPart(Carry)` |
 Transfer: `drone.carry[resource] >= amount` | `InsufficientResources` |
 Withdraw: `target.carry[resource] >= amount` | `InsufficientResources` |
 目标有该资源的容量 | `TargetFull` / `TargetEmpty` |
 `object_id` 在范围内 (range = 1) | `OutOfRange` |

### 3.4 Build

```json
{"type": "Build", "object_id": 1001, "x": 10, "y": 15, "structure": "Extension"}
```

 检查项 | 失败码 |
--------|--------|
 `object_id` 是玩家拥有的 Drone | `NotOwner` |
 `drone.body` 包含 `Work` + `Carry` 部件 | `MissingBodyPart` |
 `drone.carry[Energy] >= build_cost(structure)` | `InsufficientEnergy` |
 `(x, y)` 在玩家拥有 Controller 的房间 | `NotYourRoom` |
 该格为空（无既有建筑） | `TileOccupied` |
 该格是 Plain 地形 | `InvalidTerrain` |
 在建工程数 < MAX_CONSTRUCTION_SITES (100) | `TooManyConstructionSites` |
 `object_id` 在 `(x, y)` 范围内 (range = 3) | `OutOfRange` |

### 3.5 Attack

```json
{"type": "Attack", "object_id": 1001, "target_id": 1002}
```

 检查项 | 失败码 |
--------|--------|
 `object_id` 是玩家拥有的 Drone | `NotOwner` |
 `drone.body` 包含 `Attack` 部件 | `MissingBodyPart(Attack)` |
 `target_id` 存在 | `ObjectNotFound` |
 `target_id.owner != player_id` 或为中立敌对 | `FriendlyTarget` |
 `object_id` 在范围内 (range = 1) | `OutOfRange` |
 `drone.fatigue == 0` | `Fatigued` |

**TOCTOU**: 如果目标在快照和执行之间移动了，按当前位置检查范围 → 移开则 `OutOfRange`。攻击不跟踪移动目标。

### 3.6 RangedAttack

与 Attack 相同，range = 3，需要 `RangedAttack` 身体部件。

### 3.7 Heal

```json
{"type": "Heal", "object_id": 1001, "target_id": 1003}
```

 检查项 | 失败码 |
--------|--------|
 `drone.body` 包含 `Heal` 部件 | `MissingBodyPart(Heal)` |
 `target.hits < target.hits_max` | `AlreadyFullHealth` |
 目标属于玩家或盟友 | `NotFriendly` |
 Range = 3 | `OutOfRange` |

### 3.8 Spawn

```json
{"type": "Spawn", "spawn_id": 2001, "body": ["Move", "Work", "Carry", "Move"]}
```

 检查项 | 失败码 |
--------|--------|
 `spawn_id` 是玩家拥有的 Spawn | `NotYourSpawn` |
 `spawn.cooldown == 0` | `SpawnOnCooldown` |
 `body.len() ≤ MAX_BODY_PARTS (50)` | `BodyTooLarge` |
 `body_cost(body) ≤ spawn.energy` | `InsufficientEnergy` |
 `body_cost(body) ≤ 玩家房间能量上限` | `ExceedsRoomCapacity` |
 房间有空余 spawn 槽位 | `RoomDroneCapReached` |

Drone 在 Phase 2b spawn_system 中创建——位于 death_mark（释放 room cap 槽位）之后。`spawning_grace_system` 立即为新生 drone 附加 `SpawningGrace { remaining: 1 }` 组件——本 tick 内免疫所有伤害（含特殊攻击和衰减）。下一 tick combat/decay 正常参与。

**Spawn body_cost 扣除时点**：`body_cost` 在 Phase 2a spawn 命令校验时**立即扣除**（inline apply）——此时 spawn 尚未创建，body_cost 已从 spawn.energy 和/或全局存储中扣除。若 Phase 2b spawn_system 创建失败（如 room cap 竞争），已扣除的 body_cost **全额退还**到原扣费来源（spawn.energy 优先，spawn.energy 容量不足部分回到全局存储）。资源 refund 与 §7.2 fuel refund 是独立池——前者操作 ResourceStore，后者操作 fuel budget。

### 3.9 Recycle

```json
{"type": "Recycle", "object_id": 1001, "spawn_id": 2001}
```

 检查项 | 失败码 |
--------|--------|
 `object_id` 是玩家拥有的 Drone | `NotOwner` |
 `spawn_id` 是玩家的 Spawn | `NotYourSpawn` |
 `object_id` 在 spawn 范围内 (range = 1) | `OutOfRange` |

返还 50% 身体部件成本作为能量给 spawn。

### 3.10 Hack（特殊攻击）

```json
{"type": "Hack", "object_id": 1001, "target_id": 1002}
```

 检查项 | 失败码 |
--------|--------|
 `object_id` 是玩家拥有的 Drone | `NotOwner` |
 `drone.body` 包含 `Claim` 部件 | `MissingBodyPart(Claim)` |
 `target_id` 存在且是 Drone | `ObjectNotFound` |
 `target_id.owner != player_id`（非己方） | `FriendlyTarget` |
 `object_id` 在范围内 (range = 1) | `OutOfRange` |
 `drone.fatigue == 0` | `Fatigued` |
 冷却未到（200 tick，全局） | `OnCooldown` |
 目标未被其他玩家 Hack 中 | `AlreadyHacked` |

**效果**: 施加"控制锁"逐步建立控制——tick 1-2 目标减速 50%，tick 3-4 目标无法移动，tick 5 夺取成功（drone 转为 Neutral，停止执行 WASM，进入 idle）。5 tick 后自动恢复。idle 期间不消耗 lifespan。目标可通过 Disrupt 打断或 Fortify 净化控制锁。

**状态转换**: Hack 成功 → 目标 drone 获得 `HackControlLock{stage: 1-5}` 状态，每 tick stage 递增。stage=5 时 drone 转为 Neutral（`owner=0`，不执行 WASM，不消耗 fuel/lifespan）。5 tick 后自动恢复原 owner。Neutral 期间免疫再次 Hack。

**冷却**: 200 tick（全局冷却）。**资源消耗**: 1000 Energy。**抗性**: 目标 `Psionic` 抗性影响成功率。

### 3.11 Drain（特殊攻击）

```json
{"type": "Drain", "object_id": 1001, "target_id": 2002, "resource": "Energy"}
```

 检查项 | 失败码 |
--------|--------|
 `object_id` 是玩家拥有的 Drone | `NotOwner` |
 `drone.body` 包含 `Work` + `Carry` 部件 | `MissingBodyPart` |
 `target_id` 是 Structure 或 Storage | `NotStructure` |
 `target_id.owner != player_id`（非己方） | `FriendlyTarget` |
 `target` 有指定 resource 存量 > 0 | `TargetEmpty` |
 `drone.carry_used < drone.carry_capacity` | `CarryFull` |
 `object_id` 在范围内 (range = 1) | `OutOfRange` |
 `drone.fatigue == 0` | `Fatigued` |
 冷却未到（50 tick，每 drone） | `OnCooldown` |

**效果**: 从目标建筑/存储中窃取资源，每 tick 转移 `carry_capacity` 单位。

**状态转换**: Drain 成功 → 开始持续窃取。持续时间：drone 保持范围内则持续。移动或被 Disrupt → 中断。

**冷却**: 50 tick（每 drone）。**资源消耗**: 200 Energy/tick。**抗性**: 目标 `EMP` 抗性影响窃取效率。

### 3.12 Overload（特殊攻击）

```json
{"type": "Overload", "object_id": 1001, "target_id": 42}
```

 检查项 | 失败码 |
|--------|--------|
| `object_id` 是玩家拥有的 Drone | `NotOwner` |
| `drone.body` 包含 `RangedAttack` 部件 | `MissingBodyPart(RangedAttack)` |
| `target_id` 是有效的 player_id | `PlayerNotFound` |
| `target_id != player_id`（非己方） | `FriendlyTarget` |
| `is_visible_to(target_player, attacker)` — 可见性约束 | `TargetNotVisible` |
| 目标全局冷却（同一 target_id 过去 50 tick 内被 Overload） | `TargetOverloadCooldown` |
| `drone.fatigue == 0` | `Fatigued` |
| 冷却未到（200 tick，每 drone） | `OnCooldown` |

**效果**: 消耗目标计算配额（短期压制，可恢复）。目标 `fuel budget` 减少 500k（默认 MAX_FUEL=10M 的 5%）。**下限**: `MAX_FUEL × 0.2`。**可见性约束**: 必须 `is_visible_to(target, attacker)`，不可攻击不可见玩家。**全局冷却**: 同一 `(world_id, target_player_id)` 每 50 tick 最多被 Overload 一次（不限攻击者数量）。

**反馈**: Overload 结果通过 `OverloadPressure` 组件暴露（详见 `design/gameplay.md` §Overload 反馈透明度）。攻击者可看到自己对目标的 contribution 和总压力；被攻击者可看到总压力及所有可见 source 的 contribution。

**恢复**: 每 tick 恢复 `fuel_budget / 1000`（≈ 10k/tick 对于 10M 上限）。Fortify 立即清除 Overload 效果并重置恢复计时。恢复曲线可配置（world.toml `overload.fuel_recovery_rate`）。

**冷却**: 200 tick（每 drone）。**资源消耗**: 300 Energy。**抗性**: 目标 `EMP` 抗性影响削减量。

### 3.13 Debilitate（特殊攻击）

```json
{"type": "Debilitate", "object_id": 1001, "target_id": 1003, "damage_type": "EMP"}
```

 检查项 | 失败码 |
--------|--------|
 `object_id` 是玩家拥有的 Drone | `NotOwner` |
 `drone.body` 包含 `Work` 部件 | `MissingBodyPart(Work)` |
 `target_id` 存在（Drone 或 Structure） | `ObjectNotFound` |
 `target_id.owner != player_id`（非己方） | `FriendlyTarget` |
 `damage_type` ∈ DamageType 枚举 | `InvalidDamageType` |
 `target` 未被同类型 Debilitate 叠加 | `AlreadyDebilitated(damage_type)` |
 `object_id` 在范围内 (range = 3) | `OutOfRange` |
 `drone.fatigue == 0` | `Fatigued` |
 冷却未到（150 tick，每 drone） | `OnCooldown` |

**效果**: 给目标附加易伤状态。指定伤害类型抗性 ×2（受到该类型伤害加倍），持续 50 tick。

**状态转换**: Debilitate 成功 → 目标获得 `Debilitated{damage_type}` 状态（duration=50 tick）。同一目标可同时有不同类型的 Debilitate，但同类型不可叠加。

**冷却**: 150 tick（每 drone）。**资源消耗**: 200 Energy。**抗性**: 目标 `Corrosive` 抗性影响成功率。

### 3.14 Disrupt（特殊攻击）

```json
{"type": "Disrupt", "object_id": 1001, "target_id": 1002}
```

 检查项 | 失败码 |
--------|--------|
 `object_id` 是玩家拥有的 Drone | `NotOwner` |
 `drone.body` 包含 `Attack` 部件 | `MissingBodyPart(Attack)` |
 `target_id` 存在且是 Drone | `ObjectNotFound` |
 `target_id.owner != player_id`（非己方） | `FriendlyTarget` |
 `object_id` 在范围内 (range = 1) | `OutOfRange` |
 `drone.fatigue == 0` | `Fatigued` |
 冷却未到（50 tick，每 drone） | `OnCooldown` |

**效果**: 打断目标当前持续动作（Drain/Hack 控制锁等立即终止）。不造成 HP 伤害。

**冷却**: 50 tick（每 drone）。**资源消耗**: 100 Energy。**抗性**: 目标 `Sonic` 抗性影响成功率。

### 3.15 Fortify（特殊攻击/防御）

```json
{"type": "Fortify", "object_id": 1001, "target_id": 1003}
```

 检查项 | 失败码 |
|--------|--------|
| `object_id` 是玩家拥有的 Drone | `NotOwner` |
| `drone.body` 包含 `Tough` 部件 | `MissingBodyPart(Tough)` |
| `target_id` 存在（Drone 或 Structure） | `ObjectNotFound` |
| `target_id.owner == player_id` 或为盟友 | `NotFriendly` |
| `object_id` 在范围内 (range = 1) | `OutOfRange` |
| `drone.fatigue == 0` | `Fatigued` |
| 目标 per-target 冷却（同一 target_id 过去 300 tick 内被 Fortify） | `TargetFortifyCooldown` |
| 冷却未到（300 tick，每 drone） | `OnCooldown` |

若 `target_id` 省略，默认 fortify 自身（`object_id`）。

**效果**: 自身/友方获得护盾（所有抗性 ×0.5，即伤害减半）。**同时清除目标所有负面状态**（Debilitate/Drain/Overload/Hack 控制锁），持续 100 tick。**不可刷新**——护盾持续期间对同一目标再次 Fortify 返回 `TargetFortifyCooldown`（per-target 冷却 300 tick）。

**冷却**: 300 tick（每 drone）。**资源消耗**: 400 Energy。**抗性**: 无——这是增益+净化，不受抗性影响。

> 特殊攻击（§3.10-3.15）的 IDL 定义见 specs/gameplay/08-api-idl。

### 3.16 特殊攻击状态机矩阵

#### 同 tick 多命中优先级

同一 tick 内同一目标被多个特殊攻击命中时，按以下优先级执行（高优先级先执行，低优先级可能被高优先级效果覆盖或拒绝）：

| 优先级 | 攻击类型 | 理由 |
|:--:|------|------|
| 1 | **Disrupt** | 打断效果必须先于所有持续性效果——确保 Disrupt 能清除同 tick 施加的 Hack/Drain |
| 2 | **Fortify** | 净化效果先于施加——若同 tick 被 Fortify 和 Debilitate 同时命中，先净化再判断是否可施加新 Debilitate |
| 3 | **Debilitate** | 易伤在伤害类攻击前生效——放大后续 Hack/Drain/Overload/Leech 效果 |
| 4 | **Hack** | 夺取控制权在资源攻击前——Hack 成功后 target 可能失去 owner 保护 |
| 5 | **Drain / Leech** | 资源窃取 | 
| 6 | **Overload** | fuel 压制——若有同 tick Disrupt 则无效，若有同 tick Fortify 则清除 |
| 7 | **Fabricate** | 构造——在 combat 之前完成，但不受伤害类攻击影响 |

#### 同类型多次命中

同一 tick 内同一目标被**同一类型**特殊攻击多次命中（来自不同 attacker）：

| 攻击类型 | 同 tick 多次行为 |
|---------|----------------|
| Hack | 仅第一个成功；后续返回 `AlreadyHacked` |
| Drain | 累加：drain_total = sum(drain_i)（不超过 target 资源持有量） |
| Overload | 仅第一个成功；后续因全局冷却（50 tick per target）返回 `TargetOverloadCooldown` |
| Debilitate | 不同类型各自成功；同类型返回 `AlreadyDebilitated(damage_type)` |
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
| Fabricate | ❌（构造已完成） | ❌ | 无——构造是即时动作 |

### 3.17 Overload 抗永久锁死证明

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

### 3.18 Recycle 比例退还与 lifespan 约束

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

### 3.19 `status_advance_system` 调度

所有特殊攻击的状态推进（Hack 的 stage 递增、Overload fuel 恢复、Debilitate 计数递减、Fortify 护盾计数递减）由 `status_advance_system` 统一处理。调度位置在 Phase 2b 中 `combat_system` 之后、`regeneration_system` 之前：

```
death_mark → spawn → spawning_grace → combat → status_advance → (regeneration, decay 并行) → death_cleanup
```

此位置确保：
- combat 结算后，状态推进基于最新 HP/状态
- 状态推进在 regeneration 之前——regen 看到的是更新后的状态
- Fortify 护盾在 combat 后仍有效（护盾在 status_advance 中递减，下一 tick combat 前更新）

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
- `path_length ≤ MAX_PATH_LENGTH (100)` — 超出则中止
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
| `FriendlyTarget` | 目标是友方 | 目标可见但为友方 |
| `Fatigued` | drone 疲劳 | 自身状态 |
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
  "command": { "type": "Attack", "object_id": 1001, "target_id": 1002, "seq": 3 },
  "rejection": "NotVisibleOrNotFound",
  "detail": "target_id=1002, reason=not_visible_to_caller, caller_pos=(5,3), admin_only=true",
  "tick": 4521
}
```

## 6. 硬性边界与限制

 参数 | 限值 | 原因 |
------|------|------|
 MAX_BODY_PARTS | 50 | 防止 spawn 向量膨胀攻击 |
 MAX_PATH_LENGTH | 100 | 防止寻路计算爆炸 |
 MAX_QUERY_RANGE | 10 | 防止范围扫描过广 |
 | MAX_COMMANDS_PER_PLAYER | 500/tick | 防止 MCP 工具滥用 |
 MAX_CONSTRUCTION_SITES | 100/房间 | 防止建造刷屏 |
 | MAX_DRONES_PER_PLAYER | 50 | 可配置（world.toml 中 `drone.max_drones_per_player`），默认 50。Tier 1 容量目标: 50 players × 10 drones = 500 total |
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
 **Transfer** | `object_id.owner == player_id` | `object_id` 距 `target_id` ≤ 1 | `amount: u32`, 防溢出 (amount + target.current ≤ u32::MAX) | `drone.carry[res] ≥ amount` | N/A | `drone.body` 含 `Carry`, 目标有容量 (`TargetFull` 拒绝) |
 **Withdraw** | `object_id.owner == player_id` | `object_id` 距 `target_id` ≤ 1 | `amount: u32`, 防溢出 | `target.carry[res] ≥ amount` | N/A | `drone.body` 含 `Carry`, 自身有容量 |
 **Build** | `object_id.owner == player_id` | `object_id` 距 `(x,y)` ≤ 3 | N/A | `drone.carry[Energy] ≥ build_cost` | (x,y) 在玩家拥有 Controller 的房间内 | `drone.body` 含 `Work`+`Carry`, 格为空+Plain 地形, 在建 < 100 |
 **Attack** | `object_id.owner == player_id` | `object_id` 距 `target_id` ≤ 1 | N/A | N/A | N/A | `drone.body` 含 `Attack`, `target.owner != player_id`, `fatigue==0` |
 **RangedAttack** | `object_id.owner == player_id` | `object_id` 距 `target_id` ≤ 3 | N/A | N/A | N/A | `drone.body` 含 `RangedAttack`, `target.owner != player_id`, `fatigue==0` |
 **Heal** | `object_id.owner == player_id` | `object_id` 距 `target_id` ≤ 3 | N/A | N/A | N/A | `drone.body` 含 `Heal`, `target.hits < hits_max`, target 为友方 |
 **Spawn** | `spawn_id.owner == player_id` | N/A | `body.len() ≤ 50` (MAX_BODY_PARTS), u32 无回绕 | `body_cost ≤ spawn.energy` | N/A | `spawn.cooldown == 0`, 房间有空余 spawn 槽位, 不超房间能量上限 |
 **Recycle** | `object_id.owner == player_id` | `object_id` 距 `spawn_id` ≤ 1 | N/A | 资源返还计算无溢出 | N/A | `spawn_id` 是玩家 Spawn |
 **Hack** | `object_id.owner == player_id` | `object_id` 距 `target_id` ≤ 1 | N/A | Energy ≥ 1000 (消耗) | N/A | `drone.body` 含 `Claim`, target 非己方, `fatigue==0`, 冷却未到, 目标未被他人在 Hack 中 |
 **Drain** | `object_id.owner == player_id` | `object_id` 距 `target_id` ≤ 1 | N/A | `target` 有指定 resource 存量 > 0, `drone.carry_used < carry_capacity` | N/A | `drone.body` 含 `Work`+`Carry`, target 非己方, `fatigue==0`, 冷却未到 |
 | **Overload** | `object_id.owner == player_id` | `is_visible_to(target_player, attacker)` | N/A | Energy ≥ 300 (消耗) | N/A | `drone.body` 含 `RangedAttack`, target 非己方, 目标全局冷却 (50 tick), apply 阶段静默 clamp 至下限, `fatigue==0`, drone 冷却未到。fuel 恢复 `fuel_budget / 1000` per tick |
 **Debilitate** | `object_id.owner == player_id` | `object_id` 距 `target_id` ≤ 3 | N/A | Energy ≥ 200 (消耗) | N/A | `drone.body` 含 `Work`, target 非己方, `damage_type` ∈ DamageType 枚举, 无同类型叠加, `fatigue==0`, 冷却未到 |
 **Disrupt** | `object_id.owner == player_id` | `object_id` 距 `target_id` ≤ 1 | N/A | Energy ≥ 100 (消耗) | N/A | `drone.body` 含 `Attack`, target 非己方且为 Drone, `fatigue==0`, 冷却未到 |
 **Fortify** | `object_id.owner == player_id` | `object_id` 距 `target_id` ≤ 1 | N/A | Energy ≥ 400 (消耗) | N/A | `drone.body` 含 `Tough`, target 为己方/盟友, `fatigue==0`, 冷却未到 |
 **ClaimController** | `object_id.owner == player_id` | `object_id` 距 `target_id` ≤ 1 | N/A | N/A | N/A | `drone.body` 含 `Claim`, target 是 Controller |

> **批级与系统级校验**（在逐指令校验之上）：  
> - **JSON 大小**：单条指令 ≤ 64KB，整批（tick 输出）≤ 1MB  
> - **总数**：每 tick 每玩家 ≤ 500 条指令（含 Admin 来源）  
> - **u32 防回绕**：所有 `amount`/`sequence` 字段在反序列化阶段检查，拒绝 wrapping/overflow  
> - **所有权**：`object_id`/`spawn_id`/`target_id` 的 `owner` 必须匹配 `player_id`（Admin 放宽至可操作任意玩家实体，但仍需通过 `validate_and_apply()`）  
> - **Admin 路径统一**：Admin 命令走同一 `validate_and_apply()` 管线，仅 RejectionReason 阈值放宽；编译期通过 trait 设计确保无独立代码路径可绕过（见 specs/security/09-command-source §2.3）

## 7. 资源争用 Refund 策略

### 7.1 退还规则

 拒绝原因 | Refund | 理由 |
---------|--------|------|
 `SourceEmpty` | 退 50% fuel | 竞争导致——非玩家过错 |
 `TileOccupied` | 退 50% fuel | 同上 |
 `TargetFull` | 退 50% fuel | 同上 |
 `OutOfRange` | 不退 | 玩家应检查距离 |
 `Fatigued` | 不退 | 玩家应检查疲劳 |
 `MissingBodyPart` | 不退 | 玩家应知道自己 drone 组成 |
 `InsufficientResource` | 不退 | 玩家应计算资源 |
 `ObjectNotFound` | 不退 | 目标已被销毁——信息过期 |
 其他所有 | 不退 | 默认不退款 |

### 7.2 退还时序（Anti-Amplification）

**退还的 fuel 仅作用于下一 tick 的 fuel budget**，禁止同 tick 内计算放大：

- tick N 的指令在 tick N 执行阶段被拒绝 → 退还 credit 记入玩家的 `next_tick_fuel_credit`
- tick N+1 开始时，玩家 fuel budget = `MAX_FUEL + next_tick_fuel_credit`（不超过 `MAX_FUEL × 1.1`）
- 同 tick 内不得通过故意竞争失败来获取额外计算预算
- **Deploy-reset 规则**: refund credit 与玩家绑定。若玩家在 tick N+1 执行了任何部署操作（`swarm_deploy` / `MCP_Deploy` / `Deploy`），tick N 及之前累计的 refund credit 清零。防止 v1 刷 refund → v2 消费的跨模块预算转移。**例外**: 同一 session 内的迭代部署（同 session_id）不清除 credit——不惩罚正常迭代。

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
 `source_empty_refund_pct` | SourceEmpty 占总退还 > 80% | 标记为可疑行为模式 |
 `consecutive_high_refund_ticks` | ≥ 3 | 自动 throttle（见上表） |

---

## 8. CommandAction 变体

以下 CommandAction 变体。

### 10.1 RangedAttack

远程攻击。drone 需 RangedAttack body part。

```json
{ "action": "RangedAttack", "object_id": "d1", "target_id": "e5", "range": 3, "seq": N }
```

 校验规则 | 说明 |
---------|------|
 body part | drone 必须有 RangedAttack body part |
 射程 | target 在 range 范围内 |
 ownership | target 为敌方实体 |
 damage | parts × 25，damage_type = Kinetic |

### 10.2 ClaimController

占领 Controller。drone 需 Claim body part。

```json
{ "action": "ClaimController", "object_id": "d1", "target_id": "c1", "seq": N }
```

 校验规则 | 说明 |
---------|------|
 body part | drone 必须有 Claim body part |
 距离 | target 在 1 格内 |
 target 类型 | target 必须是 Controller |

### 10.3 Recycle

回收 drone，退还资源。

```json
{ "action": "Recycle", "object_id": "d1", "seq": N }
```

 规则 | 说明 |
------|------|
 标准退还 | body part spawn 总成本的 50% |
 Tutorial | 前 500 tick 退还 100% |
 效果 | drone 走 death_mark → death_cleanup 标准死亡路径（与其他死亡一致） |

### 10.4 特殊攻击

每种特殊攻击有独立冷却（tick）、资源消耗和抗性。与 HP 伤害互斥——同一 body part 同一 tick 只能执行一种。持续型攻击在 drone 移动或被 Disrupt 时中断。

#### Disrupt

```json
{ "action": "Disrupt", "object_id": "d1", "target_id": "e5", "seq": N }
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
{ "action": "Fortify", "object_id": "d1", "target_id": "f2", "seq": N }
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
{ "action": "Hack", "object_id": "d1", "target_id": "e5", "seq": N }
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
{ "action": "Drain", "object_id": "d1", "target_id": "s1", "seq": N }
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
{ "action": "Overload", "object_id": "d1", "target_id": "e5", "seq": N }
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
{ "action": "Debilitate", "object_id": "d1", "target_id": "e5", "damage_type": "Kinetic", "seq": N }
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
{ "action": "Leech", "object_id": "d1", "target_id": "e5", "seq": N }
```

 属性 | 值 |
------|-----|
 注册方式 | `[[custom_actions]]` |
 damage_type | Corrosive |
 base_damage | 15 |
 消耗 | 300 Energy |
 效果 | 伤害的 50% 治疗自身 |

#### Fabricate

```json
{ "action": "Fabricate", "object_id": "d1", "target_id": "e5", "structure_type": "Extension", "seq": N }
```

 属性 | 值 |
------|-----|
 注册方式 | `[[custom_actions]]` |
 冷却 | 500 tick |
 消耗 | 2000 Energy + 500 Matter |
 效果 | 将目标敌方 drone 转化为己方建筑 |
