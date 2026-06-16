# Swarm R2 设计评审 — Game Designer 视角

Reviewer: rev-gpt-designer
Task: t_e489346d / review-R2-designer-gpt
Date: 2026-06-16
Scope: `/data/swarm/docs/design/DESIGN.md`, `/data/swarm/docs/specs/05-unified-visibility-policy.md`, `/data/swarm/docs/specs/06-mvp-feedback-loop.md`, `/data/swarm/docs/specs/08-game-api-idl.md`, `/data/swarm/docs/api/mcp-tools.md`, `/data/swarm/docs/GETTING-STARTED.md`, R2 architect review, R2 designer cross-review。
Perspective: 创意构思、UX 模式、社区动力学、玩家心理学、第一小时体验、AI 玩家可学性、旁观/Replay 传播、长期追求。

## Verdict

CONDITIONAL_APPROVE

R2 版已经具备一个可实现、可解释、且有独特卖点的 programmable MMO RTS 骨架。最关键的公平性叙事已经成立：人类和 AI 都通过 WASM 玩游戏，MCP 是 screen/mouse/debugger，不是特权 action controller。World / Arena 的模式分离、可见性 / replay 的安全边界、Vanilla / Modded 的层级、drone lifespan + Controller / Depot 后勤线，都比 R1 更成熟。

但从 Game Designer 视角，我仍不建议把当前设计视为“首发体验已冻结”。现在的文档更像一个强大的系统设计，而不是一个已经被产品化的玩家旅程。第一小时、AI curriculum、Arena 运营闭环、Replay 传播包装、World 长期身份、失败恢复路径仍然需要成为首个可玩里程碑的设计合同，而不是上线后补丁。

结论：核心实现可以继续；Designer 方向的通过条件是：MVP 不只要 tick / WASM / replay 能跑，还要让新人、AI agent、观众、社区创作者在第一周内各自形成一个清晰闭环。

---

## Strengths

### S1 — “世界只认 WASM”是最强公平性和传播语句

DESIGN §1 / §4 与 MCP 工具文档已经把边界讲清楚：

- 人类：Monaco / CLI → 编译 WASM → deploy。
- AI：MCP 读世界、读 docs、生成代码 → 编译 WASM → deploy。
- MCP 明确不存在 `swarm_move` / `swarm_attack` / `swarm_build` / `swarm_spawn`。

这不仅是架构正确，也是社区心理正确。编程竞技游戏一旦出现“AI 玩家是不是有特权”的疑虑，社区信任会很难修复。Swarm 的答案很干净：世界不关心作者是谁，只看 WASM 输出。

推荐把这句话提升为官网和教程第一屏：

> Human or AI, the world only sees your code.

### S2 — Drone lifespan + Depot 后勤线有真正的差异化玩法潜力

Swarm 不应该只被定位成 “Screeps but WASM”。R2 中的 age、Controller 维修、Forward Depot、补给线、可摧毁后勤节点，把它推向了一个更独特的方向：代码驱动的后勤战争。

这套系统的设计价值很高：

- 进攻不是只堆 combat drone，而是维护远征生命线。
- 防守不是只建 Tower，而是切断敌方 Depot / Carry 补给。
- 优秀代码不只是路径优化，也是生命周期、维修窗口、资源流与前线节奏优化。

Vanilla 的设计宣言可以是：

> Logistics under code constraints.

这比一开始展示 8 种特殊攻击更容易形成核心认知。

### S3 — LEARN → DECIDE → ACT → UNDERSTAND 的反馈闭环方向正确

`06-mvp-feedback-loop.md` 已经抓住 programmable game 最重要的一点：失败必须可解释。`swarm_explain_last_tick`、rejection detail + suggestion、“为什么闲置？”、strategy dashboard、本地 `swarm sim`、replay viewer 都是高价值设计。

对这类游戏而言，“失败少发生”不是目标，“失败后我知道下一步怎么修”才是目标。若 Explainability 实现质量高，Swarm 会比传统 RTS 更适合长期学习和 AI-assisted play。

### S4 — 可见性 / Replay / Spectator 的安全思路已经比较成熟

`05-unified-visibility-policy.md` 的核心不变量是正确的：WASM snapshot 始终按 `is_visible_to()` 过滤，`player_view` 只影响屏幕和只读查询。旁观者只能看到物理状态，不看代码、指令、调试、策略指标。

这为四个后续产品能力打下基础：

- Arena 赛后公开 replay。
- World 延迟观战 / 热度图。
- 安全的社区分享。
- AI-readable replay digest。

需要注意的是 specs/05 后文仍有示例和默认值上的不一致，见 G8。

### S5 — Vanilla / Layer 1-3 分层比 R1 更接近“游戏 + 平台”的正确形态

