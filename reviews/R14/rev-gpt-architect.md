# R14 Phase 1 Clean-Slate 架构评审（GPT）

## Verdict

REQUEST_MAJOR_CHANGES

整体方向值得继续：WASM + deferred command + ECS + TickTrace 的组合像 Screeps、EVE-style authoritative simulation、FoundationDB simulation testing 这些成功案例的交集，核心目标（公平计量、确定性回放、AI/人类同路径）是清晰且有架构一致性的。

但当前文档已经出现多个“权威合同互相打架”的问题：排序键、PRNG、sandbox 生命周期、预算上限、系统顺序、失败语义在不同文档中存在不可兼容定义。这类问题不是实现细节，而是确定性 MMO 引擎最容易线上分叉、回放失败、玩家申诉无法裁决的根因。建议在进入实现前先做一次 Contract Consolidation，把唯一权威语义收敛到少数规范表，并让 design 文档只引用不重复定义。

## Strengths

- 架构核心是正确的：玩家代码只产出 CommandIntent，状态变更由服务端统一 validate/apply，避免了 sandbox 直接改世界状态的经典失败模式。
- Tick 分阶段模型（COLLECT → EXECUTE → BROADCAST）直观，新人能理解每个阶段的职责，也便于观测、回放与故障隔离。
- “Bevy World 为 tick 内工作副本，FDB 为跨 tick 持久权威源，Dragonfly/NATS 非权威”这个读写分层是健康的，没有把缓存/推送误当成权威状态。
- 对确定性的关注覆盖了排序、整数数值、禁用非确定 HashMap、TickTrace、故障注入 CI、FDB rollback restore，方向明显优于普通游戏服务端设计。
- snapshot 截断、可见性优先错误、admin/player trace 分离，说明设计已意识到信息泄露和可解释性之间的张力。
- Sandbox 采用 WASM + Wasmtime + OS 隔离双层防线，且禁止 mutating host function，抽象边界清楚。

## Concerns

### A1 — Critical — Determinism Contract 多处互相冲突，当前无法作为实现权威

最严重的问题是“同一个概念有多个不兼容定义”。这些会导致不同实现者都认为自己符合文档，但线上 tick、replay verifier、SDK、审计工具产生不同结果。

具体冲突包括：

- 玩家命令排序：engine.md 使用“seeded shuffle 后玩家顺序 + 玩家内 sequence”，tick protocol §3.1 也使用 shuffle；但 tick protocol §9.1 又定义 RawCommand 全局排序键为 `(player_id, sequence, source)`，并明确不同玩家按 player_id 字典序。
- Command validation §2.1 又写排序键为 `(player_id, shuffle_order, source, sequence)`，字段顺序本身也奇怪：如果 player_id 在 shuffle_order 前，shuffle_order 对跨玩家排序不会生效。
- PRNG：tech-choices 与 engine.md 选择 Blake3 XOF 作为 PRNG；tick protocol §9.5 却要求每 namespace 使用 ChaCha8Rng。
- ECS 调度：engine.md 说主线 `death_mark → spawn → spawning_grace → combat → status_advance → aging → death_cleanup`，并把 regeneration/decay 作为可并行；tick protocol §3.4 的 20 系统链却把 regeneration、decay 放进 `.chain()`，且顺序不同；command validation §3.19 又给出另一版 `combat → status_advance → (regeneration, decay) → death_cleanup`。
- Output 截断：tick protocol §8.2 与 §9.7 要求 WASM output 超 256KB 整批丢弃；command validation §6 又写整批 tick 输出 ≤1MB；command validation §1.1 又写总字节数 ≤256KB。

这是确定性系统里的“多源真相”失败模式。成功案例通常会把 consensus/determinism contract 做成单一规范，其他文档只能引用，不重复写值。

建议：建立 `Determinism Contract` 单一权威章节，至少冻结：排序键、PRNG 原语、系统顺序、截断/拒绝语义、budget 表、失败/重试语义。其他文档中重复定义改为“引用该章节”。

