# Swarm Implementation ROADMAP

> 基于 R22-R25 四轮评审收敛后的设计合同。
> 设计冻结：B1-B4 + D1-D6 全部闭合。
> 文件互斥原则：同一 Wave 内任务不触碰相同 `.rs` 文件。

## 当前已完成（无需任务）

| ID | 名称 | 状态 | 证据 |
|----|------|------|------|
| P0-1 | Tick 循环框架 | ✅ | `tick.rs` 3039 行 |
| P0-2 | ECS 系统调度器 | ✅ | `scheduler.rs` 554 行 |
| P0-3 | Command 收集校验 | ✅ | `command.rs` 3770 行 |
| P0-4 | WASM Sandbox | ✅ | `sandbox/lib.rs` 1802 行 |
| P0-5 | FDB 单事务持久化 | ✅ | `fdb.rs` 760 行 |
| P0-7 | RNG（Blake3 XOF） | ✅ | `tick.rs:finalize_xof()` + 测试 |
| P0-8 | IndexMap 替换 HashMap | ✅ | 全项目已使用 IndexMap |
| P1-1 | 证书颁发管理 | ✅ | `auth/mod.rs` |
| P1-2 | MCP Auth 登录流 | ✅ | `mcp.rs` 6 处引用 |
| P1-3 | MCP Tools（63 个） | ✅ | `mcp.rs` 63 个 `swarm_*` 工具 |
| P1-4 | SDK Codegen | ✅ | `sdk_gen.rs` 762 行 |
| P2-4 | World Rules 引擎 | ✅ | `rule_module.rs` 1225 行 |
| P2-6 | Controller Repair | ✅ | `controller_repair_system.rs` 244 行 |

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
                                       └─► W10 (P4-1,P4-2,P4-3,P4-4,P4-5)
                                                │
                                                └─► W11 (P1-6,P1-7,P2-7)
                                                         │
                                                         └─► W12 (P5-1..P5-7)
```

W2-W5 是严格串行的——每个都改 `world.rs` + `resources.rs`。
W1, W6-W12 可与经济链（W2-W5）并行，因为触碰不同文件。

---

## Wave 1: P0-6 Snapshot 构建器

**并行度: 1** | **文件: `sim.rs`, `tick.rs`, `lib.rs`**

### T1 — P0-6: Snapshot Builder

| 属性 | 值 |
|------|-----|
| **文件** | `src/sim.rs`（主要实现）、`src/tick.rs`（集成到 COLLECT→EXECUTE）、`src/lib.rs`（确认注册） |
| **不触碰** | `world.rs`, `scheduler.rs`, `systems/mod.rs`, `components.rs`, `command.rs` |
| **规范** | `specs/core/09-snapshot-contract.md`, `01-tick-protocol.md` §4 |
| **依赖** | 无 |
| **后续依赖** | P3-6（Visibility 提供 fog_of_war 数据给 Snapshot） |

**实现内容：**

1. `src/sim.rs` 从 72 行 stub → 完整实现：
   - `fog_of_war_filter(player_id, world) → Snapshot` — 裁剪不可见 entity
   - `collect_snapshot(world, player_ids) → Vec<(PlayerId, Snapshot)>` — 批量构建
   - WASM `tick()` 输入格式：每个玩家的可见 entity + 组件子集
2. `src/tick.rs` 集成：COLLECT → [Snapshot] → EXECUTE 流程中插入快照构建
3. 性能约束：50k entities snapshot < 20ms（后续 P5-2 验证）

**验收标准：**

```
cargo build 通过
cargo test --lib 中新增 snapshot 测试 ≥ 3 个
  - fog_of_war 过滤测试
  - 空世界快照测试
  - 多玩家快照一致性测试
