# R18 Economy Review — DeepSeek V4 Pro

**Reviewer**: rev-dsv4-economy (DeepSeek V4 Pro)
**Date**: 2026-06-18
**Phase**: R18 Phase 1 Clean-Slate
**Task**: r18-economy-dsv4

---

## 1. Verdict: CONDITIONAL_APPROVE — 3 Critical, 3 High, 3 Medium

YAML IDL 作为单事实源的闭合性**未完全达成**。Recycle 公式冲突从 R17 延续未修复（Critical D1）。Empire-upkeep 存在双公式权威分裂——Resource Ledger 声明 O(n²) 但默认 Rhai mod 参数产生近线性行为（Critical D4）。storage_tax 公式书面形式与数值示例之间存在 100× 的隐含因子差异（High D2）。YAML IDL 缺少 `08-api-idl.md` 中的 `refund_policy` 段（Medium D3），且 `08-api-idl.md` 的 RejectionReason 枚举（44+ variant with data fields）与 YAML 的 35 flat codes 不一致（Medium D5）。economy-balance-sheet 的 storage tax 数值与 Resource Ledger 公式计算存在舍入偏差（Medium D6）。

---

## 2. Findings

### CRITICAL — D1: Recycle 公式冲突 — YAML flat 50% vs Resource Ledger proportional 10-50%

**Severity**: Critical (R17遗留未修复)
**Affected files**:
- `specs/reference/game_api.idl.yaml` line 162: `refund: registry.body_cost(body) * 0.5` — **flat 50%**
- `specs/gameplay/08-api-idl.md` line 162: `refund: registry.body_cost(body) * 0.5` — **flat 50%** (same)
- `design/gameplay.md` §8: "回收退还 50%" — **flat 50%**
- `specs/core/08-resource-ledger.md` §2.3: `recycle_refund = body_cost × remaining_lifespan / total_lifespan × recycle_refund_base / 10000` with min at `recycle_refund_min=1000 bp (10%)` and base at `recycle_refund_base=5000 bp (50%)` — **proportional 10-50%**
- `design/economy-balance-sheet.md` line 150: correctly references "Resource Ledger §6 (lifespan 10%–50%)"

**Analysis**: YAML IDL（声称唯一机器事实源）定义了 flat 50% 退还。Resource Ledger（声称经济公式唯一权威）定义了 proportional 10-50%。这是硬冲突——不可能同时成立。R17 D1 已报告此问题但未修复。

**Game theory impact**:
- Flat 50% 下：新 drone spawn 后立即 recycle 净损失 50%，无套利。
- Proportional 下：新 drone spawn 后立即 recycle 仅获 10% 退还（净损失 90%），套利更不可能。
- 两种公式均无套利风险，但**数值影响巨大**：1000 Energy drone 在 lifespan 50% 时回收：flat=500, proportional=250——相差 2×。
- 博弈均衡：flat 50% 下最优策略是 drone 到期前任何时候回收均获相同收益，回收时机无决策深度。Proportional 下存在回收时机优化——过早回收损失大，过迟 drone 自行死亡归零——需在预期死亡前最后 N tick 回收，产生策略深度。

**Recommendation**: Resource Ledger 的 proportional 公式应是正确答案（它是自 R15/B9 以来声明的经济权威）。YAML IDL 应更新为 `refund: registry.recycle_refund(body, remaining_lifespan, total_lifespan)` 或等价引用。所有 Markdown 文档中的 "50%" 应改为 "up to 50%" 并引用 Resource Ledger。

---

### CRITICAL — D4: Empire-upkeep 双公式权威分裂 — Resource Ledger O(n²) vs Rhai mod 默认近线性

