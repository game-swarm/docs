# R30 Design & Economy 独立评审 — rev-dsv4-design-economy

> 评审视角：博弈论均衡分析、策略深度度量、资源流建模。分析 Nash 均衡、Pareto 最优、演化稳定策略。验证 anti-snowball 证明的数学完备性。评估信息不对称对策略空间的影响。

---

## 1. Verdict

**REQUEST_MAJOR_CHANGES**

经济系统设计方向正确——Resource Ledger 单入口、anti-snowball 超线性维护费、三层物流模式、信息不对称（本地存储隐匿性）等均展现扎实的设计思维。但存在三处 Critical 级别问题必须修复后方可进入下一阶段：(1) 收支平衡表全部场景净负且无 break-even 验证路径；(2) Resource Ledger 与 gameplay.md 间 `global_transfer_delay` 数值冲突（100 vs 10/5）；(3) 反雪球硬上限（50 房间净损 −12,625/tick）缺乏收敛到均衡点的数学证明。

---

## 2. 发现的问题

### Critical

#### C1 — 收支平衡表全部场景净负，无 break-even 证明路径

- **文件**: `design/economy-balance-sheet.md` §2.1–2.4；`specs/core/08-resource-ledger.md` §2.3 Growth Path
- **描述**: 
  - Balance Sheet 四个场景（1/5/20/50 房间）全部呈现净亏损：−30, −250, −1,940, −12,625/tick。
  - 没有任何一个场景展示玩家能达到净收支平衡或净盈余。
  - Resource Ledger §2.3 Growth Path 声称 RCL 升级 + 免维护期后可「自维持」和「轻微盈余」，但未给出对应数值证明。
  - 这意味着：文档声称系统是可持续的，但数值模型证明所有玩家均处于永恒赤字。这是**自相矛盾**的。
- **影响**: 
  - 若 anti-snowball 过强以至于任何规模都无法 break-even，则新手在 free_upkeep_ticks 到期后必然进入 death spiral，World 模式不可玩。
  - 经济「设计目标」与「数值现实」之间存在信任鸿沟——外部读者（服主、模组作者、社区）将无法判断系统是否被正确校准。
- **修复建议**:
  - **方案 A（推荐）**: 在 Balance Sheet 中增加至少一个 break-even 场景（如 RCL3 单房间 + 3 Harvester + PvE），用数值证明「高效玩家可自维持」。这是 Resource Ledger §2.3 声称但未证明的。
  - **方案 B**: 明确指出「Vanilla 经济为净赤字设计——所有玩家依赖 starting_resources + PvE faucet 维持生存」，以此作为设计哲学声明。但需确认 Tutorial/Novice 等低 upkeep 模式是否可达 break-even。
  - 无论 A 或 B，Balance Sheet 与 Growth Path 必须对齐——不能让一个文档说「自维持」而另一个文档全部为负。

#### C2 — `global_transfer_delay` 跨文档数值冲突

- **文件**: 
  - `specs/core/08-resource-ledger.md` §2.1: `global_transfer_delay = 100 tick`（仅标注「全局提取延迟」）
  - `design/gameplay.md` §2.2（资源存储模型）: `transfer_to_global_time = 10`, `transfer_from_global_time = 5`
  - `design/gameplay.md` §2.2（反制机制）: 再次使用 10/5
  - `design/gameplay.md` §2.2（安全下限）: 再次使用 10/5
- **描述**: Resource Ledger 作为「所有费率/公式/参数的唯一定义源」声明 `global_transfer_delay = 100`，但 gameplay.md 在多处使用 10/5。两者相差 10–20 倍。若 100 为权威值，则 Balance Sheet 所有涉及转换延迟的决策将完全不同（10 tick 近乎即时 vs 100 tick 需长期规划）。若 10/5 为实际值，则 Resource Ledger 的记录有误。
- **影响**: 核心经济参数不确定性——物流模式 B 的「策略深度」取决于延迟数值。100 tick 大幅削弱全局存储的战术灵活性，10 tick 则接近即时。不同实现者将基于不同文档做出相互矛盾的经济平衡。
- **修复建议**: 确定权威值并以 Resource Ledger §2.1 为单一事实源。gameplay.md 中所有延迟声明改为引用 `specs/core/08-resource-ledger.md §2.1`。同时补充 `global_transfer_delay` 是否区分存入/提取（当前仅标注「提取延迟」，存入延迟未定义）。

