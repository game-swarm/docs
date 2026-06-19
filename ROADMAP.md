# Swarm Implementation ROADMAP

> 仅列出待实现任务。已完成项已从本文移除。
> 文件互斥原则：同一 Wave 内任务不触碰相同 `.rs` 文件。
> 依赖关系：严格按 Wave 顺序执行，后续 Wave 依赖前置 Wave 完成。

---

## Wave 依赖图

```
W1 (P0-6)
 │
 ├─► W2 (P2-1) ─► W3 (P2-2) ─► W4 (P2-5) ─► W5 (P2-8)
 │                                        │
 ├─► W6 (P2-3)                            │
 │                                        │
 └─► W7 (P3-1, P3-6) ─► W8 (P3-2,P3-4,P3-5,P3-7)
                              │
                              └─► W9 (P3-3, P3-8)
                                       │
                                       └─► W10 (P4-1..P4-5)
                                                │
                                                └─► W11 (P1-6,P1-7,P2-7)
                                                         │
                                                         └─► W12 (P5-1..P5-7)
```

W2-W5 严格串行——每个均修改 `world.rs` + `resources.rs`。
W1, W6-W12 可与经济链（W2-W5）并行，文件集不相交。

---

## Wave 1: P0-6 Snapshot 构建器

**并行度: 1** | **文件: `sim.rs`, `tick.rs`, `lib.rs`**

### T1 — P0-6: Snapshot Builder

| 属性 | 值 |
|------|-----|
| **文件** | `src/sim.rs`（72行 stub → 完整）、`src/tick.rs`（集成点）、`src/lib.rs`（确认注册） |
| **不触碰** | `world.rs`, `scheduler.rs`, `systems/mod.rs`, `components.rs`, `command.rs` |
| **规范** | `specs/core/09-snapshot-contract.md`, `01-tick-protocol.md` §4 |
| **依赖** | 无 |

**实现内容：**

1. `src/sim.rs`：`fog_of_war_filter(player_id, world) → Snapshot`、`collect_snapshot(world, player_ids)`、WASM `tick()` 输入格式
2. `src/tick.rs`：COLLECT → [Snapshot] → EXECUTE 集成
3. 性能约束：50k entities snapshot < 20ms（P5-2 验证）

**验收：** `cargo test --lib` 新增 snapshot 测试 ≥ 3 个（fog_of_war 过滤、空世界、多玩家一致性）

---

## Wave 2: P2-1 Resource Ledger

**并行度: 1** | **文件: `resources.rs`, `economy.rs`, `world.rs`, `lib.rs`**

### T2 — P2-1: Resource Ledger 核心

| 属性 | 值 |
|------|-----|
| **文件** | `src/resources.rs`、`src/economy.rs`、`src/world.rs`（`[resources]` 配置）、`src/lib.rs` |
| **不触碰** | `command.rs`, `scheduler.rs`, `systems/mod.rs`, `components.rs` |
| **规范** | `specs/core/08-resource-ledger.md` §1-§2 |
| **依赖** | W1 |

**实现内容：**

1. Transfer Gateway（玩家间资源转移入口）
2. 定点费率（per-resource transfer cost）
3. Storage tax（每 tick 按存储量征税）
4. `world.toml` `[resources]` 配置节

**验收：** `cargo test --lib` 新增 ≥ 5 个测试（Transfer Gateway、费率、tax 累加、边界情况）

---

## Wave 3: P2-2 Empire Upkeep

**并行度: 1** | **文件: `memory_upkeep_system.rs`, `world.rs`, `lib.rs`**

### T3 — P2-2: Empire Upkeep 超线性维护

| 属性 | 值 |
|------|-----|
| **文件** | `src/systems/memory_upkeep_system.rs`（23行 → 完整）、`src/world.rs`（`[upkeep]` 配置）、`src/lib.rs` |
| **不触碰** | `resources.rs`, `economy.rs`, `components.rs`, `command.rs` |
| **规范** | `specs/core/08-resource-ledger.md` §Empire Upkeep |
| **依赖** | W2（需要 Resource Ledger 基础设施） |

**实现内容：**

1. 超线性维护费：`cost = base * N^(1+exponent)`
2. Deficit 惩罚（资源不足时衰减 RCL、减少产能）
3. `world.toml` `[empire_upkeep]` 节

**验收：** `cargo test --lib` 新增 ≥ 4 个测试（基准费用、超线性增长、deficit 惩罚、零 entity）

---

## Wave 4: P2-5 Starting Resources

