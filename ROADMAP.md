# Swarm — 代码对齐文档路线图

> **生成日期**: 2026-06-17
> **审计基线**: engine 177 tests, sandbox 14, sdk-rust 8, sdk-ts 11, gateway 16, frontend 10/13
> **方法论**: DESIGN.md + 全部 specs vs 实际代码逐项对比

---

## 当前状态总览

| 仓库 | Tests | 状态 |
|------|-------|------|
| engine | 177 ✓ | 核心引擎功能完善 |
| sandbox | 14 ✓ | WASM 沙箱完整 |
| sdk-rust | 8 ✓ | Rust SDK |
| sdk-ts | 11 ✓ | TypeScript SDK |
| gateway | 16 ✓ | Go 网关 (NATS relay + WS) |
| frontend | 10/13 (3 fail) | React 测试需修复 |

**已实现的 Tier 1 核心**:
- 16 CommandAction 变体 ✓
- 8 body parts ✓
- 13 structure types ✓
- 18-system ECS chain ✓
- 28 MCP tools ✓
- World Config (完整 TOML schema) ✓
- Special Effect framework + 4 effects ✓
- Custom Action framework + 2 actions ✓
- Replay Storage, Sim, Shard, Arena, Visibility, Source Gate, Rhai, Tutorial, Security, Onboarding, Ranking, NATS realtime, Dragonfly, FDB, Mod CLI ✓
- Progressive storage tax ✓
- Controller + Depot repair ✓
- BodyPart age_modifier ✓

---

## 设计与实现差距

以下差距按严重程度排列。G 前缀 = DESIGN 缺口，S 前缀 = spec 对齐缺口。

### 🔴 G1: PvE / NPC 生态层 — 完全缺失

**DESIGN 要求**: `design/modes.md` §9.0 定义了完整的 World PvE 生态层

| 缺失项 | DESIGN 描述 | 代码现状 |
|--------|-----------|---------|
| NPC 实体 (Creep, Guardian, Merchant, Swarmling) | 4 种 NPC，各有 HP/伤害/行为/刷新周期/掉落 | 0 行代码，`grep creep\|guardian\|merchant\|swarmling\|NPC` → 0 匹配 |
| 资源据点 (Rich Vein, Ancient Ruins, Energy Spring) | 3 种据点，守卫 + 产出 | 0 行代码 |
| 世界事件 (Swarm Invasion, Resource Boom, Ruin Awakening, Merchant Arrival) | 4 种事件，概率触发，确定性 seed | 0 行代码 |
| NPC 掉落经济 (Energy, Crystal, Blueprint, Wreckage) | 掉落表 + 蓝图系统 | 0 行代码 |
| 难度梯度 (Zone 1-4) | 距中心越远 NPC 越强 | 0 行代码 |
| PvE 经济约束 (`max_pve_output_per_tick`) | 全局 PvE 产出上限 | 0 行代码 |
| SpawningGrace (1 tick 无敌帧) | 防止 "出生即斩" | 0 匹配，系统不在 ECS chain 中 |

**影响**: PvE 是 World 模式的核心差异点（vs Arena）。没有 PvE，World 模式退化为纯 PvP 沙盒。

**预估工作量**: 大。约 800-1200 行 Rust（NPC 组件 + AI 系统 + 事件系统 + 掉落系统 + 据点生成 + 配置）。

---

### 🔴 G2: Special Effects 不完整 — 4/8

**DESIGN 要求**: `design/gameplay.md` + `design/engine.md` Tier Entry Gate 表

| 效果 | Tier | 代码状态 |
|------|------|---------|
| Hack | Tier 1 ✅ | ✅ 已实现 |
| Drain | Tier 1 ✅ | ✅ 已实现 |
| Overload | Tier 1 ✅ | ✅ 已实现 |
| Debilitate | Tier 1 ✅ | ✅ 已实现 |
| **Disrupt** | **Tier 1 ✅** | ❌ **缺失** |
| **Fortify** | **Tier 1 ✅** | ❌ **缺失** (仅在 CustomAction 中存在) |
| Leech | Tier 2 | ❌ 缺失 |
| Fabricate | Tier 2 | ❌ 缺失 |

**影响**: Disrupt 和 Fortify 是 Tier 1 冻结项，应在 MVP 中可用。

**预估工作量**: 小。Disrupt + Fortify 各约 40-60 行 handler。

---

### 🔴 G3: Custom Actions 不完整 — 2/6 Tier 1

**DESIGN 要求**: Tier Entry Gate 表说 Tier 1 冻结 6 种特殊攻击

