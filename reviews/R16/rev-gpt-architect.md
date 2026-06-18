# R16 Phase 1 Clean-Slate Architecture Review — GPT-5.5

## Verdict

CONDITIONAL_APPROVE

R16 相比此前版本已经从“概念上可行”推进到“可落地设计合同”的阶段：Tick、WASM sandbox、API registry、Phase 2b manifest、persistence contract 都在尝试建立单事实源和可回放边界。整体方向类似 Screeps + FoundationDB simulation/replay + deterministic ECS 的组合，属于已知可成功的架构族。

但当前文档仍有几处“看起来只是文档重复，实际会导致实现分叉”的问题。它们不必推翻架构，但必须在进入实现前收敛，否则团队会在 command enum、拒绝码、tick retry、Phase 2b 调度、sandbox ABI 上各写各的合理解释。

## Strengths

1. 单事实源意识明显增强。`api-registry.md`、`06-phase2b-system-manifest.md`、`05-persistence-contract.md` 都明确声明权威范围，并把 hash/version 写入 TickTrace，方向正确。
2. Tick 生命周期切成 COLLECT / EXECUTE / BROADCAST，且明确 WASM 输出为 deferred command，避免玩家代码直接修改世界状态，这是确定性 MMO RTS 的正确基本形态。
3. FoundationDB 只承载小事务、对象存储承载大 blob 的分层，比“FDB 事务内写一切”更现实，也避免跨存储双写无合同的问题。
4. WASM sandbox 从 runtime、WASI、seccomp、cgroup、module validation 到恶意样本库都有纵深防御，安全边界比单纯 fuel metering 更完整。
5. Phase 2a inline apply + seeded shuffle 的竞争模型直观：先到先得、长期公平、可回放，适合编程竞技游戏。
6. 文档已经开始把 replay、failure semantics、refund、visibility、truncation 当作架构一等公民，而不是实现细节，这是正确的成熟方向。

## Concerns

### A1 — High — “权威源”声明与实际重复定义仍冲突

表面上 `api-registry.md` 是 CommandAction、RejectionReason、Host Functions、容量限制的权威源，但 `02-command-validation.md` 仍重新定义了大量 action、错误码和容量值，并且存在明显不一致：

- `api-registry.md` 注册 RejectionReason 共 35 个，但 `02-command-validation.md` 使用了 `NotMovable`、`Fatigued`、`MissingBodyPart`、`TileBlocked`、`NotSource`、`SourceEmpty`、`TargetFull`、`NotYourRoom`、`TileOccupied`、`AlreadyFullHealth`、`FriendlyTarget`、`AlreadyHacked`、`InvalidDamageType` 等未在 registry 中出现的码。
- `api-registry.md` 全局上限写 `Per-player drone cap = 500`，`02-command-validation.md` 硬性边界写 `MAX_DRONES_PER_PLAYER = 50`，含义可能不同但命名会误导实现者。
- `api-registry.md` 说 WASM 输出/commands per player/tick 为 100，`02-command-validation.md` 批级校验又写整批 tick 输出 ≤ 1MB，而前文和 sandbox/tick 规范多处写输出 ≤ 256KB。
- `api-registry.md` 将 `Leech` / `Fabricate` 定为 custom actions，`02-command-validation.md` 后半又作为 CommandAction 变体展示。

这类问题不是排版问题，而是典型的“大设计文档多处复制表格 → 实现团队按不同文档生成 enum → replay/SDK/错误处理分叉”。建议把 `02-command-validation.md` 中的错误码、action 列表、容量值改为引用 registry 的 symbolic ID，只保留校验流程和逐 action 的语义补充。

### A2 — High — Tick retry / persistence / replay 语义存在三套互相打架的叙述

`01-tick-protocol.md` 与 `05-persistence-contract.md` 对 FDB commit 失败后的行为不一致：

- `01-tick-protocol.md` §3.5 / §8.4 强调 FDB commit 失败时复用同一 COLLECT 结果，不重跑 WASM，fuel 不追加，失败放弃后退还。
- `05-persistence-contract.md` §6 写 commit 失败后“重新执行 tick N（重跑 COLLECT → apply）”，并且 TickTrace 可能因为时间流逝不同。
- `01-tick-protocol.md` 又要求 COLLECT snapshot/MCP query/WASM 看到同一份 current tick snapshot，重试时如果重跑 COLLECT，就会与“同一 tick 的输入封套稳定”发生冲突。

