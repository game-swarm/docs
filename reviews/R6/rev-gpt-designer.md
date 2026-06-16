# R6 Game Designer Review — rev-gpt-designer

## Verdict

CONDITIONAL_APPROVE

R6 文档已经从“技术可实现”明显推进到“可被玩家理解和玩起来”：MVP feedback loop、first-hour 过渡、AI MCP onboarding、Arena/PvE/Replay/观战、安全可见性都已有明确合同。我的结论是可以进入实现准备，但需要先修正一个会影响 PvP 可玩性与公平性的特殊攻击跨文档矛盾，并补齐几个社区传播/长期追求层面的非阻塞合同。

## Strengths

- **首小时体验闭环成型**：`specs/gameplay/06-feedback-loop.md:23` 到 `specs/gameplay/06-feedback-loop.md:147` 把人类 5 分钟教程、AI MCP 教程、Starter Bot、safe_mode→soft_launch→PvP 的过渡和首次战斗反馈串成了完整 onboarding。相比只给 API 文档，这更像一个可以真正留住新玩家的游戏。
- **AI 玩家学习路径正确**：`design/interface.md:5` 与 `specs/gameplay/06-feedback-loop.md:39` 明确 MCP 是“屏幕和鼠标”，AI 必须写 WASM；`specs/reference/mcp-tools.md:38` 提供学习类工具，避免 AI 通过作弊式 action API 玩游戏。
- **Arena 定位清晰且有传播潜力**：`design/modes.md:85` 到 `design/modes.md:146` 将 Arena 定义为算法对抗、可复现实验和赛后 replay 的场域，不再和 World 沙盒目标混淆。
- **PvE 不再只是装饰**：`design/modes.md:25` 到 `design/modes.md:83` 把 NPC、据点、世界事件、掉落和难度地理梯度写成常驻经济层，能给新手和中期玩家提供非毁灭性目标。
- **观战/回放安全边界较成熟**：`design/gameplay.md:937` 与 `specs/security/05-visibility.md:124` 把 drone snapshot、公屏/MCP、spectator camera 分层，避免把观赏性直接变成情报泄露。

## Concerns

### G1 — High — Overload 的目标校验在设计文档和 Command Reference 中冲突

- **位置**：`design/gameplay.md:618`、`specs/security/05-visibility.md:224`、`specs/reference/commands.md:173`
- **问题**：设计文档要求 Overload 必须满足 `is_visible_to(target, attacker)`、同一目标 50 tick 全局冷却、且攻击者不能从结果推断 fuel 状态；可见性规范也要求结果三等价，隐藏目标实际 fuel。但 `specs/reference/commands.md:178` 仍写“目标玩家 fuel > MAX_FUEL×0.2”，`specs/reference/commands.md:179` 写“无 range 限制（逻辑攻击）”。这会把 Overload 从战术电子战变成全图 fuel oracle / harassment：玩家可以扫描目标是否存在、是否 fuel 低、是否可被压制，即使没有视野。
- **修正建议**：以 `design/gameplay.md:618` 和 `specs/security/05-visibility.md:224` 为准更新 reference：校验应为 attacker drone 有 `RANGED_ATTACK`、target player 在 attacker 可见实体关联范围内或 target entity 可见、fatigue=0、目标全局冷却未触发；fuel 下限检查不得作为可区分 rejection reason 暴露，返回应统一为 accepted/no-op 或 `NotVisibleOrNotFound`。

### G2 — Medium — MCP resources 还不能保证 AI “只靠 resources”完整学会玩

- **位置**：`specs/gameplay/06-feedback-loop.md:39`、`design/interface.md:33`、`specs/reference/mcp-tools.md:38`
- **问题**：文档声明 `swarm://docs/tutorials/basic-agent`、`swarm_get_docs`、`swarm_get_schema`、`swarm_get_available_actions`，但缺少 resources 命名空间的规范合同：有哪些 canonical resource URI、每个 URI 的内容结构、教程如何引用 starter bot、schema 与 world-specific SDK hash 如何对应、AI 如何从 docs 到 compile/deploy 形成可验证闭环。现在 AI onboarding 作为体验流程成立，但 MCP resource API 作为机器可读教材还不够 spec-ready。
- **修正建议**：新增或扩展 MCP resource contract：至少定义 `swarm://docs/tutorials/basic-agent`、`swarm://docs/api-reference`、`swarm://schemas/commands/{world_id}`、`swarm://sdk/{world_id}/{target}`、`swarm://examples/basic-harvester/{lang}` 的返回格式、版本字段、manifest hash、最小示例和错误码。

### G3 — Medium — Replay 分享有播放器功能，但缺少社区传播合同

