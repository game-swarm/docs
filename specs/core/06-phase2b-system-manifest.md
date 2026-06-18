# Complete Tick Execution Manifest — 权威调度

> 详见 design/engine.md
>
> **R16 B2 修复**。本文档是 Swarm 引擎**全部 tick 系统执行顺序的唯一权威定义**——覆盖 Phase 2a inline 命令处理器与 Phase 2b 被动系统。所有其他文档（engine.md、01-tick-protocol.md、02-command-validation.md）引用此处，不得重新声明可冲突的系统列表或顺序。

## 原则

1. **Phase 2a + Phase 2b 统一清单**：本文档覆盖 tick 执行的全部系统，Phase 2a inline 处理器与 Phase 2b 被动系统在同一时间线中明确定义。
2. **Serial Spine + Parallel Sets**：核心管线为串行顺序，声明为 parallel 的 set 内系统可并行。
3. **Stable IDs**：每个 system 有固定 `system_id` 和 `version`，manifest hash 进入 TickTrace。
4. **显式迭代顺序**：所有系统内实体迭代按 `StableEntityId` 或 canonical key 排序，不依赖 Bevy archetype order。
5. **R/W 声明**：每个 system 声明 reads 和 writes 的 Component/Resource 集合，CI 验证无数据竞争。

---

## 1. System Schedule (29 systems)

