# R14 游戏设计评审 — GPT

## Verdict

**CONDITIONAL_APPROVE**

从游戏设计视角看，Swarm 的核心幻想成立：玩家写代码生成自主军队，在持久世界与竞技场中通过算法、物流、侦察、战斗与调试循环获得成就。R14 文档已经解决了很多同类编程游戏最容易失败的问题：AI 与人类公平路径、首个 10 分钟 Golden Path、Replay/观战基础、可配置世界规则、反馈与调试闭环。

但我不建议直接 APPROVE。当前设计像一个很强的“可编程 RTS 引擎 + 工具链”，还没有完全收束成一个能留住玩家、能被社区传播、能让 AI agent 自举学会的“产品化游戏”。主要风险集中在：首小时情绪曲线仍偏技术验收，长期追求缺少可见的收藏/身份/社群目标，Arena 与 replay 的传播闭环被标为 RFC，AI 通过 MCP resources 学会游戏的路径还缺少从 schema 到策略范式的可执行脚手架。

## Strengths

1. **核心幻想清晰且差异化**
   - “世界只认 WASM。不论代码是谁写的”是非常强的公平承诺。
   - 人类和 AI agent 同走 SDK → WASM → deploy 路径，避免了 AI 通过 MCP 直接操作游戏动作而产生的特权感。
   - “Write once, fight forever”能很好支撑编程 MMO 的身份幻想。

2. **首个 10 分钟 Golden Path 有明确目标**
   - 从登录、SDK、编译、部署、观察、调试到首次 PvE 击杀的路径被压缩到 10 分钟内。
   - Tutorial 世界关闭 fog、免部署成本、无新手经济限制，符合降低初始摩擦的设计。
   - Starter bot、dry-run、explain-last-tick、first_tick_executed 事件都是让“代码产生世界反馈”的关键设计。

3. **反馈循环意识强**
   - LEARN → DECIDE → ACT → UNDERSTAND 四步模型正确，而且覆盖人类与 AI。
   - 每 tick explanation、idle 原因、经济仪表盘、指令溯源链对编程游戏特别重要。
   - AI 首次部署后推送 deploy_accepted / first_tick_executed，能显著降低 agent 的轮询盲区。

4. **World 与 Arena 的双核心定位合理**
   - World 接受不公平、强调有机生态；Arena 追求公平、可复现、可观赏。
   - 同一玩家用多个 WASM 策略自我对战，是编程玩家非常自然的学习方式。
   - PvE Challenge 隔离于 World 资产，避免 PvE 排行榜被持久经济污染。

5. **社区传播的技术底座已经存在**
   - TickTrace、Replay、spectate_delay、Replay privacy、战报卡 RFC、观战解说覆盖层都已经有雏形。
   - Arena 赛后公开 replay 与 PvE challenge leaderboard 具备形成“策略视频 / bot 展示 / 解说复盘”的潜力。

6. **可配置规则有助于长期生态**
   - world.toml、Rhai 模组、动态 SDK、MOD 标识，给服务器主和社区创造了长期内容扩展空间。
   - 规则可见性与 i18n 对 AI agent 和跨语言玩家都很重要。

## Concerns

### G1 — High — 首小时体验仍像“工具链验收”，缺少情绪节奏与目标钩子

文档定义了 10 分钟 Golden Path 和 First-Hour 过渡，但它们主要描述“能不能做成”和“能不能验证”，而不是“玩家为什么会兴奋”。玩家会看到 drone 采集、调试 idle、击杀 NPC；这足以证明游戏可玩，但未必足以让玩家在第一小时产生“我还想继续优化”的强动机。

具体问题：
- Tutorial 的情绪高潮只有“首次 PvE 击杀”，但缺少明确的可炫耀成果，例如第一张战报卡、第一段 replay、第一枚 badge、第一条策略指标提升。
- safe_mode → soft_launch → PvP 的节奏合理，但玩家在 tick 500-2000 期间的目标仍偏散：资源潮、遗迹、Arena challenge、contract 都是好点子，却缺少一条被 UI 明确串起来的“第一小时任务线”。
- “首次被攻击”有战斗报告，但“首次主动成功”也需要同等级反馈：首次资源潮抢占、首次 Claim、首次防住 NPC、首次策略迭代效率提升。