#### C3 — 50 房间硬上限缺乏收敛到均衡点的数学证明

- **文件**: `design/economy-balance-sheet.md` §4；`specs/core/08-resource-ledger.md` §Empire Upkeep
- **描述**: 
  - Anti-snowball 声明「50 房间附近维护费吞噬全部收入，形成 soft cap」。但 Balance Sheet 显示 50 房间净亏损 −12,625/tick——这远不止「吞噬全部收入」，而是深度负值。
  - 若 50 房间的维护费是收入的 4.2 倍（16,600 / 3,975），则「自然上限」应在远小于 50 房间时达到（约在 12–15 房间时维护费已超过收入）。
  - 缺少一个关键证明：在哪个房间数 N 处 `income(N) = upkeep(N)`？即均衡点在哪里？没有这个数值，anti-snowball 的「自然收敛」主张缺乏可验证性。
- **影响**: 反雪球合同（Anti-Snowball Contract）是 World 模式核心设计支柱。若数学证明不完备，反对者（竞技公平派玩家）将质疑系统只是「让所有人变穷」而非「收益递减」。服主无法判断参数是否需要调整。
- **修复建议**: 
  - 在 Balance Sheet 或 Resource Ledger 中增加一个**均衡点计算**: 给定 Standard 参数，求解 `income(N) ≈ upkeep(N)` 的 N 值。使用收入假设（Harvester 效率、Controller 等级、PvE 占比）作为输入。
  - 可选：提供不同效率假设下的均衡点范围（低效玩家 → 小帝国均衡；高效玩家 → 大帝国均衡），展示系统如何自然分层。

---

### High

#### H1 — 存储税 tier 在 gameplay.md 中独立声明，违反单事实源原则

- **文件**: 
  - `specs/core/08-resource-ledger.md` §2.1（权威源，声明自身为唯一权威）
  - `design/gameplay.md` §2.2「累进存储税」表格（独立声明 `[(30,0),(60,1),(85,5),(100,20)]`）
- **描述**: Resource Ledger 明确声明自身为「所有费率、公式、参数的唯一定义源」并禁止其他文档独立定义公式。但 gameplay.md §2.2 的累进存储税表格独立声明了 tier 结构，未引用 Resource Ledger。虽然数值一致，但违反了单事实源合同——未来若调整税率，有两个文档需要同步修改，引入分叉风险。
- **影响**: 中风险——当前数值一致故不产生即时错误，但违反设计合同。若未来某次修改仅更新一处，将导致跨文档不一致。
- **修复建议**: gameplay.md §2.2「累进存储税」表格改为引用 Resource Ledger §2.1 的 `storage_tax_tiers`，删除独立声明。仅保留概念说明，不重复数值。

#### H2 — Controller aging 公式中 `controller_count` 语义模糊

- **文件**: `design/gameplay.md` §2.2「Drone 生命周期」
- **描述**: 
  - 修理硬上限公式: `max(0, age + 1 - min(0.5, controller_count × 0.5))`
  - `controller_count` 指什么？是玩家拥有的 Controller 总数，还是同房间内的 Controller 数？若为后者则值为 0 或 1（每房间最多 1 个 Controller），`min(0.5, 1×0.5) = 0.5` 永远不变——`controller_count` 参数失去意义。
  - 若为前者（玩家总 Controller 数），则公式退化为 `controller_count ≥ 1 → 0.5` 的二元开关——同样不依赖数量。
  - 文档说「无论拥有多少个 Controller，每 tick 总 age 回退不超过自然增长的 50%」——这意味着上限是固定的 50%，与 controller_count 无关。那公式中的 `controller_count × 0.5` 就是误导性的。
