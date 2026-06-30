# Economy Balance Sheet — Vanilla / Tutorial / Standard

> 以下具体参数为目标经济曲线的示意性估算，用于表达 1-3 房间基础代码正流、5-10 房间普通代码停滞、15+ 房间由顶级代码消化经济惩罚的目标状态。实测校准只调整参数，不改变本文定义的目标曲线语义。

## 1. Maintenance Curve

维护费公式由 `specs/core/resource-ledger.md` §Empire Upkeep 权威定义。经济报表引用此公式，不重新声明。

```
upkeep = base_upkeep × rooms × (1 + rooms / room_soft_cap)
```

| 参数 | Standard | Vanilla (Novice) | Tutorial |
|------|:--------:|:----------------:|:--------:|
| `base_upkeep` | 30 | 20 | 10 |
| `room_soft_cap` | 15 | 18 | 20 |

维护费对应 Resource Ledger 的 `UpkeepDeduction` 操作（执行顺序第 1 步）。

| 房间数 | 维护费/tick (Standard) | 累计维护费/1500tick | 说明 |
|:------:|:----------:|:------------------:|------|
| 1 | 32 | 48,000 | 基础代码正流 |
| 5 | 200 | 300,000 | 普通代码可承受 |
| 20 | 1,400 | 2,100,000 | 需要高效经济 |
| 50 | 6,500 | 9,750,000 | 强递减区间 |

维护费随房间数呈 **超线性增长**（O(n²) 趋势）。50 房间的维护费是 5 房间的 40 倍（而非 10 倍线性）。

存储税使用 Resource Ledger §2.2 连续边际税率公式，以下场景中的存储税数值均由固定步长整数积分导出。

## 2. 收支平衡表

> **显式假设：** 以下数值基于以下前提：
> - **free_upkeep**：前 1 controller + 3 drone 免维护费（`free_upkeep_ticks` 内，默认 2000 tick）。
> - **source income**：每 Source 基础产出 10/tick（L1 无 throughput 加成）。Source 升级（L2/L3/L4）提升产出。
> - **Controller passive income**：Controller 被动收入基础 40/tick + RCL bonus，使 1-3 房间基础代码保持正流。
> - **code throughput multiplier**：代码质量影响 Harvester 采集效率——基础效率 100%（每 WORK part 采集 1 单位/tick），优化后可达到 150%–200%（更优路径、更少 idle、并行采集）。以下分别展示无优化（throughput ×1.0）和优化（throughput ×1.5）两种情景。
> - **PvE/Wreckage income**：PvE 与 Wreckage 都从 world faucet 预算支出；Wreckage 来自被摧毁 drone 残骸，回收效率低于 Recycle 并随 tick 衰减。

### 2.1 Standard 模式 — 1 房间

| 收入源 | 量/tick | 说明 |
|--------|:------:|------|
| Source Harvester ×2 | 20 | L1 source, 10/tick each |
| Controller passive income | 45 | RCL 1 |
| **总收入** | **65** | free_upkeep 不计为收入；仅免除对应维护费 |

| 支出项 | 量/tick | 说明 |
|--------|:------:|------|
| 维护费（free_upkeep cover） | 0 | 免维护期内 |
| 存储税 | 0 | 存储 < 30% 免税（tier 0，见 Resource Ledger §2.2） |
| **总支出** | **0** | |

| 净流量 | 量/tick |
|--------|:------:|
| **净盈余** | **+65** |

> **1 房间基础正流**。初始资源包 + free_upkeep 允许玩家快速建立初始经济基础；free_upkeep 结束后维护费恢复（32/tick），基础收入 65/tick 仍为正流。PvP 开启时间由世界规则独立配置，不与 free_upkeep 到期绑定。

### 2.2 Standard 模式 — 2 房间（优化代码）

| 收入源 | 量/tick | 说明 |
|--------|:------:|------|
| Source Harvester ×4 | 80 | L1-2 sources, 20/tick × 1.0 效率 = 20/tick each |
| Controller passive income | 100 | RCL 2-3 avg |
| **总收入（优化 ×1.5 效率）** | **220** | Source 30/tick × 4 + Controller |
| **总收入（基础 ×1.0）** | **180** | |

| 支出项 | 量/tick |
|--------|:------:|
| 维护费 | 68 |
| 存储税 | 0 |
| **总支出** | **68** |

| 净流量 | 量/tick | 说明 |
|--------|:------:|------|
| **净盈余（基础）** | **+112** | throughput ×1.0 时正流 |
| **净盈余（优化）** | **+152** | 良好代码 + RCL 2-3 扩大盈余 |

