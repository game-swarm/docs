# R7 — Game Designer Review (rev-gpt-designer)

评审范围：`/data/swarm/docs/design/` 全部文档，以及 `/data/swarm/docs/specs/p0/` 全部 P0 规范。
评审视角：游戏是否好玩；第一个小时体验；AI 玩家能否仅靠 MCP resources 学会；旁观/Replay/社区传播；除 GCL 与 room level 之外的长期追求。

## Verdict

APPROVE_WITH_RESERVATIONS

Swarm 的核心幻想很强："你的代码就是你的军队"，且 P0 后的架构已把最危险的公平性问题收敛到正确方向——AI 与人类都写 WASM，MCP 只是屏幕、IDE、部署和调试界面，不是 gameplay action 通道。这让它不像一个普通 RTS，而更像一个可编程生态、策略实验室和 AI agent 竞技场。

从游戏设计角度看，当前设计已经具备可玩的骨架：采集→建造→spawn→扩张→战斗/Arena→Replay 的主循环清晰；MCP 教程、starter bot、dry-run、tick explanation、本地模拟这些设计能显著降低学习成本；World/Arena 双模式也正确区分了"持久涌现"与"公平竞技"。

但我不建议直接以当前设计进入完整产品实现。最大问题不是技术，而是玩家心理曲线与内容节奏：第一个小时仍偏"工程系统验证"，还不够像游戏；长期目标除 GCL/room level/赛季 Elo 之外仍缺乏更有情感粘性的追求；社区传播机制有 replay/share 的方向，但还没有足够明确的"可炫耀物"与"可复用策略资产"。这些不阻断 Phase 1/2，但应该在 Phase 4/5 前冻结成 UX/game design 规范，否则后面会变成一个技术很强、留存偏窄的程序员沙盒。

## 问题（severity）

### G1 — High — 第一个小时的玩家目标仍不够锋利

当前 P0-6 定义了 5 分钟教程、starter bot、tick explanation、指标面板，这是正确方向。但第一个小时之后玩家要追什么仍不够明确。

现在的 early loop 大致是：
1. 看教程 bot 动起来。
2. 改一个参数。
3. 采集更多 Energy。
4. spawn 更多 drone。
5. 建造 Tower/Extension。
6. 进入 World 或 Arena。

问题在于：这条线很像"学会 API"，不一定像"我想再玩一局"。尤其对非 Screeps 老玩家，"让代码控制 drone"本身很新鲜，但如果 30-60 分钟内没有一次清晰的胜利、危机或惊喜，留存会弱。

建议：Phase 4 的教程不要只做操作教学，应加入明确的 First Hour Questline：
- 00-05 分钟：看到 starter bot 自动采集，获得第一次正反馈。
- 05-15 分钟：玩家改一行代码，让效率提升 2x，有可视化对比。
- 15-30 分钟：遭遇一个 scripted 资源瓶颈或小型入侵，要求建 Tower 或改策略。
- 30-45 分钟：解锁第二个 room/arena bot challenge。
- 45-60 分钟：生成一张可分享的"我的第一个 autonomous colony" replay card。

验收标准不应只是"能运行 1000 tick"，还应包含：新玩家 60 分钟内完成 3 个可见成就，并能解释自己代码做了什么。

### G2 — High — AI 玩家仅靠 MCP resources 能否学会：方向正确，但缺少"自举课程合同"

P0-3/P0-6 已经列出 `swarm_get_docs`、`swarm_get_schema`、`swarm_get_available_actions`、`swarm_validate_module`、`swarm_deploy`、`swarm_explain_last_tick`，理论上 AI 可以闭环。但设计还没有定义 MCP resources 的信息架构与最低可学会标准。

对 AI agent 来说，"有 docs"不等于"能学会"。如果资源只是 API reference，agent 很容易陷入：能读 schema，但不知道最小可行策略；能 deploy，但不知道为什么 bot 闲置；能看 snapshot，但不知道优先级。

建议新增一个 P0/P1 级别的 AI Onboarding Contract：
- `swarm://docs/tutorials/basic-agent` 必须是 step-by-step playbook，而非说明文。
- 必须提供可复制的 starter strategy 源码、编译命令、部署 payload 示例、预期 tick 结果。
- 每个教程 step 都要有 machine-checkable success condition，例如 `energy_income_per_100_ticks > X`、`commands_rejected == 0`。
- `swarm_get_docs` 返回的 docs 应分层：quickstart / concepts / API reference / recipes / troubleshooting。
- `swarm_explain_last_tick` 需要给出下一步建议，而不仅是 rejection reason。

