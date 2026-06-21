# R31 Design & Economy 独立评审报告

> Reviewer: `rev-dsv4-design-economy` (DeepSeek V4 Pro)
> 评审视角: 博弈论均衡分析、策略深度度量、资源流建模、Nash均衡/Pareto最优/演化稳定策略、anti-snowball数学完备性、信息不对称对策略空间的影响

---

## 1. Verdict

**REQUEST_MAJOR_CHANGES**

---

## 2. 发现的问题

### Critical

#### C1 — Balance Sheet 全负无 break-even，与原声称矛盾

- **文件**: `design/economy-balance-sheet.md` §2.1–§2.5
- **位置**: 行 35-130（收支平衡表全部场景）
- **问题描述**: Balance Sheet 中 1/2/3/5/10/20/50 房间的**每一个场景**净流量均为负值（-30, -65, -110, -250, -485, -1900, -11625）。§2.1 声称 "Controller 升级到 RCL 2-3 后可达收支平衡" 且在 §2.3 Growth Path 中声称 tick 2000+ "✅ 自维持"——但 Balance Sheet 本身**从未演示任何一个 break-even 或净正场景**。这是文档内部逻辑矛盾：证明文件声称的结论与自身提供的数据直接冲突。若所有场景均为净负，经济系统是纯死亡螺旋而非可收敛系统。
- **影响**: 破坏了 Anti-Snowball 证明的可靠性——如果一个系统在所有测量点均为亏损，则「收敛」实质上是「玩家破产」而非「均衡」。无法区分「设计目标为软上限」与「设计缺陷导致全局亏损」。
- **修复建议**:
  1. 为 1–3 房间提供**真实 break-even 场景**（含 Controller 升级到 RCL 2-3 后的收入增量、Harvester 效率优化后的收入提升）
  2. 在现有全负表中加入**过渡期列**：`free_upkeep_ticks` 期间的实际净流量（此时 UpkeepDeduction=0）
  3. 补充 2 房间 + RCL2 Controller + 3 Harvester 的 break-even 计算演示
  4. 若 Standard 模式确实设计为永远净亏损（需持续扩房间求生），应明确声明此设计意图并移除「可达收支平衡」的误导性文本

#### C2 — `transfer_from_global_time` 值跨文档冲突 (5 vs 100)

- **文件/位置**:
  - `design/gameplay.md` 行 313: `transfer_from_global_time` 默认值 = **5 tick**
  - `design/economy-balance-sheet.md` 行 145: `global_withdraw_delay` = **100 tick**（Tutorial/Novice/Standard 三列一致）
  - `specs/core/08-resource-ledger.md` 行 75: `global_transfer_delay` = **100 tick**（标注"全局提取延迟"）
- **问题描述**: 全局→本地提取延迟存在 **20 倍数值冲突**。gameplay.md 定义为 5 tick，但 economy-balance-sheet.md（模式对比表）和 resource-ledger.md（唯一经济权威）均定义为 100 tick。SDK/引擎实现者无从知晓应取何值。
- **影响**: 5 tick vs 100 tick 对游戏经济影响巨大——5 tick 意味着全局存储可近乎即时补给前线（接近 teleport），100 tick 则要求切实的物流规划。这是核心经济参数，冲突直接影响玩法深度。
- **修复建议**:
  1. 以 Resource Ledger §2.1 为准（100 tick）——因其被声明为"唯一设计/数学权威"
  2. 将 gameplay.md 行 313 的默认值从 `5` 修正为 `100`
  3. 在 gameplay.md 行 313 添加注释：`权威值见 specs/core/08-resource-ledger.md §2.1`
  4. 同时检查 `design/interface.md` 中是否也存在冲突值

#### C3 — Balance Sheet 1 房间场景缺 drone spawn 成本，初始条件不明

