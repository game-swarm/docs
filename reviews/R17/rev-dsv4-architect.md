# R17 架构评审 — Architect (DSV4)

**评审员**: rev-dsv4-architect (DeepSeek V4 Pro)
**评审方向**: Architect — ECS 调度、Tick 生命周期完整性、数据一致性、算法复杂度
**评审日期**: 2026-06-18

---

## Verdict

**REQUEST_MAJOR_CHANGES**

R15-R16 后文档质量显著提升：ECS 调度清单完整（29 systems）、Phase 2a/2b 分离清晰、持久化双写语义正确、R/W 矩阵覆盖全面。但本次发现 2 个 Critical 不一致（含 "单事实源" 原则自身被违反）与 1 个 Critical 并行安全疑点，必须修正后方可进入实现阶段。

---

## 发现问题

### Critical

#### C1: api_version 跨权威源不一致 — 单事实源原则被违反

| 位置 | 值 |
|------|-----|
| `specs/reference/api-registry.md` 头部 | `当前 API 版本: 0.1.0` |
| `specs/reference/game_api.idl.yaml` 头部 | `api_version: "0.2.0"` |

api-registry.md 自身声明为「单一权威来源」且规定「冲突时以 YAML 为准」，但其 Markdown 头部声明的 0.1.0 与 YAML 的 0.2.0 不一致。TickTrace 记录 `api_version` 和 `core_idl_version` 字段——实现者看到哪个版本号取决于他们读哪个文件。这是 "单事实源" 架构原则下的 critical 自伤。

**修复建议**: Markdown 头部改为 `0.2.0`，或在变更记录中同步。

#### C2: Snapshot 截断优先级模型在 engine.md 与 01-tick-protocol.md 之间结构性不一致

| 文档 | 优先级模型 | 结构 |
|------|-----------|------|
| `engine.md` §3.4.4 | 自机 > 友方 drone > 敌方 drone > 建筑 > NPC > 资源 | 6 级线性 |
| `specs/core/01-tick-protocol.md` §2.3 | 关键桶（Spawn/Controller/depot/storage；无条件保留） → 高优先桶（己方 drone/己方建筑） → 中优先桶（敌方可见实体/资源点） → 低优先桶（友方实体/中立实体） | 4 级桶 + 关键桶特殊语义 |

两者在三个维度上冲突：

1. **Spawn/Controller/depot/storage 的特殊地位**：01-tick-protocol.md 将其置于「关键桶——永不截断」，engine.md 未提及此分类，仅按 owner 关系线性排列。
2. **友方实体的归属**：engine.md 的「友方 drone」在第二优先级，01-tick-protocol.md 将「友方实体」置于最低桶（低优先桶）。同一玩家盟友的 drone 在两个模型中的优先级完全不同。
3. **NPC 的位置**：engine.md 有「NPC」分类（倒数第二），01-tick-protocol.md 无此分类，NPC 归入「中立实体」（最低桶）。

截断是可见性系统的核心——决定哪些实体进入 WASM tick(snapshot)。两个不同截断模型会导致 replay 非确定性：同一 tick 同一玩家，按 engine.md 和按 01-tick-protocol.md 截断会产生不同 snapshot 内容。需权威化单一模型。

**修复建议**: 选择 01-tick-protocol.md 的 4 桶模型（更精细、有关键桶保证），废弃 engine.md 的 6 级线性模型。将确定后的权威模型迁移至 api-registry.md 或独立的 spec。

#### C3: Phase 2b Status Effects Parallel Set B (S16-S22) 并行安全声明可能无效

`specs/core/06-phase2b-system-manifest.md` §2 声明 S16-S22 可并行执行，理由是「各 system 写入互不重叠的 StatusState 子类型」且「status_advance_system 与其他 system 无冲突（不同 component 实例）」。

但读 §4 R/W 矩阵：

- S16 hack_system → W: StatusState
- S17 drain_system → W: StatusState
- S18 overload_system → W: StatusState
- S19 debilitate_system → W: StatusState
- S20 disrupt_system → W: StatusState
- S21 fortify_system → W: StatusState
- S22 status_advance_system → W: StatusState

全部 7 个 system 在 R/W 矩阵中写入同一个 `StatusState` 列。若 `StatusState` 是单一 Component 类型（含 subtype enum），则 S22 的 duration 递减（duration--, expire）与 S16 的 stage++ 操作同一 component 的不同字段——在 ECS 语义下这是**同一个 archetype column 的并行写**。Bevy 的并行调度要求 `Query<&mut T>` 在 entity 级别互斥；若 S16 和 S22 操作同一 entity 的同一 component，构成数据竞争。

