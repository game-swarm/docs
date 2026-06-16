# Swarm — 实现差距追踪

> 审计日期: 2026-06-16。全量 DESIGN + 9 specs vs 代码审计。
> 测试总数: engine:159, sandbox:14, sdk-rust:8, sdk-ts:11, gateway:9, frontend:13

## 总览

| 模块 | 仓库 | 状态 |
|------|------|------|
| engine | `engine/` | 10 缺口 |
| sandbox | `sandbox/` | ✅ 完成 |
| gateway | `gateway/` | ✅ 完成 |
| frontend | `frontend/` | ✅ 完成 |
| **总计** | | **13 缺口** |

---

## 🔴 P0 — 核心游戏循环完整性

### G5b: Depot 维修系统 — DESIGN §8.2 ✅

**当前状态**: 已完成——`depot_repair_system` 实现，结合 Controller 共享 `RepairTracker` 硬上限。

- [x] 实现 `depot_repair_system`: 查询范围内 Depot，消耗 maintenance 资源（Structure.energy），降低 drone age
- [x] Controller 维修硬上限已扩展——Controller + Depot 通过 `RepairTracker` 共享 hard_cap，合计 age 回退 ≤ 自然增长 50%
- [x] maintenance 耗尽时 Depot 停止维修（energy < maintenance_cost 时跳过）
- 3 tests: 范围内维修、能量耗尽、玩家归属过滤

### G8a+G8b: BodyPart age_modifier + Drone lifespan — DESIGN §8.2 ✅

**当前状态**: 已完成——`BodyPartTypeDef` 含 `age_modifier: i32`，`Drone::new()` 聚合计算 lifespan。

- [x] `BodyPartTypeDef` 新增 `age_modifier: i32` 字段，默认 0
- [x] `BodyPartRegistry::default()` 设置: Tough=+100, Attack=-80, RangedAttack=-50, Heal=-30, Claim=-50, Move/Work/Carry=0
- [x] world.toml 解析 `[[body_part_types]]` 通过 `#[serde(default)]` 自动支持
- [x] `Drone::new(owner, body, &BodyPartRegistry)` 计算 `lifespan = DEFAULT_DRONE_LIFESPAN + sum(age_modifier)`
- [x] `spawn_system` 接收 `Res<BodyPartRegistry>`，`spawn_drone_in_room` 传入
- 1 test: `drone_lifespan_includes_age_modifiers` (4 scenarios)

---

## 🟡 P1 — MCP + 校验管线

### G13: swarm_list_modules 真实现有 — DESIGN §4.1

**当前状态**: `swarm_list_modules()` 返回硬编码 stub。

- [ ] 实现真实模块查询——从 sandbox/engine 模块注册表获取已部署 WASM 列表

### G14: swarm_get_replay 真实实现 — DESIGN §4.1

**当前状态**: `swarm_get_replay()` 返回占位消息。

- [ ] 利用 `ReplayStorageConfig` + `KeyframeData` + `WorldDelta` 实现真实 replay 查询

### S2: 缺失 RejectionReason 变体 — specs/02 §3.10-3.13

**当前状态**: `RejectionReason` enum 缺 5 个 spec 声明的变体。特殊攻击的校验绕过标准管线（用 custom action 路径替代 RejectionReason）。

spec 要求但代码未实现:
- `AlreadyHacked` — Hack 目标已被他人 Hack 中
- `InvalidDamageType` — Debilitate 的 damage_type 不在 DamageType 枚举中
- `AlreadyDebilitated(damage_type)` — 目标已有同类型 Debilitate
- `PlayerNotFound` — Overload 的 target_id 不是有效玩家
- `TargetFuelTooLow` — Overload 目标 fuel 低于下限

- [ ] 在 `RejectionReason` enum 新增 5 个变体
- [ ] 在对应的特殊攻击校验路径中返回这些 RejectionReason

### S1: COLLECT 结果跨 FDB 重试缓存 — specs/01 §3.5

**当前状态**: FDB commit 失败重试时重新执行 WASM COLLECT（重复扣 fuel），spec 要求复用首次 COLLECT 结果。

