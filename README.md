# Swarm — 设计文档

可编程 MMO RTS 游戏引擎的设计文档仓库。

进度追踪 → [ROADMAP.md](ROADMAP.md)

## 目录结构

```
docs/
├── ROADMAP.md                   # 模块化实施追踪
├── RUNBOOK.md                   # 运维手册
├── design/
│   ├── DESIGN.md                # 架构全景 + 游戏设计
│   └── tech-choices.md          # 技术选型
├── specs/p0/                    # P0 冻结规范 (9 份)
├── security/CVE-SLA.md          # Wasmtime CVE 响应 SLA
└── reviews/                     # 评审档案 (R1-R14)
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
