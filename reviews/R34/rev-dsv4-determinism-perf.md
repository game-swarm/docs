# R34 Closure Verification — Determinism & Performance (DeepSeek V4 Pro)

## Verdict
**PARTIALLY_CLOSED** — 7 of 10 closure items pass verification. 3 P-H items remain unaddressed: P-H1 (EXECUTE budget inconsistency between §1.4 and §8.2), P-H5 (admission hysteresis still asymmetric), P-H6 (no Wasmtime pre-warm strategy). Additionally, a documentation discrepancy between manifest §4 R/W matrix and the Phase 2a intent model is identified.

---

## 逐项 Pass/Fail

### B3: TickCommitRecord + combat deferred — ✅ PASS (with note)

**Verify**: Phase 2a PendingDamage/PendingHeal intent, pre-combat state reads.

| Evidence | Status |
|----------|--------|
| `design/engine.md` §3.2 Phase 2a/2b table: "Phase 2a Attack/RangedAttack/Heal 命令：仅生成 PendingDamage/PendingHeal intent，不直接修改目标 HP" | ✅ |
| `design/engine.md` §3.2: "Phase 2b combat_system (S11-S13)：统一收集 Phase 2a 产生的 PendingDamage/PendingHeal → S14 → S15 damage_application 统一写入 Entity.hits" | ✅ |
| `01-tick-protocol.md` §1.4 阶段二图: "Attack/Heal 生成 PendingDamage/Heal intent 不直接改 HP (R33 B7: pre-combat 状态读取)" | ✅ |
| `06-phase2b-system-manifest.md` S11-S13 Buffer 写入: "S11-S13 不直接修改 Entity.hits。三者各自写入线程局部的 per-system sub-buffer" | ✅ |

**Note — R/W Matrix discrepancy**:
`06-phase2b-system-manifest.md` §4 R/W matrix 对 S01 `cmd_exec` 标记 `HitPoints = W`。但 Phase 2a Attack/Heal 仅生成 intent（不直接改 HP），且 Move/Harvest/Claim 等其他 S01 命令也不涉及 HP 写入。若 S01 确实写 HitPoints（如 body_cost deduction 或结构 damage），则与 S15 的 "UNIQUE HitPoints writer（除 S10 regen 外）" 声明冲突。建议将 S01 的 HitPoints 列改为 `R`（只读，用于校验）或在 S15 中明确列出 exempted HP writers（S01/S03/S08/S10/S22/S24）并说明各 writer 的 domain。

---

### B7: Combat HP writer contract — ✅ PASS (with note)

**Verify**: D2=B deferred reducer, Phase 2a intent only, S15 unique HP writer.

| Evidence | Status |
|----------|--------|
| `06-phase2b-system-manifest.md` §S15: "S15 是 HitPoints 的 UNIQUE 写入者。HitPoints 写入契约: UNIQUE WRITER — S15 是除 S10 regen 外唯一写 Entity.hits 的 system" | ✅ |
| `design/engine.md` §3.2: 明确 Phase 2a intent → Phase 2b S15 unified HP write 的分离 | ✅ |
| `06-phase2b-system-manifest.md` §S11-S13: "S11-S13 不直接修改 Entity.hits" | ✅ |
| `06-phase2b-system-manifest.md` CI 验证 §6: "Unique Writer — 验证仅 S22 写入 StatusState；CI 拒绝任何其他 system 的 StatusState 写操作" | ✅ |
| `06-phase2b-system-manifest.md` §S15: S15 按 `target_id` 升序归并 PendingDamage + PendingHeal → net_damage → 一次性写入 | ✅ |

**Note — Multiple HP writers in R/W matrix**:
§4 R/W matrix 显示 7 个 system 写 HitPoints: S01/S03/S08/S10/S15/S22/S24。S15 的 "UNIQUE writer（除 S10 regen 外）" 声明与矩阵冲突。建议统一：S15 的 unique writer contract 应限定为 "combat damage/heal application 的 unique writer"，而 S01/S03/S08/S22/S24 是 domain-specific HP writes（initialization/decay/status effects）。矩阵 row 不变，但 S15 文本需添加 domain 限定。

---

