# R15 Phase 1 Clean-Slate 架构评审（GPT-5.5）

## Verdict

REQUEST_MAJOR_CHANGES

R15 的总体方向是正确的：WASM-only 玩家模型、deferred command、ECS、TickTrace、FDB 原子提交、确定性回放这些核心选择像一个可以成功的 Screeps 精神续作，而不是传统 MMO 服务器的错误翻版。它最强的地方是愿意把“确定性、公平预算、审计、回放”提升为一等架构合同，而不是后期补丁。

但当前文档已经进入一个危险区：同一概念在不同文件中被重复定义，并且多处定义互相冲突。这里的问题不是“实现难”，而是“两个实现团队都按文档做，最后会得到两个不兼容引擎”。如果不先收敛权威合同，后续实现会在 tick 排序、快照截断、资源预算、sandbox 隔离、spawn/recycle/refund、ECS 调度这些基础层面分叉，最终 replay verifier 会成为第一个爆炸点。

## Strengths

1. WASM-only 玩家模型清晰

人类与 AI 都编译为 WASM、引擎只认模块不认作者，这是非常好的边界。它避免了 “MCP 玩家走特殊路径” 的架构腐蚀，也避免了未来为 AI agent 开侧门。这个选择和 deferred command model 搭配得很好：WASM 负责决策，engine 负责验证与执行。

2. Deferred command model 是正确抽象

禁止 mutating host function，让所有状态变化进入统一 command validation/apply 管线，这是 MMO RTS 的正确架构。它把 replay、反作弊、权限校验、审计、错误码、退款策略统一在一个地方，避免 “SDK 调 host_move，REST 又走另一条路径” 的经典失败模式。

3. Tick 原子性意识很强

文档明确认识到 FDB rollback 不会自动恢复 Bevy World，要求 Phase 2a 前做内存快照并显式 restore，这是非常重要的架构觉悟。很多实时模拟系统会在这里犯错：持久层回滚了，内存世界没回滚，下一 tick 开始带毒。

4. 性能预算从愿景下沉到合同

3s World tick、COLLECT/EXECUTE/COMMIT/BROADCAST 分段预算、sandbox deadline、snapshot cap、host function cap、simulate cap 都被显式列出。这比“以后优化”强很多，能逼迫实现阶段做持续性能回归。

5. 可见性优先的拒绝语义合理

`NotVisibleOrNotFound` 作为玩家侧 opaque 错误是正确的安全直觉。它避免通过错误码枚举世界中不可见实体，是多人对抗游戏中非常容易被忽略但实际会炸的点。

6. FDB 只存 head/manifest/hash/pointer 的方向正确

避免把全量世界状态和大 TickTrace blob 塞进单个 FDB 事务，这是对 FoundationDB 成功案例的正确借鉴。FDB 适合强一致小事务，不适合每 tick 大 blob 写入。

## Concerns

### A1 — Critical — 权威合同重复且冲突，当前文档不具备可实现唯一性

同一基础概念在 `design/engine.md`、`specs/core/01-tick-protocol.md`、`specs/core/02-command-validation.md`、`specs/core/04-wasm-sandbox.md` 中重复定义，并且已经互相冲突。

典型例子：

- 命令排序键至少出现三种：`shuffle_order + sequence`、`(priority_class, shuffle_index, sequence, source)`、`(priority_class, shuffle_order, source, sequence)`。
- command 数量上限出现 100、500、1000 三个值。
- snapshot 截断桶顺序在 engine 与 tick spec 中不同：engine 写“自机 > 友方 drone > 敌方 drone > 建筑 > NPC > 资源”，tick spec 写“关键桶 > 己方 > 敌方/资源点 > 友方/中立”，并且 tick spec 还引入距离排序。
- ECS 主线顺序在 engine 中是 `death_mark → spawn → spawning_grace → combat → status_advance → aging → death_cleanup`，tick spec 的示例链又包含大量额外系统并把 regeneration/decay 放入 `.chain()`，和“并行系统”文字说明冲突。
- sandbox cgroup CPU 出现 `250000 3000000` 与 `50000 100000` 两套值；pids 出现 32 与 16 两套值。
- output JSON 上限同时出现 256KB、1MB、批级 ≤1MB、单条 ≤64KB 等表述。

这不是文档小瑕疵，而是架构层面的“多权威源”问题。成功的确定性游戏引擎必须有单一的 normative contract；解释性设计文档只能引用它，不能再次定义它。

