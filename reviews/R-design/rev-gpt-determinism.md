# R-design Clean-Slate Review — Determinism Reviewer (GPT-5.5)

Verdict: REQUEST_MAJOR_CHANGES

从「确定性核心」视角看，Swarm 的设计方向是对的：ECS、deferred command、TickTrace、固定 PRNG、整数/定点数、IndexMap、WASM fuel metering、MCP 不直接执行游戏动作，这些都是成功的架构基石。但当前 7 份设计文档还没有形成一个可实现、可审计、可跨机器复现的 Determinism Contract。主要问题不是“难实现”，而是多处合同相互矛盾或缺关键边界：tick 输入封套、WASM 非确定性隔离、Rhai action 排序、snapshot 截断、部署生效 tick、随机种子历史、FDB 事务边界、Pathfinding tie-break 等都还没有被统一为一个规范。

因此我建议在进入实现前做一次 deterministic spec freeze：把所有会影响 `state_checksum` 的输入、顺序、序列化、错误处理、缓存边界和版本边界都明确下来。否则这个架构会出现典型的“单机 demo 确定、生产 replay 偶发不一致”的失败模式。

## Strengths

1. 世界只认 WASM，MCP 不暴露 `swarm_move` / `swarm_attack` 等游戏动作，这是非常正确的公平性和确定性边界。AI 与人类同路径，避免了双执行器导致的不可比较行为。
2. Deferred Command Model 是正确抽象：WASM 只产生命令，引擎统一排序、校验、执行。这个模式比即时 host mutation 更容易 replay、审计和反作弊。
3. 文档已经意识到确定性基础设施：固定 PRNG、固定 hash、禁用 `std::HashMap` 迭代顺序、定点数、TickTrace、world_config/mods_lock 快照、state_checksum，这些方向都合理。
4. Tick 生命周期将 COLLECT 与 EXECUTE 分离，玩家代码在 tick 开始快照上运行，执行阶段使用当前 Bevy World 校验，这是编程 RTS 中常见且成功的确定性模式。
5. `mods.lock`、`world_config`、module hash、Wasmtime pinned version 被纳入 replay 思路，说明设计没有把“规则版本”当成旁路状态。
6. Rhai 模组的 AST 节点预算和事务性 rollback 概念很好，避免把墙钟耗时纳入状态决定。
7. 用途隔离证书和 deploy version_counter 思路降低了部署重放/乱序对世界状态的影响，这是认证域对确定性域的正向支持。

## Concerns

### A1 — Critical — Tick 输入封套未冻结，无法保证 replay 的唯一输入集

当前文档说 replay 给定 `tick N-1 状态 + tick N RawCommand + world_seed + world_config + mods_lock` 可复现，但没有定义 `tick N RawCommand` 的完整封套。至少缺少：

- 每个 active player 在该 tick 的 module_hash / module_version / code effective tick。
- 每个 player 的 WASM 执行结果状态：正常、fuel exhausted、timeout、trap、invalid output、snapshot too large、host function error。
- 玩家未提交命令时是 empty command、timeout rejection，还是该 tick 不参与。
- command 内部 `cmd_seq` 的 canonical 来源、重复/缺失/溢出处理。
- 并行 COLLECT 完成时间不应影响 tick 输入集合，但截止点、迟到结果、sandbox crash 的判定规则未冻结。
- deploy / rollback 在 tick 边界的生效规则未冻结。

风险：生产中最容易出现“某次 replay 缺一个 rejected command / timeout marker / old module hash”，导致 state_checksum 不一致，但事后无法知道是执行器、网关、部署、还是 tick 调度造成。

Recommendation:
定义 `TickInputEnvelope`，每 tick 持久化：

```text
TickInputEnvelope {
  tick_number,
  world_config_hash,
  mods_lock_hash,
  engine_abi_version,
  wasmtime_version,
  prng_epoch_id,
  active_players: [
    { player_id, module_hash, module_effective_tick, snapshot_hash, wasm_status, fuel_used, commands_hash, rejection_pre_execute }
  ],
  raw_commands: canonical ordered list,
  deploy_events: canonical ordered list,
  admin_events: canonical ordered list,
}
```

只有这个 envelope 加 `state_before` 才是 replay 的真正输入。

### A2 — Critical — WASM 非确定性边界没有被完整关死

设计选择 Wasmtime + WASI，但文档没有明确玩家 WASM 可导入哪些函数、是否允许 WASI clock/random/filesystem/env、是否允许 threads/atomics/SIMD、是否允许浮点影响 command 输出。引擎世界状态只由 RawCommand 决定，这降低了风险；但如果 replay 或调试需要重跑 WASM 生成 commands，或者在线 tick 与验证 tick 在不同机器运行，非确定性导入会直接造成 command 差异。

