# R30 Architect 独立评审报告 — rev-dsv4-architect

> 评审日期: 2026-06-21
> 评审视角: Architect — ECS 调度正确性、数据流一致性、算法复杂度与正确性、tick pipeline 确定性闭合、跨组件状态同步、持久化边界完整性
> 评审文档:
> - design/README.md, design/engine.md, design/tech-choices.md
> - specs/reference/api-registry.md
> - specs/core/01-tick-protocol.md, specs/core/02-command-validation.md
> - specs/core/04-wasm-sandbox.md, specs/core/05-persistence-contract.md
> - specs/core/06-phase2b-system-manifest.md

---

## 1. Verdict

**CONDITIONAL_APPROVE**

整体架构设计完备：确定性闭合覆盖所有关键路径（PRNG namespace 隔离、5 层 canonical sort key、indexmap/HashMap 替代、整数定点数禁用 f64）、ECS 系统调度链的 R/W 矩阵并行安全证明严谨、持久化分层（FDB replay-critical subset + Object Store async blob）干净无歧义、COLLECT 缓存 + attempt_id/collect_id/commit_id 三重标识模型正确处置了 FDB commit retry 的燃料扣费与状态一致性问题。

存在两处 **High** severity 的 manifest 文档缺陷需要闭合后再进入实现阶段——均为文档描述与实际架构意图的偏差，不涉及架构重设计。另有三处 **Medium** 跨文档一致性问题。

---

## 2. 发现的问题

### H1: Phase 2a 缺少特殊攻击指令处理器声明 [High]

**文件**: `specs/core/06-phase2b-system-manifest.md` §1 S01 定义行、§2 S01-S06 系统详情表

**问题**: 
Manifest 定义 Phase 2a 共 6 个 inline 处理器（S01–S06）。S01 `command_executor` 的 handled commands 列为 `Move, Harvest, Attack, RangedAttack, Heal, Claim`——共 6 个核心指令。但 `api-registry.md` §1 和 `02-command-validation.md` §3.10–3.15 定义了 6 个活跃特殊攻击指令（Hack/Drain/Overload/Debilitate/Disrupt/Fortify），各自有详细的 Ph2a inline 校验表（所有权、范围、冷却、body part、资源消耗）。这 6 个特殊攻击**不在任何 Phase 2a handler 的 handled commands 列表中**。

**影响**: 
实现者无法确定特殊攻击指令在 Phase 2a 的入口点——它们应由 S01 处理（需扩展 handled commands 列表），还是需要独立的 S01b `special_attack_executor`？当前 manifest 未给出路由。若实现者自行推断，可能与 Phase 2b S14 `special_attack_reducer` 的 intent 收集接口不匹配。

**修复建议**:
方案 A（推荐）— 在 S01 的 handled commands 列表中加入 `Hack, Drain, Overload, Debilitate, Disrupt, Fortify`，并更新其 Writes 声明增加 `PendingSpecialAttackIntent` buffer 写入。理由：这些指令的校验与其他 core 指令共享同样的所有权/范围/冷却/body part 检查框架，inline 应用语义一致（扣除 Energy、检查 cooldown、产出 intent）。

方案 B — 若特殊攻击校验逻辑足够独立（如需要 per-attack-type 的自定义抗性计算），新增 S01b `special_attack_executor`（Phase 2a inline），将 6 个特殊攻击指令路由至此。但其校验结果（intent buffer + resource 扣费）仍需与 S01 的 EventLog/ResourceAmount 协调。

### H2: S14 special_attack_reducer 错误引用了 S11-S13 作为 intent 来源 [High]

**文件**: `specs/core/06-phase2b-system-manifest.md` §S14 Processing pipeline 第 1 步

**问题**:
```text
S14 Processing pipeline:
  1. Parallel collect: S11-S13 产生的特殊攻击 intent
     （Hack/Drain/Overload/Debilitate/Disrupt/Fortify）写入 per-system sub-buffer
```

S11-S13 是 `attack_system` / `ranged_attack_system` / `heal_system`——这三个是 Phase 2b 被动 combat 系统，处理 NPC/Tower 自动攻击和 DoT，不处理玩家提交的特殊攻击指令。特殊攻击指令在 Phase 2a inline 阶段已被校验并产出 intent（resource 扣除 + cooldown 标记 + `PendingSpecialAttackIntent` buffer 写入）。S14 的 intent 来源应为 Phase 2a 阶段的 `PendingSpecialAttackIntent` buffer，而非 S11-S13。