> **2 房间阶段：基础代码可持续正流**。优化代码扩大扩张能力，但基础玩家不会在 1-3 房间进入维护费赤字悬崖。

### 2.3 Standard 模式 — 5 房间（良好代码）

| 收入源 | 量/tick | 说明 |
|--------|:------:|------|
| 11 Source Harvester | 330 | L1-2 sources, 20/tick × 1.5 效率 = 30/tick each |
| Controller passive income | 230 | RCL 3-4 avg |
| **总收入（优化）** | **560** | |
| **总收入（基础）** | **380** | throughput ×1.0 |

| 支出项 | 量/tick | 可重算输入 |
|--------|:------:|------|
| 维护费 | 200 | `30 × 5 × (1 + 5 / 15)` |
| 存储税 | 2 | `storage_capacity=1,000,000`, `stored_total=450,000`; continuous marginal integral ≈ 2.79, floor=2 |
| **总支出** | **202** | |

| 净流量 | 量/tick |
|--------|:------:|
| **净盈余（基础）** | **+178** |
| **净盈余（优化）** | **+358** |

> **5 房间阶段：普通代码可维持**。优化代码（×1.5）+ Controller 升级（RCL 3-4）+ Source 升级到 L2 提供扩张缓冲；普通代码通常停在 5-10 房区间。

### 2.4 Standard 模式 — 10 房间（高效代码）

| 收入源 | 量/tick | 说明 |
|--------|:------:|------|
| 23 Source Harvesters | 920 | L2-3 sources, 30/tick avg × 1.33 效率 (= ×2.0 总计) |
| Controller passive income | 500 | RCL 4-5 avg |
| PvE drop (global cap share) | 50 | global 30% cap × room share |
| Wreckage salvage | 40 | world faucet budget, decaying wreckage |
| **总收入（优化）** | **1,560** | |
| **总收入（基础）** | **1,150** | throughput ×1.0 |

| 支出项 | 量/tick | 可重算输入 |
|--------|:------:|------|
| 维护费 | 500 | `30 × 10 × (1 + 10 / 15)` |
| 存储税 | 30 | `storage_capacity=3,000,000`, `stored_total=1,650,000`; continuous marginal integral ≈ 30.24, floor=30 |
| **总支出** | **530** | |

| 净流量 | 量/tick |
|--------|:------:|
| **净盈余（基础）** | **+620** |
| **净盈余（优化）** | **+1,030** |

> **10 房间阶段：普通代码上沿**。多 Source 并行 + PvE/Wreckage 收益维持正流量；维护费超线性增长开始要求持续优化，普通代码通常在 5-10 房停滞。

### 2.5 Standard 模式 — 20 房间（需要高效经济）

| 收入源 | 量/tick | 说明 |
|--------|:------:|------|
| 46 Source Harvesters | 1,840 | L2-3 sources, avg 25/tick × 1.6 效率 |
| Controller passive income | 1,100 | RCL 5-6 avg |
| PvE drop (global cap share) | 100 | global 30% cap × room share |
| Wreckage salvage | 120 | world faucet budget, decaying wreckage |
| **总收入（优化）** | **4,700** | |
| **总收入（基础）** | **3,060** | throughput ×1.0 |

| 支出项 | 量/tick | 可重算输入 |
|--------|:------:|------|
| 维护费 | 1,400 | `30 × 20 × (1 + 20 / 15)` |
| 存储税 | 141 | `storage_capacity=4,000,000`, `stored_total=2,880,000`; continuous marginal integral ≈ 141.04, floor=141 |
| Drone spawn cost (avg 0.2/tick) | 40 | |
| **总支出** | **1,621** | |

| 净流量 | 量/tick |
|--------|:------:|
| **净盈余（基础）** | **+1,439** |
| **净盈余（优化）** | **+3,079** |

> **20 房间：顶级代码开始拉开差距**。维护费超线性增长（O(n²)）显著提高扩张门槛，但常数因子允许顶级代码消化惩罚并维持 15+ 房帝国。普通代码会因拥堵、闲置和防务成本在 5-10 房区间停滞。

### 2.6 Standard 模式 — 50 房间（软上限逼近）

| 收入源 | 量/tick | 说明 |
|--------|:------:|------|
| 115 Source Harvesters | 4,600 | L3-4 sources, avg 25/tick × 1.6 效率 |
| Controller passive income | 2,800 | RCL 6-7 avg |
| PvE drop | 500 | |
| Wreckage salvage | 300 | |
| **总收入（优化）** | **12,600** | |
| **总收入（基础）** | **7,700** | throughput ×1.0 |

