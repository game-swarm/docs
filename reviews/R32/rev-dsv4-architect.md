# R32 Architect 独立评审报告

**评审方向**: Architect（架构 — ECS 调度正确性、数据流一致性、确定性闭合、跨组件状态同步、持久化边界完整性）
**评审日期**: 2026-06-21
**评审模型**: DeepSeek V4 Pro

---

## 1. Verdict

**REQUEST_MAJOR_CHANGES**

架构整体骨架正确——确定性闭合完整（Blake3 XOF PRNG、seed shuffle、canonical sort key）、ECS 调度链明确（31 systems serial spine + 2 parallel sets）、持久化分层清晰（FDB replay-critical subset + 对象存储 async rich trace）、Phase 2a/2b 职责分离合理。但存在 **4 个 Critical** 和 **3 个 High** 问题，涉及缺失的校验覆盖、类型不一致、以及状态机防护缺口，必须在实现前修复。

---

## 2. 发现的问题

### Critical

#### C1. Leech 和 Fabricate 在 command-validation spec 中缺少逐指令校验矩阵

- **文件**: `specs/core/02-command-validation.md`
- **位置**: §3（逐指令校验矩阵）和 §6（字段级穷举校验表）
- **描述**: `06-phase2b-system-manifest.md` 将全部 8 种特殊攻击声明为核心目标设计（R30 B1/D5），`api-registry.md` §1.3 明确注册了 Leech (#20) 和 Fabricate (#21) 作为 CommandAction 变体。但 `02-command-validation.md` 的 §3 逐指令校验矩阵仅覆盖 Hack (§3.10) 到 Fortify (§3.15)，**缺失 Leech 和 Fabricate 的独立校验小节**。同样，§6 的字段级穷举校验表（七大校验维度）也缺少 Leech 和 Fabricate 的行。
- **影响**: 实现者无法从 validation spec 获知 Leech/Fabricate 的 body part 要求、range 限制、resource 消耗、cooldown、target validity 条件。这直接导致：(a) Phase 2a inline handler (S01) 的校验逻辑实现不完整；(b) CI validation 无法覆盖这两个命令的拒绝路径。
- **修复建议**:
  1. 在 §3 增加 `§3.20 Leech` 和 `§3.21 Fabricate` 小节，包含与 §3.10–3.15 相同结构的校验表（检查项 + 失败码）。
  2. 在 §6 字段级穷举校验表中增加 Leech 和 Fabricate 行，覆盖所有权、范围、数量、资源、坐标、特殊校验六大维度。
  3. Leech 校验应包括：`drone.body` 含 Attack 或专用 body part、target 存在且为敌方 drone、range=1、fatigue==0、冷却、资源消耗（300 Energy）、target hits > 0（吸血需有可吸 HP）。
  4. Fabricate 校验应包括：`drone.body` 含 Work + Claim 或专用 body part、target 存在且为敌方 drone、range=1、fatigue==0、冷却（500 tick）、资源消耗（2000 Energy + 500 Matter）、target 未被其他 Fabricate 进行中。

#### C2. Overload target_id 类型在 api-registry 与 command-validation 之间不一致

- **文件**: `specs/reference/api-registry.md` §1.3 vs `specs/core/02-command-validation.md` §3.12
- **位置**: api-registry line 80, command-validation line 340–353
- **描述**: `api-registry.md` §1.3 将 Overload 的参数声明为 `target_id: EntityId`（与所有其他 20 个 CommandAction 变体保持一致）。但 `02-command-validation.md` §3.12 明确将 Overload 的 target 校验为 **player_id**：`target_id 是有效的 player_id`、`is_visible_to(target_player, attacker)`、`target_id != player_id`（非己方）。这是语义上的类型冲突——Overload 攻击的是**玩家的 fuel budget**（一个 player-scoped 资源），不是 entity。
- **影响**: (a) 实现者看到 `EntityId` 参数类型会尝试解析为实体引用——查询 Bevy World 中的 Entity——但 target 是玩家，没有对应的 ECS entity。(b) Phase 2a S01 的 Overload handler 需要走不同的 target resolution 路径（查 PlayerState 而非 Entity），但这与所有其他 CommandAction 的 `object_id/target_id → EntityRef` 通用解析路径冲突。(c) 类型系统层面，`target_id: EntityId` 对 Overload 是语义错误。
- **修复建议**: 方案 A（推荐）— 将 Overload 的参数从 `target_id: EntityId` 改为 `target_player_id: PlayerId`，在 `api-registry.md` §1 表和 IDL YAML 中同步修改。方案 B — 保留 `target_id: EntityId` 但明确文档标注 Overload 的 `target_id` 实际承载 PlayerId 值（类型擦除），并在 validation spec 中显式声明此转换规则。建议选方案 A——类型精确性减少实现错误。

#### C3. S15 damage_application 缺少 DeathMark guard

- **文件**: `specs/core/06-phase2b-system-manifest.md`
- **位置**: §2 S15 详情 + §4 R/W 矩阵
- **描述**: S07 `death_marker` 在 Phase 2b 开头标记 hits≤0 和 lifespan expired 的实体为 DeathMark。S15 `damage_application` 在 S14 之后执行，写入 HitPoints 并在 hits≤0 时写入 DeathMark。但 S15 的系统详情未声明 `Without<DeathMark>` filter。如果 S11-S13（combat parallel set）对已 DeathMark 的实体产生了 PendingDamage（例如 Tower 自动攻击目标了已被 S07 标记的实体），S15 会尝试对已死亡实体再次操作 HitPoints 和 DeathMark。
- **影响**: (a) 已 DeathMark 实体的 HitPoints 可能被二次修改（从 0 减到负数），破坏 S25 death_cleanup 的期望状态。(b) DeathMark 被 S15 重复写入——虽然幂等但说明 filter 缺失。(c) 确定性风险：如果 Tower 攻击的 target 选择受并行 worker 顺序影响，可能导致 S15 处理的 PendingDamage 集合不确定（取决于哪些已死亡实体被 Tower 锁定）。
- **修复建议**:
  1. S15 增加 `Without<DeathMark>` filter 声明。
  2. S11-S13（attack_system, ranged_attack_system, heal_system）同样增加 `Without<DeathMark>` filter——Tower 不应攻击已死亡实体，heal 不应治疗已死亡实体。
  3. CI 验证增加规则：所有写入 HitPoints 或 DeathMark 的 system（S10 除外——regeneration 已在 S07 之后且已声明 filter）必须同时声明 `R(DeathMark)` 或应用 `Without<DeathMark>`。

#### C4. System 计数不一致 — manifest header 与 body 冲突

- **文件**: `specs/core/06-phase2b-system-manifest.md` line 20, `specs/core/01-tick-protocol.md` line 391
- **位置**: manifest §1 标题 "System Schedule (29 systems)" vs body line 76 "共计 31 个 system"; tick-protocol line 391 "覆盖全部 29 systems"
- **描述**: manifest 的 §1 标题写 "29 systems"，但实际列出了 31 个 system（S01–S29 加 S22a/S22b）。tick-protocol §3.4 line 391 同样引用 "29 systems"。
- **影响**: 实现者可能以标题中的 "29" 为基准验证 system 注册数量——实际有 31 个，导致 CI manifest 校验失败或漏注册。
- **修复建议**: 将 manifest §1 标题改为 "System Schedule (31 systems)"，将 tick-protocol line 391 的 "29" 改为 "31"，并执行全局搜索替换所有 "29 systems" 引用。

---

### High

#### H1. Phase 2a inline entity creation (S03 Build) 与 §3 pending_entities flush 规则冲突

- **文件**: `specs/core/06-phase2b-system-manifest.md`
- **位置**: §2 S03 详情 ("immediate, inline — structure appears in current tick") vs §3 Entity Creation/Despawn Order ("所有新实体追加到 pending_entities，不立即可见")
- **描述**: S03 `build_system` 声明 entity creation 为 "immediate, inline"——新 structure 在 Phase 2a 命令循环中立即出现在 Bevy World 中，对后续 Phase 2a 命令可见。但 §3 的实体创建规则说「所有新实体」走 `pending_entities → tick 末 flush`。两者直接冲突。如果 S03 确实 immediate，则 (a) 后续 Phase 2a 命令（如同一玩家的后续 Build/Transfer 命令）可以操作刚建造的 structure；(b) Phase 2b 系统也能看到这些 structure。但这与 S08 spawn_system 的 deferred creation（pending_entities → Phase 2b flush）形成不对称。
- **影响**: 同 tick 内 Build+Transfer 组合可能产生与 Build-only 不同的结果（取决于 Phase 2a 命令顺序），虽然 deterministic（seed shuffle 固定顺序）但增加了玩家策略依赖排序的复杂度。更重要的是，如果 §3 的 pending_entities flush 被实现为「所有新实体必须 flush」，S03 的 immediate 创建会被错误地延迟。
- **修复建议**:
  1. 明确区分 Phase 2a inline entity creation（S03 Build）和 Phase 2b deferred entity creation（S08 spawn）的可见性语义。
  2. 修改 §3 规则为：「Phase 2b 新实体追加到 pending_entities，tick 末 flush。Phase 2a inline 创建的实体立即在 Bevy World 中可见。」
  3. 考虑是否需要对 S03 创建的 structure 增加 1-tick 的 "construction grace period"（类似 S09 spawning_grace），防止同 tick 内 Build→Transfer 的即时利用。

#### H2. Recycle 命令参数在 api-registry 与 command-validation 之间不一致

- **文件**: `specs/reference/api-registry.md` §1.1 vs `specs/core/02-command-validation.md` §3.9
- **位置**: api-registry line 62, command-validation line 278–288
- **描述**: `api-registry.md` 声明 Recycle 的参数为 `target_id: EntityId`，描述为 "Recycle a drone or structure"（可回收 drone 或 structure）。`02-command-validation.md` §3.9 的校验 schema 为 `{"type": "Recycle", "object_id": 1001, "spawn_id": 2001}`——要求 `spawn_id` 参数（必须为玩家的 Spawn），校验 `object_id` 在 spawn 的 range=1 内。而 §10.3（末尾）又列出 Recycle 仅需 `object_id` 无 `spawn_id`。三种描述互相矛盾。
- **影响**: (a) 如果 Recycle 需要 `spawn_id`，则只能在 Spawn 旁回收——与 "Recycle a structure" 语义冲突（structure 不在 spawn 旁边如何回收？）。(b) 如果 Recycle 仅需 `object_id`（target 是 entity 自身），则 api-registry 的 `target_id` 语义正确，但 §3.9 的 spawn_id 校验多余。(c) 实现者看到三种不同描述会实现出三种不同的 Recycle handler。
- **修复建议**: 裁决 Recycle 的最终语义：
  - **方案 A（简化为 self-action）**: Recycle 是 drone/structure 的自我销毁——不需要 spawn_id，也不需要 target_id。参数仅为 `object_id`（回收自身）。资源退还到全局存储（非特定 spawn）。api-registry 将 `target_id` 改为 `N/A`，command-validation 删除 spawn_id 校验。
  - **方案 B（保留 spawn 锚点）**: Recycle 必须在 spawn 旁——保留 spawn_id 参数。但此时 "Recycle a structure" 应明确为 "Recycle a structure at a spawn"——structure 也需在 spawn 旁。api-registry 描述改为 "Recycle a drone or structure at a spawn"。
  - 建议方案 A——简化，与其他 self-targeted action 一致（Fortify 省略 target_id 时默认自身）。

#### H3. Leech 和 Fabricate 缺少 IDL body part 映射

- **文件**: `specs/core/02-command-validation.md` §3.16 + `specs/core/06-phase2b-system-manifest.md` §S22a/S22b
- **位置**: command-validation §3.10–3.15 各自声明了 body part 要求（Hack→Claim, Drain→Work+Carry, Overload→RangedAttack, Debilitate→Work, Disrupt→Attack, Fortify→Tough），但 Leech 和 Fabricate 在任何文档中都没有声明对应的 body part 要求。
- **影响**: S01 Phase 2a handler 不知道校验 Leech/Fabricate 时需要检查 drone 的哪些 body part。API registry §1.3 仅声明了分类（special_attack）和参数，没有 body part 映射。
- **修复建议**:
  1. Leech: 建议 body part = `Attack`（吸血是进攻性近战能力）或新增 `Leech` body part。
  2. Fabricate: 建议 body part = `Work + Claim`（建造+控制）或新增 `Fabricate` body part。
  3. 将映射写入 `02-command-validation.md` §3 的 Leech/Fabricate 校验小节（见 C1），同步更新 `api-registry.md` §1.3 的参数列或增加 body part 列。

---

### Medium

#### M1. Parallel Set C 仅含单个 system — 命名冗余

- **文件**: `specs/core/06-phase2b-system-manifest.md`
- **位置**: §1 line 65–67
- **描述**: "Parallel Set C: World Maintenance" 仅包含 S24 `decay_system`，且标注为 "serial within C"。一个 single-system "parallel set" 在语义上是矛盾的。R30 之前的版本可能在此 set 中有多个 system，简化后只剩下 decay。
- **影响**: 低——不影响正确性，但给实现者造成困惑（"我该并行化什么？"）。
- **修复建议**: 移除 Parallel Set C 标签，直接将 S24 列为主 serial spine 的一部分（在 S23 aging 之后、S25 death_cleanup 之前）。

#### M2. R/W 矩阵对 S11-S13 HitPoints 列标记有误导性

- **文件**: `specs/core/06-phase2b-system-manifest.md`
- **位置**: §4 R/W 矩阵
- **描述**: S11 `attack_system`、S12 `ranged_attack_system`、S13 `heal_system` 在 HitPoints 列标记为 `W`。但实际上它们写入 `PendingDamage[target_id]` / `PendingHeal[target_id]` 子缓冲区，**不直接修改 Entity.hits**。S15 才是 HitPoints 的 UNIQUE writer。标记 `W` 会让实现者误以为它们可以直接写 HitPoints，破坏 unique writer contract。
- **影响**: 实现者可能绕过 PendingDamage buffer 直接在 S11-S13 中写 HitPoints，导致并行数据竞争和 unique writer contract 被破坏。
- **修复建议**: 在 R/W 矩阵中为 S11-S13 的 HitPoints 列改为特殊标记（如 `B` = "writes to buffer"）或注释说明，使 unique writer contract 在矩阵层面可见。或在矩阵上方增加图例说明。

#### M3. 同类型特殊攻击重复命中的处理逻辑仅在 command-validation 中定义

- **文件**: `specs/core/02-command-validation.md` §3.16 vs `specs/core/06-phase2b-system-manifest.md` §S14
- **位置**: command-validation §3.16 "同类型多次命中" 表
- **描述**: Leech 的 "累加：leech_total = sum(leech_i)（不超过 target HP）" 和 Fabricate 的 "累加：各独立构造，无冲突" 仅在 `02-command-validation.md` 的 §3.16 表中定义。`06-phase2b-system-manifest.md` 的 S14 reducer 描述仅涉及异类型优先级裁决（Hack > Drain > ...），没有声明同类型累加逻辑。S22 `status_advance_system` 的伪代码也没有体现同类型累加规则。
- **影响**: S14/S22 实现者可能不知道 Leech 需要累加多个攻击者的 drain 量，导致只应用第一个 Leech 的效果。
- **修复建议**: 在 manifest §S14 的 reducer resolve 步骤中增加同类型多 intent 的处理规则（累加/取首/独立），引用 command-validation §3.16 的权威表或直接在 manifest 中重述。

---

### Low

#### L1. R/W 矩阵 S27 的 Controller 列标记有歧义

- **文件**: `specs/core/06-phase2b-system-manifest.md`
- **位置**: §4 R/W 矩阵 S27 行
- **描述**: S27 `room_state_system` 在 Controller 列标记为 `W`，但系统详情显示它写入 `Room (state, controller_level)`——即 Room 的 controller_level 字段，非 Controller component。Controller component 由 S02 和 S28 写入。
- **影响**: 低——CI 静态分析可能需要区分 Component 和 Resource 的写入，Room.controller_level 不属于 Controller component。
- **修复建议**: 在矩阵的 Controller 列标题增加注释 "Controller component + Room.controller_level"，或拆分为两列。

#### L2. engine.md §3.4.7 keyframe 间隔值无问题但缺少与 api-registry 的交叉引用

- **文件**: `design/engine.md`
- **位置**: §3.4.7 line 459
- **描述**: engine.md 写 "每 K=100 tick 写入一次 keyframe"，api-registry §5.4 同样写 "K=100"。值一致，但 engine.md 没有显式引用 api-registry 为权威源（类似它在上文 §3.4.2 的做法）。
- **影响**: 低——值一致，但未来若单方面修改 api-registry 中的 K 值，engine.md 可能成为孤立过时引用。
- **修复建议**: 增加 "权威值见 api-registry.md §5.4" 的交叉引用。

---

## 3. 亮点

1. **确定性闭合设计完整**：Blake3 XOF 覆盖 PRNG、canonical sort key 五层分层（priority_class → shuffle_index → source_rank → sequence → command_hash）、Seed 生命周期模型（Arena commit-reveal + World operator seed-bump）形成端到端确定性链。回放输入封套（TickInputEnvelope 22 字段）覆盖了从模块哈希到 visibility truncation version 的所有潜在分叉源。

2. **Phase 2a/2b 职责分离清晰且理由充分**：玩家命令 inline 执行（先到先得竞争有意义）vs 被动系统 deferred 执行（有依赖关系串行、无竞争并行）。Move-as-action 的单 action slot 设计有明确的 philosophic commitment 和 determinism 论证。

3. **Status Effect 管线重构（R30 B1）彻底**：S01 → PendingSpecialAttackIntent → S14 reducer → S16-S22b typed buffer → S22 unique StatusState writer 的五层管线完全消除了并行写入 StatusState 的风险。Unique Writer Contract 表逐项列出 8 个 StatusState component 的唯一写入者。

4. **持久化分层合同完整**：FDB replay-critical subset（10 字段不可降级）vs 对象存储 RichTraceBlob（可降级、可延迟）的分离贯穿 tick commit、deploy 状态机、GC、blob 损坏终端状态。`terminal_state` 四态模型（verified/audit_gap/unreplayable/reconstructable）覆盖了所有损坏恢复场景。

5. **容量推导有数学论证**：500/1000 player capacity derivation（engine.md §3.4.2）逐项列出假设和计算路径，Aggregate CPU Admission Formula 和 Per-Player Fair-Share Admission 有明确的预算分配逻辑。Benchmark gate 要求（persistence contract §8.3）将容量声明与实现验收绑定。

6. **反制窗口矩阵（command-validation §3.16）**：以表格清晰定义每种特殊攻击的可 Disrupt/Fortify 反制能力和时间窗口，包括 Hack 的 5-stage 内可 Disrupt、夺取后不可逆的精确语义。

---

## 4. CrossCheck

以下问题超出 Architect（架构）方向范围，需要其他评审方向确认：

- **CX-1**: Leech 和 Fabricate 的 body part 映射未定义 → 建议 **Gameplay 评审员** 检查 `design/gameplay.md` 和 `specs/gameplay/08-api-idl` 中是否已定义 Leech/Fabricate 的 body part 要求及 damage formula
- **CX-2**: Recycle 语义（self-action vs spawn-anchored）需要裁决 → 建议 **Game Mechanics 评审员** 检查 economic balance：Recycle 退还到全局存储 vs 特定 spawn 对玩家策略的影响
- **CX-3**: Overload `target_id` 类型 (EntityId vs PlayerId) 影响 WebSocket/MCP API schema → 建议 **Interface/API 评审员** 检查 `design/interface.md` 和 MCP tool schema 中 Overload 的 target 参数类型
- **CX-4**: S15 缺少 `Without<DeathMark>` guard 可能导致已死亡实体被 Tower 攻击 → 建议 **Security 评审员** 检查此漏洞是否可被利用为 DoS（堆叠尸体吸收 Tower 火力）
- **CX-5**: Leech/Fabricate 的 `custom_actions` 注册方式（02-command-validation §8 "注册方式: [[custom_actions]]"）与核心 CommandAction 变体的 IDL 注册路径是否一致 → 建议 **API/Codegen 评审员** 检查 `game_api.idl.yaml` 中 Leech/Fabricate 的注册状态