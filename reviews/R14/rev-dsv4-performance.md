# R14 性能评审报告 (DSV4)

**评审员**: `rev-dsv4-performance` | **日期**: 2026-06-18 | **阶段**: Phase 1 Clean-Slate

---

## 1. Verdict: CONDITIONAL_APPROVE

设计整体在性能方面展现了良好的工程判断——fuel metering、两阶段快照、FDB 重试缓存、种子洗牌等机制都是正确的性能基础。但存在 **2 个 Critical 级别矛盾** 和 **3 个 High 级别扩展性风险** 需要架构师介入解决后才能进入实现阶段。

---

## 2. 发现的问题

### Critical

#### D1: Sandbox 生命周期矛盾 [跨文档不一致]

**源文档**: `design/engine.md` §3.4.3 vs `specs/core/04-wasm-sandbox.md` §1

engine.md 描述的是 **long-lived worker pool + per-tick clean Store/Instance reset**（预编译模块池复用，每 tick 重置 WASM 状态）。但 wasm-sandbox.md 的架构图明确标注 **"每 tick fork → 执行 → kill"**（tick 之间无状态保留）。

这是两种截然不同的性能模型：

| 模型 | 每 tick 开销 | 内存占用 | 适用场景 |
|------|------------|---------|---------|
| Worker pool + Store reset | ~微秒级（Store 重建） | 池大小 × 128MB | 高吞吐，适合 500+ 玩家 |
| Fork-per-player | ~毫秒级（fork + seccomp + cgroup + 命名空间初始化） | 瞬时峰值 = 玩家数 × 128MB | 隔离性最强，但延迟不可接受 |

**性能影响**：若实际采用 fork-per-player 模型，以 500 玩家计算，fork 开销保守估计 5-10ms/player，仅进程创建就需要 2.5-5s——直接超出整个 tick 的 3s 预算，还不算 WASM 执行时间。

**建议**: 统一到 worker pool 模型。fork-per-player 的隔离性优势可通过 worker 级别 OS 隔离（seccomp + cgroup + namespace per worker）实现，无需每 tick 重新 fork。

---

#### D2: 单 FDB 事务串行化瓶颈

**源文档**: `specs/core/01-tick-protocol.md` §3.5

Phase 2a 采用**串行 inline 应用**模型：对每条指令逐条校验、逐条应用，所有变更包裹在单个 FDB 事务中。容量指标给出 hard cap 1000 players × 1000 commands/player = 潜在 1,000,000 条指令/tick。

**瓶颈分析**：
- FDB 单事务上限约为 10MB 写入（官方建议 <10MB/txn）
- 1M 条指令的变更记录 + TickTrace + rejection log 可能轻松超过此限制
- 串行 inline 验证意味着指令处理是 O(total_commands)，无法利用多核

**建议**：
- 增加 FDB 事务大小的硬上限（如 5MB），超限时 tick 降级
- Phase 2a 内对无冲突的指令（不同房间/不同 entity）可做批处理——将全局串行改为房间级串行，房间间并行
- 在容量合同中补充 FDB 事务大小的推导公式

---

### High

#### D3: Bevy World 深拷贝内存压力

**源文档**: `specs/core/01-tick-protocol.md` §3.5, `design/engine.md` §3.4.2

每 tick Phase 2a 开始前需要 `world.snapshot()` 做**完整深拷贝**以便 FDB 回滚。Hard cap 50,000 entities × 各组件数据。以平均 entity 含 8 个 component，每个 component 平均 64 bytes 估算，快照体积约为 `50,000 × 8 × 64 = 25.6MB`，再加上 Resource 类型数据，保守估计 30-40MB。

在 3s tick 窗口内，30-40MB 的深拷贝（分配 + memcpy）本身可能花费 10-20ms（取决于内存带宽），这虽然还在 SNAPSHOT build 预算 50ms 内，但如果是 50,000 entity 峰值，拷贝开销会显著挤占 EXECUTE 预算。

**建议**：考虑 copy-on-write 或差分快照方案——仅记录被修改的 component，回滚时恢复差分而非全量恢复。Bevy 的 change detection 机制可辅助此优化。

---

#### D4: 1000 并发 Sandbox Worker 的内存可行性

**源文档**: `design/engine.md` §3.4.2

容量合同 hard cap 1000 active players，sandbox worker pool 按 `max(min_pool, active_players)` 伸缩。每个 worker：128MB cgroup 上限 + Wasmtime runtime overhead ~20MB = ~150MB。1000 并发 worker 需要 **~150GB RAM**。这远超单节点可行范围。

