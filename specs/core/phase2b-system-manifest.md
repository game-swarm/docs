# Complete Tick Execution Manifest — 派生执行合同

> 详见 design/engine.md
>
> 本文档从 `design/engine.md` 的目标调度派生完整可执行顺序，覆盖 System Pass 2a inline 命令处理器与 System Pass 2b 被动系统。Design 是上游语义权威；其他派生 specs 必须与本清单保持一致，但本清单不得反向改写 design。
>
> **修复**：Persistent Status Effects 拆分为「并行 buffer 生产」(S16-S21/S22b) + 「串行唯一 committer」(S22)，S22 移出 Parallel Set B。combat 与特殊攻击不再由 S01 直接处理：Attack/RangedAttack/Heal 经 Action dispatch 进入 combat intent buffer；special actions 经 ActionRegistry handler 进入 special intent，S14 再把 Leech 路由到 S15、persistent/Fabricate intents 路由到 S22。

## 原则

1. **System Pass 2a + System Pass 2b 统一清单**：本文档覆盖 tick 执行的全部系统，System Pass 2a inline 处理器与 System Pass 2b 被动系统在同一时间线中明确定义。
2. **Serial Spine + Parallel Sets**：核心管线为串行顺序，声明为 parallel 的 set 内系统可并行。
3. **Stable IDs**：每个 system 有固定 `system_id` 和 `version`，manifest hash 进入 TickTrace。
4. **显式迭代顺序**：所有系统内实体迭代按 `StableEntityId` 或 canonical key 排序，不依赖 Bevy archetype order。
5. **R/W 声明**：每个 system 声明 reads 和 writes 的 Component/Resource 集合，CI 验证无数据竞争。
6. **Unique Writer Contract**：每种 status/component 有且仅有一个 system 写入。并行 set 内系统只写 typed buffer，不直接写 StatusState。

---

## 1. System Schedule (25 registered Pass 2b + 6 Pass 2a inline = 31 combined)

```
Serial Spine:
  System Pass 2a: Sorted Command Loop (inline, per-command handler dispatch)
    ┌─────────────────────────────────────────────────────┐
    │ for cmd in sorted(gameplay_raw_queue,                  │
    │     key=(player_order, player_id, sequence, command_id)):│
    │   match cmd.kind:                                    │
    │     Move/Harvest →                                   │
    │       [S01] command_executor (inline handler)        │
    │     Action { action_type, payload } →                │
    │       action_dispatch handler (per-command,          │
    │       not a manifest system)                         │
    │     ClaimController/UpgradeController →              │
    │       [S02] controller_system (inline)               │
    │     Build/Repair →                                   │
    │       [S03] build_system (inline)                    │
    │     Recycle →                                        │
    │       [S04] recycle_system (inline)                  │
    │     Transfer/Withdraw/TransferToGlobal/              │
    │     TransferFromGlobal/AlliedTransfer →              │
    │       [S05] transfer_system (inline)                 │
    │     Spawn (validate + debit + pending) →             │
    │       [S06] spawn_validator (inline)                 │
    └─────────────────────────────────────────────────────┘
  ├─────────────────────────────────────────────────────┤
  │ System Pass 2b: System Pass                           │
  │ [S07] death_marker         (serial, frees RoomCap)  │
  │ [S08] spawn_system         (serial, accepts/refunds)│
  │ [S09] spawning_grace_system (serial, BEFORE combat) │
  │ [S10] regeneration_system  (serial, BEFORE dmg)     │
  ├─────────────────────────────────────────────────────┤
  │ Parallel Set A: Combat                               │
  │ [S11] attack_system        ┐                        │
  │ [S12] ranged_attack_system  ├─ parallel              │
  │ [S13] heal_system           ┘  (disjoint entities)   │
  ├─────────────────────────────────────────────────────┤
  │ [S14] special_attack_reducer (serial, pending→sort) │
  │ [S15] damage_application   (serial, reduces A)      │
  ├─────────────────────────────────────────────────────┤
  │ Parallel Set B: Status/Resolution Buffer Production  │
  │ ┌─ S16-S22b 只读输入，写互斥 typed buffer ────┐     │
  │ │ [S16] hack_buffer          ┐                   │   │
  │ │ [S17] drain_buffer          │                   │   │
  │ │ [S18] overload_buffer       ├─ parallel         │   │
  │ │ [S19] debilitate_buffer     │  (disjoint types) │   │
  │ │ [S20] disrupt_buffer        │                   │   │
  │ │ [S21] fortify_buffer        │                   │   │
  │ │ [S22a] leech_buffer         │                   │   │
  │ │ [S22b] fabricate_buffer     ┘                   │   │
  │ └────────────────────────────────────────────────┘   │
  ├─────────────────────────────────────────────────────┤
  │ [S22] status_advance_system  (serial — 唯一 writer) │
  ├─────────────────────────────────────────────────────┤
  │ [S23] aging_system         (serial)                 │
  ├─────────────────────────────────────────────────────┤
  │ World Maintenance (serial spine)                     │
  │ [S24] decay_system          (serial)                 │
  ├─────────────────────────────────────────────────────┤
  │ [S25] death_cleanup        (serial, reads DeathMark) │
  │ [S26] pvp_block_system     (serial)                 │
  │ [S27] room_state_system    (serial)                 │
  │ [S28] controller_system    (serial, phase 2b part)  │
  │ [S29] resource_ledger      (serial, per §08)        │
  └─────────────────────────────────────────────────────┘
```

**共计 25 个 registered Pass 2b systems，加上 6 个 Pass 2a inline handlers，combined total 为 31**，共同进入 `system_manifest_hash`。**A01 action_dispatch 是 System Pass 2a 的独立 ActionRegistry fixed hook，不是 manifest system、不计入 31 entries；其 handler set 进入 `world_action_manifest_hash`**。S22 是 persistent special `StatusState` 的唯一 writer；Leech HP 由 S15 结算，Fabricate channel 由 S22 推进。