**并行度: 1** | **文件: `resources.rs`, `economy.rs`, `world.rs`, `lib.rs`**

### T4 — P2-5: Starting Resources & Free Upkeep

| 属性 | 值 |
|------|-----|
| **文件** | `src/resources.rs`、`src/economy.rs`、`src/world.rs`（配置）、`src/lib.rs` |
| **不触碰** | `command.rs`, `memory_upkeep_system.rs`, `scheduler.rs` |
| **规范** | `specs/core/08-resource-ledger.md` §2.3 |
| **依赖** | W3（需要 EmpireUpkeep 运行后才能免维护费） |

**实现内容：**

1. `starting_resources`（默认 Energy 5000 + Minerals 2000）
2. `free_upkeep_controllers: 1`、`free_upkeep_drones: 3`、`free_upkeep_ticks: 2000`

**验收：** `cargo test --lib` 新增 ≥ 3 个测试（新玩家资源注入、首 controller 免费、免维护到期恢复扣费）

---

## Wave 5: P2-8 Allied Transfer

**并行度: 1** | **文件: `command.rs`, `resources.rs`, `world.rs`, `lib.rs`**

### T5 — P2-8: Allied Transfer & Anti-Smurf

| 属性 | 值 |
|------|-----|
| **文件** | `src/command.rs`（新增 TransferToPlayer）、`src/resources.rs`、`src/world.rs`、`src/lib.rs` |
| **不触碰** | `economy.rs`, `systems/`, `scheduler.rs` |
| **规范** | `specs/core/08-resource-ledger.md` §2.1 |
| **依赖** | W4（需要完整 ResourceLedger） |

**实现内容：**

1. `TransferToPlayer` CommandAction
2. 200bp transfer fee
3. Transfer cooldown（per-player-pair）
4. Identity binding（防 smurf 小号）

**验收：** `cargo test --lib` 新增 ≥ 4 个测试（跨玩家转移、fee 扣除、cooldown、identity binding）

---

## Wave 6: P2-3 PvE Budget

**并行度: 1** | **文件: `pve.rs`, `world.rs`, `lib.rs`**

### T6 — P2-3: PvE Budget 分配

| 属性 | 值 |
|------|-----|
| **文件** | `src/pve.rs`、`src/world.rs`（`[pve_budget]` 配置）、`src/lib.rs` |
| **不触碰** | `resources.rs`, `economy.rs`, `systems/`, `command.rs` |
| **规范** | `specs/core/08-resource-ledger.md` §3 |
| **依赖** | W2（需要 Resource Ledger） |

**实现内容：**

1. 4 维 Budget：GlobalBudget / ZoneBudget / PlayerBudget / EventBudget
2. 每 tick 按比例分配 PvE 产出
3. `world.toml` `[pve_budget]` 节

**验收：** `cargo test --lib` 新增 ≥ 3 个测试（4 维分配比例、预算池上限、budget 耗尽截断）

---

## Wave 7: P3-1 + P3-6

**并行度: 2**（无共享文件）

### T7a — P3-1: Combat Pipeline 完善

| 属性 | 值 |
|------|-----|
| **文件** | `src/systems/combat_system.rs`（仅此文件，已有 274 行 16 fn） |
| **不触碰** | `scheduler.rs`, `systems/mod.rs`, `lib.rs`, `world.rs`, `command.rs` |
| **规范** | `specs/core/06-phase2b-system-manifest.md` §S11-S13 |
| **依赖** | 无 |

**实现内容：** Melee（range=1 body_part_damage）、Ranged（projectile 投递）、Heal（ally targeting）

**验收：** `cargo test --lib` combat 测试 ≥ 8 个（+3）

### T7b — P3-6: Visibility 完善

| 属性 | 值 |
|------|-----|
| **文件** | `src/visibility.rs`（仅此文件，已有 267 行 18 fn） |
| **不触碰** | `scheduler.rs`, `systems/mod.rs`, `lib.rs`, `world.rs` |
| **规范** | `specs/security/05-visibility.md` |
| **依赖** | 无 |

**实现内容：** Drone perception 半径、Player camera 视野裁剪、Spectate 模式、Fog of war per-tile 缓存

**验收：** `cargo test --lib` visibility 测试 ≥ 6 个（+2）

---

## Wave 8: P3-2 + P3-4 + P3-5 + P3-7

**并行度: 4**（无共享文件）

### T8a — P3-2: Special Attack Reducer