建议：
- 增加 **First-Hour Questline**：Deploy starter → fix idle → kill Creep → build Tower → survive first wave → publish first replay。
- 每个节点都给一个可分享或可收藏的结果：badge、highlight replay、strategy metric delta、bot version milestone。
- 把“10 分钟 Golden Path”扩展为“60 分钟留存路径”，明确第 15/30/60 分钟玩家应该追求什么。

### G2 — High — AI 仅靠 MCP resources “学会怎么玩”仍不够稳

MCP 工具集很完整，但“完整 schema + docs”不等于 agent 能形成有效策略。AI agent 需要的不只是 API 参考，还需要从状态解释到策略模板的 scaffold：如何识别源、如何选择 body、如何避免 idle、如何从 RejectionReason 修改代码、如何判断经济瓶颈。

当前已有：
- `swarm_get_schema`
- `swarm_get_docs`
- `swarm_get_available_actions`
- `swarm_sdk_fetch`
- `swarm_explain_last_tick`
- `swarm_dry_run_commands`
- `swarm_get_economy*`

缺口：
- MCP docs 没有明确区分“API reference”与“playbook”。AI 很容易读懂字段，却不知道策略优先级。
- `swarm_get_available_actions` 可能回答“现在能做什么”，但不一定回答“为什么这些动作对当前目标有意义”。
- Starter bot 有 basic-agent，但缺少多阶段可升级策略：harvester → builder → defender → claimer → scout。
- AI 的失败恢复路径需要更强：从 `OutOfRange` / `Fatigued` / `MissingBodyPart` 到代码修改建议，最好有结构化 repair hint，而不仅是自然语言 explanation。

建议：
- 新增 MCP resource：`swarm://playbooks/first-hour-agent`，包含分阶段目标、策略伪代码、常见 rejection repair table。
- 新增 MCP resource：`swarm://examples/strategy-patterns`，覆盖 harvest loop、spawn scaling、tower defense、kite、retreat、claim。
- `swarm_explain_last_tick` 增加 machine-readable `repair_hints[]`，字段包括 `symptom`, `likely_code_area`, `suggested_patch_pattern`, `confidence`。
- 将 AI onboarding 验收从“完成一次改进循环”提升为“在 tutorial world 达成首个 PvE kill 或 resource target”。

### G3 — Medium — Replay/旁观是传播核心，但目前被分散为功能点和 RFC

对编程竞技游戏来说，replay 不只是调试工具，而是社区传播的主内容载体。现在设计具备 Replay、观战、解说覆盖层、战报卡 RFC，但没有把它们提升为核心产品循环。

风险：
- World 默认 `public_spectate=false` 合理，但可能导致早期社区没有足够“可看内容”。
- Arena 赛后 replay 公开，但如果分享 URL、highlight card、自动摘要仍是 RFC，传播闭环会晚于核心玩法上线。
- Replay viewer 支持速度控制、视角切换、指令展开，但缺少“代码 diff / strategy version / metric overlay”的编程游戏特有看点。

建议：
- 将 Arena replay sharing 从 RFC 提升为核心 MVP：至少包含 share URL、preview card、关键 tick 自动摘要。
- 每次 Arena / PvE Challenge 结束生成 **Strategy Report**：代码版本、胜负关键 tick、资源曲线、最高价值指令、常见 rejected commands。
- Replay 页面支持“复制此 bot 的公开 starter fork”或“挑战这个 replay 的胜者策略”。
- 为 World 模式提供 opt-in “公开战报”，不公开全量情报，只公开经过 fog/privacy 处理的 safe highlight。

### G4 — Medium — 长期追求列出了目标，但缺少可组合的 aspirational ladder

文档列出的长期目标包括殖民地年龄、GCL、RCL、Arena 段位、PvE 里程碑、Replay/观战声誉。方向正确，但目前像并列清单，缺少玩家能理解并选择的“身份路线”。