- **文件**: `design/economy-balance-sheet.md` §2.1 行 33–51
- **位置**: 行 35–49
- **问题描述**: 1 房间收支表列出 "Source Harvester ×2" 收入 20/tick 和 "Controller income" 5/tick，总支出仅维护费 55 + 存储税 0。但未计入生成这 2 架 Harvester drone 的 spawn 成本（合计至少 200+ Energy 一次性支出），也未说明这 2 架 drone 是在 free_upkeep_ticks 期间免费生成还是由 `starting_resources` 支出。Balance Sheet 应反映**稳态**——即 drone 因 lifespan 到期而需要持续 respawn 的摊销成本。
- **影响**: 低估早期经济压力，可能使 break-even 分析偏乐观。drone 寿命 1500 tick，1500 tick 内需重新 spawn 替换死亡 drone，摊销 spawn 成本应计入每 tick 支出。
- **修复建议**:
  1. 在 1 房间场景中加入 drone spawn 摊销：`2 drones × avg_body_cost / 1500 lifespan` ≈ 0.3–0.5/tick
  2. 明确标注 free_upkeep_ticks 期间 drone 生成费用来源（starting_resources 或免税）

---

### High

#### H1 — Anti-Snowball 「证明」无数学推导，仅为断言列表

- **文件**: `design/economy-balance-sheet.md` §4 行 161–168
- **问题描述**: §4 "Anti-Snowball 证明" 是 4 条文字断言而非数学推导。关键声明 "边际收益递减：第 N+1 个房间的维护费增长 > 收入增长" 未给出导数/差分分析。维护费公式 `upkeep = base × rooms × (1 + rooms/cap)` 的边际增长为 `base × (1 + 2×rooms/cap)`，但收入边际增长取决于 Source 密度（每个房间的 Source 数量可变），两者缺乏闭合形式的不等式证明。
- **影响**: 评审无法判断反雪球机制的数学正确性。若 Source 密度高（如某些房间有 3+ Sources），收入边际增长可能超过维护费边际增长，导致大帝国反而更易维持。
- **修复建议**:
  1. 提供维护费边际公式：`∂upkeep/∂rooms = base_upkeep × (1 + 2×rooms/room_soft_cap)`
  2. 提供收入边际上限：`max_income_per_room = max_sources_per_room × max_source_output × harvest_efficiency + controller_max_income`
  3. 证明存在房间数 N* 使得 ∀ N > N*: `∂upkeep/∂rooms > ∂income/∂rooms`（或承认此为假设性设计目标而非保证）

#### H2 — Allied Transfer 每日上限与全局存储容量严重不匹配

- **文件/位置**:
  - `specs/core/08-resource-ledger.md` 行 80: `allied_daily_cap = 10,000 units`
  - `specs/core/08-resource-ledger.md` 行 73: `global_storage_capacity = 1,000,000 units`（通过 api-registry.md §5.1 确认）
- **问题描述**: Allied Transfer 每日上限 10,000 units 仅占全局存储容量 (1,000,000) 的 **1%**。以 3s/tick World 模式计算，24 小时 = 28,800 tick，日均吞吐仅 ~0.35 units/tick——在 Single-Harvester 产出 10/tick 的背景下几乎可以忽略。这使 Allied Transfer 在经济层面**功能上不可用**——盟友间无法进行有意义的资源互助。
- **影响**: 联盟机制的核心经济功能（互助）被设计参数消解。玩家组建联盟的主要经济动机缺失，联盟沦为纯外交/信息共享工具。
- **修复建议**:
  1. 将 `allied_daily_cap` 提升至至少 100,000 units（10% 容量），使每日可转移相当于一个中型玩家的日均净收入
  2. 或将 cap 按接收方 GCL 缩放：`cap = GCL × 20,000`，使大型帝国可以接收更多援助
  3. 若当前值确实为设计意图（联盟仅作信息共享），应明确声明并解释设计理由

#### H3 — Economy Balance Sheet 缺稳态 drone 摊销模型

- **文件**: `design/economy-balance-sheet.md` §2.1–§2.4
- **问题描述**: 所有房间场景的收入/支出表均缺少 drone 生命周期摊销。50 房间场景假设 ~115 Harvesters，这些 drone 每 1500 tick 死亡需重新 spawn。spawn 摊销成本 = `115 × avg_body_cost / 1500` ≈ 115 × 200 / 1500 ≈ 15.3/tick（保守估计），但表中仅在 50 房间行加入 "Drone upkeep 1,000" 而未分解为 spawn 摊销 + 维护。小房间场景完全忽略此成本。
- **影响**: 经济模型不完整，难以验证实际可持续性。
- **修复建议**: 为每个场景加入 `drone_spawn_amortization = active_drones × avg_spawn_cost / drone_lifespan` 行