**Severity**: Critical
**Affected files**:
- `specs/core/08-resource-ledger.md` §Empire Upkeep: `upkeep = base_upkeep × rooms × (1 + rooms / room_soft_cap)` — 明确 O(n²)，Standard: base=50, cap=10
- `design/economy-balance-sheet.md` §1-2: 基于上述公式验证数值（50 rooms = 15,000/tick ✓）
- `design/gameplay.md` §8.7 Rhai empire-upkeep mod: `room_penalty = rooms * (config.room_base + rooms * config.room_superlinear / FIXED_SCALE)` — 使用完全不同的参数体系
- `design/gameplay.md` line 1948: 明确承认 "Vanilla 默认值在 1-50 房间范围内产生近乎线性的维护费曲线——超线性项的贡献在默认值下极小（50 房间时仅贡献 0.25 Energy/tick）"

**Analysis**: 存在两个互不兼容的 empire-upkeep 公式体系：

| 维度 | Resource Ledger (声称权威) | Rhai mod (默认实现) |
|------|--------------------------|-------------------|
| Formula | `50 × n × (1 + n/10)` | `n × (10 + n × 0.0001)` |
| 50 rooms | 15,000/tick | ~500/tick |
| 数学性质 | **O(n²)** — superlinear | **O(n)** — nearly linear |
| Anti-snowball | 强力：50 rooms 维护费吞噬收入 | 极弱：线性增长，收入同步增长即可覆盖 |
| 收敛性 | 自然收敛 | **不收敛** — 纯线性下没有 soft cap |

gameplay.md line 1948 标注 "详见 Vanilla Economy Balance Sheet（待 B6 闭合时产出）"——经济报表本身标注为未闭合，引用了一个尚未确定的设计。但 economy-balance-sheet.md 已使用 Resource Ledger 公式做了完整的 1/5/20/50 房间数值验证并声称 "Anti-Snowball 证明"。

**Anti-snowball 影响**：如果引擎实际运行 Rhai mod 的默认参数，则：
1. 整个 economy-balance-sheet 的反雪球证明**不适用于默认世界**
2. 超线性维护费是设计文档中反雪球合同的**核心支柱**（gameplay.md §8反雪球表）
3. 玩家在默认世界可以无限扩张至 entity cap，维护费不是瓶颈
4. 服主必须手动调参才能获得文档承诺的反雪球效果——默认体验与设计意图脱钩

**Recommendation**: 
- 两个公式必须统一。推荐方向：Resource Ledger 公式成为 Vanilla 默认，Rhai mod 的 `room_superlinear` 默认值应调整为产生等效的 O(n²) 行为（如 `room_superlinear=10000` → 0.01 → Standard: `50 × n × (1 + n/10)` 近似 `n × (10 + n × 0.01)` 取 base=10, room_superlinear=50000 → 5.0）
- economy-balance-sheet 移除「待 B6 闭合」注释——它是已经基于 Resource Ledger 闭合的文档

---

### HIGH — D2: storage_tax 公式书面形式与数值示例存在 100× 因子差异

**Severity**: High
**Affected file**: `specs/core/08-resource-ledger.md` §2.2

**Analysis**: 
书面公式：
```
tax = taxable_in_tier × tier_rate[i] × global_storage_capacity / 10000
```

其中 `taxable_in_tier = min(storage_pct - tier_threshold[i], tier_width[i])` 为**百分比值**（如 30、15 等）。

示例验证（75% 存储，1M 容量）：
- tier 2: taxable = min(75-60, 25) = **15**（百分比值）
- 书面公式: 15 × 5 × 1,000,000 / 10000 = **7,500**
- 文档示例声称: **75**
- 差值: 100×

正确公式应为（两种等价写法）：
```
tax = (taxable_in_tier / 100) × global_storage_capacity × tier_rate[i] / 10000
tax = taxable_in_tier × global_storage_capacity × tier_rate[i] / 1,000,000
```

文档示例值（30、75、105）在修正后公式下全部正确。书面公式缺少 `/100` 或等价的将 `global_storage_capacity / 10000` 改为 `global_storage_capacity / 1,000,000`。

**Impact**: 如果实现者直接翻译书面公式，storage_tax 将被高估 100 倍——存储 75% 的玩家每 tick 被扣 10,500 而非 105，经济完全崩溃。由于示例数值是正确的，经验证的实现不会出错，但公式文本本身有误导性。

