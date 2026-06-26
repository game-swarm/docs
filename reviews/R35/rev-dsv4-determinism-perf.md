# R35 Determinism & Performance Review — rev-dsv4-determinism-perf

> Reviewer: DeepSeek V4 Pro (rev-dsv4-determinism-perf)
> Date: 2026-06-26
> Reviewed: 9 documents (design/ 3 + specs/ 6)
> Scope: 确定性合同完整性、非确定性源消除、tick pipeline 延迟预算、水平扩展瓶颈

---

## 1. Verdict

**CONDITIONAL_APPROVE**

确定性与性能合同整体扎实、自洽。Blake3 单原语覆盖哈希+PRNG、f64 全面定点化、`std::HashMap` 全项目禁用、canonical JSON (RFC 8785 JCS)、31-system ECS 串行脊柱 + 并行 group、EntityId 单调递增分配器、WASM fuel metering 确定性——这些构成了一个经得起 replay 验证的确定性基础。

发现 1 个 High 问题（容量推导算式与实际 worker pool 配置不一致）、4 个 Medium 问题（IndexMap 动态插入确定性文档缺口、aggregate CPU budget 估算未经验证、EXECUTE budget 语义跨文档措辞差异、COLLECT 超时与 snapshot 构建硬上限的重叠语义）。无 Critical 问题。全部问题可在文档层面修复，不涉及架构重设计。

---

## 2. 发现的问题

### H1: 1000-player 容量推导假设 1000 workers，默认配置仅 256 — engine.md §3.4.2

- **Severity**: High
- **Location**: `design/engine.md` §3.4.2「Hard cap 1000 活跃玩家推导」
- **问题描述**：

  该推导明确使用「假设 1000 workers，p50=5ms」计算并行化因子：
  ```
  1000 players × 5ms avg = 5000ms
  → 依赖并行 worker pool 分摊
  → 假设 1000 workers，p50=5ms，理论 peak = 5000ms
    但并行化为 ~125ms wall-clock（1000 × 5ms / 40 cores）
  ```
  但同一文档 §3.4.2「Worker pool 配置」中明确定义：
  ```
  worker_pool_size = min(worker_pool_max, active_players)
  worker_pool_max = 256（运行期默认）
  ```
  当 `active_players = 1000` 时，`worker_pool_size = min(256, 1000) = 256`——而非推导中假设的 1000。实际并行化因子为 `256/40 = 6.4`，WASM 执行 wall-clock ≈ `1000 × 5ms / 6.4 ≈ 781ms`（而非推导中的 125ms）。

  `api-registry.md` §5.5 确认 `worker_pool_max` 默认 256 且 `worker_pool_hard_cap = 1000`。

- **影响**：容量推导与实际配置不一致。若运维方按推导结论规划 1000-player 部署但不调整 `worker_pool_max`，COLLECT 阶段 wall-clock 将远超推导值。虽然 781ms + 500ms overhead = 1281ms 仍在 2500ms budget 内，但推导本身的数学依据是错误的——不应假设配置值不同于默认值。

- **修复建议**：
  1. **方案 A（推荐）**：重写 1000-player 推导，使用默认 `worker_pool_max = 256`，算出实际 wall-clock ≈ 781ms + 500ms overhead = 1281ms。明确标注「1000-player 部署需运维方调整 `worker_pool_max` 至 ≥ active_players 以保持线性并行度」。
  2. **方案 B**：保留当前算式但显式标注「此推导假设运维方已将 `worker_pool_max` 调整为 1000；默认配置 256 下并行度降低 ~4×」。

### M1: IndexMap 确定性合同未覆盖动态插入场景 — engine.md §3.3 + specs 交叉引用

