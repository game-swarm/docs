# Swarm R27 — Design & Economy 独立评审

**评审员**: rev-dsv4-design-economy (DeepSeek V4 Pro)
**评审范围**: 玩法完整性、经济模型平衡、World vs Arena 区分度、反雪球机制、玩家体验、UX 设计
**评审日期**: 2026-06-20

---

## Verdict

**CONDITIONAL_APPROVE**

经济模型架构扎实，反雪球体系完整且数学上自洽，World/Arena 双模式区分清晰。存在 2 个 High-severity 经济平衡问题和 1 个 High-severity 玩法完整性问题需在设计冻结前解决。无 Critical 阻断项。

---

## Strengths（亮点）

1. **经济闭环设计完整**：Faucet（Source 再生、PvE 掉落、starting_resources）↔ Sink（维护费、存储税、Spawn 成本、部署费）↔ Transfer/Lockup 的账本分类清晰，Resource Ledger 单入口架构消除逃逸路径。这是见过的最严谨的游戏经济账本设计之一。

2. **超线性维护费曲线数学自洽**：`upkeep = base_upkeep × rooms × (1 + rooms / room_soft_cap)` 的 O(n²) 趋势天然形成软上限，边际收益递减的证明路径完整。50 房间维护费是 1 房间的 ~273 倍，与收入增长的不匹配性正确验证。

3. **Controller age 维修硬上限 50%**：防止玩家堆叠 Controller 实现永久 drone 的设计精巧。相邻格仅 6 个 + Depot 排队形成物流拥挤决策，策略深度充足。

4. **soft_launch → First-Attack Shield → Soft PvP → Full PvP 四阶段渐进过渡**：这是 PvP 游戏中最完善的新手保护设计之一。Phase 1 全盾 50 tick + Phase 2 半盾 + 50% 伤害倍率的递进方案既保护新手又不永久隔离。

5. **累进存储税 + 本地隐匿性 + No Teleport 三重反垄断**：从经济、信息和物流三个维度同时打击囤积垄断，单一机制的旁路被其他维度覆盖。

6. **WASM-only 执行模型天然公平**：AI agent 和人类玩家同走 WASM 沙箱，不存在 McpPlayerExecutor 等差异化路径——这与设计议会此前纠正的 MCP 架构陷阱一致。

7. **Body part → age_modifier 系统**：TOUGH +100 延寿、ATTACK -80 折寿，将 drone 设计变成一个"攻防 vs 寿命"的 trade-off 问题，非平凡策略维度。

8. **Allied Transfer 严格受限**：2% 费 + 200 tick 延迟 + 500 tick 冷却 + 10,000/day cap + 100 tick 成员最低时长，防联盟经济滥用的多层约束完善。

---

## Issues（问题）

### G1 [High — 玩法完整性] 资源转运输中拦截机制未定义

**位置**: design/gameplay.md §2.2 "全局↔本地转换需物流运输"
**描述**: 文档声明 "转换期间资源处于'运输中'状态——可被敌方巡逻 drone 拦截（需 PvP 启用）"，但全设计文档未定义拦截的具体机制：拦截条件（同房间？相邻格？）、拦截结果（窃取？销毁？部分损失？）、拦截方需要什么 body part、被拦截方是否有防御手段（武装护送？）。

这不仅是 UX 问题——如果拦截机制未被定义，物流策略设计将缺失关键维度。运输路线规划、护航编队、Depot 选址等核心玩法依赖此机制的具体参数。

**建议**: 在 gameplay.md 或 resource-ledger.md 中定义 `InterceptTransfer` 机制：至少包括 range（建议相邻格）、body part 需求（建议 CARRY 或 Attack）、拦截成功率公式、被拦截资源的分配比例。

### G2 [High — 经济平衡] 收支平衡表全为负，缺乏正均衡点

**位置**: design/economy-balance-sheet.md §2
**描述**: 收支平衡表显示所有房间配置（1/5/20/50）均为净亏损：

```
1 房间: -30/tick
5 房间: -250/tick
20 房间: -1,940/tick
50 房间: -12,625/tick
```

这意味着 Standard 模式的 Vanilla 经济永远处于通缩状态。设计意图是"需要高效代码才能缩小缺口"和"免维护期过渡"，但：