R2 已经把 Vanilla Ruleset、Core / Declarative / Experimental、world-specific SDK、`[MOD]` 标记、官方排名隔离写进文档。这能避免“平台化野心”吞掉第一小时体验。

这个方向应继续推进：Swarm 可以是一个平台，但新玩家第一次进入时必须感到自己在玩一个具体游戏，而不是在读一套可配置引擎。

---

## Concerns

### G1 — High — 第一小时仍是功能流程，不是情绪 / 认知曲线

`06-mvp-feedback-loop.md` 已有 5 分钟教程、starter bot、MCP 教程、本地 sim、解释器和 replay viewer。但它仍更像功能清单：玩家打开、改代码、部署、调试。缺少一条按分钟设计的情绪曲线。

当前缺口：

- 第一次成功：玩家第几分钟看到什么，产生“我做到了”的感觉？
- 第一次失败：最先遇到的失败是 OutOfRange、Fatigued、MissingBodyPart，还是路径拥堵？系统如何引导修复？
- 第一次比较：玩家如何知道 Bot A 比 Bot B 好？energy/tick、idle ticks、rejection rate 如何呈现？
- 第一次理解：核心 mental model 是采集闭环、维修闭环、防守闭环，还是 replay 调试闭环？
- 第一次社交动作：第一小时内分享 replay、挑战 bot、加入 novice league，哪个发生？

建议新增 `first-hour-journey.md`：

1. 0-2 min：看到 Spawn + starter bot 自动运行，不写代码也能理解 tick。
2. 2-5 min：改一个安全参数，例如 spawn_count，立即看到 drone 数量变化。
3. 5-12 min：系统故意制造一个简单 bug，玩家用 explain 修复。
4. 12-25 min：运行本地 sim，对比两个策略的 energy/tick 和 rejection rate。
5. 25-40 min：进入 Novice World，仅启用 Energy + Spawn + Extension + Tower。
6. 40-60 min：完成可分享里程碑：RCL2、挡住 scripted raid、或发布 replay card。

### G2 — High — AI “仅通过 MCP resources 学会玩”还缺少可判定课程图

MCP 工具方向正确：`swarm_get_docs`、`swarm_get_schema`、`swarm_get_available_actions`、`swarm_validate_module`、`swarm_deploy`、`swarm_explain_last_tick`、`swarm_simulate`。AI agent 理论上能读文档、写 WASM、部署和调试。

但“能读 API 文档”不等于“能学会玩”。AI 玩家需要 machine-readable curriculum：目标、输入资源、预期输出、成功检查器、评分指标、下一课。

建议新增 MCP resource graph：

```text
swarm://tutorials/basic-agent/lesson/01-harvest
  objective: harvest 100 Energy within 200 ticks
  allowed_docs: core_api, body_parts_basic, command_harvest_transfer
  starter_module: basic-harvester.ts
  success_check: swarm_check_objective
  metrics: energy_collected, rejection_rate, idle_ticks

swarm://tutorials/basic-agent/lesson/02-fix-out-of-range
  objective: reduce OutOfRange rejections to 0 for 100 ticks

swarm://tutorials/basic-agent/lesson/03-sim-compare
  objective: compare two pathing strategies in local simulation

swarm://tutorials/basic-agent/lesson/04-tower-defense
  objective: survive scripted raid
```

`swarm_check_objective` 是只读教程检查，不是 gameplay command，不破坏公平性。没有这层，AI agent 仍可能接入成功但学习成本过高。

### G3 — High — Progressive Reveal 尚未落地为产品入口

设计文档有 Tutorial / World / Arena / Modded / Tournament，但玩家入口如果只呈现这些技术模式，新人仍会困惑。新玩家不应该先回答“World 还是 Arena”，而应该回答“今天想做什么”。

建议产品导航改成四条路径：

- Learn：教程、课程、starter bot、novice objectives。
- Build：持久 World、殖民地、后勤、长期身份。
- Compete：Arena、ranked、tournaments、公平对局。
- Watch：公开 replay、weekly highlights、延迟世界地图。

World / Arena 是底层模式；Learn / Build / Compete / Watch 是玩家动机入口。

### G4 — High — Vanilla 仍可能过宽；特殊攻击应晚于后勤 meta

R2 的 Vanilla 默认仍展示 8 种特殊攻击、6 种伤害类型、抗性、Overload/Hack/Fabricate 等高概念机制。即使它们可配置，文档呈现上仍容易让新玩家以为这些都是第一阶段必学内容。

建议拆分：