- **Severity**: Medium
- **Location**: `design/engine.md` §3.3「确定性保证与回放」；`design/engine.md` §3.1（Resource/Source 结构体定义）
- **问题描述**：

  `engine.md` §3.3 声明：
  > `IndexMap` 保留用于有序资源类型等插入顺序确定的场景

  `Resource` 和 `Source` 结构体使用 `IndexMap<String, u32>`。但确定性合同未明确回答：**当 Resource/Source 在运行时被修改（非仅世界初始化时）时，IndexMap 的插入顺序如何保持确定性？**

  具体场景：
  - 服主通过 Rhai mod 动态添加新资源类型到 Source
  - 两个 drone 在同一 tick 内向同一 Storage 存入不同类型资源
  - Transfer 操作写入 `Resource.amounts` 时的新 key 插入

  这些场景中 IndexMap 的插入顺序由 ECS system 调度顺序+实体迭代顺序决定——它们**在本次设计中是确定性的**（31-system 固定串行脊柱 + StableEntityId 排序）。但文档未显式连接这一链条：「IndexMap 动态插入顺序 → 由 ECS 调度顺序+实体迭代顺序保证 → 因此确定性成立」。

- **影响**：当前设计**实际满足确定性**（ECS 调度顺序在任何 replay 中相同），但缺少文档桥接。实现者可能误认为 IndexMap 在任何场景下都「自动」确定，忽略了对 ECS 调度顺序的依赖。非 Blocker——修正为文档补全。

- **修复建议**：在 `engine.md` §3.3 的「确定性数据结构」段落中增加一句：
  > `IndexMap` 的动态插入顺序由 ECS system 调度顺序（见 `06-phase2b-system-manifest.md` §1）和 `StableEntityId` 迭代顺序共同保证——所有可能修改 IndexMap 内容的 system 在固定串行脊柱中运行，实体迭代按 `StableEntityId` 升序，因此插入顺序在任意 replay 中一致。

### M2: Aggregate CPU Admission Formula 依赖未经验证的 PER_CORE_FUEL_RATE — engine.md §3.4.2

- **Severity**: Medium
- **Location**: `design/engine.md` §3.4.2「Aggregate CPU Admission Formula」
- **问题描述**：

  ```
  aggregate_cpu_budget = floor(TICK_BUDGET_COLLECT_MS × CPU_CORES × PER_CORE_FUEL_RATE)
  ```

  其中 `PER_CORE_FUEL_RATE` = "保守估算 ~500M fuel/s per core，对应 wasmtime 默认 fuel 计量"。注释承认这是**估算值**，且文档指出「不同 wasmtime 版本/配置的 fuel 消耗不可直接比较」。

  `effective_per_player_quota` 由此估算直接推导 → 直接影响玩家的实际 fuel 配额。若估算与实际偏差 2×，则玩家实际可消耗的 CPU 指令数与设计意图偏差 2×。

- **影响**：Fuel quota 是核心公平性合同——配额过高则 tick 可能超时，配额过低则浪费 CPU 预算。估算值作为设计占位合理（engine.md 明确「数值是估值插画」），但此值直接决定 admission formula 的数学正确性。当前标记为 Medium 符合「设计文档中估值数值不判为 Blocker」原则，但建议在文档中显式标注为 **benchmark-gated**。

- **修复建议**：在公式下方增加注释：
  > ⚠️ `PER_CORE_FUEL_RATE` 为设计阶段估值。实现阶段必须在目标硬件上 benchmark 测定实际值，纳入 CI 回归。实际值偏差 >20% 时需更新本公式。详见 `persistence-contract.md` §8.3 Synthetic Benchmark Gate。

### M3: EXECUTE budget 语义跨文档措辞不一致 — engine.md vs tick-protocol.md

