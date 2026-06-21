# R32 Architect 独立评审报告

## 1. Verdict

REQUEST_MAJOR_CHANGES

当前设计在大方向上已经具备清晰的分层目标：WASM deferred command model、Bevy ECS deterministic schedule、FDB/Object Store 分层、API Registry 单事实源都符合项目愿景。但本轮仍存在若干架构级阻塞：多处“唯一权威源”互相冲突，room-partition 的全局原子性与 FDB durable per-room commit 数据流不闭合，Persistence Contract 对 replay-critical 数据归属前后矛盾，Phase 2b manifest 的系统数量与 R/W contract 不一致。这些问题不是实现细节，而是会直接导致不同实现者作出不同系统边界与恢复语义解释，因此需要重大修改后再进入下一轮。

## 2. 发现的问题

### A-H1 — Room-partition 将已提交 per-room FDB 事务称为“无部分提交”，但缺少可成立的全局原子协议

- Severity: Critical
- 文件引用：`/tmp/swarm-review-R32/specs/core/01-tick-protocol.md:397`
- 文件引用：`/tmp/swarm-review-R32/specs/core/01-tick-protocol.md:417`
- 文件引用：`/tmp/swarm-review-R32/specs/core/01-tick-protocol.md:423`
- 文件引用：`/tmp/swarm-review-R32/specs/core/05-persistence-contract.md:358`
- 文件引用：`/tmp/swarm-review-R32/specs/core/05-persistence-contract.md:361`

问题描述：
`01-tick-protocol.md` 声称生产环境使用 room-partition tick commit，先对每个活跃房间执行独立 FDB 事务写入 room state delta，再提交 `GlobalTickCommit`，且 `GlobalTickCommit` 失败时“所有房间快照恢复”、不存在部分房间提交语义。`05-persistence-contract.md` 又将 Room-Partition 描述为每个 room 独立 FDB 事务分区，并提到 cross-room operations 使用 2-phase commit。这里的 durable write 顺序与全局原子语义冲突：一旦某些 room transaction 已经 commit 到 FDB，后续 GlobalTickCommit 失败时，仅靠 Bevy 内存快照恢复不能撤销已经 durable 的 per-room FDB 状态。文档没有定义 pending/staged keyspace、commit marker visibility rule、read fence、compensating rollback transaction、versionstamp CAS、或真正跨 key transaction 的原子边界。

影响分析：
这是 tick commit 架构的根基问题。实现者可能按字面先提交 per-room delta，导致 FDB 中出现未被 GlobalTickCommit 承认的房间状态；也可能将 per-room delta 写到 staging 区再由 global marker 发布，但文档没有这样定义。查询、replay、crash recovery、cross-room movement/resource transfer 都会因此产生分叉解释。最坏情况下，服务器 crash 于 per-room commit 成功、GlobalTickCommit 失败之间，会留下世界状态与 tick head/hash chain 不一致的 durable partial state。

修复建议：
将 room-partition 明确定义为 staged two-layer commit，而不是“已提交后再全局回滚”。建议采用：
1. per-room 事务只写 `/staged/{tick}/{room_id}/...`，不更新 visible world head；
2. `GlobalTickCommit` 是唯一发布点，写入 `committed_tick=N`、`per_room_hashes`、`global_ledger_hash`、`manifest_hash`；
3. 所有读路径只读取 `committed_tick` 指向的数据，忽略无 marker 的 staged rows；
4. GlobalTickCommit 失败时 staged rows 由 GC 清理，不需要回滚已发布状态；
5. cross-room intents 在内存 EXECUTE 阶段裁决，commit 阶段只发布已裁决结果，不在 per-room commit 之后再执行会改变语义的 cross-room 操作。
如果坚持使用 FDB 原生事务全局原子，则应删除“per-room 独立 FDB 事务先提交”的流程，改为单事务或可证明的 FDB transaction composition，而不是同时保留两种语义。

### A-H2 — Persistence Contract 对 replay-critical 数据归属自相矛盾，破坏 FDB/Object Store 分层

