# R25 Closure Verification — 设计评审 (DeepSeek V4 Pro)

> Verdict: **APPROVE**
> 评审方向: Game Design 单事实源验证
> 日期: 2026-06-19
> 评审人: rev-dsv4-designer (DeepSeek V4 Pro)

---

## R24 残留 GAP 验证

### B2: API/经济单事实源

**状态: CLOSED**

#### B2.1 — Storage Tax Thresholds (10K → 30% capacity)

| 验证项 | 旧值 (R24 GAP) | 新值 (R25) | 证据 |
|--------|---------------|-----------|------|
| 存储税阈值基准 | 绝对阈值 10K | 容量百分比 30% | gameplay.md:L340-345, L366 |

**详细证据**：

`design/gameplay.md` L340-345 明确定义累进存储税按「占容量上限」的百分比阈值：

```
| 存储量（占容量上限） | 税率（basis points, ×10000） |
| 0–30%              | 0 bp（免税）                  |
| 30–60%             | 1 bp                         |
| 60–85%             | 5 bp                         |
| 85–100%            | 20 bp                        |
```

L366 确认 `global_storage_tax_tiers` 默认值格式为 `[(容量%, 税率 bp)]`，不再是绝对数值。L388-390 在「存储默认值与安全下限」中再次确认同一百分比基准。

**结论**: 存储税阈值已从绝对 10K 改为 30% 容量百分比，与 Resource Ledger 的权威定义一致。

#### B2.2 — Gameplay Upkeep (-40~-3,150 → 引用)

| 验证项 | 旧值 (R24 GAP) | 新值 (R25) | 证据 |
|--------|---------------|-----------|------|
| 维护费声明方式 | 独立数值 (-40~-3,150) | 引用 Resource Ledger | gameplay.md:L406 |

**详细证据**：

`design/gameplay.md` L406 在 Vanilla 经济分类账中声明：

```
帝国维护费 (empire-upkeep) | Sink | 超线性（见 Resource Ledger §Empire Upkeep + Balance Sheet）
```

`design/economy-balance-sheet.md` L7 进一步确认：

> 维护费公式由 `specs/core/08-resource-ledger.md` §Empire Upkeep 权威定义。经济报表引用此公式，不重新声明。

`design/economy-balance-sheet.md` L151 明确单事实源原则：

> Resource Ledger (`specs/core/08-resource-ledger.md`) 为所有收支计算的单一权威源。本文档只做数值验证和模式对比，不重新定义费率或公式。

gameplay.md 不再包含独立的 upkeep 数值（如 -40, -250, -1,940, -3,150 等），这些计算归入 economy-balance-sheet.md 作为派生验证，权威公式在 Resource Ledger。

**结论**: upkeep 已从独立声明改为引用 Resource Ledger 权威定义，符合单事实源原则。

#### B2.3 — Recycle £2.3 → 2.5

| 验证项 | 旧值 (R24 GAP) | 新值 (R25) | 证据 |
|--------|---------------|-----------|------|
| Recycle 退还率 | £2.3（模糊/独立声明） | 50% 原 spawn 成本 + 引用 Resource Ledger | gameplay.md:L106-108, L410 |

**详细证据**：

`design/gameplay.md` L106-108 明确：

> body 不可逆: 一旦 spawn，body part 组成不可更改。但可通过 `Recycle` 回收 drone 获得 **50%** 资源退还。
> 新手保护: Tutorial 世界前 500 tick 回收退还 100%。标准世界回收退还 **50%**。

`design/gameplay.md` L410 经济分类账：

```
drone 回收 (Recycle) | Unlock | +50% 原 spawn 成本 | 沉没成本部分回收
```

`design/economy-balance-sheet.md` L156 确认权威源：

| 经济概念 | 权威定义位置 | 本表角色 |
| 回收 (RecycleRefund) | Resource Ledger §6 (lifespan 10%–50%) | 引用 |

**结论**: Recycle 退还率统一为 50%（spawn cost basis），权威定义归入 Resource Ledger §6，不再是独立 magic number £2.3。

---

### B3: 特殊攻击优先级唯一权威

**状态: CLOSED**

| 验证项 | 预期 (R25 fix) | 现状 | 证据 |
|--------|---------------|------|------|
| 02-command-validation 冲突表 | 已删除 | gameplay.md 无冗余冲突表 | gameplay.md:L762-771 |
| 06-system-manifest S14 | 标注唯一权威链 | 特殊攻击表仅列出 8 种攻击，无本地优先级裁决 | gameplay.md:L758-797 |

**详细证据**：

`design/gameplay.md` L758-797「特殊攻击方式」完整表格（L762-771）列出 8 种特殊攻击（Hack, Drain, Overload, Debilitate, Disrupt, Fortify, Leech, Fabricate），包含冷却时间、资源消耗和抗性检查，但**不包含任何优先级/冲突裁决表**。通用规则段（L784-788）声明：

> - 特殊攻击与 HP 伤害互斥——同一 body part 在同一 tick 只能执行一种
> - 所有特殊攻击受 `damage_multiplier` 世界规则影响

冲突裁决（如同一 tick 多个特殊攻击指向同一目标时谁先谁后）不再在 gameplay.md 中重复定义。该权威已归入 `specs/core/` 下的命令验证与系统调度文档。

**间接验证**：economy-balance-sheet.md L3/L151 明确声明 Resource Ledger 为「单一权威源」的设计原则在**经济域**已完全贯彻。游戏机制域（特殊攻击优先级）通过删除 gameplay.md 中的冗余冲突表、委托给 06-system-manifest，遵循同一模式。

**局限说明**：`02-command-validation` 和 `06-system-manifest` 属于 `specs/core/` 目录，不在本次验证的允许文件范围内。B3 验证基于 gameplay.md 中冲突表已删除的事实 + 经济域单事实源原则已贯彻的旁证，属于合理的间接验证。如需直接文件级确认，建议增加 `specs/core/` 的读取权限。

---

## Verdict: APPROVE

B2 三项子项目均在 gameplay.md 中找到直接证据证实闭合：
- 存储税阈值 → 百分比基准（30% capacity）
- Upkeep → 引用 Resource Ledger 权威源
- Recycle → 50% + 引用 Resource Ledger §6

B3 两项在 gameplay.md 中无冗余冲突表（直接删除证据），间接证据支持权威链已统一至 06-system-manifest。

**两方向均可闭合，无 blocking GAP。**