```
Serial Spine:
  ┌─────────────────────────────────────────────────────┐
  │ Phase 2a: Inline Command Handlers (serial)           │
  │ [S01] command_executor     (Move/Harvest/Attack/    │
  │                             RangedAttack/Heal/Claim) │
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
  │ Parallel Set B: Status Effects                       │
  │ [S16] hack_system          ┐                        │
  │ [S17] drain_system          │                        │
  │ [S18] overload_system       ├─ parallel              │
  │ [S19] debilitate_system     │  (disjoint targets)    │
  │ [S20] disrupt_system        │  (body part match req) │
  │ [S21] fortify_system        │                        │
  │ [S22] status_advance_system ┘                        │
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

**共计 29 个 system**（含 Phase 2a inline 处理器 + Phase 2b 被动系统 + Resource Ledger）。所有特殊攻击状态推进由 `status_advance_system` 统一处理，不分散到各攻击 system。

**关键时序修复**（R16 B2）：
- **death_marker 在 spawn 之前**：RoomCap 槽位同 tick 释放 → spawn 可立即使用。
- **spawning_grace 在 combat 之前**：新生 drone 获得出生 tick 无敌保护（`SpawningGrace { remaining: 1 }`），免疫所有敌对操作。
- **regeneration 在 damage_application 之前**：自然回复先于伤害结算，防止 heal 与 regen 叠加双倍回复。
- **special_attack_reducer**：parallel intent 收集 → `pending_intents` buffer → canonical priority sort → 交付 `status_advance_system`。

---

## 2. System Details

### Phase 2a: Inline Command Handlers (S01–S06)

> **Phase 2a 内联执行**：这些系统在命令循环中逐条 inline 调用。每条命令校验基于**当前 Bevy World 状态**，合法则立即应用。所有效果在后续同一 tick 的系统可见。

### S01: command_executor
- **ID**: `cmd_exec`
- **Phase**: 2a inline
- **Handled Commands**: `Move`, `Harvest`, `Attack`, `RangedAttack`, `Heal`, `Claim`
- **Reads**: CommandQueue, WorldConfig, PlayerState, Drone, Room, Entity (owner, position, hits)
- **Writes**: Drone (position, fatigue), Entity (hits), ResourceAmount, EventLog
- **Must run before**: S02
- **Iteration key**: `command.sort_key` (priority_class, shuffle_index, source_rank, sequence, command_hash)
- **Note**: Per-drone per-tick action quota enforced inline: max 1 main action per drone. Transfer/Withdraw 不计入但受 carry 容量约束。

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
- **Writes**: Structure (new), ConstructionSite (progress), ResourceAmount (cost deduction)
- **Entity creation**: ✅ (immediate, inline — structure appears in current tick)

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
- **Handled Commands**: `Transfer`, `Withdraw`
- **Reads**: ResourceAmount, Room, WorldConfig, ResourceLedger
- **Writes**: ResourceAmount (source → target), ResourceLedger
- **Linked to**: specs/core/08-resource-ledger.md

### S06: spawn_validator
- **ID**: `spawn_val`
- **Phase**: 2a inline
- **Handled Commands**: `Spawn`
- **Reads**: Spawn, DroneTemplate, Room, ResourceAmount, PlayerState
- **Writes**: Spawn (cooldown), ResourceAmount (body_cost deduction), PendingSpawn buffer
- **Note**: Phase 2a 仅校验 + 扣费 + 入队 `PendingSpawn`。实际 drone 创建由 Phase 2b S08 spawn_system 执行。同 tick 后续命令不可见待创建 drone。

---

### Phase 2b: Deferred Systems (S07–S29)

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
- **Writes**: Drone (new entity), ResourceAmount (finalize)
- **Entity creation**: ✅ — 新 Drone 追加到 `pending_entities`
- **Note**: RoomCap 在 S07 释放后立即可用，同 tick spawn 无需等待。

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
- **Writes**: Entity (hits++, capped at max_hits)
- **Must run after**: S09
- **Must run before**: S15 (damage_application)
- **Filter**: `Without<DeathMark>` — 跳过已标记死亡的实体。

### S11-S13: Combat Parallel Set A
| System | ID | Reads | Writes |
|--------|-----|-------|--------|
| attack_system | `atk` | Drone (pos, body), Entity (pos, hits) | Entity (hits) |
| ranged_attack_system | `rng_atk` | Drone (pos, body), Entity (pos) | Entity (hits) |
| heal_system | `heal` | Drone (pos), Entity (hits, max_hits) | Entity (hits) |

**Parallel safety**: 三个 system 按 `target_id` partition，同一 entity 只被一个 system 写入。Reduce 后由 S15 统一应用。`SpawningGrace` filter 在此层生效——新生 drone 被所有 combat system 跳过。

### S14: special_attack_reducer
- **ID**: `spec_atk_red`
- **Reads**: PendingSpecialAttack intents buffer (from S11-S13), Entity (status components)
- **Writes**: `pending_intents` buffer (canonical sorted), StatusState (seeded)
- **Processing pipeline (R22 B3 — 完整执行表)**:
  1. **Parallel collect**: S11-S13 产生的特殊攻击 intent（Hack/Drain/Overload/Debilitate/Disrupt/Fortify）写入 per-system sub-buffer
  2. **Merge sort**: 收集所有 sub-buffer → 按 `(priority_class, intent_source.entity_id, intent_target.entity_id)` 确定性归并排序（serial collector，禁止依赖 nondeterministic push order）
  3. **Reducer resolve**: 同一 target 的多个 intent 按优先级链裁决（Hack > Drain > Overload > Debilitate > Disrupt > Fortify）；冲突 intent 降级记录
  4. **Deliver to S22**: 排序+裁决后的 intents 交付 `status_advance_system` 统一推进
  5. **Status advance (S22)**: 统一读入 intents → 更新 StatusState（duration--, expire, apply）→ 触发 damage/application
  6. **Damage application (S15)**: 特殊攻击产生的 damage 通过 `damage_application` 统一应用
- **Must run after**: S11, S12, S13
- **Must run before**: S22
- **Note**: 此 reducer 不直接修改实体状态——仅负责 intent 归并、排序、路由。实际状态变更由 S22 `status_advance_system` 执行。

### S15: damage_application
- **ID**: `dmg_apply`
- **Reads**: PendingDamage buffer (from S11-S13), Entity (armor, resistances)
- **Writes**: Entity (hits), DeathMark (if hits ≤ 0)
- **Must run after**: S11, S12, S13, S14
- **Filter**: `Without<SpawningGrace>` — 跳过出生保护中的实体。

### S16-S22: Status Effects Parallel Set B
| System | ID | Reads | Writes |
|--------|-----|-------|--------|
| hack_system | `hack` | HackState, Entity | HackState (stage++) |
| drain_system | `drain` | DrainState, ResourceAmount | ResourceAmount (drain) |
| overload_system | `overload` | OverloadState, FuelBudget | FuelBudget (reduce) |
| debilitate_system | `debuff` | DebilitateState, Entity (efficiency) | Entity (efficiency) |
| disrupt_system | `disrupt` | DisruptState, Entity (action), Entity (body_parts) | Entity (interrupted) — **要求 body part match**（R23 D3/A） |
| fortify_system | `fort` | FortifyState, Entity (armor) | Entity (armor) |
| status_advance_system | `status_adv` | All StatusState components, pending_intents (from S14) | StatusState (duration--, expire, apply intents) |

**Parallel safety**: 各 system 操作互不重叠的 Component 集合。`status_advance_system` 读取 S14 输出的 canonical sorted intents 并统一推进，不与其他 status system 冲突（不同 component）。

### Special Attack Unique Writer Contract (R22 B3)

每种 status/component 有且仅有一个写入者 system。禁止多路径写同一状态：

| Status Component | 唯一 Writer (system_id) | 写入时机 |
|------------------|------------------------|---------|
| `HackState` | `status_adv` (S22) | status_advance 统一推进 |
| `DrainState` | `status_adv` (S22) | status_advance 统一推进 |
| `OverloadState` | `status_adv` (S22) | status_advance 统一推进 |
| `DebilitateState` | `status_adv` (S22) | status_advance 统一推进 |
| `DisruptState` | `status_adv` (S22) | status_advance 统一推进 |
| `FortifyState` | `status_adv` (S22) | status_advance 统一推进 |
| `PendingIntents` buffer | `spec_atk_red` (S14) | intent collect + merge sort |
| Damage from special attack | `dmg_apply` (S15) | damage_application 统一处理 |

**并发写入结构**: S11-S13 各自写入 per-system sub-buffer（线程局部，无竞争）。S14 serial collector 读取所有 sub-buffer → merge sort → 写入 canonical `pending_intents`。**禁止依赖 nondeterministic push order。**

### Status Advance Execution Order (per tick, within S22)

```
for each intent in pending_intents (canonically sorted):
    match intent.kind:
        Hack       → HackState.stage += 1; duration = hack_duration
        Drain      → ResourceAmount -= drain_amount; duration = drain_duration
        Overload   → FuelBudget.reduce(overload_amount); duration = overload_duration
        Debilitate → Entity.efficiency *= debilitate_factor; duration = debilitate_duration
        Disrupt    → Entity.interrupted = true; duration = disrupt_duration
        Fortify    → Entity.armor += fortify_amount; duration = fortify_duration

    // Decrement all active status durations
    for each active StatusState:
        status.duration -= 1
        if status.duration == 0 → expire effect (reverse temporary modifiers)
