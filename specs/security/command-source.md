# Command Source Model — 指令来源模型

> 详见 design/engine.md

> **目标**: 所有指令来源显式建模，不可伪造 auth context

## 1. 原则

**默认 gameplay 指令只来自 WASM。所有来源的 actor/capability/scope 由服务端注入，客户端不可自报。**

## 2. 指令来源

### 2.1 来源矩阵

| Source | 描述 | auth_context | gameplay | audit | rate_limit | visibility | budget |
|--------|------|-------------|----------|-------|------------|------------|--------|
| `WASM` | drone tick() 输出 | player_id (server-injected) | ✅ 是 | 完整 | fuel budget | 快照范围 | 10M fuel/tick |
| `MCP_Deploy` | AI 部署 WASM 代码 | CodeSigningCertificate + signed DeployPayload | ❌ 否 | 完整 | 10/h | N/A | N/A |
| `MCP_Query` | AI 查询世界/调试 | ClientAuthCertificate + signed request | ❌ 否 | 完整 | 按 per-tool `rate_limit` + `rate_limit_key`；无 aggregate MCP cap | 快照范围 | N/A |
| `Admin` | 管理操作 | ClientAuthCertificate + `admin` scope + signed request | ❌ 否 | 完整 | 见 API Registry per-tool admin rate limit | 全局 | N/A |
| `Replay` | 回放重放 | system (no player) | ❌ 否 | 完整 | N/A | 回放历史 | N/A |
| `TestHarness` | 自动化测试 | test_context | ❌ 否 | 完整 | N/A | 测试世界 | N/A |
| `Tutorial` | 教程引导 | tutorial_session + world_id | ⚠️ 仅教程世界 | 完整 | 10/tick | 教程房间 | N/A |

### 2.2 扩展来源

| Source | 描述 | auth_context | gameplay | audit | rate_limit | visibility | budget |
|--------|------|-------------|----------|-------|------------|------------|--------|
| `Deploy` | 代码部署管线（非 MCP 入口） | player_id | ❌ 否 | 完整 | 1/tick | 玩家快照 | compile budget |
| `Rollback` | 管理回滚操作 | admin_id + rollback_token | ❌ 否 | **双人审计** — 需两个不同 admin 的 Ed25519 签名，服务端在 Source Gate 前强制执行 | 手动触发 | 历史状态 | N/A |
| `Simulate` | `swarm_simulate` 预测 fork | player_id + snapshot_id | ❌ 否 | 完整 | 50/tick | owner snapshot fork | simulation budget |
| `DryRun` | deterministic safe fork | player_id | ❌ 否 | 完整 | 50/tick | owner_safe | simulation budget |
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
| `Simulate` | ❌（snapshot copy） | ❌（snapshot copy） | ❌ | ✅（副本） | ⚠️ dry-run |
| `DryRun` | ❌ | ❌ | ❌（仅编译） | ❌ | ❌ |
| `Rollback` | ✅（回滚写入） | ✅ | ✅ | ✅ | N/A（回滚状态） |
| `Deploy` | ❌ | ❌ | ✅ | ❌ | ❌ |

> **Admin 路径统一**：Admin control-plane mutation 复用标准 validation primitives，但不进入 gameplay RawCommand queue；它在 tick-boundary admin event 阶段按独立 `admin_event_id` 排序应用。外部 source 不能直接持有 `&mut World`。

### 2.4 Tutorial 来源的隔离约束

`Tutorial` 来源的指令**仅可在 `world.mode = "tutorial"` 的世界中接受**。在非 Tutorial 世界收到的 Tutorial 来源指令 → 静默丢弃 + 记录审计日志。Tutorial 世界的全局存储使用独立 namespace（`tutorial_{world_id}`），不与正式世界互通。

## 3. 不可伪造的 Auth Context + 代码签名

### 3.1 身份模型

采用**客户端 Ed25519 私钥 + Server CA 签发应用层证书**模式：

```
注册:  客户端生成 Ed25519 密钥对 → 提交 CSR → Server CA 签发用途隔离证书
签名:  部署 WASM 时客户端用 CodeSigningCertificate 对 canonical payload（`domain=SWARM-DEPLOY-V1 + wasm_hash + metadata_hash + player_id + world_id + module_slot + version_counter + transport + signed_at`）签名 → 服务端验签；证书 allowed audience 独立检查
吊销:  证书吊销 / public key 吊销 / Server CA epoch emergency bump
```

**设计决策**：客户端持有 Ed25519 私钥，部署时对结构化载荷签名。`CodeSigningCertificate` 必须在提交时有效。防重放使用 `(player_id, world_id, module_slot)` 域内 counter：低 counter 或同 counter+不同 payload 拒绝；同 counter+相同 `deploy_payload_hash` 是幂等 retry。`compiled_artifact_hash` 由 Sandbox 派生，不参与客户端签名。

