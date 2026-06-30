# R44 Cross-Cutting Review — deepseek-v4-pro

> Reviewer: rev-dsv4-cross-cutting (Architecture Reviewer, DeepSeek V4 Pro)
> Date: 2026-06-30
> Scope: Security, Performance, Operational, Edge Cases, Missing Specs
> Documents reviewed: 38 markdown files across design/, specs/core/, specs/security/, specs/gameplay/, specs/reference/

---

## §1 Critical Findings (Blockers)

### C1: Gateway 实现语言矛盾 — 跨文档不一致

**文件**:
- `design/README.md` L56 — 仓库列表含「swarm/gateway — Rust API 网关」
- `design/architecture.md` L69 — 架构图标注「Gateway Rust (axum)」
- `specs/security/gateway-protocol.md` L13 — 架构图标注「Gateway (Go, 无状态)」
- `specs/security/mcp-security.md` L2, L83 — 多次引用 Gateway 为 HTTP/SSE 前端

**问题**: gateway-protocol.md §1 明确标注 Gateway 的语言为 Go，与 design/ 中所有文档的 Rust 声明矛盾。这是设计层的根本分歧——Gateway 的实现语言直接影响 WASM 分发路径的通信协议（Go NATS 客户端 vs Rust async-nats）、运维部署面（Go 编译产物 vs Rust 编译产物）、以及安全审计面（Go GC vs Rust 所有权模型）。

**影响**: 实现团队收到矛盾指令；运维部署清单需要两套编译链；安全审计面不可确定。

**修复建议**: 在 design/ 和 specs/ 之间统一定义 Gateway 实现语言并同步修改所有文档。推荐 Rust (axum) 以保持技术栈一致。

**Severity**: Critical

---

### C2: Snapshot Contract §1.3 截断优先级与 Incremental Snapshot §3 二次排序键冲突

**文件**:
- `specs/core/snapshot-contract.md` L61-L83 — 确定性截断顺序: 距离桶 → entity_id 字典序
- `specs/core/incremental-snapshot.md` L52-L58 — 增量模式截断排序: `(entity_priority_bucket, last_modified_tick DESC, entity_id)`

**问题**: 两份规范定义了不同的截断排序键。snapshot-contract.md 使用单键 `entity_id`，incremental-snapshot.md 使用双键 `(last_modified_tick DESC, entity_id)`。当同一距离桶内有多个截断候选时，两份规范产生不同的截断结果，破坏确定性合同。

**影响**: 全量快照模式与增量快照模式下的截断结果不同 → WASM 模块接收到的 snapshot 不同 → 相同输入产生不同 tick 输出 → 破坏 replay 一致性。这是一个静默的确定性 bug。

**修复建议**: incremental-snapshot.md 必须引用 snapshot-contract.md 作为截断排序的权威源，或 snapshot-contract.md 升级为统一规范覆盖两种模式。不能两处独立定义排序键。

**Severity**: Critical

---

### C3: Resource Ledger §2.4 — Controller age repair 缺乏 TickTrace 归因路径

**文件**:
- `specs/core/resource-ledger.md` L148-L160 — Controller repair 明确声明「不作为 Resource Ledger 收支公式结算」
- `specs/core/resource-ledger.md` L5-L10 — 确定性账本原则要求「每笔资源变动记录到 TickTrace」

**问题**: Controller repair 的 age 降低操作既不是 Resource Ledger 操作，也没有独立的 TickTrace 归因路径。这意味着 Controller repair 是唯一一个**修改实体状态但不产生审计记录**的引擎操作。Replay verifier 无法验证 age repair 的正确性，反作弊审计链缺失。

**影响**: 确定性 replay 可恢复 drone age 值（从状态变更中），但无法证明 age 降低的合法性——攻击者可能修改 engine binary 跳过 repair range/queue/capacity 约束。审计缺失。

**修复建议**: 方案 A — 在 TickTrace 中新增 `AgeRepair` 事件类型，记录 `(drone_id, repair_source, repair_amount, repair_type)`。Controller repair 不涉及资源扣费（免费），但必须记录事件归属。方案 B — 将 Controller repair 纳入 Resource Ledger 作为零费率的 `AgeRepair` 操作类型（fee_bps=0），沿用现有 TickTrace 归因框架。

**Severity**: Critical

---

## §2 Design Tensions (Inconsistencies, Conflicts)

### T1: engine.md 声称 "31 systems" — 但计数方式不透明