```

### Mode Unlock Strategy (D4/B 裁决 — Standard 全量启用)

| Mode | Special Attacks | 理由 |
|------|:--------------:|------|
| Tutorial | 全部禁用 | 学习基础 Movement/Harvest/Build |
| Novice | 全部禁用 | 保护新手体验 |
| Standard | **全量启用** (Hack/Drain/Overload/Debilitate/Disrupt/Fortify) | 教程/SDK 强引导；学习者通过 code/docs 自学 |
| Arena | 全量启用 | 与 Standard 相同 |

Standard 模式下 special attack 全量可用。教程 (`swarm_get_docs`) 和 SDK 模板提供分阶段学习路径，但不限制引擎能力。

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
- **Note**: 疲劳与冷却的自然衰减。Paralel Set C 简化为单一 serial system（decay 不与其他系统并行数据竞争已由之前排序保证）。

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

- **Creation**: 所有新实体追加到 `pending_entities`，不立即可见。在当前 tick 所有 system 执行完毕后 flush（按 `StableEntityId` 排序）。
- **Despawn**: 标记 `DeathMark` 但不立即移除。S25 收集所有 DeathMark 实体，按 `entity_id` 降序 despawn（避免 ID 复用问题）。
- **同一实体先 Despawn 后 Create**: 新 entity 获得新的 `StableEntityId`，不与旧 ID 冲突。
- **RoomCap 生命周期**: S07 `death_marker` 释放槽位 → S08 `spawn_system` 消费槽位。此区间内 RoomCap 处于中间态——其他 system 不得读取 RoomCap 做准入决策。

---

## 4. Component R/W Matrix（全部 29 systems）

以下矩阵定义每个 system 对核心 Component 的读写关系。`R`=只读，`W`=写入，`-`=不访问。

| System (S##) | `Position` | `HitPoints` | `Fatigue` | `Energy/Carry` | `Cooldown` | `RoomCap` | `DeathMark` | `Owner` | `SpawningGrace` | `Controller` | `StatusState` | `ResourceLedger` |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **S01 cmd_exec** | W | W | W | W | - | - | - | R | - | - | - | - |
| **S02 ctrl_2a** | - | - | - | - | - | - | - | R | - | W | - | - |
| **S03 build** | W | W | - | W | - | - | - | W | - | - | - | - |
| **S04 recycle** | - | - | - | W | - | - | W | R | - | - | - | - |
| **S05 transfer** | - | - | - | W | - | - | - | R | - | - | - | W |
| **S06 spawn_val** | - | - | - | W | - | R | - | R | - | - | - | - |
| **S07 death_mark** | - | R | - | - | - | W | W | R | - | - | - | - |
| **S08 spawn** | W | W | - | W | W | W | - | W | - | - | - | - |
| **S09 spawn_grace** | - | - | - | - | - | - | - | - | W | - | - | - |
| **S10 regen** | - | W | - | - | - | - | - | - | - | - | - | - |
| **S11 atk** | R | W | - | - | - | - | - | R | R | - | - | - |
| **S12 rng_atk** | R | W | - | - | - | - | - | R | R | - | - | - |
| **S13 heal** | R | W | - | - | - | - | - | R | R | - | - | - |
| **S14 spec_atk_red** | - | - | - | - | - | - | - | R | - | - | W | - |
| **S15 dmg_apply** | - | W | - | - | - | - | W | - | R | - | - | - |
| **S16 hack** | - | - | - | - | - | - | - | R | - | - | W | - |
| **S17 drain** | - | - | - | W | - | - | - | - | - | - | W | - |
| **S18 overload** | - | - | - | W | - | - | - | - | - | - | W | - |
| **S19 debuff** | - | - | - | - | - | - | - | - | - | - | W | - |
| **S20 disrupt** | - | - | - | - | - | - | - | - | - | - | W | - |
| **S21 fort** | - | - | - | - | - | - | - | - | - | - | W | - |
| **S22 status_adv** | - | - | - | - | - | - | - | - | - | - | W | - |
| **S23 aging** | - | - | - | - | - | - | W | - | - | - | - | - |
| **S24 decay** | - | W | W | - | W | - | - | - | - | - | - | - |
| **S25 death_cln** | - | - | - | W | - | - | W | - | - | - | - | - |
| **S26 pvp_block** | - | - | - | - | - | - | - | R | - | - | - | - |
| **S27 room_state** | - | - | - | - | - | - | - | R | - | W | - | - |
| **S28 ctrl_p2b** | - | - | - | - | - | - | - | R | - | W | - | - |
| **S29 res_ledger** | - | - | - | R | - | - | - | - | - | - | - | W |

**并行安全证明**：

- **Combat Parallel Set A (S11-S13)**: 按 `target_id` partition，同一 entity 只被一个 system 写入。`SpawningGrace` 列为 `R`（只读 filter，不修改）。
- **Status Effects Parallel Set B (S16-S22)**: 各 system 写入互不重叠的 `StatusState` subtype（HackState ≠ DrainState ≠ OverloadState...）。`status_advance_system` 读取 S14 的 `pending_intents` 并统一写入所有 `StatusState`，与其他 system 无冲突（不同 component 实例）。
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
    system_id_29 || version_29
)
```

