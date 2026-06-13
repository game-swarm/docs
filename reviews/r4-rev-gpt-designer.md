# Game Designer Review — GPT-5.5 (Round 4)

## Verdict

APPROVE_WITH_RESERVATIONS — Phase 0 可以冻结，当前版本已经把 Round 3 的主要 gameplay/UX blockers 大体闭合：MCP 不再是作弊式 action channel，AI 玩家可通过 MCP resources 学习、部署、调试；全局存储不再是无代价的万能银行；Rhai 模组从“配置系统”升级为真实的 community ecosystem seed。

但我不建议把“玩家第一小时”和“模组生态上线”视为已完成设计。剩余问题不是架构正确性，而是 product/gameplay completeness：物流 API 已进入 IDL，但 UX 解释、可视化、转换状态、拦截反馈还不够可玩；Rhai 模组有脚本/API/市场雏形，但缺少可发现性、安全分级、兼容性测试、作者激励；F1-F10 只采纳了约一半，尚未形成完整的社区传播闭环。

结论：架构冻结可过；进入 Phase 1/2 时必须把下列 Remaining Concerns 作为 UX/API acceptance criteria，而不是“以后再补的前端 polish”。

## Strengths

S1 — 全局/本地存储的策略权衡已经成立

DESIGN.md §8.4 把 Player Storage 与 World Storage 的差异讲清楚了：全局存储用于市场、部署费、维护费；本地存储用于建造、可被掠夺、具有隐匿性。三种物流模式（无物流/轻物流/硬核物流）非常好，因为它允许同一引擎服务三类玩家：新手、默认 MMO、硬核 Factorio-like 后勤玩家。

尤其是 Round 3 的 dominant strategy blocker 已经明显缓解：累进存储税、本地存储隐匿性、全局↔本地转换时间、运输中可被拦截，共同让“把所有资源塞进全局存储”不再总是最优解。这是正确方向。

S2 — 全局存储 API 已进入 IDL，不再只是设定文本

P0-8 明确加入 `TransferToGlobal` / `TransferFromGlobal`，并包含 validator、cost、duration。这回答了 Round 3 的核心 UX/API 问题：“玩家代码到底如何发起全局↔本地转换？”

这点很重要：如果只在 DESIGN 里说“可以转换”，AI 玩家和 SDK 都无法学会；现在至少 IDL generator 可以把它投射到 TS/Rust SDK、MCP schema、docs 和 validator tests。

S3 — AI 玩家学习闭环基本完整

P0-3 与 P0-6 已经具备 AI 只靠 MCP resources 上手的最小路径：

- `swarm_get_snapshot`：看世界
- `swarm_get_available_actions`：知道现在可做什么
- `swarm_get_docs` / `swarm_get_schema`：学习 API 与规则
- `swarm_get_world_rules`：读取当前世界模组与参数
- `swarm_validate_module`：部署前预检
- `swarm_deploy`：上传 WASM
- `swarm_explain_last_tick` / `swarm_profile`：理解失败与优化策略

这使 AI 玩家不是“需要外部文档的硬编码 bot”，而是真正可以通过 MCP resources 发现游戏规则。并且 P0-3 明确 MCP 不做 `swarm_move` / `swarm_attack`，保持了“世界只认 WASM”的公平核心。

S4 — Deferred Command Model 对玩家心理更友好

WASM `tick(snapshot) → Command[]` 比 imperative host functions 更适合教学、回放和调试。玩家能看到“我提交了这些意图，引擎接受/拒绝了哪些”，这比直接调用 `host_move()` 失败更容易解释。

P0-2 的 rejection response 加上 P0-6 的每 tick explanation，是第一小时体验的关键。一个新手不怕输，怕的是“不知道为什么没动”。当前设计已经把“为什么闲置？”、“为什么不能建 Tower？”、“为什么指令失败？”放进 MVP loop，这是很强的 UX 判断。

S5 — Rhai 模组方向有生态空间

DESIGN.md §8.7 现在不仅说明“能装模组”，还定义了目录结构、`mod.toml`、`init.rhai`、`tick_start/tick_end`、Rhai state/actions API、预算、CLI 安装配置、市场页面、源码 fork/PR、i18n、玩家与 AI 可见规则。

这已经具备生态雏形：

- 服主有轻量创作入口，不需要写 Rust 或 WASM；
- 玩家和 AI 都能看到规则，不会被 hidden mod 破坏公平；
- 模组市场给社区传播提供展示面；
- i18n 让世界规则不只服务中文服主；
- TickTrace 审计让模组行为可回放。

S6 — World/Arena 双模式分工清晰