**文件**:
- `design/engine.md` L291-L292 — 标注「31 systems（Stage 2a inline 6 + Stage 2b queued 25）」
- `specs/core/phase2b-system-manifest.md` L86 — 「共计 31 个 system（新增 S22a leech_buffer + S22b fabricate_buffer，共 31）」

**问题**: engine.md 的 31=6+25 拆分与 phase2b-system-manifest.md 的 31 计数一致，但 manifest 中 S01-S06（Stage 2a）被标记为 inline handler 而非 manifest system，S07-S29（23个）+ A01 action_dispatch（不计入）= 23 个 Stage 2b systems + 6 inline = 29，加上 S22a/S22b 为 31。但 S22a/S22b 的 ID 使用了 `S22a`/`S22b`（非独立 S 编号），这可能与 S16-S21 的编号连续性混淆。

**影响**: 中等——不影响实现正确性，但影响规范可读性和新人理解。编号体系 S01-S31 并不线性连续（S22a/S22b 跳出）。

**修复建议**: 将 S22a/S22b 重新编号为 S30/S31，或在 Manifest §1 的 Schedule 中增加编号连续性注释。

**Severity**: Low

---

### T2: Allied Transfer "Restricted Intercept" 与 Resource Ledger 之间税率双写风险

**文件**:
- `specs/core/resource-ledger.md` L74-L77 — `allied_transfer_fee = 200 bp`, `allied_transfer_delay = 200 tick`
- `specs/core/snapshot-contract.md` L209-L235 — 运输中拦截机制，含成功率公式

**问题**: Allied Transfer fee (200bp) 在 Resource Ledger 中定义，但拦截成功后攻击方获得 50% 资源（snapshot-contract.md L252）。这引入了一种双写风险：若 Resource Ledger 对拦截的理解与 snapshot-contract 不一致（例如，拦截后是否仍扣原定的 200bp 转移费？），会产生经济账本分歧。

**影响**: 中等——当前两份文档独立定义了相关的经济参数，但没有交叉引用验证一致性。若后续修改其中一处而未同步另一处，会产生经济漏洞。

**修复建议**: snapshot-contract.md §3.2a 应明确声明「拦截结算后，原 Allied Transfer 费用处理方式见 Resource Ledger §2.1」。Resource Ledger 应定义 `TransferIntercepted` 操作类型的 fee 返还规则。

**Severity**: Medium

---

### T3: CVE-SLA 监控范围覆盖 crypto crates 但未覆盖 ECS/序列化核心

**文件**:
- `specs/security/CVE-SLA.md` L7-L10 — 监控范围含 `blake3`, `ed25519-dalek`, `ring`, `rustls`, `tokio`, `serde`, `serde_json`, `wasmparser`, `cranelift-codegen` 等
- `specs/core/persistence-contract.md` L51-L52 — `canonical_codec_version` 依赖 Rust (`serde_swarm`) 和 Go (`swarm-codec-go`) 双实现

**问题**: CVE-SLA 监控范围遗漏了以下对确定性至关重要的 crate:
- `bevy_ecs` — 确定性调度与 entity 迭代的核心依赖
- `serde_swarm` — canonical serialization 的 Rust 实现
- `redb` — 权威持久化层
- `async-nats` — Engine ↔ Sandbox 通信链路

这些 crate 中的安全漏洞或行为变更可导致与 Wasmtime CVE 同等严重的确定性破坏或世界状态不一致。

**影响**: High — 在 CVE-SLA 监控范围外的 crate 漏洞可能被遗漏，导致确定性合同被静默破坏。

**修复建议**: 将 `bevy_ecs`, `redb`, `async-nats` 加入 CVE-SLA 监控范围（至少 High 级别响应）。`serde_swarm` 作为 canonical serialization 实现应享有与 `serde` 同等的监控优先级。

**Severity**: High

---

### T4: Staging GC 在 GC worker 崩溃时存在静默积累风险

**文件**:
- `specs/core/tick-protocol.md` L460-L467 — Staging GC worker 每 10s 扫描，最大残留 < 15s
- `specs/core/persistence-contract.md` L355-L356 — Staging 孤立行由 GC 清理

**问题**: Staging GC 被描述为周期性 worker（每 10s 扫描），但如果 GC worker 自身崩溃且未被监控到（进程信号丢失、OOM killed without restart），staging 行将无限积累。文档中没有 GC worker 的健康检查/心跳机制或保底清理策略。

**影响**: Medium — staging 行是 tiny rows（~2KB each），正常操作下风险低。但在高频率 GlobalTickCommit 失败（如磁盘间歇性故障）场景下，staging 行可能在数小时内积累到 GB 级，触发磁盘满 + redb 写入失败连锁故障。

