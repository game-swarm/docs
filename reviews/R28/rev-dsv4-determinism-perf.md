# R28 Closure Verification — Determinism & Performance

> CV 模式 | 方向: Determinism & Performance | 评审员: dsv4-pro
> 验证目标: B4 / T-H1 / ML-1~ML-5
> 日期: 2026-06-20

---

## Verdict: CONDITIONAL_APPROVE

7 项验证中 4 项完全闭合（CLOSED），2 项部分闭合（PARTIAL），1 项存在残差（GAP）。

T-H1（seed lifecycle）修复质量最高——Arena commit-reveal 方案、World statistical detection、seed 生命周期统一表全部完备。ML-3/ML-4 是简洁有效的单点修复。B4 的容量标注和 benchmark-gate 升级正确，但 worker pool 与 per-player timeout 的架构冲突（R27 DSV4 P2 Critical）仍未闭合。ML-2 引用的 canonical-codec.md 文件缺失——代码路径指向了不存在的文件。ML-5 的 Dragonfly annotation 添加了「允许滞后」标记但执行顺序仍为串行。

## Closure Matrix

| ID | 问题 | 原始 Review | 状态 | 证据 |
|----|------|-----------|:----:|------|
| **B4** | 500/1000 容量承诺 + worker pool/timeout 模型 | R27 DSV4 P1/P2 Critical | **PARTIAL** | 见 B4 详细分析 |
| **T-H1** | RNG seed disclosure boundary + forward secrecy | R27 DSV4 T1 High, GPT T2 High | **CLOSED** | 见 T-H1 详细分析 |
| **ML-1** | 256KB vs 1MB 输出上限冲突 | R27 GPT T4 Medium | **CLOSED** | 见 ML-1 详细分析 |
| **ML-2** | canonical serialization / command_hash | R27 GPT T5 Medium | **GAP** | 见 ML-2 详细分析 |
| **ML-3** | ECS entity iteration CI 检测 | R27 DSV4 T2 High | **CLOSED** | 见 ML-3 详细分析 |
| **ML-4** | host_path_find cache_miss_penalty | R27 DSV4 T5 Low | **CLOSED** | 见 ML-4 详细分析 |
| **ML-5** | Dragonfly 同步更新阻塞 NATS | R27 DSV4 P4 Medium | **PARTIAL** | 见 ML-5 详细分析 |

---

## B4 — PARTIAL: Worker Pool vs Timeout 冲突未闭合

### 已闭合部分

1. **1000 players → benchmark-gated**: api-registry.md §5.5 L535:「⚠️ benchmark-gated（未验证）。实际 hard cap 由压力测试在目标硬件上测定」— 符合 B4 修正要求第一条。

2. **500 players → target/stress**: api-registry.md §5.5 L534:「实际容量由压力测试确定——tick 时间可随负载弹性增加」— 符合要求。

3. **Aggregate CPU Admission Formula**: engine.md §3.4.2 新增完整的 `aggregate_cpu_budget` 公式与 `effective_per_player_quota` 推导。包含 MIN_FUEL 准入门控和 `ERR_CPU_SATURATED` 拒绝机制。— 符合要求。

4. **区分 MVP/World/Arena commit budgets**: api-registry.md §5.2 明确列出 World 2500ms vs Arena 200ms per-player deadlines；§5.5 列出独立的 hardware baseline。

5. **Bevy snapshot scope**: tick-protocol.md §3.5 新增完整的必须捕获 Resource 类型清单（TickCounter, WorldSeed, PlayerOrder, RNGState 等）和 Component 类型清单，以及 entity ID allocator + pending queues + ledger buffers — 符合 R27 GPT T6。

### 未闭合部分 — P2 Critical

**问题**: R27 DSV4 P2 和 GPT P1 均标记为 Critical/High 的 worker pool 与 per-player timeout 冲突。

**当前状态**: engine.md §3.4.2 Worker Pool 推导仍为:
```
worker_pool_size = min(worker_pool_max, active_players)
worker_pool_max = 256（运行期默认）
```

