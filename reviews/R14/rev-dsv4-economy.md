# R14 经济评审报告 — rev-dsv4-economy (DSV4)

> **评审视角**: 反雪球机制分析、博弈论均衡验证、资源流数学建模
> **评审阶段**: Phase 1 Clean-Slate（设计阶段评审，不考虑分阶段实现）
> **阅读文档**: design/README.md, design/gameplay.md, design/modes.md, specs/gameplay/06-feedback-loop.md, specs/gameplay/08-api-idl.md

---

## 1. Verdict: CONDITIONAL_APPROVE

经济模型的结构设计是合理的——Faucet/Sink/Transfer/Lockup/Unlock 分类体系清晰，反雪球机制（empire-upkeep + 累进存储税 + Controller age 硬上限）形成多层防御。但在**默认参数化**和**特定边界条件**下存在收敛性缺口，需要在实现前解决以下 D1-D3 问题。

---

## 2. 发现的问题

### Critical

#### D1: Empire-upkeep 默认参数无法兑现 O(n²) 承诺 [Critical]

**位置**: gameplay.md §8.7 (empire-upkeep mod.toml + tick_end.rhai), §反雪球合同

**公式**（来自 `tick_end.rhai` 代码）:
```
upkeep = drones × drone_cost + rooms × (room_base + rooms × room_superlinear / FIXED_SCALE)
默认值: drone_cost=2, room_base=10, room_superlinear=1 (fixed<u32,4> → 0.0001)
```

**代入默认值计算**:
| 规模 | 公式计算值 | 文档声称值 | 差异 |
|---|---|---|---|
| 1房 20drone | 2×20 + 1×(10 + 1×0.0001) = 50 | ~40 | +25% |
| 5房 100drone | 2×100 + 5×(10 + 5×0.0001) = 250 | ~275 | -9% |
| 20房 500drone | 2×500 + 20×(10 + 20×0.0001) = 1200 | ~2100 | **-43%** |
| 50房 500drone | 2×500 + 50×(10 + 50×0.0001) = 1500 | ~3150 | **-52%** |

**根因**: 二次项系数 `room_superlinear = 1 (0.0001)` 过于微小。以 50 房间为例，`n² × 0.0001 = 0.25`，对总维护费几乎无贡献。实际上 `upkeep ≈ 2m + 10n`，即 O(n) 在 rooms——**反雪球的核心承诺（超线性增长）在默认参数下不成立**。

**影响**: 大帝国维护费增速与房间数基本线性——每多占一个房间，边际成本约为 `10 + drone_cost × (drone_per_room)` Energy/tick，不存在自然收敛点。玩家可以无限线性扩张。

**建议**: 
- 方案A: 将默认 `room_superlinear` 提升至约 3000-5000（即 0.3-0.5），使文档示例值可复现
- 方案B: 改用更激进的公式，如 `rooms^1.5 × room_base`，保证亚线性但确切的收敛
- 最低要求: 文档示例值与默认参数一致，或显式声明示例使用的非默认配置

#### D2: Recycle 50% 退还依赖 empire-upkeep 维持均衡，裸经济存在套利 [Critical]

**位置**: gameplay.md §Drone 身体规划 (body 不可逆 / Recycle), 08-api-idl.md §Recycle (refund: `registry.body_cost(body) * 0.5`)

**套利路径**:
1. Spawn 一个最廉价的 harvester drone（如 1×WORK + 1×MOVE + 1×CARRY = 200 Energy）
2. 在 lifespan (1500 tick) 内采集资源: 1500 tick × 1 Energy/tick = 1500 Energy 毛收入
3. 寿命耗尽前 Recycle: 退还 100 Energy
4. **净收益**: 1500 + 100 - 200 = **+1400 Energy**

**如果 empire-upkeep 启用**（默认 drone_cost=2）:
- 维护费: 1500 × 2 = 3000（超过采集收入）
- 净收益: 1500 + 100 - 200 - 3000 = **-1600 Energy**（亏损）

**问题**: Recycle 套利的唯一防线是 empire-upkeep。如果服主在 `world.toml` 中禁用 empire-upkeep（或将其 drone_cost 设为 0），Recycle 立即变成纯套利引擎。设计文档中 Recycle 独立于 empire-upkeep 定义，未声明此依赖关系。

