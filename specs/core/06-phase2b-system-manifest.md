# Complete Tick Execution Manifest — 权威调度

> 详见 design/engine.md
>
> **R16 B2 修复**。本文档是 Swarm 引擎**全部 tick 系统执行顺序的唯一权威定义**——覆盖 Phase 2a inline 命令处理器与 Phase 2b 被动系统。所有其他文档（engine.md、01-tick-protocol.md、02-command-validation.md）引用此处，不得重新声明可冲突的系统列表或顺序。
>
> **R35 D3 修复**：Status Effects 拆分为「并行 buffer 生产」(S16-S21) + 「串行唯一 committer」(S22)。S22 移出 Parallel Set B。combat 与特殊攻击不再由 S01 直接处理：Attack/RangedAttack/Heal 经 Action dispatch 进入 combat intent buffer，special actions 经 ActionRegistry handler 进入 status intent buffer。

## 原则

1. **Phase 2a + Phase 2b 统一清单**：本文档覆盖 tick 执行的全部系统，Phase 2a inline 处理器与 Phase 2b 被动系统在同一时间线中明确定义。
2. **Serial Spine + Parallel Sets**：核心管线为串行顺序，声明为 parallel 的 set 内系统可并行。
3. **Stable IDs**：每个 system 有固定 `system_id` 和 `version`，manifest hash 进入 TickTrace。
4. **显式迭代顺序**：所有系统内实体迭代按 `StableEntityId` 或 canonical key 排序，不依赖 Bevy archetype order。
5. **R/W 声明**：每个 system 声明 reads 和 writes 的 Component/Resource 集合，CI 验证无数据竞争。
6. **Unique Writer Contract**：每种 status/component 有且仅有一个 system 写入。并行 set 内系统只写 typed buffer，不直接写 StatusState。

---

## 1. System Schedule (31 systems)

```
Serial Spine:
  ┌─────────────────────────────────────────────────────┐
  │ Phase 2a: Inline Command Handlers (serial)           │
  │ [S01] command_executor     (Move/Harvest/Transfer/  │
  │                             Withdraw/Build/Spawn/   │
  │                             Recycle/Claim/Global)   │
  │ [A01] action_dispatch      (ActionRegistry dispatch)│
  │ [S02] controller_system    (phase 2a inline)        │
  │ [S03] build_system         (Build)                  │
  │ [S04] recycle_system       (Recycle → DeathMark)    │
  │ [S05] transfer_system      (Transfer/Withdraw)      │
  │ [S06] spawn_validator      (validate, no creation)  │
  ├─────────────────────────────────────────────────────┤
  │ Phase 2b: Deferred Systems                           │
  │ [S07] death_marker         (serial, frees RoomCap)  │
  │ [S08] spawn_system         (serial, creates drones) │
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
  │ Parallel Set B: Status Effect Buffer Production      │
  │ ┌─ S16-S21 只读 StatusState，写 typed buffer ─┐     │
  │ │ [S16] hack_buffer          ┐                   │   │
  │ │ [S17] drain_buffer          │                   │   │
  │ │ [S18] overload_buffer       ├─ parallel         │   │
  │ │ [S19] debilitate_buffer     │  (disjoint types) │   │
  │ │ [S20] disrupt_buffer        │                   │   │
  │ │ [S21] fortify_buffer        │                   │   │
  │ │ [S22a] leech_buffer         │  (new — R30 B1)   │   │
  │ │ [S22b] fabricate_buffer     ┘  (new — R30 B1)   │   │
  │ └────────────────────────────────────────────────┘   │
  ├─────────────────────────────────────────────────────┤
  │ [S22] status_advance_system  (serial — 唯一 writer) │
  ├─────────────────────────────────────────────────────┤
  │ [S23] aging_system         (serial)                 │
  ├─────────────────────────────────────────────────────┤
  │ Parallel Set C: World Maintenance                    │
  │ [S24] decay_system          (serial within C)        │
  ├─────────────────────────────────────────────────────┤
  │ [S25] death_cleanup        (serial, reads DeathMark) │
  │ [S26] pvp_block_system     (serial)                 │
  │ [S27] room_state_system    (serial)                 │
  │ [S28] controller_system    (serial, phase 2b part)  │
  │ [S29] resource_ledger      (serial, per §08)        │
  └─────────────────────────────────────────────────────┘
```

