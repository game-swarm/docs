# R26 Closure Verification — GPT-5.5 Game Designer

## Verdict

**CONDITIONAL_APPROVE**

本轮从游戏设计/UX/AI onboarding 视角看，R25 的核心产品语义已经基本闭合：AI 玩家可以通过 MCP resources 学习、部署、观察、解释；Arena 回到房间制；World 统计被产品语义上拆为非竞争展示；Replay/观战路径不再被 Tournament-first 口径污染。

但仍有两处会直接影响 AI-only 学习与 SDK/codegen 的残留：Host Function ABI 在非权威旁路文档仍复制旧 `range: i32`；机器权威 `game_api.idl.yaml` 仍把 `swarm_get_leaderboard` 放在 Play 且 `visibility_filter: none`，与生成后的 `api-registry.md` Arena-only 口径冲突。因此本轮不能给 APPROVE。

## Strengths

- **AI first-hour loop 已闭合**：`06-feedback-loop.md` 明确 AI 通过 `swarm_get_schema` / `swarm_get_docs` / `swarm_get_available_actions` 学习，再用 `swarm_validate_module` / `swarm_deploy` / `swarm_explain_last_tick` 形成迭代闭环。
- **MCP 工具状态对玩家心理更清晰**：`03-mcp-security.md` 不再把 onboarding/debug 工具说成 removed，改为引用 API Registry 权威与 scope/rate/detail 限制，避免 AI 玩家以为关键学习工具不可用。
- **Arena/World 产品定位更稳**：`api-registry.md` 生成稿把 `swarm_get_world_stats` 定为 World 非竞争统计，把 `swarm_get_leaderboard` 放到 Arena profile；`06-feedback-loop.md` 明确 Arena 为房间制，Tournament/League 是 P1+ 编排。
- **Replay/观战传播路径仍保留**：`06-feedback-loop.md` 的回放查看器、公开 safe view URL、赛后全知视角、观战解说覆盖层仍然支撑社区传播，不被本轮修复削弱。

## Concerns

### G1 — CLOSED — B3 Tick budget

- `specs/core/01-tick-protocol.md:73` 将 EXECUTE 写为“硬超时天花板: 500ms”，并在 `specs/core/01-tick-protocol.md:75` 明确 budget target 引用 `design/engine.md §3.4.1`。
- `design/engine.md:290` 的预算表仍是 World EXECUTE ≤400ms、Arena EXECUTE ≤50ms。
- 设计评审角度：500ms 作为 kill/ceiling、400ms/50ms 作为体验预算目标是可解释的双层模型，不再是玩家/AI 会读成“EXECUTE 预算 500ms”的单口径冲突。

### G2 — CLOSED — B4 MCP 工具清单

- `specs/reference/api-registry.md:209` 声明 56 个活跃 Game API MCP tools，`specs/reference/api-registry.md:226` 标题为 `Game API 工具清单 (56)`。
- `specs/security/03-mcp-security.md:223` 明确权威清单见 API Registry 56 tools，`specs/security/03-mcp-security.md:264` 与 `specs/security/03-mcp-security.md:272` 使用 Authority note，不再自称 active 工具已移除。
- 对 AI 玩家可学性：`swarm_get_schema`、`swarm_get_docs`、`swarm_get_available_actions`、`swarm_explain_last_tick` 均保留为 active 能力，第一小时不会被安全文档误导。

### G3 — CLOSED — R3 snapshot truncation

- `specs/core/01-tick-protocol.md:158` 明确 snapshot truncation 的唯一权威为 Snapshot Contract，tick-protocol 不定义独立算法。
- `specs/core/09-snapshot-contract.md:52` 起定义距离桶、entity_id 字典序、farthest-first 与 critical 不可截断规则。
- 仍有 `specs/core/01-tick-protocol.md:143` 的伪代码 `sort_and_truncate`，但后文立即声明算法权威归 snapshot-contract；从游戏设计视角看不再构成玩家理解分叉。

### G4 — GAP — R4 sandbox/IDL Host Function ABI

- `specs/reference/api-registry.md:401` 的权威签名为 `host_get_objects_in_range(x: i32, y: i32, range: u32, out_ptr: i32, out_len: i32) -> i32`。
- 但旁路文档仍复制旧/不一致签名：`specs/core/04-wasm-sandbox.md:209` 为 `range: i32`，`design/interface.md:75` 为 `range: i32`，`specs/reference/host-functions.md:31` 为 `range: i32`，`specs/gameplay/08-api-idl.md:263` 的概念 IDL 也为 `range: i32`。
- 对 AI-only 玩家影响：AI agent 很可能直接读 sandbox/interface/host-functions 生成绑定，得到与 registry 不一致的 signedness，导致 WASM import stub 或 SDK 类型漂移。

### G5 — CLOSED — R5 08-api-idl RangedAttack / Recycle

- `specs/gameplay/08-api-idl.md:230` 已为 `RangedAttack: { Energy: 150 }`。
- `specs/reference/economy.idl.yaml:328` / `specs/reference/economy.idl.yaml:329` 也为 `RANGED_ATTACK cost: 150`。
- `specs/gameplay/08-api-idl.md:164` 将 Recycle refund 改为 `RecycleRefund(body_cost, remaining_lifespan, total_lifespan)`，`specs/reference/economy.idl.yaml:81` 定义 lifespan-proportional 10%–50% 公式。

