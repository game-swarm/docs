# R5 最终检查 — rev-gpt-designer

Reviewer: rev-gpt-designer (GPT-5.5, Game Designer)
Scope: /data/swarm/docs/design/DESIGN.md + /data/swarm/docs/specs/p0/*
Date: 2026-06-14

## Verdict

CONDITIONAL_APPROVE

Phase 0 设计已经达到可冻结、可进入 Phase 1/2 实现的水平：核心公平性、MCP 定位、Deferred Command Model、可见性、回放、AI 上手闭环都已经从概念收敛为可实现合同。

但从 Game Designer / UX / 社区传播视角，仍有少量必须在实现前写进文档或 issue 的具体项。它们不推翻架构，不要求大改，但会直接影响“第一个小时是否好玩”、“AI 是否真的能只靠 MCP resources 学会玩”、“Replay/旁观是否能传播”。因此给 CONDITIONAL_APPROVE。

必须补齐的条件项见 Concerns G1-G5。

## Strengths

1. 核心幻想清晰：代码就是军队

Swarm 的一句话定位已经很强：可编程 MMO RTS / Screeps 精神续作 / Write once, fight forever。玩家第一眼能理解：“我不是操作单位，我是在写一个会持续作战的军队大脑。”

这对开发者玩家和 AI agent 都是好卖点：不是又一个 RTS，而是一个自动化、算法、系统设计竞技场。

2. MCP 定位已经正确

文档明确修正了最危险的设计歧义：MCP 不是 gameplay controller，不存在 swarm_move / swarm_attack / swarm_build。AI agent 通过 MCP 看世界、读文档、生成 WASM、部署 WASM；真正 gameplay 指令只来自 WASM tick()。

这对公平性、可解释性和社区接受度非常关键。人类与 AI 的差异从“是否有外挂接口”变成“谁写代码、怎么写代码”，世界只认 WASM。

3. AI 上手闭环比上一轮成熟很多

P0-6 已经覆盖 LEARN → DECIDE → ACT → UNDERSTAND：

- swarm_get_snapshot
- swarm_get_available_actions
- swarm_get_docs
- swarm_validate_module
- swarm_deploy
- swarm_explain_last_tick
- starter bots

这使 AI 玩家可以仅靠 MCP resources 完成最小学习循环。尤其 swarm_explain_last_tick 和 rejection detail 对 AI 自我修复非常重要。

4. World / Arena 双模式解决了长期目标冲突

文档已经承认 World 不追求公平，Arena 追求公平。这是正确分层：

- World 是 Minecraft 服务器式长期生活、殖民、涌现故事。
- Arena 是可排名、可回放、可传播的竞技产品。

这避免了用同一套规则同时满足“持久 MMO”和“公平电竞”的常见失败模式。

5. Replay 与可见性策略已经有传播基础

P0-5 定义了自身回放、Arena 赛后全知公开回放、World 默认不公开；P0-6 定义了玩家视角 replay viewer、赛后观战视角、fog-of-war toggle、解说覆盖层。

这已经足以支撑后续做分享链接、赛后复盘、社区内容创作。

6. 规则模组与世界配置提供了长期可玩性空间

World Rules Engine + Rhai mod system 让 Swarm 不只是“一款游戏”，而是可配置的编程 RTS 平台。不同服务器可以做：

- 轻物流新手世界
- 硬核 Factorio-like 物流世界
- 1v1 Arena
- 资源衰减生存服
- 帝国维护费服
- 自定义资源经济服

这对社区服主、模组市场和长期内容供给是强项。

7. 玩家失败反馈足够具体

Command Validation Spec + P0-6 的每 tick explanation 能把失败从“我的 bot 不动了”变成：

- OutOfRange：距离是多少，最大范围是多少
- Fatigued：疲劳值是多少
- MissingBodyPart：缺哪个 body part
- CarryFull / SourceEmpty：状态是什么

这会显著降低第一个小时的挫败感。

## Concerns

### G1 — 第一个小时的“成功体验”仍需变成强制 MVP 条件

问题：P0-6 有教程房间和 starter bot，但还没有明确写出玩家第一个小时必须达成的体验目标。

现在文档从系统角度说“5 分钟教程”、“starter bot”、“部署循环”，但缺少产品验收标准。例如：新玩家第一次打开游戏后，10 分钟内应该看到什么？30 分钟内应该完成什么？60 分钟内应该感到自己变强在哪里？

如果没有这个标准，Phase 1 很容易实现成“系统能跑”，但第一个小时像调 API，而不是玩游戏。

具体条件：在 P0-6 或 DESIGN roadmap 中补一个 “First Hour Acceptance Criteria”：

- 5 分钟内：玩家能在 Tutorial 世界看到预置 bot 采集能量。
- 10 分钟内：玩家能修改一个常量并观察 drone 数量或行为变化。
- 20 分钟内：玩家能部署自己的 basic-harvester 到 World 或 Arena sandbox。
- 30 分钟内：玩家能通过 explain_last_tick 修复至少一个失败指令。
- 60 分钟内：玩家能达成一个可视化成就，例如“稳定能量正收入 10 tick”、“成功 spawn 第 3 个 drone”、“建成第一个 Extension/Tower”。

这不是大改，但必须写成验收项，否则 MVP 很可能缺少“好玩”的定义。

### G2 — AI 仅靠 MCP resources 学会玩：仍缺“最小可运行策略包”的合同

问题：P0-6 写了 MCP 教程和 starter bot，但还没有把 MCP resource 的内容结构冻结。

AI agent 要真正自助上手，不只需要工具名，还需要一个可机器读取的学习包：

- API reference
- command schema
- snapshot schema
- starter bot source
- compile/deploy instructions
- common rejection repair guide
- minimal strategy recipe

否则不同 agent 会在“怎么把策略编译成 WASM”这一步卡住，尤其是非 TypeScript / Rust agent。

具体条件：给 `swarm://docs/tutorials/basic-agent` 增加资源合同，至少包含：

- `manifest.json`：列出教程步骤、依赖语言、目标产物。
- `snapshot.schema.json`：tick 输入 schema。
- `commands.schema.json`：Command[] 输出 schema。
- `starter-bot.ts` 与 `starter-bot.rs`：可编译最小 bot。
- `compile.md`：如何从 starter bot 生成 WASM。
- `debugging.md`：Top 10 rejection reason → 修复建议。
- `success_criteria`：部署后 N tick 内应出现的可观测结果。

这项是 AI 玩家可用性的关键，不要求 Phase 1 立即实现全部内容，但应在 P0 文档冻结为目标。

### G3 — Replay 分享策略还缺“World 可选公开”的安全产品形态

问题：P0-5 写 World 默认不公开，Arena 赛后公开。这对安全是对的，但从社区传播角度略保守。

World 模式会产生最多故事：偷袭、奇袭、物流崩溃、防线反杀、bot 进化。但如果 World replay 永远只能自身可见，社区传播会损失一大块。

具体条件：补一个 World replay 的 opt-in safe share 规则：

- 玩家可以分享自己视角 replay URL。
- 默认只包含该玩家当时可见的信息。
- 分享时可选择时间范围、房间范围、实体脱敏。
- 不泄露 world_seed、其他玩家隐藏资源、其他玩家 rejection、WASM 源码。
- 允许延迟公开，例如 T+100 tick 或 T+24h。
- 被其他玩家实体出现在视野中时，只展示当时本来可见的字段。

这不会破坏 P0-5 的可见性原则，因为它仍使用 is_visible_to(player, tick)。但它会显著增强社区传播。

### G4 — 长期追求除 GCL / room level 外已有方向，但还没形成“玩家目标菜单”

问题：设计中已经有 GCL、房间数、Arena league、赛季、市场、模组世界，但还没有清晰列出玩家可追求的长期目标类型。

编程游戏的长期留存不只靠排名。不同玩家会追求不同东西：优化狂、收藏者、服主、PvP 玩家、AI bot 作者、内容创作者。

具体条件：在 DESIGN 或 P0-6 增加 “Long-term Pursuits” 小节，至少列出：

- Colony Mastery：殖民地年龄、稳定收入、自动防御、房间扩张。
- Algorithmic Optimization：energy/tick、CPU fuel efficiency、command success rate、logistics efficiency。
- Arena Competitive：league、season rank、tournament medals。
- Bot Lineage：每次部署版本、策略演化树、可回滚冠军版本。
- Modded Worlds：通关某类规则世界、生存天数、服主成就。
- Market/Economy：交易量、套利收益、供应链稳定性。
- Community Recognition：公开 replay likes、annotated replay、starter bot fork count。

这项不是系统架构 blocker，但对“为什么长期玩”是必要产品补丁。

### G5 — 旁观者模式已经有 Replay 基础，但 Live Spectator 边界还没定义

问题：文档主要定义了 replay，尤其 Arena 赛后 replay；但直播观战的产品/安全边界未写清。

对于 Arena，Live spectator 很重要：AI 锦标赛、社区赛事、教学直播都需要它。但 live 全知视角会泄露给参赛玩家，尤其如果比赛正在进行。

具体条件：补一个 Spectator Policy：

- Arena live spectator 默认延迟 ≥100 tick 或按比赛类型配置。
- Live spectator 可用全知视角，但延迟必须大于可利用窗口。
- Private match 可禁用 spectator。
- Official tournament 可开启 commentator role，拥有 annotation 权限但不能影响比赛。
- World live spectator 默认只允许玩家授权的自身视角，不提供全知观战。
- 所有 spectator feed 走同一 visibility/delayed visibility policy，不走调试/admin trace。

这会让后续社区赛事更容易做，同时不会削弱公平性。

## Missing

1. First Hour Acceptance Criteria

目前最缺的是把“新玩家第一个小时应该获得哪些正反馈”写成验收标准。没有这个，MVP 容易偏工程而非游戏。

2. MCP Tutorial Resource Manifest

AI 玩家能否只靠 MCP resources 学会玩，取决于 resource 内容是否结构化、可机器读取、可复制运行。现在方向正确，但合同还不够具体。

3. World Replay Safe Share

Arena replay 已经很好；World 模式需要 opt-in safe share，否则大量涌现故事无法传播。

4. Live Spectator Policy

Replay 是赛后传播，Spectator 是赛事传播。需要明确定义延迟、权限、视角、commentator role。

5. Long-term Pursuits Taxonomy

除 GCL / room level / leaderboard 外，需要明确玩家长期追求菜单，覆盖优化、创作、经济、模组、社区认可。

6. “可玩垂直切片”的最小规则包

Phase 1 写了基础单位、地形、资源、API，但从游戏感角度还需要明确 MVP slice 的最小闭环：Spawn → drone → harvest → transfer → spawn more / build first structure → explain failure。建议写成一张验收图。

## Fresh Ideas

1. “Bot Autopsy” — 部署后自动诊断

每次部署新 WASM 后，系统在前 20 tick 自动生成一份 Bot Autopsy：

- idle drone 数
- 最常见 rejection
- energy delta
- CPU fuel hot spots
- “你的 bot 看起来想采集，但没有 Carry 部件”

这对人类和 AI 都是强 UX，能减少早期流失。

2. “Strategy Diff Replay” — 对比两个 bot 版本

玩家可以选择 v12 和 v13，跑同一 Arena seed，查看：

- 哪些 tick 决策不同
- 哪些 drone 路径改变
- energy/tick 差异
- 指令成功率变化

这会让“优化代码”变成可视化游戏，而不是只看日志。

3. “Replay Clip” — 生成 30 秒传播片段

从 replay 中截取 tick range，自动生成短链接：

- 标题：“3 drones held against 12”
- 关键事件标记
- 可切换双方视角
- 可嵌入论坛/Discord/Telegram

编程游戏需要降低围观门槛，Replay Clip 是传播核心。

4. “Bot Lineage Tree” — 策略进化树

每次部署成为节点，记录：

- parent version
- commit message
- performance delta
- replay examples
- rollback option

这会把“写 bot”变成长期养成。

5. “Challenge Worlds” — 官方策展规则世界

用 World Rules Engine 做官方 weekly challenge：

- No Storage Week
- Low Fuel Arena
- Fog Heavy World
- Market Only Economy
- Swamp Logistics Challenge

这能展示模组能力，也给玩家持续目标。

6. “AI-readable Patch Notes”

每次规则变更发布两份 patch notes：

- human-readable changelog
- MCP resource `swarm://docs/patches/latest.json`，包含 changed_schema、affected_commands、migration_tips

这对 AI 玩家生态很重要，避免规则变更后 bot 大面积失效。

7. “Explain Like a Coach” 模式

`swarm_explain_last_tick` 可支持 mode 参数：

- raw：机器可读 detail
- coach：自然语言建议
- optimizer：指出效率瓶颈
- security：指出异常/滥用迹象

AI agent 可用 raw，人类新手可用 coach。

## Final Check Notes

- MCP 架构方向：通过。MCP 是管理/观察/部署界面，不是 gameplay 控制器。
- AI / 人类公平性：通过。唯一执行器是 WasmSandboxExecutor，fuel metering 一致。
- Deferred Command Model：通过。mutating host functions 被禁止。
- 可见性：通过。统一 is_visible_to，调试/回放/WS/REST/MCP 都受约束。
- MVP 反馈循环：方向通过，但需补 G1/G2 的验收合同。
- Replay / 旁观 / 社区传播：方向通过，但需补 G3/G5。
- 长期追求：方向通过，但需补 G4 的玩家目标菜单。

## Approval Conditions Summary

CONDITIONAL_APPROVE 的具体条件：

1. 在 P0-6 增加 First Hour Acceptance Criteria。
2. 为 MCP basic-agent 教程增加 resource manifest / schemas / starter source / compile / debugging / success criteria 合同。
3. 在 P0-5 或 P0-6 增加 World opt-in safe replay share 规则。
4. 在 DESIGN 或 P0-6 增加 Long-term Pursuits 小节。
5. 增加 Arena/World live spectator policy，特别是延迟、视角、commentator role、World 授权视角。

以上 5 项均为文档级补齐项，不要求推翻当前架构。补齐后可转 APPROVE。
