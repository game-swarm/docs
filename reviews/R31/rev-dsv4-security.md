# R31 Security 独立评审报告

**评审人**: rev-dsv4-security (DeepSeek V4 Pro)
**评审范围**: 
- `/tmp/swarm-review-R31/design/README.md` — 系统架构概览
- `/tmp/swarm-review-R31/design/auth.md` — 用户认证系统 (1824行)
- `/tmp/swarm-review-R31/specs/reference/api-registry.md` — API 权威注册表
- `/tmp/swarm-review-R31/specs/security/03-mcp-security.md` — MCP 接口安全
- `/tmp/swarm-review-R31/specs/security/05-visibility.md` — 统一可见性策略
- `/tmp/swarm-review-R31/specs/security/09-command-source.md` — 指令来源模型
- `/tmp/swarm-review-R31/specs/security/CVE-SLA.md` — CVE 响应 SLA
- `/tmp/swarm-review-R31/specs/core/04-wasm-sandbox.md` — WASM 沙箱基线
- `/tmp/swarm-review-R31/specs/core/05-persistence-contract.md` — 持久化合同

---

## 1. Verdict

**REQUEST_MAJOR_CHANGES**

存在 2 个 Critical 跨文档一致性缺陷（编译缓存键不一致可导致沙箱逃逸；audience 格式分歧可导致证书验证失败）和 3 个 High 问题。这些问题阻碍安全合同闭合，必须在合并前修复。

---

## 2. 发现的问题

### Critical

#### C1: 编译缓存键定义跨文档不一致 — 可导致模块编译输出混用

- **文件**: `specs/core/04-wasm-sandbox.md` §1 (行41) + §7 (行343) vs `specs/security/09-command-source.md` §3.5 (行135)
- **问题描述**:
  - `04-wasm-sandbox.md` 两处定义编译缓存键为: `Blake3(module_hash || wasmtime_build_commit || wasmparser_version || validation_policy_version || target_arch || security_epoch)` — **包含 `module_hash`**
  - `09-command-source.md` §3.5 定义为: `blake3(wasmparser_version || validation_policy_version || wasmtime_build_commit || target_arch || security_epoch)` — **缺少 `module_hash`**
- **影响分析**: 若按 `09-command-source` 的版本实现（缓存键不含 `module_hash`），两个不同 WASM 模块在相同工具链版本下将共享同一个编译缓存条目。第二个模块会跳过编译，直接使用第一个模块的已编译原生码。这与部署时验证 `module_hash` 形成致命缺口——验证只检查 WASM 二进制，不检查已编译的输出归属。模块 B 的 drone 将实际执行模块 A 的编译产物。
- **安全边界**: WASM 沙箱隔离 → **突破** (跨模块代码执行)
- **修复建议**: 统一为 `04-wasm-sandbox` 版本（包含 `module_hash` 为第一组件）。同时在 CI 中添加跨文档一致性校验——`09-command-source` §3.5 的缓存键定义必须与 `04-wasm-sandbox` §7 的缓存键定义逐字一致。

#### C2: Audience 字符串格式三重不一致 — 签名验证存在失败风险

- **文件**: `design/auth.md` §5.6c vs §7.0 vs §10.8; `specs/security/03-mcp-security.md` §2.1 vs §2.2
- **问题描述**:
  1. **Canonical Request 签名 payload** (`auth.md` §5.6c, 行371): audience 格式为 `"transport:server_id:world_id:player_id"` — **不含 `swarm-aud-v1:` 前缀**
  2. **Audience 规范语法** (`auth.md` §10.8, 行923): 格式为 `swarm-aud-v1:<transport>:<server_id>:<world_id>:<subject_id>` — **含 `swarm-aud-v1:` 前缀**
  3. **证书 audience** (各处): 格式为 `swarm-aud-v1:<transport>:<server_id>:<world_id>:<player_id>` — 含前缀
  4. **Transport 枚举值不统一**:
     - `auth.md` §10.8 列出的 transport: `browser-http | browser-ws | agent-mcp | cli-rest | replay-viewer`
     - `auth.md` §7.0 Transport 表: MCP (Agent) 使用 `agent-mcp`
     - `03-mcp-security.md` §2.2 Agent/CLI: 使用 `cli-rest`
     - 即 `03-mcp-security` 将 Agent MCP 端点标注为 `cli-rest` transport，而 `auth.md` §7.0 标注为 `agent-mcp`