**建议**:
- 在 Recycle 退还逻辑中内置最小 economic sink（如退还时额外消耗 `spawn_cost × 0.1` 作为"拆解费"），使套利在无 empire-upkeep 时仍然为负
- 或在 `refund_policy` 中显式声明 `recycle = registry.body_cost(body) × (0.5 - min_maintenance_ratio)`，将维护费因子内嵌

### High

#### D3: 累进存储税顶层税率可能不足以形成有效收敛 [High]

**位置**: gameplay.md §全局存储反制机制 > 累进存储税

**税制**:
| 存储利用率 | 税率 (bp/tick) |
|---|---|
| 0-30% | 0 |
| 30-60% | 1 (0.01%) |
| 60-85% | 5 (0.05%) |
| 85-100% | 20 (0.2%) |

**每日等效税率** (3s/tick = 28,800 tick/天):
- 顶层 20bp: `(1 - 0.00002)^28800 ≈ 0.562` → **~44% 日衰减**

**均衡点**: 玩家产出 rate `P` Energy/天 → 均衡存储 `S = P / 0.44`
- 日产出 3000 Energy → S ≈ 6,818（远低于 1,000,000 容量上限）
- 日产出 100,000 Energy → S ≈ 227,273（约占容量 23%）

**分析**: 对于顶级玩家（日产出可能远超 100,000），均衡存储量仍远在容量上限之下，不会触发"天花板效应"。税制更多是对"闲置囤积"的惩罚，而非对"高产出大国"的硬限制——这与文档声称的「防止无限囤积垄断」目标部分一致，但「自然天花板」用词可能误导。

**建议**: 若需要真正的硬天花板，考虑顶层税率设为 `min(current_tier_rate, production_rate_at_cap / capacity)` 的动态税率，或添加超容量惩罚（>100% 容量时 exponential tax）。

#### D4: 全局↔本地转换损耗不对称（1% vs 5%）+ 存储税 = 三重惩罚 [High]

**位置**: gameplay.md §资源存储模型 > 三种物流模式, 08-api-idl.md §global_storage_commands

**当前设计**:
- 本地→全局: 1% 损耗 + 10 tick 锁定
- 全局→本地: 5% 损耗 + 5 tick 锁定
- 全局存储: 阶梯税制（最高 20bp/tick）

**影响**: 一个完整的资源往返（本地→全局→本地）有效损耗为:
```
总损耗 ≈ 1% + N_tick × tax_bp + 5% ≈ 6% + N_tick × tax_bp
```
如果资源在全局停留 1000 tick（约 50 分钟），在 85-100% 税档下额外增加 `1000 × 0.2% = 200%` 的税收损耗——**远超转换损耗本身**。

**博弈论分析**: 理性玩家的最优策略是**最小化全局存储滞留时间**——只在需要支付跨房间部署费时将资源转入全局，用完立即转出。这使全局存储沦为"瞬时支付通道"而非"战略储备"，与设计意图（"抽象经济力量"）矛盾。

**建议**:
- 方案A: 对称化转换损耗（如双向 2%），降低不对称性
- 方案B: 全局存储税仅对"超过 N tick 未使用的闲置余额"征收，而非对所有余额
- 方案C: 在文档中明确全局存储的定位是"支付通道"而非"储备"，调整相关描述

### Medium

#### D5: Controller age 修复硬上限（50% 自然增长）在多 Controller 场景下可能被稀释 [Medium]

**位置**: gameplay.md §Drone 生命周期 > Age 恢复

**公式**: `max(0, age + 1 - min(0.5, controller_count × 0.5))`

**分析**: 
- 1 个 Controller: 每 tick age 回退 ≤ 0.5，净增长 ≥ 0.5/tick
- 4 个 Controller: 每 tick age 回退 ≤ min(0.5, 4×0.5) = 0.5（**硬上限触发**）
- 即 controller_count ≥ 1 后不再增加回退能力

