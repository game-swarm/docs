# R17 Performance Review — DSV4 Pro

> **Reviewer**: Performance Reviewer (DeepSeek V4 Pro)
> **Date**: 2026-06-18
> **Scope**: R17 Phase 1 Clean-Slate 独立评审。仅读指定 8 份文档，验证权威单源闭合。
> **Principle**: 设计阶段评审，不考虑分阶段实现。

---

## Verdict: CONDITIONAL_APPROVE

R15-R16 多轮修复后，权威单源闭合显著改善。预算模型已从分散定义收敛到 `01-tick-protocol.md §8` 的统一表。发现 **3 个 High** 级别跨文档不一致（worker pool 公式分叉、FDB 事务大小 1000× 差异、TickTrace Envelope 缺少 R16 B3 新增字段），以及 **3 个 Medium** 和 **3 个 Low** 问题。无 Critical 阻断项——所有 High 问题可在不推翻设计的前提下修复。

---

## Findings

### H1 — Worker Pool 公式双向分叉 (High)

**位置**: `engine.md §3.4.3` vs `api-registry.md §5.1` vs `game_api.idl.yaml §5 hardware_baseline`

**证据**:
- `engine.md §3.4.3`: pool 大小按 `max(min_pool, active_players)` 动态伸缩
- `api-registry.md §5.1` + `game_api.idl.yaml`: `worker_pool_size = min(max_pool, active_players)`, `worker_pool_max = 256`

**分析**: 两个公式语义相反——engine.md 保证至少 `min_pool` 但无上界，api-registry 保证最多 `max_pool=256` 但允许低于 `min_pool`。在 500 活跃玩家时：
- engine.md 公式 → pool ≥ 500 workers → 500 × 128MB = **64GB** 仅 sandbox 内存（硬件基线全部 RAM）
- api-registry 公式 → pool ≤ 256 workers → 500 玩家需 ≥2 批次 COLLECT，worst-case 5000ms 超出 hard deadline (4000ms)

**影响**: 直接冲击容量合同 "target 500 active players"。engine 路径消耗全部 RAM 无引擎/FDB 余量；registry 路径在 worst-case 下 COLLECT 超时。

**建议**: 统一为 `min(max_pool, max(min_pool, active_players))`，在权威源 (api-registry.md + YAML) 中同时声明 lower/upper bound，并明确 500-player 场景下 expected batch count。

---

### H2 — FDB 事务大小约束 1000× 不一致 (High)

**位置**: `05-persistence-contract.md §7` vs `01-tick-protocol.md §9.4`

**证据**:
- `05-persistence-contract.md §7`: "单 tick 事务 < 10KB（仅 tick_head + manifest + hash_chain row + small mutations）"
- `01-tick-protocol.md §9.4`: "确保事务大小 < 10MB（FDB 推荐上限）"

**分析**: 10KB vs 10MB 是三个数量级的差异。persistence-contract.md 声称是权威持久化合同，但 10KB 约束极其激进——仅 tick head + manifest + hash chain 的元数据可能就接近此值，再容纳 "small mutations" (entity/resource/controller row updates) 几乎不可能。10MB 是 FDB 实际推荐事务上限，01-tick-protocol 的值更务实。

**影响**: 若实现者以 10KB 为准，需将状态变更拆分到多次 FDB 事务——破坏 tick 原子性保证。若以 10MB 为准，当前 "小事务" 架构承诺落空。

**建议**: persistence-contract.md 是后写的权威合同，应以此为准，但需将其 <10KB 修正为与 FDB 推荐上限一致的实际值（建议 1-5MB，涵盖元数据 + small mutations），并明确 "small mutations" 的规模约束（如最多 N 行 entity update）。

---

### H3 — TickTrace Envelope 缺少 R16 B3 新增 4 字段 (High)

**位置**: `api-registry.md §6` + `game_api.idl.yaml §6` vs `05-persistence-contract.md §6.1` + `engine.md §3.3`

**证据**:
- `05-persistence-contract.md §6.1` (R16 B3 新增): TickTrace 新增 `collect_id`, `attempt_id`, `commit_id`, `terminal_state`
- `engine.md §3.3`: TickInputEnvelope 包含这 4 个字段（标注 "R16 B3 新增"）
- `api-registry.md §6`: TickTrace Envelope 表格 22 字段，**不含**上述 4 个
- `game_api.idl.yaml §6`: `total_fields: 22`，**不含**上述 4 个

**分析**: 权威单源 (api-registry + YAML) 未同步 R16 B3 的 TickTrace 扩展。`total_fields: 22` 应为 26。api-registry.md 声称 "本文档是 Swarm 所有 API 合约的单一权威来源"，但遗漏了已在 engine.md 和 persistence-contract.md 中生效的字段。

