# R7 Review — rev-gpt-designer

## Verdict

REQUEST_MAJOR_CHANGES

从 game designer 角度看，Swarm 的大方向是有吸引力的：它不是“复制 Screeps”，而是把人类/AI 共同写 WASM、确定性 replay、Arena 传播、World 沙盒和可配置规则放在同一个生态里。首小时引导、AI MCP onboarding、PvE 生态层、Arena 房间与 replay/spectator 的骨架已经能让人想象“第一小时玩起来”的路径。

但当前 R7 文档仍有至少两个会直接影响 PvP 可玩性、公平性和实现合同的 High 问题：Overload 在 reference 中仍保留全图 fuel-oracle 语义；Leech/Fabricate 作为官方 8 种特殊攻击被写入 Vanilla/Reference，却缺少同等级的 validation/IDL/目标转换合同。它们不是措辞问题，而是玩家会立刻利用、实现会立刻分叉的玩法合同缺口。因此本轮不建议直接进入实现，应先修正 High 项后再进入 implementation gate。

## Strengths

- 首小时体验已经不只是“给文档”：`specs/gameplay/06-feedback-loop.md:25-37` 定义人类 5 分钟教程，`specs/gameplay/06-feedback-loop.md:83-147` 定义 safe_mode → soft_launch → PvP 的过渡、首次部署反馈和首次 PvP 提示。第一小时从“改一个 bot 参数”到“看到资源/威胁/低风险冲突”有闭环。
- AI 玩家路径方向正确：`design/interface.md:5-13` 和 `design/interface.md:48-51` 明确 MCP 是屏幕/鼠标，不是 action channel；AI 必须写 WASM，和人类共享 WasmSandboxExecutor。这个公平性原则很强。
- World/Arena 分工清晰：`design/modes.md:9-23` 把 World 定义为不追求公平的持续沙盒，把 Arena 定义为公平、可复现、适合算法对抗和展示的比赛场。
- PvE 不再只是新手假人：`design/modes.md:25-83` 给了 NPC、资源据点、世界事件、掉落经济和地理难度梯度，能为非 PvP 玩家提供中期目标。
- 可见性和 replay 的安全意识明显增强：`specs/security/05-visibility.md:124-154` 把 player view、spectator view、replay view 分层；`specs/security/05-visibility.md:360-410` 明确 oracle 防线。

## Concerns

### G1 — High — Overload 在 Command Reference 中仍是全图 fuel oracle / harassment 工具

- 位置：`design/gameplay.md:618`、`specs/core/02-command-validation.md:335-366`、`specs/security/05-visibility.md:398-410` vs `specs/reference/commands.md:173-180`
- 问题：核心设计和 validation 已要求 Overload 满足可见性、目标全局冷却，并把触底/成功/no-op 做成攻击者不可区分的等价结果；但 command reference 仍写“目标玩家 fuel > MAX_FUEL×0.2”和“无 range 限制（逻辑攻击）”。如果实现者按 reference 做，玩家可以用 Overload 扫描目标是否存在、是否处于低 fuel、是否可被压制，甚至在无视野条件下进行全图骚扰。
- 玩法后果：这会把一个应当是“战术电子战”的技能变成“远程情报探针 + 压制按钮”，破坏 fog-of-war、反侦察和 first-hour PvP 体验。新手即便在软启动后第一次接触 PvP，也可能被不可见玩家用 Overload 探测/压制，体验上会像被系统作弊。
- 修正建议：以 `specs/core/02-command-validation.md:341-366` 和 `specs/security/05-visibility.md:398-410` 为唯一合同更新 reference：删除 fuel > floor 作为可区分校验；删除“无 range 限制”；写明必须可见、不可见/不存在统一 `NotVisibleOrNotFound`，目标冷却/不适格统一 `NotEligible`，触底 no-op 仍消耗资源和冷却并返回同等 `Ok`。

### G2 — High — Leech/Fabricate 被列为官方特殊攻击，但 validation、IDL、目标转换与反制合同不完整

