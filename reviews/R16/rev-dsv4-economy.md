# R16 Economy Review — DeepSeek V4 Pro

> **Reviewer Profile**: Economy Reviewer (rev-dsv4-economy)
> **Phase**: R16 Phase 1 Clean-Slate Independent Review
> **Documents Reviewed**: design/README.md, design/gameplay.md, design/modes.md, design/economy-balance-sheet.md, specs/reference/api-registry.md, specs/gameplay/06-feedback-loop.md, specs/gameplay/08-api-idl.md, specs/core/08-resource-ledger.md

---

## Verdict

**CONDITIONAL_APPROVE** — 4 findings (1 Critical, 2 High, 1 Medium)，其中 Critical 为 economy-balance-sheet 与 empire-upkeep mod 公式结构不一致（balance sheet 使用独立公式体系且未引用 mod 参数），必须在设计阶段解决。High 发现涵盖 Recycle 退还率跨文档不一致和全局存储税收敛性参数缺失。所有发现均可在设计文档层修复，无引擎级阻塞。

---

## Strengths

1. **累进存储税设计优雅** — 四阶梯税率（0/1/5/20 bp）形成稳定均衡点：对于任意收入水平，存在 `storage_eq = income / tax_rate` 自然上限。顶部税率 20 bp 在 1500 tick 周期内累计损耗 ~95%，有效抑制无限囤积。数学上收敛且无振荡。

2. **Controller/Depot 双层维修体系** — Controller 免费维修（RCL 决定容量和距离）+ Depot 消费存储资源维修（固定 range=1），二者形成"主基地 vs 前线"的物流深度。Controller 硬上限 `min(0.5, controller_count * 0.5)` 防止多 Controller 永久化 drone，将 lifespan 约束保留为核心 tension。

3. **全局↔本地转换延迟+损耗阻止即时补给** — 双端损耗（入 1% + 出 5% = 往返 ~6%）+ 非零传输时间（入 10 tick + 出 5 tick），使全局存储只能用于"抽象经济力量"（部署费、维护费）而非战术补给。这是设计正确的：全局存储是 treasury，不是 logistics bypass。

4. **Resource Ledger 单一入口消除逃逸路径** — 所有资源流动（本地转移、全局存取、PvE 奖励、回收退还、建造消耗）通过统一 `ResourceOperation` 枚举结算，14 种操作类型闭合。定点费率模型（basis points）消除浮点非确定性。每 tick `Σ inflows - Σ outflows = Δ storage` 可审计。

5. **PvE Budget 四维账本防通胀** — Global ≤ 世界再生 × 30%、Zone ≤ 区域再生 × 50%、Player ≤ `RCL × 1000`、Event ≤ budget pool 的四维上限，防止"刷怪经济"压倒 PvP 战略价值。多维度超限时仅拒绝超限部分，不影响其他产出。

6. **实体膨胀成本归因正确** — Per-player snapshot 256KB cap 随自身 drone 数线性增长，不随全局膨胀。全局实体 > 50,000 时拒绝新 Spawn（`WorldEntityCapReached`），而非将膨胀成本外部化给现有玩家。这是少见的正确归因设计。

7. **Drone 消息系统引入博弈论深度** — 点对点消息不受引擎担保（不校验 payload 语义），使 P2P 资源交换成为博弈论问题——玩家必须设计可信协议或依赖声誉。引擎仅保证投递确定性，不承担撮合责任。

8. **新玩家经济门设计全面** — Transfer 锁（500 tick）+ PvE drop 绑定 + 同源账号组配额（5）三重反小号机制。所有参数均可配置，Tutorial 世界关闭所有限制，保持分级设计。

9. **Active aging (+10%) 防止挂机囤兵** — 执行命令的 drone 以 110% 速率衰老，使纯囤兵策略不具备经济效率——闲置 drone 也消耗维护费但无产出。与 empire-upkeep 模组的 drone_cost 组件形成双重闲置惩罚。

10. **确定性执行顺序完整** — UpkeepDeduction → StorageTax → PvEAward → LocalTransfer → GlobalDeposit → GlobalWithdraw → AlliedTransfer → BuildCost → SpawnCost → RecycleRefund，10 步执行顺序明确。同类型操作按 Command sequence 排序，保证 replay 一致性。

---

## Findings

### D1 [Critical] economy-balance-sheet 使用独立维护费公式，与 empire-upkeep mod 公式结构不兼容

**所在文档**: `design/economy-balance-sheet.md` §1 vs `design/gameplay.md` §8.7 empire-upkeep

**问题描述**:

economy-balance-sheet 定义的 Standard 模式维护费公式：
```
maintenance = base_upkeep × rooms × (1 + rooms / room_soft_cap)
base_upkeep = 50, room_soft_cap = 10
```