风险：
- World 无排行榜是对公平性的正确判断，但如果没有替代荣誉结构，老玩家缺少社会展示，新玩家缺少可追赶目标。
- GCL/RCL 容易变成单一扩张指标；文档虽然提出反雪球，但还没给非扩张型玩家足够长期追求。
- PvE 蓝图、外交、contracts、人格系统都很有潜力，但没有被串成职业/身份系统。

建议：
- 定义 4-6 条长期身份路线：Engineer（效率优化）、Warlord（Arena/PvP）、Explorer（遗迹/地图发现）、Merchant（contracts/物流）、Modder（世界规则）、Mentor（starter/replay 教学）。
- 每条路线有独立 progression、徽章、公开主页展示，不直接转化为战力。
- 将 Replay/观战声誉产品化：best replay、most forked bot、most improved strategy、best tutorial bot。
- 增加 “Bot Lineage”：公开策略可以 fork，保留作者链与版本树，形成 GitHub-like 社区荣誉。

### G5 — Medium — 可配置世界很强，但新玩家可能被规则复杂度压垮

Swarm 的规则可配置性是长期生态优势，但对第一批玩家和 AI agent 来说，动态资源、动态 body part、动态 action、MOD 世界、不同 SDK hash 都会增加认知负荷。

已有缓解：
- Vanilla Ruleset 固定默认值
- MOD 世界标识
- SDK manifest hash
- 世界规则可见性与 i18n

仍需补强：
- 世界列表需要明确的 difficulty / complexity 标签，而不仅是 `[MOD]`。
- 新玩家应默认只进入 Vanilla Tutorial / Novice，不应在 onboarding 中遇到自定义 action。
- AI agent 需要可机器读取的 complexity summary：该世界相比 Vanilla 新增了哪些规则、哪些 starter bot 仍可用、哪些策略范式失效。

建议：
- 世界入口增加 `complexity_level`: Tutorial / Novice / Standard / Advanced / Experimental。
- MCP `swarm_get_world_rules` 返回 `vanilla_diff_summary` 和 `recommended_starter_bots`。
- Web UI 以“规则差异摘要”而不是完整 TOML 作为默认展示：例如“本世界新增 Crystal/Gas，禁用 Hack，启用 heavy logistics”。

### G6 — Low — Drone 人格系统有情感价值，但目前与玩家记忆连接不足

人格不影响 gameplay 是正确选择，避免 roll 优势。但人格如果只影响动画，会很快变成背景噪声。编程游戏的情感连接来自“这个 drone 曾经做过什么”，而不只是它的性格参数。

建议：
- 给 drone 增加纯表现型 history tags：First Harvester、Survived Invasion、Killed Guardian、Built First Tower。
- Replay 中高亮有历史的 drone，形成可讲述的微故事。
- 允许玩家给重要 drone 命名或 pin 到 colony log，但不改变战斗数值。

## Missing

1. **First-Hour Questline**
   - 现在有 Golden Path 和 soft_launch，但缺少一条 UI 明确驱动的 60 分钟任务线。

2. **AI Strategy Playbooks**
   - MCP resources 需要不只是 API/schema/docs，还需要“如何玩”的策略手册、修复表、分阶段 bot 模板。

3. **Replay Sharing MVP**
   - 分享 URL、战报卡、自动摘要不应长期停留 RFC。它们是社区增长核心，不只是 nice-to-have。

4. **Public Player/Bot Profile**
   - 缺少玩家与 bot 的公开主页：策略版本、replay、成就、fork lineage、Arena/PvE 记录。

5. **Non-Power Progression**
   - 除 GCL/RCL/room count 外，需要非战力、非资产型长期成就，避免持久世界只奖励扩张。

6. **World Complexity UX**
   - 可配置规则需要面向人类和 AI 的 complexity summary、Vanilla diff、推荐 starter bot。

7. **Community Challenge Loop**
   - 有 Arena challenge 和 contracts 的点子，但缺少“创建挑战 → 分享 → fork 策略 → 再挑战”的闭环。

## Fresh Ideas

1. **Bot Lineage / Strategy Fork Graph**
   - 公开 bot 可以被 fork，保留版本树、作者链、胜率变化、关键 replay。
   - 这会把 Swarm 从“写代码打游戏”扩展为“策略代码社区”。