git push origin main
```

---

## Wave 2: P2-1 Resource Ledger

**并行度: 1** | **文件: `resources.rs`, `economy.rs`, `world.rs`, `lib.rs`**

### T2 — P2-1: Resource Ledger 核心

| 属性 | 值 |
|------|-----|
| **文件** | `src/resources.rs`、`src/economy.rs`、`src/world.rs`（新增 `[resources]` 配置节）、`src/lib.rs` |
| **不触碰** | `command.rs`, `scheduler.rs`, `systems/mod.rs`, `components.rs` |
| **规范** | `specs/core/08-resource-ledger.md` §1-§2 |
| **依赖** | W1（P0-6 完成） |

**实现内容：**

1. Transfer Gateway：玩家间资源转移入口
2. 定点费率（per-resource transfer cost，如 Energy 50bp、Minerals 100bp）
3. Storage tax（每 tick 按存储量征税）
4. `world.toml` 新增 `[resources]` 配置节

**验收标准：**

```
cargo build && cargo test --lib
新增测试 ≥ 5 个：
  - Transfer Gateway 基本流程
  - 定点费率计算
  - Storage tax 累加
  - 边界情况（零余额转移、超额转移）
git push origin main
```

---

## Wave 3: P2-2 Empire Upkeep

**并行度: 1** | **文件: `memory_upkeep_system.rs`, `world.rs`, `lib.rs`**

### T3 — P2-2: Empire Upkeep 超线性维护

| 属性 | 值 |
|------|-----|
| **文件** | `src/systems/memory_upkeep_system.rs`（从 23 行→完整）、`src/world.rs`（新增 `[upkeep]` 配置）、`src/lib.rs` |
| **不触碰** | `resources.rs`, `economy.rs`, `components.rs`, `command.rs` |
| **规范** | `specs/core/08-resource-ledger.md` §Empire Upkeep |
| **依赖** | W2（P2-1 完成——需要 Resource Ledger 的 transfer/storage 基础设施） |

**实现内容：**

1. 超线性维护费：`cost = base * N^(1+exponent)`（N = entity 数量）
2. Deficit 惩罚：资源不足时衰减 RCL、减少 drone 产能
3. `world.toml` 新增 `[empire_upkeep]` 节（base_cost, exponent, deficit_decay_rate）

**验收标准：**

```
cargo build && cargo test --lib
新增测试 ≥ 4 个：
  - 1 controller 基准费用
  - 5 controllers 超线性增长验证
  - Deficit 惩罚触发
  - 零 entity 零费用
git push origin main
```

---

## Wave 4: P2-5 Starting Resources

**并行度: 1** | **文件: `resources.rs`, `economy.rs`, `world.rs`, `lib.rs`**

### T4 — P2-5: Starting Resources & Free Upkeep

| 属性 | 值 |
|------|-----|
| **文件** | `src/resources.rs`、`src/economy.rs`、`src/world.rs`（新增配置）、`src/lib.rs` |
| **不触碰** | `command.rs`, `systems/memory_upkeep_system.rs`, `scheduler.rs` |
| **规范** | `specs/core/08-resource-ledger.md` §2.3 |
| **依赖** | W3（P2-2 完成——需要 EmpireUpkeep 系统运行后才能免维护费） |

**实现内容：**

1. `starting_resources` 配置（新玩家开局资源注入，默认 Energy 5000 + Minerals 2000）
2. `free_upkeep_controllers: 1`（第一个 controller 免维护费）
3. `free_upkeep_drones: 3`（前 3 个 drone 免维护费）
4. `free_upkeep_ticks: 2000`（免维护费持续 tick 数）

**验收标准：**

```
cargo build && cargo test --lib
新增测试 ≥ 3 个：
  - 新玩家收到 starting_resources
  - 首个 controller 免维护费验证
  - free_upkeep_ticks 到期后恢复扣费
git push origin main
```

---

## Wave 5: P2-8 Allied Transfer

**并行度: 1** | **文件: `command.rs`, `resources.rs`, `world.rs`, `lib.rs`**

### T5 — P2-8: Allied Transfer & Anti-Smurf

| 属性 | 值 |
|------|-----|
| **文件** | `src/command.rs`（新增 TransferToPlayer CommandAction）、`src/resources.rs`、`src/world.rs`（配置）、`src/lib.rs` |
| **不触碰** | `economy.rs`, `systems/`, `scheduler.rs` |
| **规范** | `specs/core/08-resource-ledger.md` §2.1 |
| **依赖** | W4（P2-5 完成——需要 ResourceLedger 完整后才能做跨玩家转移） |

**实现内容：**

1. `TransferToPlayer` CommandAction（target_player, resource, amount）
2. 200bp transfer fee
3. Transfer cooldown（per-player-pair，防止刷资源）
4. Identity binding（transfer 记录绑定 player identity，防 smurf 小号）

**验收标准：**

```
cargo build && cargo test --lib
新增测试 ≥ 4 个：
  - 跨玩家转移基本流程
  - 200bp fee 正确扣除
  - Cooldown 阻止连续转移
  - Identity binding 验证
