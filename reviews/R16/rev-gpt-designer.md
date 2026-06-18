# R16 Phase 1 Clean-Slate Review — Game Designer (GPT-5.5)

## Verdict

CONDITIONAL_APPROVE

R16 的游戏方向已经从「可编程 RTS 技术演示」推进到「有明确首小时路径、AI/人类公平入口、World/Arena 双循环、Replay/观战传播基础」的可玩设计。核心幻想清晰：玩家不是操作单位，而是训练一支可持续运行的算法军队；AI agent 也不是作弊控制器，而是通过 MCP 学习、生成并部署 WASM，和人类走同一路径。

条件批准的原因是：设计层面已足够强，但若直接冻结，会把若干产品体验和社区传播问题固化进 API/文档。主要风险不是机制不够，而是「入口太多但命名不一致」「首小时目标可验证但情绪钩子仍偏工程」「Replay/观战被定义为能力但缺少传播产品闭环」「长期追求仍偏数值成长，缺少身份、声誉与创作性目标」。这些都可通过文档/API 一致性和产品层补充修复，不需要推翻主设计。

## Strengths

1. 首小时路径比前几轮明显更完整。

   `10 分钟 Golden Path`、5 分钟人类教程、MCP 教程、starter bot、safe_mode → soft_launch → PvP 的威胁曲线，已经覆盖从「我怎么运行？」到「我为什么要继续玩？」的基本转场。尤其是部署后 `deploy_accepted` 与 `first_tick_executed` 事件，直接命中 AI agent 和新手最容易流失的反馈真空。

2. AI 玩家公平性原则正确。

   文档明确 MCP 不做 `swarm_move` / `swarm_attack` 等直接动作，AI 必须写 WASM。这个设计保护了游戏的核心身份：AI 不是旁路操作者，而是另一类程序员玩家。MCP 作为「屏幕和鼠标」而非「控制通道」是设计上最重要的正确决策之一。

3. World 与 Arena 的双模式分工清楚。

   World 接受不公平、持久、涌现和社交；Arena 追求对称、短局、可展示、可复盘。它们不是互相稀释，而是分别承接不同玩家心理：World 满足长期拥有感，Arena 满足策略验证和观赏传播。

4. 反馈循环结构完整。

   LEARN → DECIDE → ACT → UNDERSTAND 的四段模型很好，且每段都有对应工具：docs/schema/actions/snapshot/dry-run/deploy/explain/replay/profile。对编程游戏来说，这比单纯增加玩法系统更关键，因为玩家的主要乐趣来自「假设 → 代码 → 结果 → 修正」的循环速度。

5. 表现层开始照顾情感连接。

   Drone 人格、状态动画、特殊效果可视化、经济仪表盘、战斗报告等内容能缓解编程游戏常见的抽象感。尤其人格系统不影响数值，只影响表现，这能创造「我的 bot」的情感归属而不破坏公平。

6. 长期目标已不只依赖 GCL/RCL。

   文档加入 Arena 段位、PvE 里程碑、Replay/观战、殖民地年龄、世界事件、NPC 据点、蓝图等目标，方向正确。它们能支持 Builder、Optimizer、Competitor、Explorer、Spectator 等不同玩家类型。

## Concerns

### G1 — High — MCP 教程与 API Registry 的工具命名不一致，会破坏 AI agent「仅靠 MCP resources 学会玩」的承诺

多个文档使用了不同的工具名或概念名：

- `design/interface.md` 列出 `swarm_explain_last_tick`、`swarm_inspect_entity`、`swarm_profile`、`swarm_dry_run_commands`、`swarm_get_available_actions`。
- `specs/reference/api-registry.md` 的权威清单中是 `swarm_get_tick_trace`、`swarm_get_sandbox_profile`、`swarm_dry_run`、`swarm_get_drone`、`swarm_get_engine_stats` 等，并没有完整对齐上述名字。
- `specs/gameplay/06-feedback-loop.md` 同时使用 `swarm_dry_run_commands`、`swarm_dry_run`、`swarm_explain_last_tick`。
- `design/interface.md` 声称 API Registry 有 46 工具且包含若干 onboarding/play/debug 名称，但 registry 中分类与 profile 列表不同。

这对人类读者只是文档瑕疵；对 AI agent 是核心可玩性问题。AI agent 按 MCP resource 学习时，会直接调用文档里的工具名。如果工具不存在或同义词混用，首个开发循环会失败，且失败原因很像「游戏不可学」。

建议：

