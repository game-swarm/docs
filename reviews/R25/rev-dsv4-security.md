# Swarm 设计评审 R25 — Security Closure Verification

## 裁决概要

- 本轮性质：R25 Closure Verification — 验证 R24 B1-B6 与 D1-D4 的闭合情况
- 评审人：rev-dsv4-security (DeepSeek V4 Pro)
- 审阅范围：/data/swarm/docs/design/ + /data/swarm/docs/specs/
- 参考基线：/data/swarm/docs/reviews/R24/SPEAKER-VERDICT.md
- 审阅行数：~15,000 lines across 12 key documents

## Verdict

**CONDITIONAL_APPROVE**

6 个 B-items：3 CLOSED + 2 PARTIAL + 1 GAP
4 个 D-items：4 CLOSED

存在 1 个 GAP (B5 snapshot truncation model 分裂) 和 2 个 PARTIAL (B3 400/500ms 关系未文档化, B4 "已移除" 语言残留)，阻止 APPROVE。但无 Critical 安全回归，B6 auth 修复完整正确，经济数值全部收敛。

---

## B-items 逐项检查

### B1: Host Function ABI 统一到 api-registry.md 权威签名

**检查结果: CLOSED**

| 检查点 | 状态 | 证据 |
|--------|:----:|------|
| api-registry.md §4 为 canonical source | OK | §4 header: "WASM 模块通过 host function import 调用引擎服务。以下为权威签名与限制。" |
| host-functions.md 引用 api-registry | OK | L3: "权威源: game_api.idl.yaml → api-registry.md (生成)" |
| engine.md 引用 api-registry | OK | L396: "权威容量定义：所有容量上限和准入策略以 specs/reference/api-registry.md §5 为准" |
| host_get_terrain 签名一致 | OK | `(room_id: u32, out_ptr: i32, out_len: i32) -> i32` — api-registry §4.1 ≡ host-functions L23 |
| host_path_find 签名一致 | OK | `(from_x, from_y, to_x, to_y, opts_ptr, opts_len, out_ptr, out_len) -> i32` — 两文档一致 |
| host_get_world_rules 签名一致 | OK | `(rule_id_ptr, rule_id_len, out_ptr, out_len) -> i32` — 两文档一致 |
| host_get_world_config 签名一致 | OK | `(key_ptr, key_len, out_ptr, out_len) -> i32` — 两文档一致 |
| host_get_objects_in_range 签名一致 | OK | `(x, y, range, out_ptr, out_len) -> i32` — 两文档一致 |
| 函数总数 5 | OK | api-registry §4: "共计 5 个函数"; host-functions §允许的 Import: 5 |
| 权威链 IDL → api-registry → 其他文档 | OK | api-registry header: "冲突时以 IDL YAML 为准"; 其他文档引用 api-registry |

**安全评估**: Host function ABI 现已收敛。api-registry.md 声明为生成自 IDL 的单一权威源，host-functions.md 和 engine.md 均以引用方式接入。在 replay 确定性视角下，abi_version (api-registry §4.5 列出了 9 个错误码优先级) 已被纳入 TickTrace envelope (§6 字段 20: host_abi_version)，replay 一致性可验证。无安全残余。

---

### B2: 经济数值对齐 economy.idl.yaml

**检查结果: CLOSED**

