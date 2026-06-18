# R15 游戏设计评审（GPT-5.5 / Game Designer）

## Verdict

CONDITIONAL_APPROVE

R15 的方向已经足够像一个「可编程 MMO RTS」而不是单纯的技术沙箱：10 分钟 Golden Path、MCP/人类同路径、World + Arena 双模式、PvE 生态层、观战/Replay、经济仪表盘与 Drone 人格，能共同支撑第一小时的正反馈和长期社区传播。

但当前设计仍有一个核心风险：它同时承诺了太多「好玩点」——编程学习、经济优化、PvE、PvP、Arena、Replay、外交、模组、排行榜、人格表现——而玩家的首小时主线还没有被压缩成一个不可错过的情绪弧线。若不明确首小时的目标、失败反馈、社交触点和下一步召唤，玩家可能会觉得系统很强，但不知道自己为什么要继续玩。

## Strengths

1. **首小时目标比上一轮更像游戏闭环**
   - `登录 → SDK → 编译 → 部署 → 观察反馈 → 调试 → 首个 PvE 挑战` 的 10 分钟 Golden Path 是正确方向。
   - Tutorial 世界关闭 fog、免费部署、无新手经济锁，降低了「我还没理解就被规则惩罚」的挫败。
   - safe_mode → soft_launch → PvP 的威胁曲线，让从教学到真实世界之间有缓冲，而不是突然从 sandbox 掉进 full-loot MMO。

2. **AI 玩家公平性和可学性原则清晰**
   - MCP 不直接执行 `swarm_move` / `swarm_attack`，AI 必须写 WASM，与人类同路径，这是非常重要的设计底线。
   - `swarm_get_schema`、`swarm_get_docs`、`swarm_get_available_actions`、`swarm_validate_module`、`swarm_explain_last_tick` 构成了 AI agent 的 Learn/Decide/Act/Understand 闭环。
   - `first_tick_executed` 事件很好，解决 AI 首次部署后「不知道是否真的活了」的问题。

3. **World 与 Arena 的定位互补**
   - World 是持久沙盒、不追求公平；Arena 是公平算法对抗、可复现、可观战。这种分工清晰。
   - 同一玩家可以在 Arena 用多个 WASM 策略自我对抗，是可编程游戏非常强的训练/传播入口。
   - PvE Challenge 作为隔离沙盒，不污染 World 经济，适合排行榜、教程、内容创作者和 AI benchmark。

4. **可读性与情感连接被纳入设计，而非事后补 UI**
   - Drone 人格系统虽不影响数值，但能让「我的代码在跑」变成「我的小队在行动」。这对留存非常重要。
   - 行为可视化、特殊效果可视化、经济仪表盘、战斗报告、指令溯源，把本来不可见的代码结果翻译成可理解的画面和故事。

5. **长期追求不只依赖 GCL/RCL**
   - 文档中已出现殖民地年龄、Arena 段位、PvE 里程碑、Replay/观战声誉、蓝图掉落、外交/联盟、模组世界等多条追求线。
   - 这能避免所有玩家最终都卷向同一个「扩房间、升控制器」指标。

## Concerns

### G1 — High — 首小时目标仍过于「流程正确」，但情绪钩子不够强

10 分钟 Golden Path 的步骤完整，但它更像开发者 onboarding checklist，而不是玩家体验剧本。玩家会学会部署、看到 drone 采集、完成一次 PvE 击杀；但文档尚未定义这 10 分钟里玩家应产生的核心情绪：惊喜、掌控感、危险感、归属感、炫耀欲分别在哪个瞬间发生。

风险：玩家完成 starter bot 后只得到「它能跑」，而不是「我想继续改它」。编程游戏最难的不是让代码运行，而是让玩家在第一次运行后立刻产生一个小而明确的优化欲望。

建议：把 Golden Path 改写成「第一小时体验剧本」，至少包含：
- 第 1 个 aha moment：看到自己改一行代码导致 drone 数量/行为变化。
- 第 1 个 problem：某个 drone idle 或走错路。
- 第 1 个 diagnosis：`swarm_explain_last_tick` 明确指出错误。
- 第 1 个 recovery：玩家修复后效率提升。
- 第 1 个 social hook：看到附近玩家、公开 replay、排行榜 ghost，或被 NPC 事件广播吸引。
- 第 1 个 aspirational goal：展示一个高手 replay 或 Arena 策略，让玩家知道「这游戏的上限在哪里」。

### G2 — High — AI 仅通过 MCP resources 学会「规则」大体可行，但学会「策略」仍不够闭合

MCP 学习工具覆盖 schema、docs、actions、snapshot、validate、deploy、explain，足以让 AI 知道 API 怎么用。但策略学习需要更多「示例策略 + 失败案例 + 优化目标」的资源。

当前 `swarm_sdk_fetch(include_examples)`、starter bot、`swarm_get_docs` 是基础；但 AI agent 若只读这些，很可能能写出 basic harvester，却不知道下一步该优化什么：采集效率？房间扩张？防守？PvE？Arena 对抗？

