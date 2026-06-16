# R3 Architecture Review — rev-gpt-architect

## Verdict

REQUEST_MAJOR_CHANGES

整体方向是对的：R2 后最危险的架构偏差（MCP 直接操控游戏、AI 与人类走不同执行路径）已经被纠正，当前设计在公平性、确定性、资源核算、可回放性上形成了清晰主线。它不像“功能堆叠型 MMO 设计”，更像一个以 WASM sandbox + deterministic ECS + ruleset federation 为内核的 programmable strategy platform。

但 R3 版本仍有几类“看起来没问题但实际会炸”的架构风险：动态可配置性与 IDL/SDK 冻结边界互相拉扯；Rhai 模组隔离与集成模型存在双轨不收敛；多个安全/公平合同分散在 spec 中但缺一个能约束实现的单一执行模型。我的结论是：核心游戏循环可以继续，但在进入更大规模实现前，必须先收敛下列 A1/A2 级问题，否则后续代码会在“动态插件平台”和“强类型 deterministic engine”之间反复返工。

## Strengths

1. AI == Human 的执行路径已经正确

MCP 被定义为“屏幕和鼠标”，不是 gameplay controller；唯一 gameplay executor 是 WasmSandboxExecutor。DESIGN §4、specs/01 §2.1、specs/03 §1 都反复确认不存在 McpPlayerExecutor。这是最重要的架构正确性：公平性不靠策略补丁，而靠结构保证。

2. Tick 生命周期的主线清晰，符合成功案例

COLLECT → EXECUTE → BROADCAST，与 Screeps/lockstep sim/turn-based deterministic server 的成功模式一致。Phase 2a inline apply 处理资源竞争，Phase 2b ECS systems 处理被动系统，设计上比“所有 command 先 validate 再 batch apply”更不容易出现 TOCTOU 和资源双花。

3. Determinism 的关键依赖被显式列出

IndexMap、seeded shuffle、world_config/mods.lock、keyframe+delta、Wasmtime version、COLLECT cache、Bevy world snapshot restore 都进入了文档。这比很多游戏后端设计强：不是一句“我们会保持确定性”，而是列了 determinism contract。

4. MCP/Web/CLI transport 拆分是正确方向

specs/03 把 Browser endpoint 与 Agent/CLI endpoint 拆开，并且明确 Origin/CSRF 只属于浏览器环境，AI/CLI 应使用 mTLS 或 signed request。这避免了常见失败模式：把浏览器安全模型错误套到原生客户端上。

5. World Rules Engine 的产品方向有长期价值

把 Vanilla、Declarative、Experimental 分层是正确的。只要边界收紧，它可以让 Swarm 同时服务官方公平世界、社区自定义世界和 Arena/PvE 变体，而不把所有玩法硬编码进 engine。

6. 资源边界开始具体化

snapshot 256KB、commands/player/tick、host function 调用数、simulate caps、audit truncation、compile caps 都已写入 specs/01/02/04。这些数字之后可以调整，但“每个输出面都有预算”这个思路是对的。

7. FDB rollback + Bevy world snapshot 的意识到位

specs/01 §3.5 明确 FDB rollback 不会自动恢复内存 Bevy World，要求 world.restore(snapshot)。这是实际实现中非常容易炸的点，文档已经抓住了。

8. ROADMAP 能反映评审收敛状态

ROADMAP 把 R2 convergence patch 的 B1-B7 列出来，并标注测试总数和模块状态。作为进度入口是有用的；只要不要让状态语言污染 DESIGN/spec 即可。

## Concerns

A1. Dynamic CommandAction 与强类型 IDL/SDK 的边界仍不成立（blocking）

DESIGN §8.2/§8.7 与 specs/07/08 同时声称：
- world.toml 可声明 [[custom_actions]]；
- 新 CommandAction 自动暴露给 SDK 和 MCP；
- 引入新 CommandAction 需在引擎中注册变体 + validate/apply handler + IDL 暴露；
- specs/08 又要求任何 API 修改必须从 IDL 开始、生成代码一致、不能手写 Command 变体。

