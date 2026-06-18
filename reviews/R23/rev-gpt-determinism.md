# R23 确定性评审（GPT-5.5）

## Verdict

CONDITIONAL_APPROVE

设计已经把确定性作为核心合同显式化：tick 分阶段、命令排序、RNG namespace、TickTrace、system manifest、固定点数值、IndexMap、WASM 沙箱禁用时间/随机/线程等关键点都有覆盖。整体方向可批准进入下一轮，但仍存在若干会导致 replay 分叉或实现歧义的合同冲突，需在进入实现前修正为单一权威定义。

## Strengths

- 单 tick 形态基本闭合：`COLLECT → EXECUTE → BROADCAST` 边界清晰，`EXECUTE` 由 FDB commit 作为唯一权威提交点，失败时回滚 Bevy World 并复用 COLLECT buffer。
- RNG 合同有明确方向：排序 shuffle 使用 Blake3 派生，RNG 按 namespace 隔离，避免 OS entropy；文档明确不使用 `std::hash`、不依赖 HashMap 迭代顺序。
- 回放关键字段意识较强：TickTrace/TickInputEnvelope 包含 `system_manifest_hash`、`world_config_hash`、`mods_lock_hash`、`canonical_codec_version`、`visibility_truncation_version` 等 replay-sensitive 版本字段。
- WASM 沙箱对隐式非确定性源处理较全面：禁用 clock/random/filesystem/network/threads/atomics/relaxed SIMD，host function 只读且经可见性过滤。
- 数值确定性方向正确：API registry 声明移除 `f64`，资源/伤害/进度使用整数或 fixed-point，舍入规则为 floor，overflow 采用 saturating/checked math。
- Phase 2b manifest 明确 29 个 system、stable ID、R/W matrix、manifest hash 与显式迭代顺序，是跨节点一致执行的良好基础。

## Concerns

### T1 — High — TickTrace / replay-critical 合同互相冲突

`01-tick-protocol.md` §9.4 要求 TickTrace 与状态在同一 FDB 事务中原子提交，且禁止“状态成功但审计不完整”。但 `05-persistence-contract.md` §2.2/§3 又把完整 TickTrace blob 放入对象存储异步写入，并允许 blob 缺失导致 `terminal_state = audit_gap`。同时 `05-persistence-contract.md` §2.1 将 `commands + rejections`、`fuel_ledger`、`deploy_activation_decision` 列为 FDB replay-critical，而 §3 Phase B 示例只写 `tick_head/tick_manifest/hash_chain/small mutations`，没有明确这些 replay-critical 字段是否完整落在 FDB。

确定性风险：实现者可能只把 hash/pointer 写入 FDB，把 command/rejection/fuel 放入 blob；一旦 blob 缺失，`tick(seed,state,commands)` 的 commands 输入不可恢复，replay 不再闭包。

要求修正：明确“最小 replay trace”必须在 FDB 事务中原子提交，至少包括 canonical command list、rejections、fuel ledger、activation decisions、manifest hashes、state checksum；对象存储只允许保存 rich trace/per-system metrics/debug detail。若 rich blob 缺失，状态 replay 仍必须可完成，不能依赖 blob 取回 canonical commands。

### T2 — High — `terminal_state` 枚举语义不一致

`api-registry.md` §6.1 的 `terminal_state` 是 WASM/tick execution 状态：`Success/FuelExhausted/TimeoutExceeded/.../NotExecuted`。`05-persistence-contract.md` §7.2 的终端状态是 blob/replay 状态：`verified/audit_gap/unreplayable/reconstructable`。`engine.md` §3.3 又把 `terminal_state` 描述为 `verified/audit_gap/unreplayable/reconstructable`。

确定性风险：同一个字段名承载两类状态，replay verifier、audit UI、engine 可能写入/解释不同枚举，导致跨版本或跨节点校验失败。

要求修正：拆分为两个字段，例如 `wasm_terminal_state`（Success/FuelExhausted/...）与 `trace_integrity_state`（verified/audit_gap/...），并在 TickTrace Envelope、Persistence Contract、API Registry 中统一命名和编号。

### T3 — High — 特殊攻击优先级在不同文件中相互矛盾

`02-command-validation.md` §3.16 定义同 tick 多特殊攻击优先级为 `Disrupt > Fortify > Debilitate > Hack > Drain/Leech > Overload > Fabricate`；但 `06-phase2b-system-manifest.md` §S14 reducer resolve 写成 `Hack > Drain > Overload > Debilitate > Disrupt > Fortify`。这直接影响同一 tick 的状态结果。

确定性风险：两个节点如果分别按不同文档实现，同一 pending intents 会产生不同 StatusState、不同 damage/fuel/resource 结果，state_checksum 分叉。

要求修正：选择唯一权威优先级，并把另一处改为引用，不再重列。建议以 `06-phase2b-system-manifest.md` 作为调度权威，但优先级本身应在 action manifest/IDL 中机器可读并进入 `world_action_manifest_hash`。

