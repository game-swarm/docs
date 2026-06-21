# R32 Design & Economy Review — GPT-5.5

## 1. Verdict

REQUEST_MAJOR_CHANGES

核心玩法方向有明显亮点：10 分钟 Golden Path、World/Arena 双循环、经济仪表盘、Resource Ledger 单入口、PvE budget、多层 anti-snowball 都在朝正确方向收敛。但当前文档仍存在若干必须修复的目标状态冲突：Standard 经济曲线与“可自维持/高效经济可接近平衡”的玩家动机不一致；多个权威文件对 API 工具数量、CommandAction 数量、MVP/Phase/P0 语义、全局转移延迟、存储税、alliance 上限、特殊攻击数值给出冲突定义。对设计与经济方向而言，这会破坏新手→专家学习曲线、玩家策略预期和 AI agent 的可学习性，因此请求重大修改。

## 2. 发现的问题

### DE-1 — High — Standard 经济曲线全阶段净亏损，和“优化代码可自维持”的动机模型冲突

- 文件引用：`/tmp/swarm-review-R32/design/economy-balance-sheet.md:59`
- 文件引用：`/tmp/swarm-review-R32/design/economy-balance-sheet.md:78`
- 文件引用：`/tmp/swarm-review-R32/design/economy-balance-sheet.md:100`
- 文件引用：`/tmp/swarm-review-R32/design/economy-balance-sheet.md:123`
- 文件引用：`/tmp/swarm-review-R32/design/economy-balance-sheet.md:147`
- 文件引用：`/tmp/swarm-review-R32/design/economy-balance-sheet.md:171`
- 文件引用：`/tmp/swarm-review-R32/specs/core/08-resource-ledger.md:143`
- 问题描述：Balance Sheet 显示 Standard 在 free_upkeep 结束后 1 房净亏损 -33/tick，2 房优化后仍 -54，5 房优化后 -195，10 房优化后 -225，20/50 房大幅亏损；但 Resource Ledger 的 Growth Path 声称 2000+ Full economy “✅ 自维持”。同一目标设计里，玩家被告知“优化代码→可接近平衡/自维持”，数值表却显示几乎所有扩张阶段都是负收益。
- 影响分析：这会让经济模型从“代码效率创造优势”变成“维护费倒计时死亡螺旋”。新手在保护期结束后发现优化也不能盈利，会把失败归因于系统不公平而不是策略不足；专家也缺少正反馈窗口，只剩依赖 PvE/联盟补贴维持赤字。Anti-snowball 应该压制无脑扩张，而不是让正常成长路径全段亏损。
- 修复建议：以 Resource Ledger 为唯一数学权威，重新校准 `base_upkeep`、`room_soft_cap`、source/RCL/PvE 收入或升级收益，使 Standard 至少存在明确的 break-even corridor：例如 2–3 房低效略亏、5–10 房高效代码可小幅正收益、20 房顶尖代码+PvE 接近平衡、50 房明显亏损作为软上限。Balance Sheet 需把“基础/优化/顶尖”三档效率和对应 break-even 条件写成闭环，而不是所有阶段净亏损。

### DE-2 — High — 目标状态文档仍使用 Phase/MVP/P0/P1+ 语义，违反 Clean-Slate 设计即目标状态原则

- 文件引用：`/tmp/swarm-review-R32/design/modes.md:12`
- 文件引用：`/tmp/swarm-review-R32/design/modes.md:88`
- 文件引用：`/tmp/swarm-review-R32/specs/gameplay/06-feedback-loop.md:5`
- 文件引用：`/tmp/swarm-review-R32/specs/gameplay/06-feedback-loop.md:340`
- 文件引用：`/tmp/swarm-review-R32/specs/core/09-snapshot-contract.md:181`
- 文件引用：`/tmp/swarm-review-R32/specs/core/09-snapshot-contract.md:421`
- 问题描述：多处仍将设计描述为 “MVP 核心”、“P0”、“P1+”、“MVP 功能清单”、“MVP 经济边界”、“版本 MVP/Future”。这与本轮评审原则中的“设计即目标状态，不区分 Phase/MVP/迭代”直接冲突。
- 影响分析：设计文档会被实现者和玩家解读为路线图而非最终规则合同，导致哪些功能属于核心体验、哪些属于未来扩展无法判断。尤其 Arena、Tournament、经济边界、反馈循环被阶段标签切开后，玩家动机模型和产品承诺会变得不稳定。
- 修复建议：将所有 MVP/P0/P1+ 语义改写为目标状态分类：`Core Ruleset`、`Optional Module`、`Out-of-Scope RFC`、`Product Surface` 等。保留“不进入核心”的边界可以，但不要用阶段路线图措辞；若某项是最终核心，就直接作为当前目标状态写入。

