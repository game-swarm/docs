# R42 架构评审报告 — rev-glm-architect

**Reviewer**: rev-glm-architect (GLM-5.2 via newapi)
**Round**: R42
**Scope**: architecture.md, engine.md, tick-protocol.md, persistence-contract.md, wasm-sandbox.md, snapshot-contract.md, shard-protocol.md, distributed-sandbox.md, incremental-snapshot.md, command-source.md
**方向**: 架构（模式识别、接口直观性、抽象分层、跨模块数据流、组件耦合度）

---

## 1. Verdict

**CONDITIONAL_APPROVE**

整体架构清晰、分层合理。COLLECT → EXECUTE → COMMIT/BROADCAST 三段模型与两层计算（WASM 非权威 / Engine 权威）的抽象贯穿始终，文档间一致性总体较好。但存在若干 Cross-doc 术语残留、shard-protocol 与 architecture.md 间模型冲突、以及 persistence-contract 中 keyframe 位置与 architecture.md §10.2 的自相矛盾，需在有阻塞性的条目修复后达成完全推荐。

---

## 2. 发现的问题

### A-C1: shard-protocol 与 architecture.md 分片模型矛盾 [Critical]

**文件**: `specs/core/shard-protocol.md` §2, §5; `design/architecture.md` §2

**问题**: `shard-protocol.md` §2 声称 `shard_assignment = 一致性哈希 (Jump Hash)`，§5 声称「所有分片在同一进程内提交到同一个 `.redb` 文件」。而 `architecture.md` §2 明确指出「shard_id = f(room_x, room_y)，从配置 O(1) 计算，无需运行时 coordinator」「无 cluster、无 leader election、无 gossip」「每 shard 一个 Engine 进程 + 一个 redb 文件」。

两份文档描述的是完全不同的分片拓扑：
- architecture.md：静态坐标分片，per-shard 独立 Engine + 独立 redb，多进程模型
- shard-protocol.md：Jump Hash 动态分配，单进程多 shard 共享 redb，弹性分片模型

shard-protocol.md §4.2 描述的「跨分片 Combat 两阶段协议（intent broadcast + settlement ack）」在 architecture.md 的单 shard 单 writer 模型下根本不适用——architecture.md §10 明确说「单个 shard 内的 EXECUTE 不能拆成多台机器并行写入」。

**影响**: 实现者无法判断到底是遵循哪个模型。redb 文件布局、Engine 进程模型、跨 shard 通信协议全是冲突的。

**修复建议**: 这是一个 D-item。需要确定最终分片模型：
- 方案 A：architecture.md 的静态坐标分片为最终模型，shard-protocol.md 需要重写为 static partition 模型，移除 Jump Hash 和单进程多 shard 共享 redb 表述。
- 方案 B：shard-protocol.md 的弹性分片为最终模型，architecture.md §2 §3 §10 需要大幅重写以反映 Jump Hash + 单进程多 shard 部署。

---

### A-C2: persistence-contract keyframe 存储位置与 architecture.md 矛盾 [Critical]

**文件**: `specs/core/persistence-contract.md` §10.2; `design/architecture.md` §6a; `specs/core/incremental-snapshot.md` §4

**问题**: 
- `persistence-contract.md` §10.2 明确声明「Keyframe 不放在 redb 内——否则 redb 损坏时 keyframe 一并丢失」，存储位置为 `$REDB_PATH.keyframes/{tick}.snap`（独立文件）。
- `architecture.md` §6a 的 Blob Store 表格中，`Keyframe Snapshot` 被列为 Blob Store 数据类型（「✅ 可从 delta 重建」/ 保留策略 30d）。
- `incremental-snapshot.md` §4 声称「Keyframe 写入 `persistence-contract.md` 定义的 blob store；modification_set 写入 redb」。

三份文档对 keyframe 的存储位置给出三种不同答案：独立文件、Blob Store、blob store。

**影响**: Keyframe 是灾难恢复的关键锚点。存储位置不一致会导致实现者将 keyframe 放入错误位置，灾难恢复时找不到 keyframe。

**修复建议**: 统一为 persistence-contract.md §10.2 的定义——keyframe 存储为独立文件（`$REDB_PATH.keyframes/{tick}.snap`），不在 redb 内，不在 Blob Store 内。architecture.md §6a Blob Store 表格中移除 `Keyframe Snapshot` 行（keyframe 由 persistence-contract 自己管理），incremental-snapshot.md §4 修正为引用 persistence-contract §10.2 的独立文件路径。

---

