# R25 Closure Verification — rev-gpt-determinism

## Verdict

**CONDITIONAL_APPROVE**

R24 的多数 B/D 项已经朝“单一权威源 + 引用式设计文档”收敛，但仍存在可直接导致实现/回放分叉的残留：`game_api.idl.yaml` 仍保留 `per_player_drone_cap: 500`，`specs/gameplay/08-api-idl.md` 仍保留 `RangedAttack: { Energy: 100 }` 与旧 host function 签名，`specs/security/03-mcp-security.md` 仍把 active MCP tools 标为“已移除”，`api-registry.md` 自身仍有 56 vs 54 标题漂移，`snapshot-contract.md` 仍残留旧 Recycle/StorageTax 口径。Closure 未达到 APPROVE。

## Strengths

- Host Function ABI 已基本收敛到 `specs/reference/api-registry.md` §4 / `game_api.idl.yaml` 权威签名；`host-functions.md` 和 `design/interface.md` 已改为引用 Registry。
- Auth replay class 已明确：`swarm_submit_csr` 是 `non_idempotent_mutation`，在 FDB 事务内消费 PoW challenge；CodeSigningCertificate 生命周期也已收敛到 30–180 days 策略。
- Tick budget 的 design 层已经分 World/Arena 给出清晰表格，snapshot build 也按 Arena 50ms / World 200ms 分模式落地。
- Snapshot contract 已定义确定性截断、critical entities、degraded tick 与 pathfinding cache determinism，方向正确。

## Concerns

### T1 — B2 经济数值仍未闭合（GAP）

`economy.idl.yaml` / `api-registry.md` 已定义 RANGED_ATTACK=150、Recycle lifespan-proportional 10%–50%、StorageTax tiered formula，但仍有旧口径残留：

- `specs/gameplay/08-api-idl.md:225` 的 body cost 表仍写 `RangedAttack: { Energy: 100 }`，与 `api-registry.md` §10.2 的 `RANGED_ATTACK=150` 冲突。
- `specs/reference/game_api.idl.yaml:1527` 仍写 `per_player_drone_cap: 500`，与 `api-registry.md:469` / `design/engine.md:307` 的 50 冲突。由于 Registry 声称由 IDL 自动生成，这说明生成链或源文件仍不一致。
- `specs/core/09-snapshot-contract.md:191-196` 的 MVP economy boundary 仍写 `RecycleRefund` 按 `recycle_refund_base` 50%、`StorageTax` 0.1%/tick，和 `economy.idl.yaml` / Resource Ledger 的 lifespan/tiered 公式冲突。

### T2 — B4 MCP 工具清单仍未闭合（GAP）

API Registry 和 MCP tools 文档已声明 56 个 game tools，但存在两个未闭合残留：

- `specs/reference/api-registry.md:209` 写“共计 56 个活跃工具”，但 `specs/reference/api-registry.md:226` 小节标题仍是 `Game API 工具清单 (54)`。
- `specs/security/03-mcp-security.md:267` 仍把 `swarm_explain_last_tick` 标为已移除，但 `api-registry.md:298` 和 `mcp-tools.md:54` 仍将其列为 active debug tool。
- `specs/security/03-mcp-security.md:275` 仍把 `swarm_get_schema`、`swarm_get_docs`、`swarm_get_available_actions` 标为已移除，但 `api-registry.md:240-241,271` 和 `mcp-tools.md:48` 均将其列为 active onboarding/play tools。

这不是纯文案问题：AI onboarding/debug 工具的 active/removed 状态会影响 capability profile、SDK 自举和 replay-safe query surface。

### T3 — B1 Host Function ABI 基本闭合，但 `08-api-idl.md` 残留旧签名（PARTIAL）

`api-registry.md` §4、`host-functions.md`、`design/interface.md` 对 `host_get_terrain`、`host_path_find`、`host_get_world_rules` 已基本一致。但 `specs/gameplay/08-api-idl.md:253-260` 仍保留旧短名/旧签名：`get_world_rules(params: [out_ptr, out_len])`、`get_terrain(params: [x, y])`，虽然旁注称权威见 Registry，但该文件仍自称 body_cost 表为“权威来源”并包含 host_functions 块，容易继续误导实现或 codegen。

### T4 — B3 Tick budget 大体闭合，但 core tick spec 仍未完整体现分模式预算（PARTIAL）

`design/engine.md:290-298` 已给出 World/Arena 预算表，满足 D4 的分模式方向；`01-tick-protocol.md:681-704` 也定义了 tick interval、soft/hard deadline 与统一预算表。但 core tick spec 仍主要以 World `2500ms` COLLECT 为中心，缺少与 design 表等价的 Arena 300ms tick / 200ms COLLECT / 50ms EXECUTE normative 表。对于跨节点实现，Arena 节点仅读 core spec 时仍可能采用 World deadline。

### T5 — B5 Snapshot 截断权威方向正确，但与 tick spec 算法未完全统一（PARTIAL）

`snapshot-contract.md` 自称 snapshot truncation 唯一权威，并定义 distance bucket + entity_id lexicographic + farthest-first removal；但 `01-tick-protocol.md:154-160` 仍描述另一套 bucket order（关键/高/中/低优先桶，按 `distance_to_drone, entity_id`），并在同一文件内作为 `build_snapshot` 行为出现。两者都是确定性的，但不是同一算法；若实现者选不同文档，会产生 replay divergence。

### T6 — B6 Auth CSR replay 与 CodeSigning TTL 基本闭合（CLOSED）

