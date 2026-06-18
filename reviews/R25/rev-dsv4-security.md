# R25 Closure Verification — 安全方向 (rev-dsv4-security / DeepSeek V4 Pro)

> 仅验证 R24 残留 B2/B3 GAP 是否闭合。禁止开放式评审、禁止发现新问题。

## B2: API/经济单事实源

**Verdict: CLOSED**

### 1. Storage Tax Thresholds (10K→30% capacity)

旧设计使用固定阈值（如 10K）。新设计使用**累进存储税（Progressive Storage Tax）**，按存储容量百分比阶梯征收：

| 来源 | 证据 |
|------|------|
| `design/gameplay.md` §8 累进存储税 (line 366) | `global_storage_tax_tiers = [(30,0),(60,1),(85,5),(100,20)]` — 百分比阶梯，非固定数值 |
| `design/economy-balance-sheet.md` (line 29) | `storage_tax_tiers = [(30,0),(60,1),(85,5),(100,20)]` — 百分比阶梯 |
| `design/economy-balance-sheet.md` (line 136) | "存储税权威源：tier 定义见 `design/gameplay.md` §8 和 `specs/core/08-resource-ledger.md` §StorageTax" |
| `design/economy-balance-sheet.md` (line 44) | 实际运算 "存储 < 30% 免税（tier 0）" — 验证百分比模型生效 |

→ 存储税从固定阈值改为**百分比容量阶梯模型**。GAP 闭合。

### 2. Gameplay Upkeep (-40~-3,150→引用)

旧设计可能在多处硬编码具体维护费数值。新设计将维护费公式收敛到**单一权威源**：

| 来源 | 证据 |
|------|------|
| `design/economy-balance-sheet.md` (line 7-8) | "维护费公式由 `specs/core/08-resource-ledger.md` §Empire Upkeep 权威定义。经济报表引用此公式，不重新声明。" |
| `design/economy-balance-sheet.md` (line 151) | "Resource Ledger (`specs/core/08-resource-ledger.md`) 为所有收支计算的单一权威源。" |
| `design/economy-balance-sheet.md` (line 18-25) | 维护费数值由公式 `upkeep = base_upkeep × rooms × (1 + rooms / room_soft_cap)` 导出，非硬编码 |

→ 维护费数值由 Resource Ledger 单一公式导出，各处引用而非重复定义。GAP 闭合。

### 3. Recycle (£2.3→2.5)

旧设计使用固定退还价格。新设计使用 **lifespan 比例退还公式**：

| 来源 | 证据 |
|------|------|
| `specs/core/02-command-validation.md` §3.18 (line 489-490) | `refund_pct = max(0.1, 0.5 × (remaining_lifespan / total_lifespan))` — 浮动退还比例 |
| `specs/core/02-command-validation.md` (line 497-504) | 退还比例从 50%（新生）线性下降到 10%（末期），附带经济约束验证 |
| `design/economy-balance-sheet.md` (line 156) | "回收 (RecycleRefund) \| Resource Ledger §6 (lifespan 10%–50%) \| 引用" |
| `design/gameplay.md` (line 106) | "可通过 `Recycle` 回收 drone 获得 50% 资源退还" + Tutorial 新手保护 |

→ Recycle 由固定价格改为 lifespan 比例退还模型，经济约束完整。GAP 闭合。

---

## B3: 特殊攻击优先级唯一权威

**Verdict: CLOSED**

### 验证项 1: 02-command-validation 已删除冲突表

| 来源 | 证据 |
|------|------|
| `specs/core/02-command-validation.md` §3.16 同 tick 多命中优先级 (line 435-438) | "R24 B3-GAP 修复：特殊攻击优先级以 `06-phase2b-system-manifest.md` §S14 为唯一权威。**此处不再重列可冲突的优先级顺序。**" |
| `specs/core/02-command-validation.md` (line 437) | "实现者必须以此为准，**不得从本文档复制/粘贴优先级链。**" |

→ 02-command-validation.md 已显式删除冲突优先级表，仅保留交叉引用。

### 验证项 2: 06-system-manifest S14 标注唯一权威链

| 来源 | 证据 |
|------|------|
| `specs/core/06-phase2b-system-manifest.md` §S14 (line 6) | "本文档是 Swarm 引擎**全部 tick 系统执行顺序的唯一权威定义**" |
| `specs/core/06-phase2b-system-manifest.md` §S14 reducer 实现 (line 188-189) | "按**唯一权威优先级链**裁决：Hack > Drain > Overload > Debilitate > Disrupt > Fortify（此为 Swarm 引擎中该优先级链的唯一定义——`02-command-validation.md` 已删除旧优先级表）" |
| `specs/core/06-phase2b-system-manifest.md` §Special Attack Unique Writer Contract (line 217-231) | 每种 status component 有且仅有一个写入者 system（S22 status_adv），并发写入结构完整 |

→ S14 明确声明为优先级链的唯一定义，并与 02-command-validation 交叉引用一致。唯一权威链确立。

---

## Verdict

**APPROVE**

B2（API/经济单事实源）三项子项全部闭合：
- 存储税从固定阈值改为百分比阶梯模型
- 维护费收敛到 Resource Ledger 单一公式源
- Recycle 改为 lifespan 比例退还公式

B3（特殊攻击优先级唯一权威）两项子项全部闭合：
- 02-command-validation 已删除冲突优先级表
- 06-system-manifest S14 标注唯一权威链

无残留 GAP。
