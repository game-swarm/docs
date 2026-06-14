# R11 Review — rev-gpt-designer

Reviewer: rev-gpt-designer / GPT-5.5
Role: Game Designer Reviewer
Scope: `/data/swarm/docs/design/DESIGN.md`, `/data/swarm/docs/design/tech-choices.md`, `/data/swarm/docs/specs/p0/*.md`
Perspective: fun, first hour, AI learnability via MCP resources, spectator/replay/community loops, long-term goals beyond GCL/RCL.

## Verdict

APPROVE_WITH_RESERVATIONS.

R11 的设计已经比 R10 更像“可玩的产品”而不只是“可实现的引擎”。核心路线正确：世界只认 WASM，MCP 是 AI 的屏幕/鼠标而不是作弊输入通道；P0-6 明确写出 Learn → Decide → Act → Understand 的反馈闭环；P0-5 把 spectator/replay/privacy 分层；DESIGN 也补上 World/Arena 双模式、公开回放、旁观延迟、规则可见性和 Starter Bot。

从游戏设计角度，我认为可以进入 Phase 1/2 的工程验证，但不能把体验层也视为“冻结完成”。现在最大的风险不再是“AI 和人类是否公平”，而是：玩家第一个小时是否真的能从 starter bot 过渡到自己的策略；AI agent 是否只靠 MCP resources 就能形成可运行的 bot；社区是否有足够短、足够可传播的高光切片；长期追求是否避免变成单一 GCL/RCL grind。

建议：Phase 1 允许开工，但必须新增并冻结一份 `First Hour / Strategy Onboarding Spec`；Phase 2 前必须用真实 AI agent 做“blind MCP onboarding test”；Phase 4 前必须把 replay/share 的 MVP 格式定死。

## Strengths

1. 核心幻想清晰且差异化

“你的代码就是你的军队 / Write once, fight forever”非常强。Swarm 不是普通 RTS，也不是纯编程题，而是长期运行的自动化战争。WASM 多语言、fuel metering、deterministic replay、MCP AI-first 组合出了 Screeps 没有的现代感。

2. AI 玩家公平性已经收敛

DESIGN §1/§4、P0-1、P0-3、P0-9 都反复强调：AI agent 通过 MCP 看世界、生成代码、部署 WASM；游戏动作只能来自 WASM tick 输出。这个设计既保护公平性，也让 AI 玩家和人类玩家共享同一套 debug/replay 体验。

3. P0-6 把“可玩性闭环”写进规范

Learn / Decide / Act / Understand 是正确的最低可玩性框架。尤其是：
- 5 分钟人类教程
- MCP 教程资源
- starter bot
- `swarm_get_available_actions`
- `swarm_dry_run_commands`
- `swarm_explain_last_tick`
- 每 tick explanation
这些都是编程游戏避免“黑盒挫败”的关键。

4. Replay / spectator / privacy 的设计方向健康

P0-5 区分 drone snapshot、玩家屏幕、MCP 查询、spectator WebSocket、private replay、Arena public replay。World 默认隐私，Arena 赛后公开，这符合两种模式的心理预期：World 是持久资产，Arena 是竞技表演。

5. World Rules Engine 给社区留了生命力

Rhai mod、world.toml、资源类型、伤害类型、可见性、经济规则、i18n 描述都让 Swarm 有成为“服务器生态 / mod 生态”的潜力，而不只是一个固定规则的 Screeps clone。

6. 技术选型服务设计目标

Rust+Bevy、Wasmtime、FDB、NATS、ClickHouse、Monaco+PixiJS 都不是炫技堆栈，而是分别支撑 deterministic tick、sandbox fairness、replay/audit、实时观看、策略指标和代码编辑体验。

## Concerns

### G1 — High: First hour 仍缺少“从好奇到上瘾”的逐分钟节奏

文档现在有 5 分钟教程和 Starter Bot，但还没有第一小时体验脚本：玩家什么时候第一次成功 spawn？什么时候第一次看到资源增长？什么时候第一次失败？什么时候第一次优化并获得明显收益？什么时候第一次分享？什么时候第一次进入 Arena 或 World？

