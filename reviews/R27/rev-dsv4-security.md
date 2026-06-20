# R27 Security Review — DeepSeek V4 Pro

> **Reviewer**: rev-dsv4-security (Security direction, primary)
> **Model**: deepseek-v4-pro
> **Reviewed**: 9 files / ~28K tokens
> **Date**: 2026-06-20

---

## Verdict: CONDITIONAL_APPROVE

Design is security-sound at the architectural level with well-defined trust boundaries, multiple-layer sandboxing, and systematic oracle defenses. 3 High findings require resolution before implementation; none are blocking at the design layer.

---

## Findings

### Critical
(None)

### High

#### H1 — CodeSigningCertificate TTL 双值冲突

**Location**: `design/auth.md` §5.3 vs §14.1

§5.3 用途隔离证书表:
> `CodeSigningCertificate` | TTL: **30–180 days**（默认 30d，world.toml 可配）

§14.1 Token 生命周期表:
> `CodeSigningCertificate` | TTL: **15 min–180 days**

**分析**: lower bound 冲突 (30d vs 15min)。15min 下限会导致代码签名证书频繁过期，玩家每次部署都需续签——破坏可用性且与 §5.4「证书自然过期不影响已部署模块继续运行」的设计意图矛盾。§5.4 的语义只对 ≥30d 的 TTL 有意义：如果证书在提交部署时要求有效，15min TTL 意味着从证书签发到部署提交必须在 15min 内完成，这对 AI agent 异步工作流不现实。

**建议**: 统一采用 §5.3 的 30–180 days。§14.1 为编辑错误，应改为与 §5.3 一致。

---

#### H2 — Refresh Token Rotation Grace 竞态 + 家族吊销 DoS

**Location**: `design/auth.md` §14.1

> 旧 token 在 rotation 后 60s 内仍可被接受一次（grace period，防竞态）
> 异常 IP/UA 使用 grace 时触发 session family revoke（该用户所有 session 吊销）

**分析**: Grace period 的设计目标（防竞态）与家族吊销（安全）之间存在张力：

1. **重放窗口**: 60s grace 允许被盗 token 在被 rotation 后仍被接受一次。虽然触发了整个 session family 吊销，但攻击者已成功获得新 token（旧 token 的 grace 使用会签发新 token）。

2. **DoS 向量**: 若攻击者间歇性地在 60s 窗口内使用被盗旧 token，每次都会触发 session family 全量吊销——造成合法用户持续被踢出。每个受害 token 在 30d TTL 内都是可重放的武器。

3. **受信/非受信区分未被充分验证**: "受信设备（已持有有效 ClientAuthCertificate）的 grace 缩短至 10s"——但 `ClientAuthCertificate` 本身可能在同一攻击中被盗（例如同一设备被 compromise）。区分标准（仅凭是否持有证书）不足以保证安全。

**建议**: 
- Grace period 的 nonce 使用应在 **FDB 事务内**原子执行（当前仅说「原子消费：FDB 中设置 grace_consumed_at」，但未明确是 FDB 事务 vs Dragonfly）
- 考虑将 grace 限制为「同一 IP + 同一 UA + 同一 client_public_key」三重绑定，而非仅区分受信/非受信
- 文档化 grace 触发的家族吊销频率上限（如每小时最多 1 次），防止 DoS 循环

---

#### H3 — CRL 吊销延迟默认值过高

**Location**: `design/auth.md` §10.8

> 证书吊销状态 (CRL) | 允许延迟: 60s（明确接受的风险：吊销后至多 60s 旧证书仍可被接受。竞争性世界可配置为 5-10s）

**分析**: 60s 默认值对 competitive world 过高。在 competitive 场景下，60s 足够攻击者部署恶意 WASM 模块并被引擎接受执行。虽然「竞争性世界可配置为 5-10s」已记录，但：

