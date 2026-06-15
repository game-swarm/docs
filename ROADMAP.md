# Swarm — 模块化实施追踪

> 锚定 Phase 0 Architecture Freeze（2026-06-14）。审计日期: 2026-06-15  
> 只看合并到 main 且测试通过的代码。

## 总览

| 模块 | 目录 | ✅ | ⚠️ | ❌ | 进度 |
|------|------|----|----|-----|------|
| engine | `engine/` | 36 | 3 | 3 | 86% |
| sandbox | `sandbox/` | 6 | 0 | 0 | 100% |
| sdk-ts | `sdk-ts/` | 5 | 0 | 0 | 100% |
| sdk-rust | `sdk-rust/` | 0 | 0 | 3 | 0% |
| gateway | `gateway/` | 0 | 0 | 4 | 0% |
| frontend | `frontend/` | 5 | 3 | 0 | 63% |
| infra | (根目录) | 4 | 1 | 1 | 67% |
| docs | `docs/` | 6 | 0 | 0 | 100% |
| **总计** | | **62** | **7** | **11** | **78%** |

---

## engine/ — 核心引擎 (Rust + Bevy ECS) — 121 tests ✅

### ECS 世界模拟
- [x] [P1] Position/RoomId/Drone/Structure/Resource/Source/Terrain/Controller 组件
- [x] [P1] ECS systems chain (.chain() 顺序固定)
- [x] [P1] state_checksum (Blake3 XOF) 确定性
- [x] [P3] 多房间 + 房间边界 (RoomId::from_room_name, is_same_or_adjacent)

### Game API & 指令
- [x] [P1] CommandAction 枚举 (Move/Harvest/Build/Spawn/Transfer/Attack/Heal/Claim/TransferToGlobal/FromGlobal/CreateMarketOrder/BuyMarketOrder)
- [x] [P1] Command Validation Pipeline (JSON schema → 预校验 → 应用)
- [x] [P1] Refund 模型 (50% 退还 + RefundAccumulator)
- [x] [P2] Source Gate (12 来源管线化)

### Tick 引擎
- [x] [P1] 单玩家 Tick 调度器 (3s 间隔)
- [x] [P2] 多玩家 Tick 调度器 (并行 Collect + Blake3 洗牌 + 串行 Execute)
- [x] [P1] TickTrace + 回放验证 (ReplayError::StateMismatch)
- [x] [P1] TickMetrics + ClickHouse 指标 (InMemory)

### MCP 接口
- [x] [P1] 基础脚手架 (get_snapshot/deploy/world_rules)
- [x] [P2] 完整工具集 (get_available_actions/explain_last_tick/profile/dry_run/get_docs + schemas)
- [x] [P2] OAuth2 + Ed25519 证书认证
- [ ] [P2] MCP 限流 (per-source rate limiter) ❌

### 实时推送
- [x] [P2] WebSocket delta push (NATS publisher + RealtimeDelta)
- [x] [P2] 统一可见性 is_visible_to()

### 持久化
- [ ] [P3] FoundationDB 持久化 ⚠️ InMemoryFoundationDb stub
- [ ] [P3] Dragonfly 热缓存 ⚠️ InMemoryDragonfly stub (kanban 任务运行中)
- [ ] [P3] ClickHouse 指标 ⚠️ InMemoryClickHouseMetricsWriter stub

### Rhai 模组系统
- [x] [P3] 3 hooks: init.rhai / tick_start.rhai / tick_end.rhai
- [x] [P3] tick_start.rhai 在 main loop 中调用 ✅
- [x] [P3] Module CLI (swarm mod install/remove/config)
- [x] [P3] 执行预算 (AST 10k/tick, actions 100/tick, 墙钟 100ms)

### 全局存储
- [x] [P3] TransferToGlobal/TransferFromGlobal
- [x] [P3] 累进存储税 (GlobalStorageTaxTier)
- [x] [P3] Pending transfers 在 snapshot 中暴露

