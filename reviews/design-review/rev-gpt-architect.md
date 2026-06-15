# Swarm Design Review — rev-gpt-architect

Reviewer: GPT-5.5 / Architect
Scope: `/data/swarm/docs/design/DESIGN.md`, `/data/swarm/docs/design/tech-choices.md`, `/data/swarm/docs/ROADMAP.md`, and all spec files currently present under `/data/swarm/docs/specs/`.
Note: requested path `/data/swarm/docs/specs/p0/` does not exist in this checkout; the P0 specs are present directly as `/data/swarm/docs/specs/01-...` through `09-...` and were reviewed.

Verdict: CONDITIONAL_APPROVE

结论：方向批准，但不建议把当前文档视为“可长期冻结的完整架构合同”。核心架构模式是成立的：WASM-only player agency、deferred command、统一 Source Gate、确定性 replay、MCP 非 gameplay 通道，这些都匹配成功的 Screeps-like / deterministic simulation / secure sandbox 系统经验。主要风险不是“路线错了”，而是当前设计同时追求“可玩的官方 MMO RTS”和“高度可配置的游戏引擎平台”，导致若干接口边界、抽象层次和动态扩展机制仍不够收敛。建议在进入大规模实现/公开持久世界前，补齐下列 High/Critical 级问题。

## Strengths / 亮点

1. 人类与 AI 的公平路径非常清晰
   - “世界只认 WASM”是正确的架构锚点。
   - MCP 被定位为 AI 的屏幕/鼠标/部署与调试界面，而不是 `swarm_move` / `swarm_attack` 这类 gameplay 操作入口，避免了 AI 特权通道这一常见失败模式。
   - Source Model 明确区分 `WASM`、`MCP_Deploy`、`MCP_Query`、`Admin`、`RuleMod`、`Simulate` 等来源，且身份由服务端注入，不允许客户端自报。

2. Deferred Command Model 是适合此类游戏的正确抽象
   - WASM `tick(snapshot) -> CommandIntent[]` 只表达意图；引擎在统一校验管线内按当前 world state 应用，避免 mutating host function 造成 TOCTOU、旁路校验、权限泄露。
   - CommandIntent / RawCommand / ValidatedCommand 三层模型直觉性强，新人能够理解“玩家只能提出请求，世界规则决定结果”。

3. 确定性被当成系统基础，而不是事后补丁
   - Blake3、IndexMap、禁 f64、固定 ECS system order、TickTrace、replay checksum、FDB 原子提交、rollback restore 都是正确方向。
   - 对 programmable MMO 来说，replay/debug/anti-cheat 是核心产品能力；文档已经把它提升到架构级 invariant。

4. 技术选型整体匹配问题域
   - Rust + Bevy ECS：适合 headless deterministic simulation，但需接受 Bevy API 变动风险。
   - Wasmtime + fuel metering + process isolation：比 V8 wall-clock CPU 更适合公平计量。
   - FoundationDB：与“每 tick 原子提交、完整回放”的事务需求匹配。
   - NATS / Dragonfly / ClickHouse 分别用于广播、热缓存、分析，职责清晰。

5. 可见性与安全意识明显强于常见游戏设计文档
   - 统一 `is_visible_to` 函数、输出面矩阵、spectator delay、玩家原创字符串 untrusted 标注、prompt injection delimiter 合同，是跨领域（游戏安全 + AI 安全 + Web 安全）的良好模式迁移。

6. World vs Arena 分离是正确产品架构
   - 持久世界天然不公平，Arena 追求对称公平。文档没有试图用一个模式解决所有诉求，这是成熟判断。

7. ROADMAP 显示实现追踪粒度较好
   - 模块、测试数、差距表、B6-B11/H1-H2 等补齐项有记录，有利于审计设计-实现一致性。

## Concerns / 发现的问题

### A1. Critical — 动态 CommandAction / IDL / SDK 边界存在架构级张力

