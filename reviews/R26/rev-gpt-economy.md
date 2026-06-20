# R26 Economy Closure Verification — rev-gpt-economy

## Verdict

**CONDITIONAL_APPROVE**

R26 指定的大部分 R25 REOPEN/WEAK 项已经在面向读者的 spec / design 层闭合；经济主线（RangedAttack=150、Recycle lifespan-proportional、World 非竞争统计、Arena 房间制）整体成立。

但仍有两个会影响“单一权威源/生成链”的残留：

1. **R3 GAP** — `specs/core/01-tick-protocol.md` 仍保留本地 `sort_and_truncate(...)` 伪代码与截断算法摘要，不是纯引用 `specs/core/09-snapshot-contract.md`。
2. **R6 GAP** — `specs/reference/api-registry.md` 已将 leaderboard 修成 Arena，但其声明的机器源 `specs/reference/game_api.idl.yaml` 仍把 `swarm_get_leaderboard` 放在 Play 且 `visibility_filter: none`。由于 `api-registry.md` 自称由 IDL 生成且冲突时以 IDL YAML 为准，这会重新打开 World leaderboard / 非竞争统计边界。

## Strengths

- 经济数值闭合良好：`economy.idl.yaml` 中 `RANGED_ATTACK=150`，`RecycleRefund` 为 remaining-lifespan proportional 10%–50%，并保留 AlliedTransfer 的 2% fee / 200 tick delay / 500 tick cooldown / 10000 daily cap。
- 面向玩家的反馈循环已收敛：World 明确为非竞争展示，Arena 明确为房间制比赛，Tournament/League 不在 P0 MVP 范围。
- MCP 安全文档已改为 Authority note 风格，不再自行声明 active tools 被移除。

## Concerns

### E1 — B3 Tick budget: CLOSED

- `specs/core/01-tick-protocol.md` §1.4 EXECUTE 写为“硬超时天花板: 500ms”，并引用 `design/engine.md` §3.4.1 的 World ≤400ms / Arena ≤50ms budget target。
- `design/engine.md` §3.4.1 保留分模式预算表：EXECUTE World ≤400ms，Arena ≤50ms。
- 未发现“EXECUTE 500ms”作为独立预算目标残留；500ms 已降级为硬天花板语义。

### E2 — B4 MCP 工具清单: CLOSED

- `specs/reference/api-registry.md` §3 写明 game_api active tools = 56；`specs/reference/game_api.idl.yaml` 也有 `total_tools: 56`。
- `specs/security/03-mcp-security.md` §4 引用 API Registry §3.2 为 56 工具权威清单，并声明不自行维护工具移除状态。
- `swarm_get_docs`、`swarm_get_schema`、`swarm_get_available_actions`、`swarm_explain_last_tick` 均仍为 active 工具，不再被 security spec 标为“已移除”。

### E3 — R3 snapshot truncation: GAP

- `specs/core/09-snapshot-contract.md` 明确为 snapshot truncation 唯一权威，并定义触发条件、截断标记、距离桶、entity_id 字典序、farthest-first、critical entity 不可截断。
- `specs/core/01-tick-protocol.md` 已声明“snapshot-contract 是 snapshot truncation 的唯一权威源”。
- 但同文件仍保留：`entities = sort_and_truncate(entities, 256_000);`，并在后续 bullet 中摘要“距离桶 + entity_id 字典序 + farthest-first + critical 不可截断”。这不是“纯引用”，仍可能被实现者当成本地算法入口/摘要权威。
- 需要清理为纯引用：保留 cap / `truncated` / `omitted_count` 字段语义即可，删除本地函数名和算法摘要，改成“调用 snapshot-contract 定义的算法”。

### E4 — R4 sandbox/IDL host function ABI: CLOSED

- `specs/reference/api-registry.md` §4.1 权威签名为：`host_get_terrain(room_id, out_ptr, out_len)`、`host_get_objects_in_range(x, y, range, out_ptr, out_len)`、`host_path_find(..., opts_ptr, opts_len, out_ptr, out_len)`、`host_get_world_config(key_ptr, key_len, out_ptr, out_len)`、`host_get_world_rules(rule_id_ptr, rule_id_len, out_ptr, out_len)`。
- `specs/core/04-wasm-sandbox.md` §3.2 与 `specs/reference/host-functions.md` 已对齐上述签名，并明确以 API Registry 为权威。
- 未发现旧 `host_get_world_rules(out_ptr, out_len)` 或缺 `opts_ptr/opts_len` 的 path_find 残留。

### E5 — R5 08-api-idl economy values: CLOSED