常见炸点：

- WASI `random_get`、clock、filesystem、env var、network 任一开放都会让同一 snapshot 输出不同 commands。
- 多语言 runtime 可能依赖 wall clock、random seed、hash seed、locale、timezone。
- 浮点在玩家内部用于决策时，跨架构/优化版本可能产生边界差异。
- Wasmtime fuel metering 与 host function cost 合同不清，host path_find 不计入指令预算但计入 fuel，具体如何计入未规范。

Recommendation:
创建 `WasmDeterminismProfile`：

- 默认无 WASI；只允许白名单只读 host functions。
- 禁止 clock/random/filesystem/network/process/env，或提供 deterministic stubs。
- 禁止 threads/atomics；SIMD 是否允许需固定 Wasmtime target features。
- replay 官方语义应以 recorded RawCommand 为准；若提供 “re-execute WASM replay”，必须标注为 diagnostic，不作为权威。
- host function cost、错误码、buffer 边界、排序和 tie-break 全部进入 ABI spec。

### A3 — High — PRNG seed 轮换与可回放/不可预测目标存在冲突

文档同时要求：

- `world_seed = Blake3(32随机字节)`，不可从 tick_number 推导。
- 每 10,000 tick 自动轮换 `Blake3(旧种子, 当前tick)`，防止长期观察推断。
- replay 需要 `world_seed`。
- 玩家顺序洗牌和世界事件由 `world_seed + tick_number` 决定。

这里缺少 seed epoch 的持久化和披露模型。若 replay 需要历史 seed，但 seed 又用于未来不可预测性，不能简单公开当前 seed；若只存当前 seed，历史 replay 可能无法重现旧 tick；若 seed 轮换事件没有进入 TickTrace，长期审计会断链。

Recommendation:
引入 `PrngEpoch`：

```text
PrngEpoch { epoch_id, start_tick, end_tick, seed_commitment, encrypted_seed_or_reveal_policy }
```

- 每 tick 的 `prng_epoch_id` 和 `prng_offset` 写入 TickTrace。
- 旧 epoch 在安全窗口后可 reveal，用于公开 replay。
- 未来 epoch 只公开 commitment，不公开 seed。
- 所有 PRNG 调用都必须有命名 stream：`shuffle`, `room_gen`, `npc_event`, `personality`, `drop_table`，避免不同系统插入随机调用改变后续序列。

### A4 — High — FDB 单 tick 原子提交与性能/大小预算互相矛盾

文档同时说每 tick FDB 原子提交、FDB transaction size 16MB、Tier1 total drones/entities 50,000 hard cap、snapshot total 128MB、每 K=100 tick 写 keyframe，其余写 delta。这里缺少确定性提交边界：如果一个 tick 的 delta、rejections、metrics、TickTrace、state write 超过 16MB，是拒绝 tick、分块提交、还是降级写入？分块提交若没有 canonical chunk order 和 two-phase commit，会破坏“全或无”的 replay 语义。

Recommendation:
冻结 `TickCommitProtocol`：

- 先构建 deterministic `TickDelta`，计算 size。
- 若超过 hard limit，tick 必须 deterministically fail-safe：例如拒绝新 spawn / drop non-authoritative metrics / 进入 maintenance，不得部分提交世界状态。
- 如果需要 chunking，使用 `tick_commit/{N}/prepare/chunk_i` + `commit_marker`；recovery 只认完整 marker。
- TickTrace、state delta、metrics 哪些是权威、哪些可丢弃必须分类。

### A5 — High — Rhai 模组 action 排序、可见性与 rollback 语义不足

Rhai 模组是确定性风险集中点。文档说模组可信、AST 预算确定、超限 rollback，但缺少：

- 多个模组的执行顺序：按 mods.lock 顺序、dependency topological order、还是 world.toml 顺序？冲突如何处理？
- 同一模组发出多个 `actions.*` 的 canonical apply order。
- action 与 ECS 主线系统的相对顺序，尤其是 `.after(death_cleanup_system)` 的 mod 是否影响下一 tick 还是当前 tick。
- `state.players()` / `player.rooms()` 的迭代顺序是否固定。
- “模组不能看到隐藏实体”与全局经济/世界事件模组需求冲突；如果过滤依赖 observer，结果可能随可见性规则变化而改变。
- rollback 是否包括 emitted events、logs、metrics、resource deductions、damage side effects。

Recommendation:
定义 `RuleModDeterminismSpec`：mod order = dependency topo sort + name tie-break + locked rev；state iterator order = sorted by stable id；actions 先收集为 action log，按 `(mod_order, action_seq, target_id)` apply；超限则丢弃该 mod action log 全部内容，包括 events 和 metrics。