问题：
- P0-8 把 `game_api.idl` 定义为 host functions / Command / Validator / SDK / MCP schema 的单一真相来源。
- DESIGN 和 P0-7 又说 `[[custom_actions]]` 可由 `world.toml` 动态注册，SDK 和 MCP schema 自动包含所有已注册 action。
- 这两种模式分别对应“编译期稳定 API”和“运行期世界特定 API”。二者可以共存，但当前边界没有足够清楚。

为什么会炸：
- 如果 CommandAction 真运行期动态生成，TypeScript/Rust SDK 的类型、autocomplete、validator、replay schema、client UI、MCP tool schema 都会变成 world-specific artifact。
- 玩家 bot 的可移植性会下降：同一 WASM/SDK 在不同世界可能类型不兼容。
- Replay 记录如果依赖动态 action handler，旧 replay 需要绑定当时的 world.toml、mod version、handler registry、IDL ABI；否则可回放性被破坏。
- 这类似很多“插件化平台”失败模式：核心 API 尚未稳定时开放过强扩展，导致生态学习成本和兼容性爆炸。

建议：
- 明确三层扩展：
  1. Core CommandAction：编译期 IDL 冻结，官方 SDK 长期稳定。
  2. Declarative Effect：复用 Core action/effect handler，仅参数可配置，不改变 SDK 类型。
  3. Experimental World-specific Action：允许世界特定 schema/codegen，但必须要求 world-specific SDK artifact、ABI hash、replay bundle、compatibility manifest。
- 官方 World/Arena 只允许第 1 层和审过的第 2 层。
- `game_api.idl` 应记录 `core_abi_version`；world-specific registry 应记录 `world_api_hash`，并写入 TickTrace。

Severity: Critical

### A2. High — “游戏”与“游戏引擎平台”的抽象层次仍未收敛

问题：
- 文档同时强调 Swarm 是 Screeps 精神续作的 MMO RTS，又强调几乎所有内容（资源、身体、建筑、伤害、特殊效果、custom action）都可配置。
- 如果默认规则不够强，玩家看到的是“引擎”而不是“游戏”。如果扩展太自由，教程、策略分享、比赛、SDK 示例都会碎片化。

已知模式匹配：
- 成功模式：Minecraft/Factorio 先有强 canonical game，再有 modding；StarCraft 自定义地图也建立在稳定核心规则之上。
- 失败模式：过早平台化、过度抽象，导致没有一个足够好玩的默认体验，社区没有共同语言。

建议：
- 文档新增 “Official Core Ruleset Contract”。明确默认资源、body parts、建筑、市场、战斗、visibility、safe mode、Arena 规则在官方世界内稳定。
- Modded worlds 标注为非官方、不参与官方排名，除非通过 ruleset certification。
- 技术文档可继续支持 extensibility，但产品/架构冻结应冻结 canonical game 的最小闭环。

Severity: High

### A3. High — 世界拓扑、领土、sharding 与跨房间移动仍不足以支撑 MMO 规模判断

问题：
文档大量依赖 room/controller/observer/terminal/room cap/cross-world/sharding，但没有完整定义：
- room 尺寸、坐标系、出口、邻接关系；
- 房间生成、初始 spawn placement、防出生点包围；
- neutral / reserved / owned / contested room 状态机；
- 多房间控制限制、扩张成本、跨房间路径；
- shard 边界、跨 shard 资源/市场/排名一致性；
- Arena 地图模板的对称性验证。

为什么重要：
- Screeps-like 游戏的拓扑就是经济与战争。拓扑未定义时，资源、视野、path_find、spawn policy、新手保护、sharding 都无法被真实验证。

建议：
- 新增 “World Topology & Territory Contract”：room graph、coordinate model、exit rules、controller lifecycle、claim/reserve/abandon、spawn placement、room cap、cross-shard boundaries。
- MVP 可限制为固定小 room graph，但必须把后续扩展边界写清楚。

Severity: High

### A4. High — 新玩家保护 / Safe Mode 仍是字段级设计，不是生命周期设计

问题：
- Controller 有 `safe_mode`、`safe_mode_available`、`safe_mode_cooldown` 字段，但规则不足。
- Persistent MMO 中自动化玩家可 24/7 spawn camp、drain、hack、strip mine。仅有 tutorial 和 respawn policy 不足以保护留存。

