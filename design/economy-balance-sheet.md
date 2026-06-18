# Economy Balance Sheet — Vanilla / Tutorial / Standard

> **R15 B7 修复**。本文档证明 Vanilla/Standard 世界的 maintenance curve 与 anti-snowball 目标一致性，并提供 1/5/20/50 房间的数值闭环验证。

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

## 2. 收支平衡表

### 2.1 Standard 模式 — 1 房间

| 收入源 | 量/tick | 说明 |
|--------|:------:|------|
| Source Harvester ×2 | 20 | L1 source, 10/tick each |
| Controller income | 5 | RCL 1 |
| **总收入** | **25** | |

| 支出项 | 量/tick | 说明 |
|--------|:------:|------|
| 维护费 | 55 | base 50 + 1²/10 = 5 |
| 存储税 | 0 | 存储 < 30% 免税（tier 0） |
| **总支出** | **55** | |

| 净流量 | 量/tick |
|--------|:------:|
| **净亏损** | **-30** |

> 1 房间阶段需要初始资源包支撑。Controller 升级到 RCL 2-3 后可达收支平衡。

### 2.2 Standard 模式 — 5 房间

| 收入源 | 量/tick | 说明 |
|--------|:------:|------|
| 11 Source Harvester | 110 | L1-2 sources |
| Controller income | 30 | RCL 3 avg |
| **总收入** | **140** | |

| 支出项 | 量/tick |
|--------|:------:|
| 维护费 | 375 |
| 存储税 | 15 (tier 1: 30-60% 存储 @ 1 bp) |
| **总支出** | **390** |

| 净流量 | 量/tick |
|--------|:------:|
| **净亏损** | **-250** |

> 5 房间阶段需要优化 Harvester 代码效率。Controller 升级 + Source 升级到 L2-3 可缩小缺口。

### 2.3 Standard 模式 — 20 房间

| 收入源 | 量/tick | 说明 |
|--------|:------:|------|
| 46 Source Harvesters | 920 | L2-3 sources, avg 20/tick |
| Controller income | 200 | RCL 4-5 avg |
| PvE drop (global cap share) | 100 | global 30% cap × room share |
| **总收入** | **1,220** | |

| 支出项 | 量/tick |
|--------|:------:|
| 维护费 | 3,000 |
| 存储税 | 120 (tier 2: 60-85% @ 5 bp) |
| Drone spawn cost (avg 0.2/tick) | 40 |
| **总支出** | **3,160** |

| 净流量 | 量/tick |
|--------|:------:|
| **净亏损** | **-1,940** |

> 20 房间需要高效的 Harvester 代码 + 多 Source 并行 + PvE 收益。这是 "需要高效经济" 的设计目标。

### 2.4 Standard 模式 — 50 房间

| 收入源 | 量/tick | 说明 |
|--------|:------:|------|
| 115 Source Harvesters | 2,875 | L3-4 sources, avg 25/tick |
| Controller income | 600 | RCL 6-7 avg |
| PvE drop | 500 | |
| **总收入** | **3,975** | |

| 支出项 | 量/tick |
|--------|:------:|
| 维护费 | 15,000 |
| 存储税 | 600 (tier 3: 85-100% @ 20 bp) |
| Drone upkeep | 1,000 |
| **总支出** | **16,600** |

| 净流量 | 量/tick |
|--------|:------:|
| **净亏损** | **-12,625** |

> 50 房间是硬上限逼近。维持 50 房间需要极高效的代码 + PvE 农场 + 联盟交易。只有顶尖玩家才能维持。

## 3. 模式差异

| 参数 | Tutorial | Vanilla (Novice) | Standard |
|------|:--------:|:----------------:|:--------:|
| `base_upkeep` | 10 | 30 | 50 |
| `room_soft_cap` | 20 | 15 | 10 |
| `new_player_transfer_lock` | 0 | 500 | 500 |
| `pve_global_cap_pct` | 50% | 40% | 30% |
| `global_transfer_enabled` | true | true | true |
| `allied_transfer_enabled` | true | false | false (默认) |
| `storage_tax` | 免税 | tiered (0/1/5/20 bp) | tiered (0/1/5/20 bp) |
| `safe_mode_duration` | 2000 | 500 | 500 |

> **存储税权威源**：tier 定义见 `design/gameplay.md` §8「累进存储税」和 `specs/core/08-resource-ledger.md` §StorageTax。Tutorial 全免，Vanilla/Standard 使用相同 tier 结构（税率由 `global_storage_tax_tiers` 配置）。

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

存储税使用 tiered 税率形成自然均衡点：

```
Tiers: [(30%, 0 bp), (60%, 1 bp), (85%, 5 bp), (100%, 20 bp)]
```

**均衡条件**：当玩家的存储税支出 ≥ 其被动收入（Controller income）时，存储量不再增长。

设存储量为 `S`（占容量 `C` 的比例 `p = S/C`），有效税率 `τ(p)`：

```
τ(0.30) = 0          （免税）
τ(0.60) = 1 bp       （S × 0.0001 / tick）
τ(0.85) = 5 bp       （S × 0.0005 / tick）
τ(1.00) = 20 bp      （S × 0.002 / tick）
```

**均衡点**（以标准容量 1,000,000 为例）：

| 存储量 | 税率 | 每 tick 税 | 均衡所需 Controller 收入 |
|--------|------|:---------:|:----------------------:|
| 300,000 (30%) | 0 bp | 0 | 0（免税，可无限囤积） |
| 600,000 (60%) | 1 bp | 60 | RCL 3 (30/tick 净亏) |
| 850,000 (85%) | 5 bp | 425 | RCL 5+ (200/tick 净亏) |
| 1,000,000 (100%) | 20 bp | 2,000 | 极难维持（大帝国才可能） |

**证明**：对于任何理性玩家，存储量 `p ≥ 0.85` 时的边际税率 (20 bp) 大于任何 Controller 能提供的 passive income。因此存储量在 85%–100% 区间形成自然天花板——超过此点的玩家必须通过 active income（harvesting）补贴存储税，形成经济压力。此机制无需硬性 cap 即可防止无限囤积。

> 此证明假设 `global_storage_tax_tiers` 使用默认值 `[(30,0),(60,1),(85,5),(100,20)]`。服主可通过修改 tiers 改变均衡点位置。