engine.md §3.2 明确分离了两者：
- Phase 2a inline: 玩家命令（含特殊攻击）
- Phase 2b combat_system（S11-S13）: "仅处理非玩家命令的战斗——Tower 自动攻击、持续伤害效果（DoT）"

**影响**: 
实现者若按 manifest 的 S14 描述编码，会在 S11-S13 处寻找特殊攻击 intent 产出逻辑，发现不存在后产生困惑或错误地让 combat 系统产出特殊攻击 intent。

**修复建议**:
修正 S14 Processing pipeline 第 1 步为：
```text
1. Read buffer: 从 Phase 2a inline handler 产出的
   PendingSpecialAttackIntent buffer 读取全部特殊攻击 intent
   （Hack/Drain/Overload/Debilitate/Disrupt/Fortify）
```
并移除 S14 Reads 声明中的 `(from S11-S13)` 标注，改为 `(from Phase 2a PendingSpecialAttackIntent buffer)`。

---

### M1: Overload target_id 语义歧义 — EntityId vs PlayerId [Medium]

**文件**: `specs/core/02-command-validation.md` §3.12 行 347 / `specs/reference/api-registry.md` §1.3 行 73

**问题**:
`02-command-validation.md` §3.12 校验表声明 Overload 的 `target_id` 为 "有效的 player_id"（即目标是一个玩家而非实体），校验逻辑包含 `target_id != player_id`（非己方）和 `is_visible_to(target, attacker)`（可见性约束）。而 `api-registry.md` §1 的 CommandAction 表格中，所有 21 个 action 共享 `object_id: EntityId` 公共字段，Overload（#16）的 `target_id` 列与其他 action 同为 `EntityId`。

Overload 的语义是削减目标玩家的 fuel budget——操作对象是 player，不是具体 entity。但 schema 层面它与其他 action 共享 `EntityId` 类型，产生歧义。

**影响**: 
SDK codegen 可能为 Overload 生成 `target_id: EntityId` 参数签名，但引擎校验层需要将其解析为 `PlayerId`。类型不匹配增加实现摩擦。

**修复建议**:
在 `api-registry.md` §1.3 Overload 行增加注释澄清 target_id 的运行时语义：
```text
| 16 | `Overload` | `target_id: EntityId` (运行时解析为 PlayerId) | special_attack | Reduce target fuel budget |
```
或在 IDL 中将 Overload 的 target 字段独立声明为 `player_id` 类型（与其他 action 的 `target_id: EntityId` 分离），在 registry 生成时标注差异。

---

### M2: Hack 阶段效果（减速/定身）的调度位置不清 [Medium]

**文件**: `specs/core/02-command-validation.md` §3.10 行 307 / `specs/core/06-phase2b-system-manifest.md` §S22

**问题**:
`02-command-validation.md` §3.10 详细描述了 Hack 的 5 阶段效果：
- tick 1-2: 目标减速 50%
- tick 3-4: 目标无法移动
- tick 5: 夺取成功（转 Neutral）

但 `06-phase2b-system-manifest.md` §S22 `status_advance_system` 的伪代码仅包含 `HackState.stage += 1; duration = hack_duration`——无 stage 对应的减速/定身/夺取逻辑。这些阶段效果必须在某处实现。可能的位置：(a) S22 内部根据 `HackState.stage` 分支应用不同 modifier，(b) S16 `hack_system` 读取 stage 并写入 Movement/Fatigue 等组件。

当前两个文档都未明确指定。

**影响**: 
实现者无法确定 Hack 阶段效果的写入责任归属。若分别实现在 S16 和 S22 中，可能产生写入冲突（两者都尝试修改 movement 相关组件）。

**修复建议**:
在 `06-phase2b-system-manifest.md` §S22 伪代码中明确 stage-specific 分支：
```text
Hack → HackState.stage += 1
       if stage == 1-2: 施加 SlowMovement(×0.5) modifier
       if stage == 3-4: 施加 Immobilize modifier
       if stage == 5: 转移 owner → Neutral, 清除所有 HackState
```
并标注这些 modifier 写入的 Component 类型（`MovementModifier` / `Owner`），与 R/W 矩阵对齐。

---

### M3: Per-tick action quota 执行点与 02-command-validation.md 引用不一致 [Medium]

**文件**: `specs/core/06-phase2b-system-manifest.md` §S01 Note / `specs/core/02-command-validation.md` §3.3 行 374

