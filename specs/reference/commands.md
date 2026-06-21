# Command API 参考

> 权威源: [game_api.idl.yaml](game_api.idl.yaml) → [api-registry.md](api-registry.md) (生成)

> **本文档为 API Registry 的派生展示**。权威定义见 [API Registry](api-registry.md)。本文档提供使用示例和上下文说明。
>
> 详见 `specs/gameplay/08-api-idl.md`、`specs/core/02-command-validation.md`

WASM 模块通过 `tick(snapshot) → CommandIntent[]` JSON 返回指令。

## CommandIntent 格式

每条 CommandIntent 包含：

| 字段 | 类型 | 说明 |
|------|------|------|
| `sequence` | u32 | 玩家内序列号（每 tick 单调递增） |
| `action` | Action | 指令类型 + 参数，见下方逐指令定义 |

`player_id`、`source`、`tick` 由服务端 Source Gate 注入后形成 RawCommand（见 `specs/core/02-command-validation` §2）。

## 指令列表 — 21 指令（11核心+2Global+8特殊）— 见 [API Registry](api-registry.md) §1

以下 13 种指令对应 `CommandAction` enum 的 13 个核心/Global 变体；8 种特殊攻击通过 `CommandAction::Custom(type)` 路由到 `CustomActionRegistry`（见下方「特殊攻击」节）。**权威指令清单见 [API Registry](api-registry.md) §1**（21 指令：11核心+2Global+8特殊攻击）。

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

### Spawn
创建新 drone。
```json
{ "sequence": 8, "action": { "type": "Spawn", "spawn_id": "s1", "body_parts": ["MOVE", "WORK", "CARRY"] } }
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
回收 drone，退还 lifespan-proportional 比例（10%–50%）body part 资源。**权威公式见 [API Registry](api-registry.md) §10 Canonical Formulas**。
```json
{ "sequence": 12, "action": { "type": "Recycle", "object_id": "d1", "target_id": "d1" } }
```
- 校验：drone 在 Spawn 1 格内
- 退还：`max(1000, remaining_lifespan × 5000 / total_lifespan) bp × body_cost / 10000`（范围 10%–50%）

### ClaimController
占领敌方 Controller。
```json
{ "sequence": 13, "action": { "type": "ClaimController", "object_id": "d1", "target_id": "c1" } }
```
- 校验：drone 有 CLAIM body part，target 是 Controller，1 格内
- 每 CLAIM part → 1 占领进度

---

## 特殊攻击（via `CommandAction::Custom`）

以下 8 种特殊攻击通过 `CommandAction::Custom(type)` 路由至 `CustomActionRegistry`，配置于 `world.toml` 的 `[[custom_actions]]` 段。每个关联一个同名的 `[[special_effects]]` handler。

### Disrupt
打断目标持续动作，不造成 HP 伤害。
```json
{ "sequence": 14, "action": { "type": "Disrupt", "object_id": "d1", "target_id": "e5" } }
```
- 校验：drone 有 ATTACK body part，敌方 drone，1 格内，fatigue = 0
- 冷却：50 tick | 消耗：100 Energy | 抗性：Sonic | special_effect: `disrupt`

### Fortify
自身/友方护盾 + 净化负面状态。
```json
{ "sequence": 15, "action": { "type": "Fortify", "object_id": "d1", "target_id": "f2" } }
```
- 校验：drone 有 TOUGH body part，自身或友方，1 格内，fatigue = 0
- 效果：所有抗性×0.5，清除负面状态，持续 100 tick
- 冷却：300 tick | 消耗：400 Energy | special_effect: `fortify`

### Hack
夺取敌方 drone——5 tick 渐进控制后转为 Neutral。
```json
{ "sequence": 16, "action": { "type": "Hack", "object_id": "d1", "target_id": "e5" } }
```
- 校验：drone 有 CLAIM body part，敌方 drone，1 格内，未被 hack，fatigue = 0
- 进度：tick 1-2 减速 50%，tick 3-4 无法移动，tick 5 夺取成功
- 冷却：200 tick | 消耗：1000 Energy | 抗性：Psionic | special_effect: `hack`

### Drain
从目标建筑/存储窃取资源。
```json
{ "sequence": 17, "action": { "type": "Drain", "object_id": "d1", "target_id": "b1" } }
```
- 校验：drone 有 WORK + CARRY body part，敌方建筑，1 格内，fatigue = 0
- 效果：每 tick 转移 `carry_capacity` 单位资源，持续至移动或被打断
- 冷却：50 tick | 消耗：200 Energy/tick | 抗性：EMP | special_effect: `drain`

### Overload
消耗目标 fuel budget。必须满足可见性约束——仅可攻击可见玩家。
```json
{ "sequence": 18, "action": { "type": "Overload", "object_id": "d1", "target_id": "e5" } }
```
- 校验：drone 有 RANGED_ATTACK body part，目标玩家可见（`is_visible_to`），fatigue = 0
- 效果：target fuel -500k，下限 MAX_FUEL×0.2。全局冷却：同一目标每 50 tick 最多被 Overload 一次（不限攻击者数量）。反馈通过 `OverloadPressure` 组件暴露（见 `design/gameplay.md` §Overload 反馈透明度）
- 冷却：200 tick（per drone） | 消耗：300 Energy | 抗性：EMP | special_effect: `overload`

### Debilitate
给目标附加易伤状态。
```json
{ "sequence": 19, "action": { "type": "Debilitate", "object_id": "d1", "target_id": "e5", "damage_type": "Thermal" } }
```
- 校验：drone 有 WORK body part，敌方，3 格内，fatigue = 0，无同类型叠加
- 效果：指定伤害类型抗性×2，持续 50 tick
- 冷却：150 tick | 消耗：200 Energy | 抗性：Corrosive | special_effect: `debilitate`

### Leech
吸血攻击——伤害的 50% 治疗自身。
```json
{ "sequence": 20, "action": { "type": "Leech", "object_id": "d1", "target_id": "e5" } }
```
- 校验：drone 有对应 body part，敌方，1 格内
- 伤害：Corrosive 15 dmg，治疗自身 50%
- 消耗：300 Energy | 抗性：Corrosive | special_effect: `leech`

### Fabricate
将敌方 drone 转化为己方建筑。
```json
{ "sequence": 21, "action": { "type": "Fabricate", "object_id": "d1", "target_id": "e5" } }
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

