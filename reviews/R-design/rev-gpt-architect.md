# R-design Clean-Slate Review — GPT-5.5 架构师

## Verdict: REQUEST_MAJOR_CHANGES

当前设计的愿景清晰，核心方向（WASM-only 玩家路径、MCP 仅作为管理/观察界面、ECS tick、确定性回放、应用层证书）是成立的；但作为架构冻结文档仍不适合进入实现。主要问题不是“实现难”，而是多个关键合同之间互相冲突：tick 生命周期与 sandbox 生命周期、确定性合同与数值/脚本模型、Tier/MVP 边界与默认规则集、Auth 控制面边界、性能预算与数据持久化模型。若不先收敛这些合同，后续实现会在接口、数据模型和回放语义上反复返工。

结论：REQUEST_MAJOR_CHANGES。发现 9 个问题，其中 Critical 2 个、High 5 个、Medium 2 个。

---

## Strengths

1. **AI 与人类同走 WASM 路径是正确的核心架构选择**
   - `interface.md` 明确 MCP 不提供 `swarm_move` / `swarm_attack` 等游戏动作，AI agent 必须生成并部署 WASM。
   - 这避免了“AI 走特权控制通道、人类走游戏客户端”的经典公平性失败模式，也让 fuel metering、代码签名、回放审计可以统一。

2. **Deferred Command Model 与确定性回放方向正确**
   - `tick(snapshot) -> Command[]`、收集后统一排序和校验，适合 MMO 编程游戏。
   - Mutating host function 被明确禁止，这是非常重要的边界；否则 WASM host API 会变成隐式状态机，确定性和审计都会炸。

3. **Auth 使用应用层证书而不是依赖 mTLS/OAuth，是自托管游戏服务器的好方向**
   - Server Root CA / Intermediate CA / 用途隔离证书 / canonical request signature 的模型完整度高。
   - 对 AI agent、离线部署、内网、自托管场景有现实价值。

4. **设计已经意识到“单世界全量快照”不是长期答案**
   - Tier 1/2/3 快照路线、房间分片、mod manifest hash、world_config snapshot 都是正确的架构意识。
   - 这比很多早期 MMO 设计只写“以后水平扩展”要好。

5. **配置化世界 + 官方 Vanilla Ruleset 的产品方向有潜力**
   - Vanilla 给新人默认体验，world.toml 给服主调参，Layer 3 给模组世界扩展；这个分层符合开源游戏生态。

---

## Concerns

### A1 — Critical — Sandbox 生命周期合同自相矛盾，会直接影响 tick 预算、状态模型和隔离模型

`tech-choices.md` 中 Wasmtime 选择理由写道：

> per-tick fork 生命周期——每 tick 新 fork，执行完 kill，tick 间无状态保留。

但 `engine.md` 的 Tier1 性能预算又写道：

> WASM instances: 池化，min=10 / max=500；WASM 沙箱生命周期使用预编译池，不采用每玩家每 tick fork/kill 模型。

这不是实现细节差异，而是架构合同冲突：

- per-tick fork/kill：隔离强、状态天然清空、启动成本高、进程模型重。
- instance pool：性能可行、但必须定义实例复用时的 memory reset、WASI state reset、fuel reset、host state reset、side-channel 清理。
- 独立进程 worker pool：还要定义 worker 与 instance 的关系，是一玩家一进程、共享进程多 instance，还是一模块一 worker。

如果这个不冻结，以下文档都会不稳定：

- fuel metering 语义
- tick deadline / epoch interruption
- 玩家代码 tick 间状态是否允许通过 WASM memory 保留
- 预编译 artifact cache 格式
- 安全隔离级别
- replay 时 Wasmtime version 和实例初始化流程

建议：必须选择一个权威模型。架构上更合理的是：

- 部署时 compile/precompile module。
- tick 时从 pool 取干净 instance，强制 reset memory/global/WASI state。
- worker process 可复用，但玩家 WASM instance 不允许保留跨 tick mutable state，除非明确作为游戏 API 的持久 memory 并进入 world state。
- 文档删除“per-tick fork/kill”或改为“per-tick clean instance from sandbox worker pool”。

---

### A2 — Critical — 确定性合同与数值/脚本/规则配置存在多处冲突

设计反复强调确定性：禁 OS entropy、禁 non-deterministic HashMap、禁 f64、Rhai 关闭浮点、回放校验 `state_checksum`。这是正确方向。但同一批文档又大量使用浮点或半浮点语义：

- `gameplay.md` 中 `transfer_to_global_cost = { Energy = 0.01 }`、`transfer_from_global_cost = { Energy = 0.05 }`。
- 特殊攻击 `special_param = 0.5`、`damage_multiplier`、抗性 `default_resistance = 1.0`、`EMP = 2.0`、`Shielded = 0.7`。
- PvE score 公式使用 `min(1.0, par_time / actual_time)`。
- Rhai 示例中 `room_superlinear = 0.2` 或 fixed 语义混杂。
- Overload 说明“攻击公式内部可用 f64，对外暴露整数”，这与确定性合同直接冲突。

