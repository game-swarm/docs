# R-appcert-R2 Clean-Slate Review — Determinism

Reviewer: rev-gpt-determinism (GPT-5.5)
Focus: 状态机完备性、RNG 合约、重放完整性、命令顺序、吊销 / epoch bump 确定性语义

## Verdict

CONDITIONAL_APPROVE

总体判断：R2 设计已经明显具备“可确定性实现”的骨架：tick 状态机、Source Gate、CommandIntent/RawCommand 分层、TickTrace、snapshot/replay、可见性统一函数、WASM 只读 host function、CRL/epoch 事件记录等核心方向是对的。它不像常见失败案例里“实时消息 + 多入口直接改状态 + 事后补日志”的架构，而更接近成功的 deterministic simulation / event-sourced replay 设计。

但当前文档仍存在几处“看起来只是描述差异，实际会炸”的语义冲突。特别是部署生效时序、Command 顺序键、TickTrace/WAL 事务语义、security epoch 对运行中模块的状态转移、RuleMod/动态 action 的确定性边界，若不先冻结为单一合同，实现会自然分叉，导致 replay 与线上 tick 结果不一致。

## Strengths

- Tick 生命周期的 COLLECT → EXECUTE → BROADCAST 分层清晰，且明确 MCP query 与 WASM tick 读取同一 COLLECT 快照，避免中间状态泄露和 replay 歧义。
- WASM 执行模型强：唯一 WasmSandboxExecutor、无 mutating host function、fuel/memory/host-call budget、输出 JSON 全量校验，基本堵住了“执行中直接改世界”的非确定性入口。
- CommandIntent → RawCommand → ValidatedCommand 分层是正确抽象；player_id/source/tick 服务端注入，能防止客户端伪造顺序和身份上下文。
- Replay 选择记录 accepted/sorted RawCommand 而不是重跑 WASM，是正确取舍；这避开 Wasmtime 版本、JIT、玩家代码 crash/timeout 对历史回放的污染。
- 可见性使用统一 `is_visible_to(entity, player_id, tick)`，并覆盖 snapshot/MCP/REST/WS/replay/host function，是防 oracle 和 replay 视角一致性的关键亮点。
- FDB commit 失败时明确要求 Bevy World 快照恢复、COLLECT 结果跨重试复用、fuel 不重复扣费，这比“事务回滚即可”更贴近真实 ECS 实现风险。
- 安全吊销/epoch bump 被纳入 TickTrace replay 事件，而不是 replay 时重新查询当前 CRL；方向正确。

## Concerns

### A1 — High — 部署生效时序存在跨文档冲突，会直接破坏 replay 与玩家预期

`01-tick-protocol.md` 与 `06-feedback-loop.md` 明确：Tick N 部署 v2，Tick N+1 才切换，当前 tick 仍使用已加载模块。这个模型确定、直观，也符合 COLLECT 快照边界。

但 `09-command-source.md` §8.1 写成 RawCommand 顺序为 Admin → Deploy → WASM，并说明 “Deploy 命令（先部署，后 WASM 执行可引用新代码）”。这等价于同 tick deploy 影响同 tick COLLECT/WASM 执行，和前述 N+1 生效模型冲突。

风险：
- replay 若按 TickTrace 中 deploy-before-WASM 重建，会得到与线上 COLLECT 已执行模块不同的结果。
- 玩家/AI 的 first_tick_executed 事件无法定义：部署 accepted 后到底是当前 tick 还是下一 tick 首次执行。
- Arena 赛前锁定和 World 热更新将共享一套含糊语义，极易实现出两个路径。

建议：冻结为单一合同：`DeployAccepted(tick=N)` 只改变 `pending_module_version`，`active_module_version` 从 `N+1 COLLECT` 开始切换；TickTrace 必须记录 deploy accepted tick、activation tick、module_slot、old/new module hash。`09-command-source.md` 的 RawCommand 顺序应改为 Admin → WASM commands → RuleMod/系统事件，Deploy 不进入同 tick gameplay command ordering，而是 control-plane event。

### A2 — High — 指令全局排序键在 01 与 02 不一致，source 维度可能重排 gameplay

`01-tick-protocol.md` 的排序是 seeded shuffle 后按玩家顺序，再按玩家内 `sequence` 排序：`(shuffle_order, player_id, cmd.sequence)`。这是公平且易回放的模型。

`02-command-validation.md` §2.1 又写 `sequence` 是 per-(player, source)，排序键为 `(player_id, shuffle_order, source, sequence)`。这里有两个问题：
1. `player_id` 放在 `shuffle_order` 前会弱化/破坏 seeded shuffle 的公平语义。
2. `source` 进入 gameplay 排序键，但默认 gameplay 指令只应来自 WASM；Admin/Deploy/Tutorial/RuleMod 都有不同能力边界，不应混入同一个玩家内 sequence 空间。

风险：同一 tick 同一 RawCommand 集合在不同实现中可能按两种排序执行，资源竞争、TileOccupied、Overload 全局冷却、Hack 首命中都会产生不同结果。

