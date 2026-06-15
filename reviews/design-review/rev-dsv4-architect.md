# Architect 评审 — Swarm 全设计文档

> 评审员: DeepSeek V4 Pro (rev-dsv4-architect)
> 方向: 架构 — ECS 调度 / Tick 生命周期 / 数据一致性 / 算法复杂度
> 日期: 2026-06-15
> 评审范围: DESIGN.md (2034行) + tech-choices.md + ROADMAP.md + P0-1 到 P0-9 全部规范

---

## VERDICT: CONDITIONAL_APPROVE

设计核心架构自洽且坚实——延迟指令模型 + WASM 沙箱 + 确定性 ECS pipeline + 动态资源系统构成可信边界。P0-1 到 P0-9 规范体系完整覆盖了 Tick 协议、指令校验、MCP 安全合同、沙箱基线、可见性策略、反馈循环、世界规则引擎、API IDL、指令来源模型——说明从「设计」到「规范」的细化过程已完成。

**7 项 Critical 发现、4 项 High 发现、5 项 Medium 发现、3 项 Low 发现。** Critical 项集中于 FDB 回滚与 Bevy 状态一致性、TransferToGlobal 未定义提交通道、Rhai 事务与 FDB 事务的原子性边界、Phase 2a/2b 边界原则缺失、以及 Spawn 文档矛盾。这些问题均可在 ABI 冻结前通过设计澄清（非重构）解决。

---

## STRENGTHS

**S1. Deferred Command Model 架构正确性。** `tick(snapshot) → Command[]` 将只读感知与可变动作彻底分离。WASM 模块不可直接写入世界状态——所有变更通过 JSON 指令提交、引擎统一校验后应用。这是整个确定性契约的基石，设计执行到位。

**S2. 三阶段 Tick 协议边界干净。** COLLECT（并行 WASM 执行，内存快照）→ EXECUTE（串行指令应用 + ECS Systems，FDB 原子提交）→ BROADCAST（增量发布 + Dragonfly 缓存刷新）。读写分离清晰，并行/串行边界明确，失败语义（P0-1 §6）覆盖了 WASM timeout/crash/FDB fail/NATS fail/Dragonfly stale 全矩阵。

**S3. 确定性合同（Determinism Contract）完备且可实现。** Blake3 XOF PRNG、IndexMap 有序集合、禁 f64、`.chain()` ECS 排序、种子 10,000 tick 轮换——每个非确定性来源均有明确对策。三原语合一（Blake3 覆盖 Hash/PRNG/代码签名）减少审计面。

**S4. 种子洗牌（Seeded Shuffle）的公平性模型正确。** `Blake3(tick_number || world_seed)` 确定玩家排序，不可预测但可回放验证。每 tick 随机轮换 → 长期期望公平。先到先得资源竞争创造策略深度，不引入不必要的复杂性。

**S5. 可见性模型单点真源。** `is_visible_to(entity, player_id, tick)` 作为所有输出面（WASM snapshot / MCP / WebSocket delta / REST API / replay）的唯一可见性判定函数——无后门、无例外。drone 感知（WASM snapshot）与玩家视野（monitor/MCP）的分层设计在 P0-5 §3.5 明确。

**S6. FDB 权威源 + Dragonfly 非权威缓存的层级正确。** FDB 严格可序列化事务 → 每 tick 原子提交。Dragonfly 仅加速高频读取，失败回退 FDB，不参与一致性决策。BROADCAST 失败不回滚已提交 tick——正确。

**S7. 动态资源模型无硬编码。** 引擎操作 `IndexMap<String, u32>` 而非硬编码 Energy。资源类型、身体部件类型、建筑类型、伤害类型、特殊效果全部通过 world.toml 可配置。服主可定义星际争霸式双资源或帝国时代式四资源——无需改 Rust 代码。

**S8. Command Source Model (P0-9) 完整建模。** 12 种来源（WASM/MCP_Deploy/MCP_Query/Admin/Replay/TestHarness/Tutorial/Deploy/Rollback/RuleMod/Simulate/DryRun）各自的能力矩阵和可见性约束完整。Source Gate 在校验管线入口拦截非 gameplay 来源的指令。

**S9. 全局存储反雪球机制设计精巧。** 累进存储税 + 本地存储隐匿性 + 运输时间延迟——三级物流模式（无/轻/硬核）让服主可调经济复杂度。Deploy-reset 规则防止 refund 刷取跨模块预算转移。

**S10. Rhai 模组执行模型的事务隔离正确。** Buffered actions → 脚本完成 → 统一 apply。超时则全 buffer 回滚，不影响世界状态。100ms 墙钟预算作为安全网。

**S11. IDL 驱动的代码生成消除接口不一致。** `game_api.idl` → Rust/TS/MCP/Docs/Test 全目标代码生成。ABI 版本号管理变更。CI 验证生成代码与提交一致——编译时发现不一致。

---

## ISSUES — REQUIRED RESOLUTION