这会直接影响 determinism、fuel 结算、TickTrace hash、玩家公平和故障恢复。架构上必须选一个：更推荐 `COLLECT result is immutable per tick attempt and reused across FDB retries`，只有 tick 被明确放弃并进入下一次完整 tick attempt 时才允许重新 COLLECT，并且 TickTrace 要记录 attempt_id / retry_policy。否则“同一 tick 编号多次重跑 WASM”会成为 replay 和计费的长期炸点。

### A3 — High — Phase 2a / Phase 2b 边界被重新混合，manifest 与 engine 叙述不一致

`engine.md` 的模型是 Phase 2a inline 应用玩家命令，Phase 2b 处理被动系统；`06-phase2b-system-manifest.md` 却把 `command_executor`、`spawn_system`、`build_system`、`recycle_system`、`transfer_system` 放入 Phase 2b，并列出 attack/ranged/heal parallel set。与此同时 `engine.md` 明确 Attack/RangedAttack 在 Phase 2a 直接应用 damage，Phase 2b combat_system 只处理 Tower/DoT 等非玩家命令。

这会让实现者无法判断：

- Move/Attack/Harvest/Transfer 到底是在 Phase 2a 即时改 Bevy World，还是在 Phase 2b command_executor 里统一执行？
- Spawn 是 Phase 2a 扣费、Phase 2b 创建，还是 manifest 中 S03 的系统负责全部 spawn？
- Combat 是玩家攻击 inline damage，还是 S07-S10 pending damage reduce？
- `status_advance_system` 在 `02-command-validation.md` 中被放在 combat 后、regeneration 前；manifest 中又把它放入 Status Effects parallel set，且与 hack/drain/overload 并行。

这是当前最大架构缝隙之一。建议将 manifest 改名或重构为完整 Tick Execution Manifest：明确 Phase 2a command handlers 与 Phase 2b passive systems 分层；或者反过来取消 inline apply，把所有 command 都进入 manifest。两者都可行，但不能同时存在。

### A4 — Medium — Sandbox ABI 与 API registry 的 Host Function 签名不一致

`api-registry.md` 的 Host Functions 使用 `(room_id, out_ptr, out_len)`、`opts_ptr/opts_len` 等签名；`04-wasm-sandbox.md` 的 host functions 使用 `(x, y)`、不带 `room_id`，`host_get_world_rules` 的参数也不同。两者都声称是权威/基线。

这会影响 SDK codegen、WASM ABI version、host ABI compatibility、replay envelope 中的 `host_abi_version`。建议 Host Function ABI 只允许 registry 生成，sandbox 文档只说明安全规则与调用预算，不重新手写签名。

### A5 — Medium — Snapshot truncation 策略存在两套优先级模型

`engine.md` §3.4.4 的 priority bucket 是“自机 > 友方 drone > 敌方 drone > 建筑 > NPC > 资源”，`01-tick-protocol.md` §2.3 则是“关键桶 Spawn/Controller/depot/storage 永不截断 > 己方 drone/建筑 > 敌方/资源点 > 友方/中立”，排序键也从 stable entity_id 变成 distance + entity_id。

这类差异会直接造成玩家 WASM 输入不同、replay hash 不同、策略调试不可解释。建议抽出 `visibility-truncation-manifest` 作为唯一权威，并将 `visibility_truncation_version` 对应到机器可读规则。

### A6 — Medium — “新人可理解性”受过多历史残留和权威声明互相引用影响

R16 文档已经很完整，但新人会遇到强认知负担：

- 多个文件写“详见某文件”，但又保留旧表格和旧代码块。
- `01-tick-protocol.md` 明确写“以下遗留代码待迁移至 manifest 权威定义”，但仍保留足以误导实现的系统顺序。
- `README.md` 架构图仍呈现“指令收集器 + 校验器 + Bevy ECS”这种高层模型，但底层 manifest 已把 command_executor 纳入 Phase 2b。

