# R27 Determinism & Performance Review — rev-dsv4-determinism-perf

> Phase 1 Clean-Slate 独立评审 | 方向: Determinism & Performance
> 评审员: dsv4-pro | 日期: 2026-06-20

---

## Verdict: CONDITIONAL_APPROVE

Determinism 基础合同设计扎实——Blake3 单原语、五层排序键、定点算术、IndexMap、CI 确定性测试均到位。Performance 容量声明需要 benchmark gate 验证后才能信任，且 worker pool 模型与 per-player timeout 模型之间存在未解决的架构张力。建议：所有 P1/P2 项在实现 Phase 通过对应的 synthetic benchmark 后闭合；T1（seed forward-security）接受为已知风险但需确认检测机制已spec。

---

## Strengths

1. **Blake3 单原语覆盖哈希+PRNG**：Blake3 XOF 的 `seed+offset` 模式天然适配 per-entity per-tick 确定性随机流，消除 ChaCha 依赖，审计面减半。seed 推导公式 `Blake3(domain_sep || world_seed || tick.to_le_bytes())` 提供 namespace 隔离。

2. **五层排序键** `(priority_class, shuffle_index, source_rank, sequence, command_hash)`：Fisher-Yates 种子洗牌保证公平性+确定性，`command_hash = Blake3(command_json)` 作为稳定 tiebreaker 消除所有歧义。这是 RTS 确定性排序的教科书实现。

3. **两阶段快照架构**：一次构建→按房间分片→按玩家拼接，复杂度从 O(P×E) 降为 O(E + P×visible_rooms)。消除每玩家重复序列化的开销，且快照在 COLLECT 开始时一次性确定——WASM tick() 与 MCP query 看到同一份权威快照。

4. **定点算术全覆盖**：三份 IDL（game_api, auth_api, economy）中所有 f64 已替换为 BasisPoints/i64/u64 定点类型。`BasisPoints` (0-10000, 1bp=0.01%), `ResourceRate_i64` (1e6=1.0/tick), `MilliUnits` (1000=1 unit)——精度足够且跨平台确定。

5. **IndexMap 显式声明**：`Resource.amounts: IndexMap<String, u32>` 和 `Source.produces: IndexMap<String, u32>` 明确拒绝 `std::HashMap` 的非确定性迭代顺序。

6. **COLLECT 缓存跨 FDB 重试复用**：`collect_id` / `attempt_id` / `commit_id` 三层标识设计精巧——首次 COLLECT 后缓存结果，retry 不重新执行 WASM，不追加扣费。fuel 消耗上限 = 1×MAX_FUEL。消除重试路径的非确定性风险。

7. **FDB 故障注入 CI 测试**：`fdb_commit_failure_restores_snapshot_consistency()` 以确定性种子随机触发 10% tick 的 commit 失败，验证 `state_checksum` 恢复一致性——这是正确的确定性测试方法。

8. **单一指令管线**：所有入口（WASM、MCP、REST、admin CLI）走同一 `validate → apply` 路径，无绕过。Admin 命令通过 trait 设计确保无独立代码路径。

9. **Wasmtime 双预算**：fuel metering（指令计数）+ epoch interruption（墙钟），配合 long-lived worker pool + per-tick Store reset，在隔离性与性能间取得合理平衡。

10. **Room-Partition FDB 明确分阶段**：承认单事务仅 MVP（≤50 players），500+ 需 room-level partition——这是在正确的时间点做出的正确架构预留。

---

## Concerns

### Determinism

#### T1 [High] PRNG seed 前向保密——链式可推导，泄露窗口 10,000 tick

**位置**: `specs/core/01-tick-protocol.md` §3.1

种子轮换算法 `new_seed = Blake3(old_seed || current_tick)` 是单向链：知道 tick N 的 seed 即可推导 N+1, N+2, ... 的所有未来种子。文档自身承认此风险并标记为"已接受的设计决策"。

**影响面**：
- 未来 tick 的玩家排序可预测（策划排序攻击）
- 未来 tick 的 RNG 输出可预测（combat 伤害浮动、spawn 位置、资源再生等）
- 攻击者可预演所有 tick 的随机结果，选择剥削路径

**当前缓解**：每 10,000 tick 轮换 → 限制泄露窗口宽度。服主手动 bump epoch → 唯一恢复手段。

