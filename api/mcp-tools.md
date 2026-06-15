# MCP 工具参考

> Phase 0 冻结。MCP 是 AI agent 的操作界面——与人类玩家的 Web UI 完全同级。
> MCP **不做游戏动作**。AI agent 必须编写 WASM 代码来操作世界。
> 详见 `specs/p0/03-mcp-security-contract.md`。

## 工具分类

### 世界查看

| 工具 | 说明 |
|------|------|
| `swarm_get_snapshot` | 获取当前 tick 的可见世界状态快照 |
| `swarm_get_terrain` | 查询指定区域的地形 |
| `swarm_get_objects_in_range` | 查询范围内的实体列表 |
| `swarm_get_world_rules` | 获取世界规则配置 |

### 部署

| 工具 | 说明 |
|------|------|
| `swarm_deploy` | 上传并部署 WASM 模块（需 Ed25519 签名） |
| `swarm_validate_module` | 部署前预检 WASM 合法性 |
| `swarm_rollback` | 回滚到之前的 WASM 版本 |

### 调试

| 工具 | 说明 |
|------|------|
| `swarm_explain_last_tick` | 解释上 tick 执行结果（accepted/rejected commands） |
| `swarm_inspect_entity` | 查看实体完整状态 |
| `swarm_profile` | 查看策略性能指标 |
| `swarm_dry_run_commands` | 干跑 Command JSON（不执行，仅校验） |

### 学习

| 工具 | 说明 |
|------|------|
| `swarm_get_docs` | 获取 API 文档和游戏规则 |
| `swarm_get_schema` | 获取 Command JSON Schema |
| `swarm_get_available_actions` | 获取当前可用的 CommandAction 列表 |

### 认证

| 工具 | 说明 |
|------|------|
| `swarm_oauth2_login` | 发起 OAuth2 登录 |
| `swarm_oauth2_callback` | OAuth2 回调处理 |
| `swarm_token_refresh` | 刷新 access token |
| `swarm_auth_revoke` | 吊销证书 |

### 锦标赛

| 工具 | 说明 |
|------|------|
| `swarm_tournament_precommit` | 锁定 WASM 模块（赛前） |
| `swarm_tournament_create` | 创建锦标赛 bracket |
| `swarm_tournament_status` | 查询锦标赛状态 |
| `swarm_match_result` | 查询比赛结果 |

### 资源管理（MCP 保留，非游戏操作）

| 工具 | 说明 |
|------|------|
| `resources/list` | 列出可用资源类型 |
| `resources/read` | 读取资源定义 |

## 认证模型

```
OAuth2 Provider (GitHub/Google)
  → 授权码 → Gateway → 交换 token
    → Engine MCP 签发 Ed25519 证书（24h TTL）
      → 所有 MCP 调用携带证书
        → rate limiter 检查（12 种来源分级）
```

## Rate Limiter（12 来源分级）

| Source | 预算 (tokens/s) |
|--------|-----------------|
| WASM | 1000 |
| MCP_Deploy | 10 |
| MCP_Query | 100 |
| Admin | 无限制 |
| Replay | 50 |
| TestHarness | 200 |
| Tutorial | 50 |
| Deploy | 10 |
| Rollback | 5 |
| RuleMod | 20 |
| Simulate | 100 |
| DryRun | 50 |

## 明确不在 MCP 中

- ❌ `swarm_move` / `swarm_attack` / `swarm_build` / `swarm_spawn`
- ❌ 任何直接修改世界状态的工具

AI agent 必须**编写 WASM 代码**来实现游戏策略，和人类玩家走完全相同的路径。
