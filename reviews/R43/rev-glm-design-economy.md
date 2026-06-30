# R43 Phase 1 评审报告 — 设计与经济 (glm)

> 评审范围：design/README, gameplay, modes, interface, economy-balance-sheet；specs/reference/api-registry, gameplay/api-idl, gameplay/feedback-loop, gameplay/PLAYTEST-GATED, core/resource-ledger, core/snapshot-contract
>
> 评审视角：设计与经济——经济模型一致性、参数权威性、收支平衡表数值闭环、跨文档经济参数可追溯性、接口经济直觉性。

## 1. Verdict

**CONDITIONAL_APPROVE**

经济架构的核心设计（Resource Ledger 单一入口、Transfer Gateway、定点费率、确定性执行顺序）是扎实的，无根本性缺陷。但 economy-balance-sheet.md 存在多处存储税计算算术错误和会计记账逻辑问题——这是本方向的核心交付物，数值闭环验证必须准确。这些问题不阻塞设计冻结（曲线语义已声明为 illustrative，playtest-gated 可接受参数偏差），但当前文档中的数学错误必须修复后才能认定为可靠的审批。

---

## 2. 发现的问题

### 2.1 [High] Economy Balance Sheet §2.1 记账逻辑错误 — free_upkeep 被计为收入

**文件**: `design/economy-balance-sheet.md` §2.1 (2.1 Standard 模式 — 1 房间)

**问题**: §2.1 将 "free_upkeep 覆盖 +55" 列为收入项，总收入 = 77，净盈余 = +77。但 free_upkeep 在 Resource Ledger §2.3 的语义是 "UpkeepDeduction 跳过" — 这是费用豁免，不是系统注入收入。将豁免的维护费同时计为收入且将支出列为 0，构成双计算。

正确的记账应为：收入 = 22 (Source 20 + Controller 2)，维护费 = 0 (豁免期内)，净盈余 = +22。

§2.1 正文下方的说明也证实了这一点："基础收入 22/tick...free_upkeep 结束后维护费恢复（55/tick）→ 净亏损 -33/tick"（22 - 55 = -33）。§2.7 汇总表也正确列出了 1 房间收入 22、维护费 0。但 §2.1 明细表的 "总收入 77" 和 "净盈余 +77" 与之矛盾。

**影响**: 1 房间净盈余被高估 3.5 倍（77 vs 22）。free_upkeep 期的实际盈余直接影响 PG-1 早期经济曲线验证，错误的初始值会导致 playtest 校准基准偏移。

**修复建议**: 将 §2.1 表格改为：总收入 22（移除 free_upkeep 行或改为注释行），总支出 0（free_upkeep 豁免），净盈余 +22。保留下方说明文字关于 free_upkeep 价值的解释。

---

### 2.2 [High] Economy Balance Sheet 存储税算术错误 — 20 房间税率少算 50%

**文件**: `design/economy-balance-sheet.md` §2.5 + §2.7 汇总表 (20 房间行)

**问题**: 20 房间行声明 storage_capacity=4,000,000, stored_total=2,880,000 (72%)，存储税 = 180。按 Resource Ledger §2.2 tiered 公式重算：

- Tier 1 (30-60%): taxable = min(2,880,000 - 1,200,000, 1,200,000) = **1,200,000**; tax = 1,200,000 × 1bp / 10000 = 120
- Tier 2 (60-85%): taxable = min(2,880,000 - 2,400,000, 1,000,000) = **480,000**; tax = 480,000 × 5bp / 10000 = 240
- **正确存储税 = 360**，而非表格声称的 180。

表格中的中间值 (tier 1 taxable=1,200,000; tier 2 taxable=480,000) 是正确的，但最终结果 180 是错误的（恰好等于正确值的一半，疑似额外除以 2）。

§2.7 汇总表 20 房间行同样列出 180，错误被复制。

**影响**: 20 房间场景的存储税被低估 50%，导致总支出 (3,220) 的准确性受损，间接影响 "20 房边际收益递减" 这一核心 anti-snowball 论证。

**修复建议**: 将 §2.5 和 §2.7 的 20 房间存储税从 180 修正为 360，相应更新总支出和净流量。

---

### 2.3 [High] Economy Balance Sheet 存储税中间值与结果不一致 — 10 房间与 50 房间

**文件**: `design/economy-balance-sheet.md` §2.4, §2.6, §2.7

**问题**:

