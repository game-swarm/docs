# R35 Design & Economy 独立评审报告

**评审员**: rev-dsv4-design-economy (DeepSeek V4 Pro)
**日期**: 2026-06-26
**评审视角**: 博弈论均衡分析、策略深度度量、资源流建模

---

## 1. Verdict

**REQUEST_MAJOR_CHANGES**

存在 2 项 Critical 问题（全局存储容量量级差 10×、upkeep 双公式默认参数不一致），3 项 High 问题（starting_resources 多资源 vs 单能源默认冲突、存储税均衡证明缺失、Rhai 模组示例忽略 free_upkeep），需修复后才能进入下一阶段。

---

## 2. 发现的问题

### Critical

#### C1: 全局存储容量 10× 量级不一致
- **Severity**: Critical
- **位置**: 
  - `design/gameplay.md` §2.3 world.toml 示例 (line 1289): `global_storage_capacity = 100000`
  - `specs/core/08-resource-ledger.md` §2.1 (line 74-78): 隐含 `global_storage_capacity = 1,000,000`（通过存储税示例反推：容量 1,000,000，存储量 750,000 产生税 105）
  - `specs/reference/api-registry.md` §5.1 (line 555): `Global storage capacity | 1,000,000 units`
  - `design/gameplay.md` §全局存储反制机制 > transport table (line 357): `global_storage_capacity` 1,000,000
  - `design/economy-balance-sheet.md` §1 (implied via tax calculation): 1,000,000
- **问题描述**: gameplay.md §2.3 的 world.toml 示例将 `global_storage_capacity` 设为 100,000，而 Resource Ledger、API Registry、Balance Sheet 和 gameplay.md 另一处均使用 1,000,000。这是一个数量级 (10×) 的错误。100,000 容量下，存储税 tier 1 阈值 30% = 30,000 很快触发，大幅改变经济平衡——与 Balance Sheet 中 "1-3 房间 <30% 存储（免税）" 的假设直接冲突。
- **影响分析**: 若实现使用 100,000，存储税对中大型玩家冲击远大于 Balance Sheet 预期，使 "中期自维持可达" 的结论失效。若实现使用 1,000,000（正确值），则该 world.toml 示例会误导服主。
- **修复建议**: 将 `design/gameplay.md` line 1289 修正为 `global_storage_capacity = 1000000`，并在所有 world.toml 示例中统一此值。

#### C2: Empire Upkeep 双公式默认参数不一致
- **Severity**: Critical
- **位置**:
  - `specs/core/08-resource-ledger.md` §Empire Upkeep (line 286-288): `upkeep = base_upkeep × rooms × (1 + rooms / room_soft_cap)`，默认 `base_upkeep=50, room_soft_cap=10`
  - `design/gameplay.md` §2.7 tick_end.rhai (line 1549-1550): `room_penalty = rooms * (config.room_base + rooms * config.room_superlinear / FIXED_SCALE)`，默认 `drone_cost=2, room_base=10, room_superlinear=1, FIXED_SCALE=10000`
- **问题描述**: Resource Ledger 公式产生 `upkeep(10 rooms) = 50 × 10 × (1 + 10/10) = 1000`；Rhai mod 默认参数产生 `room_penalty(10 rooms) = 10 × (10 + 10/10000) ≈ 100`（不含 drone 项）。两者相差约 10×。即使将 drone_cost 考虑进去（假设 30 drones: +60），Rhai 的 ~160 也远低于 Resource Ledger 的 1000。Balance Sheet 基于 Resource Ledger 公式推导，而实现模组使用完全不同的参数。这导致：economic analysis 预计的 anti-snowball 效果在默认 Rhai 实现中不成立。
- **影响分析**: 若不修复，Vanilla/Standard 世界的实际运行维护费远低于设计值——anti-snowball 天花板消失，大帝国可持续扩张至远超 50 房，经济模型崩溃。
- **修复建议**: 
  - 方案 A（推荐）：将 Rhai mod 默认参数校准至匹配 Resource Ledger 公式——`room_base=50, room_superlinear=50000`（使 `n*50 + n²*50000/10000 = 50n + 5n²`，与 Resource Ledger 一致）
  - 方案 B：明确声明 Rhai mod 示例参数是**仅供 illustration** 的虚构值，并添加交叉引用至 Resource Ledger 的权威公式
  - 无论选哪个方案，需在 gameplay.md 的 Rhai tick_end.rhai 代码块添加注释说明默认参数与官方 Vanilla 公式的对应关系

