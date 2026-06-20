# Swarm Implementation ROADMAP

> 仅列出待实现变更。文件互斥：同一 Wave 内任务触碰的文件集完全不相交。
> 系统编号以 `specs/core/06-phase2b-system-manifest.md` 为权威来源（S01-S29）。
> DAG 经 2026-06-20 GPT-5.5 + DeepSeek V4 Pro 交叉审计修正。

---

## 当前状态

| 类别 | 数量 | 说明 |
|------|:----:|------|
|| ✅ 已完成 Wave | 14 | W0-W7, W8-W9, W10, W11, W12, W13, **W14 (EventLog)** |
|| ✅ Manifest 已实现 | 26 | S01-S25(✔), S26(✔), S27, S28 |
|| ⚠️ Stub/语义错位 | 1 | S29(387行库代码,缺ECS系统) |
|| ❌ 完全缺失 | 0 | — |
|| 🔧 Infrastructure | 4 | body_part_match, DisruptedResisted, S29 resource_ledger, arena.rs, security.rs |

> **当前提交**: `7568cef` (W14 EventLog)。W0-W14 全部完成。314 tests。
> controller_repair_system (196行) 代码正确修复 body hits —— 文件注释和 ROADMAP 旧版标注有误。

---

## 修正后的 Wave 依赖图

```
W7 (Combat+Visibility) ✅
 │
 ├─► W8  (S09+S10+S24+S26) ✅
 │      │
 │      └─► W9  (S14+S15)    ✅
 │             │
 │             ├─► W10 (body_part_match) ✅
 │             │      │
 │             │      └─► W12 (S19+S20+S21+S22) ←─ W10→S20 已就位
 │             │
 │             └─► W12 (S19+S20+S21+S22) ←─ 依赖 W9 (S14→S22 链)
 │
 ├─► W11 (S16+S17+S18) ✅ ──可与 W12 并行──► W12 (S19+S20+S21+S22) ✅
 │                                               │
 │                          ┌────────────────────┘
 │                          ▼
 │                      W13 (S23+S25) ✅
 │                          │
 │                          ▼
 │                      W14 (P3-8 Feedback Loop) ✅
 │                          │
 │                          ▼
 │                      W15a (Arena Core)
 │                          │
 │                          ▼
 │                      W15b (Arena Security)
 │                          │
 │                          ▼
 │                      W15c (Arena Gameplay)
 │
 ├─► W16a (P1-6 WASM CDN) ←─ 完全独立，可与任何 Wave 并行
 │
 ├─► W16b (P2-7 Economy Balance) ←─ 依赖 W2-W6
 │
 └─► W17 (Benchmarks) ←─ 依赖 W14+W15c+W16（全系统就位后才有有效指标）
      │
      └─► W16c (P1-7 CommandSource Gate) ←─ 依赖 W12 (special attack commands 就位)
```

**关键修正**（vs 旧 DAG）：
- ❌ 删除虚假依赖：W1→W2、W1→W7、W3→W4、W5→W6、W7→W8、W8→W9、W10→W11、W12→W13
- ✅ W11 与 W12 可并行（文件互斥）
- ✅ W17 不再独立——依赖 W14+ 全系统就位
- ✅ W15 拆分为 3 个子 Wave（原 7 串行子任务过大）
- ✅ W16 拆分为 3 个独立任务（W16a 真独立，W16b 依赖经济，W16c 依赖特殊攻击）

---

## Wave 8: S09 + S10 + S24 + S26 Stub 修复

**仓库: `engine`** | **并行度: 1**（共享 `systems/mod.rs` + `world.rs` + `scheduler.rs`）

