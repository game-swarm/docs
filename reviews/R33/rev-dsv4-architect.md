# R33 Architect Review — DeepSeek V4 Pro

## Verdict
**REQUEST_MAJOR_CHANGES** — 架构骨架正确（确定性闭合完整、Phase 2a→2b 调度链清晰、Shadow Write + Atomic Publish 持久化模型严谨、Worker Pool 水平可扩展推导充分），但存在 3 个 Critical 问题（Leech/Fabricate 校验矩阵缺失、Overload target_id 类型不一致、ClaimController handler 分配歧义）和 3 个 High 问题（Global transfer handler 映射缺口、HitPoints unique writer 声明歧义、StatusState 矩阵覆盖不完整）需要修复后方可进入 Phase 2。

---

## Critical（必须修复，否则 BLOCK）(B1..B3)

- **B1**: Leech 和 Fabricate 缺少独立的指令校验节（`02-command-validation.md`）——文档 §3.10–3.15 覆盖 Hack/Drain/Overload/Debilitate/Disrupt/Fortify 六种特殊攻击的逐字段校验矩阵，但 Leech (§3缺失) 和 Fabricate (§3缺失) 没有任何校验矩阵。字段级穷举校验表（§6）中也无 Leech/Fabricate 行。R30 B1/D5 明确「全部 8 种特殊攻击为核心目标设计——不存在 Tier 2/Phase/Future 语义」，但校验文档仅覆盖 6 种。影响：实现者无法据此实现 Leech/Fabricate 的 validate_and_apply() 路径；CI manifest 一致性检查通过但校验覆盖不完整。**修复**: 在 `02-command-validation.md` 中新增 §3.17 Leech 逐字段校验和 §3.18 Fabricate 逐字段校验，同时在 §6 字段级穷举表中补全 Leech/Fabricate 行（含所有权/范围/数量/资源/坐标/特殊校验七维度）。

- **B2**: Overload 的 `target_id` 类型语义不一致 —— `api-registry.md` §1.3 定义 Overload 参数为 `target_id: EntityId`（与所有其他 CommandAction 一致），但 `02-command-validation.md` §3.12 校验逻辑以 `target_id` 为 player_id（「target_id 是有效的 player_id」、`NotVisibleOrNotFound`），`engine.md` §3.12 Overload 语义描述也指向玩家级 fuel budget 削减。EntityId 语义下无法表达「同一 (world_id, target_player_id) 每 50 tick 全局冷却」。影响：IDL schema 与校验逻辑分裂——若 strict 按 EntityId 解析，Overload 校验将错误地将 entity ID 当作 player ID 查找；若放宽，则 CommandAction schema 的类型安全被打破。**修复**: 将 Overload 的 `target_id` 重新定义为专用目标类型（`OverloadTarget` 或显式 `PlayerId`），通过 `CustomActionRegistry` 注册独立 schema 和校验路径，与其他 CommandAction 的 EntityId 域分离。同时在 IDL YAML 中更新 Overload 的 parameter type 定义，重新运行 `generate_api_registry.py`。

- **B3**: ClaimController handler 分配歧义 —— `06-phase2b-system-manifest.md` §2 S01 `command_executor` 的 Handled Commands 列表中包含 `Claim`，S02 `controller_system (phase 2a)` 也列出 `Claim, UpgradeController`。「Claim」在 S01 和 S02 中同时出现，无法确定哪一个 handler 实际执行 ClaimController 命令。R/W 矩阵（§4）显示 S01 写入 `Position/HitPoints/Fatigue`（不写 Controller），S02 写入 `Controller`——暗示 S02 是实际 handler、S01 的 `Claim` 条目是文档错误（可能是 Hack 的 Claim body part 激活混淆）。影响：若按 S01 的 Handled Commands 列表实现，ClaimController 会被路由到错误的 handler，导致 Controller 状态不更新。**修复**: 从 S01 的 Handled Commands 列表中移除 `Claim`（S01 不处理 ClaimController）；仅在 S02 中保留。同时在 S01 注释中澄清 Hack 的 body part 检查（`Claim` body part）不意味着 S01 处理 ClaimController 命令。

---

## High（强烈建议修复）(H1..H3)