- **Severity**: Medium
- **Location**: `design/engine.md` §3.4.1 vs `specs/core/01-tick-protocol.md` §8.2
- **问题描述**：

  `engine.md` §3.4.1 表格：
  > | **EXECUTE (2a+2b)** | ≤400ms | ≤50ms | 命令应用 + ECS systems |

  `tick-protocol.md` §8.2 表格：
  > | **EXECUTE** | wall-clock total | `tick_soft_deadline_ms` 内完成 | 软截止前必须完成（EXECUTE 不独立超时，由 COLLECT+EXECUTE 总预算控制，详见 §8.1 `tick_hard_deadline_ms`）。World ≤400ms / Arena ≤50ms 仅为性能目标，非硬超时。 |

  engine.md 用「预算」措辞（暗示硬约束），tick-protocol.md 明确标注「仅为性能目标，非硬超时」。同一数值在两个文档中的语义级别不同——engine.md 未标注「非硬超时」。

- **影响**：实现者若只看 engine.md 可能将 400ms 当作硬超时实现（到 400ms 即中断 EXECUTE 阶段），而正确行为是 EXECUTE 在 COLLECT+EXECUTE 总预算内完成（tick_hard_deadline_ms = 4000ms）。这是一个实现分叉风险。

- **修复建议**：在 `engine.md` §3.4.1 的 EXECUTE 行增加注释：
  > ≤400ms 为性能目标（非硬超时）；硬截止由 `tick_hard_deadline_ms` (4000ms) 统一控制。详见 `tick-protocol.md` §8.1–8.2。

### M4: 256KB snapshot cap 与 2500ms COLLECT 超时的重叠语义未解耦 — engine.md §3.4.4 + tick-protocol.md §2.3

- **Severity**: Medium
- **Location**: `design/engine.md` §3.4.4；`specs/core/01-tick-protocol.md` §2.3、§8.2
- **问题描述**：

  Snapshot 构建有两个独立上限：(a) 256KB size cap（硬性，超限触发 truncation），(b) COLLECT 阶段 2500ms 总超时。这两个约束**独立生效**，但文档未讨论它们之间的交互：

  1. 若 snapshot 因 256KB cap 被截断，截断本身消耗 CPU 时间（sort_and_truncate 操作）——在 1000-player 场景下，1000 次截断操作的总开销是否挤占 COLLECT budget？
  2. 若某玩家 snapshot 过大导致 truncation + 后续 WASM 执行超时，2500ms COLLECT 超时触发时，该玩家的截断 snapshot 是否已正确传递给 WASM？

  当前文档将这两个约束分开叙述但未分析交互。

- **影响**：实际不存在功能缺陷——truncation 在 snapshot build 阶段（COLLECT 早期）完成，WASM 执行在后期。但缺少交互分析可能导致实现者对时序判断错误（如在 COLLECT 超时后才做 truncation）。非 Blocker——建议文档层面补全。

- **修复建议**：在 `tick-protocol.md` §2.3 快照构建时序边界图中增加标注：
  > 步骤 [3] 视野过滤+截断在步骤 [4] WASM tick() 执行**之前**完成。步骤 [3] 的总 CPU 开销（含所有玩家的截断计算）计入 COLLECT budget。若步骤 [3] + [4] 总耗时超过 `collect_timeout_ms`，超时玩家输出丢弃——但步骤 [3] 已为该玩家完成的截断结果（truncated snapshot）不会回退（下一 tick COLLECT 重新构建）。

---

## 3. 亮点

1. **Blake3 单原语全覆盖**（tech-choices.md §8）：哈希 + PRNG (XOF) + 代码签名(Ed25519 独立) —— 依赖栈最简、审计面最小、纯软件 ~6GB/s 无平台退化。`seed+offset XOF` 模式天然适配 per-player per-tick 确定性随机序列。这是教科书级的确定性工程。

2. **f64 全面定点化**（api-registry.md §0 + tick-protocol.md §7.1）：`ResourceRate_i64`（1e6 = 1.0）、`BasisPoints`（0–10000）、`MilliUnits`（1000 = 1 unit）——所有游戏状态数值全部定点整数，JSON 序列化使用整数表示，禁止 IEEE 754。跨平台、跨编译器、跨语言确定性无死角。

