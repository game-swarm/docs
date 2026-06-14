# R10 Review — rev-gpt-designer

Reviewer: GPT-5.5 / Game Designer
Scope: `/data/swarm/docs/design/DESIGN.md`, `design/tech-choices.md`, `specs/p0/*`
Perspective: fun, first hour, AI learnability via MCP resources, spectator/replay/community loops, long-term progression beyond GCL/RCL.

## Verdict

APPROVE_WITH_RESERVATIONS

Swarm 的核心方向是强的：现代 Screeps + WASM + AI-first MCP + replay determinism，已经从“技术炫技”收敛成一个可学习、可调试、可公平竞争的 programmable MMO RTS。P0 文档解决了此前最大的风险：MCP 不再是 gameplay 控制通道，AI 与人类都必须写 WASM；反馈循环也明确覆盖 Learn → Decide → Act → Understand。

但从游戏设计角度，当前设计仍偏“引擎可行性”而非“第一个小时就好玩”。P0 足以冻结架构，但不应冻结体验。进入 Phase 1 前建议补一份 `First Hour / Core Loop Spec`，把新手第一局、Tutorial bot、可视反馈、目标序列、失败解释、奖励节奏和分享点具体化。否则工程实现很可能做出一个技术上正确、但新玩家看 20 分钟还不知道为什么要继续玩的系统。

## Strengths

1. AI/人类公平性设计清晰

MCP 定位为“屏幕和鼠标”，不是 `swarm_move`/`swarm_attack` 这种直接 gameplay API。唯一执行器是 WasmSandboxExecutor，AI 写 WASM，人与 AI 共享 fuel metering。这是产品差异点，也是社区传播点：AI bot 和人类 bot 是同一个赛场的同一类 artifact。

2. 反馈闭环被显式建模

P0-6 的 Learn → Decide → Act → Understand 是正确的游戏 UX 框架。`swarm_explain_last_tick`、`swarm_get_available_actions`、`swarm_dry_run_commands`、Starter Bot、本地 `swarm sim` 都在补“为什么我的代码没做事”的核心痛点。

3. Replay / spectator 已不是事后补丁

DESIGN 与 P0-5/P0-6 已经把 replay privacy、Arena public replay、spectate delay、safe view、fog-of-war toggle 等机制纳入设计。对于 programmable game，这是社区传播的生命线：玩家会分享“我的 bot 怎么赢的”，观众会看“AI 怎么犯蠢/翻盘”。

4. World vs Arena 分离正确

持久 World 不追求公平，Arena 追求公平，这个二分避免了 Screeps 类游戏常见的价值冲突：老玩家帝国碾压新玩家 vs 公平竞技。不同模式可以承载不同玩家心理：养成/创造/社交 与 排名/锦标赛/证明实力。

5. 可配置 World Rules Engine 具备社区生命力

Rhai 模组 + world.toml + 模组市场方向很好。它让 Swarm 不只是一个游戏，而是 programmable RTS server ecosystem。长期内容供给可以由服主、模组作者、赛事组织者共同承担。

6. 技术选择服务 replay/debug

Bevy `.chain()`、FoundationDB 原子 tick、Blake3 deterministic PRNG、IDL 单一真相、TickTrace 都直接服务“可解释、可回放、可验证”。对代码游戏来说，debuggability 就是核心玩法的一部分。

## Concerns

### G1 — Critical: First hour 目标序列仍不够具体

Severity: Critical

文档说有 5 分钟教程、Starter Bot、解释器，但还没有定义新玩家第一个小时的“目标节奏”：

- 第 1 分钟看到什么？
- 第 5 分钟完成什么？
- 第 15 分钟第一次失败来自哪里？
- 第 30 分钟为什么愿意重构 bot？
- 第 60 分钟的可炫耀成果是什么？

目前可推断的新手路径是：打开教程 → 改 starter bot → 看 drone 采集 → 部署 World/Arena。但这还不是完整的 retention loop。Programmable games 的早期危险是“我知道它很深，但我还没感到爽”。

