# R28 安全评审报告 — rev-dsv4-security

**评审人**: Security Reviewer (DeepSeek V4 Pro)
**评审日期**: 2026-06-20
**源文档**:
1. `design/auth.md` (1782 lines)
2. `specs/core/04-wasm-sandbox.md` (418 lines)
3. `specs/core/01-tick-protocol.md` (877 lines)
4. `specs/reference/api-registry.md` (905 lines)
5. `specs/core/09-snapshot-contract.md` (466 lines)

---

## Verdict: APPROVE_WITH_RESERVATIONS

所有验证点均通过核心安全合同审查。发现 2 个 High 级别问题（ML-10 spec 不一致、ML-11 字段缺失）、1 个 Medium 问题（S-H1 CSR 限速架构缺口），1 个 Informational（跨文档一致性声明）。无 Critical 发现。

---

## 逐项验证

### B3: WASM Sandbox Hardening — ✅ VERIFIED

**验证点**: seccomp clone 策略统一、pids.max 统一 16、sandbox hardening checklist 唯一权威

| 项目 | 源 | 状态 |
|------|-----|------|
| seccomp clone 策略 | `04-wasm-sandbox.md` §4.1: `clone (仅 CLONE_VM \| CLONE_VFORK)` | ✅ 统一 |
| seccomp 禁止列表完整 | §4.1: open/openat/socket/connect/fork/execve/clock_gettime/getrandom/ptrace/kill/mount 全禁 | ✅ |
| pids.max = 16 | §4.2 cgroup v2: `pids.max = 16` | ✅ 统一 |
| hardening checklist | §9.1 统一 OS 加固表: seccomp × 14 项 + cgroup × 4 项 + namespace × 5 项, 附验证命令与理由 | ✅ 唯一权威 |
| CI 验证 | §9.2: `cargo test --test sandbox_boundary`, 验证 EPERM/OOM/throttled/fork fail/socket fail | ✅ |
| relaxed 模式边界 | §9.3: 仅 dev world，生产环境拒绝启动 | ✅ |

**结论**: B3 sandbox hardening 在 `04-wasm-sandbox.md` §9 中以统一表格为唯一权威源。seccomp、cgroup、namespace 三层面约束完整，CI 验证覆盖全边界。

---

### B5: Auth / Certificate / Deploy Consistency — ✅ VERIFIED

**验证点**: 证书签发 CSA/CRL 与 Registry 一致、deploy CS payload、WS per-message MAC

| 项目 | auth.md | api-registry.md | 一致性 |
|------|---------|-----------------|--------|
| 证书链模型 | §5.1: Root CA → Intermediate CA → ClientAuth/CodeSigning/Admin | §9: EdDSA JWT access token, opaque refresh token | ✅ 互补 |
| CodeSigningCertificate 用途 | §5.3: 只签 `module_hash + metadata`, TTL 30-180d | §3.2: `swarm_deploy` requires `swarm:deploy` scope, deploy_mutation replay class | ✅ |
| CS cert 过期语义 | §5.4: 部署时有效即可，过期不影响已部署模块 | §11: deploy_mutation 机制，FDB version_counter 全序 | ✅ |
| CRL 吊销窗口 | §5.3(§5.6c): Engine 内 LRU 缓存，World 60s / Arena 5s 容忍度 | §3.3 cert revoke/rotate tools | ✅ |
| WS per-message MAC | §10.5a: WS 握手含 `Swarm-Certificate-Chain` + canonical signature, 后续消息每消息 seq+MAC | §3.5: Agent WS 每消息 seq+MAC (ed25519), seq 单调递增, 回退断开 | ✅ |
| Deploy CS payload | §5.3: CodeSigningCertificate signs module_hash + metadata | §3.2: `swarm_deploy` input: `{wasm_bytes, metadata}`, output: `{fdb_version_counter, object_store_key}` | ✅ |
| Nonce/Version Counter | §10.8: deploy 用 FDB version_counter, MCP 查询用 Dragonfly SETNX, Admin 用 FDB CAS | §9: refresh token 256-bit opaque, single-use rotation | ✅ |
| 证书上限 | §5.5: 每账号 10 active cert / 5 active device | §5.8: max concurrent sessions=5, cert validity max=365d | ✅ |
| Audience 语法 | §10.8: `swarm-aud-v1:<transport>:<server_id>:<world_id>:<subject_id>` | §13 security columns: subject_source per-tool | ✅ |

