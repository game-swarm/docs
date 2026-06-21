# R34 Closure Verification — Security (DeepSeek V4 Pro)

## Verdict

**PARTIALLY_CLOSED**

5 项完全闭合 (B2 IDL+sandbox+host-fn 一致 / B4 auth_api.idl.yaml 重写完整 / B8 sandbox netns+Store reset checklist / S-H1 transport labels / D8 capability-gated / S-H10 no security_class)。3 项部分闭合 (S-H7 TTL 在 IDL↔Registry 一致但缺 auth.md 验证 / S-H6 cert-only 模型已建立但 03-mcp-security.md 不在验证范围 / S-H4/S-H5/S-H8 需 auth.md 验证不在当前文件集)。**1 项 GAP (S-H9 SWARM-DEPLOY-V1 未定义)**。**2 项 registry staleness (B2 fuel 成本 + B4 Auth RejectionReason codes 在 api-registry.md 中未更新)**。

---

## 逐项验证

### B2: host_get_random 核心 ABI — PARTIALLY_CLOSED

| 检查维度 | game_api.idl.yaml | api-registry.md | host-functions.md | 04-wasm-sandbox.md |
|---------|:---:|:---:|:---:|:---:|
| 函数注册 | ✅ §4 index=6 (行 1613) | ✅ §4.1 #6 (行 474) | ✅ 行 62 | ✅ §3.2 (行 221) |
| ABI 签名 `(sequence: u32, ...)` | ✅ 行 1615 | ✅ 行 474 | ✅ 行 64 | ✅ 行 221 |
| Seed 语义 | ✅ 行 1618 | ✅ 行 476 | ✅ 行 66 | ✅ 行 221 |
| 输出上限 256 bytes | ✅ 行 1619 | ✅ §4.3 行 499 | ✅ 行 68 | ✅ §8 行 378 |
| Per-tick 上限 10 | ✅ 行 1624 | ✅ §4.2 行 487 | ✅ 行 70 | ✅ §6 行 325 |

**GAP: Fuel 成本跨文档不一致**

| 文档 | 位置 | Fuel 成本 |
|------|------|----------|
| `game_api.idl.yaml` (权威源) | 行 1620-1622 | `base: 100`, `incremental: "+1/output byte"` |
| `host-functions.md` | 行 69 | `100 base + 1 per output byte` |
| `04-wasm-sandbox.md` | §8 行 378 | `100 + 1/output byte` |
| **`api-registry.md`** | **§4.4 行 510** | **`200` + `+10/32 bytes`** ⚠️ |

`api-registry.md` §4.4 保留旧值 `200 + 10/32 bytes`，与机器权威源 (`game_api.idl.yaml`) 的 `100 + 1/output byte` 不一致。IDL 在 v0.4.2 (2026-06-21) 更新了 fuel 成本，但 `api-registry.md` 最后生成版本为 v0.4.0 (2026-06-18)，**未重新生成**。

**修复建议**: 重新运行 `generate_api_registry.py` 更新 `api-registry.md`，使 §4.4 `host_get_random` fuel 成本与 IDL 一致。

---

### B4: auth_api.idl.yaml 证书链重写 — PARTIALLY_CLOSED

| 检查项 | auth_api.idl.yaml | api-registry.md | game_api.idl.yaml |
|--------|:---:|:---:|:---:|
| `swarm_register_challenge` | ✅ 行 37-58 | ✅ §3.3 | ✅ 行 703 (schema_source/auth_api) |
| `swarm_submit_csr` | ✅ 行 60-95 | ✅ §3.3 | ✅ 行 721 (schema_source/auth_api) |
| `swarm_renew_certificate` | ✅ 行 98-124 | ✅ §3.3 | — (auth-only tool) |
| `swarm_revoke_certificate` | ✅ 行 127-148 | ✅ §3.3 | — (auth-only tool) |
| `swarm_cert_check` | ✅ 行 172-196 | ✅ §3.3 | ✅ 行 745 (schema_source/auth_api) |
| `swarm_cert_list` | ✅ 行 150-170 | ✅ §3.3 | — |
| `swarm_get_server_trust` | ✅ 行 198-220 | ✅ §3.3 | — |
| 12 auth tools total | ✅ (7 CSR + 5 device/recovery) | ✅ §3.3 | — |
| 无 bearer/refresh/JWT | ✅ changelog 行 728 移除 | — | ✅ auth tools → cert |
| Auth shortcuts (schema_source/alias_of) | — | ✅ §3.2 Auth 表 | ✅ 行 717-764 |
| `total_tools: 12` | ✅ | ✅ §3.3 | — |

**GAP: api-registry.md §2.5 Auth RejectionReason codes 未更新**

