# R9 终审 — rev-gpt-designer

Reviewer: GPT-5.5 / Game Designer
Scope: `/data/swarm/docs/design/DESIGN.md`, `/data/swarm/docs/design/tech-choices.md`, `/data/swarm/docs/specs/p0/`
Date: 2026-06-14

## Verdict

APPROVE_WITH_RESERVATIONS

R9 已经达到“可以进入 Phase 1 实现”的设计成熟度。核心产品承诺是成立的：Swarm 不是普通 RTS，而是“代码即军队”的可编程持久世界；AI 与人类共享同一 WASM 路径；MCP 是 AI 的屏幕、鼠标、文档和调试台，而不是后门控制器；tick、visibility、replay、command validation、source gate、IDL、Rhai rules 都已经形成了一个相当完整的设计闭环。

从游戏设计角度，R9 最大进步是：它不再只是在证明“能安全运行玩家 WASM”，而是在证明“玩家可以学习、行动、理解、复盘、传播”。P0-6 的反馈循环、P0-5 的 replay/spectator 边界、P0-8 的 IDL 单一真相、P0-9 的 source model，都直接服务于可玩性与社区信任。

但我仍不建议无条件 APPROVE。当前阻断点已经不是“架构是否可行”，而是“第一个小时是否被做成一个可验收的游戏体验”。R9 文档有教程、starter bot、MCP resources、tick explanation、replay viewer，但它们仍偏功能规格，而不是一个被锁定的 first-hour golden path。长期追求也仍偏 GCL/RCL/房间/竞技排名，缺少 bot identity、achievement、replay highlight、social graph 这类能驱动社区传播和日常留存的产品层。

最终建议：允许 Phase 1 启动，但把 G1 项作为 Phase 1/2 gate。不要等核心引擎写完后再补 onboarding、MCP corpus 和 replay metadata；这些东西会反过来决定 API、数据结构和调试事件的形状。

## Strengths

1. 核心 fantasy 强，且与技术方案一致

“你的代码就是你的军队。Write once, fight forever.” 是一个真正可传播的产品钩子。WASM 多语言、fuel metering、deterministic replay、ECS、可配置世界规则都不是孤立技术点，而是在共同服务这个 fantasy：玩家写的程序在一个持久世界中持续行动、竞争、演化。

2. AI / human fairness 终于锁死在正确位置

DESIGN、P0-1、P0-3、P0-9 多次明确：唯一 gameplay executor 是 WasmSandboxExecutor；MCP 不提供 `swarm_move` / `swarm_attack` / `swarm_build`；AI 必须和人类一样写 WASM、部署 WASM、等待 tick 生效。这个决定非常关键。它避免了两个社区都会敏感的问题：人类不会觉得 AI 有后门，AI 玩家也可以通过同一套公开资源学习游戏。

3. “可编程游戏最难的 UX”被提前纳入核心规格

P0-6 把 LEARN → DECIDE → ACT → UNDERSTAND 做成 MVP feedback loop，这是正确的产品结构。`swarm_explain_last_tick`、rejection detail、why idle、strategy metrics、starter bots、本地模拟，都在解决同一个核心问题：玩家不是不愿意调试，而是需要知道“我的代码为什么没产生效果”。

4. Replay / spectator 不只是技术审计，也有产品潜力

P0-5 已经把 drone snapshot、公平视野、player view、spectator delay、replay privacy、Arena public replay 分开建模。尤其是 spectator 不能看到代码、env_vars、debug info、指令列表，这为公开观战和社区分享提供了安全边界。Arena 赛后公开 replay 的方向也非常适合传播。

5. World Rules Engine 给长期生态留下空间

Rhai mod、world.toml、资源类型、伤害类型、物流模式、规则 i18n、`swarm_get_world_rules` 共同把 Swarm 从“一个固定规则游戏”提升为“可编程游戏服务器平台”。这对社区服主、AI benchmark、教学世界、PvE 世界、硬核物流世界都很有价值。

6. IDL 单一真相是优秀的 AI-player 设计