**修复建议**: 方案 A — 在 Engine 主健康检查 (`/healthz`) 中增加 GC worker 存活检查。方案 B — 在 Engine 启动时执行一次 staging 目录扫描清理（保底）。方案 C — 给每行 staging 写入添加 TTL（如 60s），redb 支持基于时间的自动清理策略。

**Severity**: Medium

---

### T5: engine.md 的 Gateway 语言与 gateway-protocol.md — 已有 C1 覆盖，此条为扩展

**文件**:
- `design/architecture.md` — 多处标注 Rust
- `specs/security/gateway-protocol.md` — 标注 Go

**附加发现**: `specs/security/gateway-protocol.md` L15 架构图中的 Gateway 既标注 "Go" 又标注 "无状态"。design/architecture.md L69 标注 "Rust (axum)"。这不仅是语言矛盾——两种语言对应的 WebSocket 库、NATS 客户端、MCP 协议库生态完全不同，Gateway 的安全审计面（内存安全、并发模型）也因此不同。Rust 和 Go 的选择直接决定 Gateway 是否能与 Engine 共享代码、是否能嵌入 Engine 进程。

**Severity**: Critical (covered by C1)

---

## §3 Suggestions (Improvements, Simplifications)

### S1: 运维文档中缺少 World Upgrade/Migration 流程

**文件**: `docs/RUNBOOK.md` (全文件)

**问题**: RUNBOOK 覆盖了启动、备份、恢复、降级、监控，但缺少以下关键运维场景:
- World 规模扩张（从单 shard 升级到多 shard）
- world.toml 经济参数热更新流程（哪些参数可在线修改？哪些需要重启？）
- Engine 版本升级 + world state 迁移（redb schema 变更时的迁移步骤）
- Sandbox Container 集群扩容/缩容 runbook

**建议**: 在 RUNBOOK.md 新增 §8「World Lifecycle Operations」覆盖以上场景。至少需要标注哪些操作需要停机、哪些可以在线执行。

**Severity**: Medium

---

### S2: COLLECT 阶段 Engine 侧单点超时等待风险

**文件**:
- `design/engine.md` L250-L251 — per-player sandbox deadline 2500ms
- `specs/core/distributed-sandbox.md` L93-L96 — Engine 等待 NATS reply，timeout=2500ms

**观察**: COLLECT 阶段 Engine 对每个玩家的 reply 等待是**串行收集**还是**并行收集**？文档说「遍历活跃玩家，并行分发」，但没说 Engine 收集 reply 时是逐个阻塞等待还是异步收集。如果 Engine 逐个 `request(reply_timeout=2500ms)` 串行等待，那么一个慢玩家会阻塞后续玩家的 COLLECT 完成，实际 COLLECT 延迟 = `N_players × max(WASM_time, timeout)`。

**建议**: 在 distributed-sandbox.md 或 engine.md 中明确说明 Engine 是否使用异步 reply 收集（如 `nats.request_many` 或 `tokio::select!`）。

**Severity**: Medium

---

### S3: 缺少 Blob Store 降级时的 replay 可用性正式声明

**文件**:
- `specs/core/persistence-contract.md` L60-L62 — 「WASM 模块 blob 非 replay-critical」
- `design/architecture.md` L250-L252 — 「Blob Store 不是权威源——redb 的 TickCommitRecord 保存所有 blob 的 content hash 指针」

**问题**: 两份文档都声明 Blob Store 不是权威源，但没有正式定义 Blob Store 完全离线时 replay verifier 的最低操作模式。具体地：如果 S3 backend 完全不可用且 Keyframe Store 仅剩本地存储，replay 能覆盖多远的历史？

**建议**: persistence-contract.md 增加 §5.4「Blob Store Degraded Replay」明确声明最低 replay 续航。

**Severity**: Low

---

### S4: economy-balance-sheet.md 的存储税计算依赖「连续边际公式」但未提供验证工具

**文件**:
- `design/economy-balance-sheet.md` L193-L194 表中 `storage tax formula` 列标注 `continuous integral floor`
- `specs/core/resource-ledger.md` L98-L112 — 存储税连续边际税率公式

**观察**: balance-sheet 中的存储税数值注明「continuous integral floor」，但 balance-sheet 本身不包含具体的积分计算代码或可复现的验证路径。replay verifier 需要独立实现相同的积分公式才能验证 TickTrace 中的存储税记录。

