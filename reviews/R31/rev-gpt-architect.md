# R31 Clean-Slate Architect Review — GPT-5.5

## 1. Verdict

REQUEST_MAJOR_CHANGES

架构方向整体成立：WASM deferred command model、Bevy ECS deterministic manifest、FDB/Object Store 分层、API Registry 单事实源这些核心抽象与 Swarm 目标一致。但当前文档存在多处“权威合同互相覆盖/冲突”的问题，尤其是 room-partition tick commit、CommandAction 执行 lane、Host Function ABI 与特殊攻击目标状态。这些不是实现细节，而是跨模块数据流和接口边界无法唯一解释的问题，必须先修复。

## 2. 发现的问题

### A-H1 — Room-partition commit 同时声称全局原子、局部推进、2PC 和 best-effort

- severity: High
- 文件引用：
  - `/tmp/swarm-review-R31/specs/core/01-tick-protocol.md:392`
  - `/tmp/swarm-review-R31/specs/core/01-tick-protocol.md:396`
  - `/tmp/swarm-review-R31/specs/core/01-tick-protocol.md:420`
  - `/tmp/swarm-review-R31/specs/core/01-tick-protocol.md:432`
  - `/tmp/swarm-review-R31/specs/core/01-tick-protocol.md:451`
  - `/tmp/swarm-review-R31/specs/core/05-persistence-contract.md:340`
  - `/tmp/swarm-review-R31/specs/core/05-persistence-contract.md:347`
  - `/tmp/swarm-review-R31/specs/core/05-persistence-contract.md:370`
- 问题描述：`01-tick-protocol.md` 先定义生产环境强制 room-partition，并要求 GlobalTickCommit 失败时“所有房间回滚，tick 放弃”；cross-room intent 又要求 All-or-Reject、无 partial commit。但同一文档的错误恢复表又说“单房间 commit 失败：该房间 snapshot 恢复，其他房间独立推进”。`05-persistence-contract.md` 进一步把 room-partition 描述为 `2-phase commit`，但失败策略写成 `fallback to best-effort`，与 All-or-Reject 直接冲突；还保留 `单事务 MVP (默认)`，与生产强制 room-partition 和“设计即目标状态”不一致。
- 影响分析：这是 tick 原子性和世界一致性的核心边界。不同实现者可能分别实现为：全世界 tick 原子、每房间局部原子、跨房间 2PC、或 best-effort partial commit。结果会直接影响 replay、玩家可见状态、资源跨房间转移、drone 穿越出口、rollback/fuel refund，以及 TickCommitRecord 的含义。该问题会让 FDB key layout、GlobalTickCommit、WAL、snapshot restore 和 replay verifier 全部无法稳定设计。
- 修复建议：将 room-partition 提交模型收敛为单一权威状态机，并删除所有相反语义。推荐目标设计为：每 tick 先在内存中完成全局 deterministic simulation；持久化阶段按 room 分区写入 per-room commit records；只有 GlobalTickCommit 成功后 tick 才对外可见并推进 tick_counter。任何 per-room commit、cross-room intent 或 GlobalTickCommit 失败均导致该 tick abandon + 从 pre-apply snapshot 恢复；不允许“其他房间独立推进”或 `best-effort`。若确实需要局部故障隔离，应显式定义为不同设计：每房间 tick_head 独立推进、跨房间 intent 延迟结算、客户端状态版本按 room 分裂；不能与全局 replay checksum 混用。

### A-H2 — API Registry 的单事实源承诺被手写语义和目标状态冲突破坏

- severity: High
- 文件引用：
  - `/tmp/swarm-review-R31/specs/reference/api-registry.md:3`
  - `/tmp/swarm-review-R31/specs/reference/api-registry.md:5`
  - `/tmp/swarm-review-R31/specs/reference/api-registry.md:75`
  - `/tmp/swarm-review-R31/specs/reference/api-registry.md:87`
  - `/tmp/swarm-review-R31/specs/reference/api-registry.md:90`
  - `/tmp/swarm-review-R31/specs/core/06-phase2b-system-manifest.md:7`
  - `/tmp/swarm-review-R31/specs/core/06-phase2b-system-manifest.md:76`
  - `/tmp/swarm-review-R31/specs/core/06-phase2b-system-manifest.md:301`