P0-8 把 host functions、Command、Validator、SDK、MCP schema、docs、tests 绑定到 `game_api.idl`。这不仅是工程正确性，也直接影响 AI 玩家能否通过 MCP resources 学会游戏：schema、docs、SDK、validator 如果来自同一源，AI agent 遇到的世界会更一致、更可推理。

7. World / Arena 双模式定位清晰

DESIGN §10 和 P0-6 对 World 与 Arena 的差异说得足够清楚：World 是有机、持久、不完全公平；Arena 是公平、短局、可观战、可排名。这比强行让一个模式同时承担沙盒和电竞要健康。

## Concerns

### G1 — First-hour golden path 仍未冻结

Severity: G1 / Must fix before Phase 1 public playtest

P0-6 有教程房间、starter bot、MCP 教程、本地模拟、tick explanation，但它仍像功能列表，不像一个可验收的“第一个小时剧本”。对这类游戏来说，第一小时不是附属 UX，而是核心玩法的一部分。

当前仍缺少明确答案：

- 新玩家第 0-2 分钟是否已经看到 drone 在动？
- 第一次 meaningful edit 是什么：spawn 数量、body composition、target selection、还是建造 Tower？
- 第一次失败是否被系统主动解释？
- 第一次修复是否能在 1-2 个 tick 内看到效果？
- 第 30-60 分钟的第一个“我赢了/我变强了”目标是什么？
- AI agent 的等价第一小时是什么？是否能只靠 MCP resources 完成？

Recommendation:
新增或补强 `specs/p0/10-first-hour-experience.md`，定义 Human 与 AI 两条 golden path，并给出验收指标：

- time-to-first-drone-moving ≤ 2 分钟
- time-to-first-successful-deploy ≤ 10 分钟
- time-to-first-visible-code-impact ≤ 15 分钟
- time-to-first-debug-fix ≤ 25 分钟
- tutorial completion rate
- first deploy success rate
- first 100 tick rejection recovery rate

### G1 — MCP resources 还没有内容质量合同

Severity: G1 / Must fix before MCP public alpha

R9 列出了 `swarm_get_docs`、`swarm_get_schema`、`swarm_get_available_actions`、`swarm_get_world_rules`、`swarm://docs/tutorials/basic-agent`，但没有冻结它们的最小内容结构和测试标准。

AI 玩家“能不能仅通过 MCP resources 学会怎么玩”不取决于工具名是否存在，而取决于 resources 是否包含：

- chunked + versioned docs，而不是一次 dump 全部文档；
- snapshot → decision → code 的 worked examples；
- 可直接编译的 starter bot；
- 当前世界规则与 standard rules 的 diff；
- `validate_module` 的 compiler-style diagnostics；
- `explain_last_tick` 的 fix-oriented hints；
- `available_actions` 是否基于当前 snapshot 生成 affordances，而不只是 API 列表。

Recommendation:
增加 MCP learning golden test：一个无先验 agent 只调用 MCP resources，不访问外部网页、不读源码，在 tutorial world 中必须能部署 basic-harvester、采集资源，并用 `swarm_explain_last_tick` 修复至少一个失败。这个测试应成为 MCP alpha gate。

### G1 — “任意语言 → WASM”的长期优势可能伤害第一步体验

Severity: G1 / Must fix before broad onboarding

多语言 WASM 是 Swarm 的核心差异化，但第一小时不应该要求玩家理解 WASI、wasm-pack、Rust target、AssemblyScript、TinyGo 或 ABI。P0-6 说 starter bot 必须开箱即编译/运行，但还没有明确零本地工具链路径。

Recommendation:
Phase 1 至少保证一条黄金路径：

- Web UI 内置 TypeScript starter，点击 Deploy 即可 server-side compile + deploy；
- CLI `swarm deploy ./basic-harvester` 自动使用 pinned toolchain 或远程 build sandbox；
- MCP 侧提供 template/source-level build path，或清楚说明 AI 需要上传 WASM bytes；
- validate/build diagnostics 必须可被人类和 AI 直接修复。