这几句话放在一起会形成实现悖论。Rust enum、TS SDK 类型、Replay schema、Command validation 都是编译期产物；world.toml 是运行期配置。如果“动态注册 CommandAction 变体”是真的，SDK 必须变成 world-specific artifact，部署时必须校验 ABI/schema hash；如果不是真的，那么 custom_actions 只能是 `Custom{name, params}` 这类固定 envelope，不能自动变成强类型 SDK enum。

这是一个典型失败模式：插件系统文档写得像动态语言，核心引擎却是强类型确定性 Rust。早期看似灵活，后期会导致 validation、replay、SDK、MCP schema、audit 全部出现分叉。

建议：二选一并写成硬合同。
- 路线 A（推荐 MVP）：Vanilla CommandAction enum 编译期冻结；world.toml 只能调参数/启停预注册 special_effect；Experimental 世界使用 `CustomAction { name, params, schema_hash }`，不承诺官方 SDK 强类型，只生成 world-specific SDK。
- 路线 B：真正 world-specific IDL。每个 world 启动时生成/发布 `game_api_{world_id}_{abi_hash}`，WASM module manifest 必须声明 abi_hash，部署不匹配拒绝。代价高，不建议 MVP。

A2. Rhai 模组“进程隔离默认”与 ECS 集成示例仍是两套架构（blocking）

DESIGN §8.7 说 Rhai 默认 process isolation，通过 IPC 与核心引擎通信；但同一节的 `register_mod_systems` 示例是在 Bevy `Update` 中直接 `tick_end.call(...)` 并 `actions.apply(world)`。specs/07 §5.1 又补了 RhaiActionBuffer、process isolation、cgroup/seccomp、签名机制。

问题不是文档措辞，而是架构路径没有收敛：
- in-process Rhai 可以直接在 Bevy schedule 中读 World/build state/apply actions；
- process-isolated Rhai 不能拿 `&mut World`，必须通过序列化 snapshot/event/action IPC；
- deterministic node budget 在独立进程中如何中止、如何回滚、如何保证同输入同节点数，需要 runtime contract；
- mod hook 的位置（Phase 2a 前、Phase 2b 后、FDB transaction 内/外）会影响 replay checksum。

建议：删掉或标注 in-process-only 的 Bevy closure 示例，并为 process 模式写真实架构：`World -> RuleSnapshot -> RhaiSandbox IPC -> ActionBuffer -> mini-validator -> FDB txn apply`。同时明确 MVP 是否允许 process mode；如果 MVP 只做 in-process，就不要在生产安全合同里宣称默认 process isolation。

A3. Host function path_find 的成本模型不是资源等价的（blocking for scale/security）

specs/04 §8 给 `host_path_find` 成本 `10,000 + 50/tile`，specs/02 §4.3 限制 path_length ≤100、10 calls/tick、地形 hash 缓存。这个成本按“返回路径长度”计价，但实际 A*/Dijkstra 成本取决于 explored nodes、obstacle topology、可见性 mask、cache hit ratio。复杂迷宫或不可达目标会使服务端 CPU 与玩家 fuel 扣费严重不成比例。

这属于“看起来有 fuel metering，实际 host function 绕过 fuel”的典型沙箱失败模式。WASM 指令被 metered，但 host function 内部做了大量原生计算。

建议：path_find 必须按 expanded_nodes / visited_tiles 计费，并有服务端 hard cap：`max_expanded_nodes`、`max_cpu_us`、`max_cache_entries/player/tick`。返回值应包含 `partial/truncated/reason`。缓存键使用 `player_visibility_fingerprint` 是对的，但还需防止玩家用大量 from/to 撑爆缓存。

A4. Snapshot 256KB 截断策略会破坏“可理解的公平性”（high）

specs/01 §2.3 规定每玩家 snapshot ≤256KB，超限按距离排序截断，最近优先。这个策略工程上简单，但 gameplay 上会产生不可解释失败：远处可见的敌方推进、导弹/特殊攻击前置状态、市场/全局事件可能因为实体过多被截断。玩家会觉得“我明明有视野但 AI/代码看不到”。

这不是单纯 UX 问题，而是 API contract 问题。snapshot 是玩家策略输入；截断不能只按距离，必须按信息类别保留关键摘要。

建议：把 snapshot 拆成 priority lanes：
- critical：自身实体、当前 room threats、incoming hostile events、owned structures、active statuses，永不截断；
- spatial：附近实体，按距离截断；
- aggregate：远处可见实体用 summary/count/heatmap 代替完整实体；
- omitted index：按 room/type 输出 omitted_count，而不是总数。

