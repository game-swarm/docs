# R23 Game Design Review — DeepSeek V4 Pro

**Reviewer**: rev-dsv4-designer (Game Designer)
**Date**: 2026-06-19
**Phase**: Phase 1 Clean-Slate Independent Review
**Documents Reviewed**: design/README.md, design/gameplay.md, design/modes.md, design/interface.md, specs/reference/api-registry.md, specs/gameplay/06-feedback-loop.md, specs/gameplay/08-api-idl.md, specs/core/09-snapshot-contract.md

---

## Verdict

**CONDITIONAL_APPROVE** — 设计从博弈论层面评估，策略空间丰富，无明显的 dominant strategy；信息不对称设计合理；World 模式 PvE+PvP 激励结构克制但有效。7 项发现（0 Critical, 2 High, 4 Medium, 1 Low），均可通过参数调整或机制微调解。

---

## Strengths

1. **策略空间丰富，无单一最优解**。8 种 body part 的 age_modifier 机制（TOUGH +100 延寿 vs ATTACK -80 折寿）迫使玩家在寿命-战斗力-经济效率之间做真实权衡。6 种伤害类型 × 8 种特殊攻击 × 多抗性层构成非传递性克制关系。

2. **Anti-snowball 多层防线设计出色**。累进存储税（0→1→5→20bp）防止囤积垄断；O(n²) 帝国维护费制造自然收敛；Controller 续期硬上限（50% 自然增长）防止永久 drone；active_aging（+10%）惩罚挂机囤兵。这些机制并非简单粗暴的硬 cap，而是产生边际递减——保持优势但限制绝对碾压。

3. **信息不对称层次分明**。NotVisibleOrNotFound 安全合并防止 oracle inference；本地存储隐匿性给予囤积者战略优势；OverloadPressure 可见性模型（攻击者/被攻击者/三方视角）精确定义信息暴露边界；Safe Hint Ladder 按模式（competitive/practice/training）梯度释放调试信息。

4. **AI/Human 公平性天然内嵌**。MCP 不提供直接游戏动作——AI 必须写 WASM，与人类走完全相同的编译→部署→执行路径。Fuel metering（WASM 指令计数）保证 C/Python/Rust 玩家在相同配额下获得同等算力。这是设计中最优雅的部分。

5. **PvE 与 PvP 平行共生设计**。PvE 不是独立"副本"而是地理属性（距世界中心越远 NPC 越强）；PvE 经济上限（≤30% 世界再生总量）防止刷怪经济压倒 PvP 战略价值。World/Arena 两模式共用引擎、独立规则，分离持久策略与竞技公平。

6. **渐进式 PvP 过渡（First-Attack Shield）**。soft_launch → Phase 1 全盾（50 tick）→ Phase 2 半盾（25 tick + 50% 伤害）→ Full PvP，三段过渡比简单 hard switch 更符合玩家心理曲线，防止保护期结束即被清场的"悬崖体验"。

7. **Deferred Command Model 保持策略纯洁性**。WASM tick() 输出 CommandIntent → 引擎统一校验 + 冲突解决 → 确定性应用。不存在"手速优势"或"API 竞速"——胜负取决于算法质量。

---

## Concerns

### G1 [High] — Disrupt 的反制面过宽，存在策略同质化风险

**发现**：Disrupt（50 tick CD, 100 Energy）可以打断所有持续型攻击——Hack（5 tick 渐进控制）、Drain（资源窃取）、Debilitate（易伤）。这意味着任何一个携带 Attack body part 的 drone 都可以用一个低成本动作取消对手多种高投入策略。Disrupt 的 counter-scope 覆盖了 3/6 的 Tier 1 特殊攻击，使得防御方的最优响应几乎总是 Disrupt。

**博弈论分析**：在 Hack/Disrupt 子博弈中——
- 攻击者投入 1000 Energy + Claim body part + 200 tick CD 执行 Hack
- 防御者投入 100 Energy + Attack body part + 50 tick CD 执行 Disrupt
- Disrupt 的 cost-to-disrupt ratio (100E/50CD) 远低于 Hack 的 cost-to-be-disrupted (1000E/200CD)
- 防御方的 dominant strategy 倾向于始终保留 Disrupt-ready drone

