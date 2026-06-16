# R1 架构评审 — rev-gpt-architect

Reviewer: GPT-5.5 / Architect
Scope:
- /data/swarm/docs/design/DESIGN.md
- /data/swarm/docs/design/tech-choices.md
- /data/swarm/docs/ROADMAP.md
- /data/swarm/docs/specs/（用户指定的 /data/swarm/docs/specs/p0/ 不存在；实际读取了 specs 下 01-09）

## Verdict

REQUEST_MAJOR_CHANGES（架构文档层面需大改；不是否定方向）

整体方向有明显成功案例影子：Screeps 的 programmable MMO loop、ECS deterministic simulation、WASM sandbox、IDl-driven SDK、NATS/WebSocket 推送、ClickHouse 分析、FDB 权威事务源，这些组合在概念上成立。尤其「AI 与人类都只能通过 WASM 进入世界，MCP 只是屏幕和鼠标」这个边界是正确且重要的。

但当前设计最大风险不是单点技术选错，而是“文档宣称已经收敛，实际上多个核心合同互相打架”。最危险的是：一边追求 P0/MVP，一边把世界规则、模组、市场、Arena、锦标赛、特殊攻击、全局经济、进程隔离、回放、可见性、AI 调试全部塞进同一冻结面。这个形态很像很多 MMO/模拟器项目失败前的模式：核心 tick loop 尚未最小闭环稳定，就把可配置平台和运营系统提前做成第一版架构承诺，导致实现、测试、文档和玩家心智同时爆炸。

建议：先把 Phase 0 改成“确定性 tick + WASM deferred command + 最小可玩反馈闭环”的可验证内核冻结；把 World Rules Engine 的 Layer 3、Rhai 模组、特殊攻击全量、市场、联邦宇宙、锦标赛等降级为后续 RFC/Expansion，避免 P0 架构面过宽。

## Strengths / 亮点

1. AI/人类公平入口设计正确
   - DESIGN 与 MCP spec 明确：MCP 不提供 swarm_move / swarm_attack 等 gameplay tool；AI 必须生成并部署 WASM。
   - 这避免了常见失败模式：为 AI 开后门，最后公平性、可观测性和反作弊全部失效。

2. Deferred Command Model 是正确的游戏架构选择
   - WASM tick(snapshot) → CommandIntent[]，服务端注入 player_id/tick/source，再统一 validate/apply。
   - 这个模型比 mutating host function 更容易重放、审计、限流和调试。

3. 单一 Source Gate / Command Validation Pipeline 意识强
   - specs/02 与 specs/09 对来源、auth context、admin 路径、tutorial 隔离都有明确约束。
   - “客户端不可自报 player_id / source / tick”是非常关键的安全-架构边界。

4. 确定性合同覆盖面较完整
   - Blake3 XOF PRNG、IndexMap、禁 f64、固定 ECS 偏序、TickTrace state_checksum、FDB commit 失败快照恢复，都说明设计者理解 deterministic simulation 的坑。

5. 可见性作为统一函数处理是正确抽象
   - `is_visible_to(entity, player_id, tick)` 作为所有输出面的共用过滤函数，能避免 snapshot、MCP、WebSocket、REST、replay 之间的信息泄漏分叉。

6. IDL-first 方向值得保留
   - game_api.idl 生成 Rust/TS/MCP/Docs/Test 的方向正确。对这种多 SDK + AI agent + Web UI 项目，手写多份 schema 迟早会炸。

7. 文档显式记录失败语义
   - WASM timeout/crash、FDB commit fail、NATS publish fail、TickTrace write fail 等都有语义矩阵，这是比普通设计文档成熟的地方。

## Concerns / 发现的问题

A1. [Critical] P0 范围严重膨胀，架构冻结对象不清

当前 ROADMAP 宣称 engine/sandbox/sdk/gateway/frontend/infra/docs 全部 100%，同时 DESIGN/specs 覆盖：
- 持久 MMO 世界
- Arena / 锦标赛
- 全局+本地经济
- 市场交易
- Rhai 规则模组
- 可配置 body/structure/damage/custom action/special effect
- AI MCP 全工具
- 教程、starter bot、本地模拟、回放、仪表盘
- FDB/Dragonfly/ClickHouse/NATS/nginx/gateway
- OS 进程隔离、seccomp、cgroup

