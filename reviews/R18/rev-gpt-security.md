# R18 Security Review (GPT-5.5)

## 1. Verdict

REQUEST_MAJOR_CHANGES

本轮结论：YAML → api-registry.md 的“生成式单源”在基础计数和活跃 MCP tool 名称上已经闭合；我用脚本交叉验证了 `CommandAction=19`、active MCP tools `46/46`、Host Functions `5`，且 YAML 与 Markdown 活跃工具名集合无差集。

但从安全合同角度，闭合还没有完成：多个安全关键语义仍散落在 `design/auth.md`、`specs/security/03-mcp-security.md`、`specs/security/05-visibility.md`、`specs/security/09-command-source.md` 中，且与 YAML/API Registry 存在冲突。若实现/代码生成以 YAML 为唯一机器事实源，这些漂移会直接影响 replay 防护、认证授权矩阵、WebSocket 消息完整性、可见性 oracle 和部署 DoS 边界。

## 2. 发现问题

### High — H1. Auth/CSR/Recovery 安全关键 MCP 工具未进入 YAML/API Registry 单源

证据：
- `design/auth.md` §10.1 定义了大量认证工具：`swarm_register_challenge`、`swarm_submit_csr`、`swarm_renew_certificate`、`swarm_get_server_trust`、`swarm_auth_revoke`、`swarm_list_certificates`、`swarm_revoke_certificate`、`swarm_change_password`、`swarm_request_password_reset`、`swarm_admin_create_password_reset`、`swarm_confirm_password_reset`、`swarm_register_passkey`、`swarm_recover_with_passkey`、`swarm_bind_email`、`swarm_delete_account`、`swarm_restore_account`、`swarm_cancel_account_deletion`、`swarm_federated_login`。
- `game_api.idl.yaml` 的 Auth category 只有 `swarm_auth_login` 与 `swarm_auth_refresh`，active tool 总数 46。
- `api-registry.md` 也只生成这 2 个 Auth 工具。

风险：
这些工具是账号创建、CSR、证书续签/吊销、恢复链接、passkey、账号删除/恢复、联邦登录的核心 attack surface。若它们不在唯一机器源中，CI/codegen 无法强制 `required_scope`、`replay_class`、`rate_limit_key`、`visibility_filter`、admin 双签、nonce/idempotency 等安全列；实现者可能从 prose 手写路由，形成 mass-assignment、权限漏标、replay class 漏标和恢复链路枚举面。

要求：
把 auth.md §10.1 的所有实际 MCP/API 方法纳入 `game_api.idl.yaml`，并生成到 `api-registry.md`；每个方法必须有完整 security columns，尤其是 CSR/recovery/admin/federation 的 replay class、scope、rate limit、rate-limit key、admin override/dual-audit 语义。

### High — H2. `swarm_deploy` replay class 在 YAML/API Registry 中仍标成 `idempotent_mutation`，与 auth/command-source 的 `deploy_mutation` 安全语义冲突

证据：
- `design/auth.md` §5.6a 明确区分 `deploy_mutation`：部署防重放由 FDB `version_counter` 保证；`Dragonfly nonce` 不适用于 deploy。
- `design/auth.md` §10.8 也明确 “Deploy 不使用 nonce——防重放由 version_counter 保证”。
- `specs/security/09-command-source.md` §7.3 定义 Deploy 使用 per-player/per-slot 单调递增 `version_counter`。
- 但 `game_api.idl.yaml` 中 `swarm_deploy` 的 `replay_class: idempotent_mutation`；生成的 `api-registry.md` 同样显示 `idempotent_mutation`。

风险：
这不是命名小问题。若网关/SDK/CI 以 YAML 生成 replay 处理逻辑，`idempotent_mutation` 可能被映射到 Dragonfly nonce + time window 或“重复执行结果相同”的通用语义；deploy 实际需要 FDB version counter 的严格全序和崩溃后不可重放。错误 replay class 会让 WASM 部署出现旧模块重放、跨 slot 重放、异步 object-store 状态与 FDB manifest 不一致等安全风险。