### A6 — High — “禁浮点/定点数”合同与文档示例冲突

Determinism Contract 说游戏引擎数值用整数 + 定点数，Rhai 禁浮点。但多处 world.toml 示例使用 `0.01`、`0.05`、`0.001`、`special_param = 0.5`、`default_resistance = 1.0`、`damage_multiplier` 之外也有 float 风格字段。若实现者照文档做 TOML float，就会引入解析、舍入、序列化和跨语言 SDK 不一致。

Recommendation:
所有配置示例改为显式定点格式，禁止 TOML float：

```toml
transfer_to_global_cost = { Energy = { num = 1, denom = 100 } }
special_param = { fixed_u32_4 = 5000 }   # 0.5000
resistance = { fixed_u32_4 = 10000 }     # 1.0000
```

并给出 canonical parser：拒绝 float token，而不是“读入后转换”。

### A7 — Medium — Map / JSON / schema 的 canonical 序列化规则不完整

文档有 `IndexMap`，但示例仍出现 `HashMap<String, u32>`、JSON commands、TOML maps、FlatBuffers、canonical body hash。当前没有一个跨 Rust/Go/TS/SDK 的统一 canonical encoding 规范。

炸点包括：

- JSON object key order 不稳定。
- TOML map 解析后顺序不应成为状态。
- Rust `HashMap` 在 `ResourceRegistry::cost()` 示例中出现。
- FlatBuffers 字段默认值和 vector 排序规则需要冻结。
- `body_hash` 的 canonical body hash 如何处理 JSON whitespace/key order 未定义。

Recommendation:
所有进入签名、TickTrace、state_checksum、Command、world_config_hash 的数据统一走 `CanonicalBinaryEncoding v1`；JSON 只作为调试格式。Map 必须 canonical sort by UTF-8 byte order 或使用 IndexMap 但由 parser 排序生成，不依赖文件原始顺序。

### A8 — Medium — Snapshot cap 与截断策略不确定

Tier1 预算写 `Snapshot per-player = 256KB`、`Snapshot total = 128MB`，但设计未说明超过 cap 时如何处理。玩家 snapshot 是 WASM 决策输入；任何非确定性的截断、分页、排序都会导致 commands 变化。若直接报错，也要定义该 tick 玩家输出是 empty commands 还是 rejection。

Recommendation:
定义 `SnapshotBuildResult`：

- 若可见实体超过 cap，按固定 priority bucket 和 stable id 截断。
- 截断必须暴露 `snapshot.truncated = true`、`omitted_counts`。
- 或选择硬拒绝该 player tick，但要写入 TickInputEnvelope。
- 不允许依赖 ECS query iteration 原始顺序。

### A9 — Medium — Pathfinding host function 的 tie-break 与缓存语义未冻结

`host_path_find` 是只读，但它会影响玩家 command 输出。文档有 pathfinding cache LRU，但没有说明：

- A* / JPS / flow field 的具体算法。
- 相同 cost 多路径的 tie-break。
- 动态障碍、ally collision、room exit 的排序。
- cache hit/miss 是否可能返回不同等价路径。
- cache key 是否包含 world_config_hash、terrain version、visibility version。

Recommendation:
path_find 必须是 deterministic library API：固定 neighbor order、fixed cost type、fixed tie-break `(f, h, x, y, room_id)`，cache 只能缓存最终 canonical result，不允许改变结果。

### A10 — Medium — Phase 2a/2b 战斗语义存在潜在冲突

Phase 2a 表里列出 `Attack, RangedAttack, Heal` inline；后文又说 `combat_system（damage 先 → heal 后）`，并说 Attack 在 2a 直接应用 damage，combat_system 处理 Tower/DoT。Heal 到底在 2a 按玩家顺序立即生效，还是在 2b heal 后结算？如果 Heal inline，则攻击者顺序会决定治疗是否来得及；如果 Heal 2b，则与 Move-as-action / per-drone slot 的关系不同。

Recommendation:
冻结每个 action 的 effect timing：

```text
Attack: Phase2a immediate damage
RangedAttack: Phase2a immediate damage
Heal: Phase2a immediate heal 或 Phase2b queued heal（二选一）
Tower: Phase2b queued damage
DoT: Phase2b queued damage
Death: mark at deterministic boundary only
```

并写出“HP <= 0 后是否还能被 later Heal 救回”的规则。

### A11 — Medium — Deploy/version_counter 与 tick 边界缺少 deterministic 生效规则

Auth 文档提到 deploy 使用 FDB `version_counter` 防重放；engine 文档提到部署时预编译，tick 时实例化已编译模块；gameplay 有 code_update_cooldown/window/propagation_speed。缺少统一规则：部署请求在 tick N 到达，模块从 N、N+1、还是传播到 drone 所在 room 后生效？rollback 与 code propagation 如何进入 TickTrace？Arena 代码锁定是否记录 module hash set？