- **影响**: 实现者可能误解公式意图——把 `controller_count` 当作动态参数计算，而实际永远返回 0.5。
- **修复建议**: 简化公式为 `max(0, age + 1 - 0.5) = age + 0.5`，明确说明「与 Controller 数量无关，硬上限固定为 50%」。或澄清该上限是 per-controller 的（即每个 Controller 最多减少 0.5 的 age）。

#### H3 — PvE budget 「世界再生总量 × 30%」未定义

- **文件**: `design/modes.md` §9.0「NPC 掉落经济」；`specs/core/08-resource-ledger.md` §3
- **描述**: 
  - PvE 产出上限公式引用「世界再生总量 × 30%」作为 global cap。
  - 「世界再生总量」未在任何文档中形式化定义。是所有 source 的 `regeneration` 字段之和？是否包含 player-owned sources？刷新周期的 tick 粒度如何？
  - Resource Ledger §3 的 4 维账本表中「Global | ≤ 世界再生总量 × 30% | per tick」同样未定义分母。
- **影响**: PvE 经济约束是防止「刷怪经济」压倒 PvP 的关键机制。若分母未定义，实现者无法正确计算 cap，测试者无法验证约束是否生效。
- **修复建议**: 在 Resource Ledger §3 中增加「世界再生总量」的明确定义：`Σ over all rooms: Σ over all source entities in room: source_def.regeneration`，并在 PvE budget 表中引用该定义。

---

### Medium

#### M1 — Balance Sheet 存储税计算不透明

- **文件**: `design/economy-balance-sheet.md` §2.2–2.4
- **描述**: Balance Sheet 的存储税数值（15, 120, 600）直接给出，但未披露计算所基于的存储利用率假设。读者无法独立验证 `60-85% @ 5 bp → 120/tick` 的计算过程。
- **影响**: 低——数值本身看起来合理，但透明性不足降低了文档作为「数值验证」的可信度。
- **修复建议**: 每个场景明确标注假设的存储利用率（如「假设存储利用率 75%，容量 1,000,000，存储量 750,000 → 存储税 = 105/tick」），使计算过程可复现。

#### M2 — `Scramble` custom action 出现在 gameplay.md 但未在 API Registry 注册

- **文件**: 
  - `design/gameplay.md` §2.2 自定义 CommandAction 示例（行 1011-1017）：`[[custom_actions]] name = "Scramble"`
  - `specs/reference/api-registry.md` §1: CommandAction 仅列 21 种，不含 Scramble
- **描述**: gameplay.md 的 `[[custom_actions]]` 示例中包含 `Scramble`（引用 `special_effect = "scramble_commands"`），但 API Registry 的 CommandAction 表中不包含此变体。`scramble_commands` handler 在 `[[special_effects]]` 中有定义（行 1134-1138），表明引擎支持此效果，但未在 Registry 中注册为正式 CommandAction。
- **影响**: 如果 Scramble 是官方 vanilla 内容，则 Registry 不完整；如果仅是示例，则应在示例中明确标注「仅作示例，非 vanilla 内容」以避免混淆。
- **修复建议**: 在 gameplay.md 的 `[[custom_actions]]` 示例块开头加注释 `# 以下为说明性示例——仅 Hack/Drain/Overload/Debilitate/Disrupt/Fortify/Leech/Fabricate 为 vanilla 预注册内容`，或同时在 API Registry 注册 Scramble。

#### M3 — Allied Transfer 拦截公式 attacker/defender 不对称性需博弈论分析

- **文件**: `specs/core/09-snapshot-contract.md` §3.2a
- **描述**: 
  - Attacker bonus: `min(extra_parts × 5%, 25%)` — 最多 5 个额外部件达上限
  - Defender penalty: `escort_penalty = 30%` (固定)
  - 结果：无 escort 时 base 60% → 攻击方只要有 1 个额外部件 (65%) 就优于有 escort 的场景 (30%)
  - 但 escort 的边际效益（−30%）远大于单个额外攻击部件的边际效益（+5%），导致 **defender 的 escort 策略严格占优于 attacker 的额外部件策略**，直到 attacker 投入 ≥5 个额外部件。
  - 这可能是有意设计（鼓励护送），但缺乏博弈论分析来证明此不对称性不会导致 Nash 均衡坍缩为「所有 transfer 都有 escort → 所有 attacker 都不拦截」或反过来。
