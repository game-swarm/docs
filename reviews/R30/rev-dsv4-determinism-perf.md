# R30 Determinism & Performance Review — rev-dsv4-determinism-perf

## 1. Verdict

**CONDITIONAL_APPROVE**

The determinism contract is comprehensive and well-structured: HashMap→IndexMap, f64→fixed-point, time→epoch deadline, PRNG→Blake3 XOF — all four non-deterministic sources are eliminated. The tick pipeline budget is realistic and benchmark-gated. The replay architecture (COLLECT caching + recorded commands + snapshot/restore) is sound. However, there is one high-severity cross-document inconsistency in the ECS R/W matrix that could lead to implementation bugs, and the TickInputEnvelope field list is outdated in engine.md relative to the authoritative api-registry. These are documentation-level issues that should be resolved before implementation, but they do not fundamentally invalidate the design.

---

## 2. 发现的问题

### H1 (High): StatusState R/W Matrix 与 Unique Writer Contract 矛盾

**文件**: `specs/core/06-phase2b-system-manifest.md` §4 (Component R/W Matrix) vs §Special Attack Unique Writer Contract

**描述**: R/W 矩阵显示 S16-S21 (hack/drain/overload/debilitate/disrupt/fortify) 对 `StatusState` 列标记为 `W`（写入），但 Unique Writer Contract 明确声明所有 StatusState 子类型（HackState/DrainState/OverloadState/DebilitateState/DisruptState/FortifyState）的唯一写入者是 S22 (`status_adv`)。

```
R/W Matrix:     S16-S21 StatusState = W, S22 StatusState = W
Writer Contract: HackState → status_adv (S22) only
                 DrainState → status_adv (S22) only
                 ...
```

**影响**: 若实现者以 R/W 矩阵为准，S16-S21 会直接写入 StatusState，破坏 single-writer 合同，导致：(a) 与 S22 的数据竞争（同在 Parallel Set B），(b) 非确定性行为（并行写入顺序不确定），(c) replay 分叉。

**修复建议**: 
- 方案 A（推荐）: 将 R/W 矩阵中 S16-S21 的 StatusState 列改为 `R`（只读），S22 保持 `W`。同时在并行安全证明中增加 "S16-S21 仅读取各自 StatusState 子类型，S22 为唯一写入者" 的明确声明。
- 方案 B: 若 S16-S21 确实需要写入（例如 hack_system 推进 HackState stage），则将它们从 Parallel Set B 中移出，改为串行执行（S16→S17→...→S21→S22），但在 500-player 场景下这会增加 EXECUTE 延迟。

### H2 (High): engine.md TickInputEnvelope 字段列表过期

**文件**: `design/engine.md` §3.3 vs `specs/reference/api-registry.md` §6

**描述**: engine.md §3.3 列出的 TickInputEnvelope 字段（~13 项）与 api-registry.md §6 的权威 22 字段列表不一致。api-registry 新增了 `core_idl_version`, `world_action_manifest_hash`, `validator_version`, `rejection_reason_registry_version`, `system_manifest_hash`, `limits_manifest_hash`, `host_abi_version`, `canonical_codec_version`, `visibility_truncation_version`。

**影响**: engine.md 不是权威源（它声明"详细规范见 specs/core/01-tick-protocol.md"和"权威容量定义以 api-registry 为准"），但 §3.3 的字段列表没有指向 api-registry 的交叉引用。实现者若仅看 engine.md 会遗漏 9 个 replay-critical 字段，导致 TickTrace 不完整、replay 验证失败。

**修复建议**: 将 engine.md §3.3 的字段列表替换为指向 api-registry.md §6 的引用，不再重复列字段。格式参考 engine.md §3.4.2 末尾的 "权威容量定义以 api-registry 为准" 模式。

### M1 (Medium): Cross-document canonical_json NFC 归一化未验证跨语言一致性

**文件**: `specs/core/02-command-validation.md` §2.1

**描述**: `command_hash = Blake3(canonical_json(command))` 的 canonical_json 规则包含"字符串 NFC 归一化"。引擎用 Rust（`unicode-normalization` crate），Gateway 用 Go（`golang.org/x/text/unicode/norm`）。两个实现的 NFC 归一化可能因 Unicode 版本差异产生不同结果，导致同一 command 在 Rust 和 Go 两侧产生不同 hash。

**影响**: 若 Gateway 和 Engine 对同一 JSON 字符串产生不同的 canonical_json → 不同的 command_hash → command_hash tiebreaker 不一致 → replay 时命令排序不同 → state checksum 不匹配。

**修复建议**: 
- 在 TickTrace envelope 中增加 `canonical_codec_version`（已存在，api-registry §6 #21），明确记录 Unicode 版本。
- CI 增加跨语言 canonical_json 一致性测试：Rust 和 Go 对同一输入产生相同 Blake3 hash。
- 或简化 canonical_json 规则：限制字符串仅允许 ASCII 可打印字符 + NFC 预归一化，消除运行时归一化需求。

### M2 (Medium): Room-Partition 2PC 跨房间移动延迟风险