缺失：
- 首次 colony bootstrap 资源、初始 safe mode 时长、结束条件；
- safe mode 阻止哪些行为：damage、drain、hack、overload、build blocking、market attack、visibility scouting？
- safe mode 下玩家能否主动攻击或扩张；
- respawn 如何避开敌对密度/废墟农场；
- 保护如何防 alt 滥用。

建议：
- 新增 “Colony Bootstrap & Safe Mode State Machine”。
- 把 safe mode 作为 P0/P1 gameplay invariant，而不是 Controller 字段。

Severity: High

### A5. High — 特殊攻击体系复杂度超前，且部分效果跨越 gameplay/resource/security 边界

问题：
Hack/Drain/Overload/Debilitate/Disrupt/Fortify/Leech/Fabricate/Scramble 等机制很有表现力，但当前抽象密度过高。

风险：
- Overload 攻击玩家 fuel budget，是对“参与游戏能力”的攻击，不只是单位状态变化。若可堆叠，会成为 denial-of-play。
- Hack 造成 ownership/Neutral/idle/fuel/lifespan/visibility/command queue 的跨系统状态，需要严格 cleanup。
- Fabricate / convert_to_structure 改变 entity kind，涉及 inventory、ownership、body parts、construction rules、replay encoding。
- “命中判定取决于 body part 数量与目标防御差值”“damage_multiplier 影响成功率/效果量”还不够形式化。

建议：
- MVP/Core 只保留基础 combat + repair/heal + maybe claim。
- 特殊攻击作为 optional ruleset 晚期引入，每个 effect 必须定义：target validity、range、cost、cooldown scope、stacking、refresh、immunity、interrupt、death cleanup、ownership change cleanup、serialization、replay event、per-target cap、per-player cap。
- Overload 建议单独设计评审；优先考虑影响 in-world unit efficiency，而不是直接削玩家 CPU。

Severity: High

### A6. High — 资源 custody / inventory / local-global-storage 状态机仍有歧义

问题：
- DESIGN 中有时说 drone 采集先进入本地存储，有时 P0-2 Harvest 又要求 Carry capacity。
- Local storage / global storage / in-transit / terminal / market escrow / interception 之间缺少统一状态机。

会出错的地方：
- 无 storage 或 storage full 时 Harvest 怎么处理？
- 多个 nearby storage tie 如何确定？
- 本地→全局运输期间 storage 被毁怎么办？
- in-transit 资源可在什么路径/实体上被拦截？
- 市场挂单如何 escrow，partial fill 如何 deterministic settle？
- global storage tax 对 in-transit / escrow 是否计入？

建议：
- 新增 Resource Custody State Machine：`Source -> DroneCargo -> StructureInventory -> LocalAccount -> Transit -> GlobalAccount -> MarketEscrow`。
- 明确每个转移的 authority、duration、failure rollback、visibility、audit event。

Severity: High

### A7. High — 数值确定性合同与文档中的 float 示例冲突

问题：
- Determinism Contract 明确禁 f64 / 使用 fixed-point。
- 但 DESIGN/P0-7 多处配置仍使用 `0.01`、`0.05`、`0.001`、`special_param = 0.5`、`default_resistance = 1.0`、`damage_multiplier = 1.0`、`float` 字段。

为什么重要：
- 这是典型“文档看起来没问题但实现会分叉”的模式。TOML parser 读入 float 后，即使内部转换为 fixed，也需要定义 rounding、scale、serialization 和 invalid value 规则。

建议：
- 所有文档统一使用 `fixed<u32,N>` 或 integer basis points，例如 `transfer_to_global_cost_bps = 100`。
- `special_param` 改为 `fixed<i64,4>` 或按 effect 定义强类型参数。
- 配置 schema 禁止浮点 token；CI lint 文档和 world.toml 示例。

Severity: High

### A8. Medium — Tick 执行公平性简单但可能在大规模 PvP 中产生非直觉优势

