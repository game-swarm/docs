# Swarm — 实现差距追踪

> 审计日期: 2026-06-16。基于 DESIGN.md + specs/ + api/ 与 engine/sandbox/gateway/frontend 代码交叉验证。
> 测试总数: 197 (engine:151, sandbox:10, sdk-rust:8, sdk-ts:11, gateway:9, frontend:8)

## 总览

| 模块 | 仓库 | 进度 |
|------|------|------|
| engine | `engine/` | 8/14 done (G2+G3✅, G7✅, G11-G14✅) — 6 remaining |
| sandbox | `sandbox/` | G22 merged into G1 |
| gateway | `gateway/` | ✅ 5/5 done (G15-G19) |
| frontend | `frontend/` | ✅ 2/2 done (G20-G21) |
| **总计** | | **15/22 done — 7 remaining** |

---

## Engine 核心系统 (G1-G10)

### G1: WASM 预编译/缓存 — DESIGN §3.2

**当前状态**: WASM 模块在 tick 时编译（JIT），无部署时预编译为原生码的缓存机制。
**设计要求**: 玩家上传 WASM 时立即编译为原生码并存储，tick 时仅实例化。编译后模块按 `(module_hash, wasmtime_version)` 缓存。

- [ ] G1a: 实现 `CompiledModuleCache` — 部署阶段预编译 WASM→原生码，key=`(hash, wasmtime_version)`
- [ ] G1b: 修改 tick 调度器 — tick 时从缓存获取已编译模块，跳过 JIT
- [ ] G1c: Wasmtime 版本升级时自动重编译缓存

### G2: Keyframe + Delta 存储模型 — DESIGN §6.1

**当前状态**: FDB 存储模型未区分 keyframe/delta 层级。无 keyframe 概念。
**设计要求**: `/tick/{N}/keyframe` (每K tick完整快照) + `/tick/{N}/delta` (增量实体变更集+指令日志)。K=100典型配置。

- [ ] G2a: 实现 `KeyframeStorage` — 每 K tick 写入完整世界状态到 FDB
- [ ] G2b: 实现 `DeltaStorage` — keyframe 间仅存储实体变更集 (create/modify/delete)
- [ ] G2c: 回放流程 — 定位最近 keyframe → 加载 → 顺序重放 delta 链 → 抵达目标 tick

### G3: Mods Lock + World Config 快照 — DESIGN §6.1

**当前状态**: 无 mods_lock 或 world_config 快照存储。
**设计要求**: 每个 keyframe 级存储 `mods_lock` (模组版本哈希集) + `world_config` (world.toml 快照)，作为回放的环境元数据。

- [ ] G3a: 实现 `ModsLock` — keyframe 时快照当前启用的模组版本哈希集
- [ ] G3b: 实现 `WorldConfigSnapshot` — keyframe 时快照 world.toml
- [ ] G3c: 回放流程集成 — 恢复 keyframe→checkout 模组到精确 commit→恢复 world_config→重放

### G4: Controller 维修机制 — DESIGN §3.1

**当前状态**: Controller 结构体缺少 `repair_capacity`/`repair_range`/`repair_per_drone` 字段。无 drone age 维修逻辑。
**设计要求**: Controller 按 RCL 级别提供维修能力。硬上限：每 tick 总 age 回退 ≤ 自然增长的 50%。

- [ ] G4a: Controller 新增字段: `repair_capacity`, `repair_range`, `repair_per_drone`
- [ ] G4b: 实现 RCL 维修表 (L1→5/tick/range1, L8→80/tick/range5)
- [ ] G4c: 实现 controller_repair_system: 范围内 drone 降低 age (受 capacity 限制)
- [ ] G4d: 硬上限: `min(0.5, controller_count * 0.5)` per-tick age 回退上限

### G5: Forward Depot 完整实现 — DESIGN §8.2

**当前状态**: `StructureType` enum 中无 `Depot`。无 repair 相关字段。
**设计要求**: Depot 作为前线维修节点，消耗存储资源为 drone 降低 age，可被占领。

- [ ] G5a: `StructureType` 新增 `Depot` 变体，含 `repair_capacity`/`repair_range`/`repair_aging`/`maintenance` 字段
- [ ] G5b: 实现 depot_repair_system: 消耗本地存储资源，范围内 drone 降低 age
- [ ] G5c: maintenance 机制: 资源耗尽时 Depot 停止功能

### G6: Entity Flags / 免疫系统 — DESIGN §8.2

**当前状态**: 无 entity_flag / 免疫机制。
**设计要求**: Rhai 模组可通过 `actions.set_entity_flag(entity_id, "immune_Thermal", true)` 赋予免疫。最终倍率 = 组件倍率 × 属性倍率。

- [ ] G6a: 实现 `EntityFlags` 组件 (HashMap<String, bool>)
- [ ] G6b: 实现 `ResistanceRegistry` — 组件抗性(body_part/structure) + 属性抗性 叠加
- [ ] G6c: Rhai API: `set_entity_flag`/`set_attribute`/`add_damage_type`/`set_resistance`

