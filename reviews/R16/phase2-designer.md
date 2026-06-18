# R16 Phase 2 CrossCheck — Designer 补充验证

范围：仅补充阅读 R16 Phase 1 review 的 CrossCheck/相关段落，不重跑完整评审。由于当前工作树已在 commit `7e3be92` 清理 `reviews/R16/`，本次读取来源为 git commit `8c02b92` 中的 `reviews/R16/rev-*.md` 与 `R16-SPEAKER-VERDICT.md`。

## CrossCheck item -> Finding -> disposition

### 1. World mode 是否需要最小 progression / identity / reputation 结构

Finding:
- 需要，而且不应只停留在 GCL/RCL/colony age 这类系统指标。rev-dsv4-designer 将 World motivation vacuum 列为 Critical：World “无胜利条件”可以成立，但当前长期目标多为 tracking metrics，不足以回答玩家“我在建向什么”。rev-gpt-designer 同样指出长期目标仍偏系统数字，缺少 identity、collection、reputation、creative legacy。
- 最小结构应保持非 snowball、非跨世界资源优势：colony age tier、profile badge、bot lineage、代表 replay、World chronicle entry、algorithm reputation tags、cosmetic colony/drone identity。PvE milestone 可给不可交易徽章/称号/featured replay，而不是资源或战力。
- Speaker 已将其记录为 D-H1（World 模式动机真空与长期目标不足），不是 B5 经济公式 blocker，但属于 R17 前需要落文档的产品 High。

Disposition: high

### 2. World 无 leaderboard 与 registry `swarm_get_leaderboard` 是否应改 showcase / chronicle

Finding:
- 应改。World 持久沙盒天然不公平，若暴露 `leaderboard {gcl, rooms, drones}` 会把 World 心智拉向胜负排名，放大老玩家优势和挫败感。rev-gpt-designer 建议 World 使用 `showcase` / `directory` / `world_stats` / `chronicles`，Arena/PvE Challenge 才使用 leaderboard/rating/season 语义。
- rev-dsv4-designer 对“无排行榜”与“趣味展示/非竞争排名”提出语义矛盾：展示可以保留，但必须明确不是 competitive ranking。Speaker D4 已裁决 A：World 仅 showcase/chronicle/world_stats，Arena 用 leaderboard。
- API 层处置建议：`swarm_get_leaderboard` 不应在 World profile/capability 中返回 GCL/rooms/drones 排名。可拆成 `swarm_get_arena_leaderboard` 与 `swarm_get_world_showcase` / `swarm_get_world_chronicle` / `swarm_get_world_stats`；若保留旧名，只能作为 Arena canonical 或 deprecated alias。

Disposition: medium

### 3. Replay safe share / highlight card / first victory card 的 MVP-adjacent 范围

Finding:
- 应归入 MVP-adjacent，而不是完全 Future RFC。rev-gpt-designer 明确指出 raw replay viewer 不足以形成社区传播闭环，至少需要 safe view URL、minimal highlight card、Arena PvE score card / first victory card。Speaker D5 已裁决 A：MVP-adjacent 至少 safe share URL + minimal highlight / first victory card。
- 建议的最小范围要克制：
  1. Safe share URL：公开状态与命令结果的安全视图，不泄露私有 WASM 源码、私有日志、full debug detail、隐藏视野。
  2. Minimal highlight / first victory card：首次 NPC 击杀、资源潮抢占、Tower 防守、Arena PvE 通关等事件生成一张卡，包含 bot/version、关键 tick 范围、战术摘要、replay link、下一步建议。
  3. Arena PvE score card：作为低风险传播单位，奖励为 profile/cosmetic/recognition，不产出 World 资源。
- Commentary markers、diff replay、社区 replay 排行榜可后置；但 safe share 与最小战报卡若缺失，会削弱首小时情绪峰值和传播增长。

Disposition: high

### 4. `spectator_view_mode` 与 `public_spectate` / `player_view` / `spectate_delay` 的产品安全边界

