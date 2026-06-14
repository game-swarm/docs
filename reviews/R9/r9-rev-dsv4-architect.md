# R9 终审报告 — Architect Reviewer (DeepSeek V4 Pro)

**评审日期**: 2026-06-14
**评审范围**: DESIGN.md + tech-choices.md + ROADMAP.md + specs/p0/*（9份）
**评审维度**: ECS调度正确性 | Tick生命周期完整性 | 数据一致性(FDB+Dragonfly) | 算法复杂度

---

## Verdict: REQUEST_MAJOR_CHANGES

发现 3 个 D1 阻断级问题、4 个 D2 需修复问题和 3 个 D3 低优建议。D1-1 (FDB回滚与内存状态不一致) 和 D1-2 (COLLECT阶段状态读取源未定义) 涉及核心正确性，必须在 Phase 1 前解决。其余可在 Phase 1-2 中修复。

---

## D1 (阻断级 — 必须在实现前修复)

### D1-1: FDB Commit 失败时 Bevy ECS 内存状态不可回滚

**位置**: DESIGN.md §3.2 阶段二 + P0-1 §3.4

**问题描述**:

P0-1 §3.4 规定 EXECUTE 阶段整个包裹在 FDB 事务中：
```
txn = fdb.create_transaction()
for command in sorted_commands:
    result = validate_and_apply(txn, command, world_state)
...
txn.commit()
```

Bevy ECS System（harvest_system、combat_system 等）在 EXECUTE 阶段**直接修改 `World` 内存结构**。若 `txn.commit()` 失败（FDB 冲突/网络分区），设计宣称：

> "放弃的 tick：世界状态不变，tick_counter 不递增"（P0-1 §3.4）

但 Bevy `World` 已被 ECS System 原地修改——**没有快照/回滚机制**。FDB 事务回滚只影响持久化层，不影响已被污染的 ECS 内存状态。下一个 tick 的 COLLECT 阶段会读取到半修改的世界。

**影响面**: 一旦 FDB 提交失败（非零概率事件），引擎会进入不可恢复的损坏状态——世界已被部分修改但 FDB 中没有记录。回放时 `execute_deterministic != recorded_state` 必然失败。

**修复建议**:
方案 A（推荐）：EXECUTE 前对 Bevy World 做 `world.snapshot()`（深度 clone 所有 Archetype 和 Component），FDB commit 失败时恢复快照。需测量 clone 开销是否在 ~0.5s EXECUTE 预算内。
方案 B：EXECUTE 阶段不在 Bevy World 上直接运行——改为在 FDB 事务内读写（FDB 作为唯一权威状态存储），EXECUTE 只做校验，BROADCAST 阶段再从 FDB versionstamp 重建 Bevy World。代价是延迟显著增加。
方案 C：利用 Bevy 的 `World::as_unsafe_world_cell` + 手动双缓冲——维护两个 World 实例，EXECUTE 在副本上运行，commit 成功后 swap。

**最低可接受方案**: 至少文档化这个问题，并在 P0-1 中增加 "FDB commit 失败 → 引擎重启并读取 tick N-1 的 FDB 快照恢复" 的恢复流程。这不能修复正确性但能防止静默损坏。

---

### D1-2: COLLECT 阶段世界状态读取源未定义

**位置**: P0-1 §2.3 + DESIGN.md §3.2

**问题描述**:

COLLECT 阶段为每个玩家生成 snapshot（可见世界状态快照）。这需要读取当前世界状态。但**读取源未指定**：

- 选项A：从内存中的 Bevy World 读取（最快）
- 选项B：从 Dragonfly 缓存读取
- 选项C：从 FDB 读取（最权威）

如果从 Dragonfly 读取，存在以下竞争窗口：
```
Tick N EXECUTE 完成 → FDB committed → Dragonfly 更新中...
                                                  ↑
                                    Tick N+1 COLLECT 开始
                                    → 可能读到旧数据
```

Dragonfly 写入是**异步的**（P0-1 §4.2: "非权威缓存，允许滞后"），如果 COLLECT 从 Dragonfly 读，snapshot 可能落后于实际 FDB 状态。

如果从 Bevy World 内存读取，需确认 Bevy World 在 COLLECT 阶段是否已包含 tick N 的所有变更。根据设计，COLLECT 是 tick N+1 的第一阶段，此时 tick N 的 EXECUTE 已完成。所以 Bevy World 应该反映 tick N 后的状态。这是正确的——但需要**明确文档化**。

**影响面**: 若 COLLECT 从 Dragonfly 读取且 Dragonfly 滞后，玩家收到的 snapshot 是旧数据，指令基于过时信息。导致高拒绝率、玩家困惑。

**修复建议**: 
在 P0-1 §2.3 中明确写出：
```
fn build_snapshot(player_id, tick) -> Snapshot:
    // COLLECT 阶段始终从 in-memory Bevy World 读取
    // Bevy World 反映上一个已完成 tick 的 FDB-committed 状态
    entities = visibility_filter(bevy_world.all_entities(), player_id, tick)
```
并在 COLLECT 阶段开始时加一个断言：`assert!(bevy_world.tick_counter == current_tick - 1)`。

---

### D1-3: Wasmtime 版本锁定与安全 SLA 之间的矛盾

**位置**: P0-4 §2.1 + DESIGN.md §8.8

**问题描述**:

P0-4 锁定 Wasmtime 版本：`wasmtime = "=30.0"`。DESIGN.md §8.8 回放保证依赖：
> "相同 Wasmtime pinned 版本下 execute_deterministic == recorded_state"

同时 P0-4 §2.1 安全 SLA 承诺：
> "严重 CVE (CVSS ≥ 9.0): 72 小时内评估 + 补丁，必要时临时降级到已知安全版本"

这两个需求**冲突**：
- 安全 SLO 要求在发现 CVE 后升级/降级 Wasmtime
- 回放保证要求 Wasmtime 版本不变
- 降级到"已知安全版本"意味着编译行为改变 → 回放失败

**影响面**: 一旦 wasmtime 30.0 出现严重 CVE，引擎面临二选一：保持运行（有安全漏洞）或升级（破坏回放确定性）。`=30.0` 的语义是"精确此版本"——连 patch 版本升级都不允许。

**修复建议**:
方案 A：在 Replay Trace 中记录每个 tick 的 `wasmtime_version`。回放时使用对应版本的 Wasmtime。需要维护多版本 Wasmtime 编译产物（通过不同的 crate feature 或 workspace member）。
方案 B：接受 patch 版本（`"~30.0"` 允许 30.0.x），并验证 Bytecode Alliance 的 patch 升级是否改变 Cranelift 代码生成。通常安全 patch 不改代码生成。
方案 C：设计一个 WASM 执行录播模式——将 WASM 的 tick() 调用结果（Command[]）也记录到 Trace 中，回放时直接使用记录的命令，不重新执行 WASM。这完全绕过了 Wasmtime 版本依赖。

**推荐方案 C** 作为长期解（P0-1 §6.3.1 已部分覆盖："AI 玩家：记录 ACCEPTED 指令，不是原始 LLM 输出"），方案 B 作为短期缓解。

---

## D2 (高优先级 — Phase 1-2 修复)

### D2-1: 种子洗牌算法存在偏差（modulo bias）

**位置**: P0-1 §3.1

**问题描述**:

```rust
// P0-1 §3.1
// shuffle = Blake3 XOF: for i in 0..N: position[i] = XOF.read_u64() % (N - i)
```

使用 `read_u64() % (N - i)` 产生 Fisher-Yates shuffle 时，当 `(N - i)` 不整除 `2^64` 时，取模结果有微小偏差。对于 N=500 玩家，偏差约为 `2^64 mod 493 / 2^64 ≈ 10^-17`——实际影响可忽略。

**但**这个问题是确定性系统的特征信号——如果将来有人审查公平性，会发现取模偏差。而且这是**可修复的**：

```rust
// 无偏差 Fisher-Yates（rejection sampling）
fn unbiased_rand_range(xof: &mut Blake3XofReader, max: u64) -> u64 {
    let limit = u64::MAX - (u64::MAX % max);
    loop {
        let r = xof.read_u64();
        if r < limit { return r % max; }
    }
}
```

对于 Blake3 XOF（~6 GB/s），rejection sampling 的开销大约 1 in 2^64 次循环——零额外开销。

**修复建议**: 使用无偏算法。在公平性敏感的玩家排序场景，不应留下任何可争议的空间。同时添加单元测试验证 shuffle 分布均匀性（卡方检验）。

---

### D2-2: Resource.amounts 使用 HashMap 但确定性合同要求 IndexMap

**位置**: DESIGN.md §3.1 (Resource struct) + DESIGN.md §8.8 (Determinism Contract)

**问题描述**:

```rust
// DESIGN.md §3.1
struct Resource {
    amounts: HashMap<String, u32>,
}
```

DESIGN.md §8.8 明确要求：
> "HashMap 顺序: indexmap — 不用 std::HashMap（迭代顺序非确定）"

但 `Resource.amounts` 的类型声明仍是 `HashMap`。任何对 `amounts` 的迭代（生成 snapshot JSON、计算 state_checksum、序列化到 FDB）都会产生非确定结果，破坏回放。

**影响面**: 如果 state_checksum 遍历 Resource.amounts 的所有键，不同 Rust 版本/构建可能产生不同的 checksum → 回放失败。

**修复建议**: 统一改为 `IndexMap<String, u32>`。并在 clippy 配置中 ban `std::collections::HashMap` 的使用（仅允许通过 `indexmap::IndexMap` alias）。

---

### D2-3: Tick 执行超时下的部分状态一致性

**位置**: P0-1 §3.4 + §2.2

**问题描述**:

P0-1 §3.4 描述整个 EXECUTE 在 FDB 事务中。但 EXECUTE 阶段有 500ms 超时（DESIGN.md §3.2）。如果 FDB 事务在接近 500ms 时仍在处理最后几条指令，超时触发 → 事务中断 → 回滚。

但 P0-1 §2.2 的 COLLECT 超时语义是：
> "在 t + 2500ms 时刻: 对每个未响应的玩家: commands[player] = [] (宽容失败)"

EXECUTE 阶段没有类似的**优雅超时处理**。如果 EXECUTE 超过 500ms 怎么办？是粗暴中断 FDB 事务，还是有部分提交策略？

**影响面**: EXECUTE 超时 → FDB 事务回滚 → 整个 tick 丢失。多个连续 tick 超时 → 降级模式 → 服务中断。

**修复建议**: 
在 P0-1 中补充 EXECUTE 超时语义。建议：
- EXECUTE 内部维护 wall-clock timer
- 剩余时间 < 50ms 时停止处理新指令，剩余指令全部 reject（`TickTimeout` rejection reason）
- FDB commit 必须完成，但只包含已处理的指令
- 超时原因计入 TickMetrics

---

### D2-4: Dragonfly 写入失败后的缓存重建无具体流程

**位置**: P0-1 §4.2 + tech-choices.md §6

**问题描述**:

> "Dragonfly.update(delta) // 非权威缓存，允许滞后。失败则从 FDB 重建"

"从 FDB 重建"如何触发？是自动还是手动？重建期间 COLLECT 如何读取世界状态？

tech-choices.md §6:
> "FDB 是权威源，Dragonfly 只是加速读取"

如果 COLLECT 始终从 Bevy World 内存读取（参见 D1-2 修复方案），Dragonfly 失效影响面仅限于 WebSocket 推送和 MCP 查询——可恢复但需明确流程。

**修复建议**: 在 P0-1 中增加 Dragonfly 重建流程：
1. 检测到 Dragonfly 连接断开/写入失败 → 设置 `dragonfly_degraded = true`
2. COLLECT/BROADCAST 跳过 Dragonfly，改为 FDB 直读（ws查询走 REST fallback）
3. 后台 goroutine 尝试 Dragonfly 重连
4. 重连成功后 → 从 FDB `tick_current - 1` 全量恢复 → 清除 degraded flag
5. 超时 N tick 仍不可用 → 告警

---

## D3 (低优先级 — 可延后)

### D3-1: IDL 中 P0-8 Transfer cost 语义模糊

**位置**: P0-8 §2 (Transfer command)

```yaml
Transfer:
    params: { object_id, target_id, resource, amount }
    cost: { transfer_amount: amount }
```

`cost: { transfer_amount: amount }` 是"消耗 amount 资源"还是"花费 amount 作为手续费"？若是传输 fee，应从 amount 中分离。P0-2 §3.4 的 Transfer 校验没有提到额外 cost，只有 `drone.carry[resource] >= amount`。两个文档在此处语义不一致。

**建议**: 如果 Transfer 没有额外 fee，`cost: {}`（像 Move 一样）。如果是 transfer 消耗 = 传输的资源量本身，则需要更清晰命名（如 `cost: { resource_consumed: amount }`），避免与 "手续费" 混淆。

---

### D3-2: MAX_DRONES_PER_PLAYER = 500 的可见性计算爆炸

**位置**: P0-2 §6 + P0-5 §5

P0-5 §5: "每 tick、每玩家可见性计算一次并缓存。缓存键: (tick, player_id), 缓存值: HashSet<EntityId>"

500 玩家 × 500 drone 每玩家（最坏）= 250,000 实体。每个玩家的可见性过滤需检查所有实体：O(P × E) = 500 × 250,000 = 125M 次检查。即使单次检查 100ns，也需要 12.5s。

**建议**: 在 P0-5 中增加**空间索引**（quadtree/grid）加速可见性查询。COLLECT 阶段按房间+视野源分组，而非逐实体逐玩家计算。这可以在 Phase 2（多人上线）时再实现，但应在文档中注明已知瓶颈和解决方案。

---

### D3-3: P0-4 host function 列表与 DESIGN.md 不一致

**位置**: P0-4 §3.2 vs DESIGN.md §5.1

| 函数 | P0-4 §3.2 | DESIGN.md §5.1 | P0-8 IDL |
|------|-----------|----------------|----------|
| `host_get_terrain` | ✅ | ✅ | ✅ |
| `host_get_objects_in_range` | ✅ | ✅ | ✅ |
| `host_path_find` | ✅ | ✅ | ✅ |
| `host_get_world_config` | ✅ | ✅ | ✅ |
| `host_get_world_rules` | ❌ | ✅ | ✅ |

`host_get_world_rules` 在 DESIGN.md 和 P0-8 中存在，但在 P0-4（WASM沙箱基线——权威安全文档）中缺失。这是文档不一致。

**建议**: 在 P0-4 §3.2 中补充 `host_get_world_rules`。所有 host function 的权威列表应只在一处维护（P0-8 IDL），其余文档引用。

---

## Consistency Gaps (跨文档一致性)

### CG-1: EXECUTE timeout 数值不一致

| 文档 | EXECUTE timeout | 
|------|-----------------|
| DESIGN.md §3.2 | ~0.5s (图示) |
| P0-1 §1 | 500ms |
| P0-1 §5 | tick_duration_p99 threshold = 2800ms (整个 tick) |

DESIGN.md 图示中的 "~0.5s" 与 P0-1 明确 "500ms" 一致。但 P0-1 §5 的健康指标 `tick_duration_p99 > 2800ms` 是整体 tick 时间（COLLECT+EXECUTE+BROADCAST），其中 COLLECT 上限 2500ms，剩余 300ms 给 EXECUTE+BROADCAST。但 EXECUTE 预算标 500ms → 2500+500 > 3000。需要明确 EXECUTE 的 500ms 是否包含在 COLLECT 的 2500ms 窗口内（因为 COLLECT 是并行执行，其超时与 EXECUTE 串行执行不重叠）。

**实际物理时间线应为**: COLLECT(0-2500ms) → EXECUTE(2500-3000ms) → BROADCAST(~0ms)。所以 EXECUTE 最多 500ms。与文档一致但缺少显式时间线图。

### CG-2: MCP 网络架构中 Phase 1-2 定位矛盾

P0-3 §2: "MCP Server ← 引擎内嵌 (Phase 1-2)，独立服务 (Phase 3+)"
ROADMAP.md Phase 1 交付物 1.8: "MCP Server 脚手架" 
ROADMAP.md Phase 2 交付物 2.2: "MCP 完整工具集"

Phase 1 的 MCP Server 脚手架与 Phase 2 的完整 MCP 工具集之间的边界不明。P0-3 的规范覆盖了全部工具，但哪些属于 Phase 1 脚手架未标注。

---

## Algorithmic Risks (算法风险评估)

### AR-1: FDB 事务内的指令量上限

每 tick 最坏情况：500 玩家 × 100 指令/玩家 = 50,000 条指令在单个 FDB 事务中。FDB 事务大小限制 10MB。每条指令 + 校验结果估计 ~200 bytes → 50,000 × 200 = 10MB 恰好触达上限。如果增加玩家或指令上限，事务将失败。

**建议**: 在 P0-1 中增加 FDB 事务大小监控，Phase 7 前评估是否需要分片提交。

### AR-2: COLLECT 阶段 snapshot 序列化的内存占用

500 玩家并行 snapshot 序列化。如果每个 snapshot ~200KB（中型世界），总内存 = 500 × 200KB = 100MB。在 COLLECT 的 2.5s 窗口内，100MB 的 JSON 序列化开销取决于 serde_json 性能。估计 ~50-100ms per snapshot for 200KB → 单线程串行需要 25-50s。必须**并行**处理。建议在 P0-1 中明确 snapshot 构建是并行任务池（tokio::spawn 或 rayon）。

---

## Strengths (设计亮点 — 不应改动)

1. **Deferred Command Model 的一致性**: DESIGN.md + P0-2 + P0-4 三处对 "WASM 只返回 JSON，不直接调用 mutating host function" 的约束完全一致。MCP 哲学（"MCP 是屏幕和鼠标，不是操纵杆"）明确且可执行。

2. **Fuel Refund 防滥用**: 退还时序（下 tick 生效）、Deploy-reset 绑定（模块变更则作废）、同源重复退还不累计——三重防护设计严密，堵住了所有明显的退款循环利用路径。

3. **种子洗牌公平性**: Blake3 XOF 基于 world_seed + tick_number 的确定但不可预测的玩家排序，长期期望公平。方案简洁且正确（modulo bias 外）。

4. **三层信任模型**: WASM(不可信) → Rhai(服主信任) → Rust(不可变)，边界清晰，没有权限漏洞。

5. **Blake3 单原语覆盖哈希/PRNG/代码签名**: 减少依赖、降低审计面、统一性能特征。技术选型美学优秀。

6. **P0-5 统一可见性**: `is_visible_to(entity, player_id, tick)` 一个函数覆盖所有输出面，防止侧信道泄露。

---

## 总结

| 类别 | 数量 | 严重度 |
|------|------|--------|
| D1 阻断 | 3 | 必须在 Phase 1 前修复 |
| D2 高优 | 4 | Phase 1-2 修复 |
| D3 低优 | 3 | 可延后 |
| 一致性缺口 | 2 | 文档修整 |
| 算法风险 | 2 | 监控 + 中期优化 |

**Phase 1 可通过的条件**:
1. D1-1 解决方案确定（至少文档化恢复流程）
2. D1-2 明确 COLLECT 读取源
3. D1-3 Wasmtime 版本策略确定
4. D2-1 modulo bias 修复代码评审通过
5. D2-2 HashMap → IndexMap 全量替换完成

满足以上 5 项后，架构从 REQUEST_MAJOR_CHANGES 升级为 APPROVE_WITH_RESERVATIONS。