**建议**：
- 方案 A：Disrupt 打断 Hack/Drain 需要 body part match（如 Hack 需要 Claim part 的反制方也需 Claim）
- 方案 B：Disrupt 成功率与 body part 数量差相关（如 Disrupt 方 Attack part 数 vs 目标 Work/Claim part 数），非确保打断
- 方案 C：增加 Disrupt 的 CD 至 100 tick 或资源消耗至 300 Energy，拉近攻防成本比

### G2 [High] — Controller 免费维修 + 硬上限 50% 可能导致"龟缩优势"均衡

**发现**：Controller 提供免费 age 维修（范围随 RCL 1→5 增长），硬上限为每 tick 总 age 回退不超过自然增长的 50%。late-game 高 RCL 玩家在其领地内有巨大的 drone 维护优势——免费、大范围、高容量。结合 Depot 需要消耗资源的约束，已有领地的防守方在 drone 持久性上远优于进攻方。

**博弈论分析**：这会推高攻击成本（攻击方 drone 加速衰老、需自建 Depot 补给线），降低进攻收益，最终稳态可能是各玩家固守已有领地而不扩张——"龟缩均衡"（turtling equilibrium）。这与 GCL（多房间平均等级）鼓励横向扩张的设计目标矛盾。

**建议**：
- 降低 Controller age 回退上限（如 30-35%）或使上限与 RCL 成正比而非固定值
- 引入"远征维护衰减"——远离最近己方 Controller 的 drone 其 Controller 维修效率递减
- Controller 维修范围增长率放缓（如 RCL1=1, RCL3=2, RCL5=3, RCL8=4 而非线性 1→5）

### G3 [Medium] — World 模式缺乏结构性长期目标，存在"资产囤积然后不动"的末期均衡

**发现**：World 模式被明确定义为"无胜利条件——类似 MMO 持续沙盒"。这在设计哲学上是合理的，但从博弈角度看：当玩家积累足够资产后，最理性的策略是维持现状、最小化风险暴露。不存在迫使高资产玩家参与高风险互动的机制。Arena PvE Challenge 和世界事件提供了部分出口，但属于自愿参与。

**建议**：
- 考虑引入"资源衰减"作为默认启用的 vanilla 模组（当前设为默认禁用）——即使不操作，囤积资源也会随时间衰减
- GCL 引入时间衰减——长时间不扩张的玩家 GCL 缓慢下降
- 周期性世界事件（如"赛季终末"）可重新分配边缘区域资源，打破静态格局

### G4 [Medium] — PvE 经济占比上限 30% 缺乏经验校准

**发现**：`max_pve_output_per_tick ≤ 全局 NPC 产出 / tick ≤ 世界再生总量 × 30%`。30% 是一个合理的初步估算，但没有附任何经验数据或模拟验证。如果实际值过低，PvE 将成为经济上无意义的"cosmetic content"；如果过高，PvE 刷怪将成为 dominant income strategy 压倒 PvP 互动。

**建议**：
- Phase 1 接受 30% 作为可配置默认值
- Phase 2（上线后）通过实际玩家数据校准，将观察到的合理范围写入 RUNBOOK
- 可考虑基于世界活跃玩家数的动态调整（PvP-heavy 世界降低 PvE 占比，PvE-heavy 世界反之）

### G5 [Medium] — 特殊攻击的 Novice→Standard 解锁是二进制跳变

**发现**：特殊攻击解锁策略为 Tutorial（全禁）→ Novice（全禁）→ Standard（8 种全开）。Novice 玩家从完全没有特殊攻击直接跳变到面对全部 8 种，存在学习曲线断层。对比身体部件和建筑通过 RCL 渐进解锁的设计，特殊攻击的解锁粒度显得突兀。

