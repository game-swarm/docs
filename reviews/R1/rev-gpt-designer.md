# Swarm R1 设计评审 — Game Designer 视角

Reviewer: rev-gpt-designer
Scope: `/data/swarm/docs/design/DESIGN.md`, `/data/swarm/docs/design/tech-choices.md`, `/data/swarm/docs/ROADMAP.md`, `/data/swarm/docs/specs/`（请求路径 `/data/swarm/docs/specs/p0/` 不存在；实际读取 specs 目录中的 P0/核心规范，尤其 `03-mcp-security-contract.md`, `05-unified-visibility-policy.md`, `06-mvp-feedback-loop.md`, `08-game-api-idl.md`）
Perspective: 创意构思、UX 模式、社区动力学、玩家心理学、第一小时体验、AI 玩家可学性、观战/回放传播、长期追求

## Verdict

APPROVE_WITH_RESERVATIONS

设计已经具备一个“可被玩、可被学、可被观看、可被 AI 参与”的 programmable MMO RTS 核心闭环。最强的地方是它明确修正了 AI 玩家路径：AI 不通过 MCP 作弊式下指令，而是和人类一样写 WASM；同时 MVP 反馈循环文档把 Learn → Decide → Act → Understand 作为 P0 目标，这从游戏设计角度非常关键。

但我不建议直接把当前默认规则当作最终对外版本冻结。主要保留意见不是技术可行性，而是“第一小时的认知负荷”和“长期目标结构”。当前规则集合过于慷慨：多资源、轻/重物流、drone age、Controller/RCL、Depot、特殊攻击、市场、Arena、模组、AI 锦标赛几乎都已经进入同一设计面。对 Screeps 老玩家这很诱人；对新玩家和新 AI agent 则可能像在第一小时打开了完整 4X/RTS 规则书。

建议：R1 可以通过，但需要在设计文档中补一个“Vanilla First Hour Ruleset / Progressive Reveal Contract”，明确哪些规则在 Tutorial 与第一个 World 房间中默认隐藏、延后、或只作为灰显目标呈现。否则 P0 的学习闭环虽然存在，心理上仍可能断裂。

## 发现的问题

### G1 — Blocker — 第一小时可玩性仍未被规格化；功能清单等于上手路线，但不是玩家心理路线

文档已有 5 分钟教程、starter bot、每 tick 解释、本地模拟、回放查看器，这是正确方向。但当前教程只定义了“做什么”：改 spawn_count、采集、建 Tower、部署到 World/Arena；没有定义“玩家第一小时应该形成哪些 mental model”：

- 我为什么要写代码，而不是手动控制？
- 一个 drone 的生命周期为什么重要？
- 失败时我应该看地图、看 rejection、看 replay，还是看代码？
- World 和 Arena 哪个是新手默认去处？
- 我的第一个可感知胜利是什么：多采 100 Energy、升 RCL2、挡住一次袭击、还是打赢 bot？

风险：玩家在 5 分钟教程后进入 World，被 GCL/RCL/age/物流/市场/特殊攻击同时淹没；AI agent 虽然能读 docs，但缺少“从 basic-harvester 到 first-defender 到 first-claimer”的 curriculum。

建议：新增 `FirstHourJourney` 规格，至少包含：
1. 0-5 min: edit starter bot → 看到 drone 采集成功。
2. 5-15 min: 解释 3 个 rejection 并修好一个 bug。
3. 15-30 min: 本地 sim 对比两个策略，明确指标差异。
4. 30-45 min: 部署到 protected novice room，只开放 Energy + Spawn + Extension + Tower。
5. 45-60 min: 公开分享一个 replay 或挑战一个 scripted bot。

### G2 — High — 默认 Vanilla 规则过宽，容易让“可配置引擎平台”压过“一个清晰好玩的游戏”

DESIGN 的平台野心很强：world.toml 可配置资源、body parts、damage types、special effects、custom actions、Rhai mods、物流模式、市场、Arena/World 双模式。作为引擎设计，这是亮点；作为默认游戏，它可能缺少一个强烈、可复述的 meta。

目前玩家很难一句话理解 vanilla 的策略核心到底是：

- 物流优化？
- 代码效率？
- 领土扩张？
- 抗性配装？
- 特殊攻击 counter-pick？
- 市场套利？
- AI 锦标赛？

这些都好玩，但同时出现会稀释学习路径，也会让社区讨论碎片化。

建议：明确 Vanilla 的设计宣言，例如：
“Vanilla Swarm 的核心是 logistics under code constraints：你用代码自动化采集、补给、续命、扩张；战斗是后勤压力测试。”

然后把特殊攻击、复杂伤害抗性、市场、Fabricate 等标为 Advanced/Arena/Seasonal，而非第一默认世界的核心。

