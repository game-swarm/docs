# Swarm — 模块化实施追踪

> 锚定 Phase 0 Architecture Freeze（2026-06-14）。审计日期: 2026-06-15  
> 废弃了按 Phase 切割的虚假"完成"感，改为按模块逐项追踪。

## 总览

| 模块 | 目录 | ✅ | ⚠️ | ❌ | 进度 |
|------|------|----|----|-----|------|
| engine | `engine/` | 30 | 7 | 4 | 73% |
| sandbox | `sandbox/` | 6 | 0 | 0 | 100% |
| sdk-ts | `sdk-ts/` | 5 | 0 | 0 | 100% |
| sdk-rust | `sdk-rust/` | 0 | 0 | 4 | 0% |
| gateway | `gateway/` | 0 | 0 | 4 | 0% |
| frontend | `frontend/` | 2 | 4 | 2 | 25% |
| infra | (根目录) | 2 | 1 | 1 | 50% |
| docs | `docs/` | 6 | 0 | 0 | 100% |
| **总计** | | **51** | **12** | **15** | **65%** |

---

## engine/ — 核心引擎 (Rust + Bevy ECS)

### ECS 世界模拟
- [x] [P1] Position/RoomId/Drone/Structure/Resource/Source/Terrain/Controller 组件 — `components.rs`
- [x] [P1] ECS systems chain: death_mark → spawn → regeneration → combat → decay → death_cleanup → global_storage — `world.rs:195-208`
- [x] [P1] state_checksum (Blake3 XOF) — `world.rs:247-523`
- [x] [P3] 多房间 + 房间边界 — `RoomId::from_room_name()`, `is_same_or_adjacent()`

### Game API & 指令
- [x] [P1] CommandAction 枚举 (Move/Harvest/Build/Spawn/Transfer/Attack/Heal/Claim/TransferToGlobal/FromGlobal/CreateMarketOrder/BuyMarketOrder) — `command.rs:56-116`
- [x] [P1] Command Validation Pipeline (JSON schema → 预校验 → 应用) — `command.rs:254-379`
- [x] [P1] Refund 模型 (50% 退还 + RefundAccumulator) — `command.rs:516-548`
- [x] [P2] Source Gate (12 来源管线化) — `command.rs:27-40`, `source_allows_action()`

### Tick 引擎
- [x] [P1] 单玩家 Tick 调度器 (3s 间隔) — `main.rs:86-118`
- [x] [P2] 多玩家 Tick 调度器 (并行 Collect + Blake3 洗牌 + 串行 Execute) — `tick.rs:420-499`
- [x] [P1] TickTrace + 回放验证 (ReplayError::StateMismatch) — `tick.rs:53-405`

### MCP 接口
- [x] [P1] 基础脚手架 (get_snapshot/deploy/world_rules) — `mcp.rs`
- [x] [P2] 完整工具集 (get_available_actions/explain_last_tick/profile/dry_run/get_docs) — `mcp.rs:516-1154`
- [x] [P2] OAuth2 + Ed25519 证书认证 — `mcp.rs:594-742`
- [ ] [P2] MCP 限流 (per-source rate limiter) ⚠️

### 实时推送
- [x] [P2] WebSocket delta push (NATS publisher + RealtimeDelta) — `realtime.rs`
- [x] [P2] 统一可见性 is_visible_to() — `visibility.rs:13-25`, 4 tests

### 持久化
- [ ] [P3] FoundationDB 持久化 (每 tick 原子提交 `/tick/{N}/state|commands|rejections|metrics`) ⚠️ `InMemoryFoundationDb` stub
- [ ] [P3] Dragonfly 热缓存 (miss → FDB 回填, FDB 为准) ⚠️ `InMemoryDragonfly` stub
- [ ] [P3] ClickHouse 指标 (refund_abuse_rate/command_rejection_rate/tick_duration_p99) ⚠️ `InMemoryClickHouseMetricsWriter` stub

