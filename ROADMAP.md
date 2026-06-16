# Swarm — 实现差距追踪

> 审计日期: 2026-06-16。全量代码审计 vs DESIGN.md。
> 测试总数: engine:159, sandbox:14, sdk-rust:8, sdk-ts:11, gateway:9, frontend:13

## 总览

| 模块 | 仓库 | 状态 |
|------|------|------|
| engine | `engine/` | 3 缺口待修复 |
| sandbox | `sandbox/` | ✅ 完成 |
| gateway | `gateway/` | ✅ 完成 |
| frontend | `frontend/` | ✅ 完成 |
| **总计** | | **5 缺口** |

---

## P0 — 核心游戏循环完整性

### G5b: Depot 维修系统 — DESIGN §8.2

**当前状态**: Depot 在 `StructureTypeRegistry` 中已定义（含 `repair_capacity`/`repair_range`/`repair_aging`/`maintenance`），但无对应的 ECS system 执行维修。
**设计要求**: Controller 已实现维修。Depot 作为前线维修节点——消耗存储资源降低 drone age，可被占领，固定 range=1。

- [ ] 实现 `depot_repair_system`: 查询范围内 Depot，消耗 maintenance 资源，降低 drone age
- [ ] Controller 维修硬上限需扩展——Controller + Depot 合计 age 回退 ≤ 自然增长 50%
- [ ] maintenance 耗尽时 Depot 停止维修（已定义字段，需实现逻辑）

### G8a: BodyPartTypeDef.age_modifier — DESIGN §8.2

**当前状态**: `BodyPartTypeDef` 结构体缺 `age_modifier: i32` 字段。所有 body part 对 drone lifespan 无影响。
**设计要求**: 每个 body part 类型有 `age_modifier`（TOUGH +100 延寿、ATTACK -80 折寿、Heal -30、Claim -50、RangedAttack -50、Move/Work/Carry 默认 0）。

- [ ] `BodyPartTypeDef` 新增 `age_modifier: i32` 字段，默认 0
- [ ] `BodyPartRegistry::default()` 为各类型设置正确的 age_modifier
- [ ] 确保 world.toml 解析 `[[body_part_types]]` 时支持此字段
- [ ] `BodyPartRegistry::from_defs()` 传递 age_modifier

### G8b: Drone age_max 计算 — DESIGN §8.2

**当前状态**: `Drone::new()` 始终设置 `lifespan = DEFAULT_DRONE_LIFESPAN` (1500)，不聚合 body part 的 age_modifier。
**设计要求**: `age_max = BASE_AGE + sum(每个 body part 的 age_modifier)`。

- [ ] `Drone::new()` 改为接收 `&BodyPartRegistry` 或 age_modifier 列表
- [ ] 计算 `lifespan = DEFAULT_DRONE_LIFESPAN + body.iter().map(|p| registry.age_modifier(p)).sum::<i32>()`
- [ ] 更新所有 spawn 调用点传入 registry

---

## P1 — MCP 工具完善

### G13: swarm_list_modules 真实现有 — DESIGN §4.1

**当前状态**: `swarm_list_modules()` 返回硬编码 stub（hash="not-implemented", deployed_at="not-implemented"）。
**设计要求**: 返回所有已部署 WASM 模块列表（module_id, hash, deployed_at, status）。

- [ ] 实现模块存储查询（从 sandbox/engine 的模块注册表获取真实数据）
- [ ] 返回真实的 module_id、hash、部署时间

### G14: swarm_get_replay 真实实现 — DESIGN §4.1

**当前状态**: `swarm_get_replay()` 返回占位消息（"requires keyframe+delta storage integration"）。
**设计要求**: 返回指定 tick 范围的回放数据（实体变更、指令日志）。

- [ ] 利用已有的 `ReplayStorageConfig` + `KeyframeData` + `WorldDelta` 实现真实 replay 查询
- [ ] 组装 from_tick→to_tick 的 delta 链并返回实体变更集

---

## 实现优先级

| 优先级 | 缺口 | 理由 |
|--------|------|------|
| 🔴 P0 | G8a, G8b | Body part age modifier——核心 drone 生命周期差异化 |
| 🔴 P0 | G5b | Depot 维修——前线物流玩法完整性 |
| 🟡 P1 | G13, G14 | MCP stub→真实——AI 玩家模块管理和回放查看 |
