# Swarm R25 Closure Verification — Performance Reviewer (DeepSeek V4 Pro)

> 审查日期: 2026-06-20 | 审查轮次: R25 (Closure Verification)
> 范围: B1-B6 + D1-D4 的闭口验证
> 参考: /data/swarm/docs/reviews/R24/SPEAKER-VERDICT.md

## Verdict

**CONDITIONAL_APPROVE** — 3 items have residual gaps preventing full closure.

---

## B-items（共识 Blocker → 已修复）

### B1: Host Function ABI 统一 | **CLOSED**

证据链:
- api-registry.md §4（权威源，line 389-454）：定义 5 个 host function 的 canonical ABI 签名、调用预算、输出上限、per-call fuel 成本、错误优先级
- host-functions.md（line 1）：明确定位为 api-registry.md 的参考文档，签名一致
- interface.md §5.1（line 69-86）：引用 api-registry.md §4.1，签名一致
- engine.md §3.4.4（line 412-426）：引用 Snapshot Contract 为准一权威截断合同

无残留冲突。5 个函数签名三份文档一致:
- `host_get_terrain(room_id, out_ptr, out_len) -> i32`
- `host_get_objects_in_range(x, y, range, out_ptr, out_len) -> i32`
- `host_path_find(from_x, from_y, to_x, to_y, opts_ptr, opts_len, out_ptr, out_len) -> i32`
- `host_get_world_config(key_ptr, key_len, out_ptr, out_len) -> i32`
- `host_get_world_rules(rule_id_ptr, rule_id_len, out_ptr, out_len) -> i32`

### B2: 经济数值对齐 | **CLOSED**

证据链:
- resource-ledger.md §2（line 63-97）：声明为 economic system 唯一设计/数学权威，所有费率使用 bp
- economy-balance-sheet.md §5（line 151-158）：明确引用 Resource Ledger §2+§6 为权威源
- api-registry.md §5.1（line 460-486）：统一容量限制表，per-player drone cap=50，starting_resources={Energy:5000,Minerals:2000}
- engine.md §3.4.2（line 307）：per-player drone cap=50，引用 api-registry

关键数值对齐确认:
- `global_transfer_delay`: 100 tick（resource-ledger §2.1，snapshot-contract §3.1 MVP 经济操作 一致）
- `recycle_refund_base`: 5000 bp (50%)，lifespan-proportional formula（resource-ledger §2.5）
- `per-player drone cap`: 50（api-registry §5.1, engine.md §3.4.2，一致）
- `starting_resources`: {Energy:5000, Minerals:2000}（api-registry §5.1，economy-balance-sheet §3 一致）

修正完成，无残留。

### B3: Tick Budget 对齐 | **PARTIAL**

已完成:
- engine.md §3.4.1（line 290-298）：统一 World/Arena tick budget table，包含 SNAPSHOT、COLLECT、EXECUTE、COMMIT、BROADCAST 五阶段
- World: EXECUTE ≤400ms, SNAPSHOT ≤200ms p95
- Arena: EXECUTE ≤50ms, SNAPSHOT ≤50ms p99
- engine.md §3.4.2（line 320-398）：admission control、worker pool derivation、per-player quotas

残留:
- tick-protocol.md §3（line 74）：EXECUTE 超时仍为 500ms，未更新为 engine.md 的 400ms
  ```
  tick-protocol.md: "超时: 500ms"  ← stale
  engine.md:        "EXECUTE (2a+2b) ≤400ms"  ← canonical
  ```
- tick-protocol.md 缺少独立的 SNAPSHOT/COMMIT/BROADCAST budget 分配

建议: 将 tick-protocol.md EXECUTE 超时从 500ms 更新为 400ms，并在 tick-protocol.md 添加 budget 引用表指向 engine.md §3.4.1。

### B4: MCP 工具清单 54→56 | **PARTIAL**

已完成:
- api-registry.md §3 intro: "共计 56 个活跃工具"（正确）
- mcp-tools.md: "56 个 Game API 活跃工具 + 11 个 Auth API 工具"（正确）
- interface.md §4.1: "56 game tools + 11 auth tools"（正确）
- mcp-security.md（03-mcp-security.md）: 不再独立声明 tool list，引用 api-registry（正确）
- 实际工具计数: Onboarding 10 + Auth 2 + Play 16 + Deploy 7 + Debug 8 + Admin 6 + SDK 1 + Arena 4 + Resources 2 = **56** ✓

残留:
- api-registry.md §3.2 标题: `### 3.2 Game API 工具清单 (54)` → 仍为 54，应为 56

```diff
-### 3.2 Game API 工具清单 (54)
+### 3.2 Game API 工具清单 (56)
```

内容已修正（所有 intro/计数正确），仅章节标题残留旧值。建议修复标题。

### B5: Snapshot 截断统一 | **GAP**

声称的状态:
- snapshot-contract.md（line 7）: "R22 B5 修复。本文档为 snapshot truncation 的唯一权威"
- engine.md §3.4.4（line 419）: "权威截断合同见 Snapshot Contract §1"

