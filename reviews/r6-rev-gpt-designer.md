# R6 — Game Designer Review (rev-gpt-designer)

Reviewer: GPT-5.5 / Game Designer
Scope: /data/swarm/docs/design/DESIGN.md + /data/swarm/docs/specs/p0/*
Verdict: CONDITIONAL_APPROVE

## Verdict

CONDITIONAL_APPROVE

设计方向成立：Swarm 的核心 fantasy（“代码就是军队”）、人类与 AI 同路径、WASM + deterministic replay、公平资源计量、MCP 作为“屏幕和鼠标”而非 gameplay controller，这些关键决策都已经收敛，且比 Screeps 的精神续作定位更现代、更利于 AI-native 社区传播。

但从“游戏设计 / 第一小时 / 玩家留存 / AI 玩家可学会 / 旁观传播 / 长期追求”视角看，P0 文档已经把安全性、确定性、接口边界写得很硬，却仍有几个会直接影响可玩性与增长的缺口。它不是需要推倒重来，而是需要在 Phase 1-2 前补齐“新玩家第一局如何成功”“失败如何被理解”“Arena 如何成为可观看内容”“World 长期追求不只 GCL/房间数”的设计闭环。

## Highlights / 亮点

1. 核心公平性非常强
   - AI agent 与人类玩家都必须写 WASM，世界只认 WASM。
   - MCP 不含 swarm_move / swarm_attack 等直接动作工具，避免 AI 获得另一套控制面。
   - WasmSandboxExecutor 是唯一执行器，fuel metering 统一计量，设计哲学清晰且可向社区解释。

2. “可解释的失败”进入了 MVP 目标
   - P0-6 的 swarm_explain_last_tick、rejection detail、idle reason、策略指标仪表盘，是编程游戏能不能好玩的核心。
   - 对新手来说，失败不是“代码没动”，而是“为什么没动、下一步该改什么”。这是正确方向。

3. World / Arena 双模式定位明确
   - World 是有机、持久、涌现；Arena 是公平、可排名、可回放。
   - 这很好地解决了 Screeps 类游戏常见矛盾：持久世界天然不公平，但竞技需要可比性。

4. MCP resources 方向基本正确
   - swarm_get_docs、swarm_get_schema、swarm_get_world_rules、swarm_get_available_actions、教程资源，理论上足够让 AI 玩家形成学习循环。
   - P0-3 的结构化快照 + untrusted 标记 + prompt delimiter 契约，对 AI 玩家生态是必要基础。

5. 规则可配置性有社区潜力
   - World Rules Engine + Rhai mod + i18n + 可见规则，能让服务器、赛季、社区模组形成差异化。
   - 这让 Swarm 不只是“一个 Screeps clone”，而是一个 programmable strategy platform。

6. Replay / determinism 对传播很关键
   - Deterministic replay、TickTrace、Arena 赛后公开回放，为 Debug、反作弊、内容创作都打下了地基。

## Concerns / 发现的问题

### G1 — CRITICAL — 第一小时仍过重：玩家从“看懂”到“获得第一个正反馈”的路径太长

文档已有 5 分钟教程与 starter bot，但第一小时体验仍有潜在断点：

- 玩家需要理解：WASM 编译、tick 模型、Command[]、body part、资源、视野、部署、生效延迟、rejection、回放。
- AI 玩家需要理解：MCP 不是控制器、要生成代码、要编译 WASM、要部署、要等待 tick、再根据解释改代码。
- 当前教程描述偏“流程清单”，还没有定义第一小时的情绪曲线和成功标准。

风险：新手第一次部署 bot 后，如果 drone 只是 idle / Fatigued / OutOfRange / MissingBodyPart，玩家可能感受到的是“系统复杂且没有反馈”，而不是“我在优化一个生命体”。

建议在 P0-6 增加明确 First Hour Contract：

- 0-5 分钟：看到 starter bot 自动采集，获得“它活了”的反馈。
- 5-15 分钟：改一个参数，地图上可见产出变化。
- 15-30 分钟：解决一个由系统刻意制造的简单失败，例如 CarryFull，并由 explain_last_tick 指导修复。
- 30-60 分钟：完成一个可分享里程碑：第一次建造 Extension / Tower，或 Arena 教学赛击败 dummy bot。

Severity: CRITICAL，因为编程游戏的留存高度依赖第一次正反馈。

### G2 — HIGH — MCP resources “可学会”仍缺少可验证的 AI 上手基准

P0-3/P0-6 提供了 docs/schema/tutorial/action discovery，但没有定义“AI 仅通过 MCP resources 学会玩”的验收测试。

目前文档说 AI 可调用：
- swarm_get_docs
- swarm_get_schema
- swarm_get_available_actions
- swarm_validate_module
- swarm_deploy
- swarm_explain_last_tick

但缺少：
- MCP resource 的信息架构：教程索引、最小示例、错误修复 cookbook、策略模板是否结构化？
- “从零 agent”是否能在无外部知识下生成可编译 WASM？
- 如果 agent 不具备本地 Rust/TS 编译环境，MCP 是否提供官方 build path 或只提供 validate/deploy？
- AI 失败时 explain_last_tick 是否能给出机器可执行的 correction hint，而不是只给自然语言？

建议增加 AI Onboarding Acceptance Test：

- 给一个无 Swarm 先验的 agent，只允许使用 MCP resources/tools。
- 目标：在 tutorial world 内部署 starter bot，并在 N tick 内达成 harvest + transfer + spawn 或 build。
- 记录指标：首次成功部署时间、编译错误次数、command rejection rate、是否调用外部网页。
- MCP docs 必须包含可复制的最小 WASM 项目模板和构建命令，或提供 “compile service / project template resource” 的明确设计。

Severity: HIGH，因为“AI-native”是项目差异化核心，不能只靠接口存在来证明可玩。

### G3 — HIGH — 观战与传播还停留在功能描述，缺少“为什么别人想看”的内容设计

P0-5/P0-6 已有 Arena 赛后公开回放、全知视角、fog-of-war toggle、解说覆盖层、分享 safe view URL。这是好基础，但仍偏工具层。

缺少内容传播机制：
- replay highlight 自动剪辑：关键战斗、经济爆发、首次入侵、spawn 被毁、逆转点。
- 可嵌入分享卡片：最终得分、代码版本、关键指标、地图缩略图、胜负原因。
- 旁观者实时/延迟观看策略：Arena 是否允许 live spectator？延迟多少 tick 防作弊？
- 社区解说与注释层：能否把 replay 变成“代码策略讲解”？
- “我为什么输了”的公开战报是否可分享。

建议新增 Spectator & Replay Share Spec，至少定义：

- Arena live 观战延迟（例如 100 tick）与公开视角。
- 自动 highlight detector：战斗密度、资源 swing、controller 变化、spawn damage。
- Replay share URL 的默认 landing：30 秒摘要 + 时间轴 + “查看 bot 版本/策略说明”。
- 社区二创：可保存 annotated replay，支持解说文本层。

Severity: HIGH，因为可观看性是 Arena 和社区增长的主要外循环。

### G4 — HIGH — 长期追求过于依赖 GCL、房间数、Arena 排名，缺少横向身份与收藏型目标

文档中长期目标主要有：
- World：殖民地年龄、GCL、房间数。
- Arena：league、赛季、锦标赛。
- 规则模组与社区世界。

这还不够。编程游戏玩家分层明显：不是所有人都想冲排名，也不是所有人都愿意长期 PvP。缺少：

- Bot lineage / 策略谱系：我的 bot 版本如何进化？哪些策略成为社区 archetype？
- Achievement / Milestone：第一次自动防御、首次跨房运输、零 rejection 连续 100 tick、100% 能源闭环等。
- Collection / Identity：徽章、殖民地 banner、回放 trophy、赛季纪念。
- Research tree 或 capability unlock 是否存在？如果完全开放，长期成长只剩规模扩张；如果有解锁，需要避免 pay-to-win/时间碾压。
- 社区声望：优秀 starter bot、教程、mod、replay 解说的贡献者如何被看见。

建议设计 Long-term Progression Layers：

- Skill milestones：按自动化能力解锁徽章，而非只看规模。
- Strategy library：玩家可发布 bot archetype，获得 stars/forks/benchmark scores。
- Seasonal trophies：Arena 赛季、World 事件、modded challenge。
- Colony identity：可视化基地主题、旗帜、公开 profile。

Severity: HIGH，因为长期目标决定留存，也决定非顶尖玩家是否还有价值感。

### G5 — MEDIUM — World Rules Engine 很强，但会增加新玩家认知负担，需要“规则可理解性预算”

可配置资源、物流、存储税、代码传播、模组、Rhai actions 都很有潜力，但对玩家来说每个 world 都可能像新游戏。

当前已有 i18n 和 swarm_get_world_rules，但缺少“规则复杂度分级”和“策略影响摘要”。例如一个 AI 或人类进入世界时，更需要知道：

- 这个世界与默认规则相比有哪些关键差异？
- 哪些差异会影响 starter bot 是否能跑？
- 资源是否只有 Energy？代码部署是否收费？是否有 upkeep？是否 fog-of-war？
- 这是 novice-friendly / hardcore logistics / PvP arena / modded experiment？

建议为每个 world 生成 Rule Digest：

- complexity_score: 1-5
- changed_from_default: list
- starter_bot_compatibility: pass/warn/fail
- strategic_implications: 3-5 条短句
- AI-readable JSON + human-readable card

Severity: MEDIUM，因为规则自由度越高，越需要降低理解成本。

### G6 — MEDIUM — 本地模拟被放到 Phase 3，但它可能是编程游戏的核心迭代手感

P0-6 将 `swarm sim` 设为 P1 / Phase 3。作为游戏体验评审，我认为本地/快速模拟应尽量前置，至少在 Phase 1-2 提供轻量版本。

编程游戏的快乐来自：改策略 → 快速看结果 → 再改。3 秒 tick 的真实世界适合持久运行，但不适合学习和策略调试。

风险：没有快速模拟，玩家每次改代码都要等多个真实 tick，第一小时会变慢。

建议：

- Phase 1 就提供 tutorial-only fast sim 或 deterministic mini-sim。
- starter bot CI 也用同一 sim 验证。
- AI agent 教程中允许调用 swarm_simulate / dry-run 来形成快速改进循环。

Severity: MEDIUM/HIGH，取决于 Phase 1 教程是否能替代本地模拟。

### G7 — MEDIUM — Tutorial “手动控制例外”需要更强的边界与叙事，否则会混淆核心哲学

DESIGN 明确正式世界不开放 manual_control，Tutorial 世界可有受限引导操作。P0-9 也有 Tutorial source 隔离。方向正确。

但从 UX 看，教程如果允许玩家点按钮直接让 drone 做事，可能让玩家误解正式玩法；如果完全不允许，又可能上手太硬。

建议把 tutorial direct actions 设计成“解释/预览”而不是“正式操作”：

- UI 文案明确：这是教程提示，不是正式世界能力。
- 每个 tutorial action 同时展示它对应的 Command JSON 和代码片段。
- 完成后要求玩家把 direct action 替换为代码逻辑。

Severity: MEDIUM。

### G8 — MEDIUM — Arena league 分区命名可能引发公平性争议

P0-6 提到排行榜按 league 分区：Human/WASM、AI-assisted、AI tournament。

问题：Swarm 本质上允许 AI agent 与人类同路径写 WASM，现实中很难可靠区分“人类手写”“AI 辅助”“完全 AI”。如果 league 身份依赖自报，竞技社区会争议；如果依赖检测，会陷入不可证明。

建议将 league 基于提交与运行约束，而不是作者身份：

- Locked Starter / Open Code / Generated Allowed / Agent Autonomous 等规则组。
- 或明确“身份不检测，只按声明参赛，官方只保证运行环境公平”。
- 对 AI tournament，定义 agent 在比赛中是否可赛间修改代码、可使用哪些 MCP/query、是否有 wall-clock 限制。

Severity: MEDIUM。

### G9 — LOW — 文档存在一些命名/一致性小问题，会影响 SDK/docs 自动生成时的清晰度

例子：
- P0-2 RawCommand 示例含 `player_id`，但 P0-9 禁止客户端在 Command body 中自报 player_id，要求服务端注入 auth context。需要统一呈现方式，避免 SDK 用户误以为要填写 player_id。
- P0-2 部分地方使用 `InsufficientResources`，P0-8 RejectionReason 是 `InsufficientResource`。
- DESIGN 中出现两个 “## 10.”（World/Arena 与贡献指南）。
- P0-7 配置中部分字段使用浮点写法如 `decay_rate = 0.001`、`damage_multiplier = 1.0`，而 DESIGN §8.8 强调禁 f64 / 定点数；需要文档层统一为 fixed 表示，避免误导模组作者。
- P0-7 §8 提到“手动控制追加”，与 DESIGN 删除 manual_control 的哲学容易冲突，建议改为 tutorial-only 或移除。

Severity: LOW，但建议在实现前清理，避免生成工具把不一致固化。

## Missing / 缺失项

1. First Hour Contract
   - 缺少第一小时的明确体验目标、成功指标、情绪曲线、失败恢复路径。

2. AI Onboarding Acceptance Test
   - 缺少证明 AI 只用 MCP resources 能从零学会并部署可运行 bot 的自动化测试。

3. Spectator & Replay Share Spec
   - 已有 replay 功能点，但缺少传播产品设计：highlight、share card、live delay、annotated replay。

4. Long-term Progression Spec
   - 除 GCL、房间数、league 外，缺少成就、身份、策略库、贡献声望、收藏/trophy 等长期目标。

5. Rule Digest / World Complexity UX
   - 可配置世界需要“进入前一眼看懂”的摘要层，尤其给 AI agent 和新玩家。

6. Fast Iteration MVP
   - 本地模拟或 tutorial fast sim 应更早成为核心体验，而不只是 Phase 3 P1。

## Fresh Ideas / 新想法

1. “30 秒战报”自动生成
   - 每场 Arena 自动生成短战报：开局 build order、首次冲突、经济曲线转折、致胜 tick、最终 replay link。
   - 给人类是 share card，给 AI 是 JSON battle report。

2. Strategy Archetype Library
   - 玩家发布 bot 不是只发代码，而是标注策略类型：rush、turtle、economic boom、scout-heavy、logistics optimizer。
   - Arena replay 自动识别或建议 archetype，形成 metagame 讨论。

3. “Why did I lose?” 按钮
   - 对 replay 做差异分析：资源闲置、rejection 高发、移动拥堵、spawn downtime、战斗 overkill、视野不足。
   - 输出 3 条最可能的改进建议。

4. Ghost Race / Benchmark Rooms
   - 玩家可以在固定 benchmark map 上跑自己的 bot，与公开 ghost bot 的曲线比较。
   - 适合非 PvP 玩家，也适合 AI agent 自我迭代。

5. Rule Digest Card
   - 每个 world 首页显示：
     - “这是一个轻物流 PvP 世界”
     - “部署免费，代码即时生效”
     - “只有 Energy，一种资源”
     - “推荐 starter bot: basic-harvester v2”
     - “危险：有 upkeep mod，长期 idle 会破产”

6. Replay Fork
   - 玩家可以从某个 replay tick fork 出一个 sandbox scenario，尝试“如果我当时这么改会怎样”。
   - 对教学、复盘、AI 训练都很强。

7. Colony Profile as Social Object
   - 每个玩家有公开 colony page：当前世界、徽章、最佳 replay、bot lineage、常用语言、贡献的 mod/starter bot。
   - 让非冠军玩家也有可展示资产。

## Final Recommendation

可以进入实现，但建议把以下 4 项作为 Phase 1-2 的条件性阻断项或至少同阶段补充文档：

1. 补 P0-6 First Hour Contract：定义第一小时成功路径与指标。
2. 补 AI Onboarding Acceptance Test：证明 MCP resources 足以让 AI 从零部署 starter bot。
3. 补 Spectator/Replay Share Spec：让 Arena 从一开始就具备传播闭环。
4. 补 Long-term Progression mini-spec：至少定义成就、策略库、赛季 trophy、colony profile 的最小版本。

在这些补齐后，本设计不仅技术上可行，也更有机会成为“好玩、可学、可看、可传播、可长期投入”的 programmable MMO RTS。
