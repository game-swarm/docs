# Swarm Implementation ROADMAP

> 仅列出待实现变更。文件互斥：同一 Wave 内任务触碰的文件集完全不相交。
> 路径前缀：`engine:` = `/data/swarm/engine/src/`，`sandbox:` = `/data/swarm/sandbox/`，`docs:` = `/data/swarm/docs/`。
> 系统编号以 `specs/core/06-phase2b-system-manifest.md` 为唯一权威来源。

---

## Wave 依赖图

```
W1 (P0-6)
 │
 ├─► W2 (P2-1) ─► W3 (P2-3) ─► W4 (P2-2) ─► W5 (P2-5) ─► W6 (P2-8)
 │
 └─► W7 (P3-1 ‖ P3-6) ─► W8 (S09+S10 stubs) ─► W9 (P3-2+P3-4) ─► W10 (P3-5)
                              │
                              └─► W11 (P3-7) ─► W12 (Status 1/2) ─► W13 (Status 2/2)
                                                       │
                                                       └─► W14 (P3-8)
                                                                │
                                                                └─► W15 (P4-1..P4-5)
                                                                         │
                                                                         └─► W16 (P2-7 ‖ P1-7 ‖ P1-6)
                                                                                  │
                                                                                  └─► W17 (P5-1..P5-7)
```

W2-W6 严格串行（均触碰 `engine:world.rs` + `engine:lib.rs`）。
W1 独立；W7-W15 为游戏系统链，依赖 W6（需要完整 Resource Ledger）；W16-W17 为基准验证层。

---

## Wave 1: P0-6 Snapshot 构建器

**并行度: 1**

### T1 — P0-6 Snapshot Builder

| 属性 | 值 |
|------|-----|
| **仓库** | `engine` |
| **文件** | `engine:sim.rs`（72 行 stub → 完整实现）、`engine:tick.rs`（集成点）、`engine:lib.rs`（确认注册） |
| **不触碰** | `engine:world.rs`, `engine:scheduler.rs`, `engine:systems/mod.rs`, `engine:components.rs`, `engine:command.rs` |
| **规范** | `specs/core/09-snapshot-contract.md`（主要）、`specs/security/05-visibility.md`（fog_of_war 裁剪）、`specs/core/01-tick-protocol.md` §2.3（快照构建阶段） |
| **依赖** | 无 |

**实现内容：**

1. `engine:sim.rs`：`fog_of_war_filter(player_id, world) → Snapshot`（按 `05-visibility.md` 裁剪不可见 entity）、`collect_snapshot(world, player_ids) → Vec<(PlayerId, Snapshot)>`
2. `engine:tick.rs`：COLLECT → [Snapshot] → EXECUTE 流程集成
3. Capacity Admission stub（存储 SLO 配置，调参留待 P5 验证）
4. 性能目标：50k entities snapshot < 20ms（P5-2 验证）

**验收：** `cargo test --lib` 新增 snapshot 测试 ≥ 3 个

---

## Wave 2: P2-1 Resource Ledger 核心

**并行度: 1**

### T2 — P2-1 Resource Ledger

| 属性 | 值 |
|------|-----|
| **仓库** | `engine` |
| **文件** | `engine:resources.rs`、`engine:economy.rs`、`engine:world.rs`（新增 `[resources]` 配置节）、`engine:lib.rs` |
| **不触碰** | `engine:command.rs`, `engine:scheduler.rs`, `engine:systems/mod.rs`, `engine:components.rs` |
| **规范** | `specs/core/08-resource-ledger.md` §1-§2 |
| **依赖** | W1 |

**实现内容：**

1. Transfer Gateway（玩家间资源转移入口）
2. 定点费率（per-resource transfer cost）
3. Storage tax（每 tick 按存储量征税）
4. `world.toml` `[resources]` 配置节

**验收：** `cargo test --lib` 新增 ≥ 5 个测试

---

## Wave 3: P2-3 PvE Budget

**并行度: 1**

### T3 — P2-3 PvE Budget 分配

| 属性 | 值 |
|------|-----|
| **仓库** | `engine` |
| **文件** | `engine:pve.rs`、`engine:world.rs`（新增 `[pve_budget]` 配置）、`engine:lib.rs` |
| **不触碰** | `engine:resources.rs`, `engine:economy.rs`, `engine:systems/`, `engine:command.rs` |
| **规范** | `specs/core/08-resource-ledger.md` §3 |
| **依赖** | W2（需要 Resource Ledger 的 `PvEAward` 操作） |