### T4 — High — `status_advance_system` 与并行 status systems 存在唯一写入者矛盾

`06-phase2b-system-manifest.md` §S16-S22 表示 `hack_system/drain_system/overload_system/...` 都写各自 StatusState；但后续 “Special Attack Unique Writer Contract” 又声明所有 status component 的唯一 writer 都是 `status_adv`。R/W matrix 也把 S16-S21 标为写 StatusState。

确定性风险：如果实现保留 S16-S21 写入，同时 S22 再写入，状态推进顺序、duration 递减、冲突裁决都可能因 parallel scheduling 分叉。

要求修正：二选一并统一 R/W matrix。若 `status_adv` 是唯一 writer，则 S16-S21 应降为纯 intent producer/reader 或删除；若 S16-S21 保留 writer，则必须给每个 status subtype 明确不重叠写入与 S22 的前后关系。

### T5 — Medium — 快照截断算法存在三套不同定义

`engine.md` §3.4.4 使用 priority bucket：自机 > 友方 drone > 敌方 drone > 建筑 > NPC > 资源，同桶 stable `entity_id`；`01-tick-protocol.md` §2.3 使用关键桶/高/中/低优先桶，并在同桶按 `(distance_to_drone, entity_id)`；API registry 的 `visibility_truncation_version` 存在但没有绑定具体算法。

确定性风险：snapshot hash、WASM 输入、host query 结果会因实现选择不同桶顺序/距离 tie-breaker 而不同，进而导致 commands_hash 与 replay 分叉。

要求修正：建立单一 “Visibility/Truncation Manifest”，机器可读定义 bucket order、distance metric、multi-drone distance 规则、entity serialization order，并将 hash 写入 TickTrace 的 `visibility_truncation_version/hash`。

### T6 — Medium — RNG contract 不足以覆盖消费顺序和 XOF offset

文档定义了 namespace seed，但没有完整定义每个系统如何消费随机流：例如 combat 伤害浮动、NPC spawn、loot、出口生成、出生房间密度 tie-break 等需要 per-entity/per-event stream key、draw index、拒绝/跳过事件是否消耗 RNG。`engine.md` 还提到 per-entity stream seed，`01-tick-protocol.md` §9.5 表格却只写部分 namespace。

确定性风险：同一系统在并行或过滤条件不同的实现中可能消费不同数量的随机数，导致后续 RNG stream 偏移，出现跨节点分叉。

要求修正：禁止“全局顺序消费 RNG”。每个随机决策应派生独立 stream：`Blake3(domain || world_seed || tick || stable_subject_id || decision_kind || attempt_index)`，并规定未执行/被拒绝事件是否不消耗随机数。RNG manifest hash 应进入 TickTrace。

### T7 — Medium — Bevy pending entity flush 与同 tick 可见性描述冲突

`06-phase2b-system-manifest.md` §3 写“所有新实体追加到 pending_entities，在当前 tick 所有 system 执行完毕后 flush”，但 S08 spawn_system 又写“新 Drone 追加到 pending_entities”，S09 spawning_grace、S11-S15 combat filter 依赖新生 drone 的 `SpawningGrace` 与实体存在。若新 drone 到 tick 末才 flush，S09 无法找到它；若 S08 立即可见，则 §3 描述不准确。

确定性风险：不同实现对 pending entity 可见性的选择会改变出生 tick 是否可被系统处理、RoomCap 消费、combat filter、death_cleanup 结果。

要求修正：明确定义 entity lifecycle：S08 创建的新 drone 是否在 S09/S11 可查询；若需要出生保护，应在 S08 同步创建可查询实体并附带 PendingVisibility，或让 S09 处理 PendingSpawn buffer 而非实体 query。

### T8 — Medium — `COLLECT` 超时/输出大小合同存在数值冲突

`02-command-validation.md` §1.1 顶层 tick 输出总字节数 ≤ 256KB，但 §6 批级校验又写整批 ≤ 1MB；`01-tick-protocol.md` §8.2 写 Output JSON 256KB 超限“截断（保留前 256KB）”，而 §9.7 写超出时整批丢弃，不保留部分解析前缀；`04-wasm-sandbox.md` 也写超过 256KB 拒绝当 tick 所有输出。

确定性风险：截断前缀 vs 整批丢弃会改变 accepted commands；256KB vs 1MB 会改变验证边界。

要求修正：统一为一个上限和一个行为。为避免 partial JSON / prefix parsing 非确定性，建议固定为：CommandIntent JSON > 256KB 或 command count >100 时整批丢弃，记录 canonical rejection/terminal state，不解析前缀。

### T9 — Low — `HashMap/IndexMap` 约束尚未覆盖所有集合

