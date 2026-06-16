# Command Source Model — 指令来源模型

> 详见 DESIGN §3

> **目标**: 所有指令来源显式建模，不可伪造 auth context

## 1. 原则

**默认 gameplay 指令只来自 WASM。所有来源的 actor/capability/scope 由服务端注入，客户端不可自报。**

## 2. 指令来源

### 2.1 来源矩阵

| Source | 描述 | auth_context | gameplay | audit | rate_limit | visibility | budget |
|--------|------|-------------|----------|-------|------------|------------|--------|
| `WASM` | drone tick() 输出 | player_id (server-injected) | ✅ 是 | 完整 | fuel budget | 快照范围 | 10M fuel/tick |
| `MCP_Deploy` | AI 部署 WASM 代码 | player_id + token scope | ❌ 否 | 完整 | 10/h | N/A | N/A |
| `MCP_Query` | AI 查询世界/调试 | player_id + token scope | ❌ 否 | 完整 | 50/tick | 快照范围 | N/A |
| `Admin` | 管理操作 | admin_id + token scope | ❌ 否 | 完整 | 无限制 | 全局 | N/A |
| `Replay` | 回放重放 | system (no player) | ❌ 否 | 完整 | N/A | 回放历史 | N/A |
| `TestHarness` | 自动化测试 | test_context | ❌ 否 | 完整 | N/A | 测试世界 | N/A |
| `Tutorial` | 教程引导 | tutorial_session + world_id | ⚠️ 仅教程世界 | 完整 | 10/tick | 教程房间 | N/A |

### 2.2 扩展来源

| Source | 描述 | auth_context | gameplay | audit | rate_limit | visibility | budget |
|--------|------|-------------|----------|-------|------------|------------|--------|
| `Deploy` | 代码部署管线（非 MCP 入口） | player_id | ❌ 否 | 完整 | 1/tick | 玩家快照 | compile budget |
| `Rollback` | 管理回滚操作 | admin_id + rollback_token | ❌ 否 | **双人审计** — 需两个不同 admin 的 Ed25519 签名，服务端在 Source Gate 前强制执行 | 手动触发 | 历史状态 | N/A |
| `RuleMod` | Rhai 规则模组 actions | mod_id + world_owner_id | ⚠️ damage/effect/attribute/event/resource/custom handler（经能力白名单） | 完整 | 100 actions/tick | 规则作用域 | Rhai op budget |
| `Simulate` | `swarm_simulate` 试运行 | player_id + snapshot_id | ❌ 否（snapshot-bound dry-run） | 完整 | 5/tick | 快照副本 | 0.5× MAX_FUEL |
| `DryRun` | 部署前语法/校验试运行 | player_id | ❌ 否 | 完整 | 20/h | 无（仅编译） | compile budget |
| `Tutorial` | 教程引导（扩展） | tutorial_session + world_id | ⚠️ 仅教程世界 | 完整 | 10/tick | 教程房间 | tutorial budget |

### 2.3 来源能力约束

| Source | 允许写入世界 | 允许读写全局存储 | 允许部署代码 | 允许查询世界 | 允许触发战斗 |
|--------|------------|----------------|------------|------------|------------|
| `WASM` | ✅ | ✅ | ❌ | ✅（快照） | ✅（含八种特殊攻击） |
| `MCP_Deploy` | ❌ | ❌ | ✅ | ❌ | ❌ |
| `MCP_Query` | ❌ | ❌ | ❌ | ✅ | ❌ |
| `Admin` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `Replay` | ❌（只读） | ❌（只读） | ❌ | ✅（回放范围） | ❌（只读） |
| `TestHarness` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `Tutorial` | ⚠️ 教程世界隔离 | ❌（独立 namespace） | ❌ | ⚠️ 教程房间 | ❌（无敌方） |
| `RuleMod` | ⚠️ damage_entity/set_entity_flag/deduct_resource/award_resource/emit_event/custom handler（经能力白名单校验） | ❌ | ❌ | ❌ | ❌ |
| `Simulate` | ❌（snapshot copy） | ❌（snapshot copy） | ❌ | ✅（副本） | ⚠️ dry-run |
| `DryRun` | ❌ | ❌ | ❌（仅编译） | ❌ | ❌ |
| `Rollback` | ✅（回滚写入） | ✅ | ✅ | ✅ | N/A（回滚状态） |
| `Deploy` | ❌ | ❌ | ✅ | ❌ | ❌ |

