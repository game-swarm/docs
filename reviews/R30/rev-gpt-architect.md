# R30 Clean-Slate 独立评审 — Architect

## 1. Verdict

REQUEST_MAJOR_CHANGES

理由：整体架构方向（WASM deferred command + ECS deterministic tick + FDB replay-critical commit + async object store）是清晰且与项目目标一致的；但当前文档集中存在多处“权威源互相竞争”的合同裂缝，尤其是 tick commit / replay-critical 存储、capacity 与 transaction 分区、CommandAction 层级、特殊攻击执行模型、MCP/Admin mutation 与 tick 排序边界。这些不是措辞小问题，而会直接导致不同实现者写出不同的系统边界和数据流，必须在设计层闭合后才能进入实现。

## 2. 发现的问题

### A-H1 — TickTrace / Replay-critical 分层存在互斥合同

- Severity: High
- 文件引用：
  - `/tmp/swarm-review-R30/specs/core/05-persistence-contract.md:15`
  - `/tmp/swarm-review-R30/specs/core/05-persistence-contract.md:34`
  - `/tmp/swarm-review-R30/specs/core/05-persistence-contract.md:51`
  - `/tmp/swarm-review-R30/specs/core/05-persistence-contract.md:121`
  - `/tmp/swarm-review-R30/specs/core/05-persistence-contract.md:180`
  - `/tmp/swarm-review-R30/specs/core/01-tick-protocol.md:603`
  - `/tmp/swarm-review-R30/specs/core/01-tick-protocol.md:615`
  - `/tmp/swarm-review-R30/specs/core/01-tick-protocol.md:620`
- 问题描述：`05-persistence-contract.md` 正确提出 replay-critical 与 rich/debug 分层：FDB 原子提交 replay-critical subset，对象存储承载 rich trace/debug blob，可降级、可延迟、可丢失。但 `01-tick-protocol.md` 又声明 “TickTrace 写入 FDB 与 tick 执行在同一事务中”，并进一步声称 “不存在 tick 成功但回放数据丢失”。这与 `05` 的 async object store upload、`upload_status=failed`、`terminal_state=audit_gap` 语义互相冲突。
- 影响分析：实现者无法判断 “TickTrace” 到底指 FDB replay-critical subset、rich trace blob，还是二者集合。更严重的是，故障语义相反：一处允许 tick committed 但 rich audit gap，另一处要求 TickTrace 缺失则 tick 放弃。该冲突会影响 FDB transaction 结构、replay verifier 输入、告警等级、WAL 设计和容量预算。
- 修复建议：统一术语与提交边界：
  1. 所有文档中禁止裸用 `TickTrace` 表示不同层级，改为 `TickCommitRecord`、`RichTraceBlob`、`ReplayArtifact` 三个名称。
  2. `01-tick-protocol.md` §6.3.4 应改为：FDB transaction 只原子提交 replay-critical `TickCommitRecord`；rich/debug blob 异步上传，失败产生 `audit_gap` 但不回滚 tick。
  3. 若某些 replay-critical command/rejection/fuel 字段当前被称作 TickTrace，应移动到 FDB `TickCommitRecord` 清单并与 `05` §2.1 对齐。
  4. 在 README glossary 已有三层术语的前提下，应让 `01`、`05` 全部引用 glossary，而不是保留历史语义。

### A-H2 — Capacity / transaction model 同时声明 “单事务权威” 与 “500+ 必须 room-partition”

- Severity: High
- 文件引用：
  - `/tmp/swarm-review-R30/design/README.md:168`
  - `/tmp/swarm-review-R30/design/engine.md:170`
  - `/tmp/swarm-review-R30/design/engine.md:174`
  - `/tmp/swarm-review-R30/design/engine.md:304`
  - `/tmp/swarm-review-R30/design/engine.md:404`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:535`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:536`
  - `/tmp/swarm-review-R30/specs/core/05-persistence-contract.md:340`
  - `/tmp/swarm-review-R30/specs/core/05-persistence-contract.md:352`
  - `/tmp/swarm-review-R30/specs/core/05-persistence-contract.md:357`
  - `/tmp/swarm-review-R30/specs/core/05-persistence-contract.md:370`