### A2 — Critical — Sandbox 生命周期架构存在 fork-per-tick 与 long-lived pool 两种互斥模型

engine.md §3.4.3 定义 “long-lived worker pool + per-tick clean Store/Instance reset”，tech-choices 也以此作为选择 Wasmtime 的关键理由；但 specs/core/04 §1 明确写 “每 tick fork → 执行 → kill”。这不是参数差异，而是架构形态差异：

- long-lived pool 依赖进程复用、模块预编译缓存、per-tick Store/Instance reset、worker recycle。
- fork-per-tick 依赖强隔离、低持久风险，但会改变性能预算、cgroup 策略、JIT/预编译收益、FD/seccomp 生命周期。

这会直接影响 3s tick 是否可达、漏洞响应、内存泄漏模型、指标解释和运维 runbook。当前文档同时承诺两者，会让实现天然分叉。

建议：选择一个基线模型。若优先性能和 500 active players，建议以 long-lived worker pool 为主；安全上用 per-tick clean Store/Instance reset、worker recycle、OOM/trap 后替换、validation policy/security_epoch 缓存失效来补足。若坚持 fork-per-tick，需要重算所有 tick 预算并删除 long-lived pool 相关承诺。

### A3 — High — 预算与容量合同跨文档不一致，且部分数值与目标规模互相压迫

同类资源限制多处不同：

- MAX_COMMANDS_PER_PLAYER：engine.md 容量表写 1000；command validation JSON schema 写 maxItems 100、文字写 ≤500；硬性边界又写 ≤500。
- MAX_DRONES_PER_PLAYER：engine.md 容量表写 default 100；command validation §6 写默认 50 且 Tier 1 = 50 players × 10 drones。
- cgroup cpu.max：WASM sandbox §4.2 写 `250000 3000000`，§9.2 checklist 又写 `50000 100000`。
- Tick EXECUTE 预算：engine.md 表写 EXECUTE ≤400ms，tick protocol 状态机写 EXECUTE 超时 500ms，统一预算表又说 EXECUTE 无单独超时、必须在 tick_soft_deadline 内完成。

容量合同是架构的“外部接口”。如果它不一致，后续负载测试、SLO、玩家套餐、反滥用策略都会失去基准。

建议：把预算分成四张权威表：tick pipeline budget、per-player WASM budget、gameplay caps、infra sandbox caps。每个限制只在一处定义，并标明 World/Arena/MVP/目标/硬上限。

### A4 — High — FDB 事务边界与 Bevy 内存世界的关系仍有“看起来 ACID、实际双写”的风险

文档正确指出 FDB rollback 不会自动恢复 Bevy World，并要求 world.snapshot()/restore()。这是关键洞察。但现有描述仍有几个架构风险：

- tick protocol §3.5 伪代码把 `validate_and_apply(txn, command, world_state)` 混在一起，容易让实现者在 FDB txn 与 Bevy World mutation 之间形成双写同步问题。
- TickTrace/keyframe 有时说与状态同一 FDB 事务，有时又说大 blob 进入对象存储或 append-only log；若 trace payload 分裂到对象存储，需要明确 manifest commit 语义，否则会出现 FDB head 指向未成功写入的 blob。
- “commit 失败最多重试 3 次，全部失败则 tick 放弃；放弃后等待 1s 重试同一 tick；连续放弃 3 次降级”这段在读者视角有歧义：一次 tick 内 3 次 commit retry 后是“tick 放弃并不递增”还是“同一 tick 稍后重试”，fuel refund 与 COLLECT cache 生命周期也随之变化。

建议：明确采用 outbox/manifest 模式：所有大对象先 content-addressed 写入，FDB 事务只推进 head + manifest pointers + checksums；Bevy mutation 只在内存工作副本中发生，commit 成功后才发布，commit 失败必须 restore。并给出 tick abandon/retry 的唯一状态机。

### A5 — High — RuleMod/Rhai 与“确定性核心”之间的抽象边界还不够硬