**建议**：
- 引入"Basic PvP"中间层级：仅开放 Fortify + Disrupt（纯防御性特殊攻击）
- 将 Hack/Drain/Debilitate/Overload 分散到 Standard 的不同 RCL 阶段
- 或者：将特殊攻击关联到 RCL 而非世界层级——如 RCL≤4 仅 Fortify+Disrupt, RCL5+ Drain+Debilitate, RCL7+ Hack+Overload

### G6 [Medium] — 默认 code_update_cost=0 降低策略承诺深度

**发现**：`code_update_cost` 默认值为 `{Energy: 0}`，`code_update_cooldown` 最小值 5 tick。在默认配置下，玩家可以几乎零成本热切换 WASM 策略。这降低了"策略承诺"机制带来的博弈深度——玩家无需预测对手策略并提前锁定 counter，可以实时响应切换。

**分析**：虽然这是有意设计的"Tutorial 友好"默认值（Tutorial 世界明确设置 cost=0, cooldown=0），但 gameplay.md §2.2 将 `code_update_cost` 列在"代码部署"规则表中，暗示其为 World 模式的通用默认。如果标准 World 也默认免费，则策略承诺维度的深度被牺牲。

**建议**：
- 明确区分 Tutorial 默认值（免费）和 Standard World 默认值（建议 200-500 Energy）
- 或保持免费为默认，但在反雪球合同一节中注明"服主可通过非零 code_update_cost 增加策略承诺深度"
- 将代码切换视为一种"策略变更"的显性成本，使其成为玩家经济决策的一部分

### G7 [Low] — Fog-of-war 缺乏主动侦察/反侦察机制层

**发现**：当前可见性模型基于 drone 默认视野范围 + Observer 建筑扩展，属于被动信息获取。缺少主动侦察能力（如牺牲型侦察 drone、扫描脉冲、隐身/反隐身对抗）来创造信息层面的策略博弈。虽然 Arena Challenge 嵌入 World 提供了低风险信息试探途径，但缺少专门的"信息战"维度。

**建议**（Future RFC，不阻塞当前）：
- 考虑增加"Scout" body part（低成本、高速、低/无战斗力、扩大的视野范围）
- 考虑"Cloak"特殊攻击——暂时降低自身可见性，代价为不能攻击
- 这些属于 Tier 2 扩展，不影响 MVP

---

## CrossCheck — 需要跨方向检查

以下问题超出 Game Designer 方向范围，需要其他评审员验证：

- **CX1**: `code_update_cooldown` 最小值 5 tick 是否足够防止 re-deploy refund 滥用（重复部署→退费→再部署循环）？→ 建议 **Economy** 审查 refund policy (§5.2: `contention_lost=0.5, self_invalid=0.0`) 与 cooldown 的交互是否产生可利用漏洞

- **CX2**: TransferToGlobal/TransferFromGlobal 的运输时间（10/5 tick）期间资源"可被敌方巡逻 drone 拦截"——拦截的具体机制和成功率未定义 → 建议 **Architect** 检查 PvP 运输拦截是否需要补充 spec

- **CX3**: snapshots/visibility 的 `host_get_objects_in_range` 有 5/tick 硬限制和 64KB 输出限制——大型战斗（如 Arena 5000 tick 末期）中此限制是否会导致关键实体丢失？→ 建议 **Performance** 评估 snapshot 截断在实际战斗场景中的触发频率

- **CX4**: MCP 工具的 `RateLimited` 错误码如何影响 AI agent 的实时决策能力？AI agent 达到 rate limit 后是被硬阻断还是降级？→ 建议 **AI/Agent** 审查 rate limit 对 AI agent gameplay 的实际影响

- **CX5**: `swarm_simulate` 返回 `authoritative: false, not_predictive: true`——MCP 文档对 AI agent 是否清晰传达了"不能依赖 simulate 结果做竞技决策"？→ 建议 **Documentation** 审查 MCP 工具文档对此的措辞是否充分警示

