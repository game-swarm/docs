# R43 Architecture Review — rev-dsv4-architect

## 1. Verdict

`REQUEST_MAJOR_CHANGES`

整体架构设计完备且一致性高：两层计算模型（COLLECT/EXECUTE）边界清晰、31-system ECS 调度权威可靠、Shadow Write + Atomic Publish 持久化模型自洽、单函数 `is_visible_to` 跨所有输出面统一。但存在以下必须修复的问题：engine.md 中的「远期方向」违禁措辞、TickInputEnvelope 跨文档字段不一致、以及 command-validation 中 InsufficientResource 的退款表重复条目歧义。修复后可直接 APPROVE。

---

## 2. 发现的问题

### Issue A1 — `design/engine.md` §3.4.7 L555: 使用「远期方向」违禁措辞
- **Severity**: Critical
- **位置**: `/data/swarm/docs/design/engine.md` 第 555 行
- **内容**: `"水平分片为远期方向，届时再评估存储层是否需要升级。"`
- **问题描述**: Swarm 设计原则明确禁止「远期方向」「future」「deferred」「以后再说」。`architecture.md` §2 已定义静态坐标范围分片模型（`shard_grid`、per-shard Engine + redb），即水平分片是**当前设计的最终状态**，不是远期方向。此句与已确立的架构自相矛盾。
- **影响**: 若按字面理解，会动摇整个分片模型的设计权威性。下游实现者可能误判分片为未定项而推迟实现。
- **修复建议**: 删除该句，或改写为「单个 Engine 实例内不依赖分布式事务——redb WriteTransaction 满足每 tick 原子提交。跨 shard 通信仅在玩家迁移时发生（drone 穿过 shard 边界出口），不在热路径。」与 `architecture.md` §2 保持一致。

### Issue A2 — `design/engine.md` §3.3: `TickInputEnvelope` 残留 `wasm_status` 字段
- **Severity**: High
- **位置**: `/data/swarm/docs/design/engine.md` 第 356 行
- **内容**: `- wasm_status（ok/timeout/trap/fuel_exhausted）`
- **问题描述**: `engine.md` §3.3 定义的 `TickInputEnvelope` 仍包含 `wasm_status` 字段。但 `api-registry.md` §6.1 已将其升级为 `terminal_state` 显式 enum（7 variants: Success/FuelExhausted/TimeoutExceeded/SnapshotOverBudget/CommandBufferFull/InternalError/NotExecuted），其中 `NotExecuted` 覆盖了旧 `wasm_status` 无法表达的 replay/degraded skip 场景。`api-registry.md` §6 列出了 22 个字段，不含 `wasm_status`。
- **影响**: 跨文档定义不一致——实现者以 `engine.md` 为准会遗漏 `terminal_state` 的扩充语义，以 `api-registry.md` 为准则 `wasm_status` 为多余字段。回放封套的字段分歧可能导致 replay 失败。
- **修复建议**: 将 `engine.md` §3.3 中 `wasm_status（ok/timeout/trap/fuel_exhausted）` 替换为 `terminal_state（verified/audit_gap/unreplayable/reconstructable, R16 B3 新增）`，并引用 `api-registry.md` §6.1 的 7 个 `terminal_state` 变体作为权威定义。同步删除 `wasm_status`。

### Issue A3 — `specs/core/command-validation.md` §7.1: InsufficientResource 退款条目重复且语义矛盾
- **Severity**: High
- **位置**: `/data/swarm/docs/specs/core/command-validation.md` 第 466–476 行
- **内容**: 退款表中有三条 `InsufficientResource` 条目：
  - 第 468 行: `退 50% fuel`（理由：竞争导致——非玩家过错）
  - 第 470 行: `退 50% fuel`（理由：同上）
  - 第 474 行: `不退`（理由：玩家应计算资源）
- **问题描述**: 同一个 RejectionReason 在不同场景触发不同退款行为——竞争导致的资源不足（如 Source 被先到先得抢光）应退 50%，自身计算错误导致的资源不足不退。但在表中均列为 `InsufficientResource`，未通过 `debug_detail` 区分场景。读者无法从表本身判断哪条规则对应哪种场景。
- **影响**: 退款逻辑的实现者面临歧义——如何区分「竞争导致」和「计算错误」？这依赖 Phase 2a 应用时的运行时上下文判断，但表中没有给出区分条件。可能导致 refund 行为不一致，破坏 fuel 经济公平性。
- **修复建议**: 
  1. 将第 468 行和 470 行合并为一条：`InsufficientResource (竞争: Source 耗尽/Position 被占) — 退 50% fuel`
  2. 将第 474 行改为独立条目并标注区分条件：`InsufficientResource (自检失败: carry/energy 不足) — 不退`，条件写入 `debug_detail` 模板
  3. 建议增加一列「触发条件示例」使表自解释