建议：建立一个“Authority Matrix”：每个概念只能有一个权威文件，例如 tick sorting 只以 `01-tick-protocol.md §9.1` 为准，command schema 只以 `02-command-validation.md` 为准，sandbox budget 只以 `04-wasm-sandbox.md` 或 `01 §8` 为准，其他文件只写摘要与链接。所有重复表格要么删除，要么标注 non-normative。

### A2 — Critical — Tick/FDB 失败语义存在自相矛盾，会破坏燃料、公平与回放

`01-tick-protocol.md` 中对失败语义有多处冲突：

- §3.5 写 FDB commit 失败后最多重试 3 次，全部失败则 tick 放弃；放弃 tick 世界状态不变，tick_counter 不递增，消耗 fuel 退还。
- §6.1 表格写 Phase 2a panic/OOM 时“已消耗 fuel 不退，已执行玩家空 tick”；同表又写 FDB commit fail 时 fuel 退还。
- §8.4 写 FDB commit 失败重试复用 COLLECT，失败 3 次放弃后退还 consumed_fuel。
- §9.4 Crash 恢复表写 COLLECT 完成、EXECUTE 执行中崩溃时 fuel 全额退还，当前 tick 重新执行。

这些语义必须被压成一个清晰状态机：

- 哪些失败导致 tick 未提交？
- 未提交 tick 的 fuel 是否永远不生效？
- “玩家空 tick，不退 fuel” 只适用于玩家自身 WASM timeout/crash，还是也适用于引擎 panic？
- EXECUTE panic 是全 tick rollback 还是部分玩家空 tick？
- FDB retry 是否会重新执行 WASM？文档说不重新执行，这是好设计，但必须成为唯一语义。

如果不收敛，玩家会观察到不可解释的 fuel 扣费；replay 会遇到“trace 中有扣费但无状态变化”或“状态没变但玩家预算变了”的边界问题。

建议：把 tick 失败语义改写成事务状态机，而不是表格拼贴。核心原则应为：未提交 tick 不产生任何持久 gameplay/fuel 影响；玩家自身 sandbox 失败产生 0 command 且是否扣 fuel 由 COLLECT 成功边界定义；引擎/存储失败导致全 tick rollback。

### A3 — High — Command source / sequence 排序不一致，会导致跨入口公平性与回放分叉

排序是多人竞争游戏的核心公平机制。目前存在以下冲突：

- `01 §9.1` 定义 `sort_key = (priority_class, shuffle_index, sequence, source)`，即同玩家内先按 sequence，再用 source tie-break。
- `02 §2.1` 写 `sequence` 是 per-(player, source)，并说全局排序键是 `(priority_class, shuffle_order, source, sequence)`。
- `02 §2.1` 又说 WASM 的 seq=1 不与 MCP_Deploy 的 seq=1 冲突。
- `01 §9.1` 把 `source` 作为第四层 tiebreaker，且 `WASM > MCP_Deploy`。

这会影响真实 gameplay。例如同一玩家同 tick 通过 WASM 与 MCP/Admin 来源提交命令，如果 `source` 在 `sequence` 前，则所有 WASM 命令会整体在某来源前后；如果 `sequence` 在 `source` 前，则不同来源可以按 sequence 交织。两者都是合理方案，但只能选一个。

建议：明确 source 类型是否允许在 player command lane 内混排。若 MCP_Deploy 是部署事件而非 action command，最好不要混入同一 command queue；部署走独立 deploy event lane，并由 tick N+1 生效规则处理。玩家 action queue 只保留 WASM 来源，Admin/NPC 作为 priority_class 独立 lane。

### A4 — High — ECS 调度模型“串行主线 + 部分并行”的边界不稳定

设计试图同时表达两件事：

- 关键 gameplay 系统必须 `.chain()` 固定顺序。
- regeneration / decay 可并行。

这是正确方向，但当前文档把它写乱了：

- engine 文档称 regeneration、decay 与主线并行，仅需 before death_cleanup。
- tick spec 的 Rust 示例把 regeneration、decay 放进主线 `.chain()`。
- `02 §3.19` 又规定 `status_advance → (regeneration, decay 并行) → death_cleanup`。
- `01 §3.4` 的 component matrix 说 regeneration 只写 Energy/Carry，与主线不读写此字段；但主线中的 spawn/controller/transfer/refund 等概念事实上都可能触碰资源存储。

“Bevy 自动并行 + 声明无数据竞争”在设计文档层面必须非常精确，否则实现者会在系统插入时破坏确定性或中间态不变量。尤其是 RoomCap、DeathMark、ResourceStore、Status 这些资源都存在中间态。