**共计 31 个 system**（R30 B1: 新增 S22a leech_buffer + S22b fabricate_buffer，共 31）。所有特殊攻击状态推进由 `status_advance_system` (S22) **唯一**串行处理——S16-S22b 只写 typed buffer，不直接修改 StatusState。

**R35 D3 关键修复**：
- **S22 移出 Parallel Set B**：作为串行唯一 StatusState writer，不再与其他 system 并行。
- **S16-S22b 只写 typed buffer**：`HackBuffer`/`DrainBuffer`/`OverloadBuffer`/`DebilitateBuffer`/`DisruptBuffer`/`FortifyBuffer`/`LeechBuffer`/`FabricateBuffer`——由 S22 统一消费并写 StatusState。
- **S01 不处理 combat**：`Attack`/`RangedAttack`/`Heal` 不再是 `CommandAction` variant，也不由 S01 写 `HitPoints` 或 `Entity(hits)`；combat action 由 A01 action_dispatch 校验后写入 `PendingDamage`/`PendingHeal` intent buffer。
- **A01 Action dispatch**：Phase 2a 中独立于 S01 运行，读取 `CommandAction::Action { type, payload }` → `ActionRegistry` 查找 handler → validate/apply。vanilla action（3 basic combat + 8 special）统一走 registry 元数据校验。
- **S14 从 ActionRegistry intent buffer 读取**：Reducer 从 action handler 产生的 status intent buffer 读取 intent → merge sort → reducer resolve → 交付 S22。

---

## 2. System Details

### Phase 2a: Inline Command Handlers (S01–S06)

> **Phase 2a 内联执行**：这些系统在命令循环中逐条 inline 调用。每条命令校验基于**当前 Bevy World 状态**，合法则立即应用。所有效果在后续同一 tick 的系统可见。

### S01: command_executor
- **ID**: `cmd_exec`
- **Phase**: 2a inline
- **Handled Commands**: `Move`, `Harvest`, `Transfer`, `Withdraw`, `Build`, `Spawn`, `Recycle`, `ClaimController`, `TransferToGlobal`, `TransferFromGlobal`
- **Reads**: CommandQueue, WorldConfig, PlayerState, Drone, Room, Entity (owner, position)
- **Writes**: Drone (position, fatigue), ResourceAmount, EventLog, PendingSpawn buffer, DeathMark component, ResourceLedger
- **Must run before**: S02
- **Iteration key**: `command.sort_key` (priority_class, shuffle_index, source_rank, sequence, command_hash)
- **Note**: Per-drone per-tick action quota enforced inline: max 1 main action per drone. Transfer/Withdraw 不计入但受 carry 容量约束。S01 不再处理 `Attack`/`RangedAttack`/`Heal` 或任何 special action，不写 `HitPoints`/`Entity(hits)`；combat 类 action 只能通过 A01 handler 写 `PendingDamage`/`PendingHeal` intent 到 combat buffer，实际 HP 修改由 S15 统一执行。

### A01: action_dispatch (Phase 2a registry dispatch)
- **ID**: `action_dispatch`
- **Phase**: 2a inline, independent of S01
- **Handled Commands**: `CommandAction::Action { type, payload }`
- **Reads**: CommandQueue, ActionRegistry, WorldConfig, PlayerState, Drone, Room, Entity (owner, position, status), ResourceAmount
- **Writes**: PendingDamage buffer, PendingHeal buffer, status intent buffer, ResourceAmount, EventLog
- **Must run after**: S01 command sorting / quota gate for the same command slot
- **Must run before**: S11-S15, S22
- **Dispatch contract**: resolve `type` in `ActionRegistry`; reject unknown/disabled action; decode `payload` against handler schema; run handler validation against current Bevy World; apply only through typed intent buffers or non-HP resource/event writes. Handlers must not write `HitPoints` directly.

### S02: controller_system (phase 2a)
- **ID**: `ctrl_2a`
- **Phase**: 2a inline
- **Handled Commands**: `Claim`, `UpgradeController`
- **Reads**: Controller, PlayerState, Room
- **Writes**: Controller (progress, level), Room (state)
- **Must run after**: S01
- **Must run before**: S03

### S03: build_system
- **ID**: `build`
- **Phase**: 2a inline
- **Handled Commands**: `Build` (Spawn, Extension, Tower, Storage, Depot, Road, Container, Link, Terminal, Observer, Extractor, Lab, Factory, PowerSpawn, Nuker)
- **Reads**: ConstructionSite, Room, ResourceAmount, WorldConfig
- **Writes**: PendingEntityCreation buffer, ConstructionSite (progress), ResourceAmount (cost deduction)
- **Entity creation**: ✅ — 写入 `PendingEntityCreation`，不在当前 tick 直接进入可交互实体集

