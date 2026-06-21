# R32 Design & Economy 独立评审 — rev-dsv4-design-economy

> **评审日期**: 2026-06-21
> **评审范围**: R32 Clean-Slate，Design & Economy 视角专项子集
> **评审模型**: DeepSeek V4 Pro

---

## 1. Verdict

**REQUEST_MAJOR_CHANGES**

核心问题：Balance Sheet 全状态净负无 break-even 点，与 Resource Ledger 宣称的「自维持」直接矛盾。Anti-snowball 证明缺乏数学推导。另有参数遗漏和数据不一致需修复。

---

## 2. 发现的问题

### Critical

#### C1 — Balance Sheet 全范围净赤字，无可持续均衡点

- **文件**: `/tmp/swarm-review-R32/design/economy-balance-sheet.md` §2 全表
- **关联**: `/tmp/swarm-review-R32/specs/core/08-resource-ledger.md` §2.3 Growth Path

Balance Sheet 中 Standard 模式所有规模（free_upkeep 结束后）均为净赤字：

| 房间数 | 净流量/tick (优化 ×1.5) | 说明 |
|:---:|:---:|------|
| 1 (post-free_upkeep) | -33 | 基础收入 22，维护费 55 |
| 2 | -54 | 需 Controller 升级 |
| 3 | -96 | Harvester 优化初见成效 |
| 5 | -195 | 代码效率成关键 |
| 10 | -225 | 2× 效率可趋近（但仍为负） |
| 20 | -1,480 | 边际收益递减显著 |
| 50 | -11,188 | 软上限饱和 |

**不存在任何 break-even 点**。维护费 O(n²) 始终压倒收入 O(n)。

然而 Resource Ledger §2.3 Growth Path 表明确标注 tick 2000+ 阶段为 **「✅ 自维持 (Self-sustaining)」**：

```
| 2000+ | Full economy | 完整 faucet | Empire upkeep | ✅ 自维持 |
```

这与 Balance Sheet 的数学结果**直接矛盾**。若 Balance Sheet 正确，则不存在任何「自维持」状态——所有玩家在 free_upkeep 结束后进入不可逆的净消耗，唯一结果是缓慢破产。

**影响**: 若 Balance Sheet 数值正确，则游戏经济设计在数学上不可持续——这不是「anti-snowball 特性」而是「无解死亡螺旋」。若 Growth Path 的「自维持」声明正确，则 Balance Sheet 的参数或公式有误。两者必有一错。

**修复建议**:
- **方案 A**: 修正 Balance Sheet 参数使存在至少一个均衡点。例如将 `base_upkeep` 从 50 降至 30–35，使 5–10 房间 + 高效代码可达 break-even；或引入收入非线性增长（Source 升级/L3+ 产出显著提升）。
- **方案 B**: 若全赤字为有意设计，则从所有文档中移除「自维持」「break-even」等表述，明确声明 Standard 为「燃烧经济」——玩家靠初始资源 + free_upkeep 积累储备，用 PvE drop + 代码优化延长生命周期，最终必然衰退。同时需重新评估是否与「持久世界」定位冲突。
- **方案 C**: 引入玩家侧的长期收入增长曲线——例如 GCL 提供被动收入加成、殖民地年龄提供效率加成——使老玩家有路径到达均衡。当前文档中 GCL 未绑定经济收益。

> ⚠️ **D-item**: 此为设计决策项，需用户裁决。Balance Sheet 全赤字是有意设计还是参数错误？

---

### High

#### H1 — Anti-Snowball 证明缺乏数学推导

- **文件**: `/tmp/swarm-review-R32/design/economy-balance-sheet.md` §4

§4 声称 4 条性质：

1. 「边际收益递减：第 N+1 个房间的维护费增长 > 收入增长」— **未推导**。维护费增长为 dU/dN = 50 + 10N（线性递增），收入增长近似常数 ~35–45/房间。数值上确实 dU/dN > dI/dN 对所有 N>0 成立，但未给出不等式证明。
2. 「净正反馈克制：玩家必须通过代码优化获得更高效率」— **非数学陈述**，是设计意图声明。
3. 「自然上限：50 房间附近维护费吞噬全部收入」— Balance Sheet 数值支持（-11,188/tick），但未证明 50 是唯一吸引子或最优停止点。
4. 「No Teleport + 物流成本」— 定性陈述，未量化。

**影响**: 作为「anti-snowball contract」的数学基础，§4 应提供严格证明而非定性描述。当前形式无法通过 CI 验证或外部审计。

**修复建议**: 为 §4 补充形式化证明：
- 证明维护费 O(n²) 增长 > 收入 O(n) 增长对所有 n > n₀（指定 n₀ 为 break-even 消失点）
- 推导最优帝国规模 n* 使累计净收益最大化（若全赤字则 n* = 1）
- 量化 No Teleport 的经济效应（延迟成本 = 机会成本 × global_withdraw_delay）

---

#### H2 — Resource Ledger 遗漏 `global_deposit_delay` 参数

- **文件**: `/tmp/swarm-review-R32/specs/core/08-resource-ledger.md` §2.1