**关键修复**：
- **S22 移出 Parallel Set B**：作为串行唯一 StatusState writer，不再与其他 system 并行。
- **S16-S22b 只写 typed buffer**：S16-S21 产生 status effect buffers；S22a 把 S15 的 `LeechResolution` 规范化为 trace/bookkeeping buffer；S22b 产生 Fabricate channel buffer。S22 消费 status/Fabricate buffers，但不重新结算 Leech HP。
- **S01 不处理 combat**：`Attack`/`RangedAttack`/`Heal` 不再是 `CommandAction` variant，也不由 S01 写 `HitPoints` 或 `Entity(hits)`；combat action 由 A01 action_dispatch 校验后写入 `PendingDamage`/`PendingHeal` intent buffer。
- **A01 Action dispatch**：System Pass 2a sorted command loop 中 `CommandAction::Action { action_type, payload }` 的 per-command fixed hook——不是 manifest system。读取 `ActionRegistry` 查找 handler → validate/apply。vanilla/custom handler identity 与 schema 进入 `world_action_manifest_hash`，不进入 `system_manifest_hash`。
- **S14 从 ActionRegistry intent buffer 读取**：Reducer 从 action handler 产生的 special intent buffer 读取 intent → merge sort → reducer resolve → 分流到 S15/S22。

---

## 2. System Details

### System Pass 2a: Inline Command Handlers (S01–S06)

> **System Pass 2a 内联执行**：这些系统在命令循环中逐条 inline 调用。每条命令按 kind 恰好 dispatch 到 S01-S06 或 A01 中的一个 handler。S01-S06 order 进入 `system_manifest_hash`；A01 registry/handler identity 进入 `world_action_manifest_hash`。

### S01: command_executor
- **ID**: `cmd_exec`
- **Pass**: 2a inline
- **Handled Commands**: `Move`, `Harvest`
- **Reads**: CommandQueue, WorldConfig, PlayerState, Drone, Room, Entity (owner, position)
- **Writes**: Drone (position, fatigue), ResourceAmount, EventLog, ResourceLedger
- **Must run before**: S02
- **Iteration key**: `(player_order, player_id, sequence, command_id)` where `command_id = Blake3(canonical RawCommand)`
- **Note**: Per-drone per-tick action quota enforced inline: max 1 main action per drone. Transfer/Withdraw 不计入但受 carry 容量约束。S01 不再处理 `Attack`/`RangedAttack`/`Heal` 或任何 special action，不写 `HitPoints`/`Entity(hits)`；combat 类 action 只能通过 A01 handler 写 `PendingDamage`/`PendingHeal` intent 到 combat buffer，实际 HP 修改由 S15 统一执行。

### A01: action_dispatch (System Pass 2a per-command handler — not a manifest system)
- **ID**: `action_dispatch`
- **Pass**: 2a inline, independent of S01
- **Handled Commands**: `CommandAction::Action { action_type, payload }`
- **Reads**: CommandQueue, ActionRegistry, WorldConfig, PlayerState, Drone, Room, Entity (owner, position, status), ResourceAmount
- **Writes**: PendingDamage buffer, PendingHeal buffer, special intent buffer, ResourceAmount, EventLog
- **Must run after**: outer sorted-command-loop quota gate for the same command slot
- **Must run before**: S11-S15, S22
- **Dispatch contract**: after deserialization, resolve internal `action_type` against the built-in handlers or `CustomActionRegistry`; reject unknown/disabled action; decode `payload` against handler schema; run handler validation against current Bevy World; apply only through typed intent buffers or non-HP resource/event writes. Handlers must not write `HitPoints` directly.

### S02: controller_system (phase 2a)
- **ID**: `ctrl_2a`
- **Pass**: 2a inline
- **Handled Commands**: `ClaimController`, `UpgradeController`
- **Reads**: Controller, PlayerState, Room
- **Writes**: Controller (progress, level), Room (state)
- **Must run after**: S01
- **Must run before**: S03

### S03: build_system
- **ID**: `build`
- **Pass**: 2a inline
- **Handled Commands**: `Build` (Spawn, Extension, Tower, Storage, Depot, Road, Container, Link, Terminal, Observer, Extractor, Lab, Factory, PowerSpawn, Nuker), `Repair`
- **Reads**: ConstructionSite, Room, ResourceAmount, WorldConfig, Position, Owner, HitPoints, DeathMark, Entity type/body
- **Writes**: PendingEntityCreation buffer (accepted Build only), ConstructionSite (progress), ResourceAmount (cost deduction), PendingHeal buffer (accepted Repair only)
- **Entity creation**: ✅ — Build 写入 `PendingEntityCreation`，不在当前 tick 直接进入可交互实体集
- **Repair contract**: Repair 归属 S03，不新增 Pass2a handler。S03 必须校验 target 为 owned/friendly repairable entity、range ≤ 3、source drone 同时具备 Work+Carry、可支付 Energy、target 未带 DeathMark 且 `hits < hits_max`。Vanilla `repair_hp_per_work_part=5`、`repair_energy_per_hp=1`；按 `min(missing_hits, active_work_parts × 5, carried_energy)` 得到 accepted amount，扣除等量 Energy 并写入 `PendingHeal`。S03 绝不写 `HitPoints`；S15 是唯一 HP writer。

### S04: recycle_system
- **ID**: `recycle`
- **Pass**: 2a inline
- **Handled Commands**: `Recycle`
- **Reads**: Entity (drone/structure), ResourceAmount, Owner
- **Writes**: ResourceAmount (refund), Entity (DeathMark component)
- **Note**: 不立即 despawn。DeathMark 标记后走标准 death_cleanup 路径（S25）。RoomCap 在 S07 death_marker 中释放。