如果只实现 P0-6 的功能清单，玩家可能会完成教程，但不知道下一步为什么要继续。编程游戏的第一个小时不能只教 API；必须制造“我刚刚让一个小系统活起来了”的连续反馈。

建议新增 `First Hour / Core Loop Spec`，至少定义：
- 0-5 min: 运行 starter bot，看到 drone 活动
- 5-15 min: 修改一个参数，立即看到产能变化
- 15-30 min: 遇到第一个 failure，explanation 指出原因，玩家修复
- 30-45 min: 完成第一个自选目标，例如第二个 harvester / tower / controller upgrade
- 45-60 min: 生成 replay share 或进入 sandbox Arena against bot
- 每段的 UI prompt、成功条件、失败恢复、奖励反馈

### G2 — High: “AI 仅靠 MCP resources 学会玩”尚未被验收定义覆盖

P0-6 写了 AI 教程流程和 MCP docs resources，但缺少可测试的 AI learnability contract。对 Swarm 来说这不是 nice-to-have，而是核心卖点：AI agent 应该能在不知道代码库内部的情况下，通过 MCP resources 编译、部署、观察、修复一个基础 bot。

目前风险点：
- `swarm_get_docs` 的内容粒度未定义：是 API reference，还是包含策略教程、示例代码、常见错误？
- `swarm_get_available_actions` 的语义可能误导 AI：它返回“当前可用 API 函数”还是“当前状态下建议动作”？前者安全，后者可能变成策略 oracle。
- `swarm_dry_run_commands` 与“所有动作必须通过 WASM”存在认知张力：AI 可能学会 dry-run commands，却不知道如何把它写回 WASM tick。
- MCP tutorial 没有明确要求返回可复制的 minimal project structure、build command、deploy command、expected first tick output。

建议 Phase 2 blocker：做一次 blind test，让一个未看源码的 AI agent 只用 MCP resources 完成：
1. 获取规则与 API
2. 生成 TS starter bot
3. 编译 WASM
4. `swarm_validate_module`
5. `swarm_deploy`
6. 观察 20 tick
7. 根据 `swarm_explain_last_tick` 修复至少一个错误
8. 达成 harvest + transfer loop

通过标准不应是“能聊天解释”，而是“产出可部署 WASM 并在世界里产生资源净增长”。

### G3 — Medium: First fun 过度依赖“harvest loop”，缺少早期战术选择

当前 starter bot 和第一小时大概率围绕 spawn / harvest / transfer / build tower。这是必要但不够兴奋。Screeps 的问题之一就是早期像物流作业；Swarm 若要更适合传播，需要让玩家在 30 分钟内看到至少一个“策略选择导致不同结果”的瞬间。

可以考虑在教程或第一张 Arena bot map 中放入低风险分叉：
- 近源低量 vs 远源高量
- 多小 drone vs 少大 drone
- 先 tower 防守 vs 先 extension 扩产
- MOVE/WORK/CARRY body composition 的即时差异
- 通过 `swarm sim` 比较两个策略的能量曲线

这会让新玩家理解：这不是写脚本搬砖，而是在设计自主系统。

### G4 — Medium: Spectator / replay 可看，但“可传播格式”还未产品化

P0-5/P0-6 已有 replay viewer、share safe view URL、观战解说、Arena 赛后公开回放。但社区传播需要更具体的 artifact：别人点开后 15 秒内看到什么？分享卡片长什么样？是否有自动生成的高光片段？是否能嵌入论坛/README？

仅有完整 replay URL 往往传播弱，因为外人不会花 4 小时看 5000 tick。Swarm 需要“短 replay clip / strategy card / battle report”。

建议定义 Replay Share MVP：
- 15s/30s clip，tick range + camera path + overlays
- 自动摘要：winner, turning point, top 3 events, energy graph
- fog-of-war toggle，但默认使用 spectator-safe view
- social preview card：地图缩略图 + 双方 bot 名 + 关键指标
- permalink 可嵌入 GitHub README / Discord / Telegram