建议验收：一个无先验上下文的 AI agent，只访问 MCP resources 和 tools，在 30 分钟内能部署 `basic-harvester`，并在 200 tick 内实现正能量收入。

### G3 — High — 长期追求不足：GCL、房间数、Elo 不够承载持久世界

设计中有 GCL、Controller level、room count、Arena league/Elo、赛季锦标赛。这些是必要的，但对长期留存不够。Screeps 的魅力不只是升级，而是"我的殖民地是我的作品"。Swarm 目前对作品感、身份感、收藏感、历史感描述不足。

建议补充多层长期追求：
- 策略资产：bot 版本谱系、策略模块库、公开 benchmark、策略签名。
- 殖民地身份：殖民地徽章、地图铭牌、建筑布局截图、首次占领历史。
- 科研/优化：效率排行榜按场景拆分，例如 harvester efficiency、spawn uptime、combat micro、pathfinding cost。
- 社区声望：best replay、best comeback、most elegant bot、AI-only tournament champion。
- 创作经济：规则模组、starter bot、strategy package 可发布、fork、评分。

这类目标不一定影响引擎 P0，但应尽早进入 product spec，否则系统会偏向"硬核玩家 self-directed sandbox"，新玩家缺少情感锚点。

### G4 — Medium-High — World Rules Engine 很强，但可能导致新手认知过载与世界碎片化

可配置资源、多资源经济、全局/本地存储、物流模式、Rhai 模组、visibility、code propagation、memory upkeep 等都很有深度。但如果玩家一开始进入一个高度自定义的 World，会很难判断：失败是自己代码差，还是世界规则不同？AI agent 也会需要解析大量配置再决策。

建议：明确世界模板层级：
- Core World：官方标准规则，长期稳定，用于学习和大多数玩家。
- Arena Standard：竞技标准规则，赛季锁定。
- Modded Worlds：社区实验，明确标记非标准。
- Tutorial World：强脚本化、低惩罚。

另外需要 UI/MCP 上的 Rules Diff：进入世界时展示"此世界与 Standard 的差异"，而不是完整 world.toml。AI 也应能调用 `swarm_get_world_rules_diff(standard)` 或在 `swarm_get_world_rules` 中得到 diff summary。

### G5 — Medium-High — Replay 与旁观设计方向对，但传播闭环还不完整

P0-5/P0-6 对 spectator、replay、delay、privacy 的安全边界设计得不错：旁观者只能看物理状态，不能看代码、env_vars、debug info。Arena 赛后公开全知回放也很适合传播。

缺口是"为什么别人会想点开"以及"分享后能做什么"。Replay 不是只有播放器，还应该是社区内容单位。

建议补充：
- Replay Card：自动生成封面，包括双方名、地图、关键事件、胜负、时长、精彩 tick。
- Moment Clip：玩家可截取 tick range，生成 30-90 秒片段链接。
- Annotated Replay：解说层可添加文字/箭头/策略标签。
- Fork From Replay：观看 replay 后可复制某个公开 starter/strategy package，进入本地 sim 尝试改进。
- Arena Postmortem：自动总结"胜负手"，例如经济曲线交叉点、首次 tower timing、最大 command rejection spike。

如果没有这些，Replay 会成为调试工具；有了这些，它才会成为传播工具。

### G6 — Medium — Arena 的观赏性与胜利条件还偏粗

P0-6 的 Arena 胜利条件是摧毁敌方 Spawn，或时限结束按分数。方向合理，但还缺少 scoring contract。可编程 RTS 的比赛很容易出现双方龟缩、长时间无交互、或单一 rush meta。

建议 Arena 至少定义三类官方地图/规则：
- Duel：小地图、固定资源点、鼓励早期接触。
- Macro：多资源、多扩张点，考察经济与扩张。
- King of the Hill：控制中心区域得分，强迫交互。

分数也不应只按存活或资源总量，建议包括：controller progress、地图控制、资源净收入、敌方伤害、单位保存率等，并公开权重。这样 replay 与解说更有故事线。

### G7 — Medium — 指令模型与 SDK API 的表现层需要更"玩家语义化"

底层 deferred command model 很正确，但玩家不应长期面对裸 JSON command。P0-8 的 IDL 可生成 TS/Rust SDK，这是好设计。需要确保 SDK 的表层 API 更接近玩家意图，例如：
- `drone.harvestNearest()`、`spawn.spawnWorker()`、`room.findSources()` 这类 recipe helper。
- 明确区分 low-level commands 与 high-level library。
- starter bot 应展示从 helper 逐步下钻到 command 的学习路径。

