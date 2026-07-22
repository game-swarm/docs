# Swarm — 设计文档

> **Swarm** 是一个开源的、可编程的 MMO RTS 游戏引擎，受 [Screeps](https://screeps.com/) 启发，使用现代技术栈从零构建，并支持多语言。
>
> — *「你的代码就是你的军队。Write once, fight forever.」*

## 文档导航

| 域 | 文档 | 内容 |
|:--|:--|:--|
| **整体架构** | [`design/architecture.md`](architecture.md) | 两层计算模型（WASM COLLECT + Engine EXECUTE）、redb/NATS 基础设施选型、数据流全景 |
| **引擎架构** | [`design/engine.md`](engine.md) | Tick 生命周期、ECS 系统链、世界拓扑、快照模型、确定性保证、快照扩展路线、Move-as-action 设计理由 |
| **游戏机制** | [`design/gameplay.md`](gameplay.md) | Vanilla Ruleset、身体部件、伤害类型、特殊攻击（8 种）、经济模型、Controller/建筑系统；平衡目标见 [`economy-balance-sheet.md`](economy-balance-sheet.md) |
| **游戏模式** | [`design/modes.md`](modes.md) | World 持久世界 vs Arena 竞技场、PvE 生态层、Arena PvE Challenge |
| **MCP 与 API** | [`design/interface.md`](interface.md) | MCP 接口架构、Game API command-intent model、SDK |
| **用户认证** | [`design/auth.md`](auth.md) | 应用层证书、CSR、Server CA、联邦跨世界身份、账号生命周期 |
| **技术选型** | [`design/tech-choices.md`](tech-choices.md) | 各子系统技术栈对比与选型理由 |

---

## 文档边界

`design/` 是 Swarm 目标状态的唯一上游。它必须自包含地裁定外部可观察行为、默认值、协议边界、信任模型和兼容策略，不得把下游 spec、IDL、Registry 或当前实现当作决策来源。

下游 specs 从 design 派生可执行合同，可以补充编码、数据结构、存储布局和执行步骤等内部细节，但不得新增或改变 design 未裁定的外部行为。API design 拥有能力语义与信任边界；下游 IDL 拥有字段、类型、错误码和 wire schema。`GAME_API_VERSION`、`AUTH_API_VERSION`、`ECONOMY_API_VERSION`、`PLUGIN_ABI_VERSION` 与实现 crate 的 package version 是相互独立、显式命名的版本域。

---

## 1. 愿景

### 1.1 核心理念

Swarm 是一个**编程竞技场**——玩家编写真实代码来控制自主单位（drone），在一个持久共享世界中运行。与传统 RTS 不同，Swarm 的胜负不取决于手速，而取决于**算法思维、系统设计和资源优化**。

Swarm 支持两种玩家：
- **人类程序员**：通过 Web UI（Monaco 编辑器 + PixiJS 渲染）编写代码，编译为 WASM 部署
- **AI agent**：通过 MCP 接口查看世界、生成代码、部署 WASM——与人类走完全相同路径

世界只认 WASM。不论代码是谁写的。

Swarm 不是单个游戏，而是一个**可配置游戏引擎平台**。每个世界实例是一个独立 universe，有各自的规则集（world.toml）、资源体系、身体部件、建筑类型和特殊攻击——所有内容都是可配置的官方扩展，非引擎硬编码。世界之间形成**联邦宇宙**：联邦仅 identity-only——玩家可在多个世界间使用同一身份认证。资源/排名跨世界不在目标设计范围内。

### 1.2 与 Screeps 的关键区别

| 维度 | Screeps | Swarm |
|------|---------|-------|
| **玩家语言** | 仅 JavaScript | **任意语言 → WASM** |
| **沙箱** | V8 Isolate (isolated-vm) | WASM + WASI（Wasmtime，独立进程隔离） |
| **资源计量** | 墙钟 CPU 限制 | **CPU 指令计数**（fuel metering） |
| **游戏模型** | OOP 脚本模式 | **ECS**（Bevy）— 确定性、可并行、可回放 |
| **性能** | 受限于 V8 GC | WASM 原生速度，同等配额快 10-100 倍 |
| **AI 玩家** | 无原生支持 | **MCP 原生界面**——AI 写 WASM，同人类 |
| **扩展性** | 仅 JS mod | WASM 多语言 SDK + 插件系统 |
| **客户端** | Web + Steam 封装浏览器 | Web（Monaco + PixiJS）+ MCP（AI 界面） |

### 1.3 设计原则

1. **语言无关**：引擎不知道也不关心玩家代码是什么语言写的。一切编译为 WASM。
2. **确定性核心**：相同初始状态 + 相同玩家指令 → 相同世界状态。支撑回放、调试和反作弊。
3. **公平资源核算**：CPU 配额度量为 WASM 指令数，非墙钟。C 玩家和 Python 玩家在相同配额下获得同等算力。AI 玩家和人类玩家同走 WASM 沙箱，天然公平。
4. **可组合架构**：ECS 允许新增游戏机制时无需触碰既有代码。
5. **开源首日**：MIT 许可证。
6. **设计即终态**：设计文档只描述已裁定的目标状态。每个设计决策必须按当下最佳实践一次性裁定。禁止基于工程难度、工期或工作量做分期取舍；当下能裁定的必须在当下裁定。仅硬外部条件（playtest 数据、外部 API 可用性等实证依赖）可 gate 数值校准和平衡性验证。实现顺序只属于 ROADMAP，不得写进 DESIGN/spec/reference。

---

## 2. 系统架构

### 2.1 整体架构图

```
┌──────────────────────────────────────────────────────────┐
│                        客户端                               │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐ │
│  │ Web Client   │  │ Desktop App   │  │ CI/CD Pipeline   │ │
│  │ (Monaco +    │  │ (Tauri)       │  │ (GitHub Actions) │ │
│  │  PixiJS)     │  │               │  │                  │ │
│  └──────┬───────┘  └──────┬───────┘  └────────┬────────┘ │
│         │                 │                    │           │
│  ┌──────┴─────────────────┴────────────────────┴────────┐ │
│  │                   MCP Interface (AI 玩家)              │ │
│  │  AI agent 查看世界 · 生成代码 · 部署 WASM · 调试       │ │
│  └────────────────────────┬─────────────────────────────┘ │
└───────────────────────────┼───────────────────────────────┘
                            │ WebSocket /ws + HTTP POST /mcp
                            ▼
┌─────────────────────────────────────────────────────────┐
│                   网关 (Rust)                              │
│  ┌──────────────┐  ┌─────────────┐  ┌───────────────┐  │
│  │ WS Hub        │  │ Sig Verify   │  │ API Router     │  │
│  └──────────────┘  └─────────────┘  └───────────────┘  │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP /mcp + NATS realtime
                         ▼
┌─────────────────────────────────────────────────────────┐
│                Tick 引擎 (Rust)                            │
│                                                           │
│  ┌──────────────────────────────────────────────────┐   │
│  │              Tick 调度器                            │   │
│  │  Tick N-1 完成 → Tick N 分发 → Tick N+1           │   │
│  └──────────────────────┬───────────────────────────┘   │
│                         │                                 │
│          ┌──────────────┼──────────────┐                 │
│          ▼              ▼              ▼                  │
│  ┌─────────────┐ ┌────────────┐ ┌──────────────┐        │
│  │ Sandbox     │ │ Sandbox    │ │ Sandbox      │  ...   │
│  │ Worker 1    │ │ Worker 2   │ │ Worker 3     │        │
│  │ (独立进程)   │ │ (独立进程)  │ │ (独立进程)    │        │
│  │ WASM 玩家 1 │ │ WASM 玩家2 │ │ WASM 玩家 3  │        │
│  └──────┬──────┘ └─────┬──────┘ └──────┬───────┘        │
│         │              │               │                 │
│         ▼              ▼               ▼                 │
│  ┌──────────────────────────────────────────────────┐   │
│  │         指令收集器 + 校验器 + 反作弊               │   │
│  │    (去重、冲突解决、反作弊)                        │   │
│  └──────────────────────┬───────────────────────────┘   │
│                         │                                 │
│  ┌──────────────────────▼───────────────────────────┐   │
│  │              Bevy ECS 世界                         │   │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌───────────┐  │   │
│  │  │ 移动   │ │ 战斗   │ │ 经济   │ │ 建造      │  │   │
│  │  │ System │ │ System │ │ System │ │ System    │  │   │
│  │  └────────┘ └────────┘ └────────┘ └───────────┘  │   │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌───────────┐  │   │
│  │  │ 视野   │ │ 资源   │ │ 寻路   │ │ 死亡      │  │   │
│  │  │ System │ │ System │ │ System │ │ System    │  │   │
│  │  └────────┘ └────────┘ └────────┘ └───────────┘  │   │
│  └──────────────────────────────────────────────────┘   │
│                                                           │
│  ┌───────────────────┐  ┌───────────────┐                 │
│  │ MCP Server        │  │ Debug/Trace   │                 │
│  │ (MCP over HTTP)   │  │ Collector     │                 │
│  └───────────────────┘  └───────────────┘                 │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                   数据层                                   │
│  ┌──────────────┐  ┌─────────────┐  ┌───────────────┐  │
│  │ redb  │  │ Moka Cache   │  │ redb metrics  │  │
│  │ (世界状态)    │  │ (进程内热缓存) │  │ (分析 + 审计)  │  │
│  └──────────────┘  └─────────────┘  └───────────────┘  │
└─────────────────────────────────────────────────────────┘
```

Auth Service 是独立的有状态控制面，负责 CA/CSR 与证书生命周期；Gateway 只执行无状态请求签名验证，不托管 CA 私钥或证书签发状态。

### 2.2 仓库结构

```
swarm/
├── docs/design/    # 目标状态决策（本目录，唯一上游）
├── engine/         # Rust 游戏引擎 — Bevy ECS, Tick 调度, 世界模拟
├── mods/           # vanilla 内置模组源码；发布时打包为签名 .swarm-mod 制品
├── sandbox/        # WASM 沙箱运行时 — 编译服务, 模块管理, 安全审计
├── gateway/        # Rust API 网关 — WebSocket, HTTP, 认证
├── frontend/       # Web 客户端 — Monaco Editor, PixiJS 渲染
├── engine/sdk-templates/ts/    # TypeScript SDK 模板 — CommandIntent + tick 输出校验
└── engine/sdk-templates/rust/  # Rust SDK 模板 — 生成的 commands + Snapshot/types + tick bot
```

**模组发布**：vanilla 内置模组以源码目录维护，发布时 CI 执行 `swarm mod pack` 产出 Ed25519 签名的 `.swarm-mod` 单文件包，随 engine release 分发。服主通过 `swarm mod install-vanilla` 一键安装。第三方模组遵循相同发布格式：开发用源码仓库，发布用 `.swarm-mod` 签名包。

---

## 3. 数据模型

### redb — 权威状态与永久 replay history

redb 提供嵌入式 ACID WriteTransaction。每 tick 原子提交当前世界状态和 replay-critical history。Commands、rejections、world config/mod version transitions、deploy activation decisions 与校验 hash 在世界整个生命周期内永久保留，使对象存储全部丢失后仍可从 genesis 确定性 replay。

| 数据 | 存储位置 | 访问模式 |
|------|---------|---------|
| 当前世界状态 | redb | 每 tick 原子写入，启动恢复 |
| Replay-critical history | redb | 世界生命周期内永久、仅追加；可压缩索引但不得删除语义 |
| 热缓存 | Engine 进程内 Moka Cache | 高频读取，可重建 |
| Snapshot delta / ReplayArtifact / RichTraceBlob | Blob Store | 恢复加速与 rich audit，非状态权威 |
| 完整 keyframe | Keyframe Store | 恢复加速，主副本存储，非 replay 权威 |
| 分析数据 | redb metrics table | 聚合查询与审计；World 不生成公开竞争排名 |

### 回放数据

| 路径 | 内容 |
|------|------|
| `/tick/{N}/commands` | 排序后的 RawCommand |
| `/tick/{N}/state_checksum` | tick 后权威状态校验 hash |
| `/tick/{N}/rejections` | 被拒绝指令及原因 |
| `/tick/{N}/metrics` | TickMetrics |
| `/tick/{N}/mods_lock` | 模组版本哈希集 |
| `/tick/{N}/world_config` | world.toml 快照 |

Keyframe 和 delta 可以把恢复起点前移，但 deterministic replay 不依赖它们存在。活动 WASM artifact 属于 operational-critical、非 state-authoritative 数据；对象丢失时只暂停受影响玩家模块并提交 empty commands，世界和其他玩家继续推进。

---

## 4. 贡献指南

### 4.1 开发环境搭建

```bash
git clone https://github.com/game-swarm/engine.git
cd engine
cargo run
```

### 4.2 代码规范

- Rust: `cargo fmt` + `cargo clippy`（严格）
- Rust Gateway: `cargo fmt` + `cargo clippy`
- TypeScript: `prettier` + `eslint`（严格）
- Commit: [Conventional Commits](https://www.conventionalcommits.org/)

### 4.3 文档约定

见 [`AGENTS.md`](../AGENTS.md) — AI agent 处理文档仓库时应遵循的约定。

---

## 附录 A: 与 Screeps 的 API 兼容性

Swarm 不追求与 Screeps API 兼容。设计哲学不同：

- Screeps API 是面向对象的（`creep.moveTo()`, `Game.spawns['Spawn1']`）
- Swarm API 是功能/数据导向的（`move(creep_id, direction)`, return commands）

但可以通过社区项目构建兼容层，将 Screeps 风格 API 调用包装为 Swarm 指令。

## 附录 B: 为什么不用现有 Screeps 方案？

| 关注点 | Screeps | Swarm |
|--------|---------|-------|
| 语言锁定 | 仅 JS | 任意 WASM 语言 |
| 性能上限 | V8 + GC 停顿 | WASM 原生速度 |
| CPU 计量精度 | 墙钟（系统依赖） | Fuel metering（确定性） |
| 确定性 | 不保证 | 设计目标 |
| AI 玩家 | 无 | MCP 原生界面 |
| 代码年代 | 2014 起步，Node.js 8 | 2026，Rust + WASM |
| 许可证 | 混合（server 开源，client 专有） | MIT（完全开源） |

---

## 附录 C: 术语表（Glossary）

以下术语在多个文档中出现且含义有微妙差异。本文档为权威消歧义源：

| 术语 | 定义 | 存储层 |
|------|------|--------|
| `TickCommitRecord` | redb WriteTransaction 内原子提交的 replay-critical 子集——仅包含状态 checksum、命令哈希列表、rejection 计数、fuel 扣费、attempt_id。不包含 rich debug detail。 | redb |
| `RichTraceBlob` | 完整 TickTrace 序列化（含 debug_detail、rich events、per-system metrics、overload pressure 等非关键信号）。可降级、可延迟写入、可丢失而不影响 replay 正确性。 | Blob Store |
| `ReplayArtifact` | 供回放验证器使用的自包含 bundle：包含 TickCommitRecord + snapshot delta + 必要的 seed material。CI 和反作弊审计使用此格式。 | Blob Store |
| `RawCommand` | WASM 输出 + 服务端注入的 player_id/tick/source/auth context。预校验阶段的输入。 | 内存 → redb trace |
| `CommandIntent` | ABI v2 `TickResult.commands` 中的玩家指令——含 `sequence`、required `idempotency_key`、optional `client_trace_id` 与 `action`。不可信，不含任何服务端字段。 | 内存（COLLECT 阶段） |
| `ValidatedCommand` | RawCommand 通过预校验后的形式——携带解析后的目标引用、距离、成本缓存。 | 内存 → 应用阶段 |
| `DeployPayload` | Canonical structured context：`domain=SWARM-DEPLOY-V1`、wasm_hash、metadata_hash、player_id、world_id、module_slot、version_counter、transport、signed_at。证书 audience 单独校验。 | redb replay-critical history |
| `WasmModuleArtifact` | 由 DeployPayload 引用的 WASM binary、manifest 和 compiled execution artifact。它不是状态权威；丢失时只暂停受影响玩家模块。 | Blob Store（operational-critical，主副本） |
| `PendingEntityCreation` | accepted Build/Spawn/Fabricate 的待创建实体记录。S06 Spawn 先写 `ProvisionalSpawnRequest`；S08 接受后追加 Spawn creation；tick-end creation flush 是唯一 materializer，新实体下 tick 才可见/可交互。 | 内存 → redb |
| `TickInputEnvelope` | 每 tick COLLECT 输入封套：module_hash、wasmtime_version、fuel_schedule_version、snapshot_hash、commands_hash、system_manifest_hash、world_action_manifest_hash、world_config_hash、mods_lock_hash、deploy/rollback/admin events、terminal_state。确保回放输入完整性。 | redb |
| `redb_version_counter` | redb 在 deploy manifest commit 时分配的全局单调 total-order counter，供 replay 排序。它不同于客户端签名的 `DeployPayload.version_counter`：后者在 `(player_id, world_id, module_slot)` 域内防重放。 | redb |

所有文档中的 `TickTrace` 统称指向以上三种记录的集合——具体指向哪一层取决于上下文（replay-critical → TickCommitRecord，debug → RichTraceBlob，回放 → ReplayArtifact）。