建议：定义唯一排序合同：gameplay queue 只包含 Source=WASM 的 commands，排序键固定为 `(shuffle_order, player_id, sequence, stable_command_index)`；source 只作为 Source Gate/audit 字段，不参与 gameplay 排序。Admin/RuleMod/Deploy 若能改变世界，必须有独立阶段和 TickTrace event 类型，不与 WASM command queue 混排。

### A3 — High — TickTrace 写入失败语义前后矛盾：既说 tick 成功但审计不完整，又说同事务保证无缺口

`01-tick-protocol.md` §6.1 失败矩阵写：TickTrace write fail 时 “tick 执行完成，审计不完整”，Replay write fail 可从 keyframe 重建。后续 §6.3.4 又写 TickTrace 与 tick 执行同一 FDB 事务，要么都成功，要么都失败；连续失败则 tick 放弃，不存在“世界状态已变但无审计记录”。

这不是文案小问题，而是 replay 完整性的根合同冲突。

风险：
- 如果实现者按失败矩阵允许 tick 成功但 TickTrace 缺失，`execute_deterministic(state, commands) == recorded_state` 的根基会断。
- 如果实现者按 §6.3.4 同事务，失败矩阵/监控/runbook 会误导运维继续运行不可审计 tick。

建议：冻结为强合同：authoritative TickTrace（commands/rejections/metrics/state_checksum/security events）与 state commit 同一事务；写失败 = commit 失败 = tick abandon/restore。可选 WAL 只能作为 FDB 暂不可用时的 pre-commit intent 或本地恢复辅助，不能代表“tick 已成功但稍后补审计”。若保留 replay artifact（动画 delta）异步写，必须与 authoritative TickTrace 分命名。

### A4 — Medium — RNG 合约方向正确，但 PRNG stream namespace/offset 还不够可实现

设计规定 Blake3 XOF、seed = hash(tick_number, world_seed)，并禁止 OS 熵源。这是正确方向。但文档没有完整定义随机流 namespace 与 offset 分配，例如 player shuffle、spawn room、world event、NPC AI、combat 浮动、特殊效果成功率、RuleMod `scramble_commands` 是否共享同一流或独立 domain。

风险：不同实现只要调用随机数的顺序不同，就会导致同一 seed 下后续所有随机结果偏移。新增系统、优化并行、跳过空事件都可能改变 RNG consumption order。

建议：把 RNG 从“顺序消费流”改为“domain-separated random access”：`rng_u64(domain, tick, entity_id/player_id/event_type, local_index)`，每个系统有固定 domain string，禁止跨系统共享 cursor。TickTrace 记录 `world_seed_epoch` 和可选 domain version，不记录每个随机值。这样新增一个系统不会改变既有系统随机序列。

### A5 — High — RuleMod / Rhai 动态 handler 的确定性边界仍偏宽，容易成为第二套引擎

`07-world-rules.md` 已经做了很多限制：RhaiActionBuffer、AST 节点预算、签名、能力白名单、不能直接写 ECS。但同一文档后面仍允许规则 System “修改 ECS 资源/组件”，允许 `actions.register_action_handler` 注册全新 handler，允许 `set_entity_flag`/world param/effects。`08-api-idl.md` 还说需全新 handler 时通过 Rhai 模组注册。

风险：
- 这会把 determinism 合同从 Rust core 扩散到脚本生态；脚本 handler 的 ordering、数据访问、异常、版本锁定、manifest hash、replay schema 都必须和 core 一样严格，否则就是“第二套引擎”。
- `special_param = 2.0`、`default_resistance = 1.0`、`decay_rate = 0.001` 等 float 表达出现在 world.toml/mod.toml 示例中，虽然 01 禁用 f64/要求定点数，但这里没有统一禁止，会造成跨语言/解析器差异。

建议：Phase 1 冻结为“Rhai 只能声明/调度已存在 deterministic capabilities，不能注册新 apply handler”。全新 handler 必须 Rust 实现 + IDL/codegen + manifest hash + replay schema 版本。所有 world.toml/mod.toml 数值类型统一为 integer 或 fixed decimal string/`fixed<u32,N>`，禁止 float literal 作为权威配置。

### A6 — Medium — Security epoch bump 的运行中模块状态机需要更精确的 tick 边界

文档已规定 epoch bump 事件写入 FDB/TickTrace，Replay 使用记录事件，不用 wall clock，这是正确方向。但 “Engine 收到 bump 通知后立即更新 CRL 缓存”“paused_security 立即暂停”“needs_revalidation 后台队列” 仍以控制面实时事件表达，没有明确映射到 tick phase。

风险：同一个 bump 若发生在 COLLECT 中、EXECUTE 前、FDB retry 中，不同节点/重启/replay 可能判断本 tick 模块是否应执行不同。

建议：所有 security epoch bump 必须转化为 tick-bound event：`SecurityEpochBump{observed_at_server_time, effective_tick, reason, affected_module_hashes, policy}`。若在 COLLECT 已开始后收到，则最早 `N+1` 生效，除非进入 emergency pause 模式并明确 tick N abandon。Replay 只看 `effective_tick`。

### A7 — Medium — Crash/timeout/fuel refund 语义仍有一处不一致，会影响经济和 replay 指标