| 检查点 | 状态 | 证据 |
|--------|:----:|------|
| resource-ledger.md 为单一经济权威 | OK | L7: "本文档为 Swarm 经济系统的唯一设计/数学权威" |
| economy-balance-sheet.md 引用 resource-ledger | OK | L151: "Resource Ledger 为所有收支计算的单一权威源" |
| global_transfer_delay 统一 100 tick | OK | resource-ledger §2.1: 100; snapshot-contract §3.1: 100; api-registry: 100 |
| RangedAttack cost 统一 150 | OK | api-registry §10.2 (SpawnCost): RANGED_ATTACK=150; 无冲突值 |
| Recycle refund lifespan-proportional | OK | resource-ledger §2.5: 10%-50% formula; api-registry §10.2: 同公式; economy-balance-sheet §5: 引用 |
| Per-player drone cap 统一 50 | OK | api-registry §5.1: "Per-player drone cap = 50"; engine.md §3.4.2: 50 |
| Building costs 一致性 | OK | api-registry §10.2: Spawn=300, Extension=200, ...; economy-balance-sheet 引用 api-registry |
| 定点类型替代 f64 | OK | api-registry §0: Fixed-Point Type Registry — 8 种定点类型; economy.idl.yaml 使用 BasisPoints/MilliUnits |

**安全评估**: 经济数值已从 R24 的 multi-source drift 收敛到 resource-ledger.md + api-registry.md 双权威（前者为数学/公式权威，后者为 machine schema）。所有费率与成本参数可追踪到单一源。从 security 视角：经济数值的一致性直接影响 fairness — 玩家 AI 策略训练的数值若与实际 runtime 不同，会产生 exploitable gap。当前闭合良好。

---

### B3: Tick budget 对齐

**检查结果: PARTIAL**

| 检查点 | 状态 | 证据 |
|--------|:----:|------|
| engine.md 建立唯一 tick budget table | OK | §3.4.1: 完整的 World/Arena 双模式 budget table，含 COLLECT/EXECUTE/SNAPSHOT/COMMIT/BROADCAST |
| World EXECUTE budget 400ms | OK | engine.md §3.4.1 |
| World SNAPSHOT budget 200ms p95 | OK | engine.md §3.4.1 |
| Arena SNAPSHOT budget 50ms p99 | OK | engine.md §3.4.1 |
| Arena 独立 budget | OK | engine.md L398: "Arena 使用独立的 tick/collect/simulate budget" |
| Budget sum constraint | OK | engine.md §3.4.2 推导 500/1000 player capacity 时验证 budget sum |
| **400ms budget vs 500ms timeout 关系未文档化** | **GAP** | tick-protocol.md §1.4: EXECUTE 超时=500ms; engine.md: EXECUTE budget=400ms。二者可能为 budget vs timeout (100ms headroom)，但文档未显式声明此关系 |
| Benchmark gate 绑定 | OK | snapshot-contract.md §7.1: "SLO (target) / Hard Budget (拒绝阈值)" 双列，含 admission decision formula |

**安全评估**: 主要闭合良好。engine.md 已建立双模式 budget table，Arena 独立预算明确，sum constraint 在 capacity derivation 中验证。PARTIAL 扣分项：tick-protocol.md 的 EXECUTE 超时 500ms 与 engine.md budget 400ms 的关系未文档化。实现者可能错误地把 500ms 当作 budget 而非 timeout ceiling。建议在 tick-protocol.md §1.4 显式标注 "此值为 hard timeout ceiling；budget target 见 engine.md §3.4.1 (400ms)"。

从 security 视角：超时与 budget 的边界不清会导致 sandbox worker 资源分配歧义，尤其在 overload/dos 场景下 admission decision 基于 budget 计算而非 timeout，但 worker 实际以 timeout 为 kill 信号。当前已有 admission model (snapshot-contract §7.2) 以 p95 metrics 动态调节 admitted players，可缓解此缺口，但不替代显式文档。

---

### B4: MCP 工具清单 54→56

**检查结果: PARTIAL**