### G6 — GAP — R6 leaderboard → Arena, world_stats → Play

- 生成后的 `specs/reference/api-registry.md:256` 已将 `swarm_get_world_stats` 放在 Play，`specs/reference/api-registry.md:321` 已将 `swarm_get_leaderboard` 限定为 `arena_only`，`specs/reference/api-registry.md:370` / `specs/reference/api-registry.md:374` 的 profile 语义也正确。
- 但机器权威源 `specs/reference/game_api.idl.yaml:680` 仍定义 `swarm_get_leaderboard`，`specs/reference/game_api.idl.yaml:681` 仍是 `category: Play`，`specs/reference/game_api.idl.yaml:691` 仍是 `visibility_filter: none`。
- 因 `api-registry.md:3` 声称冲突时以 IDL YAML 为准，这不是单纯生成物残留，而是会重新生成并覆盖正确 registry 的源头残留。

### G7 — CLOSED — R7 CodeSigning default 7d → 30d

- `design/auth.md:274` 已写 `CodeSigningCertificate` TTL 为 `30–180 days（默认 30d，world.toml 可配）`。
- 未在正式设计/spec 路径中发现 “默认 7d” 作为 CodeSigning 默认值的残留；auth_api 中 `refresh_token_lifetime: 7d` 与 TickTrace hot retention 7d 属不同概念，不计入本项。

### G8 — CLOSED — R8 feedback-loop Tournament/MVP → 房间制 + 非竞争展示

- `specs/gameplay/06-feedback-loop.md:329` 起定义 Arena 为房间制比赛，`specs/gameplay/06-feedback-loop.md:337` 明确无自动匹配、无天梯排名、无赛季。
- `specs/gameplay/06-feedback-loop.md:338` 明确 Tournament/League 为 P1+ 上层编排，不在 P0 MVP 范围。
- `specs/gameplay/06-feedback-loop.md:327` 将 World 的 GCL/房间数定位为趣味展示/非竞争排名；这解决了设计传播诉求与竞争公平的冲突。

## Missing

- **Host ABI 单一阅读路径**：sandbox、interface、host-functions、08-api-idl 仍需要删除本地签名或改成纯引用 API Registry，否则 AI 玩家无法确信哪个 `range` 类型可编译。
- **IDL → Registry 生成链闭合**：`game_api.idl.yaml` 必须先修正 leaderboard 所属 category/profile/visibility，再重新生成 `api-registry.md`；否则当前正确的 registry 是易回滚状态。
- **针对 AI 的 drift check**：建议增加 grep/CI，覆盖 `host_get_objects_in_range.*range: i32`、`swarm_get_leaderboard` under Play、`visibility_filter: none` for leaderboard、`Game API 工具清单 (54)`。

## Fresh Ideas

- **MCP-only “first hour contract” smoke test**：让一个无项目上下文的 agent 只读 `swarm_get_docs` / `swarm_get_schema` / `swarm_get_available_actions` / `swarm_sdk_fetch`，自动生成最小 harvester WASM；若读到冲突 ABI 或 leaderboard/world_stats 混用则 CI fail。
- **Spectator-safe share cards**：Replay 分享页默认生成 15–30 秒 “why this tick mattered” 摘要卡，包含资源曲线、关键命令、失败原因；这比完整 replay 更利于社区传播。
- **World showcase 非排行化命名**：UI/API 文案尽量避免 “rank/leaderboard/top” 描述 World，使用 “colony showcase / world stats / public profile”，把竞争心理集中到 Arena Room。
- **Long-term pursuit beyond GCL/RCL**：增加非数值长期目标，如名人堂 replay、策略谱系、公开 bot benchmark、世界奇观/工程成就、教学贡献徽章，避免所有玩家只追房间等级和 GCL。

## Closure Matrix

| Item | Status | Evidence |
|---|---|---|
| B3 Tick budget | CLOSED | tick-protocol 500ms 已解释为 hard ceiling，并引用 engine budget target |
| B4 MCP tools 54→56 / removed wording | CLOSED | registry 56；security spec 使用 Authority note，不再声明 active tools removed |
| R3 snapshot truncation | CLOSED | tick-protocol 引用 snapshot-contract 为唯一权威 |
| R4 sandbox/IDL host ABI | GAP | `04-wasm-sandbox.md` / `interface.md` / `host-functions.md` / `08-api-idl.md` 仍有 `range: i32`，registry 为 `u32` |
| R5 RangedAttack / Recycle | CLOSED | 08-api-idl 与 economy.idl.yaml 已对齐 150 与 lifespan-proportional |
| R6 leaderboard/world_stats | GAP | api-registry 已正确，但 `game_api.idl.yaml` 仍将 leaderboard 放在 Play 且 visibility none |
| R7 CodeSigning default | CLOSED | auth.md 默认 30d，正式路径未见 CodeSigning 默认 7d |
| R8 feedback-loop | CLOSED | Arena 房间制；Tournament/League P1+；World 非竞争展示 |

## Final Verdict

**CONDITIONAL_APPROVE** — 6/8 项 CLOSED，2/8 项 GAP。若修复 G4 与 G6，并重新生成 Registry/SDK 文档，本方向可在下一轮转为 APPROVE。
