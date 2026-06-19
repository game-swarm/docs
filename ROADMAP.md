# Swarm Implementation ROADMAP

> 仅列出待实现变更。文件互斥：同一 Wave 内任务触碰的文件集完全不相交。
> 路径：`engine:` = `src/`，`sandbox:` = `/data/swarm/sandbox/`，`mod:` = `swarm/mod-*` 独立仓库，`docs:` = `/data/swarm/docs/`。
> 系统编号以 `specs/core/06-phase2b-system-manifest.md` 为权威来源。

---

## 当前状态审计 (2026-06-19)

| 类别 | 数量 | 说明 |
|------|:----:|------|
| ✅ 已完成 | 24 | P0-1~P0-6, P0-7~P0-8, P1-1~P1-4, P2-1, P2-4, P2-6, S07, S08, S27, S28, economy(688行), global_storage(189行), depot_repair(315行), controller_repair(244行,drone age), security(515行) |
| ⚠️ 部分/Stub | 10 | P3-1(274行), P3-6(267行), S09(21行), S10(43行), S15(28行), S24(88行), S25(9行), S26(19行), S29(0行), P4-1(623行) |
| ❌ 缺失 | 17 | P2-2,P2-3,P2-5,P2-7,P2-8, S14,S16-S23, P3-7,P3-8, P1-6,P1-7, P4-2~P4-5, P5-1~P5-7 |
| 📦 Mod 仓库 | 0 | 7 个已填充 mod.toml + 3×.rhai，已添加为 engine submodule |

> S07 death_marker、S08 spawn_system、S27 room_state_system(230行)、S28 controller_system(2b, 176行)、P0-6 snapshot(10 tests) 已完整实现，归入 ✅。
> S25 death_cleanup(9行) 归入 ⚠️ stub。S29 resource_ledger 为 per-tick ECS 系统，尚未实现，归入 ⚠️。
> P4-1 arena.rs 已有 623 行基础代码，归入 ⚠️。

---

## Wave 依赖图

```
W0 (Mod 仓库填充 + engine submodule)
 │
 ├─► W1 (P0-6)
 │     │
 │     ├─► W2 (P2-1) → W3 (P2-3) → W4 (P2-2) → W5 (P2-5) → W6 (P2-8)
 │     │
 │     └─► W7 (P3-1 ‖ P3-6) → W8 (S09+S10+S24+S26) → W9 (S14+S15)
 │              │
 │              └─► W10 (P3-7) → W11 (S16+S17+S18) → W12 (S19+S20+S21+S22)
 │                                        │
 │                                        └─► W13 (S23) → W14 (P3-8)
 │                                                             │
 │                                                             └─► W15 (P4-1~P4-7)
 │
 ├─► W16 (P1-6 ‖ P1-7 ‖ P2-7)
 │
 └─► W17 (P5-1~P5-7)
```

---

## Wave 0: 官方模组仓库初始化 ✅ (2026-06-19)

**仓库: 7 个 `swarm/mod-*` + `engine`** | **并行度: 7（独立仓库）+ 1（engine）**

> Mod 系统映射文件（`memory_upkeep_system.rs`、`npc_spawn_system.rs` 等）属于 infrastructure/mod 层，不在 tick manifest 29 系统（S01-S29）中。manifest 仅覆盖每 tick 执行的系统。

### T0a — 填充 7 个 mod 仓库

