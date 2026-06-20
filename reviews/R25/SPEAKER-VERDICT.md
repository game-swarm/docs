# Swarm 设计评审 R25 — Speaker Closure Verification 共识报告

## 裁决概要

- 本轮性质：Closure Verification（R5 pattern），不做开放式新评审，只验证 R24 指定 B1-B6 与 D1-D4 的闭合状态。
- 评审完成情况：14/14 reviewers 已完成，报告均位于 `/data/swarm/docs/reviews/R25/rev-*.md`。
- 阅读模式：Closure Verification 回退为全量阅读模式；不启用 Phase 1/Phase 2 CrossCheck。
- 闭合判定规则：CLOSED 票数 `>=10` → CONFIRMED；`>=7` → WEAK_CONFIRMED；`<7` → REOPEN。
- 总体收敛：B6、D1、D3、D4 已强确认闭合；B1、B2、B5、D2 弱确认闭合但仍有残留；B3、B4 未达闭合阈值，必须重开修复。
- Freeze 状态：未确认冻结。R25 未能达到 FREEZE_CONFIRMED。

## 总体 Verdict

**REOPEN**

理由：B3 Tick budget 对齐仅 4/14 CLOSED，B4 MCP 工具清单仅 4/14 CLOSED，均低于 7 票闭合阈值。即使多数核心设计方向已收敛，指定 Closure Gate 中仍有两个项目按规则必须 REOPEN。

## B-item 闭合矩阵

| ID | 问题 | CLOSED | PARTIAL | GAP | 闭合状态 | Speaker 判定 |
|----|------|:------:|:-------:|:---:|----------|---------------|
| B1 | Host Function ABI 统一到 api-registry.md 权威签名 | 7 | 3 | 4 | WEAK_CONFIRMED | 主权威源已建立，但 `04-wasm-sandbox.md`、`08-api-idl.md`、signedness 等残留需要清理 |
| B2 | 经济数值对齐 economy.idl.yaml | 8 | 4 | 2 | WEAK_CONFIRMED | 经济主线已闭合，但 `08-api-idl.md`、`game_api.idl.yaml`、snapshot economy boundary 残留仍被多名 reviewer 指出 |
| B3 | Tick budget 对齐 | 4 | 8 | 2 | REOPEN | 400ms / 500ms / no-standalone-timeout 与 Arena 分模式预算在 core spec 中仍不统一 |
| B4 | MCP 工具清单 54→56 | 4 | 7 | 3 | REOPEN | 56 主声明已修，但 `(54)` 标题、active tools 被标为 removed、IDL 分组注释/旧 anchor 残留仍广泛存在 |
| B5 | Snapshot 截断统一到 snapshot-contract 权威 | 7 | 2 | 5 | WEAK_CONFIRMED | snapshot-contract 权威方向成立，但 tick-protocol 旧语义桶算法仍被多方向判为未闭合 |
| B6 | Auth CSR Replay Class + CodeSigning TTL 30-180d | 11 | 2 | 1 | CONFIRMED | CSR replay 主线闭合；少数 reviewer 对 7d 默认值/365d generic max 仍有注释 |

### B1 方向 × 模型矩阵

| Reviewer | Status | 关键证据 |
|----------|--------|----------|
| rev-dsv4-security | CLOSED | api-registry / host-functions 签名一致 |
| rev-dsv4-architect | GAP | `interface.md`、`04-wasm-sandbox.md`、`08-api-idl.md` 仍有旧签名 |
| rev-dsv4-apidx | PARTIAL | `host_get_objects_in_range.range` `u32` vs `i32` |
| rev-gpt-determinism | PARTIAL | `08-api-idl.md` 仍保留旧 `get_terrain(x,y)` / `get_world_rules(out_ptr,out_len)` |
| rev-dsv4-performance | CLOSED | registry / host-functions / interface 签名一致 |
| rev-dsv4-determinism | CLOSED | 5 个 host function 跨文档无冲突 |
| rev-dsv4-economy | CLOSED | 无跨文档签名冲突 |
| rev-dsv4-designer | CLOSED | canonical source 足够清楚 |
| rev-gpt-architect | GAP | `04-wasm-sandbox.md` 仍旧 ABI 与 4 bytes 输出上限 |
| rev-gpt-performance | CLOSED | API Registry 为单一权威，核心签名同步 |
| rev-gpt-economy | CLOSED | Registry / host-functions 基本统一 |
| rev-gpt-apidx | PARTIAL | range signedness 漂移影响 SDK bindings |
| rev-gpt-designer | CLOSED | 设计层引用 Registry 足够 |
| rev-gpt-security | GAP | sandbox spec 仍旧 ABI / 输出上限 |