否则新玩家会感觉自己在写协议适配器，而不是写策略。

### G8 — Medium — 本地模拟是关键留存工具，应前移优先级

P0-6 把 `swarm sim` 标为 P1/Phase 3，Phase 5 才强调本地模拟。作为游戏设计评审，我建议尽量前移。可编程游戏最大的爽点是快速迭代；3 秒 tick 的线上世界适合持久性，但不适合学习和调参。

如果玩家每次改代码都要等待线上 tick，早期挫败会很强。`swarm sim --ticks=5000 --speed=100x` 应该尽早成为 starter bot 与教程的一部分。

建议 Phase 1/2 就提供最小 sim：单房间、固定 terrain、固定 source、无 FDB、输出指标即可。完整 deterministic replay 可以后续增强。

### G9 — Medium — 社区服主与模组市场很有潜力，但需要治理设计

Rhai 模组市场是很好的长期内容来源。但多人持久世界里，模组会影响公平、学习成本和策略迁移。当前有 rating/install 设想，但缺少治理规则。

建议：
- 官方 Standard 规则长期稳定，作为 SDK/docs 默认目标。
- 模组必须声明 determinism、balance impact、AI-readable docs、compatibility tags。
- 世界浏览器按 Standard-compatible / Experimental / Hardcore 分类。
- Replay 和排行榜必须绑定规则 hash，避免不同规则下的成绩混排。

### G10 — Low-Medium — `PLANNER-OUTPUT.md` 保留了已废弃 MCP gameplay executor 内容，容易误导后续读者

文档开头已注明 Planner 草案过时，P0 已修正。但正文仍大量出现 `McpPlayerExecutor`、MCP gameplay tools、"AI 不需要 WASM"等被否定的旧方案。对评审者或新贡献者来说，这是危险噪音。

建议：把该文件移到 `archive/` 或改名为 `PLANNER-OUTPUT-OBSOLETE.md`，并在每个过时小节加显式 `SUPERSEDED BY P0-3/P0-9` 标记。当前只在开头说明一次，仍不够防误读。

### G11 — Low — 教程世界中的受限手动引导需要更明确边界

设计强调正式世界不开放 manual_control，仅 Tutorial 有受限引导操作。这是正确的。但 Tutorial Source 在 P0-9 中允许 gameplay 指令，虽然隔离，但仍应定义这些动作是否会生成可迁移代码知识。

建议：教程引导不要让玩家习惯"点击移动 drone"，而应让玩家通过修改代码触发变化。任何手动动作都应呈现为"临时教学辅助"，并尽快转化为对应代码片段。

## 亮点

### S1 — 核心公平性方向非常好：AI 与人类同走 WASM

这是整个设计最重要的胜利。AI 不通过 MCP 直接 move/attack/build，而是写 WASM、部署、由同一 WasmSandboxExecutor 执行。它同时解决：
- AI 与人类能力不对称；
- 反作弊与资源计量复杂化；
- replay 无法复现 LLM 行为；
- MCP gameplay tool 膨胀。

"世界只认 WASM"是非常强的产品叙事，也是一条清晰的工程边界。

### S2 — Feedback Loop 意识成熟

P0-6 明确把学习、决策、行动、理解做成闭环，并提供 tutorial、available_actions、dry_run、explain_last_tick、strategy metrics、replay viewer。这说明设计没有只停留在 engine，而是在考虑玩家如何实际迭代。

尤其 `swarm_explain_last_tick` 和 rejection reason 的结构化解释，对人类与 AI 都是关键 UX。

### S3 — World/Arena 双模式划分正确

持久 World 不追求公平，追求涌现、创造、长期存在；Arena 追求对称、公平、赛季、公开 replay。这个切分避免了很多 MMO RTS 常见矛盾：持久世界天然不公平，但竞技又必须公平。

这也给社区传播提供了两条路径：World 讲故事，Arena 做赛事。

### S4 — Replay、Spectator、Visibility 的安全边界清楚

P0-5 对玩家视野、drone snapshot、旁观者视图、公开 replay、隐藏信息的分层很细。尤其明确旁观者不能看到代码版本、部署历史、env_vars、debug info、指令列表，这是正确的。

`spectate_delay` 与 Arena 赛后公开 replay 是非常适合可编程竞技的设计。

### S5 — IDL 单一真相来源能显著降低 API 漂移