这不是一个 P0，是一个平台级 1.0+扩展生态。失败模式类似：早期系统在没有真实玩家反馈前冻结太多“理论可扩展点”，后续每个 bug 都要同时穿透 IDL、SDK、规则注册、回放、可见性、审计和 UI。

建议：重新定义 P0 架构冻结边界：
- P0 必须只有 tick loop、WASM sandbox、CommandIntent、最小 ECS、最小可见性、最小 MCP deploy/query/debug、基础教程。
- 市场、Rhai、Layer 3 SDK、特殊攻击全量、联邦宇宙、锦标赛移出 P0。

A2. [Critical] 文档之间存在关键合同冲突：Command 数量与 JSON 大小限制不一致

冲突例子：
- specs/02 §1.1：Command[] maxItems = 100，总字节数 ≤ 256KB。
- specs/02 §6 批级校验：单条指令 ≤64KB，整批 ≤1MB，每 tick 每玩家 ≤500 条指令。
- DESIGN §5/§8 多处示例称 tick 返回 commands_json，但字段命名 cmd/action/type 混用。

这类限制是安全边界，不是文档细节。实现者如果按不同章节写，会出现 SDK 允许、服务端拒绝、MCP dry-run 通过但 tick 失败的玩家体验灾难。

建议：把 command envelope、CommandIntent JSON schema、大小/数量/深度限制收敛为单一权威文件；其他文档只引用，不重复写数值。

A3. [Critical] 可配置类型系统与 IDL 冻结原则互相拉扯

DESIGN 一方面说 Swarm 是可配置引擎平台：body_part_types、structure_types、damage_types、custom_actions、special_effects 都可通过 world.toml 扩展；另一方面 specs/08 的 IDL 里 BodyPart/DamageType/StructureType 是静态 enum，并说 “IDL 定义所有指令类型单一真相”。

这会产生根本问题：
- 如果 Layer 3 世界可新增 body part / damage type / CommandAction，那么 TS/Rust SDK enum 如何在运行时扩展？
- 如果 IDL 是编译期冻结，world.toml 动态注册的 CommandAction 如何进入 SDK autocomplete？
- 如果每个世界生成 world-specific SDK，那么 MCP docs/schema、module ABI hash、回放、赛事排名和客户端缓存都需要版本矩阵。

文档已有三层扩展模型，但没有把“静态 Vanilla IDL”和“world-specific schema”的边界落实到协议。当前看起来像同时想要 Kubernetes CRD 的灵活性和 protobuf enum 的稳定性。

建议：P0 只冻结 Vanilla IDL。Layer 3 必须作为明确的后续 RFC，要求：world_schema_hash、SDK artifact discovery、module ABI negotiation、deployment rejection reason、cross-world incompatibility UX。

A4. [High] “核心引擎不硬编码游戏内容”与现有 ECS/Command 设计不一致

DESIGN §8 说引擎核心只提供 validation + execution pipeline，不硬编码 Energy/body/structure/special attack。但 specs/02、specs/08 和 DESIGN §3 已经硬编码大量 action semantics：Move/Harvest/Build/Attack/Heal/Spawn/ClaimController/Hack/Drain/Overload 等。

这不是错，但抽象层次表述错误。真实情况更像：
- Core engine 硬编码一组 CommandAction semantic primitives。
- world.toml 可配置这些 primitives 的参数、成本和部分 handler。
- 深度新增需要新 handler/Rhai/IDL。

如果继续宣称“核心完全不硬编码游戏内容”，新人会误以为任意游戏都能靠 TOML 实现，最后在 custom action handler、validator、SDK 生成处踩坑。

建议：改名为 “Configurable Vanilla Ruleset + Extensible Action Registry”，不要承诺完全 data-driven engine。

A5. [High] Tick 顺序与 ECS 系统顺序在不同文档中不一致

