# MCP 接口与游戏 API

> MCP 接口与游戏 API 域文件。从 design/README.md 拆分。

## 4. MCP 接口——AI 玩家的操作界面

MCP 是 AI agent 的「屏幕和鼠标」——与人类玩家的 Web UI 完全同级。

**Schema 完整性要求**：所有 MCP 工具必须具备 `inputSchema`、`outputSchema` 和 `error` schema，由 `game_api.idl` 生成。特别是以下工具必须进入工具目录并提供完整的 request/response/error 定义和 rate limit：`swarm_sdk_fetch`、`swarm_get_schema`、`swarm_get_docs`、`swarm_get_player_status`、`swarm_deploy`、`swarm_validate_module`、`swarm_get_snapshot`、`swarm_get_available_actions`、`swarm_explain_last_tick`、`swarm_submit_csr`。

```
人类：Monaco 编辑器 → 编译 WASM → 上传 ─┐
                                       ├─→ WasmSandboxExecutor → 世界
AI：  MCP 看世界 → 生成 WASM → 部署 ───┘
```

### 4.1 MCP 工具分类

> 权威工具清单见 [API Registry](specs/reference/api-registry.md) §3 — 46 工具，含 Economy/SDK/Resources 分类

| 类别 | 工具 | 用途 | replay_class |
|------|------|------|-------------|
| **世界查看** | `swarm_get_snapshot` | 获取可见世界状态 | read_replay_safe |
| | `swarm_get_terrain` | 查看地形 | read_replay_safe |
| | `swarm_get_objects_in_range` | 查看范围内的实体 | read_replay_safe |
| | `swarm_get_world_rules` | 获取世界规则配置 | read_replay_safe |
| **部署** | `swarm_deploy` | 上传 WASM 模块 | idempotent_mutation |
| | `swarm_validate_module` | 上传前预检 | read_replay_safe |
| | `swarm_rollback` | 回滚到之前版本 | idempotent_mutation |
| | `swarm_list_modules` | 列出已部署的 WASM 模块 | read_replay_safe |
| **调试** | `swarm_explain_last_tick` | 解释上 tick 发生了什么 | read_replay_safe |
| | `swarm_inspect_entity` | 检查实体完整状态 | read_replay_safe |
| | `swarm_inspect_room` | 查看有视野的房间概况 | read_replay_safe |
| | `swarm_profile` | 策略性能指标 | read_replay_safe |
| | `swarm_dry_run_commands` | 干跑 Command JSON | read_replay_safe |
| | `swarm_get_replay` | 获取 tick 范围回放数据 | read_replay_safe |
| **学习** | `swarm_get_docs` | API 参考和游戏规则 | read_replay_safe |
| | `swarm_get_schema` | 游戏 API JSON Schema | read_replay_safe |
| | `swarm_get_available_actions` | 当前可用的 API 函数 | read_replay_safe |
| | `swarm_simulate` | 离线模拟：给定快照预测未来 N tick | read_replay_safe |
| **经济** | `swarm_get_economy` | 当前 tick 经济全貌（收入/支出/存储/税率） | read_replay_safe |
| | `swarm_get_drone_efficiency` | 每 drone 效率统计（最近 N tick） | read_replay_safe |
| | `swarm_get_economy_trend` | 经济趋势线（energy/drones/rooms/storage） | read_replay_safe |
| **认证** | `swarm_get_server_trust` | 获取 server_id 与 Swarm CA fingerprint | read_replay_safe |
| | `swarm_register_challenge` | 获取注册/CSR PoW 挑战 | read_replay_safe |
| | `swarm_submit_csr` | 提交 CSR 并按设备 profile 签发应用层证书 | non_idempotent_mutation |
| | `swarm_renew_certificate` | 续签应用层证书 | non_idempotent_mutation |
| | `swarm_list_certificates` | 列出当前账号证书 | read_replay_safe |
| | `swarm_revoke_certificate` | 吊销证书 | admin_critical |
| | `swarm_token_refresh` | 刷新 Web session 兼容 token | non_idempotent_mutation |
| | `swarm_auth_revoke` | 吊销 session/certificate/key | admin_critical |
| | `swarm_change_password` | 修改 recovery password | non_idempotent_mutation |
| | `swarm_request_password_reset` | 请求恢复链接 | non_idempotent_mutation |
| | `swarm_admin_create_password_reset` | 管理员生成恢复链接 | admin_critical |
| | `swarm_confirm_password_reset` | 确认恢复并签发新证书 | non_idempotent_mutation |
| | `swarm_register_passkey` | 绑定 passkey 恢复因子 | non_idempotent_mutation |
| | `swarm_recover_with_passkey` | 使用 passkey 恢复并签发新证书 | non_idempotent_mutation |
| | `swarm_bind_email` | 绑定邮箱 | non_idempotent_mutation |
| | `swarm_delete_account` | 删除账号 | admin_critical |
| | `swarm_restore_account` | 恢复已删除账号（grace period 内） | admin_critical |
| | `swarm_cancel_account_deletion` | 取消账号删除（同 restore） | admin_critical |
| | `swarm_federated_login` | 外部证书 bootstrap，本地重签证书 | non_idempotent_mutation |
| | `swarm_update_profile` | 修改显示名称 | non_idempotent_mutation |
| **锦标赛** | `swarm_tournament_precommit` | 锁定 WASM 模块 | read_replay_safe |
| | `swarm_tournament_create` | 创建 bracket | read_replay_safe |
| | `swarm_tournament_status` | 查询状态 | read_replay_safe |
| | `swarm_match_result` | 查询比赛结果 | read_replay_safe |