**实现内容：**

1. 4 维 Budget：GlobalBudget / ZoneBudget / PlayerBudget / EventBudget
2. 每 tick 按比例分配 PvE 产出到各预算池
3. `world.toml` `[pve_budget]` 节

**验收：** `cargo test --lib` 新增 ≥ 3 个测试

---

## Wave 4: P2-2 Empire Upkeep

**并行度: 1**

### T4 — P2-2 Empire Upkeep 超线性维护

| 属性 | 值 |
|------|-----|
| **仓库** | `engine` |
| **文件** | `engine:systems/memory_upkeep_system.rs`（23 行 stub → 完整）、`engine:world.rs`（新增 `[empire_upkeep]` 配置）、`engine:lib.rs` |
| **不触碰** | `engine:resources.rs`, `engine:economy.rs`, `engine:components.rs`, `engine:command.rs` |
| **规范** | `specs/core/08-resource-ledger.md` §Empire Upkeep、§2.4（Controller Repair）、§2.5（Recycle Refund） |
| **依赖** | W2（需要 Resource Ledger 的 `UpkeepDeduction` 操作） |

**实现内容：**

1. 维护费公式（按 spec 权威公式）：**`cost = base_upkeep × rooms × (1 + rooms / room_soft_cap)`**，默认 `base_upkeep=50`, `room_soft_cap=10`
2. Deficit 惩罚（资源不足时衰减 RCL、减少产能）
3. **Controller Repair 公式**（`specs/core/08-resource-ledger.md` §2.4）：`repair_cost = body_cost × (1 - repair_cap/10000) × (1 + distance × distance_decay_bp/10000)`，`repair_cap=3500bp(35%)`, `distance_decay_bp=500bp(5%/tile)`
4. **Recycle Refund 公式**（§2.5）：`refund = body_cost × remaining_lifespan/total_lifespan × recycle_refund_base/10000`，下限 `recycle_refund_min=1000bp(10%)`
5. `world.toml` `[empire_upkeep]` 配置节

**验收：** `cargo test --lib` 新增 ≥ 6 个测试（维护费、超线性增长、deficit、repair、recycle、零 entity）

---

## Wave 5: P2-5 Starting Resources

**并行度: 1**

### T5 — P2-5 Starting Resources & Free Upkeep

| 属性 | 值 |
|------|-----|
| **仓库** | `engine` |
| **文件** | `engine:resources.rs`、`engine:economy.rs`、`engine:world.rs`（新增配置）、`engine:lib.rs` |
| **不触碰** | `engine:command.rs`, `engine:memory_upkeep_system.rs`, `engine:scheduler.rs` |
| **规范** | `specs/core/08-resource-ledger.md` §2.3 |
| **依赖** | W4（需要 EmpireUpkeep 运行后才能免维护费） |

**实现内容：**

1. `starting_resources`（默认 Energy 5000 + Minerals 2000）
2. `free_upkeep_controllers: 1`、`free_upkeep_drones: 3`、`free_upkeep_ticks: 2000`

**验收：** `cargo test --lib` 新增 ≥ 3 个测试

---

## Wave 6: P2-8 Allied Transfer

**并行度: 1**

### T6 — P2-8 Allied Transfer & Anti-Smurf

| 属性 | 值 |
|------|-----|
| **仓库** | `engine` |
| **文件** | `engine:command.rs`（新增 TransferToPlayer CommandAction）、`engine:resources.rs`、`engine:world.rs`（配置）、`engine:lib.rs` |
| **不触碰** | `engine:economy.rs`, `engine:systems/`, `engine:scheduler.rs` |
| **规范** | `specs/core/08-resource-ledger.md` §2.1、§3.2 |
| **依赖** | W5（需要完整 Resource Ledger） |

**实现内容：**

1. `TransferToPlayer` CommandAction（target_player, resource, amount）
2. 200bp transfer fee
3. Transfer cooldown（per-player-pair）
4. Identity binding（防 smurf 小号）

**验收：** `cargo test --lib` 新增 ≥ 4 个测试

---

## Wave 7: P3-1 Combat + P3-6 Visibility

**并行度: 2**（文件互不相交）

### T7a — P3-1 Combat Pipeline

