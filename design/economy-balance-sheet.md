# Economy Balance Sheet — Vanilla / Tutorial / Standard

> **R15 B7 + B6/D3/D4 修复**。本文档证明 Vanilla/Standard 世界的 maintenance curve 与 anti-snowball 目标一致性，并提供 1/5/20/50 房间的数值闭环验证。**所有费率、公式以 `specs/core/08-resource-ledger.md` §2 统一参数表为唯一权威源。**

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
| 50 | 15,000 | 22,500,000 | 硬上限逼近 |

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
| Source Harvester ×4 | 60 | L1 source, 10/tick × 1.5 效率 = 15/tick each |
| Controller income | 6 | RCL 1–2 avg |
| **总收入** | **66** | |

| 支出项 | 量/tick |
|--------|:------:|
| 维护费 | 120 |
| 存储税 | 0 |
| **总支出** | **120** |

| 净流量 | 量/tick | 说明 |
|--------|:------:|------|
| **净亏损（基础）** | **-54** | 效率 ×1.0 时 |
| **净亏损（优化）** | **-54** | 效率 ×1.5 亦亏；需 Controller 升级至 RCL 3+ |

> **2 房间阶段仍亏损**，但通过 Controller 升级（RCL 3→被动收入 6/tick）+ 优化代码可趋近收支平衡。此为「快速扩张期」——玩家应同时提升 RCL 和代码效率。

### 2.3 Standard 模式 — 5 房间（良好代码）

| 收入源 | 量/tick | 说明 |
|--------|:------:|------|
| 11 Source Harvester | 165 | L1-2 sources, 10/tick × 1.5 效率 |
| Controller income | 30 | RCL 3 avg |
| **总收入（优化）** | **195** | |
| **总收入（基础）** | **140** | 效率 ×1.0 |

| 支出项 | 量/tick |
|--------|:------:|
| 维护费 | 375 |
| 存储税 | 15 (tier 1: 30-60% @ 1 bp) |
| **总支出** | **390** |

| 净流量 | 量/tick |
|--------|:------:|
| **净亏损（基础）** | **-250** |
| **净亏损（优化）** | **-195** |

> **5 房间阶段优化代码可显著缩小缺口**。Controller 升级 + Source 升级到 L2-3，配合 1.5× 效率，可接近收支平衡。这是「代码效率成为主要差异化因素」的转折点。

### 2.4 Standard 模式 — 10 房间（高效代码）

| 收入源 | 量/tick | 说明 |
|--------|:------:|------|
| 23 Source Harvesters | 690 | L2-3 sources, 20/tick × 1.5 效率 |
| Controller income | 80 | RCL 4 avg |
| PvE drop (global cap share) | 50 | global 30% cap × room share |
| **总收入（优化）** | **820** | |
| **总收入（基础）** | **560** | 效率 ×1.0 |

| 支出项 | 量/tick |
|--------|:------:|
| 维护费 | 1,000 |
| 存储税 | 45 (tier 1: 40-55% @ 1 bp) |
| **总支出** | **1,045** |

| 净流量 | 量/tick |
|--------|:------:|
| **净亏损（基础）** | **-485** |
| **净亏损（优化）** | **-225** |

> **10 房间阶段：优秀代码（2× 效率）可趋近收支平衡**。多 Source 并行 + PvE 收益开始发挥作用。这是「高效经济」的门槛——代码质量直接决定能否盈利。

### 2.5 Standard 模式 — 20 房间（需要高效经济）

| 收入源 | 量/tick | 说明 |
|--------|:------:|------|
| 46 Source Harvesters | 1,380 | L2-3 sources, avg 20/tick × 1.5 效率 |
| Controller income | 200 | RCL 4-5 avg |
| PvE drop (global cap share) | 100 | global 30% cap × room share |
| **总收入（优化）** | **1,680** | |
| **总收入（基础）** | **1,220** | 效率 ×1.0 |

| 支出项 | 量/tick |
|--------|:------:|
| 维护费 | 3,000 |
| 存储税 | 120 (tier 2: 60-85% @ 5 bp) |
| Drone spawn cost (avg 0.2/tick) | 40 |
| **总支出** | **3,160** |

| 净流量 | 量/tick |
|--------|:------:|
| **净亏损（基础）** | **-1,940** |
| **净亏损（优化）** | **-1,480** |

> **20 房间：需要高效经济 + PvE 收益**。边际收益开始递减——维护费超线性增长（O(n²)），收入增长放缓。即使 2× 效率也难以盈利。这是「大帝国必须有顶尖代码和 PvE 农场」的设计目标。

### 2.6 Standard 模式 — 50 房间（软上限逼近）