**结论**: 证书签发、CRL、部署 CS payload、WS 安全模型在 auth.md 与 api-registry.md 之间完全一致。证书生命周期在 auth.md §5 与 api-registry.md §3.3 两端完整闭合。

---

### S-H1: CSR Rate Limiter — ⚠️ MEDIUM (Architecture Gap)

**验证点**: CSR rate limiter (per-IP/ASN/global/semaphore) 是否存在、数值自洽

**发现**: CSR 提交本身**不设 per-IP/username 限速** — 这是显式设计决策而非遗漏。

| 保护层 | 存在 | 源 |
|--------|------|-----|
| PoW (difficulty_bits=24) | ✅ CSR 的主要速率控制 | auth.md §10.7 |
| Challenge 申请限速 (per-IP) | ✅ 10/min per IP | auth.md §10.7 |
| 恢复凭据限速 (per-IP) | ✅ 10/min per IP | auth.md §10.7 |
| 恢复凭据限速 (per-username) | ✅ 10/min, 5 次失败锁 5min | auth.md §10.7 |
| Argon2id semaphore | ✅ `min(cpu_cores, 4)` 并发上限 | auth.md §6.1 |
| CSR per-IP 限速 | ❌ 未实施 | auth.md §10.7 明述 |
| CSR per-ASN 限速 | ❌ 不存在 | — |
| CSR global semaphore | ❌ 不存在 | — |

**分析**: 
- auth.md §10.7 明述 "CSR 提交不设 IP/username 限速 — PoW 本身就是速率控制"
- 此设计在单 PoW 层面合理 (difficulty_bits=24, ~150ms Rust native, ~1.5s WASM)，但缺乏分布式 PoW 攻击的多维防护
- 分布式场景: 攻击者可使用 1000 个独立 IP 各求解 PoW 后并行提交 CSR，绕过 PoW 的串行延迟。注册后消耗 FDB 存储 (`auth/users/`, `auth/public_keys/`, `auth/certificates/` 等多条记录)
- 缺少 ASN 级或 global semaphore 意味着攻击者可从不同 IP 发起注册风暴
- 恢复凭据路径的 per-IP 限速与 argon2id semaphore 提供了多层保护示例，但 CSR 路径未采用同等策略

**建议**: 
1. 添加轻量 CSR per-IP 限速 (如 5/min)，作为 PoW 的补充而非替代
2. 考虑 global semaphore for CSR 提交 (如 100 concurrent)，防止 FDB 事务风暴
3. 或在设计文档中记录 "CSR PoW-only" 的威胁模型分析（分布式 PoW 并行化攻击的风险评估与接受声明）

---

### S-H2: Refresh Token Security — ✅ VERIFIED

**验证点**: refresh token grace FDB 原子 + IP/UA binding + revoke cap

| 机制 | 实现 | 源 |
|------|------|-----|
| FDB 原子 grace | ✅ `grace_consumed_at` 在 FDB 原子设置，"避免重复使用" | auth.md §14.1 |
| IP/UA binding | ✅ "异常 IP/UA 使用 grace 时触发 session family revoke" | auth.md §14.1 |
| Token family revocation | ✅ "Reuse triggers revocation of entire family" | api-registry.md §9 |
| 受信设备区分 | ✅ 受信设备 grace 缩短至 10s；非受信设备 60s | auth.md §14.1 |
| Single-use rotation | ✅ 每次 refresh 签发新 token + 吊销旧 token | api-registry.md §9 |
| revoke cap | ✅ `swarm_auth_revoke` MCP tool, per session/family | api-registry.md §3.3 |
| 浏览器存储保护 | ✅ HttpOnly Secure SameSite=Strict cookie, WebCrypto non-extractable key, 严禁 localStorage | auth.md §14.3 |