- **影响分析**: 
  - 签名 payload audience (`"transport:server_id:world_id:player_id"`) 与证书 audience (`swarm-aud-v1:...`) 格式不同，验证步骤 §5.6c 第5步 "audience/world_id 匹配" 无法通过简单字符串比较完成——必须实现隐式的格式转换逻辑。这种隐式合同是安全漏洞的温床。
  - Transport 枚举不一致意味着 `03-mcp-security` 描述的 Agent 连接携带 `audience=swarm-aud-v1:cli-rest:...`，而 `auth.md` §7.0 定义的 MCP 端点是 `swarm-aud-v1:agent-mcp:...`。Gateway 按 `auth.md` §7.0 规则验证时，`cli-rest` 不匹配 `agent-mcp` → 拒绝所有 Agent MCP 请求。
- **修复建议**:
  - 统一 canonical request 签名 payload 中的 audience 格式为完整 `swarm-aud-v1:<transport>:<server_id>:<world_id>:<player_id>`
  - 统一 transport 枚举：确认 Agent MCP 端点使用 `agent-mcp` 还是 `cli-rest`，在全量文档中一致使用
  - 在 `auth.md` 中新增一个唯一的 "Canonical Audience Format" 权威声明小节，所有其他文档引用此处

### High

#### H1: Sandbox Store Reset 规范缺失 — 跨 tick 状态泄漏风险未书面闭合

- **文件**: `specs/core/04-wasm-sandbox.md` §1 (行41-44); `specs/security/CVE-SLA.md`
- **问题描述**: `04-wasm-sandbox` §1 描述 "per-tick Store reset" 时仅罗列了 "清空 WASM 线性内存、重置 fuel counter、epoch deadline"。以下 critical reset 行为未明确书面化:
  - **Global/Table/Element 重置**: WASM 模块可能有 mutable globals 或 table 条目在 tick 间残留
  - **Host function 闭包状态重置**: host functions 通过 `wasmtime::Func::wrap` 注入时可能携带可变捕获
  - **WASI context 重置**: 即使 WASI 禁用了大部分功能，`WasiCtx` 内部状态（如环境变量缓存）在 Store reset 时是否完全清空
  - **Store 级 epoch deadline 重置**: epoch interruption 的 deadline 在 Store reset 后是否正确重置为新值
- **影响分析**: 若以上任何一项未在 Store reset 中正确清空，一个 tick 的执行可能向后续 tick 泄漏状态，破坏沙箱隔离。特别是在 worker pool 复用模型下（同一进程跨 tick 复用），状态泄漏风险更高。
- **修复建议**: 在 `04-wasm-sandbox` §1 新增 "Store Reset — Complete Checklist" 小节，逐项列出: linear memory (已覆盖), globals, tables, elements, host function closures, WasiCtx, fuel counter (已覆盖), epoch deadline (已覆盖), signal handlers。每项标注 reset 机制和验证方式。

#### H2: Canonical Request 签名 payload 中 audience 格式与验证逻辑不匹配

