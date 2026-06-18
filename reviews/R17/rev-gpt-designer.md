# R17 游戏设计评审（GPT-5.5 / Designer）

## Verdict

CONDITIONAL_APPROVE

从“这个游戏是否好玩、AI 是否能只靠 MCP resources 学会、社区传播与长期追求是否成立”的 Designer 视角看，R17 已经比 R15/R16 更接近闭环：10 分钟 Golden Path、First-Hour 过渡、soft_launch、Arena/PvE/Replay、长期目标系统都已经成型，且“MCP 不是游戏动作通道，AI 与人类同样写 WASM”的核心哲学在主设计中保持清晰。

但我不能给 APPROVE，因为“权威单源是否真正闭合”在游戏体验最关键的 Learn/Decide/Understand 链路上仍有明显裂缝：design/interface.md、specs/reference/api-registry.md、specs/gameplay/06-feedback-loop.md、specs/gameplay/08-api-idl.md 对 MCP 工具名、错误码、dry-run/simulate 命名、Arena 胜利条件与经济边界仍存在可见冲突。对人类玩家这会表现为文档困惑；对 AI 玩家这会直接破坏“仅靠 MCP resources 自举”的承诺。

---

## Strengths

1. 首小时体验终于有情绪曲线，而不是只有“写 bot、看资源涨”。
   - design/gameplay.md 给出 10 分钟 Golden Path：登录、SDK、编译、部署、观察、调试、首个 PvE 击杀。
   - specs/gameplay/06-feedback-loop.md 进一步补了 5 分钟教程、soft_launch、首次 PvP 被攻击时的战斗报告与 Arena Challenge 引导。
   - 这解决了早期版本“数小时独自优化，然后突然被碾压”的体验真空。

2. AI 玩家路径在设计哲学上是对的。
   - design/README.md 与 design/interface.md 明确：AI agent 通过 MCP 查看世界、生成代码、部署 WASM；游戏动作必须由 WASM tick() 输出 Command[]，不存在 swarm_move/swarm_attack 这类 MCP 直接动作。
   - 这保证 AI 与人类玩家在“世界只认 WASM”下公平，也让 AI 玩法不是外挂式控制器。

3. World 与 Arena 的产品定位清楚。
   - World 是不追求个体公平的持久沙盒，强调殖民地、扩张、经济、PvE/PvP 共存。
   - Arena 是对称、短时、算法对抗、可 replay 的表达场。
   - 这能同时服务“长期经营玩家”和“想快速验证策略/分享比赛”的玩家。

4. Replay/观战已经从技术能力走向社区传播能力。
   - modes.md 定义 Arena 赛后 replay、公开/非公开可见性、速度控制、双视角切换。
   - feedback-loop.md 补了玩家视角 replay、全知视角、fog-of-war 切换、解说覆盖层、分享 safe view URL。
   - 这对可编程 RTS 很重要：玩家愿意分享“我的算法如何赢”，比单纯排行榜更容易传播。

5. 长期追求不再只有 GCL/RCL。
   - gameplay.md 增加殖民地年龄、Arena 段位、PvE 里程碑、Replay/观战声誉等长期目标。
   - 这降低了“老玩家扩张碾压 = 唯一目标”的风险，也给非硬核 PvP 玩家留下空间。

---

## Concerns

### G1 — High — MCP 学习链路的工具名没有闭合，AI 不能可靠“只靠 MCP resources 学会怎么玩”

问题：
- design/interface.md §4.1 明确要求工具目录包含 swarm_get_schema、swarm_get_docs、swarm_get_available_actions、swarm_explain_last_tick、swarm_validate_module、swarm_deploy 等，并称权威工具清单见 API Registry。
- specs/gameplay/06-feedback-loop.md 的 AI onboarding 验收也依赖 swarm_get_schema → swarm_get_docs → swarm_get_available_actions，以及 swarm_explain_last_tick。
- 但 specs/reference/api-registry.md §3 的 46 工具清单中没有 swarm_get_schema、swarm_get_docs、swarm_get_available_actions、swarm_explain_last_tick；它有 swarm_get_tick_trace、swarm_dry_run、swarm_get_deploy_status 等另一套命名。
- interface.md 还写 swarm_dry_run_commands；registry.md 写 swarm_dry_run；snapshot-contract.md 写 swarm_simulate 与 swarm_dry_run。

为什么这是游戏设计问题：
AI agent 的第一小时不是“读整份设计文档”，而是通过 MCP resources/tools 自举。如果 onboarding 教程教它调用的工具在权威 registry 中不存在，AI 玩家会卡在第一步：不知道 API 在哪里、当前能做什么、失败后如何解释。

建议：
- 以 game_api.idl.yaml / api-registry.md 为唯一权威，创建一个“Onboarding minimal tool contract”，至少包括：
  1. swarm_get_schema 或等价命名
  2. swarm_get_docs 或 resources/read 文档资源
  3. swarm_get_available_actions 或由 swarm_get_world_rules + SDK schema 明确替代
  4. swarm_deploy
  5. swarm_validate_module 或 swarm_dry_run
  6. swarm_explain_last_tick 或明确由 swarm_get_tick_trace + explain endpoint 替代
