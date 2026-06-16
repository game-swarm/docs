# R4 Clean-Slate Architecture Review — rev-gpt-architect

## Verdict

CONDITIONAL_APPROVE

整体方向值得继续：Swarm 把 Screeps 式“代码即军队”升级为 WASM + ECS + 可回放确定性模拟，这个主轴清晰，关键安全边界（MCP 不直接下游戏动作、WASM deferred command、可见性统一过滤、Source Gate 注入身份）也比常见“先把 API 暴露出去再补安全”的设计成熟得多。

但当前文档仍有几处“看起来很完整、实现时会炸”的架构问题：尤其是全世界单事务 tick、动态规则/IDL/SDK 的边界、Rhai 隔离模型、MCP 信息通道与 WASM 公平性、以及规格内部多个硬限制不一致。建议进入实现前先收敛为一个更小、更硬的 MVP 内核：Vanilla Core + 单世界单引擎 + 可回放 tick + MCP/WASM 同等只读视图；把 Layer 3 模组、动态 SDK、复杂特殊攻击、联邦宇宙和大规模分片延后。

## Strengths

1. 核心抽象方向正确
   - “AI 与人类都必须部署 WASM；MCP 只负责观察、部署、调试，不负责 move/attack/build”是一个强边界，能避免 AI 入口变成第二套作弊 API。
   - deferred command model 也正确：WASM 返回 CommandIntent，由服务端注入 player_id/tick/source，再进入同一校验管线。这个模式比 mutating host function 更容易审计、回放和限流。

2. 确定性被当作一等需求，而不是事后补丁
   - 文档明确了 Blake3 XOF PRNG、IndexMap、整数/定点数、TickTrace、Command 记录而非 WASM 重放、FDB rollback 时恢复 Bevy World snapshot。
   - 这接近成功的 simulation/server-authoritative 游戏架构，而不是普通 Web CRUD 架构。

3. 可见性策略基本有统一入口
   - `is_visible_to(entity, player_id, tick)` 作为所有输出面共同函数，是正确抽象。
   - 明确“调试数据也不能绕过可见性”是很重要的经验，很多多人游戏和 AI 工具系统的信息泄露都发生在 debug/replay/profile 侧。

4. Source Gate / Auth Context 设计方向健康
   - 客户端不能自报 player_id/source/tick；服务端注入 envelope。
   - 部署签名加入 domain、module_hash、world_id、slot、nonce、expires_at，能抵抗常见重放和跨协议混淆。

5. 文档覆盖了运营现实
   - 有 CVE SLA、CRL/epoch、audit truncation、simulate caps、DNS rebinding、CSRF/Origin 与 agent endpoint 分离，这些不是玩具设计。

## Concerns

### A1 — High — “每世界单 Engine + 全 tick 单 FDB 原子事务”是 MVP 友好，但扩展边界没有被架构化

当前设计在单世界内使用 Bevy World 作为工作副本，EXECUTE 后把整个 tick 结果原子提交到 FoundationDB。MVP 500 活跃玩家可以尝试，但文档同时承诺 1,000-5,000 玩家、未来水平分片、联邦宇宙、跨房间移动、9 房间可见快照、全量 replay/keyframe/delta。这些扩展点现在多是声明，没有形成真正的分区边界。

风险模式：
- tick 事务写集合随世界实体增长而膨胀，FDB 冲突/提交延迟会直接影响 3s tick SLA。
- Phase 2a inline 顺序让跨房间/跨区域资源竞争天然全局排序，后续拆 shard 会很痛。
- Bevy World snapshot rollback 如果是全世界深拷贝，会在实体数上来后成为隐藏 O(world) 成本。
- “每个世界一个 Engine 实例”与“单世界无限扩展房间”之间缺少 room/region ownership 模型。

建议：
- MVP 明确只支持 single-region world，写清实体/房间/player 上限，不要暗示无缝扩展。
- 现在就定义 Region/RoomPartition 边界：tick 内跨 partition 的移动/攻击/可见性如何排序，哪些操作必须同 partition，哪些走下一 tick mailbox。
- FDB keyspace 需要按 world_id/region_id/room_id 分层，并规定提交粒度：全世界事务、region 事务、还是 tick coordinator + room transactions。
- Bevy rollback 需要从“深拷贝 World”降级为 write-ahead component journal 或 archetype-level delta snapshot，否则后续性能风险很大。

### A2 — High — “核心引擎不硬编码规则”与“动态 CommandAction/IDL/SDK”边界过度理想化

文档多处说核心引擎只提供 validation + execution pipeline，规则全部 world.toml/Rhai 配置；但同时又要求：
- 新 CommandAction 需要注册 validate/apply handler + IDL 暴露。
- Core IDL 中已经列入 Hack/Drain/Overload/Debilitate/Fortify 等特殊攻击。
- World Action Manifest 又说这些由 world.toml `[[custom_actions]]` 动态生成。
- Rhai 可以注册 handler，但 Source Model 又限制 RuleMod 不能触发战斗，只能能力白名单。

