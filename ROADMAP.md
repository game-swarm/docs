# Swarm — 实现路线图

> **基于 R21 FROZEN 文档的代码对齐路线图。** 仅列出代码与文档之间的差异项。
> 已实现项不在此列出。DESIGN.md = 目标架构, ROADMAP.md = 实现追踪。

**生成日期**: 2026-06-18 | **基准**: R21 FROZEN docs vs engine main (0c67b07)
**测试基线**: engine 200 | sandbox 14 | gateway 16 | sdk-rust 8 | sdk-ts 11 | frontend 13

---

## 差距总览

| 类别 | 差距数 | 说明 |
|------|--------|------|
| MCP 工具 | 46 缺失 | Registry 64 工具, 代码仅 26 ToolInfo |
| RejectionReason | 29 缺失 | Registry 47 canonical codes, 代码 45 (含 19 非 canonical) |
| 遗留 MCP 工具 | 8 待删 | 代码有但 registry 已移除 |
| CommandAction | 1 命名 | `SpawnDrone` → `Spawn` |
| 模块缺失 | 3 | Economy, Empire Upkeep, Auth 独立模块 |
| API 文档 | 待刷新 | commands.md, mcp-tools.md 可能过时 |

---

## MCP 工具缺口 (G-MCP)

### 在 Registry 但不在代码中 (46 tools)

**World View (15):**
- [ ] swarm_get_drone
- [ ] swarm_get_room
- [ ] swarm_get_structure
- [ ] swarm_get_controller
- [ ] swarm_get_code
- [ ] swarm_get_visibility
- [ ] swarm_get_path
- [ ] swarm_get_resources
- [ ] swarm_get_info
- [ ] swarm_list_drones
- [ ] swarm_list_rooms
- [ ] swarm_list_structures
- [ ] swarm_list_controllers
- [ ] swarm_get_events
- [ ] swarm_get_messages

**Debug & Diagnostics (6):**
- [ ] swarm_dry_run (替代 swarm_dry_run_commands)
- [ ] swarm_get_tick_trace
- [ ] swarm_get_engine_stats
- [ ] swarm_get_state_checksum
- [ ] swarm_get_sandbox_profile
- [ ] swarm_list_errors

**Economy (3):**
- [ ] swarm_get_economy
- [ ] swarm_get_economy_trend
- [ ] swarm_get_drone_efficiency

**Deploy (2):**
- [ ] swarm_get_deploy_status
- [ ] swarm_list_deployments

**Leaderboard & Market (3):**
- [ ] swarm_get_leaderboard
- [ ] swarm_list_market_orders
- [ ] swarm_sdk_fetch

**Admin (6):**
- [ ] swarm_admin_ban_player
- [ ] swarm_admin_challenge
- [ ] swarm_admin_force_gc
- [ ] swarm_admin_get_audit_log
- [ ] swarm_admin_rollback
- [ ] swarm_admin_set_world_config

**Auth (11):**
- [ ] swarm_auth_login
- [ ] swarm_auth_logout
- [ ] swarm_auth_refresh
- [ ] swarm_auth_check
- [ ] swarm_auth_cert_issue
- [ ] swarm_auth_cert_list
- [ ] swarm_auth_cert_revoke
- [ ] swarm_auth_cert_rotate
- [ ] swarm_auth_device_list
- [ ] swarm_auth_device_register
- [ ] swarm_get_world_config

### 遗留工具清理 (8 tools)

在代码中但 registry 已移除 — 需从 engine mcp.rs 删除 match arms + ToolInfo:

- [ ] swarm_attack → 删除 (MCP 不做游戏动作)
- [ ] swarm_build → 删除
- [ ] swarm_move → 删除
- [ ] swarm_spawn → 删除
- [ ] swarm_oauth2_login → 删除 (统一证书认证)
- [ ] swarm_oauth2_callback → 删除
- [ ] swarm_rollback → swarm_admin_rollback
- [ ] swarm_token_refresh → swarm_auth_refresh
- [ ] swarm_dry_run_commands → swarm_dry_run
- [ ] swarm_inspect_entity → swarm_get_drone
- [ ] swarm_inspect_room → swarm_get_room
- [ ] swarm_get_objects_in_range → host function (非 MCP 工具)

---

## RejectionReason 缺口 (G-RR)

### 在 Registry 但不在代码中 (29)

**Pipeline 层:**
- [ ] InvalidJson
- [ ] SchemaViolation
- [ ] CommandBufferFull
- [ ] TimeoutExceeded

