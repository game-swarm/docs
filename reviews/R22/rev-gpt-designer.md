# R22 游戏设计评审 — GPT-5.5

## Verdict

CONDITIONAL_APPROVE

设计方向是成立的：Swarm 有清晰的核心幻想（代码即军队）、较完整的 10 分钟 golden path、AI 与人类同路径的公平原则，以及 World/Arena 双核心模式。作为可编程 MMO RTS，它已经具备“好玩”的基本支架：看见代码改变世界、持续优化经济/物流、用 Arena 验证算法、用 Replay 传播策略。

但当前文档还不应直接冻结为最终设计。主要问题不是机制数量不足，而是玩家承诺过多且层级混乱：MVP、Future RFC、Vanilla、Tutorial、World、Arena、PvE、外交、消息、Merchant、Challenge Board 的边界在体验叙事上互相打架。若不先统一“玩家第一小时能真实体验什么、AI 仅靠 MCP resources 能学会什么、哪些社区传播能力是核心而非扩展”，实现后会出现预期落差。

## Strengths

- 核心幻想强：`你的代码就是你的军队` 足够一句话传播，且 AI/人类都写 WASM 的公平原则避免了“AI 作弊通道”的认知风险。
- 前 10 分钟路径具体：登录、SDK、编译、部署、观察、调试、首次 PvE 挑战被拆成可验收步骤，比多数可编程游戏设计更重视初次反馈。
- Feedback loop 完整：LEARN → DECIDE → ACT → UNDERSTAND 四步明确，`swarm_explain_last_tick`、`swarm_dry_run`、starter bot、经济仪表盘能显著降低“代码没动但不知道为什么”的挫败。
- World/Arena 双模式互补：World 提供长期沙盒与涌现政治，Arena 提供可复现、可分享、可比较的短局算法竞技，适合不同玩家心理。
- 观战与 Replay 已进入设计视野：Replay viewer、fog-of-war 切换、解说覆盖层、Arena 赛后公开回放，是社区传播的关键骨架。
- 长期追求不只 GCL/RCL：殖民地年龄、Arena 段位、PvE 里程碑、Replay 声誉、外交和视觉人格都能支撑非线性目标。

## Concerns

### G1 — High — 第一小时承诺过重，可能从“惊喜”变成“信息洪水”

文档同时在第一小时附近引入 SDK、WASM 编译、MCP/CLI/Web 三通道、starter bot、经济趋势、PvE、soft_launch、首次 PvP、Arena Challenge、Replay、策略指标。对程序员玩家来说，最强爽点应是“我改了一行代码，drone 真的变聪明了”；当前设计容易让玩家先学平台，再学游戏，再学经济，再学安全边界。

建议把第一小时收敛成三段体验承诺：

1. 0–10 分钟：只证明代码能控制世界。
2. 10–30 分钟：只证明优化有收益，例如采集效率从 40% 到 90%。
3. 30–60 分钟：只证明策略有对手，例如低风险 PvE 或 Arena ghost opponent。

首次 PvP、外交、市场式交换、复杂特殊攻击不应在第一小时承担教学责任。

### G2 — High — AI “仅通过 MCP resources 学会怎么玩”仍缺少一个机器可验证课程包

文档有 `swarm_get_docs`、`swarm_get_schema`、`swarm_sdk_fetch`、`swarm_get_available_actions`，原则正确。但从 AI 玩家视角，仅“有 docs 和 schema”不等于“能学会玩”。AI 需要一套可执行 curriculum：目标、当前状态、允许调用、预期产物、验收断言、下一步提示。

建议新增 MCP resource：`swarm://tutorials/basic-agent/curriculum`，包含 machine-readable steps，例如：

- step_id: spawn_first_drone
- observe: required snapshot fields
- code_goal: produce WASM that issues Spawn
- validate: expected `swarm_dry_run` assertions
- debug_if_failed: map RejectionReason → next hint

否则 AI agent 会在“读了完整 API 但不知道优先做什么”与“生成看似合理但世界不接受的代码”之间来回震荡。

### G3 — High — Replay/观战/社区传播被同时描述为核心和扩展，优先级不清