| 属性 | 值 |
|------|-----|
| **文件** | `src/systems/special_attack_reducer.rs`（**新建**）、`src/systems/mod.rs`、`src/scheduler.rs`、`src/lib.rs` |
| **不触碰** | `world.rs`, `components.rs`, `command.rs`, `combat_system.rs` |
| **规范** | `specs/core/06-phase2b-system-manifest.md` §S14 |
| **依赖** | W7 |

**实现内容：** Intent Collect → Canonical Sort（优先级+shuffle）→ Deliver
**验收：** ≥ 3 个测试（收集、排序确定性、多玩家并发）

### T8b — P3-4: Damage Application

| 属性 | 值 |
|------|-----|
| **文件** | `src/systems/death_mark_system.rs`（28行 → 完整）、`src/systems/mod.rs`、`src/lib.rs` |
| **不触碰** | `combat_system.rs`, `scheduler.rs`, `world.rs`, `command.rs` |
| **规范** | `specs/core/06-phase2b-system-manifest.md` §S15 |
| **依赖** | W7 |

**实现内容：** PendingDamage buffer、Resistance 减伤、DeathMark
**验收：** ≥ 4 个测试（收集、减伤、标记、零伤害）

### T8c — P3-5: Aging & Death

| 属性 | 值 |
|------|-----|
| **文件** | `src/systems/aging_system.rs`（**新建**）、`src/systems/death_cleanup_system.rs`（9行 → 完整）、`src/systems/mod.rs`、`src/scheduler.rs`、`src/lib.rs` |
| **不触碰** | `combat_system.rs`, `death_mark_system.rs`, `world.rs`, `command.rs` |
| **规范** | `specs/core/06-phase2b-system-manifest.md` §S23/S25 |
| **依赖** | W7 |

**实现内容：** Lifespan 组件、Active aging（条件加速老化）、Death cleanup（资源释放）
**验收：** ≥ 5 个测试（到期死亡、加速老化、资源释放、并发）

### T8d — P3-7: Body Part Match

| 属性 | 值 |
|------|-----|
| **文件** | `src/systems/combat_system.rs`（新增 body_part_match）、`src/command.rs`（验证） |
| **不触碰** | `scheduler.rs`, `systems/mod.rs`, `lib.rs`, `world.rs` |
| **规范** | `specs/core/06-phase2b-system-manifest.md` §S20，D3/A |
| **依赖** | W7 |

**实现内容：** Disrupt body part match 验证、目标 body part 指定、匹配失败 → DisruptedResisted
**验收：** ≥ 3 个测试（匹配成功、不匹配拒绝、无目标跳过）

---

## Wave 9: P3-3 + P3-8

**并行度: 2**（无共享文件）

### T9a — P3-3: Status Effects（7 系统）

| 属性 | 值 |
|------|-----|
| **文件** | 新建 7 文件 + `src/systems/mod.rs` + `src/scheduler.rs` + `src/lib.rs` + `src/components.rs`（新增 StatusEffect 组件） |
| **不触碰** | `world.rs`, `command.rs`, `combat_system.rs` |
| **规范** | `specs/core/06-phase2b-system-manifest.md` §S16-S22 |
| **依赖** | W8 |

**实现内容：**

| 系统 | 文件 | 效果 |
|------|------|------|
| S16 Stun | `stun_system.rs` | 跳过目标下 N tick 行动 |
| S17 Slow | `slow_system.rs` | 减少移动/攻击范围 |
| S18 Poison | `poison_system.rs` | 每 tick 持续伤害 |
| S19 Shield | `shield_system.rs` | 吸收伤害上限 |
| S20 Fortify | `fortify_system.rs` | 临时防御强化 |
| S21 Leech | `leech_system.rs` | 攻击回复生命 |
| S22 Drain | `drain_system.rs` | 吸取目标资源 |

每个系统独立 `.rs` + per-status unique writer。

**验收：** 每个系统 ≥ 2 个测试（共 ≥ 14 个）

### T9b — P3-8: Feedback Loop

| 属性 | 值 |
|------|-----|
| **文件** | `src/event_log.rs`（**新建**）、`src/mcp.rs`（swarm_event_stream）、`src/realtime.rs`（WebSocket push）、`src/systems/mod.rs`、`src/scheduler.rs`、`src/lib.rs`、`src/components.rs` |
| **不触碰** | `world.rs`, `command.rs`, `combat_system.rs` |
| **规范** | `specs/gameplay/06-feedback-loop.md` |
| **依赖** | W8 |