- 问题描述：API Registry 声称由 IDL 自动生成、是 API 合约单一权威来源，并禁止其他文档重声明可冲突表格。但同一 Registry 将 `Leech`、`Fabricate` 标为 `⏳ Tier 2`，而 Phase2b manifest 明确声明 8 种特殊攻击“全部作为核心目标设计”“不存在 Tier 2/Phase/Future 语义”。这不是单纯措辞问题：Registry 是 SDK/codegen/CI 的机器入口，而 manifest 是执行调度权威，两者对 action 是否核心启用给出相反答案。
- 影响分析：SDK 生成器、世界 action manifest、validator、教程/Novice gating、replay verifier 可能对 `Leech`/`Fabricate` 产生不同处理。若 Registry 生成的 SDK 将其视为 Tier 2 或可选，而 engine manifest 将其纳入核心 S22a/S22b buffer，玩家代码、服务器校验和回放记录会分叉。
- 修复建议：以目标状态统一 IDL/API Registry：删除 `Leech`/`Fabricate` 的 Tier 2 标记，明确它们是 Standard/Arena core-enabled special_attack；若仍需模式 gating，只在 `Mode Unlock Strategy` 或 world config 中表达启用策略，不在 CommandAction 权威表中标为未来/二线。并建立 CI：manifest 中的 special attack set 必须等于 API Registry `special_attack` set，且不得出现 `Tier/Future/Phase` 标记。

### A-H3 — 已注册 CommandAction 缺少明确执行 lane，破坏“所有入口走同一管线”

- severity: High
- 文件引用：
  - `/tmp/swarm-review-R31/specs/reference/api-registry.md:66`
  - `/tmp/swarm-review-R31/specs/reference/api-registry.md:72`
  - `/tmp/swarm-review-R31/specs/reference/api-registry.md:73`
  - `/tmp/swarm-review-R31/specs/reference/api-registry.md:787`
  - `/tmp/swarm-review-R31/specs/core/02-command-validation.md:35`
  - `/tmp/swarm-review-R31/specs/core/02-command-validation.md:152`
  - `/tmp/swarm-review-R31/specs/core/02-command-validation.md:592`
  - `/tmp/swarm-review-R31/specs/core/06-phase2b-system-manifest.md:92`
  - `/tmp/swarm-review-R31/specs/core/06-phase2b-system-manifest.md:127`
- 问题描述：API Registry 注册了 `TransferToGlobal` 与 `TransferFromGlobal` 两个 `economy_operation` CommandAction，并声明它们可由 WASM tick() 发出。但 `02-command-validation.md` 的逐指令校验矩阵和字段级穷举校验表没有为这两个 action 定义校验规则；`06-phase2b-system-manifest.md` 的 Phase 2a inline handlers 也只列出 `Transfer`/`Withdraw`，没有 Global Storage action 的 handler、排序位置、资源账本写入时机或 refund 语义。
- 影响分析：这是 API 层和执行层之间的黑洞。玩家/SDK 可以生成合法 CommandAction，但 validator/manifest 不知道如何执行；或者实现者会把 economy lane 做成另一条旁路，违反“所有入口走同一 validate_and_apply 管线”的架构原则。尤其 AlliedTransfer 有延迟、cooldown、daily cap、alliance age 等状态，若不纳入 tick manifest 与 resource_ledger，会影响 replay 与资源守恒。
- 修复建议：为 `TransferToGlobal` / `TransferFromGlobal` 增加明确执行 lane。推荐：在 Phase 2a 增加 `economy_operation_system` 或扩展 S05 `transfer_system`，声明其 reads/writes、resource ledger 操作、pending transfer 状态、alliance/cooldown/cap 校验、refund 策略和 TickCommitRecord 字段。`02-command-validation.md` 必须补齐逐指令校验表与字段级穷举表；`06-phase2b-system-manifest.md` 必须把该 lane 纳入 manifest hash 和 R/W matrix。

