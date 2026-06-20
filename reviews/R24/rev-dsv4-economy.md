# R24 Economy Review — rev-dsv4-economy

**Reviewer**: rev-dsv4-economy (DeepSeek V4 Pro)
**Direction**: Economy — 设计文档与规范文档之间的经济参数一致性、建筑成本对齐、资源流动校验
**Review Type**: Full Slate — design/gameplay.md ↔ economy.idl.yaml ↔ resource-ledger ↔ 08-api-idl 全量对齐检查
**Documents Reviewed**: `design/gameplay.md` (economy sections), `specs/reference/economy.idl.yaml`, `specs/reference/game_api.idl.yaml`, `specs/core/08-resource-ledger.md`, `specs/gameplay/08-api-idl.md`, `specs/gameplay/06-feedback-loop.md` — 共 6 份核心文档

---

## Verdict: REQUEST_MAJOR_CHANGES

发现 **4 Critical**（建筑成本全面不一致、global transfer delay 10× 差异、Recycle 退款模型矛盾、RangedAttack 成本不一致）、**3 High**（IDL 缺失/多余建筑类型、Controller repair 定义分裂）、**3 Medium**、**2 Low**、**2 Nash Equilibrium 问题**。

Critical 项必须在合并前修正——建筑成本差异直接影响 spawn/build/spawn balance 的 game design 决策；global transfer delay 10–20× 差异从根本上改变了「No Teleport」anti-dominant-strategy 的战术时间窗口。High 项导致 IDL 作为 single source of truth 的权威性受损。Nash Equilibrium 问题为深度经济分析发现，需设计侧裁决是否纳入正式 spec。

---

## Critical

### C1 — economy.idl.yaml 建筑成本与 design/gameplay.md 全面不一致

**位置**: `specs/reference/economy.idl.yaml` §2.5 BuildCost.cost_schedule (L237–274) vs `design/gameplay.md` §Vanilla Ruleset 建筑类型定义 (L117–228)

**冲突描述**:

| 建筑类型 | economy.idl.yaml (spec) | design/gameplay.md (design) | 差异 |
|----------|:----------------------:|:---------------------------:|:----:|
| Spawn | 300 | 200 | +50% |
| Extension | 200 | 50 | +300% |
| Tower | 800 | 200 | +300% |
| Link | 400 | 300 | +33% |
| Extractor | 600 | 800 | −25% |
| Terminal | 1200 | 500 | +140% |
| Observer | 500 | 300 | +67% |
| Storage | 500 | 500 | ✅ 一致 |
| Lab | 1000 | 1000 | ✅ 一致 |

此外，economy.idl.yaml 包含 design 中未出现的建筑类型：**Road (10)**、**Wall (50)**、**Rampart (100)**。design 中包含但 economy.idl.yaml 缺失的建筑类型：**PowerSpawn (5000)**、**Factory (1500)**、**Nuker (100000)**、**Depot (5000)**。

**影响**:

1. **Spawn cost (300 vs 200)**：50% 差异影响新游戏 opening build order——200 Energy 的 Spawn 在 safe_mode 初期即可部署多个，300 则显著延缓扩张节奏。这直接影响 growth path 的时间线（resource-ledger §2.3 Growth Path 表依赖 Spawn timing）。
2. **Tower cost (800 vs 200)**：4× 差异是最大的单项偏差——200 Energy 的 Tower 使静态防御过于便宜（在 safe_mode 500 tick 内可堆满），800 则使早期防御成为重大战略投资。两种成本下的 PvP 博弈树完全不同。
3. **Terminal cost (1200 vs 500)**：2.4× 差异影响跨世界物流的经济门槛。
4. **缺失建筑**：Depot 是前线 logistics 核心（design §后勤网络 L254-272），其在 economy.idl.yaml 中缺失意味着 spawn/build cost pipeline 无法处理 Depot 建造——要么报错，要么 fallback 到未定义行为。