**关键问题**：
- "不同 component 实例" 是指每个 StatusState subtype 是独立的 Bevy Component 类型（HackStateComponent ≠ DrainStateComponent），还是同一个 `StatusState` enum component 的不同 variant？
- 若是后者（同一 Component 类型），并行不安全。
- 若是前者（独立 Component 类型），R/W 矩阵的 `StatusState` 列应拆分为 `HackState`、`DrainState`、`OverloadState` 等独立列，且 S22 的行应标注为全部写入。

**修复建议**: 在 manifest 中明确 StatusState subtype 是独立 Component 类型还是单一 Component 的 variant。若为独立类型，拆分 R/W 矩阵列。若为单一 variant，S16-S22 必须串行化或 partition by entity_id。

### High

#### H1: Phase 2b combat 系统命名与实际功能不匹配

`06-phase2b-system-manifest.md` 中：
- S11 `attack_system` — 写入 HitPoints
- S12 `ranged_attack_system` — 写入 HitPoints
- S13 `heal_system` — 写入 HitPoints

但 `engine.md` §3.2 明确：Phase 2a 命令已直接应用玩家 Attack/RangedAttack/Heal 的伤害/治疗。Phase 2b 的 S11-S13 仅处理**非玩家**战斗（Tower 自动攻击、DoT、NPC 战斗）。

命名 `attack_system` 会误导实现者为 "所有攻击系统"——与 Phase 2a 内联 Attack 混淆。文档读者（尤其是只看 manifest 不看 engine.md 交叉引用的读者）会被误导。

**修复建议**: 重命名为 `tower_attack_system`、`npc_ranged_attack_system`、`field_heal_system` 或类似区分名称。在 manifest S11-S13 的 Note 中明确标注 "仅处理非玩家来源的战斗，玩家 Attack/RangedAttack/Heal 已在 Phase 2a inline 应用"。

#### H2: S06 spawn_validator 的 RoomCap 读取与 Phase 2b 写入之间的时序错位

| 系统 | 阶段 | RoomCap 操作 |
|------|------|-------------|
| S06 spawn_validator | Phase 2a inline | **R** — 读取 RoomCap 校验 spawn 准入 |
| S07 death_marker | Phase 2b deferred | **W** — 释放 RoomCap 槽位 |
| S08 spawn_system | Phase 2b deferred | **W** — 消费 RoomCap 槽位 |

S06 在 Phase 2a 读取 RoomCap 判断是否有空闲槽位。但 Phase 2a 与 Phase 2b 之间存在时间差——S06 执行时，Phase 2b 的 death_marker（S07）尚未释放本 tick 将要死亡的 drone 占用的槽位。

这意味着：**S06 的 RoomCap 检查基于过时数据**。若房间已达到 drone cap 上限且同 tick 有其他 drone 死亡（将在 S07 释放槽位），S06 会错误拒绝本应成功的 Spawn 命令——因为那些槽位在 S07 运行后就空闲了。

当前设计的文档声称 "death_marker 在 spawn 之前 → RoomCap 同 tick 释放"——这是正确的 Phase 2b 内时序。但 **Phase 2a 的 S06 不参与此优化**——它在 S07 之前执行，看不到即将释放的槽位。

**影响**：高 drone 密度场景下，已达 room cap 上限的房间中，死亡 drone 的槽位无法在同 tick 被复用——新 Spawn 被多延迟一个 tick。这不是数据损坏，是**吞吐量退化**。

**修复建议**：选项 A — 将 RoomCap 释放逻辑提前到 Phase 2a death_marker 等价阶段（增加 Phase 2a 复杂度）；选项 B — 接受此退化并文档化：S06 的 RoomCap 读取是对 Phase 2a 开始时的保守估计，同 tick 死亡释放的槽位将在下一 tick 可用。建议当前阶段选 B，在 manifest 中标注此已知限制。

#### H3: MCP WebSocket seq 单调递增的跨连接语义缺失

`specs/reference/api-registry.md` §3.4 规定 Agent WS 使用 `seq + MAC (ed25519)` 防重放，`seq 必须 > 上次接收值，否则断开`。

未定义的是：`上次接收值` 是 per-connection 还是 per-player 全局？若为 per-connection：
- 断开重连后 seq 从 0 重新开始 → 攻击者可重放旧消息（重连绕过）。
- 需要服务端持久化 `last_seq` 并跨连接保持。

