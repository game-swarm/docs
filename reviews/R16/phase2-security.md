# R16 Phase 2 CrossCheck — Security 补充验证

输入说明：当前 `/data/swarm/docs` HEAD 已清理 `reviews/R16/rev-*.md`，本次补充阅读从上一提交 `8c02b92` 中读取 R16 review 原文，并对当前 `design/`、`specs/`、`specs/reference/` 文档进行核查。

结论摘要：Security 相关 CrossCheck 未闭合。核心问题不是“缺少一句说明”，而是安全不变量仍分散在 `api-registry.md`、`auth.md`、`03-mcp-security.md`、`09-command-source.md`、`04-wasm-sandbox.md` 与 `interface.md`，且至少 WebSocket、deploy nonce、sandbox OS baseline 三处存在直接冲突。建议维持 R16 Speaker 的 REQUEST_MAJOR_CHANGES / B6 blocker。

---

## CrossCheck item -> Finding -> disposition

### 1. API Registry 是否必须合并 `required_scope` / `replay_class` / `subject_source` / `visibility_filter`

Finding:
- 必须合并，而且应作为 per-method / per-tool 的机器可读字段进入 `specs/reference/api-registry.md`。
- 当前 API Registry 自称“所有 API 合约单一权威源”，但 MCP Tools 表只有 `Input Schema`、`Output Schema`、`Rate Limit`，Capability Profiles 也只给 profile 级分组；没有逐工具 `required_scope`、`replay_class`、`subject_source`、`visibility_filter`、`admin_override`。
- `design/auth.md §5.6b` 有一个 5 行示例授权矩阵，字段正是 `Replay Class / Required Scope / Rate Limit / Visibility Filter / Admin Override`，但它又说“完整矩阵见 interface.md”。`design/interface.md` 仍保留旧工具名与旧分类表，和 API Registry 的 46 工具不一致，不能作为完整矩阵。
- `specs/security/03-mcp-security.md` 已将 MCP authz 指向 API Registry §3.2，但 Registry 只有 profile，没有 scope 细分；这会导致 `debug`、`deploy`、`admin`、`simulate/dry_run` 的最小权限无法由 CI/codegen 强制。
- 安全影响：典型 mass-assignment / confused-deputy 风险。实现者若只按 profile 粗放授权，`swarm_get_tick_trace`、`swarm_get_engine_stats`、`swarm_get_replay`、admin tools 等会成为越权信息泄露或状态变更入口。

Disposition: blocker

建议闭合条件：
- API Registry 工具表扩展为：`tool_name, input_schema, output_schema, required_scope, capability_profile, replay_class, subject_source, visibility_filter, rate_limit, idempotency/replay_guard, admin_override, audit_class`。
- `auth.md`、`03-mcp-security.md`、`05-visibility.md`、`09-command-source.md` 只引用 Registry，不再维护可冲突的安全矩阵。
- CI 校验：每个 MCP/REST/WS 方法必须有上述字段；`admin/debug/deploy/simulate/replay` 缺字段即失败。

---

### 2. Agent WebSocket 是否必须 per-message seq + signature；`auth.md` 的“握手后免签”是否应删除

Finding:
- 必须 per-message seq + MAC/Ed25519 signature；`design/auth.md §10.5a` 的“建立认证 WebSocket → 后续消息免签名（会话内信任）”应删除或改为仅适用于只读 browser/spectator WS。
- 当前 `specs/security/03-mcp-security.md §2.5` 已给出正确方向：Authenticated Agent WS 会话建立后，每条消息必须携带递增 `seq` 与 `mac`，签名覆盖 `SWARM-WS-MSG-V1\n<seq>\n<body_hash>`；服务端回复也必须有独立 seq + 服务端签名。
- 但 `design/auth.md §10.5a` 仍明确写“后续消息免签名（会话内信任）”，并说会话内消息不计入 per-tick rate limit。该表述会把握手认证降级为 bearer session：连接内注入、代理混淆、重放、消息重排、跨请求审计归因都会变弱。
- Browser/spectator WS 可采用只读订阅、无 per-message 签名，但必须明确禁止写操作、认证消息和 agent command 通道复用。

Disposition: blocker