**Recommendation**: 修正 §2.2 公式，添加 `/100` 因子或将分母改为 1,000,000。

---

### HIGH — D3: `specs/gameplay/08-api-idl.md` 包含 YAML IDL 中不存在的 `refund_policy` 段

**Severity**: High
**Affected files**:
- `specs/gameplay/08-api-idl.md` lines 283-285:
  ```yaml
  refund_policy:
    contention_lost: 0.5    # SourceEmpty, TileOccupied, TargetFull
    self_invalid: 0.0       # OutOfRange, Fatigued, MissingBodyPart, etc.
  ```
- `specs/reference/game_api.idl.yaml` — **无此段**

**Analysis**: `refund_policy` 定义了**指令失败后的资源退还策略**（与 Recycle 退款不同——这是 command cost refund）。YAML IDL 中完全没有此概念。如果 CI 从 YAML 重新生成文档，此段将丢失。

此外，`contention_lost: 0.5` 意味着因外部竞争条件导致指令失败时退还 50% 资源——这本身是一个经济机制（降低 PvP 竞争的风险成本），但在 Resource Ledger 中也未定义。

**Recommendation**: 
- 将 `refund_policy` 纳入 YAML IDL（作为顶层 section）
- 或在 Resource Ledger 中定义指令退还规则
- 明确 refund_policy 与 RecycleRefund 的区别

---

### HIGH — D5: `08-api-idl.md` RejectionReason 枚举（44+ variant with data）与 YAML 35 flat codes 不一致

**Severity**: High
**Affected files**:
- `specs/gameplay/08-api-idl.md` lines 65-111: RejectionReason 含 ~44 变体，部分带 data fields (如 `OutOfRange { distance: u32, max: u32 }`, `InsufficientResource { resource: ResourceName, required: u32, available: u32 }`)
- `specs/reference/game_api.idl.yaml` §2: 35 canonical codes，全部为 flat strings，data 移入 `debug_detail` (D2/B)
- `specs/reference/api-registry.md` §2: 35 canonical codes（从 YAML 生成，正确）

**Analysis**: D2/B 裁决将详细上下文从 enum variant 移至 `debug_detail` 字段，保持 wire enum 稳定为 35 codes。但 `08-api-idl.md` 的 RejectionReason 列表**未被更新**——仍保留旧版带 data 的 variant 设计（`OutOfRange{distance,max}`, `InsufficientResource{resource,required,available}` 等）。

此外，`08-api-idl.md` 包含许多 YAML 中不存在的错误码：`NotMovable`, `Fatigued`, `MissingBodyPart`, `TileBlocked`, `StillSpawning`, `OutOfRoom`, `NoPath`, `PathTooLong`, `InsufficientMoveParts`, `CarryFull`, `NotSource`, `SourceEmpty`, `TargetFull`, `TargetEmpty`, `NotYourRoom`, `TileOccupied`, `InvalidTerrain`, `TooManyConstructionSites`, `AlreadyFullHealth`, `FriendlyTarget`, `NotYourSpawn`, `BodyTooLarge`, `ExceedsRoomCapacity`, `NotFriendly`, `AlreadyHacked`, `InvalidDamageType`, `AlreadyDebilitated`。

**Recommendation**: 将 `08-api-idl.md` 的 RejectionReason 更新为引用 `api-registry.md` 的 35 canonical codes（或直接在 CI 生成时交叉校验）。

---

### MEDIUM — D6: economy-balance-sheet storage tax 数值与 Resource Ledger 公式存在舍入偏差

**Severity**: Medium
**Affected file**: `design/economy-balance-sheet.md` §2

**Analysis**: 以下对比显示 economy-balance-sheet 的 storage tax 数值与 Resource Ledger §2.2 公式计算结果存在偏差：

| Scenario | Balance Sheet | Formula (corrected) | Delta |
|----------|:------------:|:-------------------:|:-----:|
| 5 rooms (assume ~45% storage, tier 1) | 15 | 15 (150K × 1 bp) | 0 |
| 20 rooms (assume ~75-80% storage, tiers 1+2) | 120 | ~125-155 (varies by exact %) | +5~35 |
| 50 rooms (assume ~90%+ storage, all tiers) | 600 | ~455 (at 100%) | -145 |

