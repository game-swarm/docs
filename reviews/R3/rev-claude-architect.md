# R3 架构评审 — rev-claude-architect

> 评审员: rev-claude-architect (Claude Opus 4.7 — 架构方向 Primary)
> 评审范围: DESIGN.md (2364 行) + design/tech-choices.md + 9 个 specs (specs/01-09) + ROADMAP.md
> 评审日期: 2026-06-16
> 上一轮: R2 已收敛 (B1-B6 闭合 + 用户裁决 5/5)，本轮验证收敛后是否仍存结构性裂缝。

---

## Verdict — 总裁决

**APPROVE_WITH_RESERVATIONS**

R2 收敛之后，文档体在「核心确定性合同」「指令管线单一入口」「可见性单一函数」三个最关键的边界上已经守得很紧。但作为架构评审员，我不能只看入口；我要看**系统在被压力推到边缘时哪里先碎**。本轮发现 9 项结构性 Concern（`A1-A9`）——其中 `A1` (ECS 并行 RW 矩阵自相矛盾)、`A2` (Bevy↔FDB 双权威源回滚不对称)、`A4` (epoch bump 之后无降级回退) 是「上线前必须修」级，其余是「可上线但留 follow-up」级。

未发现 Reject 级 fundamental flaw——文档在 R2 之后已不存在「架构性绕路」。

---

## Strengths — 已有的结构性正确

1. **指令管线单一入口** (specs/02 §1, specs/09 §4)
   `RawCommand → Source Gate → Auth Verify → validate_and_apply()` 是唯一写入路径。Admin 走同一管线只是放宽 RejectionReason 阈值；Rust trait 设计在编译期阻断绕路（`WorldMutate` 唯一实现者是 `validate_and_apply()`）。这条边界守得最好——不是文档说守住，而是类型系统**让你想绕都绕不动**。

2. **可见性单一函数** (specs/05 §1)
   `is_visible_to(entity, player_id, tick) -> bool` 一个函数答完所有问题，所有输出面（snapshot / MCP / WS / REST / replay / host functions）都从同一缓存读，缓存键 `(tick, player_id)`。R2 之后还把 host_get_objects_in_range / host_path_find 也接进同一过滤——这堵住了 R2 之前最容易泄露 fog-of-war 的入口。

3. **Phase 2a/2b 职责拆分**
   把「玩家提交的命令」（先到先得有意义）和「被动系统」（响应状态变化）切开，前者串行 inline，后者 ECS `.chain()` 加部分并行。这是 RTS 引擎里少见的清醒——大多数引擎要么全串行（性能塌）要么全并行（确定性塌）。Phase 2a 还显式列了 5 条 TOCTOU 合同 (specs/01 §3.3)，把 inline 模型最危险的 5 个时间窗口都用契约形式写死。

4. **Determinism Contract 完整** (DESIGN §8.8, specs/01 §7.1)
   PRNG、Hash、种子洗牌、`.chain()` ECS 顺序、`indexmap`、定点数、禁 f64——这 7 个确定性来源全部明确。回放保证里加上 `world_config + mods_lock` 两个环境元数据，是其他类似引擎常忘的一环。CI 5% 抽样 full replay + FDB 故障注入测试是把确定性承诺**变成可验证的回归门禁**。

5. **退还 fuel 防放大** (specs/02 §7)
   Refund 进 `next_tick_fuel_credit`、上限 `MAX_FUEL × 1.1`、deploy-reset 规则、连续高退还率 throttle——把「故意制造竞争失败换取额外计算预算」这条侧信道关得很死。

6. **三层信任模型** (DESIGN §8.7 + specs/04)
   WASM (不可信，进程隔离 + fuel) / Rhai (服主信任，AST 解释 + ops budget) / Rust (核心不可变)。每一层的隔离手段和信任前提匹配，没有「Rhai 假装信任但又给 mutating 接口」这种常见错配。

7. **MCP 不做游戏动作**
   R2 用户裁决之后，MCP 仅作为「AI 玩家的屏幕和鼠标」——查看 + 部署 + 调试，不存在 `swarm_move/swarm_attack` 这类工具。AI 与人类同走 WASM 沙箱，公平性在 fuel metering 层面就强制了，不需要额外补丁。

---

## Concerns — 结构性问题

### A1. ECS 并行 RW 矩阵与系统语义自相矛盾 [BLOCKER]