建议补充 MCP resources，而不只是 tools：
- `swarm://tutorials/first-hour-plan`：按 tick 阶段给 AI 的目标序列。
- `swarm://examples/strategy-patterns/basic-economy`：解释采集、运输、spawn 比例。
- `swarm://examples/failure-cases/out-of-range-fatigue-carryfull`：常见失败与修复。
- `swarm://benchmarks/self-eval`：给 AI 一个可量化目标，如 500 tick 内 Energy、idle rate、survival。
- `swarm://replays/annotated/top-basic-harvester`：带注释的高手 replay，让 AI 通过观察学习。

### G3 — Medium — World 的长期追求很多，但缺少「非毁灭性竞争」的长期社交结构

设计里有外交、联盟、PvE、资源抢占、Arena challenge、Market Contracts，但它们尚未形成一个明确的长期社区循环。持久世界如果只有扩张、袭击、维护费，容易走向老玩家割据和新人孤岛；如果只靠 Arena 排行榜，World 的 MMO 感又会弱。

建议把 World 长期追求分成三类并明确默认入口：
- **个人优化**：效率曲线、殖民地年龄、PvE milestone、蓝图收集。
- **低风险竞争**：资源潮竞速、房间 claim 竞速、World 内嵌 Arena challenge、PvE challenge leaderboard。
- **社交协作/声誉**：公共 contract、联盟任务、可公开的战报卡、可订阅玩家/联盟 replay。

尤其建议把 `Market Contracts` 从一句话扩展为早期社交主线：老玩家发布「运输/防御/清怪」任务，新玩家用 bot 接单，失败只损押金，成功获得资源和声誉。这比直接 PvP 更适合新手进入社区。

### G4 — Medium — Replay/观战是传播核心，但目前仍偏功能列表，缺少分享产品形态

设计已有 replay privacy、Arena 赛后公开回放、回放播放器、观战延迟、指令展开、战报卡 RFC。这是正确方向，但对社区传播来说还不够产品化。

风险：Replay 存在但没人分享，或者只有硬核玩家能看懂。代码游戏的精彩点往往在「策略为何奏效」，不是单看单位移动。

建议把 Replay 分享定义为一等公民：
- 每场 Arena 自动生成 30 秒 highlight：关键击杀、资源反超、第一次 breach、最后 100 tick。
- 生成 share card：双方策略名、胜负、关键指标、地图种子、可复现命令。
- 支持「策略 diff replay」：同一玩家 v1/v2 bot 的效率差异对比。
- 支持注释层：玩家/AI 可在 tick 上写解说，形成教学内容。
- 支持一键 fork：从 replay 页面获取 SDK、地图 seed、初始状态，在本地/arena 复现挑战。

### G5 — Medium — 特殊攻击与可配置规则很丰富，但新手认知负荷需要更强分层

Vanilla Ruleset 同时包含 8 种 body part、6 种伤害类型、8 种特殊攻击、全局/本地物流、age 维修、Controller/Depot、PvE、外交、模组。虽然 Tutorial/Novice 禁用特殊攻击，但文档层面仍给人「规则巨大」的压力。

建议明确 `Ruleset Ladder`：
- Tutorial：只暴露 Spawn / Move / Harvest / Transfer / Build，隐藏 damage type、特殊攻击、物流损耗。
- Novice：加入 Tower、防守、Claim、简单 PvE。
- Standard：加入特殊攻击、轻物流、外交。
- Advanced/MOD：开放自定义 body/action/resource。

关键是 UI/MCP docs 也应按当前世界层级裁剪，而不是把完整规则一次性丢给玩家或 AI。

### G6 — Low — Drone 人格是好点子，但「纯表现」与「经济信号」边界需更明确

人格不影响 gameplay 数值是正确的，避免 roll advantage。但文档又说高 efficiency drone 在交易中可能溢价，容易让玩家误解 efficiency 是否真的影响效率。

建议换名或明确呈现：
- 若纯表现，避免叫 `efficiency`，可改为 `animation_style` / `tempo` / `precision`。
- 若要成为收藏/品牌价值，应在 UI 中标注「cosmetic only」。
- 不建议在默认经济里让人格形成交易溢价，否则会制造无意义的二级市场噪音。

### G7 — Low — Arena 无自动匹配/无天梯与后文排行榜/赛季存在体验口径冲突

`modes.md` 说 Arena 无自动匹配、无天梯排名、无赛季；`06-feedback-loop.md` 又列出 league 分区、锦标赛、赛季。这可能不是技术矛盾，但对玩家承诺是矛盾的。

建议统一产品口径：
- 若 MVP Arena 是「房间 + replay + challenge」，则不要承诺 league/season。
- 若 Arena 是核心传播入口，则至少保留 PvE scenario leaderboard 与公开 challenge board。
- 可以把正式天梯标为 Future，但把「可分享挑战」作为 MVP 社区传播最低闭环。

## Missing

1. **第一小时的成功指标**
   - 现在有时间目标，但缺少体验指标：部署成功率、首次修复率、首次 replay 分享率、首次 challenge 发起率、D1 留存触发点。

