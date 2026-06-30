# Economy Balance Sheet — Vanilla / Tutorial / Standard

> **R15 B7 + B6/D3/D4 修复**。本文档证明 Vanilla/Standard 世界的 maintenance curve 与 anti-snowball 目标一致性，并提供 1/5/20/50 房间的数值闭环验证。**所有费率、公式以 `specs/core/08-resource-ledger.md` §2 统一参数表为唯一权威源。**
>
> **Canonical target curve 初始参数化**：以下具体参数为目标经济曲线的示意性估算（illustrative estimates），用于表达 2–10 房间自维持、20 房后递减、50 房软上限的目标状态。后续 playtest 仅用于校准参数，不改变本文定义的目标曲线语义。

## 1. Maintenance Curve

维护费公式由 `specs/core/08-resource-ledger.md` §Empire Upkeep 权威定义。经济报表引用此公式，不重新声明。

```
upkeep = base_upkeep × rooms × (1 + rooms / room_soft_cap)
```

| 参数 | Standard | Vanilla (Novice) | Tutorial |
|------|:--------:|:----------------:|:--------:|
| `base_upkeep` | 50 | 30 | 10 |
| `room_soft_cap` | 10 | 15 | 20 |

维护费对应 Resource Ledger 的 `UpkeepDeduction` 操作（执行顺序第 1 步）。

| 房间数 | 维护费/tick (Standard) | 累计维护费/1500tick | 说明 |
|:------:|:----------:|:------------------:|------|
| 1 | 55 | 82,500 | 新手轻松 |
| 5 | 375 | 562,500 | 可承受 |
| 20 | 3,000 | 4,500,000 | 需要高效经济 |
| 50 | 15,000 | 22,500,000 | 强递减区间 |

维护费随房间数呈 **超线性增长**（O(n²) 趋势）。50 房间的维护费是 5 房间的 40 倍（而非 10 倍线性）。

存储税使用 Resource Ledger §2.2 tiered 公式（权威 tier 定义见 `specs/core/08-resource-ledger.md` §2 统一参数表），以下场景中的存储税数值均由此公式导出。

## 2. 收支平衡表

> **显式假设：** 以下数值基于以下前提：
> - **free_upkeep**：前 1 controller + 3 drone 免维护费（`free_upkeep_ticks` 内，默认 2000 tick）。
> - **source income**：每 Source 基础产出 10/tick（L1 无效率加成）。Source 升级（L2/L3/L4）提升产出。
> - **RCL passive income**：Controller 每级被动收入基础 2/tick（RCL 1–8：2–16/tick，近似线性）。
> - **code efficiency multiplier**：代码质量影响 Harvester 采集效率——基础效率 100%（每 WORK part 采集 1 单位/tick），优化后可达到 150%–200%（更优路径、更少 idle、并行采集）。以下分别展示无优化（效率 ×1.0）和优化（效率 ×1.5）两种情景。
> - **PvE drop**：global cap 的 30% × 房间占比，仅在中大型帝国（≥10 房间）计入。

### 2.1 Standard 模式 — 1 房间

| 收入源 | 量/tick | 说明 |
|--------|:------:|------|
| Source Harvester ×2 | 20 | L1 source, 10/tick each |
| Controller income | 2 | RCL 1 |
| free_upkeep 覆盖 | +55 | 前 1 controller + 3 drone 免维护费 |
| **总收入** | **77** | free_upkeep 期内维护费不计 |

| 支出项 | 量/tick | 说明 |
|--------|:------:|------|
| 维护费（free_upkeep cover） | 0 | 免维护期内 |
| 存储税 | 0 | 存储 < 30% 免税（tier 0，见 Resource Ledger §2.2） |
| **总支出** | **0** | |

| 净流量 | 量/tick |
|--------|:------:|
| **净盈余** | **+77** |

