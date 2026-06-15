# Swarm 游戏设计评审 — rev-gpt-designer

Reviewer: rev-gpt-designer
Focus: 游戏乐趣、UX 模式、社区动力学、玩家心理学、AI 可玩性
Scope:
- /data/swarm/docs/design/DESIGN.md
- /data/swarm/docs/design/tech-choices.md
- /data/swarm/docs/ROADMAP.md
- /data/swarm/docs/specs/*.md

Note: 用户指定的 `/data/swarm/docs/specs/p0/` 在当前文件树中不存在；实际 P0 规范位于 `/data/swarm/docs/specs/01-...09-....md`，本评审按现有 P0 规范文件审阅。

## Verdict: CONDITIONAL_APPROVE

Swarm 的核心幻想非常强：“你的代码就是你的军队 / Write once, fight forever”。它不是传统 RTS，也不是简单 Screeps clone，而是一个面向人类程序员和 AI agent 的可编程持久世界 + 竞技场平台。World/Arena 双模式、WASM 公平执行、MCP 作为 AI 的“屏幕和鼠标”、TickTrace/Replay/Explainability、World Rules Engine 和模组体系共同构成了一个有长期生命力的设计方向。

我给出 CONDITIONAL_APPROVE，而不是 APPROVE，原因是：

1. 设计已经解决了很多“能不能安全、公平、确定地运行”的问题；
2. P0-6 已经补上了教程、starter bot、dry run、explain last tick、replay、metrics、Arena 等关键体验闭环；
3. 但从游戏设计角度看，默认体验仍有显著的 complexity risk：DESIGN.md 和 P0 规范把 Vanilla、Advanced、Modded、Future Expansion 混在同一层级，可能导致第一个小时认知负担过高；
4. 长期追求、社区传播、玩家身份、策略分享、观看体验虽然有基础设施，但还没有产品化为足够强的社区循环。

批准条件：保留当前技术/架构方向，但在正式实现或公开测试前，必须补齐“Default Vanilla Swarm / First Hour / Community & Progression”三份玩家体验设计，把复杂系统分层投放。

---

## 发现的问题

### G1 — 默认游戏复杂度过高，缺少清晰的 Vanilla ruleset
severity: High

问题：
DESIGN.md 同时包含动态资源、多资源经济、全局/本地存储、累进税、运输拦截、RCL、drone age、Depot 后勤、特殊攻击、伤害类型/抗性、custom_actions、Rhai mods、code propagation、visibility modes、market、Arena、spectator/replay 等大量机制。每个机制单独看都有价值，但放在默认文档中会让新玩家无法判断“我第一天到底需要理解哪些规则”。

P0-6 已补上教程和 starter bot，但并未给出一个严格裁剪的 Default Vanilla Swarm 体验边界。

风险：
- 第一个小时变成阅读规则和排查失败，而不是“写一行代码，世界产生变化”的爽点。
- 玩家无法形成稳定 mental model。
- AI agent 也会被过多规则扰动，生成策略时难以聚焦。

建议：
定义 Default Vanilla Swarm v1：
- 只启用 Energy 一种资源；
- 初期只开放 Move / Work / Carry / Attack / Heal / Claim / Tough 的基础语义；
- 禁用 Hack / Drain / Overload / Debilitate / Fabricate 等特殊攻击；
- Tutorial 和 Beginner World 中隐藏或简化 global/local storage；
- RCL 只展示 1–3 的短期目标；
- Mods 只在 Advanced/Community Worlds 中启用；
- 用 UI 明确标注“Advanced rule disabled in this world”。

验收标准：新玩家在不读完整 DESIGN.md 的情况下，能在 5 分钟内理解“spawn drone → harvest → transfer → build/upgrade”。

---

### G2 — First Hour 已有组件，但缺少完整玩家旅程脚本
severity: High

问题：
P0-6 定义了 5 分钟教程、starter bot、MCP 教程、本地模拟和解释工具，这是很好的补强。但它仍偏功能清单，没有完整描述 first-hour emotional arc：玩家何时获得第一次成就感、何时第一次失败、失败如何被解释、何时毕业到 World/Arena。

建议补充 First Hour Journey：

0–2 分钟：
- OAuth 登录或本地 guest 教程；
- 自动加载 basic-harvester；
- 玩家立即看到 drone 采集并返回能量。

2–5 分钟：
- 引导改一行参数，如 `MAX_HARVESTERS = 3`；
- 一键 deploy；
- UI 展示“部署前/部署后”的能量增长对比。

5–15 分钟：
- 建第一座 Extension；
- 通过 explain_last_tick 理解一次 rejected command；
- 学会 body part 基本约束。

15–30 分钟：
- 升到 RCL2；
- 解锁 Road/Container/Extension；
- 引导建立“采集者/搬运者/建造者”的角色分工。

30–60 分钟：
- 选择进入 Beginner World、Arena puzzle 或观看公开 replay；
- 给出下一目标：更高能量效率、低 fuel 策略、第一场 Arena。

验收标准：第一个小时不是“学完规则”，而是完成 3 次可感知改进：更多采集、更少 idle、完成第一个建筑/升级。

---

### G3 — Debugging as Gameplay 方向正确，但 UX 质量 bar 需要更明确
severity: High

问题：
P0-6 的 `swarm_explain_last_tick`、“为什么闲置？”、回放查看器、策略指标仪表盘非常关键。对编程游戏来说，debugging 不是附属工具，而是核心手感。但目前规范仍主要列 API/JSON，没有定义前端和 MCP 输出的体验标准。

风险：
如果错误解释不够具体，玩家会把游戏体验理解为“我的 bot 莫名其妙不动”。

建议定义 Debug UX quality bar：
- 每个 drone 有 per-tick command timeline：planned / attempted / accepted / rejected / no-op；
- 每条 rejection 有：原因、当前位置、目标、所需条件、可执行修复建议；
- “Idle reason” 必须排序显示主因，而不是列出所有可能；
- Deploy 后自动生成 A/B metric cards：energy/tick、idle rate、rejection rate、fuel usage；
- Replay 支持选择实体并查看每 tick state diff；
- AI MCP 的 `swarm_explain_last_tick` 应返回 machine-readable suggestion，不只是自然语言。

验收标准：一个初学者看到 OutOfRange、MissingBodyPart、Fatigued、CarryFull 时，能直接知道下一次该改代码、改 body，还是改路线。

---

### G4 — AI 可玩性基础扎实，但 “仅通过 MCP resources 学会怎么玩” 还需要任务型资源
severity: Medium

问题：
MCP 设计方向正确：MCP 不提交 gameplay 指令，AI 必须写 WASM；`swarm_get_docs`、`swarm_get_schema`、`swarm_get_world_rules`、`swarm_get_available_actions`、`swarm_dry_run_commands`、`swarm_explain_last_tick` 形成了 AI 学习闭环。

不足：
AI 只拿 raw schema 和规则可能仍不够。AI agent 最需要的是 task-oriented resources：当前目标、最小可运行 bot、常见失败、当前世界策略建议。

建议新增或规范化 MCP resources：
- `swarm://tutorial/current-step`
- `swarm://examples/basic-harvester-ts`
- `swarm://examples/basic-harvester-rust`
- `swarm://objectives/current-world`
- `swarm://failures/common-rejections`
- `swarm://strategy/vanilla-opening`
- `swarm_explain_next_best_action` 或等价只读诊断：不替玩家执行，只解释可选方向。

验收标准：一个无先验上下文的 AI agent 通过 MCP docs/resources 可以完成：部署 starter bot → 修复一次 rejection → 提升 energy/tick → 进入 Arena dry run。

---

### G5 — 长期追求仍偏系统指标，缺少玩家身份与荣誉结构
severity: Medium

问题：
已有 GCL/RCL、房间数、Arena ladder、tournament、modded worlds、market、Replay，但长期动机还没有被组织成玩家看得见的 aspiration map。

仅靠 RCL/GCL 会产生 Screeps 式“越滚越大”的老玩家优势；仅靠 Arena ELO 又会让 World 的情感资产弱化。

建议加入长期追求体系：

Competitive：
- Arena rating / bot ELO / seasonal leagues；
- AI-only、Human-authored、AI-assisted 分榜；
- Weekly challenge maps。

Mastery：
- fuel efficiency records；
- fastest RCL2/RCL3；
- lowest-code-size bot；
- puzzle worlds with deterministic seeds。

Creative：
- published strategy modules；
- public bot templates；
- mod/world author reputation；
- annotated replay tutorials。

Social：
- alliances；
- team arenas；
- spectator commentary；
- “fork this bot” lineage graph。

Identity / Collection：
- profile page；
- public replay portfolio；
- trophies/badges；
- cosmetic-only drone skins in spectator view。

验收标准：玩家即使不扩更多房间，也有可追求的荣誉、作品、排名、社交身份。

---

### G6 — Spectator / Replay 已有技术设计，但社区传播产品还不够强
severity: Medium

问题：
P0-5/P0-6 已定义 spectator view、replay privacy、Arena 赛后公开 replay、回放查看器、观战解说。这是亮点。但还需要明确“如何传播”。

建议把 Replay 视为社区内容核心，而不仅是 debugging 工具：
- 每场 Arena 自动生成 match page；
- 时间线 bookmarks：first contact、first kill、base breach、turning point；
- Post-match stat cards：energy curve、unit count、fuel efficiency、rejection spikes；
- 一键导出 GIF/短视频；
- 可分享 fog-of-war toggle 链接；
- replay annotations，可作为教学文章嵌入；
- weekly highlights：最佳战斗、最离谱 bug、最高效率 bot、最佳 mod world。

验收标准：一个精彩 Arena match 可以像棋谱、SC2 replay 或 speedrun clip 一样被分享和讨论。

---

### G7 — World vs Arena 的入口定位需要产品化
severity: Medium

问题：
World/Arena 区分非常正确：World 是持久、有机、不公平；Arena 是对称、公平、可排名。但新玩家进入时应该如何选择仍需更明确。

建议设置四条入口：
- Learn：Tutorial World + Puzzle Arena；
- Build：Beginner Persistent World；
- Compete：Ranked Arena；
- Watch：Public Arena / Replay Browser。

并在 UI 中用一句话解释：
- World: “建立长期殖民地，不保证公平”；
- Arena: “公平对局，代码锁定，赛后公开回放”；
- Tutorial: “安全试错，100% recycle refund”；
- Community Worlds: “不同服主规则，可能非常复杂”。

验收标准：玩家不是被丢进一个总入口，而是按动机选择体验。

---

### G8 — 特殊攻击和抗性体系可能策略深，但玩家可读性弱
severity: Medium

问题：
Hack/Drain/Overload/Debilitate/Disrupt/Fortify、Kinetic/Thermal/EMP/Sonic/Corrosive/Psionic、属性抗性、特殊效果 registry 都很强，但容易变成玩家不理解的“状态效果汤”。

尤其：
- Hack 夺取后 Neutral 5 tick 再恢复 owner，直觉上更像 stun/confuse，不像永久 hack；
- Overload 攻击 fuel budget 是很有主题性的“攻击对方代码执行能力”，但必须非常清晰地展示；
- `damage_multiplier` 同时影响特殊效果成功率/效果量不够直观。

建议：
- Beginner/Vanilla 禁用特殊攻击；
- Advanced worlds 才启用；
- 每个特殊攻击必须有三段说明：用途、反制、观战表现；
- Replay/UI 中必须有状态图标、剩余 tick、来源、可反制方式；
- Hack 可以重新命名为 Jam/Disable，或明确区分 temporary hack vs permanent capture。

验收标准：玩家输给 Overload/Hack 后能从 replay 中理解“为什么输、如何反制”。

---

### G9 — 数值表很多，但缺少 balance goals 和调参假设
severity: Low

问题：
文档列出大量数值：RCL progress、drone cap、cooldown、fuel、damage、tax、lifespan、range、cost 等。这些作为设计草案可以，但应明确“initial tuning candidates”，否则实现者会误以为是最终平衡。

建议补充 balance goals：
- time to first drone；
- time to first successful harvest；
- time to first Extension；
- time to RCL2/RCL3；
- beginner bot expected idle rate；
- starter bot expected rejection rate；
- Arena target duration；
- comeback window after losing first skirmish；
- World expected expansion pace after day 1/week 1。

验收标准：调数时围绕体验目标，而不是争论单个 cost 是否“看起来合理”。

---

### G10 — 文档结构仍偏架构，玩家体验内容被埋在技术规范中
severity: Low

问题：
DESIGN.md 非常强，但它把 game design、architecture、security、rules、modding、deployment、roadmap 混在一起。作为工程总设计可以；作为玩家体验文档不够聚焦。

建议拆出或新增：
- PLAYER-EXPERIENCE.md：目标玩家、first hour、core loops、UX principles；
- VANILLA-RULESET.md：默认世界启用/禁用规则；
- COMMUNITY.md：replay、spectate、tournaments、mods、sharing；
- BALANCE-GOALS.md：调参目标与观测指标。

验收标准：设计评审可以单独审“玩家玩起来怎样”，而不是从架构中推断体验。

---

## 亮点

### S1 — 核心幻想强且一句话可传播
“你的代码就是你的军队”是非常好的产品核心。它同时吸引 Screeps veteran、自动化游戏玩家、AI agent 开发者、竞技 bot 作者和开源 mod 社区。

### S2 — AI 与人类同走 WASM 路径，公平性设计正确
MCP 是 AI 的 screen/mouse，不是 action controller。AI 不通过 `swarm_move` 等特权工具玩游戏，而是写 WASM。这一点非常关键：它让 AI 玩家成为合法玩家，而不是外挂。

### S3 — P0-6 的反馈闭环方向非常好
Learn → Decide → Act → Understand 的闭环是编程游戏成败关键。starter bot、dry run、explain last tick、idle explanation、local sim、replay viewer、metrics dashboard 都是正确的体验组件。

### S4 — Deterministic replay 是游戏信任与内容传播的基础
确定性 ECS、TickTrace、Command replay、state checksum 让调试、反作弊、观战、赛后分析、AI 训练都站得住。这不只是技术点，也是社区信任机制。

### S5 — World/Arena 双模式解决了持久性与公平性的冲突
World 不追求公平，提供情感资产和长期经营；Arena 追求公平，提供排名、赛事和公开 replay。这个分离是正确的，避免一个模式同时承担互相冲突的目标。

### S6 — World Rules Engine 有潜力形成服务器生态
Rhai mods + world.toml + dynamic resources/body/structures/actions 可以形成 Minecraft/Factorio modded server 式生态。长期看，这比单一官方规则更有生命力。

### S7 — 可见性和 spectator privacy 有成熟思路
P0-5 把 drone snapshot、公平视野、player view、spectator view、replay privacy 区分开，避免了“为了观战破坏竞技公平”的常见问题。

### S8 — 本地模拟与 Arena 对 AI 生态很友好
`swarm sim --ticks=5000 --speed=100x` 和 Arena tournament 会吸引 bot optimization 社区。对 AI agent 来说，可重复、可测量、可回放的环境比普通 MMO 更适合持续改进。

---

## Missing / 建议新增文档

1. PLAYER-EXPERIENCE.md
   - target audience
   - first-hour journey
   - core loops
   - failure/recovery UX
   - emotional beats

2. VANILLA-RULESET.md
   - Tutorial rules
   - Beginner World rules
   - Standard World rules
   - Advanced/Modded rules
   - 哪些机制默认禁用

3. COMMUNITY-LOOPS.md
   - replay sharing
   - public match pages
   - strategy publishing
   - bot lineage/forking
   - mod/world discovery
   - seasonal events

4. BALANCE-GOALS.md
   - time-to-first-action
   - time-to-first-building
   - RCL pacing
   - Arena duration
   - starter bot success metrics

5. MCP-LEARNABILITY.md
   - AI agent from zero context walkthrough
   - required MCP docs/resources
   - example prompts/resources
   - machine-readable error repair suggestions

---

## Fresh Ideas

1. Bot Lineage Graph
玩家可以 fork starter bot 或他人的 public bot template。Profile 展示 lineage：“这个 bot forked from basic-harvester, evolved through 12 versions, won Bronze Arena S1”。这会制造社区学习链条。

2. Replay-to-Tutorial
任何公开 replay 可以被作者加注释，转换成 tutorial：在 tick 1200 暂停，解释“这里我切换到 defender production，因为 scout 发现敌方 rush”。

3. Puzzle Worlds
每天/每周固定 seed 的小型挑战：1000 tick 内最高能量、最少 fuel 达成 RCL2、固定敌人 rush 下存活。适合新手、AI、竞速社区。

4. Strategy Cards
每次部署生成一张 strategy card：版本、核心指标、优劣、常见失败。可分享到社区，也可供 AI 读取比较。

5. Spectator Heatmaps
Replay 中显示交通拥堵、资源流向、死亡热区、fuel spike。Swarm 的视觉传播不一定靠单位动画，可以靠“系统行为可视化”。

6. Safe Beginner Worlds with Graduated Complexity
Beginner World 每隔阶段解锁一个概念：先 harvest/transfer，再 build/upgrade，再 defense，再 scout，再 market。复杂性分批投放。

7. AI League With Explainable Bots
AI-only tournaments 要求 bot 提交 README/strategy summary 或自动生成 explainability page，观众能理解“这个 AI 为什么强”。

8. Public Benchmarks
官方维护 benchmark suites：economy-basic、defense-rush、logistics-maze、arena-duel。玩家和 AI 都可以跑分，形成优化文化。

---

## Final Recommendation

CONDITIONAL_APPROVE。

Swarm 的技术和系统设计已经足够有野心，也具备成为现代可编程 MMO RTS / AI bot arena 的潜力。当前最重要的风险不是“系统不够深”，而是“默认体验太深”。

下一步不应继续增加机制，而应冻结 Default Vanilla Swarm、写清 First Hour、产品化 Replay/Spectator，并把 AI learnability 从“有 schema”提升到“能通过 MCP 完成任务”。做到这些后，Swarm 的设计可以进入 APPROVE。