`256 worker default scenario (500 active players)`: pool = 256 workers → 每个 worker 处理约 2 个玩家. 新增文本「Admission control: active_players > 256 → graceful queuing, fair-share slot allocation」但 **未定义 graceful queuing 的具体机制**。

**核心矛盾未解决**: 当 worker-1 的 player-A 消耗完整 2500ms（合法，在 budget 内），player-B queue 在 worker-1 上**从未开始执行**——player-B 的 2500ms deadline 从未启动。这不是「超时」而是「从未开始」。

**R27 Speaker 修正要求原文**:「修正 worker pool 与 per-player timeout 冲突：选择独占 worker、按 worker 分片 timeout、或改成可抢占/async dispatch 模型」

**当前文档未选择任何选项**:
- 选项 A（独占 worker）: 未采用，pool 仍为 min(256, active_players)
- 选项 B（per-worker shard timeout）: 未定义
- 选项 C（async dispatch）: 未采用，worker pool 仍为串行模型

**证据**: 扫描 api-registry.md §5.5、engine.md §3.4.2、tick-protocol.md §2.2，均无独占 worker、worker-shard timeout、或 async dispatch 的声明。

**文件验证命令**:
```
grep -rn "独占.*worker\|per-worker.*timeout\|worker.*shard\|async.*dispatch\|preempt" design/engine.md specs/core/01-tick-protocol.md specs/reference/api-registry.md
→ 零匹配
```

**严重度**: 保留 Critical。此冲突在 500 players 规模下直接发生（256 workers / 500 players → 约 49% 玩家 queue），导致这些玩家的指令从未执行。这不是边缘案例。

**修复建议**（最小改动）:
- 在 engine.md §3.4.2 或 api-registry.md §5.5 中明确声明：per-player sandbox deadline 从 **tick 开始时**计时，非从 worker 分配时计时。若 player 在 worker queue 中等待超过 deadline，该 player 本 tick 输出 0 指令（`terminal_state = TimeoutExceeded`）。worker queue 使用 FIFO + fair-share slot rotation 防止同一 player 持续被 queue。
- 或者：将 worker_pool_max 默认值从 256 提升到 ≥ active_players（至少 target 500），使默认配置下无 queue 竞争。

---

## T-H1 — CLOSED: Seed Lifecycle 完整闭合

**原始问题**: R27 DSV4 T1（High）和 GPT T2（High）均指出 seed forward-secrecy 未闭合——链式可推导、seed_epoch 未区分 opaque id 与 secret、赛中不可预测与 replay 可验证之间缺少 disclosure boundary。

**修复状态**: 01-tick-protocol.md §3.1「种子生命周期与泄露防护（R27 T-H1 — 混合方案）」完整覆盖所有要求：

| R27 要求 | 修复证据 |
|---------|---------|
| Arena commit-reveal | §Arena：赛中 seed 仅引擎，seed_commitment 公开，赛后 +100 tick 自动公开 seed → 审计方可验证 `Blake3(seed || "commit") == seed_commitment` |
| World operator seed-bump | §World leak detection: per-player win-rate deviation / combat RNG advantage / spawn clustering，每 1000 tick 汇总 → FLAG → 服主通知 |
| Statistical detection spec | 三种检测指标明确定义：连续 5+ 预测命中、all_high/all_low 分布异常、新生房间密度异常 |
| seed_epoch 语义 | Seed 生命周期统一表区分「Arena 生成/赛中/披露/归档/响应」vs「World」各阶段 |
| Replay 归档 | keyframe snapshot 包含 `(seed_epoch_id, seed, epoch_start_tick, epoch_end_tick)` |
| 泄露 runbook | 5 步应急流程：检测→确认→止损(swarm_world_seed_bump)→回滚→公告 |

**文件验证**: `grep -c "commit-reveal\|seed_commitment\|Seed-Bump\|Statistical Detection\|seed_epoch_id" specs/core/01-tick-protocol.md → 8 处匹配`

