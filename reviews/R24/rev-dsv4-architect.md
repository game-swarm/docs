# R24 Closure Verification — 架构方向 (DeepSeek V4 Pro)

> **评审判**: rev-dsv4-architect
> **日期**: 2026-06-19
> **审查范围**: B1 (World经济启动), B3 (确定性合同), B4 (容量证明+benchmark)

---

## Verdict: **APPROVE**

所有 3 个待验证项均已正确闭合。

---

## [B1] CLOSED — World 经济启动

**证据**:

1. **初始资源注入** — `08-resource-ledger.md` §2.3 (marked `R23 D1/A`):
   - `starting_resources` = `{Energy: 5000, Minerals: 2000}` — 新玩家进入世界时获得的初始资源包
   - `free_upkeep_controllers` = 1, `free_upkeep_drones` = 3, `free_upkeep_ticks` = 2000
   - 反 smurf 绑定: 同一身份（证书）只享受一次免维护

2. **确定性执行顺序** — `08-resource-ledger.md` §4: `WorldStartupSubsidy` 作为资源操作顺序的第 1 步，在 UpkeepDeduction 之前执行

3. **Growth Path 验证** — `08-resource-ledger.md` §2.3: 提供了完整的 0→2000+ tick 经济 break-even 分析表，展示从 safe_mode (0-500, 净增长) 到 full economy (2000+, 自维持) 的过渡路径

4. **权威注册** — `api-registry.md` §5.1 将 starting_resources/free_upkeep 参数列入全局容量限制表，均标记 `R23 D1/A`

**闭合判断**: World 经济启动的资源配置、免维护策略、反滥用机制已完整定义，跨 doc 一致性可验证。

---

## [B3] CLOSED — 确定性合同

**证据**:

1. **确定性声明** — `01-tick-protocol.md` §7.1:
   ```
   给定 tick N-1 状态 + tick N RawCommand + world_seed + 激活模组列表 
   → execute_deterministic == recorded_state
   ```
   每 tick 产出 `state_checksum` 写入 TickTrace

2. **5 层命令排序键** — `01-tick-protocol.md` §9.1:
   ```
   sort_key = (priority_class, shuffle_index, source_rank, sequence, command_hash)
   ```
   完全确定性排序，第五层 Blake3(command_json) 为稳定 tiebreaker

3. **RNG 确定性** — `01-tick-protocol.md` §9.5: Blake3 XOF namespace 隔离 (combat/loot/npc_spawn/event)，WASM host function 不暴露熵源

4. **Replay-Critical Subset** — `05-persistence-contract.md` §2.1: 10 项必填字段 (tick, state_checksum, system_manifest_hash, world_config_hash, mods_lock_hash, commands+rejections, fuel_ledger, deploy_activation_decision, canonical_codec_version, terminal_state) 在 FDB 事务中原子提交，缺失任一则 tick 不可 replay

5. **Deploy 完整状态机** — `05-persistence-contract.md` §2.3: VALIDATE → UPLOAD_PREPARE → MANIFEST_COMMIT → ACTIVATION_PENDING → ACTIVE/FAILED, 关键不变量: FDB manifest 是 deploy 唯一权威记录，`activation_tick = current_tick + 1`, deploy_mutation replay class 通过 fdb_version_counter 全序重放

6. **Commit Retry 语义** — `05-persistence-contract.md` §7: collect_id/attempt_id/commit_id 三标识符体系，跨重试 COLLECT 缓存复用，fuel 不追加扣费

7. **ECS 调度权威** — `06-phase2b-system-manifest.md`: 29 systems, Phase 2a inline 6 + Phase 2b deferred 23, serial spine + 3 parallel sets, Component R/W 矩阵覆盖全部 29 systems 的读写关系与并行安全证明

8. **CI 确定性验证** — `01-tick-protocol.md` §7.2: 随机采样 tick full replay 验证，`--release` 与 `--debug` 下比较 state_checksum，FDB 故障注入 CI 测试 (R23 D6/B)

9. **输出状态合同** — `01-tick-protocol.md` §9.3: WASM tick()/MCP snapshot/WebSocket delta/Replay/TickTrace 五消费端版本语义一致，关键不变量: WASM 与 MCP 始终看到同一份权威快照

