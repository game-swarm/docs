# R22 Phase 1 Clean-Slate 架构评审 — GPT-5.5

## Verdict

CONDITIONAL_APPROVE

整体方向是成立的：WASM-only player path、deferred command model、deterministic tick、FDB 作为权威提交点、manifest hash 进入 TickTrace，这些选择像 Screeps / Factorio replay / FDB simulation testing / ECS fixed schedule 的成功模式，而不是“实时 MMO + 任意脚本”常见的不可回放泥潭。

但当前文档还不能直接进入实现冻结。主要问题不是技术选型，而是“权威合同分裂”：同一个关键语义在不同文件里仍有冲突版本。若现在实现，最可能炸在 replay/audit 语义、特殊攻击调度、API enum/limit 不一致，以及快照截断/可见性语义被不同团队各自解释。

## Strengths

1. **WASM 是唯一执行路径**
   - 人类和 AI 都通过部署 WASM 参与游戏，没有 McpPlayerExecutor 这类旁路。
   - 这是公平性和安全性的关键架构胜利：同一 fuel metering、同一 sandbox、同一 command validation。

2. **Deferred command model 是正确抽象**
   - WASM 只返回 CommandIntent，所有 mutation 进入服务端 validate-and-apply 管线。
   - 这避免了 host function 直接改世界状态导致的 TOCTOU、权限绕过和 replay 分叉。

3. **确定性设计覆盖面很广**
   - 固定 system manifest、Blake3 deterministic PRNG、IndexMap / stable entity id、fixed-point integer、canonical sort key 都是必要且正确的。
   - manifest hash / limits hash / codec version 进入 TickTrace 的方向非常好，像“协议版本化 + replay verifier”的成熟工程形态。

4. **FDB 小事务 + object store 大对象分层是正确方向**
   - FDB 不写大 blob，只写 head / manifest / hash / pointer，避免 3 秒 tick 被大对象 I/O 拖死。
   - 这是从“理论 ACID”走向“能运营”的务实架构。

5. **系统调度显式化是巨大进步**
   - 29-system manifest、R/W matrix、RoomCap 中间态约束、SpawningGrace filter、death_mark → spawn 顺序都降低了实现歧义。

## Concerns

### A1 — Critical — Persistence / TickTrace 审计合同互相冲突

`01-tick-protocol.md` 明确要求 TickTrace 与世界状态在同一 FDB 事务中提交，甚至写明“不允许状态成功但审计缺失”。但 `05-persistence-contract.md` 改成 FDB commit 先成功、TickTrace blob 异步上传，上传失败时 world state 完整但 replay 不可用 / audit_gap。

这不是细节冲突，而是架构语义冲突：
- 如果 TickTrace 完整性是 gameplay consensus 的一部分，则 async blob failure 不能产生已提交 tick。
- 如果 TickTrace blob 只是审计增强件，则 `01-tick-protocol.md` 不能继续声称“状态 + 审计同事务无缺口”。

建议裁决为三层模型：
1. **FDB 同事务必写 minimal replay core**：commands_hash、state_checksum、manifest_hash、fuel_ledger_hash、content_hash、chain_hash、terminal_state。
2. **Object store 异步写 rich trace blob**：完整 state diff、debug detail、profiling、可视化 replay artifact。
3. **文档明确区分 replay-verifiable 与 debug-rich**：blob 缺失只能损失 debug richness，不能让 committed tick 变成 unreplayable；若做不到，就必须让 blob 成为 commit 前置条件。

### A2 — High — “单一权威源”仍然被多个文件重复声明并产生分叉

文档多处声明自己是权威：API Registry 是 API 权威源、Phase2b Manifest 是调度权威源、Persistence Contract 是持久化权威源。但其他文件仍重复声明具体数字和列表，且已经出现不一致。

已观察到的分叉包括：
- API Registry 开头说 Game API 工具 54 个，Auth 11 个；变更记录又说 MCP tools 总数为 56 active。
- API Registry blob `wasm_module` 最大 64 MB；WASM Sandbox 模块预校验最大 5 MB。
- Command Validation 多处出现未在 canonical RejectionReason 注册的 wire-like code，如 `TileBlocked`、`StillSpawning`、`ExceedsRoomCapacity`、`InvalidDamageType`、`AlreadyDebilitated`、`MainActionQuotaExceeded`。
- Command Validation §6 写整批 tick 输出 ≤1MB，而前文、Sandbox 和预算表写 WASM 输出 ≤256KB。
- Engine 默认 per-player drone cap 500；Command Validation 限制表又写 `MAX_DRONES_PER_PLAYER = 50`。

这些是新人实现时最容易“看起来没问题但实际会炸”的模式：每个实现者都能引用一个文档证明自己是对的。