**10 房间 (§2.4)**: 声明 storage_capacity=3,000,000, stored_total=1,650,000 (55%)，存储税 = 75。公式文本写 "tier 1 taxable=900,000; tier 2 taxable=750,000"，但实际 55% 仅落在 Tier 1 区间：
- Tier 1 (30-60%): taxable = min(1,650,000 - 900,000, 900,000) = **750,000**; tax = 75
- Tier 2: 未达 60%，taxable = 0

公式文本的 "tier 1 taxable=900,000; tier 2 taxable=750,000" 是错误的（tier 2 根本未触发），但最终结果 75 恰好正确。中间步骤与结果矛盾。

**50 房间 (§2.6)**: 声明 storage_capacity=3,000,000, stored_total=2,700,000 (90%)，存储税 = 765。公式文本写 "tier 3 taxable=450,000"，但实际 90% 仅深入 Tier 3 区间 5%：
- Tier 3 (85-100%): taxable = min(2,700,000 - 2,550,000, 450,000) = **150,000**; tax = 150,000 × 20bp / 10000 = 300

公式文本的 "tier 3 taxable=450,000" 是错误的（应是 150,000），但最终结果 765 恰好由 150,000 算出，结果正确。中间步骤与结果矛盾。

**影响**: 多个场景的存储税中间计算步骤与最终结果不一致。读者无法按公式文本重现结果。对于依赖 balance sheet 验证经济模型的 reviewer 和实现者，这损害了文档的可审计性。

**修复建议**: 修正所有场景的中间 taxable 值以匹配实际计算，确保公式文本每一步可直接验证。建议在 CI 中加入一个简单的 Python script 对 §2.7 汇总表逐行重算存储税做 diff check。

---

### 2.4 [Medium] storage_capacity 值在 balance sheet 中不一致且偏离 Resource Ledger 默认值

**文件**: `design/economy-balance-sheet.md` §2.7 汇总表

**问题**: 汇总表 storage_capacity 列：
- 1/2/3/5 房间: 1,000,000
- 10 房间: 3,000,000
- 20 房间: 4,000,000
- 50 房间: 3,000,000

两个问题：

1. Resource Ledger §2.1 和 api-registry §5.7 均将 `global_storage_capacity` 默认值设为 1,000,000/player。10/20/50 房间使用 3M/4M/3M 却无任何说明这些是 world.toml 覆盖值还是排版错误。
2. 容量轨迹 1M → 3M → 4M → 3M 非单调——50 房间的容量 (3M) 低于 20 房间 (4M)，这在逻辑上不合理（更多房间不应导致更小的存储容量）。

**影响**: 存储税计算依赖 storage_capacity，错误的容量值即使税率公式正确也会导致错误结果。非单调轨迹使 reader 怀疑整个 50 房间行的数据可靠性。

**修复建议**: 要么统一使用 1,000,000/player 默认值（最简单，且与权威源一致），要么明确声明大房间帝国使用了 world.toml 提高的 capacity 作为 illustrative scenario，并保持单调递增。

---

### 2.5 [Medium] 50 房间行的 "Drone upkeep" 类别未定义且跨场景不一致

**文件**: `design/economy-balance-sheet.md` §2.5 (20 房间) vs §2.6 (50 房间)

**问题**:
- 20 房间支出包含 "Drone spawn cost (avg 0.2/tick) = 40"——以 spawn 成本分摊到 tick。
- 50 房间支出包含 "Drone upkeep = 1,000"——以 drone 维护费形式。

两个场景使用了不同的支出类别标签 (spawn cost vs upkeep)，且 50 房间的 "Drone upkeep" 1000 单位/tick 缺少任何计算来源。Resource Ledger §2.1 的 Empire Upkeep 公式 `upkeep = base_upkeep × rooms × (1 + rooms / room_soft_cap)` 是按 rooms 计算的，不包含 per-drone 维护费分量。§2.3 提到 "前 N 个 drone 免维护费" 暗示 drone 有独立维护费，但 Resource Ledger 从未定义 per-drone 维护费费率公式。

**影响**: balance sheet 支出侧使用了一个 Resource Ledger 未定义的经济参数 (per-drone upkeep)，且未在所有场景统一应用。读者无法追溯 1,000 这个数字的来源。

**修复建议**: 要么在 Resource Ledger §2 中明确定义 per-drone 维护费公式并在所有 balance sheet 场景统一应用，要么移除 50 房间的 "Drone upkeep" 行，将所有 drone 相关开销统一归入 Empire Upkeep 或 Spawn Cost 类别。

---