specs/01 §3.4 的 RW 矩阵把 `decay_system` 标记为「与主线并行，写 `Fatigue` 和 `Cooldown`」；同表 `spawn_system` 写 `Cooldown`。两者**同时写 `Cooldown` 列**，按 Bevy 调度规则就**不可能并行**——Bevy 的 `ParallelExecutor` 会把这两个系统排成串行。

更严重的是语义层面：Spawn 命令在 Phase 2b 设置 `Spawn.cooldown = N`，如果 decay 在同 tick 并行，cooldown 在被设置后立即被减 1，新出生的 drone/spawn 就少了 1 tick 冷却。这是确定性 bug——结果取决于 Bevy 调度器的实际选择。

**根因**: 矩阵的「Cooldown」一列没有区分 `SpawnCooldown` (Spawn 建筑的冷却) 和 `ActionCooldown` (drone 行动后的疲劳冷却)。两个语义不同的字段挤在一列，让矩阵看上去有冲突。

**修复方向**:
- 拆字段: `SpawnCooldown` 仅 spawn_system 写、decay_system 不读；`ActionCooldown` (含特殊攻击 CD) 仅 decay_system 写、spawn_system 不读。
- 或者收紧顺序: `decay_system` 串行在 `spawn_system` 之后，去掉 `decay` 与主线并行的声明。
- specs/01 §3.4 的并行安全证明这一段需要重写——目前的证明在「regeneration / decay 与主线无共享数据访问」上不成立。

**爆炸半径**: 高。决定了引擎的并行调度是否能启用——如果矩阵 bug，要么不能并行（性能损失），要么并行后回放 checksum 不一致（确定性塌）。

---

### A2. Bevy World ↔ FDB 双权威源的回滚不对称 [BLOCKER]

specs/01 §3.5 + §6.3.4 说「EXECUTE 开始对 Bevy World 内存快照，FDB rollback 时显式 `world.restore(snapshot)`」。这个机制本身正确，但**只覆盖了三种失败中的两种**：

| 失败点 | spec 的说法 | 实际不变量 |
|---|---|---|
| FDB commit fail | snapshot 恢复 ✅ | OK |
| WASM crash | 该玩家 0 指令 ✅ | OK，因为 crash 在 COLLECT 阶段，没 mutate world |
| **Phase 2a 中途 panic / OOM** | 没有定义 | **❌ 未定义** |

如果 Phase 2a 在第 47 条 inline 命令上发生 Rust panic（unwrap 错误、OOM、stack overflow），Bevy World 已经被前 46 条命令修改但 snapshot 还没 commit。spec 假设 Phase 2a 不会 panic，这是一个**没有契约支撑的假设**。

更微妙的是 FDB commit 之后的 NATS publish 失败：specs/01 §4.2 说「BROADCAST failure never rolls back committed tick」。这条本身正确（FDB 已经是权威源），但 Dragonfly 缓存更新失败时 spec 说「从 FDB 重建（异步）」——「异步」这个词在确定性引擎里要小心：如果重建期间 MCP_Query 来读 Dragonfly，玩家会读到落后版本。spec 06.3.4 说「Bevy 是工作副本、FDB 是权威源」，但**没说清楚 MCP_Query 应该读哪个**。

**修复方向**:
- specs/01 §6.1 失败矩阵补一行：「Phase 2a panic/OOM」→ catch_unwind 拦截 → world.restore(snapshot) → tick abandon。
- 明确 MCP_Query 的读源优先级：FDB → Dragonfly fallback → Bevy in-memory。或者反过来。规则要写死。
- Dragonfly 重建期间是否阻塞读，需要决策。

**爆炸半径**: 中。生产里 Rust panic 概率不高，但任何一次 panic 都会产生确定性 BUG（重放不可复现），且当下没有自动降级。

---

### A3. WASM 预编译缓存和证书吊销之间的死锁

DESIGN §3.2 + specs/04 §7 + specs/09 §3.5 说：
- 部署时预编译为原生码，按 `(module_hash, wasmtime_version)` 缓存。
- 编译缓存键 = `blake3(wasmparser_version || validation_policy_version || wasmtime_build_commit || target_arch || security_epoch)`。
- 「security_epoch bump 后所有旧 epoch 证书立即失效」(specs/09 §3.4)。

两条联合起来意味着：**security_epoch 一动，全量缓存 miss，全量重编译**。

