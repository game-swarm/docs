# Swarm R26 Closure Verification — Performance Reviewer (DeepSeek V4 Pro)

> 审查日期: 2026-06-20 | 审查轮次: R26 (Closure Verification — Narrow)
> 范围: R25 REOPEN/WEAK 项的闭合验证
> 参考: /data/swarm/docs/reviews/R25/rev-dsv4-performance.md, R25 SPEAKER-VERDICT.md

## Verdict

**APPROVE** — All 8 items fully closed. No residual gaps.

---

## REOPEN 项（R25 PARTIAL/GAP → 已验证闭合）

### B3: Tick Budget — EXECUTE 500ms→硬超时天花板引用 engine.md budget | **CLOSED**

证据链:
- tick-protocol.md §3 (line 74): "硬超时天花板: 500ms" + 括号标注 "(budget target 见 design/engine.md §3.4.1: World ≤400ms, Arena ≤50ms)"
- engine.md §3.4.1 (line 290-298): 权威 budget table，World EXECUTE ≤400ms, Arena ≤50ms
- R25 残留（"tick-protocol.md EXECUTE 超时仍为 500ms，未更新为 engine.md 的 400ms"）的闭合方式：保留 500ms 为硬超时天花板（安全阀），增加 engine.md budget 引用（目标值）。500ms 硬天花板 + 400ms budget target 的双层设计合理——硬天花板防止级联超时，budget target 驱动正常 tick pacing。

无残留。CLOSED。

### B4: MCP 工具清单 (54)→(56); security spec Authority note | **CLOSED**

证据链:
- api-registry.md §3.2 heading (line 227): "### 3.2 Game API 工具清单 (56)" — 已从 54 更新为 56 ✅
- api-registry.md §3 intro (line 209): "共计 56 个活跃工具" — 计数正确
- mcp-security.md §4 (line 264): "> **Authority note**: 上述工具的 canonical definition 见 [API Registry §3.2](../reference/api-registry.md)。本文档不再声明移除状态——所有 active 工具以 API Registry 为准。" — Authority note 替代"已移除" ✅
- mcp-security.md §4 (line 224): "MCP 工具权威清单 见 API Registry §3.2 — 56 工具。" — 引用一致
- 实际工具计数: Onboarding 10 + Auth 2 + Play 15 + Deploy 7 + Debug 8 + Admin 6 + SDK 1 + Arena 5 + Resources 2 = **56** ✓

无残留。CLOSED。

---

## WEAK 项（R25 WEAK_CONFIRMED → 已验证清洁）

### R3: snapshot truncation→纯引用 snapshot-contract | **CLOSED**

证据链:
- tick-protocol.md §2.3 (line 157-161): "超限时的截断策略见 [Snapshot Contract §4](../specs/core/09-snapshot-contract.md) —— **snapshot-contract 是 snapshot truncation 的唯一权威源**。tick-protocol 不定义独立截断算法，只引用该权威源。截断算法（距离桶 + entity_id 字典序 + farthest-first + critical 不可截断）全部由 snapshot-contract 定义。"

R25 B5 GAP 的残留（"tick-protocol 仍使用语义桶模型 vs snapshot-contract 距离桶模型"）已完全清除：
- Old: 语义桶 (关键/高/中/低 4级, distance_to_drone + entity_id 升序)
- New: 纯引用 snapshot-contract (距离桶 0-6, entity_id 字典序, farthest-first, critical 不可截断)
- tick-protocol 不再包含任何独立截断算法描述
- engine.md §3.4.4 (line 419): "权威截断合同见 Snapshot Contract §1" — 引用链一致
- snapshot-contract.md §1.3: 距离桶模型 (0=self → 6=out of sight), entity_id 字典序, farthest-first
- snapshot-contract.md §1.4: critical 实体清单 (自身/Controller/target/己方 drone/攻击者) 永不截断

无残留。CLOSED。

### R4: sandbox/IDL host function ABI→api-registry 权威签名 | **CLOSED**

证据链:
- host-functions.md (line 1-3): "权威源: game_api.idl.yaml → api-registry.md (生成). 权威定义见 API Registry §4"
- 04-wasm-sandbox.md §3.2 (line 208-214): 每个 host function 注释中引用"权威签名见 api-registry.md §4.1"
- 08-api-idl.md §2 (line 239-241): "所有签名的权威定义见 API Registry §4"
- api-registry.md §4.1 (line 398-404): 5 个 host function 的 canonical ABI 签名
- 签名一致性验证通过 — 三处引用均指向 api-registry 为权威源

无残留。CLOSED。

### R5: 08-api-idl RangedAttack 100→150, Recycle→lifespan-proportional | **CLOSED**

证据链:

RangedAttack:
- 08-api-idl.md §2 body_cost (line 230): "RangedAttack: { Energy: 150 }" — 已从 100 更新为 150 ✅
- economy.idl.yaml §2.6 SpawnCost (line 329): "RANGED_ATTACK cost: 150" — 权威源一致 ✅
- api-registry.md §1.1 (line 54): RangedAttack 指令参数中有 range=3

Recycle:
- 08-api-idl.md §2 (line 164): "refund: RecycleRefund(body_cost, remaining_lifespan, total_lifespan) # lifespan-proportional 10%-50% (权威公式见 economy.idl.yaml §RecycleRefund)" ✅
- 08-api-idl.md §5.1 (line 322): "Recycle — 回收 drone，退还 lifespan-proportional body part 资源（10%-50%，详见 resource-ledger §2.5）" ✅
- economy.idl.yaml §2.1 RecycleRefund (line 59-93): lifespan-proportional formula, `refund_rate_bp = max(1000, (remaining_lifespan * 5000) / total_lifespan)`, 10%-50% ✅

