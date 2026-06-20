# R25 Closure Verification — Architect Review (rev-dsv4-architect)

**Model**: DeepSeek V4 Pro
**Direction**: Architect
**Date**: 2026-06-20

## Verdict: CONDITIONAL_APPROVE

3 GAPs (B1, B2, B6) + 2 PARTIALs (B3, D3) 需要修复。4 CLOSED + 1 CLOSED。

---

## B1: Host Function ABI 统一到 api-registry.md 权威签名

**Status: GAP**

### 已闭合
- `api-registry.md` §4: 5 个 host function 权威签名正确，含 `host_get_terrain(room_id, out_ptr, out_len) → i32`（房间级查询）、`host_get_world_rules(rule_id_ptr, rule_id_len, out_ptr, out_len) → i32`（含 rule_id 参数）
- `specs/reference/host-functions.md` (R24 B1 修复后): 全部 5 个签名已对齐 api-registry ✓

### 未闭合
以下文档仍持有**旧签名**（per-cell `host_get_terrain`、无 `rule_id` 的 `host_get_world_rules`）：

| 文件 | 行号 | 旧签名 | 权威签名 |
|------|------|--------|----------|
| `design/interface.md` | 74 | `fn host_get_terrain(x: i32, y: i32) -> i32` | `(room_id: u32, out_ptr: i32, out_len: i32) -> i32` |
| `design/interface.md` | 80 | `fn host_get_world_rules(out_ptr: i32, out_len: i32) -> i32` | `(rule_id_ptr, rule_id_len, out_ptr, out_len) -> i32` |
| `specs/core/04-wasm-sandbox.md` | 208 | `fn host_get_terrain(x: i32, y: i32) -> i32` | 同上 |
| `specs/core/04-wasm-sandbox.md` | 214 | `fn host_get_world_rules(out_ptr: i32, out_len: i32) -> i32` | 同上 |
| `specs/gameplay/08-api-idl.md` | 253-255 | `get_world_rules(params: [out_ptr, out_len])` | 缺少 `rule_id_ptr, rule_id_len` |
| `specs/gameplay/08-api-idl.md` | 258-260 | `get_terrain(params: [x, y])` → `i32` | per-cell 旧语义，应为 room 级 |

**结论**: R24 B1 修复只改了 `host-functions.md`，遗留 `interface.md`、`04-wasm-sandbox.md`、`08-api-idl.md` 三处旧签名。需要统一修改为 api-registry.md 权威签名或加引用。

---

## B2: 经济数值对齐 economy.idl.yaml

**Status: GAP**

### 已闭合
- `economy.idl.yaml` §2.6: `RANGED_ATTACK: cost: 150` ✓
- `design/gameplay.md` L106: Recycle "lifespan-proportional 比例退还（最高 50%，随剩余 lifespan 递减至 10%）" ✓
- `resource-ledger.md` §2.5: lifespan-proportional 公式已权威 ✓
- `api-registry.md` §5.1: per-player drone cap = 50，per-room = 500 ✓

### 未闭合

| 文件 | 行号 | 残留问题 |
|------|------|----------|
| `specs/gameplay/08-api-idl.md` | 230 | `RangedAttack: { Energy: 100 }` — 应为 150（economy.idl.yaml 权威值）。这是 R24 C4 (rev-dsv4-economy C4) 的残留：economy IDL=150，08-api-idl=100。 |
| `specs/gameplay/08-api-idl.md` | 322 | `Recycle \| 回收 drone，退还 50% body part 资源` — 应为 lifespan-proportional 10%-50%（economy.idl.yaml / resource-ledger.md §2.5 权威公式）。这是 flat 50% 残留。 |
| `design/auth.md` | 1139 | `"recycle": 按比例退还资源到最近 Spawn（默认 50%）` — "默认 50%" 用词误导，应为 lifespan-proportional 10%-50%。 |
| `specs/core/02-command-validation.md` | 485 | "若 Recycle 始终退还 50% body_cost" — 讨论已过时的 fixed 50% 场景，应更新为 lifespan-proportional 正确语义。 |

**结论**: 权威数值（economy.idl.yaml）已正确，但三个下游文档仍有旧值残留。08-api-idl.md 是重灾区（2 处错误）。

---

## B3: Tick budget 对齐

**Status: PARTIAL**