即使 target 500 players 也需要 ~75GB，对单节点而言偏高（但可行）。

**建议**：
- 容量合同中明确单节点硬件基线（如 128GB RAM 支撑 500 players）
- Worker pool 应支持 oversubscription 模式：当物理内存不足时，worker 数 < player 数，分批次串行执行
- 将「active players」与「concurrent sandbox workers」解耦——COLLECT 阶段可分多轮执行

---

#### D5: 快照可见性过滤的 CPU 成本

**源文档**: `design/engine.md` §3.2, `specs/core/01-tick-protocol.md` §2.3

两阶段快照模型（build once, filter per player）将复杂度从 `O(P × E)` 降为 `O(E + P × visible_entities)`。但 500 players × 平均 2000 visible entities = **1,000,000 次可见性判断/tick**。

每次判断涉及：distance check + fog_of_war 查询 + ownership check + room boundary check。按每次判断 200ns 估算，总计 200ms——占 SNAPSHOT + COLLECT 预算的显著比例。

**建议**：预计算每个房间的可见性矩阵（room × player），按房间粒度过滤后仅对边界实体做精确判断。99% 的实体可通过 room 级判断快速通过。

---

### Medium

#### D6: Delta 链完整性缺乏保护

**源文档**: `design/engine.md` §3.2

回放数据模型为 「每 K=100 tick 写入一次 keyframe，其余 tick 写入 delta」。这意味着回放 tick N 需要从最近 keyframe 开始链式应用最多 99 个 delta。若链中任一个 delta 损坏，所有后续 tick 不可回放。

**建议**：delta 链应构建为 hash chain——每个 delta 包含 `prev_delta_hash`，keyframe 包含 `chain_root_hash`。损坏检测从 O(N) 扫描降为 O(1) 验证。

---

#### D7: `host_path_find` 成本可变性

**源文档**: `specs/core/04-wasm-sandbox.md` §8

path_find 成本公式为 `500 × explored_nodes + 200 × expanded_edges`，上限为 `10 calls + 100,000 explored_nodes/tick`。

在最坏情况下（恶意玩家构造无解迷宫路径），100,000 explored_nodes × 500 = 50,000,000 fuel 的**引擎侧计算**——远超 WASM 自身的 10M fuel 预算。此非对称性是 DoS 向量：WASM 消耗 500 fuel（调用 host function），引擎消耗 50M fuel（执行寻路）。

**建议**：
- path_find 的 engine-side cost 应从调用方 WASM fuel budget 中扣除（计为 host function cost，而非仅函数调用本身）
- 或为引擎侧 path_find 设置独立 CPU 预算（如 50ms/tick total），超时返回空路径

---

#### D8: Phase 2b 并行性声明缺乏完整验证矩阵

**源文档**: `specs/core/01-tick-protocol.md` §3.4

Component 读写矩阵仅覆盖 6 个系统（death_mark → spawn → combat → regeneration → decay → death_cleanup），但 ECS 链实际包含 **20 个系统**。声称 regeneration 和 decay "与主线无数据竞争" 是可信的，但其余 14 个系统（如 `rhai_rule_module_tick_start_system`、`controller_system`、`room_state_system` 等）的并行安全性未经矩阵验证。

**建议**：补齐完整 20 系统的 Component 读写矩阵，或明确声明只有 regeneration + decay 可并行，其余全部串行。

---

### Low

#### D9: BROADCAST 阶段无延迟预算

**源文档**: `design/engine.md` §3.4.1

BROADCAST 预算设定为 ≤50ms (p99)，但未拆解为子步骤（delta 计算 + Dragonfly 写入 + NATS 发布）。500 players 的 delta 可能包含数千个变更实体，delta 计算 + 序列化本身可能接近 50ms。

**建议**：将 BROADCAST 预算拆分为 delta compute ≤15ms + Dragonfly ≤15ms + NATS publish ≤20ms，并在 CI 中独立回归。

---

#### D10: Controller 维修公式的 `global_cap` 计算

**源文档**: `design/engine.md` §3.4.5

维修 global_cap 公式 `floor(active_drones × 0.5)` 在 10,000 drones 时为 5,000。但 `repair_capacity` 在 RCL 8 时仅为 80/tick。全局 cap 在此场景下实际上由 repair_capacity 约束（80 << 5,000），global_cap 只在极端场景生效。

这不是性能问题本身，但 global_cap 的计算（需要遍历所有 active drones 计数）在 10,000 drones 时需 O(drones) 扫描——应在已有的 drone 计数缓存中维护，避免每 tick 重算。

---

## 3. 亮点