World 是持久世界与涌现叙事，Arena 是公平比赛与公开 replay。这个切分很好地避免了 Screeps 类游戏常见的“既想 MMO 又想电竞公平”的冲突。P0-5 也将 Arena 赛后全知回放、World 仅自身回放区分开来，避免 World 情报泄露。

S7 — Round 3 的确定性问题大多已闭合

DESIGN.md §8.8 明确了 ChaCha12、Blake3、IndexMap、定点数、Rhai 禁浮点、固定 ECS 顺序、replay checksum。对一个可编程 MMO 来说，这比普通游戏更重要，因为玩家会主动寻找每一个不确定性漏洞。

## Remaining Concerns

G1 — 全局存储 UX/API 仍缺少“运输状态”对象模型

P0-8 有 `TransferToGlobal` / `TransferFromGlobal`，但现在只有 command，没有把转换过程建成玩家可查询的 first-class object。DESIGN 说“运输期间不可用”“可被敌方巡逻 drone 拦截”，但 AI/玩家需要知道：

- 我有哪些 pending transfer？
- 每笔 transfer 的 source/destination、resource、amount、ETA 是多少？
- 运输中资源是否有位置、路线、承运者或 abstract lane？
- 被拦截时 TickTrace / `swarm_explain_last_tick` 如何呈现？
- 转换失败、取消、部分损失、到达后的归属规则是什么？

建议在 P0-8 或后续 P1 IDL 中加入 `TransferJob` / `LogisticsOrder` schema，并在 snapshot 中暴露自己的 pending orders。否则“物流成本”在玩家体验中会像隐藏扣费，而不是可规划、可优化、可被炫耀的 gameplay。

G2 — 物流反馈还不够“可视化可学习”

Round 3 的 F1（物流可视化）只在 Speaker report 中作为 idea 保留，当前 DESIGN/P0 没有真正采纳。对于一个以全局/本地存储为核心差异的游戏，这是偏危险的。

物流如果不可见，玩家只会感觉：资源莫名其妙少了、建造莫名其妙等 5 tick、市场买来的东西不能用。建议最低限度加入：

- 地图资源流 overlay：本地→全局、全局→本地、Terminal trade 的箭头；
- pending transfer timeline：每笔资源的 ETA 与费用；
- logistics loss breakdown：税、转换损耗、拦截损失、维护费分别列出；
- AI-readable equivalent：`swarm_get_logistics_state` 或 snapshot 字段。

这不是美术需求，是核心规则的可理解性需求。

G3 — 全局存储的默认参数仍需要 playtest gate

默认 `transfer_to_global_cost = 1%`、`transfer_from_global_cost = 5%`、to_global 10 tick、from_global 5 tick 是合理起点，但没有说明调参目标。例如：

- 新手是否会因为 5% from-global 成本而不敢扩张？
- 5 tick 是否足以防止战斗瞬时补给？
- 1% to-global 是否仍让所有市场资源默认先进全局？
- 累进税在 60%/85% 阶段是否过强，导致玩家被迫做无聊的库存整理？

建议 Phase 1/2 加一个 “logistics balance telemetry”：资源转换频率、平均本地库存比例、战斗中 from-global 使用率、新手因 InsufficientResource 卡住的 tick 数。否则参数会变成拍脑袋。

G4 — Rhai 模组 ecosystem 缺少安全/能力分级，市场上线风险偏高

当前 Rhai 模组 actions 包含 `deduct_resource`、`award_resource`、`modify_entity`、`emit_event`。虽然是服主安装、可信模型，但社区市场一旦存在，玩家会自然认为“高评分模组可安全安装”。缺少 Tier 0/1/2 分级会让 review 成本不透明。

建议采纳 Round 3 I-2：

- Tier 0: 纯参数/只读/emit_event，不改世界；适合新手服主默认安装。
- Tier 1: 经济修改，例如 award/deduct resource；需要声明经济不变量与测试。
- Tier 2: entity mutation / combat / spawn 相关；需要人工 review、签名、兼容性测试。

这会显著提升 ecosystem trust，也能让模组市场 UI 显示“这个模组会改什么”。

G5 — Rhai 模组缺少 dependency semver 与 World DNA，策略分享会碎片化

`mod.toml` 有 `dependencies = []` / `conflicts = []`，但没有 semver range、engine compatibility、Rhai API version、determinism hash。DESIGN 提到市场和 fork/PR，但没有把“这个世界到底运行了哪组规则”变成可引用对象。

建议采纳 Round 3 I-3：World DNA = Blake3(world.toml + mod names/versions + mod source hash + engine/Rhai/Wasmtime pinned versions)。用途：

- Arena 赛制引用同一规则集；
- 玩家分享 bot 时标注适配的 World DNA；
- 模组市场跑 compatibility CI；
- replay 观看者知道规则没有漂移。

没有 World DNA，社区会迅速进入“我的 bot 在你服上不能跑”的碎片化状态。

