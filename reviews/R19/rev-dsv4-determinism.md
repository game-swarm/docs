# R19 确定性/Replay 评审 — DSV4

**评审员**: rev-dsv4-determinism (DeepSeek V4 Pro)
**日期**: 2026-06-18
**评审范围**: 验证 R18 Blocker + 用户裁决是否闭合
**权威源**: `specs/reference/game_api.idl.yaml`

---

## 总体 Verdict: CONDITIONAL_APPROVE

2 GAP 发现，无共识阻塞项。B7 (worker pool 数值不一致) 和 D4 (存储税陈旧平税率引用) 需在 R20 前修复。核心确定性合同（PRNG/IndexMap/f64 禁用/TickInputEnvelope/Replay 存命指令）设计扎实。

---

## 逐项判定表

### R18 共识 Blocker

| ID | 状态 | 证据 |
|----|------|------|
| **B1** YAML vs Markdown 双写不一致 | **CLOSED** | api-registry.md 声明「由 game_api.idl.yaml 自动生成。冲突时以 YAML 为准」。YAML `api_version: "0.3.0"` 与 Markdown 一致。Markdown §变更记录 0.3.0 明确标注「R17 D1/A: YAML IDL 成为唯一机器源」。单事实源合同已建立。 |
| **B2** RejectionReason 未闭合 | **CLOSED** | YAML `rejection_reason.total_canonical_codes: 35`，覆盖 Pipeline(2) + Validation(26) + MCP(3) + Runtime(4) 四层。D2/B 裁决已实施：35 canonical code 为 wire enum，`debug_detail` (512 bytes, non-canonical) 为独立字段，`detail_level` enum (competitive/practice/training) 控制信息泄露。命名规范统一（InsufficientResource/ObjectNotFound/CooldownActive/NotVisibleOrNotFound）。 |
| **B3** MCP Tool 三套名称空间 | **CLOSED** | YAML `mcp_tools.total_tools: 46`（活跃工具，不含 RFC）。每工具携带 7 个安全列：`replay_class` (read_replay_safe/non_replayable/idempotent_mutation/admin_critical)、`visibility_filter` (fog_of_war/owner/admin_scope/none/owner_or_visible)、`rate_limit_key`、`required_scope`。Capability Profiles (onboarding/play/deploy/debug/admin) 控制能力面。Agent WS 通道安全：每消息 seq+MAC (ed25519)。 |
| **B4** Tick/Trace/Persistence 分叉 | **CLOSED** | 05-persistence-contract.md 定义清晰分层：FDB (tick head/manifest/hash) ↔ Object Store (大型 blob) ↔ WAL (未提交 apply 日志) ↔ Keyframe Store (每 K tick 快照)。Tick Commit 序列 Phase A→B→C→D 原子化，hash 链贯穿。01-tick-protocol.md §3.5 FDB 事务 + Bevy 快照恢复 + §9.4 TickTrace 完整性（状态+审计+fuel 三者原子持久化）。不存在「FDB 事务内写一切」与「跨存储双写」的合同空白。 |
| **B5** 安全字段未入机器源 | **CLOSED** | YAML IDL 中每 MCP tool 携带 `replay_class` (4 种)/`visibility_filter` (5 种)/`required_scope`/`subject_source`/`rate_limit_key`。TickTrace Envelope (22 字段) 含 `terminal_state` enum (7 variants, 替代旧 wasm_status)、`world_config_hash`、`mods_lock_hash`、`engine_abi_version`。Agent WS seq+MAC 在 api-registry.md §3.5 明确定义。持久化层 terminal_state 包含 verified/audit_gap/unreplayable/reconstructable 恢复能力分类。 |
| **B6** 经济单源未闭合 | **CLOSED** | api-registry.md §9 ResourceOperation 定义全部 6 个资源操作类型（Harvest/Transfer/Withdraw/TransferToGlobal/TransferFromGlobal/Drain）及 Resource Flow 方向。09-snapshot-contract.md §3 定义 MVP 经济边界（8 核心操作 + Allied Transfer 受限合作 + 7 Future RFC）。06-phase2b-system-manifest.md S29 resource_ledger 为最后执行系统。RNG namespace `loot` 隔离（01-tick-protocol.md §9.5）。经济操作单入口（Resource Ledger）已建立。 |
| **B7** 容量合同不可证明 | **GAP** | **数值不一致**：engine.md §3.4.2 Worker Pool 推导定义 `MAX_POOL = 1000（hard cap，编译期常量）`，而 api-registry.md §5.5 定义 `Worker pool max = max_pool = 256, world.toml 可调`。若 MAX_POOL 为绝对硬上限而 max_pool 为运行时默认值（256 ≤ 1000），则功能上一致但文件中**无显式调和文本**。位置：engine.md L345 `MAX_POOL = 1000` vs api-registry.md L414 `max_pool = 256`。需在 api-registry.md 中补充 `max_pool ≤ MAX_POOL (1000)` 约束声明，或在两文件之一统一数值。 |