---

### Medium

#### M1 — Overload 可见性约束与 PlayerId 目标的语义冲突

- **文件**: `design/gameplay.md` 行 766
- **位置**: "必须满足 `is_visible_to(target, attacker)`——不可攻击不可见玩家"
- **问题描述**: Overload 的 target 是 `PlayerId`（非 `EntityId`），但可见性检查 `is_visible_to` 是实体级语义（需要 attacker entity 能看到 target entity）。对于 player-level 目标，可见性定义不明确——攻击者需要看到目标的至少一个实体？全部实体？特定实体？这需要精确定义，否则实现会出现分歧。
- **影响**: 可能产生两种错误实现：(a) 只要 attacker 能看到 target player 的任意 entity 即可 Overload → 过于宽松；(b) 需要看到 target player 的全部 entity → 过于严格，几乎不可用
- **修复建议**: 明确定义 player-level visibility 语义："`is_visible_to_player(attacker, target_player)` 当且仅当 attacker 可看到至少一个属于 target_player 的 entity（drone/structure/controller）"

#### M2 — `special_param` 使用 float 违反定点数合同

- **文件**: `design/gameplay.md` 行 1033
- **位置**: `[[custom_actions]]` 字段表中 `special_param | float | 否 | 特殊效果的参数`
- **问题描述**: 整个引擎的确定性合同（gameplay.md §2.8 行 2011）明确规定 "禁浮点（f64 跨平台/编译器非确定）"。但 `special_param` 字段类型定义为 `float`（如 Leech `special_param = 0.5`，Fortify `special_param = 0.5`，Debilitate `special_param = 2.0`），直接违反定点数合同。
- **影响**: 浮点参数在不同平台/编译器上可能产生不同结果，破坏确定性回放保证。
- **修复建议**: 将 `special_param` 改为 `fixed<u32,4>` 或 `BasisPoints` 定点类型，所有值乘以精度因子（如 `0.5 → 5000 bp`）

#### M3 — Economy Balance Sheet 存储利用率假设无依据

- **文件**: `design/economy-balance-sheet.md` 行 119
- **位置**: "利用率假设：1-3 房间 <30% 存储（免税），5 房间 ~40%，10 房间 ~55%，20 房间 ~70%，50 房间 ~90%"
- **问题描述**: 存储利用率假设未给出推导依据。这些值直接影响存储税计算——如果实际利用率与假设有偏差，净流量将显著不同。例如 20 房间若利用率为 50%（非 70%），存储税从 120 降至 30，净亏损减少 90/tick（~5% 改善）。
- **影响**: 降低了 Balance Sheet 作为验证工具的可靠性——读者无法判断净流量数据反映的是设计目标还是特定假设下的产物。
- **修复建议**: 标注假设为「worst-case 估值」或提供利用率与房间数的函数关系推导（如 `utilization = min(95%, rooms × 1.8%)`）

#### M4 — Controller repair 硬上限公式可读性差

- **文件**: `design/gameplay.md` 行 102
- **位置**: `max(0, age + 1 - min(0.5, controller_count * 0.5))`
- **问题描述**: 公式使用嵌套 `min/max` 使得多 Controller 的收益不直观。实际上 `min(0.5, controller_count * 0.5)` 在 controller_count ≥ 1 时恒为 0.5——这意味着**第二个及之后的 Controller 对 repair 上限毫无贡献**。这个关键设计信息被埋在公式中。
- **影响**: 服主可能误以为多 Controller 可提升 repair 上限，实际并非如此。
- **修复建议**: 简化公式表述为 "每 tick age 回退上限固定为 0.5（即 age 每 tick 至少增长 0.5），无论拥有多少个 Controller"。或考虑改为阶梯式 `min(1.0, 0.3 + controller_count × 0.1)` 使多 Controller 有少量边际收益。

#### M5 — PvE global cap 与 World 再生总量的正反馈循环