### D1 [CRITICAL] Bevy World 快照回滚完整性与 FDB 事务边界

**位置**: P0-1 §3.5, DESIGN §3.2

P0-1 §3.5 明确：「EXECUTE 开始时对 Bevy World 做内存快照——FDB rollback 不自动恢复 Bevy 状态，需显式 `world.restore(snapshot)`。」

**问题**: Bevy ECS 的 World 不是简单的 `Clone` 友好结构。World 包含：Entities/Components（archetype storage）、Resources（类型擦除的 Any 映射）、Schedules（系统图）、Change detection ticks。对一个运行中的 Bevy App 做完整快照和恢复需要：

1. 捕获所有 component storage 的完整状态（包括内部稀疏集合的迭代顺序——可能成为非确定性源）
2. 捕获所有 `Resource<T>` 的状态（如 ResourceRegistry、WorldConfig、PRNG 状态）
3. 恢复后 change detection 的一致性（`.changed::<T>()` 过滤器）

**如果快照遗漏任何 component 或 resource**，恢复后的 World 与原始状态不同，重放将产生分歧的世界状态——确定性合同（§8.8）被打破。

**要求**: 
1. 显式定义「快照范围」——列出必须捕获的所有 Component 类型和 Resource 类型
2. CI 中增加「FDB 故障注入测试」：在随机 tick 触发 FDB commit 失败 → 验证 `world.restore(snapshot)` 后的状态与快照完全一致（`state_checksum == snapshot_checksum`）
3. 考虑替代方案：不使用 Bevy World 快照，而是 `txn.commit()` 成功后才将变更写入 Bevy World（类似「先提交后应用」模式）。这样 FDB 失败时 Bevy World 根本未被修改，无需回滚
4. 文档化恢复的时间预算——快照和恢复操作必须在 500ms EXECUTE 预算内完成

---

### D2 [CRITICAL] TransferToGlobal/TransferFromGlobal 提交通道未定义

**位置**: P0-8 `global_storage_commands` 段, DESIGN §8.2 物流配置

P0-8 在 `global_storage_commands:` 段独立定义了 TransferToGlobal 和 TransferFromGlobal（含 validator/duration/cost），但与常规 `commands:` 段并列。DESIGN §8.2 详细描述了全局↔本地转换的语义和物流规则。

**问题**: 这两个命令的提交通道未定义：

1. WASM 能否通过 `tick() → Command[]` 提交 TransferToGlobal？P0-8 将它们放在 `global_storage_commands:` 而非 `commands:` 中——暗示它们可能不是常规 gameplay 命令。如果是，应在 `commands:` 中定义。
2. 如果不是 WASM 提交的——是谁提交的？MCP？REST API？Rhai？Admin？
3. `duration: transfer_to_global_time` 表示转换需要 N tick——这是异步操作。在持续期间，资源处于"运输中"状态。引擎用什么 ECS 机制追踪中间状态？（Timer component？PendingTransfer resource？）
4. 运输期间的拦截机制（DESIGN §8.2：「可被敌方巡逻 drone 拦截」）如何实现？需要新的 combat/event 交互——未在任何规范中定义。

**要求**:
1. 明确 TransferToGlobal/TransferFromGlobal 的来源矩阵（加入 P0-9 §2.1 来源矩阵）
2. 如果 WASM 可提交，移至 P0-8 `commands:` 段，提供完整的 CommandIntent schema
3. 定义异步转换的内部表示（TransferState component / PendingTransfer resource + timer system）
4. 运输拦截要么提供设计，要么标记为 Phase 3+ 特性

---

### D3 [CRITICAL] Rhai 事务 Apply 与 FDB 事务原子性边界

**位置**: P0-7 §5.1, P0-1 §3.5, DESIGN §3.2, §8.7

P0-7 §5.1 描述了 Rhai 的事务执行模型：
```
Rhai 脚本执行 → RhaiActionBuffer (内存) → 统一 Apply → 写入世界状态（FDB 事务内 atomic commit）
```

P0-1 §3.5 描述了 FDB 事务包裹整个 EXECUTE 阶段：
```
txn = fdb.create_transaction()
for command in sorted_commands:
    result = validate_and_apply(txn, command, world_state)
txn.commit()
```

**问题**: 这两个原子性边界的关系未定义：

1. Rhai buffer apply 是在 FDB 事务**内**还是**外**？如果在 FDB 事务内——Rhai 的 `actions.deduct_resource` 操作是写入 FDB key 还是只修改内存 Bevy World？如果是后者，需要在 FDB txn 内部额外处理。
2. 如果 Rhai buffer apply 在 FDB 事务外——FDB commit 失败回滚了命令执行，但 Rhai buffer 可能已被部分 apply 到 Bevy World。Bevy World 状态与 FDB 状态不一致。
3. P0-7 §5.1 描述 apply 顺序是先 deduct → award → emit_event → effect。但在 P0-1 的 EXECUTE 阶段中，Rhai 钩子（tick_start/tick_end）的调用顺序与命令执行的关系未指定。

