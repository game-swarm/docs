# Swarm — 模块化实施追踪

> 锚定 Phase 0 Architecture Freeze（2026-06-14）。审计日期: 2026-06-15  
> 只看合并到 main 且测试通过的代码。135 tests passing.

## 总览

| 模块 | 目录 | ✅ | ⚠️ | ❌ | 进度 |
|------|------|----|----|-----|------|
| engine | `engine/` | 42 | 0 | 0 | 100% |
| sandbox | `sandbox/` | 6 | 0 | 0 | 100% |
| sdk-ts | `sdk-ts/` | 5 | 0 | 0 | 100% |
| sdk-rust | `sdk-rust/` | 0 | 0 | 3 | 0% |
| gateway | `gateway/` | 0 | 0 | 4 | 0% |
| frontend | `frontend/` | 5 | 3 | 0 | 63% |
| infra | (根目录) | 5 | 0 | 1 | 83% |
| docs | `docs/` | 6 | 0 | 0 | 100% |
| **总计** | | **69** | **3** | **8** | **86%** |

---

## engine/ — 核心引擎 — 135 tests ✅

### ECS 世界模拟
- [x] Position/RoomId/Drone/Structure/Resource/Source/Terrain/Controller 组件
- [x] ECS systems chain (.chain() 顺序固定)
- [x] state_checksum (Blake3 XOF)

### Game API & 指令
- [x] CommandAction (Move/Harvest/Build/Spawn/Transfer/Attack/Heal/Claim/TransferToGlobal/FromGlobal/CreateMarketOrder/BuyMarketOrder)
- [x] Command Validation Pipeline
- [x] Refund 模型 (50% 退还 + RefundAccumulator)
- [x] Source Gate (12 来源管线化)

### Tick 引擎
- [x] 单/多玩家 Tick 调度器
- [x] TickTrace + 回放验证

### MCP 接口
- [x] 基础脚手架 + 完整工具集 (10 MCP tools)
- [x] OAuth2 + Ed25519 证书
- [x] MCP rate limiter ✅

### 实时推送
- [x] WebSocket delta push
- [x] 统一可见性 is_visible_to()

### 持久化
- [x] FoundationDB 持久化 (real connector) ✅
- [ ] Dragonfly 热缓存 (kanban 任务运行中)
- [x] ClickHouse 指标 (real writer) ✅

### Rhai 模组
- [x] 3 hooks: init/tick_start/tick_end
- [x] tick_start 在 main loop 中
- [x] Module CLI
- [x] 执行预算

### 全局存储
- [x] TransferToGlobal/FromGlobal
- [x] 累进存储税
- [x] Pending transfers in snapshot

### 教程
- [x] Tutorial 世界模式
- [x] Starter bot 自动部署
- [x] 5 分钟引导成就流程 ✅

### 战斗
- [x] 战斗系统 (Attack/RangedAttack/Heal)
- [x] Controller + 房间占领
- [x] 运输拦截 (PvP) ✅

### 经济
- [x] 市场交易

### Arena & 排名
- [x] Arena 模式 (1v1, 5k tick)
- [x] 排行榜 (Elo/Glicko)
- [ ] AI 锦标赛执行引擎 ⚠️

### 生产化
- [x] 反作弊 (enhanced auditing)
- [x] 本地模拟 (swarm sim)
- [x] CI/CD Pipeline
- [x] 负载测试 (multiplayer load test) ✅
- [ ] ECS 并行化 ❌
- [ ] Sharding ❌

---

## sandbox/ — WASM 沙箱 — 100% ✅
## sdk-ts/ — TypeScript SDK — 100% ✅

---

## sdk-rust/ — Rust SDK — 0%
> 仓库已创建，待实施。

---

## gateway/ — Go API 网关 — 0%
> 仓库已创建，待实施。

---

## frontend/ — Web 客户端 — 63%
- [x] React + PixiJS WebGL
- [x] Monaco Editor
- [x] 行内校验
- [x] Tutorial 引导 UI
- [x] Tick 详细解释
- [ ] WASM 一键编译部署 ⚠️
- [ ] OAuth2 登录 UI ⚠️
- [ ] 回放查看器 (交互式) ⚠️

---

## infra/ — 基础设施 — 83%
- [x] Docker Compose
- [x] CI/CD Pipeline
- [x] Load test ✅
- [x] Security auditor
- [ ] Wasmtime CVE SLA ⚠️

---

## 当前进行中

| ID | 任务 | 状态 |
|----|------|------|
| `t_75816b11` | B2: Dragonfly real connector | 🔄 running |

## 完成 Dragonfly 后待派发

| 批次 | 任务 |
|------|------|
| B3 | sdk-rust, gateway |
| B4 | frontend: WASM编译, OAuth2, replay |
| B5 | engine: ECS并行化, sharding, AI锦标赛 |
