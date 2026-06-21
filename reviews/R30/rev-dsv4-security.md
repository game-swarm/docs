# R30 Security Review — rev-dsv4-security

> **评审视角**: 协议分析、竞态条件检测、安全边界完整性。追溯每个信任边界：client↔server MCP、drone↔sandbox、player↔player。验证 TOCTOU、时序攻击、重放攻击防护的完备性。
>
> **评审模型**: DeepSeek V4 Pro | **日期**: 2026-06-21

---

## 1. Verdict

**REQUEST_MAJOR_CHANGES**

设计在核心安全架构上表现出色——应用层证书模型、WASM sandbox 多层隔离、可见性统一过滤、FDB 原子持久化——但存在一个 **Critical** 级别的 Host Function oracle 漏洞和多个 **High** 级别的跨文档不一致问题需要修复，才能达到可实施的安全水准。

---

## 2. 发现的问题

### 2.1 Critical

#### C1 — Host Function `ERR_NOT_VISIBLE` 形成可见性 Oracle

- **文件**: `specs/reference/api-registry.md` §4.5 + `specs/security/05-visibility.md` §3.0, §10.4
- **描述**: Host Function ABI 定义了 `ERR_NOT_VISIBLE` (-3) 作为独立的错误码（"实体不可见 (visibility redaction)"）。然而 `05-visibility.md` §3.0 声明所有 host function 返回结果经 `is_visible_to` 过滤，§10.4 则规定所有特殊攻击的拒绝码统一合并为 `NotVisibleOrNotFound`。两者之间存在根本矛盾：
  - 如果 `host_get_objects_in_range` 对不可见区域返回 `ERR_NOT_VISIBLE`，WASM 可通过坐标扫描区分"区域不可见但存在实体"与"区域不可见且无实体"，形成 oracle。
  - 如果 host function 改为返回空结果集（不区分不可见/不存在），则 `ERR_NOT_VISIBLE` 错误码定义失去意义，应修正或移除。
- **影响**: WASM 沙箱内的恶意代码可通过 host function ABI 探测不可见实体，绕过 visibility 系统的 `NotVisibleOrNotFound` 合并策略。这违反了 "攻击者永远无法通过拒绝码区分'目标不存在'与'目标不可见'" 的核心安全不变量。
- **修复建议**:
  - 方案 A（推荐）: 从 Host Function ABI 中移除 `ERR_NOT_VISIBLE`。所有 host function 在不可见/不存在的场景下统一返回成功 + 空结果集（或过滤后的结果），不使用错误码区分。`ERR_VALIDATION` (-7) 仅用于参数错误（如无效 room_id、越界坐标），不涉及可见性。
  - 方案 B: 保留 `ERR_NOT_VISIBLE` 但仅用于 entity-specific 查询（如 `host_get_drone(drone_id)`）——且必须确保该 drone_id 对应实体存在但不可见时才返回此错误；若实体不存在则返回不同类型的错误。**不推荐**——这仍可能通过 drone_id 遍历形成 oracle。

---

### 2.2 High

#### H1 — 联邦 CRL 同步窗口过大（180s 吊销延迟）

- **文件**: `design/auth.md` §15.2a, §15.6
- **描述**: 联邦 CRL 同步间隔为 60s。`revocation_fallback` 默认值为 R27 ML-10 裁决的 `reject_for_code_and_login`，但 §15.6 描述的备选策略 `accept_login` / `reject_for_code` 说明非默认配置下可能存在安全退化。更重要的是：CRL 同步间隔 60s + 过期容忍 2× 同步间隔（120s）= 180s 窗口。在此窗口内，已被远程世界吊销的证书仍可用于本地登录并签发新的本地 `ClientAuthCertificate`。
- **影响**: 恶意玩家在远程世界被吊销后，可在最多 180s 内使用旧证书登录联邦信任的本地世界，获得新的本地身份。
- **修复建议**:
  - 将联邦 CRL 同步间隔从 60s 缩短到 15s（对带宽影响极小——CRL delta 通常 < 1KB）
  - `revocation_fallback` 值强制为 `reject_for_code_and_login`（不接受降级配置），CRL 过期 ≥ 30s 即拒绝该远程世界全部操作
  - 或在联邦登录握手时增加实时 CRL 查询（`GET /auth/crl/check?cert_id=...`），不依赖定期同步

