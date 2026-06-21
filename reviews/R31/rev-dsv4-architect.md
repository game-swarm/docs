# R31 Architecture Review — rev-dsv4-architect

> **审查方向**: ECS 调度正确性、数据流一致性、算法复杂度与正确性、Tick pipeline 确定性闭合、跨组件状态同步正确性、持久化边界完整性。
>
> **审查日期**: 2026-06-21
>
> **审查范围**: design/README.md, design/engine.md, design/tech-choices.md, specs/reference/api-registry.md, specs/core/01-tick-protocol.md, specs/core/02-command-validation.md, specs/core/04-wasm-sandbox.md, specs/core/05-persistence-contract.md, specs/core/06-phase2b-system-manifest.md

---

## 1. Verdict

**CONDITIONAL_APPROVE** — 架构整体正确：确定性闭合完备、ECS R/W 矩阵严格、持久化分层清晰 (FDB replay-critical + Object Store async)、31-system 调度链和 Unique Writer Contract 均经过系统化设计。发现 2 个 Critical 问题（Leech/Fabricate 校验矩阵缺失、Overload target_id 类型不一致）、1 个 High（Build inline creation 与 §3 pending_entities 矛盾）、若干 Medium。所有问题皆可修复，无根本性架构缺陷。

---

## 2. 发现的问题

### Critical

#### C1: Leech 与 Fabricate 缺少逐指令校验矩阵 — 校验管线缺口

- **文件**: `specs/core/02-command-validation.md`
- **位置**: §3 逐指令校验矩阵，§3.10–§3.15 覆盖 Hack/Drain/Overload/Debilitate/Disrupt/Fortify，但 Leech (§3.16 only) 和 Fabricate 无对应校验矩阵
- **问题描述**: 02-command-validation.md §3 为 6 种特殊攻击定义了完整的逐指令校验表（检查项 → 失败码），但 Leech 和 Fabricate 仅在 §3.16「同 tick 多次命中」表和 §8 属性描述中出现。`validate_and_apply()` 单一线程缺少这两条命令的 formal validation contract。
- **影响**: 校验管线不闭合——引擎实现需自行推断 Leech/Fabricate 的校验规则（body part 要求、range、target 约束、cooldown、resource 消耗上限），导致校验逻辑可能跳过 02-command-validation 定义的审计边界。SDK codegen 也无法为这两条命令生成 typed validation error。
- **修复建议**: 补充 §3.17 Lich (§3.17) 和 §3.18 Fabricate (§3.18) 的完整校验矩阵，至少覆盖：`object_id` ownership、body part 要求（Leech 需 `??` body part, Fabricate 需 `??`）、target validity、range、cooldown、resource 消耗、target ownership（敌对检查）。确保与 `06-phase2b-system-manifest.md` S22a/S22b buffer 定义一致。

#### C2: Overload target_id 类型不一致 — EntityId vs PlayerId

- **文件**: `specs/reference/api-registry.md` §1.3 vs `specs/core/02-command-validation.md` §3.12
- **位置**: api-registry.md 第 87 行「Overload | target_id: EntityId」；02-command-validation.md §3.12 校验表：「target_id 是有效的 player_id」
- **问题描述**: API Registry（由 IDL 自动生成）将 Overload 的 `target_id` 类型声明为 `EntityId`，但 02-command-validation.md 的校验逻辑将其作为 `player_id` 处理（`target_id 是有效的 player_id | NotVisibleOrNotFound`、`target_id != player_id（非己方）`、可见性约束 `is_visible_to(target_player, attacker)`）。这是一个语义级别的类型不匹配——SDK 会根据 IDL 生成 EntityId 参数，但引擎实际校验的是 PlayerId。
- **影响**: (a) SDK 类型系统在 Overload 上出现类型语义错误——生成的 stub 传入 entity ID 而非 player ID；(b) 若按 EntityId 校验，同一玩家的多个 drone 可能有不同 EntityId，但 Overload 按 player 级别压制 fuel budget（全局冷却 key = `(world_id, target_player_id)`），必须用 PlayerId。实现者面临歧义。
- **修复建议**: 在 `game_api.idl.yaml` 中将 Overload 的 `target_id` 类型改为 `PlayerId`（或新增 `PlayerTarget` 类型），然后重新生成 API Registry。同步更新 02-command-validation.md 中的校验表以使用正确的类型名。注意：Overload 是唯一一个以 player（非 entity）为目标的 CommandAction——这需要在 IDL 类型系统中显式表达。

