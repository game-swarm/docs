# R11 — rev-gpt-architect 架构评审

Reviewer: rev-gpt-architect
Scope: `/data/swarm/docs/design/DESIGN.md`, `tech-choices.md`, `ROADMAP.md`, `specs/p0/*.md`
Perspective: 架构相似性、失败模式、接口直觉性、抽象层次、阶段切分

---

## Verdict

**APPROVE_WITH_RESERVATIONS / 接近可冻结，但不建议直接进入大规模实现。**

整体方向是正确的：Swarm 已经把上一轮最容易炸的核心边界收敛清楚了——**MCP 不是 gameplay channel，唯一执行器是 WasmSandboxExecutor，mutating gameplay 统一走 deferred Command，Source Gate 显式建模，visibility 有统一函数，Game API 有 IDL 单一真相**。这些是成功架构的骨架。

但当前文档仍存在一类典型的“设计看起来完整，落地时会互相打架”的问题：

1. **Phase ordering 与规范状态不一致**：很多 Phase 1 验收依赖 FDB、MCP、P0-2、P0-4，而对应规范标注 Phase 2/3；这会导致实现团队不知道先做 thin vertical slice 还是先搭完整分布式系统。
2. **动态资源与早期 Command spec 仍有硬编码 Energy 痕迹**：DESIGN/P0-8 走动态 ResourceRegistry，但 P0-2、部分示例、错误码和 validator 仍按 Screeps 式 Energy 写死。
3. **Tick 原子性边界仍混杂**：P0-1 同时说 EXECUTE 阶段 FDB 事务、BROADCAST 阶段 FDB 原子提交、Phase 3 才做 FDB 持久化；这是实现时最容易产生“内存状态已变但持久化失败”的 bug 区域。
4. **可配置规则系统有能力边界漂移**：Rhai actions 被定义为“不可绕过 Command Validation Pipeline”，但 P0-7 又写“规则 System 可在 Command 执行后补充 / 手动控制追加 / 修改 ECS 组件”。这会腐蚀 replay determinism 和安全审计。

我的建议：**不要推翻设计；做一次 R11.5 文档收敛 pass**，专门修正这些跨文档合同冲突，再进入 Phase 1。Phase 1 应收缩为单机、内存/FDB-lite、单玩家、最小 API 的“可玩且可回放”切片，而不是把 Phase 2/3 的分布式与完整 MCP 也背进去。

---

## Strengths

### S1. MCP 定位已经从根上避免了“AI 特权通道”失败模式

`DESIGN.md §4`、P0-3、P0-9 都明确：MCP 是 AI 的屏幕和鼠标，不提供 `swarm_move` / `swarm_attack` / `swarm_build`。AI 与人类都必须部署 WASM，世界只认 WASM。

这非常关键。很多 AI game/server 架构会不自觉给 AI 一个 action API，然后再靠权限补丁维持公平；这种模式后期几乎必炸。Swarm 现在采用的是更干净的模型：

```
Human / AI author code → compile WASM → WasmSandboxExecutor → Command[] → Validator → ECS
```

公平性、审计、资源计量都自然集中到同一条路径。

### S2. Source Gate + Command Source Model 是优秀的防“客户端自报权限”设计

P0-9 把 WASM、MCP_Deploy、MCP_Query、Admin、Replay、TestHarness、Tutorial、RuleMod、Simulate、DryRun、Rollback、Deploy 都显式列出，并要求 actor/capability/scope 由服务端注入。

这比“每个 endpoint 自己检查权限”可靠得多。新人也容易理解：

- gameplay 默认只来自 `WASM`
- MCP 不提交 gameplay command
- client 自报 player_id 无效
- Replay/TestHarness/Admin 是显式来源，不是假装玩家

### S3. Deferred Command Model 是适合确定性 MMO RTS 的正确抽象

`tick(snapshot) → Command[]` 比 imperative host function 更适合：

- collect 可并行
- execute 可排序、重放、审计
- conflict resolution 可解释
- WASM 侧语言无关
- 回放可以记录 Command 而非重跑 WASM

这和 Screeps 的同步 JS API 很不同，但更适合 WASM + multi-language + deterministic replay。

