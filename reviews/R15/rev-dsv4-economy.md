# R15 Economy Review — DeepSeek V4 Pro

> Reviewer: rev-dsv4-economy
> Date: 2026-06-18
> Phase: Phase 1 Clean-Slate
> Files reviewed: design/README.md, design/gameplay.md, design/modes.md, specs/gameplay/06-feedback-loop.md, specs/gameplay/08-api-idl.md

## Verdict

**CONDITIONAL_APPROVE** — 经济架构设计结构优良（Faucet/Sink/Lockup/Unlock 分类体系严密，反雪球机制在概念层面完备），但默认参数存在数学一致性问题，且关键平衡表缺失。解决 D1-D4 后即可 APPROVE。

---

## Strengths

1. **Faucet/Sink/Lockup/Unlock 分类账**（gameplay.md §Vanilla 经济分类账）：经济流分类清晰完整，每条规则标注资源类型和日增长目标范围。这是游戏经济设计领域罕见的严谨实践——从第一天就建立了可审计的经济模型骨架。

2. **边际累进存储税设计**：`global_storage_tax_tiers` 采用边际税率（仅超出部分征税）而非全额累进——这在经济学术上是正确的，避免了"多存 1 单位突然触发全域惩罚"的阶梯悬崖效应。

3. **三层物流反制体系**（gameplay.md §全局存储反制机制）：累进税 + 本地隐匿性 + 运输延迟形成三足鼎立的制衡——税制阻止无限囤积，隐匿性保留策略深度，运输延迟防止"瞬移补给"。三者互相补位，任缺一个都会产生可剥削漏洞。

4. **Recycle 50% 退款 + Tutorial 100% 退款**（gameplay.md §Drone 身体规划）：50% 永久损失是合理的再配置成本，防止无限 body-cycling。Tutorial 100% 退款隔离在新手世界，不污染标准经济——分层设计干净。

5. **Controller age 维修硬上限**（gameplay.md §Drone 生命周期）：`max(0, age + 1 - min(0.5, controller_count * 0.5))` — 无论多少个 Controller，每 tick 总 age 回退 ≤ 自然增长的 50%。多 Controller 无法叠加，单 Controller 即达上限。此公式正确防止了"Controller 农场实现永久 drone"的漏洞。

6. **Rhai 模组经济能力白名单**（gameplay.md §Rhai 安全隔离）：`deduct_resource` / `award_resource` / `damage_entity` / `set_entity_flag` 等全部经白名单校验，未注册 action 被拒绝。确定性合同要求禁用浮点、indexmap 固定迭代顺序、AST 节点预算——这保证了经济模组在回放中可重现。

7. **新玩家经济门**（gameplay.md §新玩家资源门）：`transfer_lock` + `pve_drop_bound` + `same_origin_account_group_quota` 形成三层防线。Tutorial 世界默认关闭所有限制，实现学习/保护分离。

---

## Issues

### D1 [Critical] — Empire-Upkeep 默认参数：声称 O(n²) 实际 O(n)

**位置**: gameplay.md §帝国维护费示例效果 + §默认参数校准说明

**问题**: empire-upkeep 是 Vanilla 默认启用的核心反雪球机制。其公式为：

```
cost(D,R) = drone_cost × D + R × (room_base + R × room_superlinear / 10000)
```

默认参数：`drone_cost=2, room_base=10, room_superlinear=1`（fixed<u32,4>，即 0.0001）。

代入得：`cost = 2D + 10R + 0.0001R²`

在合理房间数范围内（1-200），`0.0001R²` 项完全可忽略：

| 房间数 R | 线性项 10R | 超线性项 0.0001R² | 超线性占比 |
|----------|-----------|-------------------|-----------|
| 10       | 100       | 0.01              | 0.01%     |
| 50       | 500       | 0.25              | 0.05%     |
| 100      | 1000      | 1.0               | 0.1%      |
| 200      | 2000      | 4.0               | 0.2%      |

该公式在默认参数下**本质上是线性的**。文档自身承认："默认值在 1-50 房间范围内产生近乎线性的维护费曲线"。

更严重的是，文档中 §帝国维护费示例效果 的示例数值存在**数学不一致**：

```
文档声称: 50房, 500 drone → 维护费 ≈ 3150/tick
默认公式: 2×500 + 50×(10 + 50×0.0001) = 1000 + 500.25 = 1500.25
S=10000:  2×500 + 50×(10 + 50×1) = 1000 + 3000 = 4000
```

