# R43 Phase 1 Clean-Slate 独立评审 — rev-gpt-design-economy

## 1. Verdict

REQUEST_MAJOR_CHANGES

核心设计方向有明显亮点：Swarm 已经形成了「代码效率 → 资源流 → 维护曲线 → 物流/反雪球」的完整策略闭环，并且对新手、AI agent、Arena 测试场都有专门设计。但从设计与经济视角看，当前文档仍存在几处必须修复的重大问题：经济权威数值在不同文档之间冲突、early/mid game 自维持曲线叙述互相矛盾、PvE/Boss/挑战内容边界不一致，以及玩家可理解的经济反馈尺度仍没有被目标文档闭合。这些问题会直接影响玩家预期、策略空间和实现侧调参基准，因此建议 REQUEST_MAJOR_CHANGES。

## 2. 发现的问题

### D-ECO-1 — High

文件引用：
- `/data/swarm/docs/specs/core/resource-ledger.md:143-150`
- `/data/swarm/docs/design/economy-balance-sheet.md:35-40`
- `/data/swarm/docs/design/economy-balance-sheet.md:61-83`
- `/data/swarm/docs/design/economy-balance-sheet.md:178-202`
- `/data/swarm/docs/specs/gameplay/PLAYTEST-GATED.md:9-27`
- `/data/swarm/docs/specs/gameplay/PLAYTEST-GATED.md:30-48`

问题描述：
Resource Ledger 的 Growth Path 表仍声明 `Tick 0–500` 有 `Controller income (50/tick)`，并在 `2000+` 阶段标记 `Full economy` 为自维持；但 Economy Balance Sheet 的显式假设写的是 Controller 每级被动收入基础 `2/tick`，并进一步说明 1 房 free_upkeep 结束后基础收入约 `22/tick`、维护费 `55/tick`、净流量 `-33/tick`，需要 2 房或代码效率提升才能转正。Balance Sheet 汇总又把自维持区间定义为 `2-10 房间`，其中 5 房优化后仅收支平衡、20 房后转亏。PLAYTEST-GATED 还保留了「Standard balance sheet 中 1/5/20/50 房 net flow 全为负，而 resource-ledger.md 声称 tick 2000+ 自维持」的旧问题描述。

影响分析：
这是核心经济曲线的目标状态冲突。玩家会从 Resource Ledger 得到「tick 2000 后完整经济可自维持」的承诺，但从 Balance Sheet 得到「必须 2 房、优化代码、RCL/PvE 补充后才可能转正」的承诺。对新手而言，这会直接影响第一小时动机模型：如果 free_upkeep 结束后没有明确的可执行转正路线，玩家会把维护费理解为惩罚；如果文档说已经自维持但实际曲线要求扩张，则策略学习反馈会断裂。对专家而言，这也会影响是否应该 rush 第二房、优化 harvesting、还是追 PvE drop 的判断。

修复建议：
以 Economy Balance Sheet 的 canonical target curve 为准，统一 Resource Ledger §2.3 Growth Path：
1. 将 `Controller income (50/tick)` 改为与 Balance Sheet 一致的 RCL passive income 模型，或明确该 50/tick 是 tutorial/safe-mode subsidy 而非 Controller 常规收入。
2. 将 `2000+ Full economy ✅ 自维持` 改为更精确的条件式目标：例如「若玩家已达 ≥2 rooms + 优化 harvesting + RCL2-3，则可小幅正流量；单房会进入 upkeep deficit」。
3. PLAYTEST-GATED 中 PG-1/PG-4 应更新为当前目标曲线的待验证项，不应继续描述已被 Balance Sheet 重写后的旧冲突。
4. 在 Golden Path/First-Hour 文档中补一条明确策略目标：「free_upkeep 结束前完成第二房或达到等价效率提升」。

### D-ECO-2 — High

文件引用：
- `/data/swarm/docs/design/gameplay.md:117-229`
- `/data/swarm/docs/specs/reference/api-registry.md:849-857`
- `/data/swarm/docs/specs/core/resource-ledger.md:65-101`

问题描述：
建筑成本在玩法设计和 API Registry 的经济操作表中显著不一致。Gameplay 的 `[[structure_types]]` 默认值中，PowerSpawn cost = `5000`、Nuker cost = `100000`、Depot cost = `5000`；但 API Registry 的 BuildCost 表写的是 PowerSpawn=`1200`、Nuker=`5000`、Depot=`600`。Resource Ledger §2 作为经济数学权威又没有列出完整 BuildCost 参数表，只在 API Registry 中出现 BuildCost 数值。