- Tutorial Vanilla：Move / Work / Carry，采集 + 运输 + Spawn。
- Novice Vanilla：Move / Work / Carry / Attack / Heal / Tough + Spawn / Extension / Tower / Storage；无特殊攻击。
- Standard Vanilla：启用 Disrupt / Fortify / Overload 三个最清晰机制。
- Advanced / Seasonal：Hack / Drain / Debilitate。
- Modded / Arena Seasonal：Leech / Fabricate。

Swarm 第一小时最该证明的是“代码驱动后勤循环好玩”，不是“特殊攻击表很丰富”。

### G5 — Medium — Arena 有比赛定义，但还不是竞技产品

`06-mvp-feedback-loop.md` 已定义 Arena：固定时长、对称初始条件、摧毁 Spawn 或分数胜、赛后 replay、league 分区。但一个可持续竞技模式还需要运营闭环：

- Quick match / ranked / custom lobby / tournament 四类入口。
- 新手保护 matchmaking，避免第一局碰冠军 bot。
- Rating / league / season reset / seasonal ruleset。
- 赛前 precommit、赛中锁定、赛后公开 replay 的明确流程。
- Human-written / AI-assisted / fully autonomous AI league 的边界。

建议新增 `arena-product-spec.md`。如果 MVP 无法包含至少 quick match + replay + basic rating，Arena 应标记为 experimental，而不是主入口。

### G6 — Medium — Replay 已经能看，但还没有“值得分享”的包装

Replay viewer、safe view URL、fog toggle、Arena public replay 都是基础设施。缺的是传播层：别人为什么点开？10 秒内能看懂什么？

建议把 replay 做成内容产品：

- Auto-highlight：first kill、spawn destroyed、resource swing、tower clutch、mass rejection bug、comeback。
- Share card：标题、双方、tick 区间、关键指标、30 秒 clip/GIF。
- Strategy diff overlay：本次部署相对上次 energy/tick +X%、rejection -Y%。
- Fog presets：what I saw / what opponent saw / omniscient。
- Replay annotations：玩家给 tick 区间加文字说明，形成攻略。
- Weekly Digest：每周自动生成 5 个高光 replay。

Swarm 这类游戏天然难旁观，系统必须替观众剪辑和讲故事。

### G7 — Medium — World 长期追求仍偏系统指标，缺少身份与非零和荣誉

DESIGN 中有 GCL、房间数、殖民地年龄、Arena 排名、锦标赛。但 World 模式不追求公平排名，更需要非零和目标，否则长期追求会被头部玩家垄断感吞掉。

建议长期追求分五类：

- Competitive：Arena rating、tournament titles、challenge bot records。
- Mastery：无 rejection 运行、energy/tick 里程碑、uptime、sim benchmark。
- Creative：公开 world preset、mod preset、starter bot、教程 replay。
- Social：mentor badges、联盟贡献、co-op event contribution。
- Identity：colony banner、colony chronicle、bot lineage、hall of fame。

尤其建议预留数据模型：

- Colony Chronicle：自动记录殖民地历史事件。
- Bot Lineage Graph：module hash / fork / strategy note / representative replay。
- Mentorship Quests：老玩家发布挑战，新玩家通关获得 badge。
- Aesthetic progression：旗帜、称号、地图装饰，不影响公平性。

### G8 — Medium — 可见性文档仍有产品信任风险：旁观示例与约束不完全一致

`05-unified-visibility-policy.md` 明确写了 World 模式 `public_spectate=true` 时 `spectate_delay >= 50`，这是正确的。但同文件 §8.5 示例仍展示：

```toml
public_spectate = false
spectate_delay = 0
```

单独看没有错，因为 public_spectate=false；但用户复制后只改 `public_spectate=true`，就会得到一个违反约束的危险配置。Architect review 也指出此处缺少 validate_config 伪代码与自动 clamp 策略。

设计建议：

- 在示例旁明确注释：World 模式开启 public_spectate 时必须设为 ≥50。
- 给出 `validate_config()` 的 error / clamp 行为。
- 在 Web admin UI 中把危险组合做成红色阻止项，而不是 warning。

这是 Game Design 问题，因为一旦实时旁观泄露导致玩家被偷袭，社区会认为游戏“不公平”，即使根因是配置错误。

### G9 — Medium — specs/08 的六边形 Direction 会破坏新手 mental model

DESIGN 和 specs/01 已经是方形房间、N/S/E/W 出口，但 specs/08 IDL 仍写：

```yaml
Direction: [Top, TopRight, BottomRight, Bottom, BottomLeft, TopLeft]
```

这不仅是技术不一致，也是 UX 风险。SDK 自动补全如果暴露六方向，新手会在第一小时直接学错地图模型。对编程游戏，类型系统就是教程的一部分；错误 enum 会污染所有 starter bot 和 AI docs。

建议立即统一为：