### B2 方向 × 模型矩阵

| Reviewer | Status | 关键证据 |
|----------|--------|----------|
| rev-dsv4-security | CLOSED | RangedAttack、Recycle、drone cap、building costs 对齐 |
| rev-dsv4-architect | GAP | `08-api-idl.md` RangedAttack=100、Recycle flat 50% 等残留 |
| rev-dsv4-apidx | CLOSED | 权威表与关键数值闭合 |
| rev-gpt-determinism | GAP | `game_api.idl.yaml` cap=500、snapshot-contract 旧经济边界 |
| rev-dsv4-performance | CLOSED | resource-ledger / api-registry 对齐 |
| rev-dsv4-determinism | PARTIAL | drone cap 命名歧义：50 vs 500 可能属不同层级 |
| rev-dsv4-economy | CLOSED | 经济方向确认全闭合 |
| rev-dsv4-designer | CLOSED | 策略/经济合同闭合 |
| rev-gpt-architect | PARTIAL | `08-api-idl.md` fixed 50% refund 残留 |
| rev-gpt-performance | CLOSED | economy IDL 与 Resource Ledger 闭合 |
| rev-gpt-economy | CLOSED | B2 主线闭合 |
| rev-gpt-apidx | PARTIAL | `08-api-idl.md` 旧 Recycle/RangedAttack 值 |
| rev-gpt-designer | CLOSED | gameplay / economy IDL 无直接冲突 |
| rev-gpt-security | PARTIAL | gameplay IDL / snapshot-contract 仍有旧经济值 |

### B3 方向 × 模型矩阵

| Reviewer | Status | 关键证据 |
|----------|--------|----------|
| rev-dsv4-security | PARTIAL | 400ms budget vs 500ms timeout 关系未文档化 |
| rev-dsv4-architect | PARTIAL | World/Arena budget sum 超 interval，无 backpressure 策略 |
| rev-dsv4-apidx | PARTIAL | tick-protocol 未同步 EXECUTE / Arena split |
| rev-gpt-determinism | PARTIAL | core tick spec 未完整体现 Arena normative branch |
| rev-dsv4-performance | PARTIAL | tick-protocol EXECUTE 500ms 残留 |
| rev-dsv4-determinism | PARTIAL | engine 400ms vs tick-protocol 500ms 漂移 |
| rev-dsv4-economy | CLOSED | 将 500ms 解释为 hard cutoff、400ms 为 target |
| rev-dsv4-designer | PARTIAL | 400ms budget 与 500ms timeout 缺少交叉引用 |
| rev-gpt-architect | GAP | 400ms/50ms vs 500ms/soft-deadline 多口径 |
| rev-gpt-performance | CLOSED | 认为 `tick-protocol.md` §8 与 engine 已一致 |
| rev-gpt-economy | GAP | 500ms / 400ms+50ms / no standalone timeout 三口径 |
| rev-gpt-apidx | CLOSED | design 已给预算，剩余归入 D4/B5 |
| rev-gpt-designer | CLOSED | 产品语义闭合 |
| rev-gpt-security | PARTIAL | DoS / admission control 预算合同仍不一致 |

### B4 方向 × 模型矩阵

