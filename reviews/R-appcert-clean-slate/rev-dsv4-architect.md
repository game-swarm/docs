# Architect Review — R-appcert-clean-slate

**Reviewer**: rev-dsv4-architect (DeepSeek V4 Pro)
**Date**: 2026-06-17
**Scope**: Clean-slate 全量评审，11 份目标设计文档
**Direction**: Architect — 架构一致性、边界划分、CA/CSR/证书链与联邦服务器总体模型

---

## Verdict: CONDITIONAL_APPROVE

架构方向正确，CA/CSR/应用层证书链模型本身无根本性缺陷。但发现 2 个 Critical 和 3 个 High severity 问题——均为文档间不一致和接口缺口，若不修正将导致实现阶段组件间认证失败或安全边界旁路。修正后进入实现。

---

## Top Findings

### C1 — Critical — Transport audience 格式在 5 处文档中互不兼容 [doc inconsistency]

`audience` 是跨 transport 重放防护的**安全边界字段**，不是标签。目前 5 处定义互不兼容：

| 位置 | audience 格式 |
|------|--------------|
| `design/auth.md:322` (canonical request payload) | `<world_id>@<gateway_origin>` |
| `design/auth.md:113` (issue_certificate_bundle) | `(server_id, world_id, gateway_origin)` |
| `design/auth.md:1016` (证书字段说明) | `server_id + world_id + gateway_origin` |
| `specs/security/03-mcp-security.md:114` (Agent cert) | `{server_id, world_id, "cli"}` |
| `specs/security/03-mcp-security.md:51` (cert fields) | `server_id + world_id + gateway_origin` |
| `specs/security/09-command-source.md:189-194` (transport table) | `mcp:{server_id}:{world_id}:{player_id}` 等带前缀格式 |

**影响**: 若签发端写 `world@gateway`，验证端期望 `mcp:server:world:player`，存储端存 `(server,world,gateway)`，正常请求将误拒或匹配过于宽松。过松的 audience 匹配是跨 transport 重放的常见根源。

**建议**: 选择一个权威 audience 语法并版本化，例如 `SWARM-AUD-V1:{transport}:{server_id}:{world_id}:{subject_id?}`，然后统一更新证书字段、请求签名 payload、Gateway matrix 和 SDK 示例。

---

### C2 — Critical — Gateway 协议文档仍以 JWT 作为 MCP 主认证路径 [doc inconsistency / security gap]

`specs/12-gateway-protocol.md:119` 明确写：
> `JWT 认证（mcp audience）`

这与 `design/auth.md` 的核心原则 "应用层证书强制路径" 直接矛盾。`specs/12-gateway-protocol.md:9` 的 Transport Auth Matrix 虽然也列出了 application certificate，但 §5 的 MCP 协议职责描述仍以 JWT 为中心。

**影响**: Gateway 是实现者最可能先看的入口文档。若 Gateway 侧按 JWT audience 做 MCP 主认证，后续 certificate audience、CRL、nonce、signature、federated local resign 全部被旁路。已知失败模式类似 OAuth/JWT 迁移到 mTLS/app-cert 时保留两套主路径，最后形成"安全设计在 auth 文档里，生产入口按 legacy token 放行"的双轨制。

**建议**: 将 `specs/12-gateway-protocol.md §5` 改为：MCP Agent 端点验证 `Swarm-Certificate-Chain` + canonical request signature + transport audience + nonce/timestamp。JWT 仅限 Browser Web session 兼容路径。

---

### H1 — High — `swarm_deploy_challenge` 在所有公开 MCP 工具表中缺失 [API gap]

`specs/security/09-command-source.md:99` 要求部署 nonce 通过 MCP tool `swarm_deploy_challenge` 获取，且 `swarm_deploy_challenge` 是部署验证流程的第 1 步（`specs/security/09-command-source.md:105`）。

但以下权威 MCP 工具表均未列出该 tool：