影响分析：
这些不是小的数值偏差，而是改变策略空间的数量级差异。Depot 如果是 600，前线维修节点会成为近乎廉价的标准后勤件；如果是 5000，则是战略投资。Nuker 如果是 5000，属于中后期可频繁建造的武器；如果是 100000，则是稀缺终局资产。PowerSpawn 1200 vs 5000 也会改变 RCL7 后的升级节奏。当前文档无法支持玩家或实现者形成稳定经济直觉。

修复建议：
1. 在 Resource Ledger §2 统一参数表中补全 canonical BuildCost 表，作为唯一经济权威。
2. Gameplay 的 `[[structure_types]].cost` 与 API Registry §10.2 BuildCost 必须逐项对齐；如果 Gameplay 只是示例，也必须移除具体数值或标注「引用 Resource Ledger canonical cost」。
3. 对 Depot、Nuker、PowerSpawn 这类改变战略节奏的建筑，补一句设计意图：Depot 是前线后勤投资还是廉价消耗品；Nuker 是终局稀缺威慑还是高阶常规武器。

### D-ECO-3 — High

文件引用：
- `/data/swarm/docs/design/modes.md:71-85`
- `/data/swarm/docs/design/modes.md:177-203`
- `/data/swarm/docs/specs/core/resource-ledger.md:202-219`

问题描述：
World PvE 章节明确说深度 PvE（Boss 战多阶段 AI、副本区域链、声望等）不作为原生引擎内容，属于 overhaul mod；但 Arena PvE Challenge 的预设场景又包含 `Ruin Siege`：地图中心遗迹有 `Boss NPC（1000 HP、多阶段 AI）`。这使「原生 PvE 内容边界」不一致。Resource Ledger 也已经提供 T3 `Boss Drone` 奖励层级，但 Modes 文档一边说 Boss 是 mod，一边又把 Boss 放进官方 Arena Challenge。

影响分析：
PvE 是新手过渡、经济 faucet 和风险回报曲线的核心组成。若 Boss/multi-stage AI 是官方挑战内容，则它会成为玩家学习 combat/special attack 的重要目标，也会影响 Arena PvE 排行榜的动机模型；若它只属于 mod，则官方 Challenge 不应以 Boss 为默认预设。当前冲突会让玩家不知道 PvE 的目标层级：到底是轻量训练靶、经济 catch-up、还是正式高阶 PvE 终局。

修复建议：
二选一并全局统一：
1. 若官方 Arena PvE 保留 Boss 场景，则把 Modes §9.0 的「Boss 战多阶段 AI 属于 overhaul mod」改为「World 持久生态不内置深度 Boss；Arena Challenge 可提供隔离的官方 Boss 场景，不产出 World 资源」。同时在 Resource Ledger 明确 Arena Boss 不进入 World PvE faucet。
2. 若 Boss 确实只属于 mod，则将 `Ruin Siege` 改为非 Boss 的 Guardian/Ruin challenge，删除「多阶段 AI」措辞。

### D-ECO-4 — Medium

文件引用：
- `/data/swarm/docs/design/gameplay.md:338-363`
- `/data/swarm/docs/design/gameplay.md:379-387`
- `/data/swarm/docs/specs/core/resource-ledger.md:85-118`
- `/data/swarm/docs/specs/gameplay/PLAYTEST-GATED.md:73-89`
- `/data/swarm/docs/design/economy-balance-sheet.md:254-257`

问题描述：
Storage tax 的公式和 tier 已经定义，但玩家可理解的时间尺度仍未被目标文档闭合。PLAYTEST-GATED 明确写出当前缺口：`bp/tick` 需要 per-hour/per-day 人类可读单位、PvE 收益需要 early/mid/late 定位、1%/5% round-trip 成本需要数学理由或可接受解释。Balance Sheet 虽然有局部税额重算，但没有把「0.01%/tick、0.05%/tick、0.20%/tick」翻译成玩家会感知的存储半衰期、日损耗或策略建议。

影响分析：
税率是 anti-snowball 的核心 UX。玩家不会自然理解 bp/tick 的严重程度，尤其 Swarm tick 为持续世界循环时，0.20%/tick 看起来很小，但长时间累计可能非常强。缺少人类尺度会导致两种误读：新手以为税很轻而囤满全局仓库；专家以为系统惩罚长期存储而转向本地囤积，形成与设计目标不一致的 dominant strategy。

