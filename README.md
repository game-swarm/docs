# Swarm — 设计文档

可编程 MMO RTS 游戏引擎的设计文档仓库。

进度追踪 → [ROADMAP.md](ROADMAP.md)

## 目录结构

```
docs/
├── ROADMAP.md                   # 模块化实施追踪
├── GETTING-STARTED.md           # 5 分钟入门指南
├── RUNBOOK.md                   # 运维手册
├── api/                         # API 参考
│   ├── commands.md              #   23 种 CommandAction
│   ├── host-functions.md        #   WASM host functions
│   └── mcp-tools.md             #   MCP 工具完整列表
├── design/
│   ├── DESIGN.md                # 架构全景 + 游戏设计
│   └── tech-choices.md          # 技术选型
├── specs/                       # 当前规范（git 管理历史版本）
├── security/CVE-SLA.md          # Wasmtime CVE 响应 SLA
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

## 评审流程

9 位评审者（3 模型 × 3 方向）× 14 轮迭代。Phase 0 经 R14 终审冻结。评审档案已归档到 `git tag review-archive`。

## 许可证

MIT
