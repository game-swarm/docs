# R35 Security 独立评审 — rev-dsv4-security

## 1. Verdict

**REQUEST_MAJOR_CHANGES**

存在 1 个 Critical 跨文档不一致（transport audience 标签集不统一）和 3 个 High 问题（WebSocket MAC payload 跨文档不一致、deploy 流程双文档描述矛盾、CSR 前期 email 明文传输），需要修复后方可进入实现阶段。整体安全架构设计扎实，但规范层面的精确性不足。

---

## 2. 发现的问题

### Critical

**S-C1: Transport audience 标签跨文档不一致 — 证书签发与验证脱节风险**

- **严重性**: Critical
- **位置**:
  - `specs/reference/api-registry.md` §9 Transport Labels — 仅含 `agent-mcp`, `cli-rest`, `wasm-sdk`
  - `design/auth.md` §10.8 Audience 字符串语法 — 含 `browser-http`, `browser-ws`, `agent-mcp`, `cli-rest`, `replay-viewer`
  - `specs/security/09-command-source.md` §7.0 Transport Audience — 含 `agent-mcp`, `browser-ws`, `cli-rest`, `replay-viewer`
  - `specs/security/03-mcp-security.md` §2.1/§2.2 — 使用 `swarm-aud-v1:browser-ws` 和 `swarm-aud-v1:cli-rest`
- **问题描述**: `browser-http` 仅出现在 auth.md §10.8，不出现在 api-registry.md、09-command-source.md、03-mcp-security.md 中。`browser-ws` 出现在 auth.md 和 09-command-source.md 但不出现在 api-registry.md。`wasm-sdk` 仅出现在 api-registry.md §9，不出现在 auth.md 的 audience 语法枚举中。api-registry.md 作为单一权威源，其 Transport Labels 集合与 Auth Service 签发的证书 audience 字段不匹配——Auth Service 按 auth.md 的 5-label 枚举签发证书，但 Gateway/Engine 按 api-registry.md 的 3-label 枚举验证，导致 `browser-http`/`browser-ws`/`replay-viewer` audience 的证书可能被拒绝，或 `wasm-sdk` audience 的证书在 Auth Service 侧无法签发。
- **影响**: 浏览器 WebSocket 连接 (`browser-ws` audience) 的证书握手可能因 Gateway 不识别该 transport label 而失败。`CodeSigningCertificate` 的 `wasm-sdk` audience 在 auth.md 的签发接口中无对应条目。
- **修复建议**:
  1. 在 api-registry.md §9 Transport Labels 中补全全部 6 个标签：`browser-http`, `browser-ws`, `agent-mcp`, `cli-rest`, `wasm-sdk`, `replay-viewer`（api-registry.md 是权威源，必须以它为准）。
  2. 在 auth.md §10.8 中补全 `wasm-sdk`。
  3. 在 09-command-source.md §7.0 中补全 `browser-http` 和 `wasm-sdk`。
  4. 在 03-mcp-security.md §2.1/§2.2 中明确使用完整的标签枚举而非内联硬编码。
  5. 在所有文档的 audience 示例中统一引用 api-registry.md §9 的权威枚举，禁止各文档自行定义可冲突的 transport label 集合。

---

### High

**S-H1: WebSocket per-message MAC payload 跨文档不一致 — tick 绑定缺失风险**

- **严重性**: High
- **位置**:
  - `design/auth.md` §10.5a — MAC payload 为 `SWARM-WS-MSG-V1\n<direction>\n<session_id>\n<seq>\n<tick>\n<body_hash>`（6 字段，含 tick 绑定）
  - `specs/reference/api-registry.md` §3.5 — "MAC 涵盖 `(seq, tick, payload)`"（3 字段，缺少 direction/session_id）
  - `specs/security/03-mcp-security.md` §2.5 — 仅描述 "per-message seq/MAC/signature"，未指定完整 payload 格式
