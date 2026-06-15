# Swarm DESIGN — Speaker 最终共识报告

> Speaker: rev-speaker  
> 输入: `/data/swarm/docs/reviews/design-review/` 下 9 份评审报告 + `claude-architect-findings.md`  
> 覆盖: `SPEAKER-CONSENSUS.md`  
> 说明: 本报告只综合评审共识与分歧，不新增独立技术评审结论。

## 总体裁决

**APPROVE_WITH_RESERVATIONS / CONDITIONAL_APPROVE（带保留批准）**

9 位评审员均未建议 Reject，也没有认为核心方向需要推倒重来。共同判断是：Swarm 的核心架构与核心玩法骨架成立，可以进入实现前规格收口阶段，但还不能直接冻结 ABI / IDL、默认 ruleset 或 persistent MMO 玩法参数。

被广泛认可的核心包括：

- **WASM-only player agency**：人类玩家与 AI agents 走同一条 WASM 部署与执行路径，MCP 只作为观察、部署、调试与管理界面，不具备直接 gameplay mutation 权限。来源：rev-claude-architect, rev-claude-security, rev-claude-designer, rev-dsv4-architect, rev-dsv4-security, rev-dsv4-designer, rev-gpt-architect, rev-gpt-security, rev-gpt-designer。
- **Deferred Command Model**：`tick(snapshot) -> Command[]` + Rust core validation 将不可信玩家代码与可信世界状态隔离，是 replayability、anti-cheat、resource accounting 与 AI/human fairness 的正确边界。来源：全部方向多名评审员。
- **Deterministic ECS / replay-first**：固定 PRNG/hash、ordered collections、ECS ordering、fuel metering、replay checksum 等方向正确。来源：Architect/Security/Designer 三方向均认可。
- **World/Arena split**：Persistent World 允许 emergent asymmetry，Arena 承担 ranked fairness，是健康的产品与规则分层。来源：rev-gpt-architect, rev-gpt-security, rev-gpt-designer, rev-dsv4-designer, rev-claude-designer。
- **World Rules Engine / moddability**：动态资源、body parts、damage types、Rhai rules 与 machine-readable rules 对社区 longevity 有价值。来源：rev-dsv4-architect, rev-dsv4-designer, rev-gpt-architect, rev-gpt-designer。

保留项集中在五类：

1. **Determinism Contract 尚未闭合**：Rhai wall-clock timeout、mod order、runtime/version pinning、tick overrun semantics 等会破坏 replay/re-simulation。
2. **MMO scalability 与 topology 尚未设计完**：single-world 上限、sharding/cross-shard、FoundationDB transaction limits、snapshot/query budgets、command execution bottleneck 需要明确。
3. **Gameplay exploit surfaces 需要 invariants**：resource ledger、storage transfer、special effects/status stacking、controller lifespan、refund/recycle、safe mode、market escrow 等必须规格化。
4. **Trusted mod / Rhai trust model 需要分级**：private trusted worlds、public worlds、ranked Arena 不能共享同一信任假设。
5. **Player experience layer 缺失**：first hour、onboarding、starter bot、debugging as gameplay、failure recovery、long-term goals、social/replay loops 还不足以支撑留存。

因此 Speaker 裁决：**批准方向，不批准冻结**。在 P0/P1 行动项完成前，不应冻结 ABI/IDL、默认 balance numbers、ranked Arena policy 或 public persistent World rules。

## 跨方向共识发现（≥2 方向独立发现）

### C1. Deferred Command + WASM sandbox 是正确的核心信任边界

**来源**: rev-claude-architect, rev-claude-security, rev-claude-designer, rev-dsv4-architect, rev-dsv4-security, rev-dsv4-designer, rev-gpt-architect, rev-gpt-security, rev-gpt-designer

三方向都独立确认：玩家/AI 代码只能提交 intent / Command，不能直接 mutate world state；Rust core 统一 validation 与 execution。这使攻击面集中在 Command schema / validation pipeline，可被枚举、测试与审计。该点是 Swarm 当前最强共识。

### C2. AI 与 human players 同路径是公平性与产品 identity 的核心优势