**建议**: 在 resource-ledger.md 中增加 §2.2.1「存储税积分参考实现」（伪代码或 Python snippet），确保 replay verifier 能够独立复现。balance-sheet 中的数值可以附带简化的手工可验证样例（如 1,000,000 容量下 750,000 存量 = 45/tick 的逐步计算）。

**Severity**: Low

---

### S5: Gateway 的安全 header 策略在 mcp-security.md 与 gateway-protocol.md 之间有细微差异

**文件**:
- `specs/security/gateway-protocol.md` L28-L31 — 缺少 `X-Swarm-Transport` → 401; 证书 audience 不匹配 → 403
- `specs/security/mcp-security.md` L93 — Browser endpoint 要求 CSRF token + SameSite=Strict + Fetch Metadata headers

**问题**: gateway-protocol.md 是所有 transport 的统一安全规范，而 mcp-security.md 详细定义了 Browser/Agent 两条路径的安全策略。两份文档之间的引用关系清晰（mcp-security 多次引用 gateway-protocol），但也存在单向依赖——gateway-protocol 定义 transport auth matrix 但不引用 mcp-security 的 browser-specific CSRF/SameSite/Sec-Fetch 约束。

**建议**: gateway-protocol.md §8「安全」表增加一行 Browser-specific 约束引用到 mcp-security.md §2.1。

**Severity**: Low

---

## §4 Cross-Reference Matrix

### 4.1 文档间引用完整性矩阵

| 源文档 | 应引用 | 当前状态 | 问题 |
|--------|--------|---------|------|
| `gateway-protocol.md` | `mcp-security.md` §2.1 Browser 约束 | 未引用 | T5 相关 |
| `snapshot-contract.md` | `incremental-snapshot.md` 截断排序 | 未引用 | C2 |
| `incremental-snapshot.md` | `snapshot-contract.md` 权威截断合同 | 未引用 | C2 |
| `resource-ledger.md` | `snapshot-contract.md` §3.2a 拦截结算 | 未引用 | T2 |
| `CVE-SLA.md` | `persistence-contract.md` canonical codec | 未引用 | T3 |
| `engine.md` | `phase2b-system-manifest.md` 31-system 编号 | 已引用 | T1 |
| `economy-balance-sheet.md` | `resource-ledger.md` 存储税公式 | 已引用 | ✅ |
| `gameplay.md` | `resource-ledger.md` §2 统一参数表 | 已引用 | ✅ |

### 4.2 安全面覆盖矩阵

| 安全维度 | 覆盖文档 | 覆盖程度 | 缺口 |
|---------|---------|---------|------|
| 沙箱隔离 | `wasm-sandbox.md` §§4,9 | ✅ 全面 | — |
| 网络隔离 | `wasm-sandbox.md` §4.3 | ✅ 双层 (netns + seccomp) | — |
| 认证 | `auth.md`, `command-source.md` §3 | ✅ 应用层证书链 | — |
| 授权 | `command-source.md` §2, `mcp-security.md` §2.2a | ✅ per-tool auth mode | — |
| 可见性 | `visibility.md` | ✅ 10 章节全面覆盖 | — |
| Oracle 防线 | `visibility.md` §10, `snapshot-contract.md` §4 | ✅ omitted_count 脱敏 | — |
| CVE 响应 | `CVE-SLA.md` | ⚠️ 监控范围不足 | T3 |
| 传输安全 | `gateway-protocol.md` §8 | ✅ | — |
| 确定性安全 | `tick-protocol.md` §3.1, `engine.md` §3.3 | ✅ | — |

### 4.3 性能面覆盖矩阵

| 性能维度 | 覆盖文档 | 覆盖程度 | 缺口 |
|---------|---------|---------|------|
| Tick 预算 | `engine.md` §3.4.1 | ✅ 5 阶段逐项预算 | — |
| 容量推导 | `engine.md` §3.4.2 | ✅ 500/1000 推导 | — |
| COLLECT 水平扩展 | `distributed-sandbox.md` | ✅ NATS queue-group | — |
| EXECUTE 瓶颈分析 | `architecture.md` §2, §10 | ✅ 明确标注串行瓶颈 | — |
| 分片扩展 | `shard-protocol.md` | ✅ 静态坐标分片 | — |
| 快照优化 | `engine.md` §3.2 (两阶段), `incremental-snapshot.md` | ✅ | — |
| 缓存 | `architecture.md` §6a (Moka) | ✅ | — |
| Benchmark gate | `persistence-contract.md` §8.3 | ✅ 9 项 benchmark | — |
| 运维规模指导 | — | ❌ 缺失 | S1 |