**3150 这个数字无法从公式和任何合理参数组合推导出来。** 文档声称维护费 3150 但默认公式算出 1500（差 2.1 倍），调整为 S=10000 后得 4000（差 1.27 倍）。5 房案例（275）与 S=10000 公式吻合，但更大案例不吻合。

**后果**: 使用默认参数启动的 World 服务器**没有任何有意义的反雪球效应**。大帝国按比例线性增长，先入者优势无法被经济机制自然遏制。文档 §反雪球合同 声称的 "O(n²) rooms" 不成立。

**建议**: 将 `room_superlinear` 默认值从 1（0.0001）提升到 100-500（0.01-0.05），使得在 20-50 房间范围超线性项贡献达到 10-30% 的总维护费。同时修正示例数值使其与公式自洽。

---

### D2 [High] — 存储税最高层级过于激进

**位置**: gameplay.md §全局存储反制机制 → §累进存储税

**问题**: 最高税率层级（85-100% 容量, 20 bp/tick）过于激进，实质上不是"税"而是"天花板"。

边际税率换算（容量 1M 为例）：

| 层级 | 税率 (bp) | 等效 %/tick | 该层满额纳税 | 等效 %/天 |
|------|----------|------------|-------------|----------|
| 0-30% | 0 | 0% | 0 | 0% |
| 30-60% | 1 | 0.01% | 30/tick | 288% |
| 60-85% | 5 | 0.05% | 125/tick | 1440% |
| 85-100% | 20 | 0.2% | 300/tick | 5760% |

满载纳税总额：455/tick。以每 source 300/tick 再生计算，需要 ~1.5 个 source 的产出仅用于支付存储税。

20 bp/tick 意味着在 85-100% 区间的资源以每天 5760% 的速度蒸发——这不是"税"，而是"熔毁"。85% 成为实际硬天花板，85-100% 的 15% 容量区间在实际游戏中不可持续超过几分钟。

**对比**: 30-60% 层（1 bp）和 60-85% 层（5 bp）之间的跳跃是 5x，而 60-85% 到 85-100% 是 4x。阶梯过于陡峭。建议将最高层从 20 bp 降至 8-10 bp，使 85-100% 成为"昂贵但仍可短期驻留"的区域而非"禁区"。

---

### D3 [High] — R15 vs R14 未解决项追踪：empire-upkeep 与 Recycle 套利

**位置**: gameplay.md §empire-upkeep 默认启用声明 + gameplay.md §Drone 身体规划

**问题 A — empire-upkeep 默认启用状态**: R14 Economy Review 的 D1 指出 empire-upkeep 默认参数 O(n²) 项可忽略（与本次 D1 同结论）。当前文档中 empire-upkeep 标注为"默认启用（protocol hook + Vanilla 公式），服主可关闭/替换"。此状态与 R14 一致——问题未解决，参数未调整。

**问题 B — Recycle 套利**: R14 D2 指出：当 `code_update_cost=0`（World 默认）时，若 empire-upkeep 未启用，则可能存在 Recycle 套利路径。当前文档中 empire-upkeep 默认启用且 `code_update_cost=0`，套利窗口理论上已关闭。但需验证：

- Recycle 退还 50% **基于 body part 类型**（`registry.body_cost(body) * 0.5`），不基于 drone 当前 HP
- 这意味着近死亡的战斗 drone Recycle 仍退还完整 50%
- 是否存在"战斗到 HP=1 → 撤退 Recycle → 立即重 spawn 同 body"的战术，使 Recycle 成为免费"治愈"手段？
- 计算：spawn 花费 X → 战斗造成 Y 价值 → HP 见底 → Recycle 返 0.5X → 重 spawn 花费 X。净支出：1.5X - Y。仅当 Y > 1.5X 时盈利——在同等战力对抗中难以实现。但若存在战力不对称（如高阶 body 碾压低阶），此路径可能被滥用。

**建议**: 在 body_cost 退款公式中引入 HP 比例因子：`refund = body_cost × 0.5 × (current_hits / hits_max)`。或在 R15 文档中明确说明当前设计的博弈论分析。

---

### D4 [Medium] — Vanilla Economy Balance Sheet 缺失

**位置**: gameplay.md §反雪球合同末尾

**问题**: 文档明确标注 "详见 Vanilla Economy Balance Sheet（待 B6 闭合时产出）"——这是经济模型中最关键的平衡验证文档，目前不存在。