要求：
把 `deploy_mutation` 加入 YAML replay_class 枚举，并将 `swarm_deploy` 标为 `deploy_mutation`；生成文档中也必须体现该 class，而不是仅在 notes 里补充 fdb_version_counter。

### High — H3. WebSocket 安全语义自相矛盾：auth.md 允许握手后免签，03/YAML 要求每消息 seq+MAC

证据：
- `design/auth.md` §10.5a 写明 WebSocket 证书握手完成后 “后续消息免签名（会话内信任）”。
- `specs/security/03-mcp-security.md` §2.5 要求已认证 Agent WS 会话中每条消息携带递增 `seq` + Ed25519 MAC/signature。
- `game_api.idl.yaml` `websocket_security.agent_ws` 同样写明 per-message seq + MAC，seq 回退或 MAC mismatch 断连。

风险：
WebSocket 是高频 agent 控制/查询通道。若实现者按 auth.md 的“握手后免签”实现，连接劫持、代理注入、会话内重放/重排、跨消息 body 替换都只剩传输层保护；而设计又明确支持不安全 HTTP/显式 pinning 场景，不能假设传输层永远可信。这是典型“握手认证但消息未绑定”的已知漏洞模式。

要求：
删除 auth.md 中“后续消息免签名”语义，统一为 per-message `seq == last_seq + 1` + body hash + Ed25519 signature/MAC；或者若要保留免签，必须把 YAML/API Registry 和 03 一并改为同一安全模型并给出抗重放证明。当前不能两者并存。

### High — H4. `specs/security/03-mcp-security.md` 仍列出不在 YAML/API Registry 的旧工具与旧 deploy schema

证据：
- 03 §4.1 表列出 `swarm_rollback`、`swarm_list_modules`，但 YAML/API Registry active tools 中没有这些工具；YAML 中对应的是 `swarm_get_deploy_status`、`swarm_list_deployments` 等。
- 03 §4.2/4.3/4.4 列出 `swarm_get_objects_in_range`、`swarm_explain_last_tick`、`swarm_inspect_entity`、`swarm_inspect_room`、`swarm_profile`、`swarm_get_schema`、`swarm_get_docs`、`swarm_get_available_actions` 等，也未进入 YAML active tools。
- 03 §4.1 的 `swarm_deploy` 示例仍是 `{wasm_bytes, language, version_tag, room_id}` → `{module_id,status,deployed_at}`，与 YAML/API Registry 的 `{player_id, drone_id, wasm_bytes, metadata}` → `{deploy_id, accepted, validation_errors, fdb_version_counter, object_store_key}` 不一致。

风险：
03 是 MCP security spec，若它继续保留旧工具名/旧 schema，会使实现者绕开 YAML 生成事实源，或误以为这些旧工具仍是支持面。尤其 `swarm_rollback`、`swarm_explain_last_tick`、`swarm_get_docs` 这类接口天然是高权限或高 DoS/信息泄露风险，如果不存在于 registry，就没有统一 rate limit、scope、visibility filter 和 audit schema。

要求：
03 中的工具清单必须完全引用/生成自 YAML/API Registry，不得手写冲突列表。不存在于 YAML 的工具要么加入 YAML 并生成，要么从 03 删除并改成“历史/非当前接口”。

### Medium — M1. 可见性 oracle 修正没有回流到 YAML/API Registry：`omitted_count` 仍是精确 u32

证据：
- `specs/security/05-visibility.md` §10.2 识别 `omitted_count` 精确数量会形成 oracle，并要求改为分桶：`few/some/many/extreme`。
- 但 `game_api.idl.yaml` 的 `swarm_get_snapshot` output schema 仍为 `omitted_count: u32`。
- `api-registry.md` 也生成 `{tick, entities, terrain, resources, truncated, omitted_count}`，没有分桶类型或 `total_visible_count` 分桶语义。

风险：
在竞争世界中，攻击者可以通过构造接近 snapshot 截断边界的视野/实体密度，观察 `omitted_count` 的精确变化，推断隐藏实体数量或敌方活动强度。这是低带宽但稳定的信息 oracle。