git push origin main
```

---

## Wave 6: P2-3 PvE Budget

**并行度: 1** | **文件: `pve.rs`, `world.rs`, `lib.rs`**

### T6 — P2-3: PvE Budget 分配

| 属性 | 值 |
|------|-----|
| **文件** | `src/pve.rs`、`src/world.rs`（新增 `[pve_budget]` 配置）、`src/lib.rs` |
| **不触碰** | `resources.rs`, `economy.rs`, `systems/`, `command.rs` |
| **规范** | `specs/core/08-resource-ledger.md` §3 |
| **依赖** | W2（P2-1 完成——需要 Resource Ledger） |

**实现内容：**

1. 4 维 Budget 分配：GlobalBudget / ZoneBudget / PlayerBudget / EventBudget
2. 每 tick 按比例分配 PvE 产出到各预算池
3. `world.toml` 新增 `[pve_budget]` 节

**验收标准：**

```
cargo build && cargo test --lib
新增测试 ≥ 3 个：
  - 4 维预算分配比例验证
  - 预算池累加上限
  - budget 耗尽后 PvE 产出截断
git push origin main
```

---

## Wave 7: P3-1 + P3-6（并行，无共享文件）

**并行度: 2**

### T7a — P3-1: Combat Pipeline 完善

| 属性 | 值 |
|------|-----|
| **文件** | `src/systems/combat_system.rs`（仅此文件） |
| **不触碰** | `scheduler.rs`, `systems/mod.rs`, `lib.rs`, `world.rs`, `command.rs` |
| **规范** | `specs/core/06-phase2b-system-manifest.md` §S11-S13 |
| **依赖** | 无（已有 274 行基础实现） |

**实现内容：**

1. Melee 攻击：range=1 body_part_damage 完整流程
2. Ranged 攻击：range>1 projectile 投递
3. Heal 流程：ally targeting, heal_amount 计算
4. 已有 16 个 fn，补全缺失的测试覆盖

**验收标准：**

```
cargo build && cargo test --lib
combat 测试 ≥ 8 个（现有基础上至少 +3）
  - Melee 命中/未命中
  - Ranged 射程内/外
  - Heal 友方/敌方过滤
git push origin main
```

### T7b — P3-6: Visibility 完善

| 属性 | 值 |
|------|-----|
| **文件** | `src/visibility.rs`（仅此文件） |
| **不触碰** | `scheduler.rs`, `systems/mod.rs`, `lib.rs`, `world.rs` |
| **规范** | `specs/security/05-visibility.md` |
| **依赖** | 无（已有 267 行 18 个 fn） |

**实现内容：**

1. Drone perception 半径计算（基于 drone 属性）
2. Player camera 视野裁剪
3. Spectate 模式（观战者可见范围）
4. Fog of war 粒度优化（per-tile 可见性缓存）

**验收标准：**

```
cargo build && cargo test --lib
visibility 测试 ≥ 6 个（现有基础上至少 +2）
  - Drone perception 半径
  - 不同 player camera 裁剪一致性
  - Spectate 可见范围 > 正常玩家
git push origin main
```

---

## Wave 8: P3-2 + P3-4 + P3-5 + P3-7（并行，无共享文件）

**并行度: 4**

### T8a — P3-2: Special Attack Reducer

| 属性 | 值 |
|------|-----|
| **文件** | `src/systems/special_attack_reducer.rs`（**新建**）、`src/systems/mod.rs`、`src/scheduler.rs`、`src/lib.rs` |
| **不触碰** | `world.rs`, `components.rs`, `command.rs`, `combat_system.rs` |
| **规范** | `specs/core/06-phase2b-system-manifest.md` §S14 |
| **依赖** | W7（P3-1 完成——Combat Pipeline 需要先就位） |

**实现内容：**

1. Intent Collect：收集所有玩家的 special_attack intent
2. Canonical Sort：按优先级 + 确定性 shuffle 排序
3. Deliver：按排序结果逐个投递 special attack 效果
4. 在 `scheduler.rs` 中注册 `special_attack_reducer`（已有一个占位行）

**验收标准：**

```
cargo build && cargo test --lib
新增测试 ≥ 3 个：
  - Intent 收集
  - Canonical sort 确定性
  - 多玩家并发 special attack 排序