- growth path 表（resource-ledger.md §2.3）声称 tick 2000+ 应 "✅ 自维持"，而 5 房间平衡表显示 -250/tick——矛盾
- 如果所有稳态都是亏损，则经济系统的长期演化方向是全体玩家资源归零，这不是"反雪球"而是"反所有人"
- 文档未定义"高效代码"带来的效率提升量化范围（Harvest 效率能从 1 unit/tick 提升到多少？上限是多少？）
- 缺乏一个"设计目标均衡点"——例如"在 RCL 4、3 房间、8 架 drone 的典型中玩家配置下，预期收支平衡"

**建议**: (a) 添加至少一个收支平衡或正盈余的参考配置；(b) 定义 Harvest 效率提升的上限和典型值，使"代码优化缩小缺口"可量化验证；(c) 说明初始资源和免维护期结束后，典型玩家在什么配置下应达到平衡。

### G3 [High — 经济模型] 无人机维护费在平衡表中建模不一致

**位置**: design/economy-balance-sheet.md §2.1-2.4
**描述**: 
- 1 房间平衡表：无 drone upkeep 行项
- 5 房间平衡表：无 drone upkeep 行项
- 20 房间平衡表：Drone spawn cost (avg 0.2/tick) = 40
- 50 房间平衡表：Drone upkeep = 1,000

Drone 维护费在 resource-ledger.md 中定义为 `UpkeepDeduction`（执行顺序第 1 步），但 economy-balance-sheet.md 只在 20 和 50 房间中计入，且名目不统一（"Drone spawn cost" vs "Drone upkeep"）。1 和 5 房间的 drone 维护费缺失使小规模经济看起来比实际更健康——如果 1 房间有 3 架 drone，每架 drone 维护费若为 5-10/tick，则实际净亏损会更大。

**建议**: 在所有平衡表配置中统一计入 drone upkeep，使用一致的命名和计算公式。

### G4 [Medium — 经济模型] global↔local 转换费率不对称但缺乏设计理由文档

**位置**: design/gameplay.md §2.2, specs/core/08-resource-ledger.md §2.1
**描述**: `global_deposit_fee = 100 bp (1%)` vs `global_withdraw_fee = 500 bp (5%)`，5 倍差距。round-trip 损失约 6%。设计意图推测是"鼓励本地物流、惩罚全局存储依赖"，但：(a) 文档未解释 5:1 不对称比率的设计理由；(b) 5% 提取费可能对中玩家过于惩罚——从全局提取 10000 资源支付 500 费用，尤其在需要紧急防御资源时。是否考虑过按提取量设计递减费率？

**建议**: 在 economy-balance-sheet.md 或 resource-ledger.md 中添加不对称费率的数学理由（如"5:1 比率使 round-trip 成本约等于 Empire Upkeep 在 3 房间时的日均扣除量"）。考虑紧急防御场景下的提取费减免机制（如 Controller 被攻击时的提取费减半）。

### G5 [Medium — 玩法完整性] Hack 夺取后的 Neutral drone 竞争窗口未定义

**位置**: design/gameplay.md §8 特殊攻击方式
**描述**: Hack 在 tick 5 成功后 drone 转为 Neutral（owner=0），5 tick 后自动恢复原 owner。在这 5 tick 窗口内：
- 第三方能否 Claim 该 Neutral drone？
- 如果能，Claim 和自动恢复的竞态如何裁决？
- Neutral drone 是否可被攻击（Attack/RangedAttack）？若可，HP 降至 0 后回收资源归谁？

当前文档只说明 Neutral 状态下"停止执行 WASM、不消耗 lifespan、不消耗 fuel、免疫再次 Hack"。这些空缺使 Hack 的博弈深度不完整。

**建议**: 补充 Neutral 状态下的完整交互规则：Claim 优先级、攻击许可、死亡归属。

### G6 [Medium — UX] AI agent push event 传输通道与 MCP transport 不一致

**位置**: specs/gameplay/06-feedback-loop.md §2.4, specs/reference/api-registry.md §3.5
**描述**: feedback-loop.md 声明部署后引擎推送 "first_tick_executed" 事件，AI 无需 polling。但 api-registry.md §3.5 定义 Agent WS 为 "每消息 seq + MAC (ed25519)" 的安全 WebSocket 通道，而 MCP 工具（§3.2-3.3）均通过 HTTP/JSON-RPC 调用。两种传输通道的事件推送机制未在文档中统一——AI agent 是通过 MCP over HTTP 订阅事件，还是需要维护独立的 WebSocket 连接？feedback-loop 的 "无需 polling" 依赖于确定的 push 通道。

**建议**: 在 feedback-loop.md 或 api-registry.md 中明确 MCP event subscription 的传输机制，与 §3.5 的 Agent WS 定义对齐或区分。