### S4. 统一 Visibility Policy 把常见泄漏面纳入同一个合同

P0-5 的价值不在于规则本身，而在于“所有输出面都调用同一个 `is_visible_to` / cache”的架构约束。snapshot、MCP、WebSocket、REST、replay、spectator 都列出，是正确的安全边界设计。

### S5. IDL 单一真相方向正确

P0-8 要求 `game_api.idl` 同时生成 Rust Command enum、Validator trait、TS SDK、MCP schema、Docs、Property tests。这个抽象非常必要，否则 deferred command + 多 SDK + MCP schema 必然漂移。

### S6. 技术选型大体务实

- Rust + Bevy ECS：适合确定性核心和 headless simulation。
- Wasmtime：fuel metering 与 epoch interruption 是关键硬需求。
- NATS：tick delta 推送不需要 Kafka 级别复杂度。
- ClickHouse：tick metrics / audit analytics 匹配列式 OLAP。
- Rhai：作为可信服主规则层，比让服主写 WASM 更轻。

FoundationDB 是最大运维赌注，但设计意图（每 tick 原子提交、严格可序列化、replay 哲学）成立。

---

## Concerns

### A1 [Critical] Phase 1 的交付物与规范状态/技术依赖冲突，会导致实现顺序失控

ROADMAP Phase 1 写的是“单人垂直切片”，但交付物包括：

- P0-2 Command Validation Pipeline（规范标注 Phase 2）
- P0-4 WASM Sandbox baseline（规范标注 Phase 2）
- P0-1 TickTrace + replay（涉及 FDB 写入）
- MCP Server 脚手架（P0-3 Phase 1-2）
- Docker Compose: engine + FDB + NATS

同时 Phase 3 才写 FoundationDB 持久化、Dragonfly、ClickHouse。

这会产生一个典型失败模式：团队为了满足 Phase 1 验收，不得不提前搭 FDB/NATS/MCP/完整 validator，结果 MVP 变成 mini-production，4-6 周不可控。

建议：

- Phase 1 改成 **single-process deterministic vertical slice**：Bevy world + in-memory TickTrace + WASM sandbox + 5 commands + local replay。
- FDB/NATS/MCP 完整化后移到 Phase 2/3。
- Phase 1 只保留 `swarm_get_snapshot` / `swarm_deploy` 的 mock/local MCP 或 CLI 等价入口，不要求完整 auth/rate-limit/audit。

Severity: Critical because it directly threatens schedule and implementation focus.

### A2 [Critical] Tick 原子性在文档中有三种互相冲突的落点

冲突点：

- DESIGN §3.2：EXECUTE 中 `FDB 原子提交`。
- P0-1 状态机图：BROADCAST 阶段步骤包含 `FDB 原子提交`。
- P0-1 §3.4：整个 EXECUTE 包裹在 FoundationDB 事务中。
- P0-1 §4.2：BROADCAST 读取已提交 tick result。
- ROADMAP：FDB 持久化是 Phase 3 交付物。

这不是文字小问题，而是权威状态边界问题。若实现者按状态机图把 FDB commit 放入 BROADCAST，就会出现：ECS 已执行、delta 已计算，但 commit 失败时世界如何回滚？若按 §3.4，则 BROADCAST 永不回滚，语义清楚。

建议裁决：

- Tick state mutation + FDB commit 属于 EXECUTE。
- BROADCAST 只做 post-commit side effects：Dragonfly update + NATS publish + WS fanout。
- Phase 1 若无 FDB，则定义 `DurableTickStore` trait，用 in-memory/file backend；Phase 3 替换为 FDB backend。
- 删除/修正状态机图中 BROADCAST 的 “FDB 原子提交”。

Severity: Critical because this is replay correctness and data consistency core.

### A3 [High] 动态资源模型与 P0-2/P0-8/P0-7 仍有硬编码 Energy 不一致

DESIGN §8 强调核心引擎不硬编码 Energy，资源由 `ResourceRegistry` 决定；P0-8 也把 `ResourceName` / `ResourceCost` 引入 IDL。

但 P0-2 仍大量写死：