Faizet/Sink 分类账虽列出了所有条目和"目标日均资源增长"范围，但这些是定性目标。如：
- Source 再生: "+3,000 ~ +10,000 / 玩家 / 天"
- Empire upkeep: "-40 ~ -3,150 / tick（按规模）"
- 全局存储税: "0 ~ 20 bp / tick"

这些数字的互洽性未经验证。例如：一个玩家维持 60% 全局存储（600K/1M）需支付 30/tick 存储税 + 假设 100 drone + 5 房的 empire upkeep (≈250/tick) = 280/tick 总支出。收入需来自 source 再生（300/tick × N 个 source）。N 需要 ≥ 1 才能收支平衡——这在 5 房场景下需要至少 1 个 source，看起来合理。但没有系统性的全参数空间验证。

**建议**: 在 APPROVE 前至少产出 Faucet/Sink 数值互洽矩阵——列出默认参数下 1-50 房间范围的收入/支出平衡表。无需完整 B6 闭合，但需证明分类账数字不自相矛盾。

---

### D5 [Medium] — 全局↔本地转换损耗与运输时间的套利分析缺失

**位置**: gameplay.md §资源存储模型 + gameplay.md §全局存储反制机制

**问题**: 
- `transfer_to_global_cost = 1%`, `transfer_to_global_time = 10 tick`
- `transfer_from_global_cost = 5%`, `transfer_from_global_time = 5 tick`

验证器 `transfer_time_remaining(0)` 确保同时只有一个转换进行中——这阻止了 micro-transfer 绕过的经典漏洞。✅

但运输期间的"可被拦截"机制（"运输期间资源处于'运输中'状态——可被敌方巡逻 drone 拦截"）引入了非零和的资源转移——拦截方获得资源，被拦截方损失资源 + 转换费。这在经济上是合理的（产生 PvP 激励），但需确认：

1. 拦截成功率与转换损耗的平衡——如果拦截过于容易，5% 转换费变得无意义（因为直接走运输被抢比付 5% 更亏）
2. 运输中的资源是否计入全局存储税基数？（假设不计入——因为"不可用"——但需确认）

---

### D6 [Low] — 资源门时效可能过短

**位置**: gameplay.md §新玩家资源门

**问题**: `new_player_transfer_lock_ticks = 500`。以 3s/tick 计算，仅约 25 分钟。一个刷号者注册后等待 25 分钟即可向主账号转移初始资源。配合 `same_origin_account_group_quota=5`，攻击者可以：
- 注册 5 个小号
- 各等待 25 分钟
- 转移 5 × 1000 = 5000 Energy 到主账号
- 成本 ≈ 5 × 150ms（PoW）= 750ms CPU 时间

虽然 PoW + IP 限流提供了一定阻力，但 25 分钟窗口 + 5 号配额对自动化攻击的门槛较低。

**建议**: 考虑将 `new_player_transfer_lock_ticks` 默认值提升至 2000-5000 tick（约 1.7-4 小时），或将其与 GCL/建筑进度绑定（"前 500 tick 且 GCL<2"）。

---

### D7 [Low] — IDL Recycle refund 公式精确度

**位置**: specs/gameplay/08-api-idl.md §commands.Recycle

**问题**: IDL 中 Recycle 定义为 `refund: registry.body_cost(body) * 0.5`——使用浮点乘法 `* 0.5`。但引擎确定性合同（gameplay.md §8.8）要求"数值：整数 + 定点数，禁 f64"。此矛盾需解决：refund 应使用定点数或整数除法。建议改为 `refund: registry.body_cost(body) / 2` 或使用 `fixed<u32,2>` 定点格式。

---

## Mathematical Gaps

### G1 — Empire-Upkeep 示例数值与公式不一致

| 场景 | 文档声称 | 默认公式 (S=1) | S=10000 公式 |
|------|---------|---------------|-------------|
| 1房 20 drone | 40 | 50.0 | 50.0 |
| 5房 100 drone | 275 | 250.0 | 275.0 |
| 20房 500 drone | 2100 | 1200.0 | 1600.0 |
| 50房 500 drone | 3150 | 1500.0 | 4000.0 |

没有任何单一参数组能同时匹配 5 房和 50 房的文档声称值。必须修正示例或参数使其自洽。

### G2 — Controller Age 硬上限的极端情况

`max(0, age + 1 - min(0.5, controller_count * 0.5))`

当 `controller_count ≥ 1` 时，`min(0.5, controller_count * 0.5) = 0.5`。公式退化为 `max(0, age + 0.5)`。