### S1: Fuel Metering 抽象

WASM 指令级 fuel metering 是设计的性能基石。它实现了：
- **语言无关公平**：C 玩家和 Python 玩家在相同 fuel 预算下获得同等算力
- **确定性**：相同输入 + 相同 fuel limit = 相同输出（超时输出确定性地丢弃）
- **反 DoS**：死循环在 fuel 耗尽时精确终止，不影响其他玩家

与 Screeps 的墙钟 CPU 限制相比，这是一个阶跃性改进。

---

### S2: 两阶段快照 + 按房间分片

`O(entities + players × visible_rooms)` 而非 naive `O(players × entities)` 是正确的复杂度选择。按房间分片使得快照构建可以在 room 级别并行，且在大多数场景下（玩家 drone 集中于少数房间）可见房间数 << 总房间数。

---

### S3: FDB 重试 + COLLECT 缓存复用

FDB commit 失败时不重新执行 WASM 是一个关键的工程决策。它解决了「为原子性重试而重复扣费」的公平性问题，同时避免了重试时 WASM 产出的不确定性（不同执行可能产生不同指令序列）。

**注意**：这个决策依赖于「WASM 执行是确定性的」这一前提，需要 CI 中的确定性回归测试来验证。

---

### S4: Snapshot Truncation 分桶策略

当 snapshot 超过 256KB 时，按 priority bucket + stable entity_id order 截断是正确的 overload 处理方式。关键桶（Spawn/Controller/depot）无条件保留保证核心玩法不受截断影响。

---

### S5: 种子洗牌的确定性公平

`Blake3(tick || world_seed)` 驱动的 seeded shuffle 同时满足：
- **确定性**：回放可得相同顺序
- **公平性**：每 tick 玩家顺序随机
- **不可预测**：玩家无法提前知道自己在当前 tick 的位置（在 seed 未泄露的前提下）

---

### S6: 失败语义矩阵完整

`specs/core/01-tick-protocol.md` §6.1 的失败模式矩阵覆盖了 13 种失败场景，每种都定义了影响面、玩家影响和恢复策略。这种穷尽式的失效分析在游戏引擎设计中少见，是高质量工程的标志。

---

## 4. CrossCheck — 需要跨方向检查

以下问题从性能视角出发，但根因或解决方案超出纯性能方向范围：

- **CX1**: Sandbox 生命周期模型不一致（D1）究竟哪份文档是权威源？→ 建议 **Architect** 检查 `design/engine.md` §3.4.3 和 `specs/core/04-wasm-sandbox.md` §1，统一为 worker pool 模型并删除 fork-per-tick 引用

- **CX2**: `wasm_simd(true)` 配置下，SIMD 指令的 fuel 消耗与其实际工作量之间的关系未经校准。一条 `v128.add` 完成 4 路加法，但 fuel 消耗可能是 1 条指令。是否存在 SIMD fuel 套利？→ 建议 **Security Reviewer** 检查 WASM fuel metering 对 SIMD 指令的计费公平性

- **CX3**: world_seed 前向推导特性（§3.1 种子洗牌）——知道当前 seed 可计算所有未来 seed。虽然设计文档接受此风险，但从性能攻击角度：攻击者预知排序位置后可以最优调度 drone 动作（如抢在对手前面采集/攻击）。→ 建议 **Security Reviewer** 评估 seed 泄露的攻击面和影响范围

- **CX4**: 水平分片（多 Engine 实例）的时程未定义。单节点 hard cap 1000 players 在 MMO 场景下是早期门槛。→ 建议 **Architect** 明确水平分片的触发条件（如 >800 players 持续 1h）和分片间的延迟模型

- **CX5**: WASM 静态分析中扫描「可疑系统调用模式」的成本未量化。5MB WASM 模块的静态分析在部署时完成，但 500+ 玩家同时部署时可能造成编译队列拥塞。→ 建议 **Security Reviewer** 确认 WASM 验证（wasmparser + 编译）的延迟预算

---

## 5. 扩展性上限估算

| 维度 | 当前设计上限 | 瓶颈 | 突破路径 |
|------|------------|------|---------|
| Active players | ~500（单节点 128GB RAM） | Sandbox worker 内存 | Worker oversubscription / 水平分片 |
| Total entities | 50,000 | Bevy World 深拷贝 30-40MB + 可见性过滤 1M 次/tick | COW 快照 / Room 级增量过滤 |
| Commands/tick | ~50,000（FDB 事务 5MB 限制） | FDB 单事务上限 | 房间级批处理 / FDB 事务拆分 |
| Tick interval | 3s（可满足 500 players） | COLLECT 阶段 WASM 执行 | Worker pool 扩容 / 分批 COLLECT |
| Cross-room replay | 99 delta chain max | Delta 损坏影响面 | Hash chain 完整性保护 |