A5. Refund credit 的 session 例外是预算套利入口（high）

specs/02 §7.2 已修正“退还只进入下一 tick”，并加了 deploy-reset。但“同一 session 内迭代部署不清除 credit”会重新打开跨模块预算转移：AI agent 可以长期保持一个 session，v1 构造竞争失败积累 refund，v2 在同 session 消费。

从架构直觉看，fuel credit 应绑定“执行主体”而不是“用户会话”。session 是连接/认证概念，不应进入 deterministic gameplay budget。

建议：refund credit 绑定 `(player_id, world_id, module_slot, module_hash, tick_epoch)`，任何 module_hash 变化都清零或按比例继承一个很小上限；不要有 session 例外。正常迭代部署不应通过 budget credit 来补偿。

A6. Overload 是跨玩家 resource mutation，当前模型会带来可观察副作用和 race complexity（high）

Overload 通过 gameplay command 改变目标 player 的 future fuel budget。虽然 specs/02 加了可见性、global cooldown、floor、recovery、silent no-op，但它仍是一个跨玩家 compute-resource mutation。此类机制在 programmable game 中很危险：
- 它不是作用于 drone/entity，而是作用于玩家执行预算；
- 它对 AI/human 影响不对称，AI 更依赖每 tick 计算；
- “静默 no-op”无法消除行为侧信道，攻击者可以观察目标产出/动作变化；
- global cooldown 需要原子 compare-and-set，否则多攻击者同 tick 会 race。

建议：MVP/Vanilla 禁用 Overload，只放 Advanced world；或者把 Overload 改成实体级效果（例如目标 drone 的 command quota/fatigue/cooldown），避免直接修改 player fuel budget。如果保留 player-level Overload，必须规定同 tick 多个 Overload 的排序与 cooldown CAS，并接受“行为侧信道不可完全消除”的事实，不要声称无法推断。

A7. Tick 原子性把 FDB 事务与 Bevy mutable world 混在一起，实际实现复杂度很高（medium-high）

specs/01 §3.5 的方向正确，但当前伪代码像是在 FDB txn 中直接 validate_and_apply(world_state)。真实 Bevy ECS mutation 与 FDB transaction 不是一个事务系统；restore(snapshot) 是必要但昂贵的补偿事务。500 玩家、每 tick 大量 entity 时，深拷贝完整 World 可能成为性能瓶颈。

建议：Phase 2a/2b 内部先产出 deterministic `WorldDelta`，在内存 state 上 apply；FDB commit 失败时丢弃 delta 或 replay inverse delta，而不是每 tick 深拷贝全量 World。若 MVP 先做 snapshot restore，应明确目标规模和压测门槛：entity_count、snapshot bytes、restore latency p99。

A8. Read path consistency 没有明确 tick boundary contract（medium）

DESIGN 有 Dragonfly current snapshot、NATS broadcast、Gateway WebSocket；specs/01 有 broadcast，但没有清楚说明 Gateway/MCP/REST 在 tick transition 期间读到哪个版本。典型炸点：WebSocket 已广播 tick N+1，MCP `get_snapshot` 仍读 Dragonfly tick N，player deploy/debug 对不上。

建议：所有 read API 返回 `{world_id, tick, state_checksum, visibility_epoch}`；Gateway 只在 FDB commit 成功、Dragonfly cache 完成后发布 tick N；MCP query 必须声明是 latest committed tick，不读 speculative in-memory state。

A9. 文档存在若干会误导实现的局部不一致（medium）

这些不是架构否决项，但会让新人照文档实现出错：
- specs/03 §1.1 仍写 `public_key: Ed25519 # 服务端生成的临时密钥对`，而 specs/09 §3.1/R2 裁决是客户端生成 Ed25519 私钥并签名部署载荷。
- specs/07 §5.1 “swarm mod install my-mod” 与 DESIGN 的 git-based `swarm mod add <git-url>` 分发模型冲突。
- specs/02 §6 表格有 Markdown 破损：`| MAX_COMMANDS_PER_PLAYER` 前多了 `|`；字段级表里 Overload 行也多了前导 `|`。
- specs/02 §8 后小节编号跳到 `10.1`，说明 spec 经过合并后未重编号。
- specs/02 字段级表仍写 Move “六邻可达”，api/commands.md 示例仍用 `TopRight`，与 R2 后正方形四方向/Direction 收敛冲突。

