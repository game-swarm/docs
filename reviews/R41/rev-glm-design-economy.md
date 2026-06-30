# R41 Phase 1 独立评审 — Design & Economy (游戏机制 + 经济模型 + API/DX)

**评审员**: rev-glm-design-economy (GLM-5.2)
**评审轮次**: R41 Clean-Slate
**评审范围**: design/README.md, design/gameplay.md, design/modes.md, design/interface.md, design/economy-balance-sheet.md, specs/gameplay/06-feedback-loop.md, specs/gameplay/08-api-idl.md, specs/core/08-resource-ledger.md, specs/core/09-snapshot-contract.md, specs/reference/api-registry.md

---

## 1. Verdict

**CONDITIONAL_APPROVE**

整体设计成熟度高——经济分层 (Local/Global/Allied) 合理，防雪球合同自洽，deferred command model 干净。但存在若干文档间不一致（尤其是 IDL 与 API Registry 之间的 RejectionReason enum 脱节）和数值矛盾，需修复后方可 APPROVE。以下问题按 severity 分列。

---

## 2. 发现的问题

### DE-1 [Critical] — IDL RejectionReason enum 与 API Registry canonical 48 codes 严重脱节

**文件**: `specs/gameplay/08-api-idl.md` 第 67-112 行 vs `specs/reference/api-registry.md` §2

**问题**: IDL §2 的 `RejectionReason` enum 列出约 37 个旧式变体（`NotMovable`, `Fatigued`, `MissingBodyPart`, `TileBlocked`, `StillSpawning`, `OutOfRoom`, `NoPath`, `PathTooLong`, `InsufficientMoveParts`, `CarryFull`, `NotSource`, `SourceEmpty`, `TargetFull`, `TargetEmpty`, `NotYourRoom`, `TileOccupied`, `InvalidTerrain`, `TooManyConstructionSites`, `AlreadyFullHealth`, `FriendlyTarget`, `NotYourSpawn`, `BodyTooLarge`, `ExceedsRoomCapacity`, `NotFriendly`, `AlreadyHacked`, `InvalidDamageType`, `AlreadyDebilitated` 等）。

但 API Registry §2 明确声明 48 个 canonical codes，且 §2.6 的 condition → RejectionReason → debug_detail 映射表指出这些旧变体应映射到 canonical code（如 `Fatigued` → `CooldownActive`、`NotMovable` → `CooldownActive`、`CarryFull` → `InsufficientResource`）。IDL 自身的注释（第 68 行）也写了 "权威定义见 API Registry §2 — 48 变体"，但 enum body 与权威源完全矛盾。

**影响**: IDL 声称是 codegen 的唯一真相源（"一个 IDL 生成所有绑定"），但 IDL enum 与 Registry 的实际 canonical codes 不一致。如果 codegen 从 IDL 生成 SDK，SDK 会暴露错误的 RejectionReason 类型，破坏 wire enum 合同。

**修复建议**: 将 IDL §2 的 `RejectionReason` enum 完全替换为 API Registry §2 的 48 个 canonical codes（Pipeline 2 + Validation 29 + MCP 3 + Runtime 6 + Auth 12），删除所有旧式变体。旧变体对应的 condition 通过 `debug_detail` 模板表达。

---

### DE-2 [Critical] — IDL CommandAction 注释与变体数量错误

**文件**: `specs/gameplay/08-api-idl.md` 第 115 行

**问题**: IDL commands 区注释写 `# > 权威定义见 [API Registry](../reference/api-registry.md) §1 — 19 指令`，但 API Registry §1 明确声明 "11 个 CommandAction + ActionRegistry"，变体总数为 11 + Action dispatch = 12 entries（含8 个核心 + 2 个 economy + 1 个 Action dispatch，编号 1-13+22）。"19 指令" 是旧版计数。

此外，IDL commands 区列出 Move/Harvest/Transfer/Withdraw/Build/Spawn/Recycle/ClaimController/Action = 9 entries，缺少 `TransferToGlobal` 和 `TransferFromGlobal`（它们被放在了 `global_storage_commands` 子区，虽然 API Registry §1.2 将它们归类为 EconomyOperation CommandAction）。

