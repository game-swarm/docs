# Swarm — 设计文档

可编程 MMO RTS 游戏引擎的设计文档仓库。

## 目录结构

```
docs/
├── design/            # 架构设计
│   ├── DESIGN.md      #   主设计文档
│   └── PLANNER-OUTPUT.md  # Planner 扩展计划（评审前草案）
├── specs/             # 技术规范
│   └── p0/            #   Phase 2 阻断项（6 个 P0 工件）
│       ├── 01-tick-protocol-spec.md      # Tick 协议规范
│       ├── 02-command-validation-spec.md # 指令校验规范
│       ├── 03-mcp-security-contract.md   # MCP 安全契约
│       ├── 04-wasm-sandbox-baseline.md   # WASM 沙箱基线
│       ├── 05-unified-visibility-policy.md # 统一可见性策略
│       └── 06-mvp-feedback-loop.md       # MVP 反馈循环规范
└── reviews/           # 评审报告
    ├── CONSENSUS-REPORT.md  # 评审议会共识报告
    └── review-rev-*.md      # 6 份评审员报告
```

## 代码仓库

| 仓库 | 说明 |
|------|------|
| [swarm/engine](https://git.kagurazakalan.com/swarm/engine) | Rust 游戏引擎 |
| [swarm/sandbox](https://git.kagurazakalan.com/swarm/sandbox) | WASM 沙箱运行时 |
| [swarm/gateway](https://git.kagurazakalan.com/swarm/gateway) | Go API 网关 |
| [swarm/frontend](https://git.kagurazakalan.com/swarm/frontend) | Web 客户端 |
| [swarm/sdk-ts](https://git.kagurazakalan.com/swarm/sdk-ts) | TypeScript SDK |
| [swarm/sdk-rust](https://git.kagurazakalan.com/swarm/sdk-rust) | Rust SDK |

## 评审流程

设计评审使用**评审议会机制**（design-parliament skill）：

1. **6 位评审员**（3 模型 × 2 方向）并行独立评审
2. 方向内交叉评审
3. 议会辩论处理分歧
4. **议长（rev-speaker）** 合成共识报告

评审员 Profile 列表见 Hermes 配置。

## 许可证

MIT