### D2: Combat deferred reducer (B) — ✅ PASS

**Verify**: engine + tick-protocol + manifest agree on deferred model.

| Evidence | Status |
|----------|--------|
| `design/engine.md` §3.2: Phase 2a intent generation → Phase 2b combat → S14 reducer → S15 unified HP write | ✅ |
| `01-tick-protocol.md` §1.4: Phase 2a PendingDamage/Heal intent → Phase 2b damage_application | ✅ |
| `06-phase2b-system-manifest.md` §S11-S15: PendingDamage/PendingHeal buffer → S14 collect → S14 merge sort → S15 canonical key reduce → atomic HP write | ✅ |
| All three documents consistently describe the deferred reducer pipeline | ✅ |

**三文档一致性**: engine.md、tick-protocol.md、manifest 对 deferred combat reducer 的描述完全一致——Phase 2a intent only → Phase 2b S14 reducer → S15 unique writer。无跨文档冲突。

---

### D11: per-player snapshot + critical reserve — ✅ PASS (with note)

**Verify**: per-player snapshot, actor context, critical entity size reserve, deterministic priority truncation, omitted_categories.

| Evidence | Status |
|----------|--------|
| `09-snapshot-contract.md` §1.1: 256KB per-snapshot cap, `truncated` flag | ✅ |
| `09-snapshot-contract.md` §1.2: `omitted_categories { entities, resources, events }` — 即便值为 0 键也必须存在 | ✅ |
| `09-snapshot-contract.md` §1.3: 确定性截断顺序 — distance bucket → entity_id lexicographic → farthest-first removal | ✅ |
| `09-snapshot-contract.md` §1.4: 关键实体永不截断 (self/Controller/target/allied drones/attackers) | ✅ |
| `09-snapshot-contract.md` §1.5: Competitive 模式截断降级标记 `tick_integrity = "degraded"` | ✅ |
| `01-tick-protocol.md` §2.3: per-player visibility filter + 256KB truncation with reference to snapshot-contract as sole authority | ✅ |

**Note — Critical entity size reserve 无显式上限**:
§1.4 关键实体列表包含 "己方所有 drone" + "正在攻击自身的实体"。极端场景下（玩家 500 drone + 500 攻击者 = 1000 entities × ~256 bytes = 256KB），关键实体集合自身就已占满 256KB cap——所有非关键实体（resources, structures, neutral entities）必定被截断。当前设计无 "关键实体集合大小上限" 约束。此为 R33 M4 发现，标记为 Medium（建议关注），非 blocking。若需修复，应在 §1.4 增加："若关键实体集合序列化后 > 200KB，按距离桶优先级从最远己方 drone 开始移除（保留最近 N 个己方 drone + 全部攻击者 + self + Controller），预留 ≥56KB for non-critical entities"。

---

### D12: T2/T3 核心化 — ✅ PASS

**Verify**: hash chain, cross-shard combat + logical clock, no Tier labels.

| Evidence | Status |
|----------|--------|
| `10-incremental-snapshot.md`: 文档头部声明 "原 Tier 2 内容，现已纳入核心设计。移除所有 Tier/未来/候选/待定 标签" | ✅ |
| `10-incremental-snapshot.md` §2.4 Hash Chain: `prev_modification_hash` + `self_hash = blake3(serialize_canonical(modification_set))` + chain_head 验证 | ✅ |
| `10-incremental-snapshot.md` §2.1: `TickModificationSet { prev_modification_hash, base_snapshot_hash, ... }` 完整 hash chain 字段 | ✅ |
| `11-shard-protocol.md`: 文档头部声明 "原 Tier 3 内容，现已纳入核心设计。移除所有 Tier/未来/候选/待定 标签" | ✅ |
| `11-shard-protocol.md` §4.3: "跨分片 tie-breaker 使用逻辑时钟，非物理时间戳。冲突排序键：(tick, shard_priority, entity_id)" | ✅ |
| No Tier/Future/Candidate/待定 labels found in either document | ✅ |

**R33 B2 闭合确认**: incremental-snapshot.md §2.4 新增了 hash chain 验证机制（`prev_modification_hash` + `self_hash` 链），修复了 R33 B2 发现的 "增量快照缺少 hash chain 验证" 问题。

