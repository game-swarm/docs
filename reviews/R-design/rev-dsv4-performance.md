# 性能评审 — DeepSeek V4 Pro Clean-Slate Review

> 评审员：rev-dsv4-performance (DeepSeek V4 Pro)
> 日期：2026-06-18
> 范围：7 个设计文档 — README / auth / engine / gameplay / interface / modes / tech-choices
> 原则：设计阶段评审，不考虑分阶段实现。有合适方案直接采用，不考虑实现难度。

---

## Verdict: CONDITIONAL_APPROVE

整体性能架构清晰——Tick 生命周期分离为 COLLECT → EXECUTE → BROADCAST 三阶段，双阶段快照架构消除了 O(玩家数 × 实体数) 的重复序列化，WASM 预编译 + fuel metering 精确计量。发现 **2 个 Critical、4 个 High、4 个 Medium、3 个 Low** 共计 13 个性能相关 findings。Critical 涉及 auth nonce 存储矛盾（可能导致 per-request FDB 写入爆炸）和 per-player 缓存内存预算未定义。Conditional 条件为：D1、D2 必须在实现前解决并形成书面裁决文档。

---

## Strengths

- **双阶段快照架构**（engine §3.2 两阶段快照架构）——从 O(N×M) 降到 O(M + N×V)，消除每玩家独立序列化世界状态的开销。这是整个设计中最有价值的性能优化决策。
- **WASM 预编译 + 池化**（engine §3.2 WASM 预编译, §3.4 WASM instances）——部署时编译原生码，tick 时仅实例化。池大小按活跃玩家数动态伸缩，空闲 5min 回收。避免了 per-tick fork/kill 的 fork 开销。
- **Phase 2b 并行策略**（engine §3.2 Phase 2b 并行策略）——regeneration 和 decay 系统与主线无数据竞争，利用 Bevy 依赖图自动并行调度。正确性由数据独立 + Bevy 依赖图保证，确定性不依赖并行度。
- **Fuel metering 精确计量**（tech-choices §2）——WASM 指令计数而非墙钟，C 玩家和 Python 玩家在相同配额下获得同等算力。配合 epoch interruption 实现硬超时。
- **资源核算外部化**（gameplay §8.2 实体膨胀归因）——每个玩家的 snapshot 大小与自身 drone 数量成正比，不随其他玩家膨胀而增长。全局实体数 > 50,000 hard cap 时新 Spawn 被拒，不让现有玩家承担膨胀惩罚。
- **Hot path 使用 FlatBuffers**（engine §3.4 热路径 ABI）——tick 内 snapshot 和 CommandIntent 的实时传输使用 binary canonical encoding，保证 <1ms 序列化/反序列化延迟。
- **Tier Entry Gate 矩阵**（engine §Tier Entry Gate 矩阵）——明确每个 Tier 冻结/延后的能力，`future-disabled` 项编译期通过 feature flag 排除，防止 MVP 被未来扩展污染。这种门控思维本身就是性能架构的一部分。

---

## Findings

### D1 (Critical) — Auth Nonce 存储矛盾：FDB Schema vs Dragonfly Hot-Path

**位置**：auth.md §6.2 Auth 存储 vs §10.8 Nonce 存储

**问题**：auth.md §6.2 的 FDB subspace 定义了 `auth/request_nonce/<certificate_id>/<nonce> → {created_at, expires_at}`，即每个请求 nonce 写入 FDB。但 §10.8 明确声明「Nonce 存储不写 FDB。使用 Dragonfly SETNX TTL」，并给出了 Key 格式 `nonce:{account_id}:{nonce_value}` 和 TTL 300s。

这是**直接矛盾**。如果实现按 §6.2 FDB schema 走，500 活跃玩家每 tick 的 MCP 查询（读 snapshot、调试、经济查询等）产生的 nonce FDB 写入会与每 tick 的原子世界状态提交在同一 FDB 集群中竞争。按每玩家每 tick 平均 3 次 MCP 查询估算，500 玩家 = 1500 次/3s = 500 FDB nonce 写入/s。每次写入都是独立事务，且不阻塞 tick 主事务——但这个写入量叠加 auth 其他 FDB 操作（证书审计、CRL 更新、session 旋转），可能使 FDB 成为瓶颈。

**影响**：若实现方误按 §6.2 实现，per-request FDB 写入将违反 Tier1 FDB 事务预算。若按 §10.8 实现（Dragonfly），则 §6.2 的 FDB schema 定义是误导性的。