**结论**: Refresh token 的 FDB 原子 grace、IP/UA binding、token family revocation 三层机制完整在 auth.md §14.1 和 api-registry.md §9 中闭合。受信/非受信设备的 grace 区分增加了纵深防御。

---

### ML-10: CRL Stale Default — ⚠️ HIGH (Spec Inconsistency)

**验证点**: CRL stale default 是否升级到 `reject_for_code_and_login`

**发现**: R27 ML-10 的注释声明了升级意图，但 spec 正文未同步更新。

**证据**:

1. auth.md §15.6 (Federation revocation propagation) — `revocation_fallback` 枚举:
   ```
   - "reject_for_code": 默认，login 可短期接受，code 必须拒绝
   - "accept_login": 可用性优先
   - "reject_all": 安全优先
   ```
   枚举中**不存在** `reject_for_code_and_login` 值。

2. auth.md §15.2a (Federation CRL sync) — `revocation_fallback`:
   同样的三个值，**不存在** `reject_for_code_and_login`。

3. auth.md line 1296 — R27 ML-10 注释:
   > 默认值升级为 `reject_for_code_and_login`——CRL 过期时同时拒绝 login 和 code signing，因为 login 路径同样依赖证书链验证。对于确实需要可用性优先的低风险世界，改为 `reject_for_code` 并标注风险。

4. auth.md §15 (Federation default policy) `world.toml` 示例:
   ```
   [auth.federation.default_policy]
   revocation_fallback = "reject_for_code"  ← 仍是旧默认值
   ```

**问题**: 
- 注释声明了 `reject_for_code_and_login` 应作为新默认值，但枚举定义中不存在此值
- `world.toml` 示例仍使用 `reject_for_code` 作为默认值
- 联邦 CRL 同步 (§15.2a) 与联邦撤销传播 (§15.6) 两处的枚举均需更新

**严重性**: HIGH — 若实现者按注释意图实施 `reject_for_code_and_login`，但枚举不支持，将导致运行时错误或回退到不安全默认；若实现者按枚举实施 `reject_for_code`，则与 R27 安全评审的升级决定矛盾。

**建议**: 
1. 在 auth.md §15.2a 和 §15.6 的 `revocation_fallback` 枚举中增加 `reject_for_code_and_login`
2. 更新 `world.toml` 示例中的默认值为 `reject_for_code_and_login`
3. 确保 api-registry.md 中的 auth 相关配置引用同步此变更

---

### ML-11: Identity Fingerprint Separation — ⚠️ HIGH (Field Undocumented)

**验证点**: 256-bit identity_fingerprint 与 64-bit player_id 分离是否清晰

**发现**: `identity_fingerprint` (256-bit) 字段在当前文档中**未显式定义**。

**证据**:

1. auth.md §7.1 (三层身份):
   ```
   login_username → display_name → player_id (u64)
   player_id = blake3("local:" + login_username_lowercase) → 取低 64 bits → u64
   ```

2. auth.md §6.2 (FDB Auth subspace):
   ```
   auth/identities/<provider>/<subject> → player_id (唯一索引)
   ```
   **无** `identity_fingerprint` 字段。

3. auth.md §15.4 (联邦身份映射):
   ```
   "local" + ":" + username → blake3 → u64 → player_id
   "federated" + ":" + world_id + ":" + original_player_id → blake3 → u64 → player_id
   ```

4. api-registry.md §9 (Access Token):
   `{sub (PlayerId), sid, scope, did, iat, exp, jti}` — 无 fingerprint 字段

**问题**:
- blake3 产生 256-bit 输出，但 spec 只存储低 64 bits 作为 player_id
- 全 256-bit hash 未作为独立字段存储在任何 FDB subspace 中
- 碰撞概率在 10^6 用户时为 ~2.7×10^-8（由 auth.md §7.1 计算），可接受，但在碰撞发生时无法区分（注册时检测到唯一索引冲突即拒绝，但事后无法验证两个不同 identity 是否碰巧哈希到同一 player_id）
- "identity_fingerprint" 概念在 ML-11 要求中存在，但在文档中没有任何 schema 定义