> **Out-of-Scope RFC**: `SendMessage` 指令（drone 间消息传递）为 Out-of-Scope RFC，不在当前核心定义中。详见 [API Registry](api-registry.md) §1。

## 拒绝原因 — 见 [API Registry](api-registry.md) §2

> 权威 `RejectionReason` enum 共 47 个 canonical code（35 game + 12 auth，定义见 [API Registry §2](api-registry.md)）。分为 Pipeline、Validation、MCP、Runtime、Auth 五层。

> **D2/B 设计决策**：47 canonical code 为 wire enum（35 game + 12 auth）。详细上下文信息（如 fatigue 状态、特定目标容量、body part 缺失等）放入 `debug_detail` 字段，而非增加 RejectionReason enum 变体。这保持 wire enum 稳定，同时提供丰富的调试数据。

> 旧文档中出现的 `NotMovable`、`Fatigued`、`SourceEmpty`、`TargetFull`、`TargetEmpty`、`AlreadyHacked`、`MissingBodyPart`、`TileBlocked`、`CarryFull`、`NotYourRoom`、`BodyTooLarge` 等代码已被统一合并至 canonical 47 码或降级为 `debug_detail`。详见 [API Registry §2 命名规范](api-registry.md#命名规范)。

## 校验流程

```
CommandIntent[] (WASM tick() 输出)
  → parse_tick_output (大小/深度/Schema 校验)
    → source_gate (注入 player_id/source/tick → RawCommand)
      → validate_command (认证 + 逐条校验)
        → apply_command (通过 → 写入 ECS)
        → refund_for_rejection (拒绝 → 退燃料)
```