- 问题描述：顶层与 engine 文档仍把 “单 Engine + FDB 单一提交保证世界一致性” 写成 500 活跃玩家目标架构的一部分；但 persistence contract 明确说 500/1000-player 场景必须使用 room-level partition，并引入 cross-room 2PC。API Registry 又把 500/1000 写成全局容量限制。这里的冲突不只是 scaling 细节，而是 authoritative commit boundary 从 “world-wide atomic tick” 变成 “per-room transaction + cross-room protocol”。
- 影响分析：Swarm 的核心确定性与 replay 模型依赖清晰的 tick commit boundary。若 500-player 目标使用 single world transaction，replay 与 failure semantics 是全局原子；若使用 room-partition，跨房间移动、攻击、transfer、visibility、resource ledger、hash chain 都需要 room-local commit + global tick head 的组合协议。当前文档同时承诺二者，会让执行引擎、FDB schema、replay verifier 和 sharding 预留接口全部分叉。
- 修复建议：把目标架构直接写成 room-partition，而不是 “单事务 MVP / 未来扩展” 双轨：
  1. `design/engine.md` 和 `design/README.md` 中的容量描述应改为：World target 500/hard 1000 的权威持久化模型是 room-partition tick commit；single transaction 只可作为 dev/test profile，不承载目标容量声明。
  2. 增加 `GlobalTickCommit` 结构：包含 tick、per-room commit hashes、cross-room operation set、global resource ledger hash、manifest hash。
  3. 定义 cross-room operation 的唯一模式：推荐 deterministic two-phase room commit，并明确超时不得 `best-effort` 改变 gameplay state；若失败，整组相关 room rollback 或 tick abandon。
  4. API Registry 的容量表应引用 room-partition commit contract，而非仅写 benchmark-gated 数字。

### A-H3 — CommandAction 权威集合与 Phase 2a/2b 执行模型不一致