A10. “官方默认规则集”与“所有内容可配置”的抽象层次还需收敛（medium）

文档一方面说所有身体部件、建筑、伤害、特殊攻击都是 world.toml 定义；另一方面又依赖 Rust enum/IDL/SDK 长期稳定。这个设计可以成立，但必须明确三层：
- Engine invariant：Position/Owner/ResourceStore/Command envelope/visibility/fuel/replay；
- Vanilla schema：官方 BodyPart/Command/DamageType；
- World extension：参数调整或 world-specific schema。

目前这些层混在 DESIGN §8 和 specs/07/08 中，新人会不清楚“加一个 body part”到底是改 TOML、改 Rhai、改 IDL，还是改 Rust。

## Missing

1. ABI / schema hash handshaking

需要一份明确的 `ModuleManifest`：module_hash、wasm_abi_version、game_api_abi_hash、world_rules_hash、sdk_language/version、module_slot。部署、replay、cache key 都应使用它。没有这个，world-specific SDK 或 custom_actions 会不可控。

2. Read consistency contract

需要写清 MCP/REST/WebSocket/Replay 分别读哪个 tick、是否允许 stale、如何带 state_checksum、Dragonfly 更新与 NATS publish 顺序。

3. Pathfinding resource contract

需要 expanded node 计费、CPU/us hard cap、cache eviction、partial result schema。

4. Snapshot degradation contract

需要 priority lanes、critical never-drop 列表、aggregate fallback、omitted metadata，而不是单一距离截断。

5. Mod sandbox protocol

如果默认 process isolation，需要 IPC message schema、snapshot shape、ActionBuffer schema、超限/崩溃处理、determinism proof、hook phase。否则应明确 MVP in-process，不宣称生产隔离。

6. Budget ownership model

fuel、refund、Overload、simulate、host function、deploy compile budget 分散在不同 spec 中。建议补一页 Resource Budget Model，定义每种 budget 的 owner、reset cadence、是否可被 gameplay 改变、是否进入 replay。

7. Newcomer-facing architecture map

当前文档很全，但新人会在 DESIGN/specs/api/ROADMAP 间跳转。需要一张“如果我要实现 X，该看哪些合同”的 map：Tick、Command、WASM host、MCP、Rules、Visibility、Storage。

## Phase Ordering

1. R3 convergence patch first（必须先于代码）

先修 A1/A2/A3/A4/A5/A9：
- 决定 custom_actions/IDL 路线；
- 收敛 Rhai process vs in-process；
- 修 path_find 成本合同；
- 修 snapshot 截断合同；
- 移除 refund session 例外；
- 修认证、mod install/add、Direction、Markdown 编号等文档不一致。

2. Budget/read consistency specs second

补 Resource Budget Model 与 Read Consistency Contract。没有这两份，Overload、simulate、refund、MCP debug、Dragonfly cache 会在实现阶段相互踩踏。

3. Implement core Vanilla only

先冻结 Vanilla CommandAction + fixed IDL + WASM sandbox + tick loop。不要同时实现 world-specific SDK、dynamic CommandAction、process-isolated Rhai。MVP 只允许 Layer 1/Layer 2：参数配置、启停预注册能力。

4. Add rules/mod system behind feature gate

Rhai 先 in-process dev mode 或 process sandbox 二选一，不要双写。无论哪条路线，都必须带 deterministic replay tests 和 timeout/rollback tests。

5. Add Advanced mechanics last

Overload、Fabricate、复杂 special attacks、world-specific SDK、Experimental worlds 应在 Vanilla core + replay + visibility + budget 全部稳定后再进入。否则它们会放大每个底层合同的不确定性。

6. Speaker synthesis should treat security findings as architecture blockers

我与 dsv4-security 的 C1/H2/H1 基本同意；它们不是“安全 polish”，而是架构边界未收敛。若 Speaker 需要裁决，我建议把 A1/A2/A3/A5 作为 R3 blocker，A4/A6/A8 作为 high-priority pre-MVP fix。