### G3 — High — 长期追求主要仍是 GCL、房间、排行榜；缺少“可收藏/可展示/可传承”的身份系统

文档提到 GCL、房间数、殖民地年龄、Arena league、锦标赛、排行榜；这些适合竞争型玩家，但 programmable MMO 的长期粘性还需要非零和追求：展示、身份、收藏、贡献、声望。

缺口：
- 没有 colony identity：殖民地旗帜、命名、历史墙、自动生成战报。
- 没有 bot lineage：某个 bot 策略的版本树、fork、谱系、名局。
- 没有成就/徽章：第一次 RCL2、第一次 100% uptime、第一次无 rejection 运行 1000 tick、最佳 energy/tick。
- 没有社区贡献路径：公开 starter bot、分享 replay annotations、发布 world.toml/mod preset。

建议新增长期追求层：
- Colony Chronicle：自动记录“第 N tick 建成第一座 Tower”“第 N tick 抵御第一次入侵”。
- Bot Hall of Fame：按赛季保存 module hash、作者、策略说明、代表 replay。
- Mentorship Quests：老玩家发布 challenge，新手提交 bot 通过后获得 badge。
- Aesthetic progression：地图皮肤/旗帜/称号，不影响战斗公平。

### G4 — Medium — AI 玩家“仅通过 MCP resources 学会怎么玩”方向正确，但缺少机器可执行课程与自测标准

MCP 提供 `swarm_get_docs`, `swarm_get_schema`, `swarm_get_available_actions`, `swarm_dry_run_commands`, `swarm_explain_last_tick`，这已经是很好的 AI 学习接口。问题是 docs/tutorial 仍偏“说明书”，不是“可判定的课程”。AI agent 最需要的是：目标、输入、预期输出、检查器、下一步。

建议把 MCP tutorial 设计为 resource graph：

- `swarm://tutorials/basic-agent/lesson/01-harvest`
  - objective: spawn 1 WORK+CARRY+MOVE drone and harvest 100 Energy
  - allowed_docs: API subset
  - success_check: `swarm_check_objective`
  - hints: structured, progressive
- lesson 02: fix OutOfRange
- lesson 03: use sim to compare pathing
- lesson 04: build Tower
- lesson 05: deploy to novice World

注意：不需要 MCP 直接操作游戏；`swarm_check_objective` 只检查世界状态/教程状态，不是 gameplay command，因此不破坏公平性。

### G5 — Medium — 旁观者与 replay 规格扎实，但传播机制还停在“能看”，没到“想分享”

Replay viewer 已包含时间滑块、指令箭头、采集动画、战斗效果、解说覆盖层、safe view URL；Arena 赛后 public replay 也合理。缺口是社交传播的 packaging：什么片段值得分享？分享出去的人能不能 10 秒看懂？

建议补充：
- Auto-highlight：自动标记 comeback、first kill、spawn destroyed、resource swing、tower clutch、mass rejection bug。
- Share cards：生成 10-30 秒 clip/GIF 的标题、比分、tick 区间、关键指标。
- Fog-of-war toggle presets：`what I saw` vs `omniscient`，帮助观众理解“当时为何做错”。
- Replay comments/annotations：允许作者给 tick 区间加注释，形成攻略内容。
- Arena weekly digest：自动聚合本周最精彩 5 场。

### G6 — Medium — World 模式默认 `public_spectate=false` 安全合理，但社区冷启动会变慢

安全与反情报角度，World 默认不公开旁观合理；但社区传播角度，新人如果看不到“活着的世界”，很难产生加入欲望。当前规则允许 replay privacy 与 spectate delay，但产品默认没有一个“安全展示窗”。

建议：World 首页提供 delayed public map layer：
- 延迟足够长，例如 500-1000 tick。
- 只显示地形、Controller owner/RCL、战斗热度、建筑轮廓，不显示资源量/指令/代码/内部状态。
- 对新手展示“这里发生过什么”，而不是实时情报。

这样既不破坏竞争，又能让 Swarm 看起来像 MMO，而不是只有登录后才知道是否有人玩。

### G7 — Medium — 特殊攻击体系创意强，但命名/效果存在“读起来酷，玩起来难预测”的风险

Hack, Drain, Overload, Debilitate, Disrupt, Fortify, Leech, Fabricate 形成了丰富 counterplay；尤其 Overload 攻击计算配额很契合 programmable game。但多个效果同时存在，会增加 explain_last_tick 和 balance 的压力。Fabricate “将敌方 drone 转化为己方建筑”尤其高概念，可能难以直觉理解，也可能带来大量边界问题。

建议：
- Vanilla 初期只启用 3 个特殊攻击：Disrupt, Fortify, Overload。
- Hack/Drain/Debilitate 作为 midgame unlock。
- Leech/Fabricate 作为 Arena seasonal/modded mechanics。
- 每个 special action 必须有 replay visual language：颜色、图标、持续时间条、反制提示。