| 支出项 | 量/tick | 可重算输入 |
|--------|:------:|------|
| 维护费 | 6,500 | `30 × 50 × (1 + 50 / 15)` |
| 存储税 | 364 | `storage_capacity=8,000,000`, `stored_total=7,200,000`; continuous marginal integral floor |
| Drone upkeep | 1,000 | |
| **总支出** | **7,864** | |

| 净流量 | 量/tick |
|--------|:------:|
| **净亏损（基础）** | **-164** |
| **净盈余（优化）** | **+4,736** |

> **50 房间是顶级代码区间**。维护费吞噬普通代码的余量；顶尖玩家通过路径、调度、防务、PvE 与 Wreckage 预算利用仍可维持。代码效率决定帝国规模——经济惩罚存在但最优算法可消化。

### 2.7 收支平衡汇总表 (Standard 模式)

以下汇总表提供 1/2/3/5/10/20/50 房间的收支对比。**所有数值为 canonical target curve 的初始参数化（illustrative estimates）；后续 playtest 仅用于校准 Resource Ledger 参数。** 存储税由 `storage_capacity`、`stored_total` 与 Resource Ledger 连续边际公式逐行重算。

|| 房间数 | 收入/tick (基础) | 收入/tick (优化) | 维护费/tick | storage_capacity | stored_total | 存储税/tick | storage tax formula | 净流量趋势 | 说明 |
||:------:|:--------:|:--------:|:---------:|:---------:|:---------:|:---------:|------|:---------:|------|
|| 1 | 65 | 65 | 0¹ | 1,000,000 | 200,000 | 0 | below 30%; no taxable tier | **基础正流**¹ | free_upkeep 扩大余量 |
|| 2 | 180 | 220 | 68 | 1,000,000 | 250,000 | 0 | below 30%; no taxable tier | **基础正流** | 1-3 房基础代码可持续 |
|| 3 | 260 | 360 | 108 | 1,000,000 | 290,000 | 0 | below 30%; no taxable tier | **基础正流** | Harvester + Controller passive income 驱动 |
|| 5 | 380 | 560 | 200 | 1,000,000 | 450,000 | 2 | continuous integral floor | **普通代码可维持** | 5 房普通代码稳定 |
|| 10 | 1,150 | 1,560 | 500 | 3,000,000 | 1,650,000 | 30 | continuous integral floor | **普通代码上沿** | 5-10 房为普通代码停滞带 |
|| 20 | 3,060 | 4,700 | 1,400 | 4,000,000 | 2,880,000 | 141 | continuous integral floor | **顶级代码扩张区间** | 15+ 房需要高效调度 |
|| 50 | 7,700 | 12,600 | 6,500 | 8,000,000 | 7,200,000 | 364 | continuous integral floor | **顶级代码可维持** | 经济惩罚存在但最优算法可消化 |

> **自维持区间：1-10 房间**。基础代码在 1-3 房保持正流，普通代码通常停在 5-10 房，顶级代码可达 15+ 房并继续扩张。O(n²) 经济惩罚形成 anti-snowball 压力，但不把 10 房以上定义为经济不理性；帝国规模由代码效率决定。

> `¹` 1 房间 free_upkeep 期内；free_upkeep 结束后维护费恢复仍为基础正流。free_upkeep 默认 2000 tick，初始资源包 `{Energy: 5000}` 提供建造缓冲。
>
> **可重算公式**：`upkeep = base_upkeep × rooms × (1 + rooms / room_soft_cap)`；`tax = floor(∫ marginal_rate_bp(u) d stored_units / 10000)`，其中 `marginal_rate_bp` 由 Resource Ledger §2.2 的 smoothstep 锚点定义。所有参数 world.toml 可配置——修改 `base_upkeep`、`room_soft_cap`、`storage_tax_curve`、`storage_capacity` 或 `stored_total` 后本表数值相应变化。
>
> **代码效率乘数含义**：1.5×-2.0× 表示减少 idle 时间、优化路径、减少拥堵——随着房间扩张，效率从 1.5× 逐渐提升到 2.0× 需要持续优化投入。200% (2×) 仅在完美路径 + 无拥堵 + 最优 body 组合下可达。
>
> **1→2 房间 transition**：free_upkeep 结束后，1 房基础收入约 65/tick、维护费 32/tick，仍为正流。玩家通过第二 Controller、额外 source 和 RCL 2-3 收入提升到 2 房基础 180/tick；优化代码后达 220/tick，对应 2 房维护费 68/tick。
>
> **设计目标**：**新手经济平滑、扩张由代码效率决定**。1-3 房基础代码正流；5-10 房普通代码可维持但扩张趋缓；15+ 房需要顶级调度、路径、物流和战斗代码消化 O(n²) 惩罚。本文给出 canonical target curve 的初始参数化；playtest 仅用于校准 `base_upkeep`、`room_soft_cap`、效率曲线等参数。

