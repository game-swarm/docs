# R23 设计评审 — Game Designer Reviewer (GPT-5.5)

## Verdict

**CONDITIONAL_APPROVE**

R23 的核心方向成立：Swarm 清楚地抓住了「写代码驱动军队」的长期魅力，并且把人类玩家与 AI agent 统一到 WASM 路径上，这对公平性、Replay、社区传播都很关键。当前版本已经具备可玩的骨架：10 分钟 Golden Path、Tutorial、World/Arena 双模式、PvE 生态、Replay、观战、MCP 调试闭环都有覆盖。

但从游戏设计视角，仍建议条件通过而非直接 approve：文档对「可玩」的系统性承诺很强，但第一小时的情绪曲线、MCP-only 自举闭环、社区传播产品化、长期非数值追求仍偏规格化，缺少足够明确的体验验收与内容节奏。若这些不补齐，游戏会技术上完整，但玩家前几小时可能感到“我能运行代码了，然后呢？”

## Strengths

- **核心幻想清晰**：`Write once, fight forever` 很强，玩家的技能表达不是 APM，而是算法、调度、资源优化与博弈设计。
- **AI/人类公平路径正确**：MCP 不直接移动/攻击，AI 也必须生成 WASM，避免 AI 玩家拥有不同操作面造成的设计债。
- **首个闭环意识很强**：Golden Path、starter bot、`swarm_explain_last_tick`、`swarm_dry_run`、deploy 事件等都服务于 learn/decide/act/understand。
- **World/Arena 分工合理**：World 承担持久 MMO 沙盒与涌现生态，Arena 承担公平对战、算法测试和可传播内容。
- **PvE 不是副本孤岛**：World PvE 作为地理生态层存在，能自然引导探索、风险和资源竞争。
- **Replay/观战基础扎实**：TickTrace、Replay privacy、spectate delay、Arena 赛后公开回放为社区传播打下了正确技术基础。

## Concerns

### G1 — High — 第一小时仍像“工程流程”，不像“游戏旅程”

前 10 分钟 Golden Path 可执行，但第 10–60 分钟的体验主要由 safe_mode、soft_launch、NPC、资源潮和首次 PvP 警告拼接而成，缺少清晰的阶段目标、情绪峰值和成就叙事。玩家可能完成 starter bot 后进入长时间优化真空，不知道下一步是扩张、打 NPC、抢资源、建塔、打 Arena，还是只是等保护期结束。

建议补一个 **First-Hour Quest Spine**：
- 0–10 分钟：让第一个 harvester 跑起来。
- 10–20 分钟：修复一次 idle / OutOfRange / CarryFull 问题。
- 20–35 分钟：占领或侦察第一个邻近目标点。
- 35–50 分钟：完成一次低风险 PvE / 资源潮竞争。
- 50–60 分钟：生成一张可分享的“首次殖民报告 / 首战报告”。

### G2 — High — AI agent 仅靠 MCP resources 是否能学会玩，仍缺少“课程化资源合同”

文档列出 `swarm_get_docs`、`swarm_get_schema`、`swarm_get_available_actions`、`swarm_sdk_fetch` 等工具，但 MCP resources 的信息架构还不够像一个 AI 可自主学习的课程。现在更像 API 手册集合，而不是“从零到第一个有效 bot”的分层教材。

建议明确 MCP resources 至少包含：
- `swarm://tutorials/basic-agent`：逐步任务，不只是说明。
- `swarm://examples/basic-harvester/{language}`：可编译完整项目。
- `swarm://playbooks/debug-idle-drone`：常见失败诊断流程。
- `swarm://worlds/{id}/goals/first-hour`：当前世界推荐目标。
- `swarm://schema/current`：与 manifest hash 绑定的权威 schema。

验收标准应改成：一个无项目先验的 AI agent 只调用 MCP resources/tools，在固定回合预算内完成 SDK 获取、编译、部署、解释一次失败并改进一次。

### G3 — Medium — 社区传播被标成 RFC，但它其实是冷启动核心

Arena replay、观战、highlight card、自动摘要、社区 replay 排行榜目前有些被标为扩展项。对这类编程竞技游戏，分享内容不是锦上添花，而是冷启动传播机制：玩家需要能展示“我的 bot 为什么聪明/搞笑/离谱”。

建议 MVP 至少保留最小传播闭环：
- Arena 赛后公开 replay URL。
- 自动生成 1 张战报卡：胜负、关键 tick、最有效 drone、最大失误。
- Replay 支持 fog-of-war 切换和 tick permalink。
- Web UI 一键复制分享链接。

否则社区很难围绕策略形成讨论，游戏会停留在个人 IDE 体验。

### G4 — Medium — 长期追求仍偏“规模指标”，非资产型声誉不足

文档列出殖民地年龄、GCL、RCL、Arena 段位、PvE 里程碑、Replay/观战，但 World 模式又明确不设竞争榜单。这是合理的，但需要替代性荣誉系统，否则长期目标会退化为房间数、资源量、GCL/RCL。

