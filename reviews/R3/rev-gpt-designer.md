# R3 Game Design Review — rev-gpt-designer

## Verdict

APPROVE_WITH_RESERVATIONS.

Swarm 的核心幻想很强："你的代码就是你的军队"，并且 R2 后已经修正了 MCP 公平性、Arena 房间制、Replay/旁观、AI 教程等关键方向。它现在看起来不只是 Screeps 技术翻新，而是一个面向人类程序员与 AI agent 的 programmable strategy platform。

但从游戏设计角度，最大风险仍然不是技术可行性，而是首小时可玩性与长期目标结构：文档已经列出许多系统，但玩家第一次成功获得 fun 的路径仍偏长，World 模式的中后期追求仍容易退化成 GCL/房间数/效率仪表盘，社区传播点也需要更产品化的 Replay/挑战/模板机制。

## Strengths

1. 核心定位清晰且差异化

- "世界只认 WASM" 是非常强的公平性与品牌主张。
- AI 和人类走相同路径，避免了 AI-only shortcut 破坏竞技合法性。
- WASM + 多语言 SDK 比 Screeps 的 JS-only 更符合 2026 年玩家/AI 生态。

2. MVP feedback loop 已经被正确识别

specs/06 把 Learn → Decide → Act → Understand 明确写成 MVP 闭环，这是非常正确的设计抓手。尤其是：

- 5 分钟教程
- starter bot
- swarm_explain_last_tick
- dry-run
- replay viewer
- strategy dashboard

这些比新增战斗机制更重要，因为 programmable game 的最大流失点通常是「我不知道为什么没动」。

3. Arena 房间制是正确裁决

不做自动匹配/天梯，改成房间制，显著降低 MVP 复杂度，并更贴合算法对抗：

- 同一玩家部署多个算法自我对抗
- map_seed 可复现
- 赛后自动 Replay
- public/unlisted/private 分享

这会让 Arena 成为调试、展示、教学、社区挑战的天然容器，而不是过早背负电竞匹配系统。

4. 旁观/Replay 方向有传播潜力

文档已经包含：

- 公开/私有回放
- spectator delay
- fog-of-war toggle
- 解说覆盖层
- Arena 赛后公开回放

这正是代码竞技游戏最需要的"观众层"。Screeps 一直难传播，核心原因之一是战斗过程缺乏可解释、可分享的短内容。

5. World Rules Engine 给长期生命力留出了空间

world.toml + mods.lock + i18n 让 Swarm 有机会成为"可编程策略游戏引擎"而不是单一规则游戏。服主可以创造：

- Tutorial 世界
- Novice 世界
- 高速 Arena 世界
- 硬核物流世界
- PvE Boss 世界
- 资源衰减/帝国维护/特殊攻击 Mod 世界

这对社区服和长期留存很关键。

## Concerns

### G1 — 首小时仍可能过载：玩家需要同时学习游戏、SDK、WASM、调试、策略

当前首小时路径是：启动环境 → 选 SDK → 写 bot → 编译 WASM → deploy → 看 tick → debug。对资深程序员可接受，对普通好奇玩家和 AI agent 也许仍太长。

尤其 GETTING-STARTED 的第一个 bot 示例存在体验风险：它展示了 spawn 与 harvest，但没有完整闭环到 carry/transfer/build/controller upgrade。玩家看到 drone 采集一次后，下一步 fun 不够明确。

建议首小时目标改成更强的三个明确 milestone：

1. 5 分钟：第一个 drone 出生并成功采集。
2. 15 分钟：自动往 Spawn/Storage 运回 Energy，资源数字增长。
3. 45 分钟：建出第一个 Extension 或 Tower，视觉上看到基地变强。

必须让玩家在第一小时内看到"我的代码造成了可见的世界变化"，否则 programmable game 会变成文档阅读考试。

### G2 — AI 玩家仅靠 MCP resources 能否学会：方向对，但缺少机器可执行学习路径定义

specs/06 写了 MCP 教程资源 `swarm://docs/tutorials/basic-agent`，MCP spec 也有 `swarm_get_docs`, `swarm_get_schema`, `swarm_get_available_actions`。这满足了概念层面的 learnability。

但从 AI agent 实际行为看，还缺少三个关键资源：

- 最小可部署项目模板：包括目录结构、build command、wasm target、manifest、签名/部署参数。
- 错误恢复 playbook：validate_module 失败、deploy 被拒、tick 无动作、fuel 超限、指令全 rejected 时，下一步应该调用什么。
- 自检任务清单：AI 能调用一个 resource 得到 checklist，例如 "compile → validate → deploy → wait 3 ticks → explain_last_tick → profile"。

如果这些只在自然语言 docs 中，强模型能学会，弱 agent 会卡住。建议 MCP resources 提供 structured tutorial manifest，而不只是 markdown。

### G3 — MCP `swarm_get_available_actions` 可能误导：它不应像"当前可直接执行动作"，而应强调 SDK/API capability