**来源**: rev-claude-designer, rev-gpt-designer, rev-gpt-architect, rev-gpt-security, rev-dsv4-designer, rev-claude-security

AI agents 不通过 MCP 直接调用 gameplay actions，而是和人类一样编译/部署 WASM。这避免 AI-only privileged API，保留“your code is your army”的游戏幻想，也减少公平性与权限绕过风险。必须在后续 MCP / tooling 扩展中保持该边界。

### C3. Determinism 是 anti-cheat、debugging、replay 与 competitive legitimacy 的地基，但当前仍有破口

**来源**: rev-claude-architect A1/A7, claude-architect-findings.md, rev-claude-security C1/M4, rev-gpt-security, rev-gpt-architect, rev-dsv4-designer, rev-dsv4-architect

共识是 determinism-first 方向正确，但若任何状态结果依赖 wall-clock、runtime drift、mod unordered execution、tick overload 不确定处理、non-canonical JSON 或 unresolved conflict semantics，replay/re-simulation 就会失效。尤其 `Rhai 100ms wall-clock terminate + rollback` 被 Claude Architect 与 Claude Security 同时标为 critical，其他评审员虽对 Rhai wall-clock 严重性判断不同，但也普遍要求 version pinning、deterministic ordering 与 replay metadata。

### C4. Rhai / mods 的“trusted server operator”假设需要按 game mode 分级

**来源**: rev-claude-security C2, rev-gpt-security High #2, rev-gpt-architect A13, rev-dsv4-security C2/H4, rev-dsv4-designer, rev-dsv4-architect

多位评审员指出 Rhai 具备 `award_resource`、`deduct_resource`、`damage_entity`、`set_entity_flag` 等高权限能力。对于 private server，“服主可信”可以成立；但 public worlds、mod marketplace、ranked Arena 中，可信假设会因分发、复用、二次打包与 opaque server policy 崩塌。共识建议是：capability manifest、source/config hash、signature、allowlist、mode-specific policy、deterministic mod ordering 与 replay commitment。

### C5. Resource / storage / market 必须有 canonical ledger 与 conservation invariants

**来源**: rev-gpt-security High #1, rev-gpt-architect A5/A10, rev-dsv4-security C3/M2/I1, rev-dsv4-architect D6, rev-claude-architect A3, rev-claude-security M1

Global/local storage、in-transit transfer、market orders、Terminal trading、interception、rollback、capture/destruction 与 FDB commit 都涉及 temporal accounting。跨方向共识是：必须定义 `available -> reserved -> in_transit -> settled/lost/refunded/burned` 等状态机，并保证任意 tick 中每一份 resource 只在一个 ledger bucket 内。否则 MMO economy 会出现 double-spend / duplication / tax evasion / rollback ambiguity。

### C6. Special attacks / status effects 有深度，但默认/早期引入风险高

**来源**: rev-claude-designer G3/G4/R2/R4, rev-gpt-architect A3, rev-gpt-security High #3, rev-dsv4-security H1/H5, rev-dsv4-designer S3/G concern, rev-claude-security H3/M3

Hack、Drain、Overload、Debilitate、Fortify、Fabricate 等机制可增加战术深度，但跨方向一致认为当前 status stacking、immunity windows、refresh、cleanup on death/ownership change、per-target cooldown、aggregate caps、ranked policy 尚未足够明确。尤其 Overload 攻击 player fuel/CPU budget，被多名评审员视为 denial-of-play / griefing 风险。

### C7. Controller lifespan / drone aging 机制需要重构为明确 maintenance rule

**来源**: rev-claude-designer G2/R1, rev-dsv4-security C1, rev-gpt-architect A6, rev-gpt-security Medium #5, rev-dsv4-architect D4/D5

多位评审员独立指出：Controller 对 drone age 的全局回退会导致“2 controllers finite, 3 controllers immortal”式 cliff 或 mature empires 的永久 drone，削弱 lifespan 作为 sink 的意义，并放大 snowball。需要明确 fixed-point math、floor/cap、controller eligibility、phase ordering、Neutral/Hack interaction，并保留 minimum aging rate 或改为 local/radius maintenance。

