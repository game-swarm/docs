# R32 Determinism & Performance Review — rev-dsv4-determinism-perf

## 1. Verdict

**CONDITIONAL_APPROVE**

设计在确定性方面做了非常彻底的工作——f64 全部消除为定点整数、HashMap 替换为 IndexMap、PRNG 统一为 Blake3 XOF、ECS 系统执行顺序固定且可验证、快照构建在所有 WASM 执行前完成。性能预算分配清晰，瓶颈点已识别并标注 benchmark-gated。发现 2 个 High 级别问题需修复后方可进入实现阶段。

---

## 2. 发现的问题

### H1: IndexMap 插入顺序未指定确定性排序规则（High）

**文件**: `design/engine.md` §3.1 (行 44-53)

**描述**: `Resource` 和 `Source` 实体的 `amounts`/`produces` 字段使用 `IndexMap<String, u32>` 以保证"迭代顺序确定"。但 IndexMap 的迭代顺序是**插入顺序**——仅当插入顺序确定时迭代才确定。文档未规定插入顺序的确定性规则（如按 resource type 字母序、按 ResourceRegistry canonical order 等）。

**影响**: 如果不同代码路径（normal spawn、Rhai mod、NPC 掉落）以不同顺序向同一 entity 的 IndexMap 插入条目，同一 tick 在不同 replay 中可能产生不同迭代顺序 → `state_checksum` 不一致 → replay 验证失败。

**修复建议**: 二选一：
- A) 将 IndexMap 替换为 `BTreeMap`（天然按 key 排序，零运行时心智负担）
- B) 在 `engine.md` §3.1 中显式规定："所有 IndexMap 的插入顺序必须按 key 的字节序（lexicographic）排序后插入，或按 ResourceRegistry canonical order。CI 中增加 spot-check：对随机 entity 验证其 IndexMap 迭代顺序与 canonical order 一致"

**倾向**: 方案 A 更彻底——BTreeMap 从根本上消除插入顺序依赖，不需要开发者记住"必须先排序再插入"的潜规则。

---

### H2: canonical_json() 数值序列化与 command_hash tiebreaker 的版本稳定性（High）

**文件**: `specs/core/02-command-validation.md` §2.1 (行 99-100); `specs/reference/api-registry.md` §0 (行 22-34)

**描述**: command 全局排序键的第 5 层 tiebreaker 是 `command_hash = Blake3(canonical_json(command))`。`canonical_json()` 规则为"键排序、无空格、数值无尾零、字符串 NFC 归一化"。但**未规定整数数值的序列化边界行为**：u64 值超过 2^53 时，若 JSON 序列化库内部使用 f64 中间表示，会产生精度丢失 → 不同 JSON 库产生不同字符串 → 不同 hash → 不同排序。

文档中 api-registry.md §0 已将所有 f64 替换为定点整数类型，但 canonical_json() 并未显式声明"JSON 数值必须使用任意精度整数序列化（不得经过 IEEE 754 中间表示）"。

**影响**: 
- Rust `serde_json` 默认使用 `arbitrary_precision` feature 正确处理大整数；Go `encoding/json` 默认将数字解析为 `float64` → 跨语言 replay 验证时 command_hash 可能不一致
- 同一 engine 内（全 Rust）当前无问题，但已声明的 CI 双实现验证（Rust + Go canonical_codec）可能失败

**修复建议**: 在 `02-command-validation.md` §2.1 的 `canonical_json()` 规则中增加：
> **数值序列化**：所有整数使用任意精度十进制表示，不经过 IEEE 754 中间表示。u64 值 18446744073709551615 必须序列化为 `18446744073709551615`，不得序列化为 `1.8446744073709552e19` 或精度丢失形式。

并在 `api-registry.md` §5.6 的 `canonical_codec_version` CI 校验中增加显式的大整数 fixture 测试。

---

### M1: Room-Partition 全局原子语义在高房间数下的 tick abandon 概率（Medium）

**文件**: `specs/core/01-tick-protocol.md` §3.5.3–3.5.5 (行 413-462)

**描述**: Room-partition 模型规定任何单房间 FDB 写入失败 → 整个 tick 放弃 + 全局回滚。生产环境（500+ players, 200 rooms）下，若单房间 FDB 事务失败率为 p（如 0.1%），全局 tick abandon 概率 ≈ `1 - (1 - p)^R`。当 R = 200 rooms 且 p = 0.001 时，abandon 概率 ≈ 18%。连续 3 次 abandon 触发 degraded mode（§6.2）。

**影响**: 中等。设计已正确声明"不存在部分房间已提交的中间态"，保证了确定性。但未分析高房间数下的**可用性影响**——频繁 tick abandon 可能导致 degraded mode 频繁触发，影响玩家体验。这非正确性问题，是运维可行性问题。