### S05: transfer_system
- **ID**: `transfer`
- **Pass**: 2a inline
- **Handled Commands**: `Transfer`, `Withdraw`, `TransferToGlobal`, `TransferFromGlobal`, `AlliedTransfer`
- **Reads**: ResourceAmount, Room, WorldConfig, ResourceLedger
- **Writes**: ResourceAmount (source → target), ResourceLedger
- **Linked to**: specs/core/resource-ledger.md
- **Note**: TransferToGlobal/FromGlobal 路由至 ResourceLedger GlobalDeposit/GlobalWithdraw 操作，分别受 `global_deposit_delay`(10 tick) 和 `global_withdraw_delay`(100 tick) 约束。AlliedTransfer 路由至 delayed allied transfer policy，执行 alliance/fee/cooldown/cap 校验。local Transfer/Withdraw 不受 global delay 影响。

### S06: spawn_validator
- **ID**: `spawn_val`
- **Pass**: 2a inline
- **Handled Commands**: `Spawn`
- **Reads**: Spawn, DroneTemplate, Room, ResourceAmount, PlayerState
- **Writes**: ResourceAmount (provisional body_cost debit), ProvisionalSpawnRequest buffer
- **Note**: System Pass 2a 只校验 stable facts（spawn owner、body schema、cost source、request identity 等）、预留/扣除 body_cost 并写入 `ProvisionalSpawnRequest`。S06 不写 `PendingEntityCreation`，不读写/消费 `RoomCap`，不 finalize cooldown。

---

### System Pass 2b: System Pass (S07–S29, including S22a/S22b)

### S07: death_marker
- **ID**: `death_mark`
- **fix**: 移至 spawn 之前，提前释放 RoomCap 槽位。
- **Reads**: Entity (hits ≤ 0), Drone (lifespan expired), Recycle DeathMark (from S04)
- **Writes**: DeathMark component, RoomCap (release slot)
- **Must run before**: S08 (spawn_system)
- **Note**: 所有死亡标记统一在此处理——Recycle/S04 标记、自然死亡、伤害致死。

### S08: spawn_system
- **ID**: `spawn`
- **fix**: 移至 death_marker 之后，使用已释放的 RoomCap 槽位。
- **Reads**: ProvisionalSpawnRequest buffer (from S06), DroneTemplate, Room, RoomCap, DeathMark, Spawn, ResourceAmount
- **Writes**: PendingEntityCreation buffer (accepted spawn only), ResourceAmount (refund rejected debit), Spawn (finalized cooldown), RoomCap (consume accepted slot), TickTrace spawn accept/refund records
- **Note**: S08 is the unique consumer of `ProvisionalSpawnRequest`. It rechecks volatile admission after S07 releases RoomCap, consumes RoomCap for accepted requests, finalizes cooldown, accepts/refunds the provisional debit, and appends accepted spawn requests to `PendingEntityCreation`. S08 never materializes ECS entities; tick-end creation flush is the unique `PendingEntityCreation` consumer/materializer.
- **Entity creation**: ✅ — 新 Drone 写入 `PendingEntityCreation`
- **Note**: RoomCap 在 S07 释放后立即可用，同 tick spawn 可完成准入与扣费，但创建结果本 tick 不可交互。

### S09: spawning_grace_system
- **ID**: `spawn_grace`
- **fix**: 移至 combat 之前，确保首次可交互 tick 无敌保护生效。
- **Reads**: Drone (newly interactive, spawning flag), Room
- **Writes**: SpawningGrace { remaining: 1 } component; removes expired grace before later ticks enter combat
- **Must run after**: S08 (spawn_system)
- **Must run before**: S11 (attack_system)
- **Note**: creation tick 的 pending drone 不在可见/可交互索引中。首次可交互 tick 由 S09 设置并保留 `SpawningGrace { remaining: 1 }`，使其免疫所有 combat/special/decay；再下一 tick S09 在 combat 前移除 grace，drone 才正常参与战斗。

### S10: regeneration_system
- **ID**: `regen`
- **fix**: 移至 damage_application 之前。自然回复先于伤害结算，防止 heal 与 regen 叠加双倍回复（double-dip）。
- **Reads**: Entity (hits, max_hits), Room
- **Writes**: PendingHeal buffer (natural regen intent)
- **Must run after**: S09
- **Must run before**: S15 (damage_application)
- **Filter**: `Without<DeathMark>` — 跳过已标记死亡的实体。

### S11-S13: Combat Parallel Set A

| System | ID | Reads | Writes (per-system sub-buffer) |
|--------|-----|-------|--------|
| attack_system | `atk` | Drone (pos, body), Entity (pos, hits) | **PendingDamage[target_id]** (damage value) |
| ranged_attack_system | `rng_atk` | Drone (pos, body), Entity (pos) | **PendingDamage[target_id]** (damage value) |
| heal_system | `heal` | Drone (pos), Entity (hits, max_hits) | **PendingHeal[target_id]** (heal amount) |

**Buffer 写入约定**：S11-S13 **不直接修改 Entity.hits**。三者消费 A01 action_dispatch 产生的 `PendingDamage` / `PendingHeal` intent，并可追加 Tower/DoT 等被动 combat intent；所有 combat/heal intent 由 S15 damage_application 统一归并写入 HitPoints。特殊 action intent 写入 special intent buffer，由 S14 收集并分流。

**Parallel safety**: 三个 system 按 `target_id` partition，同一 entity 只被一个 system 写入对应的 sub-buffer。`SpawningGrace` filter 在此层生效——新生 drone 被所有 combat system 跳过。

S11-S13 不产生特殊攻击 intent。特殊 action intent 由 A01 ActionRegistry handler 写入 special intent buffer。