文档中 `swarm_get_available_actions` 的描述是："我现在能做什么？返回当前状态下的可能动作列表"。但 MCP 明确不能直接提交 move/build/attack。若名字和返回内容设计不慎，AI agent 容易以为 MCP 下一步能执行这些动作。

建议改名或分层：

- `swarm_get_sdk_capabilities`：当前世界支持哪些 CommandAction/body part/custom action。
- `swarm_analyze_possible_commands(snapshot)`：给定 snapshot，返回可在 WASM 中生成的候选 command，不是 MCP 可执行动作。

返回结构中必须明确：`execution_channel: "wasm_tick_return_only"`。

### G4 — Long-term chase 仍偏传统：GCL、房间数、效率指标之外，需要更多玩家身份与收藏目标

当前长期目标包括：GCL、房间数、殖民地年龄、资源效率、Arena 回放、世界规则。它们都合理，但容易只吸引 optimization 玩家。

缺少能让玩家产生身份认同和社区话题的追求：

- 策略谱系：我的 bot 从 v1 到 v20 的 lineage、关键胜利、失败学习。
- 可展示殖民地风格：基地布局、命名、旗帜、视觉主题、公开 profile。
- 成就/徽章：第一个自动防御、第一个跨房间补给线、百 tick 零 rejected command。
- Bot archetype 收藏：harvester, defender, raider, logistician, scout 等官方识别标签。
- Arena puzzle medals：在固定 seed challenge 中达到 S/A/B 评级。

程序员也需要"我是谁"，不只是"我的吞吐率是多少"。

### G5 — World 模式的老玩家优势虽被承认，但新手社会空间还不够

文档明确 World 不追求公平，并提供 safe_mode、密度优先出生、respawn policy。这是对的。但持久 PvP 世界的最大留存风险是：新手无法判断自己是否在进步，或被老玩家生态压制后离开。

建议补充：

- Novice shard：账号创建后前 N 天只能进，或只能被同龄玩家攻击。
- Mentor/Alliance discovery：新手能找到愿意共享 starter bot 和 replay 评论的社群。
- PvE contracts：即使不参与 PvP，也能通过自动化物流/防御/采集获得目标。
- Graceful defeat：殖民地被打爆后自动生成"失败诊断 Replay"，告诉玩家被哪类策略击败。

### G6 — 战斗特殊攻击很丰富，但可能在 MVP 中压垮可读性

Hack/Drain/Overload/Debilitate/Disrupt/Fortify/Leech/Fabricate 很有想象力，但对首版 meta 来说机制密度偏高。R2 已裁决 Vanilla 分层、Tutorial/Novice 禁用特殊攻击，这是正确方向。

仍建议把 MVP 的 public narrative 聚焦到：采集、建造、防御、扩张、Arena 对抗。特殊攻击先作为 Advanced world 的卖点，而不是新手文档主轴。

### G7 — Replay/观战有基础，但缺少"一键分享成内容"的产品规格

现有 Replay viewer 是完整工具，但社区传播通常需要更短链路：

- 复制链接
- 自动裁切 highlight tick range
- 生成 30 秒 GIF/video
- 带标题、玩家名、seed、规则集、胜负摘要
- 可嵌入论坛/社交平台

如果只有完整 replay JSON/播放器，传播半径会小很多。需要明确 highlight artifact 是一等公民。

### G8 — 本地模拟是强功能，但需要防止玩家陷入离线过拟合

`swarm sim --ticks=5000 --speed=100x` 很重要。但 Arena/World 的乐趣不应变成只在本地跑 optimization benchmark。

建议引入：

- hidden validation seeds
- public challenge seeds + private scoring seeds
- strategy robustness score
- "beat 7/10 maps" 而非 "beat this one seed"

否则社区会快速出现 seed-specific exploit bot，降低观看和参与乐趣。

### G9 — 教程 bot 可编辑是好设计，但需要"失败也有趣"的教学文案

Programmable games 中最常见体验不是成功，而是：bot idle、路径卡住、资源满了不运、spawn 失败、range 不够。specs/06 已有 why idle debug，这是关键。

建议把失败态做成教程主线的一部分：

- 故意给一个少 WORK part 的 drone，让玩家看到 explain 说"无 WORK 身体部件"。
- 故意让 harvest out of range，提示 move。
- 故意让 carry full，提示 transfer。

这样玩家学到的是调试循环，而不是复制正确答案。

## Missing

1. 首小时体验脚本

需要一份明确的 `FIRST-HOUR.md` 或 tutorial spec，逐分钟定义：玩家看到什么、改哪一行代码、预期世界反馈是什么、失败时如何恢复。

2. MCP structured learning resources

建议定义 MCP resources：