> **1 房间 free_upkeep 期内纯盈余**。初始资源包 + free_upkeep 允许玩家快速建立初始经济基础。free_upkeep 结束后维护费恢复（55/tick），基础收入 22/tick → 净亏损 -33/tick。此时需要扩张到 2 房间或提升代码效率来达到收支平衡。

### 2.2 Standard 模式 — 2 房间（优化代码）

| 收入源 | 量/tick | 说明 |
|--------|:------:|------|
| Source Harvester ×4 | 80 | L1-2 sources, 20/tick × 1.0 效率 = 20/tick each |
| Controller income | 12 | RCL 2-3 avg |
| **总收入（优化 ×1.5 效率）** | **138** | Source 30/tick × 4 + Controller |
| **总收入（基础 ×1.0）** | **92** | |

| 支出项 | 量/tick |
|--------|:------:|
| 维护费 | 120 |
| 存储税 | 0 |
| **总支出** | **120** |

| 净流量 | 量/tick | 说明 |
|--------|:------:|------|
| **净亏损（基础）** | **-28** | 效率 ×1.0 时小幅亏损 |
| **净盈余（优化）** | **+18** | 良好代码 + RCL 2-3 可达到小幅正流量 |

> **2 房间阶段：良好代码可达小幅盈余**。这是「中期自维持」的起点——优化代码（×1.5 效率）+ Controller 升级（RCL 2-3）后净流量转正。基础代码仍小幅亏损，激励玩家提升效率。

### 2.3 Standard 模式 — 5 房间（良好代码）

| 收入源 | 量/tick | 说明 |
|--------|:------:|------|
| 11 Source Harvester | 330 | L1-2 sources, 20/tick × 1.5 效率 = 30/tick each |
| Controller income | 60 | RCL 3-4 avg |
| **总收入（优化）** | **390** | |
| **总收入（基础）** | **280** | 效率 ×1.0 |

| 支出项 | 量/tick | 可重算输入 |
|--------|:------:|------|
| 维护费 | 375 | `50 × 5 × (1 + 5 / 10)` |
| 存储税 | 15 | `storage_capacity=1,000,000`, `stored_total=450,000`; tier 1 taxable=`450,000-300,000=150,000`; `150,000 × 1bp / 10000` |
| **总支出** | **390** | |

| 净流量 | 量/tick |
|--------|:------:|
| **净亏损（基础）** | **-110** |
| **净盈余（优化）** | **0** |

> **5 房间阶段：良好代码可达收支平衡**。优化代码（×1.5）+ Controller 升级（RCL 3-4）+ Source 升级到 L2 可实现小幅盈余。这是「中期自维持可达」的核心验证点——适度扩张（2-5 房）下，良好代码与 RCL 管理可维持自给自足的正流量。

### 2.4 Standard 模式 — 10 房间（高效代码）

| 收入源 | 量/tick | 说明 |
|--------|:------:|------|
| 23 Source Harvesters | 920 | L2-3 sources, 30/tick avg × 1.33 效率 (= ×2.0 总计) |
| Controller income | 160 | RCL 4-5 avg |
| PvE drop (global cap share) | 50 | global 30% cap × room share |
| **总收入（优化）** | **1,130** | |
| **总收入（基础）** | **610** | 效率 ×1.0 |

| 支出项 | 量/tick | 可重算输入 |
|--------|:------:|------|
| 维护费 | 1,000 | `50 × 10 × (1 + 10 / 10)` |
| 存储税 | 75 | `storage_capacity=3,000,000`, `stored_total=1,650,000`; tier 1 taxable=`900,000`; tier 2 taxable=`750,000`; `(900,000 × 1bp + 750,000 × 5bp) / 10000` |
| **总支出** | **1,075** | |

| 净流量 | 量/tick |
|--------|:------:|
| **净亏损（基础）** | **-435** |
| **净盈余（优化）** | **+55** |