偏差方向不一致（有的低估有的高估），表明这些是近似值而非精确计算。balance-sheet 文档本身已声明 "Resource Ledger 为所有收支计算的单一权威源"——偏差可接受，但应标注为近似。

**Recommendation**: 在 balance-sheet 各表中添加 "approx" 标注或使用精确公式计算。

---

### MEDIUM — D7: Tutorial Recycle 100% 退还仅在设计文档中声明，未在 YAML IDL 体现

**Severity**: Medium
**Affected files**:
- `design/gameplay.md` §8: "新手保护: Tutorial 世界前 500 tick 回收退还 100%"
- `specs/core/08-resource-ledger.md` §2.3: "新手保护（Tutorial 前 500 tick）退还 100%，由 world.toml `tutorial_recycle_refund_full_ticks` 控制"
- `specs/reference/game_api.idl.yaml`: Recycle 定义仅为 `refund: registry.body_cost(body) * 0.5`，无 Tutorial 条件分支

**Analysis**: Tutorial 100% 回收是重要的 onboarding 设计决策（允许新人试错），但 YAML IDL 的命令定义中完全是 flat 50%。虽然可以通过 world.toml 参数实现，但 IDL 层面的命令定义没有体现条件逻辑。

**Recommendation**: YAML IDL Recycle 命令的 refund 应引用 world.toml 可配置参数而非硬编码 0.5。

---

### MEDIUM — D8: 全局存储税率 "1 bp (每万单位 1 单位)" 描述有歧义

**Severity**: Medium
**Affected file**: `design/gameplay.md` §8 累进存储税表

**Analysis**: 表格中 "1 bp（每万单位 1 单位）" 对于 tier 1，字面意思是 "每 10,000 单位存储抽取 1 单位/ tick"。实际公式为 `存储量 × 1 / 10000 / tick`。对于 30-60% tier（300,000 单位），每 tick 抽取 30 单位——这与描述一致。但 "每万单位" 可被误解为 "每 10,000 单位抽取 1 单位一次性"（而非每 tick），建议澄清。

---

## 3. Strengths

1. **Resource Ledger 的定点费率模型设计良好**：所有费率使用 basis points 禁止浮点数，Transfer Gateway 架构提供单一资源入口——从博弈论角度消除了多入口资源逃逸路径。

2. **Anti-snowball 机制的三层纵深设计**：累进存储税 + 超线性维护费 + Controller 续期硬上限（50%）形成三层反制。如果每层按设计实现，大帝国将面临数学上的自然收敛。

3. **全局↔本地转换的 No Teleport 设计**：运输延迟 (10/5 tick) + 损耗 (1%/5%) 使全局存储不能作为"战斗即时补给"，这是关键的战略深度机制——玩家必须在物流规划和即时战力之间权衡。

4. **新玩家经济门控设计完整**：transfer lock、PvE drop 绑定、同源账号组配额——三层防御防止刷号经济滥用。所有参数可配置，Tutorial 默认全关。

5. **YAML IDL 的 MCP tools security columns 设计**：`replay_class`、`visibility_filter`、`rate_limit_key`、`required_scope` 等字段使自动 codegen 产出安全感知的 SDK——从设计层面防止信息泄露。

6. **PvE budget 四维控制**：Global/Zone/Player/Event 四维上限防止 PvE faucet 无限放大——这是重要的经济闭环设计，防止「刷怪经济」压倒 PvP 战略价值。

---

## 4. CrossCheck — YAML IDL ↔ Markdown 闭环验证

