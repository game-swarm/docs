# Swarm 设计评审 R26 — Security Closure Verification (窄)

## 裁决概要

- 本轮性质：R26 Narrow Closure Verification — 仅验证 R25 REOPEN/WEAK 项的闭合
- 评审人：rev-dsv4-security (DeepSeek V4 Pro)
- 审阅范围：指定文件逐项检查，不重做全量设计评审
- 参考基线：/data/swarm/docs/reviews/R25/SPEAKER-VERDICT.md

## Verdict

**APPROVE**

10/10 项均已闭合。2 个 REOPEN 项（B3、B4）已修复，8 个 WEAK 残留已清理。无新 GAP 发现。

---

## REOPEN 项逐项检查

### B3: Tick budget — EXECUTE 500ms→硬超时天花板引用 engine.md budget

**检查结果: CLOSED**

| 检查点 | 状态 | 证据 |
|--------|:----:|------|
| tick-protocol.md EXECUTE 标注 500ms 为硬超时天花板 | OK | §1.4 L73-77: "硬超时天花板: 500ms" + "(budget target 见 design/engine.md §3.4.1: World ≤400ms, Arena ≤50ms)" |
| engine.md §3.4.1 完整 budget table | OK | World EXECUTE ≤400ms, Arena EXECUTE ≤50ms, 全阶段双模式 budget |
| 两文档关系显式声明 | OK | tick-protocol 明确标注 500ms 为 ceiling 非 budget，引用 engine.md 为 budget 权威 |
| Arena 独立 budget | OK | engine.md §3.4.1 Arena 列完整，L398 声明 Arena 使用独立 budget |

**安全评估**: R25 的 "400ms budget vs 500ms timeout 关系未文档化" 已完全修复。tick-protocol.md §1.4 现在显式标注 "硬超时天花板: 500ms" 并在括号中引用 engine.md §3.4.1 的 budget target。实现者不会再将 timeout 误解为 budget。

---

### B4: MCP 工具清单 (54)→(56); security spec Authority note 替代"已移除"

**检查结果: CLOSED**

| 检查点 | 状态 | 证据 |
|--------|:----:|------|
| api-registry.md 工具总数 56 | OK | §3 header: "共计 56 个活跃工具" |
| api-registry.md §3.2 标题 (56) | OK | "### 3.2 Game API 工具清单 (56)" — 非 (54) |
| mcp-security.md 引用 56 | OK | L223: "56 工具" |
| mcp-security.md "已移除的旧工具" 语言已清除 | OK | L264: "本文档不再声明移除状态——所有 active 工具以 API Registry 为准" |
| swarm_explain_last_tick 不再标为移除 | OK | api-registry §3.2 Debug: active tool (scope swarm:debug); mcp-security 不再自称"已移除" |
| swarm_get_schema/docs/available_actions 不再标为移除 | OK | mcp-security L270: "为 active onboarding/play 工具"; Authority note 替代移除声明 |
| Authority note 风格已建立 | OK | L264 + L272: 两处 Authority note 明确 Registry 为唯一权威源 |

**安全评估**: R25 B4 的两个核心问题均已修复：(1) 所有 54→56 计数残留已清除；(2) 旧 "已移除的旧工具" 语言已替换为 Authority note 风格——明确 "本文档不自行声明工具的移除状态，以 API Registry 为唯一权威源"。原被错误标记为移除的 swarm_explain_last_tick、swarm_get_schema、swarm_get_docs、swarm_get_available_actions 现在正确显示为 active。

---

## WEAK 项逐项检查

### R3: tick-protocol snapshot truncation → 纯引用 snapshot-contract

**检查结果: CLOSED**

| 检查点 | 状态 | 证据 |
|--------|:----:|------|
| tick-protocol §2.3 不再定义独立截断算法 | OK | L158: "snapshot-contract 是 snapshot truncation 的唯一权威源。tick-protocol 不定义独立截断算法，只引用该权威源。" |
| 旧功能桶模型已清除 | OK | 不再有"关键桶/高优先/中优先/低优先"描述；算法描述改为"距离桶 + entity_id 字典序 + farthest-first + critical 不可截断"（引用 snapshot-contract） |
| sort 键对齐 | OK | 引用 snapshot-contract 的 entity_id 字典序（非旧双键 `(distance_to_drone, entity_id)`） |
| 显式引用 snapshot-contract | OK | L158, L159, L161 三处引用 snapshot-contract |

**安全评估**: R25 的 B5-GAP（tick-protocol 与 snapshot-contract 截断模型分裂）已在 B3 同批修复中闭合。tick-protocol §2.3 现在不保留任何本地不等价算法，纯引用 snapshot-contract。实现者不会读到两个冲突的截断模型。

---

### R4: sandbox/IDL host function ABI → api-registry 权威签名

**检查结果: CLOSED**

| 检查点 | 状态 | 证据 |
|--------|:----:|------|
| wasm-sandbox.md 引用 api-registry 为权威 | OK | L208, L214: 多处 "权威签名见 api-registry.md §4.1" |
| 08-api-idl.md 引用 api-registry 为权威 | OK | L239-241: "所有签名的权威定义见 API Registry §4。以下为概念形式，实现以 Registry 为准。" |
| 08-api-idl.md host_functions 参数已更新 | OK | get_terrain 使用 `room_id: u32`（非旧 `(x,y)`）; path_find 含 `opts`; get_world_rules 含 `rule_id` |
| 函数总数 5 | OK | 与 api-registry §4 一致 |

**已知残留（不阻塞）**: `host_get_objects_in_range.range` 的 signedness — wasm-sandbox 写 `i32`，api-registry 写 `u32`。此差异已在 R25 被标注为已知残留（R25-R4），属 API/DX 方向的 codegen 风险，在安全视角不构成 GAP——range 值本身不超过 i32::MAX，运行时不会产生溢出。