- **问题描述**: auth.md 规定的 MAC payload 包含 6 个字段（含 `tick` 绑定用于防止跨 tick 消息重放），但 api-registry.md §3.5 仅列出 3 个字段，03-mcp-security.md 完全不指定 payload 格式。实现时若以 api-registry.md 为权威源实现 MAC 验证，可能遗漏 `direction`、`session_id`、`tick` 字段——其中 `tick` 缺失意味着无法防止跨 tick 重放攻击（攻击者可录制 tick N 的消息并在 tick N+1 重放）。
- **影响**: 若 Gateway/Engine 按 api-registry.md 的简化格式实现 MAC 验证，消息可在跨 tick 边界重放。`direction` 缺失可能导致同一条消息在 client→server 和 server→client 方向间重放。`session_id` 缺失可能导致跨会话重放。
- **修复建议**:
  1. 在 api-registry.md §3.5 中补全 MAC payload 为完整的 6 字段格式，与 auth.md §10.5a 对齐。
  2. 在 03-mcp-security.md §2.5 中显式引用 api-registry.md 或 auth.md 的 MAC payload 规范，而非仅文字描述。
  3. 明确定义 MAC 的 Ed25519 签名密钥来源（握手时绑定的用户私钥 vs 会话派生密钥）。

**S-H2: `swarm_deploy` 同步接收 wasm_bytes vs 异步 blob 上传 — 双文档流程矛盾**

- **严重性**: High
- **位置**:
  - `specs/reference/api-registry.md` §3.2 Deploy — `swarm_deploy` input schema 含 `wasm_bytes` 参数，暗示同步传输完整 WASM 二进制
  - `specs/core/05-persistence-contract.md` §2.3 Deploy 完整状态机 — "WASM blob 异步上传至 object store"，MANIFEST_COMMIT 不等 blob 上传完成
- **问题描述**: api-registry.md 的 `swarm_deploy` 将 `wasm_bytes` 作为 RPC 参数——这意味着客户端在单次 RPC 调用中同步传输完整 WASM 二进制。但 05-persistence-contract.md 的 deploy 状态机描述的是异步 blob 上传模型——MANIFEST_COMMIT 可以先于 blob 写入完成。如果 RPC 已同步接收到完整 wasm_bytes，则不存在"异步上传"——服务端已有完整字节，可在同一请求内完成 hash 计算和 manifest 提交。若设计意图是分离上传（客户端先上传 blob 到 object store，再提交 manifest），则 RPC schema 不应包含 `wasm_bytes` 而应是 `blob_hash + object_store_key`。当前两个模型矛盾。
- **影响**: 实现者无法确定 deploy 的正确流程——是同步 RPC（简单但大 blob 可能超时）还是异步两阶段（复杂但解耦）。API 合约与持久化合同不一致。
- **修复建议**:
  1. 明确 deploy 的唯一流程并统一两个文档。
  2. 若采用同步模型（推荐——简单且无 TOCTOU）：api-registry.md 保留 `wasm_bytes` 参数，05-persistence-contract.md §2.3 的 UPLOAD_PREPARE 阶段改为同步（计算 hash 后直接写入 FDB manifest，blob 写入对象存储为后台 best-effort 操作，失败标记 `upload_status = failed` 但不影响已 committed 的 manifest）。
  3. 若采用异步模型：api-registry.md 的 `swarm_deploy` 参数改为 `{blob_hash, object_store_key, metadata, signature}`，新增 `swarm_get_upload_url` 工具用于获取预签名上传 URL。

**S-H3: CSR 提交时 email 明文传输 — 未认证通道上的 PII 泄露**

- **严重性**: High
- **位置**: `design/auth.md` §10.3 `swarm_submit_csr` — 可选参数 `email`
- **问题描述**: `swarm_submit_csr` 接受可选的 `email` 参数用于注册时绑定邮箱。该请求在证书签发之前发送——此时客户端尚未持有应用层证书，无法建立加密通道（除非依赖外部 TLS）。若部署使用 HTTP 不安全传输（设计明确支持此场景，见 auth.md §5.7），email 将在明文 HTTP 中传输。虽然 auth.md §17.1 提到"敏感 payload 加密给服务器应用层证书 public key"，但 CSR 提交阶段客户端尚未获取服务器证书的 public key（`swarm_get_server_trust` 可获取 Root CA fingerprint，但不提供加密公钥）。
- **影响**: HTTP 部署场景下用户邮箱以明文传输，可被被动网络监听者截获。
- **修复建议**:
  1. CSR 提交阶段不直接接收 email。改为两步：证书签发成功后，通过已认证的 `swarm_bind_email` 工具绑定邮箱。
  2. 或：`swarm_submit_csr` 中 email 字段使用服务端公钥加密传输。在 `swarm_get_server_trust` 响应中增加 `encryption_public_key` 字段供客户端加密敏感字段。