`manifest_hash` 进入 TickTrace (§6 TickTrace Envelope, `system_manifest_hash`)。

---

## 6. CI 验证

| 检查项 | 方法 |
|--------|------|
| R/W 冲突检测 | 静态分析所有 29 system 的 Component access（基于 §4 矩阵） |
| 并行安全 | 验证 parallel set 内 system 无共享写入；验证 RoomCap 中间态区间无 reader |
| 迭代确定性 | CI 在 `--release` 和 `--debug` 下比较 `state_checksum` |
| Manifest 一致性 | 验证代码中的 system 注册与本文档匹配（29 systems） |
| SpawningGrace filter | 验证所有 combat 系统（S11-S15）使用 `Without<SpawningGrace>` filter |

---

## 7. 版本

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2026-06-18 | R15 B2 修复：初始版本。27 system，serial spine + 3 parallel sets。修复 `status_advance_system`/`aging_system` 缺失，明确 pvp_block 位置。 |
| 2.0.0 | 2026-06-18 | R16 B2 修复：**Complete Tick Execution Manifest**——覆盖 Phase 2a inline 处理器 + Phase 2b 被动系统。29 systems。新增 `special_attack_reducer` (S14)、`spawn_validator` (S06)。修复时序：death_mark→spawn、spawning_grace→combat 之前、regeneration→damage_application 之前。新增 Component R/W 矩阵覆盖全部 29 systems。 |