- Severity: High
- 文件引用：
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:37`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:44`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:46`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:62`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:69`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:81`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:84`
  - `/tmp/swarm-review-R30/design/engine.md:225`
  - `/tmp/swarm-review-R30/specs/core/06-phase2b-system-manifest.md:83`
  - `/tmp/swarm-review-R30/specs/core/06-phase2b-system-manifest.md:126`
  - `/tmp/swarm-review-R30/specs/core/02-command-validation.md:429`
  - `/tmp/swarm-review-R30/specs/core/02-command-validation.md:616`
- 问题描述：API Registry 声明 21 个 CommandAction，其中包含 `TransferToGlobal`、`TransferFromGlobal`、`Leech`、`Fabricate`；但 engine 的 Phase 2a 分类、manifest 的 S01-S06 handlers、command validation 的字段级穷举表没有完整覆盖这些 action。`Leech` / `Fabricate` 又被标成 Tier 2，但本轮评审原则要求设计文档呈现目标状态，不应留下 phase/tier 占位。特殊攻击描述处说 8 个特殊攻击，但 manifest 的 special_attack_reducer 只列 6 个优先级。
- 影响分析：CommandAction 是 SDK、WASM ABI、validation、TickTrace replay 和 ECS handler 的核心接口。权威集合不闭合会导致 SDK 能生成玩家可调用 action，但 engine 没有唯一执行路径；或者 replay 记录了 custom action，但 Phase 2b manifest 不知道如何调度。该问题直接破坏 API 直觉性与抽象分层。
- 修复建议：
  1. 在 `06-phase2b-system-manifest.md` 中增加 `TransferToGlobal` / `TransferFromGlobal` 的明确 handler 或声明它们经 S05 transfer/resource_ledger 处理，并补 R/W 矩阵。
  2. 对 8 个特殊攻击给出完整 reducer priority、unique writer、status/damage/resource effects；若 `Leech`、`Fabricate` 是目标设计，则不能用 `Tier 2` 弱化，应定义完整调度和校验。
  3. `02-command-validation.md` 的字段级穷举表必须与 API Registry 的 21 action 一一对应。
  4. 移除 “Tier 2” 这种阶段标签，替换为 “registered custom action, enabled by world_action_manifest” 的目标状态表述。

### A-H4 — MCP/Admin mutation 与 tick command ordering 的边界不直观且自相矛盾

- Severity: High
- 文件引用：
  - `/tmp/swarm-review-R30/design/README.md:74`
  - `/tmp/swarm-review-R30/design/README.md:124`
  - `/tmp/swarm-review-R30/specs/core/01-tick-protocol.md:114`
  - `/tmp/swarm-review-R30/specs/core/01-tick-protocol.md:180`
  - `/tmp/swarm-review-R30/specs/core/01-tick-protocol.md:770`
  - `/tmp/swarm-review-R30/specs/core/01-tick-protocol.md:774`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:277`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:304`
  - `/tmp/swarm-review-R30/specs/core/02-command-validation.md:35`
  - `/tmp/swarm-review-R30/specs/core/02-command-validation.md:514`
- 问题描述：tick-protocol 一方面说唯一玩家执行器是 WASM，MCP query 在 COLLECT 阶段读取同一快照；另一方面 determinism contract 把 Admin、WASM、MCP_Deploy、MCP_Query 放入同一个 `sort_key`，并声明 `source_rank`。command-validation 又说所有入口（WASM/MCP/REST/admin CLI）走同一校验→应用路径，但查询不进指令管线。API Registry 中 Admin rollback/config/ban 是 `admin_critical` mutation，deploy 是 `deploy_mutation`，query 是 read-safe；这些类别没有映射到一个清晰的 “tick input envelope / side-effect lane” 架构。
- 影响分析：接口对用户和实现者都不直观：MCP_Query 是否参与 command ordering？Admin rollback 是否是 tick 内 command、tick 间 control-plane mutation，还是外部 maintenance operation？如果 query 被放入 sort_key，但又“不进指令管线”，replay verifier 是否需要记录它？如果 admin mutation 与 WASM command 同 lane，则权限、rollback、hash chain、fuel/refund 语义会互相污染。
- 修复建议：明确三条 lane，并在所有文档采用同一模型：
  1. `GameplayCommandLane`：WASM CommandIntent → RawCommand → ValidatedCommand → Phase 2a，进入 sort_key 与 replay-critical command log。
  2. `ControlMutationLane`：deploy/admin config/rollback/ban，使用 FDB version counter 与 explicit replay class，在 tick boundary 生效，不与 per-player WASM commands 混排。
  3. `ReadQueryLane`：MCP/REST/WebSocket read，只读 snapshot/cache，不进入 command sort_key，只记录 rate-limit/audit。
  4. 修改 `01` §9.1：sort_key 只描述会改变 gameplay state 的 command；MCP_Query 不应作为排序类别出现。
  5. 修改 `02` §1：将 “所有入口走同一校验→应用路径” 缩窄为 “所有 mutating gameplay actions 走同一 validate_and_apply 路径”。

### A-M1 — Phase 2b manifest 的并行安全说明内部不闭合

- Severity: Medium
- 文件引用：
  - `/tmp/swarm-review-R30/specs/core/06-phase2b-system-manifest.md:172`
  - `/tmp/swarm-review-R30/specs/core/06-phase2b-system-manifest.md:179`
  - `/tmp/swarm-review-R30/specs/core/06-phase2b-system-manifest.md:181`
  - `/tmp/swarm-review-R30/specs/core/06-phase2b-system-manifest.md:203`
  - `/tmp/swarm-review-R30/specs/core/06-phase2b-system-manifest.md:214`
  - `/tmp/swarm-review-R30/specs/core/06-phase2b-system-manifest.md:216`
  - `/tmp/swarm-review-R30/specs/core/06-phase2b-system-manifest.md:356`
  - `/tmp/swarm-review-R30/specs/core/06-phase2b-system-manifest.md:357`
- 问题描述：Combat Set A 表示 S11-S13 直接写 `HitPoints`，但同时说按 target_id partition、reduce 后由 S15 统一应用。Status Set B 表示 S16-S22 都写 `StatusState`，又说 unique writer 是 S22，S16-S21 与 S22 写不同 component/subtype。R/W matrix 将 S14 写 `StatusState`，但 S14 note 又说不直接修改实体状态，仅写 pending intents。
- 影响分析：manifest 是调度唯一权威，R/W matrix 若与文字不一致，CI 静态分析和 Bevy schedule 都无法以它为准。实现者可能让 S11-S13 直接写 HP，也可能让它们写 PendingDamage；可能让 S14 写 StatusState，也可能只写 PendingIntents。两者 replay 结果和并行安全完全不同。
- 修复建议：把 “intent/buffer” 与 “component state” 分开建模：
  1. S11-S13 writes 改为 `PendingDamage` / `PendingSpecialAttackIntent`，不直接写 `HitPoints`。
  2. S15 是唯一 `HitPoints` damage writer，S13 heal 若需要即时治疗也应通过 `PendingHeal` 或明确作为独立 writer partition。
  3. S14 writes 只应是 `PendingIntents`，不得写 `StatusState`。
  4. S16-S21 若只是 effect-specific reducers，应改名或移除 “parallel status writers”；若 S22 是唯一 writer，则 S16-S21 不应写 StatusState。

### A-M2 — 快照构建模型在设计层仍保留两种复杂度叙述

- Severity: Medium
- 文件引用：
  - `/tmp/swarm-review-R30/design/engine.md:188`
  - `/tmp/swarm-review-R30/design/engine.md:258`
  - `/tmp/swarm-review-R30/specs/core/01-tick-protocol.md:136`
  - `/tmp/swarm-review-R30/specs/core/01-tick-protocol.md:157`
  - `/tmp/swarm-review-R30/specs/core/01-tick-protocol.md:171`
- 问题描述：engine 明确两阶段快照架构：tick 开始一次性构建完整世界快照，按房间分片，每玩家拼接可见分片；tick-protocol 的代码函数仍写成 `build_snapshot(player_id, tick)` 并从 `visibility_filter(all_entities, player_id, tick)` 开始，容易被理解为 per-player build。虽然后文补充 “按房间序列化一次”，但接口形态与目标架构不一致。
- 影响分析：这是架构接口直觉性问题。SnapshotBuilder 如果暴露 per-player API，实现很容易退回 O(P×E) 或把 caching 作为内部优化，而不是强制的核心数据流。也会影响 MCP `swarm_get_snapshot` 与 WASM `tick(snapshot)` 共用同一 snapshot 的合同。
- 修复建议：把接口改成两层类型：
  1. `WorldSnapshotFrame { tick, room_shards, world_config_hash, visibility_index }` 在 COLLECT 开始构建一次。
  2. `PlayerSnapshotView = stitch_visible_rooms(frame, player_id)` 只做 visibility/filter/truncation。
  3. 所有 host query / MCP snapshot 读取 `WorldSnapshotFrame`，禁止直接从 Bevy World 或 FDB 重建 per-player snapshot。

### A-M3 — `object_id` 全 action 共享字段与 Spawn/GlobalStorage 参数语义不自然

- Severity: Medium
- 文件引用：
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:41`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:58`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:66`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:67`
  - `/tmp/swarm-review-R30/specs/core/02-command-validation.md:257`
  - `/tmp/swarm-review-R30/specs/core/02-command-validation.md:576`
- 问题描述：Registry 声明所有 21 个 CommandAction 都包含 `object_id` 作为执行动作的 entity，但 Spawn 表格又有 `spawn_id`，Global Storage 指令只有 resource/amount，看不出 `object_id` 是 drone、spawn、controller、还是 account/global store actor。command-validation 的 Spawn 示例没有 `object_id`，而字段级表又把 Spawn 的所有权写成 `spawn_id.owner`。
- 影响分析：统一 `object_id` 的抽象初衷是好事，但当前命名让 API 不直观。SDK 用户会困惑 Spawn 到底传 `object_id` 还是 `spawn_id`；Global Storage 由哪个实体执行、是否消耗 action slot、是否需要 range，都不清楚。
- 修复建议：重命名并分层：
  1. 顶层统一字段改为 `actor_id`，语义为消耗 action/quota 的执行主体。
  2. Spawn 使用 `actor_id = spawn entity id`，去掉重复 `spawn_id` 或将 `spawn_id` 标为 alias，不能两者并存。
  3. Global Storage 明确 `actor_id` 是 drone/storage/terminal 之一，或声明为 account-level economy operation 不属于 CommandAction，而进入 EconomyOperation lane。

### A-L1 — 顶层架构图混淆 MCP 入口归属

- Severity: Low
- 文件引用：
  - `/tmp/swarm-review-R30/design/README.md:73`
  - `/tmp/swarm-review-R30/design/README.md:74`
  - `/tmp/swarm-review-R30/design/README.md:124`
  - `/tmp/swarm-review-R30/design/README.md:125`
  - `/tmp/swarm-review-R30/specs/core/01-tick-protocol.md:114`
- 问题描述：README 架构图把 MCP Interface 放在客户端盒子内，又在 Tick 引擎盒子里画 MCP Server。tick-protocol 则强调没有 McpPlayerExecutor，AI 和人类都必须部署 WASM。两个 MCP 位置没有明确区分 “client-facing control/query endpoint” 与 “engine-side server implementation”。
- 影响分析：从架构直觉看，读者可能误解 AI agent 可通过 MCP 直接控制 tick，而不是通过 MCP 部署 WASM 与查询 snapshot。这会干扰 Command Source 与安全模型理解。
- 修复建议：图中拆成：`MCP Client/Agent`（外部客户端）→ Gateway/API → `MCP Service`（control/query/deploy endpoint）→ Engine；并标注 “MCP never executes player logic; player logic executes only as WASM”。

### A-L2 — 文档中残留阶段/未来/MVP 表述，违背目标状态呈现原则

- Severity: Low
- 文件引用：
  - `/tmp/swarm-review-R30/design/engine.md:170`
  - `/tmp/swarm-review-R30/design/engine.md:172`
  - `/tmp/swarm-review-R30/design/engine.md:242`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:81`
  - `/tmp/swarm-review-R30/specs/reference/api-registry.md:84`
  - `/tmp/swarm-review-R30/specs/core/05-persistence-contract.md:342`
  - `/tmp/swarm-review-R30/specs/core/05-persistence-contract.md:347`