**要求**:
1. 在 P0-1 §3.5 中明确：Rhai buffer apply 必须在同一 FDB 事务中完成——FDB txn 包裹「命令执行 + Rhai buffer apply」
2. 如果 apply 操作需要写 FDB key（而非仅修改 Bevy World 组件），定义 FDB key schema
3. 失败回滚：FDB txn 失败 → Bevy World 快照恢复（同 D1）+ Rhai buffer 丢弃

---

### D4 [CRITICAL] Phase 2a/2b 边界原则缺失——命令执行语义歧义

**位置**: DESIGN §3.2, P0-1 §3.3, §3.4, P0-2 §3

设计将命令执行分为两个阶段：
- **Phase 2a (Inline)**: Move/Harvest/Build/Transfer/Attack/Heal/Recycle 立即执行
- **Phase 2b (Deferred ECS)**: Spawn (只校验不入队)、combat、regeneration、decay、death

但**没有规定什么进 2a、什么进 2b 的原则**。这导致以下具体歧义：

1. **Attack 与 combat_system 的交互**: Phase 2a 中 Attack 命令直接减少目标 HP。Phase 2b 中 combat_system 再次处理战斗。Tower 自动攻击是 combat_system 的一部分。但玩家 drone 的 Attack 命令是否也走 combat_system？如果是——重复处理（双重伤害）。如果不是——Phase 2a Attack 绕过了 combat_system 中的抗性/damage_type/damage_multiplier 计算和 damage→heal 排序逻辑。

2. **Move→Attack→Harvest 的顺序效应**: drone A 执行 Move（进入 range）→ drone B 执行 Attack（打中被移入的 drone A）→ drone A 执行 Harvest。这是在 Phase 2a 中发生的——因为命令按洗牌顺序交插执行。如果 Move 后在 Phase 2b combat_system 中才计算攻击，B 无法打到刚移入的 A。两阶段的时间差改变了战斗语义。

3. **Recycle 立即 despawn**: P0-2 §10.3 说 「drone 立即 despawn」。DESIGN §3.2 说 Recycle 在 Phase 2a 执行。但 death_cleanup_system（实际 despawn）在 Phase 2b 末尾。Recycle 是立即执行还是通过 death_mark + death_cleanup？如果是立即——与其他死亡路径不一致。如果是走 death_mark——与其他命令一致但文档不准确。

4. **Build 和 room cap**: Build 在 Phase 2a 立即创建在建工程——受 TileOccupied 先到先得限制。但 `max_per_room` 限制（如 Extension 最多 60 个/房）也应该在 Build 校验时检查。如果 room cap 在 2a 中不同玩家的 Build 导致超限——需要文档化处理方式。

**要求**:
1. 定义 2a vs 2b 的分类原则：
   ```
   2a (Inline): 玩家提交的命令——其效果依赖于执行顺序
     且「先到先得」竞争有意义。这些命令对 Bevy World
     做立即修改，后续命令基于最新状态校验。

   2b (Deferred): 被动系统——对所有实体均匀运行，或
     需要跨实体协调的命令（Spawn 需 room cap，Combat
     需同时 damage+heal 结算）。这些系统不接收玩家命令，
     而是响应 2a 产生的状态变化。
   ```
2. 明确：Attack/RangedAttack 命令在 Phase 2a 中直接应用 damage（含抗性计算）。Phase 2b combat_system 仅处理非玩家命令的战斗——Tower 自动攻击、持续伤害效果、damage-over-time。
3. Recycle 走 death_mark → death_cleanup 路径，与其他死亡一致。更新 P0-2 §10.3 中「立即 despawn」的不准确描述。

---

### D5 [CRITICAL] Controller Claim 机制完全未定义

**位置**: P0-8 §4.1 (ClaimController 变体), P0-2 §10.2, DESIGN §3.1, §8.2

DESIGN §3.1 定义了 Controller 结构体——含 owner/level/progress/downgrade_timer/safe_mode 等字段。P0-8 新增了 `ClaimController` 变体（需 Claim body part, range=1, validator=[exists,owner,drone,body_part(Claim),is_controller,in_range(1)]）。

**问题**: Claim 的语义完全空白：

1. **占领需要多少 tick/claim 次数？** 是单次 Claim → 立即转移 owner？还是累计 N 次 Claim 才能占领？如果是累计——不同玩家的 Claim 是否互相抵消？
2. **原 owner 的 Controller 有防御机制吗？** downgrade_timer 是否在 Claim 期间暂停？safe_mode 是否阻止占领？
3. **占领后的状态**: Controller 的 level/progress/downgrade_timer 如何变化？全部重置？保留？部分转移？
4. **RCL 降级连锁**: 如果 Controller 从 level 5 被占领并降为 level 1，原有 level 5 解锁的建筑（Terminal/Observer）如何处理——立即失效？转为中立？保留但不可用？