### High

#### H1: 起始资源类型「Minerals/Matter」与「单能源」默认规则集冲突
- **Severity**: High
- **位置**:
  - `specs/core/08-resource-ledger.md` §2.3 (line 128): `starting_resources = {Energy: 5000, Minerals: 2000}`
  - `design/economy-balance-sheet.md` §3 (line 216): `starting_resources` 含 Minerals
  - `specs/reference/api-registry.md` §5.1 (line 556): `Starting resources | {Energy: 5000, Minerals: 2000}`
  - `design/gameplay.md` §Official Vanilla Ruleset (line 517): "资源 | 单一 `Energy`"
  - `design/gameplay.md` §2.3 world.toml 示例 (line 1301-1306): `[[resource_types]]` 定义 Energy + Matter（非 Minerals）
- **问题描述**: Resource Ledger、Balance Sheet、API Registry 三道权威源一致声明 starting_resources 包含 `Minerals`。但 gameplay.md 的 "Official Vanilla Ruleset" 声称默认世界仅有一种资源 `Energy`。此外，gameplay.md 的多资源示例使用 `Matter` 而非 `Minerals`——连命名都不统一。
- **影响分析**: 新玩家到底获得 Energy only 还是 Energy+Minerals？这直接影响初始经济平衡——Balance Sheet 中 1 房间 5000 初始 Energy 的假设若外加 2000 Minerals，则新玩家经济更宽松。若 Vanilla 确实仅支持 Energy，则 Resource Ledger 中 Minerals 的字段成为死代码。
- **修复建议**: 
  - 确认权威决策：Vanilla 世界是否默认包含多资源？若否，将 Resource Ledger、Balance Sheet、API Registry 中的 `starting_resources` 改为 `{Energy: 5000}`，移除 Minerals/Matter 引用
  - 若是，则在 gameplay.md §Official Vanilla Ruleset 更新默认资源列表，并统一命名 (Minerals vs Matter → 选一个)
  - 此为设计决策项 (D-item)，需用户裁决

#### H2: 存储税均衡证明 (Storage Tax Equilibrium Proof) 为空壳
- **Severity**: High
- **位置**: `design/economy-balance-sheet.md` §6 (line 250-251)
- **问题描述**: §6 标题为「存储税均衡证明」，但内容仅一行引用 Resource Ledger §2.2，未包含任何数学推演。存储税从 0%→30% 进入 1bp 税率区后，需证明 `faucet_income × storage_percent = tax_rate × storage_amount` 存在稳定均衡点——否则存储量要么无限增长要么趋于零，不存在"自然天花板"。当前文档无此证明。
- **影响分析**: 存储税是整个 anti-snowball 体系的关键支柱之一。若无均衡证明，无法确保 tier 设计能形成稳定收敛。可能导致实际玩家经济在某个 tier 内永远不收敛。
- **修复建议**: 
  - 添加数学推导：证明在每个税率 tier 内，存在一个存储量使 `d(storage)/dt = income - tax(storage) - expense = 0` 有解
  - 或标记为 playtest-gated，在 `specs/PLAYTEST-GATED.md` 中明确记录此项需数据校准
  - 至少需要一个收敛性论证，而非空壳

#### H3: Rhai empire-upkeep 示例忽略 free_upkeep 豁免逻辑
- **Severity**: High
- **位置**:
  - `design/gameplay.md` §2.7 tick_end.rhai (line 1541-1562)
  - `specs/core/08-resource-ledger.md` §2.3 (line 133-137): free_upkeep 机制
  - `specs/core/08-resource-ledger.md` §4 执行顺序 (line 220): UpkeepDeduction 步骤需跳过 free_upkeep 实体
- **问题描述**: Rhai mod 的 tick_end.rhai 示例代码对**所有**玩家的**所有** drone 和房间统一扣费，未实现 free_upkeep_controllers / free_upkeep_drones / free_upkeep_ticks 的豁免逻辑。Resource Ledger §4 明确要求 UpkeepDeduction（执行顺序第 2 步）跳过免维护实体。Rhai 示例未反映此逻辑，会误导模组作者和实现者。
- **影响分析**: 若实现者照抄 Rhai 示例，新玩家在前 2000 tick 仍被扣维护费，与 Resource Ledger 的 free_upkeep 设计合同冲突，导致新玩家经济崩溃。
- **修复建议**: 在 tick_end.rhai 代码中添加 free_upkeep 检查逻辑（伪码即可），或在注释中明确标注「以下为简化示例，完整实现需根据 Resource Ledger §2.3 的 free_upkeep 参数豁免符合条件的 controller/drone」