| 检查点 | 状态 | 证据 |
|--------|:----:|------|
| api-registry.md §3 工具总数 56 | OK | "共计 56 个活跃工具 (game_api) + 11 个 Auth API 工具 (auth_api)" |
| mcp-tools.md 工具总数 56 | OK | §工具总览: "Game API 小计 56" |
| mcp-security.md 引用 api-registry 56 | OK | L223: "MCP 工具权威清单见 API Registry §3.2 — 56 工具" |
| **mcp-security.md §4.5 "已移除的旧工具" 语言残留** | **GAP** | L267: "已移除的旧工具：swarm_explain_last_tick（替换为 swarm_get_tick_trace）"; L275: "已移除的旧工具：swarm_get_schema、swarm_get_docs、swarm_get_available_actions（已整合至 SDK 和 API Registry）"。这些工具在 api-registry.md 中均为 active！ |
| onboarding tools 不在 security spec 中被标为移除 | PARTIAL | 工具未被删除（正确），但 "已移除" 措辞仍然存在（错误） |

**安全评估**: MCP 工具总数已正确统一为 56，api-registry 为 canonical source 的权威链已建立。但 R24 B4 的核心要求之一是 "删除 security spec 中'已移除但仍 active'的错误描述"，此项未完全满足。mcp-security.md §4.5 保留了 "已移除的旧工具" 措辞，即使 parenthetical 澄清 "已整合至 SDK 和 API Registry" 也不能消除安全性歧义——运维人员可能据此认为这些工具应被禁用。

具体矛盾：
- `swarm_explain_last_tick`: api-registry.md §3.2 Debug 中为 active tool (scope swarm:debug, 10/tick)。mcp-security.md 称其 "替换为 swarm_get_tick_trace" 但两个工具在 Registry 中并存。
- `swarm_get_docs`, `swarm_get_schema`, `swarm_get_available_actions`: api-registry.md §3.2 Onboarding 中为 active tools。mcp-security.md 称 "已整合至 SDK 和 API Registry" 但实际上它们仍是独立 MCP 工具入口。

建议将 mcp-security.md §4.2-4.5 的 "已移除的旧工具" 全部改为 "Authority note" 风格——标注哪些工具在 API Registry 中有 canonical definition，而非声称移除。

---

### B5: Snapshot 截断统一到 snapshot-contract 权威

**检查结果: GAP**

| 检查点 | 状态 | 证据 |
|--------|:----:|------|
| snapshot-contract.md §1 为 canonical 截断算法 | OK | §1.3-1.4: distance bucket (0-6) + entity_id 字典序 + 关键实体不可截断列表 |
| engine.md 引用 snapshot-contract 为权威 | OK | L421: "权威截断合同见 Snapshot Contract §1"; L422: 概述匹配 snapshot-contract |
| **tick-protocol.md §2.3 使用不同截断模型** | **GAP** | tick-protocol: 分桶权重模型 (关键桶/高优先/中优先/低优先) with sort key `(distance_to_drone, entity_id)`; snapshot-contract: 纯距离桶模型 (bucket 0-6) with sort key `entity_id` only |

**详细差异分析**:

| 维度 | snapshot-contract.md §1.3 (canonical) | tick-protocol.md §2.3 (冲突) |
|------|---------------------------------------|------------------------------|
| 桶定义 | 距离桶 0–6（0=自身, 1=相邻, 2=近距, 3=中距, 4=远距, 5=超远, 6=视野外） | 功能桶（关键桶/高优先/中优先/低优先） |
| 桶性质 | 纯距离——实体分类仅取决于距 drone 的格数 | 功能性——按实体角色分类（己方 drone → 高优先；敌方 → 中优先；中立 → 低优先） |
| 排序键 | entity_id 字典序（单键） | `(distance_to_drone, entity_id)` 双键 |
| 截断方向 | 从最远桶末尾开始移除 | 从低优先桶开始移除 |
| 关键实体保护 | 显式列表：自身/Controller/target/己方drone/攻击者 | 关键桶概念：Spawn/Controller/depot/storage |

**为什么这是 GAP 而非 PARTIAL**: 这两个模型在实现层面会产生不同的截断结果。给定相同的世界状态和 player view，tick-protocol 模型可能保留一个 5 格外的高优先己方 drone 而丢弃一个 3 格外的中优先敌方实体；snapshot-contract 模型则会保留 3 格实体（距离优先）而丢弃 5 格实体。这直接影响 WASM tick() 输入，进而影响 replay determinism。