| 收入源 | 量/tick | 说明 |
|--------|:------:|------|
| 115 Source Harvesters | 4,312 | L3-4 sources, avg 25/tick × 1.5 效率 |
| Controller income | 600 | RCL 6-7 avg |
| PvE drop | 500 | |
| **总收入（优化）** | **5,412** | |
| **总收入（基础）** | **3,975** | 效率 ×1.0 |

| 支出项 | 量/tick |
|--------|:------:|
| 维护费 | 15,000 |
| 存储税 | 600 (tier 3: 85-100% @ 20 bp) |
| Drone upkeep | 1,000 |
| **总支出** | **16,600** |

| 净流量 | 量/tick |
|--------|:------:|
| **净亏损（基础）** | **-12,625** |
| **净亏损（优化）** | **-11,188** |

> **50 房间是软上限逼近**。维护费吞噬全部收入——即使顶尖代码（2× 效率）也无法盈利。只有顶尖玩家 + PvE 农场 + 联盟交易才能维持。这是 anti-snowball 的自然天花板。

### 2.7 收支平衡汇总表 (Standard 模式)

### 2.7 收支平衡汇总表 (Standard 模式)

以下汇总表提供 1/2/3/5/10/20/50 房间的收支对比。**所有数值为示意性估算（illustrative estimates）——精确参数和平衡点推迟至 Resource Ledger spec 实施/playtest 阶段确定。** 利用率假设：1-3 房间 <30% 存储（免税），5 房间 ~40%，10 房间 ~55%，20 房间 ~70%，50 房间 ~90%。

| 房间数 | 收入/tick (基础) | 收入/tick (优化 ×1.5) | 维护费/tick | 存储税/tick | 净流量趋势 | 说明 |
|:------:|:--------:|:--------:|:---------:|:---------:|:---------:|------|
| 1 | 22 | 22 | 0¹ | 0 | **大幅盈余**¹ | free_upkeep 纯盈余 |
| 2 | 48 | 66 | 120 | 0 | **亏损** | 快速扩张期，需升级 RCL |
| 3 | 72 | 99 | 195 | 0 | **亏损** | Harvester 优化开始见效 |
| 5 | 140 | 195 | 375 | 15 | **亏损** | 代码效率成为关键差异化 |
| 10 | 560 | 820 | 1,000 | 45 | **亏损** | 2× 效率可趋近平衡 |
| 20 | 1,220 | 1,680 | 3,000 | 120 | **大额亏损** | 需要高效经济 + PvE 收益 |
| 50 | 3,975 | 5,412 | 15,000 | 600 | **严重亏损** | 软上限逼近，顶级玩家维持 |

> ¹ 1 房间 free_upkeep 期内；free_upkeep 结束后维护费恢复 → 净流量 -33（基础）。free_upkeep 默认 2000 tick，初始资源包 `{Energy: 5000}` 足够度过此阶段。
>
> **可重算公式**：`upkeep = base_upkeep × rooms × (1 + rooms / room_soft_cap)`，`tax = storage_amount × tax_rate_bp / 10000`（tax_rate_bp 由 `global_storage_tax_tiers` 按存储利用率查表）。所有参数 world.toml 可配置——修改 `base_upkeep`、`room_soft_cap`、`storage_tax_tiers` 后本表数值相应变化。
>
> **代码效率乘数含义**：1.5× 表示减少 idle 时间、优化路径、减少拥堵——相当于减少 33% 的采集浪费。200% (2×) 仅在完美路径 + 无拥堵 + 最优 body 组合下可达。
>
> **设计目标**：self-sustaining（收支平衡）在优化代码 + 适度扩张条件下可达，但边际收益递减确保无限扩张不可持续。精确平衡参数（base_upkeep、room_soft_cap、效率曲线）推迟至实施/playtest 阶段通过数据驱动校准——不应在 spec 阶段硬编码具体赤字数字。

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
| `starting_resources` | `{Energy: 10000, Minerals: 5000}` | `{Energy: 5000, Minerals: 2000}` | `{Energy: 5000, Minerals: 2000}` |
| `free_upkeep_controllers` | 3 | 1 | 1 |
| `free_upkeep_drones` | 5 | 3 | 3 |
| `free_upkeep_ticks` | 3000 | 2000 | 2000 |
| `repair_cap` | 5000 bp (50%) | 3500 bp (35%) | 3500 bp (35%) |
| `repair_distance_decay` | 0 bp | 500 bp (5%/tile) | 500 bp (5%/tile) |

> **存储税权威源**：tier 定义见 `design/gameplay.md` §8「累进存储税」和 `specs/core/08-resource-ledger.md` §StorageTax。Tutorial 全免，Vanilla/Standard 使用相同 tier 结构（税率由 `global_storage_tax_tiers` 配置）。
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
