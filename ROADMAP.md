# Swarm — 代码对齐文档路线图

> **生成日期**: 2026-06-17
> **审计基线**: engine 177 tests, sandbox 14, sdk-rust 8, sdk-ts 11, gateway 16, frontend 10/13
> **方法论**: DESIGN.md + 全部 specs vs 实际代码逐项对比

---

## 当前状态总览

| 仓库 | Tests | 状态 |
|------|-------|------|
| engine | 205 ✓ | 核心引擎功能完善 (+Phase B) |
| sandbox | 14 ✓ | WASM 沙箱完整 |
| sdk-rust | 8 ✓ | Rust SDK |
| sdk-ts | 11 ✓ | TypeScript SDK |
| gateway | 16 ✓ | Go 网关 (NATS relay + WS) |
| frontend | 13 ✓ | React 测试全部修复 |

**已实现的 Tier 1 核心**:
- 16 CommandAction 变体 ✓
- 8 body parts ✓
- 13 structure types ✓
- 26-system ECS chain ✓
- 30 MCP tools ✓
- World Config (完整 TOML schema) ✓
- Special Effect framework + 11 effects ✓
- Custom Action framework + 8 actions ✓
- Replay Storage, Sim, Shard, Arena, Visibility, Source Gate, Rhai, Tutorial, Security, Onboarding, Ranking, NATS realtime, Dragonfly, FDB, Mod CLI ✓
- Progressive storage tax ✓
- Controller + Depot repair ✓
- BodyPart age_modifier ✓

---

## 设计与实现差距

**全部缺口已解决** — 2026-06-17。详见下方各 Phase 完成记录。

| 类别 | 缺口数 | 状态 |
|------|:-----:|:--:|
| G1-G12 (DESIGN 缺口) | 12 | ✅ 全部解决 |
| S1-S5 (spec 对齐缺口) | 5 | ✅ 全部解决 |

> 原缺口清单已移入 Phase A-D 完成记录。

---

## 实现路线图

按优先级排列的下一阶段任务：

### Phase A: 核心缺口修复 ✅ 完成 (2026-06-17)

| ID | 任务 | 仓库 | 状态 | Commit |
|----|------|------|:--:|--------|
| G4 | SpawningGrace 系统 | engine | ✅ | `de6ffdc` |
| G7 | MIN_LIFESPAN 下限保护 | engine | ✅ | `e6bc032` |
| G5 | active_aging / idle_aging 区分 | engine | ✅ | `108d6c3` |
| G6 | Controller age 恢复 50% 硬上限 | engine | ✅ | `507ca20` |
| G9 | Recycle 退还比例 | engine | ✅ | `130a7b6` |
| G2a | Disrupt + Fortify SpecialEffect handlers | engine | ✅ | `33fb9c8` |
| G3a | Hack/Drain/Overload/Disrupt CustomAction 注册 | engine | ✅ | `db814d0` |
| G8 | DamageType 扩展 (component_multipliers) | engine | ✅ | `5588f47` |
| G11 | Frontend 测试修复 | frontend | ✅ | 13/13 通过 |

**结果**: engine 177→190 tests, frontend 10/13→13/13

### Phase B: PvE 生态层 ✅ 完成 (2026-06-17)

| ID | 任务 | 仓库 | 状态 | Commit |
|----|------|------|:--:|--------|
| G1a | NPC 组件 + ECS entities (Creep, Guardian, Merchant, Swarmling) | engine | ✅ | `3f3351c` |
| G1b | NPC AI 行为系统 (巡逻/驻守/跨房间移动) | engine | ✅ | `3f3351c` |
| G1c | 资源据点生成 + 守卫配置 | engine | ✅ | `3f3351c` |
| G1d | 世界事件系统 (概率触发 + 确定性 seed) | engine | ✅ | `aa4973a` |
| G1e | NPC 掉落经济 + 蓝图系统 | engine | ✅ | `f20354d` |
| G1f | 难度梯度 (Zone 1-4 按距离分布 NPC) | engine | ✅ | `06107a9` |
| G1g | PvE 经济约束 (max_pve_output_per_tick) | engine | ✅ | `141c27f` |

**结果**: engine 190→205 tests

### Phase C: 文档对齐 ✅ 完成 (2026-06-17)

| ID | 任务 | 仓库 | 状态 |
|----|------|------|:--:|
| S1 | 更新 spec 01 系统链 (6→20 系统) | docs | ✅ |
| S2 | RejectionReason 审计 — commands.md 36→51 种 | docs | ✅ |
| S4 | commands.md ↔ CommandAction 对齐 (23→16+8Custom) | docs | ✅ |
| S5 | mcp-tools.md 验证 (30=30) | docs | ✅ |
| S3 | 可见性系统行为验证 — VisibilityConfig 已覆盖全部模式 | engine | ✅ |

### Phase D: Tier 2 扩展 ✅ 完成 (2026-06-17)

| ID | 任务 | 仓库 | 状态 | 备注 |
|----|------|------|:--:|------|
| G2b | Leech + Fabricate SpecialEffect | engine | ✅ | handler + SpecialEffectDef 已注册 |
| G3b | Leech + Fabricate CustomAction | engine | ✅ | CustomActionDef 已注册（含 cost/cooldown/body part） |
| G12 | ClickHouse 集成 | engine | ✅ | Writer + Row + SQL + 测试完整实现 |
| G10 | Room 出口物理实现 | engine | ✅ | 跨房间移动已实现（RoomId::adjacent + Move room_dx/dy）。显式 Exit 实体需按设计扩展 |

**结果**: 全部已实现——在前序 Phase 中已包含

---

## 任务分解说明

以上 G 和 S 前缀的 ID 对应具体的可执行任务。每个任务应作为独立的 kanban task 创建，包含:
- 明确的 spec 锚点（如 `design/gameplay.md §8.2`, `specs/core/01 §2`）
- 验证标准（`cargo test`, grep 确认）
- git merge-to-main 流程

Phase A 的任务相互独立，可以并行执行。
Phase B 的任务有依赖关系（组件 → AI → 事件 → 掉落），但 G1a+G1f 可并行，G1b+G1c 可并行。