从 [`mod-template`](https://git.kagurazakalan.com/swarm/mod-template) 复制 scaffold → 定制各 mod 的 `mod.toml` + Rhai 脚本。

| 模组 | 默认 | engine 系统映射 | key config 参数 |
|------|:----:|------|------|
| `mod-empire-upkeep` | ✅ | `memory_upkeep_system.rs`, `controller_repair_system.rs` | `base_upkeep`, `room_soft_cap`, `repair_cap`, `distance_decay_bp`, `recycle_refund_base` |
| `mod-fog-of-war` | ✅ | `visibility.rs` | `fog_of_war`, `player_view`, `public_spectate` |
| `mod-resource-decay` | ❌ | `decay_system.rs` | `decay_rate`, `decay_threshold` |
| `mod-pve-spawning` | ✅ | `spawn_system.rs`, `spawning_grace_system.rs`, `npc_spawn_system.rs`, `pve.rs` | `spawn_rate`, `npc_types`, `difficulty_zones` |
| `mod-combat-core` | ✅ | `combat_system.rs`, `damage_application_system.rs`, `death_cleanup_system.rs`, `regeneration_system.rs` | `damage_multiplier`, `body_part_types` |
| `mod-special-attacks` | ✅ | S16-S22 status systems | `special_attacks_enabled`, `custom_actions` |
| `mod-depot-storage` | ✅ | `depot_repair_system.rs`, `global_storage_system.rs`, `cargo_in_transit_system.rs`, `drone_env_var_system.rs` | storage caps, transfer rates |

### T0b — engine 添加 submodule

**仓库: `engine`** | **文件: `.gitmodules`, `mods/`**

`git submodule add` 七个 mod 仓库到 `engine/mods/`。

**验收:** 每个 mod 有 `mod.toml` + 3 个 `.rhai`；`git submodule status` 显示 7 个子模块。

---

## Wave 1: P0-6 Snapshot 构建器 ✅ (2026-06-19)

**仓库: `engine`** | **并行度: 1**

| 文件 | `sim.rs` (72 行→完整), `tick.rs` (集成), `lib.rs` |
|------|------|
| 不触碰 | `world.rs`, `scheduler.rs`, `systems/mod.rs`, `components.rs`, `command.rs` |
| 规范 | `specs/core/09-snapshot-contract.md`, `specs/security/05-visibility.md`, `01-tick-protocol.md` §2.3 |

**实现:** `fog_of_war_filter()` (= `is_visible_to()`) + `collect_snapshot()` (= `build_snapshot()`) 在 `sim.rs`；COLLECT→[Snapshot]→EXECUTE 集成到 `tick.rs`。需覆盖：256KB 截断触发、确定性截断顺序（6 距离桶 + entity_id 字典序）、关键实体保护（5 类）、竞技降级标记（tick degraded）、omitted_count 分桶脱敏。
**验收:** ≥ 8 个 snapshot 测试

---

## Wave 2: P2-1 Resource Ledger

**仓库: `engine`** | **并行度: 1**

| 文件 | `resources.rs`, `economy.rs`, `world.rs` (`[resources]` 节), `lib.rs` |
|------|------|
| 不触碰 | `command.rs`, `scheduler.rs`, `systems/mod.rs`, `components.rs` |
| 规范 | `specs/core/08-resource-ledger.md` §1-§2 |

**实现:** Transfer Gateway + 定点费率 + Storage tax + `world.toml` 配置
**验收:** ≥ 5 个测试

---

## Wave 3: P2-3 PvE Budget

**仓库: `engine`** | **并行度: 1**

| 文件 | `pve.rs`, `world.rs` (`[pve_budget]`), `lib.rs` |
|------|------|
| 规范 | `specs/core/08-resource-ledger.md` §3 |

**实现:** 4 维 Budget（Global/Zone/Player/Event）+ 按比例分配产出
**验收:** ≥ 3 个测试

---

## Wave 4: P2-2 Empire Upkeep

**仓库: `engine`** | **并行度: 1**

| 文件 | `memory_upkeep_system.rs` (23行→完整), `world.rs` (`[empire_upkeep]`), `lib.rs` |
|------|------|
| 规范 | `specs/core/08-resource-ledger.md` §Empire Upkeep, §2.4, §2.5 |

**实现:**
1. 维护费公式: **`cost = base_upkeep × rooms × (1 + rooms / room_soft_cap)`**（参数从 `world.toml` `[empire_upkeep]` 读取，按模式可配置：Standard=50/10, Vanilla=30/10, Tutorial=10/5）
2. Controller Repair: `repair_cost = body_cost × (1 - repair_cap/10000) × (1 + distance × distance_decay_bp/10000)`。⚠️ 当前 `controller_repair_system.rs`(244行) 实现的是 drone age 修复——**需重写**为规范定义的 body repair 逻辑
3. Recycle Refund: `refund = body_cost × max(recycle_refund_min/10000, remaining_lifespan/total_lifespan × recycle_refund_base/10000)` = `body_cost × max(0.1, remaining/total × 0.5)`（`recycle_refund_base=5000bp`, `recycle_refund_min=1000bp`）
4. Deficit 惩罚：连续 3 tick deficit → 效率 −50%；连续 10 tick deficit → 强制死亡（age 加速 ×10）

**验收:** ≥ 6 个测试

---

## Wave 5: P2-5 Starting Resources

**仓库: `engine`** | **并行度: 1**

| 文件 | `resources.rs`, `economy.rs`, `world.rs`, `lib.rs` |
|------|------|
| 规范 | `specs/core/08-resource-ledger.md` §2.3 |

**实现:** `starting_resources` (Energy 5000 + Minerals 2000), `free_upkeep_controllers:1`, `free_upkeep_drones:3`, `free_upkeep_ticks:2000`
**验收:** ≥ 3 个测试

---

## Wave 6: P2-8 Allied Transfer

**仓库: `engine`** | **并行度: 1**

| 文件 | `command.rs` (新增 AlliedTransfer), `resources.rs`, `world.rs`, `lib.rs` |
|------|------|
| 规范 | `specs/core/08-resource-ledger.md` §2.1 |

**实现:** AlliedTransfer CommandAction + 200bp fee + cooldown + identity binding
**验收:** ≥ 4 个测试

---

## Wave 7: P3-1 Combat + P3-6 Visibility

**仓库: `engine`** | **并行度: 2**（无共享文件）

### T7a — Combat Pipeline
| 文件 | `combat_system.rs` (274行, 仅此文件) |
|------|------|
| 规范 | `specs/core/06-phase2b-system-manifest.md` §S11-S13 |

**实现:** 单文件注册 3 个 system（attack/ranged_attack/heal），并行安全由 target_id partition 保证。Melee(range=1), Ranged(projectile), Heal(ally)。
**验收:** ≥ 8 个新测试（已有 3 个，合计 ≥ 11）

### T7b — Visibility + Oracle 防线
| 文件 | `visibility.rs` (267行, 仅此文件) |
|------|------|
| 规范 | `specs/security/05-visibility.md` §1-§6, §10 |

**实现:** Drone perception, Camera 裁剪, Spectate, Oracle 防线 (`omitted_count` 分桶, `NotVisibleOrNotFound` 拒绝码等价)。同时实现 Hint Ladder（Safe/FixHint/FullDebug 三级错误提示，参见 `09-snapshot-contract.md` §4）。
**验收:** ≥ 8 个新测试（已有 3 个，合计 ≥ 11）

---

## Wave 8: S09 + S10 + S24 + S26 Stub 增强

**仓库: `engine`** | **并行度: 1**（共享 `systems/mod.rs` + `lib.rs`）

| 文件 | `spawning_grace_system.rs` (21→), `regeneration_system.rs` (43→), `decay_system.rs` (88→), `pvp_block_system.rs` (19→), `systems/mod.rs`, `scheduler.rs`, `lib.rs` |
|------|------|
| 规范 | `specs/core/06-phase2b-system-manifest.md` §S09, §S10, §S24, §S26 |

**实现:**
- **S09 SpawningGrace**: 向新生 drone 写入 `SpawningGrace{remaining:1}`（当前实现仅检查/递减已有 Grace，**缺失写入逻辑**，R16 B2 修复）
- **S10 Regeneration**: Entity HP 恢复（`hits++, capped at max_hits`, `Without<DeathMark>`）。⚠️ 当前 regeneration_system.rs(43行) 实现的是 Source 资源容量再生，与 manifest §S10 完全不符——**需重写**，非"增强"
- **S24 Decay**: 疲劳/冷却衰减。⚠️ 当前 decay_system.rs 同时处理 drone.age++（aging, S23）和 decay（S24），违反 manifest 的独立系统定义。W13 创建 aging_system.rs 时需**从 decay_system.rs 剥离 aging 逻辑**
- **S26 PvP Block**: `pvp_enabled` 检查，安全模式到期逻辑见 `01-tick-protocol.md` §2.5。⚠️ 当前调度位置在 spawn 之前，manifest 要求在 death_cleanup 之后——需修正 scheduler 注册顺序
**验收:** 每系统 ≥ 2 个测试（共 ≥ 8 个）

---

## Wave 9: S14 Special Attack Reducer + S15 Damage Application

**仓库: `engine`** | **并行度: 1**

| 文件 | `special_attack_reducer.rs` (**新建**), `damage_application_system.rs` (**新建**, S15), `systems/mod.rs`, `scheduler.rs`, `lib.rs` |
|------|------|
| 规范 | `specs/core/06-phase2b-system-manifest.md` §S14, §S15 |

> S07 `death_marker.rs`（已完成）与 S15 `damage_application_system.rs`（本 Wave 新建）是独立文件。**不要重命名或修改 death_marker.rs**——它是 S07 的完整实现。

**实现:**
- **S14**: Intent Collect → Canonical Sort (优先级+shuffle) → Deliver（不直接修改实体状态，交付 S22）
- **S15**: PendingDamage buffer → Resistance 减伤 → DeathMark（if hits≤0）
**验收:** ≥ 7 个测试

---

## Wave 10: P3-7 Body Part Match

**仓库: `engine`** | **并行度: 1**

| 文件 | `combat_system.rs` (新增 body_part_match), `command.rs` (新增 DisruptedResisted) |
|------|------|
| 规范 | `specs/core/06-phase2b-system-manifest.md` §S20, D3/A |

**实现:** body_part_match 通用验证逻辑（供 S11-S13 combat 攻击和 S20 disrupt 共用）。Disrupt body part match 验证 + 目标 body part 指定 + 失败拒绝。
**验收:** ≥ 3 个测试

---

## Wave 11: Status Effects Part 1 — S16 Hack + S18 Overload + S17 Drain

**仓库: `engine`** | **并行度: 1**

| 文件 | `hack_system.rs`, `overload_system.rs`, `drain_system.rs` (均新建), `systems/mod.rs`, `scheduler.rs`, `lib.rs`, `components.rs` (新增 StatusState + 标记组件) |
|------|------|
| 规范 | `specs/core/06-phase2b-system-manifest.md` §S16-S18 |

**实现:** S16 Hack（临时控制目标）、S18 Overload（范围伤害）、S17 Drain（吸取资源）
**验收:** 每系统 ≥ 2 个测试（共 ≥ 6 个）

---

## Wave 12: Status Effects Part 2 — S19 + S20 + S21 + S22

**仓库: `engine`** | **并行度: 1**

| 文件 | `debilitate_system.rs`, `disrupt_system.rs`, `fortify_system.rs`, `status_advance_system.rs` (均新建), `systems/mod.rs`, `scheduler.rs`, `lib.rs`, `components.rs` |
|------|------|
| 规范 | `specs/core/06-phase2b-system-manifest.md` §S19-S22 |

**实现:**
- S19 Debilitate（削弱属性）、S20 Disrupt（打断，需 body part match）、S21 Fortify（防御强化）
- S22 status_advance: **Unique Writer** — 唯一写入所有 StatusState 组件。统一读入 intent → 更新 StatusState (duration--, expire, apply) → 触发 damage
- 排序链: S14 (reducer) → S22 (status_advance) → S15 (damage_application)
  - 特殊攻击优先级链（唯一定义于 manifest §S14）：**Hack > Drain > Overload > Debilitate > Disrupt > Fortify**

**验收:** 每系统 ≥ 2 个测试（共 ≥ 8 个）+ unique writer 合约验证

---

## Wave 13: S23 Aging & S25 Death Cleanup

**仓库: `engine`** | **并行度: 1**

| 文件 | `aging_system.rs` (**新建**), `death_cleanup_system.rs` (9→), `systems/mod.rs`, `scheduler.rs`, `lib.rs`, `components.rs` (新增 Lifespan/ActiveAging) |
|------|------|
| 规范 | `specs/core/06-phase2b-system-manifest.md` §S23, §S25 |

**实现:** Lifespan 组件 + ActiveAging（加速老化，⚠️ 新增组件需同步更新 manifest §S23 的 R/W 声明）+ Death cleanup（资源释放）
**验收:** ≥ 5 个测试

---

## Wave 14: P3-8 Feedback Loop

**仓库: `engine`** | **并行度: 1**

| 文件 | `event_log.rs` (**新建**), `mcp.rs` (新增 tool), `realtime.rs` (WebSocket), `systems/mod.rs`, `scheduler.rs`, `lib.rs`, `components.rs` |
|------|------|
| 规范 | `specs/gameplay/06-feedback-loop.md` |

**实现:** EventLog 组件 + `swarm_get_snapshot`/`swarm_explain_last_tick` MCP tool + WebSocket 推送 + 事件保留策略。同时实现 `swarm_simulate`（预测性模拟，fork 隔离，RNG 命名空间隔离）和 `swarm_dry_run`（确定性试运行），参见 `09-snapshot-contract.md` §2。配套功能分布在 W1（snapshot 基础设施）、W0（starter bots）、W15（Arena replay）。
**验收:** ≥ 6 个测试（含 simulate 隔离验证）

---

## Wave 15: P4 Arena Mode（7 子任务全部修改 `arena.rs`，串行执行）

**仓库: `engine`** | **并行度: 1**（全部修改 `arena.rs`）

| # | 任务 | 规范 | 关键实现 |
|---|------|------|------|
| T15a | **P4-1** Room 创建 | `design/modes.md` §9.1.1-§9.1.2 | Create room + Configure（参数 + map + lock slots） |
| T15b | **P4-2** WASM Precommit | `design/modes.md` §9.1.2 | Module hash lock per slot（Ready 前锁定） |
| T15c | **P4-3** Match Lifecycle | `design/modes.md` §9.1.3 | Create→Configure→Ready→Play→Finish→Replay（对齐 modes.md 六阶段状态机） |
| T15d | **P4-4** Social Replay | `design/modes.md` §9.1.4 | Delayed spectator + replay URL + public_spectate 限流 |
| T15e | **P4-5** Local Replay | `specs/core/05-persistence-contract.md` §2 (Replay-Critical Subset) | Deterministic replay verifier |
| T15f | **P4-6** PvE Challenge | `design/modes.md` §9.1.5 | 4 场景引擎（Guardian Gauntlet/Swarm Defense/Resource Race/Ruin Siege）+ 评分公式 + PvE 排行榜 |
| T15g | **P4-7** Arena Admin | `design/modes.md` §9.1.1–§9.1.5 | Room 管理（list/kick/close）+ parameters 热更新。⚠️ §9.1.6 尚未创建——需在实现前补充规范 |

**文件:** T15a-c,f,g: `arena.rs`; T15d: +`replay_storage.rs`; T15e: +`tick.rs`
**验收:** arena 测试 ≥ 12 (+9), replay ≥ 3

> ⚠️ Arena 实现以 `design/modes.md` 为临时权威源。后续创建 `specs/gameplay/07-arena-contract.md` 后迁移引用。

---

## Wave 16: Auth/Security + 经济验证

**仓库: `engine`** | **并行度: 2**（T16b/T16c 串行化以避免 `lib.rs` 冲突）

> T16b 需在 `lib.rs` 注册 `mod security`；T16c 需注册 `mod wasm_deploy`。两者串行执行（T16b → T16c），避免 `lib.rs` 合并冲突。

### T16a — P2-7 Economy Balance
| 文件 | `tests/economy_balance.rs` (**新建**, 不碰 src/) |
|------|------|
| 规范 | `design/economy-balance-sheet.md` |

1/5/20/50 rooms 维护费曲线验证。
**验收:** 曲线与 balance sheet 预测一致。

### T16b — P1-7 Command Source Gate
| 文件 | `security.rs` (增强, 已注册 `pub mod security;` 于 lib.rs), `command.rs` (集成点) |
|------|------|
| 规范 | `specs/security/09-command-source.md` §4-§8 |

`CommandSource` 枚举 + MCP-only 注入 + Ed25519 证书链 + CRL + version_counter + Session 状态机。同时实现 Safe Hint Ladder 三级错误提示模型（若 W7 未完成）。
**验收:** ≥ 6 个测试。

### T16c — P1-6 WASM CDN 部署流
| 文件 | `wasm_deploy.rs` (**新建**), `lib.rs` |
|------|------|
| 规范 | `specs/security/09-command-source.md` §1-§3 |

deploy→validate→commit→activate pipeline + `swarm_deploy_module` MCP tool + CodeSigningCertificate 验证。
**验收:** ≥ 3 个测试。**不依赖 Arena**。

---

## Wave 17: P5 Benchmark Gates

**仓库: `engine`** | **并行度: 7**（独立 bench 文件）

添加 `criterion` 依赖。所有 bench 在 `benches/` 目录。
同时实现 Capacity Admission Model（`09-snapshot-contract.md` §7）：measured admission 动态调节，基于 p95/p99 指标计算 admitted_players。

| ID | 文件 | 指标 |
|----|------|------|
| P5-1 | `benches/command_loop.rs` | 100k validate p99<50ms, apply<100ms |
| P5-2 | `benches/snapshot_bench.rs` | 50k entities clone<20ms, restore<30ms |
| P5-3 | `benches/fdb_bench.rs` | 500 players p99<200ms, conflict<1% |
| P5-4 | `benches/room_partition.rs` | 1000 players, 200 rooms, p99<500ms, per-room conflict<1% |
| P5-5 | `benches/pathfinding.rs` | 50×50 A\\*, 100 concurrent ops, p99<10ms/node, fair-share + cache determinism |
| P5-6 | `benches/rollback.rs` | 500 entities 全组件, p99<50ms, entity ID allocator verified |
| P5-7 | `benches/load_test.rs` | 1000 players, 200 rooms, p99<500ms |
| P5-8 | `benches/snapshot_stitch.rs` | 1000 × 256KB snapshots, p99<100ms |

**验收:** `cargo bench` 全部通过，P5-1/P5-3/P5-7/P5-8 p99 达标。

---

## Milestones

| Milestone | 判定 | Wave |
|-----------|------|:----:|
| **M0: Mod Ready** | 7 个 mod 仓库 + engine submodule | ✅ W0 |
| **M1: Core Complete** | P0-6 Snapshot + Simulate/Dry-Run | W1, W14 |
| **M2: Economy** | P2-1..P2-8 + Balance test | W2-W6, W16a |
| **M3: Combat Foundation** | S09,S10,S14,S15,S24,S26 + Combat + Visibility + Hint Ladder | W7-W9 |
| **M4: Gameplay Systems** | Status Effects + Aging + Body Part + Feedback | W10-W14 |
| **M5: Arena** | P4-1..P4-7（含 PvE Challenge） | W15 |
| **M6: Production Ready** | Source Gate + CDN + Benchmarks + Capacity Admission | W16-W17 |