2. **One-Click Rematch From Replay**
   - 每个 replay 页面提供“用我的 bot 挑战这个状态/地图/对手”的按钮。
   - Arena 的可复现 map_seed 与 locked WASM 非常适合做 rematch culture。

3. **First Victory Card**
   - 玩家首次 PvE kill、首次防守成功、首次 Arena 胜利自动生成可分享卡片：bot 名、关键指标、replay 链接、代码语言。
   - 这能把首小时成就变成传播资产。

4. **Agent Mentor Mode**
   - AI agent 不只参赛，也可以作为导师读取 replay 与 explanation，给人类玩家生成“下一步改进建议”。
   - 这符合 Swarm 的 AI 原生定位，也能降低编程门槛。

5. **Daily Micro-Challenges**
   - 每日固定 seed 的 100-500 tick PvE puzzle：最少 tick、最低 fuel、最少 drone、最高资源效率。
   - 短内容适合分享，且不会影响 World 经济。

6. **Fog-of-War Replay Toggle as Spectator Drama**
   - Replay 默认展示双方实际视野，可一键切换全知视角。
   - 观众先看“玩家当时知道什么”，再看真相，会产生更强的解说张力。

7. **Colony Chronicle**
   - 每个 World colony 自动生成时间线：首次 spawn、首次 tower、首次 NPC wave、首次 alliance、首次被攻击、首次 claim。
   - 它是非排行榜式的长期身份展示，也能降低老玩家和新玩家之间的比较焦虑。

8. **Rule Diff Cards for MOD Worlds**
   - 每个 MOD 世界自动生成三张卡：新增资源、改变的动作、失效的 Vanilla 假设。
   - 人类读卡理解，AI 通过同一结构生成策略迁移计划。

## CrossCheck — 需要跨方向检查

- CX1: MCP resources 是否足以让 AI agent 从零完成“获取 SDK → 编译 WASM → 部署 → 调试 → PvE kill”的完整闭环，目前仍缺少 playbook/repair hints 层 → 建议 Architect 检查 MCP resource taxonomy、schema 生成链路、事件订阅与 `swarm_explain_last_tick` 的结构化输出是否支持该闭环。

- CX2: Replay/观战分享如果提升为 MVP 核心，会增加 TickTrace、隐私过滤、spectate_delay、safe highlight 的边界复杂度 → 建议 Security 检查 replay privacy、fog-of-war 泄漏、Arena 赛中旁观延迟、World safe view 的信息脱敏规则。

- CX3: World Action Manifest 动态生成 SDK 与 MCP schema 的设计对 AI 可学性很关键；如果 manifest diff 不稳定或过大，AI agent 可能无法快速适配 MOD 世界 → 建议 Architect 检查 manifest canonical hash、Vanilla diff、SDK cache、MCP `swarm_get_world_rules` 输出的一致性与可压缩摘要。

- CX4: Public bot profile、bot fork graph、replay sharing 会引入用户生成内容、代码公开/私有边界和归属问题 → 建议 Security 检查公开 WASM/源码、作者链、防恶意 replay metadata、profile 滥用与举报机制。

- CX5: Contracts、外交、player-to-player transfer、Market RFC 与长期社区身份路线强相关，但也最容易变成刷号/小号经济入口 → 建议 Security 检查 new player resource gate、same-origin quota、contract 押金、alliance transfer 的滥用面。

## 总结

R14 的设计已经具备“能运行、能调试、能公平对待 AI 与人类、能支撑持久世界和竞技场”的强基础。我建议 CONDITIONAL_APPROVE：保留当前技术与规则方向，但在冻结前补齐三类产品设计合同：

1. **First-Hour Retention Contract**：明确 60 分钟任务线、情绪峰值、可分享首胜成果。
2. **AI Learnability Contract**：MCP resources 必须包含 playbooks、examples、repair hints，不止 schema/reference。
3. **Community Propagation Contract**：Arena replay 分享、战报卡、bot profile/fork lineage 至少定义 MVP 版本。

如果这些补齐，Swarm 不只是 Screeps 的现代重构，而会更像一个“可编程策略生态 + AI 原生竞技社区”。
