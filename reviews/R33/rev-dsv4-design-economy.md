# R33 Design & Economy Review — DeepSeek V4 Pro

## Verdict
**REQUEST_MAJOR_CHANGES**

Two Critical findings (structure cost triple-inconsistency, missing deposit delay in authoritative source) and five High findings. These are not new design questions — they are cross-document consistency errors that break the "single source of truth" contract. The anti-snowball architecture is sound and the gameplay/modes/interface design forms a coherent whole, but the economic parameter inconsistencies must be resolved before this review set can close.

---

## Critical (必须修复，否则 BLOCK) (B1..B2)

### B1: Structure Build Costs — Triple Inconsistency Across Three Documents

**Severity**: Critical

**Files affected**:
- `design/gameplay.md` §2.2 `[[structure_types]]` table (lines 118–229)
- `specs/core/07-world-rules.md` §7.2 `[[structure_types]]` table (lines 642–754)
- `specs/reference/economy.idl.yaml` §2.5 BuildCost (lines 226–279)

**Discrepancy table**:

| Structure | gameplay.md | world-rules.md | economy.idl.yaml |
|-----------|:-----------:|:--------------:|:----------------:|
| Spawn | **300** | **200** | **300** |
| Extension | **200** | **50** | **200** |
| Tower | **800** | **200** | **800** |
| Storage | 500 | 500 | 500 |
| Link | **400** | **300** | **400** |
| Extractor | **600** | **800** | **600** |
| Lab | 1000 | 1000 | 1000 |
| Terminal | **1200** | **500** | **1200** |
| Observer | **500** | **300** | **500** |
| PowerSpawn | 5000 | 5000 | **not listed** |
| Factory | 1500 | 1500 | **not listed** |
| Nuker | 100000 | 100000 | **not listed** |
| Depot | 5000 | 5000 | **not listed** |
| Road | **not listed** | **not listed** | **10** |
| Wall | **not listed** | **not listed** | **50** |
| Rampart | **not listed** | **not listed** | **100** |

**Analysis**: gameplay.md and economy.idl.yaml agree on most costs (Spawn=300, Extension=200, Tower=800, Link=400, Extractor=600, Terminal=1200, Observer=500). world-rules.md disagrees on 7 of 13 structures. Additionally, economy.idl.yaml lists Road/Wall/Rampart (not in gameplay.md or world-rules.md structure_types), and is missing PowerSpawn/Factory/Nuker/Depot.

**Impact**: The `specs/core/08-resource-ledger.md` claims to be the "唯一设计/数学权威" for all economic parameters. But three documents claim different numbers for the same structures. Implementers will face contradictory specs with no way to determine which is correct. The economy.idl.yaml is the machine-readable source, but even it's incomplete.

