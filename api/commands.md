# Command API 参考

> 详见 `specs/08-game-api-idl`、`specs/02-command-validation`

WASM 模块通过 `tick(snapshot) → Command[]` JSON 返回指令。

## 通用字段

每条 Command 包含：
- `action`: 指令类型
- `object_id`: 执行的 drone ID
- `seq`: 玩家内序列号（递增）
- 各 action 特定参数

## 指令列表（23 种）

### Move
移动 drone 到目标坐标。
```json
{ "action": "Move", "object_id": "d1", "target": {"x": 10, "y": 5}, "seq": 1 }
```
- 校验：目标在 drone 1 格范围内
- 消耗：1 MOVE body part → 消除 1 fatigue

### Harvest
从 Source 采集资源。
```json
{ "action": "Harvest", "object_id": "d1", "target_id": "s1", "seq": 2 }
```
- 校验：drone 有 WORK body part，target 是 Source，相邻
- 产出：每 WORK part 采集 2 单位资源，Source.ticks_to_regeneration 重置

### Transfer
向目标转移资源。
```json
{ "action": "Transfer", "object_id": "d1", "target_id": "s2", "resource": "Energy", "amount": 100, "seq": 3 }
```
- 校验：drone 有 CARRY part 且有足够资源，target 有容量
- 支持目标：Structure、Controller（升级）、其他 drone

### Withdraw
从目标提取资源。
```json
{ "action": "Withdraw", "object_id": "d1", "target_id": "s1", "resource": "Energy", "amount": 50, "seq": 4 }
```
- 校验：drone 有 CARRY part，target 有足够资源

### Attack
近战攻击。
```json
{ "action": "Attack", "object_id": "d1", "target_id": "e5", "seq": 5 }
```
- 校验：drone 有 ATTACK body part，target 为敌方且在 1 格内
- 伤害：`ATTACK parts × 30` （受 damage_multiplier 影响）

### RangedAttack
远程攻击。
```json
{ "action": "RangedAttack", "object_id": "d1", "target_id": "e5", "range": 3, "seq": 6 }
```
- 校验：drone 有 RANGED_ATTACK body part，target 在射程内
- 伤害：`RANGED_ATTACK parts × 25`

### Heal
治疗友方。
```json
{ "action": "Heal", "object_id": "d1", "target_id": "f2", "seq": 7 }
```
- 校验：drone 有 HEAL body part，target 为友方且在 1 格内
- 治疗量：`HEAL parts × 12`

### Spawn
创建新 drone。
```json
{ "action": "Spawn", "object_id": "s1", "body": ["MOVE", "WORK", "CARRY"], "seq": 8 }
```
- 校验：object 是 Spawn structure，有足够 energy，body 合法
- 消耗：BODY_PART_COST 累加 → 从 Spawn energy 扣除
- 延迟：spawn 需求 tick 数 = body 长度

### Build
建造建筑。
```json
{ "action": "Build", "object_id": "d1", "target": {"x": 5, "y": 3}, "structure_type": "Extension", "seq": 9 }
```
- 校验：drone 有 WORK part，位置合法，满足 RCL 解锁条件
- 消耗：BUILD_COST_MULTIPLIER × 基础造价

### TransferToGlobal
存入全局存储。
```json
{ "action": "TransferToGlobal", "object_id": "d1", "resource": "Energy", "amount": 500, "seq": 10 }
```
- 校验：全局存储 enabled，未达容量上限
- 延迟：10 tick 到账，1% 手续费
- 可被运输拦截

### TransferFromGlobal
从全局存储提取。
```json
{ "action": "TransferFromGlobal", "object_id": "d1", "resource": "Energy", "amount": 200, "seq": 11 }
```
- 校验：全局存储有足够余额
- 延迟：5 tick 到账，5% 手续费

### CreateMarketOrder
创建市场订单。
```json
{ "action": "CreateMarketOrder", "object_id": "d1", "resource": "Energy", "amount": 1000, "price_resource": "Matter", "price_amount": 500, "seq": 12 }
```
- 校验：market_requires_terminal 为 true 时需 Terminal 建筑

### BuyMarketOrder
购买市场订单。
```json
{ "action": "BuyMarketOrder", "object_id": "d1", "order_id": 42, "seq": 13 }
```
- 校验：订单存在且未过期，购买者有足够资源

### Recycle
回收 drone，退还 50% body part 资源。
```json
{ "action": "Recycle", "object_id": "d1", "spawn_id": "s1", "seq": 14 }
```
- 校验：drone 在 Spawn 1 格内
- 退还：`body_cost(body) × 0.5`

### ClaimController
占领敌方 Controller。
```json
{ "action": "ClaimController", "object_id": "d1", "target_id": "c1", "seq": 15 }
```
- 校验：drone 有 CLAIM body part，target 是 Controller
- 每 CLAIM part → 1 占领进度