### S04: recycle_system
- **ID**: `recycle`
- **Phase**: 2a inline
- **Handled Commands**: `Recycle`
- **Reads**: Entity (drone/structure), ResourceAmount, Owner
- **Writes**: ResourceAmount (refund), Entity (DeathMark component)
- **Note**: 不立即 despawn。DeathMark 标记后走标准 death_cleanup 路径（S25）。RoomCap 在 S07 death_marker 中释放。

### S05: transfer_system
- **ID**: `transfer`
- **Phase**: 2a inline
- **Handled Commands**: `Transfer`, `Withdraw`, `TransferToGlobal`, `TransferFromGlobal`
- **Reads**: ResourceAmount, Room, WorldConfig, ResourceLedger
- **Writes**: ResourceAmount (source → target), ResourceLedger
- **Linked to**: specs/core/08-resource-ledger.md
- **Note**: TransferToGlobal/FromGlobal 路由至 ResourceLedger GlobalDeposit/GlobalWithdraw 操作，分别受 `global_deposit_delay`(10 tick) 和 `global_withdraw_delay`(100 tick) 约束。local Transfer/Withdraw 不受 global delay 影响。

### S06: spawn_validator
- **ID**: `spawn_val`
- **Phase**: 2a inline
- **Handled Commands**: `Spawn`
- **Reads**: Spawn, DroneTemplate, Room, ResourceAmount, PlayerState
- **Writes**: Spawn (cooldown), ResourceAmount (body_cost deduction), PendingSpawn buffer
- **Note**: Phase 2a 仅校验 + 扣费 + 入队 `PendingSpawn`。实际 drone 创建由 Phase 2b S08 spawn_system 执行。同 tick 后续命令不可见待创建 drone。

---

### Phase 2b: Deferred Systems (S07–S31)

### S07: death_marker
- **ID**: `death_mark`
- **R16 B2 fix**: 移至 spawn 之前，提前释放 RoomCap 槽位。
- **Reads**: Entity (hits ≤ 0), Drone (lifespan expired), Recycle DeathMark (from S04)
- **Writes**: DeathMark component, RoomCap (release slot)
- **Must run before**: S08 (spawn_system)
- **Note**: 所有死亡标记统一在此处理——Recycle/S04 标记、自然死亡、伤害致死。

### S08: spawn_system
- **ID**: `spawn`
- **R16 B2 fix**: 移至 death_marker 之后，使用已释放的 RoomCap 槽位。
- **Reads**: PendingSpawn buffer (from S06), DroneTemplate, Room, RoomCap
- **Writes**: PendingEntityCreation buffer, ResourceAmount (finalize)
- **Entity creation**: ✅ — 新 Drone 写入 `PendingEntityCreation`
- **Note**: RoomCap 在 S07 释放后立即可用，同 tick spawn 可完成准入与扣费，但创建结果本 tick 不可交互。

### S09: spawning_grace_system
- **ID**: `spawn_grace`
- **R16 B2 fix**: 移至 combat 之前，确保出生 tick 无敌保护生效。
- **Reads**: Drone (newly spawned, spawning flag), Room
- **Writes**: SpawningGrace { remaining: 1 } component
- **Must run after**: S08 (spawn_system)
- **Must run before**: S11 (attack_system)
- **Note**: `SpawningGrace { remaining: 1 }` 使新生 drone 在当前 tick 免疫所有伤害（含特殊攻击和衰减）。下一 tick `remaining` 递减 → 0 后正常参与战斗。

### S10: regeneration_system
- **ID**: `regen`
- **R16 B2 fix**: 移至 damage_application 之前。自然回复先于伤害结算，防止 heal 与 regen 叠加双倍回复（double-dip）。
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

**Buffer 写入约定**：S11-S13 **不直接修改 Entity.hits**。三者消费 A01 action_dispatch 产生的 `PendingDamage` / `PendingHeal` intent，并可追加 Tower/DoT 等被动 combat intent；所有 combat/heal intent 由 S15 damage_application 统一归并写入 HitPoints。特殊 action intent 写入 status intent buffer，由 S14 收集。

**Parallel safety**: 三个 system 按 `target_id` partition，同一 entity 只被一个 system 写入对应的 sub-buffer。`SpawningGrace` filter 在此层生效——新生 drone 被所有 combat system 跳过。