### 4.1a MCP Capability Profiles

MCP 工具按 capability profile 分组，`swarm_get_schema(profile=...)` 返回最小集：

| Profile | 包含工具 | 适用场景 |
|---------|---------|---------|
| onboarding | swarm_get_server_trust, swarm_register_challenge, swarm_submit_csr, swarm_sdk_fetch, swarm_get_docs | AI agent 首次接入 |
| play | swarm_get_snapshot, swarm_get_terrain, swarm_get_objects_in_range, swarm_get_world_rules, swarm_deploy, swarm_validate_module | 日常游戏操作 |
| deploy | swarm_deploy, swarm_validate_module, swarm_rollback, swarm_list_modules | 代码部署管理 |
| debug | swarm_explain_last_tick, swarm_inspect_entity, swarm_inspect_room, swarm_profile, swarm_dry_run_commands, swarm_get_replay, swarm_simulate, swarm_get_economy, swarm_get_drone_efficiency, swarm_get_economy_trend | 调试与性能分析 |
| admin | swarm_revoke_certificate, swarm_admin_create_password_reset, swarm_list_certificates, 资源管理工具 | 服务器管理 |

### 4.2 明确不在 MCP 中

MCP 不做游戏动作。不存在 `swarm_move`、`swarm_attack`、`swarm_build` 等工具。AI agent 必须**编写 WASM 代码**来实现策略，和人类玩家完全一样。

---

## 5. 游戏 API（Deferred Command Model）

WASM 模块通过 **deferred command model** 与引擎交互：

```
部署:  上传 WASM → 验证 → 预编译为原生码 → 存储（按 module_hash 索引）
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
fn host_get_terrain(x: i32, y: i32) -> i32;
fn host_get_objects_in_range(x: i32, y: i32, range: i32, out_ptr: i32, out_len: i32) -> i32;
fn host_path_find(from_x: i32, from_y: i32, to_x: i32, to_y: i32, out_ptr: i32, out_len: i32) -> i32;

// 世界配置查询
fn host_get_world_config(key_ptr: i32, key_len: i32, out_ptr: i32, out_len: i32) -> i32;
fn host_get_world_rules(out_ptr: i32, out_len: i32) -> i32;
```

> **注意**: 以下为概念签名。权威定义见 [API Registry](specs/reference/api-registry.md) §4.1

全部返回 `i32`：0 = 成功，负数 = 错误码。
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
- Error: `SDKNotFound`, `UnsupportedLanguage`, `RateLimited`
- Rate Limit: 5/min
- Replay Class: read_replay_safe

### 5.4 Command Schema 与 RejectionReason

参见 [API Registry](specs/reference/api-registry.md) §1 — 19 指令 (11核心+2Global+6特殊攻击)

Notes:
- Move: 4方向 (N/S/E/W)。8方向为 Future RFC
- SendMessage: Future RFC: drone间消息传递。当前不在 Core CommandAction 中。

RejectionReason enum: 参见 [API Registry](specs/reference/api-registry.md) §2 — 35 变体，统一为 `ObjectNotFound`、`InsufficientResource`、`NotOwner` 等

### 5.5 Host Function 成本模型

所有 host function 返回 `i32`（0=成功，负数=错误码）。每函数定义 per-tick 资源约束：

> 参见 [API Registry](specs/reference/api-registry.md) §4 — 统一预算和输出上限

Fuel deduction: 1 CPU cost unit = 1 wasmtime fuel unit。host call budget 独立于 WASM compute budget——两者均计入 per-tick 总量。

Pathfinding 确定性要求：固定 neighbor order（NESW 顺时针）、cost type（均一 1）、tie-break（最小 room_id+entity_id）、cache key（from, to）、cache hit/miss 等价性。

### 5.6 SwarmError / JSON-RPC Error Envelope

统一错误格式（JSON-RPC）：

{
  "jsonrpc": "2.0",
  "error": {
    "code": -32000,
    "message": "描述",
    "data": {
      "swarm_error": "InsufficientResources",
      "details": { "required": 200, "available": 50 },
      "retry_allowed": false,
      "idempotency_key": null
    }
  },
  "id": 1
}

SwarmError 分类：
- retry_allowed=true: TimeoutExceeded, RateLimited, ConflictRetry
- retry_allowed=false: InvalidCommand, InsufficientResources, NotAuthorized
- idempotent: deploy/validate 等可用 idempotency_key 安全重试

### 5.7 swarm_simulate 与 swarm_deploy

**swarm_simulate**: 给定 snapshot 离线模拟 N tick。不执行其他玩家 WASM——使用 NPC-only world。最大 100 tick，max_entities=1000，资源配额独立于热路径。输出 deterministic replay。参见 [API Registry](specs/reference/api-registry.md) §5。

**swarm_deploy 幂等性**: 同 module_hash 重试只扣费一次（idempotency_key = module_hash）。module 保留策略：最近 10 个版本保留，旧版本在无引用后 GC。

---