**严重性**: HIGH — 若 256-bit fingerprint 是 ML-11 明确要求的安全特性（用于事后身份审计/联邦跨世界一致性验证），当前设计缺失此字段。若 collision detection 仅依赖注册时的唯一索引检查，缺少全指纹意味着无法在运行时审计中区分碰撞与真正同一用户。

**建议**:
1. 在 `auth/identities/<provider>/<subject>` 记录中增加 `identity_fingerprint: [u8; 32]` 字段，存储完整 256-bit blake3 输出
2. 在 auth.md §7.1 中显式定义 identity_fingerprint 与 player_id 的推导关系
3. 在 api-registry.md TickTrace envelope 或 auth events 中增加 fingerprint 字段（如联邦跨世界验证时需要）

---

### T-H1: Seed Lifecycle — ✅ VERIFIED

**验证点**: seed 混合方案中 Arena commit-reveal 与安全 spec 一致

| 机制 | Arena | World | 源 |
|------|-------|-------|-----|
| 种子生成 | 安全随机源（外部熵） | Blake3 链 (`old → new`) | tick-protocol.md §2.5 |
| 赛中可见性 | seed hash 公开，seed 仅引擎 | seed 仅引擎 | §2.5 |
| 披露时机 | 赛后 +100 tick 自动公开 | 不公开（运维保护） | §2.5 |
| 归档 | 快照/keyframe 中记录 seed epoch | 同 Arena | §2.5 |
| 泄露响应 | 赛后自动审计 (seed hash 校验) | Operator seed-bump + 回滚 | §2.5 |
| 检测 | — | Statistical Detection (每 1000 tick) | §2.5 |
| seed_commitment | `Blake3(seed_epoch_0 \|\| "commit")` 写入公开元数据 | N/A | §2.5 |
| 种子轮换 | N/A（按 match 周期） | 每 10000 tick | §3.1 |

**Arena commit-reveal 验证**:
- 赛前: `seed_commitment` 写入公开元数据，seed 仅引擎内存 → ✅ 承诺不可抵赖
- 赛中: MCP/API 只暴露 `seed_commitment`，玩家无法获取实际 seed → ✅ 防止预测
- 赛后: `seed_epoch_0` 自动公开 + `Blake3(seed_epoch_0 || "commit") == seed_commitment` 可验证 → ✅ 赛后审计
- 赛后公开时机 (match_end_tick + 100) 给予 100 tick 缓冲防止赛中数据泄露 → ✅

**结论**: Arena commit-reveal 方案完整且与安全 spec 一致。World seed-bump + statistical detection 方案为无时间边界的持久世界提供了合理的运维止损机制。seed 生命周期统一模型表清晰分离了 Arena 与 World 两种模式的安全语义。

---

### E-H1: Allied Transfer Security Cross-Check — ✅ VERIFIED

**验证点**: 运输中资源 ownership 归属、无资源复制 bug

| 项目 | 实现 | 源 |
|------|------|-----|
| 延迟窗口 | 200 tick，最后 50 tick 为拦截窗口 | snapshot-contract.md §3.2a |
| 资源扣除时机 | 发送方在 deposit 时立即扣除 | §3.2a |
| 资源到达时机 | tick 200 到期日 | §3.2a |
| 拦截模式 | 窃取 (CARRY, 50%) 或 销毁 (ATTACK, 100%) | §3.2a |
| 成功率 | `clamp(60% + part_bonus - escort_penalty, 10%, 85%)` | §3.2a |
| Escort 防御 | 接收方同格 ATTACK drone 自动视为 escort, -30% | §3.2a |
| 确定性 RNG | `Blake3("intercept" \|\| transfer_id \|\| tick \|\| world_seed)` | §3.2a |
| 审计 | 每次拦截尝试记录完整 audit log | §3.2a |
| 三方通知 | 发送方/接收方/攻击方均收到事件 | §3.2a |