git push origin main
```

### T8b — P3-4: Damage Application

| 属性 | 值 |
|------|-----|
| **文件** | `src/systems/death_mark_system.rs`（从 28 行→完整）、`src/systems/mod.rs`、`src/lib.rs` |
| **不触碰** | `combat_system.rs`, `scheduler.rs`, `world.rs`, `command.rs` |
| **规范** | `specs/core/06-phase2b-system-manifest.md` §S15 |
| **依赖** | W7（P3-1 完成——需要 combat 系统的 damage 输出） |

**实现内容：**

1. PendingDamage buffer（收集 combat 系统产出的 damage）
2. Damage application（扣除 resistances 后的实际伤害）
3. DeathMark：血量 ≤0 时标记 entity 为待死亡

**验收标准：**

```
cargo build && cargo test --lib
新增测试 ≥ 4 个：
  - PendingDamage 收集
  - Resistance 减伤计算
  - DeathMark 标记
  - 零伤害不触发 DeathMark
git push origin main
```

### T8c — P3-5: Aging & Death

| 属性 | 值 |
|------|-----|
| **文件** | `src/systems/aging_system.rs`（**新建**）、`src/systems/death_cleanup_system.rs`（从 9 行→完整）、`src/systems/mod.rs`、`src/scheduler.rs`、`src/lib.rs` |
| **不触碰** | `combat_system.rs`, `death_mark_system.rs`, `world.rs`, `command.rs` |
| **规范** | `specs/core/06-phase2b-system-manifest.md` §S23/S25 |
| **依赖** | W8-T8b（P3-4 完成——DeathMark 后才能做 death cleanup） |

**实现内容：**

1. Lifespan 组件：entity 固有寿命（tick 数）
2. Active aging 系统：条件效果加速老化（如 poison 加倍 age 速率）
3. Death cleanup：清理 DeathMark entity 的资源释放

**验收标准：**

```
cargo build && cargo test --lib
新增测试 ≥ 5 个：
  - Lifespan 到期自动死亡
  - Active aging 加速
  - Death cleanup 资源释放
  - 多 entity 并发老化
git push origin main
```

### T8d — P3-7: Body Part Match

| 属性 | 值 |
|------|-----|
| **文件** | `src/systems/combat_system.rs`（新增 body_part_match 函数）、`src/command.rs`（新增验证） |
| **不触碰** | `scheduler.rs`, `systems/mod.rs`, `lib.rs`, `world.rs` |
| **规范** | `specs/core/06-phase2b-system-manifest.md` §S20，D3/A 设计决策 |
| **依赖** | W7（P3-1 完成） |

**实现内容：**

1. Disrupt special attack 的 body part match 验证
2. 每个 special attack 指定目标 body part（如 Disrupt→head）
3. 匹配成功→效果应用，失败→DisruptedResisted 拒绝

**验收标准：**

```
cargo build && cargo test --lib
新增测试 ≥ 3 个：
  - Body part 匹配成功
  - Body part 不匹配被拒绝
  - 无目标 body part 的 attack 跳过匹配