### 教程
- [x] [P4] Tutorial 世界模式 (WorldConfig::tutorial, independent namespace, tick=1000ms)
- [x] [P4] 新玩家进入 Tutorial 自动部署 starter bot
- [ ] [P4] 5 分钟引导成就流程 (6 成就定义存在，流程未集成) ⚠️

### 战斗
- [x] [P6] 战斗系统 (Attack/RangedAttack/Heal + damage_multiplier)
- [x] [P6] Controller + 房间占领 (Claim body part, GCL)

### 经济
- [x] [P6] 市场交易 (MarketOrder + CreateMarketOrder/BuyMarketOrder)

### Arena & 排名
- [x] [P6] Arena 模式 (1v1, 5k tick, 对称初始, 赛后公开回放)
- [x] [P6] 排行榜 (Elo/Glicko + Bronze..Master 分层)

### 生产化
- [x] [P7] 反作弊 (阈值检测: fuel/rejection pattern)
- [x] [P5] 本地模拟 (swarm sim --ticks=5000 --speed=100x)
- [x] [P7] CI/CD Pipeline (.github/workflows/ci.yml)
- [ ] [P6] 运输拦截 (PvP) ❌
- [ ] [P7] ECS 并行化 ❌
- [ ] [P7] Sharding ❌
- [ ] [P6] AI 锦标赛执行引擎 ⚠️

---

## sandbox/ — WASM 沙箱 — 9 tests ✅
- [x] Fuel metering + epoch interruption
- [x] 64MB 线性内存上限
- [x] 5 个只读 host functions
- [x] Deferred command model
- [x] Module 验证
- [x] Output 验证

---

## sdk-ts/ — TypeScript SDK — 11 tests ✅
- [x] tick(snapshot) → Command[] 类型
- [x] IDL 驱动常量
- [x] Starter bot 示例
- [x] Validation helpers
- [x] Visibility helpers

---

## sdk-rust/ — Rust SDK — 0 tests
> 仓库已创建，待实施。

- [ ] tick(snapshot) → Command[] 类型 ❌
- [ ] IDL 驱动代码生成 ❌
- [ ] Starter bot 示例 ❌

---

## gateway/ — Go API 网关
> 仓库已创建，待实施。

- [ ] WebSocket 连接管理 ❌
- [ ] NATS → 客户端消息中继 ❌
- [ ] OAuth2 回调 HTTP handler ❌
- [ ] Health check / readiness probe ❌

---

## frontend/ — Web 客户端 (React) — 3 tests ✅
- [x] React + PixiJS WebGL tilemap
- [x] Monaco Editor 集成 (TypeScript 自动补全 + Compile & Deploy)
- [x] 行内校验 ("WORK body part" 等)
- [x] Tutorial 引导 UI
- [x] Tick 详细解释展示
- [ ] 一键 WASM 编译部署 (未实现) ⚠️
- [ ] OAuth2 登录 UI ⚠️
- [ ] 回放查看器 (交互式) ⚠️

---

## infra/ — 基础设施
- [x] Docker Compose (fdb + nats + engine)
- [x] CI/CD Pipeline (lint → unit → integration → replay → sdk → load → deploy)
- [ ] Load test (tests/load.rs) ❌ — CI job 引用了不存在的文件
- [x] Security auditor (fuel/rejection 阈值)
- [ ] Wasmtime CVE SLA 文档 ⚠️

---

## 当前进行中

| ID | 任务 | 状态 |
|----|------|------|
| `t_75816b11` | B2: Dragonfly real connector | 🔄 running |

## 待重新派发 (Dragonfly 完成后)

| 批次 | 任务 |
|------|------|
| B2 | FDB real connector, ClickHouse real connector, MCP rate limiter |
| B3 | sdk-rust 初始, gateway 初始 |
| B4 | frontend: WASM编译部署, OAuth2UI, replay viewer |
| B5 | engine: 运输拦截, ECS并行化, sharding, AI锦标赛, onboarding流程集成 |
