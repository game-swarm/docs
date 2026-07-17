# Empirical Calibration Requirements

以下项目依赖 playtest 数据或数学模型验证；文档定义目标机制，实测数据用于校准参数

---

## PG-1: 早期经济曲线与 first-hour 承诺

**校准需求**: D4 裁决了方向，目前的 Standard balance sheet 模型（基于 `resource-ledger.md` 参数）预测 1/5/20/50 房间在无代码优化时的净流量。目前的实测校准旨在验证：

| 需要的数据 | 说明 |
|-----------|------|
| tick 0/500/1500/2000/5000/10000 实际 net flow | 从 playtest 中收集各玩家在不同时间点的资源收支 |
| 2-room/5-drone 是否可达正平衡 | 验证在 free_upkeep (2000 ticks) 结束后，基础代码是否能维持正盈余 |
| drone upkeep 统一配置后的实际影响 | 验证 Resource Ledger 中定义的全量 upkeep 对小规模帝国的实际压力 |
| Harvest 效率上限的典型值 | 验证 1.5x-2.0x 的代码优化效率是否在实际 playtest 中可达成 |

**涉及文件**: `design/gameplay.md`, `specs/core/resource-ledger.md`, `design/economy-balance-sheet.md`

**校准条件**: playtest 产出 tick-by-tick 经济数据 → 与文档模型对比 → 调整参数或文档

---

## PG-4: Standard 经济中期自维持区间

**涉及文件**: `design/economy-balance-sheet.md`

**需要验证**:

| 验证项 | 说明 |
|-------|------|
| 2-5 房良好代码下正流量可达性 | 验证自维持区间的下界（2-5 房）是否如模型预测般具有正盈余 |
| 20 房转入净亏损的边界精度 | 验证边际收益递减模型在 20 房间附近的转折点 |
| Source 产出 × 效率乘数模型准确性 | 验证 Harvester 采集效率乘数（1.0-2.0）与实际代码表现的匹配度 |
| RCL 升级带来的被动收入梯度 | 验证 Controller passive income 的数值分布是否符合预期 |

**校准条件**: playtest 收集 ≥50 active players / ≥5000 tick 的经济数据，验证模型预测的自维持区间界限 → 调参或调整文档


---

## PG-2: 特殊攻击完整状态机

**状态机模型**: 已规范化，待 playtest 验证平衡性。权威参数见 `specs/reference/special-attack-table.md`；命令校验与状态机见 `specs/core/command-validation.md` §3.10-3.19。

| 攻击 | 已规范化项 | 需 playtest 验证 |
|------|------|-----------------|
| **Hack Neutral 窗口** | Neutral、控制锁、反制窗口已在 command-validation 中定义 | Hack 的频率与价值交换是否过强 |
| **Overload 多攻击者** | 50 tick per-target 全局冷却与下限证明已规范化 | 是否仍存在协同压制体感问题 |
| **Hack 成功率公式** | 参数入口归一到 special-attack-table / ActionRegistry | 高价值 drone 是否应进一步调成功率 |
| **Fabricate 目标结构** | Fabricate action 参数与 channel 规则已规范化 | 转化建筑类型与主权交互是否平衡 |
| **Leech/Debilitate** | 叠加/反制矩阵已规范化 | 与其他 special attack 的组合是否过强 |

**涉及文件**: `specs/reference/special-attack-table.md`, `specs/core/command-validation.md` §3.10-3.19, `design/gameplay.md`

**校准条件**: playtest 验证 8 个 special attack 的博弈深度 → 补齐缺失的状态转换 → 调参

---

## PG-3: Storage tax 与 PvE faucet 量化

**校准需求**: 缺少玩家可理解的时间尺度和 PvE 定位：

| 目标 | 需要 | 原因 |
|------|------|------|
| `bp/tick` 单位 | per-hour / per-day 人类可读单位 | 玩家无法直观理解 bp/tick 的经济影响 |
| PvE 收益 = 独立数值 | 阶段收入表（early/mid/late game） | 玩家需要知道 PvE 的定位：catch-up / skill test / risk reward |
| global↔local 费率不对称 (1% vs 5%) | 数学理由或玩家可接受的解释 | 6% round-trip 成本需要被理解而非被抱怨 |
| Storage tax 0.1%/tick | 实际 playtest 中的资源流失曲线 | 验证是否过于惩罚长期存储 |

**涉及文件**: `specs/core/resource-ledger.md`, `design/economy-balance-sheet.md`

**校准条件**: playtest 收集实际经济数据 → 将 bp/tick 转换为人类时间尺度 → 明确 PvE 定位

---

## 追踪状态

| ID | 项 | 校准条件 | 预计来源 |
|----|-----|---------|---------|
| PG-1 | 早期经济曲线 | tick-by-tick 经济数据 | World playtest (≥50 active players, ≥5000 tick) |
| PG-2 | 特殊攻击状态机 | 8 个 special attack 博弈验证 | Arena playtest + 针对性测试场景 |
| PG-3 | Storage tax / PvE 量化 | 经济数学模型 + 玩家反馈 | 经济参数 sweep simulation |

这些是经验校准项；机制已在目标文档中定义，参数随实测数据调整。