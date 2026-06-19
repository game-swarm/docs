# Swarm Implementation ROADMAP

> 仅列出待实现变更。文件互斥：同一 Wave 内任务触碰的文件集完全不相交。
> 路径：`engine:` = `src/`，`sandbox:` = `/data/swarm/sandbox/`，`mod:` = `swarm/mod-*` 独立仓库，`docs:` = `/data/swarm/docs/`。
> 系统编号以 `specs/core/06-phase2b-system-manifest.md` 为权威来源。

---

## 当前状态审计 (2026-06-19)

| 类别 | 数量 | 说明 |
|------|:----:|------|
| ✅ 已完成 | 14 | P0-1~P0-5, P0-7~P0-8, P1-1~P1-4, P2-4, P2-6 |
| ⚠️ 部分/Stub | 8 | P0-6(72行), P3-1(274行), P3-6(267行), S09(21行), S10(43行), S15(28行), S24(88行), S26(19行) |
| ❌ 缺失 | 20 | P2-1,P2-2,P2-3,P2-5,P2-7,P2-8, S14,S16-S23, P3-7,P3-8, P1-6,P1-7, P4-2~P4-5, P5-1~P5-7 |
| 📦 Mod 仓库 | 8 | 已创建空仓库，无 engine submodule |

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
 │                                                             └─► W15 (P4-1~P4-5)
 │                                                                      │
 │                                                                      └─► W16 (P1-6 ‖ P1-7 ‖ P2-7)
 │                                                                               │
 │                                                                               └─► W17 (P5-1~P5-7)
