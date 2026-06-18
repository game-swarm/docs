# Architect Review — Swarm R22 Phase 1 (rev-dsv4-architect)

**评审员**: Architect (DeepSeek V4 Pro)
**日期**: 2026-06-18
**评审范围**: ECS 调度正确性 / Tick 生命周期完整性 / 数据一致性 / 算法复杂度

---

## 1. Verdict

**CONDITIONAL_APPROVE** — 架构设计总体稳健，核心调度（29-system manifest）、FDB 分层持久化、COLLECT 缓存复用等关键路径设计正确。但存在 **1 个 Critical 跨文档系统排序冲突**和 **1 个 High 容量参数不一致**，必须在 Phase 2 交叉评审前修复。

---

## 2. Strengths

- **两阶段快照架构**：一次构建房间分片 + 玩家拼接，复杂度从 O(P × E) 降为 O(E + P × R)。正确且高效。
- **FDB 异步上传 (D5/B)**：将 blob 写入移出事务热路径，FDB 仅存 manifest + hash pointer。FDB commit 成功即 tick 完成——正确解耦 I/O 延迟与事务原子性。
- **COLLECT 缓存跨重试复用**：`collect_id` 不变，`attempt_id` 递增，WASM 不重跑，fuel 不追加。设计精确。
- **29-system Manifest + R/W 矩阵**：串行脊柱 + 3 并行 sets，每 system 声明读写关系，并行安全有形式化证明。RoomCap 中间态保护 (`S07→S08` 无 reader) 正确。
- **Seeded Shuffle 公平排序**：`Blake3("shuffle" || world_seed || tick)` 确定性 + 公平轮换。前向保密威胁模型分析透彻，接受"定期轮换 + 服主介入"的合理风险。
- **Phase 2a Inline / Phase 2b Deferred 分类**：玩家命令 inline 逐条应用（先到先得），被动系统 deferred 批量执行。职责分离干净。
- **Overload 抗永久锁死证明**：形式化证明了全局冷却 + 下限保护确保目标 fuel budget 不可锁死到 0。
- **Recycle lifespan-proportional refund**：剩余 lifespan 越少退还越低，下限 10%，防止末期套利。经济约束验证完整。

---

## 3. Findings

### D1 [Critical] — 跨文档系统排序冲突：02-command-validation §3.19 vs Manifest

**文件**: `specs/core/02-command-validation.md` §3.19 vs `specs/core/06-phase2b-system-manifest.md` §1

**问题**: `02-command-validation.md` §3.19 描述 `status_advance_system` 调度位置为：

```
death_mark → spawn → spawning_grace → combat → status_advance → (regeneration, decay 并行) → death_cleanup
```

而 Manifest (权威调度，R16 B2) 定义为：

```
S07 death_marker → S08 spawn → S09 spawning_grace → S10 regeneration → S11-S13 combat → S14 spec_atk_red → S15 dmg_apply → S16-S22 status → S23 aging → S24 decay → S25 death_cleanup
```

**具体冲突**：
| 系统 | §3.19 位置 | Manifest 位置 | 冲突 |
|------|-----------|--------------|------|
| `regeneration` | combat **之后** | combat **之前** (S10, 在 S11-S13 前) | Manifest 明确此为 R16 B2 修复，防止 heal+regen 双倍回复 |
| `status_advance` | combat 之后、regeneration 之前 | S16-S22，在 damage_application (S15) 之后 | 位置偏移 2 个 system |
| `regeneration ∥ decay` | 声称可并行 | Manifest: S10 (串行) 与 S24 (串行) 被 14 个 system 隔开 | 两者均写 `HitPoints`，不可并行 |

**影响**: 实现者若以 §3.19 为参考，会将 regeneration 放在 combat 之后，导致 heal+regen 双倍回复 bug。`regeneration ∥ decay` 声称的并行会导致 `HitPoints` 数据竞争。

**修复建议**: 将 `02-command-validation.md` §3.19 整节替换为指向 Manifest 的引用，或完全重写以匹配 Manifest 的实际调度。所有 status_advance 的描述应引用 Manifest S16-S22。

---

### D2 [High] — MAX_DRONES_PER_PLAYER 参数不一致：50 vs 500

**文件**: `specs/core/02-command-validation.md` §6 vs `specs/reference/api-registry.md` §5.1 vs `design/engine.md` §3.4.2

| 文档 | 值 | 说明 |
|------|-----|------|
| `02-command-validation.md` §6 | **50** | `MAX_DRONES_PER_PLAYER` |
| `api-registry.md` §5.1 | **500** | `Per-player drone cap` (world.toml 可调) |
| `engine.md` §3.4.2 | **500** (default, configurable) | `Per-player drone cap` |

