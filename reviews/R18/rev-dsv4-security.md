# R18 安全评审 — DeepSeek V4 Pro

**评审日期**: 2026-06-18
**评审范围**: Clean-Slate Phase 1 设计评审 — 仅读 R18 docker 挂载文档
**评审聚焦**: YAML IDL → api-registry.md 生成式单源闭合性验证 + YAML↔Markdown 漂移检测

---

## Verdict: REQUEST_MAJOR_CHANGES

YAML IDL 声称"唯一机器事实源"但未真正闭合。auth.md 定义了 YAML 中不存在的 replay class（`deploy_mutation`、`non_idempotent_mutation`）和大量 auth 工具；速率限制在 auth.md 授权矩阵与 YAML IDL 之间严重不一致；audience 格式存在 4 段/5 段版本分歧。这些不是格式差异——它们是安全合约层面的冲突，直接威胁 nonce 验证策略、速率控制和传输安全绑定。

---

## 发现问题

### Critical

#### C1: swarm_deploy replay_class 漂移 — 防重放机制隐含冲突

**涉及文件**: `game_api.idl.yaml` L836, `api-registry.md` L218, `design/auth.md` §5.6a (L318-322), `design/auth.md` §10.8 (L855-878)

auth.md §5.6a 定义了 5 种 replay class，其中 `deploy_mutation` 为独立 class，防重放机制是 **FDB version_counter**（§10.8 明确"Deploy 不使用 nonce"）。但 YAML IDL 和 api-registry.md 中，`swarm_deploy` 的 `replay_class` 字段值为 `idempotent_mutation`——该 class 在 auth.md §5.6a 中的防重放机制是 **Dragonfly nonce + time window**。

```yaml
# YAML L836 — 标记为 idempotent_mutation
- name: swarm_deploy
  replay_class: idempotent_mutation
```

```
# auth.md §5.6a — deploy 是独立 class，不同 nonce 策略
deploy_mutation | FDB version_counter（见 §10.8） | swarm_deploy
idempotent_mutation | Dragonfly nonce + time window（除 deploy 外） | swarm_submit_csr
```

**安全影响**: 这两个 class 的崩溃语义根本不同——Dragonfly nonce 在 TTL 窗口内可重放（auth.md §10.8: "TTL 窗口内可重放"），而 FDB version_counter 严格递增、崩溃后不可重放。若实现方以 YAML 为准、按 `idempotent_mutation` 走 Dragonfly nonce 路径，deploy 将失去持久化防重放保证。R16 B6 裁决的 deploy_mutation 模式可能被静默绕过。

**修复建议**: 将 `deploy_mutation` 添加为 YAML IDL 和 api-registry.md 的正式 replay_class 枚举值，`swarm_deploy` 改用 `deploy_mutation`。YAML 的 replay_class enum 需从 4 值扩展为 6 值（增加 `deploy_mutation` 和 `non_idempotent_mutation`）。同时在 YAML 中为每个 replay_class 定义 nonce 策略字段，消除 auth.md 的隐式引用。

---

#### C2: replay_class 枚举不闭合 — auth.md 定义了 YAML 中不存在的值

**涉及文件**: `design/auth.md` §5.6a, `game_api.idl.yaml` §3 MCP tools

auth.md §5.6a 定义 5 种 replay class:
| class | YAML 中存在? |
|---|---|
| `read_replay_safe` | ✓ |
| `idempotent_mutation` | ✓ |
| `deploy_mutation` | **✗ 不存在** |
| `non_idempotent_mutation` | **✗ 不存在** |
| `admin_critical` | ✓ |

YAML IDL 实际使用的 replay_class 值只有 4 种:
| YAML 值 | auth.md 中存在? |
|---|---|
| `read_replay_safe` | ✓ |
| `idempotent_mutation` | ✓ |
| `non_replayable` | **✗ auth.md 未定义** |
| `admin_critical` | ✓ |