```

---

## Wave 0: 官方模组仓库初始化

**仓库: 7 个 `swarm/mod-*` + `engine`** | **并行度: 7（独立仓库）+ 1（engine）**

### T0a — 填充 7 个 mod 仓库

从 [`mod-template`](https://git.kagurazakalan.com/swarm/mod-template) 复制 scaffold → 定制各 mod 的 `mod.toml` + Rhai 脚本。

| 模组 | 默认 | engine 系统映射 | key config 参数 |
|------|:----:|------|------|
| `mod-empire-upkeep` | ✅ | `memory_upkeep_system.rs`, `controller_repair_system.rs` | `base_upkeep`, `room_soft_cap`, `repair_cap`, `distance_decay_bp`, `recycle_refund_base` |
| `mod-fog-of-war` | ✅ | `visibility.rs` | `fog_of_war`, `player_view`, `public_spectate` |
| `mod-resource-decay` | ❌ | `decay_system.rs` | `decay_rate`, `decay_threshold` |
| `mod-pve-spawning` | ✅ | `spawn_system.rs`, `spawning_grace_system.rs`, `npc_spawn_system.rs`, `pve.rs` | `spawn_rate`, `npc_types`, `difficulty_zones` |
| `mod-combat-core` | ✅ | `combat_system.rs`, `death_mark_system.rs`, `death_cleanup_system.rs`, `regeneration_system.rs` | `damage_multiplier`, `body_part_types` |
| `mod-special-attacks` | ✅ | S16-S22 status systems | `special_attacks_enabled`, `custom_actions` |
| `mod-depot-storage` | ✅ | `depot_repair_system.rs`, `global_storage_system.rs`, `cargo_in_transit_system.rs`, `drone_env_var_system.rs` | storage caps, transfer rates |

### T0b — engine 添加 submodule

**仓库: `engine`** | **文件: `.gitmodules`, `mods/`**

`git submodule add` 七个 mod 仓库到 `engine/mods/`。

**验收:** 每个 mod 有 `mod.toml` + 3 个 `.rhai`；`git submodule status` 显示 7 个子模块。

---

## Wave 1: P0-6 Snapshot 构建器

**仓库: `engine`** | **并行度: 1**

| 文件 | `sim.rs` (72 行→完整), `tick.rs` (集成), `lib.rs` |
|------|------|
| 不触碰 | `world.rs`, `scheduler.rs`, `systems/mod.rs`, `components.rs`, `command.rs` |
| 规范 | `specs/core/09-snapshot-contract.md`, `specs/security/05-visibility.md`, `01-tick-protocol.md` §2.3 |

**实现:** `fog_of_war_filter()` + `collect_snapshot()` 在 `sim.rs`；COLLECT→[Snapshot]→EXECUTE 集成到 `tick.rs`
**验收:** ≥ 3 个 snapshot 测试

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
1. 维护费公式: **`cost = base_upkeep × rooms × (1 + rooms / room_soft_cap)`**（`base_upkeep=50`, `room_soft_cap=10`）
2. Controller Repair: `repair_cost = body_cost × (1 - 3500/10000) × (1 + distance × 500/10000)`
3. Recycle Refund: `refund = body_cost × remaining_lifespan/total_lifespan × 5000/10000`（下限 1000bp）
4. Deficit 惩罚

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

| 文件 | `command.rs` (新增 TransferToPlayer), `resources.rs`, `world.rs`, `lib.rs` |
|------|------|
| 规范 | `specs/core/08-resource-ledger.md` §2.1 |

**实现:** TransferToPlayer CommandAction + 200bp fee + cooldown + identity binding
**验收:** ≥ 4 个测试

---

## Wave 7: P3-1 Combat + P3-6 Visibility

**仓库: `engine`** | **并行度: 2**（无共享文件）

### T7a — Combat Pipeline
| 文件 | `combat_system.rs` (274行, 仅此文件) |
|------|------|
| 规范 | `specs/core/06-phase2b-system-manifest.md` §S11-S13 |

**实现:** Melee(range=1), Ranged(projectile), Heal(ally)
**验收:** ≥ 8 个测试 (+3)

### T7b — Visibility + Oracle 防线
| 文件 | `visibility.rs` (267行, 仅此文件) |
|------|------|
| 规范 | `specs/security/05-visibility.md` §1-§6, §10 |

**实现:** Drone perception, Camera 裁剪, Spectate, Oracle 防线 (`omitted_count` 分桶, `NotVisibleOrNotFound` 拒绝码等价)
**验收:** ≥ 8 个测试 (+3)

---

## Wave 8: S09 + S10 + S24 + S26 Stub 增强

**仓库: `engine`** | **并行度: 1**（共享 `systems/mod.rs` + `lib.rs`）

| 文件 | `spawning_grace_system.rs` (21→), `regeneration_system.rs` (43→), `decay_system.rs` (88→), `pvp_block_system.rs` (19→), `systems/mod.rs`, `scheduler.rs`, `lib.rs` |
|------|------|
| 规范 | `specs/core/06-phase2b-system-manifest.md` §S09, §S10, §S24, §S26 |

**实现:** S09 SpawningGrace（出生 tick 无敌, R16 B2）、S10 Regeneration（先于 damage, `Without<DeathMark>`）、S24 Decay（疲劳/冷却衰减）、S26 PvP Block（安全模式到期）
**验收:** ≥ 6 个测试

---

## Wave 9: S14 Special Attack Reducer + S15 Damage Application

**仓库: `engine`** | **并行度: 1**

| 文件 | `special_attack_reducer.rs` (**新建**), `death_mark_system.rs` (28→), `systems/mod.rs`, `scheduler.rs`, `lib.rs` |
|------|------|
| 规范 | `specs/core/06-phase2b-system-manifest.md` §S14, §S15 |

**实现:**
- **S14**: Intent Collect → Canonical Sort (优先级+shuffle) → Deliver（不直接修改实体状态，交付 S22）
- **S15**: PendingDamage buffer → Resistance 减伤 → DeathMark
**验收:** ≥ 7 个测试

---

## Wave 10: P3-7 Body Part Match

**仓库: `engine`** | **并行度: 1**

| 文件 | `combat_system.rs` (新增 body_part_match), `command.rs` (新增 DisruptedResisted) |
|------|------|
| 规范 | `specs/core/06-phase2b-system-manifest.md` §S20, D3/A |

**实现:** Disrupt body part match 验证 + 目标 body part 指定 + 失败拒绝
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

**验收:** 每系统 ≥ 2 个测试（共 ≥ 8 个）+ unique writer 合约验证

---

## Wave 13: S23 Aging & S25 Death Cleanup

**仓库: `engine`** | **并行度: 1**

| 文件 | `aging_system.rs` (**新建**), `death_cleanup_system.rs` (9→), `systems/mod.rs`, `scheduler.rs`, `lib.rs`, `components.rs` (新增 Lifespan/ActiveAging) |
|------|------|
| 规范 | `specs/core/06-phase2b-system-manifest.md` §S23, §S25 |

**实现:** Lifespan 组件 + ActiveAging（加速老化）+ Death cleanup（资源释放）
**验收:** ≥ 5 个测试

---

## Wave 14: P3-8 Feedback Loop

**仓库: `engine`** | **并行度: 1**

| 文件 | `event_log.rs` (**新建**), `mcp.rs` (新增 tool), `realtime.rs` (WebSocket), `systems/mod.rs`, `scheduler.rs`, `lib.rs`, `components.rs` |
|------|------|
| 规范 | `specs/gameplay/06-feedback-loop.md` |

**实现:** EventLog 组件 + `swarm_get_snapshot`/`swarm_explain_last_tick` MCP tool + WebSocket 推送 + 事件保留策略
**验收:** ≥ 4 个测试

---

## Wave 15: P4 Arena Mode（5 子任务串行）

**仓库: `engine`** | **并行度: 1**（全部修改 `arena.rs`）

| # | 任务 | 规范 | 关键实现 |
|---|------|------|------|
| T15a | **P4-1** Room 创建 | `modes.md` §9.1 | Create room + 参数 + lock slots |
| T15b | **P4-2** WASM Precommit | `modes.md` §9.1.2 | Module hash lock per slot |
| T15c | **P4-3** Match Lifecycle | `modes.md` §9.1.3 | start→play→finish→archive |
| T15d | **P4-4** Social Replay | `modes.md` §9.1.4 | Delayed spectator + replay URL |
| T15e | **P4-5** Local Replay | `05-persistence-contract.md` §5 | Deterministic replay verifier |

**文件:** T15a-c: `arena.rs`; T15d: +`replay_storage.rs`; T15e: +`tick.rs`
**验收:** arena 测试 ≥ 8 (+5), replay ≥ 3

---

## Wave 16: Auth/Security + 经济验证

**仓库: `engine`** | **并行度: 3**（无共享文件）

### T16a — P2-7 Economy Balance
| 文件 | `tests/economy_balance.rs` (**新建**, 不碰 src/) |
|------|------|
| 规范 | `design/economy-balance-sheet.md` |

1/5/20/50 rooms 维护费曲线验证。
**验收:** 曲线与 balance sheet 预测一致。

### T16b — P1-7 Command Source Gate
| 文件 | `security.rs` (增强), `command.rs` (集成点) |
|------|------|
| 规范 | `specs/security/09-command-source.md` §4-§8 |

`CommandSource` 枚举 + MCP-only 注入 + Ed25519 证书链 + CRL + version_counter + Session 状态机。
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

| ID | 文件 | 指标 |
|----|------|------|
| P5-1 | `benches/command_loop.rs` | 100k validate p99<50ms, apply<100ms |
| P5-2 | `benches/snapshot_bench.rs` | 50k entities clone<20ms, restore<30ms |
| P5-3 | `benches/fdb_bench.rs` | 500 players p99<200ms, conflict<1% |
| P5-4 | `benches/room_partition.rs` | Room-level FDB + 2PC |
| P5-5 | `benches/pathfinding.rs` | 50×50 A\*, fair-share |
| P5-6 | `benches/rollback.rs` | 500 entities 全组件 |
| P5-7 | `benches/load_test.rs` | 1000 players p99<500ms |

**验收:** `cargo bench` 全部通过，P5-1/P5-3/P5-7 p99 达标。

---

## Milestones

| Milestone | 判定 | Wave |
|-----------|------|:----:|
| **M0: Mod Ready** | 7 个 mod 仓库 + engine submodule | W0 |
| **M1: Core Complete** | P0-6 Snapshot | W1 |
| **M2: Economy** | P2-1..P2-8 + Balance test | W2-W6, W16a |
| **M3: Combat Foundation** | S09,S10,S14,S15,S24,S26 + Combat + Visibility | W7-W9 |
| **M4: Gameplay Systems** | Status Effects + Aging + Body Part + Feedback | W10-W14 |
| **M5: Arena** | P4-1..P4-5 | W15 |
| **M6: Production Ready** | Source Gate + CDN + Benchmarks | W16-W17 |
