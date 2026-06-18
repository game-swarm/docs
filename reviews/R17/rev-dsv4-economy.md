# R17 Economy Review — DeepSeek V4 Pro

> 评审视角：反雪球机制分析、博弈论均衡验证、资源流数学建模、权威单源闭合性验证
> 
> 只读文档子集：design/{README,gameplay,modes,economy-balance-sheet}.md + specs/{reference/{api-registry,game_api.idl.yaml}, gameplay/{06-feedback-loop,08-api-idl}, core/08-resource-ledger}.md

---

## 1. Verdict

**CONDITIONAL_APPROVE** — 反雪球机制数学上成立，但权威单源尚未真正闭合。发现 1 Critical + 2 High + 4 Medium 问题需要修复后才能 APPROVE。

---

## 2. 发现问题

### D1 [Critical] Recycle 退还公式：双重权威源冲突

**涉及文档**：
- `specs/reference/game_api.idl.yaml` (机器可读权威源, api-registry 声明 "冲突时以 YAML 为准")：`refund: registry.body_cost(body) * 0.5` — **固定 50%**
- `specs/core/08-resource-ledger.md` §6 (声明 "所有收支计算的单一权威源")：`recycle_refund = max(body_cost * 10%, remaining_lifespan / total_lifespan * 50%)` — **按剩余寿命比例 10%–50%**

两份文档均声明自身为单一权威源，但给出互斥公式。`api-registry.md` 声称 YAML 优先，`resource-ledger.md` 声称自身优先——两者之间无优先级仲裁机制。

**经济影响**：
- 若固定 50%：spawn → immediate Recycle 套利路径存在。玩家可无限 spawn+recycle 测试 body 组合，只损失 50% 成本。Tutorial 世界前 500 tick 甚至 100% 退还——理论上可无限 loop spawn→recycle 刷 body 经验。
- 若比例 10%–50%：接近死亡的 drone 回收仅 10%，消除套利。但此公式与 IDL 代码生成不一致——SDK 生成的 `Recycle` validator 将使用固定 50%，与实际执行逻辑不符。

**博弈论角度**：固定 50% 下最优策略包含「到期前回收所有 drone」——使 lifespan 约束形同虚设（玩家在 drone 将死前回收，始终拿回 50%）。比例制下回收时机有实际 trade-off：早回收多退但损失剩余寿命产能，晚回收少退但充分利用寿命。

**修复建议**：在 `game_api.idl.yaml` 的 Recycle 条目中补充 `refund` 的动态公式注释，或在 resource-ledger 和 IDL YAML 之间建立明确的优先级声明（如"resource-ledger 为数值权威，IDL 中 refund 字段为默认基线值"）。

---

### D2 [High] 存储税双重定义：flat rate vs tiered

**涉及文档**：
- `specs/core/08-resource-ledger.md` §2 费率表：`storage_tax_rate = 10 bp/tick` — **统一固定税率**
- `design/gameplay.md` §8 累进存储税：`global_storage_tax_tiers = [(30%,0bp), (60%,1bp), (85%,5bp), (100%,20bp)]` — **阶梯累进税率**
- `design/economy-balance-sheet.md` §6：声明 "存储税权威源见 resource-ledger §StorageTax"——但 resource-ledger 中不存在独立的 §StorageTax 章节，只有 §2 费率表中的单行 `storage_tax_rate`

**数值差异**：
| 存储利用率 | Tiered (gameplay) | Flat 10bp (resource-ledger) |
|-----------|-------------------|---------------------------|
| 0-30% | 0 bp/tick | 10 bp/tick |
| 60% | 1 bp/tick | 10 bp/tick |
| 85% | 5 bp/tick | 10 bp/tick |
| 100% | 20 bp/tick | 10 bp/tick |

两种税制产生完全不同的均衡点。Tiered 税制在 30% 以下免税鼓励适度存储，85%+ 高税率压制囤积——符合 Anti-Dominant-Strategy 设计意图。Flat 10bp 对所有存储量统一征税，不区分策略性存储与垄断性囤积。

**修复建议**：将 tiered 税率表移入 resource-ledger.md 作为 §StorageTax 独立章节（economy-balance-sheet 已正确引用此位置），并从 §2 费率表中移除重复的 flat `storage_tax_rate`。

---

### D3 [High] 全局传输延迟数值不一致

**涉及文档**：
- `specs/core/08-resource-ledger.md` §2：`global_transfer_delay = 100 tick`（标注 "全局提取延迟"）
- `design/gameplay.md` §8：`transfer_to_global_time = 10 tick`，`transfer_from_global_time = 5 tick`

**差异**：全局→本地提取延迟在 resource-ledger 为 100 tick，在 gameplay 为 5 tick，相差 **20 倍**。本地→全局存入延迟在 resource-ledger 中未有独立参数（仅有统一 `global_transfer_delay`），在 gameplay 为 10 tick。

