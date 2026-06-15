# Swarm Docs 约定

## 文档层次

```
DESIGN.md      活文档 — 持续更新，单一设计真相源
specs/latest/  当前规范版本（符号链接）
specs/v0.N/    归档版本 — 冻结后不可修改
ROADMAP.md     实施追踪 — DESIGN vs code 差距
```

## 版本化规则

- `specs/` 下的版本目录（`v0.1`, `v0.2`, ...）是**归档**——冻结后不可修改
- `specs/latest` 是指向最新版本的符号链接
- 所有文档引用规范时使用 `specs/latest/`，不写死版本号
- 冻结新版本时：`ln -sfn v0.3 specs/latest`
- DESIGN.md 是活文档，不受版本冻结影响

## 工作流

```
DESIGN.md 更新 → spec 对齐 → 版本冻结 → 实现对齐 spec
```

1. 设计变更先在 DESIGN.md 中完成
2. 设计稳定后同步到 `specs/latest/`（下一步冻结时升版）
3. 冻结时：cp -r specs/latest specs/v0.N && ln -sfn v0.N specs/latest
4. 代码实现对齐 spec

## README 职责

- `docs/README.md` — 目录导航，指向 DESIGN + ROADMAP
- Root `README.md` — 仓库入口，指向 docs/
- `reviews/README.md` — 评审历史索引
- `api/` — 开发者参考文档（与 spec 互补，非替代）

## AGENTS.md

此文件。AI agent 处理本仓库时应遵循以上约定。
