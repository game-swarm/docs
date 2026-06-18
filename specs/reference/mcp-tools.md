# MCP 工具参考

> **权威工具清单见 [API Registry](api-registry.md) §3** — 46 工具。本文档提供逐工具详细说明。
>
> MCP 是 AI agent 的操作界面——与人类玩家的 Web UI 完全同级。
> MCP **不做游戏动作**。AI agent 必须编写 WASM 代码来操作世界。
> 详见 `specs/security/03-mcp-security.md`。

## 工具分类

### 世界查看

| 工具 | 说明 |
|------|------|
| `swarm_get_snapshot` | 获取当前 tick 的可见世界状态快照 |
| `swarm_get_terrain` | 查询指定区域的地形 |
| `swarm_get_objects_in_range` | 查询范围内的实体列表 |
| `swarm_get_world_rules` | 获取世界规则配置 |

### Economy

> 权威定义见 [API Registry](api-registry.md) §3.1。

| 工具 | 说明 |
|------|------|
| `swarm_get_economy` | 获取玩家经济概况（收入、支出、存储税、维护费） |
| `swarm_get_drone_efficiency` | 获取 drone 效率及影响因素 |
| `swarm_get_economy_trend` | 获取指定 tick 范围的经济趋势数据 |

### 部署

| 工具 | 说明 |
|------|------|
| `swarm_deploy` | 上传并部署 WASM 模块（需 Ed25519 签名） |
| `swarm_validate_module` | 部署前预检 WASM 合法性 |
| `swarm_rollback` | 回滚到之前的 WASM 版本 |
| `swarm_list_modules` | 列出所有已部署的 WASM 模块及状态 |

### 调试

| 工具 | 说明 |
|------|------|
| `swarm_explain_last_tick` | 解释上 tick 执行结果（accepted/rejected commands） |
| `swarm_inspect_entity` | 查看实体完整状态 |
| `swarm_inspect_room` | 查看有视野的房间概况 |
| `swarm_profile` | 查看策略性能指标 |
| `swarm_dry_run_commands` | 干跑 Command JSON（不执行，仅校验） |
| `swarm_get_replay` | 获取 tick 范围回放数据 |

### 学习

| 工具 | 说明 |
|------|------|
| `swarm_get_docs` | 获取 API 文档和游戏规则 |
| `swarm_get_schema` | 获取 Command JSON Schema |
| `swarm_get_available_actions` | 获取当前可用的 CommandAction 列表 |
| `swarm_simulate` | 离线模拟：给定世界快照，预测未来 N tick |

### SDK

| 工具 | 说明 |
|------|------|
| `swarm_sdk_fetch` | 获取 SDK 代码、类型定义、示例及 ABI 版本信息 |

### 认证

| 工具 | 说明 |
|------|------|
| `swarm_get_server_trust` | 获取 server_id、Swarm CA fingerprint、Intermediate chain |
| `swarm_register_challenge` | 获取注册/CSR PoW 挑战 |
| `swarm_submit_csr` | 提交 CSR 并签发应用层证书 |
| `swarm_renew_certificate` | 续签应用层证书 |
| `swarm_list_certificates` | 列出当前账号证书 |
| `swarm_revoke_certificate` | 吊销证书 |
| `swarm_token_refresh` | 刷新 Web session 兼容 token |
| `swarm_auth_revoke` | 吊销 session、certificate 或 public key |
| `swarm_update_profile` | 修改显示名称 |
| `swarm_change_password` | 修改 recovery password |
| `swarm_request_password_reset` | 请求恢复链接 |
| `swarm_admin_create_password_reset` | 管理员生成恢复链接 |
| `swarm_confirm_password_reset` | 确认恢复并签发新证书 |
| `swarm_register_passkey` | 绑定 passkey 恢复因子 |
| `swarm_recover_with_passkey` | 使用 passkey 恢复并签发新证书 |
| `swarm_bind_email` | 绑定邮箱 |
| `swarm_delete_account` | 删除账号 |
| `swarm_restore_account` | 恢复已删除账号 |
| `swarm_cancel_account_deletion` | 取消账号删除 |
| `swarm_federated_login` | 外部证书作为 bootstrap proof，本地重签证书 |

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
Client generates private key locally
  → submits CSR + PoW challenge proof
    → Server Intermediate CA signs application-layer certificates
      → MCP/HTTP/WebSocket requests carry Swarm-Certificate-Chain + request signature
        → Gateway/Engine verifies chain, usage, scope, nonce, signature
```

Swarm CA 只用于应用层证书，不安装到系统/浏览器 trust store。HTTP 等不安全传输可以完成身份认证与完整性校验；首次访问需人工确认并 pin 服务器 Root CA fingerprint，之后服务器身份由客户端证书存储中的 Root CA pin 验证，不依赖外部 TLS。

## Rate Limiter

> **权威 per-tool rate limit 见 [API Registry](api-registry.md) §3.3**。以下为 source-level 限流（参考），以 registry 为准。

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