### 已闭合
- `engine.md` §3.4.1: 分 World/Arena 的 5 阶段 budget 表 ✓
  - World: SNAPSHOT ≤200ms p95, COLLECT ≤2500ms, EXECUTE ≤400ms, COMMIT ≤50ms p99, BROADCAST ≤50ms
  - Arena: SNAPSHOT ≤50ms p99, COLLECT ≤200ms, EXECUTE ≤50ms, COMMIT ≤20ms p99, BROADCAST ≤10ms
- EXECUTE budget 统一为 400ms（不再是 400 vs 500 冲突）✓
- SNAPSHOT 已分模式（World 200ms p95 / Arena 50ms p99）✓

### 未闭合/模糊

| 问题 | 说明 |
|------|------|
| Budget sum vs interval | World: 200 + 2500 + 400 + 50 + 50 = 3200ms > 3000ms tick interval。R24 要求"明确 budget sum 不得超过 tick interval；若允许超额，必须定义 backpressure/degradation 策略"——当前文档未定义此策略。 |
| COLLECT/SNAPSHOT 并发语义 | SNAPSHOT build(200ms) 在 COLLECT(2500ms parallel) 之前串行执行，但 COLLECT 包含 per-player sandbox deadline 2500ms。两者总计 2700ms 串行 + 50+50 = 2800ms in serial path。未说明 SNAPSHOT 是否可与前一 tick 的 BROADCAST 并发以吸收 slack。 |
| Arena budget sum | Arena: 50 + 200 + 50 + 20 + 10 = 330ms > 300ms tick interval。同样无 backpressure 定义。 |

**结论**: 预算数值已对齐，但 budget sum 超 interval 的工程约束未文档化。

---

## B4: MCP 工具清单 54→56

**Status: CLOSED**

- `api-registry.md` §3: "共计 56 个活跃工具 (game_api) + 11 个 Auth API 工具 (auth_api)" ✓
- `specs/reference/mcp-tools.md`: "Game API 小计: **56**" ✓
- 分组验证: Onboarding 10 + Auth 2 + Play 16 + Deploy 7 + Debug 8 + Admin 6 + SDK 1 + Arena 4 + Resources 2 = 56 ✓
- `specs/security/03-mcp-security.md` 引用 api-registry 为权威，无冲突计数 ✓
- R24 B4 修正 (54→56) 已落实: 两个 R24 commits (cc7671f, 152fd09) 覆盖了计数更新

---

## B5: Snapshot 截断统一到 snapshot-contract 权威

**Status: CLOSED**

- `specs/core/09-snapshot-contract.md`: 声明为 snapshot truncation **唯一权威** ✓
- 截断算法: distance bucket order (0→6) + entity_id 字典序 tie-breaker + critical entity protection ✓
- `design/engine.md` §3.4.4: 明确引用 "权威截断合同见 Snapshot Contract §1" ✓
- 无其他文档声明独立截断策略 ✓

---

## B6: Auth CSR Replay Class + CodeSigning TTL 30-180d

**Status: GAP**

### CSR Replay Class — 内部矛盾仍存在

`design/auth.md` 中对 `swarm_submit_csr` 的 replay class 在**同一文件内**矛盾：

| 行号 | 声明 | Replay Class |
|------|------|-------------|
| L319 (§5.6a) | `idempotent_mutation` 示例列中：`swarm_submit_csr`（同 CSR）| **idempotent** |
| L321 (§5.6a) | `non_idempotent_mutation`: `swarm_submit_csr（FDB 事务内消费 PoW challenge，一次性）` | **non_idempotent** |
| L344 (§5.6b) | 授权矩阵明确定义: `swarm_submit_csr \| non_idempotent_mutation` | **non_idempotent** |

这是 R24 **C1 Critical**（rev-dsv4-security C1）精确描述的同一问题——"`swarm_submit_csr` 同时被标为 idempotent 与 non-idempotent"。R24 B6 fix commit (658159e) 未能修复此矛盾：L319 的 idempotent_mutation 行中仍列出 `swarm_submit_csr`。

### CodeSigning TTL — 默认值不在声明范围内

| 文件 | 行号 | 声明 |
|------|------|------|
| `design/auth.md` | L274 | CodeSigningCertificate TTL: **30–180 days（默认 7d，world.toml 可配）** |

**问题**: 默认值 7d 不在 30-180d 范围内。最小值 30d 远大于 7d。要么缩小范围（如 7-180d），要么提升默认值到 ≥30d。R24 B6 fix 声称统一了 TTL 但数值区间仍矛盾。