**安全影响**: 若 tick 引擎实现时选择其中一个模型、replay verifier 实现另一个，将产生 replay divergence——相同 tick/seed/commands 产生不同 world state。这是 C1-level 确定性破坏。虽然当前 engine.md 引用 snapshot-contract 为权威，但 tick-protocol.md 作为核心流程规范，其冲突模型对实现者有直接误导效应。

**修正要求**:
1. tick-protocol.md §2.3 的快照构建截断描述必须替换为对 snapshot-contract.md §1.3 的引用
2. `sort_and_truncate` pseudocode 中的分桶逻辑须对齐到 distance bucket model
3. `omitted_categories` 字段格式须对齐到 snapshot-contract §1.2 的三分类 (entities/resources/events)
4. 截断确定性保证 (tick-protocol L164-167) 可从 snapshot-contract §1.5 推导——保留但对齐排序键声明

---

### B6: Auth CSR Replay Class + CodeSigning TTL 30-180d

**检查结果: CLOSED**

| 检查点 | 状态 | 证据 |
|--------|:----:|------|
| swarm_submit_csr replay class 单一 | OK | auth.md §5.6a: `non_idempotent_mutation`, 机制 "FDB 事务内消费 PoW challenge，一次性"。不再同时标为 idempotent 与 non-idempotent |
| swarm_submit_csr 消费 challenge 语义 | OK | auth.md §5.2: 服务端验证步骤 1 "challenge_id 存在、未过期、未消费"; §5.6a: "FDB 事务内消费 challenge" |
| CodeSigningCertificate TTL 单一范围 | OK | auth.md §5.3: "30–180 days（默认 7d，world.toml 可配）"。不再有 30d/90d/365d 三值冲突 |
| 所有用途证书 TTL 表统一 | OK | auth.md §5.3 表格: ClientAuthCertificate 24h / CodeSigning 30-180d / Admin 1h / Federation 24h |
| 证书过期语义明确 | OK | auth.md §5.4 完整描述 expired cert 对已部署模块的影响 |
| Deploy schema 对齐 api-registry | OK | api-registry.md §11: swarm_deploy output 含 deploy_id, accepted, validation_errors, fdb_version_counter, object_store_key |
| Refresh token grace 并发语义 | OK | api-registry.md §9 Refresh Token: "single-use; each refresh issues new refresh token and revokes old one; Family Tracking: reuse triggers revocation of entire family" |
| Admin 双签要求 | OK | auth.md §5.6b 授权矩阵: "swarm_admin_create_password_reset admin_critical dual-audit"; §5.3: "敏感操作可要求双签" |

**安全评估**: B6 是 R24 中最复杂的 auth security 修复项，现已完整闭合。关键修复：
- CSR replay class 从 self-contradiction 收敛为 `non_idempotent_mutation` + FDB 事务内 challenge 消费——此机制与 deploy_mutation 的 FDB version_counter 形成一致的防重放架构
- CodeSigningCertificate TTL 从 3 个冲突值收敛为单一 range (30-180d, default 7d)，并通过 §5.4 明确过期语义（已部署模块继续运行，重新部署需新证书签名）
- Refresh token 的 family tracking + single-use rotation 给出了并发安全的实现级语义
- Admin 双签在授权矩阵中已标注 `dual-audit`

从 security reviewer 视角：代码签名证书的 7d 默认 TTL 合理——平衡了 key rotation 安全性与 AI agent 运维负担（agent 需定期 renew）。证书过期不影响已部署 WASM 模块运行的设计，消除了 "证书过期 → 已部署 AI 策略全部失效" 的 availability 风险。

---

## D-items 逐项检查

### D1: Arena 房间制优先

**检查结果: CLOSED**