- **文件**: `design/modes.md` 行 70
- **位置**: "`max_pve_output_per_tick` 可配置（默认 = 全局 NPC 产出 / tick ≤ 世界再生总量 × 30%）"
- **问题描述**: PvE 产出上限 = 世界再生总量 × 30%。世界再生总量随玩家扩张而增长（更多房间 → 更多 Source → 更高再生总量）。存在潜在正反馈：PvE 收益 → 扩张 → 更多 Source → 更高再生总量 → 更高 PvE 上限 → 更多 PvE 收益。虽然 Empire upkeep 的 O(n²) 机制可作为对冲，但 PvE 作为独立 faucer 源需要自身的反雪球约束。
- **影响**: 如果 PvE 产出效率极高（如 Guardian 蓝图掉落），玩家可能优先 PvE 农场而非 PvP 互动。
- **修复建议**: 考虑将 PvE 全局 cap 按 active players 缩放：`max_pve_output = min(world_regen × 30%, active_players × 50)`，防止「刷怪经济」在低玩家数世界成为主导策略

---

### Low

#### L1 — 存储税 tier 在 4 个文档中重复定义

- **文件**: gameplay.md, economy-balance-sheet.md, resource-ledger.md, api-registry.md
- **问题描述**: 存储税 tiers `[(30,0),(60,1),(85,5),(100,20)]` 出现在至少 4 个文档中。虽然 Resource Ledger 被声明为单一权威，但重复定义增加维护风险——修改时可能遗漏某处。
- **修复建议**: 在非权威文档中将硬编码数组替换为 `见 Resource Ledger §2.2` 引用

#### L2 — Economy Balance Sheet 缺 Tutorial/Vanilla 模式分析

- **文件**: `design/economy-balance-sheet.md`
- **问题描述**: §3 提供了三模式参数对比表，但 §2 收支分析仅覆盖 Standard 模式。Tutorial (`base_upkeep=10, room_soft_cap=20`) 和 Vanilla/Novice (`base_upkeep=30, room_soft_cap=15`) 的 break-even 行为不同，至少应提供各模式 1 房间和 5 房间的对比。
- **修复建议**: 为 Tutorial 和 Novice 模式补充 1/5/10 房间快速对比表

#### L3 — Drone age_modifier 负值极端场景未讨论

- **文件**: `design/gameplay.md` 行 888–898
- **位置**: ATTACK `age_modifier = -80`, RangedAttack `-50`, Heal `-30`, Claim `-50`
- **问题描述**: 高 ATTACK 部件 drone 可能导致 lifespan 极短。如 18×ATTACK + 1×MOVE = `max(100, 1500 - 80×18) = 100 tick`。此「玻璃大炮」设计可能为有意为之（高风险高回报），但文档未讨论极端 build 的边界和意图。
- **修复建议**: 在 §Drone 生命周期中加入关于极端 age_modifier 场景的简短设计注记

---

## 3. 亮点

1. **Resource Ledger 单入口架构**: §1 Transfer Gateway 将 Local/Global/Allied/PvE/Build/Spawn 全部统一经一个 API 结算——消除资源逃逸路径，每笔变动可审计、可归因。这是博弈论视角下反作弊的关键设计。

2. **运输中拦截 (Intercept) 机制**: Snapshot Contract §3.2a 的 Allied Transfer 拦截窗口 + 窃取/销毁双模式 + escort 防御 + RNG-based 成功率——创造了一个**非平凡的子博弈**：发送方需计算是否值得派 escort，攻击方需权衡窃取 vs 销毁，接收方需决定是否暴露收货位置。公式 `60% + part_bonus - escort_penalty` 形成三方不完全信息博弈。

3. **存储税 tiered 公式**: Resource Ledger §2.2 的边界税率设计（免税 → 1bp → 5bp → 20bp）——不是简单线性税，而是离散阶梯创造**临界点策略空间**：玩家需决定是停在 29% 容量还是冲过 30% 阈值。Tier 间的跳跃创造了离散决策点，增加策略深度。