**结论**: 硬上限公式 `min(0.5, controller_count × 0.5)` 在 `controller_count ≥ 1` 时即为 0.5，**多 Controller 不增加回退能力**。此设计合理——防止堆叠 Controller 实现永久 drone。**D5 降级评估**: 该公式已正确处理多 Controller 场景，撤回此前担忧。文档描述「无论拥有多少个 Controller，每 tick 总 age 回退不超过自然增长的 50%」准确。

但存在一个边界问题: `controller_count = 0` 时（即殖民地全灭但 drone 仍存活），age 只能增加、无法回退——此时 drone 进入不可逆死亡倒计时。此行为是 intentional design（§respawn_policy: `NewRoom | SameRoom | Spectate | Ban`），但 drone 在没有 Controller 时的 age 行为未在文档中显式说明。

**建议**: 在 §Drone 生命周期中补充「无 Controller 时 drone 不可修复 age」的显式说明。

#### D6: Same-origin 账号组配额 = 5 可被低成本绕过 [Medium]

**位置**: gameplay.md §新玩家资源门 > 同源账号组配额

**攻击成本分析**:
- 配额: 5 账号 / IP + device fingerprint
- 绕过方式: 商用代理 IP（~$1/100 IPs） + 浏览器指纹随机化
- PoW 防御: `difficulty_bits = 24` → P95 WASM 注册耗时 ~1.5s，批量注册 ~$0.10/1000 账号
- **总绕过成本**: 极低。恶意玩家可以维持远超 5 的账号数

**建议**: 
- 将 `same_origin_account_group_quota` 与 PoW 难度联动: 超配额账号需要 `difficulty_bits = 28-32`
- 或引入账号年龄门控: 配额内账号注册满 N tick 后才释放新配额

### Low

#### D7: empire-upkeep 文档示例值与默认参数不一致 [Low]

**位置**: gameplay.md §帝国维护费示例效果 (line 1883-1893) vs §mod.toml 默认参数 (line 1498-1502)

示例中 50房500drone 维护费 ~3150/tick，但代入默认参数计算仅为 ~1500/tick。两处数据矛盾——示例可能使用更高 `room_superlinear`（约 3300 而非默认 1）。

**建议**: 统一示例与默认参数，或显式标注示例使用的非默认配置。

---

## 3. 亮点

1. **Faucet/Sink/Transfer/Lockup/Unlock 五分类体系** (gameplay.md §Vanilla 经济分类账): 对经济流提供了精确的数学化语言——每个经济操作都可归入其中一类，使总量守恒分析成为可能。这是该设计文档中经济部分最强的架构决策。

2. **双层存储模型（全局/本地）**: 全局存储受税、本地存储可被掠夺——不对称的激励结构创造真实的策略深度。本地存储隐匿性与全局存储可见性的对比（§本地存储隐匿性）是一个精妙的博弈论设计。

3. **反雪球合同的自我限定**: 文档明确声明「World 模式不追求竞技公平——先入者、大帝国拥有资源优势是接受的设计」，将反雪球定位为「生态可持续性」而非「个体公平」。这种诚实的范围界定避免了常见的设计过度承诺。

4. **Resource-agnostic 引擎核心**: `HashMap<ResourceName, Amount>` 的设计使引擎不硬编码任何资源类型——所有经济规则在 world.toml 层定义（gameplay.md §8.4）。这为模组生态的多样性提供了坚实的基础。

5. **Overload 作为经济攻击向量**: 消耗目标 fuel budget 而非直接造成 HP 伤害，是具有原创性的"软杀伤"经济武器——不影响资产但影响能力，创造了非零和博弈空间。

6. **新玩家资源门（New Player Resource Gate）**: 500 tick 传输锁 + PvE 掉落绑定 + same-origin 配额组合，构成了防刷号/小号经济的多层防线，且所有参数由服主配置（gameplay.md §新玩家资源门）。

7. **实体膨胀归因的公平性**: 每个玩家的 snapshot 大小与自身 drone 数量成正比，全局 entity cap 50,000 阻止膨胀外化——这是经济设计中对"common-pool resource"问题（公地悲剧）的正确处理。

---

## 4. CrossCheck — 需要跨方向检查

以下问题超出纯经济视角，需要其他评审方向验证:

- **CX1**: empire-upkeep 是否在所有 World 模式实例中强制启用？是否存在服主误操作禁用 empire-upkeep 导致 Recycle 套利（D2）的路径？ → 建议 **Architect** 检查 world.toml 的 `[[mods]]` 加载机制是否对"核心 mod 缺失"有保护

- **CX2**: Controller age 修复公式中 `min(0.5, controller_count × 0.5)` 在 `controller_count = 0` 时 age 回退为 0。此时 drone 进入不可逆死亡——是否与 respawn_policy 的 `SameRoom`/`Spectate` 选项交互正确？ → 建议 **Gameplay** 方向检查此边界状态

- **CX3**: Entity cap 50,000 是否与 empire-upkeep 形成双重天花板？在大规模世界中，entity cap 可能在 empire-upkeep 达到收敛点之前先触发——玩家可能撞上 hard cap 而非 economic cap → 建议 **Architect** 检查 entity cap 的计算口径（是所有实体还是仅 drone）以及两种收敛机制的优先级

- **CX4**: `refund_policy` 中 `contention_lost: 0.5` 和 `self_invalid: 0.0` 的区分是否有实现层面的边界情况？例如 SourceEmpty 属于 contention_lost (0.5 refund)，但玩家代码在明知 Source 已空的情况下依然发送 Harvest 指令——是算 self_invalid 还是 contention_lost？ → 建议 **Security** 方向检查 refund 判定逻辑的确定性

- **CX5**: drone 间消息系统（gameplay.md §8.9）中的 P2P 不可信协议 + 引擎不校验 payload 语义的设计，是否可能被用于经济攻击（如虚假 offer 诱导对手 drone 移动到陷阱位置）？ → 建议 **Security** 方向评估此信任模型

---

## 5. 数学缺口总结

| 缺口 | 公式/参数 | 问题 | 严重度 |
|---|---|---|---|
| empire-upkeep 收敛性 | `2m + 10n + 0.0001n²` | 默认参数下 O(n²) 项可忽略，无收敛点 | Critical |
| Recycle 套利条件 | `harvest_rate × lifespan × (1 - tax) - spawn_cost + refund` | 无 empire-upkeep 时恒正 | Critical |
| 存储税天花板 | `storage_eq = production / daily_tax_rate` | 高产出玩家不触顶 | High |
| 全局↔本地往返损耗 | `6% + tax_over_duration` | 三重惩罚使全局存储不可用 | High |
| Controller age 公式 | `min(0.5, n×0.5)` | n≥1 时恒为 0.5，边界 n=0 行为未文档化 | Medium |
| Same-origin 配额绕过 | PoW difficulty=24 | 绕过成本 < $0.01/账号 | Medium |

---

## 6. Nash Equilibrium 初步分析

从博弈论角度，当前经济设计中的主要均衡问题:

1. **扩张 vs 维护均衡**: 在 empire-upkeep 的 O(n²) 项有效（即 room_superlinear 足够大）的前提下，存在唯一的 Nash 均衡——每个玩家的最优房间数由 `marginal_revenue_per_room = marginal_upkeep_per_room` 决定。当前默认参数下此均衡不存在（边际维护费恒定）。

2. **全局 vs 本地存储博弈**: 由于全局存储税 + 5% 取款损耗 + 本地存储隐匿性，纯策略 Nash 均衡趋近于"所有资源保持本地"。这消除了全局存储的战略价值，使其退化为瞬时支付通道。

3. **Recycle vs 持续使用**: 在 empire-upkeep 启用时，Recycle 仅在 drone 即将达到 lifespan 上限时是占优策略（回收沉没成本）。此均衡合理——鼓励在 drone 生命末期回收而非放任死亡。

4. **PvE 产出 vs PvP 风险**: PvE 产出上限 `≤ 世界再生总量 × 30%`（modes.md §NPC 掉落经济）确保 PvE 不会压倒 PvP 的战略价值——这是一个正确的均衡约束。

---

*评审完成时间: 2026-06-18*
*评审模型: DeepSeek V4 Pro*
*评审员: rev-dsv4-economy (Economy Reviewer)*