设 5000 玩家、平均编译时间 8 秒（specs/04 §7 编译超时 30s + 编译内存 512MB + 并发编译 5 个），全量重编译需要 5000 × 8s ÷ 5 = 8000 秒 ≈ **2.2 小时单机串行**。这段时间内：
- 所有玩家 tick 0 指令（模块 cache miss、未编译、tick 直接被宽容失败处理）
- world 仍在跑 tick，玩家殖民地全部静止挨打
- 新玩家无法部署（compile pool 全占）

**spec 没有给出 epoch bump 的运维 runbook 是「冻结世界」还是「带病重编译」**。这是关键决策——「冻结世界」破坏 World 模式的 7×24 持续承诺，「带病重编译」让被 Hack/Drain 中的玩家死得不明不白。

**修复方向**:
- specs/09 §3.4 「紧急轮换 runbook」需展开：epoch bump 触发时 engine 进入冻结模式（暂停 tick 调度，保留 FDB 状态），管理员公告，等 80% 玩家完成重新认证后恢复。
- 或者：缓存键拆两层——证书相关只走「快路径校验」，不触发 wasmtime 重编译。当前设计把两件事绑死了。
- 验证：100/1000/5000 玩家场景下 epoch bump 的实测时间，加入容量规划文档。

**爆炸半径**: 中-高。低频事件（年级别），但触发时是 P0 故障。R2 已经发现 D5 类似问题（用户裁决了「客户端持有 Ed25519 私钥」），但缓存的容量规划没补上。

---

### A4. Phase 2a action quota 的度量主体不清晰

specs/01 §3.3 第 3 条：「Per-drone per-tick action quota：每 drone 每 tick 最多执行 1 个 main action（Move/Attack/Harvest/Build/Heal 及其特殊攻击变体）」。

这里 **Spawn 命令针对的不是 drone，是 Spawn building**。一个 spawn 一 tick 可以执行多次 Spawn 命令吗？specs/02 §3.8 校验里有 `SpawnOnCooldown`，意味着每次 Spawn 后建筑进入冷却，所以**单个 Spawn 一 tick 最多 1 次**。但这个约束没有写进 §3.3 的 TOCTOU 合同里。

类似的歧义：
- Recycle 命令的执行主体是 spawn 还是 drone？规范说退还资源给 spawn。是否计入 drone 的 main action quota？specs/02 §3.9 说 Recycle 走 death_mark→death_cleanup 路径，不是 main action。但 §3.3 写「Move/Attack/Harvest/Build/Heal 及其特殊攻击变体」——隐含 Recycle 也算 main action？说不清楚。
- Transfer/Withdraw 同 tick 多次：§3.3 说「Transfer/Withdraw 不计入此配额但受 carry 容量约束」。那么 Transfer chain (drone A→drone B→drone C) 的中间节点是否在同 tick 完成？**对，因为是 inline 模型**——但这意味着资源可以在一 tick 内跨任意路径长度传播，违反「每 tick 物理位移有限」的物理直觉。R2 §B1 提到「Transfer chain resource amplification」是已知防御对象，但 specs/02 §3.3 校验矩阵没写「Transfer 链长度限制」。

**修复方向**:
- §3.3 第 3 条改成「Per-drone per-tick main action quota = 1, where main action = {Move, Harvest, Build, Attack, RangedAttack, Heal, Hack, Drain, Overload, Debilitate, Disrupt, Fortify, Leech, Fabricate, ClaimController}」。Recycle / Transfer / Withdraw / Spawn 显式排除。
- Spawn 用 `Spawn.cooldown` 约束（已有），不需要 per-spawn quota。
- Transfer/Withdraw 不限 chain 长度（这是设计意图，inline 模型的特性），但 spec 要明说，让玩家可预期。

**爆炸半径**: 低-中。不会破坏确定性，但会让校验测试覆盖率虚高（"特殊攻击算不算 main action"模糊会导致测试漏掉）。

---

### A5. NATS broadcast 与确定性合同的微妙脱钩

DESIGN §3.2 + specs/01 §4.2: tick 在 EXECUTE 阶段写入 FDB → NATS publish → Dragonfly update。NATS publish 失败时「客户端通过 last_tick 字段检测 gap → 主动 fetch」。

这个设计本身正确，但 Arena 的 spectator 流是把 delta 经 NATS 推到旁观者前端的——**spectator 收到的事件流不是「确定的」**：
- NATS reorder：A 房间 spectator 先看到 tick 100 的 delta，再看到 tick 99 的 delta。
- 部分 spectator 因网络丢失中间 tick → fetch 之后顺序错乱。

