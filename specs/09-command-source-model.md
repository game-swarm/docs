1|# Command Source Model — 指令来源模型
2|
3|> **状态**: 当前 | **日期**: 2026-06-14
4|
5|> **目标**: 所有指令来源显式建模，不可伪造 auth context
6|
7|## 1. 原则
8|
9|**默认 gameplay 指令只来自 WASM。所有来源的 actor/capability/scope 由服务端注入，客户端不可自报。**
10|
11|## 2. 指令来源
12|
13|### 2.1 来源矩阵
14|
15|| Source | 描述 | auth_context | gameplay | audit | rate_limit | visibility | budget |
16||--------|------|-------------|----------|-------|------------|------------|--------|
17|| `WASM` | drone tick() 输出 | player_id (server-injected) | ✅ 是 | 完整 | fuel budget | 快照范围 | 10M fuel/tick |
18|| `MCP_Deploy` | AI 部署 WASM 代码 | player_id + token scope | ❌ 否 | 完整 | 10/h | N/A | N/A |
19|| `MCP_Query` | AI 查询世界/调试 | player_id + token scope | ❌ 否 | 完整 | 50/tick | 快照范围 | N/A |
20|| `Admin` | 管理操作 | admin_id + token scope | ❌ 否 | 完整 | 无限制 | 全局 | N/A |
21|| `Replay` | 回放重放 | system (no player) | ❌ 否 | 完整 | N/A | 回放历史 | N/A |
22|| `TestHarness` | 自动化测试 | test_context | ❌ 否 | 完整 | N/A | 测试世界 | N/A |
23|| `Tutorial` | 教程引导 | tutorial_session + world_id | ⚠️ 仅教程世界 | 完整 | 10/tick | 教程房间 | N/A |
24|
25|### 2.2 扩展来源（已实现）
26|
27|| Source | 描述 | auth_context | gameplay | audit | rate_limit | visibility | budget |
28||--------|------|-------------|----------|-------|------------|------------|--------|
29|| `Deploy` | 代码部署管线（非 MCP 入口） | player_id | ❌ 否 | 完整 | 1/tick | 玩家快照 | compile budget |
30|| `Rollback` | 管理回滚操作 | admin_id + rollback_token | ❌ 否 | **双人审计** — 需两个不同 admin 的 Ed25519 签名，服务端在 Source Gate 前强制执行 | 手动触发 | 历史状态 | N/A |
31|| `RuleMod` | Rhai 规则模组 actions | mod_id + world_owner_id | ⚠️ damage/effect/attribute/event/resource/custom handler（经能力白名单） | 完整 | 100 actions/tick | 规则作用域 | Rhai op budget |
32|| `Simulate` | `swarm_simulate` 试运行 | player_id + snapshot_id | ❌ 否（snapshot-bound dry-run） | 完整 | 5/tick | 快照副本 | 0.5× MAX_FUEL |
33|| `DryRun` | 部署前语法/校验试运行 | player_id | ❌ 否 | 完整 | 20/h | 无（仅编译） | compile budget |
34|| `Tutorial` | 教程引导（扩展） | tutorial_session + world_id | ⚠️ 仅教程世界 | 完整 | 10/tick | 教程房间 | tutorial budget |
35|
36|### 2.3 来源能力约束
37|
38|| Source | 允许写入世界 | 允许读写全局存储 | 允许部署代码 | 允许查询世界 | 允许触发战斗 |
39||--------|------------|----------------|------------|------------|------------|
40|| `WASM` | ✅ | ✅ | ❌ | ✅（快照） | ✅（含六种特殊攻击：Hack/Drain/Overload/Debilitate/Disrupt/Fortify） |
41|| `MCP_Deploy` | ❌ | ❌ | ✅ | ❌ | ❌ |
42|| `MCP_Query` | ❌ | ❌ | ❌ | ✅ | ❌ |
43|| `Admin` | ✅ | ✅ | ✅ | ✅ | ✅ |
44|| `Replay` | ❌（只读） | ❌（只读） | ❌ | ✅（回放范围） | ❌（只读） |
45|| `TestHarness` | ✅ | ✅ | ✅ | ✅ | ✅ |
46|| `Tutorial` | ⚠️ 教程世界隔离 | ❌（独立 namespace） | ❌ | ⚠️ 教程房间 | ❌（无敌方） |
47|| `RuleMod` | ⚠️ damage_entity/set_entity_flag/deduct_resource/award_resource/emit_event/custom handler（经能力白名单校验） | ❌ | ❌ | ❌ | ❌ |
48|| `Simulate` | ❌（snapshot copy） | ❌（snapshot copy） | ❌ | ✅（副本） | ⚠️ dry-run |
49|| `DryRun` | ❌ | ❌ | ❌（仅编译） | ❌ | ❌ |
50|| `Rollback` | ✅（回滚写入） | ✅ | ✅ | ✅ | N/A（回滚状态） |
51|| `Deploy` | ❌ | ❌ | ✅ | ❌ | ❌ |
52|
53|> **Admin 路径统一**：Admin 命令走标准 `validate_and_apply()` 管线，仅 RejectionReason 阈值放宽（Admin 可操作任意玩家的实体，所有权检查放宽）。编译期通过 Rust trait 设计确保任何修改世界状态的代码无法绕过此路径——`WorldMutate` trait 的唯一实现者是 `validate_and_apply()`，任何试图直接持有 `&mut World` 的代码会产生编译错误。不存在 Admin 专用的独立代码路径。
54|
55|### 2.4 Tutorial 来源的隔离约束
56|
57|`Tutorial` 来源的指令**仅可在 `world.mode = "tutorial"` 的世界中接受**。在非 Tutorial 世界收到的 Tutorial 来源指令 → 静默丢弃 + 记录审计日志。Tutorial 世界的全局存储使用独立 namespace（`tutorial_{world_id}`），不与正式世界互通。
58|
59|## 3. 不可伪造的 Auth Context + 代码签名
60|
61|### 3.1 身份模型
62|
63|采用**服务端签发证书**模式：
64|
65|```
66|注册/登录:  OAuth2 (GitHub/Google) → 服务端验证身份 → 签发短期证书
67|代码签名:  WASM 部署附带证书签名 → 服务端验签
68|吊销:      证书过期（24h 默认）/ 手动吊销 → 凭据泄露可止损
69|```
70|
71|**为何不用客户端 keypair**：新手友好（不需要理解密钥管理）、吊销可控（ban 玩家 = 吊销证书）、OAuth2 已有成熟的认证基础设施。
72|
73|### 3.2 Auth Context
74|
75|每条 RawCommand 携带的服务端注入字段：
76|
77|```json
78|{
79|  "command": { /* 原始指令 */ },
80|  "auth": {
81|    "source": "WASM",
82|    "player_id": 42,                // 服务端注入——不可由客户端提供
83|    "cert_fingerprint": "sha256:abcd1234...",  // 部署时使用的证书指纹
84|    "session_id": "sess_abc",
85|    "module_hash": "blake3:def567...",         // WASM 模块内容哈希
86|    "tick_submitted": 4520,
87|    "tick_target": 4521
88|  }
89|}
90|```
91|
92|### 3.3 代码签名验证
93|
94|WASM 部署 (`swarm_deploy` / MCP_Deploy / Deploy) 时：
95|
96|1. 客户端发送 WASM 字节 + 证书（含服务端签名）
97|2. 服务端验证证书未过期、未被吊销
98|3. 服务端用证书中的 player_id 覆盖任何客户端自报的 ID
99|4. 服务端计算 `module_hash = Blake3(WASM bytes)`，写入 `auth.module_hash`
100|5. tick 执行阶段，引擎验证 `module_hash` 匹配已部署模块
101|
102|**禁止**：客户端在 Command body 中自报 `player_id`。如果客户端提供了 player_id，服务端用它自己的值覆盖。
103|
104|## 4. 校验管线
105|
106|```
107|RawCommand (携带 auth context)
108|    │
109|    ▼
110|┌─────────────────┐
111|│  Source Gate     │  ← 检查 source 是否允许提交 gameplay 指令
112|│  WASM → pass    │
113|│  MCP_Deploy →   │    ← 拒绝（MCP 不能提交 gameplay 指令）
114|│    reject 403   │
115|└────────┬────────┘
116|         │ pass
117|         ▼
118|┌─────────────────┐
119|│  Auth Verify     │  ← player_id 与 token 的 audience 绑定
120|└────────┬────────┘
121|         │
122|         ▼
123|   ──→ 进入 Command Validation Pipeline (specs/02-command-validation)
124|```
125|
126|## 5. Replay 与审计
127|
128|每条指令在 TickTrace 中记录完整 auth context。Replay 使用 `Replay` source，跳过 Source Gate 但保留完整 auth 信息。
129|
130|## 6. World/Arena 差异
131|
132|| Source | World | Arena |
133||--------|-------|-------|
134|| WASM | ✅ | ✅（赛前锁定版本） |
135|| MCP_Deploy | ✅ 随时 | ❌ 赛后不可 |
136|| MCP_Query | ✅ | ✅ |
137|| Deploy | ✅ 随时 | ❌ 赛后不可 |
138|| RuleMod | ✅（服主配置） | 赛前锁定 |
139|| Simulate | ✅（最多 5/tick） | ✅（最多 3/tick） |
140|| DryRun | ✅ | ✅ |
141|| Tutorial | ✅ 独立世界 | ❌ |
142|| Admin | ✅ | ✅（裁判权限） |
143|| Rollback | ✅ 双人审计 | ❌ |
144|| Replay | ✅ | ✅ 赛后自动公开 |
145|| TestHarness | ✅ | ✅ |
146|