### S14: special_attack_reducer
- **ID**: `spec_atk_red`
- **fix**: 从 A01 ActionRegistry handler 产生的 special intent buffer 读取 intents（非 S01/S11-S13）；不直接写 StatusState 或 HP。
- **Reads**: special intent buffer (from A01), Entity (status components — read-only for existing state reference), SpawningGrace
- **Writes**: `pending_status_intents` (canonical sorted + resolved) and `PendingLeechCombat { source, target, base_damage: 15, damage_type: Kinetic, heal_bps: 5000, sort_key }`
- **Processing pipeline**:
  1. **Collect**: A01 在 System Pass 2a dispatch 的 special action handler 产生的 intent 已入队 special intent buffer
  2. **Grace filter**: target/protected entity 带 `SpawningGrace` 的 intent 对玩家记录 `NotVisibleOrNotFound` rejection（无 target details/remaining ticks）；actor/source-owned `SpawningGrace` 在 A01 validation 阶段可记录 `CooldownActive`。出生保护期不接受任何 special effect
  3. **Merge sort**: 按 `(effect_priority, intent_source.entity_id, intent_target.entity_id)` 确定性归并排序
  4. **Reducer resolve**: 同一 target 的多个 intent 按 `design/gameplay.md` 定义的优先级链裁决：**Hack > Drain > Overload > Debilitate > Disrupt > Fortify > Leech > Fabricate**；冲突 intent 降级记录
  5. **Route**: `Hack/Drain/Overload/Debilitate/Disrupt/Fortify/Fabricate` 写入 `pending_status_intents` 交给 S22；`Leech` 写入 `PendingLeechCombat` 交给 S15
- **Must run after**: S11, S12, S13
- **Must run before**: S15, S22
- **Note**: 此 reducer **不直接修改实体状态**——仅负责 intent 归并、排序、路由。Leech 的 HP 变化由 S15 结算，其余 persistent special state 由 S22 推进。

### S15: damage_application (Combat HitPoints writer)

**S15 是 combat (damage + heal) HitPoints writer**。所有攻击/治疗的 HP 变化先写入 `PendingDamage`/`PendingHeal`/`PendingLeechCombat` typed buffer，再由 S15 统一 reduce + canonical key sort → 原子写入 `Entity.hits`。S10 regen → `PendingHeal`。S24 decay 是独立 world maintenance writer，串行执行于 S22/S23 之后。

Canonical key 归约：S15 把 `PendingDamage`、`PendingHeal` 和 `PendingLeechCombat` 放入 virtual HP ledger，按 `(target_id, source_id, sort_key)` 升序计算所有 contributions，再一次性写入每个 entity 的 `hits`。普通 damage/heal 可在同 key bucket 内整数归并；Leech 必须保留逐 intent 的 actual-damage accounting。这保证同一 entity 的 HitPoints 只在 S15 中被写入一次。

- **ID**: `dmg_apply`
- **HitPoints 写入契约**: **Combat (damage + heal) HitPoints writer** — S15 是战斗伤害/治疗（含 Leech）的统一 HitPoints 写入者。S10 regen → `PendingHeal`。S24 decay 是独立 world maintenance writer（`Without<DeathMark>` + `Without<SpawningGrace>` filters），在 S22→S23→S24 串行中执行。CI 验证：S10 不得直接写 HitPoints（必须走 buffer）；S24 的 HitPoints 写仅在 decay 域。
- **Reads**: PendingDamage buffer, PendingHeal buffer, PendingLeechCombat, Entity (hits, max_hits, armor, resistances), SpawningGrace
- **Writes**: Entity (hits), DeathMark (if hits ≤ 0), `LeechResolution { source, target, actual_damage, self_heal }`
- **Must run after**: S11, S12, S13, S14
- **Filter**: `Without<SpawningGrace>` — 跳过出生保护中的实体。**注意**: S15 亦需 `Without<DeathMark>` guard —— 已标记死亡的实体不应再接收伤害/治疗。此 guard 防止 S07-S08 区间的 DeathMark 实体因并行 race 被重复伤害应用。

**Leech settlement**：S15 将普通 combat intent 与 `PendingLeechCombat` 放入同一 canonical HP staging pass，按 `(target_id, source_id, sort_key)` 排序并在内存中的 virtual HP ledger 上计算，最后每个实体只写一次 `hits`。Leech 的 Kinetic 15 base damage 先经 armor/resistance/shield 得到 `mitigated_damage`，再计算 `scaled_damage = floor(mitigated_damage × damage_multiplier / 10000)`，最后以 `min(scaled_damage, target_virtual_remaining_hits)` 得到 `actual_damage`；`self_heal = floor(actual_damage * 5000 / 10000)`，再 cap 到 source `max_hits`。全程只用整数运算。S15 写 `LeechResolution` 供 trace/bookkeeping；S22 不得重新计算或应用 Leech HP。

### S16-S22b: Status/Resolution Buffer Production (Parallel Set B)

S16-S21 只读现有 StatusState 并写 typed effect buffer。S22a 只读 S15 的 `LeechResolution`，S22b 只读 `FabricateState` 与 channel inputs。S16-S22b 不直接修改 HP、实体或 StatusState；各自只写互不重叠的 typed buffer。

| System | ID | Reads | Writes (typed buffer) |
|--------|-----|-------|--------|
| hack_buffer | `hack_buf` | HackState, Entity (owner) | `HackBuffer { target, stage_delta }` |
| drain_buffer | `drain_buf` | DrainState, ResourceAmount | `DrainBuffer { target, amount }` |
| overload_buffer | `overload_buf` | OverloadState, FuelBudget | `OverloadBuffer { target, fuel_reduction }` |
| debilitate_buffer | `debuff_buf` | DebilitateState, ResistanceProfile | `DebilitateBuffer { target, damage_type, resistance_multiplier_bps, duration_delta }` |
| disrupt_buffer | `disrupt_buf` | DisruptState, Entity (action, body_parts) | `DisruptBuffer { target, interrupted }`；要求 action 与对应 body part 匹配 |
| fortify_buffer | `fort_buf` | FortifyState, Entity (armor) | `FortifyBuffer { target, armor_delta }` |
| leech_buffer | `leech_buf` | `LeechResolution` from S15 | `LeechBuffer { source, target, actual_damage, self_heal }`（trace/bookkeeping only） |
| fabricate_buffer | `fab_buf` | FabricateState, source/target Position, Owner, DeathMark | `FabricateBuffer { source, target, resolved_structure_type, channel_delta, complete }` |