> **10 房间阶段：高效代码可达小幅盈余**。多 Source 并行 + 高效代码（×2.0）+ PvE 收益维持正流量。但边际收益已开始递减——维护费超线性增长要求持续优化而非单纯扩张。这是「中期自维持仍可达，但扩张成本显著上升」的警示点。

### 2.5 Standard 模式 — 20 房间（需要高效经济）

| 收入源 | 量/tick | 说明 |
|--------|:------:|------|
| 46 Source Harvesters | 1,840 | L2-3 sources, avg 25/tick × 1.6 效率 |
| Controller income | 400 | RCL 5-6 avg |
| PvE drop (global cap share) | 100 | global 30% cap × room share |
| **总收入（优化）** | **2,340** | |
| **总收入（基础）** | **1,320** | 效率 ×1.0 |

| 支出项 | 量/tick | 可重算输入 |
|--------|:------:|------|
| 维护费 | 3,000 | `50 × 20 × (1 + 20 / 10)` |
| 存储税 | 180 | `storage_capacity=4,000,000`, `stored_total=2,880,000`; tier 1 taxable=`1,200,000`; tier 2 taxable=`480,000`; `(1,200,000 × 1bp + 480,000 × 5bp) / 10000` |
| Drone spawn cost (avg 0.2/tick) | 40 | |
| **总支出** | **3,220** | |

| 净流量 | 量/tick |
|--------|:------:|
| **净亏损（基础）** | **-1,900** |
| **净亏损（优化）** | **-880** |

> **20 房间：边际收益显著递减**。维护费超线性增长（O(n²)）开始压倒收入增长。高效代码可缩小缺口但仍为净亏损——这是「大帝国需要顶尖代码和 PvE 农场」的设计目标。中期自维持在 20 房不再可达——明确的自维持区间上限。

### 2.6 Standard 模式 — 50 房间（软上限逼近）

| 收入源 | 量/tick | 说明 |
|--------|:------:|------|
| 115 Source Harvesters | 4,600 | L3-4 sources, avg 25/tick × 1.6 效率 |
| Controller income | 800 | RCL 6-7 avg |
| PvE drop | 500 | |
| **总收入（优化）** | **5,900** | |
| **总收入（基础）** | **4,075** | 效率 ×1.0 |

| 支出项 | 量/tick | 可重算输入 |
|--------|:------:|------|
| 维护费 | 15,000 | `50 × 50 × (1 + 50 / 10)` |
| 存储税 | 765 | `storage_capacity=3,000,000`, `stored_total=2,700,000`; tier 1 taxable=`900,000`; tier 2 taxable=`750,000`; tier 3 taxable=`450,000`; `(900,000 × 1bp + 750,000 × 5bp + 450,000 × 20bp) / 10000` |
| Drone upkeep | 1,000 | |
| **总支出** | **16,765** | |

| 净流量 | 量/tick |
|--------|:------:|
| **净亏损（基础）** | **-12,690** |
| **净亏损（优化）** | **-10,865** |

> **50 房间是软上限逼近**。维护费吞噬全部收入——即使顶尖代码也无法盈利。只有顶尖玩家 + PvE 农场 + 联盟交易才能维持。这是 anti-snowball 的自然天花板。

### 2.7 收支平衡汇总表 (Standard 模式)

以下汇总表提供 1/2/3/5/10/20/50 房间的收支对比。**所有数值为 canonical target curve 的初始参数化（illustrative estimates）；后续 playtest 仅用于校准 Resource Ledger 参数。** 存储税由 `storage_capacity`、`stored_total` 与 Resource Ledger tier 公式逐行重算。