此差异直接影响「全局存储作为战斗即时补给」的可行性评估。100 tick 延迟（World 模式约 5 分钟 @3s/tick）使全局存储完全不可用于战术补给；5 tick 延迟（约 15 秒）则可能在拉锯战中发挥作用。economy-balance-sheet 中的「No Teleport + 物流成本」论述依赖此参数。

**修复建议**：在 resource-ledger 中拆分为 `global_deposit_delay` 和 `global_withdraw_delay` 两个独立参数，与 gameplay.md 对齐数值。或统一使用 resource-ledger 数值并更新 gameplay.md。

---

### D4 [Medium] Controller age 维修上限公式语义不清

**位置**：`design/gameplay.md` §8 "Controller 续期硬上限"

**公式**：
```
max(0, age + 1 - min(0.5, controller_count * 0.5))
```

**分析**：
- `controller_count = 1`：`min(0.5, 0.5) = 0.5`，维修上限 = 0.5/tick
- `controller_count = 2`：`min(0.5, 1.0) = 0.5`，维修上限 = 0.5/tick
- `controller_count ≥ 1`：恒为 0.5

`controller_count * 0.5` 子表达式在 controller_count ≥ 1 时被 `min(0.5, ...)` 完全覆盖——多 Controller 不能增加维修上限。文档说明中「无论拥有多少个 Controller」正确描述了此行为，但公式中保留 `controller_count * 0.5` 造成阅读误导（读者可能以为多 Controller 有收益）。

**建议**：简化为 `max(0, age + 1 - 0.5)` 或明确注释此限制的设计理由（防止 Controller 堆叠实现永久 drone）。

---

### D5 [Medium] same_origin_account_group_quota 未进入 Resource Ledger

**位置**：`design/gameplay.md` §8 新玩家资源门

参数 `same_origin_account_group_quota = 5` 是重要的经济反滥用机制（限制同 IP/device fingerprint 账号组的资源配额），但未出现在 `specs/core/08-resource-ledger.md` 的任何费率表或约束定义中。

作为资源维度的限制参数，应在 Resource Ledger 中有权威定义。当前仅 gameplay.md 声明此参数，不符合「经济参数以 resource-ledger 为单一权威源」的设计原则。

---

### D6 [Medium] PvE Budget 上限为相对值非绝对值

**位置**：`specs/core/08-resource-ledger.md` §3

PvE 全球产出上限定义为「世界再生总量 × 30%」——是相对值而非绝对值。当世界再生总量因 `source_regeneration_rate` 配置或世界规模增大时，PvE 产出同步放大。这可能导致高再生率世界中 PvE 成为主导 Faucet，超越 Source 采集的战略价值。

**建议**：增加可选的绝对上限 `max_pve_output_per_tick_absolute`，与相对上限取较小值。当前 `design/modes.md` §9.0 中提到 `max_pve_output_per_tick` 但未在 resource-ledger 中正式定义。

---

### D7 [Medium] 经济报表全场景净亏损但未标注均衡策略

**位置**：`design/economy-balance-sheet.md` §2

所有 4 个场景 (1/5/20/50 房间) 均显示净亏损。阅读者可能误判为「经济系统不可持续」。实际设计意图是迫使玩家通过代码优化提升效率——但报表中未展示「优化后可达均衡」的对比场景，也未给出典型均衡点（如「8 房间 Standard 模式，高效 Harvester 代码可达收支平衡」）。

**建议**：增加一列「优化后」场景或标注均衡房间数估算，避免读者误读为系统级缺陷。

---

## 3. 亮点

1. **反雪球维护费曲线数学坚实**：`upkeep = base × rooms × (1 + rooms/cap)` 在 50 房间下产生 40 倍于 5 房间的维护费（vs 线性 10 倍），O(n²) 趋势的 anti-snowball 效果得到数值验证。economy-balance-sheet 的 4 场景验证逻辑完整。

2. **存储税均衡证明严谨**：§6 的均衡点分析——从 `τ(0.30)=0` 到 `τ(1.00)=20bp=2000/tick`——完整证明了无硬 cap 条件下也能形成自然天花板。这是少见的在设计文档中给出形式化均衡证明的做法。

3. **Resource Ledger 执行顺序确定性**：10 步执行顺序（UpkeepDeduction → StorageTax → ... → RecycleRefund）保证了每 tick 资源变动的可重复性。每笔操作记录到 TickTrace 的 `(tick, source, target, resource_type, amount, operation, fee_paid)` 六元组——满足完全可审计性。

4. **Faucet/Sink/Lockup/Transfer 四分类法**：将每条经济规则按流向分类，清晰展示了世界资源总量的守恒约束。此分类法(`design/gameplay.md` §8 Vanilla 经济分类账) 是设计文档中的优秀实践。

5. **No Teleport 物流模型**：全局↔本地转换的延迟 + 费用设计，确保了「战斗即时补给不可行」——这是一项非平凡的策略约束，防止富裕玩家通过全局存储碾压前线。

