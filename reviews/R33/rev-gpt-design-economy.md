# R33 Design & Economy Review — GPT-5.5

## Verdict
REQUEST_MAJOR_CHANGES

R33 的核心玩法愿景、学习闭环、World/Arena 双模式定位已经比较清晰，但设计文档仍存在多处会直接阻断实现与平衡验证的重大问题：Standard 经济曲线在目标状态下没有形成可自维持区间，权威经济数值在 design/spec/IDL 之间互相冲突，Feedback Loop 与 modes 文档仍残留 MVP/P0/P1/Phase 语义，且 Game API/IDL 的机器权威与生成文档存在数量、参数和能力面冲突。这些问题会导致玩家动机模型、经济闭环、SDK/API 可用性和后续实现全部产生分叉，建议修复后再进入下一轮。

## Critical (必须修复，否则 BLOCK) (B1..Bn)

### B1. Standard 经济曲线没有自维持区间，反雪球变成全阶段净亏损

- severity: Critical
- 文件引用：`/data/swarm/docs/design/economy-balance-sheet.md:59`, `/data/swarm/docs/design/economy-balance-sheet.md:78`, `/data/swarm/docs/design/economy-balance-sheet.md:99`, `/data/swarm/docs/design/economy-balance-sheet.md:123`, `/data/swarm/docs/design/economy-balance-sheet.md:146`, `/data/swarm/docs/design/economy-balance-sheet.md:170`, `/data/swarm/docs/design/economy-balance-sheet.md:197`, `/data/swarm/docs/specs/core/08-resource-ledger.md:143`
- 问题描述：Balance Sheet 明确写出 Standard 在 1 房 free_upkeep 结束后为 -33/tick，2/3/5/10/20/50 房全部亏损；但同文又声称 self-sustaining 在“优化代码 + 适度扩张条件下可达”。Resource Ledger 也声称 2000 tick 后 Full economy “✅ 自维持”。这不是数值小偏差，而是目标状态矛盾：玩家没有一个可稳定抵达的中期正反馈平台。
- 影响分析：反雪球机制的目标应是压低无限扩张边际收益，而不是让所有标准扩张路径都净亏损。当前曲线会把玩家动机从“优化代码获取优势”变成“不断消耗初始补贴直到死亡”，导致新手保护结束后进入 upkeep deficit 死亡螺旋；专家玩家也缺少可验证的 break-even build order，经济策略空间退化为寻找文档漏洞或依赖未定义的“PvE 农场/联盟交易”。
- 修复建议：把 Standard 目标曲线改成明确的三段式目标状态：1) 新手 free_upkeep 期正流入；2) 2–5 房在良好代码和 RCL 升级后可达到小幅正流入或接近平衡；3) 20+ 房进入明显递减，50 房接近不可持续。必须重算 `base_upkeep`、`room_soft_cap`、source/RCL/PvE 收入和存储税，给出至少一个 3–5 房 “optimized but realistic” 正流量样例。若某些平衡点需要 playtest 数据，应在本文中标注为 `playtest-gated` 并同步到 `PLAYTEST-GATED.md`，但不能在最终设计中留下“所有示例全亏损却声称可自维持”的状态。

### B2. 经济权威源互相冲突，核心成本、费用和结算顺序不可实现