empire-upkeep mod（实际实现合同）的公式：
```
room_penalty = rooms * (room_base + rooms * room_superlinear / FIXED_SCALE)
total_cost = drones * drone_cost + room_penalty
```
默认参数：`drone_cost=2, room_base=10, room_superlinear=1 (0.0001)`

两个公式的差异：

| 维度 | balance-sheet (Standard) | empire-upkeep mod (默认) |
|------|--------------------------|--------------------------|
| drone 维护组件 | 无 | `drones × 2` |
| 房间线性项 | `50 × rooms` | `rooms × 10` |
| 超线性项 | `50 × rooms² / 10` | `rooms² × 0.0001` |
| 50 房间维护费(仅房间) | 15,000/tick | ~500/tick |

balance-sheet 声称的"50 房间维护费 15,000/tick"对应的是 `base_upkeep=50, room_soft_cap=10` 参数——此参数集在 mod 公式中无法直接表达（mod 公式无 soft_cap 参数，且 room_base 默认仅 10 而非 50）。

更关键的是，balance-sheet §4 "Anti-Snowball 证明" 的四条结论（边际收益递减、净正反馈克制、自然上限、物流成本）均基于 balance-sheet 自有公式验证，未在 mod 默认参数下检验。mod 默认参数下 room_superlinear=0.0001，超线性项在 50 房间时仅贡献 0.25/tick——维护费曲线近乎完全线性。

balance-sheet §3 的 Tutorial/Vanilla/Standard 模式对比表格使用的参数名（`base_upkeep`, `room_soft_cap`）在 mod 的 `[config]` 段中不存在。

**严重性**: Critical — balance-sheet 作为经济权威验证文档，其验证对象与实现合同不一致。服主无法从 balance-sheet 推算实际经济的收敛行为；"Standard 模式启用完整 anti-snowball" 的声明在默认参数下不成立。

**修复建议**:
1. 统一公式体系：balance-sheet 应直接引用 empire-upkeep mod 的参数体系（`drone_cost`, `room_base`, `room_superlinear`），而非自创参数名
2. 将 balance-sheet 的 Standard 模式参数映射为 mod 参数：例如 `room_base=50, room_superlinear=100000 (10.0)` 或等效组合
3. 在 mod 默认参数下重新验证 anti-snowball 性质，或在 balance-sheet 中明确标注"Standard 模式需调整 mod 默认参数至以下值方能启用 anti-snowball"
4. 考虑将 `room_soft_cap` 作为 mod 的可选参数加入 `mod.toml` 的 `[config]` 段，使 balance-sheet 公式成为 mod 的一个参数化实例

---

### D2 [High] Recycle 退还率在 IDL 与 Resource Ledger 间不一致

**所在文档**: `specs/gameplay/08-api-idl.md` §2 Recycle vs `specs/core/08-resource-ledger.md` §2 费率模型

**问题描述**:

IDL 定义（L160-162）:
```yaml
Recycle:
    refund: registry.body_cost(body) * 0.5
```
即固定 50% body cost 退还。

Resource Ledger 定义（L73-74, L165-166）:
```
recycle_refund_base = 5000 bp (50%)
recycle_refund_min = 1000 bp (10%)
```
以及公式：
```
recycle_refund = body_cost * remaining_lifespan * 5000 / total_lifespan / 10000
recycle_refund = max(body_cost * 1000 / 10000, recycle_refund)
```
即 lifespan 比例退还（满 lifespan→50%，空 lifespan→10% 保底）。

`design/gameplay.md` §8（L107-109）与 IDL 一致："回收 drone 获得 50% 资源退还"。

三份文档，两个不同方案：
- IDL + gameplay: 固定 50%
- Resource Ledger: lifespan 比例 10%-50%

**严重性**: High — 实现时无法确定采纳哪个方案。若采纳 lifespan 比例方案，则近死亡 drone 仅退还 10%，与 IDL 承诺的 50% 差距达 5 倍，直接影响玩家经济决策。Resource Ledger 作为资源权威合同应具备优先性，但 IDL 是代码生成来源，两者冲突时编译器无法裁定。

**博弈论影响分析**:
- 若采纳 fixed 50%：最优策略为"在 drone 即将死于 age 前 Recycle"，使用成本恒定 = 0.5 × body_cost。无激励提前 Recycle（除非为避免敌方击杀后 0% 退还）。
- 若采纳 lifespan 比例：存在最优 Recycle 时点的 trade-off——早 Recycle（高退还但短使用期）vs 晚 Recycle（长使用期但低退还）。有策略深度，但需更精确的 closed-form 均衡分析。