- **CX6**: `Leech` 和 `Fabricate` 标记为 ⏳ Tier 2 但在 api-registry.md CommandAction 表中已列出（#20, #21）——是否会造成 API 消费者期望这些可用但实际未实现？→ 建议 **Architect** 或 **API** 审查是否应使用 feature-gate 标记而非在 canonical registry 中暴露

---

## Strategy Depth Analysis

### 策略空间测度

```
维度                    选项数     约束
─────────────────────────────────────────────
Body Part 组合          8 种       50 上限，cost+age_modifier 约束
伤害类型 × 抗性         6×6        抗性倍率相乘
特殊攻击                8 种       冷却+资源消耗+body part 要求
建筑类型                13 种       RCL 渐进解锁
资源类型                可扩展     默认 1 (Energy)
物流模式                3 种       服务器级配置
可见性配置              4 种组合   服务器级配置
```

每 tick 决策空间 ≈ (body part 组合 × room 选择 × target 选择 × action 选择)，粗略估计超过 10^4 有效选项池。

### Dominant Strategy 检查

| 候选策略 | 反制手段 | 是否 dominant |
|---------|---------|:---:|
| 纯经济（全 WORK+CARRY） | 无防御→被攻击清场 | ❌ |
| 纯军事（全 ATTACK+RANGED） | 高 body cost + age 折寿 + 无经济收入 | ❌ |
| 龟缩防守（TOUGH+FORTIFY 堆叠） | Controller age 上限 + 维护费增长 + 无法扩张 | ❌ |
| Zerg rush（大量低成本 drone） | Room drone cap + Tower 防御 + active_aging | ❌ |
| 经济囤积（最大化全局存储） | 累进存储税（最高 20bp）+ 运输不可即时 | ❌ |
| Hack-spam（持续夺取敌方 drone） | Disrupt counter + Psionic 抗性 + 200tick CD | ❌ |

**结论**：不存在 dominant strategy。每个极端策略都有多层反制。最优玩法是混合策略——结合经济基础、适度军事、地图控制和物流规划。

### 纳什均衡分析（AI vs Human in World）

在 World 模式下 AI agent 与人类玩家同场竞技的均衡条件：

1. **信息对称**：AI 通过 MCP `swarm_get_snapshot` 获得与人类 Web UI 同构的世界状态 → 无信息优势
2. **行动对称**：AI 必须编译 WASM 部署，与人类完全相同的路径 → 无行动优势
3. **资源对称**：AI 受相同 fuel budget / command limit / drone cap → 无资源优势
4. **时间不对称**：AI 可 24/7 运行、更快迭代代码（修改→编译→部署循环快于人类）→ AI 具有**持续运营优势**
5. **策略不对称**：AI 擅长全局优化和精确计算，人类擅长直觉和创造力 → 领域各有优势

**预期均衡**：混合生态——AI 主导持久运营和经济优化（长期稳定策略），人类主导创新策略和竞技突破（短期战术创新）。World 模式中 AI 可能因持续运营在资源积累上领先；Arena 模式中 humans 的创造性策略可能制造意外结果。

### 信息不对称设计评分

| 维度 | 评分 | 说明 |
|------|:---:|------|
| Fog-of-war 战略价值 | ⭐⭐⭐⭐ | 本地存储隐匿 + NotVisibleOrNotFound 防止 oracle inference，迫使侦察投入 |
| 反侦察/反信息 | ⭐⭐ | 缺乏主动侦察机制层（见 G7） |
| 信息梯度发布 | ⭐⭐⭐⭐ | Safe Hint Ladder 按模式分级，竞技/练习/训练逐级释放 |
| 观战信息隔离 | ⭐⭐⭐⭐⭐ | spectate_delay + replay_privacy 防止观众信息泄露 |

---

## 附录：行文质量

- gameplay.md 内容详尽但存在大量重复（body part types 定义在 gameplay.md 中出现至少 3 次：TL;DR 表、TOML 定义块、模组扩展 API 声明）——建议后续整理时去重
- 资源存储模型、物流模式、SDK 生成流程等核心概念在 gameplay.md 和 api-idl.md 中均有覆盖，交叉引用正确但阅读路径略长