建议：不要在规范中写分散的 Bevy 调度片段。改为定义一个权威 System DAG：每个 system 声明 inputs/outputs、允许并行组、barrier、禁止读取的中间态。实现代码从 manifest 生成或校验调度，而不是手写多个 `.after/.before` 段。

### A5 — High — Snapshot 截断既承担公平又承担防滥用，但策略含混且可能被游戏化

Snapshot cap 是必要的，但当前截断策略不够稳定：

- engine 与 tick spec 的 bucket 顺序不一致。
- 一处按 stable entity_id，一处按 distance/entity_id。
- “关键桶永不截断”与 256KB 硬上限存在潜在冲突：如果关键桶本身超过 cap，系统该 rejected、分页、还是破 cap？
- `visibility_abuse` 响应里写“降低 COMBAT 优先级”，这会把资源滥用检测直接接入战斗排序，可能变成隐性惩罚系统，且会影响确定性/公平解释。
- 连续 truncated 后降低 snapshot_quota 10%，可能导致受害者被敌方实体堆叠攻击后进一步恶化，形成负反馈。

这是典型“看起来没问题但实际会炸”的系统：截断规则一旦可预测，玩家会用实体摆放操纵对手视野；截断惩罚如果作用于被压迫方，会奖励攻击者。

建议：将 snapshot truncation 分成三层：硬安全 cap、可解释信息降级、反滥用归因。截断本身必须 deterministic 且不惩罚观察者；反滥用应归因到制造实体压力的 actor/room，而不是简单惩罚 snapshot 接收者。

### A6 — High — Sandbox 生命周期仍有跨 tick 状态泄漏风险，术语需要收敛

文档说采用 long-lived worker pool + per-tick clean Store/Instance reset，并“memory 清零、fuel 重置、WASI 关闭后重新按需开启”。这是方向正确，但需要进一步精确：

- Wasmtime Store、Instance、Memory、Linker、Module、Engine 哪些复用，哪些每 tick 重建？
- “清空线性内存”与“重建 Instance”二者是否都做？如果重建 Instance，内存天然新建；如果只清零，则 data segment、globals、table、start-like 初始化语义要严格处理。
- 模块含 active data/element segments 时实例化成本和初始化副作用如何受 fuel/epoch 限制？文档提到要在 Instance::new 前设置限制，但需要成为 ABI contract。
- Store reset 后 host-side per-player state 是否也清空？例如 host function 计数、path_find cache visibility fingerprint、输出 buffer 引用。

长期 worker pool 是必要性能妥协，但它和“独立进程隔离”的安全直觉不同。新人看到“每玩家 worker 进程”可能误以为玩家与 worker 固定绑定；看到“pool size active_players”又可能以为跨玩家复用。这里需要明确 worker 是否可服务不同玩家、何时销毁、如何清理 player context。

建议：写一个 Sandbox Object Lifecycle 表：Engine/Module/CompiledCode 可跨 tick 复用；Store/Instance/Memory/CallerContext/HostCallCounters 必须 per invocation 新建；WorkerProcess 可复用但不得持有 player gameplay state。

### A7 — Medium — FoundationDB “权威源”与 Bevy “权威执行状态”的叙述容易误导

文档多次说 FDB 是权威源，也说 COLLECT 从 Bevy World 内存读取权威状态，EXECUTE 在 Bevy World 原地修改，commit 后 FDB 成为新权威。这在实现上合理，但术语容易让新人困惑：到底哪个是 source of truth？

更准确的模型应是：

- FDB 是 durable source of truth。
- Bevy World 是 current tick working set / in-memory replica。
- COLLECT snapshot 是 tick N read view。
- TickTrace 是 audit/replay truth。

如果都叫“权威”，会导致查询路径和恢复路径被误实现。比如 MCP current snapshot 读 Bevy 是对的，但历史查询必须读 FDB；Dragonfly 是 cache；NATS 只是 delivery。

建议：统一术语：Durable Truth、Working Replica、Read Snapshot、Audit Log、Cache、Delivery Channel。不要在多个层都使用“权威源”。

### A8 — Medium — 技术选型总体合理，但 Bevy 与 Determinism 的关系被过度简化

`tech-choices.md` 说 Bevy `.chain()` 与 Determinism Contract 完美匹配。这个表述过于乐观。Bevy 可以帮助表达顺序，但确定性还依赖：