### A-H1: persistence-contract.md §5.3 残留 FDB 术语 [High]

**文件**: `specs/core/persistence-contract.md` §5.3

**问题**: §5.3 Replay Verifier 输入声明：`输入: (start_tick, end_tick, fdb_manifest_list, object_store_blobs)`。`fdb_manifest_list` 是 FoundationDB 术语，但项目使用 redb。这是 R41 清理 FDB 时遗漏的残留。

此外 §8.2 标题为「Room-Partition redb WriteTransaction 策略」但 §8.1 和实现约束表中多处引用旧模型术语（如 `cross-room conflict` 语义描述引用了已删除的 per-room 独立 commit 语义）。

**影响**: 术语不一致导致实现者困惑——项目不存在 FoundationDB。

**修复建议**: 全文替换 `fdb_manifest_list` → `redb_manifest_list`。全局搜索 `fdb_` 前缀的所有残留并替换。

---

### A-H2: persistence-contract.md §10.6 存储分层表中 Blob Store 仍使用旧术语 [High]

**文件**: `specs/core/persistence-contract.md` §10.6

**问题**: §10.6 的存储分层总览图中「审计: Blob Store (大 blob, 7-180d)」行声称内容包含「RichTraceBlob, delta, WASM binaries」。但 architecture.md §6a 已将 Blob Store 重命名为「Blob Store（非权威二进制存储）」并列出四种数据类型（RichTraceBlob, ReplayArtifact, DeployPayload, Keyframe Snapshot）——其中 keyframe 不应在 Blob Store。persistence-contract.md §10.6 仍列 delta 在 blob store 范围，但 delta（modification_set）实际写入 redb。

**影响**: 存储分层定义交叉矛盾，容易让实现者将 redb 的 delta 和 keyframe 混入 Blob Store。

**修复建议**: 对齐 architecture.md §6a 的 Blob Store 定义，移除 persistence-contract.md §10.6 中「delta」行（delta 写入 redb，不写 Blob Store），并从 blob store 描述中移除 keyframe。

---

### A-H3: engine.md §3.4.7 残留「远期方向」措辞 [High]

**文件**: `design/engine.md` §3.4.7

**问题**: §3.4.7 最后一段：「水平分片为远期方向，届时再评估存储层是否需要升级」。这违反 `architecture.md` §1 / §9 / AGENTS.md 中「设计即终态——不允许 defer 到远期方向」「禁止延期词」的核心设计原则。architecture.md §2 已明确定义静态坐标分片为当前设计，shard-protocol.md 也声称已纳入核心设计。

**影响**: 设计原则违规，暗示分片不是当前设计的一部分，与架构文档矛盾。

**修复建议**: 移除「水平分片为远期方向，届时再评估存储层是否需要升级」整句。替换为对 architecture.md §2 和 shard-protocol.md 的引用。

---

### A-H4: shard-protocol.md 目标规模与 architecture.md 容量合同矛盾 [High]

**文件**: `specs/core/shard-protocol.md` §1; `design/architecture.md` §2; `design/engine.md` §3.4.2

**问题**: `shard-protocol.md` §1 声称「世界规模 >5,000 drone / 多节点部署」。但 `engine.md` §3.4.2 容量合同明确「Active drones: target 5000 / hard cap 10000」「Active players: target 500 / hard cap 1000」是「单节点，World 模式」的容量。architecture.md §2 指出多 shard 是「按坐标范围增加 shard」实现水平扩容，而非「多节点部署同一 shard」。

shard-protocol.md §1 的描述暗示单 shard 容量超过 5000 drone 才需要分片，但实际分片是以房间范围切分，单 shard target 5000 drone 就已是 hard cap。

**影响**: 容量触发分片的阈值与 architecture.md 的分片模型不匹配，实现者可能误以为单 shard 支撑任意 drone 数。

**修复建议**: shard-protocol.md §1 修改为「当单 shard 容量达到 hard cap（10000 drone / 1000 player），或需要多节点部署时启动。分片以坐标范围切分，每 shard 独立 Engine + redb」。同时与 architecture.md §2 的静态坐标分片模型对齐。

---

### A-H5: tick-protocol.md §6.3.1 残留 `redb` 作为 `/tick/{N}/state` 存储路径 [High]

**文件**: `specs/core/tick-protocol.md` §6.3.1

**问题**: §6.3.1 记录「`/tick/{N}/state → tick 后的完整世界状态`」，暗示 redb 存储完整世界状态。但 persistence-contract.md §2 原则明确「redb 只写小对象：tick head、state checksum、small manifest、object pointers + content hashes」，完整世界状态不在 redb 中（keyframe 在独立文件，delta/modification_set 在 redb 内但不是「完整世界状态」）。