这类问题看起来像“只要实现时小心”，但实际会炸：不同语言 SDK、Rhai、Rust、前端预估、回放工具若各自解析小数，确定性和 UI 一致性都会漂移。

建议：全设计统一数值表达：

- 文档中禁止裸 `0.01` / `1.0` / `0.5` 作为规则值。
- 统一使用 `fixed<i64, N>` 或 basis points，例如 `transfer_to_global_cost_bps = 100`。
- TOML 示例也必须使用整数，例如 `resistance_multiplier = 10000`。
- 所有公式给出 rounding mode：floor / ceil / bankers rounding 禁止模糊。
- Rhai API 不接受 float 类型，所有参数进入脚本前已按定点类型解析。

---

### A3 — High — Tier/MVP/默认规则集边界混乱，导致接口冻结范围不可判断

文档同时表达了三种互相拉扯的范围：

1. Tier 1 冻结 Core IDL、6 种特殊攻击，Leech/Fabricate 是 Tier 2+。
2. `gameplay.md` 又说默认 world.toml 中预注册 8 个特殊攻击，包含 Leech / Fabricate。
3. `engine.md` 写 Tier 2/3 的完整 spec 必须在 Phase 1 实现前完成，不得作为远期声明模糊处理。
4. `modes.md` 表中又写 World 领土平衡为 Phase 1+ deferred，由社区/模组解决；但 `gameplay.md` 已写 empire upkeep、累进税、反雪球合同、经济仪表盘等大量机制。

这会造成一个架构级灾难：实现者无法判断 `game_api.idl` 应该冻结什么。SDK、module manifest hash、world-specific SDK、MCP schema、replay trace 都依赖“哪些 command/action/resource/visibility 字段是核心合同”。

建议先写一个唯一权威的 Capability Matrix，按以下维度冻结：

- Core IDL v1 必含命令。
- Vanilla v1 默认启用命令。
- Tier 1 可配置但不改变 SDK 的参数。
- Tier 2 才允许改变 SDK/ABI 的能力。
- 文档示例不得展示 Tier 2 能力像 Tier 1 默认能力一样可用。

Leech/Fabricate 这种内容必须二选一：要么进入 Vanilla v1 和 Core IDL v1；要么从默认 world.toml 示例中删除，保留为 future example。

---

### A4 — High — Auth 控制面边界仍不干净，容易回到“Engine 背着 Auth 状态”的失败模式

`auth.md` 的原则是 Auth 独立控制面，Engine 只消费已签发身份/证书，不持有密码库。这是正确方向。但文档内仍有模糊或冲突：

- 架构图写 `Auth Service / Domain src/auth/ (Engine 内或独立服务)`，但接口合同又写 Auth Service 是独立进程，不与 Engine 共享内存。
- `interface.md` 把大量 auth MCP tools 放在 MCP 工具目录中；`auth.md` 又说 Engine/MCP 注册 auth tools 转发到 auth domain。
- Gateway 被描述为无状态代理，但又承担 canonical request 验签入口；Engine 也有 CertificateVerifier。
- nonce 有时在 FDB，有时在 Dragonfly；admin challenge 又“不存储，Blake3 重算”。这些都需要明确哪个组件是权威验证点。

成功案例通常是：Gateway/Auth 做认证授权，Engine 接收一个已验证且最小化的 `PlayerPrincipal` / `CapabilityGrant`；Engine 可以独立验证 replay 所需的签名和证书快照，但不参与注册、恢复、session 续签。

建议冻结边界：

- Auth Service：CSR、证书签发/吊销、recovery、session、CRL 权威。
- Gateway：transport termination、request canonicalization、签名验证、rate limit、Principal 注入。
- Engine：只验证 deploy/module 与 tick/replay 相关的证书快照，不处理 Web session，不处理 recovery，不直接暴露 auth mutation tools。
- MCP auth tools 可以存在，但路由到 Auth Service，而不是 Engine module 内实现。

---

### A5 — High — 单 tick 全世界 FDB 原子提交与性能预算不匹配，像“看起来强一致、实际吞吐会炸”的架构

文档多处写“每 tick 原子提交整个世界状态”，同时 Tier1 又给出：

- 500 active players
- 50,000 total drones/entities hard cap
- per-player snapshot 256KB
- snapshot total 128MB
- FDB transaction size 16MB
- tick interval 3000ms
- 每 K=100 tick keyframe，其余 tick delta

这里有几个架构矛盾：

