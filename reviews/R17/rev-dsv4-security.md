# R17 Security Review — rev-dsv4-security (DeepSeek V4 Pro)

**评审日期**: 2026-06-18
**评审轮次**: R17 Phase 1 Clean-Slate
**评审章程**: 设计阶段评审，仅读授权子集，验证权威单源闭合

---

## Verdict: REQUEST_MAJOR_CHANGES

权威单源未真正闭合。发现 2 个 Critical 级别的跨文档不一致——`api_version` 和 `replay_class` 枚举在两个"权威源"(api-registry.md vs game_api.idl.yaml, auth.md vs IDL) 之间存在冲突，违反 API Registry§原则1「单事实源」和§原则4「完整闭合」。此外发现 1 个 High 级别的 rate limit 数值冲突（1/5s vs 10/h，相差 72 倍）。这些问题不是设计缺失——是文档工程层面的闭合失败：多份文档声称自己是权威源但内容不同步。

---

## 发现问题

### Critical

#### C1: api_version 冲突 — 两份"权威源"声明不同版本

| 文档 | 声明的 api_version |
|------|-------------------|
| `specs/reference/api-registry.md` 第 14 行 | `0.1.0` |
| `specs/reference/game_api.idl.yaml` 第 8 行 | `0.2.0` |

**影响**: api-registry.md 明确声明自己为「所有 API 合约的单一权威来源」，而 game_api.idl.yaml 声明为「Machine-Readable Single Source of Truth — Canonical source for codegen/SDK/CI，All other docs derive from this」。两份文档互相声称彼此为派生源，但 `api_version` 不同——CI 通过哪一份？`TickTrace.api_version` 以谁为准？任何消费 `api_version` 的代码/SDK/CI 在第 0 天即产生分歧。

**违反原则**: API Registry §原则1「单事实源」、§原则4「完整闭合」

**建议修复**: 选定一份为真权威源（建议 YAML，因其可机器校验），在 api-registry.md 中移除自声明的 `api_version`，用 `(见 game_api.idl.yaml)` 引用替代。CI 强制校验 YAML → Markdown 派生一致性。

---

#### C2: replay_class 枚举不一致 — auth.md 定义 5 类但 IDL 只有 3 类

`design/auth.md` §5.6a 定义 5 个 replay class：

| Replay Class | Nonce 策略 |
|-------------|-----------|
| `read_replay_safe` | 可选 nonce + time window |
| `idempotent_mutation` | Dragonfly nonce + time window（除 deploy 外） |
| `deploy_mutation` | **FDB version_counter** |
| `non_idempotent_mutation` | FDB version counter 或一次性 challenge |
| `admin_critical` | FDB 事务内消费 challenge + 双签审计 |

但 `game_api.idl.yaml` 和 `api-registry.md` 中实际使用的 replay_class 值只有 3 个：

| IDL 中存在的值 |
|---------------|
| `read_replay_safe` |
| `idempotent_mutation` |
| `admin_critical` |

**具体冲突**:
- `swarm_deploy` 在 IDL 中被标记为 `replay_class: idempotent_mutation`，但 auth.md §5.6a 明确将其归入独立的 `deploy_mutation` 类（FDB version_counter 而非 Dragonfly nonce）
- `swarm_submit_csr` 在 auth.md §5.6b 被标记为 `non_idempotent_mutation`，但该工具未出现在 46 个 IDL MCP 工具中
- `non_idempotent_mutation` 值在 IDL 中完全不存在

**影响**: 实现者查看 IDL → 对 deploy 使用 Dragonfly nonce；实现者查看 auth.md → 对 deploy 使用 FDB version_counter。两者防重放语义不同（Dragonfly TTL 崩溃后可重放，FDB version_counter 严格递增不重放）。若代码按 IDL 实现 deploy 防重放，则产生安全降级。

**违反原则**: API Registry §原则1「单事实源」，auth.md §5.6a 的 replay class 模型与 IDL 不兼容