- severity: Critical
- 文件引用：`/data/swarm/docs/design/gameplay.md:123`, `/data/swarm/docs/specs/core/07-world-rules.md:648`, `/data/swarm/docs/specs/reference/economy.idl.yaml:239`, `/data/swarm/docs/design/gameplay.md:890`, `/data/swarm/docs/specs/core/07-world-rules.md:579`, `/data/swarm/docs/specs/reference/economy.idl.yaml:329`, `/data/swarm/docs/specs/core/08-resource-ledger.md:75`, `/data/swarm/docs/design/gameplay.md:311`, `/data/swarm/docs/design/gameplay.md:313`, `/data/swarm/docs/specs/reference/economy.idl.yaml:155`, `/data/swarm/docs/specs/core/08-resource-ledger.md:195`
- 问题描述：同一设计对象在多个“权威源”中给出不同值。Spawn 建造成本在 gameplay 为 300、world-rules 为 200、economy IDL 为 300；RangedAttack body cost 在 gameplay/economy 为 150、world-rules 为 100；Global deposit/withdraw 在 Resource Ledger 统一参数表只有 `global_transfer_delay = 100`，而 gameplay 分成 deposit 10 tick 与 withdraw 100 tick；economy IDL 写 Upkeep “Deducted before StorageTax”，但同一段描述说 StorageTax “Assessed before any other per-tick deductions”，Resource Ledger 顺序又列 Upkeep 第 2、StorageTax 第 3。
- 影响分析：经济模型无法成为可实施合同，SDK、UI tooltip、AI 策略、Balance Sheet 和 replay ledger 会生成不同数字。玩家无法学习“正确规则”，专家无法构建可靠策略，经济审计也无法判定某个资源变化是 bug 还是文档分叉。
- 修复建议：选定 `specs/core/08-resource-ledger.md` + `economy.idl.yaml` 的分工：Ledger 是数学权威，IDL 只机器编码同一数值；design 文档只引用不重列。对所有成本表和 transfer 参数做一次全量去重：保留单一 canonical 表，并在其他文档改为“引用 + 非权威示例”。同时统一执行顺序文案：明确 Upkeep 和 StorageTax 哪个先，并修正 IDL 描述与 Ledger 顺序。

### B3. API/IDL 机器权威与文档输出冲突，核心玩法能力面不稳定

- severity: Critical
- 文件引用：`/data/swarm/docs/specs/reference/api-registry.md:7`, `/data/swarm/docs/specs/reference/game_api.idl.yaml:8`, `/data/swarm/docs/specs/reference/game_api.idl.yaml:1894`, `/data/swarm/docs/specs/reference/api-registry.md:262`, `/data/swarm/docs/specs/reference/game_api.idl.yaml:498`, `/data/swarm/docs/specs/reference/api-registry.md:455`, `/data/swarm/docs/specs/reference/game_api.idl.yaml:1506`, `/data/swarm/docs/specs/reference/api-registry.md:464`, `/data/swarm/docs/specs/reference/game_api.idl.yaml:1510`, `/data/swarm/docs/specs/reference/api-registry.md:72`, `/data/swarm/docs/specs/reference/game_api.idl.yaml:198`, `/data/swarm/docs/specs/gameplay/08-api-idl.md:193`
- 问题描述：`api-registry.md` 声称由 IDL 生成且 game_api 版本为 0.4.0，但 `game_api.idl.yaml` changelog 已有 0.4.1 变更；Registry 说 57 game tools + 11 auth tools，YAML 注释仍写“46 tools”，changelog 又写 56 active；Registry Host Functions 包含 `host_get_random` 共 6 个，YAML `total_functions: 5` 且无 `host_get_random`。同时 `TransferToGlobal/TransferFromGlobal` 在 Registry 分类为 `economy_operation`，YAML 是 `global_storage`；Overload 在 Registry/YAML 参数为 `EntityId`，而 IDL spec 文档示例为 `PlayerId`。
- 影响分析：Design & Economy 角度看，这直接破坏 AI agent 与人类玩家的同等学习路径：`swarm_get_available_actions`、SDK 生成、特殊攻击、global storage 指令和 host 随机能力都会出现工具面不一致。玩家会写出在某个文档中合法、在机器 schema 中非法的 bot；Arena 公平性和 World 经济操作也会因 action schema 分叉而不可审计。
- 修复建议：重新从 YAML 生成 `api-registry.md`，并将 `game_api.idl.yaml` 的 `api_version`、`total_tools`、`total_functions`、category 命名和 changelog 统一。若 `host_get_random` 是目标设计，则必须加入 YAML 机器源；若不是，应从 Registry 删除。Overload 目标应明确是 player-level fuel attack 还是 entity-level pressure attack，并统一 `target_id` 类型、可见性规则和 UI 反馈字段。

