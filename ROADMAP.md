# Swarm Implementation ROADMAP

> 基于 R22-R25 四轮评审收敛后的设计合同拆分。
> 设计冻结状态：B1-B4 + D1-D6 全部闭合 ✓
> 最后更新：2026-06-19

## 阶段总览

| 阶段 | 名称 | 目标 | 预计文件 |
|------|------|------|---------|
| P0 | Core Engine | Tick protocol + ECS manifest + command validation + persistence | 4 specs |
| P1 | Auth & SDK | MCP auth + tools + SDK codegen | 3 specs + SDK templates |
| P2 | World Economy | Resource ledger + world rules + economy balance | 4 specs |
| P3 | Gameplay Systems | Combat + special attacks + visibility + feedback loop | 5 specs |
| P4 | Arena Mode | Room-based matches + spectator + replay | 2 specs |
| P5 | Benchmark Gates | Synthetic benchmarks + room-partition FDB + scale validation | 3 specs |

---

## P0: Core Engine — 核心引擎

**设计合同**：`specs/core/01-tick-protocol.md`, `specs/core/06-phase2b-system-manifest.md`, `specs/core/02-command-validation.md`, `specs/core/05-persistence-contract.md`

### 任务

| ID | 任务 | 输入 | 输出 |
|----|------|------|------|
| P0-1 | Tick 循环框架 | `01-tick-protocol.md` §1-§3 | COLLECT → EXECUTE → APPLY → PERSIST 主循环 |
| P0-2 | ECS 系统调度器 | `06-phase2b-system-manifest.md` §1 (29 systems) | Serial Spine + Parallel Sets 执行引擎 |
| P0-3 | Command Collector & Validator | `02-command-validation.md` §1-§3 | 21 CommandAction 收集、校验、排序 |
| P0-4 | WASM Sandbox 集成 | `04-wasm-sandbox.md` | Worker pool + fuel metering + epoch interruption |
| P0-5 | FDB 单事务持久化 | `05-persistence-contract.md` §1-§7 | tick_head + manifest + hash chain |
| P0-6 | Snapshot 构建器 | `09-snapshot-contract.md` | fog_of_war 过滤 → WASM tick() input |
| P0-7 | RNG 确定性 PRNG | `01-tick-protocol.md` §6 | ChaCha8 per-player seed derivation |
| P0-8 | IndexMap 替换 HashMap | `01-tick-protocol.md` §5 | 确定性实体迭代顺序 |

---

## P1: Auth & SDK — 认证与开发者工具

**设计合同**：`design/auth.md`, `specs/security/03-mcp-security.md`, `specs/reference/api-registry.md` §1-§4, §6-§9, `specs/reference/codegen.md`

### 任务

| ID | 任务 | 输入 | 输出 |
|----|------|------|------|
| P1-1 | 证书颁发 & 管理 | `auth.md` §2-§5 | CA → device cert → player identity |
| P1-2 | MCP Auth 登录流 | `auth.md` §6-§8 | swarm_auth_login / refresh / logout |
| P1-3 | MCP Tools (56 Game + 11 Auth) | `api-registry.md` §3 | 67 MCP 工具实现 |
| P1-4 | SDK Codegen Pipeline | `codegen.md` | IDL YAML → Rust/TS SDK types |
| P1-5 | API Registry 生成 | `codegen.md` + IDL YAML | CI gate: 生成产物与 IDL 无漂移 |
| P1-6 | WASM CDN + 部署流 | `engine.md` §3.4.5 | deploy → validate → commit → activate |
| P1-7 | Command Source Gate | `specs/security/09-command-source.md` | MCP-only command injection, no MCP-as-gameplay |

---

## P2: World Economy — 世界经济

**设计合同**：`specs/core/08-resource-ledger.md`, `specs/core/07-world-rules.md`, `design/economy-balance-sheet.md`, `design/gameplay.md` §8

### 任务

| ID | 任务 | 输入 | 输出 |
|----|------|------|------|
| P2-1 | Resource Ledger 核心 | `08-resource-ledger.md` §1-§2 | Transfer Gateway + 定点费率 + storage tax |
| P2-2 | Empire Upkeep 系统 | `08-resource-ledger.md` §Empire Upkeep | 超线性维护费 + deficit 惩罚 |
| P2-3 | PvE Budget 分配 | `08-resource-ledger.md` §3 | 4维 budget (Global/Zone/Player/Event) |
| P2-4 | World Rules 引擎 | `07-world-rules.md` | Rhai inprocess mod loader + world.toml schema |
| P2-5 | Starting Resources & Free Upkeep | `08-resource-ledger.md` §2.3 | 新玩家经济启动补贴 |
| P2-6 | Controller Repair | `08-resource-ledger.md` §2.4 | repair_cap 35% + distance_decay |
| P2-7 | Economy Balance Verification | `economy-balance-sheet.md` | 1/5/20/50 rooms break-even 测试 |
| P2-8 | Allied Transfer & Anti-Smurf | `08-resource-ledger.md` §2.1 | 200bp fee + cooldown + identity binding |

---

## P3: Gameplay Systems — 游戏系统