- **文件**: `design/auth.md` §5.6c (行360-402)
- **问题描述**: 见 C2 的细分 (1)。签名 payload audience 为 `"transport:server_id:world_id:player_id"`（不含 `swarm-aud-v1:` 前缀），而证书中 audience 为 `swarm-aud-v1:<transport>:<server_id>:<world_id>:<player_id>`。验证步骤第5条 "audience/world_id 匹配" 未定义匹配逻辑——是字符串精确匹配、还是前缀剥离后比较、还是字段级结构化比较。
- **影响分析**: 若实现采用字符串精确匹配，签名验证将系统性地失败（audience 格式不匹配），导致所有认证请求被拒。若采用宽松的隐式比较，攻击者可能构造跨 transport 的 audience 绕过——例如将在 `agent-mcp` transport 下签发的证书签名用于 `browser-ws` 连接。
- **修复建议**: 将 canonical request 签名 payload 中的 audience 字段统一为 `swarm-aud-v1:<transport>:<server_id>:<world_id>:<player_id>` 格式，并在验证步骤中明确定义: "验证时，签名 payload audience 与证书 audience 必须逐字节精确匹配。Gateway 同时验证 audience 中 `<transport>` 与实际连接 transport 一致、`<server_id>` 与当前服务器一致、`<world_id>` 与当前世界一致。"

#### H3: Agent MCP transport 枚举在 03-mcp-security 与 auth.md 间不一致

- **文件**: `specs/security/03-mcp-security.md` §2.2 vs `design/auth.md` §7.0 Transport 表
- **问题描述**: 见 C2 的细分 (4)。`03-mcp-security` §2.2 将 Agent MCP 端点的 certificate audience transport 标注为 `cli-rest`；`auth.md` §7.0 标注为 `agent-mcp`。
- **影响分析**: Gateway 按 `auth.md` §7.0 判定：收到 `X-Swarm-Transport: agent-mcp` header 时，期望 audience 包含 `swarm-aud-v1:agent-mcp:...`。若 Agent 按 `03-mcp-security` 构造 audience 为 `swarm-aud-v1:cli-rest:...`，Gateway 拒绝（`403 AudienceMismatch`）。Agent 玩家无法连接。
- **修复建议**: 选定一个 transport 值（建议 `agent-mcp`，与 `browser-ws` 等保持 `<client>-<protocol>` 命名一致性），在 `auth.md` §10.8 权威枚举表中定义，全量文档引用此权威表。`03-mcp-security` §2.2 更新 audience 示例。

### Medium

#### M1: Recovery PoW 默认关闭 — 分布式密码爆破面未充分缓解

- **文件**: `design/auth.md` §9.4 (行673-684)
- **问题描述**: `auth.recovery_pow.enabled = false` 默认关闭。恢复凭据校验仅依赖 per-IP 限流 (10/min) + per-username 限流 (10/min, 5次锁5min)。分布式攻击者（botnet, 100+ IP）可同时对 100 个不同 username 尝试恢复密码，不触发任何单 username 的锁。per-IP 限流对每个 IP 独立生效，100 个 IP 可达到 1000/min 的总尝试速率。
- **影响分析**: 虽然有 dummy argon2id（19MiB/次）作为服务端成本门槛，但攻击者可利用 cloud VM 并行发起。在 `recovery_pow.enabled = false` 时，防御完全依赖限流。建议将默认值改为 `true` 或至少 `difficulty_bits = 16` 的低难度 PoW（作为基础成本层，不显著影响合法用户）。
- **修复建议**: 将 `recovery_pow.enabled` 默认值改为 `true`，`difficulty_bits` 保持 16（~65K 尝试，<5ms Rust native）。补充文档说明: "生产环境推荐开启 recovery PoW；仅在低风险开发环境关闭。"

#### M2: `read_replay_safe` 请求 nonce 标记为可选 — 信息积累攻击面

