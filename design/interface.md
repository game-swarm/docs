# MCP 接口与游戏 API

> MCP 接口与游戏 API 域文件。从 design/README.md 拆分。

## 4. MCP 接口——AI 玩家的操作界面

MCP 是 AI agent 的「屏幕和鼠标」——与人类玩家的 Web UI 完全同级。

**Schema 完整性要求**：所有 MCP 工具由 `game_api.idl.yaml`（game 工具）、`auth_api.idl.yaml`（auth 工具）和 `economy.idl.yaml`（经济工具）定义，经 CI 生成 `api-registry.md`。详见 [API Registry](specs/reference/api-registry.md) §3。

```
人类：Monaco 编辑器 → 编译 WASM → 上传 ─┐
                                       ├─→ WasmSandboxExecutor → 世界
AI：  MCP 看世界 → 生成 WASM → 部署 ───┘
```

### 4.1 MCP 工具分类

> **权威工具清单见 [API Registry](specs/reference/api-registry.md) §3** — Game API `all_declared=57` / `active_only=53` / `rfc_gated=4`，Auth API `all_declared=12` / `active_only=12` / `rfc_gated=0`。
>
> 以下为**概念分类概述**，不列完整表。所有工具的 canonical schema、replay_class、rate_limit、security columns 以 Registry 为准。本表仅作方向性说明，不得用于实现引用。

| 类别 | 代表性工具 | 说明 |
|------|-----------|------|
| **世界查看** | `swarm_get_snapshot`, `swarm_get_terrain`, `swarm_list_drones`, `swarm_get_room` | AI agent 感知世界的「眼睛」 |
| **部署** | `swarm_deploy` (deploy_mutation), `swarm_validate_module`, `swarm_list_modules` | WASM 上传与预检 |
| **调试** | `swarm_explain_last_tick`, `swarm_get_tick_trace`, `swarm_dry_run`, `swarm_simulate` | 开发者诊断与离线模拟 |
| **经济** | `swarm_get_economy`, `swarm_get_drone_efficiency`, `swarm_get_economy_trend` | 资源流查询 |
| **认证** | 见 [auth_api.idl.yaml](specs/reference/auth_api.idl.yaml) | 设备注册、证书管理、passkey 恢复等 |
| **锦标赛** | `swarm_tournament_create`, `swarm_tournament_status`, `swarm_match_result` | 竞技赛事管理 |

> ⚠️ **已从 registry 移除的工具**：`swarm_attack`/`swarm_build`/`swarm_move`/`swarm_spawn` → MCP 不做游戏动作；`swarm_rollback` → `swarm_admin_rollback`；`swarm_inspect_entity` → `swarm_get_drone`；`swarm_inspect_room` → `swarm_get_room`；`swarm_get_objects_in_range` → host function（非 MCP 工具）；`swarm_dry_run_commands` → `swarm_dry_run`。旧 OAuth / bearer / refresh-token 工具不在 Registry 中，认证入口为 CSR/certificate lifecycle（见 Registry §3.3）。

### 4.1a MCP Capability Profiles

MCP 工具按 capability profile 分组。详见 [API Registry](specs/reference/api-registry.md) §3.4。

| Profile | 包含工具 | 适用场景 |
|---------|---------|---------|
| onboarding | 首次接入流程工具（auth + help + docs） | AI agent 首次接入 |
| play | 游戏过程工具（world view + queries + economy） | 日常游戏 |
| deploy | 部署管理工具（upload + validate + list） | 代码部署 |
| debug | 调试与性能分析工具 | 开发诊断 |
| admin | 管理工具（证书吊销、账号恢复等） | 服务器管理 |
| arena | 赛事管理工具（创建/预提交/状态/结果） | 竞技赛事 |

### 4.2 明确不在 MCP 中

MCP 不做游戏动作。不存在 `swarm_move`、`swarm_attack`、`swarm_build` 等工具。AI agent 必须**编写 WASM 代码**来实现策略，和人类玩家完全一样。

---

## 5. 游戏 API（Deferred Command Model）

WASM 模块通过 **deferred command model** 与引擎交互：

```
部署:  上传 WASM → 验证 `wasm_module_hash` → 预编译为原生码 → 存储（按服务端派生 `compiled_artifact_hash` 索引）
tick:  tick(snapshot) → Command[]
```

1. 引擎构建世界快照（按房间分片），根据玩家可见范围拼接子集，写入 WASM 线性内存
2. 调用 `tick(ptr, len)` — WASM 模块接收快照，返回指令 JSON 列表
3. 引擎校验所有指令 → 应用到世界

快照格式为结构化数据（非纯文本 JSON），房间分片保证拼接无歧义。SDK 侧通过 `WorldSnapshot` 类型访问，无需感知底层分片结构。

### 5.1 允许的 Host Function（查询专用，只读）

WASM 中**仅可调用查询类 host function**——所有函数只读，不计入指令预算但计入 fuel 预算：

```rust
// 信息查询（只读，不改变世界状态）
fn host_get_terrain(room_id: u32, out_ptr: i32, out_len: i32) -> i32;
fn host_get_objects_in_range(x: i32, y: i32, range: u32, out_ptr: i32, out_len: i32) -> i32;
fn host_path_find(from_x: i32, from_y: i32, to_x: i32, to_y: i32, opts_ptr: i32, opts_len: i32, out_ptr: i32, out_len: i32) -> i32;

// 世界配置查询
fn host_get_world_config(key_ptr: i32, key_len: i32, out_ptr: i32, out_len: i32) -> i32;
fn host_get_world_rules(rule_id_ptr: i32, rule_id_len: i32, out_ptr: i32, out_len: i32) -> i32;

// 确定性随机
fn host_get_random(sequence: u64, out_ptr: i32, out_len: i32) -> i32;
```

