# R12 Review — rev-gpt-architect

Reviewer: rev-gpt-architect (GPT-5.5)
Scope: `/data/swarm/docs/design/DESIGN.md`, `design/tech-choices.md`, `design/ROADMAP.md`, `specs/p0/*.md`

## Verdict

APPROVE_WITH_RESERVATIONS。

R12 相比早期架构已经把最危险的方向性错误修正到位：MCP 不再是 gameplay action channel；WASM 是唯一 gameplay executor；可见性、Source Gate、IDL、TickTrace、sandbox baseline 都有独立 P0 合同。这是正确的主干，像 Screeps + deterministic replay + untrusted code sandbox 的现代化重建，而不是简单 Web 游戏堆栈。

但当前文档仍有一个典型“设计看起来闭环、实现时会炸”的风险：Scope 已从 MVP 架构冻结膨胀到完整游戏平台（Rhai mods、global storage、market、Arena、special attacks、multi-room、spectator/replay/privacy、auth cert、FDB/Dragonfly/ClickHouse/NATS）。如果不强制切回“可运行垂直切片优先”，团队很容易在 Phase 1 就被跨层合同和过早抽象拖死。

我的建议：P0 可冻结，但 Phase 1 必须只实现最窄 deterministic loop，并把若干 P0 合同做成 compile/test gate，而不是一次性实现全平台。

## Strengths

1. MCP 定位正确

MCP 被定义为 AI 的“屏幕和鼠标”，不提供 `swarm_move` / `swarm_attack` / `swarm_build`。AI 与人类都通过编写并部署 WASM 进入世界。这消除了此前最可能破坏公平性的“双通道玩法”。

2. 单一 gameplay executor 清晰

P0-1 明确只有 `WasmSandboxExecutor`，无 `McpPlayerExecutor`。这个边界非常关键：权限、fuel、replay、反作弊都可围绕一个执行器构建。

3. Deferred Command Model 是合适抽象

`tick(snapshot_json) -> Command[]` 比 imperative host functions 更适合 determinism、validation、replay、debug explanation。所有 mutating 操作集中到 validation/apply pipeline，比在 WASM host calls 中分散副作用更可控。

4. 可见性策略有“单函数”原则

P0-5 的 `is_visible_to(entity, player_id, tick)` 是正确的安全/公平抽象。尤其是明确 snapshot、MCP、WS、REST、replay 都不能绕过，能防住很多“只是 debug 数据所以没事”的泄露。

5. IDL 单一真相来源方向正确

P0-8 把 Command enum、Validator、host stubs、TS SDK、MCP schema、docs、test generators 绑定到 `game_api.idl`。这能显著减少 SDK/engine/MCP 文档漂移。

6. Sandbox baseline 足够严肃

Wasmtime pinned version、fuel、epoch interruption、64MB linear memory、禁止 WASI clocks/random/network/fs、seccomp/cgroup、恶意 WASM 样本库都在正确方向上。不是“用了 WASM 就安全”的天真设计。

7. Roadmap 依赖关系大体合理

Phase 1 单人垂直切片 → Phase 2 多人/MCP → Phase 3 持久化/Rhai → Phase 4 教程/回放 → Phase 5 Web → Phase 6 Arena/战斗 → Phase 7 生产化，方向上是对的。

## Concerns

### A1 — Critical — P0-2 与 P0-9 的 command auth model 仍有合同冲突

P0-2 RawCommand 示例仍包含客户端/模块可见的：

```json
{
  "player_id": 42,
  "tick": 4521,
  "sequence": 3,
  "action": {...}
}
```

并写着 `player_id` “必须匹配已认证玩家”。但 P0-9 的核心原则是：`player_id` / source / capability / scope 由服务端注入，客户端不可自报；客户端自报 player_id 必须被覆盖。

这两个说法实现时会分裂成两套行为：

- Validator 可能相信 RawCommand 中的 `player_id`；
- Source Gate 可能覆盖 `player_id`；
- replay 记录里到底记录 submitted id、effective id，还是 auth id，会变得含糊；
- 测试 harness / admin / tutorial source 更容易误用同一 RawCommand schema。

建议：P0-2 改名区分两层：

- `SubmittedCommand`: WASM 输出，只含 `sequence` + `action`，不含 `player_id`、`source`、`module_hash`。
- `AuthenticatedCommand`: Source Gate 注入 `auth_context` 后的内部结构。

Validator 只接受 `AuthenticatedCommand`。任何外部输入 schema 中都不允许 `player_id`，或允许但标记为 ignored/forbidden 并测试覆盖。

### A2 — Critical — Phase 1 交付物仍包含过多跨服务依赖，MVP 可能失焦