**Parallel safety**: 各 system 写入互不重叠的 typed buffer（`HackBuffer` ≠ `DrainBuffer` ≠ …）。所有 buffer 与 HP/entity/StatusState component 分离——S16-S22b 不写这些 components，S15 是 combat HP writer，S22 是唯一 StatusState writer。无并行写入冲突。

### S22: status_advance_system (serial — 唯一 StatusState writer)

S22 移出 Parallel Set B，作为串行系统。**唯一写入**所有 StatusState component。

- **ID**: `status_adv`
- **Reads**: `pending_status_intents` (from S14), all typed buffers (`HackBuffer`/`DrainBuffer`/`OverloadBuffer`/`DebilitateBuffer`/`DisruptBuffer`/`FortifyBuffer`/`LeechBuffer`/`FabricateBuffer` from S16-S22b), existing StatusState, SpawningGrace, DeathMark, Owner
- **Writes**: **All persistent special StatusState components** (`HackState`, `DrainState`, `OverloadState`, `DebilitateState`, `DisruptState`, `FortifyState`, `FabricateState`), ResistanceProfile vulnerability overlay (Debilitate), Entity (armor/interrupted via effect application), ResourceAmount (drain), FuelBudget (overload), DeathMark and PendingEntityCreation (Fabricate completion only), trace/bookkeeping records
- **Must run after**: S14, S16-S22b
- **Must run before**: S23
- **Note**: 统一消费 S14 的 canonical sorted status intents 和 S16-S22b 的 typed buffers → 唯一推进 persistent special StatusState。作为防御性检查，target 带 `SpawningGrace` 时不应用 new intent 或 typed-buffer effect。`LeechBuffer` 只进入 trace/bookkeeping，绝不修改 HP/resources/age。
- **Fabricate timing**: 新 `FabricateState` 在 S22 Pass 1 创建；同 tick 的 S22b 已先执行，因此不会立即递减。首次 channel decrement 发生在下一 tick，连续完成 5 次 decrement 后才能 conversion。Disrupt priority 高于 Fabricate，S20/S22 在 completion 前看到 interrupt 时取消 channel。

### Status Advance Execution Order (per tick, within S22)

```
// Pass 1: Apply new intents from S14 (new status applications)
for each intent in pending_status_intents (canonically sorted):
    if intent.target has SpawningGrace: continue
    match intent.kind:
        Hack       → HackState.stage += 1; duration = hack_duration
        Drain      → ResourceAmount -= drain_amount; duration = drain_duration
        Overload   → FuelBudget.reduce(overload_amount); duration = overload_duration
        Debilitate → DebilitateState { damage_type, resistance_multiplier_bps: 20000, duration: 50 }
        Disrupt    → Entity.interrupted = true; duration = disrupt_duration
        Fortify    → Entity.armor += fortify_amount; duration = fortify_duration
        Fabricate  → FabricateState {
                         source, target, resolved_structure_type,
                         channel_remaining: 5,
                         started_at_tick: current_tick
                     }

// Pass 2a: Record instant Leech resolutions independently of StatusState
for each LeechBuffer in canonical (target, source) order:
    append deterministic LeechResolution trace only

// Pass 2b: Apply buffer effects from S16-S21/S22b (ongoing status/channel effects)
for each entity with active StatusState:
    if entity has SpawningGrace: continue
    if HackBuffer[entity] → apply hack stage progression
    if DrainBuffer[entity] → apply drain resource transfer
    if OverloadBuffer[entity] → apply fuel reduction
    if DebilitateBuffer[entity] → apply damage-type resistance vulnerability overlay
    if DisruptBuffer[entity] → apply interrupt flag; cancel FabricateState on that channeling source
    if FortifyBuffer[entity] → apply armor modifier
    if FabricateBuffer[entity]:
        if source/target invalid, range != 1, target not enemy Drone, or target has DeathMark/SpawningGrace:
            expire FabricateState without conversion
        else if FabricateBuffer[entity].complete:
            mark target DeathMark
            append replacement Structure { type: FabricateState.resolved_structure_type, owner: source.owner }
                to PendingEntityCreation with a new StableEntityId
        else:
            decrement channel_remaining by channel_delta

// Pass 3: Decrement durations + expire (Fabricate is advanced only by its buffer above)
for each active non-Fabricate StatusState:
    status.duration -= 1
    if status.duration == 0 → expire effect (reverse temporary modifiers)
```

### Special Attack Unique Writer Contract

每种 persistent special StatusState component 有且仅有一个写入者 system（S22）。S16-S22b 写入 typed buffer（非 StatusState），S14 写入 `pending_status_intents` 或 `PendingLeechCombat`。Leech 是 instant combat effect，不存在 `LeechState`。

