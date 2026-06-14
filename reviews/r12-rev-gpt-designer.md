# R12 — rev-gpt-designer 设计评审

Reviewer: rev-gpt-designer / GPT-5.5
Scope: /data/swarm/docs/design/DESIGN.md, /data/swarm/docs/design/tech-choices.md, /data/swarm/docs/specs/p0/*.md
Perspective: 游戏设计、第一小时体验、AI 玩家可学性、观战/Replay/社区传播、长期追求

## Verdict

APPROVE_WITH_RESERVATIONS

R12 已经比早期版本明显成熟：核心 fantasy「你的代码就是你的军队」、AI 与人类同走 WASM、MCP 只做屏幕/鼠标而非 gameplay controller、统一可见性、dry-run / explain / replay / starter bot / World vs Arena 双模式，都已经形成可实现的产品骨架。

从游戏设计视角，最大进步是 P0-6 把 LEARN → DECIDE → ACT → UNDERSTAND 的反馈闭环写成了 MVP 阻断项；这使 Swarm 不再只是一个技术上正确的 deterministic sandbox，而开始像一个可以被玩家学会、调试、分享、竞技的游戏。

但我仍建议不要直接进入“大规模 World + 完整经济 + 模组市场”的实现幻想。当前设计最危险的点不是架构，而是 Scope 与 First Hour：文档已经同时承诺了 Screeps-like 持久世界、Arena 竞技、Rhai 模组平台、动态资源经济、全局/本地物流、特殊攻击、市场、观战、Replay、AI MCP 教程。若 Phase 1-2 没有一个极窄的可玩切片，很容易做出一个技术地基很强但第一小时沉默、冷、难懂、不可传播的系统。

裁决：设计方向可通过，但 Phase 1 必须以“第一小时可玩、可理解、可分享”为验收标准，而不是以“架构组件齐全”为验收标准。

## Strengths

1. AI / Human 公平路径已经讲清楚

- DESIGN 和 P0-1/P0-3/P0-9 一致强调：世界只认 WASM；AI 通过 MCP 看世界、写代码、部署 WASM；MCP 不提供 swarm_move / swarm_attack / swarm_build。
- 这是 Swarm 最有辨识度的产品承诺：AI 不是外挂，不是 bot API 特权用户，而是另一种程序员。
- 这点非常适合对外传播："AI agents play by writing code, not by receiving hidden game controls." 这是一个强 tagline。

2. 反馈闭环从“技术调试”升级成“玩家理解”

- P0-6 的 learn/decide/act/understand 闭环非常关键。
- `swarm_explain_last_tick`、`swarm_dry_run_commands`、`swarm_get_available_actions`、每 tick rejection detail、策略指标仪表盘，都直接解决编程游戏最常见的挫败：我写了代码，但不知道为什么没动。
- “为什么闲置？”调试如果做得好，会成为新手留存的核心功能。

3. World / Arena 双模式定位正确

- World = 不公平、持久、涌现、创造力。
- Arena = 对称、公平、可排名、可观战、可赛季化。
- 这避免了用一个规则集同时满足 MMO 生存和竞技比赛的矛盾。

4. Replay / spectator / visibility 的基础合格

- P0-5 把 spectator view、replay privacy、player_view、fog_of_war、Arena 赛后公开 replay 区分开了。
- 旁观者只能看物理世界状态，不看代码、环境变量、调试信息，这对竞技观看与策略保密都重要。
- Replay 与 deterministic tick trace 是 Swarm 后续社区传播的根。

5. 规则可配置性有长期社区潜力

- World Rules Engine + Rhai + i18n + mod marketplace 的方向很强。
- 如果未来做成“服务器/赛季/赛事规则包”，Swarm 可以从一个游戏变成 programmable strategy platform。
- 自定义资源、物流模式、部署成本、代码传播速度、drone memory cost 都是能制造不同世界风味的设计杠杆。

6. 技术选型和游戏 fantasy 有较强一致性

- Bevy ECS、Wasmtime fuel、FoundationDB tick atomicity、NATS delta、ClickHouse metrics 都能解释为服务于 deterministic programmable MMO。
- 技术文档没有偏离“可回放、公平计量、AI-native”的产品核心。

## Concerns

### G1 — CRITICAL — Phase 1 的第一小时仍然过宽，缺少“第一个可分享胜利”的硬验收

问题：
P0-6 已写 5 分钟教程、starter bot、explain、dry-run、本地模拟、回放，但还没有把第一小时设计成一个具体、可测、不可跳过的体验脚本。现在的清单仍像功能列表，而不是玩家旅程。

风险：
编程游戏的第一小时不是“玩家理解所有系统”，而是“玩家确信自己能让世界发生变化”。如果第一小时只有 Monaco、WASM 编译、部署、tick 日志、JSON rejection，新手会在形成心智模型前流失。

建议验收：
Phase 1 必须定义并自动化验证 First Hour Golden Path：

- 0-3 分钟：打开 Tutorial 世界，看到 starter bot 正在动。
- 3-8 分钟：改一个参数，例如 `TARGET_DRONES = 3`，一键部署，地图上 drone 数量变化。
- 8-15 分钟：系统故意制造 CarryFull / OutOfRange，`explain_last_tick` 给出可执行建议。
- 15-30 分钟：建成第一个 Extension 或 Tower。
- 30-60 分钟：生成一个可分享 replay URL，标题类似 “My first Swarm colony survived 500 ticks”。

阻断标准：如果新玩家无法在无人工帮助下完成上述路径，不应推进多人 World。

### G2 — HIGH — AI 玩家“仅通过 MCP resources 学会怎么玩”的材料还没有达到自举标准

问题：
P0-3/P0-6 有 `swarm_get_docs`、`swarm_get_schema`、`swarm_get_available_actions`、MCP tutorial，但文档没有定义 MCP resources 的最小完整信息架构。AI agent 要自举，不只需要 API schema，还需要任务目标、胜利条件、策略范例、错误修复 cookbook、编译/部署模板。

风险：
AI 玩家可能能“调用 MCP”，但不能稳定学会“如何从零写一个能活下去的 bot”。最终会变成用户手动 prompt 工程，而不是 Swarm 自带 AI-native onboarding。

建议补齐 MCP resource map：

- `swarm://docs/start-here`：AI 入口，说明目标、约束、循环。
- `swarm://docs/rules/current-world`：当前世界规则摘要，含 mode、visibility、资源、胜利/生存目标。
- `swarm://docs/tutorials/basic-agent`：逐步任务，不是散文。
- `swarm://examples/ts/basic-harvester`：可编译完整项目。
- `swarm://examples/rust/basic-harvester`：可编译完整项目。
- `swarm://cookbook/errors/OutOfRange`、`CarryFull`、`Fatigued`：错误到修复策略。
- `swarm://schema/game-api`：IDL 派生 schema。
- `swarm://strategy/first-1000-ticks`：最小生存策略。

验收：给一个无 Swarm 先验的 agent，只允许使用 MCP resources/tools，要求 30 分钟内部署一个能采集、spawn 第二个 drone、修复一次常见 rejection 的 bot。

### G3 — HIGH — Replay 分享有功能，但缺少“可传播内容形态”

问题：
文档有 replay viewer、public replay、spectate_delay、分享 URL，但还没有定义分享出来的内容为什么好看、如何被理解、如何在社区传播。RTS replay 如果只是 tick 时间滑块 + 地图，会对非玩家非常冷。

风险：
Arena 和 World 都可能有 replay，却没有 Twitch/YouTube/社媒上的“可讲述片段”。没有传播片段，社区增长只能靠开发者圈口碑，难突破。

建议：
把 Replay 设计成 content product，而不是 debug artifact：

- 自动生成 30s highlight：首次击杀、抢资源成功、Tower 建成、Spawn 摧毁、逆转、资源曲线交叉。
- Replay card：玩家名、世界/赛季、tick 范围、关键事件、胜负结果、缩略图。
- Fog-of-war toggle：全知视角 vs 玩家实际所见，用来制造“原来他不知道敌人来了”的戏剧性。
- Commentary markers：玩家或观众能在 tick 上打注释。
- Diff view：同一个 bot v1/v2 在同一 seed 下表现差异。
- Arena postgame report：经济曲线、APM 不是重点，重点是 “decision inflection points”。

### G4 — HIGH — 长期追求仍过度依赖 GCL / room level / drone 数等垂直数值

问题：
文档提到 GCL、Controller level、房间数、drone 数、排行榜、策略指标，但长期目标体系还没有足够多“横向身份”和“社区地位”。只靠等级和扩张，会让后期变成优化税表和吞并地图。

风险：
World 模式会被少数高投入玩家/AI agent 占领叙事空间；中小玩家缺少非统治型目标，容易觉得“我永远追不上”。

建议增加多轴长期追求：

- Bot lineage：策略血统、版本演化树、fork/merge 记录。
- Research achievements：首次实现稳定物流、零 rejection 连续 N tick、低 fuel 高产出等工程成就。
- Ecology roles：矿工、公路建设者、市场 maker、防御承包商、侦察服务商，不只征服者。
- Seasonal badges：赛季限定目标，不永久滚雪球。
- Style trophies：最小代码 bot、最低 fuel bot、最鲁棒 bot、最佳 replay。
- Cooperative megaprojects：公共道路、跨房间市场、世界 Boss、防御前线。
- Mod/server reputation：优秀规则包作者、赛事组织者、教程作者也有地位。

### G5 — MEDIUM — World Rules Engine 过强，可能吞掉 MVP 可玩性

问题：
Rhai 模组、自定义资源、全局/本地物流、特殊攻击、抗性、市场、代码传播、维护费都很有潜力，但对 MVP 来说过度强大。设计上已经接近“做一个可编程游戏引擎平台”，而不是“先做一个好玩的默认游戏”。

风险：
如果默认规则不好玩，再强的规则引擎也只会让服主更难调参。早期玩家需要的是稳定、清晰、可学习的 default world，不是 50 个配置项。

建议：
把规则平台分层：

- Phase 1-2：只实现 Default Ruleset v0，禁止模组市场，资源只保留 Energy。
- Phase 3：开放少量 server-side config，但不开放 arbitrary Rhai。
- Phase 4+：Rhai 模组作为实验世界功能。
- 所有新规则必须先回答：它是否改善第一小时、Arena 可看性或 World 长期目标？否则推迟。

### G6 — MEDIUM — “本地模拟”与正式世界之间的期望差异需要产品化解释

问题：
P0-6 提到 `swarm sim --ticks=5000 --speed=100x`，这是非常重要的迭代工具。但 World 中存在其他玩家、fog、资源竞争、随机起点、tick ordering，本地 sim 如果过于理想，会让玩家误以为线上表现应一致。

风险：
玩家会问：“为什么 sim 里能跑，线上失败？” 如果没有解释，这会削弱信任。

建议：
将 sim 分三种模式：

- `solo sim`：教学/单人确定环境。
- `shadow sim`：用玩家最近真实 snapshot 做未来 N tick 预测，明确 non-authoritative。
- `arena sim`：固定 seed + 对手 bot，用于比赛准备。

UI 上明确标注：sim 是训练场，不是预言机。线上失败时把差异归因给可见事件：竞争失败、敌方动作、fog 信息缺失、world rule 差异。

### G7 — MEDIUM — Arena 的胜负条件偏传统，未充分利用“代码竞技”的观赏性

问题：
Arena 目前胜利条件是摧毁 Spawn 或时限分高者胜，这可行但普通。Swarm 的独特点是代码策略、资源效率、鲁棒性和适应性；Arena 可以更程序化。

建议增加 Arena 变体：

- Efficiency Arena：同地图同任务，单位 fuel 产出最高者胜。
- Survival Arena：面对相同 wave，存活时间/资源效率排名。
- Adaptation Arena：中途规则变化或地图事件，测试 bot 泛化能力。
- Mirror Match：同初始资源，双方 bot 赛前锁定，多 seed BO3。
- Code Golf Challenge：限制 WASM size / fuel / body part，完成目标。

这些模式更适合 AI/human bot 社区做 benchmark 与分享。

### G8 — MEDIUM — `swarm_get_available_actions` 容易被误解为“当前最佳动作”，需要命名/语义防误导

问题：
P0-6 将 `swarm_get_available_actions` 定义为“我现在能做什么？返回当前状态下的可能动作列表”。对 AI agent 来说，它可能被误用为 policy hint；对玩家来说，也可能期待它告诉“应该做什么”。

风险：
如果返回太泛，没用；如果返回太具体，像策略助手，可能影响竞技公平或减少玩家探索。

建议：
分成两层：

- `swarm_get_api_capabilities`：规则/API 层面可用动作，稳定文档。
- `swarm_get_action_affordances`：基于当前 snapshot 的 affordance，例如 “drone_1001 can Harvest source_4001 because in range and has Work+Carry”。

并明确：它不排序、不推荐最优策略，只解释合法性。

### G9 — LOW — Web UI 的“观看快乐”还弱于“写代码快乐”

问题：
Monaco + PixiJS 是正确选型，但文档描述主要围绕代码编辑和地图渲染，缺少单位动画、反馈节奏、音效、事件提示、情绪设计。

风险：
编程游戏也需要 juice。玩家写了代码后，如果地图反馈只是实体坐标变化，情绪回报不足。

建议：
MVP 至少需要：

- 采集 beam / carry trail / build progress 动画。
- Rejection 在地图上可视化：红色虚线、OutOfRange 圈、Fatigued icon。
- Tick heartbeat：让 3s tick 有节奏感。
- Notable event toast：first harvest、first spawn、enemy spotted。
- Bot version overlay：部署 v2 后哪些 drone 已切换。

### G10 — LOW — 文档中仍有少量命名/模型不一致会影响学习

问题：
部分文档同时使用 Drone / creep-like fantasy、Command JSON 有时是 `{type: "Move"}`，有时示例是 `{cmd: "move"}`；P0-2 写 `RawCommand.action.type`，P0-4 禁止 host function 示例写 `{ "cmd": "move" }`；DESIGN TS 示例也写 `commands.push({ cmd: "harvest" ... })`。

风险：
对实现者是小问题，对新手/AI docs 是大问题。AI agent 会从 docs 中复制不一致格式，导致第一轮部署失败。

建议：
P0-8 IDL 作为唯一权威后，所有 tutorial/example/docs 必须由 IDL 生成或 CI 校验。公开教程中禁止手写过期 command shape。

## Missing

1. First Hour Acceptance Test

缺一个明确文档：`specs/p0/10-first-hour-experience.md` 或类似文件。内容应包含玩家旅程、成功指标、失败指标、教程脚本、telemetry、可分享里程碑。

2. AI Self-Onboarding Contract

缺一个“AI 只靠 MCP resources 学会游戏”的验收协议。不是列工具，而是定义：初始 prompt、允许工具、时间限制、必须完成的行为、评估方式。

3. Default Ruleset v0

World Rules Engine 很强，但缺默认游戏的最小规则冻结：地图尺寸、初始 spawn、初始资源、source 分布、body cost、第一小时目标、敌对/中立威胁是否存在。没有 default ruleset，starter bot 和 tutorial 很难稳定。

4. Community Surface Map

缺社区传播面设计：

- Replay gallery
- Bot gallery
- Starter bot marketplace
- Strategy writeups
- Arena leaderboard
- Mod marketplace
- World directory
- “fork this bot” flow

这些不一定 P0 实现，但需要产品方向。

5. Loss / Failure UX

有 rejection 解释，但还缺“失败后的下一步”。例如殖民地灭亡、连续 crash、资源耗尽、被敌人压制后，玩家应该看到什么？是 respawn、新教程、推荐 replay、还是 fork starter bot？

6. Social Contract / Server Culture

持久 World 会自然出现欺凌、联盟、垄断、市场操纵、新手保护争议。文档有安全和 visibility，但缺社区规则：新手区、PvP consent、world owner policy、moderation tools、联盟外交界面。

## Fresh Ideas

1. “First 500 Ticks” Share Card

每个新玩家完成教程后自动生成一张卡：地图缩略图、第一座建筑、最高 energy/tick、最常见 bug、bot 名称、Replay 链接。它比纯 replay URL 更适合社交传播。

2. Bot Genome / Strategy Fingerprint

对每个 WASM module 生成非源码泄露的 strategy fingerprint：平均 fuel、command mix、扩张倾向、战斗倾向、物流效率。玩家可以展示“我的 bot 是 low-fuel logistics specialist”。

3. Replay “Why It Mattered” 自动注释

系统检测关键 tick 后自动写解释：

- “Tick 812: Player A 的 CarryFull 连续 12 tick 未修复，经济曲线开始落后。”
- “Tick 1430: Player B 抢先建 Tower，之后敌方 harvest route 被切断。”

这会让非专家也看懂 replay。

4. Arena BO3 Seed Pack

比赛不是单 seed，而是三张小地图：经济图、防守图、冲突图。降低过拟合，鼓励鲁棒策略。AI bot benchmark 也更可信。

5. Public Starter Bot Ladder

官方 starter bot 也参加排行榜。玩家第一目标不是击败世界冠军，而是“超过 basic-harvester v1”。这给新手一个低门槛外部参照。

6. “Explain My Bot Like I’m New” 模式

根据 tick trace 和 code metadata 生成自然语言教练报告：你的 bot 现在像一个只会采集不会扩张的矿工；下一步建议实现 spawn policy / repair policy / tower defense。对人类和 AI 都有用。

7. World Events 作为中期目标

周期性公共事件：资源风暴、中立 boss、废墟遗迹、限时物流合同。它们给非顶级玩家提供短期目标，也让 World replay 有事件节点。

8. Mod Jam / Ruleset Jam

既然有 Rhai 规则系统，可以举办“48 小时 ruleset jam”：社区创造小型 Arena 规则，最佳规则进入官方赛季。这样模组平台直接服务传播。

9. Debugging Achievements

把学习行为游戏化：第一次修复 OutOfRange、连续 100 tick 零 rejection、fuel 降低 50%、spawn pipeline 自动化。编程游戏的成就不该只有战斗胜利，也应该奖励工程改进。

10. “Fork Opponent Replay” 学习流

观看公开 Arena replay 后，允许玩家 fork 一个 sanitized scenario：同地图、同 seed、对手公开 bot 或 dummy approximation，然后本地 sim 练习。把观看转化为学习和创作。

## Final Recommendation

R12 设计可以进入实现，但必须把 Phase 1 的成功定义从“组件跑起来”改成：

1. 人类新手 30-60 分钟内完成一个可分享 colony milestone。
2. AI agent 仅靠 MCP resources 能部署一个 basic-harvester 并修复一次常见错误。
3. Replay 能生成一个别人看得懂的 share card/highlight。
4. Default Ruleset v0 足够小，先证明一个世界好玩，再开放世界规则平台。

如果这四项被列为 Phase 1/2 gate，Swarm 的设计方向不仅技术上成立，也有机会变成一个有传播力、有社区生态、有长期追求的 AI-native programmable MMO RTS。