这是一种常见失败模式：为了“可扩展”，把类型系统、协议、SDK、运行时校验、回放 determinism 都变成动态系统，结果 MVP 复杂度爆炸。

建议：
- 明确三层：
  1. Core ABI：Move/Harvest/Transfer/Build/Attack/Heal/Spawn/Recycle/ClaimController，冻结。
  2. Vanilla Extensions：特殊攻击作为内置但可开关的 compile-time known actions，不在 MVP 支持任意新增 action。
  3. Experimental Layer 3：world-specific SDK + dynamic manifest，推迟到 Core 稳定后。
- MVP 不要允许 Rhai 注册全新 gameplay handler。Rhai 只能调参、触发有限资源/事件/状态 flag。
- “新增 CommandAction 无需改 Rust”与“需要新 handler”二选一。前者只能适用于有限内置 effect DSL；后者就是需要代码扩展。

### A3 — High — Rhai 模组信任与隔离模型互相冲突

DESIGN 中说 Rhai 是服主信任代码、引擎进程内运行，不引入进程隔离；spec/07 又说默认 Rhai engine 运行于独立 sandbox 进程、seccomp/cgroup、签名强制，无未签名宽松模式。

这不是小差异，而是架构边界差异：
- in-process Rhai 可以直接依赖 Bevy World 访问和性能，但崩溃/资源耗尽风险更高。
- out-of-process Rhai 需要稳定 IPC、状态投影、action buffer 协议、序列化成本和 determinism 处理。
- 签名强制会影响本地开发、内置模组、CI fixture、社区模组安装体验。

建议：
- 选一个默认模型。架构上我建议 MVP 用 in-process + capability-limited + deterministic op budget；把 out-of-process 作为 “untrusted third-party mod future”。
- 如果坚持 out-of-process 默认，需要新增一份 RuleMod IPC schema：输入 state projection、输出 action buffer、错误/timeout/rollback 语义、版本兼容、性能预算。
- 签名策略至少要有 dev mode，但必须 world.mode=dev 或 local-only，不能在生产世界静默启用。

### A4 — High — 规格内部已有多处 hard-limit / schema 不一致，会导致实现分叉

发现的例子：
- Tick 输出 schema `maxItems: 100`，紧接着又说 MAX_COMMANDS_PER_PLAYER = 500。
- 顶层输出总字节数一处是 256KB，批级校验又写整批 ≤1MB。
- DESIGN §5 说快照为结构化数据“非纯文本 JSON”，但 sandbox ABI/spec 多处说 tick(snapshot_json) / commands_json。
- tech-choices 说 per-tick fork 生命周期；sandbox spec 说每 tick fork；但 DESIGN 又说部署时预编译、tick 时实例化模块，二者资源模型未统一。
- Command validation §5 说可见性优先，不可见或不存在统一 `NotVisibleOrNotFound`；IDL RejectionReason 仍保留大量 `ObjectNotFound`、`TargetNotVisible`，但没有把 player-facing/admin-facing error shape 作为生成规则。
- World Rules Engine §3 的 ECS 注册顺序是 death_mark → spawn → regeneration → combat → decay → death_cleanup `.chain()`，而 Tick spec/DESIGN 说 regeneration/decay 与主线并行且 combat 在 regeneration 前。

建议：
- 设立 “Constants & Limits” 单一文档或 IDL section，所有 spec 引用，不允许复制数字。
- 设立 “Wire Format Contract”：snapshot/commands 到底是 JSON、binary structured、还是 SDK abstraction；MVP 只选一种。
- RejectionReason 分为 `InternalRejection` 与 `PlayerRejectionView`，由代码生成映射，避免信息泄露策略靠人工记忆。
- ECS schedule 只保留 specs/01 里的一个版本，其他文档删掉或引用。

### A5 — High — MCP 只读能力与 WASM 公平性的边界仍不够硬

文档说 AI 通过 MCP 看世界，与人类 Web UI 同级；又说 MCP get_snapshot 与 WASM tick 输入完全相同；但 visibility spec 也说 `player_view = full` 会影响“玩家屏幕 / MCP”，而 WASM tick 始终按 `is_visible_to` 过滤。

这会产生架构问题：AI 可以通过 MCP 获得 player_view=full 的信息，然后生成/部署新 WASM。虽然它不能直接下 move 指令，但它能把超出 drone 感知的信息编码进策略，形成间接信息通道。人类也许屏幕能看到 full map，但 AI 的“观察→生成代码→部署”自动化速度和精度不同。