> **Admin 路径统一**：Admin 命令走标准 `validate_and_apply()` 管线，仅 RejectionReason 阈值放宽（Admin 可操作任意玩家的实体，所有权检查放宽）。编译期通过 Rust trait 设计确保任何修改世界状态的代码无法绕过此路径——`WorldMutate` trait 的唯一实现者是 `validate_and_apply()`，任何试图直接持有 `&mut World` 的代码会产生编译错误。不存在 Admin 专用的独立代码路径。

### 2.4 Tutorial 来源的隔离约束

`Tutorial` 来源的指令**仅可在 `world.mode = "tutorial"` 的世界中接受**。在非 Tutorial 世界收到的 Tutorial 来源指令 → 静默丢弃 + 记录审计日志。Tutorial 世界的全局存储使用独立 namespace（`tutorial_{world_id}`），不与正式世界互通。

## 3. 不可伪造的 Auth Context + 代码签名

### 3.1 身份模型

采用**客户端 Ed25519 密钥对 + 服务端签发证书**模式：

```
注册:  客户端生成 Ed25519 密钥对 → 提交公钥 → 服务端签发证书（公钥+player_id+有效期，服务端 Ed25519 签名）
签名:  部署 WASM 时客户端用私钥签名部署载荷 → 服务端验签
吊销:  证书过期（默认 90 天）/ CRL / Auth Service epoch emergency bump
```

**设计决策**（R2 用户裁决）：客户端持有 Ed25519 私钥，部署时对结构化载荷签名（非裸 WASM 字节）。此模型提供强审计链（可证明某玩家部署了某版本代码），同时通过 short-lived deploy_nonce 防重放。

### 3.2 部署载荷结构

客户端签名 payload（`DeployPayload`）至少包含以下必填字段：

```json
{
  "domain": "swarm-deploy",
  "module_hash": "blake3:abc123...",
  "player_id": 42,
  "world_id": "world_v1",
  "module_slot": "main",
  "version_tag": "v1.2.3",
  "deploy_nonce": "n_abc123...",
  "expires_at": 1782000000,
  "signature": "ed25519:sig..."
}
```

| 字段 | 说明 |
|------|------|
| `domain` | 域分隔符 `"swarm-deploy"`，防跨协议重放 |
| `module_hash` | `Blake3(WASM bytes)` |
| `player_id` | 服务端分配的玩家 ID |
| `world_id` | 目标世界 ID |
| `module_slot` | 模块槽位（main/defense/worker/...） |
| `version_tag` | 语义化版本号 |
| `deploy_nonce` | **服务端签发**的临时 nonce，短 TTL（60s），单次消费。通过 MCP `swarm_deploy_challenge` 获取 |
| `expires_at` | 部署过期时间（建议 ≤ 15 min from deploy_nonce issue） |
| `signature` | 客户端 Ed25519 私钥对上述字段的签名 |

### 3.3 部署验证流程

1. 客户端调用 MCP `swarm_deploy_challenge` → 服务端返回 `deploy_nonce`（单次，60s TTL）
2. 客户端构建 `DeployPayload`，用 Ed25519 私钥签名
3. 客户端发送 WASM bytes + DeployPayload + 证书
4. 服务端验证：
   a. 证书未过期、未被吊销（CRL 查询）
   b. `player_id` 从证书提取，覆盖任何客户端自报 ID
   c. `deploy_nonce` 有效且未消费（全局去重）
   d. `expires_at ≥ now()` 且 `≤ issued_time + 15 min`
   e. `module_hash == Blake3(收到的 WASM bytes)`
   f. Ed25519 验签通过（证书中的公钥 + signature + payload）