**影响**: IDL 与 Registry 对 CommandAction 总数和分类不一致，codegen 可能遗漏 economy operation 指令的 SDK 绑定。

**修复建议**: 更新 IDL 注释为 "11 个 CommandAction + ActionRegistry"。将 `TransferToGlobal`/`TransferFromGlobal` 归入 `commands:` 区（或明确注释它们是 CommandAction 的 economy_operation lane）。

---

### DE-3 [High] — Fabricate Energy 成本矛盾

**文件**: `design/gameplay.md` 第 766 行 vs 第 1218 行

**问题**: gameplay.md §Vanilla Action 概念表（第 766 行）写 Fabricate cost = `800 Energy`，但同文件 `[action_registry.vanilla.Fabricate]` TOML（第 1218 行）写 `cost = { Energy = 2000 }`。两处自相矛盾。

**影响**: 实现者无法确定 Fabricate 的实际资源消耗。

**修复建议**: 统一为一个值。考虑到 Fabricate 是强力转化技能（将敌方 drone 变为己方建筑，500 tick CD），2000 Energy 更合理。更新概念表第 766 行为 2000 Energy。

---

### DE-4 [High] — Leech damage_type / resistance 矛盾

**文件**: `design/gameplay.md` 第 765 行 vs 第 1094 行 vs 第 1205-1206 行

**问题**:
- 概念表（第 765 行）：Leech resistance = "目标 `Kinetic` 抗性"
- `[[special_effects]]` leech 定义（第 1094 行）：`resistance = "Corrosive"`
- `[action_registry.vanilla.Leech]` TOML（第 1205-1206 行）：`damage_type = "Corrosive"`, `base_damage = 15`

概念表说抗性是 Kinetic，但 special_effects 和 registry 都说 Corrosive。三处中两处一致 (Corrosive)，一处矛盾 (Kinetic)。

**影响**: 实现者可能按错误抗性类型计算 Leech 命中和伤害减免。

**修复建议**: 统一为 Corrosive。更新概念表第 765 行的 resistance 为 "Corrosive"。

---

### DE-5 [High] — Fabricate body part 需求矛盾

**文件**: `design/gameplay.md` 第 766 行 vs `specs/gameplay/08-api-idl.md` 第 276 行

**问题**: gameplay.md 概念表写 Fabricate 触发 body part = "Work"，但 `08-api-idl.md` §5.1 变体列表写 "Work+Carry"。

**影响**: 玩家不知道 Fabricate 需要什么 body part，SDK 类型定义会与游戏规则不一致。

**修复建议**: Fabricate 将敌方 drone 转化为建筑，需要 Work（建造能力）+ Carry（携带建筑资源？）。统一为 "Work+Carry"，更新 gameplay.md 概念表。

---

### DE-6 [High] — allied_daily_cap 动态公式 vs 固定值矛盾

**文件**: `specs/core/08-resource-ledger.md` 第 83 行 vs `specs/core/09-snapshot-contract.md` 第 215 行 vs `specs/reference/api-registry.md` 第 861 行

**问题**:
- Resource Ledger §2.1（权威源）：`allied_daily_cap = max(10_000, receiver_gcl × 20_000)` — 动态，按接收方 GCL 缩放
- snapshot-contract.md §3.2：`allied_daily_cap = 10,000 units` — 固定值
- API Registry §10.2：`Daily cap: 10,000 units per receiver` — 固定值

Resource Ledger 声明自己是 "唯一经济权威"，但另外两个文档的数值与公式不符。

**影响**: 实现者不知道应实现动态公式还是固定 10,000 上限。对于一个 GCL=5 的玩家，动态公式给出 `max(10000, 100000) = 100,000`，与固定 10,000 差 10 倍。

**修复建议**: 统一为 Resource Ledger 的动态公式。更新 snapshot-contract.md 和 API Registry §10.2 引用公式而非固定值。或者，如果实际设计意图是固定 10,000（动态公式是过度设计），则更新 Resource Ledger。

---

### DE-7 [High] — Balance Sheet storage_capacity 数值跳变无解释

**文件**: `design/economy-balance-sheet.md` §2.7 汇总表（第 182-190 行）