### B4. 设计文档仍残留 MVP/P0/P1/Phase 语义，违反“设计即目标状态”并污染玩家预期

- severity: Critical
- 文件引用：`/data/swarm/docs/design/modes.md:12`, `/data/swarm/docs/design/modes.md:88`, `/data/swarm/docs/specs/gameplay/06-feedback-loop.md:5`, `/data/swarm/docs/specs/gameplay/06-feedback-loop.md:7`, `/data/swarm/docs/specs/gameplay/06-feedback-loop.md:338`, `/data/swarm/docs/specs/gameplay/06-feedback-loop.md:340`, `/data/swarm/docs/specs/core/09-snapshot-contract.md:181`, `/data/swarm/docs/specs/core/09-snapshot-contract.md:421`, `/data/swarm/docs/design/gameplay.md:538`
- 问题描述：多处仍以 MVP/P0/P1/Phase 叙述最终规则，包括 modes 的“状态 ✅ MVP 核心”、Arena “P0/P1+”，Feedback Loop 的“MVP 必须”“MVP 功能清单”，Snapshot Contract 的“MVP Economy Boundaries”和版本表。gameplay 中 soft_launch 后 PvP 也使用 “Phase 1/2/3”。
- 影响分析：这些不是单纯措辞问题。Swarm 当前评审原则是设计文档呈现最终目标状态；Phase/MVP 语义会让实现者和玩家误读某些规则只是阶段性占位，尤其 Allied Transfer、Arena、经济边界、onboarding 验收和 PvP 过渡会被降级处理。玩家动机模型也会被“现在不做/未来再说”的语言削弱。
- 修复建议：把所有 MVP/P0/P1/Phase 语义改为目标状态语言。对于真正不在核心设计内的内容，使用 `RFC` / `Out-of-Scope` / `mod extension`；对于渐进状态机，使用“Stage”或“Transition Window”而非 Phase。Arena 房间制、反馈循环、经济边界等若是目标设计，应直接表述为当前规则。

### B5. Alliance/Allied Transfer 设计互相冲突，经济反滥用边界被绕开

- severity: Critical
- 文件引用：`/data/swarm/docs/design/economy-balance-sheet.md:208`, `/data/swarm/docs/design/economy-balance-sheet.md:222`, `/data/swarm/docs/specs/core/08-resource-ledger.md:168`, `/data/swarm/docs/specs/core/08-resource-ledger.md:80`, `/data/swarm/docs/design/gameplay.md:2120`, `/data/swarm/docs/design/gameplay.md:2125`, `/data/swarm/docs/design/gameplay.md:2135`
- 问题描述：Balance Sheet 和 Resource Ledger 定义 Standard 的 Allied Transfer 为 Restricted：2% fee、200 tick delay、500 tick cooldown、daily cap，且 Allied Transfer 是反滥用受限通道。但 gameplay 外交系统又写 allied “可直接 player↔player transfer，免 convert 延迟”，多联盟上限也从 economy IDL 的 10 变成 gameplay 的 5。
- 影响分析：这会直接绕开 B2 中 Resource Ledger 的单入口和反雪球设计。若 allied 可免延迟直接转移，大帝国/联盟可把 global/local 转换、new-player gate 和拦截窗口全部规避；若仍按 Restricted 执行，外交文档给玩家承诺了不存在的联盟特权。两者都会破坏 alliance 作为战略社交层的信任。
- 修复建议：将 diplomacy 的 allied 资源权限改为引用 `Restricted Allied Transfer`，明确不存在免延迟 player↔player direct transfer；若确实需要 ally local transfer，则必须作为同一 Resource Ledger 操作的受限子类型，继承 fee/delay/cap/intercept/new-player gate。统一 `max_active_alliances` 数值。

## High (强烈建议修复) (H1..Hn)

