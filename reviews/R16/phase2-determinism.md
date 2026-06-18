# R16 Phase 2 CrossCheck — Determinism 补充验证

输入范围：R16 Phase 1 的 CrossCheck 段落及 Determinism 相关来源，重点对照 rev-gpt-determinism、rev-dsv4-determinism、rev-gpt-architect、rev-dsv4-architect、rev-gpt-performance、rev-gpt-apidx、rev-dsv4-apidx。

说明：当前 `/data/swarm/docs` 的 `main` 已有清理提交移除 `reviews/R16/rev-*.md`；本补充阅读从上一评审提交 `8c02b92` 中读取 R16 review 原文，并对照当前 docs 中仍存在的权威/派生文档。

## CrossCheck item -> Finding -> disposition

### 1. Phase 2b schedule / spawn-death_mark / spawning_grace 是否构成 replay blocker

Finding:
- 构成 blocker。多个来源一致指出 Phase 2a/2b 与 System Manifest 不闭合：
  - rev-gpt-determinism T1/T6：Phase 2b 权威调度与其他文件冲突；parallel safety 与特殊攻击 reducer 不足。
  - rev-dsv4-determinism C1/H1/M2：death_mark/spawn 顺序、command_executor 属于 Phase 2a 还是 Phase 2b、并行集错误回滚语义均影响确定性。
  - rev-gpt-architect A3：manifest 把 `command_executor`、`spawn_system`、`build_system`、`recycle_system`、`transfer_system` 放入 Phase 2b，与 engine.md 的 inline apply 模型冲突。
  - rev-dsv4-architect C1/C2/M4：System Manifest 与 engine.md/01-tick-protocol 的 schedule 不一致，且 `spawning_grace_system` 在 manifest 中位于 S22 World Maintenance，晚于 S07-S10 combat/damage，允许 birth-tick kill。
- 当前文档证据：
  - `design/engine.md` 仍描述 `death_mark → spawn → spawning_grace → combat → status_advance → aging → death_cleanup`，并声明 newborn 本 tick 免疫。
  - `specs/core/01-tick-protocol.md` §9.6 仍列出同样的 must-chain 顺序。
  - `specs/core/06-phase2b-system-manifest.md` 则定义 S03 spawn，S07-S10 combat/damage，S11 death_marker，S20-S22 World Maintenance，其中 S22 才是 `spawning_grace_system`；同时 manifest 第 14 行标题写 “20 systems”，正文又列 S01-S27 并称 27 个 system。
- Determinism impact：同一 tick 中新 spawn entity 是否先获得 grace、是否参与 combat、RoomCap 是否由 death_mark 先释放、command apply 是 inline 还是 manifest system，都会改变 `tick(seed, state, commands) -> new_state`。两个实现者按不同文档编码会产生不同 state checksum；replay verifier 也无法知道哪个 schedule 是权威。

Disposition: blocker

Required closure:
- 将 `06-phase2b-system-manifest.md` 升级/重构为完整 Tick Execution Manifest，覆盖 Phase 2a command handlers + Phase 2b passive systems；或删除 manifest 中 command_executor/build/transfer 等 Phase 2a 项，明确其为 pre-Phase 2b。
- `spawning_grace` 必须拆成：spawn 后立即 add grace（combat 前）与 combat/decay 后 expiry/decrement（如果需要），并在 manifest 中给出两个 stable system id。
- 特殊攻击改为 pending intents -> canonical priority reducer -> status_advance，或者补齐可机器验证的 R/W proof 与 reducer tie-breaker。
- 删除 engine.md / 01-tick-protocol / 02-command-validation 中可照抄的旧 schedule，只保留对 manifest 的引用。

### 2. CommandAction/RejectionReason closure 与 codegen 对 determinism 的影响