tech-choices 引入 Rhai 作为服主可信层，tick protocol §9.8 也提到 RuleMod 必须经 World Action Manifest + IDL 注册 schema。这是正确方向，但对架构来说还缺少几个防炸边界：

- RuleMod 可以扩展哪些东西：Action schema、系统链插入点、资源公式、地图生成、AI/NPC 行为，边界未在允许文件中形成统一矩阵。
- RuleMod 是否能读取/修改 ECS World，还是只能声明规则由 engine 执行，没有完全冻结。
- RuleMod 与 replay 的版本锁定、mods_lock_hash 已提到，但缺少“manifest capability model”：每个 mod 声明读写 Component/Resource、系统顺序、determinism constraints。

这是很多可扩展游戏引擎失败的地方：插件系统一开始“只是小脚本”，后来成为第二套状态修改路径。

建议：将 RuleMod 降级为声明式/受限命令扩展优先；若允许脚本系统，必须要求 manifest 声明 capabilities、读写集、调度点、版本 hash、IDL schema，并由 engine 在同一 validate/apply 管线执行。

### A6 — Medium — “Move = Action” 是清晰设计选择，但需要在接口层暴露得更不可误用

Move 占 main action slot 是有意选择，且理由充分。风险在于文档中 Transfer/Withdraw 不计 main action，特殊攻击又与 HP 伤害/同 body part 互斥，Move/Attack/Harvest/Build/Heal 是 main action。新人实现 SDK 或写策略时容易误判。

建议：将动作模型抽象成显式的 `ActionClass`：`MainAction`、`AuxiliaryAction`、`Query`、`Deploy/Admin`，并在 IDL 中对每个 action 标注 quota class、cooldown class、refund class、visibility class。否则规则会散落在校验表 prose 中。

### A7 — Medium — Snapshot truncation 的架构目标正确，但优先级定义不一致且可能制造 gameplay 语义争议

engine.md 说 priority bucket 为“自机 > 友方 drone > 敌方 drone > 建筑 > NPC > 资源”，tick protocol §2.3 又说“关键桶 Spawn/Controller/owned depot/storage 永不截断，高优先己方 drone/建筑，中优先敌方可见实体/资源点，低优先友方/中立”。两者不一致。

此外，“敌对方通过堆叠实体增加受害方 snapshot 压力”的行为被允许，但如果关键实体永不截断、敌方排序按距离，玩家会把 truncation 当成 gameplay mechanic 研究。这个可以接受，但需要正式化，不然会变成申诉热点。

建议：把 snapshot priority 视为 gameplay-visible contract，固定唯一优先级与 tie-breaker，并在 SDK/reference 中暴露。不要在不同文档给不同桶顺序。

### A8 — Medium — MCP 与 WASM 同快照的设计很好，但“查询不进指令管线”需要更清晰的权威接口边界

tick protocol §6.4 说 MCP_Query/REST/WebSocket 的权威读源优先级不同，MCP_Query 不得直接读 FDB，必须共享 visibility filter。command validation §4 又说查询不进指令管线，在快照生成阶段处理。架构方向没问题，但接口命名容易混淆：

- WASM host query 是 tick 内只读查询，计入 fuel/host quota。
- MCP query 是外部接口查询，可能服务人类/AI agent，不一定在玩家 WASM tick 执行期。
- Web display snapshot 不受 WASM cap，且不受 fog_of_war 限制的说法在 engine.md §3.4.2 “展示用，非 WASM 输入；不受 fog_of_war 限制”非常危险：如果是玩家展示层，仍必须受可见性限制；若是 admin display，需要单独命名。

建议：把读接口分为 `PlayerVisibleSnapshot`、`AdminSnapshot`、`ReplaySnapshot`、`DisplayPage`，每类标明 auth、visibility、size cap、freshness、source。避免“展示层不受 fog_of_war”被误实现为玩家可看全图。

### A9 — Low — 技术选型整体务实，但 Bevy 版本稳定性和 headless server 边界需要显式降险