G6 — P0-7 与 DESIGN 在定点数/浮点上仍有局部文档不一致

DESIGN §8.8 已写“Rhai 模组脚本禁用浮点，所有模组参数必须 fixed/u32/i64”。但 P0-7 示例仍出现 `decay_rate = 0.001`、`damage_multiplier = 1.0`、`if config.combat.damage_multiplier < 0.0` 这类浮点写法。

这不是 gameplay blocker，但会误导实现者和模组作者。建议统一为 `fixed<u32,4>` 的整数写法，例如 `decay_rate = 10` 表示 0.0010，`damage_multiplier = 10000` 表示 1.0。模组生态早期文档必须一致，否则第三方模组会从 day one 写出非确定性参数。

G7 — `swarm_validate_plan` / `swarm_simulate` 的边界仍需产品化

P0-6 仍列出 `swarm_validate_plan`，P0-3/P0-9 更偏向 `swarm_simulate` / snapshot-bound dry-run。作为 UX，我支持保留某种 “what if?” 工具，但必须向 AI 玩家说清楚：这是 non-authoritative prediction，不是 guaranteed future。

建议命名上避免 `validate_plan` 让玩家误以为“服务器承诺会成功”。更好的命名：

- `swarm_dry_run_commands(snapshot_id, commands)`：只验证当前快照下是否合法；
- `swarm_simulate(snapshot_id, module_id, ticks)`：预测，不保证真实世界；
- response 必须包含 `confidence` / `invalidated_by`: resource contention, enemy movement, hidden information。

G8 — 第一小时仍偏“能运行”，还未到“好玩”

5 分钟教程、starter bot、解释型拒绝原因都很好，但第一小时长期目标仍不够明确。Screeps 的魅力在于“我写了一点代码，它活了，然后我想让它更聪明”。Swarm 还需要第一小时的 milestone ladder：

1. 第一个 drone 成功采集；
2. 第一次自动 spawn；
3. 第一次 building 完成；
4. 第一次资源瓶颈解释；
5. 第一次 replay 看见自己的策略改善；
6. 第一次 Arena bot 跑完并得到评分。

建议把这些做成 tutorial achievements，不只是 docs。尤其 AI 玩家也需要 machine-readable milestones，方便 agent 自我判断“我是否学会了”。

G9 — 长期追求仍过度依赖 GCL/room/league，缺少多轴身份

DESIGN 的路线图提到 GCL、房间数、league、赛季，但 Round 3 I-6（技术树/声望/赛季遗产）尚未采纳。对可编程游戏来说，长期动力不应只有“更大帝国”和“更高排名”。建议补充：

- Strategy Badges：最省 fuel、最高物流效率、最少代码行、最长无人值守；
- Mod Author Reputation：被多少世界安装、兼容多少 World DNA；
- Bot Lineage Prestige：fork tree 中被复用最多的策略；
- Research/Tech Unlocks：不是数值碾压，而是解锁观察、调试、自动化便利；
- Seasonal Legacy：赛季结束保留 cosmetic/title/replay trophy，而非永久经济优势。

否则 World 后期容易退化为“老玩家滚雪球，新玩家看不懂”。

G10 — 旁观者/Replay 分享有方向，但社区传播还不完整

P0-5/P0-6 已定义 Arena 赛后公开 replay、观战视角、解说覆盖层，这是强项。但还缺少“传播包装”：

- replay permalink 的 metadata：World DNA、bot versions、关键事件、胜负条件；
- 30 秒 highlight clip 自动生成；
- fog-of-war toggle 的 share-safe 默认；
- bot source / strategy writeup 链接；
- AI-generated commentary 的审校/标注机制。

如果 Swarm 想开源首日就获得社区传播，Replay 不能只是调试工具，它应该是“策略故事”的发布格式。

## F1-F10 Ideas Adoption Review

F1 物流可视化 — 未实质采纳。DESIGN 有物流规则，但没有 UI/MCP logistics visualization。建议升为 P1 UX requirement。

F2 MCP 策略提示资源 `swarm://docs/strategies/` — 部分采纳。P0-6 有 `swarm_get_docs` 和 tutorial resources，但没有 strategy cookbook/resource namespace。建议加入 starter strategies：harvester、builder、defender、logistics。

F3 四类世界模板 beginner/default/arena/hardcore — 部分采纳。DESIGN 有三种物流模式和 World/Arena 默认值，但没有完整 world template product surface。建议 `swarm world create --template beginner|default|arena|hardcore`。

F4 本地市场 LocalMarketRule mod — 未采纳。当前市场仍偏全局/Terminal。可作为首批官方 Rhai 示例模组，非常适合证明模组生态价值。

