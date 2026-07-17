# Swarm — 设计文档

可编程 MMO RTS 游戏引擎的设计文档仓库。

## 快速入口

| 我想… | 看这里 |
|:--|:--|
| 了解项目愿景和架构全景 | [`design/README.md`](design/README.md) |
| 查看实施进度和任务计划 | 各代码仓库自己的 `ROADMAP.md`（如存在） |
| 理解引擎如何工作（Tick/ECS/快照） | [`design/engine.md`](design/engine.md) |
| 查看游戏机制（身体部件/伤害/特殊攻击） | [`design/gameplay.md`](design/gameplay.md) |
| 了解 World vs Arena 模式 + PvE | [`design/modes.md`](design/modes.md) |
| 查看 MCP 接口和 Game API | [`design/interface.md`](design/interface.md) |
| 查阅技术选型理由 | [`design/tech-choices.md`](design/tech-choices.md) |
| 查看技术规范 | [`specs/`](specs/) — core / security / gameplay / reference |
| 查阅 API 参考 | [`specs/reference/`](specs/reference/) — commands / host functions / MCP tools |
| 学习贡献约定 | [`AGENTS.md`](AGENTS.md) |
| 运维部署 | [`RUNBOOK.md`](RUNBOOK.md) |
| 5 分钟快速上手 | [`GETTING-STARTED.md`](GETTING-STARTED.md) |

## 技术规范索引

- **Core**: [Tick Protocol](specs/core/tick-protocol.md) · [Command Validation](specs/core/command-validation.md) · [Shard Protocol](specs/core/shard-protocol.md) · [World Rules](specs/core/world-rules.md) · [WASM Sandbox](specs/core/wasm-sandbox.md) · [Distributed Sandbox](specs/core/distributed-sandbox.md) · [Mod Runtime](specs/core/mod-runtime.md) · [Phase 2b System Manifest](specs/core/phase2b-system-manifest.md) · [Incremental Snapshot](specs/core/incremental-snapshot.md) · [Snapshot Contract](specs/core/snapshot-contract.md) · [Persistence Contract](specs/core/persistence-contract.md) · [Resource Ledger](specs/core/resource-ledger.md)
- **Security**: [MCP Security](specs/security/mcp-security.md) · [Gateway Protocol](specs/security/gateway-protocol.md) · [Visibility](specs/security/visibility.md) · [Command Source](specs/security/command-source.md) · [CVE SLA](specs/security/CVE-SLA.md)
- **Gameplay**: [API IDL](specs/gameplay/api-idl.md) · [Feedback Loop](specs/gameplay/feedback-loop.md) · [Playtest Gates](specs/gameplay/PLAYTEST-GATED.md)
- **Reference**: [API Registry](specs/reference/api-registry.md) · [Commands](specs/reference/commands.md) · [Host Functions](specs/reference/host-functions.md) · [MCP Tools](specs/reference/mcp-tools.md) · [Special Attack Table](specs/reference/special-attack-table.md) · [Codegen](specs/reference/codegen.md)

## 目录结构

```
docs/
├── design/
│   ├── README.md           导航入口 — 愿景 + 架构全景 + 域文件索引
│   ├── engine.md           引擎架构 — Tick/ECS/快照/确定性/扩展能力
│   ├── gameplay.md         游戏机制 — Vanilla/身体部件/伤害/特殊攻击/经济/模组
│   ├── modes.md            游戏模式 — World vs Arena + PvE
│   ├── interface.md        MCP + Game API
│   ├── tech-choices.md     技术选型对比
│   ├── auth.md             认证架构 — Ed25519 证书链
│   └── economy-balance-sheet.md  经济平衡表
├── specs/
│   ├── core/               核心引擎规范 (tick/命令/WASM/世界规则/持久化/快照/ECS)
│   ├── security/           安全规范 (MCP/可见性/来源/CVE-SLA)
│   ├── gameplay/           游戏规范 (反馈循环/API IDL)
│   ├── reference/          API 参考 (commands/host-functions/mcp-tools/codegen)
├── AGENTS.md               AI agent 约定
├── RUNBOOK.md              运维手册
├── GETTING-STARTED.md      入门指南
└── README.md               本文件
```

## Domain Authority Map

| Domain | Authority |
|--------|-----------|
| API tools / RejectionReason / CommandAction / Host Functions | IDL YAML + manually maintained API Registry publication |
| Economy parameters / formulas | Resource Ledger + economy IDL schema |
| Body/structure costs | IDL/Registry reference tables |
| Special attacks | `specs/reference/special-attack-table.md` |
| Tick schedule / ECS R/W | `specs/core/phase2b-system-manifest.md` + mod plugin policy |
| Snapshot truncation | `specs/core/snapshot-contract.md` + visibility oracle |
| Persistence/replay retention | `specs/core/persistence-contract.md` + world.toml config |
| Security transport/authz/rate | security specs + machine-readable Registry fields |

## 代码仓库

Swarm 没有单一主仓库。每个代码仓库自包含自己的源码、构建配置、README、测试和发布流程；本文档仓库只描述跨组件协议与目标架构。

### 核心

| 仓库 | 说明 |
|------|------|
| [game-swarm/engine](https://github.com/game-swarm/engine) | Rust 游戏引擎 (Bevy ECS) |
| [game-swarm/sandbox](https://github.com/game-swarm/sandbox) | WASM 沙箱运行时 (Wasmtime) |
| [game-swarm/gateway](https://github.com/game-swarm/gateway) | Rust API 网关 |
| [game-swarm/frontend](https://github.com/game-swarm/frontend) | Web 客户端 (Monaco + PixiJS) |

### 官方模组（Vanilla Mods）

模组是独立 Rust crate（`Cargo.toml` + `mod.toml`）。Engine 可在本地把模组检出到 `mods/` 并通过 workspace 成员引入，作为 Bevy Plugin 静态编译进引擎。
模组开发参考已合并至[引擎文档](design/engine.md)。

| 模组 | 默认 | 说明 |
|------|:----:|------|
| mod-empire-upkeep | ✅ on | 帝国维护费 + Controller Repair + Recycle |
| mod-fog-of-war | ✅ on | 可见性 + 感知 + Oracle 防线 |
| mod-resource-decay | ✅ on | 存储资源自然衰减 |
| mod-pve-spawning | ✅ on | NPC 出生 + PvE 难度梯度 |
| mod-combat-core | ✅ on | 战斗 + 死亡 + 再生 |
| mod-special-attacks | ✅ on | Hack/Drain/Overload/Debilitate/Disrupt/Fortify/Leech/Fabricate |
| mod-depot-storage | ✅ on | Depot 维持 + 全局存储 + 物流 |
| mod-vanilla-boss | ✅ on | Arena/World Boss 规则 |

## 服务架构

Swarm 由以下核心服务组成：

- **Engine**: 游戏模拟引擎。
- **Sandbox**: 用户代码隔离运行环境。
- **Gateway**: API 与消息路由。
- **Frontend**: 玩家控制台。