**要求**: 增加 Controller Lifecycle 子规范（建议 P0-2 §3.18 或独立的 Controller spec），覆盖：
- 占领模型（累计次数 vs 立即；抵消规则）
- 占领后的状态转移表（level/progress/timer/safe_mode）
- RCL 降级连锁的建筑处理
- 与 safe_mode 的交互

---

### D6 [CRITICAL] Spawn 文档矛盾：创建时机与 death_cleanup 顺序

**位置**: DESIGN §3.2 (Phase 2b chain), P0-2 §3.10, P0-1 §3.4

DESIGN §3.2 Phase 2b 定义 ECS chain：
```
death_mark_system → spawn_system → combat_system → regeneration/decay → death_cleanup_system
```

P0-2 §3.10 Spawn 检查项末尾断言：「Drone 在 tick 末尾创建（death_cleanup_system 之后，spawn 槽位已释放）」

**矛盾**: spawn_system 在 chain 中第 2 位——远在 death_cleanup（末位）之前。新 spawn 的 drone 在 combat_system、regeneration_system、decay_system 中**全部参与**——它们可能在同一 tick 内被攻击、受 decay 影响。

P0-2 的描述「death_cleanup 之后」是不准确的——实际语义是「death_mark 释放 room cap 槽位之后」。但更关键的是**新 drone 是否应该在同 tick 参与后续 system**：

- 如果 spawn 后立即参与 combat → 攻击方可以在同一 tick 看到并击杀新 spawn（出生即死）
- 如果 spawn 后参与 decay → 新 drone 的同 tick fatigue/cooldown 可能非零（取决于 decay 逻辑）
- 如果 spawn 后参与 regeneration → 资源点刚被 spawn 消耗的能量立即可再生（无意义但无害）

**当前行为**（基于 chain 顺序）是新 drone 参与所有后续 system。这是有意义的（出生即投入战斗）但需要显式声明。

**要求**:
1. 修正 P0-2 §3.10 的描述为：「Drone 在 Phase 2b spawn_system 中创建——位于 death_mark（释放 room cap）之后、combat/decay/death_cleanup 之前。新 drone 在同 tick 参与战斗和衰减。」
2. 评估是否需要保护新 spawn 的 drone 在同 tick 免于攻击（`SpawnProtection` component 持续 1 tick？）。如果不需要，文档化「出生即可能被攻击」为有意设计。

---

### D7 [CRITICAL] 补丁: 原评审 D1 的 Sharding 模型——设计仍模糊

**位置**: DESIGN §7.2, §10

原评审 D1 指出了多 Shard MMO 模型未定义的问题。ROADMAP.md 显示 engine 已实现 `ShardId/ShardConfig/ShardDiscovery (323行)`。但设计文档仍未定义：

1. Shard 的**正确性边界**: 同一世界跨 shard 的一致性模型是什么？FDB 集群跨 shard 共享——但 Bevy World 是每 engine 实例独占的。如果两个 shard 各自运行独立的 engine 进程——它们的 Bevy World 是独立的。COLLECT 从本地 Bevy World 读——跨 shard drone 不可见。
2. Shard 的**可见性**: 玩家在 shard A 的 drone 能否看到 shard B 的实体？如果不能——shard 实际等于独立世界。如果能——需要跨 shard 的 `is_visible_to` 实现（FDB 查询？Dragonfly 查询？同步延迟？）
3. **Shard 间的命令冲突**: 如果两个 shard 的玩家在同一 tick 对同房间的同一资源点提交 Harvest——如何解决？单 engine 用种子洗牌解决，多 engine 无全局洗牌。

**要求**: 在明确 sharding 语义之前，DESIGN §7.2 中的「多个 Engine 实例可并行运行」表述应限定为「每个 Engine 实例服务一个独立世界——World 模式不跨 engine。」Sharding 留至 Phase 6+ 的独立设计。

---

## HIGH SEVERITY ISSUES

### H1 [HIGH] FDB Commit 成功但 Dragonfly Update 静默失败——读路径一致性窗口

**位置**: P0-1 §4.2, §6.1, DESIGN §6.2, tech-choices §6

数据流：
```
EXECUTE → FDB commit (权威) → Dragonfly.update(delta) → NATS.publish(delta)
```

P0-1 §4.2：「BROADCAST failure never rolls back committed tick」

如果 FDB commit 成功，Dragonfly.update 静默失败（网络瞬断、Dragonfly 进程重启窗口），REST API 和初始 WS 连接状态加载（通过 Dragonfly）将返回**旧版本**数据。客户端通过 WS delta（NATS）已收到新数据——但新连接或 REST API 调用者看到旧数据。

P0-1 §6.1 提到「Dragonfly cache stale: 无——FDB 为权威源；下次写入时自动刷新」。但「下次写入」是下一 tick——中间有 3s 窗口。

**要求**: 在 Dragonfly 缓存条目中写入 `last_tick` versionstamp（从 FDB versionstamp 派生）。Reader 比较 Dragonfly 的 version 与 FDB 的 `/tick/latest` counter。若 Dragonfly version < FDB latest，reader 识别出 staleness 并回退到 FDB 直读。

