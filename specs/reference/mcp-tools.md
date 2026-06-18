# MCP 工具参考

> 权威源: [game_api.idl.yaml](game_api.idl.yaml) → [api-registry.md](api-registry.md) (生成)

> **权威工具清单见 [API Registry](api-registry.md) §3** — 56 工具。本文档提供使用模式和安全约束说明。
>
> MCP 是 AI agent 的操作界面——与人类玩家的 Web UI 完全同级。
> MCP **不做游戏动作**。AI agent 必须编写 WASM 代码来操作世界。
> 详见 `specs/security/03-mcp-security.md`。

## 使用模式

### 部署

> 权威定义见 [API Registry](api-registry.md) §3.2 Deploy (6 工具)。

部署 WASM 模块的标准流程：
1. `swarm_validate_module` — 上传前预检 WASM 合法性
2. `swarm_deploy` — 上传并部署（需 Ed25519 签名，使用 deploy_mutation 模式）
3. `swarm_get_deploy_status` — 查询部署状态
4. `swarm_list_deployments` — 列出已部署模块

### 世界查看

> 权威定义见 [API Registry](api-registry.md) §3.2 Onboarding (8) + Play (14)。

核心快照与实体查询按 `fog_of_war` / `owner` / `owner_or_visible` 可见性过滤。`swarm_get_snapshot` 每 tick 一次，返回与 WASM `tick()` 输入完全相同的结构化数据。

### 调试

> 权威定义见 [API Registry](api-registry.md) §3.2 Debug (7 工具)。

调试工具需要 `swarm:debug` scope，限制 30/tick。包括 `swarm_get_tick_trace`、`swarm_simulate`、`swarm_dry_run` 等。

### 认证

> 权威定义见 [auth_api.idl.yaml](auth_api.idl.yaml) → [API Registry](api-registry.md) §3.2 Auth (2 工具)。

### 锦标赛 / SDK / Resources

> 权威定义见 [API Registry](api-registry.md) §3.2。

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

> **权威 per-tool rate limit 见 [API Registry](api-registry.md) §3.1**。以下为 source-level 限流（参考），以 registry 为准。

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