### H1. Feedback Loop 仍把 AI onboarding 描述成直接 MCP 循环，但 API 能力面缺少事件订阅合同

- severity: High
- 文件引用：`/data/swarm/docs/specs/gameplay/06-feedback-loop.md:122`, `/data/swarm/docs/specs/gameplay/06-feedback-loop.md:124`, `/data/swarm/docs/specs/gameplay/06-feedback-loop.md:135`, `/data/swarm/docs/specs/reference/api-registry.md:277`, `/data/swarm/docs/specs/reference/game_api.idl.yaml:500`
- 问题描述：Feedback Loop 承诺部署后引擎立即推送 `deploy_accepted`、下一 tick 推送 `first_tick_executed`，AI 无需 polling；但 API Registry/YAML 的 MCP tools 和 WebSocket/事件工具没有对应订阅工具、事件 schema 或 capability profile。
- 影响分析：这会破坏 10 分钟 Golden Path 中最关键的“部署后看见结果”。AI agent 若只能 polling `swarm_get_deploy_status` / `swarm_get_snapshot`，实际学习闭环与文档承诺不一致，尤其首个 tick 失败时缺少主动反馈。
- 修复建议：为 `deploy_accepted`、`first_tick_executed`、`economy_warning` 等事件补机器可读 schema，并明确通过 WebSocket channel、MCP subscription，还是 `swarm_get_events` 拉取。不要只在 UX 文档承诺事件。

### H2. Arena 设计在“无天梯/无赛季”与 Leaderboard/Tournament API 之间目标不一致

- severity: High
- 文件引用：`/data/swarm/docs/design/modes.md:88`, `/data/swarm/docs/specs/gameplay/06-feedback-loop.md:337`, `/data/swarm/docs/specs/reference/api-registry.md:370`, `/data/swarm/docs/specs/reference/api-registry.md:374`, `/data/swarm/docs/specs/reference/api-registry.md:375`, `/data/swarm/docs/specs/reference/game_api.idl.yaml:1337`
- 问题描述：modes 和 feedback-loop 声称 Arena 无自动匹配、无天梯排名、无赛季，Tournament/League 不是核心；但 API Registry/YAML 把 leaderboard、tournament_create/precommit/status、match_result 放入 active Arena capability，并非 RFC。
- 影响分析：这会影响玩家动机模型：Arena 到底是轻量房间制测试场，还是带排行榜/赛事的竞技体系？若 active API 暴露 leaderboard/tournament，玩家会预期排名、比赛组织和反作弊承诺；若文档说没有，则产品体验断裂。
- 修复建议：明确 Arena 目标状态。若 leaderboard/tournament 是核心，则 modes 删除“无天梯/无赛季/Tournament P1+”语义并补公平性、奖励、赛季范围；若不是核心，则将相关 API 移到 RFC 或 admin-only future，不计入 active capability。

### H3. Snapshot Contract 中 StorageTax 描述仍保留旧税率，经济边界误导

- severity: High
- 文件引用：`/data/swarm/docs/specs/core/09-snapshot-contract.md:196`, `/data/swarm/docs/specs/core/08-resource-ledger.md:83`, `/data/swarm/docs/specs/reference/economy.idl.yaml:115`
- 问题描述：Snapshot Contract 的 MVP Economy Boundaries 写 StorageTax “0.1%/tick”，但 Ledger/IDL 的累进税为 0/1/5/20 bp，其中最高 20 bp=0.20%/tick，且不是统一 0.1%。
- 影响分析：虽然是边界文档，但它被标注为经济边界，会让实现者或 reviewer 误以为存储税固定 0.1%，从而影响反囤积曲线和 Balance Sheet 验算。
- 修复建议：删除固定 0.1% 文案，改为“按 Resource Ledger §2.2 tiered StorageTax 执行”。

### H4. PvE faucet 的奖励表与 World PvE 掉落表不闭合

