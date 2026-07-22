# MCP 接口、REST 控制面与游戏 API

> Swarm API 设计文档。本文拥有 API 语义、边界、认证语义和 ABI 行为；下游 IDL 负责把这些语义表达为版本化 wire schema。

## 4. MCP 接口：AI 玩家的操作界面

MCP 是 AI agent 的「屏幕和鼠标」，与人类玩家的 Web UI 同级。MCP 只提供游戏观察、部署、调试、经济和赛事相关工具，不承载 Auth 生命周期。

```text
人类：Monaco 编辑器 -> 编译 WASM -> 上传 ┐
                                      ├-> WasmSandboxExecutor -> 世界
AI：  MCP 看世界 -> 生成 WASM -> 部署 ┘
```

### 4.1 MCP 工具分类

| 类别 | 代表性工具 | 说明 |
|------|-----------|------|
| 世界查看 | `swarm_get_snapshot`, `swarm_get_terrain`, `swarm_list_drones`, `swarm_get_room` | AI agent 感知世界的「眼睛」 |
| 部署 | `swarm_deploy`, `swarm_validate_module`, `swarm_list_modules` | WASM 上传、签名校验与预检 |
| 调试 | `swarm_explain_last_tick`, `swarm_get_tick_trace`, `swarm_dry_run`, `swarm_simulate` | 开发者诊断与离线模拟 |
| 经济 | `swarm_get_economy`, `swarm_get_economy_trend`, `swarm_get_drone_efficiency` | 资源流与 owner-only drone efficiency 分析；efficiency 是经济分析工具，不是新的顶层分类 |
| 锦标赛 | `swarm_tournament_create`, `swarm_tournament_status`, `swarm_match_result` | 竞技赛事管理 |

### 4.1a MCP Capability Profiles

MCP 工具按 capability profile 分组：

| Profile | 包含工具 | 适用场景 |
|---------|---------|---------|
| onboarding | `swarm_get_info` + `swarm_get_docs` + `swarm_get_schema` + `resources/list` + `resources/read`；SDK discovery 指向 signed REST `GET /sdk/:lang` | AI agent 首次接入 |
| play | world view + queries + economy | 日常游戏 |
| deploy | upload + validate + list | 代码部署 |
| debug | tick trace + dry run + simulate | 开发诊断 |
| arena | 创建/预提交/状态/结果 | 竞技赛事 |

### 4.1b MCP Rate Limits

MCP rate limit 是公开 API 行为，由 design 定义、IDL 和 Registry 下沉。限额按工具声明的 `rate_limit_key` 维度独立计数。以下 named profiles 是 IDL `mcp_tools.rate_limits` 的 canonical 输入：

| Named profile | Limit |
|---------------|-------|
| query | 50/tick |
| debug | 30/tick |
| dev_aux | 20/tick |
| deploy | 10/h |
| admin | 10/h |

每个工具仍携带显式 `rate_limit`，不得根据 MCP category 猜测。默认分配与例外如下：

| 工具组 | Per-tool rate limits |
|--------|----------------------|
| Onboarding | info 100/min；snapshot 1/tick；resources/rooms/drones 读取 10/tick；code/docs/schema 使用 dev_aux 20/tick |
| Play | replay 5/min；其余 Play 查询 10/tick |
| Deploy | deploy/validate 使用 deploy 10/h；deploy status/list 使用 dev_aux 20/tick；config/rules/modules 读取 10/tick |
| Debug | tick trace/engine stats/sandbox profile/state checksum 使用 debug 30/tick；list errors 使用 dev_aux 20/tick；simulate/dry-run 50/tick；explain last tick 10/tick |
| Arena | create/match result 20/tick；precommit 5/tick；status 50/tick |
| Resources | list/read 使用 query 50/tick |

### 4.2 明确不在 MCP 中

MCP 不做游戏动作。不存在 `swarm_move`、`swarm_attack`、`swarm_build` 等工具。AI agent 必须编写 WASM 代码来实现策略，和人类玩家完全一样。