**影响**: 实现 `/tick/{N}/state` 时可能将完整 Bevy World 序列化写入 redb，违反小事务约束。

**修复建议**: §6.3.1 修正「`/tick/{N}/state → tick 后的完整世界状态`」为「`/tick/{N}/state_checksum → tick 后的世界状态 hash`」。完整世界状态通过 keyframe + delta chain 重建，不在 redb 单 key 中存储。

---

### A-H6: distributed-sandbox.md 容器 memory.max 与 wasm-sandbox.md 不一致 [High]

**文件**: `specs/core/distributed-sandbox.md` §6; `specs/core/wasm-sandbox.md` §4.2

**问题**: 
- `distributed-sandbox.md` §6 容器资源限制：`memory.max = 256MB (每 tick 执行一个玩家，非共享)`
- `wasm-sandbox.md` §4.2 cgroup v2：`memory.max = 128MB // 2x Wasmtime 内存，覆盖运行时开销`

distributed-sandbox.md 声称这是「Worker Pool 的超集」且「Sandbox Container 代码完全一致」，但 cgroup 限制差一倍。

**影响**: 本地模式（128MB）和分布式模式（256MB）下同一 sandbox 的资源约束不同，可能导致本地测试通过但分布式部署 OOM 或反之。分布式模式下每容器只执行一个玩家，但 256MB 没有理由说明为什么要比本地大一倍。

**修复建议**: 统一为 128MB。distributed-sandbox.md §6 的 `memory.max = 256MB` 改为 `128MB`（与 wasm-sandbox.md §4.2 一致），并添加注释「分布式模式每容器单玩家，内存限制与本地 worker 一致」。

---

### A-M1: command-source.md §2.2 Tutorial 重复定义 [Medium]

**文件**: `specs/security/command-source.md` §2.1, §2.2

**问题**: §2.1 来源矩阵中已列出 `Tutorial`（tutorial_session + world_id, ⚠️ 仅教程世界, 10/tick, 教程房间, N/A）。§2.2 扩展来源又重复列出 `Tutorial`（tutorial_session + world_id, ⚠️ 仅教程世界, 10/tick, 教程房间, tutorial budget）——字段几乎相同，唯一差异是 §2.2 的 budget 列从 N/A 变为「tutorial budget」。

**影响**: 同一来源在两张表中定义不一致（budget 字段：N/A vs tutorial budget），实现者无法确定哪个为准。

**修复建议**: 从 §2.2 扩展来源表中移除 `Tutorial` 行（已在 §2.1 定义）——或合并 §2.1 和 §2.2 为一张表，消除重复。§2.1 的 budget 列应修正为「tutorial budget」。

---

### A-M2: tick-protocol.md §6.3.1 key interval 描述与 persistence-contract.md §6.2 不一致 [Medium]

**文件**: `specs/core/tick-protocol.md` §6.3.1; `specs/core/persistence-contract.md` §6.2

**问题**: tick-protocol.md §6.3.1 记录「`/tick/{N}/metrics → TickMetrics`」存储在 redb 中。persistence-contract.md §1 存储层职责表中 redb 单条上限 `< 1KB/row`。TickMetrics 包含 collect_timeout_rate, tick_duration_p99, command_rejection_rate 等每 tick 统计，若每 tick 都写入一行可能超 1KB。architecture.md §8 提到 redb metrics table 但未定义行大小约束。

**影响**: TickMetrics 可能违反 redb 小对象约束。

**修复建议**: 在 tick-protocol.md 或 persistence-contract.md 中明确 TickMetrics 的序列化大小上限（如 ≤ 512 bytes），或在 persistence-contract.md §1 表格中为 metrics 行添加特殊说明。

---

### A-M3: distributed-sandbox.md §3 snapshot 分发与 tick-protocol.md §2.3 快照构建语义不精确对齐 [Medium]

**文件**: `specs/core/distributed-sandbox.md` §3; `specs/core/tick-protocol.md` §2.3

**问题**: distributed-sandbox.md §3 Step 2 描述 Engine「遍历活跃玩家，并行分发」——对每个玩家 stitch 可见快照再发 NATS。tick-protocol.md §2.3 的两阶段快照架构明确：步骤 [1] 一次性构建完整世界快照，步骤 [3] per-player stitch，步骤 [4] WASM tick 执行。distributed-sandbox.md 的 Step 2 与 tick-protocol.md 步骤对应关系正确，但 distributed-sandbox.md 未引用 tick-protocol.md §2.3 的两阶段名称，读者需要自行映射。