---

## 6. 延迟预算验证

对照 `design/engine.md` §3.4.1 的预算分配，基于 500 active players 场景验证：

| 阶段 | 预算 | 估算消耗 | 状态 |
|------|------|---------|:--:|
| SNAPSHOT build | ≤50ms | ~15ms（50K entity 序列化） + ~10ms（房间分片） = ~25ms | ✅ |
| COLLECT (sandbox dispatch) | ≤2500ms | ~2000ms（500 players × 4ms avg WASM exec）+ ~100ms（可见性过滤）= ~2100ms | ⚠️ 边际 |
| EXECUTE (2a+2b) | ≤400ms | ~150ms（50K cmd 串行 inline）+ ~100ms（20 ECS systems）= ~250ms | ✅ |
| FDB COMMIT | ≤50ms | ~20ms（小事务 head 推进） | ✅ |
| BROADCAST | ≤50ms | ~10ms（delta）+ ~10ms（Dragonfly）+ ~10ms（NATS）= ~30ms | ✅ |

**关键风险**：COLLECT 在 500 players 时接近 2500ms 预算上限。若平均 WASM 执行时间从 4ms 升至 5ms（如玩家使用更复杂的寻路），就会超出预算。当前设计在 500 players 下是**饱和的**——没有余量应对增长或慢玩家。

---

## 7. 并发安全评审

### 7.1 FDB 事务边界

- ✅ 事务粒度正确：整个 tick 的 EXECUTE 为一个原子事务
- ✅ 重试不重新执行 WASM（COLLECT 缓存复用）——避免不确定性和双重扣费
- ⚠️ 事务内串行执行所有命令——缺乏房间级并发优化（见 D2）

### 7.2 ECS 系统间并行

- ✅ 主线 20 系统 `.chain()` 保证确定性
- ✅ regeneration + decay 数据独立，可安全并行
- ⚠️ 仅 6/20 系统有读写矩阵验证，其余 14 个系统的并行安全性未经正式证明（见 D8）

### 7.3 Sandbox Worker 并发

- ✅ 独立进程 + seccomp + cgroup 提供强隔离
- ✅ 无共享状态，worker 间零竞争
- ⚠️ Unix socket 上 gRPC 通信的序列化/反序列化开销未纳入预算
- ❌ 生命周期矛盾未解决（见 D1）

---

## 8. 峰值负载退化行为

按 hard cap 1000 active players / 10,000 drones 评估退化路径：

| 触发条件 | 退化行为 | 设计是否覆盖 |
|---------|---------|:--:|
| COLLECT 超时 (>2500ms) | 跳过未完成玩家，0 指令 | ✅ |
| 连续 3 tick 超时 | 引擎降级，暂停新玩家加入 | ✅ |
| Snapshot >256KB | 分桶截断，保留关键实体 | ✅ |
| WASM OOM/crash | 该玩家 0 指令，不影响他人 | ✅ |
| FDB commit 冲突 | 重试 3 次，复用 COLLECT 缓存 | ✅ |
| 1000 sandbox workers | 内存压力，无自动降级 | ❌ |
| Tick 接近 3s 目标 | 仅有告警，无主动降级 | ⚠️ |

**缺失的退化路径**：
- 当 sandbox worker pool 内存占用超过物理 RAM 80% 时，应自动缩小 pool 并分批执行 COLLECT
- 当 tick_duration_p99 连续 5 tick >2800ms 时，应主动降低非关键 ECS system 的频率（如减少 NPC AI 更新）

---

## 9. 总结

该设计在性能方面展现了良好的工程素养：正确的算法复杂度选择（两阶段快照）、强大的容错设计（失败语义矩阵）、以及精心考虑的公平性机制（fuel metering + 种子洗牌）。

两个 Critical 问题（sandbox 生命周期矛盾 + FDB 串行瓶颈）需要在进入实现阶段前解决。三个 High 问题（内存可行性、深拷贝开销、可见性过滤成本）不影响设计正确性但影响扩展性上限。

**CONDITIONAL_APPROVE** — 条件为解决 D1（生命周期矛盾）和 D2（FDB 事务瓶颈）后批准。

---

*评审基于以下文档（Phase 1 子集）：*
- `design/README.md`
- `design/engine.md`
- `design/tech-choices.md`
- `specs/core/01-tick-protocol.md`
- `specs/core/04-wasm-sandbox.md`
