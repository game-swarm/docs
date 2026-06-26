# R35 Security Review — rev-gpt-security

## 1. Verdict

REQUEST_MAJOR_CHANGES

理由：当前设计已经覆盖了应用层证书、CSR、nonce/replay、防可见性 oracle、WASM sandbox、对象存储异步持久化等关键安全面，但仍存在多处必须修复的安全合同分叉：指定的 CVE/SLA 文件缺失；Auth 权威参数在 design 与 API Registry 中冲突；CSR admission control 在同一文档内自相矛盾；WebSocket transport/audience/signature 语义分裂；sandbox 网络隔离描述冲突；deploy hash 对象不一致可能导致签名验证与运行对象错配。这些问题会直接影响认证链、DoS 防护、重放防护、供应链响应与 sandbox 边界的实现一致性。

## 2. 发现的问题

### S-H1 — High — specs/security/08-cve-sla.md:1

问题描述：任务指定必须评审 `/tmp/swarm-review-R35/specs/security/08-cve-sla.md`，但该路径不存在；读取结果为 File not found，目录中仅出现相似文件 `CVE-SLA.md`。由于任务明确禁止读取未列出的其他设计文档，我没有打开相似文件。

影响分析：CVE/SLA 是供应链与运行时漏洞响应的权威合同。当前安全评审无法验证 Wasmtime、wasmparser、argon2、WebAuthn、TLS/HTTP 网关、object store SDK 等依赖的漏洞分级、停服/降级触发条件、补丁时限、版本支持窗口和公告订阅源。`specs/core/04-wasm-sandbox.md:66` 到 `specs/core/04-wasm-sandbox.md:73` 明确引用 `specs/security/CVE-SLA.md` 作为权威源，但 task body 指定的是 `08-cve-sla.md`，形成路径/命名分叉。

修复建议：将 CVE/SLA 权威文件恢复到任务与索引一致的路径，或在所有引用与 task body 中统一为同一个 canonical 文件名。建议文件内至少定义：依赖范围、CVSS/EPSS/KEV 分级、Critical/High 的强制停用或 sandbox deploy freeze 条件、评估/修复时限、例外审批、SBOM 与 cargo-audit/osv-scanner/trivy 等扫描输出的 CI gate。

### S-H2 — High — design/auth.md:259 与 design/auth.md:970

问题描述：同一认证设计文档内，CSR admission control 的权威表 §5.2 明确要求 L2 per-IP CSR 提交速率 `≤ 1/30s`、L3 per-ASN `≤ 10/min`、global semaphore、bounded queue；但 §10.8「未认证端点保护」又声明 `CSR 提交 | PoW 自身限速 | 无额外 IP 限制`。

影响分析：这是 DoS 防护合同的直接冲突。实现者若按 §10.8 取消额外 IP 限流，会让攻击者用分布式或高算力来源绕过 PoW 成本，把 CSR 验签、FDB challenge 事务、审计写入和证书签发路径变成放大面。该冲突也会让 API Registry 中 `swarm_submit_csr` 的 per_ip rate limit 难以落地。

修复建议：删除或改写 `design/auth.md:978` 的「无额外 IP 限制」，明确 CSR 提交必须执行 §5.2 的 L1-L6 多层准入链，`swarm_submit_csr` rate limit key 为 `per_ip` 只是其中一层，不能替代 per-ASN/global semaphore/bounded queue/audit throttle。把 §10.8 改成引用 §5.2，不重新声明可冲突数值。

### S-H3 — High — design/auth.md:624 与 specs/reference/api-registry.md:641

问题描述：注册 PoW 默认难度在 design 与 API Registry 中冲突。`design/auth.md:624` 到 `design/auth.md:633` 声明标准默认 `difficulty_bits = 24`；`design/auth.md:1815` 到 `design/auth.md:1817` 的配置示例也写 `register_pow_difficulty_bits = 24`。但 API Registry 的 Auth 限制表声明 `CSR challenge default difficulty = 20 bits`。