**影响**: 接口直观性降低——实现者需要跨文档对照才能确认两个文档描述的是同一个流程。

**修复建议**: distributed-sandbox.md §3 Step 2 添加显式引用「详见 tick-protocol.md §2.3 两阶段快照架构」，并将 step 编号对齐。

---

### A-M4: persistence-contract.md §2.1 TickCommitRecord 字段数描述与实际不符 [Medium]

**文件**: `specs/core/persistence-contract.md` §2.1

**问题**: §2.1 标题声称「以下 10 个字段组成 TickCommitRecord」，随后表格列出编号 1-10 的字段。但 engine.md §3.3 TickInputEnvelope 和 tick-protocol.md §3.5.6 描述的 TickCommitRecord 还包含 `collect_id`、`attempt_id`、`commit_id`、`seed_epoch`、`api_version`、`engine_abi_version` 等标识字段。persistence-contract.md §7.1 标识字段节又新增了这些字段。§2.1 的「10 个字段」是指 replay-critical subset，但 §7.1 的扩展字段总数远超 10。

**影响**: 读者可能误以为 TickCommitRecord 只有 10 个字段，忽略标识字段的完整性要求。

**修复建议**: §2.1 澄清「以下 10 个字段为 replay-critical subset……标识字段（collect_id/attempt_id/commit_id 等）见 §7.1」并交叉引用。

---

### A-M5: wasm-sandbox.md §7 Pre-Warm 双重资源预算表 [Medium]

**文件**: `specs/core/wasm-sandbox.md` §7

**问题**: §7 包含两个资源预算表——一个标注为「Pre-warm 编译预算」（编译超时 30s, 编译内存 512MB, 并发编译 worker 5, 预编译缓存 3 版本），紧接着又有一个无标题的资源预算表（编译超时 30s, 编译内存 512MB, 编译进程每次部署独立 fork, 模块缓存...）。两个表内容大量重复但格式不同。

**影响**: 接口直观性降低——同一信息呈现两次，读者不确定以哪个为准。

**修复建议**: 合并为单张表，或在第二个表前添加标题（如「编译时基础预算」），明确两者的区别。

---

### A-L1: engine.md §3.0 升级/降级 CLI 语义混淆 [Low]

**文件**: `design/engine.md` §3.0

**问题**: §3.0 升级与禁用表中，`swarm mod upgrade` 描述为「下一 tick 新版本生效」，而 Mod 安装流程说「引擎编译时通过 Cargo features 引入」。如果 Mod 是静态编译进 Engine 二进制的，`swarm mod upgrade` 如何在「下一 tick」生效而不需要重新编译 Engine？

**影响**: 运维理解困惑——静态编译的 Plugin 和运行时热切换语义冲突。

**修复建议**: 澄清 `swarm mod upgrade` 的实际语义——是否需要重新编译 Engine 并重启，还是有预编译的 Plugin 二进制可以热加载。

---

### A-L2: architecture.md §8 表格「FederationCertificate」未正式定义 [Low]

**文件**: `design/architecture.md` §8

**问题**: §8 组件替代方案表已移除 Rhai/Dragonfly/ClickHouse（保留择期说明），但同节无 FederationCertificate 引用。搜查全文未见该术语在 architecture.md 中定义。command-source.md 使用「Server CA」「CodeSigningCertificate」「ClientAuthCertificate」但不出现 FederationCertificate。已由 R41 清理但需确认。

**影响**: 可能是 R41 清理后遗留的孤儿术语。也可能是尚未引入的新概念。

**修复建议**: 确认是否需要 FederationCertificate 概念；若不需要则全局搜索确保无残留引用。本条主要作为 CrossCheck 提示。

---

## 3. 亮点

### 3.1 两层计算模型抽象
architecture.md §1-§5 的「WASM Execution / COLLECT（不可信、可并行）vs World Simulation / EXECUTE（权威、串行确定性）」分层是整个架构的基石，抽象干净利落。§5 的两层计算模型表精确定义了输入、输出、失败语义和扩展方式，跨 10 份文档的高度一致性表明该抽象已深植整个设计。

