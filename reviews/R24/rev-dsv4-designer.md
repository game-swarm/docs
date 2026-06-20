# R24 Game Design Review — rev-dsv4-designer

> **评审方向**: Game Designer (DeepSeek V4 Pro)
> **评审类型**: Clean Slate — spec ↔ design 对齐检查
> **日期**: 2026-06-20

---

## Verdict: CONDITIONAL_APPROVE

Strategy space is robust —Move-as-action + 8 body parts × 6 damage types × 8 special attacks + Controller/Depot logistics creates genuine tactical depth with no detectable dominant strategy. Progressive PvP transition (First-Attack Shield → Soft PvP → Full PvP) is well-designed for new player retention.

However, 3 Critical/High spec↔design contradictions must be resolved before implementation: global transfer delay (10/5 vs 100), missing body part age_modifier values, and diverging build/body part costs across documents.

---

## Strengths

- **Move-as-action 设计**: 每 tick 单 action slot 消除 Move+Attack 顺序竞争的二义性，为编程游戏创造非平凡的战术决策
- **身体部件 age_modifier 系统**: 攻击折寿/防御延寿的 trade-off（TOUGH +100 vs ATTACK -80）让 body 规划成为有意义的长期决策
- **Controller/Depot 双层后勤**: 前线 Depot 的物理供给线设计创造了物流拥挤、补给线打击、节点夺取等战术深度
- **渐进式 PvP 过渡**: First-Attack Shield → Soft PvP → Full PvP 三个阶段有效防止新手保护期结束瞬间被碾压
- **8 种特殊攻击 + 6 种伤害类型**: 完整的克制体系（Hack→Psionic, Drain→EMP, Debilitate→Corrosive, Disrupt→Sonic）提供丰富的策略对抗
- **累进存储税 + 帝国维护费**: Anti-snowball 机制设计合理，非线性成本自然收敛帝国规模

---

## Concerns

### C1 — Global Transfer Delay: design 与 Resource Ledger 严重不一致

| 项目 | design/gameplay.md | specs/core/08-resource-ledger.md |
|------|-------------------|----------------------------------|
| 文档位置 | §2.2 资源存储模型 + §2.2 全局↔本地转换 | §2.1 统一参数表 |
| design 值 | `transfer_to_global_time = 10`, `transfer_from_global_time = 5` | — |
| spec 值 | — | `global_transfer_delay = 100 tick` |

**严重度**: **Critical**

**冲突描述**: design 定义全局↔本地双向延迟分别为 10 tick（存入）和 5 tick（提取），但 Resource Ledger（经济权威）定义 `global_transfer_delay = 100 tick`（10-20 倍差异）。`global_transfer_delay` 标为「全局提取延迟」，语义上对应 `transfer_from_global_time`——5 vs 100 差异为 20 倍。

**影响**: 如果 implemented at 100 tick，从全局存储提取资源需要 100 tick（~5 分钟）才能到账，严重改变物流策略——补给线规划从「短时等待」变为「长期预判」，可能使全局存储在战斗中几乎不可用。如果 intended 值是 10/5，则 Resource Ledger 存在写入错误。

**修正建议**: 在 Resource Ledger §2.1 中将 `global_transfer_delay` 拆分为 `global_deposit_delay = 10` 和 `global_withdraw_delay = 5`，与 design 对齐。或确认 100 tick 是否为设计意图并同步更新 design。

---

### H1 — Body Part age_modifier: design 已定义但 world-rules spec 缺失

| 项目 | design/gameplay.md | specs/core/07-world-rules.md |
|------|-------------------|------------------------------|
| 文档位置 | §8 身体部件类型定义 | §7.1 身体部件类型 |
| Attack | `age_modifier = -80` | **缺失** |
| RangedAttack | `age_modifier = -50` | **缺失** |
| Heal | `age_modifier = -30` | **缺失** |
| Claim | `age_modifier = -50` | **缺失** |
| Tough | `age_modifier = 100` | **缺失** |

**严重度**: **High**

**冲突描述**: design/gameplay.md 为 5 个身体部件明确定义了 `age_modifier` 值（影响 drone lifespan），但 specs/core/07-world-rules.md 的 `[[body_part_types]]` 定义中所有 8 个部件均未包含 `age_modifier` 字段。虽然 §7.1 字段说明表提到 `age_modifier` 为可选字段，但 design 中明确赋值的部件在 spec 中完全缺失此字段。

**影响**: 如果实现者仅参考 world-rules spec，所有 body part 的 age_modifier 将为默认值 0——dron寿命计算将出错，ATTACK drone 不会折寿、TOUGH drone 不会延寿。这彻底改变了 body 规划的 trade-off 计算。

**修正建议**: 在 world-rules.md §7.1 所有 body part 定义中补全 `age_modifier` 字段，值与 design/gameplay.md 对齐。

---

