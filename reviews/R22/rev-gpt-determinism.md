# R22 确定性评审 (GPT-5.5)

## Verdict

REQUEST_MAJOR_CHANGES

当前设计已经明显把“确定性”作为一等目标：有固定 tick phase、canonical sort key、Phase 2b manifest hash、整数/定点数策略、IndexMap/StableEntityId、WASM fuel metering、TickTrace envelope、FDB retry 复用 COLLECT buffer 等关键构件。  

但 clean-slate 评审结论是：设计尚未达到可批准状态。主要原因不是缺少确定性意识，而是若干权威文档之间存在互相冲突的 replay / persistence / schedule 合同；此外 RNG stream、canonical serialization、状态机闭合与并行 reducer 的边界仍不够精确定义。若按当前文档分别实现，极可能出现线上 tick 与 replay verifier、不同节点、不同实现者之间的分叉。

---

## Strengths

1. **Tick phase 边界清晰**  
   COLLECT → EXECUTE → BROADCAST 的阶段边界明确，WASM 与 MCP snapshot 被约束为 COLLECT 起始快照，EXECUTE 不暴露中间状态，降低 TOCTOU 与 replay 分叉风险。

2. **Replay-first 设计方向正确**  
   文档明确记录 sorted RawCommand、rejections、metrics、state_checksum、system_manifest_hash、world_config_hash、mods_lock_hash、canonical codec version 等 replay 必需信息，且回放不重跑 WASM，避免 Wasmtime 版本升级破坏旧 tick replay。

3. **RNG 与排序已经有统一方向**  
   使用 Blake3 XOF、domain separation、seeded shuffle、per-entity stream seed 方向正确；比 wall-clock / OS entropy / std::hash 更适合 deterministic simulation。

4. **已识别常见非确定性陷阱**  
   文档显式禁止 f64 状态、要求整数/定点数、避免 std::HashMap 迭代顺序、使用 StableEntityId / IndexMap、禁用 WASI clock/random/filesystem/network，这是非常好的基础。

5. **FDB retry 的 COLLECT 缓存合同是亮点**  
   commit failure 后复用 canonical COLLECT buffer，不重跑 WASM，不重复扣 fuel，并显式记录 collect_id / attempt_id / commit_id。这是 replay 与公平性都需要的关键设计。

6. **Phase 2b manifest 化方向正确**  
   将系统顺序、R/W matrix、manifest_hash 写入 TickTrace，能让 replay verifier 检测“代码调度与文档调度不一致”的问题。

---

## Concerns

### T1 — Critical — TickTrace 原子性与 Persistence async blob 合同互相冲突

`01-tick-protocol.md` 明确要求 TickTrace 与状态写入同一 FDB 事务，且禁止“状态成功但审计不完整”；还声明 TickTrace 写入失败会导致 tick 回滚，不存在 tick 成功但 replay 数据丢失。  

但 `05-persistence-contract.md` 又定义：FDB commit 先完成，TickTrace blob 异步写对象存储；blob 失败时 `upload_status=failed`，world state 完整但 replay 不可用，并可标记 `audit_gap` / `unreplayable`。  

这两个合同不能同时成立：

- 若 TickTrace 完整内容不在 FDB 事务内，则“同事务无审计缺口”不成立。
- 若对象存储失败允许 tick 成功，则 replay 完整性不是闭包。
- 若 replay verifier 依赖 object blob，而 blob 可失败，则 `tick(seed, state, commands) -> new_state` 的审计输入不再总是可恢复。

建议：必须选择一个权威模型：

- **严格 replay 模型**：TickTrace replay-critical subset（commands、rejections、state_checksum、manifest hashes、fuel ledger、terminal_state、canonical codec id）必须在 FDB 小事务内原子提交；object store 只放大体积 debug/trace blob。
- **异步审计模型**：明确承认 replay completeness 不是每 tick 强保证，并将 Verdict 降级为“state deterministic but audit best-effort”，同时修改所有声称“无 audit gap”的章节。

当前文档同时声称两者，必须 major change。

### T2 — High — RNG stream 合同仍不够可实现，且存在未注册 host RNG

文档多处声明“所有随机数来自确定种子 PRNG”，并在 §9.5 说 WASM 必须使用 `swarm_get_random(sequence)` 从 host 获取确定性随机数。  

问题：

- `api-registry.md` Host Functions 只注册了 5 个 host function，没有 `swarm_get_random` / `host_get_random`。
- RNG namespace 表只列 `combat/loot/npc_spawn/event` 的 seed 来源，但没有定义 stream offset、draw index、每个系统消耗次数、并行系统如何分配 RNG 子流。
- `combat` 与 `event` 使用 `world_seed + tick`，若同一 tick 内多个 entity/command 都从同一 namespace 抽样，必须定义 `entity_id`、`command_hash`、`target_id` 或 sorted intent index，否则执行顺序或并行 partition 会影响抽样结果。
- `per-entity stream seed` 在 engine.md 中出现，但 01 中的 namespace 表未完全采用，存在合同分叉。