`01-tick-protocol.md` §3.3 说 fuel/wall-clock 耗尽 → 完整输出丢弃，不计 refund；§8.2 也说 COLLECT 超限不退还。§6.1 里 COLLECT crash 写“不退 fuel”，Phase 2a panic/OOM 写“已消耗 fuel 不退，已执行玩家空 tick”，但 FDB commit fail 写 CPU fuel 退还。整体方向合理。

问题是 Phase 2a panic/OOM 如果发生在 inline apply 中，文档既说 Bevy snapshot 恢复、tick 放弃，又说“已执行玩家空 tick”。tick 放弃意味着世界状态不变且同 tick 重试；“已执行玩家空 tick”像是 tick 成功但玩家被惩罚。这会影响 fuel ledger 和 TickTrace。

建议：把失败分为两类：
- player-local failure（WASM timeout/crash/invalid output）：tick 继续，该玩家 0 commands，不退。
- engine-global failure（Phase 2a panic/OOM/FDB commit fail）：tick abandon，restore snapshot；若重试复用 COLLECT，则 fuel ledger 只在最终 commit 成功时结算，最终 abandon 则全部退还或明确记录不退，但不能同时说“空 tick”。

### A8 — Low — Tier 2/Tier 3 文档把候选方案放进协议正文，容易被误实现为已冻结合同

T2/T3 已标记 Phase 1+ entry gate，且列出待定项，这是诚实的。但正文仍有“推荐方案 A”“候选 Jump Hash”“两阶段 combat 延迟 1 tick”等表述，读起来像可实现规范。

风险：下游实现者可能在没有冻结全局 TickTrace merge、dynamic rebalance、cross-shard replay chain 前开始做分片；这类系统后补 determinism 通常代价极高。

建议：Phase 1 文档明确标注 T2/T3 为 non-authoritative appendix。进入实现前必须另开冻结评审，特别是 global tick barrier、shard_order 稳定性、room migration pause semantics、multi-shard TickTrace canonical merge。

### A9 — Low — 部分 API/限制数字重复且不一致，可能导致生成代码和手写文档分叉

例子：`02-command-validation.md` 顶部 schema `maxItems: 100`，随后写数组长度 ≤ `MAX_COMMANDS_PER_PLAYER (500)`；同文 §6 又有单批 1MB，而 01/04 多处是输出 JSON 256KB。CVE SLA 中 Critical 为 24h，而 04-wasm-sandbox 中仍写 72h。

风险：这些不是核心架构问题，但会让 SDK、validator、docs、CI 使用不同阈值，形成“本地 dry-run 通过、线上 tick 拒绝”的体验。

建议：预算/限制只保留一个 source of truth（建议 01 §8 tick budget + CVE-SLA），其他文档引用，不重复写数值。IDL/codegen 应从同一常量表生成 JSON schema 和 docs。

## Missing

- 缺少一份 `DETERMINISM-CONTRACT.md` 或等价章节，集中定义：tick phase、command queue、RNG domain、state checksum canonicalization、TickTrace authoritative fields、replay inputs/outputs、security event effective_tick。
- 缺少 canonical serialization 规范：世界状态 `state_checksum` 需要定义 entity/component/resource 的排序、编码、整数端序、fixed decimal 编码、字符串 normalization、map ordering。
- 缺少 RNG domain registry：每个系统的 domain string、输入 key、local_index 语义、是否允许新增 domain、manifest/replay 版本如何升级。
- 缺少 deploy activation ledger：`accepted_tick`、`compiled_tick`、`activation_tick`、`module_slot`、`module_hash`、`manifest_hash`、`security_epoch` 应成为 TickTrace 一等事件。
- 缺少 security epoch/revocation 的 tick-bound 状态机：特别是 COLLECT 期间收到 bump、FDB retry、重启恢复、replay 的边界。
- 缺少 RuleMod deterministic subset spec：禁止 float、禁止非 deterministic iteration、action buffer canonical sort、handler 注册边界、manifest hash 与 replay schema 的关系。
- 缺少 authoritative vs derived replay artifact 的命名边界：TickTrace、animation delta、player explanation、debug/admin trace 应分层，避免审计日志和展示日志混用。

## Phase Ordering

1. 先冻结 Determinism Contract：统一部署生效 tick、gameplay command sorting、TickTrace 同事务语义、engine-global failure refund 语义。
2. 冻结 RNG 与 state checksum：domain-separated RNG、canonical state serialization、fixed-point-only 配置编码。
3. 冻结 security epoch/revocation tick-bound 状态机：所有 bump/revoke 都落为 TickTrace event，并定义 `effective_tick`。
4. 冻结 RuleMod 最小确定性子集：Phase 1 只允许声明式能力和内置 handler；全新 handler 推迟到单独评审。
5. 再实现 Phase 1 单节点 Tier 1：WASM sandbox、Source Gate、command validation、full snapshot、authoritative TickTrace、replay verifier。
6. 最后再进入 T2/T3：增量快照和分片必须以 Phase 1 replay verifier 作为 oracle，且 T2/T3 文档需单独冻结后再实现。