文档明确 Resource/Source 使用 IndexMap，确定性章节禁止 `std::HashMap`。但 Pending buffers、EventLog、ResourceLedger operation aggregation、active_players 集、visible_entities、sub-buffer merge 的底层集合没有统一约束。

确定性风险：实现者可能在内部聚合中使用 HashMap/BTreeMap/Vec 不一致，尤其是 command_hash tie-break 前的 active_players order、ledger checksum、event log serialization。

要求修正：增加 Deterministic Collections Contract：所有进入 checksum、hash、serialization、iteration 的集合必须在输出前按 canonical key 排序；禁止直接序列化 hash-map iteration order。

## State Machine Gaps

- Room 状态机缺少 `reserved → contested`、`contested → neutral/abandoned`、`abandoned → owned/reserved` 等完整转换表；文本描述有路径，但没有每条边的 guard、owner/progress/downgrade_timer 更新规则。
- Deploy 状态机较完整，但 `ACTIVE` 的“drone 获得新 WASM 模块，下一 tick 生效”与 `activation_tick = current_tick + 1` 的精确 COLLECT 边界仍需定义：到达 activation_tick 时是在 COLLECT 前、COLLECT 中还是下一 tick 再执行。
- Tick failure 状态机对 `COLLECT crash`、`Phase 2a panic/OOM`、`FDB commit fail` 的 fuel refund 行为存在差异且部分冲突：表中 Phase 2a panic/OOM “已消耗 fuel 不退”，但 crash recovery/commit rollback 又说 fuel 全额退还。需要统一按 tick 是否 commit 成功定义。
- `status_advance_system` 的内部状态机未完整定义：apply intent 与 duration decrement 的顺序、同 tick 新施加状态是否立即 decrement、expire effect 与新 intent 同时发生时的优先级都需要固定。
- Entity lifecycle 状态机缺少 `pending_create → visible_this_tick? → committed`、`DeathMark → cleanup → despawn` 与 ID reuse 禁止的精确定义。

## Non-Determinism Sources

- 文档冲突本身是最大非确定性源：特殊攻击优先级、TickTrace 原子性、terminal_state、snapshot truncation、WASM output 超限处理都存在多版本定义。
- RNG 消费顺序若依赖系统迭代或并行执行，将导致 stream offset 分叉；需要 per-decision keyed RNG 替代顺序消费。
- Bevy archetype/query order 不可作为实体迭代顺序；manifest 虽声明 stable key，但所有系统、buffer、ledger、event log 都需要 CI 强制验证。
- SIMD 配置存在风险：`04-wasm-sandbox.md` 允许 World 默认 SIMD true、Arena false。虽然 relaxed SIMD 禁用，但普通 SIMD 中涉及浮点或目标架构差异时仍需证明 determinism；若玩家 WASM 可使用浮点 SIMD，跨 CPU/Wasmtime 版本可能影响结果。
- 系统时间仍出现在持久化示例字段：`tick_head(timestamp)`、`uploaded_at`、证书/认证事件时间等必须明确不进入 state_checksum / replay decision，仅作审计 metadata。
- FoundationDB retry 与 WAL/object-store async 上传不会破坏状态确定性，但只有在 replay-critical subset 完全在 FDB 内时成立；否则对象存储缺失会变成 replay 输入缺失。
- Pathfinding cache key 包含 `terrain_hash` 和 `player_visibility_fingerprint` 是正确方向，但 A* tie-break、neighbor order、open-set priority tie-break 必须固定，否则相同 cost 多路径会跨实现不同。
- Canonical serialization 未给出完整字节级规范。`command_hash = Blake3(command_json)` 若 JSON key order/whitespace/number encoding 未 canonicalize，会导致排序 tie-break 分叉。

## CrossCheck — 需要跨方向检查

- CX1: Persistence Contract 与 TickTrace 原子性存在架构级冲突 → 建议 Architect 检查 FDB replay-critical subset 与 object store rich trace 的分层边界，确认哪些字段必须小事务提交、哪些可异步降级。
- CX2: `terminal_state` 双重语义可能影响 API/SDK/运维可观测性 → 建议 Architect 检查 TickTrace Envelope、API Registry、Persistence Contract 的字段命名与版本迁移方案。
- CX3: WASM SIMD / Wasmtime target_arch / compiled_module hash 的跨节点一致性风险 → 建议 Security 检查是否允许 untrusted WASM 使用浮点/SIMD，以及 Wasmtime 编译缓存跨架构是否可被 replay verifier 安全处理。
- CX4: `command_hash = Blake3(command_json)` 的 canonical JSON 未定义 → 建议 Security 检查 JSON canonicalization、日志注入 escaping、debug_detail 截断是否可被玩家构造为排序/审计绕过。
- CX5: world_seed 泄露后的未来 tick 可预测是已接受风险，但排序攻击影响公平性 → 建议 Game Designer 检查 seeded shuffle 可预测窗口是否会损害竞技体验，是否需要赛季/竞技场额外 seed commit-reveal 机制。