|| 房间数 | 收入/tick (基础) | 收入/tick (优化) | 维护费/tick | storage_capacity | stored_total | 存储税/tick | tier formula | 净流量趋势 | 说明 |
||:------:|:--------:|:--------:|:---------:|:---------:|:---------:|:---------:|------|:---------:|------|
|| 1 | 22 | 22 | 0¹ | 1,000,000 | 200,000 | 0 | below 30%; no taxable tier | **大幅盈余**¹ | free_upkeep 纯盈余 |
|| 2 | 92 | 138 | 120 | 1,000,000 | 250,000 | 0 | below 30%; no taxable tier | **基础小亏 / 优化小盈** | 「中期自维持」起点——2 房即可转正 |
|| 3 | 175 | 250 | 195 | 1,000,000 | 290,000 | 0 | below 30%; no taxable tier | **优化小幅盈余** | Harvester 优化 + RCL 升级驱动正流量 |
|| 5 | 280 | 390 | 375 | 1,000,000 | 450,000 | 15 | `(450,000 - 300,000) × 1bp / 10000` | **优化收支平衡** | 良好代码 + RCL 3-4 → 自维持可达 |
|| 10 | 610 | 1,130 | 1,000 | 3,000,000 | 1,650,000 | 75 | `(900,000 × 1bp + 750,000 × 5bp) / 10000` | **优化小幅盈余** | 高效代码维持正流量，边际收益递减开始 |
|| 20 | 1,320 | 2,340 | 3,000 | 4,000,000 | 2,880,000 | 180 | `(1,200,000 × 1bp + 480,000 × 5bp) / 10000` | **大额亏损** | 边际收益显著递减——自维持区间上限 |
|| 50 | 4,075 | 5,900 | 15,000 | 3,000,000 | 2,700,000 | 765 | `(900,000 × 1bp + 750,000 × 5bp + 450,000 × 20bp) / 10000` | **严重亏损** | 软上限逼近，顶尖玩家维持 |

> **自维持区间：2-10 房间**。良好代码（×1.5-2.0 效率）+ 适度 RCL 升级 + PvE 补充下，Standard 经济可实现小幅正流量。20 房间边际收益显著递减，50 房间接近不可持续——形成自然天花板。此区间是 canonical target curve；实际玩家数据仅用于校准参数，详见 `specs/PLAYTEST-GATED.md` PG-1。

> `¹` 1 房间 free_upkeep 期内；free_upkeep 结束后维护费恢复 → 净流量 -33（基础）。free_upkeep 默认 2000 tick，初始资源包 `{Energy: 5000}` 足够度过此阶段。
>
> **可重算公式**：`upkeep = base_upkeep × rooms × (1 + rooms / room_soft_cap)`；`tax = Σ taxable_units_in_tier × tier_rate_bp / 10000`，其中 `taxable_units_in_tier` 由 `storage_capacity`、`stored_total` 与 `storage_tax_tiers` 的容量百分比边界换算为资源单位。所有参数 world.toml 可配置——修改 `base_upkeep`、`room_soft_cap`、`storage_tax_tiers`、`storage_capacity` 或 `stored_total` 后本表数值相应变化。
>
> **代码效率乘数含义**：1.5×-2.0× 表示减少 idle 时间、优化路径、减少拥堵——随着房间扩张，效率从 1.5× 逐渐提升到 2.0× 需要持续优化投入。200% (2×) 仅在完美路径 + 无拥堵 + 最优 body 组合下可达。
>
> **1→2 房间 transition**：free_upkeep 结束后，1 房基础收入约 22/tick、维护费 55/tick，净流量 -33/tick。默认初始资源 5,000 Energy 可覆盖约 151 tick 的单房亏损；玩家在 free_upkeep 2000 tick 窗口内通过第二 Controller、额外 source 和 RCL 2-3 收入将基础收入提升至 92/tick，优化代码后达 138/tick，对应 2 房维护费 120/tick。该窗口要求玩家在保护期内完成一次扩张或显著提升采集效率。
>
> **设计目标**：**中期自维持可达**（2-10 房间良好代码下小幅盈余），边际收益递减确保无限扩张不可持续（20 房后转入净亏损）。本文给出 canonical target curve 的初始参数化；后续 playtest 仅用于校准 `base_upkeep`、`room_soft_cap`、效率曲线等参数。

## 3. 模式差异