- design/interface.md 与 06-feedback-loop.md 不应列出与 registry 冲突的工具名；只能引用 registry 或生成表。

### G2 — High — IDL 与 API Registry 的 RejectionReason / Command 合同不一致，会破坏“失败可理解性”

问题：
- specs/reference/api-registry.md §2 说 RejectionReason 共 35 个变体，并统一命名为 InsufficientResource、ObjectNotFound、CooldownActive 等。
- specs/gameplay/08-api-idl.md §2 的 RejectionReason 列表包含 NotMovable、Fatigued、MissingBodyPart、TileBlocked、StillSpawning、NoPath、CarryFull、NotSource、TargetFull、NotYourRoom 等大量 registry 中没有的变体，同时缺少 registry 中的多个变体。
- snapshot-contract.md 的 Safe Hint Ladder 又使用 InsufficientResources、PermissionDenied、InvalidTarget 等名字；registry 明确废弃 InsufficientResources，并规定 MCP 层 NotAuthorized、validation 层 NotOwner。

为什么这是游戏设计问题：
Swarm 的核心乐趣不是“命令成功”，而是“我知道为什么失败，然后改代码”。错误码是玩家心理反馈的基础。如果文档与 IDL 对错误类别不一致：
- 人类 IDE 无法提供稳定的 inline hint。
- AI agent 无法可靠把失败原因映射到修复策略。
- Replay/战斗报告里的解释会和 SDK 类型不一致，损害学习闭环。

建议：
- RejectionReason 只允许在 registry/IDL 机器源中定义一次。
- feedback-loop 与 snapshot-contract 只引用 category，不重新造名字。
- 若产品层需要更细的“教学原因”（Fatigued、CarryFull 等），应明确区分：
  - protocol RejectionReason（稳定、少量、权威）
  - pedagogical diagnosis（由 explain_last_tick 派生、可多语言、非协议 enum）

### G3 — Medium — Arena 胜利条件存在两套口径，影响可观赏性与策略预期

问题：
- design/modes.md 表中和 §9.1.3 写：一方 drone=0 > 认输 > tick 到上限按剩余资产判定（drone数→建筑数→资源量）> 平局。
- specs/gameplay/06-feedback-loop.md §6 写：胜利条件为摧毁敌方 Spawn，或时限结束时分高者胜。

为什么这是游戏设计问题：
Arena 是 Swarm 最适合传播的模式。观众和玩家必须在开局就理解“怎样算赢”。drone=0 与摧毁 Spawn 会产生完全不同的策略：
- drone=0 鼓励歼灭战、游击与诱敌。
- Spawn kill 鼓励基地突袭、防守建筑与 race。
- 资产计分又鼓励经济滚雪球和末期保值。

建议：
- 选定唯一 Vanilla Arena scoring contract，并让 UI/replay/room config 都用同一说法。
- 如果要支持多胜利条件，应作为 room preset：Elimination / SpawnKill / ScoreAttack，而不是散落在不同文档中。

### G4 — Medium — Market/交易/合约边界仍有残留矛盾，可能污染长期目标设计

问题：
- gameplay.md 多处声明 Market/trading 为 RFC，占位且已从 IDL/默认 SDK 移除。
- snapshot-contract.md §3.2 却把 Allied Transfer 列为 MVP 中实现的受限合作；§3.3 又把 Contract Settlement、Market Orders 等列为 Future RFC。
- feedback-loop.md 的 first-hour “低风险社交冲突”包含 Market Contracts：老玩家发布资源运输/防御 bot challenge，新玩家接单获得安全奖励。

为什么这是游戏设计问题：
这会让新玩家和服主误判 MVP 的社交/经济玩法。若 Market Contracts 被文档包装成新手过渡内容，但经济边界又说 Contract Settlement 是 Future RFC，玩家第一小时会期待一个不存在的目标系统。

建议：
- MVP first-hour 中把 “Market Contracts” 改为不涉及资源结算的 Challenge Board / Replay Bounty / Badge Challenge。
- 若 Allied Transfer 属于 MVP，则 registry/IDL 必须出现对应 action/tool；否则应降级为 Future RFC。
- 新手过渡期不要依赖任何 RFC 经济功能。

### G5 — Medium — 旁观/Replay 的隐私与传播设计已经有雏形，但 World 模式的“可分享边界”还不够产品化

问题：
- modes.md 定义 World public_spectate、Arena visibility、赛后 replay 公开规则。
- feedback-loop.md 定义自身视角 replay、safe view URL、观战 fog-of-war 切换。
- snapshot-contract.md 定义截断与竞技安全提示，但没有把“分享 replay 时的视角权限、延迟、红action、公开摘要粒度”形成一个统一产品合同。

为什么这是游戏设计问题：
社区传播依赖“我敢分享”。如果分享 replay 会泄露基地布局、资源余额、未来策略、隐藏敌情，老玩家会关闭分享；如果分享内容太安全又不好看，传播价值下降。