例子：
- DESIGN §3.2：Phase 2b 主线 death_mark → spawn → combat；regeneration/decay 并行，仅需 before death_cleanup。
- specs/01 §3.4：`.chain()` 顺序 death_mark → spawn → regeneration → combat → decay → death_cleanup，且后续再说优化才并行。
- specs/07 §3 也使用 chain death_mark → spawn → regeneration → combat → decay → death_cleanup。

这会直接影响游戏语义：出生 drone 是否先经历 regen/decay/combat，资源是否在攻击前再生，疲劳递减是在战斗前还是后。对 deterministic replay 来说，这不是“实现细节”，是协议。

建议：定义唯一 Tick Phase Contract，并把所有系统分成：inline command、ordered systems、parallel independent systems。每个系统必须声明 reads/writes、before/after、determinism reason。

A6. [High] FDB 事务模型与 Bevy 内存工作副本的组合成本被低估

设计选择 FDB 原子提交是合理的，但当前写法暗示每 tick 整个执行阶段包在 FDB txn 中，同时在 Bevy World 原地修改，失败时 world.restore(snapshot)。这有几个隐性炸点：
- Bevy World 深拷贝全状态每 tick 成本可能很高，尤其 500 玩家 × 多房间 × 回放 metadata。
- FDB 事务大小/冲突/提交时延与 3s tick 目标之间没有容量模型。
- “最多重试 3 次，失败则 tick 放弃且 fuel 退还”会把外部存储抖动转化为全世界时间停顿。
- 如果 TickTrace write fail 可以导致 tick 不可回放，但 gameplay 成功，这与“确定性和可审计”目标冲突。

建议：补一个容量预算表：每 tick entity count、delta size、FDB key count、transaction byte size、commit p95/p99、world snapshot copy cost。没有这个表，FDB 选择还只是理念正确，不是架构闭环。

A7. [High] Wasmtime “每 tick fork → 执行 → kill”与预编译/性能目标张力大

每 tick 每玩家 fork worker 的隔离很强，但对 500 活跃玩家、3s tick、10M fuel 来说，进程生命周期和 IPC 成本需要证明。DESIGN 同时说“部署时预编译为原生码，tick 时仅实例化”，sandbox spec 说 worker 进程每 tick 新 fork/kill。两者可共存，但需要清晰说明：
- 预编译 artifact 存在哪里？
- fork 后是否 mmap compiled module cache？
- 每玩家一个长期 worker 再 per-tick reset 是否更现实？
- cgroup/seccomp setup 是否每 tick 重做？

如果按字面 per-player per-tick process churn，系统像“安全优先的在线 judge”，不一定像“实时 MMO tick engine”。

建议：P0 用长期 sandbox worker pool + per-tick instance reset；保留 “paranoid isolation mode” 给生产高风险世界。若坚持 fork/kill，必须给出 benchmark gate。

A8. [High] MCP 工具集在 DESIGN 与 specs 间不一致

DESIGN §4 工具表包含 swarm_tournament_precommit/create/status、oauth2_login/callback/token_refresh、dry_run_commands；specs/03 工具表包含 list_modules、inspect_room、get_replay、simulate，但没有 tournament 工具；MVP spec 又强调 dry_run_commands。

MCP 是 AI 玩家的主界面，工具不一致会导致 agent onboarding 失败。尤其 dry-run/simulate/deploy/list_modules 的边界需要清楚：哪个是 MCP tool，哪个是 REST/CLI，哪个需要 scope。

建议：生成一个 machine-readable MCP tool registry，文档从 registry 渲染。不要手写多份表。

A9. [High] ROADMAP 与设计评审现实关系异常：文档声称 100% 完成，会掩盖架构风险

ROADMAP 写“Phase 0 Architecture Freeze 设计评审 9/9 通过，B1-B9 全部闭合”、“全部完成”，并列出具体测试数量和 commit hash。但本次阅读发现文档本身仍有多个基础合同冲突。若团队把 ROADMAP 当事实来源，会形成组织性盲区：指标全绿，但底层规范不一致。

建议：ROADMAP 区分三种状态：
- design accepted
- spec internally consistent
- implementation verified
不要把“测试通过”与“架构合同一致”混为一谈。