### G8 — Low — ROADMAP 显示全模块 100% done，与评审语境可能冲突

ROADMAP 写明 Phase 0 已冻结且实现 100%，包括 Tutorial、Arena、锦标赛、观战解说等均完成。若 R1 评审是对设计做下一轮质量把关，这没问题；但如果读者以为“实现已完成，不再需要设计变更”，上述游戏体验问题可能被低估。

建议在 R1 review index 或 ROADMAP 增加“Design quality review findings are product/design refinements, not implementation gap audit”，避免把“已实现”误读为“已达到最佳体验”。

## 亮点

### S1 — AI 与人类同路径，是最重要的公平性与叙事亮点

文档明确：MCP 是 AI 的屏幕和鼠标，不是 gameplay controller；AI 必须写 WASM，与人类走同一 WasmSandboxExecutor、同一 fuel metering。这一点非常强，既避免“AI 玩家作弊”的社区争议，也让游戏叙事更纯粹：世界只认 WASM。

### S2 — Learn/Decide/Act/Understand 反馈循环非常正确

`06-mvp-feedback-loop.md` 把可玩性拆成学习、决策、行动、理解四步，并明确任何一步断裂都不可玩。这比单纯列功能更接近游戏设计本质。`swarm_explain_last_tick`、rejection suggestions、strategy dashboard 是降低 programmable game 挫败感的关键。

### S3 — Replay/观战设计已经意识到“公平性”和“观赏性”必须分层

`05-unified-visibility-policy.md` 区分 drone snapshot、玩家屏幕/MCP、旁观 WebSocket、replay privacy，并限制 spectator 只能看到物理状态，不看代码/指令/调试信息。这是很成熟的设计，能同时支持竞技、防作弊和内容传播。

### S4 — 本地模拟 `swarm sim` 是策略游戏迭代速度的核心

编程游戏最大痛点是反馈慢。`swarm sim --ticks=5000 --speed=100x` 直接解决“改代码要等现实时间”的问题，也给 AI agent 自我迭代提供了低成本路径。建议把它提升为新手教程的核心步骤，而不是 P1 附属功能。

### S5 — Drone lifespan + Depot 后勤线有潜力形成区别于 Screeps 的独特 meta

age 维修、Controller capacity、Forward Depot、补给线、摧毁后勤迫使前线撤退，这些机制把“代码优化”连接到了“空间后勤”。这是 Swarm 最有机会形成自己特色的地方：不是单纯复制 Screeps，而是让物流成为代码策略的一等公民。

### S6 — 可配置 world.toml + Layer 1/2/3 扩展模型利于社区生态

把官方稳定 SDK、声明式调参、实验性世界 SDK 分层，是社区服和官方竞技共存的好基础。`[MOD]` 标识、不参与官方排名、ABI hash 的方向也能降低玩家被不兼容规则坑到的概率。

### S7 — Debug explanations 的语气和结构对新手友好

OutOfRange 示例不仅说失败，还给 detail 和 suggestion；“为什么闲置？”也把 fatigue、body part、range 拆开。这类解释会显著降低 programmable game 的沮丧感，是 UX 上应坚持的资产。

## Missing / 建议补充的设计文档

1. `first-hour-journey.md`：按分钟描述玩家第一小时、目标、解锁、情绪曲线、失败恢复点。
2. `progressive-reveal-ruleset.md`：定义 Tutorial/Novice World/Arena/Advanced World 各自启用哪些系统。
3. `ai-curriculum-resources.md`：MCP resources 的课程图、lesson schema、success checks。
4. `community-sharing.md`：replay highlight、share card、weekly digest、annotation、public delayed world map。
5. `long-term-progression.md`：除 GCL/RCL/房间数外的 badge、colony chronicle、bot lineage、cosmetic identity、mentor challenges。

## Fresh Ideas

- “Strategy Diff”：两次部署之间自动生成策略差异报告：新增哪些行为、哪些 rejection 降低、energy/tick 变化多少。
- “Bot Autopsy”：失败后自动把 replay 切成 3 个根因：经济断粮、路径拥堵、战斗误判。
- “Ghost Race”：拿自己的 bot 和公开 replay 中的 champion bot 在同地图本地 race，学习差距。
- “Novice Safe League”：只允许 Energy + basic body parts + Tower，无市场无 special attacks，赛季 7 天重置。
- “Colony Newspaper”：每个世界每日自动生成报纸：最大扩张、最惨烈战斗、最高效 bot、最离谱 bug。
- “Explain as patch”：`swarm_explain_last_tick` 不只解释失败，还能生成对 starter bot 的最小补丁建议，供人类确认后应用。
- “AI-readable replay summaries”：为 AI agent 提供结构化 replay digest，让 AI 能从历史比赛学习，而不是只看原始 tick trace。