**结论**: CSR replay class 的内部矛盾**完全未修复**（L319 vs L321/L344）。CodeSigning TTL 默认值 7d 在 30-180d 范围外。

---

## D1: Arena 房间制优先

**Status: CLOSED**

- `design/modes.md` §9: Arena 定位为 "限时对决，类似围棋对局"，房主控制开始时间，房间创建时锁定 WASM ✓
- 胜利条件: room-based match (drone=0 > 认输 > tick limit) ✓
- API Registry 支持 tournament 工具作为上层编排（`swarm_tournament_create` 等），不改变 P0 room-match 核心 ✓
- R24 D1 推荐 A (Room Match P0, Tournament P1+) 已落实 ✓

---

## D2: World 非竞争统计

**Status: CLOSED**

- `design/modes.md` L24: "World 不设竞争榜单" ✓
- `specs/gameplay/08-api-idl.md` L433: "World 模式无公开排行榜，仅非竞争统计" ✓
- API Registry capability profiles: `play` profile 分配给 World 玩家，`arena` profile 分配给 Arena host。`swarm_get_leaderboard` 在 Play 列表但配合 Visibility Filter 控制 ✓
- R24 D2 推荐 B (非竞争 stats/analytics) 已落实 ✓

---

## D3: Recycle lifespan-proportional

**Status: PARTIAL**

### 已闭合
- `economy.idl.yaml` §2.1 RecycleRefund: `max(1000, (remaining_lifespan * 5000) / total_lifespan)` bp ✓
- `resource-ledger.md` §2.5: lifespan-proportional 权威公式 ✓
- `design/gameplay.md` L106: "lifespan-proportional 比例退还" ✓

### 未闭合
| 文件 | 行号 | 残留 |
|------|------|------|
| `specs/gameplay/08-api-idl.md` | 322 | `Recycle \| 回收 drone，退还 50% body part 资源` — 仍是 flat 50%，应为 lifespan-proportional 10-50% |
| `design/auth.md` | 1139 | `"recycle": 按比例退还资源到最近 Spawn（默认 50%）` — "默认 50%" 用词不精确 |
| `specs/core/02-command-validation.md` | 485 | "若 Recycle 始终退还 50%" 讨论已过时场景 |

**结论**: 权威源正确，下游残留与 B2 的 Recycle 残留重叠（08-api-idl.md L322 同时出现在 B2 和 D3）。

---

## D4: Snapshot budget 分模式 Arena 50ms/World 200ms

**Status: CLOSED**

- `design/engine.md` §3.4.1: World SNAPSHOT ≤200ms p95, Arena SNAPSHOT ≤50ms p99 ✓
- 与 `specs/core/09-snapshot-contract.md` 无冲突 ✓
- R24 D4 推荐 (A for Arena, B for World) 已落实: Arena 50ms p99 + World 200ms p95 ✓

---

## 汇总

| 项 | 状态 | 严重度 |
|----|------|--------|
| B1 | GAP | High — 3 文档仍持旧 host function 签名 |
| B2 | GAP | High — RangedAttack cost 100 vs 150 + Recycle flat 50% 残留 |
| B3 | PARTIAL | Medium — budget sum > interval 无 backpressure 策略 |
| B4 | CLOSED | — |
| B5 | CLOSED | — |
| B6 | GAP | Critical — CSR replay class 完全未修复；TTL 默认值矛盾 |
| D1 | CLOSED | — |
| D2 | CLOSED | — |
| D3 | PARTIAL | Medium — 08-api-idl.md flat 50% 残留 (与 B2 重叠) |
| D4 | CLOSED | — |

**GAP 修复优先级**:
1. **B6** (Critical): 删除 L319 中 idempotent_mutation 对 `swarm_submit_csr` 的引用，或统一改为 non_idempotent；TTL 默认值改为≥30d 或范围改为 7-180d
2. **B1** (High): 对齐 interface.md / 04-wasm-sandbox.md / 08-api-idl.md 三处 host function 签名
3. **B2** (High): 修正 08-api-idl.md RangedAttack cost (100→150) + Recycle (flat→proportional) + auth.md L1139 用词 + 02-command-validation.md L485 讨论

**B3 和 D3 可在下一轮 Closure Verification 中验证修复**（D3 与 B2 的 Recycle 残留重叠，可一并修复）。