- Severity: High
- 文件引用：`/tmp/swarm-review-R32/specs/core/05-persistence-contract.md:30`
- 文件引用：`/tmp/swarm-review-R32/specs/core/05-persistence-contract.md:36`
- 文件引用：`/tmp/swarm-review-R32/specs/core/05-persistence-contract.md:55`
- 文件引用：`/tmp/swarm-review-R32/specs/core/05-persistence-contract.md:156`
- 文件引用：`/tmp/swarm-review-R32/specs/core/05-persistence-contract.md:170`
- 文件引用：`/tmp/swarm-review-R32/specs/core/05-persistence-contract.md:178`
- 文件引用：`/tmp/swarm-review-R32/specs/core/05-persistence-contract.md:211`

问题描述：
同一文档前半部分定义了清晰分层：TickCommitRecord 的 10 个 replay-critical 字段在 FDB 同事务原子提交，Object Store 只承载 RichTraceBlob，blob 缺失不影响 deterministic replay，只导致 `audit_gap`。但后续 Tick Commit 序列又说 FDB commit 成功 + blob 写入失败时“world state 完整，但该 tick replay 不可用”；upload_status 表把 `pending`/`failed` 标为“replay 不可用”；Replay 正常流程要求从对象存储拉取 `tick_trace_blob` 并反序列化 TickCommitRecord。也就是说，同一合同既说 TickCommitRecord 在 FDB、blob 非关键，又说 replay 依赖对象存储 blob。

影响分析：
这会导致 persistence API、replay verifier、GC、retention policy 全部无法按唯一模型实现。如果 replay-critical commands/rejections/fuel/state_checksum 真在 FDB，Object Store failure 不应使 replay 不可用；如果 TickCommitRecord 实际在 blob 中，前面的 FDB replay-critical subset 声明就是错误的，并且异步 blob 写入会破坏审计完整性。该冲突直接影响反作弊、回放、灾备和 debug trace 的抽象边界。

修复建议：
选择并贯彻一个模型。按当前设计目标，更合理的是：
1. FDB 保存完整 replay-critical TickCommitRecord 或可重建它的 canonical rows：commands、rejections、fuel、deploy activation、snapshot_hash、commands_hash、state_checksum、manifest_hash、world_config_hash、codec version；
2. Object Store 仅保存 RichTraceBlob、可视化 replay artifact、snapshot delta blob 等非关键数据；
3. `upload_status=failed` 的语义改为 “rich audit unavailable / terminal_state=audit_gap”，不得写“replay unavailable”；
4. Replay 正常流程应先从 FDB TickCommitRecord + keyframe/delta 重建，Object Store blob 只作为 rich trace 附加输入；
5. 删除或重写 `unreplayable` 与 blob 缺失绑定的描述，仅当 FDB replay-critical subset 或 keyframe/delta chain 缺失时才允许 `unreplayable`。

### A-H3 — Phase 2b System Manifest 内部数量、ID 与 R/W contract 不一致，削弱“唯一调度权威”

- Severity: High
- 文件引用：`/tmp/swarm-review-R32/specs/core/06-phase2b-system-manifest.md:20`
- 文件引用：`/tmp/swarm-review-R32/specs/core/06-phase2b-system-manifest.md:76`
- 文件引用：`/tmp/swarm-review-R32/specs/core/06-phase2b-system-manifest.md:181`
- 文件引用：`/tmp/swarm-review-R32/specs/core/06-phase2b-system-manifest.md:189`
- 文件引用：`/tmp/swarm-review-R32/specs/core/06-phase2b-system-manifest.md:211`
- 文件引用：`/tmp/swarm-review-R32/specs/core/06-phase2b-system-manifest.md:391`

问题描述：
Manifest 标题写 “System Schedule (29 systems)”，但同页又声明共计 31 个 system，并且 manifest hash 也按 `system_id_31` 计算。更严重的是，S11-S13 说明文本明确要求 combat systems 不直接修改 `Entity.hits`，只写 `PendingDamage` / `PendingHeal` buffer，S15 是 HitPoints unique writer；但 R/W Matrix 中 S11/S12/S13 的 `HitPoints` 列标为 `W`。同时 S15 描述中又写 “S15 是除 S10 regen 外唯一写 Entity.hits 的 system”，而矩阵里 S24 decay 也写 `HitPoints`。