### Issue A4 — `specs/core/persistence-contract.md` §2.1 vs `specs/core/tick-protocol.md` §3.5.6: TickCommitRecord 字段分层命名偏差
- **Severity**: Medium
- **位置**: 
  - `/data/swarm/docs/specs/core/persistence-contract.md` §2.1（10 字段）
  - `/data/swarm/docs/specs/core/tick-protocol.md` §3.5.6（三层分离声明）
- **问题描述**: `tick-protocol.md` §3.5.6 将 replay 数据分为三层：`TickCommitRecord` replay-critical core（10 字段）、Replay identity（collect_id/attempt_id/commit_id/seed_epoch 等）、`TickInputEnvelope`（module_hash/wasmtime_version/terminal_state 等）。但 `persistence-contract.md` §2.1 未提及 Replay identity 层的存在，直接列出 10 字段作为 `TickCommitRecord`。在 `persistence-contract.md` §7.1 中，collect_id/attempt_id/commit_id 被挂到 `TickCommitRecord` 结构体内部——这与 `tick-protocol.md` 将它们列为独立 Replay identity 层的说法不一致。
- **影响**: 实现者需要明确：collect_id/attempt_id/commit_id 是否属于 TickCommitRecord 的同一 redb WriteTransaction？若属于，则 `persistence-contract.md` 的 10 字段列表应扩展或增加说明。若不属于（单独存储），则 tick-protocol.md 的 Replay identity 层定义需澄清存储位置。当前两头说法并存，存在实现分叉风险。
- **修复建议**: 在 `persistence-contract.md` §2.1 末尾增加一条说明：「`collect_id`、`attempt_id`、`commit_id`（见 §7.1）属于 Replay identity 层，与上述 10 字段在同一 redb WriteTransaction 中提交但不计入 replay-critical subset core——缺失不影响 deterministic replay，仅影响审计完整性。」与 `tick-protocol.md` §3.5.6 对齐。

### Issue A5 — `design/engine.md` §3.2 L307 vs `design/engine.md` §3.4.2 L397: `host_get_path_find` 命名不一致
- **Severity**: Low
- **位置**: 
  - `/data/swarm/docs/design/engine.md` 第 397 行: `Pathfinding requests max 10 per player per tick`
  - `/data/swarm/docs/specs/core/wasm-sandbox.md` §3.2: `host_path_find`
  - `/data/swarm/docs/specs/reference/api-registry.md` §4.1: `host_path_find`
- **问题描述**: `engine.md` 容量表使用 `Pathfinding requests` 命名，但所有 spec 文档统一使用 `host_path_find`。引擎 API 表中也有 `host_get_path`（`api-registry.md` §3.2 Play 工具 `swarm_get_path`）。同一概念三个名字：`Pathfinding` / `host_path_find` / `swarm_get_path`。`host_get_path` 是 MCP 查询工具，`host_path_find` 是 WASM host function——两者不同但读者容易混淆。
- **影响**: 新增开发者可能在 engine.md 容量表与 wasm-sandbox.md 之间建立错误映射。
- **修复建议**: 在 `engine.md` §3.4.2 容量表中将 `Pathfinding requests` 改为 `host_path_find calls`，并加脚注「此为 WASM host function 调用上限，非 MCP `swarm_get_path` 查询」。

### Issue A6 — `specs/security/visibility.md` §10.2 `omitted_count` 分桶 vs `design/engine.md` §3.4.4 `omitted_counts` 复数形式
- **Severity**: Low
- **位置**:
  - `/data/swarm/docs/specs/security/visibility.md` 第 379–390 行: `omitted_count`（单数，分桶值）
  - `/data/swarm/docs/design/engine.md` 第 518 行: `omitted_counts`（复数）
- **问题描述**: `visibility.md` 已将 `omitted_count` 改为分桶字符串值（`"few"`/`"some"`/`"many"`/`"extreme"`），但 `engine.md` 仍写为 `omitted_counts`（复数）且未注明分桶语义。字段名不一致：单数 vs 复数。
- **影响**: WASM/SDK codegen 可能产生字段命名冲突。
- **修复建议**: 统一为 `omitted_count`（单数），在 `engine.md` 中旁注「已分桶」并引用 `visibility.md` §10.2。

