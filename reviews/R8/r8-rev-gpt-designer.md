# R8 终审 — rev-gpt-designer

Reviewer: GPT-5.5 / Game Designer
Scope: `/data/swarm/docs/design/DESIGN.md`, `/data/swarm/docs/design/tech-choices.md`, `/data/swarm/docs/specs/p0/`
Date: 2026-06-14

## Verdict

APPROVE_WITH_RESERVATIONS

作为“可编程 MMO RTS / Screeps 精神续作”的产品设计，R8 已经从“技术可行性草案”推进到“可以进入实现的架构冻结版本”。核心体验闭环已经成立：玩家学习规则 → 编写/生成 WASM → 部署 → tick 执行 → 解释失败原因 → 回放/调试 → 迭代。尤其是 MCP 只作为 AI 的“屏幕和鼠标”、AI 与人类都必须通过 WASM 控制世界，这一点已经被清晰锁定，避免了最危险的公平性分叉。

但我不建议无条件 APPROVE。当前设计在“第一个小时是否真的好玩”和“长期追求是否足够可见”上仍有产品风险：教程、starter bot、tick explanation、replay viewer 被列为 P0/P1，但还没有形成一个可以被验收的 first-hour script；长期目标除了 GCL、room level、Arena 排名和 mod 世界外，还缺少玩家能每天感知的 collection / prestige / social capital 层。换句话说：技术骨架已经很强，游戏的“留存钩子”和“传播钩子”还需要在 Phase 1-2 前补一层产品规格。

建议：允许进入 Phase 1 MVP 实现，但把下列 G1/G2 问题作为 Phase 1/2 gate，不要拖到 Web 客户端完成后再补。

## Strengths

1. 核心定位清楚，且有差异化

“你的代码就是你的军队。Write once, fight forever.” 是强 hook。与 Screeps 的差异不是单纯换技术栈，而是明确变成：WASM 多语言、公平 fuel metering、确定性 replay、AI-native 但不偏袒 AI、可配置世界规则。这些都能支撑社区传播。

2. AI / 人类公平性设计基本闭环

MCP 不提供 `swarm_move` / `swarm_attack` 等动作工具，AI 只能查看世界、读 docs、生成代码、部署 WASM。WASM 是唯一 gameplay executor。这个选择对社区信任非常关键：人类玩家不会觉得 AI 有“后门 API”，AI agent 也可以只靠结构化 resources 学会玩法。

3. Debug / explanation 被提前放进核心循环

P0-6 里的 `swarm_explain_last_tick`、每 tick rejection detail、为什么闲置、策略指标仪表盘，是可编程游戏能不能留住新手的关键。很多编程游戏失败不是因为规则不好，而是玩家不知道“我的代码为什么没动”。这里方向正确。

4. Spectator / replay / privacy 的边界比前几轮成熟

P0-5 区分了 drone snapshot、公平视野、玩家屏幕、旁观者延迟、公开 replay，并明确 spectator 不可见内部状态、代码、env_vars、调试信息。Arena 赛后公开 replay 也给了传播基础。

5. World Rules Engine 给了长期生态想象力

把 Swarm 定义为“引擎平台”而不是“单一规则游戏”是好方向。Rhai mod、世界规则 i18n、规则对 AI 可查询，能让社区服主创造不同节奏：硬核物流、快节奏 Arena、教学世界、PvE 世界等。

6. 技术选型支持设计承诺

Bevy `.chain()`、Wasmtime fuel、FoundationDB 原子 tick、Blake3 确定随机、IDL 单一真相，这些不是纯工程炫技，而是直接支撑 replay、反作弊、公平性、AI 学习能力和 mod 可审计性。

## Concerns

### G1 — First-hour script 仍未冻结：玩家“第一个小时好玩吗”还只能推断，不能验收

Severity: G1 / Must fix before Phase 1 public playtest

P0-6 有 5 分钟教程、starter bot、MCP 教程、本地模拟、tick explanation，但缺少一个明确的 first-hour acceptance script：

- 第 0-5 分钟：玩家看到了什么？是否已经有一个 drone 在动？
- 第 5-15 分钟：第一次 meaningful edit 是什么？改 spawn 数量、改目标选择、改 body composition，哪一个最能产生“我在控制世界”的感觉？
- 第 15-30 分钟：第一次失败是什么？系统如何解释？玩家是否能在不查外部文档的情况下修复？
- 第 30-60 分钟：第一个小目标是什么？升级 Controller？建 Tower？打败 tutorial invader？进入 Arena？

当前教程描述偏功能清单，不是体验脚本。对编程游戏来说，第一小时必须像 puzzle game 一样精心编排，否则玩家会掉进“配置工具链 / 编译 WASM / 不知道为什么没动”的坑。