### A-M1 — Host Function ABI 在 sandbox、Registry、determinism contract 之间不闭合

- severity: Medium
- 文件引用：
  - `/tmp/swarm-review-R31/specs/core/04-wasm-sandbox.md:202`
  - `/tmp/swarm-review-R31/specs/core/04-wasm-sandbox.md:207`
  - `/tmp/swarm-review-R31/specs/core/04-wasm-sandbox.md:215`
  - `/tmp/swarm-review-R31/specs/reference/api-registry.md:439`
  - `/tmp/swarm-review-R31/specs/reference/api-registry.md:441`
  - `/tmp/swarm-review-R31/specs/reference/api-registry.md:454`
  - `/tmp/swarm-review-R31/specs/core/01-tick-protocol.md:918`
  - `/tmp/swarm-review-R31/specs/core/01-tick-protocol.md:929`
- 问题描述：`04-wasm-sandbox.md` 的允许 Host Function 列表只有 5 个，不包含 `host_get_random`；API Registry 则声明 Host Functions 共 6 个，并把 `host_get_random` 定义为权威签名；`01-tick-protocol.md` 的 RNG 合同又要求 WASM 必须通过 `swarm_get_random(sequence)` 从 host 获取确定性随机数。函数名也在 `host_get_random` 与 `swarm_get_random` 之间不统一。
- 影响分析：ABI 不闭合会导致 SDK/runtime/import whitelist 分叉。严格按 sandbox 文档实现会拒绝玩家模块导入 `host_get_random`；严格按 Registry 实现又会违反 sandbox 白名单。RNG 是确定性 replay 的核心能力，接口名称和是否暴露不能含糊。
- 修复建议：以 API Registry 为机器权威，更新 sandbox 白名单加入 `host_get_random(sequence: u64, out_ptr, out_len) -> i32`，并将 `01-tick-protocol.md` 的 `swarm_get_random` 统一改为同一 ABI 名称，或明确 `swarm_get_random` 是 SDK wrapper、底层 import 为 `host_get_random`。同时补充 visibility/预算/fuel/terminal_state 行为：该函数只读、不改变世界状态、由 `(tick_seed, player_id, drone_id, sequence)` 派生，调用失败不产生 command。

### A-M2 — Phase/System 数量和权威调度表述存在自相矛盾，削弱 manifest 可实施性

- severity: Medium
- 文件引用：
  - `/tmp/swarm-review-R31/specs/core/06-phase2b-system-manifest.md:20`
  - `/tmp/swarm-review-R31/specs/core/06-phase2b-system-manifest.md:76`
  - `/tmp/swarm-review-R31/specs/core/06-phase2b-system-manifest.md:145`
  - `/tmp/swarm-review-R31/specs/core/06-phase2b-system-manifest.md:421`
  - `/tmp/swarm-review-R31/specs/core/06-phase2b-system-manifest.md:442`
  - `/tmp/swarm-review-R31/design/engine.md:210`
  - `/tmp/swarm-review-R31/specs/core/01-tick-protocol.md:390`
- 问题描述：Manifest 章节标题写 `System Schedule (29 systems)`，正文又说“共计 31 个 system”；后文 `Phase 2b: Deferred Systems (S07–S31)`，但实际编号到 S29，新增项为 S22a/S22b 而非 S30/S31；CI 表也要求验证 31 systems。engine/tick-protocol 又用“Phase 2a inline 6 + Phase 2b deferred 25 = 31 systems”的说法。
- 影响分析：该文档被声明为调度唯一权威并进入 manifest hash，编号/数量不稳定会直接影响实现注册表、CI 静态分析、system_id versioning、TickTrace `system_manifest_hash` 和回放工具的解释。虽然目前可人工推断含义，但机器校验和开发者 onboarding 会被误导。
- 修复建议：统一命名模型：要么把 S22a/S22b 作为独立 system 并编号到 S30/S31；要么声明总数为 29 个主序号 + 2 个 sub-system，并在 manifest hash 中明确 sub-system ID。章节标题、Phase 2b 范围、CI 检查项、engine.md 和 tick-protocol 引用必须采用同一计数口径。

