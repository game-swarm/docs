# R13 Review — rev-gpt-designer

评审角色：Game Designer / UX / 社区传播 / 玩家心理
评审范围：`/data/swarm/docs/design/DESIGN.md`、`/data/swarm/docs/design/tech-choices.md`、`/data/swarm/docs/specs/p0/`

## Verdict

APPROVE_WITH_RESERVATIONS

R13 已经比前几轮更像“可玩的产品设计”，不再只是技术架构。核心风险从“AI/人类是否公平、MCP 是否越权”转移到了“第一个小时能否让玩家快速获得成就感”和“长期生态是否会被规则复杂度压垮”。

我支持 Phase 0 冻结进入实现，但建议把以下事项作为 Phase 1/2 的产品验收门槛，而不是推迟到后期：

- 新手 5 分钟教程必须真的能让玩家完成“改代码 → 看到 drone 行动 → 理解为什么失败/成功”的闭环。
- MCP resources 必须足够自描述，让 AI 只靠 resources + tools 就能学会写第一个可运行 bot。
- Replay/观战/分享不应只是 Phase 4 之后的附属功能，而应从 TickTrace schema 开始预留“可解释、可分享、可传播”的产品字段。
- World Rules Engine 很强，但需要默认规则包、难度标签、规则摘要与推荐组合，否则会变成服主可配置、玩家不可理解。

当前设计的“游戏性承诺”成立：代码就是军队、持久世界 + Arena 双模式、WASM 公平沙箱、规则模组化、回放可验证。这些都足以支撑一个有辨识度的 programmable MMO RTS。

## Strengths

1. “世界只认 WASM”的公平性表达很清晰

AI agent 和人类玩家走同一条路径：写代码、编译 WASM、部署、由 WasmSandboxExecutor 执行。MCP 被明确限定为查看、部署、调试、学习，而不是 gameplay 输入通道。这解决了 programmable game 最容易崩的公平性问题：AI 不是有特权的外挂客户端。

2. MVP 反馈循环抓住了可玩性的关键

P0-6 用 LEARN → DECIDE → ACT → UNDERSTAND 描述体验闭环，这是正确的产品视角。尤其是：

- `swarm_get_available_actions`
- `swarm_dry_run_commands`
- `swarm_explain_last_tick`
- starter bot
- 每 tick 解释
- 本地模拟

这些不是“锦上添花”，而是 programmable game 的核心 UX。玩家失败时不知道为什么，游戏就会立刻变成调试地狱。

3. World / Arena 双模式解决了公平性与持久性的冲突

World 模式承认“不追求公平”，强调持久性、涌现、创造；Arena 模式强调对称、公平、赛季、公开回放。这是健康的分层。否则单一持久世界很容易同时背负“新玩家被老玩家碾压”和“竞技排行榜不可信”两个问题。

4. 观战与 replay 已经进入正式设计，而不是事后补丁

P0-5 对 spectator view、replay privacy、spectate delay、公开 Arena 回放做了细分。对社区传播来说，这是非常重要的基础。编程游戏的传播点往往不是“我玩了什么”，而是“我的 bot 在第 4300 tick 做了一个很聪明/很蠢的事”。Replay 是内容生产工具。

5. World Rules Engine 有成为社区生态核心的潜力

Rhai 模组 + world.toml + i18n + 可见规则说明，是 Swarm 区别于 Screeps 的一个强卖点。它允许社区从“写 bot”扩展到“设计世界规则”。这能产生多种服务器文化：硬核物流服、快节奏 Arena、教学世界、PvE 生存服、经济模拟服。

6. 技术选型与游戏需求大体匹配

Bevy ECS、Wasmtime fuel、FoundationDB 原子 tick、NATS delta、ClickHouse 分析、IDL 单一真相，这些选择都服务于确定性、可回放、公平计量与调试解释。技术没有明显偏离产品目标。

## Concerns

### G1 — Critical — 第一个小时仍然缺少“具体可玩脚本”验收

设计已经写了 5 分钟教程、starter bot、解释工具，但还没有定义第一个小时的可验证体验路径。