**Fix**: Establish _one_ authoritative source for structure build costs and propagate to all other docs. The `economy.idl.yaml` §BuildCost should be the canonical source (it's machine-readable and CI-checked). Add PowerSpawn/Factory/Nuker/Depot to economy.idl.yaml. Sync world-rules.md §7.2 to match economy.idl.yaml. Mark gameplay.md §2.2 as "see economy.idl.yaml for authoritative costs." Add Road/Wall/Rampart to gameplay.md and world-rules.md structure_types lists, or remove them from economy.idl.yaml (decision needed).

**D-item: B1-STRUCTURE-COSTS** — Which document is authoritative? economy.idl.yaml (machine-readable, CI-gated) or gameplay.md (human-readable design)? And should Road/Wall/Rampart be in the standard structure list?

---

### B2: `global_deposit_delay` Missing from Resource Ledger (Authoritative Source)

**Severity**: Critical

**Files affected**:
- `specs/core/08-resource-ledger.md` §2.1 统一参数表 (lines 69–98)
- `design/gameplay.md` §2.2 物流配置 (lines 308–359)

**Issue**: gameplay.md defines TWO separate delays:
- `global_deposit_delay` = 10 tick (本地→全局)
- `global_withdraw_delay` = 100 tick (全局→本地)

But resource-ledger.md §2.1 only lists ONE delay:
- `global_transfer_delay` = 100 tick

The deposit delay of 10 tick is **completely absent** from the claimed authoritative source. The single `global_transfer_delay = 100` could reasonably be interpreted as applying to both directions (making deposit = 100, not 10), which contradicts gameplay.md and economy-balance-sheet.md.

**Impact**: `specs/core/08-resource-ledger.md` is declared as "唯一经济权威" (line 7). A missing parameter breaks this contract. Implementers following resource-ledger alone would implement deposit delay = 100 instead of 10 — a 10× difference that fundamentally changes the logistics pacing.

**Fix**: Add both `global_deposit_delay = 10` and `global_withdraw_delay = 100` to resource-ledger.md §2.1 统一参数表. Rename or remove the ambiguous `global_transfer_delay`.

---

## High (强烈建议修复) (H1..H5)

### H1: RangedAttack Body Part Cost — 150 vs 100

**Severity**: High

**Files**:
- `design/gameplay.md` §[[body_part_types]]: RangedAttack cost = `{Energy: 150}` (line 890)
- `specs/core/07-world-rules.md` §7.1: RangedAttack cost = `{Energy: 100}` (line 579)
- `specs/gameplay/08-api-idl.md` §body_cost: RangedAttack = `{Energy: 150}` (line 230)
- `specs/reference/economy.idl.yaml` §SpawnCost: RANGED_ATTACK = 150 (line 329)

**Analysis**: Three documents say 150; world-rules.md alone says 100. The outlier is world-rules.md.

**Fix**: Correct world-rules.md §7.1 RangedAttack cost to 150.

---

### H2: Allied Transfer Daily Cap — GCL-Scaled vs Flat 10000

**Severity**: High

**Files**:
- `specs/core/08-resource-ledger.md` §2.1: `allied_daily_cap` = `max(10_000, receiver_gcl × 20_000)` (line 80)
- `specs/reference/economy.idl.yaml` §2.7: `daily_cap: 10000` (flat, line 384)

**Analysis**: resource-ledger defines a GCL-scaled formula (minimum 10k, scaling with receiver's GCL). economy.idl.yaml defines a flat 10,000 cap. These produce different limits for any player with GCL ≥ 1.

**Fix**: Update economy.idl.yaml to match resource-ledger's GCL-scaled formula, or decide on a single authoritative definition and propagate.

---

### H3: Terminal Description Contradiction — "跨世界身份同步" vs "市场交易接口"

**Severity**: High

**Files**:
- `design/gameplay.md` §2.2 Terminal: "跨世界身份同步与日志交换节点" (line 178)
- `specs/core/07-world-rules.md` §7.2 Terminal: "市场交易接口" (line 703)

**Analysis**: These describe fundamentally different building functions. gameplay.md says cross-world identity sync + log exchange. world-rules.md says market trading interface. The economy-balance-sheet.md §2.7 mentions "market trading" as "RFC 占位 — 不在当前设计范围内", which aligns more with the "market trading interface" interpretation. But gameplay.md describes Terminal as an identity/logistics node.

**Fix**: Align Terminal descriptions. If Terminal is cross-world identity sync (as gameplay.md states), world-rules.md must match. If it's a future market interface, gameplay.md must be corrected.

---

### H4: economy.idl.yaml BuildCost Includes Structures Not in gameplay.md

**Severity**: High

**Files**:
- `specs/reference/economy.idl.yaml` §2.5: lists Road (10), Wall (50), Rampart (100)
- `design/gameplay.md` §2.2: no Road/Wall/Rampart in default structure_types

**Analysis**: These three structure types exist in economy.idl.yaml but are absent from both gameplay.md §2.2 and world-rules.md §7.2 structure type lists. Either they should be added to the structure_types lists, or removed from economy.idl.yaml.

**Fix**: Add Road/Wall/Rampart to gameplay.md and world-rules.md structure_types, or remove from economy.idl.yaml.

---

### H5: Anti-Snowball "证明" — 描述性断言而非数学推导

**Severity**: High

**File**: `design/economy-balance-sheet.md` §4 (lines 226–234)

**Issue**: The "Anti-Snowball 证明" section states four design properties (边际收益递减, 净正反馈克制, 自然上限, No Teleport) but provides no mathematical derivation. It's a summary of design goals, not a proof.

The balance sheet's own data (§2.7) shows net-negative flow for ALL scenarios from 2 rooms onward (even with 1.5× code efficiency). The claim that "收支平衡在优化代码 + 适度扩张条件下可达" is not supported by the numbers in the very same document — even "优化" (×1.5) scenarios are all negative beyond free_upkeep.

The document explicitly defers to playtest data (§2.7 note): "精确参数和平衡点推迟至 Resource Ledger spec 实施/playtest 阶段确定." This is honest, but the heading "Anti-Snowball 证明" is misleading — it should be "Anti-Snowball 设计目标 (待 playtest 验证)."

**Fix**: Rename §4 heading to "Anti-Snowball 设计目标" and explicitly state that mathematical proof depends on playtest-calibrated parameters. Or provide a formal proof under the stated parameters showing that a break-even point exists at some expansion level.

---

## Medium (建议关注) (M1..M4)

### M1: Fabricate Cost Inconsistency — 800 vs 2000+Matter

**Severity**: Medium

**Files**:
- `design/gameplay.md` §特殊攻击表格: Fabricate cost = `800 Energy` (line 762)
- `specs/core/07-world-rules.md` §7.5 `[[custom_actions]]`: Fabricate cost = `{Energy: 2000, Matter: 500}` (line 972)
- `design/gameplay.md` §[[custom_actions]] (later section): Fabricate cost = `{Energy: 2000, Matter: 500}` (line 1213)

**Analysis**: gameplay.md has TWO entries for Fabricate cost — the special attack table says 800, the custom_actions section (further down in the same file) says {Energy: 2000, Matter: 500}. The latter matches world-rules.md. The special attack table entry is the outlier.

**Fix**: Update gameplay.md §special_attacks Fabricate cost to `{Energy: 2000, Matter: 500}`.

---

### M2: Overload `target_id` Type Mismatch — PlayerId vs EntityId

**Severity**: Medium

**Files**:
- `specs/gameplay/08-api-idl.md` §Overload: `target_id: PlayerId` (line 194)
- `specs/reference/game_api.idl.yaml` §Overload: `target_id: EntityId` (line 246)
- `specs/reference/api-registry.md` §1.3 Overload: `target_id: EntityId` (line 86)

**Analysis**: 08-api-idl.md says Overload targets a PlayerId (matching its design as player-level fuel budget attack). But game_api.idl.yaml and api-registry.md both say EntityId. The YAML IDL is authoritative.

**Fix**: Update 08-api-idl.md §Overload to use `target_id: EntityId` to match game_api.idl.yaml.

---

### M3: 08-api-idl.md RejectionReason Has Orphaned Variants

**Severity**: Medium

**Files**:
- `specs/gameplay/08-api-idl.md` §enums RejectionReason (lines 67–112)
- `specs/reference/game_api.idl.yaml` §rejection_reason (lines 302–488)

**Analysis**: 08-api-idl.md lists RejectionReason variants not present in game_api.idl.yaml:
- `NotMovable`, `Fatigued`, `MissingBodyPart`, `TileBlocked`, `StillSpawning`, `OutOfRoom`, `NoPath`, `PathTooLong`, `InsufficientMoveParts`, `CarryFull`, `NotSource`, `SourceEmpty`, `TargetFull`, `TargetEmpty`, `NotYourRoom`, `TileOccupied`, `InvalidTerrain`, `TooManyConstructionSites`, `AlreadyFullHealth`, `FriendlyTarget`, `NotYourSpawn`, `BodyTooLarge`, `ExceedsRoomCapacity`, `NotFriendly`, `AlreadyHacked`, `InvalidDamageType`, `AlreadyDebilitated`

Per D2/B design: these are NOT canonical wire enum codes — they belong in `debug_detail` templates (see api-registry.md §2.6 condition→code mapping). But 08-api-idl.md lists them as if they're enum variants alongside the canonical codes.

**Fix**: Either remove non-canonical variants from 08-api-idl.md's RejectionReason list and add a note referencing api-registry.md §2.6, or clearly mark these as "non-wire-enum, debug_detail only."

---

### M4: Balance Sheet Net-Flow All-Negative Beyond free_upkeep

**Severity**: Medium

**File**: `design/economy-balance-sheet.md` §2.7

**Issue**: The summary table shows net-negative for ALL scenarios from 2 rooms onward:
- 2 rooms: -54/tick (both basic and optimized)
- 5 rooms: -250 to -195/tick
- 10 rooms: -485 to -225/tick
- 20 rooms: -1,940 to -1,480/tick
- 50 rooms: -12,625 to -11,188/tick

The balance sheet acknowledges this (§2.7 note: "收支平衡在优化代码 + 适度扩张条件下可达"), but the data shows it's never reached in the modeled scenarios. The 2-room scenario has income = 66 and upkeep = 120 — break-even would require 182% efficiency (impossible under ×2.0 cap) or RCL upgrades beyond the scenario's RCL1–2 average.

**Analysis**: This is not a bug — it's a known design choice documented in PG-1. But the discrepancy between the "self-sustaining is achievable" claim and the "always negative" data is confusing for implementers. The path to break-even should be explicitly modeled (e.g., "at 3 rooms + RCL3 + 2× code efficiency, net flow = 0").

**Fix**: Add an explicit break-even scenario to §2.7 showing the conditions under which net flow becomes positive. Or accept that Standard mode is inherently deflationary and update the qualitative claims accordingly.

---

## Low / Nits (可选改进) (L1..L3)

### L1: Duplicate Heading in economy-balance-sheet.md

**File**: `design/economy-balance-sheet.md` lines 177–178

**Issue**: Heading `### 2.7 收支平衡汇总表 (Standard 模式)` appears twice — once at line 177 and again at line 178.

**Fix**: Remove duplicate heading.

---

### L2: Global Storage Capacity in world-rules.md Example

**File**: `specs/core/07-world-rules.md` line 1287

**Issue**: The world.toml example sets `global_storage_capacity = 100000` (100k), but the default across all other docs is 1,000,000 (1M). While this is an example (not the default), the 10× difference may confuse readers.

**Fix**: Either update example to 1,000,000 or add an explicit comment: `# 示例值，默认 1,000,000`.

---

### L3: economy-balance-sheet.md Mode Comparison — Arena Storage Tax Absent

**File**: `design/economy-balance-sheet.md` §3 (line 199–218)

**Issue**: The mode comparison table doesn't include `storage_tax` for Arena mode. gameplay.md states "Arena 模式默认免税（竞技公平）" but this isn't reflected in the economy-balance-sheet comparison.

**Fix**: Add Arena column or note to the mode comparison table.

---

## Strengths (设计亮点)

1. **多维度反雪球体系**：维护费（超线性 O(n²)）+ 累进存储税 + Controller 老化硬上限 + First-Attack Shield 渐进过渡 + soft_launch PvE-only 阶段 + free_upkeep 新手缓冲 + SpawnGrace 1-tick 无敌帧。这不是单一机制，而是一个多层防御网络，任何一层被调参削弱后仍有其他层生效。

2. **三模式物流梯度**：模式 A（无物流/Arena）→ 模式 B（轻物流/Standard 默认）→ 模式 C（硬核物流/Factorio 式）提供了从休闲到硬核的连续难度光谱，且全部由 world.toml 参数控制，无需引擎代码变更。

3. **全球→本地转换不可即时补给**：`global_withdraw_delay = 100 tick` + `global_deposit_delay = 10 tick` 的非对称设计创造了有意义的策略权衡——囤积全局存储安全但无法紧急调用，囤积本地存储灵活但暴露于敌方掠夺。transport-intercept 机制（R27 E-H1）进一步增加了物流战的策略深度。

4. **定点数经济模型全覆盖**：从 ResourceAmount (i64) 到 BasisPoints (u32) 到 MilliUnits (i64)，所有经济计算使用定点整数，消除浮点数跨平台不确定性。economy.idl.yaml 独立于 game_api.idl.yaml，清晰分离经济操作与游戏指令。

5. **PG-1/PG-2/PG-3 在 PLAYTEST-GATED.md 中正确追踪**：三项需要 playtest 数据的未闭合项均有明确的闭合条件和数据来源要求。文档诚实标注了 "示意性估算" 而非假装精确。

6. **新手保护链设计精致**：首次 spawn → safe_mode (500 tick 无敌) → soft_launch (1500 tick PvE-only) → First-Attack Shield Phase 1 (200 tick 全盾) → Phase 2 (300 tick 半盾) → Full PvP。这是渐进式暴露而非硬开关，配合 PvP 警告广播，有效防止 "保护期结束瞬间被清场"。

---

## CrossCheck — 需要跨方向检查

- **CX1**: Structure costs triple-inconsistency (B1) → 建议 **Security/Consensus** 检查 `specs/core/08-resource-ledger.md` 和 `economy.idl.yaml` 的 CI 校验链是否检测到这些不一致。如果 CI 声称通过但数据不一致，codegen pipeline 可能有 bug。

- **CX2**: Terminal 描述矛盾 (H3: "跨世界身份同步" vs "市场交易接口") → 建议 **Auth/Identity** 检查 Terminal 的实际功能定义。如果 Terminal 负责跨世界身份同步，Auth 文档应引用它。

- **CX3**: `global_deposit_delay` (B2) 的缺失 → 建议 **Engine/Core** 检查 `specs/core/07-world-rules.md` §2.3 world.toml 示例是否暴露了 `global_deposit_delay` 参数。如果 world.toml schema 中没有此字段，引擎实现将无法区分两个方向的延迟。

- **CX4**: Anti-snowball 数学证明缺失 (H5) → 建议 **Engine/Core** 检查 `specs/core/08-resource-ledger.md` §Empire Upkeep 是否提供了 break-even 的数学条件（如 `rooms` 满足 `base_upkeep × rooms × (1 + rooms / soft_cap) < income(rooms)` 时的解）。如果 Resource Ledger 没有形式化此条件，balance-sheet 的 "self-sustaining 可达" 是无约束承诺。

- **CX5**: economy.idl.yaml 缺失 PowerSpawn/Factory/Nuker/Depot (B1 子问题) → 建议 **API/SDK** 检查 `swarm_sdk_fetch` 生成的 SDK 是否包含这些结构的 BuildCost。如果 IDL 不包含，SDK 将缺失对应的 cost 查询接口。