- 如果每 tick “世界状态”进入一个 FDB 事务，16MB transaction limit 很快成为硬墙。
- 如果只写 delta，则“每 tick 原子提交整个世界状态”的说法不准确，必须定义 delta 权威性和恢复算法。
- 128MB COLLECT snapshot 与 16MB FDB transaction 是不同路径，但文档容易让实现者把 snapshot、delta、keyframe 混在一起。
- 单全局事务意味着热点 key/subspace、冲突重试、提交延迟都会集中在 tick deadline 上。

成功案例更像 event-sourcing + periodic snapshot，而不是每 tick 全量 state transaction。建议明确：

- FDB 每 tick 写入的是 canonical TickRecord：commands、accepted/rejected、state_delta、checksum、world_config_hash、mods_lock_hash。
- Keyframe 是恢复优化，不是每 tick 权威状态。
- 当前 world head pointer 的推进是小事务，delta payload 可按房间/subspace 分块写入。
- 定义“tick commit atomicity”的粒度：是所有 delta 分块 + head pointer 原子可见，还是先写 immutable chunks 后 CAS head。
- 16MB limit 下给出最大 delta 分块策略和失败降级策略。

---

### A6 — High — Mod/Rhai 规则系统的“可信但可回滚”模型没有闭合

Rhai 作为服主安装、引擎内执行的可信规则层，这个定位可以接受；但文档又要求：

- 每个模组本 tick actions 可回滚。
- 超限时该模组本 tick actions 全部回滚，不影响其他模组和玩家。
- actions 通过 `actions.apply(world)` 写入。
- 多模组在 tick_end 顺序执行，可能互相读写资源和实体。

这里缺少事务模型：

- 模组 A 的 action 是否对模组 B 可见？
- 模组 B 基于 A 的临时结果执行后，A 超限回滚，B 是否也要回滚？
- actions 的排序键是什么？mods.lock 顺序、world.toml 顺序、依赖拓扑序？
- `state.players()` 是否读取完整世界还是可见性过滤？文档说“模组不能看到隐藏实体”，但经济维护费类模组又需要全局统计。

这类规则系统最容易变成隐式第二引擎。建议：

- 明确 Rhai 模组阶段：read-only snapshot -> produce action log -> validate all logs -> deterministic merge -> apply once。
- 模组不能边读边写世界；否则回滚语义复杂。
- 模组执行顺序由 mods.lock dependency topo + name tie-breaker 固定。
- 可信规则模组默认应有全局规则视角；若要“可见性过滤”，必须区分 `RuleMod` 与 `PlayerVisibleScript`，不要混用。

---

### A7 — High — 玩家 API 的“JSON 调试格式 vs FlatBuffers 热路径”合同不够直观，新人和 SDK 作者会困惑

`interface.md` 写 `tick(snapshot) -> Command[]`，多处示例是 JSON；`engine.md` 又写热路径 ABI 使用 binary canonical encoding（FlatBuffers），JSON 仅调试/SDK/compat。`gameplay.md` 也写 WASM 模块通过 `tick(snapshot_json) -> commands_json`。

这会让 SDK 作者不知道真正 ABI 是什么：

- WASM entrypoint 接收 JSON bytes 还是 FlatBuffers bytes？
- Command 返回 JSON 还是 binary buffer？
- canonical body hash 对 deploy/module metadata 用哪种编码？
- Replay 中保存 RawCommand 是 JSON 还是 canonical binary？
- MCP `swarm_dry_run_commands` 输入的是 JSON，那和 tick 内 command binary 如何互转？

建议定义唯一权威：

- `game_api.idl` 生成 canonical binary schema。
- WASM ABI 只认 binary snapshot/command buffer。
- JSON 是 SDK/debug/MCP 展示层，由 IDL 自动转换，不是 tick ABI。
- 所有示例统一标注“伪代码/SDK object”，避免写 `snapshot_json`。

---

### A8 — Medium — World 与 Arena 共用引擎但预算、规则、观战、锁代码语义差异很大，需要更清楚的 mode boundary

World tick 3s，Arena tick 300ms；World 支持热部署，Arena 创建时锁定 WASM；World 不追求公平，Arena 追求公平；World replay 隐私分级，Arena 赛后公开/房间可见性。方向合理，但架构边界不够硬：

- 同一个 TickRecord 是否支持不同 mode 的字段？
- Arena 是否写入同一 FDB subspace？生命周期结束即销毁时，replay/审计保存在哪里？
- Auth、CodeSigningCertificate、module registry 是否跨 World/Arena 复用？
- Arena 300ms tick 与 Wasmtime fuel、snapshot、pathfinding cache 的预算关系需要单独合同。

建议把 Mode 作为 `UniverseKind` 或 `SimulationProfile`，让 TickScheduler、storage namespace、module lock policy、replay retention policy 全部显式挂在 mode profile 下，而不是散落在 modes/gameplay/engine 三份文档中。