ROADMAP Phase 1 目标是“单人垂直切片”，但交付物已经包括：Bevy ECS、WASM sandbox、IDL codegen、Command pipeline、TickTrace replay、MCP Server 脚手架、Docker Compose、FDB、NATS、Starter Bot。按 4-6 周完成风险很高。

更危险的是：一旦 Phase 1 同时引入 FDB/NATS/MCP，团队会把大量时间花在基础设施、schema、认证和部署脚手架上，而不是验证核心 gameplay loop：snapshot → WASM → commands → validation → ECS → replay。

建议 Phase 1 拆成：

- Phase 1A: 单进程/in-memory/no network/no FDB/no NATS，只做 deterministic loop + replay checksum。
- Phase 1B: 加 TickTrace 持久化接口，但可先 SQLite/file；FDB adapter behind trait。
- Phase 1C: 再接 MCP deploy/get_snapshot 的最小只读/部署通路。

验收标准应优先是“1000 tick deterministic replay + starter bot harvest/spawn/build 成功”，不是“一键 compose 起全栈”。

### A3 — High — Tick 协议里 FDB commit 所在阶段存在文档不一致

DESIGN §3.2 写 EXECUTE 阶段包含 “FDB 原子提交”，BROADCAST 阶段更新 Dragonfly/NATS。

P0-1 状态机图则把 “FDB 原子提交” 放在 BROADCAST 阶段。

这不是文字小问题。实现中 commit boundary 决定：

- tick_counter 何时推进；
- NATS 发布是否只能在 FDB commit 成功后发生；
- commit 失败时是 abandon tick、retry same tick，还是已经执行但不广播；
- replay trace 是否可作为权威。

建议冻结一个顺序：

1. COLLECT: build snapshots + run WASM。
2. EXECUTE: validate/apply in memory，形成 candidate state + TickTrace。
3. COMMIT: FDB atomic commit state/commands/rejections/metrics/checksum。
4. PUBLISH: only after commit success，更新 Dragonfly，NATS publish。
5. ADVANCE: tick_counter = N+1。

并把 COMMIT 作为独立 phase，而不是藏在 EXECUTE 或 BROADCAST 中。

### A4 — High — “每 tick fork per player” 与 3s tick / 500 玩家目标可能冲突

P0-4 设计为 sandbox worker 每 tick 新 fork，执行一个玩家，返回指令，然后 kill。安全性强，但与 Phase 7 的 500 并发玩家、p99 tick duration < 3s 目标存在明显压力。

如果每 tick 500 players 都 fork/instantiate/load module，即使命令很少，也会被 process lifecycle、Wasmtime instantiation、cgroup/seccomp setup、Unix socket IO 拖垮。模块缓存按 `(module_hash, wasmtime_version)` 缓存能减少编译，但不能消除 instantiate/fork 成本。

建议在 P0-4 明确两档执行模式：

- Phase 1 安全优先：per-tick fork OK。
- Phase 2/生产路径：warm worker pool + per-tick Store reset / pre-instantiated module / hard kill on violation。

同时加一条早期 benchmark gate：100 players × 1000 ticks，收集 fork+instantiate overhead、p99 collect duration、timeout rate。没有这个数据，不应承诺 500 players。

### A5 — High — Determinism Contract 写得强，但外部依赖 determinism 未完全封口

文档已覆盖 Blake3、IndexMap、禁 f64、ECS `.chain()`、固定 Wasmtime version。但还有几个实现时常炸点没有明文冻结：

- JSON serialization canonical form：字段顺序、数字格式、map ordering、optional/null 缺省。
- Bevy query iteration ordering：即使用 `.chain()`，同一 system 内 query iteration order 也要稳定。
- Rhai script map iteration/order and integer overflow behavior。
- Wasmtime fuel metering 与 SIMD、优化级别、host call fuel charging 的版本敏感性。
- Cross-platform replay：是只保证同 OS/arch/container image，还是跨 Linux/macOS/CPU？

建议补一个 `Determinism Test Matrix`：同一 seed + same commands 在 CI 中跨 debug/release、不同 worker count、至少两次 fresh process replay，checksum 必须一致。若只支持 Linux x86_64 production image replay，应明确写死，不要暗示泛平台 determinism。

### A6 — High — Global storage / local storage / market 的经济模型过早复杂化

全局存储、累进税、本地隐匿性、运输时间、运输中可拦截、market terminal 规则都很有设计价值，但它们属于 mid/late game economy。现在它们已经进入 DESIGN、P0-8 commands、ROADMAP Phase 3，容易反向污染 MVP 的 Resource model。

风险：Phase 1 为了兼容未来经济系统，把每个简单 `Harvest/Transfer/Build` 都设计成复杂 resource registry + local/global/pending transfers，导致 starter loop 难实现、难调试。

建议：P0 保留资源抽象，但 Phase 1 强制默认：single resource `Energy`、local only、no global storage、no market、no tax。Global storage 在 Phase 3 作为 optional feature flag 接入，且不得影响 Phase 1 command schema 的最小可用性。

