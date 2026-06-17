# R7 设计评审 — Architect 视角（Claude Opus 4.7）

> 从 kanban 日志提取——write_file bug 导致原始输出丢失。

    Given that A1 is the same blocker R6 flagged and remains unresolved, combined with these consistency issues across multiple documents, I'm leaning toward REQUEST_MAJOR_CHANGES rather than CONDITIONAL_APPROVE.我已完成对 7 个设计文档 + 11 个 spec 的全量审查。下面是按 Architect 视角的 R7 评审结论。
    ────────────────────────────────────────
    R7 设计评审 — Architect 视角（Claude Opus 4.7）
    ────────────────────────────────────────
    Verdict
    REQUEST_MAJOR_CHANGES
    理由（一句话版）：R6 标记的 A1 (Phase 2b ECS 主链不一致) 在本轮跨 5 个权威文档出现 4 个不同版本——这是 Tier 1 实现的核心确定性合同，没有闭合就动手等于把不一致烧进运行时。叠加发现 Tier 1 容量声明自相矛盾、spawn body_cost refund 货币错位、4 项命名/默认值漂移。
    ────────────────────────────────────────
    Strengths（值得保留的部分）
    - specs/security/05-visibility §10 Oracle 防线：覆盖 MCP/dry_run/simulate/explain 五个查询面 + omitted_count 分桶 + 拒绝码等价类，逻辑闭环；这是迄今为止可见性合同最严密的版本。
    - specs/core/02 §3.17 Overload 抗永久锁死证明：把 5 行的不变量（全局冷却 + fuel 下限 + 恢复速率）化成数学反证。这种风格是真正的"边界穷举"，可以推广到其他特殊攻击。
    - specs/security/09 §7.0 Transport audience matrix：mcp/ws/rest/replay 四种 transport 的 aud 绑定 + X-Swarm-Transport header + 跨 transport 拒绝规则，把跨协议重放/混淆的爆炸面收敛到了一个表格。
    - specs/core/01 §3.1 Forward Secrecy 威胁模型：明确说明"不实现密码学完善前向保密"是因为与确定性回放冲突，并提供 epoch bump runbook 作为操作层缓解——属于把"已接受的风险"显式落纸的好范例。
    - Tier 1/2/3 Entry Gate 矩阵 (engine.md §3.2)：哪些 future 项在 Tier 1 通过 feature flag 排除，是防止 MVP 被未来扩展污染的有效护栏。
    ────────────────────────────────────────
    Concerns
    ────────────────────────────────────────
    A1 [Critical] Phase 2b ECS 主链跨 5 文档 4 版本不一致 — R6 阻塞未闭合
    位置：design/engine.md §3.2 + specs/core/01 §3.4 + specs/core/02 §3.19 + specs/core/07 §3 + design/gameplay.md §8.4
    各文档实际给出的主链：
    来源: engine.md §3.2 文字框图
    主链顺序: death_mark → spawn → combat → death_cleanup
    并行: regen, decay
    链长: 4
    ────────────────────────────────────────
    来源: engine.md §3.2 散文段落
    主链顺序: death_mark → spawn → spawning_grace → combat → status_advance →
      death_cleanup
    并行: regen, decay
    链长: 5+1
    ────────────────────────────────────────
    来源: specs/01 §3.4（Rust 代码块）
    主链顺序: death_mark → spawn → spawning_grace → combat → status_advance
    并行: regen, decay
    链长: 5 + cleanup
    ────────────────────────────────────────
    来源: specs/02 §3.19（散文）
    主链顺序: death_mark → spawn → spawning_grace → combat → status_advance
    并行: regen, decay
    链长: 5
    ────────────────────────────────────────
    来源: specs/07 §3（Rust 代码块）
    主链顺序: death_mark → spawn → regen → combat → decay → death_cleanup
    并行: 无并行
    链长: 6 串行
    ────────────────────────────────────────
    来源: design/gameplay.md §8.4
    主链顺序: death_mark → spawn → combat → death_cleanup
    并行: regen, decay
    链长: 4
    问题严重性：specs/07 把 regeneration 串到 combat 之前，并取消并行。这与 engine.md 散文段说的"regen 在 combat 之后补充资源"语义直接冲突，且把 spawning_grace 和 status_advance 完全删掉——按 specs/07 实现，新生 drone 没有无敌帧、Hack 控制锁不会推进、Overload fuel 不会恢复。
    specs/07 §3 是 WorldConfig::register_systems() 的权威 Rust 代码——这是真正会被实现者直接抄进 engine 的代码。任何文档间不一致都会以这段代码胜出。
    修正建议：以 specs/01 §3.4 为准（是唯一同时包含 5 步主链 + 并行 regen/decay + 末尾 death_cleanup 的版本），统一改写：
    - engine.md §3.2 文字框图（补 spawning_grace + status_advance）
    - specs/07 §3 整段 Rust 代码（重写为 chain 5 + parallel + cleanup 三段式）
    - design/gameplay.md §8.4 整段 Rust 代码
    - engine.md §3.2 表格 "Phase 2b" 行（补两个 system）
    并在 specs/01 §3.4 加一句"本节定义为 ECS 主链的唯一权威来源；其他文档的代码示例必须从这里复制粘贴"。
    ────────────────────────────────────────
    A2 [High] Tier 1 容量声明自相矛盾——MVP 目标不可达
    位置：design/engine.md §3.1a "扩展策略声明" + design/engine.md §3.2 "Tier 1" 行 + specs/core/07 §2 "max_drones_per_player"
    - §3.1a：单 Engine 实例的 MVP 目标 = 500 活跃玩家
    - §3.2：Tier 1 = ≤500 drone，≤50 房间
    - specs/07：max_drones_per_player = 500
    爆炸半径分析：500 活跃玩家若每人平均控制 10 个 drone（这是 Screeps 类游戏的最低门槛），世界总 drone 数 = 5000——直接踏入 Tier 2 范围。若 500 玩家 × 1 drone，玩家无法实现任何分工策略（采集 + 防守 + 占领至少各需 1 drone）。
    更严重：specs/07 允许单玩家上限 500 drone——一个玩家就能吃满整个 Tier 1 容量。
    修正建议（三选一）：
    - 把 §3.1a 改成"目标 MVP = 50 活跃玩家"，与 ≤500 drone 对齐
    - 把 §3.2 Tier 1 改成 ≤5,000 drone（但这要求 specs/01 §2.3 的 256KB snapshot + 16MB 全量快照基准重做）
    - 把 specs/07 max_drones_per_player 默认改成 min(50, total_drone_budget / active_player_count)，并在 §3.2 写明"Tier 1 容量按 50 玩家 × 10 drone 拆分"
    无论哪种，必须三处同步。
    ────────────────────────────────────────
    A3 [High] spawn body_cost refund 货币错位 — Energy ↔ fuel 混淆
    位置：specs/core/02 §3.8 "Spawn body_cost 扣除时点"
    原文："若 Phase 2b spawn_system 创建失败（如 room cap 竞争），已扣除的 body_cost 全额退还到原扣费来源（spawn.energy 优先，其次全局存储）。此 refund 记入 next_tick_fuel_credit（见 §7.2），不计入当前 tick 的 fuel budget。"
    问题：
    - body_cost 的单位是资源（如 1000 Energy），扣的是 spawn.energy 字段
    - next_tick_fuel_credit 的单位是 WASM fuel（10M instruction units），属于 §7.2 定义的 fuel refund 池
    - 把资源 refund 记到 fuel credit 池里在语义上不通——1000 Energy 等于多少 fuel？不存在转换关系
    按散文实际意图，正确语义应该是：
    - 失败 spawn 的 Energy 直接退回 spawn 建筑（或全局存储）的资源池——这是即时恢复，与 fuel 无关
    - 不写入 next_tick_fuel_credit
    修正建议：删除 specs/02 §3.8 末句"此 refund 记入 next_tick_fuel_credit（见 §7.2），不计入当前 tick 的 fuel budget"。改写为："此资源 refund 在 Phase 2b spawn_system 失败的同 tick 内即时恢复到原扣费来源（spawn.energy 优先，spawn.energy 容量不足部分回到全局存储）。资源 refund 与 §7.2 fuel refund 是独立池——前者操作 ResourceStore，后者操作 fuel budget。"
    ────────────────────────────────────────
    A4 [High] aging_system 在 ECS 链中位置缺失
    位置：design/engine.md §3.1 + design/gameplay.md §8.2 + specs/core/01 §3.4 + specs/core/07 §3
    drone lifecycle 由 §3.1 Drone.age + DEFAULT_DRONE_LIFESPAN 定义，aging mechanic 涉及：
    1. 每 tick age += 1（或 idle 100% / active 110%）
    2. Controller/Depot 维修范围内 age -= repair_aging
    3. age >= age_max 时触发死亡
    但没有任何文档说这三件事跑在哪个 system 里。decay_system 文档定义为"疲劳/冷却递减"，与 age 无关。death_mark_system 标记待死亡 entity——按谁的指示？
    可能的实现走向：
    - Option 1: aging_system 独立，在 decay 之后 / death_mark 之前（违反"主链确定 + 仅 regen/decay 并行"约定）
    - Option 2: 在 decay_system 内偷偷做（与 decay_system 的语义合同不符）
    - Option 3: 在 death_mark_system 入口扫描所有 drone 计算 age（O(N) 操作放在主链头部，影响 tick 预算）
    实现者会按个人偏好选——这正是 R6 提出 A1 的同类风险扩散。
    修正建议：在 specs/01 §3.4 主链中显式插入 aging_system，位置在 status_advance_system 之后、death_mark_system 之前（因为 aging 增长可能触发死亡，必须先 advance age 才能 mark）。读写矩阵补一行：aging_system: R Position, R Owner, RW Age, R MaintenanceContext。design/engine.md §3.1 的 prose 已经说"达到 lifespan 后自动死亡"，需要在 §3.2 主链流程中标出位置。
    ────────────────────────────────────────
    A5 [Medium] code_update_cooldown 三处默认值不一致
    位置：design/gameplay.md §8.2 表格 + specs/core/07 §2 toml + design/gameplay.md §8.3 toml
    - design/gameplay.md §8.2：默认 5，World 模式最小 5，理由是防止 re-deploy refund 滥用
    - design/gameplay.md §8.3 example：update_cooldown = 100
    - specs/core/07 §2 example：update_cooldown = 0
    specs/07 默认 0 直接违反 §8.2 的反滥用约束——服主拿默认配置启服就有漏洞。
    修正建议：统一为 5（与 §8.2 反滥用约束的最小值一致）。example toml 中改为 update_cooldown = 5，注释"World 模式最小值，禁止 
    < 5"。validate_config() 中加入断言。
    ────────────────────────────────────────
    A6 [Medium] respawn enum 命名分裂
    位置：design/gameplay.md §8.2 + design/engine.md §3.1a + specs/core/01 §2.5 + specs/core/07 §2
    - design/gameplay.md §8.2：respawn_policy: NewRoom | SameRoom | Spectate | Ban（4 值）
    - design/engine.md §3.1a：respawn_policy = NewRoom（隐含）
    - specs/core/01 §2.5：respawn_policy = "NewRoom"，注释 "NewRoom | OriginalRoom"（2 值且名字不同）
    - specs/core/07 §2：respawn = "NewRoom"（key 名不同）
    三个分歧：
    1. key 名（respawn vs respawn_policy）
    2. enum 长度（4 vs 2）
    3. enum 值名（SameRoom vs OriginalRoom）
    代码生成器从 IDL 出发，IDL（specs/gameplay/08-api-idl.md）里没看到 RespawnPolicy 枚举——枚举将由 specs/07 决定，那就只有 NewRoom，玩家失去原房间出生权。
    修正建议：在 specs/gameplay/08-api-idl.md enums: 中加入 RespawnPolicy: [NewRoom, OriginalRoom, Spectate, Ban] 作为权威定义。所有文档的 example 改为 respawn_policy（key 名），specs/07 同步。
    ────────────────────────────────────────
    A7 [Medium] CommandIntent.action 序列化字段名分裂（type vs cmd）
    位置：specs/core/02 §2.1 + specs/core/04 §3.3 + design/gameplay.md §8.5
    - specs/core/02 §2.1：{"sequence": 3, "action": {"type": "Move", ...}}
    - specs/core/04 §3.3：改为 { "cmd": "move", ... } JSON 指令
    - design/gameplay.md §8.5（TS SDK）：commands.push({ cmd: "spawn", body: [...] })
    - specs/gameplay/08-api-idl.md §2：使用 Move: YAML key（非 JSON 字段）
    JSON wire format 的 discriminator 字段：type 还是 cmd？两种命名各占一半。
    修正建议：在 specs/gameplay/08-api-idl.md §1 加一行"CommandIntent JSON discriminator 字段统一为 type，所有 wire 形态包括 SDK example 必须使用 type"。改写 specs/04 §3.3 和 design/gameplay.md §8.5 example。
    ────────────────────────────────────────
    A8 [Medium] RuleMod tick_end 钩子位置漂移
    位置：specs/core/07 §3 + design/gameplay.md §8.7（"引擎集成"代码）
    - specs/07 §3：未定义 RuleMod tick 钩子的 ECS 位置
    - design/gameplay.md §8.7：.after(death_cleanup_system)
    但 specs/07 §5.1 又说 RuleMod 通过 RhaiActionBuffer 事务性 apply——apply 必须在 FDB commit 之前（否则 effects 不进 tick），但 death_cleanup 之后就到 BROADCAST 了，FDB commit 已经发生。
    修正建议：明确规定 RuleMod on_tick_end 钩子在 ECS 主链结束之后、FDB commit 之前。在 specs/07 §3 + §5.1 + design/gameplay.md §8.7 同步，补 ECS 链最后增加 rulemod_apply_system.after(death_cleanup_system).before(fdb_commit)，把 RhaiActionBuffer 在此 system 中 flush。
    ────────────────────────────────────────
    A9 [Low] status_advance_system 未列入读写矩阵
    位置：specs/core/01 §3.4 "Component/Resource 读写矩阵"
    矩阵列了 6 个 system 的读写——缺 status_advance_system 和 spawning_grace_system。这两个是主链中的，需要在矩阵中给出读写记录才能证明并行安全性。
    特别是 status_advance_system 写 Owner（Hack stage=5 时切换 owner）+ 写 PlayerFuelBudget（Overload 恢复 fuel_budget/1000 per tick）。如果 regeneration_system 也写 PlayerFuelBudget（不太可能，但需要检查），就会破坏当前的并行安全证明。
    修正建议：在 specs/01 §3.4 矩阵中补两行：
    spawning_grace:  - | - | - | - | - | - | - | - 
                     (附加 SpawningGrace 组件，无并行风险)
    status_advance:  R | R | - | - | RW | - | - | RW
                     (写 Cooldown, 写 Owner; 与并行 regen/decay 不冲突)
    并显式标注：PlayerFuelBudget 仅由 status_advance_system 和 Overload command (Phase 2a) 写入——不在并行 system 中。
    ────────────────────────────────────────
    A10 [Low] Tier 1 PathFind explored_nodes 预算与 player count 不匹配
    位置：specs/core/04 §6 + specs/core/01 §8.2
    - 单玩家 path_find 预算：100,000 explored_nodes/tick（specs/04 §8）
    - Tier 1 容量：≤500 drone（按 A2 不论是 50 玩家还是 500 玩家）
    最坏情况：500 玩家 × 100,000 = 50M nodes/tick，3 秒 tick 内必须完成。A* 在 50×50 房间内最多 2,500 nodes/path × 9 房间 = ~22.5K nodes/path——单 path 在预算内，但聚合 50M nodes/tick 是否能在 1500ms COLLECT 阶段完成（PathFind 与 WASM 共享同一 fuel 预算）？
    修正建议：在 specs/04 §6 加一行"全局 path_find 预算 = min(N_players × 100k, GLOBAL_PATHFIND_CAP)"，给出 GLOBAL_PATHFIND_CAP 上限。或在 §8.2 加入"按玩家数动态调整 per-player 预算"的策略。
    ────────────────────────────────────────
    Missing（应有但缺失的合同）
    1. aging_system 的位置 + 读写矩阵记录（见 A4）
    2. spawn body_cost refund 资源池路径（见 A3）  
    3. status_advance_system 读写矩阵 + 与 regeneration 的并行证明（见 A9）
    4. RuleMod tick 钩子在 ECS 主链中的位置 + FDB commit 时序（见 A8）
    5. Drone aging 与 SpawningGrace 的同 tick 顺序：新生 drone 在第 1 tick 是否衰老？（涉及 idle vs active 110% 速率的边界）
    6. Tier 1 → Tier 2 迁移 entry gate：specs/future/T2-incremental-snapshot.md 已存在 spec 文档，但 design/engine.md "Tier Entry Gate 矩阵"中只标记 ❌/✅，没有具体的迁移触发指标（drone 数 / tick 时间 / 内存占用）
    7. PathFind 全局预算 cap（见 A10）
    8. PlayerFuelBudget 的 ECS Component 类型：specs/01 §3.4 矩阵以及 specs/02 §3.12 多次提到，但没有在任何 ECS Component 列表中显式定义。它属于 player entity 还是全局 Resource？
    ────────────────────────────────────────
    Phase Ordering（依赖关系评估）
    7 phase 假设的依赖链可能是 R3-R7 反复评审形成的隐含路径。从架构视角看：
    P1 [Engine 核心 + ECS 链]   ──┐
    P2 [WASM Sandbox + IDL]    ──┤
                                  ├──→ P5 [Gameplay 单测]  ──→  P7 [Tier 1 集成]
    P3 [Command Pipeline]      ──┤
    P4 [Visibility + Source]   ──┘
                                                                │
    P6 [Gateway + MCP]         ─────────────────────────────────┘
    关键依赖（不可跨）：
    - P1 ECS 链 必须先于 P3 Command Pipeline：Phase 2a 的 inline apply 走 validate_and_apply()，apply 的目标是 ECS World——ECS 系统未确定（A1）等于 apply 目标未确定
    - P4 Visibility 必须先于 P6 Gateway：MCP/WS/REST 都依赖 is_visible_to——Gateway 实现拿不到这个函数就只能产 placeholder
    - P5 Gameplay 单测 必须基于 P1 + P3 + P4 全部稳定：8 种特殊攻击的状态机测试依赖 status_advance_system 和 visibility oracle 都完成