`economy.idl.yaml` 的 BuildCost 注释明确标记为 "Base build costs per structure type"——但 design 的 world.toml 示例明确指出 `build_cost_multiplier` 可调（默认 10000 = 1.0），理论上 IDL 应使用与 design 相同的 base 值。当前差异无法用 multiplier 解释。

**修正建议**:

1. 以 `design/gameplay.md` §Vanilla Ruleset 建筑类型定义为权威 base cost，逐项修正 `economy.idl.yaml` §2.5 BuildCost.cost_schedule。
2. 补充缺失的建筑类型到 economy.idl.yaml：Depot、PowerSpawn、Factory、Nuker。
3. 从 economy.idl.yaml 移除 design Vanilla Ruleset 中未定义的 Road/Wall/Rampart，或将它们标记为 "optional extension" 并加注释说明不属于 vanilla。
4. 在 CI 中增加自动化校验：`economy.idl.yaml BuildCost.schedule.structures` 的 base cost 与 `design/gameplay.md` `[[structure_types]]` 的 `cost` 字段一一对应。

---

### C2 — global_transfer_delay：10 tick (design) vs 100 tick (spec) — 10–20 倍差异

**位置**: `design/gameplay.md` §2.2 资源与经济 / 全局↔本地转换 (L311–313) vs `specs/core/08-resource-ledger.md` §2.1 L75

**冲突描述**:

| 维度 | design/gameplay.md | resource-ledger.md (权威源) | 差异 |
|------|-------------------|---------------------------|:---:|
| 存入延迟 | `transfer_to_global_time = 10 tick` | 无独立参数 | — |
| 提取延迟 | `transfer_from_global_time = 5 tick` | `global_transfer_delay = 100 tick` | **20×** |
| 延迟语义 | 双向独立、不对称 | 单一统一延迟 | 结构分歧 |

- `design/gameplay.md` L311–313: `transfer_to_global_time = 10`（"不可为 0，防止瞬移补给"），`transfer_from_global_time = 5`（"不可为 0"）——明确双向不对称延迟。
- `specs/core/08-resource-ledger.md` §2.1 L75: `global_transfer_delay = 100 tick`，标注为「全局提取延迟」——语义上对应 `transfer_from_global_time`，但值为 100 而非 5（差异 20×）。
- `specs/core/08-resource-ledger.md` §4 执行顺序中，GlobalDeposit (step 6) 和 GlobalWithdraw (step 7) 均无独立延迟字段——整个 spec 中只有一个 `global_transfer_delay`。
- `economy.idl.yaml` 不包含 global transfer delay 参数——仅有 AlliedTransfer.transfer_delay (200 tick)。

**影响**:

1. **"No Teleport" 设计意图被破坏**：design 明确声明 "运输时间使全局存储不能作为'战斗中的即时补给'"。10 tick（design 存入）和 100 tick（spec 提取）产生两种截然不同的战术环境：
   - **10/5 tick 模型**（design）：资源锁定窗口极短——drone 在战斗中等待 5 tick 即可获得全局补给，物流规划可以 tick 级细粒度执行。
   - **100 tick 模型**（spec）：全局提取是战略级决策（100 tick ≈ 3.3 秒 @ 30 tick/s tick rate）——drone 必须提前至少 100 tick 下达提取指令，远在战斗开始之前。这是一种完全不同的经济-tick 博弈。

2. **design 的双向不对称延迟模型**：存入（10 tick）比提取（5 tick）更慢——这种不对称性的设计意图是「囤积全局存储比从中提取更耗时间」，鼓励本地存储囤积。spec 的单一 `global_transfer_delay = 100` 破坏了这种不对称性。

3. **snapshot-contract 引用链**：从 log 证据（`specs/core/09-snapshot-contract.md` L191）确认 snapshot-contract 已引用 resource-ledger 的 `global_transfer_delay = 100`。这意味着 100 tick 已进入 spec 引用链——修改需要同步更新。

**修正建议**:

1. 以 resource-ledger.md（经济权威）为准，将 `global_transfer_delay` 拆分为 `global_deposit_delay` 和 `global_withdraw_delay` 两个独立参数，与 design 的双向非对称模型对齐。
2. 若 design 的 10/5 tick 为正确值 → resource-ledger §2.1 拆分为 `global_deposit_delay = 10`, `global_withdraw_delay = 5`，并同步更新 snapshot-contract 引用。
3. 若 spec 的 100 tick 为设计意图（全局提取应是战略级延迟）→ design/gameplay.md 需同步更新 `transfer_from_global_time = 100`，并更新 growth path 分析表中的时间线。
4. 在 economy.idl.yaml 中增加 GlobalTransferDelay 操作，包含 deposit_delay 和 withdraw_delay 两个字段。

---

### C3 — Recycle 退款模型：08-api-idl flat 50% vs resource-ledger lifespan-proportional

**位置**: `specs/gameplay/08-api-idl.md` §2 Recycle 指令 (L164) vs `specs/core/08-resource-ledger.md` §2.5 (L160–165) vs `design/gameplay.md` §2.1 Drone 身体规划 (L106–108)

**冲突描述**:

| 文档 | Recycle 退款模型 | 公式 |
|------|-----------------|------|
| `specs/gameplay/08-api-idl.md` §2 L164 | **Flat 50%** | `refund: registry.body_cost(body) * 0.5` |
| `specs/core/08-resource-ledger.md` §2.5 L160–165 | **Lifespan-proportional 10%–50%** | `recycle_refund = max(body_cost × recycle_refund_min / 10000, body_cost × remaining / total × recycle_refund_base / 10000)` |
| `design/gameplay.md` §2.1 L106–108 | **Lifespan-proportional** | "lifespan-proportional 比例退还（最高 50%，随剩余 lifespan 递减至 10%）" |
| `specs/reference/economy.idl.yaml` §2.1 RecycleRefund | **Lifespan-proportional** | 与 resource-ledger 一致：`max(1000, (remaining_lifespan * 5000) / total_lifespan)` |

**影响**:

1. **Flat 50% 产生套利窗口**（已在 R23 共识中指出）：若 drone 在寿命末期（如 1 tick 剩余）仍退还 50%，玩家可通过「快到寿命 → 回收 → 重新 spawn」循环维持 constant 50% body cost，完全无视 lifespan 约束。Lifespan-proportional 模型（末期 10%）则消除了此套利。
2. **08-api-idl.md 是 SDK/WASM 开发者的主要参考文档**——若实现者按 `* 0.5` 编码，drone 回收将使用错误公式，且 CI 的 `git diff --exit-code`（08-api-idl.md §4）不会捕获此错误（因为 IDL 生成的是 `refund = registry.body_cost(body) * 0.5` 字符串）。
3. **resource-ledger 声明为「唯一经济权威」**（§开头 R22 B2 修复声明），但 08-api-idl.md 的 `* 0.5` 是硬编码而非引用 resource-ledger 公式——这破坏了权威链。
4. **commands.md 存在相同问题**：从 R25-speaker log 确认 `specs/reference/commands.md` L114 仍写 "退还 50% body part 资源"，需要同步修正。

**修正建议**:

1. 将 `specs/gameplay/08-api-idl.md` §2 Recycle 的 `refund: registry.body_cost(body) * 0.5` 替换为 lifespan-proportional 公式引用：`refund = RecycleRefund.amount(body_cost, remaining_lifespan, total_lifespan)`，并添加注释指向 resource-ledger §2.5 和 economy.idl.yaml §2.1 为权威源。
2. 同步修正 `specs/reference/commands.md` 中所有 `* 0.5` 的 flat refund 描述。
3. 在 CI 中增加校验：`08-api-idl.md` 和 `commands.md` 中 Recycle refund 的文本不得包含硬编码数值 `0.5` 或 `50%`——必须引用 resource-ledger 公式。

---