- `specs/gameplay/08-api-idl.md` body cost 中 `RangedAttack: { Energy: 150 }`，与 `economy.idl.yaml` 中 `RANGED_ATTACK cost: 150` 一致。
- `Recycle` 已写为 `RecycleRefund(body_cost, remaining_lifespan, total_lifespan)`，并标注 lifespan-proportional 10%–50%。
- 未发现 `RangedAttack: { Energy: 100 }` 或 fixed/flat 50% recycle 作为当前目标口径残留。

### E6 — R6 leaderboard → Arena, world_stats → Play: GAP

- `specs/reference/api-registry.md` 已闭合：`swarm_get_world_stats` 在 Play，语义为 World 非竞争统计；`swarm_get_leaderboard` 在 Arena，`visibility_filter = arena_only`。
- `specs/gameplay/06-feedback-loop.md` 与 `design/modes.md` 也支持该产品语义：World 非竞争展示，Arena 房间制且无自动匹配/天梯/赛季。
- 但 `specs/reference/game_api.idl.yaml` 仍未闭合：`swarm_get_leaderboard` 位于 `Play (14 tools)`，`category: Play`，`visibility_filter: none`。这与 Registry 的 Arena/arena_only 生成结果冲突。
- 因 `api-registry.md` 声明“本文档由 IDL 源自动生成；冲突时以 IDL YAML 为准”，该残留不是普通文案问题，而是权威源漂移。需要把 `game_api.idl.yaml` 中 leaderboard 迁至 Arena 或设为 arena_only，并重新生成 Registry。

### E7 — R7 CodeSigning default 7d → 30d: CLOSED

- `design/auth.md` §5.3 写明 `CodeSigningCertificate` TTL 为 30–180 days（默认 30d，world.toml 可配）。
- 未发现当前 design/spec 目标文档中仍把 CodeSigning 默认值写成 7d；`7d` 仅作为 TickTrace hot retention 出现，不属于证书 TTL。

### E8 — R8 feedback-loop Tournament/MVP: CLOSED

- `specs/gameplay/06-feedback-loop.md` §6 写明 Arena 为房间制比赛，玩家创建比赛房间，设定参数，自己或他人加入。
- 同段明确“无自动匹配、无天梯排名、无赛季”，且 Tournament/League 为 P1+ 上层编排，不在 P0 MVP 范围。
- World 侧写为趣味展示/非竞争排名；回放排行榜也标注为非竞争展示。

## Economy Balance Issues

- **Closed**: RecycleRefund 改为 lifespan-proportional 10%–50%，消除了固定 50% 回收导致的临时建造/拆除套利。
- **Closed**: RangedAttack=150 与 Attack=80 形成远程优势的显性成本差，经济权衡合理。
- **Residual risk**: R6 的 IDL 源漂移会让 codegen/SDK 重新暴露 World leaderboard，进而把持久 World 的非竞争经济展示重新导向 GCL/rooms/drones 排名竞争。

## Resource Loop Gaps

- 未发现本轮指定范围内新的资源产出/消耗/转换闭环缺口。
- R5 的经济循环残留（Recycle flat 50%、RangedAttack 100）已清理；AlliedTransfer、StorageTax、UpkeepDeduction、PvEAward 等仍由 `economy.idl.yaml` / resource-ledger 约束。
- 需要修复的不是经济公式本身，而是权威源一致性：`game_api.idl.yaml` 与生成后的 `api-registry.md` 必须重新对齐，否则未来再生成会回滚 R6 修复。

## Item Summary

| Item | Status | Notes |
|---|---|---|
| B3 Tick budget | CLOSED | 500ms = hard ceiling; budget target 引用 engine.md |
| B4 MCP tools 54→56 | CLOSED | Registry 与 game_api total_tools 均为 56；security spec 改为 Authority note |
| R3 snapshot truncation | GAP | tick-protocol 仍有 `sort_and_truncate` 与算法摘要，非纯引用 |
| R4 host function ABI | CLOSED | sandbox / host-functions / registry 签名一致 |
| R5 RangedAttack / Recycle | CLOSED | 150 + lifespan-proportional 已闭合 |
| R6 leaderboard/world_stats | GAP | Registry 已修，但 `game_api.idl.yaml` 仍 Play + visibility none |
| R7 CodeSigning TTL | CLOSED | 默认 30d，未见 7d 残留 |
| R8 Tournament/MVP | CLOSED | P0 房间制；Tournament/League P1+ |

## Required Residual Fixes

1. `specs/core/01-tick-protocol.md`: 删除或改写 `sort_and_truncate(...)` 与本地截断算法摘要，改为只引用 `specs/core/09-snapshot-contract.md`。
2. `specs/reference/game_api.idl.yaml`: 将 `swarm_get_leaderboard` 从 Play/`visibility_filter: none` 修正为 Arena/`visibility_filter: arena_only`（或等价机器字段），并重新生成 `api-registry.md`，确保 IDL 与 Registry 同步。