Resource Ledger 声明为「所有费率、公式、参数的唯一定义源」。但 §2.1 统一参数表中仅列出：

```
global_transfer_delay | 100 | tick | 全局提取延迟
```

**缺失** `global_deposit_delay`（默认 10 tick）。该参数在以下位置有定义：
- `design/gameplay.md` §8: `global_deposit_delay = 10`
- `design/economy-balance-sheet.md` §3: `global_deposit_delay = 10`

作为「唯一经济权威」，Resource Ledger 必须包含所有经济参数。`global_deposit_delay` 与 `global_transfer_delay`（即 withdraw delay）语义不同——前者控制本地→全局的延迟（10 tick），后者控制全局→本地的延迟（100 tick）。

**影响**: 实现者从 Resource Ledger 读取参数时不会意识到 deposit 有独立延迟值。若误将 `global_transfer_delay = 100` 同时用于 deposit 和 withdraw，则本地→全局也需 100 tick——严重削弱经济流动性。

**修复建议**: 在 Resource Ledger §2.1 中添加：
```
global_deposit_delay | 10 | tick | 全局存入延迟（本地→全局）
```
并将现有 `global_transfer_delay` 重命名为 `global_withdraw_delay` 以消除歧义。

---

### Medium

#### M1 — `global_storage_capacity` 示例值不一致

- **文件**: `/tmp/swarm-review-R32/design/gameplay.md` 行 1287

world.toml 配置示例中：

```toml
global_storage_capacity = 100000   # 行 1287
```

而所有权威源均为 1,000,000：

| 源 | 值 |
|---|:---:|
| gameplay.md §8 参数表 (行 309) | 1,000,000 |
| api-registry.md §5.7 | 1,000,000 |
| resource-ledger.md §5.7 | 1,000,000 |
| economy-balance-sheet.md (storage tax 示例用 1M) | 1,000,000 |

示例中的 100,000 与默认值差 10 倍。虽标记为「可配置」示例，但新读者可能误以为 100,000 是默认值。

**修复建议**: 将示例行改为 `global_storage_capacity = 1000000` 并添加注释 `# 默认值 1,000,000，服主可调`。

---

#### M2 — Balance Sheet 1 房间场景 free_upkeep 标记不清晰

- **文件**: `/tmp/swarm-review-R32/design/economy-balance-sheet.md` §2.7 汇总表

汇总表 1 房间行标注 `+22`¹ 且脚注 `¹ 1 房间 free_upkeep 期内；free_upkeep 结束后维护费恢复 → 净流量 -33（基础）`。

问题：汇总表的「净流量」列对 1 房间显示 `+22`¹（指 free_upkeep 期内仅收入侧），但对 2–50 房间显示净流量（收入 − 支出）。1 房间的列语义与其他行不同——读者需读脚注才能理解，且脚注本身包含两个不同场景的值。

**修复建议**: 汇总表分为两段：free_upkeep 期内（1–3 房间标注）和 free_upkeep 期后（所有房间）。或为 1 房间单独列出「free_upkeep 期内」和「free_upkeep 后」两行。

---

#### M3 — Economy Balance Sheet 的 `allied_transfer_enabled` 模式差异表标注歧义

- **文件**: `/tmp/swarm-review-R32/design/economy-balance-sheet.md` 行 204

```
| `allied_transfer_enabled` | true | false | **true (Restricted)** |
```

列标题为 `Tutorial | Vanilla (Novice) | Standard`。Standard 标注 `true (Restricted)` 正确。但 Novice 标注 `false` 与 gameplay.md §8「Novice 默认禁用」一致，而 Tutorial 标注 `true`——这与 gameplay.md 的 Novice/Tutorial 「默认禁用特殊攻击」的整体基调不完全矛盾（Allied Transfer 不是特殊攻击），但 Tutorial 中 `allied_transfer_enabled = true` 是否有必要值得商榷——新玩家处于学习阶段，联盟转移增加复杂度但无实际收益。

**影响**: 低——Tutorial 世界通常单人学习，不触发联盟逻辑。

**建议**: 非阻塞。`true` 和 `false` 均有合理理由。但若选择 `true`，应在 gameplay.md 补充说明 Tutorial 为何启用联盟转移。

---

### Low

#### L1 — Resource Ledger 执行顺序中 `UpkeepDeduction` 位于 `StorageTax` 之前可能造成连续赤字反馈放大

- **文件**: `/tmp/swarm-review-R32/specs/core/08-resource-ledger.md` §4

执行顺序：
```
1. WorldStartupSubsidy
2. UpkeepDeduction    ← 先扣维护费
3. StorageTax         ← 后扣存储税
4. PvEAward
...
```

若玩家全局存储不足支付维护费，`UpkeepDeduction` 扣至 0 并记录 `UpkeepDeficit`。然后 `StorageTax` 再在已归零的存储上计税（按公式 tax = 0 × rate = 0，实际无害）。但文档未说明 deficit 场景下 storage tax 是否跳过。

**影响**: 极低——0 × rate = 0，无实际数值错误。但 spec 完整性要求覆盖边界条件。