**Validation 层:**
- [ ] NotVisibleOrNotFound (替代 PlayerNotFound)
- [ ] TargetNotFound
- [ ] TargetNotVisible
- [ ] InvalidBodyPart
- [ ] NotEnoughBodyParts
- [ ] InvalidStructureType
- [ ] InvalidResourceType
- [ ] PositionOccupied
- [ ] ConstructionLimitReached
- [ ] CooldownActive
- [ ] InsufficientEnergy
- [ ] InsufficientResources
- [ ] FuelExhausted
- [ ] SafeModeActive
- [ ] TargetFortifyCooldown
- [ ] TargetOverloadCooldown

**Runtime 层:**
- [ ] InternalError
- [ ] ServerOverloaded
- [ ] SnapshotOverBudget

**Auth 层:**
- [ ] InvalidCertificate
- [ ] CertExpired
- [ ] TokenRevoked
- [ ] RefreshTokenInvalid
- [ ] NotAuthorized
- [ ] ScopeInsufficient
- [ ] SessionLimitReached
- [ ] DeviceNotRegistered
- [ ] MultiDeviceConflict
- [ ] UnknownCredential
- [ ] InternalAuthError

### 代码中但不在 Registry (19 — debug_detail 候选)

这些变体在代码中实现但 registry 将它们视为 `debug_detail` 字段内容而非 canonical wire code (per D2/B 设计决策):

- [ ] AlreadyDebilitated, AlreadyHacked, AlreadyFullHealth → debug_detail
- [ ] BodyTooLarge, MissingBodyPart, InsufficientMoveParts → debug_detail
- [ ] CarryFull, TargetEmpty, TargetFull, TargetFuelTooLow → debug_detail
- [ ] ExceedsRoomCapacity, TooManyConstructionSites → debug_detail
- [ ] Fatigued, StillSpawning → debug_detail
- [ ] FriendlyTarget, NotFriendly → debug_detail
- [ ] InvalidDamageType, InvalidTerrain → debug_detail
- [ ] NoPath, PathTooLong, OutOfRoom, TileBlocked, TileOccupied → debug_detail
- [ ] NotMovable, NotSource, NotYourRoom, NotYourSpawn → debug_detail
- [ ] OrderNotFound → debug_detail (替代 registry 的 OrderNotFound)
- [ ] PlayerNotFound → NotVisibleOrNotFound
- [ ] SourceEmpty → debug_detail
- [ ] TerminalRequired → debug_detail

---

## CommandAction (G-CMD)

- [ ] **SpawnDrone → Spawn**: engine 代码使用 `CommandAction::SpawnDrone`, registry 使用 `Spawn`. 统一为 `Spawn`.

---

## 模块缺口 (G-MOD)

- [ ] **Economy 模块**: 设计声明 `swarm_get_economy`, `swarm_get_economy_trend`, market orders 等经济查询工具，但 engine 无独立 economy 模块
- [ ] **Empire Upkeep**: 设计声明领土维护成本系统 (protocol hook + Vanilla 公式). 代码仅有 memory_upkeep (drone 内存维护), 无领土级 empire upkeep
- [ ] **Auth 独立模块**: CertificateIssuer 在 mcp.rs 中, 但设计声明 Auth 为独立控制面 (CSR, cert chain, device management). 需独立 auth 模块

---

## 实现优先级

### 🔴 P0 — 立即修复 (阻塞性)
1. `SpawnDrone` → `Spawn` 命名统一 (1 文件, 全局替换)
2. 删除 12 个遗留 MCP 工具 (mcp.rs match arms + ToolInfo + mcp_tool_source)

### 🟡 P1 — 高优先级 (核心功能)
3. MCP World View 工具 (15 tools) — AI agent 感知世界的"眼睛"
4. MCP Debug 工具 (6 tools)
5. RejectionReason registry 对齐 — 实现 29 个缺失变体

### 🟢 P2 — 中优先级 (生态完善)
6. MCP Auth 工具 (11 tools) + Auth 独立模块
7. MCP Admin 工具 (6 tools)
8. Economy 模块 + MCP Economy 工具 (3 tools)
9. MCP Leaderboard/Market 工具 (3 tools) + Deploy 工具 (2 tools)

### 🔵 P3 — 文档对齐
10. RejectionReason debug_detail 迁移 — 将 19 个非 canonical 变体移入 debug_detail
11. commands.md / mcp-tools.md 刷新
12. api-registry.md header 数字验证
