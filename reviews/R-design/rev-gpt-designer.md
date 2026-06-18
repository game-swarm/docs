# R-design Clean-Slate Review — Game Designer / UX / Community

Reviewer: rev-gpt-designer (GPT-5.5)
Verdict: CONDITIONAL_APPROVE

## Verdict

CONDITIONAL_APPROVE.

这套设计已经具备一个有吸引力的“可编程 MMO RTS 平台”骨架：WASM 同权、World/Arena 双模式、可配置 ruleset、Replay/观战、PvE 生态、经济仪表盘和 AI MCP 接口都覆盖到了。作为设计阶段方案，我认为方向值得继续推进。

但从游戏设计与首小时体验看，它仍需要在“玩家如何第一次获得乐趣”“AI agent 仅靠 MCP resources 能否自举”“社区传播如何形成内容循环”“官方默认体验如何避免被配置复杂度淹没”四个方面收口。当前最大风险不是机制不够，而是机制太多、入口太硬、缺少一条强制验证过的 onboarding golden path。

---

## Strengths / 亮点

1. **“世界只认 WASM”是正确且强的核心承诺**
   - 人类与 AI 玩家同走编写代码、编译 WASM、部署模块的路径，避免了“AI 有特殊 API/作弊入口”的公平性裂缝。
   - MCP 被定位为观察、部署、调试、学习界面，而不是游戏动作控制器，这是设计上非常重要的清晰边界。

2. **World + Arena 双模式互补**
   - World 承接 MMO 沙盒、长期资产、社交与涌现玩法。
   - Arena 承接公平对战、算法实验、可展示的短局、PvE Challenge 和公开 replay。
   - 这能解决 Screeps 类游戏常见问题：持久世界对新人不公平，但短局竞技可以给新人和社区传播一个干净入口。

3. **可观战、Replay、TickTrace 与确定性回放是社区传播的基础设施**
   - 设计把 replay 放在核心数据模型而非事后补丁，这是对编程竞技类游戏非常关键的决定。
   - Arena 赛后公开 replay、tick 定位、双视角切换、指令展开，都非常适合教学、晒战术、做内容创作。

4. **经济反馈与可视化意识很好**
   - 经济仪表盘、drone efficiency、趋势、告警、特殊效果可视化，能把“代码在做什么”转化成人能理解的反馈。
   - 对编程游戏来说，反馈闭环比机制数量更重要；这里已经有正确方向。

5. **PvE 生态层能降低纯 PvP 冷启动压力**
   - NPC、资源据点、世界事件、PvE Challenge 给了玩家在被老玩家压制前也能玩起来的目标。
   - “PvE 是地理属性而非副本入口”的设计和持久世界契合。

6. **Vanilla Ruleset + world.toml 扩展的分层思路合理**
   - Layer 1/2/3 的划分能避免所有服务器都变成不可学习的魔改世界。
   - SDK manifest hash 与 world-specific SDK 能从系统层面防止“玩家用错 API 写错世界”。

7. **长期追求已经不只 GCL/RCL**
   - 文档中已有殖民地年龄、Arena 段位、PvE 里程碑、Replay/观战声誉、外交、模组世界等方向。
   - 这些能支撑多种玩家类型：优化党、竞技党、社交党、创作型服主、AI agent 实验者。

---

## Concerns / 发现的问题

### G1 — High — 首小时体验仍过硬：缺少可验证的“10 分钟有趣”路径

当前设计描述了注册、CSR、PoW、SDK 获取、WASM 部署、tick snapshot、Command 模型、经济与世界规则，但没有把新玩家第一小时拆成明确的 playable funnel。

风险：
- 新玩家进入后可能先遇到认证、SDK、编译、WASM、世界规则、资源物流、fog of war，而不是“我的第一个 drone 动起来了”。
- “Move 占用 action slot”是有意设计，但首小时如果没有强引导，会被误解为游戏迟钝或代码没生效。
- Tutorial 世界被提到，但没有定义任务梯度、成功条件、默认 bot、失败解释与从 Tutorial 迁移到 World/Arena 的路径。