**修复建议**: 补充说明：`UpkeepDeduction` 导致存储降至 0 后，`StorageTax` 仍然执行但税率为 0（存储 < 30%）。

---

#### L2 — `special_param` 类型在不同文档间为 float vs 未指定

- **文件**: 
  - `/tmp/swarm-review-R32/design/gameplay.md` 行 1024: `special_param | float | 否`（float）
  - `/tmp/swarm-review-R32/specs/reference/api-registry.md` 多处: `special_param` 未在 schema 中定义

gameplay.md 的 `[[custom_actions]]` 字段表将 `special_param` 标为 `float`，但整个项目已全面禁用浮点数（Resource Ledger §2 明确「禁止浮点数」，API Registry §0 全部使用定点类型）。若 `special_param` 实际使用 BasisPoints 表示比例（如 0.5 → 5000 bp），应修正此处类型标注。

**修复建议**: 将 `special_param | float` 改为 `special_param | u32`（值域 0–10000，语义为 basis points），与全局定点数策略一致。或统一标注为 `MilliUnits`。

---

## 3. 亮点

1. **分层 anti-snowball 架构优秀**。累进存储税 + 超线性维护费 + Controller 老化 + 新玩家保护形成多层独立防线，即使单一机制被绕过，其他机制仍有效。设计深度超过 Screeps 的简单 GCL-upkeep 模型。

2. **Basis Points 全局一致**。从 Resource Ledger 到 API IDL 到 Balance Sheet，所有费率和比例均使用 bp/ppm 整数表示，无一处浮点数。这是经济系统确定性的关键保障。

3. **Resource Ledger 单入口架构严谨**。所有资源流动（LocalTransfer、GlobalDeposit/Withdraw、AlliedTransfer、PvEAward、RecycleRefund、BuildCost、SpawnCost、UpkeepDeduction、StorageTax）通过统一 Gateway 结算，消除多入口逃逸路径。TickTrace 归因格式（`(tick, source, target, resource_type, amount, operation, fee_paid)`）支持完整审计。

4. **PvE Budget 四维控制精妙**。Global/Zone/Player/Event 四层上限独立裁决，防止 NPC 产出压倒 PvP 经济。`max_pve_output_per_tick ≤ 世界再生总量 × 30%` 的全局约束确保 PvE 永远是补充而非主导。

5. **Allied Transfer Intercept 设计完整**。运输中拦截（R27 E-H1 最终设计）有明确的拦截窗口（150–200 tick）、成功率公式（base 60% + part bonus − escort penalty）、确定性 seed（Blake3）、三方通知和完整审计日志。这是博弈论视角下的优秀机制设计——为联盟经济引入了非平凡的战略维度。

6. **经济反馈循环设计周到**。经济仪表板（Web UI）+ MCP 经济查询 + 告警通知三通道覆盖人类和 AI 玩家。税率预警（30 tick 提前）、效率对标（vs 世界 P50）、净流入趋势线帮助玩家做出宏观决策而非仅微观操作。

---

## 4. CrossCheck — 需要跨方向检查

以下问题在我方向（Design & Economy）范围内无法独立裁决，需其他方向复核：

- **CX-1: [经济全赤字 → 安全性] → 建议 Security 检查**：若 Standard 模式经济为全状态净赤字（见 C1），富有玩家的储备优势被放大——他们用储备维持运营，而贫穷玩家在 free_upkeep 结束后迅速破产。这是否创造了「用储备碾压」的 griefing 向量？建议 Security 评估全赤字经济是否隐含 DoS 攻击面（富玩家可故意消耗新玩家的有限储备）。

- **CX-2: [Balance Sheet vs Growth Path 矛盾 → 系统] → 建议 Systems 检查**：Balance Sheet 显示全状态净赤字，Resource Ledger §2.3 声称「自维持」。两文档至少一个错误。建议 Systems reviewer 独立推导维护费公式 + 收入模型，判定哪一方正确，或指出缺失的收入源。

- **CX-3: [global_storage_capacity 示例 100k vs 1M → Technical Writer 检查**：gameplay.md 的 world.toml 示例中 `global_storage_capacity = 100000` 与默认值 1,000,000 差 10 倍（见 M1）。建议 Technical Writer 全量扫描所有 world.toml 示例中的数值与默认值的一致性。

- **CX-4: [special_param 为 float vs 全局定点数策略 → Systems 检查**：gameplay.md 行 1024 将 `special_param` 标为 `float`，与全局定点数策略冲突（见 L2）。建议 Systems reviewer 确认 `special_param` 的运行时类型——若确实是 f64，则违反了确定性合同；若实为 BasisPoints 的 u32，则文档标注错误。

- **CX-5: [维护费 deficit 惩罚链 → Gameplay 检查**：Resource Ledger §Empire Upkeep 定义 deficit 惩罚链：连续 3 tick deficit → 效率 −50%，连续 10 tick → age 加速 ×10。建议 Gameplay reviewer 验证此惩罚链与 Balance Sheet 的交互——在全赤字经济中，所有玩家是否终将触发惩罚链？若是，则惩罚链失去了作为「异常处理」的语义，变成了「常态」。