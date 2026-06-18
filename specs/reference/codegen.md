# Codegen Pipeline — IDL → API Registry / SDK / Docs

> **R22 B4 修复**。定义 IDL YAML → 生成产物的输入输出链，禁止手写分叉。

## 原则

1. **IDL 是唯一机器源**：`game_api.idl.yaml`, `auth_api.idl.yaml`, `economy.idl.yaml`。
2. **API Registry 全量生成**：`api-registry.md` 的表格/列表/计数由 codegen 产出，禁止手写。
3. **CI diff check**：CI 比较生成产物与 repo 内容，发现漂移 → 阻塞合并。

## 输入 → 输出映射

| 输入 (IDL) | 生成产物 | 不可手写区域 |
|------------|---------|-------------|
| `game_api.idl.yaml` | `api-registry.md` §1-5, §11 | CommandAction 表、RejectionReason 表、MCP Tools 表、Host Functions 表、容量限制表、常量表 |
| `auth_api.idl.yaml` | `api-registry.md` §6-9 | Auth 工具表、Auth Error Codes 表、Token Envelope |
| `economy.idl.yaml` | `api-registry.md` §10 | Economy Operations 表、Canonical Formulas 表 |
| 所有 IDL | SDK 类型定义 (`sdk-templates/`) | 类型定义、ABI 版本 |

## 禁止手写的数值

以下数值**只存在于 IDL 中**，API Registry 由 codegen 生成。任何手写副本为错误：

- CommandAction 数量 (当前 19)
- MCP tool 数量 (当前 56 active)
- RejectionReason 数量 (当前 79)
- Host function 数量 (当前 5)
- `MAX_DRONES_PER_PLAYER` (50)
- Body part costs
- Storage tax tiers
- Refund rates
- Rate limits

## CI Gate

```bash
# CI 检查: 生成产物是否与 IDL 一致
hermes codegen generate --source specs/reference/*.idl.yaml --output specs/reference/api-registry.md --check
# 退出码非零 = 漂移 → 阻塞
```

## Codegen 命令

```bash
# 生成全部产物
hermes codegen generate --source specs/reference/*.idl.yaml --output-dir specs/reference/

# 仅检查（不写入）
hermes codegen generate --source specs/reference/*.idl.yaml --check
```

## 版本同步

IDL 版本变更时自动更新 API Registry 头部 `api_version` 行和 changelog 表。