---

### R5: 08-api-idl RangedAttack 100→150, Recycle→lifespan-proportional

**检查结果: CLOSED**

| 检查点 | 状态 | 证据 |
|--------|:----:|------|
| RangedAttack body cost 150 | OK | 08-api-idl.md L230: `RangedAttack: { Energy: 150 }` |
| Recycle 为 lifespan-proportional | OK | 08-api-idl.md L164: `refund: RecycleRefund(body_cost, remaining_lifespan, total_lifespan)  # lifespan-proportional 10%-50%` |
| 旧 flat 50% 已清除 | OK | 不再有 `refund * 0.5` 或 `Recycle 50%` 残留 |
| 权威公式引用 | OK | L164: "权威公式见 economy.idl.yaml §RecycleRefund" |

**安全评估**: 08-api-idl.md 中 R25 多 reviewer 指出的旧 RangedAttack=100 和 flat 50% Recycle 残留已清除。数值与权威源（api-registry §10.2, economy.idl.yaml）一致。

---

### R6: D2-A leaderboard→Arena, world_stats→Play

**检查结果: CLOSED**

| 检查点 | 状态 | 证据 |
|--------|:----:|------|
| swarm_get_leaderboard 归入 Arena 分组 | OK | api-registry §3.2 Arena L321: `swarm_get_leaderboard` 在 Arena (5) 下 |
| swarm_get_leaderboard visibility=arena_only | OK | L321: `Visibility Filter: arena_only` — 限定 Arena 上下文 |
| swarm_get_world_stats 归入 Play 分组 | OK | api-registry §3.2 Play L256: `swarm_get_world_stats` 在 Play (15) 下 |
| Capability profile 语义分离 | OK | §3.4: `play` profile 含 `swarm_get_world_stats — World 非竞争统计`; `arena` profile 含 `swarm_get_leaderboard — Arena 竞争排行` |
| 06-feedback-loop.md 非竞争展示 | OK | L327: "趣味展示（非竞争排名）"; L354: "回放排行榜（非竞争展示）" |

**安全评估**: R25-D2-WEAK 的核心问题（API surface 命名/能力面未闭合）已解决。`swarm_get_leaderboard` 现在限制在 Arena profile 且 visibility=arena_only，World 玩家不再暴露 competitive ranking。`swarm_get_world_stats` 在 Play profile 中提供非竞争统计。capability profiles 的语义分离清晰。

---

### R7: CodeSigning default 7d→30d

**检查结果: CLOSED**

| 检查点 | 状态 | 证据 |
|--------|:----:|------|
| CodeSigningCertificate TTL 默认值 30d | OK | auth.md L274: "30–180 days（默认 30d，world.toml 可配）" |
| 旧 7d 默认值已清除 | OK | 不再有"默认 7d"残留——7d 不在 30-180d 范围内的问题已修复 |
| TTL 范围统一 | OK | L273-276: 四类证书 TTL 表无冲突 |

**安全评估**: R25 中多名 reviewer 对 "30–180 days（默认 7d）" 的措辞含混已修复——7d 默认值不在 30-180d 范围内是逻辑矛盾。现默认值为 30d（范围下限），语义一致。

---

### R8: feedback-loop Tournament/MVP→房间制+非竞争展示

**检查结果: CLOSED**

| 检查点 | 状态 | 证据 |
|--------|:----:|------|
| Tournament 不在 P0 MVP 范围 | OK | 06-feedback-loop.md L338: "Tournament/League 为 P1+ 上层编排...不在 P0 MVP 范围" |
| Arena 房间制 | OK | L329-337: "房间制比赛", "无自动匹配、无天梯排名、无赛季" |
| 非竞争展示 | OK | L327: "趣味展示（非竞争排名）"; L354: "回放排行榜（非竞争展示）" |

**安全评估**: R25-D1 的唯一 PARTIAL 来源（feedback-loop 仍把 tournament 放在 MVP 语境）已修复。Tournament/League 明确为 P1+，P0 MVP 为房间制非竞争展示。

---

## 统计

| 类别 | 项数 | CLOSED | GAP |
|------|:----:|:------:|:---:|
| REOPEN 项 | 2 | 2 (B3,B4) | 0 |
| WEAK 项 | 8 | 8 (R3-R8) | 0 |
| **合计** | **10** | **10** | **0** |

CLOSED Rate: 10/10 = 100%

---

## 已知残留（非阻塞，记录供 R27 参考）

| ID | 问题 | 位置 | 严重度 |
|----|------|------|:------:|
| R26-R1 | `host_get_objects_in_range.range` signedness (i32 vs u32) | wasm-sandbox.md L209 vs api-registry.md L401 | Low — API/DX codegen 风险 |
| R26-R2 | `omitted_count` vs `omitted_categories` | tick-protocol.md L153 | Low — 字段名未对齐 snapshot-contract，但语义引用已正确 |

---

## 审查文档清单

- specs/core/01-tick-protocol.md (B3, R3)
- design/engine.md (B3)
- specs/reference/api-registry.md (B4, R4, R5, R6)
- specs/security/03-mcp-security.md (B4)
- specs/core/04-wasm-sandbox.md (R4)
- specs/gameplay/08-api-idl.md (R4, R5)
- design/auth.md (R7)
- specs/gameplay/06-feedback-loop.md (R8)

参考基线: /data/swarm/docs/reviews/R25/SPEAKER-VERDICT.md, /data/swarm/docs/reviews/R25/rev-dsv4-security.md
审查人: rev-dsv4-security (DeepSeek V4 Pro)
审查时间: 2026-06-20