specs/05 §3.5 说 spectator 受 spectate_delay ≥ 50 tick 限制，**但没说 spectator 的事件流要保序**。如果 spectator 是裁判 / Tournament 流播主播，事件错序会让对局解说乱套。

更严重的：specs/06 §5.1 的「每 Tick 解释」API 是 REST `GET /api/v1/ticks/4521/explanation?player=42`。这个 API **仅接受 commit 完成的 tick**。但 BROADCAST 失败时，FDB 已 commit 但缓存未刷新。如果玩家立刻 GET 该 tick 的解释，命中 stale Dragonfly cache → 返回旧数据。spec 06.3.4 说「FDB 为权威源」，但 explanation API 走哪条路径没规定。

**修复方向**:
- specs/01 §4.2 加一条：spectator delta 流必须按 (world_id, tick) 严格递增，重复或乱序的事件由网关 hub 在投递前丢弃。
- specs/06 §5.1 explanation API 显式声明读源优先级（FDB 优先，cache miss fallback）以及一致性保证（read-your-write semantics for the same player's commands）。
- broadcast partial 状态下 explanation API 是否阻塞需要决策。

**爆炸半径**: 低-中。功能性而非确定性问题，影响观赛体验和 explanation 的可信度。

---

### A6. 跨世界联邦的因果性未规范

DESIGN §1.1 + §7.2 提到「联邦宇宙」+「跨世界异步交互（转移资源/共享排名）」。spec 集里**完全没有跨世界协议的规范**。

问题：
- 跨世界资产转移涉及两个 FDB cluster 的事务。要么用 2PC（破坏每世界单 FDB 的简洁性），要么用最终一致 + 重试（产生「资产丢失但事务完成」的窗口）。
- 排名聚合：两个世界的 leaderboard 合并需要时钟一致——但每个世界的 tick 时钟是独立 wallclock，无法对齐。
- 跨世界的回放：A 世界回放某 tick，包含的「跨世界资产到达事件」需要 B 世界的当时状态，但 B 世界已经 tick 了 1000 次。回放因果性怎么保证？

**修复方向**:
- 联邦宇宙在 R3 阶段标记为 **Phase 8 / 远期**，明确**不在 MVP scope**。
- 创建 specs/10-federation-protocol.md 占位（标 R4 review），描述跨世界的最终一致性保证、消息持久性窗口、回放因果性策略。
- DESIGN §1.1 在「联邦宇宙」描述里加一句：「跨世界事件在 sender 世界的 tick T+N 后承诺到达，但 receiver 世界的本地状态推进不依赖于 sender 的承诺到达」——明确事件向但不阻塞。

**爆炸半径**: 低（远期）。但**现在不写**意味着 MVP 上线后任何跨世界功能都会撞上设计真空。

---

### A7. Rhai 模组的能力白名单与「damage_entity」的爆炸半径

DESIGN §8.7 + specs/07 §5.1 列出能力白名单 6 条 action：deduct_resource / award_resource / damage_entity / set_entity_flag / emit_event / log。

`damage_entity(entity_id, amount, reason)` 是**范围最大的**——它绕过了 Combat 系统的 damage_type / 抗性 / Fortify 检查，直接修改 hits。这意味着：
- 服主装一个 `dot-damage-mod`（很常见，Pylon-style 持续伤害），mod 的 Rhai 脚本每 tick 对范围内 entity 调 `damage_entity(id, 5, "burn")`。
- 但是 mod 写错了，对己方 entity 也调用 → 全场 friendly fire。
- 玩家无法通过 Fortify 净化（damage_entity 是 RuleMod 来源，不是 Combat 命令）。
- 玩家 WASM 看到「Tick N 的 hits 突然 -5 但没有 RejectionReason 也没有 combat event」——调试黑洞。

specs/07 §5.1 的事务性 buffer 模型只保证「mod 内部 actions 一致 commit」，不保证「mod actions 经过引擎核心的伤害管线」。这两件事不同。

**修复方向**:
- `damage_entity` 改名为 `apply_raw_damage(entity, amount, damage_type, reason, bypass_resistances: bool)`，让 mod 显式声明是否绕过抗性。默认 `bypass_resistances=false`，走标准 combat 抗性矩阵。
- 在 emit_event 同时写 TickTrace `RuleModDamage{mod_id, target, amount, source_reason}` 让玩家可调试。
- specs/07 加一节「能力放大风险表」：每个 white-list action 列出可能被滥用的方式 + 对应的 sandbox 加固。