### Rhai 模组系统
- [x] [P3] 3 hooks: init.rhai / tick_start.rhai / tick_end.rhai 定义 — `rule_module.rs`
- [x] [P3] Module CLI (swarm mod install/remove/config) — `mod_cli.rs`
- [x] [P3] 执行预算 (AST 10k/tick, actions 100/tick, 墙钟 100ms)
- [ ] [P3] tick_start.rhai 在单玩家 main loop 中调用 — multi-player 路径正常 ⚠️

### 全局存储
- [x] [P3] TransferToGlobal/TransferFromGlobal — `command.rs:99-105`
- [x] [P3] 累进存储税 (GlobalStorageTaxTier) — `resources.rs:62-66`
- [x] [P3] Pending transfers 在 snapshot 中暴露 — `global_storage_system.rs`

### 教程
- [ ] [P4] WorldMode::Tutorial (独立 namespace, tick=1000ms, 资源加速) ❌
- [ ] [P4] 5 分钟引导成就流程 (6 成就: 首次采集/spawn/建造/瓶颈/回放/Arena) ⚠️ 成就定义存在
- [ ] [P4] 新玩家进入 Tutorial 自动部署 starter bot ⚠️ bot 代码存在

### 战斗
- [x] [P6] 战斗系统 (Attack/RangedAttack/Heal + damage_multiplier) — `combat_system.rs`
- [x] [P6] Controller + 房间占领 (Claim body part, GCL) — `components.rs:334-344`
- [ ] [P6] 运输拦截 (PvP 世界: 敌方 drone 拦截运输中的资源) ❌

### 经济
- [x] [P6] 市场交易 (MarketOrder + CreateMarketOrder/BuyMarketOrder) — `resources.rs:83-96`

### Arena & 排名
- [x] [P6] Arena 模式 (1v1, 5k tick, 对称初始, 赛后公开回放) — `arena.rs`
- [x] [P6] 排行榜 (Elo/Glicko + Bronze..Master 分层) — `ranking.rs`
- [ ] [P6] AI 锦标赛执行引擎 ⚠️ 预提交存在, 竞赛编排缺失

### 生产化
- [ ] [P7] ECS 并行化 (.before()/.after() 替代 .chain()) ❌
- [ ] [P7] Sharding (跨引擎进程分配房间) ❌
- [ ] [P7] 反作弊 (回放审计 + 注入检测) ⚠️ 仅阈值检测
- [x] [P5] 本地模拟 (swarm sim --ticks=5000 --speed=100x) — `main.rs:121-174`

### 引擎测试: 115 passing ✅

---

## sandbox/ — WASM 沙箱 (Rust + Wasmtime)

- [x] [P1] Fuel metering + epoch interruption (2500ms) — `lib.rs`
- [x] [P1] 64MB 线性内存上限
- [x] [P1] 5 个只读 host functions (查询 only)
- [x] [P1] Deferred command model (WASM 输出序列化 commands)
- [x] [P1] Module 验证: 大小 < 5MB, 拒绝 start section, 拒绝非法 imports
- [x] [P1] Output 验证: < 256KB, 有效指针

### 沙箱测试: 9 passing ✅

---

## sdk-ts/ — TypeScript SDK

- [x] [P1] tick(snapshot) → Command[] 完整类型定义 — `src/types.ts`
- [x] [P1] IDL 驱动常量 (MAX_FUEL, BODY_PART_COST, etc.) — `src/constants.ts`
- [x] [P1] Starter bot 示例 (collect → spawn → auto loop) — `examples/starter-bot/`
- [x] [P1] Validation helpers
- [x] [P2] Visibility helpers

### SDK-TS 测试: 11 passing ✅

---

## sdk-rust/ — Rust SDK

> 仓库已创建，零代码。

- [ ] [P1] tick(snapshot) → Command[] 类型定义 ❌
- [ ] [P1] IDL 驱动代码生成 ❌
- [ ] [P1] Starter bot 示例 ❌
- [ ] [P5] 本地模拟集成 (swarm sim 辅助) ❌

---

## gateway/ — Go API 网关

> 仓库已创建，零代码。