---

## 3. 亮点

1. **Shadow Write + Atomic Publish 持久化模型**（`tick-protocol.md` §3.5）是本次评审中架构最精致的部分。Per-room staging 写入 content-addressed 行、GlobalTickCommit 为唯一 publish 点、未被 manifest 引用的 staging 数据对外不可见——这三层保证彻底消除了「per-room 写入已持久化、全局 abort」的时序窗口。GC 策略（staging 行最大存活 < 15s）完备且无累积风险。

2. **两层计算模型的严格分离**（`architecture.md` §5）精确区分了 WASM Execution（不可信、并行、水平可扩展）与 World Simulation（可信、串行确定、硬瓶颈），并将所有扩展性投资集中在第一层——这是正确的架构判断。

3. **31-system ECS 清单**（`phase2b-system-manifest.md` §1–§4）提供的 R/W 矩阵和 Unique Writer Contract 在游戏引擎领域罕见——每类 StatusState 有且仅有一个 writer（S22），并行 buffer 生产 + 串行唯一 committer 的模式保证了正确性且可被 CI 机械验证。

4. **`is_visible_to` 单函数跨所有输出面**（`visibility.md` §1–§3）消除了信息泄露的典型多路径不一致问题。`omitted_count` 分桶（§10.2）和特殊攻击拒绝码等价类（§10.4）的 oracle 防线闭合精细——attacker 无法通过错误码区分「不存在」与「不可见」。

5. **Blake3 统一原语**（`tech-choices.md` §8）覆盖哈希、PRNG 和 XOF——减少依赖审计面，seed+offset 模式天然适配 per-entity per-tick 确定性随机流。

6. **Fixed-Point Type Registry**（`api-registry.md` §0）彻底消除 `f64` 跨平台非确定性——所有比率用 BasisPoints（×10000）、所有距离用 milli_distance（×1000）、所有资源用整数单位。这是确定性的基石。

---

## 4. CrossCheck

以下项目为架构方向关注的跨域一致性问题，由本方向评审发现，建议其他方向针对性检查：

- **CX1: TickInputEnvelope 22 字段的跨文档对齐** → 建议 **spec-writer / API 方向** 检查 `engine.md` §3.3、`tick-protocol.md` §3.5.6、`api-registry.md` §6 三处定义是否逐字段对齐。`wasm_status` → `terminal_state` 的迁移需在所有文档中同步。

- **CX2: command-validation InsufficientResource 退款的运行时区分条件** → 建议 **gameplay 方向** 检查 Phase 2a inline apply 中如何区分「竞争导致的资源不足」与「计算错误导致的资源不足」——是否需要增加新的 `debug_detail` 枚举值或子分类来触发不同 refund 行为。

- **CX3: Shadow Write 模型下 spawn body_cost refund 的时序安全性** → 建议 **安全方向** 检查：Phase 2a 扣除的 body_cost 在 Phase 2b spawn_system 创建失败后全额退还——当该 drone 的 spawn 涉及跨房间 global storage 提取时，Shadow Write 模型（跨房间在 Bevy World 内预先裁决）是否会引入 body_cost 扣费→跨房间失败→退款路径中的资源倍增漏洞。

- **CX4: `persistence-contract.md` §2.3 Deploy 状态机中 `ACTIVATION_PENDING` → `ACTIVE` 的判定条件** → 建议 **引擎方向** 检查：当 `compiled_artifact_hash` 匹配但 `upload_status == "failed"` 时，drone 是否仍可激活新模块？`persistence-contract.md` 的第 126 行确认「Blob 缺失不影响 redb 状态完整性或模块激活」，但需验证 COBLLEECT 阶段使用预编译 artifact 时是否确实不依赖 blob store 中的原始 WASM bytes。

- **CX5: Gateway 同时支持 REST 路径和 Browser WS 路径的 audience 隔离** → 建议 **安全方向** 检查 `gateway-protocol.md` §9 的 Transport Auth Matrix：Browser WS token **不得**出现在 URL query string 中（防止 nginx access log 记录），Gateway 实现是否在两个 transport 入口上严格执行了此约束。

- **CX6: `TickCommitRecord` 10 字段中不包含 per-room staging hash** → 建议 **引擎方向** 确认：deterministic replay 仅依赖 `state_checksum`（field 8，覆盖全局 canonical serialize）足够验证每个房间的状态完整性，还是需要房间级 hash 进入 replay-critical subset。
