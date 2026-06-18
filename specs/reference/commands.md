# Command API 参考

> 详见 `specs/gameplay/08-api-idl.md`、`specs/core/02-command-validation.md`

WASM 模块通过 `tick(snapshot) → CommandIntent[]` JSON 返回指令。

## CommandIntent 格式

每条 CommandIntent 包含：

| 字段 | 类型 | 说明 |
|------|------|------|
| `sequence` | u32 | 玩家内序列号（每 tick 单调递增） |
| `action` | Action | 指令类型 + 参数，见下方逐指令定义 |

`player_id`、`source`、`tick` 由服务端 Source Gate 注入后形成 RawCommand（见 `specs/core/02-command-validation` §2）。

## 指令列表（15 Core + 1 Custom + 8 Special Attacks）

以下 15 种指令对应 `CommandAction` enum 的 15 个具体变体。第 16 个变体 `CommandAction::Custom(type)` 通过 `CustomActionRegistry` 路由到 8 种特殊攻击——见下方「特殊攻击」节。

### Move
移动 drone 到目标方向。
```json
{ "sequence": 1, "action": { "type": "Move", "object_id": "d1", "direction": "North" } }
```
- 校验：drone 有 MOVE body part，fatigue = 0，目标格可通行，非 spawning
- 消耗：无

### Harvest
从 Source 采集资源。
```json
{ "sequence": 2, "action": { "type": "Harvest", "object_id": "d1", "target_id": "s1" } }
```
- 校验：drone 有 WORK + CARRY body part，target 是 Source 且有资源，相邻，fatigue = 0
- 产出：每 WORK part 采集 2 单位资源

### Transfer
向目标转移资源。
```json
{ "sequence": 3, "action": { "type": "Transfer", "object_id": "d1", "target_id": "s2", "resource": "Energy", "amount": 100 } }
```
- 校验：drone 有 CARRY part 且有足够资源，target 有容量，相邻
- 支持目标：Structure、Controller（升级）、其他 drone

### Withdraw
从目标提取资源。
```json
{ "sequence": 4, "action": { "type": "Withdraw", "object_id": "d1", "target_id": "s1", "resource": "Energy", "amount": 50 } }
```
- 校验：drone 有 CARRY part，target 有足够资源，相邻

### Attack
近战攻击。
```json
{ "sequence": 5, "action": { "type": "Attack", "object_id": "d1", "target_id": "e5" } }
```
- 校验：drone 有 ATTACK body part，target 为敌方，1 格内，fatigue = 0
- 伤害：`ATTACK parts × 30`（受 damage_multiplier 影响）

### RangedAttack
远程攻击。
```json
{ "sequence": 6, "action": { "type": "RangedAttack", "object_id": "d1", "target_id": "e5" } }
```
- 校验：drone 有 RANGED_ATTACK body part，target 在 3 格内，敌方，fatigue = 0
- 伤害：`RANGED_ATTACK parts × 25`

### Heal
治疗友方。
```json
{ "sequence": 7, "action": { "type": "Heal", "object_id": "d1", "target_id": "f2" } }
```
- 校验：drone 有 HEAL body part，target 为友方，3 格内，未满血
- 治疗量：`HEAL parts × 12`

### SpawnDrone
创建新 drone。
```json
{ "sequence": 8, "action": { "type": "Spawn", "spawn_id": "s1", "body": ["MOVE", "WORK", "CARRY"] } }
```
- 校验：spawn 是玩家的 Spawn，cooldown = 0，body 长度 ≤ 50，能量足够，房间有空槽位
- 消耗：BODY_PART_COST 累加 → 从 Spawn 扣除
- 延迟：spawn 需求 tick 数 = body 长度

### Build
建造建筑。
```json
{ "sequence": 9, "action": { "type": "Build", "object_id": "d1", "x": 5, "y": 3, "structure": "Extension" } }
```
- 校验：drone 有 WORK + CARRY part，坐标在己方房间，格为空 + Plain 地形，在建 < 100，3 格内
- 消耗：结构造价

### TransferToGlobal
存入全局存储。
```json
{ "sequence": 10, "action": { "type": "TransferToGlobal", "resource": "Energy", "amount": 500 } }
```
- 校验：全局存储 enabled，未达容量上限，transfer_time_remaining = 0
- 延迟：N tick 到账（默认 10），1% 手续费，可被运输拦截

### TransferFromGlobal
从全局存储提取。
```json
{ "sequence": 11, "action": { "type": "TransferFromGlobal", "resource": "Energy", "amount": 200 } }
```
- 校验：全局存储有足够余额，transfer_time_remaining = 0
- 延迟：N tick 到账（默认 5），5% 手续费