- Harvest: `target.source.energy > 0`
- Build/Repair/Spawn: `InsufficientEnergy`
- Spawn: `body_cost(body) ≤ spawn.energy`
- Recycle: “返还 50% 身体部件成本作为能量给 spawn”

P0-8 的 `body_cost` 默认表也是 Energy-only，虽然允许 world.toml 覆盖，但错误码/validator 语义还没完全资源泛化。

这会在实现时产生两套经济模型：

- Registry-driven dynamic resource
- Energy-special-case command validation

建议：

- P0-2 中所有 `energy` 改为 `resource` / `ResourceCost` / `ResourceStore`。
- 错误码统一为 `InsufficientResource { resource, required, available }`，不要同时存在 `InsufficientEnergy` / `InsufficientResources`。
- `Spawn.energy` 改为 `Spawn.local_store` 或 `StructureResourceStore`。
- Recycle refund 返回 `ResourceCost`，目标 store 由规则决定。

Severity: High because this会导致核心数据模型返工。

### A4 [High] RuleMod / Rhai 能力边界仍不够硬，存在绕过 Command Pipeline 的结构性风险

DESIGN 与 P0-9 说 RuleMod 只能经济 + 事件，P0-7 又说：

- 规则 System 可在 Command 执行后补充
- 示例中出现“如手动控制追加”
- 可修改 ECS 资源/组件
- actions 可以 `damage_entity`, `set_entity_flag`, `award_resource`, `deduct_resource`

这类能力如果不归入一个明确的 `RuleAction` validator，就会变成第二条 mutating pipeline。历史上 mod/plugin 系统最容易出的问题就是“核心规则很严，插件直接改内存”。

建议：

- 明确 Rhai 不直接改 ECS World，只能 emit `RuleAction[]`。
- `RuleAction[]` 进入 `RuleActionValidator`，写入 TickTrace，参与 replay checksum。
- 删除 P0-7 “手动控制追加”措辞，因为它与“manual_control 已删除”和“不可绕过 Command Validation Pipeline”冲突。
- 为每个 RuleAction 定义 capability：Economy、StatusEffect、Event、SpawnModifier、VisibilityModifier 等，不要给通用 `modify_entity` 回潮空间。

Severity: High because mod layer一旦成为隐式 privileged mutator，后期安全与回放都难修。

### A5 [High] WASM ABI 仍缺少可实现的内存返回协议

P0-4 / DESIGN 写 `tick(ptr, len) -> i32`，返回值是指令 JSON 指针；但没有定义：

- 返回 JSON 长度如何获得
- WASM 分配/释放函数名
- host 如何把 snapshot 写入线性内存（由谁分配 buffer）
- pointer/len 的 ownership
- 错误返回与 panic/invalid pointer 的区别
- string encoding 是否固定 UTF-8

只写 `i32 pointer` 会让每个 SDK 自行发明 ABI，IDL 也无法真正生成绑定。

建议在 P0-8 加 ABI section：

```
export alloc(len: i32) -> i32
export dealloc(ptr: i32, len: i32)
export tick(snapshot_ptr: i32, snapshot_len: i32) -> i64
// high 32 bits = ptr, low 32 bits = len, or write result into host-provided out buffer
```

或者采用 host-provided output buffer / canonical ABI 风格。无论选哪种，必须冻结。

Severity: High because ABI 不冻结会直接阻断 SDK/codegen。

### A6 [High] “每 tick fork → kill”与性能目标/模块缓存/TS SDK之间存在现实张力

P0-4 说每 tick 新 fork、执行一个玩家、返回指令、kill。优点是隔离强，但对目标规模有压力：每引擎实例 500 AI/player、3s tick、Wasmtime instantiation、TS-generated WASM 可能更重。

虽然文档写模块缓存按 `(module_hash, wasmtime_version)` 缓存，但仍需明确：缓存的是 compiled Module 还是 worker process？如果每 tick per-player fork + instantiate，500 玩家下 fork/IPC/instantiate overhead 可能成为主成本，而不是 fuel。

建议：

- Phase 1 benchmark gate：测量 100/500 wasm modules 的 collect p50/p95。
- 把 sandbox 生命周期拆成两个可选 profile：
  - `strict_fork_per_tick`：安全优先，早期默认
  - `pooled_worker_per_player`：生产优化，强制 reset store/instance，定期 recycle