**R33 H3 闭合确认**: shard-protocol.md 已升级为核心文档，逻辑时钟 (tick, shard_priority, entity_id) 保证了跨分片确定性。R33 H3 关注的 "跨分片 tick 同步协议细节" 在当前 scope（核心设计文档）已通过逻辑时钟给出确定性保证；详细 barrier protocol 可在实现阶段细化。

---

## P-H 逐项

### P-H1: EXECUTE unified budget table — ❌ NOT CLOSED

**对应 R33 B1 (Critical)**。统一预算表 (§8.2) 存在，但 §1.4 的 500ms 硬天花板与 §8.2 的 "EXECUTE 不单独超时" 冲突未修复。

| File | Content | Problem |
|------|---------|---------|
| `01-tick-protocol.md` §1.4 L73-77 | "硬超时天花板: 500ms (budget target 见 design/engine.md §3.4.1: World ≤400ms, Arena ≤50ms)" | EXECUTE 有独立硬天花板 500ms |
| `01-tick-protocol.md` §8.2 | "EXECUTE \| wall-clock total \| tick_soft_deadline_ms 内完成 \| 软截止前必须完成（EXECUTE 不单独超时，由 COLLECT+EXECUTE 总预算控制）" | EXECUTE 无独立超时 |

**影响**: 实现者无法确定 EXECUTE 应在 500ms abort（§1.4）还是仅在总和超过 2500ms 时触发软截止（§8.2）。两个合法解读导致完全不同的 failure mode。

**R33 修复建议未执行**:
1. 未将 §1.4 的 "硬超时天花板: 500ms" 改为引用 §8.2 语义
2. 未在 §8.2 增加 EXECUTE 独立 watchdog（防死循环）
3. engine.md §3.4.1 的 ≤400ms 未标注为 "性能目标（非硬天花板）"

---

### P-H2: hash chain verification in incremental snapshot — ✅ CLOSED

**对应 R33 B2 (Critical)**。`10-incremental-snapshot.md` §2.4 新增完整 hash chain 验证：
- `prev_modification_hash` 链
- `self_hash = blake3(serialize_canonical(modification_set))`
- `chain_head` 从 keyframe 到当前 tick 的验证流程
- "Replay verifier 加载 keyframe 后逐 tick 验证 hash chain，任一断裂 → replay 无效"

---

### P-H3: cross-shard combat logical clock — ✅ CLOSED

**对应 R33 H3 (High)**。`11-shard-protocol.md` §4.3:
- "确定性保证：跨分片 tie-breaker 使用逻辑时钟，非物理时间戳"
- "冲突排序键：(tick, shard_priority, entity_id)——全部由游戏状态派生，不依赖 FDB versionstamp 或墙钟"
- "同一初始状态 + 同一指令 + 同一分片拓扑 → 同一结果 → 可 replay"

---

### P-H4: 1000-player benchmark-gated — ✅ CLOSED

**Evidence**:
- `design/engine.md` §3.4.2: Hard cap 1000 derivation with explicit assumptions (p50=5ms, 1000 workers, 40 cores)
- "超过 hard cap: 新 WASM 部署被拒绝（`ERR_WORLD_FULL`）"
- Derivation contains explicit benchmark assumptions: "假设 1000 workers，p50=5ms"

模型存在且标记为 benchmark-gated——derivation 中的假设需 benchmark 验证。符合 "1000-player benchmark-gated" 设计要求。

---

### P-H5: admission hysteresis symmetric — ❌ NOT CLOSED

**对应 R33 H1 (High)**。`09-snapshot-contract.md` §7.2 的 admission hysteresis 仍为非对称：

```
if measured_p95 > SLO:
    reduce admitted_players by 10% (hysteresis: 10 tick cooldown before re-increase)
if measured_p95 < 50% of SLO for 30+ consecutive ticks:
    increase admitted_players by 5% (gradual recovery)
```

| 方向 | 幅度 | 条件 | Cooldown |
|------|:----:|------|:--------:|
| 降级 ↓ | 10% | measured_p95 > SLO | 10 tick |
| 恢复 ↑ | 5% | <50% SLO for 30+ ticks | 30+ ticks |

