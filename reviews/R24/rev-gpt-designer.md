# R24 GPT-5.5 Game Designer Review — spec ↔ design 对齐检查

Reviewer: rev-gpt-designer
Focus: 游戏设计、首小时体验、AI onboarding、旁观/回放/传播、长期追求
Verdict: CONDITIONAL_APPROVE

## Verdict

CONDITIONAL_APPROVE。R24 文档整体方向已经能支撑“代码就是军队”的核心体验：MCP 不做 gameplay action、AI 与人类同走 WASM、World/Arena 双模式、Replay/观战、soft_launch、PvE Challenge、长期目标等关键设计都存在。但 specs 与 design 之间仍有几处会直接影响新玩家/AI agent 学会怎么玩、Arena 产品形态、社区传播和 World 社交心理预期的未对齐点。

这些问题不要求重写核心设计，但需要在下一轮 closure verification 前统一权威口径，否则实现者可能按 spec 做出与 design 产品承诺不同的体验。

## Strengths

1. 首小时路径已从“编程沙盒”变成“可完成的体验闭环”
   - design/gameplay.md §1 定义 10 分钟 Golden Path。
   - specs/gameplay/06-feedback-loop.md §2.1-2.5 进一步给出 human/AI onboarding、starter bot、first-hour 过渡和 CI 验收。

2. AI 玩家公平性合同清晰
   - design/interface.md §4.2 明确 MCP 不做游戏动作。
   - specs/security/03-mcp-security.md §1、§4.5 同步声明 AI 必须写 WASM。
   - specs/reference/mcp-tools.md §明确不在 MCP 中 也排除了 move/attack/build/spawn。

3. Arena 与 World 的心理定位有差异化
   - design/modes.md §9 将 World 定义为 7x24 有机沙盒，Arena 定义为限时算法对局。
   - 玩家可在 Arena 用多个 WASM 自我对抗，这是非常适合 AI/算法社区传播的亮点。

4. Replay/观战已经被放进核心体验，而不是事后功能
   - design/modes.md §9.1.4 定义赛后回放、公开/私有可见性。
   - specs/gameplay/06-feedback-loop.md §5.3 定义回放查看器、fog-of-war 切换、解说覆盖层。

## Concerns

### G1 — High — AI onboarding 所需三件套在 security spec 中被标为“已移除”

位置:
- design/interface.md §4.1a / §4.2 / §5.3
- specs/gameplay/06-feedback-loop.md §2.2、§2.5、§3.1
- specs/reference/api-registry.md §3.2 Onboarding + Play
- specs/security/03-mcp-security.md §4.3-4.4

冲突描述:
- design/interface.md 说 MCP capability profiles 包含 onboarding/play/deploy/debug，并把 `swarm_get_docs`、`swarm_get_schema`、`swarm_get_available_actions` 作为 AI agent 学习世界/API 的关键工具。
- specs/gameplay/06-feedback-loop.md §2.2 明确 AI 教程流程第 2-3 步调用 `swarm_get_available_actions` 与 `swarm_get_docs`；§2.5 验收标准要求 `swarm_get_schema -> swarm_get_docs -> swarm_get_available_actions` 三次调用全部成功。
- api-registry.md §3.2 确实注册了 `swarm_get_docs`、`swarm_get_schema`、`swarm_get_available_actions`。
- 但 specs/security/03-mcp-security.md §4.3 写“已移除的旧工具：`swarm_explain_last_tick`（替换为 `swarm_get_tick_trace`）”；§4.4 又写“已移除的旧工具：`swarm_get_schema`、`swarm_get_docs`、`swarm_get_available_actions`（已整合至 SDK 和 API Registry）”。

为什么这是游戏设计问题:
AI 玩家是否能“仅通过 MCP resources/tools 学会怎么玩”是 Swarm 的核心差异化。若 security spec 被实现者视为安全权威并移除这些工具，AI onboarding 会断裂：agent 无法发现 schema、无法读规则、无法询问当前可用动作，只能依赖外部文档或人工提示。

修正建议:
以 api-registry.md + feedback-loop 为准。修改 specs/security/03-mcp-security.md：
- 删除“已移除 `swarm_get_schema` / `swarm_get_docs` / `swarm_get_available_actions` / `swarm_explain_last_tick`”的说法。
- 改为“这些工具存在，但按 API Registry 的 scope/rate_limit/profile 执行授权”。
- 若安全侧希望限制 debug 细节，应限制返回 detail_level，而不是移除 onboarding 工具。