- **影响**: 如果 escort 过于强大，Allied Transfer 拦截机制沦为「纸面功能」——无人尝试拦截因为成功率太低。降低策略深度。
- **修复建议**: 在 snapshot-contract.md §3.2a 中增加一个简短的博弈矩阵或场景分析，证明 escort/不 escort、拦截/不拦截的混合策略均衡存在且非退化。

#### M4 — 新玩家 RCL1 balance sheet 强制「升级或死亡」

- **文件**: `design/economy-balance-sheet.md` §2.1
- **描述**: 
  - RCL1 单房间净亏损 −30/tick，免维护期过后玩家必须升级到 RCL2+ 才能缩小缺口。
  - 这意味着 RCL1 是不可维持的状态——设计者意图如此（鼓励垂直发展），但文档未明确声明「RCL1 是过渡状态，不可长期驻留」。
  - 若玩家因 PvP 攻击失去 Controller 等级（降级），可能从 RCL2 跌回 RCL1 → 立即陷入 maintenance deficit → death spiral。
- **影响**: 中等——RCL 降级惩罚可能过重，导致「失去一场战斗 = 失去整个帝国」的悬崖效应，与 anti-snowball 的「渐进收敛」目标矛盾。
- **修复建议**: 在 Balance Sheet 中明确标注「RCL1 为过渡阶段，依赖初始资源维持」，并在 anti-snowball 合同中增加对 RCL 降级的经济缓冲（如降级后 N tick 维护费减半）。

---

### Low

#### L1 — `same_origin_account_group_quota` 依赖 IP 分组的脆弱性

- **文件**: `design/gameplay.md` §2.2「新玩家资源门」
- **描述**: `same_origin_account_group_quota = 5` 使用「同一 IP/device fingerprint」。IP 分组在 NAT/CGNAT/移动网络环境下高度不准确——同一 IP 可能对应数百合法用户。Device fingerprint 更可靠但未指定实现方式。
- **影响**: 低——反滥用机制，非核心经济设计。若 IP 分组过于激进，可能误伤合法用户（大学宿舍、企业 NAT）。但可通过服主配置规避。
- **修复建议**: 将 `same_origin_account_group_quota` 默认值设为更大的值（如 20）或改为 `device_fingerprint_only` 模式，标注「IP 分组仅在服主明确启用时使用」。

#### L2 — drone MIN_LIFESPAN 未进入权威参数表

- **文件**: `design/gameplay.md` §2.2「Drone 生命周期」
- **描述**: `MIN_LIFESPAN` 默认 100 tick 在 gameplay.md 中以行内方式提及（「world.toml 可配置」），但未进入 Resource Ledger 或 API Registry 的权威参数表。
- **影响**: 低——数值小、影响有限。但作为 world.toml 可配置项，应有权威定义位置。
- **修复建议**: 将 `MIN_LIFESPAN` 加入 Resource Ledger §2 统一参数表或 API Registry §5.1 容量限制表。

---

## 3. 亮点

1. **Resource Ledger 单入口架构（08-resource-ledger.md）**: 所有 11 种资源操作类型通过统一接口结算，配合确定性执行顺序和 TickTrace 归因——这是教科书级的经济系统设计。`Σ inflows - Σ outflows = Δ storage` 的可审计性为反作弊提供了数学基础。

2. **Anti-snowball 三层机制**: 超线性维护费 (O(n²)) + Controller age repair 硬上限 (50%) + 累进存储税 (0/1/5/20 bp)——三者各自独立运作且形成交叉约束。大帝国不能靠「堆 Controller 刷 age」也不能靠「囤全局存储避税」，每一条逃逸路径都被封堵。设计思维严谨。

3. **三层物流模式 (A/B/C)**: 从「无物流」到「轻物流」到「硬核物流」的可配置梯度极其优雅。不是简单开关，而是通过 `global_storage_enabled` + `transfer_cost` + `transfer_time` 三个独立参数的组合产生连续策略空间。全局↔本地转换的运输时间 + 拦截窗口（最后 50 tick）使物流成为博弈论问题而非算术计算。

