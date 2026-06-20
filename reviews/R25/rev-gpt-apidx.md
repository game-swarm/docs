# R25 Closure Verification — API/DX Review (GPT-5.5)

## Verdict

**CONDITIONAL_APPROVE**

API/DX 角度不能给 APPROVE：多数 B/D 项已经收敛到明确权威源，但仍存在会直接误导 SDK/codegen/MCP 客户端的残留冲突：`specs/gameplay/08-api-idl.md` 仍保留旧经济数值/公式；`specs/security/03-mcp-security.md` 仍把 registry 中 active 的 onboarding/debug 工具写成“已移除”；`specs/core/01-tick-protocol.md` 仍保留与 `09-snapshot-contract.md` 不同的 snapshot truncation 算法；Host Function ABI 仍有 `range: u32` vs `range: i32` 的类型漂移。

## Strengths

- `api-registry.md` 已明确声明 IDL YAML 为机器可读权威源，并把 CommandAction、RejectionReason、MCP Tools、Host Functions、Economy Operations、容量限制统一到同一 registry 入口。
- `host-functions.md` 已降级为实现指南，并显式引用 `api-registry.md` §4；主要 host function 签名、输出上限、预算已经基本一致。
- `mcp-tools.md` 已把 Game API active tools 明确为 56，并保留 Auth API 11 个工具，较 R24 的 54/56 漂移明显改善。
- `design/modes.md` 已明确 Arena P0 是房间制比赛，Tournament/League 为 P1+ 上层编排；World 表述为不设竞争榜单。
- `design/gameplay.md`、`economy.idl.yaml`、`api-registry.md` 已把 RANGED_ATTACK cost 收敛为 150，Recycle 在 reference/commands 中也已引用 lifespan-proportional 公式。

## Concerns

### X1 — B2 PARTIAL — `08-api-idl.md` 仍保留旧经济合同

- Evidence: `specs/reference/economy.idl.yaml` §RecycleRefund 使用 lifespan-proportional 10%–50%，`api-registry.md` §10.2/§10.3 也生成同一公式。
- Evidence: `design/gameplay.md` `[[body_part_types]] RangedAttack` cost 已为 `Energy = 150`，`api-registry.md` §10.2 SpawnCost 也为 `RANGED_ATTACK=150`。
- Gap: `specs/gameplay/08-api-idl.md` 仍写 `refund: registry.body_cost(body) * 0.5`，并且 body_cost 表仍写 `RangedAttack: { Energy: 100 }`。
- API/DX impact: 新用户或 SDK/codegen 作者若从 `08-api-idl.md` 学习 gameplay schema，会生成与 registry/economy 权威不一致的 Recycle/SpawnCost 行为。
- Status: **PARTIAL**。

### X2 — B4 PARTIAL — MCP security spec 仍把 active 工具标为“已移除”

- Evidence: `specs/reference/mcp-tools.md` 明确 `swarm_get_docs`、`swarm_get_schema`、`swarm_get_available_actions` 为 0.4.0 新增查询入口，Game API active tools 小计为 56。
- Evidence: `api-registry.md` §3 Debug/Arena/Onboarding 保留 active 工具表；`mcp-tools.md` 把 `swarm_explain_last_tick` 作为 Debug 工具之一。
- Gap: `specs/security/03-mcp-security.md` §4.3 仍写 `swarm_explain_last_tick` 已移除，§4.4 仍写 `swarm_get_schema`、`swarm_get_docs`、`swarm_get_available_actions` 已移除。
- API/DX impact: 这是典型反模式：security spec 与 registry 对同一 MCP surface 给出相反状态，客户端作者无法判断工具是 deprecated、removed 还是 active with scope/rate limit。
- Status: **PARTIAL**。

### X3 — B5 GAP — Snapshot truncation 唯一权威仍被 tick protocol 旧算法分叉

- Evidence: `specs/core/09-snapshot-contract.md` 明确声明自己是 snapshot truncation 唯一权威，算法为距离桶 + `entity_id` 字典序，从最远桶末尾移除，并定义 critical entity 不可截断。
- Gap: `specs/core/01-tick-protocol.md` §2.3 仍保留另一套“关键/高/中/低优先桶 + `(distance_to_drone, entity_id)` 升序”的截断算法，还写 `host_get_objects_in_range` 返回 `{items, truncated, total_visible_count?}`。
- API/DX impact: Snapshot 是 WASM/SDK 输入合同；两个算法会导致 SDK 测试夹具、模拟器、replay 工具和 engine 之间出现确定性差异。
- Status: **GAP**。