## 3. 模式差异

| | Tutorial | Vanilla (Novice) | Standard |
|------|:--------:|:----------------:|:--------:|
| `base_upkeep` | 10 | 20 | 30 |
| `room_soft_cap` | 20 | 18 | 15 |
| `pvp_unlock_tick` | 3000 | 2500 | 2000 |
| `pve_global_cap_pct` | 50% | 40% | 30% |
| `global_transfer_enabled` | true | true | true |
| `allied_transfer_enabled` | true | false | **true (Restricted)** |
| `storage_tax` | 免税 | continuous marginal anchors 30/60/85/100% | continuous marginal anchors 30/60/85/100% |
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

Controller/Depot age repair 的权威模型见 `specs/core/resource-ledger.md` §2.4：无全局 repair cap，Controller 免费，Depot 消耗本地资源，维修吞吐只受物理范围、每设施容量和队列约束。

> **存储税权威源**：曲线锚点见 `design/gameplay.md` §8「累进存储税」和 `specs/core/resource-ledger.md` §StorageTax。Tutorial 全免，Vanilla/Standard 使用相同 曲线锚点（税率由 `storage_tax_curve` 配置）。
>
> **Allied Transfer 模式差异**：Standard 默认启用 Restricted Allied Transfer（fee=200bp, delay=200 tick, cooldown=500 tick, daily_cap=10000, intercept enabled）。Novice/Tutorial 可通过 world.toml 禁用 (`allied_transfer_enabled = false`)。Arena 模式禁用 Allied Transfer（竞技公平）。

Tutorial 模式弱维护费 + 长保护期，适合新手学习。Vanilla 模式中等维护费，Standard 模式启用完整 anti-snowball。

## 4. Anti-Snowball 证明

令房间数为 `n`。边际收益函数：

```
r(n) = expected_income(n)
     = source_income(n) × code_throughput(n) + controller_income(n) + pve_award(n)
```

`source_income(n)` 受房间 source 密度与 harvester 通行拥堵约束，按近似线性增长；`code_throughput(n)` 有上界 `E_max`；`pve_award(n)` 受 Resource Ledger 的 Global/Zone/Player/Event 四维 budget 约束。故存在常数 `A`、`B`，使 `r(n) <= A × n + B`。

边际成本函数：

```
c(n) = upkeep(n) + tax(n) + conversion_loss(n)
upkeep(n) = base_upkeep × n × (1 + n / room_soft_cap)
tax(n) = continuous_storage_tax(stored(n), capacity(n))
conversion_loss(n) >= 0
```

其中 `upkeep(n)` 含二次项 `(base_upkeep / room_soft_cap) × n²`，`tax(n)` 非负且随存储利用率单调不减，`conversion_loss(n)` 非负。于是：

```
c(n) >= (base_upkeep / room_soft_cap) × n²
r(n) <= A × n + B
```

定义净流量 `f(n)=r(n)-c(n)`。`f(n)` 在小 `n` 区间可为正；当 `n -> infinity` 时，二次成本项支配线性收益项，`f(n) -> -infinity`。因此存在有限均衡点 `n*`，满足 `f(n*) >= 0` 且 `f(n*+1) < 0`。按本文 Standard 初始参数，良好代码下 `n*` 位于 10 与 20 房之间：10 房净盈余约 +100/tick，20 房净亏损约 -841/tick。

No Teleport 物流成本通过 `conversion_loss(n)` 与延迟约束提高大帝国边际成本，但不是证明有限均衡点的必要条件；维护费二次项已足以保证 `n*` 存在且有限。

## 5. 与 Resource Ledger 的关系

**Resource Ledger (`specs/core/resource-ledger.md`) 为所有收支计算的单一权威源。** 本文档只做数值验证和模式对比，不重新定义费率或公式。

| 经济概念 | 权威定义位置 | 本表角色 |
|---------|------------|---------|
| 维护费 (UpkeepDeduction) | Resource Ledger §Empire Upkeep | 验证数值合理性 |
| 回收 (RecycleRefund) | Resource Ledger §6 (lifespan 10%–50%) | 引用 |
| 存储税 (StorageTax) | Resource Ledger §2 + gameplay.md §8 曲线锚点 | 引用 |
| 费率模型 (basis points) | Resource Ledger §2 | 不重复 |

## 6. 存储税均衡证明 (Storage Tax Equilibrium Proof)

存储税使用 Resource Ledger §2.2 连续边际税率公式，以下场景中的存储税数值均由固定步长整数积分导出。