Recommendation:
定义 `CodeActivationEvent`：

- deploy accepted at server_time 不等于 world effective tick。
- 所有代码变更只在 tick boundary 生效。
- `effective_tick`、`module_hash`、`scope`、`propagation frontier` 写入 TickTrace。
- Arena start 时冻结 slots → module_hash list，比赛期间 deploy 不影响该 arena。

### A12 — Low — 时间单位混用会造成签名/验签和审计边界错误

Auth 中 Canonical Request 使用 `unix_ms`，WebSocket 握手表里使用 `unix_seconds`，nonce 有 96-bit / 128-bit 两种写法，timestamp 窗口有 30s / 60s / 300s。虽然认证不直接影响世界状态，但 deploy/admin/auth 事件进入 tick 边界时，这种混用会造成跨语言实现差异。

Recommendation:
所有 canonical payload 固定 `unix_ms` decimal string；nonce 固定 128-bit base64url；窗口按 endpoint 配置但字段单位统一。

### A13 — Low — 技术选型文档与 engine 文档在 sandbox 生命周期上矛盾

tech-choices 说 Wasmtime 的需求包括“per-tick fork 生命周期——每 tick 新 fork，执行完 kill”；engine 性能预算说“WASM instances 池化，不每 tick fork/kill”。这会影响进程隔离、缓存状态、fuel reset、memory reuse、host import state reset 等确定性边界。

Recommendation:
统一为一种合同。若采用实例池：每 tick 必须 reset store/memory/globals/fuel/import state，且禁止玩家持久化线性内存跨 tick。若采用进程池，也要说明 worker 复用但实例不复用。

## Missing

1. `Determinism Spec v1`：单独文件，定义 state_checksum 输入、TickInputEnvelope、canonical encoding、系统顺序、错误处理、版本边界。
2. `WasmDeterminismProfile`：导入白名单、Wasmtime feature set、WASI 禁用/替代、host function ABI、trap/fuel/timeout 语义。
3. `CanonicalEncoding v1`：所有签名、Command、TickTrace、world_config_hash、mods_lock_hash、state_checksum 共享同一个 encoding 规则。
4. `SnapshotTruncationSpec`：Tier1 也需要，不应等 Tier2。
5. `RuleModDeterminismSpec`：mod 排序、action log、rollback、iterator order、预算超限、visibility scope。
6. `PathfindingSpec`：算法、neighbor order、tie-break、cache key、动态障碍语义。
7. `TickCommitProtocol`：FDB size 超限、chunking、commit marker、recovery、权威/非权威数据分类。
8. `CodeActivationSpec`：deploy/rollback/code propagation/Arena lock 与 tick 边界关系。
9. `PRNG Stream Registry`：每类随机调用有独立 stream id 和 offset 规则，避免插入新随机调用改变旧行为。
10. Cross-doc consistency pass：sandbox fork vs pool、market phase、Tier1/Tier2 feature gate、float examples、time units、nonce widths。

## Phase Ordering

1. Freeze Determinism Spec v1 first. 不应先实现 engine tick。先写清楚 `state_before + TickInputEnvelope + deterministic_execute = state_after + checksum`。
2. Freeze CanonicalEncoding v1 and IDL. 之后所有 SDK、MCP schema、auth canonical request、TickTrace 都从这个 encoding 派生。
3. Freeze WASM sandbox contract. 先确定 imports、fuel、trap、timeout、host function 语义，再讨论多语言 SDK。
4. Freeze RuleMod and world_config parsing. 先消灭 float、HashMap、unordered map、mod order 不确定性，再开放 Rhai / world.toml 扩展。
5. Freeze snapshot/pathfinding/visibility. 这些直接决定玩家 commands，必须在 gameplay 平衡前完成。
6. Freeze deploy/code activation. 否则热更新、Arena lock、rollback、code propagation 会污染 replay。
7. 再进入 gameplay balancing / economy / PvE tuning。数值可以调，确定性合同不能边实现边补。

## Final Recommendation

请求大改不是否定整体架构，而是要求把“确定性”从多个文档里的好意图提升为一个可执行合同。当前设计已经有足够好的地基；下一步应把所有会影响 replay 的隐式假设显式化、版本化、测试化。

建议验收标准：任选一个 tick，在不同机器、不同线程数、冷/热缓存、不同 replay 时间执行，给定相同 `state_before + TickInputEnvelope`，必须得到 bit-identical `state_after + state_checksum`。如果某个组件不能满足这个标准，它就不能进入 authoritative path，只能作为缓存、诊断或 UI 层。