| Status Component | 唯一 Writer (system_id) | 写入时机 |
|------------------|------------------------|---------|
| `HackState` | `status_adv` (S22) | S22 Pass 1 — apply S14 intents |
| `DrainState` | `status_adv` (S22) | S22 Pass 1 — apply S14 intents |
| `OverloadState` | `status_adv` (S22) | S22 Pass 1 — apply S14 intents |
| `DebilitateState` | `status_adv` (S22) | S22 Pass 1 — apply S14 intents |
| `DisruptState` | `status_adv` (S22) | S22 Pass 1 — apply S14 intents |
| `FortifyState` | `status_adv` (S22) | S22 Pass 1 — apply S14 intents |
| `FabricateState` | `status_adv` (S22) | S22 Pass 1 create channel; later ticks advance/cancel/complete from FabricateBuffer |
| `HackBuffer` | `hack_buf` (S16) | S16 S22 Pass 2 input |
| `DrainBuffer` | `drain_buf` (S17) | S17 S22 Pass 2 input |
| `OverloadBuffer` | `overload_buf` (S18) | S18 S22 Pass 2 input |
| `DebilitateBuffer` | `debuff_buf` (S19) | S19 S22 Pass 2 input |
| `DisruptBuffer` | `disrupt_buf` (S20) | S20 S22 Pass 2 input |
| `FortifyBuffer` | `fort_buf` (S21) | S21 S22 Pass 2 input |
| `LeechResolution` | `dmg_apply` (S15) | Actual Kinetic damage + capped 50% self-heal result |
| `LeechBuffer` | `leech_buf` (S22a) | Trace/bookkeeping copy of S15 resolution; no gameplay mutation |
| `FabricateBuffer` | `fab_buf` (S22b) | S22b S22 Pass 2 input |
| `StatusActionIntent` | `action_dispatch` (A01) | A01 System Pass 2a ActionRegistry handler execution |
| `pending_status_intents` / `PendingLeechCombat` | `spec_atk_red` (S14) | S14 merge sort + reducer + route split |
| Leech damage/self-heal | `dmg_apply` (S15) | Actual-damage settlement in canonical HP pass |
| Fabricate conversion | `status_adv` (S22) | DeathMark target + append replacement structure to PendingEntityCreation |

**Buffer 生命周期**：status/Fabricate typed buffers、`LeechBuffer` 和 `pending_status_intents` 在每个 tick 结束时由 S22 消费后清空；`PendingLeechCombat` 由 S15 消费，`LeechResolution` 由 S22a 消费。`PendingEntityCreation` 不属于 status buffer，由 tick-end creation flush 消费。跨 tick 的 special 状态仅存在于 persistent StatusState component 中。

### Mode Unlock Strategy (— vanilla action registry)

| Mode | Special Attacks | 理由 |
|------|:--------------:|------|
| Tutorial | 全部禁用 | 学习基础 Movement/Harvest/Build |
| Novice | 全部禁用 | 保护新手体验 |
| Standard | **全量启用** (Hack/Drain/Overload/Debilitate/Disrupt/Fortify/Leech/Fabricate) | 教程/SDK 强引导；学习者通过 code/docs 自学 |
| Arena | 全量启用 | 与 Standard 相同 |

全部 vanilla action 通过 ActionRegistry 暴露：3 种基础 combat action（Attack/RangedAttack/Heal）+ 8 种特殊 action（Hack/Drain/Overload/Debilitate/Disrupt/Fortify/Leech/Fabricate）。`CommandAction` 不再包含 combat variant；内部 IDL 使用 `Action { action_type, payload }`，wire `type` 为具体 action 名称。

### S23: aging_system
- **ID**: `aging`
- **Reads**: Drone (age, lifespan)
- **Writes**: Drone (age++), DeathMark (if age ≥ lifespan)
- **Must run after**: S22
- **Must run before**: S24

### S24: decay_system
- **ID**: `decay`
- **Reads**: Structure (hits), Drone (fatigue, cooldown), Room
- **Writes**: Structure (hits--), Drone (fatigue--, cooldown--)
- **Filter**: `Without<DeathMark>`, `Without<SpawningGrace>`
- **Note**: 疲劳与冷却的自然衰减。World Maintenance 属于 serial spine；decay 不与其他系统并行，数据竞争由固定排序消除。

### S25: death_cleanup
- **ID**: `death_cln`
- **Reads**: DeathMark
- **Writes**: Entity (despawn), ResourceAmount (drop)
- **Entity despawn**: ✅ (flushes pending_despawn queue in deterministic order by entity_id)
- **Must run after**: S24

### S26: pvp_block_system
- **ID**: `pvp_block`
- **Reads**: Room (pvp_enabled), PlayerState
- **Writes**: PvpBlock (new), EventLog
- **Must run after**: S25
- **Note**: 在 death_cleanup 之后执行，确保已死亡实体不参与 PvP 判定

### S27: room_state_system
- **ID**: `room_state`
- **Reads**: Room, Entity, Controller
- **Writes**: Room (state, controller_level), EventLog

### S28: controller_system (phase 2b)
- **ID**: `ctrl_p2b`
- **Reads**: Controller (progress, repair_range, repair_capacity), Depot (range, local_resources, repair_aging), Room, Drone (age, StableEntityId)
- **Writes**: Controller (progress, level_up_flag), PlayerState (gcl), Drone (age reduction), Depot local_resources, TickTrace age_repair events
- **Age repair order**: 每设施对 in-range drones 按 StableEntityId 升序取 capacity；Controller 免费，Depot 先扣本地 Energy；每次 repair 的 before/after age、facility_id 和 resource debit 写 TickTrace。

### S29: resource_ledger
- **ID**: `res_ledger`
- **Reads**: All ResourceAmount changes from S01-S28
- **Writes**: ResourceLedger (operations log, balance_delta, ledger_checksum)
- **Must run last**: ✅
- **Linked to**: specs/core/resource-ledger.md
- **Recurring settlement order**: `UpkeepDeduction → StorageTax → PvEAward → ControllerPassiveIncome → WreckageSalvage → PluginSettlement`; command-triggered operations已在 S01-S06 按 canonical RawCommand order inline 结算，S29 只汇总其 trace，不重排。

---

## 3. Entity Creation/Despawn Order

### 3.0 Entity Creation Visibility Contract

所有 accepted 实体创建路径统一写入 `PendingEntityCreation` queue：S03 追加 accepted Build，S08 追加 accepted Spawn，S22 追加 completed Fabricate replacement。S06 只写 `ProvisionalSpawnRequest`。Fabricate completion 由 S22 原子标记 enemy target drone 的 `DeathMark`，并以 source owner、resolved `Tower|Storage|Wall` type 追加 replacement structure；replacement 获得新的 `StableEntityId`。新实体的 ID 可在当前 tick 内预分配并进入事件/trace，但实体数据在本 tick 结束 flush 前不加入可交互世界索引。