Finding:
- 当前仍是 high，接近 blocker；作为 B1 的 determinism 子项应阻塞实现冻结。CrossCheck 来源高度一致：
  - rev-gpt-determinism T2/T7：CommandAction 与 RejectionReason 注册表不闭合，`command_hash = Blake3(command_json)` 缺 canonical codec。
  - rev-gpt-architect A1/A4：api-registry 声称权威，但 validation/host ABI 等仍手写冲突事实；codegen 输入唯一性缺失。
  - rev-gpt-apidx X1/X2/X3/X4 与 rev-dsv4-apidx C3/C4/H1/H3/M3/M5：registry、commands.md、IDL/codegen、host ABI、SwarmError、snapshot format 多处冲突。
  - rev-dsv4-architect L1-L3/M5：`TickValidationFailed`、`NotMovable`、`StillSpawning` 等命名与 registry 不一致。
- 当前文档证据：
  - `specs/reference/api-registry.md` 声称 CommandAction 19 个、RejectionReason 35 个且为单一权威。
  - `specs/core/02-command-validation.md` 仍使用 registry 外的 rejection reasons：`SourceEmpty`、`TileOccupied`、`TargetFull`、`Fatigued`、`MissingBodyPart`、`TickValidationFailed` 等，并在 §8 重新列 CommandAction 变体。
  - `02-command-validation.md` 使用 `command_hash = Blake3(command_json)`，但未定义 canonical JSON/IDL binary encoding。
- Determinism impact：
  - 不同 SDK/Gateway/Engine 若从不同表 codegen，会接受/拒绝不同 action 或 reason，导致 command queue 和 TickTrace 分叉。
  - registry 外 reason 若被某实现映射为 generic internal error、另一实现映射为 explicit rejection，会影响 refund/fuel ledger、trace hash 与 metrics。
  - raw JSON hash 未 canonicalize 时，字段顺序、数字表示、Unicode/string escaping、未知字段是否先拒绝都会改变 tiebreaker。

Disposition: high

Required closure:
- 建立唯一机器事实源：`game_api.idl` 或 machine-readable registry；Markdown 表格全部生成。
- CI 扫描所有 docs/code 中的 Action/Reason/Tool/ABI 字面量，未注册即失败。
- `CommandAction`、custom action manifest、`RejectionReason`、Host ABI error、SwarmError namespace 建立闭包映射。
- `command_hash` 改为 canonical binary IDL encoding hash；如保留 JSON，必须指定 RFC 8785/JCS 或项目自定义 canonical JSON，并明确服务端 envelope 字段是否参与 hash。

### 3. FDB commit retry 是否必须复用 COLLECT canonical buffer

Finding:
- 必须复用；当前冲突构成 blocker。CrossCheck 来源一致：
  - rev-gpt-determinism T4：`01` 与 `05` 对 commit retry 语义冲突；重试必须复用首次 COLLECT canonical command envelope、snapshot_hash、wasm_status、fuel，不重跑 WASM。
  - rev-gpt-architect A2：推荐 `COLLECT result is immutable per tick attempt and reused across FDB retries`，仅明确放弃 tick attempt 后才允许重新 COLLECT，并记录 attempt_id。
  - rev-gpt-performance P2：重跑 COLLECT 是性能与确定性双重风险，会造成 retry storm。
- 当前文档证据：
  - `specs/core/01-tick-protocol.md` §9.8 明确禁止通过竞争失败构造重试绕过 budget：“同 tick 内 WASM 仅执行一次（首次 COLLECT），后续重试不触发新的 WASM 调用”。
  - `specs/core/05-persistence-contract.md` §6 仍写 commit 失败后“下次循环重新执行 tick N（重跑 COLLECT → apply）”，并承认 TickTrace 可能不同。
- Determinism impact：重跑 COLLECT 会重新走 wall-clock timeout、worker pool 调度、host cache、snapshot truncation、path budget、WASM trap/partial-output 等非纯状态因素；即使 world state 回滚，COLLECT 的 observed timing 与 resource pressure 也不可由 `(seed,state,commands)` 闭包推导。

Disposition: blocker