| 属性 | 值 |
|------|-----|
| **仓库** | `engine` |
| **文件** | `engine:systems/combat_system.rs`（**仅此文件**，274 行 16 fn） |
| **不触碰** | `engine:scheduler.rs`, `engine:systems/mod.rs`, `engine:lib.rs`, `engine:world.rs`, `engine:command.rs` |
| **规范** | `specs/core/06-phase2b-system-manifest.md` §S11-S13 |

**实现：** Melee（range=1 body_part_damage）、Ranged（projectile 投递）、Heal（ally targeting）
**验收：** 测试 ≥ 8 个（+3）

### T7b — P3-6 Visibility + Oracle 防线

| 属性 | 值 |
|------|-----|
| **仓库** | `engine` |
| **文件** | `engine:visibility.rs`（**仅此文件**，267 行 18 fn） |
| **不触碰** | `engine:scheduler.rs`, `engine:systems/mod.rs`, `engine:lib.rs`, `engine:world.rs` |
| **规范** | `specs/security/05-visibility.md`（全规范，含 §6 特殊攻击可见性、§10 Oracle 防线） |

**实现：**
1. Drone perception 半径、Player camera 视野裁剪、Spectate 模式
2. **Oracle 防线**（§10）：`omitted_count` 分桶脱敏（few/some/many/extreme）、拒绝码等价策略（统一 NotVisibleOrNotFound）、dry_run 脱敏
3. 特殊攻击可见性规则（§6）：Overload/Hack 双视角可观察性定义

**验收：** 测试 ≥ 8 个（+3）

---

## Wave 8: S09 + S10 系统增强

**并行度: 1**（两文件均触碰 `engine:systems/mod.rs` + `engine:lib.rs`）

### T8 — spawning_grace (S09) + regeneration (S10)

| 属性 | 值 |
|------|-----|
| **仓库** | `engine` |
| **文件** | `engine:systems/spawning_grace_system.rs`（21 行 stub → 完整）、`engine:systems/regeneration_system.rs`（43 行 thin → 完整）、`engine:systems/mod.rs`、`engine:scheduler.rs`、`engine:lib.rs` |
| **不触碰** | `engine:world.rs`, `engine:components.rs`, `engine:command.rs`, `engine:combat_system.rs` |
| **规范** | `specs/core/06-phase2b-system-manifest.md` §S09（SpawningGrace：出生 tick 无敌）、§S10（Regeneration：先于 damage_application 执行，`Without<DeathMark>` filter） |

**实现内容：**

1. **S09 SpawningGrace**：新生 drone 附加 `SpawningGrace{remaining:1}` 组件，当前 tick 内免疫伤害——修复"出生即斩"漏洞（R16 B2）
2. **S10 Regeneration**：自然回复先于伤害结算，使用 `Without<DeathMark>` filter 防 double-dip
3. 在 `scheduler.rs` 中正确排序（S09→S10→combat→damage）

**验收：** `cargo test --lib` 新增 ≥ 4 个测试（出生保护、protection 到期、regen 先于 damage、已死亡 entity 不再回复）

---

## Wave 9: P3-2 + P3-4

**并行度: 1**（两任务触碰 `engine:systems/mod.rs` + `engine:lib.rs`）

### T9 — Special Attack Reducer (S14) + Damage Application (S15)

| 属性 | 值 |
|------|-----|
| **仓库** | `engine` |
| **文件** | `engine:systems/special_attack_reducer.rs`（**新建** — S14）、`engine:systems/death_mark_system.rs`（28 行 → 重命名为 damage_application 逻辑 — S15）、`engine:systems/mod.rs`、`engine:scheduler.rs`、`engine:lib.rs` |
| **不触碰** | `engine:world.rs`, `engine:components.rs`, `engine:command.rs`, `engine:combat_system.rs` |
| **规范** | `specs/core/06-phase2b-system-manifest.md` §S14（Intent Collect→Canonical Sort→Deliver，不直接修改实体状态）、§S15（PendingDamage buffer→Resistance→DeathMark） |

**实现内容：**

1. **S14 Special Attack Reducer**：Intent Collect（收集所有玩家 special_attack intent）→ Canonical Sort（优先级+确定性 shuffle）→ Deliver（交付给 S22 status_advance）。不直接修改实体状态。
2. **S15 Damage Application**：PendingDamage buffer（收集 combat 产出的 damage）→ Resistance 减伤计算 → 实际伤害应用 → DeathMark（血量 ≤0 标记）
3. 在 `scheduler.rs` 注册两系统（S14→S22→S15 链路）

