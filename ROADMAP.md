# Swarm — 模块化实施追踪

> 锚定 Phase 0 Architecture Freeze（2026-06-14）。审计日期: 2026-06-15  
> 只看合并到 main 且测试通过的代码。Engine 150 tests, SDK-Rust 8 tests, Gateway 7 tests.

## 总览

| 模块 | 目录 | ✅ | ⚠️ | ❌ | 进度 |
|------|------|----|----|-----|------|
| engine | `engine/` | 45 | 0 | 0 | 100% |
| sandbox | `sandbox/` | 6 | 0 | 0 | 100% |
| sdk-ts | `sdk-ts/` | 5 | 0 | 0 | 100% |
| sdk-rust | `sdk-rust/` | 3 | 0 | 0 | 100% |
| gateway | `gateway/` | 4 | 0 | 0 | 100% |
| frontend | `frontend/` | 8 | 0 | 0 | 100% |
| infra | (根目录) | 6 | 0 | 0 | 100% |
| docs | `docs/` | 6 | 0 | 0 | 100% |
| **小计** | | **83** | **0** | **0** | **100%** |
| 审计缺口 (B6-B11) | engine+gateway+sandbox | 10 | 🔄1 | 0 | 91% |
| **总计** | | **93** | **1** | **0** | **99%** |

---

## engine/ — 核心引擎 — 150 tests ✅
- ECS + 12 CommandAction + Validation Pipeline + 12 Source Gate
- 单/多玩家 Tick 调度器 + TickTrace 回放
- MCP 10 工具 + OAuth2/Ed25519 证书 + rate limiter
- WebSocket delta push + 统一可见性
- FDB 持久化 (real) + ClickHouse (real) + Dragonfly (real)
- Rhai 3 hooks + Module CLI + 执行预算
- 全局存储 + 累进税
- Tutorial 世界 + starter bot 自动部署 + 5 分钟引导成就
- 战斗系统 + Controller 占领 + 运输拦截
- 市场交易 + Arena 1v1 + 排行榜
- 反作弊 enhanced + swarm sim + CI/CD + 负载测试
- [x] ECS 并行化 ✅ (multi-player tick 真正并行)
- [x] Sharding ✅ (ShardId/ShardConfig/ShardDiscovery, 323行)
- [x] AI 锦标赛执行引擎 ✅ (bracket + 自动match编排, 591行)

## sandbox/ — WASM 沙箱 — 9 tests ✅ (100%)

## sdk-ts/ — TypeScript SDK — 11 tests ✅ (100%)

## sdk-rust/ — Rust SDK — 8 tests ✅ (100%)
- [x] build.rs 代码生成 (从 engine IDL 自动生成 CommandAction)
- [x] tick(snapshot) → Command[] 类型 + constants (BODY_PART_COST/MAX_FUEL 等)
- [x] Starter bot 示例 + tests

## gateway/ — Go API 网关 — 7 tests ✅ (100%)
- [x] WebSocket 连接池 (goroutine per connection)
- [x] NATS → 客户端消息中继
- [x] OAuth2 回调 HTTP handler
- [x] Health check / readiness probe + graceful shutdown

## frontend/ — Web 客户端 — 8 tests (100%)
- [x] React + PixiJS WebGL + Monaco Editor + 行内校验
- [x] Tutorial 引导 UI + Tick 解释
- [x] OAuth2 登录 UI (证书持久化 + 自动刷新, LoginButton.tsx + test)
- [x] 交互式回放查看器 (ReplayViewer.tsx)
- [x] WASM 一键编译部署 (真实 deployBot, +1 test)

## infra/ — 基础设施 (100%)
- [x] Docker Compose + CI/CD + Load test + Security auditor
- [x] Wasmtime CVE SLA

---

## B6-B11: 审计缺口补齐 (2026-06-15 审计发现)

| 任务 | 缺口 | 仓库 | 状态 |
|------|------|------|------|
| B6 | MCP 工具补齐 (6 tools + explain_last_tick) | engine/mcp.rs | 🔄 running |
| B7 | 战斗系统 (RangedAttack/Claim/Controller/RCL) | engine/command+systems | ✅ done (`b0c6350`) |
| B8 | World Rules 可配置化 (15项规则 + world.toml) | engine/world+resources | ✅ done (`7bc855f`) |
| B9 | 可见性高级特性 (fog_of_war/player_view/spectate) | engine/visibility.rs | ✅ done (`bf04af3`) |
| B10 | Gateway OAuth2 真实 provider 集成 | gateway/ | ✅ done (`dfa3f80`) |
| B11 | WASM 沙箱 OS 进程隔离 (seccomp/cgroup) | sandbox/ | ✅ done (`05d8c5f`) |

---

## 设计与实现差距（DESIGN.md 目标 vs 当前代码）

| ID | 差距 | DESIGN 目标 | 当前实现 | 锚定点 |
|----|------|-----------|---------|--------|
| G1 | BodyPart 不可配置 | world.toml `[[body_part_types]]` 8 字段 schema | ✅ done (`0e2454e`) | DESIGN §8.2 |
| G2 | 无伤害类型体系 | 6 种伤害类型 + 抗性 | ✅ done (`0e2454e`) | DESIGN §8.2 |
| G3 | 身体部件单资源成本 | 多资源消耗 | ✅ done (`8d09471`) | DESIGN §8.2 |
| G4 | 无属性级抗性 | Rhai 模组动态属性 | ✅ done (`0e2454e`) | DESIGN §8.2 |
| G5 | StructureType 不可配置 | `[[structure_types]]` | ✅ done (`1381e7a`) | DESIGN §8.2 |
| G6 | CommandAction 不可扩展 | `[[custom_actions]]` | ✅ done (`1381e7a`) | DESIGN §8.2 |

---

## H1-H2: 特殊攻击 + 回收 (DESIGN §8.2 未实现)

| 任务 | 缺口 | DESIGN 锚定 |
|------|------|-----------|
| H1 | 特殊攻击 (Hack/Drain/Overload/Debilitate/Leech/Fabricate + Disrupt/Fortify完善) | DESIGN §8.2 特殊攻击方式表 |
| H2 | Recycle 命令 (回收 drone 退还 50% 资源) | DESIGN §8.2 Drone 身体规划 |
