# Phase 2b System Manifest — ECS 权威调度

> **R15 B2 修复**。本文档是 Swarm 引擎 Phase 2b 系统执行顺序的**唯一权威定义**。所有其他文档（engine.md、01-tick-protocol.md、02-command-validation.md）引用此处，不得重新声明可冲突的系统列表或顺序。

## 原则

1. **Serial Spine + Parallel Sets**：核心管线为串行顺序，声明为 parallel 的 set 内系统可并行。
2. **Stable IDs**：每个 system 有固定 `system_id` 和 `version`，manifest hash 进入 TickTrace。
3. **显式迭代顺序**：所有系统内实体迭代按 `StableEntityId` 或 canonical key 排序，不依赖 Bevy archetype order。
4. **R/W 声明**：每个 system 声明 reads 和 writes 的 Component/Resource 集合，CI 验证无数据竞争。

---

## 1. System Schedule (20 systems)

```
Serial Spine:
  ┌─────────────────────────────────────────────────────┐
  │ Phase 2b Pre-processing                             │
  │ [S01] command_executor     (serial)                 │
  │ [S02] controller_system    (serial)                 │
  │ [S03] spawn_system         (serial)                 │
  │ [S04] build_system         (serial)                 │
  │ [S05] recycle_system       (serial)                 │
  │ [S06] transfer_system      (serial)                 │
  ├─────────────────────────────────────────────────────┤
  │ Parallel Set A: Combat                               │
  │ [S07] attack_system        ┐                        │
  │ [S08] ranged_attack_system  ├─ parallel              │
  │ [S09] heal_system           ┘  (disjoint entities)   │
  ├─────────────────────────────────────────────────────┤
  │ [S10] damage_application   (serial, reduces A)      │
  │ [S11] death_marker         (serial)                 │
  ├─────────────────────────────────────────────────────┤
  │ Parallel Set B: Status Effects                       │
  │ [S12] hack_system          ┐                        │
  │ [S13] drain_system          │                        │
  │ [S14] overload_system       ├─ parallel              │
  │ [S15] debilitate_system     │  (disjoint targets)    │
  │ [S16] disrupt_system        │                        │
  │ [S17] fortify_system        │                        │
  │ [S18] status_advance_system ┘                        │
  ├─────────────────────────────────────────────────────┤
  │ [S19] aging_system         (serial)                 │
  ├─────────────────────────────────────────────────────┤
  │ Parallel Set C: World Maintenance                    │
  │ [S20] regeneration_system  ┐                        │
  │ [S21] decay_system          ├─ parallel              │
  │ [S22] spawning_grace_system ┘  (disjoint components) │
  ├─────────────────────────────────────────────────────┤
  │ [S23] death_cleanup        (serial, reads DeathMark) │
  │ [S24] pvp_block_system     (serial)                 │
  │ [S25] room_state_system    (serial)                 │
  │ [S26] controller_system    (serial, phase 2b part)  │
  │ [S27] resource_ledger      (serial, per §08)        │
  └─────────────────────────────────────────────────────┘
```

**共计 27 个 system**（含 Resource Ledger）。所有特殊攻击状态推进由 `status_advance_system` 统一处理，不分散到各攻击 system。

---

## 2. System Details

### S01: command_executor
- **ID**: `cmd_exec`
- **Reads**: CommandQueue, WorldConfig, PlayerState, Drone, Room
- **Writes**: Drone (position, resources), Structure (hits), ResourceAmount, EventLog
- **Must run before**: S02
- **Iteration key**: `command.sequence` (stable)

### S02: controller_system
- **ID**: `ctrl_tick`
- **Reads**: Controller, PlayerState
- **Writes**: Controller (progress, level, downgrade_timer)
- **Must run after**: S01
- **Must run before**: S03

### S03: spawn_system
- **ID**: `spawn`
- **Reads**: Spawn, DroneTemplate, Room
- **Writes**: Drone (new), Spawn (cooldown), ResourceAmount
- **Entity creation**: ✅ — 新 Drone 追加到 `pending_entities`

### S04: build_system
- **ID**: `build`
- **Reads**: ConstructionSite, Room, ResourceAmount
- **Writes**: Structure (new), ConstructionSite (progress)
- **Entity creation**: ✅

### S05: recycle_system
- **ID**: `recycle`
- **Reads**: Entity (drone/structure), ResourceAmount
- **Writes**: ResourceAmount (refund), Entity (DeathMark)
- **Entity despawn**: ✅ (marks for S23 cleanup)

### S06: transfer_system
- **ID**: `transfer`
- **Reads**: ResourceAmount, Room, WorldConfig
- **Writes**: ResourceAmount (source → target), ResourceLedger
- **Linked to**: specs/core/08-resource-ledger.md

### S07-S09: Combat Parallel Set A
| System | ID | Reads | Writes |
|--------|-----|-------|--------|
| attack_system | `atk` | Drone (pos, body), Entity (pos, hits) | Entity (hits) |
| ranged_attack_system | `rng_atk` | Drone (pos, body), Entity (pos) | Entity (hits) |
| heal_system | `heal` | Drone (pos), Entity (hits, max_hits) | Entity (hits) |