1. 默认值应为安全侧（更短延迟），由服主选择放宽——当前默认是宽松侧
2. `auth.md` §10.8 表格没有说明 **默认值**是 60s 还是由 world 模式决定
3. CVE-SLA.md Critical 级别要求 24h 响应——CRL 吊销延迟应该是秒级，不应与漏洞修补 SLA 差距 3 个数量级

**建议**: 
- Competitive world 默认 CRL 延迟设为 **5s**（已记录可配，需改为默认）
- World 模式可保留 60s 默认（持久世界容忍度更高）
- `world.toml` 验证：若 `competitive=true` 且 `crl_cache_ttl > 10` → 警告（非拒绝，留给服主选择）

---

### Medium

#### M1 — `host_path_find` cache_miss_penalty 未量化

**Location**: `specs/core/04-wasm-sandbox.md` §8

> `host_path_find` | 500 × explored_nodes + 200 × expanded_edges + **cache_miss_penalty**

`cache_miss_penalty` 无具体数值。恶意 WASM 可通过构造交替查询（A→B, C→D, A→B, C→D...）持续触发 cache miss，使实际 fuel 消耗超过预算模型假设。若 penalty 被实现为固定值（如 500 fuel），攻击者可精确控制 miss 模式最大化消耗。

**建议**: 量化 `cache_miss_penalty` 为固定值（如 2000 fuel），并在 API Registry §4.4 表中补充此值。

---

#### M2 — cgroup `pids.max` 双值

**Location**: `specs/core/04-wasm-sandbox.md` §4.2 vs §9.1

- §4.2 cgroup v2: `pids.max = 32`
- §9.1 统一 OS 加固表: `pids.max = 16`

**分析**: 同一文档内 cgroup 参数不一致。32 → 16 的差异影响安全边界（更少线程 = 更少并行攻击面），实施时必须统一。

**建议**: 以 §9.1 (16) 为准，§4.2 同步修正。理由是 worker pool 模型不需要 32 个线程；Wasmtime 编译线程数应被限制。

---

#### M3 — 联邦 CRL 同步失败时 login 仍允许

**Location**: `design/auth.md` §15.2a

> `reject_for_code` | 若 CRL 超过 2× 同步间隔未更新，拒绝该远程世界的 CodeSigningCertificate；仍允许 login

**分析**: 若远程世界被 compromise 且 CRL 同步中断（攻击者主动切断），本地世界仍允许 login——攻击者可持有远程世界签发的有效证书登录本地世界，获得 `ClientAuthCertificate` 后执行查询、调试等操作。虽然不能部署代码（`reject_for_code`），但 `swarm:read swarm:debug` scope 允许信息收集。

**建议**: `reject_for_code` 改为在 CRL 过期时也阻止 login，升级为新策略 `reject_for_code_and_login`。当前 `reject_for_code` 作为默认值风险较高。

---

#### M4 — Admin 验证放宽范围未明确

**Location**: `specs/security/09-command-source.md` §2.3

> Admin 路径统一：Admin 命令走标准 validate_and_apply() 管线，仅 RejectionReason 阈值放宽（Admin 可操作任意玩家的实体，所有权检查放宽）

**分析**: "所有权检查放宽"的范围需要精确界定：
- 是否包括绕过 `is_visible_to` 检查？如果是，则 admin 可获得全量世界信息——这应该是 `swarm:admin` scope 的预期行为，但需显式声明。
- 是否包括绕过 `cooldown` / `safemode` 检查？如果是，admin 可在 safe mode 内操作——可能破坏游戏公平性保证。
- 编译期 `WorldMutate` trait 防止绕过——这是很好的设计，但 trait 本身不限制「修改了什么」。
- API Registry 中 admin 工具的 `Required Scope` 和 `Replay Class` 列已标注，但 admin 在执行路径上的 **精确豁免项** 未在 command-source.md 中列出。

**建议**: 在 `09-command-source.md` §2.3 增加 admin validation 豁免的显式枚举表（哪些 RejectionReason 对 admin 不适用），而非「阈值放宽」的模糊描述。

