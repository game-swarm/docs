# P0-9: Command Source Model — 指令来源模型

> **状态**: Phase 0 冻结 | **日期**: 2026-06-14 | **版本**: 1.0

> **状态**: Phase 0 Architecture Freeze | **目标**: 所有指令来源显式建模，不可伪造 auth context

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

### 2.2 扩展来源（Phase 1-2 实现）

| Source | 描述 | auth_context | gameplay | audit | rate_limit | visibility | budget |
|--------|------|-------------|----------|-------|------------|------------|--------|
| `Deploy` | 代码部署管线（非 MCP 入口） | player_id | ❌ 否 | 完整 | 1/tick | 玩家快照 | compile budget |
| `Rollback` | 管理回滚操作 | admin_id + rollback_token | ❌ 否 | **双人审计** — 需两个不同 admin 的 Ed25519 签名，服务端在 Source Gate 前强制执行 | 手动触发 | 历史状态 | N/A |
| `RuleMod` | Rhai 规则模组 actions | mod_id + world_owner_id | ⚠️ 仅经济 + 事件 | 完整 | 100 actions/tick | 规则作用域 | Rhai op budget |
| `Simulate` | `swarm_simulate` 试运行 | player_id + snapshot_id | ❌ 否（snapshot-bound dry-run） | 完整 | 5/tick | 快照副本 | 0.5× MAX_FUEL |
| `DryRun` | 部署前语法/校验试运行 | player_id | ❌ 否 | 完整 | 20/h | 无（仅编译） | compile budget |
| `Tutorial` | 教程引导（扩展） | tutorial_session + world_id | ⚠️ 仅教程世界 | 完整 | 10/tick | 教程房间 | tutorial budget |

### 2.3 来源能力约束

| Source | 允许写入世界 | 允许读写全局存储 | 允许部署代码 | 允许查询世界 | 允许触发战斗 |
|--------|------------|----------------|------------|------------|------------|
| `WASM` | ✅ | ✅ | ❌ | ✅（快照） | ✅（含六种特殊攻击：Hack/Drain/Overload/Debilitate/Disrupt/Fortify） |
| `MCP_Deploy` | ❌ | ❌ | ✅ | ❌ | ❌ |
| `MCP_Query` | ❌ | ❌ | ❌ | ✅ | ❌ |
| `Admin` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `Replay` | ❌（只读） | ❌（只读） | ❌ | ✅（回放范围） | ❌（只读） |
| `TestHarness` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `Tutorial` | ⚠️ 教程世界隔离 | ❌（独立 namespace） | ❌ | ⚠️ 教程房间 | ❌（无敌方） |
| `RuleMod` | ⚠️ deduct/award/emit_event | ❌ | ❌ | ❌ | ❌ |
| `Simulate` | ❌（snapshot copy） | ❌（snapshot copy） | ❌ | ✅（副本） | ⚠️ dry-run |
| `DryRun` | ❌ | ❌ | ❌（仅编译） | ❌ | ❌ |
| `Rollback` | ✅（回滚写入） | ✅ | ✅ | ✅ | N/A（回滚状态） |
| `Deploy` | ❌ | ❌ | ✅ | ❌ | ❌ |

### 2.4 Tutorial 来源的隔离约束

`Tutorial` 来源的指令**仅可在 `world.mode = "tutorial"` 的世界中接受**。在非 Tutorial 世界收到的 Tutorial 来源指令 → 静默丢弃 + 记录审计日志。Tutorial 世界的全局存储使用独立 namespace（`tutorial_{world_id}`），不与正式世界互通。

## 3. 不可伪造的 Auth Context + 代码签名

### 3.1 身份模型

采用**服务端签发证书**模式：

```
注册/登录:  OAuth2 (GitHub/Google) → 服务端验证身份 → 签发短期证书
代码签名:  WASM 部署附带证书签名 → 服务端验签
吊销:      证书过期（24h 默认）/ 手动吊销 → 凭据泄露可止损
```

**为何不用客户端 keypair**：新手友好（不需要理解密钥管理）、吊销可控（ban 玩家 = 吊销证书）、OAuth2 已有成熟的认证基础设施。

### 3.2 Auth Context

每条 RawCommand 携带的服务端注入字段：

```json
{
  "command": { /* 原始指令 */ },
  "auth": {
    "source": "WASM",
    "player_id": 42,                // 服务端注入——不可由客户端提供
    "cert_fingerprint": "sha256:abcd1234...",  // 部署时使用的证书指纹
    "session_id": "sess_abc",
    "module_hash": "blake3:def567...",         // WASM 模块内容哈希
    "tick_submitted": 4520,
    "tick_target": 4521
  }
}
```

### 3.3 代码签名验证

WASM 部署 (`swarm_deploy` / MCP_Deploy / Deploy) 时：

1. 客户端发送 WASM 字节 + 证书（含服务端签名）
2. 服务端验证证书未过期、未被吊销
3. 服务端用证书中的 player_id 覆盖任何客户端自报的 ID
4. 服务端计算 `module_hash = Blake3(WASM bytes)`，写入 `auth.module_hash`
5. tick 执行阶段，引擎验证 `module_hash` 匹配已部署模块

**禁止**：客户端在 Command body 中自报 `player_id`。如果客户端提供了 player_id，服务端用它自己的值覆盖。

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
   ──→ 进入 Command Validation Pipeline (P0-2)
```

## 5. Replay 与审计

每条指令在 TickTrace 中记录完整 auth context。Replay 使用 `Replay` source，跳过 Source Gate 但保留完整 auth 信息。

## 6. World/Arena 差异

| Source | World | Arena |
|--------|-------|-------|
| WASM | ✅ | ✅（赛前锁定版本） |
| MCP_Deploy | ✅ 随时 | ❌ 赛后不可 |
| MCP_Query | ✅ | ✅ |
| Deploy | ✅ 随时 | ❌ 赛后不可 |
| RuleMod | ✅（服主配置） | 赛前锁定 |
| Simulate | ✅（最多 5/tick） | ✅（最多 3/tick） |
| DryRun | ✅ | ✅ |
| Tutorial | ✅ 独立世界 | ❌ |
| Admin | ✅ | ✅（裁判权限） |
| Rollback | ✅ 双人审计 | ❌ |
| Replay | ✅ | ✅ 赛后自动公开 |
| TestHarness | ✅ | ✅ |