修复建议：
不需要等 playtest 才能补「解释层」。建议在 Resource Ledger 或 Balance Sheet 中增加固定展示：
1. 每个 storage tier 的 per 100 tick / per 1000 tick 示例损耗。
2. 对 1,000,000 capacity 下 45%、75%、90% stored_total 的税额、持续 100 tick 后损耗、何时应转本地存储的提示。
3. 解释 1% deposit + 5% withdraw 的 round-trip 设计意图：防战斗瞬移补给、鼓励本地物流与提前规划。
数值校准可继续 playtest-gated，但玩家解释不应 gated。

### D-ECO-5 — Medium

文件引用：
- `/data/swarm/docs/design/gameplay.md:5-27`
- `/data/swarm/docs/specs/gameplay/feedback-loop.md:23-37`
- `/data/swarm/docs/specs/gameplay/feedback-loop.md:83-140`
- `/data/swarm/docs/specs/gameplay/feedback-loop.md:152-187`

问题描述：
Onboarding 时间承诺和学习目标分散且不完全一致。Gameplay 定义「10 分钟 Golden Path」到首个 PvE 击杀；Feedback Loop 定义「5 分钟教程」到部署 World/Arena，又定义 first-hour 过渡、safe_mode/soft_launch/PvP 接触，还要求 CI smoke test 覆盖 starter bot 编译、dry-run、部署。各段都合理，但缺少一张统一的玩家学习阶梯，把 5 分钟教程、10 分钟 PvE 击杀、first-hour PvP 过渡、AI agent 首次部署反馈整合成一条目标状态。

影响分析：
Swarm 的核心门槛是「写代码玩 RTS」。学习曲线必须极其清晰，否则玩家会在「能编译」和「知道如何变强」之间断裂。当前文档能描述单个环节，但没有把经济目标（第二房/收支平衡）、战斗目标（首次 PvE/PvP）、调试目标（explain_last_tick/dry_run）串成递进 motivation loop。

修复建议：
新增或合并一张 onboarding ladder：
- 0–5 min：改 starter bot，看到 drone 行动。
- 5–10 min：完成首个 PvE 击杀/资源事件。
- 10–30 min：达到 free_upkeep 结束前的经济目标，例如第二房或等价采集效率。
- 30–60 min：经历 soft_launch 事件、首次低风险冲突、Arena Challenge。
并明确每阶段对应 Web UI/MCP 反馈入口与成功指标。

### D-ECO-6 — Medium

文件引用：
- `/data/swarm/docs/design/gameplay.md:441-453`
- `/data/swarm/docs/specs/gameplay/feedback-loop.md:301-319`
- `/data/swarm/docs/specs/gameplay/feedback-loop.md:321-342`
- `/data/swarm/docs/design/modes.md:9-24`

问题描述：
长期目标系统列出了殖民地年龄、GCL、RCL、Arena 段位、PvE 里程碑、Replay 声誉等多条目标线；Feedback Loop 又列出策略指标仪表盘、回放排行榜、Arena 赛后回放；Modes 明确 World 不追求公平且不设竞争榜单。文档总体方向正确，但缺少「World 非竞争统计 vs Arena 竞争排名 vs PvE Challenge 排行榜」的产品边界表。

影响分析：
持久世界如果展示 GCL/rooms/drones，玩家很容易把它当排行榜，从而与「World 不追求公平」冲突；Arena/PvE Challenge 如果有排行榜，又需要避免 World 资产优势渗透。目标边界不清会影响玩家动机：新玩家可能被 World 大帝国榜单劝退，专家可能把非竞争统计优化成唯一目标，削弱横向策略空间。

修复建议：
补一张 progression/recognition matrix：
- World：非竞争 showcase，只展示自身趋势、邻域事件、Replay 声誉，不做全服排序或默认排名。
- Arena PvP：可排名，按 room/match result 与赛季/段位隔离。
- Arena PvE：按 scenario+difficulty 排行，明确不使用 World 资产。
- PvE World：仅里程碑/事件贡献，不给可交易奖励榜单。

### D-ECO-7 — Low

文件引用：
- `/data/swarm/docs/specs/gameplay/PLAYTEST-GATED.md:1-6`
- `/data/swarm/docs/specs/gameplay/PLAYTEST-GATED.md:93-101`
- `/data/swarm/docs/specs/core/resource-ledger.md:305-314`
- `/data/swarm/docs/specs/core/snapshot-contract.md:274-287`