- 文档明确 compiled module cache、instance cache、process pool 分别是否允许。

Severity: High because它可能推翻 tick budget 假设。

### A7 [Medium] P0 文档“状态”标签不一致，给工程管理信号混乱

例子：

- DESIGN Phase 0 标记完成。
- P0-1 状态是 Phase 2 阻断项。
- P0-2 状态 Frozen for Phase 0 / 实现 Phase 2。
- P0-4 状态 Frozen for Phase 0 / 实现 Phase 2。
- P0-7 状态 Phase 1 设计基础。
- ROADMAP Phase 1 又依赖 P0-1/P0-2/P0-4/P0-8。

建议统一两个字段：

```
Design status: Draft | Frozen | Superseded
Implementation phase: P1 | P2 | P3
Blocks: P1-start | P2-start | P3-start
```

Severity: Medium, but if不修会放大 A1。

### A8 [Medium] P0-5 中 `player_view = full` 允许 MCP 玩家屏幕全图，可能重新引入 AI 信息不对称

P0-5 说 `player_view` 只影响人类屏幕和 MCP 只读查询，不影响 WASM snapshot。这在 tutorial/co-op 可能没问题，但在 World 中若服主开启 `player_view=full`，AI 通过 MCP 可以全图分析并改代码，人类也许屏幕可全图，但 AI 的处理能力使其战略优势远大于人类。

这不是安全 bug，而是 gameplay/fairness policy。建议：

- World 默认禁止 `player_view=full`，只允许 Tutorial / private / co-op。
- 若开启，世界标记为 `non-competitive`，排行榜/成就隔离。
- MCP `swarm_get_snapshot` 与 “screen query” 分离命名，避免 AI 把 screen-only full map 当作 bot strategy input 的事实标准。

Severity: Medium.

### A9 [Medium] IDL 只定义 Command/host/MCP schema，但没有定义 Snapshot schema 的单一真相

P0-8 强调 IDL 生成 Command、host function、SDK、MCP、Docs，但玩家代码最常消费的是 `Snapshot`。P0-5/P0-6/P0-3 中各自有 snapshot 示例，字段不完全一致。

建议把 Snapshot、Entity components、Visibility-redacted views 也纳入 IDL 或另一个 schema：

- `WorldSnapshot`
- `VisibleEntity`
- `SelfEntityDetail`
- `SpectatorEntity`
- `TickExplanation`
- `RejectionDetail`

Severity: Medium because schema drift 会首先伤害 SDK 和 AI agent 体验。

### A10 [Medium] Tech choice 中 FoundationDB 的正确性理由成立，但运维/开发替代路径不足

FDB 是强选择，但对开源游戏项目是高门槛依赖。ROADMAP Phase 1 就要求 docker-compose 启动 FDB；新人 10 分钟看到 drone 动，这和 FDB cluster 运维体验有冲突。

建议：

- 定义 `TickStore` abstraction。
- Phase 1 默认 SQLite 或 append-only file store；Phase 3 才引入 FDB。
- CI 分两层：fast deterministic tests 用 in-memory/file；integration 用 FDB。

Severity: Medium.

### A11 [Low] 文档章节编号与命名有少量一致性问题

例如 DESIGN §11 下出现 “### 10.2 代码规范”；P0-1 有两个 `### 3.3`。这不影响架构，但冻结文档前应修。

Severity: Low.

---

## Missing

### M1. 缺少一页“权威合同索引”

现在合同分散在 DESIGN、P0-1 到 P0-9、tech-choices、ROADMAP。建议新增 `ARCHITECTURE-CONTRACTS.md` 或 DESIGN 附录，列出：

- Mutating gameplay only from WASM Command[]
- MCP no gameplay actions
- Source Gate before Validator
- EXECUTE owns atomic commit
- BROADCAST never rolls back tick
- Snapshot schema source of truth
- RuleMod only emits validated RuleAction[]
- Dynamic resources: no Energy special-case in core

这会极大降低新人误读概率。

### M2. 缺少 MVP 最小 Command 集的精确定义