### G2 — High — Arena 产品模型在 design 中是“房间制”，spec/API 却偏向“锦标赛制”

位置:
- design/modes.md §9.1.1-§9.1.4
- specs/gameplay/06-feedback-loop.md §6 Arena 模式
- specs/reference/api-registry.md §3.2 Arena
- specs/reference/game_api.idl.yaml §mcp_tools Arena

冲突描述:
- design/modes.md 定义 Arena 为房间制：创建房间、设置地图/时长/初始资源/可见性、分配槽位、房主点击开始、比赛结束生成回放。
- 同一玩家可占据多个槽位，自我对抗测试策略，这是非常具体的 UX 设定。
- 但 api-registry.md Arena 工具只有 `swarm_tournament_create`、`swarm_tournament_precommit`、`swarm_tournament_status`、`swarm_match_result`，没有 `arena_create_room`、`arena_join_slot`、`arena_start_room`、`arena_list_rooms`、`arena_get_replay` 等房间制所需 API。
- specs/gameplay/06-feedback-loop.md §6 又写“锦标赛分组、赛季”，比 design/modes.md §9.1 的“无自动匹配、无天梯排名、无赛季”更偏赛事化。

为什么这是游戏设计问题:
房间制与锦标赛制是不同首小时入口：
- 房间制支持“我拿两个 bot 自测一下”，低门槛、适合开发者迭代。
- 锦标赛制支持组织活动，但门槛更高。
若 spec 只实现 tournament API，Arena 的核心 UX 会偏离 design 的“算法 playground”。

修正建议:
二选一并统一：
A. 保留 design 房间制为 MVP：在 IDL/API Registry 增加 Arena Room lifecycle 工具，并把 tournament 标为 future/admin layer。
B. 若 Arena MVP 改为 tournament-first：更新 design/modes.md §9.1，删除房主房间/多槽位自测/无赛季等承诺。
推荐 A。房间制更符合第一小时体验和社区自传播。

### G3 — Medium — World “无排行榜”与公开 leaderboard/API/visibility 冲突

位置:
- design/gameplay.md §Vanilla Ruleset 核心默认值表
- design/modes.md §9 World vs Arena 表
- specs/reference/api-registry.md §3.2 Play `swarm_get_leaderboard`
- specs/security/05-visibility.md §2.6、§6
- specs/security/03-mcp-security.md §2.5

冲突描述:
- design/gameplay.md 明确“World 模式无排行榜；Arena 模式通过 `swarm_get_world_stats` 提供段位统计”。
- design/modes.md 说 World 不追求公平、无胜利条件，Arena 才追求竞技公平。
- api-registry.md 却暴露 `swarm_get_leaderboard`，返回 `{player, gcl, rooms, drones}`，未标注 Arena-only 或 “showcase-only”。
- specs/security/05-visibility.md §2.6 定义 `LEADERBOARD: 公开。指标: GCL、房间数、drone 数`；§6 Public 也包含“排行榜”。
- specs/security/03-mcp-security.md §2.5 spectator 事件流也含“公开排行榜”。

为什么这是游戏设计问题:
World 如果出现 GCL/房间/drone 排行榜，玩家心理会从“沙盒长期经营”转向“追榜竞赛”。这会放大先发优势焦虑，削弱 design 中 soft_launch 与 anti-snowball 的心理保护。

修正建议:
把公开排名拆成两类：
- Arena leaderboard/rating：正式竞技排名，可公开。
- World showcase/world_stats：非排序或分桶展示，如“殖民地年龄段、公开 replay、精选策略、世界事件贡献”，避免全服 GCL 排行。
API 上可将 `swarm_get_leaderboard` 限定为 `mode=arena`，World 使用 `swarm_get_world_showcase` 或在字段中明确 `ranking=false`。

### G4 — Medium — Tutorial / Golden Path 默认资源与权威 starting resources 不对齐

位置:
- design/gameplay.md §1 Golden Path
- design/gameplay.md §Official Vanilla Swarm Ruleset
- specs/reference/api-registry.md §5.1
- specs/core/08-resource-ledger.md §新玩家/starting resources（间接权威，见 Registry 引用）

冲突描述:
- design/gameplay.md §1 说 Tutorial 世界登录后“自动获得初始 Energy”，但未给出数值。
- design/gameplay.md Vanilla Ruleset 表未列新玩家初始资源包。
- api-registry.md §5.1 权威限制写 `Starting resources = {Energy: 5000, Minerals: 2000}`。
- design/gameplay.md 资源默认又说默认世界单一 `Energy`，可扩展多资源；这与 `Minerals: 2000` 在默认包中同时出现会让新手教程和 starter bot 的资源假设不清。