无残留。CLOSED。

### R6: D2-A leaderboard→Arena, world_stats→Play | **CLOSED**

证据链:

leaderboard → Arena:
- api-registry.md §3.2 Arena (line 321): `swarm_get_leaderboard` visibility_filter: **`arena_only`** — 从 R25 的 "none" 更新为 "arena_only" ✅
- api-registry.md §3.4 `arena` profile (line 374): "Arena (含 swarm_get_leaderboard — Arena 竞争排行) | Arena host / 赛事管理员" ✅

world_stats → Play (非竞争):
- api-registry.md §3.2 Play (line 256): `swarm_get_world_stats` visibility_filter: "none" — World 模式下无限制，非竞争统计 ✅
- api-registry.md §3.4 `play` profile (line 370): "Play (含 swarm_get_world_stats — World 非竞争统计) | World 玩家，Arena spectator" ✅

设计文档一致:
- modes.md §9 table (line 24): "World 不设竞争榜单" — 与 leaderboard 的 arena_only 一致 ✅
- modes.md §9.1.5: PvE 排行榜按 scenario 分组，非跨场景混合 ✅

无残留。CLOSED。

### R7: CodeSigning default 7d→30d | **CLOSED**

证据链:
- auth.md §5.3 (line 274): "CodeSigningCertificate: 30–180 days（默认 30d，world.toml 可配）" — 已从 7d 更新为 30d ✅
- auth.md §5.4 (line 280-288): 过期语义 — 部署后不受证书过期影响，30d 默认窗口合理 ✅
- auth.md §5.5 (line 290-311): 多设备证书生命周期完整定义，常用设备推荐 30-180d ✅

无残留。CLOSED。

### R8: feedback-loop Tournament/MVP→房间制+非竞争展示 | **CLOSED**

证据链:
- 06-feedback-loop.md §6 World (line 328): "趣味展示（非竞争排名）：殖民地年龄、GCL、房间数——仅供观赏" ✅
- 06-feedback-loop.md §6 Arena (line 329-338): "房间制比赛...无自动匹配、无天梯排名、无赛季。Tournament/League 为 P1+ 上层编排，通过多场 Room Match 组合实现（不在 P0 MVP 范围）" ✅
- modes.md §9.1 (line 88): "Arena P0 以房间制比赛为核心" ✅
- modes.md §9.1.5: PvE Challenge 提供计时评分，非竞争展示 ✅

无残留。CLOSED。

---

## 性能专项补充验证

### 可扩展性
- engine.md §3.1a: 三级扩展策略完整（单实例→FDB 缓存→水平分片）
- engine.md §3.4.2: Worker pool 推导公式明确，admission control 使用 measured p95 动态调节
- 未发现结构性问题

### 并发安全
- tick-protocol.md §3.5: FDB 单事务提交, 3 次重试 + backpressure
- COLLECT 跨重试缓存 — 防止重复 WASM 执行
- 未发现 FDB 事务热点

### WASM 执行
- engine.md §3.4.3: long-lived worker pool + per-tick clean Store/Instance reset
- Fuel 预算: MAX_FUEL=10,000,000, MIN_FUEL=500,000
- 未发现 WASM 执行相关残留

### 延迟预算
- engine.md §3.4.1: 五阶段 budget table 完整（SNAPSHOT/COLLECT/EXECUTE/COMMIT/BROADCAST）
- World: SNAPSHOT≤200ms p95, EXECUTE≤400ms, COMMIT≤50ms p99
- Arena: SNAPSHOT≤50ms p99, EXECUTE≤50ms, COMMIT≤20ms p99
- 延迟预算分配清晰，无矛盾

### 峰值负载
- engine.md §3.4.2: 1000 hard cap 场景 per-player fuel 极度受限（2ms），新部署被拒
- Admission control hysteresis: 10 tick cooldown
- 降级模式: 连续 3 次放弃→降级→暂停新玩家加入
- 退化行为定义完整

---

## 总结表

| # | Item | Status | Evidence |
|---|------|--------|----------|
| B3 | Tick Budget | **CLOSED** | tick-protocol.md 500ms hard ceiling + engine.md 400ms budget ref |
| B4 | MCP Tools (56) + Authority note | **CLOSED** | api-registry.md §3.2 "(56)", mcp-security.md Authority note |
| R3 | Snapshot truncation → snapshot-contract | **CLOSED** | tick-protocol.md 纯引用 snapshot-contract, 旧语义桶已移除 |
| R4 | Host function ABI → api-registry | **CLOSED** | host-functions.md/wasm-sandbox/idl 均指向 api-registry §4 |
| R5 | RangedAttack 150, Recycle lifespan-proportional | **CLOSED** | 08-api-idl 150, economy.idl.yaml RecycleRefund formula |
| R6 | leaderboard→Arena, world_stats→Play | **CLOSED** | api-registry leaderboard arena_only, world_stats Play profile |
| R7 | CodeSigning 30d | **CLOSED** | auth.md §5.3 "默认 30d" |
| R8 | Tournament/MVP→房间制+非竞争展示 | **CLOSED** | feedback-loop §6, modes.md §9.1 |

**Verdict: APPROVE**

理由: R25 Closure Verification 中标记的 8 个 REOPEN/WEAK 项全部正确闭合。R25 的核心 GAP（B5 snapshot truncation 算法双轨）已在 R26 前通过将 tick-protocol.md 完全迁移到 snapshot-contract 引用解决。无新增性能视角发现的问题。所有修改在权威源间保持一致。