- severity: High
- 文件引用：`/data/swarm/docs/design/modes.md:34`, `/data/swarm/docs/design/modes.md:35`, `/data/swarm/docs/design/modes.md:45`, `/data/swarm/docs/design/modes.md:67`, `/data/swarm/docs/specs/reference/economy.idl.yaml:196`, `/data/swarm/docs/specs/core/08-resource-ledger.md:180`
- 问题描述：modes 定义 Creep/Guardian/据点掉落 Energy/Crystal/Blueprint/Wreckage，数值是 10–30、5–15、Crystal×2000 等；economy IDL 定义 PvEAward T1=100 到 T5=50000 的 tiered base_award；Ledger 又用 Global/Zone/Player/Event 四维预算约束。三者没有映射关系。
- 影响分析：PvE 是新手 soft_launch 和中大型帝国收入的重要 faucet。若掉落表与 Ledger award tier 不映射，PvE 既可能被刷怪经济压倒 PvP，也可能因预算裁剪导致玩家看到的掉落承诺无法兑现。
- 修复建议：建立 NPC/据点 → entity_tier/entity_type_modifier → Resource Ledger budget 的映射表。Blueprint/Wreckage 若非普通资源，应说明是否进入 Ledger；若 Blueprint 能解锁能力，应标注是否 tradeable 和是否受 new-player gate 限制。

### H5. Novice/Vanilla/Standard 命名混用，学习曲线分层不清

- severity: High
- 文件引用：`/data/swarm/docs/design/gameplay.md:511`, `/data/swarm/docs/design/gameplay.md:768`, `/data/swarm/docs/design/gameplay.md:769`, `/data/swarm/docs/design/economy-balance-sheet.md:13`, `/data/swarm/docs/design/economy-balance-sheet.md:201`
- 问题描述：文档同时使用 Vanilla Ruleset、Vanilla (Novice)、Novice、Standard、Advanced。gameplay 说 Vanilla 是官方默认规则集，Balance Sheet 又把 Vanilla 标为 Novice；特殊攻击解锁用 Tutorial/Novice/Standard/Advanced。
- 影响分析：学习曲线和玩家选择世界时的心理模型会混乱。新手无法判断“Vanilla”到底是默认完整体验，还是 Novice 简化体验；服主配置也难以知道哪个是标准模板。
- 修复建议：定义清晰 taxonomy：例如 Ruleset=Vanilla，Difficulty/Profile=Tutorial/Novice/Standard/Advanced。所有表格使用同一层级，不把 Vanilla 与 Novice 混作同一维度。

## Medium (建议关注) (M1..Mn)

### M1. World vs Arena visibility 默认值冲突

- severity: Medium
- 文件引用：`/data/swarm/docs/specs/core/07-world-rules.md:533`, `/data/swarm/docs/design/gameplay.md:1243`, `/data/swarm/docs/design/modes.md:19`, `/data/swarm/docs/design/modes.md:147`
- 问题描述：World Rules 表写 Arena `visibility.fog_of_war = false（全场可见）`，但 gameplay 的竞技观战示例写 `fog_of_war=true`，观众通过延迟全图观看；modes 也强调 Arena 旁观由房间可见性控制、回放按房间公开。
- 影响分析：Arena 公平性取决于 drone 感知是否受限。若竞技 bot 也全场可见，策略空间会偏向完美信息；若只有观众延迟全图，玩家代码仍是 fog-of-war 策略。
- 修复建议：区分 `drone_fog_of_war` 与 `spectator_visibility`。建议 Arena 默认：玩家 WASM `fog_of_war=true`，spectator/replay 可延迟全图。

### M2. Tutorial 10 分钟 Golden Path 与 Feedback Loop 5 分钟教程目标不一致