A10. [Medium] 坐标/几何模型不统一：方形房间 + 六边形 Direction

DESIGN §3.1a 说房间为 50×50 正方形网格，出口 N/S/E/W；specs/02 的 Move 校验写 “Direction 是合法六边形邻居”，IDL Direction 为 Top/TopRight/BottomRight/Bottom/BottomLeft/TopLeft。这是 hex grid 方向，不是传统 square grid。

这会影响寻路、可视范围、地形邻接、出口穿越、客户端渲染和玩家直觉。新人会看不懂到底是 square tile 还是 hex tile。

建议：明确世界网格是 square 4/8-neighbor 还是 axial/offset hex。若用 hex，房间边界、出口和坐标图都要改；若用 square，Direction enum 要改。

A11. [Medium] 特殊攻击过早复杂，且包含不直观/高风险机制

Hack、Drain、Overload、Debilitate、Disrupt、Fortify、Leech、Fabricate 同时进入默认规则，会让 P0 gameplay 和 validator 复杂度暴涨。尤其：
- Overload 直接打击对方 fuel budget，本质是攻击玩家计算能力，容易变成反乐趣机制。
- Fabricate “将敌方 drone 转化为己方建筑”语义奇怪，规则/UX/平衡都不直观。
- Hack 使 drone Neutral 且不消耗 lifespan/fuel，会引入大量边界状态。

这些不是不能做，但不像 P0。成功案例通常先用少量正交动作建立清晰 mental model，再加扩展。

建议：P0 只保留 Move/Harvest/Transfer/Build/Spawn/Attack/Heal/Claim/Recycle。特殊攻击进入 Expansion RFC，并先用 Arena 实验。

A12. [Medium] 规则模组信任模型前后不一致

DESIGN §8.7 说 Rhai 是“服主声明 → 可信”，但后面又默认进程隔离、签名、seccomp、cgroup、能力白名单。specs/07 甚至无“允许未签名”模式。

这更像“不完全可信的插件”模型，而不是可信脚本。两者对 API 设计不同：可信脚本可以更强大，不可信插件必须 capability-first、resource-accounted、可撤销。

建议：明确命名为 “semi-trusted server plugins”。默认能力最小化；内置官方规则可以 in-process，第三方默认 process + signed。

A13. [Medium] 可见性与 MCP “player_view full”存在认知风险

specs/05 说 player_view=full 只影响玩家屏幕/MCP，只读查询可全图，但 WASM snapshot 仍受 fog 过滤。DESIGN 中 MCP 是 AI 的屏幕和鼠标，AI 通过 MCP 看世界并生成 WASM。如果 MCP full view 可以给 AI 看全图，即使 WASM tick 受限，AI 也能用全图信息生成策略并部署，实质上破坏 fog。

文档说教学/合作世界使用 full，这可以；但必须明确：任何竞技或正式 World 中 MCP player_view 不得比人类 UI/允许规则更多，且 AI 生成代码不能把超视野情报写入策略状态。

建议：将 `player_view=full` 标记为 non-competitive world only，并在 deploy 时绑定 world visibility policy；正式 World 不允许 MCP full view。

A14. [Medium] Local simulation / dry-run 与权威世界的边界需更硬

MVP 强调 swarm sim、swarm_dry_run_commands、swarm_simulate。它们很有价值，但容易被玩家当 oracle：探测隐藏信息、试探 RNG、反复模拟找最佳动作。

文档有 snapshot-bound non-authoritative，但缺少更严格合同：
- dry-run 输入 snapshot 是否带 visibility fingerprint？
- simulate 是否只能基于玩家已见信息？
- 是否返回 rejection only 而不返回隐藏未来状态？
- 是否计入 rate limit / fuel-like budget？

建议：把 simulate/dry-run 输出限制为“基于玩家当前可见 snapshot 的本地预测”，禁止返回任何新增隐藏实体信息。

A15. [Low] 术语与编号混乱，影响新人理解

例子：
- specs/02 §8 下出现 “### 10.1 RangedAttack”。
- specs/07 章节号从 5.1a 到 9、再到 7/9.1/6.2 混乱。
- “CommandIntent action.type” 与示例中的 `{cmd: "spawn"}` 混用。
- “RCL 1 progress_total” 与表中 Level 1 累计 progress=0、reserved progress < RCL1 的关系不够清楚。

