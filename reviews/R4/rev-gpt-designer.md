# R4 Clean-Slate Review — rev-gpt-designer

Reviewer: Game Designer / UX / Player Psychology
Scope: `/tmp/swarm-review-R4/*` clean copy only
Verdict: CONDITIONAL_APPROVE

## Verdict

CONDITIONAL_APPROVE.

R4 已经把 Swarm 从「Screeps-like 技术方案」推进成了一个较完整的可编程 MMO RTS 平台：核心循环、MCP 公平性、WASM 沙箱、回放、可见性、Arena/World 双模式、教程与 starter bot 都有明确设计。作为游戏，它的主张足够强：玩家写代码，代码成为军队；AI 和人类同路进入 WASM；策略迭代通过 replay / explain / sim 闭环完成。

我不建议进入大规模内容扩张前直接 APPROVE，原因不是架构，而是「第一个小时是否好玩」和「长期追求是否足够可传播」仍有若干高风险空洞。当前设计对已经理解 Screeps/编程游戏的玩家很有吸引力，但对新玩家、旁观者、AI-only 玩家、社区传播链路的产品化还不够硬。若补齐 onboarding、可分享 replay、Arena 社交传播、长期非 GCL 目标和若干平衡护栏，可进入实现。

## Strengths

1. 核心幻想清晰：Write once, fight forever

「你的代码就是你的军队」非常强，且与 WASM、多语言、fuel metering、确定性 replay 强绑定。它不是单纯技术包装，而是能直接转化为玩家动机：我优化一段代码，世界里的殖民地就更聪明、更强。

2. AI / 人类公平路径设计正确

MCP 被定义为 AI 的屏幕和鼠标，而不是 gameplay action channel；AI 也必须生成 WASM、部署、观察、调试。这避免了 AI 玩家获得额外操作通道，也让「AI 玩家能不能学会玩」成为 MCP docs/schema/resources 的 UX 问题，而不是公平性灾难。

3. LEARN → DECIDE → ACT → UNDERSTAND 闭环非常关键

`swarm_get_docs`、`swarm_get_schema`、`swarm_get_available_actions`、`swarm_dry_run_commands`、`swarm_explain_last_tick`、`swarm_profile`、本地 `swarm sim` 和 replay viewer 共同覆盖了编程游戏最容易失败的点：玩家不知道为什么输了、为什么 idle、为什么指令被拒绝。

4. World / Arena 双模式是正确的产品拆分

World 模式承接持久 MMO、涌现政治、殖民地经营；Arena 模式承接公平对战、自我对抗、公开回放、算法竞赛。两者共用引擎但承诺不同，能避免「持久世界不公平却要做排行榜」的经典矛盾。

5. 可见性策略对游戏公平性和观战体验有清楚边界

`drone snapshot`、玩家屏幕、MCP 查询、旁观者 WebSocket、replay privacy 分层明确。尤其是「drone 感知永远受 is_visible_to 约束，player_view 只影响屏幕/MCP」是正确不变量。

6. Rule Engine / world.toml 给社区服主留下空间

资源、body part、建筑、伤害、特殊效果、物流模式、可见性、Arena 参数均可配置。长期看，这为社区世界、教学世界、主题世界、硬核物流服提供了基础。

7. Replay/Explain 具备传播潜力

设计已有 replay viewer、指令箭头、tick slider、解说覆盖层、公开 replay。编程游戏很难靠直播实时理解，replay 是最适合传播的载体。

## Concerns

### G1 — High — 第一个小时仍偏「工程任务」，不够像游戏

文档提供了 5 分钟教程和 starter bot，但第一小时的情绪曲线还不明确。玩家完成 basic-harvester 后，下一步是「改代码、跑 sim、部署、看 explain」；这对程序员合理，但游戏层面的短期目标不够强。

风险：新玩家在第一小时感受到的是「我要先搭工具链、理解 ABI、部署 WASM、读 rejection」而不是「我马上拥有一群小单位，它们因为我的策略变聪明了」。

建议条件：定义 First Hour Milestones：
- 0-5 min：看到 starter bot 自动采集，并能改一个数字产生可视变化。
- 5-15 min：完成第一个自定义策略，例如双 harvester + one builder。
- 15-30 min：遇到第一个可解释失败，例如 OutOfRange / Fatigued，并用 explain 修复。
- 30-60 min：完成一个可分享成果：建成 Tower、赢一场 micro Arena、或生成 replay link。

### G2 — High — MCP resources 能教 AI「学会规则」，但未保证 AI「能完成编译部署」

AI onboarding 有 `swarm_get_docs`、`swarm_get_schema`、`swarm_get_world_rules`、`swarm_get_available_actions`、`swarm_validate_module`、`swarm_deploy`。这足够让 AI 读取规则和 API，但流程假设 AI agent 自己具备本地编译 WASM 的能力。

如果题目是「AI 玩家能不能仅通过 MCP resources 学会怎么玩」，答案是：能学规则，未必能完成闭环。因为 resources/docs/schema 不等于 toolchain；`swarm_validate_module` 只预检，`swarm_deploy` 需要 wasm_bytes。

