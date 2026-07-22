# MCP 工具参考

> 同步权威源: [game_api.idl.yaml](game_api.idl.yaml) ↔ [api-registry.md](api-registry.md)

> **权威工具清单见 [API Registry](api-registry.md) §3**。工具名称、数量和分组与 IDL YAML 同步维护；不要在本页维护独立计数。本文档提供使用模式和安全约束说明。
>
> MCP 是 AI agent 的游戏操作界面——与人类玩家的 Web UI 完全同级。Auth 与 SDK 获取不属于 MCP 工具面：Auth 使用 `auth_api` REST endpoints，SDK 使用 signed REST `GET /sdk/:lang`。
> MCP **不做游戏动作**。AI agent 必须编写 WASM 代码来操作世界。
> 详见 `specs/security/mcp-security.md`。

## 使用模式

MCP 工具作为 AI Agent 的感知和控制平面入口。标准的 Agent 决策循环如下：

1. **环境感知**: 调用 `swarm_get_info` 获取 API version、tick rate、world name 与 player count；调用 `swarm_get_snapshot` 获取当前 tick 和实体的结构化快照。
2. **逻辑决策**: Agent 在本地运行推理或启发式算法，决定本 Tick 的行动。
3. **世界操作**: MCP 工具不直接提供 `move` 或 `harvest` 等原子游戏动作（详见 [MCP 安全模型](../security/mcp-security.md)）。Agent 必须通过 `swarm_deploy` 提交编译好的 WASM 模块。
4. **验证与调试**: 使用 `swarm_dry_run` 或 `swarm_simulate` 在不消耗资源的情况下验证逻辑。

### 请求/响应边界

客户端通过 Gateway 的 request/response `POST /mcp` 调用工具；该接口不提供 SSE subscription。JSON-RPC envelope 由 MCP 客户端与 Gateway 处理，本页不维护独立 wire 示例。Rate limit 的设计权威是 `design/interface.md` §4.1b；每个工具的参数、结果字段、scope、replay class、visibility filter 及设计派生的 wire rate-limit 值见 [API Registry §3.2](api-registry.md)。

有关错误处理的详细信息，请参阅本页的 [错误 Envelope](#错误-envelope) 以及 [API Registry](api-registry.md) §8。

---

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

## 工具总览（同步自 API Registry 0.4.0）

| 分组 | Game API 工具数 | 说明 |
|------|-----------------|------|
| Onboarding | 10 | 信息、快照、房间、drone、文档与 schema 查询 |
| Play | 16 | 世界读取、公开聚合统计、回放、可见性、controller/structure/economy 查询 |
| Deploy | 7 | 部署、校验、状态、模块、世界配置与规则读取 |
| Debug | 8 | TickTrace、模拟、dry-run、sandbox/profile、最后 tick 解释 |
| Arena | `all_declared=4`, `active_only=4`, `gated=0` | Tournament create/precommit/status and match-result tools are active |
| Resources | 2 | `resources/list` / `resources/read` |
| **Game MCP 小计** | **`all_declared=47`, `active_only=47`, `gated=0`** | `game_api.idl.yaml` 三口径工具统计；不含 Auth/SDK |

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

> 下游定义见 [API Registry](api-registry.md) §3.2 Onboarding (10) + Play (16)。

核心快照与实体查询按 `fog_of_war` / `owner` / `owner_or_visible` 可见性过滤。`swarm_get_snapshot` 每 tick 一次，返回与 WASM `tick()` 输入完全相同的结构化数据。

0.4.0 新增的查询入口包括 `swarm_get_docs`、`swarm_get_schema`、`swarm_profile`、`swarm_get_available_actions`。

### 调试

> 权威定义见 [API Registry](api-registry.md) §3.2 Debug (8 工具)。

调试工具需要 `swarm:debug` scope。`design/interface.md` §4.1b 定义 named profiles 与显式 per-tool assignments；`swarm_simulate` 与 `swarm_dry_run` 均为 50/tick，IDL 和 Registry 必须逐项下沉相同值。

### SDK 获取

SDK canonical route 是 signed REST `GET /sdk/:lang`。`:lang` 是 SDK language identifier，例如 `typescript` 或 `rust`。输出语义为 `sdk_code`、`type_definitions`、`examples`、`abi_version`、`min_engine_version`；不支持的 language 返回 `SchemaViolation` 语义错误，频率超限返回 `RateLimited`。

### 锦标赛 / Resources

> 下游工具表见 [API Registry](api-registry.md) §3.2 Arena (`all_declared=4`, `active_only=4`, `gated=0`) 与 Resources (2)。

四个 Arena 工具均由 Engine 运行时分派。Engine 的 tournament-mode profile 还会按比赛准备流程提供一组经过筛选的查询、校验和部署工具；该 profile 不是 Arena category 的工具计数。Resources 工具提供资源定义读取。

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

> **Rate-limit 设计权威见 `design/interface.md` §4.1b**；IDL 与 [API Registry](api-registry.md) §3.1-3.2 仅下沉 named profiles 和 per-tool wire 值。以下 source-level tokens/s 表只描述 legacy/reference-only 内部预算，不覆盖公开 MCP rate limit。

| Source | 预算 (tokens/s) |
|--------|-----------------|
| WASM | 1000 |
| MCP_Deploy | 10 |
| MCP_Query | 100 |
| Replay | 50 |
| TestHarness | 200 |
| Tutorial | 50 |
| Deploy | 10 |
| Simulate | 100 |
| DryRun | 50 |

## 明确不在 MCP 中

- ❌ `swarm_move` / `swarm_attack` / `swarm_build` / `swarm_spawn`
- ❌ 任何直接修改世界状态的工具

AI agent 必须**编写 WASM 代码**来实现游戏策略，和人类玩家走完全相同的路径。