建议：所有非权威文件只保留 prose + link，不重复表格数字。CI 应禁止在非 registry/manifest/contract 文件中出现关键常量的手写值，或至少用生成器同步。

### A3 — High — 特殊攻击调度模型仍不闭合

系统清单里 `special_attack_reducer` 写成从 S11-S13 combat systems 收集特殊攻击 intent，但特殊攻击在 API Registry 中是 `CommandAction::Custom(type)`，在 Command Validation 中也是玩家提交的动作。它们应当来自 Phase 2a inline command handling 或专门的 pending special attack buffer，而不是来自 attack/ranged/heal combat systems。

同时，Manifest 把 S16-S22 放入 “Status Effects Parallel Set B”，但又说 `status_advance_system` 统一读取 S14 intents 并写入所有 StatusState。R/W matrix 中 S16-S22 都写 `StatusState`，并行安全证明却说它们写互不重叠 subtype；`status_advance_system` 又可能写所有 subtype。这里存在实现级数据竞争与语义重复：到底是各 status system apply，还是 status_advance apply？

建议改成更直观的三段：
1. Phase 2a：所有特殊攻击命令只做 validate + append `PendingSpecialIntent`。
2. Phase 2b：`special_intent_reducer` canonical sort + conflict resolution。
3. Phase 2b：单一 `status_apply_and_advance_system` 串行应用 intents、推进 duration、过期清理。

不要把“状态推进”和“状态效果系统”并行拆开，除非每个 subtype 的所有权、输入输出和 reducer 边界可以机器验证。

### A4 — High — Entity creation 可见性规则存在矛盾

Manifest §3 写“所有新实体追加到 pending_entities，当前 tick 所有 system 执行完毕后 flush”。但 S03 Build 又写 structure immediate inline creation；S08 Spawn 又写新 Drone 追加到 pending_entities，同时 S09 需要给 newly spawned drone 加 SpawningGrace，S11-S15 又要 filter 它。

这会直接影响同 tick 可见性与交互：
- Build 出来的结构是否能被同 tick 后续 Transfer / Attack / Collision 看到？
- Spawn 出来的 drone 如果 pending 到 tick 末尾，S09/S11 如何看到它？
- RoomCap 在 S07/S08 释放与消费，但 entity visibility 又延迟 flush，两者是否可能分叉？

建议把 entity lifecycle 明确拆成：
- `materialized_this_tick`：系统可见但玩家命令不可见。
- `player_addressable_next_tick`：玩家命令和 snapshot 下一 tick 才可见。
- `pending_flush` 只用于 ID 分配/存储落盘，不用于系统可见性。

否则实现者会在 Bevy command buffer、deferred spawn 和 immediate world mutation 之间做不同选择。

### A5 — Medium — Snapshot truncation 语义有两个版本

Engine 文档的 bucket 顺序是“自机 > 友方 drone > 敌方 drone > 建筑 > NPC > 资源”，Tick Protocol 的 bucket 又是“关键桶 Spawn/Controller/depot/storage 永不截断 > 己方 drone/建筑 > 敌方/资源点 > 友方/中立”。两者对玩家策略影响非常大。

这不是 UI 优先级，而是 WASM 可观测输入合同。不同截断会改变 AI 策略、replay hash、甚至公平性。

建议把 Snapshot Contract 作为唯一权威：定义 bucket、排序键、距离参考点、多 drone 如何合并距离、关键实体是否永不截断、`omitted_counts` 的精确 schema。其他文档只引用。

### A6 — Medium — 容量模型表达过于乐观，容易误导实现

目标 500 / hard cap 1000 的方向可以接受，但推导里有几个危险信号：
- “1000 workers / 40 cores → ~25ms wall-clock”这种表述忽略调度、IPC、cgroup throttling、cache pressure、Wasmtime instance reset 成本。
- cgroup `cpu.max = 250000 3000000` 表示每 sandbox 3s 内 0.25 CPU 秒；若 1000 workers 同时活跃，总额远超 40 cores 的实际预算，必须依赖 admission，而不是 worker 数学。
- Worker pool size 与 CPU quota / aggregate budget / active player admission 的关系还不够闭合。

建议将容量合同从“worker 数推导”改成“measured admission contract”：每 tick 根据实际 available core time、recent p95/p99 sandbox execution、snapshot stitching cost 动态计算 admitted players/fuel。文档中保留 500/1000 作为 SLO target，不作为数学保证。

### A7 — Medium — Command validation 的“预校验 resolved cache”与 inline 当前世界校验存在 TOCTOU 语义灰区

文档说 RawCommand 通过预校验升级为 ValidatedCommand，携带 target position、distance、cost 等缓存，应用阶段直接使用避免二次查表。但 Tick Protocol 又强调 Phase 2a 校验基于当前 Bevy World 状态，目标移动后按当前位置检查。