4. **信息不对称的战略深度**: 全局存储部分公开 vs 本地存储完全私有的设计创造了有意义的 hidden information 博弈。敌方不知道你的建筑中存了多少资源——这鼓励玩家囤积本地存储而非全局存储，与 storage tax 形成 push-pull 张力。OverloadPressure 的 visibility-gated contribution 列表（不可见攻击者不出现在列表中）进一步强化了信息不对称的策略价值。

5. **PvP 渐进过渡（First-Attack Shield → Soft PvP → Full PvP）**: 解决了 MMO PvP 的经典「保护期悬崖」问题。不是二态切换而是三阶段 500 tick 的平滑过渡，每阶段有独立的 damage multiplier 和 shield 规则。Phase 1 的 per-attacker shield（而非全局无敌）尤其精妙——玩家仍然脆弱但不会被同一攻击者连续压制。

6. **Drone 消息系统作为博弈论元素**: 「引擎不校验 payload 语义，仅保证消息已投递」+「不可信协议」——这为玩家间 P2P 经济协议创造了涌现空间。不出现在 CommandAction 中但通过 message 管道存在，干净地分离了机制层和策略层。

7. **PvE 预算 4 维账本**: Global × Zone × Player × Event 的复合预算约束防止任一维度的 faucet 失控。不是简单全局上限，而是分层约束——高活跃玩家不会垄断 PvE 产出，单个区域不会被刷爆。

8. **模组经济隔离**: `mods.lock` 的 checksum 强制 + 「checksum 不匹配 → 拒绝启动」的硬约束，确保经济模组（empire-upkeep、storage-tax）版本不可篡改。经济规则的完整性是玩家信任的基础，此设计正确地将完整性置于便利性之上。

---

## 4. CrossCheck

以下问题超出 Design & Economy 方向范围，需跨方向检查：

- **CX-1**: [C1 相关] Balance Sheet 全部净负 → 建议 **Systems Reviewer** 检查引擎侧 `UpkeepDeduction` 的实际计算公式是否与 Resource Ledger 一致，因为 perpetual deficit 可能源于公式参数配置错误而非设计意图。

- **CX-2**: [C2 相关] `global_transfer_delay` 100 vs 10/5 冲突 → 建议 **Integration/Consistency Reviewer** 系统审计所有 10 个文档中出现的经济数值，标记所有与 Resource Ledger §2.1 不一致的独立声明。

- **CX-3**: [H1 相关] Storage tax tier 多处独立声明 → 建议 **Integration/Consistency Reviewer** 验证 gameplay.md、economy-balance-sheet.md、api-registry.md 中所有经济参数的引用链路是否最终指向 Resource Ledger。

- **CX-4**: [H2 相关] Controller aging 公式 `controller_count` 歧义 → 建议 **Systems Reviewer** 核验 engine 代码中 Controller 修理逻辑的预期行为，确认公式的实际语义。

- **CX-5**: [M2 相关] Scramble 未注册 → 建议 **API/Registry Reviewer** 确认 gameplay.md 中 `[[custom_actions]]` 示例块内的 Scramble 是否为 vanilla 内容，如果是则需补充 Registry 条目。

- **CX-6**: [M3 相关] Allied Transfer 拦截博弈均衡 → 建议 **Combat/Gameplay Reviewer** 评估 escort 30% penalty 是否导致拦截机制在 Nash 均衡中不可用（纯策略 escort 占优）。

- **CX-7**: [H3 相关] PvE budget 分母未定义 → 建议 **Gameplay Reviewer** 确认 `modes.md` §9.0 的「世界再生总量」应以 Resource Ledger 的何种定义为准，并统一表述。

- **CX-8**: [M4 相关] RCL 降级 death spiral → 建议 **Gameplay Reviewer** 评估 RCL 降级（通过 PvP 攻击或 upkeep deficit）是否应该触发一段经济缓冲期，以避免悬崖效应。

---

*评审完成时间: 2026-06-21*
*模型: DeepSeek V4 Pro*
*方向: Design & Economy*