### DE-3 — High — API 工具数量与 CommandAction 数量在权威/说明文档间冲突，破坏 AI agent 学习路径

- 文件引用：`/tmp/swarm-review-R32/design/interface.md:19`
- 文件引用：`/tmp/swarm-review-R32/specs/reference/api-registry.md:254`
- 文件引用：`/tmp/swarm-review-R32/specs/reference/api-registry.md:932`
- 文件引用：`/tmp/swarm-review-R32/design/interface.md:112`
- 文件引用：`/tmp/swarm-review-R32/specs/gameplay/08-api-idl.md:115`
- 文件引用：`/tmp/swarm-review-R32/specs/reference/api-registry.md:48`
- 问题描述：interface 写“56 game tools + 11 auth tools”，Registry 正文写“57 个活跃工具 + 11 Auth API 工具”，Registry changelog 又写 “MCP tools 总数为 56 active”。同时 interface 写 CommandAction 为 21 个，API IDL spec 注释仍写 “19 指令”，Registry 写 21。
- 影响分析：AI agent onboarding 依赖 schema/docs 一致性；工具数量和动作数量不一致会让 agent 无法判断 registry 是否可信。对于编程游戏，API 学习成本就是核心 UX 成本，权威源冲突会直接损害“AI 与人类同路径”的设计承诺。
- 修复建议：以 `/tmp/swarm-review-R32/specs/reference/api-registry.md` 的生成正文为单一事实源，统一所有概述文档的数字；同时修正 Registry changelog 的 56/57 冲突，或解释 active/game/auth shortcut 的计数口径。`08-api-idl.md` 中所有“19 指令”应改为引用 Registry §1，不保留过期数字。

### DE-4 — High — Economy 权威源自身含浮点与数值冲突，削弱确定性经济合同

- 文件引用：`/tmp/swarm-review-R32/specs/core/08-resource-ledger.md:13`
- 文件引用：`/tmp/swarm-review-R32/specs/core/08-resource-ledger.md:68`
- 文件引用：`/tmp/swarm-review-R32/specs/core/08-resource-ledger.md:81`
- 文件引用：`/tmp/swarm-review-R32/design/gameplay.md:2002`
- 文件引用：`/tmp/swarm-review-R32/specs/core/09-snapshot-contract.md:196`
- 文件引用：`/tmp/swarm-review-R32/specs/core/08-resource-ledger.md:83`
- 问题描述：Resource Ledger 原则要求所有百分比和费率使用 basis points/ppm、禁止浮点，但统一参数表中 `allied_daily_cap_world_multiplier` 单位为 float。Snapshot Contract 又写 StorageTax 为 “0.1%/tick”，而 Resource Ledger 的 tier 为 0/1/5/20 bp（即最高 0.20%/tick，且按分层容量计算）。此外 gameplay 确定性合同明确 Rhai 和游戏数值禁用浮点。
- 影响分析：经济系统是策略推理的基础。若权威文件既禁止 float 又引入 float，服主配置和 SDK 生成会出现不确定口径；若存储税被概括为 0.1%/tick，玩家会误判囤积成本，影响是否使用全局存储、本地隐匿和市场策略。
- 修复建议：将 `allied_daily_cap_world_multiplier` 改为定点 `BasisPoints` 或 `MultiplierBps`，如 Standard=10000、Arena=5000、Tutorial=50000。Snapshot Contract 中不要重述“0.1%/tick”，改为“tiered StorageTax，权威公式见 Resource Ledger §2.2”。所有经济费率只保留整数定点。

### DE-5 — Medium — Global transfer 延迟命名/默认值不一致，影响物流策略直觉

- 文件引用：`/tmp/swarm-review-R32/design/gameplay.md:311`
- 文件引用：`/tmp/swarm-review-R32/design/gameplay.md:313`
- 文件引用：`/tmp/swarm-review-R32/specs/core/08-resource-ledger.md:75`
- 文件引用：`/tmp/swarm-review-R32/specs/gameplay/08-api-idl.md:277`
- 文件引用：`/tmp/swarm-review-R32/specs/gameplay/08-api-idl.md:283`
- 问题描述：gameplay 将本地→全局 deposit delay 定义为 10 tick，全局→本地 withdraw delay 定义为 100 tick；Resource Ledger 统一参数表只有 `global_transfer_delay = 100 tick`，说明为全局提取延迟；API IDL 使用 `global_deposit_delay` 和 `global_withdraw_delay` 两个变量但不在 Resource Ledger 参数表中同时定义。
- 影响分析：物流策略依赖“入库快、出库慢”还是“双向统一 100 tick”的差异。前者鼓励把前线收入较快沉入全局、提前规划提取；后者会显著改变全局存储可用性和战时补给节奏。
- 修复建议：在 Resource Ledger §2.1 明确拆成 `global_deposit_delay = 10` 与 `global_withdraw_delay = 100`，或统一改为单一 `global_transfer_delay` 并同步 gameplay/API IDL。建议保留双向差异，因为它更符合 No Teleport 与轻物流的直觉权衡。