若为 per-player 全局持久化，需要明确：
- 存储位置（FDB？Dragonfly？）
- 持久化粒度（per-tick 同步写入？允许滞后？）
- 滞后窗口内的重放风险

**修复建议**: 明确 `last_seq` 为 per-player 全局，在 FDB 中与 player state 一同持久化（同一 tick 事务内），断开重连后继续递增。

### Medium

#### M1: engine.md 的 ECS 系统数量描述过时

`engine.md` §3.2 中 Phase 2b 的 ECS Systems 只列举了 12 个系统名（death_marker → spawn → spawning_grace → regen → combat → spec_atk_red → dmg_apply → status → aging → decay → death_cleanup），但权威 manifest 实际定义了 23 个 Phase 2b 系统。虽然 engine.md 有指向 manifest 的引用，但内联列举容易让快速浏览的开发者低估系统复杂度。

**修复建议**: 删除 engine.md 中的内联列表，全部替换为 "详见 Complete Tick Execution Manifest"。

#### M2: active_players=0 的除零保护仅在 engine.md 提到

Fair-share admission 公式 `floor(global_budget / active_players)` 在 api-registry.md §5.2 和 01-tick-protocol.md §8 中均未提及 active_players=0 时的行为。仅 engine.md §3.4.2 有 "若 active_players 为 0，不执行分配"。作为容量合同的关键边界条件，应在 api-registry.md（权威源）中记录。

#### M3: room_state_system (S27) 功能定义过于模糊

`06-phase2b-system-manifest.md` §2 S27 的描述仅有 "Reads: Room, Entity, Controller; Writes: Room (state, controller_level), EventLog"。从 engine.md §3.1a 看，room state 涉及 neutral/reserved/owned/contested/abandoned 五种状态的复杂转换，contested mode 的 net progress 计算、reserved 超时回退等——这些逻辑完全未在 manifest 中体现。S27 是 Room 状态机的实现入口，其复杂度超过了 manifest 中所有其他 serial 系统。

**修复建议**: S27 应拆分为多个子系统或至少扩展 manifest 中的描述，覆盖状态转换矩阵的所有分支。

#### M4: Keyframe GC 策略存在覆盖缺口

`specs/core/05-persistence-contract.md` §5.2:
- hot: 保留 7d（每 K tick 一个 keyframe）
- cold: 保留 30d（每 10K tick 一个 keyframe）

hot 和 cold 之间（7d-30d）的 keyframe 密度骤降（从每 K 到每 10K）。若 replay verifier 需要回放 t+15d 的 tick，只能从最近的 cold keyframe 开始——最多需要重放 `30d × total_ticks_per_day` ticks，可能超过可接受的重放时间。

**修复建议**: 增加 warm 层（7d-30d，每 5K tick 一个 keyframe），或文档化 cold 层的重放时间成本估算。

---

## 亮点

1. **持久化双写语义正确**：对象存储先写 + FDB commit 原子提交 + 孤儿 GC 清理的模型在正确性上无懈可击。`collect_id` / `attempt_id` / `commit_id` 三标识符设计解决了跨重试的可追溯性。

2. **Tick 失败语义矩阵完整**：`01-tick-protocol.md` §6.1 覆盖 12 种失败模式，每种明确了对 tick/玩家/恢复策略的影响。降级模式（degraded mode）的自动退出机制（连续 10 tick 正常）避免了无限降级。

3. **Phase 2a/2b 分离设计优雅**：Inline 命令处理玩家竞争性操作（先到先得），Deferred 系统处理被动机制。Spawn body_cost 在 2a 扣除、2b 失败退还的 refund 路径是正确的。

4. **R/W 矩阵覆盖 29 systems**：每个 system 的 Component 读写关系明确，CI 可静态验证无数据竞争。RoomCap 中间态保护（S07→S08 区间无 reader）的正确推理值得肯定。

5. **确定性合同详尽**：排序键 5 层、RNG 命名空间隔离、seed epoch 管理、Wasmtime 版本与回放脱钩——均是正确的架构决策。

6. **Overload 抗永久锁死证明**：全局冷却（50 tick per target）+ 下限保护（20% MAX_FUEL）+ 恢复机制的形式化证明是高质量的架构分析。

---

## CrossCheck

### 单事实源闭合性