| Reviewer | Status | 关键证据 |
|----------|--------|----------|
| rev-dsv4-security | PARTIAL | mcp-security 仍有 “已移除旧工具” 语言 |
| rev-dsv4-architect | CLOSED | 56 计数闭合 |
| rev-dsv4-apidx | CLOSED | 工具数量与 onboarding 状态闭合 |
| rev-gpt-determinism | GAP | registry 标题 54，security spec active/removed 冲突 |
| rev-dsv4-performance | PARTIAL | api-registry §3.2 标题 `(54)` 残留 |
| rev-dsv4-determinism | CLOSED | 工具总数与 capability profile 闭合 |
| rev-dsv4-economy | CLOSED | 经济方向未发现残留 |
| rev-dsv4-designer | PARTIAL | `(54)` 标题与 onboarding removed 语言残留 |
| rev-gpt-architect | GAP | registry 56/54 与 security removed 冲突 |
| rev-gpt-performance | PARTIAL | active/removed 状态残留 |
| rev-gpt-economy | PARTIAL | 54/46 heading/anchor/removed 状态残留 |
| rev-gpt-apidx | PARTIAL | security spec 仍把 active 工具标为 removed |
| rev-gpt-designer | PARTIAL | api-registry 标题 54、IDL Play 注释 14 tools |
| rev-gpt-security | GAP | registry 标题 54，security spec removed active tools |

### B5 方向 × 模型矩阵

| Reviewer | Status | 关键证据 |
|----------|--------|----------|
| rev-dsv4-security | GAP | tick-protocol 语义桶算法 vs snapshot-contract 距离桶算法 |
| rev-dsv4-architect | CLOSED | 认为无其他文档声明独立截断策略 |
| rev-dsv4-apidx | CLOSED | 认为 tick-protocol 已与 snapshot-contract 一致 |
| rev-gpt-determinism | PARTIAL | tick-protocol 仍保留不同算法 |
| rev-dsv4-performance | GAP | 两份文件描述不同算法 |
| rev-dsv4-determinism | CLOSED | 认为分桶权重截断一致 |
| rev-dsv4-economy | CLOSED | 认为不再存在三套策略 |
| rev-dsv4-designer | CLOSED | 距离桶与关键实体规则闭合 |
| rev-gpt-architect | PARTIAL | 算法收敛，budget/visibility 字段漂移 |
| rev-gpt-performance | CLOSED | 权威引用覆盖旧描述 |
| rev-gpt-economy | GAP | tick-protocol 仍保留旧截断算法 |
| rev-gpt-apidx | GAP | tick-protocol 旧算法分叉会影响 SDK/replay |
| rev-gpt-designer | CLOSED | 指定项上未见三套策略并存 |
| rev-gpt-security | GAP | tick-protocol/security visibility 仍双/三口径 |

### B6 方向 × 模型矩阵

| Reviewer | Status | 关键证据 |
|----------|--------|----------|
| rev-dsv4-security | CLOSED | CSR replay、TTL、refresh/admin 语义闭合 |
| rev-dsv4-architect | GAP | `swarm_submit_csr` 仍在 idempotent 示例；7d default 不在 30-180d 范围内 |
| rev-dsv4-apidx | CLOSED | FDB challenge consumption 与 TTL 主线闭合 |
| rev-gpt-determinism | CLOSED | non_idempotent / FDB challenge consumption 闭合 |
| rev-dsv4-performance | CLOSED | replay + TTL 统一 |
| rev-dsv4-determinism | CLOSED | replay class 与证书生命周期闭合 |
| rev-dsv4-economy | CLOSED | replay class 与 TTL 主线闭合 |
| rev-dsv4-designer | CLOSED | 产品级矛盾消除 |
| rev-gpt-architect | CLOSED | auth / command-source 已闭合 |
| rev-gpt-performance | PARTIAL | api-registry generic cert max 365d、IDL validity_days 未 profile 化 |
| rev-gpt-economy | PARTIAL | registry 365d 上限残留 |
| rev-gpt-apidx | CLOSED | 未再看到 CSR 双写残留 |
| rev-gpt-designer | CLOSED | replay / TTL 产品级闭合 |
| rev-gpt-security | CLOSED | 主线闭合，7d default 措辞仅为含混 |

## D-item 闭合矩阵