**资源归属验证** (防复制 bug):
```
发送方 deposit → 资源从发送方扣除
  → 运输中 (tick 0-200): 资源为 "in transit"，不属于任何玩家
  → 拦截阶段 (tick 150-200):
     窃取成功: 攻击方获 50% + 接收方获 50% = 100% 运输量 ✅
     销毁成功: 100% 资源销毁 ✅
     拦截失败: 接收方获 100% ✅
```

**结论**: Allied Transfer 在运输中资源归属清晰，不存在资源复制路径。拦截机制的三方通知 + 审计日志 + 确定性 RNG 满足竞技公平要求。`swarm_simulate` 不能预测拦截结果（`not_predictive: true` + 独立 RNG namespace），防止 preview-based exploit。

---

## 发现汇总

| # | 级别 | 项目 | 问题 |
|---|------|------|------|
| 1 | **HIGH** | ML-10 | `revocation_fallback` 枚举缺少 R27 要求的 `reject_for_code_and_login` 值；`world.toml` 示例仍用旧默认 `reject_for_code` |
| 2 | **HIGH** | ML-11 | 256-bit `identity_fingerprint` 字段在 auth.md FDB schema 与 identity 模型中均未定义；仅有 64-bit `player_id` 的截断 |
| 3 | **MEDIUM** | S-H1 | CSR 提交仅靠 PoW 限速，无 per-IP/ASN/global semaphore 补充；分布式 PoW 并行化攻击路径未在威胁模型中分析 |
| 4 | INFO | B3 | `04-wasm-sandbox.md` §2 锁定 wasmtime =30.0，§6.3 模块缓存键包含 `wasmtime_build_commit`，但 api-registry.md TickTrace 记录 `wasmtime_version` (string)，类型不一致（commit vs version string），建议统一 |

---

## 跨文档一致性

| 交叉点 | 文档 A | 文档 B | 状态 |
|--------|--------|--------|------|
| 证书 TTL | auth.md §5.3: CS cert 30-180d | api-registry.md §5.8: cert validity max=365d | ✅ (365d 是上限，30-180d 是 CS 默认) |
| Sandbox fuel | 04-wasm-sandbox §6: 10M fuel | 01-tick-protocol §8.2: 10M fuel | ✅ |
| Snapshot 256KB | 01-tick-protocol §2.3: 256KB | 09-snapshot-contract §1.1: 256KB | ✅ |
| Pathfinding budget | 04-wasm-sandbox §6: 100K nodes | api-registry.md §5.2: 100K nodes | ✅ |
| CRL cache TTL | auth.md §10.8: World 60s / Arena 5s | api-registry.md (缺失 Arena CRL TTL) | ⚠️ api-registry 增补 |
| Seed rotation | 01-tick-protocol §3.1: 10000 tick | 01-tick-protocol §2.5: 10000 tick | ✅ |
| Refresh token TTL | auth.md §14.1: 30 days | api-registry.md §5.8: 7d | ⚠️ 不一致: auth.md=30d, api-registry=7d |

**追加发现 (INFO)**: auth.md §14.1 设定 `refresh_token` TTL 为 30 days，但 api-registry.md §5.8 设定 Refresh token lifetime 为 7d。建议统一为单一权威值。

---

## Build / Action Items

| 优先级 | 项目 | 行动 |
|--------|------|------|
| P0 | ML-10 | auth.md §15.2a + §15.6 枚举增加 `reject_for_code_and_login`；更新 `world.toml` 默认值示例 |
| P0 | ML-11 | auth.md §7.1 + §6.2 FDB schema 增加 `identity_fingerprint: [u8; 32]` 字段定义 |
| P1 | S-H1 | auth.md §10.7 增加 CSR per-IP 限速（或记录 "PoW-only" 的分布式威胁分析） |
| P2 | INFO | 统一 auth.md / api-registry.md 的 refresh token TTL (30d vs 7d) |
| P2 | INFO | api-registry.md 补齐 Arena CRL cache TTL (5s) |
| P2 | INFO | 统一 TickTrace `wasmtime_version` 字段类型 (version string vs commit hash) |

---

*End of R28 Security Review*