- [ ] 首次 COLLECT 后缓存 `Map<PlayerId, Vec<ValidatedCommand>>` + fuel 扣费明细
- [ ] FDB commit 失败重试跳过 COLLECT，使用缓存
- [ ] 跨重试 fuel 消耗上限 = `1 × MAX_FUEL`

---

## 🟢 P2 — 规则系统 Stub + MVP 工具

### S7a: code_propagation_system 空实现 — specs/07 §3

**当前状态**: `fn code_propagation_system() {}` — 函数体为空。WorldConfig 解析完整但系统未实现。

- [ ] 实现代码传播逻辑：按 `propagation_speed` 每 tick 传播 N 格
- [ ] 支持 `propagation_source` (Spawn/Controller/AnyDrone)

### S7b: memory_upkeep_system 未注册 — specs/07 §3

**当前状态**: `DroneConfig.memory_upkeep_cost` 配置存在，但 `memory_upkeep_system` 未实现/未注册。

- [ ] 实现 memory_upkeep_system: 按 `memory_upkeep_cost` 扣除维护费
- [ ] 注册到 ECS pipeline

### S7c: drone_env_var_system 未实现 — specs/07 §3

**当前状态**: `DroneConfig.env_vars` 配置存在，但系统未实现。

- [ ] 实现 drone_env_var_system: 允许 WASM 模块读写 drone 环境变量

### S7d: pvp_block_system 未实现 — specs/07 §3

**当前状态**: `CombatConfig.pvp_enabled` 配置存在（默认 true），但 `pvp_block_system` 未实现。

- [ ] 实现 pvp_block_system: 当 `pvp_enabled=false` 时阻止所有敌对操作

### S6a: 本地模拟 CLI — specs/06 §3.3 ✅

**当前状态**: 已完成——`swarm sim --ticks=N --speed=N` CLI 已实现，使用 `sim` 模块。

- [x] 实现 `swarm sim --ticks=N --speed=N` CLI（engine 子命令 `sim`，通过 `create_local_simulation_world` 创建本地世界）
- [x] MCP `swarm_simulate` 工具已存在；本地 sim 模块通过 `lib.rs` 注册为公共 API

### S6b: Tutorial 引导系统 — specs/06 §2.1

**当前状态**: `WorldMode::Tutorial` + `CommandSource::Tutorial` 存在，但无引导覆盖层/教程 bot/分步指导。

- [ ] 实现 Tutorial 世界引导覆盖层（前端 overlay）
- [ ] 教程 bot 自动运行+可编辑
- [ ] 分步指导：spawn drone → collect → build tower → deploy

---

## 已对齐 ✓

| Spec | 状态 |
|------|------|
| specs/01 | ✅ 核心 tick 协议完整（除 COLLECT 缓存） |
| specs/02 | ✅ 指令管线完整（除 5 个 RejectionReason） |
| specs/03 | ✅ MCP 工具 + OAuth2 + 限流全部对齐 |
| specs/04 | ✅ WASM 沙箱（Wasmtime/seccomp/cgroup/WASI）完整对齐 |
| specs/05 | ✅ 可见性（is_visible_to/fog/player_view/replay_privacy）完整对齐 |
| specs/06 | ✅ 回放查看器 + 策略仪表盘已实现（除 Tutorial + sim CLI） |
| specs/07 | ✅ world.toml 解析 + 资源系统 + 模组加载完整（除 4 个 stub system） |
| specs/08 | ✅ IDL CommandAction/BodyPart/DamageType/Direction 枚举完整对齐 |
| specs/09 | ✅ CommandSource + SourceGate + Auth Context 完整对齐 |

---

## 实现优先级

| 优先级 | 缺口 | 理由 |
|--------|------|------|
| 🟡 P1 | G13, G14 | MCP stub→真实——AI 玩家模块管理和回放 |
| 🟡 P1 | S2, S1 | 校验管线完整性 + tick 重试正确性 |
| 🟢 P2 | S7a-S7d | 规则系统 stub 补完 |
| 🟢 P2 | S6b | MVP 工具（Tutorial） |