### Medium

#### M1: PvE 收益在 Balance Sheet 中被当作按房间比例线性分配
- **Severity**: Medium
- **位置**:
  - `design/economy-balance-sheet.md` §2.4-2.6: PvE drop 作为收入项，量随房间数线性增长（10 房 = 50/tick, 20 房 = 100/tick, 50 房 = 500/tick）
  - `design/modes.md` §World PvE 生态层 (line 70): `max_pve_output_per_tick ≤ 世界再生总量 × 30%`（全局 cap）
- **问题描述**: Balance Sheet 将 PvE 收益视为按房间比例分配的收入（10 房分 50, 20 房分 100），但这与 PvE cap 的全局性质冲突。30% 再生总量是一个共享池——若世界有 100 个玩家，每人分不到 0.3%。Balance Sheet 的假设仅在"单玩家占世界大量 PvE"时成立，不具备普遍性。
- **影响分析**: Balance Sheet 中 20 房和 50 房的优化收入依赖 PvE 贡献。若实际 PvE 分配远低于假设，20 房亏损更严重，soft cap 可能更早触达。
- **修复建议**: 
  - 在 Balance Sheet 中明确 PvE 收益假设：单玩家占世界 PvE pool 的 X%
  - 或添加「无 PvE 收入」情景作为对照列（纯 faucet + controller income）
  - 标记为 playtest-gated 参数（与 PG-1 一致）

#### M2: Fabricate 抗性类型与 canonical 表不一致
- **Severity**: Medium
- **位置**:
  - `design/gameplay.md` §特殊攻击方式 (line 764): Fabricate → 目标 `EMP` 抗性
  - `design/gameplay.md` §[[special_effects]] fabricate (line 1100-1101): `resistance = "Psionic"`
- **问题描述**: 同一文档的同一特殊攻击（Fabricate），在 narrative 表格中声明抗性为 EMP，在 TOML 配置定义中声明为 Psionic。两者互斥。
- **影响分析**: 实现者会困惑——校验逻辑使用哪个抗性类型？若选 EMP 与 Psionic 不同，反制策略（堆哪种抗性）完全不同。
- **修复建议**: 统一 Fabricate 的抗性类型。参考 `api-registry.md` — 该表不直接定义特殊攻击的抗性，权威定义应在 gameplay.md 的 `[[special_effects]]` TOML 块中。建议将 narrative 表格中的 EMP 修正为 Psionic（或反之），并在 canonical 表中标注权威源。

#### M3: Overload MAX_FUEL 缺乏权威定义
- **Severity**: Medium
- **位置**:
  - `design/gameplay.md` §特殊攻击方式 (line 758): Overload 消耗 500k，下限 MAX_FUEL × 0.2
  - `design/gameplay.md` §Overload (line 759): "默认 MAX_FUEL=10M"（仅注释）
  - `specs/reference/api-registry.md`: 未定义 MAX_FUEL
- **问题描述**: Overload 效果的基准值 MAX_FUEL 仅在 gameplay.md 的注释中出现（"默认 MAX_FUEL=10M"），不在任何 spec 的权威参数表中。Resource Ledger、API Registry 均未包含此参数。若 MAX_FUEL 不是 10M，则 500k = 5% 的假设不成立。
- **影响分析**: Overload 的效果量（减 500k fuel）与 MAX_FUEL 绑定的下限（20% = 2M 若 MAX_FUEL=10M）完全取决于此未声明参数。若 MAX_FUEL 在不同世界模式下不同，Overload 的实际压制效果会剧烈变化。
- **修复建议**: 在 Resource Ledger §2 统一参数表或 API Registry §5.2 WASM 限制表中添加 `MAX_FUEL` 权威定义，并标注其默认值及 world.toml 可配性。

### Low

#### L1: PvE Budget 账本 player 维度上限与 Balance Sheet 不一致
- **Severity**: Low
- **位置**:
  - `specs/core/08-resource-ledger.md` §3 (line 187): `Player | ≤ player_controller_level × 1000 | per tick`
  - `design/economy-balance-sheet.md`: PvE 收益按房间数线性增长（不依赖 controller_level）