**缺口**：
- "玩家行为异常检测"在 runbook 中描述为检测手段，但我未在允许阅读的文档子集中找到该检测系统的 spec。若该检测系统尚未 spec，则实际恢复依赖服主人工发现——窗口期内攻击者可能已造成不可逆破坏。
- 不要求实现密码学完善前向保密（双向不可推导）的理由是"与确定性回放要求冲突"——此理由成立。但定期从外部熵源注入并非唯一方案：可使用单向 ratchet（每个 tick 的 seed 仅用于当前 tick，不暴露推导链）同时保持回放确定性（TickTrace 记录每 tick 的独立 seed）。

**建议**: 若 seed-leak 检测系统已在 security specs 中定义，此条降级为 Low（已知风险已充分缓解）。若未定义，升级为 Critical 并要求在实现 Phase 前补充自动化检测 spec。

#### T2 [High] ECS entity 迭代顺序依赖显式排序——CI 无法检测遗漏

**位置**: `specs/core/06-phase2b-system-manifest.md` §3, §6

Manifest 声明"所有系统内实体迭代按 `StableEntityId` 或 canonical key 排序，不依赖 Bevy archetype order"。但 CI 验证仅为"静态分析 R/W 矩阵"——静态分析无法检测一个系统是否在运行时使用 archetype order 而非显式排序。

**风险场景**：
- 开发者新增 system 时忘记显式排序 → 该 system 的输出变为非确定性
- `--release` vs `--debug` 的 `state_checksum` 比较可检测此问题（因为优化级别可能改变 archetype 内部顺序），但仅当该 system 的副作用影响 checksum 时才有效

**实际风险**：Bevy 的 archetype 存储在 `SparseSet` 中，其迭代顺序在相同二进制/相同输入的条件下是确定的。但跨编译优化级别、跨 Bevy 版本升级时可能变化。"不依赖 archetype order"是正确的设计原则，但遗漏检测需要运行时断言（如 debug build 中验证 system 输出不随输入顺序变化）。

**建议**: 在 CI 中增加 randomized entity iteration order test（debug build 随机打乱 archetype 内部顺序后验证 state_checksum 不变）。这比仅依赖 `--release` vs `--debug` 比较更可靠。

#### T3 [Medium] `status_advance_system` 调度位置跨文档冲突

**位置**:
- `specs/core/02-command-validation.md` §3.19（非权威）
- `specs/core/06-phase2b-system-manifest.md` §1（权威）

02-command-validation.md §3.19 描述 status_advance 位置为：
```
death_mark → spawn → spawning_grace → combat → status_advance → (regeneration, decay 并行) → death_cleanup
```

06-phase2b-system-manifest.md §1（权威源）描述为：
```
death_marker → spawn → spawning_grace → regeneration → combat → special_attack_reducer → damage_application → status effects (S16-S22, 含 status_advance) → aging → decay → death_cleanup
```

差异：02 版本中 regeneration 在 status_advance 之后且与 decay 并行；manifest 中 regeneration 在 combat 之前（S10），status_advance 在 damage_application 之后。manifest 为权威源，02 版本为 stale。

**建议**: 修复 02-command-validation.md §3.19 的调度描述，改为引用 manifest 而非重列顺序。

#### T4 [Medium] RNG namespace 表格歧义——`combat` 与 `event` 列相同 seed

**位置**: `specs/core/01-tick-protocol.md` §9.5

表格列出：
| Namespace | Seed 来源 |
|-----------|----------|
| `combat` | `world_seed + tick` |
| `event` | `world_seed + tick` |

两者列相同。下方文字澄清使用 `Blake3(domain_sep || world_seed || tick.to_le_bytes())` 且 domain_sep 不同——这实际是正确的（不同的 domain_sep 产生不同的 XOF 流）。但表格可能误导实现者使用纯 `world_seed + tick` 而不加 domain_sep。

**建议**: 表格中 Seed 来源列改为完整公式或至少标注 "+ domain_sep"，避免歧义。

#### T5 [Low] `host_path_find` cache_miss_penalty fuel 未定义固定值

**位置**: `specs/reference/api-registry.md` §4.4

`host_path_find` fuel = `500 × nodes + 200 × edges + cache_miss_penalty`。cache_miss_penalty 的下限未定义为固定值——若实现为"实际 CPU 重算时间对应的 fuel"，则在不同硬件上产生不同 fuel 消耗，破坏跨节点一致性。

**建议**: 定义 `cache_miss_penalty = 5000`（固定值）或等价于"recompute from scratch"的固定 fuel 成本。

### Performance

#### P1 [Critical] COLLECT budget 在 target 500 players 处零余量

**位置**: `design/engine.md` §3.4.2