git push origin main
```

---

## Wave 9: P3-3 + P3-8（并行，无共享文件）

**并行度: 2**

### T9a — P3-3: Status Effects（7 系统）

| 属性 | 值 |
|------|-----|
| **文件** | 新建 7 个文件：`src/systems/stun_system.rs`, `slow_system.rs`, `poison_system.rs`, `shield_system.rs`, `fortify_system.rs`, `leech_system.rs`, `drain_system.rs`；改动：`src/systems/mod.rs`, `src/scheduler.rs`, `src/lib.rs`, `src/components.rs`（新增 StatusEffect 组件） |
| **不触碰** | `world.rs`, `command.rs`, `combat_system.rs` |
| **规范** | `specs/core/06-phase2b-system-manifest.md` §S16-S22 |
| **依赖** | W8（P3-2, P3-4, P3-5, P3-7 全部完成——状态效果需要完整的 combat/damage/death 链） |

**实现内容：**

1. S16 Stun：跳过目标下 N tick 的行动
2. S17 Slow：减少目标移动/攻击范围
3. S18 Poison：每 tick 造成持续伤害（与 P3-4 Damage 集成）
4. S19 Shield：吸收伤害上限
5. S20 Fortify：临时防御强化
6. S21 Leech：攻击回复生命
7. S22 Drain：吸取目标资源

每个系统：独立 `.rs` 文件 + per-status unique writer + ECS query。

**验收标准：**

```
cargo build && cargo test --lib
每个 status 系统 ≥ 2 个测试（共 ≥ 14 个新测试）
  - 效果应用/到期清除
  - 堆叠/不堆叠行为
  - 与其他 status 的交互
git push origin main
```

### T9b — P3-8: Feedback Loop

| 属性 | 值 |
|------|-----|
| **文件** | `src/event_log.rs`（**新建**）、`src/mcp.rs`（新增 swarm_event_stream tool）、`src/realtime.rs`（WebSocket push）、`src/systems/mod.rs`、`src/scheduler.rs`、`src/lib.rs`、`src/components.rs`（新增 EventLog 组件） |
| **不触碰** | `world.rs`, `command.rs`, `combat_system.rs` |
| **规范** | `specs/gameplay/06-feedback-loop.md` |
| **依赖** | W8（P3-2..P3-7 完成——事件产生在 combat/damage/status 系统之后） |

**实现内容：**

1. EventLog 组件（per-entity tick 事件记录：damage_taken, status_applied, death 等）
2. `swarm_event_stream` MCP tool（推送事件给客户端）
3. WebSocket push 机制（实时推送到前端）
4. 事件保留策略（最近 N tick的事件，超出丢弃）

**验收标准：**

```
cargo build && cargo test --lib
新增测试 ≥ 4 个：
  - EventLog 创建
  - MCP tool 事件推送
  - WebSocket 连接→推送
  - 事件过期清理