影响分析：
该文档宣称是全部 tick 系统执行顺序的唯一权威，并且 CI 要基于 R/W Matrix 验证并行安全。如果 matrix 与 prose 不一致，CI 应该允许还是拒绝 S11-S13 直接写 hits 没有确定答案。系统数量不一致还会影响 manifest hash、TickTrace `system_manifest_hash`、replay verifier 与代码注册表一致性检查。架构层面，这使“unique writer contract”和“parallel safety proof”失去可执行含义。

修复建议：
统一 manifest 为一个机器可读 schedule 表：
1. 将标题和所有计数统一为 31 systems，或重新编号使总数与 S01–S29/S22a/S22b 一致；
2. R/W Matrix 中 S11-S13 的 `HitPoints` 应改为只写 `PendingDamage/PendingHeal` buffer，不标 `HitPoints W`；
3. 若 S10 regen、S15 damage_application、S24 decay 都可能写 `HitPoints`，则不要称 S15 是绝对 unique writer，应改成 “combat damage/heal unique committer”，并显式定义 HitPoints write lanes 的顺序与互斥范围；
4. CI contract 应以同一张表生成 manifest hash、R/W conflict check、文档渲染，避免 prose/table 双事实源。

### A-H4 — API Registry 的“单一权威来源”被 validation 文档中的非 canonical 错误码和重复 CommandAction 表削弱

- Severity: High
- 文件引用：`/tmp/swarm-review-R32/specs/reference/api-registry.md:5`
- 文件引用：`/tmp/swarm-review-R32/specs/reference/api-registry.md:96`
- 文件引用：`/tmp/swarm-review-R32/specs/core/02-command-validation.md:154`
- 文件引用：`/tmp/swarm-review-R32/specs/core/02-command-validation.md:169`
- 文件引用：`/tmp/swarm-review-R32/specs/core/02-command-validation.md:171`
- 文件引用：`/tmp/swarm-review-R32/specs/core/02-command-validation.md:269`
- 文件引用：`/tmp/swarm-review-R32/specs/core/02-command-validation.md:374`
- 文件引用：`/tmp/swarm-review-R32/specs/core/02-command-validation.md:548`
- 文件引用：`/tmp/swarm-review-R32/specs/core/02-command-validation.md:666`

问题描述：
API Registry 明确声明 CommandAction、RejectionReason、Host Functions、容量限制等均以该文档/IDL 为准，其他文档不得重新声明可冲突表格或列表。`02-command-validation.md` 虽然提示错误码为说明性名称，但实际校验表继续使用 `TileBlocked`、`StillSpawning`、`ExceedsRoomCapacity`、`InvalidDamageType`、`AlreadyDebilitated(damage_type)`、`MainActionQuotaExceeded` 等不在 API Registry canonical 47 codes 中的名称。文档后部还再次列出 “CommandAction 变体”，重复描述 RangedAttack、ClaimController、Recycle 和特殊攻击。

影响分析：
这会让 SDK、MCP error envelope、玩家文档、engine validation 实现产生分叉：实现者可能误以为这些名称是 wire enum，也可能映射到 `debug_detail`。尤其 `MainActionQuotaExceeded` 是核心 per-drone action slot 约束，如果没有 canonical mapping，将影响客户端可恢复错误处理。重复 CommandAction 表也违背 Registry 单事实源，未来新增/修改 action 时容易漏改。

修复建议：
保留 validation 文档的条件矩阵，但每个失败条件必须显式映射到 Registry canonical code + debug_detail template，例如 `目标格不可通行 → PositionOccupied 或 OutOfRange + debug_detail="TileBlocked: ..."`。删除或改写 §8 的 CommandAction 变体重复表，只保留“见 API Registry §1，本文仅补充 validation condition”。若确实需要新 canonical code（例如 `MainActionQuotaExceeded`），必须先进入 IDL/API Registry，再由 validation 引用，不能在 validation 文档中直接发明。

### A-H5 — Host function API 在 Registry、Sandbox、Tick Protocol 之间不闭合：`host_get_random` 是否存在互相矛盾

- Severity: Medium
- 文件引用：`/tmp/swarm-review-R32/specs/reference/api-registry.md:445`
- 文件引用：`/tmp/swarm-review-R32/specs/reference/api-registry.md:460`
- 文件引用：`/tmp/swarm-review-R32/specs/core/04-wasm-sandbox.md:202`
- 文件引用：`/tmp/swarm-review-R32/specs/core/04-wasm-sandbox.md:207`
- 文件引用：`/tmp/swarm-review-R32/specs/core/04-wasm-sandbox.md:214`
- 文件引用：`/tmp/swarm-review-R32/specs/core/01-tick-protocol.md:932`