---

### A9 — Medium — 接口数量和概念数量过多，首屏 mental model 偏重

从新人视角，当前文档同时引入：WASM、MCP、证书、CSR、PoW、Federation、World/Arena、Rhai mods、world.toml、SDK manifest hash、经济税、外交、人格、PvE、特殊攻击。各自都有价值，但入口抽象层级不够分明。

典型风险是：文档完整但不可学，新玩家/新贡献者不知道“最小闭环”是什么。Screeps 成功的一点是 mental model 极简单：写代码、控制 creep、采资源、造建筑。Swarm 需要保留这个简单入口。

建议 README 增加“最小闭环架构”：

1. 注册/拿证书。
2. 获取 SDK。
3. 写 `tick(snapshot) -> commands`。
4. 部署 WASM。
5. 每 tick 看 replay/explain。

其余 Auth Federation、Rhai、Tier2、PvE、外交都作为扩展层链接出去。

---

## Missing

1. **权威 IDL / Schema 冻结规则**
   - 文档多次引用 `game_api.idl`，但 7 个设计文档中没有给出它的权威字段、版本策略和兼容规则。
   - 需要明确 CoreCommand、Snapshot、TickTrace、ModuleMetadata、WorldConfigSnapshot、Error schema。

2. **TickRecord / ReplayRecord 的 canonical 数据结构**
   - 当前有路径表 `/tick/{N}/commands/state/rejections/metrics`，但缺少完整 record schema。
   - 回放确定性依赖这个 schema；它应先于实现冻结。

3. **Sandbox clean-state contract**
   - 必须写清楚 WASM memory、globals、WASI、env vars、host function cache、pathfinding cache、fuel、epoch deadline 在 tick 之间如何清理或持久化。

4. **FDB commit model**
   - 需要把“全量状态、delta、keyframe、head pointer、checksum”关系写成一个原子提交协议。

5. **Mode Profile 合同**
   - World 与 Arena 的 tick budget、module lock、storage namespace、replay retention、spectator delay 应成为统一 profile，而不是散文描述。

6. **RuleMod transaction model**
   - Rhai action log、rollback、merge order、visibility/global authority 需要正式规范。

7. **Auth/Gateway/Engine trust boundary sequence diagram**
   - 至少需要三条：register CSR、signed MCP read request、deploy WASM。每条明确哪个组件验证什么、写什么存储、给下游传什么 principal。

---

## Phase Ordering

这里的 Phase Ordering 不是按实现难度排序，而是按“架构合同依赖关系”排序；前一层不冻结，后一层文档会继续互相打架。

1. **P0 — Contract Freeze**
   - 冻结 sandbox lifecycle：clean pooled instance vs fork/kill 二选一。
   - 冻结 numeric determinism：所有规则数值统一定点整数。
   - 冻结 Core IDL v1：Snapshot、Command、TickTrace、Error、ModuleMetadata。
   - 冻结 Auth/Gateway/Engine 边界。

2. **P1 — Simulation Core Spec**
   - TickRecord / delta / keyframe / checksum / replay 协议。
   - Phase 2a/2b system ordering 和 command conflict resolution。
   - World vs Arena SimulationProfile。

3. **P2 — Player API & SDK Contract**
   - Binary ABI vs JSON debug 层明确分离。
   - SDK manifest hash、world-specific SDK、deploy validation。
   - MCP schema 由 IDL 生成，避免手写漂移。

4. **P3 — Rule/Mod Contract**
   - Vanilla v1 能力矩阵。
   - Rhai mod transaction/action log/merge/rollback。
   - Tier2/Tier3 扩展点从 Tier1 默认规则中剥离或正式纳入。

5. **P4 — Product Surface**
   - 经济仪表盘、外交、人格、PvE、观战体验。
   - 这些应建立在稳定 TickTrace、visibility、mode profile 之上，否则 UI/API 会跟着底层合同返工。

---

## Recommendations

1. 建立一份 `design/contracts.md` 或等价文档，作为所有设计文档的权威交叉索引：IDL、TickRecord、Sandbox lifecycle、Numeric determinism、Auth boundary。
2. 删除或改写所有互相冲突的句子，尤其是 per-tick fork vs pool、JSON ABI vs FlatBuffers、Leech/Fabricate Tier2 vs 默认注册。
3. 将所有 TOML 示例中的小数改为定点整数，并标注 scale。
4. 把 Auth Service 从“Engine 内或独立服务”统一为独立控制面；Engine 只消费 principal/cert snapshot。
5. 把 FDB 写入模型从“每 tick 原子提交世界状态”改成明确的 immutable tick event + delta chunks + atomic head pointer。
6. 为新贡献者提供 1 页 mental model，防止设计文档虽然完整但入口过重。
