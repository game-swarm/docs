# Swarm — 设计文档

可编程 MMO RTS 游戏引擎的设计文档仓库。**全部 7 阶段已完成**（2026-06-14）。

## 目录结构

```
docs/
├── ROADMAP.md                   # 实施计划 + 代码对齐审计 (7 阶段交付物 + 验收标准)
├── design/
│   ├── DESIGN.md                # 架构全景 + 游戏设计 (1,486 行)
│   └── tech-choices.md          # 技术选型（11 组件备选分析 + 决策理由）
├── specs/
│   └── p0/                       # P0 冻结规范 (9 份)
│       ├── 01-tick-protocol-spec.md        # Tick 生命周期 + 失败语义 + 回放
│       ├── 02-command-validation-spec.md   # 校验矩阵 + Refund 模型 + Schema
│       ├── 03-mcp-security-contract.md    # MCP 接口 + 认证流程
│       ├── 04-wasm-sandbox-baseline.md     # WASM 沙箱 + Deferred Model
│       ├── 05-unified-visibility-policy.md # 统一可见性策略
│       ├── 06-mvp-feedback-loop.md         # 学习闭环 + 调试工具
│       ├── 07-world-rules-engine.md        # Rhai 模组 + ECS Plugin
│       ├── 08-game-api-idl.md              # 单一 IDL + 代码生成
│       └── 09-command-source-model.md      # 12 来源 + 证书签名 Auth
└── reviews/                      # 评审档案 (R1-R14)
    ├── README.md                 # 轮次索引
    ├── R1/ — R14/                # 14 轮评审
    └── R14/R14-CONFIRMATION.md   # 终审：14/14 通过，Phase 0 冻结
```

## 技术选型

| 组件 | 选型 |
|------|------|
| 引擎 | Rust + Bevy ECS |
| 沙箱 | WASM + Wasmtime (per-tick fork) |
| 模组 | Rhai (AST 解释, 三层信任) |
| 持久化 | FoundationDB (严格可序列化) |
| 推送 | NATS |
| 缓存 | Dragonfly |
| 指标 | ClickHouse |
| 哈希/PRNG/签名 | Blake3 (单一原语) |
| 证书 | Ed25519 (OAuth2 → 短期证书) |
| SDK | TypeScript + Rust |
| UI | Monaco + PixiJS |

## 代码仓库

| 仓库 | 说明 | 状态 |
|------|------|------|
| [swarm/engine](https://git.kagurazakalan.com/swarm/engine) | Rust 游戏引擎 | ✅ 115 tests |
| [swarm/sandbox](https://git.kagurazakalan.com/swarm/sandbox) | WASM 沙箱运行时 | ✅ 9 tests |
| [swarm/sdk-ts](https://git.kagurazakalan.com/swarm/sdk-ts) | TypeScript SDK | ✅ 11 tests |
| [swarm/sdk-rust](https://git.kagurazakalan.com/swarm/sdk-rust) | Rust SDK | — |
| [swarm/gateway](https://git.kagurazakalan.com/swarm/gateway) | Go API 网关 | — |
| [swarm/frontend](https://git.kagurazakalan.com/swarm/frontend) | Web 客户端 | ✅ 3 tests |

## 评审流程

9 位评审者（3 模型 × 3 方向）× 14 轮迭代 → Speaker 合成共识。Phase 0 经 R14 终审确认冻结。

详见 [reviews/README.md](reviews/README.md)。

## 许可证

MIT