玩家可见 command/MCP 拒绝必须避免目标存在性 oracle。目标侧 absent、invisible、type-ineligible、target cooldown 和 protected target `SpawningGrace` failures 统一映射为 `NotVisibleOrNotFound`，不携带 target details 或 remaining ticks。`TargetOverloadCooldown` 与 `TargetFortifyCooldown` 可作为内部/admin trace 标签保留，但不得作为普通玩家可见 rejection，也不得暴露 remaining ticks。攻击者/source-owned cooldown（包括 fatigue、main-action quota、actor-own `SpawningGrace`）仍可返回 `CooldownActive`。

MCP 也不包含 Auth 工具、Auth aliases 或 Auth proxy wrappers。注册、CSR、证书续签、吊销、列表、检查和 Server CA trust discovery 只通过显式 REST action routes 完成：

- `POST /auth/register/challenge`
- `POST /auth/csr/submit`
- `POST /auth/cert/renew`
- `POST /auth/cert/revoke`
- `GET /auth/cert/list`
- `POST /auth/cert/check`
- `GET /auth/server/trust`

### 4.3 SDK 获取

SDK canonical route 是 signed REST：`GET /sdk/:lang`。`:lang` 是 SDK language identifier，例如 `typescript` 或 `rust`。该 route 使用应用层证书签名、rate limit 和 audience 检查；它不是 MCP 工具。

输出语义：`sdk_code`、`type_definitions`、`examples`、`abi_version`、`min_engine_version`。不支持的 language 返回 `SchemaViolation` 语义错误；频率超限返回 `RateLimited`。

---

## 5. 游戏 API（Command Intent Model）

WASM 模块通过 command intent model 与引擎交互：

```text
deploy: signed deploy payload -> wasm validation -> native precompile -> storage
tick:   tick(input_ptr, input_len, output_ptr, output_len) -> TickResult bytes
```

1. 引擎构建世界快照（按房间分片），根据玩家可见范围拼接子集，编码为 Swarm codec bytes，写入 WASM 线性内存。
2. 调用 `tick(input_ptr, input_len, output_ptr, output_len)`；WASM 模块读取 `TickInput`，写入 `TickResult`。
3. 引擎解码 `TickResult.commands` 并校验所有指令，再统一应用到世界；`TickResult.messages` 进入玩家消息队列。

ABI v2 是立即 breaking 的唯一 ABI surface。tick input、tick output 和全部 host payload 都使用 IDL-generated、versioned、little-endian、length-prefixed Swarm codec。JSON 只可作为调试显示格式，不能作为 ABI v2 的 tick 或 host wire format。

### 5.1 ABI v2 Version Domains

版本域彼此独立，不能互相推导：

| Domain | 作用 |
|--------|------|
| `api_semantics_version` | REST/MCP/Game API 语义版本 |
| `wire_schema_version` | IDL-generated Swarm codec schema 版本 |
| `abi_version` | WASM guest/host 调用约定版本；当前为 `v2` |
| `sdk_version` | SDK 包装层版本 |
| `world_rules_version` | 世界规则和配置语义版本 |
| `version_counter` | 单个 player/world/module_slot 的部署防重放计数器 |

### 5.2 TickInput 与 TickResult

`TickInput` 包含当前 tick、player_id、world_id、可见 snapshot、world config view、fuel budget hints 和 message inbox cursor。所有字段按 Swarm codec 编码。

`TickResult` 包含：

| 字段 | 语义 |
|------|------|
| `commands` | `CommandIntent[]`，由引擎校验后统一应用 |
| `messages` | module 产生的玩家消息或调试消息；进入消息队列，不直接改变世界状态 |

### 5.3 允许的 Host Function（查询专用，只读）

WASM 中仅可调用查询类 host function。所有函数只读，不计入指令预算但计入 fuel 预算：