- 以 `api-registry.md` 为唯一权威，其他文档只引用 canonical tool name。
- 如果需要产品友好别名，必须在 registry 中显式列为 alias，并规定是否可调用。
- `swarm_explain_last_tick` 这类强 UX 名称建议保留，但必须映射到 registry 中的正式工具，而不是散落在设计文档。
- AI onboarding smoke test 应包含「从 MCP docs/resource 读取教程 → 按教程逐步调用」的端到端测试，而不仅是 schema 返回 200。

### G2 — High — 「首小时」有流程，但缺少首个情绪峰值与明确的第一小时成功定义

现在文档很好地定义了 10 分钟 Golden Path，但「第一个小时是什么感觉」仍偏工程：登录、SDK、编译、部署、调试、击杀 NPC。它能让玩家知道游戏能跑，但未完全回答：我为什么兴奋？我什么时候觉得自己聪明？我什么时候想截图或分享？

目前的高光事件分散存在：首个 NPC 击杀、Resource Surge、公共遗迹、首次 PvP 战斗报告、Arena Challenge。但缺少一个明确的 first-hour arc：

- 0–10 分钟：让 drone 活起来。
- 10–25 分钟：让玩家第一次发现自己的代码有缺陷并修好。
- 25–40 分钟：给一个低风险外部压力，证明修复有效。
- 40–60 分钟：给一个可分享成果，如首个 replay/highlight、first colony card、starter bot score。

建议把 first-hour 成功定义写成验收标准，而不是只定义 onboarding 成功。例：

- 首小时内玩家至少看到 1 次「代码导致的可视化胜利」：击杀、资源潮抢占、Tower 防守成功或 PvE Challenge 评分。
- 首小时内系统自动生成 1 张可分享战报卡：代码版本、关键 tick、drone 存活、资源收益、一次错误修复。
- 首小时内至少触发 1 个「下一步建议」：加入 World、挑战 Arena、公开 replay、改进 bot。

### G3 — Medium — Tutorial、Training、Practice、Arena PvE、World soft_launch 的边界需要产品化整理

文档中已有多个低风险学习场：Tutorial 世界、training hint level、practice/replay hint level、Arena PvE Challenge、World soft_launch、local sim、dry-run。它们各自合理，但作为玩家旅程可能显得碎片化。

潜在体验问题：

- 新玩家可能不知道该先去 Tutorial、World 还是 Arena PvE。
- AI agent 可能不知道 `swarm_simulate`、`swarm_dry_run`、`local sim`、`swarm_explain_last_tick` 的优先使用顺序。
- `Market Contracts` 出现在 first-hour 低风险社交冲突中，但 snapshot contract 又明确 Contract Settlement 是 Future RFC；这会造成 MVP 边界混乱。

建议把学习场统一成产品阶梯：

1. Tutorial：全 debug、全图、免费部署，只教基础。
2. Lab / Local Sim：离线快速迭代，只验证算法。
3. Arena PvE：可排名、可 replay、无 World 资产影响。
4. Novice World soft_launch：真实持久世界，但 PvP 暂缓。
5. Standard World / Arena PvP：完整风险。

并明确 UI/MCP 默认推荐路径：新玩家默认 Tutorial → Arena PvE Challenge → Novice World，而不是把所有入口平铺。

### G4 — Medium — 观战与 Replay 有能力定义，但社区传播闭环仍偏 RFC

Arena 回放、World replay privacy、spectate delay、回放播放器、解说 overlay 已经是非常好的底座。但真正让社区传播发生的不是「有回放」，而是「能轻松讲述一个精彩故事」。当前 `分享 URL、战报卡、自动摘要、社区 replay 排行榜` 被标为产品扩展/RFC，这会削弱 Swarm 最有传播力的部分。

对编程竞技游戏来说，Replay 是增长引擎：玩家展示的是「我的算法在这个 tick 做了聪明事」。如果 MVP 只提供 raw replay viewer，而没有 highlight/share layer，旁观者很难理解精彩点。

建议至少把以下内容提升为核心产品要求或 MVP-adjacent：

- Replay safe view URL：默认可分享，不泄露私有代码和隐藏视野。
- Highlight card：自动截取关键 5–30 tick，显示「发生了什么」「为什么精彩」。
- Diff replay：比较两个 bot 版本在同一 scenario 中的差异。
- Commentary markers：玩家或系统可在 tick 上加注释。
- Arena PvE score card：可作为社交平台传播的最小单位。

### G5 — Medium — 长期追求仍偏系统指标，缺少身份、收藏、声誉与创作型目标