| 检查点 | 状态 | 证据 |
|--------|:----:|------|
| P0 以 Room Match 为主 | OK | modes.md §9.1: "Arena P0 以房间制比赛为核心——玩家创建比赛房间" |
| Tournament/League 为 P1+ | OK | modes.md §9.1: "Tournament/League 为 P1+ 上层编排，通过多场 Room Match 组合实现" |
| Room-based creation flow | OK | modes.md §9.1.1-9.1.3: 创建→配置→锁定WASM→比赛→结算→回放 |
| 无自动匹配/天梯/赛季 | OK | modes.md §9.1: "无自动匹配、无天梯排名、无赛季" |

**安全评估**: Arena 模型已从 R24 的 room vs tournament 歧义收敛。房间制作为 P0 有利于竞技公平性——每场比赛状态隔离、WASM 锁定、确定性 seed 可复现。无自动匹配减少了 matchmaking 层面的隐私/操控风险。CLOSED。

---

### D2: World 非竞争统计

**检查结果: CLOSED**

| 检查点 | 状态 | 证据 |
|--------|:----:|------|
| World 不设竞争榜单 | OK | modes.md §9 表格: "领土平衡...World 不设竞争榜单" |
| leaderboard 工具限于 Arena | OK | modes.md §9.1.5: PvE 排行榜按 scenario+difficulty 分组; api-registry §3.2 Arena: swarm_tournament_* tools, swarm_match_result |
| World leaderboard 语义不在 MCP 中暴露为 competitive | OK | api-registry §3.2 Play: swarm_get_leaderboard 未在 World 安全模型中激活 competitive ranking |

**安全评估**: D2 决策 (Option B: 允许非竞争型统计但不叫 leaderboard) 已落实。modes.md 明确 World "不设竞争榜单"，Arena 排行榜局限于 Arena 上下文。World 中 swarm_get_leaderboard 的 scope 限于 Arena/analytics 使用，World 玩家不暴露 competitive ranking。CLOSED。

---

### D3: Recycle lifespan-proportional

**检查结果: CLOSED**

| 检查点 | 状态 | 证据 |
|--------|:----:|------|
| lifespan-proportional 公式为权威 | OK | resource-ledger.md §2.5: `refund = body_cost × remaining_lifespan/total_lifespan × recycle_refund_base/10000`, clamp [10%, 50%] |
| api-registry.md 引用同公式 | OK | api-registry §10.2 RecycleRefund: 同公式, recycle_refund_base=5000bp, recycle_refund_min=1000bp |
| economy-balance-sheet.md 引用 | OK | §5: "RecycleRefund → Resource Ledger §6 (lifespan 10%–50%)" |
| 新手保护保留 | OK | resource-ledger.md: "新手保护（Tutorial 前 500 tick）退还 100%，world.toml tutorial_recycle_refund_full_ticks 控制" |

**安全评估**: Recycle 从 R24 的 flat 50% vs lifespan-proportional 冲突收敛为 lifespan-proportional model。此模型从经济安全视角更优——消除了 "建了立刻拆套利" 的 exploit，同时通过新手保护期保留 onboarding 友好性。CLOSED。

---

### D4: Snapshot budget 分模式 Arena 50ms/World 200ms

**检查结果: CLOSED**

| 检查点 | 状态 | 证据 |
|--------|:----:|------|
| World Snapshot: 200ms p95 | OK | engine.md §3.4.1; snapshot-contract.md §7.1 |
| Arena Snapshot: 50ms p99 | OK | engine.md §3.4.1 |
| 分模式 budget table | OK | engine.md §3.4.1: 完整 World / Arena 双列 budget |
| Arena tick interval 300ms | OK | modes.md §9.1.2: `tick_interval_ms = 300` |