这不是架构致命伤，但会显著增加贡献者上手成本。

建议：冻结前跑一次 docs lint：章节编号、术语表、JSON field naming、限制数值去重。

A16. [Low] 用户指定的 `/data/swarm/docs/specs/p0/` 不存在

实际文件在 `/data/swarm/docs/specs/01-09...`。如果评审流程依赖 `specs/p0/`，说明目录约定与实际仓库不一致。

建议：要么恢复 `specs/p0/` 目录作为 P0 spec index，要么更新评审指令与 AGENTS/README。

## Missing / 缺失项

1. 容量模型
   - 500 players、500 drones/player、room count、entity count、snapshot size、Command count、FDB transaction size、NATS delta size、WebSocket fanout、ClickHouse ingest rate 都需要量级预算。

2. P0 cut line
   - 当前没有清晰说哪些是 P0 必须实现，哪些只是远期设计。ROADMAP 虽然全绿，但设计面太大。

3. Schema/version negotiation
   - world-specific SDK、ABI hash、IDL version、MCP schema version、module compatibility、replay compatibility 需要一个统一版本协议。

4. Benchmark gates
   - sandbox fork/kill、snapshot building、Bevy world snapshot restore、FDB commit、visibility cache、path_find cache 都需要明确 p95/p99 gate。

5. Failure-mode ownership
   - tick abandon、TickTrace write fail、mod timeout、MCP deploy during degraded mode、certificate revocation during cached module execution等已有语义，但缺少谁恢复、如何告警、是否自动暂停世界的运维 runbook。

6. Player mental model
   - 作为可编程 RTS，新人首先需要理解“我能看见什么、我能提交什么、为什么失败、下一步怎么修”。文档有反馈循环，但规则复杂度远超反馈工具的解释能力。

## Phase Ordering / 建议阶段顺序

Phase 0 — Architecture Contract Freeze（先修文档，不写新功能）
1. 建立单一权威合同：Tick Phase Contract、CommandIntent Schema、MCP Tool Registry、Visibility Contract、IDL Version Contract。
2. 删除或降级所有重复数值；其他文档引用权威 spec。
3. 明确 P0 不包含：Rhai third-party plugin、Layer 3 custom schema、市场、锦标赛、全量特殊攻击、联邦宇宙。

Phase 1 — Minimal Playable Core
1. ECS + deterministic tick。
2. WASM sandbox + deferred command。
3. Vanilla commands：Move/Harvest/Transfer/Withdraw/Build/Spawn/Attack/Heal/Claim/Recycle。
4. Basic visibility + own replay + explain_last_tick。
5. TS/Rust starter bot 可真实部署。

Phase 2 — Reliability & Observability
1. FDB persistence + TickTrace + replay verification。
2. FDB failure injection + Bevy snapshot restore benchmark。
3. NATS/WebSocket gap recovery。
4. ClickHouse audit/metrics 最小集。

Phase 3 — AI/Human Tooling Parity
1. MCP deploy/query/debug 最小闭环。
2. Monaco autocomplete + inline validation。
3. swarm_dry_run_commands / swarm sim 的 snapshot-bound 安全合同。

Phase 4 — World Rules Layer 2
1. world.toml 只允许数值调参，不改变 SDK 类型系统。
2. Resource/body/structure cost 参数化。
3. 不开放 custom CommandAction。

Phase 5 — Experimental Extensions
1. Rhai plugins。
2. Layer 3 world-specific SDK。
3. Special attacks。
4. Market / Arena / tournament。
5. 每个扩展先走 RFC + migration + compatibility test。

## Final architectural recommendation

保留当前方向，但不要按当前文档直接实现或继续宣称冻结。先做一次“架构合同瘦身”：把 Swarm 从“可配置 MMO 平台全家桶”收敛为“可验证的 programmable RTS kernel”。等 kernel 跑通真实玩家/AI 的学习-决策-行动-理解闭环后，再把 World Rules Engine 和扩展生态逐层打开。