### Recycle
回收 drone，退还 50% body part 资源。
```json
{ "sequence": 14, "action": { "type": "Recycle", "object_id": "d1", "spawn_id": "s1" } }
```
- 校验：drone 在 Spawn 1 格内
- 退还：`body_cost(body) × 0.5`

### ClaimController
占领敌方 Controller。
```json
{ "sequence": 15, "action": { "type": "ClaimController", "object_id": "d1", "controller_id": "c1" } }
```
- 校验：drone 有 CLAIM body part，target 是 Controller，1 格内
- 每 CLAIM part → 1 占领进度

---

## 特殊攻击（via `CommandAction::Custom`）

以下 8 种特殊攻击通过 `CommandAction::Custom(type)` 路由至 `CustomActionRegistry`，配置于 `world.toml` 的 `[[custom_actions]]` 段。每个关联一个同名的 `[[special_effects]]` handler。

### Disrupt
打断目标持续动作，不造成 HP 伤害。
```json
{ "sequence": 16, "action": { "type": "Disrupt", "object_id": "d1", "target_id": "e5" } }
```
- 校验：drone 有 ATTACK body part，敌方 drone，1 格内，fatigue = 0
- 冷却：50 tick | 消耗：100 Energy | 抗性：Sonic | special_effect: `disrupt`

### Fortify
自身/友方护盾 + 净化负面状态。
```json
{ "sequence": 17, "action": { "type": "Fortify", "object_id": "d1", "target_id": "f2" } }
```
- 校验：drone 有 TOUGH body part，自身或友方，1 格内，fatigue = 0
- 效果：所有抗性×0.5，清除负面状态，持续 100 tick
- 冷却：300 tick | 消耗：400 Energy | special_effect: `fortify`

### Hack
夺取敌方 drone——5 tick 渐进控制后转为 Neutral。
```json
{ "sequence": 18, "action": { "type": "Hack", "object_id": "d1", "target_id": "e5" } }
```
- 校验：drone 有 CLAIM body part，敌方 drone，1 格内，未被 hack，fatigue = 0
- 进度：tick 1-2 减速 50%，tick 3-4 无法移动，tick 5 夺取成功
- 冷却：200 tick | 消耗：1000 Energy | 抗性：Psionic | special_effect: `hack`

### Drain
从目标建筑/存储窃取资源。
```json
{ "sequence": 19, "action": { "type": "Drain", "object_id": "d1", "target_id": "b1" } }
```
- 校验：drone 有 WORK + CARRY body part，敌方建筑，1 格内，fatigue = 0
- 效果：每 tick 转移 `carry_capacity` 单位资源，持续至移动或被打断
- 冷却：50 tick | 消耗：200 Energy/tick | 抗性：EMP | special_effect: `drain`

### Overload
消耗目标 fuel budget。必须满足可见性约束——仅可攻击可见玩家。
```json
{ "sequence": 20, "action": { "type": "Overload", "object_id": "d1", "target_id": 42 } }
```
- 校验：drone 有 RANGED_ATTACK body part，目标玩家可见（`is_visible_to`），fatigue = 0
- 效果：target fuel -500k，下限 MAX_FUEL×0.2。全局冷却：同一目标每 50 tick 最多被 Overload 一次（不限攻击者数量）。反馈通过 `OverloadPressure` 组件暴露（见 `design/gameplay.md` §Overload 反馈透明度）
- 冷却：200 tick（per drone） | 消耗：300 Energy | 抗性：EMP | special_effect: `overload`

### Debilitate
给目标附加易伤状态。
```json
{ "sequence": 21, "action": { "type": "Debilitate", "object_id": "d1", "target_id": "e5", "damage_type": "Thermal" } }
```
- 校验：drone 有 WORK body part，敌方，3 格内，fatigue = 0，无同类型叠加
- 效果：指定伤害类型抗性×2，持续 50 tick
- 冷却：150 tick | 消耗：200 Energy | 抗性：Corrosive | special_effect: `debilitate`

### Leech ⏳ Tier 2
吸血攻击——伤害的 50% 治疗自身。
```json
{ "sequence": 22, "action": { "type": "Leech", "object_id": "d1", "target_id": "e5" } }
```
- 校验：drone 有对应 body part，敌方，1 格内
- 伤害：Corrosive 15 dmg，治疗自身 50%
- 消耗：300 Energy | 抗性：Corrosive | special_effect: `leech`