`api-registry.md` §2.5 仍保留旧的 bearer token 模型 RejectionReason 码，与机器权威 `auth_api.idl.yaml` 不匹配：

| Index | auth_api.idl.yaml (v0.2.0) | api-registry.md (stale) |
|:---:|------|------|
| 1001 | `InvalidCertificate` ✅ | `InvalidCertificate` ✅ |
| 1002 | `CertExpired` | **`NotAuthorized`** ⚠️ (应为 CertExpired) |
| 1003 | `CertRevoked` | **`CertExpired`** ⚠️ (应为 CertRevoked) |
| 1004 | `NotAuthorized` | **`DeviceNotRegistered`** ⚠️ (应为 NotAuthorized) |
| 1005 | `ScopeInsufficient` | **`SessionLimitReached`** ⚠️ (bearer token 遗留) |
| 1006 | `DeviceNotRegistered` | **`RefreshTokenInvalid`** ⚠️ (bearer token 遗留) |
| 1007 | `DeviceLimitReached` | **`ScopeInsufficient`** ⚠️ (错位) |
| 1008 | `CertificateLimitReached` | **`TokenRevoked`** ⚠️ (bearer token 遗留) |
| 1009 | `InvalidCSR` | **`RateLimited`** ⚠️ (错位) |
| 1010 | `UnknownCredential` | **`MultiDeviceConflict`** ⚠️ (bearer token 遗留) |
| 1011 | `RateLimited` | `UnknownCredential` ✅ (巧合匹配) |
| 1012 | `InternalAuthError` | `InternalAuthError` ✅ |

12 个 auth RejectionReason 中仅 3 个 (1001, 1011, 1012) 正确匹配，5 个保留旧 bearer token 语义 (`SessionLimitReached`, `RefreshTokenInvalid`, `TokenRevoked`, `MultiDeviceConflict` + schema 不一致)，4 个索引错位。`api-registry.md` 缺少 `CertRevoked` 和 `InvalidCSR`。

**修复建议**: (a) 重新运行 `generate_api_registry.py --source auth_api.idl.yaml` 更新 `api-registry.md` §2.5；或 (b) 若 registry 确从 IDL 生成，确认 CI check 模式是否生效——当前 discrepency 应被 CI 捕获。

---

### B8: Sandbox 安全边界 — CLOSED

| 检查项 | 04-wasm-sandbox.md | 状态 |
|--------|-------|:---:|
| Netns 独立 | §4.3 行 275-277: "独立 netns，无网络接口、无路由表、无 iptables 规则" | ✅ |
| L1 netns 层 | §4.3 行 280-281: `ip link set lo down`，无任何物理/虚拟网卡 | ✅ |
| L2 seccomp 层 | §4.3 行 282-283: BPF filter 拒绝 socket/connect/bind/listen/accept/sendmsg/recvmsg | ✅ |
| 双层理由 | §4.3 行 283: "防止 netns 逃逸或配置错误" | ✅ |
| 验证命令 | §4.3 行 285: `ip netns exec ... ip link show` → 仅 lo(DOWN), route → 空 | ✅ |
| Store reset checklist | §1 行 43-48: 7 步清单（清空线性内存/重置 fuel/重建 Instance/epoch deadline/验证隔离/seccomp 验证/cgroup 验证） | ✅ |
| 任一失败 → 替换 worker | §1 行 43: "任一失败 → worker 替换并审计" | ✅ |
| R33 vs R34 对比 | R33 M1 指出 "缺乏 checklist" → 现在 7 步 explicit checklist 已就位 | ✅ |

---

### S-H Items

#### S-H1: transport labels in auth_api.idl.yaml — CLOSED

| 检查项 | auth_api.idl.yaml | 状态 |
|--------|-------|:---:|
| agent-mcp | §4 行 448: "AI agent via MCP session" | ✅ |
| cli-rest | §4 行 449: "Human CLI or REST client" | ✅ |
| wasm-sdk | §4 行 450: "WASM SDK (deploy, code signing)" | ✅ |
| Per-tool transport 字段 | 所有 12 个 auth tools 均有 `transport: "agent-mcp, cli-rest, wasm-sdk"` | ✅ |
| security_columns.transport | §8 行 707-711: 三个值完整 | ✅ |
| api-registry.md Transport Labels 表 | §9 行 817-822: 三个值完整 | ✅ |

#### S-H4: CRL fallback enum unified — UNABLE TO VERIFY

需要验证 `design/auth.md` §15.2a 与 §15.6 的 CRL fallback 枚举是否已统一。当前文件集中不包含 `design/auth.md`。CRL fallback 不在 `auth_api.idl.yaml` 范围内。

#### S-H5: Refresh token grace → cert renewal grace — UNABLE TO VERIFY

