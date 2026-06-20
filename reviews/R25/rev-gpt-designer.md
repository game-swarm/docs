# R25 Closure Verification — GPT Game Designer Review

## Verdict

**CONDITIONAL_APPROVE**

大部分 R24 B-items 与 D-items 已经闭合，尤其是 Arena 房间制、Recycle lifespan-proportional、snapshot 分模式预算、Host Function canonical 引用与 Auth TTL/replay 语义都有明确落点。但仍发现 B4/D2 相关残留：MCP 工具计数在 `api-registry.md` 小节标题中仍为 54，`game_api.idl.yaml` 的 Play 分组仍标 14 tools，且 World 非竞争统计与 `swarm_get_leaderboard` 的公开 API 命名/输出仍未完全闭合。

## Strengths

- First-hour / onboarding 相关的 MCP 三件套已恢复并活跃：`swarm_get_docs`、`swarm_get_schema`、`swarm_get_available_actions` 保留在权威工具链中，AI 玩家可通过 MCP resources/tools 学习世界、schema 与可行动作。
- Arena 产品模型明显收敛为 P0 房间制：创建房间、配置槽位、旁观延迟、Replay 公开策略已经形成可理解的第一小时竞技路径。
- Recycle 与 snapshot 预算的设计选择已经落到可执行的规则：lifespan-proportional refund 与 Arena/World 分模式 budget 都更符合玩家心理预期与公平性。

## Concerns

### G1 — B1 Host Function ABI: CLOSED

- `design/interface.md` 将 Host Function 段落标为概念签名，并明确权威定义见 `specs/reference/api-registry.md` §4.1。
- `specs/reference/api-registry.md` §4.1 给出 `host_get_terrain`、`host_path_find`、`host_get_world_rules` 等统一 ABI 签名、只读属性、预算与输出上限。
- 从设计评审角度，这足以让 AI 玩家/SDK 生成器知道实现引用应看 Registry，而不是从叙述文档手抄签名。

### G2 — B2 经济数值对齐 economy.idl.yaml: CLOSED

- `specs/reference/economy.idl.yaml` 已将 `RecycleRefund` 定义为 remaining lifespan proportional，10%–50% clamp，而不是固定 50%。
- storage tax 改为按 capacity percentage tier，而不是旧的绝对阈值；公式也使用 bp/fixed-point，利于 replay 与 AI 学习。
- gameplay 的 Vanilla defaults 仍是概述层，未发现与本轮指定项直接冲突的旧 recycle 口径。

### G3 — B3 Tick budget 对齐: CLOSED

- `specs/core/01-tick-protocol.md` 中 EXECUTE 已明确为 500ms，COLLECT 为 2500ms，且 tick 放弃/重试/degraded mode 有说明。
- snapshot budget 的模式差异转移到 snapshot contract，避免 tick protocol 与 performance wording 各自定义一套产品承诺。

### G4 — B4 MCP 工具清单 54→56: PARTIAL

- 已闭合部分：`design/interface.md`、`specs/reference/mcp-tools.md`、`api-registry.md` §3 总述均写 56 game tools + 11 auth tools；onboarding tools 保留 active，不再以 security 为由删除。
- 残留问题 1：`specs/reference/api-registry.md` §3.2 标题仍是 `Game API 工具清单 (54)`，与同文件 §3 总述和 `mcp-tools.md` 的 56 冲突。
- 残留问题 2：`specs/reference/game_api.idl.yaml` 的分组注释仍写 `Play (14 tools)`，但 registry/mcp-tools 口径为 Play 16。AI 仅靠 MCP resources 学习时，会遇到“生成源注释 vs registry 汇总”不一致。

### G5 — B5 Snapshot 截断统一到 snapshot-contract 权威: CLOSED

- `specs/core/09-snapshot-contract.md` 明确声明自身为 snapshot truncation 唯一权威，并定义 256KB、distance bucket、entity_id tie-break、关键实体不截断等确定性规则。
- `specs/core/01-tick-protocol.md` 的 snapshot 片段与 contract 方向一致，至少在本轮指定项上没有看到三套截断优先级继续并存。

### G6 — B6 Auth CSR Replay Class + CodeSigning TTL 30-180d: CLOSED

