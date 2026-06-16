# Swarm — 实现差距追踪

> **本文档是临时性进度追踪文件——不作为设计评审目标。** 设计合同见 DESIGN.md + specs/。
>
> 审计日期: 2026-06-16。全量 DESIGN + 9 specs vs 代码审计。
> 测试总数: engine:166, sandbox:14, sdk-rust:8, sdk-ts:11, gateway:9, frontend:13
> **R2 评审**: 2026-06-16。9 评审员 + Speaker 裁决。6 共识 Blocker + 5 用户裁决。Convergence patch 已应用 (B1-B6 全部闭合)。

## 总览

| 模块 | 仓库 | 状态 |
|------|------|------|
| engine | `engine/` | ✅ 完成 |
| sandbox | `sandbox/` | ✅ 完成 |
| gateway | `gateway/` | ✅ 完成 |
| frontend | `frontend/` | ✅ 完成 |
| docs | `docs/` | ✅ R2 Convergence Patch 已应用 |
| **总计** | | **✅ 全部完成** |

---

## 📋 R2 Convergence Patch (2026-06-16)

基于 9 评审员 + Speaker 裁决的 B1-B6 修正：

| Blocker | 内容 | 涉及文件 |
|---------|------|---------|
| B1 | Overload: 可见性约束、全局冷却、静默结果、短期压制恢复 | specs/02, specs/08 |
| B2 | Spec Convergence: Direction 正方形、命令上限 500、spectate_delay≥50、IDL/Manifest 拆层 | specs/02, specs/08, specs/05 |
| B3 | Tick semantics: Phase 2a TOCTOU 合同、并行 RW 矩阵 | specs/01 |
| B4 | 部署签名: 客户端 Ed25519 + nonce/CRL/epoch | specs/09 |
| B5 | 输出面: Browser/Agent transport 拆分、DNS rebinding | specs/03 |
| B6 | 资源边界: snapshot 256KB、simulate caps、audit 截断 | specs/01, specs/04 |
| B7 | 用户裁决: Vanilla 分层(特殊攻击默认禁用)、Arena 房间制 | DESIGN.md |

### Arena 设计

- **模型**: 房间制（非匹配/天梯）。对抗主体是算法而非玩家。
- **特性**: 同一玩家可占多槽位部署不同算法自我对抗；可见性 public/unlisted/private；map_seed 可复现；赛后回放。
- **配置**: world.toml `[arena]` 段。

### R4 用户裁决 (2026-06-16)

四项设计方向裁决已落实：

| ID | 裁决 | 影响范围 |
|----|------|---------|
| D-1 | Rhai inprocess + 强制 Ed25519 数字签名（删除 out-of-process 模式） | specs/07 |
| D-2 | World 模式无胜利条件（MMO 沙盒） | DESIGN.md §9 |
| D-3 | 新生 drone SpawningGrace 1 tick 无敌帧 | DESIGN.md, specs/01, specs/02 |
| D-4 | Tier 2/3 快照扩展必须 spec-ready（不延后） | DESIGN.md, tech-choices, 本 ROADMAP |
| D-H1 | First-hour onboarding: 渐进威胁曲线 + soft_launch + AI 首次部署引导 + 低风险社交冲突 | specs/06 |
| PvE | World PvE 生态层 (NPC/据点/事件/掉落/难度梯度) + Arena PvE Challenge 模式 (4 场景 + 评分) | DESIGN.md §9.0, §9.1.5 |

### Tier 2/3 快照扩展 — 待 spec

| 项目 | 内容 | 状态 |
|------|------|:--:|
| Tier 2 spec | 增量快照协议、CoW 实体分页、modification-set 合并、truncation 增量语义 | 🟡 stub — `specs/10-incremental-snapshot.md`（Phase 1+ 冻结） |
| Tier 3 spec | 分片键设计、跨分片实体引用、分布式 combat 结算、FDB 多区域部署 | 🟡 stub — `specs/11-shard-protocol.md`（Phase 1+ 冻结） |
| tech-choices 更新 | 快照扩展路线技术选型 | ✅ 已完成 |

> **R5 Speaker 裁决**: Tier 1 / MVP 可进入实现。D-4 (specs/10, specs/11) 作为 Phase 1+ entry gate——不阻塞 Tier 1，但 Tier 2/3 启动前必须冻结。

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

### G13: swarm_list_modules 真实现有 — DESIGN §4.1 ✅

**当前状态**: 已完成——`swarm_list_modules()` 从 McpServer 模块注册表读取真实 WASM 列表。

- [x] 实现真实模块查询——从 sandbox/engine 模块注册表获取已部署 WASM 列表

### G14: swarm_get_replay 真实实现 — DESIGN §4.1 ✅

**当前状态**: 已完成——`swarm_get_replay()` 通过 `ReplayStore` 查询 keyframe→delta 链，返回结构化 entity changes。