5. tick 执行时引擎验证 `module_hash` 匹配已部署模块

### 3.4 证书生命周期

- **有效期**：默认 90 天，可配置（`cert.validity_days`）
- **CRL 吊销点**：
  - deploy 时（校验证书是否在 CRL 中）
  - 每 tick 开始前（扫描活跃玩家的证书状态）
  - module cache validation 时（缓存 miss 时验证来源证书）
- **Auth Service epoch**：全局单调递增整数。emergency bump 后所有旧 epoch 证书立即失效，强制全量重新认证
- **紧急轮换 runbook**：Auth Service 私钥泄露 → bump epoch → 所有客户端重新签发证书 → 旧证书 CRL 加入永久条目

### 3.5 编译缓存键

编译缓存键包含以下不可变字段（任一变更 → 缓存 miss → 重新验证 + 编译）：

```
blake3(wasmparser_version || validation_policy_version || wasmtime_build_commit || target_arch || security_epoch)
```

缓存仅跳过编译，不跳过验证——每次 tick 启动时对缓存条目重新执行证书/CRL 检查。

## 4. 校验管线

```
RawCommand (携带 auth context)
    │
    ▼
┌─────────────────┐
│  Source Gate     │  ← 检查 source 是否允许提交 gameplay 指令
│  WASM → pass    │
│  MCP_Deploy →   │    ← 拒绝（MCP 不能提交 gameplay 指令）
│    reject 403   │
└────────┬────────┘
         │ pass
         ▼
┌─────────────────┐
│  Auth Verify     │  ← player_id 与 token 的 audience 绑定
└────────┬────────┘
         │
         ▼
   ──→ 进入 Command Validation Pipeline (specs/02-command-validation)
```

## 5. Replay 与审计

每条指令在 TickTrace 中记录完整 auth context。Replay 使用 `Replay` source，跳过 Source Gate 但保留完整 auth 信息。

## 6. World/Arena 差异

| Source | World | Arena |
|--------|-------|-------|
| WASM | ✅ | ✅（赛前锁定版本） |
| MCP_Deploy | ✅ 随时 | ✅ 随时 |
| MCP_Query | ✅ | ✅ |
| Deploy | ✅ 随时 | ✅ 随时 |
| RuleMod | ✅（服主配置） | 赛前锁定 |
| Simulate | ✅（最多 5/tick） | ✅（最多 10/tick — Arena 对模拟需求更高） |
| DryRun | ✅ | ✅ |
| Tutorial | ✅ 独立世界 | ❌ |
| Admin | ✅ | ✅（裁判权限） |
| Rollback | ✅ 双人审计 | ❌ |
| Replay | ✅ | ✅ 赛后自动公开 |
| TestHarness | ✅ | ✅ |

## 7. Session 与 Deploy Nonce 状态机

### 7.0 Transport Audience 与 Browser/Agent 判定

JWT Token 的 `aud`（audience）字段用于绑定 token 到特定 transport，防止跨 transport 重放：

| Transport | `aud` 值 | 判定方式 |
|-----------|---------|---------|
| MCP (Agent) | `mcp:{world_id}:{player_id}` | HTTP header `X-Swarm-Transport: mcp` + `Authorization: Bearer <jwt>` |
| WebSocket (Browser) | `ws:{world_id}:{player_id}` | WebSocket 升级请求中 `X-Swarm-Transport: ws` header + `?token=<jwt>` query param |
| REST (Browser/CLI) | `rest:{world_id}:{player_id}` | HTTP header `X-Swarm-Transport: rest` + `Authorization: Bearer <jwt>` |
| Replay (Viewer) | `replay:{world_id}:{match_id}` | HTTP header `X-Swarm-Transport: replay` |