### C4 — RANGED_ATTACK body part cost：150 (economy.idl.yaml) vs 100 (design/08-api-idl)

**位置**: `specs/reference/economy.idl.yaml` §2.6 SpawnCost.cost_schedule (L329) vs `design/gameplay.md` §2.1 RangedAttack body part (L899) vs `specs/gameplay/08-api-idl.md` §2 body_cost 表 (L230)

**冲突描述**:

| 文档 | RANGED_ATTACK body part cost |
|------|:--------------------------:|
| `economy.idl.yaml` §2.6 SpawnCost | **150 Energy** |
| `design/gameplay.md` §2.1 body_part_types | **100 Energy** |
| `specs/gameplay/08-api-idl.md` §2 body_cost | **100 Energy** |
| `game_api.idl.yaml` | 未独立定义 body_cost |

**影响**:

1. **Spawn cost 计算公式分歧**：`spawn_cost = sum(body_part.cost for each body_part)`。若 economy.idl.yaml 的 150 为权威，则 `[MOVE, RANGED_ATTACK]` drone 的 spawn cost = 50 + 150 = 200；若 design 的 100 为权威，则 = 50 + 100 = 150。33% 差异影响早期 military drone 的经济可行性。
2. **Authority 冲突**：`economy.idl.yaml` 的 SpawnCost 声明 body part costs 为权威值；但 `design/gameplay.md` 的 `[[body_part_types]]` 同样声明了 cost 字段（"生成该 body part 的资源消耗"——必需字段）。两份文档均声称定义 body part spawn 成本，但值不同。
3. **CI 盲区**：`08-api-idl.md` §4 的 CI 检查仅验证「生成的代码与提交代码一致」——不验证 economy.idl.yaml 中的 body part cost 是否与 design 对齐。
4. **其他 body part costs 一致**：Move (50/50)、Work (100/100)、Carry (50/50)、Attack (80/80)、Heal (250/250)、Claim (600/600)、Tough (10/10) 在所有文档间完全一致。只有 RANGED_ATTACK 存在差异——这大概率是 economy.idl.yaml 在独立编写时的笔误。

**修正建议**:

1. 以 `design/gameplay.md` L899 的 100 Energy 为权威（8/8 body parts 在 design↔spec↔IDL 间一致），将 `economy.idl.yaml` L329 的 RANGED_ATTACK cost 从 150 修正为 100。
2. 在 CI 中增加 body part cost 交叉校验：`economy.idl.yaml SpawnCost.body_parts[*].cost == design/gameplay.md [[body_part_types]].cost`。
3. 确认 `game_api.idl.yaml` 是否需要显式包含 body_cost 定义表（当前缺失，仅 economy.idl.yaml 和 08-api-idl.md 有）。

---

## High

### H1 — economy.idl.yaml 建筑类型集合与 design/gameplay.md Vanilla Ruleset 不匹配

**位置**: `specs/reference/economy.idl.yaml` §2.5 BuildCost.cost_schedule (L238–274) vs `design/gameplay.md` §2.1 自定义建筑类型 (L117–228)

**描述**:

两份文档定义的 Vanilla 建筑类型集合不同：

| 类别 | economy.idl.yaml 有，design 无 | design 有，economy.idl.yaml 无 |
|------|------------------------------|------------------------------|
| 新增 | Road, Wall, Rampart | — |
| 缺失 | — | **Depot**, **PowerSpawn**, **Factory**, **Nuker** |

**影响**:

1. **Road (10) / Wall (50) / Rampart (100)** 出现在 economy.idl.yaml 的 BuildCost 表中，但在 design/gameplay.md 的 Vanilla Ruleset `[[structure_types]]` 中不存在这些类型。它们可能是后续扩展（Road 类似 Screeps 的 road 系统，Wall/Rampart 类似防御工事），但在 design 文档中没有任何定义——这使得它们的 cost 来源不可追溯。
2. **Depot 完全缺失**：Depot 是 design §2.1 后勤网络的核心建筑——前线 age 维修节点，带 maintenance 消耗、repair_capacity/repair_range/repair_aging 参数。若 economy.idl.yaml 的 BuildCost 不包含 Depot，则 Depot 建造的 resource cost 无处查询——实现者只能从 design 的 `cost = { Energy: 5000 }` 猜测。
3. **PowerSpawn / Factory / Nuker 缺失**：这三个是 RCL 7–8 的高级建筑。缺失意味着高 RCL 阶段的建造 pipeline 在 economy IDL 中无定义。
4. **StructureType 枚举不一致**：`specs/gameplay/08-api-idl.md` §2 StructureType enum (L65–66) 包含 13 个类型（Spawn, Extension, Tower, Storage, Link, Extractor, Lab, Terminal, Nuker, Observer, PowerSpawn, Factory, Depot）——与 design 一致。但 economy.idl.yaml 的 BuildCost 表仅列了 12 个（缺 4，多 3）——与 StructureType enum 和 design 均不对齐。

**修正建议**:

1. 将 economy.idl.yaml BuildCost 表与 design/gameplay.md + 08-api-idl.md StructureType enum 对齐：补充 Depot (5000), PowerSpawn (5000), Factory (1500), Nuker (100000)；移除或标记 Road/Wall/Rampart 为非 vanilla。
2. 建立 authoritative StructureType 枚举源（建议以 08-api-idl.md StructureType enum 为准），所有其他文档从该源引用。

---

### H2 — Controller repair 定义分裂：hard cap (gameplay) vs repair_cap + distance_decay (resource-ledger)

**位置**: `design/gameplay.md` §2.1 Drone 生命周期 (L102) vs `specs/core/08-resource-ledger.md` §2.4 (L146–156)

**冲突描述**:

两份文档定义了两种不同的 Controller repair 模型：

| 维度 | design/gameplay.md | resource-ledger.md |
|------|-------------------|-------------------|
| 模型 | **Age rollback hard cap** — 每 tick 总 age 回退 ≤ 自然增长的 50% | **Repair cost formula** — `repair_cost = body_cost × (1 - repair_cap/10000) × (1 + distance × distance_decay_bp/10000)` |
| cap 含义 | 上限: `max(0, age + 1 - min(0.5, controller_count × 0.5))` | `repair_cap = 3500 bp (35%)` — 免费比例 |
| 距离衰减 | 未定义（Controller range 由 RCL 决定: 1–5 格） | `distance_decay_bp = 500 bp/tile (5%)` |
| 硬上限 | ❌ 有独立公式 | ❌ 仅有 cost 公式 |

**影响**:

1. **两种模型不兼容**：gameplay 说的是「最多回退多少 age」（quantity cap），resource-ledger 说的是「repair 要花多少资源」（cost），两者维度不同。
   - gameplay 的 hard cap：无论多少个 Controller、多少 drone 排队，每 tick 玩家总计 age 回退不超过 `min(0.5, controller_count × 0.5)` ticks。这是 **resource-independent** 的物理 cap。
   - resource-ledger 的 repair cost：Controller repair 不是免费的——按 body_cost 的 (100% − 35%) = 65% 计算，且随距离递增。这是 **resource-dependent** 的 cost 模型。

2. **resource-ledger 未提 hard cap**：§2.4 公式中 `repair_cap = 3500 bp` 是 cost reduction cap（修复只需付 65%），而非 age rollback quantity cap。gameplay 的「每 tick 总 age 回退 ≤ 50% 自然增长」是数量限制，不是 cost 限制。

3. **design/gameplay.md 未提 distance_decay**：gameplay 说 Controller "维修距离随 RCL 增长（RCL1=1 格，RCL8=5 格），免费"——明确说是免费的（免费但范围受限）。resource-ledger 则引入了 cost 和 distance_decay。两种描述的共同点仅在于「近距离 repair 更有利」，但实现完全不同（range gate vs cost scale）。