### G7 [Low — 博弈论] Overload 多攻击者协同压制缺乏累积上限

**位置**: design/gameplay.md §8 Overload
**描述**: Overload 的单次效果是 -500k fuel，下限 MAX_FUEL×0.2（即 2M/10M），目标全局冷却 50 tick。但多攻击者协同可以：玩家 A 在 tick 0 攻击 → 冷却 50 tick；玩家 B 在 tick 5 攻击 → 冷却 50 tick；玩家 C 在 tick 10 攻击……如果 10 个玩家协调，可在 50 tick 内将目标 fuel 从 10M 压制到 2M 下限并持续维持。fuel 恢复速率是 fuel_budget/1000 per tick（即 10k/tick at max）——从 2M 恢复到 10M 需要 ~800 tick，远慢于压制速率。这使协同 Overload 成为支配性压制策略——目标玩家无法执行任何 WASM 计算。

**建议**: 考虑添加 per-player OverloadPressure 累积上限（如单个目标在 100 tick 内最多被 Overload 3 次，不限来源），或使 Overload 效果对已处于低 fuel 状态的目标递减。

### G8 [Low — 经济模型] body part spawn cost 中 Claim 600 Energy vs Hack 1000 Energy 的性价比不对称

**位置**: design/gameplay.md §2.2 body part costs + §8 Hack cost
**描述**: 生成 1 个 Claim body part = 600 Energy（一次性），执行 Hack = 1000 Energy/次（每 200 tick 冷却）。一个 [MOVE, CLAIM] 的 2-part drone 总 spawn 成本 = 650 Energy，可执行多次 Hack。如果 Hack 成功夺取敌方高价值 drone（如 [MOVE, MOVE, WORK, WORK, CARRY, CARRY, ATTACK, ATTACK, TOUGH, TOUGH] 的 10-part drone，spawn 成本 ~2,400 Energy），投入产出比极高。需要考虑 Hack 成功率与目标 drone body 组成的关系（目前文档声明"命中判定取决于 body part 数量与目标防御的差值"，但未给公式）。

**建议**: 定义 Hack 命中判定的具体公式，确保高价值目标更难被 Hack。或使 Hack 的资源消耗与被 Hack 目标的 body cost 成比例。

### E1 [Low — 经济治理] PoW 注册成本过低可能不足以防刷号

**位置**: design/gameplay.md §2.2 PoW 经济治理
**描述**: `difficulty_bits = 24` 的 P95 WASM 耗时 1.5s，每 1000 账号攻击成本 ~$0.10。虽然 new_player_transfer_lock（500 tick）和 same_origin_account_group_quota（5）提供额外防护，但 $0.10/千号的攻击成本对刷号农场（用于绕过 room drone cap 或实施协同 Overload 压制）仍然过低。对于 World 持久模式的长期经济，刷号 ROI 可能极高。

**建议**: 评估是否需要将 default difficulty_bits 提升至 26-28（P95 WASM 耗时 4-6s），或使 difficulty 随账号创建频率自适应调整的上限更高（当前 max=32）。

---

## CrossCheck — 需要跨方向检查

- **CX1**: transfer 运输中拦截机制的缺失可能引入安全攻击面（如通过拦截实现资源复制 bug）→ 建议 **Security 检查** transfer 状态机的完整性，特别是"运输中"资源的 ownership 归属和并发原子性

- **CX2**: Fabricate（敌方 drone → 己方建筑）的转化目标结构类型未指定——如果转化出的建筑是 Spawn，会产生领土主权问题 → 建议 **Architect 检查** Fabricate handler 的 ECS 组件转换逻辑和 Room Controller 交互

- **CX3**: Overload 多攻击者协同压制问题 → 建议 **Security 检查** fuel budget 恢复模型的抗 DoS 韧性，验证是否存在 3+ 攻击者可持续使目标无法执行 WASM 的协同向量

- **CX4**: Neutral drone 状态（Hack 夺取后）的完整交互规则缺失 → 建议 **Architect 检查** ECS ownership 状态机的竞态条件，特别是 Claim vs 自动恢复 vs 攻击三种操作的执行优先级

- **CX5**: `swarm_simulate` 和 `swarm_dry_run` 的 fork 隔离声明充分，但 simulate 使用独立 RNG seed `hash(authoritative_seed + "simulate_preview" + drone_id + tick)` — 此 seed 可从 simulation 输出反推 authoritative RNG 状态吗？→ 建议 **Security 检查** RNG seed derivation 的信息泄漏风险