git push origin main
```

---

## Wave 10: P4 Arena Mode（串行，共享 arena.rs）

**并行度: 1（5 个任务串行，全部改 arena.rs）**

### T10a — P4-1: Room 创建 & 配置
**文件**: `src/arena.rs` | **规范**: `design/modes.md` §Arena
1. Create room with parameters（max_players, map, tick_rate）
2. Lock slots（player 加入后锁定）
3. Room config 持久化

### T10b — P4-2: WASM Precommit
**文件**: `src/arena.rs` | **规范**: `design/modes.md` §Arena
1. WASM module hash 记录
2. Per-slot module hash lock
3. Precommit 流程（玩家锁定 module→比赛开始前验证 hash）

### T10c — P4-3: Match Lifecycle
**文件**: `src/arena.rs` | **规范**: `design/modes.md` §Arena
1. Match start（所有 slot 锁定→开赛）
2. Match run（tick loop 封装）
3. Match finish（胜负判定→结果记录）
4. Match archive（数据归档到 replay_storage）

### T10d — P4-4: Social Replay Highlight
**文件**: `src/replay_storage.rs`, `src/arena.rs` | **规范**: `design/modes.md` §Arena (D5/B)
1. Delayed public spectator（比赛结束后 N tick 公开观战）
2. Replay URL 生成

### T10e — P4-5: Local Replay
**文件**: `src/replay_storage.rs`, `src/tick.rs` | **规范**: `specs/core/05-persistence-contract.md` §5
1. Deterministic replay verifier（重放→状态 checksum 一致）
2. Replay 文件格式定义

**汇总验收**（所有 P4 任务合并）：

```
cargo build && cargo test --lib
arena 测试 ≥ 8 个（现有基础上至少 +5）
replay 测试 ≥ 3 个
git push origin main
```

---

## Wave 11: P1-6 + P1-7 + P2-7（并行，无共享文件）

**并行度: 3**

### T11a — P1-6: WASM CDN 部署流

| 属性 | 值 |
|------|-----|
| **文件** | `src/wasm_deploy.rs`（**新建**）、`src/lib.rs` |
| **不触碰** | `sandbox/`, `arena.rs`, `mcp.rs` |
| **规范** | `design/engine.md` §3.4.5 |

**实现内容：**

1. Deploy pipeline：上传 → 验证(sandbox 预编译) → commit → activate
2. 版本化 module 存储
3. `swarm_deploy_module` MCP tool

**验收标准：** `cargo build && cargo test --lib`，deploy flow 端到端测试 ≥ 2 个。

### T11b — P1-7: Command Source Gate

| 属性 | 值 |
|------|-----|
| **文件** | `src/security.rs`（增强已有 515 行文件）、`src/command.rs`（集成点） |
| **规范** | `specs/security/09-command-source.md` |

**实现内容：**

1. MCP-only command injection（拒绝非 MCP 来源的 CommandAction）
2. `CommandSource` 枚举 → 每个 command 标记来源
3. Source gate 在 command validation 阶段执行

**验收标准：** `cargo build && cargo test --lib`，非 MCP 来源拒绝测试 ≥ 2 个。

### T11c — P2-7: Economy Balance 测试

| 属性 | 值 |
|------|-----|
| **文件** | `tests/economy_balance.rs`（**新建**） |
| **不触碰** | 任何 `src/` 文件 |
| **规范** | `design/economy-balance-sheet.md` |

**实现内容：**

1. 1 room break-even 测试
2. 5 rooms break-even 测试
3. 20 rooms break-even 测试
4. 50 rooms break-even 测试
5. 资源流动闭环验证（产出→存储→消耗→产出）

**验收标准：** `cargo test --lib` + 新集成测试通过，各规模 break-even 断言。

---

## Wave 12: P5 Benchmark Gates

**并行度: 7（全部新建 bench 文件，互不重叠）**

所有 benchmark 放入 `benches/` 目录，添加 `criterion` 依赖到 `Cargo.toml`。

| ID | 名称 | 文件 | 规范 | 指标 |
|----|------|------|------|------|
| P5-1 | Command Loop | `benches/command_loop.rs` | `05-persistence-contract.md` §8.3 | 100k validate p99<50ms, apply p99<100ms |
| P5-2 | Snapshot Clone/Restore | `benches/snapshot_bench.rs` | 同上 | 50k entities clone<20ms, restore<30ms |
| P5-3 | FDB Single-TX | `benches/fdb_bench.rs` | 同上 | 500 players p99<200ms, conflict<1% |
| P5-4 | FDB Room-Partition | `benches/room_partition.rs` | 同上 §8.1 | Room-level FDB + 2PC |
| P5-5 | Pathfinding | `benches/pathfinding.rs` | 同上 §8.3 | 50×50 A\*, fair-share |
| P5-6 | Rollback Snapshot | `benches/rollback.rs` | 同上 | 500 entities 全组件 |
| P5-7 | Load Test 1000 Players | `benches/load_test.rs` | `engine.md` §3.4.2 | p99<500ms |

**依赖**: W11（P2-7 经济测试完成——需要完整的经济系统）。

**验收标准**（所有 P5）：

```
cargo bench（所有 benchmark 运行通过）
P5-1: p99 validate < 50ms, apply < 100ms
P5-3: p99 < 200ms, conflict < 1%
P5-7: 1000 players p99 < 500ms
git push origin main
```

---

## Milestones

| Milestone | 判定 | 包含 Wave |
|-----------|------|----------|
| **M1: Core Complete** | 全部 P0 任务闭合 | W1 |
| **M2: World Economy** | P2-1..P2-8 全部完成 + 经济测试通过 | W2-W6 + W11c |
| **M3: Gameplay Complete** | P3-1..P3-8 全部完成 | W7-W9 |
| **M4: Arena Works** | P4-1..P4-5 全部完成 | W10 |
| **M5: Auth & DevOps** | P1-6 + P1-7 完成 | W11a-b |
| **M6: Scale Verified** | P5-1..P5-7 全部 benchmark 通过 | W12 |
