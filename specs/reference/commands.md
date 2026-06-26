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

## 指令列表 — 11 Core + Action dispatch（11 vanilla + mod）— 见 [API Registry](api-registry.md) §1

以下 11 种指令对应 `CommandAction` enum 的非战斗基础变体；战斗/效果动作通过 `CommandAction::Action { type, payload }` 派发到 `ActionRegistry`（见下方「Action Dispatch」节）。**权威指令清单见 [API Registry](api-registry.md) §1**。

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

### Spawn
创建新 drone。
```json
{ "sequence": 8, "action": { "type": "Spawn", "object_id": "d1", "spawn_id": "s1", "body_parts": ["MOVE", "WORK", "CARRY"] } }
```
- 校验：spawn 是玩家的 Spawn，cooldown = 0，body 长度 ≤ 50，能量足够，房间有空槽位
- 消耗：BODY_PART_COST 累加 → 从 Spawn 扣除
- 延迟：spawn 需求 tick 数 = body 长度

### Build
建造建筑。
```json
{ "sequence": 9, "action": { "type": "Build", "object_id": "d1", "x": 5, "y": 3, "structure_type": "Extension" } }
```
- 校验：drone 有 WORK + CARRY part，坐标在己方房间，格为空 + Plain 地形，在建 < 100，3 格内
- 消耗：结构造价

### TransferToGlobal
存入全局存储。
```json
{ "sequence": 10, "action": { "type": "TransferToGlobal", "object_id": "d1", "resource": "Energy", "amount": 500 } }
```
- 校验：全局存储 enabled，未达容量上限，transfer_time_remaining = 0
- 延迟：N tick 到账（默认 10），1% 手续费，可被运输拦截

### TransferFromGlobal
从全局存储提取。
```json
{ "sequence": 11, "action": { "type": "TransferFromGlobal", "object_id": "d1", "resource": "Energy", "amount": 200 } }
```
- 校验：全局存储有足够余额，transfer_time_remaining = 0
- 延迟：N tick 到账（默认 5），5% 手续费

### Recycle
回收自身，退还 lifespan-proportional 比例（10%–50%）body part 资源。Recycle 为 self-action（仅 `object_id`，无 `target_id`）。**权威公式见 [API Registry](api-registry.md) §10 Canonical Formulas**。
```json
{ "sequence": 12, "action": { "type": "Recycle", "object_id": "d1" } }
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

## Action Dispatch

`CommandAction::Action` 将所有战斗/效果动作统一派发到 `ActionRegistry`。Vanilla 注册表包含 11 个内置动作；mod 可通过 world action manifest 注册额外动作，但不能覆盖 vanilla 名称。参数、消耗、冷却、范围、反制方式以 [Vanilla Action Canonical Table](special-attack-table.md) 为权威源。

```text
CommandAction::Action {
  type: "Attack",
  payload: { object_id: "d1", target_id: "e5" }
}
```

| Action | Category | 简述 |
|--------|----------|------|
| `Attack` | `basic_combat` | 近战攻击目标 |
| `RangedAttack` | `basic_combat` | 远程攻击目标 |
| `Heal` | `basic_combat` | 治疗或修复目标 |
| `Hack` | `special_attack` | 5-stage 控制夺取 |
| `Drain` | `special_attack` | 持续窃取目标资源 |
| `Overload` | `special_attack` | 压制目标玩家 fuel budget |
| `Debilitate` | `special_attack` | 降低目标效率/附加易伤 |
| `Disrupt` | `special_attack` | 打断目标当前操作 |
| `Fortify` | `special_attack` | 增强自身或友方防御 |
| `Leech` | `special_attack` | 造成伤害并按比例自愈 |
| `Fabricate` | `special_attack` | 将敌方 drone 转化为己方结构 |

### 附加效果（无默认 vanilla action，通过 `world.toml` 配置绑定）

以下 3 个 special_effect handler 已在引擎中注册，可通过 world action manifest 绑定到 mod action：

| 效果 | 说明 | 目标 | 抗性 |
|------|------|------|------|
| `heal_self` | 攻击者回复造成伤害的配置比例 | enemy_any | — |
| `scramble_commands` | 随机化目标下一条指令顺序 | enemy_drone | — |
| `convert_to_structure` | 将目标 drone 转化为己方建筑 | enemy_drone | Psionic |

（共 11 个 vanilla action + 3 个附加 special_effect handler 可供 mod action 复用）

> **Out-of-Scope RFC**: `SendMessage` 指令（drone 间消息传递）为 Out-of-Scope RFC，不在当前核心定义中。详见 [API Registry](api-registry.md) §1。

## 拒绝原因 — 见 [API Registry](api-registry.md) §2

> 权威 `RejectionReason` enum 共 48 个 canonical code（定义见 [API Registry §2](api-registry.md)）。分为 Pipeline、Validation、MCP、Runtime、Auth 五层。

> **D2/B 设计决策**：48 canonical code 为 wire enum。详细上下文信息（如 fatigue 状态、特定目标容量、body part 缺失等）放入 `debug_detail` 字段，而非增加 RejectionReason enum 变体。这保持 wire enum 稳定，同时提供丰富的调试数据。

> 旧文档中出现的 `NotMovable`、`Fatigued`、`SourceEmpty`、`TargetFull`、`TargetEmpty`、`AlreadyHacked`、`MissingBodyPart`、`TileBlocked`、`CarryFull`、`NotYourRoom`、`BodyTooLarge` 等代码已被统一合并至 canonical code 或降级为 `debug_detail`。详见 [API Registry §2 命名规范](api-registry.md#命名规范)。

## 校验流程

```
CommandIntent[] (WASM tick() 输出)
  → parse_tick_output (大小/深度/Schema 校验)
    → source_gate (注入 player_id/source/tick → RawCommand)
      → validate_command (认证 + 逐条校验)
        → apply_command (通过 → 写入 ECS)
        → refund_for_rejection (拒绝 → 退燃料)
```