| 域 | YAML IDL | api-registry.md | 一致性 |
|----|----------|-----------------|:------:|
| CommandAction | 19 variants | 19 variants | ✅ |
| RejectionReason | 35 canonical codes | 35 canonical codes | ✅ |
| MCP Tools | 46 active | 46 active | ✅ |
| Host Functions | 5 functions | 5 functions | ✅ |
| Limits | 25+ params | 25+ params | ✅ |
| TickTrace Envelope | 22 fields | 22 fields | ✅ |
| terminal_state | 7 variants | 7 variants | ✅ |
| Direction4 | 4 directions | 4 directions | ✅ |
| ResourceOperation | 6 types | 6 types | ✅ |
| Deploy fdb_version_counter | present | present | ✅ |
| Persistence async_upload | present | present | ✅ |

**YAML → Markdown consistency: PASS (11/11 sections match)**

| 域 | YAML IDL | 08-api-idl.md | 一致性 |
|----|----------|---------------|:------:|
| Recycle refund | `* 0.5` flat | `* 0.5` flat | ✅ (both wrong vs Resource Ledger) |
| RejectionReason | 35 flat codes | 44+ variants with data | ❌ D5 |
| refund_policy | absent | `contention_lost: 0.5` etc. | ❌ D3 |
| host_functions | 5 with budgets | 5 with budgets | ✅ |
| global_storage_commands | TransferToGlobal/FromGlobal | TransferToGlobal/FromGlobal | ✅ |

**YAML → 08-api-idl.md consistency: PARTIAL (2/5 mismatches)**

---

## 5. Nash Equilibrium Analysis

### 5.1 存储策略均衡

**Dominant strategy identified**: 在 taxed 的全局存储和 untaxed 的本地存储之间，**最优策略始终是最大化本地存储利用率**。本地存储完全隐匿（敌方无法获知真实经济实力），且不触发存储税。这是设计的意图（stealth advantage 是 feature，不是 bug），但需注意：当所有玩家采取此策略时，全局存储仅用作部署费支付中转，税收产出近零——税制的宏观经济调节作用被架空。

### 5.2 回收均衡

- **Flat 50% (YAML IDL)**: 回收时机无决策深度——任意时刻回收收益相同。Nash equilibrium: drone 在预期死亡前的最后 1 tick 回收（最大化使用寿命）。策略退化。
- **Proportional 10-50% (Resource Ledger)**: 存在 timing tradeoff——早回收多拿 refund 但损失使用时间 vs 晚回收多使用但 refund 减少。产生有意义的 Nash equilibrium。支持 Resource Ledger 版本。

### 5.3 Empire-upkeep 收敛条件（Resource Ledger 公式）

```
upkeep(n) = 50 × n × (1 + n/10) = 50n + 5n²
income(n) ≈ α × n + β  (α ≈ source/tick/room, β ≈ PvE/Controller)
```

Nash equilibrium 在 `50n + 5n² = αn + β` → `5n² + (50-α)n - β = 0`。

对于 α=25 (avg source output), β=0: n ≈ 0（无正根）——任何扩张均亏损，玩家被迫优化代码提高 α。

对于 α=100 (optimized): n ≈ 10 rooms（均衡点）。50 房间时 upkeep=15,000, income≈5,000 — deficit 10,000/tick。**强力收敛。**

但如果使用 Rhai mod 默认参数（nearly linear），n 无上限直至 entity cap——**无 Nash equilibrium**。

---

## 6. Summary

| # | Severity | ID | Issue |
|---|----------|-----|-------|
| 1 | **Critical** | D1 | Recycle formula: YAML flat 50% vs Resource Ledger proportional 10-50% (R17 遗留) |
| 2 | **Critical** | D4 | Empire-upkeep dual formula: Resource Ledger O(n²) vs Rhai mod default nearly-linear |
| 3 | **High** | D2 | storage_tax formula written form missing /100 factor |
| 4 | **High** | D3 | refund_policy section in 08-api-idl.md not in YAML IDL |
| 5 | **High** | D5 | 08-api-idl.md RejectionReason (44+ data variants) vs YAML (35 flat codes) |
| 6 | **Medium** | D6 | economy-balance-sheet storage tax values approximate vs formula |
| 7 | **Medium** | D7 | Tutorial 100% recycle not reflected in YAML IDL |
| 8 | **Medium** | D8 | "每万单位 1 单位" storage tax wording ambiguous |
