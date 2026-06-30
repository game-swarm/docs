# Swarm — 设计文档

可编程 MMO RTS 游戏引擎的设计文档仓库。

## 快速入口

| 我想… | 看这里 |
|:--|:--|
| 了解项目愿景和架构全景 | [`design/README.md`](design/README.md) |
| 查看实施进度和任务计划 | 主仓库 `ROADMAP.md` |
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
├── ROADMAP.md              实施进度追踪（位于主仓库）
├── AGENTS.md               AI agent 约定
├── RUNBOOK.md              运维手册
├── GETTING-STARTED.md      入门指南
└── README.md               本文件
```

## Domain Authority Map

| Domain | Authority |
|--------|-----------|
| API tools / RejectionReason / CommandAction / Host Functions | IDL YAML + generated API Registry |
| Economy parameters / formulas | Resource Ledger + generated economy schema |
| Body/structure costs | generated cost table from IDL/Registry |
| Special attacks | `specs/reference/special-attack-table.md` |
| Tick schedule / ECS R/W | `specs/core/phase2b-system-manifest.md` + mod plugin policy |
| Snapshot truncation | `specs/core/snapshot-contract.md` + visibility oracle |
| Persistence/replay retention | `specs/core/persistence-contract.md` + world.toml config |
| Security transport/authz/rate | security specs + machine-readable Registry fields |

## 代码仓库

### 核心

| 仓库 | 说明 |
|------|------|
| [swarm/engine](https://git.kagurazakalan.com/swarm/engine) | Rust 游戏引擎 (Bevy ECS) |
| [swarm/sandbox](https://git.kagurazakalan.com/swarm/sandbox) | WASM 沙箱运行时 (Wasmtime) |
| [swarm/gateway](https://git.kagurazakalan.com/swarm/gateway) | Rust API 网关 |
| [swarm/frontend](https://git.kagurazakalan.com/swarm/frontend) | Web 客户端 (Monaco + PixiJS) |

### 官方模组（Vanilla Mods）

每个模组 = 独立 Rust crate 仓库（`Cargo.toml` + `mod.toml`），engine 通过 git submodule 引用并静态编译为 Bevy Plugin。
模组开发模板：[swarm/mod-template](https://git.kagurazakalan.com/swarm/mod-template)。

| 模组 | 默认 | 说明 |
|------|:----:|------|
| [mod-empire-upkeep](https://git.kagurazakalan.com/swarm/mod-empire-upkeep) | ✅ on | 帝国维护费 + Controller Repair + Recycle |
| [mod-fog-of-war](https://git.kagurazakalan.com/swarm/mod-fog-of-war) | ✅ on | 可见性 + 感知 + Oracle 防线 |
| [mod-resource-decay](https://git.kagurazakalan.com/swarm/mod-resource-decay) | ❌ off | 存储资源自然衰减 |
| [mod-pve-spawning](https://git.kagurazakalan.com/swarm/mod-pve-spawning) | ✅ on | NPC 出生 + PvE 难度梯度 |
| [mod-combat-core](https://git.kagurazakalan.com/swarm/mod-combat-core) | ✅ on | 战斗 + 死亡 + 再生 |
| [mod-special-attacks](https://git.kagurazakalan.com/swarm/mod-special-attacks) | ✅ on | Hack/Drain/Overload/Debilitate/Disrupt/Fortify |
| [mod-depot-storage](https://git.kagurazakalan.com/swarm/mod-depot-storage) | ✅ on | Depot 维修 + 全局存储 + 物流 |

## 许可证

MIT
