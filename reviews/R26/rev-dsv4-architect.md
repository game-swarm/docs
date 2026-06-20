# R26 Closure Verification — Architect Review (rev-dsv4-architect)

**Model**: DeepSeek V4 Pro
**Direction**: Architect
**Date**: 2026-06-20
**Scope**: Narrow — R25 REOPEN (B3, B4) + WEAK residues (R3-R8) only

## Verdict: APPROVE

All 8 verification items CLOSED. No GAPs, no PARTIALs, no new findings. R25 REOPEN and WEAK items are fully resolved in source docs.

---

## REOPEN 项闭合验证

### B3: Tick Budget — CLOSED

**Required**: EXECUTE 500ms → hard timeout ceiling referencing engine.md budget

**Evidence**:

- `specs/core/01-tick-protocol.md` L74-77:
  ```
  硬超时天花板: 500ms
  (budget target 见 design/engine.md §3.4.1: World ≤400ms, Arena ≤50ms)
  ```
  500ms 已明确标记为"硬超时天花板"而非 EXECUTE budget；budget target 引用 engine.md §3.4.1 权威表 ✅

- `design/engine.md` §3.4.1: World/Arena 分模式 budget 表完整，EXECUTE World ≤400ms, Arena ≤50ms ✅

- 无残留 "EXECUTE 500ms" 独立声明，无多口径冲突 ✅

### B4: MCP 工具清单 — CLOSED

**Required**: (54) → (56); security spec Authority note 替代"已移除"语言

**Evidence**:

- `specs/reference/api-registry.md` L209: "共计 **56 个活跃工具** (game_api)" ✅
- `specs/reference/api-registry.md` L226: "Game API 工具清单 **(56)**" ✅ — 标题已修正
- `specs/security/03-mcp-security.md` L264: "Authority note: 上述工具的 canonical definition 见 API Registry §3.2。本文档**不再声明移除状态**——所有 active 工具以 API Registry 为准。" ✅
- `specs/security/03-mcp-security.md` L272: "Authority note: 所有工具的 canonical definition 与 active/removed 状态以 API Registry §3.2 为**唯一权威源**。本文档不自行声明工具的移除状态。" ✅

- 没有 (54) 残留标题、没有 "已移除/已整合" 对 active 工具的错误声明 ✅

---

## WEAK 残留项闭合验证

### R3: tick-protocol snapshot truncation → pure reference snapshot-contract — CLOSED

**Required**: tick-protocol 不保留独立截断算法，只引用 snapshot-contract

**Evidence**:

- `specs/core/01-tick-protocol.md` L157-161:
  ```
  超限时的截断策略见 Snapshot Contract §4 —— **snapshot-contract 是 snapshot truncation 的唯一权威源**。
  tick-protocol 不定义独立截断算法，只引用该权威源。
  - 截断算法（距离桶 + entity_id 字典序 + farthest-first + critical 不可截断）全部由 snapshot-contract 定义。
  ```
  ✅ 纯引用，无本地独立算法。`sort_and_truncate` 调用点仍存在但仅作为 stub 引用 snapshot-contract 逻辑。

### R4: sandbox/IDL host function ABI → api-registry authority signature — CLOSED

**Required**: 04-wasm-sandbox.md 和 08-api-idl.md 的 host function 签名对齐 api-registry.md §4.1

**Evidence**:

- `specs/core/04-wasm-sandbox.md` L208-214: 全部 5 个 host function 签名匹配 api-registry §4.1:
  - `host_get_terrain(room_id: u32, out_ptr: i32, out_len: i32) -> i32` ✅ (旧: `host_get_terrain(x: i32, y: i32) -> i32`)
  - `host_get_world_rules(rule_id_ptr: i32, rule_id_len: i32, out_ptr: i32, out_len: i32) -> i32` ✅ (旧: `host_get_world_rules(out_ptr: i32, out_len: i32) -> i32`)
  - 其余 3 个签名（host_get_objects_in_range, host_path_find, host_get_world_config）一致 ✅

- `specs/gameplay/08-api-idl.md` L258-259: `get_terrain: params: [room_id: u32, out_ptr: i32, out_len: i32]` ✅
  L253-254: `get_world_rules: params: [rule_id_ptr: i32, rule_id_len: i32, out_ptr: i32, out_len: i32]` ✅
  L241: 明确注释"所有签名的权威定义见 API Registry §4" ✅

- 无旧 per-cell `host_get_terrain(x, y)` 残留，无缺 `rule_id` 的 `host_get_world_rules` 残留 ✅

### R5: 08-api-idl RangedAttack 100→150, Recycle→lifespan-proportional — CLOSED

**Required**: RangedAttack cost = 150, Recycle = lifespan-proportional 10%-50%

**Evidence**:

- `specs/gameplay/08-api-idl.md` L230: `RangedAttack: { Energy: 150 }` ✅ (旧: `{ Energy: 100 }`)
- `specs/gameplay/08-api-idl.md` L164: `refund: RecycleRefund(body_cost, remaining_lifespan, total_lifespan) # lifespan-proportional 10%-50% (权威公式见 economy.idl.yaml §RecycleRefund)` ✅
- `specs/gameplay/08-api-idl.md` L322: `Recycle | — | — | 回收 drone，退还 lifespan-proportional body part 资源（10%-50%，详见 resource-ledger §2.5）` ✅ (旧: flat 50%)

- RangedAttack cost 对齐 economy.idl.yaml 权威值 ✅
- Recycle 语义对齐 resource-ledger/ economy.idl.yaml lifespan-proportional ✅

### R6: leaderboard → Arena, world_stats → Play — CLOSED

**Required**: D2-A leaderboard 限定 Arena 竞争排行，world_stats 作为 World 非竞争统计

**Evidence**:

- `specs/reference/api-registry.md` §3.4 Capability Profiles:
  - `play`: "Play (含 `swarm_get_world_stats` — World 非竞争统计)" ✅
  - `arena`: "Arena (含 `swarm_get_leaderboard` — Arena 竞争排行)" ✅

- `specs/reference/api-registry.md` §3.2 Arena: `swarm_get_leaderboard` visibility filter = `arena_only` ✅
- `specs/reference/api-registry.md` §3.2 Play: `swarm_get_world_stats` visibility = `none` ✅

- `swarm_get_leaderboard` 已限定 Arena profile + `arena_only` visibility filter ✅
- `swarm_get_world_stats` 已归入 Play profile，语义为非竞争统计 ✅

### R7: CodeSigning default 7d → 30d — CLOSED

**Required**: CodeSigningCertificate TTL 默认值进入 30-180d 范围内；CSR replay class 内部矛盾消除

**Evidence**:

- `design/auth.md` L274: `CodeSigningCertificate | WASM/module deploy 签名凭证 | 30–180 days（**默认 30d**，world.toml 可配）` ✅ (旧: 默认 7d)

- `design/auth.md` §5.6a Replay Class 表 (L319-L321):
  - L319 `idempotent_mutation` 示例: `swarm_auth_device_register` ✅ (旧: 曾含 `swarm_submit_csr`)
  - L321 `non_idempotent_mutation` 示例: `swarm_submit_csr（FDB 事务内消费 PoW challenge，一次性）` ✅
  - `swarm_submit_csr` 不再同时出现在 idempotent 和 non_idempotent 两列 ✅

- `design/auth.md` §5.6b 授权矩阵 L344: `swarm_submit_csr | non_idempotent_mutation` ✅

- 默认值 30d 落在 30-180d 范围内 ✅
- CSR replay class 内部矛盾已消除 ✅

### R8: feedback-loop Tournament/MVP → 房间制+非竞争展示 — CLOSED

**Required**: Tournament/League 明确标记 P1+，不在 P0 MVP；World 为趣味展示非竞争排名

**Evidence**:

- `specs/gameplay/06-feedback-loop.md` L337-338:
  ```
  - 无自动匹配、无天梯排名、无赛季
  - Tournament/League 为 P1+ 上层编排，通过多场 Room Match 组合实现（不在 P0 MVP 范围）
  ```
  ✅ Tournament 已明确排除 P0 MVP 范围

- `specs/gameplay/06-feedback-loop.md` L327: "趣味展示（非竞争排名）：殖民地年龄、GCL、房间数——仅供观赏" ✅
- `specs/gameplay/06-feedback-loop.md` L354: "回放排行榜（非竞争展示）" ✅

- 无 Tournament 在 MVP 语境的残留 ✅
- World 展示明确标记为非竞争 ✅

---

## 汇总

| # | 项 | 类型 | 状态 |
|---|----|------|:--:|
| B3 | Tick budget 500ms→hard ceiling, ref engine.md | REOPEN | CLOSED |
| B4 | MCP tool count (54)→(56), Authority note | REOPEN | CLOSED |
| R3 | tick-protocol snapshot → pure ref snapshot-contract | WEAK | CLOSED |
| R4 | sandbox/IDL host ABI → api-registry authority | WEAK | CLOSED |
| R5 | 08-api-idl RangedAttack=150, Recycle=proportional | WEAK | CLOSED |
| R6 | leaderboard→Arena, world_stats→Play | WEAK | CLOSED |
| R7 | CodeSigning 7d→30d, CSR replay unified | WEAK | CLOSED |
| R8 | feedback-loop Tournament→房间制+非竞争 | WEAK | CLOSED |

**无 GAP，无 PARTIAL，无新发现。**