- **H1**: TransferToGlobal 和 TransferFromGlobal（CommandAction #12/#13）缺少 Phase 2a inline handler 映射 —— `06-phase2b-system-manifest.md` §2 S05 `transfer_system` 的 Handled Commands 为 `Transfer, Withdraw`（本地转移），未列出 `TransferToGlobal`/`TransferFromGlobal`。`api-registry.md` §1.2 将这些指令路由至「Economy Operation 管线」进行验证和执行，但 manifest 中没有声明对应的 Phase 2a handler system_id。S29 `resource_ledger` 是 Phase 2b 末端系统，不适合处理 Phase 2a 级别的校验+扣费。影响：实现者在 manifest 中找不到这两个命令的 handler 注册点；CI manifest 一致性检查可能遗漏此缺口。**修复**: 在 manifest 中新增 S05a（或扩展现有 S05）明确声明 TransferToGlobal/TransferFromGlobal 的 inline handler，并补充对应的 R/W 矩阵行。或者，若设计意图是 Economy Operation 走独立于 Phase 2a 的路径，需在 manifest §1 中显式声明 Economy Operation 管线的调度位置和与 Phase 2a/2b 的时序关系。

- **H2**: S01 与 S15 的 HitPoints 写入冲突 Unique Writer 声明 —— `06-phase2b-system-manifest.md` §2 S15 声明「S15 是 HitPoints 的 UNIQUE 写入者。除 S10 regen 外唯一写 Entity.hits 的 system」。但 R/W 矩阵（§4）同时标记 S01（`cmd_exec`）的 `HitPoints` 列为 `W`。Attack/RangedAttack 在 Phase 2a 直接修改 HP（`engine.md` §3.2 确认）。时序上 Phase 2a 先于 Phase 2b，无并行 race，但 Unique Writer 声明未区分 Phase 边界，导致静态分析工具可能误报冲突。影响：CI Unique Writer 验证逻辑若严格按矩阵执行，会在 S01/S15 的 HitPoints 写入上产生假阳性。**修复**: 在 S15 的 Unique Writer 声明中加限定词「S15 是 Phase 2b 中 HitPoints 的 UNIQUE 写入者。S01 在 Phase 2a 中的 HitPoints 写入已完成，S10 在 S15 之前串行执行」。同时在 R/W 矩阵 `HitPoints` 列补充脚注说明 Phase 2a（S01-S06）与 Phase 2b（S07-S29）的写操作具有时间顺序隔离。

- **H3**: `04-wasm-sandbox.md` §3.2 允许的 Host Function 列表缺失 `host_get_random` —— sandbox 文档列出 5 个 host function（terrain/objects_in_range/path_find/world_config/world_rules），但 `api-registry.md` §4.1 列出 6 个（含 `host_get_random`）。`api-registry.md` 是 IDL 生成的机器权威源，sandbox 文档为手写。影响：SDK 开发者可能误以为 WASM 模块无法获取确定性随机数；sandbox 白名单实现可能遗漏 `host_get_random` 的导入校验。**修复**: 在 `04-wasm-sandbox.md` §3.2 的允许 Host Function 列表中显式添加 `host_get_random` 的签名和说明（标注 domain separation 语义）。同时验证 `ALLOWED_HOST_FUNCTIONS` 常量包含此函数。

---

## Medium（建议关注）(M1..M4)

- **M1**: `engine.md` §3.2 Phase 2a 流程描述「Spawn 命令在 Phase 2a 中只校验不入队」略有不精确——`06-phase2b-system-manifest.md` S06 明确指出 Phase 2a spawn_validator 执行「校验 + 扣费（body_cost deduction）+ 入队 PendingSpawn」。`body_cost` 的扣除是副作用（写入 ResourceAmount），应在高层流程描述中体现，避免读者误以为 Spawn 在 Phase 2a 中完全不产生状态变更。建议改为「Spawn 命令在 Phase 2a 中校验 + 预扣费 + 入队 PendingSpawn，实际 drone 创建推迟到 Phase 2b S08」。

- **M2**: `02-command-validation.md` §3.12 Overload 校验未明确 RNG 来源——Overload 的抗性成功率判定需要 PRNG，但文档未说明使用的是引擎侧 Blake3 XOF（确定性）还是其他 RNG 源。特殊攻击的抗性/成功率判定应统一声明 RNG namespace（如 `combat` 或专用 `spec_atk` namespace），与 `01-tick-protocol.md` §9.5 的 RNG namespace 隔离模型对齐。建议在 Overload 校验节末尾追加 RNG contract 说明。