### C8. Default numbers 是 balance hypotheses，不应视为 frozen spec

**来源**: rev-claude-designer G1/G6, rev-gpt-designer G10, rev-gpt-architect A11, rev-gpt-security Informational #3, rev-dsv4-designer, rev-claude-architect A6

RCL thresholds、storage tax、transfer cost/time、drone caps、fuel effects、lifespan、cooldowns、damage、body costs 等数值目前缺乏 simulation / telemetry 支撑。跨方向共识是：接口与 invariants 可以先冻结，balance numbers 应标记为 initial tuning candidates，并通过 agent-based / adversarial simulation 验证后再进入默认 ruleset。

### C9. Player experience / onboarding / first-hour 是设计阻塞项，不是 UI 后置项

**来源**: rev-gpt-designer G1/G3/G4/M2/M3/M4, rev-claude-designer Missing, rev-dsv4-designer G1/G2/G4/G7, rev-gpt-architect A2/A14

Designer 方向全体一致，Architect 也从 new-player survival / tutorial world 角度支持：当前文档更像 engine design spec，而不是完整 game design。first successful action、starter bot、tutorial ladder、debugging feedback、failure recovery、newbie protection、long-term motivation 与 social loops 必须进入首个可玩里程碑，否则技术骨架成立但留存失败。

### C10. Visibility / MCP / replay / spectator endpoints 需要字段级 matrix 与 redaction rules

**来源**: rev-gpt-architect A8, rev-gpt-security Medium #6, rev-claude-security H2/M2/I2, rev-dsv4-security M2, rev-dsv4-architect P0-5 consistency, rev-gpt-designer G8

Visibility model 方向正确，但所有输出面——WASM snapshot、player UI、MCP `inspect/explain/profile/dry_run`、replay、spectator、admin/audit——必须共享一套 field-level visibility matrix。否则 debug tools 会成为 hidden-state oracle 或 live Arena side channel。

### C11. MMO scalability 不能只靠部署图表达，需要 gameplay-level topology / sharding model

**来源**: rev-claude-architect A2/A3/A4, rev-dsv4-architect D1/C1, rev-gpt-architect A1/scalability, rev-gpt-security Medium #3, rev-claude-security H1

共识是单世界串行 EXECUTE、snapshot serialization、host pathfinding/range queries、FDB transaction limit、replay volume 与 global storage/market coordination 都会成为 MMO scale 约束。需要明确：Phase 1 是 single engine vertical scale 还是 sharded rooms；10000 players 是多世界水平扩展目标还是 single world 目标；cross-shard interaction 是否存在。

### C12. World/Arena split 正确，但 ranked Arena 需要更严格 commitments

**来源**: rev-gpt-security Medium #2, rev-gpt-architect, rev-gpt-designer G7/G8, rev-dsv4-designer, rev-claude-security M2/H4

World 可容忍 emergent unfairness，但 Arena 必须绑定 engine/rules/mod/map/WASM/compiler/SDK/initial-state hashes，live spectate delay 必须 non-zero，code lock 与 replay privacy 要明确。Arena 不应默认启用 arbitrary Rhai 或 high-risk special effects。

## 方向内共识

### Architect 方向共识

**A1. 架构核心可行，但 implementation freeze 前必须先冻结 determinism / ABI / topology contracts。**  
来源: rev-claude-architect, rev-dsv4-architect, rev-gpt-architect

三位 Architect 都给出 Conditional / Approve with reservations。共同认可 deferred command、WASM sandbox、deterministic ECS 与 World Rules Engine；共同要求在实现前补全 topology/sharding、Phase 2a/2b boundary、resource custody、visibility matrix、custom CommandAction vs stable SDK、tick overload semantics。

**A2. 单世界扩展上限与 sharding 策略必须显式声明。**  
来源: rev-claude-architect A2/A3, rev-dsv4-architect D1/C1, rev-gpt-architect A1/scalability

Claude Architect 更强调单世界串行 EXECUTE 与 FDB 事务硬限制；DSV4 Architect 建议 Phase 1-3 采用 single engine vertical scale 并把 horizontal sharding 延后；GPT Architect 要求 world topology / territory model 与 cross-shard gameplay model。共识不是“现在必须实现 sharding”，而是“必须写清楚当前阶段不承诺 single massive world”。