要求：
将 YAML 中 `omitted_count` 类型改为 bucket enum，例如 `OmittedCountBucket = 0 | few | some | many | extreme`，并生成到 API Registry/SDK；若保留数值，仅允许代表“可见且已过滤后的自身可知范围”，不能包含隐藏实体计数。

### Medium — M2. WASM/blob size 边界冲突：5 MB 上传/校验 vs 64 MB object-store wasm_module

证据：
- `specs/core/04-wasm-sandbox.md` §2.4 与 §6 规定 WASM 模块体积最大 5 MB。
- `specs/security/03-mcp-security.md` §5.3 规定 HTTP `max body size = 5 MB`，并称与 WASM 模块体积一致。
- 但 `game_api.idl.yaml` persistence `blob_types.wasm_module.max_size: 64 MB`；生成的 `api-registry.md` §11 也写 `wasm_module | 64 MB`。

风险：
入口限流、对象存储、编译预算、缓存、sandbox validation 之间的最大体积不一致，会导致最小请求制造最大后端开销：例如网关允许/对象存储接受 64 MB blob，后续编译/validation 才拒绝；或 registry/SDK 告诉客户端 64 MB，HTTP 层却 5 MB 拒绝。对 deploy path 是典型 DoS 与状态漂移风险。

要求：
在 YAML 中将 active `wasm_module` deploy 上限与 sandbox/gateway 对齐为同一值；若确实需要 64 MB，必须同步提高 gateway max body、编译预算、object-store backpressure、validation timeout，并重新评估 DoS。

### Medium — M3. Replay class 词汇表仍未统一，YAML 出现 `non_replayable`，auth.md 词汇表使用 `non_idempotent_mutation`

证据：
- `design/auth.md` §5.6a 定义 replay classes：`read_replay_safe`、`idempotent_mutation`、`deploy_mutation`、`non_idempotent_mutation`、`admin_critical`。
- `game_api.idl.yaml` active tools 中实际 classes 为：`read_replay_safe`、`idempotent_mutation`、`admin_critical`、`non_replayable`。

风险：
如果 codegen/CI 按字符串匹配策略生成 nonce/idempotency 逻辑，`non_replayable` 可能没有处理器或落到默认分支。认证类 `swarm_auth_login` / `swarm_auth_refresh` 使用该值，正好位于 token/session 旋转路径，错误默认处理会影响重放窗口和 refresh token rotation。

要求：
把 replay class 做成 YAML 中的显式 enum，并让所有文档只引用该 enum。若需要 `non_replayable`，在 auth.md 表中正式定义其 nonce/challenge/事务语义；否则改为 `non_idempotent_mutation` 或更具体的 auth/session class。

### Medium — M4. Wasmtime 版本锁定写法与 CVE-SLA 的“精确锁定”目标不够闭合

证据：
- `specs/core/04-wasm-sandbox.md` 写 `wasmtime = "=30.0"`，并称锁定版本、不自动升级。
- `specs/security/CVE-SLA.md` 要求关键依赖显式锁定到精确版本 `=X.Y.Z`。

风险：
安全响应要求精确补丁级别；Wasmtime/Cranelift 的安全修复通常按 patch release 发布。文档写 `=30.0` 容易造成实现者不明确是否锁到 `30.0.0`，也不利于 CVE 记录模板中的 “当前版本/目标版本” 精确追踪。

要求：
示例改成明确 patch 版本（如 `=30.0.0` 或当前支持窗口内的具体版本），并在 TickTrace/编译缓存键中记录 wasmtime build commit 或完整 crate version。

### Informational — I1. 基础 YAML→Markdown 机械闭合已有明显进展

验证结果：
- YAML active MCP tools: 46，unique 46。
- Markdown active MCP tools: 46，unique 46。
- YAML `total_tools: 46` 与 Markdown “工具清单 (46)” 一致。
- YAML 与 Markdown active tool name 差集为空。
- CommandAction 实际 19 个，与 `total_variants: 19` 一致。
- Host Functions 实际 5 个，与 registry claim 一致。

说明：
这说明 R15-R17 后的生成式单源在“列表/计数”层面已基本有效；当前阻塞不在机械生成，而在安全语义没有全部进入 YAML 结构化字段。