**建议**：
1. 删除 §6.2 中的 `auth/request_nonce/` FDB 定义（已由 §10.8 的 Dragonfly 方案取代）
2. 在 §6.2 中增加明确的 Nonce 存储注释指向 §10.8
3. 定义 Dragonfly 崩溃时的 nonce 重放窗口语义（TTL 窗口内可重放，窗口过后拒绝）——设计已描述但需在 spec 中固定

---

### D2 (Critical) — Per-Player 缓存内存预算未定义

**位置**：engine.md §3.4 Tier1 性能预算注册表

**问题**：Tier1 预算注册表定义：
- Pathfinding cache: 10,000 entries per player, LRU
- Visibility cache: 50,000 entries per player, TTL=1 tick

但**没有定义每个 entry 的内存大小**。以 500 活跃玩家计算：
- Pathfinding: 500 × 10,000 = 5,000,000 entries。如果每个 entry 包含一条路径（平均长度 20 格，每格 `(i32,i32)` = 8 bytes），则 ~80 bytes/entry → 5M × 80 ≈ 400MB。
- Visibility: 500 × 50,000 = 25,000,000 entries。每个 entry 至少包含 `entity_id (u64) + visible (bool) + metadata` ~16 bytes → 25M × 16 ≈ 400MB。

两个缓存合计 ~800MB，加上 WASM 实例内存（500 instances × 预估 4MB = 2GB）、Bevy World 内存（50,000 实体 × 预估 512 bytes = 25MB）、FDB 客户端缓冲——**Tier1 单节点总内存可能超过 4GB**。这不一定是问题，但需要明确预算。

**建议**：
1. 在 Tier1 预算注册表中增加「Player cache memory budget: X MB per player, Y GB total」
2. 为 pathfinding 和 visibility cache entry 定义具体结构体和字节估算
3. 考虑 visibility cache 是否真的需要 per-player 存储——visibility 结果本质上由 `entity position + player drone positions + fog_of_war rules` 决定，可能可以在 COLLECT 阶段统一计算后分发（以 CPU 换内存）

---

### D3 (High) — CRL 缓存 60s 吊销窗口：安全⇔性能权衡需明确合同

**位置**：auth.md §10.8 Auth 子系统缓存边界

**问题**：证书吊销状态缓存允许 60s 延迟（「吊销后至多 60s 旧证书仍可被接受」）。从性能角度，这避免了 per-request FDB CRL 查询——正确。但从正确性角度，这意味着：一个被吊销的 `CodeSigningCertificate` 在 60s 内仍可部署恶意 WASM；一个被吊销的 `AdminCertificate` 在 60s 内仍可执行管理操作。

设计文档承认这是「明确接受的风险」，并说明「竞争性世界可配置为 5-10s」。但这个配置值直接影响 FDB 读负载——若设为 5s，500 玩家场景下 CRL 缓存刷新频率从 1/60s 变为 1/5s，FDB 读负载上升 12×。

**建议**：
1. 在 Tier1 预算中增加「CRL refresh FDB read budget: X reads/s」
2. 定义 CRL 缓存的 refresh 策略：是定时全量刷新还是在请求时 check-and-refresh？全量刷新在 60s 一次时开销可接受，5s 一次时需要考虑 FDB range read 开销
3. 考虑分级吊销延迟：`CodeSigningCertificate` 的吊销窗口是否可以更短（如 5s），而 `ClientAuthCertificate` 保持 60s

---

### D4 (High) — Arena 300ms Tick 预算中 FDB 提交窗口未定义

**位置**：engine.md §3.4, modes.md §9.1.2

**问题**：Arena 模式 tick interval = 300ms，COLLECT budget = 200ms，EXECUTE = 剩余至 tick 截止。但 FDB 原子提交通常需要 5-50ms（取决于写入量和集群状态）。在 300ms tick 下，如果 COLLECT 消耗 200ms，EXECUTE 消耗 80ms，留给 FDB commit 的时间只剩 20ms——这在 FDB 事务冲突重试场景下不够。

mode.md §9.1.2 没有提供 Arena 的 FDB 写入预算。与 World 模式的 3s tick 不同，Arena 的短 tick 使得任何 FDB 事务延迟都会导致 tick 超时。

**建议**：
1. 在 Arena 性能预算中增加「FDB commit budget: Xms (p99)」
2. 考虑 Arena 是否可以使用更轻量的事务（如仅写入 delta，跳过 keyframe）
3. 或者为 Arena 设置独立的 FDB 集群/数据库，避免与 World 模式竞争