如果第一步是工具链地狱，后面的 replay、Arena、mod 都很难被玩家看到。

### G1 — `player_view = full` 对 AI/MCP 的公平边界仍需硬限制

Severity: G1 / Must fix before any public PvP world

P0-5 明确：无论 player_view 如何，WASM `tick()` snapshot 始终按 `is_visible_to` 过滤；但 `player_view = full` 时，玩家屏幕 / MCP 可以看全图。对教学世界没问题；对 PvP/ranked world，AI agent 可以通过 MCP full view 看全图，再把情报编码进下一版 WASM 策略，间接突破 fog-of-war。

文档已有部分约束，但还应更硬：

- `player_view = full` 只能用于 tutorial、sandbox、admin、non-competitive worlds；
- ranked Arena 禁用；
- public PvP World 若启用则必须标记为 non-fair / unranked；
- MCP `swarm_get_snapshot` 与 WASM snapshot 的差异必须在响应中显式标注。

Recommendation:
把这条写进 P0-5/P0-7 的配置校验：`pvp_enabled && ranked/public_leaderboard` 时拒绝 `player_view=full`，除非 world explicitly `competitive=false`。

### G2 — 长期追求仍偏领地/数值，缺少 bot identity 与社会资本

Severity: G2 / Should fix before Phase 4 retention push

当前长期追求主要是 GCL、Controller level、房间数、Arena league、锦标赛、mod 世界。它们能吸引硬核玩家，但还不够支撑社区传播。

玩家真正会分享的不是“我有一个 RCL 5 房间”，而是：

- “这是我的 bot，它的策略很酷”；
- “这是 v13，相比 v12 fuel 降了 18%”；
- “这场 replay 里我的 bot 反杀了 rush”；
- “我做了一个 beginner-friendly mod world”；
- “我的 bot 连续 1000 tick 零 rejection”。

Recommendation:
路线图中预留 bot profile / strategy profile：bot 名称、作者、语言、版本、部署历史、公开指标、replay 列表、achievements、fork lineage、strategy tags。

### G2 — Replay 已有安全边界，但还不是传播产品

Severity: G2 / Should fix before Arena launch

P0-6 提到回放查看器、safe view URL、解说覆盖层；P0-5 有 replay privacy。但传播所需的 metadata/schema 还不够具体。

Recommendation:
新增 Replay Share Metadata Schema：

- title / description
- participants / bot_name / language / bot_version
- world_id / match_id / map_seed / ruleset_hash
- result / win condition / duration_ticks
- key_events: first_spawn, first_tower, first_kill, spawn_destroyed, resource_swing
- thumbnail_frame / minimap_snapshot
- public_safe_summary
- share_permissions
- fog_view_modes: A_view / B_view / omniscient

没有这些，replay viewer 更像调试工具，而不是社区增长工具。

### G2 — `swarm_dry_run_commands` 命名容易破坏“不能直接提交指令”的心智模型

Severity: G2 / UX wording risk

P0-6 说 `swarm_dry_run_commands` 用于“如果我提交这些指令，会成功吗？”，但设计核心又反复强调玩家不能直接提交 gameplay commands，只能部署 WASM。虽然 dry-run 是 snapshot-bound non-authoritative，但这个命名会让新手和 AI agent 误以为存在 command submission API。

Recommendation:
改名为更贴近 deferred model 的名字：

- `swarm_validate_tick_output`
- `swarm_dry_run_tick_output`
- `swarm_simulate_module_tick`

并在 docs 中明确：它验证的是“某个 WASM tick output 在某个 snapshot 下会不会通过 validator”，不是 gameplay action endpoint。

### G2 — World Rules Engine 的可变性需要 newbie-safe summary

Severity: G2 / Onboarding complexity

“每个世界规则不同”是长期优势，但新手和 AI agent 都可能被规则差异压垮。R9 已有 i18n、world rules 查询、mod config，但缺少一个进入世界前的低认知负担摘要。