| ID | 决策项 | CLOSED | PARTIAL | GAP | 闭合状态 | Speaker 判定 |
|----|--------|:------:|:-------:|:---:|----------|---------------|
| D1 | Arena 房间制优先 | 13 | 1 | 0 | CONFIRMED | P0 Room Match 已强确认闭合；仅 feedback-loop MVP 语境仍有 Tournament 残留 |
| D2 | World 非竞争统计 | 7 | 7 | 0 | WEAK_CONFIRMED | 设计意图闭合，但 `swarm_get_leaderboard` 命名/API profile 仍争议很大 |
| D3 | Recycle lifespan-proportional | 10 | 3 | 1 | CONFIRMED | 主合同已强确认闭合；少量旧 50% 残留被并入 B2/08-api-idl 清理 |
| D4 | Snapshot budget 分模式 Arena 50ms / World 200ms | 10 | 2 | 2 | CONFIRMED | design/engine 强确认闭合；core spec / snapshot-contract 是否必须同步仍有少量分歧 |

### D1 方向 × 模型矩阵

| Reviewer | Status | 备注 |
|----------|--------|------|
| rev-dsv4-security | CLOSED | Arena P0 Room Match 明确 |
| rev-dsv4-architect | CLOSED | Tournament 为 P1+ |
| rev-dsv4-apidx | CLOSED | Option A 已写入 modes.md |
| rev-gpt-determinism | CLOSED | Room/match 为 P0 |
| rev-dsv4-performance | CLOSED | 房间模型闭合 |
| rev-dsv4-determinism | CLOSED | 无自动匹配/天梯/赛季 |
| rev-dsv4-economy | CLOSED | Option A 采纳 |
| rev-dsv4-designer | CLOSED | 第一小时竞技路径闭合 |
| rev-gpt-architect | CLOSED | Room Match 流程已是 P0 |
| rev-gpt-performance | CLOSED | Room Match 为核心 |
| rev-gpt-economy | PARTIAL | feedback-loop 仍把锦标赛放 MVP 语境 |
| rev-gpt-apidx | CLOSED | P0 房间制闭合 |
| rev-gpt-designer | CLOSED | 产品路径闭合 |
| rev-gpt-security | CLOSED | modes 明确 P0 房间制 |

### D2 方向 × 模型矩阵

| Reviewer | Status | 备注 |
|----------|--------|------|
| rev-dsv4-security | CLOSED | World 不设竞争榜单，工具按语义限定 |
| rev-dsv4-architect | CLOSED | 非竞争统计方向闭合 |
| rev-dsv4-apidx | CLOSED | 设计意图闭合 |
| rev-gpt-determinism | PARTIAL | `swarm_get_leaderboard` 仍全局 active |
| rev-dsv4-performance | PARTIAL | API 未限制 World leaderboard |
| rev-dsv4-determinism | CLOSED | leaderboard 属于 Arena profile |
| rev-dsv4-economy | CLOSED | World 禁用 competitive leaderboard |
| rev-dsv4-designer | PARTIAL | World 玩家仍可访问 leaderboard API |
| rev-gpt-architect | PARTIAL | visibility 仍有 public leaderboard / leaderboard_snapshot |
| rev-gpt-performance | CLOSED | gameplay 语义闭合 |
| rev-gpt-economy | PARTIAL | leaderboard API 命名残留 |
| rev-gpt-apidx | CLOSED | PvE leaderboard 限于 Arena challenge 语境 |
| rev-gpt-designer | PARTIAL | World showcase stats 与 leaderboard 未拆清 |
| rev-gpt-security | PARTIAL | API Registry 仍暴露 world leaderboard |

### D3 方向 × 模型矩阵

