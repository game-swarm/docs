# Swarm Docs 约定

## 文档层次

```
DESIGN.md      活文档 — 持续更新，单一设计真相源
specs/         当前规范 — git 管理版本历史，无需手动归档
ROADMAP.md     实施追踪 — DESIGN vs code 差距
```

## 规范管理

- `specs/` 目录存放当前规范文件，无版本子目录
- **历史版本由 git 管理**——`git log specs/` 可追溯所有变更
- 需要 checkpoint 时用 `git tag v0.N` 标记，不需要复制目录
- DESIGN.md 是活文档，直接修改提交
- 所有文档引用规范时使用 `specs/<文件名>`

## 工作流

```
DESIGN.md 更新 → spec 对齐 → 代码实现对齐 spec
```

1. 设计变更先在 DESIGN.md 中完成
2. 设计稳定后同步到 `specs/`
3. 代码实现对齐 spec

## README 职责

- `docs/README.md` — 目录导航，指向 DESIGN + ROADMAP
- Root `README.md` — 仓库入口，指向 docs/
- `reviews/README.md` — 评审历史索引
- `api/` — 开发者参考文档（与 spec 互补，非替代）

## AGENTS.md

此文件。AI agent 处理本仓库时应遵循以上约定。