**影响**: CI 自动校验会因 YAML 声明 22 fields 而实际 TickTrace 结构包含 26 fields 报不一致错误。回放验证器若以 registry 为准解析 TickTrace 会丢失 commit retry 追踪能力。

**建议**: 更新 `game_api.idl.yaml` 的 `tick_trace_envelope.fields` 增加 4 个字段，`total_fields` 改为 26。同步更新 `api-registry.md §6` 表格。

---

### M1 — api_version 跨文档不一致 (Medium)

**位置**: `api-registry.md §开头` vs `game_api.idl.yaml §开头`

**证据**:
- `api-registry.md`: "当前 API 版本: `0.1.0`"
- `game_api.idl.yaml`: `api_version: "0.2.0"`

**分析**: api-registry.md 明确声明 "机器可读权威源: game_api.idl.yaml。Markdown 表格由此文件生成。冲突时以 YAML 为准。" 但 Markdown 未从 YAML 重新生成，版本号滞后。YAML (0.2.0) 为权威值。

**影响**: 低——YAML 是权威源且冲突规则明确。但 CI 若校验 Markdown 与 YAML 版本一致性会失败。

**建议**: 重新从 YAML 生成 Markdown，或 CI 中加入 api_version 一致性检查。

---

### M2 — Tick p99 预算超出 tick_interval 目标 (Medium)

**位置**: `engine.md §3.4.1` vs `01-tick-protocol.md §8.1`

**证据**:
- `engine.md §3.4.1`: 各阶段 p99 预算 = SNAPSHOT(50) + COLLECT(2500) + EXECUTE(400) + COMMIT(50) + BROADCAST(50) = **3050ms**
- `01-tick-protocol.md §8.1`: `tick_interval_ms = 3000ms` (World 目标值，非硬上限)
- `01-tick-protocol.md §8.1`: `tick_hard_deadline_ms = 4000ms`

**分析**: p99 预算总和 (3050ms) 超出 tick_interval 目标 (3000ms) 约 1.7%。hard deadline (4000ms) 提供安全余量，但在 p99 负载下系统可持续 tick rate 为 3050ms/tick 而非标称 3000ms/tick。COLLECT 的 2500ms 是 per-player deadline 加 dispatch overhead，实际并行执行下 COLLECT 阶段 wall time 通常低于此值——所以实际 p99 更接近目标。

**影响**: 低至中——hard deadline 保底，不会出现 tick 放弃。但标称 3s/tick 在 p99 下轻微偏离。

**建议**: 在预算表中增加 "effective p99 tick interval at 500 players" 估算值，或收紧某阶段预算（如 SNAPSHOT 从 50ms → 30ms）以保持 sum ≤ 3000ms。

---

### M3 — COLLECT per-player deadline = tick_soft_deadline，零 margin (Medium)

**位置**: `01-tick-protocol.md §8.1-8.2`

**证据**:
- `tick_soft_deadline_ms = 2500ms`
- `collect_timeout_ms = 2500ms` (per-player)
- EXECUTE wall-clock 依赖 COLLECT+EXECUTE ≤ soft_deadline

**分析**: 在最坏情况下（单个玩家用满 2500ms），COLLECT 阶段结束后 soft deadline 已耗尽，EXECUTE、COMMIT、BROADCAST 均在 hard deadline (4000ms) 保护下运行。这是设计意图——soft deadline 先截断慢玩家，hard deadline 保底整个 tick。但文档未明确说明 COLLECT 超限玩家如何影响同批次已完成玩家（他们的 EXECUTE 是否等待 soft_deadline 到期？）。

**影响**: 中等——hard deadline 保底，但设计意图需更清晰。

**建议**: 在 01-tick-protocol.md §8.1 中增加 soft deadline 到达时的精确行为：已完成 COLLECT 的玩家是否立即进入 EXECUTE（不等慢玩家），还是等 soft deadline 到期后统一 EXECUTE。

---

### L1 — Worker Pool 内存预算无 headroom (Low)

**位置**: `api-registry.md §5.1` + `04-wasm-sandbox.md §4.2`

**证据**:
- Worker pool max = 256，每 worker cgroup memory.max = 128MB
- 256 × 128MB = **32GB** 仅 sandbox
- Hardware baseline: **64GB RAM, 32 cores**
- 引擎 (Bevy World 50K entities) + FDB + NATS + Dragonfly + OS 共享剩余 32GB

**分析**: 32GB headroom 足够但无显著余量。Bevy World with 50,000 entities 的深拷贝快照（§3.4.1 SNAPSHOT 阶段）本身可能消耗 GB 级内存。若实际 entity 序列化开销高于预期，可能在 500-player 负载下触发 OOM。