这两者容易导致实现者缓存过多：如果 `resolved.distance_to_target`、`object_position`、`cost` 被应用阶段复用，就会把 snapshot/预校验时状态错误地带入 inline apply。

建议：ValidatedCommand 只允许缓存不可变解析结果（entity id parse、action schema、resource type enum、body cost formula version）。所有依赖当前世界的字段必须在 `validate_and_apply()` 中重新读取。

### A8 — Low — 接口直觉性仍有小摩擦

整体 API 已比 Screeps OOP 更适合 WASM/IDL，但有几处命名和分层会让新人困惑：
- MCP Tools 与 Host Functions 部分重叠，如 path / terrain / objects 查询，需要清晰解释“外部客户端 MCP”和“WASM 内 host fn”的关系。
- `MCP_Query` 被放入 command sort priority，但查询又“不进指令管线”。这在概念上容易误解为 query 会参与 Phase 2a ordering。
- `Overload target_id` 有时像 player_id，有时示例像 entity id，需要统一类型名。

## Missing

1. **权威源边界矩阵**
   - 需要一张表明确每类事实由哪个文件/IDL 唯一拥有：limits、rejection enum、command schema、snapshot truncation、system order、persistence semantics、sandbox budgets。

2. **Replay 最小充分数据定义**
   - 必须定义没有 rich TickTrace blob 时，靠 FDB manifest/hash/pointers 是否足以 replay/verify。
   - 如果不足，应明确 committed tick 对 replay blob 的同步依赖。

3. **特殊攻击状态机的机器可读 manifest**
   - 当前 prose 太多，且跨 command validation / manifest / gameplay 分散。
   - 建议把 special action priority、stacking、cooldown、status writes、counterplay window 放入 IDL 或 generated registry。

4. **Snapshot Contract 未纳入本次白名单但被大量引用**
   - 当前被评审文件中已出现多个 snapshot truncation 版本，应补入下一轮架构评审范围。

5. **跨存储恢复 runbook 的端到端状态机**
   - FDB commit 成功、object upload pending/failed、engine crash、GC、replay verifier 的组合状态需要一个完整状态图。

6. **实现者友好的 glossary**
   - `tick N initial snapshot`、`committed tick`、`current Bevy World`、`FDB authority`、`Dragonfly stale cache`、`MCP query snapshot` 这些术语需要统一定义。

## Phase Ordering

1. **先冻结权威合同，而不是先实现 engine**
   - A1/A2/A3/A4 必须先裁决，否则实现会分叉。
   - 优先顺序：Persistence replay contract → API/limits registry cleanup → system manifest special attack rewrite → entity creation visibility rule。

2. **第二步生成机器可读 contracts**
   - API Registry、System Manifest、Limits Manifest、Snapshot Contract、Special Action Manifest 都应由 IDL/manifest 生成 Markdown。
   - 非权威文档只保留解释文字，不复制数值表。

3. **第三步写 conformance tests before implementation**
   - 重点测试：FDB commit retry 不重跑 WASM、object blob missing 的 replay 行为、special attack 同 tick priority、SpawningGrace filter、snapshot truncation stable order。

4. **第四步实现最小垂直切片**
   - 先实现 Move/Harvest/Transfer/Spawn/Attack + minimal replay + one sandbox worker pool。
   - 暂缓 Leech/Fabricate、复杂 economy、联盟、Arena tournament，除非其 manifest 已机器化。

5. **第五步做容量验证再承诺 hard cap**
   - 500/1000 active player 只能在 benchmark 后变成承诺。
   - 设计文档可保留目标，但实现准入应由 measured admission control 驱动。

## CrossCheck — 需要跨方向检查

- CX1: TickTrace blob 异步上传失败后，是否仍满足反作弊与审计要求 → 建议 Security 检查 “committed state but missing rich trace” 是否可被攻击者利用来制造不可审计窗口。
- CX2: `debug_detail` 在 practice/training 模式中可能泄露不可见实体信息 → 建议 Security 检查 visibility redaction 与 admin/player trace 分离。
- CX3: Snapshot truncation bucket 会显著影响玩家策略与新手体验 → 建议 Game Designer 检查 “关键实体永不截断” 与 “敌方/资源优先级” 是否符合 gameplay 预期。
- CX4: Move-as-action 的迟钝感是明确设计选择，但会影响 AI 编程模型学习曲线 → 建议 Game Designer 检查教程、SDK 示例和 early-game pacing。
- CX5: 1000 worker / 40 cores 容量推导可能低估运维成本 → 建议 DevOps/Performance 检查 cgroup、process pool、Wasmtime reset、FDB p99 commit 的真实压测模型。
- CX6: MCP tools 与 WASM host functions 的查询能力边界相近 → 建议 UX/API Reviewer 检查新人是否能直观看懂“外部 agent 查询”和“沙箱内查询”的差异。