- 问题描述：文档仍出现 “目标 MVP”“远期方向”“playtest 阶段可能被挑战”“Tier 2”“单事务 MVP”等阶段化措辞。本轮评审要求设计即目标状态，不区分 Phase/MVP/迭代。
- 影响分析：这些词会让实现者把部分核心合同当成临时方案或 future extension，尤其在容量、special attack 和 move-as-action 这种核心设计上造成执行歧义。
- 修复建议：删除阶段化措辞，改为目标状态合同。确需配置差异时，用 `world_profile` / `mode capability` / `enabled_by_world_action_manifest` 表达，而不是 MVP/Tier/Future。

## 3. 亮点

1. WASM deferred command model 方向正确。`04-wasm-sandbox.md:167` 明确 WASM 不直接调用 mutating host function，所有状态变更经 JSON command 返回并由引擎统一应用；这与确定性 replay、审计和安全边界高度一致。

2. Source Gate / CommandIntent / RawCommand / ValidatedCommand 三层抽象清晰。`02-command-validation.md:61` 到 `02-command-validation.md:76` 把不可信输入、服务端注入身份、预校验缓存分层拆开，是非常好的接口边界。

3. Tick 内快照一致性目标明确。`01-tick-protocol.md:171` 到 `01-tick-protocol.md:190` 定义 WASM tick 与 MCP snapshot query 看到同一 COLLECT 快照，避免观察 EXECUTE 中间态，这是跨模块数据流中最关键的正确方向。