Required closure:
- `05-persistence-contract.md` 删除“重跑 COLLECT”语义，改为 retry 同一 collect_id 的 canonical buffer。
- TickTrace/manifest 明确 `tick_number`、`attempt_id`、`collect_id`、`commit_id`、`retry_count`、`retry_policy`。
- 对象 blob/manifest 可重新从同一 canonical TickTrace buffer 派生，但不得重新执行 WASM 或重新解析不可信输出。
- commit 失败 N 次后的 terminal transition 必须唯一：rollback snapshot + mark attempt failed + refund/fuel ledger 按 canonical buffer 结算或整体放弃，禁止隐式重采集。

### 4. output oversize truncate vs discard 语义

Finding:
- 当前为 high；若实现进入代码前不统一，会成为 replay blocker。CrossCheck 来源：rev-gpt-determinism T3 明确指出 `01`、`02`、`04` 对 WASM output 超限/partial-output 语义冲突。
- 当前文档证据：
  - `specs/core/04-wasm-sandbox.md` §1：trap/OOM/timeout/partial-output 均丢弃该玩家当 tick 全部指令输出，记录 `output_discarded`。
  - `specs/core/02-command-validation.md` §1.1：总字节数 ≤256KB；非 JSON 字节或 schema 失败时整个 tick 输出丢弃，记录 `TickValidationFailed`。
  - `specs/core/01-tick-protocol.md` §9.7：WASM tick() 输出超 256KB 时“整批丢弃——不保留部分解析的前缀”，但拒绝码写为 `output_truncated`，命名仍暗示截断。
  - Snapshot input truncation 是另一语义：`snapshot.truncated=true` 且 deterministic sort/truncate。该语义不应与 WASM output oversize 混用。
- Determinism impact：JSON output prefix truncation 会依赖 parser recovery、UTF-8 边界、数组逗号/闭合处理和 SDK serialization；discard 则是闭合、可验证的单一状态。当前“truncated”命名可能导致实现者保留前缀。

Disposition: high

Required closure:
- 对 WASM output 采用唯一规则：超过 cap / partial-output / invalid JSON / schema violation => 整批丢弃，不产生任何 command，不 prefix parse。
- 统一 TickTrace 状态枚举，如 `OutputDiscarded { reason: OutputTooLarge | PartialOutput | InvalidJson | SchemaViolation | Trap | Oom | Timeout }`。
- 将 `output_truncated` 改名为 `output_discarded` 或 `OutputTooLarge`；保留 `truncated` 仅用于 snapshot/query response。
- 明确是否进入 refund/fuel ledger：未进入 command validation 的输出失败不产生 per-command rejection；只记录 per-player COLLECT status。

### 5. event-keyed counter RNG / canonical codec/hash / JSON canonicalization

Finding:
- 当前为 high。R16 已有 namespace seed 与 Blake3 XOF，但 draw-level 合同不足；canonical codec/hash 也未闭合。
- CrossCheck 来源：
  - rev-gpt-determinism T5/T7：namespace seed 不足，必须 event-keyed counter-based RNG；`command_hash = Blake3(command_json)` 缺 canonical JSON/codec。
  - rev-dsv4-determinism M3：per-entity stream seed/domain_sep 未完整文档化。
  - rev-dsv4-architect H2：canonical JSON 未指定会让不同 SDK 的同义 command hash 不同。
  - rev-gpt-apidx/rev-dsv4-apidx：IDL/codegen 与 snapshot serialization format 未定义，影响 SDK 与 replay。
- 当前文档证据：
  - `specs/core/01-tick-protocol.md` §9.5 只列 `combat`、`loot`、`npc_spawn`、`event` namespaces，并说使用 Blake3 XOF；未定义每个事件的 canonical `event_key` 与 `draw_index`。
  - `specs/reference/api-registry.md` TickTrace envelope 有 `canonical_codec_version` 字段，但未定义 codec 行为。
  - `02-command-validation.md` 的 final sort tiebreaker 仍是 raw `Blake3(command_json)`。
- Determinism impact：共享 mutable RNGState 按 ECS/query/parallel iteration order draw，会让 parallel set、HashMap/registry iteration、custom action、RuleMod 引入隐式非确定性。raw JSON hash 使 SDK serializer 成为隐式状态机。