建议闭合条件：
- 删除 `auth.md §10.5a` 中“后续消息免签名（会话内信任）”。
- 统一为两条路径：
  1. Authenticated Agent WS: handshake + 每消息 seq + 签名/MAC + rate limit + audit。
  2. Browser/Spectator WS: 只读 delta stream，无写方法，无 agent command，按 spectator delay/privacy 过滤。
- Gateway protocol 禁止仅凭 `Sec-WebSocket-Protocol: swarm-cert.<cert_id>` 建立认证 agent 写通道；必须完成 canonical WS handshake 并进入 per-message 验签状态机。

---

### 3. Deploy nonce: Dragonfly nonce vs FDB `version_counter`

Finding:
- `swarm_deploy` 应以 FDB per-player/per-slot `version_counter` 为唯一防重放权威；不应归入 Dragonfly nonce 的 `idempotent_mutation` 示例。
- 当前 `specs/security/09-command-source.md` 与 `design/auth.md §10.8` 均已写明 Deploy 不使用 nonce，防重放由 FDB `version_counter` 保证。
- 但 `design/auth.md §5.6a` 仍在 `idempotent_mutation` 示例中列出 `swarm_deploy`，Nonce 策略为 Dragonfly nonce + time window。该冲突会导致实现者选择 Dragonfly SETNX TTL，形成 cache crash 后 TTL 窗口内可重放部署的风险。
- `specs/DEFERRED.md` 仍记录 Dragonfly nonce 崩溃窗口讨论，需确保它不再覆盖 deploy 路径。

Disposition: blocker

建议闭合条件：
- `auth.md §5.6a` 删除 `swarm_deploy` 作为 Dragonfly nonce 示例，改列 `swarm_deploy` 为 `deploy_versioned_mutation` 或 `idempotent_by_fdb_version`。
- API Registry 增加 `replay_guard=FDB_version_counter(player_id, slot)` 字段。
- CI 禁止 deploy 方法被标注为 `Dragonfly nonce`。

---

### 4. Admin source / capability / rate limit / 双签 / audit 是否冲突

Finding:
- 当前不是完全冲突，而是“保护散落且 Registry 不可执行”。`auth.md` 中有 FDB admin nonce counter、admin recovery 双人授权、audit log；API Registry 中只有一个粗粒度 `admin` profile 和 6 个 Admin tools；没有拆分 AdminRead / AdminConfig / AdminRollback / AdminSecurityAction，也没有逐工具双签、cooldown、idempotency、audit schema。
- `swarm_admin_challenge` 在 Registry 中 rate limit 为 5/min，Admin 通用 rate limit 又是 10/h，`swarm_admin_get_audit_log` 为 30/tick；这些可能合理，但没有 source/capability/audit class 字段说明为什么读 audit 与写 config/rollback/ban 使用不同限流语义。
- `design/auth.md §11.3` 对 `swarm_admin_create_password_reset` 要求双 admin + 用户 out-of-band 验证，但 Registry 表只写 `{challenge, signature}` / `{granted, scope, expiry}` 风格的 admin challenge，无法表达“发起/确认/过期/审计”的两阶段状态机。
- 安全影响：Admin 是最高权限面。若实现只按 `admin` profile 放行，会出现 rollback/config/ban/recovery/audit read 混用同一 capability 的过宽授权；若实现按 `auth.md` 写，又和 Registry/codegen 不一致。

Disposition: high

建议闭合条件：
- API Registry 增加 Admin capability 分级：`AdminRead`、`AdminConfig`、`AdminRollback`、`AdminSecurityAction`、`AdminRecovery`。
- 每个 Admin tool 声明：`required_admin_capability`、`dual_control_required`、`idempotency_key_required`、`challenge_source=FDB_CAS`、`rate_limit`、`cooldown`、`audit_schema`、`redaction_policy`。
- `swarm_admin_create_password_reset` 必须是两阶段状态机：initiate + confirm，不返回 reset URL，audit 记录双 admin id 与 target id，禁止 admin 指定用户私钥/密码。

---

### 5. Sandbox OS net namespace / clone / `pids.max` / seccomp 是否有唯一生产基线