- **位置**：`specs/gameplay/06-feedback-loop.md:245`、`design/modes.md:143`、`specs/security/05-visibility.md:156`
- **问题**：回放查看器已有 tick slider、视角切换、指令展开、safe view URL 和 Arena 公开回放；安全侧也定义了公开/自身回放的可见性。但“分享”还只是 URL，没有定义社区传播所需的 metadata：标题、缩略图 tick、关键事件摘要、可嵌入片段、评论/解说权限、match card、排行榜反链。这样实现后能看 replay，但不一定能形成传播飞轮。
- **修正建议**：为 replay artifact 定义 share metadata：`title`、`world/match_id`、`players`、`duration_ticks`、`highlight_ticks`、`thumbnail_tick`、`visibility`、`safe_view_policy`、`annotations`、`source_match/leaderboard links`；Arena 结算页应自动生成“可分享战报卡”。

### G4 — Medium — 长期追求主要仍是 GCL/RCL/房间数/Arena 排名，缺少多轴身份目标

- **位置**：`design/modes.md:22`、`specs/gameplay/06-feedback-loop.md:261`、`specs/security/05-visibility.md:68`
- **问题**：World 被定义为无胜利条件的持续沙盒，指标仪表盘与 leaderboard 主要覆盖 GCL、房间数、drone 数、效率、战斗胜率；Arena/PvE 有 leaderboard。但对非硬核竞速玩家，长期身份目标仍偏薄：没有成就、收藏、蓝图图鉴、联盟贡献、声望、赛季纪念、观战创作者等目标轴。长期目标过于集中在“更强/更多/更高排名”，会削弱社区中 builder、teacher、caster、modder 的留存。
- **修正建议**：补一个非阻塞 progression contract：World 成就、PvE 蓝图图鉴、联盟/公会贡献、公开 replay 创作者指标、Arena season badge、mod/world curator reputation。注意这些目标不应直接破坏 World 不公平沙盒的定位，可作为展示和身份层。

### G5 — Low — GETTING-STARTED 与当前 action/schema 命名存在入门割裂风险

- **位置**：`GETTING-STARTED.md:40`、`specs/reference/commands.md:78`
- **问题**：入门示例使用 `action: "SpawnDrone"` 和 `seq`，而 reference 使用 `{ "action": { "type": "Spawn", ... } }` 与 `sequence`。这不是核心设计合同问题，但它会直接破坏第一小时体验：新玩家/AI 复制示例后无法部署或 dry-run，反馈循环第一步失败。
- **修正建议**：让 GETTING-STARTED 的代码示例与 canonical Command schema 完全一致，或明确它是 SDK wrapper 语法并链接 wrapper→raw command 的映射。

## Missing

- **MCP resource manifest**：缺少“AI 只读 resources 即可完成教程”的机器可读目录、版本、schema、示例 artifact 合同。
- **Replay social graph**：缺少 replay 与 match、排行榜、玩家 profile、annotation、embed card 的关联模型。
- **Long-term identity layer**：缺少非 GCL/RCL/rank 的长期身份目标，尤其是 builder、mentor、caster、modder 的可展示成就。
- **Spectator UX states**：已有安全边界，但缺少 spectator UI 的状态合同：延迟提示、fog toggle 标记、信息被隐藏时的占位/解释、解说 overlay 权限。

## Fresh Ideas

- **“First Hour Autopsy” 自动战报**：新玩家前 2000 tick 后生成一份报告：资源曲线、idle drone 原因、第一次战斗、下一步建议，并可一键转为 AI prompt。
- **Replay Clip DSL**：允许玩家/解说员把 `tick_start/tick_end/camera/player/fog_mode/annotation` 保存为短片段，形成可分享“高光片段”而不是整场 replay。
- **Blueprint Collection**：PvE 掉落蓝图不仅解锁配方，也进入可展示图鉴；重复蓝图可转化为 cosmetic/称号，避免纯数值膨胀。
- **Mentor Contracts**：老玩家发布 starter bot 改进任务或防守挑战，新玩家完成后获得安全奖励；这把 onboarding、市场和社区教学连起来。
- **Arena Ghost Opponent**：允许玩家挑战某个公开 replay 的“冻结策略版本”，作为异步对战和教学素材，不要求双方同时在线。

## Final Assessment

R6 的游戏设计已经足够接近可实现：核心循环能解释“为什么好玩”，AI 与人类路径公平，Arena/World/PvE 分工清晰，观战与 replay 有安全基础。阻塞实现前最需要修的是 G1，因为它会直接影响 PvP 公平、信息泄露和特殊攻击心智模型；G2-G5 建议作为实现前的 spec polish 或 MVP+ 社区层补强。