- **文件**: `design/auth.md` §5.6a (行316-323)
- **问题描述**: `read_replay_safe` replay class 描述为 "可选 nonce，time window 校验"。即查询类请求（如 `swarm_get_snapshot`）的 nonce 不是必选的。攻击者可在 time window 内（默认 60s, 见 `auth.md` §5.7 行413）重放查询请求。
- **影响分析**: 对只读查询，重放不改变状态，但:
  - 攻击者可观察 time window 内的 snapshot 变化（如通过重放定时查询捕捉 drone 移动模式）
  - 重放可放大信息收集速率（绕过 per-tick rate limit——若 nonce 未强制，重放请求可能被计数为新请求）
  - 对 competitive world，这构成轻量级的信息不对称
- **修复建议**: 对 `fog_of_war=true` 的 competitive world，建议将 `read_replay_safe` 的 nonce 从 "可选" 改为 "强制 (60s TTL)"。nonce 消耗可在 Dragonfly 中实现（与 `idempotent_mutation` 一致），不显著增加延迟。对 tutorial/sandbox world 保持可选。

#### M3: WebSocket per-message MAC 缺少 tick 绑定 — 跨 tick 消息注入窗口

- **文件**: `specs/security/03-mcp-security.md` §2.5 (行159-165); `design/auth.md` §10.5a (行804-809)
- **问题描述**: Agent WS per-message MAC 覆盖 `SWARM-WS-MSG-V1\n<seq>\n<body_hash>`。序列号 `seq` 单调递增，接收方检查 `seq == last_seq + 1`。但 MAC 中**不包含 tick 编号**。
- **影响分析**: seq 机制防止了同一连接内的消息重排/重放。但若攻击者在 tick N 捕获了合法的 `(seq=5, MAC, payload)`，而连接由于网络抖动在 tick N+1 仍存活且 `last_seq` 恰好为 4，攻击者可注入该消息。更严重的是：若连接断开后重连（30s 内，见 `auth.md` §10.5a 行811 "WebSocket 断开后需重新握手"），seq 从 1 重新开始。攻击者可保存 tick N 的 `seq=1..k` 消息并在重连后重放——但重新握手应该重置状态。实际上 per-message seq 绑定到单个连接生命周期，重连后需重新握手，所以跨重连重放不可行。但在同一连接内的跨 tick 消息捕获+注入仍然可能。添加 tick 到 MAC payload 可提供 defense-in-depth。
- **修复建议**: 将 MAC payload 扩展为 `SWARM-WS-MSG-V1\n<tick>\n<seq>\n<body_hash>`，tick 值为消息产生时的逻辑 tick。接收方验证 tick 在合理窗口内（±1 tick）。

#### M4: Sandbox `relaxed` 模式守卫仅检查 `world.mode` — 可被 world.toml 误配置绕过

- **文件**: `specs/core/04-wasm-sandbox.md` §9.3 (行410-419)
- **问题描述**: 生产环境 `sandbox.relaxed = true` 的拒绝逻辑为 "引擎启动时检查配置，若为 true 且 `world.mode != \"development\"` → 拒绝启动"。但 `world.mode` 可在 `world.toml` 中配置——攻击者若能修改 world.toml（通过供应链攻击或配置管理漏洞），可将 `world.mode` 设为 `"development"` 并同时设置 `sandbox.relaxed = true`，从而放宽 sandbox 限制。
- **影响分析**: `relaxed` 模式允许 `clock_gettime`、`stderr` 输出、256MB 内存。结合 `relaxed` 开启，攻击者可通过 timing side-channel 探测更多宿主机信息。`stderr` 输出可泄露 sandbox 内部状态。
- **修复建议**: 增加编译期 flag 区分 dev/release 构建——release 构建中 `sandbox.relaxed` 被编译期无条件拒绝，无论 `world.mode` 值。`cargo build --release` 时此 flag 设为 `false` 且不可通过配置文件覆盖。`world.mode = "development"` 仅在 debug 构建中允许 `relaxed`。

### Low

#### L1: CVE 监控范围未显式覆盖 Rust stdlib 与核心生态