**建议修复**:
1. 将 `deploy_mutation` 和 `non_idempotent_mutation` 加入 IDL 的 replay_class 枚举
2. `swarm_deploy` 在 IDL 中的 replay_class 改为 `deploy_mutation`
3. 将 auth 系列 MCP 工具（§10.1 的 19 个工具）注册到 IDL 中，各自标注 replay_class
4. CI 校验 IDL replay_class 枚举值与 auth.md §5.6a 完全一致

---

### High

#### H1: swarm_deploy rate limit 数值冲突 — 1/5s vs 10/h

| 源 | swarm_deploy rate limit |
|----|------------------------|
| `api-registry.md` §3.1 MCP 工具表 | `1/5s` |
| `api-registry.md` §3.3 通用限流 | `10/h`（deploy 类） |
| `game_api.idl.yaml` `swarm_deploy.rate_limit` | `10/h` |

`1/5s` = 720/h，`10/h` = 0.0028/s。差异 72 倍。同一文档（api-registry.md）内部自相矛盾。

**影响**: 若按 1/5s 实现 → 攻击者可以 720 次/h 的频率轰炸部署端点（编译 DoS + 存储 DoS）。若按 10/h 实现 → 符合设计意图但与 markdown 表格冲突。实现者无法确定正确值。

**建议修复**: 以 YAML IDL 的 `10/h` 为权威值，修正 api-registry.md markdown 表格中 swarm_deploy 的 Rate Limit 列。

---

#### H2: audience transport 类型跨文档不完整

`design/auth.md` §10.8 定义 audience transport 枚举为 5 个值：`browser-http | browser-ws | agent-mcp | cli-rest | replay-viewer`。

但各 spec 文档的覆盖不完整：

| Transport | auth.md §10.8 | 03-mcp-security.md §2 | 09-command-source.md §7.0 |
|-----------|:---:|:---:|:---:|
| `browser-http` | ✅ | ✅ | ❌ 缺失 |
| `browser-ws` | ✅ | ❌ 未提及 | ✅ |
| `agent-mcp` | ✅ | ❌ 未提及 | ✅ |
| `cli-rest` | ✅ | ✅ | ✅ |
| `replay-viewer` | ✅ | ❌ 未提及 | ✅ |

**关键缺口**:
- `agent-mcp` 在 03-mcp-security.md 中完全缺失——这意味着 MCP agent 的 transport 安全合同只有 09-command-source 覆盖，03-mcp-security（本应是最权威的安全规范）没有定义 Agent 的 audience 绑定
- `browser-http` 在 09-command-source 中缺失——浏览器 HTTP 路径的 audience 约束未在命令来源模型中表达

**影响**: `agent-mcp` 是 AI agent 的主 transport 路径。若 03-mcp-security 未定义其 audience，则 MCP 安全评审存在盲区——例如 agent 使用 `cli-rest` audience 的证书通过 MCP 端点认证是否应被拒绝？

**建议修复**: 03-mcp-security.md §2 补充完整的 5 种 transport audience 矩阵；09-command-source.md §7.0 补充 `browser-http` 行。

---

#### H3: read_replay_safe nonce — §5.6a 说"可选" vs §10.8 说 Dragonfly 存储

auth.md §5.6a 对 `read_replay_safe` 的 nonce 策略为「可选 nonce，time window 校验」。但 §10.8 Nonce 存储中「MCP 查询请求（读）」使用 Dragonfly SETNX TTL 存储 nonce。

若 nonce 是"可选"的，攻击者可省略 nonce 完全绕过 Dragonfly 去重，仅剩 time window 校验。Time window 校验（±30s 或 ±60s）只能限制重放窗口，不能防止窗口内重放。对于 `swarm_get_snapshot`（1/tick limit）、`swarm_deploy`（10/h limit）等限流端点，窗口内重放可能导致 rate limit 被消耗或快照数据在窗口内被重复拉取。

**影响**: 对于 competitive world 的 `swarm_get_snapshot`，窗口内重放可让攻击者每秒多次拉取快照，绕过 1/tick limit——尤其在 60s time window 内。

**建议修复**: 明确 read_replay_safe 的 nonce 策略——若 Dragonfly 是权威 nonce 存储，则 nonce 应为 mandatory，并在 §5.6a 中将"可选"改为"强制"。