Recommendation:
给每个 world 生成机器可读 badge：

- complexity: beginner / standard / expert
- archetype: standard-swarm / logistics-heavy / arena / pve / modded
- competitive: true/false
- rules_diff_from_standard
- recommended_starter_bots
- estimated_first_goal
- spectator/replay policy

人类 UI 和 MCP 都应先展示这个摘要，再展示完整 TOML/mod config。

### G2 — World 与 Arena 的产品顺序需要更强约束

Severity: G2 / Product sequencing risk

文档已经说 Arena 在 Phase 6，但 DESIGN 与 P0 文档中 Arena 内容较多，容易让实现团队过早分散注意力。World 和 Arena 需要不同的 onboarding、matchmaking、replay、ranking、balance 工具。早期两个都做半成品，会稀释体验。

Recommendation:
Phase 1-3 明确只承诺 Tutorial/Solo World → small Persistent World shard。Arena 的数据结构可以预留，但不作为 public promise。等 replay、spectator、league、match rules、locked deployment 都成熟后再公开 Arena。

### G2 — `get_available_actions` 的产品语义需要更明确

Severity: G2 / AI learning quality risk

P0-3/P0-6 提到 `swarm_get_available_actions`，但它可以有两种完全不同的含义：

1. API reference level：当前世界支持哪些 command/function；
2. Situation affordance level：基于当前 snapshot，我的这些实体现在能做哪些事，失败风险是什么。

对 AI 玩家和新手，第二种价值大很多。只给 API 列表并不能回答“我下一步该做什么”。

Recommendation:
定义分层响应：

- `api_actions`: 世界规则允许的动作；
- `entity_affordances`: 每个自身实体当前可行动作；
- `blocked_actions`: 为什么不能做；
- `suggested_next_goals`: tutorial/standard bot 下的建议目标；
- docs links。

### G3 — 文档状态与章节编号仍有清理项

Severity: G3 / Documentation cleanup

DESIGN §9 说 Phase 0 Architecture Freeze 完成，但部分 P0 文档 frontmatter 仍写 “Phase 2 阻断项” 或 “Phase 1 设计基础”。DESIGN §11 下还有 `### 10.2 代码规范` 编号错误。

Recommendation:
统一每个 P0 spec 的 frontmatter：`status`、`phase_gate`、`owner`、`last_reviewed`、`frozen_since`。同时跑一次 docs lint 修正章节编号。

### G3 — Command JSON 示例术语仍需 lint

Severity: G3 / Polish before codegen

文档中仍有一些 `cmd` vs `action.type`、`Energy` vs dynamic resource、`InsufficientEnergy` vs `InsufficientResource`、`host_get_world_rules` 是否在允许 host function 表中一致等小差异。这些不影响 R9 方向，但会影响 IDL/codegen/SDK/docs 一致性。

Recommendation:
在 API freeze 后做 terminology lint：IDL、P0-2 validator、P0-4 host functions、DESIGN 示例、TS SDK 示例必须统一。

## Missing

1. First-hour acceptance spec

需要 Human 与 AI 两条可执行 golden path：从新账号/新 agent 到首次部署、首次可见影响、首次失败解释、首次修复、首次小目标完成。

2. MCP resource corpus spec

需要冻结 docs/resources 的格式、chunking、版本、locale、starter code、worked examples、diagnostics schema、golden tests。

3. Zero-toolchain onboarding path

需要至少一条 TS starter 的 browser/server-side compile + deploy 路径。任意语言可以是长期目标，第一小时必须有一键成功路径。

4. Bot / strategy public identity

需要 bot profile、version history、strategy card、公开指标、replay 列表、achievement、fork lineage。

5. Replay share schema

需要 key events、thumbnail、share card、participants、ruleset hash、safe summary、fog view modes。

6. World preset / rule diff badge

需要 Tutorial、Standard World、Logistics Light、Hardcore Logistics、PvE Sandbox、Arena 等 preset，以及每个世界相对 standard 的差异摘要。