P0-8 的 `game_api.idl → Rust/TS/MCP/Docs/Test` 是非常正确的。对这类游戏，API 漂移会直接破坏玩家 bot、AI docs、教程和 replay。IDL-first 能把"游戏规则"变成可验证合同。

### S6 — World Rules Engine 有平台潜力

Rhai 模组 + world.toml + i18n + MCP 可读规则，让 Swarm 不只是一个 Screeps clone，而是可编程策略游戏引擎。社区可以做不同经济模型、资源系统、upkeep、fog、territory control，这会显著扩展内容寿命。

### S7 — Determinism Contract 很完整，支撑游戏设计上的信任

Blake3、禁 f64、IndexMap、固定 ECS 顺序、TickTrace、replay verification，这些看似技术细节，但对玩家心理很关键。玩家要相信：失败是策略问题，不是服务器随机抽风；比赛结果可复盘；争议可重放。

### S8 — Starter Bot 与 MCP 教程的方向能服务 AI 原生传播

如果实现得足够好，Swarm 很适合成为"AI agent benchmark as game"。AI 玩家可以公开自己的 bot、参加 Arena、分享 replay、被人类 fork 策略。这是比传统 Screeps 更有时代感的定位。

## Missing / 建议新增设计文档

1. `FIRST-HOUR-EXPERIENCE.md`
   - 定义新玩家 0-60 分钟体验、成就、情绪曲线、失败恢复、可分享时刻。

2. `AI-ONBOARDING-CONTRACT.md`
   - 定义 MCP resources 树、AI 从零部署 starter bot 的验收标准、machine-checkable tutorial steps。

3. `REPLAY-AND-SHARING-SPEC.md`
   - 定义 replay card、moment clip、annotated replay、fork from replay、postmatch summary。

4. `PROGRESSION-AND-META.md`
   - 除 GCL/room level/Elo 外的长期追求：策略资产、殖民地身份、社区声望、收藏、赛季遗产。

5. `ARENA-MODES-AND-SCORING.md`
   - 定义官方 Arena 地图类型、胜利条件、计分权重、防龟缩机制、观战数据。

6. `STANDARD-WORLD-PROFILE.md`
   - 定义官方标准规则与 modded world 的 diff/compatibility 机制，避免规则碎片化。

## Fresh Ideas

1. Colony Replay Card
   - 每个玩家完成教程后自动生成一张卡：殖民地名、第一架 drone、首次建造、能量曲线、10 秒动图式 replay preview。

2. Strategy Package Registry
   - 玩家可发布 `strategy.toml + wasm/module source + docs + benchmark results`。别人可 fork、评分、在本地 sim 跑分。

3. Bot Gym Challenges
   - 官方提供小型离线挑战：1000 tick 内采集最多 Energy、最少 fuel 完成 spawn、固定敌人入侵防守。排行榜按 deterministic seed 分组。

4. Explainable Bot Timeline
   - 回放中显示"bot 版本 v3 在 tick 450 部署；之后 rejection rate 从 20% 降到 3%"，让代码迭代本身成为故事。

5. Arena Commentary Overlay
   - 自动标注关键事件：首次扩张、首次攻击、经济反超、tower timing、spawn 被摧毁。方便社区解说和短视频传播。

6. AI vs Human Mixed League
   - 不只是 Human/WASM 与 AI tournament，也可以有 AI-assisted league：人类写策略框架，AI 做局部优化，明确标注。

7. Rules Diff Banner
   - 进入任何世界时显示："Compared to Standard: Matter enabled, code updates cost 500 Energy, fog disabled, upkeep mod active." AI MCP 同样读取此 diff。

8. Public Benchmark Seeds
   - 官方维护固定 benchmark seeds，让玩家优化 bot 时有共同语言："我的 harvester 在 seed-2026-01 上 5000 tick 产出 12,430 Energy。"

9. Strategy Archaeology
   - 长期 World 中保留 bot 版本历史与殖民地发展树，玩家可以回看"我的帝国如何从 starter bot 演化到 v42"。

10. Spectator Safe Heatmaps
   - 旁观者不可见内部代码，但可以看公开物理热力图：战斗密度、资源流动、扩张速度。既安全又有观赏性。

## Final Recommendation

允许 Phase 1/2 继续推进，但在 Phase 4/5 前补齐 First Hour、AI Onboarding、Replay Sharing、Progression Meta 四份产品设计合同。Swarm 的技术设计已经足够独特；下一步要确保它不仅是一个优雅的可编程引擎，也是一款玩家愿意留下、愿意分享、愿意反复优化的游戏。