**问题**: storage_capacity 在不同房间数场景下跳变：
- 1-5 rooms: 1,000,000
- 10 rooms: 3,000,000
- 20 rooms: 2,000,000（比 10 rooms 减少）
- 50 rooms: 3,000,000

20-room 的 storage_capacity (2M) 小于 10-room (3M)，这在逻辑上不合理——更大的帝国不应有更少的存储容量。Resource Ledger §2.1 说默认 `global_storage_capacity = 1,000,000 units/player`，但 balance sheet 在不同场景使用了不同值且无解释。

**影响**: 存储税计算依赖 storage_capacity，错误的容量导致税收估算偏离。也让 balance sheet 的自洽性存疑。

**修复建议**: 明确 storage_capacity 的语义——是 per-player 固定值（=1,000,000）还是随房间数增长（如 `base + room_count × per_room_bonus`）？统一所有场景的计算逻辑，并在 §2.7 表中标注计算公式。

---

### DE-8 [Medium] — IDL Spawn/Recycle 参数签名与 API Registry 不一致

**文件**: `specs/gameplay/08-api-idl.md` 第 142-149 行 vs `specs/reference/api-registry.md` §1.1

**问题**:
- IDL Spawn: `params: { spawn_id: ObjectId, body: Vec<BodyPart> }` — 字段名 `body`
- API Registry Spawn: `body_parts: [BodyPart], spawn_id: SpawnId` — 字段名 `body_parts`
- IDL Recycle: `params: { object_id: ObjectId, spawn_id: ObjectId }` — 两个参数
- API Registry Recycle: `object_id: EntityId (self-action)` — 仅一个参数

**影响**: SDK codegen 如果从 IDL 生成，字段名和参数数量与 Registry 权威定义不一致。

**修复建议**: 更新 IDL 以匹配 API Registry：Spawn 字段改 `body_parts`，Recycle 改为 self-action（仅 `object_id`）。

---

### DE-9 [Medium] — tick() 返回格式歧义

**文件**: `specs/gameplay/08-api-idl.md` 第 189-192 行 vs `design/gameplay.md` §2.9 第 2019-2036 行 vs `design/interface.md` §5 第 59-60 行

**问题**:
- IDL: `tick` returns `i32` (0 = success, pointer to command JSON)
- interface.md: `tick(snapshot) → Command[]` — 返回指令列表
- gameplay.md §2.9: tick() 返回 `{ commands, messages }` — 返回包含 commands 和 messages 的结构体

三处对 tick() 的返回格式描述不一致。gameplay.md 引入了 messages 返回路径但 IDL 和 interface.md 都未反映。

**影响**: WASM ABI 合同不明确——实现者不知道 tick() 是否应返回包含 messages 的复合结构，还是仅返回 commands。

**修复建议**: 在 IDL 中明确 tick() 的返回格式为 `{ commands: Command[], messages?: Message[] }`（或仅 commands，messages 通过其他机制传递）。同步更新 interface.md 和 gameplay.md。

---

### DE-10 [Medium] — IDL refund_policy 未在权威源中定义

**文件**: `specs/gameplay/08-api-idl.md` 第 231-233 行

**问题**: IDL 末尾有 `refund_policy` 段，定义 `contention_lost: 0.5`（SourceEmpty/TileOccupied/TargetFull 时退还 50%）和 `self_invalid: 0.0`（OutOfRange/Fatigued 不退）。但此 refund_policy 概念未出现在 API Registry、Resource Ledger 或任何其他文档中。Resource Ledger 的 `ResourceOperation` 枚举中也没有 refund-related operation。

**影响**: 退款规则是否为当前设计的一部分不明确。如果 codegen 从 IDL 生成 validator 逻辑，会引入未在其他文档中定义的游戏规则。

**修复建议**: 如果 refund_policy 是当前设计，在 Resource Ledger 中补充定义并在 API Registry 中注册。如果已废弃，从 IDL 中移除。

---

### DE-11 [Medium] — Economy balance sheet "代码效率乘数" 无权威定义

**文件**: `design/economy-balance-sheet.md` §2（第 39 行）及全文