---

### D5 (High) — Rhai Mod 串行执行可能主导 EXECUTE 阶段

**位置**：gameplay.md §8.7 引擎集成, §Rhai 执行预算

**问题**：每个 Rhai mod 的 `tick_start`/`tick_end` 钩子按顺序串行执行，且注册在 `after(death_cleanup_system)`。如果世界启用了 20 个 mod（如示例中的 empire-upkeep、resource-decay、fog-of-war 等），每个 mod 执行 5ms AST 预算（100,000 AST 节点限制下保守估计），则 mod 执行总时间 = 20 × 5ms = 100ms——占 EXECUTE budget 中很大比例。

虽然 §Rhai 执行预算 定义了硬限制（100,000 AST 节点 + 100 actions/tick），但**没有定义 per-mod 墙钟预算或总的 mod 执行预算占 EXECUTE 的比例**。超限检测依赖 AST 节点计数（确定性）而非墙钟——这正确，但从性能规划角度，服主需要知道「启用 N 个 mod 对 tick 延迟的预期影响」。

**建议**：
1. 在 Tier1 预算中增加「Rhai mod total budget: X% of EXECUTE phase (e.g., 20%)」
2. 定义 per-mod 墙钟监控告警阈值（如 > 50ms 触发 WARN）
3. 考虑是否可以并行执行无数据依赖的 mod 钩子（类似 regeneration/decay 的并行策略）

---

### D6 (High) — FDB Auth Subspace 与 World State 在同一集群中竞争

**位置**：auth.md §6.2, engine.md §3.4 FDB 写入策略

**问题**：auth 所有数据（users, public_keys, certificates, challenges, sessions, CRL, revocations, audit logs）全部存储在 FDB 中，且使用 `auth/` 前缀隔离。这些操作与每 tick 的世界状态原子提交共享同一 FDB 集群。

Tier1 每日写入预算 ≤500GB 是基于「500 players × 3s tick × 24h × 16MB」的估算。但这个估算假设每 tick 写入 16MB，而实际 delta 写入远小于此。真正的问题不是总容量，而是 **事务竞争**：auth 操作（特别是证书签发、CRL 更新、session rotation）可能在 tick 事务提交时产生锁竞争，导致 tick 事务重试。

**建议**：
1. 明确 auth 操作与 tick 事务的隔离级别：auth 操作是否可以在独立事务中完成（不参与 tick 原子提交）？
2. 如果 auth 和 world state 必须共享 FDB，在 Tier1 预算中增加「FDB transaction conflict rate: <1%」
3. 评估是否值得为 auth 使用独立 FDB 数据库（同一集群，不同 DB），减少 key range 锁竞争

---

### D7 (Medium) — 证书链验证冷路径延迟

**位置**：auth.md §10.8 证书链验证缓存, §5.5 Canonical Request Signature

**问题**：证书链验证缓存为 Engine 内 LRU（10,000 条），命中时延迟 ≤10ms。但冷路径（首次请求、证书续签后、缓存淘汰后）需要完整验证：Ed25519 链验证 + CRL 状态查询（FDB）+ audience/scope 校验。Ed25519 验证速度 ~30k/s，验证一个完整证书链（leaf + intermediate + root）约需 3 次签名验证 ≈ 100μs。CRL 查询如果走 FDB（缓存未命中），可能增加 5-50ms。

在 World 冷启动或大规模证书续签后，冷路径比例可能很高。500 玩家同时首次连接时，冷路径延迟可能导致 FDB 请求风暴。

**建议**：
1. 在 Tier1 预算中增加「Auth p99 latency: 10ms (cache hit) / 50ms (cache miss)」——设计已有此预算，但需补充「cold start storm: max X concurrent FDB CRL queries」
2. 考虑为 CRL 使用 Dragonfly 缓存（类似 nonce），减少冷路径对 FDB 的直接依赖

---

### D8 (Medium) — 联邦 CRL 同步 60s 间隔的轮询负载

**位置**：auth.md §15.2a 联邦 CRL 同步

**问题**：每个信任的远程世界每 60s 同步一次 CRL 增量。如果有 10 个联邦世界，就是 10 次/60s = ~0.17 QPS 的 HTTP 请求——负载微不足道。但每次同步需要验证 delta CRL 签名（Ed25519）、合并本地 CRL、更新 Engine LRU 缓存。如果联邦 CRL 较大（如远程世界有大量吊销事件），合并操作可能成为 CPU 热点。