**评估**: 修复质量高。Arena commit-reveal 正确解决了「赛中不可预测 + 赛后可审计」的双重要求。World 的 statistical detection + operator seed-bump 在无时间边界的持久世界中是合理的折衷——真正的密码学前向保密与确定性 replay 不可兼得，文档将此作为已接受约束明确声明。

**状态**: CLOSED ✅

---

## ML-1 — CLOSED: 256KB vs 1MB 输出上限冲突

**原始问题**: R27 GPT T4 指出 command validation 文档中 256KB 和 1MB 冲突——同一 tick output cap 出现两个不同值。

**修复后状态**:
- 02-command-validation.md §6 硬性边界: 整批（tick 输出）≤ 256KB（唯一值）
- 04-wasm-sandbox.md L316: `max_output_bytes = 1 MB` — 但上下文是 **MCP simulate 专用**（「模拟结果最大输出」），非 WASM tick output
- 01-tick-protocol.md L730: `max_output_bytes = 1 MB` — 同样在 simulate context

**评估**: 256KB = WASM tick output cap；1MB = MCP simulate output cap。两者用途不同，不再冲突。命名仍可改进（建议 MCP simulate 使用 `max_simulate_output_bytes` 避免混淆），但不构成合同矛盾。

**状态**: CLOSED ✅

---

## ML-2 — GAP: canonical-codec.md 缺失

**原始问题**: R27 GPT T5 指出 canonical serialization / command_hash 细节不完整——缺少机器化的 canonical codec 定义。

**当前状态**:

已改进部分:
- api-registry.md TickTrace envelope 新增 field 21: `canonical_codec_version` (u32) ✅
- 02-command-validation.md L99: `command_hash = Blake3(canonical_json(command))` — 明确使用 canonical_json() ✅
- 文本引用 `specs/reference/canonical-codec.md` 作为 canonical_json() 定义源 ✅
- 明确使用 RawCommand（含注入字段）而非 CommandIntent 原始输出 ✅

**GAP**: `specs/reference/canonical-codec.md` 文件不存在。

```
$ ls /data/swarm/docs/specs/reference/canonical-codec.md
→ NOT FOUND
```

**影响**: 02-command-validation.md L99 声称 `canonical_json()` 定义在 `specs/reference/canonical-codec.md`，包含「键排序、无空格、数值无尾零、字符串 NFC 归一化」。但该文件缺失——实现者无法查阅具体的 canonical JSON 规则。不同实现可能对 JSON key ordering、number encoding、string normalization 有不同解释，导致 command_hash 和 state_checksum 跨实现分叉。

**严重度**: Medium（文档引用断裂）。不影响核心确定性合同（键排序等规则已在 L99 内联描述），但缺少正式代码规范文件会造成实现差异。

**修复建议**: 创建 `specs/reference/canonical-codec.md`，内容至少包含：
- JSON key 按 UTF-8 字节序递归排序
- 无空白字符（缩进/空格/换行）
- 数值无尾零（`1.0` → `1`，`1.50` → `1.5`）
- 字符串 NFC 归一化
- enum 表示规则（整数索引 vs 字符串）
- unknown field policy（忽略/拒绝）
- 版本号对应 canonical_codec_version

**状态**: GAP ⚠️

---

## ML-3 — CLOSED: ECS Entity Iteration CI

**原始问题**: R27 DSV4 T2（High）指出 ECS entity 迭代顺序依赖显式排序，但 CI 仅做静态分析无法检测遗漏。建议 randomized entity iteration order test。

**修复**: specs/core/07-world-rules.md L204 新增:

> **R27 ML-3 — ECS Entity Iteration Determinism**: Bevy ECS 不保证 archetype/table 内部存储的遍历顺序。引擎在所有遍历中必须显式排序（按 entity_id 字典序）。CI 增加 `randomized-entity-iteration` test mode：通过 feature flag 随机化 Bevy 内部存储顺序，运行确定性 replay 场景并断言 state_checksum 一致。