**修复建议**:
1. 以 Resource Ledger 为权威源（已有详细公式和费率参数），IDL 应从 Resource Ledger 派生 `refund` 字段
2. 将 lifespan 比例公式写入 IDL 的 Recycle 定义，或至少注明 `refund: see Resource Ledger §2`
3. 更新 `design/gameplay.md` L107-109 的 "50%" 描述，注明是"满 lifespan 时的上限比例"
4. 提供最优 Recycle 时点的博弈论分析：设 drone 剩余 lifespan = L，可产生资源 R/tick，body_cost = C，在 lifespan 比例退还下，最优 Recycle tick 的 closed-form 解

---

### D3 [High] 全局存储税率收敛参数缺失 — 无 Equilibrium Storage 封闭解文档

**所在文档**: `design/gameplay.md` §8 全局存储反制机制

**问题描述**:

累进税率设计正确（4 阶梯，0/1/5/20 bp），但缺少关键收敛参数文档。当前只给出了税率阶梯定义，未提供：

1. **各阶梯的 equilibrium storage**: 对于收入速率 I (units/tick)，均衡存储量 `S_eq = I / tax_rate`。例如：
   - 30-60% 阶梯（1 bp）：`S_eq = I / 0.0001`，若 I=100 → S_eq=1,000,000（已超 60% 上限，实际不会在该阶梯达到均衡——会在更低阶梯收敛）
   - 60-85% 阶梯（5 bp）：`S_eq = I / 0.0005`，若 I=100 → S_eq=200,000（在 60-85% 区间内）
   - 85-100% 阶梯（20 bp）：`S_eq = I / 0.002`，若 I=100 → S_eq=50,000（低于 85% 阈值，均衡在更低阶梯达成）

2. **最大可持续收入**: 在 85-100% 阶梯，`I_max = 1,000,000 × 0.002 = 2,000/tick`。收入超过此值的玩家将始终在容量上限运营且 net 为负，存储量下降至下一阶梯的均衡点。

3. **阶梯边界的振荡分析**: 当玩家存储恰好在阶梯边界附近（如 30% 或 60% 处），税率在相邻阶梯之间切换是否导致持续振荡？需要证明振荡是稳定的（Dedekind cut 式收敛）或提供 damping 机制。

**严重性**: High — 这是经济设计的核心验证缺失。虽然阶梯税率直觉上防止无限囤积，但缺少数学证明（均衡存在性、唯一性、收敛性、阶梯边界的稳定性）。

**修复建议**:
1. 在 economy-balance-sheet 中增加 §6 "Storage Tax Convergence Proof"，包含：
   - 各阶梯的均衡存储 vs 收入曲线
   - 最大可持续收入计算
   - 阶梯边界稳定性分析（证明不存在无限振荡——由于税率只在存储量变化方向上单调递增，均衡唯一）
2. 提供 `storage_tax_tiers` 的参数设计原理：为什么选择 30/60/85 分界点和 0/1/5/20 bp 税率
3. 补充验证：均衡存储量的稳定性——当存储偏离均衡时，净变化量符号是否将存储推回均衡

---

### D4 [Medium] Controller age 维修硬上限公式存在内部歧义

**所在文档**: `design/gameplay.md` §8 Drone 生命周期

**问题描述**:

公式：
```
max(0, age + 1 - min(0.5, controller_count * 0.5))
```

分析：
- `controller_count >= 1` → `controller_count * 0.5 >= 0.5` → `min(0.5, ...)` = 0.5
- `controller_count = 0` → `min(0.5, 0)` = 0

结论：对于任何 controller_count ≥ 1，min 项恒为 0.5。这意味着：
- 1 个 Controller 和 50 个 Controller 提供的 age 回退上限完全相同（均为 0.5/tick）
- 公式中 `controller_count * 0.5` 永远在 count=1 时即触及 cap

文档同时声称"此上限防止玩家通过堆叠多个 Controller 实现永久 drone"——但如果 1 个 Controller 已触达全局上限，则不存在"堆叠多个 Controller"的场景需要防止。该叙述的前提是多个 Controller 能提供增量收益，但公式不支持此前提。

两种可能解释：
1. **公式有误**：应为 `min(0.5, controller_count * 0.1)` 或其他渐近形式，使多个 Controller 在 cap 以下提供增量收益
2. **叙述有误**：Controller 数量不影响 age 回退上限，仅影响可服务的 drone 数量（RCL 决定的 repair_capacity 和 repair_range）

**严重性**: Medium — 不影响引擎可实施性（只要选一种解释实现即可），但文档内部矛盾可能导致实现错误。

**修复建议**:
1. 明确: Controller age 回退上限是全局固定的 0.5/tick（与 Controller 数量无关），还是每 Controller 独立贡献？
2. 若每 Controller 独立贡献但设硬上限，修正公式使多个 Controller 在上限以下提供增量收益，如 `min(0.5, 0.5 + controller_count * 0.05)` 或移除 controller_count 项直接用 `0.5` 常量
3. 同步更新"防止堆叠 Controller"的叙述以匹配最终公式

---