建议补强长期追求：
- Strategy Codex：公开策略谱系、版本演化、胜率变化。
- Engineering Achievements：低 CPU、高效率、零 idle、最小 body 通关等工程型成就。
- World Legacy：殖民地历史、首次发现、事件参与、联盟外交记录。
- Community Bounties：非资源奖励的挑战板，发放称号、徽章、Replay 展示位。

### G5 — Medium — 可配置世界强大，但会削弱新手认知稳定性

World Rules Engine 很强，但“所有内容可配置”会让玩家尤其是 AI agent 面临认知负担：这个世界的 Energy、body part、特殊攻击、物流模式都可能不同。文档有 SDK/manifest/hash 机制，但产品层需要更强的“这个世界怎么玩”的摘要。

建议每个世界提供 `World Rule Card`：
- 资源体系：有几种资源、主要 faucet/sink。
- 物流模式：无物流 / 轻物流 / 硬核物流。
- PvP 风险：safe/soft/full 阶段。
- 特殊攻击：启用哪些、禁用哪些。
- 推荐 starter bot：本世界可用模板。

这个 card 应同时给 Web UI、MCP 和 replay 分享页使用。

### G6 — Low — Tutorial 禁止 manual control 是哲学正确，但可能牺牲理解速度

正式世界不开放 manual control 很对；但 Tutorial 中的受限引导操作如果太弱，新人可能很难建立空间/动作直觉。建议 Tutorial 允许“解释性 ghost command”：玩家点击地图生成一段等价代码 patch，而不是直接操控 drone。这样保留“代码就是军队”的哲学，同时降低学习门槛。

## Missing

- **First-hour measurable fun criteria**：除了能完成 PvE，还应定义玩家是否看到目标、是否理解失败、是否获得分享物、是否愿意继续优化。
- **AI-only onboarding benchmark**：需要一个无人工提示的 MCP agent smoke test，证明 resources 足够教会 AI 玩。
- **Replay share MVP scope**：需要把最小分享链路从 RFC 拉进 MVP，至少 Arena 赛后可公开传播。
- **Spectator product contract**：已有 `public_spectate` / `spectate_delay`，但缺少观众看到什么、如何避免剧透、如何生成解说层的产品合同。
- **Long-term identity layer**：玩家、殖民地、策略、Replay、联盟的声誉如何沉淀，还没有形成统一的非资源成长体系。
- **Failure drama design**：被攻击、被 Hack、经济崩盘、保护期结束这些负面事件需要战报/复盘/复仇入口，否则只会挫败。

## Fresh Ideas

- **Colony Diary**：系统自动记录“第一个 drone、第一次 idle 修复、第一次击杀、第一次被攻击、第一次扩张”，生成殖民地时间线。
- **Bot Autopsy**：部署失败或战败后自动生成“死因报告”，按代码行、命令、资源和战术原因分层解释。
- **Strategy Cards**：Replay 自动抽取策略标签，如 turtle、rush、kiting、logistics-first，方便社区检索和讨论。
- **Ghost Coach**：Tutorial 中玩家点击目标，系统不执行命令，而是生成“你需要写这样的代码”示例 patch。
- **Arena Kata**：短小算法题式 PvE Challenge，例如 100 tick 内采满资源、最少 fuel 击杀 Guardian，用于日常练习和社区挑战。
- **Public Bot Zoo**：玩家可公开某个旧版本 WASM 作为 sparring bot，其他人可在 Arena 中挑战，不影响 World 资产。
- **Patch Notes as Gameplay**：每次 bot 部署自动生成策略变更摘要，长期形成可分享的工程演进故事。

## CrossCheck — 需要跨方向检查

- CX1: MCP resources 是否足够支持“AI agent 无先验自举”，目前文档更多是工具列表而非课程化资源合同 → 建议 Architect 检查 MCP resource URI、schema version、manifest hash、docs/codegen 链路是否闭合。
- CX2: `api-registry.md` 顶部写 54 game tools，但 `design/interface.md` 写 56 game tools + 11 auth tools，且 changelog 也写 56 active → 建议 Architect 检查 IDL/codegen 事实源与文档生成一致性。
- CX3: Replay/观战公开、fog-of-war 切换、spectate delay、TickTrace 数据可能泄露隐藏策略或 WASM 行为模式 → 建议 Security 检查 replay privacy、visibility filter、延迟观战与导出字段的泄露边界。
- CX4: `swarm_get_code`、`swarm_get_replay`、`swarm_get_tick_trace`、debug detail 在训练/练习/竞技模式下的信息量差异很关键 → 建议 Security 检查 scope、owner/admin 可见性和 safe hint ladder 是否统一落到所有 API。
- CX5: World Rules 高度可配置会导致 SDK、starter bot、MCP docs 与当前世界 manifest 不匹配 → 建议 Architect 检查 `target_manifest_hash`、SDK cache、world rule card 与部署校验是否覆盖所有 mod 变更路径。