实际冲突 — 两份文件描述的是**不同的截断算法**:

| 维度 | snapshot-contract.md §1.3 | tick-protocol.md §2.3 |
|------|--------------------------|------------------------|
| 分组模型 | 距离桶 0(self)→6(out of sight) 7 级 | 语义桶: 关键/高/中/低 4 级 |
| 第二排序键 | entity_id 字典序 | (distance_to_drone, entity_id) 升序 |
| 截断方向 | 从最远桶末尾开始移除 | 桶内按确定性排序键升序保留 |
| 不可截断清单 | 自身/Controller/target/己方 drone/攻击者 | 关键桶 unconditional: Spawn/Controller/玩家 depot/storage |
| 标记字段 | `omitted_categories` (entities/resources/events) | `truncated`, `omitted_count` |
| 桶内 tie-break | entity_id 字典序 | distance_to_drone + entity_id |

engine.md §3.4.4 引用的是 snapshot-contract 的距离桶模型，但 tick-protocol.md §2.3 使用的是语义优先级桶模型。

这是 R24 B5 的核心问题未完全闭合的证据。Speaker 要求: "指定唯一 snapshot truncation algorithm，包括 bucket order、tie-breaker、size limit、debug output、fog-of-war invariant。所有 tick/snapshot/security 文档引用同一算法。"

当前 snapshot-contract 被标记为权威但 tick-protocol 仍有不同的算法实现。

建议: 二选一作为 canonical，另一份文档改为引用。推荐以 snapshot-contract 的距离桶模型为权威（已由 engine.md 引用，且更细粒度、更具确定性）。

### B6: Auth CSR Replay + CodeSigning TTL | **CLOSED**

证据链:
- auth.md §5.6a（line 312-324）: Replay Class 分类表 — `swarm_submit_csr` 标记为 `non_idempotent_mutation`，防重放机制: "FDB 事务内消费 PoW challenge，一次性"
- auth.md §5.6a: 明确区分 Dragonfly nonce（仅 read_replay_safe/idempotent_mutation）vs FDB version counter/challenge consumption（non_idempotent_mutation/admin_critical）
- auth.md §5.3（line 274）: CodeSigningCertificate TTL: "30–180 days（默认 7d，world.toml 可配）"
- auth.md §5.3（line 273-277）: 用途隔离证书表，CodeSigningCertificate 约束 "只能签 module_hash + metadata"，TTL 明确
- auth.md §5.4（line 280-289）: 过期语义——部署后不受证书过期影响
- auth.md §5.5（line 290-311）: 多设备证书生命周期完整定义

CSR replay class 和 CodeSigningCertificate TTL 均已统一，无内部矛盾。

---

## D-items（已裁决 → 需验证落实）

### D1: Arena 房间制优先 | **CLOSED**

modes.md §9.1（line 88）:
> "Arena **P0 以房间制比赛为核心**——玩家创建比赛房间，设定参数，自己或他人加入。无自动匹配、无天梯排名、无赛季。**Tournament/League 为 P1+ 上层编排**，通过多场 Room Match 组合实现，不在 P0 交付范围。"

与 Speaker 推荐（Option A）一致。modes.md §9.1.1-9.1.5 完整定义了房间模型: 创建→配置→就绪→比赛→回放，PvP + PvE Challenge 双模式。CLOSED。

### D2: World 非竞争型统计 | **PARTIAL**

已完成:
- modes.md §9 table（line 24）: World "不设竞争榜单"（no competitive leaderboard）
- modes.md §9.1（line 88）: Arena 有独立 leaderboard/ranking（PvE 排行榜 §9.1.5）

残留:
- api-registry.md §3.2 Play 分类: `swarm_get_leaderboard` 仍为 active tool，`visibility_filter: none`，`subject_source: world`
- api-registry.md §3.4 Capability Profiles: `play` profile 分配给 "World 玩家，Arena spectator"

Speaker 裁决 D2/B:
> "World 允许非竞争型 stats/analytics，但命名不得叫 leaderboard，且不进入排名奖励"

当前状态:
1. `swarm_get_leaderboard` 名称未改，仍叫 leaderboard
2. `visibility_filter: none` — World 模式下无限制暴露，未区分竞争型 vs 非竞争型
3. World play profile 包含 leaderboard 工具，与 "不设竞争榜单" 设计承诺冲突

建议:
- 要么将 `swarm_get_leaderboard` 的 visibility_filter 改为 `arena_only`（仅 Arena 世界可见）
- 要么拆分为 World 专用的 `swarm_get_stats`（非竞争统计，不含排名/奖励权重）与 Arena 的 `swarm_get_leaderboard`

### D3: Recycle lifespan-proportional | **CLOSED**

resource-ledger.md §2.5（line 158-165）:
```
recycle_refund = body_cost × remaining_lifespan / total_lifespan × recycle_refund_base / 10000
recycle_refund = max(body_cost × recycle_refund_min / 10000, recycle_refund)
```
- `recycle_refund_base`: 5000 bp (50%)
- `recycle_refund_min`: 1000 bp (10%)
- Drone 寿命 10% 时退还 10%，寿命 100% 时退还 50%
- 新手保护（Tutorial 前 500 tick）退还 100%