---

### Medium

#### M1: admin nonce 机制双重描述 — §5.6a vs §10.8

auth.md §5.6a 描述 admin_critical 的防重放为「FDB 事务内消费 challenge + 双签审计」。
auth.md §10.8 描述为「FDB monotonic counter (CAS atomic) … per-admin 单调递增计数器 … CAS 递增计数器」。

两者语义不同：§5.6a 是 per-operation challenge 消费（一次性 challenge token），§10.8 是 per-admin 单调计数器（操作序号）。虽然可以实现为"challenge 绑定当前计数器值"的兼容方案，但两份描述未明确关联，实现者可能误解为两个独立机制。

**建议修复**: 统一描述——例如「admin 操作使用 per-admin monotonic counter 作为 challenge 的一部分，FDB 事务内 CAS 递增 + 双签审计」。

---

#### M2: auth MCP 工具未注册到 IDL

auth.md §10.1 定义了 19 个 MCP 工具（`swarm_register_challenge` 到 `swarm_federated_login`），但这些工具不在 `game_api.idl.yaml` 的 46 个 MCP 工具表中。

**影响**: API Registry 声称是「所有 API 合约的单一权威来源」且「未注册的 CI 拒绝」。若 auth 工具不在 IDL 中，按 API Registry §原则4 CI 应拒绝这些工具的调用——但这显然不是设计意图。实际效果是 IDL 和 auth.md 各自为政。

**建议修复**: 将 19 个 auth 工具注册到 IDL 中，标注 replay_class、scope、rate_limit 等安全列。auth.md §10.1 改为引用 IDL。

---

#### M3: WebSocket 签名 domain separator 与 audience 格式不一致

- `09-command-source.md` §7.0 WebSocket audience: `swarm-aud-v1:browser-ws:{server_id}:{world_id}:{player_id}`
- `auth.md` §10.5a WebSocket 握手签名 payload: `SWARM-WS-V1\n<cert_id>\n<timestamp>\n<nonce>`
- `api-registry.md` §3.4 Agent WS per-message 签名: `SWARM-WS-MSG-V1\n<seq>\n<body_hash>`

这里有三层不同的签名 domain separator：握手（`SWARM-WS-V1`）、per-message（`SWARM-WS-MSG-V1`）、audience（`swarm-aud-v1:...`）。三者的版本号独立演进，但没有文档说明它们之间的关系和版本同步策略。

**建议修复**: 在 auth.md 或 09-command-source.md 中增加一节说明 domain separator 体系——WS 握手签名、per-message MAC、audience 字符串三者的分层关系与版本策略。

---

#### M4: cgroup pids.max 值冲突

| 源 | pids.max |
|----|---------|
| `04-wasm-sandbox.md` §4.2 | `32` |
| `04-wasm-sandbox.md` §9.1 | `16` |

同一文档内部 pids.max 不一致（32 vs 16）。§9.1 的表格是部署前 checklist 应使用的权威值，但 §4.2 的运行时配置代码示例使用了不同的值。

**建议修复**: 统一为 16 或 32。考虑到 Wasmtime + 编译线程的需求，建议 32，并确保 §9.1 表格更新。

---

### Low

#### L1: 05-visibility.md omitted_count oracle 修正遗留

§10.2 已将 `omitted_count` 改为分桶值（few/some/many/extreme），但 §3.1 快照示例 JSON 中仍使用 `"omitted_count": 0`（整数）。快照 schema 未同步更新。

**建议修复**: §3.1 示例更新为 `"omitted_count": "none"` 或使用新的分桶枚举值。

---

#### L2: auth.md §10.5a WebSocket 握手 vs api-registry.md §3.4 Agent WS

auth.md §10.5a 说 WS 握手后「后续消息免签名（会话内信任）」。但 api-registry.md §3.4 说 Agent WS「每条消息附带单调递增序列号和消息认证码」。两者矛盾——握手后是否需要 per-message 签名？