`design/auth.md:271-275` 定义 `CodeSigningCertificate` TTL 为 30–180 days，`design/auth.md:316-324` 将 `swarm_submit_csr` 归入 `non_idempotent_mutation` 并要求 FDB 事务内消费 challenge。`design/auth.md:727-749` 的 `swarm_submit_csr` 请求明确不携带客户端自报 challenge/difficulty，服务端从 FDB 读取权威值。该项从确定性/防重放视角可视为闭合。

## State Machine Gaps

- **MCP tool lifecycle**：active vs removed 没有单一状态机。Security spec 的“已移除旧工具”与 Registry active list 并存，缺少 `active/deprecated/removed/replaced_by` 的唯一枚举和迁移规则。
- **Snapshot truncation state**：tick-protocol 与 snapshot-contract 对截断状态机使用不同 bucket model；需要规定 `build_snapshot()` 必须调用 snapshot-contract 算法，而不是本地定义另一套 `sort_and_truncate`。
- **Arena tick state**：design 中已有 Arena 分模式预算，但 core tick state machine 尚未把 Arena deadline 作为 normative branch 写入 `COLLECT/EXECUTE/BROADCAST` 状态。
- **Generated source authority**：API Registry 声称 IDL 是权威并由其生成，但 `game_api.idl.yaml` 与 Registry 在 drone cap 上冲突，说明 “IDL → Registry → docs” 状态转换未闭包。

## Non-Determinism Sources

- **IDL/Registry drift**：`per_player_drone_cap` 500 vs 50 会导致不同节点按不同 cap 接受/拒绝 spawn，直接造成 state divergence。
- **Economy formula drift**：Recycle fixed/base 50% vs lifespan-proportional、StorageTax 0.1% vs tiered bp，会导致 resource ledger 不同，破坏 replay。
- **Snapshot algorithm drift**：distance bucket 算法 vs critical/high/medium/low bucket 算法都确定，但不等价；跨节点引用不同文档会产生不同 WASM input。
- **MCP active set drift**：active/removed 工具状态不一致会导致客户端 capability、debug query 和 onboarding replay-safe surface 不一致。
- **旧 host ABI 残留**：`08-api-idl.md` 的旧 host signatures 若被 codegen 或 SDK 作者采纳，会导致 WASM ABI mismatch。

## Item-by-Item Closure Check

| Item | Result | Evidence |
|------|--------|----------|
| B1 Host Function ABI 统一到 API Registry | PARTIAL | Registry/host-functions/interface 已对齐，但 `08-api-idl.md` 仍残留旧 `get_terrain(x,y)` 与 `get_world_rules(out_ptr,out_len)` |
| B2 经济数值对齐 economy.idl.yaml | GAP | `08-api-idl.md` RangedAttack=100；`game_api.idl.yaml` per_player_drone_cap=500；`snapshot-contract.md` 旧 Recycle/StorageTax 口径 |
| B3 Tick budget 对齐 | PARTIAL | design 表已分 World/Arena；core tick spec 仍缺 Arena normative branch，EXECUTE 语义仍偏 World 总预算 |
| B4 MCP 工具清单 54→56 | GAP | Registry intro 56 但小节标题 54；security spec 仍把 active onboarding/debug tools 标为已移除 |
| B5 Snapshot 截断统一到 snapshot-contract | PARTIAL | snapshot-contract 有权威算法；tick-protocol 仍保留不同截断算法 |
| B6 Auth CSR Replay Class + CodeSigning TTL 30–180d | CLOSED | `swarm_submit_csr` non_idempotent/FDB challenge consumption；CodeSigning TTL 30–180 days 已写入 design/auth |
| D1 Arena 房间制优先 | CLOSED | design/interface 与 design/engine 保留 Arena room/match 作为 P0，同时 tournament tools 作为 Arena profile/tooling，不作为 world action channel |
| D2 World 非竞争统计 | PARTIAL | product/design 倾向非竞争 stats，但 API 中 `swarm_get_leaderboard` 仍全局 active，未在 Registry 中明确限定 World 仅 stats/analytics 命名 |
| D3 Recycle lifespan-proportional | GAP | economy/ledger 已闭合，但 snapshot-contract MVP boundary 仍保留 base 50% 旧口径 |
| D4 Snapshot budget 分模式 Arena 50ms / World 200ms | CLOSED | `design/engine.md` 明确 World ≤200ms p95、Arena ≤50ms p99；snapshot-contract 保留 World measured SLO 200ms p95 |

## Required Closure Before APPROVE

1. 将 `specs/reference/game_api.idl.yaml` 的 `per_player_drone_cap` 改为 50，并重新生成/校验 `api-registry.md`。
2. 将 `specs/gameplay/08-api-idl.md` 的 RangedAttack cost 改为 150，或删除该手写成本表并引用 `economy.idl.yaml` / API Registry。
3. 删除或改写 `specs/security/03-mcp-security.md` 中 active tools 的“已移除”声明；为 deprecated tools 建立 canonical lifecycle table。
4. 将 `api-registry.md` §3.2 标题从 `(54)` 改为 `(56)`，并增加生成检查防止 count drift。
5. 让 `01-tick-protocol.md` 的 snapshot truncation 直接引用 `09-snapshot-contract.md` 算法，删除本地不等价算法。
6. 更新 `09-snapshot-contract.md` MVP economy boundary：Recycle 改为 lifespan-proportional 10%–50%，StorageTax 改为 tiered bp formula。