### R18 用户裁决

| ID | 状态 | 证据 |
|----|------|------|
| **D1** api-registry.md 全量生成 | **CLOSED** | api-registry.md 覆盖 11 个完整章节：CommandAction (19)、RejectionReason (35)、MCP Tools (46)、Host Functions (5)、全局容量限制 (25 参数)、TickTrace Envelope (22 字段)、Direction4、SwarmError、ResourceOperation、Deploy (deploy_mutation)、Persistence (async_object_store_upload)。版本 0.3.0，与 YAML 逐项对应。 |
| **D2** RejectionReason canonical+debug_detail | **CLOSED** | YAML `rejection_reason.total_canonical_codes: 35` + `debug_detail.max_length: 512` + `detail_level` enum (competitive/practice/training, default=competitive)。api-registry.md §2 同步。wire enum 保持稳定（35 code），详细上下文走 debug_detail 独立字段。 |
| **D3** Recycle refund lifespan 10-50% | **CLOSED** | 09-snapshot-contract.md §3.1: `RecycleRefund: 拆除建筑/回收 drone，按 recycle_refund_base（50%）退还资源，最低 recycle_refund_min（10%）`。范围 10%-50% 明确。engine.md §3.2 确认 Recycle 走标准 death_mark→death_cleanup 路径。 |
| **D4** Storage tax tiered 0/1/5/20bp | **GAP** | 09-snapshot-contract.md §3.1 仍引用**平税率** `StorageTax: 仓库存储税（0.1%/tick）`。tiered 结构 `[(30,0),(60,1),(85,5),(100,20)]` 存在于本评审范围外文件（design/gameplay.md §8、specs/core/08-resource-ledger.md §2.2）但**不在评审授权文件内**。位置：09-snapshot-contract.md L192。09-snapshot-contract.md 需更新为引用 tiered 公式（如 `storage_tax_tiers = [(30,0),(60,1),(85,5),(100,20)]`，详见 specs/core/08-resource-ledger.md），而非陈旧平税率。 |
| **D5** blob 异步上传 | **CLOSED** | 05-persistence-contract.md §2 Phase C: FDB commit 成功 → 入队异步任务 write_blob → upload_status 跟踪 (pending/uploading/complete/failed)。api-registry.md §11: async_object_store_upload fire-and-forget, FDB 仅存 manifest + hash pointer。失败语义完整（重试 3 次指数退避 → failed → replay gap 标记 audit_gap）。D5/B 裁决已实施。 |
| **D6** soft_launch 3阶段PvP | **N/A** | soft_launch 3 阶段 PvP 过渡机制 (D6/B) 不在本评审授权文件列表中。此为 gameplay 设计域裁决，非确定性关注点。从本评审视角标记为 N/A。 |
| **DA1** deploy_mutation replay_class | **CLOSED** | api-registry.md §10: deploy_mutation 模式 —— WASM blob 异步上传至 object store，FDB 仅提交小型 manifest (blob_hash + fdb_version_counter)。YAML `swarm_deploy.replay_class: idempotent_mutation`。fdb_version_counter (u64, FDB 事务内递增) 为 replay 提供严格全序。激活延迟到 tick boundary 保证确定性调度。 |
| **DA2** f64→定点 | **CONCERN** | YAML IDL 中 **11 处** f64 存在于 `read_replay_safe` 工具的输出 schema：swarm_get_resources.income_rate、swarm_get_path.distance/cost、swarm_get_controller.progress、swarm_get_economy.{income,expenses,storage_tax,maintenance}、swarm_get_drone_efficiency.efficiency、swarm_simulate.confidence、resources/read.base_value。engine.md §3.4.8 和 01-tick-protocol.md §7.1 均声明「数值：整数 + 定点数，禁用 f64」。**缓解**：这些为 MCP 只读查询的输出显示值，不反馈入游戏状态计算——引擎内部使用 u64/i64 定点整数，f64 仅用于客户端展示。不影响 replay determinism。**建议**：将 MCP 输出 schema 中的 f64 替换为 `fixed_point` 或 `string` (如 "12345" → 123.45 的显示转换由客户端完成)，消除「禁止 f64」原则与 machine source 之间的表面矛盾。 |
| **DA3** worker pool 256 default | **CLOSED** | api-registry.md §5.5: `Worker pool size = min(max_pool, active_players), max_pool 默认 256, World 模式`。默认值 256 已权威注册。与 B7 的 1000 hard cap 关系需调和（见 B7 GAP）。 |