我建议把首小时拆成硬验收：

- 0–5 分钟：玩家打开教程，看到一个预运行 bot，能修改一个数字并看到 drone 数量变化。
- 5–15 分钟：玩家部署 basic-harvester 到隔离世界，看到能量增长曲线。
- 15–30 分钟：玩家遇到至少一个失败指令，并通过 explanation 修复它。
- 30–45 分钟：玩家添加第二种角色或建筑行为，例如 Tower/Extension。
- 45–60 分钟：玩家导出/分享一次 replay 或 sim 结果。

没有这条路径，Phase 1 可能实现了引擎垂直切片，但玩家感受仍是“我在配工具链”。

Severity: Critical，因为 programmable game 的流失通常发生在第一个成功反馈之前。

### G2 — High — MCP resources “可自学性”还没有足够严格的验收标准

P0-6 说 AI 通过 `swarm://docs/tutorials/basic-agent`、`swarm_get_docs`、`swarm_get_available_actions` 学习。但从 AI 玩家视角，需要更强的 contract：

- MCP resource 是否包含最小可运行 bot？
- 是否包含当前 world rules 的自然语言摘要？
- 是否包含“下一步建议”？
- `swarm_get_available_actions` 返回的是 API 列表，还是结合当前 snapshot 的 affordance？
- AI 不知道地图目标时，是否能通过 resources 理解“什么是好表现”？

建议增加 AI onboarding eval：给一个全新 agent，只允许访问 MCP resources/tools，不给外部说明，目标是在 N 次调用内部署一个能采集并运回资源的 WASM bot。这个 eval 应作为 Phase 2 验收。

Severity: High，因为“AI 原生界面”是 Swarm 的核心差异化，如果 AI 仍需人类读 DESIGN.md 喂提示，就不算闭环。

### G3 — High — World Rules Engine 的表达力很强，但玩家认知负担过高

当前规则系统包含：自定义资源、多资源成本、全局/本地存储、物流时间、累进税、代码传播、memory upkeep、drone lifespan、特殊攻击、伤害类型、抗性、模组、i18n。作为引擎平台这很棒，但作为默认游戏可能过载。

风险：新玩家进入一个服，看到几十个规则参数，却不知道哪些影响策略优先级。

需要补一层“规则 UX”：

- Rule Digest：一句话概括这个世界怎么玩，例如“轻物流 + 快速扩张 + 公开 Arena”。
- Complexity Rating：1–5 星复杂度。
- Strategy Hints：规则变化对 bot 策略的影响，例如“有 memory upkeep，请避免给每个 drone 写大量 env”。
- Preset Packs：Default World、Tutorial、Arena Duel、Hardcore Logistics、Economy Server。
- Diff from Default：展示本世界与默认规则的差异，而不是完整 world.toml。

Severity: High，因为规则可配置若没有可理解层，会降低加入率，并削弱社区服务器发现。

### G4 — High — 长期追求仍偏“扩张数值”，缺少玩家身份与收藏型目标

当前长期目标主要是 GCL、room level、房间数、drone 数、资源、排行榜。对硬核优化玩家足够，但对社区传播和长期留存还不够。

建议加入非纯数值目标：

- Bot lineage：代码版本家谱，展示某个 bot 从 v1 到 v42 的进化。
- Strategy badges：例如“无攻击占领 3 房”“100 tick 内恢复经济”“最低 fuel 完成采集闭环”。
- Public bot zoo：玩家可发布只读 bot 包，别人 fork、评分、跑 benchmark。
- World achievements：服务器级成就，例如“首次跨房间贸易”“首次公开锦标赛冠军”。
- Replay highlight collection：玩家主页展示精选片段。

Severity: High，因为 GCL/RCL 只服务优化型玩家，不足以支撑内容创作型、收藏型、社交型玩家。

### G5 — Medium — Replay 分享设计有方向，但还缺“传播格式”

P0-6/P0-5 已有 replay viewer、分享 URL、解说覆盖层、公开 Arena 回放。但还没有定义分享对象的最小内容单元。