---

### H2 [HIGH] Fuel Refund Deploy-Reset 规则的 session_id 定义缺失

**位置**: P0-2 §7.2

P0-2 §7.2：「Deploy-reset 规则: refund credit 与玩家绑定。若玩家在 tick N+1 执行了任何部署操作… tick N 及之前累计的 refund credit 清零。例外: 同一 session 内的迭代部署（同 session_id）不清除 credit。」

**问题**: `session_id` 的定义完全缺失：
- 是 WebSocket 连接 session？OAuth2 token session？浏览器 tab session？
- 如果是 WebSocket session——WS 断开重连 = 新 session → 积累的 refund credit 被清除（不合理）
- 如果是 OAuth2 session——AI agent 的 MCP 连接可能使用同一 token 数小时 → 所有退款累积（可能被滥用）
- 如果是 explicit deployment session（由客户端声明 begin/end）——未定义 API

**要求**: 明确定义 session_id 的生命周期和来源：
1. session_id 由客户端在首次部署时通过 `X-Swarm-Deploy-Session: <uuid>` header 声明
2. 同一 session_id 的有效期为最近一次部署后的 300 tick（15 分钟@3s tick）
3. 超时未部署 = session 过期 → refund credit 保留（不触发 deploy-reset）
4. 新 session_id = 清空旧 session 的 refund credit

---

### H3 [HIGH] BodyPart range 与 CommandAction range 的配置不一致

**位置**: P0-7 §6.1 (BodyPart 字段表), P0-2 §3.9 (Heal 校验)

P0-7 §6.1 字段说明表格中注释：
> `range` — 生效距离。注：CommandAction 的 `in_range()` 校验可覆盖此值（如 Heal body part range=1 但实际命令有效距离=3）

这明确承认：body part 配置中的 `range=1` 与实际 Heal 命令的 `range=3` 不同。玩家在 world.toml 中看到 `Heal range=1` 但引擎用 range=3 校验——配置成为误导。

**问题不止 Heal**：如果 body part 的 range 被 command 的 range 覆盖——为什么 body part 还需要 range 字段？如果 body part range 是生成时的属性（spawn 时记录）而 command range 是执行时的校验——那就需要两个独立字段并说明关系。

**要求**:
1. 决定：body_part.range 是权威值还是可覆盖的默认值？
2. 如果 body_part.range 是权威值——修正 Heal body part 为 `range=3`
3. 如果 command 可覆盖——移除 body_part 的 range 字段或重命名为 `default_range`，在 P0-7 字段表中明确是可覆盖的

---

### H4 [HIGH] Tick 输出 JSON Schema 校验失败策略过严——全或无

**位置**: P0-2 §1.1, §2.1

P0-2 §1.1：「校验失败的 tick 输出：不计入 refund（未进入指令管线），记录到 TickTrace 为 `TickValidationFailed`。」

P0-2 §2.1：「若 CommandIntent 包含这些字段（player_id/source/tick/auth）→ 整个 tick 输出被拒绝（TickValidationFailed），不计入 refund。」

**问题**: 玩家的 100 条合法指令 + 1 条含禁止字段的指令 = 全部丢弃。这是拒绝服务攻击向量（恶意提交含禁止字段的指令以触发全丢弃），也是糟糕的开发体验（一个拼写错误导致整个 tick 浪费）。

更合理的模型：在反序列化阶段逐条校验，合法指令通过，含禁止字段的指令单独拒绝。只有「顶层 JSON 根本不是数组」才应判全丢弃。

**要求**:
1. 区分：JSON 结构错误（非数组、非 JSON）→ TickValidationFailed（全丢弃）
2. 单条指令含禁止字段 → 该指令单独拒绝（记录 RejectionReason），其余指令正常处理
3. 更新 P0-2 §2.1 的禁止字段处理策略

---

## MEDIUM SEVERITY ISSUES

### M1 [MEDIUM] Neutral Drone (Hack) 的可见性与目标性

**位置**: P0-2 §3.12, DESIGN §8.2 (Hack 效果)

Hack 成功后 drone 转为 Neutral (`owner=0`)——不执行 WASM、不消耗 fuel/lifespan、5 tick 后自动恢复原 owner。可见性规则：「对原 owner 保持可见（ally 级），对其他玩家为 enemy 级。」

**歧义**: "其他玩家" 是否包括 Hack 发起者？Hack 发起者投入了 1000 Energy + 200 tick CD 夺取了一架 drone——5 tick 内该 drone 免疫再次 Hack、不执行任何代码、不属于任何人。Hack 发起者应该：
- 能看到 Neutral drone 吗？（应该——否则不知道夺取是否成功）
- 能攻击 Neutral drone 吗？（如果能——夺取 + 击杀 = 变相即死；如果不能——需要明确规则）