Recommendation:
新增 `specs/p0/10-first-hour-experience.md` 或纳入 P0-6，定义 Human 与 AI 两条 first-hour golden path，并给出验收指标：time-to-first-drone-moving、time-to-first-code-edit-impact、time-to-first-debug-fix、tutorial completion rate、first deploy success rate。

### G1 — AI 仅靠 MCP resources 学会怎么玩：方向正确，但 resources 内容契约还不够具体

Severity: G1 / Must fix before MCP public alpha

文档列出了 `swarm_get_docs`、`swarm_get_schema`、`swarm_get_available_actions`、`swarm_get_world_rules`、`swarm://docs/tutorials/basic-agent`，但还没有冻结这些 resources 的最小内容质量：

- `swarm_get_docs` 返回 markdown、JSON、还是 chunked docs？
- 是否有“从 snapshot 到策略代码”的 worked example？
- 是否包含可直接编译的 TS/Rust starter bot？
- `swarm_get_available_actions` 是列出 API 函数，还是结合当前 snapshot 给出 action affordances？
- AI 如何知道“下一步最小可行目标”是什么？
- AI 生成代码失败时，validate_module 是否返回可修复的 compiler-style diagnostics？

如果只是返回完整 API reference，LLM 可能能读懂，但不能保证“仅通过 MCP resources 就能上手”。AI onboarding 需要像 API coding benchmark 一样可测。

Recommendation:
给 MCP docs/resources 增加 golden tests：一个空白 agent 只调用 MCP resources，不使用外部知识，必须能在 tutorial 世界中部署 basic-harvester，并在 N tick 内采集资源。把这个作为 MCP alpha 的验收测试。

### G1 — MVP 仍有“编译链摩擦”风险：代码就是军队，但第一步不应是工具链地狱

Severity: G1 / Must fix before broad onboarding

设计强调任意语言 → WASM，这是长期优势；但新手第一小时如果要安装 Rust/wasm-pack、AssemblyScript、TinyGo 或处理 WASI/ABI，会严重损害体验。P0-6 说 starter bot 必须开箱即编译/运行，但没有明确“零本地工具链路径”。

Recommendation:
Phase 1 就应提供至少一种 browser/server-side compile path：

- Web UI 内置 TypeScript starter，点击 Deploy 即服务端编译 WASM。
- CLI `swarm deploy ./basic-harvester` 自动拉取 pinned toolchain 或使用远程 build sandbox。
- MCP `swarm_validate_module` 对源码路径/语言也给出 compile diagnostics，或单独提供 `swarm_compile` / `swarm_build_template` 开发辅助。

不一定要支持所有语言，但必须保证 TS starter 的 first deploy 是“一键成功”。

### G2 — 长期追求还偏工程/领地，缺少可展示的个人成长与社会资本

Severity: G2 / Should fix before Phase 4 retention push

当前长期目标包括 GCL、room level、Arena league、锦标赛、mod 世界、排行榜。这些足够支撑硬核玩家，但对社区传播和中轻度开发者，仍缺少“我可以展示我是谁”的层：

- Bot identity：策略名、版本历史、徽章、签名页面。
- Achievement：首次自动采集、100% uptime、无 rejection 运行 1000 tick、最短代码挑战、最低 fuel 达成任务。
- Collection：回放 highlight、battle card、bot lineage、strategy archetype。
- Social capital：fork/star 他人的 starter bot、订阅策略作者、mod 世界推荐。

Recommendation:
把“账号 / bot profile / achievement / share page”列入产品路线，哪怕实现晚于核心引擎，也要在数据模型和 replay metadata 中预留。

### G2 — Replay 分享有基础，但还不是“传播产品”

Severity: G2 / Should fix before Arena launch

P0-5/P0-6 已有 replay privacy、赛后公开、safe view URL、解说覆盖层。但传播需要更具体的内容形态：

- 自动生成 30s highlight：关键击杀、首次破防、资源曲线反转。
- Share card：双方 bot 名、语言、版本、胜利条件、tick、地图种子、关键指标。
- Annotated replay：作者可在 tick 上加注释，社区可评论。
- “Fork this bot from replay”：看到精彩策略后能跳到源码/模板。
- Embed mode：能嵌入 blog / Discord / X card。

否则 replay viewer 只是调试工具，不是社区增长工具。

Recommendation:
新增 Replay Metadata Schema：title、participants、bot_version、language、result、key_events、public_safe_summary、thumbnail_frame、share_permissions。Arena replay 生成时自动填充。

### G2 — World vs Arena 双模式合理，但默认 MVP 重点可能分散

Severity: G2 / Product sequencing risk

设计同时推进持久 World 与公平 Arena。二者都重要，但 first MVP 如果两个都半成品，体验会模糊：