**验收：** ≥ 7 个测试（Intent 收集、排序确定性、多玩家并发、PendingDamage、resistance 减伤、DeathMark、零伤害）

---

## Wave 10: P3-5 Aging & Death

**并行度: 1**

### T10 — Aging (S23) + Death Cleanup (S25)

| 属性 | 值 |
|------|-----|
| **仓库** | `engine` |
| **文件** | `engine:systems/aging_system.rs`（**新建** — S23）、`engine:systems/death_cleanup_system.rs`（9 行 stub → 完整 — S25）、`engine:systems/death_mark_system.rs`（补充 DeathMark 组件）、`engine:systems/mod.rs`、`engine:scheduler.rs`、`engine:lib.rs`、`engine:components.rs`（新增 Lifespan 组件） |
| **不触碰** | `engine:world.rs`, `engine:command.rs`, `engine:combat_system.rs` |
| **规范** | `specs/core/06-phase2b-system-manifest.md` §S23（Lifespan + ActiveAging）、§S25（Death Cleanup） |

**实现内容：**

1. **S23 Aging**：`Lifespan` 组件（entity 固有寿命 tick 数）、`ActiveAging`（条件效果加速老化）
2. **S25 Death Cleanup**：清理 DeathMark entity（释放资源、移除组件、更新计数）
3. `components.rs` 新增 `Lifespan`、`ActiveAging` 组件定义

**验收：** ≥ 5 个测试（寿命到期死亡、active aging 加速、death cleanup 资源释放、多 entity 并发老化、已清理 entity 不可查询）

---

## Wave 11: P3-7 Body Part Match

**并行度: 1**

### T11 — Body Part Match (S20 disrupt 依赖)

| 属性 | 值 |
|------|-----|
| **仓库** | `engine` |
| **文件** | `engine:systems/combat_system.rs`（新增 body_part_match 函数）、`engine:command.rs`（新增 DisruptedResisted 拒绝原因） |
| **不触碰** | `engine:scheduler.rs`, `engine:systems/mod.rs`, `engine:lib.rs`, `engine:world.rs`, `engine:components.rs` |
| **规范** | `specs/core/06-phase2b-system-manifest.md` §S20（Body Part Match Requirement）、设计决策 D3/A |
| **依赖** | W7（P3-1 Combat 完成） |

**实现内容：**

1. Disrupt special attack 的 body part match 验证
2. 目标 body part 指定（如 Disrupt→head）
3. 匹配成功→交付 S22；失败→`DisruptedResisted` 拒绝

**验收：** ≥ 3 个测试（匹配成功、不匹配拒绝、无目标 body part 跳过）

---

## Wave 12: P3-3 Status Effects（上）— Hack + Overload + Drain

**并行度: 1**

### T12 — Status Effects Part 1: S16 Hack + S18 Overload + S17 Drain

| 属性 | 值 |
|------|-----|
| **仓库** | `engine` |
| **文件** | `engine:systems/hack_system.rs`（**新建** — S16）、`engine:systems/overload_system.rs`（**新建** — S18）、`engine:systems/drain_system.rs`（**新建** — S17）、`engine:systems/mod.rs`、`engine:scheduler.rs`、`engine:lib.rs`、`engine:components.rs`（新增 StatusState 组件 + 各 status 标记组件） |
| **不触碰** | `engine:world.rs`, `engine:command.rs`, `engine:combat_system.rs` |
| **规范** | `specs/core/06-phase2b-system-manifest.md` §S16-S18（Hack/Drain/Overload，parallel set B，disjoint targets） |

**实现内容：**

1. **S16 Hack**：目标 Drone 被临时控制，攻击盟友
2. **S18 Overload**：目标结构过载，造成范围伤害
3. **S17 Drain**：吸取目标资源转移给攻击者
4. 三个系统属于 parallel set B——目标 disjoint，可安全并行执行
5. `components.rs` 新增 `StatusState`、`Hacked`、`Overloaded`、`Draining` 组件

**验收：** 每个系统 ≥ 2 个测试（共 ≥ 6 个）

---

## Wave 13: P3-3 Status Effects（下）— Debilitate + Disrupt + Fortify + status_advance