**要求**: 在 P0-2 §3.12 末尾增加 Neutral drone 的完整交互规则矩阵：
| 交互方 | 可见 | 可攻击 | 可治疗 | 可再次 Hack |
|--------|------|--------|--------|-------------|
| 原 owner | ✅ | ✅ | ✅ | ❌ (免疫) |
| Hack 发起者 | ✅ | ? | ? | ❌ (免疫) |
| 第三方 | ✅ (enemy级) | ✅ | ❌ | ❌ (免疫) |

---

### M2 [MEDIUM] Controller Upgrade Progress 转换率未定义

**位置**: DESIGN §3.1, RCL 升级表

DESIGN §3.1：「在 Controller 所在房间内向 Controller 存入资源（通过 Transfer 指令），每 tick 自动转换为 progress。progress >= progress_total 时升级到下一级。」

**缺失**:
1. 转换率未定义——1 Energy → N progress？所有存入资源都转换还是 capped per tick？
2. RCL 升级表列的 progress 值（RCL2=200, RCL3=500...）巨大——如果 1 Energy = 1 progress，升级到 RCL8 需要 150,000 Energy。这是有意设计还是占位数值？
3. 多人向同一 Controller 存入——是否先到先得（同一 tick 的 phase 2a 竞争）？存款失败的退还？
4. 存入的是全局存储还是本地存储的资源？

**要求**: 增加 Controller upgrade 子规范：
- 转换率：`progress_per_unit = world.toml 可配置，默认 1 Energy → 1 progress`
- 每 tick 转换上限：限制为 deposit 的所有资源（不做二次 cap）
- 竞争规则：Transfer 命令在 Phase 2a 先到先得（标准资源竞争规则）
- 来源：必须从本地存储扣除（无法从全局存储远程存入）

---

### M3 [MEDIUM] Overload Fuel Reduction Timing 需要明确标定

**位置**: DESIGN §8.2 (Overload), P0-2 §3.14, P0-8 (Overload IDL)

Overload 消耗目标 fuel budget 500k。时序：玩家在 Phase 1 WASM 执行中消耗 fuel → Phase 2 执行 Overload 命令 → 目标玩家的 fuel budget 减少。

目标玩家的 WASM 已在 Phase 1 执行完毕——本 tick 的 fuel 已消耗完。Overload 的效果必然作用于**下一 tick**。这是唯一合理的解释——但这在文档中**无处声明**。P0-2 §3.14 只说「目标 fuel budget 减少 500k」——读者需要自行推导时序。

**要求**: 在 P0-2 §3.14 和 DESIGN §8.2 Overload 描述中显式添加：「效果作用于目标**下一 tick** 的 fuel budget。本 tick 由于目标 WASM 已在 COLLECT 阶段执行完毕，不受影响。」

---

### M4 [MEDIUM] 可见性缓存与 Snapshot 的一致性窗口

**位置**: P0-5 §5, P0-1 §2.3

P0-5 §5：「每 tick、每玩家可见性计算一次并缓存。缓存键: (tick, player_id)。」

P0-1 §2.3：「COLLECT 阶段从 Bevy World 内存读取权威状态，不访问 FDB/Dragonfly。」

一致性：可见性缓存基于 Bevy World 内存状态构建 ——与 snapshot 同源。这是正确的。但缓存在 tick 间失效（「失效: 下一 tick」）——如果 COLLECT 阶段在 tick N 构建缓存后、BROADCAST 阶段的 delta 计算在 tick N（同一 Bevy World 状态）——delta 计算与可见性缓存的实体集合应该完全一致。如果任何系统在 COLLECT 后、BROADCAST 前修改了可见性（不应发生），就会不一致。

**要求**: 在可见性缓存失效策略中增加：缓存仅在 tick_counter 推进时才失效（即新 COLLECT 阶段开始前）。不依赖「下一 tick」这种墙上时间表述。

---

### M5 [MEDIUM] config 跨文档的数值漂移

**位置**: DESIGN §8.2 vs P0-7 §2 vs P0-8

以下参数在多处定义了略有不同的默认值：

| 参数 | DESIGN §8.2 | P0-7 §2 | 差异 |
|------|-----------|---------|------|
| `drone.memory_size` | 1024 | 1024 | 一致 |
| `drone.lifespan` | 1500 | 未在 P0-7 config 中 | — |
| `spawn.cooldown` | 100 (cooldown=100 注释) | 0 (cooldown=0) | 不一致 |
| body_part costs | 与 P0-8 body_cost 表一致 | 与 DESIGN 一致 | 一致 |

`spawn.cooldown` 在 DESIGN 示例 config 中注释为 100，P0-7 完整 config 中为 0。需要收敛。

**要求**: 在 DESIGN §8.3 示例 config 与 P0-7 §2 完整 config 间做一次全量 diff，消除所有差异。建议保留 P0-7 为权威配置源。

---

## LOW SEVERITY ISSUES

### L1 [LOW] global_storage_tax_tiers 的单位不可自文档化

**位置**: DESIGN §8.2 累进税表