`modes.md` 将 Arena 赛后 Replay、公开回放作为比赛流程一环；`feedback-loop.md` 将回放查看器、公开回放、观战解说列入 MVP 功能清单；但 `modes.md` 又把分享 URL、战报卡、自动摘要、社区 replay 排行榜标为 RFC 产品扩展。

从游戏设计角度，Replay 分享不是锦上添花，而是可编程竞技的传播引擎。玩家很难通过截图传播“算法赢了”；必须通过 replay、tick 注释、关键决策摘要传播。

建议明确三层：

- Core：每场 Arena 必有 replay URL，支持公开/私有权限。
- Social MVP：一键分享 highlight tick range + 简短战报卡。
- Future：自动解说、排行榜精选、社区二创工具。

若没有 Social MVP，Arena 的社区增长会明显受限。

### G4 — Medium — Arena 定位存在“无排名房间制”与“段位/赛季/锦标赛”冲突

`modes.md` 说 Arena “无自动匹配、无天梯排名、无赛季”，但 `gameplay.md` 的长期目标写了 Arena 段位/赛季，`feedback-loop.md` 又列出排行榜、锦标赛、赛季。这会影响玩家预期：Arena 是私人实验室、公开比赛平台，还是正式竞技场？

建议拆成两个产品层：

- Arena Room：自测、邀请、无天梯。
- Arena Circuit：官方/社区赛事、排行榜、赛季、公开 replay。

这样能保留 MVP 的房间制简单性，同时不给长期竞技目标制造文档矛盾。

### G5 — Medium — PvE 内容与经济边界/Future RFC 有叙事冲突

World PvE 中 Merchant、蓝图、NPC 掉落、资源据点是很强的长期追求；但 Snapshot Contract 又把 Merchant NPC、Drone P2P Offer、Contract Settlement 等划为 Future RFC。`gameplay.md` 还写首个 PvE 挑战获得 PvE drop、Guardian 掉蓝图。

从玩家心理看，PvE 奖励如果在 tutorial/early game 被承诺，却在 MVP 边界中被推迟，会造成“打完了但奖励系统不完整”的落差。

建议把 PvE 奖励分层：

- MVP：只给非交易型成就、replay badge、scenario score。
- Vanilla World：Energy/Crystal 掉落通过 `PvEAward` ledger。
- Future：蓝图、Merchant、声望、Boss 多阶段。

同时在 golden path 中避免承诺“首次 PvE drop”，改为“首次 PvE 战斗报告 + 成就”。

### G6 — Medium — 特殊攻击体系创意足，但过早进入 Standard 会压垮可读性

Hack、Drain、Overload、Debilitate、Disrupt、Fortify、Leech、Fabricate 形成了很好的 counterplay 语言，但 Standard 世界一口气开放全部 8 种，会让新玩家刚理解 Move/Harvest/Build，就遇到“我的 fuel 被压制、drone 被 Hack、资源被 Drain”的多层失败原因。

建议设计“可读性解锁”而非只按世界层级启用：

- Novice：无特殊攻击。
- Standard early zone：只启用 Disrupt/Fortify 这类直观动作。
- Standard contested zone：启用 Hack/Drain/Overload。
- Advanced：全部开放 + custom actions。

这能让地图地理同时承担教学坡度。

### G7 — Low — Drone 人格很有味道，但需要避免“伪数值优势”误读

人格纯表现很适合增强情感连接，但文档写“高 efficiency drone 在交易中可能溢价”，容易让玩家误以为人格影响真实性能，或形成抽卡式价值判断。

建议将人格定位为 replay/观战/收藏表达，不进入经济价值描述。可以让玩家命名、涂装、徽章化 drone，但不要暗示人格会带来市场溢价。

### G8 — Low — World 无排行榜是合理的，但仍需要“可炫耀的非竞争展示面”

文档正确意识到持久世界天然不公平，不应做强排行榜。但完全无榜会削弱社区传播。建议提供非零和 showcase：最古老殖民地、最高效 harvest bot、最短 PvE 解法、最有趣 replay、最大公开地图艺术、最佳新手教程 bot 等。