### High

#### H1: Entity Creation 时序矛盾 — Build inline vs pending_entities

- **文件**: `specs/core/06-phase2b-system-manifest.md` §3
- **位置**: §3「Creation: 所有新实体追加到 pending_entities，不立即可见。在当前 tick 所有 system 执行完毕后 flush」；但 S03 build_system 标注「Entity creation: ✅ (immediate, inline — structure appears in current tick)」
- **问题描述**: §3 声称所有新实体通过 `pending_entities` 延迟可见，但 S03 Build 创建的结构是 **inline immediate**——在 Phase 2a 命令循环中立即出现。S08 Spawn 创建的 drone 则走 `pending_entities`，延迟到 tick 结束 flush。两个路径语义矛盾：(a) Build 创建的结构在同 tick 后续 Phase 2a 系统中可见吗？(b) 在 Phase 2b combat 中可见吗？
- **影响**: 若 Build inline 创建在 Phase 2b 不可见，则同 tick 建造的结构无法被 Tower 保护或纳入 combat 计算——这可能是有意设计，但需要明确声明。若可见，则 §3「所有新实体」的说法错误——Phase 2a inline creation 应单独说明。实现者无法据此确定 Build 创建的结构在同 tick 的可见性窗口。
- **修复建议**: 明确区分两类 entity creation：(a) Phase 2a inline creation（Build → 立即可见，对 Phase 2a 后续命令和 Phase 2b 均可见）; (b) Phase 2b deferred creation（Spawn → pending_entities → tick 结束 flush，当前 tick 内不可见）。更新 §3 文本，将「所有新实体」改为「Phase 2b deferred creation 的新实体」。同时在 S03 文档中明确声明 immediate creation 的可见性范围（当前 tick 全部 Phase 2b systems 可见？还是仅限于本 tick 剩余 Phase 2a 命令？）。

#### H2: ResourceAmount 多写入者 — resource_ledger 追踪机制未定义

- **文件**: `specs/core/06-phase2b-system-manifest.md` §S29
- **位置**: S29 resource_ledger:「Reads: All ResourceAmount changes from S01-S28」
- **问题描述**: Phase 2a inline (S01–S06) + Phase 2b (S17, S22, S25) 共计至少 9 个 system 直接写入 ResourceAmount。S29 声称读取「所有 ResourceAmount changes」，但文档未定义 delta tracking 机制——是 (a) 维护 tick 内 change log（每个 ResourceAmount 变更 emit event → S29 消费）还是 (b) S29 在 tick 末尾 diff Bevy World 前后快照？方案 (a) 要求每个写入 system 在修改 ResourceAmount 时 emit event，但当前 manifest 未声明此类 event。方案 (b) 无法区分同一 entity 被多个 system 修改的情况（如 Phase 2a Transfer + Phase 2b Drain 对同一 target 的资源变更会被合并）。
- **影响**: resource_ledger checksum 的可审计性取决于 delta tracking 的保真度。若使用 diff 方式，中间变更（如 build 扣费后又 refund）会被丢失，影响 replay debug 的粒度。若使用 event log，需要所有 ResourceAmount writer 的显式契约。
- **修复建议**: 在 manifest 中明确声明 resource_ledger 的 delta tracking 方式。推荐方案 (a)：定义 `ResourceDeltaEvent` buffer——每个 ResourceAmount writer 在修改时 push delta event（entity_id, resource_type, delta_amount, source_system_id）。S29 消费此 buffer 构建 ResourceLedger。同步更新 R/W 矩阵，为所有 ResourceAmount writer 增加 `ResourceDeltaEvent` buffer 写入声明。

### Medium

#### M1: Recycle 后 drone 携带资源的处理未定义

- **文件**: `specs/core/02-command-validation.md` §3.9 vs `specs/core/06-phase2b-system-manifest.md` S04
- **位置**: 02-command-validation §3.9 Recycle 描述仅提及「返还 lifespan-proportional 比例（10%–50%）身体部件成本作为能量给 spawn」。未说明 drone 自身 carry 资源 (ResourceAmount) 的命运。
- **问题描述**: Screeps 中 Recycle 将 creep 携带的资源一并返还 spawn。Swarm 文档未定义此行为。若 drone 携带 1000 Energy 执行 Recycle，spawn 收到 body_cost 的 50%（如 300 Energy refund），但 drone 自身携带的 1000 Energy 去哪了？选项：(a) 一并返还 spawn，(b) 掉落为地上 Resource，(c) 随 drone 销毁而消失。
- **影响**: 资源总量不守恒的可能性——若 carry 内容消失，Recycle 成为资源黑洞。若返还 spawn，spawn 可能超出 energy_capacity。
- **修复建议**: 在 §3.9 校验矩阵中增加：`drone carry 资源 → 落入 spawn（优先填充 spawn.energy_capacity），超出部分掉落为地上 Resource。掉落 Resource 按 `carry.amounts` 逐项 split 到独立 Resource entity`。在 S04 或 S25 death_cleanup 中声明 carry 资源处理的实现位置。