- severity: Medium
- 文件引用：`/data/swarm/docs/design/gameplay.md:5`, `/data/swarm/docs/design/gameplay.md:26`, `/data/swarm/docs/specs/gameplay/06-feedback-loop.md:23`, `/data/swarm/docs/specs/gameplay/06-feedback-loop.md:25`
- 问题描述：gameplay 定义从登录到首个 PvE 挑战 ≤10 分钟；Feedback Loop 定义人类程序员 5 分钟教程，但教程步骤与 PvE 挑战、部署到 World、safe/soft_launch 的边界没有统一。
- 影响分析：5 分钟学会按钮与 10 分钟完成首个 PvE 是两个不同目标。若验收不区分，CI smoke test 和 UX 指标会互相覆盖。
- 修复建议：拆成两个目标：5 分钟完成 Tutorial 操作闭环；10 分钟完成 Tutorial PvE 或 Arena PvE challenge。每个目标给出独立验收。

### M3. Special attack 的成本与抗性在设计层仍有局部冲突

- severity: Medium
- 文件引用：`/data/swarm/docs/design/gameplay.md:761`, `/data/swarm/docs/design/gameplay.md:1089`, `/data/swarm/docs/design/gameplay.md:1213`, `/data/swarm/docs/specs/core/07-world-rules.md:850`, `/data/swarm/docs/specs/core/07-world-rules.md:1080`
- 问题描述：Leech 表格写受 Kinetic 抗性影响，但 special_effect 定义 leech resistance 为 Corrosive；Fabricate 表格成本为 800 Energy，默认 custom_actions 为 2000 Energy + 500 Matter；World Rules 的特殊攻击表只列到 Fortify，缺 Leech/Fabricate。
- 影响分析：特殊攻击是专家策略空间的核心，成本/抗性冲突会导致 counterplay 无法学习。Leech 到底是 Kinetic 吸血还是 Corrosive 特效，会影响 body/resistance meta。
- 修复建议：为 8 个特殊攻击建立单一 canonical table，包含 body part、damage_type、resistance、cost、cooldown、range、channel、counterplay，并让 design/spec/IDL 都引用它。

### M4. `swarm_get_objectives` 可能引入资源奖励逃逸路径

- severity: Medium
- 文件引用：`/data/swarm/docs/specs/reference/game_api.idl.yaml:687`, `/data/swarm/docs/specs/core/09-snapshot-contract.md:269`, `/data/swarm/docs/specs/core/09-snapshot-contract.md:280`
- 问题描述：`swarm_get_objectives` output schema 包含 `reward` 对象，语义是“what you get on completion”；Snapshot Contract 又禁止 Challenge Board 直接资源奖励，资源注入唯一合法路径是 PvEAward。
- 影响分析：如果 objectives 的 reward 可表达资源，会诱导 UI/AI 认为任务完成可直接发资源，绕开 Resource Ledger 的 PvE Award 预算。
- 修复建议：将 objective reward 类型改为 non-resource reward 或明确 resource reward 仅是 `PvEAward` 的展示视图，必须带 ledger operation id 和 budget source。

## Low / Nits (可选改进) (L1..Ln)

### L1. 文档存在重复标题和旧修复标记

- severity: Low
- 文件引用：`/data/swarm/docs/design/economy-balance-sheet.md:3`, `/data/swarm/docs/design/economy-balance-sheet.md:175`, `/data/swarm/docs/design/economy-balance-sheet.md:177`
- 问题描述：Balance Sheet 开头仍写 “R15 B7 + B6/D3/D4 修复”，且 §2.7 标题重复两次。
- 影响分析：旧评审修复标记会让文档看起来像历史补丁而非干净目标状态；重复标题影响可读性。
- 修复建议：删除旧修复标记，合并重复标题。

### L2. 部分配置示例使用浮点，破坏定点叙事一致性

- severity: Low
- 文件引用：`/data/swarm/docs/specs/core/07-world-rules.md:49`, `/data/swarm/docs/specs/core/07-world-rules.md:58`, `/data/swarm/docs/specs/core/07-world-rules.md:103`, `/data/swarm/docs/specs/core/07-world-rules.md:109`, `/data/swarm/docs/specs/core/07-world-rules.md:985`
- 问题描述：world-rules 示例仍出现 `decay_rate = 0.0`、`0.001`、`transfer_to_global_cost = { Energy = 0.01 }`、`damage_multiplier = 1.0`、`special_param: float`。
- 影响分析：虽然可能是配置表现层，但与“所有百分比/费率禁浮点”的确定性叙事冲突，容易误导服主和实现者。
- 修复建议：示例统一使用 bp/ppm/fixed 表示，例如 `transfer_to_global_fee_bp = 100`、`damage_multiplier_bp = 10000`、`special_param_bp = 5000`。