- **M3**: `09-snapshot-contract.md` §1.5 竞技截断降级规则使用术语 `action_range`（「移除了任何一个玩家可合法交互的实体（位于 action_range 内但被截断）」），但该术语在 snapshot-contract 或关联文档中未定义。`action_range` 可能指 `MAX_QUERY_RANGE (10)` 或 per-drone 的实际操作范围（Attack range=1, RangedAttack range=3, Heal range=3 等）。建议明确定义或交叉引用 `02-command-validation.md` §3 中各 action 的 range 参数。

- **M4**: `02-command-validation.md` §5.1 拒绝响应表中列出 `MainActionQuotaExceeded` 作为拒绝码，但 `api-registry.md` §2 RejectionReason 枚举中无此 canonical code。Main action quota 超出应映射到现有 canonical code（如 `CooldownActive` 配合 debug_detail），或需要在 IDL YAML 中新增 wire enum 变体。建议：要么在 api-registry 中注册此码，要么在 command-validation 中将其标记为 `(debug_detail)` 模式并映射到 `CooldownActive` canonical code。

---

## Low / Nits（可选改进）(L1..L4)

- **L1**: `engine.md` §3.1a Room 状态机图中 `owned ↔ contested` 为双向箭头，但正文仅描述了 neutral/reserved→contested 的触发路径（两玩家同时 Claim）。`owned → contested` 的触发条件缺失——已占领的房间在何种情况下进入 contested？若设计意图是不允许 owned→contested（需要先 abandoned→neutral→contested），应修正状态机图为单向 `→ contested` 而非 `↔`。

- **L2**: `engine.md` §3.1a 描述 Controller「Repair 降低 drone age」但未说明 Controller repair 的触发方式——是玩家通过 CommandAction 触发还是被动系统（如 depot/controller 自动维修）？`design/gameplay.md` 可能有详细定义，但 engine.md 的概述性描述应与 gameplay 文档的 repair 机制交叉引用。

- **L3**: `07-world-rules.md` 长度 1242 行，混合了 Rhai 模组规范、world.toml schema、body part 定义（§7.1）、structure 定义（§7.2）。其中 body part 和 structure 的详细定义（含 default cost/hits/rcl 等游戏数据）属于数据定义范畴，置于 world-rules 文档下稀释了「规则引擎」的核心关注点。建议将 §7 的游戏数据定义提取到独立文档（如 `specs/gameplay/body-parts.md` 和 `specs/gameplay/structures.md`），world-rules 保留对它们的引用。

- **L4**: `api-registry.md` §4.5 Host Function ABI 错误优先级中 `ERR_TIMEOUT`（priority 9）标注「仅在线执行，replay 不重跑 COLLECT」。replay 验证器处理 timeout 时以 `terminal_state = TimeoutExceeded` 而非重新执行 WASM——此语义正确，但建议在 `01-tick-protocol.md` §6.3 的回放协议中显式声明「replay verifier 读取 terminal_state 字段，对于 TimeoutExceeded 的 tick 不尝试重新执行 WASM，直接使用记录的 Command[] 进行状态回放」。

---

## Strengths（设计亮点）

1. **Shadow Write + Atomic Publish 持久化模型**（`01-tick-protocol.md` §3.5）：彻底消除了旧模型中「per-room 写入已持久化但全局 abort」的时序窗口。Staging 行不是已提交状态，GlobalTickCommit 是唯一 publish 点——此设计是分布式事务中少见的干净抽象，推导严密。

2. **Phase 2a/2b 分离 + Unique Writer Contract**（`06-phase2b-system-manifest.md`）：Inline 命令执行与 Deferred 系统调度的边界清晰。「先到先得」竞争模型在 Phase 2a 实现，被动系统在 Phase 2b 以 serial spine + parallel sets 调度。StatusState 的唯一写入者（S22）和 HitPoints 的唯一写入者（S15）合同 + CI 静态验证构成了强确定性保证。