建议新增 `specs/p0/10-first-hour-experience.md` 或 Phase 1 blocker，定义：

- Tutorial milestones: spawn first drone, first harvest, first transfer, first build, first defense, first replay share
- 每个 milestone 的视觉反馈、代码 diff、系统提示、失败解释
- 10 个新手常见失败与 explain 文案
- 第一个可分享 replay 的生成时机
- Tutorial 完成奖励：badge / template unlock / bot profile card

### G2 — High: 长期追求过度集中在 GCL/RCL/房间数，缺少“身份型”和“创作型”目标

Severity: High

当前长期追求主要是 GCL、Controller level、房间数、drone 数、Arena league。它们是必要的，但会导致优化型玩家有目标，创作型/社区型玩家动力不足。

Swarm 的独特玩家可能不只想“变强”，还想：

- 证明自己的 bot 很聪明
- 发布一个可 fork 的策略库
- 成为某类世界规则的专家
- 让 AI agent 学会自己的 bot 风格
- 做出被别人观战、解说、复盘的经典对局

建议新增长期追求层：

- Strategy Elo：按 bot/module hash 计分，而不是只按账号计分
- Bot Lineage：记录 fork/merge/版本谱系，形成“策略家族树”
- Achievement：First Autonomous Expansion、Zero-Rejection 100 ticks、Underdog Defense、Energy Efficiency Master
- Creator Reputation：starter bot、mod、replay annotation、tutorial contribution 的声望
- Research/Tech Tree：非数值碾压，而是解锁观测、模拟、分析工具或 cosmetic profile

### G3 — High: AI 仅靠 MCP resources 是否能学会玩，仍缺“任务化课程”和“机器可评估目标”

Severity: High

P0-3/P0-6 提供 `swarm_get_docs`、`swarm_get_schema`、`swarm_get_available_actions`、`swarm_explain_last_tick`，这对 AI 是必要的。但“能读 API”不等于“能学会玩”。AI agent 需要 structured curriculum：任务、验收、示例、反例、rubric。

建议 MCP docs 不只是 API reference，而是带任务资源：

- `swarm://tutorials/basic-agent/lesson-01-spawn`
- `swarm://tutorials/basic-agent/lesson-02-harvest-loop`
- `swarm://tutorials/basic-agent/lesson-03-debug-rejection`
- `swarm://tutorials/basic-agent/lesson-04-expand-room`

每课包含：

- Goal: “在 200 tick 内采集 1000 Energy”
- Starting snapshot
- Allowed APIs
- Reference solution pseudocode
- Common failure patterns
- Machine-graded success criteria
- Replay link / trace bundle

否则 AI 很可能读完 schema 后生成“能编译但策略很蠢”的代码，调试成本高，无法形成 AI-vs-AI 社区内容。

### G4 — Medium: Spectator / Replay 有机制，但缺“传播产品形态”

Severity: Medium

文档提到 replay viewer、safe view URL、观战解说、公开 replay。但还缺社区传播层的产品细节：分享出去的链接长什么样？观众第一眼看什么？能否生成短视频/GIF？能否 embed？能否看到关键转折点？

对于这类游戏，传播不是“可以看 replay”，而是“别人愿意点开”。建议补：

- Replay Card：玩家名、bot hash、世界/赛事、胜负、tick 长度、关键指标
- Highlight Auto-cut：检测 first kill、controller capture、spawn destroyed、resource swing、comeback
- Share modes：30s highlight GIF、full replay URL、annotated timeline、embeddable widget
- Fog toggle：omniscient / player A vision / player B vision / commentator overlay
- “Explain this moment”：对某 tick 生成自然语言战报

### G5 — Medium: 游戏 API 的动作语义偏 Screeps 基础集，缺早期“策略张力”钩子

Severity: Medium