---

### Medium

**S-M1: FDB challenge 存储缺少显式 TTL 清理机制 — 存储膨胀风险**

- **位置**: `design/auth.md` §9.3 — Challenge TTL 300s，"FDB 存储 TTL 自动清理"
- **问题描述**: FDB 不原生支持 TTL 自动过期。文档提到"自动清理"但未指定清理机制（后台 GC 进程？定时扫描？）。若依赖手动清理或无清理，`auth/challenges/` subspace 将持续增长（虽然有 10/min per-IP 限速，但分布式攻击者可用多 IP 绕过）。
- **修复建议**: 明确 FDB challenge 清理策略——建议使用后台 GC worker 每 60s 扫描 `auth/challenges/` 并删除 `created_at + ttl < now` 的记录。

**S-M2: Store reset checklist 第 5 步「验证 Store 隔离」缺乏具体验证方法**

- **位置**: `specs/core/04-wasm-sandbox.md` §1 Store reset checklist 步骤 5
- **问题描述**: "验证 Store 隔离：检查实例化的 Instance 不含上一 tick 残留引用/状态"——但未说明如何执行此验证。Wasmtime Instance 的内部状态（如 global 变量、table 条目、memory 内容）在重新实例化后应由 Wasmtime 保证清空，但需要明确验证方法（例如：在实例化后检查所有 imported global 的初始值是否为编译器定义的默认值、memory 前 N 页是否全零）。
- **修复建议**: 补充具体的验证步骤：memory 清零由步骤 1 覆盖；Instance 重建由步骤 3 覆盖。步骤 5 应改为验证性检查——抽样读取 memory 前 256 字节确认全零、验证 table 长度为 0、验证所有 global 值为默认值。提供具体的检查代码或伪代码。

**S-M3: Refresh token rotation grace period 缺少 IP/UA 异常检测的具体阈值**

- **位置**: `design/auth.md` §14.1 — "异常 IP/UA 使用 grace 时触发 session family revoke"
- **问题描述**: grace period（60s 非受信设备 / 10s 受信设备）允许旧 refresh token 在 rotation 后仍被接受。若旧 token 被窃取，攻击者可在 grace 窗口内使用。文档称"异常 IP/UA"会触发全家吊销，但未定义何为"异常"——同一城市的不同 IP？同一 ISP 的不同 IP 段？移动网络的 IP 漂移？缺少具体阈值可能导致误吊销（正常用户移动切换被吊销）或漏检（攻击者使用同 ISP IP 绕过）。
- **修复建议**: 定义具体的异常检测规则：IP 前缀变化（/24 for IPv4, /48 for IPv6）、ASN 变化、User-Agent 变化、地理位置跳跃（>1000km）。建议 grace 窗口极短（受信设备 10s 已足够），并增加可选的显式确认步骤（如要求客户端在 rotation 响应中确认新 token）。

**S-M4: CVE-SLA critical crate 列表可能遗漏证书相关依赖**

- **位置**: `specs/security/CVE-SLA.md` §1 — critical crates 列表
- **问题描述**: 列表包含 `blake3`, `ed25519-dalek`, `ring`, `rustls` 等，但不包含证书解析相关 crate。若 Swarm 使用 `x509-cert`、`der`、`pkcs8`、`pem-rfc7468` 等 crate 进行证书解析和密钥处理，这些也应纳入 CVE 监控范围——证书解析漏洞可直接导致认证绕过。
- **修复建议**: 审查 `Cargo.toml` 中所有与证书/X.509/ASN.1/密钥解析相关的依赖，将其加入 CVE-SLA 的 critical crates 列表。

**S-M5: `swarm_deploy` 没有显式的 code_signature 参数**