---

### Low

#### L1 — WASM 输出 JSON 256KB 上限在 `tick()` 返回非零时仍检查

**Location**: `specs/core/04-wasm-sandbox.md` §3.1

> tick() 返回非 0 → 视为执行失败，当 tick 0 指令

若 `tick()` 返回非 0 但已通过 shared memory 写入了部分 JSON 到 result buffer，引擎是否正确清理/忽略？当前描述只说了「0 指令」但没有明确 buffer 清理语义。若未清理，buffer 内容可能被下一 tick 的 alloc/free 周期意外读取（WASM 线性内存复用）。

**建议**: 明确 `tick()` 返回非 0 时引擎**不读取** result buffer，直接重置 Store（清空线性内存）。

---

#### L2 — `auth/cert_audit` 不记录请求源 IP

**Location**: `design/auth.md` §3.1

签发审计记录字段: `player_id, public_key_id, usage, issued_at, issuer, scopes, ttl`。缺少 IP 地址。虽然 MCP 审计日志 (`mcp_audit` 表) 会记录 IP，但证书签发是一个独立的安全事件——将 IP 关联到具体证书的签发记录用于事后取证有价值。

**建议**: 添加 `source_ip` 字段到 `auth/cert_audit`。

---

#### L3 — Browser Spectator WS 无 per-message 认证

**Location**: `specs/security/03-mcp-security.md` §2.5

> 公开 spectator WS 端点不接受 Swarm-Certificate-Chain 头部，不执行证书握手
> 无 per-message 签名要求

虽然是只读推送，但在 DNS rebinding 场景下：若攻击者通过 rebinding 将 spectator WS 连接重定向到 loopback 上的内部服务，spectator WS 连接会成为 SSRF 隧道。当前防御（`Host` header 检查、拒绝 private IP redirect）覆盖了大部分场景，但未认证的 WS 连接本身的 bare socket 一旦建立，即可承载任意数据。

**建议**: 已知风险，当前网络层防御充足。可考虑 spectator WS 在 connect 阶段验证 `Sec-WebSocket-Protocol` 包含特定子协议标识。

---

#### L4 — CSR 提交 `challenge_id` 与 CSR payload 内 `challenge_id` 双重来源

**Location**: `design/auth.md` §9.3 vs §5.2

- §9.3: `swarm_submit_csr` 参数包含 `challenge_id`（JSON-RPC param）
- §5.2: CSR payload 内也包含 `challenge_id` 和 `challenge`

服务端验证 flow 使用 `params.challenge_id` 从 FDB 读取权威 challenge。但 CSR payload 内的 challenge 字段被忽略——客户端仍可填任意值。虽然这不导致安全漏洞（服务端从 FDB 读取权威值），但攻击者可能通过填充超长/畸形 CSR challenge 字段触发解析侧信道或内存压力。

**建议**: 服务端在解析 CSR 后校验 `challenge_id` 与 `params.challenge_id` 一致。不一致 → 拒绝（防止协议混淆）。

---

## Bright Spots

1. **Auth Service / Engine 职责分离** — Auth Service 独立进程持有签名能力，Engine 仅验证信任链。`Server Root CA` 离线、`Intermediate CA` 在线轮换、HSM 要求、启动强制检查——完整的 CA 安全 lifecycle。

2. **多层沙箱** — seccomp BPF + cgroup v2 + Wasmtime fuel metering + wasmparser 预校验 + StartSection 拒绝 + 恶意样本 CI。纵深防御设计优秀。特别是「不依赖 Wasmtime 的模块校验来做安全决策——wasmparser 预检在 Wasmtime 之外先行」。

3. **Oracle 防线系统化** — `is_visible_to` 单函数、`omitted_count` 分桶、`NotVisibleOrNotFound` 合并码、特殊攻击拒绝码等价类、`dry_run/simulate` 脱敏——全面且一致。