4. **渐进式 PvP 过渡 (First-Attack Shield phases)**: gameplay.md §soft_launch 的三阶段 PvP 过渡（Phase 1 全盾 50 tick → Phase 2 半盾 + 50% 伤害 → Phase 3 全 PvP）——避免了博弈论中的「悬崖效应」（保护结束瞬间被清场），用渐进机制转化为平滑的学习曲线。

5. **Controller + Depot 双层 age 维修**: 免费 Controller repair（有 RCL/距离限制）+ 付费 Depot repair（前线消耗战）——创造物流-战术 tradeoff：前线 Depot 需 CARRY drone 运输资源维持，形成可被攻击的供应链。这正是 RTS 博弈论的经典补给线机制。

6. **New Player Gate**: `new_player_transfer_lock_ticks` + `same_origin_account_group_quota`——从博弈论角度直接消解了刷号/小号的 Nash 均衡优势（多账号 farming 后转移资源给主号）。

7. **Drone 间消息机制的不可信协议设计**: §2.9 明确声明 "消息协议不强制诚实"——将 P2P 交换转化为博弈论问题，玩家须自行设计可信协议或依赖声誉。这是正确的设计选择——不试图在引擎层解决承诺问题（commitment problem），留给 meta-game。

8. **Snapshot truncation 确定性与竞技降级标记**: §1 的确定性截断顺序 + `tick_integrity = "degraded"` 标记——防止大帝国利用 snapshot overflow 获取信息优势，同时不阻塞引擎运行。

---

## 4. CrossCheck

以下问题超出 Design & Economy 方向的专业范围，标注目标方向供交叉验证：

- **CX-1**: Economy Balance Sheet 50-room 的 115 Harvesters + drone upkeep 1000/tick 是否与 Room drone cap (500 total, per-player 50) 兼容？→ 建议 **Gameplay 方向** 检查 room-level cap 与大帝国 drone 分布的冲突 @ `specs/core/09-snapshot-contract.md` §5.1 和 `design/gameplay.md` drone cap 参数

- **CX-2**: Controller repair 硬上限公式 `max(0, age + 1 - min(0.5, controller_count * 0.5))` 中 `controller_count * 0.5` 永远 ≥0.5（当 count ≥ 1），使多 Controller 无收益——这是否为设计意图？→ 建议 **Gameplay 方向** 验证 Controller 维修的预期收益曲线

- **CX-3**: `transfer_from_global_time = 5` (gameplay.md) vs `global_withdraw_delay = 100` (economy-balance-sheet.md) 的冲突需跨文档统一——→ 建议 **Engine/Architecture 方向** 以 Resource Ledger 为准进行全局一致性扫描，检查 `design/interface.md` 中是否存在第三个值

- **CX-4**: Overload 攻击以 PlayerId 为目标但需 `is_visible_to` 检查——player-level visibility 语义未经定义 → 建议 **Security/Visibility 方向** 检查 visibility contract 是否覆盖 player-level 查询 @ `specs/core/09-snapshot-contract.md` 和 `design/engine.md`

- **CX-5**: 50,000 全局 entity hard cap 是否早于经济收敛点触发？若 hard cap 先于 anti-snowball 软上限触发，新玩家加入即被 `WorldEntityCapReached` 拒绝——→ 建议 **Architecture 方向** 验证 `design/engine.md` 和 `specs/core/09-snapshot-contract.md` 的容量模型与 economy-balance-sheet 收敛假设的一致性

- **CX-6**: `special_param: float` 类型违反定点数合同（gameplay.md §2.8）→ 建议 **Security/Determinism 方向** 检查所有 IDL/TOML schema 中是否还有其他 float 类型

- **CX-7**: Economy Balance Sheet 存储利用率假设（40%/55%/70%/90%）是否与 Resource Ledger 的实际存储税触发点一致？→ 建议 **Architecture 方向** 验证 Balance Sheet 的数值模拟假设与 Resource Ledger 公式的数学一致性

- **CX-8**: 50 房间场景 `global_withdraw_delay = 100` 是否意味着前线 Depot 从全局仓库提取资源需等待 100 tick？→ 建议 **Gameplay 方向** 验证长延迟下 Depot 维修场景的实际可用性（Depot capacity 50,000，维修消耗 10/tick，100 tick 窗口内可能耗尽）