**R35 D3**: S11-S13 不产生特殊攻击 intent。特殊 action intent 由 A01 ActionRegistry handler 写入 status intent buffer。

### S14: special_attack_reducer
- **ID**: `spec_atk_red`
- **R35 D3 fix**: 从 A01 ActionRegistry handler 产生的 status intent buffer 读取 intents（非 S01/S11-S13）；不直接写 StatusState。
- **Reads**: status intent buffer (from A01), Entity (status components — read-only for existing state reference)
- **Writes**: `pending_intents` buffer (canonical sorted + resolved)
- **Processing pipeline (R35 D3)**:
  1. **Collect**: A01 在 Phase 2a dispatch 的 special action handler 产生的 intent 已入队 status intent buffer
  2. **Merge sort**: 按 `(priority_class, intent_source.entity_id, intent_target.entity_id)` 确定性归并排序
  3. **Reducer resolve**: 同一 target 的多个 intent 按**唯一权威优先级链**裁决：**Hack > Drain > Overload > Debilitate > Disrupt > Fortify > Leech > Fabricate**（此为 Swarm 引擎中该优先级链的唯一定义）；冲突 intent 降级记录
  4. **Deliver to S22**: 排序+裁决后的 intents 交付 `status_advance_system` 统一推进
- **Must run after**: S11, S12, S13
- **Must run before**: S22
- **Note**: 此 reducer **不直接修改实体状态**——仅负责 intent 归并、排序、路由。实际状态变更由 S22 `status_advance_system` 串行执行。

### S15: damage_application (UNIQUE HitPoints writer)

**S15 是 HitPoints 的 UNIQUE 写入者**。所有伤害/治疗/自然回复/状态效果 HP 变化都先写入 `PendingDamage`/`PendingHeal` typed buffer，再由 S15 统一 reduce + canonical key sort → 原子写入 `Entity.hits`。不存在任何其他 system 直接修改 HitPoints。

Canonical key 归约：S15 对 `PendingDamage[target_id]` 和 `PendingHeal[target_id]` 按 `target_id` 升序归并——同 target 的 damage 先合并（`net_damage = Σ attack - Σ heal`），再一次性写入 `Entity.hits`。这保证同一 entity 的 HitPoints 只在 S15 中被写入一次。

- **ID**: `dmg_apply`
- **HitPoints 写入契约**: **UNIQUE WRITER** — S15 是唯一写 `Entity.hits` 的 system。CI 静态验证：任何其他 system 对 `HitPoints` 的写操作必须被拒绝。
- **Reads**: PendingDamage buffer, PendingHeal buffer, Entity (armor, resistances)
- **Writes**: Entity (hits), DeathMark (if hits ≤ 0)
- **Must run after**: S11, S12, S13, S14
- **Filter**: `Without<SpawningGrace>` — 跳过出生保护中的实体。**注意**: S15 亦需 `Without<DeathMark>` guard —— 已标记死亡的实体不应再接收伤害/治疗。此 guard 防止 S07-S08 区间的 DeathMark 实体因并行 race 被重复伤害应用。

### S16-S22b: Status Effect Buffer Production (Parallel Set B)

**R30 B1**: S16-S22b **只读**现有 StatusState，**只写** typed effect buffer。不直接修改任何 StatusState component。所有 buffer 由 S22 统一消费。

| System | ID | Reads | Writes (typed buffer) |
|--------|-----|-------|--------|
| hack_buffer | `hack_buf` | HackState, Entity (owner) | `HackBuffer { target, stage_delta }` |
| drain_buffer | `drain_buf` | DrainState, ResourceAmount | `DrainBuffer { target, amount }` |
| overload_buffer | `overload_buf` | OverloadState, FuelBudget | `OverloadBuffer { target, fuel_reduction }` |
| debilitate_buffer | `debuff_buf` | DebilitateState, Entity (efficiency) | `DebilitateBuffer { target, factor }` |
| disrupt_buffer | `disrupt_buf` | DisruptState, Entity (action, body_parts) | `DisruptBuffer { target, interrupted }` — **要求 body part match**（R23 D3/A） |
| fortify_buffer | `fort_buf` | FortifyState, Entity (armor) | `FortifyBuffer { target, armor_delta }` |
| leech_buffer | `leech_buf` | LeechState, ResourceAmount, Entity (age) | `LeechBuffer { target, resource_drain, age_transfer }` — **新增 (R30 B1)** |
| fabricate_buffer | `fab_buf` | FabricateState, Drone (body) | `FabricateBuffer { target, body_part_mod }` — **新增 (R30 B1)** |