Move/Harvest/Transfer/Build/Repair/Attack/Spawn 是够做 MVP 的，但第一小时的策略张力可能不足：玩家多数时间只是把资源从 Source 搬到 Spawn。文档后段有特殊攻击、全局存储、市场、模组等深层系统，但 Phase 1-2 的可玩核心可能偏平。

建议 MVP 就加入至少一个低复杂度但高表达力的决策钩子：

- Carry route choice: 近源低量 vs 远源高量
- Body composition tradeoff: MOVE/WORK/CARRY 的即时可见差异
- Risk/reward tile: 高产源在危险区或高 swamp 成本区
- Deploy cooldown/cost: 让“改代码”本身成为策略节奏
- Local simulation score: 鼓励玩家优化同一目标

不一定要复杂战斗，但要让玩家在 15 分钟内感到“我改了算法，所以结果明显变好了”。

### G6 — Medium: World Rules Engine 很强，但新手认知负荷可能爆炸

Severity: Medium

可配置资源、多伤害类型、特殊攻击、全局/本地存储、模组、物流模式、visibility 模式都很强，但如果早期 UI/MCP docs 把这些平铺给新玩家，会造成规则海啸。

建议按 experience tier 隐藏复杂度：

- Tutorial: 单资源、无 PvP、无全局存储税、固定地图
- Starter World: Energy only、轻物流、基础 body parts、少量建筑
- Standard World: 开启市场、fog、PvP、全局存储反制
- Expert/Modded World: 多资源、伤害类型、特殊攻击、Rhai 模组

MCP docs 也应按 world profile 返回“你现在需要知道的规则”，而不是 dump 全部规则。

### G7 — Medium: Arena 赛制方向正确，但胜利条件和观赏性指标还太粗

Severity: Medium

Arena 目前是摧毁 Spawn 或时限分高者胜。需要更明确的 scoring，避免 turtle、draw、无聊最优策略。

建议定义 Arena score：

- Primary: enemy spawn destroyed
- Secondary: controller progress / territory / resource income / combat value
- Tiebreaker: energy efficiency、command success rate、damage dealt、surviving drone value
- Anti-stall: 低交互惩罚或地图资源逐步枯竭
- Match phases: opening / expansion / conflict / endgame，便于解说和观战

### G8 — Low: 文档中部分 UX 命名仍偏技术，不够玩家语言

Severity: Low

例如 `swarm_dry_run_commands` 对 AI/开发者可以，但 Web UI 面向玩家应表达为“试运行本 tick / 预测是否成功”；`fuel refund`、`SourceEmpty`、`TickValidationFailed` 也需要玩家语言映射。

建议维护一层 UX copy dictionary：

- `OutOfRange` → “太远了：移动到 1 格内，或改用远程动作”
- `Fatigued` → “这个 drone 还在恢复移动疲劳”
- `MissingBodyPart(Work)` → “这个 drone 没有 WORK 部件，不能采集/建造”
- `TickValidationFailed` → “你的 bot 输出格式不对，本 tick 未执行”

机器码保留，玩家解释必须友好。

### G9 — Low: Mod 市场和规则透明度很好，但缺“安全信任 UX”

Severity: Low

Rhai 模组由服主安装，可信边界清楚。但玩家加入 modded world 前需要知道“这个世界有多魔改、是否公平、是否适合我”。

建议每个 world 有 Rule Badge：

- Vanilla / Lightly Modded / Heavily Modded
- PvP On/Off
- AI-friendly / Human-friendly
- Replay public/private
- Economy complexity: Basic / Advanced / Hardcore
- Estimated skill level

这会显著改善 server discovery。

## Missing

1. First Hour Experience Spec

必须补。当前 P0 更像架构冻结，不像体验冻结。建议定义逐分钟体验、任务、反馈、失败解释、奖励、分享点。

2. Onboarding content contract

Starter Bot 不应只是代码样例，还应有：

- annotated code
- expected replay
- expected metrics
- common modifications
- “try changing this line” prompts
- AI-readable lesson rubric

3. Bot identity / sharing model