- query iteration order 是否稳定；
- entity id 分配是否可回放；
- parallel systems 是否真的无可观察共享；
- floating point 是否完全禁用；
- HashMap/IndexMap 是否所有路径都遵守；
- plugin/system 注册顺序是否由 manifest 锁定。

Bevy 是好选择，但不是确定性的保证来源。成功案例更像是“在通用 ECS 上构建确定性执行层”，而不是“ECS 自带确定性”。

建议：把 Bevy 定位为 execution substrate，而 Determinism Contract 才是产品级约束。需要一个 replay determinism CI gate 覆盖不同机器、不同线程数、不同 system schedule 的一致性。

### A9 — Medium — 游戏 action 抽象层次开始膨胀，核心规范与扩展 action 混杂

`02-command-validation.md` 同时定义基础动作、特殊攻击、custom actions（Leech/Fabricate）、重复的 CommandAction 变体，还出现 Recycle 两套退还规则：前文 lifespan 挂钩，后文标准 50% + Tutorial 100%。这让新人很难判断哪些是核心 v1，哪些是玩法扩展，哪些是示例。

这是常见设计文档膨胀模式：核心协议还没冻结，玩法内容已经把协议文档污染。后果是 validation 层很快变成“所有游戏规则的大杂烩”，失去可组合性。

建议：把 command validation 分为三层：Core Command Envelope、Built-in Vanilla Actions、RuleMod/Custom Action Registration。核心规范只定义 envelope、source、sorting、visibility、rejection、budget；具体动作矩阵放到 gameplay/vanilla 规范；custom actions 只通过 manifest/IDL 注册。

### A10 — Medium — 资源预算目标与容量目标之间缺少反压模型

文档给了 500 active players、5000 drones、50000 entities、per-player 256KB snapshot、COLLECT 2500ms、EXECUTE 400ms 等指标，但缺少当世界接近上限时的架构级反压策略。

例如：

- 1000 active players × 256KB snapshot = 256MB/tick 输入级别压力，虽然实际可见会小，但 worst-case 需要明确。
- Pathfinding 每玩家 10 次 + 100,000 explored nodes，如果 500 玩家同时打满，COLLECT host function 预算可能成为主瓶颈。
- Snapshot 构建 O(entities + players × visible_entities) 对 50000 entities 可行，但需要 room density cap 与 visible fanout cap 支撑。
- Dragonfly 允许滞后 ≤2 tick 与表格里 0–60s 可配置冲突。

建议：补一个 Admission/Backpressure Contract：玩家活跃判定、per-room density cap、pathfinding global budget、snapshot build global budget、degraded read mode、join/deploy throttle 的触发条件与优先级。

### A11 — Low — 接口对新人不够直观，术语和编号漂移严重

文档存在明显编号漂移和术语漂移：

- README 中 design/engine.md 是 §3 Engine，但文件内又从 §3 开始。
- `02-command-validation.md` 后半部分出现 “## 8 CommandAction 变体” 下的 “### 10.1”。
- `design/engine.md` 引用 `interface.md §4`，但本次白名单未包含 interface，且排序权威实际在 core spec。
- `specs/core/04-wasm-sandbox.md` 多次写“详见 design/interface.md”，但核心 ABI 事实上在 sandbox spec 内定义。

这些对架构正确性不是最高风险，但会显著增加新人误解概率。当前文档已经需要“读者自己归并冲突”，这对 Clean-Slate Phase 1 不合格。

### A12 — Low — 单实例优先的扩展策略务实，但 shard 预留还停留在口号

“单 Engine + FDB 单一提交 → 500/1000 玩家；水平分片为远期”是务实的，不应过早实现分片。但文档说 API 和数据模型预留 shard 扩展接口，却没有在白名单文件中看到关键不变量：entity id 是否包含 shard/room 前缀、跨房间 move 是否可变成跨 engine handoff、TickTrace 链是否 per shard、world_seed 是否 per shard/region。

这不是当前必须实现，但如果现在的 ID/trace/command envelope 完全不预留，将来水平分片会很痛。

## Missing

1. 单一权威矩阵

缺少一张表说明每个架构概念的 normative source：tick sorting、budget、snapshot truncation、sandbox lifecycle、command schema、failure semantics、ECS DAG、refund、replay、query source。没有这张表，文档会继续漂移。

2. Tick Failure State Machine

需要从“表格描述”升级为状态机：COLLECT_PENDING、COLLECT_DONE、EXECUTE_IN_PROGRESS、COMMIT_PENDING、COMMITTED、ABORTED、RETRYING、DEGRADED。每条边定义 state/fuel/trace/world snapshot 的处理。