### G5 — Medium: 长期追求仍偏 GCL/RCL/房间数，缺少身份型与创作型目标

文档已经列出 GCL、room level、房间数、drone 数、Arena league、tournament、mod market。这是好的骨架，但长期留存不能只靠扩张与排行榜。编程游戏的强动机还包括“我写出了漂亮系统”“我的 bot 被别人 fork”“我的世界规则被社区采用”“我的 replay 成为教学案例”。

建议补充长期 meta goals：
- Bot lineage：bot 版本树、策略 changelog、可公开 fork
- Achievement 不只按规模，也按风格：最省 fuel、最低 body cost、无攻击胜利、单房间极限产能
- Mod author progression：安装量、评分、兼容世界数
- Coach/teacher role：玩家可发布 annotated replay / tutorial bot
- Seasonal constraints：每季限制不同资源/视野/身体部件，避免 dominant strategy 固化

### G6 — Medium: World Rules Engine 很强，但新手认知负担可能爆炸

DESIGN §8 和 P0-7 给了资源、物流、伤害、特殊攻击、mod、i18n、可见性、市场、全局/本地存储等大量可配置项。作为平台很强；作为首个 World 的玩家体验可能过载。

需要明确：默认 World 的规则应非常少，复杂性逐步开放。否则新玩家在第一小时面对的不只是 API，还有 world.toml 的规则海洋。

建议：
- 定义 `Default World Rules — Beginner Edition`
- 第一世界只开放 Energy、MOVE/WORK/CARRY、Spawn/Extension/Tower、无复杂伤害类型、轻物流或无物流
- 高级资源、特殊攻击、Rhai mods、market logistics 放到后续世界或赛季
- MCP `swarm_get_world_rules` 应支持 `summary`, `full`, `diff_from_default` 三种模式

### G7 — Medium: Arena 胜利条件太单一，可能压缩策略多样性

P0-6 Arena 目前写“摧毁敌方 Spawn，或时限结束时分高者胜”。这是清晰的，但如果 score 未详细定义，玩家会迅速围绕一个 dominant build order 优化。Arena 是最适合传播和比赛的模式，胜利条件需要既清晰又鼓励多策略。

建议 score 由多个公开权重组成并可赛季化：
- enemy spawn damage / destruction
- controller progress
- resource net worth
- map control
- surviving drone value
- fuel efficiency bonus（小权重，避免纯龟缩）

同时支持特殊 Arena templates：rush map、economy map、fog map、limited body map、asymmetric objective map。

### G8 — Low: UI/UX 命名仍偏工程语汇，需要玩家语言层

`RawCommand`, `Source Gate`, `auth_context`, `fuel refund`, `global_storage`, `TransferToGlobal`, `RuleMod` 是实现术语。玩家界面与教程应有更自然的语言：
- “为什么没动？”而不是 rejection detail
- “你的代码本 tick 做了 5 件事，4 件成功”
- “能量被卡在本地仓库，需要转运”
- “这段代码太贵，超过本 tick CPU 配额”

文档可继续保留工程术语，但 P0-6 的 UI examples 应固化玩家语言，避免工程实现直接泄露到产品体验。

### G9 — Low: Community safety / etiquette 未进入设计视野

World 模式是 7×24 PvP + AI agents + public profiles + replay sharing。社区动力学会出现：新手被老玩家 farm、AI bot spam、公开 replay 羞辱、mod 诱导安装、联盟霸凌。安全评审会看技术安全，但 game design 需要 social safety。

建议至少定义：
- Beginner protected worlds / noob shard
- Arena league matchmaking / bot rating
- World griefing policy: spawn camping, resource starvation, alliance dogpiling
- Replay report / takedown for harassment metadata（不改链上事实，但可隐藏社交展示）
- Mod market moderation and compatibility badges

## Missing

1. `First Hour / Core Loop Spec`