| Reviewer | Status | 备注 |
|----------|--------|------|
| rev-dsv4-security | CLOSED | lifespan-proportional 公式闭合 |
| rev-dsv4-architect | PARTIAL | `08-api-idl.md` flat 50% 残留 |
| rev-dsv4-apidx | CLOSED | 公式全闭合 |
| rev-gpt-determinism | GAP | snapshot-contract MVP boundary 旧口径 |
| rev-dsv4-performance | CLOSED | Resource Ledger 公式闭合 |
| rev-dsv4-determinism | CLOSED | bp 公式闭合 |
| rev-dsv4-economy | CLOSED | 无固定 50% 残留 |
| rev-dsv4-designer | CLOSED | timing decision 成立 |
| rev-gpt-architect | PARTIAL | `08-api-idl.md` 旧 refund 残留 |
| rev-gpt-performance | CLOSED | IDL / Registry / Ledger 闭合 |
| rev-gpt-economy | CLOSED | D3 闭合 |
| rev-gpt-apidx | PARTIAL | `08-api-idl.md` flat 50% 残留 |
| rev-gpt-designer | CLOSED | clamp 10%-50% 闭合 |
| rev-gpt-security | CLOSED | 主合同闭合，旧值并入 B2 |

### D4 方向 × 模型矩阵

| Reviewer | Status | 备注 |
|----------|--------|------|
| rev-dsv4-security | CLOSED | engine.md / modes.md 分模式 budget 闭合 |
| rev-dsv4-architect | CLOSED | Arena 50ms / World 200ms 已落实 |
| rev-dsv4-apidx | CLOSED | engine.md 为权威预算表 |
| rev-gpt-determinism | CLOSED | D4 闭合 |
| rev-dsv4-performance | CLOSED | 与 Speaker 推荐一致 |
| rev-dsv4-determinism | CLOSED | Snapshot budget 分模式定义 |
| rev-dsv4-economy | CLOSED | Option A/B 采纳 |
| rev-dsv4-designer | CLOSED | 产品语义闭合 |
| rev-gpt-architect | GAP | core spec 未落实分模式 snapshot budget |
| rev-gpt-performance | CLOSED | design/engine 足够，snapshot-contract 不冲突 |
| rev-gpt-economy | PARTIAL | design 分模已修，tick/snapshot specs 未完全同步 |
| rev-gpt-apidx | PARTIAL | snapshot-contract SLO 表未分模式 |
| rev-gpt-designer | CLOSED | 分模式产品语义闭合 |
| rev-gpt-security | GAP | 未找到 Arena 50ms snapshot build gate 权威闭合 |

## 共识 Blocker / Reopen Items

### R25-B3-REOPEN: Tick budget 对齐未闭合

**方向 × 模型矩阵**: 4 CLOSED / 8 PARTIAL / 2 GAP。低于 7 CLOSED 阈值。

**同意者（非 CLOSED）**: rev-dsv4-security, rev-dsv4-architect, rev-dsv4-apidx, rev-gpt-determinism, rev-dsv4-performance, rev-dsv4-determinism, rev-dsv4-designer, rev-gpt-architect, rev-gpt-economy, rev-gpt-security。

**问题**:
- `design/engine.md` 给出 World EXECUTE ≤400ms / Arena ≤50ms；多名 reviewer 仍在 `01-tick-protocol.md` 中读到 EXECUTE 500ms、或 “EXECUTE 不单独超时” 的不同口径。
- Arena 分模式预算在 design 层明确，但 core tick spec 未形成等价 normative branch。
- 部分 reviewer 认为 500ms 可解释为 hard timeout、400ms 为 target budget；但该关系未被显式写清，导致 closure 票无法收敛。
- budget sum / backpressure / degradation 策略仍有解释分歧：World 表面相加 3200ms > 3000ms，Arena 表面相加 330ms > 300ms；是否并行、是否包含关系、是否 hard cutoff 未完全统一。

**修正要求**:
1. 在 `specs/core/01-tick-protocol.md` 建立与 `design/engine.md §3.4.1` 同构的 World/Arena tick budget 表，或明确声明 engine 表为唯一预算权威并删除本地冲突值。
2. 明确 `budget target` 与 `hard timeout ceiling` 的关系；若保留 500ms，必须写明它不是 EXECUTE budget，而是 kill/ceiling，并说明 400ms target 的 admission/benchmark 用途。
3. 对 Arena 写出 `tick_interval=300ms` 下的 Snapshot/COLLECT/EXECUTE/COMMIT/BROADCAST normative 参数，不只在 design 层出现。
4. 写清 budget sum 超 interval 的并发/包含关系与 backpressure/degraded mode 触发条件。