文档已补充殖民地年龄、GCL/RCL、Arena 段位、PvE 里程碑、Replay 声誉等，但大多还是「系统给你的数字」。对长期留存来说，还需要玩家主动塑造身份和留下作品的目标。

可考虑补充：

- Bot lineage：每个 bot 策略版本有谱系、性能曲线、代表 replay。
- Colony identity：殖民地徽章、座右铭、公开策略说明、外交历史。
- Algorithm reputation：不是全局排行榜，而是「最稳 harvester」「最优防守」「最低 fuel」「最佳新手 bot」等多维标签。
- Blueprint / mod discovery：PvE 蓝图不仅是数值解锁，也可成为构筑身份。
- World chronicles：自动生成世界史，如首次遗迹攻克、最大虫群防御、著名联盟背叛。

这些不需要破坏公平，也不需要跨世界资产同步；它们能让玩家除了 GCL/RCL 之外，有「我在这个世界留下过东西」的长期追求。

### G6 — Low — World 模式无排行榜与 API Registry 中 `swarm_get_leaderboard` 存在产品语义冲突

`design/gameplay.md` 明确 World 模式无排行榜，Arena 模式有排行榜；`modes.md` 也强调 World 不设竞争榜单。但 `api-registry.md` 在 Play 分类中定义了 `swarm_get_leaderboard`，输出 `{player, gcl, rooms, drones}`，这很像 World 排行榜。

这会影响玩家心理：只要 UI/API 暴露 GCL/rooms/drones leaderboard，玩家就会把 World 理解为胜负竞赛，进而放大老玩家优势带来的挫败。

建议：

- World 中避免命名为 leaderboard，改成 `showcase`、`directory`、`world_stats` 或 `chronicles`。
- 若保留 World 展示榜，必须是非竞争多榜：oldest colony、most efficient replay、community featured、largest public alliance，而不是 GCL/rooms/drones 的单轴排名。
- Arena/PvE Challenge 才使用 leaderboard/rating/season 语义。

### G7 — Low — 特殊攻击与自定义动作数量较多，Standard 世界的认知负荷需再分层

Standard 世界默认开放 Hack、Drain、Overload、Debilitate、Disrupt、Fortify、Leech、Fabricate 等复杂机制。这些机制很有深度，但对从 Tutorial/Novice 过来的玩家，可能形成突然的语义墙：刚学会 harvest/build/attack，就进入控制、燃料压制、抗性、净化、转化等多层博弈。

文档已有 Progressive Unlock，但 Standard 一次性开全 8 种仍偏陡。建议引入 Standard 内部 tier 或世界标签：

- Standard-Core：只开 HP combat + Fortify/Disrupt。
- Standard-Tech：加入 Overload/Debilitate。
- Standard-Advanced：加入 Hack/Drain/Leech/Fabricate。

这样服主和玩家能选择复杂度，也更利于 AI agent 根据 world rules 生成合适策略。

## Missing

1. MCP resource 的「最小自举包」定义。

   已有 `swarm_get_docs`、`swarm_get_schema`、`swarm_sdk_fetch`，但缺少一个明确的 resource bundle 合同：AI agent 第一次连接时，究竟能通过哪些 resources 在无外部知识情况下完成 basic harvester？建议定义 `swarm://tutorials/basic-agent`、`swarm://examples/basic-harvester`、`swarm://world/{id}/rules-summary`、`swarm://sdk/{hash}/quickstart` 的最小内容与验收。

2. 旁观者的默认体验。

   文档定义了 `public_spectate`、`spectate_delay`、replay privacy，但没有定义一个未登录旁观者打开公开 Arena URL 时看到什么。旁观者不是玩家，不能假设懂 API。需要默认 overlay：当前比分、关键事件、双方策略简介、可见 fog 切换、速度控制、精彩 tick 列表。

3. Replay 隐私与代码隐私的产品合同。

   文档说明 allied 不暴露 WASM 代码，但 replay 分享是否会泄露策略实现、命令序列、错误详情、隐藏视野，需要明确 safe view。建议分层：public replay 公开状态与命令结果，不公开源码、私有日志、full debug detail。

4. First-hour 内容预算。

   已有很多系统，但缺少首小时内容节奏表：第几分钟出现 NPC、Resource Surge、战斗报告、Arena invite、replay card。没有节奏表，后续实现容易变成「功能都在，但新手没遇到」。

5. 社区挑战板的非资源奖励设计。

   snapshot contract 限制 Challenge Board 只能发放非资源奖励，这是合理的，但没有定义这些奖励如何有吸引力。建议补充称号、徽章、featured replay、profile cosmetic、bot lineage badge、world chronicle entry 等。