7. RejectionReason UX copy table

需要 RejectionReason → human explanation → AI hint → likely fix → docs link 的表。P0-2 有机器 detail，P0-6 有示例，但还不是完整 copy contract。

8. Competitive fairness config validation

需要对 `player_view=full`、public spectate、replay privacy、ranked/PvP 的组合做硬校验，防止服主误配导致公平性争议。

9. Progression beyond GCL/RCL

需要 achievement、efficiency medals、no-rejection streak、seasonal goals、bot reputation、mod author reputation、replay highlights 等软追求。

## Fresh Ideas

1. Bot Gym 作为第一小时主入口

在正式 World 前做 10 个小关卡：采集、搬运、spawn、修路、建 Tower、防守、修复、扩张、避敌、低 fuel 优化。每关都有目标、starter code、失败解释、replay ghost。AI agent 通过 MCP 进入同一 Gym。

2. Strategy Card

每次部署生成一张卡：bot name、version、language、WASM size、平均 fuel、指令成功率、经济曲线、常见 rejection、行为标签（harvester-heavy / rush / turtle / logistics）。可分享，也可用于版本对比。

3. Coach-style explanation

`swarm_explain_last_tick` 不只列 rejected commands，还给教练式摘要：

- 你的 drone 38% 时间 idle；
- 主要原因是 CarryFull 后没有 transfer；
- 建议生成 hauler 或把 target 改为最近 Spawn；
- 相关教程：logistics/basic-hauling。

4. Replay-to-template

公开 replay 中允许 “Fork this strategy”。如果源码不公开，也可以生成 behavior template：body composition、target priority、扩张节奏、常见状态机。这能把 replay 变成学习入口。

5. No-rejection streak 成就

连续 100 / 1000 / 10000 tick 无 rejected command 给 badge。它把工程质量转成游戏成就，非常契合可编程游戏。

6. Bot version duels

允许玩家让自己的 v12 和 v13 在 Arena sandbox 自动对打，生成 regression report：v13 资源效率 +18%，但 combat survival -7%。这对程序员玩家很有吸引力。

7. World Rule Diff Badge

进入世界前显示：Standard World + Logistics Light；Differences: code update cost Energy 500, global storage tax enabled, fog-of-war on, PvP on；Starter compatibility: basic-harvester ✅, tower-defense ✅, room-claimer ⚠️。

8. AI / Human / Hybrid league 品牌化

不要只在规则里区分，产品上直接品牌化：Human-authored WASM League、AI-authored Bot League、Hybrid/Open League。这样能减少公平争议，也能吸引不同社区。

9. Spectator fog toggle

Arena replay 默认全知，但一键切换 Player A saw / Player B saw / Omniscient。它既增强观赏性，也能教育玩家理解信息战。

10. Mod safety / beginner badge

Mod 市场除了 rating，还显示 Deterministic、No hidden info、Low CPU、Beginner friendly、PvP balanced 等徽章。AI agent 也能读取这些 badges 决定是否加入世界。

## Final Gate Recommendation

R9 可进入 Phase 1 实现，但建议新增四个 Phase 1/2 gate：

1. First-hour gate
   新人类玩家与新 AI agent 分别完成 tutorial golden path：首次成功部署 ≤ 10 分钟，首次可见代码影响 ≤ 15 分钟，首次 debug fix ≤ 25 分钟。

2. MCP learning gate
   一个无先验 agent 只依赖 MCP resources，在 tutorial world 中成功部署 basic-harvester，并用 `swarm_explain_last_tick` 修复至少一个失败。

3. Zero-toolchain gate
   Web UI 或 CLI 至少有一条 TypeScript starter 一键编译/部署路径，不要求玩家安装本地 WASM 工具链。

4. Replay/share gate
   tutorial run 或 Arena match 自动产出 safe replay metadata、key events summary、thumbnail/share card 所需字段。

如果这些 gate 被加入路线图，我的 R9 终审意见是：APPROVE_WITH_RESERVATIONS，可以开始实现。