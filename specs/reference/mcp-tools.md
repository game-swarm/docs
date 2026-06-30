# MCP 工具参考

> 权威源: [game_api.idl.yaml](game_api.idl.yaml) → [api-registry.md](api-registry.md) (生成)

> **权威工具清单见 [API Registry](api-registry.md) §3** — 工具数量与分组以 Registry 三口径为准（Game API `all_declared=57` / `active_only=53` / `rfc_gated=4`；Auth API `all_declared=7` / `active_only=7` / `rfc_gated=0`）。本文档提供使用模式和安全约束说明。
>
> MCP 是 AI agent 的操作界面——与人类玩家的 Web UI 完全同级。
> MCP **不做游戏动作**。AI agent 必须编写 WASM 代码来操作世界。
> 详见 `specs/security/mcp-security.md`。

## 使用模式

## 错误 Envelope

MCP 工具调用失败统一返回标准 JSON-RPC 2.0 error object，权威定义见 [API Registry](api-registry.md) §8 SwarmError JSON-RPC Envelope。

| 字段 | 说明 |
|------|------|
| `error.code` | numeric JSON-RPC error code；Swarm application error 固定使用 `-32000`，不得填 RejectionReason 字符串 |
| `error.message` | 人类可读摘要 |
| `error.data.rejection_reason` | canonical RejectionReason wire enum string（见 Registry §2）；SDK 据此生成 typed exception |
| `error.data.debug_detail` | 非 canonical 上下文详情（≤ 512 bytes）；详细程度由 `detail_level` 控制 |
| `error.data.retry_allowed` | 是否可安全重试（machine-readable，可选） |
| `error.data.idempotency_key` | 幂等重试 key（machine-readable，可选） |
| `error.data.retry_after_tick` | 建议最早重试 tick（machine-readable，可选） |

所有业务拒绝原因必须放在 `error.data.rejection_reason`，`error.code` 只保留 JSON-RPC numeric 分类。

## 工具总览（同步自 API Registry 0.5.0）

| 分组 | Game API 工具数 | 说明 |
|------|-----------------|------|
| Onboarding | 11 | 信息、快照、房间、drone、文档与 schema 查询 |
| Auth | 3 | `swarm_register_challenge` / `swarm_submit_csr` / `swarm_cert_check` (证书链模型) |
| Play | 15 | 世界读取、回放、可见性、controller/structure/economy 查询 |
| Deploy | 7 | 部署、校验、状态、模块、世界配置与规则读取 |
| Debug | 8 | TickTrace、模拟、dry-run、sandbox/profile、最后 tick 解释 |
| Admin | 6 | 管理挑战、配置、回滚、封禁、GC、审计日志 |
| SDK | 1 | `swarm_sdk_fetch` |
| Arena | `all_declared=4`, `active_only=1`, `rfc_gated=3` | `swarm_match_result` active；锦标赛编排为 extension-gated |
| Resources | 2 | `resources/list` / `resources/read` |
| **Game API 小计** | **`all_declared=57`, `active_only=53`, `rfc_gated=4`** | `game_api.idl.yaml` 三口径工具统计 |
| **Auth API** | **`all_declared=7`, `active_only=7`, `rfc_gated=0`** | `auth_api.idl.yaml` CSR lifecycle 工具 |

### 部署

> 权威定义见 [API Registry](api-registry.md) §3.2 Deploy (7 工具)。

部署 WASM 模块的标准流程：
1. `swarm_validate_module` — 上传前预检 WASM 合法性
2. `swarm_deploy` — 上传并部署（需 Ed25519 签名，使用 deploy_mutation 模式）
3. `swarm_get_deploy_status` — 查询部署状态
4. `swarm_list_deployments` — 列出已部署模块
5. `swarm_list_modules` — 列出玩家模块清单
6. `swarm_get_world_config` — 读取世界配置
7. `swarm_get_world_rules` — 读取规则模块参数

### 世界查看

> 权威定义见 [API Registry](api-registry.md) §3.2 Onboarding (11) + Play (15)。

核心快照与实体查询按 `fog_of_war` / `owner` / `owner_or_visible` 可见性过滤。`swarm_get_snapshot` 每 tick 一次，返回与 WASM `tick()` 输入完全相同的结构化数据。

0.4.0 新增的查询入口包括 `swarm_get_docs`、`swarm_get_schema`、`swarm_profile`、`swarm_get_available_actions`。

### 调试

> 权威定义见 [API Registry](api-registry.md) §3.2 Debug (8 工具)。

调试工具需要 `swarm:debug` scope，限制 30/tick。包括 `swarm_get_tick_trace`、`swarm_simulate`、`swarm_dry_run`、`swarm_explain_last_tick` 等。

### 认证

> 权威定义见 [API Registry](api-registry.md) §3.2 Auth (3 个 Game API 简化工具) 与 §3.3 Auth API 工具 (12 个完整 auth 工具)。

### 锦标赛 / SDK / Resources

> 权威定义见 [API Registry](api-registry.md) §3.2 Arena (`all_declared=4`, `active_only=1`, `rfc_gated=3`)、SDK (1)、Resources (2)。

Arena 当前 active 工具为 `swarm_match_result`；`swarm_tournament_create`、`swarm_tournament_precommit`、`swarm_tournament_status` 为 extension。SDK/Resources 工具分别提供 SDK 拉取与资源定义读取。

## 认证模型

```
Client generates private key locally
  → submits CSR + PoW challenge proof
    → Server CA signs application-layer certificates
      → MCP/HTTP/WebSocket requests carry Swarm-Certificate + request signature
        → Gateway/Engine verifies chain, usage, scope, nonce, signature
```

Swarm CA 只用于应用层证书，不安装到系统/浏览器 trust store。HTTP 等不安全传输可以完成身份认证与完整性校验；首次访问需人工确认并 pin 服务器 CA fingerprint，之后服务器身份由客户端证书存储中的 Server CA pin 验证，不依赖外部 TLS。

## Rate Limiter（Legacy / Reference Only）

> **权威 per-tool rate limit 见 [API Registry](api-registry.md) §3.1**。以下 source-level tokens/s 表仅作 legacy/reference-only 背景说明；实际限流以 registry per-tool rate limit 为准。

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
| Simulate | 100 |
| DryRun | 50 |

## 明确不在 MCP 中

- ❌ `swarm_move` / `swarm_attack` / `swarm_build` / `swarm_spawn`
- ❌ 任何直接修改世界状态的工具

AI agent 必须**编写 WASM 代码**来实现游戏策略，和人类玩家走完全相同的路径。