**爆炸半径**: 中。模组生态启动后这是最常见的玩家-服主投诉来源。

---

### A8. Tick 预算分配下 BROADCAST 的隐式异步

DESIGN §3.2 + specs/01 §1.4: COLLECT 2500ms hard + EXECUTE 500ms hard = **3000ms tick interval 已被 COLLECT+EXECUTE 用满**。BROADCAST 在 tick 之外，标注「即时」（spec 没给具体上限）。

实际意味着：
- 阶段三 `compute_delta + Dragonfly update + NATS publish` 在 tick N 的 EXECUTE 完成之后、tick N+1 的 COLLECT 开始之前必须完成。
- 没有具体预算 (e.g. 200ms 上限) 意味着如果 NATS 慢了，tick N+1 的 COLLECT 开始时玩家拿不到 tick N 的 snapshot——空 tick 或 stale snapshot。

更微妙：`compute_delta(world_state_before, world_state_after)` 需要保留 before snapshot——这就是 §3.5 那个 Bevy snapshot。**snapshot 在 commit 后是否立即 drop**？如果保留到 BROADCAST 完成才 drop，意味着每 tick 至少持有 2 倍世界状态内存。500 玩家 + 5MB 世界 = 5GB 内存（在 single-engine 模型下）。spec 没有给世界状态体积上限。

**修复方向**:
- specs/01 §1.4 / §4 加 BROADCAST 预算：阶段三总耗时上限 200ms（500ms 也 OK，但要写明）。超过 → tick 标记为「broadcast deferred」+ tick N+1 的玩家可能收到合并 delta。
- §3.5 snapshot 生命周期补一行：「commit 成功后 snapshot 立即 drop，BROADCAST 用 commit 后的 in-memory delta」。
- 文档体加「世界状态体积上限」：500 玩家 × 平均 500 drone × 平均 5KB/drone ≈ 1.25GB；500 房间 × 平均 50 实体 ≈ 0.5GB。给容量规划。

**爆炸半径**: 中。MVP 500 玩家场景下不会爆，但 specs/01 §5 的 `tick_duration_p99 > 2800ms 警告` 阈值已经隐含承认 tick 经常会接近预算上限。BROADCAST 没预算意味着压力大时 tick 时间不可预测。

---

### A9. Spawn 房间分配的「密度优先」+「避免包围」缺少形式化定义

DESIGN §3.1a + specs/01 §2.5: 新玩家分配出生房间时「密度优先」+「避免包围」。两条规则**都没有形式化定义**。

- 「密度」= 候选区域内活跃玩家数？还是活跃 drone 数？还是 Controller level 总和？三种度量结果完全不同。
- 「避免包围」检查范围是 3×3 还是 5×5？「敌对玩家已占领」是 RCL ≥ 1 还是 RCL ≥ 3？
- 当所有候选区域都被包围时怎么办？specs 没有定义 fallback。

更关键：这两条规则是**不可玩家观测的**——玩家不知道为什么自己出生在这个房间。导致：
- A 玩家觉得系统「针对他」，永远把他放在敌对玩家之间。
- B 玩家通过观察发现密度算法的边界，然后**故意制造低活跃度** drone（占着不打）让自己被分到富矿区。

**修复方向**:
- specs/01 §2.5 形式化定义：
  ```
  density(region) = sum(controller_level for room in region.rooms_3x3 if room.has_owner)
  surrounded(region) = (count(adjacent room with owner != new_player and rcl >= 2) >= 7)
  spawn_score(region) = density(region) * 100 + (surrounded(region) ? 1000 : 0)
  // 选择 spawn_score 最低的 region；并列时按 region.coord 字典序选最小
  ```
- 加 fallback：所有候选都 surrounded 时，扩展搜索半径到 5×5。
- 算法本身可以保密，但「算法的存在」+「我可以请求重抽 1 次（消耗资源）」要可见，让玩家有 agency。

**爆炸半径**: 低（用户体验，不破坏一致性），但对新玩家留存率有直接影响——R2 已经投入大量精力做 Tutorial，spawn 分配不规范会让 Tutorial 之后第一次进入正式世界的玩家直接退坑。

---

## Missing — 缺失项