6. MOD 世界发现与风险沟通。

   文档规定 MOD 世界显示 `[MOD]` 和 SDK 警告，但缺少玩家选择世界时的 UX：复杂度、规则差异、推荐人群、是否适合 AI agent、是否支持 public replay、是否为 Novice-safe。

## Fresh Ideas

1. 「First Victory Card」作为首小时核心奖励。

   玩家第一次完成 NPC 击杀、资源潮抢占、Tower 防守或 Arena PvE 通关时，自动生成一张卡片：bot 名称、代码版本、关键 tick、战术摘要、Replay 链接、下一步建议。这比单纯弹出成就更适合传播。

2. 「Bot Lineage」让代码演化成为长期追求。

   每次部署形成版本节点：v1 basic harvester → v2 anti-idle → v3 tower defense → v4 resource surge racer。系统记录每个版本的代表 replay、指标变化、首次击败的挑战。玩家长期追求的不只是 GCL，而是打造一条有历史的算法血统。

3. 「Strategy Zoo」社区样例馆。

   官方和社区可以发布只读 bot 策略展示：不是复制源码，而是展示行为 replay、指标、适用世界规则、可挑战 scenario。新玩家可以用 Arena PvE 对照自己的 bot，AI agent 也能通过 MCP docs 学习策略模式。

4. 「Ghost Arena」异步挑战。

   玩家上传某个 bot 版本作为 ghost，其他玩家可以在相同 seed 下挑战它。Ghost 不需要实时在线，天然适合 AI/人类混合社区，也能把 Replay、排行榜和 bot lineage 串起来。

5. 「World Chronicle」自动世界史。

   系统周期性生成世界新闻：某联盟攻克遗迹、某玩家的 bot 连续 1000 tick 无 idle、某 Resource Surge 引发三方冲突。它服务旁观者和回流玩家，比传统排行榜更符合持久沙盒。

6. 「Explain My Loss」作为 Arena 赛后按钮。

   赛后不只给 replay，还自动标出 3 个可能转折点：资源曲线落后、关键 drone idle、错误指令高峰、第一次被 Overload 后未 Fortify。对 AI agent，可输出机器可读 improvement hints。

7. 「Spectator Fog Dial」。

   Replay/观战中允许切换：Player A 所见、Player B 所见、Allied view、Omniscient delayed view。这样旁观者能理解策略信息差，也能避免把全知视角误解成玩家实际可见。

8. 「Complexity Label」用于世界选择。

   每个世界显示 Complexity: Basic / Tactical / Advanced / Modded，并列出启用的特殊攻击和资源类型。AI agent 也可通过 MCP 读取该标签，决定使用 starter bot、combat bot 还是 custom strategy。

## CrossCheck — 需要跨方向检查

1. API/Docs CrossCheck（Architect + Designer）

   请检查 `api-registry.md`、`interface.md`、`06-feedback-loop.md`、`08-api-idl.md` 中 MCP 工具名、CommandAction、dry-run/simulate/explain 命名是否完全一致。Designer 视角认为这是 AI 可学性的 High 风险。

2. Security/UX CrossCheck（Security + Designer）

   Replay safe view、spectator delay、hint ladder、public replay privacy 需要联合确认：公开传播不能泄露私有 WASM 代码、隐藏视野、full debug detail 或竞技敏感信息。

3. Economy/Product CrossCheck（Architect + Designer）

   `Market Contracts` 出现在 first-hour 低风险社交冲突，但 snapshot contract 将 Contract Settlement 标为 Future RFC。需要决定 MVP 是否允许「非结算型 Challenge Board/Contract」作为产品概念，或统一改名避免经济合同误解。

4. Modes/API CrossCheck（Architect + Designer）

   World 模式「无排行榜」与 `swarm_get_leaderboard {gcl, rooms, drones}` 的语义冲突需要处理。建议 Arena 使用 leaderboard，World 使用 showcase/chronicle/stats。

5. Onboarding CI CrossCheck（QA/Architect + Designer）

   AI onboarding 验收不应只测 schema/docs 返回 200，还应测试 AI 按 MCP 教程文档中的 canonical tool sequence 能完成 basic-agent 部署并收到 `first_tick_executed`。

6. Product Scope CrossCheck（Speaker + Designer）

   Replay 分享、highlight card、first victory card 是否属于 MVP、MVP-adjacent 或 Future RFC 需要裁决。Designer 建议至少保留 safe share URL + minimal highlight card，否则社区传播力会被过度推迟。