容量推导：
```
500 players × 5ms avg = 2500ms ← 严格等于 COLLECT budget
→ p99 players (15ms) 会导致排队，增大 tick 超时风险
```

此推导自身承认"500 = target（安全操作点，有余量处理 p99 延迟）"与数学矛盾：p50 已饱和 budget，p99 将直接突破。500 不是"有余量的安全操作点"而是"无余量的饱和点"。

**结论**：500 应为 **stress target**（需验证的峰值），而非 **safe target**。Safe target 应在 ~350-400 范围（p50 × 400 ≈ 2000ms，留 500ms p99 余量）。建议重新标注或降低 target 到 p95 能稳定完成的数值。

#### P2 [Critical] Worker pool 模型与 per-player timeout 模型冲突

**位置**: `design/engine.md` §3.4.2, §3.4.3; `specs/core/01-tick-protocol.md` §2.2

两个模型存在根本性架构张力：

1. **Worker pool 模型** (§3.4.2)：pool size = min(256, active_players)。500 players → 256 workers → 每 worker ~2 players **串行执行**。
2. **Timeout 模型** (§2.2)：每 player 独立 deadline = 2500ms，超时 → 0 指令。

**冲突**：若 worker-1 的 player-A 消耗完整 2500ms（正常，在 budget 内），queued 的 player-B 在 worker-1 上根本得不到执行机会——它不是"超时"，而是"从未开始"。player-B 的 2500ms deadline 从未启动。

**修复需求**：
- 选项 A：worker pool size 必须 ≥ active_players（每 player 独占 worker），或
- 选项 B：per-worker timeout = 2500ms / players_per_worker（在 worker 层面分片），或
- 选项 C：sandbox 执行改为 async/parallel dispatch（非 worker-pool 串行模型）

当前设计选择了 worker pool（性能优化）但保留了 per-player timeout（正确性保证）——两者不可兼得。必须选择其一并调整另一模型。

#### P3 [High] FDB 单事务 commit 500 players 的 p99<200ms 目标激进

**位置**: `specs/core/05-persistence-contract.md` §8.3

Synthetic benchmark gate: "FDB single-tx commit, 500 active players: p99 < 200ms, conflict rate < 1%."

FDB 的优势在大量小事务并发，而非单一大事务。500 玩家的单事务需包含：全部 commands + rejections + fuel ledger + entity state deltas + resource ledger changes + manifest/hash updates。FDB 事务大小每 tick 随活跃玩家线性增长。p99<200ms 在 500 玩家规模下需要实测验证——这是一个需要 benchmark gate 来证明或证伪的声明，不应作为已成立的假设。

好消息：文档自身将此作为 benchmark gate（"Gate 失败 → 对应容量声明不可信"），这意味着设计者意识到这是需要验证的而非已成立的。当前状态可接受——只需确认这些 benchmark 在实现 Phase 中被实际执行。

#### P4 [Medium] Dragonfly 同步更新阻塞 NATS 广播

**位置**: `specs/core/01-tick-protocol.md` §4.2

```text
1. Dragonfly.update(delta)
2. NATS.publish("tick.{tick}", delta)
```

Dragonfly 更新在 NATS 发布**之前**且是同步的。若 Dragonfly 响应慢（高负载、网络抖动），NATS 广播被延迟，客户端收到 delta 的时间被推迟。

Dragonfly 的角色是"非权威缓存"——允许滞后。广播的实时性对玩家体验更重要。两者操作同一 delta 数据，应并行执行或 Dragonfly 异步化。

**建议**: Dragonfly update 和 NATS publish 并行执行（无依赖），或 Dragonfly update 改为异步（fire-and-forget，失败时从 FDB 重建）。

#### P5 [Medium] Bevy World 全量快照每 tick — 50K entities 的 clone+restore 在 50ms 内？

**位置**: `specs/core/01-tick-protocol.md` §3.5; `specs/core/05-persistence-contract.md` §8.3

Benchmark gate: "Entity snapshot clone: 50k entities, p99 < 20ms" + "Entity snapshot restore: 50k entities, p99 < 30ms" = 总计 50ms。

Bevy World 深拷贝 50,000 个 entity 的所有 component 在 20ms 内是对 Rust 内存分配器的严峻考验。Archetype 存储意味着 component 数据分散在多个 `Column` 中——clone 需要遍历所有 archetype 的所有 column 并复制。这是可以优化的（自定义 allocator、copy-on-write），但文档未描述优化策略。

同样：这是 benchmark gate 而非已成立声明，当前可接受。

