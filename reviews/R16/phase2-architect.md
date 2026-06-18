# R16 Phase 2 CrossCheck — Architect 补充验证

范围：只做 Phase 2 补充阅读，不重跑完整评审。输入来自 R16 Phase 1 的 CrossCheck 段落及 Architect 相关来源：`rev-gpt-architect`、`rev-dsv4-architect`、`rev-gpt-determinism`、`rev-dsv4-determinism`、`rev-gpt-apidx`、`rev-dsv4-apidx`、`rev-gpt-performance`、`rev-dsv4-performance`，并补读少量 Designer/Security CrossCheck 中指向 Architect 的条目。

注：当前工作树中 `/data/swarm/docs/reviews/R16` 曾被清理；本次从 docs repo commit `8c02b92` 恢复 Phase 1 输入到任务 workspace 后完成核查，并将本文件写回目标路径。

## CrossCheck item -> Finding -> disposition

### 1. API Registry / `game_api.idl` / 派生文档的权威层级

Finding: **权威层级方向正确，但仍不可落地；应定为 high。** 多个评审独立指出同一模式：`api-registry.md` 口头声明自己是 CommandAction、RejectionReason、MCP tools、Host Functions、容量限制的唯一权威，但 `commands.md`、`02-command-validation.md`、`host-functions.md`、`design/interface.md`、`mcp-tools.md` 仍保留可被实现者直接复制的旧表格/旧签名/旧工具名。API-DX 还指出 `game_api.idl` 若作为机器事实源，则 registry 不应再自称上游权威，而应是 generated registry view；反之，若 registry 是事实源，则 IDL/codegen/Markdown/Rust enum/SDK schema 都必须从 registry 生成。

典型冲突包括：
- Core CommandAction 数量/结构冲突：registry 为 11 core + 2 global + 6 special，Leech/Fabricate 为 custom；派生文档仍把 Leech/Fabricate 混入 enum/special_effect。
- RejectionReason 冲突：validation/commands 使用 `NotMovable`、`Fatigued`、`MissingBodyPart`、`TileBlocked`、`StillSpawning`、`TargetFull` 等未注册外部 code。
- Host ABI 冲突：registry 的 `host_get_terrain(room_id, out_ptr, out_len)`、`host_path_find(... opts_ptr/opts_len ...)` 与 host-functions reference 的旧签名不一致；预算错误码 `-4` vs `-1` 也冲突。
- MCP tool 冲突：`swarm_profile` vs `swarm_get_sandbox_profile`、`swarm_dry_run_commands` vs `swarm_dry_run`、`swarm_explain_last_tick` vs `swarm_get_tick_trace`、`swarm_list_modules` vs `swarm_list_deployments`。
- 版本/容量字段冲突：`api_version` semver string vs TickTrace `u32`；tick output/snapshot/command batch 256KB 与 1MB 表述混用。

Architect disposition: **high**。这不是单纯文档瑕疵，而是会直接导致 SDK codegen、WASM ABI binding、MCP schema、replay envelope、错误处理各自生成不同合同。落地条件应是：明确 `game_api.idl` 与 registry 的父子关系；只允许一个机器事实源；所有派生文档标注 Non-authoritative 或自动生成；CI 扫描派生文档中的 enum/tool/error/host ABI 字面量，未注册即失败。

### 2. Phase 2a / Phase 2b 与 `06-phase2b-system-manifest` 是否应合并为完整 Tick Execution Manifest

Finding: **应合并/升级为完整 Tick Execution Manifest；当前 Phase 2b-only manifest 已不足以承载真实调度。** Architect 与 Determinism/Performance 来源一致：`engine.md` 描述 Phase 2a inline apply 玩家命令、Phase 2b 处理被动系统；但 `06-phase2b-system-manifest.md` 又把 `command_executor`、`spawn_system`、`build_system`、`recycle_system`、`transfer_system`、attack/ranged/heal parallel set 纳入 Phase 2b。两个文档不是“粒度不同”，而是在实现拓扑上互斥。