**问题**:
Manifest S01 Note 声明：`Per-drone per-tick action quota enforced inline: max 1 main action per drone. Transfer/Withdraw 不计入但受 carry 容量约束。`

`02-command-validation.md` §3.3 行 374 声明：`Per-drone per-tick action quota：每 drone 每 tick 最多执行 1 个 main action（Move/Attack/Harvest/Build/Heal 及其特殊攻击变体）。`

两处对 "main action" 的范围定义不同：
- Manifest S01 Note: 未列出具体 action 类型，仅说 "max 1 main action"
- `02-command-validation.md` §3.3: 列出 `Move/Attack/Harvest/Build/Heal 及其特殊攻击变体`

此外，`api-registry.md` §5.1 有 `Commands/player/tick = 100` 的全局上限，但这与 per-drone action quota 是两个独立维度。Manifest S01 定义 per-drone quota，但 `02-command-validation.md` 未提及 Manifest 是此 quota 的权威定义源。

**影响**: 
若未来新增 action 类型（如 mod 自定义 action），需确定它是否计入 per-drone quota——当前两处文档定义范围不完全一致。

**修复建议**:
在 `02-command-validation.md` §3.3 增加引用：`> 权威 per-drone per-tick action quota 定义见 06-phase2b-system-manifest.md §S01。`
并在 Manifest S01 中明确列出 main action 类型（`Move, Harvest, Attack, RangedAttack, Heal, Claim, Build, Recycle, Hack, Drain, Overload, Debilitate, Disrupt, Fortify`），标注 `Transfer/Withdraw 不计入，Spawn 不计入（仅校验）`。

---

### L1: Decay (S24) 标记为 "Parallel Set C" 但仅含单系统 [Low]

**文件**: `specs/core/06-phase2b-system-manifest.md` §1 System Schedule 行 57-58

**问题**:
```text
Parallel Set C: World Maintenance
  [S24] decay_system (serial within C)
```

"Parallel Set C" 仅含 1 个 system——标记为 parallel set 无意义。`(serial within C)` 的注释暗示此 set 原本设计为容纳多个 system（如 decay + structure_decay 等），但当前仅剩一个。此命名可能误导读者认为 decay 在某并行组内执行。

**影响**: 
低——文档可读性。不影响架构正确性（decay 与其他 system 无数据竞争已在 R/W 矩阵中证明）。

**修复建议**:
方案 A — 将 S24 直接提升为 serial spine 的一个独立节点，移除 "Parallel Set C" 包装。
方案 B — 若未来计划扩展此 set（如加入 `structure_decay_system`），保留结构但添加注释 `(reserved for future parallel systems)`。

---

## 3. 亮点

1. **确定性合同完整无死角**（01-tick-protocol.md §9）：PRNG namespace 隔离（combat/loot/npc_spawn/event 各自独立 Blake3 XOF 派生流）、5 层 canonical sort key（priority_class → shuffle_index → source_rank → sequence → command_hash）、indexmap 替代 HashMap、定点整数禁用 f64——覆盖了 Rust 生态中所有已知的非确定性来源。Seed 生命周期模型（Arena commit-reveal + World operator seed-bump）基于根本约束（确定系统中前向保密不可能）的务实设计。

2. **持久化分层架构干净**（05-persistence-contract.md）：FDB 只存 replay-critical subset（10 项必填字段，§2.1）+ 大 blob 异步进 object store（§Phase C）。`upload_status` 状态机（pending → uploading → complete/failed）正确处理了 blob 缺失时的降级语义（`terminal_state = audit_gap`）。Deploy 完整状态机（§2.3: VALIDATE → UPLOAD_PREPARE → MANIFEST_COMMIT → ACTIVATION_PENDING → ACTIVE/FAILED）消除了 blob 异步上传的 TOCTOU 缺口。Commit retry 的 collect_id/attempt_id/commit_id 三重标识（§7.1）正确处置了燃料跨重试不追加扣费的语义。

3. **ECS R/W 矩阵并行安全证明严谨**（06-phase2b-system-manifest.md §4）：
   - Combat Parallel Set A (S11-S13): 按 `target_id` partition 保证无共享写入
   - Status Effects Parallel Set B (S16-S22): 各 system 写入互不重叠的 `StatusState` subtype（HackState ≠ DrainState ≠ OverloadState...），`status_advance_system` 统一推进但写入不同 component 实例
   - RoomCap 中间态保护: S07→S08 区间禁止任何 system 读取 RoomCap 做准入决策
   - Special Attack Unique Writer Contract: 每种 status component 有且仅有一个 writer（S22）