4. **反枚举措施** — dummy argon2id、`username_visibility` 配 private、登录失败统一 `invalid_credentials`、邮箱恢复统一返回成功——防止用户存在性泄漏。

5. **Deploy 防重放** — `version_counter` 在 FDB 事务内原子递增，不依赖对象存储 blob 可用性。`deploy_mutation` replay class 以 `fdb_version_counter` 全序重放。

6. **PoW 抗降级** — 客户端不提交 challenge/difficulty，服务端从 FDB 读取权威值。即使客户端回传错误值也不影响验证。

7. **CVE SLA 覆盖关键 crate** — 不只是 Wasmtime，还包括 `blake3`, `ed25519-dalek`, `ring`, `rustls`, `tokio` 等。回滚策略明确，staging 灰度发布。

8. **Admin 双签** — 回滚、恢复链接生成需双 admin 确认，审计日志记录双方。

9. **Agent 代理注册安全** — handoff code 而非裸 token，私钥归属明确合同（托管/自管两种模式），聊天日志脱敏。

10. **WASM Deferred Command Model** — 所有写操作通过 `tick() → JSON commands` 延迟执行，沙箱内只暴露只读 host function。无直接 world mutating 路径。

---

## CrossCheck

以下问题超出现有 Security 文档范围，建议跨方向检查：

- **CX1: `version_counter` vs `fdb_version_counter` 命名冲突** → 建议 Architect 检查
  `design/auth.md` §10.8 和 `09-command-source.md` §7.3 的 `version_counter` 是 per-player/per-slot 单调计数器（DeployPayload 字段）。`specs/reference/api-registry.md` §11 的 `fdb_version_counter` 是 deploy manifest 的 FDB 事务计数器。两者命名相似但语义不同——验证所有部署流文档中命名一致。

- **CX2: 三层 drone cap (per-player 50 / per-room 500 / global 10000) 一致性** → 建议 Architect 检查
  API Registry §5.1 声明了此三层 cap 并引用 "R23 D2/B"。验证 `design/engine.md` 和 `design/gameplay.md` 中此模型的文档一致性。

- **CX3: Replay-Critical subset 与 TickTrace Envelope 的 deploy_events** → 建议 Architect 检查
  `05-persistence-contract.md` §2.1 的 replay-critical fields 包含 `deploy_activation_decision`（#8），但 API Registry §6 TickTrace Envelope 包含 `deploy_events`（#8）。验证 deploy 事件在 FDB commit 和 TickTrace 中的表示一致性。

- **CX4: Admin 工具 `swarm_admin_rollback` 的 replay 一致性** → 建议 Architect 检查
  `09-command-source.md` §8.2 说 "Replay 不重新编译 WASM、不重新执行 tick()"。但 rollback 后 replay 如何处理 rollback 边界？rollback 的 tick 范围是否可 replay？建议 Architect 在 engine.md 中明确 rollback tick 的 replay 语义。

- **CX5: `swarm_get_docs` 和 `swarm_get_schema` 的信息泄露面** → 建议 Designer 检查
  API Registry 中这两个工具的 `visibility_filter` 为 `none`（无可见性过滤）。若返回的文档/ schema 包含世界特定配置信息（如经济参数、模组列表），可能泄露超出 `is_visible_to` 范围的数据。建议 Designer 验证这两个工具的输出不包含 per-world 敏感配置。

- **CX6: Economy operations 的 fuel 成本** → 建议 Performance 检查
  Economy operations (StorageTax, UpkeepDeduction, RecycleRefund 等) 是引擎侧计算，不消耗玩家 fuel。但 PvEAward、AlliedTransfer 可能涉及大量玩家间的资源流动。建议 Performance 评估最坏情况下的 tick 计算成本。

---

*审查完成。3 High / 4 Medium / 4 Low / 10 Bright Spots / 6 CrossChecks。*