建议：
- 对正式 World/Arena，MCP_Query 默认必须等价于 WASM snapshot，而不是 Web UI camera。`player_view=full` 只能用于 tutorial/co-op/admin 或明确 non-competitive 世界。
- 如果允许人类屏幕 full map，则 AI MCP 也可以 full map，但该世界必须标记为 non-ranked / non-competitive，并在规则中显式声明。
- Deploy cadence 要纳入公平性：AI 能否每 tick 观察并重部署？World 中可随时热重载，Arena 赛前锁定；但 World 里频繁 MCP 观察 + 部署可能变成外部控制回路。需要明确 `code_update_cooldown` 的默认值和 MCP deploy 限制是否足以防止“remote control by redeploy”。

### A6 — Medium — per-tick per-player fork 的隔离强，但成本模型可能不成立

每 tick、每玩家 fork sandbox worker，执行后 kill，可以避免跨 tick 状态和持久感染；但 500 活跃玩家、3s tick 下就是持续每 3s 数百次 fork/instantiate。再加上 Wasmtime store、memory limits、Unix socket、cgroup/seccomp 设置，实际开销需要验证。

这不是反对强隔离，而是需要避免把安全模型和调度模型绑死。

建议：
- MVP 需要一个 spike：500 players × minimal WASM × 3s tick，测 fork/instantiate/policy setup p99。
- 如果成本过高，考虑 warm worker pool + per tick fresh Store/Instance + memory zeroing + epoch/fuel reset，而不是 OS process 每 tick fork。
- 安全合同应定义“不保留玩家可观察状态”，不一定定义“必须 fork”。fork 是实现策略，不应成为协议承诺。

### A7 — Medium — Snapshot truncation 规则可用，但会影响玩家模型稳定性

每玩家快照 256KB，按关键桶/距离桶截断，是必要 DoS 防护。但在 RTS 中，截断本身会变成 gameplay mechanic：敌人可以用实体海制造 omitted_count，使对方策略在边界条件下退化。文档有关键桶保护，但中低优先级截断仍可能改变策略判断。

建议：
- Snapshot 必须提供稳定分页/查询机制：基础 snapshot 保证关键实体，非关键实体通过 quota query 获取，且 query 结果也有 deterministic ordering。
- `omitted_count` 需要按 bucket/type/range 细分，否则玩家无法写出稳定降级策略。
- MVP 限制实体密度，比复杂截断算法更实际。

### A8 — Medium — 数据权威源叙述较完整，但恢复流程还缺“启动/故障时间线”

文档说 COLLECT 从 Bevy 内存读，EXECUTE 修改 Bevy，提交 FDB 后 FDB 为持久权威，启动/恢复从 FDB 重建 Bevy。这是合理的。但还缺少几个实际会炸的流程：
- Engine crash 发生在 FDB commit 成功后、Dragonfly/NATS 更新前。
- Engine crash 发生在 Bevy 已修改、FDB commit 未知状态时。
- 多 Gateway 查询当前状态时，读 Bevy、Dragonfly、FDB 的版本差异如何呈现。
- TickTrace write fail 与 state commit 是否同事务；spec 表格说 TickTrace write fail 不影响 gameplay，但 determinism/replay 又依赖 TickTrace。

建议：
- 明确 tick commit record 是唯一完成标记，state/delta/commands/rejections/metrics 是否同一 FDB transaction。
- 启动恢复流程必须扫描最后 complete tick，丢弃 partial tick，重建 Bevy 与 Dragonfly，再恢复 NATS publish。
- 当前查询返回必须带 `tick` 和 `source_version`，客户端按 tick gap 自愈。

### A9 — Medium — MVP 范围仍过大，像“平台首版”而非“可玩闭环首版”

MVP 清单包含教程、人类 Web IDE、AI MCP 教程、starter bots、本地模拟、dry run、explain tick、replay viewer、strategy dashboard、Arena、锦标赛、观战解说。加上动态规则、Rhai、特殊攻击、市场、全局/本地存储，范围已经接近完整产品。

建议：
- 真 MVP 只保留：single persistent world、basic resources、spawn/harvest/transfer/build/move/attack/heal、WASM deploy、MCP snapshot/docs/deploy/explain_last_tick、minimal Web viewer、TickTrace replay CLI。
- Arena、tournament、strategy dashboard、special attacks、Rhai mods、market、global storage 都应是 Phase 2+。

### A10 — Low — 新人理解成本偏高，抽象名词过多

当前文档同时出现：Core IDL、World Action Manifest、RuleMod、custom_actions、special_effects、body_part_types、Rhai actions、Source Gate、CommandIntent/RawCommand/ValidatedCommand、player_view/fog_of_war/replay_privacy。每个都合理，但组合后新人很难判断“我改一个动作需要改哪里”。