影响分析：PoW 难度是未认证入口抗滥用的核心参数。20 bits 与 24 bits 相差 16 倍预期工作量，会显著改变批量注册成本和服务端压力模型。更严重的是 API Registry 自称由 IDL 自动生成且为 API 合约权威，若实现按 IDL 生成 20 bits，而设计/安全测试按 24 bits 评估，会导致 DoS 风险被低估。

修复建议：选择单一权威默认值并同步 IDL/API Registry、design/auth.md、配置示例和测试。若目标是标准防滥用，建议将 IDL/Auth Registry 默认改为 24 bits；若保留 20 bits，必须重新评估注册洪泛成本并在 design 中降低相关安全声明。

### S-H4 — High — design/auth.md:360 与 specs/reference/api-registry.md:816

问题描述：application-layer certificate audience 的 transport 枚举不一致。`design/auth.md:937` 到 `design/auth.md:946` 定义 transport 包含 `browser-http | browser-ws | agent-mcp | cli-rest | replay-viewer`；`specs/reference/api-registry.md:816` 到 `specs/reference/api-registry.md:823` 的 Transport Labels 只列出 `agent-mcp | cli-rest | wasm-sdk`；`specs/security/09-command-source.md:185` 到 `specs/security/09-command-source.md:200` 又声明 `browser-ws`、`replay-viewer` 等 transport，并要求缺少 `X-Swarm-Transport` 拒绝。

影响分析：audience 是跨 transport 重放防护的核心字段。枚举分叉会导致某些合法 transport 无法验签、或某些实现宽松匹配 audience。尤其 Browser WS、Agent MCP、CLI REST、WASM SDK deploy 的证书不应互换；枚举不一致会扩大跨协议重放和 confused deputy 风险。

修复建议：以 API Registry/IDL 为机器权威补齐完整 transport enum，并把所有文档改为引用该枚举。建议 canonical transport 至少包含 `browser-http`、`browser-ws`、`agent-mcp`、`cli-rest`、`wasm-sdk`、`replay-viewer`、`federation`，并定义每个 transport 是否允许 bearer token、应用层证书、WebSocket、只读 spectator。

### S-H5 — High — design/auth.md:789 与 specs/reference/api-registry.md:441

问题描述：WebSocket 安全合同存在三处分叉。`design/auth.md:789` 到 `design/auth.md:827` 要求 Agent/CLI WS 握手后每条消息使用 `SWARM-WS-MSG-V1`、direction、session_id、seq、tick、body_hash 的 Ed25519 签名，并严格 `seq == last_seq + 1`。`specs/security/03-mcp-security.md:155` 到 `specs/security/03-mcp-security.md:175`基本一致。但 API Registry `specs/reference/api-registry.md:441` 到 `specs/reference/api-registry.md:451` 又称 Agent WS 序列号与 MAC 由 `Swarm-Request-Signature` 头携带，每消息覆盖 `(method, uri, timestamp, seq, body_hash)`，且只要求 `seq > last_seq`。

影响分析：WS 消息认证格式、严格递增语义和 tick/session 绑定不一致，会导致实现间无法互通，或更糟：某实现接受跳号、跨 tick、跨 session 重放消息。`seq > last_seq` 允许丢包式跳跃，与设计中的 `seq == last_seq + 1` 不同，会削弱重排/注入检测。

修复建议：将 API Registry 的 WebSocket 安全列改为引用 `SWARM-WS-MSG-V1` canonical payload，并明确 `seq == last_seq + 1`、direction 独立计数、session_id/tick/body_hash 必填、失败即断开+审计。不要复用普通 HTTP `Swarm-Request-Signature` 头语义描述 WS per-message 签名。

### S-H6 — High — specs/core/04-wasm-sandbox.md:21 与 specs/core/04-wasm-sandbox.md:275