- **文件**: `specs/security/CVE-SLA.md` (行14-16)
- **问题描述**: Critical Rust crates 列表包含了 `blake3`, `ed25519-dalek`, `ring`, `rustls`, `tokio`, `serde`, `serde_json`, `wasmparser`, `cranelift-codegen`, `cap-std`, `nix`, `libc`, `crossbeam`, `parking_lot`，但未明确覆盖 Rust 标准库 (`std`) 和 Bevy ECS 框架。`std::collections::HashMap` 的 hash 算法变更可能破坏确定性；Bevy 的调度器行为变更可能影响 tick 执行顺序。
- **影响分析**: 低概率但高影响——标准库或核心框架出现破坏性安全修复时，可能未被及时识别。
- **修复建议**: 将 `std` 和 `bevy` 加入 Critical Rust crates 列表，明确其监控责任归属。

#### L2: World 模式 CRL 吊销缓存 60s 延迟 — 对安全事件响应偏慢

- **文件**: `design/auth.md` §10.8 证书吊销状态缓存 (行947)
- **问题描述**: World 模式下 CRL 缓存允许 60s 延迟，意味着证书吊销后最多 60s 内旧证书仍可被接受。对于 competitive Arena，延迟为 5s。
- **影响分析**: World 模式风险较低（持久世界，非竞技场景），但 60s 对于检测到正在进行的攻击（如证书私钥泄露）时响应偏慢。攻击者可在 60s 窗口内用已吊销证书提交大量恶意操作。
- **修复建议**: 为 World 模式增加 "security event" 快速路径：当吊销原因为 `key_compromise` 或 `intermediate_ca_compromise` 时，Engine 通过 push 通知（而非等待缓存 TTL）立即刷新该特定证书的缓存条目。

#### L3: Refresh token rotation grace period 逻辑跨受信/非受信设备不对称

- **文件**: `design/auth.md` §14.1 (行1264-1268)
- **问题描述**: `refresh_token` rotation 后旧 token 有 grace period——受信设备（持有有效 `ClientAuthCertificate`）grace 10s，非受信设备（仅 `refresh_token`）grace 60s。非受信设备的 grace 是受信设备的 6 倍。如果攻击者窃取了 `refresh_token`（非受信设备场景），他们有 60s 窗口使用旧 token，而合法用户的受信设备只有 10s 窗口。这不合理——非受信设备应有更短而非更长的 grace。
- **影响分析**: 攻击者窃取 `refresh_token` 后在 60s 内可发起请求，与合法用户的 token rotation 形成竞态。但由于 "异常 IP/UA 使用 grace 时触发 session family revoke"，此风险已有缓解。
- **修复建议**: 统一 grace 为 10s，或在文档中说明非受信设备 grace 更长的设计理由（如网络延迟/时钟偏差容忍度）。当前 6× 差异缺乏书面理由。

---

## 3. 亮点

1. **Oracle 防线闭合完整** (`05-visibility.md` §10): `omitted_count` 分桶脱敏、特殊攻击拒绝码等价策略（`NotVisibleOrNotFound`/`NotEligible`）、`dry_run`/`simulate` 脱敏——跨 MCP/snapshot/WS/replay 全部输出面的 oracle 防线系统性地闭合。`NotVisibleOrNotFound` 的统一返回码设计尤其优雅——攻击者无法通过错误码区分"目标不存在"与"目标不可见"。

2. **多维度 CSR Admission Control** (`auth.md` §10.7): 六层防护——PoW (L1) → Per-IP (L2) → Per-ASN (L3) → Global semaphore (L4) → Worker queue (L5) → Audit throttle (L6)。文档明确论证了"PoW 不能替代速率限制"的设计理由（分布式攻击者可利用并行计算绕过 PoW 难度），多层防护设计成熟。

3. **应用层证书 + 不安全传输可认证** (`auth.md` §5.7): Swarm CA 不进入系统 trust store，HTTP 等不安全传输可通过应用层证书完成身份认证和完整性校验。首次访问时的 TOFU pinning 设计实用且安全——人工确认 Server Root CA fingerprint 后写入客户端证书存储。

