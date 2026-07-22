# Command API 参考

> 同步权威源: [game_api.idl.yaml](game_api.idl.yaml) ↔ [api-registry.md](api-registry.md)

> **本文档为 API Registry 的派生展示**。权威定义见 [API Registry](api-registry.md)。本文档提供使用示例和上下文说明。
>
> 详见 `specs/gameplay/api-idl.md`、`specs/core/command-validation.md`

WASM 模块通过 ABI v2 `tick(input_ptr, input_len, output_ptr, output_len) -> TickResult` 返回 Swarm codec bytes。`TickResult.commands` 承载 `CommandIntent[]`，`TickResult.messages` 承载玩家/调试消息；JSON 只用于调试展示，不是 tick wire format。

## CommandIntent 格式

每条 CommandIntent 包含：

| 字段 | 类型 | 说明 |
|------|------|------|
| `sequence` | u32 | 玩家内序列号（每 tick 单调递增） |
| `idempotency_key` | string | 必需；同 player/tick 重复相同 command 幂等，冲突内容拒绝 |
| `client_trace_id` | string? | 可选 opaque trace id |
| `action` | Action | 指令类型 + 参数，见下方逐指令定义 |

`player_id`、`source`、`tick` 由服务端 Source Gate 注入后形成 RawCommand（见 `specs/core/command-validation` §2）。

## 指令列表 — 见 [API Registry](api-registry.md) §1

以下指令覆盖 `CommandAction` enum 的全部 13 个非战斗基础变体；战斗/效果动作通过 `CommandAction::Action { action_type, object_id, payload }` 派发到 `ActionRegistry`（见下方「Action Dispatch」节）。**权威指令清单由 IDL YAML 与 [API Registry](api-registry.md) §1 同步维护**；Repair/Spawn 的执行措辞必须同时与 `command-validation.md` 和 `phase2b-system-manifest.md` 对齐。

### Move
移动 drone 到目标方向。
```json
{ "sequence": 1, "idempotency_key": "move-1001-t42", "action": { "type": "Move", "object_id": 1001, "direction": "North" } }
```
- 校验：drone 有 MOVE body part，fatigue = 0，目标格可通行，非 spawning
- 消耗：无

### Harvest
从 Source 采集资源。
```json
{ "sequence": 2, "idempotency_key": "harvest-1001-t42", "action": { "type": "Harvest", "object_id": 1001, "target_id": 4001, "resource": "Energy" } }
```
- 校验：drone 有 WORK + CARRY body part，target 是 Source 且有资源，相邻，fatigue = 0
- 产出：基础效率 100% 时每 WORK part 采集 1 单位资源/tick；代码 throughput multiplier 可将 Harvester 采集效率提升到 150%–200%

### Transfer
向目标转移资源。
```json
{ "sequence": 3, "idempotency_key": "transfer-1001-t42", "action": { "type": "Transfer", "object_id": 1001, "target_id": 2002, "resource": "Energy", "amount": 100 } }
```
- 校验：drone 有 CARRY part 且有足够资源，target 有容量，相邻
- 支持目标：Structure、Controller（升级）、其他 drone

### Withdraw
从目标提取资源。
```json
{ "sequence": 4, "idempotency_key": "withdraw-1001-t42", "action": { "type": "Withdraw", "object_id": 1001, "target_id": 2001, "resource": "Energy", "amount": 50 } }
```
- 校验：drone 有 CARRY part，target 有足够资源，相邻

### UpgradeController
升级 owned Controller。
```json
{ "sequence": 5, "idempotency_key": "upgrade-1001-t42", "action": { "type": "UpgradeController", "object_id": 1001, "target_id": 3001 } }
```
- 校验：drone 有 WORK + CARRY body part，target 是己方 Controller，range ≤ 3，Controller level < 8，携带足够 Energy