- **问题描述**: Resource Ledger 的 per-player PvE cap 按 `controller_level × 1000` 计算，但 Balance Sheet 假设 PvE 收益与房间数成正比。RCL 和房间数是不同维度——5 房玩家的 RCL 可能 3-4（cap 3000-4000/tick），而 Balance Sheet 的 PvE 收益 50/tick (10 房) 远低于此。数值上不冲突（假设值在 cap 内），但建模维度不一致。
- **修复建议**: 在 Balance Sheet 中标注 PvE 收益假设同时受 global cap 和 player-level cap 约束，实际值取两者的 min。非阻塞。

#### L2: Rhai mod 配置示例 `onshortfall` 与 Resource Ledger §Empire Upkeep 的 deficit 机制重复定义
- **Severity**: Low
- **位置**:
  - `design/gameplay.md` §2.7 mod.toml (line 1522-1523): `onshortfall = { type = "enum", default = "degrade", values = ["degrade", "damage", "despawn"] }`
  - `specs/core/08-resource-ledger.md` §Empire Upkeep (line 292): "连续 3 tick deficit 触发 drone 饥饿惩罚（效率 −50%），连续 10 tick deficit 触发 drone 强制死亡（age 加速 ×10）"
- **问题描述**: empire-upkeep 模组提供 onshortfall 配置（degrade/damage/despawn），而 Resource Ledger 本身已定义全局 deficit 机制（3 tick → 效率 -50%，10 tick → age×10）。两者存在重叠：模组的 onshortfall 可能覆盖或冲突于引擎级 deficit 行为。但 Resource Ledger 的 deficit 机制是按 tick 累积的，而 onshortfall 是按「维护费不足时」触发的，两者可能是不同层面的机制。当前文档未澄清其交互。
- **修复建议**: 在 Resource Ledger §Empire Upkeep 或 gameplay.md mod 文档中添加一句话澄清 onshortfall 与 engine-level deficit 的关系（如 "onshortfall 决定当次维护费不足时的立即行为；Resource Ledger 的 deficit 累积计数器决定持续不足时的递增惩罚"）。

---

## 3. 亮点

1. **Resource Ledger 作为单一经济权威的架构很优秀**: 所有费率、公式、执行顺序集中在 `08-resource-ledger.md` 统一定义，其他文档仅引用——消除了 R22-R34 多轮评审中反复出现的多文档费率冲突问题。Transfer Gateway 的单一入口设计从根本上杜绝了资源逃逸路径。

2. **定点数类型体系完整且一致**: `BasisPoints`、`ResourceRate_i64`、`MilliUnits` 等在 IDL 和 Resource Ledger 中定义清晰，api-registry.md §0 的 Fixed-Point Type Registry 提供了完整的跨文档引用锚点。所有计算公式使用 bp 整数运算，无浮点数。

3. **Anti-snowball 多层防御设计有深度**: 超线性维护费 + 累进存储税 + 运输延迟 + 拦截机制 + Controller 老化 + Room cap ——不是单一机制，而是从经济、物流、军事三个维度同时施加约束，形成嵌套 Nash 均衡。单个机制被绕过（如通过 Allied Transfer 规避存储税）时，其他层次（物流延迟 + 拦截）仍生效。

4. **Allied Transfer 受限 + 拦截的博弈论设计精巧**: 200 tick 延迟窗口（前 150 tick 安全 + 后 50 tick 可拦截）、Escort 防御机制、拦截成功率公式——将资源运输从纯后勤转化为需要兵力护航的策略博弈。成功率的 `base 60% + part_bonus (max 25%) - escort_penalty (30%)` 结构确保无法单方面垄断拦截，必须在攻击和护航之间分配 CARRY/ATTACK 部件。

5. **PvE Budget 四维账本防止 faucet 无限放大**: Global/Zone/Player/Event 四层 cap 叠加，防止"刷怪经济"压倒 PvP 战略价值。NPC tier → PvE award 的映射表明确，per-player cap 按 controller_level 缩放防止小号刷资源。

6. **经济反馈循环设计覆盖双通道**: Web UI 经济仪表盘（实时存储利用率、税率预测、效率指标）+ MCP 经济查询工具（`swarm_get_economy`、`swarm_get_economy_trend`）——使人类和 AI 玩家均能做出有信息量的经济决策。存储税率预警（30 tick 提前警告进入下一 tier）是良好的 UX 设计。