- World 的乐趣来自持久、扩张、邻居、未知、长期优化。
- Arena 的乐趣来自公平、短局、回放、排名、观赏。

P0-6 把 Arena 放到 Phase 6，但 DESIGN 和 P0-5 已经大量描述 Arena。产品叙事上需要明确 Phase 1-3 的主体验到底是什么。

Recommendation:
Phase 1-3 主打 “Solo/Tutorial World → Persistent World small shard”。Arena 可以保留协议兼容，但不要作为早期玩家承诺。等 replay、spectator、matchmaking、league 都具备后再公开 Arena。

### G2 — 可见性策略里 `player_view = full` 对 MCP 查询的产品/安全含义需要再澄清

Severity: G2 / Design consistency risk

P0-5 说 `player_view = full` 时 drone snapshot 仍按 `is_visible_to` 过滤，但玩家屏幕 / MCP 可看全图。这对教学世界和合作世界有用，但对 AI 玩家尤其敏感：如果 MCP 查询能看 full map，而 WASM snapshot 不能看，AI 可以把全图信息写入下一版 WASM 策略，间接影响 gameplay。

这在教学世界无所谓，在正式 World/Arena 会破坏信息公平。文档中有组合示例，但缺少硬性限制：哪些 world mode 可以启用 `player_view=full`？是否禁止出现在 ranked / public PvP？

Recommendation:
把 `player_view=full` 标为 non-competitive / tutorial / admin-like setting。若世界允许 PvP 或 leaderboard，则必须在 UI/MCP 中显著标记“非公平世界”，且 Arena/ranked 禁用。

### G2 — `swarm_dry_run_commands` 与“没有直接提交指令通道”的心智可能冲突

Severity: G2 / UX wording risk

P0-6 把 `swarm_dry_run_commands` 描述为“如果我提交这些指令，会成功吗？”但整个设计反复强调玩家不能直接提交 gameplay 指令，只能部署 WASM。虽然 dry-run 是 snapshot-bound non-authoritative，但新手和 AI agent 可能误解为“我可以先计划 commands，再提交 commands”。

Recommendation:
改名或文案更贴近 WASM 开发：

- `swarm_dry_run_tick_output`
- `swarm_validate_tick_output`
- `swarm_simulate_module_tick`

强调它验证的是“我的 WASM 在此 snapshot 下返回的 command list”，不是一个可执行 gameplay API。

### G2 — World Rules / Mods 很强，但新手可能被规则可变性压垮

Severity: G2 / Onboarding complexity

“每个世界规则不同”是长期生态优势，但对 AI 与人类新手都是认知负担。P0-7/P0-3 提供 `swarm_get_world_rules` 和 i18n 描述，但还缺少“规则摘要 / difficulty badge / compatibility signal”。

Recommendation:
每个世界应有机器可读 difficulty/profile：

- `complexity: beginner | standard | expert`
- `archetype: standard-swarm | logistics-heavy | arena | pve | modded`
- `rules_diff_from_standard`: 自动生成规则差异摘要
- `recommended_starter_bots`: 哪些 starter bot 可用

AI agent 和人类 UI 都应先展示摘要，而不是直接 dump 完整 TOML/mod config。

### G3 — 文档状态标记不一致，会影响实现团队判断 freeze 范围

Severity: G3 / Documentation cleanup

DESIGN §9 标记 Phase 0 Architecture Freeze 已完成；P0-2/P0-3/P0-4/P0-5/P0-8/P0-9 标为 Frozen 或 Phase 0；但 P0-1、P0-6 仍写“Phase 2 阻断项”，P0-7 写“Phase 1 设计基础”。这些状态可能是历史残留，但会让实现团队不知道哪些是已冻结合同，哪些还可改。

Recommendation:
统一 frontmatter：`status: frozen | draft | blocker`、`phase_gate: P1/P2`、`owner`、`last_reviewed`。R8 终审后冻结的内容必须明确。

### G3 — 命名和章节编号有小瑕疵

Severity: G3 / Polish

DESIGN §11 后出现 `### 10.2 代码规范`，应为 `11.2`。此外部分术语在不同文档中略有差异：`cmd` vs `action.type`、`energy` vs dynamic resource、`manual_control` 已删除但 World/Arena 默认表仍列 `manual_control=false`。这些不是玩法阻断，但会影响 IDL/codegen 一致性。

Recommendation:
在 API freeze 后跑一次 terminology lint，确保 Command JSON 示例、IDL、validator spec、SDK 示例一致。

## Missing

1. First-hour acceptance test

需要一个可执行验收：新账号/新 AI agent 从零开始，在 tutorial world 完成采集、部署、解释一次失败、修复并再次部署。没有这个，MVP “可玩”只能靠主观判断。