**修复建议**: 在 `engine.md` §3.4.2 或 `01-tick-protocol.md` §3.5 中增加以下分析（不改变语义，仅记录预期）：
> **Room-Partition 可用性模型**：假设单房间 FDB 事务冲突率 p（target < 0.1%），N 个活跃房间下 tick abandon 概率 = `1 - (1-p)^N`。运维应监控 `tick_abandon_rate` 并按需调整 FDB 集群容量。p 的上限由 `05-persistence-contract.md` §8.3 Synthetic Benchmark 的 `per-room conflict rate < 1%` gate 验证。

---

### M2: S22 status_advance_system 实体迭代的 StableEntityId 排序开销（Medium）

**文件**: `specs/core/06-phase2b-system-manifest.md` §3.2 (行 383-384)

**描述**: S22 迭代实体顺序为 `sorted(entities_with_active_status, StableEntityId)`。即每 tick 需要**收集所有携带 StatusState 的实体 → 按 StableEntityId 排序 → 依次推进**。在 5000 活跃 drone 且特殊攻击普及率高的场景下，可能有数百至数千个实体携带 StatusState，排序开销需纳入 EXECUTE budget（≤400ms）。

**影响**: 中等。排序操作本身是确定性的（按 StableEntityId），但 O(N log N) 的开销在 N 较大时可能挤压其他 Phase 2b 系统的 budget。当前 p99 < 100ms 的 command apply benchmark 未单独覆盖 status_advance 排序开销。

**修复建议**: 在 `05-persistence-contract.md` §8.3 Synthetic Benchmark 中增加一条：
> | Status advance sort | 5000 entities with active StatusState | p99 < 5ms |

或设计优化：维护一个 per-tick 的 `ActiveStatusEntities` 有序集合（如 BTreeSet），避免每 tick 重新收集+排序。StableEntityId 单调递增的特性使得新实体的插入为 O(log N)，无需全量重排。

---

### M3: Pathfinding cache_miss_penalty 固定 2000 fuel 的合理性（Medium）

**文件**: `specs/core/04-wasm-sandbox.md` §8 (行 355)

**描述**: `host_path_find` 的 cache_miss_penalty 固定为 2000 fuel，"与硬件无关，保证跨节点确定性结算"。但没有说明 2000 fuel 对应多少实际 CPU 工作量，也没有说明这个固定值是否足以覆盖实际 cache miss 的计算成本。

**影响**: 低-中。固定 penalty 保证了确定性，但若 2000 fuel 远低于实际计算成本，玩家可能通过触发 cache miss 获得廉价寻路（fuel 计量不足）；若远高于实际成本，则不公平地惩罚 cache miss。设计已明确固定值用于确定性，但未给出选择依据。

**修复建议**: 在注释中补充 2000 fuel 的来源：
> `cache_miss_penalty = 2000 fuel` 基于 A* 在 50×50 网格上平均展开 20 nodes × 100 fuel/node 的保守估算（含 hash 查找开销）。实际值在 benchmark gate 中校准并硬编码，不依赖运行时测量。

---

### L1: WASM Store 每 tick 线性内存清零的带宽开销（Low）

**文件**: `specs/core/04-wasm-sandbox.md` §1 (行 41)

**描述**: Worker pool 模型下每 tick 需要"重置 Wasmtime Store（清空线性内存、重置 fuel counter、重建 Instance）"。WASM 线性内存上限 64MB。若每次清零都写入 64MB 零字节，500 players × 64MB = 32GB/tick 的内存带宽。但实际实现可使用 Wasmtime 的 `Store::reset()` 或 memory growth tracking 只清零已使用页面。

**影响**: 低。这是实现优化问题而非设计缺陷。Wasmtime 的 Store 重置通常不涉及全量内存清零（使用 CoW 页面映射或仅重置已分配页面）。

**修复建议**: 在 `04-wasm-sandbox.md` §1 的 Store reset 描述中补充：
> **注意**: Store reset 不要求全量线性内存清零——仅清零 WASM 页面分配表和 fuel counter。内存页面回收由 Wasmtime 内部 CoW/MMU 机制处理。实际内存带宽开销远低于 64MB×N。

---

### L2: Deploy 状态机 ACTIVATION_PENDING 的 30s 等待超时与 tick 周期不协调（Low）

**文件**: `specs/core/05-persistence-contract.md` §2.3 (行 103-105)

**描述**: activation_tick 到达时若 upload_status == "pending"，等待最多 30s。但 tick interval 为 3s。30s = 10 ticks。如果 blob 上传需要 15s，drone 将丢失 5 ticks 的执行窗口（等待 30s 后才判定 FAILED）。文档并未说明是否在每个 tick 都检查 upload_status（即 "30s" 是相对于 activation_tick 的最大等待时间，还是在每个 tick boundary 检查时最多等待 30s）。

**影响**: 低。这更像是歧义性而非缺陷——实际实现中显然应该是"每 tick 检查一次，累计等待 ≤ 30s"，但文档表述可能导致实现错误（如在 activation_tick 阻塞 30s）。

**修复建议**: 将行 103 改为：
> `upload_status == "pending" (blob 仍在传输) → 每 tick boundary 检查一次，累计等待最多 30s (10 ticks)；仍 pending → 视为 FAILED`