### R25-B4-REOPEN: MCP 工具清单与 active/removed 状态未闭合

**方向 × 模型矩阵**: 4 CLOSED / 7 PARTIAL / 3 GAP。低于 7 CLOSED 阈值。

**同意者（非 CLOSED）**: rev-dsv4-security, rev-gpt-determinism, rev-dsv4-performance, rev-dsv4-designer, rev-gpt-architect, rev-gpt-performance, rev-gpt-economy, rev-gpt-apidx, rev-gpt-designer, rev-gpt-security。

**问题**:
- `api-registry.md` 总述为 56 active tools，但 §3.2 标题仍被多名 reviewer 读到 `Game API 工具清单 (54)`。
- `specs/security/03-mcp-security.md` 仍将 active onboarding/debug/deploy tools 写为 “已移除/已整合”，包括 `swarm_explain_last_tick`、`swarm_get_schema`、`swarm_get_docs`、`swarm_get_available_actions`，部分 reviewer 还指出 `swarm_list_modules`。
- `game_api.idl.yaml` 分组注释仍可能写 `Play (14 tools)`，而 registry/mcp-tools 为 Play 16。
- 旧链接锚点如 `#32-工具清单-46` 仍被指出，说明文档生成/引用链未完全闭环。

**修正要求**:
1. 将所有 `54` 工具计数残留改为 `56`，包括标题、注释、anchor、README/索引引用。
2. 在 security spec 中删除 “active 工具已移除” 的表述，改为 “active but scoped/rate-limited/detail-limited” 或直接引用 API Registry。
3. 为 MCP tool lifecycle 建立唯一状态枚举：`active / deprecated / removed / replaced_by`，避免 security spec 与 registry 分别手写状态。
4. 添加最小 drift check，校验 IDL 分组数、Registry 总数、mcp-tools 总览、security 引用状态一致。

## 弱确认但仍需清理的残留

### R25-B1-WEAK: Host ABI 权威源已建立，但旁路旧签名仍被多名 reviewer 指出

**闭合票数**: 7/14 CLOSED。

**残留**:
- `specs/core/04-wasm-sandbox.md` 被多名 GPT reviewer 指出仍有旧 `host_get_terrain(x,y)`、缺少 opts 的 `host_path_find`、缺少 `rule_id` 的 `host_get_world_rules`，以及 `host_get_terrain` 4 bytes 输出上限。
- `specs/gameplay/08-api-idl.md` 被多名 reviewer 指出仍保留旧 host_functions 块。
- `host_get_objects_in_range.range` 的 signedness (`u32` vs `i32`) 在 API/DX 方向被标记为 SDK/codegen 风险。

**处置**: 不按规则 REOPEN，但应与 B3/B4 修复同批清理；否则下一轮容易重新跌破阈值。

### R25-B2-WEAK: 经济主线闭合，但旧 IDL/边界文档残留仍明显

**闭合票数**: 8/14 CLOSED。

**残留**:
- `specs/gameplay/08-api-idl.md` 的 RangedAttack=100、fixed/flat 50% Recycle refund 被多名 reviewer 反复指出。
- `game_api.idl.yaml` `per_player_drone_cap=500` vs Registry `50` 被 determinism reviewer 指出为字段命名歧义。
- `snapshot-contract.md` MVP economy boundary 的 `RecycleRefund base 50%`、`StorageTax 0.1%/tick` 被安全/确定性方向指出仍可能误导实现。

**处置**: 弱确认闭合；应作为直接文档残留修复，不需要新 D-item。

### R25-B5-WEAK: Snapshot 权威方向成立，但 tick-protocol 旧算法造成严重分歧

**闭合票数**: 7/14 CLOSED。

**残留**:
- 5 名 reviewer 判为 GAP，2 名判为 PARTIAL；核心分歧是 `01-tick-protocol.md` 是否仍定义 “关键/高/中/低语义桶 + distance/entity_id” 的独立截断算法。
- 即便 CLOSED 阵营承认 snapshot-contract 为权威，GAP 阵营认为 tick-protocol 是实现者会直接照抄的核心流程规范，不能保留不等价算法。