| 文档 | 缺失内容 |
|------|---------|
| `design/interface.md §4.1` (17-62 行) | 未列出 `swarm_deploy_challenge` |
| `design/auth.md §10.1` (608-629 行) | 未列出 |
| `specs/reference/mcp-tools.md` (18-25 行) | 未列出 |
| `GETTING-STARTED.md:76` | 直接 `swarm_deploy(module_bytes, wasm_signature)` |

**影响**: 新人或 SDK 作者会自然实现成 `swarm_deploy(wasm, signature)` 一步式接口，导致 nonce 生命周期、pending deploy token、IP/audience binding 落空。部署防重放完全失效。

**建议**: 将 `swarm_deploy_challenge` 加入所有 MCP tool 表，或将 nonce 签发合并进 `swarm_deploy` 作为两阶段操作并显式文档化。

---

### H2 — High — Auth Service 部署位置模糊: "Engine 内或独立服务" [architectural ambiguity]

`design/auth.md:63` 写 `src/auth/ (Engine 内或独立服务)`，§3.1 又说 "Auth 可位于 Engine 进程内（模块调用）或独立服务（内部 RPC）"。

这不是语法问题——它直接影响：

1. **Intermediate CA 私钥存放位置**：若 Auth 在 Engine 进程内，Engine 进程持有 Intermediate CA 私钥，攻击面扩大
2. **服务拓扑**：`RUNBOOK.md` 的启动序列未包含独立 Auth Service
3. **故障域**：Engine crash = Auth 不可用 vs Engine crash ≠ Auth 不可用
4. **Phase 1 实现表**（`auth.md:1207`）全部列在 `src/auth/`，暗示 in-process，但未明确

**建议**: 明确决定 Auth Service 部署拓扑。若 in-process，文档化 Intermediate CA 私钥的进程内保护策略。若独立服务，更新 RUNBOOK 启动序列、Gateway 路由和部署架构图。

---

### H3 — High — DeployPayload 结构在 auth.md / 09-command-source.md / interface.md 之间不一致 [API gap]

| 文档 | Deploy 签名载荷 |
|------|----------------|
| `design/auth.md §5.4` | 仅提 `module_hash + metadata` 由 `CodeSigningCertificate` 签名 |
| `specs/security/09-command-source.md §3.2` | 完整 `DeployPayload`：domain, module_hash, player_id, world_id, module_slot, version_tag, deploy_nonce, expires_at, signature |
| `design/interface.md §4.2` | 无 DeployPayload 概念，`swarm_deploy(module_bytes, wasm_signature)` |
| `GETTING-STARTED.md:76` | `swarm_deploy(module_bytes, wasm_signature)` |

**影响**: auth.md 定义的签名粒度比 09-command-source.md 粗得多——缺少 domain 分隔符和 module_slot，跨协议重放风险升高。interface.md 和 GETTING-STARTED 的一步式接口完全不经过 nonce 验证。

**建议**: 以 09-command-source.md 的 `DeployPayload` 为权威结构，统一更新 auth.md §5.4、interface.md 和 GETTING-STARTED.md。

---

### M1 — Medium — WASM 沙箱 spec 未引用证书验证流程 [doc inconsistency]

`specs/core/04-wasm-sandbox.md` 完整描述了 sandbox worker 的 OS 隔离、Wasmtime 配置、模块校验，但未描述 sandbox 接收的 `player_id` 如何从应用层证书链认证而来。Engine 侧的 `CertificateVerifier`（`auth.md:76`）与 Sandbox Worker 之间缺少架构连线。

**建议**: 在 `04-wasm-sandbox.md` 中添加一段 "认证上下文注入"，说明 Engine 在 fork sandbox worker 前已验证证书链并将 `player_id` + `scope` 注入 sandbox 上下文，sandbox 不参与验证。

---

### M2 — Medium — RUNBOOK CLI 工具未经设计文档定义 [doc inconsistency]