#### M2: S29 resource_ledger 在 31-system 模型中的位置

- **文件**: `specs/core/06-phase2b-system-manifest.md` §1 System Schedule
- **位置**: S29 resource_ledger 标注「Must run last: ✅」
- **问题描述**: S29 之后没有任何系统。但在 room-partition commit 模型 (§3.5 of 01-tick-protocol.md) 中，Phase 2b 之后有 cross-room intent 处理和 GlobalTickCommit。resource_ledger 产出的 checksum 似乎在这些步骤之前，但 cross-room 资源传输也会改变全局资源账本——这意味着 S29 在 cross-room intent 处理之前运行，可能遗漏跨房间资源变更。
- **影响**: 在 room-partition 模式 (500+ players) 下，跨房间资源传输的 ledger 记录可能不完整。单事务 MVP 不触发此问题（所有变更在同一事务中），但生产环境的 room-partition 场景需要显式处理。
- **修复建议**: 明确声明 resource_ledger 的覆盖范围：(a) 仅覆盖 per-room 变更，cross-room 资源传输由 `CrossRoomIntent` handler 单独记账；(b) 或 S29 延迟到 cross-room intent 处理之后（通过 `pending_cross_room` buffer 收集后补记）。在 manifest §S29 注释中声明此语义。

#### M3: Recycle body_cost refund 溢出 — spawn energy capacity 未校验

- **文件**: `specs/core/02-command-validation.md` §3.9
- **位置**: §3.9 校验表无 spawn.energy_capacity 检查
- **问题描述**: Recycle refund 将 body_cost 比例能量返还给 spawn，但未校验 spawn 是否有足够容量接收此能量。若 spawn.energy → spawn.energy_capacity 仅剩 10 Energy，但 recycle refund = 500 Energy，能量溢出。
- **影响**: 能量凭空消失或溢出逻辑未定义。现有校验未处理此边界条件。
- **修复建议**: 在 §3.9 校验矩阵中增加：`spawn.energy + refund ≤ spawn.energy_capacity`（超出部分掉落为地上 Resource）。与 M1 修复合并处理。

#### M4: Multiple DeathMark writers — 时序正确性需显式声明

- **文件**: `specs/core/06-phase2b-system-manifest.md` §4 R/W Matrix
- **位置**: DeathMark 列：S04(W), S07(W), S15(W), S23(W), S25(W)
- **问题描述**: 五个 system 写入 DeathMark：(a) S04 Recycle Phase 2a inline，(b) S07 death_marker 处理 hits≤0/lifespan expired/Recycle，(c) S15 damage_application 处理战斗死亡，(d) S23 aging 处理 lifespan 过期，(e) S25 death_cleanup 处理 despawn。虽然时序正确（S04 → S07 → S15 → S23 → S25），但 5 个 writer 违反了"单一 writer per component per tick"的 ECS 最佳实践。
- **影响**: 当前调度下安全——S04 在 Phase 2a inline 标记，S07 处理已有死亡，S15 追加战斗死亡，S23 追加衰老死亡，S25 最后清理。但如果未来有 system 插入 S07 和 S15 之间并尝试写入 DeathMark 做准入决策，可能产生竞态。这是「可工作但脆弱」的模式。
- **修复建议**: 在当前 manifest §4 注释中声明 DeathMark 的多写入者约束：(a) 所有 DeathMark writer 按严格时序排列，(b) 任何新增 system 不得在 S23 之后写入 DeathMark，(c) S25 是唯一 despawn 路径。CI 验证规则中加入 DeathMark writer 顺序检查。或者考虑将 DeathMark 拆分为 `DeathMark (pending)` 和 `DeathConfirmed`，由 S25 统一转换。

#### M5: 02-command-validation §3.16 同类型多次命中表 vs §8 Leech/Fabricate 描述不一致