| Action | Tier | 代码状态 |
|--------|------|---------|
| Debilitate | Tier 1 ✅ | ✅ CustomActionDef |
| Fortify | Tier 1 ✅ | ✅ CustomActionDef |
| **Disrupt** | **Tier 1 ✅** | ❌ 缺失 |
| **Hack** | **Tier 1 ✅** | ❌ 缺失 |
| **Drain** | **Tier 1 ✅** | ❌ 缺失 |
| **Overload** | **Tier 1 ✅** | ❌ 缺失 |
| Leech | Tier 2 | ❌ 缺失 |
| Fabricate | Tier 2 | ❌ 缺失 |

注: Hack/Drain/Overload 作为 SpecialEffect 已实现，但未注册为 CustomAction（玩家可通过 `CommandAction::Custom` 调用的独立入口）。

**影响**: 玩家无法通过 `CommandAction::Custom("Hack")` 等调用这些特殊攻击。

**预估工作量**: 小。4 个 CustomActionDef 注册，每个约 20 行。

---

### 🟡 G4: SpawningGrace 系统缺失

**DESIGN 要求**: `design/engine.md` 明确列出 `spawning_grace_system` 在 Phase 2b ECS chain 中，位于 spawn_system 之后、combat 之前，为新 drone 附加 1 tick 无敌帧。

**代码现状**: `grep SpawningGrace\|spawning_grace` → **0 匹配**。ECS chain 中无此系统。

**影响**: 新 drone 可被对手在出生 tick 秒杀（"出生即斩"）。DESIGN 明确将此列为 anti-frustration 机制。

**预估工作量**: 小。约 60-80 行（SpawningGrace 组件 + system + 注册到 chain 的 spawn_system 之后）。

---

### 🟡 G5: active_aging / idle_aging 未区分

**DESIGN 要求**: `design/gameplay.md` §8.2 — idle drone 100% 衰老，active drone 110% 衰老（防止挂机囤兵）。

**代码现状**: `decay_system` 对全部 drone 同速率加 age。无 active/idle 区分逻辑。

**影响**: 玩家可挂机囤兵无惩罚。

**预估工作量**: 小。需在 Drone 组件添加 `last_action_tick` 字段，decay_system 中判断。

---

### 🟡 G6: Controller age 恢复硬上限

**DESIGN 要求**: `design/gameplay.md` §8.2 — "Controller 续期硬上限：无论拥有多少个 Controller，每 tick 总 age 回退不超过自然增长（+1/tick）的 50%"

**代码现状**: `controller_repair_system` 存在，但需验证是否实现了 50% 硬上限。`repair_per_drone` 字段存在，但未见跨 Controller 的全局 age 回退上限逻辑。

**影响**: 玩家可通过堆叠多个 Controller 实现永久 drone，削弱 lifespan 核心约束。

**预估工作量**: 小。在 controller_repair_system 或 decay_system 中添加全局计数器。

---

### 🟡 G7: MIN_LIFESPAN 未实现

**DESIGN 要求**: `design/gameplay.md` §8.2 — `age_max = max(MIN_LIFESPAN, BASE_AGE + sum(age_modifier))`，MIN_LIFESPAN 默认 100 tick，world.toml 可配置。

**代码现状**: `Drone.lifespan` 字段存在，body part `age_modifier` 字段存在，但无 `MIN_LIFESPAN` 常量和下限保护。

**影响**: body part 配置可能产生负数 lifespan 的 drone。

**预估工作量**: 极小。添加常量 + spawn 时 clamp。

---

### 🟡 G8: DamageType 系统不完整

**DESIGN 要求**: `design/gameplay.md` 提到 `[[damage_types]]` 可配置，含 attribute_multipliers 和 component_multipliers。

**代码现状**: 只有 3 种: Kinetic, Thermal, EMP。`DamageTypeDef` 结构有 `attribute_multipliers` 字段但无 `component_multipliers`。

**影响**: 无法配置完整的伤害类型矩阵。

**预估工作量**: 小。扩展 DamageTypeDef，添加默认类型（Corrosive, Psionic, etc.）。

---

### 🟡 G9: Recycle 退还比例

**DESIGN 要求**: `design/gameplay.md` §8.2 — 标准世界 50% 退还，Tutorial 世界 100% 退还。

**代码现状**: Recycle 命令存在但需验证退还比例是否正确实现。

**预估工作量**: 极小。常量 + 条件分支。

---

### 🟠 G10: Room 拓扑 — 出口/地形生成

**DESIGN 要求**: `design/engine.md` §3.1a 定义了完整 room 模型、出口配对、地形确定性生成。

**代码现状**: RoomName 坐标系统存在。但物理出口、房间间穿越、地形生成需要检查完整性。

**预估工作量**: 中。需确认是否需要补充。

---

### 🟠 G11: Frontend 测试修复