这是当前最重要缺口。P0-6 有功能清单，但没有逐分钟体验、目标序列、失败恢复、奖励节奏和分享点。

2. `AI MCP Onboarding Acceptance Test`

应作为 Phase 2 blocker。用真实 AI agent 只靠 MCP resources 产出可部署 bot，并以资源净增长作为通过标准。

3. `Replay Share MVP Spec`

需要定义短 clip、battle report、social card、safe-view permissions、embed format。否则 replay 很可能成为“有功能但没人分享”。

4. `Default Beginner World Rules`

平台规则太强，默认世界必须克制。需要明确第一世界禁用或隐藏哪些复杂系统。

5. `Long-Term Progression Matrix`

除了 GCL/RCL/room/league，需要 bot lineage、achievements、mod author、coach/replay author、seasonal constraints 等非规模目标。

6. `Community Dynamics / Anti-Griefing Spec`

尤其是 World 模式的新手保护、AI spam、联盟压制、mod marketplace moderation。

## Fresh Ideas

1. Strategy Lab

一个独立 UI：玩家选择两个 bot 版本，在相同 seed 上跑 1000 tick，输出 energy curve、fuel usage、command rejection heatmap、turning point。它比普通 replay 更能帮助学习，也很适合 AI agent 自动迭代。

2. Bot Genome / Lineage

每次部署形成版本节点：父版本、变更摘要、指标变化、replay 样本。公开 bot 可以被 fork，形成“策略谱系”。社区传播不只是分享结果，而是分享演化过程。

3. “Explain Like I’m a Drone” Debug Mode

选中一个 idle drone，系统用玩家语言说：
“我想采集，但我没有 WORK；我能移动，但目标太远；建议 spawn body=[MOVE,WORK,CARRY] 或把我派到 source_4001。”
这对人类和 AI 都有价值，可作为 MCP explanation 的同源文案。

4. Arena Puzzle of the Day

每日固定 seed 小谜题：100 tick 内最大化能量、最少 fuel 建塔、用 3 个 drone 防住一波进攻。低门槛、高传播、适合排行榜，也能训练 AI agents。

5. Spectator Commentary DSL

允许玩家给 replay 添加 annotation：tick range、camera target、caption、highlight arrows。优秀 replay 可以变成教程内容，促进社区知识沉淀。

6. World Rule Diff Cards

进入一个 modded world 前，UI/MCP 返回“与默认世界不同的 5 条规则”：
- Energy 产量 -30%
- MOVE 成本 +20%
- public_spectate 开启，延迟 100 tick
- empire-upkeep enabled
这能显著降低规则认知负担。

7. Seasonal Constraint League

每季 Arena 给一个限制：无 Tower、只有 20 body parts、fog enabled、Energy 稀缺、代码部署锁定更早。这样长期 meta 不会只剩一个最优 bot。

8. “First Share” Moment

教程结束自动生成一张卡片：“My first Swarm colony survived 500 ticks — 3 drones, 1 tower, 92% command success”。让新玩家即使还没赢，也有可展示的成就。

## Recommended Phase Gates

Phase 1 before completion:
- Freeze `First Hour / Core Loop Spec`.
- Starter bot must produce visible progress within 60 seconds of tutorial start.
- Every common beginner failure must map to a human-readable suggestion.

Phase 2 before completion:
- Pass blind AI MCP onboarding test.
- MCP docs must include minimal project scaffold + build/deploy commands + expected outputs.
- `swarm_get_available_actions` must be clarified as discovery/help, not strategy oracle.

Phase 4 before completion:
- Replay share MVP implemented as short safe-view clip or battle report, not only full replay viewer.
- Strategy metrics dashboard supports comparing two deployments.

Phase 6 before public Arena:
- Score formula and Arena templates frozen.
- Spectator default view and delay policy verified against information leakage and watchability.

Final note: R11 is directionally strong. The architecture now protects fairness and learnability well enough to start building. The remaining work is product design discipline: make the first hour delightful, make AI onboarding empirically pass, and make replay/community artifacts short enough to spread.