### 2.6 [Medium] MIN_LIFESPAN 声称权威源在 Resource Ledger §2 但未定义

**文件**: `design/gameplay.md` 第 98 行

**问题**: gameplay.md 声明 "MIN_LIFESPAN 默认 100 tick（world.toml 可配置），防止 body part 配置出负数 lifespan" 并标注 "MIN_LIFESPAN 权威值见 Resource Ledger §2 统一参数表"。

但 `specs/core/resource-ledger.md` §2.1 统一参数表不包含 MIN_LIFESPAN、BASE_AGE、drone_lifespan 或任何 age-related 参数。§2.1 只有 Global Transfer、Allied Transfer、Storage Tax、Recycle、New Player Gate 五个分区。

**影响**: gameplay.md 的 drone 生命周期公式 `age_max = max(MIN_LIFESPAN, BASE_AGE + sum(age_modifier))` 中，MIN_LIFESPAN 和 BASE_AGE 均无权威定义。drone lifespan 是经济系统的重要组成部分（影响 Recycle refund 和 spawn 成本回收周期），缺失权威值会造成实现分叉。

**修复建议**: 在 Resource Ledger §2.1 新增 Drone Lifespan 分区，定义 MIN_LIFESPAN (100)、BASE_AGE (1500) 等权威参数；或在 gameplay.md 中移除对 Resource Ledger 的引用声明，改为本文件内定义。

---

### 2.7 [Medium] Drone 间消息机制 (gameplay §2.9) 未反映在 IDL tick() 合约中

**文件**: `design/gameplay.md` §2.9 vs `specs/gameplay/api-idl.md` §2

**问题**: gameplay.md §2.9 定义了 `tick()` 可返回 `Message[]` 的 drone 间消息机制——`TickResult = { commands: Command[], messages: Message[] }`。消息系统支持 peer-to-peer 资源交换提议，具有经济含义（非正式资源转移通道）。

但 api-idl.md §2 的 tick() 合约定义为：`params: [snapshot_ptr, snapshot_len, result_ptr]`, `returns: i32` (result_ptr points to `{ ptr, len }` containing **CommandIntent[]** JSON)。IDL 中 tick() 的返回类型只有 CommandIntent[]，没有 messages 字段的 schema 定义。

**影响**: 一个具有经济影响的功能 (peer-to-peer 资源交换) 在行为层 (gameplay) 有完整设计，但在接口合约层 (IDL) 缺失。如果按 IDL 实现，消息系统不存在；如果按 gameplay 实现，IDL 需要更新。这是设计-合约层不同步。

**修复建议**: 在 api-idl.md §2 的 tick() export 中明确 TickResult 包含 messages 字段，或声明消息系统通过独立 host function / CommandAction 实现。同时明确消息系统是否参与 Resource Ledger 审计（当前 §2.9 说 "引擎不校验 payload 语义"，但资源交换如果不走 Transfer Gateway 可能绕过 Resource Ledger §1 "单一入口" 原则）。

---

### 2.8 [Low] `global_storage_public` 标记 "（计划中）" 违反 设计即终态 原则

**文件**: `design/gameplay.md` §2.2 全局存储反制机制表格

**问题**: 表格中 `global_storage_public` 的说明列为 "（计划中）全局存储是否完全公开"。AGENTS.md 明确禁止使用延期词（future/deferred/以后/远期），"（计划中）" 属于同类。

**影响**: 该字段要么是当前设计的一个具体配置参数（有默认值和无歧义语义），要么不应列出。"计划中" 使该字段处于未裁决状态。

**修复建议**: 移除 "（计划中）" 标注。如果该参数当前不实现，应完全从表中移除（可记入 RFC）；如果保留，给出具体默认语义。

---

### 2.9 [Low] Allied Transfer daily_cap 在 balance sheet 中只列 floor 值

**文件**: `design/economy-balance-sheet.md` §3 模式差异表

**问题**: §3 表格列出 Standard 模式 `allied_daily_cap` = 10000。但 Resource Ledger §2.1 公式为 `max(10,000, receiver_gcl × 20,000) × allied_daily_cap_world_multiplier / 100`。10000 仅是公式的下限 (floor)，对任何 GCL ≥ 1 的接收方，实际 cap = 20,000 × GCL。将 floor 值列为代表性数值具有误导性。

**影响**: 轻微——读者可能误以为 Standard 联盟转移上限固定为 10,000，低估了高 GCL 玩家的联盟转移能力。