**问题**: Balance sheet 的核心论据——"2-10 房间自维持可达"——依赖于 "优化代码 ×1.5-2.0 效率" 乘数。但这个乘数从未被正式定义：
- 没有公式说明 1.5× = 什么条件（减少 idle X%？优化路径 Y%？）
- 没有上限/下限约束
- 没有在 Resource Ledger 或 API Registry 中注册

**影响**: Balance sheet 的自维持论证基于一个无法验证或实现的乘数。Playtest 可以校准参数，但当前乘数的语义不明确。

**修复建议**: 在 economy-balance-sheet.md 或 Resource Ledger 中明确定义效率乘数的计算维度（idle ratio、path efficiency、parallelism factor 等）和取值范围。或者标注此乘数为 illustrative estimate 的输入假设，与 balance sheet 的 illustrative 定位一致。

---

### DE-12 [Medium] — Repair distance decay 参数与 gameplay.md 矛盾

**文件**: `specs/reference/api-registry.md` 第 562 行 vs `design/gameplay.md` 第 274 行 vs `specs/core/08-resource-ledger.md` 第 166 行

**问题**:
- API Registry §5.1: `Repair distance decay: 500 bp/tile (R23 D4/A)` — 作为权威参数
- gameplay.md 第 274 行: "全局 repair_cap、按 body_cost 收费的 repair_cost、距离衰减收费等比例经济公式不属于 Vanilla age repair 权威模型"
- Resource Ledger §2.4: "全局 repair_cap、repair_cost、distance_decay_bp 不属于基础经济账本权威公式"

API Registry 将 repair distance decay 列为权威参数，但 gameplay.md 和 Resource Ledger 都说它不属于 vanilla 模型。

**影响**: 实现者会困惑是否要实现 distance decay 收费。

**修复建议**: 如果 distance decay 不属于 vanilla 模型，从 API Registry §5.1 移除该行或标注为 "mod-optional, not vanilla"。如果它属于某次裁决（R23 D4/A）的最终设计，需更新 gameplay.md 和 Resource Ledger 以反映。

---

### DE-13 [Low] — allied_daily_cap_world_multiplier 语义未在其他文档展开

**文件**: `specs/core/08-resource-ledger.md` 第 84 行

**问题**: Resource Ledger §2.1 定义 `allied_daily_cap_world_multiplier = 100 (u32, scale×100)`，注明 "Standard=100=1.0×, Arena=50=0.5×, Tutorial=500=5.0×"。但 balance sheet §3 的模式差异表仅列 `allied_transfer_enabled` 的 bool 值，未引用此 multiplier。modes.md 也未提及 Arena 的 allied transfer cap 被减半。

**影响**: 模式间 allied daily cap 的差异未被完整传播到所有相关文档。

**修复建议**: 在 economy-balance-sheet.md §3 模式差异表或 modes.md Arena 配置中补充 `allied_daily_cap_world_multiplier` 的各模式默认值。

---

### DE-14 [Low] — global_storage_public 标注为"计划中"但已出现在参数表

**文件**: `design/gameplay.md` 第 362 行

**问题**: gameplay.md §全局存储反制机制 参数表包含 `global_storage_public | bool | false | （计划中）全局存储是否完全公开`。标注"计划中"与"设计即终态"评审原则冲突——如果它是当前设计的一部分应在文档中明确，如果是未来扩展应标注 RFC。

**修复建议**: 移除"计划中"标注，明确为当前设计参数（默认 false）或标注为 RFC-gated。

---

## 3. 亮点

1. **经济分层设计精良**: Local/Global/Allied Transfer 三层各有明确的约束（即时/延迟/受限），物流模式 A/B/C 覆盖了从休闲到硬核的玩家偏好。全局↔本地转换的不可即时性 (deposit_delay/withdraw_delay) 创造了非平凡的战略权衡——存储不是即时补给，物流规划是核心玩法。

2. **防雪球合同多层自洽**: 超线性维护费 (O(n²)) + 累进存储税 (4-tier) + Controller 老化 + No Teleport 物流成本，四个独立机制从不同角度抑制无限扩张。Balance sheet 的 1/2/5/10/20/50 房间数值闭环验证（虽然参数为 illustrative）展示了设计意图的可量化性。