**文件**: `specs/core/05-persistence-contract.md` §8.1

**描述**: Room-Partition 模式下，"Cross-room operations: 2-phase commit（source room → target room）"，2PC 超时 3s。Drone 跨房间移动频繁发生（出口每 tick 可能有多个 drone 穿越）。若每 tick 有 N 次跨房间移动，每次 2PC 的协调开销可能累积。

**影响**: 500-player 场景下，若 20% 的 drone 每 tick 跨房间移动（~1000 次），2PC 协调开销可能导致 FDB commit 阶段超预算（≤50ms p99）。

**修复建议**: 
- 明确 2PC 是 FDB 事务层的实现细节还是应用层协议。若是 FDB 事务层，FoundationDB 的原子提交可能已覆盖跨 key-range 的事务一致性，不需要显式 2PC。
- 增加 cross-room move batching：同 tick 内同一房间对的所有跨房间移动合并为一个 FDB 事务。
- 在 benchmark gate（05-persistence-contract.md §8.3）中增加 "Cross-room move 2PC, 100 concurrent cross-room moves, p99 < 50ms" 测试项。

### M3 (Medium): Sandbox Worker OS 隔离开销未 benchmark

**文件**: `specs/core/04-wasm-sandbox.md` §4, §9; `design/engine.md` §3.4.2

**描述**: 每个 sandbox worker 有独立 cgroup v2 + seccomp BPF + pid/net/mnt/ipc/uts namespace。1000 workers 时，kernel 维护这些隔离结构的开销（cgroup hierarchy traversal, seccomp filter evaluation, namespace structs）未在 benchmark gate 中验证。

**影响**: 1000-worker 场景下，OS 隔离开销可能导致 dispatch overhead 超出预算的 500ms 估算。cgroup v2 的 `cpu.max` 控制器在大量 cgroup 下的层级遍历可能成为瓶颈。

**修复建议**: 在 benchmark gate 中增加 "Sandbox worker spawn + isolate, 1000 workers, p99 < 500ms" 测试项。或采用 cgroup v2 "flat hierarchy" 模式减少遍历开销。

### M4 (Medium): Parallel Set B 的 Bevy 调度器兼容性未验证

**文件**: `specs/core/06-phase2b-system-manifest.md` §1, §S16-S22

**描述**: Parallel Set B 声称 S16-S22 可并行，理由是"各 system 操作互不重叠的 Component 集合"。但 Bevy 的调度器在组件级别检测冲突——若所有 StatusState 子类型注册为同一 Component 类型（如 `StatusState<T>` 泛型），Bevy 可能将它们视为同一组件，拒绝并行化。

**影响**: 若 Bevy 串行化 S16-S22，Phase 2b EXECUTE 时间可能显著增加（每个 status system 串行执行而非并行），在 500-player 大量特殊攻击场景下可能超出 400ms budget。

**修复建议**: 
- 确认 Bevy 的 component access 检测是否支持泛型组件子类型区分（`StatusState<Hack>` vs `StatusState<Drain>`）。
- 若不支持，将各 StatusState 子类型定义为独立 struct（`HackState`, `DrainState` 等而非 `StatusState<Hack>`），确保 Bevy 调度器正确识别并行机会。
- CI 增加 "Bevy schedule graph verification: confirm S16-S22 are parallelized" 检查项。

### M5 (Medium): Snapshot Stitching 在 500-player 下的性能未 gate

**文件**: `design/engine.md` §3.4.1, §3.2（两阶段快照架构）

**描述**: SNAPSHOT budget 为 ≤200ms p95（World 模式）。两阶段架构声称复杂度从 O(P×E) 降为 O(E + P×visible_rooms)。但 500 players × 9 rooms × per-room entity count 的 stitching 操作（序列化 + 过滤 + 截断）的 wall-clock 时间未在 benchmark gate 中独立验证。现有 benchmark gate 只有 "Snapshot stitching, 1000 × 256KB snapshots, p99 < 100ms"，这对应 1000 players 而非 stitching 本身。

**影响**: Snapshot 构建可能成为 500-player 场景的瓶颈，超出 200ms budget。

**修复建议**: 拆分 benchmark: "Room shard serialization, 200 rooms × 250 entities, p99 < 50ms" + "Per-player view stitching, 500 players × 9 rooms, p99 < 150ms"。

### L1 (Low): "Parallel Set C" 标签残留

**文件**: `specs/core/06-phase2b-system-manifest.md` §1 (System Schedule)

**描述**: S24 `decay_system` 仍在 "Parallel Set C: World Maintenance" 标题下，但注释说明 "Parallel Set C 简化为单一 serial system（decay 不与其他系统并行数据竞争已由之前排序保证）"。标签与行为不一致。

**影响**: 低——实际执行是串行的，仅文档标签误导。

**修复建议**: 将 "Parallel Set C: World Maintenance" 改为 "World Maintenance (serial)"，或直接删除 Parallel Set 标签。

### L2 (Low): engine.md §3.1 Resource/Source 结构缺少确定性迭代保证注释

**文件**: `design/engine.md` §3.1