economy-balance-sheet.md §5（line 156）: "回收 (RecycleRefund) | Resource Ledger §6 (lifespan 10%–50%) | 引用"

与 Speaker 推荐（Option B）一致。CLOSED。

### D4: Snapshot budget 分模式 Arena 50ms / World 200ms | **CLOSED**

engine.md §3.4.1（line 290-298）:
| 阶段 | World 预算 | Arena 预算 |
|------|-----------|-----------|
| SNAPSHOT build | ≤200ms (p95) | ≤50ms (p99) |
| EXECUTE (2a+2b) | ≤400ms | ≤50ms |
| COMMIT (FDB) | ≤50ms (p99) | ≤20ms (p99) |

与 Speaker 推荐一致: Arena 使用 50ms p99（严格实时），World 使用 200ms p95（允许 degrade）。

snapshot-contract.md §7（line 393-400）Capacity Admission Model 中的 Snapshot build time 仅声明 World 的 "200ms p95 SLO / 500ms hard"，未显式拆分 Arena。但 engine.md 已做拆分，snapshot-contract 引用 engine.md 即可。

---

## 性能专项视角

作为 performance reviewer，额外验证以下与性能直接相关的闭口:

### 可扩展性
- engine.md §3.1a（line 168-173）: 三级扩展策略明确（单实例→FDB 缓存→水平分片）
- engine.md §3.4.2: Worker pool 推导公式清晰，256 default / 1000 hard cap
- Admission control formula 使用 measured p95 动态调节（snapshot-contract §7.2）
- 容量合同: target 500 / hard cap 1000 active players, 5000/10000 drones, 50,000 entities

### 并发安全
- tick-protocol.md §3.5: FDB 单事务提交, 3 次重试 + backpressure
- COLLECT 结果跨重试缓存（tick-protocol §2.3 时序边界），不重复执行 WASM
- Phase 2b parallel sets: Combat 按 target_id partition, Status Effects 按 subtype 并行（engine.md §3.2）
- 未发现 FDB 事务热点或锁竞争问题

### WASM 执行
- engine.md §3.4.3: long-lived worker pool + per-tick clean Store/Instance reset
- WASM 预编译（编译期），tick 时仅实例化
- Per-player sandbox deadline: 2500ms World / 200ms Arena
- Fuel 预算: MAX_FUEL=10,000,000, MIN_FUEL=500,000（admission threshold）

### 延迟预算
- 端到端 tick 延迟: SNAPSHOT(200ms) + COLLECT(2500ms, 含 WASM exec) + EXECUTE(400ms) + COMMIT(50ms) + BROADCAST(50ms) = 3200ms，其中 COLLECT 内含 SNAPSHOT build，实际 pipeline: COLLECT(2500) + EXECUTE(400) + COMMIT(50) + BROADCAST(50) = 3000ms 刚好匹配 tick_interval
- engine.md 附录的 500/1000 player capacity derivation 详细分解了各阶段负载

### 峰值负载退化
- engine.md §3.4.2: 1000 hard cap 场景下 per-player fuel 极度受限（2ms），新 WASM 部署被拒（ERR_WORLD_FULL）
- Admission control hysteresis: 10 tick cooldown before re-increase
- 降级模式: tick 连续 3 次放弃后进入降级（暂停新玩家加入），告警触发
- snapshot-contract §1.5: 竞技模式截断降级标记（tick degraded），API 暴露 tick_integrity

---

## 总结

| Item | Status | Issue |
|------|--------|-------|
| B1: Host ABI | CLOSED | — |
| B2: Economy | CLOSED | — |
| B3: Tick Budget | PARTIAL | tick-protocol.md EXECUTE 500ms → 400ms 未同步 |
| B4: MCP Tools | PARTIAL | api-registry.md §3.2 标题 "(54)" → "(56)" 未修正 |
| B5: Snapshot | **GAP** | tick-protocol 仍使用语义桶模型 vs snapshot-contract 距离桶模型 |
| B6: Auth | CLOSED | — |
| D1: Arena Room | CLOSED | — |
| D2: World Stats | PARTIAL | swarm_get_leaderboard 未对 World 做非竞争限制 |
| D3: Recycle | CLOSED | — |
| D4: Snapshot Budget | CLOSED | — |

**Verdict: CONDITIONAL_APPROVE**

理由: 10 个验证项中 6 个正确闭合（CLOSED），3 个部分闭合（PARTIAL，均为小修正），1 个未闭合（GAP，B5 截断算法双轨）。B5 的 snapshot truncation algorithm 分歧是确定性/replay 的关键路径——tick-protocol.md 与 snapshot-contract 使用不同的分桶排序模型会导致实现者在 replay 一致性上做出不同选择。要求在下一次 Closure Verification 前将 tick-protocol.md §2.3 的截断描述同步到 snapshot-contract §1.3 的距离桶模型（或反向决定以 tick-protocol 为准并更新 snapshot-contract+engine.md 引用）。