**双向缺口**:
- auth.md → YAML: `deploy_mutation` 和 `non_idempotent_mutation` 从未被引用
- YAML → auth.md: `non_replayable` 未在任何设计文档中定义

这导致"哪个文档定义权威 replay_class 枚举"不明确——实现方无单一来源可查。

**修复建议**: YAML IDL 顶部新增 `replay_class` enum 段，列出所有合法值及其 nonce 策略和崩溃语义。auth.md §5.6a 改为引用该段。

---

### High

#### H1: 速率限制冲突 — auth.md §5.6b 授权矩阵与 YAML IDL 不一致

**涉及文件**: `design/auth.md` §5.6b, `game_api.idl.yaml` §3

| 工具 | auth.md §5.6b | YAML IDL / api-registry.md |
|---|---|---|
| `swarm_get_snapshot` | **10/s** | **1/tick** |
| `swarm_deploy` | **1/5s** | **10/h** |
| `swarm_submit_csr` | **1/30s** | 工具不在 YAML 中 |

`10/s` vs `1/tick` 含义完全不同——前者限每秒 10 次（无 tick 关联），后者每 tick 最多 1 次。若 tick rate = 1/s，两者数值相等但语义不同（tick 对齐 vs 滑动窗口）。若 tick rate = 3/s，则 1/tick = 3/s（比 10/s 更严格）。`1/5s` (720/h) vs `10/h` 相差 72 倍。

**安全影响**: rate limit 是 DoS 防护的一线。限速不一致意味着 Gateway 和 Engine 可能使用不同阈值，攻击者可能利用较宽松值（如 1/5s deploy）进行高频部署 DoS。

**修复建议**: YAML IDL 为权威源。auth.md §5.6b 应删除硬编码 rate limit 列，改为 `→ 见 API Registry`，或从 YAML 自动生成。

---

#### H2: Audience 格式分歧 — 4 段 vs 5 段

**涉及文件**: `design/auth.md` §3.1, `design/auth.md` §10.8, `specs/security/09-command-source.md` §7.0

auth.md §3.1 (证书签发接口):
```
audience: "swarm-aud-v1:swarm-alpha:world_v1:42"
```
格式: `swarm-aud-v1:<server_id>:<world_id>:<player_id>` — **4 段**

auth.md §10.8 (Audience 字符串语法) 和 09-command-source.md §7.0:
```
audience: "swarm-aud-v1:<transport>:<server_id>:<world_id>:<subject_id>"
```
格式: `swarm-aud-v1:<transport>:<server_id>:<world_id>:<subject_id>` — **5 段**，含 `transport`

**安全影响**: 09-command-source.md §7.0 要求 `X-Swarm-Transport` header 与 audience 中的 transport 匹配，并强制拒绝缺少该 header 的请求。若 auth.md §3.1 的 4 段格式被实现，certificate 将缺少 transport 绑定，可能被跨 transport 重放（如 agent-mcp 证书用于 browser-ws）。这是 R17 发现的"权威单源未闭合"问题的延续——证书签发侧与传输验证侧的 audience 格式未对齐。

**修复建议**: 统一为 5 段格式。auth.md §3.1 中 `issue_certificate_bundle()` 示例 audience 改为 `"swarm-aud-v1:cli-rest:swarm-alpha:world_v1:42"`。

---

#### H3: Auth 工具群未在 YAML IDL 注册 — 单源不完整

**涉及文件**: `design/auth.md` §10.1, `game_api.idl.yaml` §3

auth.md §10.1 列出了 20 个 auth 相关 MCP 工具:
`swarm_register_challenge`, `swarm_submit_csr`, `swarm_renew_certificate`, `swarm_get_server_trust`, `swarm_token_refresh`, `swarm_auth_revoke`, `swarm_list_certificates`, `swarm_revoke_certificate`, `swarm_update_profile`, `swarm_change_password`, `swarm_request_password_reset`, `swarm_admin_create_password_reset`, `swarm_confirm_password_reset`, `swarm_register_passkey`, `swarm_recover_with_passkey`, `swarm_bind_email`, `swarm_delete_account`, `swarm_restore_account`, `swarm_cancel_account_deletion`, `swarm_federated_login`