问题描述：WASM sandbox 网络隔离描述自相矛盾。架构图/OS 隔离清单在 `specs/core/04-wasm-sandbox.md:21` 到 `specs/core/04-wasm-sandbox.md:26` 写「无网络命名空间」；但同文件 `specs/core/04-wasm-sandbox.md:275` 到 `specs/core/04-wasm-sandbox.md:285` 又要求 sandbox 进程拥有独立 netns、无网络接口、socket 返回 EAFNOSUPPORT，并把 netns 作为 L1 防线。

影响分析：sandbox 网络边界是高风险攻击面。若实现者按前文理解为没有独立 netns，仅依赖 seccomp 禁 socket，则 seccomp 配置错误、Wasmtime/JIT 或宿主 syscall 漏洞可能导致网络访问逃逸。该冲突会直接影响 CI 边界测试和部署 checklist。

修复建议：统一为“独立 netns，无接口/无路由/lo down + seccomp 禁 socket 双层防护”。将 `04-wasm-sandbox.md:24` 的「无网络命名空间」改为「独立网络命名空间（无接口/无路由）」并保持 §4.3、§9.1 的验证命令一致。

### S-H7 — High — specs/security/09-command-source.md:73 与 specs/core/05-persistence-contract.md:86

问题描述：DeployPayload 签名、manifest 与持久化合同对 `module_hash` 的对象定义不一致。`specs/security/09-command-source.md:73` 到 `specs/security/09-command-source.md:115` 要求客户端签名 `module_hash = Blake3(WASM bytes)`，服务端验证 `module_hash == Blake3(收到的 WASM bytes)`。但 `specs/core/05-persistence-contract.md:86` 到 `specs/core/05-persistence-contract.md:89` 在 UPLOAD_PREPARE 中写「编译 WASM → 原生码」后计算 `module_hash = Blake3(compiled_module)`。

影响分析：这是供应链完整性与部署认证的根本性分叉。客户端无法预先签名服务端特定 Wasmtime 版本/target_arch/security_epoch 下的 compiled native artifact；若 FDB manifest 记录 compiled_module hash，而签名验证记录 wasm_bytes hash，部署激活、回放、object store 校验、缓存键可能指向不同对象，造成 TOCTOU、错误归因或绕过签名语义。

修复建议：将 signed deploy identity 固定为 `wasm_module_hash = Blake3(canonical WASM bytes)`，FDB deploy manifest 必须记录该 hash。compiled artifact 另设 `compiled_artifact_hash = Blake3(compiled bytes || wasmtime_build_commit || target_arch || validation_policy_version || security_epoch)` 作为缓存/预热内部字段，不作为客户端签名的 `module_hash`。所有文档统一命名，避免一个字段承载两种对象。

### S-H8 — Medium — design/auth.md:1045 与 design/auth.md:1012

问题描述：账号恢复后旧证书吊销默认策略存在文本冲突。`design/auth.md:1012` 到 `design/auth.md:1019` 的恢复默认策略表规定 `all-certs-lost` 默认吊销全部旧证书、`stolen-device` 默认吊销全部旧证书。但邮箱恢复确认流程 `design/auth.md:1081` 到 `design/auth.md:1085` 写「确认恢复后签发新证书并吊销所有现有 refresh token；是否吊销旧证书由用户选择，默认保留未撤销证书」。

影响分析：恢复路径是账号接管后的关键安全边界。如果“所有证书丢失”或“设备被盗”时默认保留旧证书，攻击者持有的旧私钥/证书可能继续可用，尤其 CRL 延迟和证书 TTL 较长时风险显著。相反，如果实现按表强制吊销，但 UI 按流程文案允许保留，会产生用户预期与安全行为分裂。

修复建议：将恢复确认流程改为按 `recovery_reason` 执行 §10.9 默认策略：`stolen-device` 与 `all-certs-lost` 默认吊销全部旧证书；`device-swap`、`forgot-password` 可默认保留并提示用户手动吊销。恢复 token 中应携带 reason 或由确认时显式选择并审计。

### S-H9 — Medium — specs/security/05-visibility.md:401 与 specs/reference/api-registry.md:131