为什么这是游戏设计问题:
10 分钟 Golden Path 高度依赖初始资源是否足以 spawn/build/repair。若 starter bot 假设 Energy-only，而 spec 给出 Energy+Minerals，教程世界可能出现“文档说可跑，实际缺某资源/多出陌生资源”的认知噪音。

修正建议:
在 design/gameplay.md §1 或 Vanilla Ruleset 表中明确：
- Tutorial starting_resources 与 World starting_resources 是否相同。
- Vanilla 是否真的是 Energy-only；若是，则 `Minerals` 应改为 future/modded 示例。
- starter bot CI 使用哪个 world profile 的 starting resources。

### G5 — Medium — Feedback-loop spec 中 Arena 胜利条件与 design/modes 不一致

位置:
- design/modes.md §9 表、§9.1.3
- specs/gameplay/06-feedback-loop.md §6 Arena 模式

冲突描述:
- design/modes.md 定义 Arena 终止条件优先级：一方 drone=0 > 一方认输 > tick 到上限按剩余资产判定（drone数 → 建筑数 → 资源量） > 平局。
- specs/gameplay/06-feedback-loop.md §6 写 Arena 胜利条件为“摧毁敌方 Spawn，或时限结束时分高者胜”。

为什么这是游戏设计问题:
这会改变玩家写 bot 的目标函数：
- drone=0 优先鼓励机动/击杀策略。
- 摧毁 Spawn 优先鼓励 base-rush。
- 剩余资产判定与“分数”判定也会导致不同 meta。

修正建议:
以 design/modes.md 的具体优先级为准，或在 modes 中改成 Spawn-based。建议保留 design/modes.md 的多层判定，并在 feedback-loop 中引用它，避免 starter bot 和 PvE Challenge 评分混淆 Arena PvP 胜负。

## Missing

1. 缺少 AI-only MCP 自举验收的“资源形态”定义
   - 已有 `swarm_get_docs`/`schema`/`available_actions`，但没有明确 MCP resources URI 清单与最小教程内容包的权威位置。
   - 建议新增 `specs/reference/onboarding-resources.md` 或在 API Registry 中列出 `swarm://docs/tutorials/basic-agent`、`swarm://docs/api-reference` 的 schema/version/hash。

2. 缺少 Replay 分享的隐私分级 API
   - design/modes.md 与 feedback-loop 有 Replay/分享/观战概念。
   - API 只看到 `swarm_get_replay` 与 `swarm_match_result.replay_url?`，缺少“生成公开 safe view URL / unlisted link / fog-of-war view mode”的明确 mutation 或 policy。

3. 缺少 World 非排行榜的社区传播替代品
   - design 想避免 World 排行榜，但 spec 多处仍写 leaderboard。
   - 需要正面定义 World 的“可传播对象”：Replay highlight、殖民地 tour、战报卡、PvE 事件贡献、策略说明页等。

## Fresh Ideas

1. “Agent First Run Certificate”
   - AI agent 完成首次 `schema -> docs -> validate -> deploy -> first_tick_executed -> explain_last_tick` 后，生成一张本地/公开可分享的 onboarding badge。它不影响经济，但能促进 AI 社区传播。

2. Arena Room Share Card
   - 每个 Arena room/match 自动生成一张战报卡：地图 seed、双方 module hash、关键 tick、胜负原因、replay link。比传统 leaderboard 更适合开发者社区讨论。

3. World Showcase 不排序，只聚类
   - World 不显示“第 1 名”，而显示“本周最老殖民地 / 最远探索 / 最精彩防守 replay / 最低资源通关 PvE challenge”。降低先发优势焦虑，同时保留传播性。

4. MCP “What can I do next?” composite resource
   - 在 `swarm_get_available_actions` 之外增加 tutorial-oriented docs topic：根据当前 snapshot 返回下一步学习建议，但保持只读，不做 gameplay action。AI agent 可用它降低首小时迷路率。

## Summary

R24 从游戏设计角度可以 conditional approve，但建议 Gate 修复 G1/G2/G3：
- G1 直接影响 AI 是否能自举学习。
- G2 决定 Arena 是开发者 playground 还是赛事后台。
- G3 决定 World 玩家心理是沙盒经营还是排行榜竞赛。

G4/G5 可作为 Medium 在同一轮顺手对齐。完成后，Swarm 的“第一小时 + AI 自举 + replay 社区传播”合同会更稳定。