**并行度: 1**

### T13 — Status Effects Part 2: S19 + S20 + S21 + S22

| 属性 | 值 |
|------|-----|
| **仓库** | `engine` |
| **文件** | `engine:systems/debilitate_system.rs`（**新建** — S19）、`engine:systems/disrupt_system.rs`（**新建** — S20）、`engine:systems/fortify_system.rs`（**新建** — S21）、`engine:systems/status_advance_system.rs`（**新建** — S22）、`engine:systems/mod.rs`、`engine:scheduler.rs`、`engine:lib.rs`、`engine:components.rs` |
| **不触碰** | `engine:world.rs`, `engine:command.rs`, `engine:combat_system.rs` |
| **规范** | `specs/core/06-phase2b-system-manifest.md` §S19-S22（Debilitate/Disrupt/Fortify/status_advance） |
| **依赖** | W12（Status Part 1 完成——需要 StatusState 组件和 S22 的 Unique Writer Contract） |

**实现内容：**

1. **S19 Debilitate**：削弱目标属性
2. **S20 Disrupt**：打断目标行动（需 body part match — 依赖 W11）
3. **S21 Fortify**：临时防御强化
4. **S22 status_advance**：**Unique Writer**——唯一写入所有 StatusState 组件的系统。统一读入 intent → 更新 StatusState（duration--, expire, apply）→ 触发 damage
5. 排序：S14（reducer）→ S22（status_advance）→ S15（damage_application）

**验收：** 每个系统 ≥ 2 个测试（共 ≥ 8 个）+ S22 unique writer 合约验证

---

## Wave 14: P3-8 Feedback Loop

**并行度: 1**

### T14 — EventLog + MCP/WebSocket 推送

| 属性 | 值 |
|------|-----|
| **仓库** | `engine` |
| **文件** | `engine:event_log.rs`（**新建**）、`engine:mcp.rs`（新增 `swarm_get_snapshot`、`swarm_explain_last_tick` push）、`engine:realtime.rs`（WebSocket 推送）、`engine:systems/mod.rs`、`engine:scheduler.rs`、`engine:lib.rs`、`engine:components.rs`（新增 EventLog 组件） |
| **不触碰** | `engine:world.rs`, `engine:command.rs`, `engine:combat_system.rs` |
| **规范** | `specs/gameplay/06-feedback-loop.md`（全规范） |
| **依赖** | W13（Status 完整后才能产生有意义的事件） |

**实现内容：**

1. `EventLog` 组件（per-tick 事件：damage_taken, status_applied, death 等）
2. `swarm_get_snapshot`、`swarm_explain_last_tick` MCP tool
3. WebSocket 实时推送
4. 事件保留策略（最近 N tick，超出丢弃）

**验收：** ≥ 4 个测试（EventLog 创建、MCP 推送、WebSocket 推送、过期清理）

---

## Wave 15: P4 Arena Mode

**并行度: 1**（5 任务串行，全部修改 `engine:arena.rs`）

| # | 任务 | 规范 | 说明 |
|---|------|------|------|
| T15a | **P4-1** Room 创建 & 配置 | `design/modes.md` §9.1 | Create room + 参数 + lock slots |
| T15b | **P4-2** WASM Precommit | `design/modes.md` §9.1.2 | Module hash lock per slot + precommit 流程 |
| T15c | **P4-3** Match Lifecycle | `design/modes.md` §9.1.3 | Create→Configure→Ready→Play→Finish→Replay |
| T15d | **P4-4** Social Replay | `design/modes.md` §9.1.4 | Delayed public spectator + replay URL |
| T15e | **P4-5** Local Replay | `specs/core/05-persistence-contract.md` §5 | Deterministic replay verifier |

**文件集：** T15a-c 仅 `engine:arena.rs`；T15d 增加 `engine:replay_storage.rs`；T15e 增加 `engine:tick.rs`

**验收：** arena 测试 ≥ 8 个（+5）、replay 测试 ≥ 3 个

---

## Wave 16: P2-7 + P1-7 + P1-6

**并行度: 3**（文件互不相交：`tests/`、`engine:security.rs+command.rs`、`engine:wasm_deploy.rs+lib.rs`）

### T16a — P2-7 Economy Balance 验证