建议条件：MCP learning resources 必须包含：
- `swarm://docs/tutorials/basic-agent` 的完整最小可运行项目。
- `swarm_sdk_fetch(world_id)` 返回 SDK artifact 和 build instructions。
- 至少一个不依赖外部脚手架的 minimal WASM sample，含 base64 或 source + deterministic build recipe。
- 明确说明「MCP 不负责编译」或新增 hosted compile/sandboxed build 工具。否则 AI-only 玩家会卡在从源码到 WASM 的鸿沟。

### G3 — High — 特殊攻击系统过早复杂，可能压垮可理解性和平衡

Hack、Drain、Overload、Debilitate、Disrupt、Fortify、Leech、Fabricate 都很有想象力，但它们组合后会产生高认知负担：控制锁、Neutral、fuel 压制、抗性、净化、持续动作、资源窃取、转化建筑。文档虽然给 Tutorial/Novice 默认禁用特殊攻击，但 Standard+ 全部可用的跳变过陡。

风险：玩家还没理解采集/物流/占领，就被 Hack/Fabricate/Overload 这类 meta 技能支配。尤其 Overload 直接攻击对方计算配额，是非常有主题性的机制，但也最容易成为挫败来源：玩家感受到「我的代码突然不工作了」，需要极强解释 UI。

建议条件：把特殊攻击分成明确 unlock tiers，而不是 Standard+ 一次性全部打开：
- Tier 0：Move/Harvest/Build/Transfer/Spawn/Attack/Heal。
- Tier 1：Disrupt/Fortify（可理解的打断与防御）。
- Tier 2：Drain/Debilitate（经济与易伤）。
- Tier 3：Hack/Overload/Fabricate（高影响 meta 技能，仅 Advanced/Arena lab）。
并为每个技能提供 replay explanation 模板和 counterplay hint。

### G4 — Medium — World 模式长期追求仍偏传统 GCL/room count，缺少玩家身份目标

文档有 GCL、房间数、殖民地年龄、资源、市场、Arena replay，但长期追求主要还是扩张和效率。对于可编程 MMO，长期留存还需要「我是谁」和「我在社区中留下什么」：策略作者、世界服主、模组作者、赛事组织者、教学者、replay 解说者。

风险：老玩家只剩扩张效率竞赛；新玩家面对老玩家帝国时缺少非对称目标。

建议条件：设计非 GCL 长期目标：
- Algorithm Gallery：玩家发布 bot 版本、说明、成绩、replay。
- Strategy Badges：物流大师、防守专家、低 CPU 挑战、最小 body 通关。
- Mod/World Creator reputation：世界被收藏、被 fork、被用于比赛。
- Arena puzzle of the week：固定地图挑战，按代码效率/资源效率排名。
- Replay annotation author：优秀解说/教程 replay 进入官方精选。

### G5 — Medium — 旁观者和 replay 有基础，但社区传播链路还未产品化

文档已有 replay viewer、分享回放、观战视角、解说覆盖层、Arena 赛后公开回放。但缺少「一条 replay 如何在社区传播」的完整产品规格：链接预览、短片段、关键 tick、评论、fork 策略、从 replay 一键进入 Arena rematch。

风险：replay 成为调试工具，而不是传播工具。Screeps-like 游戏天然难看懂，如果没有强 replay packaging，社区扩散会很弱。

建议条件：补一份 Replay Sharing UX spec：
- URL 支持 `?tick=1234&speed=4x&view=omniscient&annot=...`。
- 一键生成 30 秒 highlight clip 或 GIF/WebM。
- 关键事件自动打点：first kill、spawn destroyed、tower online、resource collapse、CPU overloaded。
- Replay 页面显示双方 bot version、规则 hash、地图 seed、最终指标。
- 「Fork this match」：用同地图 seed 和相同初始条件创建 Arena 房间。

### G6 — Medium — 新手保护与密度分配保护了公平，但可能削弱早期社交冲突

密度最低出生、避免包围、500 tick safe_mode、重生到新房间都合理。但如果早期缺少轻量互动，新玩家前几小时可能像单机优化题，直到突然遇到 PvP 或 logistics bottleneck。

建议条件：加入低风险早期社交/冲突：
- 新手区公共事件：限时资源潮、可合作击破中立据点。
- Non-lethal skirmish：小型 Arena challenge 嵌入 World UI。
- Market/tutorial contracts：老玩家发布资源运输/防御 bot challenge，新玩家接单获得安全奖励。
- Ghost opponent：从公开 replay 中抽取一个弱 AI 作为教学对手。

### G7 — Medium — Arena 胜负与评分目标仍不够稳定

不同文档中 Arena 终止/胜利描述略有差异：MVP 反馈循环写「摧毁敌方 Spawn 或时限结束时分高者胜」；DESIGN §9.1.3 写「drone=0 > 认输 > tick 到上限按剩余资产判定」。这不是致命问题，但对算法竞赛非常关键，因为评分函数会决定 meta。