**分析**: api-registry.md §3.4 的描述更安全（per-message seq+MAC 防会话劫持），03-mcp-security.md §2.5 也确认了 per-message seq+MAC。auth.md §10.5a 的「免签名」表述不准确——应该说「免重新握手验证，但 per-message seq+MAC 仍需继续」。

**建议修复**: auth.md §10.5a 改为「后续消息免重新握手，但每消息仍需 seq+MAC/signature 验证」。

---

#### L3: 03-mcp-security.md vs 05-visibility.md — ticket 编号冲突

03-mcp-security.md §5.3 引用 `specs/core/02-command-validation`，但 05-visibility.md §6.2 Hack 可见性也引用 `specs/core/02-command-validation`——路径正确但 02-command-validation 不在本次授权文档列表中，无法验证引用目标是否存在。

**建议**: 非安全相关，但作为文档工程实践，交叉引用应可机器验证。

---

## 亮点

1. **CRL/epoch bump 分层体系完整闭合**: auth.md §10.8 缓存边界表 + §8.4 epoch bump 确定性 + 09-command-source.md §3.4 吊销结果确定性——三份文档对 CRL 缓存（Engine LRU, 60s TTL）、epoch bump（FDB 记录, replay 使用记录事件）、吊销结果（TickTrace 记录, 不重新评估）的描述完全一致。这是经过 R14/R15/R16 多轮修复后的成果。

2. **PoW 防篡改闭合**: auth.md §9.3 服务端从 FDB 读取权威 challenge+difficulty，客户端不回传 challenge/difficulty。§10.7 CSR 提交不设 IP/username 限速——PoW 本身就是速率控制。Challenge 申请设 10/min IP 限速防存储 DoS。三层防护完整且互不冲突。

3. **05-visibility.md oracle 防线体系**: §10 完整覆盖了 MCP 查询面约束（fog_of_war + player_view 组合拒绝）、omitted_count 分桶脱敏、dry_run/simulate 脱敏、特殊攻击拒绝码等价策略——所有 oracle 攻击向量均有对应防线。

4. **04-wasm-sandbox.md OS 加固表**: §9.1 统一 OS 加固 checklist 完整覆盖 seccomp/cgroup/namespace 三层，每个约束项标注了允许/禁止、限制值、验证命令、理由——可直接作为部署前验证脚本的输入。

5. **auth.md §5.6a 请求重放分类模型**: 5 级 replay class 模型（read_replay_safe → idempotent_mutation → deploy_mutation → non_idempotent_mutation → admin_critical）设计合理——每级 nonce 策略与存储引擎匹配（Dragonfly TTL 用于轻量去重，FDB version_counter 用于严格防重放，FDB CAS 用于 admin atomic）。尽管 IDL 同步有问题（C2），但分类模型本身是正确的。

---

## CrossCheck

以下交叉验证项指向其他评审员：

### → Architect (rev-dsv4-architect)
- **C2 修复影响**: 若在 IDL 中增加 `deploy_mutation` 和 `non_idempotent_mutation` 枚举值，需确认 Engine tick pipeline 中 Source Gate / Nonce 验证逻辑按 replay_class 分派——当前设计是否已预留扩展点？
- **M4 cgroup pids.max**: 32 还是 16？需根据 Wasmtime 30.0 + Cranelift 编译线程数确定权威值。

### → Interface Designer (rev-dsv4-interface)
- **M2**: 19 个 auth MCP 工具需注册到 IDL——请确认每个工具的 replay_class、required_scope、visibility_filter、rate_limit_key。
- **H1**: 确认 swarm_deploy 权威 rate limit 为 10/h（而非 1/5s）。

### → Game Designer (rev-dsv4-gameplay)
- **L1**: 05-visibility.md §3.1 快照 JSON 示例需同步 omitted_count 分桶格式。

### 通用
- **api_version 收敛** (C1): 建议 R17 合稿时以 YAML IDL 的 0.2.0 为权威，api-registry.md 移除自声明版本号。所有 Markdown 文档的版本号统一改为 `(见 game_api.idl.yaml)` 引用。

---

*评审依据: 仅读取 /tmp/swarm-review-R17/ 下授权子集（9 文件），未读取 /data/swarm/ 仓库或历史评审。*