关键冲突：
- `engine.md` 20-system flat `.chain()` 与 manifest 27-system serial spine + 3 parallel sets 不同。
- Move/Attack/Harvest/Transfer 是 Phase 2a 即时修改 Bevy World，还是在 manifest 的 command_executor / parallel combat set 中执行，不清楚。
- Attack/RangedAttack/Heal 在 engine 中属于 Phase 2a command apply；manifest 中又有 S07-S10 pending damage reducer。
- manifest 缺失 engine chain 中的 Rhai rule tick start/end、seed rotation、cargo/global storage、controller/depot repair、memory upkeep、drone env var、onboarding 等系统，且未声明这些是否 outside scope。
- Component R/W matrix 仅覆盖少量组件，无法验证 manifest 中 30+ component/resource 的并行安全。

Architect disposition: **blocker**。如果只把 `06-phase2b-system-manifest` 修补为“Phase 2b 被动系统清单”，仍然无法回答 command handlers 与 passive systems 的唯一交界。建议改为机器可读 `Tick Execution Manifest`：按 SNAPSHOT/COLLECT/Phase2a command reducer/Phase2b passive systems/COMMIT/BROADCAST 定义完整顺序、parallel set、R/W 集、稳定迭代键、tie-breaker、authority scope。旧 `engine.md` 代码块应降级为解释性伪代码或从 manifest 生成。

### 3. spawn / death_mark / RoomCap / spawning_grace / pvp_block / regeneration / combat 的唯一调度

Finding: **当前没有唯一调度；并且至少有一个具体 correctness bug。** DeepSeek Architect 给出的 C2 很关键：manifest 中 S03 spawn 创建 drone，而 S07-S10 combat/damage/death_marker 在前，S22 才运行 `spawning_grace_system`，这会允许新生 drone 在 birth tick 被攻击、标记死亡并在 S23 cleanup 中删除，违反 engine.md “本 tick 内免疫所有伤害”的设计合同。

调度冲突逐项判断：
- `death_mark` / `spawn` / `RoomCap`：engine 约束为 death_mark release → spawn check/consume，且中间系统不得读 RoomCap；manifest 将 spawn 放在 death_marker 前，且 R/W 声明未把 RoomCap 纳入系统读写，改变了 room cap 生命周期。
- `spawning_grace`：应在 spawn 后、任何 combat/damage 前建立；manifest 放在 combat/death 后，破坏 birth-kill prevention。
- `pvp_block`：engine 放在 death_mark 与 spawn 间；manifest 放在 death_cleanup 后。后者可能更安全，但二者语义不同，必须择一。
- `regeneration` / `combat`：engine regeneration 在 combat 前，manifest regeneration 在 combat/aging 后；这决定本 tick regen 是否可吸收本 tick damage，属于玩法/经济可见差异。
- special status reducer：Disrupt/Fortify/Hack/Overload/Debilitate/Drain 与 `status_advance` 在 manifest parallel set B 中，但 Determinism 要求同 target multi-status reducer 必须有 canonical order，不能靠并行系统隐含解决。
- custom actions：Leech/Fabricate 作为 World Action Manifest/custom handler 时，其执行时序和并行安全尚未进入 system manifest。

Architect disposition: **blocker**。这会直接制造不同 engine 实现和 replay 分叉。最低修复要求：选择唯一顺序并写入完整 Tick Execution Manifest；`RoomCap`、`SpawningGrace`、`PvpBlock`、`PendingDamage`、`StatusIntent` 等全部进入 R/W matrix；为同 target 多状态、多 damage、spawn density、contested room/controller 等定义 canonical reducer/tie-breaker。就当前资料看，`spawning_grace` 必须移动到 spawn 之后、combat 之前；`regeneration` 的前/后 combat 语义需由 Gameplay/Economy 裁决后冻结。

### 4. Persistence retry 是否复用 COLLECT canonical buffer

Finding: **应复用 COLLECT canonical buffer；`05-persistence-contract.md` 中“重跑 COLLECT”叙述必须删除或改写。** GPT Architect、GPT Determinism、GPT Performance 均指向同一结论：`01-tick-protocol.md` 要求 FDB commit 失败时不重新执行 WASM，复用首次 COLLECT 的命令列表、fuel ledger、snapshot_hash/commands_hash；但 `05-persistence-contract.md` §6 写 commit 失败后重新执行 tick N（重跑 COLLECT → apply），甚至承认 TickTrace 可能因时间流逝不同。