**影响**: 低——当前估算足够但接近边界。

**建议**: 在容量合同中增加 per-entity 内存估算，验证 50K entities 深拷贝内存是否 fit 32GB + swap-disabled 约束。

---

### L2 — host_path_find cache_miss_penalty 未量化 (Low)

**位置**: `04-wasm-sandbox.md §8` vs `api-registry.md §4.4`

**证据**:
- `04-wasm-sandbox.md §8`: `host_path_find` cost = `500 × explored_nodes + 200 × expanded_edges + cache_miss_penalty`
- `api-registry.md §4.4`: `host_path_find` cost = `500 × nodes + 200 × edges`（无 cache_miss_penalty）

**分析**: cache miss 的 fuel cost 在 sandbox 文档中提及但未在权威 registry 中量化。实现者无法确定 cache_miss 的 fuel charge 值。

**建议**: 在 api-registry.md §4.4 + game_api.idl.yaml §4 中增加 `cache_miss_penalty` 的具体值。

---

### L3 — deploy cooldown 5 ticks 可能限制 AI agent 迭代 (Low)

**位置**: `game_api.idl.yaml §5 replay.code_update_cooldown`

**证据**: `code_update_cooldown = 5 ticks`（World 最小，15s at 3s/tick）

**分析**: 性能评审角度——此 cooldown 防止部署风暴，合理。但 AI agent 通过 MCP 快速迭代时，15s 等待可能影响体验。非阻断，仅作记录。

---

## Strengths

1. **两阶段快照架构 (engine.md §3.2)** — 一次性世界快照 + 按房间分片 + per-player 拼接，将复杂度从 `O(P×E)` 降为 `O(E + P×visible_rooms)`。消除了 R15 中每玩家独立序列化的核心性能问题。

2. **WASM 预编译 + Hash 缓存 (engine.md §3.2, wasm-sandbox.md §1)** — 部署时预编译、tick 时仅实例化。6-component 缓存键 (module_hash || wasmtime_build_commit || wasmparser_version || validation_policy_version || target_arch || security_epoch) 覆盖所有失效场景。

3. **Deferred Command Model (wasm-sandbox.md §3)** — WASM tick() 仅输出 JSON 指令，所有 mutating 操作经引擎统一校验和应用。干净的审计链 + 确定性回放。

4. **COLLECT 缓存跨 FDB Retry 复用 (01-tick-protocol.md §2.3.1, persistence-contract.md §6)** — FDB commit 失败时不重跑 WASM，不追加扣 fuel。`collect_id` 不变、`attempt_id` 递增的设计使重试可追踪且资源公平。

5. **Per-player fair-share admission (engine.md §3.4.2, api-registry.md §5.2)** — 寻路全局 100K explored nodes/tick 按活跃玩家均分，先到先得消费。防止单玩家垄断引擎资源。

6. **统一预算表 (01-tick-protocol.md §8.2)** — COLLECT/EXECUTE/BROADCAST/COMPILE 四阶段预算收敛到单一表格，覆盖 wall-clock、fuel、memory、host calls。消除了 R15 中跨文档分散定义的风险。

7. **Blake3 单原语覆盖哈希+PRNG (tech-choices.md §8)** — 减少依赖面，~6GB/s 纯软件无平台退化，XOF 模式天然适配 per-player per-tick 确定随机序列。

8. **FDB 双写失败语义清晰 (persistence-contract.md §3)** — 5 种场景矩阵覆盖正常/写入失败/超时/commit 失败/commit 超时，孤儿 blob GC 策略明确。

---

## CrossCheck

### 权威单源闭合验证