**A3. Phase 2 execution semantics 需要形式化。**  
来源: rev-claude-architect A5, rev-dsv4-architect D2/D3/D4/D5, rev-gpt-architect A7

Inline command execution、deferred ECS systems、spawn room cap、combat simultaneous resolution、death/recycle/age ordering、first-come conflict resolution 都必须被规格化，否则会产生 race condition、double-apply、unfair turn advantage 或 replay ambiguity。

**A4. Stable SDK/IDL 与 dynamic extensibility 存在结构张力。**  
来源: rev-claude-architect A6, rev-gpt-architect A4/internal consistency, rev-dsv4-architect S5 + D2 concerns

新 CommandAction 要求 engine registration / IDL / SDK regeneration，而文档又暗示 TOML/Rhai 可动态注册 custom actions。方向共识是分层：Core Ruleset 稳定；safe config 不改 SDK；experimental custom actions 需要 world-specific schema/SDK，不能直接进入 ranked/default。

### Security 方向共识

**S1. 安全基线强，但信任边界必须更硬。**  
来源: rev-claude-security, rev-dsv4-security, rev-gpt-security

三位 Security 均给 Conditional Approve。共同认可 WASM untrusted、Rhai trusted、Rust core 的三层模型与 source gate/deferred command；共同指出风险集中在 Rhai 权限、Command validation、resource/state transitions、special effects 与 visibility/debug endpoints。

**S2. Command validation 是唯一收口点，必须字段级穷举。**  
来源: rev-claude-security C3, rev-gpt-security Medium #4, rev-dsv4-security S1/S2 + verification checklist

需要所有权、范围、类型、数量、坐标、entity_id、overflow、unknown fields、JSON size/depth/string length、Command[] length、per-tick caps、canonical JSON、DoS budgets。Validation 自身也必须有 cost limits。

**S3. Rhai/mods 需要 capability sandbox + signing/hash policy。**  
来源: rev-claude-security C2, rev-gpt-security High #2, rev-dsv4-security C2/H4

Security 方向一致要求：私服、公共 World、ranked Arena 分别定义不同 mod policy；mod source/config hash 写入 replay/tournament commitments；capability manifest 限制 award/deduct/damage/ownership/flags/economy reads；多 mod 顺序与冲突必须 deterministic。

**S4. Economic exploits 是 MMO 最高价值攻击面。**  
来源: rev-gpt-security High #1, rev-dsv4-security C3/M2/I1, rev-claude-security H1/M1/M3

Global/local storage、transfer losses、market escrow、refund/recycle、tutorial isolation、in-transit visibility、resource tax evasion、custom effects resource injection 都应按 adversarial economy 处理。必须有 conservation invariant 与 automated exploit tests。

### Game Designer 方向共识

**G1. 玩法骨架强，但文档缺 Player Experience layer。**  
来源: rev-claude-designer, rev-dsv4-designer, rev-gpt-designer

三位 Designer 都认可 core fantasy、AI/human parity、deferred tick loop、World/Arena split、strategic depth 与 moddability；也一致指出 DESIGN.md 过于 systems-heavy，缺 first-hour、tutorial ladder、starter bots、debugging feel、failure recovery、long-term motivation、social/replay loops。

**G2. 默认 complexity budget 过高，需要 Default Vanilla / Core Ruleset。**  
来源: rev-gpt-designer G2, rev-claude-designer G3/G5, rev-dsv4-designer G1/G2 + strategy analysis

Designer 方向建议先给玩家一个清晰可学的 default game：single resource 或极简资源、基础 combat、RCL1-3 MVP、无/少 special attacks、无 arbitrary mods、local logistics 渐进解锁。Advanced mechanics 应进入 optional worlds / future modules。

**G3. Onboarding、失败恢复与新手保护是留存核心。**  
来源: rev-gpt-designer G1/M2/M3/M4, rev-claude-designer Missing, rev-dsv4-designer G1/G7