建议：
- 增加 Replay Visibility Presets：
  1. Self Debug：完整自身视角 + 错误细节，仅自己可见。
  2. Safe Share：仅已公开/已过期情报，隐藏资源余额和未暴露单位。
  3. Arena Public：赛后全知，按房间 visibility 公开。
  4. Caster Mode：延迟观战 + fog toggle + 不显示未公开代码。
- 为 World replay 明确默认：公开分享只能是 safe share，不应默认全知。

### G6 — Low — 长期目标列表方向正确，但“可炫耀的身份层”仍偏弱

问题：
长期目标系统已经列出殖民地年龄、GCL/RCL、Arena 段位、PvE 里程碑、Replay/观战声誉。但这些多数仍是系统指标，不一定形成玩家身份表达。

为什么这是游戏设计问题：
可编程游戏的强社区动力来自“某个玩家/团队以某种算法风格闻名”：最省 fuel、最强防守、最优物流、最漂亮 replay、最离谱一行代码 bot。单纯 GCL/房间数不足以支撑这种身份。

建议：
- 增加 non-resource reputation：Strategy Tags、Replay Collections、Bot Lineage、Algorithm Hall of Fame、Fuel Efficiency Medals。
- 这些不改变经济，不破坏公平，但能显著提升社区传播与长期归属感。

---

## Missing

1. MCP resources 的“最小自举包”缺失统一定义。
   - 应有一个 AI 第一次连接后只靠 resources/list + resources/read 或 swarm_get_docs 就能拿到的 tutorial bundle：规则摘要、SDK 获取、最小 bot、错误码解释、dry-run 示例、部署后反馈事件。

2. 教程世界与正式 World 的迁移奖励/风险边界还不够清楚。
   - 已有 Tutorial 世界默认放宽规则，但需要明确：教程产出是否完全不可带出？starter bot 如何一键迁移？迁移后是否保留 replay/成就？

3. World 模式的社区发现入口仍弱。
   - Arena 有房间列表、赛后 replay、PvE 排行榜；World 目前更像“自己玩自己的殖民地”。可以补：公开殖民地名片、世界事件 feed、附近冲突摘要、可订阅玩家/房间。

4. Replay 与代码版本的绑定关系需要产品化呈现。
   - TickTrace 有 module_hash，但玩家看到 replay 时应能知道：这是哪个 bot 版本、是否公开源码、是否可 fork、是否可挑战。

5. “新玩家被老玩家影响”的情绪保护还可以更明确。
   - 文档有 safe_mode、soft_launch、安全区出生、SpawnGrace，但缺少失败后恢复路径：基地被毁后如何重建、是否推荐 Arena 练习、是否展示“你输了但学到了什么”的报告。

---

## Fresh Ideas

1. Replay as Resume：玩家主页展示“代表作 replay”而不是只展示 GCL。
   - 例如：Best Defense、Fastest Guardian Clear、Lowest Fuel Victory、Most Forked Bot。

2. Bot Lineage / Fork Graph：允许玩家公开某个 bot 的策略谱系。
   - “这个塔防 bot fork 自 basic-harvester v3，加入了 kiting 与 fuel-aware pathing。”
   - 对开源社区传播很强，也符合 Swarm 的代码文化。

3. First Blood / First Fix Moments：首小时重点奖励“修好一个 bug”而不是只奖励“打赢”。
   - AI 和人类都可以收到：你的 OutOfRange 错误已连续 20 tick 不再出现。
   - 这把调试也变成成就感来源。

4. Caster Packet：每场 Arena 自动生成一份可分享战报。
   - 包含关键 tick、经济曲线、命令成功率、转折点、双方 bot 版本 hash。
   - 不需要立即做视频，只要战报卡 + replay deep link 就能传播。

5. Practice Ghosts：Arena PvE/练习模式可加载公开 replay 的“幽灵对手”。
   - 玩家不是直接复制对手代码，而是对抗其历史 command trace 或行为模型。
   - 既保护源码，又提供可学习目标。

6. AI Onboarding Contract Test：把 AI agent 当作玩家做自动验收。
   - CI 中启动一个最小 MCP client，只给它 resources 和 schema，要求它完成 fetch SDK → build starter → validate → deploy → explain_last_tick。
   - 这是验证“AI 仅靠 MCP resources 能学会怎么玩”的最直接方式。

---

## CrossCheck

- 只读范围：本评审仅基于任务允许的 8 个文件：design/README.md、design/gameplay.md、design/modes.md、design/interface.md、specs/reference/api-registry.md、specs/gameplay/06-feedback-loop.md、specs/gameplay/08-api-idl.md、specs/core/09-snapshot-contract.md。
- 未读取 /data/swarm 下代码仓库，未读取旧评审，未读取 reviews/。
- 权威单源闭合性结论：未完全闭合。最主要断点是 MCP onboarding 工具名、RejectionReason/错误提示命名、dry-run/simulate/explain 工具命名、Arena 胜利条件、MVP 经济边界。
- 设计阶段结论：不要求按实现阶段拆分；从完整设计可玩性看，核心方向可接受，但必须先修复上述权威合同冲突，否则 AI 玩家自举、教程、SDK、Replay 解释会在产品体验上互相打架。