3. System DAG Manifest

需要 machine-readable 或至少表格化的 ECS system manifest：system name、phase、reads、writes、barrier、parallel group、forbidden intermediate reads、determinism notes。当前散落的 `.after/.before` 代码片段不足以作为架构合同。

4. Sandbox Object Lifecycle Contract

需要明确 worker process、compiled module、store、instance、memory、host context、counters、cache 的生命周期与清理边界。否则 long-lived worker pool 会成为安全与确定性的灰区。

5. Snapshot/Visibility Abuse Threat Model

需要明确攻击者通过实体堆叠、出口视野、NPC/资源摆放、友方实体填充等方式影响他人 snapshot 的可行性，以及反制策略归因到谁。

6. ID / Entity / Room / Shard 命名合同

即使分片是远期，也需要现在确定 ID 是否稳定、是否跨 replay、是否包含 world/room/shard 信息、entity_id 排序是否可作为 deterministic tie-breaker。

7. Config Precedence Contract

world.toml、engine defaults、mode-specific defaults（World/Arena/dev relaxed）、RuleMod 覆盖项、server admin override 的优先级没有形成统一合同。当前很多预算“可配置”，但不知道谁能改、改了是否影响 replay。

8. Non-normative 示例标记

很多代码块看起来像规范，但可能只是示例。需要明确标注 Example / Normative / Informative，否则实现者会按示例实现。

## CrossCheck — 需要跨方向检查

- CX1: Sandbox seccomp/cgroup 与 Wasmtime 实际 syscall/API 可行性需要安全方向复核 → 建议 Security 检查 Wasmtime 30 在 Linux 下 JIT、epoch、fuel、mprotect、signals、threads 所需 syscall 是否与白名单一致。
- CX2: `NotVisibleOrNotFound`、snapshot truncation、host_get_objects_in_range 是否仍可能通过 timing/size/omitted_count 泄露不可见实体 → 建议 Security 检查信息侧信道与玩家可见 trace。
- CX3: Overload/Debilitate/Hack/Fortify 的特殊攻击状态机是否会破坏核心 command abstraction → 建议 Gameplay 检查这些是否属于 Vanilla Action，而不是 core validation 必备概念。
- CX4: 256KB snapshot cap、pathfinding host cost、500/1000 active player 容量目标是否能同时成立 → 建议 Performance 检查 worst-case COLLECT/SNAPSHOT 预算模型。
- CX5: MCP query 与 WASM tick 共享同一 snapshot 的产品语义是否满足 AI agent 调试体验 → 建议 UX/API 检查“为什么我 query 看不到刚提交动作结果”的开发者心智模型。
- CX6: FDB 小事务 + 对象存储/append-only log 的 TickTrace 链完整性 → 建议 Storage/Infra 检查 manifest/hash/pointer 方案是否覆盖 crash recovery 与 WAL replay。

## Phase Ordering

1. 先冻结权威合同，而不是继续扩展玩法

R15 下一步不应继续增加 action、特殊攻击、玩法表格。必须先做 contract consolidation：删除重复定义，建立 Authority Matrix，把冲突项收敛到唯一值。

2. 第二步冻结 Tick Failure State Machine

这是 replay、fuel、公平、FDB、Bevy snapshot 的共同根。没有这个，任何实现都会在异常路径分叉。建议把 A2 作为最高优先级修复。

3. 第三步冻结 Sorting / Source / Deploy lane

玩家公平性依赖排序；AI/MCP 与 WASM 的关系也依赖 source lane。建议明确 deploy 不是 player action command，不参与同一 action queue。

4. 第四步冻结 ECS System DAG

在玩法继续增长前，先规定系统插入方式与读写 manifest。否则后续每加一个状态系统都会重新打开确定性风险。

5. 第五步冻结 Sandbox Lifecycle

在实现 worker pool 前，明确 Store/Instance/Memory/HostContext 生命周期。这个决定会影响性能、安全、调试和 replay。

6. 第六步再推进 gameplay action 与 RuleMod

只有 core envelope、validation、budget、snapshot、failure、DAG 稳定后，特殊攻击和 custom actions 才应该继续扩展。否则玩法规则会持续污染 core protocol。

7. 最后才讨论 shard 预留细节

当前单实例优先是合理的；但在 ID、TickTrace、world_seed、room handoff 上留下轻量不变量即可，不要过早实现多 engine shard。