### H2 — Build Costs: design/gameplay.md 与 api-registry.md 多处不一致

| 建筑 | design/gameplay.md | api-registry.md §10.2 | 差异 |
|------|-------------------|----------------------|------|
| Spawn | {Energy: 200} | 300 | +50% |
| Tower | {Energy: 200} | 800 | +300% |
| Link | {Energy: 300} | 400 | +33% |
| Extractor | {Energy: 800} | 600 | -25% |
| Terminal | {Energy: 500} | 1200 | +140% |
| Observer | {Energy: 300} | 500 | +67% |

**严重度**: **High**

**冲突描述**: 6 个建筑在两份文档中的建造成本不同。api-registry 数据来自 economy.idl.yaml → CI 自动生成，design/gameplay.md 为手工维护。差异幅度从 -25%（Extractor）到 +300%（Tower）。

**影响**: Tower 从 200→800 (+300%) 将显著改变早期防御策略——新手需攒 4 倍资源才能建塔。Terminal 从 500→1200 (+140%) 推迟市场交易解锁时间。

**修正建议**: 以 economy.idl.yaml 为权威源，将 design/gameplay.md §2.2 建筑类型表中的 cost 值与 api-registry §10.2 BuildCost 对齐。或反之，若 design 值为设计意图则修正 economy.idl.yaml。

---

### H3 — RangedAttack Body Part Cost 不一致

| 项目 | design/gameplay.md | api-registry.md §10.2 |
|------|-------------------|----------------------|
| RangedAttack 生成成本 | {Energy: 100} | 150 |

**严重度**: **High**

**冲突描述**: design/gameplay.md body part 定义中 RangedAttack cost=100，但 api-registry SpawnCost 表中 RANGED_ATTACK=150（+50%）。其他 body part 成本一致（Move=50, Work=100, Carry=50, Attack=80, Heal=250, Claim=600, Tough=10）。

**影响**: 远程攻击 drone 的生成成本在实际实现中可能比设计意图高 50%，改变远程 vs 近战的 cost-efficiency 计算。

**修正建议**: 以 economy.idl.yaml 为权威源，统一 design/gameplay.md 或 IDL 中 RangedAttack 的 cost 值。

---

### M1 — Heal Range: body part 定义 vs Command 校验不一致（有解释但模糊）

| 项目 | 值 | 来源 |
|------|-----|------|
| Heal body part range | 1 | design/gameplay.md, specs/core/07-world-rules.md |
| Heal Command 校验距离 | 3 格内 | specs/reference/commands.md |

**严重度**: **Medium**

**冲突描述**: body part 定义中 Heal range=1，但 commands.md 校验条件为"3 格内"。world-rules.md §7.1 有一条注释说明 CommandAction 的 `in_range()` 可覆盖 body part 的 range 值——但 design/gameplay.md 未提及此覆盖，读者会认为 Heal 只能治疗相邻格。

**影响**: 新手玩家读 design 会误以为 Heal 只能 1 格内使用，实际实现支持 3 格。设计文档的信息不对称可能误导策略编写。

**修正建议**: 在 design/gameplay.md body part 表中为 Heal 添加注释 `Command 校验实际有效距离 3`。

---

### M2 — Heal 的「缩短负面状态」能力：design 定义但 spec 缺失

| 项目 | design/gameplay.md | specs/reference/commands.md |
|------|-------------------|----------------------------|
| Heal 额外效果 | "每 tick 可缩短一个负面状态 10 tick 持续时间" | 未提及——仅定义 `HEAL parts × 12` HP 恢复 |

**严重度**: **Medium**

**冲突描述**: design 赋予 Heal body part 额外的负面状态缩短能力，但 commands.md 和 api-registry 中 Heal 命令仅定义 HP 恢复，不包含负面状态缩短逻辑。如果这是一个设计意图但尚未在 spec 中落地，则属于 spec 滞后。

**影响**: 实现可能遗漏此能力——玩家读了 design 期望 Heal 可以清负面状态（与 Fortify 的净化功能互补），但实现只有 HP 恢复。

**修正建议**: 若是设计意图，在 api-registry 和 commands.md 的 Heal 条目中添加 `status_reduction: 10 tick per HEAL part` 参数。若此能力已由 Fortify 覆盖且不再计划，从 design/gameplay.md body part 表中移除该描述。

---

### M3 — World 模式「无排行榜」但 API 提供 leaderboard 工具

| 项目 | design | spec |
|------|--------|------|
| World 排行榜 | "World 模式无排行榜"（gameplay.md, modes.md） | `swarm_get_leaderboard` 存在（api-registry.md §3.2 Play） |

**严重度**: **Medium**

**冲突描述**: design 明确声明 World 模式无排行榜、不设竞争榜单，但 API Registry 中存在 `swarm_get_leaderboard` 工具。该工具未标注 scope 限制（World-only / Arena-only），API 文档读者会假定其在两种模式下均可用。