### 4.4 运维面覆盖矩阵

| 运维维度 | 覆盖文档 | 覆盖程度 | 缺口 |
|---------|---------|---------|------|
| 启动序列 | `RUNBOOK.md` §1 | ✅ | — |
| 备份恢复 | `RUNBOOK.md` §3 | ✅ | — |
| 降级模式 | `RUNBOOK.md` §4 | ✅ 4 种降级场景 | — |
| 监控指标 | `RUNBOOK.md` §5 | ✅ 8 项指标+阈值 | — |
| 灾难恢复 | `RUNBOOK.md` §6 | ✅ 6 步 DR 流程 | — |
| 密钥轮换 | `RUNBOOK.md` §2 | ✅ world_seed + CA | — |
| 升级/迁移 | — | ❌ 缺失 | S1 |
| 多 shard 运维 | — | ❌ 缺失 | S1 |
| redb 恢复 | `persistence-contract.md` §§9-10 | ✅ Keyframe 独立存储 | — |
| Blob Store 运维 | `architecture.md` §6a | ⚠️ 仅配置说明 | S3 |

### 4.5 跨文档交叉引用待办

| ID | 类型 | 从 | 到 | 描述 |
|----|------|----|----|------|
| CX-1 | 新增引用 | `snapshot-contract.md` §1.3 | `incremental-snapshot.md` §3 | 声明全量截断排序为权威源，增量模式引用而非重定义 |
| CX-2 | 新增引用 | `resource-ledger.md` §2.1 | `snapshot-contract.md` §3.2a | 声明拦截结算后的 fee 处理规则 |
| CX-3 | 新增引用 | `CVE-SLA.md` §监控来源 | `persistence-contract.md` §2.1 | 加入 canonical codec 双实现 crate 监控 |
| CX-4 | 新增条目 | `RUNBOOK.md` | — | 新增 §8 World Lifecycle (upgrade/migration/shard expansion) |
| CX-5 | 新增声明 | `engine.md` §3.2 | `distributed-sandbox.md` §3 | 明确 Engine 侧 COLLECT reply 收集为并行异步 |

---

## §5 Summary

### Blocker 裁决需求 (D-items)

| ID | Severity | 描述 | 裁决建议 |
|----|----------|------|---------|
| D-C1 | Critical | Gateway 语言矛盾 (Rust vs Go) | 统一为 Rust (axum) 或 Go，同步全部文档 |
| D-C2 | Critical | Snapshot 截断排序键两份规范独立定义 | snapshot-contract.md 为权威源 |
| D-C3 | Critical | Controller age repair 无 TickTrace 归因 | 新增 AgeRepair 事件类型 |

### 非阻塞待办

- **High**: T3 (CVE-SLA 监控范围扩展) — 加入 bevy_ecs, redb, async-nats
- **Medium**: T2, T4, S1, S2 — 经济双写风险、Staging GC 保底、运维升级流程、COLLECT 并行收集
- **Low**: T1, S3, S4, S5 — 编号连续性、Blob Store 降级声明、存储税验证工具、Browser 约束引用

### 亮点

1. **Sandbox 隔离四层防御** (seccomp + cgroup v2 + netns + Wasmtime) — 业界顶级的 WASM 沙箱设计，clone flags matrix 和 9.1 OS 加固 checklist 极其详尽
2. **确定性纵深防御** — 从数据结构 (BTreeMap 禁止 HashMap)、种子管理 (Blake3 XOF)、ECS 迭代顺序到 snapshot 截断排序，形成了完整的确定性合同链
3. **Oracle 防线闭合 (visibility.md §10)** — omitted_count 分桶脱敏、特殊攻击拒绝码等价类、fog_of_war + player_view 组合验证拒绝——这三个机制组合形成了几乎无侧信道的信息泄露防护
4. **持久化分层 (redb + Blob Store + Keyframe + WAL)** — replay-critical / debug-rich / recover-only 三层语义分离，Shadow Write + Atomic Publish 消除了 per-room partial commit 窗口
5. **Overload 永久锁死数学证明 (command-validation.md §3.9)** — 用形式化推导证明了机制安全性，这是设计评审中的黄金标准
6. **经济模型的形式化收敛证明 (economy-balance-sheet.md §4)** — O(n²) 维护费 + 连续边际存储税的 anti-snowball 证明，用数学保证了长期经济可持续性
7. **Per-tool auth mode (mcp-security.md §2.2a)** — 三层粒度 (web_session_ok / app_cert_required / admin_scope_required) 的认证模型是 API 安全设计的标杆