**Parallel safety (R30 B1)**: 各 system 写入互不重叠的 typed buffer（`HackBuffer` ≠ `DrainBuffer` ≠ …）。所有 buffer 与 StatusState component 分离——S16-S22b 不写任何 StatusState，S22 作为唯一 StatusState writer 串行执行。无并行写入冲突。

### S22: status_advance_system (serial — 唯一 StatusState writer)

**R30 B1**: S22 移出 Parallel Set B，作为串行系统。**唯一写入**所有 StatusState component。

- **ID**: `status_adv`
- **Reads**: `pending_intents` (from S14), all typed buffers (`HackBuffer`/`DrainBuffer`/`OverloadBuffer`/`DebilitateBuffer`/`DisruptBuffer`/`FortifyBuffer`/`LeechBuffer`/`FabricateBuffer` from S16-S22b), existing StatusState
- **Writes**: **All StatusState components** (`HackState`, `DrainState`, `OverloadState`, `DebilitateState`, `DisruptState`, `FortifyState`, `LeechState`, `FabricateState`), PendingDamage buffer, Entity (armor/efficiency/interrupted via effect application), ResourceAmount (drain), FuelBudget (overload)
- **Must run after**: S14, S16-S22b
- **Must run before**: S23
- **Note**: 统一消费 S14 的 canonical sorted intents 和 S16-S22b 的 typed buffers → 唯一推进所有 StatusState（duration--, expire, apply new intents, apply buffer effects）。

### Status Advance Execution Order (per tick, within S22 — R30 B1)

```
// Phase 1: Apply new intents from S14 (new status applications)
for each intent in pending_intents (canonically sorted):
    match intent.kind:
        Hack       → HackState.stage += 1; duration = hack_duration
        Drain      → ResourceAmount -= drain_amount; duration = drain_duration
        Overload   → FuelBudget.reduce(overload_amount); duration = overload_duration
        Debilitate → Entity.efficiency *= debilitate_factor; duration = debilitate_duration
        Disrupt    → Entity.interrupted = true; duration = disrupt_duration
        Fortify    → Entity.armor += fortify_amount; duration = fortify_duration
        Leech      → PendingDamage += leech_damage; Entity.age += age_transfer; duration = leech_duration
        Fabricate  → Entity.body_parts.modify(fabricate_mod); duration = fabricate_duration

// Phase 2: Apply buffer effects from S16-S22b (ongoing status tick effects)
for each entity with active StatusState:
    if HackBuffer[entity] → apply hack stage progression
    if DrainBuffer[entity] → apply drain resource transfer
    if OverloadBuffer[entity] → apply fuel reduction
    if DebilitateBuffer[entity] → apply efficiency modifier
    if DisruptBuffer[entity] → apply interrupt flag
    if FortifyBuffer[entity] → apply armor modifier
    if LeechBuffer[entity] → enqueue PendingDamage + apply age transfer
    if FabricateBuffer[entity] → apply body part modification

// Phase 3: Decrement durations + expire
for each active StatusState:
    status.duration -= 1
    if status.duration == 0 → expire effect (reverse temporary modifiers)
```

### Special Attack Unique Writer Contract (R30 B1)

每种 StatusState component 有且仅有一个写入者 system（S22）。S16-S22b 写入 typed buffer（非 StatusState），S14 写入 `pending_intents` buffer。