#### P6 [Low] COLLECT 阶段 per-player snapshot stitching 的 256KB×1000 场景

**位置**: `design/engine.md` §3.4.2; `specs/core/05-persistence-contract.md` §8.3

Benchmark gate: "Snapshot stitching: 1000 × 256KB snapshots, p99 < 100ms."

这是指从分片快照中为 1000 个玩家各拼接出 ≤256KB 的可见实体视图。1000 × 256KB = 256MB 的数据搬运。若实现为 per-player 独立拼接（复制可见实体到 per-player buffer），内存带宽可能成为瓶颈。若实现为 view/pointer 结构（零拷贝），则可行但复杂度高。

建议在实现 Phase 中明确拼接策略（零拷贝 vs 复制）。

#### P7 [Low] `status_advance_system` 每 tick 全量扫描所有 active status

**位置**: `specs/core/06-phase2b-system-manifest.md` §S22

S22 每 tick 迭代所有 active StatusState components：每个 status 的 duration--, expire check, apply/reverse effects。10,000 entities × 平均 0-3 statuses = 最多 30,000 次迭代。每次迭代工作量小，目前不构成瓶颈。仅在大规模 status-spam 场景下才可能成为问题——且该场景受 per-drone cooldown 限制。

---

## Replay Integrity Issues

1. **WASM 模块跨架构重放**：模块缓存键含 `target_arch`，WASM 执行结果跨架构不可复现。缓解：TickTrace 记录 `Command[]` 而非 WASM 输出，回放时执行命令序列不重调 WASM（06-phase2b-system-manifest.md §6.3.3 确认）。状态：已处理。

2. **Deploy 时序确定性**：`fdb_version_counter` 提供 deploy event 的严格全序，replay verifier 以此重放。deploy 在 `activation_tick = current_tick + 1` 生效——当前 tick 不受 deploy 影响。状态：正确。

3. **Snapshot 截断确定性**：距离桶→entity_id 字典序→farthest-first，critical entities 不可截断。排序算法稳定（entity_id 字典序）。状态：正确。

4. **FDB commit 失败后 Bevy World 恢复**：`world.restore(snapshot)` 完全回滚至 Phase 2a 前状态。CI 故障注入测试验证此路径。状态：CI 覆盖到位。

---

## Scalability Limits

| 规模 | 瓶颈 | 当前设计状态 |
|------|------|------------|
| 100 players | 无瓶颈 | MVP 安全区 |
| 500 players | COLLECT budget 饱和 (P1), worker pool 冲突 (P2) | 需 benchmark 验证 + 修复 P2 |
| 1000 players | FDB 单事务不可行 (P3), fuel 极度受限 (2ms/player) | 需 room-partition + benchmark |
| 10000+ players | 水平分片（远期） | 数据模型已预留分片接口 |

**关键路径**: P1 + P2 必须在 500-player benchmark 通过后才能声称支持 500 target。P3 决定 1000-player 的可行性。

---

## CrossCheck — 跨方向检查请求

- **CX1**: PRNG seed 前向保密泄露检测系统是否已 spec？01-tick-protocol.md runbook 提到"玩家行为异常检测"但未指定具体检测机制。→ 建议 **Architect/Security** 检查是否有独立的 seed-leak detection spec，若没有建议补充。

- **CX2**: `status_advance_system` 调度位置在 02-command-validation.md §3.19 与 06-manifest §1 矛盾。→ 建议 **Architect/Speaker** 将 02 版本同步至 manifest 权威版。

- **CX3**: RNG namespace 表格（01-tick-protocol.md §9.5）中 `combat` 和 `event` 的 seed 来源列相同值。下方文字澄清了 domain_sep 隔离，但表格可能误导实现。→ 建议 **Architect** 修正表格以减少实现歧义。

- **CX4**: 1000-player 时 per-player 有效 fuel budget ~2ms——这是否影响游戏性（玩家可执行的指令量）？→ 建议 **Designer/Economy** 评估 fuel throttling 对游戏体验的影响。

- **CX5**: worker pool size=256 与 per-player timeout=2500ms 冲突 (P2)——此问题跨越 engine（调度模型）、sandbox（进程模型）、tick-protocol（超时语义）三个域。→ 建议 **Architect** 在修复决策中主导（涉及 engine/sandbox 合同变更）。

---

*评审完成。建议在实现 Phase 中优先解决 P1+P2（阻塞 500-player 验证），然后运行 §8.3 全部 8 个 synthetic benchmark gate 以闭合 P3/P5/P6。*