- 位置：`design/gameplay.md:610-623`、`design/gameplay.md:1021-1037`、`specs/core/02-command-validation.md:435-477`、`specs/gameplay/08-api-idl.md:176-216`、`specs/reference/commands.md:191-206`
- 问题：文档把 8 个特殊攻击写成 Vanilla Standard+ 的官方默认能力，其中 Leech/Fabricate 也出现在 default `world.toml` 和 command reference。但 core validation 只展开到 §3.15 Fortify，IDL 也只定义 Hack/Drain/Overload/Debilitate/Disrupt/Fortify，缺少 Leech/Fabricate 命令定义；reference 对二者仅写“对应 body part”“敌方 drone，1 格内”。Fabricate 的“将敌方 drone 转化为己方建筑”尤其缺少关键合同：转成哪类建筑、是否选择 `structure_type`、成本是否包含新建筑建造成本、是否受 RCL/max_per_room/领土/地形/占用限制、原 body/resource 如何处理、是否可对 hero/neutral/spawning/grace 目标使用、是否有可反制窗口。
- 玩法后果：Leech 若无 cooldown/body part/伤害结算顺序，会成为低成本 sustain dominant strategy；Fabricate 若无 structure whitelist 和放置/经济约束，会成为“用敌方单位免费造建筑”或“绕过 RCL/领土/成本”的破局技能。玩家心理上也会觉得被 Fabricate 很不公平，因为它把单位损失、建筑生成和控制权转换压缩成一个即时动作。
- 修正建议：在 core validation 与 IDL 中补齐 Leech/Fabricate 同等级章节。Fabricate 至少需要：`structure_type` 参数或固定默认；允许结构白名单；目标必须 visible enemy drone 且非 spawning/grace/neutral；tile/terrain/territory/RCL/max_per_room 校验；额外扣除 `build_cost(structure_type)` 或明确“只转为临时 construct/token”；是否占用 main action；失败 refund 规则；TickTrace 记录；反制窗口（建议改成 3-5 tick channel，可被 Disrupt/Fortify 打断，而不是即时不可反制）。

### G3 — Medium — Spectator delay 的默认值在 design 与 security 间冲突，影响观战体验和情报安全

- 位置：`design/gameplay.md:1055-1057`、`specs/security/05-visibility.md:136-139`、`specs/security/05-visibility.md:318-320`
- 问题：design/gameplay 写 `spectate_delay` 默认 0，0 = 实时；security spec 写 World 下 `public_spectate=true` 时必须 ≥50 tick，并在配置表中给默认 50。Arena/World 的观战传播很依赖这个默认值：默认实时会造成情报外流，默认过长又会降低 live spectacle。
- 玩法后果：如果实现按 design/gameplay 默认 0，World public spectate 会成为外部情报频道；如果实现按 security 拒绝 <50，但 UI/文档告诉服主 0 可用，会造成配置失败和运营困惑。
- 修正建议：统一为“World public spectate 默认 false；一旦开启，默认 delay=50 且 validate_config 拒绝 <50；Arena live spectate 可独立默认 0 或小延迟，但赛中 UI 必须标明 delay/fog/all-seeing 状态”。同时在 spectator UI 合同里定义“当前延迟 N tick”“fog-of-war 视角/全知视角”显著标识。

### G4 — Medium — AI 只靠 MCP resources 学会玩的机器可读合同仍不足

- 位置：`specs/gameplay/06-feedback-loop.md:39-64`、`specs/reference/mcp-tools.md:38-45`、`design/gameplay.md:1643-1719`
- 问题：文档已有 AI 教程流程、`swarm_get_docs`、`swarm_get_schema`、`swarm_get_available_actions`、`swarm_get_world_rules`，但缺少 canonical MCP resources manifest。也就是说，AI 知道“应该调用 docs/schema/actions”，但不知道有哪些稳定 URI、版本、语言 SDK、starter bot artifacts、world.toml schema、custom_actions schema、示例 replay/debug traces 可以被枚举和验证。
- 玩法后果：AI 玩家很可能第一小时卡在“能看 snapshot，但不知道如何从 resources 拼出可编译 WASM 工程”。如果必须依赖网页教程、人类 README 或外部知识，就不满足“AI 玩家能仅通过 MCP resources 学会怎么玩”的目标。
- 修正建议：定义 `swarm://manifest` 或 `resources/list` 的强合同，至少包含：`api_reference_uri`、`command_schema_uri`、`world_rules_schema_uri`、`starter_bot_uri`、`sdk_templates`、`compile_targets`、`example_snapshots`、`example_tick_explanations`、`tutorial_steps`、`version/abi`、`locale`。再定义一个 acceptance test：全新 AI agent 只读这些 resources，能生成/validate/deploy `basic-harvester` 并解释前 10 tick。

### G5 — Medium — Replay 分享仍是“能看 URL”，但还不足以形成社区传播飞轮