| 标志 | 值 | 含义 |
|------|----|------|
| `visible_same_tick` | `false` | 同 tick 快照、查询、后续命令和系统扫描均不可见新实体 |
| `interactable_same_tick` | `false` | 同 tick 不能被移动、攻击、治疗、转移、建造依赖或作为 target 解析 |

- **Creation**: 所有 accepted 新实体追加到 `PendingEntityCreation`，不立即可见/不可交互。tick-end creation flush 不属于 31 combined system/handler entries，是 `PendingEntityCreation` 的唯一 consumer/materializer；它在当前 tick 所有 system 执行完毕后按 `StableEntityId` 排序 materialize accepted Build/Spawn/Fabricate，从下一 tick 开始参与快照、命令校验和系统迭代。
- **Despawn**: 标记 `DeathMark` 但不立即移除。S25 收集所有 DeathMark 实体，按 StableEntityId 字节序升序 despawn；StableEntityId 不复用。
- **同一实体先 Despawn 后 Create**: 新 entity 获得新的 `StableEntityId`，不与替换前 ID 冲突。
- **RoomCap 生命周期**: S06 不接触 RoomCap；S07 `death_marker` 释放槽位 → S08 `spawn_system` 重新校验并消费 accepted spawn 槽位。此区间内 RoomCap 处于中间态——其他 system 不得读取 RoomCap 做准入决策。

### 3.1 EntityId 分配器确定性契约

- `EntityId` 分配器为 **per-world 顺序单调递增**：新 entity 的 `StableEntityId = last_allocated_id + 1`，不依赖 HashMap 迭代顺序或 allocator 内部状态。
- 跨 tick 分配保持连续（不跨 tick 跳跃），不回收已 despawn 实体的 ID。
- **CI replay 验证**：随机采样 tick，对比两次独立 replay 的 entity 创建顺序与 `StableEntityId` 分配——必须逐位一致。

### 3.2 S22 实体迭代顺序

S22 `status_advance_system` 迭代实体顺序：`sorted(entities_with_active_status, StableEntityId)`。即先收集所有携带任意 active `StatusState` component 的实体，按 `StableEntityId` 升序迭代推进。此排序保证跨 replay / 跨平台确定性，不依赖 Bevy archetype 内部顺序。

---

## 4. Component R/W Matrix（25 registered Pass 2b + 6 Pass 2a inline = 31 combined）

以下矩阵定义每个 system 对核心 Component 的读写关系。`R`=只读，`W`=写入，`-`=不访问。`SpecAtkIntent` 列表示 A01 产生的 special action intent；`StatusState` 和 `SpecBuffer` 列拆分。