需要 preloaded starter bot、5/15/30/60 分钟 milestones、human-readable rejection reasons、“why idle?” explanation、safe tutorial economy、wipeout recovery、beginner protection、respawn/relocation policy。

**G4. 长期动机与 social/replay/community loops 需要一等公民化。**  
来源: rev-gpt-designer G6/G8/M5/M6/F ideas, rev-dsv4-designer G2/G4/G5, rev-claude-designer Missing

World 模式不能只有 RCL/GCL 数字积累；Arena 也不能只有比赛规则。需要 leagues、seasonal goals、bot/version pages、public replay portfolio、strategy sharing/forking、alliances/diplomacy、server/mod discovery、spectator content loop。

## 未解决分歧（需用户裁决）— 全部已解决 ✅

| # | 问题 | 结论 |
|---|------|------|
| D1 | Rhai wall-clock | 紧急保险丝，全回滚 = 确定性的，保留 ✅ |
| D2 | 单世界 vs 多世界 | 联邦宇宙模型 ✅ |
| D3 | 特殊攻击归属 | 默认启用的官方扩展 ✅ |
| D4 | Controller 永久 drone | 范围限制 + 每 tick 总量上限 ✅ |
| D5 | 产品定位 | 可配置平台 + 官方 curated default ✅ |

### D1. Rhai wall-clock timeout 是否可作为状态决定因素 — ✅ 已解决

**结论**: 设计意图已澄清——100ms 墙钟是紧急保险丝，不是主要预算。触发时**整个模组本 tick 所有 actions 全回滚**（事务隔离），因此结果是确定性的：无论在哪台机器、在哪个 AST 节点触发，canonical state 都是"该模组本 tick 零 effect"。AST 节点数（10,000）才是主要确定性预算。分歧已闭合。

### D2. 单世界 MMO vs 多世界实例 — ✅ 已解决

**结论**: 采用**联邦宇宙模型**——每个世界独立引擎、独立 tick、确定性自治。玩家可跨世界拥有身份和资产，世界间支持异步交互（如跨世界转移资源、共享排名），但无同步实时交互（无跨世界 combat、无跨世界同步 market）。类似 Mastodon 实例间的关系：独立运行，但可互通。

### D3. Default Vanilla 是否应保留高级特殊攻击 — ✅ 已解决

**结论**: 默认世界包含特殊攻击，但特殊攻击与 body part、建筑、伤害类型一样，本质是**默认启用的官方扩展**——通过 world.toml 配置声明，非引擎硬编码。服主可禁用/修改/替换。引擎核心只提供 validation + execution pipeline，具体内容由 world.toml 决定。

### D4. Controller lifespan 是 anti-snowball sink 还是 empire maintenance reward — ✅ 已解决

**结论**: 

1. **Age 上限由 body part 类型决定**：`age_max = BASE_AGE + sum(每个部件的 age_modifier)`，其中 `age_modifier` 定义在 `[[body_part_types]]` 中，世界可配置。重型战斗部件（ATTACK -80, HEAL -30）折寿，耐用部件（TOUGH +100）延寿。
2. **Drone 必须主动返回 Controller 才能降低 age**（非被动光环）。Controller 的维修容量有上限（每 tick 可服务的 drone 数 / 总 age 回退量），RCL 越高容量越大。
3. **Healer 只能恢复 HP，不能降低 age**——age 是战略级物流约束，HP 是战术级。
4. **活动 drone 衰老加速**：idle 正常流逝，每 tick 执行命令 +10% 流逝，防止挂机囤兵。

### D5. Swarm 初版定位 — ✅ 已解决（由 D3 导出）

**结论**: 引擎是**可配置平台**，官方 Default World 是**一套默认启用的扩展组合**（8 body parts + 12 structures + 6 damage types + 8 special attacks + 1 resource）。两者不矛盾——引擎提供 world.toml 配置机制，官方 curated default 是推荐的起点配置。服主可以在此基础上禁用、修改、或从头定义自己的世界规则。

## 行动建议（P0/P1/P2/P3 优先级排序）

### P0 — ABI/IDL / implementation freeze 前必须完成

