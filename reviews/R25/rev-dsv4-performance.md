# R25 CV-性能 — Closure Verification (DeepSeek V4 Pro)

> 评审员：rev-dsv4-performance (DeepSeek V4 Pro)
> 日期：2026-06-19
> 范围：R24 残留 B2/B3 GAP 闭合验证（仅验证，不发现新问题）

---

## B2-GAP: API/经济单事实源

**结论：CLOSED**

### 1. Storage Tax Thresholds (10K→30% capacity)

| 证据 | 文件 | 行号 |
|------|------|------|
| 累进存储税按 capacity 百分比分层：`[(30,0),(60,1),(85,5),(100,20)]` | `design/gameplay.md` §2.2 | 340-347 |
| 税率统一由 `global_storage_tax_tiers` 配置 | `design/economy-balance-sheet.md` §6 | 162 |
| Resource Ledger §2.2 为 tiered 公式权威源 | `specs/core/08-resource-ledger.md` §2 | 63-66 |

旧 R24 GAP 提及的绝对阈值（10K）已替换为 capacity 百分比分层（30%/60%/85%/100%）。
第一个 tier 边界从绝对值 10,000 改为相对值 30% capacity，消除了规模耦合。

### 2. Gameplay Upkeep (-40~-3,150→引用)

| 证据 | 文件 | 行号 |
|------|------|------|
| economy-balance-sheet.md 明确声明 Resource Ledger 为唯一权威源 | `design/economy-balance-sheet.md` L3 | 3 |
| 维护费 = `base_upkeep × rooms × (1 + rooms / room_soft_cap)` | `design/economy-balance-sheet.md` §1 | 9-11 |
| Resource Ledger 声明为 "唯一设计/数学权威" | `specs/core/08-resource-ledger.md` L7 | 7 |
| gameplay.md 帝国维护费引用 Resource Ledger | `design/gameplay.md` 行407 | 407 |

旧 R24 GAP 中 gameplay.md 内联的硬编码维护费数值（-40、-3,150 等）已替换为
公式化计算 + 到 Resource Ledger 的引用。economy-balance-sheet.md 中的数值
（55/375/3,000/15,000 per tick for 1/5/20/50 rooms）均由公式推导，非重复声明。

### 3. Recycle §2.3→2.5

| 证据 | 文件 | 行号 |
|------|------|------|
| Recycle 详细退还规则移至 `02-command-validation.md` §3.18 | `specs/core/02-command-validation.md` | 483-505 |
| lifespan 挂钩退还公式：`refund_pct = max(0.1, 0.5 × (remaining/total))` | 同上 | 490-495 |
| gameplay.md 仅保留简介（"回收 drone 获得 50% 资源退还"） | `design/gameplay.md` | 106 |

旧 R24 GAP 中 gameplay.md §2.3 的 Recycle 详细规则（含退还比例计算）已迁移到
`specs/core/02-command-validation.md` §3.18，并升级为与 lifespan 挂钩的精确退还公式
（含 10% 下限），消除了 "末期回收套利" 的经济漏洞。gameplay.md 中仅保留概要引用。

---

## B3-GAP: 特殊攻击优先级唯一权威

**结论：CLOSED**

### 1. 02-command-validation 已删除冲突表

| 证据 | 文件 | 行号 |
|------|------|------|
| 明确标注 "R24 B3-GAP 修复" | `specs/core/02-command-validation.md` §3.16 | 435 |
| "此处不再重列可冲突的优先级顺序" | 同上 | 435-436 |
| "实现者必须以此为准，不得从本文档复制/粘贴优先级链" | 同上 | 437 |

旧 R24 GAP 中的问题——`02-command-validation.md` 与 `06-system-manifest.md` 各自
维护一份可冲突优先级表——已修复。02 文档现在显式删除旧表，仅保留到 06 的引用。

### 2. 06-system-manifest S14 标注唯一权威链

| 证据 | 文件 | 行号 |
|------|------|------|
| S14 reducer 定义唯一权威优先级链：**Hack > Drain > Overload > Debilitate > Disrupt > Fortify** | `specs/core/06-phase2b-system-manifest.md` S14 | 188 |
| "此为 Swarm 引擎中该优先级链的唯一定义" | 同上 | 188 |
| "`02-command-validation.md` 已删除旧优先级表" | 同上 | 188 |
| Special Attack Unique Writer Contract 表 | `specs/core/06-phase2b-system-manifest.md` §表 | 220-229 |

旧 R24 GAP 中的问题——特殊攻击优先级链在多个文档中重复定义，存在不一致风险——已修复。
`06-phase2b-system-manifest.md` §S14 现在持有该优先级链的唯一定义，且显式标注
"02-command-validation.md 已删除旧优先级表"。Unique Writer Contract 进一步确保
每种 status component 有且仅有一个写入者 system。

---

## Verdict: APPROVE

B2 和 B3 均 CLOSED，无残留 GAP。

| GAP | 状态 | 关键变更 |
|-----|------|---------|
| B2 | CLOSED | 存储税从绝对值改为百分比分层 (30% capacity)；维护费改为公式 + Resource Ledger 引用；Recycle 详细规则迁移到 02-command-validation §3.18 + lifespan 挂钩公式 |
| B3 | CLOSED | 02 删除旧优先级表并引用 06 §S14；06 §S14 声明唯一权威链 Hack>Drain>Overload>Debilitate>Disrupt>Fortify；Unique Writer Contract 强化 |

**评级：APPROVE** — 两项 R24 残留 GAP 均已在 R25 设计中充分闭合。
