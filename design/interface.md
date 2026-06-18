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

| 类别 | 工具 | 用途 |
|------|------|------|
| **世界查看** | `swarm_get_snapshot` | 获取可见世界状态 |
| | `swarm_get_terrain` | 查看地形 |
| | `swarm_get_objects_in_range` | 查看范围内的实体 |
| | `swarm_get_world_rules` | 获取世界规则配置 |
| **部署** | `swarm_deploy` | 上传 WASM 模块 |
| | `swarm_validate_module` | 上传前预检 |
| | `swarm_rollback` | 回滚到之前版本 |
| | `swarm_list_modules` | 列出已部署的 WASM 模块 |
| **调试** | `swarm_explain_last_tick` | 解释上 tick 发生了什么 |
| | `swarm_inspect_entity` | 检查实体完整状态 |
| | `swarm_inspect_room` | 查看有视野的房间概况 |
| | `swarm_profile` | 策略性能指标 |
| | `swarm_dry_run_commands` | 干跑 Command JSON |
| | `swarm_get_replay` | 获取 tick 范围回放数据 |
| **学习** | `swarm_get_docs` | API 参考和游戏规则 |
| | `swarm_get_schema` | 游戏 API JSON Schema |
| | `swarm_get_available_actions` | 当前可用的 API 函数 |
| | `swarm_simulate` | 离线模拟：给定快照预测未来 N tick |
| **认证** | `swarm_get_server_trust` | 获取 server_id 与 Swarm CA fingerprint |
| | `swarm_register_challenge` | 获取注册/CSR PoW 挑战 |
| | `swarm_submit_csr` | 提交 CSR 并按设备 profile 签发应用层证书 |
| | `swarm_renew_certificate` | 续签应用层证书 |
| | `swarm_list_certificates` | 列出当前账号证书 |
| | `swarm_revoke_certificate` | 吊销证书 |
| | `swarm_token_refresh` | 刷新 Web session 兼容 token |
| | `swarm_auth_revoke` | 吊销 session/certificate/key |
| | `swarm_change_password` | 修改 recovery password |
| | `swarm_request_password_reset` | 请求恢复链接 |
| | `swarm_admin_create_password_reset` | 管理员生成恢复链接 |
| | `swarm_confirm_password_reset` | 确认恢复并签发新证书 |
| | `swarm_register_passkey` | 绑定 passkey 恢复因子 |
| | `swarm_recover_with_passkey` | 使用 passkey 恢复并签发新证书 |
| | `swarm_bind_email` | 绑定邮箱 |
| | `swarm_delete_account` | 删除账号 |
| | `swarm_restore_account` | 恢复已删除账号（grace period 内） |
| | `swarm_cancel_account_deletion` | 取消账号删除（同 restore） |
| | `swarm_federated_login` | 外部证书 bootstrap，本地重签证书 |
| | `swarm_update_profile` | 修改显示名称 |
| **锦标赛** | `swarm_tournament_precommit` | 锁定 WASM 模块 |
| | `swarm_tournament_create` | 创建 bracket |
| | `swarm_tournament_status` | 查询状态 |
| | `swarm_match_result` | 查询比赛结果 |
| **资源管理** | `resources/list` | 列出可用资源类型 |
| | `resources/read` | 读取资源定义 |

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

---