建议明确三种传播格式：

- Replay URL：完整 tick 时间轴。
- Clip：tick A–B 的短片段，带标题、注释、视角、fog-of-war 切换。
- Strategy Card：比赛/世界事件摘要卡，包含 bot 名、关键指标、胜负原因、可复现 seed。

特别是 Clip 很关键。完整 replay 太长，社区传播需要“30 秒看懂”的切片。

Severity: Medium，因为不阻塞核心可玩，但会显著影响社区增长。

### G6 — Medium — “可解释性”目前偏错误解释，还应包含策略解释

`swarm_explain_last_tick` 现在能解释成功/失败、状态变化、notable events，这很好。但 programmable game 的满足感来自“我理解了策略为什么有效”。

建议增加 strategy-level explanations：

- 我的 energy/tick 为什么下降？
- 哪些 drone 长期 idle？
- 哪个房间是瓶颈？
- 我的 command rejection 是否集中在某类错误？
- 如果我增加 Carry body part，预计收益如何？

可以先不做 AI coach，但数据结构要预留“metric attribution”。

Severity: Medium，因为这会决定玩家能否从“能运行”进入“想优化”。

### G7 — Medium — Arena 的观赏性胜利条件仍偏传统 RTS，可考虑更适合代码竞技的赛制

Arena 当前胜利条件是摧毁敌方 Spawn 或时限比分。这可行，但代码竞技还有更多有趣赛制：

- Efficiency Duel：同资源、同地图，比单位 fuel 的产出。
- Survival Script：面对同一波 PvE 压力，看谁撑得久。
- King of the Hill：控制中心区域累计 tick。
- Logistics Race：谁先把 N 单位资源运到目标点。
- Blind Bot Challenge：开局只给部分地图信息，考验探索算法。

Severity: Medium。基础 Arena 可先做，但赛制多样性会影响赛事内容生命力。

### G8 — Medium — 默认经济的“全局存储”可能削弱空间策略，需要谨慎调参

默认轻物流模式很友好，但如果全局存储过强，玩家会把空间问题抽象成全局余额，减少“运输线、前线补给、本地仓库”的 RTS 味道。文档已有反制：税、隐匿、运输时间、拦截。但 Phase 1/2 应尽早用 sim 验证默认参数。

建议定义经济健康指标：

- 本地资源占比 vs 全局资源占比。
- 运输指令占总指令比例。
- 前线断供是否真实发生。
- 大玩家囤积是否压制新玩家市场。

Severity: Medium，因为这不是架构问题，是调参问题，但会直接影响“像不像 RTS”。

### G9 — Low — 文档中存在少量命名/一致性瑕疵，可能影响 AI 读取

例子：

- DESIGN §11.1 后出现 “### 10.2 代码规范”，编号不一致。
- P0-1 状态仍写 Phase 2 阻断项，而 DESIGN Phase 0 已标记完成，状态语义可能混淆。
- `spectate_delay` 在 world.toml 示例中注释为“回放无延迟”，但字段是旁观延迟，容易误读。
- P0-2 仍写“所有入口（WASM tick 输出、MCP tool、REST API、admin CLI）走同一校验路径”，但 P0-9 已明确 MCP_Deploy/MCP_Query 不提交 gameplay。建议改成“所有 gameplay-capable sources”。

Severity: Low。不会影响设计方向，但会影响 AI agent 仅靠文档学习时的稳定性。

## Missing

1. 缺少 First-Hour Journey 文档

建议新增 `specs/p0/10-first-hour-player-journey.md` 或放入 P0-6，明确人类玩家和 AI 玩家第一个小时的逐分钟目标、UI 状态、成功指标、失败兜底。

2. 缺少 MCP Self-Learning Eval

需要一个机器可跑的验收：新 agent 只靠 MCP resources，在空白 tutorial world 内生成、验证、部署 basic bot，并在若干 tick 内达成采集目标。

3. 缺少 Default Rules Preset

现在 world.toml 示例很多，但还缺“官方默认世界”的最终冻结参数，以及为什么这些参数适合新手/长期世界。