### 3.2 Shadow Write + Atomic Publish
tick-protocol.md §3.5 的 Shadow Write 模型设计精巧——staging 行不是已提交状态，GlobalTickCommit 是唯一 publish 点，不是 per-room promotion（无 TOCTOU 窗口），失败时 forward abandon + GC（不是回滚）。§3.5.6 错误恢复表的「新 vs 旧」对比清晰说明了为什么旧模型的 per-room commit 存在时序窗口。这是处理分布式原子性的优秀设计。

### 3.3 Persistence 三层分离
persistence-contract.md §2 的「deterministic_replay / rich_debug_replay / WASM module blob」三层分离声明使得 replay 核心与 debug 辅助解耦。TickCommitRecord 10 字段 + keyframe/delta chain 足够 deterministic replay，Blob/RichTraceBlob 缺失只产生 audit_gap 而非 unreplayable。这一分离使得 blob 异步写入不阻塞 tick 循环且不触发回滚，整个 commit 流程的失败语义非常清晰（§4 失败矩阵 + §7 hash chain + commit retry）。

### 3.4 Command Source Model
command-source.md 的来源矩阵（§2.1-§2.3）将所有指令来源显式建模——WASM / MCP_Deploy / MCP_Query / Admin / Replay / TestHarness / Tutorial / Deploy / Rollback / Simulate / DryRun。每个来源有明确的 auth_context、gameplay/audit/rate_limit/visibility/budget 约束和写入能力约束（§2.3 表）。Source Gate（§4）在验证管线入口处拒绝不合法来源。Admin 路径统一通过 `validate_and_apply()` 且编译期 trait 设计保证无旁路——这是防止权限提升的优秀设计。Replay/审计链路（§5, §7）完整，version_counter 防重放机制（§7.3）明确。

### 3.5 Snapshot 截断合同的确定性严格性
snapshot-contract.md §1 的截断合同设计精确——距离桶 0-6 + entity_id 字典序 + farthest-first removal + critical entity 不可截断 + 128KB reserve + minimum retention set + SnapshotOverBudget 惩罚。§1.5 竞技模式截断降级将截断严重程度暴露给竞技平台判定。§7 pathfinding cache determinism contract 保证 cache 是 pure optimization（hit/miss 不改变输出）。整个合同从理论到边界条件都追求确定性和可验证性。

---

## 4. CrossCheck

以下问题超出本方向（架构）的范围，建议相应方向检查：

- **CX-1**: [shard-protocol.md §4.2 跨分片 Combat 两阶段协议的确定性是否与 Design-Economy 方向的 combat 规则兼容？两阶段（intent broadcast + settlement ack）引入 1 tick 延迟和「target_dead」竞态，这如何影响 Phase 2a/2b 的 damage_application 时序？] → 建议 **Design-Economy** 检查 combat pipeline 跨分片语义。

- **CX-2**: [distributed-sandbox.md §4.1 NATS subject `swarm.tick.{tick}.player.{player_id}` 与 architecture.md §7 的 NATS 用法是否统一？architecture.md §7 提到 NATS queue-group 负载均衡 sandbox dispatch，但 distributed-sandbox.md §6 使用 `shared queue group "sandbox-workers"`——两处 queue group 名称需要一致或说明关系。] → 建议 **Cross-Cutting** 检查 NATS subject 命名规范一致性。

- **CX-3**: [command-source.md §7.0 的 audience 格式 `swarm-aud-v1:{transport}:{server_id}:{world_id}:{player_id}` 中 `server_id` 的定义和来源在哪里？是否与 auth.md / tech-choices.md 中的 Server CA / server identity 模型一致？] → 建议 **Cross-Cutting** 检查 server_id 与 auth 域术语对齐。

- **CX-4**: [snapshot-contract.md §3.2a 运输中拦截（R27 E-H1）的拦截成功率公式包含 `base_success = 60%`——这是浮点百分比还是 basis points？engine.md §3.4.8 明确「禁用 f64」。60% 在定点整数中应表示为 6000 bps，但文档写的是 60%。] → 建议 **Design-Economy** 检查所有经济/战斗公式的数值表示一致性。

- **CX-5**: [persistence-contract.md §8.3 Synthetic Benchmark 要求的 benchmark gate（如 redb room-partition commit p99 < 500ms for 1000 active players, 200 rooms）是否与 engine.md §3.4.1 Tick Pipeline 预算一致？COMMIT p99 ≤ 50ms vs benchmark target p99 < 500ms 差 10 倍——两者定义的指标语义不同（一个是 tick pipeline 内 commit 阶段，一个是端到端 room-partition commit）但文档未明确区分。] → 建议 **Cross-Cutting** 检查 benchmark gate 与 performance budget 的口径对齐。