问题描述：
给定评审原则要求文档呈现目标状态、不是历史路线图；但 PLAYTEST-GATED 仍以「R27 未闭合项」「来源」「Speaker Verdict」「D-item 裁决」等历史评审追踪格式呈现，Resource Ledger/Snapshot Contract 也存在「远期入口」「Out-of-Scope」「当前不实现」这类路线图/范围管理语言。

影响分析：
这不是单纯格式问题。设计读者会把这些内容理解为「尚未裁定」或「以后再说」，削弱经济系统边界的权威性。尤其市场、合约、Merchant、P2P 交易等经济入口，如果只是 out-of-scope 而没有目标边界，会让 mod/core 分界不清。

修复建议：
将 PLAYTEST-GATED 改写为「Empirical Calibration Requirements」：只保留需实证校准的指标、采样方法、闭合条件，不保留评审历史和旧状态。将「远期入口 / 当前不实现」改为目标边界语言，例如「Non-Core Economic Extensions：核心经济不包含 X；若世界需要 X，必须作为 mod 并满足 Resource Ledger 审计接口」。

## 3. 亮点

1. 经济闭环设计方向强：Source faucet、Spawn/Build sink、Storage tax、Empire upkeep、global/local transfer loss、PvE budget 共同形成了可调的资源流网络。特别是 `2-10 房间可自维持、20+递减、50 软上限` 的目标曲线具备清晰 anti-snowball 意图。

2. 新手保护不是简单无敌：safe_mode、soft_launch、First-Attack Shield、低风险 PvE/资源竞争、Arena Challenge 等机制组合，能把「突然被老玩家清场」改造成渐进式学习压力。这符合 MMO RTS 的长期留存需求。

3. AI agent 与人类玩家路径一致：MCP 不直接操作 drone，而是学习、生成、验证、部署 WASM；配合 `swarm_explain_last_tick`、`swarm_dry_run`、`swarm_get_deploy_status`，形成了 AI 可调试的 feedback loop，而不是给 AI 特权接口。

4. 物流作为策略空间被认真对待：global/local 双层存储、deposit/withdraw delay、Restricted Allied Transfer、运输中拦截、Depot 前线维修，都在把资源优势转化为空间/时间/风险决策，而不是单纯账户数字。

5. Arena 与 World 的差异定位清楚：World 接受不公平和持久涌现，Arena 追求隔离、公平、可复现算法对抗。Arena PvE Challenge 不产出 World 资源这一点很好地避免了测试场污染持久经济。

6. 经济可观测性设计充分：Web UI 经济仪表盘、MCP economy tools、idle/negative-flow/storage tier warnings、drone efficiency 等机制能把复杂经济模型转译为玩家可行动的反馈。

## 4. CrossCheck — 需要跨方向检查

- CX1: `api-idl.md` 的 RejectionReason 示例列表与 `api-registry.md` canonical 48 codes 看起来不完全一致，例如 Registry 包含 `InsufficientResource`，而 `api-idl.md:67-115` 的枚举块未列出该项 → 建议 Architect/API 方向检查 IDL YAML、Registry、生成文档三方是否真实一致。

- CX2: `api-registry.md:964-975` 保留日期化 changelog，`PLAYTEST-GATED.md` 保留 R27 历史追踪格式，可能违反本仓库「设计即目标状态、git 记录历史」的文档约定 → 建议 Cross-Cutting/Docs Governance 方向检查哪些 reference/spec 文档仍含历史版本、日期、Phase/R 状态语言。

- CX3: `snapshot-contract.md:360-377` 的 Training debug 示例使用 `distance: 12.53`、`required_range: 5.0`、`action_range: 3.0` 等浮点表示；即便只是展示层，也可能与 fixed-point determinism contract 产生术语冲突 → 建议 Engine/Determinism 方向检查 debug payload 是否应统一使用 milli_distance 或 fixed-point 展示。

- CX4: `modes.md` 的 World PvE、Arena PvE Challenge 与 Resource Ledger PvEAward budget 横跨玩法、账本、排行榜与回放隐私；Boss/Challenge/World faucet 的边界需要跨玩法与经济共同裁定 → 建议 Gameplay + Economy + API 方向联合检查 PvE scenario 是否影响 `swarm_match_result`、排行榜、PvEAward 和 replay schema。

- CX5: `Resource Ledger` 中 Allied Transfer、GlobalDeposit/Withdraw 的拦截条件涉及 visibility、PvP state、alliance state、destination_room、escort 自动判定 → 建议 Security/Engine 方向检查其是否会产生信息泄露、TOCTOU 或 replay 非确定性。