| 属性 | 值 |
|------|-----|
| **仓库** | `engine` |
| **文件** | `engine:tests/economy_balance.rs`（**新建**，不触碰任何 `engine:src/` 文件） |
| **规范** | `design/economy-balance-sheet.md` |
| **依赖** | W6（需要完整经济系统） |

**实现：** 1/5/20/50 rooms 验证维护费超线性增长曲线与 balance sheet 预测一致（注意：balance sheet 显示全规模净亏损，break-even 需靠 RCL 升级）
**验收：** 各规模维护费曲线验证通过

### T16b — P1-7 Command Source Gate

| 属性 | 值 |
|------|-----|
| **仓库** | `engine` |
| **文件** | `engine:security.rs`（已有 515 行，增强）、`engine:command.rs`（集成点） |
| **不触碰** | `engine:lib.rs`, `engine:world.rs`, `engine:scheduler.rs` |
| **规范** | `specs/security/09-command-source.md` §4-§8 |

**实现：**
1. `CommandSource` 枚举 → 每个 command 标记来源
2. Source gate 在 validation 阶段拒绝非 MCP 来源的 CommandAction
3. Ed25519 证书链验证、CRL 吊销检查、version_counter 防重放
4. Session 状态机、确定性吊销

**验收：** ≥ 6 个测试（非 MCP 来源拒绝、audience 不匹配、stale version_counter、吊销证书、transport header 缺失、epoch bump）

### T16c — P1-6 WASM CDN 部署流

| 属性 | 值 |
|------|-----|
| **仓库** | `engine` |
| **文件** | `engine:wasm_deploy.rs`（**新建**）、`engine:lib.rs` |
| **不触碰** | `engine:security.rs`, `engine:command.rs`, `engine:arena.rs`, `sandbox:` |
| **规范** | `specs/security/09-command-source.md` §1-§3（deploy pipeline、certificate chain、version_counter）、`specs/core/05-persistence-contract.md` §2.3 |
| **依赖** | W1（需要引擎基础），**不依赖 Arena** |

**实现：**
1. Deploy pipeline：上传→验证（sandbox 预编译）→commit→activate
2. 版本化 module 存储
3. `swarm_deploy_module` MCP tool
4. CodeSigningCertificate 验证、防重放（version_counter）

**验收：** ≥ 3 个 deploy flow 端到端测试

---

## Wave 17: P5 Benchmark Gates

**并行度: 7**（全部新建 `engine:benches/` 文件，互不重叠）

添加 `criterion` 依赖到 `engine:Cargo.toml`。

| ID | 名称 | 文件 | 规范 | 指标 |
|----|------|------|------|------|
| P5-1 | Command Loop | `engine:benches/command_loop.rs` | `05-persistence-contract.md` §8.3 | 100k validate p99<50ms, apply<100ms |
| P5-2 | Snapshot Clone/Restore | `engine:benches/snapshot_bench.rs` | 同上 | 50k entities clone<20ms, restore<30ms |
| P5-3 | FDB Single-TX | `engine:benches/fdb_bench.rs` | 同上 | 500 players p99<200ms, conflict<1% |
| P5-4 | FDB Room-Partition | `engine:benches/room_partition.rs` | 同上 §8.1 | Room-level FDB + 2PC |
| P5-5 | Pathfinding | `engine:benches/pathfinding.rs` | 同上 §8.3 | 50×50 A\*, fair-share |
| P5-6 | Rollback Snapshot | `engine:benches/rollback.rs` | 同上 | 500 entities 全组件 |
| P5-7 | Load Test | `engine:benches/load_test.rs` | `design/engine.md` §3.4.2 | 1000 players p99<500ms |

**依赖：** W16（需要完整功能实现）
**验收：** `cargo bench` 全部通过，P5-1/P5-3/P5-7 满足 p99 指标

---

## Milestones

| Milestone | 判定 | 包含 Wave |
|-----------|------|----------|
| **M1: Core Complete** | P0-6 闭合 | W1 |
| **M2: World Economy** | P2-1..P2-8 全部 + 经济测试 | W2-W6 + W16a |
| **M3: Gameplay Complete** | P3-1..P3-8 全部 + S09+S10 | W7-W14 |
| **M4: Arena Works** | P4-1..P4-5 全部 | W15 |
| **M5: Auth & DevOps** | P1-6 + P1-7 | W16b-c |
| **M6: Scale Verified** | P5-1..P5-7 benchmark 全部通过 | W17 |