4. **Transport 拆分安全模型** (`03-mcp-security` §2): Browser (Origin + CSRF) vs Agent (应用层证书 + canonical signature) 的明确分离设计。DNS rebinding 防御表格（6 种攻击向量 + 对应防御）覆盖全面。

5. **确定性吊销结果** (`09-command-source` §8.3): 证书吊销按 reason 产生确定性结果——`key_compromise` → freeze, `device_lost` → continue, `intermediate_ca_compromise` → `paused_security`。Replay 使用记录事件，不重新评估吊销。这保证了安全事件在 replay 中的可重现性。

6. **Deferred Command Model** (`04-wasm-sandbox` §3): WASM 仅能输出 CommandIntent JSON，所有状态变更通过引擎统一校验后应用。WASM 中无 mutating host function——防御了 WASM 层面的任意状态写入。与 `is_visible_to` 过滤的 host functions 配合，形成双重防线。

---

## 4. CrossCheck

以下问题超出 Security 方向的独立判断范围，需跨方向协同审查：

- **CX-N1**: 编译缓存键不一致 (C1) 的直接风险在 sandbox 层（模块混用 → 沙箱逃逸），但根因是 `09-command-source` §3.5 的缓存键定义与 `04-wasm-sandbox` §7 的定义分歧。→ 建议 **Engine/Architecture** 方向检查: `09-command-source` §3.5 的编译缓存键定义是否为 R27 某次重构后的遗留错误？全量 `wasmtime::Module::from_binary` 调用点是否从同一缓存读取？是否存在其他子系统也定义了编译缓存键？

- **CX-N2**: Audience 格式三重不一致 (C2) 涉及 `auth.md`（认证）、`03-mcp-security`（MCP 安全）、`09-command-source` §7.0（transport 判定）。→ 建议 **Speaker/全方向** 检查: 是否存在一个 central "Canonical Audience Format" 权威源被遗漏？`03-mcp-security` 中 `cli-rest` 的使用是否因为该文档在 `auth.md` §7.0 transport 枚举更新前编写？建议由 Speaker 统一裁决 transport 枚举值。

- **CX-N3**: Sandbox Store Reset 的完整 checklist (H1) 是否在 `04-wasm-sandbox` 之外的文档中定义？→ 建议 **Engine/Architecture** 检查: Wasmtime `Store::reset()` 的 API 是否已在 wasmtime ≥30 版本中明确行为（globals/tables/elements/WasiCtx 的 reset 语义）？`engine/src/sandbox/` 代码中 Store reset 的实际实现是否覆盖了所有项目？

- **CX-N4**: Recovery PoW 默认值 (M1) 涉及 auth 安全性与用户体验的权衡——默认开启 low-difficulty PoW 是否会显著影响 player onboarding 体验？→ 建议 **Gameplay/UX** 方向评估: 16-bit PoW 在移动端 WASM 的 ~20ms 延迟是否可接受？或应保持 `false` 但增加 per-ASN 限流层？

- **CX-N5**: `read_replay_safe` nonce 强制化 (M2) 涉及 Dragonfly 负载评估——若所有只读请求强制 nonce，Dragonfly SETNX 写入量将增加 read_query_count × 1。→ 建议 **Infrastructure/Performance** 方向评估: 当前设计的 Dragonfly nonce 写入速率是否在 500-player × 50-read/tick 负载下可承受？是否需分片或采样？

- **CX-N6**: WebSocket per-message MAC 添加 tick 绑定 (M3) → 建议 **Engine/Architecture** 检查: 当前 Wasmtime Store 的 tick 编号是否在 sandbox worker 中可获取？跨 tick 消息在同一个 WS 连接内的时序是否可能（即 sandbox worker 在 tick N 处理完消息后，是否可能在同一连接内收到 tick N-1 的延迟消息）？