### DE-6 — Medium — Allied alliance 上限不一致，外交经济规模边界不清

- 文件引用：`/tmp/swarm-review-R32/design/gameplay.md:2135`
- 文件引用：`/tmp/swarm-review-R32/specs/reference/api-registry.md:619`
- 问题描述：gameplay 外交安全写“每玩家最多同时 5 个 active alliance”，API Registry Economy 限制写 Max active alliances = 10。
- 影响分析：联盟数量上限直接决定 Allied Transfer 的网络外部性和大玩家资源互助规模。5 与 10 对 anti-snowball 的影响很大：10 个联盟会显著增强大帝国互保和资源调度能力，可能绕开维护费压力。
- 修复建议：把 max active alliances 纳入 Resource Ledger 或外交规则的单一权威参数表，并同步 Registry。若目标是限制雪球，建议默认 5，并让服主可配置；若保留 10，需要补充为何不会放大联盟经济垄断。

### DE-7 — Medium — Leech/Fabricate 数值与抗性在设计表、special_effect、默认 custom_actions 间不一致

- 文件引用：`/tmp/swarm-review-R32/design/gameplay.md:761`
- 文件引用：`/tmp/swarm-review-R32/design/gameplay.md:762`
- 文件引用：`/tmp/swarm-review-R32/design/gameplay.md:1089`
- 文件引用：`/tmp/swarm-review-R32/design/gameplay.md:1098`
- 文件引用：`/tmp/swarm-review-R32/design/gameplay.md:1199`
- 文件引用：`/tmp/swarm-review-R32/design/gameplay.md:1213`
- 文件引用：`/tmp/swarm-review-R32/specs/gameplay/08-api-idl.md:329`
- 文件引用：`/tmp/swarm-review-R32/specs/gameplay/08-api-idl.md:330`
- 问题描述：特殊攻击表中 Leech 是 Kinetic 伤害、300 Energy、目标 Kinetic 抗性；special_effect 定义中 leech resistance 是 Corrosive；默认 custom_actions 中 Leech 是 Corrosive 15 dmg。Fabricate 表中 cost 为 800 Energy、抗性 EMP；默认 custom_actions 为 2000 Energy + 500 Matter；special_effect resistance 为 Psionic。
- 影响分析：特殊攻击是 Standard/Arena 核心能力。数值和抗性冲突会让玩家无法建立可学习的 counter-play：到底该堆 Kinetic、Corrosive、EMP 还是 Psionic 抗性？Fabricate 的成本差异也会改变它是战术工具还是终局奇招。
- 修复建议：为 8 个特殊攻击建立单一权威表，至少包含 body part、range、cooldown、cost、damage/effect、resistance、counter。其他段落只引用该表。Leech/Fabricate 的抗性与 cost 需一次性统一。

### DE-8 — Medium — Tutorial/Golden Path 的 PvE 时间目标与世界保护曲线可能互相打架

- 文件引用：`/tmp/swarm-review-R32/design/gameplay.md:24`
- 文件引用：`/tmp/swarm-review-R32/design/gameplay.md:26`
- 文件引用：`/tmp/swarm-review-R32/design/gameplay.md:526`
- 文件引用：`/tmp/swarm-review-R32/design/gameplay.md:527`
- 文件引用：`/tmp/swarm-review-R32/specs/gameplay/06-feedback-loop.md:90`
- 问题描述：10 分钟 Golden Path 要求 T+8–10min 完成首个 PvE 击杀；同时 World/Tutorial 保护曲线描述 500 tick safe_mode + 1500 tick soft_launch，且 Tutorial 禁用多项限制。若 tick interval 为 World 3s、Tutorial 1s/Arena 300ms 等多口径并存，玩家到底何时遭遇 PvE、是否在 safe_mode 内战斗并不清晰。
- 影响分析：新手体验的关键是“何时从观察转为主动战斗”。若 safe_mode 被理解为纯学习无压力，首个 PvE 击杀却发生在 10 分钟内，必须说明 Tutorial 世界的 tick interval、PvE spawn 脚本与 safe_mode 关系，否则教程目标不可验证。
- 修复建议：为 Tutorial Golden Path 单独定义 tick interval、scripted NPC spawn 时刻、safe_mode 对 PvE 的作用边界。建议明确：Tutorial PvE challenge 是受控脚本事件，不受正式 World PvP safe/soft_launch 节奏约束。