**修复建议**: 将 §3 表格改为列出公式 `max(10000, gcl×20000)` 而非单一数值，或在数值后注明 "(floor; scales with receiver GCL)"。

---

## 3. 亮点

### 3.1 Resource Ledger 单一权威架构 — 优秀
`specs/core/resource-ledger.md` 作为所有费率/公式的唯一定义源，配合 Transfer Gateway 统一所有资源流入口 (Local/Global/Allied/PvE/Recycle/Build/Spawn/Upkeep/StorageTax)，消除了多入口资源逃逸风险。确定性执行顺序 (§4, 11 步有序) 确保 replay 一致性。其他文档统一引用本 Ledger 而非独立定义公式，纪律性好。

### 3.2 累进存储税 tiered 公式 — 设计合理
存储税采用 4-tier 累进结构 (0/1/5/20 bp at 30/60/85/100%)，使用 basis points 定点计算，公式数学清晰 (§2.2)。tier 边界以容量百分比定义、taxable_units 以资源单位计算、最终除以 10000 的转换链避免了浮点数。作为 anti-dominant-strategy 的内置反制机制，设计成熟。

### 3.3 渐进 PvP 过渡 (D6/B) — 设计细致入微
gameplay.md §2.2 的 soft_launch 后三阶段过渡 (First-Attack Shield → Soft PvP → Full PvP) 是优秀的新手保护设计。per-attacker 归属避免 "多攻击者轮替破盾"，shield_cooldown 防止循环，Phase 2 的 50% damage_multiplier + special_attack_immune=false 实现了平滑的难度梯度而非硬切换。

### 3.4 确定性合同 — 严谨
gameplay.md §2.8 的确定性模型覆盖了 PRNG (Blake3 XOF)、种子轮换 (每 10000 tick)、排序键 (priority_class, shuffle_index, sequence, source)、HashMap→BTreeMap、定点数值禁浮点等全链路。从经济角度，这保证了存储税、upkeep 等 per-tick 计算在 replay 中完全可复现。

### 3.5 Snapshot 截断确定性顺序 — 规范完备
snapshot-contract.md §1.3 的距离桶 + entity_id 字典序 + 从最远截断的确定性策略，使得即使触发截断，相同输入永远产生相同输出。Critical Entity Size Reserve 和 Minimum Retention Set 的分层保护确保了截断不破坏战术合法性。从经济角度，被截断实体仍正常参与资源流动（§5.2）是正确的——感知截断不应影响经济结算。

---

## 4. CrossCheck — 需要跨方向检查

- CX1: gameplay.md §2.9 的 drone 消息机制使 tick() 返回 `Message[]`，但 api-idl.md §2 的 tick() export 合约中 result_ptr 仅指向 CommandIntent[] JSON，无 messages 字段 schema。更关键的是，消息系统支持的 peer-to-peer 资源交换提议如果不走 Transfer Gateway，可能绕过 Resource Ledger §1 "单一入口" 原则。→ 建议 [interface] 检查 [tick() 返回类型合约 + 消息系统与 Resource Ledger 的边界]
- CX2: gameplay.md 第 98 行声明 MIN_LIFESPAN 权威值在 Resource Ledger §2，但该参数不存在于 Resource Ledger。同时 BASE_AGE (1500) 和各 body_part 的 age_modifier (+100/-80/-50/-30) 也无权威定义源。→ 建议 [engine] 检查 [drone lifespan 完整参数权威性: MIN_LIFESPAN, BASE_AGE, age_modifier 的 spec 定义位置]
- CX3: gameplay.md §1 Golden Path 第 6 步引用 MCP 工具 `swarm_trace_command(entity_id, tick)`，但 API Registry §3.2 不存在此工具（最接近的是 `swarm_get_tick_trace` 和 `swarm_explain_last_tick`）。→ 建议 [interface] 检查 [Golden Path 中引用的所有 MCP 工具名是否在 Registry 中注册]
- CX4: gameplay.md §Overload 反馈透明度 / 数据出口列出 "MCP `swarm_get_entity`"，但 API Registry §3.2 无此工具（有 swarm_get_drone / swarm_get_structure / swarm_get_controller）。→ 建议 [interface] 检查 [OverloadPressure 数据出口引用的工具名]
- CX5: balance sheet 50 房间行的 "Drone upkeep = 1,000" 引用了 per-drone 维护费，但 Resource Ledger §2 从未定义 per-drone upkeep 费率。→ 建议 [engine] 检查 [drone 维护费是否独立于 Empire Upkeep 存在，若是则需在 Resource Ledger 定义公式]