建议：新增 RNG Contract 表：`domain, seed_material, stream_id, draw_index rule, consumer system, replay field`。所有 RNG consumer 必须使用 `(domain_sep, world_seed_epoch, tick, stable_subject_id, stable_event_id)` 派生独立子流，禁止共享 mutable RNGState 依赖调用顺序。

### T3 — High — Canonical serialization / command_hash 未闭合

全局排序依赖 `command_hash = Blake3(command_json)`，TickTrace 也记录 `commands_hash`、`canonical_codec_version`。但文档未定义 canonical JSON / binary codec：

- JSON object key order 是否排序？
- number 是否允许不同 textual representation？
- string escaping 是否规范化？
- RawCommand 中 debug_detail、auth context、source injected fields 是否进入 hash？
- `command_hash` 是对 CommandIntent、RawCommand 还是 ValidatedCommand hash？
- 不同 SDK / gateway / replay verifier 是否必须使用同一个 canonical binary form？

若实现者直接 hash 原始 JSON bytes，等价命令可因字段顺序或 whitespace 产生不同排序。若 hash 语义对象，又需要规范化编码。  

建议：禁止以非规范 JSON bytes 作为排序 hash。定义 `CanonicalCommandV1` 二进制编码或 RFC8785 JSON Canonicalization，并明确 hash 输入字段集合。

### T4 — High — Phase 2b special attack / status schedule 存在内部矛盾

`06-phase2b-system-manifest.md` 声称：

- S14 `special_attack_reducer` 只归并、排序、路由，不直接修改实体状态。
- 但 S14 R/W 表写 `StatusState (seeded)`。
- S16-S22 为 parallel set，S16-S21 各写不同 StatusState subtype，S22 `status_advance_system` 又写所有 StatusState 并应用 S14 intents。
- 并行安全证明声称 S22 与其他 status system 无冲突，但表中 S16-S22 都写 `StatusState`，除非 subtype 拆成不同 component，否则存在共享写入。
- `02-command-validation.md` §3.19 又给出旧顺序：`death_mark → spawn → spawning_grace → combat → status_advance → (regeneration, decay 并行) → death_cleanup`，与 manifest 的 S10 regeneration before combat / S14 / S15 / S16-S22 不一致。

结果是：同一特殊攻击在 replay 中到底由 Phase 2a inline apply、S14 reducer、S16-S21 subtype system，还是 S22 统一应用，并不唯一。  

建议：

- 将特殊攻击命令在 Phase 2a 中统一转成 `PendingSpecialIntent`，不在 combat S11-S13 中产生。
- S14 只做 canonical sort，不写 StatusState。
- S22 串行、唯一地应用 sorted intents 与 duration advance。
- S16-S21 若保留并行，只能读取已提交状态并产生 disjoint outputs，不能与 S22 同 tick 写同一 subtype。
- 删除或修正 `02-command-validation.md` §3.19 的旧调度描述。

### T5 — High — Room / Controller 状态机未完全闭合

Room 状态机列出 `neutral/reserved/owned/contested/abandoned`，但 transition guard 和冲突解决仍不完整：

- `contested` 只描述“两玩家同时 Claim”，未定义三方以上 Claim、同 tick 多 Claim、不同 body part 权重、tie break、progress 初始值与归零规则。
- `reserved` 超时回 `neutral`，但 timeout decrement 是哪个 system 处理、何时相对 Claim/Upgrade 执行未写入 Phase 2b manifest。
- `abandoned` 到 `owned/neutral` 的精确路径不清晰，RCL>1 降级后是否回 owned、abandoned 继续倒计时，还是保持 abandoned 状态不明。
- `owner 失去` 的来源（主动放弃、玩家删除、Hack、资源耗尽、controller downgrade）未与 command/source model 绑定。

建议：将 Room/Controller 状态机改成完整 transition table：`from_state, event, guard, deterministic ordering, action, to_state, system_id`，并把 timeout/downgrade/claim conflict 纳入 manifest。

### T6 — Medium — Snapshot truncation 规则跨文件不一致，且多 drone 距离定义不明

`engine.md` 的 bucket 顺序是“自机 > 友方 drone > 敌方 drone > 建筑 > NPC > 资源”，同 bucket stable `entity_id`。  