**影响**: 若 leaderboard 仅在 Arena 可用，需在 API 文档中标注。否则实现可能错误地暴露 World 排行榜，违反设计合同。

**修正建议**: 在 api-registry.md `swarm_get_leaderboard` 条目中添加 `visibility_filter: arena_only` 或明确的 scope 说明。

---

### L1 — Starting Resources 仅定义在 Resource Ledger，design/gameplay.md 缺失

| 项目 | design/gameplay.md | specs/core/08-resource-ledger.md |
|------|-------------------|----------------------------------|
| 新玩家初始资源 | 未定义 | `{Energy: 5000, Minerals: 2000}` |

**严重度**: **Low**

**描述**: design/gameplay.md §1 Golden Path 提到"自动获得初始 Energy"但未给出具体数值。初始资源包仅在 Resource Ledger §2.3 和 api-registry §5.1 中定义。

**修正建议**: 在 design/gameplay.md §1 或 Vanilla Ruleset 汇总表中引用初始资源默认值。

---

### L2 — world-rules spec 示例中 code_update_cooldown = 0 与 design 默认值 5 不一致

| 项目 | design/gameplay.md | specs/core/07-world-rules.md |
|------|-------------------|------------------------------|
| code_update_cooldown 默认值 | 5 | 示例显示 `update_cooldown = 0` |

**严重度**: **Low**

**描述**: world-rules.md world.toml 示例中 `update_cooldown = 0`，但 design §2.2 明确 `code_update_cooldown` 默认 5、最小值 5。推测 world-rules 示例使用 Tutorial 配置。

**修正建议**: 在 world-rules.md 示例文件中将 `update_cooldown` 改为 5 或添加注释 `# 默认 5，示例为 Tutorial 配置`。

---

## Strategy Depth Analysis

### 策略空间评估

**动作空间**: 每 tick 每 drone 选择 Move/Harvest/Attack/RangedAttack/Heal/Build/Recycle/Claim/Spawn + 8 种特殊攻击 + Global Storage 操作。单 drone 每 tick 选择 1 个主动作 + 可选指令（如 Transfer）。500 drone × 100 玩家 → 巨大组合空间。

**身体部件规划**: 8 种 body part 构成 drone 蓝图——Move 消除 fatigue、Work 采集/建造、Carry 运输、Attack 近战、RangedAttack 远程、Heal 治疗、Claim 占领、Tough 加血。age_modifier 引入寿命 trade-off——ATTACK 折寿 80 tick、TOUGH 延寿 100 tick。body 不可逆（只能 Recycle 部分退还），构成有意义的长期规划决策。

**后勤深度**: Controller（免费维修，RCL 决定容量+距离）vs Depot（消耗资源维修，范围固定 1）。前线 Depot 需要 CARRY drone 持续补给——物流是玩法而非免费午餐。Depot 被摧毁→前线 drone 断粮。维修硬上限（50% 自然增长）防止永生 drone。

**伤害体系**: 6 种伤害类型 × 2 层抗性（组件 × 属性）。Tough 对 Kinetic/Sonic 抗性 0.5，建筑对 EMP 弱 2.0。特殊攻击绑定特定抗性（Hack→Psionic、Drain→EMP、Debilitate→Corrosive），产生克制链而非单一的攻防升级。

**Anti-Snowball**: 累进存储税（最高 20bp/tick）+ 帝国维护费 O(n²) + 维修硬上限 + soft_launch 过渡——不保证公平但防止垄断固化。

### Dominant Strategy 检测

未检测到明显 dominant strategy。原因：
1. 身体部件的 lifespan trade-off 防止「全 ATTACK rush」
2. 累进存储税防止「纯囤积经济」
3. Move-as-action 防止「攻击+移动」的无损追击
4. 特殊攻击抗性体系创造克制（Hack 被 Fortify 反制）
5. Depot 供给线脆弱性防止「纯远征」策略

### 信息不对称设计

fog_of_war（World 默认启用）+ 本地存储隐匿性（敌方不可见）提供足够策略深度。Overload 的可见性约束（必须 `is_visible`）防止不可见攻击。First-Attack Shield 暴露攻击者位置（即使超出正常视野）——这是设计上的主动信息赋予，平衡新手的信息劣势。

---

## Summary

| 严重度 | 数量 | 项目 |
|--------|------|------|
| Critical | 1 | C1 — Global transfer delay 10/5 vs 100 |
| High | 3 | H1 — Body part age_modifier 缺失; H2 — Build costs 不一致; H3 — RangedAttack cost 不一致 |
| Medium | 3 | M1 — Heal range 1 vs 3; M2 — Heal 负面状态缩短能力缺失; M3 — World leaderboard 矛盾 |
| Low | 2 | L1 — Starting resources 未在 design 定义; L2 — code_update_cooldown 示例值 |