问题：
- 当前执行按 shuffled player order + player-local sequence。简单、可回放，但 whole-player order 在大规模战斗中可能让一个玩家本 tick 连续吃完多个资源/攻击窗口。

风险：
- 玩家可以通过 command 数量和排序让一个 tick 内的先手收益放大。
- “长期期望公平”不等于单次大型战斗体验公平。

建议：
- 明确这是有意设计，或改为 action/entity phase interleaving：move phase、harvest phase、combat phase 等。
- 至少添加 per-player/per-entity/per-action budget，并记录“一个玩家单 tick 最多可改变多少 contested state”。

Severity: Medium

### A9. Medium — Rhai 模组权限模型需要 capability 分层

问题：
- 文档有时说 Rhai 可信、服主安装；有时又说 state query 经可见性过滤、不能看到隐藏实体。
- RuleMod source 允许 deduct/award/emit_event，但不允许读世界；P0-7 示例又遍历 `state.players()` 和 player drones/rooms。

建议：
- 定义 mod capability classes：
  - `global_authority`: 可读全局 aggregate / 全局 rule enforcement；
  - `player_perspective`: 按某 player 视角运行；
  - `spectator_safe`: 只能读公开物理状态；
  - `economy_only`: 只能 deduct/award/market fee。
- 每个 mod 在 manifest 中声明 capability，世界加载时审计。

Severity: Medium

### A10. Medium — 可见性矩阵很好，但 field-level contract 仍需落到实体类型

问题：
P0-5 已有数据分级和输出面规则，但对每种 entity/component 的字段级可见性仍不足。例如：
- enemy drone 是否可见 fatigue/cooldown/status effects/cargo/env vars/current action？
- enemy structure 是否可见 stored resources、cooldown、repair queue？
- Hack/Drain/Overload 状态对双方、旁观者、回放如何显示？

建议：
- 添加 `VisibilityFieldMatrix`，按 EntityType × Field × Surface(snapshot/MCP/UI/replay/spectator/admin) 定义。
- 用测试生成器保证新增字段必须声明可见性。

Severity: Medium

### A11. Medium — Market 仍像占位功能，但 ROADMAP 显示已实现完成

问题：
- DESIGN 提到 Terminal、market trading、market_requires_terminal、价格操纵反制。
- P0 规范未给出完整 deterministic market model。
- ROADMAP 说“市场交易 + Arena 1v1 + 排行榜”已完成，但设计文档仍不足以审计 market 正确性。

缺失：
- order book 类型、price units、escrow、partial fill、fees、cancel、expiration、regional/global market、terminal requirement、物流/拦截、anti-alt。

建议：
- 若市场已实现，应补 P0-10 Market Spec。
- 若不是 MVP 核心，应从 P0 完成清单降级为 P1/P2。

Severity: Medium

### A12. Medium — ROADMAP 的“100% 完成”与当前审计性质有错位

问题：
- ROADMAP 声称 main 上 engine/sandbox/frontend/gateway/docs 全部 100%。
- 本次是设计评审而非代码审计；文档内仍存在多个设计缺口。

风险：
- “实现完成”会掩盖“架构合同未收敛”，导致后续修复成本上升。

建议：
- ROADMAP 增加状态分类：Implementation Complete / Design Contract Complete / Reviewed / Production-ready。
- 对市场、special effects、world topology、safe mode 等标注“implemented but needs spec hardening”或“spec missing”。

Severity: Medium

### A13. Low — 技术选型文档整体合理，但部分理由过度绝对化

问题：
- “FoundationDB 是唯一提供这个保证的分布式 KV”“ClickHouse 没有任何对手”“Bevy `.chain()` 完美匹配”等表述偏营销化。

建议：
- 技术选型文档应保留 trade-off：FDB 运维复杂、Bevy 版本 churn、Wasmtime JIT warmup/cache、Dragonfly 新生态风险。
- 对 architecture review 来说，承认风险比写成绝对正确更有价值。

Severity: Low

### A14. Low — 部分文档编号/章节状态有维护痕迹