```yaml
Direction: [North, South, East, West]
```

或如果未来要六边形，就反向修改 DESIGN / specs/01 / terrain / pathfinding。不要两套 mental model 并存。

### G10 — Low-Medium — 失败 / 灭亡后的恢复循环仍不够情绪化

文档有 respawn_policy、新手 safe_mode、replay，但“我被打爆后还想继续吗？”仍需要更具体设计。Screeps-like 游戏的失败成本高，恢复体验必须产品化。

建议：

- 失败原因归类：经济断粮 / 路径拥堵 / 防御不足 / 被 Overload / 补给线断裂。
- Bot Autopsy：自动切出关键 tick，并给出 3 个根因。
- Ghost simulation retry：在本地复盘同一局势，测试改进代码。
- Novice rebuild grant：新手首次全灭后给一次受限重建资源。
- 保留 colony chronicle / bot lineage，降低“全部归零”的挫败感。

---

## Missing

1. `first-hour-journey.md`：按分钟定义第一小时目标、解锁、失败点、情绪曲线、分享节点。
2. `progressive-reveal-ruleset.md`：Tutorial / Novice Vanilla / Standard Vanilla / Advanced / Modded 各启用哪些规则。
3. `ai-curriculum-resources.md`：MCP resource graph、lesson schema、success checks、AI-readable hints。
4. `arena-product-spec.md`：quick match、ranked、league、season、tournament、AI-assisted 分区。
5. `community-sharing.md`：Replay auto-highlight、share card、weekly digest、annotations、public delayed map。
6. `long-term-progression.md`：GCL/RCL 之外的 identity、bot lineage、colony chronicle、mentor quests、cosmetics。
7. `failure-recovery-loop.md`：drone 死亡、房间被夺、殖民地全灭后的复盘与重入路径。
8. `vanilla-design-declaration.md`：用一句话锁定官方默认 meta，例如 “logistics under code constraints”。
9. `spectator-safety-config.md` 或 specs/05 补丁：World public spectate 的 validate_config / clamp / admin UI guard。
10. `sdk-mental-model-contract.md`：确保 IDL、starter bot、AI docs、教程文本都使用同一地图/方向/命令模型。

---

## Fresh Ideas

- Strategy Diff：每次部署后自动生成“本版本相对上版本”的行为差异、指标变化、rejection 变化。
- Bot Autopsy：失败后自动把 replay 切成 3 个根因：经济断粮、路径拥堵、战斗误判。
- Ghost Race：用自己的 bot 在同地图本地对跑 champion bot 的公开 replay，学习差距。
- Novice Safe League：7 天赛季，只允许 Energy + basic body parts + Tower，无市场、无特殊攻击。
- Colony Newspaper：每个世界每日自动生成报纸：最大扩张、最惨烈战斗、最高效 bot、最离谱 bug。
- Replay-to-Tutorial：玩家把一段 replay 标注成教学关卡，其他玩家 / AI 可挑战复现或改进。
- AI-readable Replay Digest：为 AI agent 提供结构化 replay summary，而不是只给 tick trace。
- Explain as Patch：`swarm_explain_last_tick` 不只解释失败，还生成 starter bot 的最小补丁建议，供玩家确认后应用。
- Delayed World Heatmap：公开首页只展示延迟战斗热度、扩张热度、资源交通热度，像 MMO 的“卫星云图”。
- Bot Lineage Hall：每个著名 bot 有谱系树、module hash、代表战、fork 关系和作者说明。
- Spectator Story Mode：Replay viewer 自动生成“这一战发生了什么”的 5 句旁白，降低观看门槛。
- Curriculum Badges for AI：AI agent 完成 MCP lesson 后获得可公开验证的 badge，形成 AI league 入门门槛。

---

## Designer Exit Criteria

建议 Speaker 在 R2 结束时将 Designer 方向通过条件定义为：

1. 核心实现可以继续：WASM 同路径、tick、visibility、replay、MCP 非 gameplay action 已达标。
2. 首个可玩里程碑必须包含 First Hour + Novice Vanilla + Explainability，而不是只包含完整系统的缩水版。
3. AI 玩家必须能仅通过 MCP resources 完成至少 4 课 curriculum：harvest、fix rejection、sim compare、tower defense。
4. Arena 若进入 MVP，必须至少有 quick match / replay / basic rating；否则应降级为 experimental。
5. World 若进入公开测试，必须有 delayed public map 或 weekly digest 之一解决社区冷启动。
6. Long-term identity 不必 P0 全做，但至少要预留 Bot Lineage / Colony Chronicle 的数据模型。

Final Designer Verdict: CONDITIONAL_APPROVE. R2 设计骨架通过；首发体验仍需产品化补强。