建议：
- 增加官方 First Hour spec：
  1. 0–5 分钟：无需本地工具链，用 Web/AI 生成 starter WASM，让第一个 drone harvest。
  2. 5–15 分钟：修改一行策略，让 drone 在 Harvest/Transfer/Spawn 中形成循环。
  3. 15–30 分钟：引入 Move-as-action、fatigue、RCL、存储。
  4. 30–60 分钟：进入 Arena PvE Challenge 或小型 Tutorial World。
- 每一步必须有：目标、默认代码、可视化反馈、常见失败解释、MCP 等价流程。

### G2 — High — AI-only MCP onboarding 还不是闭环

设计列出了 `swarm_get_docs`、`swarm_get_schema`、`swarm_sdk_fetch`、`swarm_get_available_actions`、`swarm_explain_last_tick` 等工具，也在 auth.md 中列出 AI onboarding resource 名称。但仍缺少一个强合同：一个没有外部文档、只拿到 MCP resources 的 AI agent，能否完成“注册 → 获取 SDK → 生成代码 → 编译 WASM → validate → deploy → debug first tick”。

风险：
- MCP 工具存在不等于 agent 能学会玩。AI 需要任务化资源、示例、错误恢复、最小 bot 模板和 schema 之间的引用关系。
- 文档没有定义 MCP resources 的信息架构，例如 `docs/tutorial/first-drone`、`examples/ts/harvester-bot`、`schemas/command`、`recipes/debug-rejected-command` 是否可被统一发现。
- 如果 AI agent 需要离开 MCP 去网页/wiki 搜索，AI 原生入口就不成立。

建议：
- 增加 “MCP Learnability Contract”：
  - 从空上下文 agent 开始，只允许调用 MCP resources/tools。
  - 验收标准：60 分钟内完成 self-register、sdk fetch、compile、deploy、解释一次 rejected command 并修复。
  - 必备 resources：quickstart、starter bots、API schema、world rules、common errors、debug recipes、security/auth handoff。
- `swarm_get_docs` 应返回导航图，而非散文文档；每个 doc 节点应有 `next_steps`、`related_schema`、`example_code`。

### G3 — High — 特殊攻击 Tier 与默认规则存在自相矛盾

gameplay.md 多处说明：Tier 1 只有 6 种特殊攻击（Hack/Drain/Overload/Debilitate/Disrupt/Fortify），Leech/Fabricate 为 Tier 2+。但 README 导航写“特殊攻击（8 种）”，gameplay.md 后段又说默认 world.toml 预注册 8 个特殊攻击，并给出 Leech/Fabricate 的默认配置。

风险：
- 玩家、AI、SDK codegen、Arena 平衡和 Tutorial 教学会不知道官方 Vanilla v1 到底支持 6 种还是 8 种。
- 这直接影响首小时认知负荷与竞技公平。

建议：
- 冻结一个明确版本：Vanilla v1 = 6 种，Leech/Fabricate 只在 Tier 2/custom_actions 示例中出现；或 Vanilla v1 = 8 种，并删除 Tier 2+ 说法。
- README、Tier Entry Gate、Vanilla Ruleset 表、default world.toml 示例必须一致。

### G4 — Medium — 旁观/Replay 有基础，但社区传播闭环不足

Replay 数据、Arena 赛后公开、双视角、指令展开都很好，但仍偏“数据功能”，还没有形成“内容产品”。

缺口：
- 缺少可分享 replay URL、缩略图/战报卡片、关键 tick highlight、自动摘要。
- 缺少“策略页面”：某个 WASM 模块的版本、胜率、作者说明、公开源码/闭源标记、benchmark 历史。
- 缺少社区挑战：每周官方 Arena seed、PvE Challenge leaderboard、featured replay、best bot of the week。
- 没有说明 replay 的隐私策略如何转化为分享 UX：private/allies/world/public 对用户意味着什么。

建议：
- 把 Replay 设计提升为 Community Artifact：
  - replay permalink
  - tick highlight markers
  - auto-generated battle report
  - embed-friendly viewer
  - “fork this strategy”入口
  - AI-generated commentary 可选层

### G5 — Medium — 长期追求虽列出，但缺少“非扩张型成就”体系