---

## Replay Gaps

1. **specs/gameplay/04-replay-recording.md 缺失**：该文件在任务授权列表中但不存在于 `/tmp/swarm-review-R19/` 路径下。Replay recording 相关内容分散在 01-tick-protocol.md §6.3（回放协议、记录、执行、Wasmtime 版本共存）、05-persistence-contract.md §4（Replay 恢复、Replay Verifier 输入）、engine.md §3.3（回放输入封套 TickInputEnvelope）。若 04-replay-recording.md 原计划为集中式规范，考虑在 R20 中从现有文件提取内容创建或删除授权列表中的引用。

2. **design/architecture.md 缺失**：同样在任务授权列表中但不存在。架构内容已整合到 design/README.md 和 design/engine.md 中。若此为有意合并，建议更新文档导航（design/README.md 的表格中无 architecture.md 条目，已自身一致）。

---

## Formal State Issues

1. **Worker pool 数值二义性** (B7): 两个权威文档对同一参数给出不同数值（1000 vs 256），缺少 `max_pool ≤ MAX_POOL` 调和声明。在确定性上下文中，worker pool 大小影响 COLLECT 阶段并行度——虽然不直接影响世界状态（WASM 不感知 pool 大小），但影响超时行为和资源竞争。需单一权威声明。

2. **09-snapshot-contract.md 陈旧平税率** (D4): 该文件 §3.1 的 StorageTax 仍为 `0.1%/tick`（10bp），而 D4 裁决要求 tiered 0/1/5/20bp。tiered 公式已在其他文档中定义但 09-snapshot-contract.md 未更新引用。这属于文档一致性缺陷，不直接影响确定性但可能误导实现者。

3. **MCP output f64 表面矛盾** (DA2): 11 处 f64 在 read_replay_safe 工具的输出 schema 中。虽不影响 replay（展示层），但「禁用 f64」的绝对声明与 machine source 中的 f64 存在形成审计表面矛盾。建议标记为 `fixed_point_display` 或替换为整数/字符串类型。

---

## CrossCheck: 建议其他方向验证

1. **安全评审 (Security)**: 验证 MCP output f64 是否可能通过 AI agent 决策路径间接影响世界状态（如 agent 读取 income_rate: f64 后选择不同的部署策略——若 f64 在不同平台上产生微小差异，可能导致 agent 行为分叉）。

2. **经济评审 (Economy)**: 验证 09-snapshot-contract.md §3.1 的平税率与 specs/core/08-resource-ledger.md 的 tiered 公式之间的迁移路径——MVP 中 StorageTax 实际按哪个合同实现？

3. **架构评审 (Architecture)**: 确认 design/architecture.md 和 specs/gameplay/04-replay-recording.md 的缺失是否为有意合并——若是，更新任务授权文件列表；若否，补充缺失规范。

---

## 评审边界声明

- **未读取** `/data/swarm/` 代码仓库、旧评审、reviews/ 目录、ROADMAP
- **未读取授权列表外文件**（design/gameplay.md、specs/core/08-resource-ledger.md 等仅在 search_files 中被动匹配，未主动读取内容）
- **以 IDL YAML 为权威源**（冲突时以 YAML 为准）
- **非本方向项标记为 N/A**（D6 soft_launch 属 gameplay 域）
- **不重新评审设计本身**，仅验证 R18 闭合状态