- **CX6**: 经济平衡表全负的问题可能与 maintenance formula 的 `room_soft_cap = 10` 参数设置有关——此参数是否有跨模块影响（如 engine.md 中的 room cap 定义是否与此一致）？→ 建议 **Architect 检查** room_soft_cap 在 engine/tick/rule 各层的统一定义

---

## Resource Model Issues（资源闭环诊断）

### 闭环完整性: PASS（基本闭合）

```
Faucets:  Source 再生 + PvE 掉落 + starting_resources + Controller income
Sinks:    维护费 + 存储税 + Spawn 成本 + 部署费 + global↔local 转换损耗
Transfers: drone 间本地转移（零和）
Lockups:   建筑建造成本（可回收 50%）+ Controller 升级（永久锁定）
Unlocks:   drone 回收 (10-50%) + 建筑摧毁 (50%)
```

**诊断**: 所有资源的 source 和 sink 均有定义。Faucet 总量受 PvE global cap（≤ 世界再生 × 30%）约束。长期来看 Sink > Faucet（平衡表全负），这形成软性 deflationary pressure——设计意图是限制帝国无限扩张，但需验证并非所有玩家规模都亏损（见 G2）。

### 闭环缺口: 建筑摧毁的回收资源未在平衡表建模

平衡表未计入建筑摧毁的资源回收（Unlock）。在大规模 PvP 场景中，建筑摧毁回收可能成为显著 Faucet（重新流入经济）。如果 50 房间的大帝国被攻陷 10 个房间，建筑回收可能瞬间注入大量资源——这与"反雪球"目标可能冲突（溃败者反而获得资源注入）。

### 闭环缺口: Drone 死亡不产生资源回收

当前 drone 死亡（非 Recycle）不退还任何资源——body cost 完全沉没。这与建筑摧毁 50% 回收不对称。考虑是否应让 drone 死亡产生残骸（Wreckage），可被 CARRY drone 回收部分资源——这会增加战术深度（胜方打扫战场获取经济优势）但可能增强雪球效应。至少应在设计文档中明确"drone 死亡不回收"是刻意设计决策而非遗漏。

---

## Game Theory Gaps（博弈论缺口）

1. **Drone 消息协议的不可信模型** (§2.9) 是优秀的博弈论设计——peer-to-peer 交换无引擎担保，玩家必须自建声誉系统。但缺少对 Sybil 攻击的讨论：同一玩家用多个 drone 身份发送虚假 offer，探测其他玩家的策略逻辑。

2. **Hack 博弈** (5 tick 渐进控制) 的 counter-play 空间充足（Disrupt 打断、Fortify 净化），但反制成本不对称——Disrupt 100 Energy vs Hack 1000 Energy，防守方明显有利。这是否是设计意图？

3. **Allied 系统中的叛变冷却 24h** 防止"结盟→偷袭→重结盟"循环，但未防止"结盟→获取 intel（友方 drone 位置）→在冷却内用非 allied 小号攻击"。Federation identity 仅 identity-only，不防多号。

4. **First-Attack Shield** 的 per-attacker scope 意味着多攻击者轮流攻击可以耗尽盾牌覆盖——Phase 1 中 A 攻击触发盾牌 → B 攻击无盾牌 → 伤害生效。这个设计可能导致老玩家用多个 drone 分时攻击绕过保护。

---

## 总结

Swarm R27 的经济模型是该类型游戏（编程 MMO RTS）中设计最严谨的方案之一。单入口 Resource Ledger + 定点数费率 + 确定性执行顺序构成了可审计的经济基础。反雪球体系通过维护费（O(n²)）+ 累进存储税 + Controller age 上限 + room drone cap 四层机制覆盖，且各层之间有互补性（绕过一层会被另一层捕获）。

**冻结前必须解决的三个 High 问题**:
1. G1: 运输中拦截机制必须完整定义（影响物流玩法核心）
2. G2: 收支平衡表需包含至少一个正均衡配置，或明确说明"代码效率提升"的可量化范围
3. G3: 平衡表中 drone upkeep 建模必须统一

如果 G2 的本质是"设计意图为所有配置都亏损，让玩家竞争有限资源"，这可以接受——但需在文档中明确声明，并给出 Faucet/Sink 长期演化的稳态分析（如"在总玩家数 N、平均效率 E 的条件下，稳态人均资源量收敛于 X"）。

**Verdict: CONDITIONAL_APPROVE** — 三个 High 问题解决后可直接进入 Phase 2 跨方向评审。