ROADMAP Phase 1 写 Move/Harvest/Build/Spawn/Transfer 5 指令，但 P0-8 还包括 MoveTo/Withdraw/Repair/Attack/RangedAttack/Heal/Recycle/GlobalStorage commands。

建议标注每个 Command 的 `introduced_in_phase`。

### M3. 缺少 Sandbox ABI 规范

见 A5。需要冻结 alloc/dealloc/result length/error protocol。

### M4. 缺少 deterministic test matrix

已有方向，但需要更明确的 matrix：

- same commands same checksum
- command order shuffle deterministic
- RuleAction replay deterministic
- visibility cache no leak across outputs
- FDB commit fail restores Bevy snapshot
- invalid WASM output no refund
- contention refund capped

### M5. 缺少 “local-first developer mode”

如果 Phase 1 就要求 FDB/NATS/OAuth/MCP，贡献门槛偏高。需要官方 `swarm dev --local` 或 docker compose minimal profile。

### M6. 缺少 schema/version migration policy

P0-8 有 `abi_version`，但世界状态、TickTrace、snapshot schema、RuleMod config version 如何迁移还没写。持久世界项目必须提前定义 migration strategy。

---

## Phase Ordering

### 建议的修订阶段顺序

#### Phase 0.5: 文档收敛 / Contract hardening（建议 2-4 天）

必须先修：

1. 修 P0-1 Tick commit 所属阶段：EXECUTE commit，BROADCAST post-commit only。
2. 修 ROADMAP Phase 1：去掉对 FDB/NATS/完整 MCP/auth 的硬依赖。
3. 修 P0-2 Energy hardcoding，与 P0-8 ResourceRegistry 对齐。
4. 修 P0-7 RuleMod 能力边界：RuleAction[] + validator + TickTrace。
5. 补 P0-8 WASM ABI：alloc/dealloc/result length/error。
6. 给每个 P0 文档统一 `Design status / Implementation phase / Blocks`。

#### Phase 1: Local deterministic vertical slice

目标：一个玩家、本地单进程、可运行 1000 tick、可 replay。

保留：

- Bevy ECS minimal world
- Wasmtime sandbox minimal viable
- Move/Harvest/Build/Spawn/Transfer
- Dynamic ResourceStore 但默认 Energy
- In-memory/file TickTrace
- TS starter bot
- CLI deploy 或 local MCP stub

推迟：

- FDB cluster
- NATS
- Dragonfly
- ClickHouse
- full OAuth2 / Ed25519 cert flow
- full MCP tool suite
- Rhai mods

#### Phase 2: Multi-player + Source Gate + Visibility + real MCP

目标：多人公平性与 AI/human parity。

加入：

- parallel COLLECT
- seeded shuffle
- Source Gate 12 sources 的核心子集
- real MCP query/deploy/debug
- visibility cache over snapshot/MCP/WS
- NATS/WebSocket delta

#### Phase 3: Persistence + FDB + audit stores

目标：权威持久化和 replay durability。

加入：

- FDB TickStore backend
- Dragonfly read cache
- ClickHouse metrics/audit
- commit failure / Bevy restore tests

#### Phase 4: RuleMod / Rhai + world configurability

目标：可配置世界，但必须在 RuleAction validator 已经稳定后上。

加入：

- Rhai execution budget
- RuleAction[] validation
- mod config schema/i18n
- empire-upkeep official mod

#### Phase 5+: Web UX / Tutorial / Replay viewer / Arena / Production

Web 客户端和教程可在 Phase 2 后并行推进，但 Arena、market、combat、public replay 应等 visibility + replay + persistence 稳定后再做。

---

## Final Recommendation

**架构方向保留，先做 R11.5 文档修正再开 Phase 1。**

我不会要求大改核心方案；现在的问题不是“方向错”，而是“多个正确局部还没完全拧成一个可执行合同”。如果现在直接实现，最可能炸在：

1. Tick commit/rollback 边界；
2. Phase 1 scope 膨胀；
3. Energy hardcoding 返工；
4. RuleMod 绕过 validator；
5. WASM ABI 各 SDK 分裂。

把这五点修掉后，Swarm 的架构就从“漂亮的愿景设计”进入“可实施的工程合同”。