### X4 — B1 PARTIAL — Host Function ABI 基本收敛但仍有单字段类型漂移

- Evidence: `api-registry.md` §4.1 与 `host-functions.md` 已统一 5 个 host function 的主签名和输出上限。
- Gap: `api-registry.md` §4.1 把 `host_get_objects_in_range` 的 `range` 写为 `u32`，而 `host-functions.md` 和 `design/interface.md` 仍写 `range: i32`。
- API/DX impact: 对语言 SDK/WASM bindings 来说 signedness 是 ABI 级差异；即使运行时可容忍，代码生成器也会生成不同类型。
- Status: **PARTIAL**。

### X5 — D4 PARTIAL — Snapshot budget 分模式已落 design，但 spec budget 仍混有旧 World-only 表

- Evidence: `design/engine.md` §3.4.1 已给 World/Arena 分模式预算：World snapshot ≤200ms p95，Arena snapshot ≤50ms p99；这符合 D4。
- Gap: `specs/core/09-snapshot-contract.md` §7.1 仍只有 `Snapshot build time < 200ms p95 | hard 500ms` 的单一表，没有把 Arena 50ms p99 同步进去。
- API/DX impact: benchmark gate 与 SDK/testing profile 无法从 snapshot-contract 单独推导 Arena/World 的不同预算。
- Status: **PARTIAL**。

## Missing

逐项 closure 状态：

| Item | Status | API/DX closure note |
|------|--------|---------------------|
| B1 Host Function ABI | PARTIAL | Registry/host-functions 主体已统一；`host_get_objects_in_range.range` signedness 仍漂移。 |
| B2 Economy numeric alignment | PARTIAL | Registry/economy/design 基本统一；`specs/gameplay/08-api-idl.md` 仍有旧 Recycle/RangedAttack 值。 |
| B3 Tick budget alignment | CLOSED | `design/engine.md` 已给 World/Arena 阶段预算，EXECUTE=400ms(World)/50ms(Arena)，不再看到 500ms 作为目标预算；剩余 snapshot-contract 表归入 D4/B5。 |
| B4 MCP tools 54→56 | PARTIAL | `mcp-tools.md` 已为 56；security spec 仍称多个 active 工具已移除。 |
| B5 Snapshot truncation authority | GAP | `09-snapshot-contract.md` 与 `01-tick-protocol.md` 仍存在两套算法。 |
| B6 Auth CSR replay + CodeSigning TTL | CLOSED | Deploy replay 已收敛到 version_counter；CodeSigningCertificate 常用设备 TTL 30–180d；未再看到 idempotent/non-idempotent CSR 双写残留。 |
| D1 Arena room-first | CLOSED | `design/modes.md` 明确 P0 房间制；Tournament/League 为 P1+ 编排。 |
| D2 World non-competitive stats | CLOSED | `design/modes.md` 明确 World 不设竞争榜单；PvE leaderboard 限于 Arena challenge 语境。 |
| D3 Recycle lifespan-proportional | PARTIAL | 权威 reference 已是 lifespan-proportional；`08-api-idl.md` 残留 flat 50%。 |
| D4 Snapshot budget by mode | PARTIAL | design 已落 World 200ms/Arena 50ms；snapshot-contract SLO 表仍未分模式。 |

## API Consistency Issues

- **Canonical source leakage**: `api-registry.md` 自称单一权威，但 `specs/gameplay/08-api-idl.md` 仍像第二个 IDL 源，且数值已 drift；建议把该文件改成引用 registry/economy 的说明性文档，或从生成链中删除重复表。
- **Removed vs active ambiguity**: `03-mcp-security.md` 的“已移除旧工具”表必须改为“active but scoped/rate-limited”或直接引用 registry；不要在 security 文档中手写工具生命周期状态。
- **ABI signedness drift**: `range: i32/u32` 需要统一到 IDL/registry 权威签名；SDK 生成器应只从一个 schema 读类型。
- **Snapshot schema duplication**: `01-tick-protocol.md` 不应继续描述截断算法和 host query 截断返回形状；应只引用 `09-snapshot-contract.md`，避免 replay/test harness 双实现。
- **Budget table locality**: 分模式 snapshot budget 不应只存在于 design；`09-snapshot-contract.md` 作为 snapshot 权威也需要同一 World/Arena SLO 表。