需要把“bot”作为一等公民：名字、头像/徽章、版本、hash、lineage、战绩、replay、作者、fork 来源。否则社区传播只会围绕玩家账号，无法形成策略生态。

4. Community surfaces

缺少：public bot gallery、strategy leaderboard、mod marketplace UX、replay gallery、tournament page、world browser。

5. Anti-smurf / AI league taxonomy

P0-6 提到 Human/WASM、AI-assisted、AI tournament，但还没定义判定边界。长期需要处理：人类写 bot、AI 写 bot、人类+AI 共同迭代、完全 autonomous agent。建议不急着强执法，但需要产品标签。

6. “Fun metrics” telemetry

文档有 tick health、refund abuse、command rejection 等系统指标，但缺体验指标：

- time_to_first_drone
- time_to_first_successful_harvest
- time_to_first_deploy
- tutorial_completion_rate
- first_hour_redeployment_count
- explain_last_tick_open_rate
- replay_share_rate
- starter_bot_modification_rate

这些比系统 p99 更能告诉你游戏是否好玩。

## Fresh Ideas

1. Bot Trading Card

每次部署生成 bot card：名称、版本、语言、策略标签、效率图、最近战绩、signature replay。玩家可以分享“这是我的 v17 harvester”。AI agent 也可以把 card 作为 self-description。

2. Strategy Lineage Graph

记录 bot fork / copy / rewrite 的 lineage。社区会自然形成“某某开局流派”“蜂群防御流”“远矿 rush 流”。这比单纯排行榜更有生命力。

3. Replay-to-Code Debug Loop

在 replay 某 tick 点选一个失败动作，UI 直接跳到相关代码位置或生成 MCP prompt：

“在 tick 4521，drone_1003 因 Fatigued 未移动。请分析 bot v12 的 movement planner 并建议修改。”

4. Daily Challenge / Puzzle Room

每天一个固定 seed 小地图：在 300 tick 内最大化 energy / 最快建 tower / 最少 fuel 完成采集。排行榜按 bot hash。对新手、AI agent、社区传播都很友好。

5. Ghost Bots

玩家可以在本地/教程中对战公开 bot 的“ghost replay”或固定版本 WASM。这样即使服务器没真人，也有学习对手。

6. Explainable Tournament Broadcast

Arena replay 自动生成解说层：开局 build order、资源曲线、关键错误、胜率转折点。观众不懂代码也能看懂比赛。

7. World Browser with Rule Badges

加入世界前展示：Vanilla/Modded、PvP、Replay policy、AI density、平均 tick age、新手友好度、主要资源类型。减少玩家误入硬核世界后流失。

8. “No Code Yet” Planning Mode

人类新手在写代码前，可以用可视化 block/intent 规划：Harvest loop、Spawn loop、Upgrade controller。系统生成 TS starter code。它不是正式 gameplay 控制，只是代码生成辅助，不破坏“代码就是军队”。

9. AI Agent Certification Suite

提供 MCP 资源 `swarm://benchmarks/basic-competency`：AI agent 需要通过 spawn/harvest/build/debug 四个关卡，拿到 “Swarm-capable agent” badge。对外传播很强，也能测试 MCP docs 是否足够。

10. Failure Museum

公开收集有趣失败 replay：“100 个 drone 卡在门口”“AI 把所有资源转全局导致前线断粮”“tower 建在墙里”。Programmable games 的失败本身就是内容。

## Recommendation

Phase 0 架构可以冻结；Phase 1 前不要直接进入全栈实现。建议先补三份体验文档：

1. `specs/p0/10-first-hour-experience.md`
2. `specs/p0/11-bot-identity-and-sharing.md`
3. `specs/p0/12-community-replay-and-arena.md`

其中第 1 份应作为 Phase 1 blocker；第 2/3 可作为 Phase 2-4 的产品约束。当前技术架构足够支撑一个好玩的游戏，但还需要把“玩家为什么继续玩、为什么分享、为什么回来”写成与 Determinism Contract 同等级的设计合同。