### Disrupt
打断目标持续动作，不造成 HP 伤害。
```json
{ "action": "Disrupt", "object_id": "d1", "target_id": "e5", "seq": 16 }
```
- 校验：drone 有 ATTACK body part，敌方 drone，1 格内
- 冷却：50 tick | 消耗：100 Energy | 抗性：Sonic
- special_effect: `disrupt`

### Fortify
自身/友方护盾 + 净化负面状态。
```json
{ "action": "Fortify", "object_id": "d1", "target_id": "f2", "seq": 17 }
```
- 校验：drone 有 TOUGH body part，自身或友方，1 格内
- 效果：所有抗性×0.5，清除负面状态，持续 100 tick
- 冷却：300 tick | 消耗：400 Energy
- special_effect: `fortify`

### Hack
夺取敌方 drone——5 tick 渐进控制后转为 Neutral。
```json
{ "action": "Hack", "object_id": "d1", "target_id": "e5", "seq": 18 }
```
- 校验：drone 有 CLAIM body part，敌方 drone，1 格内，未被 hack
- 进度：tick 1-2 减速 50%，tick 3-4 无法移动，tick 5 夺取成功
- 冷却：200 tick | 消耗：1000 Energy | 抗性：Psionic
- special_effect: `hack`

### Drain
从目标建筑/存储窃取资源。
```json
{ "action": "Drain", "object_id": "d1", "target_id": "b1", "seq": 19 }
```
- 校验：drone 有 CARRY+WORK body part，敌方建筑，1 格内
- 效果：每 tick 转移 `carry_capacity` 单位资源
- 冷却：50 tick | 消耗：200 Energy/tick | 抗性：EMP
- special_effect: `drain`

### Overload
消耗目标 fuel budget。
```json
{ "action": "Overload", "object_id": "d1", "target_id": "<player_id>", "seq": 20 }
```
- 校验：drone 有 RANGED_ATTACK body part，敌方玩家，fuel 高于 20%
- 效果：target fuel -500k，下限 MAX_FUEL×0.2
- 冷却：200 tick | 消耗：300 Energy | 抗性：EMP
- special_effect: `overload`

### Debilitate
给目标附加易伤状态。
```json
{ "action": "Debilitate", "object_id": "d1", "target_id": "e5", "damage_type": "Thermal", "seq": 21 }
```
- 校验：drone 有 WORK body part，敌方，3 格内
- 效果：指定伤害类型抗性×2，持续 50 tick
- 冷却：150 tick | 消耗：200 Energy | 抗性：Corrosive
- special_effect: `debilitate`

### Leech
吸血攻击——伤害的 50% 治疗自身。
```json
{ "action": "Leech", "object_id": "d1", "target_id": "e5", "seq": 22 }
```
- 校验：drone 有对应 body part，敌方，1 格内
- 伤害：Corrosive 15 dmg，治疗自身 50%
- 消耗：300 Energy | 抗性：Corrosive
- special_effect: `leech`

### Fabricate
将敌方 drone 转化为己方建筑。
```json
{ "action": "Fabricate", "object_id": "d1", "target_id": "e5", "seq": 23 }
```
- 校验：drone 有对应 body part，敌方 drone，1 格内
- 冷却：500 tick | 消耗：2000 Energy + 500 Matter
- special_effect: `fabricate`

## 拒绝原因（24 种）

| 拒绝原因 | 说明 |
|----------|------|
| `InvalidJson` | JSON 格式错误 |
| `SchemaMismatch` | 缺少必需字段 |
| `UnknownAction` | action 不在允许列表中 |
| `SourceNotAllowed` | 命令来源无权执行该操作 |
| `NoSuchEntity` | object 或 target 不存在 |
| `NotOwner` | 不是实体的拥有者 |
| `EntityDead` | 实体已死亡 |
| `CooldownActive` | 实体在冷却中 |
| `InsufficientResources` | 资源不足 |
| `InvalidTarget` | 目标类型不匹配 |
| `OutOfRange` | 目标超出范围 |
| `PathBlocked` | 移动路径被阻挡 |
| `CapacityExceeded` | 超出容量限制 |
| `RclRequirement` | RCL 等级不足 |
| `BodyPartMissing` | 缺少必需身体部件 |
| `NoSpawnAvailable` | 无可用的 Spawn |
| `InvalidBodyPlan` | 身体规划非法 |
| `SpawnCooldown` | Spawn 在冷却中 |
| `GlobalStorageDisabled` | 全局存储未启用 |
| `GlobalStorageFull` | 全局存储已满 |
| `MarketOrderNotFound` | 订单不存在 |
| `MarketOrderExpired` | 订单已过期 |
| `RateLimited` | 超出频率限制 |
| `InvalidSchema` | Schema 不匹配 |

## 校验流程

```
tick() 返回 JSON
  → parse_tick_output (大小/深度/Schema 校验)
    → source_gate (权限矩阵检查)
      → validate_command (认证 + 逐条 valid)
        → apply_command (通过 → 写入 ECS)
        → refund_for_rejection (拒绝 → 退燃料)
```