| Status Component | 唯一 Writer (system_id) | 写入时机 |
|------------------|------------------------|---------|
| `HackState` | `status_adv` (S22) | S22 Phase 1 — apply S14 intents |
| `DrainState` | `status_adv` (S22) | S22 Phase 1 — apply S14 intents |
| `OverloadState` | `status_adv` (S22) | S22 Phase 1 — apply S14 intents |
| `DebilitateState` | `status_adv` (S22) | S22 Phase 1 — apply S14 intents |
| `DisruptState` | `status_adv` (S22) | S22 Phase 1 — apply S14 intents |
| `FortifyState` | `status_adv` (S22) | S22 Phase 1 — apply S14 intents |
| `LeechState` | `status_adv` (S22) | S22 Phase 1 — apply S14 intents **(R30 B1 新增)** |
| `FabricateState` | `status_adv` (S22) | S22 Phase 1 — apply S14 intents **(R30 B1 新增)** |
| `HackBuffer` | `hack_buf` (S16) | S16 S22 Phase 2 input |
| `DrainBuffer` | `drain_buf` (S17) | S17 S22 Phase 2 input |
| `OverloadBuffer` | `overload_buf` (S18) | S18 S22 Phase 2 input |
| `DebilitateBuffer` | `debuff_buf` (S19) | S19 S22 Phase 2 input |
| `DisruptBuffer` | `disrupt_buf` (S20) | S20 S22 Phase 2 input |
| `FortifyBuffer` | `fort_buf` (S21) | S21 S22 Phase 2 input |
| `LeechBuffer` | `leech_buf` (S22a) | S22a S22 Phase 2 input |
| `FabricateBuffer` | `fab_buf` (S22b) | S22b S22 Phase 2 input |
| `StatusActionIntent` | `action_dispatch` (A01) | A01 Phase 2a ActionRegistry handler execution |
| `pending_intents` (resolved) | `spec_atk_red` (S14) | S14 merge sort + reducer |
| Damage from special attack | `dmg_apply` (S15) | damage_application 统一处理 |

**Buffer 生命周期**：所有 typed buffer（HackBuffer 等）和 `pending_intents` 在每个 tick 结束时由 S22 消费后清空。不跨 tick 持久化。跨 tick 的状态仅存在于 StatusState component 中。

### Mode Unlock Strategy (R35 D3 — vanilla action registry)

| Mode | Special Attacks | 理由 |
|------|:--------------:|------|
| Tutorial | 全部禁用 | 学习基础 Movement/Harvest/Build |
| Novice | 全部禁用 | 保护新手体验 |
| Standard | **全量启用** (Hack/Drain/Overload/Debilitate/Disrupt/Fortify/Leech/Fabricate) | 教程/SDK 强引导；学习者通过 code/docs 自学 |
| Arena | 全量启用 | 与 Standard 相同 |

全部 vanilla action 通过 ActionRegistry 暴露：3 种基础 combat action（Attack/RangedAttack/Heal）+ 8 种特殊 action（Hack/Drain/Overload/Debilitate/Disrupt/Fortify/Leech/Fabricate）。`CommandAction` 不再包含 combat variant；IDL 只承载 `Action { type, payload }`。

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
- **Filter**: `Without<DeathMark>`
- **Note**: 疲劳与冷却的自然衰减。Parallel Set C 简化为单一 serial system（decay 不与其他系统并行数据竞争已由之前排序保证）。

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
- **Reads**: Controller (progress), Room
- **Writes**: Controller (progress, level_up_flag), PlayerState (gcl)

### S29: resource_ledger
- **ID**: `res_ledger`
- **Reads**: All ResourceAmount changes from S01-S28
- **Writes**: ResourceLedger (operations log, balance_delta, ledger_checksum)
- **Must run last**: ✅
- **Linked to**: specs/core/08-resource-ledger.md

---

## 3. Entity Creation/Despawn Order

### 3.0 Entity Creation Visibility Contract

所有实体创建路径（Build、Spawn、Fabricate、脚本化系统创建）统一写入 `PendingEntityCreation` queue。新实体的 `StableEntityId` 可在当前 tick 内预分配并进入事件/trace，但实体数据在本 tick 结束 flush 前不加入可交互世界索引。

| 标志 | 值 | 含义 |
|------|----|------|
| `visible_same_tick` | `false` | 同 tick 快照、查询、后续命令和系统扫描均不可见新实体 |
| `interactable_same_tick` | `false` | 同 tick 不能被移动、攻击、治疗、转移、建造依赖或作为 target 解析 |

- **Creation**: 所有新实体追加到 `PendingEntityCreation`，不立即可见/不可交互。在当前 tick 所有 system 执行完毕后 flush（按 `StableEntityId` 排序），从下一 tick 开始参与快照、命令校验和系统迭代。
- **Despawn**: 标记 `DeathMark` 但不立即移除。S25 收集所有 DeathMark 实体，按 `entity_id` 降序 despawn（避免 ID 复用问题）。
- **同一实体先 Despawn 后 Create**: 新 entity 获得新的 `StableEntityId`，不与旧 ID 冲突。
- **RoomCap 生命周期**: S07 `death_marker` 释放槽位 → S08 `spawn_system` 消费槽位。此区间内 RoomCap 处于中间态——其他 system 不得读取 RoomCap 做准入决策。

### 3.1 EntityId 分配器确定性契约