---

## 3. 亮点

1. **f64 彻底消除** (api-registry.md §0): Fixed-Point Type Registry 完整覆盖所有浮点场景 —— ResourceRate_i64、ProgressBps_i64、BasisPoints、EfficiencyBps、ConfidenceBps、milli_distance、micro_cost、MilliUnits。所有经济公式使用 floor 舍入和 basis points 精度。这是确定性设计中最容易遗漏的点，R32 处理得非常彻底。

2. **Blake3 单原语设计** (tech-choices.md §8): 哈希 + PRNG 统一为 Blake3（含 XOF 模式）。依赖栈减少一个 ChaCha crate，审计面减半，无平台退化（~6 GB/s 纯软件）。`host_get_random` 使用 `(tick_seed, player_id, drone_id, sequence)` domain separation 确保独立随机流——这在多实体并发 PRNG 场景中非常关键。

3. **Phase 2b 并行安全证明** (06-phase2b-system-manifest.md §4): R/W 矩阵覆盖全部 31 systems，并行集按 target_id / typed buffer 类型 partition，S22 为唯一 StatusState writer。RoomCap 中间态区间明确的读写保护（S07→S08 之间禁止读取）。CI 静态验证 unique writer contract——这在 ECS 调度中极少见如此完整的并发正确性证明。

4. **Seeded shuffle 的 bias 消除** (01-tick-protocol.md §3.1): Fisher-Yates shuffle 使用 rejection sampling 消除模偏差（`XOF.read_u64() % (N - i)` 在 `N - i` 不整除 2^64 时丢弃超出范围的采样值）。这是 PRNG shuffle 中最容易被忽视的正确性细节。

5. **Replay-Critical Subset 显式声明** (05-persistence-contract.md §2): TickCommitRecord 的 10 个必填字段清单，与 RichTraceBlob 的降级行为分离——FDB 失败 = tick abandon，对象存储失败 = audit_gap（不触发回滚）。`collect_id` / `attempt_id` / `commit_id` 三标识体系支持 FDB 重试而不破坏 replay 完整性。

6. **Seed 泄露分层防护** (01-tick-protocol.md §3.1): Arena commit-reveal（赛中不可见 + 赛后自动审计）+ World operator seed-bump + statistical detection。正确承认了"确定性系统中真正的前向保密不可能"这一根本约束，并在约束内做到了最大限度的防护。

---

## 4. CrossCheck — 需要跨方向检查

以下问题在我的方向（Determinism & Performance）范围内已识别出风险，但根因或全面评估需要其他方向的专业视角：

- **CX-1: IndexMap 迭代顺序 → 建议 Data Model 方向检查** Resource/Source 实体的 IndexMap 在序列化、快照构建、ECS query 中的使用是否全部依赖迭代顺序。H1 建议替换 BTreeMap——需 Data Model reviewer 评估所有 IndexMap 使用点的兼容性。

- **CX-2: canonical_json() 跨语言数值序列化 → 建议 Codec/Serialization 方向检查** canonical_codec_version CI 验证 (api-registry.md §5.6) 中的 Rust + Go 双实现 fixture 是否已包含 u64 边界值（0, 2^53-1, 2^53, 2^64-1）的 round-trip 测试。H2 中建议的"任意精度整数"约束需 Codec reviewer 确认可行性。

- **CX-3: Room-partition tick abandon 概率 → 建议 Infrastructure 方向检查** M1 中 200 rooms + 0.1% per-room failure → ~18% abandon 概率是否在 FDB 生产集群实测中成立。需 Infrastructure reviewer 评估 FDB 集群在 Swarm 的 key layout 下 per-room 事务的实际冲突率。

- **CX-4: S22 status_advance 排序开销 → 建议 Systems/ECS 方向检查** M2 中建议的 BTreeSet 优化是否与 Bevy ECS 的 component storage 模型兼容。需 Systems reviewer 评估在 Bevy 中维护跨 system 的有序集合的可行性和正确性（特别是 entity despawn 时的清理）。

- **CX-5: WASM SIMD deterministic subset → 建议 Sandbox 方向检查** engine.md §3.4.3 标记 SIMD deterministic subset 为 "deferred — non-blocking"。需 Sandbox reviewer 确认 Cranelift 在不同架构 (x86_64 vs ARM64) 上对 WASM SIMD 指令的代码生成是否已保证确定性（即使默认禁用，未来启用时需提前验证）。

- **CX-6: FDB commit retry 中 COLLECT 缓存复用 → 建议 Tick Protocol 方向检查** 01-tick-protocol.md §7 规定 commit retry 时复用 COLLECT buffer（不重跑 WASM）。需 Tick Protocol reviewer 确认：spawn_validator 的 body_cost 在 Phase 2a inline apply 时已扣除，若 FDB commit 失败 3 次并最终 abandon，已扣 fuel 和 body_cost 的退还路径是否完整覆盖（包括跨资源池退还的原子性）。