- **位置**: `specs/reference/api-registry.md` §3.2 Deploy — `swarm_deploy` input schema
- **问题描述**: `swarm_deploy` 的 input schema 为 `{player_id, drone_id, wasm_bytes, metadata}`，不包含 code signature 字段。但 auth.md §5.4 和 09-command-source.md §3.3 明确要求部署时必须携带 `CodeSigningCertificate` 签名。api-registry.md 的 schema 缺少 `code_signature`、`certificate_id` 等认证字段——这些可能作为 HTTP headers 传输（`Swarm-Signature` 等），但 deploy 的签名 payload 包含 `module_hash` 和 `metadata_hash`，与 canonical request signature（覆盖 method/path/body_hash）不同。deploy 需要双层签名：请求签名（认证）+ deploy payload 签名（代码签名）。
- **修复建议**: 在 api-registry.md `swarm_deploy` 的 input schema 中显式增加 `code_signature`、`certificate_id`、`version_counter` 字段，或在文档中明确说明 deploy 的双层签名模型，并引用 09-command-source.md §3.2 的 `DeployPayload` 结构。

---

### Low

**S-L1: `omitted_count` 分桶在 training 模式下丢失精确调试信息**

- **位置**: `specs/security/05-visibility.md` §10.2
- **问题描述**: `omitted_count` 分桶（"few"/"some"/"many"/"extreme"）对所有 `detail_level` 统一生效。在 `training` 模式下，开发者需要精确的截断数量来调试 snapshot 大小问题，分桶会丧失此信息。但分桶仅影响 `swarm_get_snapshot` 的输出——WASM `tick()` 收到的也是分桶值吗？如果 WASM 侧也是分桶值，会影响玩家的调试能力。
- **修复建议**: 将分桶策略绑定到 `detail_level`：`competitive` → 分桶（当前设计），`practice` → 分桶但更细粒度，`training` → 精确值。WASM `tick()` 收到的 snapshot 在 `training` 模式下可包含精确值。

**S-L2: `host_get_random` sequence 参数类型不一致**

- **位置**: 
  - `specs/core/04-wasm-sandbox.md` §3.2 — `host_get_random(sequence: u32, ...)`
  - `specs/reference/api-registry.md` §4.1 — `host_get_random(sequence: u64, ...)`
- **问题描述**: 04-wasm-sandbox.md 中 `host_get_random` 的 sequence 参数为 `u32`，api-registry.md 中为 `u64`。虽然 u32 的 4B 序列空间足够（10 次调用/tick × 2³² ticks），但类型不一致会导致 SDK 代码生成和 ABI 绑定的分歧。
- **修复建议**: 统一为 `u64`（api-registry.md 是权威源，以它为准），更新 04-wasm-sandbox.md 的签名。

**S-L3: Admin 双签要求仅覆盖 epoch bump，未覆盖 batch revoke**

- **位置**: `design/auth.md` §10.5b Admin 高权限操作认证
- **问题描述**: 表格中仅 Epoch bump / force CRL rotation 要求双 Admin 确认，Batch revoke 和 World config 热更新仅需单 Admin。批量吊销证书是高影响操作——恶意或失误的批量吊销可导致大量玩家失去部署能力。建议 Batch revoke（超过可配置阈值，如 >5 证书）也要求双签。
- **修复建议**: 为 Batch revoke 增加阈值触发的双签要求：≤5 证书单签即可，>5 证书要求第二个 Admin 确认。

---

## 3. 亮点

1. **FDB/Object Store 分层持久化架构** (`05-persistence-contract.md`): 10 字段的 replay-critical TickCommitRecord 在 FDB 中原子提交 + RichTraceBlob 异步写入对象存储的分离设计，消除了跨存储双写的原子性问题，同时保证确定性回放不依赖对象存储可用性。`terminal_state = audit_gap` 的降级语义设计优雅。

2. **多维度可见性 oracle 防线** (`05-visibility.md`): `NotVisibleOrNotFound` 统一错误码、`omitted_count` 分桶、特殊攻击拒绝码等价类（`NotEligible` vs 自身状态码）、`fog_of_war=true` 且 `player_view=full` 的组合被配置验证拒绝——形成了系统的反 oracle 体系。