配置格式：`[(30,0),(60,1),(85,5),(100,20)]`。表中注释「每10万单位税率」。但 toml 格式中裸整数(1,5,20) 无法让读者（服主）理解这是「每10万单位扣 N 单位」。建议在配置 key 中编码单位：`global_storage_tax_tiers_bp100k` 或使用 `fixed<u32,4>` 精度类型。

---

### L2 [LOW] Rhai 禁止浮点但 P0-7 §2 有 float 类型字段

**位置**: P0-7 §2 (decay_rate=0.001 被写作 float 字面量), DESIGN §8.8 (禁 f64)

P0-7 config 示例中有 `decay_rate = 0.001` —— 这是 f64 字面量。但 DESIGN §8.8 明确「禁 f64」。Rhai 侧的浮点引擎也已关闭。decay_rate 应声明为 `fixed<u32,4>` 类型（即 10 表示 0.0010）。

**要求**: P0-7 config 示例中所有小数值改为 `fixed<u32,4>` 定点表示。

---

### L3 [LOW] Arena 模式的 spec_delay 最小值约束被 P0-5 新增规则覆盖

**位置**: P0-5 §3.5

P0-5 §3.5 规定：「World 模式下若 public_spectate = true，spectate_delay 必须 ≥ 50 tick」。但 Arena 模式在 DESIGN §10 中定义为 `spectate_delay=0`（赛后公开）。Arena 赛后的公开回放与 spectate_delay 约束的关系未说明——是赛后免除 spectate_delay 限制？还是 spectate_delay 仅影响实时观战而不影响回放？

---

## CONSISTENCY CROSS-CHECK

### DESIGN.md ↔ P0-1 (Tick Protocol)
- ✅ 三阶段模型一致（COLLECT → EXECUTE → BROADCAST）
- ✅ 2500ms/500ms 超时一致
- ✅ 种子洗牌、inline 命令、deferred spawn 一致
- ✅ P0-1 §6 失败语义矩阵补充了 DESIGN 不覆盖的边界
- ⚠️ P0-1 §3.5 tick abandon 行为已完整定义（回答了原 D6）
- ⚠️ 原 D6 中「tick_counter 推进时机」已明确——在 FDB commit 成功后（P0-1 §3.5 末尾 state diagram）

### DESIGN.md ↔ P0-2 (Command Validation)
- ✅ CommandIntent → RawCommand → ValidatedCommand 层次完整
- ✅ 指令校验矩阵覆盖 12 种基础命令 + 6 种特殊攻击
- ✅ Refund 策略（退 50%/不退）与竞争模型一致
- ⚠️ Spawn 文档矛盾（D6）
- ⚠️ Tick 输出全或无策略过严（H4）

### DESIGN.md ↔ P0-3 (MCP Security Contract)
- ✅ MCP 不是 gameplay 通道——与 DESIGN §4.2 一致
- ✅ 可见性过滤与 P0-5 一致
- ✅ 限流合理且文档化
- ✅ AI 快照安全契约（untrusted 标记+分隔符）设计正确

### DESIGN.md ↔ P0-4 (WASM Sandbox)
- ✅ Wasmtime fuel metering + epoch interruption 配置完整
- ✅ 恶意 WASM 测试类别覆盖全面
- ✅ OS 隔离三层（seccomp/cgroup/netns）设计正确
- ✅ 内存布局（前后 guard page）防御完善
- ⚠️ 编译预算（30s/512MB）与 P0-9 的 DryRun/Simulate source 的 compile budget 共享——需确认不冲突

### DESIGN.md ↔ P0-5 (Visibility)
- ✅ `is_visible_to` 单点真源一致
- ✅ drone 感知 vs 玩家视野的分层一致
- ✅ 旁观者信息分级表（实体状态 vs 内部状态 vs 调试信息）设计优秀

### DESIGN.md ↔ P0-7 (World Rules Engine)
- ✅ 资源类型/身体部件/建筑/伤害/特殊效果——全可配置化一致
- ✅ Rhai 事务模型（buffer → apply）与 P0-1 EXECUTE 阶段集成模式一致
- ⚠️ P0-7 中 Rhai buffer apply 与 FDB 事务的关系未明确交叉引用（D3）
- ⚠️ 配置数值漂移（M5）

### DESIGN.md ↔ P0-8 (API IDL)
- ✅ Command 变体 20 种——与 P0-2 校验矩阵对应
- ✅ body_cost 表权威来源在 P0-8——与 DESIGN §8.2 一致
- ⚠️ TransferToGlobal/TransferFromGlobal 归属问题（D2）

### DESIGN.md ↔ P0-9 (Command Source Model)
- ✅ 12 种来源建模完整
- ✅ Source Gate 拦截至关重要——保障只有 WASM 能提交 gameplay 命令
- ✅ 能力矩阵详尽

### ROADMAP.md ↔ 规范
- ✅ Engine 151 tests + sandbox 10 tests + SDK/TS 11 tests + Rust 8 tests
- ✅ 所有 B6-B11 审计缺口已关闭
- ✅ 所有 G1-G7 设计与实现差距已关闭
- ✅ H1a-H1b 特殊攻击已实现
- ⚠️ Sharding 实现（323行）先于设计定义——存在实现与设计漂移风险