Disposition: high

Required closure:
- 定义 counter-based API：`rng(namespace, world_seed, tick, event_key, draw_index) -> uN`，禁止通过 mutable stream `next()` 依赖迭代顺序。
- 为所有 RNG 用例列 domain_sep 与 event_key schema：combat damage、crit、loot、npc spawn、world event、custom action/RuleMod、spawn tie-break、status reducer tie-break。
- 所有 registry/world config/custom_actions/resource maps 使用 canonical sort + canonical hash；禁止 HashMap iteration 进入 hash 或执行顺序。
- 定义 canonical codec：command_hash、commands_hash、snapshot_hash、state_checksum、manifest_hash、TickTrace content_hash 均指向同一版本化 codec；避免 raw JSON bytes。

### 6. World SIMD default true 是否应 opt-in 或需要 CPU feature fingerprint

Finding:
- 应降级为 opt-in；若保留默认 true，则至少必须在 TickInputEnvelope/module cache/replay metadata 中加入 CPU feature fingerprint，并限制跨节点迁移。Disposition 评为 high（dsv4-determinism 评 Critical；gpt-determinism 与 performance 均要求明确边界）。
- CrossCheck 来源：
  - rev-dsv4-determinism C2：World 默认 SIMD true 破坏跨架构确定性，建议 World 默认 false；若启用，TickInputEnvelope 加 `simd_arch_fingerprint`。
  - rev-gpt-determinism T12：普通 SIMD/浮点与玩家 WASM 浮点策略未定义，authoritative replay 不重跑 WASM 仍需明确 dry-run/degraded verification 边界。
  - rev-gpt-performance P3：module cache key 有 target_arch 但还应含 CPU feature profile；跨节点不一致需重编译或禁用 SIMD。
- 当前文档证据：
  - `specs/core/04-wasm-sandbox.md` §2.2：`config.wasm_simd(world_config.simd_enabled)`，注释为 World 默认 true、Arena 默认 false；`wasm_relaxed_simd(false)`。
  - `design/engine.md` §3.4.3 又把 SIMD 列入禁用的 WASI/能力列表，存在描述冲突。
- Determinism impact：即使 replay 通常使用 committed Command[] 而不重跑 WASM，在线 authoritative COLLECT 仍决定初始命令；跨 CPU、跨 Wasmtime/cranelift target、浮点 NaN/rounding/fast-math 可能导致不同 commands。dry-run/simulate/recovery 若重跑 WASM，也会暴露不一致。

Disposition: high

Required closure:
- 默认：World 与 Arena 均 `simd_enabled=false`；SIMD 作为 world/operator opt-in。
- 若 opt-in：module cache key 增加 `cpu_feature_profile`、`cranelift_flags`、`wasmtime_version`、`validation_policy_version`；TickTrace/TickInputEnvelope 记录 profile hash。
- 禁止 relaxed SIMD 已正确，但还需明确玩家 WASM 浮点策略：禁止浮点影响 command output，或固定 NaN canonicalization/rounding/profile，并声明跨 profile replay 不权威。
- 跨节点迁移时 profile 不匹配 => 禁用 SIMD/重编译/拒绝迁移；dry-run/simulate 输出必须标注 `authoritative:false` 或要求 profile match。

## 综合结论

Determinism Phase 2 补充验证确认：R16 的确定性问题主要不是缺少机制，而是“多个权威源同时存在”。其中 Phase 2b schedule/spawning_grace 与 FDB commit retry 已达到 replay blocker；CommandAction/RejectionReason/codegen、WASM output 超限语义、event-keyed counter RNG/canonical codec、World SIMD 默认策略均为进入实现前必须关闭的 high-risk 合同缺口。

建议 Speaker 将本补充并入 R16 addendum/R17 输入，并维持 REQUEST_MAJOR_CHANGES；在实现前先完成：完整 Tick Execution Manifest、机器事实源 codegen、commit retry state machine、canonical codec/RNG spec、SIMD policy 五个收敛项。