但 age 是整数（u32），`age + 0.5` 在整数语义下的行为未定义。如果向下取整（truncate），则 age 每 tick 实际减少 0 或 1，取决于小数累积。如果每 2 tick 累积到 1 再扣除，则有效 aging 速率为 0.5/tick——与设计目标一致。需在规范中明确小数处理规则。

### G3 — Global↔Local 转换百分比的定点精度

`transfer_to_global_cost = { Energy: 0.01 }`（1%）、`transfer_from_global_cost = { Energy: 0.05 }`（5%）。这些都是百分比，应用到实际 amount 时：
- `TransferToGlobal(100 Energy) → cost = 100 × 0.01 = 1 Energy` ✅ 整数
- `TransferToGlobal(50 Energy) → cost = 50 × 0.01 = 0.5 Energy` ⚠️ 非整数

确定性合同要求定点数而非浮点。需明确小数截断方向（floor/ceil/round）以及是否设置最小成本（如至少 1 单位）。

---

## Nash Equilibrium Issues

### N1 — 存储税下的纳什均衡：囤积 vs 流通

存储税在 60% 容量以上产生显著成本。纳什均衡将迫使理性玩家维持在 ~55-60% 容量——刚好低于 60% 税率跳跃点。但这一均衡是脆弱的：

- 若所有玩家都维持在 60%，则没有人有动力囤积资源 → 市场流动性高（当市场实现时）
- 但若一个玩家突破 60% 囤积（承受 1-5bp 税），可能获得战略优势（如战时快速爆兵）
- 敌对玩家无法区分"对方在囤积"还是"对方在忍受税率"——因为本地存储不可见（隐匿性）

此博弈的均衡取决于军事回报是否超过税收成本。文档未分析此博弈论场景——囤积 vs 流通的阈值点在何处。

### N2 — Alliance 免费 Transfer 的套利

Allied 玩家间 `Transfer` 免 convert 延迟（gameplay.md §Allied 特权）。这意味着：
1. 玩家 A 本地存储 → 无需付 convert 成本直接 transfer 给玩家 B
2. 玩家 B 可以将资源转入全局存储（付 1% 成本）
3. 再转回给玩家 A（再付 5% 成本）

直接路径 A→全局：1% 成本 + 10 tick 延迟。间接路径 A→B→全局→A：...显然更贵。所以没有直接套利。

但如果 A 和 B 协作规避运输时间：A 需要本地资源但 global 转换需 5 tick——B 直接 transfer 给 A 是即时的（同 tick）。这本身是 alliance 的设计目的，不是漏洞——但需确认 alliance transfer 的及时性不会瓦解"运输时间作为战略约束"的设计。

---

## CrossCheck

- **CX1**: empire-upkeep 默认参数 `room_superlinear=1` 导致 O(n²) 项可忽略，这是有意为之还是疏忽？ → 建议 **Architect** 检查：反雪球合同中的 O(n²) 声明与默认参数是否矛盾，应该以哪个为准？
- **CX2**: PvE NPC 掉落经济上限 `max_pve_output_per_tick ≤ 世界再生总量 × 30%` ——这个 30% 阈值如何与 Source 再生、empire upkeep 等 Faucet/Sink 流量互洽？ → 建议 **Gameplay** 检查：PvE 掉落上限是否与 Vanilla Economy Balance Sheet 中的数值一致？
- **CX3**: `same_origin_account_group_quota=5` + `new_player_transfer_lock_ticks=500` 的组合是否足以防止刷号经济滥用？ → 建议 **Security** 检查：500 tick (25 min) 的转移锁是否过短？是否需要与 PoW 难度联动？
- **CX4**: Recycle 退款基于 body part 类型而非当前 HP——近死亡 drone 全退 50% 是否引入"自杀式消耗→回收"的无损战术？ → 建议 **Gameplay** 检查：是否应在 refund 公式中引入 HP 比例因子？
- **CX5**: IDL 中 `refund: registry.body_cost(body) * 0.5` 使用浮点乘法，与确定性合同中"禁 f64"矛盾 → 建议 **Architect** 检查：IDL 的浮点用法是否与引擎整数/定点数实现一致？

---

## Summary

经济架构的数学模型骨架正确：Faucet/Sink 分类、边际累进税、运输延迟反制、Controller age 硬上限都是经过深思熟虑的设计。两个 Critical/High 问题集中在**参数层面**而非**结构层面**——empire-upkeep 默认参数使反雪球失效 + 存储税最高层级过于激进。辅以示例数值不一致和 Balance Sheet 缺失，当前设计可进入实现阶段但需在编码开始前修正参数。Verdict: **CONDITIONAL_APPROVE**。