建议在每份文档开头增加 `Authority / Non-authority` 块：本文件定义什么、不定义什么、冲突时以谁为准。否则“单事实源”原则会被读者体验上的多事实源抵消。

### A7 — Low — 技术选型整体合理，但 Bevy API 稳定性与 deterministic ECS 的绑定需要版本策略

选择 Bevy 有现实优势，但 `.chain()` / schedule / archetype iteration 在 Bevy 小版本变化下可能影响 determinism 或实现方式。文档强调 Wasmtime pinning，却没有同等强调 Bevy pinning、system registration compatibility、manifest-to-code CI 的具体失败策略。

这不是阻塞问题，但建议把 Bevy 版本、schedule API 变更策略、manifest hash 变更流程纳入 tech choices 或 system manifest。

## Missing

1. 缺少机器可读的 registry/manifest 产物。当前表格适合人读，但真正避免分叉需要 `api-registry.yaml`、`system-manifest.yaml`、`limits.yaml` 或等价 IDL，Markdown 从机器源生成。
2. 缺少“冲突检测 CI”的明确范围。文档多次说 CI 校验一致性，但未定义具体校验哪些文件、哪些字段、失败时谁是源。
3. 缺少 Tick attempt/retry 的一等概念。若 commit retry、object-store timeout、WAL fallback 都存在，TickTrace 需要明确 `tick_number`、`attempt_id`、`collect_id`、`commit_id` 的关系。
4. 缺少 admin/source lane 的完整架构边界。本轮限定材料引用 security/09，但未读到；从已读材料看 priority_class 已出现，仍需跨安全方向确认 Admin 是否真的不绕过 validate_and_apply。
5. 缺少 schema 演进策略。`api_version`、`engine_abi_version`、`host_abi_version`、`system_manifest_hash` 都存在，但没有说明旧世界、旧 replay、旧 SDK 如何在版本升级后共存。
6. 缺少“文档生成/冻结流程”。如果 registry 是权威，其他文档必须禁止手写派生表，否则 R17 还会重新漂移。

## CrossCheck — 需要跨方向检查

1. Security: A1/A4 中的 RejectionReason 与 Host Function ABI 冲突会影响安全错误脱敏、oracle 防护和 WASM ABI 边界，需要安全评审确认 registry 是否覆盖所有实际错误码。
2. Determinism/Replay: A2/A3/A5 都会造成 replay 分叉，需要确定性方向检查 Tick retry、Phase 2a/2b、snapshot truncation 是否有唯一执行轨迹。
3. Persistence: A2 需要持久化方向确认对象存储先写、FDB commit retry、WAL、COLLECT cache 的一致恢复模型。
4. SDK/API: A1/A4 需要 API/SDK 方向确认 codegen 输入唯一，禁止 SDK 从 validation 文档抄 enum。
5. Gameplay: A3 需要玩法方向确认 Move-as-action、Attack damage timing、special attack priority 是否仍满足预期手感。
6. Ops: A7 与 Missing #5 需要运维方向确认 Bevy/Wasmtime/FDB/manifest 升级、回滚、replay verification 的 runbook。

## Phase Ordering

1. 先冻结权威源边界：确定 `api-registry`、`phase execution manifest`、`persistence contract`、`visibility truncation manifest` 的唯一职责。
2. 再删除或降级重复表格：把 `02-command-validation.md` 中的 enum/错误码/容量值改成引用 registry，把 `01-tick-protocol.md` 中遗留 system 顺序改成非权威说明。
3. 然后统一 Tick retry 合同：明确 FDB commit retry 是否复用 COLLECT、何时允许重跑 WASM、fuel/refund/TickTrace 如何记录。
4. 接着统一 Phase 2a/2b：选择 inline command apply 或 manifest command execution 二者之一，并让 engine、validation、manifest 三处同名阶段完全一致。
5. 再落机器可读清单和 CI：从 YAML/IDL 生成 Markdown 表格、Rust enum、SDK types、replay envelope constants。
6. 最后进入实现：先做 skeleton + registry codegen + manifest verifier，再实现 sandbox、tick execution、persistence；不要先手写业务逻辑，否则会把当前文档冲突固化进代码。