YAML IDL 仅包含其中 2 个: `swarm_auth_login`, `swarm_auth_refresh`。

另外 18 个 auth 工具**未在任何机器可读源中注册**。这意味着:
- CI 无法自动验证这些工具的 schema、replay_class、scope、rate limit
- SDK codegen 不会为它们生成类型
- 跨文件一致性检查不会覆盖它们

**安全影响**: auth 工具中有高安全敏感操作（`swarm_revoke_certificate`、`swarm_admin_create_password_reset`、`swarm_federated_login`），其 replay_class、rate limit、required_scope 在 YAML 中无记录，无法被 CI 自动审计。auth.md §5.6b 为其中 3 个工具（`swarm_submit_csr`、`swarm_revoke_certificate`、`swarm_admin_create_password_reset`）硬编码了授权参数——这些值未经过 YAML → registry 生成管线的校验。

**修复建议**: 将所有 auth 工具注册到 YAML IDL，或创建独立的 `auth_api.idl.yaml`。auth.md §10.1 表格应标注"→ 见 API Registry"。

---

### Medium

#### M1: swarm_submit_csr 的 replay_class 歧义

auth.md §5.6a 将 `swarm_submit_csr` 归入 `idempotent_mutation`:
```
idempotent_mutation | Dragonfly nonce + time window（除 deploy 外）| swarm_submit_csr（同 CSR）
```

但 auth.md §5.6b 将其归入 `non_idempotent_mutation`:
```
swarm_submit_csr | non_idempotent_mutation | swarm:register | 1/30s | none | no
```

同一份文档内对同一工具产生自相矛盾的分类——§5.6a 说 idempotent（同 CSR 重复提交结果相同），§5.6b 说 non_idempotent（重复产生副作用）。由于该工具不在 YAML 中，没有权威裁决。

#### M2: API Registry 中的 omitted_count 类型与 visibility spec 分桶方案不一致

05-visibility.md §10.2 已将 `omitted_count` 从精确整数改为分桶字符串（`"few"`, `"some"`, `"many"`, `"extreme"`），但 api-registry.md 多处仍显示 `omitted_count: u32`（如 §1.1 swarm_get_snapshot output_schema L469，YAML L467）。分桶方案命名已定但未反映到机器可读源。

#### M3: 09-command-source.md §7.0 的 X-Swarm-Transport header 判定规则在 auth.md 中无对应表述

09-command-source.md §7.0 要求"缺少 X-Swarm-Transport header → 拒绝（401 MissingTransportHeader）"，但 auth.md 的 certificate 验证流程（§5.6c）未提及此 header 检查。若 Gateway 实现以 auth.md 为准，transport 绑定可能被跳过。

---

### Informational

#### I1: CVE-SLA 覆盖良好

CVE-SLA.md 覆盖了 Wasmtime 及 15 个 critical Rust crates（包括 blake3、ed25519-dalek、ring、rustls 等），监控来源明确（cargo audit + RustSec Advisory DB），对 crypto crates 的升级后 determinism regression test 要求合理。

#### I2: 可见性模型闭合质量高

05-visibility.md 的 oracle 防线设计（§10）是本次评审中质量最高的安全设计段：
- `NotVisibleOrNotFound` 等价类封闭目标存在/不可见 oracle
- `omitted_count` 分桶方案消除截断计数 oracle
- `debug_detail` 三级脱敏（competitive/practice/training）
- 特殊攻击拒绝码等价策略完整覆盖 8 种攻击类型

#### I3: Deferred Command Model 与不可伪造 auth context 坚实