- `EntityId` 分配器为 **per-world 顺序单调递增**：新 entity 的 `StableEntityId = last_allocated_id + 1`，不依赖 HashMap 迭代顺序或 allocator 内部状态。
- 跨 tick 分配保持连续（不跨 tick 跳跃），不回收已 despawn 实体的 ID。
- **CI replay 验证**：随机采样 tick，对比两次独立 replay 的 entity 创建顺序与 `StableEntityId` 分配——必须逐位一致。

### 3.2 S22 实体迭代顺序

S22 `status_advance_system` 迭代实体顺序：`sorted(entities_with_active_status, StableEntityId)`。即先收集所有携带任意 active `StatusState` component 的实体，按 `StableEntityId` 升序迭代推进。此排序保证跨 replay / 跨平台确定性，不依赖 Bevy archetype 内部顺序。

---

## 4. Component R/W Matrix（全部 31 systems — R30 B1）

以下矩阵定义每个 system 对核心 Component 的读写关系。`R`=只读，`W`=写入，`-`=不访问。**R35 D3**: `SpecAtkIntent` 列表示 A01 产生的 status action intent；`StatusState` 和 `SpecBuffer` 列拆分。

| System (S##) | `Position` | `HitPoints` | `Fatigue` | `Energy/Carry` | `Cooldown` | `RoomCap` | `DeathMark` | `Owner` | `SpawningGrace` | `Controller` | `SpecAtkIntent` | `SpecBuffer` | `StatusState` | `ResourceLedger` |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **S01 cmd_exec** | W | - | W | W | - | - | W | R | - | W | - | - | - | W |
| **S02 ctrl_2a** | - | - | - | - | - | - | - | R | - | W | - | - | - | - |
| **S03 build** | W | W | - | W | - | - | - | W | - | - | - | - | - | - |
| **S04 recycle** | - | - | - | W | - | - | W | R | - | - | - | - | - | - |
| **S05 transfer** | - | - | - | W | - | - | - | R | - | - | - | - | - | W |
| **S06 spawn_val** | - | - | - | W | - | R | - | R | - | - | - | - | - | - |
| **S07 death_mark** | - | R | - | - | - | W | W | R | - | - | - | - | - | - |
| **S08 spawn** | W | W | - | W | W | W | - | W | - | - | - | - | - | - |
| **S09 spawn_grace** | - | - | - | - | - | - | - | - | W | - | - | - | - | - |
| **S10 regen** | - | W | - | - | - | - | - | - | - | - | - | - | - | - |
| **S11 atk** | R | - | - | - | - | - | - | R | R | - | - | - | - | - |
| **S12 rng_atk** | R | - | - | - | - | - | - | R | R | - | - | - | - | - |
| **S13 heal** | R | - | - | - | - | - | - | R | R | - | - | - | - | - |
| **S14 spec_atk_red** | - | - | - | - | - | - | - | R | - | - | **R** | - | **R** | - |
| S15 dmg_apply | - | W | - | - | - | - | W | - | R | - | - | - | - | - |
|   |   | **combat/heal domain** |   |   |   |   |   |   |   |   |   |   |   |

> **Domain-specific writer 注**: S15 是 combat damage + heal 的 unique HitPoints writer——仅处理攻击和治疗的 HP 变更。S10 regeneration 是独立 writer（自然回复，在 combat 之前执行）。S22 status_advance_system 是另一类 HP 修改者（特殊攻击效果如 Leech drain），通过 StatusState→HP 路径在 S22 内部实现。三者写入同一 HitPoints component 但操作不同语义域（combat/heal vs regen vs special attack effect），时序保证无竞争（S10→S15→S22 串行）。
| **S16 hack_buf** | - | - | - | - | - | - | - | R | - | - | - | **W** | **R** | - |
| **S17 drain_buf** | - | - | - | W | - | - | - | - | - | - | - | **W** | **R** | - |
| **S18 overload_buf** | - | - | - | W | - | - | - | - | - | - | - | **W** | **R** | - |
| **S19 debuff_buf** | - | - | - | - | - | - | - | - | - | - | - | **W** | **R** | - |
| **S20 disrupt_buf** | - | - | - | - | - | - | - | - | - | - | - | **W** | **R** | - |
| **S21 fort_buf** | - | - | - | - | - | - | - | - | - | - | - | **W** | **R** | - |
| **S22a leech_buf** | - | - | - | W | - | - | - | - | - | - | - | **W** | **R** | - |
| **S22b fab_buf** | - | - | - | - | - | - | - | - | - | - | - | **W** | **R** | - |
| **S22 status_adv** | - | W | - | W | - | - | - | - | - | - | - | **R** | **W** | - |
| **S23 aging** | - | - | - | - | - | - | W | - | - | - | - | - | - | - |
| **S24 decay** | - | W | W | - | W | - | - | - | - | - | - | - | - | - |
| **S25 death_cln** | - | - | - | W | - | - | W | - | - | - | - | - | - | - |
| **S26 pvp_block** | - | - | - | - | - | - | - | R | - | - | - | - | - | - |
| **S27 room_state** | - | - | - | - | - | - | - | R | - | W | - | - | - | - |
| **S28 ctrl_p2b** | - | - | - | - | - | - | - | R | - | W | - | - | - | - |
| **S29 res_ledger** | - | - | - | R | - | - | - | - | - | - | - | - | - | W |

**Column legend (R35 D3)**:
- `SpecAtkIntent` = status action intent buffer — A01 writes, S14 reads
- `SpecBuffer` = typed effect buffers (`HackBuffer`/`DrainBuffer`/.../`LeechBuffer`/`FabricateBuffer`) — S16-S22b write, S22 reads
- `StatusState` = all status components (`HackState`/`DrainState`/.../`LeechState`/`FabricateState`) — S14 reads (reference), S16-S22b read (reference), **S22 is the ONLY writer**

**并行安全证明 (R30 B1)**：

- **Combat Parallel Set A (S11-S13)**: 按 `target_id` partition，同一 entity 只被一个 system 写入。`SpawningGrace` 列为 `R`（只读 filter，不修改）。
- **Status Buffer Production Parallel Set B (S16-S22b)**: 各 system 写入互不重叠的 typed buffer（`HackBuffer` ≠ `DrainBuffer` ≠ …）。所有 system 只读 StatusState（不修改）。零并行写入冲突。
- **S22 serial unique writer**: S22 是唯一 StatusState writer——读取所有 buffer 后串行推进。无并行写入者与 S22 竞争。
- **World Maintenance (S24 decay)**: `HitPoints` 和 `Fatigue` 列在该阶段仅 decay 访问——S10 regen 已在之前完成且使用 `Without<DeathMark>` filter，无数据竞争。
- **RoomCap 中间态保护**: S07→S08 之间无其他 system 读取 RoomCap。

---

## 5. Manifest Hash

每次 engine 版本发布时计算：

```
manifest_hash = Blake3(
    system_id_1 || version_1 ||
    system_id_2 || version_2 ||
    ...
    system_id_31 || version_31
)
```

`manifest_hash` 进入 TickTrace (§6 TickTrace Envelope, `system_manifest_hash`)。ActionRegistry handler set/hash 单独进入 world manifest；`CommandAction::Action { type, payload }` 的 dispatch 边界不改变本系统清单的固定顺序。

---

## 6. CI 验证

| 检查项 | 方法 |
|--------|------|
| R/W 冲突检测 | 静态分析所有 31 system 的 Component access（基于 §4 矩阵） |
| 并行安全 | 验证 parallel set 内 system 无共享写入；验证 RoomCap 中间态区间无 reader；验证 S22 是唯一 StatusState writer |
| 迭代确定性 | CI 在 `--release` 和 `--debug` 下比较 `state_checksum` |
| Manifest 一致性 | 验证代码中的 system 注册与本文档匹配（31 systems） |
| SpawningGrace filter | 验证所有 combat 系统（S11-S15）使用 `Without<SpawningGrace>` filter |
| Unique Writer | 验证仅 S22 写入 StatusState；CI 拒绝任何其他 system 的 StatusState 写操作 |
| Buffer 生命周期 | 验证 S22 消费后所有 typed buffer 和 pending_intents 被清空 |

---

## 7. 版本

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2026-06-18 | R15 B2 修复：初始版本。27 system，serial spine + 3 parallel sets。 |
| 2.0.0 | 2026-06-18 | R16 B2 修复：31 systems。S14 special_attack_reducer、S06 spawn_validator。 |
| 3.0.0 | 2026-06-21 | **R30 B1 修复**：Status Effects 拆分——S16-S22b 并行 buffer 生产 + S22 串行唯一 StatusState committer。新增 S22a leech_buffer + S22b fabricate_buffer（31 systems）。S01 写入 PendingSpecialAttackIntent。8 种特殊攻击全部核心目标。S14 从 S01 读取 intents。Unique Writer Contract 完备化。 |