### 3.2 部署载荷结构

客户端签名 payload（`DeployPayload` / `SWARM-DEPLOY-V1`）只包含提交前客户端可知字段：

```json
{
  "domain": "SWARM-DEPLOY-V1",
"wasm_hash": "blake3:abc123...",
  "metadata_hash": "blake3:def456...",
  "player_id": 42,
  "world_id": "world_v1",
  "module_slot": "main",
  "version_counter": 17,
  "transport": "mcp",
  "signed_at": 1781697600
}
```

| 字段 | 说明 |
|------|------|
| `domain` | 域分隔符 `"SWARM-DEPLOY-V1"`，防跨协议重放 |
| `wasm_hash` | `Blake3(WASM bytes)`，canonical DeployPayload wire field |
| `metadata_hash` | `Blake3(mod.toml)` |
| `player_id` | 服务端分配的玩家 ID |
| `world_id` | 目标世界 ID |
| `module_slot` | 模块槽位（main/defense/worker/...） |
| `version_counter` | `(player_id, world_id, module_slot)` 域内单调递增计数器 |
| `transport` | 实际入口 transport 绑定；canonical wire values 为 `mcp`、`rest`、`ws`、`replay` |
| `signed_at` | 客户端签名时间戳（unix 秒） |

客户端 Ed25519 私钥对上述 canonical `DeployPayload` JSON bytes 签名；Base64 签名通过 `swarm_deploy.params.code_signature` 作为 payload 的 sibling 字段发送，不属于 `DeployPayload` 本体。证书 allowed audience 不作为客户端自报字段信任，服务端必须把 deploy 的实际入口 transport 与证书 allowed audience 做 membership 检查。`compiled_artifact_hash` 是 Sandbox 编译后派生字段，也不属于 `DeployPayload`。服务端 manifest 记录 `deploy_payload_hash = Blake3(canonical SWARM-DEPLOY-V1 payload)` 与 `compiled_artifact_hash`。

### 3.3 部署验证流程

1. 客户端构建 `DeployPayload`，新内容使用高于 current 的 `version_counter`，用 Ed25519 私钥签名；完全相同的 retry 复用原 payload/counter/signature
2. 客户端通过 `swarm_deploy` 同步发送 WASM bytes + `mod.toml` + DeployPayload + `code_signature` + `certificate_id`；服务端不接受先签名后异步补传 bytes 的 deploy
3. 服务端验证：
   a. `CodeSigningCertificate` 可追溯到本服 Server CA，usage=code_signing
   b. 证书在部署提交时未过期、未被吊销（CRL 查询）
   c. `player_id` 从证书提取，覆盖任何客户端自报 ID
   d. Ed25519 验签通过，并计算 canonical `deploy_payload_hash`
   e. `version_counter == current` 且 payload hash 相同 → `already_deployed`，返回原 deploy_id / `redb_version_counter`，不分配新 counter
   f. `version_counter <= current` 且 payload hash 不同 → `stale_deploy`
   g. `version_counter > current` → 继续新部署验证
   h. `wasm_hash == Blake3(收到的 WASM bytes)`，`metadata_hash == Blake3(收到的 mod.toml)`
   i. Deploy payload 的 `transport` 与实际入口 transport 一致；不一致为 `401 InvalidTransportBinding`
   j. 证书 allowed audience 覆盖实际入口 transport；不覆盖为 `403 AudienceMismatch`
4. 编译完成后计算 `compiled_artifact_hash`，并把 signed `wasm_hash` 记录为 manifest 内部字段 `wasm_module_hash`；tick 执行时引擎验证运行时 artifact 匹配 `compiled_artifact_hash`，replay/audit 使用 manifest `wasm_module_hash` 追溯原始代码；证书自然过期不终止已部署模块

### 3.4 证书生命周期

- **有效期**：按证书 profile 配置；常用设备可 30–180 天，临时设备 15min–24h；管理员权限通过短 TTL ClientAuthCertificate + `admin` scope 表达
- **CRL 吊销点**：
  - deploy 提交时（校验证书是否在 CRL 中）
  - certificate renewal / CSR recovery 时（校验替换前证书和 public key 状态）
  - revocation cache miss 时向 Auth Service 查询
- **CRL 保留窗口**：在线 CRL 只需保留尚未过期证书和最近过期证书。保留期为 `max_certificate_ttl + max_clock_skew + operational_grace`。超过窗口的吊销项可从在线认证路径清理。
- **过期 vs 吊销**：证书自然过期不影响已部署模块继续运行；证书吊销是安全事件，服务器按 revocation reason 冻结、回滚或继续允许既有模块。
- **Auth Service epoch**：全局单调递增整数。emergency bump 后所有替换前 epoch 证书立即失效，强制全量重新认证
- **紧急轮换 runbook**：Server CA 泄露 → bump epoch → 所有客户端重新签发证书 → 当前有效窗口内替换前证书加入 CRL