#### H2 — 服务器代管私钥 (`managed_by_server=true`) 的服务器妥协风险

- **文件**: `design/auth.md` §5.2
- **描述**: 当用户选择服务器代管私钥时，`managed_by_server=true` 标记的密钥对由服务端生成并持有。文档声明约束了 TTL、scope（不可签发 AdminCertificate）并写入审计日志。但若服务器被妥协，攻击者可：
  - 使用所有代管密钥签名任意操作
  - 修改审计日志掩盖行为（除非审计日志有防篡改机制——未在文档中找到）
- **影响**: 服务器妥协 = 所有代管密钥账号的完全失控。虽然 scope 限制阻止了 admin 操作，但 code_signing 和 client_auth 的滥用可造成实质性破坏。
- **修复建议**:
  - 代管密钥必须使用 HSM 或至少独立加密存储（密钥加密密钥与 Auth Service 进程隔离）
  - 审计日志使用 append-only + hash chain 防篡改（与 TickTrace hash chain 同一模式）
  - `managed_by_server=true` 的证书 TTL 强制 ≤ 1h，续签需用户显式授权
  - 在 world.toml 中增加 `[auth] allow_managed_keys = false` 默认关闭，需服主显式 opt-in 并接受风险声明

#### H3 — Host Function ABI 与 Snapshot 接口的可见性合同不一致

- **文件**: `specs/reference/api-registry.md` §4.5 vs `specs/security/05-visibility.md` §3.0 vs `specs/core/04-wasm-sandbox.md` §3.2
- **描述**: 三份文档对 host function 的可见性行为描述存在微妙差异：
  - `api-registry.md` §4.5: 定义 `ERR_NOT_VISIBLE` 为独立错误码
  - `05-visibility.md` §3.0: 声明 "所有 query host function 的返回结果均经 is_visible_to 过滤"
  - `04-wasm-sandbox.md` §3.2: 在函数注释中标注 "← 仅返回 is_visible_to(caller) 为 true 的实体"
  
  核心问题：`ERR_NOT_VISIBLE` 的具体触发条件未在任何文档中明确定义。是"查询区域内所有实体均不可见"触发？还是"特定 target entity 不可见"触发？这会直接影响 oracle 攻击面。
- **影响**: 实现者根据含糊规范可能引入信息泄露路径。WASM 沙箱的可见性完整性无法在 spec 层面得到保证。
- **修复建议**:
  - 与 C1 合并修复：移除 `ERR_NOT_VISIBLE` 或精确定义其触发条件（且必须与 visibility spec 的 `NotVisibleOrNotFound` 合并策略一致）
  - 在 `api-registry.md` §4.5 中为每个 host function 单独列出：哪些错误码可返回、在什么条件下返回
  - CI 增加 spec-consistency 检查：`ERR_NOT_VISIBLE` 的出现必须被 `05-visibility.md` 的逻辑覆盖

#### H4 — Deploy 状态机崩溃恢复缺口

- **文件**: `specs/security/09-command-source.md` §7.4 + `specs/core/05-persistence-contract.md` §2.3
- **描述**: Deploy 状态机定义了 `idle → compiling → deployed → active` 流程。`version_counter` 在 FDB 事务中递增，但 §7.4 状态转换表未覆盖以下崩溃场景：
  - 服务器在 `compiling` 状态崩溃：`version_counter` 已递增（FDB 事务已提交），但编译未完成。重启后 deploy 记录停留在 `compiling`，客户端无法重试（因为 version_counter 已被消费，任何 ≤ 当前 counter 的提交被拒绝为 `stale_deploy`）。客户端必须递增到 counter+1 才能重试——但文档未说明客户端如何发现当前 counter 值。
- **影响**: 在编译阶段崩溃后，客户端 deploy 请求进入死锁——不知道当前 counter 值就无法构造有效 payload，旧 counter 被永久阻塞。
- **修复建议**:
  - 增加 MCP 工具 `swarm_get_deploy_counter` 或 `swarm_get_deploy_status` 返回 `current_version_counter`，让客户端可以同步
  - 或在 `compiling → idle` 转换中不消费 version_counter（先编译再递增 counter），但这引入 TOCTOU
  - 推荐方案：`swarm_get_deploy_status` 已返回 `fdb_version_counter`（api-registry.md §3.2 Deploy），确认该字段在所有中间状态都可用，并在文档中显式说明崩溃恢复路径