### DE-9 — Low — 文档引用和标题残留旧修复标签，降低 Clean-Slate 可读性

- 文件引用：`/tmp/swarm-review-R32/design/economy-balance-sheet.md:3`
- 文件引用：`/tmp/swarm-review-R32/specs/core/09-snapshot-contract.md:5`
- 文件引用：`/tmp/swarm-review-R32/specs/core/09-snapshot-contract.md:7`
- 文件引用：`/tmp/swarm-review-R32/specs/core/08-resource-ledger.md:5`
- 问题描述：文档开头仍出现 R15/R22/R23/R27 修复标签和历史修复说明。
- 影响分析：这不是阻塞设计机制的问题，但 Clean-Slate 文档应呈现最终目标状态。历史标签会让读者误以为文档是补丁堆叠，降低权威感。
- 修复建议：将历史修复标签移入 changelog 或完全移除；正文只保留当前目标状态和权威引用。

## 3. 亮点

- 10 分钟 Golden Path 把“登录→SDK→编译→部署→观察→调试→首个 PvE”拆成可验收路径，对编程游戏的新手转化非常关键，尤其覆盖 AI agent 的首轮部署反馈。
- World/Arena 双核心定位清晰：World 接受不公平与持久涌现，Arena 追求对称竞技；这避免了用同一经济模型同时满足沙盒和电竞两种矛盾目标。
- Resource Ledger 单入口是正确方向：把 Local/Global/Allied/PvE/Recycle/Build/Spawn/Tax/Upkeep 放入统一账本，有利于防资源逃逸、审计和经济平衡。
- Anti-snowball 机制组合有策略空间：维护费、存储税、No Teleport、本地隐匿、Controller aging、soft_launch、安全出生共同形成多层约束，而不是单一硬 cap。
- 经济反馈 UX 做得扎实：Web UI 经济总览、趋势、效率、税率预警，以及 MCP `swarm_get_economy` / `swarm_get_drone_efficiency` / `swarm_get_economy_trend` 能让人类和 AI 都理解“为什么经济变差”。
- PvE budget 设计合理：将 NPC 掉落限制在世界再生总量比例内，并按 Global/Zone/Player/Event 四维预算裁决，能避免刷怪经济压倒 PvP/扩张战略。
- 特殊攻击全部暴露反馈而非静默，尤其 OverloadPressure 的 contribution 可见性模型，有助于反制决策与战斗可读性。
- Tutorial/Novice/Standard/Arena 在特殊攻击、物流、税制、保护期上的差异化方向正确，能承载新手学习曲线和专家策略深度。

## 4. CrossCheck

- CX-1: API Registry 写“由 IDL 自动生成”，但同一文件正文与 changelog 数量冲突，可能是 codegen 或手写生成物漂移 → 建议 API/Tooling 方向检查 registry 生成链、active tool 计数口径和 CI gate。
- CX-2: `08-api-idl.md` 示例 schema 仍包含过期 RejectionReason 和 19 指令注释，可能不仅是文档问题，也可能影响 SDK/starter bot 生成 → 建议 API/SDK 方向检查 IDL YAML 与 markdown spec 的同步策略。
- CX-3: Snapshot Contract 中训练模式 debug 示例使用 `distance: 12.53`、`required_range: 5.0` 浮点值 → 建议 Determinism/Core 方向检查所有 debug payload 是否允许 float，还是必须同样用 fixed-point/milli_distance。
- CX-4: Resource Ledger 说 Merchant NPC 是 Future RFC，但 modes.md World PvE 已列 Merchant NPC 常驻事件 → 建议 Gameplay/PvE 方向裁定 Merchant 是核心 NPC 还是 Future RFC，并同步经济边界。
- CX-5: Allied Transfer intercept 的拦截条件依赖接收方房间、escort 与 visibility，可能与 fog-of-war/ally visibility/replay 产生信息泄露边界 → 建议 Security/Visibility 方向检查拦截事件可见性与 oracle 风险。
- CX-6: `global_transfer_delay`、deploy/event 推送、first_tick_executed 等事件可能需要 TickTrace/WS schema 支撑 → 建议 Protocol/API 方向检查事件名、payload 和 replay_class 是否已注册。