问题描述：特殊攻击可见性拒绝码使用未注册 canonical code。`specs/security/05-visibility.md:401` 到 `specs/security/05-visibility.md:413` 要求目标不可被攻击或处于冷却统一返回 `NotEligible`，但 API Registry RejectionReason 表 `specs/reference/api-registry.md:131` 到 `specs/reference/api-registry.md:164` 没有 `NotEligible`，且 `specs/reference/api-registry.md:219` 到 `specs/reference/api-registry.md:258` 要求不得发明新的 wire enum。

影响分析：这是安全 oracle 防线与机器权威枚举之间的冲突。实现者若新增 `NotEligible` 会违反 IDL/CI；若改用现有具体拒绝码，又可能泄露目标存在、类型、冷却状态等信息，形成可见性 oracle。

修复建议：在 IDL/API Registry 中正式新增 `NotEligible`，或把 visibility spec 改为使用现有 canonical code 的安全等价类，例如统一映射到 `NotVisibleOrNotFound` 或 `CooldownActive` 的脱敏 debug_detail 版本。必须由 API Registry 注册，不能只在 visibility 文档中出现。

### S-H10 — Medium — specs/security/03-mcp-security.md:306 与 specs/reference/api-registry.md:563

问题描述：MCP HTTP body size 与 WASM 模块大小上限不一致。`specs/security/03-mcp-security.md:306` 到 `specs/security/03-mcp-security.md:314` 声明 HTTP `max body size = 5 MB` 且「与 WASM 模块体积限制一致」；`specs/core/04-wasm-sandbox.md:132` 到 `specs/core/04-wasm-sandbox.md:139` 也限制 WASM bytes 最大 5MB。但 API Registry 的 WASM 限制表 `specs/reference/api-registry.md:563` 到 `specs/reference/api-registry.md:570` 只列 WASM 内存/CPU/timeout，没有列模块体积；同时 Persistence Blob Types `specs/reference/api-registry.md:929` 到 `specs/reference/api-registry.md:934` 将 `wasm_module` 最大大小写为 64MB。

影响分析：上传入口、sandbox 预校验和 object store 上限不一致会造成 DoS 与用户体验问题。若 gateway 接受 64MB，而 sandbox 最终拒绝 5MB，攻击者可用大 body 消耗带宽、base64 解码、object store、hashing 和审计资源；若 gateway 5MB 而 object store 64MB，文档又暗示二者一致，测试难以覆盖真实限制。

修复建议：选择单一 `max_wasm_upload_bytes` 并在 API Registry、MCP HTTP 安全合同、sandbox validate_module、object store blob table 中同步。若 object store 保留 64MB 用于未来或非玩家模块，必须把玩家 `swarm_deploy` upload cap 单独命名为 5MB，并要求 gateway 在解析前执行 Content-Length/body cap。

### S-L1 — Low — specs/security/09-command-source.md:15

问题描述：`Admin` source 在来源矩阵中 `rate_limit` 写「无限制」，但 API Registry 的 Admin 类 rate limit 是 `10/h`，具体 admin tools 也有 `5/min`、`10/h`、`30/tick` 等限制。

影响分析：虽然多个文档已有 admin rate limit，但 command-source 表仍可能误导实现者在 Source Gate 或 admin path 跳过限流。高权限管理操作若无 rate limit，会扩大误操作、凭据泄露后滥用和审计写入 DoS 风险。

修复建议：把 `specs/security/09-command-source.md:20` 的 Admin `rate_limit` 改为「见 API Registry per-tool admin rate limit」，不要写“无限制”。Admin override 只应放宽可见性/所有权，不应绕过认证、nonce、双签、冷却和审计限制。

## 3. 亮点