1. **写入 Determinism Contract v1**  
   - 移除或隔离 Rhai wall-clock 对 canonical state 的影响；采用 deterministic AST/instruction/action budgets。  
   - 规定 mod execution order、JSON canonicalization、runtime/version pinning、replay metadata、tick overrun behavior。  
   - 来源: C3, D1；rev-claude-architect, rev-claude-security, rev-gpt-security, rev-gpt-architect。

2. **定义 Command Validation Schema 与 abuse limits**  
   - 每个 CommandAction 的 ownership/range/type/resource/coordinate/entity/status validation 表。  
   - Command[] length、JSON bytes、string length、depth、resource map entries、unknown fields、overflow behavior、per-drone/per-player/per-tick caps。  
   - 来源: S2；rev-claude-security, rev-gpt-security, rev-dsv4-security。

3. **建立 Resource Ledger / Custody State Machine**  
   - `available/reserved/in_transit/escrow/settled/refunded/lost/burned/taxed`。  
   - conversion、market、terminal、interception、capture/destruction、rollback、FDB commit failure、shutdown 都有 deterministic settlement。  
   - 添加 conservation invariant 与 exploit tests。  
   - 来源: C5；rev-gpt-security, rev-gpt-architect, rev-dsv4-security, rev-claude-architect。

4. **明确 Phase 2a/2b execution semantics 与 conflict resolution**  
   - Inline vs deferred 原则；combat simultaneous vs first-come；spawn cap race；death/recycle/age ordering；resource conflict pro-rata/exclusive 分类。  
   - TickTrace 记录 conflict outcomes。  
   - 来源: A3；rev-dsv4-architect, rev-claude-architect, rev-gpt-architect, rev-gpt-security。

5. **确定 World topology / scale promise / sharding boundary**  
   - 房间尺寸、坐标、邻接、room transitions、spawn placement、territory/controller rules、single-world hard limits。  
   - 明确 Phase 1-3 是否 single engine vertical scale；10000 players 是否为多世界平台指标。  
   - 来源: C11/D2；rev-claude-architect, rev-dsv4-architect, rev-gpt-architect。

6. **定义 Ranked Arena trust commitments**  
   - WASM hash、SDK/compiler/engine/Wasmtime/rules/mod/map/initial-state hashes；non-zero spectate delay；code lock；mod allowlist。  
   - 来源: C12；rev-gpt-security, rev-claude-security, rev-gpt-designer。

7. **Rhai/mod trust policy 分级**  
   - Private trusted, public disclosed, ranked allowlisted 三层。  
   - Capability manifest、source/config hash、signature、deterministic ordering、per-action validators。  
   - 来源: C4/S3；rev-claude-security, rev-gpt-security, rev-dsv4-security。

### P1 — 首个可玩版本 / public persistent test 前必须完成

1. **Default Vanilla / Core Ruleset v1**  
   - 明确哪些是 Engine Core、Default Ruleset、Advanced Worlds、Example Mods。  
   - MVP 建议只含基础 loop：spawn/move/harvest/carry/transfer/build/repair/attack/death/controller upgrade。  
   - 高级 special attacks、market、arbitrary Rhai、custom actions 默认延后或禁用。  
   - 来源: G2/D3/D5。

2. **First Hour Player Journey + Tutorial Ladder**  
   - 0-5/5-15/15-30/30-60 分钟目标；preloaded starter bot；first successful action；graduation path。  
   - Tutorial economy 与 real worlds 完全隔离；100% refund 不得泄露到正式 economy。  
   - 来源: C9/G3。

3. **Debugging as Gameplay**  
   - Rejected command human-readable reasons；per-drone planned/attempted/succeeded/failed timeline；“why idle?”；fuel profile；deployment before/after metrics；replay diff。  
   - MCP docs/resources 需回答“what should I do next?”。  
   - 来源: rev-gpt-designer G4/G9, rev-dsv4-designer G1, rev-claude-designer Missing。

4. **New-player protection / failure recovery / safe mode**  
   - Spawn zones、grace period、safe mode semantics、respawn/relocation、wipeout recovery、anti-grief restrictions、inactive decay。  
   - 来源: rev-gpt-architect A2/A9, rev-gpt-designer M4, rev-claude-designer Missing。