## Strengths (设计亮点)

- 10 分钟 Golden Path 与 Learn/Decide/Act/Understand 闭环方向正确，尤其同时考虑人类 Web UI 和 AI MCP 的学习路径，能支撑“AI 和人类同走 WASM”这一核心卖点（`/data/swarm/docs/design/gameplay.md:5`, `/data/swarm/docs/specs/gameplay/06-feedback-loop.md:9`）。
- World 与 Arena 的定位差异有清晰产品直觉：World 接受不公平的有机沙盒，Arena 追求对称初始条件和算法对抗，适合承载不同动机模型（`/data/swarm/docs/design/modes.md:9`）。
- Resource Ledger 的单入口账本、TickTrace 归因和定点费率原则是正确方向，能为经济审计、回放和反滥用提供强基础（`/data/swarm/docs/specs/core/08-resource-ledger.md:9`）。
- Global/Local storage 双层模型很有策略空间：全局便捷但有税和延迟，本地隐匿但需要物流并可被掠夺，符合 MMO RTS 的长期博弈（`/data/swarm/docs/design/gameplay.md:282`）。
- soft_launch、First-Attack Shield、PvE 低风险冲突等新手过渡机制方向良好，能缓解 Screeps-like 游戏常见的“保护期结束瞬间被清场”问题（`/data/swarm/docs/design/gameplay.md:529`）。
- OverloadPressure 可见性设计较成熟，既给被攻击者反馈和反制信息，又避免通过不可见 attacker contribution 反向定位隐身单位（`/data/swarm/docs/design/gameplay.md:789`）。

## CrossCheck — 需要跨方向检查

- CX1: API Registry 声称由 IDL 自动生成但与 YAML 源在版本、工具数、host function 和 category 上冲突 → 建议 API/Tooling 检查 codegen 是否真实可复现、CI 是否覆盖 registry drift。
- CX2: `host_get_random` 是否应进入机器 IDL，以及 deterministic random bytes 是否会成为玩家策略输入 → 建议 Determinism/Security 检查 replay seed、domain separation 和信息泄露边界。
- CX3: Rhai RuleMod 能力白名单在 design/gameplay 与 world-rules 中描述不完全一致，且涉及 `actions.add_body_part_type` / `actions.add_damage_type` / `actions.register_action_handler` → 建议 Modding/Engine 检查 RuleMod ABI 是否真支持这些能力且不绕过 validation。
- CX4: Allied Transfer 拦截的成功率公式使用百分比和 escort 判定，可能涉及 RNG、可见性和 TickTrace 审计 → 建议 Determinism/Security 检查固定点表达、RNG 输入、oracle 风险和 replay 字段。
- CX5: Snapshot truncation 关键实体和 competitive degraded tick 可能影响 Arena 判胜与 replay 公信力 → 建议 Engine/UX 检查截断后 UI/API 如何向玩家展示 tick_integrity。
- CX6: API 中 `swarm_get_code` 暴露 code bytes，虽然 visibility_filter=owner，但涉及源码/隐私边界 → 建议 Security/Auth 检查 scope、owner 判定和 replay_with_source 设计一致性。
- CX7: Economy Balance Sheet 声称部分精确参数推迟 playtest，但任务要求检查 PLAYTEST-GATED 追踪；本轮禁止读取非指定文件，无法确认追踪状态 → 建议 Speaker 或 Docs Governance 检查 `PLAYTEST-GATED.md` 是否登记经济曲线、storage tax、special attack 等 playtest-gated 项。