4. 缺少 Replay Clip Schema

TickTrace 支持 replay，但还需要面向分享的 Clip/Annotation schema：标题、tick range、camera path、fog mode、annotations、safe visibility mode。

5. 缺少 Player Profile / Bot Profile 设计

长期社区需要玩家主页、bot 主页、版本历史、成就、公开 replay、fork 链接。否则社区资产散落在代码仓库和 replay URL 中。

6. 缺少 Live Ops / Server Discovery 设计

既然 Swarm 是可配置世界平台，就需要世界列表如何展示：规则摘要、复杂度、在线人数、tick rate、PvP 强度、AI-friendly 程度、replay policy、推荐 starter bot。

7. 缺少 Fun Metrics

技术指标很多，如 fuel、latency、rejection rate；但产品侧还需要：首个成功部署时间、首个资源采集时间、教程完成率、首个 replay 分享率、7 日内 bot 版本迭代次数。

## Fresh Ideas

1. “Bot Gym” 作为 AI/人类共同训练场

提供一组固定 scenario：采集、物流、防守、扩张、战斗、恢复。每个 scenario 有 seed、目标、评分函数。人类和 AI 都可以本地跑：

`swarm gym run basic-harvest --bot ./mybot --ticks 1000`

这会把学习、benchmark、内容分享统一起来。

2. Replay Clip 一键生成“策略卡”

每场 Arena 或关键 World 事件自动生成一张 Strategy Card：

- bot 名称和版本
- 关键 tick
- 决胜事件
- energy/tick 曲线
- fuel 使用曲线
- 3 个 replay clip

这非常适合论坛、X/Twitter、Discord/Telegram 传播。

3. MCP Resource 加“任务式教程”而不只是文档

例如：

`swarm://tutorials/basic-agent/step/3`

返回：当前目标、可用工具、示例代码片段、验收条件。AI agent 完成后调用 `swarm_submit_tutorial_step`，服务端返回下一步。这会比纯 docs 更适合 agent 自学。

4. “World Rule Diff” 生成 bot migration hints

当玩家把 bot 从一个世界部署到另一个世界时，系统自动提示：

- 这个世界有 Matter，spawn 成本不同。
- code update 有 100 tick cooldown。
- memory upkeep 非零，你的 bot 使用大量 env_vars。
- global storage disabled，你需要显式物流。

这能把规则复杂度转化为可操作建议。

5. Public Bot Zoo + Forkable Starter Bots

官方 starter bot 不应只是代码样例，而应是可 fork、可跑 benchmark、可看 replay 的公共实体。玩家可以发布自己的 bot，但默认只公开接口/README/成绩，不泄露源码，除非选择开源。

6. “Why idle?” 做成最重要的新手按钮

在 UI 中选中 drone 后，第一按钮不是属性面板，而是：

“为什么它没做事？”

返回可行动建议。这比完整调试器更符合新手心理。

7. Arena 解说 Overlay 标准化

Replay annotation 不只让人手写，也可以由系统自动标注：

- first contact
- first kill
- economy lead change
- spawn destroyed
- mass idle detected
- decisive failed command burst

这样 replay 天然适合观看。

8. “Ghost Replay” 对比调试

玩家本地 sim 两个 bot 版本，在同一 seed 上并排 replay。展示 v12 与 v13 的差异：哪个 tick 开始资源曲线分叉，哪个命令导致失败。这会极大提升优化体验。

## Final Recommendation

可以进入实现，但请把 Phase 1/2 的成功标准从“引擎能 tick”提高到“玩家/AI 能完成闭环”。

最低产品门槛建议：

1. 人类玩家：5 分钟内改动 starter bot 并看到世界变化。
2. AI 玩家：只靠 MCP resources/tools 部署 basic bot。
3. 调试：每个失败命令都有可读原因和下一步建议。
4. Replay：至少能生成一个可分享的安全 clip，而不只是内部 TickTrace。
5. 世界规则：默认规则有摘要、复杂度、diff 和策略提示。

如果这五点成立，Swarm 不只是技术上优雅，也会在第一小时真的好玩。