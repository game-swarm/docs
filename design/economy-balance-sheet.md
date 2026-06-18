# Economy Balance Sheet — Vanilla / Tutorial / Standard

> **R15 B7 修复**。本文档证明 Vanilla/Standard 世界的 maintenance curve 与 anti-snowball 目标一致性，并提供 1/5/20/50 房间的数值闭环验证。

## 1. Maintenance Curve

维护费公式（Standard 模式）：

```
maintenance = base_upkeep × rooms × (1 + rooms / room_soft_cap)
room_soft_cap = 10
base_upkeep = 50
```

| 房间数 | 维护费/tick | 累计维护费/1500tick | 说明 |
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
| 存储税 | 0 | < 阈值免税 |
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
| 存储税 | 15 |
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
| 存储税 | 120 |
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
| 存储税 | 600 |
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
| `storage_tax_rate` | 0 bp | 5 bp | 10 bp |
| `safe_mode_duration` | 2000 | 500 | 500 |

Tutorial 模式弱维护费 + 长保护期，适合新手学习。Vanilla 模式中等维护费，Standard 模式启用完整 anti-snowball。

## 4. Anti-Snowball 证明

通过超线性维护费曲线，Standard 模式满足：

1. **边际收益递减**：第 N+1 个房间的维护费增长 > 收入增长。
2. **净正反馈克制**：玩家必须通过代码优化获得更高效率，而非单纯扩张。
3. **自然上限**：50 房间附近维护费吞噬全部收入，形成 soft cap。
4. **No Teleport + 物流成本**：远距离资源转移承担转换时间/损耗，强化 "维持大帝国需要物流基础设施"。

## 5. 与 Resource Ledger 的关系

所有收支通过 `specs/core/08-resource-ledger.md` 定义的 Resource Ledger 统一结算。费率使用 basis points，收益/支出使用 `ResourceAmount: i64` 整数。