### A-M3 — 目标状态文档仍保留 MVP/Tier/Future 语义，违反当前设计评审原则并污染架构判断

- severity: Medium
- 文件引用：
  - `/tmp/swarm-review-R31/design/engine.md:170`
  - `/tmp/swarm-review-R31/design/engine.md:242`
  - `/tmp/swarm-review-R31/specs/core/05-persistence-contract.md:347`
  - `/tmp/swarm-review-R31/specs/reference/api-registry.md:87`
  - `/tmp/swarm-review-R31/specs/reference/api-registry.md:90`
  - `/tmp/swarm-review-R31/specs/reference/api-registry.md:711`
- 问题描述：文档多处仍使用 `MVP`、`Tier 2`、`Future RFC`、`playtest 阶段可能被挑战` 这类阶段/路线图语言。任务要求明确“设计即目标状态”“不考虑分阶段实现”。其中部分词只是叙述噪声，但 `single transaction MVP`、`Leech/Fabricate Tier 2` 这类语义已经影响技术合同。
- 影响分析：实现者会无法判断哪些是当前必须实现的目标设计，哪些是可选/未来扩展。对 API、调度、容量和持久化这类核心合同而言，阶段词会导致分叉实现和 review 争议。
- 修复建议：清理目标状态文档中的阶段语言。若某机制是目标设计，就直接写为标准设计；若是可选扩展，放入明确的 RuleMod/RFC 扩展文档，不要在核心 API/manifest 中标为 Tier/Future。容量不确定性可表达为 `benchmark-gated`，但不应使用 MVP 作为架构状态。

## 3. 亮点

- WASM deferred command model 的边界清晰：`tick(snapshot) -> CommandIntent[] -> RawCommand -> ValidatedCommand` 将不可信玩家代码与权威世界修改隔离，符合可回放和安全目标。
- ECS manifest 的 Unique Writer Contract 是正确方向：S16-S22b typed buffer + S22 serial committer 能降低并行数据竞争，并让特殊攻击状态推进有单一写入点。
- FDB replay-critical subset 与 Object Store rich/debug blob 分层合理：把小型、不可降级字段留在 FDB，同步对象 hash/pointer，大 blob 异步化，符合 FDB 事务模型和 replay 审计需求。
- API Registry 作为 IDL 生成物的定位正确：CommandAction、RejectionReason、Host Functions、容量限制集中注册，是防止 SDK/engine/MCP 分叉的必要抽象。
- Snapshot 架构从 per-player serialization 改为一次 world snapshot + room shard stitching，抽象层次合理，能同时服务 WASM 与 MCP snapshot 一致性。
- 可见性优先错误策略（`NotVisibleOrNotFound`）和 player/admin trace 分层设计良好，避免 API 成为实体存在性 oracle。

## 4. CrossCheck — 需要跨方向检查

- CX-1: `host_get_random` 暴露给 WASM 后是否允许玩家通过大量调用推断 shuffle/combat RNG 相关流 → 建议 Security 检查 RNG domain separation、sequence 滥用和跨 namespace 隔离。
- CX-2: Room-partition 若采用全局 tick 原子提交，FDB 多事务提交期间的 crash recovery 是否能证明没有 partial externally-visible state → 建议 Persistence/Backend 检查 WAL、GlobalTickCommit、per-room commit record 的恢复协议。
- CX-3: `TransferToGlobal` / `TransferFromGlobal` 进入 CommandAction 后，AlliedTransfer 的 alliance age、daily cap、delay queue 是否与 ResourceLedger 数学公式一致 → 建议 Economy 检查资源守恒、税费、refund 与延迟到账。
- CX-4: `Leech` / `Fabricate` 从 Tier 2 统一为核心设计后，其 gameplay counterplay、教程暴露和 Novice/Standard gating 是否合理 → 建议 Gameplay/UX 检查上手复杂度与反制窗口。
- CX-5: TickTrace retention、Object Store TTL、keyframe GC 与“永久可 replay / audit_gap / unreplayable”语义是否一致 → 建议 Observability/Replay 检查审计 SLA 与冷存恢复路径。
