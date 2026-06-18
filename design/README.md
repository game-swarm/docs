# Swarm — 设计文档

> **Swarm** 是一个开源的、可编程的 MMO RTS 游戏引擎。它是 [Screeps](https://screeps.com/) 的精神续作，用现代技术栈从零重构，支持多语言。
>
> — *「你的代码就是你的军队。Write once, fight forever.」*

## 文档导航

| 域 | 文档 | 内容 |
|:--|:--|:--|
| **引擎架构** | [`design/engine.md`](engine.md) | Tick 生命周期、ECS 系统链、世界拓扑、快照模型、确定性保证、快照扩展路线、Move-as-action 设计理由 |
| **游戏机制** | [`design/gameplay.md`](gameplay.md) | Vanilla Ruleset、身体部件、伤害类型、特殊攻击（8 种）、经济模型、Controller/建筑系统 |
| **游戏模式** | [`design/modes.md`](modes.md) | World 持久世界 vs Arena 竞技场、PvE 生态层、Arena PvE Challenge |
| **MCP 与 API** | [`design/interface.md`](interface.md) | MCP 接口架构、Game API deferred command model、SDK |
| **用户认证** | [`design/auth.md`](auth.md) | 应用层证书、CSR、passkey/email/admin 恢复、联邦跨世界身份、账号生命周期 |
| **技术选型** | [`design/tech-choices.md`](tech-choices.md) | 各子系统技术栈对比与选型理由 |
| **技术规范** | [`specs/`](../specs/) | 技术规范，按域分 core/security/gameplay/future |
| **API 参考** | [`specs/reference/`](../specs/reference/) | 面向开发者的接口文档 |
| **运维手册** | [`RUNBOOK.md`](../RUNBOOK.md) | 启动序列、降级模式、备份恢复、监控 |

---

## 1. 愿景

### 1.1 核心理念

Swarm 是一个**编程竞技场**——玩家编写真实代码来控制自主单位（drone），在一个持久共享世界中运行。与传统 RTS 不同，Swarm 的胜负不取决于手速，而取决于**算法思维、系统设计和资源优化**。

Swarm 支持两种玩家：
- **人类程序员**：通过 Web UI（Monaco 编辑器 + PixiJS 渲染）编写代码，编译为 WASM 部署
- **AI agent**：通过 MCP 接口查看世界、生成代码、部署 WASM——与人类走完全相同路径

世界只认 WASM。不论代码是谁写的。

Swarm 不是单个游戏，而是一个**可配置游戏引擎平台**。每个世界实例是一个独立 universe，有各自的规则集（world.toml）、资源体系、身体部件、建筑类型和特殊攻击——所有内容都是可配置的官方扩展，非引擎硬编码。世界之间形成**联邦宇宙**：联邦仅 identity-only——玩家可在多个世界间使用同一身份认证。资源/排名跨世界不在当前设计范围内。

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
                            │
            WebSocket + REST │ HTTPS (MCP)
                            ▼
┌─────────────────────────────────────────────────────────┐
│                   网关 (Go)                                │
│  ┌──────────────┐  ┌─────────────┐  ┌───────────────┐  │
│  │ WS Hub        │  │ Auth (CA/CSR)│  │ API Router     │  │
│  └──────────────┘  └─────────────┘  └───────────────┘  │
└────────────────────────┬────────────────────────────────┘
                         │ gRPC + NATS
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
│  │ (rmcp, HTTP/SSE)  │  │ Collector     │                 │
│  └───────────────────┘  └───────────────┘                 │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                   数据层                                   │
│  ┌──────────────┐  ┌─────────────┐  ┌───────────────┐  │
│  │ FoundationDB  │  │ Dragonfly    │  │ ClickHouse     │  │
│  │ (世界状态)    │  │ (热缓存)     │  │ (分析 + 审计)  │  │
│  └──────────────┘  └─────────────┘  └───────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 2.2 仓库结构

```
swarm/
├── docs/           # 设计文档、技术规范
│   ├── design/     #   架构设计（本目录）
│   ├── specs/      #   技术规范 (core/ security/ gameplay/ future/)
│   ├── specs/reference/        #   API 参考
│   └── security/   #   安全策略
├── engine/         # Rust 游戏引擎 — Bevy ECS, Tick 调度, 世界模拟
├── sandbox/        # WASM 沙箱运行时 — 编译服务, 模块管理, 安全审计
├── gateway/        # Go API 网关 — WebSocket, REST, gRPC, 认证
├── frontend/       # Web 客户端 — Monaco Editor, PixiJS 渲染
├── sdk-ts/         # TypeScript SDK — 游戏 API 类型 + WASM 编译工具链
└── sdk-rust/       # Rust SDK — 游戏 API + wasm-bindgen 工具链
```

---

## 3. 数据模型

### FoundationDB — 世界状态

FoundationDB 提供严格可序列化事务。每 tick 原子提交，保证世界状态一致性和回放验证。

| 数据 | 存储位置 | 访问模式 |
|------|---------|---------|
| 世界状态 | FDB | 每 tick 原子写入, 启动恢复 |
| 热缓存 | Dragonfly | 高频读取, 允许 ≤2 tick 滞后 |
| TickTrace | FDB | 不可变, 仅追加 |
| 分析数据 | ClickHouse | 聚合查询, 排行榜, 审计 |

### 回放数据

| 路径 | 内容 |
|------|------|
| `/tick/{N}/commands` | 排序后的 RawCommand |
| `/tick/{N}/state` | tick 后世界状态 |
| `/tick/{N}/rejections` | 被拒绝指令及原因 |
| `/tick/{N}/metrics` | TickMetrics |
| `/tick/{N}/mods_lock` | 模组版本哈希集 |
| `/tick/{N}/world_config` | world.toml 快照 |

---

## 4. 贡献指南

### 4.1 开发环境搭建

```bash
git clone git@git.kagurazakalan.com:swarm/engine.git
cd engine && docker-compose up
```

### 4.2 代码规范

- Rust: `cargo fmt` + `cargo clippy`（严格）
- Go: `gofmt` + `golangci-lint`
- TypeScript: `prettier` + `eslint`（严格）
- Commit: [Conventional Commits](https://www.conventionalcommits.org/)

### 4.3 文档约定

见 [`AGENTS.md`](../AGENTS.md) — AI agent 处理本仓库时应遵循的约定。

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