`RUNBOOK.md:96-109` 列出了运维 CLI 工具：`swarm ca root init`、`swarm ca intermediate issue`、`swarm ca fingerprint`、`swarm cert revoke`、`swarm key revoke`。这些工具在 `design/auth.md`、`design/interface.md`、`specs/reference/mcp-tools.md` 中均未定义其接口契约。

**建议**: 在 `specs/reference/` 中补充 CA 管理 CLI 的接口规范，或在 `design/auth.md` 中增加运维工具契约章节。

---

### M3 — Medium — auth.md §10.5 自引用错误 [doc inconsistency]

`design/auth.md:693`：
> 服务端按 **§5.4** 验证证书链、usage、scope、audience、nonce 和签名。

§5.4 是 "代码签名证书过期语义"，正确的引用应为 **§5.6** "Canonical Request Signature"（`auth.md:299-330`）。

---

### M4 — Medium — 联邦 CRL 传播仅有拉取模型，无推送/通知机制 [deferred implementation concern]

`design/auth.md §15.6` 的撤销传播完全是 polling-based：定期查询 `GET /auth/revocations?since=<timestamp>`。对于紧急吊销（如 Intermediate CA 泄露），轮询间隔 + stale cache 窗口可达 3600 秒。虽然 `revocation_fallback` 的三种策略设计了降级行为，但缺少主动推送机制（如 federation event push via NATS）。

**建议**: 在 `specs/future/` 或 auth.md 中注明联邦 CRL push 作为 Tier 2 增强，并确认 Tier 1 的 polling-only 延迟在运维 SLI 内可接受。

---

### L1 — Low — `swarm_cancel_account_deletion` 在 interface.md 中缺失

`design/auth.md §10.1` 列出了 `swarm_cancel_account_deletion`，但 `design/interface.md §4.1` 的认证工具表中没有。`specs/reference/mcp-tools.md` 也缺失。

---

### L2 — Low — CodeSigningCertificate 在 04-wasm-sandbox.md 的编译缓存键中引用但未解释验证流程

`specs/core/04-wasm-sandbox.md:338` 的缓存键包含安全上下文但 "编译仅跳过，验证不跳过" 的说明未引用证书验证的具体流程。

---

## Strengths

1. **控制面分离**: Auth 作为独立控制面，Engine 只 `CertificateVerifier` 消费已签发身份——职责边界清晰
2. **离线 Root CA + 在线 Intermediate CA**: 经典两层 PKI 模型，Root CA 私钥离线保护，Intermediate CA 可轮换吊销——教科书级正确
3. **用途隔离证书**: `ClientAuthCertificate` / `CodeSigningCertificate` / `AdminCertificate` / `FederationCertificate` 分用——防止凭据混淆和权限提升
4. **代码签名证书过期语义** (`auth.md §5.4`): 部署时检查，过期不影响已部署模块——消除了"证书过期 → 世界停止"的单点故障
5. **联邦本地重签** (`auth.md §15.5`): 远端证书只作 bootstrap proof，目标服始终签发本地证书——防止远程 CA 越权
6. **PoW 服务端权威 challenge** (`auth.md §9.3`): 客户端不回传 challenge/difficulty，从 FDB 读取服务端权威值——防降级攻击设计正确
7. **Transport audience 绑定** (`09-command-source.md §7.0`): 证书绑定 transport，Agent cert 不能用于 Browser WS——防跨协议凭据重放
8. **多设备证书生命周期** (`auth.md §5.5`): 每设备独立证书、独立吊销、不互相影响——运维粒度恰当
9. **Canonical request signature** (`auth.md §5.6`): body_hash + timestamp + nonce + certificate_id——防篡改 + 防重放
10. **Agent 代理注册安全交付** (`auth.md §4.3`): 一次性 handoff code 而非裸私钥/refresh_token——防聊天日志泄露

---