## 3. 亮点

- 应用层证书模型整体方向正确：用途隔离证书、CSR、公私钥不出客户端、Server Root CA 不进入系统 trust store、Intermediate CA HSM/KMS 要求、CRL/epoch bump 都覆盖了核心威胁。
- Auth 热路径已经识别 argon2id DoS：per-IP 限流先于 argon2，worker/semaphore 限并发，这比常见“dummy hash 防枚举但引入 DoS”设计更成熟。
- WASM sandbox 基线有多层防护：Wasmtime fuel、epoch interruption、WASI 禁用、host function 白名单、seccomp、cgroup、namespace、恶意样本 CI、TickTrace 字段截断，覆盖了常见 sandbox escape/DoS 面。
- 可见性文档明确提出单一 `is_visible_to` 函数与跨输出面缓存，且识别了 `omitted_count` oracle；方向正确，只是尚未回流到 YAML。
- CVE-SLA 覆盖 Wasmtime 之外的关键 Rust crates（crypto/TLS/async/serde/wasmparser/cranelift），且明确禁止为赶 SLA 放宽 sandbox 约束，这是好的安全运营边界。

## 4. CrossCheck

### 单源闭合检查

脚本检查（只读取任务允许文件）：

```text
yaml active tool count 46 unique 46
md active tool count 46 unique 46
yaml total_tools 46
md active tool claims 46
diff yaml-md [] []
command total actual 19
host funcs count 5
```

结论：
- YAML ↔ generated Markdown 在 active MCP tool 名称和主要计数上闭合。
- 但“安全语义单源”未闭合：replay class、auth 工具矩阵、WS per-message signature、visibility truncation bucket、WASM size limit 仍与非生成文档冲突。

### Drift matrix

| 主题 | YAML/API Registry | 其它设计/安全文档 | 安全结论 |
|---|---|---|---|
| Auth tools | 仅 `swarm_auth_login` / `swarm_auth_refresh` | auth.md 定义 CSR/renew/revoke/reset/passkey/federation/delete 等大量工具 | High drift：安全关键端点未进入机器源 |
| Deploy replay | `idempotent_mutation` | auth.md / command-source 定义 `deploy_mutation` + FDB version_counter | High drift：replay 防护语义冲突 |
| WebSocket | YAML/03 要 per-message seq+MAC | auth.md 写握手后免签 | High drift：会话内消息完整性冲突 |
| MCP tool names | 46 active tools | 03 仍列旧工具名和旧 deploy schema | High drift：实现者会绕过 registry |
| Snapshot truncation | `omitted_count: u32` | visibility.md 要分桶，避免 oracle | Medium drift：信息泄露修正未回流 |
| WASM size | object-store wasm_module 64 MB | sandbox/gateway 5 MB | Medium drift：DoS 边界不一致 |
| Replay vocabulary | `non_replayable` | auth.md class table 无此项 | Medium drift：codegen 默认分支风险 |

### 建议的 R18 出口标准

R18 不应只验证 Markdown 是否由 YAML 生成；还应要求以下 CI/生成检查成为硬门禁：

1. YAML `mcp_tools.tools[*]` 是唯一工具列表；安全规格不得手写工具表，只能引用或生成。
2. `replay_class`、`visibility_filter`、`required_scope`、`rate_limit_key` 必须是 YAML enum，未知值 CI fail。
3. 所有 `design/auth.md` 暴露的 MCP/Auth 方法必须在 YAML 注册；反向也成立。
4. `api-registry.md` 中禁止出现 YAML 不存在的 tool name、schema field、limit number。
5. 对 `swarm_deploy` 单独断言：`replay_class == deploy_mutation`，输出包含 `fdb_version_counter`，且不使用 Dragonfly nonce 作为 replay 权威。
6. 对 visibility schema 单独断言：`omitted_count` 不得是精确隐藏实体数量，必须是 bucket enum 或删除。
7. 对 deploy size 单独断言：gateway max body、sandbox validation max、persistence wasm_module max 三者一致或有明确分层说明。