**评估**: 修复简洁有效。通过 feature flag 随机化内部存储顺序（而非依赖 release vs debug 差异）是正确的检测方法——可以系统性地暴露任何隐式依赖 archetype order 的代码。

**状态**: CLOSED ✅

---

## ML-4 — CLOSED: host_path_find cache_miss_penalty

**原始问题**: R27 DSV4 T5（Low）指出 cache_miss_penalty 未定义为固定值——若实现为「实际 CPU 重算时间对应的 fuel」则跨硬件不一致。

**修复**: specs/core/04-wasm-sandbox.md L355:

> `host_path_find` 成本: `500 × explored_nodes + 200 × expanded_edges + cache_miss_penalty`，cache_miss_penalty = **固定 2000 fuel**（与硬件无关，保证跨节点确定性结算）

**评估**: 固定值 2000 fuel 消除硬件依赖性。✅

**状态**: CLOSED ✅

---

## ML-5 — PARTIAL: Dragonfly 同步阻塞 NATS

**原始问题**: R27 DSV4 P4（Medium）指出 Dragonfly 同步更新在 NATS broadcast 之前——Dragonfly 高负载时阻塞客户端广播。

**修复**: 01-tick-protocol.md §4.2 L522:
```
2. Dragonfly.update(delta)   // 非权威缓存，允许滞后。失败则从 FDB 重建
3. NATS.publish("tick.{tick}", delta)
```

新增「允许滞后」annotation ✅。Broadcast 段（L526-527）确认「BROADCAST failure never rolls back committed tick」✅。

**但串行顺序未改变**: Dragonfly.update 仍在 NATS.publish 之前执行且为同步调用。「允许滞后」是语义声明，不是架构变更——若 Dragonfly 响应慢（高负载、网络抖动），NATS broadcast 仍被延迟。

**R27 Speaker 修正要求原文**:「Dragonfly update 与 NATS publish 并行执行」或「Dragonfly update 改为异步」

**当前实现**: 既非并行也非异步。annotation 改善了文档意图但不改变执行语义。

**严重度**: Low — Dragonfly 设计为低延迟内存缓存，生产环境中其响应时间通常远低于 broadcast 预算。且 tick 已持久化到 FDB，Dragonfly 慢只影响客户端显示延迟，不影响世界状态。

**状态**: PARTIAL ⚠️ — annotation 已添加，架构串行顺序未改变。

---

## Scalability 评估

| 规模 | 瓶颈 | R27 后状态 |
|------|------|-----------|
| 100 players | 无 | 安全区 — 无变化 |
| 500 players | COLLECT budget 饱和 + worker pool/timeout 冲突 | **P2 冲突未闭合** — 此为 R28 最大残留风险 |
| 1000 players | benchmark-gated | 标注正确 — 未验证但文档诚实 |

---

## Replay Integrity

R27 已覆盖的基础确定性合同在 R28 文档中保持完整——Blake3 单原语、五层排序键、IndexMap、定点算术、两阶段快照、COLLECT 缓存跨重试复用、单指令管线。R28 未引入新的 replay 风险。

---

## 结论与建议

1. **B4 P2 GAP 必须在下轮前闭合** — worker pool vs timeout 冲突是唯一残留的 Critical 项。建议选择最小改动方案：明确 per-player deadline 从 tick 开始时计时，worker queue 超时玩家本 tick 得 0 指令。

2. **ML-2 canonical-codec.md 必须创建** — 文档引用指向不存在文件。补充后 ML-2 可闭合。

3. **ML-5 建议接受为 Low 残留** — Dragonfly annotation 已改善文档意图；生产环境中 Dragonfly 延迟通常远低于广播预算。改为异步可在实现 Phase 中完成。

4. **T-H1 修复质量可作为后续 CV 参考** — Arena commit-reveal + World statistical detection 的混合方案处理了「确定性 replay vs forward secrecy」的根本张力。

5. **建议 R29 为 Ultra-Narrow CV** — 仅验证 B4 P2 + ML-2。2 项 verify 可极快完成。