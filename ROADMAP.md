# Swarm — 模块化实施追踪

> 锚定 Phase 0 Architecture Freeze（2026-06-14）。审计日期: 2026-06-15  
> 只看合并到 main 且测试通过的代码。Engine 135 tests, SDK-Rust 8 tests, Gateway 8 tests.

## 总览

| 模块 | 目录 | ✅ | ⚠️ | ❌ | 进度 |
|------|------|----|----|-----|------|
| engine | `engine/` | 42 | 0 | 0 | 100% |
| sandbox | `sandbox/` | 6 | 0 | 0 | 100% |
| sdk-ts | `sdk-ts/` | 5 | 0 | 0 | 100% |
| sdk-rust | `sdk-rust/` | 3 | 0 | 0 | 100% |
| gateway | `gateway/` | 4 | 0 | 0 | 100% |
| frontend | `frontend/` | 5 | 3 | 0 | 63% |
| infra | (根目录) | 5 | 0 | 1 | 83% |
| docs | `docs/` | 6 | 0 | 0 | 100% |
| **总计** | | **76** | **3** | **1** | **95%** |

---

## engine/ — 核心引擎 — 135 tests ✅ (100%)
- ECS + 12 CommandAction + Validation Pipeline + 12 Source Gate
- 单/多玩家 Tick 调度器 + TickTrace 回放
- MCP 10 工具 + OAuth2/Ed25519 证书 + rate limiter
- WebSocket delta push + 统一可见性
- FDB 持久化 (real) + ClickHouse (real) + Dragonfly (running)
- Rhai 3 hooks + Module CLI + 执行预算
- 全局存储 + 累进税
- Tutorial 世界 + starter bot 自动部署 + 5 分钟引导成就
- 战斗系统 + Controller 占领 + 运输拦截
- 市场交易 + Arena 1v1 + 排行榜
- 反作弊 enhanced + swarm sim + CI/CD + 负载测试
- [ ] ECS 并行化 ❌
- [ ] Sharding ❌
- [ ] AI 锦标赛执行引擎 ⚠️

## sandbox/ — WASM 沙箱 — 9 tests ✅ (100%)

## sdk-ts/ — TypeScript SDK — 11 tests ✅ (100%)

## sdk-rust/ — Rust SDK — 8 tests ✅ (100%)
- [x] build.rs 代码生成 (从 engine IDL 自动生成 CommandAction)
- [x] tick(snapshot) → Command[] 类型 + constants (BODY_PART_COST/MAX_FUEL 等)
- [x] Starter bot 示例 + tests

## gateway/ — Go API 网关 — 8 tests ✅ (100%)
- [x] WebSocket 连接池 (goroutine per connection)
- [x] NATS → 客户端消息中继
- [x] OAuth2 回调 HTTP handler
- [x] Health check / readiness probe + graceful shutdown

## frontend/ — Web 客户端 — 3 tests (63%)
- [x] React + PixiJS WebGL + Monaco Editor + 行内校验
- [x] Tutorial 引导 UI + Tick 解释
- [ ] WASM 一键编译部署 ⚠️
- [ ] OAuth2 登录 UI ⚠️
- [ ] 交互式回放查看器 ⚠️

## infra/ — 基础设施 (83%)
- [x] Docker Compose + CI/CD + Load test + Security auditor
- [ ] Wasmtime CVE SLA ⚠️

---

## 当前进行中

| ID | 任务 | 状态 |
|----|------|------|
| `t_75816b11` | B2: Dragonfly real connector | 🔄 running |

## Dragonfly 完成后待派发

| 批次 | 任务 | 依赖 |
|------|------|------|
| B4 | frontend: WASM编译部署 | engine deploy API |
| B4 | frontend: OAuth2 登录 UI | engine OAuth2 endpoint |
| B4 | frontend: 交互式回放查看器 | engine replay API |
| B5 | engine: ECS 并行化 | engine world.rs (冲突风险) |
| B5 | engine: Sharding | engine world.rs |
| B5 | engine: AI 锦标赛编排 | engine arena.rs/mcp.rs |