### Spawn
创建新 drone。
```json
{ "sequence": 8, "idempotency_key": "spawn-1001-t42", "action": { "type": "Spawn", "object_id": 1001, "spawn_id": 2001, "body_parts": ["Move", "Work", "Carry"] } }
```
- S06 stable validation：spawn owner、body schema/长度 ≤ 50、cost source 与 request identity；provisional debit 后写入 `ProvisionalSpawnRequest`
- S08 volatile admission：在 S07 释放 RoomCap 后 recheck slot，accepted request 消费 RoomCap/finalize cooldown 并追加 `PendingEntityCreation`；rejected request 全额退款
- materialization：tick-end creation flush 按 StableEntityId 排序创建，最早下一 tick 可交互；不存在 body-length tick delay

### Repair
修复 owned/friendly repairable target；wire 不携带 amount。
```json
{ "sequence": 9, "idempotency_key": "repair-1001-t42", "action": { "type": "Repair", "object_id": 1001, "target_id": 2001 } }
```
- owner：S03 `build_system`；source 需要 WORK + CARRY，range ≤ 3，target 非 DeathMark 且未满 HP
- Vanilla：`repair_hp_per_work_part=5`、`repair_energy_per_hp=1`
- accepted amount：`min(missing_hits, active_work_parts × repair_hp_per_work_part, carried_energy / repair_energy_per_hp)`
- 结果：扣除 accepted Energy，写入 `PendingHeal`；S15 是 HP writer

### Build
建造建筑。
```json
{ "sequence": 10, "idempotency_key": "build-1001-t42", "action": { "type": "Build", "object_id": 1001, "x": 5, "y": 3, "structure": "Extension" } }
```
- 校验：drone 有 WORK + CARRY part，坐标在己方房间，格为空 + Plain 地形，在建 < 100，3 格内
- 消耗：结构造价

### TransferToGlobal
存入全局存储。
```json
{ "sequence": 11, "idempotency_key": "transfer-global-in-t42", "action": { "type": "TransferToGlobal", "resource": "Energy", "amount": 500 } }
```
- 校验：全局存储 enabled，未达容量上限，transfer_time_remaining = 0
- 延迟：N tick 到账（默认 10），1% 手续费，可被运输拦截

### TransferFromGlobal
从全局存储提取。
```json
{ "sequence": 12, "idempotency_key": "transfer-global-out-t42", "action": { "type": "TransferFromGlobal", "resource": "Energy", "amount": 200 } }
```
- 校验：全局存储有足够余额，transfer_time_remaining = 0
- 延迟：N tick 到账（默认 100），1% 手续费

### AlliedTransfer
通过 delayed allied transfer rules 向其他玩家转移全局资源。
```json
{ "sequence": 6, "idempotency_key": "allied-transfer-p2-t42", "action": { "type": "AlliedTransfer", "target_player": "player-2", "resource": "Energy", "amount": 200 } }
```
- 校验：目标玩家满足 alliance policy，全局存储余额充足，transfer cooldown 已结束

### Recycle
回收自身，退还 lifespan-proportional 比例（10%–50%）body part 资源。Recycle 为 self-action（仅 `object_id`，无 `target_id`）。**权威公式见 [API Registry](api-registry.md) §10 Canonical Formulas**。
```json
{ "sequence": 13, "idempotency_key": "recycle-1001-t42", "action": { "type": "Recycle", "object_id": 1001 } }
```
- 校验：`object_id` 属于调用者，实体可回收，且未处于禁止回收状态；不要求靠近 Spawn。公式由 design gameplay 定义并下沉到 Economy IDL/Resource Ledger
- 退还：`max(1000, remaining_lifespan × 5000 / total_lifespan) bp × body_cost / 10000`（范围 10%–50%）

### ClaimController
占领敌方 Controller。
```json
{ "sequence": 14, "idempotency_key": "claim-1001-t42", "action": { "type": "ClaimController", "object_id": 1001, "target_id": 3001 } }
```
- 校验：drone 有 CLAIM body part，target 是 Controller，1 格内
- 每 CLAIM part → 1 占领进度