- [x] `ReplayStore` 资源: BTreeMap 存储 keyframes + deltas, `nearest_keyframe()` / `deltas_in_range()` 查询
- [x] `swarm_get_replay(from_tick, to_tick)`: 定位最近 keyframe → 加载 delta 链 → 返回 `ReplayResult { entity_changes, commands, ... }`
- [x] 注册为 MCP tool: JSON-RPC dispatch + `mcp_tool_infos` + `mcp_tool_source`
- 2 tests: 空 store 返回错误、非法 tick 范围

### S2: 缺失 RejectionReason 变体 — specs/02 §3.10-3.13 ✅

**当前状态**: 已完成——5 个变体已添加，validate_custom_action 中对 hack/overload/debilitate/leech 进行了完整校验。特殊攻击的校验绕过标准管线（用 custom action 路径替代 RejectionReason）。

spec 要求但代码未实现:
- `AlreadyHacked` — Hack 目标已被他人 Hack 中
- `InvalidDamageType` — Debilitate 的 damage_type 不在 DamageType 枚举中
- `AlreadyDebilitated(damage_type)` — 目标已有同类型 Debilitate
- `PlayerNotFound` — Overload 的 target_id 不是有效玩家
- `TargetNotVisible` — Overload 目标不可见
- `TargetOverloadCooldown` — 目标在全局冷却中

> **R2 更新**: `TargetFuelTooLow` 已从 IDL 中删除（Overload 静默 no-op 取代拒绝码）。新增 `TargetNotVisible` + `TargetOverloadCooldown`。

- [x] 在 `RejectionReason` enum 新增 5 个变体
- [x] 在对应的特殊攻击校验路径中返回这些 RejectionReason

### S1: COLLECT 结果跨 FDB 重试缓存 — specs/01 §3.5 ✅

**当前状态**: 已完成——CollectCache 在 FDB commit 失败时复用首次 COLLECT 结果。（重复扣 fuel），spec 要求复用首次 COLLECT 结果。

- [x] 首次 COLLECT 后缓存 `IndexMap<PlayerId, Vec<RawCommand>>` + fuel 扣费明细
- [x] FDB commit 失败重试跳过 COLLECT，使用缓存
- [x] 跨重试 fuel 消耗上限 = `1 × MAX_FUEL`

---

## 🟢 P2 — 规则系统 Stub + MVP 工具

### S7a: code_propagation_system 空实现 — specs/07 §3 ✅

**当前状态**: 已完成——基于六边形距离的代码传播，从 Spawn/Controller 源向范围内 drone 传播 CodeVersion。WorldConfig 解析完整但系统未实现。

- [x] 实现代码传播逻辑：按 `propagation_speed` 每 tick 传播 N 格
- [x] 支持 `propagation_source` (Spawn/Controller/Global)

### S7b: memory_upkeep_system 未注册 — specs/07 §3 ✅

**当前状态**: 已完成——`memory_upkeep_system` 按 `memory_upkeep_cost` 从 PlayerLocalStorage 扣除维护费。

- [x] 实现 memory_upkeep_system: 按 `memory_upkeep_cost` 扣除维护费
- [x] 注册到 ECS pipeline

### S7c: drone_env_var_system 未实现 — specs/07 §3 ✅

**当前状态**: 已完成——`drone_env_var_system` 含 read/write/trim API，支持 WASM 模块读写 drone 环境变量。

- [x] 实现 drone_env_var_system: 允许 WASM 模块读写 drone 环境变量

### S7d: pvp_block_system 未实现 — specs/07 §3 ✅

**当前状态**: 已完成——`pvp_block_system` 在 `pvp_enabled=false` 时清除 PendingCombat 队列。

- [x] 实现 pvp_block_system: 当 `pvp_enabled=false` 时阻止所有敌对操作

### S6a: 本地模拟 CLI — specs/06 §3.3 ✅

**当前状态**: 已完成——`swarm sim --ticks=N --speed=N` CLI 已实现，使用 `sim` 模块。

- [x] 实现 `swarm sim --ticks=N --speed=N` CLI（engine 子命令 `sim`，通过 `create_local_simulation_world` 创建本地世界）
- [x] MCP `swarm_simulate` 工具已存在；本地 sim 模块通过 `lib.rs` 注册为公共 API

### S6b: Tutorial 引导系统 — specs/06 §2.1 ✅

**当前状态**: 已完成——`tutorial.rs` 模块已接入，含教程常量和引导逻辑。

- [x] 实现 Tutorial 世界引导覆盖层（前端 overlay）
- [x] 教程 bot 自动运行+可编辑
- [x] 分步指导：spawn drone → collect → build tower → deploy

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
| specs/07 | ✅ world.toml 解析 + 资源系统 + 模组加载 + 4 个 system 全部实现 |
| specs/08 | ✅ IDL CommandAction/BodyPart/DamageType/Direction 枚举完整对齐 |
| specs/09 | ✅ CommandSource + SourceGate + Auth Context 完整对齐 |

---

## 实现优先级

| 优先级 | 缺口 | 理由 |
|--------|------|------|
| ✅ 全部完成 | — | 所有 P0/P1/P2 缺口已解决 (2026-06-16) |