Finding:
- 当前没有唯一生产基线，存在直接冲突。
- `specs/core/04-wasm-sandbox.md §4.1` 允许 `clone (仅 CLONE_VM | CLONE_VFORK)`，`§4.2` 写 `pids.max = 32`，`§4.3` 写“sandbox 进程无网络命名空间”。
- 同一文件 `§9.1-§9.3` 又写 `fork/vfork/clone` 全禁、`pids.max = 16`、独立 `pid/net/mnt/ipc/uts` namespace，网络 namespace 内 socket 应失败。
- 这不是小数字不一致：它决定 Wasmtime worker 是否可创建线程/进程、是否有独立 net namespace、CI 如何验证、seccomp profile 如何部署。实现者按 §4 或 §9 会得到不同安全边界。

Disposition: blocker

建议闭合条件：
- 选定一个生产基线并删除另一套描述。安全侧建议生产基线为：
  - WASI filesystem/network/clock/random/env/process/threads 全禁。
  - 独立 `pid/net/mnt/ipc/uts` namespace；net namespace 无外部接口；seccomp 禁止 `socket/connect/sendmsg/recvmsg`。
  - seccomp 默认禁止 `fork/vfork/clone/clone3/execve`；若 Wasmtime 运行时必须创建线程，必须单独列出允许的 clone flags、创建时机、pids.max、CI 断言与威胁分析，不能同时写“clone 全禁”。
  - `pids.max` 选择单一值（建议 16，除非实际 Wasmtime worker 证明需要 32），并和 cgroup 验证命令一致。
- CI `sandbox_boundary` 必须覆盖：clone/fork/socket/open/getrandom/clock_gettime 失败、cgroup pids/memory/cpu 生效、net namespace 无接口、worker reset 后无跨玩家残留。

---

### 6. Dependency SLA 是否需覆盖 rmcp / Bevy / crypto / serde / db clients

Finding:
- 需要覆盖。当前 `specs/security/CVE-SLA.md` 是 Wasmtime CVE SLA，监控源和测试流程都围绕 Wasmtime/sandbox；没有覆盖 rmcp、Bevy、crypto/auth crates、serde/serde_json、compression、FoundationDB/Dragonfly/NATS/ClickHouse clients、TLS/HTTP/WebSocket/gRPC 依赖。
- `specs/core/04-wasm-sandbox.md` 只把 `wasmparser_version` 放入模块缓存 key，但 SLA 未覆盖 wasmparser。R16 review 已多次指出 rmcp/Bevy/wasmparser/serde/db clients 都在攻击面上：MCP/WS 解析、ECS 调度、canonical serialization、数据库客户端反序列化与连接池都可能导致 RCE/DoS/越权。

Disposition: high

建议闭合条件：
- 将 `CVE-SLA.md` 改为 `Dependency Security SLA`，按 Tier 分级：
  - Tier 0: Wasmtime/wasmparser、crypto/auth、canonical codec/hash、serde_json 或等价解析器、TLS/HTTP/WS stack、FDB client。
  - Tier 1: rmcp/MCP stack、Bevy ECS、Dragonfly/NATS/ClickHouse clients、compression、object-store SDK。
  - Tier 2: SDK/tooling/test-only dependencies。
- 每个 Tier 定义 Critical/High 响应时间、临时缓解、回滚策略、CI audit 命令、SBOM/lockfile policy、禁用 feature policy。
- Security epoch bump / module cache key 应记录受影响依赖版本，尤其 Wasmtime + wasmparser + validation_policy + target_arch。

---

### 7. Replay / spectator / hint ladder / public privacy 边界

Finding:
- 现有文档有较好的局部约束，但仍需要并入 Registry 的 `visibility_filter` 和 `privacy_class` 字段。
- `specs/security/05-visibility.md` 明确 `public_spectate=true` 时 spectator 可看延迟全图，但受 `spectate_delay` 与 `replay_privacy` 过滤；`specs/core/09-snapshot-contract.md` 定义 Safe Hint Ladder。
- 但 API Registry 的 `swarm_get_replay`、`swarm_get_tick_trace`、`swarm_get_engine_stats`、`swarm_simulate`、`swarm_dry_run` 没有声明输出 privacy class、hint level 上限、是否允许 competitive world 提升 debug detail。
- `specs/core/09-snapshot-contract.md §5.3` 写 `swarm_dry_run` 可传入 `hint_level` 覆盖世界默认值（仅限训练模式提升，不允许降级）措辞有歧义：在 competitive world 中绝不能由客户端把 hint 提升到 FullDebug。