F5 Rhai 市场信誉系统 ReputationRule mod — 未采纳。适合作为 Tier 0/1 模组示例：不直接改变战斗，只影响交易信任和市场排序。

F6 replay 解说生成 — 部分采纳。P0-6 有观战解说，R3 Speaker 也保留 I-9，但还没有具体 data contract。建议 TickTrace 中标注 highlight candidates。

F7 bot lineage / fork tree — 未采纳。对开源策略生态非常关键。建议至少在 module metadata 中预留 `parent_module_id` / `source_repo` / `license`。

F8 硬核物流专属排行榜 — 未采纳。当前 leaderboard 仍是 GCL/房间/drone。建议为 hardcore logistics worlds 增加 throughput、average delivery distance、loss rate、fuel per delivered resource。

F9 i18n 术语表 MCP resource — 部分采纳。Rhai mod i18n 和 Accept-Language 已采纳，但术语表资源未出现。建议 `swarm://docs/glossary?locale=zh`，帮助 AI 稳定理解 Energy/Storage/Controller/Global Storage 等术语。

F10 新手世界默认启用解释型拒绝原因 — 基本采纳。P0-2 rejection detail + P0-6 explain_last_tick 覆盖了核心需求。建议确保 beginner template 默认开启 verbose explanations，而 Arena 可降级为 compact。

总体采纳度：约 4.5/10。关键 blockers 已采纳，但社区传播和长期追求类 ideas 还偏 backlog。

## Fresh Ideas

N1 — Logistics Job Board

把全局↔本地转换、Terminal trade、本地运输统一抽象为 Logistics Job。玩家和 AI 都能看到自己的 job board：pending、in_transit、delivered、intercepted、failed。硬核世界可以允许玩家写专门的 carrier bot 自动接单，形成“物流职业”。

N2 — Official Mod Starter Pack

Phase 2 前准备 5 个官方 Rhai 示例模组，作为生态种子：

- `local-market`：地理约束交易；
- `empire-upkeep`：帝国维护费；
- `logistics-tax`：领土控制者收过路费；
- `reputation-market`：交易信誉；
- `seasonal-mutations`：赛季事件/资源变异。

每个模组都附带 tests、World DNA、截图、AI-readable rules，给社区一个可 fork 的质量标准。

N3 — Strategy Cookbook as MCP Resources

除了 API docs，提供 `swarm://strategies/basic-harvester`, `swarm://strategies/remote-mining`, `swarm://strategies/logistics-buffering`, `swarm://strategies/arena-rush`。它们不直接给最优代码，而是给 strategy pattern、常见失败、指标目标。AI 玩家会非常需要这种中层知识。

N4 — Replay Highlight Schema

TickTrace 中为事件打 highlight tags：first_spawn、first_tower、resource_starvation、enemy_contact、base_breach、logistics_intercept、comeback、decisive_fight。这样 replay viewer、AI 解说、社交分享都能复用同一份结构化事件。

N5 — World Template Cards

把世界配置产品化为卡片，而不是让服主直接面对 world.toml：

- Beginner: 免费部署、无存储税、verbose explanation、弱 PvP；
- Default MMO: 轻物流、市场、PvP、普通 fog；
- Hardcore Logistics: 无全局存储或高转换成本、物流 leaderboard；
- Arena: 对称地图、全信息、赛后公开 replay；
- Seasonal: 固定周期、World DNA、赛季遗产。

N6 — “Why Not?” API

在 `swarm_get_available_actions` 旁边增加 `swarm_explain_unavailable_actions(entity_id)`。新手和 AI 最常问的不是“我能做什么”，而是“为什么我不能 build/spawn/transfer？”这能显著降低第一小时挫败感。

N7 — Bot Lineage Metadata

每次 deploy 可选提交：source repo、license、parent module/bot id、strategy tags。未来可做 fork tree、策略家声望、bot genealogy replay。这对开源社区传播比普通排行榜更有生命力。

N8 — Logistics Heatmap for Spectators

Arena/World replay 中展示资源流热力图：哪些路线承载最多资源，哪些 chokepoint 被截断，哪次 raid 切断了供应线。这会让“代码游戏”变得可观看，而不是只有作者看得懂。

N9 — AI Self-Evaluation Milestones

MCP tutorial 返回 machine-readable goals：`harvested_energy >= 100`, `spawned_drones >= 3`, `built_structure == Tower`, `command_success_rate >= 80%`。AI agent 可以自动判断是否完成教程，而不是靠自然语言猜测。

N10 — Mod Compatibility CI in Marketplace

模组市场对每个提交自动跑：determinism replay test、budget test、API compatibility、i18n completeness、Tier permission diff。市场页面显示 badge。这样生态从一开始就是“可运行的规则包”，不是脚本垃圾场。