> **注意**: 以下为概念签名。权威定义见 [API Registry](specs/reference/api-registry.md) §4.1

全部返回 `i32`：ret >= 0 = bytes_written，ret < 0 = canonical ABI error code（见 API Registry §4.5）。
`out_ptr`/`out_len`：WASM 分配缓冲区，host 写入结果后再次校验边界。

### 5.2 禁止的 Host Function

以下**游戏动作不得作为 host function 暴露给 WASM**。所有 mutating 操作通过 `tick() → Command[]` JSON 延迟模型提交，引擎在校验后统一应用：

- ❌ `host_move` / `host_move_to` — 改为 `{ "action": "Move", ... }` JSON 指令
- ❌ `host_harvest` / `host_transfer` / `host_withdraw`
- ❌ `host_build` / `host_repair`
- ❌ `host_attack` / `host_ranged_attack` / `host_heal`
- ❌ `host_spawn` / `host_recycle`

> **设计合同**: WASM 模块不直接调用 mutating host function。所有状态变更通过 `tick() → JSON` 延迟模型提交。

### 5.3 swarm_sdk_fetch — AI Agent 自举入口

`swarm_sdk_fetch` 是 AI agent 首次接入的关键工具——返回 SDK 代码和类型定义。

- Input: `{ language: "typescript" | "rust", include_examples: bool }`
- Output: `{ sdk_code: string, type_definitions: string, examples: string[], abi_version: string, min_engine_version: string }`
- Error: wire 仅返回 canonical `RejectionReason`（如 `RateLimited`、`SchemaViolation`、`InternalError`）；SDK 可在本地映射为 `sdk_not_found` / `unsupported_language` 等非 wire 分类，并必须标注不得写入 `error.data.rejection_reason`
- Rate Limit: 5/min
- Replay Class: read_replay_safe

### 5.4 CommandAction 定义 (单一事实源)

**CommandAction 的唯一权威定义在 [API Registry](specs/reference/api-registry.md) §1**。所有 11 个 CommandAction 变体 + `Action` dispatch 的完整 schema、参数、分类和 actor_id/object_id 语义以 Registry 为准。combat/effect 能力（包括 vanilla `Attack`/`RangedAttack`/`Heal` 与 8 个 special action）通过 ActionRegistry 派发，不作为顶层 CommandAction 变体计数。本文档及其他设计文档不得重新声明 CommandAction 列表或参数；只能引用 Registry。

Notes:
- Move: 4方向 (N/S/E/W)。8方向为 Out-of-Scope RFC，不在当前核心定义中。
- SendMessage: Out-of-Scope RFC: drone间消息传递。当前不在 Core CommandAction 中。

### 5.5 Host Function 成本模型

所有 host function 返回 `i32`（0=成功，负数=错误码）。每函数定义 per-tick 资源约束：

> 参见 [API Registry](specs/reference/api-registry.md) §4 — 统一预算和输出上限

Fuel deduction: 1 CPU cost unit = 1 wasmtime fuel unit。host call budget 独立于 WASM compute budget——两者均计入 per-tick 总量。

Pathfinding 确定性要求：固定 neighbor order（NESW 顺时针）、cost type（均一 1）、tie-break（最小 room_id+entity_id）、cache key（from, to）、cache hit/miss 等价性。

### 5.6 SwarmError 错误格式

统一错误格式由 [API Registry](specs/reference/api-registry.md) §8 SwarmError JSON-RPC Envelope 定义，遵循标准 JSON-RPC 2.0 error object：

| 字段 | 说明 |
|------|------|
| `error.code` | numeric JSON-RPC error code；Swarm application error 固定使用 `-32000`，不得填 RejectionReason 字符串 |
| `error.message` | 人类可读摘要 |
| `error.data.rejection_reason` | canonical RejectionReason wire enum string (48 codes, 见 Registry §2) |
| `error.data.debug_detail` | 非 canonical 上下文详情 (≤ 512 bytes)；详细程度由 `detail_level` 控制 |
| `error.data.retry_allowed` | 是否可安全重试 (machine-readable) |
| `error.data.idempotency_key` | 幂等重试 key (machine-readable) |
| `error.data.retry_after_tick` | 建议最早重试 tick (machine-readable) |

所有业务拒绝原因通过 `error.data.rejection_reason` 传递；所有错误上下文通过 `error.data.debug_detail` 传递，不在 wire enum 中增加新变体。condition → canonical RejectionReason → debug_detail template 的完整映射见 Registry §2.6。

**SwarmError SDK 本地分类 (非 wire 指引)**:
- retryable: wire `TimeoutExceeded` / `RateLimited`；SDK 可本地归类为 retryable，但不得把本地分类写入 `error.data.rejection_reason`
- fatal_validation: wire `InsufficientResource` / `NotOwner` / `SchemaViolation`；SDK 可本地归类为 fatal_validation，但 wire 仍只使用 canonical enum
- idempotent: deploy/validate 等可用 idempotency_key 安全重试

### 5.7 swarm_simulate 与 swarm_deploy

**swarm_simulate**: 给定 snapshot 离线模拟 N tick。不执行其他玩家 WASM——使用 NPC-only world。最大 100 tick，max_entities=1000，资源配额独立于热路径。输出 deterministic replay。参见 [API Registry](specs/reference/api-registry.md) §5。

**swarm_deploy 部署语义**: `replay_class: deploy_mutation` — 依赖 FDB `version_counter` 防重放（非 Dragonfly nonce/window）。同 `module_hash` 重试只扣费一次（idempotency_key = module_hash）。module 保留策略：最近 10 个版本保留，旧版本在无引用后 GC。

---