**安全评估**: Snapshot budget 已按 D4 决策 (A for Arena, B for World) 落实。从安全视角：Arena 的 50ms p99 + 300ms tick interval 比 World 的 200ms p95 + 3000ms interval 更严格，这与 Arena 的公平实时性需求一致。但需要确认 tick-protocol.md 中是否反映了 Arena tick interval 差异——当前 tick-protocol §1.4 的状态机以 2500ms/500ms 为参数，仅描述 World 模式。Arena 的 300ms/200ms/50ms/50ms 状态机在 tick-protocol 中缺失。这是文档完整性 gap，非安全性 gap——因为 engine.md §3.4.1 已提供 Arena budget table 为权威。若想提升为严格闭合，建议在 tick-protocol.md 中增加 Arena 模式 tick 状态机或明确声明 "Arena 模式参数见 engine.md §3.4.1 Arena 列"。

---

## 安全方向专项检查

### S-CV1: Overload 受害者信息不对称

R24 ML-10 (Overload 受害者信息不对称) 的处理方式检查：当前文档中 Overload 特殊攻击 (api-registry §1.3 #16) 描述为 "Reduce target fuel budget"，但未明确受害者是否可感知被 Overload。从安全视角这是有意设计——若受害者可感知，则攻击的信息不对称价值降低。建议在 design 中补充 design rationale，明确这是 "有意设计 (by design)" 还是 "待补充 (TBD)"。**非 blocking，作为 Low 备注。**

---

## 统计

| 类别 | CLOSED | PARTIAL | GAP | 合计 |
|------|:------:|:-------:|:---:|:----:|
| B-items | 3 (B1,B2,B6) | 2 (B3,B4) | 1 (B5) | 6 |
| D-items | 4 (D1-D4) | 0 | 0 | 4 |
| **合计** | **7** | **2** | **1** | **10** |

CLOSED Rate: 7/10 = 70%

---

## 修正建议（优先级排序）

### P0 — 必须修复（阻止 APPROVE）

1. **B5-GAP: tick-protocol.md §2.3 快照截断模型对齐到 snapshot-contract.md**
   - 将 tick-protocol §2.3 的功能性分桶模型替换为 distance bucket model (0-6)
   - 将排序键从 `(distance_to_drone, entity_id)` 改为 `entity_id` 字典序
   - 将 `omitted_count` 改为 `omitted_categories: {entities, resources, events}` 三字段
   - $2.3 首行增加显式引用: "截断算法权威定义见 snapshot-contract.md §1.3–1.4"

### P1 — 建议修复（阻止无条件 APPROVE，不阻止 CONDITIONAL_APPROVE）

2. **B4-PARTIAL: mcp-security.md §4.2-4.5 删除 "已移除的旧工具" 语言**
   - 将 "已移除的旧工具：X（替换为 Y）" 改为 "Authority note: X 的 canonical definition 见 API Registry §3.2; Y 为补充/替代工具"
   - 移除对 swarm_explain_last_tick 的 "替换为 swarm_get_tick_trace" 描述（两者在 Registry 中并存）

3. **B3-PARTIAL: tick-protocol.md §1.4 显式标注 EXECUTE timeout vs budget 关系**
   - 在 "超时: 500ms" 后增加: "(hard timeout ceiling; budget target 见 engine.md §3.4.1: ≤400ms)"

### P2 — 文档完整性（非 blocking）

4. tick-protocol.md 增加 Arena 模式参数声明或引用 engine.md §3.4.1 Arena 列
5. Overload 受害者感知设计 rationale 补充（ML-10 处置）

---

## 评审附件

- 审查文档清单: api-registry.md, host-functions.md, engine.md, tick-protocol.md, snapshot-contract.md, resource-ledger.md, economy-balance-sheet.md, economy.idl.yaml (via api-registry), mcp-tools.md, mcp-security.md (03-mcp-security.md), auth.md, modes.md, interface.md
- 参考基线: /data/swarm/docs/reviews/R24/SPEAKER-VERDICT.md
- R24 Security Reviewer 原始报告: /data/swarm/docs/reviews/R24/rev-dsv4-security.md
- 审查人: rev-dsv4-security (DeepSeek V4 Pro)
- 审查时间: 2026-06-20