**Parallel safety**: 三个 system 按 `target_id` partition，同一 entity 只被一个 system 写入。Reduce 后由 S10 统一应用。

### S10: damage_application
- **ID**: `dmg_apply`
- **Reads**: PendingDamage buffer (from S07-S09), Entity (armor, resistances)
- **Writes**: Entity (hits), DeathMark
- **Must run after**: S07, S08, S09

### S11: death_marker
- **ID**: `death_mark`
- **Reads**: Entity (hits ≤ 0), Drone (lifespan expired)
- **Writes**: DeathMark component
- **Must run before**: S23

### S12-S18: Status Effects Parallel Set B
| System | ID | Reads | Writes |
|--------|-----|-------|--------|
| hack_system | `hack` | HackState, Entity | HackState (stage++) |
| drain_system | `drain` | DrainState, ResourceAmount | ResourceAmount (drain) |
| overload_system | `overload` | OverloadState, FuelBudget | FuelBudget (reduce) |
| debilitate_system | `debuff` | DebilitateState, Entity (efficiency) | Entity (efficiency) |
| disrupt_system | `disrupt` | DisruptState, Entity (action) | Entity (interrupted) |
| fortify_system | `fort` | FortifyState, Entity (armor) | Entity (armor) |
| status_advance_system | `status_adv` | All StatusState components | StatusState (duration--, expire) |

**Parallel safety**: 各 system 操作互不重叠的 Component 集合。`status_advance_system` 只读不写非 status 组件，与其他 status system 无冲突（不同 component）。

### S19: aging_system
- **ID**: `aging`
- **Reads**: Drone (age, lifespan)
- **Writes**: Drone (age++), DeathMark (if age ≥ lifespan)
- **Must run after**: S18
- **Must run before**: S20

### S20-S22: World Maintenance Parallel Set C
| System | ID | Reads | Writes |
|--------|-----|-------|--------|
| regeneration_system | `regen` | Entity (hits, max_hits), Room | Entity (hits) |
| decay_system | `decay` | Structure (hits), Room | Structure (hits) |
| spawning_grace_system | `spawn_grace` | SpawningGrace, Room | SpawningGrace (timer--) |

**Parallel safety**: 操作互不重叠的 Component/Entity 集合。

### S23: death_cleanup
- **ID**: `death_cln`
- **Reads**: DeathMark
- **Writes**: Entity (despawn), ResourceAmount (drop)
- **Entity despawn**: ✅ (flushes pending_despawn queue in deterministic order by entity_id)

### S24: pvp_block_system
- **ID**: `pvp_block`
- **Reads**: Room (pvp_enabled), PlayerState
- **Writes**: PvpBlock (new), EventLog
- **Must run after**: S23
- **Note**: 在 death_cleanup 之后执行，确保已死亡实体不参与 PvP 判定

### S25: room_state_system
- **ID**: `room_state`
- **Reads**: Room, Entity, Controller
- **Writes**: Room (state, controller_level), EventLog

### S26: controller_system (phase 2b)
- **ID**: `ctrl_p2b`
- **Reads**: Controller (progress), Room
- **Writes**: Controller (progress, level_up_flag), PlayerState (gcl)

### S27: resource_ledger
- **ID**: `res_ledger`
- **Reads**: All ResourceAmount changes from S01-S26
- **Writes**: ResourceLedger (operations log, balance_delta, ledger_checksum)
- **Must run last**: ✅
- **Linked to**: specs/core/08-resource-ledger.md

---

## 3. Entity Creation/Despawn Order

- **Creation**: 所有新实体追加到 `pending_entities`，不立即可见。在当前 tick 所有 system 执行完毕后 flush（按 `StableEntityId` 排序）。
- **Despawn**: 标记 `DeathMark` 但不立即移除。S23 收集所有 DeathMark 实体，按 `entity_id` 降序 despawn（避免 ID 复用问题）。
- **同一实体先 Despawn 后 Create**: 新 entity 获得新的 `StableEntityId`，不与旧 ID 冲突。

---

## 4. Manifest Hash

每次 engine 版本发布时计算：

```
manifest_hash = Blake3(
    system_id_1 || version_1 ||
    system_id_2 || version_2 ||
    ...
    system_id_27 || version_27
)
```

`manifest_hash` 进入 TickTrace (§6 TickTrace Envelope, `system_manifest_hash`)。

---

## 5. CI 验证

| 检查项 | 方法 |
|--------|------|
| R/W 冲突检测 | 静态分析所有 system 的 Component access |
| 并行安全 | 验证 parallel set 内 system 无共享写入 |
| 迭代确定性 | CI 在 `--release` 和 `--debug` 下比较 `state_checksum` |
| Manifest 一致性 | 验证代码中的 system 注册与本文档匹配 |

---

## 6. 版本

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2026-06-18 | R15 B2 修复：初始版本。27 system，serial spine + 3 parallel sets。修复 `status_advance_system`/`aging_system` 缺失，明确 pvp_block 位置。 |