```rust
fn host_get_terrain(room_id: u32, out_ptr: i32, out_len: i32) -> i32;
fn host_get_objects_in_range(x: i32, y: i32, range: u32, out_ptr: i32, out_len: i32) -> i32;
fn host_path_find(from_x: i32, from_y: i32, to_x: i32, to_y: i32, opts_ptr: i32, opts_len: i32, out_ptr: i32, out_len: i32) -> i32;
fn host_get_world_config(key_ptr: i32, key_len: i32, out_ptr: i32, out_len: i32) -> i32;
fn host_get_world_rules(rule_id_ptr: i32, rule_id_len: i32, out_ptr: i32, out_len: i32) -> i32;
fn host_get_random(sequence: u64, out_ptr: i32, out_len: i32) -> i32;
fn host_get_fuel_remaining() -> u64;
```

Host payloads use Swarm codec. Host result bytes use a guest buffer tagged header followed by payload:

```text
tag: u16
code: i32
payload_len: u32
payload: [u8; payload_len]
```

The host function return value is `bytes_written` when non-negative. A negative return value means ABI-level failure such as invalid guest pointer, insufficient output buffer, decode failure, or fuel exhaustion before writing a complete header. Domain query errors are encoded in the tagged `HostResult` header and payload, not as negative ABI returns.

`HostError` is an independent enum for host query semantics. It is separate from REST/MCP rejection reasons and separate from negative ABI failures. Hidden or absent entity queries return a successful empty result; they do not reveal whether the entity is outside visibility or absent from the world.

### 5.4 禁止的 Host Function

以下游戏动作不得作为 host function 暴露给 WASM。所有 mutating 操作通过 `TickResult.commands` 延迟模型提交，引擎在校验后统一应用：

- `host_move` / `host_move_to`
- `host_harvest` / `host_transfer` / `host_withdraw`
- `host_build` / `host_repair`
- `host_attack` / `host_ranged_attack` / `host_heal`
- `host_spawn` / `host_recycle`

### 5.5 CommandAction 定义

CommandAction 语义由本设计域定义：每个 command 是 player module 对未来世界状态变更的 intent，而不是立即执行的 host call。`CommandIntent` envelope 包含 `sequence`、required `idempotency_key`、optional `client_trace_id` 与嵌套的 `action`；`CommandAction` 仅包含 action kind 与 typed parameters。player identity、tick、source 与 auth context 由服务端注入 `RawCommand`，不属于玩家提供的 `CommandAction`。combat/effect 能力，包括 vanilla `Attack`/`RangedAttack`/`Heal` 与 special action，通过 ActionRegistry 派发，不作为 mutating host function。

ActionRegistry dispatch 的内部 `action_type` 选择一个 closed `ActionPayload` concrete schema；Vanilla schema 由 engine-owned registry 固定，扩展 schema 只能来自 enabled signed-plugin World Action Manifest。IDL generator 为每个 concrete payload 生成 Swarm codec，禁止 JSON/free-form map。wire 使用具体 action 名称作为 `type`，并把 selected payload fields 扁平化；因此同名 `target_id` 可按 action schema 分别是 `EntityId`（如 Attack）或 `PlayerId`（Overload）。

Move 使用 4 方向 N/S/E/W。消息不是 command action；消息由 `TickResult.messages` 单独返回。

### 5.6 Host Function 成本模型

每个 host function 定义 per-tick 资源约束：base fuel cost、payload byte cost、output byte cap、per-tick call cap 和 deterministic cache policy。Fuel deduction: 1 CPU cost unit = 1 wasmtime fuel unit。host call budget 独立于 WASM compute budget，两者均计入 per-tick 总量。

Pathfinding 确定性要求：固定 neighbor order（NESW 顺时针）、cost type（均一 1）、tie-break（最小 room_id+entity_id）、cache key（from, to）、cache hit/miss 等价性。