- `specs/security/09-command-source.md` 将 CodeSigningCertificate 有效期统一为常用设备 30–180 天，临时设备/管理员证书另列短 TTL，语义清楚。
- Deploy 防重放统一为 per-player/per-slot `version_counter`，相同 module/hash 返回 already_deployed；CSR/证书路径没有再出现“同一操作同时 idempotent 与 non-idempotent”的产品级矛盾。
- `specs/security/03-mcp-security.md` 保留 Browser Origin/CSRF 与 Agent app-cert signed request 的分离，未再把 browser CSRF 语义混到 agent 主路径。

### G7 — D1 Arena 房间制优先: CLOSED

- `design/modes.md` 明确写 Arena P0 以房间制比赛为核心，Tournament/League 为 P1+ 上层编排。
- 房间配置、槽位、spectate delay/privacy、finish-to-replay 流程已补齐；这对“第一小时能不能开一局、看一局、分享一局”是正向闭合。

### G8 — D2 World 非竞争统计: PARTIAL

- 已闭合部分：`design/gameplay.md` 明确 World 无公开排行榜，仅提供非竞争统计；`specs/gameplay/06-feedback-loop.md` 也把 World 展示描述为“非竞争排名/观赏”。
- 残留问题：`api-registry.md` 和 `game_api.idl.yaml` 仍暴露 `swarm_get_leaderboard`，输出字段为 `{player, gcl, rooms, drones}`，subject_source 为 `world`，visibility_filter 为 `none`。这仍会诱导产品/API 使用者把 World 的 showcase stats 理解成公开 leaderboard。
- 建议闭合方式：若保留 World 统计，应把 API 命名/输出改为 `swarm_get_world_stats` 或在 schema 中强制 `scope = arena|world_showcase` 并注明 world_showcase 不产生排名奖励、不代表公平竞技。

### G9 — D3 Recycle lifespan-proportional: CLOSED

- `economy.idl.yaml` 已用 remaining_lifespan/total_lifespan 计算 refund_rate_bp，并 clamp 到 10%–50%。
- 这比固定 50% 更能抑制临时建造套利，且对玩家解释成本可接受。

### G10 — D4 Snapshot budget 分模式 Arena 50ms / World 200ms: CLOSED

- `design/modes.md` 给 Arena 300ms tick interval 与比赛实时性语境；`snapshot-contract.md` 给 World/general SLO `Snapshot build time < 200ms p95`。
- R24 要求的方向是 “Arena 50ms / World 200ms 分模式”，当前文档至少已经不再把 50ms p99 与 200ms p95混为同一硬门槛；Arena 严格实时性与 World 宽松 SLO 的产品语义闭合。

## Missing

- **B4 residual fix**: 将 `api-registry.md` §3.2 标题 `Game API 工具清单 (54)` 改为 56，并同步 `game_api.idl.yaml` 的 Play 分组注释为 16 tools。
- **D2 residual fix**: 将 World showcase stats 与 Arena leaderboard 在 API 命名、scope、输出字段上拆开；避免 `swarm_get_leaderboard` 继续作为 world/global 无过滤接口出现。
- **Generated-count guard**: 需要一个最小 CI/check 脚本验证 IDL 分组数、Registry 小节数、mcp-tools 总览数一致，否则 54/56 类问题会反复回归。

## Fresh Ideas

- **AI onboarding smoke test**: 用一个“零上下文 AI agent”仅读 MCP docs/schema/actions，要求 10 分钟内完成 spawn → deploy → first harvest 的脚本化验证；这比人工读表更能证明第一小时体验闭合。
- **Spectator-to-player funnel**: Arena replay 分享页应提供“Fork this strategy / Challenge this module / Explain this tick”三个按钮，把旁观者直接转成创作者。
- **Non-competitive World cards**: World stats 不叫 leaderboard，叫 Colony Postcard / World Showcase，展示殖民地年龄、房间生态、NPC 击退、资源流图，避免玩家误以为是公平排名。
- **Long-term pursuits beyond GCL/room level**: 增加可展示但非零和的追求，如策略谱系、Replay 收藏、生态事件贡献、世界模组声望、Arena 解题挑战徽章。