选择 Bevy ECS 可以成立，尤其 Rust 同栈和调度图能力匹配。但 Bevy 是游戏引擎，不只是 ECS 库；其 API 变动、插件默认行为、浮点/时间资源、Schedule 语义升级都可能影响确定性。

建议：冻结 Bevy 版本，禁用/避开非确定默认插件，定义 Swarm 自己的 minimal App/Schedule profile，并要求所有 system 加入 manifest，不允许 ad hoc system 注册。

## Missing

- 单一权威 `Determinism Contract`：排序、PRNG、system order、numeric rules、truncation、replay input、failure semantics 需要一个不可重复定义的规范源。
- `Action Manifest` / `World Action Manifest` 的完整 schema：action quota class、读写集、cooldown/refund/visibility、状态推进点、IDL 绑定、mod capability。
- Worker lifecycle ADR：long-lived worker pool vs fork-per-tick 必须二选一，并附性能/安全/SLO 影响。
- Tick state machine 的正式状态图：commit retry、tick abandon、same-tick retry、degraded mode、fuel refund、COLLECT cache 生命周期需要消歧。
- Read model taxonomy：PlayerVisible/Admin/Replay/Display/MCP/WASM host query 的 auth、visibility、freshness、cap、source。
- Capacity contract registry：所有硬限制与默认值需要集中表，不应散落在 engine/spec/sandbox/validation。
- Mod/Rhai capability model：没有它，插件迟早会变成绕过 validate/apply 的第二状态通道。

## CrossCheck — 需要跨方向检查

- CX1: `world_seed` 泄露后未来 tick 可预测，文档接受“定期轮换 + 手动 bump”而非密码学前向安全 → 建议 Security 检查威胁模型是否足以覆盖竞技公平与内部威胁。
- CX2: “player display snapshot 不受 fog_of_war 限制”可能是文档措辞，也可能是严重信息泄露 → 建议 Security / UX 检查展示层、admin 层、玩家层的权限分离。
- CX3: WASM sandbox seccomp 白名单允许 `write`、部分位置允许 `clone`，另一些 checklist 禁止 clone/fork，策略不一致 → 建议 Security 检查实际 Wasmtime 运行所需 syscall 与隔离边界。
- CX4: Snapshot truncation 允许被敌方实体压力影响，可能成为高级战术或 DoS 边界 → 建议 Gameplay / Security 联合检查是否公平、可解释、可滥用。
- CX5: Move 占 main action slot 会显著改变 Screeps 玩家迁移体验 → 建议 UX / Gameplay 检查新手心智模型、SDK 提示与教程是否能避免“单位迟钝”误解。
- CX6: FDB + object store / WAL / TickTrace 的组合涉及审计完整性 → 建议 Ops / Security 检查备份恢复、WAL 加密、对象存储一致性和灾备 runbook。

## Phase Ordering

1. Contract consolidation first：先合并并冻结 Determinism Contract、预算表、worker lifecycle、tick failure state machine；这一步不应写代码。
2. Interface freeze second：冻结 CommandIntent/RawCommand/ValidatedCommand、Action Manifest、read model taxonomy、snapshot truncation priority。
3. Architecture prototype third：只验证 tick loop、sandbox execution、validate/apply、FDB manifest commit、rollback restore、TickTrace replay，不做完整 gameplay。
4. Adversarial test suite fourth：用恶意 WASM、commit failure、snapshot truncation、排序冲突、seed replay、visibility probing 证明核心合同。
5. Gameplay expansion last：再加入特殊攻击、Rhai RuleMod、NPC、经济细节；所有新增机制必须通过 Action Manifest 和同一 validate/apply 管线。

## Bottom Line

R14 的方向不是错的，反而已经抓住了编程 MMO 引擎最关键的几个支柱：authoritative simulation、deferred command、deterministic replay、WASM sandbox、公平资源计量。当前阻塞点是“文档层的架构一致性”而不是“缺少更多功能”。如果现在按这些文档并行实现，会很容易出现多个都合理但互不兼容的引擎。先收敛合同，再实现。