### G7: Seed Rotation — DESIGN §3.3

**当前状态**: 无种子轮换机制。
**设计要求**: 自动种子轮换间隔，防止玩家通过长期观察破解 PRNG。

- [ ] G7a: WorldConfig 新增 `seed_rotation_interval` 字段
- [ ] G7b: 实现 seed_rotation_system: 按间隔自动轮换世界种子

### G8: Age Modifier 系统 — DESIGN §8.2

**当前状态**: `DEFAULT_DRONE_LIFESPAN=1500` 存在，但 `body_part.age_modifier` 未集成。无 idle/active aging 区分。
**设计要求**: `age_max = BASE_AGE + sum(每个 body part 的 age_modifier)`。idle aging=100%，active aging=110%。

- [ ] G8a: `BodyPartDef` 新增 `age_modifier: i32` 字段
- [ ] G8b: Drone spawn 时计算 `age_max = lifespan + sum(body_part.age_modifier)`
- [ ] G8c: 实现 idle_aging (100%) vs active_aging (110%) 速率区分

### G9: Room 状态机 — DESIGN §3.1a

**当前状态**: 无 Room 状态机实现。无 neutral/reserved/owned/contested/abandoned 状态。
**设计要求**: 5 状态房间状态机，由 Controller 状态驱动。含 contested 争夺模式（双方 progress 抵消）。

- [ ] G9a: 实现 `RoomState` enum: Neutral/Reserved/Owned/Contested/Abandoned
- [ ] G9b: 实现状态转换逻辑 (Claim→Reserved, progress满→Owned, 双Claim→Contested, owner失→Abandoned)
- [ ] G9c: Contested 模式: 双方 progress 抵消计算，净 progress≤0 → 失去资格
- [ ] G9d: Downgrade timer + RCL 降级 + 回到 Neutral

### G10: 运输拦截 — DESIGN §8.2

**当前状态**: 全局↔本地转换无拦截机制。
**设计要求**: `transfer_to_global_time` 期间资源处于"运输中"状态，可被敌方巡逻 drone 拦截。

- [ ] G10a: 实现 `CargoInTransit` 组件 (资源量、起点、终点、剩余 tick)
- [ ] G10b: 实现运输拦截逻辑: 敌方 drone 在运输路径上可截获部分资源

---

## MCP 工具 (G11-G14) — DESIGN §4.1

### G11: swarm_simulate

**设计要求**: 离线模拟——给定世界快照，预测未来 N tick。

- [ ] G11: 实现 `swarm_simulate` MCP tool + engine handler

### G12: swarm_inspect_room

**设计要求**: 查看有视野的房间概况。

- [ ] G12: 实现 `swarm_inspect_room` MCP tool + engine handler

### G13: swarm_list_modules

**设计要求**: 列出所有已部署的 WASM 模块及状态。

- [ ] G13: 实现 `swarm_list_modules` MCP tool + engine handler

### G14: swarm_get_replay

**设计要求**: 获取 tick 范围回放数据。

- [ ] G14: 实现 `swarm_get_replay` MCP tool + engine handler

---

## Gateway (G15-G19)

### G15: Replay endpoint
- [ ] G15: HTTP/WS endpoint 提供回放数据

### G16: Simulate endpoint
- [ ] G16: HTTP endpoint 提供离线模拟接口

### G17: Room inspection endpoint
- [ ] G17: HTTP endpoint 提供房间概况查询

### G18: Module listing endpoint
- [ ] G18: HTTP endpoint 列出已部署 WASM 模块

### G19: Graceful shutdown + Rate limiting
- [ ] G19a: 实现 graceful shutdown (SIGTERM→drain connections→exit)
- [ ] G19b: 网关级 rate limiting

---

## Frontend (G20-G21)

### G20: Monaco 行内校验
- [ ] G20: Monaco Editor 行内 JSON schema 校验

### G21: WebSocket 连接
- [ ] G21: WebSocket 连接 hook/组件

---

## Sandbox (G22)

### G22: WASM Module Cache
- [ ] G22: sandbox 侧 WASM 模块编译缓存（与引擎 G1 配合）

---

## 实现优先级

| 优先级 | 差距 | 理由 |
|--------|------|------|
| 🔴 P0 | G8, G4, G5 | Age/Lifespan 系统——核心游戏循环完整性 |
| 🔴 P0 | G9 | Room 状态机——领土系统基础 |
| 🟡 P1 | G1, G22 | WASM 预编译——性能关键路径 |
| 🟡 P1 | G2, G3 | Keyframe/Delta + Mods Lock——回放和反作弊基础 |
| 🟡 P1 | G6, G10 | Entity Flags + Transport Intercept——战斗/物流完整性 |
| 🟡 P1 | G7 | Seed Rotation——安全 |
| 🟢 P2 | G11-G14 | MCP 工具——AI 玩家体验 |
| 🟢 P2 | G15-G19 | Gateway 端点 |
| 🟢 P2 | G20-G21 | Frontend 完善 |