## Consistency Gaps (跨文档差异汇总)

| # | 主题 | 文档 A | 文档 B | 差异 |
|---|------|--------|--------|------|
| G1 | audience 格式 | `auth.md:322` → `<world_id>@<gateway_origin>` | `09-cmd:189` → `mcp:{s}:{w}:{p}` | 无法互操作 |
| G2 | MCP 认证机制 | `12-gateway:119` → JWT | `auth.md §14.5` → 应用层证书链 | 双轨制风险 |
| G3 | `swarm_deploy_challenge` | `09-cmd:99` → 存在且必须 | `interface.md §4.1` → 不存在 | 部署流程不可执行 |
| G4 | DeployPayload 结构 | `09-cmd §3.2` → 完整 9 字段 | `auth.md §5.4` → 仅 `module_hash+metadata` | 签名粒度不同 |
| G5 | Auth Service 拓扑 | `auth.md:63` → in-process 或独立 | `RUNBOOK.md` → 未包含 Auth Service | 部署不可操作 |
| G6 | `swarm ca` CLI | `RUNBOOK.md §2` → 存在 | `auth.md §18` → 未定义 | 无接口契约 |

---

## Algorithmic Risks

1. **Nonce 存储膨胀** (`auth.md §5.6` + `auth.md:422`): canonical request nonce 以 `auth/request_nonce/<certificate_id>/<nonce>` 存储。长 TTL 证书（180 天）在高频调用下积累大量 nonce。建议明确 nonce 清理策略（按时间窗口 TTL 自动过期清理）。

2. **联邦 CRL 拉取风暴** (`auth.md §15.6`): 多世界联邦在高频部署场景下，每个 deploy 触发一次远端 CRL 拉取。建议增加 CRL 缓存层和缓存 TTL 显式文档化。

3. **PoW difficulty_bits 对移动端不友好** (`auth.md §9.2`): 默认 difficulty_bits=24 在移动端 WASM 约需 3 秒。对首次用户体验有影响，但可通过动态 difficulty negotiation 缓解——该机制未在文档中出现。

---

## Questions / Assumptions

1. **`gateway_origin` 的语义**: 它是证书 audience 的一部分、请求 audience 的一部分、两者都是、还是仅用于 pinning/display？当前文档暗示多种用法，需明确。
2. **Intermediate CA 轮换策略**: auth.md §3.1 说 "定期轮换并可被 Root CA 吊销"，但未指定轮换周期和轮换期间的证书兼容窗口。假设轮换窗口 > 最长证书 TTL。
3. **离线 Root CA 的备份与灾难恢复**: RUNBOOK 有 FDB 备份恢复但无 Root CA 私钥的备份恢复流程。假设运维方自行管理。
4. **`swarm_deploy_challenge` 是否存在**: `09-command-source.md` 依赖它，但 public API docs 中不存在。需明确决策：独立 MCP tool 或 internal to `swarm_deploy`。
5. **AdminCertificate 的双签机制**: auth.md §5.3 说 "敏感操作可要求双签"，§5.4 未进一步展开。假设双签是 Phase 2 而非 Phase 1 范围。

---

## Summary

- **Verdict**: CONDITIONAL_APPROVE
- **Findings**: 2 Critical / 3 High / 4 Medium / 2 Low = 11 total
- **Consistency gaps**: 6 处跨文档不一致
- **Algorithmic risks**: 3 处（nonce 膨胀、CRL 拉取风暴、PoW 移动端体验）
- **Strengths**: 10 项架构亮点

CA/CSR/证书链与联邦模型的总体架构设计方向正确，无根本性缺陷。Critical 和 High 问题集中于**文档间接口一致性**和**公开 API 缺口**——这些问题在实现前修正成本低，实现后修正将涉及多处代码重构。建议优先解决 C1 (audience 统一)、C2 (Gateway 去 JWT)、H1 (补全 MCP tool 表)，然后进入实现。