- [ ] [P2] WebSocket 连接管理 (goroutine per connection) ❌
- [ ] [P2] NATS → 客户端消息中继 (delta broadcast) ❌
- [ ] [P5] OAuth2 回调 HTTP handler ❌
- [ ] [P7] Health check / readiness probe ❌

---

## frontend/ — Web 客户端 (React)

- [x] [P5] React + PixiJS WebGL tilemap 地图渲染 — `MapView.tsx`
- [ ] [P5] Monaco Editor 集成 (TypeScript 自动补全) ❌ — 依赖已安装, 未集成
- [ ] [P5] IDE: 行内校验 (已实现) + 一键 WASM 编译部署 (未实现) ⚠️
- [ ] [P5] OAuth2 登录 UI ⚠️
- [ ] [P4] 回放查看器 (交互式 tick 选择 + 快照/指令/拒绝浏览) ⚠️ — 当前为静态演示
- [ ] [P4] Tutorial 引导 UI ❌
- [x] [P4] Tick 详细解释展示 — `App.tsx:89-94`
- [ ] [P6] 锦标赛观战 UI ⚠️

### 前端测试: 3 passing ✅

---

## infra/ — 基础设施

- [x] [P1] Docker Compose 开发环境 (fdb + nats + engine) — `docker-compose.yml`
- [x] [P7] CI/CD Pipeline (lint → unit → integration → replay → sdk → load → deploy) — `.github/workflows/ci.yml`
- [ ] [P7] 负载测试文件 ⚠️ — CI 已配置, `tests/load.rs` 缺失
- [ ] [P7] Wasmtime CVE SLA 文档 (响应 < 7 天, 迁移脚本) ❌

---

## docs/ — 设计文档

- [x] [P0] DESIGN.md — 架构全景 + 游戏设计
- [x] [P0] tech-choices.md — 11 组件备选分析
- [x] [P0] ROADMAP.md — 本文件
- [x] [P0] P0 规范 (9 份: tick protocol, command validation, MCP security, WASM sandbox, visibility, MVP feedback, world rules, game API IDL, command source model)
- [x] [P0] 评审档案 R1-R14 (130+ 份评审文件)
- [x] [P7] RUNBOOK.md

---

## 依赖图（决定实施顺序）

```
                    ┌─────────────────┐
                    │  engine ECS 核心  │ ← 基础依赖
                    └────────┬────────┘
                             │
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                   ▼
   ┌──────────┐     ┌──────────────┐    ┌──────────────┐
   │ sandbox   │     │ engine Game  │    │ engine Tick   │
   │ (WASM)    │     │ API/Commands │    │ Scheduler     │
   └─────┬─────┘     └──────┬───────┘    └──────┬───────┘
         │                  │                   │
         └──────────────────┼───────────────────┘
                            │
               ┌────────────┼────────────┐
               ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ sdk-ts    │ │ sdk-rust │ │ engine   │
        │           │ │          │ │ MCP/WS   │
        └──────────┘ └──────────┘ └────┬─────┘
                                       │
                          ┌────────────┼────────────┐
                          ▼            ▼            ▼
                   ┌──────────┐ ┌──────────┐ ┌──────────┐
                   │ gateway   │ │ frontend  │ │ engine   │
                   │ (Go)      │ │ (React)   │ │ 持久化    │
                   └──────────┘ └──────────┘ │ Rhai/战斗 │
                                             │ Arena     │
                                             └──────────┘
```

### 推荐实施顺序

| 批次 | 模块 | 理由 |
|------|------|------|
| **B1** (当前) | engine: tutorial, transport, tick_start | 解除 ❌ 标记 |
| **B2** | engine: FDB/Dragonfly/ClickHouse 真实连接 | 解除 ⚠️ stub |
| **B3** | sdk-rust (初始) + gateway (初始) | 填充空仓库 |
| **B4** | frontend: Monaco, OAuth2 UI, replay, tutorial | 完整产品体验 |
| **B5** | engine: ECS 并行化, sharding, 反作弊增强, AI 锦标赛 | 生产化收官 |