4. Manifest-driven ECS 调度是正确抽象。`06-phase2b-system-manifest.md:7` 到 `06-phase2b-system-manifest.md:13` 通过 stable system id、manifest hash、显式 R/W 声明把调度纳入 replay contract，方向非常好；只需修复内部 R/W 与文字不一致。

5. Persistence 分层思路优秀。`05-persistence-contract.md:9` 到 `05-persistence-contract.md:15` 将 FDB small authoritative records、object store large blobs、hash chain、replay-critical/debug separation 拆开，是支撑 MMO 级 tick 流量的正确架构。

6. Sandbox 生命周期与安全边界写得具体。`04-wasm-sandbox.md:41` 到 `04-wasm-sandbox.md:45` 解释 long-lived worker pool + per-tick Store reset 的边界，`04-wasm-sandbox.md:361` 到 `04-wasm-sandbox.md:418` 给出 OS 加固 checklist，可直接指导实现与 CI。

7. API Registry 的单事实源意识很强。`api-registry.md:3` 到 `api-registry.md:16` 明确 IDL → Registry/SDK 生成链和 CI 闭合原则，这是避免 SDK/engine/interface 分叉的正确机制。

## 4. CrossCheck — 需要跨方向检查

- CX-1: Room-partition + cross-room 2PC 是否能保持 deterministic replay 与 global hash chain 连续性 → 建议 Persistence/Determinism 方向检查 per-room commit hash、global tick head、cross-room rollback 的一致性。
- CX-2: MCP/Admin mutation lane 拆分后，认证 scope、证书用途、admin audit 是否仍完整 → 建议 Security/Auth 方向检查 `admin_critical`、`deploy_mutation`、`read_replay_safe` 的权限边界和审计字段。
- CX-3: 8 个特殊攻击完整启用后，状态机优先级、反制窗口、抗性计算是否与 gameplay 文档一致 → 建议 Gameplay 方向检查 Hack/Drain/Overload/Debilitate/Disrupt/Fortify/Leech/Fabricate 的同 tick reducer 和 mode capability。
- CX-4: Snapshot truncation 的 authoritative source 当前被引用到未在本任务允许列表中的 snapshot contract → 建议 Snapshot/API 方向检查 `09-snapshot-contract.md` 与 engine/tick-protocol/API Registry 的截断字段、critical entity、host_get_objects_in_range 返回格式是否一致。
- CX-5: Global Storage action 到底属于 CommandAction 还是 EconomyOperation lane → 建议 Economy/Resource Ledger 方向检查 `TransferToGlobal`、`TransferFromGlobal`、storage tax、global cap、resource ledger checksum 的执行边界。
- CX-6: Worker pool 与 cgroup cpu.max 的容量声明是否匹配 500/1000 player budget → 建议 Performance/Sandbox 方向检查 per-worker 0.25 CPU 秒、256/1000 worker cap、32 cores target 的预算闭合。