**描述**: `Resource` 和 `Source` struct 使用 `IndexMap<String, u32>`，注释说明 "IndexMap 保证迭代顺序确定"。但 `Drone.body: Vec<BodyPart>` 和 `Structure` 等未显式注释确定性。虽然 `Vec` 本身保持插入顺序，但若从 HashMap 构建再转为 Vec，顺序可能不确定。

**影响**: 低——若实现者不警惕，可能在从 HashMap-derived 数据集构建 Component 时引入非确定顺序。

**修复建议**: 在所有 ECS Component 定义中增加确定性注释，明确迭代/存储顺序保证。

---

## 3. 亮点

1. **单原语覆盖哈希+PRNG (Blake3)**: `design/tech-choices.md` §8 的 Blake3 单原语策略优雅且高效——减少一个 crate 依赖（ChaCha），审计面减半，无平台退化风险。`blake3::Hasher::update_with_seek` 的 XOF offset 模式天然适配 per-player per-tick 确定性随机序列。

2. **两阶段快照架构**: `design/engine.md` §3.2 从 O(P×E) 到 O(E + P×visible_rooms) 的复杂度降低是真正的架构优化，不是常数因子优化。一次性构建 + 按房间分片 + 按需拼接的设计干净利落。

3. **COLLECT 缓存跨重试复用**: `specs/core/01-tick-protocol.md` §3.5（COLLECT 结果跨重试缓存）消除了 FDB commit 失败时的双倍 fuel 扣费和 WASM 非确定性重跑风险。`collect_id` / `attempt_id` / `commit_id` 三标识体系为审计提供了完整的因果链。

4. **定点数类型注册表**: `api-registry.md` §0 的 Fixed-Point Type Registry 将所有 f64 替换为明确量纲的定点整数类型（`ResourceRate_i64`, `ProgressBps_i64`, `BasisPoints`, `MilliUnits` 等），每个类型有明确的底层类型和量纲。这是消除浮点非确定性的正确方式——不是"用整数代替"，而是"用有量纲的定点数代替"。

5. **种子洗牌 (Seeded Shuffle)**: `specs/core/01-tick-protocol.md` §3.1 的 `(priority_class, shuffle_index, source_rank, sequence, command_hash)` 五层排序键设计周全——长期公平性（seed shuffle）、确定性（command_hash tiebreaker）、紧急优先级（Admin priority_class）三者兼顾。Arena commit-reveal + World statistical detection 的差异化种子安全策略体现了对两种模式不同需求的深入理解。

6. **Replay verifier 不依赖 WASM 重执行**: `specs/core/01-tick-protocol.md` §6.3.3 明确"回放时引擎直接执行已记录的指令序列，不重新调用 WASM"。这消除了 Wasmtime 版本升级对 replay 的影响，是实现可持续 replay 的正确架构决策。

7. **Phase 2b 系统调度 Manifest**: `specs/core/06-phase2b-system-manifest.md` 的 29-system 统一清单 + R/W 矩阵 + 并行安全证明 + Manifest hash → TickTrace 的链路为 CI 自动化验证提供了机器可读的确定性合同。这是将"文档声明"转化为"可验证合同"的关键一步。

---

## 4. CrossCheck

以下问题超出 Determinism & Performance 方向范围，建议对应方向检查：

- **CX1**: `canonical_json()` 的 NFC 归一化和 JSON 键排序在 Rust (engine) 和 Go (gateway) 两侧是否产生相同结果？→ 建议 **Security/Auth** 检查 Gateway 侧是否参与 command_hash 计算路径，以及 **API/DX** 检查 canonical_json 规范的跨语言一致性测试计划。

- **CX2**: R/W Matrix（S16-S21 对 StatusState=W）与 Unique Writer Contract（仅 S22 写入）的矛盾需要仲裁——哪个是权威声明？→ 建议 **Architect** 确认并同步两处文档。

- **CX3**: Room-Partition FDB 的 2PC 是否适用于跨房间 drone 移动？若移动频繁，2PC 开销是否可在 ≤50ms p99 FDB commit budget 内完成？→ 建议 **Architect** 审查 cross-room move 的 FDB 事务策略。

- **CX4**: Sandbox worker 的 OS 隔离（独立 cgroup/seccomp/namespace × 1000）在 kernel 层的开销是否已验证？→ 建议 **Security** 检查 OS 加固层是否在目标规模下引入了非预期的延迟 spike。

- **CX5**: Bevy 调度器是否能区分泛型组件子类型（`StatusState<Hack>` vs `StatusState<Drain>`）以实现 Parallel Set B 的并行化？→ 建议 **Architect** 验证 Bevy 的 component access detection 粒度。

- **CX6**: `host_path_find` 的 `cache_miss_penalty = 固定 2000 fuel`（`04-wasm-sandbox.md` §8）——若 penalty 是固定的，跨节点 replay 时是否与首次执行一致？缓存的 `(from, to, terrain_hash, player_visibility_fingerprint)` 键在 replay 时是否完全重现？→ 建议 **Architect** 验证 pathfinding 缓存的确定性 replay 语义。