### 3.5 编译缓存键

编译缓存键包含以下不可变字段（任一变更 → 缓存 miss → 重新验证 + 编译）：

```
blake3(wasmparser_version || validation_policy_version || wasmtime_build_commit || target_arch || security_epoch)
```

缓存仅跳过编译，不跳过部署时验证；缓存键使用 `compiled_artifact_hash` 与 validation/security epoch，已部署模块运行时校验 `compiled_artifact_hash`，代码签名校验 wire `wasm_hash`，审计记录 manifest `wasm_module_hash`。证书自然过期不触发缓存失效；吊销导致的冻结/回滚由 revocation reason 策略处理。

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
│  Auth Verify     │  ← player_id 从证书注入，证书 allowed audience 覆盖实际 transport
└────────┬────────┘
         │
         ▼
   ──→ 进入 Command Validation Pipeline (specs/core/command-validation)
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
| Simulate | ✅（50/tick） | ✅（50/tick） |
| DryRun | ✅（50/tick） | ✅（50/tick） |
| Tutorial | ✅ 独立世界 | ❌ |
| Admin | ✅ | ✅（裁判权限） |
| Rollback | ✅ 双人审计 | ❌ |
| Replay | ✅ owner/private policy | ✅ 赛后按 room visibility（public/unlisted/private） |
| TestHarness | ✅ | ✅ |

## 7. Transport Binding 与 Deploy Nonce 状态机

### 7.0 Transport Binding 判定

应用层证书请求签名绑定 `cert_id`、`player_id` 与实际 transport，防止跨 transport 重放。所有客户端，包括 Browser，都使用应用层证书签名；浏览器 cookie 或浏览器请求头检查不是认证分支。普通 CORS 可存在，但不作为身份或信任依据。

| Transport | 应用层证书绑定 | 判定方式 |
|-----------|----------------|---------|
| MCP | signed `cert_id` + `player_id` + actual MCP transport | `POST /mcp` + `Swarm-Certificate` + `Swarm-Cert-Id` + `Swarm-Signature` |
| WebSocket | signed `cert_id` ticket + actual `ws` transport | WebSocket query `room`, `sessionId`, `certId`, `expires`, `signature` |
| Auth REST | PoW/CSR signature or signed `ClientAuthCertificate`, depending on route | Explicit `/auth/*` REST action route |
| REST | signed `cert_id` + `player_id` + actual REST transport | REST request + application certificate signature |
| Replay | replay transport or anonymous public replay | public replay policy or signed private replay request |

**判定规则**：
- 缺少必需 transport binding 字段，或签名 payload 中的 transport 与实际请求 transport 不一致 → 拒绝（`401 InvalidTransportBinding`）
- 签名有效但证书 allowed audience 不覆盖实际请求 transport → 拒绝（`403 AudienceMismatch`）
- MCP、WebSocket、spectator、Auth REST、SDK REST 与普通 REST transport 不可互换
- Deploy payload 的 `transport` 必须为实际入口的 canonical transport value（`mcp`、`rest`、`ws` 或 `replay`），证书 audience 另行检查 membership

**Server-issued Certificate 所有权模型**：

```
证书层级:
  用户 Ed25519 密钥对（客户端生成，私钥不离开客户端）
    │
    └─→ Server CA 签发 CodeSigningCertificate { player_id, public_key, usage, validity }
         │
         └─→ 部署提交时客户端用私钥签名 DeployPayload
               │
               └─→ 服务端用证书中的公钥验签

所有权: 玩家 = 私钥持有者 = 证书主体。证书不可跨玩家转移。
CRL: 吊销证书是安全事件；按 reason 冻结、回滚或继续允许既有模块。自然过期不影响已部署模块。
Epoch: 全局 bump → 所有当前有效证书失效 → 全量重新认证
```

### 7.1 Connection Session 生命周期

`session_id` 是 Gateway 连接/退款 credit 作用域标识，不是认证凭据。认证身份来自应用层证书签名，`session_id` 只绑定单个连接生命周期：

```
signed connection accepted → 签发 session_id（128-bit 随机，服务端签名）
    │
    ├─ 连接存活期间: session 有效
    ├─ 断连: session 标记为 pending_close
    ├─ 重连（60s 内）: 恢复原 session，refund credit 保留
    ├─ 超时（>60s）: session 关闭，refund credit 清零
    └─ 长期 agent: 定期心跳续期（建议 30s 间隔）
```

| 字段 | 说明 |
|------|------|
| session_id | Gateway 签发，不可伪造；不可替代应用层证书认证 |
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

### 7.3 Version Counter 防重放