| 系统 | 文件 | 行数 | 修复内容 |
|------|------|:---:|---------|
| **S09** | `spawning_grace_system.rs` | 21→~50 | **写入 `SpawningGrace{remaining:1}` 到新生 drone**（当前只读/过期）。若写入已由 `spawn_system.rs` 完成则迁移 |
| **S10** | `regeneration_system.rs` | 43→~80 | **完整重写**：Entity HP 恢复（`hits++`，capped at `max_hits`，`Without<DeathMark>`）。当前 43 行实现 Source 容量再生——完全错误 |
| **S24** | `decay_system.rs` | 88→~50 | **剥离 aging 逻辑**：只保留 fatigue/cooldown 衰减。`drone.age++` 代码移至 W13 的 `aging_system.rs` |
| **S26** | `pvp_block_system.rs` | 19→~30 | **修正调度位置**：从 spawn 之前移至 death_cleanup 之后（manifest §S26）。增强安全模式到期逻辑 |

**此外**：
- 修正 `controller_repair_system.rs` 第7行注释："Drone age repair system" → "Drone body hits repair system"
- 修正 `scheduler.rs` 中 S26 的注册顺序
- 迁移 S09 SpawningGrace 写入逻辑（评估 `spawn_system.rs` 中是否已有——若有则统一）

**验收:** 每系统 ≥ 2 个测试（共 ≥ 8 个）

---

## Wave 9: S14 Special Attack Reducer + S15 Damage Application

**仓库: `engine`** | **并行度: 1**（2 个新文件 + 共享 infra）

| 文件 | `special_attack_reducer.rs` (**新建**), `damage_application_system.rs` (**新建**), `systems/mod.rs`, `scheduler.rs`, `world.rs`, `lib.rs` |
|------|------|
| 规范 | `specs/core/06-phase2b-system-manifest.md` §S14, §S15 |

> ⚠️ **注意**：绝不修改 `death_mark_system.rs`（S07 的完整实现，独立于 S15）

**实现:**
- **S14**: Intent Collect → Canonical Sort (优先级: Hack > Drain > Overload > Debilitate > Disrupt > Fortify + shuffle) → Deliver（不直接修改实体，交付 S22 `status_advance_system`）
- **S15**: PendingDamage buffer → Resistance 减伤 → DeathMark（if hits≤0）
- **排序链**: S14 (reducer) → S22 (status_advance) → S15 (damage_application)
  - ⚠️ S14 交付 S22，S22 写入 S15 的 damage buffer——三阶段管线

**验收:** ≥ 7 个测试

---

---

---

---

## Wave 13: S23 Aging + S25 Death Cleanup

**仓库: `engine`** | **并行度: 1**

| 文件 | `aging_system.rs` (**新建**), `death_cleanup_system.rs` (9→), `systems/mod.rs`, `scheduler.rs`, `world.rs`, `lib.rs`, `components.rs` (新增 Lifespan/ActiveAging) |
|------|------|
| 规范 | `specs/core/06-phase2b-system-manifest.md` §S23, §S25 |

**实现:**
- **S23 Aging**: 从 `decay_system.rs` 迁移 aging 逻辑到独立 `aging_system.rs`。Lifespan 组件 + ActiveAging（加速老化）。更新 `decay_system.rs` 移除 `drone.age++` 代码
- **S25 Death Cleanup**: 从 9 行 stub 增强为完整实现——despawn + ResourceAmount 掉落释放
- ⚠️ 新增 Lifespan/ActiveAging 组件需同步更新 manifest §S23 的 R/W 声明

**验收:** ≥ 5 个测试

---

## Wave 14: P3-8 Feedback Loop

**仓库: `engine`** | **并行度: 1**

| 文件 | `event_log.rs` (**新建**), `mcp.rs` (新增 tool), `realtime.rs` (WebSocket), `systems/mod.rs`, `scheduler.rs`, `world.rs`, `lib.rs`, `components.rs` |
|------|------|
| 规范 | `specs/gameplay/06-feedback-loop.md` |