4. **关键时序设计正确**（R16 B2 修复链）：
   - `death_marker` → `spawn`: RoomCap 同 tick 释放+消费，无浪费 tick
   - `spawning_grace` → combat: 新生 drone 1 tick 无敌帧，防止"出生即斩"
   - `regeneration` → `damage_application`: 自然回复先于伤害结算，防止 heal+regen 双倍回复
   - special_attack_reducer → status_advance_system: intent 归并/排序/裁决与状态推进分离，单写者合同

5. **Bevy World snapshot/restore 故障恢复模型**（01-tick-protocol.md §3.5）：Phase 2a 前深拷贝全量 World 状态（含所有 Component + Resource 的清单覆盖），FDB commit 失败时 `world.restore(snapshot)` 完整回滚。COLLECT 结果跨重试缓存（不重新执行 WASM，同一 collect_id）。CI 故障注入测试（随机 10% commit 失败率，验证 `state_checksum == snapshot_checksum`）。

6. **经济约束反套利证明**：
   - Recycle lifespan-proportional 退还：`refund_pct = max(0.1, 0.5 × remaining/total)`，末期仅 10% body_cost——无法形成"Recycle→spawn→净赚"循环（02-command-validation.md §3.18）
   - Overload 抗永久锁死证明：全局冷却 50 tick per target 不限攻击者数 + 恢复速率 `fuel_budget/1000` per tick + 下限 20% MAX_FUEL——数学上不可能将 target fuel 压至 0（02-command-validation.md §3.17）

7. **Per-player fair-share admission**：pathfinding 按 `floor(global_budget / active_players)` 均分，份额在 tick 开始时固定，先到先得消耗。防止单玩家垄断全局资源（engine.md §3.4.2）。

---

## 4. CrossCheck — 需要跨方向检查

以下问题在我（Architect）的方向范围内可识别但无法独立裁决——需要其他方向的 reviewer 确认：

- **CX1**: Phase 2a inline handlers (S01-S06) 的 handled commands 列表可能缺少特殊攻击指令路由（见 H1）。建议 **Mechanics (gameplay)** 方向确认特殊攻击的校验逻辑是归入 `command_executor`（S01）扩展还是需要独立的 Phase 2a handler。

- **CX2**: Overload 效果（fuel budget 削减）在 Phase 2b 应用、影响下一 tick COLLECT 的时序是否正确？当前设计中 Phase 2a 的 WASM 执行已使用本 tick 的 fuel budget——Overload 只能影响未来 tick。建议 **Gameplay** 方向确认此设计意图是否与预期的"即时压制"体验一致。

- **CX3**: Hack 阶段效果（减速/定身/夺取）的 ECS Component 写入责任归属——是由 S22 `status_advance_system` 统一处理还是 S16 `hack_system` 分散处理？建议 **Mechanics** 方向明确 HackState 各阶段的 modifier 应用路径，并与 manifest 的 Unique Writer Contract 对齐。

- **CX4**: Sandbox worker pool 的 `fork + seccomp + cgroup v2` 模型隐含 Linux-only 依赖。`04-wasm-sandbox.md` §4 的 seccomp BPF 白名单、cgroup v2 memory.max/cpu.max 配置均为 Linux 内核特性。建议 **Security** 方向评估：(a) macOS/Windows 开发环境的 sandbox 降级策略，(b) Docker/K8s 容器内嵌套 cgroup 的兼容性。

- **CX5**: `api-registry.md` §1.3 声明 Leech（#20）和 Fabricate（#21）为 Tier 2 特性（`⏳ Tier 2`），但 `02-command-validation.md` §3.16 特殊攻击状态机矩阵包含了它们的同 tick 多次行为规则和反制窗口。建议 **Gameplay** 方向确认 Tier 2 特性在 Phase 1 设计文档中的状态——是否应移除或标注为 "future"。

- **CX6**: `02-command-validation.md` §5.1 拒绝码表中出现了 `MainActionQuotaExceeded`、`StillSpawning`、`AlreadyDebilitated(damage_type)` 等码，但 `api-registry.md` §2 的 canonical RejectionReason enum（47 codes: 35 game + 12 auth）中未找到这些码。建议 **Interface (API)** 方向验证这些拒绝码是否应注册进 canonical enum，或按 D2/B 决策（放入 `debug_detail` 字段）。

---

*评审完成。2 High + 3 Medium + 1 Low 问题需闭合后进入实现阶段。架构整体正确，manifest 文档修复量小。*