2. MCP resource corpus spec

需要冻结 MCP docs/resources 的内容结构、chunking、版本、locale、示例代码、可编译 starter、错误诊断格式。AI player 是否能学会游戏，取决于这些 resources 的质量，而不只是工具名存在。

3. Bot profile / public identity

玩家真正分享的不是“我有 RCL 4 房间”，而是“这是我的 bot，它会这样打”。需要 bot profile、版本 changelog、语言、作者、公开指标、replay 列表。

4. Replay share schema

已有 replay viewer 概念，但缺少 share card/highlight/commentary/thumbnail/key event schema。

5. Newbie-safe world presets

World Rules Engine 需要标准 preset：Tutorial、Standard World、Logistics Hardcore、Arena、PvE Sandbox。否则“可配置”会变成“每个世界都要先读规则书”。

6. UX copy for rejection reasons

P0-2 给了机器 detail，P0-6 给了示例 suggestion。但需要一张 RejectionReason → human copy → AI hint → docs link 的表。这是新手留存核心。

7. Long-term progression beyond GCL/RCL

需要 achievement、seasonal goals、bot reputation、mod author reputation、challenge medals、efficiency records 等软追求。

## Fresh Ideas

1. “Bot Gym” 作为第一小时核心

在正式 World 前，给玩家一个 Bot Gym：固定 10 个小关卡，每关 1 个明确目标：采集、搬运、修路、建塔、防守、修复、扩张、避敌、资源选择、低 fuel 优化。每关都有可 replay 的 ghost solution。AI agent 也通过 MCP 进入同一 Gym。

2. “Explain my bot like a coach”

`swarm_explain_last_tick` 不只解释失败，还给 coach-style summary：

- 你的 drone 40% 时间在 idle。
- 主要原因是 CarryFull 后没有 transfer target。
- 建议：给 harvester 分配最近 Spawn，或 spawn hauler。
- 相关文档：link to logistics tutorial。

这会比纯 rejection log 更能留住新手。

3. Strategy Cards

每次部署生成一张 Strategy Card：语言、代码大小、平均 fuel、指令成功率、经济曲线、常见错误、核心行为标签（harvester-heavy / rush / turtle / logistics）。玩家可以分享，也能比较版本。

4. Replay-to-template

公开 replay 中允许点击某个 bot：`Fork starter from this strategy`。不公开源码时，也可以生成“行为模板”：采集优先级、body composition、扩张节奏。这样 replay 成为学习入口，而不只是观赏。

5. “AI League / Human League / Hybrid League” 明确品牌化

P0-6 已列 league 分区。建议产品上更鲜明：

- Human-authored WASM League
- AI-authored Bot League
- Hybrid/Open League

这样公平争议会少很多，也能吸引不同社区。

6. World Rule Diff Badge

进入世界前展示：

- Standard World + Logistics Light
- Differences: code update costs Energy 500; global storage tax enabled; fog-of-war on; PvP on
- Starter compatibility: basic-harvester ✅, tower-defense ✅, room-claimer ⚠️ needs Claim part

AI 通过 MCP 也拿同一份 badge。

7. “No-rejection streak” 成就

鼓励玩家写健壮代码：连续 100/1000 tick 无 rejected command，给 badge。它把工程质量转化为游戏成就，非常适合编程游戏。

8. Spectator delayed omniscience with fog toggle

Arena replay 默认全知，但提供 hotkey 切换 “Player A saw / Player B saw / Omniscient”。这既有观赏性，也能教育玩家信息战。

9. Bot version duels

允许玩家让自己的 v12 和 v13 在 Arena sandbox 中自动对打，生成 regression report。对编程玩家非常有吸引力，也能变成内容：“v13 beat v12 by 18% energy efficiency”。

10. Community mod safety rating

Mod 市场除了 rating，还显示 determinism/safety badges：No randomness, No hidden info, Low CPU, Beginner friendly, PvP balanced。AI agent 也可读取这些 badges 决定是否加入世界。

## Final Gate Recommendation

可以进入 Phase 1 实现，但建议新增三个 Phase 1/2 gate：

1. First-hour gate:
   新人类玩家和新 AI agent 各自完成 tutorial golden path，time-to-first-successful-deploy ≤ 10 分钟，time-to-first-visible-impact ≤ 15 分钟。

2. MCP learning gate:
   一个无先验 agent 只依赖 MCP resources，在 tutorial world 中成功部署 basic-harvester，并用 `swarm_explain_last_tick` 修复至少一个失败。

3. Replay/share gate:
   Arena 或 tutorial run 自动产出 shareable replay metadata + safe viewer URL + key events summary。

如果这三个 gate 加入路线图，我对 R8 的终审意见是：APPROVE_WITH_RESERVATIONS，设计足够进入实现。