**闭合判断**: 确定性合同从输入→执行→输出→审计→验证全链路闭合。排序键、RNG、ECS 调度、部署时序、重试语义、Replay-Critical Subset 均明确定义且可 CI 验证。

---

## [B4] CLOSED — 容量证明 + Benchmark

**证据**:

1. **Tick Pipeline 预算** — `engine.md` §3.4.1:
   | 阶段 | World 预算 | Arena 预算 |
   |------|-----------|-----------|
   | Tick interval | 3000ms | 300ms |
   | SNAPSHOT build | ≤50ms (p99) | ≤20ms (p99) |
   | COLLECT | ≤2500ms | ≤200ms |
   | EXECUTE | ≤400ms | ≤50ms |
   | COMMIT (FDB) | ≤50ms (p99) | ≤20ms (p99) |
   | BROADCAST | ≤50ms | ≤10ms |

2. **容量合同** — `engine.md` §3.4.2:
   - Active players: target 500 / hard cap 1000
   - Active drones: target 5000 / hard cap 10000
   - Total entities: hard cap 50000
   - Per-player drone cap: 50 (三层 cap: per-room / per-player / per-world)

3. **Aggregate CPU Admission Formula** — `engine.md` §3.4.2:
   ```
   aggregate_cpu_budget = floor(2500ms × CPU_CORES × 500 MIPS/core)
   per_player_cpu_quota = floor(aggregate_cpu_budget / active_players)
   effective_per_player_quota = min(per_player_cpu_quota, 10,000,000)
   ```
   含 admission 决策: effective_per_player_quota < 500,000 → ERR_CPU_SATURATED

4. **500/1000 Player Capacity Derivation** — `engine.md` §3.4.2: 完整的数学推导，500 players at p50 execution time 饱和 Collect phase，1000 players 依赖并行 worker pool 分摊

5. **Synthetic Benchmark Gates** — `05-persistence-contract.md` §8.3:
   | Benchmark | 目标 | 判定标准 |
   |-----------|------|---------|
   | Command validate loop | 100k commands/tick | p99 < 50ms |
   | Command apply loop | 100k commands/tick | p99 < 100ms |
   | Entity snapshot clone | 50k entities | p99 < 20ms |
   | Entity snapshot restore | 50k entities | p99 < 30ms |
   | Snapshot stitching | 1000 × 256KB snapshots | p99 < 100ms |
   | FDB single-tx commit | 500 active players | p99 < 200ms, conflict rate < 1% |
   | FDB room-partition commit | 1000 players, 200 rooms | p99 < 500ms, per-room conflict rate < 1% |
   | Pathfinding | 50×50 A*, 100 concurrent | p99 < 10ms/node |
   | Rollback Bevy snapshot/restore | 500 entities | p99 < 50ms |

6. **Gate 失败语义** — `05-persistence-contract.md` §8.3: "Gate 失败 → 对应容量声明不可信，需降级规模或优化实现"

7. **硬件基线** — `api-registry.md` §5.5: target 500 players @ 64GB RAM/32 cores, hard cap 1000, worker pool 默认 256/hard cap 1000

8. **Per-Player Fair-Share Admission** — `api-registry.md` §5.6: pathfinding 100,000 nodes/tick 按活跃玩家数均分，先到先得，超出即 ERR_BUDGET_EXHAUSTED

**闭合判断**: 容量合同具有硬数字、数学推导和明确的 benchmark gate 阈值。Gate 失败语义明确，"超过容量即降级"的可测试闭合回路完整。

---

## 审查结论

| 项目 | 状态 | 关键落地文档 |
|------|:----:|------------|
| B1 — World 经济启动 | CLOSED | 08-resource-ledger.md §2.3, api-registry.md §5.1 |
| B3 — 确定性合同 | CLOSED | 01-tick-protocol.md §7/§9, 05-persistence-contract.md §2, 06-phase2b-system-manifest.md |
| B4 — 容量证明+benchmark | CLOSED | engine.md §3.4, 05-persistence-contract.md §8.3, api-registry.md §5.5-5.6 |

**Verdict: APPROVE** — 所有待验证项均已正确闭合，文档间一致性可交叉验证。