3. **Deferred Command Model 干净**: WASM `tick() → Command[]` + 只读 host functions 是一个优雅的隔离设计。所有 mutating 操作通过 JSON 延迟提交，引擎统一校验后应用，天然防注入且保证确定性。禁止 host_move/host_attack 等 mutating host function 的设计合同清晰。

4. **Snapshot Truncation Contract 严谨**: 距离桶 + entity_id 字典序的确定性截断顺序、Critical Entity Size Reserve (128KB/256KB)、tick degraded 标记——这些细节表明设计者深入考虑了大帝国场景下的感知快照行为。

5. **Safe Hint Ladder 安全设计出色**: competitive/practice/training 三级错误提示模型有效防止了通过错误消息探测隐藏状态。competitive 模式下所有错误消息为常数字符串（无动态值）是正确的安全决策。

6. **Allied Transfer Intercept 机制 (R27 E-H1) 增加了战略深度**: 200 tick 延迟窗口中最后 50 tick 的可拦截设计，配合 Steal/Destroy 两种模式和 escort 防御，在不引入完整物流战 mod 的前提下提供了有意义的后勤博弈。

7. **Resource Ledger 单一经济权威的架构正确**: 将所有费率、公式、参数集中在 Resource Ledger §2 统一参数表中，其他文档只能引用不可重新声明——这是防止经济数值跨文档不一致的正确架构决策（尽管当前执行中仍有残留不一致）。

8. **PvE 生态层的地理难度梯度设计直觉**: 中心→中层→外层→边境的 Zone 1-4 难度递增，让 PvE 成为地理属性而非副本入口，自然融入 World 持久世界。NPC 行为由引擎内置 AI 驱动（非 WASM），确定性保证好。

---

## 4. CrossCheck — 需要跨方向检查

- **CX-1**: [IDL RejectionReason enum 完全使用旧式变体名，与 API Registry canonical 48 codes 矛盾] → 建议 **engine/determinism** 方向检查 codegen pipeline (`generate_api_registry.py`) 是否实际从 IDL YAML 生成 Registry——如果 IDL YAML（非 .md）中的 enum 也是旧式，codegen 产物会错误；如果 YAML 已更新但 .md 未同步，需确认 codegen 源到底是哪个文件。

- **CX-2**: [allied_daily_cap 在 Resource Ledger 中是动态公式 `max(10_000, GCL × 20_000)`，在 snapshot-contract.md 和 API Registry 中是固定 10,000] → 建议 **engine/architecture** 方向检查 allied transfer 的实际 enforcement 逻辑代码是否实现了 GCL 缩放，还是硬编码 10,000。

- **CX-3**: [API Registry §5.1 列出 "Repair distance decay: 500 bp/tile (R23 D4/A)" 作为权威参数，但 gameplay.md 和 Resource Ledger 都说 distance decay 不属于 vanilla age repair 模型] → 建议 **engine** 方向检查 repair 系统实际是否实现了 distance-based decay 收费，此参数是否为 dead config。

- **CX-4**: [tick() 返回格式歧义——IDL 说返回 i32 (pointer to JSON)，interface.md 说返回 Command[]，gameplay.md §2.9 说返回 { commands, messages }] → 建议 **engine/sandbox** 方向检查 WASM ABI 合同中 tick() 的实际返回内存布局和 messages 的传递机制（是同一返回缓冲区还是独立通道）。

- **CX-5**: [allied_daily_cap_world_multiplier (Standard=1.0×, Arena=0.5×, Tutorial=5.0×) 在 Resource Ledger 中定义，但 Arena 配置未在 modes.md 中展开] → 建议 **modes/pvp** 方向检查 Arena 世界是否真的允许 Allied Transfer（balance sheet §3 显示 Arena 禁用 Allied Transfer），如果禁用则 multiplier 无意义。

- **CX-6**: [IDL refund_policy (contention_lost: 0.5, self_invalid: 0.0) 未在任何权威文档中定义] → 建议 **engine** 方向检查 command validation pipeline 是否实际实现了部分退款逻辑，还是已移除。

- **CX-7**: [Balance sheet 中 storage_capacity 在 20-room 场景为 2M（少于 10-room 的 3M）] → 建议 **data-integrity** 方向验证 balance sheet 数值的数学一致性和可重算性，确认是否为笔误或有意设计。