---

### 2.3 Medium

#### M1 — CSR 提交的 Challenge 并发竞争

- **文件**: `design/auth.md` §9.3, §9.4
- **描述**: CSR 提交验证 PoW 后原子消费 challenge（FDB 事务内标记 `consumed`）。如果同一 challenge_id 被两个并发请求提交（race condition），FDB 事务的乐观并发控制应处理——第二个事务会冲突重试，发现 challenge 已 consumed 后返回 `challenge_consumed`。这一行为依赖 FDB 事务的 SERIALIZABLE 隔离级别，但文档未显式声明此依赖。
- **影响**: 如果 FDB 隔离级别被降级或实现使用了非事务性检查，可能出现 double-spend。
- **修复建议**:
  - 在 §9.3 的验证流程中显式标注 "依赖 FDB 严格可序列化事务"
  - 增加集成测试：两个并发 CSR 使用同一 challenge_id → 一个成功一个返回 `challenge_consumed`

#### M2 — 编译管道 DoS 攻击面

- **文件**: `specs/core/04-wasm-sandbox.md` §7
- **描述**: 编译预算为 30s 超时 + 512MB 内存 + 最多 5 并发。恶意 WASM 可被精心构造为恰好 29.9s 的编译时间，5 个此类并发请求即可完全饱和编译管道 30s。结合部署频率限制（10/h），单个玩家无法造成显著影响，但 10 个协调的恶意账号可消耗 5×30s×10/h = 1500s/h 的编译资源。
- **影响**: 中等——已有速率限制限制了单个玩家的影响，但协调攻击仍可能造成编译服务降级。
- **修复建议**:
  - 将编译超时从 30s 降低到 15s（正常 WASM 编译 < 3s）
  - 增加 per-IP 编译并发限制（当前仅有 per-player 部署限速 10/h）
  - 或增加编译复杂度预算（如限制 WASM 函数数量、指令数等）

#### M3 — WebSocket Agent seq 计数器无持久化语义

- **文件**: `specs/reference/api-registry.md` §3.5
- **描述**: Agent WS 使用 per-message seq + Ed25519 MAC。服务器维护 `last_seq` 计数器。若服务器崩溃重启，`last_seq` 是否有持久化？若无，重启后 `last_seq` 重置为 0，客户端发送 seq=42 的消息会被拒绝（因为 42 > 1，违反 seq 单调性检查）。
- **影响**: 服务器重启后所有已连接 Agent WS 会话需要重新握手（断开重连）。这是可恢复的但会导致中断。
- **修复建议**:
  - 明确 seq 计数器仅在连接生命周期内有效，断开重连后 seq 重新从 1 开始
  - 或在 Dragonfly 中持久化 `last_seq`（TTL = session timeout）

#### M4 — Cross-Room 2PC Fallback 语义不明确

- **文件**: `specs/core/05-persistence-contract.md` §8.2
- **描述**: Cross-room 2PC 的约束表中标注 "超时 3s，fallback to best-effort"。`best-effort` 未定义——是指放弃跨房间操作？部分提交？异步补偿？
- **影响**: 在 room partition 模式下，跨房间操作（如跨房间资源传输）的语义不确定——可能引入不一致状态。
- **修复建议**:
  - 定义 `best-effort` 的具体行为：若 2PC 超时，source room 操作提交，target room 操作放弃并记录 `cross_room_failed` 事件；后续 tick 重试
  - 与 economy/gameplay 方向协调，确认跨房间操作的一致性语义

#### M5 — `swarm_deploy` 的 wasm_bytes 字段暴露风险