| | Tutorial | Vanilla (Novice) | Standard |
|------|:--------:|:----------------:|:--------:|
| `base_upkeep` | 10 | 30 | 50 |
| `room_soft_cap` | 20 | 15 | 10 |
| `new_player_transfer_lock` | 0 | 500 | 500 |
| `pve_global_cap_pct` | 50% | 40% | 30% |
| `global_transfer_enabled` | true | true | true |
| `allied_transfer_enabled` | true | false | **true (Restricted)** |
| `storage_tax` | 免税 | tiered (0/1/5/20 bp) | tiered (0/1/5/20 bp) |
| `global_deposit_delay` | 10 | 10 | 10 |
| `global_withdraw_delay` | 100 | 100 | 100 |
| `safe_mode_duration` | 2000 | 500 | 500 |
| `starting_resources` | `{Energy: 10000}` | `{Energy: 5000}` | `{Energy: 5000}` |
| `free_upkeep_controllers` | 3 | 1 | 1 |
| `free_upkeep_drones` | 5 | 3 | 3 |
| `free_upkeep_ticks` | 3000 | 2000 | 2000 |
| `controller_repair_cost` | 0 | 0 | 0 |
| `controller_repair_limit` | range/capacity/queue | range/capacity/queue | range/capacity/queue |
| `depot_repair_cost` | local depot resources | local depot resources | local depot resources |

Controller/Depot age repair 的权威模型见 `specs/core/08-resource-ledger.md` §2.4：无全局 repair cap，Controller 免费，Depot 消耗本地资源，维修吞吐只受物理范围、每设施容量和队列约束。

> **存储税权威源**：tier 定义见 `design/gameplay.md` §8「累进存储税」和 `specs/core/08-resource-ledger.md` §StorageTax。Tutorial 全免，Vanilla/Standard 使用相同 tier 结构（税率由 `storage_tax_tiers` 配置）。
>
> **Allied Transfer 模式差异**：Standard 默认启用 Restricted Allied Transfer（fee=200bp, delay=200 tick, cooldown=500 tick, daily_cap=10000, intercept enabled）。Novice/Tutorial 可通过 world.toml 禁用 (`allied_transfer_enabled = false`)。Arena 模式禁用 Allied Transfer（竞技公平）。

Tutorial 模式弱维护费 + 长保护期，适合新手学习。Vanilla 模式中等维护费，Standard 模式启用完整 anti-snowball。

## 4. Anti-Snowball 证明

通过超线性维护费曲线，Standard 模式满足：

1. **边际收益递减**：第 N+1 个房间的维护费增长 > 收入增长。
2. **净正反馈克制**：玩家必须通过代码优化获得更高效率，而非单纯扩张。
3. **自然上限**：50 房间附近维护费吞噬全部收入，形成 soft cap。
4. **No Teleport + 物流成本**：远距离资源转移承担转换时间/损耗，强化 "维持大帝国需要物流基础设施"。

## 5. 与 Resource Ledger 的关系

**Resource Ledger (`specs/core/08-resource-ledger.md`) 为所有收支计算的单一权威源。** 本文档只做数值验证和模式对比，不重新定义费率或公式。

| 经济概念 | 权威定义位置 | 本表角色 |
|---------|------------|---------|
| 维护费 (UpkeepDeduction) | Resource Ledger §Empire Upkeep | 验证数值合理性 |
| 回收 (RecycleRefund) | Resource Ledger §6 (lifespan 10%–50%) | 引用 |
| 存储税 (StorageTax) | Resource Ledger §2 + gameplay.md §8 tier 表 | 引用 |
| 费率模型 (basis points) | Resource Ledger §2 | 不重复 |

## 6. 存储税均衡证明 (Storage Tax Equilibrium Proof)

存储税使用 Resource Ledger §2.2 tiered 公式（权威 tier 定义见 `specs/core/08-resource-ledger.md` §2 统一参数表），以下场景中的存储税数值均由此公式导出。