文档已经有 GCL、RCL、殖民地年龄、Arena 段位、PvE 里程碑、Replay 声誉，但大部分仍围绕扩张、战斗、资源与排名。

风险：
- World 模式若无排行榜且不追求公平，需要更多非零和目标，否则长期玩家的默认目标会退化为扩张/压制/资源垄断。
- 非硬核玩家、创作者、教学者、服主、AI bot 作者需要被系统承认的成就类型。

建议：
- 增加长期目标矩阵：
  - Architect：高效基地蓝图、物流评分、低 fuel 策略。
  - Explorer：发现遗迹、绘制地图、公开 intel。
  - Scientist：发布可复用 bot library、SDK examples。
  - Diplomat：联盟稳定时长、贸易网络。
  - Curator：创建高评分 mod world / PvE scenario。
  - Performer：Replay 获赞、赛事解说、教学贡献。
- 避免全部奖励都变成数值优势；可以给 cosmetic、profile badge、replay framing、world listing 权重。

### G6 — Medium — 规则可配置性强，但官方默认体验需要更硬的产品边界

Swarm 是可配置平台，这很强；但从玩家角度，过度可配置会削弱“我正在玩 Swarm”的共同语言。

风险：
- 如果每个世界的资源、body part、特殊攻击、物流、mod 都不同，新玩家和 AI agent 难以迁移经验。
- 社区内容难以复用：一个攻略/Replay 可能只对某个 world manifest 有意义。
- 官方 Vanilla、Novice、Standard、Advanced 的边界目前还不够产品化。

建议：
- 定义 Official Track：Tutorial → Novice World → Standard World → Arena Standard，保证 API/规则长期稳定。
- Modded worlds 明确作为 Advanced/Experimental Track，UI 上显示兼容性、学习成本、SDK hash、是否参与官方展示。
- 对每个世界生成 “Rule Diff from Vanilla”，让人类和 AI 一眼知道差异。

### G7 — Medium — Debug UX 需要从“工具存在”升级为“代码-命令-世界状态闭环”

已有 `swarm_explain_last_tick`、rejections、TickTrace、Replay、可视化状态，这是好基础。但编程游戏真正的留存点在于玩家能快速回答：“为什么我的代码没有产生我想要的结果？”

缺口：
- 没有明确 source map / command provenance：某条 rejected command 来自哪段玩家代码、哪个 drone、哪个 decision branch。
- `swarm_dry_run_commands` 是命令级，不一定能解释从 snapshot 到 command 的策略错误。
- Replay 指令展开若不能链接到模块版本与代码行，会变成只给专家用的审计数据。

建议：
- 增加 Debug Timeline：snapshot input → player log → emitted commands → validation result → ECS effect → visual delta。
- SDK 支持 structured decision log，例如 `trace("harvester.choose_source", {...})`，受配额限制进入 TickTrace。
- Web UI 中点击 drone 可看到最近 N tick 的 action reason、rejected reason、fuel cost、source code span。

### G8 — Low/Medium — “Move = Action”是有趣选择，但需要官方新手解释与模式验证

我认可 Move 占用 action slot 的哲学：它会让预判、队列、阵型和路径规划更重要。但这会显著改变传统 RTS 手感，也会让 Screeps 玩家产生迁移误差。

风险：
- 首小时误读为卡顿。
- 早期采集循环更慢，反馈频率下降。
- 战斗观赏性可能呈现“追击或攻击二选一”的断续感，需要动画补偿。

建议：
- Tutorial 必须用可视化解释：本 tick 移动，next tick 采集。
- Arena/PvE Challenge 中设计一个专门关卡教预判移动。
- Playtest 指标：first harvest time、first successful spawn loop、因“drone 不动/不采集”触发 explain_last_tick 的比例。

### G9 — Low — 认证设计很完整，但对首小时有产品摩擦风险

auth.md 的证书/CSR/PoW/恢复/联邦设计非常完整，但它作为玩家入口可能压过游戏本身。

风险：
- 新玩家在理解游戏前先遇到 CA、CSR、certificate、PoW、device profile 等概念。
- AI agent 需要正确持久化 credentials，否则首小时会卡在安全流程。