| 维度 | 权威源 | 一致性 |
|------|--------|:------:|
| CommandAction (19 variants) | game_api.idl.yaml §1 ↔ api-registry.md §1 | ✅ 一致 |
| RejectionReason (35 variants) | game_api.idl.yaml §2 ↔ api-registry.md §2 | ✅ 一致 |
| MCP Tools (46) | game_api.idl.yaml §3 ↔ api-registry.md §3 | ✅ 一致 |
| Host Functions (5, cost/signature) | game_api.idl.yaml §4 ↔ api-registry.md §4 ↔ wasm-sandbox.md §8 | ⚠️ cache_miss_penalty 未量化 (L2) |
| 容量限制 (25 params) | game_api.idl.yaml §5 ↔ api-registry.md §5 ↔ engine.md §3.4.2 | ⚠️ worker pool 公式分叉 (H1) |
| TickTrace Envelope | game_api.idl.yaml §6 ↔ api-registry.md §6 | ❌ 缺少 4 字段 (H3) |
| Tick 预算 (p99) | engine.md §3.4.1 ↔ 01-tick-protocol.md §8 | ⚠️ sum 超 interval 目标 (M2) |
| FDB 事务大小 | persistence-contract.md §7 ↔ 01-tick-protocol.md §9.4 | ❌ 10KB vs 10MB (H2) |
| api_version | game_api.idl.yaml vs api-registry.md | ⚠️ 0.2.0 vs 0.1.0 (M1) |
| Direction4 | game_api.idl.yaml §7 ↔ api-registry.md §7 | ✅ 一致 |
| Sandbox deadline | engine.md §3.4.1 ↔ wasm-sandbox.md §6 ↔ api-registry.md §5 | ✅ 一致 (2500ms) |
| Pathfinding budget | engine.md §3.4.2 ↔ wasm-sandbox.md §6 ↔ api-registry.md §5 | ✅ 一致 (100K nodes, 10 calls) |
| Snapshot cap | engine.md §3.4.2 ↔ wasm-sandbox.md §6 ↔ api-registry.md §5 | ✅ 一致 (256KB) |
| Tick 失败语义 | 01-tick-protocol.md §6.1 ↔ persistence-contract.md §6 | ✅ 一致 |
| RNG 确定性 | 01-tick-protocol.md §9.5 ↔ tech-choices.md §8 | ✅ 一致 |
| Per-drone action quota | 01-tick-protocol.md §3.3 ↔ engine.md §3.2 | ✅ 一致 (1 main action) |

### R15-R16 问题闭合追踪

| 原问题 | 状态 | 证据 |
|--------|:----:|------|
| R15 C1: COLLECT budget zero-margin | ✅ 已修复 | 01-tick-protocol.md §8.2 统一预算表，hard deadline 4000ms 保底 |
| R15 C2: tick p99 exceeds soft deadline | ⚠️ 部分修复 | hard deadline 从无到有，但 p99 sum 3050ms 仍超 interval 3000ms (M2) |
| R15 C3: FDB single-transaction bottleneck | ✅ 已修复 | persistence-contract.md §2-3 分层持久化：FDB 仅小对象 + pointer |
| R16 C1: worker pool 64GB memory cliff | ⚠️ 未闭合 | H1 发现公式仍分叉，256 cap 有但 engine 文档未引用 |
| R16 H1: per-player deadline budget erosion | ✅ 已修复 | wasm-sandbox.md §6 明确 2500ms deadline + deterministic no-op |
| R16 H2: FDB 10x write amplification | ✅ 已修复 | persistence-contract.md §5.3 keyframe K=100 + delta chain |
| R16 B3: commit retry hash chain gaps | ⚠️ 字段缺失 | collect_id/attempt_id/commit_id 已设计但未进入权威 registry (H3) |

### 延迟预算分解 (end-to-end, 500 players, p99)

```
                    ┌──── SNAPSHOT ────┐  ≤50ms   一次性构建 + 房间分片
                    │                  │
     tick N start ──┤   COLLECT        ├─ ≤2500ms 并行 WASM 执行 (256 workers × 500 players)
                    │   (sandbox dispatch)│          per-player deadline 2500ms
                    │                  │
                    ├──── EXECUTE ─────┤  ≤400ms  Phase 2a inline + Phase 2b ECS
                    │   (2a + 2b)      │          29 systems, serial spine + 3 parallel sets
                    │                  │
                    ├──── COMMIT ──────┤  ≤50ms   FDB atomic (head + manifest + hash + small mutations)
                    │   (FDB)          │          重试最多 3 次 (复用 COLLECT 缓存)
                    │                  │
                    ├─── BROADCAST ────┤  ≤50ms   Delta → NATS → Gateway → WS
                    │                  │          异步，失败不回滚 tick
                    │                  │
     tick N end ────┴──────────────────┘
     
     Total p99: ≤3050ms (target 3000ms, hard deadline 4000ms)
     Bottleneck: COLLECT 阶段 — 占预算 82%。并行度由 worker pool 决定。
```

---

## 总结

R17 文档在权威单源闭合上较 R15-R16 有实质进步。统一预算表 (01-tick-protocol §8)、分层持久化合同 (05-persistence-contract)、两阶段快照架构是三个关键改进。剩余问题集中在跨文档同步摩擦：worker pool 公式、FDB 事务大小、TickTrace Envelope 字段滞后。这些问题不涉及架构推翻，可在下一轮文档修订中修复。

**建议修复优先级**: H3 (TickTrace 字段) → H2 (FDB 事务大小统一) → H1 (worker pool 公式统一) → M1 (api_version) → M2/M3 (预算微调) → L1-L3。