**设计合同**：`specs/core/06-phase2b-system-manifest.md` §S11-S22, `design/gameplay.md`, `specs/security/05-visibility.md`, `specs/gameplay/06-feedback-loop.md`

### 任务

| ID | 任务 | 输入 | 输出 |
|----|------|------|------|
| P3-1 | Combat Pipeline (S11-S13) | `06-phase2b-system-manifest.md` §S11-S13 | Melee + Ranged + Heal parallel set |
| P3-2 | Special Attack Reducer (S14) | `06-phase2b-system-manifest.md` §S14 | Intent collect → canonical sort → deliver |
| P3-3 | Status Effects (S16-S22) | `06-phase2b-system-manifest.md` §S16-S22 | 7 status systems + per-status unique writer |
| P3-4 | Damage Application (S15) | `06-phase2b-system-manifest.md` §S15 | PendingDamage buffer → hits/DeathMark |
| P3-5 | Aging & Death (S23/S25) | `06-phase2b-system-manifest.md` §S23/S25 | lifespan + active_aging + death marker cleanup |
| P3-6 | Fog of War & Visibility | `specs/security/05-visibility.md` | drone perception + player camera + spectate |
| P3-7 | Special Attack Body Part Match | `06-phase2b-system-manifest.md` §S20 | Disrupt body part match requirement (D3/A) |
| P3-8 | Feedback Loop & UI Events | `specs/gameplay/06-feedback-loop.md` | EventLog → MCP/WebSocket push |

---

## P4: Arena Mode — 竞技模式

**设计合同**：`design/modes.md`, `design/gameplay.md` §Arena

### 任务

| ID | 任务 | 输入 | 输出 |
|----|------|------|------|
| P4-1 | Room 创建 & 配置 | `modes.md` §Arena | Create room, set parameters, lock slots |
| P4-2 | WASM Precommit | `modes.md` §Arena | module hash lock per slot |
| P4-3 | Match Lifecycle | `modes.md` §Arena | start → run → finish → archive |
| P4-4 | Social Replay Highlight | `modes.md` §Arena (D5/B) | delayed public spectator + replay URL |
| P4-5 | Local Replay | `05-persistence-contract.md` §5 | deterministic replay verifier |

---

## P5: Benchmark Gates — 容量证明

**设计合同**：`specs/core/05-persistence-contract.md` §8.3, `design/engine.md` §3.4.2

### 任务

| ID | 任务 | 输入 | 输出 |
|----|------|------|------|
| P5-1 | Command Loop Benchmark | `05-persistence-contract.md` §8.3 | 100k validate p99<50ms, 100k apply p99<100ms |
| P5-2 | Snapshot Clone/Restore | `05-persistence-contract.md` §8.3 | 50k entities clone<20ms, restore<30ms |
| P5-3 | FDB Single-TX Benchmark | `05-persistence-contract.md` §8.3 | 500 players, p99<200ms, conflict<1% |
| P5-4 | FDB Room-Partition (D6/B) | `05-persistence-contract.md` §8.1 | Room-level FDB transactions + 2PC |
| P5-5 | Pathfinding Benchmark | `05-persistence-contract.md` §8.3 | 50×50 A*, fair-share guarantee |
| P5-6 | Rollback Snapshot/Restore | `05-persistence-contract.md` §8.3 | 500 entities all components, entity ID allocator |
| P5-7 | Load Test: 1000 Players | `engine.md` §3.4.2 | Room-partition FDB, p99<500ms |

---

## 优先级与依赖

```
P0 (Core Engine) ───────────────────────────────────────────────┐
  ├── P1 (Auth & SDK) ─── 可并行 ───┐                           │
  └── P2 (World Economy) ─── 依赖 P0 ─── 可并行 ───┐            │
                                                    ├── P3 (Gameplay)
                                          依赖 P0+P2 ───┘
                                                          │
                                                    ┌─────┘
                                                    ├── P4 (Arena) ── 依赖 P0+P2+P3
                                                    └── P5 (Benchmarks) ── 可并行
```

**并行策略**：
- P1 和 P2 可与 P0 后期并行（P0-5 持久化完成后）
- P3 依赖 P0+P2（需要 Command + Resource Ledger）
- P4 和 P5 在 P3 中期启动

---

## Milestones

| Milestone | 判定 | 包含阶段 |
|-----------|------|---------|
| **M1: Core Deterministic** | 单 tick 完整 cycle COLLECT→EXECUTE→APPLY→PERSIST，RNG 确定性，state checksum 一致 | P0 |
| **M2: Player Can Login & Deploy** | 证书登录 → MCP tools → WASM deploy → tick() 运行 | P0 + P1 |
| **M3: World Economy Live** | Resource Ledger + upkeep + storage tax + starting resources | P0 + P1 + P2 |
| **M4: Gameplay Complete** | Combat + special attacks + status effects + visibility | P0-P3 |
| **M5: Arena Match Works** | 完整 room 创建→比赛→replay 流程 | P0-P4 |
| **M6: Scale Verified** | 全部 9 项 benchmark gates 通过 | P0-P5 |