**实现:** EventLog 组件 + `swarm_get_snapshot`/`swarm_explain_last_tick` MCP tool + WebSocket 推送 + 事件保留策略。
同时实现 `swarm_simulate`（预测性模拟，fork 隔离，RNG 命名空间隔离）和 `swarm_dry_run`（确定性试运行），参见 `specs/core/09-snapshot-contract.md` §2。
同时实现 `swarm_get_docs` / `swarm_get_available_actions` MCP tools（`06-feedback-loop.md` §2.2）。

**验收:** ≥ 6 个测试（含 simulate 隔离验证）

---

## Wave 15a: Arena Core (P4-1 + P4-3)

**仓库: `engine`** | **并行度: 1**

| 文件 | 主要 `arena.rs`（623行基础） |
|------|------|
| 规范 | `design/modes.md` §9.1.1-§9.1.3 |

| # | 任务 | 关键实现 |
|---|------|---------|
| P4-1 | Room 创建 | Create room + Configure（参数 + map + lock slots） |
| P4-3 | Match Lifecycle | Create→Configure→Ready→Play→Finish→Replay 六阶段状态机 |

**验收:** ≥ 5 个测试

---

## Wave 15b: Arena Security (P4-2 + P4-4 + P4-5)

**仓库: `engine`** | **并行度: 1**

| 文件 | `arena.rs` + `replay_storage.rs`（新建） + `tick.rs` |
|------|------|
| 规范 | `design/modes.md` §9.1.2, §9.1.4, `specs/core/05-persistence-contract.md` §2 |

| # | 任务 | 关键实现 |
|---|------|---------|
| P4-2 | WASM Precommit | Module hash lock per slot（Ready 前锁定） |
| P4-4 | Social Replay | Delayed spectator + replay URL + public_spectate 限流 |
| P4-5 | Local Replay | Deterministic replay verifier（Replay-Critical Subset） |

**验收:** replay ≥ 3 个测试

---

## Wave 15c: Arena Gameplay (P4-6 + P4-7)

**仓库: `engine`** | **并行度: 1**

| 文件 | `arena.rs` |
|------|------|
| 规范 | `design/modes.md` §9.1.5, §9.1.6 (如未创建则需先补充) |

| # | 任务 | 关键实现 |
|---|------|---------|
| P4-6 | PvE Challenge | 4 场景引擎（Guardian Gauntlet/Swarm Defense/Resource Race/Ruin Siege）+ 评分公式 + PvE 排行榜 |
| P4-7 | Arena Admin | Room 管理（list/kick/close）+ parameters 热更新 |

**验收:** ≥ 4 个测试

---

## Wave 16a: P1-6 WASM CDN 部署流

**仓库: `engine`** | **并行度: 1** | **可与任何其他 Wave 并行**

| 文件 | `wasm_deploy.rs` (**新建**), `lib.rs` |
|------|------|
| 规范 | `specs/security/09-command-source.md` §1-§3 |

**实现:** deploy→validate→commit→activate pipeline + `swarm_deploy_module` MCP tool + CodeSigningCertificate 验证。
**验收:** ≥ 3 个测试。**不依赖 Arena**。

---

## Wave 16b: P2-7 Economy Balance（依赖 W2-W6）

**仓库: `engine`** | **并行度: 1** | **依赖: W2-W6 (economy)**

| 文件 | `tests/economy_balance.rs` (**新建**, 不碰 src/) |
|------|------|
| 规范 | `design/economy-balance-sheet.md` |

1/5/20/50 rooms 维护费曲线验证。
**验收:** 曲线与 balance sheet 预测一致。

---

## Wave 16c: P1-7 CommandSource Gate（依赖 W12）

**仓库: `engine`** | **并行度: 1** | **依赖: W12 (special attack commands)**

| 文件 | `security.rs` (515行→增强), `command.rs` (集成点) |
|------|------|
| 规范 | `specs/security/09-command-source.md` §4-§8 |

`CommandSource` 枚举 + MCP-only 注入 + Ed25519 证书链 + CRL + version_counter + Session 状态机。同时实现 Safe Hint Ladder 三级错误提示模型。
**验收:** ≥ 6 个测试。