- **文件**: `specs/security/03-mcp-security.md` §4.1
- **描述**: `swarm_deploy` 的 input schema 包含 `wasm_bytes`（base64 WASM 二进制）。如果 MCP 日志/审计记录保留了完整的 `wasm_bytes`，则攻击者通过 ClickHouse 审计日志访问即可获取所有已部署的 WASM 源码（wasm 可反编译为近似源码）。当前 `mcp_audit` 表包含 `parameters String`——这意味着 WASM blob 可能被完整记录。
- **影响**: WASM 模块（玩家策略代码）可通过审计日志泄露给未授权方。
- **修复建议**:
  - `swarm_deploy` 的审计日志只记录 `module_hash` + `metadata_hash`，不记录 `wasm_bytes`
  - 在 §7 mcp_audit 表设计中增加敏感字段脱敏策略（`wasm_bytes` → `\"<REDACTED>\"`）
  - 增加参数级别的审计脱敏配置

---

### 2.4 Low

#### L1 — CVE-SLA 未覆盖非 Rust 依赖

- **文件**: `specs/security/CVE-SLA.md`
- **描述**: SLA 范围限定于 Wasmtime 和指定的 Rust crate 列表。Gateway（Go）、FoundationDB client、Dragonfly client、前端依赖未在范围内。
- **修复建议**: 增加 Gateway/Go 依赖的 CVE 监控要求（最低：`govulncheck` CI 集成，Critical/High 同 SLA 响应时间）

#### L2 — 浏览器 IndexedDB 存储证书

- **文件**: `design/auth.md` §14.3
- **描述**: Certificate 存储在 IndexedDB（JS 可访问）。文档已声明 certificate "仅作缓存，不构成独立认证根"，且签名仍需 WebCrypto non-extractable 私钥。在当前设计下这是安全的——证书本身被盗用无法伪造签名。但需验证前端实现确实不将 certificate 用作 bearer token。
- **修复建议**: 在前端测试中增加 "certificate-only 请求被拒绝" 的集成测试

#### L3 — SIMD 确定性风险

- **文件**: `specs/core/04-wasm-sandbox.md` §2.2
- **描述**: `wasm_simd` 按 world.toml 配置启用（默认禁用），仅 `deterministic_subset` 时放开。Wasmtine 的 SIMD 确定性子集是什么？文档未引用具体规范。不同 CPU 架构（x86 AVX2 vs ARM NEON）的 SIMD 行为可能产生不同结果。
- **修复建议**: 引用 Wasmtime 的 SIMD 确定性文档或 Bytecode Alliance 规范；增加跨架构 SIMD 回归测试

#### L4 — Overload 特殊攻击的 target_player_id 可见性

- **文件**: `specs/security/05-visibility.md` §6.1
- **描述**: Overload 攻击成功后 attacker 可见 `target_player_id`。文档未澄清：若 target 实体在 attacker 视野内，这是否合法？分析后确认合法——因为 attacker 需要通过 `target_id` 指定目标，且目标在视野内才能执行攻击（否则被 `NotVisibleOrNotFound` 拒绝）。但文档应显式声明此前提。
- **修复建议**: 在 §6.1 attacker 视角第一条增加 "仅在攻击执行成功的前提下（即 target 在 attacker 视野内且攻击未拒绝）"

#### L5 — WASM Entity Name 字符校验的执行点

- **文件**: `specs/security/03-mcp-security.md` §6.2 + `specs/core/04-wasm-sandbox.md`
- **描述**: 名称仅允许 `[a-zA-Z0-9 _-]`，最长 32 字符。文档标注 "输入时拒绝"。执行点在何处？是在 WASM 输出 JSON 解析时校验，还是在 FDB 写入时校验？如果 WASM tick() 的输出 JSON 直接包含 name 字段但未经服务端校验，可能允许注入。
- **修复建议**: 明确执行点为 "服务端在 RawCommand 解析时强制校验，拒绝不符合字符集的 name 字段（拒绝码 InvalidName）"

#### L6 — 可见性缓存内存占用

- **文件**: `specs/security/05-visibility.md` §5
- **描述**: 每 tick、每玩家缓存 `HashSet<EntityId>`。在 500 玩家 × 50,000 实体的最坏情况下，每玩家缓存约 400KB（50,000 × 8 bytes），合计 ~200MB。实际会因 fog-of-war 远小于此值，但文档应评估内存上限。
- **修复建议**: 增加缓存上限策略（如 LRU 淘汰或限制每玩家可见实体数上限）；标注内存评估

---

## 3. 亮点

