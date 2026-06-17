# Swarm — 设计文档

可编程 MMO RTS 游戏引擎的设计文档仓库。

## 快速入口

| 我想… | 看这里 |
|:--|:--|
| 了解项目愿景和架构全景 | [`design/README.md`](design/README.md) |
| 理解引擎如何工作（Tick/ECS/快照） | [`design/engine.md`](design/engine.md) |
| 查看游戏机制（身体部件/伤害/特殊攻击） | [`design/gameplay.md`](design/gameplay.md) |
| 了解 World vs Arena 模式 + PvE | [`design/modes.md`](design/modes.md) |
| 查看 MCP 接口和 Game API | [`design/interface.md`](design/interface.md) |
| 查阅技术选型理由 | [`design/tech-choices.md`](design/tech-choices.md) |
| 查看技术规范 | [`specs/`](specs/) — core / security / gameplay / future |
| 查阅 API 参考 | [`specs/reference/`](specs/reference/) — commands / host functions / MCP tools |
| 学习贡献约定 | [`AGENTS.md`](AGENTS.md) |
| 运维部署 | [`RUNBOOK.md`](RUNBOOK.md) |
| 5 分钟快速上手 | [`GETTING-STARTED.md`](GETTING-STARTED.md) |


## 目录结构

```
docs/
├── design/
│   ├── README.md          导航入口 — 愿景 + 架构全景 + 域文件索引
│   ├── engine.md          引擎架构 — Tick/ECS/快照/确定性/扩展路线
│   ├── gameplay.md        游戏机制 — Vanilla/身体部件/伤害/特殊攻击/经济
│   ├── modes.md           游戏模式 — World vs Arena + PvE
│   ├── interface.md       MCP + Game API
│   └── tech-choices.md    技术选型对比
├── specs/
│   ├── core/              核心引擎规范 (tick/命令/WASM/世界规则)
│   ├── security/          安全规范 (MCP/可见性/来源/CVE-SLA)
│   ├── gameplay/          游戏规范 (反馈循环/API IDL)
│   ├── future/            扩展路线 (T2 增量快照/T3 分片)
│   ├── reference/         API 参考 (commands/host-functions/mcp-tools)
│   └── 12-gateway-protocol.md  Gateway 协议
├── AGENTS.md              AI agent 约定
├── RUNBOOK.md             运维手册
├── GETTING-STARTED.md     入门指南
└── README.md              本文件
```

## 代码仓库

| 仓库 | 说明 |
|------|------|
| [swarm/engine](https://git.kagurazakalan.com/swarm/engine) | Rust 游戏引擎 |
| [swarm/sandbox](https://git.kagurazakalan.com/swarm/sandbox) | WASM 沙箱运行时 |
| [swarm/sdk-ts](https://git.kagurazakalan.com/swarm/sdk-ts) | TypeScript SDK |
| [swarm/sdk-rust](https://git.kagurazakalan.com/swarm/sdk-rust) | Rust SDK |
| [swarm/gateway](https://git.kagurazakalan.com/swarm/gateway) | Go API 网关 |
| [swarm/frontend](https://git.kagurazakalan.com/swarm/frontend) | Web 客户端 |

## 许可证

MIT