Disposition: medium

建议闭合条件：
- Registry 为 replay/debug/simulate/dry_run 增加 `privacy_class`、`hint_level_max`、`competitive_allowed`、`redaction_policy`。
- 明确 competitive world 中客户端不能提升 hint level；training/full debug 只能在非竞技世界或 owner-only dev environment 使用。

---

### 8. `world_seed` / `seed_epoch` / `player_order` 可见性

Finding:
- `specs/core/01-tick-protocol.md` 已有 world_seed 泄露威胁模型，承认 world_seed 是服主级秘密；TickTrace 记录 seed epoch 与活跃玩家集以支持 replay。
- 但 API Registry 没有声明哪些 debug/replay/admin 方法可以返回 `seed_epoch`、`player_order`、shuffle seed 或相关派生信息。Determinism review 的担忧成立：如果 debug/MCP/API 在当前 tick 或未来 tick 暴露 player_order/seed 相关信息，会破坏公平性。

Disposition: medium

建议闭合条件：
- Registry 为 `swarm_get_tick_trace`、`swarm_get_replay`、admin audit/replay verifier 定义 seed 字段 redaction：普通玩家和 spectator 不返回 `world_seed` / future seed / future player_order；历史 replay 只在延迟窗口和权限满足后返回最小验证材料。
- Admin/security audit 可访问完整材料，但必须 audit，且不可通过 public replay 输出。

---

### 9. CRL 缓存窗口对 deploy 路径

Finding:
- `design/auth.md §10.8` 仍写 CRL 允许延迟 60s，competitive world 可配置为 5-10s；`09-command-source.md` 要求部署提交时证书未过期、未吊销。
- 对 deploy 来说，吊销后 60s 仍可部署恶意 WASM 的窗口偏大；如果 CRL LRU 不是事件驱动失效，而是定时轮询，实际窗口可能更长。

Disposition: high

建议闭合条件：
- 对 `swarm_deploy` / code-signing path 采用更严格策略：CRL 事件驱动失效；deploy 热路径若 CRL cache age 超过阈值则强制查 FDB 或拒绝。
- competitive world 默认 CRL TTL 不应高于 10s；高价值 code-signing 可要求 0-stale 或 short-stale + audit。

---

### 10. Snapshot 截断 / 实体密度 DoS

Finding:
- `specs/core/09-snapshot-contract.md` 关注截断公平性，但实体堆叠导致 snapshot 构造排序/序列化 CPU 放大仍是 DoS 面。
- `rev-dsv4-performance` 指出敌对方可通过堆叠实体增加受害方 snapshot 压力；当前 security 文档没有明确每玩家 snapshot CPU budget、per-room/entity density cap 或 abuse detection。

Disposition: medium

建议闭合条件：
- Registry / limits manifest 加入 snapshot build CPU budget、per-player/per-room fair-share、truncation before expensive serialization 的要求。
- metrics 区分 `snapshot_truncated`、`snapshot_cpu_budget_exhausted`、`visibility_filter_budget_exhausted`，并触发 abuse audit。

---

## 最小闭合清单

1. API Registry 成为唯一安全合同源，新增逐工具安全字段并由 CI 校验。
2. 删除 `auth.md` 中 Agent WS “握手后免签”语句；Authenticated Agent WS 必须 per-message seq + signature。
3. `swarm_deploy` 防重放唯一采用 FDB `version_counter`；删除 Dragonfly nonce 示例冲突。
4. Admin tools 拆 capability + dual-control + FDB challenge + audit schema，并进入 Registry。
5. Sandbox OS baseline 只保留一套生产规范，消除 clone / pids.max / net namespace 冲突。
6. Wasmtime CVE SLA 扩展为 Dependency Security SLA，覆盖 rmcp、Bevy、wasmparser、crypto/auth、serde/canonical codec、db/cache/messaging clients。