**影响**: 若实现者以 `02-command-validation.md` 为准，会将单个玩家的 drone 上限硬编码为 50，严重限制游戏规模（500 活跃玩家 × 50 drones = 2500，远低于 5000 target）。

**修复建议**: `02-command-validation.md` §6 的 `MAX_DRONES_PER_PLAYER` 应改为 500（与 registry 一致），或标注为 "per-room cap" 以区分 per-player cap。api-registry 是权威数值源——其它文档应引用而非重新声明。

---

### D3 [Medium] — 排序键定义不一致：§3.1 简化版 vs §9.1 权威版

**文件**: `specs/core/01-tick-protocol.md` §3.1 vs §9.1

| 层级 | §3.1 (简化) | §9.1 (权威) |
|------|------------|------------|
| 1 | `order_index` | `priority_class` (0=Admin, 1=WASM, 2=MCP_Deploy, 3=MCP_Query) |
| 2 | `player_id` | `shuffle_index` (Fisher-Yates) |
| 3 | `cmd.sequence` | `source_rank` |
| 4 | — | `sequence` |
| 5 | — | `command_hash` (Blake3) |

§3.1 的伪代码未包含 `priority_class` 和 `source_rank`。如果实现者只看 §3.1，Admin 命令不会获得最优先执行，MCP_Deploy 与 WASM 命令也不会被正确分层。

**修复建议**: 在 §3.1 添加注释指向 §9.1 的规范定义，或将两节合并。`§9.1` 应标注为 **canonical** 排序定义。

---

### D4 [Medium] — 快照截断 `distance_to_drone` 歧义：哪个 drone？

**文件**: `specs/core/01-tick-protocol.md` §2.3, `design/engine.md` §3.4.4

截断排序键使用 `distance_to_drone`——但一个玩家可能有多个 drone 在不同房间。文档未指定：
- 用最近 drone 的距离？
- 用所有 drone 的最小距离？
- 用拥有最多可见实体的 drone？

**修复建议**: 明确指定为 "到玩家最近 drone 的曼哈顿距离"。此定义必须进入确定性合同——不同实现选择会导致不同的截断结果，破坏 replay。

---

### D5 [Low] — FDB 异步上传 crash 恢复未定义

**文件**: `specs/core/05-persistence-contract.md` §2, §6.2

FDB commit 成功后，blob 异步上传。若引擎在此窗口 crash：
- `tick_manifest.upload_status = 'pending'` 或 `'uploading'`
- blob 未写入对象存储
- 重启后该 tick 的 replay 永久不可用

文档未定义引擎重启时对 `upload_status ∈ {pending, uploading}` 的恢复策略（应扫描并重试）。当前只有 in-process 3 次重试（1s/2s/4s 指数退避），进程 crash 后这些记录永久丢失。

**修复建议**: 在 `05-persistence-contract.md` 增加 "Crash Recovery" 小节，定义引擎启动时扫描 `upload_status != 'complete'` 的 tick_manifest 行并重试上传。

---

### D6 [Low] — Refund 表中 `InsufficientResource` 重复且矛盾

**文件**: `specs/core/02-command-validation.md` §7.1

Refund 策略表中有两个 `InsufficientResource` 条目：

| 出现位置 | 退还 | 理由 |
|---------|:--:|------|
| 第 1 条 | 退 50% fuel | 竞争导致——非玩家过错 |
| 第 4 条（再次出现） | 不退 | 玩家应计算资源 |

两条规则未区分适用场景。一个 drone 试图 Harvest 已枯竭的 Source——是竞争（该退 50%）还是玩家应自行检查（不退）？

**修复建议**: 区分 `InsufficientResource_Contention`（竞争导致，退 50%）和 `InsufficientResource_SelfOwn`（自身资源不足，不退），或明确按指令类型拆分 refund 规则。

---

### D7 [Low] — SnapBuild vs COLLECT 的 `tick_counter` 语义歧义

**文件**: `specs/core/01-tick-protocol.md` §1.4 vs §2.3

§1.4 Tick 状态机显示 `tick_counter = N` 在空闲等待阶段，三个阶段完成后 `tick_counter = N + 1`。但 §2.3 快照时序边界中，快照构建发生在 COLLECT 开始时，此时 `tick_counter` 仍为 N（尚未递增）。快照中的 `snapshot.tick` 字段标注为 `current_tick`——这意味着 `current_tick = N`。