| System (S##) | `Position` | `HitPoints` | `Fatigue` | `Energy/Carry` | `Cooldown` | `RoomCap` | `DeathMark` | `Owner` | `SpawningGrace` | `Controller` | `SpecAtkIntent` | `SpecBuffer` | `StatusState` | `ResourceLedger` |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **S01 cmd_exec** | W | - | W | W | - | - | - | R | - | - | - | - | - | W |
| **S02 ctrl_2a** | - | - | - | - | - | - | - | R | - | W | - | - | - | - |
| **S03 build** | R | R | - | W | - | - | R | R | - | - | - | W | - | - |
| **S04 recycle** | - | - | - | W | - | - | W | R | - | - | - | - | - | - |
| **S05 transfer** | - | - | - | W | - | - | - | R | - | - | - | - | - | W |
| **S06 spawn_val** | - | - | - | W | - | - | - | R | - | - | - | - | - | - |
| **S07 death_mark** | - | R | - | - | - | W | W | R | - | - | - | - | - | - |
| **S08 spawn** | - | - | - | W | W | W | R | R | - | - | - | - | - | - |
| **S09 spawn_grace** | - | - | - | - | - | - | - | - | W | - | - | - | - | - |
| **S10 regen** | - | R | - | - | - | - | - | - | - | - | - | - | - | - |
| **S11 atk** | R | - | - | - | - | - | - | R | R | - | - | - | - | - |
| **S12 rng_atk** | R | - | - | - | - | - | - | R | R | - | - | - | - | - |
| **S13 heal** | R | - | - | - | - | - | - | R | R | - | - | - | - | - |
| **S14 spec_atk_red** | - | - | - | - | - | - | - | R | R | - | **R** | **W** | **R** | - |
| S15 dmg_apply | - | W | - | - | - | - | W | - | R | - | - | **R/W** | - | - |
| **S16 hack_buf** | - | - | - | - | - | - | - | R | - | - | - | **W** | **R** | - |
| **S17 drain_buf** | - | - | - | W | - | - | - | - | - | - | - | **W** | **R** | - |
| **S18 overload_buf** | - | - | - | W | - | - | - | - | - | - | - | **W** | **R** | - |
| **S19 debuff_buf** | - | - | - | - | - | - | - | - | - | - | - | **W** | **R** | - |
| **S20 disrupt_buf** | - | - | - | - | - | - | - | - | - | - | - | **W** | **R** | - |
| **S21 fort_buf** | - | - | - | - | - | - | - | - | - | - | - | **W** | **R** | - |
| **S22a leech_buf** | - | - | - | - | - | - | - | - | - | - | - | **R/W** | - | - |
| **S22b fab_buf** | R | - | - | - | - | - | R | R | - | - | - | **W** | **R** | - |
| **S22 status_adv** | R | R | - | W | - | - | W | R | R | - | - | **R** | **W** | - |
| **S23 aging** | - | - | - | - | - | - | W | - | - | - | - | - | - | - |
| **S24 decay** | - | W | W | - | W | - | - | - | R | - | - | - | - | - |
| **S25 death_cln** | - | - | - | W | - | - | W | - | - | - | - | - | - | - |
| **S26 pvp_block** | - | - | - | - | - | - | - | R | - | - | - | - | - | - |
| **S27 room_state** | - | - | - | - | - | - | - | R | - | W | - | - | - | - |
| **S28 ctrl_p2b** | - | - | - | - | - | - | - | R | - | W | - | - | - | - |
| **S29 res_ledger** | - | - | - | R | - | - | - | - | - | - | - | - | - | W |

> **Multi-writer HitPoints contract**: HitPoints 由两个独立 writer 按严格串行顺序写入，无竞争：
> - **S10 regen** → `PendingHeal` buffer → S15 结算（不直接写 HitPoints）
> - **S15 dmg_apply** → combat damage + heal + regen + Repair + Leech 统一结算写入 HitPoints
> - **S24 decay** → world maintenance decay (Structure hits--)，在 S15/S22/S23 之后执行，S24 的 HP 写与 combat 域分离
>
> CI 验证规则：S10 对 HitPoints 的 matrix entry 为 R（只读，写操作必须走 buffer）；S15 为 W（combat domain）；S24 为 W（decay domain，`Without<DeathMark>` + `Without<SpawningGrace>` filter）。S15→S22→S23→S24 串行执行保证无数据竞争。

**Column legend**:
- `SpecAtkIntent` = special action intent buffer — A01 writes, S14 reads
- `SpecBuffer` = routed combat/special inputs and typed buffers (`PendingHeal`, `PendingLeechCombat`, `LeechResolution`, `HackBuffer`/.../`FabricateBuffer`) — S03/S10/S14/S15/S16-S22b produce or consume by contract; S22 reads only status/Fabricate buffers and Leech bookkeeping
- `StatusState` = persistent special status components (`HackState`/`DrainState`/.../`FabricateState`; no `LeechState`) — S14/S16-S22b may read, **S22 is the ONLY writer**
- `PendingEntityCreation` is a queue rather than a Component column. S03 may append accepted Build, S08 may append accepted Spawn after consuming `ProvisionalSpawnRequest`, and S22 may append only a completed Fabricate replacement; tick-end creation flush remains its sole consumer/materializer and sits outside the 31 combined entries.
- `ProvisionalSpawnRequest` is a queue owned by S06/S08: S06 is the only writer, S08 is the only consumer. It is not visible to snapshots, command validation, MCP, or ECS entity scans.

**并行安全证明**：

- **Combat Parallel Set A (S11-S13)**: 按 `target_id` partition，同一 entity 只被一个 system 写入。`SpawningGrace` 列为 `R`（只读 filter，不修改）。
- **Status/Resolution Buffer Production Parallel Set B (S16-S22b)**: 各 system 写入互不重叠的 typed buffer。S16-S21/S22b 只读 StatusState，S22a 只读 LeechResolution；零并行写入冲突。
- **S22 serial unique writer**: S22 是唯一 persistent special StatusState writer——读取 status/Fabricate buffers 后串行推进；Leech HP 已由 S15 完成，S22 只记录 resolution。
- **World Maintenance (S24 decay)**: `HitPoints` 和 `Fatigue` 列在该阶段仅 decay 访问——S10 regen 已完成并通过 S15 结算，无数据竞争。
- **RoomCap 中间态保护**: S07→S08 之间无其他 system 读取 RoomCap。

---

## 5. Manifest Hash

每次 engine 版本发布时计算：

```
system_manifest_hash = Blake3(
    system_id_1 || version_1 ||
    system_id_2 || version_2 ||
    ...
    system_id_31 || version_31
)
```

上述 31 个 hash entries 是 6 个 Pass 2a inline handler entries + 25 个 registered Pass 2b system entries；实现注册表必须分别验证两个子集合及 combined order。

`system_manifest_hash` 进入 TickTrace。ActionRegistry/A01 handler set 单独进入 `world_action_manifest_hash`；A01 不增加 system entry，也不改变本系统清单的固定顺序。

---

## 6. CI 验证

| 检查项 | 方法 |
|--------|------|
| R/W 冲突检测 | 静态分析 6 个 Pass 2a inline handlers + 25 个 registered Pass 2b systems（31 combined）的 Component access（基于 §4 矩阵） |
| 并行安全 | 验证 parallel set 内 system 无共享写入；验证 RoomCap 中间态区间无 reader；验证 S22 是唯一 StatusState writer |
| 迭代确定性 | CI 在 `--release` 和 `--debug` 下比较 `state_checksum` |
| Manifest 一致性 | 分别验证 25 个 registered Pass 2b systems、6 个 Pass 2a inline handlers 与 31-entry combined order |
| SpawningGrace filter | 验证 S11-S15、S22 和 S24 读取/过滤 `SpawningGrace`；S14 丢弃 special intents，S22 不应用 new/buffer effects，S24 不执行 decay |
| Unique Writer | 验证仅 S22 写入 StatusState；CI 拒绝任何其他 system 的 StatusState 写操作 |
| Buffer 生命周期 | 验证 S15 清空 `PendingLeechCombat`，S22a 清空 `LeechResolution`，S22 清空 status/Fabricate buffers 与 `pending_status_intents`；`PendingEntityCreation` 仅由 tick-end flush 清空 |

---

## 7. 版本

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 |  | 修复：初始版本。27 system，serial spine + 3 parallel sets。 |
| 2.0.0 |  | 修复：6 个 Pass 2a inline handlers + 25 个 registered Pass 2b systems = 31 combined；增加 S14 special_attack_reducer、S06 spawn_validator。 |
| 3.0.0 |  | **修复**：Persistent Status Effects 拆分为 Parallel Set B buffer production + S22 串行唯一 StatusState committer。S22a 处理 LeechResolution bookkeeping，S22b 处理 Fabricate channel buffer；Leech HP 由 S15 结算，Fabricate conversion 走 PendingEntityCreation。A01 ActionRegistry handler 写入 special intent，S14 归并后分流。 |