问题描述：
API Registry 注册了 6 个 Host Functions，其中包括 `host_get_random`。Tick Protocol 也说 WASM 代码必须使用 `swarm_get_random(sequence)` 从 host 获取确定性随机数。但 WASM Sandbox 的“允许的 Host Function”只列出 terrain、objects_in_range、path_find、world_config、world_rules 五个函数，没有 `host_get_random`；同节还强调 WASM 禁止随机源，容易被解读为没有 RNG host function。

影响分析：
这是 API surface 的直觉性与闭合性问题。SDK/codegen 可能根据 Registry 生成 `host_get_random` binding，而 sandbox whitelist 根据 sandbox 文档拒绝该 import，导致玩家模块部署失败。相反，如果实现者按 sandbox 文档不暴露 deterministic RNG，玩家代码将无法实现需要随机性的 deterministic strategy，也与 Tick Protocol 设计冲突。

修复建议：
以 API Registry 为权威补齐 sandbox 文档：允许列表加入 `host_get_random(sequence, out_ptr, out_len)`，并明确“禁止 OS/WASI random；允许 engine deterministic RNG host function”。同时统一命名：Registry 为 `host_get_random`，Tick Protocol 不应写成 `swarm_get_random`，除非二者分别代表 WASM host ABI 与 SDK wrapper，并需明示映射关系。

### A-M1 — 容量与 worker pool 推导存在架构层面的概念混用

- Severity: Medium
- 文件引用：`/tmp/swarm-review-R32/design/engine.md:319`
- 文件引用：`/tmp/swarm-review-R32/design/engine.md:324`
- 文件引用：`/tmp/swarm-review-R32/design/engine.md:388`
- 文件引用：`/tmp/swarm-review-R32/design/engine.md:393`
- 文件引用：`/tmp/swarm-review-R32/specs/reference/api-registry.md:588`
- 文件引用：`/tmp/swarm-review-R32/specs/reference/api-registry.md:590`

问题描述：
engine.md 的 CPU admission formula 以 `CPU_CORES × PER_CORE_MIPS` 推导 aggregate fuel，但后面的 1000 player hard cap 推导又写 “假设 1000 workers，p50=5ms，理论 peak = 5000ms 但并行化为 ~25ms wall-clock (1000 workers / 40 cores)”。这把 worker 数量、CPU cores、wall-clock、per-player fuel throttling 混在一起，没有形成可执行的 admission contract。API Registry 同时写 target 500、hard cap 1000 benchmark-gated，worker_pool max 默认 256，hard cap 1000。

影响分析：
架构上已经正确识别 worker pool 不是唯一瓶颈，但当前公式容易让实现者误以为把 worker 数扩到 active_players 就能线性消除 1000 players 的 CPU 时间。实际上 1000 long-lived workers 在 32/40 cores 上仍受 CPU quota、scheduler overhead、cgroup、memory pressure、snapshot stitching、IPC fanout 制约。容量合同若不收敛为统一 admission API，会影响 world.toml 配置、degraded mode、operator capacity planning。

修复建议：
将容量部分重构为“合同 + 推导注释”两层：Registry 只保留权威 limits；engine.md 给出 admission controller 输入输出，不给易误导的线性 wall-clock 估算。建议定义：`effective_collect_capacity = measured_p95_player_exec_ms × active_players / effective_parallelism + dispatch_overhead + snapshot_stitching_overhead`，其中 `effective_parallelism` 来自 benchmark/telemetry，而非 worker 数。hard cap 1000 应保持 benchmark-gated，并明确 admission controller 以实时 p95/p99 和 tick budget 判定，而不是固定假设。

### A-L1 — API Registry 自身工具计数与 changelog 不一致

- Severity: Low
- 文件引用：`/tmp/swarm-review-R32/specs/reference/api-registry.md:254`
- 文件引用：`/tmp/swarm-review-R32/specs/reference/api-registry.md:932`

问题描述：
正文声明 Game API 工具清单为 57 个活跃工具 + 11 个 Auth API 工具，但 changelog 的 0.4.0 条目写 “MCP tools 总数为 56 active”。