2. **玩家失败后的情绪修复机制**
   - 有战斗报告和 explain，但缺少「失败后给一个安全下一步」：推荐 Arena 练习、自动生成修复任务、推荐 starter bot patch、展示相近玩家如何解决。

3. **社区首页/发现页设计**
   - 设计有 replay、challenge、contracts、MOD 世界，但缺少玩家打开游戏后看到的社区入口：热门 replay、活跃世界、可接 contract、推荐 Arena challenge、教程精选。

4. **AI agent 的标准学习包**
   - MCP tools 足够，但 resources 还应包括可下载的教程文本、注释 replay、starter strategy progression、评估 benchmark。

5. **非程序员旁观者路径**
   - 如果目标包含社区传播，旁观者不一定会写代码。需要定义「我只看 replay/比赛/战报，也能理解发生什么」的观看体验。

6. **长期非数值声誉系统**
   - Replay/观战声誉被提到，但缺少具体指标：策略被 fork 次数、replay 收藏、contract 完成率、教程贡献、模组采用量。

## Fresh Ideas

1. **First Hour Questline：不是任务系统，而是调试剧本**
   - 给每个新玩家一个「有小 bug 的 starter bot」。第一步不是从零写代码，而是修复一个明显问题：drone 会采集但不会回家。
   - 玩家调用 explain，看到原因，改 3 行代码，立即获得效率提升。这比空白模板更容易制造掌控感。

2. **Ghost Replay Onboarding**
   - 教程地图中显示一个半透明高手 ghost bot，在旁边完成同样任务。
   - 玩家可以切换「我的策略 vs ghost 策略」效率图，天然引出优化欲望。

3. **Strategy Card 分享格式**
   - 每次部署生成一张策略卡：语言、WASM hash、最近 500 tick 指标、关键行为标签（harvester / defender / scout）、可 fork 链接。
   - 社区传播不只分享 replay，也分享「这个 bot 做了什么」。

4. **Arena Seed Challenge**
   - 每周发布固定 map_seed + scenario 的 challenge。玩家提交 WASM，结果可复现，Replay 自动公开。
   - 这是 AI agent、人类玩家、内容创作者共同参与的最低摩擦活动。

5. **Contract Board 作为新手社交入口**
   - 老玩家发布任务：「清理这个 NPC 据点」「运 1000 Energy 到 Depot」「写一个 anti-swarmling bot」。
   - 新玩家用隔离 Arena/PvE 沙盒完成验证，成功后 World 内结算奖励。这样新手可以服务老玩家，而不是只能被老玩家攻击。

6. **Explain as Coach**
   - `swarm_explain_last_tick` 不只回答发生了什么，还给出一条可执行改进建议，并附带 docs/replay 链接。
   - 对 AI 返回 machine-readable hints；对人类返回自然语言和代码定位。

7. **Forkable Replay**
   - 每个 replay 页面有 `Fork this state`：复制 map seed、world rules、起始 tick snapshot，创建一个本地 sim 或 Arena challenge。
   - 这能把观看转化为行动，是代码游戏传播的关键。

8. **Progression Beyond GCL/RCL**
   - `Strategy Mastery`: 按 bot 在 PvE/Arena/World 的稳定性、效率、适应性生成徽章。
   - `Colony Chronicle`: 殖民地历史时间线，记录第一次扩张、第一次防守、第一次联盟、第一次击败 Guardian。
   - `Blueprint Collection`: PvE 掉落蓝图不仅是资源，也是可展示收藏。
   - `Mentor Reputation`: 玩家发布的 starter bot / replay annotation 被 fork 或完成后获得声誉。

## CrossCheck — 需要跨方向检查

- CX1: MCP resources 是否足以让 AI agent 只靠 schema/docs/examples 完成首次部署、调试和一次策略改进，目前 tools 很完整但 resources 组织尚未完全定义 → 建议 Architect 检查 MCP resource URI、版本化、manifest hash 绑定与 docs 生成链路。

- CX2: Replay/观战/公开分享涉及 fog-of-war、spectate_delay、replay_privacy 和 Arena 公开规则，若处理不当会泄露 World 情报 → 建议 Security 检查 Replay safe view、延迟观战、权限边界和 TickTrace 脱敏策略。

- CX3: World Action Manifest 动态生成 SDK/MCP schema 后，AI 学到的 action 集是否与当前世界完全一致，尤其 MOD 世界和特殊攻击裁剪 → 建议 Architect 检查 IDL 与 world.toml/custom_actions 生成链路的一致性。

- CX4: `public_spectate=false` 的 World 默认值与社区传播目标存在张力；Arena 默认公开又依赖隐私设置 → 建议 Security 检查默认隐私是否安全，Designer/Speaker 再裁决传播目标与隐私默认的平衡。

- CX5: Contract Board / Market Contracts 若进入设计，会触及资源转移、防刷号、新玩家锁和经济滥用 → 建议 Security 检查合约押金、奖励结算、同源账号组与新玩家资源门的交互。