以下是评审过程中发现的「文档没有错，但根本就没写」的部分。每一项都是 R3 之后必须补的：

### M1. 可观测性 spec 缺失

spec 集里 specs/01 §5 提了 `collect_timeout_rate / tick_abandon_rate / tick_duration_p99 / command_rejection_rate` 4 个指标和阈值，但没有：
- 指标导出协议（Prometheus? OpenTelemetry?）
- 告警分级和值班 runbook
- 指标存储 retention（ClickHouse 已经有 mcp_audit, 但 tick metrics 在哪？）
- dashboard 模板（Grafana?）

**建议**: 创建 `specs/10-observability.md`，作为 R3.5 follow-up review。

### M2. 容量规划文档缺失

DESIGN §3.1a 「扩展策略声明」表格只给了三层目标（500 / 5000 / 不限），没有：
- 每层的资源预算（RAM / CPU / FDB cluster size）
- 每层之间的迁移路径（500 → 5000 时数据如何迁移？）
- 单 FDB cluster 上限（FDB 官方推荐 < 100M ops/s，对应多少玩家？）

**建议**: tech-choices.md 补一节「容量与扩展」，每层给具体数字。

### M3. 零停机升级模型

spec 里没找到引擎本身的零停机升级流程：
- Wasmtime 版本升级（确定性敏感）触发什么？
- Bevy 版本升级（系统调度可能变）触发什么？
- engine binary 重启时 in-flight tick 怎么办？

**建议**: specs/04 §1 dependency lock 之后补一节「升级与回滚」。

### M4. 多 Engine 实例之间的协议（远期但应留 placeholder）

DESIGN §7.2 「多个 Engine 实例可并行运行——每个服务一个独立的世界」。但 multi-engine 部署下：
- Gateway 如何路由 player → engine（按 world_id）？
- 玩家在两个 world 同时在线，两个 engine 的认证 token 共享吗？
- world.toml 在多 engine 之间是否需要中心化配置 store？

**建议**: 不在 R3 必须，但 DESIGN §7.2 加一句「多 engine 间无实时协议，世界完全独立」让边界明确。

### M5. WASM 模块的代码兼容性合同

specs/04 + specs/08 IDL 提到 `abi_version` 但没有：
- abi_version bump 的策略（什么时候 bump major？）
- 旧 abi 的 WASM 模块在新 engine 上的行为（拒绝运行？兼容运行？）
- ABI 版本和 mod manifest hash 的交互

**建议**: specs/08 §1 加一节「ABI 演进策略」。

### M6. Arena 房间的资源配额和 DoS 防护

DESIGN §9.1 + specs/03 §5.2 说「每引擎实例最大 AI 玩家数 500 / max_rooms = 10」。但 Arena 房间的具体资源开销（每个 Arena 房间额外 X% engine CPU + Y MB 内存）没有量化，意味着：
- 服主无法判断「能开几个 Arena」
- 一个长时 (`match_duration = 50000`) 的 Arena 房间可能挤掉 World 模式的服务质量

**建议**: DESIGN §9.1 加 Arena 房间的资源预算估算表。

---

## Phase Ordering — 实施阶段建议

注意：当前 ROADMAP.md 已经显示 R2 闭合后所有 P0/P1/P2 缺口已解决，文档体处于「实现已对齐设计」状态。下面 Phase Ordering 是针对**本评审 9 项 Concern + 6 项 Missing 的修复顺序**，不是从零开发的 phase 计划。

### Phase R3.0 — 上线前必须修 (BLOCKER)
**串行**，无法并行（每项都涉及 spec 文本修改）。

| 顺序 | 修复项 | 涉及文件 | 估时 |
|---|---|---|---|
| 1 | A1 ECS RW 矩阵拆字段 / 重排序 | specs/01 §3.4 | 0.5 day |
| 2 | A2 Phase 2a panic 兜底 + MCP_Query 读源优先级 | specs/01 §3.5, §6.1; specs/03; specs/06 §5.1 | 1 day |
| 3 | A4 epoch bump runbook + 容量规划 | specs/09 §3.4; tech-choices.md (M2) | 1 day |

**总计**: 2-3 days，1 个评审员单线推进。

### Phase R3.1 — Concern 闭合 (并行 OK)
A3、A5、A6、A7、A8、A9 之间**无文件冲突**，可并行：