**建议**：
1. 定义联邦 CRL 同步的 CPU 预算：<10ms per sync, <50ms total per cycle
2. 增量同步应支持断点续传（`since` 参数），避免全量重传

---

### D9 (Medium) — Snapshot 256KB Per-Player Cap 的 enforce 机制未描述

**位置**：engine.md §3.4

**问题**：Tier1 预算定义了「Snapshot per-player: 256KB」上限，但没有描述如果玩家的可见世界超过 256KB 时引擎的行为。是 truncation？是截断最近实体？是拒绝整个 tick？文档在 Tier 2 提到了「truncation 在增量模式下的语义」但 Tier 1 没有。

在 500-drone 场景中，如果玩家的 drone 分布在多个房间且有 Observer 扩展视野，可见实体可能超过 256KB FlatBuffers 序列化上限。

**建议**：
1. 明确 Tier1 中 snapshot 超限的行为：truncation 策略（按距离/优先级/最近交互时间？）还是拒绝 tick（返回错误）？
2. snapshot 大小应在 COLLECT 阶段检测，如果超限触发告警

---

### D10 (Medium) — Tick Trace 保留策略未定义，FDB 存储无限增长

**位置**：README.md §3 数据模型, engine.md §3.2 阶段三 广播

**问题**：README §3 定义「TickTrace: FDB 不可变, 仅追加」。engine §3.2 说「持久化：每 tick 存储 delta，每 K tick 存储 keyframe 到 FDB（回放用）」。但没有任何地方定义 TickTrace 的保留策略。

Tier1 每日写入预算 500GB 是基于每 tick 的 world state delta + keyframe。但 TickTrace（RawCommand、RejectionReason、TickMetrics）也在 FDB 中。如果无限期保留，FDB 存储会无限增长；如果有 TTL，则回放能力受限。

**建议**：
1. 定义 TickTrace 保留策略：保留最近 N tick（如 100,000 tick ≈ 83 小时 at 3s tick）
2. 超出保留期的 TickTrace 迁移到 ClickHouse（用于长期分析）或删除
3. 在 Tier1 预算中增加「TickTrace storage: X GB/day, retention: Y days」

---

### D11 (Low) — ClickHouse 写入的 tick-burst 问题

**位置**：tech-choices.md §7

**问题**：ClickHouse 接收每个 tick 的 `TickMetrics` 数据。每 tick 一次 INSERT（500 玩家 × 1 row = 500 rows/tick），在 3s 间隔下约 167 rows/s——对 ClickHouse 完全微不足道。但 ClickHouse 针对批量写入优化，高频小批量插入会产生大量 part，触发频繁的 merge。建议每 N tick 批量写入一次（如每 10 tick = 每 30s 一次 5000 rows 的 INSERT），减少 merge 压力。

**建议**：
1. ClickHouse 写入使用批量模式：每 10-30 tick 或每 30s 批量一次
2. 定义 ClickHouse 写入缓冲内存预算

---

### D12 (Low) — `swarm_simulate` 离线模拟无资源预算

**位置**：interface.md §4.1

**问题**：MCP 工具 `swarm_simulate` 允许「给定快照预测未来 N tick」。这在 AI agent 策略优化中非常有用，但无限制的模拟会消耗引擎 CPU。文档没有定义模拟的资源限制——N 的上限？是否限制并发模拟数？模拟是否消耗 player fuel？

**建议**：
1. 定义 `swarm_simulate` 的资源预算：max N tick、max 并发数、是否计入 player CPU quota
2. 考虑模拟使用独立线程池，不阻塞主 tick 循环

---

### D13 (Low) — PoW 求解对 WASM AI Agent 的延迟影响

**位置**：auth.md §9.2, §4.2

**问题**：默认 difficulty_bits=24 时 WASM 环境求解 PoW 需要 1.5s（auth §9.2 表格）。这对 AI agent 的首次注册影响不大（一次性操作），但如果 `login_pow` 或 `recovery_pow` 被触发，AI agent 在执行关键操作前需要等待 PoW 求解——增加 1.5s 延迟。

这个延迟在设计上合理，但从性能角度需要明确：PoW 求解在客户端进行，不消耗服务器资源——这是好的。但文档应该明确 AI agent 的 PoW 求解预期延迟，帮助 agent 开发者规划超时和重试策略。