### Fabricate ⏳ Tier 2
将敌方 drone 转化为己方建筑。
```json
{ "sequence": 23, "action": { "type": "Fabricate", "object_id": "d1", "target_id": "e5" } }
```
- 校验：drone 有对应 body part，敌方 drone，1 格内
- 冷却：500 tick | 消耗：2000 Energy + 500 Matter | special_effect: `fabricate`

### 附加效果（无默认 CustomAction，通过 `world.toml` 配置绑定）

以下 3 个 special_effect handler 已在引擎中注册，可通过 `[[custom_actions]]` + `[[special_effects]]` 配置绑定到自定义动作：

| 效果 | 说明 | 目标 | 抗性 |
|------|------|------|------|
| `heal_self` | 攻击者回复造成伤害的配置比例 | enemy_any | — |
| `scramble_commands` | 随机化目标下一条指令顺序 | enemy_drone | — |
| `convert_to_structure` | 将目标 drone 转化为己方建筑 | enemy_drone | Psionic |

（共 11 个 special_effect handler：8 个绑定默认 CustomAction + 3 个附加）

## 拒绝原因（45 种）

> `RejectionReason` enum 共 45 个变体。以下为主管线校验拒绝原因。

| 拒绝原因 | 说明 |
|----------|------|
| `ObjectNotFound` | object 或 target 不存在 |
| `NotOwner` | 不是实体的拥有者 |
| `NotMovable` | 目标实体不可移动（非 Drone） |
| `Fatigued` | drone 疲劳值 > 0，无法行动 |
| `MissingBodyPart` | 缺少必需身体部件（含缺失的 part 名） |
| `TileBlocked` | 目标格被阻挡（Wall / 敌对占据） |
| `InvalidDirection` | 非法的移动方向 |
| `StillSpawning` | drone 仍在孵化中 |
| `OutOfRoom` | 目标不在当前房间 |
| `NoPath` | 无可达路径 |
| `PathTooLong` | 路径超过最大长度限制 |
| `InsufficientMoveParts` | MOVE 部件不足以消除 fatigue |
| `CarryFull` | drone 携带容量已满 |
| `NotSource` | 目标不是资源点 |
| `SourceEmpty` | 资源点已枯竭 |
| `OutOfRange` | 目标超出有效距离（含实际距离和最大距离） |
| `InsufficientResource` | 指定资源不足（含资源名、需求量、可用量） |
| `TargetFull` | 目标资源存储已满 |
| `TargetEmpty` | 目标无可提取资源 |
| `NotYourRoom` | 不在你控制的房间内 |
| `TileOccupied` | 目标格已被占据 |
| `InvalidTerrain` | 地形不支持该操作 |
| `TooManyConstructionSites` | 在建工程数已达上限 |
| `AlreadyFullHealth` | 目标已满血 |
| `FriendlyTarget` | 目标是友方（不允许攻击） |
| `NotYourSpawn` | Spawn 不属于你 |
| `SpawnOnCooldown` | Spawn 在冷却中 |
| `BodyTooLarge` | body part 数量超过上限 |
| `ExceedsRoomCapacity` | 超出房间能量/槽位上限 |
| `RoomDroneCapReached` | 房间 drone 数量已达上限 |
| `NotFriendly` | 目标不是友方（不允许治疗/buff） |
| `AlreadyHacked` | 目标已被其他玩家 Hack 中 |
| `InvalidDamageType` | damage_type 不在注册的 DamageType 枚举中 |
| `AlreadyDebilitated` | 目标已有同类型 Debilitate 效果（含 damage_type） |
| `NotVisibleOrNotFound` | 目标不可见或不存在——替代 `PlayerNotFound`。Overload 等使用等价拒绝类 |

> **管线级拒绝**（在 Command 校验之前触发，不计入 `RejectionReason` enum 的仅有）：
> `InvalidJson`、`SchemaViolation`。
>
> 注：`SourceNotAllowed` 和 `UnknownAction` **在** `RejectionReason` enum 内——它们在上表已列出，当在管线早期触发时同属管线级拒绝。

> **子系统拒绝**（由各自模块独立校验，非 Command 校验管线）：`GlobalStorageDisabled`、`TransferInProgress`。MCP 层另有 `RateLimited`。

## 校验流程

```
CommandIntent[] (WASM tick() 输出)
  → parse_tick_output (大小/深度/Schema 校验)
    → source_gate (注入 player_id/source/tick → RawCommand)
      → validate_command (认证 + 逐条校验)
        → apply_command (通过 → 写入 ECS)
        → refund_for_rejection (拒绝 → 退燃料)
```