3. **WASM 沙箱纵深防御** (`04-wasm-sandbox.md`): seccomp (BPF) + cgroup v2 + 独立 netns + Store reset checklist + per-process worker 隔离 + 禁止 StartSection + 编译缓存键包含 security_epoch——5 层 OS 隔离加 3 层 WASM 级防护，防御深度充足。

4. **用途隔离证书模型** (`design/auth.md`): `ClientAuthCertificate` / `CodeSigningCertificate` / `AdminCertificate` / `FederationCertificate` 各自独立的 TTL、scope 和 audience——防止认证凭据被跨用途滥用。Admin 证书 1h TTL + 短有效期是最佳实践。

5. **多层 CSR 准入控制** (`design/auth.md` §5.2): L1 PoW → L2 per-IP 限流 → L3 per-ASN 限流 → L4 全局 semaphore → L5 有界队列 → L6 audit throttle——6 层递进防护防止注册滥用。PoW challenge 服务端权威读取（客户端不可自报 challenge/difficulty）防止降级攻击。

6. **Deferred command model** (`04-wasm-sandbox.md` §3): WASM `tick()` 仅返回 JSON 指令而非直接调用 mutating host function——即使 WASM 沙箱被突破，攻击者仍需通过指令校验管线才能影响世界状态。所有 mutating 操作经过统一的 `validate_and_apply()` 路径。

7. **Version counter 防重放** (`09-command-source.md` §7.3): Deploy 不使用 nonce 而用 FDB per-player/per-slot 单调递增 `version_counter`——崩溃安全、严格递增、不依赖外部存储。与 MCP 查询的 Dragonfly nonce 分层清晰。

---

## 4. CrossCheck — 需要跨方向检查

- **CX-1: [S-C1 相关] Transport audience 标签枚举不统一** → 建议 **Architecture + Interface** 方向联合审查：确认所有文档（api-registry.md, auth.md, 03-mcp-security.md, 09-command-source.md）中的 transport label 集合完全一致，以 api-registry.md §9 为单一权威源。Gateway 证书验证逻辑和 Auth Service 证书签发逻辑必须使用同一枚举。

- **CX-2: [S-H2 相关] `swarm_deploy` RPC 参数与异步 blob 上传流程矛盾** → 建议 **Core/Engine** 方向检查 deploy 端到端流程：明确是同步 RPC（wasm_bytes 在请求体中）还是异步两阶段（先上传 blob 再提交 manifest）。若为同步，05-persistence-contract.md 的 UPLOAD_PREPARE 阶段需重写；若为异步，api-registry.md 的 schema 需改为 blob reference。

- **CX-3: [S-H1 相关] WebSocket per-message MAC payload 规范统一** → 建议 **Interface/MCP** 方向验证：以 auth.md §10.5a 的 6 字段 payload（direction + session_id + seq + tick + body_hash）为权威格式，更新 api-registry.md §3.5 和 03-mcp-security.md §2.5 使其一致。确认 MAC 签名密钥来源（会话派生 vs 握手绑定的用户私钥）。

- **CX-4: [S-M1 相关] FDB challenge/subspace TTL 清理机制** → 建议 **Infrastructure/Storage** 方向审查：确认 FDB `auth/challenges/` subspace 的垃圾回收策略（后台 worker 扫描间隔、批量删除的事务边界）。验证在 10000+ challenge records 下的 GC 不会影响 tick 事务延迟。

- **CX-5: [S-M3 相关] Refresh token grace period 安全边界** → 建议 **Auth** 方向审查：定义 IP/UA 异常检测的具体阈值（IP 前缀掩码、ASN 变化、地理位置跳跃距离）。评估移动网络 IP 漂移的误吊销风险。

- **CX-6: [S-M5 相关] Deploy 双层签名模型（请求认证 + 代码签名）** → 建议 **Interface + Auth** 联合审查：`swarm_deploy` 需要同时验证 Canonical Request Signature（认证请求者）和 DeployPayload Signature（认证代码作者）。确认 MCP schema 中如何表达这两个签名——请求签名在 HTTP headers，代码签名在 request body 中？api-registry.md 的 deploy schema 需要补充 `code_signature` 字段。