`01-tick-protocol.md` 的 bucket 顺序是“关键桶 Spawn/Controller/depot/storage > 己方 drone/建筑按距离 > 敌方/资源点按距离 > 友方/中立”，同桶 `(distance_to_drone, entity_id)`。  

问题：

- 两个文档优先级不同，可能导致同一状态下截断结果不同。
- `distance_to_drone` 对拥有多个 drone 的玩家不唯一：取 min distance、按每个 drone 分别生成 snapshot、还是按 player centroid？
- `serialized_size` 本身依赖 canonical serialization；若编码未定义，截断边界也不稳定。

建议：指定唯一权威 truncation algorithm，包含 exact bucket order、distance function、multi-drone aggregation、tie-break key、canonical encoded byte length。

### T7 — Medium — Active player set / seeded shuffle 的输入快照未完整定义

排序属性依赖“相同玩家集 + 相同 seed → 相同顺序”。但 active player set 的采样点和排序前 canonical list 未完全定义：

- active_players 是 COLLECT 开始时、有 WASM 模块且至少 1 drone，还是 EXECUTE 前经过 death/spawn 后？
- 新部署、新玩家加入、全灭、safe_mode、degraded mode skip 是否仍进入 shuffle？
- `ERR_CPU_SATURATED` / NotExecuted 玩家是否占 shuffle slot？
- active player canonical ordering 是否按 `PlayerId` 升序后 Fisher-Yates？

建议：TickTrace 记录 `active_player_set_hash` 与 canonical ordered player list hash；shuffle 输入必须是 COLLECT boundary 的 stable player list。

### T8 — Medium — Sandbox SIMD / floating-point 内部计算边界需要更强声明

文档要求状态与公式禁止 f64，但 WASM sandbox 中 World 默认 `simd_enabled=true`，且恶意样本包含 NaN boxing。即使世界状态不用 f64，玩家 WASM 内部可使用 float/SIMD 来决定输出 command。不同 target_arch、compiler、SIMD lowering、NaN canonicalization 可能导致玩家代码在不同节点输出不同 command。  

如果 Swarm 只在单 engine authoritative node 执行 WASM、replay 不重跑 WASM，则这不是 replay 分叉；但如果未来跨节点或 verifier 重跑 COLLECT，则会变成非确定性源。  

建议：明确合同：authoritative replay 不重跑 WASM，因此 WASM internal FP 不属于 replay deterministic core；若要跨节点 duplicate COLLECT，则必须固定 target_arch、Wasmtime build、SIMD setting，并禁用或规范 NaN/relaxed SIMD。

### T9 — Medium — System time 字段需明确排除 state/replay hash

Persistence 中 `tick_head(timestamp)`、manifest `uploaded_at`、auth token `iat/exp`、cert issue/expiry、audit log 时间等字段涉及 wall-clock。文档禁止 WASI clock，但 engine 自身仍会记录时间。  

建议明确：

- wall-clock 字段不得进入 `state_checksum`、command ordering、RNG seed、world simulation state。
- 若进入 audit hash chain，必须作为 non-simulation metadata，不参与 `execute_deterministic(state, commands)` comparison。
- `tick_number` 是 simulation time 的唯一权威时间。

### T10 — Low — 数值/限制表存在多处不一致，容易诱发实现分叉

示例：

- `api-registry.md` 说 MCP tools 共 54 active，changelog 又说 56 active。
- `02-command-validation.md` 顶层输出 ≤256KB，但批级校验又说整批 ≤1MB。
- `api-registry.md` 全局 drone cap 为 10,000、per-player drone cap 500；`02-command-validation.md` 末尾又有 MAX_DRONES_PER_PLAYER 50。
- WASM module size 在 sandbox 为 5MB，api registry blob type 为 64MB。
- Recycle refund 在不同位置出现固定 50%、lifespan 10–50%、tutorial 100% 三套规则。

这些不一定都是 determinism bug，但会让不同实现者选择不同“权威值”，最终导致 replay 与线上分叉。

---

## State Machine Gaps

1. **Room/Controller 状态机缺 transition table**  
   需要穷举 `neutral/reserved/owned/contested/abandoned` 的全部 event、guard、action、to_state，并绑定执行 system。

2. **Tick failure 状态机存在双模型**  
   `TickTrace write fail = tick rollback` 与 `blob upload failed = tick success but replay gap` 必须拆分 replay-critical trace 与 debug blob，否则 tick 成功/失败状态机不闭合。

3. **Deploy 状态机不完整**  
   `validate/upload/commit/activate` 中 async upload 与 activation 的关系不闭合：如果 FDB manifest committed 但 blob upload failed，下一 tick 是否可激活？若不能，terminal_state 是 NotExecuted、deploy rejected，还是 rollback deploy event？