风险：如果得分函数太粗，玩家会优化单一 dominant strategy，例如只保 drone 数、不打经济；如果摧毁 Spawn 是唯一目标，则 turtle/rush 平衡会极难。

建议条件：Arena 必须有权威 scoring spec：
- Primary：对方 spawn/core destroyed。
- Secondary：控制面积、有效经济流、军事价值、建筑价值、剩余资源，按权重。
- Anti-stall：无交战/无扩张过久触发 pressure event 或判定。
- Draw policy：固定 map_seed 下可复现，平局可接受但要被标记。

### G8 — Low — 可配置世界很强，但玩家选择世界时的信息架构未定义

world.toml、mods、SDK hash、Layer 1/2/3、[MOD] 标识都很完整，但玩家在世界列表中如何选择世界尚不明确。

建议：世界列表需要显示：规则复杂度、是否 Vanilla、是否 PvP、tick speed、物流模式、special attacks tier、public replay、active players、recommended skill level、SDK compatibility。否则新玩家可能误入高复杂度 MOD 世界。

## Missing

1. First Hour Playtest Script

需要一份可执行的 playtest checklist，而不只是教程描述。观察指标应包括：首次部署耗时、首次理解 rejection 耗时、首次产生可视成就耗时、玩家是否能解释下一步目标。

2. AI-only Onboarding Acceptance Criteria

需要定义「只给 MCP resources + tools，一个未预训练 Swarm 的 agent 是否能完成 basic-harvester 部署」的验收测试。理想验收：agent 调用 docs/schema/world_rules/sdk_fetch，生成或获取 starter bot，validate，deploy，explain，迭代一次。

3. Replay Sharing / Spectator Product Spec

现有设计有技术能力，缺产品闭环。应补：分享链接、延迟策略、highlight、注释、权限、嵌入卡片、从 replay fork match。

4. Arena Scoring Canonical Spec

需要统一胜负条件、资产估值、反拖延、平局处理、league 分类。

5. Long-Term Progression Beyond Expansion

缺少跨 World/Arena/Mod/Replay 的身份型成长系统：作者声誉、策略收藏、世界 fork、赛事成绩、教学贡献。

6. Balance Telemetry Plan

已有 strategy dashboard，但缺设计侧要看的 liveops 指标：新手 24h 留存、首次 tower 建成率、平均 idle drone 比例、常见 rejection 分布、特殊攻击使用率/胜率、Overload 后流失率、Arena 平均时长、rush/turtle 胜率。

## Fresh Ideas

1. Bot Genome / Strategy Diff

每次部署生成策略版本卡：代码 hash、规则 hash、核心指标变化、相对上一版的行为 diff。玩家能看到「v12 比 v11 少 23% idle，多采 18% energy」。这会把代码迭代变成 RPG 式成长。

2. Replay-to-Patch

在 replay 中选中一个失败事件，点击「生成修复任务」：系统把 tick snapshot、rejection、相关 entity、建议 prompt 打包给 AI agent 或 IDE。对 AI 玩家尤其强。

3. Arena Seed Ladder without Matchmaking

不做自动匹配也可以做 weekly seed ladder：官方每周发布固定 map_seed + 初始规则，玩家提交 WASM，在本地/服务器跑标准评测，公开 replay 和分数。低运维、高传播。

4. Spectator Commentary DSL

让社区作者给 replay 写轻量注释脚本：在 tick 1200 显示「红方物流线断裂」、tick 1430 高亮 Tower。优秀注释 replay 会成为教程内容。

5. Newbie Ghosts

把优秀 starter bot 或玩家公开 bot 的旧版本做成 ghost opponent。新玩家不用直接面对老玩家帝国，也能在 30 分钟内体验「我的代码打赢了一个对手」。

6. Strategy Contracts

World 中允许玩家发布合约：运输 N energy、守住某房间 1000 tick、写一个低 CPU harvester。合约以 replay/metrics 自动验收，给新玩家提供非扩张型目标。

7. Complexity Budget per World

世界配置自动计算 complexity score：资源种类、body parts、special attacks、fog、logistics、mods。Tutorial/Novice 世界限制 score，上手路径更稳。

8. Explain as Narrative

`swarm_explain_last_tick` 除结构化 JSON 外，为 Web UI 生成一行人类可读战报：
「Harvester-3 想采集 Energy，但距离 source 2 格；它需要先 Move West。」
编程游戏的乐趣很大一部分来自把系统反馈转成玩家能理解的故事。

## Final Recommendation

进入实现前建议把以下作为 R4 条件项：

1. 补 First Hour Playtest Script。
2. 补 AI-only MCP onboarding 验收测试，明确 SDK/build 闭环。
3. 补 Replay Sharing UX spec。
4. 统一 Arena scoring spec。
5. 为特殊攻击定义 tiered unlock 和 replay/explain counterplay 模板。
6. 增加长期身份型目标，而不只依赖 GCL/room count。

完成这些后，设计从 game design 角度可以 APPROVE。当前为 CONDITIONAL_APPROVE。