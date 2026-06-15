# Swarm — 设计文档

可编程 MMO RTS 游戏引擎的设计文档仓库。**模块化追踪中**（2026-06-15 审计）— B6-B11 缺口补齐进行中。

## 代码仓库

| 仓库 | 说明 | 状态 |
|------|------|------|
| [swarm/engine](https://git.kagurazakalan.com/swarm/engine) | Rust 游戏引擎 | ✅ 144 tests |
| [swarm/sandbox](https://git.kagurazakalan.com/swarm/sandbox) | WASM 沙箱运行时 | ✅ 9 tests |
| [swarm/sdk-ts](https://git.kagurazakalan.com/swarm/sdk-ts) | TypeScript SDK | ✅ 11 tests |
| [swarm/sdk-rust](https://git.kagurazakalan.com/swarm/sdk-rust) | Rust SDK | ✅ 8 tests |
| [swarm/gateway](https://git.kagurazakalan.com/swarm/gateway) | Go API 网关 | ✅ 7 tests |
| [swarm/frontend](https://git.kagurazakalan.com/swarm/frontend) | Web 客户端 | ✅ 8 tests |

## 目录结构

```
docs/
├── ROADMAP.md                   # 模块化实施追踪
├── RUNBOOK.md                   # 运维手册（密钥轮换/备份恢复）
├── design/
│   ├── DESIGN.md                # 架构全景 + 游戏设计
│   └── tech-choices.md          # 技术选型（11 组件备选分析）
├── specs/p0/                    # P0 冻结规范 (9 份)
├── security/
│   └── CVE-SLA.md               # Wasmtime CVE 响应 SLA
└── reviews/                     # 评审档案 (R1-R14)
```

## 评审流程

9 位评审者（3 模型 × 3 方向）× 14 轮迭代 → Speaker 合成共识。Phase 0 经 R14 终审确认冻结。

详见 [reviews/README.md](reviews/README.md)。

## 许可证

MIT