6. **新玩家经济门控完整**：transfer lock、PvE drop 绑定、同源配额——三个维度同时作用，系统性防止刷号/小号经济滥用。Tutorial 世界默认关闭所有限制的设计考虑周全。

---

## 4. CrossCheck

### 4.1 权威单源闭合性矩阵

| 经济参数 | api-registry (YAML) | resource-ledger | gameplay.md | economy-balance-sheet | 闭合状态 |
|---------|:---:|:---:|:---:|:---:|:---:|
| **Recycle 退还公式** | 固定 50% | 比例 10-50% | 固定 50% | 引用 RL | ❌ CRITICAL |
| **存储税税率** | — | flat 10bp | tiered 4级 | tiered 4级 | ❌ HIGH |
| **全局传输延迟** | — | 100 tick (单一) | 10/5 tick (分离) | 引用 RL | ❌ HIGH |
| empire upkeep 公式 | — | O(n²) | O(n²) | O(n²) | ✅ |
| body part costs | — | — | 8种成本 | 引用 RL | ✅ |
| 全局↔本地费率 (1%/5%) | — | 100/500 bp | 0.01/0.05 | 引用 RL | ✅ |
| new_player_transfer_lock | — | 500 tick | 500 tick | 500 tick (modes) | ✅ |
| same_origin_quota | — | 缺失 | 5 | — | ⚠️ MEDIUM |
| PvE budget cap | — | 30% 相对值 | 30% (modes) | — | ⚠️ MEDIUM |
| 全局存储容量 1M | ✅ | ✅ | ✅ | ✅ | ✅ |

### 4.2 Nash 均衡分析

**Empire Upkeep 均衡**：
维护费 O(n²) 增长 vs 收入 O(n) 增长（新增房间的 Source 产出线性增长但维护费超线性增长），必然存在一个 `rooms*` 使得 `income(rooms*) = upkeep(rooms*)`。此均衡点取决于玩家代码效率——高效应玩家的 `rooms*` 更大，形成「代码能力 → 可维持帝国规模」的 skill-based 约束。数学上满足纳什均衡存在性。

**存储税均衡**（tiered 版本）：
在 tiered 税制下，理性玩家的存储量 ≤ 85% 容量（边际税率 20bp > Controller passive income）。超过此点后囤积是严格劣势策略——每个理性玩家独立选择 ≤85%，构成 Nash 均衡。

**Recycle 策略均衡**（当前冲突下）：
- 固定 50%：spawn→recycle 始终损失 50%，但无时机差异。最优策略是「在 drone 将死前回收」→ 与 lifespan 设计意图矛盾。
- 比例 10-50%：存在回收时机 trade-off。寿命 100% 时回收得 50%，寿命 20% 时回收得 10%。最优策略取决于「剩余寿命预期产出 vs 回收退还差」。

**多资源通胀风险**：
若服主配置多种资源且各资源独立定义 Faucet/Sink，需确保每种资源的净流量可控。当前文档中仅 Energy 有完整的 Faucet/Sink 闭环验证；Crystal/Gas 等扩展资源只有成本定义（body part 可选消耗、建筑可选消耗），缺少独立的 Faucet 定义和均衡验证。

### 4.3 World vs Arena 经济差异

| 维度 | World | Arena | 验证状态 |
|------|-------|-------|:---:|
| empire upkeep | 默认启用 | N/A（短对局） | ✅ |
| 存储税 | tiered | 免税 | ✅ |
| 初始资源 | 标准起始包 | 对称初始 (10K Energy + 5K Crystal) | ✅ |
| 物流模式 | B (轻物流) | 默认 A (无物流) | ✅ |
| 代码部署费 | 默认 0 | 比赛开始锁定，赛中不可部署 | ✅ |
| PvE | 常驻生态层 | PvE Challenge 隔离沙盒 | ✅ |

Arena 模式经济设计干净——对称起点 + 免税 + 代码锁定 + 固定时长，变量仅为玩家算法。无经济层面的套利路径。

---

## 5. 总结

R17 文档集在**反雪球机制设计**和**经济分类学**上达到高质量水平。empire upkeep O(n²) 维护费 + tiered 存储税 + No Teleport 物流三重约束构成了有效的 anti-snowball 体系。

**但权威单源闭合未达成**：3 个核心经济参数（Recycle 公式、存储税结构、全局传输延迟）在声称"单一权威源"的文档间存在不可调和冲突。`api-registry.md` 与 `resource-ledger.md` 各自声明自身为终极权威却互不引用优先级——这正是 R15-R16 多轮修复后仍残留的架构性问题。

**修复优先级**：
1. D1 (Recycle 公式) → 定义权威优先级并统一公式
2. D2 (存储税) → 将 tiered 定义移入 resource-ledger
3. D3 (传输延迟) → 拆分参数并对齐数值
4. D4-D7 → 文档澄清，不阻塞实现

修复 D1-D3 后可升级为 APPROVE。
