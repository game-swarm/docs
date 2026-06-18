# Swarm Docs 约定

## 核心原则：目标状态，非现状追踪


| 禁止 | 原因 |
|------|------|
| 日期标记 (`2026-06-14`) | 文档不是日志，git 已记录时间 |
| 状态行 (`> **状态**: 当前`) | 无"当前/过去"之分，只描述目标 |
| 实现注释 (`锚定 design/README.md §X`) | 文档自足，不需要"锚定"声明 |
| 变更标记 (`新增`/`删除`/`v0.2`) | git diff 负责历史，文档不回溯 |
| Phase/版本号 (`P0-N`/`Phase 0`) | 无阶段概念，无版本标记 |
| 最后更新日期 | git blame 负责归属 |
| 版本分期设计 (`v1 先 X，v1.1 再 Y`) | 设计按最佳实践一次性完整描述，不做"当前凑合、以后升级"的分期妥协 |


design/README.md、specs/、specs/reference/ 中的所有文档，读起来应该像一件成品的规格说明书。

**引用方向（单向向上）：**

```
design/*.md  ←──  specs/  ←──  specs/reference/
 (被引用)         (引用设计)    (引用规范)
```

- `design/README.md` 是总导航——自足，不引用 specs
- 每个 spec 头部声明 `> 详见 design/<domain>.md`
- specs/reference/ 文档引用对应 spec

```
design/README.md    设计导航 — 愿景 + 架构全景 + 域文件索引
design/engine.md    引擎架构 — Tick 生命周期, ECS, 快照, 确定性
design/gameplay.md  游戏机制 — Vanilla, 身体部件, 伤害, 特殊攻击
design/modes.md     游戏模式 — World vs Arena, PvE
design/interface.md MCP 与 API — 工具, 命令模型, SDK
specs/core/        核心引擎规范 (tick, 命令, WASM, 规则)
specs/security/    安全规范 (MCP, 可见性, 来源)
specs/gameplay/    游戏规范 (反馈循环, IDL)
specs/future/      扩展路线 (T2 增量快照, T3 分片)
specs/reference/               API 参考 — 开发者面向的接口文档
```

## 规范管理

- `specs/` 按域分子目录：`core/` `security/` `gameplay/` `future/`
- `specs/12-gateway-protocol.md` 为跨域 Gateway 协议（汇聚 specs/core/01 §4 + specs/security/03 §2 等）
- **历史版本由 git 管理**——`git log specs/` 可追溯所有变更
- 需要 checkpoint 时用 `git tag v0.N` 标记，不需要复制目录
- `design/README.md` 是导航入口；域细节在各 `design/<domain>.md`
- 所有文档引用规范时使用 `specs/<dir>/<NN>-<name>.md` 格式

## 工作流

```
design/*.md 更新 → spec 对齐 → 代码实现对齐 spec
```

1. 设计变更先在 design/README.md 中完成
2. 设计稳定后同步到 `specs/`
3. 代码实现对齐 spec

## 评审流程


| 仓库状态由 `reviews/` 目录是否存在来判断：

| 状态 | 标志 | 含义 |
|------|------|------|
| 🟢 稳定 | 无 `reviews/` 目录 | 文档已冻结，可直接修改或发起新一轮评审 |
| 🔴 评审中 | 存在 `reviews/RN/` | 文档正在根据评审意见修改中，**不要直接修改文档**——先阅读评审报告了解上下文 |

**评审循环**：

```
R{N}:   创建干净文档副本 → 分发 9 评审员 → Speaker 裁决 → 提交评审报告
           ↓
        根据 Blocker 修改文档 → 验证一致性 → 用户确认
           ↓
        提交文档修改 → 清理 reviews/ 目录
           ↓
R{N+1}: (重复，文档已回到稳定状态)
```

**关键规则**：
1. 评审完成后**立即提交评审报告**（`git add reviews/ && git commit`），再开始修改文档
2. 只有当所有 Blocker 修复完毕、用户确认后，才**清理 `reviews/` 目录**（`git rm -r reviews/`）
3. `reviews/` 目录存在 = 文档正在修改中，任何 agent 应先读评审报告再操作
4. 评审报告是审计轨迹，通过 git history 可回溯完整评审历史

## README 职责

- Root `README.md` — 仓库入口，指向 docs/
- `specs/reference/` — 开发者参考文档（与 spec 互补，非替代）

## AGENTS.md

此文件。AI agent 处理本仓库时应遵循以上约定。