04-wasm-sandbox.md §3 的 deferred command model 和 09-command-source.md §3 的不可伪造 auth context 设计合理：所有状态变更必须通过 JSON 返回、`player_id` 服务端注入、`WorldMutate` trait 编译期强制唯一实现者——这些构成了稳固的安全基座。

---

## 亮点

1. **YAML IDL 本身质量高**: 结构清晰、注释完整、46 个工具全部带 security columns（replay_class, visibility_filter, rate_limit_key）。如果 auth 工具补全且 replay_class enum 闭合，这个单源将是真正的权威。
2. **Oracle 防线全面**: 05-visibility.md §10 从 MCP 查询、omitted_count、dry_run、特殊攻击拒绝码四个维度封堵了信息泄露路径，是教科书级的设计。
3. **CVE-SLA 务实**: 分级响应时间（24h/72h/1w/next release）、明确回滚策略、对 crypto crates 的 determinism regression test——这些在游戏引擎中少见但 Swarm 因其 replay 确定性需求而必要。
4. **Deferred Command Model 双向安全**: WASM 无权直接修改世界状态 + `player_id` 服务端注入——这两条规则使 WASM 沙箱即使在逃逸情况下也无法伪造玩家身份或直接操作 ECS。

---

## CrossCheck

### Architect (rev-dsv4-architect)
- C1 和 C2 的 replay_class 枚举不闭合是架构级问题——YAML IDL 需要顶层 `replay_class` enum 段定义所有合法值及其 nonce 策略。请确认是否应该在 YAML 中为每种 replay_class 定义 `nonce_mechanism` 和 `crash_semantics` 字段。
- H1 的速率限制冲突本质是"单源之前的残留"——请裁决 auth.md §5.6b 是否应从设计文档降级为"实现提示"，并建立 YAML → auth.md 的单向生成约束。

### Game Designer (rev-dsv4-game-designer)
- M2 中 `omitted_count` 分桶方案已在 visibility spec 中定型，但未传播到 YAML/registry。请确认 bucket 名称 (`"few"`, `"some"`, `"many"`, `"extreme"`) 是否最终，以便更新 YAML。
- 49 个 MCP tool（46 registered + 1 RFC + 2 隐式 host fn only）的 capability profile 分配是否覆盖了所有玩家角色？

### Auth Designer (rev-dsv4-auth-designer)
- H3: 18 个未注册 auth 工具的 replay_class、rate_limit、scope 需要正式化。请确认是否创建独立 `auth_api.idl.yaml` 还是并入 `game_api.idl.yaml`。
- H2: audience 格式统一为 5 段后，auth.md §3.1 `issue_certificate_bundle()` 示例需要更新。请确认 `transport` 枚举值 (`agent-mcp`, `cli-rest`, `browser-ws`, `browser-http`, `replay-viewer`) 是否最终。
- M1: `swarm_submit_csr` 的 replay_class 在 auth.md §5.6a (idempotent_mutation) 和 §5.6b (non_idempotent_mutation) 之间矛盾——请裁决哪个正确。

---

## 评审统计

| 严重级别 | 数量 |
|---|---|
| Critical | 2 |
| High | 3 |
| Medium | 3 |
| Informational | 3 |
| **合计** | **11** |

**R17 → R18 趋势**: R17 发现的 `api_version` 冲突（0.1.0 vs 0.2.0）已修复（统一为 0.3.0）。R17 的 `replay_class` 枚举不一致（auth.md 5 类 vs IDL 3 类）未完全修复——auth.md 保留了 5 类而 YAML 仅使用 4 类，且 `deploy_mutation` 仍不在 YAML 中。生成式单源闭合在推进中但尚未完成。

---

*评审员: Security Reviewer — DeepSeek V4 Pro*
*下一步: 各 CrossCheck 目标评审员需在 Consensus Report 中回应上述问题。*