3. **Worker Pool 容量推导**（`engine.md` §3.4.2）：500/1000 玩家容量从 per-player WASM p50/p99 执行时间、Collect budget、并行度逐层推导，不是拍脑袋数字。Aggregate CPU Admission Formula 和 per-player fair-share 机制完整。正确识别了真正瓶颈（Phase 2 sandbox 串行执行、per-player WASM 执行时间），而非 worker pool 本身。

4. **确定性合同分层完整**（`01-tick-protocol.md` §9）：五层命令排序键（priority_class → shuffle_index → source_rank → sequence → command_hash）保证了任意玩家集的确定性全序。RNG namespace 隔离（combat/loot/npc_spawn/event）、Blake3 单原语覆盖哈希+PRNG、BTreeMap 替代 HashMap——每个非确定性源都有明确的替代方案和 contract 约束。

5. **持久化分层（replay-critical vs debug/rich）**：`05-persistence-contract.md` 明确声明 TickCommitRecord 的 10 个 FDB 原子字段 + terminal_state 四态模型（verified/audit_gap/unreplayable/reconstructable），对象存储中的 RichTraceBlob 可降级但不可影响 deterministic replay。WASM 模块 blob 非 replay-critical（D6 裁决）——这消除了「WASM 二进制丢失导致世界状态不可回放」的常见误区。

6. **Snapshot 截断合同**（`09-snapshot-contract.md` §1）：确定性截断顺序（距离桶 → entity_id 字典序 → farthest-first）+ 关键实体永不截断 + 竞技降级标记——在 256KB 硬约束下最大化信息保留，同时防范 oracle 攻击（截断模式不可被玩家利用来推断隐藏实体分布）。

7. **Allied Transfer 拦截设计**（`09-snapshot-contract.md` §3.2a）：R27 E-H1 裁决的最终设计——200 tick 延迟窗口中 50 tick 可拦截窗口、窃取/销毁双模式、escort 防御、确定性 RNG——在「核心机制即最终设计」原则下做到了简洁且可扩展（完整物流战留给 mod）。

---

## CrossCheck — 需要跨方向检查

- **CX1**: `specs/future/T3-shard-protocol.md` 与核心架构兼容性 → **建议 Security Reviewer** 检查 T3 分片协议的水平扩展模型是否与 Shadow Write + Atomic Publish 持久化模型兼容（跨分片 GlobalTickCommit 的原子性在水平分片下是否需要两阶段提交），以及分片边界上的跨房间操作（Cross-Room Intents）在分片场景下的 all-or-reject 语义如何保持。

- **CX2**: Leech 和 Fabricate 的 body part 定义 → **建议 Gameplay Reviewer** 检查 `07-world-rules.md` §7.1 身体部件类型中是否注册了 Leech/Fabricate 所需的 body part 类型（当前仅列出 8 种基础类型：Move/Work/Carry/Attack/RangedAttack/Heal/Claim/Tough），以及 `specs/gameplay/` 下是否有 Leech/Fabricate 的详细参数（damage_type, base_damage, cost, cooldown）定义。

- **CX3**: Overload target_id 类型修复 → **建议 Security Reviewer** 检查将 Overload 的 `target_id` 改为 PlayerId 后，`02-command-validation.md` §5 的可见性优先原则如何处理——`NotVisibleOrNotFound` 语义下，攻击方如何通过 is_visible_to 验证目标 player（需有至少一个 drone 在目标玩家视野内），以及此检测是否会产生 oracle 信息泄露。

- **CX4**: `02-command-validation.md` §7.2 退还时序中的 fuel refund → **建议 Economy Reviewer** 检查 fuel refund 与 Resource Ledger 的资源 refund 之间的独立性边界——fuel refund 操作 fuel budget（§7.2），resource refund 操作 ResourceStore（Spawn body_cost refund），两者在 S22/S29 中是否有交叉结算窗口。`01-tick-protocol.md` §9.4 确认两者为独立资源池，但需要实现级验证。

- **CX5**: `07-world-rules.md` §5 Rhai 事务性执行模型的 Action Buffer → **建议 Security Reviewer** 检查 Rhai `actions.*` buffer 是否可能通过 `actions.set_world_param` 间接修改与 Command Validation Pipeline 共享的参数（如 damage_multiplier、resource regeneration rate），从而绕过「Rhai 不能绕过 Command Validation Pipeline」的隔离保证。