4. **Depot repair 未在 resource-ledger 中定义**：gameplay §后勤网络 L254-272 定义了 Forward Depot 的 repair（固定 range=1, repair_aging=5, maintenance cost），但 resource-ledger 未独立建模 Depot repair——仅 §2.4 定义 Controller repair。

**修正建议**:

1. 以 resource-ledger §2.4 为权威 Controller repair 公式（已由 R23 D4/A 裁决），但补充 gameplay 中的 **age rollback hard cap** 作为一个独立约束——两者应同时存在：
   - `repair_cost` formula (resource-ledger) — 回答「修一次花多少？」
   - `max_age_rollback_per_tick = max(0, natural_aging × min(0.5, controller_count × 0.5))` (gameplay) — 回答「总共能修多少？」
2. 在 resource-ledger 中补充 Depot repair 的独立建模（maintenance cost, repair_aging=5, repair_range=1）。
3. 在 design/gameplay.md 中同步 resource-ledger §2.4 的 cost formula（不再称 Controller repair 为 "免费"）。

---

## Medium

### M1 — economy.idl.yaml 缺失部分建筑类型参数（Depot maintenance 未建模）

**位置**: `specs/reference/economy.idl.yaml` §2.5 vs `design/gameplay.md` §2.1 Depot (L218–228)

**描述**:

Depot 在 design 中有完整的 maintenance/repair 参数定义（`maintenance = { Energy: 10 }`, `repair_capacity = 10`, `repair_range = 1`, `repair_aging = 5`），但 economy.idl.yaml 不仅缺失 Depot 建筑类型（见 H1），也缺失 per-tick maintenance deduction 的经济模型。当前 economy.idl.yaml 仅有 UpkeepDeduction（empire upkeep）和 StorageTax——**没有 per-structure maintenance deduction operation**。

**影响**: Depot 的 maintenance cost 在 economy pipeline 中没有对应的 ResourceOperation——实现者无法确定 maintenance 在 Resource Ledger 执行顺序中的位置、扣除来源（本地存储 vs 全局存储）、deficit 处理策略。

**修正建议**: 在 economy.idl.yaml 中增加 `MaintenanceDeduction` ResourceOperation（类别: maintenance），定义 per-structure per-tick 维护费扣除公式，并在 resource-ledger §4 执行顺序中插入。

---

### M2 — 08-api-idl.md body_cost 表 RangedAttack 与其他文档一致但 economy.idl.yaml 不一致（C4 的次级表现）

**位置**: `specs/gameplay/08-api-idl.md` §2 body_cost (L230) vs `design/gameplay.md` §2.1 body_part_types (L899) vs `specs/reference/economy.idl.yaml` §2.6 (L329)

**描述**:

三份文档中的 body part cost 比较：

| Body Part | design/gameplay.md | 08-api-idl.md | economy.idl.yaml |
|-----------|:---:|:---:|:---:|
| Move | 50 | 50 | 50 |
| Work | 100 | 100 | 100 |
| Carry | 50 | 50 | 50 |
| Attack | 80 | 80 | 80 |
| **RangedAttack** | **100** | **100** | **150** ⚠️ |
| Heal | 250 | 250 | 250 |
| Claim | 600 | 600 | 600 |
| Tough | 10 | 10 | 10 |

design 与 08-api-idl 在全部 8 项上一致——economy.idl.yaml 仅在 RangedAttack 上偏离。这强烈暗示 economy.idl.yaml 的 150 是孤立错误，而非系统性差异。

**修正建议**: 见 C4。

---

### M3 — global ↔ local transfer fee 在 economy.idl.yaml 中缺失

**位置**: `specs/reference/economy.idl.yaml` vs `specs/core/08-resource-ledger.md` §2.1 (L73–74) vs `design/gameplay.md` §2.2 (L310–313)

**描述**:

resource-ledger §2.1 定义了完整的 global transfer fee 参数：`global_deposit_fee = 100 bp (1.00%)`, `global_withdraw_fee = 500 bp (5.00%)`。design/gameplay.md §2.2 定义了 `transfer_to_global_cost = {Energy: 0.01}` (1%) 和 `transfer_from_global_cost = {Energy: 0.05}` (5%)——数值与 resource-ledger 一致。

但 economy.idl.yaml 中 **仅有 AlliedTransfer 的 fee (200 bp)**，没有 GlobalDeposit 或 GlobalWithdraw 的 fee operation。这意味着 economy IDL 作为机器可读经济规范，缺少两个核心 transfer operation。

**影响**: SDK 生成工具从 economy.idl.yaml 扫描 ResourceOperation 时，不会发现 global deposit/withdraw 的 fee 扣除逻辑——代码生成将漏掉 1% 和 5% 的 transfer fee。

**修正建议**: 在 economy.idl.yaml 中增加 `GlobalDepositFee` 和 `GlobalWithdrawFee` ResourceOperation（或合并为 `GlobalTransferFee`），包含 deposit_fee_bp (=100) 和 withdraw_fee_bp (=500) 参数。

---

## Low

### L1 — economy.idl.yaml AlliedTransfer 参数与 design 未交叉引用

**位置**: `specs/reference/economy.idl.yaml` §2.7 (L352–400) vs `design/gameplay.md`

**描述**:

economy.idl.yaml 的 AlliedTransfer 定义了完整的 fee (200 bp), delay (200 tick), cooldown (500 tick), daily_cap (10000 units) 参数，但 design/gameplay.md 中未独立定义联盟转移参数——仅在 resource-ledger §2.1 中有对应定义。作为 design 文档，gameplay.md 应至少以 summary 形式引用这些参数。

**修正建议**: 在 design/gameplay.md §2.2 资源与经济部分中增加联盟转移的经济参数 summary，引用 resource-ledger §2.1 为权威源。

---

### L2 — economy.idl.yaml ApiVersion 0.1.1 尚未包含 R23/R24 所有参数

**位置**: `specs/reference/economy.idl.yaml` changelog (L513–529)

**描述**:

economy.idl.yaml changelog 最新版本为 "0.1.1" (2026-06-18)，包含 R22 B2 修复（StorageTax percentage-based, UpkeepDeduction superlinear, AlliedTransfer 参数）。但 $2.3 Starting Resources & Free Upkeep（R23 D1/A 裁决）、$2.4 Controller Repair（R23 D4/A 裁决）均未反映在 economy.idl.yaml 的任何 ResourceOperation 或 limits 中。

**影响**: 新加入的 starting_resources、free_upkeep_controllers/drones/ticks、repair_cap、repair_distance_decay 在 economy IDL 中无 schema 定义——这意味着 IDL 代码生成器不会为这些参数生成类型和校验。

**修正建议**: 将 economy.idl.yaml 升级到 0.2.0，增加 WorldStartupSubsidy、FreeUpkeep（controller/drone/tick）、ControllerRepair（cost formula with cap + distance_decay）三个 ResourceOperation。

---

## Nash Equilibrium Issues

### N1 — 同步 free_upkeep 到期窗口（tick 2000）：可预测的全员脆弱期

**分析**:

`free_upkeep_ticks = 2000`（resource-ledger §2.3 L127）对所有新玩家统一——这意味着在同一天加入的 cohort 将在同一个 tick 窗口同时失去免维护保护。此时：
- 所有同 cohort 玩家突然开始支付 empire upkeep——包括 controller + drone 维护费。
- 若玩家未在 2000 tick 内建立足够的 faucer 管道（resource-ledger §2.3 Growth Path 假设 break-even 在 tick 2000+），将同时陷入 upkeep deficit 死亡螺旋。
- 攻击者可以精确计算窗口——在 tick 1990–2010 窗口集中攻击同 cohort 玩家，利用对手经济脆弱期。