### 内部一致性（DESIGN.md self-consistency）
- ✅ 资源 → body part cost → action cost pipeline 连贯
- ✅ Body part → CommandAction → custom_actions 扩展链清晰
- ✅ World Rules → TOML → ECS system registration 集成合理
- ✅ Rhai mod 生命周期（init → tick_start → tick_end）干净
- ⚠️ Controller 升级进度转换率未定义（M2）
- ⚠️ ClaimController 机制完全缺失（D5）

---

## ALGORITHMIC COMPLEXITY & SCALABILITY

### Tick 预算可行性（目标: 3s/tick）

| 阶段 | 复杂度 | 100 玩家 | 500 玩家 | 1000 玩家 | 瓶颈分析 |
|------|--------|---------|---------|----------|---------|
| Phase 1: Snapshot | O(R × E_visible) per-room serial, per-player filter | <10ms | <50ms | <100ms | 按房间序列化+按玩家过滤的优化已经到位 |
| Phase 1: WASM exec | O(P) parallel ops | 2.5s budget | ~500ms/core | ~1s/core | 独立 sandbox 进程，线性随核心数扩展 |
| Phase 2a: Command inline | O(C) serial | <50ms | ~250ms | ~500ms | **第一瓶颈**。50k commands × 50μs/validate = 2.5s |
| Phase 2b: ECS systems | O(E) serial | <10ms | ~50ms | ~100ms | 可接受。Bevy archetype 存储对 cache 友好 |
| Phase 3: Delta + Dragonfly | O(ΔE) | <10ms | <50ms | <100ms | 可接受 |

**第一瓶颈**: Phase 2a 串行命令执行。1000 玩家 × 50 drone = 50k drone × 1-2 cmd/drone = 50-100k commands/tick。单条校验（entity lookup + owner check + body part check + range + resource check）估计 50-100μs → 5-10s。

**缓解路径**:
1. **Phase 3 前不需要**: 单 engine 承载 500 活跃玩家已足够 MVP
2. **空间分区并行化 (Phase 6+)**: 不同房间的命令无冲突 → 按房间并行执行 Phase 2a
3. **批量预校验 (Phase 4+)**: 先并行校验所有命令（只读），再串行应用（写入）——校验瓶颈变为并行化

### WASM 执行并行化上限

500 sandbox worker 独立进程，每个 Wasmtime 实例 ~64MB WASM 内存 + 128MB OS 内存上限 = ~192MB per worker。500 workers = 96GB RAM。这是部署时的资源规划考虑，非设计问题。

### 回放存储估算

- 每 tick 存储：RawCommand[] + 拒绝记录 + TickMetrics ≈ 100KB/tick（500 活跃玩家）
- 每 100 tick 完整快照：50,000 实体 × 1KB ≈ 50MB
- 每天（28,800 tick @3s）：100KB × 28,800 + 50MB × 288 ≈ 2.88GB + 14.4GB = 17.3GB/day
- FDB LSM-tree 存储层对此完全可承受

增量 delta 存储（只存变更实体）可在 Phase 4+ 将存储降低 ~90%。

---

## SUMMARY

| 等级 | 数量 | 问题 | 阻塞阶段 |
|------|------|------|---------|
| **CRITICAL** | 7 | D1 (Bevy 回滚), D2 (TransferToGlobal), D3 (Rhai+FDB 原子性), D4 (Phase 2a/2b 边界), D5 (ClaimController), D6 (Spawn 矛盾), D7 (Sharding 语义) | ABI 冻结前 |
| **HIGH** | 4 | H1 (Dragonfly staleness), H2 (session_id), H3 (BodyPart range), H4 (全或无校验) | Phase 1 |
| **MEDIUM** | 5 | M1 (Neutral drone), M2 (Controller progress), M3 (Overload timing), M4 (可见性缓存), M5 (配置漂移) | Phase 2 |
| **LOW** | 3 | L1 (tax_tiers 单位), L2 (float 字面量), L3 (spectate_delay) | 非阻塞 |
| **STRENGTHS** | 11 | S1–S11 | — |

**关键路径**: D1–D7 必须在 ABI/IDL 冻结前解决——其中 D1（Bevy 回滚）是唯一需要架构方案选择的（快照 vs 「先提交后应用」模式），其余均可通过设计澄清解决。H1–H4 在 Phase 1 实现前澄清。M 级问题大多是无歧义的文档补充，可并行进行。

**架构总体评估**: 设计的核心正确性成立——延迟指令模型、确定性 ECS pipeline、FDB 权威源、WASM 统一沙箱这四大支柱没有结构性问题。发现的问题集中在边界定义（Controller lifecycle、TransferToGlobal 通道、Spawn 时机、Phase 2a/2b 原则）和文档一致性——这些是精细化的设计补充，而非架构返工。
