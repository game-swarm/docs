# R15 Phase 2 Designer CrossCheck 补充阅读

## Scope

本文件只处理 R15 Speaker 指派给 Designer/UX/Game Design 的 Phase 2 CrossCheck 补充阅读，不重跑完整游戏设计评审。输入重点来自 `rev-dsv4-performance.md`、`rev-gpt-apidx.md`、`rev-gpt-economy.md`、`rev-gpt-security.md` 的 CrossCheck 段落，并参考 `R15-SPEAKER-VERDICT.md` 中 CX3 队列。

## Findings

### 1. Snapshot 256KB cap 与截断公平性

CrossCheck item -> Performance CX3: Snapshot 256KB cap 在 RCL8/高建筑密度/高 drone 密度下是否充足；截断导致的信息丢失对战术决策与公平性的影响需要 Gameplay 评估。

Finding -> 这是 Designer 视角的 high 风险，不应只当性能预算问题。若 snapshot 被截断但玩家/AI 只看到“合法但不完整”的局面，失败会被玩家归因为策略错误、脚本 bug 或对手作弊，而不是系统边界。对 AI 玩家尤其严重：MCP resources 能教会规则，但无法让 agent 推断“我没有收到全部可见状态”。这会破坏首小时信任感，也会让竞技复盘难以解释。

Finding -> 可接受的设计边界不是“256KB 足够大”，而是“截断必须是显式、稳定、可复盘、可调试的游戏规则”。如果保留 cap，snapshot 需要包含 `truncated=true`、被截断实体类别/数量、排序规则、可操作对象是否完整、推荐降级策略等元数据；竞技世界应禁止影响 tactical legality 的静默截断。最好把 256KB 作为默认传输预算，而不是不可解释的视野规则。

disposition -> high. 不必升级为 R15 blocker，但应进入 R15.1 High/D-item：定义 snapshot overflow UX 与公平合同，至少要求显式截断标记、确定性截断顺序、Replay/TickTrace 可见，并说明哪些对象永不被截断。

### 2. tick 延迟、COLLECT 截断与部分玩家 0 指令

CrossCheck item -> Performance CX5: 软截止 2500ms 在 p99 预算 3050ms 下持续触发时，玩家会经历 COLLECT 截断与部分玩家被跳过；需要评估 tick 延迟、不完整 tick 和 0 指令的玩家感知。

Finding -> 这是首小时和长期竞技信任的 high 风险。Screeps-like 游戏的玩家心理默认是“我的代码每 tick 都被公平执行”；如果部分玩家因系统压力产生 0 指令，玩家体验上接近掉线、服务器吃指令或隐性惩罚。即使技术上 deterministic，只要 UI/trace 不解释，社区会把它解读为不公平调度。

Finding -> COLLECT 截断必须在产品语义上命名清楚：是 player code timeout、server overload、room tick degraded，还是 world-wide soft pause。不同语义对应不同补偿和展示。若 0 指令来自玩家自身 fuel/time overrun，可以作为可学习的策略反馈；若来自系统侧 collect deadline，则应在 TickTrace、Replay、客户端 timeline 和 post-tick error 中标记为 server-side degraded tick，且不能让受影响玩家在 PvP 中承担完整失败成本。

disposition -> high. 需要补一条 UX/公平合同：所有 0-command tick 必须区分 player-caused 与 system-caused；system-caused COLLECT 截断要可见、可复盘、可统计，并定义竞技处理策略（例如延迟 tick、降级世界、暂停提交或显式 compensation），不能静默吞掉。

### 3. opaque visibility-first error 与新手调试体验

CrossCheck item -> API/DX CX3: visibility-first 错误策略与玩家调试体验存在张力；opaque error 可能让新手难以修复策略，需要 UX/Game Design 检查是否提供安全 hint。

Finding -> 该问题为 medium，但会显著影响 AI MCP 可学性和新手留存。visibility-first error 的安全目标正确：不能通过错误信息泄露 unseen entity。但若所有失败都只返回 opaque，首小时会变成“代码运行了但不知道为什么失败”，AI agent 也只能在 resources 中学到接口，学不到实际调试路径。

Finding -> 推荐采用分层 hint，而不是放弃 opaque。玩家可见层返回安全类别：`not_visible_or_not_actionable`、`stale_id`、`out_of_range_known_target`、`insufficient_resource_visible`、`action_not_available_in_world` 等；trace 层给出不泄露坐标/隐藏属性的修复建议；Replay/训练世界可启用更详细解释。竞技世界不应返回“目标存在但不可见”这类 oracle 信息。

disposition -> medium. 当前不构成 blocker；应补入 API/DX 与 UX 文档：visibility-first error 必须有 safe hint taxonomy，并在 MCP docs/examples 中展示调试循环，否则 AI 玩家仅靠 resources 学会玩法的承诺会打折。

### 4. `swarm_simulate` 命名与“预测未来”预期

CrossCheck item -> API/DX CX6: `swarm_simulate` 不执行其他玩家 WASM、使用 NPC-only world，与玩家期望的“预测未来 N tick”可能冲突；Security CX2 也要求确认 simulate 不会成为高精度战术 oracle。