`auth_api.idl.yaml` v0.2.0 的证书链模型彻底移除了 refresh token（changelog 行 728: "Removed: bearer token, refresh token, JWT envelope"）。R33 H2 的 refresh token grace per-IP 绑定问题因模型变更而自然解决——不存在 refresh token grace。但 `swarm_renew_certificate` 的 renewal grace window 验证需在 `design/auth.md` 中确认。

#### S-H6: Agent/CLI only cert chain — CLOSED (from available files)

| 检查项 | 证据 | 状态 |
|--------|------|:---:|
| Bearer/JWT 从 auth IDL 移除 | auth_api.idl.yaml changelog 行 728 | ✅ |
| Swarm-Certificate-Chain header | auth_api.idl.yaml §4 行 419-420: 唯一认证头 | ✅ |
| Swarm-Signature header | auth_api.idl.yaml §4 行 425: Ed25519 签名 | ✅ |
| Game API auth tools 全部 alias_of | game_api.idl.yaml 行 717-764 | ✅ |
| 无 Authorization: Bearer 语义 | auth_api.idl.yaml 全量移除 | ✅ |

> ⚠️ 原始 R33 H3 要求 `03-mcp-security.md` 显式声明拒绝 JWT Bearer——该文件不在本次验证范围内。

#### S-H7: TTL/lockout params synced — CLOSED (IDL↔Registry)

| 参数 | auth_api.idl.yaml §7 | api-registry.md §5.8 | 匹配 |
|------|------|------|:---:|
| CSR challenge TTL | 300s (行 657) | 300s (行 643) | ✅ |
| Failed CSR lockout threshold | 5 (行 658) | 5 attempts (行 645) | ✅ |
| Failed CSR lockout window | 15m (行 659) | 15m (行 646) | ✅ |
| Failed CSR lockout duration | 30m (行 660) | 30m (行 647) | ✅ |
| Certificate validity max | 365d (行 655) | 365d (行 648) | ✅ |
| ClientAuthCertificate TTL | 15 min–180 days (§3) | 15 min–180 days (行 649) | ✅ |
| CodeSigningCertificate TTL | 30–180 days (§3) | 30–180 days (行 650) | ✅ |
| AdminCertificate TTL | 15 min–1h (§3) | 15 min–1h (行 651) | ✅ |
| FederationCertificate TTL | 24h (§3) | 24h (行 652) | ✅ |
| Nonce window | 60s (行 444) | 60s (行 653) | ✅ |
| Max active certs | 10 (§2 行 406) | 10 (行 641) | ✅ |
| Max active devices | 5 (§2 行 407) | 5 (行 642) | ✅ |

> ⚠️ 是否与 `design/auth.md` 一致需额外验证。

#### S-H8: Admin source → API Registry limits — UNABLE TO VERIFY

Game API IDL 的 admin tools (行 1255-1345) 与 api-registry.md §3.2 Admin 表 (行 359-368) 的 rate limits 一致。但原始 R33 H2 (rev-gpt-security) 问题的核心是 `09-command-source.md` 中 "Admin source 无限制" vs Registry admin limits 的分歧。`09-command-source.md` 不在本次验证范围内。

#### S-H9: SWARM-DEPLOY-V1 payload — NOT CLOSED

**无证据**：在所有已验证文件中 (game_api.idl.yaml, auth_api.idl.yaml, api-registry.md) **未找到** `SWARM-DEPLOY-V1` canonical payload 定义。

- `game_api.idl.yaml` §10 Deploy (行 1858-1897): 定义了 deploy_mutation 机制、fdb_version_counter、4-step flow、swarm_deploy_output schema，但**未定义** deploy 的 canonical request payload 格式（certificate binding、audience binding、expiry binding）。
- `auth_api.idl.yaml` §4: 定义了 `SWARM-REQUEST-V1`（通用 authenticated request），但**未延伸至** deploy 语义的专用格式。
- `api-registry.md` §3.2: `swarm_deploy` 工具 schema 不含 certificate/audience/expiry binding 字段。

原始 R33 S-H9 (rev-gpt-security H3) 要求: "Deploy signed payload 缺 certificate/audience/expiry binding — 直接修复：定义 SWARM-DEPLOY-V1 canonical payload"。

**修复建议**: 在 `game_api.idl.yaml` §10 或 `auth_api.idl.yaml` 中定义 `SWARM-DEPLOY-V1` canonical deploy payload，明确 `(method, path, body_hash, timestamp, nonce, certificate_id, player_id, audience, deploy_id, module_hash, fdb_version_counter_predicted)` 的签名覆盖范围。

#### S-H10: no security_class (D9=B) — CLOSED