| 修复项 | 涉及文件 | 可并行组 |
|---|---|---|
| A3 action quota 度量主体澄清 | specs/01 §3.3, specs/02 §3.3 | Group α |
| A5 spectator/explanation 一致性 | specs/01 §4.2, specs/06 §5.1 | Group β |
| A6 联邦协议占位 | DESIGN §1.1, §7.2 + specs/10 (新) | Group γ |
| A7 Rhai damage_entity 加固 | DESIGN §8.7, specs/07 §5.1 | Group α |
| A8 BROADCAST 预算 + snapshot 生命周期 | specs/01 §1.4, §3.5, §4 | Group β |
| A9 spawn 分配形式化 | specs/01 §2.5 | Group γ |

**Group α / β / γ 内部串行，组间并行。** 按 6 项任务、3 组并发，3 个评审员各取一组：~1 day。

### Phase R3.2 — Missing 项补齐
**M1 (可观测性) 和 M5 (ABI 演进) 优先**——MVP 上线前必须有，否则线上没有可观测性。M2 (容量规划) 已在 R3.0 部分覆盖。M3 / M4 / M6 可推到 R4。

| Missing | 优先级 | 阶段 |
|---|---|---|
| M1 可观测性 spec | P0 | R3.2 |
| M5 ABI 演进策略 | P0 | R3.2 |
| M2 容量规划详细表 | P0 (R3.0 已有粗略) | R3.2 |
| M3 引擎升级模型 | P1 | R4 |
| M4 多 engine 协议占位 | P1 | R4 |
| M6 Arena 资源配额 | P1 | R4 |

### 依赖关系图

```
                R3.0 BLOCKERS (串行)
                    │
         ┌──────────┼──────────┐
         │          │          │
       A1 ECS    A2 Bevy    A4 epoch
         │          │          │
         └──────────┼──────────┘
                    │
              (R3.1 入口)
                    │
       ┌────────────┼────────────┐
       │            │            │
     Group α     Group β      Group γ
   (A3,A7)     (A5,A8)       (A6,A9)
       │            │            │
       └────────────┼────────────┘
                    │
                  R3.2
              (M1,M2,M5)
                    │
                R3 闭合
                    │
         (R4 covers M3,M4,M6 + 联邦协议)
```

**整体估时**: R3 修复期 = R3.0 (3d) + R3.1 (1d 并行) + R3.2 (2d) = **~6 工作日**。

---

## 附录: 边界与爆炸半径

按「如果这个边界被突破会发生什么」的视角，本评审识别的关键边界优先级：

| # | 边界 | 守护手段 | 突破后果 |
|---|------|---------|---------|
| 1 | Source Gate (specs/09) | trait + 编译期 | 状态写入路径绕过 → 确定性塌 |
| 2 | is_visible_to (specs/05) | 单一函数 + 缓存 | fog-of-war 泄露 → 公平性塌 |
| 3 | Determinism Contract (DESIGN §8.8) | PRNG/Hash/order 固定 | 回放不一致 → 反作弊塌 |
| 4 | Phase 2a TOCTOU (specs/01 §3.3) | 5 条契约 inline | inline 时间窗口攻击 → 资源放大 |
| 5 | WASM Sandbox (specs/04) | seccomp+cgroup+wasmtime | 容器逃逸 → host 沦陷 |
| 6 | Rule Mod Capability (DESIGN §8.7) | white-list 6 actions | mod 滥用 → 玩家不可调试损失 |
| 7 | FDB ↔ Bevy Coupling (specs/01 §3.5) | snapshot+restore | tick abandon → 状态回滚不全 (A2) |
| 8 | ECS Parallel RW (specs/01 §3.4) | RW matrix | RW 冲突 → race condition (A1) |

边界 1-3 已守得很紧，边界 4-6 有结构性 concern 但可控，边界 7-8 是本轮发现的真正裂缝。

---

## 评审员签字

> Verdict: APPROVE_WITH_RESERVATIONS
> Blockers (上线前必须修): A1, A2, A4
> Required follow-up: A3, A5, A7, A8 + M1, M5
> 远期: A6, M3, M4, M6
>
> 文档体在 R2 之后已经达到「敢上线」的水准，但还没到「敢上线给 5000 玩家」的水准。R3 修完三个 Blocker 之后可以开实现层的 Phase 1 (核心 tick); 5000 玩家级别需要等 M2 容量规划补齐之后再说。
>
> — rev-claude-architect, 2026-06-16