- 应用层证书模型方向正确：`design/auth.md:21` 到 `design/auth.md:35` 明确 Swarm CA 不进入系统 trust store，TLS/mTLS 与应用层身份分离，降低误用为通用 TLS CA 的风险。
- CSR 多层准入链设计充分：`design/auth.md:259` 到 `design/auth.md:269` 覆盖 PoW、per-IP、per-ASN、global semaphore、bounded queue、audit throttle，比单纯 PoW 更能抵御分布式注册洪泛。
- Canonical Request Signature 细节扎实：`design/auth.md:360` 到 `design/auth.md:414` 定义 LF、字段顺序、body hash、timestamp/nonce/cert/player/audience，具备实现确定性验签的基础。
- 浏览器凭据存储策略安全：`design/auth.md:1291` 到 `design/auth.md:1300` 禁止 localStorage 长期 bearer material，使用 HttpOnly Secure SameSite cookie、WebCrypto non-extractable key、CSP 与 Trusted Types，符合 XSS 高风险环境下的防护要求。
- 可见性统一函数和 oracle 防线明确：`specs/security/05-visibility.md:5` 到 `specs/security/05-visibility.md:13` 要求所有输出面调用同一个 `is_visible_to`；`specs/security/05-visibility.md:363` 到 `specs/security/05-visibility.md:413` 针对 omitted_count、simulate、dry_run、special attack oracle 做了专门闭合。
- WASM sandbox 采用多层边界：`specs/core/04-wasm-sandbox.md:75` 到 `specs/core/04-wasm-sandbox.md:130` 禁用 WASI 文件/网络/时钟/随机数，`specs/core/04-wasm-sandbox.md:423` 到 `specs/core/04-wasm-sandbox.md:480` 给出 seccomp/cgroup/namespace checklist 和 CI 验证。
- 持久化分层安全性好：`specs/core/05-persistence-contract.md:30` 到 `specs/core/05-persistence-contract.md:62` 清晰分离 replay-critical FDB subset 与 rich debug object store，降低对象存储失败对确定性 replay 的影响。
- Agent/AI prompt injection 风险有被建模：`specs/security/03-mcp-security.md:316` 到 `specs/security/03-mcp-security.md:357` 将游戏数据标注为 untrusted，并要求 SDK prompt delimiter，适合 AI player 场景。

## 4. CrossCheck — 需要跨方向检查

- CX1: API Registry 声称由 IDL 自动生成，但 auth transport enum、PoW 默认值、Auth 限制、WS 安全语义与设计文档不一致 → 建议 API/IDL 方向检查 `auth_api.idl.yaml` 与生成器是否落后于目标设计。
- CX2: `design/auth.md:358` 写完整矩阵见 `interface.md`，但本轮禁止读取 `design/interface.md`；MCP 工具授权矩阵是否仍与 API Registry 一致无法确认 → 建议 Interface/API 方向检查 capability profile、scope、visibility filter 的单事实源。
- CX3: `specs/core/05-persistence-contract.md:353` 到 `specs/core/05-persistence-contract.md:355` 引用 `specs/core/01-tick-protocol.md` 的 room-partition shadow write，但本轮未授权读取 → 建议 Core/Tick 方向检查 staging publish、GlobalTickCommit、cross-room all-or-nothing 是否闭合。
- CX4: `specs/core/04-wasm-sandbox.md:104` 到 `specs/core/04-wasm-sandbox.md:105` 允许 deterministic SIMD opt-in，但没有看到跨硬件确定性测试矩阵 → 建议 Determinism/Runtime 方向检查 SIMD、Cranelift、target_arch、wasmtime version 的 replay determinism gate。
- CX5: Object store、ClickHouse、Dragonfly、FoundationDB 多存储安全边界没有在本子集看到统一 credential/secrets 管理与 network policy → 建议 Ops/Infra 方向检查最小权限 IAM、bucket policy、FDB subspace ACL、Dragonfly auth/TLS、ClickHouse 审计表防篡改。
- CX6: 邮件恢复/passkey/WebAuthn 涉及 origin/rp_id、邮件投递、token URL 泄漏与 anti-phishing，但本轮未读取前端/邮件 runbook → 建议 Frontend/Auth UX 方向检查 WebAuthn rp_id、reset link Referrer-Policy、邮件模板反钓鱼、浏览器 key import/handoff UX。