**处置**: 虽按票数 WEAK_CONFIRMED，但建议升格为 B3 同批修复：tick-protocol 不应保留本地 snapshot truncation 算法，只引用 snapshot-contract。

### R25-D2-WEAK: World 非竞争统计语义闭合，但 API 命名/能力面未闭合

**闭合票数**: 7/14 CLOSED。

**残留**:
- `swarm_get_leaderboard` 在 API Registry / game_api IDL 中仍表现为 world/global/none visibility，被 7 名 reviewer 判为 PARTIAL。
- 设计文档 “World 不设竞争榜单” 已闭合，但 API surface 仍会诱导实现者/玩家将 World showcase stats 理解为 competitive leaderboard。

**处置**: 弱确认闭合；下一轮修复可选择限制 `swarm_get_leaderboard` 到 Arena，或拆出 `swarm_get_world_stats` / `world_showcase` 语义。

## 已强确认闭合项

### R25-B6-CONFIRMED: Auth CSR Replay Class + CodeSigning TTL

**闭合票数**: 11/14 CLOSED。

**共识**:
- `swarm_submit_csr` 已归入 `non_idempotent_mutation`，核心机制为 FDB 事务内消费 PoW challenge。
- CodeSigningCertificate 30–180 days 主线已在 auth / command-source 语义中收敛。

**残留但不阻塞**:
- `30–180 days（默认 7d）` 的默认值措辞存在少量语义含混。
- api-registry generic cert max 365d / `validity_days` 未 profile 化，被 performance/economy 标为 PARTIAL。

### R25-D1-CONFIRMED: Arena 房间制优先

**闭合票数**: 13/14 CLOSED。

**共识**: Arena P0 以 Room Match 为核心，Tournament/League 为 P1+ 上层编排。唯一 PARTIAL 来自 feedback-loop 文档仍把 tournament 放在 MVP 语境。

### R25-D3-CONFIRMED: Recycle lifespan-proportional

**闭合票数**: 10/14 CLOSED。

**共识**: Resource Ledger / economy IDL / gameplay 主线均已采用 lifespan-proportional 10%-50% refund。旧 flat 50% 残留合并到 B2 残留处理。

### R25-D4-CONFIRMED: Snapshot budget 分模式

**闭合票数**: 10/14 CLOSED。

**共识**: design/engine 已明确 Arena 50ms p99 / World 200ms p95 的分模式预算。少数 GAP/PARTIAL 要求 snapshot-contract/tick-protocol 也同步同一表；此要求与 B3 修复重叠。

## 残留问题清单

| ID | 优先级 | 问题 | 来源方向 | 处置 |
|----|--------|------|----------|------|
| R25-R1 | P0 | Tick budget 400ms/500ms/no-timeout 多口径 | Security / Architect / API-DX / Determinism / Economy | REOPEN，直接修复 B3 |
| R25-R2 | P0 | MCP 56/54 标题、active/removed 工具状态冲突 | Security / Performance / Designer / API-DX / Determinism | REOPEN，直接修复 B4 |
| R25-R3 | P1 | tick-protocol 仍保留旧 snapshot truncation 算法 | Security / Performance / Economy / API-DX / Determinism | 与 B3 同批修复；B5 当前 WEAK_CONFIRMED |
| R25-R4 | P1 | sandbox / gameplay IDL 仍有旧 Host ABI 签名 | Architect / Security / API-DX / Determinism | 清理旁路文档；B1 当前 WEAK_CONFIRMED |
| R25-R5 | P1 | `08-api-idl.md` 旧 RangedAttack/Reycle 口径 | Architect / Security / API-DX / Determinism | 清理旁路文档；B2/D3 残留 |
| R25-R6 | P1 | World leaderboard API 与非竞争统计语义冲突 | Designer / Security / Performance / Economy / Determinism | 弱确认，建议限制到 Arena 或拆 `world_stats` |
| R25-R7 | P2 | CodeSigning 7d default / 365d generic max 表述含混 | Architect / Performance / Economy / Security | 非阻塞，下一轮清理 profile-specific TTL 表 |
| R25-R8 | P2 | Tournament/League 在 feedback-loop MVP 语境残留 | Economy | 非阻塞，D1 已强确认闭合 |