建议：
- 增加 3 条端到端 walkthrough：
  1. 添加一个普通 Command 的修改路径。
  2. 调整一个 Vanilla body part 数值的修改路径。
  3. 添加一个 world-specific custom action 的修改路径（标注非 MVP）。
- 每条 walkthrough 明确代码生成、校验、SDK、docs、tests、replay 的影响面。

## Missing

1. Room/Region 分区模型
   - 需要定义未来 shard/region 的主权、跨区移动、跨区 combat、跨区可见性、跨区事务边界。

2. Canonical wire format
   - snapshot 和 command 输出到底是 JSON 还是二进制结构化格式，需要单一答案。

3. ECS schedule 单一真相
   - specs/01 与 specs/07 的系统顺序不一致，必须统一。

4. Full recovery runbook
   - Engine crash、FDB unknown commit、partial TickTrace、Dragonfly stale、NATS missed publish 的恢复时间线。

5. RuleMod IPC / isolation contract
   - 如果默认 out-of-process，必须定义 IPC schema；如果默认 in-process，必须删除 out-of-process 默认叙述。

6. Manifest compatibility matrix
   - world.toml 调参不改变 manifest_hash，但 cost/cooldown 调整可能改变 WASM 策略假设。需要区分 ABI compatibility 与 gameplay compatibility。

7. Performance proof points
   - per-tick fork、snapshot build/truncation、FDB commit size、WASM instantiation p99、MCP simulate caps 都需要 spike 数据。

8. Player-facing vs admin-facing error mapping
   - 可见性优先要求 opaque error，但 IDL 内部拒绝码很多。需要生成式映射，不靠实现者自觉。

9. Deploy-as-control-loop 限制
   - 对 AI agent 尤其重要：MCP observation + frequent deploy 是否构成外部实时控制，需要规则化。

10. Testing pyramid
   - 文档列了很多测试点，但还缺“哪些是 merge-blocking”：determinism replay、visibility leak matrix、malicious WASM corpus、FDB fault injection、IDL generated-code diff 应作为最低 CI 门槛。

## Phase Ordering

### Phase 0 — Spec convergence gate

目标：先让文档成为一个可实现合同。

必须完成：
- 统一 constants/limits：command count、JSON/body size、snapshot size、simulate limits。
- 统一 wire format：JSON vs binary structured。
- 统一 ECS schedule。
- 统一 Rhai isolation 默认。
- 分离 `InternalRejection` 与 `PlayerRejectionView`。
- 冻结 MVP Core IDL，特殊攻击和 Layer 3 明确延后或标为 optional。

### Phase 1 — Deterministic Vanilla Kernel

目标：跑通单世界、单引擎、可回放核心循环。

范围：
- Basic room topology。
- Spawn/Move/Harvest/Transfer/Build/Attack/Heal/Recycle/ClaimController。
- WASM deploy + deferred CommandIntent。
- Source Gate。
- TickTrace + replay checksum。
- FDB commit + Bevy rollback/recovery。
- Minimal visibility via `is_visible_to`。

不做：Rhai mods、special attacks、market、global storage、Arena、dynamic SDK。

### Phase 2 — Player feedback loop

目标：让人类和 AI 都能闭环玩起来。

范围：
- MCP get_snapshot/get_docs/get_schema/deploy/explain_last_tick。
- Minimal Web viewer + deploy UI。
- Starter bot TS/Rust。
- Local sim CLI。
- Player-facing rejection explanations。
- Visibility leak tests across snapshot/MCP/WS/REST/replay。

### Phase 3 — Scale and hardening

目标：证明 500-player MVP 可运行。

范围：
- Sandbox execution benchmark：fork vs worker pool。
- Snapshot performance and truncation tests。
- FDB fault injection and recovery runbook。
- Dragonfly/NATS gap recovery。
- cgroup/seccomp malicious WASM corpus。

### Phase 4 — Arena and replay productization

目标：把公平竞技作为独立玩法上线。

范围：
- Arena room model。
- Code lock at start。
- Symmetric map seed。
- Delayed/public replay。
- Spectator privacy contract。

### Phase 5 — Rule system and Vanilla extensions

目标：在核心稳定后引入可配置玩法。

范围：
- World.toml numeric tuning。
- Vanilla special attacks as built-in optional actions。
- Body/structure/resource configurable costs。
- Conservative in-process Rhai or clearly specified out-of-process RuleMod IPC。

### Phase 6 — Layer 3 dynamic worlds

目标：支持 world-specific SDK、custom actions、third-party mods。

范围：
- World Action Manifest canonical hash。
- SDK artifact generation/distribution。
- Mod signing/trust model。
- Experimental non-ranked MOD worlds。
- Region/shard architecture if player scale demands it。