影响分析：
单独看不是架构阻塞，但它削弱 API Registry 作为自动生成单事实源的可信度。若 CI 或 codegen 使用计数字段进行完整性检查，可能出现误报或漏报。

修复建议：
重新生成 Registry 或修正 changelog 计数，使正文、IDL 生成计数、变更记录一致。若 changelog 不参与机器校验，也应避免保留会误导 reviewer/实现者的旧计数。

## 3. 亮点

1. WASM deferred command model 的方向正确：`04-wasm-sandbox.md:167` 明确禁止 mutating host function，所有状态变更通过 JSON CommandIntent 返回，再由 engine 统一校验与应用。这保持了语言无关、公平资源计量和确定性 replay 的核心目标。

2. CommandIntent → RawCommand → ValidatedCommand 的类型层次直观：`02-command-validation.md:61` 将不可信玩家输出、服务端注入 envelope、校验后执行对象分层表达，接口边界清楚，有助于防止 player_id/source/tick 伪造。

3. Tick Protocol 对 COLLECT 快照边界的描述很强：`01-tick-protocol.md:171` 明确 WASM tick 和 MCP query 读取同一份 COLLECT 开始快照，EXECUTE 中间状态不可观察。这是避免 TOCTOU 与客户端时差歧义的关键抽象。

4. Phase 2a inline + Phase 2b deferred 的分层总体合理：`design/engine.md:221` 把玩家命令的先到先得竞争与被动 ECS 系统拆开，符合编程 RTS 的可解释性需求，也能让 replay order 更直接。

5. API Registry 的机器权威意图值得保留：`api-registry.md:1` 到 `api-registry.md:16` 明确 IDL→Registry→SDK/codegen 链路，方向上能解决跨文档 API 漂移问题。本轮问题主要是部分手写文档仍未完全服从该权威源。

6. Sandbox OS boundary 与 Wasmtime 配置细节足够深入：`04-wasm-sandbox.md:41`、`04-wasm-sandbox.md:361` 对 worker lifecycle、Store reset、seccomp/cgroup/namespace checklist 做了具体约束，抽象层次比泛泛“使用 WASM 沙箱”更可实施。

7. Replay/fuel retry 缓存思路正确：`01-tick-protocol.md:505` 和 `05-persistence-contract.md:266` 明确 FDB commit retry 复用 canonical COLLECT buffer，不重跑 WASM、不追加 fuel。这符合确定性和公平计费目标。

## 4. CrossCheck — 需要跨方向检查

- CX-1: Validation 文档中 `TileBlocked`、`StillSpawning`、`InvalidDamageType`、`MainActionQuotaExceeded` 等非 canonical code 是否只是文档残留，还是 IDL 漏项 → 建议 API/IDL 方向检查 `game_api.idl.yaml` 中 RejectionReason 与 validation condition mapping 的完整性。

- CX-2: `host_get_random` / `swarm_get_random` 命名与 SDK wrapper 边界不清 → 建议 SDK/API 方向检查 TS/Rust SDK 生成的 host ABI 名称、玩家可调用 wrapper 名称、Registry 名称是否一一映射。

- CX-3: room-partition staged commit 若改为 commit marker 模式，查询路径必须忽略未发布 staged rows → 建议 Persistence/Runtime 方向检查 FDB key layout、read source priority、crash recovery、GC staged rows 的完整协议。

- CX-4: S10/S15/S24 都可能写 HitPoints，但 manifest 同时使用 unique writer 术语 → 建议 Determinism/Engine 方向检查 Component R/W 静态分析模型是否支持“分阶段多 writer 但无并发冲突”，或是否需要拆分 `RegenDelta`/`DamageDelta`/`DecayDelta` buffer。

- CX-5: `02-command-validation.md` 多处引用 `specs/security/09-command-source.md`、`specs/core/08-resource-ledger.md`、`specs/gameplay/08-api-idl`，本任务未授权读取 → 建议 Security/Economy/Game Design 方向分别检查这些被引用文档是否与本轮核心子集一致。

- CX-6: API Registry changelog 计数与正文不一致可能来自生成脚本未覆盖 changelog → 建议 Tooling/Docs 方向检查 `generate_api_registry.py` 是否生成或校验 changelog 中的 totals，避免自动生成文档内仍有手写漂移。