Finding -> 当前命名存在 medium-to-high 的产品语义风险。`simulate` 在策略游戏语境中很容易被理解为“基于当前局面预测未来”；但设计实际更像 solo dry-run / sandbox validation。如果玩家以为它能预测 PvP 对手行动，结果会误导策略；如果它真的接近预测，又会成为 oracle 并破坏竞技公平。

Finding -> 最稳妥的 UX 方案是改名或强制输出假设。建议 MVP 将工具命名为 `swarm_dry_run`、`swarm_simulate_solo` 或 `swarm_validate_strategy_step`，并在每次响应中显式返回 `assumptions`: no_other_player_wasm, npc_only_or_static_world, snapshot_time, fuel_budget, confidence=not_predictive。Replay/分享中也应避免把 dry-run 结果包装成“未来预测”。

disposition -> medium. 不需要阻断 R15，但应改名或补强 response contract；若保留 `swarm_simulate` 名称，必须在 MCP docs、schema description 和 UI 文案中明确“不是未来预测”。

### 5. Market / Merchant / Contracts / allied transfer 的 MVP 边界

CrossCheck item -> Economy CX6: Market 虽为 RFC，但 Merchant、Market Contracts、drone P2P offer 和 allied transfer 仍构成事实交易层；需要 Game Designer 检查 MVP 是否保留这些入口，或统一标为后续经济扩展。

Finding -> 这是 high 风险，原因不是“经济系统不好玩”，而是 MVP 同时引入多个交易入口会稀释核心乐趣并放大 abuse 面。第一小时的乐趣应来自写代码、部署 drone、看到策略反馈；Market/Contracts/Merchant/allied transfer 会把注意力转向套利、搬砖、小号、联盟洗钱和客服争议。它们还会让社区 meta 过早固化为经济效率，而不是策略创造。

Finding -> 建议 MVP 明确降级：保留最小必要的本地/全局资源流动和教学用 faucet；allied transfer 只保留受限、延迟、带税/配额/审计的合作赠与，或移入 Future；Market Contracts、Merchant、drone P2P offer 统一标为 Future Economy RFC，不作为 R15 MVP 可实现入口。若 Contract Board 是社区传播钩子，可先做 non-transfer 的 challenge/bounty/replay share，不直接结算资源。

disposition -> high. 建议并入 R15.1 High/D-item：MVP 经济入口必须收敛到一个权威 transfer path；Market/Contracts/Merchant 默认 Future，allied transfer 至少降级为受限合作机制并等待 Security/Economy 复核。

### 6. `player_view=full`、public spectator 与 replay privacy 的产品语义

CrossCheck item -> Security CX3: `player_view=full`、public spectator、replay privacy 的产品语义需要 UX + Gameplay 检查，避免教学/合作/竞技三类世界在 UI 上被误配置为实时全图泄露。

Finding -> 这是 medium，接近 high 的配置 UX 风险。Designer 视角重点不是单个 flag 是否安全，而是服主/玩家能否理解三种模式：competitive、cooperative/tutorial、public showcase。若 UI 只暴露 `player_view=full` 或 `public_spectate=false` 这类底层开关，服主很容易为了传播效果打开全图，实际破坏竞技公平。

Finding -> 建议把配置产品化为 World visibility preset：`competitive_private`、`competitive_delayed_spectate`、`tutorial_full_view`、`showcase_public_full_view`。每个 preset 明确 fog、spectate_delay、replay safe view、MCP visibility、shareability。竞技世界默认不允许实时 full map；公开传播通过延迟观战、赛后 replay、裁剪视角和红队/蓝队 safe overlay 来满足。

disposition -> medium. 与 Security CX3 互相支撑；应补入 UX 配置合同，但不单独升级 blocker。

## Missing

- 缺少 snapshot overflow 的玩家可见文案、MCP response 字段和 Replay 表达方式。
- 缺少 COLLECT 截断时的归因模型：player timeout、sandbox crash、server overload、deadline skip 目前在玩家心理上会混成“系统吃指令”。
- 缺少面向 AI agent 的调试教程：从 opaque error 到 safe hint 到修复代码的最短闭环。
- 缺少 MVP/Future economy 边界表，导致 RFC 组件以零散入口形式漏回 MVP。
- 缺少 spectator/replay/world visibility preset，底层 flag 太容易被误用。

## Fresh Ideas

- “Fairness Receipt”：每 tick 给玩家一个轻量 receipt，显示 module executed、fuel used、commands accepted/rejected、snapshot truncated、server degraded 等状态，供 UI、Replay、客服和 AI debug 共用。
- “Overflow Training Room”：新手/AI 教程里故意制造 snapshot overflow，让玩家学会处理 `truncated=true`，避免第一次在 PvP 中才遇到。
- “Safe Hint Ladder”：同一错误在 competitive、practice、replay 三种上下文显示不同细节，既保护 fog-of-war，又降低新手挫败。
- “Dry-run Badge”：所有 `simulate`/dry-run 输出在 UI 和 MCP 中带不可去除的 `not_predictive` badge，防止社区传播时误称为未来预测。
- “Challenge Board before Contract Board”：MVP 先做公开挑战、Replay 分享和非资源奖励榜单，等反作弊/经济账本成熟后再开放资源结算合约。