- **文件**: `specs/core/02-command-validation.md`
- **位置**: §3.16 同类型多次命中表：「Leech: 累加：leech_total = sum(leech_i)（不超过 target HP）」；§8 Leech 描述：「base_damage = 15, 伤害的 50% 治疗自身」——无累加语义
- **问题描述**: §3.16 说同一 tick 多次 Leech 命中会累加伤害（上限 target HP），但 §8 Leech 的独立描述只说「base_damage = 15, 效果: 伤害的 50% 治疗自身」，未提累加。类似地，Fabricate §3.16 说「各独立构造，无冲突」，但 §8 描述「将目标敌方 drone 转化为己方建筑」——多次 Fabricate 同一 drone 的行为未定义（第 2 次 Fabricate 时 drone 已是建筑？）。
- **影响**: Leech 的累加与 base_damage 15 的组合语义不清晰——10 个 drone 同时 Leech 同一目标 = 150 damage + 75 self-heal 吗？Fabricate 多次命中同一 target 的语义更模糊——第 1 次构造后 target 已变为建筑，第 2 次如何处理？
- **修复建议**: 为 Leech 和 Fabricate 定义完整的同 tick 多次命中语义，对齐 §3.16 表和 §8 独立描述。推荐：Leech 累加 damage（不超过 target current HP），self-heal 部分也累加（不超过 self max_hits）。Fabricate：仅第一次成功，后续返回 `(debug_detail)`（如「TargetAlreadyFabricated」）。更新 §8 描述以与 §3.16 表一致。

### Low

#### L1: "31 systems" 编号约定略微混淆

- **文件**: `specs/core/06-phase2b-system-manifest.md`
- **位置**: §1 标题「System Schedule (29 systems)」但实际 31；§S22a/S22b 以逻辑 ID 插入但未重编号
- **问题描述**: manifest 标题写 (29 systems)，正文说「共计 31 个 system」。S22a 和 S22b 是在 S22 之后插入的子编号，但没有 S30/S31。虽然 S22a/S22b 的 system_id 已经是独立值（`leech_buf`, `fab_buf`），但标题不一致可能导致跨文档引用时数错 system 数量。
- **影响**: 低——所有跨文档引用均以 system_id（如 `leech_buf`）而非线性编号索引。标题 (29) 是历史遗留，修复即可。
- **修复建议**: §1 标题改为「System Schedule (31 systems)」。可选：将 S22a/S22b 重编号为 S30/S31 以消除歧义，但需同步更新所有表引用。

#### L2: host_get_random seed 派生描述在文档间不统一

- **文件**: `specs/reference/api-registry.md` §4.1 vs `specs/core/01-tick-protocol.md` §9.5
- **位置**: api-registry §4.1:「引擎内部 PRNG 以 (tick_seed, player_id, drone_id, sequence) 为种子」; 01-tick-protocol §9.5 RNG namespace 表:「world_seed + tick」或「world_seed + tick + entity_id/room_id」
- **问题描述**: host_get_random 的 seed 派生使用 `(tick_seed, player_id, drone_id, sequence)` 五元组，但 §9.5 引擎级 RNG namespace 使用 `(world_seed, tick)` 二元组（combat/loot/npc_spawn/event）。两者在不同的确定性域中——host 函数是 per-drone 用户空间确定性，引擎 RNG 是全局世界确定性。但目前文档没有显式区分这两层 RNG 域。
- **影响**: 低——实现层不会混淆（host function 和引擎 ECS 是两个代码路径），但阅读者可能误以为同一 RNG 源服务于两层。补充文档区分即可。
- **修复建议**: 在 01-tick-protocol.md §9.5 开头增加说明：「以下 namespace 为引擎 ECS 层 RNG（非 WASM 用户空间）。WASM 通过 host_get_random 获取 per-drone 确定性随机数，其种子派生见 api-registry §4.1。」

---

## 3. 亮点

1. **确定性闭合完备**：Blake3 XOF 统一覆盖哈希 + PRNG，Fisher-Yates shuffle seed 公式 `Blake3("shuffle" || world_seed || tick.to_le_bytes())` 完全确定。五层排序键 `(priority_class, shuffle_index, source_rank, sequence, command_hash)` 消除了同 tick 指令排序的任意二义性。`canonical_json()` 规则（键排序、无空格、数值无尾零、字符串 NFC 归一化）防止 JSON 序列化差分导致 command_hash 不同。这是教科书级的确定性设计。