**判定规则**：
- 缺少 `X-Swarm-Transport` header → 拒绝（`401 MissingTransportHeader`）
- `aud` 不匹配请求 transport → 拒绝（`403 AudienceMismatch`）
- MCP token **不得**用于 WebSocket 连接（Agent transport 与 Browser transport 不可互换）
- Deploy nonce 的 `audience` 字段同上规则

**Server-issued Certificate 所有权模型**：

```
证书层级:
  玩家 Ed25519 密钥对（客户端生成，私钥不离开客户端）
    │
    └─→ 服务端签发 Certificate { player_id, public_key, validity, epoch }
         │
         └─→ 部署时客户端用私钥签名 DeployPayload
               │
               └─→ 服务端用证书中的公钥验签

所有权: 玩家 = 私钥持有者 = 证书主体。证书不可跨玩家转移。
CRL: 吊销证书 → 该密钥对的所有部署立即失效 → player 需重新注册
Epoch: 全局 bump → 所有证书失效 → 全量重新认证
```

### 7.1 Session 生命周期

`session_id` 由 Auth Service 在玩家认证时签发，绑定到单个连接生命周期：

```
认证成功 → 签发 session_id（128-bit 随机，服务端签名）
    │
    ├─ 连接存活期间: session 有效
    ├─ 断连: session 标记为 pending_close
    ├─ 重连（60s 内）: 恢复原 session，refund credit 保留
    ├─ 超时（>60s）: session 关闭，refund credit 清零
    └─ 长期 agent: 定期心跳续期（建议 30s 间隔）
```

| 字段 | 说明 |
|------|------|
| session_id | 服务端签发，不可伪造 |
| player_id | 绑定单一玩家 |
| created_at | 签发时间 |
| expires_at | 上次心跳 + 60s（断连超时） |
| status | active / pending_close / closed |

### 7.2 Refund Credit 作用域

```
refund_credit 归属:
  player_id + wasm_slot + session_id + tick_window

跨 slot 不得转移（slot A 的 refund 不能给 slot B 用）
跨 session 不得转移（重连恢复除外）
跨 audience 不得转移（World refund 不能用于 Arena）
每 tick 上限: MAX_FUEL × 10%
```

### 7.3 Deploy Nonce 生命周期

```
1. 客户端调用 swarm_deploy_challenge → 服务端签发 nonce
   nonce 属性:
     - 128-bit 随机
     - TTL: 60s
     - audience: {player_id, world_id, wasm_slot}
     - IP-bound（默认）: 签发 IP 与请求 IP 一致才接受
     - single-use: 消费后立即作废

2. 客户端签名 payload（含 nonce）→ 提交部署

3. 服务端验证:
   a. nonce 存在且未被消费（全局去重）
   b. nonce 未过期（≤ 60s from issue）
   c. nonce audience 匹配请求（player/world/slot/IP）
   d. Ed25519 验签通过

4. 编译时间 > nonce TTL:
   → 服务端创建 pending_deploy 状态
   → 返回 deploy_token（30min TTL）
   → 编译完成后用 deploy_token 提交
   → 不延长裸 nonce（防重放窗口扩大）
```

### 7.4 状态转换表

| 状态 | 触发 | 下一状态 |
|------|------|---------|
| idle | 客户端请求 nonce | nonce_issued |
| nonce_issued | 客户端提交 signed payload + 验签通过 | compiling |
| nonce_issued | nonce 过期（60s） | idle（nonce 作废） |
| compiling | 编译成功 | deployed |
| compiling | 编译失败 | idle（可重试，需新 nonce） |
| compiling | deploy_token 过期（30min） | idle |
| deployed | tick 执行验证失败 | rejected |
| deployed | tick 执行成功 | active |

所有状态转换写入 audit log，包含 timestamp + session_id + player_id + world_id + slot。