3. **31-system ECS Manifest**（06-phase2b-system-manifest.md）：Serial spine + 2 parallel sets，R/W 矩阵逐 system 声明，Unique Writer Contract（S22 是唯一 StatusState writer），Parallel safety 按 target_id partition / typed buffer 隔离证明。CI 静态验证 R/W 冲突 + 并行安全 + 确定性迭代。这是 ECS 确定性调度的工程范本。

4. **Shadow Write + Atomic Publish**（tick-protocol.md §3.5 + persistence-contract.md §8）：Staging 行非 committed 状态 → GlobalTickCommit 是唯一 publish 点 → staging 孤立行 GC < 15s。消除了旧模型「per-room 写入已持久化、全局 abort」的时序窗口。语义干净——不存在部分提交的中间态。

5. **COLLECT 缓存复用机制**（tick-protocol.md §7 + §8.4）：FDB commit 失败重试时复用 canonical COLLECT buffer——不重跑 WASM、不追加 fuel 扣费、`collect_id` 不变。跨重试 fuel ≤ 1×MAX_FUEL。这是 FDB 事务重试与确定性合同的正确结合。

6. **Attack/Heal 与 combat_system 职责分离**（engine.md §3.2 + 06-phase2b-system-manifest §S11-S15）：Phase 2a 只生成 PendingDamage/PendingHeal intent，Phase 2b S15 统一写入 HitPoints。避免了同 tick 内 Attack 顺序差异导致的不同 HP 结果。

7. **Deploy 完整状态机**（persistence-contract.md §2.3）：VALIDATE → UPLOAD_PREPARE → MANIFEST_COMMIT → ACTIVATION_PENDING → ACTIVE/FAILED。FDB manifest 是 deploy 唯一权威记录，blob upload 异步不阻塞 tick。WASM 模块 blob 缺失不影响 deterministic replay（R27 D6 已裁决）。

---

## 4. CrossCheck — 需要跨方向检查

以下问题在我的方向（确定性+性能）内发现疑点，但裁决需要其他方向的权威判断：

- **CX1**: IndexMap 动态插入的确定性依赖 ECS 调度顺序——Resource/Source 的 IndexMap 在 Rhai mod 或 Transfer 操作中被修改时，插入顺序由 ECS system 执行顺序决定。→ 建议 **Security reviewer** 检查：Rhai mod 是否有独立路径绕过 ECS 调度直接修改 IndexMap？若有，则 IndexMap 插入顺序可能非确定。

- **CX2**: WASM SIMD deterministic subset (wasm-sandbox.md §2.2 `config.wasm_simd(world_config.simd_enabled)` + engine.md §3.4.3「SIMD deterministic subset deferred — non-blocking」) —— 当前默认禁用，但 `world_config.simd_enabled = true` 时启用「deterministic integer subset」。→ 建议 **Integration reviewer** 检查：此 deterministic subset 是否跨 ARM/x86 架构验证？若未验证，启用 SIMD 后 replay 跨架构可能破裂。

- **CX3**: FDB shadow write staging GC interval 10s（tick-protocol.md §3.5.3「GC worker 每 10s 扫描」）——在 1000-player 1000-tick 积压下，staging 孤立行最大残留 < 15s 的保证是否成立？→ 建议 **Operations reviewer** 检查：Staging GC 扫描速度是否与 staging 行产生速率匹配（per-tick staging 行数 = active_rooms × 2 keys）。

- **CX4**: 确定性合同 §7.1 声明「禁止 IEEE 754 浮点数」，但 Rhai 模组脚本（tech-choices.md §3）的「可关闭浮点引擎侧」——默认是关闭还是开启？若服主误配置为开启，Rhai 脚本中的浮点运算是否污染游戏状态？→ 建议 **Security reviewer** 检查：Rhai 浮点引擎的 world.toml 配置项是否有生产环境保护（`world.mode != "development"` 时拒绝 `rhai.float_enabled = true`，类似 wasm-sandbox.md §9.3 的 `sandbox.relaxed` 保护）。