### A7 — High — World Rules/Rhai 的 capability model 与 “不能绕过 Command Validation Pipeline” 仍不够精确

P0-7 写“模组通过 actions 请求引擎操作——不能绕过 Command Validation Pipeline”，但 DESIGN §8.7 又写 `actions.deduct_resource/award_resource/damage_entity/set_entity_flag` 不进命令管线但经 mini-validator。

这两者容易让实现者误解：Rhai 到底是走完整 Command Validation，还是走独立 mini-validator？如果是后者，它本质上就是第二条 mutation pipeline。

建议把规则模组能力正式建模为：

- `RuleAction` enum，与 gameplay `Command` 分离。
- 每个 `RuleAction` 有 capability、scope、budget、determinism、audit schema。
- mini-validator 的规则和测试与 P0-2 同级，不要只在 prose 中描述。
- TickTrace 记录 RuleAction 的 before/after 或 deterministic diff。

否则未来 mod bug 会成为“合法后门”。

### A8 — Medium — API 命名与字段风格仍有漂移，会伤害新人理解

文档中同一概念存在多种命名：

- `Command[]` vs `{ "cmd": "move" }` vs `{ "action": { "type": "Move" } }`。
- `pvp` vs `pvp_enabled`。
- `damage` vs `damage_multiplier`。
- `source_regeneration` vs `source_regeneration_rate`。
- `memory_size` 与 P0-7 的 1024、DESIGN example 的 2048。
- `Transfer` IDL 是单 resource + amount，DESIGN TS 示例用 `resources: { Energy: 100, Matter: 50 }`。

这些在设计阶段看起来无害，实现后会导致 SDK、IDL、docs、tests 反复漂移。

建议：P0-8 的 IDL 是唯一权威后，所有 prose 示例必须从 IDL 生成或至少 lint。手写示例只允许伪代码并明确标注 `illustrative only`。

### A9 — Medium — Tech choices 中 Blake3 MAC “代码签名”表述容易误导

tech-choices §8 把 Blake3 MAC 列在“代码签名”，同时 §9 又选 Ed25519 用于证书。P0-3/P0-9 里部署 WASM 是“证书 + 私钥签名 Blake3(WASM bytes)”。

Blake3 keyed hash 是 MAC，不是 public-key signature。它适合服务端内部认证，不适合客户端对服务端证明“我持有某私钥”，除非共享 secret，这不符合客户端分发模型。

建议文档统一：

- `module_hash = Blake3(wasm_bytes)` 用于内容寻址/cache/replay。
- `deploy_signature = Ed25519.sign(module_hash)` 用于客户端证明。
- Blake3 keyed hash 仅用于 server-side token/MAC，如确实需要。

### A10 — Medium — Visibility policy 对 `player_view = full` + MCP 的公平边界需要更硬

P0-5 说 `player_view = full` 只影响玩家屏幕和 MCP 只读查询，WASM snapshot 仍按 `is_visible_to`。这在“人类看全图但代码看不到全图”的世界里会产生旁路：人类或 AI 可以看全图后把信息写进下一版 WASM 策略，间接突破 drone 感知。

如果 `player_view=full` 是 tutorial/co-op/admin 场景，没问题；如果 persistent competitive world 允许它，就不是单纯 UI 设置，而是 gameplay rule。

建议：把 `player_view=full` 标为 non-competitive world only；World PvP 默认禁止；Arena 禁止赛中 full MCP/view，只允许赛后 delayed replay。

### A11 — Medium — Special attacks 和 damage type 系统明显超出当前 IDL/P0 覆盖

DESIGN 已设计 Hack/Drain/Overload/Debilitate/Disrupt/Fortify、damage types、resistance、immunity、body part extension。但 P0-8 IDL 只有基础 Attack/RangedAttack/Heal，没有这些 command/schema/validator/cost/rejection reasons。

这不是立即 blocker，因为 Roadmap 放到 Phase 6。但它在 DESIGN 主文档中出现得太早，会让 Phase 1-2 实现者以为基础 Combat model 必须预留大量抽象。

建议移到 `design/future-combat.md` 或标注 “Non-P0 / Phase 6 only”。Phase 1-2 的 Command/BodyPart 不要为特殊攻击提前泛化。

### A12 — Medium — FDB 作为 Phase 3 持久化合理，但 Phase 1 docker-compose 直接引入会增加新人门槛

tech-choices 选择 FoundationDB 的理由成立：严格可序列化 + tick atomic commit。但 FoundationDB 运维复杂，Rust binding 和本地开发体验都比 SQLite/Postgres 差。ROADMAP Phase 1 又要求 docker-compose 一键启动 engine + FDB + NATS。