这些不必影响资源，也不会制造老玩家碾压新玩家的公平焦虑。

## Missing

- 缺少明确的 First-Hour Experience Spec：玩家每 10 分钟应感受到什么情绪、看到什么反馈、完成什么可分享成果。
- 缺少 AI curriculum resource：目前 MCP 有工具和 docs，但没有机器可执行的学习路径与验收断言。
- 缺少 Replay 分享的最低产品定义：至少应定义 replay URL、权限、highlight range、战报卡字段。
- 缺少 Arena 产品分层：私人房间、自测 ghost、公开挑战、锦标赛/赛季应分层命名。
- 缺少社区动力学模型：联盟、外交、Replay、PvE、Arena 彼此如何产生论坛/Discord/视频传播尚未串起来。
- 缺少新玩家失败复盘：首次被打爆、首次部署失败、首次经济崩溃、首次 snapshot 截断时，玩家如何被挽回。
- 缺少长期非资产追求：称号、徽章、策略谱系、bot lineage、公开教程贡献、replay curator 声望等可补足 GCL/RCL 之外的动机。

## Fresh Ideas

- Ghost Arena：允许玩家把自己的旧 WASM、公开 replay 中的对手策略、官方 starter bot 作为 ghost opponent，低风险练习并生成对比报告。
- Strategy Lineage：每次部署形成 bot lineage graph，玩家可公开“这个版本从 v12 改进了 pathfinding，效率 +18%”，让代码演化本身可分享。
- Replay Highlight DSL：玩家或 AI 可给 tick range 加注释：`tick 420: bait`, `tick 510: supply cut`，生成可嵌入论坛的战报。
- Daily Puzzle：官方每天从真实 replay 中截取一个局面，让玩家提交 100 tick WASM 解法，排名按效率/损失/代码大小分榜。
- Mentor Bot：高阶玩家可发布只读教学 bot，附带 explanation trace，新人能 fork 并在 Tutorial world 中修改。
- Reputation Without Power：社区声望来自公开 replay、教程 bot、Arena puzzle、mod 文档贡献，不授予资源优势，避免 pay-to-win/old-player snowball。
- Spectator Delay Theater：Arena 观战默认延迟全图 + 双方实际视野切换，让观众理解“算法为什么不知道敌人在那”。
- First Failure Report：首次部署失败不是报错列表，而是“你的 bot 没动，因为没有 WORK part；点击生成最小修复 diff”。

## CrossCheck — 需要跨方向检查

- CX1: API Registry 的 MCP tool 数量在正文写“54 game + 11 auth”，变更记录写“56 active”，interface.md 写“56 game tools + 11 auth tools”，会影响 AI onboarding 文档可信度 → 建议 Architect 检查 IDL 生成源与 api-registry.md 计数一致性。
- CX2: `feedback-loop.md` 把公开回放、观战解说、锦标赛系统列为 MVP；`modes.md` 又将社区 replay 排行榜/战报卡标为 RFC，产品层级冲突 → 建议 Architect 检查 MVP/Future 边界并统一发布切片。
- CX3: World PvE 中 Merchant 与 Snapshot Contract 中 `RFC-MERCHANT` 冲突，Drone P2P 消息机制与 `RFC-P2P` 边界也可能冲突 → 建议 Architect 检查玩法承诺、经济 ledger 与 Future RFC 的边界。
- CX4: Arena 文档同时声明“无天梯排名、无赛季”和“Arena 段位/排行榜/锦标赛/赛季” → 建议 Architect 检查模式命名与数据模型是否拆分 Room vs Circuit。
- CX5: `public_spectate`、`replay_privacy`、Arena 公开 replay、World 私有视野之间涉及信息泄露与玩家隐私 → 建议 Security 检查 spectator delay、fog-of-war replay、权限过滤与 replay redaction。
- CX6: MCP AI 教程依赖 `swarm_get_docs`/`swarm_get_schema`/`swarm_sdk_fetch`，但是否足以让无先验 agent 编译并部署 WASM 取决于 SDK artifact 完整性 → 建议 Architect 检查 MCP resources 是否包含编译工具链、manifest hash、starter bot、错误修复路径。