| 合同域 | 权威源 | 跨文档引用是否一致 | 备注 |
|--------|--------|:---:|------|
| CommandAction (19) | `game_api.idl.yaml` + `api-registry.md` | ✅ | IDL 与 Markdown 一致 |
| RejectionReason (35) | `game_api.idl.yaml` + `api-registry.md` | ✅ | 35 变体，4 层完整 |
| MCP Tools (46) | `game_api.idl.yaml` + `api-registry.md` | ✅ | Profiles / rate limits 一致 |
| System Schedule (29) | `06-phase2b-system-manifest.md` | ⚠️ | engine.md 内联列表过时（M1） |
| 容量限制 (25 params) | `api-registry.md` §5 | ✅ | engine.md 引用权威 |
| Tick 预算表 | `01-tick-protocol.md` §8.2 | ✅ | 与 engine.md §3.4.1 一致 |
| TickTrace Envelope | `api-registry.md` §6 | ✅ | 22 字段与 engine.md §3.3 一致 |
| Snapshot 截断 | `01-tick-protocol.md` §2.3 | ❌ | engine.md §3.4.4 模型冲突（C2） |
| api_version | `game_api.idl.yaml` vs `api-registry.md` | ❌ | 0.2.0 vs 0.1.0（C1） |
| Room 状态机 | `engine.md` §3.1a / `01-tick-protocol.md` §1.3 | ✅ | 5 状态一致 |
| Special Attack 状态机 | `02-command-validation.md` §3.16 | ✅ | 优先级/多命中/反制窗口完整 |

### 数据流闭合性

| 路径 | 读源 | 写目标 | 一致性保证 |
|------|------|--------|:---:|
| WASM tick(snapshot) | COLLECT 开始时 Bevy snapshot | CommandIntent[] → FDB | ✅ `snapshot.tick == current_tick` |
| MCP swarm_get_snapshot | 同 WASM 的 snapshot（COLLECT 阶段构建） | 只读 | ✅ 与 WASM 看到同一份 |
| Phase 2a inline | 当前 Bevy World（逐条修改后） | Bevy World + FDB 事务内 | ✅ TOCTOU 合同 5 条规则 |
| Phase 2b systems | Phase 2a 修改后的 Bevy World | Bevy World + FDB 事务内 | ✅ serial spine 保证 |
| FDB commit | Bevy World post-2b | FDB 持久化 | ✅ 原子事务 |
| Dragonfly cache | FDB（BROADCAST 阶段） | 缓存 | ✅ 允许 ≤2 tick 滞后 |
| NATS broadcast | FDB post-commit delta | WebSocket 客户端 | ✅ gap 检测 + fetch |
| Replay | FDB tick_manifest → Object Store blob | replay verifier | ✅ hash chain 验证 |

### ECS 调度安全性

| 并行域 | 系统 | 安全保证 | 状态 |
|------|------|---------|:---:|
| Combat Set A | S11-S13 | target_id partition | ✅ |
| Status Set B | S16-S22 | claimed disjoint StatusState subtypes | ❓ C3 |
| world_maintenance | S24 decay | serial, no shared writes | ✅ |
| RoomCap 区间 | S07→S08 | no reader in between | ✅ |
| SpawningGrace filter | S11-S15 | Without<SpawningGrace> | ✅ |

---

## 算法复杂度审计

| 路径 | 复杂度 | 上限 | 风险 |
|------|--------|------|:---:|
| Snapshot 构建 | O(entities + rooms) | 50,000 entities | ✅ 一次性、无 per-player 重复 |
| WASM 执行 | O(players × fuel) 并行 | 500 players × 10M fuel | ✅ worker pool |
| Phase 2a inline | O(commands × validation_cost) | 100 cmd/player × 500 players = 50,000 | ✅ 逐条 O(1) 校验 |
| Phase 2b combat | O(entities × attackers) 并行 | 10,000 drones | ✅ partition by target |
| Pathfinding | O(nodes explored) | 100,000/tick global | ✅ fair-share |
| FDB transaction | O(state_delta) | < 10KB（无大 blob） | ✅ 小事务 |

整体复杂度在设计容量内可控。500 活跃玩家 × 100 指令的上限在单机 32 核下不构成瓶颈。

---

## 与 R16 发现对比

| R16 发现 | R17 状态 |
|----------|:---:|
| C1: ECS schedule 矛盾 (20-system vs 27-system) | ✅ 修复 — 29 systems manifest 权威 |
| C2: spawning grace timing | ✅ 修复 — S09 在 combat 之前 |
| H1: RoomCap 中间态 | ✅ 修复 — S07→S08 区间明确 |
| M3: R/W 矩阵仅 6/20 | ✅ 修复 — 覆盖全部 29 systems |

R16 的 4 个 Critical/High 已全部闭合。本次新增问题为更深层的一致性审计（单事实源自伤、截断模型冲突、并行安全疑点）。