**R33 H1 发现仍完全适用**: 一次 burst 触发降级后，需 30 tick × 20 increments = 600 tick (30 分钟 @3s/tick) 才能恢复到 100%。若 burst 每几分钟发生一次，系统永久运行在降级容量。恢复条件 30 tick 远长于降级 cooldown 10 tick。

**R33 修复建议未执行**:
- 未将恢复条件从 30 tick 降至 10 tick（对称）
- 未增加快速恢复路径（25% SLO for 5 ticks → immediate recovery）
- 未增加 manual override admin API

---

### P-H6: Wasmtime pre-warm strategy — ❌ NOT CLOSED

**对应 R33 M1 (Medium)**。全量搜索 Swarm 文档（design/engine.md, tick-protocol.md, manifest, snapshot-contract, incremental-snapshot, shard-protocol）未发现 Wasmtime 版本升级预暖策略。

| Current state | Gap |
|---------------|-----|
| `design/engine.md` §3.4.3: "Wasmtime version 固定：编译期锁定，升级后重编译所有缓存模块" | 仅声明重编译，无异步预暖流程 |
| `design/engine.md` §3.4.3: "编译后的模块按 (module_hash, wasmtime_version) 缓存" | 版本升级 → 全量 cache miss |
| 无异步 pre-warm 机制 | R33 M1 修复建议（后台逐步重编译 + 原子切换）完全未执行 |

**影响**: Wasmtime CVE 修复（安全 SLA ≤72h）触发版本升级 → 500 player × 1-5 modules → 大规模 cache 失效 → 30s/module × 并发5 → ~50 分钟全量重建 → tick timeout storm。当前无防御措施。

---

## Strengths (设计亮点)

1. **Deferred combat model 三文档一致性**: engine.md + tick-protocol.md + manifest 对 Phase 2a intent → Phase 2b reducer → S15 unique writer 的 pipeline 描述完全一致，无跨文档冲突。

2. **Hash chain 修复扎实**: incremental-snapshot.md §2.4 的 `prev_modification_hash` + `self_hash` + `chain_head` 三组件 hash chain 设计完整，涵盖重建验证流程和断裂检测。

3. **T2/T3 核心化干净**: 两个文档移除了全部 Tier/未来/候选/待定 标签，逻辑时钟 (tick, shard_priority, entity_id) 为跨分片确定性提供了坚实保证。

4. **Snapshot truncation 确定性合同完整**: 距离桶 + entity_id 字典序 + farthest-first + critical 不可截断——四层优先级清晰，`omitted_categories` 字段 schema 稳定。

5. **EXECUTE 统一预算表 (§8.2) 存在且权威声明**: "消除跨文档分散定义导致的实现分叉风险"——预算表本身是正确的，只是 §1.4 的旧值未同步更新。

---

## GAP 修复建议 (按优先级)

### GAP-1 (Critical): 修复 §1.4 EXECUTE 500ms 硬天花板 → 引用 §8.2

**Fix**:
```
File: specs/core/01-tick-protocol.md §1.4 (lines 73-77)

OLD:
│     阶段二：执行 (EXECUTE)          │
│  硬超时天花板: 500ms                │
│  (budget target 见                  │
│   design/engine.md §3.4.1:          │
│   World ≤400ms, Arena ≤50ms)        │

NEW:
│     阶段二：执行 (EXECUTE)          │
│  在 tick_soft_deadline_ms(2500ms)   │
│  和 tick_hard_deadline_ms(4000ms)   │
│  约束下运行（见 §8.2 统一预算表）。 │
│  EXECUTE 不单独超时——超时由        │
│  COLLECT+EXECUTE 总预算控制。       │
│  性能目标: ≤400ms (World)/≤50ms     │
│  (Arena)，见 design/engine.md §3.4.1│
```

### GAP-2 (High): Admission hysteresis 对称化