**实现内容：** EventLog 组件、`swarm_event_stream` MCP tool、WebSocket 实时推送、事件保留策略
**验收：** ≥ 4 个测试（EventLog 创建、MCP 推送、WebSocket 推送、过期清理）

---

## Wave 10: P4 Arena Mode

**并行度: 1**（5 任务串行，全部修改 `arena.rs`）

### T10a — P4-1: Room 创建 & 配置
**文件**: `src/arena.rs` | **规范**: `design/modes.md` §Arena
Create room + 参数配置 + lock slots

### T10b — P4-2: WASM Precommit
**文件**: `src/arena.rs` | **规范**: `design/modes.md` §Arena
Module hash lock per slot + precommit 流程

### T10c — P4-3: Match Lifecycle
**文件**: `src/arena.rs` | **规范**: `design/modes.md` §Arena
start → run → finish → archive

### T10d — P4-4: Social Replay Highlight
**文件**: `src/replay_storage.rs`, `src/arena.rs` | **规范**: `design/modes.md` (D5/B)
Delayed public spectator + replay URL

### T10e — P4-5: Local Replay
**文件**: `src/replay_storage.rs`, `src/tick.rs` | **规范**: `specs/core/05-persistence-contract.md` §5
Deterministic replay verifier + replay 文件格式

**汇总验收：** arena 测试 ≥ 8 个（+5）、replay 测试 ≥ 3 个

---

## Wave 11: P1-6 + P1-7 + P2-7

**并行度: 3**（无共享文件）

### T11a — P1-6: WASM CDN 部署流
**文件**: `src/wasm_deploy.rs`（**新建**）、`src/lib.rs`
**规范**: `design/engine.md` §3.4.5
Deploy pipeline（上传→验证→commit→activate）、版本化存储、`swarm_deploy_module` MCP tool
**验收**: ≥ 2 个 deploy flow 端到端测试

### T11b — P1-7: Command Source Gate
**文件**: `src/security.rs`（已有 515 行）、`src/command.rs`（集成点）
**规范**: `specs/security/09-command-source.md`
MCP-only command injection、`CommandSource` 枚举、validation 阶段 source gate
**验收**: ≥ 2 个非 MCP 来源拒绝测试

### T11c — P2-7: Economy Balance 测试
**文件**: `tests/economy_balance.rs`（**新建**，不触碰任何 `src/` 文件）
**规范**: `design/economy-balance-sheet.md`
1/5/20/50 rooms break-even 测试 + 资源流动闭环
**验收**: 各规模 break-even 断言通过

---

## Wave 12: P5 Benchmark Gates

**并行度: 7**（全部新建 bench 文件，互不重叠）

添加 `criterion` 依赖到 `Cargo.toml`。

| ID | 名称 | 文件 | 规范 | 指标 |
|----|------|------|------|------|
| P5-1 | Command Loop | `benches/command_loop.rs` | `05-persistence-contract.md` §8.3 | 100k validate p99<50ms, apply<100ms |
| P5-2 | Snapshot | `benches/snapshot_bench.rs` | 同上 | 50k entities clone<20ms, restore<30ms |
| P5-3 | FDB Single-TX | `benches/fdb_bench.rs` | 同上 | 500 players p99<200ms, conflict<1% |
| P5-4 | FDB Room-Partition | `benches/room_partition.rs` | 同上 §8.1 | Room-level FDB + 2PC |
| P5-5 | Pathfinding | `benches/pathfinding.rs` | 同上 §8.3 | 50×50 A\*, fair-share |
| P5-6 | Rollback Snapshot | `benches/rollback.rs` | 同上 | 500 entities 全组件 |
| P5-7 | Load Test | `benches/load_test.rs` | `engine.md` §3.4.2 | 1000 players p99<500ms |

**依赖**: W11（需要完整经济系统）
**验收**: `cargo bench` 全部通过，P5-1/P5-3/P5-7 满足 p99 指标

---

## Milestones

| Milestone | 判定 | 包含 Wave |
|-----------|------|----------|
| **M1: Core Complete** | P0-6 闭合 | W1 |
| **M2: World Economy** | P2-1..P2-8 全部 + 经济测试 | W2-W6 + W11c |
| **M3: Gameplay Complete** | P3-1..P3-8 全部 | W7-W9 |
| **M4: Arena Works** | P4-1..P4-5 全部 | W10 |
| **M5: Auth & DevOps** | P1-6 + P1-7 | W11a-b |
| **M6: Scale Verified** | P5-1..P5-7 benchmark 全部通过 | W12 |