---

## Action Dispatch

`CommandAction::Action` 将所有战斗/效果动作统一派发到 `ActionRegistry`。Vanilla 注册表包含 11 个内置动作；mod 可通过 world action manifest 注册额外动作，但不能覆盖 vanilla 名称。参数、消耗、冷却、范围、反制方式以 [Vanilla Action Canonical Table](special-attack-table.md) 为权威源。

Wire（selected payload fields 保持顶层扁平）：

```json
{ "type": "Attack", "object_id": 1001, "target_id": 5005 }
```

Internal dispatch（同一字段由 `action_type` 选择的 closed payload schema 解码）：

```text
CommandAction::Action {
  action_type: "Attack",
  object_id: 1001,
  payload: ActionPayload::Attack { target_id: 5005 }
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
| `Debilitate` | `special_attack` | 指定 damage type 抗性 ×2，持续 50 tick |
| `Disrupt` | `special_attack` | 打断目标当前操作 |
| `Fortify` | `special_attack` | 增强自身或友方防御 |
| `Leech` | `special_attack` | 造成伤害并按比例自愈 |
| `Fabricate` | `special_attack` | 将敌方 drone 转化为己方结构 |

### 附加效果（无默认 vanilla action，由 signed plugin package manifest 声明）

以下 3 个 reusable handler 可由 enabled signed plugin 的 World Action Manifest 绑定到非保留 mod action；`world.toml [mods.<plugin_id>]` 只能提供其 strict typed 参数：

| 效果 | 说明 | 目标 | 抗性 |
|------|------|------|------|
| `heal_self` | 攻击者回复造成伤害的配置比例 | enemy_any | — |
| `scramble_commands` | 随机化目标下一条指令顺序 | enemy_drone | — |
| `convert_to_structure` | 将目标 drone 转化为己方建筑 | enemy_drone | Psionic |

Vanilla action 与附加 special_effect handler 清单以 IDL/Registry 的同步定义为准；本节只说明使用边界。

> ABI v2 tick wire 返回 `TickResult`。`messages` 是 `TickResult` 字段，进入玩家消息队列，不是 `CommandAction`，也不直接改变世界状态。

## 拒绝原因 — 见 [API Registry](api-registry.md) §2

> Game `RejectionReason` 由 design 的接口语义派生，并在 IDL YAML 与 [API Registry §2](api-registry.md) 同步发布；分为 Pipeline、Validation、MCP 与 Runtime 层。Auth REST 使用 `auth_api.idl.yaml` 的独立 `AuthError` enum。

> Canonical code 为 wire enum。详细上下文信息（如 fatigue 状态、特定目标容量、body part 缺失等）放入 `debug_detail` 字段，而非增加 RejectionReason enum 变体。这保持 wire enum 稳定，同时提供丰富的调试数据。

> 替换前文档中出现的 `NotMovable`、`Fatigued`、`SourceEmpty`、`TargetFull`、`TargetEmpty`、`AlreadyHacked`、`MissingBodyPart`、`TileBlocked`、`CarryFull`、`NotYourRoom`、`BodyTooLarge` 等代码已被统一合并至 canonical code 或降级为 `debug_detail`。详见 [API Registry §2 命名规范](api-registry.md#命名规范)。

## 校验流程

```
TickResult (WASM tick() 输出, Swarm codec)
  → decode_tick_result (大小/深度/Schema 校验)
    → TickResult.commands: CommandIntent[]
  → source_gate (注入 player_id/source/tick → RawCommand)
      → validate_command (认证 + 逐条校验)
        → apply_command (通过 → 写入 ECS)
        → refund_for_rejection (拒绝 → 退燃料)
```

所有指令最终通过服务端校验管线处理，详见 `specs/core/command-validation.md`。
