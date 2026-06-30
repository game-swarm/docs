# R41 Phase 1 Clean-Slate 独立评审 — Design & Economy

评审员：rev-gpt-design-economy
评审范围：design/README.md, design/gameplay.md, design/modes.md, design/interface.md, design/economy-balance-sheet.md, specs/gameplay/*, specs/core/08-resource-ledger.md, specs/core/09-snapshot-contract.md, specs/reference/api-registry.md

## 1. Verdict

REQUEST_MAJOR_CHANGES

理由：整体玩法方向、资源账本单入口、World/Arena 双模式和反馈循环设计已经成型，但仍存在几处会直接影响经济曲线可信度、玩家策略预期和 API/规则一致性的阻塞问题。尤其是经济平衡表中的 storage tax 计算错误、Controller/Depot age repair 权威语义互相冲突、Drone P2P 资源交换与 Resource Ledger Out-of-Scope 边界冲突，会导致实现者和服主无法判断最终目标状态。

## 2. 发现的问题

### D&E-1 — High — Economy Balance Sheet 的 storage tax 计算多处错误，导致 anti-snowball 曲线数值证明不可信

文件引用：
- /tmp/swarm-review-R41/design/economy-balance-sheet.md:117-121
- /tmp/swarm-review-R41/design/economy-balance-sheet.md:140-145
- /tmp/swarm-review-R41/design/economy-balance-sheet.md:164-169
- /tmp/swarm-review-R41/design/economy-balance-sheet.md:178-190
- /tmp/swarm-review-R41/specs/core/08-resource-ledger.md:102-118

问题描述：
Resource Ledger §2.2 定义的 tiered storage tax 是按每个容量区间逐 tier 征税：0–30% 为 0bp，30–60% 为 1bp，60–85% 为 5bp，85–100% 为 20bp。但 Balance Sheet 多处少算了 tier 宽度：
- 10 房：capacity=3,000,000，stored=1,650,000，30–60% tier 应税 750,000，税额应为 75/tick；文档写 45/tick。
- 20 房：capacity=2,000,000，stored=1,440,000，30–60% tier 应税 600,000、60–72% tier 应税 240,000，税额应为 60+120=180/tick；文档写 120/tick。
- 50 房：capacity=3,000,000，stored=2,700,000，30–60% 应税 900,000、60–85% 应税 750,000、85–90% 应税 150,000，税额应为 90+375+300=765/tick；文档写 600/tick。

影响分析：
Balance Sheet 是 Standard 经济曲线的证明文档。当前 tax 数值系统性偏低，会高估 10/20/50 房经济可持续性，削弱 storage tax 与 upkeep 共同构成的 anti-snowball 证明。虽然 upkeep 是主要 sink，但该表被用作 canonical target curve 的初始参数化；错误数字会误导后续 playtest 校准方向和服主调参直觉。

修复建议：
按 Resource Ledger §2.2 逐 tier 重算所有 Balance Sheet 场景，并同步更新：
- §2.4 10 房 storage tax 45 → 75，总支出 1,045 → 1,075，净流量相应调整。
- §2.5 20 房 storage tax 120 → 180，总支出 3,160 → 3,220，净流量相应调整。
- §2.6 50 房 storage tax 600 → 765，总支出 16,600 → 16,765，净流量相应调整。
- §2.7 汇总表中相同字段与 tier formula 全部重算。
建议在文档中加一行明确“Balance Sheet 数值由 §2.2 公式逐 tier floor-round 生成”，避免未来再次按单一差额误算。

### D&E-2 — High — Controller age repair 是否存在 50% 上限存在权威冲突

文件引用：
- /tmp/swarm-review-R41/design/gameplay.md:102
- /tmp/swarm-review-R41/design/gameplay.md:523-525
- /tmp/swarm-review-R41/specs/core/08-resource-ledger.md:152-166
- /tmp/swarm-review-R41/design/economy-balance-sheet.md:220-223

问题描述：
design/gameplay.md 的 Vanilla 默认值表声明“Controller 维修：硬上限：每 tick 总 age 回退 ≤ 自然增长的 50%”。但同一文件前文和 Resource Ledger 明确说 Controller repair 免费，只受 repair_range、repair_capacity、确定性队列等物理约束限制，不存在额外全局 repair cap/cost。Economy Balance Sheet 的模式差异表也采用 range/capacity/queue 模型。

影响分析：
这是核心 maintenance curve 冲突：
- 若存在 50% 总 age 回退硬上限，玩家无法通过拥挤排队之外的投入完全抵消 active aging，大规模 drone 运营会形成硬衰减压力。
- 若不存在 50% 上限，玩家可以通过基地/Depot 位置和物流组织维持更长前线持续性，策略空间偏向补给线和拥堵管理。
两者给出的 optimal play 完全不同，会影响 novice→expert 学习曲线、前线远征节奏和 anti-hoarding 机制。

修复建议：
选择一个权威目标状态并全局统一。基于 Resource Ledger 当前语义，建议删除 gameplay.md:523-525 中“硬上限 50%”表述，改为：“Controller age repair：免费；受 RCL repair_range、repair_capacity 和确定性队列限制；无全局 repair cap。”如果设计确实需要 50% cap，则必须把它写入 Resource Ledger §2.4 并说明它如何与 Controller/Depot repair_capacity 组合计算。

### D&E-3 — High — Drone P2P 资源交换协议与 Resource Ledger 的 Out-of-Scope 边界冲突

文件引用：
- /tmp/swarm-review-R41/design/gameplay.md:2001-2009
- /tmp/swarm-review-R41/specs/core/08-resource-ledger.md:305-314
- /tmp/swarm-review-R41/specs/core/09-snapshot-contract.md:262-275

问题描述：
design/gameplay.md 在 Drone 消息机制中明确提出“点对点资源交换协议”，甚至举例 “请求 100 Energy，我用 50 Crystal 交换”，并说引擎不提供撮合/担保、由 WASM 层实现不可信协议。Resource Ledger §7 却把 Drone P2P Offer 标为 Out-of-Scope，替代方案为 Restricted Allied Transfer。Snapshot Contract 也把 Drone P2P Offer / Auction / Escrow 等经济功能划为远期 RFC。

影响分析：
如果 P2P exchange 被视为当前设计的一部分，它会绕过 Resource Ledger 已建立的 Allied Transfer fee/delay/cooldown/daily_cap/new_player_transfer_lock 等 anti-abuse 合同，形成玩家可以通过 local drone transfer + off-ledger messaging 实现的事实市场。若它只是“消息 payload 可以表达报价但没有结算语义”，则文档目前的措辞会让实现者以为需要支持 P2P 交易玩法。该冲突直接影响 resource flow、反刷号、新手资源门和 alliance transfer 的存在意义。

修复建议：
将 gameplay.md 的 Drone 消息机制改写为“消息可承载非权威意图/报价文本，但任何资源结算仍必须通过 Resource Ledger 已定义操作；Drone P2P Offer/escrow/contract settlement 不属于当前核心设计”。保留不可信消息博弈作为社交/协议层玩法，但明确：消息本身不创建任何可执行 resource exchange primitive，不能绕过 new_player_transfer_lock、AlliedTransfer cap 或 Global transfer delay。

### D&E-4 — Medium — Snapshot Contract 的 Economy Boundaries 中 storage tax 描述与 Resource Ledger tiered 公式冲突

文件引用：
- /tmp/swarm-review-R41/specs/core/09-snapshot-contract.md:191-205
- /tmp/swarm-review-R41/specs/core/08-resource-ledger.md:85-118
- /tmp/swarm-review-R41/specs/reference/api-registry.md:856

问题描述：
Snapshot Contract §3.1 把 `StorageTax` 描述为“仓库存储税（0.1%/tick）”。但 Resource Ledger 和 API Registry 定义的是 tiered tax：0–30%=0bp，30–60%=1bp，60–85%=5bp，85–100%=20bp，分别是 0%、0.01%、0.05%、0.20% per tick，不存在统一的 0.1%/tick。

影响分析：
这会让实现者、服主和玩家对存储税强度形成错误直觉。0.1%/tick 在中低 tier 会显著过高，在最高 tier 又低于 0.2%/tick，既破坏新手囤积缓冲，也削弱高存储惩罚。

修复建议：
将 Snapshot Contract line 204 改为“仓库存储税（tiered：0/1/5/20 bp per tick，权威公式见 Resource Ledger §2.2）”。不要在非权威文档写单一税率。

### D&E-5 — Medium — API Registry 仍声明 repair distance decay，与 Vanilla age repair 模型冲突

文件引用：
- /tmp/swarm-review-R41/specs/reference/api-registry.md:561-563
- /tmp/swarm-review-R41/specs/core/08-resource-ledger.md:152-166
- /tmp/swarm-review-R41/design/gameplay.md:102,273-274

问题描述：
API Registry §5.1 同时写“无全局 repair cap — 维修受物理范围和 per-Controller 容量自然限制”，又列出“Repair distance decay = 500 bp/tile”。Resource Ledger §2.4 和 gameplay.md 明确说全局 `repair_cap`、按 `body_cost` 收费的 `repair_cost`、距离衰减收费等比例经济公式不属于 Vanilla age repair 权威模型。

影响分析：
距离衰减会改变 depot/controller 周围站位优化：玩家需要计算距离边际效率，而非只考虑 range/capacity/queue 与物流拥堵。对新手而言，这增加隐藏复杂度；对专家而言，会改变前线 Depot 的最优布局和 drone 排队策略。API Registry 若作为权威输出，将迫使实现包含一个设计文档已排除的机制。

修复建议：
从 API Registry 的 game limits 中移除 Repair distance decay，或明确标为 RFC/mod-only，不属于 Vanilla active limits。若该表由 IDL 生成，则应修正 IDL 源而非手改生成物。

### D&E-6 — Medium — World PvE 默认内容使用 Crystal/Blueprint，但 Vanilla 默认经济宣称单一 Energy，资源学习路径不够一致

文件引用：
- /tmp/swarm-review-R41/design/gameplay.md:517-523
- /tmp/swarm-review-R41/design/modes.md:40-70
- /tmp/swarm-review-R41/design/economy-balance-sheet.md:204-216

问题描述：
Vanilla Ruleset 核心默认值强调默认资源是单一 `Energy`，并且 Balance Sheet 的 Tutorial/Vanilla/Standard starting_resources 都是 `{Energy: ...}`。但 World PvE 生态层的资源据点和掉落表直接使用 `Crystal`、蓝图和 NPC 残骸，如 Rich Vein 产出 Crystal ×2000、Resource Race 采集 Crystal、Guardian 蓝图掉落等。

影响分析：
如果 Standard Vanilla 真的只有 Energy，则 modes.md 的 World PvE 默认内容不能直接作为 vanilla target state；如果 Crystal/Blueprint 是 World PvE 默认内容，则“默认单一 Energy 简化经济模型”的新手承诺被破坏。对新手学习曲线而言，前 10 分钟和 first-hour 阶段需要非常稳定的资源语义；过早引入第二资源与蓝图会增加策略负担。

修复建议：
明确区分：
- Vanilla/Novice/Standard 默认 World PvE 只掉落 Energy；Crystal/Blueprint 示例迁移到 Advanced/modded world 示例；或
- 正式定义 Crystal/Blueprint 是 Standard World 的默认扩展资源，并同步修改 Vanilla Ruleset、Balance Sheet、Resource Ledger 的 PvEAward 和 starting resources 叙述。
从设计一致性看，建议前者：保持 Vanilla 单 Energy，Crystal/Blueprint 作为 mod/Advanced PvE 内容。

### D&E-7 — Low — Feedback Loop 中 Arena 胜利条件与 modes.md 的房间可配置胜利条件表述不一致

文件引用：
- /tmp/swarm-review-R41/specs/gameplay/06-feedback-loop.md:333-342
- /tmp/swarm-review-R41/design/modes.md:21-24,145

问题描述：
Feedback Loop §6 简化描述 Arena 胜利条件为“摧毁敌方 Spawn，或时限结束时分高者胜”。modes.md 则定义了房间可配置的多种 victory_condition：fixed_ticks、destroy_all_structures、full_wipe、capture_points_consecutive/cumulative 等。

影响分析：
这不是机制根本缺陷，但会影响 onboarding 文档和 AI agent 自举时对 Arena 目标的理解。如果教程/文档只教“摧毁 Spawn”，玩家可能无法理解 capture point 或 full wipe 房间为何表现不同。

修复建议：
把 Feedback Loop §6 的 Arena 胜利条件改为引用 modes.md 的可配置 victory_condition，并仅把“摧毁敌方 Spawn/资产评分”作为默认 starter challenge 示例。

## 3. 亮点

1. Golden Path 清晰：design/gameplay.md:5-27 给出了 10 分钟上手路径，Feedback Loop specs/gameplay/06-feedback-loop.md:152-187 又补充了可自动化验收标准。对编程游戏而言，“部署后看到反馈”和“为什么失败”的闭环非常关键，这部分设计方向正确。

2. World 与 Arena 的动机分离明确：design/modes.md:9-24 把持久世界的不公平沙盒和 Arena 的公平算法对决分开，避免用同一套公平性目标扭曲两种玩法。尤其是同一玩家可用多个 WASM 槽位自我对战（modes.md:107）非常适合策略开发与社区分享。

3. Resource Ledger 单入口是正确的经济基础：specs/core/08-resource-ledger.md:11-17 和 47-62 把所有资源流统一进审计账本，能支撑 anti-abuse、replay 和经济调参。这是 MMO 编程游戏防止资源逃逸路径的关键架构。

4. Anti-snowball 目标不是“硬公平”，而是生态可持续：design/gameplay.md:425-439 明确 World 不追求个体公平，而用 storage tax、upkeep、controller aging、soft_launch、安全出生等机制维持长期生态。这比强行把持久世界做成竞技场更符合玩家动机模型。

5. 经济反馈面向人类与 AI 双通道：design/gameplay.md:2173-2219 定义 Web UI 仪表板和 MCP 经济查询/告警，能让玩家把“优化代码”与“经济净流”建立直接因果关系，是编程游戏最重要的学习反馈之一。

6. API/DX 方向基本健康：design/interface.md:47-50 坚持 MCP 不直接做游戏动作，所有玩家都必须写 WASM；api-registry.md:37-85 用 Core CommandAction + ActionRegistry 分离基础操作与可扩展 combat/effect，符合“代码就是军队”的玩法一致性。

## 4. CrossCheck — 需要跨方向检查

CX-1: Resource Ledger 与 API Registry 的 repair distance decay / repair cap 生成源可能仍残留旧字段 → 建议 Core/API 方向检查 IDL YAML 中是否仍声明 `repair_distance_decay` 或相关 active limit，并确保生成物不会重新引入已废弃规则。

CX-2: Drone P2P Offer 的边界需要安全/反滥用复核 → 建议 Security/Economy 方向检查 local transfer + message payload 是否能组合绕过 new_player_transfer_lock、AlliedTransfer cap、daily cap 或 fee/delay。

CX-3: Balance Sheet 经济表应增加自动重算校验 → 建议 Tooling/Docs 方向检查是否可用脚本从 Resource Ledger 参数生成 economy-balance-sheet.md 的 tax/upkeep 数值，避免手算漂移。

CX-4: API Registry 由 IDL 生成但部分文档仍把 Registry 称为权威、同时又说冲突以 IDL YAML 为准 → 建议 API/Docs 方向检查“人读权威”和“机器权威”的措辞层级，避免 reviewer/implementer 不知道冲突时该改 YAML 还是改 markdown。

CX-5: Snapshot Contract 训练模式 debug 示例使用浮点距离 `12.53` / `5.0` → 建议 Determinism/API 方向检查 debug payload 是否允许 human-readable float；若进入 replay/API schema，应改为 milli_distance 定点或明确为展示层格式。