但 §9.3 输出状态合同中说 `snapshot.tick == current_tick`。这里的 `current_tick` 是 tick N（EXECUTE 即将处理的 tick）还是 tick N（COLLECT 正在收集命令的 tick）？如果 COLLECT 在 tick N 开始但 EXECUTE 处理的是 tick N 积累的命令，那么 `current_tick` 应始终等于 `tick_counter`（即 N）。这需要明确。

**修复建议**: 在 Tick 状态机中明确标注 `tick_counter` 在各阶段的取值，确保 COLLECT snapshot 的 `tick` 字段与 EXECUTE 处理的 tick 编号一致。

---

## 4. CrossCheck — 需要跨方向检查

以下为我怀疑但超出架构方向的潜在问题，需要其他方向评审员确认：

- **CX1**: Controller 维修公式使用 `global_cap = floor(active_drones × 0.5)` 限制每 tick 总 age 回退。此公式在 5000 drone 规模下 global_cap = 2500 age reduction/tick。但 repair_capacity 在 RCL8 时仅为 80/tick——差距 31 倍。维修是否实际成为瓶颈？→ 建议 **Game Designer** 检查维修容量与 drone 规模的经济平衡。

- **CX2**: Overload 的 `is_visible_to(target_player, attacker)` 约束在 `02-command-validation.md` §3.12 中定义，但 MCP 工具 `swarm_get_snapshot` 使用的是 fog_of_war 过滤。若 MCP query 绕过了 visibility check，攻击者可通过反复 query 确认目标是否在线并推断 fuel 水平。→ 建议 **Security** 检查所有 MCP tool 的 visibility_filter 是否与 game-layer visibility 一致。

- **CX3**: `swarm_deploy` 使用 `deploy_mutation` replay class，但 `swarm_deploy` 的 blob 异步上传（Phase C）与 FDB manifest commit（Phase B）之间存在时序窗口。如果在 blob 上传完成前触发 replay，replay verifier 找不到 blob。→ 建议 **Architect** (cross-check with rev-claude-architect) 验证 deploy_mutation replay 在异步上传模型下仍保持确定性。

- **CX4**: `status_advance_system` 统一推进所有特殊攻击状态，但特殊攻击的 intent 收集发生在 combat parallel set A (S11-S13)，而 reducer (S14) 进行 canonical sort，最终在 S22 应用。若 S11-S13 并行写入 `pending_intents` buffer，需要确认 buffer 的并发写入策略（lock-free? per-system sub-buffer?）。→ 建议 **Architect** 验证 `pending_intents` 的并行写入安全性。

- **CX5**: `swarm_get_snapshot` MCP tool rate limit 为 `1/tick`，但 WASM tick() 内部可以无限次调用 `host_get_objects_in_range`（上限 5/tick）。AI 玩家通过 MCP query 能获取的信息量远小于 WASM 玩家——这可能是设计意图（MCP 是管理接口），但可能在 competitive 模式下产生不公平。→ 建议 **Game Designer** 评估 MCP vs WASM 信息不对称是否影响竞技公平性。

---

## 5. Algorithmic Complexity Analysis

| 操作 | 声明复杂度 | 实际分析 | 判定 |
|------|----------|---------|:--:|
| Snapshot build + stitch | O(E + P × R) | E=50k entities, P=500 players, R≤9 rooms. ~50k + 500×9×~500 = ~2.3M ops. | ✅ 可行 |
| Seeded shuffle | O(P log P) | Fisher-Yates: 500 swaps, trivial | ✅ |
| Command sort | O(C log C) global tier | C ≤ 500×100 = 50k commands worst case. 50k log 50k ≈ 780k comparisons. | ✅ 可行，但接近 budget |
| Pathfinding global budget | 100,000 explored nodes/tick | A* per call ≤ 500 nodes (MAX_PATH_LENGTH). 500 players × 10 calls = 5000 calls, fair-share 20 nodes/call at 500 players. | ⚠️ tight at scale |
| FDB transaction | < 10KB/tick | Per spec. 50k entities delta would exceed this if not using delta encoding | ⚠️ 需 delta 编码验证 |
| Parallel combat (S11-S13) | target_id partition | Partition by target_id: worst case all attack same target → serial bottleneck | ⚠️ 单目标退化 |

---

*评审基于只读子集：design/README.md, design/engine.md, design/tech-choices.md, specs/reference/api-registry.md, specs/core/01-05-06 + 04-wasm-sandbox。未读取 reviews/、/data/swarm/ 下任何文件。*