**Severity**: 这是 Nash Equilibrium 问题而非 Critical——因为它是经济博弈策略层的发现，不影响技术正确性（参数定义一致、公式正确）。但这是 game design 层面的策略退化：所有玩家的脆弱窗口同步化，创造了可被利用的集体弱点。

**建议**:
- 加入 `free_upkeep_tick_jitter` 随机扰动（如 ±200 tick uniform random，每玩家独立），使脆弱窗口分散。
- 或加入 phased expiration：免维护逐步递减而非硬截止（如第 1800–2000 tick 维护费从 0% 线性增长到 100%）。

---

### N2 — 静止扩张均衡：O(n²) empire upkeep 在固定房间数处达到 Nash 均衡后无进一步扩张激励

**分析**:

empire upkeep 公式（resource-ledger §Empire Upkeep L264–266）为 superlinear：
```
upkeep = base_upkeep × rooms × (1 + rooms / room_soft_cap)
```

在 Standard 模式 (base_upkeep=50, room_soft_cap=10)：
- 1 room: 50 × 1 × 1.1 = 55
- 5 rooms: 50 × 5 × 1.5 = 375
- 10 rooms: 50 × 10 × 2.0 = 1,000
- 20 rooms: 50 × 20 × 3.0 = 3,000

边际 upkeep（第 n 间房）: `base_upkeep × (1 + 2n/room_soft_cap)` = 50 × (1 + 0.2n)。

当每间房的边际收入（source regeneration + harvester yield）≈ 边际 upkeep 时，玩家达到 Nash 均衡——不再有纯经济动机继续扩张。在 Standard 模式，均衡点约在 15–20 rooms 附近（取决于 source density 和 harvester 效率）。

**问题**:
1. **均衡后的行为退化**：达到均衡点的玩家失去了纯经济扩张的动机——可能转向纯军事 PvP（突袭 weaker players）或囤积。如果没有其他 progression 目标超越均衡点，后期游戏变成纯粹的资源重新分配（零和）。
2. **均衡点与 design 目标不一致**：design §2.2 长期目标系统定义了 GCL (Global Control Level)、殖民地年龄、RCL 等非线性目标——但这些是 progression 里程碑，不是持续经济激励。Player 在 20 rooms 处达到经济均衡后，GCL 的继续增长需要非经济动机驱动（Arena 段位、PvE 里程碑、Replay reputation）。
3. **equilibrium room count 可调但未文档化**：`room_soft_cap` 和 `base_upkeep` 是服主可调参数，可以移动均衡点——但 design 文档未讨论此机制作为 game design 调参杠杆的使用方式。

**Severity**: Nash Equilibrium 发现——经济模型收敛于固定点，这不是 bug 而是 game design 层面的特性。是否需要打破均衡（如引入递减的 empire upkeep scaling 或 per-room 规模效益）取决于 design 意图。

**建议**:
- 在 design/gameplay.md 或 economy-balance-sheet.md 中文档化 empire upkeep formula 的均衡点分析——使服主理解调参后果。
- 考虑在 design 中明确声明：Vannila 的 empire upkeep 设计目标就是在 ~20 rooms 处收敛——超大型帝国需依靠非经济手段维持（联盟、PvE、Arena）。

---

## Review Statistics

| Metric | Value |
|--------|-------|
| Documents reviewed | 6 |
| Critical findings | 4 |
| High findings | 2 |
| Medium findings | 3 |
| Low findings | 2 |
| Nash Equilibrium issues | 2 |
| Cross-domain items | 0 |

---

*Review completed 2026-06-20. 下一轮 Closure Verification 建议重点关注 C1 (building costs alignment) — 这是最大面积的不一致，涉及 7/11 建筑类型的 cost 偏差；C2 (global_transfer_delay) — 10–20× 差异改变核心 anti-dominant-strategy 的战术时间窗口；C3 (Recycle flat vs proportional) — 已在 R23 共识中指出但尚未修正 08-api-idl.md 的硬编码 `* 0.5`。*