**现状**: 3 个 React 测试失败（`render` 和 `waitFor` 相关）。

**预估工作量**: 小。React 测试配置修复。

---

### 🟠 G12: ClickHouse 集成

**DESIGN 要求**: 分析数据（聚合查询、排行榜、审计）存储于 ClickHouse。

**代码现状**: `clickhouse.rs` 仅 52 行 stub。

**预估工作量**: 中。取决于是否需要实际集成。

---

## Spec 对齐缺口

### S1: specs/core/01 中的 SpawningGrace、active_aging、room exits

spec 01 描述了完整的 Phase 2b 系统链（含 spawning_grace_system），以及 room topology（出口、坐标系）。代码缺失 spawning_grace_system，active_aging 逻辑，room exits 待验证。

### S2: specs/core/02 中的 RejectionReason 完整性

spec 02 定义了完整的 RejectionReason 表格。需验证代码中所有 reason 都已实现。

### S3: specs/security/05 中的可见性模式

spec 05 定义了 fog_of_war, player_view (Drone/Full/Allied), spectate, replay_privacy。VisibilityConfig 已含这些字段但需验证系统行为。

### S4: specs/reference/commands.md 对齐

需验证 commands.md 中的 CommandAction 列表与代码 enum 完全一致。

### S5: specs/reference/mcp-tools.md 对齐

需验证列出的 MCP 工具与 `mcp_tool_infos()` 注册一致。

---

## 实现路线图

按优先级排列的下一阶段任务：

### Phase A: 核心缺口修复 (预计 4-6 小时)

| ID | 任务 | 仓库 | 预估 |
|----|------|------|------|
| G4 | SpawningGrace 系统 | engine | 60-80 行 |
| G7 | MIN_LIFESPAN 下限保护 | engine | 10 行 |
| G5 | active_aging / idle_aging 区分 | engine | 50 行 |
| G6 | Controller age 恢复 50% 硬上限 | engine | 40 行 |
| G9 | Recycle 退还比例 | engine | 20 行 |
| G2a | Disrupt + Fortify SpecialEffect handlers | engine | 100 行 |
| G3a | Hack/Drain/Overload/Disrupt CustomAction 注册 | engine | 80 行 |
| G8 | DamageType 扩展 (component_multipliers) | engine | 60 行 |
| G11 | Frontend 测试修复 | frontend | 30 行 |

### Phase B: PvE 生态层 (预计 12-20 小时)

| ID | 任务 | 仓库 | 预估 |
|----|------|------|------|
| G1a | NPC 组件 + ECS entities (Creep, Guardian, Merchant, Swarmling) | engine | 300 行 |
| G1b | NPC AI 行为系统 (巡逻/驻守/跨房间移动) | engine | 300 行 |
| G1c | 资源据点生成 + 守卫配置 | engine | 200 行 |
| G1d | 世界事件系统 (概率触发 + 确定性 seed) | engine | 250 行 |
| G1e | NPC 掉落经济 + 蓝图系统 | engine | 200 行 |
| G1f | 难度梯度 (Zone 1-4 按距离分布 NPC) | engine | 100 行 |
| G1g | PvE 经济约束 (max_pve_output_per_tick) | engine | 50 行 |

### Phase C: 文档对齐 (预计 2-4 小时)

| ID | 任务 | 仓库 | 预估 |
|----|------|------|------|
| S1 | 更新 spec 01 反映实际系统链 | docs | 编辑 |
| S2 | 审计 RejectionReason 完整性 | engine+docs | 审计 |
| S4 | commands.md ↔ CommandAction enum 对齐 | docs | 编辑 |
| S5 | mcp-tools.md ↔ mcp_tool_infos() 对齐 | docs | 编辑 |
| S3 | 可见性系统行为验证 | engine | 审计 |

### Phase D: Tier 2 扩展 (按需)

| ID | 任务 | 仓库 | 预估 |
|----|------|------|------|
| G2b | Leech + Fabricate SpecialEffect | engine | 100 行 |
| G3b | Leech + Fabricate CustomAction | engine | 40 行 |
| G12 | ClickHouse 集成 | engine | 300 行 |
| G10 | Room 出口物理实现 | engine | 200+ 行 |

---

## 任务分解说明

以上 G 和 S 前缀的 ID 对应具体的可执行任务。每个任务应作为独立的 kanban task 创建，包含:
- 明确的 spec 锚点（如 `design/gameplay.md §8.2`, `specs/core/01 §2`）
- 验证标准（`cargo test`, grep 确认）
- git merge-to-main 流程

Phase A 的任务相互独立，可以并行执行。
Phase B 的任务有依赖关系（组件 → AI → 事件 → 掉落），但 G1a+G1f 可并行，G1b+G1c 可并行。