Finding:
- 需要显式定义 `spectator_view_mode`，并把安全默认写入 world config / registry 可读合同。rev-dsv4-designer 指出 `public_spectate=true` + `player_view="drone"` + `spectate_delay=0` 时，旁观者究竟看 drone perspective 还是 full map 未定义；若实时全图可被 Discord/Twitch 外联利用成为合法情报旁路。
- rev-gpt-security 进一步认为 World 延迟全图旁观不能只靠 `spectate_delay >= 50 tick`：Competitive World 默认应禁止 public full-map spectate，除非显式 `spectator_intel_risk_accepted=true`；延迟应按 wall-clock 最小时长（例如 5–10 分钟）配置，而不是固定 tick 数；`replay_privacy=private` 不应向 spectator 发送全图实体位置。
- 推荐产品边界：
  - `spectator_view_mode="player_perspective"` 默认：只看某玩家/某 drone 合法可见内容，可用于 tutorial、Arena live spectate、公开教学。
  - `delayed_full`：全图但强制 wall-clock delay，适合非竞争 World 或赛后 replay。
  - `delayed_dual` / fog dial：允许切换 Player A/B/omniscient delayed，用于 replay 教学，不用于实时竞争 World。
  - `public_spectate=false` 或 only metadata 是 Competitive World 默认；Browser/Spectator WS 与 Agent WS 权限隔离。

Disposition: high

### 5. Arena PvE 与 World profile / cosmetic recognition 的桥接

Finding:
- 需要桥接，但桥接只能是 recognition，不应是资源/战力/World 资产流动。rev-dsv4-designer 将 Arena PvE disconnected from World economy 列为 High：隔离资源是正确的竞争完整性选择，但若没有 profile visibility、badge、cosmetic display，World 玩家缺少参与 Arena PvE 的动机。
- 与 Economy 方向一致：Arena 与 World 经济应独立，Challenge Board 奖励限制为 bounty points / title / badge / featured replay / profile cosmetic，而不是 World resource。rev-gpt-economy 也要求清理 Market Contracts / settlement 语义，避免把非结算型 challenge 误读为经济合同。
- 最小桥接建议：World player profile 展示 Arena PvE best scores、scenario badges、first-clear card、bot lineage representative replay；World 中可放 cosmetic monument/room border/nameplate，但不得给 global storage、upkeep reduction、combat stat、资源 faucet。

Disposition: medium

### 6. Defensive bias: lifespan + repair + Fortify 是否需要参数建议

Finding:
- 需要作为 balance High 进入参数验证，不建议升级 blocker。rev-dsv4-designer 明确指出 ATTACK/RANGED_ATTACK lifespan penalty、active aging、Controller/Depot repair、Fortify ×0.5 resist + cleanse 可能组合成 repair fortress：攻击方行军与战斗双重衰老，防御方在 repair range 内配 TOUGH 与 Fortify，形成进攻三重惩罚。
- rev-dsv4-economy 还发现 Controller age repair 公式歧义：`min(0.5, controller_count * 0.5)` 在 controller_count ≥ 1 时恒为 0.5，叙述却暗示堆叠 Controller 需要被 cap。这个歧义会影响防御强度评估，应先裁定公式语义。
- 参数建议（用于 R17 balance sheet / simulation，不作为最终数值）：
  1. 将 ATTACK age_modifier 从 -80 调到 -40，RANGED_ATTACK 从 -50 调到 -25，或给“最近 20 tick 造成伤害的返回 combat drone”短期 repair surge，降低进攻寿命惩罚。
  2. Fortify Standard 默认 resist multiplier 从 ×0.5 调到 ×0.7，或缩短 duration / 增加 cooldown-cost ratio；保留强力 Fortify 给 Advanced/MOD world。
  3. 明确 Controller repair 是全局固定上限 0.5/tick，还是 per-controller 渐进贡献；若是后者，公式应改为低斜率并有 cap，而不是 1 个 Controller 即满 cap。
  4. 用 deterministic Arena scenario 做 defense-vs-offense smoke test：同等资源、同等 travel distance、含/不含 Fortify，检查 attacker expected value 是否长期为负。

Disposition: high

## Addendum to Speaker / R17 输入

- D-H1 与 D-H2 建议保留为 Designer 方向 High：它们不是实现权威源 blocker，但直接影响首小时留存、社区传播和长期追求。
- D4 / D5 已有 Speaker 裁决，应在 R17 文档中落到 API/UX 术语：World showcase/chronicle/stats；safe share URL + minimal highlight/first victory card 为 MVP-adjacent。
- spectator 相关项应与 Security/API-DX 合并成机器可读字段：`spectator_view_mode`、`public_spectate`、`spectate_delay_wall_clock_min`、`replay_privacy`、`visibility_filter`。
