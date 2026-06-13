# P0-9: Command Source Model — 指令来源模型

> **状态**: Phase 0 Architecture Freeze | **目标**: 所有指令来源显式建模，不可伪造 auth context

## 1. 原则

**默认 gameplay 指令只来自 WASM。所有来源的 actor/capability/scope 由服务端注入，客户端不可自报。**

## 2. 指令来源

| Source | 描述 | auth_context | gameplay | audit | rate_limit |
|--------|------|-------------|----------|-------|------------|
| `WASM` | drone tick() 输出 | player_id (server-injected) | ✅ 是 | 完整 | fuel budget |
| `MCP_Deploy` | AI 部署 WASM | player_id + token scope | ❌ 否 | 完整 | 10/h |
| `MCP_Query` | AI 查询世界/调试 | player_id + token scope | ❌ 否 | 完整 | 50/tick |
| `Admin` | 管理操作 | admin_id + token scope | ❌ 否 | 完整 | 无限制 |
| `Replay` | 回放重放 | system (no player) | ❌ 否 | 完整 | N/A |
| `TestHarness` | 自动化测试 | test_context | ❌ 否 | 完整 | N/A |
| `Tutorial` | 教程引导 | tutorial_session | ⚠️ 仅教程世界 | 完整 | 10/tick |

## 3. 不可伪造的 Auth Context

每条 RawCommand 携带的服务端注入字段：

```json
{
  "command": { /* 原始指令 */ },
  "auth": {
    "source": "WASM",
    "player_id": 42,          // 服务端注入——不可由客户端提供
    "session_id": "sess_abc",
    "module_version": "v1.2.0",
    "tick_submitted": 4520,
    "tick_target": 4521
  }
}
```

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
| Tutorial | ✅ 独立世界 | ❌ |
| Admin | ✅ | ✅（裁判权限） |