- 位置：`specs/gameplay/06-feedback-loop.md:245-259`、`design/modes.md:143-145`、`specs/security/05-visibility.md:156-164`
- 问题：回放播放器有 slider、视角切换、指令展开、safe view URL、赛后公开回放，但缺少分享 artifact 的产品合同：标题、封面 tick、关键事件、玩家/算法版本、比分、highlight clip、annotation 权限、embed card、排行榜/锦标赛反链、fork challenge 入口。
- 玩法后果：实现后会“有 replay”，但不一定会“有人传播 replay”。对编程竞技游戏而言，社区传播不是锦上添花，而是让外部观众理解算法对抗、让玩家炫耀策略和吸引新人的核心渠道。
- 修正建议：定义 `ReplayShareCard` / `MatchSummary` schema：`title`、`match_id/world_id`、`participants`、`module_hash/version_label`、`duration_ticks`、`winner/score`、`highlight_ticks`、`thumbnail_tick`、`safe_view_policy`、`annotations`、`leaderboard_link`、`rematch/fork_challenge_link`。Arena 结算页应自动生成可分享战报卡。

### G6 — Medium — 长期追求仍偏“更强/更多/更高排名”，缺少多轴身份目标

- 位置：`design/modes.md:21-23`、`specs/gameplay/06-feedback-loop.md:261-302`、`design/modes.md:147-198`
- 问题：World 明确无胜利条件，指标仪表盘有 GCL、效率、战斗胜率；Arena/PvE 有排行榜和赛季/锦标赛。但长期身份目标仍主要集中在扩张、效率和排名。对 builder、teacher、caster、modder、world curator、PvE collector 这类社区角色，缺少可展示、可积累的身份层。
- 玩法后果：硬核优化玩家会留下，但社区宽度可能不足。一个可编程 MMO 的长期生命力不只来自 GCL/RCL/房间数，也来自“我是谁”：我写过被 100 人 fork 的 bot、我维护一个热门世界规则、我做过精彩解说、我收集过稀有蓝图。
- 修正建议：增加非阻塞但明确的 progression/identity contract：成就、蓝图图鉴、公开 bot fork/star、Arena season badge、PvE scenario mastery、联盟贡献、导师声望、replay caster metrics、mod/world curator reputation。这些应主要是展示层，不直接破坏 World 的不公平沙盒定位。

### G7 — Low — World PvE 事件完全确定且规则公开，可能被脚本化农场过早解构

- 位置：`design/modes.md:50-70`
- 问题：世界事件使用 `Blake3(world_seed || tick_number || event_type)` 确定性触发，NPC 掉落有经济上限。这保证可回放，但也意味着长期运行后，玩家/AI 可能通过观察事件序列预测资源爆发、遗迹激活、游商到来，形成专门 farm bot。
- 玩法后果：PvE 常驻层本来用于给新手和中期玩家提供非毁灭性目标；如果被少数脚本化玩家稳定预测和垄断，会削弱 PvE 的探索感与追赶价值。
- 修正建议：不破坏 replay 的前提下引入“可验证但不可提前预测”的事件随机性：例如按 epoch 预提交 seed hash，事件触发后揭示 seed；或把事件位置/奖励在公开广播前只进入 TickTrace sealed field，赛后可验证。至少需要一条“anti-farm determinism”设计说明。

## Missing

- MCP resource manifest：AI-only onboarding 需要机器可读资源目录、版本、ABI、SDK template、starter bot artifact 和 acceptance test。
- Replay social graph：replay 与 match、leaderboard、player profile、annotation、share card、fork/rematch 的关联模型缺失。
- Spectator UX states：观战延迟、fog/all-seeing 状态、隐藏信息占位、解说 overlay 权限还没有 UI 合同。
- Special attack balancing sheet：8 种特殊攻击缺少统一数值表、unlock tier、counterplay、cooldown stacking、经济成本、失败 refund 与新手禁用策略的一张权威表。
- Long-term identity layer：成就、图鉴、联盟、导师、caster、modder/world curator reputation 等非 GCL 目标轴缺失。

## Fresh Ideas

- “Replay to Challenge”：任何公开 replay 的某个 tick 可以一键 fork 成 Arena puzzle，玩家/AI 从该局面开始尝试“10 tick 内反杀/救援/最高采集”。这能把 replay 变成可互动内容，而不只是录像。
- “Bot Recipe Cards”：为 starter bot 和优秀公开 bot 自动生成策略卡：输入假设、适用世界规则、弱点、最近胜率、可 fork 链接。AI 也可通过 MCP 读取这些卡学习 meta。
- “First Defeat Coach”：玩家第一次被 Hack/Overload/Fabricate 等特殊攻击击败时，不只显示战报，还给一个可运行的 counter-bot diff 或 Arena drill。
- “Caster Mode”：公开 replay 允许社区解说者添加 annotation track；优秀 annotation 获得 caster reputation，成为传播层长期目标。
- “World Rule Preview Simulator”：加入世界前，玩家/AI 可用 1000 tick 快速模拟该世界的 ruleset，看到 upkeep、物流、特殊攻击禁用/启用对 starter bot 的影响，降低加入自定义世界的认知成本。