Deploy 不使用服务端 nonce。防重放通过 `(player_id, world_id, module_slot)` 域内单调递增 `version_counter` 实现：

```
1. 客户端为每个 world/module slot 维护 version_counter（初始 0；新内容通常使用 current + 1，允许跳号）

2. 客户端构建 DeployPayload：
   - version_counter > 客户端已知 current_version_counter
   - `wasm_hash = Blake3(WASM bytes)`；服务端 manifest 将同一值存为 `wasm_module_hash`
   - metadata_hash = Blake3(mod.toml)
   - player_id = 证书主体 player_id
   - world_id = 目标世界
   - module_slot = 目标槽位
   - transport = 实际入口 transport
   - signed_at = 客户端当前时间戳
   - 用 CodeSigningCertificate 对应私钥签名

3. 服务端先验签和验证证书/transport/audience，再按 `(player_id, world_id, module_slot)` 原子比较 counter：
   a. `version_counter == current` 且 `deploy_payload_hash == committed.deploy_payload_hash` → `already_deployed`，返回原 deploy_id / `redb_version_counter`，不扣费、不重新编译、不递增
   b. `version_counter <= current` 且 payload hash 不同 → `stale_deploy`
   c. `version_counter > current` → 接受新部署；允许跳号并原子更新 current
   d. CodeSigningCertificate allowed audience 必须覆盖实际入口；不匹配 → `403 AudienceMismatch`

4. 只有 counter/payload 组合满足 3a 时才返回 `already_deployed`；不能用相同 hash 绕过不同 world/slot/counter 的验证。
```

### 7.4 状态转换表

| 状态 | 触发 | 下一状态 |
|------|------|---------|
| idle | 客户端提交 signed DeployPayload + 验签 + counter 通过 | compiling |
| idle | counter == current 且 payload hash 相同 | already_deployed |
| idle | counter ≤ current 且 payload hash 不同 | rejected (stale_deploy) |
| compiling | 编译成功 | deployed |
| compiling | 编译失败 | idle（完全相同请求可复用 counter 重试；变更 payload 必须使用更高 counter） |
| deployed | tick 执行验证失败 | rejected |
| deployed | tick 执行成功 | active |

所有状态转换写入 audit log，包含 timestamp + session_id + player_id + world_id + slot。

## 8. 确定性语义

### 8.1 RawCommand 顺序

Deploy 不进入 RawCommand queue。Gameplay RawCommand queue 只包含 WASM `TickResult.commands` 经服务端注入后的命令；Admin/TestHarness/Tutorial 是独立 versioned control-plane events，只读 query 不进入任何 mutation queue。MCP_Deploy 按 §7.3 与 `activation_tick >= current_tick + 1` 生效。

同 tick gameplay RawCommand 的唯一顺序是 `(player_order, player_id, sequence, command_id)`；`player_order` 来自 canonical shuffle，`command_id = Blake3(canonical RawCommand)`。Control-plane events 在独立阶段按各自稳定 ID 排序，不能插入 gameplay tuple。

Replay 必须使用相同的命令顺序重建相同结果。Deploy replay 使用 redb deploy manifest 的 `redb_version_counter` 和 `activation_tick`，不插入 gameplay RawCommand 顺序。

### 8.2 墙钟超时与编译超时

Wall-clock timeout 和 compile-time timeout 在正常执行和 replay 中行为不同：

| 场景 | 正常执行 | Replay |
|------|---------|--------|
| WASM tick() 超时 | COLLECT 返回整批 0 command；没有任何该玩家命令进入 EXECUTE | 重放记录的 0-command collect result |
| 编译超时 | 部署失败，返回 `compile_timeout` | 重放记录的编译结果（成功/失败/超时） |
| DeployPayload 过期 | 拒绝部署 | 重放记录的部署结果 |

Replay 不重新编译 WASM、不重新执行 tick()——使用记录的命令序列和 tick delta。

### 8.3 确定性吊销结果

证书吊销按 reason 产生确定性结果：

| Revocation reason | 已部署模块行为 | 新部署 |
|------------------|---------------|--------|
| `key_compromise` | 冻结该证书签名的所有模块 | 拒绝 |
| `device_lost` | 继续运行（非安全事件） | 拒绝 |
| `admin_action` | 按 admin 指定策略 | 按策略 |
| `server_ca_compromise` | `paused_security` 立即 | 拒绝（epoch bump） |
| `code_signing_verifier_bug` | `paused_security` 立即 | 拒绝 |

吊销结果写入 TickTrace。Replay 使用记录事件，不重新评估吊销。

### 8.4 Security Epoch Bump 确定性

Security epoch bump 按 D5 裁决的分级状态机执行。Replay 时：

- 使用记录的 bump 事件而非重新触发
- 模块安全状态变更从 TickTrace 重放，不重新计算
- Bump 时间戳使用记录值，不使用 wall clock