5. **Status Effect Resolution Model**  
   - Stacking、refresh、duration、immunity window、aggregate cap、per-target cooldown、cleanup on death/ownership change、visibility、replay encoding。  
   - Overload/Hack/Drain/Fortify 需专项 review 后再进 default。  
   - 来源: C6。

6. **Controller lifespan redesign**  
   - Fixed-point age math、minimum aging、diminishing returns、local/radius vs global、Controller eligibility、phase ordering。  
   - 来源: C7/D4。

7. **Visibility / MCP / replay field matrix**  
   - Entity fields by surface：WASM snapshot、player UI、MCP inspect/explain/profile/dry_run、spectator、replay、admin/audit。  
   - Dry-run 不得成为 hidden-state oracle。  
   - 来源: C10。

### P2 — Multiplayer beta / economy beta 前完成

1. **Host function/query budgets**  
   - path_find、range query、snapshot serialization、visible entity count、returned object count、search nodes、cache policy、query credits/fuel charging。  
   - 来源: C11, rev-gpt-security Medium #3, rev-claude-security H1。

2. **Balance simulation plan**  
   - RCL curve、storage tax、transfer costs/times、drone caps、lifespan、special cooldowns、combat damage、fuel effects。  
   - Agent-based/adversarial scenarios：hoarding、zerg rush、turtle defense、drain farming、Overload lockdown、market manipulation、newbie griefing。  
   - 来源: C8。

3. **Market model or explicit deferral**  
   - Order types、fees、escrow、partial fill、cancellation、settlement timing、regional/global market、anti-manipulation。  
   - 若 MVP 不做 market，应明确 out of scope。  
   - 来源: rev-gpt-architect A10, rev-gpt-security High #1。

4. **FDB / persistence / replay storage strategy**  
   - Transaction size/time limits、tick commit failure recovery、checkpoint/delta strategy、Dragonfly cache consistency、replay volume budget。  
   - 来源: rev-claude-architect A3, rev-dsv4-architect D6/C2。

5. **Supply-chain / reproducibility policy**  
   - Engine, Wasmtime, Rhai, SDK, mods, rulesets pinned per world/tournament；CVE tracking；ranked worlds 禁止 mid-season auto-update。  
   - 来源: rev-claude-security M4/I1, rev-gpt-security Medium #7。

6. **Social / community / replay loops**  
   - Public bot/version pages、strategy sharing/forking、alliances/diplomacy、server/mod discovery、shareable replay pages、match stats cards、annotated tutorials。  
   - 来源: G4。

### P3 — 后续扩展 / polish

1. **Advanced Worlds / mod marketplace governance**  
   - Mod review status、author identity、signatures、compatibility metadata、server discovery、world rules diff。  
   - 支撑平台路线但不阻塞 MVP。

2. **Advanced combat rollout**  
   - Hack/Drain/Overload/Debilitate/Fortify/Fabricate 分批启用；每批基于 telemetry 与 balance simulations。  
   - Overload 单独设计审查，因为它攻击 player compute budget。

3. **Long-term progression expansion**  
   - Seasonal leagues、bot ELO、challenge badges、optimization benchmarks、puzzle worlds、profile identity、spectator cosmetics。  
   - 避免 pay-to-win 或不可逆 snowball。

4. **Document restructuring**  
   - 将 DESIGN 拆分或重排为：Player Fantasy、Target Audiences、First Hour、Core Loops、Default Ruleset、Progression/Social、Advanced/Modded Systems、Technical Architecture、Security/Determinism Contracts。  
   - 使 game design 与 engine spec 都可审阅。

5. **UX / terminology polish**  
   - Player-facing glossary；隐藏 ECS/Rhai/FoundationDB/CommandAction 等实现术语；为每个核心 mechanic 提供 one-sentence explanation、example scenario、counterplay。

---

Speaker 结论：Swarm 的核心方向获得跨方向强共识；当前风险不是“概念不成立”，而是“过早冻结未闭合的边界”。下一步应先完成 P0 contracts，再把 P1 Player Experience 与 Default Core Ruleset 拉到与 engine implementation 同等优先级。