## CrossCheck — 需要跨方向检查

### 与 Security Reviewer
- **D1 (balance-sheet vs mod 公式不一致)**: 若实现时误采纳 balance-sheet 的激进参数（`base_upkeep=50, room_soft_cap=10`），新玩家可能被瞬间耗尽资源。Security reviewer 应验证参数边界的安全性——是否存在使经济瞬间崩溃的合法参数范围。
- **同源账号组配额绕过**: `same_origin_account_group_quota = 5` 依赖 IP/device fingerprint，需 Security reviewer 评估绕过难度和可能的强化方案。

### 与 Architecture Reviewer
- **Resource Ledger 单一入口**: 14 种 `ResourceOperation` 枚举通过同一 API 结算——Architecture reviewer 应验证此设计在高并发（100 players × 100 commands/tick）下的性能特征。
- **Recycle 退还率不一致**: IDL vs Resource Ledger 采用不同公式——需 Architecture reviewer 裁定以哪个为权威源，因其涉及代码生成管线（IDL → Rust enum）。

### 与 Gameplay Reviewer
- **D4 Controller age 硬上限歧义**: Gameplay reviewer 应澄清是 per-Controller 独立计算还是全局上限。
- **经济平衡表全尺度亏损**: 所有房间规模（1/5/20/50）均显示净亏损。Gameplay reviewer 需确认"代码效率提升"能桥接的最大缺口，并量化初始资源包大小。当前文档暗示效率可弥合 1 房间的 -30/tick（收入 25, 维护 55），但效率提升 120% 在 MVP 中是否可达成？

### 与 Balance Reviewer
- **D3 存储税收敛参数**: Balance reviewer 应提供 closed-form 均衡解和各阶梯最大可持续收入。
- **D1 公式统一**: Balance reviewer 应协调 economy-balance-sheet 与 empire-upkeep mod 的参数映射。

### 跨模式差异验证
- **Arena 免税 vs World 累进税**: `design/modes.md` 确认 Arena 免税（竞技公平），balance-sheet 仅覆盖 World 模式。Arena 模式的初始资源配置（`Energy = 10000, Crystal = 5000`）和 5000 tick 时长对应 World 模式中的哪个发展阶段？Arena 经济是否有独立的收支闭环验证？

---

## Mathematical Gaps Summary

| # | Gap | 所在文档 | 严重性 |
|---|-----|---------|--------|
| 1 | balance-sheet 维护费公式与 mod 公式参数体系不兼容，未提供映射 | economy-balance-sheet.md | Critical |
| 2 | Recycle 退还率 fixed 50% vs lifespan 比例 10-50% 未统一 | IDL vs Resource Ledger | High |
| 3 | 存储税各阶梯 equilibrium storage 和最大可持续收入未计算 | gameplay.md | High |
| 4 | Controller age 硬上限公式 controller_count 项在 count≥1 时恒为 cap | gameplay.md | Medium |
| 5 | 经济平衡表所有尺度净亏损，初始资源包未量化，"效率提升"缺口未验证 | economy-balance-sheet.md | Medium |

## Nash Equilibrium Observations

1. **Recycle 博弈 (若采纳 lifespan 比例方案)**: 纯策略 Nash 均衡存在于某个 `t_recycle` 使得 `(harvested(t) + refund(t))` 最大化。若其他玩家也采用相同策略，该均衡是对称的——无偏离激励。若采纳固定 50% 方案，均衡退化至"尽可能晚 Recycle"——同样稳定。

2. **全局存储囤积博弈**: 累进税率使存储策略收敛至唯一均衡。无玩家可通过单方面囤积获得优势（超额部分被税率侵蚀）。但若玩家联盟共享全局存储配额（通过 Allied Transfer），可能突破 per-player 税率限制——当前 allied 共享设计未明确是否合并计算存储税率。

3. **Empire-upkeep 拥挤博弈**: 超线性维护费使"无限扩张"不是 Nash 均衡——每个玩家存在最优房间数。若所有玩家同时扩张，资源竞争加剧（Source 争夺），进一步推高扩张成本。均衡存在但不一定唯一（取决于初始分布和 Source 分布）。

4. **P2P 消息交换博弈 (不可信协议)**: 无引擎担保的 P2P 交换是典型的 Prisoner's Dilemma 变体。单次博弈中 defect（收资源不履约）是 dominant strategy。但在重复博弈中，reputation 和 retaliation 可维持合作均衡——此设计将"建立信任"作为玩法层挑战，符合游戏深度目标。

5. **跨 World/Arena 经济分离**: Arena 经济完全隔离于 World——无跨模式资源流动路径。Nash 均衡在两种模式下独立存在，互不干扰。Arena 的对称初始条件 + 代码锁定消除了 World 模式中的先发优势和信息不对称，使均衡更接近完全信息博弈。