| 文件 | 搜索 `security_class` | 状态 |
|------|------|:---:|
| auth_api.idl.yaml | 未出现 | ✅ |
| game_api.idl.yaml | 未出现 | ✅ |
| api-registry.md | 未出现 | ✅ |
| 04-wasm-sandbox.md | 未出现 | ✅ |

D9 裁决为 B (不引入 security_class)，文档中确认无该字段。✅

---

### D8: RuleMod capability-gated + compatibility — CLOSED

| 检查项 | rhai-mod-abi.md | 状态 |
|--------|-------|:---:|
| `direct_ecs_writer` capability | §4.1 行 139: `🔴 Critical`, default 拒绝, 需服主显式授权 + CI unique writer gate | ✅ |
| `engine_version` 声明 | §4.3 行 163: `engine_version = ">=0.9, <1.0"` (必填) | ✅ |
| `abi_version` 声明 | §4.3 行 164: `abi_version = 1` (必填) | ✅ |
| `affected_components` 声明 | §4.3 行 165-168: 必填白名单, 至少一个 (如 HitPoints, Position) | ✅ |
| `affected_resources` 声明 | §4.3 行 169-171: 必填白名单, 至少一个 (如 Energy) | ✅ |
| CI 校验 10 项 | §4.3 行 189-202: 含 engine_version/abi_version/affected_components/unique writer gate/manifest_hash/RW matrix/授权/审计 | ✅ |
| manifest_hash 参与 replay | §4.3 CI check 7: `manifest_hash` 计入 `world_action_manifest_hash` | ✅ |
| `world_action_manifest_hash` | api-registry.md §6 #15 (行 679): TickTrace envelope 包含此字段 | ✅ |

---

## 亮点

1. **auth_api.idl.yaml v0.2.0 重写彻底**：7 CSR lifecycle + 5 device/recovery/federation = 12 tools，12 canonical RejectionReason codes，transport labels，canonical request signature——IDL 层完全消除了 R33 B4 的 bearer token 分叉。

2. **host_get_random 在 IDL/sandbox/host-functions.md 三文档中完全一致**：seed 语义、fuel (100+1/byte)、输出上限 (256 bytes)、per-tick 上限 (10) 精确同步。domain separation 用 `(tick_seed, player_id, drone_id, sequence)` 保证了确定性和 replay 安全。

3. **04-wasm-sandbox.md Store reset checklist 完整**：7 步清单涵盖线性内存清零→fuel counter→Instance 重建→epoch deadline→Store 隔离验证→seccomp 验证→cgroup 验证。任一失败→替换 worker+审计——从 R33 M1 "缺 checklist" 到完整的 fail-stop 链条。

4. **双层网络隔离设计精确**：L1 netns (无接口/无路由/lo down) + L2 seccomp (socket 族全禁)，每层有验证命令和 escape 防护 rationale——这是可实现的、可测试的隔离方案。

5. **D8 direct_ecs_writer 的 capability gating 严密**：10 项 CI checks 覆盖了 engine_version/abi_version/affected_components/unique writer gate/manifest_hash/RW matrix 注册/授权/审计的全链路——即使 Speaker 推荐方案 A，当前 B 实现的质量足以安全部署。

---

## CrossCheck

- **CX-1**: api-registry.md Auth RejectionReason codes 未更新 (B4 GAP) → 建议 **API/DX 方向**检查 `generate_api_registry.py` 是否正确解析 auth_api.idl.yaml v0.2.0 的 rejection_reason variants，并重新生成 registry；CI check 模式应捕获此不一致。

- **CX-2**: api-registry.md host_get_random fuel 成本 stale (B2 GAP) → 建议 **API/DX 方向**确认 `generate_api_registry.py` 是否重新生成了 §4.4 fuel 表，IDL v0.4.2 的 host_functions.per_call_fuel 变更是否已传播。

- **CX-3**: SWARM-DEPLOY-V1 缺失 → 建议 **Security (原方向)** 在 `game_api.idl.yaml` §10 或 `auth_api.idl.yaml` 中定义 SWARM-DEPLOY-V1 canonical payload；建议 **Engine 方向**确认 deploy 签名验证路径中 certificate/audience/expiry binding 的实际实现。

- **CX-4**: S-H4/S-H5/S-H8 需 auth.md/03-mcp-security.md/09-command-source.md 验证 → 建议 **Speaker** 确定这些文件的 R33 closure 状态是否需要独立验证，或由 auth.md 修复 review 覆盖。

- **CX-5**: api-registry.md changelog 仅至 v0.4.0 (2026-06-18)，未反映 game_api v0.4.2 和 auth_api v0.2.0 的变更 → 建议 **API/DX 方向**确认 `generate_api_registry.py` 的 changelog 自动生成逻辑是否覆盖所有三个 IDL 源的版本变更。