问题：
- 多个 spec 重复 `状态: 当前`。
- P0-2 后段 “## 8 新增” 内部小节编号跳到 `10.1`。
- P0-7 有 “## 5.1” 后接 “## 8”，再接 “## 7”。
- 用户请求路径是 `specs/p0/`，实际文件在 `specs/`。

建议：
- 增加 docs lint：heading order、duplicate status、broken path、spec index。

Severity: Low

## Missing / 仍缺失的设计章节

1. World Topology & Territory Contract
   - room graph、coordinate、exits、claim/reserve、neutral/contested、spawn placement、room cap、cross-shard。

2. Colony Bootstrap & Safe Mode State Machine
   - 新手保护、safe mode 触发/持续/限制/反滥用。

3. Resource Custody / Inventory / Market Escrow State Machine
   - source、drone cargo、structure inventory、local/global、transit、terminal、market。

4. API Stability & World-specific Extension Policy
   - core IDL vs dynamic action registry、SDK compatibility、world_api_hash、replay bundle。

5. Special Effects Formal Semantics
   - 状态叠加、优先级、cleanup、caps、replay encoding，尤其 Overload。

6. Field-level Visibility Matrix
   - 按 entity/component/surface 定义字段可见性。

7. Market Spec
   - order book、settlement、escrow、fees、terminal/logistics、anti-manipulation。

8. Mod Capability Model
   - Rhai 权限、可见性、可写 action、审计等级。

9. Deterministic Config Schema
   - 禁 float 的 TOML 表达、fixed-point scale、rounding、serialization。

10. Production Readiness Criteria
   - tick overrun load shedding、pathfinding load、snapshot size、shard limits、replay storage cost。

## Phase Ordering / 建议阶段顺序

Phase 0 — Spec hardening before further freeze
- 先修 A1/A3/A4/A6/A7：API 扩展边界、世界拓扑、新手保护、资源状态机、禁浮点配置。
- 建立 spec index：`docs/specs/README.md` 或恢复 `docs/specs/p0/` 路径。

Phase 1 — Canonical Core Ruleset MVP
- 只实现/冻结最小可玩闭环：spawn、move、harvest、carry、transfer、build、repair、attack、heal、claim/controller upgrade、death/decay、basic visibility、replay。
- 不把 advanced special attacks、market、Rhai custom action 作为 MVP 必需。

Phase 2 — Persistent World Safety
- 加入 room topology、safe mode、新手区/respawn、fog of war field matrix、basic PvP、room transition。
- 开启小规模 public test 前必须完成新玩家保护。

Phase 3 — Economy and Market
- 资源 custody 稳定后再引入 global/local storage、terminal、market escrow、运输/拦截。
- Market 必须有独立 spec 和 replay tests。

Phase 4 — Extensibility
- 在 canonical game 稳定后启用 Rhai mods、world-specific custom actions、mod marketplace。
- 官方 ranked Arena 默认禁用实验性 world-specific API。

Phase 5 — Advanced Combat / Meta Mechanics
- Hack/Drain/Overload/Debilitate/Fortify/Fabricate 逐个上线，每个单独平衡与安全评审。
- Overload 需要独立 architecture/security/gameplay review，因为它攻击 compute budget，风险高于普通战斗效果。

## Final Recommendation

CONDITIONAL_APPROVE。

这份设计的核心方向是强的，且多处体现了对已知失败模式的规避：AI 不走特权 gameplay API、WASM 沙箱统一、公平 fuel metering、deferred command、统一 Source Gate、确定性 replay、可见性统一函数。这些是可以继续投资的架构基础。

但当前还不能视为完全架构冻结。最需要立刻收敛的是：动态扩展与稳定 IDL 的边界、world topology、新手保护/safe mode、资源 custody、禁浮点配置，以及 advanced special effects 的形式化语义。若这些补齐，Swarm 有机会成为一个技术上干净、玩法上可持续的现代 Screeps-like MMO；若跳过这些，风险是实现出一个功能很多但规则边界含糊、生态难以稳定、公开世界容易被自动化玩家压垮的平台。