---

## 4. CrossCheck — 需要跨方向检查

- **CX1**: empire-upkeep 双公式默认参数不一致（Resource Ledger: base_upkeep=50, room_soft_cap=10 → 1000/tick @ 10 rooms；Rhai mod: room_base=10 → ~100/tick） → 建议 **Core/Engine reviewer** 检查 `engine/mods/empire-upkeep/` 的实际实现代码——验证其默认参数与 Resource Ledger 公式是否一致，以及 Balance Sheet 推导是否正确反映了实现行为

- **CX2**: `design/modes.md` §9.0 的 NPC 掉落经济 (line 70) 说 `max_pve_output_per_tick ≤ 世界再生总量 × 30%`，但 `specs/core/08-resource-ledger.md` §3 PvE Budget 的 Global 维度同样限制为 `≤ 世界再生总量 × 30%`。两处在同一概念上保持一致，但均未定义「世界再生总量」如何计算——是所有 Source 再生之和？是否含 Controller passive income？ → 建议 **Core/Engine reviewer** 检查 `engine/` 中 PvE budget 计算的实际公式，确认「世界再生总量」的定义

- **CX3**: `design/gameplay.md` §存储税累进税制 (line 357) 的 transport 表格列出 `global_storage_tax_tiers = [(30,0),(60,1),(85,5),(100,20)]`，同时 `specs/reference/api-registry.md` §10.2 的 StorageTax (line 854) 说 "Tiers: 0%–30% cap = 0 bp, 30%–60% = 1 bp, 60%–85% = 5 bp, 85%–100% = 20 bp"。两个源一致。但 `design/gameplay.md` §2.3 world.toml 示例 (line 1289) 中 `global_storage_capacity = 100000` 与 1,000,000 矛盾（见上面 C1）。 → 建议 **Security/Audit reviewer** 验证 FDB 中 storage_capacity 字段的实际 scale 及存储税计算的单元测试——确保 100,000 和 1,000,000 之间不存在混淆

- **CX4**: `design/gameplay.md` §特殊攻击抗性 (line 764): Fabricate 的抗性在 narrative 表格中说 EMP，在 `[[special_effects]]` TOML 块 (line 1100) 中说 Psionic。 → 建议 **Gameplay/Combat reviewer** 检查 `specs/reference/special-attack-table.md`（canonical 特殊攻击参数表）确认权威值

- **CX5**: `specs/core/09-snapshot-contract.md` §3.2 (line 218) 说 "核心系统不实现联盟资源池、联盟税率、联盟仓库共享。完整物流战留给 Rhai mod"，但 `design/gameplay.md` §外交系统 (line 2127) 说 Allied 状态下可 "直接 player↔player transfer，免 convert 延迟"。如果免 convert 延迟 = 绕过 global_deposit_delay/global_withdraw_delay，则外交系统实际上修改了 Resource Ledger 的传输延迟——这属于 core 还是 mod？ → 建议 **Core/Engine reviewer** 检查 Allied Transfer 的实现是否绕过 Resource Ledger 的 delay 管线

- **CX6**: `design/gameplay.md` §2.9 Drone 间消息机制 (line 2022) 说 "消息协议不强制诚实——引擎不校验 payload 语义"，同时 `design/gameplay.md` §经济分类账 (line 404) 将「市场交易」标为 RFC 不在当前设计范围。这两个声明之间存在张力：消息机制 + 不可信协议本质上是去中心化市场的底层基础设施。 → 建议 **Security reviewer** 检查消息 payload 是否可能被用于构建绕过 Resource Ledger 的非正式经济通道（如通过消息协议实现 OTC 交易，再用 WASM Transfer 指令结算）

---

## D-Item（需用户裁决）

- **D1 (from H1)**: 默认起始资源是否应包含 Minerals/Matter？即 Vanilla 世界是「单一 Energy」还是「Energy + Minerals」？
  - 选项 A: 单一 Energy → 修改 Resource Ledger、Balance Sheet、API Registry 的 starting_resources 为 `{Energy: 5000}`
  - 选项 B: Energy + Minerals → 修改 gameplay.md Official Vanilla Ruleset 的资源列表，统一命名 (Minerals vs Matter → 选其一)