建议 adapter-first：

- `WorldStore` trait 从 Day 1 存在。
- Phase 1 默认 `InMemoryStore` / `FileTraceStore`。
- Phase 3 接 FDB，开始测试真实事务/冲突/备份恢复。

这样不牺牲架构方向，也不让新开发者第一天卡在 FDB 集群。

## Missing

1. Explicit P0 invariants checklist

建议新增 `specs/p0/00-invariants.md`，列出不可破坏合同：

- gameplay mutation only from WASM `SubmittedCommand` after Source Gate。
- no client-supplied player_id trusted。
- all visibility through `is_visible_to` except explicitly delayed spectator/replay views。
- no mutating host functions。
- replay checksum is authoritative。
- publish only after durable commit。

这类不变量应被 CI/test names 直接引用。

2. Failure semantics for commit/publish

缺少清晰说明：FDB commit 失败、Dragonfly 更新失败、NATS publish 失败、client gap、sandbox worker crash、module cache invalidation 时分别如何处理。尤其需要定义 tick 是否 retry、abandon、or advance with empty commands。

3. Schema/codegen governance

P0-8 说 IDL 生成所有绑定，但缺少：IDL versioning policy、backward compatibility、migration、generated code review policy、breaking change process。

4. Performance budget spreadsheet

已有单项预算（fuel、host calls、Rhai AST、tick 3s），但缺少整体 tick budget allocation：snapshot build、sandbox collect、validation、ECS execute、commit、publish 各占多少 p50/p99。没有这个，500 players 目标不可验证。

5. Security threat model document

各处有安全措施，但缺少按 attacker 分类的 threat model：malicious WASM player、malicious MCP client、malicious mod author、spectator collusion、admin misuse、supply-chain compromise、DoS。建议 P0 后补一个 `SECURITY.md`。

6. Minimal playable spec

P0 文档很多，但缺少“最小可玩世界”冻结：地图尺寸、坐标系（方格/六边形当前混用：Direction 是六方向，但 terrain 示例像 x/y grid）、Source 行为、Spawn 行为、body fatigue formula、build progress formula、harvest amount。没有这些，starter bot 无法稳定实现。

7. Coordinate/topology decision

P0-8 Direction 是六边形邻居（TopRight/BottomRight 等），但大量示例用 `(x,y)` tile/grid，`plain/wall/swamp` 接近 Screeps 方格。需要明确是 hex grid、square grid 还是 axial/cube coordinates。这个决策会影响 pathfinding、range、visibility、movement、rendering。

## Phase Ordering

Recommended ordering adjustment:

1. R12 Freeze Cleanup (before implementation)

- Fix A1: P0-2/P0-9 command auth schema split。
- Fix A3: Tick COMMIT/PUBLISH phase boundary。
- Fix A8: IDL/prose naming drift。
- Add P0 invariants checklist。
- Decide coordinate topology。

2. Phase 1A — deterministic single-process vertical slice

- In-memory Bevy world。
- One room, one player, one resource Energy。
- WASM tick → SubmittedCommand[]。
- Source Gate injects auth context。
- Validate/apply Move/Harvest/Transfer/Spawn/Build。
- TickTrace file output + checksum。
- Starter bot runs 1000 ticks and replay matches。

No FDB, no NATS, no Dragonfly, no ClickHouse, no Rhai, no market, no global storage.

3. Phase 1B — sandbox hardening and IDL gate

- Wasmtime fuel/timeout/memory limits。
- Query-only host functions。
- Malicious WASM tests。
- IDL generates Command/TS SDK/validator stubs。
- Canonical JSON / deterministic serialization tests。

4. Phase 1C — minimal deploy/debug loop

- `swarm_deploy` / `swarm_get_snapshot` / `swarm_explain_last_tick` minimum MCP。
- Still local single-process or simple HTTP; auth can be dev token initially but Source Gate shape must match final。

5. Phase 2 — multiplayer and visibility

- Multiple players, seeded shuffle, contention/refund。
- Unified visibility cache。
- MCP/WebSocket/REST outputs all tested against same visibility fixtures。

6. Phase 3 — durable services

- FDB adapter, Dragonfly, NATS, ClickHouse。
- Commit/publish failure semantics。
- Operational tests and backup/replay validation。

7. Later phases

- Rhai rules only after replay/visibility/source contracts are stable。
- Global storage/market only after local economy is fun。
- Combat/Arena/special attacks only after baseline movement/economy/debug loop is proven。

## Final note

R12 的主架构方向可以继续，但要防止“平台野心”压过“可玩内核”。最重要的下一步不是继续加功能设计，而是把 P0 合同削成可测试的不变量，并用最小垂直切片证明：一个 bot 在一个房间里跑 1000 tick，重放逐 tick checksum 完全一致，所有 rejected commands 都能解释清楚。