2. **S14→S22 特殊攻击管线拆分（R30 B1 修复）**：将特殊攻击处理拆分为「Parallel Buffer Production（S16–S22b）」+「Serial Unique Committer（S22）」是架构上的正确决策。8 个 typed buffer (`HackBuffer`, `DrainBuffer`, …, `FabricateBuffer`) 互不重叠——并行安全天然保证。S22 作为唯一 StatusState writer 消除了并行写入竞争。`PendingSpecialAttackIntent` (S01→S14→S22) 的三段式 pipeline 清晰可审计。

3. **持久化分层严格隔离**：FDB replay-critical subset（10 项必填字段 — 05-persistence-contract.md §2.1）+ Object Store async blob（3 次重试，降级为 `audit_gap` 不回滚 tick）。`fdb_version_counter` 为 deploy mutation 提供严格全序。TickCommitRecord 与 FDB state 在同一事务——「状态成功但审计缺失」被原子性禁止。RichTraceBlob 异步写入失败不触发回滚并生成 `terminal_state = audit_gap`——持久化层语义精确、无歧义。

4. **RoomCap 生命周期保护**：`S06(R) → S07(W) → S08(R+W)` 三阶段严格排序 + 中间态禁止读。R/W 矩阵中仅有这三个 system 访问 RoomCap，任何新增 system 插入此区间被 manifest 的声明性约束阻止。这是「设计就防错」的范式。

5. **Phase 2a TOCTOU 保护合同（02-command-validation §3.3）**：Spawn pending 不可见、Hack 不立即转移所有权（5 tick delay）、per-drone per-tick action quota、fuel/wall-clock 耗尽全弃、指令队列不跨 tick——五条规则在 `validate_and_apply()` 单一路径中强制执行，没有旁路。特别是「Spawn pending 不可见」结合 S06 validate-only + S08 deferred creation 的时序，彻底消除了「同 tick 对未出生 drone 执行命令」的 TOCTOU 漏洞。

6. **WASM snapshot 截断确定性**：距离桶 + entity_id 字典序 + farthest-first 的截断算法（引用 snapshot-contract 权威源而非自行定义），保证 replay 时截断结果一致。`snapshot.truncated=true` flag + `omitted_counts` 给 WASM 模块降级信号，设计周到。

7. **Overload 抗永久锁死证明（02-command-validation §3.17）**：形式化的数学证明——全局冷却 + lower bound + 恢复速率三个约束合力保证 `MAX_FUEL × 0.2` 下限永不突破。这不是宣传口号而是可验证的定理。

---

## 4. CrossCheck — 需要跨方向检查

以下问题超出 Architect（ECS/数据流/调度/持久化）边界，需要其他方向确认：

- **CX-1**: Leech/Fabricate 缺少校验矩阵（C1）→ 建议 **Validator** 检查 `02-command-validation.md` 是否应补充 §3.17/§3.18，以及 `game_api.idl.yaml` 中 Leech/Fabricate 的 validation rules 是否已定义。

- **CX-2**: Overload target_id 类型不一致（C2）→ 建议 **IDL Codegen** 检查 `game_api.idl.yaml` 中 Overload action 的 `target_id` 字段类型，确认是 `EntityId` 还是应新增 `PlayerId` 类型。SDK stub 生成依赖此类型。

- **CX-3**: Recycle 后 drone carry 资源处理（M1）+ spawn energy_capacity 溢出（M3）→ 建议 **Economy** 检查 Resource Ledger §2.5 是否已覆盖 Recycle 的资源回流模型（carry + refund），以及溢出时掉落语义。

- **CX-4**: S29 resource_ledger 在 cross-room intent 之前的运行时位置（M2）→ 建议 **Persister** 检查 05-persistence-contract.md 中 room-partition 模式下 cross-room 资源传输的 ledger 记录完整性问题。

- **CX-5**: Build inline creation 在 Phase 2b 的可见性（H1）→ 建议 **Gameplay** 检查 design/gameplay.md 中 Tower 自动攻击是否应在 Build 同 tick 生效——这影响「同 tick 建造 Tower → Tower 参与 combat」的战术可行性。

- **CX-6**: 02-command-validation §3.16 同类型多次命中表 vs §8 Leech/Fabricate 描述不一致（M5）→ 建议 **Gameplay** 确认 Leech 和 Fabricate 的完整设计意图（累加语义、多次命中行为），更新 §3.16 表和 §8 描述以对齐。