**建议**：
1. 在 AI agent onboarding 文档（`docs/auth/onboarding-ai`）中明确 PoW 求解延迟预期
2. 考虑 AI agent 可以预求解 PoW（offline），注册时直接提交

---

## Recommendations

1. **统一 Auth Nonce 存储方案**（D1）——删除 FDB schema 中的 `auth/request_nonce/`，统一使用 Dragonfly SETNX TTL。这是最紧迫的矛盾。

2. **补充内存预算**（D2）——为 pathfinding/visibility cache 定义 entry 大小和总内存预算。这直接影响硬件规格和运维规划。

3. **CRL 缓存分级**（D3）——考虑按证书类型分级吊销延迟：高价值操作（CodeSigning/Admin）使用更短的吊销窗口。

4. **Arena 独立 FDB 预算**（D4）——为 Arena 模式定义独立的 tick 内 FDB commit 窗口和重试策略。

5. **Mod 执行预算占比**（D5）——定义 Rhai mod 总执行时间占 EXECUTE 阶段的比例上限，帮助服主规划 mod 组合。

6. **Tick Trace 保留策略**（D10）——在 FDB 存储预算中包含 TickTrace 的保留期和迁移策略。

7. **Tier 2/3 快照扩展优先**（engine §3.2 快照扩展路线）——文档正确指出 Tier 2/3 的完整 spec 必须在 Phase 1 实现前完成。作为性能评审员特别强调：增量快照的 modification-set tracking 的性能特征（CPU 开销、内存足迹）必须在 spec 中量化，不能只做架构描述。

---

## Consistency Gaps

| # | 位置 A | 位置 B | 矛盾 |
|---|--------|--------|------|
| G1 | auth.md §6.2 FDB subspace `auth/request_nonce/` | auth.md §10.8「Nonce 存储不写 FDB。使用 Dragonfly SETNX TTL」 | FDB schema 定义了 nonce 存储，但 hot path 描述使用 Dragonfly。见 D1。 |
| G2 | engine.md §3.4「Snapshot total: 128MB (500 players × 256KB)」 | engine.md §3.2 两阶段快照「复杂度 O(实体数 + 玩家数 × 可见房间数)」 | 128MB 预算是基于每玩家 256KB × 500 的简单乘法，与两阶段快照的实际复杂度不一致。实际中并非所有玩家的 snapshot 都达到 256KB 上限，也不需要 500 份独立完整副本。 |
| G3 | gameplay.md §8.2 Vanilla Ruleset「Leec/Fabricate 为 Tier 2+」 | gameplay.md §特殊攻击方式表格 Leech/Fabricate 标注「🔮 Tier 2+ — 通过 `[[custom_actions]]` 注册」但默认 world.toml 示例中已注册 | 设计说 Tier 2+ 但默认配置已包含——不矛盾但混淆了「规范定义」和「示例配置」的边界。 |

---

## Algorithmic Risks

1. **Pathfinding A* 爆炸**：per-player 10,000 entry LRU cache 在大型地图（50×50 格 × 50 房间 = 125,000 格子）下，pathfind 请求可能频繁 cache miss。如果玩家的 100 个 drone 每 tick 都在不同位置请求 pathfind，cache hit rate 可能很低。建议在 COLLECT 阶段使用按房间预计算的 pathfinding 距离表（Floyd-Warshall per room + exit-to-exit compression）作为基础层，per-player 缓存作为覆盖层。

2. **Visibility 计算 O(N²)**：500 玩家 × 各 10+ drone，每个 drone 需要计算对其他所有实体的可见性。naive 实现 O(drones × entities) = 5,000 × 50,000 = 250M 次可见性检查/tick。Visibility cache (per-player 50,000 entries, TTL=1 tick) 缓存的是结果而非减少计算量——TTL=1 tick 意味着每 tick 重新计算。建议使用空间分区（room-level grid + observer range）减少计算量，而非依赖缓存。

3. **FDB Transaction atomicity with keyframe writing**：每 K=100 tick 写入一次 keyframe（约 16MB）。如果 keyframe 写入与 delta 写入在同一个事务中，事务大小会显著增加（delta + 16MB keyframe vs delta only）。Tier1 FDB transaction size 16MB 上限意味着 keyframe tick 的事务可能接近甚至超过上限。建议 keyframe 写入使用独立事务（在 delta 提交后异步写入）。

---

*End of review. 13 findings (2C / 4H / 4M / 3L), 3 consistency gaps, 3 algorithmic risks identified.*