Architect 判断：对 deterministic MMO 来说，commit retry 是持久化重试，不是 simulation retry。若在同一 tick_number 下重跑 COLLECT，会带来：
- fuel 可能重复扣/重复 refund，或玩家可因 FDB 抖动获得额外执行机会；
- WASM timeout、host-call budget、path cache state、snapshot truncation、MCP query 结果可能变化；
- TickTrace hash、state_checksum、audit replay 与玩家可见行为分叉；
- 真实时间进入 authoritative trace 的风险。

应建立一等概念：`tick_number`、`attempt_id`、`collect_id`、`commit_attempt_id`。同一 simulation attempt 的 FDB/object-store retry 必须复用 canonical COLLECT buffer，包括 snapshot hash、validated commands、wasm_status、fuel ledger、player order、rejection list、host-call outputs/limits。只有 tick 被明确放弃并进入新的 simulation attempt 时，才允许重新 COLLECT，且必须产生新的 attempt id，不能伪装成同一 authoritative trace。

Architect disposition: **blocker**。这是 replay/fairness/persistence 的核心合同，不统一不能实现。

### 5. Capacity manifest 与 worker pool / admission 是否是架构约束

Finding: **是架构约束，不是运维后补；当前缺少可执行 capacity manifest。** Performance 两份评审都指出：target 500 active players / hard 1000 players 与 `pool_size = active_players`、per-player 2500ms deadline、128MB worker cgroup、500/1000 并发 Wasmtime 实例绑定后，会形成明显资源悬崖。500 players 仅 worker memory 上限就是 64GB；1000 players 约 128GB；若所有玩家可消耗 2500ms CPU，500 players 约需 42+ fully utilized cores，1000 players 约需 84+ cores，还未计入 engine/FDB/network。

这与架构直接相关，因为 Tick 合同当前依赖“所有玩家完全并行执行”来让 COLLECT ≤2500ms 成立。一旦引入合理的 `max_pool = f(cpu cores, memory)`，per-player 2500ms 就会侵蚀全局 COLLECT 预算，排队玩家可能被 soft deadline 清空为 0 command。Admission、worker pool、budget degradation 因而必须是 manifest 化合同，而不是部署时再调参。

Architect disposition: **high**。应新增或扩展 capacity manifest，至少包含：
- target/hard cap 对应硬件基线：CPU cores、memory、NUMA、FDB/object store/NATS baseline；
- `min_pool` / `max_pool` / queue policy / fairness policy / worker recycle/prewarm；
- per-player deadline 与 global COLLECT budget 的关系：固定 2500ms 只在 full parallelism 成立时可用，否则应按 remaining_budget/queued_players 或 time-slice 调整；
- admission control：active player cap、world degradation、Arena 300ms 的更低 cap 或独立 benchmark contract；
- capacity-related constants 从 Limits/Capacity Manifest 引用，并进入 CI benchmark/soak test。

若不做，设计会在纸面上满足 3s tick，实际部署时靠无限 worker 并发维持 SLA，这是典型“看起来没问题但会炸”的 MMO sandbox 模式。

## Phase Ordering

1. 先裁定事实源层级：`game_api.idl` vs `api-registry` 谁是机器源；另一方必须 generated/read-only。
2. 将 `06-phase2b-system-manifest` 升级/合并为完整 `Tick Execution Manifest`，覆盖 Phase 2a command handlers 与 Phase 2b passive systems，而不是只列被动系统。
3. 在 manifest 中冻结唯一调度：spawn/death_mark/RoomCap/spawning_grace/pvp_block/regeneration/combat/status reducer/custom action handler，并补齐 R/W matrix 与 canonical tie-breaker。
4. 统一 persistence retry：commit/object-store/FDB retry 复用 COLLECT canonical buffer；引入 attempt/collect/commit id；删除“同 tick 重跑 COLLECT”叙述。
5. 引入 Capacity Manifest：把 worker pool、admission、tick budget、hardware baseline、benchmark gates 作为架构输入，而非运维附录。
6. 最后再做文档清理与 CI：删除手写派生表格，从机器源生成 Markdown/Rust/SDK/MCP schema，并加入 cross-doc literal scanner 与 replay/throughput benchmarks。