- `swarm://tutorials/basic-agent/manifest.json`
- `swarm://templates/typescript/basic-harvester`
- `swarm://templates/rust/basic-harvester`
- `swarm://playbooks/debug/no-actions`
- `swarm://playbooks/debug/rejected-commands`
- `swarm://checklists/deploy-loop`

3. Strategy lineage/profile

缺少 player/bot profile 的设计：版本历史不仅是 rollback，也应是玩家对外展示资产。

4. Community challenge model

Arena 房间制很好，但还需要官方/社区 challenge：固定 ruleset + seed pool + scoring function + leaderboard/medals。否则 Arena 只是私人测试房。

5. Replay highlight/export spec

Replay viewer 之外，需要"短内容导出"。这会直接影响社区传播。

6. Newbie social/protection layer

safe_mode 不等于留存。需要 Novice world、mentor link、失败诊断、友好 PvE 目标。

7. Bot marketplace / template gallery 的非中心化版本

文档拒绝中心化 mod market 是合理的，但 starter bot/template discovery 仍需要入口。可以是 curated examples，不必是完整市场。

## Fresh Ideas

1. Daily Puzzle Seeds

每天生成 3 个官方 challenge：

- Harvest Sprint：500 tick 内采集最多 Energy。
- Tower Defense：抵御 scripted wave。
- Logistics Knot：在拥挤地形中最大化 throughput。

玩家提交 WASM，系统跑 hidden seeds，给 medal。这个比早期天梯更适合传播和学习。

2. Replay Postcard

每场 Arena 自动生成一张 share card：

- 地图缩略图
- 双方 bot 名称
- 关键 tick：first contact、first kill、spawn destroyed
- 30 秒 highlight URL
- seed/ruleset hash

目标是让玩家愿意发到群里，而不是只分享长 replay。

3. Bot Lineage Tree

每次 deploy 形成版本节点：

- parent module hash
- 关键指标变化
- 首次击败哪个 opponent/seed
- 回滚点

玩家 profile 展示 bot 的演化树，强化长期身份感。

4. Explain-as-Coach

`swarm_explain_last_tick` 可以有两种模式：

- raw：结构化 rejection/state changes。
- coach：面向新手/AI 的下一步建议。

AI agent 可用 raw，人类教程用 coach。两者共享事实来源，避免幻觉。

5. Ghost Opponents

从公开 Arena replay 中抽取历史 bot 作为 ghost opponent。新玩家可挑战：

- 官方 starter ghost
- 社区热门 ghost
- 自己旧版本 ghost

这比实时 PvP 更低压力，也天然使用 replay/module archive。

6. Strategy Tags 自动识别

根据行为指标自动给 bot 打标签：

- turtle defender
- rush attacker
- logistics optimizer
- scout-heavy
- economy-first

这些标签用于 profile、match room、replay 搜索和社区讨论。

7. Onboarding Contract for AI Agents

提供一个 machine-readable contract：

```json
{
  "goal": "deploy_basic_harvester",
  "steps": [
    {"call": "swarm_get_docs", "resource": "tutorial/basic-agent"},
    {"call": "swarm_get_schema"},
    {"build": "template:typescript/basic-harvester"},
    {"call": "swarm_validate_module"},
    {"call": "swarm_deploy"},
    {"wait_ticks": 3},
    {"call": "swarm_explain_last_tick"}
  ],
  "success_predicates": [
    "module.status == active",
    "commands_accepted > 0",
    "energy_delta >= 0"
  ]
}
```

这能让普通 AI agent 不靠大模型推理也能完成第一次入门。

8. Community Replay Annotations

允许玩家在 replay tick 上添加评论：

- "这里 pathfinding 卡住了"
- "这个 tower timing 很漂亮"
- "v12 比 v11 多了 scout，所以提前发现 rush"

这会把 replay 变成教学内容，而不只是录像。

9. Soft Goals for World Mode

World 模式不做公平排名，但可做非竞争展示：

- Oldest colony still alive
- Most efficient 1000-tick window
- Best recovery after wipe
- Most compact base
- Most readable public bot writeup

这些目标降低纯 GCL 统治，鼓励多种玩家动机。

10. "No Code Yet" Viewer

让未登录访客可以打开 public Arena replay 或 sample world，先看 bot 战斗，再决定是否写代码。对 programmable game 来说，先看到结果再要求写代码，转化率会高很多。

## Final R3 Position

Swarm 的 R3 设计已经足够进入实现/产品原型阶段，但 Game Design 侧建议把下一轮重点从"更多系统"转为"更短的 fun loop、更强的可解释性、更可分享的 replay、更机器可读的 AI onboarding"。

若这些补齐，Swarm 有机会同时抓住三类人：

- 程序员：写策略、调效率、看指标。
- AI agent 玩家：通过 MCP 学习、部署、迭代。
- 旁观/社区用户：看 Arena、分享 replay、挑战 puzzle。

不要让它只成为 Screeps with WASM；应把它做成 programmable strategy 的 GitHub + YouTube + training arena。