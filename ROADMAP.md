# Swarm — 模块化实施追踪

> 锚定 Phase 0 Architecture Freeze（2026-06-14）。审计日期: 2026-06-15  
> 只看合并到 main 且测试通过的代码。Engine 151 tests, SDK-Rust 8 tests, Gateway 7 tests.

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
| 审计缺口 (B6-B11) | engine+gateway+sandbox | 10 | 0 | 0 | 100% |
| **总计** | | **93** | **0** | **0** | **100%** |

待实现: H1b (6 special attacks configurable via [[special_effects]])

---

## engine/ — 核心引擎 — 151 tests ✅
- ECS + 16 CommandAction (+ 1 Custom for [[custom_actions]]) + Validation Pipeline + 12 Source Gate
- 单/多玩家 Tick 调度器 + TickTrace 回放
- MCP 24 工具 + OAuth2/Ed25519 证书 + rate limiter
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

## sandbox/ — WASM 沙箱 — 10 tests ✅ (100%)

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
| B6 | MCP 工具补齐 (6 tools + explain_last_tick) | engine/mcp.rs | ✅ done (`aaad5fd`) |
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
| G7 | special_effect 硬编码 enum | `SpecialEffectRegistry` (字符串→handler 映射) | 🔄 H1b 实现中 | DESIGN §8.2 |

---

## H1-H2: 特殊攻击 + 回收 (DESIGN §8.2)

| 任务 | 内容 | 状态 |
|------|------|------|
| H1a | Disrupt + Fortify 特殊攻击实现 | ✅ done (`3559d8e`) |
| H2 | Recycle 命令 (回收 drone 退还 50% 资源) | ✅ done (`83e613b`) |
| H1b | Hack/Drain/Overload/Debilitate/Leech/Fabricate (通过 [[special_effects]] + [[custom_actions]] 可配置注册) | 🔄 kanban running (`t_1515f1f5`) |

**H1b 架构要求** (DESIGN §8.2 已更新):
- 新增 `[[special_effects]]` world.toml 配置段 (8 字段: name/description/handler/target/duration/resistance)
- 10 个内置 handler: hack/drain/overload/debilitate/disrupt/fortify/leech/fabricate/heal_self/scramble_commands/convert_to_structure
- `CustomActionSpecialEffect` enum → SpecialEffectRegistry (字符串→handler 映射，非硬编码)
- 全部 8 个特殊攻击在默认 world.toml 中作为 `[[custom_actions]]` 条目预注册