1. **应用层证书模型设计成熟** — `design/auth.md` 的 CSR → 用途隔离证书 → canonical request signature 全链路设计清晰、完整。Server Root CA 离线 + Intermediate CA 在线轮换 + HSM 保护 + 启动强制检查——多层纵深防御。应用层证书不进入系统 trust store，传输层 CA 隔离——正确避免了传统 PKI 的 trust store 污染问题。

2. **可见性系统的 Oracle 防线闭合良好** — `05-visibility.md` §10 的 `omitted_count` 分桶、`dry_run`/`simulate` 脱敏、特殊攻击拒绝码 `NotVisibleOrNotFound`/`NotEligible` 等价合并——显示了系统性的 oracle 消除思维。这是很多系统忽视的细节。

3. **WASM Sandbox 隔离多层纵深** — `04-wasm-sandbox.md` 的 seccomp BPF + cgroup v2 + 网络命名空间 + 只读根文件系统 + Wasmtime fuel/epoch/内存限制 + WASI 全禁——五层独立隔离，任一层被突破仍有 backup。§9 的统一 OS 加固 checklist 是部署安全的优秀实践。

4. **Persistence Contract 的 FDB-as-authority 模型** — `05-persistence-contract.md` 的 replay-critical subset 声明 + FDB 原子提交 + blob 异步上传 + hash chain 完整性验证——明确的职责分离和失败语义。D5/B 裁决将 blob 写入改为异步是正确的，避免了大 blob 拖慢 FDB 事务。

5. **Transport Split 安全模型** — `03-mcp-security.md` §2 将 Browser 和 Agent/CLI 分离为两条独立的传输安全路径——Browser 依赖 Origin/CSRF/Fetch Metadata，Agent 依赖应用层证书签名——防止了跨协议混淆攻击。

6. **Auth 多维 Admission Control** — `design/auth.md` §10.7 的 CSR 6 层限流（PoW → per-IP → per-ASN → global semaphore → worker queue → audit throttle）展示了针对分布式 DoS 的分层防御思维。

7. **Command Source 不可伪造** — `09-command-source.md` 的所有 auth context 服务端注入、客户端不可自报、Source Gate 前置隔离——正确实施了 zero-trust 原则。

---

## 4. CrossCheck

以下是我在安全方向内发现但需要其他方向评审确认的问题：

- **CX-1: Host Function ABI 与 Command Validation 的可见性合并策略一致性** → 建议 **API Design / Gameplay** 方向检查：`ERR_NOT_VISIBLE` 的语义与 Command Validation 中 `NotVisibleOrNotFound` 的统一策略是否在所有 host function 调用路径上保持一致。特别关注 `host_get_objects_in_range` 和 `host_path_find` 在不可见区域的返回值。

- **CX-2: Cross-Room 2PC best-effort fallback 语义** → 建议 **Engine / Economy** 方向检查：`05-persistence-contract.md` §8.2 的 `best-effort` 在跨房间资源操作中的具体行为。是否需要与 economy 的 transfer 语义协调？

- **CX-3: SIMD deterministic_subset 定义** → 建议 **Determinism & Performance** 方向检查：`04-wasm-sandbox.md` §2.2 的 `deterministic_subset` SIMD 是否在 Wasmtime 文档中有权威定义？跨 x86/ARM 的 SIMD 行为一致性是否经过验证？

- **CX-4: MCP Audit 脱敏范围** → 建议 **API Design / Privacy** 方向检查：`mcp_audit` 表是否应增加字段级别的脱敏策略（特别是 `swarm_deploy` 的 `wasm_bytes`）？敏感参数（私钥引用、recovery token）是否进入审计日志？

- **CX-5: Deploy version_counter 崩溃恢复的客户端可见性** → 建议 **API Design** 方向检查：`swarm_get_deploy_status` 是否在所有中间状态（compiling、activation_pending）都返回 `fdb_version_counter`？崩溃后客户端如何同步当前 counter？

- **CX-6: Managed-by-server 密钥的审计日志防篡改** → 建议 **Engine / Persistence** 方向检查：`design/auth.md` 的 `auth/admin_audit` 和 `auth/key_audit` 日志是否使用 append-only + hash chain 防篡改（类似 TickTrace hash chain）？当前设计是否允许 Auth Service 单方面修改审计日志？