**Fix** (`specs/core/09-snapshot-contract.md` §7.2):
```
选项 A（对称快速恢复）:
  if measured_p95 > SLO:
      reduce admitted_players by 10% (10 tick cooldown)
  if measured_p95 < 50% of SLO for 10+ consecutive ticks:   // 30→10
      increase admitted_players by 10%                        // 5%→10%
  if measured_p95 < 25% of SLO for 5+ consecutive ticks:     // 新增快速恢复
      increase admitted_players by 20%

选项 B（对称 + admin API）:
  保持降级/恢复速率不对称但增加：
  - admin API: swarm_admin_set_admission_capacity { world_id, target }
  - 自动恢复: 若无 burst 发生 60 tick，自动恢复到 target
```

### GAP-3 (Medium): Wasmtime pre-warm strategy

**Fix** (新增 `design/engine.md` §3.4.3 小节或 `specs/core/04-wasm-sandbox.md`):
```
Wasmtime 版本升级迁移策略:
1. 新版本 Wasmtime engine 初始化（非 tick 路径）
2. 后台异步预编译：按 player 活跃度优先级重编译模块
3. 双版本并行期：tick 使用旧缓存，后台新缓存逐步就绪
4. 原子切换：新缓存覆盖率 > 80% 时切换到新版本 Wasmtime
5. 旧版本 engine 保留 24h 后回收（rollback window）
6. 若 1h 内缓存覆盖率未达 50% → 告警，降级至仅编译 active players 模块
```

### GAP-4 (Medium): R/W matrix HitPoints 列与 S15 unique writer 对齐

**Fix** (`06-phase2b-system-manifest.md` §S15 + §4):
```
§S15 文本修改:
"S15 是 combat damage/heal application 的 UNIQUE 写入者。除 S10 regen（life regeneration）
外，Phase 2b 中仅 S15 写入 Entity.hits 用于 combat 结算。
S01/S03/S08 的 HP 写入限定于：实体初始化 (S08 spawn)、结构建造 (S03 build)、
非 combat HP 变更 (S01 command inline apply)。S22 的 HP 写入限定于 status effect 
application。S24 的 HP 写入限定于 structure decay。各 writer 的 domain 互不重叠。"

§4 矩阵保持不变（多 writer 是正确的），但添加脚注说明各 writer 的 HP domain。
```

---

## CrossCheck

- **CX-1**: §1.4 EXECUTE budget 冲突 (500ms vs unified model) → 建议 **Architecture Reviewer** 检查：engine.md §3.4.1 的 ≤400ms 标注为 "性能目标" 非硬天花板后，Phase 2b 无独立 watchdog 时若 status_advance (S22) 对 5000 active status entities 耗时过长如何保护 tick。
  
- **CX-2**: Admission hysteresis 非对称 → 建议 **Gameplay Reviewer** 检查：若系统长期运行在降级容量（90% of target 500 = 450），对 1000 active drones 的 combat density 是否有可观测的 gameplay 影响。

- **CX-3**: R/W matrix 多 HP writer vs S15 unique claim → 建议 **Interface/CI Reviewer** 确认：CI 静态验证是否真正强制执行 S15 的 "unique writer" 约束——若 matrix 本身标记 S01/S03/S08 为 W，CI 无法区分合法 domain-specific write 与非法 combat write。建议 CI 检查改为 per-domain 验证而非全局 column 检查。

---

## 总结

| Category | Pass | Fail | Notes |
|----------|:----:|:----:|-------|
| B3 (combat deferred) | ✅ | | Minor R/W matrix note |
| B7 (HP writer contract) | ✅ | | Matrix discrepancy with S15 unique claim |
| D2 (deferred reducer) | ✅ | | Three-document consistency |
| D11 (per-player snapshot) | ✅ | | Critical reserve size boundary unaddressed (R33 M4) |
| D12 (T2/T3 core) | ✅ | | Hash chain + logical clock both confirmed |
| P-H1 (EXECUTE budget) | | ❌ | §1.4 500ms still conflicts with §8.2 |
| P-H2 (hash chain) | ✅ | | Fully implemented |
| P-H3 (logical clock) | ✅ | | Fully documented |
| P-H4 (1000-player) | ✅ | | Benchmark-gated model exists |
| P-H5 (hysteresis) | | ❌ | Still asymmetric |
| P-H6 (wasmtime pre-warm) | | ❌ | No pre-warm strategy |

**总计**: 7/10 PASS, 3/10 FAIL.