## D-items（需用户裁决）

本轮未发现新的 D-item。R25 所有残留均为 Closure residue / 文档同步问题，不是新设计决策。

### 可选微决策（不阻塞修复）

#### D2-API: World stats 命名

**问题**: `swarm_get_leaderboard` 是否应继续兼容 World 非竞争统计。

**选项**:
- A：将 `swarm_get_leaderboard` 限定为 Arena competitive profile；World 改用 `swarm_get_world_stats`。
- B：保留 `swarm_get_leaderboard`，但 schema 增加 `scope = arena_competitive | world_showcase`，并声明 World 不排名、不奖励、不公平竞技。

**推荐**: A。理由：与 “World 不设竞争榜单” 的产品语言最一致，也能减少未来 reviewer 对 leaderboard 命名的反复误判。

## 文档维护项

1. 增加最小 drift check：
   - MCP tool count: IDL group count / api-registry total / mcp-tools total / security references。
   - Host ABI: api-registry vs host-functions vs sandbox/interface/IDL 是否复制旧签名。
   - Economy: `RangedAttack: 100`、`refund * 0.5`、`Recycle 50%`、`StorageTax 0.1%` 残留扫描。
   - Tick/Snapshot: `EXECUTE 500ms`、本地 `sort_and_truncate`、`Game API 工具清单 (54)`、`leaderboard_snapshot`。
2. 将权威源策略落成文档规则：规范文件不重复 Registry/Ledger/Snapshot Contract 的表格，除非自动生成；手写文档只能引用。
3. 对 API Registry 生成链做一次校验：若 registry 声称由 IDL 生成，则 IDL 中的 cap/tool group 注释必须与 registry 一致。
4. 在 `reviews/README.md` 中记录 R25 Verdict: REOPEN，避免误读为 Freeze 确认轮。

## 评审统计

### Verdict 矩阵

| Direction | GPT-5.5 | DeepSeek V4 Pro |
|-----------|---------|-----------------|
| Architect | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE |
| Security | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE |
| Designer | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE |
| Performance | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE |
| Economy | CONDITIONAL_APPROVE | APPROVE |
| API/DX | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE |
| Determinism | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE |

### Item 闭合强度

| 分类 | 项目 | 数量 |
|------|------|:----:|
| CONFIRMED | B6, D1, D3, D4 | 4 |
| WEAK_CONFIRMED | B1, B2, B5, D2 | 4 |
| REOPEN | B3, B4 | 2 |

### 共识强度评估

- 强收敛：Auth / Arena Room / Recycle / Snapshot budget 的设计方向已稳定。
- 弱收敛：Host ABI、经济数值、snapshot truncation、World stats 都已有权威方向，但旁路文档残留仍显著。
- 未收敛：Tick budget 与 MCP tool lifecycle/计数；这两项有跨方向 + 跨模型广泛不闭合信号，不能忽略。
- 最终判定：由于 Closure Verification 规则是逐项 gate，B3/B4 低于闭合阈值，R25 必须判为 **REOPEN**。

## 下一轮入场条件

进入 R26 前建议至少完成以下直接修复：

1. B3：统一 `01-tick-protocol.md` 与 `design/engine.md` 的 World/Arena budget 表，删除或解释 500ms EXECUTE 残留。
2. B4：修正所有 54/56/14/16 工具计数残留，删除 active tools “已移除” 文案。
3. B5 overlap：将 tick-protocol snapshot truncation 改为纯引用 snapshot-contract，不保留本地不等价算法。
4. B1/B2 residue：清理 sandbox / 08-api-idl / snapshot-contract 中旧 ABI、旧经济值。
5. D2 residue：将 World 非竞争统计从 `leaderboard` 命名/API profile 中拆清。

建议 R26 使用窄 Closure Verification：只验证 B3、B4，以及 B1/B2/B5/D2 的残留清理项；无需重新开放全设计评审。