---

## Wave 17: P5 Benchmark Gates（依赖 W14 + W15c + W16c）

**仓库: `engine`** | **并行度: 7**（独立 bench 文件）| **依赖: 全系统就位**

> ⚠️ **DAG 关键修正**：Benchmark 测量完整系统链性能。W8-W14 新增系统将显著改变性能特征（30-70%）。必须在 W14+W15c+W16c 之后运行才能获得有效指标。

添加 `criterion` 依赖。所有 bench 在 `benches/` 目录。
同时实现 Capacity Admission Model（`specs/core/09-snapshot-contract.md` §7）：measured admission 动态调节，基于 p95/p99 指标计算 admitted_players。

| ID | 文件 | 指标 |
|----|------|------|
| P5-1 | `benches/command_loop.rs` | 100k validate p99<50ms, apply<100ms |
| P5-2 | `benches/snapshot_bench.rs` | 50k entities clone<20ms, restore<30ms |
| P5-3 | `benches/fdb_bench.rs` | 500 players p99<200ms, conflict<1% |
| P5-4 | `benches/room_partition.rs` | 1000 players, 200 rooms, p99<500ms |
| P5-5 | `benches/pathfinding.rs` | 50×50 A*, 100 concurrent ops |
| P5-6 | `benches/rollback_snapshot.rs` | 500 entities 全组件, p99<50ms (**需迁移到 benches/ 目录**) |
| P5-7 | `benches/load_test.rs` | 1000 players, 200 rooms, p99<500ms |
| P5-8 | `benches/snapshot_stitch.rs` | 1000 × 256KB snapshots, p99<100ms |

**验收:** `cargo bench` 全部通过，P5-1/P5-3/P5-7/P5-8 p99 达标。

---

## 遗漏项（审计发现，非 Manifest 但 Spec 要求）

| # | 项目 | Spec 来源 | 处置 | 计划 |
|---|------|----------|------|------|
| G1 | controller_repair 注释修正 | — | 代码正确(修复 body hits)，注释错误 | W8 随带修复 |
| G2 | `swarm_get_docs` / `swarm_get_available_actions` MCP | `06-feedback-loop.md` §2.2 | 未在任何 Wave | 并入 W14 |
| G3 | Tutorial 5 分钟引导覆盖 | `06-feedback-loop.md` §2.1 | 代码存在但未实现引导层 | 并入 W14 |
| G4 | NPC 使用特殊攻击 | manifest §S16-S22 (敌交互) | `npc/ai.rs` 未集成特殊攻击系统 | W11-W12 后追加 |
| G5 | Mod 仓库同步（系统变更时更新 mod.toml config keys） | W0 | W0 创建后未维护 | 每 Wave 完成后检查 |
| G6 | S29 per-tick ECS 系统注册 | manifest §S29 | `resource_ledger.rs` 库代码完整但未在 world.rs 注册 | 创建独立任务，随 W14 一起做 |
| G7 | Capacity Admission Model | `09-snapshot-contract.md` §7 | 提及但无实现任务 | 并入 W17 |

---

## Milestones

| Milestone | 判定 | 依赖 Wave |
|-----------|------|:----:|
| **M0: Mod Ready** | ✅ | W0 |
| **M1: Core Complete** | Snapshot + Simulate/Dry-Run | W1, W14 |
| **M2: Economy** | P2-1..P2-8 + Balance test | W2-W6, W16b |
| **M3: Combat Foundation** | S09,S10,S14,S15,S24,S26 stub 修复 + Combat | W7-W9 |
| **M4: Gameplay Systems** | Status Effects + Aging + Body Part + Feedback | W10-W14 |
| **M5: Arena** | P4-1..P4-7（3 子 Wave） | W15a-W15c |
| **M6: Production Ready** | Source Gate + CDN + Benchmarks + Capacity Admission | W16a-W17 |