建议：
- 玩家界面隐藏术语：显示 “Create account/device”、“Save recovery method”、“Deploy permission”，高级面板再显示证书细节。
- AI MCP onboarding 要把 credential persistence 作为自动 checklist，并提供 `swarm_auth_doctor` 或等价诊断工具。

---

## Missing / 缺失项

1. **First Hour / Tutorial 详细规格**
   - 任务列表、默认 starter code、失败恢复、成功指标、Web 与 MCP 两条路径。

2. **AI MCP 自举验收测试**
   - 明确“只通过 MCP resources 学会玩”的测试脚本与通过标准。

3. **Replay 社区产品层**
   - permalink、battle report、highlight、分享卡片、embed、fork strategy。

4. **官方规则轨道与 Rule Diff**
   - Vanilla/Novice/Standard/Advanced/Modded 的清晰产品边界。

5. **Debug provenance**
   - 从代码行/decision log 到 command rejection 再到 replay tick 的追踪模型。

6. **非扩张型长期成就系统**
   - 创作、教学、外交、探索、效率、模组贡献等声誉路径。

7. **Playtest 指标表**
   - 首次部署时间、首次有效 command、首次资源循环、首次 replay 分享、AI 自举成功率、Arena 复赛率等。

---

## Recommendations / 建议

1. **新增 `design/onboarding.md`**
   - 定义 Tutorial、First Hour、AI-only MCP onboarding、Web onboarding、失败恢复和指标。

2. **新增 `design/community.md` 或扩展 modes/gameplay**
   - 把 Replay、观战、挑战、排行榜、策略页面、分享卡片作为一个完整社区循环设计。

3. **修正特殊攻击 Tier 矛盾**
   - 统一 README、gameplay、Tier Entry Gate、default world.toml 示例。

4. **为 MCP resources 设计导航型信息架构**
   - `docs/quickstart/*`、`examples/*`、`schemas/*`、`recipes/debug/*`、`rules/current`，每个节点有机器可读 metadata。

5. **定义 Debug Timeline 合同**
   - command provenance、structured logs、source map、replay tick linking。

6. **把官方默认体验产品化**
   - “Official Standard World”和“Official Standard Arena”需要像卡牌游戏标准赛制一样稳定，modded worlds 作为可发现但明确分区的创作层。

7. **用 playtest gates 冻结关键争议机制**
   - Move-as-action、PoW 默认难度、soft_launch 时长、Arena tick 300ms、特殊攻击复杂度，都需要玩家行为数据验证。

---

## Fresh Ideas / 新想法

1. **Strategy Card / Bot Card**
   - 每个部署过的 WASM 模块生成一张卡：语言、manifest hash、版本、公开/私有、最近战绩、燃料效率、作者注释、可 fork 状态。

2. **Replay as Pull Request**
   - 玩家看完失败 replay 后，可以让 AI agent 生成“策略补丁建议”，以 diff 形式展示：为什么输、改哪段逻辑、预期改善什么指标。

3. **Weekly Seed Challenge**
   - 官方每周发布固定 Arena/PvE seed，所有人提交 bot，公开 replay 与排行榜。低运营成本，高社区传播。

4. **AI Coach Mode**
   - MCP/Web UI 内置只读 coach：读取 replay + explain_last_tick + economy trend，给出“下一步最可能提升收益的三件事”。

5. **Rule Diff Badge**
   - 世界列表显示：`Vanilla + LogisticsHardcore + NoSpecialAttacks`，点击可展开与官方规则差异。AI MCP 也能读取同样 diff。

6. **First Drone Ceremony**
   - 新玩家第一次成功 harvest/transfer/spawn 时生成一条小 replay clip，可一键分享。这比完整战报更适合首小时传播。

7. **Colony Museum**
   - 长期 World 里允许玩家公开某个房间的历史 replay、蓝图、外交事件，形成非战斗型声誉与参观目标。

---

## Issue Count

Total issues: 9
- High: 3
- Medium: 4
- Low/Medium: 1
- Low: 1

Final verdict: CONDITIONAL_APPROVE