MCP Controller 查询经过 fog-of-war 后只公开 `room`、`level` 与 `owner`。`progress` 和 `downgrade_timer` 是 owner-only 字段：查询其他玩家 Controller 时必须省略，不得返回占位值或可推断的精度降级值。

MCP Structure 查询经过 fog-of-war 后可公开 `id`、`type`、`pos`、`hits` 与 `capacity`。`cooldown` 是 owner-only 字段：查询其他玩家 Structure 时必须省略，不得返回占位值、舍入值或可推断的 cooldown bucket。

MCP Drone 查询对可见非 owner 只公开 `id`、`room`、`body`、`lifespan`、`status` 与 visibility-filtered `overload_pressure`。`code_hash` 和 `fuel_used` 是 owner-only fields，非 owner 必须省略；代码内容仍只通过 owner-scoped `swarm_get_code`，fuel profiling 只通过 admin/debug surfaces。

`swarm_get_drone_efficiency` 的 aggregate efficiency 与 factors 是 owner-only strategy metrics；可见非 owner 不得查询，不返回降精度 bucket 或占位值。

### 5.7 SwarmError 错误格式

世界配置 `hint_level` 的 canonical 值为 `competitive | practice | training`，默认 `competitive`。它由服主在启动前配置并进入 `world_config_hash`；客户端/MCP 不能覆盖。`competitive` 只返回 canonical code，`practice` 增加 actor-authorized 修复提示，`training` 只在隔离训练世界增加 actor-authorized debug。`swarm_dry_run` 无论该值为何都固定使用 competitive-safe 输出。

Game MCP/JSON-RPC 使用 SwarmError envelope；Auth REST 使用独立 JSON `AuthError` envelope，不携带 Game `RejectionReason`：

| 字段 | 说明 |
|------|------|
| `error.code` | numeric transport error code；Swarm application error 使用 `-32000` |
| `error.message` | 人类可读摘要 |
| `error.data.rejection_reason` | canonical RejectionReason wire enum string |
| `error.data.debug_detail` | 非 canonical 上下文详情，不超过 512 bytes |
| `error.data.retry_allowed` | 是否可安全重试 |
| `error.data.idempotency_key` | 幂等重试 key |
| `error.data.retry_after_tick` | 建议最早重试 tick |

Auth REST 不使用 Game JSON-RPC `RejectionReason`。它使用独立 `AuthError` enum：

| AuthError | HTTP | 语义 |
|-----------|------|------|
| `InvalidTransportBinding` | 401 | 请求签名绑定的 transport 与实际 transport 不一致，或 transport 绑定字段缺失 |
| `AudienceMismatch` | 403 | 证书有效且签名有效，但证书 allowed audience 不覆盖该 transport |
| `InvalidCertificate` | 401 | 证书链、签名、usage、expiry 或 revocation 校验失败 |
| `RateLimited` | 429 | Auth operation rate limit exceeded |
| `RequestExpired` | 401 | Timestamp 无效或超出 60 秒 freshness window |
| `ReplayDetected` | 409 | Nonce 已使用，或 replay-store 安全性无法保证 |

### 5.8 swarm_simulate 与 swarm_deploy

`swarm_simulate` 给定 snapshot 离线模拟 N tick。不执行其他玩家 WASM，使用 NPC-only world。最大 100 tick，max_entities=1000，资源配额独立于热路径。输出 deterministic replay。

`swarm_deploy` 是 deploy mutation。部署签名 payload 必须绑定：

- `domain = "SWARM-DEPLOY-V1"`
- `wasm_hash`
- `metadata_hash`
- `player_id`
- `world_id`
- `module_slot`
- `version_counter`
- `transport`
- `signed_at`

`CodeSigningCertificate.allowed_audience` 单独检查。`version_counter` 在 `(player_id, world_id, module_slot)` 域内单调；同 counter+相同 `deploy_payload_hash` 的 retry 返回 AlreadyDeployed、原 deploy_id 与原 `redb_version_counter`，不递增、不重复扣费；同/低 counter 的不同 payload 拒绝。