4. **Special attack 状态机需要单一 writer**  
   Hack/Drain/Overload/Debilitate/Disrupt/Fortify 的 apply、advance、expire、cleanse、interrupt 当前分散在 Phase 2a、S14、S16-S22、S22 描述之间，需要归一到一条 canonical transition path。

5. **Refund / fuel credit 状态机需要事件排序**  
   refund credit、deploy-reset、same-session exception、tick abandon fuel refund、resource refund 是多个 ledger。需要定义同 tick 多事件排序与 checksum 归属。

6. **Degraded mode 状态机未纳入 replay contract**  
   degraded mode 暂停 deploy / skip WASM / join_lock 会改变 active player set 与 command set，应作为 TickTrace replay-critical input，而不只是运维状态。

---

## Non-Determinism Sources

1. **Object-store async TickTrace blob**  
   blob upload success/failure 会决定 replay 是否完整，但不影响 FDB state，形成 audit nondeterminism 与 replay gap。

2. **未定义 canonical serialization**  
   command_hash、commands_hash、snapshot_hash、state_checksum、truncation size 都依赖 canonical encoding；未定义会导致实现分叉。

3. **共享或顺序依赖 RNG stream**  
   RNG namespace 没有 draw index / stream id 完整规则，parallel systems 若共享 RNGState 会受执行顺序影响。

4. **Bevy / ECS iteration order**  
   manifest 要求 StableEntityId，但需要 CI 强制所有 query 都排序；任何遗漏都会把 archetype order 引入结果。

5. **HashMap / unordered collections**  
   文档已要求 IndexMap，但 RuleMod、SDK、ResourceRegistry、WorldConfig、ActionManifest 若允许普通 map 序列化，仍可能污染 hash 与 iteration。

6. **System time / timestamps**  
   tick_head timestamp、uploaded_at、auth iat/exp 若进入 simulation hash，会引入 wall-clock nondeterminism。

7. **WASM internal FP / SIMD**  
   若未来跨节点重跑 WASM COLLECT，float/SIMD/NaN 行为可能影响 command output；当前只在 authoritative node 执行且 replay 不重跑 WASM时可接受，但需明确边界。

8. **Pathfinding cache 与 budget**  
   `host_path_find` 有 cache_miss_penalty、fair-share budget、先到先得消耗；必须定义 cache key、cache population timing、miss/hit 是否 replay-critical，否则 cache 状态会影响 fuel 与结果。

9. **Parallel reducer merge order**  
   PendingDamage / PendingSpecialIntent / ResourceLedger delta 若来自并行系统，必须先 canonical sort 再 reduce；任何 append order 都不可接受。

10. **Dynamic RuleMod / custom actions**  
   RuleMod 若能注册 action/schema/status handler，必须禁止第二条状态修改路径，并将 action manifest hash、handler version、deterministic iteration rules 纳入 replay-critical envelope。

---

## CrossCheck — 需要跨方向检查

- CX1: Persistence 与 replay-critical TickTrace 的权威模型冲突 → 建议 Architect 检查是否采用“FDB 内 replay-critical subset + object store debug blob”的分层方案。
- CX2: async object store upload 后 deploy activation 的失败语义不闭合 → 建议 Architect / Reliability 检查 FDB manifest committed 但 blob missing 时下一 tick 如何处理。
- CX3: Special attack schedule 在 manifest 与 command-validation 中冲突 → 建议 Gameplay / Architect 检查特殊攻击到底是 Phase 2a intent、Phase 2b reducer，还是 status system 单一 writer。
- CX4: sandbox SIMD/FP 边界影响跨节点 verifier → 建议 Security / Runtime 检查是否需要禁用 SIMD 或声明 replay 永不重跑 WASM COLLECT。
- CX5: 文档权威源声明过多且互相重述限制数值 → 建议 Documentation / Architect 检查 api-registry、tick-protocol、command-validation、sandbox 的 single source of truth。

---

## Required Fixes Before Approval

1. 统一 TickTrace / Persistence 合同，消除“同事务无 audit gap”与“async blob failed but tick success”的矛盾。
2. 定义 canonical serialization，并使 command_hash / commands_hash / snapshot_hash / state_checksum 使用同一 codec version。
3. 完成 RNG stream contract：每个 consumer 的 domain、seed material、subject id、draw index、parallel behavior 必须固定。
4. 修正 Phase 2b manifest 与 command-validation 的调度冲突，尤其是 special_attack_reducer/status_advance 的写入权责。
5. 将 Room/Controller、Deploy、Degraded、Refund 状态机补成 transition table。
6. 统一 snapshot truncation、limits、Recycle refund、module size 等跨文档冲突值。
